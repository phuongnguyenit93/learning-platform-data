# Xây luồng xác thực WebFlux với nguồn người dùng reactive

## 1. Mục tiêu bài thực hành tổng hợp

Trong ứng dụng Spring WebFlux, xác thực không chỉ là viết một hàm so sánh mật khẩu. Luồng đăng nhập cần phối hợp **ReactiveUserDetailsService**, **ReactiveAuthenticationManager**, **SecurityWebFilterChain**, nguồn dữ liệu reactive và cơ chế lưu SecurityContext. Nếu nguồn người dùng là database R2DBC, lời gọi tìm user phải trả về `Mono<UserDetails>` và không được chặn luồng event loop.

Bài này xây dựng một ứng dụng Spring Boot 3.x / Spring Security 6.x / Java 17+ có:

1. Nguồn user reactive dựa trên **Spring Data R2DBC** và bảng `app_user`.
2. Form login do **Spring Security WebFlux** xử lý; không tự so password trong controller.
3. Mật khẩu lưu dạng **BCrypt hash**, quyền `ROLE_READER` hoặc `ROLE_ADMIN` lấy từ dữ liệu được server kiểm soát.
4. Endpoint `GET /me` cho user authenticated và `GET /admin/panel` cần role ADMIN.
5. Phiên WebFlux với `WebSession`, CSRF cho form login và request sau đăng nhập.
6. Kiểm thử bằng `WebTestClient`: login thật → lấy cookie phiên → GET /me trong request mới; sai password; thiếu CSRF; thiếu role.
7. Phân biệt **authentication**, **authorization**, **reactive context**, **blocking password hash** và **reactive database I/O**.
8. Kế hoạch chuyển từ database H2 dùng cho lab sang PostgreSQL R2DBC, session store phân tán, TLS, rate limit, monitoring và kiểm thử tải.

Mẫu dùng **Spring Boot 3.5.x + Spring Security 6.5.x**, với ví dụ Gradle cho một phiên bản cụ thể trong nhánh Boot 3.5. Đây là bài **WebFlux/Reactive**: không sử dụng `HttpSecurity`, `SecurityFilterChain` của Servlet, `HttpSession` hoặc `UsernamePasswordAuthenticationFilter` để ghép sai hai mô hình.

**Điều phải nhớ:** reactive **không đồng nghĩa** mọi tác vụ đều phi blocking. R2DBC cung cấp API truy vấn database không blocking, còn BCrypt/Argon2 là công việc CPU intensive cần cách sắp xếp scheduler hợp lý. Việc trả `Mono` từ một hàm vẫn có thể chặn event loop nếu bên trong nó gọi JDBC, `Thread.sleep` hoặc `block()`.

## 2. So sánh ngắn Spring MVC Security và WebFlux Security

| Vấn đề | Servlet / Spring MVC | Reactive / Spring WebFlux |
| --- | --- | --- |
| Web pipeline | `SecurityFilterChain`, servlet filters | `SecurityWebFilterChain`, WebFilters |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| User lookup | `UserDetailsService.loadUserByUsername` | `ReactiveUserDetailsService.findByUsername` |
| Kiểu kết quả user | `UserDetails` | `Mono<UserDetails>` |
| Context của request | Thường `SecurityContextHolder` / thread-local | `ReactiveSecurityContextHolder` / Reactor Context |
| HTTP request | `HttpServletRequest` | `ServerWebExchange` |
| Session | `HttpSession` | `WebSession` |
| Repository session security | `SecurityContextRepository` | `ServerSecurityContextRepository` |
| Security filter login form | `UsernamePasswordAuthenticationFilter` | `AuthenticationWebFilter` |
| Test HTTP | `MockMvc` | `WebTestClient` |
| Data source hợp với flow | JDBC/JPA (blocking) | R2DBC/Reactive repository |

Nếu trộn `spring-boot-starter-web` (MVC) với `spring-boot-starter-webflux` mà không xác định web application type, Spring Boot có thể ưu tiên Servlet stack. Bài này dùng **chỉ** `spring-boot-starter-webflux`, chủ động cấu hình `spring.main.web-application-type: reactive` trong lab và không khai báo `@EnableWebSecurity` của Servlet.

Đây là **hai cấu hình bảo mật khác nhau**, không phải tên lớp được đổi cho giống nhau. `SecurityContextHolder.getContext()` ở một reactive callback có thể không trả context mong muốn; lấy identity qua `ReactiveSecurityContextHolder.getContext()` hoặc các API WebFlux có hỗ trợ principal/context.

## 3. Kiến trúc: người dùng reactive đi qua các tầng nào?

```text
Browser                         Spring WebFlux / Reactor            R2DBC DB
   │                                       │                            │
   │ GET /login                            │                            │
   ├──────────────────────────────────────>│ Login page + CSRF          │
   │<──────────────────────────────────────┤                            │
   │ POST /login + username,password,CSRF  │                            │
   ├──────────────────────────────────────>│ AuthenticationWebFilter   │
   │                                       │   │                        │
   │                                       │   ▼                        │
   │                                       │ ReactiveAuthenticationMgr │
   │                                       │   │                        │
   │                                       │   ▼                        │
   │                                       │ ReactiveUserDetailsService│
   │                                       │   │ findByUsername -> Mono│
   │                                       │   ├───────────────────────>│
   │                                       │   │   password_hash,roles  │
   │                                       │   │<───────────────────────┤
   │                                       │   ▼                        │
   │                                       │ PasswordEncoder.matches   │
   │                                       │   │                        │
   │                                       │   ▼                        │
   │                                       │ authenticated Authentication
   │                                       │   │                        │
   │                                       │ save SecurityContext to WebSession
   │<──────────────────────────────────────┤ 302 + session cookie       │
   │ GET /me + same session cookie          │                            │
   ├──────────────────────────────────────>│ load context, authorize   │
   │<──────────────────────────────────────┤ 200 JSON username + role  │
```

Không có controller `POST /login` tự tạo trong mẫu: **formLogin của Spring Security** sở hữu endpoint này. Controller chỉ phục vụ dữ liệu sau khi filter xác thực và authorization cho phép.

### 3.1. Bất biến quan trọng của flow

- Một `username/password` do browser gửi là **credential chưa được tin**.
- User record lấy từ DB là dữ liệu server-side; password hash **không** được trả về API.
- Authentication thành công chỉ khi password hash khớp, tài khoản được phép sử dụng và policy khác (nếu có) đạt.
- Role lấy từ user record/mapping có kiểm soát; client không thể tự gửi `role=ADMIN` để nâng quyền.
- Với browser session, request thứ hai dùng cookie phiên được cấp sau login; không gửi lại password.
- Với resource server stateless, request sau phải mang token hợp lệ riêng; không nhầm mô hình với lưu `WebSession`.

## 4. Những interface quan trọng

### 4.1. ReactiveUserDetailsService

Hợp đồng cốt lõi:

```java
Mono<UserDetails> findByUsername(String username);
```

Đây là **chữ ký mô tả API**, không phải file Java độc lập. Khi không có user, trả `Mono.empty()`. Khi DB lỗi, trả `Mono.error(...)`, **không** chuyển mọi network timeout thành `Mono.empty()` rồi nói user sai password. Manager chịu trách nhiệm phân biệt xác thực bị từ chối và lỗi backend.

### 4.2. ReactiveAuthenticationManager

Hợp đồng:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

Đối với username/password, `UserDetailsRepositoryReactiveAuthenticationManager` dùng `ReactiveUserDetailsService` để lấy `UserDetails` và dùng `PasswordEncoder` để kiểm credential. Khi sai, pipeline có thể phát authentication exception theo framework; khi thành công, `Authentication` được cấp authorities của user.

### 4.3. SecurityWebFilterChain

Định nghĩa đường dẫn nào public, đường dẫn nào cần role, bật form login và logout, dùng authentication manager nào. `.authorizeExchange(...)` là API WebFlux; không dùng `.authorizeHttpRequests(...)` của Servlet.

### 4.4. ReactiveSecurityContextHolder

Là lối vào `SecurityContext` bằng **Reactor Context**, không phải kho user của toàn ứng dụng. Không nên lưu Authentication trong biến static hoặc singleton field. Khi reactive publisher đổi scheduler hoặc có asynchronous boundary, cần giữ chuỗi Reactor phù hợp để framework quản lý context propagation.

## 5. Chuẩn bị project Spring Boot 3.5.x, Java 17

Bài dùng H2/R2DBC trong bộ nhớ để học, **không phải kho identity production**. Một dự án Gradle mới có các file:

```text
reactive-auth-lab/
  build.gradle
  settings.gradle
  src/main/java/com/example/reactiveauth/
    ReactiveAuthApplication.java
    AccountRow.java
    AccountRepository.java
    DatabaseUserDetailsService.java
    SecurityConfig.java
    IdentityController.java
    LabSeedConfig.java
  src/main/resources/
    application.yml
    schema.sql
  src/test/java/com/example/reactiveauth/
    ReactiveAuthFlowTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'reactive-auth-lab'
```

**`build.gradle`** — ví dụ dùng Boot 3.5.6 với dependency management tương ứng; giữ dependency versions theo BOM khi nâng cấp:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'

    runtimeOnly 'io.r2dbc:r2dbc-h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-data-r2dbc` cung cấp Spring Data R2DBC/ReactiveCrudRepository và connection factory; `r2dbc-h2` là driver thử nghiệm. Không thêm JDBC/JPA vào request path. Khi chuyển sang PostgreSQL dùng R2DBC driver tương ứng và quản lý migration.

Cần JDK 17+ và một Gradle wrapper do project tạo. Chạy lệnh tương ứng trong thư mục dự án, không mặc định đã có wrapper nếu chỉ copy các khối văn bản.

## 6. Cấu hình reactive database, session và seed thử nghiệm

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: reactive
  r2dbc:
    url: "r2dbc:h2:mem:///reactive_auth?options=DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
    username: sa
  sql:
    init:
      mode: always

server:
  port: 8080

demo:
  seed-enabled: ${DEMO_SEED_ENABLED:false}
  seed-password: ${DEMO_SEED_PASSWORD:}
```

Giải thích:

- `web-application-type: reactive` làm rõ stack WebFlux cho lab; không phải cách khắc phục mọi classpath conflict trong một hệ thống lớn.
- `r2dbc:h2:mem:///reactive_auth?...` là H2 in-memory qua R2DBC. `DB_CLOSE_DELAY=-1` giúp database không tự biến mất chỉ vì đóng connection cuối. Với dữ liệu thật, dùng DB server bền vững.
- `spring.sql.init.mode: always` bảo Spring Boot chạy `schema.sql` trong môi trường này, gồm R2DBC `ConnectionFactory`. **Production** nên dùng migration quản lý phiên bản, không tự chạy DDL mỗi lần restart.
- `DEMO_SEED_ENABLED` mặc định false. Nếu true, cần cung cấp `DEMO_SEED_PASSWORD` riêng; không commit mật khẩu mẫu thật.
- Việc cấp demo credential qua environment cho lab chỉ để tái hiện bài tập; với production dùng secret manager và không đăng seed bean này.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS app_user (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(120) NOT NULL,
    enabled BOOLEAN NOT NULL,
    role VARCHAR(30) NOT NULL
);
```

Đối với lab, một user có một role để code gọn; production có thể tách `user_role` và permission tables, tenant binding, account states, lịch sử password, MFA factors. Không nhận role trực tiếp từ body login.

## 7. Entity và repository thật sự reactive

**`AccountRow.java`**

```java
package com.example.reactiveauth;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("app_user")
public record AccountRow(
        @Id Long id,
        String username,
        @Column("password_hash") String passwordHash,
        boolean enabled,
        String role
) {}
```

**`AccountRepository.java`**

```java
package com.example.reactiveauth;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface AccountRepository
        extends ReactiveCrudRepository<AccountRow, Long> {

    Mono<AccountRow> findByUsername(String username);

    Mono<Boolean> existsByUsername(String username);
}
```

**Ý nghĩa:**

- `findByUsername(...)` là query method do Spring Data R2DBC triển khai dựa trên property `username`.
- `Mono<AccountRow>` đại diện cho 0 hoặc 1 user; repository không trả list người dùng.
- `@Column("password_hash")` ánh xạ hash trong SQL vào trường `passwordHash`.
- `ReactiveCrudRepository` không phải interface JPA blocking; kết quả chỉ chạy khi publisher được subscribe.
- Chỉ lưu hash, không lưu mật khẩu thô. Password hash không được đưa vào JSON response, audit log, tracing payload hay metric label.
- Index UNIQUE trên username có giá trị bảo mật: không được có hai accounts khác nhau cùng khóa tra cứu nếu thiết kế login chỉ dùng username. Với multi-tenant, khóa chính sách có thể là (tenant_id, normalized_username) thay vì username global.

### 7.1. Vì sao không gọi block() trong service?

Sai lầm:

```java
// PHẢN VÍ DỤ: không dùng trên WebFlux event loop.
AccountRow row = repository.findByUsername(username).block();
return Mono.just(toUserDetails(row));
```

Khi dùng `block()` trong reactive HTTP request, bạn có thể chặn event-loop và gặp lỗi của Reactor đối với non-blocking threads. Dùng các phép toán Reactor như `map`, `flatMap`, `switchIfEmpty`, `onErrorResume` theo semantics đúng.

**Không giải quyết bằng cách đổi return type thành Mono mà bên trong vẫn gọi JDBC/JPA.** Một truy vấn blocking phải được di chuyển sang scheduler phù hợp như boundedElastic nếu đang chuyển đổi hệ thống, nhưng giải pháp mục tiêu ở bài này là **R2DBC** cho phần user lookup.

## 8. ReactiveUserDetailsService lấy user từ R2DBC

**`DatabaseUserDetailsService.java`**

```java
package com.example.reactiveauth;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public final class DatabaseUserDetailsService
        implements ReactiveUserDetailsService {

    private final AccountRepository accounts;

    public DatabaseUserDetailsService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return accounts.findByUsername(username)
                .map(row -> {
                    String authority = switch (row.role()) {
                        case "READER" -> "ROLE_READER";
                        case "ADMIN" -> "ROLE_ADMIN";
                        default -> throw new IllegalStateException(
                                "Unsupported stored account role");
                    };

                    return User.withUsername(row.username())
                            .password(row.passwordHash())
                            .authorities(authority)
                            .disabled(!row.enabled())
                            .build();
                });
    }
}
```

**Tại sao code này phù hợp reactive?**

1. Từ username do login filter gửi, gọi repository trả `Mono<AccountRow>`.
2. `map(...)` chuyển bản ghi DB thành `UserDetails` một cách **đồng bộ, ngắn, không I/O** trong callback.
3. User không tồn tại → Mono rỗng, để authentication manager xử lý rejection.
4. Account bị disable → `UserDetails.isEnabled()==false`; manager có thể từ chối trước khi cấp authenticated token.
5. Role được ánh xạ từ một whitelist server-side; role không hợp lệ → exception/fail closed, không gán tạm ROLE_ADMIN hoặc ROLE_USER.
6. Password hash được giữ trong `UserDetails` để manager kiểm `PasswordEncoder.matches(...)`; controller không bao giờ nhìn thấy nó.

**Cần hiểu về thông báo lỗi:** `Mono.empty()` là “không tìm thấy account”. `Mono.error(R2dbc...Exception)` là lỗi truy vấn/đường truyền. Không viết `.onErrorResume(ex -> Mono.empty())` trên mọi exception: nó có thể làm DB outage biến thành “sai mật khẩu”, gây khó chẩn đoán và rủi ro retry/lockout.

### 8.1. Canonical username và chống enumeration

- Normalize username theo **cùng quy tắc** tại lúc tạo account và lúc tìm kiếm (case sensitivity, Unicode, email alias, tenant).
- Giới hạn độ dài input và số attempts trước truy vấn để tránh attacker tạo nhiều lookups.
- Không trả public “username không tồn tại” khác với “password sai”.
- Không ghi username/password thô vào log hoặc metric labels.
- Với privileged accounts/tenant, thêm account status, password expiry, breached password checks, MFA/risk policy ở tầng bảo mật phù hợp.
- Nếu mapping quyền cần query thứ hai, phải dùng `flatMap(row -> roleRepository...collectList().map(...))`, không lấy role bằng blocking DAO bên trong `map`.

## 9. PasswordEncoder và ReactiveAuthenticationManager

**`SecurityConfig.java`** dưới đây kết hợp authentication manager và chính sách WebFlux:

```java
package com.example.reactiveauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            ReactiveUserDetailsService userService,
            PasswordEncoder passwordEncoder) {

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(
                        userService);
        manager.setPasswordEncoder(passwordEncoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain webFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
                .authenticationManager(authenticationManager)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/", "/error", "/login").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .pathMatchers("/me").authenticated()
                        .anyExchange().denyAll())
                .formLogin(Customizer.withDefaults())
                .logout(Customizer.withDefaults())
                .build();
    }
}
```

**Giải thích quan hệ các thành phần:**

- `UserDetailsRepositoryReactiveAuthenticationManager` là implementation của `ReactiveAuthenticationManager`, dùng `ReactiveUserDetailsService` để tìm user/password hash.
- `setPasswordEncoder(...)` phải phù hợp với thuật toán/hash đã lưu. Không dùng `NoOpPasswordEncoder` hoặc so sánh plaintext trong ứng dụng thật.
- `ServerHttpSecurity.authenticationManager(...)` đặt manager cho chain; form login dùng manager thích hợp để xử lý username/password.
- `.authorizeExchange(...)` đặt quyền: root public, `/me` cần authenticated, `/admin/**` cần ROLE_ADMIN; các đường dẫn khác mặc định bị từ chối.
- `.formLogin(...)` bật giao diện login mặc định và filter xác thực form, không phải controller tự làm.
- `.logout(...)` bật logout theo framework; với browser session và CSRF, logout state-changing request thường cần POST kèm CSRF.
- Không gọi `.csrf(disable)`, vì đây là **web browser dùng session cookie**. CSRF protection WebFlux mặc định được giữ.
- Với mặc định của Spring Security, form login thành công có thể lưu Authentication vào `WebSession`, cho request sau sử dụng cùng session cookie.
- `@EnableWebFluxSecurity` và `SecurityWebFilterChain` là API reactive; không đặt thêm Servlet `@EnableWebSecurity` trên cùng demo.

### 9.1. BCrypt vẫn tốn CPU

PasswordEncoder.matches là công việc CPU-intensive. Spring Security `AbstractUserDetailsReactiveAuthenticationManager` có scheduler hỗ trợ password encoding/checking; **R2DBC giúp truy vấn không blocking nhưng không làm BCrypt thành network I/O phi blocking**.

Nếu kiểm password ở code custom (không dùng manager chuẩn), tuyệt đối tránh chạy `matches(...)` ngay trên Netty event loop với tải lớn. Cần bounded CPU scheduling, rate limit và load test. Đừng tự bọc tất cả publisher trong `subscribeOn(boundedElastic())` khi không hiểu demand: điều đó có thể che blocking thay vì giải quyết kiến trúc.

## 10. Khởi động ứng dụng và seed một account lab

**`ReactiveAuthApplication.java`**

```java
package com.example.reactiveauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveAuthApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAuthApplication.class, args);
    }
}
```

Để có người dùng thử nghiệm, thêm bean seed **chỉ khi cấu hình lab bật**.

**`LabSeedConfig.java`**

```java
package com.example.reactiveauth;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class LabSeedConfig {

    @Bean
    ApplicationRunner seedLabUser(
            AccountRepository repository,
            PasswordEncoder encoder,
            @Value("${demo.seed-enabled:false}") boolean enabled,
            @Value("${demo.seed-password:}") String password) {

        return args -> {
            if (!enabled) {
                return;
            }
            if (password == null || password.length() < 12) {
                throw new IllegalStateException(
                        "Set a separate lab password of at least 12 characters");
            }

            // CHỈ startup runner, KHÔNG chạy trong reactive request callback.
            boolean exists = Boolean.TRUE.equals(
                    repository.existsByUsername("alice")
                            .block(Duration.ofSeconds(5)));

            if (!exists) {
                AccountRow account = new AccountRow(
                        null,
                        "alice",
                        encoder.encode(password),
                        true,
                        "READER");

                repository.save(account)
                        .block(Duration.ofSeconds(10));
            }
        };
    }
}
```

**Phân biệt kỹ:** đoạn `block(Duration)` xuất hiện **chỉ trong ApplicationRunner khởi tạo lab**, tức lúc startup trên luồng vận hành, không nằm trong `ReactiveUserDetailsService` hoặc HTTP event loop. Nó có timeouts để tránh vô hạn. Không copy cách seed blocking này vào login handler. Với production, account provisioning phải là luồng riêng có migration/transaction/approval và không dùng seed từ một biến môi trường toàn cục.

Lưu ý concurrency: nếu bật cùng seed trên hai instances lần đầu chạy, cùng thấy chưa có Alice rồi cùng insert; UNIQUE constraint sẽ làm một bên thất bại. Đây là **demo single-instance H2**, không phải cơ chế provisioning đa node. Trong hệ thống thật, dùng migration/provisioning idempotent với transaction/constraint và theo dõi race.

### 10.1. Chạy demo

Bash:

```bash
export DEMO_SEED_ENABLED=true
export DEMO_SEED_PASSWORD='local-lab-strong-passphrase-2026'
./gradlew bootRun
```

Windows PowerShell:

```powershell
$env:DEMO_SEED_ENABLED = "true"
$env:DEMO_SEED_PASSWORD = "local-lab-strong-passphrase-2026"
.\gradlew.bat bootRun
```

Các chuỗi trên **chỉ dùng ở môi trường học tập cục bộ**. Chạy app public với account seed/mật khẩu trong bài là không an toàn. Tạo password riêng từ secret manager cho staging/prod, không ghi giá trị thật vào source code, shell history hoặc CI logs.

Với cấu hình lab, `schema.sql` được chạy và `alice` được lưu với BCrypt hash. Sau restart, vì dùng H2 in-memory, dữ liệu được tạo lại theo cấu hình; không kỳ vọng persistence sau restart. Truy cập `http://localhost:8080/login` để xem login form mặc định.

## 11. Controller reactive: lấy Authentication từ Reactor Context

**`IdentityController.java`**

```java
package com.example.reactiveauth;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("Home: public");
    }

    @GetMapping("/me")
    public Mono<Map<String, Object>> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> {
                    List<String> roles =
                            authentication.getAuthorities().stream()
                                    .map(GrantedAuthority::getAuthority)
                                    .sorted()
                                    .toList();

                    return Map.<String, Object>of(
                            "username", authentication.getName(),
                            "authenticated", authentication.isAuthenticated(),
                            "authorities", roles);
                });
    }

    @GetMapping("/admin/panel")
    public Mono<String> admin() {
        return Mono.just("Admin: permitted");
    }
}
```

Request `GET /me` chỉ chạy controller sau khi `.authenticated()` cho phép. Code không tự nhận username từ query/header, không gọi `block()` và không dùng `SecurityContextHolder.getContext()` theo kiểu thread-local của MVC.

Response kỳ vọng sau khi Alice login:

```json
{
  "username": "alice",
  "authenticated": true,
  "authorities": ["ROLE_READER"]
}
```

Đây là dữ liệu **kỳ vọng của demo**, không phải output đã chạy trong một repository cụ thể. Endpoint học tập trả authorities để dễ quan sát; production nên xem xét không expose chi tiết quyền nội bộ và tuyệt đối không serialize toàn bộ principal/password hash/token.

### 11.1. Reactor Context và scheduler

`ReactiveSecurityContextHolder.getContext()` đọc SecurityContext từ subscriber context được Spring Security quản lý. Nếu code tạo publisher rời rạc rồi tự gọi `subscribe()` trong controller/service, hoặc tự chuyển data sang callback ngoài pipeline mà không quản context, SecurityContext và việc xử lý lỗi có thể không còn liên kết đúng request.

**Cách đúng:** trả publisher và để WebFlux subscribe; nếu cần gọi service, dùng `flatMap`/`map` trên cùng chain.

```java
// Snippet hợp lệ bên trong một reactive service:
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .flatMap(authentication ->
                accountService.findSummary(authentication.getName()));
```

Đoạn này cần `accountService.findSummary(...)` trả `Mono<...>` và phải kiểm ownership/tenant ở service. Không dùng thông tin principal để bỏ qua object-level authorization.

## 12. Từ browser đến WebSession: request thứ hai kiểm điều gì?

Form login WebFlux thông thường có hai request:

```text
GET /login
  → HTML login form có CSRF token và session cookie khi cần

POST /login
  Content-Type: application/x-www-form-urlencoded
  username=alice
  password=...
  _csrf=...
  → AuthenticationWebFilter
  → DB lookup + BCrypt check
  → success handler + SecurityContext save
  → 302 redirect + session cookie

GET /me
  Cookie: SESSION=<giá trị nhận sau login>
  → SecurityContext được load từ WebSession
  → 200, username=alice, ROLE_READER
```

**Không kết luận “login đã lưu state” chỉ từ POST 302.** Một custom authentication handler có thể tạo Authentication đúng trong request login nhưng không persist vào `ServerSecurityContextRepository`, khiến GET kế tiếp anonymous.

Với WebFlux session cookie thường mang tên `SESSION`, khác `JSESSIONID` thường gặp ở Servlet. Tên này có thể được thay bằng cấu hình session ID resolver/proxy; kiểm thực tế trước khi viết automation hoặc hardcode cookie cho môi trường production.

### 12.1. Logout và session lifecycle

Sau logout, session đã bị invalidate không được tiếp tục dùng để gọi `/me`. Trong system nhiều nodes, cần shared reactive WebSession store (ví dụ Spring Session reactive Redis) nếu yêu cầu session có thể phục hồi ở pod bất kỳ. Sticky routing không tự bảo đảm correctness khi node bị drain/restart.

Session cookie cần TLS, `Secure`, `HttpOnly`, `SameSite` và path/domain phù hợp; thay đổi session ID/rotation và idle timeout theo policy. Cookie ID là bí mật mang quyền truy cập, không đưa vào URL/log.

## 13. Form login và CSRF trong WebFlux

Một form login dùng cookie có nguy cơ Cross-Site Request Forgery. Spring Security WebFlux mặc định **bật CSRF**, thường lưu token dự kiến trong `WebSessionServerCsrfTokenRepository`.

Các điểm phải tuân thủ:

- Browser GET login page, nhận CSRF token ở form.
- Browser POST login hoặc logout phải gửi token được server chấp nhận.
- Không tắt `csrf()` toàn hệ thống chỉ vì một test POST trả 403.
- Request AJAX/SPA dùng cookie session cần gửi CSRF token bằng header hoặc mô hình repo được cấu hình.
- Với `CookieServerCsrfTokenRepository`, việc để cookie đọc được qua JavaScript phải là quyết định có chủ đích, kèm bảo vệ XSS.
- Một API chỉ dùng Bearer token trong header, không dùng cookie auto-submitted, có thể có CSRF policy riêng; đừng lấy điều đó để tắt CSRF cho form login.
- CSRF 403 xảy ra **trước** password check; không được kết luận password sai từ HTTP 403.

Thử sai:

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded

username=alice&password=correct
```

Nếu không có CSRF token hợp lệ, kỳ vọng lỗi CSRF, dù password đúng. Không gửi password trong các test/report/log thực; ví dụ giao thức chỉ là minh họa.

## 14. WebTestClient: kiểm authorization bằng mock, không thay login thật

Spring Security Test hỗ trợ WebFlux qua:

- `SecurityMockServerConfigurers.springSecurity()`: gắn hỗ trợ security vào `WebTestClient` bind-to-context.
- `SecurityMockServerConfigurers.csrf()`: chèn CSRF test support cho unsafe requests.
- `SecurityMockServerConfigurers.mockUser()`: cấp principal giả cho **một request** để kiểm authorization.
- `@WithMockUser`: thuận tiện cho policy tests nhưng không đi qua database/BCrypt.
- `StepVerifier`: kiểm các publishers như `Mono<AccountRow>`, `Mono<UserDetails>`, errors/completion.
- HTTP integration test với cookie/session: chứng minh request sau login thấy đúng principal.

**Không đánh đồng:** một test dùng `mockUser("alice")` và `GET /me` trả 200 **không chứng minh** `ReactiveUserDetailsService` lấy đúng user từ DB hay password được kiểm. Đó là một test authorization có context giả.

## 15. Test tích hợp: login thật rồi GET mới với cùng session

File sau sử dụng Spring Test context và bind `WebTestClient` vào WebFlux application context với Spring Security. Nó chạy qua security web filters, form login, reactive manager và nguồn H2/R2DBC của demo.

**`src/test/java/com/example/reactiveauth/ReactiveAuthFlowTest.java`**

```java
package com.example.reactiveauth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(properties = {
        "demo.seed-enabled=true",
        "demo.seed-password=local-test-password-2026"
})
class ReactiveAuthFlowTest {

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

    private ResponseCookie loginAlice() {
        EntityExchangeResult<byte[]> result = client
                .mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "local-test-password-2026"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

        ResponseCookie session = result.getResponseCookies()
                .getFirst("SESSION");
        assertNotNull(session, "Expected WebFlux session cookie");
        return session;
    }

    @Test
    void loginThenNewRequestMustRestoreDatabaseUser() {
        ResponseCookie session = loginAlice();

        client.get()
                .uri("/me")
                .cookie(session.getName(), session.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.username").isEqualTo("alice")
                .jsonPath("$.authenticated").isEqualTo(true)
                .jsonPath("$.authorities[0]").isEqualTo("ROLE_READER");
    }

    @Test
    void anonymousRequestCannotBorrowPreviousLogin() {
        loginAlice();

        client.get()
                .uri("/me")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void authenticatedReaderCannotAccessAdminArea() {
        ResponseCookie session = loginAlice();

        client.get()
                .uri("/admin/panel")
                .cookie(session.getName(), session.getValue())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void wrongPasswordDoesNotProvideAccess() {
        client.mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "incorrect"))
                .exchange()
                .expectStatus().is3xxRedirection();

        client.get()
                .uri("/me")
                .accept(MediaType.TEXT_HTML)
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void loginWithoutCsrfIsDenied() {
        client.post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "local-test-password-2026"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

**Đọc test đúng mục tiêu:**

- `.mutateWith(csrf())` là helper test, không phải ứng dụng production tự thêm CSRF cho client.
- `POST /login` thực hiện login bằng Spring Security filters; password hash được kiểm bởi manager.
- `getResponseCookies().getFirst("SESSION")` lấy session cookie sau đăng nhập theo default WebFlux lab. Trong hệ thống có cấu hình cookie name khác, sửa helper theo contract thật.
- `GET /me` mới **không gửi username/password**, chỉ gửi cookie. Nó chứng minh context được load và trả đúng danh tính/quyền.
- Request không gửi cookie không được mượn session Alice. Hai request độc lập là trọng tâm chứ không chỉ assert 302.
- User READER vào admin phải 403; sai password không tạo authenticated session.
- Không có CSRF token → bị từ chối dù password đúng. Không disable bảo vệ chỉ để test qua.

**Giới hạn của Mock WebTestClient:** bind-to-context giúp kiểm WebFlux filters/manager/repository nhưng chưa chứng minh cookie flags, TLS termination hoặc shared session giữa hai pods. Cần HTTP end-to-end với RANDOM_PORT/cookie jar để kiểm triển khai thực tế.

### 15.1. Nếu WebTestClient của dự án không cấp cookie như mong đợi

Kiểm trước:

1. Ứng dụng thực sự chạy WebFlux hay vô tình bị chọn Servlet?
2. Client đã `apply(springSecurity())` khi bind-to-context chưa?
3. `POST /login` đang được `AuthenticationWebFilter` xử lý hay custom route?
4. Login có lưu `SecurityContext` vào `WebSession` chưa?
5. Cookie name có phải `SESSION` hay được custom?
6. Test double có dùng `mockUser()` và vô tình bypass login thật?
7. Có redirect/saved-request hoặc session fixation policy đổi cookie sau login không?

Không sửa bằng cách tự thêm `mockUser` cho GET /me; làm vậy sẽ che chính lỗi persistence mà test muốn phát hiện.

## 16. Kiểm thử ReactiveUserDetailsService độc lập

Ngoài HTTP integration test, nên có unit/integration test cho lookup semantics:

- Alice có trong DB → `Mono<UserDetails>` phát một user đúng username, enabled, password **là hash** và authorities.
- Unknown username → `Mono.empty()` (không có user), không trả placeholder account.
- Account `enabled=false` → user details disabled, manager không cấp login.
- DB timeout/connection error → reactive error signal; không đổi thành user-not-found.
- Role không được whitelist → fail closed; không tự cấp authorities mặc định mạnh.
- Username có ký tự gây SQL injection → repository parameter binding, không tự nối SQL string.
- Đồng thời nhiều lookups → không có blocking event-loop, pool có giới hạn.

Ví dụ **snippet trong test class** có `@Autowired AccountRepository repository`:

```java
StepVerifier.create(repository.findByUsername("alice"))
        .assertNext(row -> {
            assertEquals("alice", row.username());
            assertTrue(row.passwordHash().startsWith("$2"));
            assertTrue(row.enabled());
        })
        .verifyComplete();

StepVerifier.create(repository.findByUsername("missing-user"))
        .verifyComplete();
```

Cần imports `reactor.test.StepVerifier` và các assertions của JUnit. Đoạn trên **không phải class độc lập**; nó chỉ minh họa cách kiểm reactive signal. Với test DB chung, bảo đảm seed đã chạy và không để tests sửa dữ liệu làm ảnh hưởng lẫn nhau.

### 16.1. Tại sao StepVerifier không thay security integration test?

`StepVerifier` xác minh repository/Mono. Nó không chạy AuthenticationWebFilter, PasswordEncoder, SecurityContext persistence hoặc authorization rule. Vì vậy cần kết hợp cả **test nguồn dữ liệu** và **test chuỗi HTTP**.

## 17. Lỗi thường gặp: một Mono không làm code bên trong trở thành reactive

### 17.1. Ví dụ sai: blocking JDBC bị bọc trong Mono

```java
// PHẢN VÍ DỤ:
public Mono<UserDetails> findByUsername(String username) {
    UserEntity entity = jpaUserRepository.findByUsername(username);
    return Mono.just(toUserDetails(entity));
}
```

Ở đây truy vấn JDBC/JPA được thực hiện **trước khi Mono được tạo**. Nếu chạy trong Netty event loop, nó vẫn blocking. Dự án chuyển đổi tạm thời có thể dùng `Mono.fromCallable(() -> blockingLookup(username)).subscribeOn(Schedulers.boundedElastic())`, nhưng đây là **adapter cho blocking source**, không phải R2DBC thật; cần giới hạn concurrency, timeouts và lên kế hoạch loại bỏ blocking.

### 17.2. Ví dụ sai: block() trên kết quả repository

```java
// PHẢN VÍ DỤ:
AccountRow account = accounts.findByUsername(username).block();
return Mono.just(toDetails(account));
```

Có thể treo request, tốn thread hoặc Reactor ném lỗi `block()/blockFirst()/blockLast() are blocking` khi ở non-blocking thread.

### 17.3. Ví dụ sai: tự subscribe() trong controller

```java
// PHẢN VÍ DỤ:
accounts.findByUsername(username)
        .subscribe(account -> auditService.record(account));
return Mono.just("OK");
```

Request đã trả OK trước khi subscription thật hoàn tất; lỗi bị phân tách và context/cancellation không theo request. Thay bằng pipeline trả publisher được ghép đúng, ví dụ `flatMap(account -> auditService.recordSafeEvent(account).thenReturn(...))` khi ghi audit là điều kiện bắt buộc; với telemetry best-effort có queue được quản lý, không tự subscribe bừa bãi.

### 17.4. Ví dụ sai: username có role từ request

```java
// PHẢN VÍ DỤ:
return User.withUsername(username)
        .password(password)
        .roles(request.getQueryParams().getFirst("role"))
        .build();
```

Quyền phải đến từ nguồn tin cậy, không phải client. Cùng lúc, không đưa raw password vào UserDetails ở nguồn lưu trữ.

## 18. WebFlux session khác JWT stateless như thế nào?

Trong mẫu **form login browser**:

```text
POST /login → Authentication
          → WebSessionServerSecurityContextRepository
          → Cookie SESSION
GET /me + SESSION → load Authentication
```

Trong mẫu **OAuth2 Resource Server JWT**:

```text
GET /api/me + Authorization: Bearer <access_token>
          → AuthenticationWebFilter / Bearer support
          → ReactiveJwtDecoder xác minh token
          → Authentication cho request này
GET /api/me không token → 401
```

Không được nghĩ “đã reactive thì không có session”. WebFlux hỗ trợ web session. Không được nghĩ “đã login web thì API stateless tự có token”. Hai flow có credential/state khác nhau.

Nếu cần chạy cả form web và API bearer, cân nhắc **nhiều SecurityWebFilterChain** với `securityMatcher(ServerWebExchangeMatcher)` và `@Order` để tách:

- `/api/**`: bearer token, 401 + `WWW-Authenticate`, không redirect HTML login.
- Trang web: form/OIDC login, session cookie và CSRF.
- Catch-all: deny/require authentication theo policy.

Không áp dụng `SessionCreationPolicy.STATELESS` của Servlet lên WebFlux; quản session/context bằng API reactive phù hợp.

## 19. Role, ownership và dữ liệu nghiệp vụ

Ví dụ `.pathMatchers("/admin/**").hasRole("ADMIN")` chỉ kiểm **authority**, không có nghĩa user đã đủ quyền trên mọi bản ghi. Với API như `GET /orders/{id}`, có thể cần:

```text
authenticated
AND requiredAuthority
AND order.tenantId == principal.tenantId
AND order.ownerId == principal.id
```

Kiểm tenant/ownership bằng query reactive và rule được server thực hiện. Không lấy ownerId từ URL rồi cho phép khi role nào đó đúng nếu sản phẩm yêu cầu kiểm sở hữu đối tượng. Với multi-tenant, một username có thể trùng giữa tenants; repository interface `findByUsername` của demo không đủ cho hệ thống thật. Hãy định nghĩa khóa danh tính nhất quán như (tenantId, normalizedUsername) đã xác minh và ánh xạ principal bằng stable internal ID.

Reactive method security có `@EnableReactiveMethodSecurity` khi cần policy ở service; SpEL expression/manager phải không blocking. WebFlux path rules không thay cho object-level authorization.

## 20. Nguồn người dùng production: PostgreSQL R2DBC và migration

Để chuyển từ H2 lab sang PostgreSQL:

1. Dùng driver R2DBC PostgreSQL do BOM quản lý và connection URL `r2dbc:postgresql://...`.
2. Cấu hình TLS, database account least privilege, pool/timeouts, credential từ secret manager.
3. Dùng Flyway/Liquibase/migration được chạy bởi quy trình riêng nếu cần JDBC migration tool; không mặc định ứng dụng đã có JDBC driver chỉ vì dùng R2DBC.
4. Tạo unique index theo canonical account/tenant key và ràng buộc các columns của account.
5. Bảo vệ hash với adaptive algorithm/parameters, nâng cấp hash và account lifecycle theo policy.
6. Dùng `ReactiveUserDetailsService` trả Mono, không chuyển sang JPA trong cùng request.
7. Bảo đảm DB outage gây failure rõ ràng và fail closed, không biến mọi vấn đề thành empty account.
8. Load test truy vấn under concurrency; điều chỉnh R2DBC pool, index và scheduler cho password hashing.
9. Cân nhắc session store chung nếu nhiều pods; một H2 in-memory DB ở mỗi pod hiển nhiên không phải nguồn account chung.
10. Thiết kế MFA/step-up, brute-force throttling, lockout, audit và recovery trước khi production.

Ví dụ config PostgreSQL (thay thế H2, **không copy cùng lúc**):

```yaml
spring:
  r2dbc:
    url: "r2dbc:postgresql://db.internal.example:5432/authdb"
    username: ${R2DBC_USERNAME}
    password: ${R2DBC_PASSWORD}
```

Đối với auth DB, dùng TLS và truststore phù hợp driver. Đừng in password hay URL có embedded credentials trong logs. Quản lý migration để schema deploy tương thích với ứng dụng; rollback không nên mất user sessions hoặc quyền do thay đổi mapping role không được kiểm soát.

## 21. Hiệu năng: password hashing, event loop, pool và backpressure

Reactive giúp giữ threads hiệu quả khi nhiều request chờ I/O, nhưng không làm biến mất chi phí bảo mật:

| Nút thắt | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| BCrypt cost cao | Login p99 tăng/CPU cao | Tham số encoder phù hợp, giới hạn concurrent hash và rate limit |
| R2DBC pool cạn | Connection acquire timeout | Điều chỉnh pool, limit ingress, tối ưu query/index |
| Blocking call trong map/flatMap | Netty event loop stalled, BlockHound báo lỗi | Loại JDBC/.block; adapter boundedElastic nếu bắt buộc tạm thời |
| Quá nhiều password attempts | CPU bị chiếm dù user sai | Per-account/per-IP/tenant rate limits trước hash |
| DB credential rotation sai | Hàng loạt login fail | Health/alerts, secret rotation có kiểm thử |
| Bị slow query/findByUsername | Nhiều request giữ connection lâu | Index, max query time, response/backoff |
| Session store bị lỗi | User login xong request sau anonymous | Quan sát WebSession persistence, fail closed |
| Thiếu resource bounds | Queues/tasks vô hạn | Bounded schedulers, connection pools và budgets |
| GC/memory pressure | p95/p99 jitter | Giới hạn payload, concurrency, rate/lifecycle |
| Thử password trên event loop | Tụt throughput request khác | Dùng manager chuẩn và đánh giá scheduler |

**Không gọi `passwordEncoder.encode(rawPassword)` ở WebFlux event loop trong endpoint đăng ký hoặc reset mật khẩu nếu dùng algorithm CPU intensive.** Với code custom hãy schedule công việc CPU hợp lý, giới hạn concurrency và kiểm tra timeouts; mã mẫu chỉ hash trong ApplicationRunner khi khởi động lab.

Dùng metrics có kiểm soát: login success/failure, duration, password verify latency, reactive DB pool acquire, rate limit/429, WebSession load/save failures, event loop blocked count và app errors. Không dùng username/password/token làm tags.

## 22. Luồng xử lý lỗi an toàn

Một hệ thống nên phân biệt:

| Trường hợp | Bề mặt client | Phân loại nội bộ |
| --- | --- | --- |
| Username/password sai | Generic login failure, có thể redirect `/login?error` | CREDENTIAL_REJECTED |
| User không tồn tại | Cùng thông báo công khai | UNKNOWN_SUBJECT hoặc generic auth failure |
| Account disabled/locked | Thông báo an toàn theo policy, không lộ enumeration | ACCOUNT_DISABLED / LOCKED |
| DB/R2DBC timeout | Tạm thời không thể xác thực; không permit bypass | IDENTITY_STORE_UNAVAILABLE |
| CSRF sai/thiếu | 403, không kiểm password | CSRF_REJECTED |
| Đã login, thiếu role | 403 | AUTHORIZATION_DENIED |
| Không có session, vào web protected | Redirect login | ANONYMOUS_ACCESS |
| Session bị hết hạn | Phải login lại | SESSION_EXPIRED |
| API JWT sai | 401 Bearer nếu có API Resource Server | TOKEN_REJECTED |

**Điểm đáng chú ý:** không tự tạo `UserDetails` khi database error để “cho user login offline”; điều đó có thể tạo cửa sau. Không ghi `Authentication.toString()`, raw password, full principal, headers/cookies vào logs. Có thể dùng correlation ID và mã cơ chế/nhóm lỗi đã allowlist.

Khi login failure, phản hồi chung giúp chống user enumeration. Nội bộ cần có observability chính xác để không nhầm DB outage với sai mật khẩu hàng loạt.

## 23. Bảo mật đầy đủ trước khi đưa WebFlux login vào production

- **HTTPS/TLS** từ client tới ingress/app; bảo vệ cookie phiên và dữ liệu xác thực.
- **CSRF:** bật cho browser session và unsafe methods; test cả login/logout và API ghi dữ liệu.
- **XSS:** nếu attacker chạy JavaScript trong cùng origin, cookie HttpOnly giúp hạn chế lấy token trực tiếp nhưng không xóa hết tác hại của XSS. Có CSP, encoding và sanitization.
- **Session fixation:** dùng cơ chế session security phù hợp; test ID/cookie trước–sau login và request sau logout.
- **Password:** BCrypt/Argon2 adaptive hash, chính sách upgrade, không dùng plaintext, không để credential trong logs.
- **Brute force/credential stuffing:** per-account/per-source/risk throttling trước password verification, không khóa account vĩnh viễn do vài request từ attacker.
- **MFA:** cho tài nguyên cần assurance cao, có factor verification/step-up riêng; chỉ có `formLogin()` chưa phải MFA.
- **Account status:** disabled, locked, expired; policy cần phản ánh server-side authoritative state.
- **Role mapping:** whitelist, object-level authorization, tenant binding. DB role sai không trở thành ADMIN.
- **Reactive safety:** không JDBC/JPA/.block trong event-loop. Giới hạn concurrency và thread pools cho CPU-intensive hashing.
- **Session store multi-node:** nếu cần HA, dùng Spring Session reactive backend được hỗ trợ, test chuyển node và logout.
- **Secret management:** demo seed chỉ dùng lab; secrets/DB credentials trong secret manager; không expose repository DB hoặc password hash qua endpoint.
- **Error handling:** không trả stack trace, SQL exception, user existence hay nguyên nhân LDAP/DB ra public.
- **Auditing:** record loại sự kiện/actor đã pseudonymize, không block login path bằng SIEM/HTTP call chậm; audit bắt buộc có durable handoff riêng.
- **Testing:** WebTestClient integration + signed-token tests nếu có JWT + E2E browser/cookie/proxy + load/chaos tests.
- **Dependency upgrades:** giữ tương thích Boot/WebFlux/Security/Reactor/R2DBC/H2 theo BOM và theo dõi CVE/security updates.

## 24. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Copy `HttpSecurity`/`SecurityFilterChain` của MVC | Không bảo vệ đúng WebFlux filter chain | Dùng `ServerHttpSecurity` / `SecurityWebFilterChain` |
| `ReactiveUserDetailsService` gọi JPA/JDBC trực tiếp | Block event loop | Dùng R2DBC hoặc adapter trên scheduler có kiểm soát |
| Trả `Mono.just(blockingResult)` | Vẫn blocking trước khi tạo publisher | Compose non-blocking source/flatMap |
| Gọi `block()` trong HTTP handler | Deadlock/thread starvation hoặc Reactor exception | Trả Mono/Flux, để WebFlux subscribe |
| Tự gọi `subscribe()` rồi trả OK | Error/context không theo request | Trả composed reactive pipeline |
| Không có PasswordEncoder phù hợp | Password hash không được verify đúng | Cấu hình BCrypt/Delegating đúng và test |
| Dùng raw password trong DB | Lộ credential khi bị breach | Adaptive hash + salt/migration |
| Cấp role từ request body | Privilege escalation | Map server-side từ DB/IdP đã verify |
| `onErrorResume(Mono::empty)` cho lỗi DB | Lỗi hạ tầng bị nhầm thành wrong password | Bảo toàn error, phân loại nội bộ |
| Tắt CSRF vì form POST trả 403 | CSRF vulnerability | Gửi token đúng từ browser/test |
| Chỉ test `@WithMockUser` | Không test R2DBC/password/form login | POST /login thật rồi GET mới với cookie |
| Chỉ assert POST 302 | Không biết context đã được lưu qua request | GET /me với cùng SESSION cookie |
| Không phân biệt browser và API Bearer | API nhận HTML redirect thay vì 401 | Tách policy/chain theo endpoint |
| Giữ SecurityContext trong static field | Rò danh tính giữa users/threads | Reactor Context + security repositories |
| Tự tạo principal mà không kiểm account status | Disabled user vẫn login | Dùng UserDetails checks/correct manager |
| Dùng H2 local cho nhiều pods | Mỗi pod có user DB khác nhau | Shared production DB |
| Rate limit chỉ sau BCrypt | CPU DoS đã xảy ra | Pre-auth limit phân tán |
| H2 schema.sql mỗi startup trên DB production | Data/schema corruption risk | Migration/CI deployment control |
| DTO API trả nguyên UserDetails | Lộ hash/roles/details | Response contract allowlist |
| Không test store outage | Có thể permitAll fallback hoặc lỗi bị mask | Fail closed, 503/UX đúng, alerts |
| Không test cookie sau logout | Session cũ còn quyền | E2E revoke/invalidation |
| Dùng nhiều chain mà matcher/order sai | Endpoint bỏ xác thực hoặc wrong handler | Ordered matcher tests và catch-all |
| Giữ seed account mẫu trong public deployment | Credential dễ đoán, tài khoản không kiểm soát | Tắt seed ngoài lab, provisioning chính thức |

## 25. Checklist nghiệm thu bài thực hành

- [ ] App dùng `spring-boot-starter-webflux`, không vô tình chạy MVC Servlet.
- [ ] Có `SecurityWebFilterChain` và `.authorizeExchange(...)` áp quyền đúng.
- [ ] `ReactiveUserDetailsService.findByUsername` trả `Mono<UserDetails>` và không blocking.
- [ ] AccountRepository dùng R2DBC, ánh xạ đúng username/password hash/role/enabled.
- [ ] Password lưu BCrypt hash, manager dùng PasswordEncoder tương thích.
- [ ] Unknown username không tạo account giả, DB error không bị nuốt thành Mono.empty.
- [ ] Form login được Spring Security xử lý, không so password trong controller.
- [ ] POST login thành công tạo WebSession có authenticated SecurityContext theo thiết kế.
- [ ] GET /me **request mới** với session cookie trả đúng Alice/ROLE_READER.
- [ ] GET /me **không cookie** không được mượn danh tính từ request trước.
- [ ] Sai password không đăng nhập được; disabled account bị từ chối.
- [ ] User thiếu ROLE_ADMIN vào /admin/panel bị 403.
- [ ] Login/logout POST thiếu CSRF bị từ chối, không tắt CSRF vì test.
- [ ] Không gọi block()/subscribe() bừa bãi trong reactive request path.
- [ ] Test bằng WebTestClient và StepVerifier, có negative cases.
- [ ] Cookie/TLS, rate limit, session store, secret management và load test được đánh giá cho production.
- [ ] Có theo dõi R2DBC errors, hash latency và failure categories không lộ secrets.
- [ ] Với nhiều nodes, session store và account data là nguồn chung, không dựa vào H2 local.

## 26. Bài tập mở rộng

1. Thay hardcode role một-cột bằng bảng `account_role` reactive. Viết query theo user ID, dùng `flatMap(...collectList()...)` để tạo authorities, tránh N+1 với users có nhiều roles.
2. Thêm user Bob có `ROLE_ADMIN` qua seed/migration an toàn, kiểm WebTestClient /admin/panel trả 200 với Bob nhưng 403 với Alice.
3. Tạo trường `locked`/`credentials_expired_at` trong DB và map sang UserDetails trạng thái phù hợp. Test login bị từ chối khi locked/expired.
4. Tạo custom ReactiveUserDetailsService trả `Mono.error(...)` khi DB unavailable; test failure không bị biến thành account-not-found.
5. Chuyển sang PostgreSQL R2DBC, kiểm index/canonicalization và multi-tenant subject uniqueness.
6. Thêm `ReactiveUserDetailsPasswordService` cho upgrade password hash, kiểm không nâng hash sai user.
7. Thêm rate limiter WebFilter dựa trên account và trusted IP; kiểm brute-force requests không gọi BCrypt sau khi hết quota.
8. Cài `@EnableReactiveMethodSecurity` cho một service trả Mono, kiểm cả role và object ownership/tenant.
9. Chạy hai instance dùng shared reactive session store, login ở A rồi request tới B. Xác nhận principal không bị mất khi đổi node.
10. Tạo một API JWT chain riêng, kiểm 401 Bearer khi không token và 403 khi token hợp lệ thiếu scope; không chuyển API sang HTML login.
11. Dùng BlockHound trong môi trường test (với cấu hình JVM phù hợp) hoặc profiling event-loop để phát hiện một đoạn JDBC/blocking call lẫn vào request.
12. Kiểm session timeout/logout/re-authentication và saved request redirect khi form login hoàn tất.

## 27. Tổng kết và nguồn tham khảo

- Spring WebFlux dùng **SecurityWebFilterChain**, **ServerHttpSecurity**, **ReactiveAuthenticationManager**, **ReactiveUserDetailsService** và **Reactor Context**; không đổi tên API Servlet theo cảm tính.
- Nguồn user reactive qua R2DBC trả `Mono<AccountRow>`, được map sang `Mono<UserDetails>`; sai credential và lỗi database là **hai trường hợp khác nhau**.
- Form login filter gọi manager kiểm BCrypt và trạng thái account, rồi lưu authenticated SecurityContext vào WebSession; GET sau login phải mang cookie phiên để khôi phục identity.
- Authorization cần phân biệt `authenticated`, `hasRole` và quyền nghiệp vụ trên từng đối tượng. Role do server cấp, không từ user input.
- **Reactive không làm mã hash trở thành non-blocking**; cần scheduler và concurrency policy phù hợp; không gọi block/subscribe trong request.
- WebTestClient thật sự gửi form login khác với `mockUser()`. Test hai request chứng minh persistence và ngăn rò state giữa users.
- H2/seed chỉ dành cho học tập; production cần shared DB, migration, rate limit, CSRF, TLS, session store và audit được vận hành đúng.

**Tài liệu chính thức:**

- [Spring Security 6.5 — WebFlux Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/index.html)
- [Spring Security 6.5 — WebFlux Form Login](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/passwords/form-login.html)
- [Spring Security 6.5 — WebFlux Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Reactive Authentication Testing](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html)
- [Spring Security 6.5 — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security 6.5 — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 Javadoc — UserDetailsRepositoryReactiveAuthenticationManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html)
- [Spring Boot 3.5 — R2DBC and Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Data R2DBC — Reactive Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
- [Spring Framework — R2DBC ConnectionFactory](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)