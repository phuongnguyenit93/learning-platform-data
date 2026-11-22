# Đọc danh tính hiện tại bằng ReactiveSecurityContextHolder trong Spring Security Reactive

## 1. Bài toán và mục tiêu

Trong Spring WebFlux, một request được xác thực sẽ có **Authentication** mô tả danh tính và quyền hạn của người gọi. Khi xử lý nằm sâu trong service thay vì trực tiếp ở controller, lập trình viên thường cần đọc danh tính hiện tại từ **ReactiveSecurityContextHolder**.

Sau bài học, bạn cần có khả năng:

1. Giải thích vai trò của SecurityContext, Authentication, principal và Reactor Context.
2. Đọc username, authorities hoặc principal từ ReactiveSecurityContextHolder.getContext() trong một Mono/Flux.
3. Xử lý an toàn khi context không tồn tại, Authentication null hoặc người gọi anonymous.
4. Hiểu việc Reactor Context đi theo subscription thay vì ThreadLocal và cách contextWrite ảnh hưởng pipeline.
5. Biết khi nào dùng withAuthentication, withSecurityContext, clearContext và giới hạn của các API này.
6. Viết ứng dụng Java 17+ chạy được bằng Spring Boot WebFlux, thử curl và kiểm tra với StepVerifier.
7. Phân biệt lấy danh tính với quyết định phân quyền trên tài nguyên cụ thể.

**Ý chính:** đọc danh tính từ ngữ cảnh đã được thiết lập bằng xác thực đáng tin cậy. Bản thân getContext() **không đăng nhập**, **không xác minh password/token** và **không tự cấp quyền**.

## 2. Tầng dữ liệu: Reactor Context → SecurityContext → Authentication

Các đối tượng cần phân biệt:

| Thành phần | Công dụng | Điều cần chú ý |
| --- | --- | --- |
| **Reactor Context** | Dữ liệu gắn với một subscriber/chuỗi reactive | Không phải Map global và không gắn cố định vào thread |
| **SecurityContext** | Chứa Authentication, có thể chưa có Authentication | SecurityContext.getAuthentication() có thể null |
| **Authentication** | Thông tin principal, credentials, authorities và trạng thái xác thực | Loại cụ thể phụ thuộc cơ chế xác thực |
| **Principal** | Đại diện danh tính; có thể là UserDetails, Jwt, OAuth2 principal hoặc kiểu ứng dụng | Không cast mọi principal về UserDetails |
| **Authentication.getName()** | Tên danh tính theo hợp đồng Authentication | Không mặc nhiên là ID nghiệp vụ bất biến |
| **GrantedAuthority** | Quyền, role hoặc scope sau khi được ánh xạ | ROLE_USER, SCOPE_orders.read có semantics tùy cấu hình |
| **ReactiveSecurityContextHolder** | Cung cấp API đọc/ghi SecurityContext vào Reactor Context | Trả Mono<SecurityContext> thay vì SecurityContext đồng bộ |

Sơ đồ khái niệm:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |-- AuthenticationWebFilter / HTTP Basic / JWT / cơ chế khác
    |-- Bộ xác thực kiểm chứng credential, tạo Authentication đáng tin
    |-- SecurityContext chứa Authentication
    v
Reactor Context của subscription hiện tại
    |
    +--> Controller (Mono/Flux)
            |
            +--> Service (Mono/Flux)
                    |
                    +--> ReactiveSecurityContextHolder.getContext()
                            |
                            v
                      Mono<SecurityContext>
                            |
                            v
                      Authentication
                            |
                      name / principal / authorities
~~~

Spring Security Reactive có thể dùng **ReactorContextWebFilter** và ServerSecurityContextRepository để nạp context; cơ chế xác thực thành công cũng có thể đặt context cho phần xử lý tiếp theo. Với session, HTTP Basic và bearer token, cách lưu/khôi phục giữa các request khác nhau. Không suy luận rằng luôn có HTTP session hoặc context tồn tại tại mọi vị trí.

## 3. Vì sao SecurityContextHolder của servlet không đủ?

Ở servlet truyền thống, SecurityContextHolder thường lưu context trong ThreadLocal của thread đang xử lý request. Ở WebFlux:

- Nhiều request có thể đi qua cùng event-loop thread.
- Một request có thể tạm dừng trong khi chờ I/O.
- Sau publishOn/subscribeOn, pipeline có thể tiếp tục trên thread khác.
- Một publisher có thể được subscribe nhiều lần với các context khác nhau.

Ví dụ:

~~~text
Request Alice:  thread-A ---> I/O ---> thread-C ---> response
Request Bob:    thread-A ---> I/O ---> thread-B ---> response

Thread-A không phải "thread của Alice" mãi mãi.
Danh tính được mang bởi Reactor Context của từng subscription.
~~~

Dùng API reactive:

~~~java
Mono<Authentication> current =
        ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

Dùng SecurityContextHolder.getContext() kiểu ThreadLocal trong WebFlux có thể nhận dữ liệu trống, sai thời điểm hoặc phụ thuộc cầu nối ngữ cảnh chưa được kiểm chứng. Hãy giữ các thao tác trong Mono/Flux hoặc truyền ID người dùng đã được xác minh qua tham số khi cần.

## 4. Hợp đồng API chính

Những phương thức quan trọng:

~~~java
// Lấy SecurityContext từ Reactor Context hiện tại.
static Mono<SecurityContext> getContext();

// Đặt một Authentication vào Reactor Context mới.
static reactor.util.context.Context withAuthentication(
        Authentication authentication);

// Đặt Publisher của SecurityContext vào Context mới.
static reactor.util.context.Context withSecurityContext(
        Mono<? extends SecurityContext> securityContext);

// Trả về hàm loại bỏ mục SecurityContext khỏi Reactor Context.
static java.util.function.Function<
        reactor.util.context.Context,
        reactor.util.context.Context> clearContext();
~~~

**Không thể** gán Mono vào biến SecurityContext thông thường:

~~~java
// Sai kiểu, không biên dịch.
SecurityContext ctx = ReactiveSecurityContextHolder.getContext();
~~~

Thay vào đó, compose bằng các operator:

~~~java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName);
~~~

Một lời gọi getContext() tạo **Mono mô tả việc đọc context khi subscribe**, không lập tức truy xuất danh tính từ một biến toàn cục. Đừng gọi block() trong WebFlux handler để buộc nó thành String.

## 5. Cách đọc danh tính an toàn

### 5.1. Lấy username

~~~java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName);
}
~~~

Nếu context chứa Authentication của alice, Mono phát "alice". Nếu không có context hoặc Authentication là null, Mono thường hoàn thành rỗng. Dùng Mono.justOrEmpty thay vì map trực tiếp từ một giá trị có thể null để tránh lỗi khi ánh xạ null.

### 5.2. Bắt buộc có danh tính đã được xác thực

~~~java
public Mono<String> requiredUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .filter(authentication ->
                    authentication.isAuthenticated()
                    && !(authentication instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Authentication required")));
}
~~~

Import dành cho đoạn phương thức minh họa:

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;
~~~

**Lưu ý:** AnonymousAuthenticationToken có thể có isAuthenticated() là true. Vì vậy chỉ dùng isAuthenticated() không bảo đảm đây là danh tính người dùng thực sự đã login. Tại tầng HTTP, ưu tiên cấu hình Spring Security với .authenticated(), hasRole/hasAuthority và để framework xử lý anonymous. Khi phải kiểm tra trong Java, dùng AuthenticationTrustResolver phù hợp hoặc kiểm tra anonymous rõ ràng.

AccessDeniedException trong service có thể được chuyển thành phản hồi theo cấu hình xử lý ngoại lệ; không mặc định tất cả lỗi service sẽ trả đúng 401. 401 thường là thiếu/sai credential ở entry point, 403 thường là đã xác thực nhưng không có quyền. Việc xử lý chính xác phụ thuộc filter chain/handler.

### 5.3. Lấy authorities

~~~java
public Mono<List<String>> currentAuthorities() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(authentication -> authentication.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
}
~~~

Import bổ sung:

~~~java
import java.util.List;
import org.springframework.security.core.GrantedAuthority;
~~~

Với .roles("USER"), authority mặc định là ROLE_USER. Với Resource Server và mapping scope mặc định, scope có thể thành authority dạng SCOPE_orders.read. Đừng so sánh chuỗi quyền mà không hiểu cách chuyển đổi của hệ thống.

### 5.4. Lấy principal nhưng không để lộ dữ liệu nhạy cảm

~~~java
public Mono<Object> currentPrincipal() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
            .map(Authentication::getPrincipal);
}
~~~

Principal có thể là UserDetails, Jwt, một OAuth2 principal hoặc kiểu tùy biến. Không ép kiểu nếu chưa kiểm tra, không trả thẳng toàn bộ object ra JSON vì có thể chứa password hash, claim nội bộ, token hoặc thông tin không dành cho client. Map nó sang DTO chỉ có những trường được phép.

### 5.5. Lời chào công khai khác quyết định bảo mật

Nếu endpoint hoàn toàn công khai, có thể fallback tên hiển thị:

~~~java
Mono<String> greeting = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .filter(auth ->
                !(auth instanceof AnonymousAuthenticationToken))
        .map(Authentication::getName)
        .defaultIfEmpty("guest")
        .map(name -> "hello " + name);
~~~

Fallback "guest" phù hợp cho **hiển thị**; không được dùng làm bằng chứng có quyền đọc dữ liệu riêng tư. Với endpoint được bảo vệ, thiếu danh tính phải bị từ chối an toàn.

## 6. Reactor Context được truyền như thế nào?

Reactor Context gắn với Subscriber và được lan truyền theo chuỗi subscription. Operator **contextWrite** tạo/biến đổi Context nhìn thấy bởi các operator **phía upstream** của nó.

Ví dụ dùng Authentication có nguồn tin cậy:

~~~java
Authentication trusted = /* đã được manager xác minh */;

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(trusted));
~~~

Đây là đoạn minh họa API; biến trusted phải được tạo từ hệ thống xác thực đáng tin hoặc fixture test, không được tự lấy từ header X-User mà client tùy ý gửi.

**Vì sao contextWrite nằm ở cuối?** Subscription truyền yêu cầu ngược từ downstream lên upstream. contextWrite nằm dưới nguồn đọc context sẽ đưa giá trị vào ngữ cảnh của các operator phía trên. Nếu đặt contextWrite trong inner publisher, giá trị có thể chỉ áp dụng với inner publisher đó; không tự thay đổi toàn bộ chuỗi.

Các operator Reactor bình thường như map, flatMap, publishOn, subscribeOn duy trì cơ chế truy cập Reactor Context khi publisher được compose đúng. Nhưng một raw Executor, CompletableFuture, callback hoặc thread tự tạo **không tự mang mọi Reactor Context**. Khi sang một hệ không sử dụng Reactor, truyền các trường đã xác minh cần thiết theo hợp đồng rõ ràng.

## 7. Vì sao không dùng block() hoặc subscribe() thủ công?

**block():** có thể gây nghẽn event-loop và làm mất ngữ cảnh mong đợi khi tạo subscription riêng.

~~~java
// Không nên làm trong WebFlux service/handler:
String name = ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .block();
~~~

**subscribe() thủ công:** tạo subscription riêng ngoài vòng đời request, lỗi và context khó kiểm soát.

~~~java
// Không nên dùng để lấy danh tính trong request:
ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName())
        .subscribe(name -> audit(name));

return Mono.just("ok");
~~~

Nếu audit được yêu cầu trong luồng xử lý:

~~~java
// Minh họa tích hợp: auditService.persist(actorId) trả Mono<Void>.
return requiredUsername()
        .flatMap(actor -> auditService.persist(actor)
                .thenReturn("ok"));
~~~

Nếu audit bắt buộc phải bền vững dù client hủy kết nối, cần thiết kế transaction/outbox hoặc hàng đợi bền vững độc lập. Không dựa hoàn toàn vào doFinally hoặc một fire-and-forget subscribe() để xác nhận đã lưu sự kiện bắt buộc.

## 8. Demo Java 17+: đọc danh tính từ Spring Security WebFlux

Bản demo cung cấp:

- HTTP Basic xác thực hai người dùng trong bộ nhớ.
- /api/me đọc danh tính từ **IdentityService** bằng ReactiveSecurityContextHolder.
- /api/authorities xem GrantedAuthority.
- /api/principal sử dụng Mono<Principal> ở controller để đối chiếu.
- /api/user/greeting được bảo vệ bằng reactive method security.
- /api/admin/report yêu cầu ROLE_ADMIN ở HTTP filter.

Cấu trúc file:

~~~text
reactive-current-identity/
├── settings.gradle
├── build.gradle
├── src/main/java/example/identity/IdentityApplication.java
├── src/main/java/example/identity/IdentityService.java
├── src/main/java/example/identity/IdentityController.java
└── src/test/java/example/identity/IdentityServiceTest.java
~~~

### 8.1. settings.gradle

~~~groovy
rootProject.name = 'reactive-current-identity'
~~~

### 8.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 8.3. IdentityApplication.java

~~~java
package example.identity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/admin/**").hasRole("ADMIN")
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }
}
~~~

SecurityWebFilterChain cho phép /public/ping, yêu cầu xác thực trên /api/**, và chỉ ROLE_ADMIN có thể vào /api/admin/**. @EnableReactiveMethodSecurity kích hoạt hỗ trợ @PreAuthorize cho Spring bean trả về Publisher.

Mật khẩu trong demo chỉ dùng học tập. Ở production, dùng nguồn danh tính và kho bí mật thích hợp, HTTPS, quản lý credential và rate limit.

### 8.4. IdentityService.java

~~~java
package example.identity;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<String> requiredUsername() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
                .filter(authentication ->
                        authentication.isAuthenticated()
                        && !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName)
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException("Authentication required")));
    }

    @PreAuthorize("hasRole('USER')")
    public Mono<String> userGreeting() {
        return requiredUsername()
                .map(name -> "service hello " + name);
    }
}
~~~

Điểm cốt lõi: service nhận đúng danh tính **tại thời điểm subscribe**, không trữ tên trong singleton. @PreAuthorize được áp dụng khi controller gọi qua Spring bean/proxy. Gọi nội bộ bằng this.userGreeting() có thể bỏ qua proxy và không kích hoạt method security.

### 8.5. IdentityController.java

~~~java
package example.identity;

import java.security.Principal;
import java.util.stream.Collectors;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    private final IdentityService identityService;

    public IdentityController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return identityService.requiredUsername()
                .map(name -> "hello " + name);
    }

    @GetMapping("/api/authorities")
    public Mono<String> authorities() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
                .map(Authentication::getAuthorities)
                .map(auths -> auths.stream()
                        .map(GrantedAuthority::getAuthority)
                        .sorted()
                        .collect(Collectors.joining(",")));
    }

    @GetMapping("/api/principal")
    public Mono<String> fromArgument(Mono<Principal> principal) {
        return principal.map(p -> "principal " + p.getName());
    }

    @GetMapping("/api/user/greeting")
    public Mono<String> greeting() {
        return identityService.userGreeting();
    }

    @GetMapping("/api/admin/report")
    public Mono<String> adminReport() {
        return identityService.requiredUsername()
                .map(name -> "admin report for " + name);
    }
}
~~~

Hai cách lấy danh tính: service tự dùng ReactiveSecurityContextHolder, còn controller có thể nhận Mono<Principal> qua argument resolver của WebFlux. Với một endpoint chỉ cần principal, cách nhận tham số có thể đơn giản hơn; với service dùng lại ở nhiều nơi, đọc reactive context giúp không phải truyền Principal qua từng phương thức.

### 8.6. Chạy demo

Cần JDK 17+ và Gradle 8.x tương thích với phiên bản Spring Boot 3.3.5:

~~~bash
gradle bootRun
~~~

Trong terminal khác, chạy các lệnh kiểu Bash:

~~~bash
curl -s http://localhost:8080/public/ping
# pong

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
# 401

curl -s -u alice:alice-pass http://localhost:8080/api/me
# hello alice

curl -s -u admin:admin-pass http://localhost:8080/api/me
# hello admin

curl -s -u alice:alice-pass http://localhost:8080/api/authorities
# ROLE_USER

curl -s -u admin:admin-pass http://localhost:8080/api/authorities
# ROLE_ADMIN

curl -s -u alice:alice-pass http://localhost:8080/api/principal
# principal alice

curl -s -u alice:alice-pass http://localhost:8080/api/user/greeting
# service hello alice

curl -s -o /dev/null -w '%{http_code}\n' \
  -u admin:admin-pass http://localhost:8080/api/user/greeting
# 403

curl -s -o /dev/null -w '%{http_code}\n' \
  -u alice:alice-pass http://localhost:8080/api/admin/report
# 403

curl -s -u admin:admin-pass http://localhost:8080/api/admin/report
# admin report for admin
~~~

Các đoạn sau dấu # là **kết quả dự kiến của demo**, không phải câu lệnh. Trên PowerShell dùng curl.exe và nhập trên một dòng; ký tự xuống dòng kiểu Bash không áp dụng trực tiếp.

| Request | Context/authority | Quy tắc | Kết quả |
| --- | --- | --- | --- |
| GET /public/ping | Không bắt buộc danh tính | permitAll | 200 pong |
| GET /api/me thiếu credential | Không có Authentication tin cậy | authenticated | 401 |
| GET /api/me bằng alice | alice, ROLE_USER | authenticated | 200 hello alice |
| GET /api/authorities bằng admin | admin, ROLE_ADMIN | authenticated | 200 ROLE_ADMIN |
| GET /api/user/greeting bằng alice | alice, ROLE_USER | @PreAuthorize USER | 200 service hello alice |
| GET /api/user/greeting bằng admin | admin, ROLE_ADMIN | @PreAuthorize USER | 403 |
| GET /api/admin/report bằng alice | alice, ROLE_USER | hasRole ADMIN | 403 |
| GET /api/admin/report bằng admin | admin, ROLE_ADMIN | hasRole ADMIN | 200 admin report for admin |

HTTP Basic kiểm tra credential cho mỗi request phù hợp; demo không triển khai login session. Không dựa vào mã trả lời của một request public để suy ra rằng mọi WebFilter đều bị bỏ qua.

## 9. Kiểm thử trực tiếp bằng StepVerifier

Với unit test không qua HTTP, bạn có thể chủ động cung cấp Authentication tin cậy cho Reactor Context bằng **withAuthentication**. Đây là kỹ thuật tạo fixture, không phải đường xác thực đầu vào production.

### 9.1. IdentityServiceTest.java

~~~java
package example.identity;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class IdentityServiceTest {

    private final IdentityService service = new IdentityService();

    private static Authentication verified(String username) {
        return UsernamePasswordAuthenticationToken.authenticated(
                username,
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void eachSubscriptionHasItsOwnIdentity() {
        Mono<String> username = service.requiredUsername();

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        verified("alice"))))
                .expectNext("alice")
                .verifyComplete();

        StepVerifier.create(username.contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        verified("bob"))))
                .expectNext("bob")
                .verifyComplete();
    }

    @Test
    void missingContextDoesNotGrantAccess() {
        StepVerifier.create(service.requiredUsername())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void clearContextMakesIdentityUnavailableToUpstream() {
        Mono<String> username = service.requiredUsername()
                .contextWrite(ReactiveSecurityContextHolder.clearContext())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                verified("alice")));

        StepVerifier.create(username)
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả dự kiến:** các test PASS và Gradle kết thúc với BUILD SUCCESSFUL, miễn JDK/dependencies được cài đúng.

Unit test này không khởi động Spring proxy nên không phải là bài test cho @PreAuthorize; nó trực tiếp chứng minh IdentityService đọc Reactor Context đúng. Kiểm thử method security đầy đủ cần Spring context/WebTestClient.

### 9.2. Tại sao cùng Mono đọc được hai user?

Một publisher có thể được subscribe trong hai Context khác nhau:

~~~text
Mono<String> username
   |
   +-- Subscription 1: Context(Authentication=alice) -> alice
   |
   +-- Subscription 2: Context(Authentication=bob)   -> bob
~~~

Không có biến toàn cục username bị ghi đè. Ngữ cảnh áp dụng theo từng subscriber. Đây là lý do không nên cache username của request ở một trường singleton.

## 10. withAuthentication, withSecurityContext và clearContext

**withAuthentication(authentication)** tạo Reactor Context chứa Mono<SecurityContext> với Authentication được cung cấp. Phù hợp cho unit test hoặc mã framework tin cậy, không phù hợp để biến username do client gửi thành Authentication hợp lệ.

**withSecurityContext(Mono<? extends SecurityContext>)** hữu ích khi đã có SecurityContext hoặc Publisher của nó:

~~~java
Authentication trusted = /* lấy từ manager đã xác thực */;
SecurityContext context = new SecurityContextImpl(trusted);

Mono<String> username = ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .contextWrite(
                ReactiveSecurityContextHolder.withSecurityContext(
                        Mono.just(context)));
~~~

Import bổ sung:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
~~~

Đoạn trên là **ví dụ tích hợp**, cần thay trusted bằng đối tượng đã được xác minh. Không biến username, role hoặc authenticated=true do một HTTP header tự khai thành context được tin cậy.

**clearContext()** trả Function<Context,Context> để xóa mục SecurityContext trên nhánh pipeline. Ví dụ test:

~~~java
Mono<String> name = service.requiredUsername()
        .contextWrite(ReactiveSecurityContextHolder.clearContext())
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        verified("alice")));
~~~

Thứ tự rất quan trọng: contextWrite phía ngoài thêm Authentication khi subscribe; contextWrite phía trong gần nguồn xóa context trước khi service đọc. Đây chỉ là thao tác thay đổi **Reactor Context trong pipeline**, không phải logout toàn cục. Nó không thu hồi JWT, xóa server session, xóa cookie, hủy refresh token hay chặn request khác. Logout phải thực hiện theo cơ chế session/token của ứng dụng.

## 11. Đọc context trong tác vụ bất đồng bộ

Trong pipeline Reactor được compose đúng, context có thể đi theo chuỗi qua các operator và scheduler. Tuy nhiên, khi tích hợp raw Executor, CompletableFuture hoặc tác vụ nền độc lập, không được giả định Reactor Context tự xuất hiện ở mọi thread.

Một cách thiết kế an toàn:

~~~java
// Minh họa tích hợp: jobPublisher được ứng dụng triển khai.
return identityService.requiredUsername()
        .flatMap(actorId ->
                jobPublisher.enqueue(actorId, documentId));
~~~

actorId ở đây đã được lấy từ Authentication; nếu cần tenantId hoặc subject ổn định, trích từ principal/claims đã kiểm chứng. Job cần cơ chế xác thực, kiểm soát quyền và kiểm toán riêng; không tự dùng context rỗng để suy ra system/admin.

Các dấu hiệu mất context:

- Mã đọc danh tính được gọi ngoài pipeline hoặc từ static initializer.
- Service tự subscribe thay vì trả Mono/Flux.
- Dùng block() rồi hy vọng context vẫn truyền qua thread.
- Không vào đúng SecurityWebFilterChain hoặc filter xác thực chưa thiết lập SecurityContext.
- Đặt contextWrite không đúng vị trí.
- Tự tạo publisher/async callback không được compose vào chuỗi request.
- Dùng SecurityContextHolder ThreadLocal như ở servlet.

Khi gặp ReactiveSecurityContextHolder.getContext() rỗng bất ngờ, nên kiểm tra lần lượt những ranh giới trên trước khi sửa code. Không tạo Authentication mặc định có quyền admin để che lỗi.

## 12. Lấy danh tính chưa đủ để kiểm tra quyền

Xét GET /api/orders/42. API đã biết request thuộc alice, nhưng đơn hàng 42 có thể thuộc bob. Việc đọc alice từ ReactiveSecurityContextHolder chỉ trả lời **ai đang gọi**, chưa trả lời **có được xem đơn 42 hay không**.

Ví dụ minh họa service:

~~~java
// Minh họa tích hợp: OrderDto và orderRepository do ứng dụng định nghĩa.
public Mono<OrderDto> readOrder(String orderId) {
    return identityService.requiredUsername()
            .flatMap(username ->
                    orderRepository.findByIdAndOwnerUsername(
                            orderId, username));
}
~~~

Repository phải lọc theo **cả orderId lẫn owner/tenant được xác minh**. Nếu quyền đọc phức tạp hơn, thêm policy check ở tầng service/data phù hợp. Không tin ownerId hoặc tenantId chỉ do client tự khai.

Với JWT, claims như sub, tenant, groups chỉ đáng tin sau khi xác minh signature, issuer, audience, expiry và các ràng buộc cần thiết. Với user ID lâu dài, ưu tiên subject/id ổn định thay vì mặc định username luôn bất biến.

## 13. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng SecurityContextHolder trong WebFlux như ThreadLocal servlet | Danh tính mất hoặc sai khi đổi thread | ReactiveSecurityContextHolder |
| Gọi getContext().block() trong handler | Nghẽn event-loop, tạo subscription không phù hợp | Trả Mono/Flux |
| Tự subscribe() để đọc principal | Mất vòng đời và context, lỗi khó quan sát | flatMap/then trong pipeline trả về |
| Cast mọi principal sang UserDetails | JWT/OIDC principal có kiểu khác | Kiểm tra type hoặc dùng getName() |
| Chỉ kiểm tra isAuthenticated() | AnonymousAuthenticationToken có thể true | Sử dụng authenticated/trust resolver |
| Dùng defaultIfEmpty("admin") ở API riêng tư | Thiếu context được coi là có quyền | Fail closed, báo lỗi |
| Đưa Authentication từ X-User client vào withAuthentication | Giả mạo danh tính và quyền | Chỉ dùng kết quả manager đã xác minh |
| Gửi nguyên Authentication/principal lên client | Lộ credentials/claim nội bộ | Chỉ map field được phép |
| Gọi map trực tiếp trên Authentication có thể null | Có thể phát lỗi null | Mono.justOrEmpty |
| Cache tên user của request trong singleton | Dữ liệu cross-request bị lẫn | Đọc tại subscription |
| Coi clearContext() là logout mọi request | Không xóa token/session ngoài pipeline | Logout và revocation đúng cơ chế |
| Lấy username làm đủ quyền đọc record | IDOR/BOLA, lộ dữ liệu user khác | Kiểm tra owner/tenant |
| Đặt contextWrite sai vị trí | Operator cần đọc không thấy context | Hiểu hướng subscription upstream |
| Log toàn bộ SecurityContext hoặc JWT | Lộ dữ liệu nhạy cảm | Chỉ log actor ID/correlation ID đã lọc |

## 14. Kiểm thử cần có

**Unit test bằng StepVerifier:**

- Alice, Bob trong hai subscription tách biệt.
- Thiếu Context → service cần danh tính trả lỗi.
- AnonymousAuthenticationToken → không bị coi là user đã đăng nhập.
- Context được clear ở nhánh upstream → không truy cập được.
- Không fallback quyền cao khi lỗi.

**Integration test bằng WebTestClient:**

- /public/ping không credential vẫn thành công.
- /api/me không credential bị từ chối.
- /api/me bằng hai user trả hai danh tính đúng, kể cả khi chạy song song.
- ROLE_USER không gọi được admin endpoint.
- @PreAuthorize chỉ cho ROLE_USER vào /api/user/greeting.
- Nếu dùng JWT/session/multiple chains, test ngữ cảnh theo đúng cấu hình thực tế.

**Kiểm thử async:** một pipeline có publishOn/subscribeOn vẫn giữ context khi compose đúng; raw background task nhận actor ID qua hợp đồng tường minh. Test việc mất context nên dùng StepVerifier và synchronization đáng tin, tránh Thread.sleep rồi suy đoán.

**Quan sát vận hành:** khi cần lưu audit ai đã thao tác, chỉ lưu actor ID/subject, hành động, tài nguyên, kết quả quyền và correlation ID đã kiểm soát; không lưu password, raw bearer token hoặc toàn bộ principal.

## 15. Câu hỏi tự luyện

1. ReactiveSecurityContextHolder.getContext() trả về SecurityContext hay Mono<SecurityContext>?
2. Vì sao ThreadLocal không đủ an toàn để đọc danh tính trong WebFlux?
3. Khác biệt giữa SecurityContext, Authentication và principal?
4. Nếu getContext() rỗng, có được tự gán role USER để tiếp tục truy cập không?
5. Vì sao isAuthenticated() đơn lẻ chưa đủ để loại anonymous?
6. Vì sao contextWrite thường đặt ở dưới publisher cần đọc context?
7. Chạy hai subscription của cùng Mono trong Context Alice và Bob thì danh tính phải ra sao?
8. clearContext() có xóa JWT hoặc session server hay không?
9. Vì sao @PreAuthorize cần gọi qua Spring bean/proxy?
10. Vì sao đọc username của alice vẫn chưa cho phép xem đơn hàng của bob?
11. Khi service gọi raw Executor, nên xử lý actor identity thế nào?
12. Khi muốn chỉ dùng username ở controller, có thể nhận Mono<Principal> thay vì tự truy xuất SecurityContext không?

**Đáp án:** (1) Mono<SecurityContext>; (2) Reactor thay thread và chia sẻ thread, Context theo subscriber; (3) vùng lưu, thông tin xác thực và đối tượng danh tính; (4) không, fail closed; (5) anonymous token có thể authenticated=true; (6) contextWrite biến đổi context thấy bởi upstream; (7) Alice và Bob tương ứng, không lẫn; (8) không, chỉ xóa key trong Reactor Context; (9) annotation được xử lý qua proxy; (10) cần quyền owner/tenant; (11) truyền ID đã được xác minh và bảo vệ job bằng chính sách riêng; (12) có, nếu WebFlux resolver hỗ trợ tham số đó.

## 16. Nguồn tra cứu

- Spring Security Javadoc — ReactiveSecurityContextHolder: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Project Reactor — Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html

**Kết luận:** Khi cần biết ai đang gọi một service trong Spring Security Reactive, đọc **ReactiveSecurityContextHolder.getContext() → Authentication → principal/name/authorities** bằng Mono/Flux. Bảo đảm context thuộc subscription hiện tại, chỉ tin Authentication do cơ chế bảo mật xác minh, xử lý trường hợp thiếu context một cách an toàn và luôn kết hợp kiểm tra authorization theo tài nguyên thực tế.