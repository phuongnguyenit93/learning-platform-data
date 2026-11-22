# Chuyển tiếp Bearer token bằng WebClient và kiểm soát ranh giới tin cậy trong Spring Security WebFlux

## Mục tiêu bài học

Bài này thuộc module **Spring Security – reactive**, chủ đề **Resource Server Opaque**. Sau khi học xong, bạn có thể:

1. Mô tả chính xác luồng request từ client đến Spring WebFlux Resource Server A, qua OAuth2 Token Introspection, rồi tới downstream Resource Server B bằng `WebClient`.
2. Biết lúc nào có thể **relay đúng Bearer token đã xác thực**, lúc nào phải dùng **OAuth2 Token Exchange / on-behalf-of** hoặc một token riêng bằng `client_credentials`.
3. Dùng `ServerBearerExchangeFilterFunction` trong reactive `WebClient`, hiểu nó lấy token credential từ `Authentication` trong Reactor Context và không tự refresh token.
4. Thiết kế **WebClient chuyên dụng cho một upstream tin cậy**; không cài filter chuyển token trên WebClient chung cho URL tùy ý, không nhận absolute URL từ client.
5. Bảo vệ ranh giới tin cậy: allowlist scheme/host/path, HTTPS/mTLS, redirect policy, DNS/egress, chống SSRF, audience/scope, token secrecy, correlation IDs và failure handling.
6. Viết Spring Boot 3.x / Java 17+ demo với `ReactiveOpaqueTokenIntrospector`, `SecurityWebFilterChain`, WebClient có relay và WebClient không relay, rồi kiểm thử bằng `WebTestClient`/`MockWebServer`/`StepVerifier`.
7. Phân biệt HTTP 401/403 của **caller → A** với lỗi token không được **B** chấp nhận; quản lý không rò token ở logs, redirect, exception body và tracing.
8. Hiểu vì sao token relay không tạo thêm quyền và không làm thay bước xác thực/phân quyền độc lập của downstream.

> **Phiên bản áp dụng:** Spring Security 6.5.x (reactive) trên Java 17+ / Spring Boot 3.5.16 để có ví dụ dễ tái tạo. Spring Boot 3.5.16 là bản OSS cuối nhánh 3.5; khi triển khai mới cần ưu tiên dòng còn được hỗ trợ và cập nhật bản vá bảo mật. Các mã ví dụ ngoài project runnable được ghi rõ là fragment.

---

## 1. Tình huống nghiệp vụ

Một frontend có access token `reader-token` do Authorization Server phát, gọi:

```http
GET /api/relay/profile HTTP/1.1
Host: api-edge.example.test
Authorization: Bearer reader-token
```

API A là **Spring Security WebFlux Resource Server dùng opaque token introspection**. A cần gọi dịch vụ B để lấy hồ sơ:

```text
                    Authentication boundary                 Trust boundary
                     (client -> A)                            (A -> B)
                           |                                     |
Frontend                   v                                     v
  |
  | Authorization: Bearer <opaque-token>
  v
+-----------------------------+              +-------------------------------+
| Resource Server A           |              | Resource Server B             |
| Spring WebFlux              |              | profile-service               |
|                             |              |                               |
| 1. Token Introspection      |              | 5. Kiểm tra Bearer token      |
| 2. Authentication           |              | 6. Kiểm tra aud/scope/ACL     |
| 3. Authorization            |              | 7. Trả profile nếu hợp lệ     |
| 4. WebClient relay          |------------->|                               |
+-----------------------------+              +-------------------------------+
             |   ^                                          ^
             |   |                                          |
             v   |                                          |
      Authorization Server                             (Có thể introspect
      POST /introspect                                 lại hoặc verify riêng)
      active, aud, scope, sub
```

A không nên lấy raw HTTP `Authorization` rồi chuyển tiếp ngay. Trình tự đúng là:

1. A nhận Bearer token qua WebFlux Security chain.
2. `ReactiveOpaqueTokenIntrospector` hỏi **Authorization Server đáng tin** xem token active và thông tin scope/audience.
3. A xác thực danh tính/chủ thể, áp luật vào endpoint `/api/relay/profile`.
4. Trong request đã qua authorization, **WebClient chuyên dụng** lấy token credential từ `Authentication` trong Reactor Context.
5. A gửi token đến **B đã được allowlist** qua HTTPS.
6. B **tự** xác thực token, kiểm tra audience và quyền của chính mình; A cho qua không đồng nghĩa B phải cho qua.
7. A trả response nghiệp vụ đã được chọn lọc, không echo token hoặc credentials của request.

**Bearer token là credential:** ai giữ chuỗi token có thể sử dụng nó trong phạm vi quyền của token. Chuyển tiếp sai host, ghi vào log hoặc follow redirect không an toàn có thể gây rò quyền tương đương làm lộ mật khẩu tạm thời.

## 2. Resource Server Opaque xác thực inbound token như thế nào?

Trong Spring Security WebFlux:

```text
Incoming Authorization: Bearer TOKEN
          |
          v
ServerBearerTokenAuthenticationConverter
          |
          v
Opaque-token authentication
          |
          v
ReactiveOpaqueTokenIntrospector.introspect(TOKEN)
          |
          v
Authorization Server RFC 7662
          |
          +-- active=false / token invalid -> 401; không tạo principal
          |
          +-- active=true, sub, aud, scope, exp...
                    |
                    v
             OAuth2AuthenticatedPrincipal
                    |
                    v
             BearerTokenAuthentication
             - Principal: introspection attributes
             - Credentials: OAuth2AccessToken
             - Authorities: SCOPE_profile.read ...
                    |
                    v
             Reactor SecurityContext
                    |
                    v
             HTTP authorization + controller
```

**Ranh giới quan trọng:** một token đã pass introspection ở A **chỉ** chứng minh token được Authorization Server chấp nhận theo chính sách của A. Token có thể không được phép vào B vì audience khác, thiếu scope hoặc resource-owner/tenant không phù hợp.

Introspection JSON ví dụ:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "profile.read",
  "aud": ["api://relay-edge", "api://profile-service"],
  "client_id": "web-portal",
  "exp": 1799999999
}
```

Trong ví dụ, audience được phát rõ cho **cả A và B** để minh họa trường hợp có thể relay một token theo hợp đồng với Authorization Server. Không phải mọi provider hỗ trợ multi-audience. Nếu B chỉ chấp nhận `api://profile-service` mà token chỉ có `aud=api://relay-edge`, B **phải từ chối** token đó dù A đã cho phép caller.

Mặc định, mỗi scope được ánh xạ thành authority `SCOPE_<scope>`, ví dụ `scope: "profile.read"` tạo `SCOPE_profile.read`. Endpoint A dùng `hasAuthority("SCOPE_profile.read")`; B có thể yêu cầu thêm quyền khác theo contract riêng.

### Opaque token không có nghĩa A đọc được claim từ token string

Với opaque token, chuỗi `reader-token` chỉ là identifier/credential. Không parse token theo dấu chấm, không tự decode và không tin giá trị `scope` do caller gửi thêm qua header/query. Quyền phải đến từ introspection server tin cậy hoặc service cấp quyền đã xác minh.

## 3. ServerBearerExchangeFilterFunction là gì?

Spring Security có filter dành riêng cho **reactive token relay**:

```java
import org.springframework.security.oauth2.server.resource.web
        .reactive.function.client.ServerBearerExchangeFilterFunction;
```

Một cách dùng cơ bản:

```java
@Bean
WebClient downstreamWebClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
```

Khi downstream `WebClient` thực hiện request trong **Reactor Context chứa Authentication** có credentials kiểu `AbstractOAuth2Token`, filter lấy token value và thêm `Authorization: Bearer ...` vào request outbound. Trong Resource Server Opaque mặc định, authentication thường là `BearerTokenAuthentication` với OAuth2 token credential.

**Năm điều cần nhớ:**

1. Filter **không tự xác thực token inbound**: đó là việc của WebFlux Security chain ở A.
2. Filter **không tự kiểm tra audience/scope cho B**: việc đó thuộc contract A–B và Resource Server B.
3. Filter **không tự refresh token** khi hết hạn. Nó relay token đang có; khác với OAuth2 Client dùng `ReactiveOAuth2AuthorizedClientManager`.
4. Filter không tự tạo hoặc đánh giá allowlist hostname/URL. **Mọi request gửi bởi WebClient có filter có thể mang token** nếu có eligible Authentication.
5. Filter lấy token từ **Reactor SecurityContext**; nếu làm mất context hoặc chạy ngoài HTTP request, nó thường không tìm được credential để gắn.

### Không phải Servlet filter

| Ngăn xếp | Class | Nguồn context |
| --- | --- | --- |
| WebFlux reactive | `ServerBearerExchangeFilterFunction` | Reactor SecurityContext |
| Servlet | `ServletBearerExchangeFilterFunction` | Servlet/ThreadLocal SecurityContext |
| OAuth2 Client token acquisition | `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Authorized client manager, registration/principal |
| WebFlux Resource Server inbound | `ServerHttpSecurity.oauth2ResourceServer(...).opaqueToken(...)` | Bearer auth + introspection |

Đừng lấy ví dụ Servlet `SecurityFilterChain`/`HttpSecurity` rồi dán vào WebFlux, và cũng không dùng `.block()` trong Netty event loop để lấy authentication/token.

## 4. Token relay, client_credentials và token exchange: khi nào dùng?

Ba chiến lược thường gặp:

| Chiến lược | Bearer gửi tới B | Khi thích hợp | Rủi ro chính |
| --- | --- | --- | --- |
| **Token relay** | Cùng token mà caller gửi cho A | Token được IdP phát với audience/scope hợp lệ cho B và B chấp nhận delegation này | Token rộng quyền, lộ token nhiều hop |
| **OAuth2 Token Exchange** (RFC 8693) | Token mới do IdP phát cho B thay mặt caller | B cần audience/scope riêng hoặc giảm quyền theo hop | Cần IdP hỗ trợ exchange và mapping policy |
| **client_credentials** | Token của A/service identity | B thực hiện tác vụ hệ thống, không nhân danh end user | Confused deputy nếu dùng service token cho việc user không được phép |

**Ví dụ 1 — Relay hợp lệ:** API A và B đều là Resource Servers trong cùng trust domain, Authorization Server phát token `aud=["api://relay-edge","api://profile-service"]`, scope thích hợp, cả hai validate độc lập. A có thể relay cho endpoint đã định trước, không cho user chọn B tùy ý.

**Ví dụ 2 — Phải trao đổi token:** Token inbound chỉ có `aud=api://relay-edge`. B yêu cầu `aud=api://profile-service`. Không được bỏ audience validation ở B để "làm cho relay chạy"; dùng Token Exchange / delegated authorization với token mới dành cho B (nếu IdP hỗ trợ).

**Ví dụ 3 — App-to-app:** A chạy job tổng hợp hệ thống không có user request. `ServerBearerExchangeFilterFunction` có thể không có user bearer credential. Dùng OAuth2 Client service manager cấp `client_credentials` cho A, rồi B phân quyền theo service principal/scopes.

### Bất biến của mô hình "on behalf of user"

Một token của Alice **không được** dùng cho Bob, kể cả hai request chạy cùng một instance. Tuyệt đối không đặt user token trong singleton field, static cache dùng chung, ThreadLocal không tương thích reactive, Redis key thiếu principal hoặc HTTP header mặc định của global WebClient. Token phải được lấy từ **đúng subscription/context của request hiện tại** và chỉ gửi đến upstream có quyền nhận.

## 5. Ranh giới tin cậy: destination quan trọng không kém token

### Tại sao WebClient chung nguy hiểm?

Cấu hình sau **không an toàn** nếu WebClient được tái sử dụng cho arbitrary URLs:

```java
// Anti-pattern: mọi URL được gọi qua client này có thể nhận bearer.
@Bean
WebClient generalPurposeClient() {
    return WebClient.builder()
            .filter(new ServerBearerExchangeFilterFunction())
            .build();
}
```

Ví dụ khác dễ gây rò:

```java
// Anti-pattern: người dùng điều khiển absolute outbound URL.
return generalPurposeClient.get()
        .uri(userProvidedUrl)
        .retrieve()
        .bodyToMono(String.class);
```

Nếu `userProvidedUrl` chỉ tới host attacker hoặc một metadata IP nội bộ, token có thể bị gửi qua mạng đến bên không tin cậy (SSRF và token exfiltration). Không sửa chỉ bằng việc kiểm tra chuỗi URL có chứa `example.test`; URL parser, DNS, redirect, IPv4/IPv6 literal, userinfo và encoding tạo nhiều đường lách.

**Giải pháp:** chỉ cấu hình một `WebClient` có Bearer relay cho **một upstream đã tin**, base URL từ config vận hành, đường dẫn cố định trong code, không gọi URI absolute theo user, disable redirect, kiểm soát egress mạng và TLS.

### Các điều kiện production cần có

1. `https://` với certificate/hostname verification, hoặc mTLS phù hợp service-to-service; tuyệt đối không dùng `trustAll` hoặc tắt TLS.
2. Hostname, scheme, port và path prefix của B nằm trong **allowlist tin cậy**; cấu hình từ deployment chứ không lấy trực tiếp từ request/cookie/header.
3. Egress restrictions ở cluster/service mesh/firewall chỉ cho phép A gọi đúng B; code check URI một mình không ngăn DNS rebinding/service discovery lạm dụng.
4. **Không tự theo redirect 30x** cho request mang Bearer token, nhất là redirect sang host/scheme khác. Phân biệt HTTP status 302 với lỗi nghiệp vụ.
5. Hai loại WebClient riêng: WebClient có token relay và WebClient public **không có** token relay.
6. Không log Authorization header, token string, URL query chứa token hoặc raw exception có credentials.
7. B tự introspect/verify token, kiểm tra audience của chính B và scope, rồi kiểm tra owner/tenant/resource.
8. Timeout, backpressure, hạn mức response body và cancellation được cấu hình; tránh retry vô hạn hoặc retry unsafe POST tự động.
9. Không tự echo downstream `WWW-Authenticate`/response headers nhạy cảm ra caller khi có thể lộ chi tiết token.
10. Kết quả của A không nên được public-cache nếu phụ thuộc danh tính; kiểm tra cache key, `Cache-Control` và privacy policy.

## 6. Reactor SecurityContext và quy tắc reactive

Trong WebFlux, Authentication thường được gắn vào **Reactor Context**, không phải ThreadLocal truyền thống.

```java
// Fragment đọc Authentication nếu cần kiểm tra policy bổ sung:
return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .flatMap(authentication -> validatePolicy(authentication));
```

Ở đây `validatePolicy(...)` là hàm ứng dụng cần tự định nghĩa, fragment không chạy độc lập.

**Cách đúng:** trả về toàn bộ `Mono` hoặc `Flux` từ controller/service, để Spring WebFlux subscribe và security context đi theo reactive pipeline.

```java
@GetMapping("/api/relay/profile")
public Mono<String> profile() {
    return service.profile();  // Reactor Context được giữ trong pipeline
}
```

**Cách sai:**

```java
// Anti-pattern: side effect không được compose, lỗi và context khó quản lý.
webClient.get().uri("/internal/profile")
        .retrieve().bodyToMono(String.class)
        .subscribe();
return Mono.just("done");
```

Không tự dùng `Thread.sleep`, `block()`, JDBC blocking call hoặc Runnable bên ngoài Reactor Context để "lấy token". Với job nền dùng machine token/client_credentials thay vì mượn token request bất kỳ.

### Filter gặp request đã có Authorization header

Theo Spring Security docs, nếu bạn chủ động cấu hình `headers.setBearerAuth(otherToken)` cho outbound call, bearer relay filter có thể để yên token mà bạn đã đặt. Điều này **không** biến token tự chọn thành an toàn. Nếu ứng dụng cần token khác, phải dùng OAuth2 Client/token exchange và kiểm soát client, audience/permissions rõ ràng.

---

## 7. Project thực hành Java 17+ / Spring Boot 3.5.16

Mục tiêu của demo:

- A là **WebFlux Opaque Resource Server**: nhận Bearer, gọi introspection server theo Spring Security.
- A xác nhận audience `api://relay-edge` và scope `profile.read`.
- A gọi B bằng **WebClient chuyên dụng** với `ServerBearerExchangeFilterFunction`. Upstream URL do server config quyết định và path cố định.
- A có một WebClient khác để gọi endpoint public B **mà không relay token**.
- A tắt follow redirects cho các WebClient, chủ động xử lý response non-2xx thành lỗi an toàn.
- Test dùng **MockWebServer** mô phỏng IdP và B, cùng một capture server để phát hiện token có bị đưa qua redirect không.
- Test sử dụng HTTP loopback và token giả; đây là **integration test flow**, không chứng minh HTTPS/cert và security policy của B production.

### 7.1. Cấu trúc

```text
opaque-relay-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/relayload/
        OpaqueRelayApplication.java
        SecurityConfiguration.java
        DownstreamWebClientConfiguration.java
        DownstreamRelayService.java
        RelayController.java
      resources/
        application.yml
    test/
      java/example/relayload/
        OpaqueRelayIntegrationTest.java
```

Package được đặt là `example.relayload` trong **tất cả file**. Không đổi package hoặc tên class lẻ tẻ khi copy.

### 7.2. Gradle

**`settings.gradle`**

```groovy
rootProject.name = 'opaque-relay-lab'
```

**`build.gradle`**

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
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot WebFlux starter tích hợp Reactor Netty và `WebClient`. Starter Resource Server kéo các thành phần Bearer/opaque introspection. `MockWebServer` là test dependency; không deploy nó cùng app.

Cần JDK 17+, Gradle Wrapper tương thích hoặc Gradle có sẵn. Nếu project dùng BOM do tổ chức quản lý, hãy chọn phiên bản patch mới được hỗ trợ thay vì giữ nguyên baseline cũ của bài học.

### 7.3. application.yml

**`src/main/resources/application.yml`**

```yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: opaque-relay-lab
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI:https://idp.example.invalid/oauth2/introspect}
          client-id: ${INTROSPECTION_CLIENT_ID:relay-resource-server}
          client-secret: ${INTROSPECTION_CLIENT_SECRET:local-demo-only}

downstream:
  profile-base-url: ${PROFILE_BASE_URL:https://profile.example.invalid}
  allow-insecure-loopback-for-tests: false
```

Giải thích:

- API A chỉ bind loopback trong **mô hình học một máy**. Production qua container/network policy cần cấu hình listener riêng, không vô tình public backend.
- `opaquetoken.introspection-uri` là endpoint RFC 7662, không phải OAuth2 token endpoint.
- Client ID/secret dùng để A xác thực với introspection endpoint; **không** là Bearer token của user, không ghi credential thật vào Git.
- `profile-base-url` là **cấu hình tin cậy của server**, không lấy từ query parameter.
- `allow-insecure-loopback-for-tests: false` ở mặc định; integration tests ghi đè thành true chỉ để dùng MockWebServer HTTP tại `127.0.0.1`. Không cho phép HTTP gửi token ra Internet.
- Địa chỉ `.invalid` là tài liệu giả; `bootRun` không thể truy cập endpoint thật khi chưa cấu hình IdP/upstream phù hợp.

### 7.4. Main class

**`src/main/java/example/relayload/OpaqueRelayApplication.java`**

```java
package example.relayload;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OpaqueRelayApplication {
    public static void main(String[] args) {
        SpringApplication.run(OpaqueRelayApplication.class, args);
    }
}
```

### 7.5. Resource Server Security: kiểm tra audience và scope

**`src/main/java/example/relayload/SecurityConfiguration.java`**

```java
package example.relayload;

import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    private static final String EDGE_AUDIENCE = "api://relay-edge";

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
                    String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
                    String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
                    String clientSecret) {

        ReactiveOpaqueTokenIntrospector delegate =
                SpringReactiveOpaqueTokenIntrospector
                        .withIntrospectionUri(uri)
                        .clientId(clientId)
                        .clientSecret(clientSecret)
                        .build();

        return token -> delegate.introspect(token)
                .flatMap(principal -> {
                    Object aud = principal.getAttribute("aud");
                    if (!hasAudience(aud, EDGE_AUDIENCE)) {
                        return Mono.error(new OAuth2AuthenticationException(
                                new OAuth2Error("invalid_token",
                                        "Token not issued for relay edge", null)));
                    }
                    return Mono.just(principal);
                });
    }

    private static boolean hasAudience(Object aud, String expected) {
        if (aud instanceof String value) {
            return expected.equals(value);
        }
        if (aud instanceof Collection<?> values) {
            return values.contains(expected);
        }
        return false;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET,
                                "/api/public/ping",
                                "/api/public/downstream-check")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/relay/**")
                            .hasAuthority("SCOPE_profile.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(resource -> resource
                        .opaqueToken(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là Spring Security **reactive**, không dùng `HttpSecurity` hay Servlet `OpaqueTokenIntrospector`.

**Vì sao cần audience check?** Spring OAuth2 opaque introspection mặc định xác minh `active` và tạo scope authorities; không nên mặc định nó luôn kiểm tra audience riêng của ứng dụng. Decorator trên chỉ cho token có `aud` chứa `api://relay-edge` được vào A. Token không active bị delegate từ chối **trước** callback mapper.

**Vì sao có scope rule?** Một token active, audience đúng nhưng chỉ có `scope=profile.write` vẫn bị HTTP 403 tại A nếu gọi `/api/relay/profile`. Điều này tránh gửi token không có quyền đọc tới B chỉ để B từ chối.

**Chú ý:** B vẫn phải kiểm tra audience **của B**. Đoạn trên chỉ chứng minh A kiểm tra audience của A.

### 7.6. Tách WebClient có token và WebClient public

**`src/main/java/example/relayload/DownstreamWebClientConfiguration.java`**

```java
package example.relayload;

import java.net.URI;
import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.server.resource.web.reactive
        .function.client.ServerBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class DownstreamWebClientConfiguration {

    private static URI validatedBase(
            String raw, boolean allowInsecureLoopbackForTests) {

        URI uri = URI.create(raw);

        boolean https = "https".equalsIgnoreCase(uri.getScheme());
        boolean localTest = allowInsecureLoopbackForTests
                && "http".equalsIgnoreCase(uri.getScheme())
                && "127.0.0.1".equals(uri.getHost());

        if (!(https || localTest)
                || uri.getHost() == null
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getRawPath() != null
                    && !uri.getRawPath().isEmpty()
                    && !"/".equals(uri.getRawPath()))) {
            throw new IllegalArgumentException(
                    "Profile upstream base URL is not allowed");
        }
        return uri;
    }

    private static ReactorClientHttpConnector connector() {
        HttpClient client = HttpClient.create()
                .followRedirect(false)
                .responseTimeout(Duration.ofSeconds(5));

        return new ReactorClientHttpConnector(client);
    }

    @Bean("profileRelayWebClient")
    WebClient profileRelayWebClient(
            @Value("${downstream.profile-base-url}") String rawBaseUrl,
            @Value("${downstream.allow-insecure-loopback-for-tests:false}")
                    boolean allowTestHttp) {

        URI base = validatedBase(rawBaseUrl, allowTestHttp);

        // WebClient này CHỈ dùng cho profile service đáng tin cậy.
        return WebClient.builder()
                .baseUrl(base.toString())
                .clientConnector(connector())
                .filter(new ServerBearerExchangeFilterFunction())
                .build();
    }

    @Bean("publicWebClient")
    WebClient publicWebClient(
            @Value("${downstream.profile-base-url}") String rawBaseUrl,
            @Value("${downstream.allow-insecure-loopback-for-tests:false}")
                    boolean allowTestHttp) {

        URI base = validatedBase(rawBaseUrl, allowTestHttp);

        // Không có ServerBearerExchangeFilterFunction ở client này.
        return WebClient.builder()
                .baseUrl(base.toString())
                .clientConnector(connector())
                .build();
    }
}
```

**Những điểm cần đánh giá:**

- `profile-base-url` là **ops-owned configuration**. Hàm `validatedBase` kiểm tra scheme, userinfo, query, fragment và yêu cầu base URL ở gốc host; test-only HTTP chỉ cho loopback và phải bật cờ rõ ràng.
- `followRedirect(false)` là biện pháp phòng vệ: một response `302 Location: ...` không được tự động chuyển tiếp credential sang một host khác.
- `responseTimeout(5s)` giới hạn thời gian chờ response. Production còn cần connect timeout, DNS policy, backpressure, giới hạn body và retry rõ ràng.
- WebClient dùng `baseUrl` **không có nghĩa bản thân nó ngăn absolute `.uri(...)`**. Vì vậy service bên dưới chỉ gọi **path hằng số cố định**. Không expose WebClient này qua endpoint nhận arbitrary URL.
- Một Host URL hợp lệ lúc khởi động không ngăn DNS rebinding hoặc proxy network bị cấu hình sai. **Cần egress firewall/service mesh allowlist**, workload identity và TLS/mTLS.
- `publicWebClient` không có Bearer filter và được dùng cho request public. Không vô tình dùng `profileRelayWebClient` để gọi các API analytics, image fetch, webhook hoặc bên thứ ba.
- Production có thể dùng một WebClient chuyên theo profile-service và thêm certificate pinning/mTLS theo infrastructure, nhưng không tắt TLS hostname validation để xử lý lỗi handshake.
- Hai beans được khai báo tên riêng để tránh inject nhầm.

### 7.7. Service gọi downstream với path cố định, không tự follow redirect

**`src/main/java/example/relayload/DownstreamRelayService.java`**

```java
package example.relayload;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@Service
public class DownstreamRelayService {

    private final WebClient relayClient;
    private final WebClient publicClient;

    public DownstreamRelayService(
            @Qualifier("profileRelayWebClient") WebClient relayClient,
            @Qualifier("publicWebClient") WebClient publicClient) {
        this.relayClient = relayClient;
        this.publicClient = publicClient;
    }

    public Mono<String> profile() {
        return fetch(relayClient, "/internal/profile");
    }

    public Mono<String> denied() {
        return fetch(relayClient, "/internal/denied");
    }

    public Mono<String> redirectProbe() {
        return fetch(relayClient, "/internal/redirect");
    }

    public Mono<String> publicCheck() {
        return fetch(publicClient, "/public/check");
    }

    private Mono<String> fetch(WebClient client, String fixedPath) {
        // fixedPath chỉ do code ở trên quyết định, KHÔNG từ HTTP query.
        return client.get().uri(fixedPath)
                .exchangeToMono(this::handleResponse)
                .onErrorMap(WebClientRequestException.class,
                        error -> new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Downstream unavailable"));
    }

    private Mono<String> handleResponse(ClientResponse response) {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class)
                    .switchIfEmpty(Mono.error(
                            new ResponseStatusException(
                                    HttpStatus.BAD_GATEWAY,
                                    "Empty downstream response")));
        }

        // Bao gồm 301/302/307/308, 401/403 và 5xx của B.
        // Không tự follow Location hoặc trả body lỗi nhạy cảm của B.
        return response.releaseBody()
                .then(Mono.error(new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "Downstream rejected request")));
    }
}
```

**Tại sao code trên chọn `502 Bad Gateway` cho lỗi downstream?** Đây là chính sách đơn giản cho demo: A không chuyển nguyên body/headers về caller, nhất là token-related diagnostics từ B. Production có thể quyết định map downstream 401/403 thành 401/403 cho client, hoặc một error code nghiệp vụ khác, **nhưng phải thiết kế rõ** để không tạo vòng lặp đăng nhập/retry và không leak credentials.

- `response.releaseBody()` giúp giải phóng body cho response không được dùng.
- Không dùng `retry()` vô hạn, nhất là với POST/side effects.
- Không tự lấy raw HTTP Authorization của inbound request rồi gọi `setBearerAuth(...)`, vì điều đó có thể xảy ra **trước** khi token được introspect.
- Không trả `Mono.just("OK")` trước khi WebClient hoàn tất.
- Khi downstream đổi endpoint hoặc policy, sửa config/code review, không lấy URL từ người dùng để "linh hoạt".

### 7.8. Controller

**`src/main/java/example/relayload/RelayController.java`**

```java
package example.relayload;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class RelayController {

    private final DownstreamRelayService downstream;

    public RelayController(DownstreamRelayService downstream) {
        this.downstream = downstream;
    }

    @GetMapping("/api/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/public/downstream-check")
    public Mono<String> publicDownstreamCheck() {
        return downstream.publicCheck();
    }

    @GetMapping("/api/relay/profile")
    public Mono<String> profile() {
        return downstream.profile();
    }

    @GetMapping("/api/relay/denied")
    public Mono<String> denied() {
        return downstream.denied();
    }

    @GetMapping("/api/relay/redirect")
    public Mono<String> redirectProbe() {
        return downstream.redirectProbe();
    }
}
```

Controller chỉ trả kết quả đã được dịch vụ B cung cấp hoặc lỗi an toàn, **không bao giờ trả raw Bearer token**. Spring Security xử lý `SCOPE_profile.read` trước khi cho vào `/api/relay/**`. Không có endpoint cho caller chỉ định `uri=...` hoặc `host=...`.

---

## 8. Integration test WebTestClient và MockWebServer

Test chạy **embedded Reactor Netty trên cổng ngẫu nhiên** và ba MockWebServers:

- `IDP`: mô phỏng introspection endpoint, yêu cầu Basic của Resource Server A, trả active/scope/audience.
- `PROFILE`: mô phỏng downstream B, kiểm tra header Bearer khi nhận `GET /internal/profile`; đây **không phải Resource Server B đầy đủ**, vì không tự introspect theo RFC 7662.
- `CAPTURE`: mock host khác để phát hiện nếu WebClient đi theo redirect sang destination khác.

Mọi token, Basic credentials và endpoint HTTP đều chỉ dùng **loopback trong test**. Không sao chép HTTP introspection hay secrets giả vào production.

### 8.1. Bộ test đầy đủ

**`src/test/java/example/relayload/OpaqueRelayIntegrationTest.java`**

```java
package example.relayload;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.Base64;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.server.ResponseStatusException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpaqueRelayIntegrationTest {

    private static final String BASIC = "Basic " +
            Base64.getEncoder().encodeToString(
                    "relay-resource-server:test-secret"
                            .getBytes(StandardCharsets.UTF_8));

    private static final MockWebServer CAPTURE = startCapture();
    private static final MockWebServer PROFILE = startProfile();
    private static final MockWebServer IDP = startIdp();

    @DynamicPropertySource
    static void configureEndpoints(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri",
                () -> IDP.url("/introspect").toString());
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-id",
                () -> "relay-resource-server");
        registry.add(
                "spring.security.oauth2.resourceserver.opaquetoken.client-secret",
                () -> "test-secret");
        registry.add("downstream.profile-base-url",
                () -> PROFILE.url("/").toString());
        registry.add("downstream.allow-insecure-loopback-for-tests",
                () -> "true");
    }

    @LocalServerPort
    int port;

    @Autowired
    DownstreamRelayService service;

    private WebTestClient client;

    @BeforeEach
    void prepare() throws InterruptedException {
        client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        // Dọn recorded requests từ test trước; tests chạy tuần tự.
        while (PROFILE.takeRequest(0, TimeUnit.MILLISECONDS) != null) {
            // drain
        }
    }

    @AfterAll
    static void shutdown() throws IOException {
        IDP.shutdown();
        PROFILE.shutdown();
        CAPTURE.shutdown();
    }

    private static MockWebServer startCapture() {
        MockWebServer server = new MockWebServer();
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startProfile() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                String path = request.getPath();
                if ("/internal/profile".equals(path)) {
                    if ("Bearer reader-token".equals(
                            request.getHeader("Authorization"))) {
                        return new MockResponse()
                                .setResponseCode(200)
                                .setBody("profile-for-alice");
                    }
                    return new MockResponse()
                            .setResponseCode(401)
                            .setBody("downstream-invalid-token");
                }

                if ("/internal/denied".equals(path)) {
                    return new MockResponse()
                            .setResponseCode(401)
                            .setBody("private-upstream-diagnostic");
                }

                if ("/internal/redirect".equals(path)) {
                    return new MockResponse()
                            .setResponseCode(302)
                            .setHeader("Location",
                                    CAPTURE.url("/capture").toString());
                }

                if ("/public/check".equals(path)) {
                    boolean noAuthorization =
                            request.getHeader("Authorization") == null;
                    return new MockResponse()
                            .setResponseCode(200)
                            .setBody(noAuthorization
                                    ? "no-token-received"
                                    : "unexpected-token");
                }

                return new MockResponse().setResponseCode(404);
            }
        });
        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static MockWebServer startIdp() {
        MockWebServer server = new MockWebServer();
        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if (!"POST".equals(request.getMethod())
                        || !"/introspect".equals(request.getPath())) {
                    return new MockResponse().setResponseCode(404);
                }
                if (!BASIC.equals(request.getHeader("Authorization"))) {
                    return new MockResponse().setResponseCode(401);
                }

                String body = request.getBody().readUtf8();
                String token = Arrays.stream(body.split("&"))
                        .filter(v -> v.startsWith("token="))
                        .map(v -> URLDecoder.decode(
                                v.substring(6), StandardCharsets.UTF_8))
                        .findFirst().orElse("");

                return new MockResponse()
                        .setResponseCode(200)
                        .setHeader("Content-Type", "application/json")
                        .setBody(introspectionResult(token));
            }
        });

        try {
            server.start();
            return server;
        } catch (IOException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String introspectionResult(String token) {
        return switch (token) {
            case "reader-token" -> """
                {
                  "active": true,
                  "sub": "alice",
                  "scope": "profile.read",
                  "aud": ["api://relay-edge", "api://profile-service"]
                }
                """;
            case "no-scope-token" -> """
                {
                  "active": true,
                  "sub": "bob",
                  "scope": "profile.write",
                  "aud": ["api://relay-edge", "api://profile-service"]
                }
                """;
            case "wrong-audience-token" -> """
                {
                  "active": true,
                  "sub": "mallory",
                  "scope": "profile.read",
                  "aud": "api://unrelated"
                }
                """;
            default -> """
                {"active":false}
                """;
        };
    }

    @Test
    void pingIsPublic() {
        client.get().uri("/api/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void noBearerToProtectedRouteIs401() {
        client.get().uri("/api/relay/profile")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void inactiveTokenIs401() {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("inactive-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void tokenForWrongAudienceIs401() {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("wrong-audience-token"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validTokenWithoutRequiredScopeIs403() {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("no-scope-token"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void goodBearerIsRelayedToFixedDownstream() throws InterruptedException {
        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("profile-for-alice");

        RecordedRequest request = PROFILE.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("/internal/profile", request.getPath());
        assertEquals("Bearer reader-token",
                request.getHeader("Authorization"));
    }

    @Test
    void publicWebClientNeverRelaysEvenIfCallerIsAuthenticated()
            throws InterruptedException {
        client.get().uri("/api/public/downstream-check")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("no-token-received");

        RecordedRequest request = PROFILE.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("/public/check", request.getPath());
        assertNull(request.getHeader("Authorization"));
    }

    @Test
    void downstream401BecomesSafeGatewayError() {
        client.get().uri("/api/relay/denied")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isEqualTo(502);
    }

    @Test
    void redirectToDifferentHostIsNotFollowed() {
        int before = CAPTURE.getRequestCount();

        client.get().uri("/api/relay/redirect")
                .headers(h -> h.setBearerAuth("reader-token"))
                .exchange()
                .expectStatus().isEqualTo(502);

        // Nếu HTTP client tự follow redirect, CAPTURE sẽ tăng count.
        assertEquals(before, CAPTURE.getRequestCount());
    }

    @Test
    void rejectedScopeDoesNotCallDownstream() {
        int before = PROFILE.getRequestCount();

        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("no-scope-token"))
                .exchange()
                .expectStatus().isForbidden();

        assertEquals(before, PROFILE.getRequestCount());
    }

    @Test
    void invalidAudienceDoesNotCallDownstream() {
        int before = PROFILE.getRequestCount();

        client.get().uri("/api/relay/profile")
                .headers(h -> h.setBearerAuth("wrong-audience-token"))
                .exchange()
                .expectStatus().isUnauthorized();

        assertEquals(before, PROFILE.getRequestCount());
    }

    @Test
    void outsideRequestContextNoUserBearerIsInvented()
            throws InterruptedException {
        StepVerifier.create(service.profile())
                .expectError(ResponseStatusException.class)
                .verify();

        RecordedRequest request = PROFILE.takeRequest(
                2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertNull(request.getHeader("Authorization"));
    }
}
```

### 8.2. Chạy tests

Với Gradle Wrapper có trong project:

```bash
./gradlew test --tests example.relayload.OpaqueRelayIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.relayload.OpaqueRelayIntegrationTest
```

Hoặc dùng Gradle được cài đặt tương thích:

```bash
gradle test --tests example.relayload.OpaqueRelayIntegrationTest
```

**Kết quả kỳ vọng:** 12 tests PASS nếu project, JDK 17+, dependencies và khả năng bind loopback đúng như mô tả. Đây là **dự đoán dựa trên source**, không phải log chạy tests đã thực hiện trong một workspace thực tế.

### 8.3. Kết quả nào đã được kiểm tra trong project?

| Test | Điều được kiểm chứng |
| --- | --- |
| `pingIsPublic` | Endpoint public không cần Bearer |
| `noBearerToProtectedRouteIs401` | Không có Authentication không được vào relay |
| `inactiveTokenIs401` | Introspection từ chối token không active |
| `tokenForWrongAudienceIs401` | Audience của A phải đúng |
| `validTokenWithoutRequiredScopeIs403` | Scope required phải đạt trước outbound call |
| `goodBearerIsRelayedToFixedDownstream` | B nhận đúng `Authorization: Bearer reader-token` tại path cố định |
| `publicWebClientNeverRelaysEvenIfCallerIsAuthenticated` | WebClient public không có token relay |
| `downstream401BecomesSafeGatewayError` | A không echo body/WWW-Authenticate của B |
| `redirectToDifferentHostIsNotFollowed` | Outbound client từ chối việc follow redirect |
| `rejectedScopeDoesNotCallDownstream` | Authorization fail tại A không gọi B |
| `invalidAudienceDoesNotCallDownstream` | Token sai audience không chạm B |
| `outsideRequestContextNoUserBearerIsInvented` | Không có Reactor authentication thì filter không bịa Bearer token |

**Giới hạn:** B mock chỉ so sánh header theo chuỗi test, không tự gọi IdP để verify active/scope/audience. Integration test này chứng minh **A introspects, A authorizes, A relays và policy không leak trong hai WebClients**; nó chưa chứng minh Resource Server B production đã validate đúng. Muốn kiểm chứng toàn hệ thống, triển khai B riêng với JWT/opaque Resource Server config và chạy cross-service tests dưới TLS thật.

### 8.4. Cẩn thận với bộ đếm và test song song

Các MockWebServer dùng static fields, `@AfterAll` đóng server. `@BeforeEach` dọn queue các requests đã ghi ở PROFILE. Bộ test được viết cho **chạy tuần tự theo mặc định JUnit**; nếu CI bật test parallel, phải cô lập MockWebServer/app context cho từng test hoặc đồng bộ hóa phép đo `getRequestCount`, tránh race. Không chạy bộ test ở production network.

---

## 9. Những thao tác không được dùng cho token relay

### 9.1. Copy raw Authorization header ngay lúc nhận request

```java
// Anti-pattern: có thể chuyển tiếp credential trước khi đã xác thực.
String inboundAuthorization =
        exchange.getRequest().getHeaders().getFirst("Authorization");

return webClient.get().uri(userProvidedUrl)
        .header("Authorization", inboundAuthorization)
        .retrieve().bodyToMono(String.class);
```

Nhược điểm:

- Dễ thực thi khi authentication chưa thành công hoặc endpoint permitAll.
- Không có audience/scope/ownership policy cho B.
- `userProvidedUrl` mở SSRF và token exfiltration.
- Thường dễ bị log raw header khi debug.
- Nếu có redirect/host mismatch, credential có thể đi đến sai dịch vụ.

**Ưu tiên** `ServerBearerExchangeFilterFunction` sau Spring Security authentication, trên WebClient outbound chuyên dụng với path cố định.

### 9.2. Dùng ThreadLocal SecurityContextHolder trong WebFlux

```java
// Anti-pattern trong reactive controller/service:
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Reactor có thể chuyển scheduling giữa threads. `SecurityContextHolder` ThreadLocal kiểu truyền thống không là nguồn tin cậy để tìm Authentication theo reactive subscription. Dùng `ReactiveSecurityContextHolder` hoặc filter chính thức.

### 9.3. Lưu token vào singleton mutable field

```java
// Anti-pattern: concurrent requests của Alice và Bob có thể lẫn token.
private String lastBearer;

void setBearer(String value) {
    this.lastBearer = value;
}
```

Không lưu raw token user ở static field, shared WebClient default Authorization header hoặc cache không phân vùng principal. Trong reactive app có concurrent requests, token cross-user leak có thể trở thành nghiêm trọng.

### 9.4. Dùng OAuth2 Client filter thay thế relay mà không phân biệt grant

`ServerOAuth2AuthorizedClientExchangeFilterFunction` gọi manager để lấy/refresh **authorized client** theo registration và principal. Nó không phải chỉ copy inbound `Authorization`.

Nếu API A cần tự xin client_credentials cho job, chọn OAuth2 Client. Nếu B cần token riêng theo audience của B, xem RFC 8693 Token Exchange. Không dùng manager với một client registration tùy chọn từ HTTP input rồi vô tình lấy token service-level có quyền rộng hơn caller.

### 9.5. Bỏ kiểm tra audience ở B

Không được coi việc A đã xác thực token là lý do B bỏ introspection/issuer/audience validation. A và B là **hai trust boundaries**; hệ thống downstream không nên nhận bất cứ token nào chỉ vì request đến từ IP nội bộ. Với zero-trust/microservices, dùng workload identity/mTLS để xác thực service A, và Bearer token/scope để xác thực danh tính/cấp quyền tương ứng.

### 9.6. Dùng CORS như một công cụ phân quyền server-to-server

CORS là chính sách browser về cross-origin JavaScript; WebClient, cURL và máy chủ khác không bị CORS chặn theo cơ chế browser. Một upstream không được bảo vệ chỉ bằng `Access-Control-Allow-Origin`. Authentication/authorization và trusted network policies mới là lớp kiểm soát thực.

---

## 10. Làm thế nào ngăn rò Bearer token qua redirect?

Giả sử một downstream trả:

```http
HTTP/1.1 302 Found
Location: https://some-other.example.invalid/collect
```

Nếu HTTP client tự theo redirect, có thể có nguy cơ gửi credential tới host khác tùy chính sách redirect của implementation. **Không dựa vào giả định** rằng thư viện luôn loại Authorization header khi host đổi. Hãy cấu hình rõ `followRedirect(false)` và từ chối mọi 3xx trong service outbound có token như demo.

Khi thực sự cần chuyển host, client nên:

1. Kiểm tra destination mới qua policy allowlist do server sở hữu, không nhận trực tiếp từ upstream không tin.
2. Thực hiện một **request mới** với token có audience/scope dành cho destination đó, không mặc định giữ token cũ.
3. Không chuyển Authorization/cookie/header nhạy cảm từ B sang C nếu C không có quyền nhận.
4. Kiểm tra HTTPS, certificate hostname, egress network, DNS resolution và response size/timeout.
5. Audit đường đi của token mà không log token value.

**WebClient.baseUrl(...) một mình không giới hạn destination.** Một absolute URI truyền vào `.uri(...)` có thể override base URL. Vì vậy code review phải bao gồm **tất cả lệnh gọi** `profileRelayWebClient` và không expose arbitrary URI/path mapping ra public API.

### HTTPS chưa đủ nếu destination không đáng tin

TLS bảo vệ **đường truyền tới đích mà client đã chọn**. Nếu đích là attacker-controlled domain và có certificate hợp lệ, TLS vẫn vận chuyển Bearer token một cách an toàn **đến attacker**. Do đó phải kiểm soát **ai là đích được phép**, không chỉ kiểm tra URL bắt đầu bằng https://.

---

## 11. Retry, timeout, cancellation và backpressure

### Timeout

HTTP introspection (A → IdP) và outbound call (A → B) đều có độ trễ. Nếu không có timeout, request có thể treo và cạn connection pool trong khi tài nguyên/tokens vẫn còn được giữ trong pipeline.

Trong demo, `responseTimeout(Duration.ofSeconds(5))` giới hạn thời gian chờ response của Netty. Production còn cần connect timeout, DNS resolution policy, pool timeout, deadlines end-to-end và metrics. Mỗi timeout nên dẫn đến lỗi an toàn, không fallback `permitAll()`.

### Retry

Không dùng:

```java
// Anti-pattern: có thể spam request và không giới hạn lỗi.
return service.profile().retry();
```

Nếu retry cần thiết:

- Chỉ retry lỗi mạng/5xx transient theo danh sách cụ thể.
- Áp backoff, jitter và số lần thử tối đa.
- Không retry 401/403 vô hạn khi B không chấp nhận token: token relay không thể refresh credential.
- Với POST/PUT gây side effects, cần idempotency key và thiết kế retry rõ.
- Đảm bảo tracing không ghi token, và cả request mới vẫn giữ đúng security context/authorization.

### Cancellation và reactive chain

Khi client hủy request, downstream subscription nên được cancel theo Reactor chain. Không tự `subscribe()` vào một WebClient request tách khỏi lifecycle rồi để nó tiếp tục gửi token sau khi upstream HTTP response đã kết thúc. Tách các thao tác background ra job có service credentials phù hợp thay vì giữ user token.

### Response body và error sanitization

Trong demo, lỗi B được chuyển thành một `ResponseStatusException(502, ...)` chung và body lỗi bị release, không được echo. Production cần giới hạn kích thước response, tránh response-based injection và xác minh content type/schema trước khi trả dữ liệu cho client. Nếu B chứa thông tin PII, API A vẫn phải có authorization theo dữ liệu.

---

## 12. Xây dựng ranh giới tin cậy cho kiến trúc nhiều dịch vụ

### Mô hình đơn giản

```text
Browser
  |
  | Token audience dành cho A và B
  v
Edge API A --mTLS/HTTPS + delegated Bearer--> Profile B
     |
     +-- riêng: introspection endpoint IdP (HTTPS, Basic client auth)
```

Đặt chính sách:

- **Client → A:** Token active, audience của A, required scope, rate limit.
- **A → IdP:** Chỉ HTTPS introspection URI từ trusted config; bảo vệ secret; validate response.
- **A → B:** Chỉ allowlisted hostname/path, TLS/mTLS, không follow redirect, không log token.
- **B:** Introspection/verification độc lập, audience của B, scope/ownership/tenant.
- **B → DB:** Row-level authorization theo principal/tenant/resource. Không chỉ xem `sub` là một string tin cậy nếu chưa được verify.

### Multi-hop A → B → C

Không tự coi một access token nhiều-hop là bearer có thể chuyển không giới hạn. Càng nhiều dịch vụ giữ token, rủi ro leak càng tăng. Nếu C là trust domain khác, ưu tiên token exchange hoặc workload token riêng có scope/audience ngắn. Theo dõi **delegation chain** và tránh confused deputy.

### Multi-tenant

Token của Alice ở tenant A không được dùng truy cập dữ liệu tenant B. Cần tránh:

- Dùng client_registration_id chung để lưu token user trong shared cache không có subject/tenant key.
- Chuyển tiếp token user giữa các tenant chỉ vì scope giống nhau.
- Dựa vào `X-Tenant-ID` client tự gửi thay cho identity/tenant được IdP xác nhận.
- Cho WebClient redirect hoặc resolve host dựa trên tenant name chưa validate.

Khi tenant có endpoint riêng, dùng một server-side mapping allowlisted tenant → endpoint, không xây URL từ raw tenant id hoặc hostname nhận trực tiếp.

---

## 13. 401, 403, 502: chẩn đoán đúng tầng

| Trường hợp | A xác thực? | A gọi B? | HTTP thường thấy |
| --- | --- | --- | --- |
| Không Bearer | Chưa có | Không | 401 tại A |
| Token inactive/invalid | Không | Không | 401 tại A |
| Token sai audience A | Không | Không | 401 tại A |
| Token active đúng audience nhưng thiếu scope ở A | Có | Không | 403 tại A |
| Token active, audience+scope A đúng, B chấp nhận | Có | Có | 200 |
| Token đúng tại A nhưng B từ chối vì audience/scope B | Có | Có | Tùy mapping A (demo 502) |
| B trả 302 tới host ngoài | Có | Có (không follow) | 502 trong demo |
| IdP introspection timeout/outage | Không có kết quả xác minh | Không | Không cấp dữ liệu; status phụ thuộc xử lý lỗi |
| B timeout/unreachable | Có | Đã thử | 502/504 hoặc lỗi được map an toàn |

Một 403 tại A và 403 tại B là hai tình huống khác nhau. Trong demo, B trả 401 được dịch thành 502 ở A để không leak raw downstream body và challenge headers; hệ thống thật có thể chọn lỗi nghiệp vụ cụ thể nhưng cần nêu rõ contract và observability.

### Cách debug

1. Kiểm tra A trả 401 trước hay sau introspection (không log token).
2. Kiểm tra A có đúng `SCOPE_profile.read` và audience `api://relay-edge` không.
3. Đối chiếu B có được phép nhận token này không; B có audience `api://profile-service` và scope phù hợp không.
4. Kiểm tra outbound domain, scheme, path, DNS và upstream certificate. Không để user điều khiển URL.
5. Xem trace/correlation ID giữa A–IdP–B, tránh sao chép Authorization header vào trace baggage.
6. Với 302, xem `Location` như dữ liệu không đáng tin, không tự follow bằng Bearer client.
7. Nếu B 401 do token hết hạn, relay filter **không tự refresh**; thiết kế reauthentication hoặc token exchange/client flow phù hợp.
8. Nếu B 403 do insufficient_scope, không nới policy hoặc dùng service token rộng quyền để "sửa".
9. Kiểm tra retry/concurrency/cache, không gửi user bearer ngoài lifecycle.
10. Reproduce bằng WebTestClient với MockWebServer, rồi staging TLS thật.

---

## 14. Checklist production và câu hỏi kiểm tra

### Checklist bảo mật

1. Endpoint protected ở A có `SecurityWebFilterChain` reactive và opaque introspection chuẩn.
2. Introspection endpoint HTTPS đáng tin, client-id/secret từ secret manager, không fail open.
3. Audience A được validate; required scope được áp trước outbound.
4. B phải xác thực token độc lập và validate audience/scope/owner/tenant của B.
5. Token relay chỉ khi IdP có policy cho phép B nhận cùng token; nếu không, dùng token exchange/credentials thích hợp.
6. Bearer relay filter chỉ nằm trên WebClient **chuyên cho B**, không trên global/general-purpose WebClient.
7. URL B được lấy từ server-owned allowlist/config, path cố định; không nhận arbitrary outbound URL từ user.
8. Redirect tự động bị tắt, 3xx không được theo tới destination không tin.
9. HTTPS/mTLS, hostname/certificate verification, DNS/egress restriction và network policy đã được kiểm tra.
10. Không log Bearer, client secret, raw introspection response có thông tin nhạy cảm hoặc Authorization header.
11. Không lưu user token trong static/singleton fields hoặc ThreadLocal không reactive; không làm mất Reactor SecurityContext.
12. Cấu hình timeout, retry giới hạn, circuit breaker/backpressure và observability.
13. 401/403/502 được phân biệt, không echo nguyên error response/header từ B.
14. Không cache kết quả theo URL mà bỏ qua user/tenant, và không public-cache PII.
15. Kiểm thử âm tính: inactive, wrong aud, missing scope, wrong host, redirect, no context, upstream 401, network error, token leakage.
16. Kiểm tra security dependency versions và vá các CVE trước production; Spring Boot 3.5 không còn OSS support.
17. Với multi-tenant, kiểm tra tenant/owner ở dữ liệu B, không chỉ scope toàn cục.
18. Có threat model và runbook rõ cho token exchange, revocation và trust boundary khi bổ sung dịch vụ mới.

### Bài tập

1. Giải thích `ServerBearerExchangeFilterFunction` lấy token từ đâu khi WebFlux controller trả một `Mono`.
2. Vì sao cùng một opaque token được A introspect thành công vẫn có thể bị B trả 401?
3. So sánh relay, `client_credentials` và RFC 8693 Token Exchange về audience và quyền user.
4. Bỏ `.filter(new ServerBearerExchangeFilterFunction())` khỏi relay client rồi chạy test; quan sát B không nhận token.
5. Đưa filter relay vào public client rồi chạy test; vì sao test chống leak phải thất bại?
6. Bật `followRedirect(true)` chỉ trong **môi trường test có MockWebServer**, không gửi token thật; đánh giá khả năng gọi CAPTURE và hành vi header khi chuyển host. Khôi phục `false` sau khi hoàn tất.
7. Thử `no-scope-token` và quan sát A trả 403 **trước** khi có HTTP tới B.
8. Thử token active nhưng aud sai, xác định đoạn introspector trả 401.
9. Viết integration test cho B thật để kiểm tra audience B và scope mà test MockWebServer hiện chưa chứng minh.
10. Thay `PROFILE_BASE_URL` bằng URL HTTP ngoài localhost: ứng dụng phải từ chối cấu hình như thế nào?
11. Cho phép một query parameter user kiểm soát **dữ liệu tìm kiếm** chứ không phải host/path. Hãy viết validation để vẫn không mở absolute URI hoặc path traversal.
12. Thêm một phương án Token Exchange nếu IdP hỗ trợ, bảo đảm token mới chỉ có `aud=api://profile-service`.
13. So sánh Reactor Context với ThreadLocal SecurityContext; vì sao tự `subscribe()` có thể làm mất request lifecycle?
14. Tạo chính sách response error 502, correlation ID và log masking khi B trả 401/403.
15. Đánh giá nguy cơ khi cùng một Bearer được relay qua A→B→C, tìm ranh giới nên dừng relay.
16. Đặt policy caching kết quả profile theo subject/tenant, tránh trả dữ liệu Alice cho Bob.
17. Dùng mTLS kết hợp Bearer ở B và giải thích vì sao mTLS chỉ chứng minh A là caller service, chưa thay authorization của Alice.
18. Thiết kế test cho WebClient public không gửi token kể cả khi caller đã authenticated.

## Tổng kết

Trong **Spring Security reactive Resource Server Opaque**, trước tiên A dùng `ReactiveOpaqueTokenIntrospector` để kiểm chứng Bearer token và tạo `Authentication` trong Reactor Context. `ServerBearerExchangeFilterFunction` có thể dùng credential OAuth2 đã xác thực ấy để gắn `Authorization: Bearer ...` vào request `WebClient` đi tới downstream.

**Điểm cốt lõi không phải việc thêm header, mà là quyền chuyển token qua một ranh giới tin cậy:** token phải có audience/scope dành cho B, WebClient chỉ được gọi upstream được allowlist, HTTPS/mTLS/egress được bảo vệ, không tự follow redirect, không log token và B phải xác minh độc lập. Filter relay **không** gia hạn token, không thay OAuth2 Client/token exchange và không tự cấp quyền. Token relay phải được thiết kế có chủ đích như một cơ chế ủy quyền liên dịch vụ, không phải thao tác copy header ở mọi outbound call.

## Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Reactive Resource Server Bearer Token Propagation](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/bearer-tokens.html)
- [Spring Security 6.5 — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — ServerBearerExchangeFilterFunction API](https://docs.spring.io/spring-security/site/docs/6.5.4-SNAPSHOT/api/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServerBearerExchangeFilterFunction.html)
- [Spring Security 6.5 — OAuth2 Client in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Framework 6.2 — WebClient Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-filter.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Reactor Netty — HTTP Client](https://projectreactor.io/docs/netty/release/reference/http-client.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [OWASP — Server Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
