# Rà soát khác biệt Servlet, reactive và các thư viện tích hợp bên ngoài

## 1. Vì sao “đúng phiên bản” chưa đủ để ứng dụng xác thực an toàn?

Trong hệ sinh thái Java, Spring Security cung cấp cả **Servlet security** và **Reactive WebFlux security**, nhưng chúng **không phải hai lớp API có thể thay thế lẫn nhau**. Một ứng dụng có thể compile thành công, chạy được endpoint và vẫn sai vì security chain không được kích hoạt, lấy principal từ nhầm context, hoặc thư viện IdP/JWT/LDAP tích hợp bên ngoài không tương thích với phiên bản framework.

Ví dụ:

- Một đoạn hướng dẫn có `HttpSecurity` và `SecurityFilterChain` được copy vào dự án WebFlux đang dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Các bean có thể không phục vụ đúng request path.
- Một ứng dụng Spring MVC thêm `spring-boot-starter-webflux` chỉ để dùng `WebClient`, rồi tưởng phải đổi toàn bộ authorization sang reactive security.
- OAuth2 login client đã được bật, nhưng API bearer JWT lại thiếu resource-server configuration; kiểm tra token không xảy ra ở nơi cần.
- Nhóm phát triển nâng Spring Boot 3.x lên Boot 4.x nhưng giữ bản `spring-security-test` hoặc thư viện SSO cũ, dẫn đến lỗi classpath/auto-configuration và test không còn dựng đúng security context.
- Một thư viện JWT khác tự parse token, tạo `Authentication` đã authenticated mà bỏ qua kiểm tra `aud`, `iss`, thuật toán và key rotation.
- Spring Security 7.x đã loại bỏ một số API deprecated, còn plugin tích hợp bên ngoài vẫn compile cho thế hệ Security 5/6.
- Ứng dụng dùng `javax.servlet.*` từ mã tích hợp cũ trong khi Spring Framework 6+ đã theo Jakarta namespace; Boot 4 tiếp tục nâng baseline Jakarta EE.

**Mục đích của bài:** biết cách **rà soát bộ phiên bản, runtime stack, security filters, contract thư viện bên thứ ba và bằng chứng kiểm thử** trước khi nâng cấp hoặc thêm tính năng xác thực.

Ba nguyên tắc:

1. **Chọn stack theo runtime:** Servlet MVC và WebFlux có các entry point/security context/lifecycle khác nhau.
2. **Chọn bộ dependency tương thích:** Boot BOM, Spring Security modules, Spring Framework, servlet/reactive server và external libraries phải được quản lý như một tập.
3. **Kiểm thử ranh giới thật:** unit test chỉ mock principal không chứng minh browser login, JWT decoder, IdP callback hay reverse proxy vận hành đúng.

## 2. Bản đồ khái niệm: các lớp phải được kiểm tra

~~~text
[HTTP client / browser]
        |
        v
[Reverse proxy / Gateway / TLS termination]
        |
        v
[Spring Boot Runtime]
        |
        +--------------------------+
        |                          |
        v                          v
  Servlet / Spring MVC         Reactive / WebFlux
  - Servlet Filter             - WebFilter
  - HttpServletRequest         - ServerWebExchange
  - SecurityFilterChain        - SecurityWebFilterChain
  - HttpSecurity               - ServerHttpSecurity
  - AuthenticationManager      - ReactiveAuthenticationManager
  - SecurityContextHolder      - ReactiveSecurityContextHolder
  - HttpSession / Spring       - WebSession / reactive
    Session                      session support
        |                          |
        +-------------+------------+
                      |
                      v
           [External integrations]
           OAuth2 Client / Resource Server
           OIDC / SAML2 / LDAP / WebAuthn
           JWT libraries / IdP SDKs
           Spring Session / Gateway / Cloud
                      |
                      v
            [Authorization + Audit]
~~~

Đây là **sơ đồ vai trò**, không phải ứng dụng bắt buộc chạy cả hai nhánh. Phần lớn service nên chọn **một runtime server stack chính**, chỉ bổ sung thư viện client từ stack khác khi có lý do thực tế.

Khái niệm “Servlet”/“Reactive” trong bài chỉ về **server-side security execution model**. Java `CompletableFuture`, WebClient hoặc một method trả `Mono` trong service chưa tự biến security chain thành WebFlux.

## 3. Snapshot các thế hệ phiên bản cần phân biệt

Tại thời điểm tài liệu được đối chiếu (tháng 11/2026), có hai dòng phổ biến để chuẩn bị/migration:

| Lớp | Spring Boot 3.x / Spring Security 6.x | Spring Boot 4.x / Spring Security 7.x |
|---|---|---|
| Java baseline | Java 17+. | Java 17+ vẫn là baseline; dùng LTS mới hơn nếu toàn bộ hệ thống hỗ trợ. |
| Spring Framework | 6.x (Boot 3). | 7.x (Boot 4). |
| Jakarta | Jakarta EE 9+/10 tùy phiên bản Boot/Framework. | Jakarta EE 11 baseline; Servlet 6.1 cho Servlet server. |
| Embedded Servlet | Đối chiếu runtime cụ thể với Boot 3.x dependency management. | Tomcat 11.x hoặc Jetty 12.1.x theo Boot 4 release/documentation; không tự mang container cũ. |
| Security configuration | `SecurityFilterChain`, lambda DSL; chuẩn bị deprecations trước khi lên 7. | Các API deprecated bị loại theo migration; tiếp tục dùng type đúng Servlet/Reactive. |
| Spring Security OAuth Authorization Server | Module/project được quản lý theo thế hệ dependency. | Được tích hợp vào Spring Security 7, cần rà lại artifact/starter và API. |
| Jackson | Thường Jackson 2 theo Boot 3.x defaults. | Jackson 3 là hướng mặc định; API/config serialization cần rà soát. |
| Test support | `spring-security-test` cùng phiên bản Security/BOM, Boot starter test. | Boot 4 modular test starters, ví dụ `spring-boot-starter-security-test` cho security test integration. |

**Không chọn version chỉ vì “7 lớn hơn 6”.** Cần đọc **support policy, dependency constraints và breaking changes** của tổ hợp Boot + Security + Framework thực tế. Spring Security 6.5 là nhánh được hướng dẫn dùng để **chuẩn bị** chuyển lên 7.0, không phải tất cả 6.x có thể nhảy thẳng qua mà không sửa.

Theo tài liệu được tham chiếu, Spring Security stable docs cung cấp nhánh 7.1.x và 6.5.x; các patch numbers thay đổi theo thời gian. Nên **pin patch trong BOM/build** và ghi lại ngày khảo sát thay vì hard-code “mới nhất” vào module.

### Java 17+ và Jakarta package

Nếu source cũ có:

~~~java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
~~~

trên Spring Framework 6+/Boot 3+ thường phải chuyển sang:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
~~~

Đây là **namespace change** cho Servlet APIs, không đơn giản replace mọi `javax.*` trong toàn project: `javax.crypto`, `javax.net` là Java SE và vẫn mang tên đó. Plugin binary build cho `javax.servlet.Filter` không thể được coi là tương thích `jakarta.servlet.Filter` chỉ nhờ JVM cùng chạy Java 17.

Với Boot 4, kiểm Servlet 6.1 compatibility, JPA/Validation, app server, Spring Cloud release train, testing libraries và plugins liên quan; không chỉ sửa import Servlet.

## 4. Vì sao không tự trộn versions trong Maven/Gradle?

Spring Boot cung cấp **dependency management (BOM)**. Mỗi thế hệ Boot quản lý một tập tương thích cho Spring Framework, Spring Security, Jackson, Reactor, Tomcat/Jetty, Spring Session và nhiều dependencies khác.

Ví dụ Maven Boot 3.x:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version><!-- Boot 3.x patch đã phê duyệt --></version>
</parent>
~~~

Trong bài hướng dẫn, đây là **template cấu hình** với comment thay cho version, không phải POM để chạy ngay. Ở dự án thật, chỉ định patch release có thật, và thường **không ghi version** cho dependencies đã do Boot quản lý:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Một lỗi phổ biến là:

~~~xml
<!-- Cấu hình nguy cơ lệch hệ sinh thái -->
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-web</artifactId>
    <version>7.1.2</version>
</dependency>
~~~

trong ứng dụng Boot 3.x đang quản lý Security 6.x. Không nên trộn `spring-security-web` 7.x với `spring-security-config` 6.x chỉ để nhận một tính năng mới; có thể gây `NoSuchMethodError`, `NoClassDefFoundError`, bean mismatches hoặc thay đổi behavior không lường trước.

Với Gradle, dùng Spring Boot plugin/dependency management hoặc Gradle platform BOM phù hợp; **không khai báo mỗi artifact security ở một version khác nhau**. Khi buộc override vì CVE, cần xác nhận override thuộc dòng tương thích và kiểm thử đầy đủ; không phải cứ số patch cao là thay thế an toàn.

## 5. Maven/Gradle dependency graph là một phần của security review

Trước khi so sánh code Servlet và Reactive, xuất **effective dependency graph**:

~~~bash
# Maven (Linux/macOS/Git Bash):
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework
mvn help:effective-pom

# Gradle:
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core \
  --configuration runtimeClasspath
~~~

Trên Windows PowerShell/cmd, dùng `gradlew.bat` thay vì `./gradlew` nếu wrapper tương ứng. Các lệnh là thao tác đọc dependency và cần Maven/Gradle project thực. Không dùng `dependency:tree` để suy support policy nếu nó chỉ trả danh sách artifact; cần đối chiếu release notes.

Các dấu hiệu cần tìm:

- Có **hai major versions** của Spring Security trên dependency tree không?
- Có Jackson 2 và Jackson 3 được dùng đúng theo integration contract, hay thư viện third-party bắt class cũ?
- Có classpath chứa `javax.servlet` trong plugin chạy với `jakarta.servlet` không?
- Có `spring-boot-starter-web`/`webmvc` và `webflux` cùng lúc không? Vì sao?
- Có thư viện tự kéo `spring-security-oauth2-resource-server` phiên bản khác BOM không?
- Có hai JWT decoders khác nhau cùng chạy hoặc một library bypass Spring validator không?
- `spring-security-test` có khớp security runtime không? Boot 4 có companion test starter đúng không?
- Một SAML/LDAP/WebAuthn adapter có yêu cầu JDK, Jakarta, Reactor hoặc Servlet version riêng không?

**SBOM, CVE scanning, license check và support matrix** nên thực hiện ở cả compile/runtime/test scopes. Một thư viện chỉ ở test scope có thể vẫn ảnh hưởng kết quả kiểm thử; một thư viện transitively đi vào runtime có thể kéo bản mật mã/JWT cũ.

## 6. Servlet security và Reactive security khác nhau ở đâu?

| Năng lực | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| HTTP abstraction | `HttpServletRequest`, `HttpServletResponse`, `Filter`. | `ServerWebExchange`, `ServerHttpRequest`, `WebFilter`. |
| Security pipeline | `FilterChainProxy` và `SecurityFilterChain`. | `WebFilterChainProxy` và `SecurityWebFilterChain`. |
| Cấu hình | `HttpSecurity`. | `ServerHttpSecurity`. |
| Authentication entry | `AuthenticationManager` / `ProviderManager`. | `ReactiveAuthenticationManager`, reactive manager resolution. |
| User lookup | `UserDetailsService`, potentially blocking DB/LDAP access. | `ReactiveUserDetailsService` hoặc reactive integration; tránh block event loop. |
| Request principal | `SecurityContextHolder` trong mô hình Servlet request/thread. | `ReactiveSecurityContextHolder`/Reactor Context theo reactive subscription. |
| Authorization | `authorizeHttpRequests`, Servlet `AuthorizationManager` và method security. | `authorizeExchange`, reactive authorization managers, reactive method security. |
| Session | Servlet `HttpSession`; Spring Session Servlet. | WebFlux `WebSession`; reactive session implementation. |
| CSRF | `CsrfFilter` và Servlet token repositories. | Reactive CSRF WebFilter/repositories. |
| CORS | Servlet CORS filter/config. | Reactive CORS/WebFilter config. |
| Test | `MockMvc` và Servlet security post-processors. | `WebTestClient` và reactive `SecurityMockServerConfigurers`. |
| Server default | Servlet container (ví dụ Tomcat). | Thường Reactor Netty hoặc reactive server được hỗ trợ. |

Không nên viết một helper kiểu "lấy SecurityContextHolder ở mọi service" nếu service chạy dưới reactive pipelines; ThreadLocal không theo Reactor scheduling một cách đáng tin. Ngược lại, không dùng `ReactiveSecurityContextHolder` làm nguồn sự thật cho một Servlet controller sync thông thường nếu chưa có bridge đã thiết kế.

### Khác biệt không chỉ là return type

Trả `Mono<ResponseEntity<?>>` từ một method không chứng minh đã chuyển security stack. Cần xem **server runtime, HandlerMapping, filter chain, request abstraction và context propagation**. Spring WebFlux có thể cùng tồn tại dưới dạng client dependency trong một Servlet app; default web application type của Boot khi cả MVC và WebFlux classpath cùng có thường là Servlet trừ khi cấu hình đặc biệt.

## 7. Servlet `SecurityFilterChain`: ví dụ tích hợp

Đoạn này dùng Spring MVC/Spring Security Servlet, cần Boot-compatible dependencies và `JwtDecoder`/issuer URI nếu bật JWT resource server.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

**Đây là integration snippet**, không phải JDK 17 standalone. Cần resource server JOSE support, decoder và security policy cho CSRF, sessions, errors, scopes, method security, reverse-proxy trust. Một JWT hợp lệ nhưng sai `aud` không được mặc nhiên nhận nếu API có audience policy; cần `JwtDecoder` validator tương ứng.

Quan trọng:

- `securityMatcher("/api/**")` chọn **phạm vi chain**.
- `requestMatchers("/api/health")` quyết định **authorization bên trong chain**.
- Nếu không có fallback chain và endpoint ngoài `/api/**` không match chain nào, endpoint đó có thể **không được Spring Security bảo vệ**. Đừng nhầm `anyRequest().authenticated()` là "mọi request trên toàn server".
- Nếu có nhiều chains, thứ tự `@Order` và matchers cần kiểm thử với mọi route, đặc biệt actuator, login, oauth2 callback và endpoints mới.
- Custom `OncePerRequestFilter` thuộc Servlet stack; filter order phải được xác định, không copy vào WebFlux.

### Authentication trong Servlet

`AuthenticationManager` nhận `Authentication` request, có thể dispatch qua `DaoAuthenticationProvider`, `JwtAuthenticationProvider`, LDAP provider hoặc custom API-key provider. Nếu không provider nào hỗ trợ request class, `ProviderNotFoundException` có thể xuất hiện. Đây là logic thuộc Servlet-style manager/provider arrangement; không mặc định sao chép nó sang reactive manager contract.

## 8. WebFlux `SecurityWebFilterChain`: ví dụ tích hợp riêng

Trong một ứng dụng WebFlux riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new org.springframework.security.web.server.util.matcher
                    .PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/health").permitAll()
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Đây là **reactive integration snippet**; không copy đặt bên cạnh Servlet config trong cùng project rồi coi hai chains cùng bảo vệ một request. Cần `ReactiveJwtDecoder`/issuer config, WebFlux runtime và phương án fallback chain bảo vệ URL ngoài `/api/**`. Với Spring Security 7.x, đối chiếu API đúng bản mà BOM quản lý.

Khác biệt chính với Servlet:

- `ServerHttpSecurity` thay `HttpSecurity`.
- `SecurityWebFilterChain` thay `SecurityFilterChain`.
- `authorizeExchange` thay `authorizeHttpRequests`.
- `pathMatchers` và `ServerWebExchangeMatcher` theo server exchange, không phải Servlet RequestMatcher.
- `ReactiveAuthenticationManager` trả `Mono<Authentication>` và phải giữ reactive context.
- Reactive CSRF/session/logout và token handlers có server abstraction khác.

**Không chặn event loop:** nếu custom reactive authentication provider gọi JDBC/LDAP blocking hoặc `Thread.sleep` trên Netty event-loop, throughput/login latency có thể sụt nghiêm trọng. Dùng reactive-capable integration, hoặc đưa blocking calls lên bounded scheduler theo thiết kế có giới hạn, theo dõi saturation và timeout. Không mặc định annotation `@Async` là giải pháp thay đổi context an toàn.

## 9. Reactive SecurityContext và ThreadLocal: bẫy nhiều dự án mắc

Servlet code thường lấy user:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Trong một reactive flow, request có thể đi qua nhiều threads; dùng ThreadLocal theo lối Servlet có thể trả `null` hoặc authentication sai context. Reactive path nên dựa vào Reactor Context:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> authenticatedName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .filter(auth -> auth != null && auth.isAuthenticated())
        .map(Authentication::getName);
}
~~~

Đây là **integration method** trong reactive project, không phải chương trình `javac` độc lập. Nếu security context không tồn tại, `Mono` có thể hoàn tất rỗng; endpoint phải có policy rõ thay vì mặc định nhận "anonymous" như authenticated.

### Context propagation

Cẩn thận khi dùng:

- `publishOn`/`subscribeOn`, Reactor operators, asynchronous callbacks.
- `CompletableFuture` hoặc thư viện không gắn Reactor Context.
- Custom scheduler, message listeners, background jobs.
- RSocket, GraphQL, gRPC adapters có context truyền riêng.
- Một blocking client được gọi trong WebFlux security chain.

**Đừng copy `SecurityContextHolder` vào một static field** hay `InheritableThreadLocal` để “giữ user”; đó là nguy cơ rò identity giữa requests/threads. Với background jobs, truyền **trusted business identity/correlation** theo contract cụ thể và tái kiểm authorization ở resource operation.

## 10. Cùng một chức năng, module tích hợp khác nhau

| Chức năng | Servlet approach | Reactive approach | External integration cần rà |
|---|---|---|---|
| Username/password | Form login/Basic + UserDetailsService/AuthenticationProvider. | Reactive authentication + ReactiveUserDetailsService. | Password encoder, LDAP, datastore blocking/reactive. |
| OAuth2 Login/OIDC RP | Servlet OAuth2 client filters, session/authorization request repository. | Reactive OAuth2 client/OIDC support trong WebFilter pipeline. | IdP discovery, issuer, callback/redirect, state/nonce, client registration. |
| Resource Server JWT | Bearer filter + JwtDecoder/JwtAuthenticationConverter. | Reactive bearer WebFilter + ReactiveJwtDecoder. | JOSE/JWK library, key rotation, issuer/audience validators. |
| Opaque token | Introspection client/opaque token provider. | Reactive introspection/client. | AS outage, introspection credentials, cache, TTL/revocation. |
| SAML2 Login | Module `spring-security-saml2-service-provider` theo Servlet support. | Kiểm hỗ trợ chính thức theo stack/version; không suy cùng feature set. | OpenSAML dependency, metadata, certificates, clock skew, logout. |
| LDAP | Spring Security LDAP provider. | Cần kiểm connector support; nhiều LDAP drivers/bind hoạt động blocking. | LDAP SDK, TLS/LDAPS, pooling/timeouts. |
| WebAuthn/passkey | Spring Security WebAuthn support phù hợp bản; custom ceremony/challenge policy. | Kiểm tính năng native reactive trước khi thiết kế. | FIDO2/WebAuthn library, origin/RP ID, attestation/credential store. |
| Session | HttpSession/Spring Session Servlet. | WebSession/Spring Session reactive. | Redis/JDBC, serializer, cookie flags, cross-node revoke. |
| Gateway | Servlet gateway/proxy, headers/forwarded trust. | Spring Cloud Gateway Reactive khi dùng WebFlux. | Gateway starter/release train, forwarded identity, token relay, route filters. |
| Test | MockMvc, spring-security-test Servlet helpers. | WebTestClient + reactive security test configurers. | Test starters, embedded IdP, MockWebServer/WireMock variants. |

Không suy từ việc một tính năng có trên **Servlet reference guide** rằng nó có **API reactive tương đương**. Spring Security có tài liệu tách "Servlet Applications" và "Reactive Applications"; hãy kiểm tra tính năng, provider class, test support và lifecycle ở đúng nhánh.

## 11. OAuth2 Login và Resource Server không phải cùng một integration

Đây là khác biệt vừa theo **mục đích**, vừa theo **dependencies**:

- **OAuth2 Client / OIDC RP (`oauth2Login`):** ứng dụng đưa browser tới IdP, nhận callback, thực hiện authorization-code flow, tạo principal/session. Cần xử lý `state`, `nonce`, PKCE theo client policy, client registration và public redirect URI.
- **OAuth2 Resource Server (`oauth2ResourceServer`):** API nhận Bearer token, xác minh chữ ký JWT hoặc introspection opaque token, issuer, audience, expiry, scopes và mapping authorities.
- **OAuth2 Authorization Server:** phát hành token, quản trị clients/grants/consent, ký/rotate keys; đây là một vai trò khác, không tự có chỉ bằng cấu hình Resource Server.

Một ứng dụng có thể đóng nhiều vai trò, nhưng cần **cấu hình từng đường riêng**. Đặt dependency OAuth2 client không tự thêm JWT Resource Server filter; bật JWT không tự cho ứng dụng xử lý OIDC callback.

### Đổi phiên bản Spring Authorization Server

Tài liệu Spring Security 7 ghi nhận Spring Authorization Server **được đưa vào Spring Security**. Khi nâng từ dự án cũ dùng Authorization Server artifact/starter riêng sang Security 7 / Boot 4, phải đối chiếu **tọa độ dependency mới, packages, configuration DSL, persisted authorization data và Jackson serialization**. Không chỉ đổi version của `spring-security-oauth2-authorization-server` trong POM rồi mặc định mọi DB token row còn deserialize được.

**Không dùng thư viện OAuth2 legacy `spring-security-oauth`/`@EnableAuthorizationServer` từ các ví dụ nhiều năm trước làm hướng cấu hình production mới** mà không xác minh tình trạng bảo trì/tương thích. Những module thế hệ cũ có thể không hỗ trợ Spring Security 6/7 hoặc Jakarta EE.

## 12. JWT/JOSE: không để thư viện phụ bypass Spring validators

Spring Security Resource Server thường dùng `spring-security-oauth2-resource-server` cùng `spring-security-oauth2-jose` cho JWT. `Nimbus JOSE + JWT` và các thư viện liên quan có thể xuất hiện transitively; dependency tree phải xác nhận phiên bản do BOM và các tích hợp của bạn cần.

### Những thứ token validator phải kiểm

1. Chữ ký theo thuật toán allowlist; không chấp nhận `alg=none` khi không được policy cho phép.
2. Key/JWKS xuất phát từ trusted issuer/key provider; rotation và cache policy rõ ràng.
3. `iss` chính xác nhà phát hành tin cậy; không tin issuer bất kỳ chỉ vì nó có JWKS công khai.
4. `aud` chứa tài nguyên API tương ứng; không sử dụng ID Token OIDC làm API access token.
5. `exp`, `nbf` và clock-skew hợp lý, không cho token hết hạn.
6. Client/scopes/authorities mapping từ trusted claims; không cấp `ROLE_ADMIN` từ một claim client tự khai.
7. Token purpose và multi-tenant identity binding `(iss,sub)` hoặc identity link đã xác minh.
8. Kế hoạch revoke/epoch/introspection nếu yêu cầu chặn trước `exp`.

### Rủi ro khi dùng JWT SDK ngoài

Nếu một SDK bên ngoài tự decode Base64 JWT payload rồi code gọi:

~~~java
// KHÔNG ĐƯỢC coi việc parse claims là xác minh token:
// String payload = new String(Base64.getUrlDecoder().decode(parts[1]));
// Authentication auth = makeAuthenticatedFrom(payload);
~~~

thì attacker có thể thay claims nếu signature không được xác minh. Dùng `JwtDecoder`/`ReactiveJwtDecoder` phù hợp hoặc thư viện được đánh giá bảo mật và tích hợp **trước** khi tạo authenticated SecurityContext.

Đừng tạo `JwtAuthenticationToken` trực tiếp từ JSON client rồi nghĩ có authentication thật. `jwt()` trong `spring-security-test` là **mock helper**, không kiểm signature/issuer/audience. Cần integration tests với signed test tokens và negative cases.

## 13. SAML2, LDAP, Kerberos, CAS và WebAuthn: kiểm ma trận tính năng

**SAML2 Service Provider:** Spring Security hỗ trợ SAML2 login với integration phù hợp. Xác minh thư viện OpenSAML, security dependencies, Java/Jakarta versions, XML signature verification, metadata/certificate rotation, clock skew và logout. SAML2 feature availability/hook là một trong những nội dung phải kiểm tra **đúng Servlet hay reactive**. Không sao chép SAML `Saml2WebSsoAuthenticationFilter` vào WebFlux.

**LDAP/Active Directory:** các client LDAP có thể dùng blocking I/O và quy tắc trust TLS riêng. Trong Servlet, `LdapAuthenticationProvider` và `UserDetailsService` là pattern phổ biến. Trong WebFlux, không nhét LDAP bind blocking vào Netty event loop; đánh giá adapter, timeout và scheduler nếu cần. Tài khoản đã bị khóa/disabled ở directory cần được xử lý thành authentication failure, không fail open khi LDAP unavailable.

**CAS/Kerberos:** một số tiện ích có module/security extension riêng. Spring Security 7 documentation nêu Kerberos extension đã được tích hợp vào Spring Security; không vì vậy mặc định các thư viện adapter CAS/Kerberos cũ tương thích Jackson 3/Jakarta EE 11. Kiểm tra module cụ thể, maintainers và release train.

**WebAuthn/FIDO2/passkeys:** WebAuthn yêu cầu origin/RP ID, challenge binding, credential public key store, counter/replay policy, session/user binding và browser support. Một provider library cũ có thể giới hạn API Servlet dù core crypto chạy JDK17. Xác minh native support ở đúng Spring Security version/stack và các thư viện FIDO2 tích hợp.

**MFA libraries:** TOTP, push, SMS/Email OTP, backup codes có thể là giải pháp riêng. Đừng biến sự kiện password success thành "đã hoàn tất MFA" chỉ vì provider ngoài trả `authenticated=true`; cần assurance evidence và step-up policy nhất quán.

## 14. Spring Session, Redis/JDBC và serializer versioning

Session là phần dễ vỡ khi nâng Boot/Security/Framework hoặc khi đổi từ Servlet sang reactive:

| Mặt cần kiểm | Servlet | Reactive |
|---|---|---|
| Session abstraction | `HttpSession` / Spring Session Servlet. | `WebSession` / Spring Session reactive. |
| SecurityContext persistence | `SecurityContextRepository` và session storage. | `ServerSecurityContextRepository`/Reactor exchange. |
| Repository | Spring Session Redis/JDBC tùy loại. | Reactive-compatible repository/store được hỗ trợ. |
| Cookie name/flags | Servlet container hoặc Spring Session `CookieSerializer`. | Reactive WebSession/session cookie configurator. |
| Logout/revoke | Invalidate server-side session, remember-me, grants liên quan. | Invalidate WebSession, security context và token grants. |
| Serializer | Có thể chứa security principal/context serialized. | Có thể có serializer/context contract khác. |

Không chuyển trực tiếp Java-serialized SecurityContext của hệ cũ vào hệ mới mà không thử migration, nhất là khi **Spring Security 7 / Boot 4 chuyển sang Jackson 3** cho những phần serialization JSON liên quan. Nếu session dùng JDK serialization, class/version compatibility còn có vấn đề riêng. Tách migration session store, đặt TTL và có fallback logout/re-auth dự kiến.

Một thay đổi auth-principal class/package có thể làm các session persisted của bản trước không deserialize được. Hãy kiểm tra canary deployment với sessions được tạo ở bản cũ rồi đọc ở bản mới, đặc biệt blue/green rolling deployments khi **hai phiên bản cùng sử dụng một Redis keyspace**.

**Không phải mọi cookie name do `server.servlet.session.cookie.*` điều khiển** nếu Spring Session custom serializer sở hữu cookie; kiểm tra `Set-Cookie` thật. Dù cookie còn hợp lệ, resource server JWT có thể độc lập session nên phải quản lý grant revocation riêng.

## 15. Spring Cloud Gateway, service mesh và thư viện proxy identity

Nhiều dự án Spring Cloud Gateway chạy **Reactive WebFlux**, nhưng Spring Cloud Gateway cũng có lựa chọn **Server MVC**; không suy từ tên "Gateway" rằng toàn bộ pipeline đều reactive. Phải kiểm tra starter, runtime, WebFilter/Servlet Filter stack và release train tương thích với Boot.

Một số ranh giới:

- Gateway nhận TLS, có thể đóng vai trò **OAuth2 client** và dùng token relay downstream.
- Resource server trong backend phải **tự kiểm tra token hoặc trust contract rõ ràng**; không tin `X-Forwarded-User` từ Internet.
- `X-Forwarded-For`/`Forwarded`/`Host` có thể bị client giả; trusted edge phải strip và ghi lại.
- Gateway có thể làm rate limiting và route filtering, nhưng service-side authorization phải bảo vệ bypass path.
- Token relay chỉ chuyển token, **không tạo quyền ở downstream** nếu claims/audience không đúng.
- Một security SDK ở gateway có thể dùng Servlet classes nếu bạn chọn sai artifact, dẫn đến missing class hoặc filter không chạy.

### Spring Cloud compatibility

Đừng chỉ nâng Spring Boot trong khi giữ nguyên Spring Cloud BOM bất kỳ. **Mỗi Spring Cloud release train hỗ trợ những Boot versions cụ thể**. Kiểm tra Spring Cloud compatibility matrix và các starters như Gateway, Config, Circuit Breaker, Security integration theo version thực. Nếu dùng reactor-netty/gateway reactive, còn phải kiểm Netty/Reactor baseline.

Việc dependency tree compile được không chứng minh starter auto-configuration không bị back off hoặc filter order không thay đổi. Integration test qua proxy/route là bắt buộc.

## 16. Spring Boot 4 modular starters và test starters

Theo Boot 4 migration guide, hệ thống dependency/starter được module hóa chi tiết hơn. Một số tọa độ thay đổi đáng chú ý:

| Chức năng | Tọa độ Boot 3 thường dùng | Tọa độ Boot 4 migration guide |
|---|---|---|
| MVC server | `spring-boot-starter-web`. | `spring-boot-starter-webmvc`. |
| WebFlux server | `spring-boot-starter-webflux`. | `spring-boot-starter-webflux`. |
| Security core/web | `spring-boot-starter-security`. | `spring-boot-starter-security`. |
| OAuth2 client | `spring-boot-starter-oauth2-client`. | `spring-boot-starter-security-oauth2-client`. |
| OAuth2 resource server | `spring-boot-starter-oauth2-resource-server`. | `spring-boot-starter-security-oauth2-resource-server`. |
| Spring Session Redis | `spring-session-data-redis` hoặc Boot integrations. | `spring-boot-starter-session-data-redis`. |
| Security test | `spring-security-test` + Boot starter test. | `spring-boot-starter-security-test` theo tài liệu Boot 4 test modularity. |
| Web MVC test | `spring-boot-starter-test` và MVC test support. | `spring-boot-starter-webmvc-test`; chọn companion tech test starter. |

Bảng này là **điểm bắt đầu để rà soát**, không phải tuyên bố tọa độ cũ không còn resolve ở mọi repository. Chỉ sửa dependency thực có trong project và đọc migration guide tương ứng patch release; không copy tất cả starters nếu app không dùng chúng.

Boot 4 migration guide cũng nhấn mạnh test infrastructure modularization. Các annotation như `@WithMockUser`/`@WithUserDetails` nên được chạy với **security test starter tương ứng**, không dựa vào một tổ hợp transitive dependencies vô tình còn tồn tại.

Với Boot 4, Servlet baseline 6.1 làm **Undertow support bị loại** theo Boot 4.0 migration guide tại thời điểm tham khảo; nếu ứng dụng cũ dùng Undertow, đó là **migration decision**, không chỉ một dependency version bump. Đánh giá container alternative, performance và deployment constraints.

## 17. Nâng Spring Security 6.5 → 7.x có những điểm nào cần chú ý?

Tài liệu migration của Spring Security khuyến nghị lên **Security 6.5** và hoàn thành các bước chuẩn bị trước khi nâng lên 7.x. Cần rà:

1. **Deprecated APIs đã loại:** tìm các API được đánh dấu deprecated trong 6.x, đổi sang replacement theo migration docs.
2. **Lambda/Customizer DSL:** tránh dùng các lối cấu hình không còn được hỗ trợ, xác nhận `HttpSecurity` và `ServerHttpSecurity` APIs đúng nhánh.
3. **Authorization management:** kiểm tra `AuthorizationManager`, request matching và method security; đừng giả định cấu hình cũ tiếp tục match route.
4. **Default behavior:** tái kiểm public/protected endpoints, CORS/CSRF, session fixation, request cache, headers và stateless API sau upgrade.
5. **Serialization:** kiểm Jackson 2 → Jackson 3, SecurityJackson modules, OAuth2 Authorization Server persisted objects.
6. **Extensions được tích hợp:** Authorization Server/Kerberos modules và 3rd-party adapters có thể đổi tọa độ.
7. **Test dependencies:** Boot 4 companion starters, Spring Security test helpers, JUnit compatibility.
8. **Servlet containers:** Jakarta EE 11/Servlet 6.1, proxy/forwarded headers và HttpSession behavior.
9. **Reactive context:** Reactor/WebFlux/Netty versions và các custom reactive filters.
10. **Monitoring:** exception mapping, authentication events, authorization denials và log redaction.

### Jackson 3 là điểm đặc biệt quan trọng

Theo Security 7 migration guide, cách cấu hình Jackson 2 `ObjectMapper` với `SecurityJackson2Modules` chuyển sang Jackson 3 `JsonMapper.Builder` với `SecurityJacksonModules`. Authorization Server trong Security 7 mặc định dùng Jackson 3. Nếu kho token/authorization/session chứa serialized security objects, hãy kiểm tra **đọc dữ liệu cũ, ghi dữ liệu mới, rollback/rolling upgrade**; không suy rằng mọi persisted JSON đều tương thích chỉ vì security API vẫn build.

**Migration không chỉ là chạy `mvn versions:set`.** Rà runtime behavior và dữ liệu đang sống (sessions, OAuth grants, JWK keys, refresh token families).

## 18. Quy trình audit thư viện tích hợp bên ngoài

Khi dự án cần Auth0/Okta/Keycloak SDK, LDAP adapter, Nimbus/JJWT, Spring Cloud Gateway, CAS/SAML plugin, Spring Session Redis hay custom OAuth provider, lập một hồ sơ tương thích cho từng thư viện:

| Thuộc tính | Cần ghi lại |
|---|---|
| `group:artifact:version` | Coordinates chính xác và nguồn lấy artifact. |
| Maintainer / release date | Thư viện còn được bảo trì và hỗ trợ security patches không? |
| Java baseline | Java 17/21/25, bytecode compatibility, JPMS/module restrictions. |
| Spring Framework/Security baseline | Phải chạy với Security 6 hay 7, Servlet hay reactive? |
| Jakarta/Servlet/Netty | `javax.servlet` hay `jakarta.servlet`? Servlet version? Reactor Netty baseline? |
| Jackson/JSON | Jackson 2 vs 3, serializer module, API type. |
| Role trong authentication | Client, Resource Server, Authorization Server, Gateway, token parser, Identity Provider adapter? |
| Authentication principal type | `OAuth2User`, `OidcUser`, `JwtAuthenticationToken`, custom `Authentication`? |
| Filter/WebFilter | Cắm vào chain nào, thứ tự nào, matcher nào? |
| Trust contract | Token signature/issuer/audience, TLS, forwarded headers, IdP trust. |
| Configuration properties | Auto-config metadata, property name, bean-conditional behavior. |
| Tests | Unit, integration, contract against IdP/backend, negative security cases. |
| Vulnerabilities / license | CVE, transitive dependencies, EOL, upgrade path. |

**Tuyên bố “Spring Boot compatible” của nhà cung cấp không đủ.** Phải nêu rõ **Boot 3.x vs Boot 4.x, Servlet vs reactive, Spring Security 6.x vs 7.x**. Nếu adapter chỉ hỗ trợ Servlet filters, không được nhét nó vào WebFlux và xem một unit test compile là bằng chứng.

Đối với custom integration, ưu tiên **adapter nhỏ theo interface chuẩn của Spring Security**, tách crypto verification, subject mapping và token/permission policy khỏi web filter; cách này giúp migration dễ hơn và giảm vendor lock-in.

## 19. Audit thứ tự filters và “đường bypass” khi tích hợp SDK

Một SDK ngoài thường cung cấp Servlet `Filter`, `OncePerRequestFilter`, Spring `AuthenticationProvider` hoặc WebFlux `WebFilter`. Khi cài đặt:

~~~text
Ingress -> Spring Security FilterChainProxy
             |
             +-- request matcher picks chain
             +-- custom SDK filter at chosen order
             +-- bearer / form / oauth2 filter
             +-- SecurityContext
             +-- AuthorizationFilter
             |
          Controller / Method security
~~~

Các câu hỏi cần trả lời:

- Filter SDK chạy **bên trong** hay bên ngoài `FilterChainProxy`?
- Nó có set `SecurityContextHolder` trước khi token được xác minh không?
- Nó có bỏ qua authorization filter hoặc trả HTTP 200 khi authentication thất bại không?
- Nó có tạo `Authentication` đúng loại và dùng manager/provider phù hợp không?
- Nó có phát event audit nhiều lần, hoặc không phát event ở custom path?
- Nếu SDK ném exception, `AuthenticationEntryPoint`/`AccessDeniedHandler` của ứng dụng có xử lý được không?
- Nó có đọc bearer token/cookie từ query string hoặc ghi vào logs không?
- Với reactive, nó có dùng Reactor Context thay vì Servlet ThreadLocal không?
- Đường logout/revoke và session cleanup có hoạt động khi SDK version mới thay principal class không?

**Không bao giờ khắc phục SDK mismatch bằng cách `permitAll` endpoint nhạy cảm hoặc tự đặt `authenticated=true`.** Một lỗi tích hợp phải fail closed.

## 20. Kiểm thử: MockMvc khác WebTestClient và client-bound testing

**Servlet / MockMvc:**

~~~java
import static org.springframework.security.test.web.servlet.setup
    .SecurityMockMvcConfigurers.springSecurity;

// Tích hợp vào Spring MVC WebApplicationContext test:
MockMvc mvc = MockMvcBuilders.webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

`MockMvc` + `springSecurity()` chạy Servlet security filters của test context. `@WithMockUser`/`user()` giả lập authenticated principal để test authorization. Nếu muốn chứng minh password login, phải gửi `formLogin()` với `UserDetailsService`/provider thật theo profile test.

**Reactive / WebTestClient:**

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

// Tích hợp vào WebFlux ApplicationContext test:
WebTestClient client = WebTestClient.bindToApplicationContext(context)
    .apply(springSecurity())
    .configureClient()
    .build();
~~~

`mockUser()`/`mockJwt()` reactive security configurers đặt authentication vào reactive exchange. Chúng không giống Servlet `SecurityMockMvcRequestPostProcessors.user()`/`jwt()`.

**Một lưu ý:** `WebTestClient` cũng có adapter cho MockMvc hoặc gọi HTTP server thực; tên client alone không chứng minh runtime đang dùng WebFlux. Chọn security mutators theo **server binding type**.

### Những thứ mock không kiểm tra

- `jwt()`/`mockJwt()` không xác minh JWT signature, issuer, audience hay expiry của token thật.
- `@WithMockUser` không kiểm PasswordEncoder, account lock/disable hoặc login provider.
- `mockOAuth2Login`/`oidcLogin()` không tự kiểm authorization-code callback, `state`, `nonce` hay PKCE.
- Một controller test slice có thể không bao gồm full security configuration hoặc custom filters.

Muốn test an toàn, kết hợp **positive/negative HTTP integration tests**, decoder/provider unit tests, và IdP/LDAP/Redis external contract tests qua test container/mock server đáng tin.

## 21. Java 17 độc lập: ma trận quyết định thay vì đoán stack

Chương trình sau **chạy được bằng JDK 17 thuần**, không có Spring dependency. Nó minh họa quy trình **chọn đúng cấu hình và cảnh báo mâu thuẫn** từ một bộ mô tả triển khai. Nó **không** introspect Maven dependencies, không có security filter thật, và không thay kết quả test. Dùng để học cách chuẩn hóa quyết định trước khi review thư viện tích hợp.

Lưu tệp `SecurityStackAuditDemo.java`:

~~~java
public class SecurityStackAuditDemo {

    enum Stack { SERVLET, REACTIVE }
    enum LibraryKind { SERVLET_FILTER, REACTIVE_WEBFILTER, PURE_CRYPTO }

    record AuditRequest(Stack stack, LibraryKind library,
                        int bootMajor, int securityMajor,
                        boolean jackson2Serializer) {}

    static String audit(AuditRequest request) {
        if (request.bootMajor() == 3 && request.securityMajor() != 6) {
            return "VERSION_MISMATCH";
        }
        if (request.bootMajor() == 4 && request.securityMajor() != 7) {
            return "VERSION_MISMATCH";
        }
        if (request.bootMajor() != 3 && request.bootMajor() != 4) {
            return "UNSUPPORTED_EXAMPLE_PAIR";
        }
        if (request.stack() == Stack.SERVLET
                && request.library() == LibraryKind.REACTIVE_WEBFILTER) {
            return "WRONG_WEB_STACK";
        }
        if (request.stack() == Stack.REACTIVE
                && request.library() == LibraryKind.SERVLET_FILTER) {
            return "WRONG_WEB_STACK";
        }
        if (request.bootMajor() == 4 && request.jackson2Serializer()) {
            return "REVIEW_JACKSON_MIGRATION";
        }
        return "REVIEW_EXTERNAL_CONTRACT";
    }

    static void show(String name, AuditRequest request) {
        System.out.println(name + ": " + audit(request));
    }

    public static void main(String[] args) {
        show("mvc-ok", new AuditRequest(
                Stack.SERVLET, LibraryKind.SERVLET_FILTER,
                3, 6, false));
        show("wrong-security-major", new AuditRequest(
                Stack.SERVLET, LibraryKind.SERVLET_FILTER,
                3, 7, false));
        show("reactive-servlet-sdk", new AuditRequest(
                Stack.REACTIVE, LibraryKind.SERVLET_FILTER,
                4, 7, false));
        show("mvc-reactive-filter", new AuditRequest(
                Stack.SERVLET, LibraryKind.REACTIVE_WEBFILTER,
                4, 7, false));
        show("jackson-migration", new AuditRequest(
                Stack.REACTIVE, LibraryKind.PURE_CRYPTO,
                4, 7, true));
        show("reactive-ok", new AuditRequest(
                Stack.REACTIVE, LibraryKind.REACTIVE_WEBFILTER,
                4, 7, false));
    }
}
~~~

Chạy:

~~~bash
javac SecurityStackAuditDemo.java
java SecurityStackAuditDemo
~~~

**Stdout chính xác:**

~~~text
mvc-ok: REVIEW_EXTERNAL_CONTRACT
wrong-security-major: VERSION_MISMATCH
reactive-servlet-sdk: WRONG_WEB_STACK
mvc-reactive-filter: WRONG_WEB_STACK
jackson-migration: REVIEW_JACKSON_MIGRATION
reactive-ok: REVIEW_EXTERNAL_CONTRACT
~~~

Giải thích:

- Tổ hợp Boot 3/Security 6 hoặc Boot 4/Security 7 **đúng thế hệ** chưa chứng minh dependency transitives an toàn; vẫn cần contract test.
- Servlet filter trong reactive server không thuộc đúng server abstraction.
- Reactive WebFilter trong Servlet MVC server không bảo vệ servlet request.
- Boot 4/Security 7 với serializer còn phụ thuộc Jackson 2 cần rà data migration/config.
- Chương trình cố ý chỉ phân nhóm sơ bộ; nó không quyết định patch-level compatibility, availability, annotations hay release train chính xác.

Trong thực tế, lấy input từ Maven/Gradle `dependency:tree`, Spring Boot BOM, security filter chain, IdP contracts và release notes, **không chỉ từ code check major**.

## 22. Ma trận kiểm thử sau upgrade và thêm thư viện

| Kịch bản | Servlet | Reactive | Thư viện ngoài / dữ liệu |
|---|---|---|---|
| Anonymous truy cập endpoint bảo vệ. | Expected redirect/401 đúng entry point. | Expected 401/redirect theo WebFilter config. | Gateway không bypass. |
| Role USER gọi ADMIN endpoint. | `403` hoặc policy-defined denial. | Reactive authorization denial. | SDK không tự tạo admin authority. |
| Password đúng/sai. | Provider/PasswordEncoder chạy thật. | Reactive manager/user store chạy thật. | LDAP/IdP timeout, status disabled. |
| Bearer JWT hợp lệ. | Servlet JwtDecoder/claims converter. | ReactiveJwtDecoder/converter. | JWKS/kid rotation, issuers. |
| JWT sai `aud`/`iss`/`exp`/signature. | Từ chối. | Từ chối. | Không bypass bởi external decoder. |
| OAuth2 Login callback/state/nonce. | Session request repository và OIDC login. | Reactive login flow. | IdP redirect URI, client auth, PKCE. |
| MFA chưa hoàn thành. | Không có elevated permission. | Tương đương reactive policy. | MFA SDK chứng minh assurance, challenge expiry. |
| Logout và revoke sessions. | Servlet session store invalidated. | WebSession invalidated. | Redis/IdP grants đã revoke đúng scope. |
| CSRF thiếu/invalid trên state-changing cookie POST. | Chặn. | Chặn. | Gateway không disable header/protection. |
| Multiple chains + custom matcher. | Chính xác chain theo `@Order`. | Chính xác WebFilterChain theo matcher. | SDK filter thuộc đúng chain/order. |
| Cross-tenant access. | Deny. | Deny. | Issuer/tenant mapping tin cậy. |
| Reverse proxy headers bị giả. | Host/scheme/IP không bị spoof. | Tương đương. | Gateway sanitize. |
| Session được tạo ở phiên bản trước. | Đọc hoặc logout theo migration plan. | Đọc hoặc re-auth có kế hoạch. | Serializer Jackson3/Redis key compatibility. |
| Authorization Server persisted grants. | Client/server interaction không lỗi. | Nếu server hỗ trợ stack này. | Jackson2→3, token revocation, JWK. |
| Test fixture `@WithMockUser`. | Chỉ chứng minh authorization mock. | Chỉ chứng minh auth context mock. | Security-test version/test starter đúng. |
| Blue/green upgrade. | Old/new nodes không cho bypass. | Old/new nodes không context leak. | Token/session/Redis schema and rollback. |

**Phân loại rõ regression:** startup/classpath, filter configuration, authentication, authorization, session/serialization, external protocol, observability. Một build compile thành công nhưng authorization tests thiếu negative cases **chưa đủ** để approve migration.

### Tại sao cần cả contract test với IdP?

Một client OIDC có thể tạo `OAuth2AuthenticationToken` mock hợp lệ trong test, nhưng production callback lỗi vì redirect URI, issuer metadata, client secret, JWK `kid` hoặc `SameSite` cookie. Contract test với IdP sandbox (hoặc mô phỏng đúng protocol) giúp phát hiện các lỗi đó. Không để CI dùng real production credentials hoặc gửi OTP thật của người dùng.

## 23. Runbook rà soát khi cần đổi major version

### Pha 1 — Inventory

1. Ghi Boot, Spring Framework, Spring Security, Java, Servlet/Jakarta, Reactor/Netty và Spring Cloud versions.
2. Xác định app là Servlet hay Reactive bằng **runtime** (không chỉ nhìn tên dependency).
3. Liệt kê tất cả Spring Security modules và external auth providers/SDKs.
4. Xác định các điểm mở rộng: filters, WebFilters, providers, converters, managers, security contexts, sessions, token serializers.
5. Ghi lại public URLs, issuer/audience, OAuth2 callback/redirect URIs, cookie policy, Gateway trust boundary.

### Pha 2 — Compatibility review

1. Chọn Boot BOM mục tiêu theo support policy/maintenance release.
2. Theo Spring Security migration guide tương ứng; nếu từ 6.x lên 7.x, nâng tới 6.5 và hoàn thành preparation steps trước.
3. Đối chiếu Jakarta EE 11 / Servlet 6.1 và server dependencies khi lên Boot 4.
4. So sánh Boot 4 starter/test-starter artifact names và Jackson 3 migration.
5. Đối chiếu Spring Cloud release train và external SDK matrix.
6. Phân loại library không tương thích: thay thế, cô lập adapter, nâng phiên bản hoặc chưa nâng main app.
7. Chuẩn bị migration persisted session/grant/cache schema; thiết kế rollback.

### Pha 3 — Implement

1. Giữ code Servlet chỉ ở Servlet module, reactive chỉ ở WebFlux module hoặc bridge rõ contract.
2. Sửa deprecated/removed APIs, imports Jakarta, dependency coordinates.
3. Cập nhật custom authentication/authorization providers và error mapping.
4. Xác minh principal/context propagation và không block reactive event loop.
5. Rà JWT validators, IdP metadata, multi-tenant mapping và token revocation.
6. Điều chỉnh test starters, security test helpers, mocks/fixtures và negative tests.

### Pha 4 — Verify & deploy

1. Chạy dependency convergence, SBOM/CVE scan, unit, MockMvc/WebTestClient integration, external contract tests.
2. Test thực qua public proxy với TLS/cookie/redirect; so `Location`, `Set-Cookie` và IdP callback.
3. Thử blue/green và rollback khi sessions/tokens cùng tồn tại giữa versions.
4. Dùng canary và metrics: `401`/`403`, redirect loops, auth failures, latency, WebFlux event loop saturation, session deserialization errors.
5. Đặt tiêu chí rollback nếu login success rate giảm hoặc có authorization bypass.
6. Sau deploy, rà application logs để không lộ token, password, OTP, cookies hoặc sensitive claims.

**Đừng dùng thay đổi security major version làm nơi thử nghiệm ngẫu nhiên mọi integration cùng lúc.** Chia migration thành các bước kiểm chứng được và giữ cơ chế rollback phù hợp phiên dữ liệu đang tồn tại.

## 24. Các lỗi suy luận phổ biến

**Lỗi 1 — “Có WebClient tức ứng dụng là WebFlux”.** Sai; một Servlet app có thể dùng WebClient. Runtime web application type và filter/security context mới là tiêu chí.

**Lỗi 2 — “`SecurityFilterChain` bảo vệ cả reactive request”.** Sai trong WebFlux; cần `SecurityWebFilterChain`/`ServerHttpSecurity`.

**Lỗi 3 — “`SecurityContextHolder` luôn mang principal đúng trong Reactor”.** Sai; reactive cần Reactor Context và context propagation phù hợp.

**Lỗi 4 — “Boot đã quản lý phiên bản nên SDK ngoài chắc chắn tương thích”.** BOM quản lý nhiều artifacts nhưng không chứng minh một adapter proprietary hỗ trợ Security 7/Jakarta 11.

**Lỗi 5 — “Thêm `oauth2Login` là API tự xác thực JWT”.** Sai; resource-server có role/config khác với OAuth2 client.

**Lỗi 6 — “JWT decode payload được là token hợp lệ”.** Sai; phải verify signature và policy claims.

**Lỗi 7 — “Mock JWT test xanh chứng minh production JWT verifier an toàn”.** Sai; `jwt()`/`mockJwt()` tạo authentication test.

**Lỗi 8 — “Đổi javax.servlet sang jakarta.servlet là xong migration”.** Chưa đủ; runtime container, framework, filter registration, Jakarta APIs và dependencies cũng phải tương thích.

**Lỗi 9 — “Boot 4 chỉ đổi version của starter web”.** Không; Boot 4 modular starters/test starters, Jackson 3 và Servlet 6.1 có tác động đáng kể.

**Lỗi 10 — “Spring Session Redis dùng chung keyspace sẽ đọc được context hai major versions”.** Không đảm bảo; thử serialization/rolling upgrade.

**Lỗi 11 — “Proxy xác thực rồi backend có thể tin bất kỳ X-Forwarded-User”.** Sai; phải strip inbound headers, đóng backend và định nghĩa trust contract.

**Lỗi 12 — “Reactor event loop có thể chạy LDAP/JDBC blocking tự nhiên”.** Sai; đánh giá throughput và bounded scheduling, không block event loop.

**Lỗi 13 — “Provider bean hiện diện là mọi security chain sẽ dùng”.** Không nhất thiết; manager/chain-local wiring quyết định.

**Lỗi 14 — “Nâng patch mới nhất của từng Security module riêng lẻ là an toàn”.** Sai; giữ managed version set thống nhất.

## 25. Checklist kết luận cho người triển khai

- [ ] Xác định **runtime server stack** bằng cấu hình thật: Servlet MVC hay WebFlux.
- [ ] Có inventory Boot, Security, Framework, Java, Jakarta/Servlet, Reactor/Netty, Cloud và third-party dependencies.
- [ ] Dùng BOM/release train tương thích, không trộn nhiều Security major versions.
- [ ] Đã đọc migration guide 6.5→7.x nếu nâng Security 7, kể cả deprecations và Jackson 3.
- [ ] Khi lên Boot 4, rà Servlet 6.1/Jakarta EE 11, starter/test-starter names và embedded container.
- [ ] Servlet config dùng `HttpSecurity`/`SecurityFilterChain`; reactive dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.
- [ ] Không lấy principal từ Servlet ThreadLocal trong reactive flow thiếu context bridge.
- [ ] Custom filters/WebFilters, AuthenticationManagers/providers và request matchers ở đúng chain.
- [ ] JWT/OIDC/SAML/LDAP/WebAuthn modules được kiểm theo stack/version, không chỉ tên thư viện.
- [ ] OAuth2 Client, Resource Server và Authorization Server được phân vai và cấu hình riêng.
- [ ] IdP discovery/issuer/audience/signatures, callback URIs và state/nonce/PKCE được test thật.
- [ ] Spring Session serialization và rolling upgrade/rollback được kiểm chứng.
- [ ] Gateway/proxy trust, token relay, headers và CSRF/CORS/session boundaries không tạo bypass.
- [ ] spring-security-test/mock helpers chỉ được coi là auth mocks; có integration tests cho credential verification.
- [ ] External SDK có bảng support, release dates, CVEs, bytecode/Jakarta/Jackson alignment và contract tests.
- [ ] Test đầy đủ positive/negative, cross-tenant, disabled account, expired token, revoked session và missing factor.
- [ ] Logging không chứa raw tokens/password/OTP/cookies; có metrics/canary/rollback threshold.

## 26. Tổng kết

Rà soát phiên bản Spring Security **không chỉ là kiểm tra version number**. Cần xác minh ba lớp:

1. **Stack contract:** Servlet filters/HttpSecurity/SecurityFilterChain khác Reactive WebFilters/ServerHttpSecurity/SecurityWebFilterChain, nhất là security context, sessions và blocking I/O.
2. **Version contract:** Spring Boot BOM quyết định bộ Framework/Security/Jakarta/Reactor/Jackson tương thích; Spring Security 6.5 là bước chuẩn bị được khuyến nghị trước Security 7, và Boot 4 có đổi mới lớn ở Jakarta EE 11, Servlet 6.1, Jackson 3, modular starters/test infrastructure.
3. **Integration contract:** OAuth2 client, resource server, authorization server, SAML2, LDAP, WebAuthn, Spring Session, Gateway và các SDK ngoài phải có hỗ trợ chính thức **cho đúng runtime và major version**, đồng thời vượt qua integration/negative security tests.

Một hệ thống an toàn là hệ thống **có chứng cứ** cho mỗi ranh giới xác thực: token được verify, provider được gọi trong đúng chain, principal/context không rò giữa requests, role/tenant/assurance được kiểm tại tài nguyên, dữ liệu phiên/grant còn đọc được sau migration và rollback có kế hoạch. Không biến lỗi compatibility thành lý do để tắt bảo mật.

## Tài liệu tham khảo chính thức

- [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/): khuyến nghị chuẩn bị ở Security 6.5, migration và Jackson 3.
- [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html): tính năng, removals và thay đổi module.
- [Spring Security — Project Modules and Dependencies](https://docs.spring.io/spring-security/reference/modules.html): Core, Web, Config, LDAP, OAuth2 Client/JOSE/Resource Server, Test.
- [Spring Security — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `HttpSecurity`, `SecurityFilterChain` và multiple chains.
- [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain` và multiple chains.
- [Spring Security — Reactive Authentication](https://docs.spring.io/spring-security/reference/reactive/authentication/index.html): reactive authentication architecture.
- [Spring Security — Servlet OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): decoder, issuer, validators và bearer token processing.
- [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reactive decoder/resource server.
- [Spring Security — Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc security integration.
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): WebTestClient security integration.
- [Spring Boot — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html): Servlet/reactive auto-configuration và customization.
- [Spring Boot — Managed Dependency Coordinates](https://docs.spring.io/spring-boot/appendix/dependency-versions/coordinates.html): kiểm tra versions do BOM quản lý.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): modular starters/test starters, Servlet baseline, breaking changes.
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java/Framework/Servlet container baseline.
- [Spring Framework 7.0 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-7.0-Release-Notes): Jakarta EE 11, Java baseline, Jackson 3 và core changes.
- [Spring Cloud — Release Trains](https://spring.io/projects/spring-cloud): đối chiếu Cloud train với Boot releases.
- [Spring Session — Reference](https://docs.spring.io/spring-session/reference/): session store, Servlet/reactive integration và persistence.
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): xác thực, chống enumeration và hệ quả security policy.
- [OWASP — JSON Web Token for Java Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): JWT validation/rủi ro phổ biến.
