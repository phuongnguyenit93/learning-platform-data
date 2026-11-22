# Tải quyền, nhóm quyền và tránh truy vấn lặp không cần thiết trong Spring Security

> **Phạm vi:** Spring Security Authentication trên ứng dụng Servlet/Spring MVC. Chủ đề trọng tâm là cách `UserDetailsService` tải **quyền trực tiếp**, **quyền từ các nhóm người dùng**, tạo `GrantedAuthority` và tránh lỗi truy vấn lặp kiểu **N+1**. Bài có ví dụ **Spring Boot 3.5.x, Java 17+, Spring JDBC và H2** chạy độc lập, cùng hướng triển khai với Spring Data JPA. Phân biệt rõ hiệu quả truy vấn, bảo vệ dữ liệu danh tính, cập nhật quyền và vòng đời session/cache.

## 1. Mục tiêu của bài học

Sau bài này bạn cần làm được những việc sau:

1. Vẽ được quan hệ **tài khoản → quyền trực tiếp**, **tài khoản → nhóm → quyền từ nhóm**, giải thích quy tắc gộp và loại trùng.
2. Hiểu vì sao `DaoAuthenticationProvider` cần `UserDetailsService.loadUserByUsername(...)` cung cấp `UserDetails` cùng authorities đáng tin.
3. Nhận biết N+1: một truy vấn lấy danh sách nhóm, sau đó lại một truy vấn cho **mỗi nhóm** để lấy quyền.
4. Biết gom quyền bằng **truy vấn tập hợp (set-based query)**, projection/batch loading hoặc cấu hình fetch thích hợp; không mặc định eager-load mọi quan hệ.
5. Tạo danh sách `GrantedAuthority` đúng định dạng, chỉ cấp quyền từ kho dữ liệu được tin cậy và phân biệt role với permission nghiệp vụ.
6. Đo số SQL query thay vì suy đoán; kiểm tra ảnh hưởng của index, kích thước tập quyền, group hierarchy và request concurrency.
7. Giải thích giới hạn của cache: quyền bị thu hồi trong DB chưa chắc có hiệu lực tức thì với session, token hoặc `UserDetails` đã cache.
8. Có thể triển khai demo chạy được và kiểm thử trường hợp đúng quyền, quyền kế thừa qua nhóm, trùng quyền và không đủ quyền.

**Câu hỏi thiết kế quan trọng:** một user thuộc 30 nhóm có nhất thiết cần 30 lần truy vấn DB để biết quyền không? **Không.** Nếu dữ liệu được mô hình hóa phù hợp, việc tổng hợp có thể thực hiện bằng một truy vấn SQL hoặc vài truy vấn theo lô với số lượt ổn định theo cấu trúc dữ liệu.

## 2. Vị trí tải quyền trong luồng authentication

```text
HTTP request chứa username/password
    ↓
Spring Security authentication filter
    ↓
AuthenticationManager (thường ProviderManager)
    ↓
DaoAuthenticationProvider
    ├── UserDetailsService.loadUserByUsername(username)
    │    ├── lấy tài khoản và trạng thái
    │    ├── lấy quyền trực tiếp
    │    ├── lấy các nhóm hợp lệ
    │    ├── lấy quyền từ nhóm (tập hợp, tránh N+1)
    │    └── trả UserDetails với GrantedAuthority
    └── PasswordEncoder.matches(rawPassword, storedHash)
    ↓
Authentication đã xác thực (principal + authorities)
    ↓
SecurityContext
    ↓
Authorization rule: hasRole / hasAuthority / method security
```

`UserDetailsService` không tự kiểm tra mật khẩu trong flow thông thường; nó tải thông tin cần cho `DaoAuthenticationProvider`. Quyền được lấy từ kho tài khoản/tổ chức và **được đưa vào `UserDetails.getAuthorities()`**. Sau xác thực, các quy tắc `hasRole(...)`, `hasAuthority(...)` và `@PreAuthorize` có thể dựa vào authorities đó.

Một điểm cần hiểu: danh sách authority là một **snapshot tại thời điểm authentication**. Nếu dùng session, kết quả có thể được lưu lại và các request sau không tải lại quyền. Nếu dùng HTTP Basic stateless, tài khoản thường được tải khi credential được xử lý ở từng request; tuy nhiên cache hoặc cơ chế xác thực khác có thể làm điều đó thay đổi. Không đồng nhất việc “request đến” với “`loadUserByUsername` chắc chắn chạy”.

## 3. Mô hình dữ liệu: quyền trực tiếp và quyền qua nhóm

Giả sử hệ thống quản lý tài liệu có bảng như sau:

| Bảng | Nội dung | Ví dụ |
| --- | --- | --- |
| `app_account` | ID nội bộ, username, password hash, enabled | `mai`, `an` |
| `account_authority` | Quyền gán trực tiếp cho tài khoản | `mai → ROLE_READER` |
| `security_group` | Danh mục nhóm người dùng | `content-editors` |
| `group_membership` | Quan hệ user thuộc nhóm nào | `mai → content-editors` |
| `group_authority` | Quyền/role được gán cho một nhóm | `content-editors → ROLE_EDITOR` |

```text
Account: mai
   ├── direct authority: ROLE_READER
   └── member of: content-editors
           ├── ROLE_EDITOR
           └── documents:write

Effective authorities for mai:
   ROLE_READER
   ROLE_EDITOR
   documents:write
```

Trong bài này, **“quyền hiệu lực” là hợp của quyền trực tiếp và quyền từ các nhóm đang có hiệu lực**. Đây là quy tắc ứng dụng lựa chọn để học; các hệ thống thực có thể có deny rules, thứ tự ưu tiên, thời gian hiệu lực, phân cấp nhóm hoặc điều kiện theo tenant. Không tự áp dụng phép hợp đơn giản khi hệ thống có chính sách **deny overrides** hoặc quy tắc xung đột đặc biệt.

### Phân biệt nhóm, vai trò và permission

- **Group (nhóm)**: cấu trúc tổ chức hoặc tập thành viên, ví dụ `content-editors`. Group tự nó chưa chắc là authority để gọi `hasRole`.
- **Role (vai trò)**: một nhóm quyền được biểu diễn thành authority, ví dụ `ROLE_EDITOR` hoặc `ROLE_READER`.
- **Permission (quyền thao tác)**: quyền ứng dụng, ví dụ `documents:write` hoặc `documents:read`.
- **GrantedAuthority**: đối tượng mà Spring Security dùng để biểu diễn authority đã gán. Cách đơn giản là `new SimpleGrantedAuthority("ROLE_EDITOR")`.

Rule `hasRole("EDITOR")` mặc định kiểm tra authority `ROLE_EDITOR`; `hasAuthority("documents:write")` kiểm tra chuỗi chính xác. Đừng gắn một group name như `content-editors` vào authorities rồi mong `hasRole("EDITOR")` tự hiểu đó là nhóm biên tập.

**Thiết kế tên rõ ràng:** áp dụng quy tắc nhất quán như `ROLE_...` cho role và `resource:action` cho permission. Khi ánh xạ quyền trong DB, kiểm tra chuỗi hợp lệ, không sinh `ROLE_ROLE_EDITOR` và không tin quyền do frontend tự gửi.

### Cần tính thêm những trường hợp nào?

1. User thuộc hai nhóm cùng có `ROLE_EDITOR` → **chỉ có một authority hiệu lực**.
2. User có `ROLE_READER` trực tiếp và từ nhóm → cũng nên loại trùng.
3. User không thuộc nhóm nào → vẫn có thể có quyền trực tiếp hoặc authorities rỗng.
4. Nhóm bị vô hiệu hóa, membership hết hạn → cần lọc theo cờ/trạng thái trước khi cấp quyền; mô hình demo chưa có cột này.
5. Quyền áp dụng cho từng tenant/organization → phải ràng buộc đúng namespace khi truy vấn, không lấy nhóm trùng tên ở tenant khác.
6. Đăng nhập bằng JWT/OIDC → có thể có authorities từ issuer/converter; không mặc định cộng mọi claim bên ngoài vào quyền nội bộ nếu thiếu quy tắc trust.

## 4. Lỗi N+1 xuất hiện như thế nào?

### Cách tải không hiệu quả

Giả sử ta làm:

```java
// Pseudocode minh họa anti-pattern; không phải class chạy độc lập.
Account user = accountRepository.findByUsername(username).orElseThrow();
List<Group> groups = groupRepository.findGroupsOfUser(user.getId());

Set<String> codes = new HashSet<>(user.getDirectAuthorities());
for (Group group : groups) {
    // Sai hướng: mỗi nhóm lại kích hoạt một query riêng.
    codes.addAll(groupAuthorityRepository.findCodesByGroupId(group.getId()));
}
```

Nếu có N nhóm, riêng phần group lookup có thể tiêu tốn:

```text
1 SELECT user
1 SELECT group memberships
N SELECT group authorities (1 lần / nhóm)
+ các SELECT khác để lấy direct authorities hoặc lazy relations
--------------------------------------------------------------
Tối thiểu N + 2 SELECT trong đường đi minh họa
```

Ví dụ N = 30 thì một request có thể tạo 32 SELECT trở lên; cùng endpoint 100 request làm tải DB tăng nhanh. Với ORM, N+1 cũng có thể **ẩn trong vòng lặp gọi getter** như `group.getAuthorities()` hoặc khi mapping DTO/`UserDetails` sau khi đã nhận entity.

N+1 mô tả **số lần đi DB tăng theo số phần tử** cần tải. Đừng nhầm với việc một truy vấn trả nhiều hàng: một truy vấn có 300 authority rows có đặc tính chi phí khác 300 round-trip. Kết quả nhiều hàng vẫn có thể tốn băng thông và memory, nên mục tiêu không phải gom mọi thứ vào một câu SQL khổng lồ bất chấp cardinality.

### Cách đúng: tính quyền theo tập hợp

Một phương án tốt là **hai SELECT cho mỗi lần tải user**, không phụ thuộc số nhóm:

1. SELECT tài khoản và trạng thái theo `username` (dùng unique index).
2. SELECT quyền hiệu lực bằng **`UNION`** quyền trực tiếp và quyền qua nhóm. Database xử lý join/dedup dựa trên index.

```sql
SELECT authority_code
FROM (
    SELECT da.authority_code
    FROM account_authority da
    WHERE da.account_id = ?

    UNION

    SELECT ga.authority_code
    FROM group_membership gm
    JOIN group_authority ga
      ON ga.group_id = gm.group_id
    WHERE gm.account_id = ?
) resolved
ORDER BY authority_code;
```

`UNION` mặc định loại trùng. Nếu muốn `UNION ALL` để tối ưu một số DB, cần loại trùng trong Java bằng `Set` hoặc `distinct` và kiểm chứng hiệu quả trên dữ liệu thật. Giữ thứ tự kết quả xác định giúp test và điều tra dễ hơn nhưng **thứ tự authorities không có ý nghĩa cấp quyền**.

Đoạn SQL sử dụng cấu trúc của bài này; tên bảng và cột phải đổi theo schema của dự án. Khi có nhóm vô hiệu hóa hoặc membership có thời hạn, thêm điều kiện lọc vào đúng phép JOIN, không chỉ lọc ở UI.

## 5. Các chiến lược tránh truy vấn lặp

| Kỹ thuật | Phù hợp khi | Điểm cần kiểm tra |
| --- | --- | --- |
| Một query với JOIN/UNION/projection | Quyền trải trên vài bảng chuẩn hóa, cần tải thành snapshot | Index, số row thực tế, dedup và tenant filtering |
| Hai bước: lấy account, lấy toàn bộ authorities của account | Cần giữ account query đơn giản | Số SELECT ổn định, snapshot hợp lý |
| Batch query `WHERE group_id IN (...)` | Đã có danh sách nhóm và cần tải quyền của nhiều nhóm | Chia batch nếu quá giới hạn tham số; tránh gọi lặp trong vòng for |
| Spring Data JPA `@EntityGraph` có phạm vi | Cần lấy một quan hệ được kiểm soát cùng entity | Không tự động giải quyết mọi quan hệ lồng nhau |
| JPQL constructor projection / interface projection | Chỉ cần authority code, không cần entity graph lớn | Tránh N+1 do lazy getter; validate JPQL và kiểu projection |
| Hibernate batch fetching (`@BatchSize` / cấu hình batch) | Không tránh được mọi lazy load trong một số flow | Giảm N+1 thành truy vấn theo lô nhưng vẫn có nhiều query |
| Cache snapshot quyền có TTL/invalidation | Nguồn phân quyền tốn kém, nhiều lần xác thực lại | Độ cũ quyền, thu hồi quyền, password hash và shared mutable state |

**Không chọn `FetchType.EAGER` cho mọi association** để chữa N+1: một user có nhiều groups, mỗi group có nhiều roles/permissions có thể tạo phép nhân Cartesian, kết quả lớn hoặc lỗi khi fetch nhiều bag. Chỉ fetch thuộc tính thực sự cần. Với JPA, đếm SQL thực thi trên test có nhiều nhóm; không chỉ dựa vào việc code có `@EntityGraph` hay `JOIN FETCH`.

Nếu role hierarchy đã được xử lý bằng `RoleHierarchy` ở tầng authorization, xác định rõ có cần **materialize toàn bộ quyền kế thừa vào `Authentication.getAuthorities()`** hay để Spring Security áp dụng role hierarchy khi kiểm tra. Không mở rộng hai lần không kiểm soát.

## 6. Ví dụ Spring Boot đầy đủ: tải user + quyền bằng hai SELECT

Dự án dùng **Spring JDBC** để SQL nhìn thấy rõ ràng, tránh các yếu tố ẩn từ lazy-loading của ORM. Demo đăng nhập HTTP Basic stateless; mỗi lần tải tài khoản (khi provider xử lý credential) sẽ gọi đúng **hai SELECT** trong `UserDetailsService`: một account, một danh sách authority đã tổng hợp. Dữ liệu đặt trong H2 in-memory và chỉ dành cho học tập.

### 6.1. Cấu trúc thư mục

```text
authority-loading-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/dev/demo/authorities/AuthoritiesDemoApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/dev/demo/authorities/AuthoritiesDemoApplicationTests.java
```

Yêu cầu JDK 17+ và Gradle tương thích với Spring Boot 3.5.

`settings.gradle`:

```groovy
rootProject.name = 'authority-loading-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:authoritiesdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Demo: không mở H2 Console hoặc bật log SQL chứa credential.
```

### 6.2. Schema chuẩn hóa và index

`src/main/resources/schema.sql`:

```sql
CREATE TABLE app_account (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE security_group (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE account_authority (
    account_id BIGINT NOT NULL REFERENCES app_account(id),
    authority_code VARCHAR(160) NOT NULL,
    PRIMARY KEY (account_id, authority_code)
);

CREATE TABLE group_membership (
    account_id BIGINT NOT NULL REFERENCES app_account(id),
    group_id BIGINT NOT NULL REFERENCES security_group(id),
    PRIMARY KEY (account_id, group_id)
);

CREATE TABLE group_authority (
    group_id BIGINT NOT NULL REFERENCES security_group(id),
    authority_code VARCHAR(160) NOT NULL,
    PRIMARY KEY (group_id, authority_code)
);

CREATE INDEX idx_group_membership_by_group
    ON group_membership(group_id);
```

Unique index của `username` hỗ trợ account lookup; khóa chính ghép của `account_authority` và `group_membership` giúp truy vấn theo `account_id`; khóa chính `group_authority(group_id, authority_code)` hỗ trợ join theo group ID. Tùy DB thực tế và phân bố dữ liệu cần kiểm tra `EXPLAIN`/query plan thay vì đoán index luôn hiệu quả.

Trong multi-tenant, unique constraint và điều kiện truy vấn phải bao gồm `tenant_id` hoặc khóa định danh tương ứng. Schema đơn giản này cố ý **chưa triển khai tenant** để tập trung vào quan hệ account → group → authority.

### 6.3. Ứng dụng Java hoàn chỉnh

Tạo `src/main/java/dev/demo/authorities/AuthoritiesDemoApplication.java`:

```java
package dev.demo.authorities;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthoritiesDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthoritiesDemoApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    CommandLineRunner seed(JdbcTemplate db, PasswordEncoder encoder) {
        return args -> {
            // Chỉ phục vụ demo: khởi tạo password hash bằng BCrypt.
            db.update(
                    "INSERT INTO app_account "
                            + "(username, password_hash, enabled) VALUES (?, ?, ?)",
                    "mai", encoder.encode("demo-pass-123"), true);
            db.update(
                    "INSERT INTO app_account "
                            + "(username, password_hash, enabled) VALUES (?, ?, ?)",
                    "an", encoder.encode("demo-pass-123"), true);
            db.update(
                    "INSERT INTO security_group (group_name) VALUES (?)",
                    "content-editors");

            Long maiId = db.queryForObject(
                    "SELECT id FROM app_account WHERE username = ?",
                    Long.class, "mai");
            Long anId = db.queryForObject(
                    "SELECT id FROM app_account WHERE username = ?",
                    Long.class, "an");
            Long editorsId = db.queryForObject(
                    "SELECT id FROM security_group WHERE group_name = ?",
                    Long.class, "content-editors");

            db.update(
                    "INSERT INTO account_authority VALUES (?, ?)",
                    maiId, "ROLE_READER");
            db.update(
                    "INSERT INTO account_authority VALUES (?, ?)",
                    anId, "ROLE_READER");
            db.update(
                    "INSERT INTO group_membership VALUES (?, ?)",
                    maiId, editorsId);
            db.update(
                    "INSERT INTO group_authority VALUES (?, ?)",
                    editorsId, "ROLE_EDITOR");
            db.update(
                    "INSERT INTO group_authority VALUES (?, ?)",
                    editorsId, "documents:write");

            // Mai được ROLE_READER trực tiếp.
            // ROLE_EDITOR và documents:write đến từ nhóm.
        };
    }
}

@Configuration
class DemoSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/me").authenticated()
                    .requestMatchers("/editor/ping").hasRole("EDITOR")
                    .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS));

        return http.build();
    }
}

@Service
class DatabaseAccountUserDetailsService implements UserDetailsService {
    private final JdbcTemplate jdbc;

    DatabaseAccountUserDetailsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public UserDetails loadUserByUsername(String username)
            throws UsernameNotFoundException {

        // SELECT #1: lấy đúng một tài khoản (username unique).
        List<AccountRow> accounts = jdbc.query(
                "SELECT id, username, password_hash, enabled "
                        + "FROM app_account WHERE username = ?",
                (rs, rowNum) -> new AccountRow(
                        rs.getLong("id"),
                        rs.getString("username"),
                        rs.getString("password_hash"),
                        rs.getBoolean("enabled")),
                username);

        if (accounts.isEmpty()) {
            throw new UsernameNotFoundException("Account not found");
        }

        AccountRow account = accounts.get(0);

        // SELECT #2: một truy vấn gộp cả quyền trực tiếp và từ nhóm.
        String sql = """
                SELECT authority_code
                FROM (
                    SELECT da.authority_code
                    FROM account_authority da
                    WHERE da.account_id = ?

                    UNION

                    SELECT ga.authority_code
                    FROM group_membership gm
                    JOIN group_authority ga
                      ON ga.group_id = gm.group_id
                    WHERE gm.account_id = ?
                ) resolved
                ORDER BY authority_code
                """;

        List<GrantedAuthority> authorities = jdbc.query(
                sql,
                (rs, rowNum) -> new SimpleGrantedAuthority(
                        rs.getString("authority_code")),
                account.id(), account.id());

        return User.withUsername(account.username())
                .password(account.passwordHash())
                .disabled(!account.enabled())
                .authorities(authorities)
                .build();
    }

    private record AccountRow(
            long id, String username, String passwordHash, boolean enabled) {}
}

@RestController
class MeController {
    record MeResponse(String username, List<String> authorities) {}

    @GetMapping("/me")
    MeResponse me(Authentication authentication) {
        List<String> names = authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
        return new MeResponse(authentication.getName(), names);
    }

    @GetMapping("/editor/ping")
    String editorPing() {
        return "editor-ok";
    }
}
```

**Giải thích phần quan trọng:**

1. `DatabaseAccountUserDetailsService` chỉ thực hiện **hai query SELECT** trong mỗi lượt `loadUserByUsername(...)` thành công: truy vấn account và truy vấn authority tập hợp. Số query **không tăng theo số nhóm**; số dòng kết quả và thời gian JOIN vẫn phụ thuộc dữ liệu.
2. Dùng tham số `?` qua `JdbcTemplate` thay vì ghép chuỗi username vào SQL để tránh SQL injection.
3. `UNION` loại authority trùng nếu user vừa có quyền trực tiếp vừa thừa hưởng cùng quyền từ nhóm.
4. `User.withUsername(...).authorities(...)` dựng principal có `GrantedAuthority` đáng tin; ứng dụng **không cần** định nghĩa custom `UserDetails` chỉ để lấy roles.
5. `DaoAuthenticationProvider` do Spring Security cấu hình với `UserDetailsService` và `PasswordEncoder` sẽ kiểm tra password hash; service tải quyền **không tự so sánh password**.
6. `hasRole("EDITOR")` kiểm tra `ROLE_EDITOR`. User `mai` có quyền đó **qua nhóm**, còn `an` chỉ có `ROLE_READER`.
7. `STATELESS` cùng HTTP Basic giúp demo kiểm tra credential riêng theo request. Đây không phải cách thiết kế mặc định cho mọi browser form login; với browser gửi cookie cần đánh giá CSRF và session.
8. `schema.sql` chạy khi khởi động DB H2, sau đó `CommandLineRunner` thêm dữ liệu demo. Hai username/mật khẩu trong ví dụ **không được dùng cho môi trường thực**.

### 6.4. Chạy thử từ terminal

Tại thư mục `authority-loading-demo`, chạy với Gradle tương thích Java 17:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper, dùng `./gradlew bootRun` trên macOS/Linux hoặc `gradlew.bat bootRun` trên Windows. Gửi request từ terminal khác:

```bash
curl -i -u mai:demo-pass-123 http://localhost:8080/me
curl -i -u mai:demo-pass-123 http://localhost:8080/editor/ping
curl -i -u an:demo-pass-123 http://localhost:8080/me
curl -i -u an:demo-pass-123 http://localhost:8080/editor/ping
curl -i http://localhost:8080/me
```

Trên Windows PowerShell, có thể thay `curl` bằng `curl.exe` để tránh alias. Chỉ nhập mật khẩu demo, không truyền password thật trong lệnh shell dễ lưu vào history.

Kết quả cốt lõi:

| Request | Status | Response khi thành công |
| --- | --- | --- |
| `mai` → `GET /me` | **200** | `{"username":"mai","authorities":["ROLE_EDITOR","ROLE_READER","documents:write"]}` |
| `mai` → `GET /editor/ping` | **200** | `editor-ok` |
| `an` → `GET /me` | **200** | `{"username":"an","authorities":["ROLE_READER"]}` |
| `an` → `GET /editor/ping` | **403** | Không đủ `ROLE_EDITOR` |
| Chưa xác thực → `GET /me` | **401** | HTTP Basic challenge |
| Mật khẩu sai → `GET /me` | **401** | Không trả dữ liệu principal |

Trong chuỗi authorities của `mai`, phần **`ROLE_EDITOR` và `documents:write`** đến từ bảng `group_authority`, mặc dù account không có hai quyền này trực tiếp. Đó là hành vi chính cần chứng minh trong bài.

### 6.5. Kiểm thử với MockMvc

Tạo `src/test/java/dev/demo/authorities/AuthoritiesDemoApplicationTests.java`:

```java
package dev.demo.authorities;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItems;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthoritiesDemoApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void directAndGroupAuthoritiesAreLoaded() throws Exception {
        mvc.perform(get("/me")
                        .with(httpBasic("mai", "demo-pass-123")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("mai"))
                .andExpect(jsonPath("$.authorities",
                        hasItems("ROLE_READER",
                                "ROLE_EDITOR",
                                "documents:write")));
    }

    @Test
    void groupRoleControlsEditorEndpoint() throws Exception {
        mvc.perform(get("/editor/ping")
                        .with(httpBasic("mai", "demo-pass-123")))
                .andExpect(status().isOk());

        mvc.perform(get("/editor/ping")
                        .with(httpBasic("an", "demo-pass-123")))
                .andExpect(status().isForbidden());
    }

    @Test
    void missingOrBadCredentialIsRejected() throws Exception {
        mvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                        .with(httpBasic("mai", "wrong")))
                .andExpect(status().isUnauthorized());
    }
}
```

Chạy:

```bash
gradle test
```

Những test này chứng minh **quyền từ nhóm được phản ánh vào authorization** và đường login thật của HTTP Basic hoạt động. Tuy nhiên chúng **chưa tự chứng minh số query**. Muốn chứng minh không có N+1, cần thêm kiểm chứng SQL count trên lần đăng nhập user thuộc nhiều nhóm.

## 7. Đo query thực tế và viết test bắt N+1

### 7.1. Đo bằng gì?

- Với Spring JDBC, sử dụng data source proxy, JDBC tracing/metrics hoặc công cụ quan sát SQL của DB trong môi trường dev/test, chỉ lọc các `SELECT` thuộc `loadUserByUsername`.
- Với Spring Data JPA/Hibernate, bật thống kê Hibernate hoặc dùng công cụ đếm query. Chỉ đếm SQL thực thi, không chỉ đếm số method repository.
- Đo riêng lần **cold login**, **warm cache** và request **đã có session**. Ba trường hợp có đường đi rất khác nhau.
- Loại các query tạo schema/seed hoặc query nghiệp vụ của controller khỏi số liệu phần tải authority.

### 7.2. Kịch bản đo

Tạo 1 user thuộc N nhóm; mỗi nhóm có vài quyền, có một số quyền trùng. Chạy với N = 1, 5, 20, 100. Với demo JDBC:

```text
Case N=1   -> Account SELECT: 1; authorities UNION SELECT: 1
Case N=5   -> Account SELECT: 1; authorities UNION SELECT: 1
Case N=20  -> Account SELECT: 1; authorities UNION SELECT: 1
Case N=100 -> Account SELECT: 1; authorities UNION SELECT: 1
```

Đây là **số câu SELECT do method demo gọi** khi tài khoản tồn tại, không phải kết quả benchmark độ trễ DB đã đo. Nếu hiện thực khác tạo N SELECT cho group rights thì N+1 vẫn tồn tại. Ngoài số query, phải đo tổng số rows, thời gian chạy, CPU và plan: một join khổng lồ có thể chậm dù chỉ một round-trip.

### 7.3. Test không làm sai nghĩa “truy vấn lặp”

Một test chỉ khẳng định `getAuthorities()` có đúng ba phần tử **không đủ** để bắt N+1. Nên có test bổ sung:

1. Insert một user có 50 nhóm/role associations (có trùng quyền).
2. Xóa hoặc vô hiệu cache cho lần cold authentication nếu đang đo query gốc.
3. Gọi `loadUserByUsername` hoặc authentication manager qua một đường test thực.
4. Đếm SELECT trong khoảng gọi đó; với giải pháp hai SELECT, số đếm không đổi khi tăng nhóm.
5. Assert tập quyền hiệu lực khớp dữ liệu, không có duplicate.
6. Chạy lại khi group bị xóa hoặc quyền thay đổi, kiểm tra invalidation và session state theo chính sách.

Nếu dùng database test container giống production, kết quả sẽ đáng tin hơn việc chỉ đo H2. `EXPLAIN ANALYZE`/thống kê thời gian có ích khi dữ liệu lớn; H2 là môi trường học tập, không dự đoán chính xác planner của PostgreSQL/MySQL.

## 8. Nếu dự án dùng Spring Data JPA thì làm sao?

Spring Data JPA thường ánh xạ `Account`, `Group`, `Role` và các quan hệ bằng annotation. Có hai vấn đề riêng: **số round-trip** và **kích thước graph được tải**.

### 8.1. Tránh vòng lặp lazy-loading

```java
// Pseudocode minh họa anti-pattern; class và entity chưa khai báo.
Account account = repository.findByUsername(username).orElseThrow();

for (Group group : account.getGroups()) {
    for (Role role : group.getRoles()) {
        authorities.add(new SimpleGrantedAuthority(role.getCode()));
    }
}
```

Nếu `groups` hoặc `roles` là LAZY, getter có thể sinh SQL theo từng group trong vòng lặp. Đó là N+1 dù method repository ban đầu chỉ viết một dòng.

### 8.2. Các phương án triển khai JPA

**Phương án 1 — Projection lấy authority code:** viết một repository query dùng JOIN/truy vấn theo account ID, trả danh sách `String`/projection. Chuyển code thành `SimpleGrantedAuthority`. Tránh phải dựng full entity graph.

**Phương án 2 — Lấy account trước, lấy quyền sau:** `findByUsername(...)` tải đúng account; query thứ hai trả mọi authority trực tiếp và từ group. Có thể cần hai repository method cho hai nguồn hoặc một native query `UNION` tùy database. Số query giữ ít và ổn định.

**Phương án 3 — @EntityGraph một số quan hệ cụ thể:** dùng khi thực sự cần entity liên quan và cardinality vừa phải:

```java
// Snippet JPA cần có entity Account và AccountRepository thích hợp.
@EntityGraph(attributePaths = {"groups"})
Optional<Account> findByUsername(String username);
```

Đây **không phải giải pháp tự động** cho quyền lồng trong `group.roles`. Nếu sau đó truy cập `group.getRoles()` nhiều lần, vẫn có thể phát sinh truy vấn bổ sung. Dùng `@EntityGraph(attributePaths={"groups","groups.roles"})` hoặc nhiều `JOIN FETCH` với các collection lớn có nguy cơ **nhân bản số dòng**, thậm chí `MultipleBagFetchException` khi fetch nhiều bag; cần đo và chọn theo cấu trúc mapping.

**Phương án 4 — Hibernate batch fetching:** dùng `@BatchSize`/`hibernate.default_batch_fetch_size` khi lazy loading cần thiết. Nó có thể gom N truy vấn thành số batch nhỏ hơn nhưng không bảo đảm đúng một SELECT.

**Phương án 5 — DTO projection với native SQL:** khi join/union phức tạp hoặc cần performance rõ ràng. Chú ý SQL dialect, tên bảng, schema migration và test trên DB thật.

### 8.3. Transaction boundary

Trong JPA, nếu `UserDetailsService` truy cập quan hệ lazy **ngoài transaction**, có thể gặp `LazyInitializationException`. Giải pháp đúng là **định nghĩa fetch/query và transaction phù hợp**, materialize snapshot `UserDetails` ngay tại tầng service. Không bật Open Session in View như một cách chữa N+1; làm như vậy có thể đẩy query bất ngờ ra controller/serializer.

Ví dụ gắn `@Transactional(readOnly=true)` cho method tải user khi cần (snippet):

```java
@Override
@Transactional(readOnly = true)
public UserDetails loadUserByUsername(String username) {
    // 1. Query account; 2. Query authorities theo lô;
    // 3. Tạo snapshot UserDetails trước khi transaction kết thúc.
    // Phần repository/entity cụ thể do ứng dụng cung cấp.
}
```

`@Transactional(readOnly=true)` không tự biến nhiều query thành một query và không phải cam kết ngăn mọi cập nhật từ mọi thread; nó chủ yếu giúp quản lý transaction/hint cho persistence provider. Tải đúng dữ liệu vẫn là trách nhiệm thiết kế query.

## 9. Cache quyền: tối ưu có điều kiện, không đánh đổi bảo mật

Một số hệ thống xác thực rất thường xuyên (ví dụ API dùng Basic stateless) có thể cache `UserDetails` để giảm tải DB. Spring Security hỗ trợ `CachingUserDetailsService`/`UserCache` và có thể kết hợp caching của Spring như `@Cacheable`. Nhưng **đối tượng UserDetails có password hash và flags**, nên caching cần thiết kế cẩn thận.

### 9.1. Cache không có nghĩa quyền được cập nhật ngay

Giả sử `mai` đang có `ROLE_EDITOR` rồi admin rút quyền trong DB:

```text
t0: loadUserByUsername -> authorities = [ROLE_EDITOR, ROLE_READER]
t1: admin remove ROLE_EDITOR trong DB
t2: cache / existing HTTP session vẫn giữ snapshot cũ
t3: request mới có thể còn thấy ROLE_EDITOR
t4: cache evict / session invalidated / token hết hạn / revalidate
    -> authority mới có hiệu lực theo chính sách
```

**Câu hỏi nghiệp vụ:** quyền bị thu hồi phải có hiệu lực sau 5 giây, 5 phút hay ngay lập tức? Không có câu trả lời chung. Từ yêu cầu đó mới chọn TTL, eviction, session revocation và quy trình refresh.

### 9.2. Rủi ro với password hash và eraseCredentials

`ProviderManager` theo mặc định gọi `eraseCredentials()` khi authentication thành công nếu result/principal hỗ trợ `CredentialsContainer`. `org.springframework.security.core.userdetails.User` có cơ chế xóa credential. Nếu một `UserDetails` trong cache là **cùng object instance** được dùng làm principal của kết quả, việc xóa có thể khiến cached entry mất password hash và những lần xác thực sau gặp lỗi.

Các lựa chọn cần cân nhắc:

1. **Không cache UserDetails chứa hash** khi số lần authentication ít hoặc đã có server session, tránh rủi ro và đơn giản hóa invalidation.
2. **Cache dữ liệu domain không nhạy cảm/authority IDs** ở nơi riêng, rồi xây `UserDetails` mới mỗi lần authentication; kiểm soát rõ số query còn lại và không đưa secret vào cache không được bảo vệ.
3. **Dùng bản sao/đối tượng khác cho authenticated principal** nếu có custom provider, để credential erasure không sửa cached user object.
4. Khi chủ động dùng `CachingUserDetailsService`/`@Cacheable` theo tài liệu Spring Security, có thể cần **điều chỉnh chính sách credential erasure** để giữ password hash dùng cho các lần kiểm tra sau. Đây là đánh đổi bảo mật thực sự: chỉ thực hiện khi hiểu rủi ro memory/cache, TTL, bảo vệ cache và cơ chế evict; không tắt xóa credential toàn cục chỉ để chữa lỗi một cách tùy tiện.

**Cần phân biệt:** cache `UserDetails` để xác thực lại password, cache **effective authorities** để giảm SQL và lưu `Authentication` trong **SecurityContext/session** là ba cấp dữ liệu khác nhau với vòng đời thu hồi khác nhau.

### 9.3. Cache key và invalidation

- Cache key nên chứa **namespace/tenant + stable account ID** hoặc username đã được chuẩn hóa đủ bảo đảm duy nhất theo cách lookup thực tế.
- Khi đổi password, khóa account, thay group membership, đổi role, xóa role, chuyển tenant, phải xác định các cache entry bị ảnh hưởng.
- Khi một group role đổi, cần vô hiệu hóa quyền của **toàn bộ thành viên liên quan**, không chỉ người thực hiện thay đổi.
- Với nhiều server, eviction phải lan truyền hoặc có TTL/version/revalidation; cache ở một node có thể khác node khác.
- Có thể dùng `security_version`/`authority_version` để phát hiện snapshot lỗi thời nếu tính cập nhật quyền quan trọng.
- Không đưa password, access token, raw `Authentication` hoặc dữ liệu cá nhân không cần thiết vào cache chung hay log.

### 9.4. Có nên cache luôn mọi group graph?

Không nhất thiết. Nếu số nhóm/role nhỏ và query SQL có index tốt, **hai SELECT rõ ràng** thường đủ nhanh và dễ bảo trì. Cache làm giảm query nhưng tăng chi phí invalidation, rủi ro phân quyền lỗi thời và khó debug. Hãy đo p95/p99 latency, load DB và tỷ lệ thay đổi quyền trước khi cache.

## 10. Authorization, role hierarchy và quyền theo tài nguyên

Authorities được gắn vào `Authentication` để Spring Security quyết định truy cập. Nhưng cần phân biệt ba lớp:

1. **Authentication:** xác nhận danh tính và tải authorities đáng tin.
2. **Authorization theo quyền toàn ứng dụng:** `hasRole("EDITOR")`, `hasAuthority("documents:write")`.
3. **Authorization theo tài nguyên:** user có `documents:write` vẫn có thể **không được sửa tài liệu của tenant khác** hoặc tài liệu thuộc owner khác.

Ví dụ `@PreAuthorize("hasAuthority('documents:write')")` kiểm tra quyền tổng quát, nhưng muốn kiểm tra tài liệu số 123 thuộc tenant hợp lệ vẫn cần service/policy theo object. Đừng tạo hàng triệu `GrantedAuthority` như `DOCUMENT_123_WRITE` để thay thế resource ownership nếu hệ thống có nhiều tài liệu.

### Group hierarchy, role hierarchy và nhóm lồng nhau

Nếu group `senior-editors` là thành viên của group `editors`, mô hình demo **không tự xử lý group lồng nhau**. Muốn hỗ trợ cần định nghĩa hướng kế thừa, chu kỳ (cycle), giới hạn độ sâu và cách duyệt closure; cân nhắc recursive SQL CTE hoặc bảng closure có kiểm soát. Không dùng vòng đệ quy không có cycle detection.

`RoleHierarchy` của Spring Security giúp authorization hiểu mối quan hệ như `ROLE_ADMIN > ROLE_EDITOR`. Đó là một cơ chế khác với **user thuộc group nào trong database**. Nếu sử dụng cả hai, xác định tập authority nào được materialize ở login và tập nào được suy diễn ở thời điểm authorization, tránh cấp quyền rộng hơn dự kiến.

### Quyền đến từ IdP hoặc token

Một access token JWT có scope/roles từ issuer; principal có thể là `Jwt` chứ không phải `UserDetails`. Nếu ứng dụng kết hợp quyền DB và token, cần quy tắc kiểm tra issuer, audience, tenant và nguồn sự thật. Không lấy một mảng `roles` do client tự gửi rồi cho thẳng vào `SimpleGrantedAuthority` mà thiếu xác minh.

## 11. Quy tắc nhất quán và bảo mật dữ liệu quyền

**Không cache bừa, không overfetch và không tin dữ liệu bên ngoài chỉ vì giống role code.** Có thể dùng checklist:

- `username` có unique index trong đúng namespace, không phụ thuộc display name.
- `password_hash` được lưu với encoder thích hợp; service chỉ tải hash, không log/serialize nó.
- `account.enabled` và các cờ trạng thái khác được kiểm tra đúng; nếu schema có `locked`/`expired` thì truyền đúng vào `UserDetails`.
- Group membership có foreign key, unique constraint và lọc trạng thái/expiry đúng.
- Authority code được validate theo quy ước role/permission, không chứa giá trị rỗng hoặc dữ liệu từ client chưa tin cậy.
- Query không làm **cross-tenant join**; tenant ID phải xuất hiện trong khóa/điều kiện cần thiết.
- Quan hệ role/group nhiều-nhiều được load bằng query tập hợp hoặc batching có giới hạn.
- Kết quả được dedup trước khi tạo authorities; không phụ thuộc thứ tự DB để cấp quyền.
- Thay đổi quyền có chiến lược evict/revalidate session/cache/token cụ thể.
- Kiểm thử user không có group, nhiều group, role trùng, user disabled, user không tồn tại và revoked role.

Trong hệ thống có quyền nhạy cảm, hãy mô tả rõ **nguồn quyền tối thượng**: account authorities từ DB, IAM/LDAP, OIDC issuer hoặc cơ chế quản trị tập trung. Khi các nguồn xung đột, chính sách ưu tiên và audit phải được định nghĩa; phép union tất cả các nguồn có thể vô tình cấp quyền quá mức.

## 12. Những lỗi phổ biến cần tránh

1. **Tải mỗi group bằng một SELECT trong vòng lặp:** N+1. Chuyển sang JOIN/UNION/projection/batch.
2. **Cho rằng `FetchType.EAGER` tự chữa mọi vấn đề:** có thể gây overfetch, Cartesian explosion, thậm chí lỗi fetch nhiều collection.
3. **Chỉ quan sát SQL ở một user có một nhóm:** N+1 chỉ bộc lộ rõ khi có nhiều phần tử. Test với hàng chục nhóm.
4. **Đếm query mà không tính rows/latency:** một query khổng lồ có thể còn chậm hơn vài query nhỏ được index tốt.
5. **Đưa group name vào `hasRole(...)` như thể nó là role code:** phải ánh xạ group → authority có định nghĩa.
6. **Không loại trùng direct và group authorities:** gây dữ liệu rối; dùng `UNION`/`distinct`/`Set` theo thiết kế.
7. **Đọc quyền qua lazy entity sau khi transaction kết thúc:** dễ `LazyInitializationException`; tạo snapshot trước khi trả `UserDetails`.
8. **Tự kiểm tra password trong `UserDetailsService`:** nhầm trách nhiệm với `DaoAuthenticationProvider`/`PasswordEncoder`.
9. **Trả raw JPA entity làm principal:** có nguy cơ lazy loading, serialize dữ liệu nội bộ và giữ object graph lớn trong session.
10. **Cache `UserDetails` rồi để credential erasure sửa cached instance:** lần login sau có thể mất hash; quản lý object lifecycle và cache đúng.
11. **Tin rằng DB đổi role là mọi session/JWT đổi ngay:** nhiều cơ chế giữ snapshot; cần TTL/revocation/revalidation.
12. **Cache theo username trong hệ thống multi-tenant:** cùng username có thể thuộc nhiều tenant; cache key thiếu namespace dẫn đến lẫn quyền.
13. **Thêm quyền từ nhóm do client khai báo:** membership phải đến từ nguồn đáng tin và được xác minh.
14. **Dùng role toàn cục thay kiểm tra owner/tenant của từng tài nguyên:** có thể mở dữ liệu ngoài phạm vi.
15. **Không có index cho bảng membership và join:** ngay cả query set-based cũng có thể rất chậm khi dữ liệu lớn.
16. **Không kiểm thử deny/revocation:** kiểm thử chỉ happy path không phát hiện quyền bị cấp rộng hơn dự kiến.

## 13. Bài tập củng cố

**Bài A — Nhìn ra N+1.** Một user thuộc 40 nhóm, mỗi nhóm có ba quyền. Viết số SELECT dự kiến của cách lặp query từng nhóm và của cách gom quyền bằng UNION. Giải thích vì sao số rows trả về vẫn có thể lớn mặc dù SQL query count không tăng.

**Bài B — Loại trùng.** Gán `ROLE_EDITOR` trực tiếp cho `mai` trong demo, đồng thời giữ `ROLE_EDITOR` qua group. Kiểm tra `GET /me` chỉ có **một** `ROLE_EDITOR`.

**Bài C — Thu hồi quyền.** Xóa `ROLE_EDITOR` khỏi `group_authority` khi user đã đăng nhập. Dự đoán hành vi với HTTP Basic stateless, form login/session và một application có `UserDetails` cache. Giải thích cache invalidation nào cần thêm.

**Bài D — Tối ưu với JPA.** Viết hai cách tải authorities qua Spring Data JPA: projection query và một `@EntityGraph` giới hạn. Bật SQL count, tạo 50 nhóm, so sánh số query, số rows và độ trễ thay vì chỉ xem code ngắn dài.

**Bài E — Tenant.** Bổ sung `tenant_id` cho account và group, viết điều kiện để không có group membership xuyên tenant. Thử hai tenant cùng username, rồi thiết kế cache key và policy lookup phù hợp.

**Bài F — Nhóm lồng nhau.** Đề xuất closure cho nhóm A chứa B, B chứa C và C chứa A. Chỉ ra vì sao cần cycle detection, giới hạn độ sâu, và cách tránh traversal phát sinh N+1.

**Bài G — Authorization theo object.** User có `documents:write` nhưng tài liệu thuộc tenant khác. Thiết kế kiểm tra ở service/authorization policy để vẫn từ chối sửa tài liệu đó.

### Khi nào được coi là hoàn thành?

Bạn giải thích được: quyền trực tiếp và quyền nhóm được hợp thế nào, vì sao role và group không đồng nhất, N+1 nằm ở đâu, cách viết truy vấn tập hợp tránh số SELECT tăng theo N, cách đo SQL thật, cách trả `GrantedAuthority` trong `UserDetails`, và vì sao session/cache/token có thể giữ quyền đã bị thu hồi. Bạn chạy được demo và chứng minh user có quyền qua nhóm mà không bị tải từng nhóm một.

## 14. Tài liệu chính thức để đối chiếu

- [Spring Security — UserDetailsService](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details-service.html): nguồn tải user để provider kiểm tra.
- [Spring Security — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): cách provider dùng `UserDetails` và `PasswordEncoder`.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `GrantedAuthority` và `ProviderManager`.
- [Spring Security — Caching UserDetails](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/caching.html): `CachingUserDetailsService`, `@Cacheable` và vấn đề erase credentials.
- [Spring Security — UserDetails và CredentialsContainer](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/user-details.html): lưu/xóa thông tin nhạy cảm trong principal.
- [Spring Data JPA — Query Methods / EntityGraph](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): cách khai `@EntityGraph` và query method.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html): `GrantedAuthority`, vai trò và cơ chế kiểm tra quyền.

Các đoạn code chạy tập trung vào Spring Boot 3.5/Spring Security 6.5 và Java 17. Khi ứng dụng dùng Spring Security 7, JPA provider khác hoặc DB khác H2, hãy đối chiếu API, cách sinh SQL và kế hoạch thực thi của đúng phiên bản.