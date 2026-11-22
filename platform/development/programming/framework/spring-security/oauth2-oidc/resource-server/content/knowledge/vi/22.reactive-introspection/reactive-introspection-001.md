# ReactiveOpaqueTokenIntrospector và hợp đồng kết quả Mono

Trong **Spring Security OAuth 2.0/OIDC Resource Server chạy trên WebFlux**, API có thể xác thực một Bearer access token bằng cách gọi **token introspection endpoint** của Authorization Server (AS). Cách này đặc biệt hữu ích khi AS phát hành **opaque access token**: chuỗi token không cần có cấu trúc mà Resource Server tự giải mã được; thay vào đó, AS xác nhận trạng thái và metadata của token.

Ở Servlet, điểm mở rộng quen thuộc là `OpaqueTokenIntrospector`, trả trực tiếp `OAuth2AuthenticatedPrincipal`. Trong **WebFlux**, interface tương ứng là **`ReactiveOpaqueTokenIntrospector`**, trả một **`Mono<OAuth2AuthenticatedPrincipal>`**. Sự khác biệt không chỉ là thêm `Mono` vào chữ ký: **giá trị thành công, kết quả rỗng, lỗi bất đồng bộ, thời điểm subscription, cancellation, retry và việc tránh blocking** đều ảnh hưởng trực tiếp đến an toàn của cơ chế xác thực.

Hợp đồng cần nhớ ngay từ đầu:

> **Khi token được xác minh hợp lệ, phát ra đúng một `OAuth2AuthenticatedPrincipal` đáng tin; khi không thể xác minh, không được phát ra một principal mang quyền.** Một token không active cần bị từ chối, không được mặc định chuyển thành anonymous có quyền, không được `onErrorResume` thành user “dự phòng”.

Bài này tập trung vào chính interface `ReactiveOpaqueTokenIntrospector` và **hợp đồng `Mono`** của nó trong ngữ cảnh **Introspection phản ứng**: cách Spring Security kết nối nó vào WebFlux, những tín hiệu Reactor có ý nghĩa gì, cách viết decorator kiểm tra audience/issuer và giữ scope, kiểm thử với `StepVerifier`/`WebTestClient`, cũng như những giới hạn về lỗi mạng, hiệu năng và thu hồi token.

## 1. Introspection trong hệ thống Resource Server phản ứng

Một request:

```http
GET /api/orders/ORD-123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer opaque-access-token
```

được xử lý theo ý tưởng:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant API as WebFlux Resource Server
    participant I as ReactiveOpaqueTokenIntrospector
    participant AS as Authorization Server
    C->>API: GET /api/orders/ORD-123 + Bearer token
    API->>I: introspect(token) => Mono<Principal>
    I->>AS: HTTPS POST token introspection
    AS-->>I: active=true, scope, sub, aud, ...
    I-->>API: onNext(OAuth2AuthenticatedPrincipal)
    I-->>API: onComplete()
    API->>API: Authentication / authorities
    API->>API: HTTP authorization + owner/tenant
    API-->>C: 200 nếu mọi điều kiện đều hợp lệ
```

Với token không active hoặc thông tin không đáp ứng hợp đồng, kết quả mong muốn là **lỗi xác thực** trong reactive pipeline, không phải một principal hợp lệ. Sau khi Authentication đã được tạo, Spring Security còn phải kiểm tra **`GrantedAuthority`**, và service vẫn phải kiểm tra quyền trên từng đơn hàng.

### 1.1. Nhiệm vụ của từng thành phần

| Thành phần | Vai trò | Điều không được suy diễn |
|---|---|---|
| `SecurityWebFilterChain` | Cấu hình các WebFlux security filters và luật HTTP | Không tự xác minh token nếu chưa bật resource server |
| `ServerHttpSecurity.oauth2ResourceServer(...opaqueToken...)` | Bật Bearer authentication bằng introspection | Không tự cấp mọi scope cho một token active |
| `OpaqueTokenReactiveAuthenticationManager` | Phối hợp introspector và authentication converter | Không thay thế ownership/tenant checks |
| **`ReactiveOpaqueTokenIntrospector`** | Xác minh token, trả `Mono<OAuth2AuthenticatedPrincipal>` hoặc lỗi | Không phải HTTP controller, không nên tự quyết URL authorization |
| `ReactiveOpaqueTokenAuthenticationConverter` | Chuyển kết quả introspection hợp lệ thành `Mono<Authentication>` | Không nên biến thất bại introspection thành successful auth |
| `OAuth2AuthenticatedPrincipal` | Chứa attributes, authorities, tên principal | Không phải mặc định là user entity trong DB |
| `BearerTokenAuthentication` | Authentication phổ biến của opaque bearer | Không tự cho quyền thao tác trên mọi bản ghi |
| `ReactiveSecurityContextHolder` | Truy cập SecurityContext trong Reactor Context | Không phải cơ chế lưu trạng thái đăng nhập lâu dài |

### 1.2. Introspection không phải JWT decoding

Một WebFlux Resource Server có thể xác thực bằng:

- **JWT path:** `ReactiveJwtDecoder` kiểm tra chữ ký/issuer/audience/thời gian theo cấu hình.
- **Opaque/introspection path:** `ReactiveOpaqueTokenIntrospector` hỏi nguồn tin cậy về trạng thái token và nhận metadata.

Đừng gắn `ReactiveJwtDecoder` vào ứng dụng rồi chờ `ReactiveOpaqueTokenIntrospector` tự chạy, hoặc coi một Bearer string giống JWT là chắc chắn phải decode tại chỗ. Loại access token và đường xác thực phải được thống nhất trong hợp đồng với AS.

Opaque introspection có thể dùng ngay cả khi access token thực tế có định dạng JWT, nếu API chủ đích muốn AS quyết định trạng thái/token revocation. Khi đó Resource Server **vẫn** nên dựa vào kết quả introspection đáng tin, không tự trộn thêm claims chưa xác minh từ token raw.

## 2. Chữ ký chính xác của interface

Theo Javadoc Spring Security, `ReactiveOpaqueTokenIntrospector` là một functional interface với phương thức cốt lõi:

```java
package org.springframework.security.oauth2.server.resource.introspection;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import reactor.core.publisher.Mono;

@FunctionalInterface
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
```

Đây là **chữ ký minh họa** của interface; để sử dụng hãy import interface có sẵn từ Spring Security, không tự định nghĩa lại nó trong dự án.

Giải thích từng thành phần:

- `String token`: chuỗi bearer credential đang được yêu cầu xác minh. Đây là **bí mật**, cần tránh đưa vào log, exception, URL hoặc metrics label.
- `introspect`: biểu diễn thao tác xác minh token và lấy thuộc tính từ AS hoặc nguồn đáng tin có hợp đồng tương đương.
- `Mono<OAuth2AuthenticatedPrincipal>`: publisher tối đa **một** principal hợp lệ, hoặc phát lỗi/hoàn thành rỗng tùy implementation.
- `OAuth2AuthenticatedPrincipal`: tập attributes và authorities do introspector tạo từ **metadata đã được xác minh**.

Interface tồn tại từ **Spring Security 5.2**. Trong những dòng Spring Security hiện đại, implementation chuẩn được dùng là `SpringReactiveOpaqueTokenIntrospector`; các ứng dụng bản cũ có thể dùng `NimbusReactiveOpaqueTokenIntrospector`. Tên constructor, builder và các APIs cấu hình có thể khác nhau theo phiên bản.

### 2.1. Không nhầm với Servlet interface

Servlet:

```java
OpaqueTokenIntrospector introspector;
OAuth2AuthenticatedPrincipal principal =
    introspector.introspect(token);
```

WebFlux:

```java
ReactiveOpaqueTokenIntrospector introspector;
Mono<OAuth2AuthenticatedPrincipal> publisher =
    introspector.introspect(token);
```

Hai interface không hoán đổi trực tiếp được. Nếu gọi introspector **blocking** từ một WebFlux filter, request có thể chặn Netty event-loop hoặc thread xử lý phản ứng. Nếu bắt buộc tích hợp một client blocking, phải đặt nó ở một boundary riêng có scheduler dành cho blocking I/O và đánh giá tải, timeout, cancellation — không biến đó thành thiết kế mặc định.

### 2.2. Không nhầm với authentication converter

Ở đường reactive có một điểm mở rộng khác:

```java
// Chữ ký minh họa của API có từ Spring Security 5.8:
Mono<Authentication> convert(
    String introspectedToken,
    OAuth2AuthenticatedPrincipal authenticatedPrincipal);
```

Đó là `ReactiveOpaqueTokenAuthenticationConverter`. Nó chạy **sau introspection thành công** để tạo Authentication. Nó không xác minh `active` của token thay introspector. Nếu cần tùy chỉnh **cách diễn giải metadata, audience, issuer, authorities của principal**, có thể bọc introspector. Nếu cần thay **loại Authentication** hoặc conversion phức tạp, hãy cân nhắc converter ở phiên bản hỗ trợ.

## 3. Hợp đồng kết quả `Mono`: ba loại tín hiệu

Trong Reactor, `Mono<T>` có thể phát tối đa một `onNext(T)` rồi `onComplete()`, chỉ `onComplete()` mà không có phần tử, hoặc `onError(Throwable)`. Các trường hợp cần xử lý rõ:

| Tín hiệu `Mono` | Ý nghĩa Reactor | Ý nghĩa trong token introspection |
|---|---|---|
| `onNext(principal) → onComplete()` | Một giá trị thành công | **Token đã được xác minh**, principal phải có attributes/authorities theo hợp đồng |
| `onError(exception)` | Publisher thất bại | Token không hợp lệ, phản hồi sai hợp đồng hoặc lỗi hệ thống; **không được cấp Authentication thành công** |
| `onComplete()` không có `onNext` | Publisher rỗng | **Không có bằng chứng token hợp lệ**; custom wrapper nên chuyển thành từ chối rõ ràng nếu hợp đồng yêu cầu kết quả xác minh |
| Không có tín hiệu kết thúc | Publisher treo | Request có thể chiếm tài nguyên; cần timeout và chính sách lỗi |
| `cancel()` từ subscriber | Subscriber không cần kết quả nữa | Không đảm bảo AS chưa nhận token hoặc mọi network side effect được hoàn tác |

**Quan trọng:** interface nói “trả `Mono<OAuth2AuthenticatedPrincipal>`”, nhưng **không nên xem `Mono.empty()` là một cách cấp quyền hoặc một phản hồi introspection đầy đủ**. Nếu token không hợp lệ, dùng error signal thể hiện failure một cách tường minh; nếu delegate bất ngờ trả empty, wrapper bảo mật có thể fail closed bằng `switchIfEmpty(Mono.error(...))`.

### 3.1. Case thành công

```java
OAuth2AuthenticatedPrincipal principal =
    new DefaultOAuth2AuthenticatedPrincipal(
        "user-842",
        Map.of("sub", "user-842"),
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );

Mono<OAuth2AuthenticatedPrincipal> success =
    Mono.just(principal);
```

Đây là **fixture test**. Trong production, `principal` chỉ đáng tin **sau** khi token đã được AS/nguồn introspection xác minh; không lấy một `Map` do HTTP caller gửi rồi bọc bằng `Mono.just` để tạo authentication.

### 3.2. Case token không hợp lệ

```java
Mono<OAuth2AuthenticatedPrincipal> invalid =
    Mono.error(new BadOpaqueTokenException("Token is inactive"));
```

`BadOpaqueTokenException` nằm trong package `org.springframework.security.oauth2.server.resource.introspection`. Nó phù hợp để báo token không được chấp nhận. Không đặt nguyên bearer token trong message:

```java
// Không an toàn: token có thể bị lộ trong log/error response.
return Mono.error(new BadOpaqueTokenException(
    "Invalid token: " + token));
```

### 3.3. Case không có dữ liệu: fail closed

```java
Mono<OAuth2AuthenticatedPrincipal> empty = Mono.empty();
```

Một custom introspector không nên cố ý trả empty để “bỏ qua kiểm tra và cho request chạy tiếp”. Ý nghĩa empty trong một authentication pipeline có thể phụ thuộc `ReactiveAuthenticationManager`/filter đã kết hợp; đó **không phải** một principal đã được xác minh.

Một decorator có thể áp invariant:

```java
return delegate.introspect(token)
    .switchIfEmpty(Mono.error(
        new BadOpaqueTokenException(
            "Introspection returned no authenticated principal")));
```

Khi đó caller nhận lỗi thay vì một kết quả chưa xác định. **Không dùng** `defaultIfEmpty(adminPrincipal)` hoặc `switchIfEmpty(Mono.just(fallbackPrincipal))` nếu principal đó có quyền: thiếu chứng cứ xác thực phải dẫn tới deny.

### 3.4. Case publisher treo

```java
Mono<OAuth2AuthenticatedPrincipal> never = Mono.never();
```

Đây cũng không phải kết quả “token active”. Request có thể chờ mãi nếu không có timeout. Một wrapper có thể giới hạn thời gian:

```java
return delegate.introspect(token)
    .timeout(Duration.ofSeconds(2));
```

Khi timeout, publisher phát lỗi. **Timeout không phải bằng chứng token giả**, nên tránh chuyển mọi timeout thành `BadOpaqueTokenException` với ngữ nghĩa `invalid_token` nếu hệ thống cần phân biệt lỗi AS và token bị từ chối. Bất kể status HTTP cuối cùng được cấu hình ra sao, **không được tự cấp quyền khi không xác minh được**.

## 4. Từ RFC 7662 đến `Mono<OAuth2AuthenticatedPrincipal>`

Introspection chuẩn theo **RFC 7662** thường gửi token bằng POST form body tới AS; Resource Server phải được AS xác thực theo phương thức thỏa thuận, ví dụ client credentials qua Basic authentication:

```http
POST /oauth2/introspect HTTP/1.1
Host: idp.example.com
Authorization: Basic BASE64_RESOURCE_SERVER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

token=OPAQUE_ACCESS_TOKEN
```

Đây là **minh họa giao thức**, không phải URL/credential thật. Trong WebFlux, `SpringReactiveOpaqueTokenIntrospector` thường đảm nhận HTTP call này. Không cần controller tự dựng introspection request trên mọi endpoint.

### 4.1. Response token active

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "client_id": "shop-web",
  "token_type": "Bearer",
  "sub": "user-842",
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a",
  "exp": 1893459600
}
```

Trong RFC 7662:

- `active` là trường **bắt buộc** của response introspection.
- `scope` (nếu trả) là chuỗi chứa danh sách scope **cách nhau bằng dấu cách**.
- `sub`, `client_id`, `aud`, `iss`, `exp`, `iat`, `nbf` có thể xuất hiện tùy AS.
- `tenant_id` là extension giả định, **không phải claim RFC 7662 bắt buộc**.

Resource Server dùng metadata từ AS được tin cậy, không đọc `scope` từ query parameter hoặc header do client tự khai báo.

Khi token được delegate xác minh, principal có thể cung cấp:

```java
principal.getName();
principal.getAttribute("sub");
principal.getAttribute("aud");
principal.getAttribute("iss");
principal.getAuthorities();
```

Theo mặc định, Spring Security opaque resource server ánh xạ scopes thành authorities với prefix `SCOPE_`:

```text
scope trong response:
    "orders.read orders.update"

GrantedAuthority:
    SCOPE_orders.read
    SCOPE_orders.update
```

`SCOPE_` là cách biểu diễn quyền của Spring Security, không phải chữ mà AS bắt buộc đưa vào mỗi tên scope.

### 4.2. Response token không active

```json
{
  "active": false
}
```

AS có thể trả response rất tối giản để không tiết lộ thông tin token không hợp lệ. Với trường hợp này, introspector chuẩn phải **từ chối việc xác thực token**, không emit một principal mang tên `anonymous` với `SCOPE_orders.read`.

Ở pipeline reactive, ta mong đợi tín hiệu failure được truyền cho authentication manager, ví dụ `onError(BadOpaqueTokenException)` hoặc exception phù hợp của implementation. Không nên quy định rằng **mọi** lỗi đều cùng một exception class: lỗi mạng, HTTP 5xx, JSON không hợp lệ, AS không xác thực client và `active=false` không có cùng nguyên nhân.

### 4.3. Scope thiếu không giống token inactive

```json
{
  "active": true,
  "sub": "user-842",
  "aud": ["orders-api"]
}
```

Nếu AS chấp nhận token nhưng không cấp `orders.read`, Authentication có thể được tạo **không có `SCOPE_orders.read`**. Khi đó route yêu cầu `SCOPE_orders.read` sẽ bị từ chối ở **authorization** (thường 403), thay vì token bắt buộc bị xem inactive.

Nếu hợp đồng Resource Server yêu cầu **scope luôn hiện diện**, custom introspector có thể từ chối response thiếu scope sớm. Nhưng đừng âm thầm tự thêm read scope để “khắc phục” thiếu metadata.

### 4.4. `aud`, `iss` và scope là các kiểm tra độc lập

Token:

```json
{
  "active": true,
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read"
}
```

không tự thích hợp cho Orders API. Audience trả lời **token dành cho resource nào**; scope trả lời **phạm vi chức năng được cấp**. Nếu Orders API bắt buộc `aud=orders-api`, cần kiểm tra từ response đáng tin hoặc dựa vào ràng buộc AS đủ mạnh tương đương. Đừng giả định `opaqueToken()` mặc định kiểm tra mọi rule mở rộng về audience/tenant của riêng ứng dụng.

## 5. Cấu hình WebFlux Resource Server dùng introspection

Với Spring Boot 3.x / Spring Security 6.x, dependency:

```groovy
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Không cần thêm `spring-boot-starter-web` chỉ để xác thực opaque token trong WebFlux; thêm Spring MVC vào classpath có thể làm thay đổi lựa chọn web application type tùy cấu hình Boot.

### 5.1. Cấu hình bằng application.yml

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

Giá trị secret phải đến từ secret manager/environment phù hợp, **không** commit client secret thật. Resource Server phải dùng HTTPS, kiểm tra TLS, timeout và chính sách lỗi. Boot có thể auto-config `ReactiveOpaqueTokenIntrospector` khi có đủ dependencies/properties và ứng dụng không tự thay thế bean/DSL.

### 5.2. Cấu hình SecurityWebFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            // Ví dụ API chỉ dùng Bearer header, không dùng browser
            // cookies làm credential cho request ghi.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.delete")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
```

Điểm cần phân biệt:

- WebFlux dùng `ServerHttpSecurity`/`SecurityWebFilterChain`, không phải Servlet `HttpSecurity`/`SecurityFilterChain`.
- `authorizeExchange` chỉ kiểm tra HTTP authorization sau authentication; nó không tự gọi AS.
- `opaqueToken` kích hoạt nhánh reactive introspection; Spring Security dùng `ReactiveOpaqueTokenIntrospector`.
- HTTP rule `SCOPE_orders.read` kiểm tra authorities của Authentication. Nó **không trực tiếp parse chuỗi scope từ request**.
- `anyExchange().denyAll()` từ chối các path/method chưa liệt kê; cần mở/thiết kế CORS preflight, health, actuator và các route khác theo hợp đồng.

Việc tắt CSRF trong mẫu chỉ phù hợp API thuần Bearer header mà browser không tự gắn credential qua cookie. Nếu cùng ứng dụng có browser session/cookie login, phải thiết kế CSRF riêng.

### 5.3. Luồng bên trong Spring Security

```mermaid
flowchart TD
    A["Authorization: Bearer opaque-token"] --> B["WebFlux Bearer authentication filter"]
    B --> C["OpaqueTokenReactiveAuthenticationManager"]
    C --> D["ReactiveOpaqueTokenIntrospector.introspect(token)"]
    D --> E{"Mono signal"}
    E -->|"onNext(principal)"| F["ReactiveOpaqueTokenAuthenticationConverter"]
    F --> G["BearerTokenAuthentication"]
    G --> H["Reactor SecurityContext"]
    H --> I{"HTTP / method authority?"}
    I -->|"Không"| N["403 thường gặp"]
    I -->|"Có"| J["Domain owner/tenant policy"]
    E -->|"onError"| K["Authentication failure"]
    E -->|"empty"| L["Không có principal; fail closed"]
```

Đây là mô hình khái niệm; các exception handlers có thể điều chỉnh status/body và lỗi AS không khả dụng có thể được xử lý khác token invalid. Điều bất biến là **không cấp Authentication thành công khi chưa xác minh được token**.

## 6. Dùng implementation chuẩn `SpringReactiveOpaqueTokenIntrospector`

Ở Spring Security hiện đại, có thể cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
    .SpringReactiveOpaqueTokenIntrospector;

@Bean
ReactiveOpaqueTokenIntrospector baseIntrospector(
        @Value("${app.security.introspection-uri}") String uri,
        @Value("${app.security.introspection-client-id}") String clientId,
        @Value("${app.security.introspection-client-secret}") String secret) {

    return SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(clientId)
        .clientSecret(secret)
        .build();
}
```

Các property ứng dụng:

```yaml
app:
  security:
    introspection-uri: https://idp.example.com/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: "${INTROSPECTION_CLIENT_SECRET}"
```

`SpringReactiveOpaqueTokenIntrospector` có đường builder theo Javadoc hiện đại. Nếu dự án sử dụng phiên bản cũ hơn, hãy xem class/constructor tương ứng; trong những nhánh cũ có `NimbusReactiveOpaqueTokenIntrospector`. Không chọn class theo trí nhớ nếu IDE của dependency hiện tại không có.

### 6.1. Tự cung cấp bean thay đổi auto-configuration

Khi ứng dụng khai báo `ReactiveOpaqueTokenIntrospector` bean hoặc cấu hình `opaqueToken.introspector(...)` tường minh, Spring Boot/DSL có thể **nhường hoặc thay thế** cấu hình mặc định. Vì vậy:

- Không mặc định Boot vẫn áp mọi thuộc tính opaque-token vào bean đã tự tạo.
- Không để nhiều bean introspector không rõ bean nào được sử dụng ở chain.
- Với nhiều chains, kiểm tra chain dành cho `/api/**` có nối đúng introspector.
- Test một Bearer request thật qua WebFlux filter, không chỉ gọi introspector riêng lẻ.

### 6.2. Override bằng DSL tường minh

```java
@Bean
SecurityWebFilterChain apiChain(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector introspector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector)))
        .build();
}
```

Đây là ví dụ nối introspector tường minh, không phải đầy đủ scope rules. Với API có thao tác nhạy cảm, nên thay `authenticated()` bằng các `hasAuthority(...)`/`access(...)` phù hợp và kiểm tra quyền nghiệp vụ ở service.

## 7. Tính lazy và thời điểm subscription

`Mono` là **Publisher**, không phải một promise đã chạy xong ở thời điểm phương thức Java trả về. Nhiều publisher từ Reactor và WebClient có tính **cold**: công việc thực sự thường bắt đầu khi có subscriber.

Ví dụ:

```java
ReactiveOpaqueTokenIntrospector introspector = token ->
    Mono.defer(() -> {
        System.out.println("Introspection subscribed");
        return remoteIntrospection(token);
    });

Mono<OAuth2AuthenticatedPrincipal> result =
    introspector.introspect("opaque-test-token");

// Đến đây chưa nhất thiết đã gọi remoteIntrospection.
// Tác vụ sẽ bắt đầu khi có subscription.
```

`remoteIntrospection` là phương thức minh họa trả `Mono<OAuth2AuthenticatedPrincipal>`. Không dùng `System.out.println` để ghi token trong production. `Mono.defer` giúp trì hoãn việc xây một publisher có tác dụng phụ đến lúc subscribe.

### 7.1. Vì sao `Mono.just(blockingCall())` không biến I/O thành reactive?

Anti-pattern:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    OAuth2AuthenticatedPrincipal principal =
        blockingHttpClient.introspect(token);  // BLOCKING ngay lúc gọi
    return Mono.just(principal);
}
```

`Mono.just(...)` nhận **giá trị đã được tính xong**. HTTP call đã chạy trước khi Mono được trả, có thể chặn Netty event loop. Tương tự:

```java
return Mono.just(blockingHttpClient.introspect(token));
```

vẫn là blocking.

Ưu tiên `SpringReactiveOpaqueTokenIntrospector` với HTTP client phản ứng. Nếu buộc dùng một client blocking không có lựa chọn thay thế, cần cô lập:

```java
return Mono.fromCallable(() -> blockingHttpClient.introspect(token))
    .subscribeOn(Schedulers.boundedElastic());
```

`Schedulers.boundedElastic()` chỉ giúp **không chiếm event-loop** cho blocking call, **không tự biến thư viện blocking thành non-blocking** và không tự xử lý timeout/retry/cancellation của HTTP client. Đây là bridge tạm thời, không phải lựa chọn ưu tiên cho Resource Server tải cao.

### 7.2. Cùng một Mono được subscribe nhiều lần

```java
Mono<OAuth2AuthenticatedPrincipal> result =
    introspector.introspect(token);

result.subscribe();
result.subscribe();
```

Với **cold publisher** thông thường, mỗi subscription có thể tạo **một lần introspection mới**. Nhưng với publisher đã cache/hot hoặc implementation tùy chỉnh, không được giả định số lần HTTP call tuyệt đối bằng số lần subscribe.

Trong đường HTTP authentication thông thường, framework quản lý subscription. **Không tự `subscribe()` bên trong introspector** chỉ để “kiểm tra token trước”: một detached subscription tạo race, không truyền lỗi về authentication pipeline và có thể chạy việc không còn cần thiết.

### 7.3. Một request không nên xác thực bằng hai kết quả khác nhau

Nếu ứng dụng tùy ý subscribe hai lần vào remote introspection trong một request, token có thể bị thu hồi giữa hai lần hoặc AS trả metadata khác nhau. Việc duplicate subscriptions có thể làm logic lộn xộn; framework authentication nên nhận **một publisher đã được kết hợp đúng**.

Nếu cần chia sẻ một kết quả trong cùng chuỗi, cân nhắc thiết kế publisher rõ ràng. Không dùng `cache()` vô hạn để biến kết quả xác thực thành quyền vĩnh viễn.

## 8. Viết decorator bảo vệ hợp đồng `Mono`

Giả sử Orders API có yêu cầu:

- Introspection từ AS đáng tin phải hoàn thành thành công.
- `iss` phải đúng issuer được cho phép.
- `aud` phải chứa `orders-api`.
- Delegate đã tạo `SCOPE_...` authorities từ `scope`; decorator phải **giữ nguyên**, không tự xóa.
- Nếu có extension `permissions`, chỉ giá trị `order:approve` được chuyển thành `PERMISSION_order:approve`.
- Thiếu/không khớp issuer/audience hoặc extension sai type phải **fail closed**.
- Không biến empty/error thành Authentication có quyền.

Implementation sau không tự gửi HTTP. Nó chỉ bọc một `ReactiveOpaqueTokenIntrospector` đã được cấu hình để xác minh token:

```java
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

public final class PolicyCheckingReactiveIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final String trustedIssuer;
    private final String requiredAudience;

    public PolicyCheckingReactiveIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            String trustedIssuer,
            String requiredAudience) {

        this.delegate = Objects.requireNonNull(delegate);
        this.trustedIssuer = Objects.requireNonNull(trustedIssuer);
        this.requiredAudience = Objects.requireNonNull(requiredAudience);
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        // Mono.defer giữ lời gọi delegate ở thời điểm subscription.
        return Mono.defer(() -> delegate.introspect(token))
            // Empty không có nghĩa token hợp lệ.
            .switchIfEmpty(Mono.error(new BadOpaqueTokenException(
                "No authenticated introspection principal")))
            // Kiểm tra contract và gắn thêm quyền đã được duyệt.
            .map(this::validateAndEnrich);
    }

    private OAuth2AuthenticatedPrincipal validateAndEnrich(
            OAuth2AuthenticatedPrincipal principal) {

        if (!trustedIssuer.equals(principal.getAttribute("iss"))) {
            throw new BadOpaqueTokenException(
                "Introspected issuer is not trusted");
        }

        Object rawAudience = principal.getAttribute("aud");
        boolean audienceMatches =
            (rawAudience instanceof String aud
                && requiredAudience.equals(aud))
            || (rawAudience instanceof Collection<?> audiences
                && audiences.contains(requiredAudience));

        if (!audienceMatches) {
            throw new BadOpaqueTokenException(
                "Introspected audience is not accepted");
        }

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        Object rawPermissions = principal.getAttribute("permissions");

        if (rawPermissions != null) {
            if (!(rawPermissions instanceof Collection<?> permissions)) {
                throw new BadOpaqueTokenException(
                    "Malformed permissions metadata");
            }

            for (Object rawPermission : permissions) {
                if (!(rawPermission instanceof String permission)) {
                    throw new BadOpaqueTokenException(
                        "Malformed permission entry");
                }
                if ("order:approve".equals(permission)) {
                    authorities.add(new SimpleGrantedAuthority(
                        "PERMISSION_order:approve"));
                }
            }
        }

        Map<String, Object> attributes = principal.getAttributes();

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            attributes,
            authorities
        );
    }
}
```

### 8.1. Vì sao dùng `Mono.defer`?

`Mono.defer(() -> delegate.introspect(token))`:

- Trì hoãn lời gọi delegate tới subscription; giúp không kích hoạt HTTP khi mới lắp chuỗi.
- Chuyển exception ném đồng bộ khi gọi `delegate.introspect(token)` thành error signal của publisher, thay vì làm method trả lỗi đồng bộ ngoài chuỗi.
- Giữ khả năng cancellation/timeout/retry composition theo Reactor.

Nó **không tự bảo đảm** delegate bên trong là non-blocking. Nếu delegate thực hiện HTTP blocking lúc được gọi, công việc blocking vẫn chạy trên thread subscription. Vì vậy phải dùng một delegate reactive thực sự hoặc bridge blocking có cấu hình đúng.

### 8.2. Vì sao dùng `switchIfEmpty`?

Nếu delegate vi phạm kỳ vọng bằng cách trả `Mono.empty()`, decorator không tạo anonymous principal hoặc cấp read scope mặc định. Nó phát error signal để authentication không tiếp tục như đã thành công.

Trong một API bảo mật, **empty không phải một quyết định allow**. Nếu muốn biểu đạt “không phải token của manager này, thử manager khác”, đó là hợp đồng của một lớp routing/authentication khác, cần thiết kế rõ và không mượn empty để bỏ qua kiểm tra trong một nhánh opaque.

### 8.3. Vì sao không `onErrorResume(... -> Mono.just(guest))`?

`onErrorResume` không xấu tự thân; nó hữu ích để phục hồi từ các lỗi nghiệp vụ không liên quan đến authentication. Nhưng trong introspection:

```java
// KHÔNG DÙNG: token không được xác minh mà vẫn cấp quyền.
return delegate.introspect(token)
    .onErrorResume(error -> Mono.just(
        fallbackPrincipalWithReadScope));
```

là **fail-open**. Nó có thể biến `active=false`, timeout, sai client secret hoặc lỗi TLS thành quyền đọc API. Nếu cần xử lý lỗi, chỉ nên biến nó thành **một lỗi an toàn khác**, ghi số liệu/log đã lọc, hoặc áp một cache policy được thiết kế và kiểm chứng riêng.

### 8.4. Vì sao giữ `getAuthorities()`?

`SpringReactiveOpaqueTokenIntrospector` có thể đã ánh xạ `scope` thành `SCOPE_orders.read`. Khi custom tạo `DefaultOAuth2AuthenticatedPrincipal` mới, nếu chỉ đưa permission mới mà bỏ authorities cũ, HTTP rule `hasAuthority("SCOPE_orders.read")` sẽ không khớp dù token đã được cấp read scope.

Ở đây `LinkedHashSet` giữ quyền gốc và loại bỏ bản sao nếu permission trùng. **Giữ mọi authorities** chỉ phù hợp khi delegate được tin cậy và các authorities đó thuộc hợp đồng của API; nếu cần giới hạn theo resource, hãy thêm bước policy lọc/từ chối có chủ đích.

### 8.5. Tại sao audience/issuer phải lấy sau delegate?

Opaque token raw không nhất thiết chứa bất kỳ claim nào API đọc được. Ngay cả khi raw token trông giống JWT, không được parse `iss` hoặc `aud` chưa xác minh rồi coi là đáng tin. Decorator ở đây kiểm tra **attributes do delegate được tin cậy trả sau introspection**.

Ứng dụng đa issuer cần chọn AS và introspection endpoint từ cấu hình/allowlist an toàn; không xây URL introspection từ một claim chưa xác thực trong token hoặc header tùy ý.

### 8.6. Giới hạn và giả định của ví dụ

Mã minh họa giả định:

- AS luôn trả `iss`, `aud` theo contract. Nếu không, policy từ chối; cần trao đổi hợp đồng với AS thay vì âm thầm bỏ check.
- `permissions` là extension được AS xác nhận và không do client tự khai báo.
- `aud` có thể là String hoặc Collection của Strings; nếu AS dùng định dạng khác, adapter phải chuẩn hóa được xác minh.
- `getName()` của principal là tên được delegate xác định; có thể đại diện cho service client thay vì user.
- API còn kiểm tra ownership/tenant tại business service.

Không sử dụng decorator này như bằng chứng AS đã xác thực token nếu `delegate` chính là một stub mà production code tạo ra mà không kiểm tra token.

## 9. Cấu hình bean và kết nối decorator vào WebFlux

Ví dụ tạo delegate chuẩn rồi bọc policy:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
    .SpringReactiveOpaqueTokenIntrospector;

@Configuration
public class IntrospectionBeans {

    @Bean
    ReactiveOpaqueTokenIntrospector reactiveOpaqueTokenIntrospector(
            @Value("${app.security.introspection-uri}") String endpoint,
            @Value("${app.security.introspection-client-id}") String id,
            @Value("${app.security.introspection-client-secret}") String secret,
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.audience}") String audience) {

        ReactiveOpaqueTokenIntrospector remote =
            SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(endpoint)
                .clientId(id)
                .clientSecret(secret)
                .build();

        return new PolicyCheckingReactiveIntrospector(
            remote, issuer, audience);
    }
}
```

```yaml
app:
  security:
    introspection-uri: https://idp.example.com/oauth2/introspect
    introspection-client-id: orders-resource-server
    introspection-client-secret: "${INTROSPECTION_CLIENT_SECRET}"
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
```

Bean này là **một `ReactiveOpaqueTokenIntrospector` duy nhất** cho ví dụ. Trường hợp có nhiều bean khác kiểu hoặc nhiều security chains, cần chỉ định rõ bean nào được dùng.

### 9.1. Nối explicit vào `SecurityWebFilterChain`

```java
@Bean
SecurityWebFilterChain ordersChain(
        ServerHttpSecurity http,
        ReactiveOpaqueTokenIntrospector introspector) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector)))
        .build();
}
```

Đoạn trên chỉ minh họa wiring introspector. Một API thật cần phân biệt GET/POST/PUT/DELETE, mở các endpoint được phép và có fallback phù hợp. Không dùng một rule read áp cho cả DELETE nếu API có phương thức xóa.

### 9.2. DSL `introspectionUri(...)` và `introspector(...)` khác nhau

- `opaqueToken.introspectionUri(...)` / `introspectionClientCredentials(...)`: cấu hình remote introspection mà framework sử dụng.
- **`opaqueToken.introspector(customBean)`**: thay thế/ghi đè đường introspector bằng implementation do ứng dụng cung cấp.

Nếu có custom policy về audience hoặc permission, chỉ thay URI không làm policy tự chạy. Phải nối đúng decorator hoặc phương án policy được version hỗ trợ.

### 9.3. Không gọi `block()` khi tạo bean

Anti-pattern:

```java
@Bean
OAuth2AuthenticatedPrincipal bootstrapPrincipal(
        ReactiveOpaqueTokenIntrospector introspector) {
    return introspector.introspect("some-token").block();
}
```

Điều này gọi introspection ngay khi khởi tạo application, không liên quan tới bearer token request hiện tại; còn có thể làm startup phụ thuộc token hết hạn/IdP. Bean nên là **introspector**, không phải một principal cố định áp cho mọi request.

## 10. Non-blocking: yêu cầu chất lượng của một reactive introspector

Hợp đồng trả `Mono` cho phép kết hợp với Reactor, nhưng **không tự đảm bảo** implementation thực sự non-blocking.

### 10.1. Sai: gọi HTTP đồng bộ trước khi Mono được tạo

```java
return Mono.just(restTemplate.postForObject(
    introspectionUrl, request, OAuth2AuthenticatedPrincipal.class));
```

Đoạn này chặn thread thực hiện lời gọi, bất chấp return type Mono.

### 10.2. Sai: gọi `block()` trong `map`

```java
return delegate.introspect(token)
    .map(principal -> blockingAclLookup(principal).block());
```

Với Reactor, `block()` ở event loop có thể ném lỗi hoặc làm giảm throughput nghiêm trọng. Nếu ACL thật sự cần I/O, đổi `map` thành `flatMap` và dùng repository/client reactive:

```java
return delegate.introspect(token)
    .flatMap(principal ->
        reactiveAclService.enrich(principal));
```

`reactiveAclService.enrich` trong ví dụ trả `Mono<OAuth2AuthenticatedPrincipal>` và phải tuân thủ invariant bảo mật: khi không có quyền hoặc lỗi, **không được tạo quyền dự phòng**.

### 10.3. Dùng đúng operators

| Operator | Phù hợp khi | Cẩn trọng |
|---|---|---|
| `map` | Chuyển principal thành principal mới bằng code nhanh, không blocking | Không dùng khi hàm trả Mono |
| `flatMap` | Chính sách cần I/O phản ứng trả Mono | Quản lý empty/error, không fail-open |
| `switchIfEmpty` | Empty phải chuyển sang lỗi rõ ràng | Không tạo default principal có quyền |
| `timeout` | Giới hạn thời gian chờ upstream | Timeout là lỗi hệ thống, không mặc định token giả |
| `onErrorMap` | Chuyển lớp exception vì hợp đồng | Không nuốt nguyên nhân quan trọng hoặc làm lộ token |
| `onErrorResume` | Chỉ phục hồi theo policy an toàn, thường chuyển lỗi | Cấp quyền dự phòng khi AS lỗi là nguy hiểm |
| `retryWhen` | Retry một số lỗi I/O phù hợp | Không retry token invalid, phải giới hạn số lần/backoff |
| `doOnError` / `doFinally` | Observability, metrics không nhạy cảm | Không log bearer token/secret |
| `cache` | Chia sẻ kết quả có chính sách rõ | Không biến token active thành quyền vĩnh viễn |
| `subscribeOn` | Đưa boundary blocking có chủ đích sang scheduler riêng | Không tự chuyển blocking client thành reactive |

## 11. Empty, error và retry: phân biệt lỗi token với lỗi hạ tầng

Một hệ thống thực tế có ít nhất ba loại thất bại:

1. **Token bị từ chối:** `active=false`, sai audience/issuer/token profile.
2. **Không thể liên hệ AS:** DNS, TLS, timeout, 5xx, rate limit.
3. **Phản hồi sai hợp đồng:** thiếu `active`, JSON sai type, thông tin issuer/audience không đáp ứng yêu cầu.

Không nên gom tất cả vào một catch rồi cấp một principal “để hệ thống còn hoạt động”.

### 11.1. Bảng kỳ vọng kết quả

| Tình huống | `Mono` kỳ vọng ở tầng introspection | Hành vi bảo mật |
|---|---|---|
| AS trả `active=true`, metadata đúng | `onNext(principal) + onComplete` | Tiếp tục authorization |
| AS trả `active=false` | `onError` token invalid | Không tạo Authentication thành công |
| Audience sai | `onError` token không được API chấp nhận | Không cấp quyền từ token của resource khác |
| Issuer sai | `onError` | Không cấp quyền từ issuer khác |
| AS timeout | `onError(TimeoutException)` hoặc exception tương ứng | **Fail closed**; báo lỗi theo vận hành |
| AS 5xx | `onError` upstream failure | Không tự cho qua |
| AS trả body không đúng JSON/hợp đồng | `onError` | Không tự suy đoán `active=true` |
| Delegate trả `Mono.empty()` | Wrapper chuyển thành `onError` | Không xác thực bằng kết quả rỗng |
| Scope thiếu nhưng token active | Có thể trả principal thiếu `SCOPE_...` | HTTP/method scope rule từ chối |
| AS trả metadata của client credentials | Principal có thể đại diện service | Không suy ra user tương tác từ `client_id` |

### 11.2. Retry chỉ khi có lý do

Một introspection request thường là thao tác đọc trạng thái, nên retry một số lỗi kết nối có thể chấp nhận được về mặt chức năng. Nhưng:

- Retry làm tăng tải AS, có thể gây **retry storm**.
- Bearer token được gửi thêm lần; phải bảo vệ transport và metrics.
- Không retry `active=false`, sai issuer/audience hoặc lỗi contract không thể tự hồi phục.
- Retry có thể làm thời gian xác thực vượt SLA và giữ request trong hàng đợi lâu.
- Cần giới hạn số lần, timeout tổng, backoff và circuit breaker nếu phù hợp.

Ví dụ ý tưởng:

```java
return delegate.introspect(token)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientInfrastructureFailure))
    .switchIfEmpty(Mono.error(
        new BadOpaqueTokenException("No introspection result")));
```

`isTransientInfrastructureFailure` là predicate **do application định nghĩa** chỉ true cho lỗi I/O có thể retry; không được true cho token bị từ chối hoặc security policy failure. `Retry` là `reactor.util.retry.Retry`. Đoạn trên minh họa operator composition, không phải recommendation mặc định cho mọi AS.

**Đặt timeout/retry ở tầng phù hợp:** timeout phía HTTP client vẫn cần để giới hạn connect/read; Reactor `timeout` là bảo vệ ở publisher. Timeout tổng của cả request phải tính thêm mọi lần retry.

### 11.3. Đừng tự chuyển mọi upstream error thành 401 invalid_token

Một token bị AS xác nhận inactive khác với AS đang down. Với API:

- Token invalid → thường 401.
- Token active nhưng thiếu scope → thường 403.
- AS timeout → lỗi xác thực hạ tầng, HTTP status có thể theo exception handling/custom 5xx, nhưng **không được cấp quyền**.

Chuyển mọi `TimeoutException` thành `BadOpaqueTokenException` có thể khiến hệ thống báo 401 và khiến client hiểu sai rằng token đã hết hiệu lực. Nên phân biệt nguyên nhân trong metrics/log và phản hồi công khai theo chính sách bảo mật.

### 11.4. Cancellation

Nếu client đóng kết nối trước khi introspection hoàn tất, subscription có thể bị cancel. Điều này không đảm bảo HTTP request tới AS đã bị rút lại; AS có thể đã nhận token. Không ghi log “AS never saw token” chỉ vì publisher bị cancel.

Hạn chế detached subscriptions và I/O không cần thiết; cancellation giúp tiết kiệm tài nguyên khi operators/HTTP client hỗ trợ. Observability nên phân biệt cancel, timeout, invalid và success.

## 12. Scopes, authorities và quyền nghiệp vụ sau introspection

Giả sử AS trả:

```json
{
  "active": true,
  "sub": "user-842",
  "scope": "orders.read orders.update",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a"
}
```

Principal có authorities:

```text
SCOPE_orders.read
SCOPE_orders.update
```

Trong `SecurityWebFilterChain`:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.PUT, "/api/orders/**")
    .hasAuthority("SCOPE_orders.update")
```

Với method security:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import reactor.core.publisher.Mono;

@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderView> readOrder(String id) {
    return repository.findById(id).map(OrderView::from);
}
```

Trong WebFlux, cần bật `@EnableReactiveMethodSecurity` và method phải được gọi qua Spring-managed proxy theo cơ chế hỗ trợ. `@PreAuthorize` kiểm tra authority từ Authentication đã được tạo sau introspection, **không** thực hiện một introspection HTTP call mới cho mỗi annotation.

### 12.1. Scope không cho quyền với mọi object

Token `orders.read` không có nghĩa được xem mọi order ID. Business service cần:

```text
GET /api/orders/ORD-123
  |
  +-- token active?
  +-- aud = orders-api?
  +-- có SCOPE_orders.read?
  +-- sub + issuer + tenant được phép đọc ORD-123?
  +-- trạng thái/order policy có cho phép tiết lộ?
```

Với reactive repository, nên lọc ở query theo actor/tenant, thay vì tải toàn bộ dữ liệu rồi mới dùng reactive post-filter. Các field `sub`/`tenant_id` có thể thiếu với client credentials; policy cần phân biệt service identity và user identity.

### 12.2. Nguy cơ custom converter làm mất `SCOPE_`

Anti-pattern:

```java
return delegate.introspect(token)
    .map(principal ->
        new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            List.of(new SimpleGrantedAuthority("ROLE_USER"))));
```

Đây là thay toàn bộ authorities. Nếu ý định chỉ thêm role, code đã làm mất `SCOPE_orders.read`, khiến API 403 dù AS cấp scope. Cần **giữ `principal.getAuthorities()`** hoặc có policy filter rõ. Không tự thêm `ROLE_ADMIN` từ metadata chưa được thẩm định.

### 12.3. `scope` không phải `scp`/`permissions` mặc định

RFC 7662 định nghĩa `scope` thường là chuỗi phân cách dấu cách:

```json
{ "active": true, "scope": "orders.read orders.write" }
```

Một số AS trả extension:

```json
{ "active": true, "scp": ["orders.read", "orders.write"] }
```

Không mặc định mọi Spring Security introspector mapping `scp`/`permissions` như `scope`. Nếu AS dùng extension, phải thống nhất schema, nguồn authoritative, allowed values và viết adapter/decorator **sau introspection**. Không hợp nhất mù quáng hai claim có thể có semantics khác nhau.

## 13. Reactor Context và việc dùng principal sau authentication

Trong WebFlux, Spring Security dùng **Reactor Context** để truyền `SecurityContext` trong chuỗi request. Không mặc định đọc principal từ một ThreadLocal của Servlet.

Ví dụ:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentActorName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(Authentication::getName);
}
```

Trong controller có thể inject:

```java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import reactor.core.publisher.Mono;

@GetMapping("/api/me")
public Mono<String> me(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    return Mono.just(principal.getName());
}
```

Ví dụ dùng `OAuth2AuthenticatedPrincipal` vì opaque resource-server Authentication thường giữ principal kiểu đó. Không copy ví dụ JWT `@AuthenticationPrincipal Jwt` và mặc định nó áp dụng ở đây. Trong code domain dùng chung, nên chuyển các principal khác nhau sang một `CurrentActor` nội bộ theo hợp đồng.

### 13.1. Không dùng SecurityContextHolder global

Anti-pattern:

```java
// Không dùng cho WebFlux multi-user:
SecurityContextHolder.setStrategyName(
    SecurityContextHolder.MODE_GLOBAL);
```

Điều này có thể khiến một Authentication được dùng chung giữa nhiều requests và người dùng. Vấn đề mất context trong một detached reactive subscription phải giải quyết bằng tổ chức publisher/context propagation, **không** bằng global holder.

### 13.2. Không khởi chạy nested subscribe

```java
introspector.introspect(token)
    .subscribe(principal -> cachedCurrentUser = principal);

return Mono.just("ok");
```

Không dùng mẫu này trong request filter/controller: lời gọi subscribe tách rời chuỗi có thể chạy sau khi response đã hoàn tất, bỏ qua lỗi và dễ trộn state giữa người dùng nếu `cachedCurrentUser` là field shared. Để Spring Security quản lý reactive authentication pipeline.

## 14. Cache introspection: tối ưu có đánh đổi an toàn

Introspection có thể thêm một network round-trip trên mỗi request. Caching giúp giảm latency nhưng đồng thời tạo cửa sổ **revocation delay**.

### 14.1. Không dùng `Mono.cache()` như một token store vô hạn

Ví dụ nguy hiểm:

```java
ConcurrentMap<String, Mono<OAuth2AuthenticatedPrincipal>> cache =
    new ConcurrentHashMap<>();

public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return cache.computeIfAbsent(
        token,
        t -> delegate.introspect(t).cache());
}
```

Mẫu này có thể giữ một principal active **không có giới hạn thời gian** và giữ raw token làm map key trong memory. Nếu AS thu hồi token, API vẫn có thể dùng kết quả cached trước đó. Nó cũng có nguy cơ tăng memory và giữ dữ liệu token lâu hơn cần thiết.

Một cache production cần policy:

- Key gắn với **credential và resource/issuer/policy namespace phù hợp**, không chỉ `sub`.
- TTL nhỏ hơn/không vượt thời điểm `exp` nếu có.
- Giới hạn kích thước và thời gian sống.
- Rõ behavior khi `active=false`, network error, cancellation.
- Cơ chế đồng bộ/invalidation khi quyền bị thay đổi hoặc token bị thu hồi nếu có yêu cầu gần realtime.
- Không log/raw-export keys và attributes nhạy cảm.

### 14.2. Hai token cùng chủ thể có thể có quyền khác nhau

```text
token-A: sub=user-842, scope=orders.read
token-B: sub=user-842, scope=orders.read orders.delete
```

Nếu cache authentication chỉ theo `sub`, token A có thể bị cấp authority từ token B. Scope gắn với **access token đã được cấp**, không phải quyền bất biến của username.

### 14.3. Cache kết quả hay cache HTTP response?

| Cache | Điều được lưu | Rủi ro |
|---|---|---|
| Cache `Mono<OAuth2AuthenticatedPrincipal>` | Có thể chia sẻ publisher/result | Có thể cache lỗi/token revoked và dữ liệu không hết hạn đúng |
| Cache principal sau introspection | Attributes/authorities đã được xác minh | Có thể stale về scope, issuer/audience policy |
| Cache HTTP introspection response | JSON metadata | PII/claims nhạy cảm, serialization, schema drift |
| Không cache | Mỗi request hỏi AS | AS availability/latency |

Nếu chính sách bắt buộc thu hồi token gần tức thời, hãy đánh giá kỹ bất kỳ cache nào. Cache là một quyết định vận hành/bảo mật riêng, **không phải nghĩa mặc định của `Mono`**.

## 15. Unit test hợp đồng `Mono` với `StepVerifier`

Trọng tâm kiểm thử introspector reactive là **không chỉ nhìn return value**, mà còn quan sát tín hiệu publisher:

```text
Case A: onNext(principal) -> onComplete
Case B: onError(BadOpaqueTokenException)
Case C: Mono.empty() từ delegate -> wrapper chuyển thành error
Case D: error từ delegate -> không có principal dự phòng
Case E: chưa subscribe -> chưa tạo remote call (với Mono.defer)
Case F: quyền gốc giữ nguyên sau mapping
```

Không cần IdP thật cho unit test decorator; fake delegate có thể trả Mono đã biết.

### 15.1. Fixture principal tối thiểu

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

final class PrincipalFixtures {

    static final String ISSUER =
        "https://idp.example.com/realms/shop";

    static OAuth2AuthenticatedPrincipal readPrincipal() {
        Map<String, Object> attributes = new LinkedHashMap<>();
        attributes.put("sub", "user-842");
        attributes.put("iss", ISSUER);
        attributes.put("aud", List.of("orders-api"));
        attributes.put("permissions", List.of("order:approve"));

        return new DefaultOAuth2AuthenticatedPrincipal(
            "user-842",
            attributes,
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));
    }
}
```

Fixture tạo principal trực tiếp. Nó **không chứng minh access token đã qua AS**; đó là giả định có chủ đích của unit test wrapper.

### 15.2. Kiểm tra success và giữ authority

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class PolicyCheckingReactiveIntrospectorTest {

    private static final String TOKEN = "opaque-unit-test-token";

    @Test
    void validPrincipalPreservesScopeAndAddsApprovedPermission() {
        ReactiveOpaqueTokenIntrospector delegate =
            token -> Mono.just(PrincipalFixtures.readPrincipal());

        PolicyCheckingReactiveIntrospector subject =
            new PolicyCheckingReactiveIntrospector(
                delegate,
                PrincipalFixtures.ISSUER,
                "orders-api");

        StepVerifier.create(subject.introspect(TOKEN))
            .assertNext(principal -> {
                assertThat(principal.getName())
                    .isEqualTo("user-842");
                assertThat(principal.getAuthorities())
                    .extracting(GrantedAuthority::getAuthority)
                    .containsExactlyInAnyOrder(
                        "SCOPE_orders.read",
                        "PERMISSION_order:approve");
            })
            .verifyComplete();
    }
}
```

Điểm chính: `StepVerifier` khẳng định **một principal được emit và publisher hoàn thành**, đồng thời kiểm tra authority list sau mapping. Không cần cấu hình OAuth client secret hoặc HTTP mock server.

### 15.3. Kiểm tra token invalid

```java
@Test
void inactiveTokenCannotBecomeAuthenticatedPrincipal() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.error(
            new BadOpaqueTokenException("Token is inactive"));

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("inactive-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

Test này chỉ chứng minh wrapper **không nuốt error**. Việc chuyển JSON `active=false` thành `BadOpaqueTokenException` là trách nhiệm của delegate, cần test riêng ở contract/adapter layer.

### 15.4. Kiểm tra empty fail closed

```java
@Test
void emptyDelegateResultIsRejected() {
    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.empty();

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("empty-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

Đây là test trực tiếp của **hợp đồng Mono**. Không dùng `verifyComplete()` với không có `onNext` như một authentication thành công.

### 15.5. Kiểm tra issuer/audience sai

```java
@Test
void wrongAudienceIsRejected() {
    Map<String, Object> attributes = new HashMap<>();
    attributes.put("iss", PrincipalFixtures.ISSUER);
    attributes.put("aud", List.of("payments-api"));
    attributes.put("sub", "user-842");

    OAuth2AuthenticatedPrincipal source =
        new DefaultOAuth2AuthenticatedPrincipal(
            "user-842",
            attributes,
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.just(source);

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("test-token"))
        .expectError(BadOpaqueTokenException.class)
        .verify();
}
```

`HashMap` và các imports cho principal/authorities cần được thêm trong class test phù hợp. Các case tương tự gồm thiếu issuer, audience null/number, audience String hợp lệ và collection có nhiều audiences. **Không dùng substring** trên audience raw để chấp nhận nhầm resource như `orders-api-other`.

### 15.6. Kiểm tra tính lazy

```java
@Test
void delegateIsCalledAtSubscriptionTime() {
    AtomicInteger invocations = new AtomicInteger();

    ReactiveOpaqueTokenIntrospector delegate = token -> {
        invocations.incrementAndGet();
        return Mono.just(PrincipalFixtures.readPrincipal());
    };

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    Mono<OAuth2AuthenticatedPrincipal> result =
        subject.introspect("test-token");

    assertThat(invocations.get()).isZero();

    StepVerifier.create(result)
        .expectNextCount(1)
        .verifyComplete();

    assertThat(invocations.get()).isEqualTo(1);
}
```

`AtomicInteger` nằm trong `java.util.concurrent.atomic`. Test chứng minh **wrapper dùng `Mono.defer`**, không đánh giá code HTTP của production client. Một delegate có internal cache có thể có semantics riêng; unit test ở đây chỉ đo số lần gọi phương thức của fake delegate.

### 15.7. Kiểm tra lỗi hạ tầng không bị nuốt

```java
@Test
void infrastructureFailureDoesNotGrantPermission() {
    RuntimeException upstreamFailure =
        new IllegalStateException("Introspection unavailable");

    ReactiveOpaqueTokenIntrospector delegate =
        token -> Mono.error(upstreamFailure);

    var subject = new PolicyCheckingReactiveIntrospector(
        delegate, PrincipalFixtures.ISSUER, "orders-api");

    StepVerifier.create(subject.introspect("test-token"))
        .expectErrorMatches(error -> error == upstreamFailure)
        .verify();
}
```

Test không ấn định rằng HTTP status phải là 401; đây là unit test publisher. Status HTTP khi AS down thuộc integration/exception handling policy.

## 16. Test timeout, cancellation và các edge cases

### 16.1. Virtual time cho timeout

Reactor Test hỗ trợ virtual time để tránh đợi thật:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.<OAuth2AuthenticatedPrincipal>never()
            .timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(java.util.concurrent.TimeoutException.class)
    .verify();
```

Ví dụ kiểm tra semantics của operator `timeout`, không chứng minh HTTP client đã cấu hình socket timeout. Một integration test riêng cần mô phỏng AS phản hồi chậm để xác minh timeout thực và việc xử lý lỗi.

### 16.2. Cancel

```java
StepVerifier.create(
        Mono.<OAuth2AuthenticatedPrincipal>never())
    .expectSubscription()
    .thenCancel()
    .verify();
```

Test này chứng minh publisher có thể được cancel, không chứng minh upstream AS đã dừng xử lý request. Muốn kiểm tra network cancellation thật, cần integration test với WebClient/mock server thích hợp.

### 16.3. Delegate trả null

Một implementation sai có thể:

```java
@Override
public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    return null; // VI PHẠM hợp đồng API.
}
```

Reactive Streams không chấp nhận null như phần tử thành công. Trả null thay vì Mono gây lỗi lập trình, không phải token “không có user”. Với `Mono.defer`, lời gọi delegate trả null sẽ trở thành error trong pipeline; không tự cấp quyền để “sửa” lỗi đó.

Tương tự:

```java
return Mono.just((OAuth2AuthenticatedPrincipal) null);
```

là không hợp lệ vì `Mono.just` yêu cầu phần tử không null. Nếu có object thiếu `sub` nhưng là client-credentials token, chính sách phải diễn giải service identity theo hợp đồng, không tạo null principal.

### 16.4. Publisher emit nhiều principals là sai loại

`ReactiveOpaqueTokenIntrospector` trả `Mono` chứ không phải `Flux`: một token được xác minh phải dẫn đến **một kết luận principal** cho invocation, không phải stream nhiều identity. Không dùng `Flux.fromIterable(principals).next()` để tùy tiện lấy principal đầu khi AS trả nhiều records; đó là sai hợp đồng và có thể gây confusion identity.

## 17. Kiểm thử Spring Security pipeline qua `WebTestClient`

Unit tests của `PolicyCheckingReactiveIntrospector` chưa chứng minh `SecurityWebFilterChain` thực sự dùng implementation này. Để test wiring:

1. Cấu hình test WebFlux application có `SecurityWebFilterChain` bật opaque-token resource server.
2. Cấp một fake `ReactiveOpaqueTokenIntrospector` có behavior kiểm soát được.
3. Gửi **Authorization: Bearer ...** thật qua `WebTestClient`.
4. Xác nhận token valid + scope đúng được phép; invalid token bị 401; active nhưng scope thiếu bị 403.

### 17.1. Fake introspector cho test

```java
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

@TestConfiguration
class FakeIntrospectionConfiguration {

    @Bean
    @Primary
    ReactiveOpaqueTokenIntrospector testIntrospector() {
        ReactiveOpaqueTokenIntrospector delegate = token -> {
            if ("read-token".equals(token)) {
                return Mono.just(PrincipalFixtures.readPrincipal());
            }
            return Mono.error(
                new BadOpaqueTokenException("Token is inactive"));
        };

        return new PolicyCheckingReactiveIntrospector(
            delegate,
            PrincipalFixtures.ISSUER,
            "orders-api");
    }
}
```

Đây là test fixture. Đừng publish bean `testIntrospector` trong production configuration; nó chấp nhận một literal token và không liên hệ Authorization Server thật.

### 17.2. HTTP request test

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OpaqueWebFluxSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void acceptedTokenCanCallReadApi() {
        client.get().uri("/api/orders/ORD-123")
            .headers(headers ->
                headers.setBearerAuth("read-token"))
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void inactiveTokenIsRejected() {
        client.get().uri("/api/orders/ORD-123")
            .headers(headers ->
                headers.setBearerAuth("inactive-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Mẫu này cần test context import đúng `FakeIntrospectionConfiguration`, controller cho `/api/orders/ORD-123`, dữ liệu và business policy tương thích; `@AutoConfigureWebTestClient` không tự tạo endpoint. Nếu security DSL **gắn cứng một introspector instance** chứ không inject bean, chỉ thêm `@Primary` test bean chưa chắc thay instance đó. Phải bảo đảm test chain thực sự dùng fake được cấu hình.

### 17.3. Test thiếu scope

Fake introspector có thể trả một principal `SCOPE_other.read` cho `wrong-scope-token`; gửi token qua Bearer header rồi mong đợi **403** khi route yêu cầu `SCOPE_orders.read`. Khi fake trả `BadOpaqueTokenException`, expect **401** cho token invalid.

Trường hợp có scope đúng nhưng order thuộc tenant khác phải kiểm tra riêng tại business service. Một token có `SCOPE_orders.read` **không tự cho quyền đọc mọi ID**.

### 17.4. `mockOpaqueToken()` không kiểm tra introspector

Spring Security Test cung cấp:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

client.mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders/ORD-123")
    .exchange()
    .expectStatus().isOk();
```

Đây là cách tốt để kiểm tra **authorization với Authentication đã được tạo sẵn**. Nhưng nó có thể **bỏ qua `ReactiveOpaqueTokenIntrospector` và không gọi AS**. Vì vậy:

- `mockOpaqueToken()` test HTTP/method authorization.
- Fake introspector + Bearer header test wiring/interceptor behavior.
- Mock HTTP server cho introspection endpoint test RFC 7662 response parsing/`active`/scope mapping.
- Test tích hợp với AS thực (test environment) kiểm tra client authentication, token issuance, revocation và metadata contract.

Đừng nói “introspection đã được test” chỉ vì `mockOpaqueToken()` trả 200.

## 18. Contract test với một HTTP introspection endpoint giả lập

Để test implementation **`SpringReactiveOpaqueTokenIntrospector`** chứ không chỉ wrapper, có thể dùng mock HTTP server (ví dụ MockWebServer hoặc WireMock chạy local trong test) trả các response chuẩn:

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "sub": "user-842",
  "aud": ["orders-api"],
  "iss": "https://idp.example.com/realms/shop"
}
```

và:

```json
{
  "active": false
}
```

Test nên xác nhận:

| Fixture response/điều kiện | Kết quả adapter |
|---|---|
| `active=true`, `scope=orders.read orders.update` | Một principal, có authorities `SCOPE_orders.read` và `SCOPE_orders.update` |
| `active=true`, scope thiếu | Principal thiếu scope authority, hoặc bị policy bổ sung từ chối |
| `active=false` | Token không được xác thực, publisher lỗi |
| `aud=["payments-api"]` | Decorator Orders API từ chối |
| JSON sai type, ví dụ `active="true"` | Không tự suy đoán valid |
| HTTP 401 từ introspection endpoint | Lỗi client credentials/AS, không cấp quyền |
| HTTP 5xx hoặc timeout | Lỗi hạ tầng, fail closed |
| Body không đúng JSON | Lỗi decode/contract, fail closed |

Hành vi chính xác của implementation có thể khác theo phiên bản đối với parsing thuộc tính, nên assert **trạng thái xác thực và authorities mà API thực dùng**, không assert toàn bộ object bằng `toString()`.

### 18.1. Không hard-code token thật trong fixtures

Token introspection dùng Bearer credential — nếu lộ có thể bị replay. Không đưa:

```text
Authorization: Bearer <real-user-token>
client_secret=<real-secret>
entire raw introspection response with PII
```

vào test artifacts, logs hoặc source control. Dùng token giả không có giá trị như `opaque-test-token` và metadata synthetic. Test AS thật dùng short-lived credentials, test-only scopes và cleanup có kiểm soát.

## 19. Những hiểu nhầm dễ gây lỗ hổng

| Nhận định sai | Điều cần hiểu đúng |
|---|---|
| “Trả `Mono` nghĩa HTTP call đã non-blocking.” | Có thể gọi blocking code trước `Mono.just`; phải kiểm tra implementation |
| “`Mono.empty()` nghĩa token anonymous hợp lệ.” | Empty không chứng minh valid; nên fail closed theo hợp đồng |
| “Token active là được vào mọi endpoint.” | Cần audience/scope và business authorization |
| “`onErrorResume` tạo guest principal giúp API ổn định.” | Có thể biến token bị thu hồi/AS down thành quyền trái phép |
| “`scope=orders.write` tự bao hàm read/delete.” | Scope không có hierarchy mặc định |
| “`hasRole('orders.read')` sẽ kiểm tra OAuth scope.” | Mặc định role prefix là `ROLE_`, scope mapping thường `SCOPE_` |
| “`scp` array luôn tương đương `scope`.” | Tùy IdP/adapter; cần contract riêng |
| “JWT trong token raw có `aud=orders-api` nên không cần introspection.” | Claim chưa xác minh không phải bằng chứng |
| “Có `@AuthenticationPrincipal Jwt` là lấy được principal opaque.” | Opaque thường là `OAuth2AuthenticatedPrincipal` |
| “Dùng Servlet `OpaqueTokenIntrospector` trong WebFlux là ổn.” | Nó đồng bộ; reactive path dùng `ReactiveOpaqueTokenIntrospector` |
| “Khi AS lỗi có thể dùng quyền của user lần trước.” | Dễ trộn access token/authority; cache phải theo credential và TTL có policy |
| “`Mono.cache()` giúp token revocation vẫn hiệu lực ngay.” | Cache có thể giữ token đã bị thu hồi |
| “Gọi `subscribe()` trong filter để auth chạy sớm.” | Detached subscription có race/error bị bỏ qua |
| “Gọi `block()` trong `map` chỉ mất chút thời gian.” | Có thể chặn Netty event loop và lỗi ở scheduler non-blocking |
| “`MockOpaqueToken` test chứng minh AS đã trả `active=true`.” | Nó giả lập Authentication, bỏ qua introspector thật |
| “HTTP 403 chứng minh token bị AS từ chối.” | 403 thường do thiếu quyền; invalid token thường 401 |
| “Token có `SCOPE_orders.read` được đọc mọi đơn hàng.” | Cần owner/tenant/state checks ở domain |
| “Có `ReactiveOpaqueTokenAuthenticationConverter` thì không cần introspector.” | Converter xử lý kết quả **sau** introspection thành công |
| “Có timeout thì được mặc định cho phép.” | Timeout là thiếu bằng chứng xác thực; phải fail closed |
| “Cancellation đồng nghĩa AS không nhìn thấy token.” | Request có thể đã tới AS; cancellation không hoàn tác network call |

## 20. Checklist thiết kế và kiểm thử production

Khi thêm hoặc tùy biến reactive introspection, có thể triển khai theo thứ tự:

1. **Xác nhận token contract:** opaque/reference token hay JWT được introspect; AS endpoint nào tin cậy?
2. **Bật đúng WebFlux stack:** `SecurityWebFilterChain`, `ServerHttpSecurity` và `oauth2ResourceServer(...opaqueToken...)`.
3. **Dùng đúng interface:** `ReactiveOpaqueTokenIntrospector`, return `Mono<OAuth2AuthenticatedPrincipal>`, không trả principal trực tiếp hoặc null.
4. **Định nghĩa thành công:** chỉ emit principal sau xác minh, với attributes/authorities được tin cậy.
5. **Định nghĩa failure:** token inactive/error/empty không sinh successful Authentication; tránh fail-open.
6. **Định nghĩa identity và resource:** issuer/audience, client credentials vs user, tenant/subject, các trường bắt buộc.
7. **Giữ mapping scope đúng:** `scope` → `SCOPE_...`; custom permissions chỉ theo allowlist và nguồn xác thực.
8. **Đảm bảo I/O phản ứng:** không `block()`, không `Mono.just(blockingCall())` trên event loop.
9. **Xác định timeout/retry:** giới hạn latency và lỗi upstream; không retry token invalid; không làm lộ credential.
10. **Kiểm soát caching:** TTL, exp, revocation, principal isolation theo token/resource/issuer.
11. **Đặt business policy:** scope chỉ là quyền chức năng; owner/tenant/state phải kiểm tra riêng.
12. **Unit test tín hiệu Mono:** success, error, empty, invalid, malformed, lazy subscription, scope preservation.
13. **Test adapter HTTP:** `active=true/false`, format `scope`, lỗi HTTP/JSON/TLS/timeout.
14. **Test WebFlux wiring:** Bearer header thật, custom introspector được gọi, 401/403 đúng tầng.
15. **Test AS integration riêng:** client auth, token issuance/revocation, metadata contract và secret rotation.
16. **Quan sát vận hành:** latency p95/p99, AS timeout, tỷ lệ 401/403, cache hit, cancellation; không log token raw.

### 20.1. Sơ đồ quyết định khi `Mono` hoàn tất

```mermaid
flowchart TD
    A["ReactiveOpaqueTokenIntrospector.introspect(token)"] --> B{"Publisher phát tín hiệu gì?"}
    B -->|"onNext(principal)"| C{"Principal đến từ nguồn introspection đáng tin?"}
    C -->|"Không"| X["Deny / lỗi xác thực"]
    C -->|"Có"| D{"Issuer / audience / token profile đúng?"}
    D -->|"Không"| X
    D -->|"Có"| E["Giữ scope authorities, custom mapping theo policy"]
    E --> F{"HTTP/method scope được cấp?"}
    F -->|"Không"| Y["Từ chối authorization"]
    F -->|"Có"| G{"Owner / tenant / business state hợp lệ?"}
    G -->|"Không"| Y
    G -->|"Có"| H["Cho xử lý tài nguyên"]
    B -->|"onError"| I["Phân loại invalid vs AS failure<br/>không cấp quyền"]
    B -->|"onComplete rỗng"| J["Chuyển thành lỗi/fail closed"]
    B -->|"không kết thúc"| K["Timeout và fail closed"]
```

## 21. Tổng kết

```text
WEBFLUX OPAQUE RESOURCE SERVER

Authorization: Bearer opaque-token
                  |
                  v
OpaqueTokenReactiveAuthenticationManager
                  |
                  v
ReactiveOpaqueTokenIntrospector
                  |
                  v
Mono<OAuth2AuthenticatedPrincipal>
  |
  +-- onNext(principal) + onComplete
  |      -> Authentication / SCOPE_ authorities
  |      -> HTTP authorization
  |      -> owner/tenant/business policy
  |
  +-- onError(...)
  |      -> Authentication không thành công
  |
  +-- onComplete() không có principal
  |      -> Không phải xác thực thành công;
  |         custom wrapper nên fail closed
  |
  +-- không hoàn tất
         -> timeout, không cấp quyền dự phòng

Không dùng:
  Mono.just(blockingIntrospection())
  Mono.empty() làm quyền mặc định
  onErrorResume(... -> adminPrincipal)
  subscribe() tách rời đường xác thực
  cache() vô thời hạn
```

**`ReactiveOpaqueTokenIntrospector` là ranh giới giữa Bearer token chưa được tin cậy và principal đã được xác minh trong WebFlux.** Hợp đồng `Mono<OAuth2AuthenticatedPrincipal>` yêu cầu code phân biệt rõ **một giá trị thành công**, **không có giá trị**, **lỗi** và **việc chờ quá lâu**. Chỉ principal từ introspection đáng tin mới được dùng tạo Authentication; empty/error/timeout không phải lý do tự thêm authorities.

Trong triển khai thực tế, hãy để `SpringReactiveOpaqueTokenIntrospector` thực hiện HTTP introspection phản ứng, bọc nó bằng policy delegate khi cần kiểm tra issuer/audience hoặc ánh xạ quyền đặc thù, giữ nguyên `SCOPE_` nếu không có lý do rõ để thay đổi, và tách các lớp test: **`StepVerifier` cho hợp đồng publisher, mock HTTP cho RFC 7662, `WebTestClient` cho Spring Security wiring và integration với AS thật cho contract môi trường**.

## Tài liệu tham khảo

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): ý nghĩa `active`, `scope`, metadata và authorization của introspection endpoint.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): OAuth access token, phạm vi scope và mô hình Resource Server.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credential, `invalid_token`, `insufficient_scope` và 401/403.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): ràng buộc access token với resource/audience.
- [Spring Security Reference — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `SpringReactiveOpaqueTokenIntrospector`, WebFlux wiring, authorities và custom introspection.
- [Spring Security 6.5 Reference — Reactive Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html): cùng chủ đề cho dòng 6.5 khi dự án chưa nâng lên 7.x.
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html): chữ ký `Mono<OAuth2AuthenticatedPrincipal> introspect(String)`.
- [Spring Security API — SpringReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringReactiveOpaqueTokenIntrospector.html): implementation và builder.
- [Spring Security API — OpaqueTokenReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenReactiveAuthenticationManager.html): tạo Authentication từ introspection.
- [Spring Security API — ReactiveOpaqueTokenAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenAuthenticationConverter.html): chuyển principal thành `Mono<Authentication>`.
- [Spring Security Reference — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOpaqueToken()` và giới hạn của authentication fixtures.
- [Project Reactor Reference — Mono](https://projectreactor.io/docs/core/release/reference/coreFeatures/mono.html): `Mono` và các tín hiệu hoàn tất/lỗi.
- [Project Reactor Reference — Testing with StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier và virtual time.
- [Project Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context trong pipeline phản ứng.
- [Spring Security Reference — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain`/`ServerHttpSecurity`.
- [OWASP API Security 2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): scope chưa đủ cho quyền trên object.
