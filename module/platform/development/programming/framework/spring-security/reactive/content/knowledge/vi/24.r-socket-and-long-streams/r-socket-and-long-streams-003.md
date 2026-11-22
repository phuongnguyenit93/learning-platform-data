# Xác thực RSocket bằng Simple Authentication hoặc Bearer token trong Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Chủ đề cha:** RSocket và luồng dài  
> **Mục tiêu:** Thiết lập bảo mật RSocket ở khung SETUP hoặc từng request, gửi Simple Authentication (username/password) hoặc Bearer JWT theo đúng authentication metadata, phân quyền RSocket routes bằng Spring Security, xử lý stream dài và kiểm thử trực tiếp RSocket TCP bằng Java 17+.

## 1. Bài toán và kết quả cần đạt

Một server nhận RSocket request `secure.echo`, `secure.stream` và `secure.emit`. Một client có thể mở kết nối TCP rồi gửi nhiều yêu cầu trong cùng connection. Ta muốn từ chối các request không được xác thực, đồng thời cho phép hai hình thức chứng minh danh tính:

1. **Simple Authentication:** client cung cấp username/password trong RSocket Authentication Metadata; Spring Security kiểm tra bằng `ReactiveUserDetailsService` và password encoder.
2. **Bearer JWT:** client cung cấp access token trong authentication metadata; Spring Security dùng `ReactiveJwtDecoder` xác minh chữ ký và claims, rồi so scope/authorities với route.

Khác REST API, RSocket có các frames SETUP, REQUEST_RESPONSE, REQUEST_STREAM, REQUEST_FNF, REQUEST_CHANNEL, PAYLOAD, REQUEST_N và CANCEL. Một connection có thể tồn tại lâu và đồng thời mang nhiều streams. Bảo mật cần quyết định **ai có quyền kết nối** và **ai có quyền thực hiện từng request**, không coi hai câu hỏi là một.

Trong bài này, RSocket server chạy trên TCP localhost trong lab. Bất kỳ môi trường thực nào gửi username/password hay token phải có **TLS hoặc WSS**, redaction và giới hạn tài nguyên. TCP plaintext trong ví dụ chỉ phục vụ học tập trên máy cá nhân.

## 2. RSocket so với HTTP và WebSocket

| Chủ đề | HTTP WebFlux | RSocket |
| --- | --- | --- |
| Giao thức | HTTP requests/responses | RSocket frames + metadata/payload |
| Routing | URL, HTTP method | Route trong RSocket metadata |
| Credential | Thường `Authorization`/cookie | Authentication metadata extension |
| Security DSL | `ServerHttpSecurity` | `RSocketSecurity` |
| Response error | HTTP 401/403/5xx | RSocket ERROR/frame hoặc setup rejection |
| Luồng dài | SSE/WebSocket/Flux | Request-stream/request-channel với backpressure |
| Kết nối | Từng request hoặc HTTP connection pool | Một connection multiplex nhiều interactions |

**Không thể chỉ khai báo HTTP `SecurityWebFilterChain` rồi coi các RSocket routes đã được bảo vệ.** Bảo mật RSocket đi qua `PayloadSocketAcceptorInterceptor`; WebSocket handshake HTTP có thể được bảo vệ ở lớp khác, nhưng các RSocket request frames vẫn phải áp chính sách của chúng.

RSocket request-response thường đọc bằng `retrieveMono`; request-stream bằng `retrieveFlux`; fire-and-forget bằng `send()`. Với fire-and-forget, Mono hoàn thành khi gửi thành công **không xác nhận** một transaction nghiệp vụ đã commit.

## 3. Khái niệm authentication ở SETUP và request

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as Spring RSocket Server
    participant A as Security Interceptor
    participant H as MessageMapping
    C->>S: SETUP + authentication metadata (nếu có)
    S->>A: Check SETUP policy
    alt Setup rejected
        A-->>C: Setup error
    else Setup accepted
        S-->>C: Connection established
        C->>S: REQUEST_RESPONSE route=secure.echo + metadata
        S->>A: Authenticate request metadata / context
        A->>A: Check matching route authorities
        alt Not allowed
            A-->>C: RSocket error
        else Allowed
            A->>H: invoke handler
            H-->>C: response payload
        end
    end
~~~

**SETUP authentication** phù hợp khi một connection luôn thuộc một người dùng hoặc một service: client đăng nhập khi kết nối, các requests sau có thể thừa hưởng security context. **Per-request authentication** phù hợp cho connection dùng chung: từng request mang token/credential của chủ thể thực.

Có thể dùng cả hai: workload có quyền mở connection ở SETUP và end-user có quyền riêng cho từng request. Tuy nhiên phải thiết kế rõ chính sách inheritance/override. Không lấy token của Alice ở SETUP rồi gửi yêu cầu của Bob trên cùng requester mà không có kiểm soát per-request, vì downstream có thể xử lý tất cả như Alice.

**Thời điểm kiểm tra rất quan trọng:** một JWT được xác minh khi mở stream không có nghĩa mọi event tiếp theo của stream được xác minh lại tự động. Xem mục về thời hạn và revocation.

## 4. Kiến trúc bảo mật Spring RSocket

Các class/bean chính:

- `@EnableRSocketSecurity` và `RSocketSecurity` từ Spring Security RSocket.
- `PayloadSocketAcceptorInterceptor` do `rsocket.build()` tạo.
- `SecuritySocketAcceptorInterceptor` gắn vào acceptor, Spring Boot tự đăng ký khi dependencies đúng; manual integration cần `RSocketServerCustomizer`.
- `AuthenticationPayloadInterceptor` kết nối authentication converter với `ReactiveAuthenticationManager`.
- `AuthorizationPayloadInterceptor` quyết định quyền theo route/setup/metadata.
- `MapReactiveUserDetailsService` và `PasswordEncoder` cho Simple Authentication.
- `ReactiveJwtDecoder` + validators khi dùng JWT.
- `RSocketRequester` ở client và `@MessageMapping` ở receiver.

Cấu hình WebFlux HTTP và RSocket có thể tồn tại cạnh nhau nhưng không cùng một filter chain. Đối với RSocket TCP độc lập, không có HTTP 401/403 cho từng frame. Nếu tổ chức đặt HTTP gateway trước RSocket, gateway tự định nghĩa việc ánh xạ lỗi sang HTTP response, không phải RSocket protocol mặc định.

## 5. MIME type của authentication metadata

RSocket authentication sử dụng `WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION`:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());
~~~

MIME type xác định cách Spring Security đọc metadata. Client cần composite metadata khi gửi đồng thời route + credential. Tên route, username/password và Bearer token là các trường **khác nhau**, không gộp credential vào route hoặc payload business tùy tiện.

| Phía gửi | Đối tượng | Encoder | Security DSL phía nhận |
| --- | --- | --- | --- |
| Simple | `UsernamePasswordMetadata` | `SimpleAuthenticationEncoder` | `simpleAuthentication(...)` |
| Bearer JWT | `BearerTokenMetadata` | String metadata theo RSocket extension | `jwt(...)` |

Không đưa HTTP header `Authorization: Bearer ...` vào RSocket TCP rồi nghĩ receiver tự nhận diện. Auth metadata RSocket là định dạng riêng; nếu MIME type hoặc encoder sai, server không thể xác thực đúng.

## 6. Simple Authentication là gì, có phải HTTP Basic không?

Simple Authentication gửi username/password theo RSocket Authentication Metadata Extension. Nó không phải HTTP Basic, mặc dù cùng mang hai giá trị username/password. Spring Security đã deprecate DSL `basicAuthentication(...)` cũ; đối với cơ chế chuẩn, dùng `simpleAuthentication(Customizer.withDefaults())`.

Receiver mẫu:

~~~java
@Bean
PayloadSocketAcceptorInterceptor rsocketInterceptor(
        RSocketSecurity rsocket) {
    rsocket.authorizePayload(authz -> authz
            .anyRequest().authenticated()
            .anyExchange().permitAll())
        .simpleAuthentication(Customizer.withDefaults());
    return rsocket.build();
}
~~~

Đoạn trên là **snippet**: cần đặt trong class `@Configuration`/`@EnableRSocketSecurity` và thêm user details/password policy. Với production, dùng account store/IdP có rate limiting, lockout và password hashing phù hợp; không hardcode password, không dùng `User.withDefaultPasswordEncoder()` ngoài demo.

Username/password là credential dài hạn. Nếu một shared pool dùng credentials của admin ở SETUP, toàn bộ users có nguy cơ nhận quyền admin. Dùng credential ở từng request hoặc workload identity ở SETUP khi connection shared.

## 7. Bearer JWT và khác biệt với opaque token

Bearer authentication metadata có thể chở một token string; ví dụ Spring Security `rsocket.jwt(...)` xác thực **JWT** bằng `ReactiveJwtDecoder`. Nó không tự cấp token, không refresh token và không có mặc định introspection cho opaque random string.

Các kiểm tra JWT cần có:
- Chữ ký JWS bằng trusted public key/JWKS và thuật toán allowlist.
- `iss` đúng trusted issuer.
- `exp`, `nbf` theo clock skew cho phép.
- `aud` chứa chính RSocket service hoặc resource ID được phép.
- Claim type/token purpose phù hợp; **ID Token OIDC không thay access token**.
- Scope/roles tại route và owner/tenant tại domain service.

Nếu hệ thống thực sự dùng OAuth2 opaque token, phải dùng custom authentication manager/introspection pipeline tương thích và test; không tắt kiểm tra JWT hoặc coi Base64 decode là xác thực.

## 8. Route authorization và thứ tự matcher

DSL minh họa:

~~~java
rsocket.authorizePayload(authz -> authz
    .setup().permitAll()
    .route("secure.echo").hasRole("USER")
    .route("secure.stream").hasRole("USER")
    .route("secure.emit").hasRole("USER")
    .anyRequest().denyAll()
    .anyExchange().permitAll());
~~~

Matchers được xét **theo thứ tự**. Rule `anyRequest().denyAll()` chặn mọi RSocket request route không khai báo. `anyExchange().permitAll()` là fallback cho exchanges còn lại, chẳng hạn những continuation frames không có route metadata, theo hướng dẫn Spring Security.

Nếu đặt `anyRequest().permitAll()` trước private routes, tất cả requests có thể được cho phép và các checks phía sau không còn tác dụng. Không nhầm một route string với HTTP path. Với JWT, ví dụ dùng `.hasAuthority("SCOPE_messages.read")` thay role theo chính sách API.

### 8.1. Yêu cầu quyền ở SETUP

Nếu peer cần quyền đặc biệt mới được mở connection:

~~~java
rsocket.authorizePayload(authz -> authz
    .setup().hasRole("SETUP")
    .route("secure.echo").hasAuthority("SCOPE_messages.read")
    .anyRequest().denyAll()
    .anyExchange().permitAll());
~~~

Đây là **cấu hình biến thể**. Peer SETUP cần `ROLE_SETUP`; các requests có thể mang credential user riêng. Cần kiểm chứng setup identity có được giữ hay overridden khi request metadata xuất hiện, tránh trộn quyền peer với quyền user.

## 9. Bài thực hành Java 17+ và giới hạn phiên bản

Project sử dụng Spring Boot `3.3.13` và Spring Security 6.x để có APIs ổn định cho ví dụ. Đây là phiên bản học tập **đã hết OSS support**; production mới cần phiên bản còn hỗ trợ và rà soát APIs/known vulnerabilities.

~~~text
rsocket-simple-bearer/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/rsocket/
    │   │   ├── RSocketApp.java
    │   │   ├── SecuredRoutes.java
    │   │   ├── SimpleRSocketSecurityConfig.java
    │   │   ├── JwtRSocketSecurityConfig.java
    │   │   └── SimpleClient.java
    │   └── resources/application.yml
    └── test/java/demo/rsocket/
        ├── SimpleAuthRSocketTest.java
        └── JwtBearerRSocketTest.java
~~~

Hai profiles `simple` và `jwt` cho phép dùng cùng route controller nhưng chọn authentication mechanism riêng. Không bật cả hai cùng lúc trong lab vì sẽ đăng ký hai interceptors với semantics khác nhau.

### 9.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>rsocket-simple-bearer</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-rsocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build><plugins><plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin></plugins></build>
</project>
~~~

RSocket TCP là một server riêng, không cần HTTP Servlet starter. `spring-boot-starter-rsocket` cung cấp RSocket messaging/Netty; `spring-security-rsocket` mới cung cấp metadata security. Dependency OAuth2 Resource Server dùng cho JWT profile, không phải Authorization Server.

### 9.2. RSocketApp.java

~~~java
package demo.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketApp {
    public static void main(String[] args) {
        SpringApplication.run(RSocketApp.class, args);
    }
}
~~~

### 9.3. application.yml

~~~yaml
spring:
  profiles:
    default: simple
  rsocket:
    server:
      transport: tcp
      port: ${RSOCKET_PORT:7000}

demo:
  rsocket:
    username: ${DEMO_RSOCKET_USER:demo}
    password: ${DEMO_RSOCKET_PASSWORD:}
  jwt:
    issuer: ${RSOCKET_JWT_ISSUER:https://issuer.example.invalid/realms/demo}
    jwks-uri: ${RSOCKET_JWKS_URI:https://issuer.example.invalid/jwks}
    audience: ${RSOCKET_JWT_AUDIENCE:messages-api}
~~~

`.invalid` dùng làm placeholder; **không có IdP tại đó**. Simple profile fail fast khi password rỗng; JWT profile chỉ hoạt động với issuer/JWKS URLs thật của IdP tin cậy. Lệnh kiểm thử có thể dùng random RSocket port `0`, không cần cố định 7000.

## 10. SecuredRoutes.java: ba kiểu tương tác

~~~java
package demo.rsocket;

import java.time.Duration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Controller
public class SecuredRoutes {

    @MessageMapping("secure.echo")
    public Mono<String> echo(String value) {
        return Mono.just("echo:" + value);
    }

    @MessageMapping("secure.stream")
    public Flux<String> stream(Integer requested) {
        int count = Math.min(5, Math.max(1, requested));
        return Flux.range(0, count)
            .delayElements(Duration.ofMillis(20))
            .map(i -> "event-" + i);
    }

    @MessageMapping("secure.emit")
    public Mono<Void> emit(String message) {
        // Bài lab không ghi database hoặc tạo side effect.
        return Mono.empty();
    }
}
~~~

Spring Boot tạo `RSocketMessageHandler` để tìm các route `@MessageMapping`, và interceptor xác minh trước khi handler xử lý. `secure.echo` là request-response, `secure.stream` là request-stream, `secure.emit` có thể dùng fire-and-forget.

Stream giới hạn tối đa năm events cho lab. Production cần quotas theo principal/tenant, message size limits, chống stream exhaustion, cancellation, và business authorization trên dữ liệu được gửi đi. Không gửi một `Flux` toàn cục của nhiều tenants tới mọi subscribers chỉ vì route yêu cầu authenticated.

## 11. SimpleRSocketSecurityConfig.java: username/password thật sự được verify

~~~java
package demo.rsocket;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@Profile("simple")
@EnableRSocketSecurity
public class SimpleRSocketSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(
            PasswordEncoder encoder,
            @Value("${demo.rsocket.username}") String username,
            @Value("${demo.rsocket.password}") String password) {
        if (password.isBlank()) {
            throw new IllegalStateException(
                "DEMO_RSOCKET_PASSWORD must be configured");
        }
        UserDetails user = User.withUsername(username)
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    PayloadSocketAcceptorInterceptor simpleInterceptor(
            RSocketSecurity rsocket) {
        rsocket.authorizePayload(authz -> authz
                .setup().permitAll()
                .route("secure.echo").hasRole("USER")
                .route("secure.stream").hasRole("USER")
                .route("secure.emit").hasRole("USER")
                .anyRequest().denyAll()
                .anyExchange().permitAll())
            .simpleAuthentication(Customizer.withDefaults());
        return rsocket.build();
    }
}
~~~

**Đọc kỹ:**
1. `@EnableRSocketSecurity` kết nối RSocket Security DSL với app.
2. `MapReactiveUserDetailsService` lưu `UserDetails` demo với BCrypt hash, không plaintext password.
3. `setup().permitAll()` cho phép tạo connection không credential, nhưng private routes vẫn cần quyền.
4. `roles("USER")` tạo authority `ROLE_USER` để `hasRole("USER")` so khớp.
5. `simpleAuthentication` cài credential converter; không dùng HTTP Basic.
6. `anyRequest().denyAll()` từ chối các request routes ngoài danh sách.
7. Không tạo thêm profile JWT bean đồng thời; chỉ chọn một profile.

Production nên dùng account service, secret manager và password policies thay cho một user cấu hình. Password trong metadata chỉ an toàn qua TLS/WSS; không dùng RSocket TCP plaintext qua internet.

## 12. SimpleClient.java: gửi Simple credential ở SETUP

~~~java
package demo.rsocket;

import java.time.Duration;
import java.util.List;
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;

public final class SimpleClient {

    private static final MimeType AUTH =
        MimeTypeUtils.parseMimeType(
            WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    public static void main(String[] args) {
        String user = System.getenv()
            .getOrDefault("DEMO_RSOCKET_USER", "demo");
        String password = System.getenv("DEMO_RSOCKET_PASSWORD");
        if (password == null || password.isBlank()) {
            throw new IllegalStateException(
                "DEMO_RSOCKET_PASSWORD must be configured");
        }

        RSocketRequester requester = RSocketRequester.builder()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()))
            .setupMetadata(
                new UsernamePasswordMetadata(user, password), AUTH)
            .connectTcp("127.0.0.1", 7000)
            .block(Duration.ofSeconds(10));

        if (requester == null) {
            throw new IllegalStateException("RSocket connect failed");
        }
        try {
            String echo = requester.route("secure.echo")
                .data("hello")
                .retrieveMono(String.class)
                .block(Duration.ofSeconds(10));
            List<String> events = requester.route("secure.stream")
                .data(3)
                .retrieveFlux(String.class)
                .collectList()
                .block(Duration.ofSeconds(10));
            System.out.println(echo);
            System.out.println(events);
        } finally {
            requester.rsocket().dispose();
        }
    }
}
~~~

Với password trùng server và server chạy ở localhost:7000, stdout dự kiến:

~~~text
echo:hello
[event-0, event-1, event-2]
~~~

**Phân biệt:** Đây là output kỳ vọng của code lab, chưa có nghĩa mã nguồn đã được chạy trong chính cuộc hội thoại. `RSocketRequester.builder()` hỗ trợ cấu hình setup metadata, `SimpleAuthenticationEncoder` chịu trách nhiệm mã hóa username/password vào authentication MIME.

Tại SETUP, requester biểu diễn một principal cụ thể. Không tái dùng requester này làm singleton cho nhiều users khác nhau nếu muốn downstream phân quyền theo người gửi HTTP request phía trên.

## 13. Simple credential ở mỗi request

Đối với kết nối dùng chung, dùng credential tại request:

~~~java
// Snippet; requester, user, password, authMime đã có.
UsernamePasswordMetadata credential =
    new UsernamePasswordMetadata(user, password);

Mono<String> result = requester.route("secure.echo")
    .metadata(credential, authMime)
    .data("hello")
    .retrieveMono(String.class);
~~~

Requester phải được dựng với `SimpleAuthenticationEncoder` trong `RSocketStrategies`. Auth metadata cần đi **cùng** interaction cụ thể, không lưu username/password vào một biến mutable toàn cục như `currentCredential` trên pooled requester.

Ở phía server, `simpleAuthentication` có thể xử lý credential ở setup hoặc request theo extension. Đặt matching/authorization rules để request không metadata không tự được cấp quyền. Nếu một endpoint chỉ cần public, thêm route `permitAll` **tường minh** trước deny-all, không mở toàn bộ API.

## 14. JwtRSocketSecurityConfig.java: Bearer JWT ở receiver

~~~java
package demo.rsocket;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.rsocket.EnableRSocketSecurity;
import org.springframework.security.config.annotation.rsocket.RSocketSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.rsocket.core.PayloadSocketAcceptorInterceptor;

@Configuration
@Profile("jwt")
@EnableRSocketSecurity
public class JwtRSocketSecurityConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${demo.jwt.issuer}") String issuer,
            @Value("${demo.jwt.jwks-uri}") String jwksUri,
            @Value("${demo.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> validators =
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                jwt -> jwt.getAudience().contains(audience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Wrong audience for RSocket service", null)));

        decoder.setJwtValidator(validators);
        return decoder;
    }

    @Bean
    PayloadSocketAcceptorInterceptor jwtInterceptor(
            RSocketSecurity rsocket) {

        rsocket.authorizePayload(authz -> authz
                .setup().permitAll()
                .route("secure.echo")
                    .hasAuthority("SCOPE_messages.read")
                .route("secure.stream")
                    .hasAuthority("SCOPE_messages.read")
                .route("secure.emit")
                    .hasAuthority("SCOPE_messages.write")
                .anyRequest().denyAll()
                .anyExchange().permitAll())
            .jwt(Customizer.withDefaults());

        return rsocket.build();
    }
}
~~~

**Không chỉ check chữ ký:** `withJwkSetUri` dùng trusted JWKS URI, pin `RS256` theo policy và ghép issuer/time validators với audience validator. Nếu IdP thật dùng thuật toán khác, chọn allowlist theo IdP contract, không tin algorithm do token khai tùy ý.

Default JWT scope converter thường tạo `SCOPE_messages.read` từ `scope=messages.read` hoặc `scp`. Nếu IdP phát role claim khác, cần converter tương ứng và negative tests. Token có cùng chữ ký issuer nhưng `aud` của service khác **phải bị reject**.

Không dùng ID Token OIDC như access token cho RSocket Resource Server. Không đưa một URL JWKS do user request gửi vào `withJwkSetUri`, tránh SSRF/trust injection.

## 15. BearerTokenMetadata ở SETUP hoặc request

Cả hai hình thức dùng `BearerTokenMetadata`:

~~~java
import io.rsocket.metadata.WellKnownMimeType;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;

MimeType authMime = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

// accessToken phải do OAuth2 client tin cậy lấy cho đúng audience.
String accessToken = tokenFromAuthorizedClient;

// SETUP authentication: một identity cho connection.
Mono<RSocketRequester> connection = RSocketRequester.builder()
    .setupMetadata(new BearerTokenMetadata(accessToken), authMime)
    .connectTcp("127.0.0.1", 7000);

// Per-request authentication: identity riêng cho interaction.
Mono<String> response = requester.route("secure.echo")
    .metadata(new BearerTokenMetadata(accessToken), authMime)
    .data("hello")
    .retrieveMono(String.class);
~~~

Đây là **snippet**, biến `tokenFromAuthorizedClient` và `requester` chỉ là input giả định (không phải token được phát trong project); dùng OAuth2 Client Credentials/Authorization Code + token exchange hợp lệ tùy trust model. Không hardcode JWT, không gửi raw ID Token, không copy token sai audience tới service này.

**Không nhầm RSocket Bearer với HTTP:** metadata chứa token string, client không thêm literal prefix `Bearer ` của Authorization HTTP header. Phía server `jwt()` dựa vào `ReactiveJwtDecoder`; nếu token hết hạn/có chữ ký sai, request bị authentication error.

## 16. Kiểm thử phải dùng RSocketRequester, không chỉ WebTestClient

`WebTestClient` dành cho HTTP WebFlux và không thực hiện RSocket SETUP, metadata encoding hay request-stream frames. Bài kiểm thử sau khởi động RSocket server trên **random TCP port**.

Spring Boot 3.3 cung cấp annotation `@LocalRSocketServerPort` trong package `org.springframework.boot.test.rsocket.server`, với `spring.rsocket.server.port=0`; client dùng `RSocketRequester.Builder.connectTcp(...)`.

Các checks cần có:
- Username/password đúng ở SETUP được quyền gọi route.
- Không credential bị từ chối ở private route.
- Password sai ở SETUP hoặc per-request bị từ chối.
- Username/password đúng ở request trên connection anonymous được chấp nhận.
- Stream chỉ emit đúng số events; route ngoài allowlist bị deny.
- Bearer metadata được JWT authentication pipeline đọc đúng; valid scope pass, missing scope fail.
- JWT cryptography/issuer/audience/expiry phải test với signed tokens riêng, không coi Mockito decoder là verify thật.

## 17. SimpleAuthRSocketTest.java — real TCP security tests

~~~java
package demo.rsocket;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.rsocket.metadata.SimpleAuthenticationEncoder;
import org.springframework.security.rsocket.metadata.UsernamePasswordMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.profiles.active=simple",
    "spring.rsocket.server.port=0",
    "demo.rsocket.password=lab-only-password"
})
class SimpleAuthRSocketTest {

    static final MimeType AUTH = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort int port;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> builders;

    Mono<RSocketRequester> connected(String password) {
        RSocketRequester.Builder builder = builders.getObject()
            .rsocketStrategies(s ->
                s.encoder(new SimpleAuthenticationEncoder()));
        if (password != null) {
            builder.setupMetadata(
                new UsernamePasswordMetadata("demo", password), AUTH);
        }
        return builder.connectTcp("127.0.0.1", port);
    }

    @Test
    void correctSetupCredentialsAllowEcho() {
        StepVerifier.create(connected("lab-only-password")
                .flatMap(r -> r.route("secure.echo")
                    .data("hi").retrieveMono(String.class)))
            .expectNext("echo:hi").verifyComplete();
    }

    @Test
    void missingCredentialsCannotReadPrivateRoute() {
        StepVerifier.create(connected(null)
                .flatMap(r -> r.route("secure.echo")
                    .data("hi").retrieveMono(String.class)))
            .expectError().verify();
    }

    @Test
    void wrongSetupPasswordIsRejected() {
        StepVerifier.create(connected("wrong")
                .flatMap(r -> r.route("secure.echo")
                    .data("hi").retrieveMono(String.class)))
            .expectError().verify();
    }

    @Test
    void perRequestSimpleCredentialsAreAccepted() {
        StepVerifier.create(connected(null)
                .flatMap(r -> r.route("secure.echo")
                    .metadata(new UsernamePasswordMetadata(
                        "demo", "lab-only-password"), AUTH)
                    .data("request").retrieveMono(String.class)))
            .expectNext("echo:request").verifyComplete();
    }

    @Test
    void invalidRequestCredentialIsRejected() {
        StepVerifier.create(connected(null)
                .flatMap(r -> r.route("secure.echo")
                    .metadata(new UsernamePasswordMetadata(
                        "demo", "wrong"), AUTH)
                    .data("request").retrieveMono(String.class)))
            .expectError().verify();
    }

    @Test
    void streamOnlyEmitsRequestedElements() {
        StepVerifier.create(connected("lab-only-password")
                .flatMap(r -> r.route("secure.stream")
                    .data(3).retrieveFlux(String.class).collectList()))
            .assertNext(list -> assertEquals(
                List.of("event-0", "event-1", "event-2"), list))
            .verifyComplete();
    }

    @Test
    void unknownRouteDoesNotBecomePublic() {
        StepVerifier.create(connected("lab-only-password")
                .flatMap(r -> r.route("admin.secret")
                    .data("x").retrieveMono(String.class)))
            .expectError().verify();
    }
}
~~~

**Bảy tests** kiểm tra RSocket TCP, metadata encoder và route authorization. Chúng không có HTTP status 401/403: test mong đợi RSocket signal error. `ObjectProvider<RSocketRequester.Builder>` lấy builder mới cho mỗi connection, tránh metadata SETUP của test trước “dính” qua test sau; builder là mutable/prototype. Test suite thực tế còn cần connection teardown/`dispose()` theo lifecycle để tránh rò resources khi chạy CI lâu.

Các tests dùng account demo với BCrypt; không chứng minh được LDAP/IdP, JWT trust, TLS hoặc distributed session authorization của production.

## 18. JwtBearerRSocketTest.java — metadata + scope, không thay crypto test

~~~java
package demo.rsocket;

import static org.mockito.Mockito.when;

import java.time.Instant;
import io.rsocket.metadata.WellKnownMimeType;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.rsocket.server.LocalRSocketServerPort;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.rsocket.metadata.BearerTokenMetadata;
import org.springframework.util.MimeType;
import org.springframework.util.MimeTypeUtils;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringBootTest(properties = {
    "spring.profiles.active=jwt",
    "spring.rsocket.server.port=0"
})
class JwtBearerRSocketTest {

    static final MimeType AUTH = MimeTypeUtils.parseMimeType(
        WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

    @LocalRSocketServerPort int port;

    @Autowired
    ObjectProvider<RSocketRequester.Builder> builders;

    @MockBean
    ReactiveJwtDecoder jwtDecoder;

    Mono<String> ask(String token) {
        return builders.getObject()
            .connectTcp("127.0.0.1", port)
            .flatMap(r -> r.route("secure.echo")
                .metadata(new BearerTokenMetadata(token), AUTH)
                .data("hi").retrieveMono(String.class));
    }

    Jwt fakeJwt(String scopes) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-value")
            .header("alg", "RS256")
            .subject("alice")
            .issuedAt(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(300))
            .claim("scope", scopes)
            .claim("aud", new String[]{"messages-api"})
            .build();
    }

    @Test
    void validMockJwtWithReadScopeMayEcho() {
        when(jwtDecoder.decode("token-with-read"))
            .thenReturn(Mono.just(fakeJwt("messages.read")));
        StepVerifier.create(ask("token-with-read"))
            .expectNext("echo:hi").verifyComplete();
    }

    @Test
    void jwtWithoutScopeIsRejectedByAuthorization() {
        when(jwtDecoder.decode("limited-token"))
            .thenReturn(Mono.just(fakeJwt("profile")));
        StepVerifier.create(ask("limited-token"))
            .expectError().verify();
    }

    @Test
    void jwtDecoderErrorRejectsRequest() {
        when(jwtDecoder.decode("invalid-token"))
            .thenReturn(Mono.error(
                new BadJwtException("Invalid JWT")));
        StepVerifier.create(ask("invalid-token"))
            .expectError().verify();
    }
}
~~~

**Ba tests** minh họa Spring RSocket đọc Bearer metadata, truyền qua decoder và kiểm tra scope. `@MockBean ReactiveJwtDecoder` **không verify chữ ký/iss/exp/nbf/aud thật**. Trong production test suite, phải có test riêng ký RSA với private test key, verify bằng `NimbusReactiveJwtDecoder` và JWKS fake, thử sai chữ ký, issuer, audience, expired, future nbf.

`@MockBean` được sử dụng theo Boot 3.3; ở Boot mới hơn API mocking có thể đổi. Không nhận token giả `test-value` ngoài lớp test mock.

## 19. Lệnh build, chạy server và client

Trên Java 17+ và Maven, tại thư mục có `pom.xml`:

~~~bash
mvn clean test
mvn -q -DskipTests package
~~~

Test classes cấu hình random RSocket TCP port, không cần IdP thật cho phần mock. Các tests phải được chạy trong môi trường có Maven/JDK phù hợp; đây là **mã hướng dẫn** chứ không phải kết quả biên dịch đã kiểm chứng trong cuộc hội thoại này.

Chạy Simple profile ở local:

~~~bash
export DEMO_RSOCKET_PASSWORD="lab-only-password"
export SPRING_PROFILES_ACTIVE=simple
mvn spring-boot:run
~~~

Trên PowerShell:

~~~powershell
$env:DEMO_RSOCKET_PASSWORD = "lab-only-password"
$env:SPRING_PROFILES_ACTIVE = "simple"
mvn spring-boot:run
~~~

Mở terminal khác và chạy client:

~~~bash
java -cp target/classes demo.rsocket.SimpleClient
~~~

**Lưu ý classpath:** `SimpleClient` phụ thuộc Spring/RSocket libraries; `java -cp target/classes` **không đủ classpath dependency** cho client standalone. Dùng Maven exec plugin với project dependencies, ví dụ:

~~~bash
mvn org.codehaus.mojo:exec-maven-plugin:3.3.0:java \
  -Dexec.mainClass=demo.rsocket.SimpleClient
~~~

PowerShell có thể nhập thành một dòng:

~~~powershell
mvn org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.rsocket.SimpleClient
~~~

Khi `localhost:7000` đang chạy và password khớp, stdout kỳ vọng:

~~~text
echo:hello
[event-0, event-1, event-2]
~~~

Không ghi password/JWT thật vào Git, log, process command arguments hoặc recording. Đây là TCP local **chưa có TLS**; chuyển sang TLS/WSS khi chạy trong mạng thật.

## 20. Chạy JWT profile với IdP thật

Tạo OAuth2 Client phù hợp để lấy **access token** do một Identity Provider cấp cho audience `messages-api`. Không lấy ID Token của login rồi dùng bừa bãi làm access token RSocket.

Khi đã có IdP thật và JWKS hợp lệ, đặt cấu hình:

~~~bash
export SPRING_PROFILES_ACTIVE=jwt
export RSOCKET_JWT_ISSUER="https://idp.example.com/realms/demo"
export RSOCKET_JWKS_URI="https://idp.example.com/realms/demo/protocol/openid-connect/certs"
export RSOCKET_JWT_AUDIENCE="messages-api"
mvn spring-boot:run
~~~

Client phải gửi:

~~~java
MimeType mimeType = MimeTypeUtils.parseMimeType(
    WellKnownMimeType.MESSAGE_RSOCKET_AUTHENTICATION.getString());

Mono<RSocketRequester> requester = RSocketRequester.builder()
    .setupMetadata(new BearerTokenMetadata(accessToken), mimeType)
    .connectTcp("127.0.0.1", 7000);
~~~

Đây là **snippet**, `accessToken` phải được lấy từ OAuth2 client/server hợp lệ. Nếu muốn dùng request-level identity, thay `setupMetadata(...)` bằng `route(...).metadata(new BearerTokenMetadata(accessToken), mimeType)`.

Môi trường lab mặc định issuer `.invalid` không xác thực được Bearer thật. Không “sửa” 401 bằng cách bỏ issuer/audience/signature validation. Đảm bảo JWKS qua HTTPS, thuật toán đúng, đồng hồ NTP đúng và key rotation được giám sát.

## 21. Long stream: expiry và revocation không tự động cập nhật

Ví dụ user mở request-stream với JWT còn hạn 60 giây. Decoder xác minh lúc request được bắt đầu; 60 giây sau token hết hạn, **stream đang chạy có thể không tự bị đóng**, bởi security đã kiểm tra ở điểm authorization ban đầu. Điều này phải được giải quyết theo security SLA chứ không mặc định framework thực hiện continuous authorization.

Các chiến lược:
1. Giới hạn thời lượng stream, buộc client subscribe lại với token mới sau một khoảng.
2. Trước khi emit dữ liệu nhạy cảm, đối chiếu owner/tenant và permission hiện hành ở service.
3. Lắng nghe revocation/user disable events để đóng streams đang hoạt động khi cần.
4. Khi role/tenant thay đổi, đóng connections hoặc re-authorize streams theo policy.
5. Với credential SETUP lâu dài, đặt connection maximum age và buộc reconnect.
6. Nếu stream bị CANCEL, dừng upstream work và giải phóng DB/Redis/Netty resources.

Đừng bảo đảm “JWT bị revoke tại IdP thì RSocket stream dừng ngay” khi chỉ có local JWT signature validation. Stateless JWT không biết instant revocation nếu không có signal/introspection/state bổ sung.

## 22. Backpressure và cancellation là một phần của bảo mật

RSocket điều phối demand qua `REQUEST_N`, client có thể hủy stream bằng `CANCEL`. Dù user authenticated, vẫn cần:
- Maximum concurrent streams/user/tenant.
- Maximum payload/metadata sizes và deserialization limits.
- Rate limits, timeout, quotas và bounded buffers.
- Dừng generator khi cancel; không dùng `subscribe()` tùy tiện tạo background process không có owner.
- `doFinally` hoặc resource-aware operators cho cleanup/audit.
- Kiểm tra data-level tenant filters trên mỗi subscription.
- Không retry Request-Channel hoặc Fire-and-Forget có side effects vô điều kiện nếu response bị timeout.

Với `Flux.interval(Duration.ofMillis(100))`, thêm `take(max)` hoặc cơ chế kết thúc. Với data streams nhạy cảm, có thể yêu cầu reauthentication định kỳ thay vì stream vô hạn dựa vào quyền cũ.

## 23. Shared requester, token relay và Reactor Context

Một gateway nhận HTTP từ Alice và Bob có thể dùng một RSocketRequester tới downstream. Nếu requester có token Alice ở SETUP, requests Bob có thể được xem là Alice; đây là lỗi isolation nghiêm trọng.

**Mô hình an toàn:**
- Peer identity ở SETUP (nếu dùng) đại diện workload/gateway, không giả làm người dùng bất kỳ.
- End-user token cần được chọn tường minh ở từng request, có audience/scope hợp lệ cho downstream.
- Không tự relay inbound JWT tới mọi service; đôi khi cần OAuth2 Token Exchange / On-Behalf-Of.
- Giữ principal/tenant trong Reactor Context của request hiện hành, không dùng mutable global ThreadLocal.
- Khi đổi user, không tái sử dụng connection gắn user cũ nếu không có per-request auth.
- Test concurrent Alice/Bob với hai JWT mocks và các tenant khác nhau để phát hiện cross-request leakage.

Không đặt Bearer tokens trong RSocket route string, payload hay logger. `BearerTokenMetadata` đi trong protocol metadata và vẫn có thể bị lộ bởi wiretap/APM nếu chưa redact.

## 24. RSocket resume/reconnect khác fresh authentication

RSocket có thể hỗ trợ resume tùy cấu hình. Resume một protocol session **không chắc** tạo mới `SETUP` hoặc tái thực hiện xác thực như một connection hoàn toàn mới. Khi token bị revoke/expired hoặc user đổi tenant:
- Đánh giá max connection/session age.
- Cân nhắc disable resume cho high-risk subscriptions.
- Đóng requester và mở lại với credential được cấp mới.
- Không tự reconnect với stale password/JWT mãi mãi.
- Dùng backoff/jitter khi server restart để tránh thundering herd.
- Tách retry của authentication khỏi retry business action, đặc biệt FNF/channel có side effects.

Không khẳng định “resume tự làm reauthentication” khi chưa kiểm chứng implementation và security chain thực tế. Chỉ fresh SETUP và/or request metadata validation theo rules mới xác định kết quả.

## 25. TLS, WebSocket, CORS và metadata leakage

RSocket dùng TCP hoặc WebSocket. Khi chạy public:
- Dùng RSocket TCP/TLS hoặc WSS; kiểm tra server certificates.
- Restrict ingress, ports, origin tại WebSocket handshake phù hợp threat model.
- Giới hạn kết nối/frames/metadata và kiểm tra mTLS nếu workload nhạy cảm.
- Redact username/password, JWT và sensitive claims ở Netty wiretap, proxy, APM, tracing và error frames.
- Không coi browser CORS/Origin như authentication; RSocket client TCP không tuân Same-Origin Policy.
- WebSocket handshake HTTP có thể authenticated, nhưng vẫn cần RSocket route authorization nếu handler dùng metadata riêng.
- Không chuyển Bearer token sang host lạ khi redirect/proxy; dùng allowlisted destinations.
- Bảo vệ JWKS retrieval, issuer allowlist và token rotation.

**HTTP CSRF không tự áp dụng vào RSocket TCP** như cookie POST, nhưng nếu browser sử dụng WebSocket/cookie handshake thì origin/cross-site WebSocket hijacking và session policies cần được đánh giá. Không dùng kết luận “RSocket không cần security vì đã qua WebSocket” để bỏ route checks.

## 26. Bảng lỗi thường gặp và xử lý

| Triệu chứng | Nguyên nhân có thể | Điều cần làm |
| --- | --- | --- |
| Server nhận route dù chưa login | Matcher order hoặc thiếu RSocket interceptor | `@EnableRSocketSecurity`, deny-all và boot wiring |
| Simple credential bị từ chối | Thiếu encoder/sai auth MIME/password | `SimpleAuthenticationEncoder`, `UsernamePasswordMetadata` |
| Dùng HTTP Basic header không hiệu quả | RSocket cần authentication metadata | Gửi theo MIME extension |
| JWT đúng nhưng request fail | Audience/issuer/time/algorithm hoặc scope | Kiểm tra decoder + authorities |
| Shared requester lẫn Alice/Bob | SETUP token cho user đầu tiên | Per-request token hoặc tách connections |
| Sai route bị RSocket error | `anyRequest().denyAll()` | Đây là hành vi an toàn |
| Stream tiếp tục sau token exp | Chỉ authenticate lúc bắt đầu | Max-age stream, cancel/revalidation policy |
| RSocket TCP exposes credentials | Chạy plaintext ngoài localhost | TLS/WSS và redaction |
| Nhiều streams làm hết memory | Không quotas/backpressure | Limits, demand, cancellation |
| HTTP tests pass nhưng RSocket fail | WebTestClient không gửi RSocket frames | Dùng RSocketRequester integration test |
| Mock JWT test pass nhưng prod fail | Mock bỏ qua crypto validation | Signed JWT + trusted JWKS tests |
| Reconnect vẫn dùng credential revoked | Client cache token/setup cũ | Refresh và reauthenticate |
| FNF send success mà data không lưu | Không có ứng dụng-level ack | Xây response pattern nếu cần xác nhận |
| Custom decoder chấp nhận JWT sai aud | Quên audience validator | Add exact audience membership |
| 401/403 được tìm trong RSocket error | RSocket không có HTTP status per frame | Đọc protocol exception, gateway mapping |

Debug theo thứ tự: server transport + boot dependencies → security interceptor → SETUP decision → auth MIME + metadata encoder → authentication manager/decoder → scope/role matcher → handler → stream/backpressure → client lifecycle. Không hạ authentication policy chỉ để “cho demo chạy”.

## 27. Bài tập và checklist

**A — SETUP Simple:** Chạy profile simple, gửi username/password bằng Simple metadata ở SETUP, truy cập echo/stream. Đổi password thành sai và chứng minh request bị từ chối.

**B — Per-request Simple:** Mở anonymous SETUP, gửi metadata đúng ở một request và không metadata ở request tiếp theo. Giải thích tại sao kết quả khác.

**C — Bearer JWT:** Tích hợp IdP sandbox, gửi token `aud=messages-api` có scope messages.read; kiểm tra route được phép, token sai audience bị từ chối.

**D — Rule precedence:** Thử đặt `anyRequest().permitAll()` lên trước private route trong test-only rồi sửa; mô tả lỗi bypass.

**E — Shared connection:** Cho hai principals khác nhau cùng requester, mỗi request mang credential riêng; assert không lấy nhầm tenant/user.

**F — Long stream:** Đặt max stream duration và `take(n)`, thử CANCEL để chứng minh không sinh events nữa; thêm test revoke giữa stream.

**G — FNF:** Xây một route có acknowledgment rõ nếu nghiệp vụ yêu cầu xác nhận commit, không chỉ dựa vào send().

**H — TLS:** Đưa TCP từ localhost sang TLS/WSS ở staging, kiểm tra certs/proxy logs và auth metadata không bị ghi lại.

**Checklist:**
- [ ] RSocket setup/route và HTTP requests khác nhau.
- [ ] RSocketSecurity, PayloadSocketAcceptorInterceptor được gắn thực sự.
- [ ] Simple auth dùng UsernamePasswordMetadata + SimpleAuthenticationEncoder.
- [ ] Bearer dùng BearerTokenMetadata và ReactiveJwtDecoder.
- [ ] Valid JWT cần chữ ký/iss/exp/nbf/aud/scope hợp lệ.
- [ ] Route matcher đúng thứ tự, anyRequest deny-all.
- [ ] Shared connection không trộn user/setup identity.
- [ ] Stream dài có expiry/revocation/cancellation policy.
- [ ] RSocket TCP ngoài localhost được bảo vệ TLS/WSS.
- [ ] Có real TCP tests, mock decoder tests và crypto negative tests riêng.
- [ ] Không log secret/token, có quotas và backpressure.
- [ ] Không mặc định RSocket error là HTTP 401/403.

## 28. Câu hỏi tự kiểm tra và tài liệu

1. RSocket SETUP authentication và per-request authentication khác nhau thế nào?
2. Vì sao WebFlux SecurityWebFilterChain không đủ cho RSocket TCP?
3. Tại sao Simple Authentication không phải HTTP Basic?
4. Client cần encoder nào cho UsernamePasswordMetadata?
5. Authentication MIME type phải lấy từ WellKnownMimeType nào?
6. Điều gì xảy ra nếu anyRequest permitAll đứng trước private route?
7. BearerTokenMetadata có chứa HTTP header Authorization không?
8. JWT đúng issuer nhưng sai audience có được vào service không?
9. Khi stream đã mở, token hết hạn có tự kết thúc stream không?
10. Vì sao shared requester chứa user token ở SETUP nguy hiểm?
11. Mock ReactiveJwtDecoder kiểm tra cryptographic signature không?
12. Tại sao RSocket error không nên được assert theo HTTP status?
13. Vì sao connection resume không mặc định có nghĩa fresh login?
14. Khi nào phải dùng TLS/WSS và redaction?

**Tài liệu chính thức:**
- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/rsocket.html): SETUP/request authentication, Simple/JWT metadata, authorizePayload.
- [Spring Security — RSocketSecurity Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/rsocket/RSocketSecurity.html): simpleAuthentication, jwt, authorizePayload.
- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html): TCP/WebSocket, server autoconfiguration, requester.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models, @MessageMapping, metadata, streams.
- [Spring Security — SimpleAuthenticationEncoder](https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/rsocket/metadata/SimpleAuthenticationEncoder.html): client auth encoder.
- [Spring Security — Reactive OAuth2 JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): JWT validators.
- [Spring — RSocket Security Getting Started](https://spring.io/blog/2020/06/17/getting-started-with-rsocket-spring-security/): examples.
- [Spring — Testing RSocket Responders](https://spring.io/blog/2020/05/25/getting-started-with-rsocket-testing-spring-boot-responders): test real TCP requests.
- [RSocket Protocol](https://rsocket.io/about/protocol/): frames, backpressure, resumability.
- [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519): iss, aud, exp, nbf.
- [RFC 8725 — JWT Security Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key confusion, audience.
- [OWASP — WebSocket Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): WSS/origin/connection security khi dùng RSocket over WebSocket.

**Kết luận:** Spring Security Reactive dùng `RSocketSecurity` và authentication metadata để bảo vệ RSocket chứ không dựa vào HTTP filter. Simple Authentication gửi username/password qua encoder đúng; Bearer JWT yêu cầu trusted `ReactiveJwtDecoder`, issuer/audience/time/scope checks. Đặt rõ security boundary ở SETUP hay từng REQUEST, không dùng một SETUP user identity cho shared connections, và kiểm soát tuổi stream/cancellation/revocation. Kết quả kiểm thử đáng tin phải bao gồm **RSocket TCP metadata/route tests**, cộng thêm **JWT cryptographic tests** riêng trước khi triển khai thực tế.