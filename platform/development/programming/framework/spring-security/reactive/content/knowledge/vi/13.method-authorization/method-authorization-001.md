# Bật @EnableReactiveMethodSecurity và lựa chọn cơ chế AuthorizationManager theo phiên bản

## 1. Mục tiêu

Trong Spring Security **reactive** (Spring WebFlux), bảo vệ URL bằng `ServerHttpSecurity.authorizeExchange(...)` là một lớp phòng vệ quan trọng, nhưng không thay thế việc kiểm tra quyền ngay tại **service method**. Một service có thể được gọi từ REST controller, GraphQL handler, message consumer, job hoặc một service khác. Nếu quyền chỉ được kiểm tra ở một URL, lời gọi đi từ đường khác có thể không chịu cùng chính sách.

Spring Security cung cấp `@EnableReactiveMethodSecurity` để bật method security gắn với **Reactor Context**, và từ nhánh 5.8 có mô hình mới dựa trên `ReactiveAuthorizationManager`. Việc dùng cấu hình nào phải dựa vào **phiên bản Spring Security thực tế**, không đơn thuần phiên bản Java hoặc một ví dụ trên blog.

Sau bài học, bạn sẽ:

1. Bật reactive method security đúng cách và phân biệt với `@EnableMethodSecurity` của Servlet.
2. Hiểu lịch sử `useAuthorizationManager` và chọn mặc định phù hợp cho Spring Security 5.8, 6.x, 7.x.
3. Giải thích luồng `@PreAuthorize`, `@PostAuthorize`, AOP proxy, Reactor Context và `ReactiveAuthorizationManager`.
4. Viết ví dụ Spring Boot WebFlux Java 17+ dùng `Mono`, `Flux`, các role và authority khác nhau.
5. Kiểm thử bằng HTTP và `StepVerifier`, nhận diện các lỗi do proxy, context, annotation và phụ thuộc phiên bản.

**Phạm vi:** bài tập trung vào phương thức reactive trong Spring Security, không phải cấu hình `HttpSecurity`, `SecurityFilterChain`, `@EnableGlobalMethodSecurity` hoặc Servlet `MethodInterceptor` thông thường.

## 2. Vì sao cần method security?

Giả sử API `GET /api/admin/report` đã được kiểm soát ở HTTP layer. Tuy nhiên, service `reportService.exportSensitiveReport()` còn được gọi từ một endpoint khác chưa bảo vệ hoặc từ một luồng xử lý ngoài HTTP. Khi thêm:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> exportSensitiveReport() {
    return Mono.just("SECRET_REPORT");
}
~~~

Spring Security đặt một **method-security interceptor** quanh method trên bean do Spring quản lý. Trước khi cho method phát kết quả, interceptor dùng thông tin `Authentication` và biểu thức `hasRole('ADMIN')` để quyết định quyền. Không đủ quyền thì publisher kết thúc bằng lỗi truy cập (thường là `AccessDeniedException`/`AuthorizationDeniedException`, tùy version), thay vì trả dữ liệu cho caller.

Method security có lợi khi:

- Một nghiệp vụ dùng chung nhiều giao diện truy cập.
- Quyền phụ thuộc tham số method, chủ sở hữu đối tượng, tenant hoặc authority.
- Một controller vô tình quên HTTP matcher nhưng service vẫn có lớp bảo vệ độc lập.
- Có yêu cầu kiểm soát cả **trước khi xử lý** và **trước khi trả kết quả**.

Nhưng method security **không thay thế** HTTP security. HTTP filter còn xử lý authentication, CSRF, CORS, URL routing, entry point và HTTP 401/403. Thiết kế tốt dùng cả hai để *defense in depth*.

## 3. Bật @EnableReactiveMethodSecurity ở đâu?

Với Spring Boot WebFlux, có thể đặt annotation trên class `@Configuration`, hoặc ngay trên main application class đã chứa `@SpringBootApplication`:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfig {
}
~~~

Đây là **snippet cấu hình**, cần import:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
~~~

Nếu đặt annotation trên class `@SpringBootApplication` thì không cần tạo class cấu hình riêng. Tránh khai báo cùng lúc nhiều bản cấu hình method security không có mục đích; chúng có thể dẫn đến advisor lặp hoặc xung đột.

**Điểm quan trọng:** chỉ thêm `spring-boot-starter-security` chưa tự động bật toàn bộ annotation security của service. Cần khai báo `@EnableReactiveMethodSecurity` để Spring tạo các proxy/advisor cần thiết.

### 3.1. Chọn annotation đúng stack

| Nền tảng | Annotation cần dùng | Lý do |
| --- | --- | --- |
| Spring WebFlux + `Mono`/`Flux` | `@EnableReactiveMethodSecurity` | Tích hợp Reactor Context và reactive method interceptors |
| Spring MVC/Servlet | `@EnableMethodSecurity` | Method security trong Servlet / synchronous stack |
| Dự án Servlet rất cũ | `@EnableGlobalMethodSecurity` (legacy) | Không phải lựa chọn mới; không sao chép sang WebFlux |
| Cấu hình HTTP riêng cho WebFlux | `@EnableWebFluxSecurity` và `SecurityWebFilterChain` | Bảo vệ request; không tự thay method security |

Một codebase có cả MVC/WebFlux dependency cần kiểm tra ứng dụng thực sự chạy `REACTIVE` hay `SERVLET`. Đừng dùng `@EnableMethodSecurity` vì thấy tên ngắn hơn: đây là annotation khác, với semantics/phương thức xử lý khác.

## 4. Lựa chọn useAuthorizationManager theo phiên bản

Đây là trọng tâm của bài. Attribute `useAuthorizationManager` được bổ sung ở Spring Security 5.8, để chuyển từ pipeline method security cũ sang các interceptor dựa trên `ReactiveAuthorizationManager`.

### 4.1. Bảng tương thích

| Spring Security | Cấu hình khuyến nghị | Giải thích |
| --- | --- | --- |
| **5.7 trở về trước** | `@EnableReactiveMethodSecurity` | Chưa có `useAuthorizationManager`; không thêm thuộc tính chưa tồn tại |
| **5.8.x** | `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` | **Phải opt-in** nếu muốn reactive AuthorizationManager; Javadoc 5.8 ghi default **false** |
| **6.0.x** | Ưu tiên `@EnableReactiveMethodSecurity` trên patch đã sửa; kiểm tra Javadoc/patch | Migration guide của 6.0 chuyển default thành true, nhưng các bản patch rất sớm từng có sai khác giữa docs và code; nên dùng bản 6.0.x đã vá |
| **6.1–6.5.x** | `@EnableReactiveMethodSecurity` | Default `useAuthorizationManager = true`; bỏ thuộc tính thừa trong code mới |
| **7.0–7.1.x** | `@EnableReactiveMethodSecurity` | Javadoc 7.1 xác nhận default true; hướng AuthorizationManager là mặc định |
| **Các bản sau này** | Tra Javadoc của dependency **đã resolve** | API có thể thay đổi; không suy ra mặc định vĩnh viễn |

Hai cấu hình sau tương đương về lựa chọn manager trên các phiên bản mà **default true**:

~~~java
@EnableReactiveMethodSecurity

// Tường minh nhưng không cần thiết trong Spring Security 6.5 / 7.1:
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
~~~

Đây là **hai phương án riêng** để đặt trên class, không phải hai annotation cần dùng đồng thời.

**Bằng chứng phiên bản:** Javadoc Spring Security 5.8.16 ghi `useAuthorizationManager` default `false`; Javadoc Spring Security 7.1 ghi `true`. Tài liệu migration 6.5 xác nhận bước chuyển từ cấu hình tường minh sang annotation rút gọn sau khi default đổi ở 6.0. Khi gặp một ứng dụng 6.0.0 rất cũ, xác minh đúng patch và ưu tiên nâng cấp thay vì dựa vào giả định.

### 4.2. Liên hệ Spring Boot

Spring Boot BOM quản lý phiên bản Spring Security khi bạn dùng parent/BOM của Boot:

- **Spring Boot 3.5.x** đi cùng nhánh Spring Security **6.5.x** theo BOM patch tương ứng; Java tối thiểu 17.
- **Spring Boot 4.1.x** đi cùng nhánh Spring Security **7.1.x** theo BOM patch tương ứng; Java tối thiểu 17.
- Dự án tự override `spring-security-config`, `spring-security-core` hay `spring-security-web` có thể chạy phiên bản khác tài liệu Boot bạn đang xem. Kiểm tra dependency graph.

Trên Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw help:effective-pom
~~~

Trên Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config \
  --configuration runtimeClasspath
~~~

PowerShell/Windows dùng `.\mvnw.cmd` hoặc `.\gradlew.bat` tương ứng và đặt lệnh trên một dòng nếu shell không hỗ trợ nối dòng kiểu Bash. Không chỉ đọc version của `spring-security-web` rồi mặc định tất cả module security cùng version; hãy xác minh dependency resolution thực tế.

### 4.3. Có nên đặt useAuthorizationManager=false?

**Không dùng trong code mới.** Giá trị false chọn cơ chế method security cũ; một số phiên bản mới có yêu cầu bổ sung module `spring-security-access` cho legacy metadata/voter infrastructure. Chỉ cân nhắc khi duy trì hệ thống cũ có lý do rõ ràng, đã đọc migration notes đúng version và có kế hoạch loại bỏ.

Đừng dùng false để “sửa” lỗi 403 mà chưa tìm nguyên nhân; nó có thể vô tình thay đổi cách tính quyền trên toàn bộ service.

## 5. Khác biệt AuthorizationManager mới và pipeline cũ

### 5.1. Mô hình cũ

Trong kiến trúc legacy, hệ thống có thể sử dụng:

- `MethodSecurityMetadataSource` để đọc metadata/annotation.
- `ConfigAttribute` để biểu diễn điều kiện.
- `AccessDecisionManager` và các `AccessDecisionVoter` để bỏ phiếu.
- Các interceptor cũ gắn chặt những abstraction nói trên.

Mô hình này phức tạp khi cần tùy biến, thử nghiệm hoặc tích hợp với Reactor.

### 5.2. Mô hình dựa ReactiveAuthorizationManager

Với `useAuthorizationManager = true`, Spring Security reactive tạo các advisor/interceptor tương ứng với các annotation như:

| Annotation | Điểm kiểm tra | Thành phần liên quan |
| --- | --- | --- |
| `@PreAuthorize` | Trước lời gọi / trước publisher được phép chạy | `AuthorizationManagerBeforeReactiveMethodInterceptor` |
| `@PostAuthorize` | Sau khi đã tạo kết quả reactive, trước khi phát cho caller | `AuthorizationManagerAfterReactiveMethodInterceptor` |
| `@PreFilter` | Lọc tập tham số truyền vào (khi áp dụng được) | `PreFilterAuthorizationReactiveMethodInterceptor` |
| `@PostFilter` | Lọc phần tử kết quả (khi áp dụng được) | `PostFilterAuthorizationReactiveMethodInterceptor` |

Giao diện manager trong Spring Security 7.1 có chữ ký:

~~~java
public interface ReactiveAuthorizationManager<T> {
    Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication, T object);

    // verify(...) là phương thức mặc định để kiểm tra quyền.
}
~~~

Đây là **chữ ký rút gọn**, không phải toàn bộ source. `AuthorizationResult.isGranted()` biểu diễn kết quả; một số API/đoạn code cũ dùng `AuthorizationDecision` (một kiểu kết quả) hoặc `check(...)` trả `AuthorizationDecision`. Trong các bản mới, ưu tiên `authorize(...)` và `AuthorizationResult` theo Javadoc cụ thể.

Với method security, đối tượng `T` thường là `org.aopalliance.intercept.MethodInvocation`, có thông tin method, target và arguments. Một manager tùy biến có thể quyết định dựa vào danh tính, quyền, tham số hoặc chính sách miền nghiệp vụ. Manager trả `Mono.empty()` có thể nghĩa là abstain/không đưa ra quyết định; **không được xem empty là một cơ chế deny-all** khi muốn fail closed.

### 5.3. Trước method và sau method không giống nhau

Ví dụ:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> createReport() {
    return Mono.just("REPORT_READY");
}

@PostAuthorize("returnObject == authentication.name")
public Mono<String> readUsername(String selectedName) {
    return Mono.just(selectedName);
}
~~~

Hai method là snippet đặt trong một bean Spring. Với `@PreAuthorize`, quyền được xác định trước khi cho method chạy. Với `@PostAuthorize`, giá trị đã được tính/phát trong luồng nội bộ có thể bị kiểm tra sau, trước khi chuyển tới subscriber bên ngoài.

**Không dùng `@PostAuthorize` để bảo vệ thao tác có side effect** như chuyển tiền, xóa record hoặc gửi email: tác vụ có thể đã xảy ra trước khi hậu kiểm từ chối. Với thao tác thay đổi trạng thái, kiểm tra trước và kiểm tra quyền nghiệp vụ ở ranh giới transaction.

## 6. Reactor Context: nguồn của Authentication

Ở Spring MVC/Servlet, code thường quen với `SecurityContextHolder` kiểu `ThreadLocal`. Trong WebFlux, request có thể chạy qua nhiều thread. Reactive method security lấy thông tin từ **Reactor Context**, do `ReactiveSecurityContextHolder` cung cấp.

~~~text
HTTP request + credentials
         |
         v
SecurityWebFilterChain / AuthenticationWebFilter
         |
         v
SecurityContext được đưa vào Reactor Context
         |
         v
Controller gọi Spring-managed service proxy
         |
         v
Method interceptor đọc Authentication trong Reactor Context
         |
         +-- ALLOW -> subscription đến Mono/Flux của method
         |
         +-- DENY  -> Publisher phát AccessDeniedException
         |
         v
ExceptionTranslationWebFilter / error handling của WebFlux
         |
         v
HTTP 401 hoặc 403 theo trạng thái và cơ chế
~~~

**Điều kiện quan trọng:** method nên trả `org.reactivestreams.Publisher` (thường là `Mono<T>`, `Flux<T>`), để security interceptor tích hợp với context tại subscription. Các ứng dụng coroutine trên những nhánh hỗ trợ có quy tắc riêng, nên đọc tài liệu cho đúng phiên bản Kotlin/Spring Security.

Ví dụ đọc context trong pipeline:

~~~java
Mono<String> currentUserName = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
~~~

Snippet này cần import `ReactiveSecurityContextHolder`, `SecurityContext`, `Authentication` và `Mono`. Khi không có context tương ứng, publisher có thể empty; đừng biến empty thành tài khoản “admin” mặc định.

Trong unit test không có HTTP request, có thể gắn context bằng:

~~~java
Authentication user = new TestingAuthenticationToken(
        "reader", "unused", "ROLE_USER");

Mono<String> result = securedService.profile()
        .contextWrite(ReactiveSecurityContextHolder.withAuthentication(user));
~~~

Snippet ở đây giả định `securedService` là bean được Spring proxy và method `profile()` có annotation. Kiểm thử đầy đủ cần subscribe (`StepVerifier`), không chỉ khởi tạo một `Mono`. Tránh sử dụng `SecurityContextHolder.getContext()` dựa ThreadLocal để suy đoán danh tính đang áp dụng trong subscriber reactive.

## 7. Dự án hoàn chỉnh: bật reactive method security và xem kết quả

Để thấy hai lớp bảo vệ hoạt động độc lập, ta tạo một API Spring Boot WebFlux có:

- HTTP Basic xác thực user từ in-memory store.
- `SecurityWebFilterChain` xác thực tất cả URL `/api/**`.
- Method security kiểm tra role/authority tại service.
- `@PreAuthorize` cho các service cần `ROLE_USER`, `ROLE_ADMIN` và `report:read`.
- `@PostAuthorize` cho method chỉ được trả tên của chính caller.
- Các endpoint GET, nên không cần tắt CSRF của Spring Security.

### 7.1. File pom.xml

Tạo project trên [Spring Initializr](https://start.spring.io/) với Java 17+, Maven, Spring Boot 4.1.2, group `com.example`, artifact `reactive-method-demo`; chọn **Spring Reactive Web** và **Spring Security**. Ví dụ `pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>reactive-method-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
~~~

Không khai báo version riêng của từng module `spring-security-*`. Dùng parent/BOM để tránh trộn Spring Framework, Security và Reactor không tương thích.

### 7.2. File Java độc lập

Tạo file `src/main/java/com/example/methoddemo/ReactiveMethodDemoApplication.java`:

~~~java
package com.example.methoddemo;

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
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveMethodDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveMethodDemoApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
                .password("{noop}reader123")
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password("{noop}admin123")
                .roles("USER", "ADMIN")
                .build();

        UserDetails analyst = User.withUsername("analyst")
                .password("{noop}analyst123")
                .authorities("report:read")
                .build();

        return new MapReactiveUserDetailsService(reader, admin, analyst);
    }

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/status").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Service
    static class SecuredService {

        @PreAuthorize("hasRole('USER')")
        public Mono<String> profile() {
            return Mono.just("PROFILE_OK");
        }

        @PreAuthorize("hasRole('ADMIN')")
        public Mono<String> adminReport() {
            return Mono.just("ADMIN_REPORT_OK");
        }

        @PreAuthorize("hasAuthority('report:read')")
        public Flux<String> reports() {
            return Flux.just("R1", "R2");
        }

        @PreAuthorize("#owner == authentication.name")
        public Mono<String> byOwner(String owner) {
            return Mono.just("OWNER_OK:" + owner);
        }

        @PostAuthorize("returnObject == authentication.name")
        public Mono<String> checkedName(String name) {
            return Mono.just(name);
        }
    }

    @RestController
    static class DemoController {
        private final SecuredService service;

        DemoController(SecuredService service) {
            this.service = service;
        }

        @GetMapping("/status")
        Mono<String> status() {
            return Mono.just("UP");
        }

        @GetMapping("/api/profile")
        Mono<String> profile() {
            return service.profile();
        }

        @GetMapping("/api/admin")
        Mono<String> adminReport() {
            return service.adminReport();
        }

        @GetMapping("/api/reports")
        Flux<String> reports() {
            return service.reports();
        }

        @GetMapping("/api/owner/{owner}")
        Mono<String> byOwner(@PathVariable String owner) {
            return service.byOwner(owner);
        }

        @GetMapping("/api/checked/{name}")
        Mono<String> checkedName(@PathVariable String name) {
            return service.checkedName(name);
        }
    }
}
~~~

**Chú thích về khả năng chạy:**

- Class public và đường dẫn package khớp nhau; các class `@Service` và `@RestController` là **nested static class** được Spring component scan tìm thấy. Chúng không phải `final` để tránh vấn đề proxy.
- `SecuredService` là một Spring bean riêng được controller inject, nên lời gọi đi **qua AOP proxy**, không phải gọi `this.method()` trong cùng object.
- `@EnableReactiveMethodSecurity` dùng mặc định AuthorizationManager của Spring Security 7.1. Khi nâng cấp hoặc thử nhánh 5.8, cần chỉnh annotation theo bảng phiên bản.
- `MapReactiveUserDetailsService` dùng ba user local. `{noop}` không mã hóa password: **chỉ dùng demo trên máy local**, không dùng plaintext/hardcoded credentials trong production. Ứng dụng thật cần password encoder, HTTPS và hệ thống danh tính thích hợp.
- `roles("USER")` tạo authority `ROLE_USER`, `roles("ADMIN")` tạo `ROLE_ADMIN`; `hasRole("ADMIN")` có prefix `ROLE_` mặc định. `authorities("report:read")` tạo chuỗi authority nguyên văn để `hasAuthority("report:read")` kiểm tra.
- `@PostAuthorize` kiểm tra **giá trị đã phát ra** từ `Mono<String>` trước khi người gọi nhận được. Vì method chỉ trả tên, không có tác động dữ liệu khi deny.
- `SecurityWebFilterChain` bảo vệ request ở HTTP layer; method security thực hiện kiểm tra sâu hơn khi service được gọi. Không dùng HTTP matcher thay cho AOP proxy.

### 7.3. Chạy dự án

Tại thư mục chứa `pom.xml`, chạy:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

Trên Windows dùng `.\mvnw.cmd clean package` và `.\mvnw.cmd spring-boot:run`. Nếu project không có wrapper, có thể dùng Maven đã cài qua `mvn clean package` và `mvn spring-boot:run`.

Ứng dụng mặc định lắng nghe `http://localhost:8080`. Nếu package/import không đúng version, hãy dừng và kiểm tra Javadoc/dependency tree; không “sửa” bằng cách bỏ `@EnableReactiveMethodSecurity` hoặc thêm các dependency Servlet không liên quan.

### 7.4. Kiểm chứng qua curl

Các lệnh ví dụ:

~~~bash
curl -i http://localhost:8080/status
curl -i http://localhost:8080/api/profile
curl -i -u 'reader:reader123' http://localhost:8080/api/profile
curl -i -u 'reader:reader123' http://localhost:8080/api/admin
curl -i -u 'admin:admin123' http://localhost:8080/api/admin
curl -i -u 'analyst:analyst123' http://localhost:8080/api/reports
curl -i -u 'reader:reader123' http://localhost:8080/api/reports
curl -i -u 'reader:reader123' http://localhost:8080/api/owner/reader
curl -i -u 'reader:reader123' http://localhost:8080/api/owner/admin
curl -i -u 'reader:reader123' http://localhost:8080/api/checked/reader
curl -i -u 'reader:reader123' http://localhost:8080/api/checked/admin
~~~

Dùng `curl.exe` nếu PowerShell đặt alias `curl` cho `Invoke-WebRequest`. Kết quả mong đợi (khi app chạy với Basic mặc định và không có custom exception handler):

| Request | Status | Nội dung hoặc lý do |
| --- | --- | --- |
| `GET /status` anonymous | **200** | `UP` |
| `GET /api/profile` anonymous | **401** | Bị HTTP rule `authenticated` chặn |
| Reader → `/api/profile` | **200** | `PROFILE_OK` |
| Reader → `/api/admin` | **403** | HTTP auth thành công, service thiếu `ROLE_ADMIN` |
| Admin → `/api/admin` | **200** | `ADMIN_REPORT_OK` |
| Analyst → `/api/reports` | **200** | Nội dung `R1` và `R2` qua `Flux` |
| Reader → `/api/reports` | **403** | Không có authority `report:read` |
| Reader → `/api/owner/reader` | **200** | `OWNER_OK:reader` |
| Reader → `/api/owner/admin` | **403** | `#owner` không bằng `authentication.name` |
| Reader → `/api/checked/reader` | **200** | `reader` |
| Reader → `/api/checked/admin` | **403** | `@PostAuthorize` chặn giá trị trả về không khớp |

`Flux<String>` qua WebFlux có thể được encode/stream theo `Accept` và codec; **không hard-code format body** của hai phần tử nếu không cố định media type trong controller. HTTP status và nội dung từng phần tử là tín hiệu chính.

Nếu anonymous gọi service qua HTTP trong một cấu hình khác cho phép URL, method security denial vẫn có thể dẫn tới authentication entry point/401. Nhưng status HTTP cuối cùng phụ thuộc authentication mechanism, entry point và exception handling; không khẳng định mọi lời gọi service ngoài HTTP có thể chuyển thành HTTP 403.

## 8. Kiểm thử method security không cần HTTP

Một bài test chỉ dùng `curl` không chứng minh method security được kiểm tra độc lập nếu HTTP layer đã chặn trước. Với service có AOP proxy, hãy test publisher trực tiếp và gắn authentication vào Reactor Context.

Ví dụ **đoạn phương thức kiểm thử**, cần Spring Test/`reactor-test`, service phải được inject từ ApplicationContext:

~~~java
@Test
void readerCannotCallAdminService() {
    Authentication reader = new TestingAuthenticationToken(
            "reader", "unused", "ROLE_USER");

    Mono<String> invocation = service.adminReport()
            .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(reader));

    StepVerifier.create(invocation)
            .expectError(AccessDeniedException.class)
            .verify();
}

@Test
void adminCanCallAdminService() {
    Authentication admin = new TestingAuthenticationToken(
            "admin", "unused", "ROLE_ADMIN");

    Mono<String> invocation = service.adminReport()
            .contextWrite(
                    ReactiveSecurityContextHolder.withAuthentication(admin));

    StepVerifier.create(invocation)
            .expectNext("ADMIN_REPORT_OK")
            .verifyComplete();
}
~~~

Đây là **test snippet**, chưa phải class test hoàn chỉnh. Cần imports `org.junit.jupiter.api.Test`, `org.springframework.security.authentication.TestingAuthenticationToken`, `org.springframework.security.core.Authentication`, `org.springframework.security.core.context.ReactiveSecurityContextHolder`, `org.springframework.security.access.AccessDeniedException`, `reactor.core.publisher.Mono` và `reactor.test.StepVerifier`. Bean `service` phải là **proxy từ Spring**; không tạo bằng `new SecuredService()` vì làm vậy sẽ bỏ qua AOP. Một số phiên bản ném subtype của `AccessDeniedException`; `expectError(AccessDeniedException.class)` phù hợp khi subtype kế thừa exception đó.

Đối với full test project, thêm dependencies kiểm thử do Spring Boot BOM quản lý, ví dụ Spring Boot WebFlux test starter và Spring Security test theo phiên bản đang sử dụng. Nếu dùng Spring Boot 4, các starter test có thể được tách theo chức năng; xác minh artifact tương ứng qua Initializr thay vì sao chép nguyên danh sách test dependency từ Boot 2.x.

**Tại sao dùng `contextWrite` sau lời gọi?** Publisher deferred nhận Reactor Context khi subscribe. Nếu service là proxy, method-security interceptor được thực thi tương thích với subscription; context giúp manager nhìn thấy user của test.

Nếu một test không có context, method security có thể phát lỗi authentication thay vì success; đó là điều cần phát hiện chứ không nên giả lập ThreadLocal security context.

## 9. Các annotation và biểu thức cần nhớ

### 9.1. @PreAuthorize

~~~java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminOnly() {
    return Mono.just("OK");
}

@PreAuthorize("hasAuthority('invoice:read')")
public Flux<String> invoices() {
    return Flux.just("I-1", "I-2");
}

@PreAuthorize("#ownerId == authentication.name")
public Mono<String> owned(String ownerId) {
    return Mono.just(ownerId);
}
~~~

Đây là **các method snippet đặt trong Spring bean**, cần import `@PreAuthorize`, `Mono`, `Flux`. Biểu thức có thể đọc principal/roles/authority/parameters. Với Java compile không giữ tên tham số theo cách SpEL mong đợi, cần bật metadata parameter names hoặc dùng annotation thích hợp như `@P("ownerId")` theo phiên bản; với Spring Boot compiler plugin hiện đại thường cấu hình hỗ trợ `-parameters`. Nếu SpEL không tìm được `#ownerId`, kiểm tra metadata trước khi đổi chính sách.

### 9.2. @PostAuthorize

~~~java
@PostAuthorize("returnObject.owner == authentication.name")
public Mono<DocumentView> findDocument(String id) {
    return repository.findById(id);
}
~~~

**Đây là snippet minh họa không độc lập**: `DocumentView` và `repository` giả định, với `owner` là property của object trả về. Spring Security reactive có thể đánh giá dữ liệu được phát ra từ `Mono` trước khi downstream sử dụng nó. Tuy nhiên, truy vấn đã thực hiện; đừng coi đây là biện pháp chống side effect hoặc chống truy vấn trái quyền tại DB. Với thông tin nhạy cảm, có thể cần kiểm tra owner **trước truy vấn** hoặc lọc ngay ở database theo tenant/user id để tránh leak qua log, timing và cache.

### 9.3. @PreFilter và @PostFilter

Các interceptor trên AuthorizationManager path hỗ trợ kiểm tra trước/sau các collection hoặc publisher theo contract API. Vì filter có thể xử lý từng phần tử hoặc tập tham số, cần xem kiểu trả về, mức độ đánh giá lazy và chi phí trên publisher. Không dùng `@PostFilter` thay cho `WHERE tenant_id = ...` ở database khi dữ liệu lớn hoặc đa tenant.

### 9.4. hasRole và hasAuthority

| Biểu thức | Điều kiện thường dùng |
| --- | --- |
| `hasRole('ADMIN')` | Authentication có `ROLE_ADMIN` theo prefix role mặc định |
| `hasAuthority('ROLE_ADMIN')` | Authentication có authority đúng chuỗi `ROLE_ADMIN` |
| `hasAuthority('report:read')` | Có authority đúng `report:read` |
| `isAuthenticated()` | Có authentication được Spring Security xem là đăng nhập hợp lệ |
| `#owner == authentication.name` | Method argument `owner` khớp principal name |

Nếu ứng dụng dùng `GrantedAuthorityDefaults` để thay prefix role, `hasRole` có thể có cách diễn giải khác; kiểm tra cấu hình phiên bản/bean. Không tự nối `ROLE_` vào mọi chuỗi khi API đã làm việc đó.

### 9.5. SpEL phải không blocking

Các expression và custom bean được dùng trong `@PreAuthorize` chạy trên đường reactive request. Một bean trả `Mono<Boolean>` có thể làm việc reactive; nếu bean chỉ trả `Boolean`, tránh gọi JDBC blocking hoặc HTTP client blocking trong đó.

Ví dụ bean kiểm tra sở hữu bằng Reactor Context:

~~~java
@Component("ownerPolicy")
class OwnerPolicy {

    public Mono<Boolean> canRead(String owner) {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication ->
                        authentication.getName().equals(owner)
                        || authentication.getAuthorities().stream().anyMatch(
                            a -> "ROLE_ADMIN".equals(a.getAuthority())))
                .defaultIfEmpty(false);
    }
}

// Trong Spring-managed service:
@PreAuthorize("@ownerPolicy.canRead(#owner)")
public Mono<String> readFor(String owner) {
    return Mono.just("OK");
}
~~~

Đây là **snippet hai class/method**, không phải file độc lập: cần đặt method có annotation trong service và import `@Component`, `ReactiveSecurityContextHolder`, `SecurityContext`, `Mono`. Theo tài liệu AuthorizationManager method-security, custom bean trong SpEL có thể trả `Boolean` hoặc `Mono<Boolean>`. `defaultIfEmpty(false)` giúp không có context dẫn tới deny rõ ràng.

Một chính sách owner production cần dựa vào id bền vững và kiểm tra tenant/resource, không chỉ so chuỗi path/username. Nếu cần truy vấn resource, ưu tiên repository reactive và kiểm soát lỗi truy cập dữ liệu.

## 10. Tùy chỉnh ReactiveAuthorizationManager ở mức interceptor

### 10.1. Khi nào cần?

Các biểu thức `@PreAuthorize` thường đủ. Khi logic phân quyền cần test sâu, lấy nhiều ngữ cảnh hoặc tái sử dụng policy, có thể viết một `ReactiveAuthorizationManager<MethodInvocation>` và gắn nó vào advisor. **Chỉ tạo một bean manager không tự khiến toàn bộ `@PreAuthorize` dùng manager đó**; phải đăng ký interceptor/pointcut phù hợp.

Ví dụ manager đơn giản kiểm tra `ROLE_AUDITOR` (đoạn mã **minh họa**, không phải cấu hình hoàn chỉnh):

~~~java
final class AuditorAuthorizationManager
        implements ReactiveAuthorizationManager<MethodInvocation> {

    @Override
    public Mono<AuthorizationResult> authorize(
            Mono<Authentication> authentication,
            MethodInvocation invocation) {

        return authentication
                .map(user -> user.getAuthorities().stream()
                        .anyMatch(a -> "ROLE_AUDITOR".equals(a.getAuthority())))
                .map(granted ->
                        (AuthorizationResult) new AuthorizationDecision(granted))
                .defaultIfEmpty(new AuthorizationDecision(false));
    }
}
~~~

Imports cần dùng:

~~~java
import org.aopalliance.intercept.MethodInvocation;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.authorization.ReactiveAuthorizationManager;
import org.springframework.security.core.Authentication;
import reactor.core.publisher.Mono;
~~~

Trong Spring Security 7.1, `ReactiveAuthorizationManager.authorize(Mono<Authentication>, T)` trả `Mono<AuthorizationResult>`, không phải boolean đồng bộ. `AuthorizationDecision` là một implementation của `AuthorizationResult`. Với một số tài liệu cũ, bạn có thể thấy `check(...)` hoặc chữ ký nhận `Supplier<Authentication>`; **hãy đối chiếu Javadoc đúng resolved version** thay vì copy lẫn API.

### 10.2. Cách gắn vào method interceptor

API có factory:

~~~java
AuthorizationManagerBeforeReactiveMethodInterceptor.preAuthorize(manager);
~~~

Đây là **dòng minh họa**, với `manager` kiểu `ReactiveAuthorizationManager<MethodInvocation>`. Để sử dụng cần publish `Advisor` / bean hạ tầng với pointcut cho đúng annotation. Nếu đã bật `@EnableReactiveMethodSecurity` khiến Spring đăng ký default advisor, việc thêm advisor mới mà không vô hiệu hóa/tùy biến default có thể khiến **cả hai rule bị áp dụng** hoặc có xung đột.

Vì vậy, trong phần lớn dự án, cách an toàn hơn là:

1. Giữ `@EnableReactiveMethodSecurity` với các default interceptors.
2. Đưa logic vào bean để SpEL gọi, hoặc một service authorization được kiểm thử riêng.
3. Chỉ thay đổi advisor nội bộ khi thật sự cần, đã hiểu thứ tự `AuthorizationInterceptorsOrder`, pointcut, AOP và dependency.
4. Viết integration test để chứng minh các annotation không bị bỏ qua hoặc chạy lặp.

**Không dùng snippet factory một mình rồi tuyên bố đã “thay toàn bộ AuthorizationManager”.** Nếu phải can thiệp hạ tầng, xem tài liệu Spring Security method-security tương ứng, bởi số lượng interceptor và điểm đăng ký thay đổi giữa phiên bản.

## 11. AOP proxy: bẫy làm method security không chạy

### 11.1. Lời gọi nội bộ (self-invocation)

Giả sử:

~~~java
@Service
class ReportService {

    public Mono<String> unsafeFacade() {
        return adminOnly(); // this.adminOnly(): bỏ qua Spring AOP proxy
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminOnly() {
        return Mono.just("SECRET");
    }
}
~~~

Đây là **snippet minh họa nguy cơ**: nếu `unsafeFacade()` được gọi từ bean khác, lời gọi nội bộ tới `adminOnly()` vẫn là `this.adminOnly()`, không đi qua proxy riêng của method đó. Vì vậy annotation có thể không được kiểm tra như mong muốn.

**Giải pháp:** chuyển business method cần bảo vệ sang một bean riêng rồi inject vào bean gọi; hoặc thiết kế lại luồng để luôn đi qua Spring-managed proxy. Không coi annotation trên private method hoặc method được gọi trực tiếp bằng `new` là biện pháp bảo vệ hiệu lực.

### 11.2. Final/private method và Kotlin

Spring AOP proxy có giới hạn đối với method không thể override và internal invocation. Với class không có interface, Spring thường sử dụng class-based proxy; class hoặc method `final` có thể ngăn proxy hoạt động theo cách mong muốn. Trong Kotlin, class mặc định `final`, cần các plugin/mẫu proxy tương thích. Không chỉ nhìn thấy annotation trong source rồi kết luận interceptor đã chạy.

### 11.3. Bean do Spring quản lý

Nếu bạn tạo object bằng `new SecuredService()` trong controller/test, đó không phải proxy bean Spring; annotation có thể không được enforce. Dùng dependency injection từ ApplicationContext, và viết test fail để kiểm tra security advice thật sự được đăng ký.

### 11.4. Mono không được subscribe

Reactive publisher chỉ mô tả công việc. Nếu bạn gọi method trả `Mono` nhưng không return/subscribe, không thể xem việc không thấy lỗi là bằng chứng cho quyền đã được cấp. Trong WebFlux, controller nên **return publisher** cho framework. Trong test, dùng `StepVerifier` để buộc thực thi và kiểm chứng `onNext`/`onError`.

## 12. Phân biệt lỗi của method security và lỗi HTTP

| Tình huống | Ở tầng method | HTTP thường thấy với Basic |
| --- | --- | --- |
| Request không có user và HTTP yêu cầu `authenticated` | Không vào method | **401** |
| User đã xác thực nhưng thiếu `ROLE_ADMIN` | Method security deny | **403** |
| User hợp lệ, có role | Publisher được phép phát kết quả | **200** nếu handler thành công |
| Method bị deny ngoài HTTP (job/service test) | Publisher lỗi `AccessDeniedException` | **Không có HTTP response** để tự quy đổi |
| CSRF token thiếu ở POST | Có thể bị `CsrfWebFilter` chặn trước method | **403** nhưng không phải role denial |
| HTTP 404 route không tồn tại | Service không được gọi | **404** nếu HTTP rule cho đi qua route lookup |

`ExceptionTranslationWebFilter` có thể chuyển lỗi access denied phát sinh trong reactive request flow thành entry point hoặc access-denied response. Nhưng không thể nói mọi `AccessDeniedException` ở background task tự biến thành HTTP 403. Với non-HTTP caller, phải xử lý exception theo ranh giới nghiệp vụ và ghi audit thích hợp.

## 13. Chiến lược migration an toàn

Nếu một codebase đang dùng Spring Security 5.8 với:

~~~java
@EnableReactiveMethodSecurity(useAuthorizationManager = true)
~~~

khi nâng lên 6.5/7.1 có thể chuyển thành:

~~~java
@EnableReactiveMethodSecurity
~~~

Thực hiện theo thứ tự:

1. **Kiểm kê version đã resolve** của `spring-security-config`, `spring-security-core`, `spring-security-web`; xác định Boot BOM.
2. Xem `@EnableReactiveMethodSecurity` trong Javadoc **của phiên bản đang dùng**, nhất là nếu từ 5.8 hoặc patch 6.0.0 cũ.
3. Kiểm thử mọi `@PreAuthorize`, `@PostAuthorize`, custom SpEL bean, custom interceptor, role prefix và các return type.
4. Nếu có custom `AccessDecisionVoter`/metadata source, lập kế hoạch thay bằng `ReactiveAuthorizationManager` hoặc logic bean trong SpEL. Không đoán những custom extension cũ tự hoạt động trong architecture mới.
5. Không mang `@EnableMethodSecurity(prePostEnabled = false)` từ hướng dẫn Servlet sang annotation reactive: `@EnableReactiveMethodSecurity` có tập attribute khác (proxyTargetClass, mode, order, useAuthorizationManager). Cần cấu hình hạ tầng reactive theo Javadoc riêng.
6. Nếu dùng annotation trên interface, class hoặc method kế thừa, kiểm tra AOP pointcut và những annotation xung đột; AuthorizationManager path có cơ chế phát hiện một số cấu hình mơ hồ.
7. Chạy lại integration tests với Spring Boot patch mới, nhất là các policy có `Mono<Boolean>` trong SpEL, `@PostAuthorize` và Reactor Context.
8. Sau migration, log/metric nên theo dõi denied method invocation nhưng không xuất principal secrets hoặc dữ liệu nhạy cảm.

### Ma trận chọn nhanh

| Bạn đang ở đâu? | Làm gì? |
| --- | --- |
| Mới tạo project Boot 4.1 / Security 7.1 | `@EnableReactiveMethodSecurity` |
| Project Boot 3.5 / Security 6.5 | `@EnableReactiveMethodSecurity` |
| Legacy Security 5.8, cần AuthorizationManager | `@EnableReactiveMethodSecurity(useAuthorizationManager = true)` |
| Dự án 5.7 trở xuống | Không thêm attribute chưa hỗ trợ; lên kế hoạch nâng cấp |
| Codebase có `useAuthorizationManager = false` | Kiểm tra phụ thuộc legacy và nhu cầu migration; không chép vào dự án mới |
| Method annotation không chạy | Kiểm tra enable annotation, proxy, self-invocation, Publisher và context trước khi đổi chính sách |
| Cần logic phức tạp | Ưu tiên custom SpEL bean reactive, chỉ thay advisor khi đã hiểu hạ tầng |

## 14. Những lỗi thường gặp

**“Tôi thêm `@PreAuthorize` nhưng user vẫn vào được.”** Có thể thiếu `@EnableReactiveMethodSecurity`, service không phải bean Spring, lời gọi self-invocation, method final/private, annotation đặt sai chỗ hoặc test không subscribe. Không giải quyết bằng cách thêm HTTP matcher ngẫu nhiên rồi cho rằng method security đã hoạt động.

**“Tôi có `@EnableMethodSecurity` mà Mono không lấy được user.”** Có thể đang dùng cấu hình Servlet thay cho reactive. Chuyển sang `@EnableReactiveMethodSecurity` và xác minh Reactor Context.

**“Tôi bỏ `useAuthorizationManager = true` ở Security 5.8 rồi policy đổi kết quả.”** Ở 5.8, default là false. Giữ opt-in true đến khi bạn nâng cấp lên phiên bản có default true được xác nhận.

**“Tôi viết `@PreAuthorize("hasRole('ROLE_ADMIN')")`.”** `hasRole` thường tự thêm `ROLE_`. Trong demo dùng `hasRole('ADMIN')`; nếu cần exact string, dùng `hasAuthority('ROLE_ADMIN')`.

**“Tôi đặt JWT principal vào ThreadLocal rồi method vẫn không thấy.”** Reactive flow truyền context qua Reactor; dùng cơ chế authentication/WebFilter của Spring Security hoặc `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` trong test, không dựa ThreadLocal.

**“Tôi dùng `Mono.just(blockingRepository.findById(...))` trong biểu thức authorization.”** Lời gọi blocking vẫn chạy trước khi tạo Mono. Sử dụng reactive repository/HTTP client; nếu bất khả kháng, thiết kế scheduler và timeout có giới hạn.

**“Tôi cho `@PostAuthorize` bảo vệ chuyển tiền.”** Hậu kiểm có thể xảy ra sau side effect. Với thao tác thay đổi dữ liệu, phải kiểm tra quyền trước transaction và tại chỗ truy cập dữ liệu nhạy cảm.

**“Tôi tạo custom ReactiveAuthorizationManager bean là annotation tự dùng.”** Không. Manager phải được kết nối đúng advisor/pointcut hoặc được một component SpEL gọi. Tự thay default advisor có thể gây duplicate enforcement.

**“Một endpoint trả 403 chứng minh annotation đang chạy.”** Không nhất thiết: 403 có thể xuất phát từ HTTP authorization, CSRF, role method hoặc exception handler tùy biến. Kiểm tra bằng test trực tiếp gọi Spring-managed service proxy với các principal khác nhau.

## 15. Checklist trước khi đưa vào production

1. Đang chạy đúng WebFlux/reactive ApplicationContext, không trộn Servlet method security.
2. Spring Security BOM/version đã resolve được xác minh; attribute `useAuthorizationManager` đúng nhánh.
3. `@EnableReactiveMethodSecurity` có mặt tại cấu hình và Spring tạo đúng reactive interceptors.
4. Mọi method được bảo vệ là Spring-managed bean được gọi qua proxy và trả Publisher phù hợp.
5. Có authentication trong Reactor Context khi method được gọi.
6. Role prefix, authority và parameter metadata trong SpEL được test rõ ràng.
7. Method cần kiểm tra sở hữu/tenant có policy dựa dữ liệu đáng tin, không chỉ so tham số do client gửi.
8. Không có blocking I/O trong manager, policy bean hoặc path đang chạy trên event loop.
9. Không dựa vào hậu kiểm để ngăn side effect.
10. Có test cho anonymous, user thường, admin, sai role, sai owner, producer/consumer ngoài HTTP và self-invocation.
11. HTTP security vẫn có rule chặt chẽ, CSRF/CORS/session/token theo threat model.
12. Lỗi quyền được log an toàn, không tiết lộ dữ liệu nghiệp vụ/credentials.

## 16. Câu hỏi tự đánh giá

**Câu 1.** Spring Security 5.8 muốn dùng AuthorizationManager-based method security thì đặt annotation gì?

**Đáp án:** `@EnableReactiveMethodSecurity(useAuthorizationManager = true)`, vì Javadoc 5.8 ghi mặc định false.

**Câu 2.** Ở Spring Security 6.5 hoặc 7.1, có cần luôn viết thuộc tính true không?

**Đáp án:** Không. `@EnableReactiveMethodSecurity` mặc định bật AuthorizationManager. Nên giữ code gọn và xác minh đúng version đã resolve.

**Câu 3.** Vì sao method `Mono<String> sensitive()` có `@PreAuthorize` vẫn bị bỏ qua khi gọi từ một method khác cùng class?

**Đáp án:** Lời gọi nội bộ qua `this` không đi qua Spring AOP proxy; chuyển method bảo vệ sang Spring bean riêng và inject để lời gọi qua proxy.

**Câu 4.** Sự khác nhau của `@PreAuthorize` và `@PostAuthorize`?

**Đáp án:** Pre kiểm tra trước khi gọi/cho phép publisher thực thi; Post kiểm tra kết quả sau khi có dữ liệu và trước khi downstream nhận, nên không bảo đảm ngăn side effect đã xảy ra.

**Câu 5.** Vì sao dùng `ReactiveSecurityContextHolder` thay vì `SecurityContextHolder` ThreadLocal?

**Đáp án:** Luồng reactive có thể đổi thread; Reactor Context đi theo subscriber và là nơi Spring Security tích hợp Authentication.

**Câu 6.** Tại sao `hasRole('ADMIN')` trong demo đọc được authority `ROLE_ADMIN`?

**Đáp án:** Spring Security dùng prefix `ROLE_` theo mặc định cho kiểm tra role; `roles("ADMIN")` tạo authority tương ứng.

**Câu 7.** Tại sao user `reader` nhận 403 khi gọi `/api/admin` dù HTTP layer cho user đăng nhập vào `/api/**`?

**Đáp án:** HTTP chỉ yêu cầu authenticated; service method còn `@PreAuthorize("hasRole('ADMIN')")`, reader thiếu role nên method-security interceptor deny.

**Câu 8.** Khi custom manager trả `Mono.empty()`, đó có phải là một quyết định từ chối chắc chắn?

**Đáp án:** Không; theo contract `ReactiveAuthorizationManager`, empty có thể biểu diễn không đưa ra quyết định. Nếu cần fail closed, hãy trả kết quả deny rõ ràng và bảo đảm policy composition đúng.

## 17. Tài liệu chính thức và kiểm tra phiên bản

- [Spring Security 7.1 — EnableReactiveMethodSecurity và AuthorizationManager](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Javadoc — EnableReactiveMethodSecurity (hiện hành, default true)](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Javadoc — EnableReactiveMethodSecurity 5.8.16 (default false)](https://docs.spring.io/spring-security/site/docs/5.8.16/api/org/springframework/security/config/annotation/method/configuration/EnableReactiveMethodSecurity.html)
- [Spring Security 6.5 Migration — Reactive / AuthorizationManager](https://docs.spring.io/spring-security/reference/6.5/migration/reactive.html)
- [Javadoc — ReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/ReactiveAuthorizationManager.html)
- [Javadoc — AuthorizationManagerBeforeReactiveMethodInterceptor](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/AuthorizationManagerBeforeReactiveMethodInterceptor.html)
- [Javadoc — PreAuthorizeReactiveAuthorizationManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/PreAuthorizeReactiveAuthorizationManager.html)
- [Spring Security — Reactive WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
