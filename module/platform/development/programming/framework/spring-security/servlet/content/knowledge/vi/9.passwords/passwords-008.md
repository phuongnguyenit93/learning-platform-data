# Di chuyển dữ liệu mật khẩu cũ mà vẫn kiểm soát thuật toán được chấp nhận

> **Phạm vi:** Spring Security trên **Servlet stack**, Java 17+, các ví dụ tích hợp dùng Spring Boot 3 / Spring Security 6.x. Mục tiêu là đọc được dữ liệu password hash cũ **trong một giai đoạn chuyển tiếp có kiểm soát**, xác thực bằng đúng thuật toán đã được phê duyệt, nâng cấp sang cách hash mới **sau khi người dùng nhập đúng mật khẩu**, rồi loại bỏ thuật toán cũ đúng thời hạn. Không áp dụng tư duy “thử mọi encoder đến khi khớp” hoặc chấp nhận hash thiếu nhận dạng mặc định.

## 1. Vấn đề thực tế

Một hệ thống lâu năm có thể tồn tại nhiều thế hệ mật khẩu:

| Dạng lưu trữ | Ví dụ cấu trúc | Vấn đề |
| --- | --- | --- |
| BCrypt cũ không có tiền tố | `$2a$08$...` | Không có metadata thuật toán ở cấp ứng dụng; chi phí work factor cũ có thể thấp. |
| BCrypt cũ đã gắn ID riêng | `{bcrypt-v1}$2a$08$...` | Đã biết chính xác họ thuật toán; cần chuyển tiếp và nâng work factor. |
| BCrypt hiện hành có ID | `{bcrypt}$2a$12$...` | Có thể được chấp nhận trong policy mới. |
| PBKDF2 đời cũ | `{pbkdf2-legacy}...` | Phải biết **chính xác** PRF, salt, iteration, format và độ dài output lịch sử. |
| Không rõ thuật toán, MD5/SHA-1/chuỗi có vẻ plaintext | Dữ liệu không xác minh được nguồn | **Không tự đoán**, không thêm `noop` hoặc mặc định thử thuật toán yếu. |

Các chuỗi có dấu `...` trong bảng chỉ thể hiện **hình dạng**; chúng không phải hash dùng được trong production. Định dạng thực phải được đối chiếu với dữ liệu, code cũ, migration cũ và test vectors đáng tin.

Bốn câu hỏi bắt buộc trả lời trước khi viết migration:

1. **Hash nào đang lưu?** Xác minh thuật toán, phiên bản, tham số, format, tiền tố, pepper nếu có và nơi lưu salt. Không đủ chứng cứ thì phải đưa bản ghi vào quy trình khôi phục/reset.
2. **Phiên bản nào còn được phép xác thực?** Quy định allowlist với chủ sở hữu, mức rủi ro, hạn cuối loại bỏ và phạm vi tài khoản.
3. **Hash mới là gì?** Chọn password hashing algorithm chuyên dụng và work factor đã đo đạc trên hệ thống thực. Ví dụ bài dùng BCrypt với cost 12 để minh họa, không khẳng định 12 là giá trị tối ưu cho mọi môi trường.
4. **Khi nào nâng cấp?** Khi có password thô từ một lần login **đã xác minh thành công**, hoặc khi người dùng thực hiện quy trình đổi/reset password. Không thể nâng cấp thực chất chỉ bằng chuyển chuỗi hash cũ sang tiền tố mới.

## 2. Phân biệt ba thao tác thường bị nhầm

**Gắn nhãn thuật toán (tagging):** đổi `$2a$08$...` thành `{bcrypt-v1}$2a$08$...` nếu đã xác minh từ metadata hoặc source code cũ rằng bản ghi chắc chắn là BCrypt đời cũ. Việc này **không thay đổi sức mạnh bảo vệ** của password; nó chỉ giúp hệ thống chọn đúng verifier.

**Kiểm tra mật khẩu (verification):** người dùng nhập raw password; `PasswordEncoder.matches(raw, stored)` dùng đúng encoder từ allowlist để xác minh. Không giải mã hash vì password hash không phải encryption có thể đảo ngược.

**Hash lại (rehash/upgrade):** sau khi verification thành công, dùng **raw password vừa được nhập** để tạo hash mới với thuật toán/work factor hiện hành, rồi cập nhật DB an toàn. Đây mới là bước làm dữ liệu dần hội tụ về chính sách mới.

~~~text
Stored hash             Password nhập vào
    |                          |
    +------ thuật toán ID -----+
               |
               v
       policy cho phép ID?
          /           \
        không          có
         |             |
         v             v
    từ chối an toàn   PasswordEncoder.matches(...)
                       /             \
                  sai                 đúng
                   |                   |
                   v                   v
              auth thất bại     upgradeEncoding(...)?
                                    /        \
                                  có         không
                                   |           |
                                   v           v
                            encode password    login thành công
                            bằng policy mới
                                   |
                                   v
                            ghi DB an toàn
                                   |
                                   v
                            login thành công
~~~

**Quan trọng:** chỉ bắt đầu từ **stored hash** được hệ thống quản lý. Không nhận một chuỗi `{id}hash` do client gửi rồi tin ID trong đó để lựa chọn chính sách hoặc cho phép quyền. Danh sách thuật toán nằm trong **cấu hình server**, không đến từ request.

## 3. `DelegatingPasswordEncoder` và danh sách thuật toán tường minh

Spring Security cung cấp `DelegatingPasswordEncoder`: một password hash có dạng `{id}encodedPassword`. `id` chọn `PasswordEncoder` tương ứng từ map do server cấu hình; một `idForEncode` xác định thuật toán dùng để **tạo hash mới**.

Với cấu hình ví dụ:

~~~text
{bcrypt}    $2a$12$...     -> encoder cho BCrypt cost 12
{bcrypt-v1} $2a$08$...     -> encoder kiểm chứng BCrypt legacy cost 8
{noop}      secret          -> KHÔNG có trong allowlist
{md5}       ...             -> KHÔNG có trong allowlist
<no-id>     $2a$08$...      -> chưa được phân loại, không chấp nhận mặc định
~~~

Bảng chỉ là minh họa về **routing theo ID**. Hash BCrypt tự lưu cost trong chuỗi nên một `BCryptPasswordEncoder` có thể kiểm chứng hash BCrypt với cost lịch sử; hai ID được dùng ở đây để biểu đạt **chính sách vòng đời**, không phải hai thuật toán mật mã khác nhau.

### Bean chính sách mật khẩu: `PasswordPolicyConfig.java`

~~~java
package com.example.passwordmigration;

import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.crypto.password.DelegatingPasswordEncoder;

@Configuration
public class PasswordPolicyConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        Map<String, PasswordEncoder> allowed = Map.of(
                "bcrypt", new BCryptPasswordEncoder(12),
                "bcrypt-v1", new BCryptPasswordEncoder(8)
        );

        // Chỉ ID bcrypt được dùng khi tạo hash mới.
        // ID bcrypt-v1 được giữ tạm để xác minh bản ghi lịch sử.
        return new DelegatingPasswordEncoder("bcrypt", allowed);
    }
}
~~~

**Tại sao đây là allowlist thật?**

- Chỉ có hai ID `bcrypt` và `bcrypt-v1` được khai báo. Một hash có `{noop}`, `{md5}` hoặc ID bất kỳ không được thêm vào map.
- `idForEncode="bcrypt"` nghĩa là `encode(raw)` tạo một hash **mới** với dạng `{bcrypt}$2...`.
- `bcrypt-v1` được phép **verify**, không bao giờ được chọn làm thuật toán tạo hash mới trong configurer này.
- Không gọi `setDefaultPasswordEncoderForMatches(...)` để tự đoán hash thiếu ID, càng không cung cấp `NoOpPasswordEncoder` làm fallback. Cấu hình thiếu ID/ID không được hỗ trợ phải fail closed. Mặc định `DelegatingPasswordEncoder` có thể ném `IllegalArgumentException` cho ID không ánh xạ; ứng dụng cần kiểm soát quan sát lỗi và phản hồi, không chuyển lỗi đó thành một đường bypass.
- Không gọi `PasswordEncoderFactories.createDelegatingPasswordEncoder()` nếu yêu cầu bảo mật là **thu hẹp tập thuật toán được cho phép**: factory mặc định có thể cấu hình nhiều encoder cho mục đích tương thích hơn policy nghiêm ngặt bạn muốn.

Không nhầm **allowlist ở cấp ID** với bảo đảm mọi tham số nội bộ đều phù hợp. Với một ID đại diện cho nhiều phiên bản PBKDF2 có salt/iteration/PRF khác nhau, phải quyết định **cách phân biệt phiên bản tham số** hoặc ràng buộc verifier riêng. Không tự dùng encoder “mặc định hiện tại” để kiểm chứng dữ liệu PBKDF2 được tạo với tham số đời trước.

## 4. Vòng đời xác thực và nâng cấp tự động khi login thành công

Đối với username/password trên Servlet stack:

~~~text
UsernamePasswordAuthenticationFilter
    -> AuthenticationManager
        -> DaoAuthenticationProvider
            -> UserDetailsService.loadUserByUsername(username)
               -> UserDetails.getPassword() trả "{bcrypt-v1}..."
            -> PasswordEncoder.matches(rawPassword, storedHash)
               -> chỉ chấp nhận ID trong allowlist
            -> kiểm tra trạng thái tài khoản
            -> nếu hợp lệ và upgradeEncoding(storedHash)==true:
                   newHash = PasswordEncoder.encode(rawPassword)
                   UserDetailsPasswordService.updatePassword(user, newHash)
            -> trả Authentication đã xác thực
    -> SecurityContext / success handler / session theo cấu hình
~~~

Đối tượng `UserDetailsService` chỉ **đọc** user và stored hash. `PasswordEncoder` xác minh hash. `UserDetailsPasswordService` cung cấp một điểm **ghi hash mới** được Spring Security dùng khi provider đã xác thực thành công và xác định cần nâng cấp.

Một lần login thất bại **không** được ghi hash mới, không gọi `encode` rồi lưu password của attacker, không “đánh dấu đã migrate”. Hãy nhớ: password hash không có chức năng đảo ngược; muốn rehash phải có raw password hợp lệ do người dùng vừa cung cấp.

### `upgradeEncoding(...)` hoạt động ở đâu?

`PasswordEncoder.upgradeEncoding(encodedPassword)` biểu thị hash hiện tại có cần nâng cấp theo chính sách của encoder hay không. `DelegatingPasswordEncoder` có thể yêu cầu nâng cấp khi ID của hash khác `idForEncode`; với hash đúng ID hiện hành, nó có thể chuyển kiểm tra cho encoder bên trong để xét tham số như BCrypt cost.

Ví dụ với policy ở mục 3:

| Stored hash | Verify bằng | Nâng cấp khi login thành công? |
| --- | --- | --- |
| `{bcrypt-v1}$2a$08$...` | `bcrypt-v1` | Có, do khác ID tạo hash mới `bcrypt`. |
| `{bcrypt}$2a$08$...` | `bcrypt` | Có thể có: `BCryptPasswordEncoder(12).upgradeEncoding(...)` xét cost trong hash. |
| `{bcrypt}$2a$12$...` | `bcrypt` | Thường không cần nâng cấp với policy cost 12. |
| `{noop}rawpassword` | Không có encoder | Không xác thực; xử lý theo policy chặn/reset. |
| `$2a$08$...` không ID | Không có encoder mặc định | Chưa được phép login cho đến khi đã phân loại/gắn nhãn đúng hoặc reset. |

`upgradeEncoding` không tự ghi DB. Muốn cập nhật bền vững phải có `UserDetailsPasswordService` được dùng bởi đúng `DaoAuthenticationProvider` hoặc viết cơ chế tương đương cho authentication provider tự tạo.

## 5. Ví dụ tích hợp Spring Boot với kho tài khoản có sẵn

Ví dụ minh họa một ứng dụng Spring Boot 3, Spring Security 6, Java 17 có bảng tài khoản đơn giản và JDBC. Nó chủ động cấu hình provider để tránh phụ thuộc vào việc ứng dụng tự động chọn bean nào khi có nhiều manager/provider.

**Dependencies:** `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-jdbc`, H2 cho demo/test; `spring-boot-starter-test` và `spring-security-test` cho test. Đây là **các tệp thuộc một dự án Spring Boot** có main class/build file, không phải các chương trình Java SE một file biên dịch chỉ bằng `javac`.

### 5.1. Schema: `src/main/resources/schema.sql`

~~~sql
CREATE TABLE app_account (
    username VARCHAR(100) PRIMARY KEY,
    password_hash VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);
~~~

Một hệ thống production nên dùng migrations được version hóa (Flyway/Liquibase), backup và kiểm tra trước/sau. Nếu có nhiều tenant, khóa truy vấn và ràng buộc duy nhất phải bao gồm tenant đáng tin. Với H2 demo, có thể dùng:

~~~properties
spring.datasource.url=jdbc:h2:mem:migrationdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Đây là cấu hình **chỉ cho học tập/test**; không dùng H2 in-memory để lưu mật khẩu production.

### 5.2. Tra cứu hash từ DB: `DatabaseUserDetailsService.java`

~~~java
package com.example.passwordmigration;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;

@Service
public final class DatabaseUserDetailsService
        implements UserDetailsService {

    private final JdbcTemplate jdbc;

    public DatabaseUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record Account(
            String username, String passwordHash, boolean enabled) {}

    @Override
    public UserDetails loadUserByUsername(String username) {
        List<Account> rows = jdbc.query(
                """
                SELECT username, password_hash, enabled
                FROM app_account
                WHERE username = ?
                """,
                (rs, row) -> new Account(
                        rs.getString("username"),
                        rs.getString("password_hash"),
                        rs.getBoolean("enabled")
                ),
                username
        );

        if (rows.isEmpty()) {
            throw new UsernameNotFoundException("Invalid username or password");
        }

        Account account = rows.get(0);

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities("ROLE_USER")
                .build();
    }
}
~~~

Dấu `?` bind username thành tham số, không ghép SQL từ request. Dòng `.password(account.passwordHash())` trả **stored encoded password** nguyên vẹn (bao gồm `{id}`), **không** trả mật khẩu plaintext. Adapter này không thực hiện `matches(...)`, không tự khẳng định đã xác thực.

`ROLE_USER` được gán cố định chỉ để demo tập trung vào password migration; **production phải lấy quyền thực từ nguồn do server quản lý**, không dùng authority chung khi ứng dụng cần phân quyền nhiều mức. Trạng thái khóa, hết hạn mật khẩu và account cần mở rộng schema/mapper tương ứng.

### 5.3. Ghi hash mới bằng so sánh-đổi: `JdbcPasswordUpgradeService.java`

~~~java
package com.example.passwordmigration;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.stereotype.Service;

@Service
public final class JdbcPasswordUpgradeService
        implements UserDetailsPasswordService {

    private final JdbcTemplate jdbc;

    public JdbcPasswordUpgradeService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails updatePassword(UserDetails user, String newPassword) {

        // Chỉ ghi nếu hash cũ vẫn đúng: bảo vệ khỏi ghi đè
        // một password reset hoặc cập nhật đồng thời.
        int updated = jdbc.update(
                """
                UPDATE app_account
                SET password_hash = ?
                WHERE username = ? AND password_hash = ?
                """,
                newPassword,
                user.getUsername(),
                user.getPassword()
        );

        if (updated != 1) {
            throw new IllegalStateException(
                    "Password changed concurrently; retry authentication");
        }

        // Trả về principal chứa hash mới theo hợp đồng API.
        return User.withUserDetails(user)
                .password(newPassword)
                .build();
    }
}
~~~

Giải thích:

- `UserDetailsPasswordService.updatePassword(...)` được gọi **sau khi xác thực đúng mật khẩu**, nếu provider đánh giá cần upgrade; `newPassword` ở đây là **hash mới đã encode**, không phải raw password.
- Câu lệnh SQL dùng **compare-and-swap (CAS)**: điều kiện `AND password_hash = ?` tránh ghi đè password mới khi một process khác vừa reset/migrate.
- Nếu có hai lần đăng nhập hợp lệ chạy song song trên cùng hash cũ, một lệnh update có thể thành công, lệnh sau có thể nhận `updated=0`. Demo chọn fail closed và yêu cầu thử lại; production có thể re-read và xử lý tranh chấp một cách an toàn, nhưng không được ghi đè password reset hoặc bỏ qua lỗi mà không kiểm chứng.
- Khi database lỗi, đường đi cần thất bại an toàn và báo lỗi vận hành phù hợp, không được giả vờ đã nâng cấp bền vững. Cân nhắc transaction, audit event và giới hạn retry theo kiến trúc.
- Không log `newPassword`, `user.getPassword()` hoặc credentials. Dù là hash, chúng vẫn là dữ liệu nhạy cảm trong vận hành.

### 5.4. Kết nối provider và filter chain: `SecurityConfig.java`

~~~java
package com.example.passwordmigration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetailsPasswordService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    AuthenticationProvider accountProvider(
            UserDetailsService users,
            PasswordEncoder passwordEncoder,
            UserDetailsPasswordService passwordUpdates) {

        // Spring Security 6.x: constructor rỗng + setter tương thích.
        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(passwordEncoder);
        provider.setUserDetailsPasswordService(passwordUpdates);
        return provider;
    }

    @Bean
    SecurityFilterChain webChain(
            HttpSecurity http,
            AuthenticationProvider accountProvider) throws Exception {

        http
            .authenticationProvider(accountProvider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ví dụ chủ động khai báo `DaoAuthenticationProvider` để thấy rõ ba phụ thuộc: `UserDetailsService`, `PasswordEncoder` và `UserDetailsPasswordService`. Cách tạo provider bằng no-arg constructor và setter phù hợp các bản Spring Security 6.x, nhưng một số API đã deprecate ở các bản 6.x mới; khi nâng cấp lớn, dùng constructor/API tương đương mà phiên bản mục tiêu hỗ trợ. Không thêm cùng provider nhiều lần vào nhiều manager mà không nắm rõ mô hình chain.

Một controller `/me` đơn giản để kiểm tra request sau đăng nhập:

~~~java
package com.example.passwordmigration;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UserController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Authentication authentication) {
        return authentication.getName();
    }
}
~~~

Với form login stateful, `POST /login` cần CSRF token hợp lệ nếu bật CSRF; các filter bảo mật chuẩn xử lý form login, session fixation và lưu `SecurityContext` theo cấu hình. Không tắt CSRF chỉ để kiểm tra migration.

## 6. Dữ liệu cũ chưa có `{id}`: chuyển tiếp như thế nào?

Có hai trường hợp khác nhau:

**A. Dữ liệu được chứng minh rõ là BCrypt cũ nhưng thiếu tiền tố.** Nếu có bằng chứng từ source code cũ, schema, migration history, hoặc test vectors, một job quản trị có thể bổ sung `{bcrypt-v1}` vào phía trước hash **mà không cần mật khẩu gốc**. Đây chỉ là **thao tác gắn nhãn**, không tăng độ mạnh hash. Sau đó, login thành công sẽ xác minh bằng legacy BCrypt và tạo hash mới `{bcrypt}...`.

**B. Dữ liệu không xác định được thuật toán hoặc có dấu hiệu chứa plaintext/MD5 không được policy phê duyệt.** Không thử tuần tự nhiều thuật toán “cho chắc”; không bật `noop` hoặc fallback global. Đưa tài khoản vào luồng reset/recovery đã xác minh danh tính hoặc xử lý theo quy trình rủi ro được phê duyệt.

Ví dụ thao tác SQL cập nhật **một bản ghi đã được phân loại từ trước**, dùng ứng dụng migration bind tham số:

~~~sql
UPDATE app_account
SET password_hash = ?
WHERE username = ? AND password_hash = ?;
~~~

Các giá trị bind tương ứng: hash có prefix mới, username, **giá trị hash cũ chính xác**. Dùng điều kiện hash cũ để tránh ghi đè nếu người dùng đã đổi password trong lúc migration. Không chạy câu lệnh bulk kiểu “mọi chuỗi không có `{` đều là BCrypt” khi chưa có bằng chứng.

### Tiêu chí kiểm tra trước khi gắn prefix

- Dữ liệu bắt nguồn từ đúng hệ thống cũ đã được xác minh.
- Biết rõ thuật toán và format từng nhóm; đối với BCrypt, xác nhận cấu trúc hash, version marker và cost thuộc phạm vi hợp lệ.
- Có kế hoạch thống kê **số lượng bản ghi theo nhóm** nhưng log không chứa hash hoặc password.
- Có backup và quy trình rollback được kiểm thử; giữ backup theo chính sách bảo vệ dữ liệu nhạy cảm.
- Chỉ gắn ID nằm trong allowlist được phê duyệt; **không** biến ID không rõ thành `{bcrypt}` để qua bước kiểm tra.
- Có batch size phù hợp, đo lỗi và phát hiện cập nhật đồng thời.

Với **PBKDF2 cũ**, chỉ gọi tên thuật toán là chưa đủ. Các triển khai có thể khác salt length, iteration count, PRF, encoding hex/base64 hoặc pepper. Nếu không biết chắc tham số và lưu trữ salt, không thể xây verifier đúng. Khi xác định được, có thể viết một encoder legacy riêng với **tham số cố định** và đăng ký dưới ID riêng như `pbkdf2-v1`; không dùng mặc định PBKDF2 hiện tại để đoán.

## 7. Ví dụ độc lập Java 17: kiểm tra allowlist trước khi gọi verifier

Thí nghiệm dưới đây minh họa **chính sách chọn ID**. Nó **không hash hoặc xác thực password**, không thay thế Spring Security. Mục đích là hiểu rằng hệ thống chỉ xét ID đã được server phê duyệt.

Tạo tệp `PasswordHashPolicyDemo.java`:

~~~java
import java.util.Set;

public final class PasswordHashPolicyDemo {
    private static final Set<String> ALLOWED =
            Set.of("bcrypt", "bcrypt-v1");

    static String policyDecision(String storedHash) {
        if (storedHash == null || !storedHash.startsWith("{")) {
            return "REJECT: untagged";
        }

        int close = storedHash.indexOf('}');
        if (close <= 1 || close == storedHash.length() - 1) {
            return "REJECT: malformed";
        }

        String id = storedHash.substring(1, close);
        if (!ALLOWED.contains(id)) {
            return "REJECT: id=" + id;
        }
        if (id.equals("bcrypt-v1")) {
            return "ALLOW legacy: verify, then upgrade on success";
        }
        return "ALLOW current: verify with current encoder";
    }

    public static void main(String[] args) {
        System.out.println(policyDecision("{bcrypt}example-hash"));
        System.out.println(policyDecision("{bcrypt-v1}example-hash"));
        System.out.println(policyDecision("{noop}plain"));
        System.out.println(policyDecision("$2a$08$example"));
        System.out.println(policyDecision("{bcrypt}"));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac PasswordHashPolicyDemo.java
java PasswordHashPolicyDemo
~~~

Stdout **chính xác**:

~~~text
ALLOW current: verify with current encoder
ALLOW legacy: verify, then upgrade on success
REJECT: id=noop
REJECT: untagged
REJECT: malformed
~~~

Các chuỗi `example-hash` chỉ là placeholder về **dữ liệu đầu vào của phép kiểm tra ID**, không phải password hash hợp lệ; chương trình cố tình **không gọi `matches`**. Trên hệ thống thật, pass qua bước allowlist **không đủ**: còn phải kiểm tra cú pháp hash, policy tham số và xác minh password bằng encoder phù hợp. Khi không rõ định dạng, ưu tiên từ chối rồi thực hiện recovery thay vì đoán.

## 8. Kiểm thử tích hợp: đúng mật khẩu mới được rehash

Tạo `src/test/java/com/example/passwordmigration/PasswordMigrationIntegrationTest.java` trong dự án Spring Boot đã có main class, các bean và H2 như trên:

~~~java
package com.example.passwordmigration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.unauthenticated;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordMigrationIntegrationTest {

    @Autowired JdbcTemplate jdbc;
    @Autowired MockMvc mvc;
    @Autowired PasswordEncoder encoder;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM app_account");
    }

    private void insert(String username, String hash) {
        jdbc.update(
            "INSERT INTO app_account(username, password_hash, enabled) VALUES (?, ?, ?)",
            username, hash, true
        );
    }

    private String hashFor(String username) {
        return jdbc.queryForObject(
            "SELECT password_hash FROM app_account WHERE username = ?",
            String.class, username
        );
    }

    @Test
    void correctPasswordUpgradesLegacyHash() throws Exception {
        String legacy = "{bcrypt-v1}"
                + new BCryptPasswordEncoder(8).encode("test-only");
        insert("alice", legacy);

        mvc.perform(formLogin().user("alice").password("test-only"))
            .andExpect(authenticated().withUsername("alice"));

        String upgraded = hashFor("alice");
        assertTrue(upgraded.startsWith("{bcrypt}"));
        assertTrue(encoder.matches("test-only", upgraded));
    }

    @Test
    void wrongPasswordDoesNotChangeStoredHash() throws Exception {
        String legacy = "{bcrypt-v1}"
                + new BCryptPasswordEncoder(8).encode("test-only");
        insert("bob", legacy);

        mvc.perform(formLogin().user("bob").password("incorrect"))
            .andExpect(unauthenticated());

        assertEquals(legacy, hashFor("bob"));
    }

    @Test
    void unsupportedAlgorithmIsNotSilentlyAccepted() {
        assertThrows(IllegalArgumentException.class,
                () -> encoder.matches("hello", "{noop}hello"));
    }
}
~~~

Spring Security Test cung cấp `formLogin()` request builder với cách xử lý CSRF phù hợp với flow mặc định. Các test đặt account vào H2 rồi thực sự gọi authentication filter/provider và truy vấn DB để kiểm chứng **hash thay đổi hoặc giữ nguyên**.

**Điều test xác nhận:**

1. Login đúng bằng hash có ID cũ ⇒ verifier legacy được dùng ⇒ `upgradeEncoding` đánh dấu cần nâng ⇒ hash mới bắt đầu bằng `{bcrypt}`, và `matches` của policy mới chấp nhận mật khẩu đúng.
2. Login sai ⇒ không rehash, cột `password_hash` giữ nguyên.
3. ID `noop` không nằm trong map ⇒ encoder không âm thầm chấp nhận plaintext. Kiểu exception cụ thể của library phải được kiểm tra với phiên bản thực tế; test ví dụ minh họa hành vi mặc định của `DelegatingPasswordEncoder` không có default encoder.

Chạy trong dự án có Maven Wrapper:

~~~bash
./mvnw test
~~~

Các đoạn Spring ở mục 5–8 cần classpath Spring Boot và file build; chúng không chạy độc lập bằng `javac`. Output build phụ thuộc môi trường nên không khẳng định một stdout giả định. Ứng dụng thực tế còn phải test những cơ chế authentication khác (HTTP Basic, remember-me, custom provider, nhiều security chain) nếu chúng cùng dùng kho password.

### Bộ test cần thêm trước khi rollout

| Tình huống | Kết quả cần đạt |
| --- | --- |
| `{bcrypt-v1}` và raw password đúng | Đăng nhập được; hash được rehash sang ID hiện hành bằng password đúng. |
| `{bcrypt-v1}` và password sai | Từ chối; **không** cập nhật DB. |
| `{bcrypt}` nhưng cost thấp hơn chính sách mới | Nếu `upgradeEncoding` yêu cầu, nâng cost sau login đúng. |
| `{bcrypt}` đúng tham số hiện hành | Đăng nhập được; không ghi lại hash mỗi request vô ích. |
| `{noop}`, `{md5}`, ID lạ hoặc hash thiếu ID | Không có fallback, không login thành công; kích hoạt đường xử lý lỗi/recovery thích hợp. |
| Hash không hợp lệ dù ID nằm trong allowlist | Verifier không chấp nhận; không cấp `Authentication`. |
| Tài khoản bị disable/locked | Không xác thực dù password đúng; không rehash để “mở khóa”. |
| Hai login đồng thời hoặc admin reset password cùng lúc | Không overwrite password mới; CAS/transaction xử lý xung đột an toàn. |
| DB bị lỗi khi updatePassword | Không tuyên bố đã migrate; có giám sát và đường lỗi an toàn. |
| Form login thiếu CSRF token | Không đi đến xác thực thành công trong ứng dụng bật CSRF đúng policy. |
| Password cũ không xuất hiện trong login hàng tháng | Được xử lý qua kế hoạch reset/sunset, không giữ legacy verifier vô thời hạn. |

## 9. Tại sao không nên “thử hết thuật toán đến khi khớp”?

Một cách làm sai thường thấy:

~~~text
for (encoder in allEncoders) {
    if (encoder.matches(raw, stored)) {
        return authenticated;
    }
}
~~~

Đây là **phản ví dụ**, không phải thiết kế nên triển khai. Vấn đề:

- Dữ liệu sai/không rõ nguồn có thể được một encoder quá yếu chấp nhận ngoài ý muốn.
- Một chuỗi có dạng “plaintext” có thể khớp `NoOpPasswordEncoder`; việc bật noop làm tăng nguy cơ bypass.
- Hệ thống không biết chính xác bản ghi đã được xác minh bởi chính sách nào để audit và loại bỏ.
- Độ phức tạp và thời gian phản hồi khác nhau có thể gây vấn đề vận hành, side channel hoặc DoS.
- Khi thay thuật toán, thử nhiều đường không phải giải pháp cho missing metadata; nó giấu lỗi dữ liệu và làm chi phí migration tăng dần.

**Thay thế:** mỗi bản ghi phải được phân loại đáng tin bằng ID/metadata; chỉ map tới encoder đã phê duyệt. Nếu thiếu thông tin để chọn verifier duy nhất, đưa bản ghi vào quy trình reset thay vì suy đoán.

**Đừng coi hash prefix là bằng chứng tự thân:** tiền tố `{bcrypt}` chỉ là metadata định tuyến verifier, không tự xác thực việc account có thuộc đúng user hay đã dùng cost hợp lệ. Cần kiểm soát integrity của database, truy vấn user theo danh tính tin cậy và việc thay đổi hash qua các API có phân quyền.

## 10. Migration theo giai đoạn trong production

### Giai đoạn 0 — Khảo sát và phân loại

- Thống kê số bản ghi theo nguồn/định dạng/ID **không xuất hash hoặc password** vào dashboard/log.
- Xác minh code lưu password trước đây và test vectors để biết từng thuật toán, pepper, encoding, tham số.
- Kiểm tra password reset, thay đổi tài khoản, SSO, API, remember-me, cache, session và các client cũ.
- Chọn thuật toán hiện hành và work factor sau benchmark trên hạ tầng thực; cân bằng chi phí chống brute-force với độ trễ/CPU của login.
- Lập danh sách ID được chấp nhận tạm thời và **ngày sunset**. Phê duyệt ngoại lệ kỹ thuật nếu legacy algorithm quá yếu; ưu tiên forced reset khi không đủ an toàn.

### Giai đoạn 1 — Chuẩn hóa metadata đã xác minh

- Backup theo quy trình bảo vệ bí mật, có khả năng khôi phục.
- Đối với nhóm legacy đã chứng minh rõ format, gắn ID định tuyến `{legacy-id}` với compare-and-swap; có thể xử lý theo batch có checkpoint.
- Những bản ghi chưa phân loại rõ phải nằm trong trạng thái **không thể xác thực bằng fallback** và có recovery/reset.
- Không chuyển `{bcrypt-v1}hash` thành `{bcrypt}hash` chỉ để thống kê hoàn tất; nếu cost/thuật toán chưa đổi thì **chưa rehash**.

### Giai đoạn 2 — Đọc cả cũ và mới theo policy

- Deploy allowlist `DelegatingPasswordEncoder` **hẹp**, `idForEncode` chỉ trỏ thuật toán hiện hành.
- Kiểm tra provider dùng đúng encoder và `UserDetailsPasswordService`; nếu có nhiều `AuthenticationProvider` phải review chúng riêng.
- Nhánh lỗi unknown ID phải an toàn, không lộ username tồn tại/hash và không âm thầm cho phép `noop`.
- Deploy metrics: số lần verify legacy, nâng cấp thành công/thất bại, số tài khoản còn cũ, độ trễ và CPU login. Không ghi secrets.
- Hỗ trợ rollback ứng dụng có kiểm soát nhưng tuyệt đối không rollback password hash mới thành thuật toán yếu.

### Giai đoạn 3 — Rehash-on-login / reset

- User có password hợp lệ và hash legacy ⇒ verify cũ ⇒ hash mới ⇒ CAS update.
- Khi user **đổi/reset password**, luôn encode bằng policy mới; các quy trình này không được viết lại hash cũ.
- Trường hợp user không đăng nhập nhiều tháng sẽ không tự nâng; gửi yêu cầu reset hợp lý hoặc đặt bước nâng cấp lúc họ quay lại, tùy hạn sunset.
- Nếu legacy algorithm yếu đến mức không còn chấp nhận, **không đợi login vô hạn**; áp dụng reset bắt buộc qua kênh xác minh danh tính.

### Giai đoạn 4 — Ngừng chấp nhận cũ

- Xác nhận số tài khoản legacy còn lại, chính sách xử lý dormant users và coverage các client authentication.
- Bỏ ID cũ khỏi allowlist sau thời hạn được phê duyệt; test lại unknown ID/legacy ID.
- Giữ mọi password mới ở scheme mới; xóa code migration khi đã hoàn thành.
- Cập nhật runbook, cảnh báo, audit và cơ chế khôi phục tài khoản. Không giữ weak verifier vĩnh viễn vì “còn vài user cũ”.

**Tiêu chí “migration xong”** không phải chỉ vì column đã có prefix. Hoàn thành nghĩa là user đủ điều kiện đã có hash hiện hành, các tài khoản chưa nâng đã qua recovery/reset hoặc được vô hiệu phù hợp, và verifier cũ đã bị gỡ theo chính sách.

## 11. Rủi ro và tình huống khó

### Thiếu thuật toán ID

Nếu `DelegatingPasswordEncoder` gặp hash trần thiếu `{id}` mà không có default, nó không thể chọn encoder đáng tin; hành vi mặc định có thể ném exception. Đây là tín hiệu dữ liệu chưa migration. Đừng “khắc phục” bằng `setDefaultPasswordEncoderForMatches(NoOpPasswordEncoder...)` hoặc generic fallback có thể nhận mọi chuỗi.

Nếu cần hỗ trợ ngắn hạn cho một tập hash bare BCrypt đã được **định danh chắc chắn**, nên dùng job tag dữ liệu trước hoặc cơ chế truy vấn ID/format tường minh từ metadata đáng tin; không nhận biết bằng việc thử hàng loạt encoder.

### Legacy MD5/SHA-1/plaintext

Các định dạng này không đáp ứng yêu cầu password storage hiện đại. Nếu hệ thống cũ thực sự có chúng, nên ưu tiên **reset password được xác minh danh tính**; nếu có ngoại lệ chuyển tiếp, phải là quyết định bảo mật có phê duyệt, phạm vi hẹp, giới hạn thời gian và biện pháp giảm thiểu. Không đưa một encoder yếu vào default allowlist toàn hệ thống chỉ để tránh hỗ trợ khách hàng.

### Thay đổi thuật toán và tham số

Đổi BCrypt cost, chuyển BCrypt sang Argon2id, hoặc nâng PBKDF2 iterations đều là migration **hash mới**, cần raw password khi rehash. Đặc biệt với PBKDF2, cùng tên thuật toán nhưng khác tham số/format là những scheme khác nhau về mặt verifier.

Không chọn thuật toán chỉ vì tên nghe mới hơn; hãy xem thư viện được duy trì, môi trường (memory/CPU), tiêu chuẩn bảo mật và giới hạn hệ thống. Nên có quy trình benchmark và đo độ trễ authentication thực tế.

### Pepper, HSM và định dạng bí mật lịch sử

Nếu hash cũ được tạo từ `pepper + password` hoặc một KDF sử dụng secret ngoài DB, phải biết chính xác cách kết hợp byte/encoding và vẫn có secret để verify. Mất pepper có thể khiến không thể xác minh password cũ; trong trường hợp đó, cần quy trình reset, không tự giả định encoder hiện hành kiểm chứng được.

Pepper/keys cần được quản lý qua secret manager/HSM phù hợp, không ghi vào source code, DB dump hoặc logs. Việc rotation có thể cần hỗ trợ song song key ID và chuyển tiếp có thời hạn; đó là một chính sách mật mã riêng bên cạnh password-hash algorithm ID.

### Race condition khi đổi password

Bài demo dùng câu lệnh `UPDATE ... WHERE password_hash = oldHash`. Trường hợp quản trị viên reset trong lúc login:

~~~text
T1: đọc hash A -> xác minh password đúng với A
T2: reset password -> ghi hash B
T1: thử update A -> hash C với điều kiện stored=A
Kết quả: 0 bản ghi cập nhật; B vẫn còn, không bị ghi đè
~~~

Đây là hành vi **đúng để bảo vệ reset**. T1 có thể cần retry xác thực theo thiết kế bảo mật, nhưng không được tự coi một user đã reset mật khẩu vẫn có phiên mới hợp lệ. Nếu dùng cache UserDetails hoặc event-driven cập nhật, phải giải quyết tính nhất quán tương đương.

### Nhiều instance và availability

Một rollout có nhiều phiên bản server chạy song song phải chắc chắn code cũ **có thể đọc** hash scheme mới trước khi instance mới bắt đầu tạo chúng; nếu không, user login trên instance A được upgrade rồi bị từ chối trên instance B dùng code cũ. Chiến lược an toàn thường gồm deploy code **đọc được cả legacy và new** trước, rồi mới bật **ghi new** và cuối cùng xóa đọc legacy. Không hạ chuẩn mật mã để che lỗi rollout.

Đồng thời cần giới hạn tổng chi phí password hashing: mỗi login rất tốn CPU/memory; có rate limiting, account lockout/backoff phù hợp, chống credential stuffing và giám sát performance để tránh DoS.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm tra/an toàn |
| --- | --- | --- |
| `There is no PasswordEncoder mapped for the id "null"` | Hash cũ chưa có prefix. | Phân loại và gắn nhãn có chứng cứ hoặc reset; không bật noop fallback. |
| Đã thêm prefix nhưng đăng nhập vẫn sai | ID không khớp format/cost/pepper, password thật sai, dữ liệu đã hỏng. | Đối chiếu test vectors và lịch sử encoder; không thử mù thuật toán. |
| `{bcrypt-v1}` login được nhưng DB không đổi | Chưa cấu hình `UserDetailsPasswordService` vào đúng provider; updater lỗi; `upgradeEncoding` không kích hoạt. | Test provider + service + DB sau login thành công. |
| Login thành công mà scheme mới vẫn cost cũ | Chỉ đổi prefix, chưa gọi `encode(raw)`; encoder mới cấu hình cost chưa nâng. | Kiểm tra hash mới do encoder tạo, đừng rename legacy ID. |
| Login sai lại cập nhật hash | Custom flow rehash trước khi verify, không có boundary success. | Chỉ lưu sau xác thực thành công; test wrong password giữ nguyên hash. |
| Bản ghi password reset bị ghi đè | Ghi update vô điều kiện sau khi đã đọc hash cũ. | Dùng CAS/transaction và xử lý conflict. |
| User login được node A nhưng lỗi node B | Các node không dùng cùng allowlist hoặc version tương thích. | Rollout hai pha reader-before-writer; nhất quán cấu hình. |
| Hash vẫn lưu plaintext sau migration | Client/service bypass encoder, script ghi giá trị thô, `noop` được chấp nhận. | Audit tất cả luồng tạo/đổi/reset password; không dùng plaintext storage. |
| Một nhóm dormant users vẫn legacy | Họ không login nên rehash-on-login không chạy. | Chính sách reset/sunset theo hạn, không giữ support cũ vĩnh viễn. |
| Authentication trả 500 với unknown ID | Encoder ném lỗi định dạng không được xử lý ở boundary thích hợp. | Fail closed và đưa lỗi qua handling/monitoring phù hợp, không chuyển thành login thành công. |

## 13. Checklist triển khai

- [ ] Có thống kê và bằng chứng về mọi dạng hash/password lịch sử, kể cả tham số và pepper.
- [ ] Có danh sách **allowed ID → encoder**, mỗi mapping đều có chủ sở hữu/phê duyệt và thời hạn nếu legacy.
- [ ] `idForEncode` trỏ duy nhất scheme đang được phê duyệt cho password mới.
- [ ] Không bật `noop`, không fallback cho hash không rõ ID, không tự thử nhiều encoder.
- [ ] Các tài khoản với hash không phân loại được đi qua reset/recovery an toàn.
- [ ] `UserDetailsService` trả stored hash đầy đủ; `DaoAuthenticationProvider` dùng policy encoder.
- [ ] `UserDetailsPasswordService` hoặc luồng tương đương đã kết nối với provider và có CAS ghi DB.
- [ ] Tests: đúng mật khẩu → rehash; sai mật khẩu → không ghi; unknown ID → từ chối; policy cost → nâng cấp.
- [ ] Kiểm tra cả session/login form, API, nhiều node, cache, account disabled, login đồng thời, password reset.
- [ ] Metrics/audit **không chứa** raw password, password hash, token, cookie session.
- [ ] Đã có lịch sunset và tiêu chí gỡ legacy encoder, hướng dẫn người dùng không đăng nhập lâu ngày.
- [ ] Rollback không biến hash hiện hành trở lại scheme yếu.

## 14. Câu hỏi ôn tập

**Q1. Vì sao chỉ thêm `{bcrypt}` vào đầu hash cũ chưa phải nâng cấp mật khẩu?** Vì phần hash và cost vẫn cũ. Rehash thật sự cần raw password hợp lệ rồi encode bằng scheme mới.

**Q2. `DelegatingPasswordEncoder` chọn verifier bằng cách nào?** Nó tách `{id}` từ stored hash và tìm encoder trong map allowlist của server. `idForEncode` chỉ ra encoder được dùng khi tạo hash mới.

**Q3. Dữ liệu password cũ thiếu `{id}` thì có nên bật fallback cho tất cả không?** Không. Chỉ gắn nhãn khi xác minh chắc chắn scheme lịch sử hoặc dùng quy trình reset. Fallback mù dễ mở rộng tập thuật toán yếu ngoài policy.

**Q4. Vai trò của `UserDetailsPasswordService` khác `UserDetailsService` thế nào?** `UserDetailsService` đọc user/hash; `UserDetailsPasswordService` ghi hash đã được nâng cấp sau khi provider xác thực đúng và yêu cầu upgrade.

**Q5. Vì sao cần điều kiện `WHERE password_hash = oldHash` khi cập nhật?** Để tránh việc một login dựa trên hash cũ ghi đè thay đổi mật khẩu/reset vừa diễn ra ở thread/server khác.

**Q6. Có thể đổi hash cũ thành Argon2id mà không biết password gốc không?** Không, trừ khi đang có raw password hợp lệ ở thời điểm login/change/reset. Hash là phép một chiều, không thể chuyển trực tiếp giữa scheme một cách an toàn chỉ bằng tên thuật toán.

**Q7. Có đủ để giữ encoder legacy mãi vì một số account không login?** Không. Cần hạn ngừng chấp nhận cũ, xử lý dormant users và quy trình recovery/reset.

**Ghi nhớ:** **Phân loại đúng → allowlist chặt → verify bằng scheme được phê duyệt → rehash chỉ sau thành công → cập nhật an toàn → loại bỏ legacy đúng hạn.** Đây là cách di chuyển password store mà không vô tình chấp nhận thuật toán yếu hoặc làm hỏng quy trình xác thực.
