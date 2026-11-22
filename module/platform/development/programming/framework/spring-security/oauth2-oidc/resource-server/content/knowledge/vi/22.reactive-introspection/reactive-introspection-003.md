# Thông tin xác thực tới introspection endpoint

## 1. Vì sao Resource Server cần một bộ credential riêng?

Trong **Spring Security OAuth 2.0 / OIDC Resource Server** chạy trên **WebFlux**, client thường gửi OAuth 2.0 access token qua HTTP:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_CUA_NGUOI_GOI>
~~~

Nếu API chọn **opaque token introspection**, nó phải hỏi Authorization Server (AS) token đó còn hoạt động và được cấp những scopes nào. Để hỏi, Resource Server (RS) tự đóng vai trò **một client của introspection endpoint**, và AS phải xác thực/ủy quyền cho RS.

Có **hai thông tin xác thực tách biệt**:

| Thông tin | Chủ thể | Vị trí | Ý nghĩa |
|---|---|---|---|
| Access token cần introspect | OAuth client hoặc user/service đang gọi API | Header `Authorization: Bearer` inbound, rồi body `token` outbound | Đối tượng cần kiểm tra tính hợp lệ và quyền |
| Introspection credential | Resource Server | Request outbound tới AS, thường header `Authorization: Basic` | Chứng minh **RS được phép hỏi trạng thái token** |

Ví dụ hợp đồng:

~~~text
Inbound API request:
  Authorization: Bearer <opaque-token-T>

Outbound introspection:
  POST https://id.example.test/oauth2/introspect
  Authorization: Basic <RS-client-id-and-secret>
  Content-Type: application/x-www-form-urlencoded
  Body: token=<opaque-token-T>
~~~

**Không gửi raw access token của caller như password của RS; không thay Basic bằng chính Bearer token đang cần kiểm tra.** Đây là hai trust boundaries khác nhau.

Bài này tập trung vào **thông tin xác thực Resource Server sử dụng khi gọi introspection endpoint**, trong bối cảnh kiến trúc **WebFlux reactive**. Các chủ đề liên quan gồm RFC 7662, RFC 6749, HTTP Basic, client credentials/secret management, mTLS, private-key JWT, tùy chỉnh `ReactiveOpaqueTokenIntrospector`, HTTP error handling, rotation và kiểm thử.

## 2. RFC 7662 mô tả việc gọi introspection như thế nào?

### 2.1. HTTP request

**RFC 7662 — OAuth 2.0 Token Introspection** định nghĩa HTTP POST với body kiểu `application/x-www-form-urlencoded`. Ví dụ:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: id.example.test
Authorization: Basic <RS_CLIENT_CREDENTIALS_BASE64>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

token=<ACCESS_TOKEN_T>&token_type_hint=access_token
~~~

Trong đó:

- `token`: **bắt buộc** — access token cần được kiểm tra.
- `token_type_hint`: **tùy chọn** — gợi ý loại token, không phải bằng chứng token hợp lệ.
- `Authorization: Basic`: một phương thức xác thực **Resource Server với AS**, nếu AS hỗ trợ `client_secret_basic`.
- Introspection URI: endpoint tin cậy của AS, do cấu hình server-side cung cấp.
- HTTPS/TLS: cần bảo vệ cả Basic credential và access token trong request.

Một số AS hỗ trợ cách xác thực khác ngoài HTTP Basic, chẳng hạn service Bearer token, mTLS hoặc JWT client assertion. **RFC 7662 yêu cầu endpoint được bảo vệ, nhưng không bắt buộc chỉ một client authentication scheme.** Phải tuân theo hợp đồng thực tế của AS.

### 2.2. HTTP response

Khi token còn active:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "active": true,
  "sub": "user-123",
  "scope": "orders.read orders.export",
  "client_id": "web-storefront",
  "aud": ["orders-api"],
  "exp": 2000000000
}
~~~

Khi token không còn hoạt động:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"active": false}
~~~

**HTTP 200 không đồng nghĩa token còn active**; trạng thái nằm trong JSON `active`. RFC 7662 không bắt buộc mọi response có đủ `sub`, `aud` hay `exp`; các thuộc tính ngoài `active` phụ thuộc token profile và authorization policy.

AS phải giới hạn ai được introspect vì endpoint có thể tiết lộ trạng thái token, user identity hoặc scopes. Một RS của Billing API không nên mặc nhiên có quyền truy vấn metadata của mọi token dành cho Orders API.

### 2.3. Sequence diagram

~~~mermaid
sequenceDiagram
    participant Caller as OAuth Client
    participant RS as WebFlux Resource Server
    participant Int as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    Caller->>RS: Authorization: Bearer T
    RS->>Int: introspect(T)
    Int->>AS: POST form token=T + Basic RS credential
    AS->>AS: Xác thực danh tính/quyền introspection của RS
    AS->>AS: Kiểm tra trạng thái token T
    AS-->>Int: active + attributes
    alt active=true
        Int-->>RS: OAuth2AuthenticatedPrincipal
        RS->>RS: Authorization theo scopes/ACL
        RS-->>Caller: 2xx hoặc 403
    else active=false
        Int-->>RS: Authentication failure
        RS-->>Caller: Thường 401
    else RS credential sai / AS lỗi
        AS-->>Int: 401/403/5xx hoặc timeout
        Int-->>RS: Không có quyết định token đáng tin
        RS-->>Caller: Fail closed theo exception policy
    end
~~~

**Lỗi xác thực RS với AS không phải là lỗi đăng nhập của user.** Hai request HTTP độc lập nên phải có error diagnostics độc lập.

## 3. `client_id` và `client_secret` trong introspection thuộc về ai?

Giả sử ứng dụng Orders API được AS cấp:

~~~text
Introspection endpoint:
  https://id.example.test/oauth2/introspect

Resource Server client_id:
  orders-api-introspector

Resource Server client_secret:
  <SECRET_LUU_TRONG_SECRET_MANAGER>

Permitted resource/audience:
  orders-api
~~~

Một JWT/opaque access token của user có thể gắn `client_id=web-storefront`, nhưng RS vẫn sử dụng **orders-api-introspector** khi gọi introspection.

Không được nhầm:

- `client_id` trong introspection credential: identity của **Resource Server** khi giao tiếp với AS.
- `client_id` trong introspection response: có thể là identity của **OAuth client đã được cấp token**.
- `sub` trong introspection response: chủ thể của access token, không phải RS introspection client.
- `scope`: phạm vi token được ủy quyền, không phải quyền của RS đối với introspection endpoint.

Credential của RS nên có **least privilege**. Nếu AS hỗ trợ giới hạn resource, dùng per-API introspection credential và chỉ cho phép RS hỏi token dành cho chính nó.

## 4. HTTP Basic: không chỉ là Base64

Một header HTTP Basic có cú pháp:

~~~http
Authorization: Basic <BASE64_OF_USERNAME_COLON_PASSWORD>
~~~

Base64 **không bảo mật**; người đọc được header có thể giải mã username/password. Vì vậy HTTPS với xác minh server certificate và hostname là tối quan trọng.

### 4.1. OAuth client-secret Basic có quy tắc encoding riêng

**RFC 6749 `2.3.1** quy định khi OAuth client dùng HTTP Basic, `client_id` và `client_secret` được mã hóa theo `application/x-www-form-urlencoded` trước khi dùng làm username/password của Basic.

Điều này quan trọng với:

- Dấu cách.
- Dấu `:` và `+`.
- Ký tự `&`, `=`, `%`.
- Ký tự Unicode/non-ASCII.

Nếu tự ghép:

~~~java
String basic = Base64.getEncoder().encodeToString(
    (clientId + ":" + clientSecret).getBytes(StandardCharsets.UTF_8)
);
~~~

thì cách trên **không tự triển khai chính xác OAuth form encoding trong mọi trường hợp**.

Khi dùng `SpringReactiveOpaqueTokenIntrospector` builder, truyền **giá trị chưa encode** vào `clientId(...)` và `clientSecret(...)`; builder xử lý encoding. Nếu tự tạo `WebClient`, phải đảm bảo HTTP Basic được dựng theo yêu cầu của OAuth/AS.

### 4.2. Không truyền secret vào query string

Không gửi:

~~~http
GET /oauth2/introspect?token=T&client_secret=...
~~~

RFC 7662 dùng POST form body. Đưa secret hoặc access token vào URL query có thể làm lộ qua access logs, browser history, proxies, CDN hoặc tracing. Ngay cả form body cũng cần redaction ở logs/APM.

### 4.3. Không xem Basic secret là service Bearer access token

Sai:

~~~http
Authorization: Bearer <RS_CLIENT_SECRET>
~~~

Một client secret không phải OAuth access token. Nếu AS yêu cầu Bearer để authorize introspection, RS phải dùng một **service access token riêng** có audience/scope phù hợp, không biến client secret thành Bearer bằng cách đổi prefix.

## 5. Cấu hình mặc định trong Spring Boot WebFlux

### 5.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` đều có mặt, Spring Boot có thể ưu tiên Servlet application type. Hãy kiểm tra web stack thật của ứng dụng; mục tiêu bài này là WebFlux.

### 5.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Đây là ba properties quan trọng nhất cho opaque introspection mặc định. `OAUTH_INTROSPECTION_CLIENT_SECRET` được inject từ runtime/secret manager, **không phải plaintext secret commit vào Git**.

Trong Spring Boot khi không có introspector bean khác ghi đè, các properties này có thể được dùng để tạo **`ReactiveOpaqueTokenIntrospector`** mặc định cho Resource Server.

### 5.3. WebFlux SecurityWebFilterChain

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

`oauth2ResourceServer(...opaqueToken(...))` bật Bearer authentication qua introspection. `hasAuthority("SCOPE_orders.read")` kiểm tra scope sau khi token đã active và Spring Security tạo authorities.

**`anyExchange().authenticated()` không thay thế quyền object-level**. Ngay cả token có `orders.read` cũng không tự cho phép đọc order thuộc tenant khác.

### 5.4. Cấu hình nào không cần tự tạo WebClient?

Nếu AS dùng Basic client credentials bình thường, Boot properties và `opaqueToken(Customizer.withDefaults())` thường đủ. Không nên viết custom HTTP client chỉ để làm lại chức năng sẵn có, vì dễ:

- Quên gắn Basic header.
- Để credential ở sai request.
- Bỏ TLS verification.
- Làm lộ token trong request logs.
- Mất error handling của Spring Security.

## 6. Cấu hình tường minh bằng SpringReactiveOpaqueTokenIntrospector

### 6.1. Reactive interface

Trong WebFlux, interface là:

~~~java
org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector
~~~

Nó có method ý tưởng:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
~~~

Không nhầm với Servlet `OpaqueTokenIntrospector` trả kết quả đồng bộ. Khi viết custom reactive introspection, không gọi `block()` trong request pipeline.

### 6.2. Builder với client ID/secret

Spring Security 6.5+ hỗ trợ builder:

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class ReactiveIntrospectionConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String id,
            @Value("${app.security.introspection.client-secret}") String secret) {

        return SpringReactiveOpaqueTokenIntrospector
            .withIntrospectionUri(uri)
            .clientId(id)
            .clientSecret(secret)
            .build();
    }
}
~~~

YAML custom properties:

~~~yaml
app:
  security:
    introspection:
      uri: https://id.example.test/oauth2/introspect
      client-id: orders-api-introspector
      client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

**Truyền raw ID và raw secret cho builder**, không URL-encode trước vì builder đã có cơ chế encoding riêng.

Constructor cũ `new SpringReactiveOpaqueTokenIntrospector(uri, id, secret)` được đánh dấu deprecated từ Spring Security 6.5. Với phiên bản hỗ trợ builder, ưu tiên builder. Nếu đang dùng version cũ, đọc API của version tương ứng.

### 6.3. Bean tự khai báo thay thế default

Nếu ứng dụng tự khai báo `ReactiveOpaqueTokenIntrospector` bean, Boot auto-configuration thường nhường chỗ. Vì thế chính bean custom phải giữ:

- Đúng URI và HTTPS endpoint.
- Đúng credential/authentication mechanism.
- Đúng HTTP method/form body.
- Kiểm tra `active` và response contract.
- Error handling/fail-closed.
- Timeout và transport policy.

Đừng tạo custom bean có kết quả `Mono.just(principal)` cho mọi token chỉ để bỏ remote introspection: đó là **authentication bypass**.

### 6.4. Cấu hình qua ServerHttpSecurity DSL

Thay vì bean, có thể khai báo trực tiếp:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        @Value("${app.security.introspection.uri}") String uri,
        @Value("${app.security.introspection.client-id}") String id,
        @Value("${app.security.introspection.client-secret}") String secret) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque
                .introspectionUri(uri)
                .introspectionClientCredentials(id, secret)
            )
        )
        .build();
}
~~~

Đây là **một phương án thay thế** cho Boot properties hoặc custom bean. Không cấu hình secret khác nhau ở nhiều nơi rồi mặc định chúng được hợp nhất theo ý muốn.

## 7. Custom WebClient: phải tự cấu hình Basic authentication

### 7.1. Tại sao cần custom WebClient?

Các nhu cầu thường gặp:

- Connect/read/response timeout theo SLO.
- Proxy outbound hoặc egress policy.
- Connection pooling và concurrency limits.
- mTLS client certificate/truststore.
- HTTP tracing với redaction.
- Một client authentication scheme không phải mặc định.

Spring Security có constructor `SpringReactiveOpaqueTokenIntrospector(String, WebClient)` ở các phiên bản hỗ trợ. Khi truyền WebClient riêng, **WebClient đó phải tự cung cấp cách xác thực với introspection endpoint**; không được giả định Boot tự thêm Basic client ID/secret.

### 7.2. Ví dụ WebClient HTTP Basic với Reactor Netty timeout

~~~java
package com.example.orders.security;

import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class IntrospectionHttpClientConfig {

    @Bean
    ReactiveOpaqueTokenIntrospector introspector(
            @Value("${app.security.introspection.uri}") String uri,
            @Value("${app.security.introspection.client-id}") String id,
            @Value("${app.security.introspection.client-secret}") String secret) {

        HttpClient transport = HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
            .responseTimeout(Duration.ofSeconds(2));

        // RFC 6749 client_secret_basic: form-encode values first.
        String basicUsername = URLEncoder.encode(
            id, StandardCharsets.UTF_8);
        String basicPassword = URLEncoder.encode(
            secret, StandardCharsets.UTF_8);

        WebClient client = WebClient.builder()
            .clientConnector(
                new ReactorClientHttpConnector(transport))
            .defaultHeaders(headers -> headers.setBasicAuth(
                basicUsername,
                basicPassword
            ))
            .build();

        return new SpringReactiveOpaqueTokenIntrospector(
            uri, client);
    }
}
~~~

Hai timeout là **giá trị minh họa**, không phải khuyến nghị cho mọi hệ thống. Không cấu hình Basic credentials ở một WebClient dùng chung cho các host khác, vì `defaultHeaders(...)` có thể gửi cùng credentials tới nơi không mong muốn.

Sự khác biệt encoding rất quan trọng:

- Với **builder `withIntrospectionUri(...).clientId(...).clientSecret(...)`**, truyền **raw values**.
- Với **custom `WebClient#setBasicAuth`** ở ví dụ trên, mã chủ động áp `URLEncoder` trước để đáp ứng quy tắc OAuth `client_secret_basic`.
- Không URL-encode trước rồi dùng builder, gây double encoding.
- Không tự cắt chuỗi Basic ở dấu hai chấm trong secret theo logic ứng dụng; dùng một thư viện HTTP phù hợp.

### 7.3. Không gửi Basic credential đến URL không tin cậy

Một WebClient với Basic default header **không được** lấy endpoint URL từ request:

~~~java
// Sai ý tưởng: URI do caller tự điều khiển.
String uri = request.queryParams().getFirst("introspectUrl");
~~~

Nếu code dùng URI đó cùng WebClient mang Basic credentials, attacker có thể gây **SSRF và credential exfiltration**.

Đúng hơn là sử dụng endpoint **được quản trị ở server-side**, qua allowlist host/issuer. Nếu AS trả redirect sang host khác, không tự động follow redirect rồi gửi lại Basic credentials nếu chưa đánh giá trust policy.

## 8. Các phương thức xác thực introspection khác

### 8.1. `client_secret_basic`

~~~http
Authorization: Basic <RS_CLIENT_ID_AND_SECRET>
Content-Type: application/x-www-form-urlencoded

token=<CALLER_ACCESS_TOKEN>
~~~

Đây là cơ chế phổ biến, được hỗ trợ tốt qua Spring Boot properties/builder. Secret phải được giữ ở backend và truyền qua HTTPS.

### 8.2. `client_secret_post`

Một số AS yêu cầu truyền client credentials trong body:

~~~http
POST /oauth2/introspect HTTP/1.1
Content-Type: application/x-www-form-urlencoded

token=<CALLER_ACCESS_TOKEN>&client_id=<RS_ID>&client_secret=<RS_SECRET>
~~~

Đây **không** phải cách mặc định mà ta có thể tự giả định từ properties `client-id`/`client-secret`. Cần custom integration đúng hợp đồng AS.

Rủi ro: client secret trong form body dễ bị lộ qua request body logging/APM. Không gửi thêm Basic credential cùng lúc trừ khi profile yêu cầu rõ.

### 8.3. Service Bearer token dành riêng cho introspection

RFC 7662 cho phép AS bảo vệ endpoint bằng một OAuth access token dành cho RS:

~~~http
POST /oauth2/introspect HTTP/1.1
Authorization: Bearer <RS_INTROSPECTION_SERVICE_TOKEN>
Content-Type: application/x-www-form-urlencoded

token=<CALLER_ACCESS_TOKEN>
~~~

Hai token này **khác nhau**. RS có thể cần một OAuth2 client-credentials flow riêng để lấy service token, cache theo `exp` và rotate credential. Với WebFlux, quá trình lấy token nên dùng reactive OAuth2 Client/WebClient, không `block()` trên event loop.

Không chuyển incoming Bearer token vào outbound `Authorization` theo kiểu blind forwarding.

### 8.4. mTLS client authentication

Với mTLS, AS có thể yêu cầu RS cung cấp **client certificate** ở TLS handshake. RS cần:

- Private key và client certificate được AS đăng ký/cho phép.
- Truststore xác minh certificate của AS.
- Hostname verification và SNI đúng.
- Certificate rotation và cảnh báo expiry.
- Cấu hình HTTP client/egress proxy phù hợp.

**RFC 8705** mô tả OAuth 2.0 mutual-TLS client authentication và certificate-bound access tokens. Không tự giả định mọi introspection endpoint hỗ trợ mTLS chỉ vì một endpoint khác của AS hỗ trợ.

mTLS xác thực RS **không** thay thế token `active`/scope/audience checks.

### 8.5. `private_key_jwt`

Một số AS chấp nhận JWT assertion do RS ký:

~~~text
client_assertion_type =
  urn:ietf:params:oauth:client-assertion-type:jwt-bearer

client_assertion =
  <JWT_SIGNED_BY_RS_PRIVATE_KEY>
~~~

Assertion có thể chứa:

~~~json
{
  "iss": "orders-api-introspector",
  "sub": "orders-api-introspector",
  "aud": "https://id.example.test/oauth2/introspect",
  "iat": 1900000000,
  "exp": 1900000060,
  "jti": "unique-assertion-id"
}
~~~

Đây chỉ là payload minh họa, không có chữ ký thật. AS phải kiểm tra client identity, signature, audience, thời hạn, replay protection và key registration. **`introspectionClientCredentials(id, secret)` không mặc nhiên tạo private-key JWT assertion**. Cần integration riêng đúng AS.

### 8.6. So sánh

| Cơ chế | Credential của RS | Ở đâu | Cấu hình thông thường |
|---|---|---|---|
| `client_secret_basic` | ID + secret | Basic header | Spring Boot properties/builder |
| `client_secret_post` | ID + secret | Form body | Custom integration theo AS |
| Service Bearer token | RS access token | Authorization Bearer | Reactive OAuth2 Client + custom introspector |
| mTLS | Client certificate/key | TLS handshake | HTTP client SSL configuration |
| `private_key_jwt` | Private key ký assertion | Form fields | JWT signing/custom integration |
| Không có xác thực RS | Không có | Không | Không đáp ứng mục tiêu bảo vệ endpoint RFC 7662 |

## 9. Bí mật introspection không được đưa lên frontend

Một SPA/browser OAuth client thường là **public client** và không thể lưu client secret an toàn trong JavaScript bundle. Không đưa introspection secret vào `NEXT_PUBLIC_*`, `VITE_*` hoặc HTML.

Đường đi an toàn:

~~~text
Browser SPA
    | Bearer user access token
    v
Orders Resource Server
    | Basic orders-api-introspector credential
    v
Authorization Server
~~~

Nếu một ứng dụng Spring vừa là OAuth2 Login client vừa là Resource Server, hai cấu hình có thể khác nhau:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          browser-login:
            client-id: web-login-client
            client-secret: ${WEB_LOGIN_CLIENT_SECRET}

      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Ví dụ chỉ nhằm phân biệt credentials, không phải cấu hình OIDC login hoàn chỉnh. Không chia sẻ một secret giữa frontend, OAuth login và introspection chỉ để giảm số lượng cấu hình.

## 10. Secret management và vòng đời rotation

### 10.1. Lưu và tiêm credentials

Ưu tiên:

- Secret manager/Vault hoặc managed secret service.
- Environment variables được inject từ hệ điều hành/orchestrator với RBAC phù hợp.
- Kubernetes Secret kèm phân quyền và encryption at rest theo chính sách.
- Keystore/HSM cho private keys và mTLS credentials.

Tránh hard-code trong Java/YAML commit lên Git, command-line arguments, logs, screenshots, metrics labels hoặc crash reports.

Biến môi trường không mặc nhiên hoàn toàn kín: admin/process inspection hoặc crash dump có thể đọc được. Cần thiết kế permission và lifecycle phù hợp.

### 10.2. Secret rotation

Một quy trình thực tế:

1. AS phát hành credential mới và có một khoảng overlap có giới hạn nếu được hỗ trợ.
2. Cập nhật secret manager.
3. Rollout/refresh RS instances để dùng credential mới.
4. Kiểm tra HTTP introspection calls thành công bằng test/staging và metrics.
5. Thu hồi credential cũ sau khi xác nhận toàn bộ replicas đã đổi.
6. Theo dõi 401 từ AS, không log secret mới/cũ.

Nhiều `@Value` và WebClient default headers được khởi tạo **một lần lúc startup**. Chỉ thay secret ở secret manager chưa đảm bảo instance đang chạy tự đổi Basic header. Có thể cần rolling restart hoặc một credential provider có khả năng refresh rõ ràng.

### 10.3. Least privilege per Resource Server

Không dùng một introspection credential chung cho mọi microservice nếu AS cho phép phân quyền riêng:

~~~text
orders-api-introspector  -> orders-api tokens
billing-api-introspector -> billing-api tokens
users-api-introspector   -> users-api tokens
~~~

Một service bị compromise không nên có quyền introspect token của tất cả services. AS có thể gắn quyền/metadata cho RS client, trong khi RS vẫn phải kiểm tra audience và local authorization theo hợp đồng.

## 11. Multi-issuer: không chuyển credentials sai nơi

Một hệ thống có thể tin hai Authorization Servers:

~~~text
AS-A:
  https://as-a.example.test/introspect
  client: orders-a / secret-a

AS-B:
  https://as-b.example.test/introspect
  client: orders-b / secret-b
~~~

**Không gửi `secret-a` tới AS-B**, không gửi user token của tenant B tới AS-A nếu không có hợp đồng. Thiết kế an toàn cần một registry trusted:

~~~mermaid
flowchart TD
    A["Request vào API"] --> B["Trusted route/tenant mapping"]
    B --> C{"AS nào đã được allowlist?"}
    C --> D["AS-A endpoint + credential A"]
    C --> E["AS-B endpoint + credential B"]
    D --> F["Reactive introspector A"]
    E --> G["Reactive introspector B"]
    F --> H["Validated principal"]
    G --> H
    H --> I["Scope + tenant/ACL authorization"]
~~~

Không dùng `iss` **chưa xác minh** hoặc một query/header do caller gửi làm URL introspection tùy ý. Với opaque token, không thể mặc định parse token để biết issuer đáng tin.

Có thể dùng nhiều `SecurityWebFilterChain` với matcher/`@Order` theo API routes, hoặc composite introspector được quản trị. Phải kiểm tra chain đầu tiên match, không để chain rộng lấy nhầm credentials.

## 12. Lỗi 401 của AS khác lỗi 401 trả cho API client

Có hai HTTP exchanges:

~~~text
Exchange 1:
  Caller -> Resource Server API
  Authorization: Bearer <USER_ACCESS_TOKEN>

Exchange 2:
  Resource Server -> AS introspection
  Authorization: Basic <RS_CREDENTIAL>
  Body: token=<USER_ACCESS_TOKEN>
~~~

| Kết quả từ AS | Kết luận đúng | Không được kết luận |
|---|---|---|
| 200, `active:true` | Token được AS xác nhận active lúc hỏi | Caller được mọi quyền |
| 200, `active:false` | Token inactive | Credential RS sai |
| 401 từ introspection endpoint | RS client auth có thể sai hoặc thiếu | User token chắc chắn expired |
| 403 từ introspection endpoint | RS có thể thiếu quyền introspect | User thiếu OAuth scope tại API |
| 429 | AS rate limit | Token đã bị revoke |
| 5xx | AS lỗi hạ tầng | Tự động active=true |
| TLS/connect/read timeout | Không có kết quả tin cậy | Có thể bỏ qua introspection |

Nếu client secret sai, mọi requests có Bearer token đều có thể thất bại. **Yêu cầu người dùng đăng nhập lại không giải quyết lỗi rotation của credential Resource Server.**

Khi AS không trả lời, RS phải **fail closed** — không tạo principal authenticated từ sự suy đoán. HTTP status cuối cho caller phụ thuộc exception handling; không tự đổi mọi lỗi network thành `invalid_token` và buộc client refresh token vô hạn.

### 12.1. Một request active nhưng thiếu scope

Nếu introspection trả:

~~~json
{
  "active": true,
  "scope": "profile"
}
~~~

mà URL rule yêu cầu `SCOPE_orders.read`, RS authentication có thể thành công nhưng **authorization thường trả 403**. Đây là lỗi khác với RS Basic credential bị AS từ chối.

### 12.2. Retry có kiểm soát

Không retry `active:false` — đó là quyết định token. Không retry 401 client auth vô hạn — secret có thể sai.

Với 429/5xx/timeout, có thể dùng:

- Connect/response timeout.
- Retry budget và exponential backoff/jitter.
- Circuit breaker/bulkhead.
- Outbound rate limit.
- Cảnh báo AS availability.

**Không fail open** chỉ để giữ API trả 200 khi AS outage. Opaque introspection là một dependency trên đường authentication.

## 13. TLS, proxy và rủi ro leak credentials

### 13.1. Bảo vệ hai bí mật trong một request

Outbound introspection chứa:

1. RS credential trong Basic header/service token/client assertion hoặc mTLS handshake.
2. Caller access token trong form field `token`.

Vì thế cần HTTPS, server certificate verification, trusted host allowlist, egress restrictions và log redaction. Không tắt SSL verification vì lỗi truststore.

### 13.2. Redirect nguy hiểm

Một WebClient có Basic header mặc định không nên tự động follow redirect sang host khác và mang theo credentials. Với AS endpoint đổi URL, cập nhật cấu hình qua quy trình được phê duyệt; không tin một redirect do network/AS giả mạo.

### 13.3. Không log HTTP wire data

Tránh log:

~~~text
Authorization: Basic Zm9vOmJhcg==
Authorization: Bearer <USER_TOKEN>
token=<USER_TOKEN>
client_secret=<SECRET>
~~~

Basic Base64 có thể giải mã. APM/tracing/logging cần redaction ở request header và form body, không chỉ JSON response.

Thay bằng metrics:

~~~text
component=reactive-introspection
asHost=id.example.test
result=client_auth_failed
asHttpStatus=401
latencyMs=48
requestId=req-f71a
credentialVersion=v2
~~~

`credentialVersion` là một identifier không nhạy cảm do hệ thống quản lý nếu có; không dùng secret thực làm identifier.

## 14. Availability, latency và cache

### 14.1. Introspection tạo một network dependency

Không cache, mỗi HTTP Bearer request có thể làm một remote POST. Điều này tăng:

- Request latency p50/p95/p99.
- Tải Authorization Server.
- Sự phụ thuộc vào DNS, TLS, proxy và AS database.
- Số outbound connections và nguy cơ token-spray DoS.

Resource Server nên đặt timeout phù hợp SLO, có giới hạn concurrency và theo dõi lỗi theo nguyên nhân.

### 14.2. Cache không giải quyết lỗi secret

Một positive cache có thể giúp những token đã từng được introspect tiếp tục được dùng trong TTL, nhưng cache misses vẫn cần credential RS đúng. Sau credential rotation mà RS chưa cập nhật, hệ thống có thể có hành vi bất nhất giữa cache hits và misses.

Cache `active:true` còn khiến revoke detection chậm hơn. Không dùng stale positive result vô thời hạn khi AS bị outage. TTL phải gắn với security contract, token expiry và revocation requirements.

### 14.3. Không nhầm JWKS cache với introspection

JWKS cache chứa public signing keys để verify JWT offline. Introspection cache lưu quyết định active/principal. **JWKS không giúp RS xác thực với introspection endpoint** và không làm client secret trở nên không cần thiết.

## 15. Kiểm thử outbound Basic authentication

Một test WebFlux URL authorization dùng `mockOpaqueToken()` **không chứng minh** RS đã thực hiện HTTP POST hoặc gửi Basic credential đúng. Muốn kiểm tra outbound authentication, hãy dùng HTTP test server.

### 15.1. Dependencies test

Ví dụ với MockWebServer và Reactor Test:

~~~groovy
dependencies {
    testImplementation 'com.squareup.okhttp3:mockwebserver'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Nếu dependency management không cung cấp version, cấu hình một version tương thích. Test server chỉ chạy local; **không dùng HTTP introspection ra Internet trong production**.

### 15.2. Test request outbound

~~~java
package com.example.orders.security;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;

import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class IntrospectionClientAuthTest {

    @Test
    void sendsBasicClientCredentialsAndTokenInFormBody()
            throws Exception {

        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(
                new MockResponse()
                    .setResponseCode(200)
                    .setHeader("Content-Type", "application/json")
                    .setBody("""
                        {
                          "active": true,
                          "sub": "test-user",
                          "scope": "orders.read"
                        }
                        """)
            );

            ReactiveOpaqueTokenIntrospector introspector =
                SpringReactiveOpaqueTokenIntrospector
                    .withIntrospectionUri(
                        server.url("/introspect").toString())
                    .clientId("test-rs")
                    .clientSecret("test-secret")
                    .build();

            StepVerifier.create(
                introspector.introspect("test-access-token"))
                .assertNext(principal ->
                    assertThat(principal.getName())
                        .isEqualTo("test-user"))
                .verifyComplete();

            RecordedRequest request = server.takeRequest();

            assertThat(request.getMethod()).isEqualTo("POST");
            assertThat(request.getPath()).isEqualTo("/introspect");

            String authorization =
                request.getHeader("Authorization");

            assertThat(authorization).startsWith("Basic ");

            String decoded = new String(
                Base64.getDecoder().decode(
                    authorization.substring(6)),
                StandardCharsets.UTF_8
            );

            assertThat(decoded).isEqualTo("test-rs:test-secret");
            assertThat(request.getBody().readUtf8())
                .contains("token=test-access-token");
        }
    }
}
~~~

Đây là **giá trị test**, không phải credentials production. Khi thực sự chạy, dùng JUnit/MockWebServer versions tương thích. Với client ID/secret chứa ký tự đặc biệt, phải thêm test OAuth `application/x-www-form-urlencoded` encoding thay vì chỉ so test credentials đơn giản.

### 15.3. Test thêm trường hợp thất bại

| Test case | Kỳ vọng |
|---|---|
| AS trả `200 active:true` | Principal được tạo |
| AS trả `200 active:false` | Không tạo authenticated principal |
| AS trả 401 do Basic sai | Phát hiện RS client-auth failure |
| AS trả 403 | Phát hiện RS thiếu quyền introspection |
| AS trả 429 | Không retry vô hạn |
| AS trả 5xx | Fail closed và telemetry infrastructure |
| Timeout / TLS failure | Không tạo principal |
| Client secret có `:`, `+`, Unicode | OAuth Basic encoding đúng |
| Proxy strip Authorization | Test phát hiện thiếu Basic |
| Introspection URI bị đổi sang host khác | Không gửi secret đến host không tin cậy |
| Caller token hợp lệ nhưng thiếu scope | URL authorization deny, thường 403 |
| Credential rotate | RS dùng credential version đúng sau rollout |

Không dùng `active:false` làm bằng chứng RS Basic sai; nó là một quyết định token, không phải lỗi client authentication.

## 16. WebTestClient mockOpaqueToken để test quyền, không test credential

Spring Security Test có reactive helper:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

Với `WebTestClient` đã tích hợp Spring Security test support:

~~~java
client.mutateWith(
        mockOpaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
~~~

Helper này tạo `BearerTokenAuthentication` thử nghiệm, bỏ qua remote introspection. Nó phù hợp để kiểm tra HTTP authorization theo scope, nhưng **không xác minh**:

- Introspection client ID/secret có đúng không.
- Authorization header outbound là Basic hay Bearer.
- HTTP POST `token` form body có đúng không.
- AS trả `active:false` hoặc 401 thì sao.
- TLS, rotation, timeout và permission của introspection client.

Nên có **hai lớp test riêng**: test HTTP client/introspector bằng mock AS, và test URL/method authorization bằng WebTestClient.

## 17. Runbook: phân biệt lỗi client credentials với lỗi access token

### 17.1. Hàng loạt request thất bại sau secret rotation

Kiểm tra:

1. AS đã rotate/revoke secret cũ chưa?
2. Secret manager đang cung cấp credential version nào?
3. RS replicas đã restart/refresh nếu bean đọc `@Value` lúc startup chưa?
4. AS có thay client auth method từ Basic sang mTLS/private-key JWT không?
5. Outbound header có đúng Basic và OAuth form encoding không?
6. Client ID có thuộc đúng AS realm/tenant/resource không?
7. Proxy/egress có strip hoặc đổi `Authorization` không?
8. URI/host/TLS certificate có thay đổi không?

Không đề nghị toàn bộ users login lại khi gốc lỗi nằm ở RS credential.

### 17.2. AS trả active=false dù token vừa phát hành

Kiểm tra token đang introspect có đúng access token không, token có dành cho RS không, AS node có trạng thái token đúng chưa, grant có bị disable không và RS credential có quyền introspect token thuộc resource đó không.

Không hard-code `active=true` để làm API chạy tạm.

### 17.3. Tăng timeout và rate limit

Kiểm tra introspection RPS, tail latency, AS availability, HTTP client connection pooling, retries, token-spray và cache policy. Không fail open hoặc retry vô hạn.

### 17.4. Lỗi SSL/mTLS handshake

Kiểm tra CA trust, SAN/hostname, certificate expiry, SNI, client keystore/keypair, quyền đọc file và egress proxy. **Không tắt certificate verification** để chữa lỗi.

## 18. Những nhầm lẫn cần tránh

### “Incoming Bearer token cũng xác thực RS với AS”

Không. Với Basic introspection, token caller nằm ở form field `token`; RS dùng client credential riêng ở outbound header.

### “Base64 Basic đã là mã hóa bí mật”

Không. Base64 có thể giải mã; phải dùng TLS và bảo vệ credential trong logs.

### “Spring Boot client ID/secret luôn đủ cho mọi AS”

Không. Các cơ chế `client_secret_post`, mTLS, Bearer service token và `private_key_jwt` có thể cần custom integration đúng AS.

### “Custom WebClient tự lấy client secret từ properties”

Không chắc. Khi truyền WebClient riêng vào introspector, phải cấu hình chính HTTP client đó.

### “Chỉ cần HTTP 200 từ AS là cho phép request”

Không. Phải có `active:true` và còn cần scope, audience/resource, local ACL.

### “AS trả 401 thì user token hết hạn”

Không nhất thiết. Đó có thể là lỗi Basic credential của RS.

### “Đổi secret ở Vault là mọi instance tự sử dụng secret mới”

Không chắc. WebClient và Bean có thể giữ secret đã đọc từ startup; cần chiến lược refresh/rollout.

### “Dùng một credential cho mọi issuer là tiết kiệm”

Rủi ro lớn về privilege và credential leakage. Per-issuer endpoint/credential mapping phải được allowlist.

### “Có mTLS thì không cần token authorization”

Sai. mTLS xác thực Resource Server với AS, token vẫn phải active và được phép truy cập resource.

### “Test mockOpaqueToken chứng minh Basic đã đúng”

Không. Nó chỉ mô phỏng Authentication; cần mock HTTP server để kiểm tra Basic/form.

### “Timeout có thể được giải quyết bằng cách tin mọi token”

Không. Không có quyết định tin cậy thì fail closed; cần cải thiện availability và observability của AS.

## 19. Checklist triển khai

1. Endpoint introspection có **HTTPS** và thuộc trusted host allowlist.
2. RS dùng **credential riêng**, không dùng token của caller làm client authentication.
3. Cơ chế AS yêu cầu đã được xác nhận: Basic, post, mTLS, service Bearer hay JWT assertion.
4. Với Basic, client ID/secret được encode theo OAuth contract, không double-encode.
5. Secret lấy từ secret manager/environment được bảo vệ, không commit vào Git/frontend.
6. Custom WebClient được cấu hình client authentication đúng và chỉ dùng cho AS tin cậy.
7. Không follow redirects tùy tiện với Basic credential.
8. AS giới hạn quyền introspection của RS theo resource/tenant nếu hỗ trợ.
9. Không nhầm HTTP `401/403` từ introspection endpoint với `active:false`.
10. AS outage/timeout/TLS errors **không** dẫn tới authenticated principal.
11. Có rotation runbook, alerts và cơ chế refresh/restart rõ ràng.
12. Logs/metrics không chứa Basic header, bearer token hoặc form body.
13. Có test outbound POST/Basic/form và error responses bằng mock AS.
14. Có test authorization độc lập bằng `WebTestClient.mockOpaqueToken()`.
15. Với nhiều AS, mỗi introspection endpoint có credential đúng và matcher/registry trusted.

## 20. Tổng kết

**Resource Server cần chứng minh danh tính của chính nó khi hỏi Authorization Server về một token**. Hãy coi đây là kênh machine-to-machine riêng:

~~~text
Client -> Resource Server:
    Authorization: Bearer <CALLER_TOKEN>

Resource Server -> Introspection endpoint:
    Authorization: Basic <RESOURCE_SERVER_CREDENTIAL>
    Form body: token=<CALLER_TOKEN>

Authorization Server:
    Xác thực Resource Server
    Kiểm tra quyền introspection
    Trả active + attributes của token

Resource Server:
    Chỉ tạo Authentication khi token hợp lệ
    Kiểm tra scope + business authorization
~~~

Trong Spring WebFlux, lựa chọn đơn giản nhất với AS hỗ trợ Basic là **Boot `opaquetoken.introspection-uri/client-id/client-secret`** hoặc **`SpringReactiveOpaqueTokenIntrospector` builder**. Chỉ tùy chỉnh WebClient khi cần thay transport/credentials profile. Khi tùy chỉnh, giữ HTTPS, Basic encoding, secret isolation, fail-closed và kiểm thử outbound request.

### Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6749 — OAuth 2.0 Authorization Framework, `2.3.1 Client Password](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication](https://www.rfc-editor.org/rfc/rfc7523)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication](https://www.rfc-editor.org/rfc/rfc8705)
- [Spring Security Reference — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Boot Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security Reference — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)

