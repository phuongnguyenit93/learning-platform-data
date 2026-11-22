# Proxy, self-invocation và điều kiện để interceptor được áp dụng

> **Module:** Spring Security – authorization. **Nhóm:** Method security Reactive. Bài này giải thích cách `@PreAuthorize`/`@PostAuthorize` được gắn qua Spring AOP proxy, tại sao `this.method()` không đi qua advice, yêu cầu đối với Spring-managed bean và reactive return type, sự khác biệt JDK proxy/CGLIB, các giới hạn `private`/`final`, và cách kiểm thử bằng Java 17+, Spring Boot 3.x, Spring Security 6.x, Reactor `StepVerifier` và `WebTestClient`.

## 1. Vấn đề: annotation không đồng nghĩa mọi lời gọi đã được chặn

~~~java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOC_APPROVE')")
    public Mono<String> approve() {
        return Mono.just("approved");
    }

    public Mono<String> approveInternally() {
        return this.approve();
    }
}
~~~

Lời gọi từ bean khác tới `documentService.approve()` đi qua Spring bean proxy và có thể kích hoạt method-security interceptor. Nhưng lời gọi `this.approve()` bên trong chính target là **self-invocation**; ở cơ chế Spring AOP mặc định, lời gọi nội bộ không đi qua proxy nên annotation trên `approve()` không được xét **cho lời gọi đó**.

~~~text
External bean -> Spring proxy -> method-security advice -> target.approve()

External bean -> proxy -> target.approveInternally()
                               |
                               +-> this.approve() (không qua proxy)
~~~

Đây là lỗi về **ranh giới áp dụng interceptor**, không phải lỗi `Mono`, không phải Spring Security tự hết hiệu lực và cũng không thể sửa bằng cách đổi từ JDK proxy sang CGLIB.

**Quy tắc:** những điểm vào nghiệp vụ cần được bảo vệ phải có security policy chạy thực sự, được xác nhận bằng kiểm thử theo đường gọi production. Đừng dựa vào việc nhìn thấy annotation trong source code.

## 2. Cấu trúc của Method Security Reactive

| Thành phần | Vai trò |
| --- | --- |
| `Authentication` | Principal và authorities đã được xác thực |
| `ReactiveSecurityContextHolder` | Đọc SecurityContext từ Reactor Context |
| `@EnableReactiveMethodSecurity` | Bật advisors/interceptors cho reactive methods |
| `@PreAuthorize` | Khai điều kiện quyền trước xử lý method |
| `@PostAuthorize` | Kiểm điều kiện sau method theo reactive semantics |
| `AuthorizationManager` | API quyết định ALLOW/DENY trong Spring Security hiện đại |
| Spring AOP proxy | Intercept những invocation đi qua bean proxy |
| Target object | Thực thi method nghiệp vụ |
| `Mono`/`Flux` | Publisher phản ánh result/error khi được subscribe |

Spring Security 6.x có thể cấu hình:

~~~java
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class MethodSecurityConfiguration {
}
~~~

Spring AOP tạo proxy cho bean phù hợp. Khi lời gọi đi qua proxy, advisor nhận diện `@PreAuthorize`, lấy Authentication qua **Reactor Context** khi kiểm tra quyền trong quá trình reactive và cho phép/từ chối theo biểu thức.

### Phân biệt invocation với subscription

~~~text
1. Caller gọi securedBean.operation() qua proxy.
2. Spring reactive interceptor tạo/bao Publisher phù hợp.
3. WebFlux/StepVerifier subscribe Publisher.
4. Authentication trong subscriber Reactor Context được dùng xét quyền.
5. Nếu deny: Publisher phát AccessDeniedException.
6. Nếu allow: Publisher nghiệp vụ có thể được thực thi.
~~~

Test chỉ gọi `Mono<?> p = bean.operation()` hoặc `assertNotNull(p)` chưa chứng minh enforcement. Test nên **subscribe** bằng `StepVerifier` hoặc `WebTestClient.exchange()`. Side effects nên nằm trong reactive source (`Mono.defer` hoặc reactive repository) chứ không chạy sớm trước khi quyền được xác minh.

Reactive Method Security khác cấu hình Servlet Method Security: `@EnableWebFluxSecurity` chỉ bật WebFlux HTTP security, không thay `@EnableReactiveMethodSecurity` khi cần bảo vệ service methods.

## 3. Target, proxy và self-invocation

Giả sử có:

~~~java
@Service
class ApplicationService {
    public Mono<String> outer() {
        return inner();
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> inner() {
        return Mono.just("operation-result");
    }
}
~~~

Nếu ứng dụng gọi `service.outer()` từ bên ngoài:
- Invocation `outer` đi vào proxy rồi target.
- Trên target, `inner()` tương đương `this.inner()`.
- Lời gọi `inner` không trở lại proxy.
- Advice của `inner` không được áp dụng trong đường gọi ấy.

Ngay cả khi `outer` là public, `inner` là public, bean là `@Service` và security annotations được bật, **điều kiện qua proxy vẫn không thỏa**.

### Những đường gọi cần phân biệt

| Đường gọi | Qua proxy? | Hành vi liên quan |
| --- | --- | --- |
| Controller inject bean và gọi method annotated | Có nếu injection trả proxy | Interceptor có thể chạy |
| Bean A inject bean B rồi gọi method annotated ở B | Có | Interceptor có thể chạy |
| Method cùng target gọi `this.secured()` | Không | Method advice bị bỏ qua |
| Method cùng target gọi `secured()` không có `this` | Không | Vẫn self-invocation |
| Tự `new Service()` ngoài Spring context | Không | Không có Spring AOP |
| `@Bean` trả instance được container quản lý | Có thể | Container có thể tạo proxy |
| `private` helper được annotate | Không | Không là proxy boundary |
| Class CGLIB với `final` method | Không advise được method đó | Không thể override |
| JDK proxy được inject bằng interface | Có | Interface method có thể được intercept |
| Method chưa được subscribe | Chưa đủ chứng cứ | Không kết luận decision đã chạy |

Nếu method ngoài proxy đã có security rule chặn đủ action thì một lời gọi nội bộ tới helper không nhất thiết tạo lỗ hổng. Rủi ro phát sinh khi **security boundary thực tế chỉ đặt trên method bị gọi nội bộ**, hoặc có đường vào khác không được bảo vệ.

## 4. JDK dynamic proxy và CGLIB

Spring AOP thường chọn một trong hai cơ chế:

| Đặc điểm | JDK proxy | CGLIB/class-based proxy |
| --- | --- | --- |
| Proxy cái gì? | Interface(s) | Subclass của target |
| Đường inject ổn định | Interface | Class hoặc interface |
| Concrete method không khai trong interface | Không expose qua interface proxy | Có thể được advise nếu đủ điều kiện |
| `final class` | Có thể proxy qua interface tùy cấu hình | Không tạo subclass được |
| `final method` | Phụ thuộc invocation qua interface proxy | Không override/advice bằng subclass |
| `private method` | Không phải public interface method | Không override/advice |
| Self-invocation | Không được advice | Không được advice |

Không giả định loại proxy tuyệt đối từ việc class có interface: Spring Boot và cấu hình AOP có thể thay đổi strategy. Dùng:

~~~java
AopUtils.isAopProxy(bean);
AopUtils.isJdkDynamicProxy(bean);
AopUtils.isCglibProxy(bean);
~~~

Đó là các **đoạn kiểm tra** trong context/test đã import `org.springframework.aop.support.AopUtils`, không phải chương trình độc lập.

### Các tình huống visibility

- **`private`:** không được class-based proxy override; đừng đặt chốt quyền chỉ trên private method.
- **`final` method:** class-based proxy không override; không dùng để làm điểm chặn trên CGLIB.
- **`final` class:** không thể subclass để CGLIB proxy; interface-based proxy là tình huống khác cần test.
- **`protected`/package-private:** khả năng advice phụ thuộc kiểu proxy, version và visibility. Ưu tiên **public service method** cho ranh giới quyền.
- **`static` method/constructor:** không phải instance-method boundary của Spring AOP proxy thông thường.
- **Kotlin:** class/method mặc định final; thường cần `kotlin-spring`/all-open plugin cho Spring-managed classes.
- **Java module/JPMS:** hạn chế mở package/visibility có thể ảnh hưởng CGLIB.
- **JDK proxy:** inject concrete implementation có thể không tương thích; inject interface khi chọn interface proxy.

Việc bật `proxyTargetClass=true` không khắc phục self-invocation. Nó chỉ ảnh hưởng cách proxy được xây dựng.

## 5. Java 17 thuần: nhìn thấy self-call đi vòng qua proxy

Minh họa dưới đây dùng JDK `Proxy`, **không phải implementation của Spring Security**. Nó làm rõ việc một lời gọi nội bộ không đi lại qua proxy.

**`ProxyLab.java`**

~~~java
import java.lang.reflect.Proxy;

public class ProxyLab {
    public interface Operations {
        String guarded();
        String fromWithin();
    }

    static class Target implements Operations {
        @Override
        public String guarded() {
            return "TARGET METHOD";
        }

        @Override
        public String fromWithin() {
            return this.guarded();
        }
    }

    public static void main(String[] args) {
        Target target = new Target();
        Operations proxy = (Operations) Proxy.newProxyInstance(
                ProxyLab.class.getClassLoader(),
                new Class<?>[]{Operations.class},
                (p, method, arguments) -> {
                    if (method.getName().equals("guarded")) {
                        return "PROXY INTERCEPTED";
                    }
                    return method.invoke(target, arguments);
                });

        System.out.println(proxy.guarded());
        System.out.println(proxy.fromWithin());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ProxyLab.java
java ProxyLab
~~~

**Stdout chính xác:**

~~~text
PROXY INTERCEPTED
TARGET METHOD
~~~

Lần gọi thứ nhất đi qua `InvocationHandler` và bị intercept. Lần thứ hai gọi `Target.fromWithin()`; trong target, `this.guarded()` chạy trực tiếp. Mẫu này không đưa dữ liệu nhạy cảm vào ví dụ và chỉ nhằm học cách proxy hoạt động.

## 6. Ví dụ WebFlux/Spring Security có thể chạy

Dự án Java 17+ với Gradle, Spring Boot 3.x (ví dụ 3.5.x), Spring Security 6.x. Chúng ta tạo:
- Một security configuration bật WebFlux và Reactive Method Security.
- Một service `GuardedService` có method được annotate, cộng một method self-call **chỉ phục vụ test**.
- Một `SafeFacade` là bean khác inject `GuardedService`.
- Controller chỉ expose **đường gọi qua proxy**, không expose method self-call.
- Integration tests vừa kiểm tra role qua HTTP vừa kiểm tra advice bằng Reactor `StepVerifier`.

### 6.1. `settings.gradle`

~~~groovy
rootProject.name = 'reactive-proxy-lab'
~~~

### 6.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.proxy'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 6.3. `src/main/java/demo/proxy/ReactiveProxyApplication.java`

~~~java
package demo.proxy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveProxyApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveProxyApplication.class, args);
    }
}
~~~

### 6.4. `src/main/java/demo/proxy/ReactiveSecurityConfiguration.java`

~~~java
package demo.proxy;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
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
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
public class ReactiveSecurityConfiguration {
    @Bean
    SecurityWebFilterChain web(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/direct", "/api/facade")
                        .authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails viewer = User.withUsername("viewer")
                .password(encoder.encode("viewer-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(viewer, admin);
    }
}
~~~

`@EnableReactiveMethodSecurity` áp dụng annotation ở service, trong khi `SecurityWebFilterChain` chỉ yêu cầu user đã authenticated ở hai route. Nhờ vậy test có thể phân biệt **HTTP auth gate** với **method role gate**. `hasRole("ADMIN")` bên dưới kiểm authority `ROLE_ADMIN` (do `roles("ADMIN")` tạo ra). User store trong RAM và mật khẩu mẫu không dùng cho production.

### 6.5. `src/main/java/demo/proxy/GuardedService.java`

~~~java
package demo.proxy;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GuardedService {
    private final AtomicInteger executions = new AtomicInteger();

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> perform() {
        return Mono.defer(() -> {
            executions.incrementAndGet();
            return Mono.just("operation-performed");
        });
    }

    // Chỉ dùng trong bài kiểm thử cơ chế self-invocation.
    // Không expose method này ở HTTP API.
    public Mono<String> unsafeInternalCall() {
        return this.perform();
    }

    public int executionCount() {
        return executions.get();
    }
}
~~~

Đặt việc thực thi trong `Mono.defer` để khi publisher bị từ chối, logic nghiệp vụ không chạy. `unsafeInternalCall` là **phản ví dụ**, không phải một API được khuyến nghị. Đường gọi từ chính target sang `perform` không đi qua proxy.

### 6.6. `src/main/java/demo/proxy/SafeFacade.java`

~~~java
package demo.proxy;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SafeFacade {
    private final GuardedService guarded;

    public SafeFacade(GuardedService guarded) {
        this.guarded = guarded;
    }

    public Mono<String> performFromAnotherBean() {
        return guarded.perform();
    }
}
~~~

Đây là cách sửa được ưu tiên: façade và service là **hai Spring beans**. `SafeFacade` gọi `GuardedService` qua dependency đã inject, nghĩa là đi qua bean proxy.

### 6.7. `src/main/java/demo/proxy/ExampleController.java`

~~~java
package demo.proxy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ExampleController {
    private final GuardedService guarded;
    private final SafeFacade facade;

    public ExampleController(
            GuardedService guarded,
            SafeFacade facade) {
        this.guarded = guarded;
        this.facade = facade;
    }

    @GetMapping("/api/public")
    public Mono<String> publicPing() {
        return Mono.just("pong");
    }

    @GetMapping("/api/direct")
    public Mono<String> direct() {
        return guarded.perform();
    }

    @GetMapping("/api/facade")
    public Mono<String> facade() {
        return facade.performFromAnotherBean();
    }
}
~~~

Không có route cho `unsafeInternalCall()`. Hai đường production-intended trong demo đều đi tới `GuardedService.perform()` qua Spring bean proxy. Trong hệ thống có dữ liệu nhạy cảm, vẫn cần kiểm tra owner/tenant/permission per-resource; quyền `ROLE_ADMIN` chung chưa đủ.

## 7. Kiểm thử proxy và đường gọi thực tế

**`src/test/java/demo/proxy/ProxyIntegrationTest.java`**

~~~java
package demo.proxy;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        classes = ReactiveProxyApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ProxyIntegrationTest {
    @Autowired ApplicationContext context;
    @Autowired GuardedService guarded;
    @Autowired SafeFacade facade;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    private Authentication auth(String name, String authority) {
        return new UsernamePasswordAuthenticationToken(
                name, "test-only",
                List.of(new SimpleGrantedAuthority(authority)));
    }

    @Test
    void guardedBeanIsAProxy() {
        assertTrue(AopUtils.isAopProxy(guarded));
    }

    @Test
    void anonymousCannotCallDirect() {
        client.get().uri("/api/direct")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedViewerCannotCallDirect() {
        client.get().uri("/api/direct")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void authenticatedViewerCannotCallFacade() {
        client.get().uri("/api/facade")
                .headers(h -> h.setBasicAuth(
                        "viewer", "viewer-pass"))
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void adminCanCallBothRoutes() {
        client.get().uri("/api/direct")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("operation-performed");

        client.get().uri("/api/facade")
                .headers(h -> h.setBasicAuth(
                        "admin", "admin-pass"))
                .exchange().expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("operation-performed");
    }

    @Test
    void deniedSubscriptionDoesNotExecuteBusinessWork() {
        int before = guarded.executionCount();

        StepVerifier.create(guarded.perform()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("viewer", "ROLE_USER"))))
                .expectError(AccessDeniedException.class)
                .verify();

        assertEquals(before, guarded.executionCount());
    }

    @Test
    void adminSubscriptionPerformsWork() {
        StepVerifier.create(guarded.perform()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("admin", "ROLE_ADMIN"))))
                .expectNext("operation-performed")
                .verifyComplete();
    }

    @Test
    void internalCallDemonstratesMissingInterception() {
        // Cố ý chứng minh self-invocation không qua proxy.
        StepVerifier.create(guarded.unsafeInternalCall()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("viewer", "ROLE_USER"))))
                .expectNext("operation-performed")
                .verifyComplete();
    }

    @Test
    void separateBeanCallUsesTheInterceptor() {
        StepVerifier.create(facade.performFromAnotherBean()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                auth("viewer", "ROLE_USER"))))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void plainNewObjectIsNotProxied() {
        GuardedService manuallyCreated = new GuardedService();
        assertFalse(AopUtils.isAopProxy(manuallyCreated));

        StepVerifier.create(manuallyCreated.perform())
                .expectNext("operation-performed")
                .verifyComplete();
    }

    @Test
    void publicRouteIsPublic() {
        client.get().uri("/api/public")
                .exchange().expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

### 7.1. Vì sao test nội bộ lại “thành công”?

Test `internalCallDemonstratesMissingInterception` **chủ ý** minh họa việc method annotation không được áp dụng cho self-invocation. Đó là **điều cần loại bỏ trong code production**, không phải permission policy mong muốn. Controller chính không expose đường đó. Sau khi hoàn thành bài thực hành, xóa hoặc refactor `unsafeInternalCall`.

### 7.2. Ma trận kiểm thử

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Bean `GuardedService` lấy từ Spring Context | `AopUtils.isAopProxy` = true |
| Anonymous GET /api/direct | HTTP 401 |
| Viewer GET /api/direct | HTTP 403 |
| Viewer GET /api/facade | HTTP 403 |
| Admin GET /api/direct, /api/facade | HTTP 200, `operation-performed` |
| Viewer gọi `guarded.perform()` qua proxy bằng StepVerifier | `AccessDeniedException` |
| Publisher bị deny | `executionCount` không tăng |
| Admin gọi `perform()` | Publisher hoàn tất với value |
| Viewer gọi `unsafeInternalCall()` | Trả value, chứng minh thiếu interception |
| Viewer gọi qua façade đúng | `AccessDeniedException` |
| Tự `new GuardedService()` | Không phải AOP proxy |
| Anonymous GET /api/public | HTTP 200 |

### 7.3. Chạy test

~~~bash
./gradlew test --tests demo.proxy.ProxyIntegrationTest
./gradlew bootRun
~~~

Windows:

~~~text
gradlew.bat test --tests demo.proxy.ProxyIntegrationTest
gradlew.bat bootRun
~~~

Thử HTTP:

~~~bash
curl -i http://localhost:8080/api/direct
curl -i -u viewer:viewer-pass http://localhost:8080/api/direct
curl -i -u admin:admin-pass http://localhost:8080/api/facade
~~~

Kỳ vọng lần lượt là 401, 403 và 200 với body `operation-performed`. Bài đã được kiểm tra tĩnh; cần thực thi test trên project và versions thực tế trước khi dùng production. Không đặt demo passwords vào log/shell history của môi trường thật.

## 8. Những điều kiện để interceptor thực sự được áp dụng

1. **Dependency và configuration:** Có Spring Security và `@EnableReactiveMethodSecurity`. Không nhầm với `@EnableWebFluxSecurity` chỉ bảo vệ HTTP.
2. **Managed bean:** Service phải do Spring quản lý; object tự tạo trực tiếp không có proxy.
3. **Annotation resolution:** `@PreAuthorize` được đặt đúng method/class, không bị xung đột hoặc đặt ở vị trí Spring phiên bản đó không nhận diện.
4. **Proxyable method:** Method được expose đúng kiểu JDK/CGLIB proxy; tránh private/final không phù hợp.
5. **External call:** Invocation phải đi qua proxy, không phải `this.method()` hay constructor.
6. **Reactive signature:** Return type là `Publisher` được hỗ trợ (thường `Mono`/`Flux`), không đổi thành method blocking thông thường mà vẫn mong reactive method security hoạt động.
7. **Reactor Context:** Khi Publisher được subscribe, có Authentication đáng tin với authorities đúng.
8. **Subscription:** Publisher được subscribe; `StepVerifier`/`WebTestClient` mới chứng minh allow/deny.
9. **Không nuốt lỗi:** `AccessDeniedException` không bị `onErrorResume` chuyển thành dữ liệu nhạy cảm.
10. **Bảo vệ business:** Các điều kiện tenant/owner/resource vẫn được xét độc lập với role tổng quát.

### Vì sao `@PostAuthorize` không cứu được self-invocation?

`@PostAuthorize` cũng là method-security advice được gắn qua AOP. Nếu lời gọi không qua proxy, annotation hậu kiểm cũng không thực thi ở lời gọi đó. Ngoài ra hậu kiểm không nên là chốt duy nhất với tác dụng phụ không thể rollback (gửi email/event, xóa file remote). Hãy authorize trước mutation và dùng transaction/outbox khi cần.

## 9. Sửa self-invocation đúng cách

### 9.1. Tách public method sang bean khác (ưu tiên)

~~~text
Controller
   |
   v
Facade bean
   |
   v
Protected bean PROXY
   |
   +-> @PreAuthorize + reactive service implementation
~~~

Ưu điểm: rõ boundary, dễ test, ít coupling vào Spring internals, không tạo vòng phụ thuộc. Mẫu `SafeFacade` trong project áp dụng cách này.

### 9.2. Đặt annotation lên public entry thực tế

Nếu method công khai `outer` là đường duy nhất được phép gọi, có thể annotate trực tiếp:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> outer() {
    return innerHelper();
}
~~~

**Đây là đoạn minh họa**: `innerHelper` phải được định nghĩa và không có đường công khai khác bỏ qua `outer`. Điều kiện là **mọi đường vào nhạy cảm đều đi qua entry được bảo vệ**. Nếu còn endpoint hoặc worker gọi helper trực tiếp, cần thêm boundary riêng.

### 9.3. Self-injection

Có thể inject self proxy qua cách thức phù hợp, nhưng dễ phát sinh circular dependencies và lỗi type với JDK proxies. Không ưu tiên hơn tách bean. Cần test rõ instance được inject có phải proxy.

### 9.4. `AopContext.currentProxy()`

Spring AOP có `AopContext.currentProxy()` khi expose proxy được cấu hình, nhưng cách này liên kết business code với AOP internals. Trong reactive flow có đổi scheduler/thread, dùng current proxy bằng ThreadLocal tại thời điểm sai có thể khó bảo đảm. Không dùng làm mặc định.

### 9.5. AspectJ weaving

AspectJ compile-time/load-time weaving có thể áp dụng advice ở bytecode, tránh chính hạn chế self-invocation của Spring AOP proxy. Nhưng đó là cơ chế build/runtime khác, đòi hỏi cấu hình, kiểm thử riêng và không chỉ sửa bằng một annotation. Với ứng dụng WebFlux thông thường, tách bean rõ ràng thường đơn giản và an toàn hơn.

## 10. Lỗi quan sát được và cách kiểm tra

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `@PreAuthorize` không chặn dù code có annotation | Chưa bật reactive method security | Thêm `@EnableReactiveMethodSecurity` |
| Viewer gọi method direct bị từ chối, gọi internal được | Self-invocation | Tách bean hoặc bảo vệ entry |
| Test tạo object bằng `new` không bị chặn | Không có proxy | Inject bean Spring trong integration test |
| `AopUtils.isAopProxy` = false | Bean không được proxy/annotation không áp dụng | Kiểm dependency, configuration, method |
| Concrete class injection lỗi | JDK interface proxy | Inject interface hoặc điều chỉnh proxy strategy |
| `final` class không khởi tạo proxy | CGLIB cần subclass | Bỏ final hoặc dùng interface phù hợp |
| `private` method annotate nhưng không có effect | Không intercept private | Bảo vệ public method |
| Không có Authentication trong StepVerifier | Chưa thêm Reactor Context | `contextWrite(withAuthentication(testAuth))` |
| Test chỉ assert Mono object | Publisher chưa subscribe | `StepVerifier.create(...).verify()` |
| HTTP 401 | Chưa đăng nhập hoặc sai credentials | Kiểm authentication filter/entry point |
| HTTP 403 | Đã đăng nhập nhưng thiếu authority | Kiểm `hasRole`/`hasAuthority`/CSRF khi có unsafe method |
| `block()` gây lỗi trên Netty thread | Blocking trong non-blocking context | Compose Mono/Flux |
| `@Transactional` cũng bị bỏ qua trong cùng class | Self-invocation bypass proxy | Tách transactional bean, test transaction |
| Khác nhau sau nâng Boot | Proxy mode/annotation resolution khác | Integration regression tests |
| User đúng role vẫn đọc sai tenant | Thiếu resource-level checks | Bind tenant/owner/resource vào policy |
| Error bị catch và trả success | `onErrorResume` fail open | Propagate access denied, không trả payload |
| Mono cache chia sẻ dữ liệu user | Cache không phân vùng theo identity | Không global-cache giá trị phụ thuộc auth |

## 11. `@Transactional`, caching và WebFlux context

`@Transactional`, `@Cacheable` và Method Security đều có thể dựa vào proxy. Nếu một method nội bộ được gọi bằng `this`, có thể bỏ qua advice giao dịch **cũng như** authorization. `@Transactional` reactive cần `ReactiveTransactionManager` phù hợp và Publisher thực thi trong reactive transaction context; có security context không tự có transaction.

Không tự giả định thứ tự transaction/security advisors chỉ vì vị trí annotations trong source. Nếu policy cần đọc DB trong cùng transaction hoặc phải chống race với thay đổi quyền, kiểm tra thực tế bằng integration test, transaction isolation, locks hoặc revision-aware policy.

**Reactor Context** mang authentication theo subscription; `SecurityContextHolder` imperative thường dùng ThreadLocal không phải nguồn mặc định đáng tin trong WebFlux. Không tự `subscribe()`/`block()` khi viết reactive service. Không đưa `Authentication` vào Context dựa trên input không tin cậy.

Một service có thể được proxy đúng nhưng vẫn sai object-level authorization nếu `@PreAuthorize("hasRole('ADMIN')")` không xét tenant, owner và trạng thái resource. Method Security là điểm thực thi policy, **không tự biết** mọi điều kiện nghiệp vụ.

## 12. Checklist trước production

1. Có `@EnableReactiveMethodSecurity` và dependency thích hợp?
2. Method bảo vệ là public service entry, return `Mono`/`Flux`?
3. Bean từ ApplicationContext thực sự là Spring AOP proxy?
4. Có lời gọi `this.securedMethod()`, self-invocation hoặc constructor call không?
5. Proxy mode JDK/CGLIB có phù hợp interfaces, final, visibility?
6. Có test direct invocation và đường gọi qua façade/controller thật?
7. Negative test user thiếu quyền có subscribe và nhận `AccessDeniedException`?
8. Test chứng minh denied publisher không mutate business state?
9. HTTP test phân biệt 401 chưa authenticated và 403 không đủ role?
10. Không có URL hoặc worker path truy cập method chưa được bảo vệ?
11. Reactive Context chứa principal đã được xác thực, không fake từ header?
12. Không swallow `AccessDeniedException` bằng fallback trả dữ liệu?
13. Không self-injection/circular dependency phức tạp nếu có thể tách bean?
14. Không dùng `@PostAuthorize` làm chốt duy nhất sau side effect?
15. Các operations theo document/tenant có permission checks đúng resource?
16. `@Transactional`/`@Cacheable` và Method Security được test cùng lúc nếu kết hợp?
17. Kotlin all-open hoặc JPMS proxy visibility được xử lý nếu cần?
18. CI có tests bằng Spring context, Reactor StepVerifier, WebTestClient?

## 13. Bài tập

**Bài 1:** Biên dịch `ProxyLab.java` bằng `javac/java`. Giải thích chính xác hai dòng stdout và mối liên hệ với Spring AOP.

**Bài 2:** Dùng StepVerifier gọi `GuardedService.perform` qua Spring bean với viewer, sau đó gọi `unsafeInternalCall`. Giải thích tại sao kết quả khác nhau dù bên trong đều gọi `perform`.

**Bài 3:** Refactor code sao cho không tồn tại đường gọi nội bộ không kiểm quyền. Đưa chốt sang bean riêng, hoặc đặt annotation trên entry thực tế.

**Bài 4:** Thêm một `@PreAuthorize("hasAuthority('DOC_APPROVE')")` cho method trả Mono. Test USER không có quyền, ADMIN có quyền khi scope nghiệp vụ cho phép.

**Bài 5:** Dùng `AopUtils` xác minh JDK/CGLIB proxy trong project có/không interface. Thử method final và ghi nhận giới hạn của từng kiểu.

**Bài 6:** Đặt side effect trong `Mono.defer`, đo counter trước/sau một deny. Test không có business side effect khi quyền bị từ chối.

**Bài 7:** Tạo rule theo document và tenant. Test người có `ROLE_ADMIN` tại tenant A không tự sửa tài liệu tenant B.

**Bài 8:** Dùng WebTestClient kiểm tra HTTP Basic, 401, 403, 200. Sau đó bỏ `@EnableReactiveMethodSecurity` trong nhánh thử nghiệm và quan sát tests bảo mật phải phát hiện regression.

**Bài 9:** Tạo hai service annotations `@Transactional` và `@PreAuthorize`, dùng database reactive để chứng minh self-invocation có thể phá transaction/authorization boundaries.

**Tiêu chí hoàn thành:** phân biệt target/proxy, giải thích JDK vs CGLIB và `private`/`final`, nêu đúng nguyên nhân self-invocation, biết điều kiện reactive Publisher/Reactor Context và có integration tests chứng minh interceptor thực sự chạy.

## Tài liệu tham khảo chính thức

- Spring Security – Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security 6.5 – Reactive Method Security: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html
- Spring Framework 6.2 – Proxying Mechanisms, self-invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Security – ReactiveSecurityContextHolder API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html
- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security – WebFlux test setup: https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html
- Spring Framework – Declarative transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Reactor – Context: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
