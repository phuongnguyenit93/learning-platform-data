# ReactiveAuthenticationManagerResolver<ServerWebExchange> và chọn bộ xác thực trong Gateway đa tenant

> **Phạm vi:** Spring Security Reactive (WebFlux), Java 17+, Spring Security 6.x và Spring Boot 3.3.x. Bài học giải thích cách chọn **ReactiveAuthenticationManager** theo ngữ cảnh request qua `ReactiveAuthenticationManagerResolver<ServerWebExchange>`; ứng dụng trong Gateway/API đa tenant, nhiều issuer JWT, HTTP Basic hoặc cơ chế riêng; cách tránh nhầm tenant, xung đột xác thực, request không match và rò quyền giữa tenant. Ví dụ dùng Spring Boot **3.3.13** để minh họa API Java 17; bản demo không phải lựa chọn phiên bản production năm 2026. Khi triển khai thực tế phải dùng nhánh được hỗ trợ và cập nhật vá bảo mật.

## 1. Khi nào một AuthenticationManager là chưa đủ?

Một gateway WebFlux nhận các loại request:

- `GET /tenants/alpha/whoami`: tài khoản của tenant **alpha**.
- `GET /tenants/beta/whoami`: tài khoản của tenant **beta**.
- `GET /api/reports`: Bearer JWT do một trong nhiều IdP được tin cậy cấp.
- `GET /public/health`: không đòi login nhưng vẫn có chính sách gateway riêng.

Nếu dùng một manager kiểm mọi credential, hệ thống có thể phát sinh lỗi:

1. Username `alex` tồn tại ở cả alpha và beta; nếu manager truy vấn một bảng user chung mà không ràng buộc tenant, người dùng alpha có thể được nhận nhầm ở beta.
2. Một gateway chấp nhận JWT từ nhiều issuer; một decoder chỉ biết khóa của issuer A sẽ từ chối token B dù B hợp lệ, hoặc tệ hơn developer tắt issuer/audience verification để “hỗ trợ tất cả”.
3. Một API cho service dùng HTTP Basic trong khi route khác dùng opaque introspection; yêu cầu không được phép trượt từ cơ chế này sang cơ chế khác khi credential sai.
4. Một implementation gọi network discovery theo `iss`/`Host`/`X-Tenant` do khách tùy ý gửi, tạo **SSRF** hoặc tin nhầm Authorization Server của kẻ tấn công.
5. Hai reactive authentication filters cùng cố xác thực request, hoặc một global WebFilter bị đăng ký lặp, làm lặp truy vấn database, introspection, metrics và các side effect.

`ReactiveAuthenticationManagerResolver<ServerWebExchange>` giúp **chọn đúng manager** cho một request. Nhưng nó **không tự xác minh credential**, không tự xác định quyền truy cập tài nguyên và không thay thế authorization.

### Bức tranh luồng

```text
                         HTTP request
                               |
                               v
                      SecurityWebFilterChain
                      (securityMatcher chọn chain)
                               |
                               v
                      AuthenticationWebFilter
                  requiresAuthenticationMatcher?
                               |
                    có credential thuộc scheme?
                               |
                               v
             ReactiveAuthenticationManagerResolver
                       .resolve(exchange)
                               |
              +----------------+----------------+
              |                                 |
        /tenants/alpha/**                 /tenants/beta/**
              |                                 |
              v                                 v
     alpha AuthenticationManager      beta AuthenticationManager
              |                                 |
         verify password/token             verify password/token
              |                                 |
              +----------------+----------------+
                               |
                     Authentication thành công
                               |
                     ReactiveSecurityContextHolder
                               |
                    authorizeExchange / service ACL
                               |
                        controller / downstream
```

**Điểm chốt:** giá trị route hoặc một issuer *được đọc từ token trước khi kiểm chữ ký* chỉ là **gợi ý định tuyến tới một verifier đã tin cậy**. Nó **không phải bằng chứng tenant hoặc identity**. Verifier và authorization mới kết luận token/người dùng có quyền trong tenant đó.

## 2. API chính xác: ReactiveAuthenticationManagerResolver<C>

Trong Spring Security, interface thuộc package:

```java
package org.springframework.security.authentication;

@FunctionalInterface
public interface ReactiveAuthenticationManagerResolver<C> {
    Mono<ReactiveAuthenticationManager> resolve(C context);
}
```

Đây là **chữ ký rút gọn để giải thích**; import class có sẵn từ thư viện, không tạo file trùng tên. Khi `C = ServerWebExchange`:

```java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String path = exchange.getRequest().getPath().value();
        return selectManagerForTrustedRoute(path);
    };
```

Mảnh trên là **pseudocode** vì `selectManagerForTrustedRoute` chưa định nghĩa. Nó cho thấy resolver nhận toàn bộ request context WebFlux, sau đó trả **Mono chứa một manager**.

Ba loại vai trò:

| Thành phần | Đầu vào | Kết quả | Trách nhiệm |
|---|---|---|---|
| `ServerWebExchangeMatcher` | `ServerWebExchange` | `Mono<MatchResult>` | Request này thuộc filter/chain nào? |
| `ServerAuthenticationConverter` | `ServerWebExchange` | `Mono<Authentication>` chưa xác thực | Credential nào được client gửi? |
| `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | `ServerWebExchange` | `Mono<ReactiveAuthenticationManager>` | Manager nào phải kiểm credential? |
| `ReactiveAuthenticationManager` | `Authentication` chưa xác thực | `Mono<Authentication>` authenticated hoặc error/empty | Credential có hợp lệ trong cơ chế đã chọn? |
| `ReactiveAuthorizationManager` | Authentication và context truy cập | Quyết định grant/deny | Principal được phép làm gì? |

**Resolver không trả `Authentication`.** Nếu bạn viết resolver trả một authenticated token chỉ vì header `X-Tenant: alpha`, đó là nhầm chức năng và có thể tạo lỗ hổng bypass authentication.

### 2.1 Mono nghĩa là gì?

`resolve(exchange)` trả `Mono<ReactiveAuthenticationManager>`:

- `Mono.just(manager)`: chọn được một manager cụ thể.
- `Mono.defer(...)`: chỉ quyết định ở thời điểm subscribe, hữu ích khi dựa vào trạng thái đã chuẩn bị cho request.
- `Mono.empty()`: không tìm được manager; **không xem empty là cho phép truy cập**. Cách xử lý tiếp theo phụ thuộc filter tích hợp, nên với route protected hãy chọn policy fail-closed rõ và test.
- `Mono.error(new BadCredentialsException(...))`: không thể chọn verifier hợp lệ; trong flow authentication, lỗi bảo mật phải dẫn đến từ chối, không tự chọn manager mặc định rộng hơn.

Phải tránh `block()` trong resolver trên Netty event-loop. Nếu lựa chọn manager yêu cầu database/network, dùng reactive client thật, hoặc có ranh giới scheduler cho API blocking, giới hạn concurrency, timeout và caching.

### 2.2 Resolver có thể là lambda, class hoặc implementation có sẵn

```java
ReactiveAuthenticationManagerResolver<ServerWebExchange> r =
    exchange -> Mono.just(preconfiguredManager);
```

Với **một manager**, resolver như trên không thêm nhiều giá trị; tạo `new AuthenticationWebFilter(preconfiguredManager)` là đủ. Resolver có ích khi một **request** thực sự cần lựa chọn khác nhau, chẳng hạn tenant theo route hoặc issuer của Bearer token.

## 3. Ba tầng điều phối — đừng hoán đổi

Spring Security WebFlux có nhiều cấp lựa chọn:

1. **`ServerHttpSecurity.securityMatcher(...)`:** request thuộc **SecurityWebFilterChain** nào? Chỉ chain đầu tiên khớp theo thứ tự `@Order` được chọn.
2. **`AuthenticationWebFilter.setRequiresAuthenticationMatcher(...)`:** authentication filter cụ thể có cần thử tạo authentication với request đó không?
3. **`ReactiveAuthenticationManagerResolver<ServerWebExchange>.resolve(...)`:** nếu converter phát credential, chọn manager nào để xác minh nó?

Sau các bước trên, `authorizeExchange(...)` và service-level policies kiểm quyền truy cập.

```text
         request
            |
    chọn chain đầu tiên match
            |
     trong chain đó:
       (i)  requiresAuthenticationMatcher
       (ii) ServerAuthenticationConverter
       (iii) resolver -> manager
       (iv) manager.authenticate(...)
       (v)  authorizeExchange(...)
            |
      business operation
```

**Không cần resolver nếu bạn đã tách hoàn toàn 2 tenant thành 2 SecurityWebFilterChain độc lập và mỗi chain có một manager.** Nhưng khi một gateway phục vụ hàng chục tenant theo một pattern chung, resolver giúp dùng **một filter**, chọn đúng manager từ danh sách server-side tin cậy.

### So sánh lựa chọn kiến trúc

| Bài toán | Công cụ phù hợp | Lý do |
|---|---|---|
| `/api/**` dùng Bearer; `/web/**` dùng form session | Nhiều `SecurityWebFilterChain` + `securityMatcher` | Hai mô hình HTTP/security khác nhau |
| Một chain xác thực bằng Basic, nhiều tenant theo URL | `AuthenticationWebFilter` + `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | Cùng credential converter, manager khác |
| Một chain nhận JWT từ 2 issuer hợp lệ | `JwtIssuerReactiveAuthenticationManagerResolver` | Chọn JWT verifier theo issuer **trong allowlist** |
| Một tenant dùng opaque token, tenant khác dùng JWT | Resolver chọn manager JWT hoặc opaque; phải có policy xác định loại token | Cùng chain nhưng verification khác nhau |
| Một route hỗ trợ Basic và Bearer | Converter/matcher rõ ràng, hoặc chain tách theo contract | Đừng “thử lần lượt cho đến khi có manager thành công” |
| Một user đã login nhưng thiếu quyền record tenant khác | Authorization và business-level ACL | Resolver không quyết định quyền record |
| API gateway chuyển tiếp token user | Resource server authentication + token relay có kiểm soát | Resolver không tự đổi audience/token |
| App tự lấy client-credentials token để gọi API | `ReactiveOAuth2AuthorizedClientManager` | Đây là **outbound OAuth2 client**, không phải inbound AuthenticationManagerResolver |

## 4. Nguồn thông tin dùng để chọn tenant

Một resolver có thể đọc host, path, header, mTLS identity, hoặc dữ liệu token đã định dạng. Nhưng **mức độ tin cậy khác nhau**.

| Nguồn lựa chọn | Có thể dùng làm selector? | Bắt buộc bảo vệ |
|---|---|---|
| Route `/tenants/alpha/**` | Có | Chỉ cho tenant trong allowlist; manager xác thực đúng tenant; kiểm tenant-object ACL |
| Header `X-Tenant: alpha` | Có, **chỉ như hint** | Không gán quyền tenant chỉ dựa trên header; đối chiếu identity/issuer/claim đã verify |
| `Host` / `Forwarded` / `X-Forwarded-Host` | Có với trusted proxy | Phải loại spoofed forwarded headers; kiểm canonical host/tenant mapping |
| `iss` trong JWT chưa verify | Có để chọn một verifier đã tin | **Không** dùng làm bằng chứng issuer/token đáng tin trước khi validate signature+claims |
| `aud` trong JWT chưa verify | Không đủ để cấp quyền; có thể là hint kỹ thuật khi thiết kế chuẩn | Verifier phải kiểm audience thực tế; tránh token substitution |
| SNI hoặc mTLS client cert đã verify ở edge | Có khi hợp đồng tin cậy được thiết lập | Proxy phải xác thực/chuyển identity chống spoofing; không tin header client tự khai |
| Query `?tenant=alpha` | Chỉ dùng chọn tentative tenant nếu business thực sự cần | Không tự cấp role; cần authorization đối tượng và audit |
| Tên file hoặc mã user do client nhập | Không phải nguồn quyền | Không dùng làm identity để lựa verifier rồi cấp quyền |
| Issuer ID từ tenant registry nội bộ | Có | Registry chỉ admin tin cậy chỉnh; có kiểm TLS/issuer/JWKS và vòng đời config |

**Định tuyến tenant** (tenant resolution) và **ủy quyền tenant** (tenant authorization) là hai bước khác nhau. Request `/tenants/beta/orders/1` có thể chọn manager beta, nhưng người dùng vẫn phải có quyền beta và quyền record `orders/1`.

## 5. Cách AuthenticationWebFilter dùng resolver

`AuthenticationWebFilter` thuộc package `org.springframework.security.web.server.authentication`, có hai constructor:

```java
new AuthenticationWebFilter(ReactiveAuthenticationManager manager);

new AuthenticationWebFilter(
    ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver);
```

Flow có ý nghĩa:

1. Xem `requiresAuthenticationMatcher`.
2. Chuyển HTTP request thành một `Authentication` chưa được kiểm qua `ServerAuthenticationConverter`.
3. Nếu converter trả `Mono.empty()`, **không có authentication attempt**; tiếp tục chain.
4. Khi có credential, gọi resolver để xác định manager phù hợp.
5. Manager kiểm credential và phát authenticated result hoặc `AuthenticationException`.
6. Thành công: ghi SecurityContext trong Reactor pipeline / repository được cấu hình. Thất bại: `ServerAuthenticationFailureHandler` trả 401 hay response theo policy.

```java
// Mảnh cấu hình, không phải toàn bộ application.
AuthenticationWebFilter filter =
    new AuthenticationWebFilter(tenantResolver);

filter.setRequiresAuthenticationMatcher(
    ServerWebExchangeMatchers.pathMatchers(
        HttpMethod.GET, "/tenants/**"));

filter.setServerAuthenticationConverter(
    new ServerHttpBasicAuthenticationConverter());

filter.setSecurityContextRepository(
    NoOpServerSecurityContextRepository.getInstance());
```

**Không để default converter bị hiểu nhầm.** `AuthenticationWebFilter` mặc định dùng `ServerHttpBasicAuthenticationConverter`; trong ví dụ vẫn khai báo rõ để người học biết nó đọc `Authorization: Basic ...`, **không** đọc Bearer JWT, API key hoặc cookie theo suy đoán.

### Credential sai khác credential vắng mặt

`ServerAuthenticationConverter.convert(exchange)` trả empty khi **không có credential thuộc cơ chế**. Khi người dùng gửi **Basic sai password**, manager phải báo lỗi, **không** dùng `Mono.empty()` để cho phép filter khác thử và “cứu” request.

Với gateway nhiều credential types, cần policy minh bạch: chọn manager theo route/issuer được tin cậy, không fallback từ invalid user token sang app token có quyền cao hơn.

## 6. Hai implementation có sẵn đáng biết

### 6.1 ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver

Spring Security cung cấp `ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver`. Có thể định tuyến manager theo `ServerWebExchangeMatcher`:

```java
var resolver =
    ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver
        .builder()
        .add(ServerWebExchangeMatchers.pathMatchers(
             "/tenants/alpha/**"), alphaManager)
        .add(ServerWebExchangeMatchers.pathMatchers(
             "/tenants/beta/**"), betaManager)
        .build();
```

Đây là **mảnh Java** với biến `alphaManager`/`betaManager` đã có và imports tương ứng. `Builder.add(matcher, manager)` trả về một resolver ghép các cặp matcher → manager. Mỗi match phải được kiểm để không đặt matcher rộng `/tenants/**` trước rule hẹp và vô tình chọn sai manager.

`setDefaultAuthenticationManager(manager)` tồn tại, nhưng **không** nên đặt một manager có quyền rộng làm fallback cho tenant không biết; chọn default **deny/unknown-tenant** và test. Nếu hệ thống thực sự có một tenant mặc định, nó phải là chính sách nghiệp vụ tường minh và **không** là “được phép khi tenant header không hợp lệ”.

### 6.2 JwtIssuerReactiveAuthenticationManagerResolver

Spring Security OAuth2 Resource Server Reactive có:

`org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver`

Nó được dùng khi một gateway/resource server chấp nhận JWT từ **một tập issuer tin cậy**:

```java
JwtIssuerReactiveAuthenticationManagerResolver resolver =
    JwtIssuerReactiveAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://login.alpha.example/realms/main",
            "https://login.beta.example/realms/main");

http
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2
        .authenticationManagerResolver(resolver));
```

Đây là mảnh config Spring Security 6.3+/6.5. Muốn chạy thật phải có IdP/JWKS và `SecurityWebFilterChain` phù hợp. `fromTrustedIssuers` **không** tự đánh giá business ACL/tenant ownership. Nó chọn manager theo `iss` mà token khai báo, **chỉ nếu issuer nằm trong danh sách tin**.

**Chú ý bảo mật:** giá trị `iss` được đọc ở bước chọn decoder **trước khi JWT được verify**. Chỉ dùng nó để chọn một manager đã cấu hình từ allowlist; **sau đó** decoder phải kiểm chữ ký, issuer, timestamps và các validators (bao gồm audience phù hợp). Một attacker có thể tự tạo token với `iss=https://evil.example`; không được gọi discovery/JWKS của evil để tạo một manager tự động rồi chấp nhận token đó.

### 6.3 Không nhầm JWT issuer resolver với Servlet

| Reactivity | Đúng interface/class | Không copy nhầm |
|---|---|---|
| WebFlux | `ReactiveAuthenticationManagerResolver<ServerWebExchange>` | `AuthenticationManagerResolver<HttpServletRequest>` |
| WebFlux JWT multi issuer | `JwtIssuerReactiveAuthenticationManagerResolver` | `JwtIssuerAuthenticationManagerResolver` (Servlet) |
| Reactive JWT manager | `JwtReactiveAuthenticationManager` | `JwtAuthenticationProvider` (Servlet) |
| WebFlux chain | `ServerHttpSecurity` + `SecurityWebFilterChain` | `HttpSecurity` + `SecurityFilterChain` |
| WebFlux decoder | `ReactiveJwtDecoder` | `JwtDecoder` Servlet-oriented API |
| Reactive request | `ServerWebExchange` | `HttpServletRequest` |

## 7. Thứ tự Spring Security chains và resolver

Một gateway có thể tổ chức:

```text
@Order(0)  /api/tenant/**  -> JWT multi-issuer resolver
@Order(1)  /legacy/**      -> Basic per-tenant resolver
@Order(2)  fallback        -> deny-all
```

Trong cách này:

- `securityMatcher` chọn **chain** theo URL.
- Chain JWT có built-in OAuth2 Resource Server, không tự viết Bearer token parsing.
- Chain legacy có một `AuthenticationWebFilter` với resolver chọn credential manager theo route.
- Fallback deny-all giúp URL mới không vô tình nằm ngoài security.
- Giữa các chain, tránh thứ tự matcher rộng đứng trước matcher hẹp.

**Không bắt mọi route chạy chung một resolver** khi authentication models quá khác nhau. Một resolver có thể chọn manager, nhưng nó không tự thay converter Basic thành Bearer hay giải quyết CORS/CSRF/cookie/session giữa browser và API.

### Ví dụ chính sách route

| Nhóm route | Credential scheme | Resolver/manager | Session | Failure |
|---|---|---|---|---|
| `/tenants/alpha/**` | Basic trong demo; production thường JWT/mTLS | Alpha manager | Stateless demo | 401 Basic challenge |
| `/tenants/beta/**` | Basic trong demo | Beta manager | Stateless demo | 401 Basic challenge |
| `/api/**` | Bearer JWT | JwtIssuerReactiveAuthenticationManagerResolver | Stateless (tùy cấu hình) | 401 invalid token |
| `/web/**` | Form/OIDC login | Login filters + provider flow | Browser session | 302/login hoặc 401 phù hợp |
| `/actuator/health` | Public chỉ health non-sensitive | Chain policy riêng | Không | 200 nếu được cho phép |
| URL không rõ | Không | Fallback deny-all | Không | 403/401 theo policy |

## 8. Thiết kế fail-closed cho unknown tenant

Một resolver nên có hành vi xác định cho **tenant không tồn tại**:

```text
/tenants/alpha/whoami -> manager alpha
/tenants/beta/whoami  -> manager beta
/tenants/gamma/whoami -> FAIL CLOSED (không chọn alpha làm fallback)
/tenants//whoami      -> không hợp lệ
/tenants/../alpha     -> không dùng raw input để đoán tenant
```

Có thể dùng `Mono.error(new BadCredentialsException("Unsupported tenant"))` trong authentication flow hoặc một manager cố định luôn từ chối; status phụ thuộc exception handling/filter. **Không bao giờ** để `managers.get(tenant) == null` rồi lấy `managerDefaultWithAdminPrivileges`.

Một route valid chưa có credential cũng phải bị authorization chặn; converter empty không có nghĩa “anonymous được phép” nếu route cần authentication.

### Bảo vệ tenant ID trong URL

Tenant segment nên được giới hạn bằng format/allowlist **do server xác định**, ví dụ `[a-z][a-z0-9-]*`, và so với registry chỉ cho tenant active. Không tự nối string này vào SQL schema, hostname, issuer URI hoặc secret path chưa validate.

Một cách tổ chức an toàn:

1. Parse tenant đúng **một nơi** theo route matcher, không từ nhiều header mâu thuẫn.
2. Lookup tenant trong registry server-side có trạng thái active.
3. Chọn manager gắn với tenant đã được đăng ký.
4. Manager xác minh credential.
5. Authorization đối chiếu **tenant trong route** với tenant/issuer/claims đã được xác minh.
6. Business service kiểm ownership/tenant của bản ghi, ngay cả khi route-level check đã qua.

## 9. Demo runnable — cùng username, 2 tenant, 2 manager, 1 AuthenticationWebFilter

Bài minh họa bằng **HTTP Basic trên localhost** để quan sát resolver chọn đúng password verifier mà **không cần IdP/JWKS online**. Đây **không phải kiến trúc login tenant production**, nơi thường dùng OIDC/JWT hoặc mTLS. Có hai tenant:

- `alpha`: user `alex`, password học tập `alpha-only-dev`, authority `TENANT_ALPHA`.
- `beta`: user **cũng là `alex`**, nhưng password `beta-only-dev`, authority `TENANT_BETA`.

**Điều cần chứng minh:** credential đúng cho alpha **không** đăng nhập được vào beta dù username trùng; resolver chọn manager dựa trên **route được nhận diện**, manager xác minh credential của **tenant đó**, và authorization yêu cầu authority đúng tenant.

### 9.1 Cấu trúc

```text
webflux-tenant-resolver/
  settings.gradle
  build.gradle
  src/main/java/demo/tenant/TenantResolverApplication.java
  src/main/java/demo/tenant/TenantManagerResolver.java
  src/main/java/demo/tenant/TenantSecurityConfiguration.java
  src/main/java/demo/tenant/TenantController.java
  src/test/java/demo/tenant/TenantResolverTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-tenant-resolver'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.tenant'
version = '1.0.0'

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Demo chỉ dùng GET, giữ default CSRF cho các method không an toàn; không thêm Servlet starter. Dependencies được quản lý bởi Spring Boot plugin. Bản này minh họa API 6.3, không có IdP thật.

### 9.2 Spring Boot main

**src/main/java/demo/tenant/TenantResolverApplication.java**

```java
package demo.tenant;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TenantResolverApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantResolverApplication.class, args);
    }
}
```

### 9.3 TenantManagerResolver.java

```java
package demo.tenant;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

public final class TenantManagerResolver
        implements ReactiveAuthenticationManagerResolver<ServerWebExchange> {

    private static final Pattern ROUTE = Pattern.compile(
        "^/tenants/([a-z][a-z0-9-]*)/whoami$");

    private final Map<String, ReactiveAuthenticationManager> managers;
    private final Map<String, AtomicInteger> selections;

    public TenantManagerResolver(
            Map<String, ReactiveAuthenticationManager> managers) {
        this.managers = Map.copyOf(managers);
        this.selections = new ConcurrentHashMap<>();
        for (String tenant : managers.keySet()) {
            this.selections.put(tenant, new AtomicInteger());
        }
    }

    @Override
    public Mono<ReactiveAuthenticationManager> resolve(
            ServerWebExchange exchange) {

        return Mono.defer(() -> {
            String path = exchange.getRequest()
                .getPath().pathWithinApplication().value();

            Matcher matcher = ROUTE.matcher(path);
            if (!matcher.matches()) {
                return Mono.error(new BadCredentialsException(
                    "Unsupported tenant route"));
            }

            String tenant = matcher.group(1);
            ReactiveAuthenticationManager manager =
                managers.get(tenant);

            if (manager == null) {
                return Mono.error(new BadCredentialsException(
                    "Unsupported tenant"));
            }

            // Dùng trong bài test, không log credential.
            selections.get(tenant).incrementAndGet();
            return Mono.just(manager);
        });
    }

    public int selectedCount(String tenant) {
        AtomicInteger count = selections.get(tenant);
        return count == null ? 0 : count.get();
    }
}
```

**Cơ chế:**

- `implements ReactiveAuthenticationManagerResolver<ServerWebExchange>` là mục đích của bài.
- `Map.copyOf(managers)` chốt bảng manager cho demo; không tạo manager tùy ý từ input của khách.
- Regex chỉ nhận route `/tenants/{id}/whoami` có cấu trúc phù hợp; id tiếp tục được kiểm trong map allowlist.
- `Mono.defer(...)` bảo đảm resolve xảy ra khi publisher được subscribe. Không gọi `block()` hay làm discovery network.
- Unknown route/tenant trả `BadCredentialsException` thay vì một tenant default.
- `AtomicInteger` đếm manager selection để test **không lựa sai tenant**. Đây không phải counter production cho bảo mật; đa request đồng thời có thể làm việc so trước/sau toàn cục không phù hợp, nên các test demo chạy tuần tự.
- **Không implement `WebFilter` và không @Component** class này; nó được đăng ký dưới dạng resolver bean, tránh bị xem như global WebFilter chạy ngoài Security chain.

### 9.4 TenantSecurityConfiguration.java

```java
package demo.tenant;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.HttpBasicServerAuthenticationEntryPoint;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.authentication.ServerHttpBasicAuthenticationConverter;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class TenantSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    private static ReactiveAuthenticationManager manager(
            String password, String authority,
            PasswordEncoder encoder) {

        UserDetails alex = User.withUsername("alex")
            .password(encoder.encode(password))
            .authorities(authority)
            .build();

        var users = new MapReactiveUserDetailsService(alex);
        var manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    TenantManagerResolver tenantResolver(PasswordEncoder encoder) {
        return new TenantManagerResolver(Map.of(
            "alpha", manager("alpha-only-dev",
                "TENANT_ALPHA", encoder),
            "beta", manager("beta-only-dev",
                "TENANT_BETA", encoder)));
    }

    @Bean
    @Order(0)
    SecurityWebFilterChain tenantChain(
            ServerHttpSecurity http,
            TenantManagerResolver resolver) {

        var entryPoint = new HttpBasicServerAuthenticationEntryPoint();
        entryPoint.setRealm("tenant-demo");

        // Filter chỉ thuộc SecurityWebFilterChain; không là @Bean WebFilter.
        var tenantFilter = new AuthenticationWebFilter(resolver);
        tenantFilter.setServerAuthenticationConverter(
            new ServerHttpBasicAuthenticationConverter());
        tenantFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                HttpMethod.GET, "/tenants/**"));
        tenantFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance());
        tenantFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(entryPoint));

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/tenants/**"))
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/tenants/alpha/whoami")
                    .hasAuthority("TENANT_ALPHA")
                .pathMatchers(HttpMethod.GET,
                    "/tenants/beta/whoami")
                    .hasAuthority("TENANT_BETA")
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(entryPoint))
            .addFilterAt(
                tenantFilter, SecurityWebFiltersOrder.AUTHENTICATION)
            .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain denyAllFallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

**Giải thích cấu hình:**

1. Mỗi tenant có **ReactiveAuthenticationManager riêng**, dùng `UserDetailsRepositoryReactiveAuthenticationManager` với `MapReactiveUserDetailsService` riêng và password được BCrypt encode.
2. `"alex"` có mặt cả hai tenant nhưng password và authority khác. Việc dùng cùng username giúp test lỗi **cross-tenant authentication**.
3. `tenantResolver(...)` trả bean kiểu `TenantManagerResolver`, **không** là `ReactiveAuthenticationManager` bean toàn cục, giúp tránh Spring Boot tự dùng nhầm làm manager của chain khác.
4. `new AuthenticationWebFilter(resolver)` là API chính xác: filter tự gọi resolver khi có Basic authentication attempt.
5. `setServerAuthenticationConverter(new ServerHttpBasicAuthenticationConverter())` bảo đảm chỉ Basic credential được parser đọc. Header Bearer, API key hoặc cookie phiên không được tự coi hợp lệ.
6. `setRequiresAuthenticationMatcher(...)` hạn chế filter ở **GET /tenants/**`. `POST` không tự trở thành route được xác thực bởi filter này.
7. `NoOpServerSecurityContextRepository` giữ authentication cho **request hiện tại** qua Reactor Context, không lưu làm session login cho request kế tiếp.
8. `httpBasic(...disable())` ngăn **built-in Basic filter thứ hai** được thêm vào chain, vì chúng ta đã tự tạo AuthenticationWebFilter đọc Basic. Đây là cách tránh request bị xác thực lặp.
9. `formLogin(...disable())` ngăn browser form filter tham gia tenant API chain.
10. `exceptionHandling.authenticationEntryPoint(...)` xử lý trường hợp thiếu credential vào route protected, còn failure handler trên filter xử lý Basic sai. Cả hai dùng HTTP Basic challenge 401.
11. `authorizeExchange` kiểm authority tenant cụ thể, **không** dùng `authenticated()` đơn thuần để cấp quyền ngang tenant.
12. Chain fallback chỉ deny route còn lại. **Không** có securityMatcher trên fallback, nên nó match request không nằm trong chain `/tenants/**`.
13. Demo vẫn bật CSRF mặc định cho unsafe methods; mọi route được demo chủ đích là GET. Nếu mở rộng POST/PUT/DELETE, phải thiết kế CSRF/CORS/authentication theo threat model mới, không tự bỏ lớp bảo vệ.

### 9.5 TenantController.java

```java
package demo.tenant;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class TenantController {

    @GetMapping("/tenants/{tenant}/whoami")
    public Mono<String> whoami(
            @PathVariable String tenant,
            Principal principal) {

        return Mono.just(tenant + ":" + principal.getName());
    }
}
```

**Không dựa vào `@PathVariable tenant` để tự nhận là authenticated.** Route tenant chỉ được trả về sau Security filter và authorization. Trong nghiệp vụ thật phải kiểm **tenant ID từ identity đã xác minh** và quyền record, đặc biệt ở những route dynamic không có `hasAuthority("TENANT_ALPHA")` hardcoded.

### 9.6 Chạy và quan sát

```bash
gradle bootRun
```

Khi có Gradle Wrapper phù hợp: `./gradlew bootRun` hoặc Windows `gradlew.bat bootRun`. Với PowerShell, có thể cần dùng `curl.exe` để không gọi alias.

```bash
# Alpha credential đúng. Curl sẽ hỏi password:
curl -i -u alex http://localhost:8080/tenants/alpha/whoami
# Nhập alpha-only-dev

# Beta credential đúng:
curl -i -u alex http://localhost:8080/tenants/beta/whoami
# Nhập beta-only-dev

# Cố dùng credential alpha trên URL beta:
curl -i -u alex http://localhost:8080/tenants/beta/whoami
# Nhập alpha-only-dev

# Không gửi Basic:
curl -i http://localhost:8080/tenants/alpha/whoami

# Tenant unknown:
curl -i -u alex http://localhost:8080/tenants/gamma/whoami
```

Kết quả **dự kiến**:

```text
GET /tenants/alpha/whoami + Basic alex/alpha-only-dev  -> 200 alpha:alex
GET /tenants/beta/whoami  + Basic alex/beta-only-dev   -> 200 beta:alex
GET /tenants/beta/whoami  + Basic alex/alpha-only-dev  -> 401
GET /tenants/alpha/whoami + no Basic                   -> 401
GET /tenants/gamma/whoami + Basic alex/anything        -> 4xx; never 200
```

Credential/pw trên chỉ là training data không có giá trị ngoài localhost. Production cần TLS, password/secret manager, bruteforce controls, identity provider phù hợp và rate limits.

## 10. WebTestClient: kiểm đúng manager và cách ly tenant

**src/test/java/demo/tenant/TenantResolverTest.java**

```java
package demo.tenant;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class TenantResolverTest {

    @Autowired
    WebTestClient client;

    @Autowired
    TenantManagerResolver resolver;

    @Test
    void alphaWithAlphaPasswordSucceedsAndSelectsOnce() {
        int before = resolver.selectedCount("alpha");

        client.get().uri("/tenants/alpha/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("alpha:alex");

        assertEquals(before + 1, resolver.selectedCount("alpha"));
    }

    @Test
    void betaWithBetaPasswordSucceedsAndSelectsOnce() {
        int before = resolver.selectedCount("beta");

        client.get().uri("/tenants/beta/whoami")
            .headers(h -> h.setBasicAuth("alex", "beta-only-dev"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("beta:alex");

        assertEquals(before + 1, resolver.selectedCount("beta"));
    }

    @Test
    void alphaPasswordCannotAuthenticateInBeta() {
        int beforeBeta = resolver.selectedCount("beta");

        client.get().uri("/tenants/beta/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(beforeBeta + 1, resolver.selectedCount("beta"));
    }

    @Test
    void betaPasswordCannotAuthenticateInAlpha() {
        int beforeAlpha = resolver.selectedCount("alpha");

        client.get().uri("/tenants/alpha/whoami")
            .headers(h -> h.setBasicAuth("alex", "beta-only-dev"))
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(beforeAlpha + 1, resolver.selectedCount("alpha"));
    }

    @Test
    void missingCredentialDoesNotSelectAnyManager() {
        int alpha = resolver.selectedCount("alpha");
        int beta = resolver.selectedCount("beta");

        client.get().uri("/tenants/alpha/whoami")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Basic .*");

        assertEquals(alpha, resolver.selectedCount("alpha"));
        assertEquals(beta, resolver.selectedCount("beta"));
    }

    @Test
    void bearerHeaderIsNotAcceptedAsBasicAuthentication() {
        int alpha = resolver.selectedCount("alpha");

        client.get().uri("/tenants/alpha/whoami")
            .header(HttpHeaders.AUTHORIZATION, "Bearer fake-token")
            .exchange()
            .expectStatus().isUnauthorized();

        assertEquals(alpha, resolver.selectedCount("alpha"));
    }

    @Test
    void unknownTenantFailsClosed() {
        int alpha = resolver.selectedCount("alpha");
        int beta = resolver.selectedCount("beta");

        client.get().uri("/tenants/gamma/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().is4xxClientError();

        assertEquals(alpha, resolver.selectedCount("alpha"));
        assertEquals(beta, resolver.selectedCount("beta"));
    }

    @Test
    void unrelatedRouteCannotUseTenantBasicAuthentication() {
        int alpha = resolver.selectedCount("alpha");
        int beta = resolver.selectedCount("beta");

        client.get().uri("/unlisted")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().is4xxClientError();

        assertEquals(alpha, resolver.selectedCount("alpha"));
        assertEquals(beta, resolver.selectedCount("beta"));
    }

    @Test
    void sessionCookieAloneDoesNotAuthenticate() {
        client.get().uri("/tenants/alpha/whoami")
            .cookie("SESSION", "invented-session-id")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unsafePostDoesNotUseGetOnlyAuthenticationFilter() {
        int alpha = resolver.selectedCount("alpha");

        client.post().uri("/tenants/alpha/whoami")
            .headers(h -> h.setBasicAuth("alex", "alpha-only-dev"))
            .exchange()
            .expectStatus().isForbidden();

        assertEquals(alpha, resolver.selectedCount("alpha"));
    }
}
```

**10 phương thức test** kiểm:

1. Alpha và beta đúng credential trả 200, manager được chọn một lần.
2. Cùng username nhưng password của tenant khác **không** được dùng thành công.
3. Không có header Basic → converter không phát Authentication → manager resolver không bị gọi và route vẫn 401.
4. Header Bearer không được custom Basic converter coi hợp lệ.
5. Tenant không nằm trong allowlist không nhận manager alpha/beta làm fallback.
6. Route ngoài `/tenants/**` không kích hoạt resolver.
7. Cookie giả không tạo authenticated session vì `NoOpServerSecurityContextRepository`.
8. Unsafe POST không được matcher GET nhận; CSRF và authorization đều không cho qua.

**Lưu ý QA:** các test dựa trên thiết kế API/Javadoc, chưa có log build/test Gradle chạy trong môi trường tác giả. Nếu production dùng proxy rewrite path, hãy test đường dẫn mà Spring WebFlux thực sự nhận và xử lý normalization của HTTP stack.

### 10.1 Tại sao test đếm manager selection?

`AtomicInteger` tăng khi `TenantManagerResolver.resolve(...)` tìm được manager. Nó xác nhận một request Basic hợp lệ/sai password được đưa đến **một** manager thuộc tenant phù hợp. Tuy nhiên:

- Counter đo **số lần chọn manager**, không trực tiếp đo số lần manager.authenticate hay số lần query DB.
- Để đo retry/subscription, instrument reactive manager hoặc user repository ở test.
- Shared counter có thể bị ảnh hưởng bởi tests chạy song song hoặc HTTP traffic khác; demo chạy tuần tự.
- Không dựa vào counter này như cơ chế rate limit hoặc audit production.
- Khi converter trả empty, resolver có thể không được gọi; điều này phù hợp flow chuẩn của AuthenticationWebFilter.

## 11. Production JWT đa issuer: lựa chọn và verify đúng cách

Demo Basic giúp thấy rõ resolver, nhưng Gateway production thường dùng Bearer JWT. Spring Security đã cung cấp `JwtIssuerReactiveAuthenticationManagerResolver`; **ưu tiên nó** khi yêu cầu chỉ là nhận token từ nhiều issuers được phép.

### 11.1 Mẫu WebFlux Resource Server với trusted issuers

```java
package example.jwt;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerReactiveAuthenticationManagerResolver;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class MultiIssuerSecurityConfiguration {

    @Bean
    SecurityWebFilterChain jwtApi(ServerHttpSecurity http) {
        var resolver =
            JwtIssuerReactiveAuthenticationManagerResolver
                .fromTrustedIssuers(
                    "https://login.alpha.example/realms/main",
                    "https://login.beta.example/realms/main");

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.authenticationManagerResolver(resolver))
            .build();
    }
}
```

**Đây là phương án thay thế demo Basic**, không dán class này cạnh `TenantSecurityConfiguration` trong cùng project mà không thiết kế lại chains. Để chạy thực cần IdP/JWKS thực sự, issuer hợp lệ và token đúng target. URL `.example` chỉ là minh họa, không phải IdP online.

**Đọc đúng:**

- Built-in `oauth2ResourceServer` cung cấp cách lấy Bearer token từ request; bạn không cần tự parse Bearer từ query/cookie.
- Resolver dùng claim issuer để **chọn** đúng `JwtReactiveAuthenticationManager` trong số issuer tin cậy.
- Theo tài liệu Spring Security 6.5, việc khởi tạo manager/JWK metadata có thể **lazy** theo issuer khi request đầu tiên đến, giảm dependency startup nhưng làm lần đầu có thể phụ thuộc network IdP.
- Xác minh chữ ký, issuer, expiry và validator cấu hình là trách nhiệm của decoder/manager.
- `authenticated()` **không đủ** với Gateway dữ liệu nhiều tenant: cần audience/scope/tenant/object ACL ở cả Gateway và downstream.

### 11.2 Chọn issuer chưa đủ để giới hạn audience

Một token từ issuer alpha có thể được cấp cho một ứng dụng/Resource Server khác. Chỉ đúng `iss` không chứng minh token có `aud` dành cho Gateway.

Production cần kiểm:

```text
signature    valid?
iss          exactly one of trusted issuer strings?
aud          contains this gateway / required resource?
exp, nbf     within allowed time / skew?
scope        enough for requested operation?
subject      allowed to access tenant?
tenant claim consistent with route/host?
record       owned by authorized subject/tenant?
```

Với từng issuer, phải bổ sung `OAuth2TokenValidator<Jwt>` thích hợp cho audience/scope/tenant claims hoặc dùng một `ReactiveJwtDecoder` đã được cấu hình đầy đủ. Không khẳng định `fromTrustedIssuers(...)` tự suy ra audience mong muốn từ URL.

### 11.3 Tránh tenant mix-up qua token `iss`

Giả sử request:

```http
GET /tenants/beta/reports HTTP/1.1
Host: gateway.example.com
Authorization: Bearer <JWT_ISSUER_ALPHA>
```

Nếu resolver issuer chấp nhận issuer alpha hợp lệ, request có thể được **xác thực** dưới danh tính alpha. Nhưng resource `/tenants/beta/reports` là của beta. Gateway/downstream phải tiếp tục kiểm **tenant của route = tenant gắn với authenticated principal**, hoặc có chính sách cross-tenant delegation được chứng minh. Chỉ có `anyExchange().authenticated()` sẽ làm thiếu bước này.

Một policy an toàn:

```text
issuer alpha -> tenant alpha identity
issuer beta  -> tenant beta identity

GET /tenants/alpha/** with verified alpha identity -> xét scope/ACL
GET /tenants/beta/**  with verified alpha identity -> 403
GET /tenants/beta/**  with verified beta identity  -> xét scope/ACL
```

Thông tin mapping issuer → tenant phải nằm trong **server-side tenant registry**, không lấy trực tiếp từ header `X-Tenant` do client tự đặt. Với tổ chức có shared issuer phục vụ nhiều tenant, dùng một trusted tenant claim được xác minh và đối chiếu route, thay vì chỉ issuer string.

## 12. Cấu hình nhiều loại token: JWT và opaque

Một số doanh nghiệp có hai issuer/tenant:

- Tenant A phát JWT có signature và JWKS.
- Tenant B phát **opaque token** cần gọi introspection endpoint.

Về mặt API, `ReactiveAuthenticationManagerResolver<ServerWebExchange>` có thể chọn `JwtReactiveAuthenticationManager` hoặc manager dựa trên `ReactiveOpaqueTokenIntrospector` (khi được cấu hình theo đúng Spring Security version).

```text
request /tenant-A/... + Bearer token
 -> trusted tenant registry A
 -> JwtReactiveAuthenticationManager
 -> ReactiveJwtDecoder verify JWT

request /tenant-B/... + Bearer token
 -> trusted tenant registry B
 -> Opaque introspection manager
 -> HTTPS introspection service verifies token state
```

**Không mặc định đoán token là JWT chỉ dựa vào dấu chấm trong chuỗi**. Token opaque có thể nhìn giống JWT, hoặc format JWT-like được dùng cho mục đích khác. Quyết định theo **hợp đồng issuer/resource server và tuyến/tenant trusted**, không dựa vào cấu trúc sơ sài.

Nếu cùng URL buộc chấp nhận hai token types, cần một routing policy fail-closed và test các trường hợp ambiguous/unsupported; không introspect JWT sai rồi fallback sang một manager có authority mạnh hơn để được 200.

### 12.1 Mỗi tenant có introspection credentials riêng

Với opaque tokens, client ID/secret dùng ở introspection endpoint có thể khác nhau giữa các tenant. Đây là **credentials của Resource Server** khi gọi introspection, không phải password user ở HTTP request. Không dùng cùng secret cho mọi tenant chỉ để đơn giản hóa, không log token trong HTTP client tracing.

Introspection thường có network latency và availability dependency. Dùng nonblocking WebClient, TLS, bounded connections/timeout, rate limits và caching theo TTL/revocation policy; không `block()` ngay trên event loop.

## 13. Resolver động: thêm tenant runtime

Một gateway nhiều tenant không muốn restart mỗi lần onboard tenant mới. Có thể lưu registry:

```text
tenantId / issuer
   -> manager/decoder cấu hình đã được duyệt
   -> trạng thái ACTIVE/REVOKED
   -> allowed audiences + scopes
   -> key rotation/reload policy
```

### 13.1 Đừng làm discovery từ input của người dùng

**Phản ví dụ nguy hiểm:**

```java
// PHẢN VÍ DỤ: không dùng trong request handler.
String issuer = exchange.getRequest().getHeaders()
    .getFirst("X-Issuer");

// Dòng dưới có nguy cơ SSRF nếu issuer do client tùy ý gửi:
// ReactiveJwtDecoders.fromIssuerLocation(issuer)
```

Nếu attacker đưa `X-Issuer: http://169.254.169.254/...` hoặc URL nội bộ, server có thể gửi request discovery đến host không được phép. Thậm chí nếu URL thuộc Internet, attacker có thể phát JWT do mình tự ký và tự đăng JWKS tương ứng.

**Đúng hơn:** chỉ admin có quyền và quy trình onboarding phê duyệt issuer/tenant → lưu vào registry server-side; resolver lookup **chỉ từ danh sách đã được duyệt**. Không tự tin issuer vì tên miền nhìn giống công ty; đối chiếu đúng URI, TLS, ownership và scopes.

### 13.2 Thiết kế repository of managers

Theo hướng dẫn Spring Security multi-tenancy, có thể dựng `JwtIssuerReactiveAuthenticationManagerResolver` với repository đã kiểm soát:

```java
// Mảnh code — map được xây từ nguồn tin cậy trước đó.
Map<String, ReactiveAuthenticationManager> managers =
    new ConcurrentHashMap<>();

JwtIssuerReactiveAuthenticationManagerResolver resolver =
    new JwtIssuerReactiveAuthenticationManagerResolver(
        issuer -> Mono.justOrEmpty(managers.get(issuer)));
```

Đoạn này cần imports `Map`, `ConcurrentHashMap`, `Mono`, `ReactiveAuthenticationManager` và resolver. **Không** đặt logic “nếu map miss thì lấy JWK của issuer từ token” vào đây. Bổ sung tenant mới phải qua bước admin phê duyệt, dựng decoder/JWKS với issuer và audience validators, rồi mới đưa manager vào registry.

Một kế hoạch onboarding an toàn:

1. Nhận yêu cầu tenant qua kênh quản trị đã xác thực.
2. Xác minh quyền quản trị tenant và metadata issuer từ nguồn tin cậy.
3. Validate HTTPS, hostname, issuer ID, allowed audience, JWT algs, scopes, JWK URL, key rotation.
4. Khởi tạo/cấu hình manager theo phiên bản đã kiểm; kiểm health và introspection/JWKS.
5. Công bố immutable snapshot hoặc concurrent map update có phiên bản, kèm audit.
6. Khi tenant bị disable, dừng chọn manager/issuer mới, xử lý cache/TTL theo policy.
7. Test request cũ/in-flight và multi-node config convergence.
8. Nếu issuer outage, fail closed; không tự dùng manager một tenant khác.

### 13.3 Lazy initialization và blocking boundary

Spring Security có cách tạo JWT manager từ issuer bằng factory; tùy version một số helper discovery có thể dùng I/O đồng bộ. Nếu cần đưa blocking discovery vào reactive manager provisioning, tạo ở startup/admin async workflow hoặc bọc phù hợp:

```java
Mono<ReactiveJwtDecoder> decoder =
    Mono.fromCallable(() ->
        ReactiveJwtDecoders.fromIssuerLocation(trustedIssuer))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **mảnh minh họa** cần imports, chỉ sử dụng khi `trustedIssuer` đã có trong registry tin cậy; không gọi theo mỗi HTTP request. Tránh tạo manager/JWKS client mới cho mỗi request, gây thắt cổ chai, DoS và token verification không nhất quán. Có cache theo issuer, giới hạn kích thước, timeout, retry/backoff và metrics.

## 14. Gateway routing vs security resolution

Spring Cloud Gateway thường có route predicates/filter chains xác định backend đích. Đừng nhầm việc **Gateway route đến microservice** với việc **Spring Security chọn verifier**:

```text
Request
  |
  +--> Security: chọn chain + manager + xác thực token
  |                  |
  |             identity/scope/tenant
  |                  |
  +--> Authorization: có quyền gọi route/object?
  |                  |
  +--> Gateway route predicate: đi backend nào?
  |                  |
  +--> Token relay / outbound auth: token nào được gửi?
  |                  |
  v
Downstream API (PHẢI kiểm token/audience/tenant theo trust model)
```

Đường đi qua Gateway không tự biến token sai audience thành hợp lệ. Nếu Gateway nhận token `aud=gateway` và backend đòi `aud=orders-api`, cân nhắc token exchange/on-behalf-of hoặc xin token đúng đích. **Không** tắt audience validation ở backend chỉ vì Gateway đã nhận token.

### 14.1 Đừng dựa vào X-Tenant để cấp quyền

```http
GET /tenants/beta/orders HTTP/1.1
X-Tenant: beta
Authorization: Bearer <TOKEN_CUA_USER_ALPHA>
```

Một header do khách gửi có thể giúp chọn **candidate tenant** nhưng không chứng minh user alpha được phép xem beta. Đối chiếu tenant trong **verified JWT claims/authority và mapping server-side** với tenant route. Không đem header `X-Tenant` raw đến backend rồi coi nó như một authentication assertion.

### 14.2 Forwarded headers và host-based tenant

Trong reverse proxy, `X-Forwarded-Host`/`Forwarded` có thể ảnh hưởng URI/tenant routing. Chỉ tin các header này khi ingress đáng tin **xóa/ghi đè** mọi giá trị do client gửi, cấu hình trusted proxies và normalizes hostname. Nếu không, attacker có thể chọn manager/tenant bất ngờ bằng host spoofing.

Không cố sửa vấn đề này bằng cách cho resolver “thử tất cả managers”; đó là route confusion. Xây canonical mapping giữa external host, tenant, issuer đã được phê duyệt và resource paths.

### 14.3 Chặn đồng thời nhiều credential

Request có cả `Authorization: Bearer A` và `X-API-Key: B` cần policy rõ ràng. Có thể:

- Route Bearer **chỉ** chấp nhận Bearer, từ chối extra credential khi threat model yêu cầu.
- Route API key chỉ chấp nhận key, bỏ qua hoặc từ chối Bearer theo hợp đồng, nhưng **không** tự dùng Bearer sai làm fallback.
- Với migration, một converter có policy chọn đúng một scheme; cả hai credential xuất hiện → 400/401 theo contract.

Resolver **chọn manager**, không bắt buộc tự giải quyết việc convert nhiều credential types. Converter/matcher là lớp riêng và cần test.

## 15. Các lỗi 401, 403, redirect và thông điệp an toàn

| Tình huống | HTTP hợp lý | Nguyên nhân |
|---|---|---|
| Route protected, không có credential | 401 | Chưa authentication |
| Có credential nhưng sai/expired/chữ ký không hợp lệ | 401 | Authentication thất bại |
| Credential đúng cho tenant alpha nhưng dùng vào beta route | 401 hoặc 403 tùy flow; **phải từ chối** | Nếu manager beta từ chối credential → 401; nếu đã authenticated nhưng thiếu quyền beta → 403 |
| Unknown tenant | 4xx fail-closed | Resolver không được chọn fallback quyền rộng |
| Token hợp lệ nhưng thiếu scope/role | 403 | Authorization từ chối |
| Token hợp lệ nhưng sai audience resource | 401 invalid token hoặc status theo resource-server contract | Validation token từ chối |
| Browser chưa login vào trang | 302 tới login hoặc 401 theo UX/chain | Không có identity |
| Gateway không gọi được issuer/JWKS/introspection | Không chấp nhận token; trả lỗi an toàn tùy điểm hỏng | Không fallback sang issuer khác |
| Preflight OPTIONS | Theo CORS policy | Không phải “bỏ qua auth cho mọi route” |
| Resource không tồn tại | 404/4xx sau khi chính sách bảo mật xác định | Không để unknown tenant trở thành public |

Mỗi hệ thống có error contract riêng. **Đừng biến mọi 403 thành “token đã hết hạn”**; CSRF, thiếu quyền, sai tenant và authentication failures là các nguyên nhân khác nhau.

Trong JSON error body không phản chiếu raw authorization token, client secret, issuer metadata nhạy cảm, session ID hoặc stacktrace. Log route template, tenant ID đã validate (nếu được phép), credential mechanism, correlation ID, status và code lỗi ổn định — không log token hoặc password.

## 16. Chẩn đoán các sai lầm thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm |
|---|---|---|
| Tenant alpha login được trên route beta | Manager chung lookup username mà không gắn tenant; quyền chỉ `authenticated()` | Tách manager/user store, kiểm authority/tenant |
| Request với `X-Tenant` lạ làm server gọi URL lạ | Discovery issuer từ input client | Issuer allowlist, loại SSRF |
| JWKS server bị gọi liên tục | Manager/decoder tạo lại mỗi request | Cache theo issuer, preprovision, telemetry |
| Basic manager bị gọi hai lần | Built-in HTTP Basic + custom AuthenticationWebFilter | Tắt built-in Basic hoặc bỏ custom filter trùng |
| Spring Security chấp nhận Bearer sai issuer | Verifier không kiểm issuer/signature | Dùng trusted issuers + JWT validator |
| Token issuer alpha gọi record beta được | Chỉ `authenticated()`, thiếu tenant ACL | Compare verified tenant/issuer với route và record |
| Một request 401 dù JWT đúng chữ ký | Sai audience/scope/issuer, expired/clock skew, thiếu JWK | Kiểm chi tiết validator policy, không tắt |
| GET có token đúng nhưng 403 | Thiếu authority/role hoặc tenant mismatch | Test authorization riêng |
| Không có credential nhưng resolver không chạy | Converter trả Mono.empty | Bình thường; authorization phải trả 401 |
| POST không có CSRF token 403 | CSRF filter chặn trước manager/controller | Cấu hình token phù hợp, không tắt toàn cục |
| Gateway route đúng nhưng token relay sai | Token downstream aud không phù hợp | Token exchange, đúng resource token |
| Route mới được gọi không auth | Không chain nào match | Fallback chain denyAll |
| `@Order` gây route rơi vào chain khác | Matcher rộng trước hẹp | Sắp xếp hẹp trước, test path |
| Hai tenant có cùng username tạo nhầm identity | Account key chỉ username | Dùng cặp issuer+sub hoặc tenant+user ID |
| Một backend không chịu trạng thái session | Multi-node session store/TTL lỗi | Tách state, shared store hoặc stateless JWT đúng contract |
| Token JWK rotation làm request fail | Cache key/JWKS refresh không phù hợp | Quản lý cache và rotation |
| Resolver custom query JDBC trên event loop | Blocking I/O | Reactive driver hoặc bounded scheduler |
| Rò credential trong log tracing | Log raw request/headers | Redact, kiểm log pipeline |
| Tenant đã disable vẫn được request | Registry/cache chưa invalidate | Lifecycle cache, revocation propagation |

## 17. Test matrix cho hệ thống production

| Lớp | Ca kiểm thử | Kết quả cần có |
|---|---|---|
| Selector | Tenant alpha/beta được phê duyệt | Chọn đúng một manager |
| Selector | Unknown tenant/path gần giống | Không fallback sang default permissive |
| Credential | User alpha password ở beta | Authentication từ chối |
| Credential | Missing/invalid Basic/Bearer | 401, không gọi business |
| Filter | Không có Basic trong WebFlux demo | Converter empty, resolver không gọi |
| Filter | Built-in + custom filter trùng | Test đếm attempts phát hiện và sửa |
| Chain | Hẹp trước rộng, fallback | Route thuộc chain đúng |
| JWT issuer | Token issuer A/B hợp lệ | Chọn manager/JWKS tương ứng |
| JWT issuer | Issuer attacker, unsigned/wrong-key JWT | 401, **không** gọi discovery theo issuer attacker |
| JWT claims | Wrong aud, expired, not-before | 401 theo validator |
| JWT tenant | Token alpha gọi beta route | 403 hoặc 401 theo policy; không truy cập beta |
| JWT scope | Thiếu required scopes | 403 |
| Data ACL | Đúng tenant nhưng record người khác | 403/404 theo policy |
| Proxy | Spoofed X-Forwarded-Host | Không đổi tenant ngoài trusted mapping |
| CORS/CSRF | Preflight và unsafe methods | Policy đúng, không bypass |
| Network | JWKS/introspection outage | Fail closed, timeout/bounded retry |
| Dynamic tenant | Onboard/disable trong lúc có traffic | Snapshot/registry consistent, caches được cập nhật |
| Token relay | Bearer downstream đúng audience | Backend kiểm lại token và quyền |
| Concurrency | Nhiều requests cùng issuer mới | Manager lazy loading không tạo storm |
| Logging | Authentication errors | Không lộ Bearer/secret/password |

**Điều quan trọng:** test credential-type routing bằng Basic offline chỉ xác nhận **cơ chế chọn manager**. Để kiểm đầy đủ JWT đa issuer, cần signed test tokens, JWKS hoặc mock IdP thực sự và audit validator (signature, issuer, audience, scope, tenant), không chỉ tạo `Jwt` object bằng test builder.

## 18. Checklist triển khai

1. Lập bảng route/tenant → issuer/provider → credential type → required scopes/authority → backend.
2. Chọn rõ khi nào dùng nhiều `SecurityWebFilterChain`, khi nào dùng resolver trong một chain.
3. Dùng đúng interface WebFlux `ReactiveAuthenticationManagerResolver<ServerWebExchange>`.
4. Tách `ServerAuthenticationConverter` (trích xuất credential) khỏi resolver (chọn verifier) và manager (xác minh).
5. Chỉ chọn manager từ config/registry đáng tin; không tạo discovery từ URL do khách cung cấp.
6. Không để unknown tenant trở thành default trusted tenant hoặc có quyền ADMIN.
7. Nếu JWT nhiều issuer, ưu tiên `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)`.
8. Kiểm issuer **và** JWT signature, timestamps, audience và scope; tenant claim phải đồng nhất route.
9. Không xem `iss`/`Host`/`X-Tenant` raw là identity đã verified.
10. Với opaque introspection, tách đúng introspector/credentials từng tenant; không tái sử dụng session/token vô điều kiện.
11. Chặn credential mixing và cơ chế fallback từ token sai sang manager rộng quyền.
12. Đặt filter trong đúng Security chain, không đăng ký đồng thời global `WebFilter`.
13. Cấu hình `NoOpServerSecurityContextRepository` nếu API được thiết kế stateless; kiểm các filter/session khác.
14. Có fallback chain, thứ tự `@Order`, authorization rules hẹp trước rộng, và negative tests.
15. Giữ CSRF/CORS cho đúng threat model; đừng sửa 403 bằng disable tất cả.
16. Đảm bảo Proxy forwarded headers chỉ tin nguồn đáng tin; tránh tenant host spoofing.
17. Bảo vệ secrets, HTTPS, password policies, JWK/secret rotation, cache và revocation.
18. Đo latency/failed issuer/resolver selection mà không ghi raw token hay password.
19. Test nhiều tenant có cùng username; test signed JWT sai issuer/audience/tenant và object-level ACL.
20. Khi gateway relay access token, kiểm đúng downstream audience/permissions hoặc dùng token exchange khi cần.
21. Kiểm lại API trên đúng version Spring Security trước mỗi lần upgrade.

## 19. Bài tập thực hành

1. Vẽ flow `AuthenticationWebFilter → converter → resolver → manager → SecurityContext → authorization`. Chỗ nào lấy token raw, chỗ nào mới xác nhận identity?
2. Đổi username `alex` ở hai tenant nhưng giữ password khác. Viết WebTestClient chứng minh không cross-auth.
3. Thêm tenant `gamma` có password và authority riêng vào resolver. Cần thay đổi gì trong authorization rules?
4. Thêm route `/tenants/alpha/admin`. Nếu chỉ giữ `authenticated()`, lỗ hổng nào có thể xảy ra?
5. Xóa fallback chain; thử URL không match. Vì sao không được giả định mặc định là 403?
6. Thêm duplicate `AuthenticationWebFilter` global và trong chain ở môi trường test. Đo số resolver/manager attempts, rồi sửa.
7. Dùng `ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver.builder()` để thay custom regex resolver; so sánh độ rõ ràng và matcher ordering.
8. Thay Basic demo bằng JWT multi-issuer và signed test tokens. Test issuer trusted/untrusted.
9. Gửi JWT hợp lệ issuer alpha vào route beta: chỉ `authenticated()` có đủ không? Thêm tenant authorization.
10. Thêm validator audience bắt buộc `gateway-api` và test token từ cùng issuer nhưng `aud=other-api` bị từ chối.
11. Đặt API sau reverse proxy, giả mạo `X-Forwarded-Host`; xác định trust boundary.
12. Thiết kế onboarding tenant runtime: admin API, issuer allowlist, metadata validation, manager cache, disable/revoke, multi-node sync.
13. Cho tenant B dùng opaque introspection trong khi A dùng JWT; mô tả manager và cách tránh fallback khi introspection thất bại.
14. Dùng performance test để đo độ trễ request đầu tiên khi JWT resolver lazy load JWK metadata và các request tiếp theo.
15. Đặt timeout cho registry và decoder; đảm bảo không `block()` trên Netty event loop.
16. Viết security regression test cho CORS preflight và CSRF unsafe methods sau khi thêm một route mới.
17. Kiểm việc Spring Cloud Gateway route đến downstream không tự bypass audience validation.
18. Kiểm log/trace có che Authorization, cookie, client secret và JWT claims nhạy cảm chưa.

## Kết luận

`ReactiveAuthenticationManagerResolver<ServerWebExchange>` là **bộ chọn bộ xác thực**, không phải bộ tự xác thực. Trong Spring Security WebFlux, một `AuthenticationWebFilter` có thể lấy credential bằng converter, gọi resolver theo request để chọn **ReactiveAuthenticationManager**, rồi manager mới kiểm password/JWT/opaque token. Với Gateway đa tenant, key selector như URL/host/header/`iss` chưa xác minh chỉ được dùng để **chọn trong tập managers/issuers đã tin cậy**; quyền tenant phải được kiểm lại sau authentication bằng claims/authorities đã verify và policy nghiệp vụ. Khi nhận JWT từ nhiều issuer, ưu tiên `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)`; khi các tenant dùng cơ chế khác nhau, xem xét resolver/chain theo matcher và giữ fail-closed. Một thiết kế an toàn có filter order rõ, không double-auth, không block event loop, không arbitrary issuer discovery, có fallback deny-all và test cross-tenant ở cả authentication, authorization và downstream.

## Tài liệu chính thức

1. Spring Security 6.5 — Reactive OAuth2 Resource Server Multi-tenancy: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html
2. Spring Security — ReactiveAuthenticationManagerResolver Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html
3. Spring Security — AuthenticationWebFilter Javadoc (resolver constructor, converter, matcher, failure): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
4. Spring Security 6.5 — JwtIssuerReactiveAuthenticationManagerResolver Javadoc: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html
5. Spring Security 6.5 — ServerHttpSecurity.OAuth2ResourceServerSpec.authenticationManagerResolver: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2ResourceServerSpec.html
6. Spring Security 6.5 — ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/ServerWebExchangeDelegatingReactiveAuthenticationManagerResolver.html
7. Spring Security 6.3 — WebFlux Security multiple filter chains: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
8. Spring Security — Reactive JWT Resource Server: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
9. Spring Security — UserDetailsRepositoryReactiveAuthenticationManager Javadoc: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
10. Spring Framework — Reactive WebFlux filter processing: https://docs.spring.io/spring-framework/reference/web/webflux.html
