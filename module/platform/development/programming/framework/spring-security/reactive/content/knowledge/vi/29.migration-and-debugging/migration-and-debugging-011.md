# Chẩn đoán annotation bảo mật không chạy và lỗi tự gọi phương thức trong Spring Security Reactive

Bài học thuộc nhóm **Chuyển đổi và gỡ lỗi** của module **Spring Security – reactive**. Tình huống điển hình: một phương thức có `@PreAuthorize("hasRole('ADMIN')")` nhưng người dùng thường vẫn nhận dữ liệu; khi gọi từ controller khác thì bị từ chối, còn gọi từ phương thức cùng lớp lại thành công. Nguyên nhân thường nằm ở **kích hoạt method security**, **ranh giới Spring AOP proxy**, **kiểu phương thức reactive** hoặc **Reactor SecurityContext**; đôi khi annotation vẫn chạy nhưng biểu thức quyền trả kết quả không như mong đợi.

Mục tiêu là tự chẩn đoán đúng tầng đang lỗi, **tái hiện self-invocation**, sửa bằng cách chuyển lời gọi qua Spring-managed bean/proxy, và viết kiểm thử chống hồi quy. Ví dụ sử dụng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, WebFlux và Reactor**.

## 1. Phân biệt “annotation không chạy” với “quyết định không đúng”

| Dấu hiệu | Điều có thể đã xảy ra | Điểm cần kiểm tra |
| --- | --- | --- |
| Người dùng `USER` gọi được phương thức chỉ `ADMIN` | Advice chưa chạy, self-invocation, hoặc biểu thức/quyền được cấu hình sai | Có bật `@EnableReactiveMethodSecurity`? Có gọi qua proxy? Roles thực là gì? |
| API trả 401 khi chưa đăng nhập | Web filter hoặc method authorization từ chối rồi được chuyển thành authentication entry point | Có HTTP Basic/Bearer? Security context hiện có là gì? |
| API trả 403 cho tài khoản đã đăng nhập | Có thể WebFlux URL authorization **hoặc** method authorization từ chối | Cô lập chính sách HTTP và service để xác định tầng |
| Hàm gắn `@PreAuthorize` không được gọi, test chỉ kiểm tra `Mono` vừa được tạo | Chuỗi reactive chưa được subscribe; chưa quan sát tín hiệu | Dùng `StepVerifier` hoặc `WebTestClient.exchange()` |
| Method chạy trong request bình thường, lỗi khi chạy task nền | Không có `Authentication` trong Reactor `Context`, hoặc subscription bị tách rời | Kiểm tra nơi tạo subscription và ngữ cảnh bảo mật |
| Có proxy, nhưng lời gọi `this.secured()` vẫn không bị kiểm tra | Spring AOP chỉ intercept lời gọi đi **qua proxy** | Tách method sang bean khác rồi inject và gọi qua bean |

**Hai lớp bảo vệ tách biệt:** `authorizeExchange(...)` trong `SecurityWebFilterChain` bảo vệ URL, còn `@PreAuthorize`/`@PostAuthorize` bảo vệ lời gọi phương thức Spring bean. `@EnableWebFluxSecurity` hoặc dependency `spring-boot-starter-security` **không thay thế** `@EnableReactiveMethodSecurity` khi muốn thực thi annotation ở tầng method. Một route có `permitAll()` vẫn có thể bị `@PreAuthorize` chặn ở service; một route được HTTP layer bảo vệ đúng không chứng minh method annotation đã được bật.

## 2. Cơ chế proxy và self-invocation

Spring Security reactive method authorization dựa trên **Spring AOP**. Trong chế độ proxy (mặc định), interceptor chỉ có cơ hội kiểm tra khi client gọi method **trên proxy của bean**:

```text
Controller
   |
   | service.secured()      (service được Spring inject)
   v
Spring AOP proxy
   |
   | @PreAuthorize -> kiểm tra Authentication + quyền
   |-- DENY -> AccessDeniedException, không cho tới method
   '-- GRANT
          |
          v
      target.secured()
```

Nhưng nếu một method bên trong cùng đối tượng gọi `this.secured()` hoặc chỉ `secured()`:

```text
Controller -> proxy.outer() -> target.outer()
                                  |
                                  | this.secured()
                                  v
                              target.secured()
                    (không đi qua proxy, bỏ qua @PreAuthorize)
```

Dù `target.secured()` có annotation và Spring **đã tạo proxy**, lời gọi nội bộ vẫn bypass advice. Điều này cũng đúng khi call được giấu trong `Mono.defer(() -> this.secured())`, `flatMap(x -> this.secured())` hoặc lambda ở cùng instance: bản chất vẫn là `this`, không phải proxy. Chuyển sang reactive operators **không tự sửa** vấn đề self-invocation.

**Lỗi không chỉ nằm ở method được gọi:** `@Transactional`, `@Cacheable` và các Spring AOP advice khác cũng có giới hạn self-invocation tương tự, dù tác động cụ thể phụ thuộc cấu hình và kiểu proxy.

## 3. Điều kiện cần để method security reactive hoạt động

### 3.1. Bật đúng annotation cho reactive

Dùng:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
```

Import:

```java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

Từ Spring Security 6.0, `useAuthorizationManager` mặc định là `true`; `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` cũng hợp lệ với dòng 6.3 nhưng không cần viết dài. Nó kích hoạt các interceptor như `AuthorizationManagerBeforeReactiveMethodInterceptor` cho `@PreAuthorize`.

Đừng thay bằng `@EnableMethodSecurity` của cách cấu hình thông thường cho ứng dụng WebFlux nếu mục tiêu là reactive method interception. `@EnableWebFluxSecurity` dùng cho web filter; nó không tự bật method annotation. Với `@Secured` hoặc `@RolesAllowed`, cần đối chiếu các tùy chọn enablement phù hợp; trong bài này dùng `@PreAuthorize` để cô lập lỗi.

### 3.2. Phương thức là của Spring bean được gọi qua proxy

- Lớp cần được Spring quản lý: `@Service`, `@Component` hoặc bean từ `@Bean` thuộc application context đúng. `new SensitiveService()` tạo đối tượng trực tiếp sẽ không có proxy Spring.
- Có thể dùng JDK interface proxy khi có interface hoặc subclass proxy (CGLIB) khi phù hợp. Với subclass proxy, lớp/method `final` không thể được advice bằng override; method `private` cũng không được intercept qua subclass proxy.
- Với Kotlin, class/method mặc định `final`; cần chú ý plugin `kotlin-spring`/`all-open` hoặc thiết kế interface/proxy phù hợp. Đừng dựa vào subclass proxy cho `final` method.
- Đặt annotation trên public service method dễ đọc và kiểm thử; nếu dùng interface, generic, bridge method, inheritance hoặc annotation trên implementation, cần xác minh proxy nhìn thấy chính xác annotation/target method.
- Nếu interface-based proxy được dùng, hãy inject qua interface phù hợp và gọi interface method; đừng ép cast proxy sang concrete class mà nó không implement.

### 3.3. Reactor Publisher, subscription và SecurityContext

Với Java reactive method security, thực hành thông thường dùng phương thức trả về `Mono<T>`/`Flux<T>` (hoặc `Publisher<T>`), để authorization tích hợp với Reactor `Context`. Không sao chép nguyên method đồng bộ trả `String` của Servlet sang reactive rồi cho rằng hành vi giống nhau.

`ReactiveSecurityContextHolder` lưu/đọc thông tin xác thực từ **Reactor Context**. Với request WebFlux đi qua Spring Security, context được thiết lập từ quá trình xác thực HTTP. Với unit test hoặc job không khởi đầu từ HTTP, phải cấp context theo cách hợp lệ, ví dụ `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`. Không dùng `SecurityContextHolder.getContext()` ThreadLocal từ Servlet làm bằng chứng cho reactor pipeline.

Publisher chưa được **subscribe** sẽ chưa phát ra kết quả/báo lỗi như một luồng request thật. Đừng kiểm thử bằng việc chỉ viết `Mono<String> result = service.secured()` rồi khẳng định đã được allow/deny. Tránh `.block()` trong WebFlux event-loop; dùng `StepVerifier` trong test hoặc `WebTestClient` cho kiểm thử HTTP.

## 4. Ví dụ đầy đủ: tái hiện lỗ hổng, sau đó sửa đúng

Ví dụ cố tình có hai đường dẫn **chỉ dành cho local demo**:

- `GET /lab/self` gọi method bảo vệ qua `this` trong cùng bean: **bypass** authorization method.
- `GET /lab/proxy` gọi method của bean bảo vệ khác qua Spring injection: **đúng** proxy boundary, yêu cầu `ROLE_ADMIN`.

HTTP layer cho phép cả hai đường dẫn (`permitAll()`) **để quan sát độc lập method security**. Đây là cấu hình minh họa lỗ hổng; không đưa `/lab/self` lên production. Tài khoản demo có mật khẩu cố định và chỉ được khai báo khi bật profile `demo`.

### 4.1. Tạo dự án Maven

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>reactive-method-proxy-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

### 4.2. Khởi động ứng dụng

Tạo `src/main/java/com/example/methodlab/MethodLabApplication.java`:

```java
package com.example.methodlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodLabApplication.class, args);
    }
}
```

### 4.3. Web security và reactive method security

Tạo `src/main/java/com/example/methodlab/SecurityConfiguration.java`:

```java
package com.example.methodlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        // Chỉ để thấy method security có chạy hay không.
                        .pathMatchers(HttpMethod.GET, "/lab/self", "/lab/proxy")
                            .permitAll()
                        .anyExchange().authenticated())
                .httpBasic(withDefaults())
                .formLogin(form -> form.disable())
                // GET-only demo: không tắt CSRF toàn cục.
                .build();
    }

    @Bean
    @Profile("demo")
    MapReactiveUserDetailsService demoUsers() {
        return new MapReactiveUserDetailsService(
                User.withUsername("viewer")
                        .password("{noop}viewer123")
                        .roles("USER")
                        .build(),
                User.withUsername("admin")
                        .password("{noop}admin123")
                        .roles("ADMIN")
                        .build());
    }
}
```

`{noop}` chỉ minh họa PasswordEncoder được khai báo rõ cho lab, **không bảo vệ mật khẩu**; không dùng tài khoản demo hoặc kiểu lưu mật khẩu này cho production. Trong hệ thống thật dùng password hash an toàn, identity provider/authorization server, TLS và quản lý secret phù hợp. Tùy cấu hình authentication, Basic credential hợp lệ sẽ tạo `Authentication` có authority `ROLE_USER` hoặc `ROLE_ADMIN` trong Reactor SecurityContext.

### 4.4. Bean có lỗi tự gọi: annotation bị bỏ qua

Tạo `src/main/java/com/example/methodlab/SelfCallingService.java`:

```java
package com.example.methodlab;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SelfCallingService {

    public Mono<String> readInternally() {
        // Sai: target gọi trực tiếp method cùng lớp, không đi qua AOP proxy.
        return this.secret();
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> secret() {
        return Mono.fromSupplier(() -> "secret-report");
    }
}
```

Điều đáng chú ý: `SelfCallingService` vẫn là Spring bean, `secret()` là public và có annotation hợp lệ. Nếu một bean khác gọi `selfCallingService.secret()` qua proxy, quyền được kiểm tra. Nhưng lời gọi `readInternally() -> this.secret()` chạy **bên trong target** nên interceptor của `secret()` bị bỏ qua. `Mono.fromSupplier` chỉ trì hoãn việc tạo dữ liệu tới subscription; nó **không** thay đổi tuyến gọi qua proxy.

### 4.5. Sửa bằng cách tách bean bảo vệ khỏi bean điều phối

Tạo `src/main/java/com/example/methodlab/ProtectedReportService.java`:

```java
package com.example.methodlab;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProtectedReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readReport() {
        return Mono.fromSupplier(() -> "secret-report");
    }
}
```

Tạo `src/main/java/com/example/methodlab/ReportFacade.java`:

```java
package com.example.methodlab;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportFacade {

    private final ProtectedReportService protectedReport;

    public ReportFacade(ProtectedReportService protectedReport) {
        this.protectedReport = protectedReport;
    }

    public Mono<String> readThroughProxy() {
        // Đúng: gọi sang Spring bean khác bằng reference đã được DI.
        return protectedReport.readReport();
    }
}
```

`ReportFacade` chỉ điều phối, `ProtectedReportService` sở hữu chính sách quyền. Khi Spring inject `protectedReport`, đối tượng nhận được là proxy thích hợp, nên `@PreAuthorize` được thực thi. Tách bean cũng làm ranh giới authorization dễ nhìn thấy trong code review và dễ test độc lập.

### 4.6. Controller dùng cùng HTTP policy để so sánh

Tạo `src/main/java/com/example/methodlab/LabController.java`:

```java
package com.example.methodlab;

import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@Profile("demo")
@RestController
class LabController {

    private final SelfCallingService self;
    private final ReportFacade facade;

    LabController(SelfCallingService self, ReportFacade facade) {
        this.self = self;
        this.facade = facade;
    }

    @GetMapping("/lab/self")
    Mono<String> unsafeSelfCall() {
        return self.readInternally();
    }

    @GetMapping("/lab/proxy")
    Mono<String> secureCrossBeanCall() {
        return facade.readThroughProxy();
    }
}
```

Ở đây controller là một bean khác, nhưng `self.readInternally()` **không có** `@PreAuthorize`; khi vào method đó, lời gọi `this.secret()` bị bypass. `facade.readThroughProxy()` đi qua `ProtectedReportService` proxy nên chính sách ADMIN vẫn chạy.

**Sơ đồ mấu chốt:**

```text
GET /lab/self
  Controller -> SelfCallingService proxy -> target.readInternally()
                                      -> this.secret() [BYPASS]
  USER/anonymous có thể thấy "secret-report" (lỗ hổng minh họa)

GET /lab/proxy
  Controller -> ReportFacade -> ProtectedReportService proxy
                               -> @PreAuthorize ADMIN
  anonymous -> HTTP 401
  USER      -> HTTP 403
  ADMIN     -> HTTP 200, "secret-report"
```

Trong hệ thống thật không được giữ endpoint `/lab/self`: nó chỉ để **chứng minh** lỗi. Cách sửa đúng trong nghiệp vụ là chuyển logic nhạy cảm sang bean/đường gọi bảo vệ và xóa mọi tuyến bypass đã tìm thấy, không chỉ “thêm annotation” vào nhiều nơi cho đến khi test tình cờ xanh.

## 5. Chạy thử và đọc tín hiệu

Chạy JDK 17+, Maven:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=demo
```

Sau khi server khởi động trên `localhost:8080`, thử:

```bash
curl -i http://localhost:8080/lab/self
curl -i -u viewer:viewer123 http://localhost:8080/lab/self

curl -i http://localhost:8080/lab/proxy
curl -i -u viewer:viewer123 http://localhost:8080/lab/proxy
curl -i -u admin:admin123 http://localhost:8080/lab/proxy
```

Kết quả **dự kiến** (status chính xác có thể phụ thuộc cách ứng dụng tùy biến exception handler/entry point; với cấu hình ví dụ là 200/401/403):

| Caller | `GET /lab/self` (lỗi) | `GET /lab/proxy` (đúng) |
| --- | --- | --- |
| Anonymous | **200**, trả `secret-report` dù không đăng nhập | **401**, yêu cầu xác thực |
| `viewer` có `ROLE_USER` | **200**, sai mục tiêu bảo vệ | **403**, xác thực rồi nhưng thiếu ADMIN |
| `admin` có `ROLE_ADMIN` | 200 | 200, trả `secret-report` |

Chỉ thấy 403 ở controller **chưa đủ** để kết luận annotation chạy: nếu HTTP policy đã yêu cầu ADMIN ngay từ URL, controller có thể bị chặn **trước khi service được gọi**. Trong demo, hai URL đều `permitAll` có chủ ý để tách hai tầng kiểm tra.

Nếu có Basic header sai mật khẩu, request có thể bị từ chối ngay ở authentication filter (401) và không đến controller. Đừng dùng trường hợp sai mật khẩu để đánh giá self-invocation. Trong hệ thống thực, không đưa password lên command-line; lệnh `curl -u` với mật khẩu mẫu chỉ dành cho môi trường local, nên dùng TLS nếu chạy qua mạng.

## 6. Test tích hợp chứng minh proxy boundary

Tạo `src/test/java/com/example/methodlab/MethodSecurityIntegrationTest.java`:

```java
package com.example.methodlab;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("demo")
class MethodSecurityIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    SelfCallingService self;

    @Autowired
    ProtectedReportService report;

    @Test
    void springHasProxiesButSelfInvocationStillBypassesAdvice() {
        assertThat(AopUtils.isAopProxy(self)).isTrue();
        assertThat(AopUtils.isAopProxy(report)).isTrue();

        client.get().uri("/lab/self")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("secret-report");
    }

    @Test
    void anonymousRequestIsStoppedAtProtectedMethod() {
        client.get().uri("/lab/proxy")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ordinaryUserIsDeniedByMethodSecurity() {
        client.get().uri("/lab/proxy")
                .headers(h -> h.setBasicAuth("viewer", "viewer123"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanCallTheProtectedMethod() {
        client.get().uri("/lab/proxy")
                .headers(h -> h.setBasicAuth("admin", "admin123"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("secret-report");
    }
}
```

Chạy:

```bash
mvn test
```

Bài test xác nhận hai điều khác nhau: **proxy có tồn tại** và **lời gọi đi qua proxy hay không**. `AopUtils.isAopProxy(self) == true` không có nghĩa mọi method gọi bên trong bean đều được intercept. Đó là lý do test với anonymous ở `/lab/self` cho 200 là dấu hiệu bypass, trong khi `/lab/proxy` buộc phải có kết quả 401/403/200 theo danh tính. Chỉ dùng test assert bean có annotation hoặc proxy sẽ bỏ sót lỗi self-invocation.

Sau khi sửa ứng dụng thực, điều kiện chấp nhận nên là **không còn nhánh bypass**; không chuyển bài test minh họa lỗ hổng thành tiêu chí thành công của production.

## 7. Test trực tiếp method bằng Reactor Context

Có thể tách khỏi HTTP để chứng minh lỗi nằm ở tầng method. Khi kiểm tra trực tiếp, tự cung cấp `Authentication` vào Reactor context. Ví dụ một test đơn giản, giả sử có bean `ProtectedReportService` và `SelfCallingService` được `@Autowired` trong `@SpringBootTest`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

@SpringBootTest
class MethodAuthorizationUnitStyleTest {

    @Autowired
    ProtectedReportService report;

    @Autowired
    SelfCallingService self;

    @Test
    void userGetsDeniedThroughProxy() {
        Authentication viewer = new UsernamePasswordAuthenticationToken(
                "viewer", "n/a", AuthorityUtils.createAuthorityList("ROLE_USER"));

        StepVerifier.create(report.readReport()
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(viewer)))
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void sameUserBypassesProtectionWithSelfCall() {
        Authentication viewer = new UsernamePasswordAuthenticationToken(
                "viewer", "n/a", AuthorityUtils.createAuthorityList("ROLE_USER"));

        StepVerifier.create(self.readInternally()
                .contextWrite(ReactiveSecurityContextHolder.withAuthentication(viewer)))
                .expectNext("secret-report")
                .verifyComplete();
    }
}
```

Đoạn này có thể đặt thành file `src/test/java/com/example/methodlab/MethodAuthorizationUnitStyleTest.java` sau khi thêm khai báo `package com.example.methodlab;` ở đầu tệp; phần import/class đã viết đầy đủ còn dòng `package` được lược bớt chỉ để tập trung vào kiểm tra Reactor context. Nếu chạy như tệp độc lập, phải bổ sung đúng dòng package.

Test cần **subscribe** bằng `StepVerifier`; chỉ gọi `report.readReport()` không xác nhận luồng authorization đã thực thi. Khi bạn thực sự dùng `Mono.deferContextual` hoặc các operators khác, Reactor Context truyền theo subscription. `publishOn`/`subscribeOn` bình thường **không mặc nhiên** làm mất Reactor Context; vấn đề thường xuất hiện khi tự `subscribe()` tách chuỗi, gọi code bên ngoài Reactor, hoặc không truyền context vào publisher mới.

Nếu kiểm tra method security khi không có HTTP request, đừng áp `@WithMockUser` cho mọi kiểu test một cách máy móc rồi suy luận theo ThreadLocal. `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` là cách minh bạch để chứng minh pipeline đang thấy authentication nào. Test HTTP bằng `WebTestClient`/Spring Security test support thì ngữ cảnh được thiết lập theo filter chain.

## 8. Quy trình chẩn đoán theo thứ tự

Khi annotation dường như không chạy, điều tra theo thứ tự sau để tránh sửa nhầm tầng:

### Bước 1 — Xác nhận request thực sự đến method

- Ghi nhận controller route, HTTP status, authorization filter rule khớp và log an toàn tại đầu method (không log secret).
- Nếu request bị chặn trước controller, lỗi hiện tại có thể nằm ở `authorizeExchange`, filter authentication, exception handler hoặc CSRF, chưa liên quan tới `@PreAuthorize` của service.
- Nếu request bypass gateway/đi qua entry point khác, xem lại mọi security chain và đường gọi internal/batch.
- Tách một service integration test để gọi protected bean trực tiếp; so sánh kết quả với HTTP test.

### Bước 2 — Kiểm tra annotation và cấu hình kích hoạt

- Đã có `@EnableReactiveMethodSecurity` trong Spring application context tương ứng chưa?
- Annotated class có thực sự là Spring bean, được component scan/`@Bean` tạo không, hay một nơi nào đó dùng `new`?
- Method trả `Mono`/`Flux` đúng hợp đồng reactive Java? Annotated method là public, non-final và không bị thiết kế proxy loại bỏ?
- Có bật đúng loại annotation (`@PreAuthorize`, `@Secured`, `@RolesAllowed`) với lựa chọn thích hợp không?
- Khi dùng Spring test slice như `@WebFluxTest`, có đưa configuration/service/advisor thật vào context test không? Test quá hẹp có thể không giống production.

### Bước 3 — Xác minh proxy tại caller

Trong test hoặc công cụ chẩn đoán nội bộ:

```java
import org.springframework.aop.support.AopUtils;

Object bean = applicationContext.getBean(ProtectedReportService.class);
boolean proxied = AopUtils.isAopProxy(bean);
Class<?> targetType = AopUtils.getTargetClass(bean);
```

Đây là **mã minh họa** đặt trong test/bean đã có `applicationContext`, không phải một chương trình Java độc lập. `proxied == false` là manh mối rất mạnh nếu class lẽ ra cần method security; `proxied == true` chỉ chứng minh bean có proxy, **chưa** chứng minh advisor cho annotation cụ thể đã chạy trên lời gọi bạn đang xét. Kiểm tra caller có giữ bean Spring-injected hay đối tượng mới tạo; nếu caller là method cùng class, tìm `this.secured(...)` và lời gọi không ghi `this`.

Khi nhiều loại advice cùng tồn tại, có thể kiểm tra advisor chain bằng diagnostics AOP phù hợp. Nhưng đừng biến việc in tên proxy thành một phép kiểm tra “an toàn” duy nhất; **behavior test** theo role mới xác nhận chính sách.

### Bước 4 — Quan sát authentication trong Reactor Context

- Với WebFlux, biết cơ chế authentication (Basic, Bearer token, OAuth2 Login, session) đang tạo principal nào và authority nào.
- Có gọi `.subscribe()` thủ công bên trong service không? Một chuỗi độc lập có thể chạy ngoài security context mong đợi.
- Có tạo publisher/CompletableFuture không nối với Reactor subscription của request hay dùng `SecurityContextHolder` ThreadLocal từ code Servlet không?
- Với gọi không phát sinh từ HTTP (messaging, scheduled jobs, CLI, tests), cần mô hình danh tính kỹ thuật riêng; không tự thêm “admin” mặc định.
- Một request chuyển scheduler không nhất thiết mất context: kiểm tra pipeline thật bằng `ReactiveSecurityContextHolder.getContext()` thay vì dựa vào ThreadLocal/MDC.

### Bước 5 — Kiểm tra quyền, expression và xử lý lỗi

- `hasRole('ADMIN')` tìm authority `ROLE_ADMIN`. `hasAuthority('ADMIN')` tìm chính xác authority `ADMIN`. Chỉ có scope `SCOPE_admin` không đồng nghĩa có `ROLE_ADMIN`.
- Nếu dùng tên tham số trong SpEL, ví dụ `#ownerId`, xác minh parameter name metadata (`-parameters`), `@P` hoặc cách trích xuất tên tham số đang dùng; biểu thức sai có thể phát lỗi thay vì cho phép.
- Nếu có `@PreAuthorize` trên interface, class và override, kiểm tra annotation thực tế được Spring nhận và tránh các annotation xung đột.
- Một `AccessDeniedException` có thể bị code khác `onErrorResume` nuốt và đổi thành HTTP 200: đó là **xử lý lỗi nguy hiểm**, không phải bằng chứng advice đã không chạy.
- Trường hợp `@PostAuthorize` kiểm tra **sau** khi method được gọi, không thay thế kiểm tra trước một hành động có side effect. Với tác vụ ghi/xóa, nên dùng `@PreAuthorize` hoặc kiểm tra quyền trước side effect theo thiết kế.
- Nếu code đang dùng legacy reactive method security config từ Spring Security cũ, kiểm tra migration sang `AuthorizationManager` và các default bật annotation.

### Bước 6 — Thêm log tạm thời và giữ bí mật

Có thể bật log phù hợp trong môi trường kiểm soát:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.authorization: TRACE
    org.springframework.aop: DEBUG
```

Log mức TRACE có thể rất nhiều và có thể chứa chi tiết về đánh giá quyền; chỉ dùng trong môi trường được phép, có thời hạn và loại bỏ dữ liệu nhạy cảm. Không log password, access token, Authorization header, nguyên bản JWT hoặc dữ liệu người dùng để “chứng minh” context. Tập trung vào tên method, loại principal đã giảm nhạy cảm, tập authority cần thiết, rule được xét, outcome và correlation ID.

## 9. Cách sửa nào phù hợp?

**Ưu tiên tách bean (như `ReportFacade -> ProtectedReportService`):** Dễ đọc, dễ test, không phụ thuộc việc expose proxy. Chức năng bảo vệ trở thành ranh giới dịch vụ rõ ràng; các caller khác cũng phải đi qua bean bảo vệ. Tách code không có nghĩa mọi nghiệp vụ tự an toàn: phải khảo sát cả các đường gọi khác có thể đi trực tiếp vào implementation hoặc data repository mà không qua policy.

**Self injection / inject proxy của chính bean:** Có thể dùng reference đã được Spring inject (thường qua lazy/provider thích hợp) rồi gọi method bảo vệ trên reference proxy. Tuy nhiên dễ tạo vòng dependency/cấu hình khó hiểu; cần test rõ ràng. Không thay thế bằng `this.secured()`.

**`AopContext.currentProxy()`:** Spring Framework có hỗ trợ khi cấu hình expose proxy, nhưng gắn code nghiệp vụ trực tiếp với hạ tầng AOP và dễ làm test khó hơn. Không chọn làm giải pháp mặc định cho lỗi này.

**AspectJ weaving:** Khác AOP proxy, compile-time/load-time weaving có thể xử lý self-invocation vì advice gắn vào bytecode. Đây là thay đổi kiến trúc/build/runtime với yêu cầu kiểm thử và tương thích riêng, không thể chỉ đổi một property rồi mặc định mọi security advisor reactive hoạt động như cũ. Với code học tập và phần lớn service WebFlux, tách bean là giải pháp an toàn, đơn giản nhất.

**Không nên “sửa” bằng:** xóa `@PreAuthorize`, bọc `AccessDeniedException` bằng `onErrorResume(e -> Mono.just(secret))`, thêm `permitAll` ở HTTP layer, gán mặc định `ROLE_ADMIN` hoặc tự tạo `SecurityContext` có toàn quyền cho request chưa xác thực. Những cách này làm mất hàng rào bảo mật và che giấu nguyên nhân.

## 10. Các lỗi thường gặp khi chuyển từ Servlet sang WebFlux

| Nhận định sai | Thực tế và cách khắc phục |
| --- | --- |
| Đã bật `@EnableWebFluxSecurity` nghĩa là `@PreAuthorize` sẽ chạy | Bật riêng `@EnableReactiveMethodSecurity` |
| Dùng `@EnableMethodSecurity` từ ví dụ MVC là tương đương | Kiểm tra cấu hình reactive đúng với Reactor SecurityContext và interceptor |
| Lớp có `@Service` thì `this.secured()` vẫn qua proxy | Self-invocation gọi target trực tiếp, bypass advice |
| Chỉ cần `AopUtils.isAopProxy(bean)` là đủ | Proxy có thể tồn tại nhưng inner call không đi qua nó |
| Code chuyển `Mono.just(...)` thành `Mono.defer(...)` sẽ sửa self-invocation | Reactive laziness không đổi reference `this` |
| `Mono` chưa subscribe mà không có exception tức là được phép | Subscribe qua `StepVerifier` hoặc `WebTestClient` |
| `SecurityContextHolder.getContext()` luôn đúng trong WebFlux | Reactive SecurityContext được truyền bằng Reactor `Context` |
| `publishOn` luôn làm mất security context | Reactor Context có cơ chế propagate theo subscription; cần kiểm chứng chỗ tách pipeline |
| Method `private`/`final` luôn được AOP advice | Subclass proxy không intercept được các method này; xem loại proxy |
| `hasRole('ADMIN')` tương đương `hasAuthority('ADMIN')` | `hasRole` thường đòi authority `ROLE_ADMIN` |
| HTTP 403 chứng minh method annotation chạy | HTTP authorization có thể chặn trước khi tới service |
| `@PostAuthorize` có thể ngăn side effect trong method | Hành động có thể đã được thực hiện; dùng pre-authorization cho thao tác nhạy cảm |
| Inject bean vòng vào chính nó là cách sửa tốt nhất | Tách secured method sang bean riêng thường rõ ràng và dễ kiểm thử hơn |

## 11. Checklist QA cho một bug bảo mật ở method

Một bản sửa chỉ nên được chấp nhận khi:

1. Method được bảo vệ thực sự thuộc Spring-managed bean trong application context đang phục vụ request; method/interceptor reactive đúng phiên bản và đúng kiểu proxy.
2. Mọi caller của thao tác nhạy cảm **đều** đi qua điểm vào có authorization; không còn `this.method()`, new instance hoặc shortcut khác bypass chính sách.
3. Test phân quyền đối với **anonymous**, tài khoản thiếu quyền và tài khoản đủ quyền; xác nhận kết quả ở **service method** và ít nhất một đường HTTP.
4. Test đã subscribe vào `Mono`/`Flux`; nếu ngoài HTTP có cấp `ReactiveSecurityContextHolder` đúng cách, không mặc định ThreadLocal chứa identity.
5. 401/403 được tạo theo đúng chính sách và không bị handler tùy chỉnh nuốt thành “success”; HTTP routing rule không vô tình che lỗi method security.
6. Không dùng `final`/`private` method như nơi duy nhất đặt annotation khi proxy không thể advice; không để thiếu matcher/đăng ký annotation mà app vẫn chạy bình thường.
7. Khi refactor service, review các đường gọi khác, side effect và thứ tự kiểm tra quyền; tuyệt đối không thêm quyền mặc định rộng hơn để làm test xanh.

## 12. Tóm tắt cơ chế để tự gỡ lỗi

`@PreAuthorize` ở WebFlux chỉ phát huy khi method security reactive được bật, method phù hợp và lời gọi đi qua Spring AOP proxy trong một Reactor subscription có SecurityContext thích hợp. **Self-invocation** là trường hợp dễ đánh lừa nhất: bean đã có proxy, annotation vẫn hợp lệ nhưng `this.method()` bên trong bean bỏ qua interceptor. Sửa bằng cách **tách phương thức bảo vệ sang bean khác và inject bean đó**, kiểm tra anonymous/USER/ADMIN ở service và HTTP, rồi xác minh mọi caller đều dùng đường đi đã được bảo vệ.

### Tài liệu chính thức

- Spring Security 6.3 – Reactive Method Security (EnableReactiveMethodSecurity, AuthorizationManager, Reactor Context): https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security – Reactive Method Security (tài liệu bản mới, đối chiếu phiên bản khi áp dụng): https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security – Reactive Testing Authentication: https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html
- Spring Framework – AOP Proxying Mechanisms và Self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Reactor – Adding a Context to a Reactive Sequence: https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html
- Spring Security – Reactive Web Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html