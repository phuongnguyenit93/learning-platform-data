# Chuỗi dự phòng để bảo vệ các đường dẫn chưa được chuỗi khác bao phủ

> **Phạm vi:** Spring Security 6 trên **Servlet stack** (Spring Boot 3.x, Spring MVC, Java 17+). Bài học thuộc **Cấu hình bảo mật**, giải thích cách thiết kế một **`SecurityFilterChain` dự phòng (fallback/catch-all)** để request không khớp các chuỗi chuyên biệt vẫn chịu chính sách bảo vệ rõ ràng. Đây là cơ chế chọn chuỗi HTTP security trong Servlet; Spring WebFlux có cơ chế `SecurityWebFilterChain` riêng.

## 1. Vấn đề: đường dẫn mới có thể vô tình nằm ngoài mọi chuỗi bảo mật

Một ứng dụng có thể chia cấu hình thành nhiều `SecurityFilterChain`: chain riêng cho `/api/**`, chain cho đường dẫn quản trị, chain cho giao diện web, v.v. Việc chia nhỏ này hữu ích vì mỗi nhóm có thể có xác thực, session, CSRF hoặc cách trả lỗi khác nhau.

Nhưng nếu **không có chain nào phù hợp** với request, `FilterChainProxy` không thực thi các security filter thuộc những chain đó cho request ấy; lời gọi có thể tiếp tục tới servlet/controller. Do đó một đường dẫn mới như `/reports` có thể **không nhận được yêu cầu đăng nhập** như người lập trình tưởng, dù trong dự án đang tồn tại nhiều bean `SecurityFilterChain`.

Ví dụ cấu hình chưa đủ phạm vi:

```java
// ĐOẠN MINH HỌA RỦI RO: chỉ có một chain, không phải cấu hình hoàn chỉnh.
@Bean
@Order(1)
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Giả sử đây là **chain duy nhất** và ứng dụng có controller `GET /reports`. Chain trên chỉ xét request khớp `/api/**`; `/reports` không khớp nên không đi qua các security filter do chain này cung cấp. Trong Spring Boot thông thường, khi bạn đã khai báo bean `SecurityFilterChain` tùy chỉnh, chuỗi mặc định của Boot không tự xuất hiện như một lớp bảo vệ phụ. Nếu không có cơ chế bảo vệ khác, `GET /reports` có thể trở thành endpoint công khai ngoài ý muốn.

**Mục tiêu của fallback:** đặt một chain cuối cùng có phạm vi bao phủ các request còn lại và chính sách mặc định được chủ động lựa chọn, thường là `anyRequest().authenticated()`.

## 2. FilterChainProxy chọn chuỗi bảo mật như thế nào?

Trên Servlet stack, container thường gọi `DelegatingFilterProxy` hướng tới Spring bean `springSecurityFilterChain` (thường là `FilterChainProxy`). Khi request đến, `FilterChainProxy` đi qua danh sách `SecurityFilterChain` **theo thứ tự đã sắp** và chọn **chain đầu tiên có `RequestMatcher` phù hợp**.

```text
HTTP GET /reports
    |
    v
Servlet container -> DelegatingFilterProxy -> FilterChainProxy
                                             |
                                             v
                           SecurityFilterChain @Order(1)
                           securityMatcher("/api/**")
                           match? NO
                                             |
                                             v
                           SecurityFilterChain @Order(2)
                           securityMatcher("/admin/**")
                           match? NO
                                             |
                                             v
                           Fallback SecurityFilterChain @Order(3)
                           mặc định match mọi request
                           match? YES
                                             |
                                             v
                           các security filters của fallback
                           -> authenticate / authorize
                           -> cho đi tiếp hoặc trả lỗi
```

Có ba quy tắc nền tảng:

1. **First match wins.** Chỉ chain đầu tiên khớp được chọn; filter của các chain còn lại không tự ghép thêm vào chuỗi đang chạy.
2. **`securityMatcher(...)` xác định phạm vi áp dụng của cả chain.** Bên trong chain, các `requestMatchers(...)` thuộc `authorizeHttpRequests` mới xác định quyền cho từng request mà chain đó nhận.
3. **Chain dự phòng phải match mọi request còn lại và nằm sau chain chuyên biệt.** Có thể bỏ `securityMatcher(...)` trên fallback vì matcher mặc định của một `HttpSecurity` thông thường là mọi request. Khi cần tường minh, có thể dùng `AnyRequestMatcher.INSTANCE`; không được vô tình giới hạn fallback về `/web/**` hoặc `/api/**`.

Bảng phân biệt ba quyết định:

| Câu hỏi | Nơi cấu hình | Ý nghĩa |
| --- | --- | --- |
| Chuỗi nào nhận `/reports`? | `@Order` trên bean `SecurityFilterChain` và `http.securityMatcher(...)` | Lựa chọn **một** chain |
| Trong chain đã chọn, `/reports` được phép làm gì? | `authorizeHttpRequests` với `requestMatchers` và `anyRequest` | Quy tắc authorization |
| Một request bị từ chối sẽ ra 401, 403 hay redirect? | Entry point, authentication mechanism và exception handling của chain đã chọn | Cách phản hồi khi chưa xác thực/không đủ quyền |

Một câu lệnh `.anyRequest().authenticated()` ở **bên trong** chain chỉ bao phủ mọi request **đã được chain ấy chọn**, không mở rộng `securityMatcher` của chain ra toàn ứng dụng.

## 3. Mẫu cấu hình fallback đúng

Mẫu đơn giản có một chain chuyên biệt cho API và một chain cuối:

```java
@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                // Không đặt securityMatcher: chain này mặc định match mọi request.
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Đây là **đoạn cấu hình minh họa**, cần đặt trong dự án Spring Boot/Spring Security với các import `@Configuration`, `@Bean`, `@Order`, `SecurityFilterChain`, `HttpSecurity` và `Customizer`. Phần 5 bên dưới cung cấp bộ tệp đầy đủ để chạy.

Trong cấu hình này:

- `GET /api/public` → chọn chain API → được phép không đăng nhập nhờ `permitAll()`.
- `GET /api/orders` → chọn chain API → cần xác thực.
- `GET /public` → không khớp `/api/**` → chọn fallback → được phép không đăng nhập.
- `GET /reports` → không khớp API → chọn fallback → cần xác thực, dù đường dẫn này mới được thêm vào ứng dụng.

Việc `@Order(1)` đứng trước `@Order(2)` là thiết yếu. **Không đặt chain match-all lên trước chain API**: nếu fallback đứng đầu, nó nhận tất cả request và chain API sẽ không được sử dụng, làm mất các cấu hình chuyên biệt như session, CORS, CSRF hoặc quy tắc quyền của API.

### Khi cần nhiều chain hơn

Ví dụ thứ tự sau phù hợp với các phạm vi tách biệt:

```text
@Order(10) -> securityMatcher("/api/**")       -> chính sách API
@Order(20) -> securityMatcher("/admin/**")     -> chính sách quản trị
@Order(90) -> không khai báo securityMatcher   -> fallback cho phần còn lại
```

Con số `@Order` chỉ là thứ tự ưu tiên, không phải độ mạnh của bảo mật: **giá trị nhỏ hơn có ưu tiên cao hơn**. Đặt giá trị rõ ràng cho các chain để tránh thứ tự không minh bạch khi nhiều bean cùng tồn tại.

Không được đặt fallback có matcher chuyên biệt như `securityMatcher("/home/**")` rồi coi đó là catch-all. Nếu viết matcher tường minh, có thể dùng:

```java
http.securityMatcher(
        org.springframework.security.web.util.matcher.AnyRequestMatcher.INSTANCE
);
```

Đoạn trên chỉ thể hiện cách đặt matcher; thông thường **bỏ `securityMatcher` trong fallback dễ đọc hơn**.

## 4. Chọn chính sách mặc định: authenticated, denyAll hay permitAll?

**Cách chọn fallback là quyết định an ninh**, không phải chỉ là kỹ thuật sắp thứ tự.

| Chính sách của fallback | Kết quả | Khi cân nhắc |
| --- | --- | --- |
| `anyRequest().authenticated()` | Request còn lại phải có danh tính hợp lệ | Phổ biến cho ứng dụng có endpoint nội bộ cần đăng nhập |
| `anyRequest().denyAll()` | Từ chối mọi request chưa có quy tắc cho phép cụ thể | Môi trường yêu cầu **fail closed** và rà soát endpoint mới |
| `anyRequest().permitAll()` | Cho phép request không khớp các chuỗi trước đó | Chỉ phù hợp nếu **chủ ý** để toàn bộ phần còn lại là public; không phải mặc định an toàn |

`authenticated()` xác minh người gọi có danh tính, **không tự kiểm tra quyền nghiệp vụ**. Nếu `/admin` chỉ dành cho quản trị, fallback có thể thêm quy tắc `requestMatchers("/admin/**").hasRole("ADMIN")` **trước** `anyRequest().authenticated()`, hoặc tách chain quản trị riêng. Đừng coi “đã đăng nhập” đồng nghĩa “được phép làm mọi thao tác”.

`denyAll()` hữu ích nếu muốn endpoint mới phải được khai báo rõ mới mở được. Khi dùng, phải bảo đảm những endpoint hợp lệ như `/login`, health check, static resources, callback hoặc trang lỗi được xử lý đúng bằng chain thích hợp hay quy tắc cho phép có chủ đích. Mọi ngoại lệ `permitAll()` phải càng cụ thể càng tốt.

**Dễ nhầm:** `permitAll()` trong `authorizeHttpRequests` vẫn giữ request đi qua security filter chain phù hợp. Ngược lại, `web.ignoring()` loại URL khỏi các xử lý security filters bình thường và có thể tạo vùng không được bảo vệ; hãy ưu tiên `permitAll()` khi cần public endpoint nhưng vẫn muốn hưởng lợi từ security headers hoặc cơ chế chung.

## 5. Dự án Java 17+ chạy được và kiểm thử tự động

Ví dụ dùng **Spring Boot 3.3.5 / Spring Security 6.x / Java 17 / Gradle 8.5**. Có hai chain và một tập endpoint cụ thể. Mục tiêu là chứng minh rằng **cả đường dẫn chưa có controller cũng phải bị fallback kiểm tra trước khi trả 404**.

### 5.1. Cấu trúc dự án

```text
fallback-chain-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    SecurityConfig.java
    DemoController.java
  src/test/java/demo/
    SecurityConfigTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'fallback-chain-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

### 5.2. Lớp khởi động

`src/main/java/demo/DemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 5.3. Hai SecurityFilterChain và tài khoản demo

`src/main/java/demo/SecurityConfig.java`:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
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
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("study123"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
```

Tài khoản `learner / study123` là dữ liệu học tập cục bộ để chạy `curl` và kiểm thử. Mật khẩu đã được băm bằng BCrypt trước khi lưu trong `InMemoryUserDetailsManager`. Với ứng dụng thật, không hard-code tài khoản/mật khẩu trong mã nguồn, và sử dụng HTTPS cho HTTP Basic.

Điểm cần quan sát: **fallback không có `securityMatcher(...)`**, chỉ có `authorizeHttpRequests`. Vì vậy nó match request còn lại sau chain API, rồi yêu cầu xác thực trừ `/public`. Hai chain đều dùng HTTP Basic để kết quả 401 dễ kiểm chứng; ứng dụng thật có thể chọn cơ chế xác thực khác theo từng chain.

### 5.4. Controller

`src/main/java/demo/DemoController.java`:

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api-public";
    }

    @GetMapping("/api/orders")
    public String apiOrders() {
        return "api-orders";
    }

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/admin")
    public String adminPage() {
        return "admin";
    }
}
```

Không có handler cho `/future/feature`. Ta dùng URL đó để kiểm tra fallback bảo vệ ngay cả những đường dẫn chưa được triển khai.

### 5.5. Kiểm thử Spring Security bằng MockMvc

`src/test/java/demo/SecurityConfigTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityConfigTest {

    @Autowired
    MockMvc mvc;

    @Test
    void explicitPublicEndpointsAllowAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("api-public"));
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void apiChainRejectsAnonymousCaller() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void fallbackRejectsAnonymousCaller() throws Exception {
        mvc.perform(get("/admin"))
                .andExpect(status().isUnauthorized());
        mvc.perform(get("/future/feature"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsReachProtectedControllers() throws Exception {
        mvc.perform(get("/api/orders").with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("api-orders"));
        mvc.perform(get("/admin").with(httpBasic("learner", "study123")))
                .andExpect(status().isOk())
                .andExpect(content().string("admin"));
    }

    @Test
    void authenticatedRequestToUnknownPathBecomesNotFound() throws Exception {
        mvc.perform(get("/future/feature").with(httpBasic("learner", "study123")))
                .andExpect(status().isNotFound());
    }
}
```

Bài kiểm thử quan trọng nhất là `fallbackRejectsAnonymousCaller()`: `/future/feature` **chưa tồn tại trong controller** nhưng request chưa xác thực vẫn nhận **401** vì fallback chạy trước Spring MVC. Khi xác thực hợp lệ, request được phép đi tới MVC và lúc đó mới nhận **404** do không tìm thấy handler. Trạng thái thực tế có thể khác nếu ứng dụng đã cấu hình exception handling, login redirect hoặc một reverse proxy phía trước; ở đây ta dùng cấu hình HTTP Basic đã nêu.

### 5.6. Chạy dự án và quan sát

Cài JDK 17+ và Gradle tương thích (ví dụ Gradle 8.5). Tại thư mục dự án, chạy:

```bash
gradle test
gradle bootRun
```

Nếu dự án có Gradle wrapper, thay `gradle` bằng `./gradlew` (Linux/macOS) hoặc `.\gradlew.bat` (Windows).

Từ terminal khác:

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/orders
curl -i http://localhost:8080/public
curl -i http://localhost:8080/admin
curl -i http://localhost:8080/future/feature
curl -i -u learner:study123 http://localhost:8080/api/orders
curl -i -u learner:study123 http://localhost:8080/admin
curl -i -u learner:study123 http://localhost:8080/future/feature
```

Kết quả dự kiến **với cấu hình demo** (bỏ qua những HTTP header do server sinh ra, chỉ xét status/body):

| Request | Chain được chọn | HTTP status | Body khi 200 |
| --- | --- | --- | --- |
| `GET /api/public`, anonymous | API | **200** | `api-public` |
| `GET /api/orders`, anonymous | API | **401** | — |
| `GET /public`, anonymous | Fallback | **200** | `public` |
| `GET /admin`, anonymous | Fallback | **401** | — |
| `GET /future/feature`, anonymous | Fallback | **401** | — |
| `GET /api/orders`, Basic hợp lệ | API | **200** | `api-orders` |
| `GET /admin`, Basic hợp lệ | Fallback | **200** | `admin` |
| `GET /future/feature`, Basic hợp lệ | Fallback | **404** | — |

**Không dùng 404 của một URL chưa có controller để kết luận nó được bảo vệ.** Cần kiểm tra trường hợp **chưa xác thực** trước; khi fallback yêu cầu xác thực và chưa có credentials, security xử lý trước khi MVC quyết định có handler hay không.

## 6. Những cấu hình sai dễ tạo lỗ hổng

### 6.1. Tưởng `anyRequest().authenticated()` của API bảo vệ toàn bộ ứng dụng

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
```

`anyRequest` chỉ áp dụng **trong phạm vi `/api/**`** của chain đó. Không bảo vệ `/admin` hoặc `/orders` nếu không có chain khác bao phủ. Giải pháp là thêm chain fallback match-all sau các chain cụ thể.

### 6.2. Đặt fallback ở ưu tiên cao hơn API

```text
SAI:
@Order(1) -> fallback (match tất cả)
@Order(2) -> API (match /api/**, nhưng không bao giờ được chọn)
```

Điều này có thể khiến request API đi qua chính sách dành cho web/fallback và mất các giới hạn API riêng. Giải pháp: đặt chain chuyên biệt trước, fallback sau; chứng minh thứ tự bằng các bài kiểm thử cho từng nhóm URL.

### 6.3. Gọi một chain `/web/**` là “fallback”

```java
// Đây chỉ là chain chuyên biệt cho /web/**, KHÔNG phải catch-all.
http.securityMatcher("/web/**")
    .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
```

`/reports` không khớp `/web/**`. Nếu cần fallback, để chain cuối match mọi request hoặc dùng matcher thực sự bao phủ toàn bộ phạm vi mong muốn.

### 6.4. Cho phép cả fallback vì “không biết URL này là gì”

```java
// Cẩn trọng: mở mọi URL chưa match chain trước đó.
.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
```

Đây không phải “dự phòng bảo vệ”. Nó làm URL mới mặc định public. Với bài toán yêu cầu bảo vệ đường dẫn chưa có chuỗi bao phủ, chọn `authenticated()` hoặc `denyAll()` tùy chính sách.

### 6.5. Mất quyền truy cập các endpoint public, login hoặc error

Fallback mặc định yêu cầu xác thực có thể vô tình bảo vệ `/login`, tài nguyên CSS/JS, health endpoint hoặc callback. Cần quyết định rõ URL nào public, URL nào yêu cầu role và đặt matcher trước luật cuối `anyRequest`. Với form login, đảm bảo **login page và login processing URL** được áp dụng đúng chain; URL đăng nhập do một chain cấu hình có thể không khả dụng nếu URL đó không nằm trong matcher của chain.

Không sử dụng wildcard công khai quá rộng chỉ để làm cho giao diện chạy. Kiểm thử cả request bình thường và luồng đăng nhập/đăng xuất/CSRF.

### 6.6. `web.ignoring()` gây hiểu lầm rằng fallback vẫn bảo vệ

`web.ignoring()` làm request bỏ qua các security filter thường áp dụng, vì vậy một vùng đã được ignore không nên được coi là được fallback bảo vệ. Khi cần trang public nhưng vẫn muốn security headers và xử lý chung, cấu hình `permitAll()` trong chain phù hợp thường dễ kiểm soát hơn.

### 6.7. Một matcher khó thấy bỏ sót URL

Đừng chỉ kiểm thử `/api/items` mà bỏ qua các biến thể đường dẫn có/không dấu gạch chéo cuối, URL encode, chữ hoa/chữ thường, servlet path, endpoint version mới hoặc matcher MVC khác với matcher mong đợi. Matcher cụ thể có thể phụ thuộc loại `RequestMatcher` và cấu hình ứng dụng. Viết test bằng đúng URL thực tế và bảo đảm fallback nhận phần không match.

### 6.8. Tin rằng fallback bảo vệ mọi cổng và servlet context của hệ thống

Fallback chỉ hoạt động cho **request thực sự đi qua `DelegatingFilterProxy` / `FilterChainProxy` tương ứng**. Một Servlet context khác, management server ở cổng riêng, reverse proxy trước ứng dụng hoặc URL bị loại khỏi filter mapping có thể cần cấu hình riêng. Không suy rộng chain fallback của một ứng dụng sang mọi thành phần hạ tầng.

## 7. Cách quan sát và gỡ lỗi chain selection

Khi một endpoint có kết quả không mong đợi, kiểm tra theo thứ tự:

1. **Request có đi vào Spring Security Servlet hay không?** Xác nhận `springSecurityFilterChain` proxy đã đăng ký cho đường dẫn và dispatcher type đang xét.
2. **Các `SecurityFilterChain` đang có là những chain nào?** Ghi lại `@Order`, `securityMatcher`, rule authorization và cơ chế xác thực cho từng chain.
3. **Chain đầu tiên match request là chain nào?** Một chain match-all đứng trước sẽ làm các chain sau trở nên vô hiệu cho URL đó.
4. **Request matcher trong `authorizeHttpRequests` của chain đã chọn áp dụng luật nào?** Quy tắc `permitAll` đặt quá rộng có thể cho phép nhiều URL hơn dự kiến.
5. **Lỗi trả về thuộc loại nào?** HTTP 401 thường là chưa xác thực trong ví dụ HTTP Basic; 403 liên quan bị từ chối truy cập hoặc CSRF; 302 có thể do form login. Status còn phụ thuộc cấu hình.
6. **Endpoint có được MVC ánh xạ tới controller không?** Đừng nhầm lỗi 404 sau xác thực với việc request không qua bảo mật.

Trong môi trường phát triển, có thể tạm bật log ở mức DEBUG để quan sát việc bảo vệ request:

```properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
logging.level.org.springframework.security=DEBUG
```

Không bật log nhạy cảm ở mức quá chi tiết trên môi trường sản xuất. Log có thể chứa thông tin request; tránh ghi token, cookie hoặc credentials. Việc xem message “Securing ...” chỉ là tín hiệu; kiểm thử hành vi 401/403/200 vẫn cần thiết.

### Ma trận regression test nên có

| Loại đường dẫn | Anonymous | Người dùng hợp lệ | Giá trị kiểm chứng |
| --- | --- | --- | --- |
| Public có chủ đích | 200 (hoặc response public dự kiến) | Hoạt động | Không khóa nhầm public |
| API chuyên biệt | 401 theo HTTP Basic (nếu cần login) | 200/403 theo quyền | API chain được chọn |
| Đường dẫn nội bộ do fallback bao phủ | 401 theo HTTP Basic | 200/403 theo quyền | Fallback không bỏ sót |
| **Đường dẫn mới hoặc chưa có handler** | **401** nếu fallback yêu cầu authentication | **404** nếu handler chưa có | Không mở vô tình URL mới |
| Đường dẫn nhạy cảm yêu cầu role | 401 khi chưa login | 403 nếu sai role | `authenticated()` không thay role checks |

Đối với endpoint chỉ nhận POST/PUT/DELETE, test thêm CSRF, content type và method cụ thể. Trong cấu hình mặc định trên Servlet, CSRF có thể trả **403** trước một số bước authorization; không giả định mọi request chưa login đều phải trả 401 trong mọi trường hợp.

## 8. Thay đổi chính sách và kiểm thử an toàn

Nếu ứng dụng muốn “mọi route phải khai báo mới được sử dụng”, fallback có thể chuyển từ `authenticated()` sang `denyAll()`:

```java
// Biến thể chính sách, không nằm trong demo runnable ở trên.
@Bean
@Order(99)
SecurityFilterChain denyUnknown(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .build();
}
```

Biến thể này **phải thay thế fallback hiện tại**, không thêm như chain thứ ba phía sau một catch-all đã match trước đó; nếu thêm sau thì không có cơ hội chạy. `denyAll` chặn cả request đã xác thực, do đó cần chain hoặc quy tắc riêng cho các URL hợp lệ. Thiết kế này phù hợp nơi việc xuất hiện endpoint mới cần phê duyệt chính sách.

Ngược lại, với ứng dụng cho phép nhiều người dùng đã xác thực truy cập những route chung, `authenticated()` là mặc định thực tế hơn. Dù chọn cách nào, hãy bổ sung **một kiểm thử cho URL giả định chưa được khai báo** để phát hiện sớm việc fallback bị xóa, đổi matcher hoặc đẩy lên sai thứ tự.

## 9. Câu hỏi tự kiểm tra

1. **Vì sao chỉ có `.securityMatcher("/api/**")` và `anyRequest().authenticated()` vẫn có thể bỏ hở `/reports`?** Vì `anyRequest` chỉ áp dụng sau khi chain API được chọn; `/reports` không khớp matcher của chain.
2. **Vì sao fallback phải đứng cuối?** `FilterChainProxy` chọn chain đầu tiên khớp; một catch-all đứng đầu sẽ che khuất các chain chuyên biệt.
3. **Fallback có nhất thiết cần viết `securityMatcher("/**")` không?** Không; với `HttpSecurity` thông thường, không đặt `securityMatcher` nghĩa là match mọi request. Có thể dùng `AnyRequestMatcher.INSTANCE` khi cần tường minh.
4. **Khác nhau giữa `authenticated()` và `denyAll()` ở fallback?** `authenticated()` cho người đã xác thực đi tiếp nếu không có luật hạn chế khác; `denyAll()` từ chối mọi request của chain đó.
5. **`GET /future/feature` chưa có controller, tại sao anonymous nhận 401 trước 404 trong demo?** Fallback kiểm tra authentication trước khi MVC tìm handler; sau khi authentication thành công, MVC mới trả 404.
6. **`permitAll()` có bỏ qua Spring Security filter chain không?** Không; nó là quy tắc authorization bên trong chain. `web.ignoring()` mới bỏ qua những security filters bình thường cho request.
7. **Đã cấu hình fallback rồi có cần test API chain riêng không?** Có. Cần đảm bảo fallback không đứng trước và không vô tình thay thế luật, auth mechanism, CSRF hoặc session policy chuyên biệt của API.

**Ghi nhớ:** Khi dùng nhiều `SecurityFilterChain`, hãy xác định **chain chuyên biệt trước, chain fallback match-all cuối**; áp dụng chính sách bảo vệ mặc định cho URL còn lại; kiểm thử cả URL mới/chưa có handler. Việc có `anyRequest().authenticated()` trong một chain giới hạn **không** bảo đảm bảo vệ toàn bộ ứng dụng.
