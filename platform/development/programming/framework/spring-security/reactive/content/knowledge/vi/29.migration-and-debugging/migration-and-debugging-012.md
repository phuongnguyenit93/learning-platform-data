# Đọc tài liệu nâng cấp và kiểm tra thay đổi mặc định theo phiên bản trong Spring Security Reactive

## 1. Vì sao phải đọc migration guide và xác minh lại default?

Một ứng dụng WebFlux có thể **biên dịch thành công nhưng thay đổi hành vi bảo mật** sau khi nâng Spring Boot, Spring Framework hoặc Spring Security. Mã cấu hình không đổi không bảo đảm rằng mọi request sẽ nhận cùng kết quả: giá trị mặc định của CSRF, cách ánh xạ quyền, bộ giải mã JWT, thứ tự filter, cơ chế xử lý lỗi, session hoặc auto-configuration có thể khác. Ngược lại, nhiều thay đổi được mô tả trong migration guide chỉ áp dụng cho **Servlet** và không nên sao chép vào **Reactive**.

Ví dụ: ứng dụng trước đây nhận token CSRF theo cách cũ nhưng phiên bản mới dùng cách xử lý chống BREACH; trình duyệt bị HTTP 403 mặc dù role vẫn đúng. Hoặc API phát hành JWT riêng dùng giá trị `typ` tùy chỉnh; khi nâng phiên bản, cần so sánh cách xác minh type và tập validator trước khi quyết định xóa một cấu hình tạm thời. Nếu chỉ sửa cho “test xanh” bằng `csrf.disable()` hoặc chấp nhận mọi JWT type, có thể tạo lỗ hổng.

Sau bài này, bạn có thể:

1. Đọc đúng tài liệu cho **phiên bản đang chạy, phiên bản đích, WebFlux** và mọi điểm trung gian.
2. Phân biệt **thay đổi API/DSL**, **thay đổi mặc định**, **thay đổi hành vi**, **thay đổi phụ thuộc** và **thay đổi cấu hình của chính ứng dụng**.
3. Tự lập bảng quyết định trước/sau theo tình huống đăng nhập, phân quyền, CSRF, CORS, OAuth2/JWT, session, HTTP status và security headers.
4. Dùng `WebTestClient` cùng `spring-security-test` để biến hành vi bảo mật mong đợi thành kiểm thử có thể chạy ở cả phiên bản cũ và mới.
5. Nâng cấp theo chặng, thu thập bằng chứng, tìm nguyên nhân và rollback an toàn khi kiểm thử phát hiện sai khác.

**Phạm vi:** ứng dụng **Spring Security Reactive** trên Spring WebFlux, với `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveSecurityContextHolder`, `ReactiveAuthenticationManager` và các kiểu client như HTTP Basic, cookie/session, OAuth2 Login hoặc resource server bearer token. Các ví dụ dùng Java 17. Bài không giả định mọi thay đổi được liệt kê đều ảnh hưởng tới tất cả ứng dụng: cần so sánh đúng chức năng đang được sử dụng.

## 2. Bước đầu tiên: cố định phiên bản thực tế, không suy từ tên tài liệu

Một dự án thường có nhiều số phiên bản liên quan:

| Thành phần | Vai trò | Vì sao cần ghi lại |
| --- | --- | --- |
| JDK | Runtime và toolchain | Bản nâng cấp có thể yêu cầu JDK tối thiểu mới hoặc thay đổi TLS/crypto provider |
| Spring Boot | BOM/dependency management và auto-configuration | Đổi parent/BOM có thể đồng thời đổi nhiều thư viện |
| Spring Framework / WebFlux | HTTP stack, codec, reactive context | Các thay đổi ở WebFlux ảnh hưởng request, response, exception |
| Spring Security | Authentication, authorization, CSRF, OAuth2, headers | Migration guide chính để rà soát các điều khiển bảo mật |
| Reactor / Reactor Netty | Publisher, scheduler, HTTP server/client | Context propagation, pipeline, timeout và event loop |
| Jackson | JSON/serialization, đặc biệt session/token serialization tùy ứng dụng | Bản major có thể đổi API, format, module |
| Spring Session, OAuth2 client, gateway, test libraries | Thành phần tùy chọn | Tương thích giữa các artifact không được suy ra từ một số version |

**Phải lưu hai bộ số liệu:** `baseline` là phiên bản *đang vận hành*, `candidate` là phiên bản *dự kiến phát hành*. Đừng dùng URL tài liệu `/reference/` không gắn version rồi đọc như thể nó mô tả hành vi của bản đang chạy. Trang mặc định thường chuyển sang nhánh mới nhất.

Ví dụ bảng đầu vào cho đợt nâng cấp:

| Thuộc tính | Baseline | Candidate | Nguồn xác minh |
| --- | --- | --- | --- |
| Java | 17 | Theo yêu cầu tương thích của candidate | `java -version`, build pipeline |
| Spring Boot | 3.x.y | Phiên bản đích được duyệt | Parent/BOM, `dependency:tree` |
| Spring Security | Do BOM thực sự resolve | Do BOM candidate resolve | Effective dependencies |
| WebFlux | Đang chạy ở stack Reactive | Vẫn Reactive | Dependency graph, application context |
| Authentication flow | Basic / form / OIDC / JWT / opaque | Có thay đổi hay không? | Cấu hình `SecurityWebFilterChain`, bean và test |
| Session/CSRF | Cookie/WebSession hay bearer thuần | Chính sách giữ hoặc đổi | Browser, config, test |
| Gateway/TLS/route | Rule/headers đang hoạt động | Rule/headers candidate | Test ở public ingress |

Không ghi “Security 6” khi thực tế chỉ biết Boot 3: phải tra artifact được resolve. Cũng không nên nâng riêng `spring-security-*` vượt khỏi BOM của Boot khi chưa có bằng chứng tương thích. Nếu buộc override một bản vá Security, lưu rõ lý do, version chính xác, BOM liên quan và bộ test tương thích.

### 2.1. Thu thập version bằng Maven

Trong một dự án Maven thực tế:

```bash
java -version
./mvnw -version
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw dependency:tree -Dincludes=io.projectreactor
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core
```

Nếu dùng Maven hệ thống thay vì wrapper, thay `./mvnw` bằng `mvn`; trên Windows có thể dùng `mvnw.cmd`. Kết quả `dependency:tree` cần được lưu vào artifact CI theo build ID. Đọc `effective-pom.xml` trong môi trường nội bộ; nó có thể chứa cấu hình repository và thuộc tính không nên công khai.

### 2.2. Thu thập version bằng Gradle

Ví dụ khi dùng Gradle và plugin Java/Spring Boot:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-webflux
./gradlew dependencyInsight --configuration runtimeClasspath --dependency spring-security-config
./gradlew dependencyInsight --configuration runtimeClasspath --dependency reactor-core
```

Dùng configuration thực tế của dự án; nếu `runtimeClasspath` không tồn tại thì kiểm tra model Gradle, thay bằng configuration hợp lệ. Không kết luận package đang chạy dựa vào dependency khai báo trực tiếp: dependency constraint, resolution strategy, platform/BOM, dependency lock hoặc lớp trong runtime artifact có thể làm version khác dự kiến.

## 3. Đọc tài liệu nâng cấp đúng thứ tự và đúng hệ

Mỗi bước phải trả lời bốn câu: **đang ở đâu, muốn tới đâu, thay đổi nào có hiệu lực, bằng chứng xác nhận là gì?**

### 3.1. Nguồn tài liệu cần kiểm tra theo thứ tự

1. **Release notes / security advisories** của bản đích và tất cả phiên bản trung gian: bug fix, CVE, hành vi cố ý thay đổi, tính năng bị deprecate/remove.
2. **Spring Boot migration guide**: cấu hình và auto-configuration, tên starter/module, dependency management, Actuator, Jackson, Spring Framework, minimum Java.
3. **Spring Security preparation guide** của major đích: đưa code lên trạng thái tương thích trong bản cũ trước khi bật hành vi mới, ví dụ chuẩn bị 6.5 trước khi lên 7.
4. **Spring Security migration guide** bản đích, chọn nhánh **Reactive**. Mục **Servlet** chỉ là tham khảo nếu ứng dụng có cả Servlet ở module khác; không sao chép API Servlet vào WebFlux.
5. **Reference và Javadoc theo đúng version** cho từng symbol đang dùng: `SecurityWebFilterChain`, `ServerHttpSecurity`, `ServerWebExchangeMatcher`, `ReactiveJwtDecoder`, `ServerCsrfTokenRepository`, v.v.
6. **Spring Security test reference** cùng dòng phiên bản và issue/release notes cho bug cụ thể. Khi source code và tài liệu mô tả không nhất quán, ưu tiên xác minh bằng test nhỏ có version lock và ghi nhận vấn đề.

Các trang gốc có thể xem:

- Spring Security migrations: https://docs.spring.io/spring-security/reference/migration/
- Spring Security reactive migration: https://docs.spring.io/spring-security/reference/migration/reactive.html
- Preparation for Security 7 trên nhánh Security 6.5: https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html
- Configuration migration 6.5 → 7: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security Reactive: https://docs.spring.io/spring-security/reference/reactive/index.html
- Spring Boot reference: https://docs.spring.io/spring-boot/reference/

**Quy tắc phiên bản:** pin `/6.5/`, `/7.0/` hoặc một nhánh tài liệu phù hợp khi đối chiếu, ghi ngày truy cập và commit/build đang thử. Không dùng trang SNAPSHOT/RC làm chuẩn sản xuất nếu chưa chủ động chọn release đó. Khi nội dung phiên bản hiện tại trong tài liệu thay đổi, hãy lấy lại link tương ứng với phiên bản đang kiểm thử.

### 3.2. Đọc thay đổi thành checklist kỹ thuật

Một mục trong migration guide phải được chuyển thành một quyết định kiểm chứng được:

| Câu hỏi khi đọc | Cách ghi lại |
| --- | --- |
| Thay đổi áp dụng ở phiên bản nào? | Major/minor/patch chính xác và link tài liệu |
| Áp dụng cho Reactive hay Servlet? | Stack; class API; module |
| Cần điều kiện gì để bị tác động? | Ví dụ: dùng JWT decoder tùy chỉnh hoặc token CSRF tự xử lý |
| Trước đây hành vi mặc định là gì? | Baseline test, Javadoc version cũ |
| Sau nâng cấp điều gì được thay thế? | Candidate test, config mới |
| Cấu hình hiện tại override default không? | Link tới đoạn config/bean, property hoặc custom filter |
| Có thay đổi ý nghĩa bảo mật không? | Risk, negative/positive test, owner |
| Khi fail thì xử lý thế nào? | Cách sửa đúng, điều kiện rollback, không hạ security vô tội vạ |

Nên ưu tiên mục **Removed**, **Deprecated**, **Changed default**, **Behavioral change** và **Security hardening**. Một lỗi compile thường dễ phát hiện; sai khác runtime khi không có kiểm thử thường nguy hiểm hơn.

### 3.3. Đừng nhầm source compatibility với behavior compatibility

- **Source compatibility:** các import và method vẫn tồn tại, mã biên dịch.
- **Binary compatibility:** thư viện/plugin đã biên dịch vẫn liên kết runtime.
- **Configuration compatibility:** bean/properties có còn được Boot auto-config hoặc Spring Security sử dụng như trước?
- **Behavior compatibility:** cùng request và cùng credential có cùng quyết định cho phép/từ chối, cùng header, session và exception?
- **Data compatibility:** serialized session, OAuth2 authorized-client records, encrypted tokens hoặc stored password hash cũ còn được đọc sau triển khai?
- **Operational compatibility:** TLS/cipher, logging, metrics, latency, tracing, gateway, browser/IdP tương tác đúng?

Chỉ chạy unit test cho controller thì thường mới kiểm tra được một phần. Những thay đổi trong `WebFilter` hoặc default configuration xảy ra trước khi controller được gọi.

## 4. Các nhóm default phải kiểm tra riêng trong ứng dụng Reactive

Không cần tất cả nhóm đều thay đổi ở mỗi version. Nhưng với mỗi nhóm đang được sử dụng, phải xác nhận nó bằng test và đối chiếu release notes đúng khoảng nâng cấp.

| Nhóm | Điều cần so sánh trước/sau | Dấu hiệu thay đổi |
| --- | --- | --- |
| Auto-configuration Boot | Khi có/không có bean `SecurityWebFilterChain`, user mặc định, cơ chế login, thứ tự config | Toàn bộ API tự nhiên 401/302 hoặc route trở nên public |
| Authentication | Basic/form/OAuth2/JWT/opaque, issuer, audience, timestamp, authorities, password encoder, entry point | Login thất bại, token hợp lệ bị 401, thông báo lỗi sai |
| Authorization HTTP | `securityMatcher` chọn chain, `pathMatchers` và thứ tự, rule cuối `denyAll/authenticated` | USER vào được admin, route mới không được bảo vệ |
| Reactive method security | `@EnableReactiveMethodSecurity`, `@PreAuthorize`, principal/role, return type `Mono/Flux` | HTTP mở đúng nhưng dữ liệu của tenant khác bị đọc |
| CSRF | Enabled, repository, cách token đến client, token handler và xử lý unsafe methods | POST hợp lệ bị 403 hoặc POST không token vẫn được xử lý |
| CORS | Preflight, origin/method/header/credentials, filter order | OPTIONS nhận 401/302, origin lạ đọc được dữ liệu |
| Headers và cookie | HSTS, CSP, frame, nosniff, cache, SameSite, Secure, HttpOnly | Header bị mất trên 200/401/403, session cookie thay đổi |
| Session và reactive context | `WebSession`, `ServerSecurityContextRepository`, Reactor Context, authentication save/load | Principal trống sau redirect, dữ liệu user không đi theo pipeline |
| OAuth2 login/client | Redirect URI, callback, state, authorized client, role mapping | Redirect loop, login xong vẫn 403, refresh không hoạt động |
| Resource server JWT | `ReactiveJwtDecoder`, `typ`, issuer, audience, signature, JWKS, clock skew | JWT hợp lệ bị 401 hoặc token không đúng purpose lại được chấp nhận |
| Resource server opaque token | `ReactiveOpaqueTokenIntrospector`, client auth encoding và timeout | Introspection bị 401 hoặc chậm bất thường |
| Error mapping | 401/403/5xx, failure handler, exception propagation | Lỗi hệ thống bị báo là sai credential hoặc rò exception |
| Test/security integration | `WebTestClient`, `spring-security-test`, mock principal/CSRF, real vs mock client | Test xanh nhờ mock nhưng production bị fail |
| Logging/observability | request/trace correlation, reactive context, masking, audit event | Mất trace, log trùng, lộ token |

**Ưu tiên kiểm tra explicit config lẫn implicit default.** Nếu ứng dụng tự khai báo `SecurityWebFilterChain`, hành vi của Boot auto-config sẽ khác trường hợp không khai báo. Một bài viết nói “mặc định tất cả request cần authentication” không đủ để kết luận ứng dụng của bạn như vậy.

## 5. Những thay đổi đã được tài liệu mô tả: cách đọc không nhầm stack

### 5.1. Reactive CSRF: từ Security 5.8 sang Security 6.0

Tài liệu Reactive CSRF nêu: ở **5.8**, `ServerCsrfTokenRequestAttributeHandler` là handler mặc định; từ **6.0**, mặc định chuyển thành `XorServerCsrfTokenRequestAttributeHandler` nhằm cung cấp bảo vệ BREACH. CSRF vẫn được bật mặc định cho các thao tác HTTP không an toàn.

Điều này có nghĩa:

- Người dùng có session cookie và gọi `POST` cần gửi token CSRF đúng cơ chế.
- Nếu SPA lấy token rồi gửi header, phải kiểm tra cách token được hiển thị và giải mã theo handler. Không tự sửa bằng cách bỏ xác thực token.
- Dùng `CookieServerCsrfTokenRepository` hay `WebSessionServerCsrfTokenRepository` là một **quyết định lưu token**, còn handler xử lý token request là một **quyết định khác**.
- Nếu tự tùy biến handler, cần kiểm tra rằng biện pháp chống BREACH vẫn phù hợp; thay về handler cũ có thể mất phòng vệ, nên yêu cầu threat review.

Ví dụ cấu hình để **giữ cơ chế mặc định của version đang chạy**:

```java
// Đoạn trong @Bean SecurityWebFilterChain trên WebFlux:
http.csrf(org.springframework.security.config.Customizer.withDefaults());
```

Để so sánh một baseline cũ với candidate mới, chạy bốn thử nghiệm: GET form/token, POST không token, POST token sai, POST token lấy theo cơ chế chính thức và gửi đúng header. Kiểm tra cùng cookie/session trong toàn bộ luồng. Kiểm thử với `WebTestClient.mutateWith(csrf())` kiểm chứng phần rule nhưng **không thay thế test trình duyệt thật về cách SPA lấy và gửi token**.

Nguồn: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html

### 5.2. Lambda DSL và việc bỏ API cấu hình cũ

Hướng dẫn chuẩn bị Spring Security 7 nói **Lambda DSL** là cách cấu hình được yêu cầu ở 7; kiểu gọi chuỗi `.and()` cũ không còn là lối viết hợp lệ cho cấu hình tương ứng. Điều này áp dụng việc chuyển mẫu cấu hình; **đừng copy ví dụ Servlet dùng `HttpSecurity`, `SecurityFilterChain`, `authorizeHttpRequests` sang WebFlux**.

Reactive Lambda DSL minh họa:

```java
// Đây là thân một @Bean, cần các import ServerHttpSecurity,
// SecurityWebFilterChain và Customizer ở project thực tế.
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public").permitAll()
                    .pathMatchers("/admin/**").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .httpBasic(org.springframework.security.config.Customizer.withDefaults())
            .build();
}
```

Sau khi rewrite sang DSL mới, hãy so sánh *thứ tự matcher, thứ tự các chain và hành vi mặc định được kích hoạt* với baseline. Một lần “refactor syntax” cũng có thể sửa nhầm phạm vi `permitAll`, CSRF, HTTP Basic hoặc form login.

Nguồn: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html

### 5.3. Security 6.5 → 7: kiểm tra JWT `typ` ở Reactive

Theo migration guide của Spring Security 7, với `NimbusReactiveJwtDecoder`, phần xác minh header `typ` được chuyển theo hướng dùng `JwtTypeValidator`. Hướng dẫn chuẩn bị từ 6.5 chỉ rõ cách đưa validator vào trước khi lên major mới; sau khi lên 7 có thể gỡ cấu hình chuyển tiếp nếu giữ chính sách mặc định.

**Điều phải xác minh:** application đang chấp nhận JWT có type gì, có token `at+jwt` / custom `typ` không, và chính sách mục đích token là gì. JWT có chữ ký đúng **chưa chắc** là token đúng loại, đúng issuer/audience/resource. Tránh tắt validation chỉ để token lỗi tiếp tục dùng được.

Đoạn minh họa **chỉ áp dụng cho chuyển tiếp trên Security 6.5 khi dự án dùng decoder tùy chỉnh** (không phải chương trình hoàn chỉnh):

```java
// Spring Security 6.5: chuẩn bị hành vi kiểm tra typ theo 7.x
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                .validateTypes(false)
                .build();
decoder.setJwtValidator(JwtValidators.createDefaultWithValidators(
        new JwtIssuerValidator(issuer), JwtTypeValidator.jwt()));
return decoder;
```

Theo hướng dẫn hoàn tất ở Security 7, sau khi kiểm chứng mục đích token và validator cần thiết, dạng mặc định có thể là:

```java
// Spring Security 7: minh họa trường hợp chỉ cần default JWT typ
NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                .build();
decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(issuer));
return decoder;
```

Hai đoạn ở trên sử dụng API của hai dòng version khác nhau, không ghép vào cùng file và không dùng nguyên xi nếu ứng dụng đã định nghĩa thêm audience hoặc custom validators. **Nhất thiết giữ tất cả validator nghiệp vụ** khi chuyển; ví dụ code chỉ minh họa phần validator liên quan đến migration. Kiểm tra bằng token hợp lệ, token sai chữ ký, token hết hạn, sai issuer, sai audience, thiếu `typ`, `typ` bất thường và loại token khác mục đích. Không log toàn bộ bearer token vào CI.

Nguồn: https://docs.spring.io/spring-security/reference/migration/reactive.html

### 5.4. Spring Boot 4 / Security 7: đọc thay đổi phụ thuộc và JSON

Migration guide Spring Security 7 yêu cầu phối hợp với bản Spring Boot 4 phù hợp và nêu việc chuyển từ Jackson 2 sang Jackson 3 cho các tích hợp liên quan; đặc biệt những ứng dụng tự lưu/đọc security objects có module serializer riêng cần rà soát. Đây là thay đổi **hệ sinh thái + serialization**, không chỉ sửa một dòng `SecurityWebFilterChain`.

Checklist thêm:

- So sánh effective dependency graph, loại bỏ override xung đột. Kiểm tra Spring Framework, WebFlux, Jackson, Reactor và test dependency đồng bộ.
- Nếu ứng dụng lưu serialized authentication/session/authorized-client, tạo test đọc dữ liệu do baseline ghi bằng candidate; có plan migration/expire session được chấp thuận.
- So sánh cách cấu hình Jackson modules dùng bởi Spring Security. Hướng dẫn 7 chuyển `SecurityJackson2Modules` trên Jackson 2 sang `SecurityJacksonModules` với Jackson 3; chỉ sửa khi dự án **thật sự dùng tính năng này**.
- Kiểm tra integration Spring Session, Redis, message broker và cache. Việc khởi động thành công không chứng minh dữ liệu phiên cũ còn đọc được.
- Nếu có Spring Cloud Gateway hoặc module build ngoài WebFlux, đọc migration guide của từng artifact và test end-to-end qua gateway.

Nguồn: https://docs.spring.io/spring-security/reference/migration/

### 5.5. Phân biệt thay đổi Servlet với Reactive

Mục `PortResolver` hoặc `AntPathRequestMatcher` / `MvcRequestMatcher` trong hướng dẫn **Servlet** không có nghĩa phải thêm bean `PortResolver` hay dùng `PathPatternRequestMatcher` của Servlet cho WebFlux. Trong WebFlux phải xem `ServerWebExchangeMatcher`, `PathPatternParserServerWebExchangeMatcher` và các API `ServerHttpSecurity` đúng version.

Cũng vậy, `SecurityContextHolder` ThreadLocal, `HttpSession`, `FilterChainProxy` servlet và `MockMvc` không phải cơ chế mặc định để lấy principal, quản lý session hay test Reactive; ưu tiên `ReactiveSecurityContextHolder`, `WebSession` và `WebTestClient`.

Nếu migration guide chỉ đề cập Servlet, hãy ghi “**not applicable** sau khi kiểm tra stack/API” thay vì đoán WebFlux đã thay đổi tương tự. Một mục không áp dụng vẫn là kết quả review hợp lệ khi có lý do.

## 6. Quy trình nâng cấp giảm rủi ro

### Giai đoạn A — Chụp baseline **trước khi đổi dependency**

1. Ghi build ID/commit, Java version, parent/BOM, dependency graph và cấu hình active profile.
2. Kiểm kê mọi bean `SecurityWebFilterChain` và thứ tự `@Order` nếu có nhiều chain; xác định matcher nào chọn chain nào.
3. Liệt kê các request quan trọng: login, logout, callback OAuth2, refresh token, API read/write, admin, actuator, tenant/ownership, CSRF preflight, error route.
4. Với mỗi request, xác định **actor, credential, CSRF token, route, method, expected HTTP/status, header và side effect**.
5. Chạy và lưu test baseline trong CI, có positive/negative cases. Đừng thiết lập baseline bằng trạng thái sai đã biết; đánh dấu security debt cần sửa.
6. Ghi lại configuration explicit và mọi chỗ rely on defaults: các lệnh `httpBasic(withDefaults())`, `oauth2ResourceServer`, `csrf`, custom manager/converter/decoder, default user auto-config.
7. Lưu dữ liệu thử nghiệm (JWT giả lập, cookie test, serialized auth nếu có) theo cách không tiết lộ credential thực.

### Giai đoạn B — Đọc thay đổi rồi lập kế hoạch

1. Chọn đường nâng cấp được chính thức hỗ trợ, ví dụ 6.x → 6.5 và chuẩn bị → 7.x theo tài liệu tương ứng; **không nhảy qua bước chuẩn bị cần thiết**.
2. Đọc từng migration guide/version notes và chuyển mỗi mục liên quan thành thay đổi code/config, owner và một hoặc nhiều test.
3. Phân loại: compile failure, deprecated API, changed default, security behavior, dependency/runtime, operational compatibility.
4. Tách PR thay đổi dependency khỏi PR thay đổi policy nghiệp vụ nếu có thể. Việc ghi lại quyết định giúp biết lỗi do nâng framework hay do thay rule.
5. Kiểm tra advisory bảo mật và patch cuối được hỗ trợ của nhánh đích. Một phiên bản sample cũ trong tài liệu học là **fixture**, không phải khuyến nghị pin lâu dài.

### Giai đoạn C — Chạy candidate và so sánh

1. Cập nhật parent/BOM/lockfile; dựng project sạch, dùng dependency graph mới.
2. Sửa các API bị remove và migration-required configs; tuyệt đối không đơn giản hóa policy bằng `permitAll` hoặc `csrf.disable()` chỉ để build xanh.
3. Chạy unit, integration, API contract và tests trên cùng bộ tình huống baseline. So sánh kết quả theo ngữ nghĩa bảo mật, không so raw message/stack trace tùy version.
4. Chạy test với WebTestClient liên kết ApplicationContext để kiểm tra Spring Security filter; chạy thêm HTTP test thật qua server/gateway để phát hiện redirect, cookie, CORS và TLS.
5. Kiểm tra JWT thật theo metadata từ IdP test, JWKS rotate, signature, issuer/audience/typ và expiry; không dùng token production.
6. So sánh latency/error/log của xác thực và authorization, không lộ payload hay token trong log khi bật diagnostics.

### Giai đoạn D — Canary/rollout và rollback

1. Test staging giống production về gateway, TLS, cookies và identity provider.
2. Canary từng phần nếu hạ tầng hỗ trợ; theo dõi 401/403/5xx, OAuth2 callback, tỷ lệ login, latency p95/p99, session restore, refresh token, CSRF/CORS failures.
3. Chuẩn bị rollback khi thay đổi gây false deny, false allow hoặc rò dữ liệu. Nếu có migration dữ liệu/session, rollback phải xét tương thích schema, không chỉ đổi container image.
4. Sau phát hành, khóa phiên bản và lưu migration record; khi nâng patch tiếp tục so release notes vì bản vá có thể sửa behavior liên quan security.

## 7. Ví dụ chạy được: “security contract tests” cho một baseline

Mẫu này cố ý **không tự khai báo `SecurityWebFilterChain`** để quan sát cấu hình mặc định do Spring Boot phối hợp Spring Security tạo ra cho WebFlux. Nó giúp giải thích vì sao khi thêm một bean cấu hình riêng, kiểm thử baseline phải chạy lại. Dùng Spring Boot **3.3.13** làm **fixture học tập đã cố định** để mỗi người có thể chạy giống nhau; đây là dòng đã kết thúc hỗ trợ cộng đồng, **không phải mục tiêu phiên bản production**.

Đối với một candidate thực tế, bạn sẽ **chọn parent/BOM theo migration guide đã đọc**, sửa các API nếu cần, rồi chạy lại **cùng một tập security contract tests**. Không có lệnh nào dưới đây tự động chứng minh tất cả phiên bản mới tương thích.

### 7.1. Tạo `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>dev.example</groupId>
    <artifactId>reactive-upgrade-contract</artifactId>
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

Không thêm version riêng cho `spring-security-test` vì parent Boot quản lý nhất quán với Spring Security runtime.

### 7.2. Tạo `src/main/java/dev/example/upgrade/UpgradeBaselineApplication.java`

```java
package dev.example.upgrade;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class UpgradeBaselineApplication {
    public static void main(String[] args) {
        SpringApplication.run(UpgradeBaselineApplication.class, args);
    }
}

@RestController
class RecordController {
    @GetMapping("/api/records")
    Mono<String> read() {
        return Mono.just("records");
    }

    @PostMapping("/api/records")
    Mono<String> create() {
        // Demo: không sửa dữ liệu. Endpoint POST để kiểm tra CSRF.
        return Mono.just("created");
    }
}
```

Ở đây sự hiện diện của Spring Security trên classpath kích hoạt security auto-configuration của Boot theo version tương ứng. Không có custom `SecurityWebFilterChain`, tất cả endpoint phải được xác thực theo cấu hình mặc định của fixture; form login/Basic có thể dẫn tới phản hồi khác nhau tùy `Accept`. Test sẽ gửi `Accept: application/json` khi muốn xác nhận HTTP 401 thay vì đoán redirect trình duyệt.

### 7.3. Tạo `src/test/java/dev/example/upgrade/SecurityContractTest.java`

```java
package dev.example.upgrade;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

@SpringBootTest
class SecurityContractTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void anonymousRequestMustAuthenticate() {
        client.get().uri("/api/records")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCanRead() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/api/records")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("records");
    }

    @Test
    void postRequiresCsrfEvenWithAuthentication() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .post().uri("/api/records")
                .exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockUser("alice").roles("USER"))
                .mutateWith(csrf())
                .post().uri("/api/records")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void secureResponseHeaderIsPresent() {
        client.mutateWith(mockUser("alice").roles("USER"))
                .get().uri("/api/records")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Content-Type-Options", "nosniff");
    }
}
```

Chạy tại thư mục chứa `pom.xml`:

```bash
mvn test
mvn dependency:tree -Dincludes=org.springframework.security
mvn spring-boot:run
```

Sau khi ứng dụng chạy, terminal khác thử:

```bash
curl -i -H 'Accept: application/json' http://localhost:8080/api/records
```

Ở fixture baseline, mong đợi 401 với request ẩn danh ở trên, còn các kiểm thử `mockUser` đã xác minh GET có quyền và POST phải kèm CSRF. Maven sẽ in nhiều dòng log và thời lượng thay đổi theo máy; không có một output console cố định nên không mô tả giả stdout. Các request dùng `mockUser` chỉ kiểm tra security pipeline **với danh tính giả lập**; muốn kiểm tra xác thực mật khẩu, bearer/JWT hoặc IdP phải có test riêng với credential thực của môi trường test.

### 7.4. Thí nghiệm nâng cấp và cách đọc thất bại

- **Thí nghiệm 1 — phiên bản:** thay parent sang một phiên bản chính thức được chọn, cập nhật code theo migration guide, giữ test. Nếu lỗi compile, so JDK/starter/Jackson/import/API; nếu compile nhưng test đổi kết quả, so implicit defaults và rule custom.
- **Thí nghiệm 2 — custom chain:** thêm một `@Bean SecurityWebFilterChain` chứa rule riêng. Từ lúc đó, kết luận về Boot default “mọi route authenticated” không còn đủ; test `/api/records` phải xác nhận rule do ứng dụng định nghĩa.
- **Thí nghiệm 3 — thay đổi CSRF:** trong **môi trường test riêng**, cấu hình CSRF theo một chính sách explicit hợp lệ, chạy lại `postRequiresCsrfEvenWithAuthentication`. Nếu 403 biến mất khi token thiếu, hãy ghi đây là thay đổi chính sách có chủ đích/chưa được chấp thuận, không tự thay expected status thành 200.
- **Thí nghiệm 4 — test HTTP thực:** khởi động server và kiểm tra `Location`, `Set-Cookie`, `WWW-Authenticate`, header CORS, HSTS ở HTTPS edge. Test bind ApplicationContext không bao phủ được ingress và browser behavior.
- **Thí nghiệm 5 — token migration:** thêm resource server và một bộ JWT test token hợp lệ/sai issuer/audience/typ; so kết quả ở baseline và candidate. Không lấy token thật đưa vào log hoặc commit.

**Cách diễn giải đúng:** một test chuyển từ xanh sang đỏ là tín hiệu để phân tích, không nhất thiết chứng minh thư viện lỗi. Có thể policy cũ không an toàn; khi đó phải đặt expected behavior theo security requirement đã phê duyệt, ghi rõ thay đổi có chủ đích.

## 8. Cách lập bảng “default diff” trước và sau nâng cấp

Lưu bảng cùng commit nâng cấp. Mỗi ô “expected” phải có nguồn: migration note, reference đúng version hoặc kết quả test đã kiểm chứng. Không điền từ ký ức.

| ID | Invariant bảo mật | Baseline | Candidate | Test | Quyết định |
| --- | --- | --- | --- | --- | --- |
| AUTH-01 | Ẩn danh không đọc dữ liệu riêng | 401 hoặc redirect theo Accept | Giữ theo contract client | WebTestClient + HTTP real | PASS/FAIL |
| AUTH-02 | USER không vào admin | 403 | 403 | Role matrix | PASS/FAIL |
| AUTH-03 | ADMIN vẫn thực thi API hợp lệ | 2xx | 2xx | Positive test | PASS/FAIL |
| CSRF-01 | Cookie/session POST thiếu token bị chặn | 403 | 403 | Bad/valid token | PASS/FAIL |
| CSRF-02 | SPA truyền token theo handler mới | Hoạt động | Hoạt động | Browser E2E | PASS/FAIL |
| CORS-01 | Origin lạ không được cấp CORS đọc response | Không có allow-origin hợp lệ | Giữ | Preflight + real browser | PASS/FAIL |
| HDR-01 | Header chống MIME sniffing | Có | Có | Response headers | PASS/FAIL |
| MATCH-01 | Route mới không mặc nhiên public | Deny/authenticated | Giữ | Unknown-route test | PASS/FAIL |
| JWT-01 | Issuer/audience/typ đúng mới được nhận | Theo policy | Giữ hoặc chặt hơn có duyệt | Signed fixture tokens | PASS/FAIL |
| CONTEXT-01 | Principal theo đúng reactive pipeline | Có | Có | Mono/Flux + method security | PASS/FAIL |
| SESS-01 | Session/authorized client có vòng đời đúng | Theo baseline | Theo migration plan | Login/logout/restore | PASS/FAIL |
| AUDIT-01 | Ghi đủ sự kiện denied/sensitive action | Có | Có | Event assertions | PASS/FAIL |

**Thêm case âm:** user bị khóa, password sai, token hết hạn, thiếu scope, token đúng chữ ký nhưng sai audience, khác tenant, route encoded/path edge case, lỗi upstream IdP, session expired. Với mỗi case, xác nhận cả **quyết định bảo mật** và **không có side effect**, không chỉ HTTP status.

Bảng diff phải phân biệt:

- `expected_same`: hành vi bắt buộc giữ.
- `intentional_change`: hành vi thay đổi đã được phê duyệt kèm migration note.
- `unexpected_change`: khác biệt chưa giải thích, cần chặn release nếu ảnh hưởng bảo mật.
- `not_applicable`: tính năng/stack không dùng, có bằng chứng.
- `not_verified`: chưa có test hoặc môi trường cần thiết; không ghi “PASS” thay cho thiếu dữ liệu.

## 9. Phương pháp gỡ lỗi khi thay đổi version làm test fail

### 9.1. Trường hợp POST từ SPA đột nhiên 403

1. Xác nhận `GET` của user tương ứng hoạt động và token đăng nhập có hiệu lực.
2. So `WebSession`, cookie, CSRF token được tạo/cấp, tên header, request handler và cách client đọc token.
3. Đọc migration note Reactive CSRF giữa hai phiên bản (đặc biệt 5.8 → 6.0 khi cần).
4. Chạy biến thể thiếu token, token sai, token hợp lệ. Nếu chỉ token hợp lệ thành công, vấn đề thuộc CSRF/client integration.
5. Nếu vẫn 403 khi token hợp lệ, xem role/matcher/method security/tenant. Tránh vô hiệu hóa CSRF để che lỗi.

### 9.2. JWT trước đây dùng được, sau nâng cấp nhận 401

1. So effective `spring-security-oauth2-jose`, `ReactiveJwtDecoder` bean, issuer/JWKS endpoint và clock.
2. Xác minh JWT signature, `alg`, `kid`, `iss`, `aud`, `exp`, `nbf` và `typ` với công cụ test an toàn; không log token thật.
3. Nếu đi từ 6.5 sang 7.x, đọc riêng mục Reactive `JwtTypeValidator`; giữ đúng validation của loại token được chấp nhận.
4. Nếu token hợp lệ về authentication nhưng API 403, so `JwtAuthenticationConverter`, mapped authorities, role prefix và authorization rule.
5. Cân nhắc lỗi cấu hình mạng/JWKS/IdP, không quy mọi 401 cho thay đổi Security.

### 9.3. Sau update, 401 biến thành 302 tới login page

1. Kiểm tra client `Accept`, cơ chế login được bật và `ServerAuthenticationEntryPoint`.
2. So `SecurityWebFilterChain` có được Boot tạo hay bị bean mới thay thế.
3. Kiểm tra path matcher cho API/HTML và custom exception handling.
4. Xác nhận contract mong đợi: browser HTML có thể chuyển hướng, API JSON nên có response mà client xử lý đúng.
5. Test qua gateway vì rewrite/headers có thể tạo khác biệt với WebTestClient.

### 9.4. Unit test xanh nhưng production mất principal

1. Tìm đoạn dùng `ThreadLocal` hoặc `SecurityContextHolder` không phù hợp với Reactor.
2. Kiểm tra `ReactiveSecurityContextHolder.getContext()` được đọc **bên trong pipeline** và có subscription đúng.
3. Nếu có `publishOn`, `subscribeOn`, WebClient, scheduler hoặc custom filter, kiểm tra context propagation, tránh tự `subscribe()`/`block()` gây đứt pipeline.
4. So Boot/Security/Reactor/Micrometer phiên bản, test đường đi end-to-end với principal thật.
5. Phân biệt thiếu quyền với mất authentication bằng event có cấu trúc, không rò credential.

### 9.5. Service khởi động nhưng có dữ liệu/session cũ không đọc được

1. Xác nhận cấu trúc serialized object, codec, Jackson modules, Spring Session repository và key namespace.
2. So release notes Boot/Security/Jackson; riêng 6→7 xem hướng dẫn Jackson 2→3 khi có security object serialization.
3. Thử đọc dữ liệu mẫu do bản cũ tạo bằng bản mới trên môi trường test.
4. Có chiến lược rotate/expire/migrate session khi cần, đánh giá ảnh hưởng login liên tục.
5. Lưu kế hoạch rollback tương thích; không giả định việc rollback image khôi phục được schema dữ liệu cũ.

## 10. Giới hạn và nguyên tắc bảo mật khi so sánh version

**Không chấp nhận “để tương thích” bằng cách nới policy mù quáng.** Ví dụ: `anyExchange().permitAll()` để qua test, bỏ CSRF cho cookie API, vô hiệu hóa xác minh JWT signature, bỏ kiểm tra issuer/audience, nhận mọi origin CORS hoặc log toàn bộ token đều không phải cách xử lý migration đúng.

**Không dựa vào version label không kiểm chứng.** Một trang docs được render ở bản mới nhất; một module có thể đang resolve artifact khác qua BOM; một bean do app tự tạo có thể override framework default. Cần ba nguồn cùng tồn tại: migration note đúng version, dependency graph thực tế và runtime test.

**Không “fix” bằng cách đổi assertion theo hiện trạng mới.** Điều kiện cho phép/từ chối phải xuất phát từ security requirement. Khi major upgrade có chủ đích thay đổi chính sách, ghi rõ RFC/ADR, owner và thông tin rollout.

**Không phát biểu chính sách đầy đủ chỉ dựa trên unit test mockUser.** Test fake principal thích hợp kiểm tra `AuthorizationManager`, CSRF và filter logic, nhưng không thay thế test real login/IdP/JWKS, browser cookie, network gateway, CORS, TLS và database ownership.

**Không trộn Servlet và Reactive.** Các tài liệu cùng tên có thể dùng `HttpSecurity` ở Servlet và `ServerHttpSecurity` ở Reactive; tên tương tự không đảm bảo kiểu, phương thức và default giống nhau. Kiểm tra đường dẫn `reactive` trong tài liệu lẫn package của API.

## 11. Mẫu biên bản nâng cấp có thể sử dụng lại

```yaml
security_upgrade_review:
  baseline:
    build: "old-build-id"
    boot: "resolved-boot-version"
    security: "resolved-security-version"
    jdk: "resolved-java-version"
    web_stack: "REACTIVE_WEBFLUX"
  candidate:
    build: "candidate-build-id"
    boot: "approved-target-version"
    security: "resolved-target-version"
    jdk: "approved-jdk"
  documentation:
    - "spring-boot-migration-guide-pinned-url"
    - "spring-security-preparation-guide-pinned-url"
    - "spring-security-reactive-migration-guide-pinned-url"
    - "relevant-release-notes-or-security-advisories"
  impacted_features:
    - "authentication"
    - "authorization"
    - "csrf"
    - "oauth2-jwt"
    - "session-and-headers"
  behavioral_tests:
    baseline_run: "ci-test-report-id"
    candidate_run: "ci-test-report-id"
    differences:
      expected_same: []
      approved_changes: []
      unresolved: []
  operations:
    canary_signal: ["login-success", "401-403-ratio", "p95"]
    rollback_strategy: "documented-for-this-release"
  approval:
    security_owner: "reviewer-id"
    result: "pending"
```

Đây là **mẫu cấu trúc**, không phải biên bản đã được xác minh cho một sản phẩm. Lưu evidence link, policy version, test run, chữ ký/reviewer và expiry của ngoại lệ khi thực tế sử dụng; không đưa password hoặc JWT vào YAML.

## 12. Checklist cuối cùng trước khi coi migration hoàn tất

- [ ] Đã ghi version thực tế của Boot, Security, Framework, Reactor, Java, Jackson ở baseline và candidate.
- [ ] Đã đọc release notes, preparation guide, migration guide và phần Reactive cho **đúng đường nâng cấp**.
- [ ] Mọi mục thay đổi liên quan đã có owner, điều kiện áp dụng, sửa đổi cần thiết và test minh chứng.
- [ ] Không dùng cấu hình Servlet thay cho WebFlux và không suy một default của Boot áp dụng khi có custom chain.
- [ ] Authentication (Basic/form/OIDC/bearer), authorization (HTTP và method), CSRF, CORS, headers, session đều có positive và negative tests phù hợp.
- [ ] JWT có kiểm tra signature, `iss`, `aud`, `exp`, `typ` theo requirement; không bỏ custom validators khi migration.
- [ ] Test bên trong `ApplicationContext` đã qua, đồng thời smoke test qua HTTP/TLS/gateway/IdP ở môi trường giống production đã qua.
- [ ] Không có khác biệt bảo mật chưa giải thích; không rò token, PII hoặc chi tiết exception.
- [ ] Kiểm thử serializations/session legacy (nếu tồn tại) và rollback đã được đánh giá.
- [ ] Bản candidate có dependency graph, test report, migration record và người phê duyệt tương ứng.

## 13. Tài liệu tham khảo

1. Spring Security migration overview: https://docs.spring.io/spring-security/reference/migration/
2. Spring Security Reactive migration: https://docs.spring.io/spring-security/reference/migration/reactive.html
3. Spring Security 6.5 preparation for 7.0: https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html
4. Spring Security 6.5 configuration preparation: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
5. Spring Security Reactive CSRF and version-related handler: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
6. Spring Security WebFlux request authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html
7. Spring Security Reactive tests: https://docs.spring.io/spring-security/reference/reactive/test/index.html
8. Spring Boot Maven dependency management: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
9. Spring Boot reference / migration: https://docs.spring.io/spring-boot/reference/
10. Spring Security 6.5 preparation for JWT type validation: https://docs.spring.io/spring-security/reference/6.5/migration-7/oauth2.html

**Kết luận vận dụng:** giá trị chính của migration guide là giúp tạo **giả thuyết cụ thể về thay đổi**; bằng chứng cuối cùng phải là dependency thực tế, cấu hình đang chạy và kiểm thử cho quyết định bảo mật trên ứng dụng Reactive. Khi cả ba khớp với security contract đã duyệt, việc nâng cấp mới có cơ sở để phát hành.
