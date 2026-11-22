# Nâng cấp giá trị băm qua UserDetailsPasswordService

Trong ứng dụng **Spring Security Servlet**, mật khẩu của người dùng thường được lưu dưới dạng **giá trị băm mật khẩu có salt và thông số chi phí** (password hash), không phải mật khẩu rõ. Theo thời gian, chính sách băm thay đổi: thuật toán cũ không còn được ưu tiên, mức cost không đủ cao, hoặc hệ thống chuyển sang cách đánh dấu thuật toán mới như `{bcrypt}`. Một ứng dụng đang có người dùng thật cần nâng cấp các hash cũ mà **không biết lại mật khẩu gốc của từng người**.

Spring Security hỗ trợ mô hình **nâng cấp khi người dùng xác thực thành công** (opportunistic password rehashing) bằng cách phối hợp:

- `PasswordEncoder.matches(rawPassword, storedHash)`: xác minh mật khẩu người dùng vừa gửi với giá trị đang lưu.
- `PasswordEncoder.upgradeEncoding(storedHash)`: cho biết hash đang lưu có cần được nâng cấp theo chính sách của encoder hiện tại hay không.
- `PasswordEncoder.encode(rawPassword)`: tạo hash mới từ chính mật khẩu vừa được xác minh.
- `UserDetailsPasswordService.updatePassword(user, newEncodedPassword)`: ghi **hash mới**, không phải mật khẩu rõ, vào kho tài khoản.
- `DaoAuthenticationProvider`: thành phần có thể điều phối các bước trên sau khi quá trình xác thực mật khẩu thành công nếu đã được cấu hình `UserDetailsPasswordService`.

Đây **không phải** thao tác giải mã hash cũ và cũng không phải cách đặt lại mật khẩu khi người dùng quên mật khẩu. Bài học giải thích luồng xử lý, hợp đồng API, cấu hình Spring Security 6.x, ví dụ với JDBC, kiểm thử và những giới hạn về bảo mật, hiệu năng và cạnh tranh dữ liệu.

## 1. Vì sao cần nâng cấp hash?

Password hash có thể chứa thông tin nhận biết thuật toán và cost; ví dụ một chuỗi BCrypt thường có tiền tố dạng `$2a$10$...`, trong đó `10` thể hiện log2 cost. Với encoder dạng ủy quyền (`DelegatingPasswordEncoder`), dữ liệu lưu có thể bắt đầu bằng mã thuật toán, ví dụ `{bcrypt}$2a$10$...`.

Các tình huống cần nâng cấp:

| Tình huống | Giá trị đang lưu | Chính sách hiện tại | Điều mong muốn |
| --- | --- | --- | --- |
| Tăng BCrypt cost | BCrypt cost 8 | BCrypt cost 12 | Người đăng nhập thành công được ghi hash BCrypt cost 12 |
| Di chuyển thuật toán | `{pbkdf2}...` | Encoder hiện tại tạo `{bcrypt}...` hoặc thuật toán đã chọn khác | Xác minh bằng thuật toán cũ được cho phép, rồi ghi theo thuật toán mới |
| Bỏ định dạng di sản | Hash cũ không có `{id}` | Chuỗi mới có `{bcrypt}` | Có bộ xác minh di sản **được kiểm soát**, sau đó ghi hash có định dạng mới |
| Đã đạt chính sách | Hash dùng đúng thuật toán và cost hiện tại | Chính sách không thay đổi | Không ghi lại dữ liệu không cần thiết |
| Mật khẩu sai | Bất kỳ hash nào | Bất kỳ | Từ chối xác thực, **không nâng cấp** |
| Xác thực không qua password | OAuth2 SSO/JWT hoặc cơ chế khác | Password policy nội bộ | Không mặc định có plaintext để rehash; cần quy trình riêng |

Việc nâng cost phải dựa trên benchmark và khả năng chịu tải thực tế. Chi phí quá thấp làm tăng rủi ro brute-force khi DB bị lộ, còn cost quá cao có thể tạo điểm nghẽn CPU/độ trễ khi nhiều người đăng nhập đồng thời.

**Điều kiện tối quan trọng:** chỉ tạo hash mới từ **mật khẩu vừa được xác minh thành công**. Không tự sinh hash mới bằng cách gọi `encode(oldHash)`; hành động ấy biến chính chuỗi hash cũ thành “mật khẩu” và khiến mật khẩu thực không còn khớp.

## 2. Vai trò của từng API

| Thành phần | Hợp đồng hoặc phương thức | Trách nhiệm |
| --- | --- | --- |
| `UserDetailsService` | `loadUserByUsername(username)` | Nạp tài khoản, hash mật khẩu và authorities |
| `PasswordEncoder` | `matches(raw, encoded)` | Đối chiếu password được trình bày với hash lưu |
| `PasswordEncoder` | `upgradeEncoding(encoded)` | Quyết định có nên thay hash theo chính sách mới |
| `PasswordEncoder` | `encode(raw)` | Tạo hash mới từ mật khẩu rõ hiện có trong thời điểm xác thực |
| `UserDetailsPasswordService` | `updatePassword(user, newPassword)` | Lưu hash mới và trả về `UserDetails` phản ánh mật khẩu đã cập nhật |
| `DaoAuthenticationProvider` | Logic xác thực tài khoản qua DAO | Phối hợp service, encoder và việc thay password hash sau thành công |
| `AuthenticationManager` | `authenticate(...)` | Điều phối các provider xác thực tương ứng |
| `SecurityContext` | `setAuthentication(...)` | Giữ kết quả xác thực cho phạm vi xử lý, **không** phải nơi lưu hash |

Phương thức cốt lõi của interface `UserDetailsPasswordService`:

~~~java
// Hình dạng hợp đồng API của Spring Security:
public interface UserDetailsPasswordService {
    UserDetails updatePassword(UserDetails user, String newPassword);
}
~~~

Đây là **mã mô tả chữ ký interface**, cần các import `UserDetails` tương ứng nếu viết vào project; không phải class tự chạy. Tham số `newPassword` có tên dễ gây hiểu nhầm: trong luồng nâng cấp của `DaoAuthenticationProvider`, nó là **giá trị mật khẩu đã được encoder mã hóa/băm**, không phải raw password.

Cách triển khai service phải bảo đảm:

1. Ghi giá trị hash vào tài khoản chính xác, đúng username/ID trong kho lưu trữ.
2. Không thay authorities, trạng thái enabled, tenant hoặc metadata tài khoản ngoài ý muốn.
3. Trả `UserDetails` phù hợp sau cập nhật để provider có kết quả xác thực nhất quán.
4. Xử lý transaction, đồng thời, lỗi database và audit thay đổi nếu môi trường yêu cầu.
5. Không đưa raw password/hash ra log hoặc response.

## 3. Luồng tự động nâng cấp khi đăng nhập

Trong ứng dụng Servlet dùng username/password qua HTTP Basic hoặc form login với `DaoAuthenticationProvider`, luồng điển hình:

~~~text
HTTP request mang username + raw password
               |
               v
Authentication filter
               |
               v
AuthenticationManager -> DaoAuthenticationProvider
               |
               +--> UserDetailsService.loadUserByUsername(username)
               |       |
               |       +--> UserDetails.password = storedEncoded
               |
               +--> kiểm tra trạng thái account
               +--> PasswordEncoder.matches(rawPassword, storedEncoded)
                       |
              +--------+--------+
              |                 |
           false               true
              |                 |
              v                 v
       Xác thực thất bại     Xác thực thành công
       KHÔNG update hash         |
                                v
                     PasswordEncoder.upgradeEncoding(storedEncoded)
                          |                    |
                        false                 true
                          |                    |
                          v                    v
                     Giữ hash cũ      encode(rawPassword)
                                               |
                                               v
                           UserDetailsPasswordService.updatePassword(
                               user, newEncodedPassword)
                                               |
                                               v
                           Authentication thành công, sử dụng
                           UserDetails đã cập nhật phù hợp
~~~

Mô hình này áp dụng khi provider **được cấu hình** với `UserDetailsPasswordService`. Nếu chỉ khai báo bean encoder mà chưa kết nối password service vào provider, không thể mặc định quá trình login sẽ tự gọi `updatePassword(...)`.

Các điểm cần lưu ý:

- `matches(...)` chạy **trước** `upgradeEncoding(...)` trong quá trình quyết định nâng cấp; hash mới không được tạo cho password sai.
- Chỉ gọi `updatePassword(...)` khi encoder cho rằng nên nâng cấp (theo hành vi provider ở phiên bản đang sử dụng) và service nâng cấp đã được cấu hình.
- Dịch vụ cập nhật **hash**, không được nhận raw password để cất vào DB.
- Nếu người dùng đã có hash đáp ứng policy, login không cần ghi DB chỉ để đổi salt.
- Việc nâng cấp là **tác dụng phụ của một lần xác thực password thành công**; nó không phải job tự chạy để nâng cấp tất cả user không đăng nhập.

**Đừng nhầm nâng cấp hash với thay password:** password người dùng nhập vẫn như cũ; chỉ thuật toán/thông số/định dạng của hash lưu thay đổi. Với quy trình người dùng chủ động đổi mật khẩu, cần API thay password và kiểm tra quyền/credential riêng.

## 4. PasswordEncoder.upgradeEncoding hoạt động ra sao?

Interface `PasswordEncoder` định nghĩa `encode(...)`, `matches(...)` và phương thức mặc định `upgradeEncoding(...)`. Một implementation có thể dùng thông tin trong chuỗi đã lưu để xác định hash có đủ mới.

### 4.1. BCryptPasswordEncoder và mức strength

Ví dụ chính sách hiện tại:

~~~java
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

PasswordEncoder encoder = new BCryptPasswordEncoder(12);
~~~

Giả sử DB có BCrypt được tạo với cost 8 (ví dụ mở đầu bằng `$2a$08$...`). `BCryptPasswordEncoder(12)` có thể **xác minh** hash cũ vì hash chứa cost riêng, và `upgradeEncoding(oldHash)` có thể trả `true` vì cost cũ thấp hơn cost cấu hình.

Sau login hợp lệ, provider sẽ có cơ hội ghi hash mới có cost 12. Nếu hash đã ở cost 12 hoặc cao hơn, việc nâng cấp chỉ dựa trên cost thấp hơn thường không cần thiết; cũng không nên hạ cost chỉ vì thay cấu hình từ 12 xuống 10.

Ví dụ ý nghĩa:

~~~text
Đang lưu: bcrypt(cost=8)     -> policy bcrypt(cost=12) -> upgrade=true
Đang lưu: bcrypt(cost=12)    -> policy bcrypt(cost=12) -> upgrade=false
Đang lưu: bcrypt(cost=14)    -> policy bcrypt(cost=12) -> không hạ cost
Password nhập sai            -> không tới bước nâng cấp
~~~

Các dòng này là **mô tả ngữ nghĩa**, không phải output của một lệnh cụ thể. Cost 8 trong bài chỉ nhằm minh họa dữ liệu cũ; không khuyến nghị dùng cost thấp cho hệ thống thật. Cần chọn work factor dựa trên mức tải, độ trễ cho phép và hướng dẫn bảo mật hiện hành.

### 4.2. DelegatingPasswordEncoder và tiền tố {id}

`DelegatingPasswordEncoder` lưu thuật toán bằng tiền tố:

~~~text
{bcrypt}$2a$12$...
{pbkdf2}...
{argon2}...
~~~

Mô hình này giúp cơ chế xác thực nhận biết encoder phải dùng cho **giá trị cũ**, trong khi `encode(...)` sử dụng **idForEncode hiện tại**. Khi id của hash lưu không còn là id mới, `upgradeEncoding(...)` có thể báo cần nâng cấp. Khi id không đổi, encoder con có thể tiếp tục quyết định dựa trên thông số cost.

Ví dụ bean theo factory của Spring Security:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

Factory này chọn cấu hình thuật toán và cách lưu có prefix theo phiên bản Spring Security đang dùng; không mặc định giá trị cost cụ thể mà không kiểm tra version/bean thực tế.

**Định dạng phải thống nhất:**

- `BCryptPasswordEncoder` trực tiếp thường làm việc với hash BCrypt dạng `$2a$...` (không có prefix `{bcrypt}`).
- `DelegatingPasswordEncoder` sử dụng tiền tố `{id}` để định tuyến; với dữ liệu không có id, hành vi mặc định có thể từ chối do không biết encoder tương ứng.
- Khi di chuyển dữ liệu cũ không có tiền tố, có thể cấu hình một fallback decoder **chỉ trong giai đoạn migration và chỉ cho định dạng thật sự tin cậy**, hoặc buộc reset password. Không tùy tiện chấp nhận `{noop}` hay plaintext như một “giải pháp” cho production.
- Không sửa trực tiếp tiền tố của hash mà chưa kiểm tra body có đúng định dạng thuật toán được khai báo. Thay `{sha256}` bằng `{bcrypt}` không biến dữ liệu SHA-256 thành BCrypt.

### 4.3. Không đủ thông tin thì không thể tái băm

Hash là phép biến đổi một chiều, không thể lấy lại password rõ từ stored hash để tạo hash mới. Vì vậy việc rehash lười theo login chỉ xảy ra **khi người dùng gửi lại mật khẩu đúng**. Với tài khoản lâu không đăng nhập, cần phương án chính sách: chờ login lần sau, bắt buộc đổi/reset mật khẩu, hoặc ngưng hỗ trợ hash di sản sau thời hạn công bố.

Nếu đã tắt hoàn toàn bộ xác minh thuật toán cũ, những user còn hash cũ sẽ không thể đăng nhập để tự nâng cấp. Kế hoạch migration phải tính tới **cửa sổ tương thích có giới hạn**, thống kê số user chưa nâng cấp và luồng reset an toàn.

## 5. UserDetailsPasswordService liên quan gì đến UserDetailsService?

Hai interface có tên tương tự nhưng có nhiệm vụ khác:

~~~text
UserDetailsService
    loadUserByUsername(username)
            -> UserDetails gồm encoded password

UserDetailsPasswordService
    updatePassword(user, newEncodedPassword)
            -> ghi hash mới, trả UserDetails đã cập nhật
~~~

Một class có thể triển khai cả hai; ví dụ `JdbcUserDetailsManager` của Spring Security có thể làm nguồn đọc tài khoản và cung cấp hành vi cập nhật password khi cấu hình tương thích với schema/query.

Nếu ứng dụng dùng `JpaRepository` hoặc domain service riêng, có thể tạo adapter triển khai `UserDetailsPasswordService`. Ví dụ **fragment khái niệm**, không có mã JPA repository cụ thể:

~~~java
@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String newEncodedPassword) {
    Account account = repository.findByUsername(user.getUsername())
            .orElseThrow(() -> new UsernameNotFoundException(
                    "Account no longer exists"));

    account.setPasswordHash(newEncodedPassword);
    repository.save(account);

    return User.withUserDetails(user)
            .password(newEncodedPassword)
            .build();
}
~~~

Ở đây `Account`, `repository`, `@Transactional` và các import là thành phần **của dự án**, không phải class độc lập. Việc dùng `User.withUserDetails(...)` thích hợp nếu dữ liệu UserDetails và authority có thể được biểu diễn đầy đủ bằng builder này; nếu ứng dụng có custom principal chứa thông tin chuyên biệt, hãy trả về loại `UserDetails` giữ nguyên các thuộc tính cần thiết.

Bảo đảm service không bỏ qua tenant boundary. Khi username có thể trùng giữa các tenant, cần khóa định danh bất biến hoặc điều kiện tenant đã được xác thực; chỉ dùng `WHERE username=?` có thể cập nhật nhầm người.

### Tại sao phải trả về UserDetails?

`UserDetailsPasswordService.updatePassword(...)` trả về `UserDetails` để provider có thể tiếp tục với user phản ánh mật khẩu mới và dữ liệu account nhất quán. Trả object giữ hash cũ sau khi đã ghi DB có thể làm kết quả xử lý/caching không đồng nhất. Trả `null` trái với kỳ vọng hoạt động và có thể gây lỗi trong lần xác thực.

Không đổi username, authorities, trạng thái enabled hoặc các cờ account chỉ để cập nhật hash. Nếu cần đồng thời cập nhật policy/state khác, đó là quyết định nghiệp vụ riêng, có transaction và test rõ ràng.

## 6. Ví dụ thực tế: Spring Boot + H2 + JdbcUserDetailsManager

Mục tiêu của ví dụ: tạo một tài khoản demo với **BCrypt cost 8 (di sản)**, cấu hình policy hiện tại **BCrypt cost 12**, đăng nhập qua HTTP Basic, sau đó quan sát cột password trong bảng `users` được nâng lên hash cost 12.

Đây là mã cho **Spring Boot 3.x / Spring Security 6.x / Java 17+**; cần classpath Spring, H2 và Maven. Đoạn Spring **không biên dịch chỉ bằng `javac` JDK trống**. Constructor và API của `DaoAuthenticationProvider` có thay đổi/deprecation giữa các phiên bản 6.x; ví dụ dùng cách cấu hình truyền thống phổ biến cho Spring Security 6.x và cần điều chỉnh nếu dự án khóa phiên bản khác.

### 6.1. Dependencies trong Maven

Trong `pom.xml` của project Spring Boot đã có parent/BOM phù hợp, cần những dependency sau:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
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
~~~

Không tự ghép các version Spring Security khác với BOM của Spring Boot. Với các bản Spring Boot mới, package test/autoconfiguration có thể thay đổi; điều chỉnh import đúng phiên bản.

### 6.2. Lược đồ JDBC mặc định

Tạo `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE users (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(50) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_auth_user FOREIGN KEY (username) REFERENCES users(username),
    CONSTRAINT uq_auth UNIQUE (username, authority)
);
~~~

Hai bảng tương thích với lookup user và authorities thông thường của `JdbcUserDetailsManager`. Password hash cần cột đủ dài cho định dạng có prefix, BCrypt, Argon2 hoặc thuật toán được chọn. Nếu schema production khác (ví dụ cột `password_hash`), phải cấu hình **cả truy vấn đọc lẫn cập nhật password** đúng schema, không chỉ sửa câu SELECT.

Tạo `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:password_upgrade_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

H2 in-memory chỉ phục vụ học tập; không dùng làm cơ sở dữ liệu tài khoản production. Môi trường thật phải dùng migration versioned, kiểm soát truy cập DB, TLS khi thích hợp và kế hoạch backup.

### 6.3. Class Spring Boot

Tạo `src/main/java/com/example/demo/PasswordUpgradeApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PasswordUpgradeApplication {
    public static void main(String[] args) {
        SpringApplication.run(PasswordUpgradeApplication.class, args);
    }
}
~~~

### 6.4. Bean encoder, JDBC manager và DaoAuthenticationProvider

Tạo `src/main/java/com/example/demo/PasswordUpgradeConfig.java`:

~~~java
package com.example.demo;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PasswordUpgradeConfig {

    @Bean
    JdbcUserDetailsManager users(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(12); // Chính sách MỚI.
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            JdbcUserDetailsManager users,
            PasswordEncoder encoder) throws Exception {

        DaoAuthenticationProvider provider = new DaoAuthenticationProvider();
        provider.setUserDetailsService(users);
        provider.setPasswordEncoder(encoder);

        // Đây là kết nối quan trọng cho bước nâng cấp sau xác thực:
        provider.setUserDetailsPasswordService(users);

        http.authenticationProvider(provider)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    CommandLineRunner seedLegacyAccount(JdbcUserDetailsManager users) {
        return args -> {
            String password = System.getenv("DEMO_PASSWORD");
            if (password == null || password.isBlank()) {
                return; // Không tạo tài khoản với mật khẩu mặc định.
            }

            // CỐ Ý tạo hash cost thấp chỉ để quan sát nâng cấp.
            PasswordEncoder oldEncoder = new BCryptPasswordEncoder(8);
            if (!users.userExists("alice")) {
                users.createUser(User.withUsername("alice")
                    .password(oldEncoder.encode(password))
                    .roles("USER")
                    .build());
            }
        };
    }
}
~~~

**Điểm cốt lõi của cấu hình:**

1. `JdbcUserDetailsManager` cung cấp `UserDetailsService` và khả năng lưu mật khẩu cập nhật theo interface `UserDetailsPasswordService`.
2. `DaoAuthenticationProvider` xác minh password với bean `BCryptPasswordEncoder(12)`.
3. `provider.setUserDetailsPasswordService(users)` cho provider biết cách **ghi hash mới**.
4. Tài khoản demo Alice ban đầu có hash BCrypt cost 8 nhưng vẫn xác minh được bằng encoder cost 12.
5. Khi Alice đăng nhập **thành công**, provider có thể rehash bằng cost 12, gọi `users.updatePassword(...)` rồi tiếp tục tạo kết quả xác thực.
6. Khi password sai, hash không được nâng cấp. Khi đã đạt cost 12, login tiếp theo thông thường không cần cập nhật.

Khai báo bean `JdbcUserDetailsManager` và `PasswordEncoder` không đủ nếu provider thực tế dùng để xác thực là provider khác hoặc chưa được kết nối password service. Trong một ứng dụng có nhiều provider, chain, filter, SSO hoặc JWT, cần xác định **provider nào thật sự xử lý credential**.

**Giới hạn version:** `DaoAuthenticationProvider()` và `setUserDetailsService(...)` có thể bị đánh dấu deprecated ở những bản Spring Security 6.x mới. Nếu thư viện hỗ trợ constructor nhận `UserDetailsService`, có thể dùng constructor đó và bỏ setter. Chỉ thay cú pháp khởi tạo provider, không thay ý nghĩa của `setPasswordEncoder(...)` hay `setUserDetailsPasswordService(...)`.

### 6.5. Endpoint để quan sát login

Tạo `src/main/java/com/example/demo/WhoAmIController.java`:

~~~java
package com.example.demo;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return "Hello, " + principal.getName();
    }
}
~~~

`/me` được bảo vệ bằng `authenticated()`, do đó khi request vào controller với cấu hình minh họa, principal hợp lệ đã được xác thực. Endpoint công khai không đụng tới principal.

### 6.6. Chạy demo và kiểm tra database

Sau khi thiết lập project/Maven wrapper và JDK phù hợp, ở máy thử nghiệm Unix-like:

~~~bash
export DEMO_PASSWORD='only-local-demo-password'
./mvnw spring-boot:run
~~~

Đây là password **giả chỉ dùng cho phát triển**. Trên môi trường thật không khai báo password qua command line/history như ví dụ, không cấp tài khoản demo cố định, và tuyệt đối không copy password production vào file bài học.

Gửi request trước khi đăng nhập:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
~~~

Dự kiến `/public` thường trả `200` và `/me` không có credentials thường trả `401` với HTTP Basic challenge. Sau đó:

~~~bash
curl -i -u alice http://localhost:8080/me
~~~

`curl` sẽ yêu cầu nhập password qua prompt; nhập đúng mật khẩu bạn đã thiết lập lúc seed. Với cấu hình thành công, response thường là HTTP 200 và body `Hello, alice`.

Kiểm tra cột mật khẩu trong H2 bằng một công cụ SQL được cấp quyền:

~~~sql
SELECT username, password, enabled
FROM users
WHERE username = 'alice';
~~~

Trước lần đăng nhập hợp lệ, hash của Alice có dạng BCrypt cost 8, thường thấy chuỗi có `$08$` trong phần tiền tố BCrypt; sau lần đăng nhập hợp lệ, hash mới thường có cost 12 (`$12$`). Dữ liệu hash thực tế khác mỗi lần do salt ngẫu nhiên; **không có một chuỗi output cố định để sao chép**.

Trong production, không đưa hash lên dashboard/log công khai. Khi kiểm thử, tốt hơn chỉ truy vấn trạng thái/định dạng qua integration test trong môi trường cách ly; nếu phải đọc hash thực, giới hạn quyền và vòng đời dữ liệu.

## 7. Kiểm thử tự động giá trị hash trước và sau login

Trong cùng dự án có `spring-boot-starter-test`, `spring-security-test`, `JdbcUserDetailsManager` và `JdbcTemplate`, một test tích hợp có thể tạo user với hash cost thấp rồi thực hiện HTTP Basic thật qua `MockMvc`.

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.JdbcUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PasswordUpgradeIntegrationTest {

    @Autowired MockMvc mvc;
    @Autowired JdbcUserDetailsManager users;
    @Autowired JdbcTemplate jdbc;
    @Autowired PasswordEncoder encoder;

    private String stored(String name) {
        return jdbc.queryForObject(
            "SELECT password FROM users WHERE username = ?",
            String.class,
            name
        );
    }

    @Test
    void successfulLoginUpgradesHashButWrongPasswordDoesNot()
            throws Exception {

        String username = "upgrade-test-user";
        String raw = "test-only-password";
        String legacyHash = new BCryptPasswordEncoder(8).encode(raw);

        if (users.userExists(username)) {
            users.deleteUser(username);
        }
        users.createUser(User.withUsername(username)
            .password(legacyHash)
            .roles("USER")
            .build());

        String before = stored(username);
        assertEquals(legacyHash, before);
        assertTrue(encoder.matches(raw, before));
        assertTrue(encoder.upgradeEncoding(before));

        // Password SAI không được ghi hash mới.
        mvc.perform(get("/me").with(httpBasic(username, "incorrect")))
            .andExpect(status().isUnauthorized());
        assertEquals(before, stored(username));

        // Password ĐÚNG: provider kiểm tra rồi lưu hash mới.
        mvc.perform(get("/me").with(httpBasic(username, raw)))
            .andExpect(status().isOk());

        String after = stored(username);
        assertNotEquals(before, after);
        assertTrue(encoder.matches(raw, after));
        assertFalse(encoder.upgradeEncoding(after));

        // Login tiếp với hash đã đạt chính sách.
        mvc.perform(get("/me").with(httpBasic(username, raw)))
            .andExpect(status().isOk());
        assertEquals(after, stored(username));
    }
}
~~~

Test dùng password giả, H2 in-memory và account riêng. Nó xác minh **database thực sự đổi** sau login qua provider, thay vì chỉ chứng minh một lần gọi `PasswordEncoder.encode(...)` có thể tạo hash mới. Các assertion dựa trên cấu hình demo: một provider phù hợp, `BCryptPasswordEncoder(12)`, password service được gắn và request HTTP Basic được đưa qua Spring Security filter.

Nếu môi trường khác có provider riêng hoặc các event xử lý login thay đổi, test cần điều chỉnh. Nếu Spring Security có cache user details, phải xác minh đường cập nhật/cách vô hiệu hóa cache và kết quả authentication vẫn nhất quán sau thay hash.

### Kiểm thử nhiều trường hợp khác

| Case | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Password sai | Raw credential không khớp | Không ghi hash; lỗi xác thực |
| User disabled/locked | Tài khoản không hợp lệ theo chính sách | Không nâng cấp như một login thành công |
| Hash cost thấp | Credential đúng, service hoạt động | Ghi hash mới đạt policy |
| Hash đã đạt policy | Credential đúng | Không cập nhật không cần thiết |
| Kho dữ liệu chỉ đọc | Credential đúng nhưng update bị từ chối | Xử lý lỗi có chủ đích, không tuyên bố đã nâng cấp |
| Đổi thuật toán | Old encoder còn xác minh được, policy mới khác | Chuyển định dạng sau login; test compatibility |
| Login cạnh tranh | Hai request cùng dùng password cũ | Không làm mất thay đổi password/quyền xảy ra đồng thời |
| Password reset | Người dùng không cung cấp password cũ hợp lệ | Dùng quy trình reset, không giả làm upgrade tự động |

Một unit test chỉ giả lập `@WithMockUser` **không kích hoạt DaoAuthenticationProvider xác minh password thật**, nên không kiểm tra được đường đi nâng cấp hash. Cần integration test qua credential thực hoặc test riêng provider với `UserDetailsPasswordService` giả lập có ghi nhận số lần gọi.

## 8. Java 17 độc lập: mô phỏng quyết định nâng cấp

Để hiểu thứ tự **xác minh → xét cần nâng cấp → ghi hash mới**, có thể dùng chương trình Java 17 thuần sau. Nó **không băm mật khẩu thật, không xác thực user**: các cờ `passwordVerified` giả định kết quả đã có từ một password verifier đáng tin cậy. Điều này cố tình giữ ví dụ không thể bị nhầm là một thuật toán password hashing để dùng trong production.

Lưu tệp `PasswordUpgradeDecisionDemo.java`:

~~~java
public class PasswordUpgradeDecisionDemo {
    record Account(String username, int storedCost) {}

    static String login(Account user, boolean passwordVerified, int policyCost) {
        if (!passwordVerified) {
            return user.username() + " -> rejected; hash unchanged";
        }
        if (user.storedCost() < policyCost) {
            return user.username() + " -> upgrade "
                    + user.storedCost() + " to " + policyCost;
        }
        return user.username() + " -> accepted; hash unchanged";
    }

    public static void main(String[] args) {
        System.out.println(login(new Account("alice", 8), true, 12));
        System.out.println(login(new Account("bob", 8), false, 12));
        System.out.println(login(new Account("carol", 12), true, 12));
        System.out.println(login(new Account("dave", 14), true, 12));
    }
}
~~~

Lệnh biên dịch/chạy:

~~~bash
javac PasswordUpgradeDecisionDemo.java
java PasswordUpgradeDecisionDemo
~~~

Stdout chính xác:

~~~text
alice -> upgrade 8 to 12
bob -> rejected; hash unchanged
carol -> accepted; hash unchanged
dave -> accepted; hash unchanged
~~~

Ở hệ thống Spring Security, `PasswordEncoder.matches(...)` đưa ra kết quả xác minh thực; `upgradeEncoding(...)` đánh giá thuật toán/cost thực thay vì chỉ so sánh số nguyên; `UserDetailsPasswordService.updatePassword(...)` mới ghi encoded password sau khi xác thực thành công. Mô hình thuần Java trên giúp hình dung nhánh quyết định, **không thay thế BCrypt/Argon2/PBKDF2**.

## 9. Nếu không dùng JDBC: triển khai service ghi hash có trách nhiệm

Một ứng dụng có thể giữ tài khoản trong JPA, MongoDB, service nội bộ hoặc kho khác. Cần adapter đưa logic ghi hash vào `UserDetailsPasswordService` với **khóa định danh đáng tin cậy** và quyền ghi phù hợp. Mẫu service ứng dụng:

~~~java
// Fragment minh họa bên trong bean@Service đã được thiết kế đầy đủ.
@Override
@Transactional
public UserDetails updatePassword(UserDetails user, String encodedPassword) {
    Account account = accountRepository.findByLogin(user.getUsername())
        .orElseThrow(() -> new UsernameNotFoundException(
            "Account unavailable"));

    account.setPasswordHash(encodedPassword);
    accountRepository.save(account);

    return User.withUserDetails(user)
        .password(encodedPassword)
        .build();
}
~~~

Đây là **pseudo-real fragment**: `Account`/repository là kiểu domain tự định nghĩa; import và transaction configuration phải bổ sung. Trong hệ thống nhiều tenant hoặc liên kết nhiều username, tìm account bằng `user.getUsername()` có thể chưa đủ an toàn. Cần identifier đã được kiểm tra, tenant boundary và cơ chế concurrency thích hợp.

### Đồng thời và cập nhật password khác

Hai login của cùng user có thể cùng thấy hash cũ, cùng tạo hai hash mới khác nhau do salt. Nếu cả hai dùng cùng password hợp lệ, việc hash mới ghi đè nhau thường không làm mật khẩu mất hiệu lực, nhưng vẫn tạo ghi DB không cần thiết. Nguy hiểm hơn:

1. Request A xác minh password cũ.
2. Request B chủ động **đổi/reset mật khẩu** sang giá trị khác.
3. Request A dùng dữ liệu user cũ và ghi “hash nâng cấp” của password cũ đè lên hash mới.

Điều này có thể làm password cũ sống lại. Nên thiết kế cập nhật có **optimistic concurrency**:

~~~sql
UPDATE users
SET password = ?
WHERE username = ?
  AND password = ?;
~~~

Trong đó các tham số lần lượt là `newEncodedPassword`, `username` và **oldEncodedPassword** đã được đọc trước đó. Nếu số hàng cập nhật bằng 0, dữ liệu đã thay đổi; **không ghi đè vô điều kiện**. Đây là chiến lược SQL tham khảo, không phải truy vấn mặc định được cam kết của `JdbcUserDetailsManager`. Với database có version column, có thể dùng `WHERE id=? AND version=?`. Nếu dùng `JdbcUserDetailsManager` với SQL cập nhật đơn giản, phải đánh giá yêu cầu cạnh tranh và bổ sung lớp cập nhật riêng nếu nghiệp vụ đòi hỏi chống stale write.

Không nên phát ra một response “đăng nhập thành công, hash đã được nâng cấp” nếu cập nhật DB thất bại; trạng thái xác thực và khả năng retry cần theo chính sách ứng dụng, có logging/audit an toàn và test đầy đủ.

### Chú ý cache của UserDetailsService

Một provider hoặc ứng dụng có thể cache `UserDetails`. Sau khi hash thay đổi trong DB, cache phải được cập nhật hoặc vô hiệu hóa phù hợp. Nếu cache còn hash cũ, authentication sau đó có thể gặp hành vi khó hiểu hoặc rehash lặp lại. Đừng giả định mọi lần login đều truy vấn lại database; hãy xác định `UserCache` thực tế và các tầng cache riêng.

## 10. Nâng cấp hash theo chiến lược migration

Một migration thành công không chỉ đổi bean `PasswordEncoder`:

### Bước 1: Kiểm kê dữ liệu

Xác định thuật toán, cost, tiền tố `{id}` và phần trăm tài khoản theo từng định dạng; tránh ghi lại toàn bộ hash/secret vào log. Nếu DB cũ chứa plaintext hoặc hash yếu, coi đây là vấn đề bảo mật cần giải quyết bằng kế hoạch chuyển đổi chặt chẽ và có thể bắt buộc reset.

### Bước 2: Chọn chính sách mới và khả năng tương thích

Lập benchmark password hashing (CPU, memory, số lần login đồng thời) trên hạ tầng thật. Chọn encoder mới an toàn, có tham số thích hợp. Giữ bộ xác minh di sản **chỉ với các định dạng cụ thể** trong thời hạn di chuyển. Không tạo cấu hình “bất kỳ hash nào cũng khớp” hoặc fallback bỏ xác minh password.

### Bước 3: Kết nối provider và password service

Xác định provider nào nhận username/password. Nối encoder mới và `UserDetailsPasswordService` vào đúng `DaoAuthenticationProvider`; kiểm tra đường đi xác thực thành công đã gọi service và lưu hash mới. Nếu nhiều phương thức login, không nhầm OIDC/JWT/SSO với password authentication trong DB.

### Bước 4: Kiểm thử trước khi triển khai

Test login sai, đúng, disabled, hash cũ, hash mới, concurrency, DB failure, cache và quyền ứng dụng. Trong môi trường thử nghiệm, kiểm tra format hash sau login bằng truy vấn giới hạn; không in mật khẩu rõ.

### Bước 5: Quan sát và hoàn tất

Theo dõi **số lượng tài khoản còn dùng định dạng cũ** và tỷ lệ thất bại của quá trình upgrade, không thu thập credentials. Sau một giai đoạn, người dùng không login cần reset password hoặc chiến lược vận hành khác. Chỉ gỡ bỏ bộ xác minh di sản khi đã có phương án cho các user còn lại.

### Bước 6: Chuẩn bị rollback

Nếu phát hiện lỗi sau khi phát hành hash mới, rollback code không thể đơn giản dùng encoder **chỉ hiểu hash cũ**. Khi lập kế hoạch triển khai, bảo đảm phiên bản ứng dụng rollback có thể xác minh cả định dạng cũ và mới, hoặc có lộ trình khôi phục có kiểm soát. **Không downgrade hash** để phục vụ rollback.

## 11. Các nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao không đúng | Cách xử lý |
| --- | --- | --- |
| “Chỉ cần đổi bean BCrypt từ 8 lên 12, DB tự cập nhật” | Chưa chắc provider có `UserDetailsPasswordService` | Kết nối service, test hash trước/sau login |
| “Có thể decode hash cũ để encode lại mà không cần login” | Hash mật khẩu một chiều | Chờ login hợp lệ hoặc bắt buộc reset |
| “PasswordEncoder.encode(oldHash) là nâng cấp” | Hash cũ không phải raw password | Chỉ encode password vừa được xác minh |
| “Hash mới phải giống nhau nếu password giống nhau” | BCrypt có salt ngẫu nhiên | Dùng `matches(...)`, không so sánh chuỗi hash |
| “Sai password cũng nên nâng cấp” | Không có bằng chứng password đúng | Không đổi hash khi xác thực thất bại |
| “UserDetailsPasswordService cần raw password” | Interface nhận encoded password để lưu | Không truyền raw password vào repository/log |
| “Nâng cấp hash là đổi mật khẩu người dùng” | Password vẫn như cũ | Phân biệt update hash với reset/change |
| “DelegatingPasswordEncoder luôn hiểu hash không có {id}” | Có thể không biết encoder phù hợp | Thiết kế fallback di sản an toàn hoặc reset |
| “Cứ giảm cost thì dữ liệu nên downgrade” | Hạ cost làm giảm sức chống brute-force | Không downgrade; đánh giá chính sách |
| “DaoAuthenticationProvider luôn được gọi ở mọi lần SSO/JWT” | Mỗi cơ chế có provider/filter khác | Kiểm tra đường xác thực thực tế |
| “Một login thành công chứng minh DB đã cập nhật” | Có thể thiếu service hoặc update lỗi | Kiểm tra hash trước/sau bằng integration test |
| “Nâng cấp hash luôn race-safe” | Đổi password đồng thời có thể bị stale write | Optimistic locking/conditional update |
| “Hash đủ mạnh thì không cần giới hạn đăng nhập” | Brute-force online khác offline | Rate limiting, MFA, giám sát, chống enumeration |
| “Hết support hash cũ ngay sau deploy là an toàn” | User dormant có thể mất khả năng login | Lộ trình chuyển đổi và reset có kiểm soát |

## 12. Bài tập tự kiểm tra

**Bài 1.** User Alice lưu BCrypt cost 8, ứng dụng dùng `BCryptPasswordEncoder(12)`. Alice đăng nhập đúng mật khẩu qua provider đã kết nối `UserDetailsPasswordService`. Điều gì có thể xảy ra?

**Đáp án:** Provider xác minh raw password với hash cost 8; encoder cho biết cần nâng cấp; provider tạo hash cost 12 từ raw password, gọi service cập nhật hash và hoàn tất xác thực. Password Alice nhập không thay đổi.

**Bài 2.** Alice nhập sai password vào cùng tài khoản. Có nên gọi `updatePassword(...)` không?

**Đáp án:** Không. Password chưa được xác minh; không được dùng giá trị sai hoặc hash cũ để tạo stored hash mới.

**Bài 3.** Dữ liệu đang là `{pbkdf2}...`, encoder mới sinh `{bcrypt}...`. Khi nào dữ liệu có thể di chuyển?

**Đáp án:** Khi cấu hình vẫn xác minh hợp lệ hash PBKDF2 di sản; một lần login bằng password đúng có thể tạo hash BCrypt mới và ghi lại thông qua password service. Nếu thuật toán cũ đã bị tắt, người dùng phải đi theo luồng reset/di chuyển khác.

**Bài 4.** `JdbcUserDetailsManager` đã được cấu hình cho login, nhưng sau mỗi lần đăng nhập đúng hash không đổi. Hai khả năng cần kiểm tra đầu tiên?

**Đáp án:** Có thể `upgradeEncoding(storedHash)` trả false vì hash đã đạt policy; hoặc provider thực tế chưa được nối `UserDetailsPasswordService` / đang dùng provider khác. Kiểm tra bean, đường authentication, trạng thái encoder và integration test.

**Bài 5.** Vì sao đoạn `UPDATE users SET password=? WHERE username=?` có thể chưa đủ trong trường hợp password reset đồng thời?

**Đáp án:** Một lần login đã xác minh password cũ có thể ghi hash cũ được nâng cấp **sau** khi reset đã đổi password. Cần conditional update/optimistic locking hoặc chính sách concurrency tương đương để không ghi đè thay đổi mới.

**Bài 6.** Hash BCrypt được encode lại sau login và chuỗi hash hoàn toàn khác, nhưng user vẫn đăng nhập bằng password cũ. Đây có phải lỗi?

**Đáp án:** Không. Salt khác tạo hash khác; verifier vẫn phải `matches(raw, newHash) = true`. Điều này chính là kết quả hợp lệ của rehash.

**Bài 7.** Đã nâng toàn bộ hash của user hoạt động, nhưng tài khoản không đăng nhập nhiều năm còn hash cũ. Có thể gọi `UserDetailsPasswordService.updatePassword(...)` với giá trị hash cũ để tự hoàn tất không?

**Đáp án:** Không. Phải có raw password đúng hoặc tiến hành quy trình đặt lại password an toàn. Không encode hash cũ thay cho password.

## 13. Checklist áp dụng

- [ ] Xác định định dạng/cost hash **đang lưu** và chính sách encoder **mới**.
- [ ] Đảm bảo `PasswordEncoder.matches(...)` còn hiểu những định dạng cũ cần hỗ trợ trong giai đoạn migration.
- [ ] Kiểm thử `upgradeEncoding(...)` cho hash cũ, hash mới và trường hợp không hợp lệ.
- [ ] Xác định đúng `DaoAuthenticationProvider` xử lý login; kết nối `UserDetailsPasswordService` vào provider.
- [ ] Service chỉ ghi **encoded password**, trả về `UserDetails` nhất quán và giữ nguyên các thuộc tính khác.
- [ ] Thiết kế transaction, optimistic update, cache invalidation và xử lý DB failure theo nghiệp vụ.
- [ ] Kiểm thử login sai **không ghi**, login đúng **nâng cấp**, login tiếp theo **không ghi lại**.
- [ ] Không lưu/log raw password, hash, token hoặc credential; kiểm soát quyền đọc DB.
- [ ] Đánh giá work factor và rate limiting để tránh gây nghẽn xác thực khi tăng cost.
- [ ] Có phương án cho dormant account, rollback tương thích và loại bỏ thuật toán cũ đúng lộ trình.
- [ ] Phân biệt hash migration với reset/change password và với cơ chế OAuth2/SSO/JWT.

**Kết luận:** `UserDetailsPasswordService` là **khâu ghi lại giá trị băm mật khẩu đã nâng cấp**, còn việc xác minh, quyết định nâng cấp và tạo hash mới nằm trong sự phối hợp của `DaoAuthenticationProvider` và `PasswordEncoder`. Cơ chế chỉ có ý nghĩa khi người dùng **vừa xác thực thành công bằng password** và provider đã được kết nối service cập nhật; ứng dụng vẫn phải bảo đảm schema, tương thích định dạng, concurrency và kế hoạch migration.