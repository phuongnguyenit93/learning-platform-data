# Giới hạn của JDBC, JPA, LDAP đồng bộ và phương án tích hợp tại ranh giới chặn luồng

> **Ngữ cảnh:** Spring Boot 3.3.x, Spring Security 6.x, Spring WebFlux, Project Reactor và Java 17+. Bài tập trung vào **tìm người dùng, xác minh mật khẩu và truy cập danh bạ** khi hệ thống reactive vẫn phải tương tác với JDBC, Spring Data JPA hoặc LDAP/JNDI đồng bộ. Mục tiêu là xác định ranh giới chặn luồng rõ ràng, không giả vờ rằng một API đồng bộ trở thành non-blocking chỉ vì được bọc bằng `Mono`.

## 1. Vấn đề: một cuộc gọi blocking có thể làm nghẽn nhiều request

WebFlux được xây dựng quanh I/O bất đồng bộ, non-blocking. Một số lượng nhỏ event-loop thread có thể xử lý nhiều kết nối vì chúng **không phải chờ** một request SQL hoặc LDAP kết thúc rồi mới làm việc khác. Ngược lại:

- `JdbcTemplate`, JDBC `Connection` và `ResultSet`: đợi driver thực hiện SQL và trả dữ liệu theo cách đồng bộ.
- JPA `EntityManager`, Spring Data JPA `JpaRepository`, Hibernate ORM cổ điển: thực hiện truy vấn, flush, lazy loading và transaction theo mô hình imperative; phần I/O đến DB vẫn blocking.
- Spring LDAP/JNDI `LdapTemplate` và các client LDAP đồng bộ: có thể chờ kết nối, bind, search và phản hồi từ server danh bạ.
- `PasswordEncoder.matches(...)` với BCrypt/Argon2/PBKDF2: công việc CPU tốn chi phí đáng kể; không nhất thiết *đợi I/O* nhưng cũng không nên chiếm event loop quá lâu.

Ví dụ phản-pattern:

```java
@GetMapping("/api/users/{name}")
Mono<String> user(@PathVariable String name) {
    UserRecord record = jdbcUserDao.findBlocking(name); // BLOCKING ngay
    return Mono.just(record.displayName());
}
```

Đây chỉ là **đoạn minh họa** (không đủ imports/class). `findBlocking` chạy **trước khi Mono được trả về** trên thread đang gọi handler, thường thuộc luồng xử lý reactive. Nếu DB chậm, thread bị giữ lại; các request khác cũng có thể chậm theo.

Một kiểu sai thứ hai:

```java
Mono<UserRecord> user = Mono.just(jdbcUserDao.findBlocking(name));
```

`Mono.just(...)` không hoãn phép gọi trong đối số: Java tính `findBlocking(name)` **trước**, rồi mới đưa kết quả vào publisher. Tên `Mono` không làm thao tác bên trong trở thành non-blocking.

**Tư duy đúng:** muốn dùng một thư viện blocking, phải đưa **chính thao tác blocking** vào một vùng có thread phù hợp, có giới hạn concurrency/queue/timeout; giữ việc kiểm quyền và xử lý Reactor ở bên ngoài vùng đó.

## 2. Phân biệt ba loại tài nguyên trong reactive security

| Thành phần | API hay gặp | Có tự non-blocking không? | Điều cần quản lý |
|---|---|---|---|
| JDBC | `DataSource`, `JdbcTemplate`, JDBC driver | **Không** | Thread chờ, connection pool, query/statement timeout |
| Spring Data JPA | `JpaRepository`, `EntityManager`, Hibernate | **Không** | Thread, transaction gắn thread, EntityManager, lazy loading |
| LDAP đồng bộ | `LdapTemplate`, JNDI, LDAP bind/search API | **Không** | Connection/socket timeout, pool, TLS, filter injection |
| Spring Security reactive | `ReactiveUserDetailsService`, `ReactiveAuthenticationManager` | **Giao diện reactive** | Implementation có thể vẫn blocking nếu viết sai |
| R2DBC | `ConnectionFactory`/reactive DB drivers | **Thiết kế non-blocking** | Driver, reactive pool, giới hạn truy vấn và transaction reactive |
| Password hashing | `PasswordEncoder.matches` | Thường **CPU-bound** | CPU budget, password hash cost, scheduler thích hợp |

Không nên suy luận: “WebFlux + JPA = reactive database”. JPA/JDBC không thành non-blocking do Spring Boot chọn HTTP stack WebFlux.

### Kiểu phản hồi của service không quyết định bản chất của thao tác

Một method trả `Mono<User>` có thể chỉ là **vỏ bọc** quanh JDBC. Điều quyết định là bên trong có gọi đồng bộ trên event-loop không, có dispatch sang scheduler phù hợp không và có giới hạn lượng công việc chờ hay không.

Ngược lại, **dùng JDBC/JPA trong ứng dụng WebFlux không bị cấm tuyệt đối**. Đây có thể là chiến lược chuyển đổi hợp lý khi chưa thể thay database driver hoặc lớp repository; nó có chi phí, giới hạn throughput và yêu cầu vận hành rõ ràng.

## 3. Mẫu ranh giới chặn luồng trong Project Reactor

Pattern chuẩn khi *một thao tác đồng bộ có thể blocking*:

```java
Mono<UserRecord> result =
    Mono.fromCallable(() -> legacyUserDao.load(username))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **mảnh mã**; cần có DAO, model và imports tương ứng. Ba ý chính:

1. `Mono.fromCallable(...)` hoãn thực thi `Callable` đến lúc có subscription. Việc tạo publisher không gọi DAO.
2. `subscribeOn(Schedulers.boundedElastic())` chuyển việc subscribe nguồn này sang scheduler dành cho blocking I/O, tránh chạy `Callable` trên event-loop.
3. Nếu DAO ném exception, `Mono` phát `onError`; nếu `Callable` trả `null`, `Mono.fromCallable` hoàn thành rỗng. Với truy vấn user, thường nên phân biệt “không tìm thấy” bằng ngoại lệ/`Mono.empty()` có chủ đích.

Cùng mẫu với `Runnable` không trả giá trị:

```java
Mono<Void> operation =
    Mono.fromRunnable(() -> blockingAuditStore.write(entry))
        .subscribeOn(Schedulers.boundedElastic())
        .then();
```

`Mono.fromCallable` phù hợp khi cần trả `UserDetails`, DTO hoặc kết quả tìm kiếm. Không gọi `block()`, `subscribe()` thủ công để “ép kết quả” trong controller hay service WebFlux.

### Vì sao `subscribeOn` thay vì chỉ `publishOn`?

Đặt `publishOn` **sau** source đã gọi blocking quá sớm không sửa được lần chặn trước đó. `subscribeOn` gắn lên source hoãn thực thi để việc tạo subscription và gọi `Callable` chạy ở scheduler đã chọn. Ví dụ minh họa:

```java
// ĐÚNG: JDBC nằm trong Callable và chạy trên scheduler blocking
Mono.fromCallable(() -> jdbcUserDao.load(username))
    .subscribeOn(Schedulers.boundedElastic())
    .map(UserRecord::displayName);

// SAI: JDBC chạy ngay khi tạo Mono
Mono.just(jdbcUserDao.load(username))
    .publishOn(Schedulers.boundedElastic());
```

**`subscribeOn` không làm database I/O bất đồng bộ:** nó chỉ dùng thread khác để **đợi** tác vụ đồng bộ hoàn tất. Số lượng thread, connection và hàng đợi vẫn là giới hạn thật.

## 4. Cấu hình scheduler, connection pool và giới hạn tải

`Schedulers.boundedElastic()` là scheduler dùng chung của Reactor cho tác vụ có thể chặn. Nó có số thread và số task chờ **được giới hạn**; không phải kho thread vô hạn. Với luồng xác thực cần cô lập với những công việc blocking khác, có thể cấp một scheduler riêng:

```java
@Bean(destroyMethod = "dispose")
Scheduler jdbcAuthScheduler() {
    return Schedulers.newBoundedElastic(
        4,        // tối đa 4 worker thread cho scheduler này
        100,      // giới hạn task đợi theo cấu hình scheduler
        "jdbc-auth");
}
```

Đây là method cấu hình, **không chạy độc lập** nếu chưa đặt vào `@Configuration` và import `Bean`, `Scheduler`, `Schedulers`. `destroyMethod="dispose"` giúp giải phóng scheduler khi application context đóng. Con số 4/100 chỉ là **giá trị minh họa**; phải chọn theo độ trễ truy vấn, pool DB và giới hạn hệ thống, không sao chép như tham số production.

Không có công thức một-kích-thước-cho-tất-cả. Ví dụ nếu JDBC pool chỉ có 4 connection nhưng đồng thời có hàng trăm request login, tăng thread từ 4 lên 100 thường chỉ tạo thêm thread chờ pool; nó không làm DB xử lý nhanh gấp 25 lần.

### Những giới hạn nên phối hợp

- **Connection pool:** HikariCP maximum pool size, connection timeout, kiểm tra kết nối lỗi.
- **Thread pool/scheduler:** số worker, queue cap, chính sách khi overload. Một scheduler riêng cho auth tránh JDBC login chiếm hết shared scheduler phục vụ tác vụ khác.
- **Bulkhead/semaphore:** nếu cần hạn chế số request đồng thời vào LDAP/DB, kiểm soát ở phía adapter; queue có kích thước hữu hạn và phản hồi quá tải có chủ đích.
- **Statement/query timeout và LDAP connect/read timeout:** đặt ở driver/client, không chỉ đặt timeout reactive bên ngoài.
- **Giám sát:** latency p50/p95/p99 của lookup, pool active/pending, thread queue, timeout, số lần xác thực thất bại, sự cố LDAP.
- **Giới hạn đăng nhập:** rate limiting/chống brute force, backoff, MFA hay chính sách khóa tài khoản phù hợp rủi ro; không phụ thuộc riêng số thread.

Nếu một công việc blocking chiếm 1 thread trong suốt thời gian chờ, năng lực đồng thời gắn với số thread có thể chạy và số connection khả dụng. **Backpressure của Reactor không tự mở rộng JDBC pool, cũng không tự từ chối mọi burst request HTTP**.

### Timeout và cancellation không đồng nghĩa dừng ngay JDBC

`Mono.timeout(Duration.ofSeconds(3))` có thể làm caller ngừng đợi và phát tín hiệu timeout, nhưng thao tác JDBC/LDAP đồng bộ đang chờ socket hoặc driver **không được bảo đảm dừng ngay**. Một số driver có thể phản ứng với interrupt/cancel; một số không. Phải có timeout ở connection, statement và socket, tránh rò rỉ thread/connection sau khi client đã bỏ request. Không dùng `retry()` vô hạn đối với lỗi nguồn user hoặc LDAP: nó có thể khuếch đại tải vào backend đang gặp sự cố.

## 5. Ranh giới tích hợp vào Spring Security reactive

Spring Security WebFlux nhận các giao diện reactive:

```java
public interface ReactiveUserDetailsService {
    Mono<UserDetails> findByUsername(String username);
}
```

Đoạn trên lược bớt package/import cho dễ đọc. **Giao diện `ReactiveUserDetailsService` không hứa rằng mọi implementation đều non-blocking**. Nếu backend là JDBC/JPA/LDAP đồng bộ, việc chọn scheduler phù hợp là trách nhiệm implementation/adaptor.

Một cách tích hợp chuẩn:

```text
HTTP Basic / form login
           |
           v
SecurityWebFilterChain
           |
           v
ReactiveAuthenticationManager
           |
           v
ReactiveUserDetailsService.findByUsername()
           |
           +--> Mono.fromCallable(...)
                    .subscribeOn(boundedElastic / dedicated blocking Scheduler)
                           |
                           v
                   JDBC / JPA / LDAP đồng bộ
                           |
                           v
                   UserDetails (hash + authorities)
           |
           v
PasswordEncoder.matches(...) -> authentication result
           |
           v
Authorization -> controller/service
```

**Không bọc cả quá trình chỉ bằng cách đặt `@Async` vào DAO** rồi để Spring Security tự đoán kết quả. `@Async` thường trả `Future`/`CompletableFuture` và có hệ thống executor khác; nếu dùng phải chuyển thành Publisher đúng cách, đảm bảo giới hạn và truyền lỗi. Với Spring Security reactive, `ReactiveUserDetailsService` là điểm tích hợp trực tiếp, dễ test.

### Password hash có hai loại chi phí khác I/O

- **Đọc hash user** từ JDBC/JPA/LDAP đồng bộ là thao tác có thể **I/O-blocking**; offload lên `boundedElastic`.
- **Xác minh BCrypt/Argon2** là công việc **CPU-intensive**; nên có giới hạn concurrency và không thực hiện vô hạn trên event loop.
- `UserDetailsRepositoryReactiveAuthenticationManager` của Spring Security dùng `ReactiveUserDetailsService` để tìm user, rồi thực hiện kiểm tra password và trạng thái user. Nó hỗ trợ `setPasswordEncoder(...)` và `setScheduler(...)` để điều chỉnh scheduler cho phần xử lý liên quan đến password; mặc định của implementation dành cho xử lý CPU. Scheduler của password matching **không thay thế scheduler dùng cho I/O JDBC**.

Đừng dùng `NoOpPasswordEncoder` hoặc lưu mật khẩu plaintext để “tăng tốc” production. Chọn thuật toán hash phù hợp, có salt, cost và quy trình nâng cấp hash theo chính sách bảo mật.

## 6. Demo chạy được: WebFlux + Spring Security + JDBC/H2 tại blocking boundary

Demo này chủ động dùng **JDBC đồng bộ**, không giả định nó non-blocking. Để tránh lệ thuộc MySQL/PostgreSQL ngoài máy học, backend là H2 in-memory qua `JdbcTemplate`. App tạo một user demo và một endpoint bảo vệ bằng HTTP Basic. Mọi lookup JDBC do authentication flow tạo ra được chạy trên scheduler `jdbc-auth` với giới hạn tài nguyên. Password dùng BCrypt hash.

Phiên bản minh họa: **Spring Boot 3.3.13**, Java 17+, Gradle phù hợp Spring Boot 3.3.

### 6.1 Cấu trúc

```text
jdbc-boundary-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/boundary/BlockingBoundaryApplication.java
  src/main/java/demo/boundary/BlockingUserLookup.java
  src/main/java/demo/boundary/SecurityConfiguration.java
  src/main/java/demo/boundary/ApiController.java
  src/test/java/demo/boundary/BlockingBoundaryTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'jdbc-boundary-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.boundary'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` cung cấp reactive web server; `spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và HikariCP. Thêm JDBC starter **không biến JDBC thành reactive**. Không có `spring-boot-starter-web` để tránh trộn định hướng web stack khi học.

### 6.2 Khởi động app và seed user trong H2

**src/main/java/demo/boundary/BlockingBoundaryApplication.java**

```java
package demo.boundary;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;

@SpringBootApplication
public class BlockingBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(BlockingBoundaryApplication.class, args);
    }

    @Bean
    ApplicationRunner seedUser(JdbcTemplate jdbc, PasswordEncoder encoder) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE IF NOT EXISTS app_users (
                    username VARCHAR(80) PRIMARY KEY,
                    password_hash VARCHAR(100) NOT NULL,
                    enabled BOOLEAN NOT NULL
                )
                """);

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM app_users WHERE username = ?",
                Integer.class, "reader");

            if (count != null && count == 0) {
                jdbc.update("""
                    INSERT INTO app_users(username, password_hash, enabled)
                    VALUES (?, ?, ?)
                    """, "reader", encoder.encode("dev-only-password"), true);
            }
        };
    }
}
```

Lưu ý:

- `ApplicationRunner` là công việc **khởi động** (không phải request processing); dùng JDBC đồng bộ tại đây không chặn event-loop đang xử lý request như anti-pattern ở mục 1.
- H2 in-memory không phải user store production.
- `"dev-only-password"` là credential cố định **chỉ cho demo localhost**; production phải lấy secret từ hệ thống quản lý thích hợp, không ghi cứng trong mã nguồn.
- Mật khẩu được lưu bằng BCrypt hash trong cột `password_hash`; không lưu plaintext trong DB.

### 6.3 DAO JDBC chỉ làm việc đồng bộ

**src/main/java/demo/boundary/BlockingUserLookup.java**

```java
package demo.boundary;

import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Repository;

@Repository
public class BlockingUserLookup {

    private final JdbcTemplate jdbc;

    public BlockingUserLookup(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public UserDetails loadByUsername(String username) {
        List<UserDetails> users = jdbc.query(
            """
            SELECT username, password_hash, enabled
            FROM app_users
            WHERE username = ?
            """,
            (rs, rowNum) -> User.withUsername(rs.getString("username"))
                .password(rs.getString("password_hash"))
                .disabled(!rs.getBoolean("enabled"))
                .roles("READER")
                .build(),
            username);

        if (users.isEmpty()) {
            throw new UsernameNotFoundException("User not found");
        }
        return users.get(0);
    }
}
```

DAO này **cố ý imperative**: method `loadByUsername` trả `UserDetails`, không tự tạo Mono, không tự chọn thread. Việc tách nó ra giúp nhìn thấy ranh giới blocking ở adapter. Câu SQL dùng `?` với tham số truyền qua `JdbcTemplate`, không nối username từ request vào query, nhằm tránh SQL injection.

`UsernameNotFoundException` là một tín hiệu xác thực thất bại; không nên biến mọi lỗi database, timeout, LDAP unavailable thành “username không tồn tại” vì sẽ che giấu sự cố hạ tầng. Không trả thông tin SQL/user enumeration chi tiết cho client.

### 6.4 Adapter ReactiveUserDetailsService và authentication manager

**src/main/java/demo/boundary/SecurityConfiguration.java**

```java
package demo.boundary;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean(destroyMethod = "dispose")
    Scheduler jdbcAuthScheduler() {
        return Schedulers.newBoundedElastic(4, 100, "jdbc-auth");
    }

    @Bean
    ReactiveUserDetailsService users(
            BlockingUserLookup lookup,
            @Qualifier("jdbcAuthScheduler") Scheduler scheduler) {

        return username -> Mono
            .fromCallable(() -> lookup.loadByUsername(username))
            .subscribeOn(scheduler);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            ReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager = new UserDetailsRepositoryReactiveAuthenticationManager(
            users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager authenticationManager) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/private")
                    .hasRole("READER")
                .anyExchange().authenticated())
            .httpBasic(basic ->
                basic.authenticationManager(authenticationManager))
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Các chi tiết quan trọng:

1. `lookup.loadByUsername(username)` **nằm bên trong `Mono.fromCallable`**, nên không chạy khi tạo publisher.
2. `subscribeOn(scheduler)` đặt ngay sau source, đảm bảo phần JDBC lookup khi được subscribe chạy trên pool `jdbc-auth`, không chiếm Netty event-loop.
3. Scheduler được giới hạn để không tạo vô hạn blocking worker. `@Qualifier` bảo đảm đúng scheduler được dùng.
4. `ReactiveUserDetailsService` là bean do ứng dụng cung cấp: Spring Boot không cần sinh tài khoản `user` ngẫu nhiên. User demo được tạo bởi `ApplicationRunner`.
5. `UserDetailsRepositoryReactiveAuthenticationManager` dùng `ReactiveUserDetailsService` để lấy hash và `PasswordEncoder` để so sánh password. Nó không bắt DAO biến thành non-blocking.
6. `httpBasic(basic -> basic.authenticationManager(...))` kết nối manager vào Basic authentication một cách **tường minh**, không phụ thuộc suy luận auto-config khi đã tự tạo chain.
7. `hasRole("READER")` kiểm tra authority `ROLE_READER` của user được DAO dựng; `anyExchange().authenticated()` yêu cầu đăng nhập với request còn lại.
8. `formLogin(...disable())` chỉ để API demo dễ kiểm tra HTTP 401; ứng dụng UI với cookie/session cần chính sách form/CSRF phù hợp.
9. Password hash matching có cost CPU và được manager xử lý bằng scheduler riêng theo implementation; không phải bất cứ thao tác nào sau `subscribeOn` đều bắt buộc tiếp tục chạy trên scheduler JDBC.
10. Khi muốn giới hạn request/công suất login chặt hơn, bổ sung queue/concurrency/rate limit theo ngân sách backend; scheduler là **một lớp** kiểm soát chứ không phải toàn bộ.

Nếu sử dụng `ReactiveUserDetailsService` nhưng **vô tình viết**:

```java
return username -> Mono.just(lookup.loadByUsername(username));
```

thì việc query vẫn xảy ra ngay lúc gọi `findByUsername` trên thread hiện tại. Đây là lỗi rất phổ biến khi tích hợp legacy.

### 6.5 Controller và request đã xác thực

**src/main/java/demo/boundary/ApiController.java**

```java
package demo.boundary;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/public")
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping("/api/private")
    public Mono<String> privateEndpoint(Principal principal) {
        return Mono.just("hello " + principal.getName());
    }
}
```

Không cần gọi JDBC lần nữa trong controller chỉ để lấy tên: authentication manager đã tạo principal khi HTTP Basic thành công. Truy vấn dữ liệu riêng của từng người dùng vẫn cần kiểm quyền đối tượng/tenant, không chỉ đọc `principal.getName()`.

### 6.6 Chạy và kiểm tra bằng curl

Trong thư mục dự án (JDK 17+ và Gradle tương thích):

```bash
gradle bootRun
```

Nếu đã có Gradle wrapper, dùng `./gradlew bootRun`; Windows: `gradlew.bat bootRun`. Từ terminal khác:

```bash
curl -i http://localhost:8080/api/public
curl -i -H "Accept: application/json" \
    http://localhost:8080/api/private

# Trình curl CLI sẽ hỏi password; nhập dev-only-password
curl -i -u reader http://localhost:8080/api/private

# Nhập sai password để kiểm thử trường hợp âm tính
curl -i -u reader http://localhost:8080/api/private
```

Hai lệnh cuối giống nhau về cú pháp; **kết quả phụ thuộc mật khẩu nhập** tại prompt. Trên PowerShell, nếu `curl` là alias, dùng `curl.exe`.

| Request | HTTP kỳ vọng | Giải thích |
|---|---|---|
| `GET /api/public` không credential | 200, body `public` | URL cố ý public |
| `GET /api/private` không credential | 401 | Chưa xác thực |
| `GET /api/private` với `reader` / `dev-only-password` | 200, body `hello reader` | JDBC tìm user, BCrypt so khớp, có `ROLE_READER` |
| `GET /api/private` với mật khẩu sai | 401 | Xác thực thất bại |
| `GET /api/private` với user không tồn tại | 401 | Không tiết lộ thông tin xác thực cụ thể |

Không đoán stdout chính xác của Gradle vì phụ thuộc môi trường, phiên bản JDK, plugin và log; phần quan trọng là HTTP status/body. Nếu database chưa init xong, H2 connection lỗi hoặc app không chạy, hãy xem log thay vì mặc nhiên coi mọi lỗi là 401.

## 7. Kiểm thử tự động ở ranh giới security + JDBC

**src/test/java/demo/boundary/BlockingBoundaryTest.java**

```java
package demo.boundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BlockingBoundaryTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsPublic() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void privateRouteNeedsAuthentication() {
        client.get().uri("/api/private")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void jdbcBackedUserCanAuthenticate() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "dev-only-password"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello reader");
    }

    @Test
    void wrongPasswordIsRejected() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("reader", "wrong-password"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void unknownUserIsRejected() {
        client.get().uri("/api/private")
            .headers(h -> h.setBasicAuth("missing", "anything"))
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

Chạy:

```bash
gradle test
```

Dự án đầy đủ có **5 phương thức test**, mong đợi đều pass khi dependency tải được và runtime phù hợp. Test kiểm chứng cấu hình tích hợp, không chứng minh bằng đo đạc rằng event loop không bao giờ bị block. Cần test riêng về scheduler/latency/thread contention và monitor dưới tải thật để đánh giá giới hạn.

### Kiểm tra thread trong một thí nghiệm bổ sung

Tạm thời instrument DAO trong môi trường local:

```java
String currentThread = Thread.currentThread().getName();
System.out.println("JDBC lookup thread = " + currentThread);
```

Đoạn trên chỉ để kiểm tra scheduler; không ghi username/password, credential hay SQL params nhạy cảm. Tên thread thông thường chứa `jdbc-auth` do `Schedulers.newBoundedElastic` đặt tên. **Không phụ thuộc tên thread làm điều kiện bảo mật**: nó là công cụ chẩn đoán, không phải hợp đồng public API. Không giữ `System.out.println` ở DAO production.

## 8. Tích hợp Spring Data JPA đúng ranh giới transaction

JPA/`EntityManager` vẫn blocking. Với ORM, thêm một vấn đề: **transaction và persistence context của JDBC/JPA imperative thường gắn với thread hiện hành**. Spring `@Transactional` khi dùng `PlatformTransactionManager` cũng dùng cơ chế gắn với thread. Vì vậy không nên bắt đầu transaction trên event-loop rồi chuyển một đoạn truy vấn qua worker thread khác và cho rằng transaction vẫn tự đi theo.

### 8.1 Mô hình đúng: service imperative có transaction, gọi từ adapter

Giả sử ứng dụng đã có `JpaRepository<AccountEntity, Long>`:

```java
@Service
public class BlockingAccountService {
    private final AccountRepository repository;

    public BlockingAccountService(AccountRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public AccountView load(long accountId) {
        var entity = repository.findById(accountId)
            .orElseThrow(() -> new AccountNotFoundException(accountId));

        // Mapping dữ liệu cần thiết trong transaction,
        // kể cả quan hệ lazy nếu cần và được phép truy cập.
        return new AccountView(entity.getId(), entity.getDisplayName());
    }
}
```

Đây là **mảnh mã minh họa kiến trúc**, cần có entity, repository, `AccountView` và `AccountNotFoundException` của ứng dụng. Điểm quan trọng là `load(...)` trả **DTO thường**, không trả `Mono`; transaction của `PlatformTransactionManager` bao toàn bộ các thao tác JPA trong method được gọi qua Spring proxy.

Adapter reactive ở **bean khác**:

```java
@Service
public class ReactiveAccountGateway {
    private final BlockingAccountService legacy;
    private final Scheduler blockingScheduler;

    public ReactiveAccountGateway(
            BlockingAccountService legacy,
            @Qualifier("jdbcAuthScheduler") Scheduler blockingScheduler) {
        this.legacy = legacy;
        this.blockingScheduler = blockingScheduler;
    }

    public Mono<AccountView> load(long accountId) {
        return Mono.fromCallable(() -> legacy.load(accountId))
            .subscribeOn(blockingScheduler);
    }
}
```

Đoạn này cũng chỉ minh họa; cần imports. Luồng đúng là scheduler worker **gọi qua bean Spring proxy** → transaction được mở trên worker thread → repository truy vấn, lazy mapping và commit/rollback trong cùng lời gọi → chỉ trả DTO về Reactor. Không chuyển entity còn lazy association ra khỏi transaction rồi đọc ở thread khác.

**Cảnh báo self-invocation:** gọi một method `@Transactional` bằng `this.load(...)` trong cùng bean có thể bỏ qua Spring AOP proxy, khiến transaction không được áp dụng như mong đợi. Dùng bean riêng hoặc `TransactionTemplate` nếu cần chắc chắn ranh giới.

### 8.2 Mô hình sai

```java
// Anti-pattern: transaction imperative không tự bám theo
// một chuỗi Mono được tạo và chạy trên thread khác.
@Transactional
public Mono<AccountView> load(long accountId) {
    return Mono.fromCallable(() ->
        repository.findById(accountId)
            .map(e -> new AccountView(e.getId(), e.getDisplayName()))
            .orElseThrow())
        .subscribeOn(Schedulers.boundedElastic());
}
```

Vấn đề: thời điểm chạy code JPA nằm **lúc subscription**, có thể ở thread khác; còn proxy/transaction manager và loại method trả `Mono` có quy tắc áp dụng riêng. Với `PlatformTransactionManager` JDBC/JPA, không dựa vào `@Transactional` của method trả reactive publisher để tự giữ transaction; hãy định nghĩa một method **imperative trả DTO** như mục 8.1.

### 8.3 Khi nào chọn R2DBC thay JPA/JDBC?

Nếu luồng request chủ yếu là database I/O, cần tải concurrent cao và driver/database hỗ trợ R2DBC, sử dụng Spring Data R2DBC và `R2dbcEntityTemplate`/`ReactiveCrudRepository` có thể phù hợp hơn. Nhưng:

- R2DBC **không phải adapter “tự động biến JPA thành reactive”**; entity mapping, cascade, lazy loading, query model và transaction khác JPA.
- Nếu cần JPA mapping/ORM hiện có, hãy đánh giá chi phí chuyển đổi với lợi ích thực; giữ ranh giới blocking có thể là bước chuyển tiếp có quản trị.
- Transaction reactive thường dùng `ReactiveTransactionManager` và Reactor Context, **khác** `PlatformTransactionManager` + thread-local. Không trộn transaction manager và kỳ vọng chúng bao cùng một đơn vị công việc.
- Truy vấn nhỏ vẫn cần index, giới hạn thời gian, pooling và kiểm quyền. Đổi driver không chữa schema/query kém.

## 9. LDAP đồng bộ: search, bind và kiểm tra danh tính

LDAP thường tham gia hai hoạt động: tìm người dùng/nhóm trong directory và xác minh credential. Các implementation LDAP/JNDI đồng bộ có thể chặn lúc mở kết nối, bind, search, đọc group membership hoặc khi server mất kết nối.

### 9.1 Adapter tại ranh giới blocking

Nếu ứng dụng đã có `BlockingLdapIdentityService` dùng `LdapTemplate`/JNDI đúng chuẩn:

```java
public Mono<UserDetails> findByUsername(String username) {
    return Mono.fromCallable(() -> ldapIdentityService.lookup(username))
        .subscribeOn(ldapScheduler);
}
```

Đây là **mảnh mã tích hợp**, không phải ứng dụng LDAP đầy đủ: bạn cần định nghĩa `ldapIdentityService`, cấu hình context source/LDAP server, xây UserDetails từ kết quả và cung cấp scheduler có giới hạn. Khi flow gồm cả LDAP bind và group lookup, cần xem đó là **một thao tác đồng bộ** có timeout, session và tài nguyên phải đóng trong adapter. Đừng gọi `LdapTemplate.search(...)` trực tiếp từ event-loop rồi chỉ bọc kết quả bằng `Mono.just(...)`.

### 9.2 LDAP cần các giới hạn riêng

- **Network timeout:** connect timeout, read timeout, giới hạn thời gian search, số entry trả về và referral policy theo client/server.
- **TLS:** LDAP over TLS (LDAPS hoặc StartTLS nếu được hỗ trợ/cấu hình đúng), xác minh certificate/hostname; không gửi mật khẩu qua kết nối không được bảo vệ.
- **Filter injection:** không nối thẳng `"(uid=" + username + ")"` từ input chưa được escape vào LDAP search filter. Dùng builder/escaping hỗ trợ của thư viện, ví dụ query builder cho LDAP.
- **Quyền truy cập:** account bind/search dùng least privilege; không log password, DN đầy đủ nếu nhạy cảm, token hay kết quả private.
- **Pool và concurrency:** thread blocking, connection pool directory, retry/circuit breaker có giới hạn.
- **Failure mode:** directory không phản hồi là sự cố hạ tầng, không nên coi mọi thất bại mạng là password sai; cần phân biệt log nội bộ với thông điệp an toàn cho client.

Việc ánh xạ LDAP group sang authorities của Spring Security phải do policy rõ ràng quyết định, chẳng hạn `ROLE_STAFF` chỉ khi nhóm đáng tin thực sự khớp. Không lấy giá trị group từ header hoặc payload do client tự gửi.

### 9.3 Dùng client LDAP thực sự bất đồng bộ nếu có

Nếu tổ chức có thư viện LDAP asynchronous phù hợp, một cổng dịch vụ định danh riêng hoặc giao thức khác với client non-blocking, bạn có thể thiết kế adapter reactive **thực sự**. Nhưng phải xác minh thư viện có I/O async thật, không chỉ trả `CompletableFuture` bên ngoài một nhóm thread blocking. Việc đổi giao diện trả về không đủ chứng minh non-blocking.

## 10. Timeout, cancellation, lỗi và an toàn truy cập

### 10.1 Không biến lỗi hạ tầng thành 401 sai nguyên nhân

Trong auth flow:

| Trạng thái | Cách hiểu | Điều nên làm |
|---|---|---|
| User không tồn tại | Kết quả tìm kiếm danh tính không có | Từ chối xác thực, không tiết lộ username tồn tại hay không |
| Password không khớp | Credential sai | Từ chối xác thực; rate limit chống đoán password |
| User bị disable/lock | Tài khoản không được phép login | Manager kiểm trạng thái account |
| JDBC pool exhausted | Hạ tầng không xử lý kịp | Ghi metrics/log có kiểm soát, fail closed, phục hồi tài nguyên |
| LDAP timeout/unavailable | Danh bạ lỗi mạng/server | Không tự cho phép anonymous truy cập private data; theo dõi incident |
| Publisher bị timeout | Request hết thời gian chờ | Hủy subscription và kiểm soát tác vụ blocking còn sống; không đảm bảo JDBC đã bị dừng |

**Fail closed** nghĩa là không cấp quyền khi không xác minh được danh tính. Nhưng không được đánh đồng tất cả lỗi backend thành “sai mật khẩu” khi ghi log/metrics nội bộ; điều đó làm khó phát hiện outage và có thể gây lockout hoặc phản ứng sai trong vận hành.

### 10.2 Timeout có hai lớp

Giả sử cần deadline cho một lookup, bạn có thể có:

```java
Mono<UserDetails> user = Mono.fromCallable(() -> dao.loadByUsername(username))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(3));
```

Đây là **mảnh code minh họa**; cần import `Duration` và chọn thời gian theo SLO thật. Timeout Reactor giới hạn thời gian đợi của subscriber; nó không thay thế JDBC statement timeout, connection acquisition timeout, LDAP connect/read timeout. Không gắn retry vô hạn vào một request login lỗi do DB chậm.

### 10.3 Cancellation không nên phá ranh giới giao dịch

Khi client đóng kết nối, subscription có thể bị cancel, nhưng một lời gọi JDBC/JPA/LDAP sync đã bắt đầu vẫn có thể đang giữ thread/connection. Thao tác cần có timeout thật và luôn giải phóng tài nguyên qua JDBC/JPA/Spring-managed boundary. Với giao dịch cập nhật, cancellation của HTTP không phải giao thức “rollback từ xa” bảo đảm; xác định hành vi commit/rollback, idempotency và audit ở service.

### 10.4 Security context và transaction context khác nhau

Spring Security reactive thường truyền `SecurityContext` qua **Reactor Context**. Trong khi JDBC/JPA `@Transactional` với `PlatformTransactionManager` dùng **ThreadLocal** gắn connection/EntityManager ở thread nơi transaction hoạt động. Không được suy luận:

- “Vì Reactor Context truyền qua `publishOn` nên JDBC transaction cũng truyền qua.”
- “Vì `@Transactional` được khai báo, một `Mono.fromCallable` tạo ở trong method tự thuộc cùng imperative transaction.”
- “Vì biết username từ security context, repository tự kiểm quyền từng bản ghi.”

Cần ranh giới transaction riêng, và kiểm tra quyền tài nguyên bằng danh tính đã xác minh.

## 11. Lựa chọn chiến lược theo hệ thống

| Hoàn cảnh | Khuyến nghị |
|---|---|
| Dự án đang dùng JDBC/JPA ổn định, chuyển HTTP sang WebFlux | Giữ DAO/service imperative, đặt adapter `Mono.fromCallable + subscribeOn` có pool/timeout/metrics |
| Ứng dụng chủ yếu truy vấn SQL và có driver R2DBC phù hợp | Đánh giá chuyển data access sang R2DBC; tránh bọc JDBC lâu dài nếu tải yêu cầu cao |
| Xác thực dựa LDAP cũ/JNDI | Offload cả search/bind đồng bộ lên scheduler riêng, đặt timeout bảo mật và pool; cân nhắc IdP ngoài |
| Cần giữ transaction JPA nhiều bước | Đóng toàn bộ đơn vị công việc trong một method imperative `@Transactional` gọi từ worker thread |
| Muốn hỗ trợ JWT/Identity Provider | Ưu tiên resource server/JWT validation phù hợp, nhưng xác minh token, chính sách mạng và kiểm quyền vẫn bắt buộc |
| Auth load cao, password hash CPU nặng | Tách ngân sách CPU cho hash, ngân sách I/O cho directory/DB; rate limit, bulkhead, theo dõi độ trễ |
| Không xác định được nguồn user hiện tại | Kiểm tra `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` và chain thực tế; không đoán từ dependency |

Một hệ thống có thể dùng đồng thời reactive HTTP và blocking repository một cách có kiểm soát. Nhưng nếu phần lớn request phải chờ blocking I/O, lợi thế concurrency của WebFlux giảm; nếu không có ràng buộc bắt buộc với reactive stack, một ứng dụng MVC/Servlet với threading phù hợp cũng đáng được so sánh. Lựa chọn kiến trúc phụ thuộc đặc điểm I/O, tài nguyên vận hành và nhu cầu toàn hệ thống, không phải nhãn “reactive” hay “non-reactive” một mình.

## 12. Những lỗi phổ biến và cách sửa

| Anti-pattern | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| `Mono.just(jdbc.query(...))` | JDBC đã chạy blocking trước khi tạo Mono | `Mono.fromCallable(...).subscribeOn(blockingScheduler)` |
| Gọi JPA/LDAP sync trong `map` chạy trên event-loop | Có thể giữ event-loop trong thời gian chờ | Offload đúng thao tác vào worker |
| Dùng `Schedulers.parallel()` cho JDBC/LDAP chờ mạng | Scheduler dành cho công việc CPU, không chờ I/O lâu | `boundedElastic` hoặc scheduler blocking riêng |
| Dùng `boundedElastic` nhưng queue không có giám sát | Task đợi nhiều, latency và overload tăng | Đặt giới hạn, metrics, rate limit/bulkhead |
| Tăng thread để chữa DB pool nhỏ | Chỉ thêm thread đang chờ connection | Tối ưu query, pool, concurrency theo ngân sách |
| Nghĩ `Mono.timeout` sẽ chắc chắn ngắt SQL | JDBC sync có thể tiếp tục chạy sau timeout | Đặt driver/statement/socket timeout |
| `@Transactional` method trả `Mono` bọc JPA | Giao dịch imperative không tự sống qua subscription/thread khác | Gói JPA trong service imperative `@Transactional`, gọi qua proxy ở worker |
| Trả entity JPA có lazy field ra chuỗi reactive | Lazy loading sau transaction có thể lỗi hoặc thêm blocking I/O | Map sang DTO đầy đủ trong transaction |
| Dùng `ReactiveSecurityContextHolder` thay cho tx manager | Security context khác resource/transaction | Quản lý transaction đúng loại backend |
| Đặt BCrypt trong event-loop theo kiểu tự code | CPU-intensive hash làm tăng latency request khác | Dùng manager/scheduler/giới hạn CPU phù hợp |
| Lưu password plaintext hoặc dùng NoOp encoder | Rủi ro lộ credential | Sử dụng hash có salt và cost phù hợp |
| LDAP filter nối chuỗi user input | LDAP injection | Builder/escaping, validate input, least privilege |
| Backend auth lỗi thì `permitAll()` private route | Mất bảo mật khi sự cố hạ tầng | Fail closed, policy rõ ràng và observability |
| Tự `subscribe()` cho lookup trong controller | Tách flow lỗi/cancel/context, response không chờ auth đúng | Trả publisher để framework subscribe |
| Log password, Basic Authorization, JDBC secret | Lộ credential | Che/redact log và hạn chế người xem |
| Chỉ test login đúng | Không phát hiện endpoint mở/timeout/brute force | Test anonymous, sai password, quá tải, outage và data authorization |

## 13. Checklist triển khai và bài tập

### 13.1 Checklist

1. Xác định từng thư viện I/O: JDBC, JPA, LDAP client nào thực sự blocking? Không đánh đồng interface `Mono` với I/O async.
2. Tìm những vị trí `Mono.just(dao.call())`, `map(x -> dao.call())` hoặc truy vấn từ controller, event-loop.
3. Đặt **toàn bộ lời gọi đồng bộ** vào `fromCallable/fromRunnable`, `subscribeOn` scheduler có ngân sách rõ.
4. Chỉnh pool DB/LDAP cùng scheduler; đặt giới hạn queue/concurrency và quan sát request login burst.
5. Với JPA/transaction, gọi bean imperative `@Transactional` qua proxy trong worker, trả DTO.
6. Thiết lập BCrypt/Argon2/PBKDF2 với password hash đúng và ngân sách CPU; không dùng plaintext password.
7. Đặt timeout ở HTTP/publisher **và** driver/statement/socket, hiểu limitation của cancellation.
8. Phân biệt bad credential với DB/directory failure ở metrics và nội bộ, không lộ thông tin cho client.
9. Kiểm thử âm tính: không credential, password sai, user không tồn tại, disabled user, sai role/tenant.
10. Giám sát event loop blocking, blocking scheduler utilization, JDBC pool pending, LDAP latency và authentication error rate.
11. Nếu không còn đủ năng lực phục vụ tải, xem xét R2DBC, IdP async hoặc thay kiến trúc một cách có số liệu.

### 13.2 Bài tập

1. Chạy demo và giải thích tại sao `JdbcTemplate` vẫn blocking dù HTTP endpoint trả `Mono`.
2. Đổi adapter từ `fromCallable` sang `Mono.just(lookup.loadByUsername(...))`, rồi chỉ ra thời điểm DB query chạy; trả về cách đúng.
3. Thử in tên thread trong DAO (không log credentials), xem nó có chứa `jdbc-auth` không; đo lại khi dùng `Schedulers.boundedElastic()`.
4. Viết hai test mới: user bị `enabled = false` và user không có `ROLE_READER`; xác nhận endpoint private không chấp nhận.
5. Giả sử Hikari pool giảm còn 2 connections trong khi 20 login cùng lúc. Hãy mô tả hàng đợi có thể hình thành ở đâu và vì sao chỉ tăng số thread không chữa được DB bottleneck.
6. Với JPA, so sánh service `@Transactional public AccountView load()` chạy hoàn toàn trên worker với method `@Transactional Mono<AccountView> load()` bị defer; giải thích rủi ro transaction/lazy loading.
7. Với LDAP, viết danh sách timeout connect/read/search, TLS settings, filter escaping và cách fail closed khi directory mất kết nối.
8. Viết kịch bản kiểm thử outage: tắt DB ngay giữa login, xác nhận client không thể vào private resource và metrics phân biệt lỗi backend với mật khẩu sai.
9. Nêu ba trường hợp nên chuyển sang R2DBC hoặc IdP thay vì tiếp tục wrap blocking backend; giải thích chi phí migration.

## Tóm tắt

**JDBC, Spring Data JPA và LDAP/JNDI đồng bộ đều có thể giữ thread trong lúc chờ I/O**. Trong WebFlux, dùng `Mono.fromCallable(...)` hoặc `Mono.fromRunnable(...)` cùng `subscribeOn(Schedulers.boundedElastic())` / scheduler blocking riêng để đặt ranh giới rõ ràng; cách bọc này **không biến thư viện sync thành non-blocking**. Với Spring Security, đưa JDBC/JPA/LDAP lookup vào `ReactiveUserDetailsService` adapter, để `ReactiveAuthenticationManager` thực hiện xác thực bằng password hash, và bảo vệ route bằng `SecurityWebFilterChain`. Với JPA, đặt transaction imperative trong một lời gọi synchronous được thực thi trên worker thread. Kết hợp timeout ở driver, connection pool, queue cap, rate limiting, giám sát và kiểm thử âm tính để ranh giới này thực sự có thể vận hành an toàn.

## Tài liệu chính thức

- Project Reactor — FAQ: How Do I Wrap a Synchronous, Blocking Call?: https://projectreactor.io/docs/core/3.6.0/reference/faq.html
- Spring Security 6.3 — ReactiveUserDetailsService API: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/core/userdetails/ReactiveUserDetailsService.html
- Spring Security — UserDetailsRepositoryReactiveAuthenticationManager: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authentication/UserDetailsRepositoryReactiveAuthenticationManager.html
- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Boot 3.3 — WebFlux Security Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Framework — Declarative transaction implementation, ThreadLocal và ReactiveTransactionManager: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — JDBC connections và thread-bound connection: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
