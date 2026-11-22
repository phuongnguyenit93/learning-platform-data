# Kích hoạt @EnableReactiveMethodSecurity theo phiên bản Spring Security

## 1. Vấn đề: HTTP đã bảo vệ nhưng method vẫn có thể không được bảo vệ

Một ứng dụng WebFlux có `SecurityWebFilterChain`, cấu hình OAuth2 Resource Server hoặc HTTP Basic, và endpoint yêu cầu xác thực. Developer gắn `@PreAuthorize("hasAuthority('DOC_READ')")` lên phương thức service, nhưng một người không có `DOC_READ` vẫn đọc được tài liệu. Nguyên nhân có thể rất đơn giản: **chưa kích hoạt reactive method security**, đã dùng nhầm annotation dành cho Servlet, hoặc gọi service mà không đi qua Spring AOP proxy.

Spring Security tách hai biên giới:

- **HTTP reactive security**: `@EnableWebFluxSecurity` / auto-configuration, `ServerHttpSecurity.authorizeExchange` và `SecurityWebFilterChain` quyết định ai được gọi URL.
- **Reactive method security**: `@EnableReactiveMethodSecurity` cài các interceptor cho `@PreAuthorize`, `@PostAuthorize` và các method-level policies trên Spring-managed beans.

Bật tầng HTTP **không tự chứng minh** tầng method đã bật; Spring Boot Security starter không tự kích hoạt mọi annotation method security. Ngược lại, bật method security không có nghĩa tất cả đường HTTP đều được cấu hình chống truy cập trái phép. Cần dùng cả hai và kiểm thử từng biên giới.

Mục tiêu bài này:

1. Nhận diện cách bật `@EnableReactiveMethodSecurity` trên Spring Security 5.0–5.7, 5.8, 6.x và 7.x.
2. Hiểu `useAuthorizationManager` và vì sao **giá trị mặc định đổi ở 6.0**.
3. Viết cấu hình WebFlux đúng, service trả `Mono`/`Flux` và chạy qua Spring AOP proxy.
4. Tách rõ `@EnableReactiveMethodSecurity` với `@EnableMethodSecurity` và `@EnableWebFluxSecurity`.
5. Viết test `StepVerifier`/`WebTestClient` chứng minh phép kiểm tra quyền thật sự chạy, cả khi thiếu quyền.
6. Chẩn đoán sai phiên bản, dependency, Reactor Context, self-invocation, test mock, blocking và phương thức không phù hợp.

## 2. Kiến trúc Reactive Method Security

```text
Client
  |
  v
WebFlux HTTP SecurityWebFilterChain
  |  Authentication + HTTP authorization
  v
@Controller / @RestController
  |
  v
Spring AOP proxy cho service bean
  |
  +-- @PreAuthorize / custom reactive authorization interceptor
  |       |
  |       v
  |    Reactor Context -> Authentication
  |       |
  |       +--> DENY: AccessDeniedException (không đi tiếp)
  |       |
  |       +--> GRANT: subscribe/tiếp tục Publisher
  |
  v
@Service method -> Mono<T> / Flux<T>
  |
  +-- (nếu có) @PostAuthorize / @PostFilter
  v
Reactive repository / response
```

Spring Security reactive lấy security context từ **Reactor Context**, thông qua `ReactiveSecurityContextHolder`. Một method security expression có thể dùng `authentication`, `principal`, `hasRole(...)`, `hasAuthority(...)` hoặc bean policy được công bố đúng cách.

Những lưu ý:

- `ReactiveSecurityContextHolder` không đơn thuần đọc ThreadLocal hiện hành. Reactive chain có thể đổi thread nên không thể dựa vào `SecurityContextHolder.getContext()` kiểu servlet.
- Spring AOP proxy phải thực sự được gọi. Nếu controller tự `new SomeService()` hoặc một method trong cùng bean gọi `this.protectedMethod()`, interceptor có thể không được áp dụng.
- Các method bảo vệ bằng reactive annotations nên có return type thuộc `org.reactivestreams.Publisher`, phổ biến là `Mono<T>` hoặc `Flux<T>`. Kotlin coroutines được hỗ trợ trên nhánh AuthorizationManager tương ứng.
- Một service trả `Mono` nhưng tự `block()` để lấy dữ liệu trước guard có thể làm sai thiết kế không chặn; giữ policy và repository trong reactive pipeline.
- Phân quyền trên method chỉ bảo vệ những method thật sự được match và gọi qua proxy; nó không tự thêm `tenant_id` vào SQL.

## 3. Bảng phiên bản: khác biệt quan trọng nhất

| Spring Security | Cách bật reactive method security | `useAuthorizationManager` mặc định | Gợi ý |
| --- | --- | --- | --- |
| 5.0–5.7 | `@EnableReactiveMethodSecurity` | Chưa có thuộc tính mới này | Dùng legacy infrastructure, đọc tài liệu đúng minor version |
| **5.8.x** | `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` | **false** | Chủ động bật cơ chế mới khi chuẩn bị nâng 6.x |
| **6.0–6.5.x** | `@EnableReactiveMethodSecurity` | **true** | Không cần ghi `useAuthorizationManager = true` |
| **7.0.x** | `@EnableReactiveMethodSecurity` | **true** | Vẫn có thuộc tính này theo JavaDoc 7.0; xác minh API cụ thể khi nâng |
| 7.1+ | Kiểm tra JavaDoc của phiên bản được khóa trong build | Không dựa trên mẹo của 5.8 | Ưu tiên cấu hình mặc định AuthorizationManager nếu JavaDoc xác nhận |

**Căn cứ:** JavaDoc Spring Security 5.8.16 ghi `useAuthorizationManager` có mặc định `false`. JavaDoc 6.5.11 và 7.0.8 ghi mặc định `true`. Hướng dẫn migration reactive 6.0 nói có thể bỏ `useAuthorizationManager = true` khi nâng từ 5.8 sang 6.0.

Đừng suy ra Spring Security version chỉ từ tên Spring Boot hoặc JDK. Đọc dependency tree/BOM thực tế của dự án. Spring Boot 2.x thông thường đi với Security 5.x, Boot 3.x với Security 6.x, Boot 4.x với Security 7.x; nếu dự án override versions, phải kiểm tra tương thích.

### Quy tắc chọn nhanh

- **Đang ở 5.8 và muốn dùng AuthorizationManager mới**: ghi rõ `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`.
- **Đang ở 6.x**: dùng `@EnableReactiveMethodSecurity`; `true` là mặc định.
- **Đang ở 7.x đã kiểm chứng JavaDoc**: dùng `@EnableReactiveMethodSecurity` theo phiên bản đó; tránh giữ cấu hình legacy `false` trừ khi có lý do và dependency tương ứng.
- **Đang ở 5.7 trở xuống**: không copy cú pháp `useAuthorizationManager` vì có thể không biên dịch; nâng lên 5.8 trước nếu muốn đi theo lộ trình đổi infrastructure.

Nếu một dự án dùng Security 5.8 nhưng chỉ đặt `@EnableReactiveMethodSecurity`, annotation vẫn bật method security **theo kiểu legacy mặc định**, không phải “tắt method security”. Hãy phân biệt **method security đang bật** với **engine được dùng để thực thi nó**.

## 4. Vì sao Spring Security 5.8 có hai cơ chế?

Trong 5.8, nhóm dự án Spring Security chuẩn bị thay đổi cơ chế method authorization. Legacy path dựa nhiều hơn trên metadata sources, config attributes, AccessDecisionManager/voters. Cơ chế mới dùng `ReactiveAuthorizationManager`, interceptors và Spring AOP.

```java
// Spring Security 5.8: bật engine mới tường minh.
@Configuration
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
class ReactiveMethodSecurityConfig {
}
```

Những lợi ích của nhánh AuthorizationManager trong tài liệu chính thức:

- API `AuthorizationManager`/`ReactiveAuthorizationManager` gọn hơn cho việc compose và customize.
- Hỗ trợ giá trị reactive ở biểu thức khi dùng đúng contract, bao gồm bean trả `Mono<Boolean>`.
- Dùng các thành phần Spring AOP thông thường thay cho nhiều abstraction legacy.
- Có kiểm tra xung đột annotations và hỗ trợ tiêu chuẩn tương ứng của framework.
- Cải thiện đường chuyển sang 6.x khi mặc định đổi sang `true`.

### Cấu hình mặc định 5.8 nếu không ghi cờ

```java
// Spring Security 5.8: bật reactive method security legacy.
@Configuration
@EnableReactiveMethodSecurity
class LegacyReactiveMethodSecurityConfig {
}
```

Vẫn có thể thực thi `@PreAuthorize` trên các reactive beans, nhưng extension points/hành vi cụ thể không nhất thiết giống nhánh AuthorizationManager. Đừng coi sự kiện “test với @PreAuthorize xanh” là bằng chứng đã dùng engine mới; cần kiểm tra annotation parameter và/hoặc beans infrastructure.

### Khi nâng từ 5.8 sang 6.x

```diff
- @EnableReactiveMethodSecurity(useAuthorizationManager = true)
+ @EnableReactiveMethodSecurity
```

Dòng thay đổi trên là **một bước dọn cấu hình**, không phải yêu cầu bắt buộc để code chạy. Với 6.x, ghi `true` vẫn có ý nghĩa nếu thuộc tính còn tồn tại, nhưng không cần thiết. Quan trọng hơn là chạy regression tests method security sau khi đổi defaults.

## 5. Cấu hình Spring Security 6.x (và 7.x tương ứng)

Mẫu gọn:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Java cho phép import xuống dòng **sau dấu chấm** nếu cú pháp phân tách hợp lệ, nhưng để tránh copy-paste lỗi, có thể viết một dòng:

```java
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
```

Đặt annotation lên một class nằm trong Spring application context: `@Configuration` được component scan hoặc `@Import`. Đặt nó lên một class ở package không được scan thì có thể **không kích hoạt gì**.

Không cần đặt `@EnableReactiveMethodSecurity` trên từng `@Service`. Nó là annotation cấu hình chung để tạo các interceptors.

### Không nhầm với @EnableMethodSecurity

```java
// Servlet/synchronous method security; không tự thay thế reactive setup.
@EnableMethodSecurity

// Reactive method security, có Reactor Context.
@EnableReactiveMethodSecurity

// HTTP WebFlux security configuration; không tự kích hoạt method-level.
@EnableWebFluxSecurity
```

`@EnableMethodSecurity` dành cho đường method authorization thông thường, còn `@EnableReactiveMethodSecurity` dùng với reactive services. Trên một ứng dụng thuần WebFlux, hãy ưu tiên annotation reactive khi bảo vệ service trả `Mono`/`Flux`.

### Không tự suy diễn thuộc tính

JavaDoc `@EnableReactiveMethodSecurity` 6.5/7.0 có `proxyTargetClass`, `mode`, `order`, `useAuthorizationManager`. Không copy nguyên attributes `prePostEnabled`, `securedEnabled`, `jsr250Enabled` từ `@EnableMethodSecurity` vì chúng thuộc **annotation khác**, không phải những thuộc tính chung mặc định.

Ví dụ **không biên dịch** (phản ví dụ):

```java
// SAI: @EnableReactiveMethodSecurity không có prePostEnabled như trên.
@EnableReactiveMethodSecurity(prePostEnabled = true)
```

Kiểm tra chữ ký annotation đúng phiên bản qua IDE/Javadoc, không dựa vào một ví dụ servlet.

## 6. Phân biệt HTTP security và reactive method security

WebFlux HTTP:

```java
@Configuration
@EnableWebFluxSecurity
class ReactiveHttpSecurityConfig {

    @Bean
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/**").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **snippet tích hợp**, cần imports `Bean`, `Configuration`, `EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `Customizer`. Nó chỉ yêu cầu authenticated cho `/api/**`; **không** đòi DOC_READ tại HTTP layer.

Service:

```java
@Service
class DocumentService {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<String> readDocument(long id) {
        return Mono.just("document " + id);
    }
}
```

Khi `@EnableReactiveMethodSecurity` được bật, người authenticated nhưng thiếu `DOC_READ` phải bị chặn ở **service layer**. Đây là cách test rõ ràng rằng annotation method đang hoạt động.

Nếu HTTP đã dùng `.pathMatchers("/api/**").hasAuthority("DOC_READ")` thì một test unauthorized chỉ chứng minh HTTP guard hoạt động; nó **không chứng minh method security đã kích hoạt**. Hãy có ít nhất một test trong đó HTTP layer cho qua authenticated user, nhưng method layer từ chối.

## 7. Dependency và tương thích với Spring Boot

Một ứng dụng thực cần:

- Spring Boot WebFlux starter cho nonblocking HTTP server.
- Spring Security starter/core/config/web cho authentication/authorization.
- Reactor và Spring AOP infrastructure; security method interception hoạt động qua Spring-managed proxy.
- Starter test và reactor-test để kiểm thử với `WebTestClient` và `StepVerifier`.
- Nếu dùng JWT Resource Server: `spring-boot-starter-oauth2-resource-server` và issuer/audience configuration đáng tin.

Spring Boot BOM nên quản lý Spring Security, Reactor và Spring Framework cùng một bộ phiên bản tương thích. Đừng tự ép `spring-security-config` 7.x vào Spring Boot 3.x đang dùng Framework 6.x hoặc trộn Reactor major versions khi chưa kiểm chứng.

### Maven dependency tree

```bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework:spring-aop
mvn dependency:tree -Dincludes=io.projectreactor
```

Xác nhận kết quả thực tế trước khi chọn cách kích hoạt. Nếu project Gradle, dùng `./gradlew dependencies --configuration runtimeClasspath` hoặc `dependencyInsight` với module cụ thể.

### Spring Boot 3.x và 4.x

Spring Boot 3.x/Spring Security 6.x và Boot 4.x/Spring Security 7.x đều yêu cầu Java hiện đại; Boot 4.0 migration guide nêu Java 17 trở lên và Spring Framework 7.x. Tài liệu này dùng **Java 17** cho ví dụ Boot 3.5.x vì dễ học và kiểm thử. Với Boot 4.x, cần dùng dependency management và phiên bản plugins do Boot 4 BOM tương ứng cung cấp; không khẳng định pom Boot 3.5 là pom cho Boot 4.

### Không thử “sửa” bằng cách thêm cả hai annotations

```java
// Tránh đăng ký hai kiểu method security cho cùng logic nếu không có
// thiết kế rõ ràng; có thể gây interceptors trùng/khó dự đoán.
@EnableMethodSecurity
@EnableReactiveMethodSecurity
```

Trong một ứng dụng hỗn hợp có cả synchronous và reactive services, cần thiết kế rõ mỗi nhóm được bảo vệ qua interceptors nào, thứ tự thế nào và có tests; không thêm cả hai chỉ để một test bất kỳ hết 403.

## 8. Ví dụ runnable: ứng dụng Spring Boot WebFlux + Reactive Method Security

Dự án dưới đây minh họa một tình huống dễ kiểm chứng:

- HTTP filter chain yêu cầu **chỉ authenticated** cho `/api/**`.
- Method `DocumentService.read` yêu cầu **authority chính xác DOC_READ**.
- Method `DocumentService.audit` yêu cầu `ROLE_ADMIN` qua `hasRole('ADMIN')`.
- User `reader` đọc được document nhưng không xem audit.
- User `viewer` đăng nhập được nhưng bị method-level deny khi đọc.
- User `admin` xem được audit nhưng **không tự có DOC_READ**.
- Request không có credentials nhận 401 tại HTTP layer.

Project dùng Spring Boot **3.5.16**, Java 17 và Spring Security do BOM quản lý. Version này là một **ví dụ khóa phiên bản của nhánh 3.5**; với dự án thực, dùng maintenance version đang được hỗ trợ và cập nhật đồng bộ.

```text
reactive-method-security-lab/
├── pom.xml
└── src/
    ├── main/java/demo/reactive/
    │   ├── ReactiveMethodSecurityLab.java
    │   ├── DocumentService.java
    │   └── DocumentController.java
    └── test/java/demo/reactive/
        └── ReactiveMethodSecurityLabTest.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-method-security-lab</artifactId>
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
</project>
```

Không cần Servlet MVC starter trong project này. Không hardcode Spring Security 6.x riêng trong pom vì Boot parent đã cung cấp dependency management tương thích.

### 8.2. ReactiveMethodSecurityLab.java

```java
package demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityLab {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveMethodSecurityLab.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchange -> exchange
                    .pathMatchers(HttpMethod.GET, "/api/**").authenticated()
                    .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}pass")
                .authorities("DOC_READ")
                .build();

        UserDetails viewer = User.withUsername("viewer")
                .password("{noop}pass")
                .roles("VIEWER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}pass")
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(reader, viewer, admin);
    }
}
```

**Giải thích:**

- `@SpringBootApplication` đồng thời là một cấu hình Spring; `@EnableReactiveMethodSecurity` ở đây đăng ký method security cho các beans được scan trong package `demo.reactive`.
- `@EnableWebFluxSecurity` bật WebFlux security theo cấu hình rõ ràng; còn `@EnableReactiveMethodSecurity` bật annotation method.
- Filter chain chỉ yêu cầu authenticated cho GET `/api/**`, nên test viewer bị 403 sẽ chứng minh layer service.
- `{noop}pass` chỉ dành cho môi trường demo/test; production phải hash mật khẩu an toàn và cấu hình users/IdP thật.
- `.anyExchange().denyAll()` tránh vô tình cho mọi HTTP route còn lại.
- `hasAuthority('DOC_READ')` khớp chính xác DOC_READ; `roles("ADMIN")` tạo authority `ROLE_ADMIN` nên `hasRole('ADMIN')` thành công.

### 8.3. DocumentService.java

```java
package demo.reactive;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('DOC_READ')")
    public Mono<DocumentView> read(String id) {
        return Mono.just(new DocumentView(id, "Document " + id));
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> audit() {
        return Mono.just("audit-ready");
    }

    public record DocumentView(String id, String title) {
    }
}
```

`Mono` là publisher sẽ được WebFlux subscribe. Trong ứng dụng thực, logic này thường dùng `Mono.defer` hoặc reactive repository, có thể có access checks theo document ID, tenant và ownership. `@PreAuthorize("hasAuthority('DOC_READ')")` chỉ kiểm tra một **authority chức năng**; nó không tự kiểm tra quyền đối với từng ID.

### 8.4. DocumentController.java

```java
package demo.reactive;

import demo.reactive.DocumentService.DocumentView;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/documents/{id}")
    public Mono<DocumentView> document(@PathVariable String id) {
        return service.read(id);
    }

    @GetMapping("/audit")
    public Mono<String> audit() {
        return service.audit();
    }
}
```

Controller nhận **Spring-managed bean** qua constructor. Không tạo `new DocumentService()` vì như vậy bỏ qua proxy. `@PathVariable` ở đây chỉ quyết định ID để minh họa; code production cần validate và ràng buộc query theo tenant/resource.

### 8.5. ReactiveMethodSecurityLabTest.java

```java
package demo.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveMethodSecurityLabTest {

    @Autowired
    WebTestClient web;

    @Test
    void readerWithDocReadCanReadDocument() {
        web.get()
            .uri("/api/documents/42")
            .headers(headers -> headers.setBasicAuth("reader", "pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("42")
            .jsonPath("$.title").isEqualTo("Document 42");
    }

    @Test
    void viewerIsAuthenticatedButMethodDeniesDocRead() {
        web.get()
            .uri("/api/documents/42")
            .headers(headers -> headers.setBasicAuth("viewer", "pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void anonymousRequestIsRejectedAtHttpBoundary() {
        web.get()
            .uri("/api/documents/42")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void adminRoleCanCallAuditMethod() {
        web.get()
            .uri("/api/audit")
            .headers(headers -> headers.setBasicAuth("admin", "pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("audit-ready");
    }

    @Test
    void readerCannotCallAdminAuditMethod() {
        web.get()
            .uri("/api/audit")
            .headers(headers -> headers.setBasicAuth("reader", "pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleDoesNotImplicitlyHaveDocReadAuthority() {
        web.get()
            .uri("/api/documents/42")
            .headers(headers -> headers.setBasicAuth("admin", "pass"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Ý nghĩa từng nhóm test:**

- `readerCanRead`: cấu hình chạy được cho một authority đúng.
- `viewerIsAuthenticatedButMethodDeniesDocRead`: HTTP chỉ cần authenticated, nên 403 chứng minh method-level check.
- `anonymousRequestIsRejectedAtHttpBoundary`: HTTP filter yêu cầu authenticated.
- `adminRoleCanCallAuditMethod`: `hasRole('ADMIN')` khớp `ROLE_ADMIN`.
- `readerCannotCallAdminAuditMethod`: role và authority không bị trộn.
- `adminRoleDoesNotImplicitlyHaveDocReadAuthority`: admin role không tự bypass một `hasAuthority('DOC_READ')` trừ khi có role hierarchy/policy bổ sung.

Đây là **sáu test integration**. Chạy chúng để xác nhận cả proxy registration và Reactor Context thực tế. Nếu xóa `@EnableReactiveMethodSecurity` rồi chạy lại, các test 403 ở method layer phải thất bại—đó là một negative control có ích, không phải thao tác thực hiện trên hệ thống production.

### 8.6. Chạy dự án

```bash
mvn clean test
mvn spring-boot:run
```

Khi server đã chạy ở `localhost:8080`, thử:

```bash
curl -i -u reader:pass http://localhost:8080/api/documents/42
curl -i -u viewer:pass http://localhost:8080/api/documents/42
curl -i -u admin:pass  http://localhost:8080/api/audit
curl -i http://localhost:8080/api/documents/42
```

Kết quả dự kiến:

| Lời gọi | HTTP | Nội dung đáng chú ý |
| --- | --- | --- |
| reader GET document | 200 | JSON `{"id":"42","title":"Document 42"}` |
| viewer GET document | 403 | Không trả JSON tài liệu |
| admin GET audit | 200 | Body `audit-ready` |
| anonymous GET document | 401 | Không có tài liệu |

Với `curl`, header/body thực tế và error response phụ thuộc Spring Boot/Spring Security version, nên không cam kết bytes chi tiết của header. Bộ code trên được thiết kế để chạy với Java 17, nhưng **Maven tests chưa được thực thi trong lúc soạn bài**; nếu dependency artifact/version khác ở môi trường dự án, phải dùng phiên bản tương thích và chạy tests.

## 9. Trực tiếp kiểm tra Reactor Context bằng StepVerifier

Tài liệu chính thức cho biết `ReactiveSecurityContextHolder` làm việc với Reactor Context. Trong WebFlux, Spring Security dựng context theo authentication của request; trong unit test không có HTTP cần tạo nó có chủ đích.

```java
Authentication auth = new TestingAuthenticationToken(
        "alice", "n/a", "DOC_READ");

Mono<String> currentUser = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);

StepVerifier.create(currentUser
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth)))
        .expectNext("alice")
        .verifyComplete();
```

Đây là **snippet unit test**, cần imports `Authentication`, `TestingAuthenticationToken`, `ReactiveSecurityContextHolder`, `SecurityContext`, `Mono` và `StepVerifier`. Nó xác minh việc mang Authentication trong reactive subscription, **không chứng minh @PreAuthorize đã bật**. Kiểm tra method security thật bằng cách inject protected service bean rồi subscribe với user có/không có quyền.

Ví dụ:

```java
Mono<DocumentService.DocumentView> actual = service.read("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth));

StepVerifier.create(actual)
        .expectNextMatches(view -> view.id().equals("42"))
        .verifyComplete();
```

`service` trong snippet phải là **Spring-managed proxied bean** và cấu hình có `@EnableReactiveMethodSecurity`. Nếu chỉ `new DocumentService()`, test này có thể cho phép user không có authority mà không chứng minh lỗi framework—vì đã bypass proxy.

### Test DENY

```java
Authentication viewer = new TestingAuthenticationToken(
        "viewer", "n/a", "ROLE_VIEWER");

StepVerifier.create(service.read("42")
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(viewer)))
        .expectErrorMatches(error ->
            error instanceof AccessDeniedException)
        .verify();
```

Đây cũng là **snippet test tích hợp**, cần import `AccessDeniedException` và có bean service được proxy. Trong nhánh Spring Security mới hơn có thể dùng subtype riêng của AccessDeniedException; kiểm tra hierarchy theo phiên bản.

## 10. @PreAuthorize và biểu thức đồng bộ/Reactive

Ví dụ đơn giản:

```java
@PreAuthorize("hasAuthority('DOC_READ')")
public Mono<Document> read(String id) {
    return documentRepository.findById(id);
}
```

Biểu thức trả boolean, không block. Với AuthorizationManager-based reactive method security, Spring docs còn trình bày một bean policy có thể trả `Mono<Boolean>`, ví dụ:

```java
@Component("docPolicy")
class DocPolicy {

    Mono<Boolean> canRead(String id) {
        return externalPolicyClient.checkRead(id)
                .defaultIfEmpty(false)
                .onErrorReturn(false);
    }
}
```

Và:

```java
@PreAuthorize("@docPolicy.canRead(#id)")
public Mono<Document> read(String id) {
    return documentRepository.findById(id);
}
```

Hai đoạn là **snippet tích hợp**, `externalPolicyClient`/`Document`/repository phải do app cung cấp, và policy cần subject/tenant/action/resource đã xác minh để không quyết định chỉ dựa trên ID client. Đường `Mono<Boolean>` của bean policy phù hợp với cơ chế AuthorizationManager ở các versions được tài liệu xác nhận; legacy 5.7 có thể yêu cầu cách làm khác.

### Không dùng block() trong SpEL policy

```java
// SAI: có thể block event-loop và làm hỏng reactive context.
@PreAuthorize("@docPolicy.canRead(#id).block()")
```

Giữ kết quả reactive để infrastructure xử lý thay vì đồng bộ hóa bằng `block()`. Nếu policy backend timeout, một `Mono.empty()` hoặc `Mono.error()` không được hiểu là PERMIT; policy adapter/PEP phải fail closed và audit theo contract.

### Bean policy có thể dùng Authentication

Một expression có thể truyền `authentication` vào method bean:

```java
@PreAuthorize("@docPolicy.canRead(authentication, #id)")
```

Đây là hướng tốt hơn nếu quyền phụ thuộc subject/roles/tenant; policy bean phải kiểm tra input là Authentication đã được framework cung cấp và xác minh, không lấy thông tin này từ user-provided header.

## 11. @PostAuthorize, @PreFilter và @PostFilter

Nhánh AuthorizationManager của reactive method security hỗ trợ cả before- và after-method authorization; tài liệu mô tả các interceptors:

- `AuthorizationManagerBeforeReactiveMethodInterceptor.preAuthorize()`.
- `AuthorizationManagerAfterReactiveMethodInterceptor.postAuthorize()`.
- `PreFilterAuthorizationReactiveMethodInterceptor`.
- `PostFilterAuthorizationReactiveMethodInterceptor`.

Mục đích:

| Annotation | Thời điểm | Điều cần lưu ý |
| --- | --- | --- |
| `@PreAuthorize` | Trước khi method được phép thực thi | Phù hợp để chặn lời gọi theo authority/parameters |
| `@PostAuthorize` | Sau method invocation/giá trị được phát để kiểm tra | Có thể đã fetch dữ liệu; không bảo vệ side effect đã làm |
| `@PreFilter` | Lọc input collection theo policy | Không tự thay tenant policy ở repository |
| `@PostFilter` | Lọc các phần tử output theo policy | Không tự sửa SQL count/pagination/aggregations |

Ví dụ minh họa:

```java
@PostAuthorize("returnObject.ownerId == authentication.name")
public Mono<Document> loadIfOwner(String id) {
    return repository.findById(id);
}
```

Đây là **snippet tích hợp** cần model/mapper đúng và security configuration tương thích. Đối với dữ liệu nhạy cảm, nên dùng query có tenant/owner predicate **trước khi đọc** thay vì rely duy nhất vào `@PostAuthorize`, vì data fetch đã có thể xảy ra dù giá trị sau đó bị chặn.

Không sao chép ngẫu nhiên cùng một annotation trên cả class và method với quy tắc xung đột; cơ chế AuthorizationManager có thể kiểm tra ambiguity. Khi dùng annotations kết hợp, phải test logic tổng được yêu cầu, thường các guards bắt buộc cần cùng đạt.

## 12. Spring AOP proxy: khi đã bật annotation mà test vẫn không deny

Các trường hợp thường gây bypass:

### Self-invocation

```java
@Service
class ArchiveService {

    public Mono<String> outer() {
        return inner(); // this.inner(): không đi qua proxy.
    }

    @PreAuthorize("hasAuthority('ARCHIVE')")
    public Mono<String> inner() {
        return Mono.just("archived");
    }
}
```

Nếu controller gọi `outer()`, method `inner()` được gọi **bên trong cùng object** nên `@PreAuthorize` ở `inner` có thể không được áp dụng. Giải pháp: chuyển protected method sang một Spring bean khác và inject nó, hoặc thiết kế enforcement ngay entry point qua proxy; không cố vá bằng cách tự lấy proxy từ context mọi nơi.

### Tự tạo object bằng new

```java
DocumentService service = new DocumentService();
service.read("42");
```

Không có interceptor ở một instance do bạn tự tạo. Dùng dependency injection qua constructor và gọi bean.

### private/final và proxy mode

Spring AOP proxy không chặn private method như method joinpoint bên ngoài. Class/method final cũng hạn chế khả năng tạo subclass proxy; nếu dùng JDK interface proxy thì method được chặn phải đi qua interface được proxy. `@EnableReactiveMethodSecurity(proxyTargetClass = true)` yêu cầu class-based proxy khi `mode=PROXY`, nhưng **không làm private/final method bỗng trở nên interceptable**.

JavaDoc ghi thay đổi `proxyTargetClass=true` có thể ảnh hưởng **toàn bộ Spring-managed beans phải proxy**, không chỉ security. Không bật bừa để sửa một lỗi không hiểu nguyên nhân.

### Advice order và @Transactional

Method security, reactive transactions, tracing/caching có thể là những advices khác nhau. `order` giúp cấu hình thứ tự theo API phiên bản, nhưng việc mặc định như thế nào cần test trên bean thực. Nếu transaction bắt đầu sau authorization hay authorization cần đọc data trong transaction, đặt rõ yêu cầu và không suy diễn từ tên annotation.

## 13. Reactor Context, coroutine và tránh ThreadLocal trong WebFlux

Trong servlet, `SecurityContextHolder` mặc định gắn với thread. Trong WebFlux:

```java
Mono<String> name = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
```

Reactor Context đi theo **subscription**, không phải theo một thread duy nhất. Nếu xử lý chuyển từ event-loop sang `Schedulers.boundedElastic()`, đừng lấy `SecurityContextHolder.getContext()` và mong đó là identity của caller đang chạy trên một thread mới.

### Khi cần tenant context

Tenant scope do app tạo cần được resolve từ Authentication đã xác minh + server membership trước khi dùng:

```java
Mono<Document> read(String id) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(auth -> tenantPolicy.authorizedScope(auth))
            .flatMap(scope -> documentRepository
                    .findByIdAndTenant(id, scope.tenantId()));
}
```

Đây là **snippet tích hợp**, các beans/record phải do app cung cấp; nó minh họa tenant authorization ở data layer chứ không phải tự kích hoạt method security. `@PreAuthorize` kiểm tra chức năng, nhưng không tự thêm điều kiện tenant vào query.

### Kotlin coroutines

Tài liệu Spring Security mới mô tả hỗ trợ Kotlin suspend methods trên cơ chế AuthorizationManager. Không sao chép mã Kotlin `suspend fun` sang project Java 17, và không giả định legacy 5.7 có cùng hỗ trợ như 6.x. Trong Kotlin, Spring AOP cần tương thích proxy và lớp/method thường phải có khả năng được proxy (plugin all-open hoặc quy tắc tương ứng).

## 14. Đọc đúng cấu hình trong phiên bản 7.x

Nhánh Spring Security 7.x có thêm thay đổi API và dependency so với 6.x. Tuy nhiên annotation `@EnableReactiveMethodSecurity` vẫn xuất hiện trong JavaDoc 7.0, và `useAuthorizationManager` có default true theo JavaDoc 7.0.8. Vì vậy, **không tuyên bố annotation này đã bị xóa trong 7.0**.

Mẫu chính:

```java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveSecurityConfiguration {
}
```

Cảnh báo migration:

1. Đọc JavaDoc của **đúng minor** được BOM quản lý, không dựa vào bản snapshot khác.
2. Không override Spring Security modules khác major trong cùng application.
3. Tránh dùng `useAuthorizationManager=false` để giữ legacy infrastructure khi module/dependency tương ứng không còn; ở nhánh mới có thể yêu cầu `spring-security-access` hoặc một đường migration riêng.
4. Kiểm tra mọi custom extension: `ReactiveAuthorizationManager`, interceptors, expression handlers và event hooks có thể khác method signatures giữa các major.
5. Chạy integration tests chứng minh `@PreAuthorize` deny và grant sau nâng cấp.
6. Với Boot 4.x, kiểm tra hệ thống dependency/module splits theo migration guide, đặc biệt Spring Framework 7/Jakarta và Java baseline.

### Vì sao tài liệu đôi khi vẫn ghi cú pháp 5.8?

Reference guides đôi khi giới thiệu `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` trong mục kể về Spring Security 5.8 để giải thích nguồn gốc feature. Cú pháp này vẫn có thể hợp lệ ở 6.x/7.0 nhưng **không còn cần thiết** khi giá trị mặc định đã là true. Hãy ưu tiên JavaDoc default và trang migration reactive khi quyết định bật cờ.

## 15. Các extension point khi cần thay đổi cách cấp quyền

Phần lớn ứng dụng chỉ cần `@EnableReactiveMethodSecurity` với `@PreAuthorize`. Nếu chính sách cần ABAC/ACL theo document, có thể:

1. Gọi bean có method reactive trong SpEL, trả `Mono<Boolean>` và fail closed.
2. Tạo custom `ReactiveAuthorizationManager<MethodInvocation>`.
3. Đăng ký custom reactive method interceptor/pointcut với role infrastructure theo API tương ứng.
4. Cấu hình expression handler/role hierarchy bằng Spring beans phù hợp.

Ví dụ `@PreAuthorize` gọi bean:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #docId)")
public Mono<DocumentView> document(String docId) {
    return repository.findVisibleDocument(docId);
}
```

Policy bean không chỉ trả true dựa trên một `docId` caller khai. Nó phải xác minh tenant/resource và dùng policy services có deadline/failure handling hợp lệ.

### Tránh cấu hình custom interceptor trùng

Nếu bạn vừa bật các default reactive interceptors qua annotation, vừa tự công bố thêm interceptors cùng pointcut mà không xác định thứ tự, cùng method có thể bị check nhiều lần với semantics khác nhau. Không được “chữa” một lỗi 403 bằng cách bỏ qua interceptor đang deny mà chưa hiểu rule. Hãy test số lần evaluate, vị trí before/after và tất cả hành động nhạy cảm.

### Synchronous manager và reactive manager là hai contract khác nhau

Đối với WebFlux, chọn API hỗ trợ reactive decisions, chứ không gọi blocking `AuthorizationManager<MethodInvocation>` rồi `block()` bên trong event loop. Cần đúng generics `MethodInvocation` và chữ ký theo version. Không lấy một ví dụ servlet tự động chuyển thành reactive bằng cách đổi `Mono.just(...)` mà bỏ qua Context.

## 16. Chẩn đoán khi annotation có vẻ không hiệu lực

### Bước 1. Xác nhận phiên bản

Chạy:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Đọc `@EnableReactiveMethodSecurity` của đúng artifact `spring-security-config`. Với 5.8, nếu bạn cần AuthorizationManager hãy xác nhận cờ true; với 6.x mặc định true.

### Bước 2. Xác nhận configuration được scan

Class gắn `@EnableReactiveMethodSecurity` phải nằm trong context startup. Một file tồn tại trong repo nhưng ở package không được scan không kích hoạt gì. Kiểm tra `@SpringBootApplication(scanBasePackages=...)` hoặc `@Import` có đưa class đó vào context không.

### Bước 3. Xác nhận service được proxy

Method có annotation thuộc Spring bean, controller gọi bean qua constructor injection. Nếu dùng `this.method()`, private/final, tự new object, kiểm tra lại AOP.

### Bước 4. Xác nhận đúng reactive interface

Service trả `Mono`/`Flux`; WebFlux subscriber chạy với Reactive SecurityContext. Nếu method trả giá trị Java `String` thay vì Publisher trong Java reactive method security, không giả định interception an toàn theo contract tài liệu. Với Kotlin coroutines, dùng phiên bản đã hỗ trợ và kiểm tra cấu hình Kotlin AOP.

### Bước 5. Xác nhận role/authority

`hasRole('ADMIN')` thường tìm `ROLE_ADMIN`. `hasAuthority('ADMIN')` tìm chính xác `ADMIN`. Đừng tạo `roles("ADMIN")` rồi test `hasAuthority('ADMIN')` và kết luận annotation không hoạt động.

### Bước 6. Test một authenticated user không có quyền

Đây là test có giá trị hơn chỉ test user ADMIN nhận 200. Khi HTTP filter chỉ yêu cầu authenticated, method phải trả 403 nếu thiếu quyền. Không để HTTP layer cũng deny cùng authority rồi mất khả năng phân biệt nơi đã chặn.

### Bước 7. Xác nhận Context khi subscribe

`Mono` là lazy. Một caller có thể tạo Publisher trong context A nhưng subscribe trong context B. Test `StepVerifier` với `ReactiveSecurityContextHolder.withAuthentication(...)`; không capture raw Authentication trong field static hoặc cache toàn cục.

### Bước 8. Xác nhận errors và HTTP status

Thiếu/invalid auth thường 401; user authenticated thiếu quyền thường 403. Với lỗi backend policy có thể chọn 503 theo contract nhưng vẫn fail closed. Trong test trực tiếp method, thường quan sát `AccessDeniedException` thay vì HTTP status.

### Bước 9. Xác nhận object policy trong repository

Một 200 dù method security đúng vẫn có thể lộ document tenant khác nếu `@PreAuthorize` chỉ kiểm tra DOC_READ. Test resource isolation riêng, ví dụ query `findByIdAndTenant`.

## 17. Bảng lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `@PreAuthorize` không deny | Quên `@EnableReactiveMethodSecurity` | Negative integration test với viewer |
| Có annotation nhưng không proxy | Class không trong scan, tự new instance | Inspect bean/call path |
| Proxy có nhưng method nội bộ không chặn | Self-invocation qua `this` | Tách bean |
| Test WebTestClient 403 dù method annotation sai | HTTP guard đã deny trước | Test authenticated viewer trên HTTP chỉ-authenticated |
| 401 khi expected 403 | Authentication fail/missing | Header Basic/token, entry point |
| 403 khi expected 200 | Authority `DOC_READ` khác role `ROLE_DOC_READ` | In authorities và test contract |
| Spring Security 5.8 không dùng manager mới | Quên `useAuthorizationManager=true` | Kiểm tra default JavaDoc 5.8 |
| Cấu hình `prePostEnabled` không compile | Nhầm với `@EnableMethodSecurity` | Đọc annotation 6.5 JavaDoc |
| Không có Authentication trong reactive check | Lấy từ ThreadLocal hoặc Context thiếu | Test Reactor `contextWrite` |
| `Mono<Boolean>` SpEL không dùng đúng | Legacy engine/extension khác | Bật AuthorizationManager hoặc đổi adapter |
| Runtime error khi nâng Boot 4 | Trộn Security/Framework major versions | Inspect BOM/dependency tree |
| Method trả non-Publisher | Không đúng contract reactive Java | Đổi sang Mono/Flux hoặc tách synchronous |
| Policy remote timeout bị cấp quyền | Fallback `onErrorReturn(true)` | Fail closed và fault injection |
| API đúng 200 nhưng lộ tenant khác | Chỉ function-level guard | Scope ở repository/query |
| Không thấy thông tin trong HTTP error | Filter/exception mapping khác | Integration test, logs có kiểm soát |

## 18. Trình tự migration 5.8 → 6.x → 7.x

Nếu đang ở 5.8 legacy:

1. Khóa versions của BOM/Security/Framework và chạy baseline tests.
2. Thay `@EnableReactiveMethodSecurity` bằng `@EnableReactiveMethodSecurity(useAuthorizationManager=true)` trên 5.8 để chuyển engine có kiểm soát.
3. Sửa custom method-security beans/SpEL/extensions cho API AuthorizationManager nếu cần.
4. Test grant/deny, absence of authentication, Reactor Context, context switching và role prefix.
5. Nâng lên 6.x theo BOM tương thích; annotation có thể rút gọn thành `@EnableReactiveMethodSecurity`.
6. Xác minh mọi service vẫn gọi qua proxy và HTTP chain bảo vệ đúng.
7. Khi đi 7.x/Boot 4.x, xem migration guide về API, dependencies và Java baseline; không bật `useAuthorizationManager=false` để quay về legacy khi chưa có contract rõ.
8. Chạy lại các test tích hợp (đặc biệt negative paths), performance/cancellation và kiểm thử cross-tenant.

Nếu đang ở 6.x và chỉ muốn kích hoạt reactive method security, không cần thực hiện mọi bước migration trên. Thêm `@EnableReactiveMethodSecurity` vào configuration, rồi thêm negative test là con đường ngắn nhất.

### Giữ tương thích bằng tests thay vì phỏng đoán

Các docs ở nhiều phiên bản có thể giữ ví dụ từ 5.8 để giải thích lịch sử. Đừng dựa vào một trang hướng dẫn chung để suy ra default trong artifact. Mỗi lần nâng version, kiểm tra JavaDoc và tests thực thi dưới chính dependency tree sẽ cho câu trả lời chính xác hơn.

## 19. Test thiết kế đầy đủ cho production

Một bộ tests mạnh nên có:

| Case | Method / context | Kỳ vọng |
| --- | --- | --- |
| User DOC_READ | `@PreAuthorize("hasAuthority('DOC_READ')")` | PERMIT |
| User VIEWER authenticated | Cùng method | DENY |
| Anonymous caller | HTTP route authenticated | 401 |
| Admin role | `hasRole('ADMIN')` | PERMIT |
| DOC_READ chỉ có authority, không có ROLE_ADMIN | Admin method | DENY |
| ROLE_ADMIN nhưng không có DOC_READ | Read method | DENY |
| Caller trực tiếp từ Spring bean | Inject service và StepVerifier | Interceptor có hiệu lực |
| Caller tạo `new Service()` | Không có Spring proxy | Test phải phát hiện việc bypass |
| Method tự gọi nội bộ | `this.inner()` | Không coi inner advice đã chạy |
| Context thay đổi giữa thread | Reactor `publishOn` | Identity vẫn theo subscription |
| SpEL bean trả `Mono.empty()` | Không có quyết định | Không permit |
| SpEL bean trả `Mono.error` | PDP lỗi | Không permit |
| Tenant khác | Query resource có tenant mismatch | Không lộ data |
| Method trả `Flux` | Multiple items | Không phát protected items khi deny |
| Reactive after-check deny | `@PostAuthorize` | Không trả protected result |
| HTTP match public | `permitAll` | Chỉ public endpoint được phép |
| Method security disabled | Negative control trong test isolation | Viewer không còn bị chặn tại method; test phát hiện |
| Version bump | Security 5.8/6.x/7.x riêng | Cùng truth table với cấu hình tương ứng |

Trong WebFlux integration, dùng `WebTestClient` thay vì chỉ gọi controller bằng `new`. Trong unit/reactive pipeline, dùng `StepVerifier` và `contextWrite`. Với JWT, mock authentication tests không thay thế signature/issuer/audience verification tests.

**Quan trọng:** kiểm thử method-security bằng việc gọi method **thông qua proxy**; nếu chỉ mock service hoặc dùng `@MockBean` thay service thật, `@PreAuthorize` của service có thể không được thực thi.

## 20. Các lỗi phổ biến cần tránh

**1. Chỉ thêm `@PreAuthorize` mà quên `@EnableReactiveMethodSecurity`.** Annotation có thể không có hiệu lực nếu chưa đăng ký interceptor.

**2. Cho rằng `@EnableWebFluxSecurity` tự bật method security.** Nó phục vụ HTTP security.

**3. Dùng `@EnableMethodSecurity` thay reactive annotation.** Hai đường method authorization có mục tiêu khác nhau.

**4. Nói 5.8 mặc định `useAuthorizationManager=true`.** JavaDoc 5.8 ghi **false**; 6.0 mới đổi default sang true.

**5. Nói 7.0 đã xóa `@EnableReactiveMethodSecurity`.** JavaDoc 7.0 vẫn có annotation này.

**6. Copy `prePostEnabled=true` sang `@EnableReactiveMethodSecurity`.** Không phải attribute của annotation reactive trong JavaDoc nêu trên.

**7. Đọc tài liệu 6.x nhưng dùng artifact 5.7.** Cú pháp/extension points có thể không tồn tại.

**8. Tự tạo service bằng `new` hoặc gọi `this.protectedMethod()`.** Bypass proxy-based interception.

**9. Kỳ vọng private/final method được proxy bảo vệ.** AOP proxy có giới hạn.

**10. Dùng `SecurityContextHolder` thread-local trên reactive chain.** Có thể không đại diện đúng subscriber.

**11. Gọi `block()` bên trong SpEL policy/Reactive service trên event loop.** Gây nghẽn, phá nonblocking model.

**12. Test với user ADMIN duy nhất.** Không phát hiện annotation vô hiệu hoặc authority mismatch.

**13. HTTP guard cũng kiểm tra đúng authority, rồi coi 403 là bằng chứng method security.** Cần test riêng phương thức.

**14. Dùng `hasAuthority("ADMIN")` khi user chỉ có `ROLE_ADMIN`.** Tên authority phải chính xác.

**15. Dựa vào `@PostAuthorize` để ngăn tất cả dữ liệu DB bị đọc.** Nó diễn ra sau invocation; cần query scope trước.

**16. Return Mono/Flux nhưng gọi repository không scoped theo tenant.** Functional authorization không tự bảo vệ từng record.

**17. Một `Mono.empty()` policy result được coi là PERMIT.** Thiếu quyết định không phải grant, nên fail closed.

**18. Cố giữ `useAuthorizationManager=false` qua major migration khi legacy dependency không còn.** Kiểm tra đường được hỗ trợ và không trộn modules.

**19. Đặt @EnableReactiveMethodSecurity ở một class không được scan.** Annotation không được Spring khởi tạo.

**20. Không chạy regression tests sau nâng Security/Boot.** Default, custom interceptor và proxy semantics có thể khác.

## 21. Checklist kích hoạt trước khi deploy

- [ ] Đã xác minh Spring Security version thực bằng Maven/Gradle dependency report.
- [ ] Với 5.8, quyết định rõ dùng legacy (mặc định false) hay AuthorizationManager (true).
- [ ] Với 6.x/7.x theo JavaDoc, `@EnableReactiveMethodSecurity` có default manager true.
- [ ] Không dùng attributes của `@EnableMethodSecurity` nhầm sang annotation reactive.
- [ ] Cấu hình được Spring scan hoặc import trong đúng application context.
- [ ] Có `SecurityWebFilterChain` riêng cho HTTP auth và route matching.
- [ ] Service có `@PreAuthorize` là Spring bean, được gọi qua proxy.
- [ ] Phương thức Java reactive trả `Mono`/`Flux`, tránh blocking SpEL.
- [ ] Cách xử lý `ReactiveSecurityContextHolder` đúng theo Reactor subscription.
- [ ] Test authenticated nhưng thiếu quyền → 403 tại method level.
- [ ] Test anonymous → 401 ở HTTP layer.
- [ ] Test hasAuthority và hasRole với đúng prefix `ROLE_`.
- [ ] Test behavior khi policy bean empty/error/timeout, không fail open.
- [ ] Test self-invocation/final/private nếu kiến trúc có các trường hợp này.
- [ ] Test resource ID/tenant/owner và query-level authorization riêng.
- [ ] Test HTTP/method integration sau mỗi lần nâng BOM/Security major version.
- [ ] Không dùng quyền “ADMIN mặc định vượt mọi policy” khi không có contract.
- [ ] Audit denied decisions mà không log credentials/secret token.

**Kết luận:** `@EnableReactiveMethodSecurity` là bước kích hoạt phương thức phân quyền trong ứng dụng WebFlux. Sự khác biệt phiên bản quan trọng là **5.8 có `useAuthorizationManager` nhưng mặc định false**, còn **6.x và JavaDoc 7.0 mặc định true**. Kích hoạt annotation đúng mới là bước đầu: phải bảo đảm Spring-managed proxy được gọi, Reactor Context mang authentication, method trả reactive types và negative integration tests thật sự ngăn user thiếu quyền. HTTP security và method security bổ trợ nhau, không tự thay thế nhau.

## Tài liệu tham khảo chính thức

- [Spring Security 5.8.16 — EnableReactiveMethodSecurity JavaDoc](https://docs.spring.io/spring-security/site/docs/5.8.16/api/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5.11 — EnableReactiveMethodSecurity JavaDoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 7.0.8 — EnableReactiveMethodSecurity JavaDoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 7.0 — Reactive Method Security](https://docs.spring.io/spring-security/reference/7.0/reactive/authorization/method.html)
- [Spring Security — Reactive Migration Guide](https://docs.spring.io/spring-security/reference/6.5/migration/reactive.html)
- [Spring Security — WebFlux HTTP Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
