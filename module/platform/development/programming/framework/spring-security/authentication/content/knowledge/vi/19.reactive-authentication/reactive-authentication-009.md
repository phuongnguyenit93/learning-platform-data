# Tích hợp kho dữ liệu không chặn luồng và kiểm soát công việc tốn CPU trong xác thực reactive

## 1. Mục tiêu và bối cảnh

Trong Spring Security chạy trên Spring WebFlux, việc nhận một yêu cầu HTTP bằng mô hình reactive chưa đủ để hệ thống xác thực hoạt động hiệu quả. Trên đường xử lý đăng nhập thường có hai loại công việc rất khác nhau:

1. **I/O đến kho danh tính**: tìm tài khoản, trạng thái khóa/vô hiệu hóa, quyền hạn hoặc thông tin phiên. Đây là công việc chờ cơ sở dữ liệu, Redis hay dịch vụ từ xa. Cần dùng API và driver hỗ trợ I/O không chặn luồng.
2. **Tính toán tốn CPU**: đối chiếu mật khẩu bằng BCrypt, PBKDF2, Argon2; xử lý chữ ký mật mã hoặc các phép biến đổi nặng. Công việc này có thể không thực hiện I/O nhưng vẫn chiếm CPU đủ lâu để làm nghẽn event loop nếu chạy nhầm trên đó.

Bài học tập trung vào **xác thực reactive** của module Spring Security: cách nối `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` với kho dữ liệu reactive, đặt đúng ranh giới cho phép tính CPU, kiểm soát mức đồng thời, xử lý lỗi và kiểm chứng bằng tình huống thực tế. Ví dụ sử dụng Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring WebFlux và PostgreSQL qua Spring Data R2DBC; ý tưởng cũng áp dụng cho phiên bản tương thích mới hơn.

Kết quả cần đạt: đọc được luồng `request → tìm người dùng → kiểm tra mật khẩu → tạo Authentication`, xác định thao tác nào có thể chặn luồng, và thiết kế được hệ thống không đánh đổi độ an toàn xác thực để lấy thông lượng.

## 2. Vì sao “Mono” không đồng nghĩa với không chặn luồng?

Spring WebFlux thường phục vụ nhiều kết nối trên số lượng event-loop thread nhỏ. Nếu một event loop bị giữ trong 200 ms bởi JDBC hoặc thao tác hash nặng, những yêu cầu khác dùng cùng luồng sẽ chậm theo.

| Thao tác | Bản chất | Cách xử lý thích hợp |
| --- | --- | --- |
| Truy vấn người dùng bằng Spring Data R2DBC + driver R2DBC | I/O bất đồng bộ, không chặn trong lúc chờ dữ liệu | Giữ trong chuỗi `Mono`/`Flux`, không `block()` |
| Truy vấn Redis bằng reactive client | I/O bất đồng bộ | Dùng reactive API và giới hạn timeout/pool phù hợp |
| BCrypt `matches`/`encode` | CPU-bound, API đồng bộ | Chạy trên scheduler dành cho CPU, có giới hạn công suất |
| JDBC/JPA, `RestTemplate`, SDK HTTP đồng bộ | I/O chặn luồng | Ưu tiên thay bằng driver/client reactive; nếu chưa thể, cô lập tạm trên `boundedElastic` |
| `Mono.just(repository.findByUsername(name))` nếu repository là blocking | Gọi blocking **ngay khi tạo Mono** | Sai: bọc trong `Mono` không chuyển lời gọi thành nonblocking |
| `mono.block()` hoặc `Future.get()` trong WebFlux handler | Chờ đồng bộ | Không dùng trên luồng xử lý reactive |

`subscribeOn` chuyển nơi chạy phần việc đồng bộ được bao trong publisher; nó **không tự biến** JDBC thành driver bất đồng bộ. `publishOn` chuyển luồng cho các toán tử downstream; không nên dời cả pipeline sang thread pool chỉ vì một thao tác CPU. Chọn ranh giới nhỏ nhất chứa phép tính đồng bộ.

Sơ đồ logic:

```text
HTTP request
  → Spring Security WebFilter (WebFlux)
  → ReactiveAuthenticationManager
  → ReactiveUserDetailsService
  → R2DBC repository ── nonblocking I/O ── PostgreSQL
  → PasswordEncoder.matches(...) ── CPU scheduler
  → Authentication / phản hồi 401 nếu thông tin đăng nhập sai
```

Không đánh đồng lỗi kho dữ liệu với sai mật khẩu: cơ sở dữ liệu không sẵn sàng là lỗi hạ tầng, không phải bằng chứng người dùng nhập sai.

## 3. Tích hợp kho người dùng bằng Spring Data R2DBC

### 3.1. Điều kiện cần

Một ứng dụng Spring Boot đã cấu hình dependency management có thể dùng các phần phụ thuộc sau trong `build.gradle` (đây là **đoạn dependencies**, không phải toàn bộ build script):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Cơ sở dữ liệu PostgreSQL tối giản:

```sql
CREATE TABLE app_users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(128) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    role VARCHAR(64) NOT NULL
);
```

Cấu hình phát triển trong `src/main/resources/application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/security_lab
```

Đặt tài khoản và mật khẩu kết nối thông qua biến môi trường `SPRING_R2DBC_USERNAME` và `SPRING_R2DBC_PASSWORD`. Database và bảng phải được tạo trước; R2DBC không tự đảm bảo có schema. Dùng migration như Flyway/Liquibase bằng một quy trình khởi tạo phù hợp, không chạy migration JDBC chặn luồng ở đường xử lý request. Không đưa mật khẩu kết nối hoặc mật khẩu người dùng thực vào tài liệu cấu hình được commit.

### 3.2. Entity và reactive repository

Các tệp Java sau nằm trong `src/main/java/com/example/authdemo/` và dùng package `com.example.authdemo`.

**`AppUser.java`**:

```java
package com.example.authdemo;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("app_users")
public record AppUser(
        @Id Long id,
        String username,
        @Column("password_hash") String passwordHash,
        boolean enabled,
        String role) {
}
```

**`AppUserRepository.java`**:

```java
package com.example.authdemo;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface AppUserRepository
        extends ReactiveCrudRepository<AppUser, Long> {

    Mono<AppUser> findByUsername(String username);
}
```

`findByUsername` là phương thức truy vấn theo tên do Spring Data suy ra. `Mono<AppUser>` phát tối đa một tài khoản; không có bản ghi thì hoàn tất rỗng; lỗi driver hoặc kết nối phát tín hiệu `onError`. Ràng buộc `UNIQUE` của `username` giúp tránh nhiều tài khoản trùng tên. Không gọi `.block()` trong repository, service hay filter.

### 3.3. Chuyển bản ghi sang đối tượng Spring Security

**`DatabaseReactiveUserDetailsService.java`**:

```java
package com.example.authdemo;

import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DatabaseReactiveUserDetailsService
        implements ReactiveUserDetailsService {

    private final AppUserRepository repository;

    public DatabaseReactiveUserDetailsService(AppUserRepository repository) {
        this.repository = repository;
    }

    @Override
    public Mono<UserDetails> findByUsername(String username) {
        return repository.findByUsername(username)
                .map(account -> User.withUsername(account.username())
                        .password(account.passwordHash())
                        .authorities(account.role())
                        .disabled(!account.enabled())
                        .build());
    }
}
```

Giải thích:

- `ReactiveUserDetailsService` chỉ tải thông tin dùng để xác thực; nó **không tự kiểm tra** mật khẩu và không được tự tạo `Authentication` đã xác thực.
- `passwordHash` phải là giá trị đã mã hóa phù hợp với `PasswordEncoder` (ví dụ `{bcrypt}...` khi dùng `DelegatingPasswordEncoder`), không phải plaintext.
- Ví dụ lưu một authority `ROLE_USER`. Phương thức `authorities(...)` dùng nguyên chuỗi quyền; nếu dùng `roles("USER")` thì Spring Security mới thêm tiền tố `ROLE_`. Với hệ thống nhiều quyền, thiết kế thêm bảng quan hệ/truy vấn reactive riêng hoặc mapping phù hợp.
- Cờ `enabled` được đưa vào `UserDetails` để authentication manager thực hiện kiểm tra trạng thái tài khoản. Không tự trả `Mono.empty()` cho mọi lỗi hạ tầng.
- Khi hệ thống dùng Redis, một `ReactiveUserDetailsService` có thể kết hợp reactive Redis client với R2DBC, nhưng phải định nghĩa rõ TTL, invalidation và mức nhạy cảm của dữ liệu được cache. Tránh cache mật khẩu thô/token hoặc trạng thái khóa quá lâu.

## 4. Tách phần xác minh mật khẩu ra khỏi event loop

### 4.1. Chọn đúng thành phần Spring Security

`UserDetailsRepositoryReactiveAuthenticationManager` kết hợp `ReactiveUserDetailsService` với `PasswordEncoder` để xác minh username/password. Spring Security hỗ trợ cấu hình scheduler cho tác vụ mã hóa/xác minh mật khẩu, vì đây là CPU-intensive. Có thể dùng scheduler mặc định của framework; ví dụ dưới tạo một pool CPU riêng để đo và kiểm soát ảnh hưởng giữa các loại công việc.

**`SecurityConfig.java`**:

```java
package com.example.authdemo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean(destroyMethod = "dispose")
    Scheduler authCpuScheduler() {
        int workers = Math.max(1, Runtime.getRuntime().availableProcessors() / 2);
        return Schedulers.newParallel("auth-password", workers);
    }

    @Bean
    ReactiveAuthenticationManager reactiveAuthenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder,
            @Qualifier("authCpuScheduler") Scheduler cpuScheduler) {

        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        manager.setScheduler(cpuScheduler);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
                .authenticationManager(authenticationManager)
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Điểm cốt lõi:

1. Tra cứu qua R2DBC vẫn là I/O reactive; không bọc toàn bộ `findByUsername` vào `boundedElastic`.
2. Manager đã thực hiện đối chiếu mật khẩu đúng chỗ theo scheduler được cấu hình; **không bọc lại** cả manager bằng `subscribeOn` như một phép tối ưu hóa mù quáng.
3. `Schedulers.newParallel(name, workers)` cấp một số luồng cố định cho tác vụ CPU. Công thức số worker là ví dụ khởi đầu, **không phải** cấu hình tối ưu cho mọi máy; phải hiệu chỉnh dựa trên tài nguyên và đo đạc thực tế.
4. `@Bean(destroyMethod = "dispose")` giải phóng scheduler riêng khi ứng dụng đóng. Không gọi `dispose()` với scheduler dùng chung do Reactor quản lý.
5. `DelegatingPasswordEncoder` nhận biết tiền tố thuật toán như `{bcrypt}`, hỗ trợ chuyển đổi thuật toán về sau. Không sử dụng `NoOpPasswordEncoder` hay lưu plaintext.

Một controller nhỏ để kiểm tra luồng: **`MeController.java`**.

```java
package com.example.authdemo;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class MeController {

    @GetMapping("/me")
    public Mono<String> me(Mono<Principal> principal) {
        return principal.map(user -> "Authenticated: " + user.getName());
    }
}
```

**`AuthDemoApplication.java`**:

```java
package com.example.authdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthDemoApplication.class, args);
    }
}
```

Các đoạn Java trên là các tệp riêng, hoàn chỉnh trong cùng package; với dependency, PostgreSQL/schema và cấu hình nêu trên, chúng tạo luồng HTTP Basic → reactive authentication manager → R2DBC repository → xác minh mật khẩu. HTTP Basic chỉ thích hợp với kết nối được bảo vệ bằng HTTPS trong thực tế. Ví dụ không tự thêm endpoint đăng ký hoặc tài khoản mặc định.

### 4.2. Hash khi tạo hoặc đổi mật khẩu cũng là CPU-heavy

Nếu có quy trình cấp tài khoản, cần tính hash **trước** thao tác lưu reactive. Ví dụ service dùng chung scheduler chuyên trách; trong production có thể tách pool cấp tài khoản và pool xác minh để bảo vệ năng lực đăng nhập.

**`AccountProvisioningService.java`**:

```java
package com.example.authdemo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@Service
public class AccountProvisioningService {

    private final AppUserRepository repository;
    private final PasswordEncoder encoder;
    private final Scheduler cpuScheduler;

    public AccountProvisioningService(
            AppUserRepository repository,
            PasswordEncoder encoder,
            @Qualifier("authCpuScheduler") Scheduler cpuScheduler) {
        this.repository = repository;
        this.encoder = encoder;
        this.cpuScheduler = cpuScheduler;
    }

    public Mono<AppUser> createUser(String username, String rawPassword) {
        return Mono.fromCallable(() -> encoder.encode(rawPassword))
                .subscribeOn(cpuScheduler)
                .flatMap(hash -> repository.save(
                        new AppUser(null, username, hash, true, "ROLE_USER")));
    }
}
```

Ở đây `Mono.fromCallable` trì hoãn thực thi hàm hash tới thời điểm subscribe, còn `subscribeOn(cpuScheduler)` chuyển đúng phép tính đồng bộ sang scheduler CPU. `flatMap` tiếp tục bằng lệnh `save` reactive, không cần gọi `block()`. Đây là ví dụ về **xử lý CPU và ghi dữ liệu**, không phải API đăng ký hoàn chỉnh: cần kiểm tra đầu vào, chính sách mật khẩu, quyền cấp tài khoản, chống đăng ký ồ ạt, bắt lỗi trùng username và không log mật khẩu/hash.

## 5. Kiểm soát mức đồng thời và tài nguyên

**Nonblocking không đồng nghĩa với vô hạn công suất.** Mỗi yêu cầu đăng nhập có thể chiếm CPU đáng kể để so khớp BCrypt/Argon2; R2DBC cũng bị giới hạn bởi pool kết nối và database.

| Nút thắt | Biểu hiện | Biện pháp |
| --- | --- | --- |
| Event loop bị blocking | Yêu cầu nhẹ cũng tăng latency, throughput giảm | Loại bỏ `block()`, JDBC, lời gọi mạng đồng bộ trong WebFlux; tách CPU khỏi event loop |
| CPU hash quá tải | p95/p99 của login tăng; CPU cao; scheduler có hàng đợi | Giới hạn đồng thời/rate limit, đo tải thực tế, có thể dùng scheduler riêng |
| R2DBC connection pool cạn | Tăng thời gian chờ kết nối hoặc timeout | Chọn pool phù hợp với sức chịu tải DB; đặt timeout và giám sát active/pending |
| DB chậm hoặc mất kết nối | Lỗi truy vấn; login không hoàn tất | Timeout, circuit breaker khi phù hợp, trả lỗi hạ tầng có kiểm soát |
| Hàng đợi tăng nhanh khi có tấn công login | Tốn CPU và bộ nhớ dù I/O nonblocking | Rate limit theo IP/tài khoản, chống brute force, admission control trước bước hash |

Phân biệt ba kiểu scheduler quan trọng:

- `Schedulers.parallel()` / `Schedulers.newParallel(...)`: phù hợp các công việc **CPU-bound không blocking**. Luồng cố định nhưng công việc vẫn có thể xếp hàng; giới hạn số worker **không tự giới hạn lượng request chờ**.
- `Schedulers.boundedElastic()`: dành cho **mã legacy thực sự blocking** cần cô lập tạm (JDBC, file I/O đồng bộ, SDK đồng bộ), có giới hạn thread/hàng đợi riêng. Không nên coi đây là cách chuẩn để tăng tốc tính toán CPU thuần túy.
- `Schedulers.immediate()`: chạy trên luồng hiện tại; không phù hợp với tác vụ mật mã nặng ở event loop.

Một ví dụ cô lập adapter blocking *chỉ để chuyển tiếp trong lúc migration*:

```java
Mono<LegacyAccount> findLegacyAccount(String username) {
    return Mono.fromCallable(() -> legacyJdbcDao.findByUsername(username))
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây chỉ là phương thức minh họa, không phải chương trình độc lập: `LegacyAccount` và `legacyJdbcDao` thuộc hệ thống legacy. Nó giúp tránh chặn event loop, **nhưng database call vẫn blocking**, tiêu tốn luồng và bị giới hạn bởi pool. Ưu tiên chuyển sang client/driver reactive khi có thể.

Với `Flux.flatMap(mapper, concurrency)`, tham số `concurrency` có ích cho một luồng xử lý nhiều phần tử; nó **không** tạo ra hạn mức login toàn hệ thống vì mỗi HTTP request là một pipeline riêng. Hạn mức toàn cục cần rate limiter/bulkhead/semaphore/queue có giới hạn ở tầng phù hợp, cùng chính sách trả lỗi khi quá tải. Đừng đợi đến khi phép hash đã chạy mới kiểm tra quota.

Timeout là một biện pháp bảo vệ thời gian chờ; hủy một reactive publisher **không đảm bảo** đã hủy ngay tác vụ CPU đang chạy hoặc truy vấn đã gửi xuống database. Cần kiểm tra semantics của driver và giới hạn tài nguyên ở nguồn.

## 6. Dòng dữ liệu, lỗi và bảo mật

Một yêu cầu xác thực thường đi qua các trạng thái sau:

1. WebFlux security filter đọc username/password từ HTTP Basic (hoặc một cơ chế đăng nhập tương ứng).
2. Reactive authentication manager gọi `ReactiveUserDetailsService.findByUsername`.
3. Repository phát bản ghi, kết thúc rỗng nếu không tìm thấy, hoặc phát lỗi từ DB.
4. Manager kiểm tra tài khoản và đối chiếu password hash bằng `PasswordEncoder` trên scheduler CPU.
5. Nếu hợp lệ, manager trả `Authentication` đã xác thực; Spring Security dùng để áp dụng authorization và cung cấp principal cho phần xử lý sau.

| Tình huống | Ý nghĩa/ứng xử |
| --- | --- |
| Không tìm thấy username | Xác thực thất bại; tránh tiết lộ người dùng có tồn tại hay không |
| Password không khớp | Xác thực thất bại, thông thường HTTP 401 với HTTP Basic |
| Tài khoản `enabled=false` | Không cho xác thực; không bỏ qua kiểm tra trạng thái |
| DB timeout / mất kết nối | Lỗi hạ tầng; không biến mọi lỗi thành `BadCredentialsException` |
| CPU bị quá tải | Áp dụng hạn mức và phản hồi phù hợp; không mở rộng thread pool không kiểm soát |
| Đăng nhập thành công | Chỉ cấp quyền từ dữ liệu đã kiểm tra; không tin role do client gửi |

Đặc biệt với WebFlux, Spring Security gắn thông tin security vào **Reactor Context**. Không dựa vào `ThreadLocal` truyền thống hoặc giả định một request luôn chạy trên một thread. Nếu code tự đọc authentication trong service, sử dụng `ReactiveSecurityContextHolder.getContext()` trong chuỗi reactive thích hợp. Không truyền password hoặc hash vào log, metrics, tracing, exception message hay phản hồi API.

Cần có lớp bảo vệ thêm như TLS, rate limiting, giám sát đăng nhập thất bại, chính sách khóa tạm thời hợp lý, secret management, điều chỉnh cost của password encoder theo khả năng CPU, và xử lý chu kỳ đổi password/hash. Giá trị bcrypt có prefix `{bcrypt}` là chuỗi lưu trữ đã hash, không phải plaintext và cũng không phải cơ chế mã hóa có thể giải ngược.

## 7. Chạy thử và kiểm chứng

### 7.1. Chuẩn bị dữ liệu

- Khởi động PostgreSQL, tạo database `security_lab` và bảng `app_users` như trên; cấu hình biến môi trường kết nối.
- Tạo tài khoản thử nghiệm bằng một luồng provisioning hợp lệ gọi `AccountProvisioningService.createUser("alice", "demo-secret")` hoặc công cụ quản trị dùng cùng `PasswordEncoder`. Trong DB, `password_hash` phải bắt đầu bằng tiền tố như `{bcrypt}`. Không chèn chuỗi `"demo-secret"` trực tiếp vào `password_hash`.
- Với ứng dụng Spring Boot có Gradle wrapper và plugin Boot, chạy `./gradlew bootRun` (PowerShell/Windows: `.\gradlew.bat bootRun`). Trên Linux/macOS, bảo đảm script wrapper có quyền chạy.
- Chỉ dùng credential minh họa ở môi trường phát triển.

Khi đã có user, gọi endpoint (với HTTPS khi sử dụng ngoài máy phát triển):

```bash
curl -i http://localhost:8080/me
curl -i -u 'alice:wrong-password' http://localhost:8080/me
curl -i -u 'alice:demo-secret' http://localhost:8080/me
```

Hai yêu cầu đầu cần bị từ chối (thường `401 Unauthorized`). Yêu cầu cuối thành công nếu account tồn tại, được bật và hash khớp, trả HTTP 200 với nội dung:

```text
Authenticated: alice
```

Đó là **kết quả kỳ vọng có điều kiện**, không phải stdout đã ghi nhận từ một hệ thống đang chạy trong bài viết này.

### 7.2. Unit test bộ xác thực không cần database

Tệp `src/test/java/com/example/authdemo/AuthenticationManagerTest.java` kiểm tra logic so khớp mật khẩu độc lập với R2DBC; integration test dùng database thật/Testcontainers sẽ kiểm tra tầng lưu trữ.

```java
package com.example.authdemo;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthenticationManagerTest {

    @Test
    void acceptsCorrectPasswordAndRejectsIncorrectPassword() {
        PasswordEncoder encoder =
                PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails user = User.withUsername("alice")
                .password(encoder.encode("demo-secret"))
                .roles("USER")
                .build();

        ReactiveUserDetailsService users = name ->
                "alice".equals(name) ? Mono.just(user) : Mono.empty();

        var manager =
                new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);

        StepVerifier.create(manager.authenticate(
                        new UsernamePasswordAuthenticationToken(
                                "alice", "demo-secret")))
                .assertNext(authentication ->
                        assertTrue(authentication.isAuthenticated()))
                .verifyComplete();

        StepVerifier.create(manager.authenticate(
                        new UsernamePasswordAuthenticationToken(
                                "alice", "wrong-password")))
                .expectError(BadCredentialsException.class)
                .verify();
    }
}
```

Kiểm thử này chứng minh manager chấp nhận hoặc từ chối mật khẩu theo hash. Nó không chứng minh khả năng không blocking của JDBC/R2DBC; cần kiểm thử tích hợp và quan sát runtime cho phần đó.

### 7.3. Checklist tải và vận hành

Kiểm chứng bằng tải có kiểm soát, thay đổi số lượng yêu cầu đăng nhập đồng thời và theo dõi:

- **Event loop**: thời gian phản hồi endpoint nhẹ có bị ảnh hưởng bởi đợt đăng nhập hay không; có phát hiện blocking operation trên event-loop thread hay không.
- **CPU**: mức sử dụng, hàng đợi/độ trễ xử lý hash; độ nhạy khi thay đổi cost và số worker.
- **R2DBC pool**: active/pending connection, thời gian chờ, timeout, lỗi kết nối và DB query latency.
- **Đăng nhập**: tỉ lệ thành công/thất bại, p50/p95/p99, rate limit, lỗi infrastructure so với bad credentials; không ghi thông tin bí mật vào telemetry.
- **Tình huống lỗi**: user không tồn tại, mật khẩu sai, account bị disable, DB down, DB chậm, lượng yêu cầu đột biến. Không để lỗi database chuyển thành xác thực thành công hoặc bị che giấu thành lỗi nhập mật khẩu.

Dùng các công cụ đo phù hợp như Micrometer/Actuator, tracing an toàn và thử nghiệm BlockHound khi môi trường kiểm thử hỗ trợ. BlockHound có thể tìm lời gọi blocking trên luồng nonblocking, nhưng **không** thay thế benchmark CPU hoặc kiểm thử áp lực.

## 8. Sai lầm thường gặp và cách sửa

| Sai lầm | Vấn đề | Hướng sửa |
| --- | --- | --- |
| `Mono.just(jdbcDao.loadUser(name))` | JDBC chạy trước khi Mono được tạo, chặn thread đang gọi | Dùng R2DBC; nếu còn legacy, `fromCallable(...).subscribeOn(boundedElastic)` để cô lập |
| `repository.findByUsername(name).block()` | Phá luồng reactive và có thể gây lỗi trên event loop | Trả `Mono`, kết hợp bằng `map`/`flatMap` |
| Gọi `passwordEncoder.matches` trực tiếp trong `map` trên event loop | Hash có thể chiếm CPU lâu | Dùng reactive authentication manager có scheduler phù hợp |
| Gửi toàn pipeline qua `boundedElastic` | Không giải quyết bản chất CPU; thêm thread/context switch | Tách thao tác CPU và dùng scheduler CPU; giữ database reactive |
| Tăng worker vô hạn khi chậm | Tranh chấp CPU và tăng hàng đợi | Đo công suất, giới hạn concurrency/rate, chính sách quá tải |
| Dùng `onErrorResume(e -> Mono.empty())` cho mọi lỗi repository | Che mất sự cố DB thành user “không tồn tại” | Phân loại lỗi; để lỗi hạ tầng được xử lý đúng và không fail-open |
| Lưu password không có tiền tố hoặc dùng `{noop}` | Không tương thích encoder hoặc làm yếu bảo mật | Hash mạnh bằng `DelegatingPasswordEncoder`, kiểm tra cost và kế hoạch nâng cấp |
| Lấy Authentication qua `ThreadLocal` sau khi đổi scheduler | Mất ngữ cảnh hoặc đọc sai thông tin | Dùng `ReactiveSecurityContextHolder`/Reactor Context |
| Chỉ giới hạn `flatMap(concurrency)` trong một stream | Không giới hạn tổng request HTTP độc lập | Thêm rate limiter/bulkhead ở mức ứng dụng |

## 9. Bài tập áp dụng

1. Thay repository ở ví dụ bằng reactive Redis hoặc một dịch vụ danh tính hỗ trợ asynchronous I/O. Chỉ ra nơi đặt timeout, nơi ánh xạ dữ liệu về `UserDetails` và cách phân biệt “not found” với lỗi upstream.
2. Đo độ trễ `/me` cùng một endpoint không cần đăng nhập dưới tải. Cố ý chuyển password matching lên event loop trong môi trường thử nghiệm để quan sát tác hại, sau đó trả lại scheduler đúng. Không triển khai biến thể blocking vào production.
3. Thiết kế hạn mức đăng nhập khi có nhiều yêu cầu sai mật khẩu. Giải thích tại sao giới hạn thread CPU mà thiếu giới hạn hàng đợi vẫn có thể làm cạn tài nguyên.
4. Bổ sung integration test với PostgreSQL/Testcontainers: người dùng tồn tại, bị vô hiệu hóa, không tồn tại và database lỗi; xác minh không có `block()` trong đường xử lý request.

## 10. Ghi nhớ

- **Kho dữ liệu**: chọn client/driver thật sự reactive (ví dụ R2DBC), kết hợp bằng `Mono`/`Flux`; không dùng `block()`.
- **Mật khẩu và phép toán nặng**: dù không I/O, vẫn phải tránh chiếm event loop; để manager sử dụng scheduler CPU phù hợp và đo công suất.
- **Giới hạn tài nguyên**: pool DB, số worker, hàng đợi, timeout, rate limit và admission control là các lớp bảo vệ khác nhau.
- **Đúng ngữ nghĩa bảo mật**: sai thông tin đăng nhập, account bị khóa và lỗi hạ tầng phải được phân biệt; không log credential hoặc tự cấp quyền khi upstream lỗi.

Tài liệu tham khảo để đối chiếu API và mô hình thực thi: Spring Security WebFlux Security (https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html), `UserDetailsRepositoryReactiveAuthenticationManager` Javadoc (https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html), Spring Data R2DBC (https://docs.spring.io/spring-data/relational/reference/r2dbc.html), Reactor Schedulers (https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).