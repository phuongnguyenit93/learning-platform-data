# Lựa chọn clientRegistrationId hoặc OAuth2AuthorizedClient cho từng lời gọi

## Mục tiêu học tập

Bài này thuộc phần **OAuth2 Client** của **Spring Security reactive / Spring WebFlux**. Sau khi học, bạn có thể:

1. Phân biệt `ClientRegistration`, `clientRegistrationId`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager` và `ServerOAuth2AuthorizedClientExchangeFilterFunction`.
2. Chọn một OAuth2 client **theo từng outbound WebClient request**, dùng `.attributes(clientRegistrationId("..."))` hoặc `.attributes(oauth2AuthorizedClient(client))`.
3. Giải thích tại sao hai cách không đồng nghĩa trong mọi tình huống, nhất là khi app hỗ trợ **nhiều người dùng, nhiều OAuth2 providers hoặc nhiều downstream APIs**.
4. Kết hợp `@RegisteredOAuth2AuthorizedClient` trong WebFlux controller, `ReactiveSecurityContextHolder` và kho authorized client phù hợp.
5. Cấu hình **user-delegated authorization_code** so với **service-to-service client_credentials**, kể cả một scheduled job không có `ServerWebExchange`.
6. Nhận diện rủi ro của implicit defaults, forwarding token sai audience, SSRF và token exfiltration.
7. Chạy ví dụ Java 17 offline với WebClient filter thật và fake authorization manager/transport, kiểm thử `StepVerifier` cho hai registrations, client explicit và request không có token.
8. Xử lý token gần hết hạn, refresh/reauthorization và phản hồi 401/403 từ Resource Server đúng theo Spring Security reactive 6.5.

> Chỉ dùng **reactive OAuth2 Client**: `ServerOAuth2AuthorizedClientExchangeFilterFunction` và `ReactiveOAuth2AuthorizedClientManager`. API Servlet là `ServletOAuth2AuthorizedClientExchangeFilterFunction` và không thay thế trực tiếp cho WebFlux. Outbound OAuth2 Client cũng khác với `oauth2ResourceServer().jwt()`, vốn **kiểm tra token inbound**.

## 1. Vì sao cần chọn client trên mỗi request?

Một WebFlux backend có thể gọi nhiều dịch vụ với quyền khác nhau:

~~~text
User/browser ----> Spring WebFlux application
                       |
                       +---> Catalog API
                       |       OAuth2 registration: catalog-client
                       |       Required scope: catalog.read
                       |
                       +---> Billing API
                       |       OAuth2 registration: billing-client
                       |       Required scope: billing.read
                       |
                       +---> Profile API
                               OAuth2AuthorizedClient
                               của user đã đồng ý quyền truy cập
~~~

Không nên gửi access token của Profile (Alice) đến Billing hoặc token có audience Catalog đến CRM. Bearer token là một credential: ai sở hữu token có thể thử sử dụng nó trong phạm vi server chấp nhận.

### 1.1. Các thuật ngữ nền tảng

| Đối tượng | Vai trò | Có gì bên trong? |
|---|---|---|
| `ClientRegistration` | Metadata OAuth2 client đã đăng ký trong Spring. | `registrationId`, client ID/secret, grant type, scopes, provider/token/authorization URIs. |
| `clientRegistrationId` | String khóa để tra cấu hình. | Ví dụ `"catalog-client"`, **không** nhất thiết giống client ID ở IdP. |
| `OAuth2AuthorizedClient` | Một client đã được cấp access token cho một resource owner. | ClientRegistration, `principalName`, access token và optional refresh token. |
| `ReactiveOAuth2AuthorizedClientManager` | Quản lý authorize/re-authorize, load/save, refresh/renew. | Phối hợp với providers, service/repository, principal/context. |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Tích hợp OAuth2 Client vào reactive WebClient. | Đọc request attributes, lấy authorized client, đặt HTTP Bearer header. |
| `ServerOAuth2AuthorizedClientRepository` | Lưu authorized client theo request/principal WebFlux. | Dữ liệu authorized clients phục vụ web requests. |
| `ReactiveOAuth2AuthorizedClientService` | Dịch vụ tra/lưu authorized clients cấp ứng dụng. | Thường key theo registrationId + principalName. |

**Quan trọng:** Một registration có thể gắn với nhiều authorized clients:

~~~text
ClientRegistration ID = "profile-login"

  OAuth2AuthorizedClient(user="alice")
      -> accessToken A

  OAuth2AuthorizedClient(user="bob")
      -> accessToken B
~~~

Vì vậy, **chỉ biết registration ID chưa có nghĩa đã biết user/token nào**. Manager cần principal/current security context tương ứng. Ngược lại, một user có thể có nhiều authorized clients cho nhiều registrations.

### 1.2. Registration ID khác với client ID từ provider

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog-client:
            client-id: catalog-application-id-issued-by-provider
            authorization-grant-type: client_credentials
~~~

Đoạn YAML trên là **mảnh cấu hình để nhận diện tên trường**, chưa đủ chạy client_credentials vì còn secret và provider/token URI. Đối số `clientRegistrationId("catalog-client")` phải là **khóa catalog-client trong YAML**, không phải chuỗi `catalog-application-id-issued-by-provider`.

## 2. WebClient OAuth2 filter hoạt động thế nào?

Cấu hình phổ biến:

~~~java
@Bean
WebClient oauthWebClient(
    WebClient.Builder builder,
    ReactiveOAuth2AuthorizedClientManager manager) {

    var oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return builder.filter(oauth2).build();
}
~~~

Đây là **mảnh method cấu hình trong Spring bean**. Filter không phải Authorization Server. Nó là cầu nối giữa một outbound `WebClient` request và authorized client manager.

~~~text
WebClient outgoing request
        |
        v
ServerOAuth2AuthorizedClientExchangeFilterFunction
        |
        +-- Có oauth2AuthorizedClient(object)?
        |       -> dùng object cụ thể;
        |          manager có thể re-authorize/refresh
        |
        +-- Có clientRegistrationId("id")?
        |       -> dùng id + principal/context,
        |          manager lookup/authorize/refresh
        |
        +-- Không chỉ rõ client?
                -> không có implicit token trừ khi
                   bật cấu hình default phù hợp
        |
        v
Authorization: Bearer <access-token>
        |
        v
Downstream Resource Server kiểm tra token/permission
~~~

Đây là **sơ đồ khái niệm**. Không khuyến nghị đặt cả `oauth2AuthorizedClient(...)` và `clientRegistrationId(...)` mâu thuẫn trong cùng request rồi dựa vào thứ tự precedence nội bộ của filter. Hãy **chọn một cách cho mỗi lời gọi**.

### 2.1. Những gì filter KHÔNG tự bảo đảm

- Token chắc chắn có scope phù hợp hay audience của API đích.
- Client caller có quyền dùng một service registration nhạy cảm.
- Authorization Server luôn cấp/refresh được token.
- Host được yêu cầu là hợp lệ và không bị SSRF.
- Resource Server sẽ cho phép business operation.
- CSRF trên API inbound đã được bảo vệ.
- Bất kỳ request không có OAuth2 attribute nào cũng sẽ tự có token.

Các ràng buộc ấy cần được kiểm tra ở Authentication, Authorization, manager config, outbound routing và resource server.

## 3. Cách 1: chọn clientRegistrationId trên từng request

Khi biết registration nào dành cho endpoint, nhưng chưa có một authorized client cụ thể:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> readCatalog(WebClient client) {
    return client.get()
        .uri("https://catalog-api.example.test/v1/items")
        .attributes(clientRegistrationId("catalog-client"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Đây là mảnh method Java; `client` phải được cấu hình OAuth2 filter. Khi subscribe, manager có thể:

1. Tra `ClientRegistration` theo `catalog-client`.
2. Xác định principal/authorization context.
3. Tìm `OAuth2AuthorizedClient` đã lưu.
4. Nếu cần và có provider phù hợp, xin token mới hoặc refresh/reauthorize.
5. Trả object để filter đặt `Authorization: Bearer ...` lên request HTTP.

**Không cam kết luôn có token chỉ bằng cách truyền ID**. `client_credentials` có thể xin token trực tiếp, còn `authorization_code` của user có thể cần redirect browser/consent. Nếu grant/provider không hỗ trợ, principal sai hoặc token service lỗi, request có thể không được authorize.

### 3.1. Hai requests trong cùng pipeline

~~~java
Mono<String> catalog = webClient.get()
    .uri("https://catalog-api.example.test/v1/items")
    .attributes(clientRegistrationId("catalog-client"))
    .retrieve().bodyToMono(String.class);

Mono<String> billing = webClient.get()
    .uri("https://billing-api.example.test/v1/invoices")
    .attributes(clientRegistrationId("billing-client"))
    .retrieve().bodyToMono(String.class);

return Mono.zip(catalog, billing)
    .map(tuple -> tuple.getT1() + " | " + tuple.getT2());
~~~

Đây là mảnh code trong service. Cùng WebClient bean nhưng mỗi request có token selection riêng. Không sửa một global default registration giữa hai requests song song vì sẽ tạo race/credential leak.

### 3.2. Đừng chọn registration/URL trực tiếp từ user input

~~~java
// PHẢN VÍ DỤ bảo mật, không dùng trong production:
@GetMapping("/proxy")
Mono<String> proxy(@RequestParam String registrationId,
                   @RequestParam String targetUrl) {
    return webClient.get()
        .uri(targetUrl)
        .attributes(clientRegistrationId(registrationId))
        .retrieve().bodyToMono(String.class);
}
~~~

Lỗi: caller tự chọn **OAuth2 registration** và **URL nhận token**. Nó có thể kích hoạt client credentials mạnh hơn quyền của caller hoặc gửi Bearer token đến domain attacker (**SSRF/token exfiltration**).

Thay bằng routing do server kiểm soát:

~~~text
Operation listCatalog
   -> required app permission: catalog:read
   -> trusted registration: catalog-client
   -> trusted host: https://catalog-api.example.test

Operation listBilling
   -> required app permission: billing:read
   -> trusted registration: billing-client
   -> trusted host: https://billing-api.example.test
~~~

Nếu có multi-tenant dynamic routing, tenant/client registration phải được xác minh trong allowlist có policy, không lấy raw registrationId/URL từ query mà không validate.

## 4. Cách 2: truyền OAuth2AuthorizedClient object cụ thể

Nếu controller đã có một object authorized client **tin cậy**, ví dụ nhờ `@RegisteredOAuth2AuthorizedClient`:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@GetMapping("/my-profile")
Mono<String> profile(
    @RegisteredOAuth2AuthorizedClient("profile-login")
    OAuth2AuthorizedClient authorizedClient) {

    return webClient.get()
        .uri("https://profile-api.example.test/v1/me")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve().bodyToMono(String.class);
}
~~~

Đây là mảnh controller, cần `webClient` inject và các imports tương ứng. `@RegisteredOAuth2AuthorizedClient` từ `org.springframework.security.oauth2.client.annotation` có argument resolver cho Spring Security reactive controller.

Điều kiện cần kiểm tra:

- `authorizedClient.getClientRegistration().getRegistrationId()` dành cho profile API.
- `authorizedClient.getPrincipalName()` thuộc **resource owner đang được xử lý**, không phải user/tenant khác.
- Access token có audience/scope/issuer phù hợp với API đích.
- Nếu token đã hết hạn, manager/provider có thể refresh; không khẳng định explicit object luôn bị gửi nguyên token cũ.
- Khi chưa có consent/authorization, xử lý login flow hoặc lỗi; **không fallback sang service/admin credential**.
- Không đưa `authorizedClient.getAccessToken().getTokenValue()` vào API JSON, logs, URL hoặc browser.

### 4.1. So sánh hai lựa chọn

| Tình huống | `clientRegistrationId("...")` | `oauth2AuthorizedClient(client)` |
|---|---|---|
| Input | Khóa cấu hình Spring | Đối tượng đã chọn |
| Phụ thuộc principal | Manager/repository tra theo ngữ cảnh | Object có `principalName` riêng |
| Chưa có token | Manager có thể xin token nếu grant hỗ trợ | Object phải đã được giải quyết |
| Refresh/re-authorize | Có thể | Có thể |
| User-delegated OAuth2 | Cần đúng current principal/store/consent | Rõ object của đúng user |
| Service-to-service | Phù hợp nếu có manager service và principal đúng | Phù hợp nếu manager đã cấp object cho job |
| Lỗi phổ biến | Sai registration/context | Dùng object của người khác |

**Không có lựa chọn nào an toàn tuyệt đối chỉ bằng chữ ký API**. Cả hai phải bảo đảm token được gửi đến trusted host và đúng quyền.

### 4.2. Hai OAuth2AuthorizedClient trong một controller

~~~java
@GetMapping("/dashboard")
Mono<String> dashboard(
    @RegisteredOAuth2AuthorizedClient("calendar-login")
    OAuth2AuthorizedClient calendar,
    @RegisteredOAuth2AuthorizedClient("crm-login")
    OAuth2AuthorizedClient crm) {

    Mono<String> events = webClient.get()
        .uri("https://calendar-api.example.test/v1/events")
        .attributes(oauth2AuthorizedClient(calendar))
        .retrieve().bodyToMono(String.class);

    Mono<String> contacts = webClient.get()
        .uri("https://crm-api.example.test/v1/contacts")
        .attributes(oauth2AuthorizedClient(crm))
        .retrieve().bodyToMono(String.class);

    return Mono.zip(events, contacts)
        .map(pair -> pair.getT1() + " / " + pair.getT2());
}
~~~

Đây là mảnh controller. Nó minh họa rằng token calendar không tự được gửi sang CRM. Nếu một provider không có consent hoặc bị từ chối, xử lý lỗi theo UX thay vì lấy token provider còn lại cho qua.

## 5. Đúng principal, Reactor Context và authorized-client repository

Trong WebFlux, Authentication thuộc **Reactor Context** theo subscription. Cần giữ context khi outbound client tìm authorized client của user.

~~~text
WebFlux request của Alice
      |
      +-- ReactiveSecurityContextHolder
              Authentication principal = Alice
              |
              +-- clientRegistrationId("crm-login")
                      |
                      +-- lookup authorized client:
                          registration = crm-login
                          principal = Alice
                          -> token Alice, không phải token Bob
~~~

### 5.1. Chỗ lưu dữ liệu nào?

- `ServerOAuth2AuthorizedClientRepository` chịu trách nhiệm load/save authorized clients trong WebFlux **web request context**, liên quan `ServerWebExchange`.
- `ReactiveOAuth2AuthorizedClientService` cung cấp lưu trữ ở **application level**, thường keyed bởi registrationId và principalName.
- `ServerSecurityContextRepository` là kho **Authentication/SecurityContext** cho đăng nhập, khác với kho OAuth2 access/refresh tokens.
- `ReactiveOAuth2AuthorizedClientManager` điều phối các nguồn và cấp/refresh theo grant.

### 5.2. Gắn ServerWebExchange nếu cấu hình cần

Filter có static helper:

~~~java
.attributes(
    ServerOAuth2AuthorizedClientExchangeFilterFunction
        .serverWebExchange(exchange))
~~~

`exchange` phải là `ServerWebExchange` do request hiện tại cung cấp. Không mặc định mọi manager đều cần gọi helper này; phụ thuộc constructor, repository và context sẵn có.

Nếu không có web request (scheduler/worker), đừng tạo fake ServerWebExchange để qua lỗi. Hãy dùng manager service-level, mục 6.

### 5.3. Không subscribe/block sai vị trí

~~~java
// Sai trong controller WebFlux:
service.callCrm().subscribe();
return Mono.empty();
~~~

Detached subscription có thể mất security context và lỗi. Cách đúng là **return publisher**:

~~~java
return service.callCrm();
~~~

`block()` cũng không được dùng trên event loop. Với một chương trình **console main** hoặc test, blocking tại ranh giới ngoài của ứng dụng có thể chấp nhận và sẽ được minh họa trong mục 7.

## 6. client_credentials trong background job

Một scheduled job không có browser, HTTP request hay principal người dùng. Với machine-to-machine, nên dùng:

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`

và `ReactiveOAuth2AuthorizedClientService` để lưu service token. Spring Security phân biệt rõ manager này với `DefaultReactiveOAuth2AuthorizedClientManager` dùng trong web-request context.

~~~java
@Bean
ReactiveOAuth2AuthorizedClientManager backgroundManager(
    ReactiveClientRegistrationRepository registrations,
    ReactiveOAuth2AuthorizedClientService service) {

    var manager =
        new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, service);

    manager.setAuthorizedClientProvider(
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build());

    return manager;
}
~~~

Mảnh code này cần imports tương ứng và được đặt trong configuration class. Sử dụng service principal ổn định để quản lý token:

~~~java
Authentication servicePrincipal =
    new UsernamePasswordAuthenticationToken(
        "service:reporting", "N/A",
        AuthorityUtils.NO_AUTHORITIES);

OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reporting-service")
        .principal(servicePrincipal)
        .build();

return backgroundManager.authorize(authorizeRequest)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Authorization unavailable")))
    .flatMap(client -> webClient.get()
        .uri("https://reporting-api.example.test/v1/summary")
        .attributes(oauth2AuthorizedClient(client))
        .retrieve().bodyToMono(String.class));
~~~

Đây là mảnh method với backgroundManager và webClient đã inject. Sau khi manager cấp token, truyền **authorized client chính xác** vào lời gọi. Không biến service credential thành fallback cho user thiếu OAuth2 consent: đó có thể là **confused deputy**.

**Lưu ý:** Nếu filter WebClient được cấu hình bằng manager khác với `backgroundManager`, có thể xảy ra lookup/refresh ở hai nơi. Trong production nên nối filter với manager/store nhất quán hoặc tạo dedicated WebClient cho background service.

## 7. Ví dụ Java 17 chạy độc lập, không cần IdP

Ta sử dụng **chính `ServerOAuth2AuthorizedClientExchangeFilterFunction` thật** của Spring Security, nhưng thay bằng:

- `ReactiveOAuth2AuthorizedClientManager` fixture trả hai authorized clients có tokens test.
- `ExchangeFunction` in-memory nhận request **sau khi filter gắn Bearer**, trả header vào fake response.
- `ReactiveSecurityContextHolder.withAuthentication(...)` cho context principal test.

**Không có network traffic** tới `trusted-api.invalid` hoặc `idp.invalid`. Token strings chỉ là dữ liệu unit test, **không phải credential**. Không dùng fake manager hoặc echo Authorization header này trong production.

### 7.1. Cấu trúc và build

~~~text
oauth2-per-call-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/PerCallDemo.java
    └── test/java/example/PerCallDemoTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'oauth2-per-call-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.5.16'
    }
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.PerCallDemo'
}

dependencies {
    implementation 'org.springframework:spring-webflux'
    implementation 'org.springframework.security:spring-security-oauth2-client'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng Java 17+ và Gradle/Wrapper tương thích. Spring Boot BOM quản lý các phiên bản framework/security trong project console này.

### 7.2. Main class đầy đủ

Tệp `src/main/java/example/PerCallDemo.java`:

~~~java
package example;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

public final class PerCallDemo {

    private PerCallDemo() {
    }

    static ClientRegistration registration(String id) {
        return ClientRegistration.withRegistrationId(id)
            .clientId("fixture-client-" + id)
            .clientSecret("fixture-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri("https://idp.invalid/token")
            .scope("demo.read")
            .build();
    }

    static OAuth2AuthorizedClient fixture(String id, String value) {
        var token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            value,
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2099-01-01T00:00:00Z"));

        return new OAuth2AuthorizedClient(
            registration(id), "demo-principal", token);
    }

    private static final Map<String, OAuth2AuthorizedClient> CLIENTS =
        Map.of(
            "catalog", fixture("catalog", "fixture-catalog"),
            "billing", fixture("billing", "fixture-billing"));

    static Authentication principal() {
        return new UsernamePasswordAuthenticationToken(
            "demo-principal", "N/A",
            List.of(new SimpleGrantedAuthority("ROLE_DEMO")));
    }

    static WebClient client() {
        // CHỈ TEST: không gọi Authorization Server thật.
        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            if (request.getAuthorizedClient() != null) {
                return Mono.just(request.getAuthorizedClient());
            }

            OAuth2AuthorizedClient selected =
                CLIENTS.get(request.getClientRegistrationId());

            return selected == null
                ? Mono.empty()
                : Mono.just(selected);
        };

        var oauth =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);

        // CHỈ TEST: không có HTTP network, chỉ xem Bearer header.
        ExchangeFunction fakeTransport = request -> {
            String authorization =
                request.headers().getFirst(HttpHeaders.AUTHORIZATION);

            String body = authorization == null
                ? "(no-token)"
                : authorization;

            return Mono.just(
                ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, "text/plain")
                    .body(body)
                    .build());
        };

        return WebClient.builder()
            .filter(oauth)
            .exchangeFunction(fakeTransport)
            .build();
    }

    static Mono<String> byRegistration(WebClient client, String id) {
        return client.get()
            .uri("https://trusted-api.invalid/resource")
            .attributes(clientRegistrationId(id))
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal()));
    }

    static Mono<String> byClient(
        WebClient client, OAuth2AuthorizedClient authorized) {

        return client.get()
            .uri("https://trusted-api.invalid/resource")
            .attributes(oauth2AuthorizedClient(authorized))
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal()));
    }

    static Mono<String> withoutChoice(WebClient client) {
        return client.get()
            .uri("https://trusted-api.invalid/resource")
            .retrieve()
            .bodyToMono(String.class)
            .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                    principal()));
    }

    private static void verify(
        String label, String actual, String expected) {

        if (!expected.equals(actual)) {
            throw new IllegalStateException(label + " mismatch");
        }
        System.out.println(label + ": PASS");
    }

    public static void main(String[] args) {
        WebClient webClient = client();

        // block() chỉ ở ranh giới console main, KHÔNG ở WebFlux.
        verify("catalog-registration",
            byRegistration(webClient, "catalog").block(),
            "Bearer fixture-catalog");

        verify("billing-registration",
            byRegistration(webClient, "billing").block(),
            "Bearer fixture-billing");

        verify("explicit-authorized-client",
            byClient(webClient,
                fixture("catalog", "fixture-explicit")).block(),
            "Bearer fixture-explicit");

        verify("no-implicit-default",
            withoutChoice(webClient).block(),
            "(no-token)");
    }
}
~~~

Tại sao code này có giá trị học tập?

1. `ClientRegistration` được tạo cho hai IDs, cùng grant client_credentials nhưng client ID và token fixture khác nhau.
2. Fake `ReactiveOAuth2AuthorizedClientManager` cho thấy manager nhận `getClientRegistrationId()` hoặc `getAuthorizedClient()` để chọn object. Manager production phải làm OAuth2 thật.
3. `ServerOAuth2AuthorizedClientExchangeFilterFunction` là **filter thật**; nó đính kèm Bearer header.
4. `ExchangeFunction` fake intercept ở in-memory boundary, không kết nối tới domain .invalid.
5. `byRegistration` và `byClient` cùng dùng một WebClient nhưng có lựa chọn khác nhau.
6. `withoutChoice` xác minh không có implicit default thì request không tự có token.
7. Reactor Context mang principal; chỉ `main` dùng `block()` vì đây là CLI, không phải WebFlux server.

### 7.3. Chạy và kết quả mong đợi

~~~bash
gradle run
~~~

Hoặc `./gradlew run`, `gradlew.bat run` khi có Gradle Wrapper. **Stdout logic main** (không gồm log Gradle) kỳ vọng:

~~~text
catalog-registration: PASS
billing-registration: PASS
explicit-authorized-client: PASS
no-implicit-default: PASS
~~~

Đây là stdout **dự kiến từ code**, không phải khẳng định đã thực thi build trong quá trình biên soạn.

### 7.4. Kiểm thử bằng StepVerifier

Tệp `src/test/java/example/PerCallDemoTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PerCallDemoTest {

    private final WebClient client = PerCallDemo.client();

    @Test
    void catalogRegistrationUsesCatalogToken() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "catalog"))
            .expectNext("Bearer fixture-catalog")
            .verifyComplete();
    }

    @Test
    void billingRegistrationUsesBillingToken() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "billing"))
            .expectNext("Bearer fixture-billing")
            .verifyComplete();
    }

    @Test
    void explicitAuthorizedClientIsUsedForThisCall() {
        StepVerifier.create(
            PerCallDemo.byClient(client,
                PerCallDemo.fixture("catalog", "fixture-explicit")))
            .expectNext("Bearer fixture-explicit")
            .verifyComplete();
    }

    @Test
    void missingChoiceDoesNotSendBearer() {
        StepVerifier.create(
            PerCallDemo.withoutChoice(client))
            .expectNext("(no-token)")
            .verifyComplete();
    }

    @Test
    void oneCallDoesNotChangeGlobalDefault() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "catalog")
                .then(PerCallDemo.byRegistration(
                    client, "billing"))
                .then(PerCallDemo.withoutChoice(client)))
            .expectNext("(no-token)")
            .verifyComplete();
    }

    @Test
    void concurrentCallsKeepSeparateTokens() {
        StepVerifier.create(
            PerCallDemo.byRegistration(client, "catalog")
                .zipWith(
                    PerCallDemo.byRegistration(client, "billing")))
            .assertNext(pair -> {
                assertEquals("Bearer fixture-catalog", pair.getT1());
                assertEquals("Bearer fixture-billing", pair.getT2());
            })
            .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Kỳ vọng **6 test pass** với dependency/toolchain phù hợp; cần **chạy thật** để xác nhận trong môi trường riêng. Test không chứng minh IdP cấp token thật, refresh đúng hoặc resource server đã kiểm tra scope/audience. Những việc ấy cần integration tests với mock/real IdP và resource server.

**Không copy fakeTransport vào production:** Nó echo Authorization header trong response chỉ để test token giả. Với credential thật, tuyệt đối không log/echo token.

## 8. Cấu hình thực tế với nhiều registrations

Ví dụ YAML cho WebFlux Spring Boot app:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog-client:
            provider: corp
            client-id: ${CATALOG_CLIENT_ID}
            client-secret: ${CATALOG_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: catalog.read
          billing-client:
            provider: corp
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: billing.read
        provider:
          corp:
            token-uri: https://idp.example.test/oauth2/token
~~~

Biến môi trường ở `${...}` phải được cung cấp khi triển khai; không đưa secrets vào repository. URL `idp.example.test` là domain ví dụ; dùng token endpoint thật của provider và TLS. Đây là mẫu **client_credentials**: nếu cần token người dùng (authorization_code) thì cấu hình grant/redirect/scope và login/consent riêng.

### 8.1. WebClient filter không bật default

~~~java
@Configuration
public class OAuth2WebClientConfig {

    @Bean
    WebClient oauthWebClient(
        WebClient.Builder builder,
        ReactiveOAuth2AuthorizedClientManager manager) {

        var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);

        // Không gọi setDefaultOAuth2AuthorizedClient(true).
        // Không setDefaultClientRegistrationId trên shared WebClient.
        return builder.filter(filter).build();
    }
}
~~~

Đây là class minh họa cần imports. Spring Security reactive 6.5 có thể cung cấp default manager nếu chưa có bean tùy biến; khi có nhiều managers, cấu hình injection rõ bằng bean name/`@Qualifier`.

Mỗi business operation chỉ định client:

~~~java
Mono<String> catalog(WebClient oauthWebClient) {
    return oauthWebClient.get()
        .uri("https://catalog-api.example.test/v1/items")
        .attributes(clientRegistrationId("catalog-client"))
        .retrieve().bodyToMono(String.class);
}

Mono<String> billing(WebClient oauthWebClient) {
    return oauthWebClient.get()
        .uri("https://billing-api.example.test/v1/invoices")
        .attributes(clientRegistrationId("billing-client"))
        .retrieve().bodyToMono(String.class);
}
~~~

Với background `client_credentials`, nhớ manager được gắn với service-level store và principal. Ví dụ này không tự biến cấu hình web request manager thành background manager.

### 8.2. Hai implicit defaults cần cân nhắc kỹ

~~~java
// Cảnh báo: chỉ dùng khi WebClient đã bị giới hạn cho một đích tin cậy.
filter.setDefaultOAuth2AuthorizedClient(true);

filter.setDefaultClientRegistrationId("catalog-client");
~~~

- `setDefaultOAuth2AuthorizedClient(true)` có thể chọn authorized client liên quan đến current OAuth2 Authentication và đính kèm token cho requests thiếu explicit choice.
- `setDefaultClientRegistrationId("catalog-client")` đặt một registration mặc định.
- Hai setters có ý nghĩa khác nhau, **không bắt buộc bật cả hai**.
- Trên shared WebClient gọi nhiều APIs hoặc nhận arbitrary URL, mặc định có thể rò Bearer token sang host sai.

An toàn hơn: **tắt implicit defaults**, chọn attribute per call và giới hạn base URL/redirect destination. Nếu thật sự cần default, tạo WebClient riêng chỉ tới **một trusted origin**, có test không rò credential.

## 9. Resource server 401/403, token refresh và filter constructors

Authorized client manager có thể:

- Load token đã lưu theo `registrationId` và principal.
- Xin token khi có provider phù hợp.
- Refresh/renew khi access token hết hạn/sắp hết hạn và grant/refresh token hỗ trợ.
- Save authorized client mới hoặc remove trên failure theo policy.
- Trả empty/error khi flow không hỗ trợ hoặc IdP lỗi.

### 9.1. Hai constructors có failure behavior khác nhau

| Constructor của `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Xử lý response lỗi downstream |
|---|---|
| Nhận `ReactiveClientRegistrationRepository` + `ServerOAuth2AuthorizedClientRepository` | Có thể được cấu hình sẵn `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` cho một số OAuth2 error codes. |
| Nhận `ReactiveOAuth2AuthorizedClientManager` | **Không** tự cấu hình handler cho downstream HTTP 401/403. Nếu muốn xóa token cached không hợp lệ, phải gọi `setAuthorizationFailureHandler(...)` phù hợp store. |

**Không nói mọi 401 đều được refresh hoặc mọi 403 đều bị xóa khỏi cache.** Phải xác định Bearer error code và chính sách remove. Lạm dụng retry có thể tạo vòng lặp cấp token, tăng tải IdP và làm sai authorization.

| Downstream response | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| 401 + `invalid_token` | Token hết hạn/revoked/invalid | Refresh/re-authorize có kiểm soát, remove cached invalid token nếu policy |
| 403 + `insufficient_scope` | Token hợp lệ nhưng thiếu scope/role | Xem lại registration scope/consent/permissions, không retry vô hạn |
| 401 do sai `aud`/`iss` | Token cấp cho audience/provider khác | Sửa registration/token request/resource mapping |
| 429 | Rate limiting | Backoff có giới hạn |
| 5xx | Downstream lỗi | Retry chỉ khi idempotent, có timeout/circuit breaker |

### 9.2. Object explicit không bảo đảm token bất biến

Truyền `oauth2AuthorizedClient(client)` là chọn **authorized client hiện có**; manager có thể refresh token nếu được cấu hình. Test offline trong mục 7 dùng token còn hạn tới năm 2099 nên tập trung đo cơ chế lựa chọn, không đo refresh.

## 10. Các giới hạn an ninh

### 10.1. CSRF bảo vệ browser khác với outbound OAuth2

Nếu ứng dụng có session cookies, API POST/PUT/DELETE inbound từ browser vẫn cần **CSRF protection** tùy threat model. Chọn `clientRegistrationId` cho outbound call **không thay thế** CSRF token/Origin/SameSite policy.

`state`/PKCE của OAuth2 login callback cũng không thay CSRF protection cho nghiệp vụ sau login. Không tắt CSRF toàn ứng dụng chỉ vì đã dùng OAuth2 Client.

### 10.2. Bearer token và SSRF

Một token được gửi qua HTTPS đến **host attacker** vẫn bị rò cho attacker. Cần hostname allowlist, DNS/redirect controls và egress policy. Không cho request input quyết định URI và registration tùy ý.

Token audience/scope cũng cần được kiểm tra: cùng Authorization Server không có nghĩa tất cả services cùng tin một token.

### 10.3. Đừng tự relay token inbound

Một access token cấp cho API A không tự dành cho API B. Nếu cần delegation/token exchange, dùng flow phù hợp thay vì copy raw `Authorization` header sang mọi downstream. OIDC **ID Token** không thay access token cho resource API.

### 10.4. Service credential không làm caller có quyền

Trước khi backend dùng `billing-client` để gọi API mạnh, phải kiểm tra caller/tenant/business authorization. Đừng biến service token thành cách vượt qua quyền người dùng.

## 11. Những lỗi phổ biến

**1. Nhầm `registrationId` với client ID IdP.** Dùng khóa config Spring.

**2. Chỉ tạo OAuth2 WebClient filter rồi mong request nào cũng có token.** Chọn per-call attribute hoặc explicit default theo policy.

**3. Dùng global default trên WebClient đa mục đích.** Có thể gửi token tới external URL không dự tính.

**4. Đổi global default giữa hai calls đồng thời.** Dễ race; chọn qua request attributes.

**5. Tra authorized client chỉ bằng registration và không xét principal.** Có thể lấy token của Alice cho Bob.

**6. Giữ OAuth2AuthorizedClient trong singleton field.** Dễ dùng object người dùng trước cho người dùng sau.

**7. Dùng service credential thay user credential khi user thiếu consent.** Tạo confused deputy.

**8. Background job dùng manager web-request.** Dùng manager dựa trên ReactiveOAuth2AuthorizedClientService.

**9. Để user chọn raw target URL và registration.** SSRF/Bearer exfiltration; áp allowlist phía server.

**10. Dùng `block()`/`subscribe()` trong event loop.** Mất reactive properties và context; return Publisher.

**11. Tưởng OAuth2AuthorizedClient object tự bảo đảm token được resource server chấp nhận.** Downstream vẫn xác minh audience/scope/issuer.

**12. Nghĩ explicit object token không bao giờ refresh.** Manager có thể re-authorize/refresh.

**13. Nghĩ 401 downstream luôn xóa token cached.** Constructor manager không tự cài failure handler.

**14. Retry 403 insufficient_scope vô hạn.** Scope/policy sai không chữa bằng retry.

**15. Dùng ServletOAuth2AuthorizedClientExchangeFilterFunction trong WebFlux.** Sai API stack.

**16. Nhầm OAuth2 Client outbound với Resource Server inbound.** Hai vai trò khác nhau.

**17. Log Authorization/refresh token hoặc gửi chúng cho frontend.** Bearer token là credential.

**18. Tạo AuthorizedClient từ raw string do client gửi.** Không thay OAuth2 validation.

**19. Không test call thiếu attribute.** Có thể bỏ sót default token leak.

**20. Không kiểm tra principal/context trên background job.** Có thể dùng nhầm user token hoặc không tìm được authorized client.

## 12. Checklist trước triển khai

1. Đã có registrations đúng client ID, provider/token URI, grant/scopes?
2. Từng outbound call có chọn registration ID hoặc authorized client **tường minh**?
3. Destination URL là trusted host có allowlist/TLS/redirect constraints?
4. Caller có quyền kích hoạt operation dùng token đó không?
5. User-delegated client có principalName đúng và không bị share giữa tenants?
6. Background client_credentials dùng service-level manager/principal?
7. Manager có provider hỗ trợ grant và token refresh?
8. WebClient không bật global defaults nếu dùng chung nhiều hosts?
9. OAuth2 filter constructor/failure handler phù hợp 401/403 và cache store?
10. Không fallback user token sang service/admin token?
11. Không `block()`/`subscribe()` trong WebFlux request pipeline?
12. Không log/echo Bearer, client secret hoặc refresh token?
13. Có test các registration A/B, client explicit, thiếu attribute, concurrent calls?
14. Có integration tests IdP real/mocked cho issuance, refresh, revoke, expiry?
15. Resource Server kiểm tra token issuer/audience/scope và business authorization?
16. CSRF của inbound browser requests vẫn được bảo vệ?
17. Có chính sách thu hồi user OAuth2AuthorizedClient khi logout/revoke?
18. Khi thêm downstream, policy operations→registration/host được security review?

## 13. Tự kiểm tra có đáp án

**1.** `clientRegistrationId("catalog-client")` có truyền client ID IdP không?

**Đáp án:** Không, nó truyền registration key của Spring; manager dùng nó để tìm metadata và authorized client.

**2.** Đã có AuthorizedClient đúng user, chọn API nào?

**Đáp án:** `.attributes(oauth2AuthorizedClient(client))`, rồi để filter gắn token.

**3.** Có thể dùng chung WebClient cho Catalog và Billing không?

**Đáp án:** Có. Chọn attribute per request, không mutation global.

**4.** Vì sao một registrationId không xác định được riêng token của Alice?

**Đáp án:** Authorized client thường gắn registration **và principalName**; Bob có thể có object khác cùng registration.

**5.** Không có web request trong scheduled job thì dùng manager nào?

**Đáp án:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` với service principal ổn định.

**6.** `setDefaultOAuth2AuthorizedClient(true)` nguy hiểm ở đâu?

**Đáp án:** Shared WebClient có thể gửi token cho outbound calls không được chỉ định, kể cả host sai.

**7.** Resource Server trả 403 insufficient_scope có nên thử lại đến khi được không?

**Đáp án:** Không. Xem lại scopes/consent/authorization thay vì blind retry.

**8.** Test offline mục 7 xác nhận gì?

**Đáp án:** Nó kiểm tra request-specific token selection của filter bằng token fixtures, **không** chứng minh IdP token flow, token refresh hoặc JWT downstream validation.

**9.** OAuth2 Client có tự kiểm tra Bearer token inbound không?

**Đáp án:** Không. Cần Resource Server configuration riêng nếu ứng dụng cung cấp API nhận token.

**10.** Nếu outbound URI HTTPS nhưng do user nhập, có an toàn để gửi token không?

**Đáp án:** Chưa. HTTPS bảo vệ đường truyền đến chính host đó, không bảo đảm host đáng tin. Cần allowlist và chống SSRF.

## Tài liệu chính thức

- Spring Security 6.5 — Reactive OAuth2 Authorized Clients (per-call attributes): https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5 — Reactive OAuth2 Client WebClient Integration: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security — Reactive OAuth2 Core Interfaces and Managers: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc, constructor-specific failure handling: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- `OAuth2AuthorizeRequest` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizeRequest.html
- `@RegisteredOAuth2AuthorizedClient` Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/annotation/RegisteredOAuth2AuthorizedClient.html
- Spring Security — Reactive OAuth2 Client testing: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- RFC 6750 — Bearer Tokens: https://www.rfc-editor.org/rfc/rfc6750
