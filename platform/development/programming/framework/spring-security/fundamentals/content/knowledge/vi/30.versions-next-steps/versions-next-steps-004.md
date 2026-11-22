# WebSecurityConfigurerAdapter, API matcher cũ và Lambda DSL hiện đại

> **Phạm vi:** cấu hình bảo mật HTTP cho ứng dụng **Servlet / Spring MVC** bằng Spring Security. Bài này không dùng cấu hình WebFlux (`SecurityWebFilterChain`). Mục tiêu là đọc được mã bảo mật đời cũ, di chuyển sang cấu hình dựa trên bean và tránh thay đổi chính sách truy cập trong quá trình nâng phiên bản.

## 1. Tại sao cách cấu hình thay đổi?

Trước đây ứng dụng thường tạo lớp kế thừa `WebSecurityConfigurerAdapter`, rồi ghi đè `configure(HttpSecurity)`, `configure(WebSecurity)` hoặc `configure(AuthenticationManagerBuilder)`. Cách này gom nhiều trách nhiệm vào một lớp kế thừa và dễ làm người đọc nhầm giữa “yêu cầu nào đi qua bộ lọc bảo mật” với “người dùng nào được phép truy cập”.

Cấu hình hiện đại dùng các bean có trách nhiệm rõ ràng:

- **`SecurityFilterChain`**: mô tả bộ lọc và quy tắc HTTP; tạo bằng `HttpSecurity` rồi gọi `http.build()`.
- **`UserDetailsService` / `AuthenticationProvider` / `PasswordEncoder`**: cung cấp cách nạp người dùng và xác thực phù hợp nhu cầu.
- **`AuthenticationManager`**: chỉ cần công khai thành bean khi một thành phần khác thực sự phải tiêm hoặc gọi nó.
- **`WebSecurityCustomizer`**: cấu hình mức `WebSecurity`, đặc biệt là yêu cầu bỏ qua hoàn toàn filter chain; chỉ dùng có chủ đích.

Cách cấu hình lambda diễn đạt cùng một chính sách bằng các khối con nằm trong `HttpSecurity`; sau mỗi lời gọi lambda, luồng cấu hình quay lại đối tượng `HttpSecurity`, không cần `.and()`.

### Các mốc phiên bản cần nhận diện

| Phiên bản | Ý nghĩa khi đọc/migrate mã |
| --- | --- |
| Spring Security 5.4 | Đã hỗ trợ tự khai báo bean `SecurityFilterChain`. |
| Spring Security 5.7 | `WebSecurityConfigurerAdapter` bị đánh dấu deprecated; Spring khuyến nghị cấu hình theo component. |
| Spring Security 5.8 | Bước đệm có nhiều API để chuẩn bị nâng lên 6.x. |
| Spring Security 6.0 | Loại bỏ `WebSecurityConfigurerAdapter`; API DSL `antMatchers`, `mvcMatchers` cũ cần được chuyển sang `requestMatchers`/matcher phù hợp. |
| Spring Security 6.x | Dùng `authorizeHttpRequests` + Lambda DSL; các kiểu chain cũ và nhiều lời gọi cấu hình không lambda được đánh dấu bỏ dần. |
| Spring Security 7.0 | Lambda DSL là kiểu cấu hình bắt buộc; bỏ kiểu chaining `.and()` và `authorizeRequests`. `AntPathRequestMatcher`/`MvcRequestMatcher` không còn được hỗ trợ; matcher đường dẫn mặc định hướng tới `PathPatternRequestMatcher`. |

**Không suy ra phiên bản chỉ từ đoạn code.** Xem phiên bản được quản lý trong Maven/Gradle và dependency thực tế. Khi nâng Spring Boot, đối chiếu cả phiên bản Spring Security đi kèm. Ví dụ ứng dụng minh họa ở phần 5 cố định vào Spring Boot 3.3.0 (nhánh Spring Security 6.x), còn ghi chú về 7.x là hướng di chuyển API.

## 2. Nhận diện cấu hình kiểu cũ

Ví dụ **lịch sử cho Spring Security 5.x**, chỉ để hiểu cú pháp; không biên dịch lại nguyên trạng trên Spring Security 6/7:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter;

@Configuration
@EnableWebSecurity
public class LegacySecurityConfig extends WebSecurityConfigurerAdapter {

    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers(HttpMethod.GET, "/api/items/**").hasAnyRole("USER", "ADMIN")
                .antMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .httpBasic();
    }
}
```

Đọc từ trên xuống: đường dẫn `/public/**` được phép truy cập công khai; `GET /api/items/**` yêu cầu role USER hoặc ADMIN; `/api/admin/**` yêu cầu ADMIN; các yêu cầu còn lại chỉ cần đăng nhập. `httpBasic()` bật xác thực HTTP Basic để ví dụ API có cách gửi thông tin đăng nhập. Cú pháp `.and()` đưa quá trình cấu hình từ `authorizeRequests()` trở về `HttpSecurity`.

Đoạn mã cũ **không có nghĩa** mọi matcher cũ đều là một API duy nhất:

- `authorizeRequests().antMatchers(...)`: chỉ định quy tắc **phân quyền HTTP** theo mẫu Ant.
- `authorizeRequests().mvcMatchers(...)`: dùng ngữ nghĩa matcher tích hợp Spring MVC của phiên bản cũ.
- `authorizeRequests().regexMatchers(...)`: dùng biểu thức chính quy ở DSL cũ.
- `http.antMatcher(...)`/`http.mvcMatcher(...)` (lịch sử): giới hạn **phạm vi một filter chain**, khác mục đích phân quyền bên trong chain.
- `web.ignoring().antMatchers(...)`: loại yêu cầu ra **khỏi toàn bộ Spring Security filter chain**, không tương đương với `permitAll()`.

Khi chuyển đổi, phải biết matcher đó đang giới hạn **chain**, đang đặt **authorization rule**, hay đang **bỏ qua filter**.

## 3. Bản đồ chuyển đổi API

| Mã cũ / bối cảnh | Hướng hiện đại | Lý do |
| --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` và `configure(HttpSecurity)` | `@Bean SecurityFilterChain filterChain(HttpSecurity http)` | Cấu hình theo bean, kết thúc bằng `http.build()`. |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Dùng mô hình `AuthorizationManager`/`AuthorizationFilter` hiện đại. |
| `antMatchers("/x/**")` hoặc `mvcMatchers("/x/**")` trong authorization | `requestMatchers("/x/**")` | Giao DSL hiện đại cho rule, chọn matcher thích hợp theo phiên bản và môi trường. |
| `regexMatchers(...)` trong authorization | `requestMatchers(RegexRequestMatcher.regexMatcher(...))` | Chỉ định tường minh matcher regex nếu thật sự cần. |
| `http.antMatcher("/api/**")` trong cấu hình chain | `http.securityMatcher("/api/**")` | Chọn yêu cầu được đưa vào chain đó. |
| `authorizeRequests().anyRequest()` | `authorizeHttpRequests(auth -> auth.anyRequest()...)` | Quy tắc cuối trong phạm vi chain đang chọn. |
| `.formLogin().and().httpBasic()` | `.formLogin(Customizer.withDefaults()).httpBasic(Customizer.withDefaults())` | Lambda DSL; không còn `.and()` ở 7.x. |
| `configure(WebSecurity)` để bỏ qua URL | `@Bean WebSecurityCustomizer`, nếu thực sự phải ignore | `ignoring()` bỏ luôn các filter và bảo vệ do chúng cung cấp. |
| `configure(AuthenticationManagerBuilder)` | Bean `UserDetailsService`, `AuthenticationProvider`, `PasswordEncoder` hoặc cấu hình `AuthenticationManager` khi cần | Tách phần xác thực khỏi rule HTTP. |
| `http.apply(customDsl)` | `http.with(customDsl, customizer)` trên các bản hỗ trợ API mới | Chuẩn bị cho việc loại `.and()` trong DSL tùy biến ở 7.x. |

Cần kiểm tra kiểu `RequestMatcher` thực tế khi nâng **6.x → 7.x**. Trên nhiều phiên bản 6.x, overload nhận `String` có thể chọn matcher theo việc ứng dụng có Spring MVC trên classpath hay không; Spring Security 7 chuyển về `PathPatternRequestMatcher`. Không giả định hai matcher có cú pháp và ngữ nghĩa trùng nhau cho mọi pattern. Đặc biệt, các pattern Ant kiểu `/**/admin` cần được kiểm tra lại vì `PathPattern` có những hạn chế cú pháp khác.

## 4. Lambda DSL hoạt động như thế nào?

```java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());

return http.build();
```

Đây là **đoạn cấu hình đặt bên trong phương thức bean** và cần import phù hợp; chương trình chạy đầy đủ có ở phần tiếp theo.

- `auth -> ...` nhận đối tượng chuyên cấu hình authorization. Khi lambda kết thúc, có thể tiếp tục gọi `.httpBasic(...)` trên `HttpSecurity`.
- `Customizer.withDefaults()` tương đương một lambda cấu hình rỗng, dùng mặc định của tính năng. Nó **không** có nghĩa “vô hiệu hóa” tính năng.
- `requestMatchers(...)` xác định quy tắc cho yêu cầu khớp mẫu. Quy tắc được xét **theo thứ tự khai báo**, rule đầu tiên khớp sẽ quyết định.
- `hasRole("ADMIN")` tìm authority `ROLE_ADMIN`; nếu lưu authority không có tiền tố `ROLE_`, cân nhắc `hasAuthority("...")` theo giá trị thực.
- `anyRequest().authenticated()` là quy tắc dự phòng; đặt **cuối** danh sách. `denyAll()` là lựa chọn khép chặt hơn khi ứng dụng chỉ muốn mở những endpoint đã liệt kê.
- `permitAll()` bỏ yêu cầu đăng nhập cho rule đó, nhưng request vẫn đi qua filter chain; nó không tự tắt CSRF hay các cơ chế bảo vệ khác.

Sai lầm về **thứ tự rule**:

```java
// SAI về chính sách: /api/admin/** đã bị rule rộng phía trước bắt lấy.
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

```java
// ĐÚNG: đặc thù trước, tổng quát sau.
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
```

## 5. Dự án Spring Boot chạy được: từ mã cũ sang bean hiện đại

Ví dụ dùng **Java 17, Maven và Spring Boot 3.3.0 / Spring Security 6.x**. Mục đích là thử chính sách matcher bằng HTTP Basic trên các endpoint GET; việc giữ cấu hình CSRF mặc định phù hợp với ví dụ này. Đây là ứng dụng demo, không phải cơ chế lưu người dùng/sử dụng mật khẩu cho production.

### 5.1. Cấu trúc tệp

```text
security-migration-demo/
├── pom.xml
└── src/
    ├── main/java/example/demo/
    │   ├── DemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/example/demo/
        └── SecurityRulesTest.java
```

Tạo `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>security-migration-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`src/main/java/example/demo/DemoApplication.java`:

```java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/example/demo/SecurityConfig.java`:

```java
package example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/items/**")
                    .hasAnyRole("USER", "ADMIN")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build()
        );
    }
}
```

Ở đây `SecurityFilterChain` là **một bean**, nên Spring Security dùng nó làm cấu hình HTTP. Không còn `extends WebSecurityConfigurerAdapter`. Việc cấp người dùng demo tách khỏi cấu hình matcher: `UserDetailsService` nạp user, `PasswordEncoder` mã hóa mật khẩu bằng BCrypt, còn `SecurityFilterChain` quyết định quyền truy cập URL.

`src/main/java/example/demo/DemoController.java`:

```java
package example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/items/{id}")
    public String item(@PathVariable String id) {
        return "item-" + id;
    }

    @GetMapping("/api/admin/report")
    public String report() {
        return "admin-only";
    }

    @GetMapping("/account")
    public String account() {
        return "signed-in";
    }
}
```

### 5.2. Chạy và quan sát

Từ thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn test
mvn spring-boot:run
```

Mở một terminal khác trên macOS/Linux; các lệnh sau **chỉ in mã HTTP** nên không phụ thuộc header/body của framework:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/public/ping
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/items/42
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader-pass http://localhost:8080/api/items/42
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader-pass http://localhost:8080/api/admin/report
curl -s -o /dev/null -w '%{http_code}\n' -u admin:admin-pass http://localhost:8080/api/admin/report
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/account
```

Khi app chạy trên cổng 8080 và không có proxy/chỉnh sửa cấu hình khác, stdout lần lượt là:

```text
200
401
200
403
200
401
```

Giải thích từng trường hợp: public không cần login; API item không có credential bị HTTP Basic challenge (**401**); USER đọc item được (**200**); USER đã xác thực nhưng thiếu role ADMIN nên **403**; ADMIN đọc report được (**200**); đường dẫn không liệt kê vẫn cần login (**401**). Với cấu hình `formLogin` thay vì chỉ `httpBasic`, request chưa đăng nhập có thể bị **302** chuyển tới login; đừng dùng quy tắc “mọi request chưa login luôn 401” cho mọi kiểu ứng dụng.

Trên Windows PowerShell nên gọi `curl.exe` để tránh alias `curl`; thay `/dev/null` bằng `NUL` nếu chạy trực tiếp trên Windows.

### 5.3. Kiểm thử tự động chính sách với MockMvc

`src/test/java/example/demo/SecurityRulesTest.java`:

```java
package example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public/ping")).andExpect(status().isOk());
    }

    @Test
    void itemRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/items/42")).andExpect(status().isUnauthorized());
    }

    @Test
    void readerMayViewItem() throws Exception {
        mvc.perform(get("/api/items/42").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isOk());
    }

    @Test
    void readerMayNotViewAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report").with(httpBasic("reader", "reader-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminMayViewReport() throws Exception {
        mvc.perform(get("/api/admin/report").with(httpBasic("admin", "admin-pass")))
            .andExpect(status().isOk());
    }
}
```

`mvn test` phải chạy các test này và kết quả mong đợi là **5 test thành công** nếu mã/tệp đúng như trên. Với ứng dụng có các phương thức ghi dữ liệu như `POST`/`PUT`/`DELETE`, kiểm tra riêng CSRF: khi CSRF được bật, thử nghiệm MockMvc có thể cần `.with(csrf())` bên cạnh thông tin đăng nhập. **Đừng tắt CSRF để sửa một test 403 mà chưa phân tích cách ứng dụng xác thực.**

## 6. Hai lớp matcher: chọn filter chain rồi mới chọn rule

Đây là điểm dễ gây lỗi nhất khi đổi API.

```text
HTTP request
  ↓
DelegatingFilterProxy / FilterChainProxy
  ↓ chọn SecurityFilterChain ĐẦU TIÊN có securityMatcher khớp
Các security filter trong chain (authentication, CSRF, authorization, ...)
  ↓ authorizeHttpRequests → requestMatchers → rule đầu tiên khớp
Controller nếu được phép
```

- `http.securityMatcher("/api/**")` = “**chain này** nhận loại request nào?”; nếu không cấu hình, matcher của chain mặc định nhận mọi request.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin/**")...)` = “**bên trong chain đã chọn**, request này cần quyền gì?”.
- `anyRequest()` chỉ nói về các request còn lại **trong chain hiện tại**, không kéo request bên ngoài chain vào.
- Khi có nhiều `SecurityFilterChain`, `@Order(1)` được xét trước `@Order(2)`; **chỉ chain đầu tiên khớp được dùng**, không cộng dồn authorization của mọi chain.
- Nếu không có chain nào khớp, request có thể **đi ngoài Spring Security**, là lỗ hổng bảo vệ nghiêm trọng nếu không chủ ý.

Ví dụ **hai bean độc lập, minh họa cấu hình đa chain** (đặt bên trong cùng một `@Configuration`, có các import tương ứng):

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

`/api/admin/report` đi vào `apiChain`, áp rule ADMIN; `/account` đi vào `fallbackChain`. Vì fallback không có `securityMatcher` riêng, nó bao phủ các request chưa được chain trước chọn, kể cả URL của trang đăng nhập mặc định. Nếu chỉ khai báo `apiChain`, yêu cầu ngoài `/api/**` không được chain này bảo vệ. Với nhiều chain, cũng cần đặt các URL đăng nhập/logout sinh bởi filter vào phạm vi chain tương ứng; một chain chỉ match `/api/**` thường không thể cung cấp endpoint `/login` mặc định.

## 7. `requestMatchers`: pattern, HTTP method và phiên bản

`requestMatchers("/api/items/**")` là rule theo đường dẫn; `requestMatchers(HttpMethod.GET, "/api/items/**")` thêm điều kiện HTTP method. Nếu ứng dụng muốn phân quyền GET khác POST, cần rule tường minh cho từng method hoặc chính sách dự phòng thích hợp.

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/items/**").hasAuthority("item:read")
    .requestMatchers(HttpMethod.POST, "/api/items/**").hasAuthority("item:write")
    .anyRequest().denyAll()
)
```

Đoạn trên là **fragment**; cần một cấu hình HTTP và cơ chế xác thực cấp authority tương ứng. `hasAuthority("item:read")` so đúng chuỗi authority; `hasRole("USER")` thông thường so `ROLE_USER`. Matcher URL chủ yếu xét path, **không tự xét query string**: `/api/items/42?preview=true` vẫn nằm trên path `/api/items/42`. Muốn xét tham số, dùng `RequestMatcher` tùy biến cùng kiểm thử tương ứng.

### Khi nâng sang Spring Security 7

Spring Security 7 dùng `PathPatternRequestMatcher` thay cho các cách matcher Ant/MVC đã ngừng hỗ trợ. Quy tắc đường dẫn cần viết theo ngữ nghĩa `PathPattern`; URL trong Java DSL là đường dẫn từ application (không gồm context path). Với nhiều servlet, hãy xem xét **servlet path prefix** để tránh khớp sai endpoint.

Trên phiên bản có hỗ trợ `PathPatternRequestMatcher`, có thể khai báo matcher tường minh:

```java
import static org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher.withDefaults;

// Fragment trong cấu hình Spring Security hỗ trợ PathPatternRequestMatcher:
var apiAdmin = withDefaults().matcher("/api/admin/**");
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(apiAdmin).hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

Đoạn này mô tả cách dùng matcher tường minh trên phiên bản có lớp đó; **không** đặt nguyên vào dự án Boot 3.3.0 ở phần 5 nếu dependency Spring Security chưa cung cấp API. Khi migrate 6.x → 7.x, chạy lại test matcher với slash cuối, đường dẫn sâu, encoded path, nhiều servlet và các pattern dùng `**`; không thay cơ học `AntPathRequestMatcher` bằng một class khác rồi coi là tương đương hoàn toàn.

## 8. `permitAll()` khác `web.ignoring()`

Ví dụ tốt để mở tài nguyên tĩnh trong ứng dụng web:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
```

Request vẫn qua các security filter, nên có thể nhận các security header và cơ chế bảo vệ liên quan. Ngược lại:

```java
@Bean
WebSecurityCustomizer webSecurityCustomizer() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
```

Fragment `WebSecurityCustomizer` này khiến `/assets/**` **bỏ qua Spring Security filter chain**. Chỉ dùng khi yêu cầu thật sự phải tránh mọi filter; Spring Security khuyến nghị ưu tiên `permitAll()` cho tài nguyên tĩnh. Đặc biệt, **đừng** chuyển `web.ignoring()` thành `permitAll()` hoặc ngược lại mà không cân nhắc hiệu ứng của filters, header, audit và CSRF.

## 9. Khi ứng dụng cũ còn cấu hình AuthenticationManager

Một lớp adapter lịch sử có thể ghi đè `configure(AuthenticationManagerBuilder)` để thêm user, LDAP hay authentication provider. Trong cấu hình bean hiện đại, đừng sao chép mù quáng cú pháp cũ: hãy giữ **cơ chế xác thực thực tế** (password encoding, user store, provider order) rồi cung cấp các bean tương ứng.

Nếu code nghiệp vụ thật sự cần inject `AuthenticationManager`, trên cấu hình Spring Security 6.x có thể lấy qua `AuthenticationConfiguration`:

```java
@Bean
AuthenticationManager authenticationManager(AuthenticationConfiguration configuration)
        throws Exception {
    return configuration.getAuthenticationManager();
}
```

Đây là **fragment bổ sung**; cần import `org.springframework.security.authentication.AuthenticationManager` và `org.springframework.security.config.annotation.authentication.configuration.AuthenticationConfiguration`. Không cần khai báo bean trên chỉ để cấu hình `HttpSecurity` thông thường. Với authentication provider tùy biến hoặc nhiều filter chain, phải kiểm tra cơ chế kết hợp provider và phạm vi AuthenticationManager thực tế, không mặc định mọi ứng dụng dùng cùng một manager.

## 10. Những lỗi thường gặp khi migrate

1. **Nâng dependency lên 6.x nhưng giữ `extends WebSecurityConfigurerAdapter` hoặc `antMatchers`.** Kết quả là lỗi compile vì API đã bị loại bỏ. Chuyển sang bean và matcher mới trước khi chạy test.
2. **Nhầm `securityMatcher` với `requestMatchers`.** Dùng sai vị trí có thể để request không được chain nào bảo vệ; luôn có fallback phù hợp.
3. **Đặt rule rộng trước rule đặc thù.** Ví dụ `/api/**` trước `/api/admin/**` làm rule ADMIN không được xét; sửa thứ tự và test từng URL.
4. **Dùng `hasRole("ROLE_ADMIN")`.** `hasRole` thêm tiền tố role theo quy ước; dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` đúng giá trị lưu trong hệ thống.
5. **Dùng `ignoring()` để mở static resource.** Điều này bỏ qua toàn bộ security filter; ưu tiên `permitAll()` khi không có lý do mạnh để bỏ filter.
6. **Tưởng `permitAll()` tự vô hiệu hóa CSRF.** CSRF là cơ chế riêng; request thay đổi trạng thái vẫn có thể bị 403 nếu thiếu token.
7. **Giữ `.and()` hoặc DSL không lambda khi chuẩn bị lên 7.x.** Viết trực tiếp Lambda DSL, dùng `Customizer.withDefaults()` cho tính năng cấu hình mặc định.
8. **Thay Ant pattern bằng PathPattern mà không test.** Cú pháp wildcard, servlet path và cách match có thể khác; phải kiểm tra trường hợp biên.
9. **Quên endpoint do filter tạo ra.** `formLogin()`, logout hoặc endpoint authentication tùy chỉnh có thể nằm ngoài `securityMatcher`, gây 404/luồng đăng nhập hỏng.
10. **Chỉ kiểm tra request thành công.** Một migration an toàn cần cả test 401 (chưa đăng nhập), 403 (đã đăng nhập nhưng thiếu quyền), 200 (đúng quyền), và tình huống method/URL không được cấp phép.

### Checklist thực hành trước khi chốt migration

- [ ] Xác định chính xác phiên bản Spring Boot/Spring Security và Java đang chạy.
- [ ] Liệt kê cấu hình adapter cũ, HTTP matcher, `WebSecurity` ignore và các authentication provider.
- [ ] Di chuyển HTTP sang `SecurityFilterChain`; tách password/user/provider thành các bean rõ ràng.
- [ ] Thay `authorizeRequests` bằng `authorizeHttpRequests`; thay matcher cũ theo **đúng vai trò** của nó.
- [ ] Soát thứ tự rule từ cụ thể đến tổng quát; `anyRequest` ở cuối.
- [ ] Nếu nhiều chain, kiểm tra `@Order`, `securityMatcher`, fallback và endpoint do filter sinh ra.
- [ ] Giữ/kiểm tra CSRF, header, session, CORS, authentication entry point và exception handling theo hành vi mong muốn.
- [ ] Viết test cho anonymous, USER, ADMIN; các đường dẫn/method được phép và bị từ chối.
- [ ] Nếu nâng lên 7.x, loại DSL chaining cũ và kiểm tra lại toàn bộ pattern theo `PathPatternRequestMatcher`.

## 11. Nguồn chính thức để đối chiếu API

- Spring Blog — *Spring Security without the WebSecurityConfigurerAdapter*: https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter
- Spring Security 6.5 — *Java Configuration*, đặc biệt phần multiple chains và `securityMatcher`: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security 6.5 — *Authorize HttpServletRequests*, bao gồm rule order và `permitAll` vs `ignoring`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security — *Configuration Migrations for 7*: https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html
- Spring Security — *Web Migrations for 7* (`PathPatternRequestMatcher`): https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html

**Kết quả cần đạt:** đọc một cấu hình `WebSecurityConfigurerAdapter` là nhận ra chính xác policy cũ; chuyển sang bean `SecurityFilterChain` + Lambda DSL mà vẫn giữ được thứ tự phân quyền, phạm vi filter chain và các biện pháp bảo vệ HTTP, đồng thời biết những matcher nào phải đánh giá lại khi lên Spring Security 7.
