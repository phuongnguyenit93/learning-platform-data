# Tiêm OAuth2AuthorizedClient bằng @RegisteredOAuth2AuthorizedClient

**Module:** Spring Security – reactive (WebFlux)  
**Phần:** OAuth2 Client  
**Mục tiêu:** Hiểu cách WebFlux giải tham số `@RegisteredOAuth2AuthorizedClient` thành `OAuth2AuthorizedClient`, cách lựa chọn đúng registration/principal/token, kết hợp `WebClient` để gọi API bên ngoài, kiểm thử annotation mà không phải chạy Authorization Server thật và tránh rò rỉ credential.

## 1. Kết luận trọng tâm

`@RegisteredOAuth2AuthorizedClient("demo-client")` có thể đặt trên **tham số của một annotated controller WebFlux** kiểu `OAuth2AuthorizedClient`. Spring Security tự giải tham số dựa trên OAuth2 Client infrastructure, `ClientRegistration`, principal/request context, repository và `ReactiveOAuth2AuthorizedClientManager` tương ứng.

```java
@GetMapping("/inventory")
public Mono<String> inventory(
        @RegisteredOAuth2AuthorizedClient("inventory-client")
        OAuth2AuthorizedClient authorizedClient) {

    return webClient.get()
        .uri("https://trusted-inventory.example.invalid/items")
        .attributes(
            ServerOAuth2AuthorizedClientExchangeFilterFunction
                .oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

Đây là **fragment**, không phải file Java độc lập: `webClient` cần được cấu hình OAuth2 filter, registration `inventory-client` phải tồn tại, token phải được cấp theo grant phù hợp, host minh họa không hoạt động. Đoạn này cho thấy hai hành động khác nhau:

1. **Injection:** framework giải `OAuth2AuthorizedClient` làm tham số controller.
2. **Outbound authorization:** caller chỉ định client đó cho `WebClient`, để filter thêm `Authorization: Bearer ...` vào request tới API được tin cậy.

**Không** trả `getAccessToken().getTokenValue()` hoặc `getRefreshToken().getTokenValue()` vào JSON, log, tracing hoặc browser chỉ để xem injection có hoạt động hay không. Đây là Bearer credential; nếu lộ có thể bị sử dụng theo phạm vi/hiệu lực của nó.

## 2. Các đối tượng phải phân biệt

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| `ClientRegistration` | Cấu hình ứng dụng đã đăng ký với Authorization Server: registration ID, client ID, scope, grant type, token URI, redirect URI nếu dùng | `inventory-client` |
| `ReactiveClientRegistrationRepository` | Tra cứu registration theo ID; Boot có thể auto-config từ properties | `findByRegistrationId("inventory-client")` |
| `OAuth2AuthorizedClient` | Liên kết registration, principal name, access token và refresh token tùy chọn | Grant cho Alice hoặc service account |
| `OAuth2AccessToken` | Token để Client gọi Resource Server, có scopes và issued/expires timestamp | Bearer access token |
| `OAuth2RefreshToken` | Token có thể dùng xin access token mới tại Authorization Server khi được cấp | Không có ở nhiều `client_credentials` grants |
| `OAuth2AuthenticationToken` | Authentication của user khi đăng nhập OAuth2/OIDC vào website | Principal trong WebSession |
| `ReactiveOAuth2AuthorizedClientManager` | Authorize, re-authorize, refresh/renew và phối hợp persistence | Được argument resolver/WebClient dùng |
| `ServerOAuth2AuthorizedClientRepository` | Lưu/tra authorized client trong web request/session context | WebFlux-aware repository |
| `ReactiveOAuth2AuthorizedClientService` | Dịch vụ load/save authorized client theo registration/principal ở phạm vi ứng dụng | In-memory, R2DBC/custom |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Thêm Bearer token vào outbound `WebClient` request theo authorized client | `.attributes(oauth2AuthorizedClient(client))` |

**ClientRegistration không phải Authorized Client.** Registration có thể tồn tại trước khi bất kỳ user/service nào nhận token. Authorized client chỉ tồn tại hữu ích khi authorization/grant đã được thực hiện hoặc trong test đã được giả lập.

**Authentication không phải Authorized Client.** Một website có thể có browser session đã đăng nhập, nhưng chưa được cấp access token cho một API riêng. Ngược lại, scheduled job có thể lấy token `client_credentials` không liên quan phiên browser.

**ID Token không phải Access Token.** Trong OIDC, `id_token` dùng cho Relying Party xác minh sự kiện đăng nhập; API Resource Server cần access token phù hợp audience/scope. Đừng dùng `OidcUser.getIdToken()` thay `OAuth2AuthorizedClient.getAccessToken()`.

### 2.1. Hai khóa nhận diện authorized client

Một authorized client thường được liên hệ bằng **registrationId** và **principalName**:

```text
Registration: inventory-client
          |
          +-- principalName: alice
          |     access_token: token-user-A
          |
          +-- principalName: bob
          |     access_token: token-user-B
          |
          +-- principalName: service-principal
                access_token: token-service (khi policy cho phép)
```

Với authorization code grant, access token có thể đại diện delegated access của một user. Với client credentials, token thường đại diện **ứng dụng**. Principal name được dùng trong storage/authorization request có thể khác ý nghĩa nghiệp vụ của end user. Không chia sẻ token người dùng giữa requests qua biến `static currentToken`, và không chọn token từ tên user được HTTP client tự khai mà chưa xác minh.

Với multi-tenant/multi-provider, cần tách theo issuer, tenant và registration, không chỉ username. Token của tenant A không được dùng để gọi API/tenant B.

## 3. Chính xác annotation tiêm vào đâu?

Import:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
```

Tại controller:

```java
@GetMapping("/client/details")
public Mono<String> details(
    @RegisteredOAuth2AuthorizedClient("demo-client")
    OAuth2AuthorizedClient client) {

    String id = client.getClientRegistration().getRegistrationId();
    String principal = client.getPrincipalName();
    return Mono.just(id + ":" + principal);
}
```

Spring Security WebFlux có `OAuth2AuthorizedClientArgumentResolver` thuộc package `org.springframework.security.oauth2.client.web.reactive.result.method.annotation`, là `HandlerMethodArgumentResolver` dành cho reactive annotated endpoints. Nó làm việc với `ServerWebExchange`, OAuth2 authorized client manager/repository và Authentication của request. Resolver chạy theo mô hình reactive nội bộ, nhưng tham số do controller nhận là **`OAuth2AuthorizedClient`**, không cần tự bọc `Mono<OAuth2AuthorizedClient>` trong signature.

**Giá trị annotation là registration ID nội bộ**, không phải OAuth `client-id` do IdP cấp:

```java
@RegisteredOAuth2AuthorizedClient("demo-client")
OAuth2AuthorizedClient a

@RegisteredOAuth2AuthorizedClient(registrationId = "demo-client")
OAuth2AuthorizedClient b
```

Hai cách tương đương nhờ alias `value` và `registrationId`. Nếu properties là `registration.reporting` mà annotation yêu cầu `demo-client`, resolver không tự đoán đúng registration khác. Đừng nhận registration ID tùy ý từ query/header public rồi đem authorize tới mọi provider mà không có allowlist.

### 3.1. Annotation không phải @Autowired

`@RegisteredOAuth2AuthorizedClient` chỉ giải **method parameter** ở handler được framework xử lý. Không đặt vào field singleton rồi chờ Spring inject token. Không đặt lên một `@Service` tùy ý và mong nó có hiệu lực như AOP authorization. Với service hoặc background job, inject `ReactiveOAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientService` và gọi API tương ứng.

Nếu test khởi tạo controller bằng `new ClientController()` rồi gọi trực tiếp Java method, không có MVC/WebFlux argument resolver; muốn test annotation phải đi qua `WebTestClient` với Spring context và security config.

### 3.2. Pipeline khi một request đi vào

```text
Browser / client -> GET /client/details
       |
       v
SecurityWebFilterChain: authentication, .authenticated()
       |
       v
Handler mapping -> annotated controller method
       |
       v
OAuth2AuthorizedClientArgumentResolver:
  registrationId = "demo-client"
  principalName = authenticated context / chosen service principal
       |
       +--> existing authorized client? -> load
       |
       +--> missing/expired? -> manager + provider theo grant
       |     authorization_code -> có thể cần redirect/consent
       |     client_credentials -> có thể POST token endpoint
       |     refresh_token -> có thể làm mới nếu có và được hỗ trợ
       |
       +--> failure / config missing -> không có usable token
       |
       v
Controller nhận OAuth2AuthorizedClient
       |
       +--> trả DTO metadata an toàn; hoặc
       |
       +--> gửi bằng WebClient có OAuth2 filter
               |
               v
             Resource Server kiểm Bearer, audience, scope, thời gian
```

Không có lời hứa rằng annotation **luôn gọi** AS để lấy token mới trên mọi request. Với token còn hạn và đã được lưu, manager thường load/reuse. Không có registration/authorization/provider phù hợp thì không thể tiêm ra token hợp lệ bằng phép màu.

## 4. Cấu hình OAuth2 Client trong Spring WebFlux

Dependency cần thiết: `spring-boot-starter-oauth2-client` (ngoài WebFlux/Security). Cấu hình cơ bản:

```java
@Configuration
@EnableWebFluxSecurity
class SecurityConfiguration {
    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **fragment**; project đầy đủ nằm ở phần 8. `oauth2Client()` bật OAuth2 Client support; không có nghĩa app tự trở thành Resource Server nhận inbound Bearer token. `oauth2Login()` chỉ cần khi dùng OAuth2/OIDC để đăng nhập user qua provider; một local form login + `client_credentials` token outbound là use case hợp lệ khác.

Trong Spring Boot có thể cấu hình registration bằng properties; `ReactiveClientRegistrationRepository` được xây từ đó. Ví dụ:

```properties
spring.security.oauth2.client.registration.demo-client.provider=demo-provider
spring.security.oauth2.client.registration.demo-client.client-id=demo-client-id
spring.security.oauth2.client.registration.demo-client.client-secret=training-invalid
spring.security.oauth2.client.registration.demo-client.authorization-grant-type=client_credentials
spring.security.oauth2.client.registration.demo-client.scope=inventory.read
spring.security.oauth2.client.provider.demo-provider.token-uri=https://idp.example.invalid/oauth2/token
```

Đây là **placeholder minh họa, không hoạt động với IdP thật**. Không đưa `training-invalid` vào production; lấy credentials/URI được cấp hợp lệ, dùng secret manager, HTTPS và scopes được phê duyệt.

### 4.1. Grant type thay đổi ý nghĩa token

| Grant | Ai cấp token? | Token đại diện cho ai? | Lưu ý |
| --- | --- | --- | --- |
| `authorization_code` | AS sau browser authorization/login/consent | Quyền được user ủy quyền cho client | Code + state + PKCE/nonce theo profile, callback URI chính xác |
| `client_credentials` | AS cấp trực tiếp cho confidential client | **Ứng dụng/client** | Không tự đại diện một end user; thường không refresh token |
| `refresh_token` | AS cấp access token mới theo refresh grant | Theo authorized grant đã có | Chỉ nếu refresh token hợp lệ và provider hỗ trợ |
| Extension grants | Tùy provider, ví dụ token exchange theo policy | Tùy grant và issuer | Không tự bật mọi grant; cần cấu hình rõ |

Trong một controller dùng `@RegisteredOAuth2AuthorizedClient("demo-client")` cho client_credentials, token có thể gắn với principal của request trong storage nhưng **quyền của token vẫn là quyền ứng dụng**, không phải quyền admin của người gọi. Hãy kiểm business authorization ở route/service.

### 4.2. ReactiveOAuth2AuthorizedClientManager có hai bối cảnh

- `DefaultReactiveOAuth2AuthorizedClientManager` thích hợp **web request context**; phối hợp repository lưu client và refresh/renew qua providers.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` thích hợp **ngoài WebExchange**, ví dụ cron/queue/batch, dùng service store và service principal tường minh.

Đừng dùng annotated controller argument resolver từ background job, vì không có handler method/ServerWebExchange để giải tham số.

## 5. Dùng authorized client cho WebClient outbound

Cần cấu hình `ServerOAuth2AuthorizedClientExchangeFilterFunction`:

```java
@Bean
WebClient protectedWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    var oauth =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .filter(oauth)
        .build();
}
```

Fragment cần imports: `WebClient`, `ReactiveOAuth2AuthorizedClientManager`, `ServerOAuth2AuthorizedClientExchangeFilterFunction`, `@Bean`. Nếu dùng bare `WebClient.create()` không có OAuth2 filter, chỉ đặt request attribute chưa chắc thêm header.

### 5.1. Chọn client tường minh trên đúng request

```java
return webClient.get()
    .uri("https://trusted-api.example.invalid/v1/items")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
```

`oauth2AuthorizedClient(...)` là static helper ghi thuộc tính vào request để OAuth2 filter sử dụng. Không biến token thành string trong controller để chèn thủ công nếu có thể giữ credential trong filter có kiểm soát.

### 5.2. Chọn theo registration ID khi chưa có đối tượng

```java
return webClient.get()
    .uri("https://trusted-api.example.invalid/v1/items")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("inventory-client"))
    .retrieve()
    .bodyToMono(String.class);
```

Ở đây filter/manager sẽ xác định authorized client từ registration, principal/context và grant. Không phải thay thế hoàn toàn trường hợp annotation: khi controller đã có client chính xác, truyền object tường minh dễ audit hơn.

### 5.3. Rủi ro default authorized client

`ServerOAuth2AuthorizedClientExchangeFilterFunction.setDefaultOAuth2AuthorizedClient(true)` có thể chọn authorized client mặc định của user đã OAuth2 Login cho các outbound requests. Tài liệu Spring Security cảnh báo về việc mọi request từ WebClient dùng chung có thể được gửi token. Tương tự, `setDefaultClientRegistrationId("...")` có thể đính token ngoài ý muốn.

**Khuyến nghị:** Dùng `WebClient` riêng cho trusted upstream; chọn authorized client mỗi request, allowlist destination, kiểm redirect/SSRF và không log header `Authorization`. Token cấp cho API A không mặc nhiên được API B chấp nhận; Resource Server cần kiểm `aud`, issuer, exp và scope/permissions.

## 6. Quản lý vòng đời token và repository

`OAuth2AuthorizedClient` thường có:

```java
OAuth2AccessToken access = client.getAccessToken();
String registrationId =
    client.getClientRegistration().getRegistrationId();
String principalName = client.getPrincipalName();

boolean hasRefreshToken = client.getRefreshToken() != null;
```

Đoạn này là fragment. Không đọc `getRefreshToken().getTokenValue()` khi refresh token null. `OAuth2AccessToken` có `getIssuedAt()`, `getExpiresAt()` và `getScopes()`; có thể dùng metadata an toàn để giám sát expiry mà **không đưa tokenValue vào log**.

- `ServerOAuth2AuthorizedClientRepository` dùng trong web request, có thể giữ state giữa requests.
- `ReactiveOAuth2AuthorizedClientService` là abstraction lưu/tra application-level; Spring có in-memory và khả năng R2DBC/custom persistence.
- `ReactiveOAuth2AuthorizedClientManager` điều phối `ReactiveOAuth2AuthorizedClientProvider`, có thể refresh/renew khi grant và provider phù hợp.
- Việc hết hạn/revoke token ở AS không tự logout browser session WebFlux. Local logout cũng không chắc đã thu hồi mọi access token đã phát.
- Nếu một refresh attempt trả `invalid_grant`, ứng dụng cần loại bỏ stale authorized client theo policy và thông báo/re-authorize phù hợp, tránh retry vô hạn.
- Trong môi trường nhiều instance, cần shared storage/kế hoạch token renewal concurrency, bảo mật token at rest, TTL, rotation, audit và incident response.

**Phân biệt đọc repository với authorize qua manager:** `loadAuthorizedClient(registrationId, principalName)` chỉ đọc một client đã lưu; manager authorize có thể đánh giá expiry và gọi provider xin token mới. Nếu chỉ load rồi gửi token stale, API có thể trả 401.

## 7. Java 17 CLI độc lập: một registration, nhiều principal

Để thấy “authorized client” không đơn giản là “cấu hình client”, dùng ví dụ thuần Java dưới đây. Nó **không** tạo OAuth2 token thật và không làm authentication.

Lưu `ClientAssociationDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ClientAssociationDemo {
    record BoundClient(String registration, String principal,
                       Set<String> scopes) {}

    public static void main(String[] args) {
        var items = List.of(
            new BoundClient("inventory", "alice",
                Set.of("inventory.read")),
            new BoundClient("inventory", "bob",
                Set.of("inventory.write", "inventory.read")),
            new BoundClient("reports", "alice",
                Set.of("report.read"))
        );

        for (BoundClient item : items) {
            String scopes = String.join(",",
                new TreeSet<>(item.scopes()));
            System.out.println(item.registration() + "|"
                + item.principal() + "|" + scopes);
        }
    }
}
```

Chạy:

```bash
javac ClientAssociationDemo.java
java ClientAssociationDemo
```

**Stdout chính xác:**

```text
inventory|alice|inventory.read
inventory|bob|inventory.read,inventory.write
reports|alice|report.read
```

Bài học: registration, principal và scopes đều quan trọng. Trong ứng dụng thật `OAuth2AuthorizedClient` còn chứa access/refresh tokens bí mật, và persistence/lookup phải tách đúng user/tenant.

## 8. Ứng dụng mẫu Spring Boot WebFlux Java 17+ kiểm chứng injection

Ta tạo app gồm browser **form login** để xác thực user với `WebSession` và OAuth2 Client registration `demo-client` theo `client_credentials` để minh họa annotation. Dữ liệu token thật cần AS, nhưng **integration tests dùng `mockOAuth2Client` nên không cần IdP đang chạy**.

Lưu ý hai chế độ:

- **`mvn test`**: sử dụng `spring-security-test` để tạo authorized client giả và SecurityContext trong WebFlux test. Các request đi qua handler/controller và annotation resolver thật, nhưng không gọi AS/token endpoint.
- **Chạy với AS thật**: thay client credentials/token URI trong properties bằng giá trị hợp lệ. Sau khi form login, manager có thể xin access token thật cho registration. Với placeholder `idp.example.invalid`, endpoint cần token **không thể hoàn thành ngoài test**; đây là giới hạn có chủ đích, không phải một OAuth server giả.

### 8.1. Cấu trúc file

```text
webflux-registered-client/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/registered/
    │   │   ├── RegisteredClientApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ClientController.java
    │   └── resources/application.properties
    └── test/java/demo/registered/
        └── RegisteredClientTests.java
```

Java 17+, Maven 3.9+ và Spring Boot **3.5.7** làm mốc ví dụ. Với production hãy dùng phiên bản có bản vá và còn hỗ trợ. Không thêm `spring-boot-starter-web` vì cần **Reactive WebFlux**, không phải Servlet MVC.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>webflux-registered-client</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.springframework.security</groupId>
      <artifactId>spring-security-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

`src/main/resources/application.properties`:

```properties
spring.application.name=webflux-registered-client
server.port=8080

# ID, secret và token endpoint của provider thực phải thay cho demo.
spring.security.oauth2.client.registration.demo-client.provider=demo-provider
spring.security.oauth2.client.registration.demo-client.client-id=training-id
spring.security.oauth2.client.registration.demo-client.client-secret=training-invalid
spring.security.oauth2.client.registration.demo-client.authorization-grant-type=client_credentials
spring.security.oauth2.client.registration.demo-client.scope=inventory.read
spring.security.oauth2.client.provider.demo-provider.token-uri=https://idp.example.invalid/token
```

Các giá trị `training-id`/`training-invalid` và `idp.example.invalid` **không có hiệu lực với Authorization Server nào**; tests sẽ tự cung cấp authorized client giả thay vì gọi endpoint này. Production phải dùng secret manager và endpoint từ IdP đáng tin.

`src/main/java/demo/registered/RegisteredClientApplication.java`:

```java
package demo.registered;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegisteredClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegisteredClientApplication.class, args);
    }
}
```

### 8.2. SecurityConfig.java

`src/main/java/demo/registered/SecurityConfig.java`:

```java
package demo.registered;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(viewer);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers("/client/**").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .oauth2Client(Customizer.withDefaults())
            // CSRF mặc định vẫn bật cho browser POST.
            .build();
    }
}
```

`formLogin` cho phép browser login bằng user demo, `oauth2Client` cung cấp OAuth2 Client integration. Hai việc độc lập: browser session **không tự chứng minh** token của AS đã được cấp; authorized client manager phải lookup/authorize theo registration. `anyExchange().denyAll()` chặn route chưa khai báo. Không tắt CSRF chỉ vì có OAuth2 token cho downstream.

### 8.3. ClientController.java: tham số được tiêm

`src/main/java/demo/registered/ClientController.java`:

```java
package demo.registered;

import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ClientController {

    public record ClientView(
        String registrationId, String principalName,
        List<String> scopes, boolean refreshTokenPresent
    ) {}

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> home() {
        return Mono.just("public");
    }

    @GetMapping(value = "/client/metadata",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ClientView> metadata(
            @RegisteredOAuth2AuthorizedClient("demo-client")
            OAuth2AuthorizedClient client) {
        return Mono.just(safeView(client));
    }

    @GetMapping(value = "/client/alias",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ClientView> alias(
            @RegisteredOAuth2AuthorizedClient(
                registrationId = "demo-client")
            OAuth2AuthorizedClient client) {
        return Mono.just(safeView(client));
    }

    @PostMapping(value = "/client/check",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> check(
            @RegisteredOAuth2AuthorizedClient("demo-client")
            OAuth2AuthorizedClient client) {
        return Mono.just("accepted:" +
            client.getClientRegistration().getRegistrationId());
    }

    private static ClientView safeView(OAuth2AuthorizedClient client) {
        List<String> scopes = client.getAccessToken().getScopes()
            .stream().sorted().toList();

        return new ClientView(
            client.getClientRegistration().getRegistrationId(),
            client.getPrincipalName(), scopes,
            client.getRefreshToken() != null);
    }
}
```

Đây là code chỉ trả **metadata được chọn lọc**. Tuyệt đối không `return Mono.just(client)` để Spring tự serialize toàn bộ authorized client, vì có thể làm lộ access/refresh token. Ngay cả `scopes`/`principalName` cũng phải qua đánh giá privacy và authorization nếu đưa ra browser ngoài mục tiêu demo.

### 8.4. Test bằng WebTestClient và mockOAuth2Client

`spring-security-test` có `SecurityMockServerConfigurers.mockOAuth2Client("demo-client")`, có thể cung cấp `OAuth2AuthorizedClient` giả trong test `ServerWebExchange`. `mockUser("alice")` đặt Authentication độc lập. Do đó test chứng minh **argument resolver và controller** hoạt động, nhưng không thử token exchange, signing hay refresh với IdP thật.

`src/test/java/demo/registered/RegisteredClientTests.java`:

```java
package demo.registered;

import java.time.Instant;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Client;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class RegisteredClientTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    private static OAuth2AccessToken token(Set<String> scopes) {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-token-never-use-in-production",
            now.minusSeconds(60),
            now.plusSeconds(600), scopes);
    }

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRouteWorks() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void anonymousCannotReadClientMetadata() {
        client.get().uri("/client/metadata")
            .exchange().expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                loc -> assertTrue(loc.contains("/login")));
    }

    @Test
    void injectionResolvesRegistrationAndPrincipal() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.registrationId").isEqualTo("demo-client")
            .jsonPath("$.principalName").isEqualTo("alice");
    }

    @Test
    void aliasRegistrationIdIsEquivalent() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/alias")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.registrationId").isEqualTo("demo-client");
    }

    @Test
    void scopesAreSortedInSafeDto() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of(
                    "inventory.write", "inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scopes[0]").isEqualTo("inventory.read")
            .jsonPath("$.scopes[1]").isEqualTo("inventory.write");
    }

    @Test
    void refreshTokenIsOptional() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.refreshTokenPresent").isEqualTo(false);
    }

    @Test
    void differentPrincipalDoesNotBecomeAlice() {
        client.mutateWith(mockUser("bob"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("bob")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principalName").isEqualTo("bob");
    }

    @Test
    void queryCannotOverrideExplicitRegistrationId() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata?registrationId=other")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.registrationId").isEqualTo("demo-client");
    }

    @Test
    void jsonResponseDoesNotExposeRawToken() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody(String.class)
            .value(body -> assertFalse(body.contains(
                "test-token-never-use-in-production")));
    }

    @Test
    void browserPostWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .post().uri("/client/check")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void browserPostWithCsrfSucceeds() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .mutateWith(csrf())
            .post().uri("/client/check")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "accepted:demo-client");
    }

    @Test
    void explicitClientAttributeAttachesBearerOnlyOnOutbound() {
        ClientRegistration reg =
            ClientRegistration.withRegistrationId("demo-client")
                .clientId("demo-id")
                .clientSecret("dummy")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.invalid/token")
                .build();

        OAuth2AuthorizedClient authorized =
            new OAuth2AuthorizedClient(
                reg, token(Set.of("inventory.read")), "alice");

        ReactiveOAuth2AuthorizedClientManager manager =
            request -> Mono.just(authorized);

        ExchangeFunction fake = request -> {
            String authorization = request.headers()
                .getFirst(HttpHeaders.AUTHORIZATION);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .body(authorization == null
                    ? "NO_AUTH" : authorization)
                .build());
        };

        var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);
        WebClient web = WebClient.builder()
            .exchangeFunction(fake)
            .filter(filter)
            .build();

        String result = web.get()
            .uri("https://trusted-api.example.invalid/data")
            .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction
                    .oauth2AuthorizedClient(authorized))
            .retrieve()
            .bodyToMono(String.class)
            .block();

        assertEquals("Bearer test-token-never-use-in-production",
            result);
    }
}
```

Chạy:

```bash
mvn test
```

Mục tiêu là **12 bài test** khi code được đặt đúng tên file/package, JDK và dependencies tương thích. Đây là giáo trình tự chạy; **không khẳng định đã chạy test trên máy của bạn**. Những test sử dụng `mockOAuth2Client` **không** gọi AS, không xác thực chữ ký access token thật, không test PKCE/OIDC callback; test WebClient cuối dùng `ExchangeFunction` giả, không kết nối host minh họa. Vì thế cần tích hợp AS sandbox riêng trước production.

### 8.5. Đọc kết quả test đúng cách

- Public 200 và anonymous redirect xác nhận HTTP security của web app vẫn chạy.
- `mockUser` và `mockOAuth2Client` mô phỏng **hai đối tượng độc lập**: Authentication và authorized client. Khi gọi qua `WebTestClient`, WebFlux argument resolver gắn client vào handler parameter.
- Test alias chứng minh `@RegisteredOAuth2AuthorizedClient("demo-client")` và `registrationId="demo-client"` tương đương.
- Test scopes/refresh kiểm meta an toàn, không phụ thuộc raw token.
- Bob/alias-query xác nhận route không dùng một global username hoặc lấy registration ID do client tùy ý khai.
- Test POST không CSRF 403 và POST có CSRF 200 khẳng định browser session vẫn cần CSRF dù outbound API dùng OAuth2.
- Test outbound không cần mạng, nhưng có thể kiểm đúng `Authorization: Bearer ...` do OAuth2 filter thêm cho **request đã chọn**.

## 9. Thực hành thủ công với AS thật

Dùng:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Truy cập `http://localhost:8080/public` → trả `public`. Mở `http://localhost:8080/client/metadata` khi chưa login → redirect đến `/login`. Đăng nhập bằng user demo `viewer` và password `viewer123`.

Tại thời điểm controller cần `@RegisteredOAuth2AuthorizedClient("demo-client")`, manager phải tìm authorized client trong storage hoặc thực hiện grant `client_credentials` với AS. Vì `token-uri=https://idp.example.invalid/token` chỉ là placeholder, **không kỳ vọng thành công với AS demo chưa thay**. Đây không phải lỗi của annotation.

Để chạy với AS được tổ chức cấp quyền:

- Thay `client-id` và `client-secret` bằng client credentials thật từ secret manager.
- Thay `token-uri` bằng HTTPS token endpoint đã xác minh.
- Xin scope phù hợp `inventory.read` theo provider.
- Xác định AS cấp access token cho application hay user; đảm bảo downstream API chấp nhận đúng audience và scope.
- Khi browser login và call endpoint, chỉ trả DTO metadata. Nếu token request thất bại, không expose full OAuth2 error description chứa secret.

Test với curl không có cookie chỉ quan sát redirect:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/client/metadata
```

`curl` không tự giữ session cookie giữa hai câu lệnh. Để mô phỏng browser login cần cookie jar, form CSRF token và redirect flow; đơn giản hơn dùng browser cho login và `mvn test` cho injection. Không dùng token thật trong shell history/log.

### 9.1. Nếu dùng OIDC Login thay form login

Một ứng dụng thực có thể cấu hình:

```java
return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/", "/login",
            "/oauth2/authorization/**",
            "/login/oauth2/code/**").permitAll()
        .anyExchange().authenticated())
    .oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults())
    .build();
```

Đây là cấu hình **thay thế**, không phải bean chain thứ hai cùng matcher. Với `authorization_code`, provider/registration/redirect URI/`openid` được cấu hình đúng, user login OIDC và Spring tạo `OAuth2AuthenticationToken` cùng authorized client liên quan. Controller dùng `@RegisteredOAuth2AuthorizedClient("enterprise-oidc")` có thể chọn token được ủy quyền cho đúng provider. Nếu login bằng registration `google` mà muốn token của `inventory-service`, cần một authorization riêng hoặc client_credentials, không thể tự đổi ID Token Google thành access token của inventory.

## 10. Khi không nên dùng annotation

### 10.1. Service method hoặc scheduled job

Thay vì:

```java
// SAI NGỮ CẢNH: không có WebFlux handler argument resolver.
public Mono<String> scheduled(
    @RegisteredOAuth2AuthorizedClient("demo-client")
    OAuth2AuthorizedClient client) {
    return Mono.just("wrong pattern");
}
```

Nên inject `ReactiveOAuth2AuthorizedClientManager` và gọi `authorize(...)` với `OAuth2AuthorizeRequest`:

```java
@Service
class ClientGateway {
    private final ReactiveOAuth2AuthorizedClientManager manager;

    ClientGateway(ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    Mono<OAuth2AuthorizedClient> authorize(
            String registrationId, Authentication principal) {

        OAuth2AuthorizeRequest req =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(registrationId)
                .principal(principal)
                .build();

        return manager.authorize(req);
    }
}
```

Đoạn trên là fragment cần imports và manager phù hợp. Nếu dùng `DefaultReactiveOAuth2AuthorizedClientManager` theo web, nó có thể cần `ServerWebExchange` trong context. Với background work cần `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientService` và service principal được quản lý, không mượn quyền admin từ request giả.

### 10.2. Chỉ cần load token đã lưu

`ReactiveOAuth2AuthorizedClientService.loadAuthorizedClient(registrationId, principalName)` có thể đọc client đã lưu. Nó **không đồng nghĩa** với authorize/refresh. Nếu mục tiêu là token hợp lệ để gọi API, dùng manager/provider đúng lifecycle thay vì cứ lấy stale token và gửi.

### 10.3. Cần tenant/user-specific authorization phức tạp

Annotation chọn registration thuận tiện nhưng policy tenant/resource ownership vẫn là trách nhiệm của service/API. Không lấy registration ID từ `X-Client` public header rồi cho phép chọn mọi client secret của tổ chức. Không dùng `@Registered...` để tự bypass `@PreAuthorize` hay `authorizeExchange`.

## 11. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Annotation không được nhận | Thiếu OAuth2 client dependency/registration, không gọi qua WebFlux handler | Kiểm starter, `oauth2Client()`, controller/WebTestClient |
| Client registration không tồn tại | Sai key `demo-client`/`provider`/`client-id` | Đối chiếu properties và annotation |
| Client chưa có access token | Grant chưa diễn ra hoặc manager không hỗ trợ | Xác định authorization_code/client_credentials, token endpoint |
| App gọi token URI giả bị lỗi | Demo AS placeholder | Thay bằng AS thật; test mock chỉ kiểm injection |
| Đã login nhưng authorized client chưa có | Authentication và authorization grant khác nhau | Kiểm authorized client store/grant |
| API upstream trả 401 | Không có Bearer header, token invalid/expired/wrong audience | Kiểm WebClient filter, token metadata, Resource Server |
| API trả 403 | Thiếu scope/role/object-level permission | Kiểm API policy, không tự bỏ permission |
| Refresh token null | AS/grant không cấp | Kiểm null, không giả định luôn có refresh |
| Token của user khác bị dùng | Shared singleton cache hoặc principal không phân vùng | Store theo principal/tenant, test đa user |
| Token xuất hiện trong JSON/log | Serialize nguyên authorized client hoặc in Authorization header | DTO an toàn, redaction và xử lý sự cố lộ token |
| POST browser 403 dù đã login | CSRF thiếu/sai | Giữ CSRF cho session, gửi token hợp lệ |
| WebClient không gửi Bearer | Thiếu `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Cài filter và gắn attribute |
| WebClient gửi token sang host lạ | Bật default authorized client quá rộng | Client/request tường minh, allowlist destination |
| Test mock pass nhưng production lỗi | Mock không kiểm AS/token/PKCE/network | Thêm sandbox integration e2e |
| Blocking trên Netty | Gọi `block()` trong controller | Trả `Mono`/`Flux`, để WebFlux subscribe |

### 11.1. Không coi annotation là công cụ authentication

Spring Security vẫn cần xác thực request qua WebSession, OAuth2 Login, Basic hoặc cơ chế được thiết kế. Một authorized client chứa token **không** tự cho user mọi role trong ứng dụng. `hasRole("ADMIN")`/`@PreAuthorize`/tenant check vẫn cần theo domain.

### 11.2. Không gửi nhầm ID Token

ID Token của OIDC phục vụ đăng nhập RP; Resource Server cần access token được cấp cho audience/scope đúng. JWT có chữ ký không phải lý do hợp lệ để dùng ID Token trên API bất kỳ.

### 11.3. Không lộ token qua debug/exception

Tránh `log.info("client={}", authorizedClient)`, full HTTP headers, JSON serialization tự do và URL query token. Token value có thể bị ghi bởi filter/tracing; cấu hình redaction và log chỉ metadata an toàn với correlation ID.

## 12. Checklist trước production

1. Xác nhận app đóng vai trò **OAuth2 Client**, không nhầm với AS/Resource Server.
2. Dùng client registration/provider đáng tin, grant type/scopes/token URI/redirect URI chính xác.
3. Đặt annotation ở **annotated WebFlux controller method parameter** với registration ID tường minh.
4. Bảo đảm Authentication của request và authorized client principal/tenant phù hợp, không dùng global token.
5. Quản lý refresh/renew/expiry/revocation và persistence đúng khi nhiều app instances.
6. Cài OAuth2 filter cho `WebClient`, chỉ đính token ở request đi tới host được phép, không bật default quá rộng.
7. Không đưa access/refresh/ID tokens hoặc client secret ra browser/log, sử dụng safe DTO.
8. Giữ CSRF cho state-changing browser session routes; OAuth2 Client outbound không loại bỏ CSRF.
9. Kiểm Resource Server audience, issuer, expiration, scope và domain permissions.
10. Test annotation bằng `mockOAuth2Client` kết hợp `WebTestClient`, và test grant/refresh với AS sandbox thật.
11. Với scheduled/background jobs, dùng service manager, tránh lấy web exchange không tồn tại.
12. Giám sát lỗi authorization token endpoint bằng correlation IDs không lộ credential, có timeout/retry theo policy.
13. Nâng Spring Security/Boot theo bản hỗ trợ và chạy lại regression tests.

## 13. Tự đánh giá

**1.** `@RegisteredOAuth2AuthorizedClient("demo-client")` tìm gì?  
Authorized client theo registration và principal/context được quản lý bởi reactive OAuth2 Client infrastructure, không phải client ID trần.

**2.** Vì sao `ClientRegistration` khác `OAuth2AuthorizedClient`?  
Một cái là cấu hình với AS; cái còn lại gắn cấu hình đó với principal và token đã được cấp.

**3.** Method parameter nên là `OAuth2AuthorizedClient` hay `Mono<OAuth2AuthorizedClient>`?  
Thông dụng chính thức là **`OAuth2AuthorizedClient`**; resolver reactive xử lý bất đồng bộ trước khi truyền đối số.

**4.** Cùng registration có thể dùng cho Alice và Bob không?  
Có, nhưng phải lưu/tra đúng principal/tenant và không dùng lẫn user tokens.

**5.** Nếu browser đã đăng nhập thì client_credentials token đã tồn tại chưa?  
Không chắc. Browser Authentication và OAuth2 authorization grant là các trạng thái khác nhau.

**6.** `client_credentials` token có nhất thiết là token người dùng không?  
Không. Nó thường là quyền của **client application**.

**7.** Vì sao cần `ServerOAuth2AuthorizedClientExchangeFilterFunction`?  
Để `WebClient` đọc authorized client attribute và gắn Bearer token trên outbound request theo cấu hình.

**8.** Có thể trả `OAuth2AuthorizedClient` trực tiếp trong JSON không?  
Không nên: nó có access token và có thể refresh token. Dùng DTO metadata đã chọn lọc.

**9.** `mockOAuth2Client` có xác minh token thật từ AS không?  
Không. Nó đưa authorized client giả vào test context, không kiểm token endpoint/refresh/PKCE.

**10.** Local WebFlux controller có thể dùng annotation trong scheduled job không?  
Không theo handler argument resolver thông dụng. Background code dùng service-based reactive manager.

**11.** Tại sao POST session lại có thể 403 dù client đã có access token?  
Vì CSRF bảo vệ browser cookie/session mutations độc lập với OAuth2 client token.

**12.** Có nên bật `setDefaultOAuth2AuthorizedClient(true)` trên shared WebClient không?  
Rủi ro rò token sang host không đúng mục đích; ưu tiên explicit client per request và trusted host allowlist.

### Nguồn tài liệu chính thức

- Spring Security 6.5, *Reactive Authorized Client Features*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5, *OAuth2 Client Core Interfaces*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security 6.5, *OAuth2 Client Authorization Grants*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- Spring Security 6.5, *OAuth2 WebFlux Overview*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 API, `RegisteredOAuth2AuthorizedClient`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/annotation/RegisteredOAuth2AuthorizedClient.html
- Spring Security 6.5 API, `OAuth2AuthorizedClientArgumentResolver` (reactive): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/result/method/annotation/OAuth2AuthorizedClientArgumentResolver.html
- Spring Security, *Testing OAuth2 Clients in WebFlux*: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security, *Testing WebFlux Authentication*: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html

**Tóm tắt:** `@RegisteredOAuth2AuthorizedClient` cho phép controller WebFlux nhận authorized client đúng registration/principal theo infrastructure Spring Security Reactive. Cần phân biệt config registration với token/grant, dùng `WebClient` OAuth2 filter để gửi access token **tới đúng API**, không lộ credential và không biến annotation thành authentication/authorization thay thế. Kiểm thử bằng `mockOAuth2Client` là phù hợp cho resolver, nhưng phải thêm integration thật cho grant, refresh và security khi đưa vào production.