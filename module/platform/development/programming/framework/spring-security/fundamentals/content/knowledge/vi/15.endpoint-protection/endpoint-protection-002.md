# Cho phép endpoint công khai bằng `permitAll`

> **Module:** Spring Security - fundamentals  
> **Nhóm:** Bảo vệ endpoint  
> **Trọng tâm:** Dùng `permitAll()` để cho phép request phù hợp đi qua **bước kiểm tra quyền ở cấp HTTP**, đồng thời giữ ứng dụng bên trong Spring Security filter chain.

## 1. Mục tiêu

Sau bài này, bạn cần làm được những việc sau:

- Giải thích chính xác `permitAll()` cho phép điều gì và những lớp bảo vệ nào **vẫn còn hiệu lực**.
- Cấu hình đường dẫn công khai như `GET /public/ping` hoặc trang đăng nhập, song song với endpoint yêu cầu xác thực.
- Hiểu cách `requestMatchers(...)`, HTTP method, thứ tự luật và `anyRequest()` quyết định request nào được phép.
- Phân biệt `permitAll()` với `authenticated()`, `anonymous()`, `denyAll()`, `web.ignoring()` và `securityMatcher(...)`.
- Kiểm chứng hành vi bằng HTTP request và Spring Security MockMvc test, đặc biệt là tình huống **POST công khai vẫn cần CSRF token** khi CSRF đang bật.

## 2. `permitAll()` thực sự làm gì?

Một endpoint được gọi là **công khai** khi chính sách truy cập của ứng dụng cho phép client sử dụng endpoint đó mà không bắt buộc phải đăng nhập. Trong Spring Security Servlet hiện đại, ta có thể khai báo:

~~~java
// Đoạn minh họa DSL ở bên trong cấu hình HttpSecurity.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

`permitAll()` là một quyết định của **authorization**: đối với request khớp matcher, bước kiểm tra quyền truy cập này trả kết quả cho phép mà không cần tra cứu một `Authentication` cụ thể để ra quyết định. Trong mô hình `authorizeHttpRequests` của Spring Security 6+, quy tắc `permitAll` cũng không cần lấy `Authentication` từ HTTP session chỉ để kiểm tra quyền.

Điểm quan trọng: **`permitAll()` không có nghĩa request bỏ qua Spring Security.** Nếu request vẫn khớp `SecurityFilterChain`, các filter liên quan vẫn có thể được thực thi, ví dụ:

- Bộ lọc xử lý cơ chế xác thực được cấu hình như HTTP Basic, Bearer token hoặc form login.
- CSRF protection đối với request phù hợp với chính sách CSRF.
- Các security response headers và các tích hợp bảo vệ khác được cấu hình trong chain.
- Filter tùy biến và các kiểm tra tại method/business layer nếu ứng dụng có chúng.

Vì vậy, câu phát biểu chính xác là:

> **“Endpoint được phép truy cập mà không yêu cầu xác thực tại quy tắc HTTP authorization này.”**  
> Không phải “endpoint đã được tắt mọi kiểm tra bảo mật”.

### Luồng xử lý khái niệm

~~~text
GET /public/ping  -- không gửi credentials
       |
       v
Chọn SecurityFilterChain phù hợp
       |
       v
Các security filter áp dụng cho chain
       |  (authentication, headers, CSRF nếu phù hợp...)
       v
AuthorizationFilter
       |
       +-- request khớp /public/ping -> permitAll -> GRANTED
       |
       v
Controller xử lý request
       |
       v
HTTP 200 + nội dung trả về
~~~

Nếu controller bị lỗi, đường dẫn không tồn tại, phương thức HTTP không được hỗ trợ hoặc một filter khác từ chối, client vẫn có thể nhận `4xx`/`5xx`. `permitAll` không bảo đảm status cuối cùng luôn là `200 OK`.

## 3. Các kiểu luật trong cùng `authorizeHttpRequests`

Bảng sau mô tả các luật thường dùng ở lớp authorization Servlet:

| Luật | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `permitAll()` | Bỏ yêu cầu xác thực/quyền tại luật này; request phù hợp được cấp quyền truy cập | Landing page, health probe công khai |
| `authenticated()` | Cần danh tính được Spring Security công nhận là đã xác thực | `/api/me` |
| `hasAuthority("report:read")` | Cần authority khớp chính xác chuỗi được yêu cầu | Đọc báo cáo nội bộ |
| `hasRole("ADMIN")` | Theo mặc định yêu cầu authority `ROLE_ADMIN` | Endpoint quản trị |
| `anonymous()` | Chỉ cho các request được Spring Security đánh giá là anonymous | Một số trang chỉ dành cho khách |
| `denyAll()` | Luôn từ chối trong bước HTTP authorization | Đường dẫn chưa công bố |

`authenticated()` **không** đồng nghĩa được thực hiện mọi thao tác. `permitAll()` cũng không phải `anonymous()`: người đã đăng nhập vẫn được phép gọi endpoint công khai, trừ khi một chính sách khác hạn chế họ.

### Chọn vùng công khai thật rõ

Giả sử ứng dụng có:

~~~text
GET  /public/ping       -> công khai
POST /public/feedback   -> công khai ở bước authorization
GET  /api/me            -> cần xác thực
GET  /admin/reports     -> cần quyền ROLE_ADMIN
mọi request khác        -> từ chối theo mặc định
~~~

Cấu hình rõ ràng có thể viết:

~~~java
// Đoạn trích trong SecurityFilterChain; import được thể hiện trong ví dụ đầy đủ.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
    .requestMatchers(HttpMethod.POST, "/public/feedback").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

**Vì sao có `HttpMethod.GET` và `HttpMethod.POST`?** Một đường dẫn có thể hỗ trợ nhiều phương thức với mức độ nhạy cảm khác nhau. `requestMatchers("/public/**").permitAll()` sẽ rộng hơn, áp dụng cho các HTTP method khớp pattern. Nếu chỉ muốn `GET /public/ping` công khai, matcher có HTTP method thể hiện ý đồ chính xác hơn.

**Vì sao dùng `anyRequest().denyAll()`?** Vì các endpoint mới xuất hiện sau này sẽ không vô tình được công khai; người phát triển phải khai báo quyền trước khi mở. Nếu thiết kế ứng dụng yêu cầu mọi endpoint còn lại đều được dùng sau khi đăng nhập, `anyRequest().authenticated()` có thể phù hợp. Chọn default dựa trên chính sách thực, không theo thói quen.

## 4. Ví dụ Spring Boot 3.3 / Java 17+ chạy được

Ví dụ sau dùng Spring MVC trên Servlet với Spring Security 6.x thông qua Spring Boot 3.3.5. Ta tạo **hai endpoint công khai** (`GET`, `POST`) và **một endpoint riêng tư**, giữ CSRF mặc định để quan sát rõ phạm vi `permitAll`.

### 4.1. Cấu trúc file

~~~text
public-endpoints-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── PublicEndpointsApplication.java
    │   ├── SecurityConfig.java
    │   └── PublicController.java
    └── test/java/demo/
        └── PublicEndpointSecurityTest.java
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'public-endpoints-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
~~~

**Giải thích:** Starter Web tạo HTTP controller ở Servlet stack; Starter Security bổ sung filter chain; dependency Spring Security Test cung cấp bộ công cụ tạo authentication/CSRF giả lập khi kiểm thử. Không cần khai báo trực tiếp phiên bản Spring Security vì Spring Boot BOM quản lý phiên bản tương thích.

### 4.2. Khởi động ứng dụng

File `src/main/java/demo/PublicEndpointsApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PublicEndpointsApplication {
    public static void main(String[] args) {
        SpringApplication.run(PublicEndpointsApplication.class, args);
    }
}
~~~

### 4.3. Khai báo `SecurityFilterChain`

File `src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/ping")
                    .permitAll()
                .requestMatchers(HttpMethod.POST, "/public/feedback")
                    .permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-password"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(alice);
    }
}
~~~

**Giải thích từng quyết định:**

1. `GET /public/ping` và `POST /public/feedback` nhận `permitAll`. Đây là **hai luật authorization**, không phải cấu hình tắt filter chain.
2. `/api/**` cần `authenticated()`, nên `GET /api/me` không được gọi chỉ với phiên anonymous.
3. Những URL chưa được khai báo bị `denyAll()`. Với fallback này, endpoint mới phải được khai báo chính sách trước khi dùng.
4. `httpBasic()` cung cấp cơ chế xác thực đơn giản để thử bằng `curl -u`.
5. `InMemoryUserDetailsManager` và mật khẩu `demo-password` chỉ phục vụ ví dụ cục bộ. Production cần nơi lưu credential, quản trị user và chính sách mật khẩu thích hợp.
6. **Không có** `csrf.disable()`. Spring Security sẽ giữ mặc định bảo vệ CSRF trên những request phù hợp; nhờ đó `POST` công khai thể hiện một ranh giới khác với authorization.

### 4.4. Tạo controller

File `src/main/java/demo/PublicController.java`:

~~~java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PublicController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @PostMapping("/public/feedback")
    public String feedback() {
        return "received";
    }

    @GetMapping("/api/me")
    public String me(Authentication authentication) {
        return "user=" + authentication.getName();
    }
}
~~~

`ping()` không đòi hỏi `Authentication`. `me()` có thể dùng argument `Authentication` vì rule `/api/**.authenticated()` yêu cầu request đã xác thực. Trong ứng dụng phức tạp, business logic vẫn phải kiểm tra quyền/ownership tài nguyên nếu cần.

### 4.5. Chạy và quan sát

Từ thư mục project, dùng JDK 17+ và một bản Gradle 8.x tương thích với plugin Spring Boot 3.3:

~~~bash
gradle bootRun
~~~

Mở terminal khác và gọi:

~~~bash
curl -i http://localhost:8080/public/ping
~~~

Kết quả cốt lõi: **HTTP 200**, body:

~~~text
pong
~~~

Không gửi `Authorization` hoặc session cookie mà vẫn nhận body `pong`: luật `permitAll` đã cho phép request này.

~~~bash
curl -i http://localhost:8080/api/me
~~~

Với cấu hình HTTP Basic ở trên, request không có credential hợp lệ thường nhận **HTTP 401** cùng header `WWW-Authenticate`. Đây là kết quả của quy tắc `authenticated()`, khác với `permitAll()`.

~~~bash
curl -i -u alice:demo-password http://localhost:8080/api/me
~~~

Kết quả cốt lõi: **HTTP 200**, body:

~~~text
user=alice
~~~

Để thấy `permitAll` **không bỏ qua CSRF**, thử:

~~~bash
curl -i -X POST http://localhost:8080/public/feedback
~~~

Với CSRF protection mặc định và không gửi CSRF token, request POST này bị từ chối, thông thường **HTTP 403**. URL đã được `permitAll`, nhưng request vẫn phải vượt qua các filter bảo mật phù hợp.

> Các ví dụ `curl` chỉ trình bày status và body chính, không liệt kê mọi response header hoặc trang lỗi do framework tạo. Test ở phần kế tiếp minh họa cách cung cấp CSRF token hợp lệ. Nếu ứng dụng đã thay đổi CSRF, authentication entry point, filter chain hoặc error handling, kết quả HTTP có thể khác.

## 5. Kiểm thử tự động để chứng minh quy tắc

File `src/test/java/demo/PublicEndpointSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PublicEndpointSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetWorksWithoutCredentials() throws Exception {
        mvc.perform(get("/public/ping"))
            .andExpect(status().isOk())
            .andExpect(content().string("pong"));
    }

    @Test
    void privateGetRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGetCanReadThePrincipal() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("user=alice"));
    }

    @Test
    void publicPostStillNeedsCsrfWhenCsrfIsEnabled()
            throws Exception {
        mvc.perform(post("/public/feedback"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/public/feedback").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("received"));
    }
}
~~~

**Giải thích:** Các static import bị xuống dòng vẫn là cú pháp Java hợp lệ vì câu lệnh `import static ...;` chỉ kết thúc ở dấu chấm phẩy. `httpBasic(...)` gắn HTTP Basic credentials cho request; `csrf()` tạo CSRF token hợp lệ trong request MockMvc; chúng không làm biến đổi quy tắc `permitAll`.

Chạy:

~~~bash
gradle test
~~~

Kỳ vọng: **4 tests passed**. Đây là một kịch bản minh họa độc lập để chạy trong project được tạo theo hướng dẫn; status test phản ánh các default/configuration đã ghi ở trên. Không dùng thử nghiệm này làm bằng chứng các ứng dụng khác có cùng thiết lập CSRF, session hay entry point.

Bốn tình huống được kiểm chứng:

| Request | Credentials / CSRF | Kỳ vọng |
| --- | --- | --- |
| `GET /public/ping` | Không có credentials | `200`, `pong` |
| `GET /api/me` | Không có credentials | `401` dưới cấu hình HTTP Basic |
| `GET /api/me` | HTTP Basic của Alice | `200`, `user=alice` |
| `POST /public/feedback` | Không có CSRF token | `403` |
| `POST /public/feedback` | CSRF token hợp lệ trong MockMvc | `200`, `received` |

**Lưu ý quan trọng:** `gradle test` là lệnh kiểm tra; kết quả `4 tests passed` là kết quả kỳ vọng của fixture được mô tả, không phải log đã đo trên máy bạn.

## 6. Matcher phải cụ thể và đúng thứ tự

Trong `authorizeHttpRequests`, Spring Security xét các rule đã khai báo theo thứ tự và sử dụng **quy tắc đầu tiên khớp request**. Một matcher quá rộng đặt trước có thể khiến luật chặt hơn phía sau không bao giờ được dùng.

**Ví dụ sai:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

`/**` đã khớp `/admin/reports` trước. Luật `hasRole("ADMIN")` không còn cơ hội bảo vệ request tương ứng.

**Cách viết đúng ý đồ:**

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/ping").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Không để `anyRequest()` trước các luật chi tiết. Nếu ứng dụng có nhiều đường dẫn, dành phần công khai cho những nhóm dễ nhận biết (`/public/**`, tài nguyên tĩnh, callback riêng), tránh một glob rộng để “giải quyết nhanh” lỗi 401/403.

### Chỉ mở đúng HTTP method

Ví dụ cùng `/catalog`:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/catalog").permitAll()
    .requestMatchers(HttpMethod.POST, "/catalog")
        .hasAuthority("catalog:write")
    .anyRequest().authenticated()
);
~~~

`GET` được xem công khai; `POST` đòi quyền ghi. Không nên thay hai luật bằng `requestMatchers("/catalog").permitAll()` nếu endpoint hỗ trợ cả hành động đọc và tạo dữ liệu.

### Điều gì xảy ra khi controller không tồn tại?

`permitAll` chỉ quyết định **authorization**. Nó không tự tạo HTTP mapping:

~~~text
GET /public/does-not-exist
    -> Nếu /public/** được permitAll, đi tiếp tới ứng dụng
    -> Không có handler phù hợp
    -> Thường là 404, không phải 200
~~~

Nếu request có phương thức không được controller hỗ trợ, có thể nhận `405 Method Not Allowed` hoặc một response lỗi khác sau các filter. Không coi mọi `4xx` trên public URL là bằng chứng `permitAll` thất bại.

## 7. `permitAll` khác `web.ignoring()` như thế nào?

Đây là khác biệt dễ gây lỗi nhất khi bảo vệ endpoint và tài nguyên tĩnh.

| Cách cấu hình | Request có đi qua Spring Security filter chain không? | Ảnh hưởng |
| --- | --- | --- |
| `requestMatchers("/css/**").permitAll()` bên trong chain | **Có**, nếu chain đó khớp request | Không bắt buộc authz, vẫn có thể nhận security headers, CORS/CSRF và các filter liên quan |
| `web.ignoring().requestMatchers("/css/**")` | **Không** qua Spring Security chain đối với đường dẫn bị ignore | Spring Security không áp dụng security headers và các filter của nó cho request đó |
| `http.securityMatcher("/api/**")` trên một chain | Chọn **phạm vi request** của chain đó | Không phải một luật “permit” cho endpoint bên trong chain; chain khác có thể xử lý hoặc request không có chain phù hợp |

Trong Spring Security 6+, tài liệu chính thức khuyến nghị ưu tiên `permitAll` thay vì bỏ qua filter chain, kể cả với tài nguyên tĩnh. Một lý do là response security headers vẫn hữu ích cho CSS/JS/images. Việc kiểm tra authorization của `permitAll` cũng không cần lấy `Authentication` từ session, nên tránh được nhược điểm hiệu năng của một số cách cũ.

**Không dùng `web.ignoring()` chỉ để cho phép người chưa đăng nhập tải asset.** Nếu thật sự cần loại bỏ một request khỏi Spring Security, cần xem xét hậu quả cho toàn bộ filter/security headers thay vì coi đó là cách viết ngắn của `permitAll`.

## 8. `requestMatchers` và `securityMatcher` hoạt động ở hai tầng khác nhau

Khi có nhiều `SecurityFilterChain`, Spring Security chọn chain phù hợp với request (theo thứ tự chain được cấu hình). **Bên trong chain đã được chọn**, các luật `authorizeHttpRequests` mới đánh giá điều kiện.

~~~text
Request
   |
   v
SecurityFilterChain nào khớp securityMatcher?
   |
   +-- Chain 1: /api/**   -> luật authorizeHttpRequests của Chain 1
   |
   +-- Chain 2: mọi URL còn lại -> luật của Chain 2
   |
   v
Chỉ chain được chọn áp dụng
~~~

Ví dụ khái niệm:

~~~java
// Đoạn cấu hình minh họa; đây là hai @Bean trong một @Configuration.
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll()
        )
        .build();
}
~~~

Các import bổ sung bao gồm `org.springframework.core.annotation.Order`. **Đây là cấu hình thay thế để hiểu cơ chế nhiều chain, không ghép nguyên xi vào project ví dụ ở phần 4.** Khi `/api/public/ping` được gọi, request khớp API chain. Việc đặt `/api/public/**.permitAll()` chỉ trong fallback chain sẽ không giúp ích, vì chain đó không được chọn cho URL `/api/**`.

Nếu một request không khớp **bất kỳ** `SecurityFilterChain` nào, nó có thể nằm ngoài sự bảo vệ của Spring Security. Luôn kiểm tra phạm vi chain và có fallback chain phù hợp khi cấu hình nhiều chain.

## 9. Những lớp bảo vệ vẫn áp dụng cho endpoint công khai

### 9.1. CSRF đối với hành động thay đổi trạng thái

CSRF bảo vệ một số kiểu ứng dụng dùng cookie/session tự động gửi kèm từ trình duyệt. Mặc định, Spring Security Servlet yêu cầu CSRF token với các HTTP method “không an toàn” như `POST`, `PUT`, `PATCH`, `DELETE`.

~~~text
POST /public/feedback
  permitAll ở authorization: Có
  CSRF token yêu cầu theo cấu hình: Có
  Không gửi CSRF token: 403 (với cấu hình ví dụ)
~~~

Không tự suy luận “POST là public thì phải `csrf.disable()`”. Nếu đó là API stateless chỉ dùng bearer token trong Authorization header và không dựa vào ambient browser credentials, hãy đánh giá nhu cầu CSRF theo mô hình đe dọa thực tế. Khi cần ngoại lệ, giới hạn theo matcher CSRF đúng endpoint và giải thích lý do; không tắt toàn bộ CSRF của ứng dụng web có session để sửa một test.

### 9.2. Authentication filter vẫn có thể phản ứng với credentials xấu

Với một endpoint public, client không cần gửi credential. Nhưng nếu client **chủ động** gửi Bearer token không hợp lệ tới ứng dụng được cấu hình OAuth2 Resource Server, authentication filter có thể từ chối token đó **trước khi đến luật `permitAll`**. Cũng vậy, một header HTTP Basic sai có thể dẫn đến phản hồi xác thực tùy filter/entry point.

Không cam kết rằng “`permitAll` luôn trả 200 kể cả khi request chứa credential sai”. Test riêng cả **không có credential** và **có credential không hợp lệ**, theo đúng cơ chế xác thực thực tế của chain.

### 9.3. CORS là cơ chế khác

Một public API không đồng nghĩa JavaScript ở mọi origin đều tự do đọc response. Browser áp dụng same-origin policy và CORS; Spring Security và Spring MVC/WebFlux cần được cấu hình CORS đúng nhu cầu. Preflight `OPTIONS` có thể được xử lý khác request thật; cho phép public `GET` bằng `permitAll` **không tự động tạo CORS response headers**.

### 9.4. Method security và business rule vẫn có hiệu lực

Một endpoint có thể được `permitAll` ở tầng HTTP nhưng handler gọi service có `@PreAuthorize("hasRole('ADMIN')")` hoặc kiểm tra quyền theo tài nguyên. Khi method security đã bật và lời gọi đi qua cơ chế áp dụng bảo mật, policy đó vẫn có thể từ chối. Hãy tránh cấu hình mâu thuẫn giữa tuyên bố public và logic bắt buộc login phía dưới; nếu cần public chỉ một phần dữ liệu, thiết kế API riêng cho bản công khai.

### 9.5. Headers, session, logging

Security headers như `X-Content-Type-Options` hoặc `X-Frame-Options` vẫn có thể được thêm qua chain. `permitAll` **không ngăn** ứng dụng chủ động tạo session khi cần, cũng không phải chỉ thị “không lưu cookie”. Việc không lấy `Authentication` từ session **cho chính quyết định authorization này** không đồng nghĩa không filter hoặc component nào khác từng truy cập session.

## 10. Ví dụ áp dụng: static assets, trang đăng nhập, health và API

### Static assets

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/css/**", "/js/**", "/images/**").permitAll()
    .anyRequest().authenticated()
);
~~~

Ví dụ này phù hợp khi các path tương ứng thực sự dùng để phục vụ asset công khai. Với Spring Boot, có thể dùng `PathRequest.toStaticResources().atCommonLocations()` khi thích hợp để diễn tả các vị trí tài nguyên tĩnh phổ biến thay vì tự liệt kê. Hãy xem đường dẫn thực tế và nơi ứng dụng đóng gói asset.

### Trang đăng nhập và tài nguyên phụ trợ

~~~java
// Đoạn cấu hình minh họa ở cấp ứng dụng có form login.
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/login", "/css/**", "/js/**").permitAll()
    .anyRequest().authenticated()
).formLogin(Customizer.withDefaults());
~~~

Form login mặc định cung cấp cơ chế trang/login processing tương ứng. Đối với **custom login page**, cần tạo MVC controller/template phù hợp và đảm bảo endpoint login, CSS/JS được phép truy cập khi chưa đăng nhập, tránh vòng lặp chuyển hướng. `permitAll` ở tầng HTTP authorization không thay thế việc cấu hình login processing hay CSRF.

### Health probe

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/actuator/health").permitAll()
    .anyRequest().authenticated()
);
~~~

Đây là ví dụ về **luật truy cập**, không tự cài Actuator hoặc bật endpoint. Nếu dùng Spring Boot Actuator, cần có dependency, cấu hình exposure và quy tắc truy cập tương ứng. Tránh mặc định công khai toàn bộ `/actuator/**` chỉ vì muốn public health probe; các endpoint quản trị khác có thể lộ thông tin nhạy cảm.

### API cung cấp dữ liệu public nhưng có endpoint riêng tư

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/articles").permitAll()
    .requestMatchers(HttpMethod.GET, "/articles/*").permitAll()
    .requestMatchers(HttpMethod.POST, "/articles")
        .hasAuthority("article:write")
    .anyRequest().authenticated()
);
~~~

Pattern của `requestMatchers` chịu ngữ nghĩa matcher mà Spring Security chọn cho stack/configuration thực tế. Luôn test đúng URL, method và trường hợp cạnh; không giả định dấu sao khớp mọi cấp đường dẫn trong mọi matcher.

## 11. WebFlux dùng `permitAll` như thế nào?

Đối với Spring WebFlux, cấu hình tương ứng sử dụng `SecurityWebFilterChain` và `ServerHttpSecurity.authorizeExchange(...)`:

~~~java
// Đoạn mã cấu hình minh họa, đặt trong ứng dụng Spring WebFlux.
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/public/ping").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Các import liên quan gồm `org.springframework.security.web.server.SecurityWebFilterChain`, `org.springframework.security.config.web.server.ServerHttpSecurity`, `org.springframework.security.config.Customizer`, `org.springframework.http.HttpMethod` và `org.springframework.context.annotation.Bean`.

**Tương đồng về ngữ nghĩa:** Endpoint public không cần authz ở luật được chỉ định, nhưng các WebFilter/security integration khác vẫn có thể áp dụng.

**Khác biệt về API:** Servlet dùng `SecurityFilterChain` + `authorizeHttpRequests` + `requestMatchers`; WebFlux dùng `SecurityWebFilterChain` + `authorizeExchange` + `pathMatchers`. Không trộn hai DSL vào cùng một configuration. Trong reactive code, thông tin xác thực được duy trì qua Reactor Context và đọc qua `ReactiveSecurityContextHolder` khi cần; việc `permitAll` không thay đổi nguyên tắc này.

## 12. Checklist khi mở một endpoint công khai

Trước khi thêm `permitAll`, trả lời bốn câu hỏi kỹ thuật:

1. **Phạm vi URL/method:** Có đúng chỉ `GET /public/ping` cần public, hay cả `POST /public/**`? Nếu khác nhau, tách matcher theo method.
2. **Lớp bảo vệ khác:** Endpoint có thay đổi dữ liệu, dùng cookie/session, nhận Bearer token, hoặc cần CORS không? Kiểm tra CSRF/authentication filter/CORS như các chính sách riêng.
3. **Dữ liệu và business logic:** Endpoint public có thể trả về PII, nội dung nội bộ, dữ liệu cross-tenant hoặc cần rate limiting không? Public authorization không có nghĩa dữ liệu nào cũng an toàn để công khai.
4. **Kiểm thử:** Test request **không có credential**, request có credential hợp lệ/không hợp lệ khi thích hợp, HTTP method không được phép và quy tắc fallback.

Nếu là endpoint dùng cho webhook bên thứ ba, public ở cấp `authenticated()` có thể là cần thiết nhưng **không đồng nghĩa chấp nhận mọi nguồn gửi**. Cần thực hiện xác minh chữ ký/HMAC hoặc cơ chế tin cậy do nhà cung cấp quy định ở tầng tương ứng và xử lý replay theo chính sách. Không biến webhook thành public không kiểm chứng chỉ vì nó không dùng session login.

## 13. Các lỗi thường gặp

| Lỗi | Tác động | Hướng xử lý |
| --- | --- | --- |
| Đặt `/**.permitAll()` trước các luật bảo vệ | Matcher rộng cho qua endpoint nội bộ | Đặt matcher cụ thể trước, fallback an toàn |
| Dùng `web.ignoring()` cho asset chỉ vì muốn tải CSS khi chưa login | Bỏ qua security headers và các filter của Spring Security | Dùng `permitAll()` cho asset cần công khai |
| Nghĩ `permitAll()` tắt CSRF | POST công khai vẫn bị `403` | Hiểu CSRF là filter độc lập, cấu hình theo threat model |
| Nghĩ `permitAll()` luôn trả `200` | 404, 405, lỗi controller, invalid credentials vẫn có thể xảy ra | Kiểm tra từng tầng xử lý request |
| Đặt permit rule trong sai `SecurityFilterChain` | Rule không được dùng | Kiểm tra `securityMatcher` và thứ tự chain |
| Dùng pattern quá rộng như `/actuator/**` | Có thể công khai thông tin quản trị | Chỉ mở `/actuator/health` khi cần |
| Chỉ test bằng một browser đã login | Không biết endpoint có thật sự public | Test ẩn danh bằng MockMvc/curl |
| Bỏ qua HTTP method | Có thể công khai cả POST/DELETE khi chỉ định public GET | Dùng matcher theo `HttpMethod` |
| Public URL nhưng service vẫn đòi `@PreAuthorize` | API trả 403 dù luật HTTP permit | Làm rõ policy ở từng tầng, test end-to-end |
| Tin rằng `permitAll` tạo ra endpoint | URL có thể 404/405 | Tạo controller/handler/static mapping thực tế |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Nếu `GET /public/ping` được `permitAll`, client không đăng nhập có gọi được không?

**Đáp án:** Có thể qua bước HTTP authorization mà không cần đăng nhập. Request vẫn phải qua các filter phù hợp và controller xử lý thành công.

**Câu 2.** Vì sao `POST /public/feedback` được `permitAll` nhưng lại nhận `403`?

**Đáp án:** Khi CSRF protection áp dụng, `POST` có thể cần CSRF token. `permitAll` chỉ cho phép ở lớp authorization, không vô hiệu hóa `CsrfFilter`.

**Câu 3.** `permitAll` có giống `web.ignoring()` không?

**Đáp án:** Không. `permitAll` là luật của request authorization trong một security chain; `web.ignoring()` bỏ qua toàn bộ Spring Security chain đối với URL được ignore.

**Câu 4.** Vì sao `requestMatchers("/**").permitAll()` đặt trước `requestMatchers("/admin/**").hasRole("ADMIN")` nguy hiểm?

**Đáp án:** Vì matcher `/**` khớp trước, nên `/admin/**` được permit ở luật rộng; luật admin đặt sau không còn tác dụng với request ấy.

**Câu 5.** Khi có hai `SecurityFilterChain`, vì sao `permitAll` ở chain B có thể không áp dụng cho `/api/public/ping`?

**Đáp án:** Nếu chain A được chọn trước theo `securityMatcher("/api/**")`, chỉ các luật authorization trong chain A được áp dụng cho request đó.

**Câu 6.** Vì sao không nên public `/actuator/**` chỉ để mở health probe?

**Đáp án:** Wildcard đó có thể bao gồm những endpoint quản trị khác. Chỉ mở đúng endpoint được phép tiết lộ, ví dụ `GET /actuator/health`, và xác minh cấu hình Actuator thực tế.

## 15. Tóm tắt và tài liệu tham khảo

`permitAll()` **mở quyền truy cập ở một bước authorization cụ thể**. Nó là lựa chọn tự nhiên cho endpoint/trang/tài nguyên công khai vì vẫn giữ request trong Spring Security chain. Để dùng an toàn, chọn matcher đúng URL và method, đặt luật theo thứ tự cụ thể, giữ fallback bảo vệ, và kiểm chứng các lớp CSRF, authentication, CORS, method security cùng cơ chế xác thực token có liên quan.

Đọc thêm từ tài liệu chính thức:

- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
