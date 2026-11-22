# Thiết lập `spring-boot-starter-webflux`, `spring-boot-starter-security` và `spring-security-test`

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Khởi tạo ứng dụng  
> **Đích thực hành:** Có một ứng dụng Spring Boot WebFlux chạy được, một cấu hình bảo vệ HTTP bằng Spring Security reactive và một bộ test xác thực/phân quyền bằng `WebTestClient` cùng `spring-security-test`.

## 1. Hiểu rõ vai trò của từng dependency

Trong ứng dụng reactive, **WebFlux** cung cấp mô hình web và xử lý bất đồng bộ dựa trên `Publisher` (`Mono`/`Flux`), **Spring Security** bảo vệ request và quản lý danh tính/quyền truy cập, còn **Spring Security Test** cung cấp công cụ mô phỏng danh tính và kiểm thử các chính sách bảo mật. Đây là ba trách nhiệm khác nhau, được tích hợp khi chạy chung.

| Dependency | Scope | Cung cấp gì? | Dùng ở đâu? |
| --- | --- | --- | --- |
| `org.springframework.boot:spring-boot-starter-webflux` | Runtime/compile | Spring WebFlux, Reactor, hỗ trợ REST controller hoặc functional routing, máy chủ Reactor Netty mặc định | `@RestController`, `Mono`, `Flux`, xử lý HTTP reactive |
| `org.springframework.boot:spring-boot-starter-security` | Runtime/compile | Spring Security core, cấu hình Spring Security và tích hợp bảo vệ web; với WebFlux dùng các thành phần reactive | `SecurityWebFilterChain`, `ServerHttpSecurity`, `ReactiveAuthenticationManager` |
| `org.springframework.security:spring-security-test` | **Test only** | `mockUser()`, `springSecurity()`, `csrf()`, `@WithMockUser`, các công cụ kiểm thử security | `src/test/java`, `WebTestClient`, JUnit |
| `org.springframework.boot:spring-boot-starter-test` | Test only | JUnit Jupiter, Spring Boot Test/Spring Test, AssertJ, Mockito và các thư viện test phổ biến | Chạy `@SpringBootTest`, assertion và test context |
| `io.projectreactor:reactor-test` | Test only | `StepVerifier`, `TestPublisher` dùng kiểm tra publisher của Reactor | Unit test chuỗi `Mono`/`Flux` độc lập với HTTP |

**Không nhầm hai nhóm test:** `spring-boot-starter-test` mang lại nền tảng JUnit và Spring Test; `spring-security-test` thêm những tiện ích đặc thù về security. Muốn test endpoint WebFlux bảo mật một cách thuận tiện thì cần cả hai. `reactor-test` hữu ích cho test operator/publisher nhưng không thay thế `WebTestClient`.

**Không trộn hai web stack theo thói quen:** `spring-boot-starter-web` là nền tảng Spring MVC/Servlet. Khi cả `starter-web` và `starter-webflux` cùng có mặt, Spring Boot thường chọn ứng dụng Servlet. Để học cấu hình reactive chính xác, chỉ dùng `spring-boot-starter-webflux` ở ví dụ này. WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity`; Spring MVC dùng `SecurityFilterChain` và `HttpSecurity`.

### Từ dependency đến request

```text
spring-boot-starter-webflux
    └── WebFlux WebHandler + Reactor Netty + Mono/Flux
               │
HTTP request ──┼──> SecurityWebFilterChain (spring-boot-starter-security)
               │         ├── xác thực người gọi
               │         └── kiểm tra authority/role
               └──> @RestController / reactive service ──> response

JUnit + Spring Test (spring-boot-starter-test)
    └── WebTestClient + SecurityMockServerConfigurers (spring-security-test)
                └── gửi request giả lập, kiểm tra 200 / 401 / 403
```

Spring Security reactive gắn `Authentication` vào `SecurityContext` trong Reactor `Context`. Không giả định một request WebFlux sẽ chạy trọn đời trên một thread cố định.

## 2. Điều kiện tiên quyết và cách khởi tạo project

Ví dụ độc lập bên dưới dùng **Java 17+** và **Spring Boot 3.5.16**, một phiên bản cụ thể để phụ thuộc được quản lý đồng bộ. Cần Maven 3.6.3+ (nếu chọn Maven) hoặc bản Gradle tương thích với Spring Boot 3.5 (nếu chọn Gradle). Khi đưa vào dự án khác, chọn nhánh Spring Boot đang được dự án hỗ trợ và để BOM/plugin của Spring Boot quản lý phiên bản Spring Framework, Spring Security và Reactor.

Có thể khởi tạo bằng [Spring Initializr](https://start.spring.io/) rồi chọn:

1. **Project:** Maven hoặc Gradle; **Language:** Java; **Java:** 17 hoặc cao hơn.
2. **Dependencies:** **Spring Reactive Web** (WebFlux), **Spring Security**.
3. Thêm `spring-security-test` vào test dependencies nếu project generator chưa đưa vào; giữ `spring-boot-starter-test` và thêm `reactor-test` khi cần test `Mono`/`Flux`.
4. Đặt source Java dưới cùng một root package để `@SpringBootApplication` và `@SpringBootTest` dò được cấu hình.

Không thêm version riêng cho ba dependency chính khi sử dụng Spring Boot parent/BOM. Tự phối phiên bản Spring Security, Spring WebFlux, Reactor khác nhánh có thể gây `NoSuchMethodError`, xung đột class hoặc sai cấu hình test.

## 3. Cấu hình build bằng Maven: đầy đủ và có thể chạy

Cấu trúc file hoàn chỉnh của phần thực hành:

```text
reactive-security-setup/
├── pom.xml
└── src/
    ├── main/java/demo/reactivesecurity/
    │   ├── ReactiveSecurityApplication.java
    │   ├── SecurityConfiguration.java
    │   └── SampleController.java
    └── test/java/demo/reactivesecurity/
        └── ReactiveSecurityApplicationTests.java
```

### 3.1. File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactive-security-setup</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>reactive-security-setup</name>

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

Giải thích:

- `spring-boot-starter-parent` áp dụng quản lý version, cấu hình build và plugin phù hợp với phiên bản Spring Boot được chọn. Không cần điền `<version>` riêng cho `starter-webflux`, `starter-security`, `starter-test`, `spring-security-test` hoặc `reactor-test`.
- `spring-security-test` có `<scope>test</scope>`: class mock security được biên dịch và sử dụng trong test, không đóng gói thành dependency runtime của ứng dụng.
- `spring-boot-starter-test` là bộ khung test; `spring-security-test` là phần mở rộng về security.
- `reactor-test` không phải điều kiện bắt buộc để viết `WebTestClient` test đơn giản, nhưng nên có khi kiểm tra publisher bằng `StepVerifier`.

## 4. Nếu project dùng Gradle (Groovy DSL)

Thay `pom.xml` bằng `settings.gradle` và `build.gradle` dưới đây; **chỉ chọn một hệ build** cho ví dụ, không cần giữ cả Maven và Gradle trong cùng project.

**`settings.gradle`**

```groovy
rootProject.name = 'reactive-security-setup'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ở Gradle, `implementation` tương ứng dependencies cần khi biên dịch/chạy ứng dụng; `testImplementation` chỉ cần để biên dịch/chạy test. Spring Boot plugin phối hợp dependency management để dùng các phiên bản tương thích. Nếu dùng Kotlin DSL thì cú pháp khác; đoạn này dành cho `build.gradle` (Groovy).

## 5. Ứng dụng WebFlux mẫu: kiểm chứng các starter hoạt động chung

Các file Java sau dùng **package `demo.reactivesecurity`**. Sao chép đúng đường dẫn và package để các lớp được Spring Boot phát hiện.

### 5.1. `src/main/java/demo/reactivesecurity/ReactiveSecurityApplication.java`

```java
package demo.reactivesecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveSecurityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveSecurityApplication.class, args);
    }
}
```

`@SpringBootApplication` là điểm khởi động, tự động quét các class trong cùng package và các package con. Khi dependencies đúng, Boot khởi động WebFlux application với embedded Reactor Netty theo mặc định.

### 5.2. `src/main/java/demo/reactivesecurity/SecurityConfiguration.java`

```java
package demo.reactivesecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/reports").hasRole("READER")
                .anyExchange().authenticated()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .roles("READER")
            .build();

        UserDetails guest = User.withUsername("guest")
            .password("{noop}guest123")
            .roles("GUEST")
            .build();

        return new MapReactiveUserDetailsService(reader, guest);
    }
}
```

Các điểm cần hiểu:

- `@EnableWebFluxSecurity` bật cấu hình security cho WebFlux; Spring Security dùng **WebFilter** để tích hợp vào reactive web stack.
- `SecurityWebFilterChain` và `ServerHttpSecurity` là API reactive. Không thay bằng `SecurityFilterChain`, `HttpSecurity` hay `@EnableWebSecurity` của Servlet.
- `/api/public` được truy cập công khai; `/api/reports` cần role `READER`; đường dẫn còn lại cần người đã xác thực.
- `roles("READER")` cấp authority `ROLE_READER`; `hasRole("READER")` kiểm tra chuỗi `ROLE_READER` mặc định.
- `httpBasic` giúp chạy thử bằng HTTP Basic credentials; `formLogin` tắt để API demo không redirect tới trang HTML login.
- `MapReactiveUserDetailsService` là kho người dùng trong bộ nhớ, thích hợp cho demo/tài liệu học. Hệ thống thật thường dùng nguồn user và `PasswordEncoder` được cấu hình đúng.
- **`{noop}` chỉ dành cho ví dụ cục bộ:** nó chấp nhận mật khẩu không băm. Ứng dụng thật phải lưu hash mạnh (ví dụ BCrypt/Argon2), dùng HTTPS và tuyệt đối không commit mật khẩu vào source. Ví dụ không vô hiệu hóa CSRF; các request test bên dưới đều là GET.

Nếu chỉ thêm `starter-security` mà chưa tự khai báo rule, Spring Boot/Spring Security có thể bảo vệ tất cả request theo cấu hình mặc định, sử dụng user mặc định được sinh hoặc cung cấp theo cấu hình. Việc thấy 401 ngay sau khi thêm dependency là hành vi bảo vệ mặc định thường gặp, không phải WebFlux không hoạt động.

### 5.3. `src/main/java/demo/reactivesecurity/SampleController.java`

```java
package demo.reactivesecurity;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class SampleController {

    @GetMapping("/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public OK");
    }

    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("reports OK");
    }

    @GetMapping("/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(authentication -> "user: " + authentication.getName());
    }
}
```

`Mono<String>` thể hiện kiểu trả về reactive. Endpoint `/api/me` minh họa cách đọc chủ thể đã xác thực qua **Reactor security context**; không tự lấy danh tính từ query parameter, và không dựa vào `ThreadLocal` thường như một nguồn xuyên suốt pipeline.

## 6. Test Spring Security reactive bằng `spring-security-test`

Mục đích là xác minh được cả hai tình huống:

1. **Authentication thật:** gửi username/password bằng HTTP Basic, cho phép Security chain tự xác thực dựa trên `MapReactiveUserDetailsService`.
2. **Authorization cô lập:** dùng `mockUser()` để tạo authenticated principal giả cho một request, kiểm tra role mà không cần nhập mật khẩu hoặc gọi identity provider thật.

Trong ví dụ này dùng `@SpringBootTest` để nạp cấu hình ứng dụng thật, rồi liên kết `WebTestClient` với `ApplicationContext` và **`springSecurity()`** để kích hoạt security test support. Cách này không cần chạy server thật trên cổng TCP.

### 6.1. `src/test/java/demo/reactivesecurity/ReactiveSecurityApplicationTests.java`

```java
package demo.reactivesecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityApplicationTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAccessibleWithoutLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void reportsRequireAuthentication() {
        client.get().uri("/api/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void realBasicReaderCanReadReports() {
        client.get().uri("/api/reports")
            .headers(headers -> headers.setBasicAuth("reader", "reader123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void realBasicGuestIsForbidden() {
        client.get().uri("/api/reports")
            .headers(headers -> headers.setBasicAuth("guest", "guest123"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        client.get().uri("/api/reports")
            .headers(headers -> headers.setBasicAuth("reader", "wrong"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedReaderCanReadReports() {
        client.mutateWith(mockUser("alice").roles("READER"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("reports OK");
    }

    @Test
    void mockedGuestCannotReadReports() {
        client.mutateWith(mockUser("bob").roles("GUEST"))
            .get().uri("/api/reports")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Tại sao test này cần đủ ba starter/library đã nêu?**

- `WebTestClient` kiểm tra request/response theo kiểu WebFlux mà không đòi server thật. Đây là API của Spring Test dùng cùng WebFlux, không phải `MockMvc`.
- `@SpringBootTest`, `@Test`, `@BeforeEach` cần nền tảng test của Spring Boot và JUnit.
- `SecurityMockServerConfigurers.springSecurity()` và `mockUser()` nằm trong **`spring-security-test`**. Nếu thiếu dependency test này, import hai method sẽ không biên dịch.
- `mockUser("alice").roles("READER")` tạo request với người dùng giả đã xác thực và authority `ROLE_READER`. Nó **không** kiểm thử cơ chế kiểm tra mật khẩu thật.
- Test gửi Basic credentials mới kiểm tra bước xác thực dựa trên `UserDetails` và mật khẩu; test mock user chủ yếu kiểm tra authorization rule.
- `@SpringBootTest` + `bindToApplicationContext` giữ cả `SecurityConfiguration` trong context. Khi dùng `@WebFluxTest` để chỉ load controller, phải `@Import(SecurityConfiguration.class)` nếu muốn kiểm tra chính sách custom này; slice test không tự nạp mọi cấu hình ứng dụng.

### 6.2. Ma trận kết quả và cách đọc lỗi

| Test | Principal/credentials | Quy tắc | HTTP dự kiến |
| --- | --- | --- | --- |
| `publicEndpointIsAccessibleWithoutLogin` | Không có | `permitAll` | **200** |
| `reportsRequireAuthentication` | Không có | Endpoint yêu cầu `ROLE_READER` | **401** |
| `realBasicReaderCanReadReports` | Basic `reader` đúng mật khẩu | Có `ROLE_READER` | **200** |
| `realBasicGuestIsForbidden` | Basic `guest` đúng mật khẩu | Chỉ có `ROLE_GUEST` | **403** |
| `wrongPasswordIsUnauthorized` | Basic sai mật khẩu | Xác thực thất bại | **401** |
| `mockedReaderCanReadReports` | Mock `alice`, role `READER` | Có `ROLE_READER` | **200** |
| `mockedGuestCannotReadReports` | Mock `bob`, role `GUEST` | Thiếu `ROLE_READER` | **403** |

**401**: chưa chứng minh được danh tính hợp lệ cho tài nguyên được bảo vệ. **403**: danh tính đã được chấp nhận nhưng không đủ quyền trong chính sách này. Test nên phân biệt rõ hai tình huống, không chỉ khẳng định "request thất bại".

### 6.3. Các công cụ test khác nên biết

- **`@WithMockUser(username = "alice", roles = "READER")`:** một cách khác để đặt security context giả cho test. Với WebFlux cần bảo đảm Spring Security Test được tích hợp vào test context/`WebTestClient`; ví dụ chính dùng `mockUser` để thể hiện rõ cách áp dụng theo từng request.
- **`mockUser().authorities(...)`:** hữu ích nếu policy dùng quyền chi tiết như `report:read`, không phải role. `roles("READER")` và `authorities(new SimpleGrantedAuthority("report:read"))` biểu diễn hai quy tắc khác nhau.
- **`csrf()`:** khi viết test POST/PUT/PATCH/DELETE trong ứng dụng có CSRF protection, một request hợp lệ có thể cần `client.mutateWith(csrf())` trước `.post()`. Không tắt CSRF chỉ để làm test xanh; quyết định chính sách CSRF dựa trên cookie/session/bearer và mô hình client.
- **`mockJwt()`:** chỉ áp dụng khi có cấu hình OAuth2 Resource Server thích hợp; không tự trở thành cơ chế xác thực JWT thật chỉ vì đã thêm `spring-security-test`.
- **`StepVerifier`:** kiểm thử trình tự tín hiệu của `Mono`/`Flux` ở unit test, bổ sung cho test HTTP bằng `WebTestClient`.
- **`@AutoConfigureWebTestClient`:** Spring Boot có thể tự cấp `WebTestClient` cho `@SpringBootTest`; ví dụ đang dùng cách `bindToApplicationContext(...).apply(springSecurity())` để thể hiện việc lắp ghép Spring Security Test tường minh.

Ví dụ bổ sung **chỉ minh họa cho một publisher đơn giản**, chạy được nếu đặt trong test class có dependency `reactor-test`:

```java
// Ví dụ method trong một lớp JUnit test có import Mono và StepVerifier:
@Test
void monoEmitsOneValueAndCompletes() {
    StepVerifier.create(Mono.just("ready"))
        .expectNext("ready")
        .verifyComplete();
}
```

Để sử dụng, thêm import `org.junit.jupiter.api.Test`, `reactor.core.publisher.Mono` và `reactor.test.StepVerifier` vào file test tương ứng. Đoạn này không thay thế việc test bảo mật HTTP.

## 7. Chạy dự án, đọc kết quả và xác minh dependencies

### 7.1. Kiểm tra môi trường

```bash
java -version
mvn -version
```

Kỳ vọng `java -version` hiển thị Java 17 hoặc cao hơn và `mvn -version` dùng JDK tương thích. Nếu sử dụng wrapper `mvnw` do Spring Initializr tạo, dùng `./mvnw` (Linux/macOS) hoặc `.\mvnw.cmd` (Windows) thay cho `mvn`.

### 7.2. Chạy test

```bash
mvn clean test
```

Kết quả logic cần đạt: **7 test chạy thành công, 0 test thất bại, 0 lỗi**. Ghi nhớ rằng dòng output Maven (thời gian, tên JUnit provider, số plugin) thay đổi theo môi trường; hãy kiểm tra dòng `BUILD SUCCESS` và báo cáo trong `target/surefire-reports/`.

Nếu dùng Gradle:

```bash
gradle test
```

Khi đã có Gradle wrapper, dùng `./gradlew test` trên Linux/macOS hoặc `.\gradlew.bat test` trên Windows. Xem kết quả HTML tại `build/reports/tests/test/index.html`.

### 7.3. Khởi động server và gọi API thủ công

```bash
mvn spring-boot:run
```

Trong terminal khác:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/reports
curl -i -u guest:guest123 http://localhost:8080/api/reports
curl -i -u reader:reader123 http://localhost:8080/api/me
```

Trên Windows PowerShell, dùng `curl.exe` thay cho `curl` nếu `curl` bị ánh xạ sang lệnh PowerShell khác.

Kết quả mong đợi:

| HTTP request | Status | Body ở trường hợp thành công |
| --- | --- | --- |
| `GET /api/public`, không credentials | 200 | `public OK` |
| `GET /api/reports`, không credentials | 401 | Không cố định |
| `GET /api/reports` với `reader:reader123` | 200 | `reports OK` |
| `GET /api/reports` với `guest:guest123` | 403 | Không cố định |
| `GET /api/me` với `reader:reader123` | 200 | `user: reader` |

Không dựa vào toàn bộ response header hoặc body của lỗi 401/403 để xác nhận bài học: format lỗi có thể được Spring Boot/Spring Security thay đổi bởi cấu hình exception handling.

### 7.4. Kiểm tra classpath đúng scope

Với Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.security
```

Với Gradle:

```bash
gradle dependencies --configuration runtimeClasspath
gradle dependencies --configuration testRuntimeClasspath
```

Hãy tìm `spring-security-test` trong **test** classpath; nó không cần xuất hiện trong runtime classpath đóng gói của ứng dụng. `spring-security-test` thuộc test vì ứng dụng production không dùng `mockUser` để quyết định quyền.

## 8. Những lỗi cấu hình phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Import `mockUser` hoặc `springSecurity` không tìm thấy | Thiếu `spring-security-test` ở test dependencies, nhầm package Servlet | Thêm artifact `org.springframework.security:spring-security-test` với test scope, import `...test.web.reactive.server.SecurityMockServerConfigurers` |
| Không tìm thấy `@Test` / `@SpringBootTest` | Thiếu `spring-boot-starter-test` | Khai báo starter test và chạy bằng JUnit Platform |
| Dùng `MockMvc`, `HttpSecurity`, `SecurityFilterChain` trong demo WebFlux | Nhầm stack Servlet với reactive | Dùng `WebTestClient`, `ServerHttpSecurity`, `SecurityWebFilterChain` |
| Request công khai trả 401 | Chưa có rule `permitAll`, path không khớp hoặc cấu hình security chưa được nạp | Kiểm tra chain, thứ tự `pathMatchers` và chính xác URL |
| Người dùng đúng mật khẩu nhưng nhận 403 | Đã xác thực, thiếu role/authority | Xem `hasRole("READER")` cần `ROLE_READER`; kiểm tra `roles`/`authorities` |
| Có role `READER` nhưng gửi chuỗi `READER` trong `hasAuthority` | Nhầm `hasRole` và `hasAuthority` | Với role dùng `hasRole("READER")` hoặc `hasAuthority("ROLE_READER")` |
| Test mock user pass nhưng login thật 401 | Test `mockUser` đã bỏ qua xác minh credentials | Thêm test HTTP Basic/JWT thật ở cấp integration, kiểm tra user store/password encoder |
| Test `@WebFluxTest` khác chính sách security production | Slice test không tự mang tất cả cấu hình custom | Import SecurityConfiguration cần kiểm tra hoặc dùng `@SpringBootTest` |
| POST đã có quyền nhưng vẫn nhận 403 | Thiếu CSRF token khi cơ chế CSRF đang bật | Dùng `csrf()` trong security test phù hợp; thiết kế CSRF theo kiểu client thực |
| `NoSuchMethodError` khi test hoặc chạy | Ép version Spring Security, Reactor hoặc Spring Framework lệch Spring Boot BOM | Bỏ version không cần thiết, kiểm tra cây dependencies và build lại |
| Ứng dụng chạy bằng MVC dù đã thêm WebFlux | Có cả `spring-boot-starter-web` | Chọn chủ động một web stack; demo reactive chỉ cần `starter-webflux` |
| `ClassNotFoundException` test helper khi chạy production | Đưa `spring-security-test` vào main source hoặc runtime | Chỉ dùng helper trong `src/test/java` với test scope |
| Dự án dùng `block()` trong handler reactive | Logic chặn thread/event loop | Dùng operators của Reactor, thiết kế repository/client reactive phù hợp |
| Tests chỉ phủ đường dẫn thành công | Thiếu coverage cho truy cập trái phép | Thêm 401, 403, sai mật khẩu, đúng/sai role và tài nguyên không thuộc chủ thể |

### Checklist tự kiểm tra sau khi tạo project

- [ ] Build chọn đúng **WebFlux**, không kéo MVC/Servlet vào tình cờ.
- [ ] Dependency chạy ứng dụng gồm `starter-webflux` và `starter-security`.
- [ ] Dependency test gồm `starter-test` và `spring-security-test`, cùng `reactor-test` nếu test publisher.
- [ ] Spring Boot quản lý version của Spring Security và Reactor.
- [ ] Có `SecurityWebFilterChain` và tối thiểu một rule `permitAll`, một rule yêu cầu quyền.
- [ ] Có test **không đăng nhập → 401**, **đúng quyền → 200**, **thiếu quyền → 403**.
- [ ] Có test dùng **credentials thật** và test dùng **mock user**; hiểu chúng chứng minh điều gì khác nhau.
- [ ] Không dùng `{noop}` hoặc mật khẩu cứng trong môi trường thực.

## 9. Câu hỏi tự kiểm tra

**Câu 1.** Nếu chỉ có `spring-boot-starter-webflux` mà không có `spring-boot-starter-security`, Spring WebFlux có tự áp dụng `hasRole` không?  
**Trả lời:** Không. WebFlux cung cấp xử lý HTTP reactive, còn cơ chế authorization thuộc Spring Security.

**Câu 2.** Vì sao `spring-security-test` được đặt trong `test` scope?  
**Trả lời:** Vì nó cung cấp các công cụ mô phỏng, thiết lập và kiểm tra security phục vụ thử nghiệm, không phải thành phần xác thực người dùng production.

**Câu 3.** Test dùng `mockUser("alice").roles("READER")` trả 200 có chứng minh mật khẩu của Alice đúng không?  
**Trả lời:** Không. Nó chứng minh rule cho phép principal giả với role tương ứng; cần test thực qua HTTP Basic/identity provider để kiểm tra credential flow.

**Câu 4.** Có cần tắt CSRF để GET `/api/reports` trong ví dụ chạy được không?  
**Trả lời:** Không. Bài thực hành chỉ dùng GET. CSRF là vấn đề đặc biệt cần kiểm tra với các request thay đổi trạng thái, nhất là ứng dụng xác thực bằng cookie/session.

**Câu 5.** Tại sao cùng là Spring Security nhưng ứng dụng reactive cần `SecurityWebFilterChain`?  
**Trả lời:** Vì WebFlux sử dụng chuỗi reactive `WebFilter` và Reactor `Context`, khác mô hình Servlet filter của Spring MVC.

## 10. Tài liệu chính thức và điểm ghi nhớ

- Spring Security – WebFlux Security: https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html
- Spring Security – Getting Started with WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/getting-started.html
- Spring Security – WebTestClient Security Setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security – Testing Authentication: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security – Testing with CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot – System Requirements (3.5): https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Initializr: https://start.spring.io/

**Ghi nhớ:** `starter-webflux` dựng nền web reactive; `starter-security` bảo vệ request bằng reactive security chain; `spring-security-test` phối hợp với `starter-test` để xác minh quyền và danh tính bằng `WebTestClient`. Một project được thiết lập đúng cần kiểm tra cả **khả năng chạy** lẫn **hành vi 200/401/403**, đồng thời phân biệt test xác thực thật với test mô phỏng người dùng.
