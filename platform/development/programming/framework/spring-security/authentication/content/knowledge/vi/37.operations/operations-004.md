# Đo độ trễ xác thực, chi phí băm mật khẩu và truy vấn tài khoản trong Spring Security

## 1. Vì sao xác thực có thể chậm dù endpoint rất đơn giản?

Một request `POST /login` có thể chỉ trả redirect hoặc JSON ngắn, nhưng phía backend thường thực hiện nhiều bước:

- Đọc request, xử lý cookie/CSRF, chọn `SecurityFilterChain` và authentication filter.
- Lấy thông tin user từ DB/LDAP/dịch vụ định danh; chờ connection pool và network.
- Kiểm tra account có enabled/locked/expired hay không.
- Chạy `PasswordEncoder.matches(...)` với bcrypt/PBKDF2/scrypt/Argon2; công việc **cố tình tốn CPU hoặc bộ nhớ** để chống dò password offline.
- Nếu policy thay đổi, có thể chạy `upgradeEncoding(...)` và `encode(...)` rồi ghi password hash mới.
- Tạo `Authentication`, chạy các kiểm tra bổ sung, ghi session/security context, audit login, redirect hoặc tạo token.
- Đi qua proxy/network/browser; nếu có IdP/OIDC, còn thêm các request/redirect khác.

Nếu chỉ đọc `http.server.requests` rồi thấy p95 tăng, chưa biết nguyên nhân do **băm mật khẩu**, **DB**, **Hikari pool**, **lockout/rate limiting**, **session persistence**, **proxy** hay **IdP**. Bài này trình bày phương pháp đo từng lớp, đọc kết quả, thiết kế dashboard và dùng kết quả để tối ưu **không làm giảm bảo mật**.

Ngữ cảnh chính: Spring Boot 3.x + Spring Security 6.5 Servlet (Spring MVC), Java 17+, Micrometer/Actuator, database relational. Các nguyên tắc tương tự áp dụng với WebFlux, LDAP và SSO nhưng hook/cơ chế khác.

### Mục tiêu hoàn thành

Sau bài này, bạn có thể:

1. Phân biệt **request latency**, **authentication-manager latency**, **account-lookup latency**, **password verification/encoding latency** và **session/audit latency**.
2. Ghi nhận `count`, `total time`, p50/p95/p99, histogram cùng throughput/error rate **theo tag ít cardinality**.
3. Cấu hình Spring Boot Actuator + Micrometer và biết các observation mặc định của Spring Security.
4. Phân tích latency của `UserDetailsService.loadUserByUsername`, `PasswordEncoder.matches`/`encode` và pool DB.
5. Benchmark work factor bcrypt/PBKDF2/Argon2 **trên hardware thực**, không chọn thuật toán yếu chỉ để đạt một chỉ số nhanh.
6. Viết test xác minh instrumentation, so sánh trước–sau và tránh leak raw username/password/token.

## 2. Định nghĩa các lớp độ trễ: không đánh đồng

Một sơ đồ rút gọn đối với đăng nhập bằng password:

```text
Client
 |
 |  T_network + browser + TLS + load balancer
 v
Ingress / Reverse proxy
 |
 |  T_queue + servlet container thread
 v
Spring Security FilterChain
 |
 |--- CSRF / request extraction / basic rate-limit
 |
 |--- AuthenticationManager.authenticate()
 |      |
 |      +--- UserDetailsService.loadUserByUsername()
 |      |      +--- Connection pool wait
 |      |      +--- Network DB / LDAP
 |      |      +--- SQL execution + row mapping
 |      |
 |      +--- account status checks
 |      |
 |      +--- PasswordEncoder.matches(raw, encoded)
 |      |      +--- CPU / memory work factor
 |      |
 |      +--- optional breached password check
 |      +--- optional upgradeEncoding + encode + updatePassword
 |
 |--- session/security context persist, audit, success handler
 |
 v
HTTP response
 |
 v
Client
```

Các định nghĩa hữu ích:

| Metric đề xuất | Ranh giới | Bao gồm | Không bao gồm |
| --- | --- | --- | --- |
| `http.server.requests` | Server nhận request → trả response theo instrumentation Spring MVC | Filter/controller handling liên quan request, theo cấu hình | Thời gian client, DNS và network trước server |
| `spring.security.authentications` | Observation quanh authentication attempt | Công việc của manager/provider tùy version/config | Không mặc nhiên toàn bộ HTTP response |
| `app.auth.manager` | Application wrapper của `AuthenticationManager.authenticate` | Lookup + verify + provider logic | Thường không gồm TLS và post-login session writer |
| `app.auth.account.lookup` | `UserDetailsService.loadUserByUsername` hoặc DB repository | Thời gian call lookup được đo | Không luôn đồng nghĩa SQL execution; có thể gồm pool wait/cache |
| `app.auth.password.matches` | `PasswordEncoder.matches` | Băm/so sánh credential (CPU/memory) | Không gồm DB lookup nếu đo đúng |
| `app.auth.password.encode` | `PasswordEncoder.encode` | Hash mới khi đăng ký/reset/rehash | Không nhất thiết có trên login bình thường |
| `app.auth.postlogin` | App success handler / session+audit (đặt rõ boundaries) | Thành phần sau provider success | Đừng coi provider success là browser session đã bền vững |
| `jdbc.connections.*` / `hikaricp.*` | Pool management gauges/timers | Active/idle/waiting/maximum và pool-specific | Không tự cho biết SQL nào chậm |

Một HTTP request có thể là `GET /api/orders` dùng session cookie và **không** gọi password encoder. Mặt khác, một lần `POST /login` bằng password thực sự có thể tiêu tốn hàng trăm mili-giây ở hàm hash. Vì vậy không lấy trung bình của **toàn bộ HTTP requests** để đại diện cho latency login.

### Định nghĩa chính xác “login thành công”

- `AuthenticationManager.authenticate` trả `Authentication` có thể chưa có nghĩa session đã được persisted hoặc redirect đã xong.
- Một `AuthenticationSuccessEvent` phản ánh sự kiện tại authentication layer, có thể không phải mỗi lần user interactive login.
- Đăng nhập có thể fail với `BadCredentialsException`, `LockedException`, thiếu MFA, timeout DB hoặc IdP error; dashboard cần phân loại nhóm **ổn định và ít nhãn**, không đưa message/raw username vào tag.
- Nếu bật HTTP Basic và mỗi request gửi credentials, xác thực có thể diễn ra **mỗi request** thay vì chỉ lúc login; đo theo authentication mechanism và traffic mix.

## 3. Các thống kê cần đo và đọc đúng

| Chỉ số | Câu hỏi trả lời | Bẫy thường gặp |
| --- | --- | --- |
| `count` / throughput | Có bao nhiêu attempts/s? | Dồn login và JWT validation vào một series |
| `mean` = total/count | Chi phí trung bình | Che khuất hàng đợi và long tail |
| `p50` | Điển hình một nửa requests | Không nêu trải nghiệm các request chậm |
| `p95` | Mốc 95% requests không vượt | P95 thiếu ý nghĩa khi mẫu ít |
| `p99` | Đuôi chậm nhất của 99% | Rất nhiễu khi lưu lượng thấp |
| `max` | Đỉnh theo cửa sổ thống kê | Micrometer max có thể reset theo time window |
| `failure rate` | Mức lỗi xác thực/hạ tầng | Password sai không luôn là “lỗi hệ thống” |
| `CPU / allocation / GC` | Password hash hay server nóng? | CPU bình quân thấp vẫn có queue theo core |
| `pool wait / active / pending` | Chờ kết nối DB? | SQL nhanh nhưng pool vẫn nghẽn |
| `DB query duration` | Tra cứu account có chậm không? | Phụ thuộc cache, index, network, locks |

### p95/p99 không phải kết quả cộng đơn giản

Giả sử bốn lần đăng nhập có lookup lần lượt 8/12/9/30 ms và verify hash 120/135/115/150 ms. P95 của lookup là 30 ms, p95 của verify là 150 ms; **p95 của tổng** không nhất thiết bằng 180 ms. Các percentile của hai phân phối không được phép cộng để tính percentile của tổng.

Nguyên nhân: các lần chậm nhất ở hai phase có thể thuộc **hai request khác nhau**, cùng với queue, session, instrumentation overhead và cách chọn mẫu. Chỉ tính p95 tổng từ **các số đo end-to-end thực tế**, sau đó dùng tracing/segment timers tìm nguyên nhân.

**Nearest-rank:** với N samples đã sắp xếp, percentile p gần đúng ở index `ceil(p*N)-1` (0-based). Metric backends có thể dùng histogram/ước lượng khác, vì vậy sample nhỏ trong Java demo khác cách Prometheus `histogram_quantile` nội suy.

### Chọn cửa sổ thống kê

- 5 phút thường phản ánh biến động gần hiện tại, nhưng với vài login/giờ có thể không đủ mẫu.
- Dashboard nên hiển thị **sample count song song với p95/p99**; bỏ qua alert p99 khi N quá thấp.
- Phân tách khung giờ cao điểm/bình thường và deployment revisions để tránh kết luận sai sau khi traffic mix thay đổi.
- Đọc latency cùng với throughput, saturation, error rate và CPU/memory; latency tăng có thể do queue, không chỉ code chạy chậm.

## 4. Quan sát mặc định của Spring Security 6.5

Spring Security hỗ trợ **Observability** khi có `ObservationRegistry` trong Spring context. Tài liệu 6.5 mô tả các spans, gồm:

- `spring.security.http.requests`: theo dõi tổng thời gian filter chain.
- `spring.security.http.chains.before` / `.after`: hoạt động nhận/trả của security filters.
- `spring.security.http.secured.requests` và `.unsecured.requests`: phần xử lý được bảo vệ/không được bảo vệ.
- `spring.security.authentications`: quá trình `AuthenticationManager`.
- `spring.security.authorizations`: bước quyết định authorization.

Những observation này rất hữu ích để đối chiếu **authentication vs authorization vs request processing**. Tuy nhiên:

1. **Observation/trace span không đồng nghĩa mỗi span mặc định sẽ trở thành một histogram Prometheus với tên giống hệt**. Điều đó phụ thuộc `ObservationHandler`, meter registry, cấu hình version và exporter.
2. Một `ObservationAuthenticationManager` có thể wrap manager để tạo observation; không giả định mọi `AuthenticationManager` tự tạo metrics trong ứng dụng đã tùy biến wiring.
3. Không dựa vào tên span `spring.security.authentications` để suy ra tự động đã tách được `loadUserByUsername` hay `matches`; muốn tách sâu phải instrument ở đúng thành phần.
4. Nếu tự tạo wrapper Micrometer quanh authentication manager, tránh nhân đôi metrics/overhead do instrumentation lồng nhau. Nên ghi rõ metric là **app-defined**, không tự tuyên bố là tên mặc định của framework.

Nguồn: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/observability.html

## 5. Bật Spring Boot Actuator + Micrometer đúng phạm vi

Trong project Spring Boot 3.x đã cấu hình plugin/dependencies, thêm vào `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Khi dùng Prometheus làm backend:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Ví dụ `src/main/resources/application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus"

  metrics:
    distribution:
      percentiles-histogram:
        "app.auth.manager": true
        "app.auth.account.lookup": true
        "app.auth.password.matches": true
      slo:
        "app.auth.manager": 100ms,250ms,500ms,1s

  observations:
    http:
      server:
        requests:
          name: http.server.requests
```

Giải thích:

- `spring-boot-starter-actuator` đưa Micrometer/Actuator integration vào ứng dụng; exporter Prometheus cần registry thích hợp.
- `/actuator/metrics` dùng để khám phá meter names và drill-down; `/actuator/prometheus` là endpoint exporter nếu module/tùy chỉnh cho phép.
- `percentiles-histogram` là tùy chọn để publish histogram buckets phục vụ percentile ở backend hỗ trợ, không tự động hiển thị p95 nếu không truy vấn đúng.
- `slo` có thể cấu hình buckets theo threshold mục tiêu; các ngưỡng 100–1000 ms chỉ là **ví dụ**, không phải bảo đảm hiệu năng hay bắt buộc của Spring.
- `http.server.requests` là meter do Spring Boot/Spring MVC observation hỗ trợ; **một số filter exceptions** và custom response paths có thể không được phân loại như dự kiến nếu exception đã được xử lý trước MVC instrumentation.
- YAML này **không tự tạo** ba meter `app.auth.*`. Chúng chỉ xuất hiện sau khi code chủ động instrument và **đã có ít nhất một quan sát**.

### Bảo mật Actuator là yêu cầu bắt buộc

Mặc định Spring Boot chỉ expose endpoint health qua HTTP; khi bật metrics/prometheus phải **chặn truy cập từ Internet công cộng** bằng network/firewall hoặc security chain chuyên biệt. Nếu ứng dụng định nghĩa `SecurityFilterChain` tùy biến, không mặc định Spring Boot còn tự chặn mọi actuator endpoint.

Không mở `management.endpoints.web.exposure.include: "*"` trên Internet chỉ để Grafana đọc metrics. Giảm metadata nhạy cảm, giới hạn role/binding/management port và giám sát số request đến actuator.

Kiểm tra local sau khi được phép:

```bash
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/metrics/app.auth.manager
curl -s http://localhost:8080/actuator/prometheus
```

Lệnh chỉ minh họa trên localhost hoặc qua kênh quản trị tin cậy; nếu endpoint được bảo vệ, cung cấp credential của hệ thống monitoring **không đưa vào shell history hoặc logs**.

## 6. Micrometer Timer: instrument AuthenticationManager

Mục tiêu là đo chính xác thời gian của `AuthenticationManager.authenticate(...)` và **ghi kết quả cả khi ném exception**. Code sau là một Java class cho ứng dụng Spring Security 6.x, không phải ứng dụng Java độc lập.

File `src/main/java/demo/metrics/TimedAuthenticationManager.java`:

```java
package demo.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;

public final class TimedAuthenticationManager
        implements AuthenticationManager {

    private final AuthenticationManager delegate;
    private final Timer success;
    private final Timer invalidCredentials;
    private final Timer internalError;

    public TimedAuthenticationManager(
            AuthenticationManager delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.success = create(registry, "success");
        this.invalidCredentials = create(registry, "auth_failure");
        this.internalError = create(registry, "server_error");
    }

    private static Timer create(MeterRegistry registry, String result) {
        return Timer.builder("app.auth.manager")
                .description("Time spent in application authentication manager")
                .tag("result", result)
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {

        long start = System.nanoTime();
        Timer target = internalError;

        try {
            Authentication outcome = delegate.authenticate(request);
            if (outcome != null && outcome.isAuthenticated()) {
                target = success;
            } else {
                // Một số AuthenticationManager có thể abstain (return null).
                target = internalError;
            }
            return outcome;
        } catch (AuthenticationException ex) {
            target = invalidCredentials;
            throw ex;
        } finally {
            target.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }
}
```

**Phạm vi đo:** timer bao quanh `authenticate`; gồm lookup và KDF mà provider thực sự thực hiện, nhưng không gồm thời gian trước/sau manager. Kết quả `auth_failure` gộp các `AuthenticationException` (bad credentials, locked, disabled…); nếu cần phân loại thêm, dùng một số **nhãn cố định đã qua allowlist** thay vì exception message.

**Wiring cần chú ý:** phải wrap **manager thực sự được formLogin/HTTP Basic/custom auth filter gọi**. Chỉ khai báo bean rồi đặt cùng tên sẽ không bảo đảm mọi authentication flow đi qua wrapper. Với ứng dụng có nhiều `SecurityFilterChain`, mỗi chain có thể dùng manager khác. Việc tạo wrapper vòng (inject một manager mà chính wrapper là bean manager) gây circular dependency. Thiết kế factory/delegate cụ thể và test integration xác nhận số lần đo đúng.

**Không dùng `Timer.Sample` lưu global:** mỗi request/call phải có một sample riêng hoặc dùng monotonic start time riêng như code trên. Chọn `System.nanoTime()`/MeterRegistry clock để đo elapsed; không dùng `Instant.now()` để tính duration vì đồng hồ wall-clock có thể nhảy.

### Đo đúng cả nhánh ngoại lệ

Lệnh `finally` bảo đảm có sample khi:

- Mật khẩu sai/đăng nhập fail theo `AuthenticationException`.
- Account bị khóa, disabled hoặc expired.
- Delegate ném unexpected runtime error/DB problem.
- Provider trả null khi abstain.

Nếu chỉ record timer sau câu `return`, đa số failure attempts **không có metric**, làm dashboard tưởng hệ thống rất nhanh khi đang bị tấn công hoặc DB lỗi.

### Thử test bằng SimpleMeterRegistry

Đoạn test sau **chỉ chạy khi có JUnit/Mockito và Spring Security**:

```java
@Test
void successShouldIncrementSuccessTimer() {
    var registry = new SimpleMeterRegistry();
    AuthenticationManager fake = request ->
            UsernamePasswordAuthenticationToken.authenticated(
                    "alice", null,
                    List.of(new SimpleGrantedAuthority("ROLE_USER")));
    AuthenticationManager timed =
            new TimedAuthenticationManager(fake, registry);

    Authentication input =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    "alice", "example-test-only");
    Authentication result = timed.authenticate(input);

    assertTrue(result.isAuthenticated());
    assertEquals(1L, registry.get("app.auth.manager")
            .tag("result", "success").timer().count());
    assertEquals(0L, registry.get("app.auth.manager")
            .tag("result", "auth_failure").timer().count());
}
```

Imports bổ sung: `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.springframework.security.core.authority.SimpleGrantedAuthority`, `org.springframework.security.core.Authentication`, `java.util.List` và JUnit 5. Đây là **mảnh test trong project**; không tự chạy với lệnh `java` nếu không có classpath/dependencies.

Trong production có thể dùng Spring Security **observation gốc** thay vì wrapper nếu metric có đủ thông tin; khi cần detail lookup/hash, instrument ở đúng component và tránh đếm trùng.

## 7. Đo UserDetailsService.loadUserByUsername: dữ liệu người dùng nằm ở DB/LDAP

`DaoAuthenticationProvider` thường gọi `UserDetailsService.loadUserByUsername` để lấy `UserDetails` và hash, trừ trường hợp có cache hoặc provider custom. Thời gian method gồm:

```text
lookup duration
 = cache lookup / transformation
 + pool acquisition wait
 + network time DB/LDAP
 + query/LDAP operation
 + row mapping / object construction
 + optional retries
```

Nếu cache hit, method có thể chỉ mất micro/milliseconds. Khi cache miss, thời gian tăng. Vì vậy nên đo **đúng hai mốc khác nhau** khi cần:

1. `app.auth.account.lookup`: wrapper quanh `UserDetailsService.loadUserByUsername`, phản ánh cảm nhận của caller.
2. `app.auth.db.query`: timer/trace ở tầng repository/JdbcTemplate/DataSource instrumentation, phản ánh truy vấn (có thể tách pool wait và execution nếu driver/proxy hỗ trợ).

Ví dụ wrapper:

```java
package demo.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;

public final class TimedUserDetailsService implements UserDetailsService {

    private final UserDetailsService delegate;
    private final Timer lookupTimer;

    public TimedUserDetailsService(
            UserDetailsService delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.lookupTimer = Timer.builder("app.auth.account.lookup")
                .description("Duration of user lookup during authentication")
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {
        long start = System.nanoTime();
        try {
            return delegate.loadUserByUsername(username);
        } finally {
            lookupTimer.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }
}
```

Đây là **một decorator**; phải thay đúng `UserDetailsService` mà provider đang dùng và tránh wiring vòng. Để tách success/failure, có thể dùng 2 timers/tag kết quả **được khởi tạo trước** và chọn trong catch/finally. Không tạo meter tên mới dựa vào raw username. Ví dụ trên đo cả `UsernameNotFoundException`, vì `finally` luôn chạy.

### Tại sao phải quan sát pool?

Spring Boot Actuator có instrumentation `jdbc.connections.*` cho DataSource và `hikaricp.*` cho HikariCP nếu dùng đúng integration. Cần theo dõi:

- `active` connections có gần `max` không?
- `idle` connections có cạn về 0 không?
- `pending/waiting` threads có tăng không?
- `connection acquisition` wait có tăng trong giờ cao điểm không?
- DB CPU, lock waits, network RTT và query execution có tăng không?

**Connection pool metrics không thay thế query profiling.** Pool full có thể là triệu chứng của transaction dài hoặc query chậm, không có nghĩa tăng `maximumPoolSize` luôn giải quyết. Nếu DB đã saturation, mở thêm connections có thể làm chậm hơn.

### Truy vấn account nên thiết kế đúng

Một truy vấn ứng dụng điển hình:

```sql
SELECT user_id, normalized_username, password_hash,
       enabled, account_locked, credentials_expired
FROM app_users
WHERE normalized_username = :username;
```

- Tạo **unique index** trên khóa lookup đúng collation/case-normalization và tenant nếu có.
- Đọc đúng một account; không scan full table, không join các bảng không cần cho authentication.
- Sử dụng prepared statements/bind parameters; không concat raw username vào SQL.
- Tránh query N+1 cho authorities/roles/tenants. Nếu cần loading nhiều quan hệ, đo từng SQL hoặc thiết kế fetch cụ thể.
- Không log `password_hash`/raw password, token, session cookie; khi debug SQL có parameter logging, cần redact sensitive params.
- Nếu account không tồn tại, không tiết lộ điều đó cho attacker qua message, status hoặc timing khác biệt quá lớn.

### Query plan và thời gian thực

- `EXPLAIN (ANALYZE, BUFFERS)` trong PostgreSQL giúp xem index/scan/IO nhưng **thực thi** truy vấn; sử dụng an toàn trong môi trường và với dữ liệu được phép.
- So sánh elapsed ở application với `pg_stat_statements`/DB metrics và pool wait; DB query 3 ms nhưng caller chờ pool 80 ms vẫn tạo lookup 83+ ms.
- Tracing spans giúp tìm account lookup lặp hai lần hoặc call ngoài dự kiến; correlation ID không được chứa raw credentials.
- Với LDAP/AD, latency phụ thuộc directory connection pooling, TLS, DN search, group membership queries, referral chasing, DNS, failover; không đổ lỗi cho SQL DB khi nguồn user không phải DB.

## 8. Đo chi phí PasswordEncoder.matches và encode

Hash password được thiết kế **cố ý chậm**. Spring Security khuyến nghị tune adaptive one-way function theo hệ thống; OWASP khuyên benchmark work factor trên server thật và cân bằng chống brute force với rủi ro DoS. Nên xem tài liệu hiện hành về Argon2id, scrypt, bcrypt, PBKDF2 và yêu cầu compliance.

Cần phân biệt:

- `PasswordEncoder.matches(raw, encoded)`: xác minh password nhập vào (đặc biệt trên login).
- `PasswordEncoder.encode(raw)`: tạo hash mới khi đăng ký, reset hoặc **nâng cấp rehash sau login thành công**.
- `PasswordEncoder.upgradeEncoding(encoded)`: kiểm tra policy hash đã lưu (thường nhẹ), **không tự tạo hash mới**.
- `DelegatingPasswordEncoder` chọn thuật toán theo `{id}` của hash đã lưu; thuật toán/cost có thể khác nhau giữa accounts.

Đo `matches` và `encode` riêng. Nếu gộp chúng thành “hash time”, việc rehash thỉnh thoảng sẽ làm phân phối khác biệt, đặc biệt sau triển khai policy mới.

### PasswordEncoder decorator ví dụ

```java
package demo.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.security.crypto.password.PasswordEncoder;

public final class TimedPasswordEncoder implements PasswordEncoder {

    private final PasswordEncoder delegate;
    private final Timer matchTimer;
    private final Timer encodeTimer;

    public TimedPasswordEncoder(
            PasswordEncoder delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.matchTimer = Timer.builder("app.auth.password.matches")
                .publishPercentileHistogram()
                .register(registry);
        this.encodeTimer = Timer.builder("app.auth.password.encode")
                .publishPercentileHistogram()
                .register(registry);
    }

    @Override
    public String encode(CharSequence rawPassword) {
        long start = System.nanoTime();
        try {
            return delegate.encode(rawPassword);
        } finally {
            encodeTimer.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }

    @Override
    public boolean matches(
            CharSequence rawPassword, String encodedPassword) {
        long start = System.nanoTime();
        try {
            return delegate.matches(rawPassword, encodedPassword);
        } finally {
            matchTimer.record(
                    System.nanoTime() - start, TimeUnit.NANOSECONDS);
        }
    }

    @Override
    public boolean upgradeEncoding(String encodedPassword) {
        return delegate.upgradeEncoding(encodedPassword);
    }
}
```

**Bảo mật instrumentation:** hàm wrapper **không** log `rawPassword`, `encodedPassword`, username hoặc stack trace có sensitive values; metrics chỉ lưu duration/count. Đừng chuyển password/hash vào tag hoặc trace attributes; chúng sẽ đi xa và có retention dài.

**Chi tiết quan trọng:** `PasswordEncoder.matches` trả false vẫn thường tiêu tốn CPU tương đương một phép verify. Nhưng nếu user không tồn tại và provider bỏ qua KDF, response có thể nhanh hơn, làm lộ username enumeration qua timing. Spring Security `DaoAuthenticationProvider` có biện pháp giảm timing differences cho user không tồn tại; nếu tự viết provider hoặc cache logic, phải test negative path thay vì cố tình làm mọi request lỗi nhanh nhất.

### Nên gắn tag nào?

Một bộ tag **ít giá trị biến thiên** có thể gồm:

| Tag | Ví dụ | Lưu ý |
| --- | --- | --- |
| `method` | `password` / `webauthn` / `oidc` | Method cố định, không phải raw factor secret |
| `result` | `success` / `auth_failure` / `server_error` | Đừng dùng exception message |
| `algorithm` | `bcrypt` / `pbkdf2` / `argon2id` | Nhóm ổn định; có thể bỏ nếu không cần |
| `policy_tier` | `legacy` / `current` | Phân nhóm cố định thay vì raw hash |
| `cache` | `hit` / `miss` | Chỉ khi thật sự biết cache state |
| `service` | `identity-api` | Đặt ở resource attributes của telemetry phù hợp |

Không gắn: raw username/email, user ID, IP, token, session ID, SQL có parameters, password string, arbitrary URI, UUID mỗi request, traceId, raw exception message. Một triệu users tạo một triệu time series nếu tag theo user — gây **high cardinality** và có thể lộ thông tin cá nhân.

## 9. Chọn work factor: không đổi bảo mật lấy con số latency đẹp

Một hash chậm là **đặc tính bảo vệ**, không phải bug cần xóa. Nhưng work factor quá cao có thể làm server kiệt CPU/RAM khi nhiều đăng nhập cùng lúc, kể cả attacker cố ý spam.

### Chi phí thực tế phụ thuộc

- CPU architecture, core/thread scheduling, container CPU quota, virtualization và noisy neighbors.
- Algorithm và params: bcrypt cost (xấp xỉ tăng mạnh theo cost), PBKDF2 iterations, scrypt N/r/p, Argon2id memory/time/parallelism.
- Nhiều hash đồng thời; Argon2id tiêu tốn memory theo mỗi hash, rất khác mô hình CPU của bcrypt.
- JVM warmup, JIT, library native/Java implementation, GC, allocator, số lượng request hiện hành.
- Xác thực thành công có thêm rehash/encode, còn user sai password có thể chỉ verify.
- Dùng `DelegatingPasswordEncoder`: legacy/strong hashes lẫn nhau có phân phối latency khác; phải tách theo nhóm.

### Cách benchmark đáng tin

1. Chọn thuật toán và mức security policy trước, theo OWASP/tuân thủ của hệ thống.
2. Trên **hardware/container tương đương production**, đo cold/warmup riêng và đặc biệt throughput khi concurrency tăng.
3. Benchmark `matches` trên các hash đã sinh bằng **salt hợp lệ**, đúng policy, với password test giả.
4. Đo `encode` riêng; login bình thường thường không gọi encode, chỉ gọi khi cần rehash.
5. Thực hiện **nhiều lần đo sau warmup**; dùng JMH cho microbenchmark JVM khi cần độ tin cậy.
6. Đo tải end-to-end với requests đồng thời, pool/CPU/RAM/GC; tránh microbenchmark chạy một thread rồi suy luận toàn hệ thống.
7. Chọn mức bảo mật không dưới policy tối thiểu, đồng thời kiểm soát rate limiting, queue bounded và resource budgets.
8. Document baseline cho từng environment và rebenchmark sau thay đổi CPU/Java/encoder version.

**Không dùng** `MessageDigest SHA-256` nhanh thay cho bcrypt/PBKDF2/scrypt/Argon2 nhằm “giảm độ trễ login”. SHA-256 nhanh một lượt không phải password-hashing algorithm phù hợp chống brute-force offline.

### Ví dụ JMH — snippet, không phải Java SE độc lập

```java
// Cần org.openjdk.jmh:jmh-core và annotation processor đúng phiên bản.
// Đây là JMH benchmark class, không chạy bằng javac/java thuần.
@State(Scope.Thread)
public class BCryptVerificationBenchmark {

    @Param({"10", "12"})
    public int strength;

    private BCryptPasswordEncoder encoder;
    private String storedHash;

    @Setup(Level.Trial)
    public void prepare() {
        encoder = new BCryptPasswordEncoder(strength);
        storedHash = encoder.encode("benchmark-only-password");
    }

    @Benchmark
    public boolean verify() {
        return encoder.matches(
                "benchmark-only-password", storedHash);
    }
}
```

Cần imports `org.openjdk.jmh.annotations.*` và `org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder`. JMH có warmup, measurement, forks/thống kê theo runner; phải xem **cost 10/12 chỉ là tham số benchmark**, không khuyến nghị thay default. Không thử benchmark từ user/password production.

### Ước lượng CPU budget

Một minh họa cách suy nghĩ (không thay benchmark):

```text
Login rate = 20 requests/second
CPU work mỗi password verify ≈ 250 ms CPU
CPU core-equivalent cho riêng verify ≈ 20 * 0.250 = 5 cores

+ DB, TLS, authorization, post-login, GC, queue, OS overhead
+ headroom cho traffic peak / brute-force throttling
```

**Đây là phép tính nếu 250 ms là CPU time per hash**, không phải wall-clock latency khi nhiều requests bị scheduler chờ. Không chuyển trực tiếp wall p95 thành “CPU cores cần” mà không đo CPU time/CPU utilization. Với Argon2id, còn cần ước lượng memory footprint trên **số hash in flight**, tránh OOM.

## 10. Java 17 thuần: phân rã latency với fake monotonic ticker

Ví dụ chạy với JDK 17 **không yêu cầu Spring, DB, Micrometer**. Nó mô phỏng các khoảng thời gian cố định để kiểm tra công thức p50/p95, ranh giới các phase, ghi cả success/failure và chứng minh tại sao cần nhìn cả total lẫn component.

**Đây là mô phỏng, KHÔNG phải kết quả benchmark thật của bcrypt hay DB.** Không dùng các số 120–150 ms làm chuẩn performance thực tế.

Tạo file `AuthLatencyBreakdownDemo.java`:

```java
import java.util.*;
import java.util.concurrent.TimeUnit;

public class AuthLatencyBreakdownDemo {
    record Point(String metric, String outcome, long elapsedMillis) {}

    static final class FakeTicker {
        private long nanos;
        long read() { return nanos; }

        void advanceMillis(long millis) {
            if (millis < 0) {
                throw new IllegalArgumentException("negative duration");
            }
            nanos += TimeUnit.MILLISECONDS.toNanos(millis);
        }
    }

    static final class Recorder {
        private final FakeTicker ticker;
        private final List<Point> points = new ArrayList<>();

        Recorder(FakeTicker ticker) { this.ticker = ticker; }

        void time(String metric, String outcome, Runnable operation) {
            long start = ticker.read();
            try {
                operation.run();
            } finally {
                points.add(new Point(
                        metric, outcome,
                        TimeUnit.NANOSECONDS.toMillis(
                                ticker.read() - start)));
            }
        }

        void recordTotal(String result, long startNanos) {
            points.add(new Point(
                    "auth_total", result,
                    TimeUnit.NANOSECONDS.toMillis(
                            ticker.read() - startNanos)));
        }

        void summarize(String metric, String outcome) {
            List<Long> values = points.stream()
                    .filter(p -> p.metric().equals(metric)
                            && p.outcome().equals(outcome))
                    .map(Point::elapsedMillis)
                    .sorted()
                    .toList();

            if (values.isEmpty()) return;

            int n = values.size();
            long p50 = values.get((int) Math.ceil(0.50 * n) - 1);
            long p95 = values.get((int) Math.ceil(0.95 * n) - 1);

            System.out.println(metric + "/" + outcome
                    + " count=" + n + " p50=" + p50
                    + "ms p95=" + p95 + "ms");
        }
    }

    static void login(
            Recorder recorder, FakeTicker ticker,
            boolean passwordCorrect,
            long lookupMillis, long hashMillis, long successMillis) {

        long start = ticker.read();
        try {
            recorder.time("account_lookup", "all",
                    () -> ticker.advanceMillis(lookupMillis));

            recorder.time("password_verify", "all",
                    () -> ticker.advanceMillis(hashMillis));

            if (passwordCorrect) {
                recorder.time("after_success", "all",
                        () -> ticker.advanceMillis(successMillis));
            }
        } finally {
            recorder.recordTotal(
                    passwordCorrect ? "success" : "failure", start);
        }
    }

    public static void main(String[] args) {
        var ticker = new FakeTicker();
        var recorder = new Recorder(ticker);

        login(recorder, ticker, true,    8, 120, 5);
        login(recorder, ticker, true,   12, 135, 6);
        login(recorder, ticker, false,   9, 115, 0);
        login(recorder, ticker, true,   30, 150, 5);

        recorder.summarize("auth_total", "success");
        recorder.summarize("auth_total", "failure");
        recorder.summarize("account_lookup", "all");
        recorder.summarize("password_verify", "all");
        recorder.summarize("after_success", "all");
    }
}
```

Chạy:

```bash
javac AuthLatencyBreakdownDemo.java
java AuthLatencyBreakdownDemo
```

**Stdout đúng:**

```text
auth_total/success count=3 p50=153ms p95=185ms
auth_total/failure count=1 p50=124ms p95=124ms
account_lookup/all count=4 p50=9ms p95=30ms
password_verify/all count=4 p50=120ms p95=150ms
after_success/all count=3 p50=5ms p95=6ms
```

### Diễn giải chính xác

- Thành công có tổng: 8+120+5=133 ms, 12+135+6=153 ms, 30+150+5=185 ms. Sorted: 133,153,185 → p50=153, p95=185.
- Thất bại có tổng 9+115=124 ms; không chạy after-success. `count=1` khiến p95=124 ms **chưa có ý nghĩa thống kê** để alert.
- Lookup của tất cả requests là 8,12,9,30 ms. Sorted: 8,9,12,30 → p50=9, p95=30.
- Password verify của tất cả requests: 120,135,115,150 ms. Sorted 115,120,135,150 → p50=120, p95=150.
- After-success có 5,6,5 ms → p50=5, p95=6.
- Timers thành phần **nằm lồng trong** tổng; không cộng `count` của chúng thành số login attempts. Mỗi authentication attempt ghi đúng một total sample.
- `FakeTicker` không chờ thực và không tiêu CPU; chỉ tăng giả lập thời gian, nên test chạy deterministic, không cần `Thread.sleep` và không tạo số liệu hiệu năng hệ thống thật.
- `try/finally` ghi metric khi logic phát sinh exception; trong demo chỉ minh họa đường normal và logical wrong-password. Production phải tag `server_error` khi exception thật thay vì tự cho tất cả là `failure`.

**Bài tập tự làm:** thêm 10 lần login có lookup tăng 10→100 ms, giữ verify cố định, rồi đọc p95 và count. Viết assertion xác minh auth_total có đúng số mẫu bằng số attempts. Không thay code demo thành benchmark Spring Security chỉ bằng cách đổi tên lớp.

## 11. Prometheus/Grafana: truy vấn latency và saturation

Giả sử ứng dụng publish Timer `app.auth.manager` và registry Prometheus expose các time series kiểu:

```text
app_auth_manager_seconds_count{result="success"}
app_auth_manager_seconds_sum{result="success"}
app_auth_manager_seconds_bucket{result="success",le="..."}
```

Tên thực tế còn phụ thuộc exporter/version/naming convention; **kiểm tra `/actuator/prometheus` để xác nhận trước khi copy query**.

### QPS/số attempts trong 5 phút

```promql
sum by (result) (
  rate(app_auth_manager_seconds_count[5m])
)
```

### p95 authentication success từ histogram

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(app_auth_manager_seconds_bucket{result="success"}[5m])
  )
)
```

Kết quả là **giây**, không phải mili-giây. Để hiển thị ms, nhân 1000 trong query hoặc đặt unit ở Grafana. Với nhiều service instances, `sum by (le)` gom đúng các bucket của nhóm đã lọc; **không tính trung bình p95 của từng pod** để tạo p95 tổng.

### p99 và phân tách theo result

```promql
histogram_quantile(
  0.99,
  sum by (le, result) (
    rate(app_auth_manager_seconds_bucket[15m])
  )
)
```

Nếu muốn phân theo `method`/`region`, giữ các label có số lượng hữu hạn đã được định nghĩa. Khi traffic ít, giảm độ chi tiết label để tránh mỗi chuỗi chỉ có vài samples.

### Lỗi máy chủ và thất bại xác thực

```promql
sum(rate(app_auth_manager_seconds_count{result="server_error"}[5m]))
/
clamp_min(sum(rate(app_auth_manager_seconds_count[5m])), 0.001)
```

**Đừng coi tất cả `auth_failure` là lỗi hệ thống:** một user nhập sai password và một database outage cần các cảnh báo khác nhau. Brute-force attempts thường làm failure rate tăng trong khi service vẫn vận hành theo security policy; nên có rate-limit/abuse dashboard riêng.

### DB pool saturation và tài nguyên

Kết hợp p95/p99 với:

- CPU usage/saturation/container throttling.
- GC pause time, heap/non-heap, thread count/thread-pool queue.
- Hikari `active`/`idle`/`pending`/`max` và connection acquisition latency.
- DB query execution, lock wait, deadlocks, connection timeout, slow query count.
- Network/LDAP/IdP latency nếu auth qua service bên ngoài.
- Rate limiting/retries/login volume và distribution password policy tiers.

Có thể cần custom dashboards vì series names của Hikari/Spring Boot thay đổi theo exporter; tránh copy tên metric không xuất hiện trong môi trường thật.

## 12. Điều tra bottleneck: một cây quyết định thực dụng

```text
Login p95 tăng?
    |
    +-- http.server.requests tăng,
    |   app.auth.manager KHÔNG tăng
    |      -> proxy/thread queue/CSRF/filter/session/audit/redirect?
    |
    +-- app.auth.manager tăng
           |
           +-- account.lookup tăng
           |       |
           |       +-- Hikari pending/connection wait tăng?
           |       |      -> pool exhaustion / DB load / transaction dài
           |       +-- DB query p95 tăng?
           |       |      -> index, plan, IO, lock, network, N+1
           |       +-- LDAP/IdP call tăng?
           |              -> directory network/pooling/external dependency
           |
           +-- password.matches tăng
           |       |
           |       +-- CPU throttling / saturation?
           |       +-- work factor/encoder mix changed?
           |       +-- GC/memory pressure?
           |       +-- brute-force concurrency surge?
           |
           +-- postlogin/upgrade/encode tăng
                   |
                   +-- rehash rollout tạo spike?
                   +-- session persistence/audit/outbox chậm?
```

### Tình huống A — đổi bcrypt cost

Trước deploy dùng cost cũ, sau deploy cost mới. Nếu `password.matches` latency tăng trong khi account lookup ổn định và CPU tăng, **đó có thể là chi phí bảo mật tăng như dự kiến**, không phải SQL regression. Cần đo capacity và kiểm soát số login đồng thời; không tự rollback về hash yếu hơn chỉ để biểu đồ đẹp.

### Tình huống B — connection pool cạn

`account.lookup` p95 tăng nhưng DB query execution trong DB chỉ vài mili-giây. Khi pool pending tăng mạnh, request có thể mất nhiều thời gian **chờ lấy connection**. Đọc pool stats, thời gian giữ connection, transaction dài và load DB; không tăng pool size vô hạn.

### Tình huống C — user lookup hai lần

Tracing thấy `loadUserByUsername` chạy hai lần mỗi login: có thể do custom provider, user cache miss, post-login reload hoặc event listener. Kiểm tra code path và caching semantics; tránh cache encoded password lâu đến mức policy reset/revoke không có tác dụng.

### Tình huống D — sau deploy bị nhiều invalid credentials

Mục tiêu không phải làm failed login nhanh “bất thường” bằng cách bỏ KDF/lockout checks, vì có thể tạo timing enumeration. Xác định nguồn traffic, rate limiter, bot challenge và CPU abuse, đồng thời giữ thông báo/timing đủ nhất quán và không lộ user existence.

### Tình huống E — chỉ client thấy chậm

`app.auth.manager` 150 ms nhưng browser đo 2 giây. Cần RUM/network waterfall, ingress/proxy queue, DNS/TLS, redirect chain, OIDC hops, browser resources, session store, thứ tự callback. Micrometer server timers không bao phủ toàn bộ đường request từ client.

## 13. Benchmark micro và load test phải đi cùng nhau

**Microbenchmark:** đo một hàm `matches` với giả lập tải thấp, không cho biết behavior khi 100 logins đồng thời hoặc khi pool DB và CPU cùng saturated.

**Load test:** đo toàn flow khi users đồng thời, có DB thật, pool, container quotas, TLS và network tương đương production. Nên chạy:

- Baseline 1→5→20→50 users concurrently, giữ rate có kiểm soát.
- Đủ traffic trong nhiều phút để JIT/GC/pool metrics ổn định.
- Mix các kết quả `success`/`auth_failure` có **tỷ lệ hợp lý**; không tạo lượng brute-force thật trên production.
- Phân tách thuật toán legacy/current, rehash first-login vs subsequent-login.
- Có peak/spike test để đo queue và graceful degradation.
- Giám sát P95/P99 và CPU/memory/DB, không chỉ QPS.
- Thử timeout/retries/rate-limiter behavior và xem hệ thống có bị DoS khi hash concurrency tăng không.
- Không dùng raw production usernames/passwords trong load-test scripts; seed synthetic accounts và secret test riêng.

**Warmup vs benchmark:** `System.nanoTime` đo elapsed tốt khi instrument request, nhưng chạy một vòng lặp nhỏ từ `main` rồi kết luận “bcrypt trung bình 12 ms” là không đáng tin cậy. JMH dùng warmup/forks giúp nghiên cứu mã JVM; load test giúp đánh giá concurrency, p95, queue và end-to-end.

## 14. Thiết kế SLO và cảnh báo có ý nghĩa

Có thể định nghĩa mục tiêu cho service, ví dụ **minh họa**:

| Mục tiêu | Mẫu ví dụ | Yêu cầu bổ sung |
| --- | --- | --- |
| `auth.manager` p95 success | Nhỏ hơn 500 ms | Chỉ so sánh trên hardware, security policy, traffic mix xác định |
| `auth.account.lookup` p95 | Nhỏ hơn 100 ms | Đo cả pool wait; tách cache hit/miss |
| `auth.password.matches` p95 | Trong ngân sách KDF policy | Không hạ cost để “đạt KPI” |
| 5xx/server error rate | Dưới một ngưỡng thấp | Tách khỏi bad credentials |
| Hikari connection wait | Không tăng liên tục trong peak | Kết hợp active/max/pending |
| CPU throttling | Không duy trì gần saturation | Điều chỉnh concurrency/resource budgets |

**SLO không phải định mức bảo mật:** ứng dụng ưu tiên assurance có thể chấp nhận hash verify chậm hơn; ứng dụng nhiều triệu logins/s có kiến trúc khác. Đo có cấu hình, threshold gắn với trải nghiệm và risk assessment.

Alert nên dùng ít nhất:

1. P95/P99 vượt target trong cửa sổ đủ mẫu.
2. Throughput và error-rate thay đổi.
3. CPU throttling/DB pool saturation.
4. So sánh với baseline cùng thời điểm/release.
5. Alert security riêng cho tỷ lệ auth failures/rate limiting và dấu hiệu brute-force.

Không alert dựa duy nhất một sample cực đại của timer khi lưu lượng thấp; `max` trong Micrometer có time-window semantics.

## 15. Instrumentation overhead và sampling

Đo hiệu năng **cũng tiêu tài nguyên**. Một timer với 3 tags cố định rẻ hơn việc tạo span full stack trace, nhưng:

- Mỗi combination metric name + tags là một series family; high-cardinality kéo RAM/CPU/export cost tăng.
- Histogram buckets nhiều sẽ tạo nhiều time series; chỉ publish cho các phase quan trọng, chọn boundaries phù hợp.
- Trace sampling quá cao có thể làm tăng overhead, đặc biệt nếu instrument DB/LDAP mỗi request.
- Log thời gian cho từng password attempt có nguy cơ lộ username/password qua JSON log context; ưu tiên metrics aggregate và trace sampling có sanitization.
- Cần kiểm tra instrumentation có double-record ở decorator và framework observation hay không.
- Timing chính xác nanoseconds có thể làm tăng footprint nếu đưa từng sample vào log; `Timer` tổng hợp tốt hơn.

**Không đo trên biến raw credential rồi xuất dưới dạng metric tag.** Đối với trace, không dùng `authentication.getCredentials().toString()`, không đưa session cookie, authorization header, password hash, OTP hoặc token vào span.

## 16. Kiểm thử instrumentation và tính đúng đắn của dữ liệu

Để instrumentation thực sự đáng tin, cần test không chỉ response mà còn số metric samples:

| Scenario | Điều phải kiểm tra |
| --- | --- |
| Login đúng | `auth.manager{result=success}` +1, lookup +1 nếu thực sự gọi, matches +1 |
| Password sai | `auth_failure` +1, matches +1, không tính vào success |
| User không tồn tại | Lookup +1, provider vẫn bảo vệ timing-enumeration theo policy |
| Account disabled | Auth failure +1; một số provider có thể không gọi matches — **đo thực tế**, không ép |
| DB timeout | `server_error` +1; timer ghi trong finally; không có fake success |
| Hash hiện hành | Verify +1, encode +0 |
| Hash legacy được upgrade | Verify +1, encode +1, repository write đúng policy |
| Cache hit | Không gọi DB lookup nếu cache hiệu lực; metric caller/provider vẫn đo |
| Basic auth mỗi request | Count theo attempts thực, không tưởng là một login session |
| Multiple providers | Không double-count, chỉ manager thực tế được instrument |
| Password reset | Encode timer ghi vào reset flow; không nhầm với login verify |
| Concurrent load | Hist/count vẫn ghi đầy đủ khi 20–100 requests song song |
| Trace sampled | Tags không chứa PII/credentials, trace ID chỉ trong tracing |
| Metrics exporter không kết nối | Auth behavior không fail-open/fail-closed sai ý vì exporter lỗi |
| Actuator unauthorized | Non-admin/Internet không đọc được metrics nhạy cảm |
| No traffic | Không kết luận p99=0 là “nhanh”; label N=0/không có dữ liệu |
| GC pause | p95 manager có thể tăng dù SQL/hash CPU không đổi theo wall time |
| Queue saturation | Server/request p95 tăng trước auth manager; đo đúng ranh giới |

### Test SimpleMeterRegistry cho wrong password

```java
@Test
void invalidCredentialShouldBeCountedAsAuthFailure() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    AuthenticationManager failing = request -> {
        throw new BadCredentialsException("invalid");
    };
    TimedAuthenticationManager wrapped =
            new TimedAuthenticationManager(failing, registry);

    assertThrows(BadCredentialsException.class,
            () -> wrapped.authenticate(
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            "test-user", "wrong")));

    assertEquals(1L, registry.get("app.auth.manager")
            .tag("result", "auth_failure").timer().count());
    assertEquals(0L, registry.get("app.auth.manager")
            .tag("result", "success").timer().count());
}
```

Các imports cần có: `io.micrometer.core.instrument.simple.SimpleMeterRegistry`, `org.springframework.security.authentication.AuthenticationManager`, `org.springframework.security.authentication.BadCredentialsException`, `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`, `org.junit.jupiter.api.Test`, static `org.junit.jupiter.api.Assertions.*`. Đây là mảnh unit test trong project có dependencies cần thiết; không chạy độc lập bằng JDK.

### Integration tests cần triển khai thật

- Khởi tạo Spring Boot app với `@SpringBootTest`, `@AutoConfigureMockMvc` và password user store có test fixtures.
- Gửi form login có `csrf()` qua filter chain thật, không dùng `@WithMockUser` để test password verification (nó bypass provider).
- Kiểm tra actual `MeterRegistry` count/timer; không chỉ assert HTTP 302 vì cả login thành công/thất bại có thể redirect.
- Nếu dùng JDBC, đo DB query timer/cache/pool wait ở test environment; một H2 in-memory DB không đại diện PostgreSQL production.
- Dùng fake `Clock`/registry clock nếu kiểm thử duration deterministic; không `Thread.sleep` để tạo p95 test mong muốn.
- Test rằng app không tạo series theo username/email. Kiểm tra `registry.getMeters()` và tags cho values cố định.
- Với Prometheus, kiểm tra metric export names/buckets/units thực tế và PromQL dashboard trong staging.

## 17. Lỗi triển khai thường gặp

**1. Chỉ xem trung bình.** Mean 100 ms có thể đi kèm p99 2 giây; phải xem histogram và tail.

**2. Xem thời gian HTTP rồi kết luận bcrypt chậm.** HTTP gồm TLS/queue/filter/session/proxy; đo `PasswordEncoder.matches`.

**3. Xem thời gian `AuthenticationManager` rồi kết luận SQL chậm.** Manager gồm lookup, verify và logic khác; cần timer lookup và DB.

**4. Cộng p95 các phase thành p95 total.** Percentile không có tính cộng; đo total trực tiếp.

**5. Chỉ đo success.** Failed auth/DB errors bị bỏ metric làm dashboard thiếu đúng thời điểm tấn công.

**6. Gắn tag username/email/IP/sessionId.** Gây high-cardinality và rò dữ liệu cá nhân; dùng tag finite.

**7. Dùng `Instant.now()` để tính elapsed.** Wall-clock có thể nhảy; dùng monotonic `System.nanoTime()` hoặc registry clock.

**8. Xem ObservationAuthenticationManager là đã có đủ biểu đồ từng SQL.** Observation auth tổng không tách repository/KDF nếu không instrument thêm.

**9. Thay bcrypt bằng SHA-256 cho nhanh.** Hạ bảo mật, không phù hợp password storage; tune work factor và capacity đúng.

**10. Chọn bcrypt/Argon2 params từ laptop dev.** CPU/RAM khác production; benchmark cả độ trễ đơn lẻ và tải đồng thời.

**11. Cho unlimited parallel hashes.** Dễ CPU saturation/Argon2 OOM; rate limit, concurrency budgets và resource quotas.

**12. Tăng Hikari maximumPoolSize khi query chậm.** Có thể tăng tải DB hơn nữa; điều tra lock, plan, pool wait trước.

**13. Cache UserDetails vô thời hạn để “tăng tốc”.** Password reset, account lock và quyền thu hồi có thể không phản ánh kịp; cache invalidation/TTL đúng policy.

**14. Bỏ qua user not found timing.** Kẻ tấn công có thể suy đoán account existence; test invalid user và fake hash behavior.

**15. Đo `encode` và `matches` như một metric.** Không phân biệt login bình thường với rehash/registration/reset.

**16. Quên path rehash của `DaoAuthenticationProvider`.** Sau đổi policy, `encode` tăng và DB writes xuất hiện trên success; phải theo dõi riêng.

**17. Trộn failed credentials và 5xx.** Kết quả tự nhiên của người dùng bị xem như outage, làm alert sai.

**18. Nhiều metrics wrappers cùng ghi một attempt.** Thống kê count bị nhân đôi, p95 không còn đúng; kiểm tra bean wiring/tracing.

**19. Benchmark một lần bằng `System.nanoTime`.** JVM JIT/GC/CPU noise làm số sai; dùng JMH và repeated load tests.

**20. Dùng dữ liệu production thật để benchmark.** Rủi ro lộ credentials và tạo logs; dùng test data.

**21. Expose /actuator/prometheus công khai.** Có thể rò topology, labels, system metrics; chỉ expose qua management network và auth.

**22. Không kiểm tra số samples khi vẽ p99.** Low traffic làm percentile dao động; phải gate theo count và cửa sổ.

**23. Nhầm duration units.** Micrometer timer chấp nhận TimeUnit, Prometheus thường hiển thị seconds; Grafana unit phải đúng.

**24. Tối ưu DB mà bỏ pool acquisition.** Query execution nhanh nhưng request vẫn chờ connection; đo cả pool wait.

**25. Cho logging TRACE vô hạn ở login path.** Tốn CPU/IO, rủi ro credential leakage; dùng sampling/redaction.

**26. Giảm bảo mật để đáp ứng SLO.** Không tắt throttling, account checks hay MFA; phải điều chỉnh cấu trúc, tài nguyên và UX theo threat model.

## 18. Checklist trước khi vận hành production

- [ ] Đã xác định login path thực tế: form login, HTTP Basic, JWT, LDAP hay OIDC?
- [ ] `http.server.requests` và `spring.security.authentications` được hiểu đúng ranh giới, không coi spans là histograms sẵn có?
- [ ] Có timer tách manager, user lookup, password matches, password encode và post-login khi cần?
- [ ] Mỗi timer ghi trong `finally` và phân loại success/auth failure/server error với tags hữu hạn?
- [ ] Dùng `System.nanoTime()`/Micrometer timer, không dùng wall-clock để đo duration?
- [ ] PasswordEncoder đang dùng adaptive hash theo policy; benchmark work factor trên hardware thật?
- [ ] Đã đo single-user và concurrent throughput, CPU throttling, memory cho Argon2?
- [ ] Có phân biệt DB pool wait, query execution, network RTT, cache hit/miss và LDAP?
- [ ] Không có username/email/IP/sessionID/password/hash/token trong metrics hoặc trace tags?
- [ ] Dashboards hiển thị count, throughput, p50/p95/p99, errors, CPU/GC/pool cùng lúc?
- [ ] Prometheus histogram buckets đã được bật đúng meter, query uses `rate`/`sum by(le)` và đúng đơn vị?
- [ ] Nếu app có ít login, đã gate alerts theo sample count/cửa sổ phù hợp?
- [ ] Thay đổi encoder cost, deployment, DB index hay cache được đo trước–sau cùng traffic mix?
- [ ] Actuator/metrics/prometheus được bảo vệ mạng và authentication/authorization?
- [ ] Đã test wiring của manager/provider/PasswordEncoder thực tế chứ không chỉ tồn tại bean?
- [ ] Có test negative paths, timeout DB, password sai, user unknown, legacy rehash và parallel logins?
- [ ] Không hạ password hash strength chỉ để đạt latency target; có rate limiting/capacity planning?
- [ ] Có runbook: phát hiện p95 tăng → phân biệt CPU hash, pool DB, downstream và post-login?

### Tài liệu tham khảo

- Spring Security 6.5 — Observability: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/observability.html
- Spring Security 6.5 — Password Storage / tune work factor: https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html
- Spring Security 6.5 — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security 6.5 API — ObservationAuthenticationManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ObservationAuthenticationManager.html
- Spring Boot 3.5 — Metrics, Spring MVC, JDBC/Hikari: https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- Spring Boot 3.5 — Actuator endpoints & security: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Micrometer — Timers: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — Histograms and Percentiles: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- OWASP — Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- JMH — Official OpenJDK microbenchmark harness: https://github.com/openjdk/jmh

**Kết luận:** đo xác thực đúng là đo **từng ranh giới**, không chỉ HTTP tổng hoặc CPU. Sử dụng metrics/timer có tags an toàn để phân biệt lookup, password verify, rehash và post-login; kết hợp histogram p95/p99, DB pool, CPU/RAM và tracing. Tối ưu năng lực xử lý và truy vấn khi có bằng chứng, **không làm yếu thuật toán hash hoặc bỏ kiểm soát bảo mật để giảm latency**.
