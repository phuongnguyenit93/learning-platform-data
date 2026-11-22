# Hiệu năng băm mật khẩu, truy vấn quyền và dịch vụ danh tính bên ngoài trong Spring Security Servlet

## 1. Bài toán vận hành: đăng nhập và phân quyền vừa an toàn vừa đáp ứng SLO

Ứng dụng **Spring Security Servlet** thường có ba nguồn chi phí đáng kể trong đường đi xác thực/ủy quyền:

1. **Băm/kiểm tra mật khẩu**: các hàm password hashing có chủ đích tốn CPU, đôi khi cả bộ nhớ; đây là đặc tính bảo vệ mật khẩu khi dữ liệu bị lộ, không đơn thuần là một lỗi hiệu năng.
2. **Truy vấn danh tính và quyền**: tải `UserDetails`, authorities, nhóm/role, policy theo đối tượng và tenant có thể gây nhiều truy vấn SQL, N+1 hoặc cache sai độ mới.
3. **Phụ thuộc dịch vụ danh tính bên ngoài**: OIDC/OAuth2 provider, JWKS endpoint, OAuth2 introspection, LDAP hoặc hệ thống tra quyền từ xa thêm độ trễ mạng và rủi ro không sẵn sàng.

Khi người dùng báo “đăng nhập rất chậm”, không nên lập tức hạ work factor của BCrypt hoặc tắt kiểm tra quyền. Cần **xác định đường đi chính xác, đo chi phí từng bước, tối ưu những phần không làm suy yếu bảo mật, và đánh giá tải đồng thời**.

Ví dụ:

- Trang login POST dùng password authentication: có thể cần truy vấn user, xác minh password hash, lưu session, kiểm tra trạng thái account.
- HTTP request mang JWT: thường kiểm token **cục bộ** sau khi có khóa công khai từ JWKS cache; không nhất thiết gọi Identity Provider ở **mỗi request**.
- HTTP request mang opaque access token: có thể phải gọi **introspection** từ xa trên từng lần xác thực nếu không có cơ chế caching phù hợp.
- Request tới endpoint admin: có thể kiểm authority từ token, session hoặc một dịch vụ ACL/role trong database; việc này có thể xảy ra mỗi request hoặc mỗi lời gọi method tùy thiết kế.
- OAuth2 Login authorization-code: một số bước tương tác với IdP diễn ra lúc redirect/callback, nhưng không đồng nghĩa mỗi request sau login đều gọi IdP.

Bài này tập trung vào **đo lường, mô hình tải, cấu hình thực tế, chiến lược cache và vận hành an toàn**, dành cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC Servlet**.

## 2. Trước khi tối ưu: dựng bản đồ độ trễ và ranh giới tin cậy

Một đường đi login bằng mật khẩu có thể như sau:

~~~text
POST /login
  │
  ├── Servlet filter chain / AuthenticationManager
  │     │
  │     ├── UserDetailsService.loadUserByUsername()
  │     │      ├── SELECT user + trạng thái account
  │     │      └── SELECT/group authorities (nếu cần)
  │     │
  │     ├── PasswordEncoder.matches(raw, encoded)
  │     │      └── CPU + memory cost có chủ đích
  │     │
  │     └── Authentication success/failure + SecurityContext
  │
  └── HTTP response, session/cookie khi có
~~~

Một HTTP request mang token có đường đi khác:

~~~text
GET /api/reports
  │
  ├── BearerTokenAuthenticationFilter
  │     │
  │     ├── JWT: JwtDecoder + signature/claims validation
  │     │      └── Key lookup/JWKS thường dùng cache
  │     │
  │     └── opaque token: OAuth2TokenIntrospector
  │            └── Có thể cần HTTP request tới IdP
  │
  ├── authorizeHttpRequests / @PreAuthorize
  │     └── Authority đã có hoặc cần truy vấn ACL/tenant
  │
  └── Controller, business service, database/downstream
~~~

**Không cộng nhầm chi phí của hai luồng.** JWT Resource Server **không** thường chạy `PasswordEncoder.matches()` với password người dùng trên mỗi request. PasswordEncoder thuộc quá trình password authentication hoặc thay đổi mật khẩu; Bearer token authentication là luồng khác. Ngược lại, khi ứng dụng dùng HTTP Basic, mật khẩu có thể được xác thực lại cho từng request tùy cơ chế cache/context, nên đường đi có thể tốn kém hơn session login.

### 2.1. Đặt chỉ số đúng chỗ

| Chỉ số | Ý nghĩa | Tác dụng |
| --- | --- | --- |
| `auth.login.duration` p50/p95/p99 | Tổng thời gian login thành công/thất bại | Phát hiện đuôi độ trễ và user-facing impact |
| `auth.password.verify.duration` | Thời gian `PasswordEncoder.matches()` | So sánh cost/hash implementation/hardware |
| `auth.user.lookup.duration` | Thời gian tra user + roles | Chẩn đoán SQL, kết nối, indexes |
| `auth.authorization.duration` | Thời gian quyết định quyền | Tìm ACL truy vấn lặp và chính sách tốn kém |
| `auth.idp.request.duration` | HTTP tới token/introspection/userinfo/JWKS | Nhìn latency, timeout, dependency health |
| `db.pool.active/pending` | Áp lực connection pool | Phát hiện queueing hoặc pool exhaustion |
| `executor.active/queued`, CPU/GC | Áp lực luồng, bộ nhớ và thời gian chờ | Xem băm mật khẩu có bão hòa tài nguyên không |
| Error rate 401/403/429/5xx | Phân biệt sai credentials, thiếu quyền, rate limit, outage | Không coi mọi 401 là lỗi hiệu năng |
| Token cache/JWKS cache hit/miss | Số lần phải gọi remote key/discovery | Phát hiện cache miss thừa, key rotation |

`p95` là percentile của **một tập request**, không phải trung bình; p95 của các bước **không được cộng đơn giản** để suy ra p95 end-to-end, vì các bước có tương quan và phân phối khác nhau. Cần tracing hoặc đo phân phối toàn chuỗi.

**Không ghi raw password, encoded password, access token, refresh token, Authorization header, session ID, client secret hay thông tin định danh nhạy cảm** vào metrics tags, tracing spans hoặc logs. Metrics nên có nhãn giới hạn số giá trị, ví dụ `outcome=success|failure|timeout` và tên operation đã chuẩn hóa, không dùng username hoặc token làm label.

### 2.2. Latency budget và capacity

Đặt SLO riêng cho login, request đã authenticated và endpoint gọi IdP. Ví dụ một hệ thống **tự chọn** ngưỡng p95 cho login và chia thời gian cho DB, hashing, session, proxy; con số này phải dựa trên sản phẩm và môi trường, không có một giá trị mặc định áp dụng cho mọi ứng dụng Spring Security.

Đặc biệt với password hashing, chỉ số quan trọng là **số phép kiểm tra đồng thời**. Nếu một lần verify chiếm 200 ms CPU trên hạ tầng đang chạy và có 50 login mới/giây, riêng tải này có thể tạo áp lực CPU tương đương khoảng 10 phép verify đồng thời theo mô hình đơn giản. Đây là **ước lượng capacity**, chưa tính cạnh tranh CPU, queueing, garbage collection hay số core thật.

Tối ưu cần so sánh cả **throughput, p99, CPU, memory, tỷ lệ bị rate-limit và tác động bảo mật**, không chỉ một phép băm chạy trên máy lập trình.

## 3. Vì sao password hashing phải chậm có chủ đích?

Mật khẩu là bí mật có entropy do người dùng chọn, không phải khóa ngẫu nhiên mạnh. Khi database password hashes bị lộ, attacker có thể thử rất nhiều mật khẩu ngoại tuyến. **Password hashing chậm, có salt riêng và chi phí tính toán đủ lớn** làm việc đoán mật khẩu tốn tài nguyên hơn.

Những họ thuật toán thường được sử dụng:

| Thuật toán | Đặc tính | Lưu ý vận hành |
| --- | --- | --- |
| Argon2id | Memory-hard, kết hợp chi phí bộ nhớ/thời gian/song song | Phải đo đồng thời CPU và memory, kiểm thư viện/encoder tương thích |
| scrypt | Memory-hard, điều chỉnh cost/độ lớn bộ nhớ | Dễ gây sức ép bộ nhớ nếu nhận quá nhiều login đồng thời |
| bcrypt | Cost điều chỉnh theo số vòng lặp, phổ biến trong Spring | Đo CPU, nhớ giới hạn độ dài mật khẩu đầu vào của implementation |
| PBKDF2 | Nhiều vòng lặp, phổ biến trong các môi trường có yêu cầu thuật toán cụ thể | Cần iteration count phù hợp, không xem một vòng là đủ |
| SHA-256/MD5 trực tiếp | Hash mật mã tổng quát rất nhanh | **Không đủ an toàn để lưu mật khẩu người dùng khi dùng trực tiếp** |

**Không tự chọn** thuật toán/cost chỉ vì một ví dụ trên mạng có con số đẹp. Mức khuyến nghị thay đổi theo thời gian, hardware và yêu cầu tuân thủ. Tham khảo tài liệu password storage hiện hành của Spring Security, OWASP và tiêu chuẩn áp dụng; kiểm benchmark trên môi trường mục tiêu, rồi công bố chính sách nâng cấp có kiểm soát.

### 3.1. Salt, pepper và encoded password

- Mỗi password hash cần **salt ngẫu nhiên độc lập**. Các encoder hiện đại thường đóng gói salt, tham số và output trong encoded string.
- Salt **không phải secret** và có thể lưu cùng encoded password; không dùng một salt cố định cho toàn hệ thống.
- **Pepper** là một bí mật bổ sung do tổ chức quản lý độc lập với DB, nếu dùng. Phải có kế hoạch bảo quản/rotation/recovery; pepper không thay thế thuật toán password hashing chuẩn.
- Không lưu plaintext, reversible encrypted password để tiện xác thực, hoặc hash bằng `SHA-256(password)` trực tiếp.
- Không log hoặc trả encoded password cho frontend. Encoded hash vẫn là dữ liệu bảo mật cần giới hạn truy cập vì nó có thể phục vụ offline attack.

**bcrypt và độ dài đầu vào:** nhiều bcrypt implementation có giới hạn byte đầu vào (thường nêu 72 byte); cách xử lý chuỗi dài, Unicode, version và tiền xử lý phụ thuộc thư viện. Không tự cắt password một cách âm thầm hoặc tự tiền hash không tương thích. Đặt policy nhập password hợp lý, công khai, kiểm thử Unicode và migration của thuật toán được chọn.

### 3.2. CPU/memory pressure là một phần threat model

Work factor lớn giúp chống brute force offline, nhưng lại làm login online tốn CPU. Attacker có thể gửi nhiều request login để gây nghẽn worker threads. Giải pháp không nên là giảm cost xuống mức yếu; cần **rate limiting, admission control, concurrency bounds, protection tại edge, monitoring và capacity planning**.

Cách bảo vệ gồm: giới hạn tốc độ theo tài khoản + IP/risk signal (không chỉ IP), số login tối đa đồng thời, timeout/queue hợp lý, phát hiện credential stuffing, challenge/risk verification khi cần. Tránh lock account quá dễ để attacker gây denial-of-service cho nạn nhân.

**Cân bằng bảo mật và vận hành:** không thêm cache “mật khẩu hợp lệ cho user X” vô thời hạn để bỏ kiểm hash trong mọi request; thiết kế session/token đúng cơ chế Spring Security để không lặp password verification không cần thiết.

## 4. Cấu hình PasswordEncoder trong Spring Boot/Security 6

Trong Spring Security, interface chính là `PasswordEncoder`:

~~~java
public interface PasswordEncoder {
    String encode(CharSequence rawPassword);
    boolean matches(CharSequence rawPassword,
                    String encodedPassword);
    default boolean upgradeEncoding(String encodedPassword) {
        return false;
    }
}
~~~

Đây là chữ ký rút gọn để giải thích contract, không phải hướng dẫn tự viết lại interface framework. `encode()` dùng khi tạo/thay đổi mật khẩu, `matches()` dùng khi kiểm tra. `upgradeEncoding()` cho biết encoded password nên được nâng cấp theo chính sách encoder hiện tại (tùy implementation).

Một cấu hình thường dùng với Spring Boot 3 / Security 6, file `PasswordConfig.java` trong package `com.example.demo`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Configuration
public class PasswordConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
            .createDelegatingPasswordEncoder();
    }
}
~~~

`DelegatingPasswordEncoder` cho phép phân biệt thuật toán theo prefix trong encoded value, ví dụ `{bcrypt}...`; việc encode password **mới** sử dụng thuật toán mặc định của factory ở phiên bản hiện tại, trong khi việc matches có thể nhận các định dạng legacy được cấu hình. **Không tự suy ra** factory mặc định ở mọi phiên bản luôn có cost cố định theo chính sách tổ chức: kiểm tra encoder thực được tạo và benchmark trên deployment mục tiêu.

Nếu tổ chức có chính sách bcrypt cost riêng, ví dụ khai báo:

~~~java
@Bean
PasswordEncoder bcryptEncoder() {
    return new org.springframework.security.crypto.bcrypt
        .BCryptPasswordEncoder(12);
}
~~~

**Chỉ xem đây là ví dụ cấu hình cost 12, không phải khuyến nghị blanket.** Khi thay bean bằng BCryptPasswordEncoder thuần, bạn phải biết các stored password đang có prefix `{bcrypt}` hay chỉ chuỗi bcrypt raw. Một BCryptPasswordEncoder thuần không tự hiểu mọi prefix; việc chuyển đổi encoder phải được kiểm tra với dữ liệu đã lưu và backward compatibility. Với mã Java thật, hãy dùng import class trên **một dòng**, chẳng hạn:

~~~java
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
~~~

Nếu đã sử dụng `DelegatingPasswordEncoder`, có thể cấu hình mapping encoder theo policy để vừa tạo hash mới đúng chuẩn, vừa kiểm được các hash cũ. Không xóa prefix hoặc tự sửa các encoded strings trên DB nếu chưa chứng minh migration an toàn.

### 4.1. Rehash trên lần đăng nhập thành công

Khi tăng work factor hoặc đổi thuật toán, không cần bắt mọi user reset mật khẩu ngay nếu chính sách cho phép **rehash after successful login**:

~~~text
User nhập password
  │
  ├─ Load encoded password cũ từ DB
  ├─ PasswordEncoder.matches(raw, oldEncoded) == true
  │
  ├─ Kiểm tra upgradeEncoding(oldEncoded)
  │     ├─ false -> tiếp tục authentication
  │     └─ true  -> encode(raw) theo policy mới
  │                 -> lưu hash mới an toàn/atomic
  │
  └─ Trả authentication thành công
~~~

Spring Security có cơ chế `UserDetailsPasswordService` kết hợp `DaoAuthenticationProvider` để nâng cấp password khi được cấu hình phù hợp. **Không chỉ bật `upgradeEncoding()` rồi mặc định database đã tự đổi**: phải kiểm tra implementation cập nhật hash và transaction/conditional write, bảo đảm migration không làm ghi đè password đã được đổi đồng thời.

Cần quan sát cả thời gian **encode khi nâng cấp** (thường làm tăng cost ở một số login) và thời gian verify. Không bao giờ đưa raw password vào audit logs, metrics, async queues hoặc retry job.

### 4.2. Chọn work factor bằng benchmark có điều kiện

Quy trình thực tế:

1. Xác định thuật toán, thư viện, phiên bản và loại hash có trong DB hiện tại.
2. Đo `encode()` và `matches()` với dữ liệu thử (không dùng mật khẩu thật) trên CPU/memory của **container/VM production-like**.
3. Đo ở nhiều mức concurrency, gồm peak traffic và spike; ghi p50/p95/p99, CPU throttling và memory pressure.
4. Kiểm số login/giây có thể chịu, queueing và tài nguyên còn lại cho ứng dụng.
5. Thử rate limits/overload handling để attacker không chiếm toàn bộ thread pool.
6. So sánh với mức bảo mật tổ chức yêu cầu; chọn cost đủ mạnh **không làm hệ thống mất tính sẵn sàng**.
7. Lên kế hoạch nâng cấp/migration và đo lại sau thay CPU size, container limits, JVM hoặc thư viện.

**Không benchmark bằng một lần chạy rồi gọi số đó là p95.** JVM warm-up, CPU scheduler, thermal throttling và co-tenancy có thể làm sai kết luận. Nên chạy benchmark tách khỏi thời gian deployment, đồng thời có bài load test end-to-end.

### 4.3. Ví dụ JUnit benchmark an toàn cho môi trường thử nghiệm

Đây là file `PasswordCostTest.java` dưới `src/test/java/com/example/demo/`; nó **không có expected timing cứng**, vì timing phải lấy trực tiếp ở máy chạy:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

class PasswordCostTest {

    @Test
    void measureVerifyLatencyOnCurrentMachine() {
        PasswordEncoder encoder = new BCryptPasswordEncoder(12);
        String encoded = encoder.encode("demo-password-only");

        // Warm-up ngắn; benchmark chính thức cần nhiều mẫu hơn.
        assertTrue(encoder.matches("demo-password-only", encoded));

        List<Long> samples = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            long start = System.nanoTime();
            boolean valid = encoder.matches(
                "demo-password-only", encoded);
            long elapsed = System.nanoTime() - start;

            assertTrue(valid);
            samples.add(elapsed);
        }

        Collections.sort(samples);
        double medianMillis = samples.get(samples.size() / 2)
            / 1_000_000.0;

        System.out.printf(
            "bcrypt_verify_median_ms=%.1f%n", medianMillis);
    }
}
~~~

**Ý nghĩa:** test xác nhận `matches()` thật và in median của bảy mẫu trên **máy hiện tại**. Đây chỉ là smoke measurement có điều kiện, **không phải benchmark khoa học hoặc cơ sở đủ để chọn cost production**. Không đưa ra stdout số mili giây giả định; hãy chạy trên deployment target, có sampling/load test. Chỉ dùng password thử không nhạy cảm và không log encoded password.

## 5. Truy vấn quyền: giảm round-trip mà không làm quyền bị cũ

### 5.1. Authentication DB và authorization DB không luôn nằm ở cùng bước

Với form login + `DaoAuthenticationProvider`, `UserDetailsService.loadUserByUsername()` thường được gọi khi xác thực. Trường `UserDetails.getAuthorities()` có thể chứa role/authority đã tải lúc login. Sau khi login, nếu sử dụng HTTP session thì Spring Security có thể dùng SecurityContext trong phiên thay vì query lại mỗi request.

Ngược lại:

- Request Bearer stateless có thể xác thực JWT và lấy authority từ token ở **mỗi request**.
- `@PreAuthorize` có thể gọi custom `PermissionEvaluator`, chính sách ACL hoặc repository **mỗi khi service method được gọi**.
- Một request có thể gọi danh sách 100 tài nguyên và kiểm quyền từng cái, dẫn tới **N+1 queries** mặc dù đăng nhập chỉ mất một query.
- Một user có role thay đổi khi session đang hoạt động, nhưng context/claims có thể giữ quyền cũ; giảm query đồng thời làm tăng rủi ro **stale authorization**.

Do vậy phải xác định **nguồn sự thật của quyền**: JWT claims, session authorities, local DB, ACL service, policy decision point (PDP), hay kết hợp. Không “cache mọi quyền” một cách mù quáng.

### 5.2. N+1 role lookup và phân trang

Ví dụ dễ gây N+1:

~~~text
SELECT * FROM app_user WHERE username = ?
SELECT authority FROM user_authority WHERE user_id = ?
GET /orders (100 records)
  -> SELECT ... permission ... WHERE order_id = ?   (lặp 100 lần)
~~~

Không phải cứ có nhiều query là sai; vấn đề là query count tăng theo số đối tượng hoặc request tạo ra fan-out không kiểm soát.

Hướng cải thiện:

- Với user profile và authority nhỏ: có thể **join/fetch một lần** ở auth path, tránh truy vấn role riêng cho từng dòng.
- Với quyền đối tượng: dùng **set-based authorization query**, ví dụ truy vấn danh sách order mà user đã được phép xem, thay vì fetch 100 orders rồi kiểm 100 lần.
- Tạo **indexes theo WHERE/JOIN thật**; kiểm `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường PostgreSQL phù hợp, không chỉ dựa vào sự hiện diện của index.
- Giới hạn scope, phân trang và số lượng authorities trả về, tránh tải toàn bộ policy graph của doanh nghiệp vào `Authentication`.
- Truy vấn có tham số; không ghép username/tenant/resource ID vào SQL strings không kiểm soát.

### 5.3. Schema minh họa và index

Ví dụ **SQL theo phong cách PostgreSQL** (mỗi hệ quản trị có thể khác):

~~~sql
CREATE TABLE app_user (
    id BIGINT PRIMARY KEY,
    username VARCHAR(200) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE user_authority (
    user_id BIGINT NOT NULL REFERENCES app_user(id),
    authority VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, authority)
);

-- UNIQUE(username) hỗ trợ truy vấn login theo username.
-- PRIMARY KEY(user_id, authority) hỗ trợ join theo user_id.

SELECT u.id, u.username, u.password_hash,
       u.enabled, a.authority
FROM app_user u
LEFT JOIN user_authority a ON a.user_id = u.id
WHERE u.username = ?
ORDER BY a.authority;
~~~

Ký tự `?` trong câu SQL cuối là **bind parameter của JDBC**, không phải cú pháp chuẩn khi chạy trực tiếp bằng `psql`. DDL chỉ là ví dụ học tập; production cần migration, policies, secrets, backup, tenant model, user status và soft deletion phù hợp.

Với dữ liệu multi-tenant, `username` không nhất thiết unique toàn hệ thống. Nếu tenant là thành phần định danh, cần unique key và query theo **(tenant_id, username)**; tenant ID phải đến từ context được xác thực/kiểm chứng, không tin header client tự tạo để đọc authorities của tenant khác.

### 5.4. Ví dụ UserDetailsService dùng một query join

File `DbUserDetailsService.java` của ứng dụng Boot có `spring-boot-starter-jdbc`, datasource và bảng như mục trên. Đây là **class trong project Spring**, không phải Java standalone. Một query join để đọc user và authorities:

~~~java
package com.example.demo;

import java.util.List;
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public class DbUserDetailsService implements UserDetailsService {

    private final JdbcTemplate jdbc;

    public DbUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record AuthRow(String username, String passwordHash,
                           boolean enabled, String authority) {}

    @Override
    public UserDetails loadUserByUsername(String username) {
        String sql = """
            SELECT u.username, u.password_hash, u.enabled, a.authority
            FROM app_user u
            LEFT JOIN user_authority a ON a.user_id = u.id
            WHERE u.username = ?
            ORDER BY a.authority
            """;

        List<AuthRow> rows = jdbc.query(sql,
            ps -> ps.setString(1, username),
            (rs, row) -> new AuthRow(
                rs.getString("username"),
                rs.getString("password_hash"),
                rs.getBoolean("enabled"),
                rs.getString("authority")));

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("User not found");
        }

        AuthRow first = rows.get(0);
        String[] authorities = rows.stream()
            .map(AuthRow::authority)
            .filter(Objects::nonNull)
            .distinct()
            .toArray(String[]::new);

        return User.withUsername(first.username())
            .password(first.passwordHash())
            .disabled(!first.enabled())
            .authorities(authorities)
            .build();
    }
}
~~~

**Giải thích:**

- `LEFT JOIN` giúp account không có authority vẫn được tìm thấy; quyền truy cập các resource bảo vệ sẽ phụ thuộc policy. Đừng tự cấp `ROLE_USER` nếu account/permission store chưa cấp.
- `JdbcTemplate` sử dụng prepared statement; username không được ghép thẳng vào SQL.
- Tránh gọi thêm N truy vấn role theo số rows. Tuy nhiên một join có thể nhân nhiều dòng theo authorities; **đo dữ liệu thật** để quyết định join một lần hay hai truy vấn có lợi hơn.
- Việc account có `enabled=false` không được bỏ qua chỉ vì SQL trả về role. `DaoAuthenticationProvider` sẽ kiểm các flags của `UserDetails` theo cấu hình bình thường.
- Không ném exception chứa username/SQL secret vào HTTP response. `UsernameNotFoundException` giúp auth flow xử lý thất bại; external message phải tránh dò account.
- Trong môi trường có quyền theo role hierarchy, organization, resource, group hoặc tenant, cần chuẩn hóa mapping và authorization riêng. Dữ liệu authorities được trả từ DB **không đảm bảo** điều kiện kiểm quyền sở hữu tài nguyên.

Dependency JDBC bổ sung khi dùng mẫu trên:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là phần mở rộng cho dự án đã có Spring Security Starter/Web và datasource. Nếu không dùng PostgreSQL, thay driver/DDL phù hợp. Để chạy toàn bộ flow, cần bảng schema/migrations, DB test data và encoder tương thích encoded hashes.

### 5.5. Vì sao index/connection pool quan trọng?

Một query role dùng index tốt vẫn có thể chậm do **connection acquisition**: pool HikariCP cạn, giao dịch kéo dài, lock trên row, network tới DB và queueing. Nên đo riêng:

- Thời gian đợi connection và thời gian SQL thực.
- Query execution plan, số rows đọc/đưa ra, full scan và sorts.
- Query count theo request và per-user (qua metric tổng hợp; không dùng user ID làm high-cardinality tag).
- Database CPU, I/O, locks, deadlocks, connection saturation.
- Transaction boundary: tránh giữ connection trong lúc gọi IdP mạng hoặc làm password hashing CPU kéo dài nếu không cần.

**Không tự tăng pool size vô hạn** để sửa latency: DB có giới hạn connections và concurrency. Cần cân bằng thread pools của Servlet, Hikari, IdP HTTP client và service throughput.

## 6. Cache quyền: nhanh hơn nhưng phải giữ khả năng thu hồi

Một cache của authority/ACL có thể giảm truy vấn đáng kể. Nhưng nếu người quản trị thu hồi quyền `PAYMENT_APPROVE`, việc trả cached allow quá lâu có thể tạo lỗ hổng.

### 6.1. Chiến lược cache theo loại dữ liệu

| Dữ liệu | Có thể cache? | Rủi ro quan trọng |
| --- | --- | --- |
| User profile công khai/ít biến động | Có, TTL phù hợp | Stale display, giới hạn quyền xem |
| UserDetails + authorities trong session | Thường đã có context trong session | Role/lock/revocation không phản ánh ngay |
| Global role definition và role-to-permission map | Có thể nếu versioned | Thay đổi policy không được áp tức thì |
| Permission theo object/tenant | Cẩn trọng, TTL ngắn/invalidation rõ | Cross-tenant leak hoặc quyền đã bị thu hồi |
| JWT claims | Token được ký và kiểm định; không thể sửa claims trong token cũ | Thời gian còn hiệu lực của token tạo cửa sổ stale |
| Opaque token introspection result | Có thể với policy giới hạn TTL | Token bị thu hồi vẫn có thể được chấp nhận trước TTL |
| Password plaintext hoặc kết quả “password matches” | **Không cache kiểu xác thực bỏ kiểm** | Tái sử dụng credential hoặc bypass cơ chế bảo vệ |
| JWT signing public keys/JWKS | Thường có cache theo decoder/HTTP client | Rotation, stale keys, outage và cache-miss storm |

Đối với role/ACL cache, khóa cache cần thể hiện **user ID ổn định + tenant + resource/action hoặc policy version** khi phù hợp. Không cache theo username chung trong multi-tenant. Tránh “positive permission cache” vô hạn, invalidate trên cập nhật role/ACL, account disabled, logout/session revocation hoặc policy rollout nếu yêu cầu.

### 6.2. TTL vs quyền tức thời

Giả sử role được cache **60 giây** theo policy của hệ thống. Nếu bị thu hồi lúc giây thứ 1, thông tin allow cũ có thể sống gần một phút nếu không invalidate. Con số 60 giây chỉ là ví dụ trade-off, **không phải TTL đề xuất**. Với thao tác rủi ro cao, có thể cần:

- Lookup quyền tươi ngay trước business side effect.
- Permission version/role version trong context, kiểm version chống stale.
- Event-driven invalidation khi cập nhật quyền.
- Token TTL ngắn và cơ chế revoke/introspection phù hợp.
- PDP kiểm soát truy cập tập trung có latency budget và fallback fail closed.

**Không dùng “fail open”** khi DB quyền hoặc PDP bị lỗi: nếu không thể xác minh quyền cho thao tác nhạy cảm, hãy từ chối tạm thời và báo lỗi phục vụ vận hành thay vì coi mọi principal là admin. Cần phân biệt thiếu quyền (403) và lỗi dependency (thường là 5xx/503) khi quan sát, không giấu outage như một lỗi password ngẫu nhiên.

### 6.3. Authority của JWT khác permission realtime

Nếu `JwtAuthenticationConverter` đọc scope từ JWT và tạo `SCOPE_reports.read`, Spring Security có thể ra quyết định mà không truy vấn role database. Tuy nhiên token đã phát hành có thể tiếp tục mang scope cũ cho tới khi hết hạn hoặc bị thu hồi theo hệ thống. Một DB role update **không tự làm JWT cũ mất scope**.

Trong môi trường đa tenant, các token có thể chứa claims issuer/organization/tenant, nhưng resource server vẫn cần kiểm **issuer, audience, subject, tenant membership và object-level authorization** theo trust contract. Không tin một `X-Tenant-Id` từ client để chọn nhầm namespace cache quyền.

## 7. Dịch vụ danh tính bên ngoài: phân biệt các call thật sự đi qua mạng

“IdP chậm” không phải một chẩn đoán đầy đủ. Các luồng có chi phí mạng khác nhau:

| Luồng | Khi nào gọi mạng tới IdP? | Cần theo dõi |
| --- | --- | --- |
| OIDC Login authorization code | Redirect/consent/callback, token exchange; UserInfo tùy cấu hình | Browser round trip, token endpoint p95, login success/failure |
| Resource Server JWT | Có thể lấy discovery/JWKS khi startup/cache miss/rotation; kiểm JWT thường local | JWKS hit/miss, signature validation CPU, issuer/audience errors |
| Resource Server opaque token | Introspection per token/request tùy implementation/cache | HTTP latency, active false, 401 upstream, 5xx/timeout |
| OAuth2 Client `client_credentials` | Token endpoint khi cần access token mới | Reuse/expiry, token issuance rate, thundering herd |
| LDAP/remote user directory | Lookup user/password/groups tùy authentication provider | Bind/search latency, pool, paging, TLS |
| External authorization service/PDP | Khi quyết định quyền cần rule ngoài hệ thống | p95/p99, cache TTL, fail-closed, request fan-out |

### 7.1. JWT Resource Server: không gọi IdP trên mọi request

Với JWT, resource server có thể validate **chữ ký cục bộ** sau khi tải public key từ JWKS. Một ví dụ cấu hình `application.yml` (một ứng dụng **JWT mode**):

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/demo
~~~

URI là placeholder cho IdP thử nghiệm. Tùy provider và Spring Security version, decoder có thể lấy metadata, JWKS để kiểm chữ ký. **Không mặc định** `issuer-uri` đã kiểm audience riêng của API; cần cấu hình audience validator nếu hợp đồng đòi `aud=reports-api`.

Tối ưu đúng:

1. Đảm bảo decoder/JWKS caching có hành vi phù hợp, tránh khởi tạo decoder lại trên từng request.
2. Kiểm số JWKS requests và status khi key rotation/cached key không khớp.
3. Cấu hình HTTP connect/read timeouts, cache refresh phù hợp với security contract.
4. Không chấp nhận chữ ký sai hoặc bỏ issuer validation vì IdP tạm mất kết nối.
5. Thử key rotation từ `kid=key-A` sang `kid=key-B`, và tình huống JWKS không sẵn.
6. Không lưu token vào metrics hoặc log; khi trace chỉ ghi loại luồng và error category đã sanitize.

Một JWKS HTTP cache có thể giảm call remote, nhưng **không có nghĩa cache token “không cần verify”**. JWT vẫn phải qua signature và claims validation theo decoder.

### 7.2. Opaque token introspection: network nằm ngay trong đường đi request

Khi dùng opaque token, Spring Security có thể gọi `OAuth2TokenIntrospector` để hỏi token active và lấy claims. Ví dụ cấu hình **thay thế cho JWT mode**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.test/oauth2/introspect
          client-id: resource-api
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

`${...}` là placeholder Spring lấy secret từ cấu hình môi trường sau khi triển khai thật. Không để client secret trong source code, ticket hay log. Tên property `opaquetoken` thuộc cách cấu hình resource server opaque token ở Spring Boot 3; phải dùng đúng version và dependency.

Với mỗi HTTP request Bearer, nếu implementation introspector không cache, response có thể chờ **network RTT + xử lý IdP + TLS/connection pool**. Nếu API nhận vài nghìn request/giây, điều này có thể làm IdP quá tải và tăng p99 của API. Các quyết định bao gồm:

- Khi token có thể chuyển sang JWT được ký và xác thực cục bộ **theo hợp đồng IdP**, đánh giá ưu/nhược về revocation, key rotation và claims.
- Nếu cần opaque token, xem xét **caching introspection có TTL phù hợp với expiry và revocation SLA**; không cache `active=true` dài hơn thời gian cho phép.
- Dùng HTTP connection pooling/timeouts, retry giới hạn cho lỗi transient (nếu thư viện/implementation phù hợp).
- Theo dõi tỷ lệ hit/miss của cache và số introspection requests/giây trên một API node.
- **Không sửa `active=false` thành true** hay “tạm cho qua” khi IdP tắt.

Quan trọng: HTTP 200 của introspection endpoint vẫn có thể chứa `{"active":false}`. Thông tin xác thực phụ thuộc trường `active` và claim hợp lệ, không phụ thuộc chỉ status HTTP.

### 7.3. OAuth2 Client token endpoint: tránh thundering herd

Khi backend dùng `client_credentials`, `OAuth2AuthorizedClientManager` và service/repository phù hợp có thể dùng lại access token còn hạn, xin token mới khi cần. Nếu nhiều instance cùng thấy token hết hạn và đồng loạt request token mới, authorization server chịu **token storm**.

Có thể cân nhắc:

- Dùng authorized-client storage/cache có lifecycle rõ ràng, khóa theo `registrationId + principal` phù hợp.
- Token refresh/reauthorization trước hạn với clock skew phù hợp, nhưng không làm hàng nghìn instance đồng bộ gọi trong cùng mili giây.
- Giới hạn concurrency và retries đối với token endpoint; backoff + jitter.
- Quan sát issuance rate, 429, client authentication failures và latencies.
- Không dùng token của user cho service identity hoặc vice versa chỉ để giảm số lần gọi IdP.

Các giải pháp đồng bộ cluster cần tránh single-point-of-failure và đảm bảo không cache token của tenant/user sai. Client secret phải được rotate theo chính sách.

### 7.4. Identity provider có thể lỗi theo nhiều cách

| Biểu hiện | Có thể là | Chẩn đoán |
| --- | --- | --- |
| Login browser bị delay tại callback | Token endpoint, UserInfo, proxy, TLS hoặc session persistence | Phân tích tracing từng mốc, redirect URI và IdP metrics |
| JWT trước đó chạy, token với `kid` mới trả 401 | Rotation/JWKS cache miss hoặc key không được công bố | Kiểm JWKS và thuật toán với issuer đáng tin |
| Opaque token requests đột nhiên p99 tăng | Introspection service slow, connection pool exhausted | Test upstream latency, HTTP pool/timeout/cache |
| Introspection trả 401 | Credential resource server cho introspection sai/hết hạn | Kiểm client auth/secret, đừng buộc user đổi password |
| Introspection trả `active=false` | Token không còn hiệu lực/không được nhận | Xử lý 401 đúng, không “retry tới khi active” |
| JWT valid nhưng 403 | Scope/roles/audience/authorization policy chưa đạt | Kiểm converter và policy; refresh token không chữa mọi 403 |
| IdP 5xx hoặc DNS timeout | Dependency outage | Circuit breaker, timeout, tách lỗi dependency với lỗi credential |
| JWKS trả 200 nhưng decoder vẫn thất bại | Key set không có `kid` phù hợp, thuật toán/issuer sai | Test rotation/metadata/validation |
| Scope mapping thay đổi sau IdP update | Contract claims khác | Contract tests với IdP test/staging |

## 8. Timeout, retry, circuit breaker và failure mode phải có chính sách

### 8.1. Timeouts theo latency budget

Một request HTTP bên ngoài cần **connection timeout, response/read timeout và tổng deadline** tương ứng SLO. Đặt timeout vô hạn là rủi ro giữ chặt Servlet threads và connection pool; timeout quá thấp tạo nhiều false failures trong lúc IdP hơi chậm.

Tùy triển khai, cấu hình HTTP client qua Spring Security introspector/decoder hoặc connector do tổ chức quản lý; **API builder và cách inject HTTP client thay đổi theo phiên bản**, nên cần kiểm integration test và hợp đồng phiên bản thật. Không lấy một cặp số timeout minh họa rồi coi phù hợp mọi mạng.

Nếu API có ngân sách tổng 1 giây, không thể cho từng dependency retry 3 lần với timeout 1 giây rồi vẫn hứa SLO 1 giây. Phải giới hạn tổng thời gian theo critical path và dừng hợp lý.

### 8.2. Retry chỉ cho lỗi có thể phục hồi

- **Có thể cân nhắc retry giới hạn:** kết nối bị reset, timeout ngắn hạn, upstream 429/503 khi có backoff/jitter và request an toàn để lặp.
- **Không retry vô hạn:** sai client secret (401 của token/introspection endpoint), `invalid_grant`, `active=false`, JWT signature invalid, issuer/audience mismatch.
- **Không đánh đồng HTTP 401 của Resource Server với outage IdP.** Status response cho client và lỗi upstream cần được ghi nhận đúng nguồn.
- Dùng **circuit breaker/bulkhead** để bảo vệ pool của ứng dụng khi provider down; nhưng không biến một breaker open thành “accept user without verification”.

Với yêu cầu nhạy cảm, khi không thể xác minh token/quyền, nguyên tắc là **fail closed**. Có thể trả 503 hoặc lỗi ứng dụng phù hợp để client retry sau; không trả kết quả có dữ liệu riêng chỉ vì IdP tạm offline.

### 8.3. Cache không phải cách tắt validation

Cache public signing keys vẫn phải validate JWT. Cache introspection result phải có TTL và contract revoke. Cache authority phải invalidate quyền khi cập nhật. Cache role theo tenant phải tách key. Cache password **không được biến thành bằng chứng đăng nhập vĩnh viễn**.

Với cache phân tán, kiểm dữ liệu tồn tại sau deploy/restart, TTL drift, eviction, key namespace, serialization/versioning, race conditions và fan-out khi toàn bộ cache cùng hết hạn. Cơ chế cache miss stampede thường xuất hiện chính lúc IdP vừa chậm hoặc rotate key.

## 9. Công thức vận hành: đo trước khi thay một tham số

### 9.1. Hai kiểu latency phổ biến

**Login bằng mật khẩu:**

~~~text
login wall time
  ≈ request parsing
  + wait for DB connection
  + load user/authorities
  + password matches CPU/memory
  + session/audit
  + response/queueing
~~~

**API opaque token cần quyền từ DB:**

~~~text
request wall time
  ≈ bearer parsing
  + introspection HTTP latency
  + permission lookup
  + business operation
  + response/queueing
~~~

Dấu `≈` là mô hình tư duy về **đường tuần tự**, không có nghĩa từng phần đo riêng cộng chính xác ra p95/p99. Một số bước chạy song song, gặp cache hoặc đang chờ pool.

### 9.2. Khi tối ưu DB chỉ có tác dụng nhỏ

Nếu một login mất 170 ms ở password hashing và 15 ms ở truy vấn user, tối ưu query từ 15 ms xuống 5 ms sẽ giảm khoảng 10 ms cho **một đường đi tuần tự minh họa**; không giải quyết CPU saturation do hash. Ngược lại, nếu endpoint resource server không băm password nhưng chạy 30 permission queries, sửa N+1 có thể cải thiện phần lớn latency.

Bài học: **đừng tối ưu hệ thống auth theo chẩn đoán chung “Spring Security chậm”**; đo nơi đợi thật, giảm query count, dùng indexes, caching đúng TTL và bảo vệ hash strength.

### 9.3. Mô hình Little's Law và cạnh tranh tài nguyên

Theo mô hình tải ổn định, số công việc đang xử lý trung bình `L ≈ λ × W`, với `λ` là throughput và `W` là thời gian một request ở trong hệ thống. Nếu 100 phép verify/s, mỗi phép chiếm 0,2 s ở điều kiện giả định, có thể có khoảng 20 phép verify đồng thời trung bình. **Đây không phải phép chọn thread pool size trực tiếp**: chi phí CPU thực, số core, queuing và burst traffic làm thay đổi kết quả.

Khi hashing memory-hard, số phép verify chạy đồng thời còn bị giới hạn bởi **RAM thực tế của container**. Đừng chỉ xem CPU utilization rồi nâng concurrency cho tới khi JVM hoặc kernel OOM.

## 10. Ví dụ Java 17 thuần để hiểu latency budget

File `AuthLatencyModel.java` dưới thư mục bất kỳ, chạy bằng JDK 17+ không cần Spring. Các số là **dữ liệu mô hình giả định**, không phải benchmark hay SLO production.

~~~java
public class AuthLatencyModel {

    record Budget(int hashMs, int dbMs, int idpMs) {
        int passwordLoginMs() {
            return hashMs + dbMs;
        }

        int remoteAuthorizationMs() {
            return dbMs + idpMs;
        }

        Budget fasterDatabase(int newDbMs) {
            return new Budget(hashMs, newDbMs, idpMs);
        }
    }

    public static void main(String[] args) {
        Budget baseline = new Budget(170, 15, 90);
        Budget tuned = baseline.fasterDatabase(5);

        System.out.println(
            "login-before=" + baseline.passwordLoginMs() + "ms");
        System.out.println(
            "login-after=" + tuned.passwordLoginMs() + "ms");
        System.out.println(
            "remote-before="
                + baseline.remoteAuthorizationMs() + "ms");
        System.out.println(
            "remote-after="
                + tuned.remoteAuthorizationMs() + "ms");
        System.out.println(
            "db-saved="
                + (baseline.passwordLoginMs()
                   - tuned.passwordLoginMs()) + "ms");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac AuthLatencyModel.java
java AuthLatencyModel
~~~

Stdout **chính xác**:

~~~text
login-before=185ms
login-after=175ms
remote-before=105ms
remote-after=95ms
db-saved=10ms
~~~

Code chỉ minh họa **phân rã tổng thời gian giả định** và ảnh hưởng khi tối ưu riêng DB. Nó không đo thread scheduling, network latency distribution, p99, cache hit ratio, concurrency, transaction cost hoặc chất lượng password hashing. Không dùng con số trên làm cấu hình timeout hoặc hash cost.

## 11. Instrumentation trong ứng dụng Servlet

Để có telemetry hữu ích, gắn timing tại boundary đáng tin: `UserDetailsService`, phần gọi `PasswordEncoder`, authorization repository/service, introspection HTTP client, JWKS fetch và login endpoint. Nếu dùng Micrometer/Spring Boot Actuator, có thể cấu hình timers/histograms theo cơ chế tương thích phiên bản.

Ví dụ một service wrapper mô tả đo thời gian verify mà **không log password/hash** (class có dependency Micrometer trong project):

~~~java
package com.example.demo;

import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class TimedPasswordVerifier {

    private final PasswordEncoder delegate;
    private final MeterRegistry registry;

    public TimedPasswordVerifier(
            PasswordEncoder delegate, MeterRegistry registry) {
        this.delegate = delegate;
        this.registry = registry;
    }

    public boolean matches(CharSequence raw, String encoded) {
        return registry.timer("auth.password.verify")
            .record(() -> delegate.matches(raw, encoded));
    }
}
~~~

Đây là **wrapper mẫu**; không tự được Spring Security sử dụng chỉ vì có bean. Muốn đo đường đi `DaoAuthenticationProvider`, cần cấu hình tích hợp wrapper đúng chỗ, tránh tạo hai bean `PasswordEncoder` gây ambiguous injection hoặc làm vòng phụ thuộc. Với Boot, Micrometer thường đi cùng Actuator hoặc dependency tương ứng; xác nhận library và bean registry thật trước khi biên dịch.

**Không gắn tag `user=username`, `passwordHash=...` hay `token=...`**. Tránh lưu raw JWT claims làm metric labels. Chỉ xuất số đo tổng hợp, route template, idp registration theo allowlist và outcome/error category đã sanitize. Đo cả **thất bại**, vì mật khẩu sai hoặc token invalid có thể tạo CPU/network load đáng kể.

### 11.1. Mỗi metric trả lời câu hỏi nào?

- Nếu password verify p95 tăng cùng CPU throttling, kiểm container CPU quota, hash algorithm, work factor và login spikes.
- Nếu DB lookup p95 tăng nhưng query execution nhanh, kiểm Hikari acquisition, locks, pool exhaustion, proxy/network.
- Nếu authorization query count tăng theo số DTO trong response, kiểm N+1/ACL per row.
- Nếu JWT API chậm cùng IdP nhưng không có JWKS cache miss, có thể bottleneck **không** nằm ở IdP: kiểm business DB/external services trước.
- Nếu opaque token API p99 tăng cùng introspection p99, đo HTTP connection pool, retry và endpoint health.
- Nếu login user đã authenticated bỗng gọi `PasswordEncoder.matches()` trên mọi GET, xem chính sách Basic authentication, stateless/session và caching thay vì giảm hash cost.
- Nếu lỗi 401 tăng sau IdP rotation, kiểm issuer, audience, JWKS `kid`, clock skew và cấu hình validation; đừng giải quyết bằng cách bỏ xác minh chữ ký.

## 12. Kiểm thử hiệu năng và lỗi theo ba trục

### 12.1. Benchmark hashing theo CPU và tải đồng thời

Test trên môi trường giống production nhất có thể, với:

1. Có account test thật sự được encode theo algorithm/cost đang áp dụng.
2. Đo `encode` và `matches` tách biệt.
3. Dùng workload login thành công và thất bại; không để test tạo credential stuffing trên IdP công cộng.
4. Tăng concurrency có kiểm soát, đo CPU, memory, active threads, pending queue, GC, latency p95/p99.
5. Test burst/rate limiter, user lockout policy, khả năng phục hồi khi tải giảm.
6. Kiểm encoded password di trú: prefix/algorithm/cost cũ vẫn matches, rehash được thực hiện an toàn khi login thành công.
7. Kiểm Unicode, password dài, thuật toán hash khác nhau và không lộ thông tin qua error/timing.

Đừng chạy brute-force giả định số lượng lớn trên hạ tầng bên ngoài không được phép; load test phải có môi trường và phạm vi được phê duyệt.

### 12.2. DB quyền với dữ liệu lớn và multi-tenant

Tạo fixtures có user với nhiều roles, nhiều groups và resource ACL; kiểm:

- Số SQL queries per login/request; không tăng theo số dòng kết quả nếu có thể dùng set-based query.
- Query plan và index usage trên dữ liệu có phân phối thực tế.
- Khi đổi role/disable account, cache đã invalidate và session/token policy áp đúng.
- Khi tenant A và B có cùng username/resource ID, cache keys/policy không gây lộ dữ liệu chéo.
- Khi DB pool hết connection hoặc lock kéo dài, auth flow báo lỗi an toàn, không fail open.
- Với user có 0 authority, app không tự cấp mặc định quyền cao.

### 12.3. Test IdP qua môi trường cô lập

Trong CI/unit integration có thể dùng JWKS HTTP stub, token endpoint test hoặc local introspection stub; để kiểm vendor contract phải bổ sung **IdP staging hoặc container IdP**. Các tình huống:

| Tình huống | Mong đợi |
| --- | --- |
| JWT đúng issuer/audience/scope | Resource Server cho phép khi business policy thỏa |
| JWT wrong signature/expired/other issuer | Từ chối, không truy cập dữ liệu |
| JWKS rotation/cached old key | Cập nhật phù hợp mà không chấp nhận key không đáng tin |
| Introspection `active=true` | Authentication có principal/authority đúng |
| Introspection `active=false` | Từ chối token |
| Introspection 401 do client credentials sai | Báo dependency/config error an toàn; không nhận token |
| IdP timeout/5xx | Hạn chế retry, circuit breaker, không fail open |
| Token cấp với scope ít hơn | 403/authorization denial theo policy |
| Các node đồng thời renew client_credentials | Không tạo token storm/không vượt rate limits |
| Revocation/change role trong IdP | Hệ thống tôn trọng contract về TTL/cache và quyền |

MockMvc tests với `jwt()` hoặc `opaqueToken()` chỉ xác minh authorization **với authentication dựng sẵn**. Để test đường đi thật, gửi Bearer header qua Spring Security filter chain với `JwtDecoder` thực hoặc `OAuth2TokenIntrospector` thực và HTTP stub; sau đó có E2E IdP. Không tuyên bố “đã benchmark IdP” chỉ vì Mockito mock trả trong 1 ms.

### 12.4. Đo đúng dưới tải thực tế

Chạy test theo các giai đoạn:

~~~text
Warm-up JVM, DB pool, JWKS cache
    ↓
Steady state: throughput mục tiêu
    ↓
Burst/spike: login hoặc opaque-token peak
    ↓
Failure injection: IdP timeout, DB pool pressure, rotation
    ↓
Recovery: giảm tải và quan sát service phục hồi
    ↓
Kiểm lại không có quyền bị cấp sai/credential bị log
~~~

Ghi lại JVM/CPU quota, memory limit, thư viện/JDK, loại DB, số instance và mạng. Một kết quả performance không có môi trường chạy hoặc phân phối latency thì khó so sánh sau deploy.

## 13. Sai lầm vận hành thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| Login chậm, CPU luôn cao | Password hashing cost/concurrency, CPU quota hoặc credential stuffing | Benchmark, capacity plan, rate limiting; không tự hạ cost |
| Login chậm, CPU thấp nhưng DB pending tăng | JDBC pool cạn, query lock/transaction kéo dài | Đo acquisition, index, transaction, pool sizing |
| Role queries tăng gấp trăm khi xem danh sách | N+1 trong `PermissionEvaluator` hoặc service ACL | Set-based fetch/check, hạn chế fan-out |
| Người đã bị tước admin vẫn thao tác được | Session authorities/JWT/cache stale | Role version, revocation/invalidation, step-up/fresh-check |
| Một user của tenant A thấy quyền tenant B | Cache key/query thiếu tenant binding | Bind tenant được tin cậy, test cross-tenant |
| JWT API gọi IdP liên tục | Decoder/JWKS cache bị tạo mới hoặc sai key/rotation | Giữ decoder đúng lifecycle, quan sát JWKS requests |
| Opaque API phụ thuộc IdP mỗi request và p99 xấu | Introspection HTTP RTT/cache miss | Pool/timeout, cache TTL có kiểm soát, cân nhắc trust architecture |
| IdP lỗi thì API cho truy cập mọi token | Fail-open fallback nguy hiểm | Fail closed, 503 khi xác thực không thể thực hiện |
| Token endpoint bị 429 sau deploy | Nhiều instance refresh cùng lúc | Token reuse, bound concurrency, jitter/backoff |
| Mất client secret nhưng server báo mọi user sai mật khẩu | Trộn upstream client auth failure với end-user authentication | Phân loại lỗi, alert nội bộ, response an toàn |
| Cache authority rất nhanh nhưng dữ liệu sai | Không có invalidation hoặc TTL không gắn risk | Xác định revocation SLA và fresh checks |
| Tối ưu password matches bằng SHA-256 trực tiếp | Hiểu nhầm slow hash là bottleneck không cần thiết | Giữ password KDF chuẩn, giảm online abuse/query cost |
| Metrics bùng cardinality | Ghi username/JWT/subject vào tags | Label bounded, correlation ID trong logs an toàn |
| p95 local tốt, p99 production xấu | Container throttling, connection queuing, network tail | Load test production-like và phân tán tracing |
| Cấu hình timeout quá lớn | Servlet threads giữ lâu, cascade failure | End-to-end deadline, bounded retries/bulkheads |
| Sau key rotation mọi request fail | JWKS cache TTL/refresh sai, issuer/kid/alg mismatch | Contract tests với IdP, kiểm key rollover |

### Checklist trước khi đưa vào production

- [ ] Đo từng bước trong auth path: `UserDetailsService`, hash verify, authority decision, JWKS/introspection, pool waiting.
- [ ] Hash password bằng KDF chuẩn với salt riêng; work factor dựa trên threat model và benchmark hardware mục tiêu.
- [ ] Có rate limiting, admission control, giới hạn concurrency, bảo vệ trước credential stuffing/DoS.
- [ ] Dùng `DelegatingPasswordEncoder`/migration plan phù hợp, không mất khả năng xác minh password cũ.
- [ ] Chỉ rehash sau successful login và có cập nhật hash an toàn.
- [ ] Query user/authority có indexes thích hợp; đo N+1, DB time và connection acquisition.
- [ ] Quyền theo user/tenant/resource dùng cache key đúng, TTL/invalidation/revocation policy rõ ràng.
- [ ] JWT validation luôn kiểm chữ ký/issuer/expiry và audience theo contract; JWKS được cache nhưng không bỏ crypto validation.
- [ ] Opaque introspection có latency/timeout/cache plan phù hợp, không coi `active=false` là thành công.
- [ ] OAuth2 Client không tạo token storm; có reuse và retry giới hạn.
- [ ] Nếu IdP/PDP/DB unavailable, thao tác cần xác thực/ủy quyền vẫn **fail closed**.
- [ ] Metrics p50/p95/p99, query count, error category, connection pools, CPU/memory được quan sát liên tục.
- [ ] Không log passwords/hashes/raw tokens/session IDs/secrets/PII vào tracing hoặc metrics tags.
- [ ] Test concurrency, role revoke, key rotation, expired JWT, introspection outage, cache stale và multi-tenant boundaries.
- [ ] Có runbook phân biệt authentication failure, authorization denial, network/provider outage và overload.
- [ ] Performance tuning được kiểm lại sau thay đổi Spring Security version, JVM, container resources, database indexes hoặc provider contract.

**Kết luận:** vận hành Spring Security hiệu quả không phải “làm password hash thật nhanh” hoặc “cache tất cả quyền”. Phải giữ **password hashing đủ mạnh**, cắt giảm **truy vấn quyền không cần thiết và N+1**, đồng thời quản lý **độ trễ, cache, timeout, key rotation và khả năng lỗi của IdP** theo ranh giới tin cậy. Đo bằng telemetry và load test đúng đường đi; bảo đảm mọi tối ưu vẫn giữ nguyên authentication validation, authorization và khả năng thu hồi quyền.
