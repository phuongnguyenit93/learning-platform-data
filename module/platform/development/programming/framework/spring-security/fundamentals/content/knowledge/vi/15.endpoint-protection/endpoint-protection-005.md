# Thứ tự quy tắc và nguyên tắc dùng quy tắc khớp đầu tiên

## 1. Mục tiêu

Bài học thuộc chủ đề **Bảo vệ endpoint** trong Spring Security. Sau khi hoàn thành, bạn có thể:

1. Giải thích cơ chế **first matching rule** trong `authorizeHttpRequests`: các cặp matcher–quy tắc được duyệt theo thứ tự khai báo, và **chỉ quy tắc đầu tiên khớp được áp dụng**.
2. Đặt matcher đặc thù trước matcher bao quát, sử dụng `anyRequest().denyAll()` đúng vai trò fallback.
3. Nhận diện lỗi *rule shadowing*: quy tắc bảo mật chặt đứng sau một quy tắc rộng nên không bao giờ được dùng.
4. Phân biệt việc `FilterChainProxy` chọn **`SecurityFilterChain` đầu tiên khớp** với việc `AuthorizationFilter` chọn **rule đầu tiên khớp bên trong chain**.
5. Phân biệt thứ tự security rules với cách Spring MVC chọn controller mapping theo độ đặc hiệu.
6. Xây dựng và chạy Java 17 + Spring Boot với HTTP Basic, kiểm tra 200/401/403 và viết kiểm thử chống lỗi đảo thứ tự.

Ví dụ chính dùng **Spring MVC/Servlet** (`HttpSecurity`, `SecurityFilterChain`). Spring WebFlux dùng các type reactive khác (`ServerHttpSecurity`, `SecurityWebFilterChain`), không dùng lẫn hai stack.

## 2. Một danh sách rule hoạt động ra sao?

Xét cấu hình HTTP:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
```

Đây là **fragment minh họa**; nó cần nằm trong method cấu hình `SecurityFilterChain` của ứng dụng.

Mỗi dòng tạo một cặp **`RequestMatcher` → `AuthorizationManager`**. Ví dụ:

- Matcher `/public/**` khớp một nhóm đường dẫn công khai; `permitAll()` cho phép truy cập ở bước authorization này.
- Matcher `/api/admin/**` yêu cầu role `ADMIN`.
- Matcher `/api/**` yêu cầu người gọi đã xác thực.
- `anyRequest()` là trường hợp chung khi các matcher trước chưa khớp.

Khi request đến, Spring Security thực hiện logic khái quát:

```text
Request R
   │
   ▼
Matcher 1 có khớp R?
   ├─ Có  → Áp dụng rule 1 → ALLOW hoặc DENY → DỪNG CHỌN RULE
   └─ Không
          ▼
Matcher 2 có khớp R?
   ├─ Có  → Áp dụng rule 2 → ALLOW hoặc DENY → DỪNG CHỌN RULE
   └─ Không
          ▼
Matcher 3 ... → ...
          ▼
Fallback anyRequest() nếu chưa có matcher nào khớp
```

**Hai điều cần nhớ:**

- Spring Security không thử mọi rule rồi chọn rule “mạnh nhất”, “cụ thể nhất” hoặc rule có quyết định *allow*.
- Nếu rule đầu tiên khớp nhưng người dùng không thỏa điều kiện, request **bị từ chối ngay theo rule đó**. Không có bước thử rule thứ hai để tìm đường đi khác.

Tài liệu Spring Security gọi rõ hành vi này là việc xử lý các cặp pattern/rule theo **thứ tự khai báo** và chỉ áp dụng **first match**.

### Theo dấu từng request

| Request | Matcher đầu tiên khớp | Quy tắc thực sự áp dụng |
| --- | --- | --- |
| `GET /public/news` | `/public/**` | `permitAll` |
| `GET /api/admin/users` | `/api/admin/**` | `hasRole("ADMIN")` |
| `GET /api/orders` | `/api/**` | `authenticated` |
| `GET /internal/health` | `anyRequest()` | `denyAll` |

`/api/admin/users` đồng thời thỏa pattern `/api/**`. Tuy nhiên dòng `/api/admin/**` ở trên được chọn sớm, do đó người dùng chỉ có `ROLE_USER` không qua được, dù họ đã đăng nhập.

## 3. Thứ tự sai có thể làm lộ endpoint

**Cấu hình nguy hiểm:**

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
);
```

Request `GET /api/admin/users` đã khớp dòng `/api/**` và được cho phép. Dòng `hasRole("ADMIN")` phía dưới **không bao giờ quyết định quyền cho request này**. Fallback `denyAll()` cũng không giúp: nó chỉ xử lý request **chưa được** một dòng trước match.

Một lỗi khác khó nhận biết hơn:

```java
.requestMatchers("/api/**").authenticated()
.requestMatchers("/api/admin/**").hasRole("ADMIN")
```

Trong chính sách HTTP trên, mọi user đã đăng nhập có thể đến `/api/admin/**` vì `authenticated()` được chọn trước. Việc giao diện ẩn nút Admin không ngăn người dùng tự gọi HTTP trực tiếp.

**Sửa đúng:**

```java
.requestMatchers("/api/admin/**").hasRole("ADMIN")
.requestMatchers("/api/**").authenticated()
.anyRequest().denyAll()
```

Đây là quy tắc sắp xếp có thể kiểm chứng: **đặc thù trước, bao quát sau, fallback cuối**. Không cần đo độ dài chuỗi; hãy tìm các matcher có thể đồng thời khớp cùng request.

### Quy tắc đầu tiên khớp rồi từ chối có xét tiếp không?

**Không.** Giả sử `/api/admin/users` gặp `hasRole("ADMIN")` và người gọi có `ROLE_USER`. Quyết định là từ chối; Spring Security không “rơi xuống” `authenticated()` bên dưới. Nếu lại thử rule sau thì mọi chính sách nhạy cảm đều có thể bị vô hiệu bởi một fallback rộng.

## 4. Khác biệt với chọn controller của Spring MVC

Thường tồn tại hai cơ chế độc lập:

| Thành phần | Việc cần làm | Cơ chế chọn |
| --- | --- | --- |
| Spring Security `authorizeHttpRequests` | Chọn chính sách authorization HTTP | **Rule đầu tiên có matcher khớp theo thứ tự khai báo** |
| Spring MVC `@RequestMapping`, `@GetMapping` | Chọn controller method | Xét method/path/params/headers và độ đặc hiệu mapping theo cơ chế MVC |
| Spring Security `FilterChainProxy` (nhiều chains) | Chọn `SecurityFilterChain` | **Chain đầu tiên có security matcher khớp theo thứ tự ưu tiên** |

Ví dụ controller cụ thể:

```java
@GetMapping("/api/admin/users")
public String users() {
    return "users";
}
```

Spring MVC có thể chọn mapping này thay vì handler chung, nhưng nó **không** tự nâng ưu tiên cho rule `/api/admin/**` của Spring Security. Nếu security đã đặt `/api/**.permitAll()` trước, endpoint vẫn có nguy cơ bị mở quyền dù controller mapping rất cụ thể.

**Nguyên tắc:** không dùng thuật toán chọn handler MVC để suy luận thứ tự policy security.

## 5. Thiết kế danh sách quy tắc an toàn

Một mẫu đáng cân nhắc:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/reports/admin").hasRole("ADMIN")
    .requestMatchers("/api/reports/**").hasAnyRole("ANALYST", "ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
)
```

Với mẫu này:

| Request | Dòng được chọn | Lý do |
| --- | --- | --- |
| `/public/ping` | `/public/**` | Public, khớp sớm |
| `/api/reports/admin` | `/api/reports/admin` | Đặc thù hơn đường báo cáo thường |
| `/api/reports/summary` | `/api/reports/**` | Không khớp exact admin, khớp reports |
| `/api/profile` | `/api/**` | Chỉ còn matcher API chung |
| `/internal/diagnostics` | `anyRequest()` | Không thuộc nhóm được liệt kê |

Không có cơ chế mặc định tự hiểu rằng `ADMIN` “bao gồm” `ANALYST`. Quy tắc `hasAnyRole("ANALYST","ADMIN")` ở đây **cho phép một trong hai**; đó là chính sách OR tường minh, không phải role hierarchy.

### anyRequest() dùng để làm gì?

`anyRequest().denyAll()` thể hiện **default deny**: endpoint mới chưa được khai báo quyền sẽ bị từ chối thay vì trở thành công khai. Mặc dù vậy, nó không cứu được bất kỳ endpoint nào bị match bởi rule quá rộng phía trên.

Trong DSL, `anyRequest()` là fallback cuối danh sách. Đừng viết một `permitAll()` bao trùm phía trước rồi nghĩ fallback có thể khóa bớt URL.

### Hiểu các rule hay gặp

- `permitAll()`: cho phép đi qua bước authorization trên route khớp; các filter khác vẫn có thể hoạt động.
- `authenticated()`: cần xác thực thành công, không đòi role cụ thể.
- `hasRole("ADMIN")`: theo quy ước mặc định, cần authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")`: kiểm tra chính xác chuỗi authority được cung cấp.
- `hasAnyRole("ANALYST","ADMIN")`: cần ít nhất một authority tương ứng.
- `denyAll()`: từ chối dù người dùng có role gì.

`User.withUsername("admin").roles("ADMIN")` tạo authority `ROLE_ADMIN`; khi gọi `hasRole`, **không truyền** `"ROLE_ADMIN"` vào tham số của `hasRole` trong cấu hình tiền tố mặc định.

## 6. Ứng dụng Java 17 có thể chạy: kiểm chứng first-match

Ta xây dựng một ứng dụng Spring Boot Servlet/MVC với các endpoint:

| Endpoint | Chính sách |
| --- | --- |
| `GET /public/ping` | Công khai |
| `GET /api/profile` | Bất kỳ người dùng đã xác thực |
| `GET /api/reports/summary` | ANALYST hoặc ADMIN |
| `GET /api/reports/admin` | Chỉ ADMIN |
| `GET /internal/diagnostics` | Có controller thật, nhưng bị fallback denyAll |

Ví dụ sử dụng **Spring Boot 3.3.13**, Spring Security 6.x, Gradle 8.x và Java 17+. Dùng HTTP Basic và chỉ có GET để quan sát first-match rõ ràng mà không cần thay đổi thiết lập CSRF.

### 6.1. Cấu trúc và build

```text
rule-order-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/ruleorder/
    │   ├── RuleOrderApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/ruleorder/
        └── RuleOrderSecurityTests.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'rule-order-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/ruleorder/RuleOrderApplication.java`**

```java
package com.example.ruleorder;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuleOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuleOrderApplication.class, args);
    }
}
```

### 6.2. SecurityFilterChain: lưu ý thứ tự

**`src/main/java/com/example/ruleorder/SecurityConfig.java`**

```java
package com.example.ruleorder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/api/reports/admin").hasRole("ADMIN")
                .requestMatchers("/api/reports/**").hasAnyRole("ANALYST", "ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails viewer = User.withUsername("viewer")
            .password("{noop}viewer123")
            .roles("VIEWER")
            .build();

        UserDetails analyst = User.withUsername("analyst")
            .password("{noop}analyst123")
            .roles("ANALYST")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(viewer, analyst, admin);
    }
}
```

Ứng dụng tạo ba user có **một role riêng** mỗi người. Không có hệ thống kế thừa role tự động. `ADMIN` truy cập được summary vì rule dùng `hasAnyRole("ANALYST","ADMIN")`, không phải vì admin ngầm có authority `ROLE_ANALYST`.

`{noop}` và tài khoản cố định **chỉ phục vụ demo cục bộ**, tuyệt đối không triển khai lên production. Ứng dụng thật cần password encoder an toàn, lưu trữ secrets, kiểm soát vòng đời user/roles và HTTPS.

`httpBasic(withDefaults())` kích hoạt HTTP Basic; `formLogin(...disable())` tránh redirect sang trang login cho các request cần authentication. Ví dụ giữ nguyên thiết lập CSRF mặc định và không có endpoint thay đổi dữ liệu.

### 6.3. Controller

**`src/main/java/com/example/ruleorder/DemoController.java`**

```java
package com.example.ruleorder;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String publicPing() {
        return "public";
    }

    @GetMapping("/api/profile")
    public String profile() {
        return "profile";
    }

    @GetMapping("/api/reports/summary")
    public String summary() {
        return "summary";
    }

    @GetMapping("/api/reports/admin")
    public String adminReport() {
        return "admin-report";
    }

    @GetMapping("/internal/diagnostics")
    public String diagnostics() {
        return "internal";
    }
}
```

`/internal/diagnostics` **có mapping thật** nhưng bị denyAll ở tầng HTTP. Một user đã đăng nhập gọi endpoint đó sẽ bị 403 và không nhận body `"internal"`. Vì vậy, sự tồn tại của `@GetMapping` không đảm bảo request được phép tới controller.

### 6.4. Chạy bằng Gradle và gửi request

Trong thư mục `rule-order-demo`, cài JDK 17+ và Gradle 8.x tương thích, sau đó chạy:

```bash
gradle test
gradle bootRun
```

Nếu dự án có Gradle Wrapper tương thích, thay bằng `./gradlew test` và `./gradlew bootRun` trên Linux/macOS, hoặc `gradlew.bat test` và `gradlew.bat bootRun` trên Windows. Không thể dùng lệnh `javac`/`java` trần mà thiếu toàn bộ thư viện Spring; Gradle cấp classpath và khởi chạy `RuleOrderApplication`.

Ở terminal khác:

```bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/profile
curl -i -u viewer:viewer123 http://localhost:8080/api/profile
curl -i -u viewer:viewer123 http://localhost:8080/api/reports/summary
curl -i -u analyst:analyst123 http://localhost:8080/api/reports/summary
curl -i -u analyst:analyst123 http://localhost:8080/api/reports/admin
curl -i -u admin:admin123 http://localhost:8080/api/reports/admin
curl -i -u admin:admin123 http://localhost:8080/internal/diagnostics
```

**Ma trận HTTP dự kiến:**

| GET endpoint | Anonymous | VIEWER | ANALYST | ADMIN |
| --- | :---: | :---: | :---: | :---: |
| `/public/ping` | 200 | 200 | 200 | 200 |
| `/api/profile` | 401 | 200 | 200 | 200 |
| `/api/reports/summary` | 401 | 403 | 200 | 200 |
| `/api/reports/admin` | 401 | 403 | 403 | 200 |
| `/internal/diagnostics` | 401* | 403 | 403 | 403 |

`*` Với HTTP Basic của demo, anonymous bị chặn bởi `denyAll()` có thể đi qua `AuthenticationEntryPoint` và nhận 401; phản hồi cụ thể của anonymous trong ứng dụng khác còn phụ thuộc exception handling. Bài test dưới đây chủ động xác nhận **403 cho authenticated user** ở endpoint này.

Body của các response **200** tương ứng là `public`, `profile`, `summary` và `admin-report`. Đừng kỳ vọng body của 401/403 có JSON cố định; framework và cấu hình content negotiation có thể thay đổi response lỗi. Điều cần đối chiếu ở đây là status code và việc endpoint nhạy cảm không trả dữ liệu thành công.

### 6.5. Test tự động bắt lỗi đảo thứ tự

**`src/test/java/com/example/ruleorder/RuleOrderSecurityTests.java`**

```java
package com.example.ruleorder;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RuleOrderSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicIsAccessibleWithoutLogin() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousCannotUseApi() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "VIEWER")
    void viewerCanReadProfileButNotReports() throws Exception {
        mvc.perform(get("/api/profile"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ANALYST")
    void analystCanReadSummaryButNotAdminReport() throws Exception {
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isOk())
            .andExpect(content().string("summary"));
        mvc.perform(get("/api/reports/admin"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void adminCanReadAllReportEndpoints() throws Exception {
        mvc.perform(get("/api/reports/summary"))
            .andExpect(status().isOk());
        mvc.perform(get("/api/reports/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-report"));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void unlistedDiagnosticsRemainsDenied() throws Exception {
        mvc.perform(get("/internal/diagnostics"))
            .andExpect(status().isForbidden());
    }
}
```

**Vì sao đây là bộ test có giá trị?**

- Nếu đặt `/api/**.authenticated()` **trước** `/api/reports/**`, VIEWER sẽ vô tình vào được summary; test `viewerCanReadProfileButNotReports` thất bại.
- Nếu đặt `/api/reports/**` **trước** `/api/reports/admin`, ANALYST sẽ vào được admin report; test `analystCanReadSummaryButNotAdminReport` thất bại.
- Nếu loại fallback `denyAll()` hoặc thay bằng rule quá rộng, test `unlistedDiagnosticsRemainsDenied` sẽ chỉ ra thay đổi ngoài dự kiến.
- Test cho phép và từ chối được đặt cạnh nhau để thể hiện toàn bộ biên của policy.

`@WithMockUser(roles = "ANALYST")` tạo `ROLE_ANALYST` trong test security context; nó không thực hiện login thật với password store `InMemoryUserDetailsManager`. Dùng các lệnh `curl -u` phía trên khi cần kiểm tra riêng HTTP Basic và credentials.

## 7. Hai cấp “first match” khi có nhiều SecurityFilterChain

Một ứng dụng có thể khai báo nhiều `SecurityFilterChain`, ví dụ API dùng bearer token và website dùng session login. Đừng nhầm thứ tự **các chain** với thứ tự **các rule**.

**Cấp 1 — chọn chain.** `FilterChainProxy` duyệt các chains theo thứ tự ưu tiên, thường đặt bằng `@Order`. Chain đầu tiên mà `securityMatcher` chấp nhận request sẽ được chọn. Nếu request bị từ chối bên trong chain đó, Spring Security **không chuyển qua chain khác** để xin phép lần hai.

**Cấp 2 — chọn authorization rule.** Bên trong chain đã chọn, `authorizeHttpRequests` xét `requestMatchers` theo thứ tự và áp dụng rule đầu tiên khớp.

```text
Request
  ↓
FilterChainProxy
  ├─ @Order(1) SecurityFilterChain có securityMatcher khớp?
  │       ├─ Có → chọn chain 1 → áp dụng first-match rule trong chain 1
  │       └─ Không
  ├─ @Order(2) SecurityFilterChain có securityMatcher khớp?
  │       ├─ Có → chọn chain 2 → áp dụng first-match rule trong chain 2
  │       └─ Không
  └─ Không chain nào khớp → request nằm ngoài các security chains đó
```

**Fragment riêng minh họa hai chain (không chèn vào demo ở mục 6):**

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll()
        )
        .build();
}
```

Đoạn trên cần import `org.springframework.core.annotation.Order` và các import security/bean tương ứng; đây chỉ là phần cấu hình minh họa, không phải chương trình độc lập.

Với `GET /api/admin/users`, chain API `@Order(1)` được chọn; rule admin bên trong chain đó quyết định quyền. Với `GET /public/ping`, chain API không khớp nên fallback chain `@Order(2)` được xét và từ chối. **Nếu chain tổng quát không có `securityMatcher` được đặt ưu tiên cao nhất**, nó có thể che chain API phía dưới do mặc định một chain thường khớp mọi request.

Đặc biệt: nếu chỉ tạo một chain có `securityMatcher("/api/**")` và **không có fallback chain bao phủ phần còn lại**, các request không thuộc `/api/**` có thể không được Spring Security bảo vệ. Không được suy luận rằng “không match chain” nghĩa là “deny mặc định”; đó là hai tình huống khác nhau.

| API | Cấp áp dụng | Câu hỏi |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | Cả `SecurityFilterChain` | Chain này có được chọn cho request không? |
| `authorizeHttpRequests(...requestMatchers(...))` | Bên trong chain được chọn | Rule nào áp dụng? |
| `anyRequest().denyAll()` | Fallback trong chain được chọn | Nếu không rule nào trước đó khớp thì sao? |

## 8. HTTP method cũng là một phần của matcher

Đường dẫn giống nhau chưa chắc dùng cùng một rule. Ví dụ:

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
    .requestMatchers(HttpMethod.GET, "/api/articles/**").hasRole("READER")
    .anyRequest().denyAll()
)
```

Đây là **fragment** cần import `org.springframework.http.HttpMethod`. DELETE và GET được xác định riêng; POST/PATCH không khớp hai dòng trên sẽ bị fallback `denyAll`. Nếu đặt rule chung:

```java
.requestMatchers("/api/articles/**").authenticated()
.requestMatchers(HttpMethod.DELETE, "/api/articles/**").hasRole("ADMIN")
```

ở phía trước, rule DELETE sẽ bị che bởi matcher không giới hạn method. Cách sửa là đưa rule DELETE đặc thù lên trước và kiểm tra những HTTP methods còn lại.

### Chú ý HTTP HEAD và OPTIONS

Spring MVC có thể hỗ trợ **HEAD** cho handler `@GetMapping`, trong khi matcher security giới hạn `HttpMethod.GET` không đương nhiên match HEAD. Nếu một rule rộng phía sau lại dễ hơn, HEAD có thể đi theo một policy khác. Do đó, với tài nguyên nhạy cảm, hãy xác định rõ chính sách cho HEAD/OPTIONS, endpoint preflight và các method khác, thay vì giả định chỉ GET là đủ.

Việc match còn có thể phụ thuộc context path, servlet path, dấu gạch cuối, encoding, cấu hình case sensitivity và loại `RequestMatcher` thực tế. API `requestMatchers(String...)` trong môi trường Spring MVC có thể chọn matcher hiểu MVC tùy phiên bản và cách cấu hình. Hãy kiểm thử **request thực** qua gateway hoặc web server, tránh suy đoán chỉ từ chuỗi nhìn thấy trong URL.

### Không nhầm permitAll với bỏ qua filter

`requestMatchers("/public/**").permitAll()` cho phép ở lớp HTTP authorization của security chain, nhưng request vẫn đi qua các security filters đã cấu hình. Còn `web.ignoring()` hoặc cấu hình khiến không có chain nào match có thể làm request bỏ qua các filter đó. Với public endpoints thông thường, dùng `permitAll()` giúp giữ security headers và các cơ chế cần thiết. Không bỏ qua toàn bộ chain chỉ để tránh đăng nhập.

## 9. Security HTTP không thay kiểm tra quyền tại service

Một rule `.requestMatchers("/api/documents/**").authenticated()` chỉ cho biết request đã đăng nhập; nó **không** chứng minh user được đọc document ID cụ thể. Với `GET /api/documents/123`, backend còn phải kiểm tra owner, tenant, trạng thái, khả năng chia sẻ và quyền nghiệp vụ.

Mã minh họa:

```java
@GetMapping("/api/documents/{documentId}")
public DocumentDto view(@PathVariable long documentId) {
    return documentService.getVisibleForCurrentUser(documentId);
}
```

Đây là **fragment không độc lập**; cần các type `DocumentDto`, `documentService` và kiểm tra quyền resource ở server. Một lời gọi dịch vụ từ scheduled job hoặc message handler còn có thể bypass HTTP layer; dùng `@PreAuthorize` hoặc authorization service phù hợp khi chính sách cần được duy trì ở nhiều đường vào.

Dù vậy, một kiểm tra ở service **không phải lý do để để sai thứ tự HTTP rule**: endpoint khác có thể trả trực tiếp dữ liệu hoặc gọi đường service chưa được bảo vệ tương đương.

## 10. Lỗi phổ biến và checklist review

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `/api/**.permitAll()` đặt trước `/api/admin/**.hasRole("ADMIN")` | Endpoint admin có thể thành public | Rule admin trước, test anonymous |
| `/api/**.authenticated()` trước `/api/reports/**.hasRole(...)` | User bất kỳ đã đăng nhập có thể xem báo cáo | Rule báo cáo trước, test user không có role |
| Cho rằng rule “cụ thể nhất” sẽ tự được chọn | Đánh giá sai policy | Review theo thứ tự thật trong DSL |
| Cho rằng nếu rule deny sẽ thử rule sau | Hiểu sai mô hình first-match | Rule khớp đã quyết định, không có fallback allow |
| Đặt `anyRequest().permitAll()` khi chưa review toàn bộ route | Endpoint mới có thể lộ | Dùng `denyAll` khi phù hợp với chính sách |
| Chain tổng quát ưu tiên cao hơn chain API | Chain API bị che | Đặt `@Order` và `securityMatcher` rõ ràng |
| Dùng `securityMatcher("/api/**")` mà thiếu fallback chain | Các đường khác có thể không được bảo vệ | Bổ sung chain phủ phần còn lại |
| Rule GET có quyền cao nhưng HEAD/OPTIONS đi vào rule rộng | Khác biệt policy theo method | Thiết kế/test toàn bộ HTTP methods liên quan |
| Nhầm MVC handler specificity với security rule order | Tin nhầm endpoint cụ thể tự được bảo vệ | Test hai cơ chế riêng |
| Chỉ test 200, không test 401/403 | Không bắt được quyền bị mở | Test cả negative case |
| Coi mọi 403 đều do thiếu role | Bỏ sót CSRF/dispatch/access denied handler | Kiểm tra nguyên nhân thật qua logs an toàn |
| Gán `hasRole("ROLE_ADMIN")` theo prefix mặc định | Role check sai | Dùng `hasRole("ADMIN")` hoặc `hasAuthority("ROLE_ADMIN")` |

Checklist trước khi đổi rule:

1. Với mỗi endpoint nhạy cảm, liệt kê tất cả matcher có khả năng khớp; chỉ ra **matcher đầu tiên**.
2. Kiểm tra rule được chọn có đủ chặt ngay cả với user chỉ đăng nhập nhưng không có role.
3. Kiểm tra có bất kỳ matcher rộng nào vô tình che matcher đặc thù hay không.
4. Với nhiều chain, xác định **chain đầu tiên** và chain fallback, kiểm tra `@Order`.
5. Kiểm tra các HTTP methods, đặc biệt HEAD/OPTIONS khi controller có GET.
6. Test anonymous, ít quyền, đúng quyền và request ngoài danh sách.
7. Với resource ID, kiểm tra owner/tenant/state ở tầng nghiệp vụ.

## 11. Bài tập tự kiểm tra

**Câu 1.** Với thứ tự `/api/**.authenticated()` rồi `/api/admin/**.hasRole("ADMIN")`, user có `ROLE_USER` truy cập `/api/admin/users` sẽ thế nào?

**Đáp án:** bước HTTP authorization đầu tiên có thể cho qua vì user đã xác thực. Rule admin bị che. Controller/service khác vẫn có thể từ chối, nhưng cấu hình URL đang sai.

**Câu 2.** Nếu quy tắc đầu tiên khớp và trả 403, Spring Security có xét quy tắc tiếp theo không?

**Đáp án:** không. “First match” có nghĩa chọn policy một lần, dù policy cho phép hay từ chối.

**Câu 3.** `anyRequest().denyAll()` có chặn được `/api/admin/users` khi `/api/**.permitAll()` đứng đầu không?

**Đáp án:** không. Request đã được matcher đầu tiên chọn, nên không đến fallback.

**Câu 4.** Tại sao `@GetMapping("/api/admin/users")` không chứng minh rule `/api/admin/**` được xét trước `/api/**`?

**Đáp án:** Spring MVC chọn controller mapping theo cơ chế riêng; Spring Security áp dụng authorization rule theo thứ tự khai báo.

**Câu 5.** Hai `SecurityFilterChain` cùng khớp `/api/admin`; nếu chain đầu tiên deny, chain thứ hai có được dùng không?

**Đáp án:** không. `FilterChainProxy` chọn chain khớp đầu tiên; chain sau chỉ được thử khi chain trước **không match**.

**Câu 6.** `securityMatcher("/api/**")` có nghĩa là mọi URL ngoài API sẽ bị deny?

**Đáp án:** không. Nếu không có chain nào khác match, URL ngoài `/api/**` có thể không được Spring Security bảo vệ.

**Câu 7.** Vì sao cần test `ANALYST` bị 403 khi truy cập `/api/reports/admin`?

**Đáp án:** nếu ai đó đưa `/api/reports/**` lên trước rule admin, test này sẽ thất bại và phát hiện quyền bị mở quá rộng.

**Câu 8.** Khi dùng `HttpMethod.GET` matcher, có thể bỏ qua HEAD không?

**Đáp án:** không nên suy luận như vậy; một handler `@GetMapping` có thể xử lý HEAD trong Spring MVC, trong khi security matcher chỉ giới hạn GET. Cần xác định rõ policy HEAD.

## 12. Ghi nhớ

- **Trong `authorizeHttpRequests`, chỉ rule đầu tiên có matcher khớp được áp dụng**, kể cả khi rule đó từ chối.
- **Rule đặc thù trước, rule rộng sau, fallback cuối**; `anyRequest().denyAll()` chỉ bảo vệ request chưa được matcher trước chọn.
- **Hai cấp first-match khác nhau:** chọn `SecurityFilterChain` theo `securityMatcher` và thứ tự chain, sau đó chọn authorization rule theo `requestMatchers`.
- `@GetMapping`/`@RequestMapping` có cơ chế chọn handler độc lập; đừng đồng nhất độ đặc hiệu MVC với độ ưu tiên của rule security.
- Matcher có thể xét HTTP method, path, servlet mapping, dispatch và matcher custom; test endpoint thật và các phương thức HTTP quan trọng.
- **Test denied case** phát hiện rule bị shadow tốt hơn chỉ kiểm tra các response thành công.
- Bảo vệ HTTP cần đi cùng kiểm tra quyền trên từng tài nguyên ở service khi nghiệp vụ yêu cầu.

### Tài liệu chính thức

- Spring Security — Authorize HTTP Requests, first matching rule: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Multiple SecurityFilterChain và securityMatcher: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — FilterChainProxy architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — MockMvc integration: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — @WithMockUser testing: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework — Mapping Requests, specificity và HTTP HEAD: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
