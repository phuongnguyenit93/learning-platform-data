# Bảo vệ tài nguyên tĩnh, endpoint quản trị và thông tin chẩn đoán

Một ứng dụng Spring Boot thường có nhiều loại HTTP resource: CSS/JavaScript dành cho mọi người, trang và API của người dùng đã đăng nhập, thao tác quản trị, health checks, metrics, cùng các công cụ chẩn đoán như log, thread dump, environment hay heap dump. **Các loại tài nguyên này không được mặc định dùng một chính sách truy cập.** CSS của trang đăng nhập phải tải được trước khi authentication; trang quản trị đòi kiểm tra role; health endpoint cần đủ thông tin cho probes nhưng không nên lộ cấu trúc hạ tầng; heap dump và thông tin môi trường thường không nên xuất hiện trên HTTP production.

Mục tiêu bài học là thiết kế **bề mặt truy cập tối thiểu**, kết hợp **Spring Security authorization**, **Spring Boot Actuator exposure** và **giới hạn mạng/giới hạn nội dung**. Các ví dụ chính dành cho **Spring Boot 3.x, Spring MVC/Servlet, Spring Security 6.x, Java 17+**. Phần riêng cho WebFlux được đánh dấu là API khác, không trộn với chương trình MVC.

**Ba lớp phòng vệ:**

1. **Không expose khi không cần:** endpoint không có HTTP mapping thì không thể bị gọi theo route đó.
2. **Bắt buộc xác thực và phân quyền:** endpoint đã được expose vẫn phải được bảo vệ theo role/permission phù hợp.
3. **Giới hạn thông tin và đường mạng:** người có quyền chỉ xem dữ liệu cần thiết, kênh quản trị không mặc nhiên mở ra Internet.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt tài nguyên tĩnh công khai, trang authenticated, endpoint admin, endpoint OPS, health probe và chẩn đoán nhạy cảm.
- Dùng `PathRequest.toStaticResources().atCommonLocations()` với `permitAll()` thay vì loại tất cả static requests khỏi filter chain.
- Hiểu `SecurityFilterChain`, `securityMatcher`, `requestMatchers`, `@Order`, `hasRole`, `authenticated` và `anyRequest`.
- Hiểu khác biệt giữa **enabled**, **exposed over HTTP/JMX** và **authorized** của Spring Boot Actuator.
- Dùng `EndpointRequest.toAnyEndpoint()` và `EndpointRequest.to("health")` cho Actuator thay vì hardcode matcher thiếu linh hoạt.
- Xây dựng ứng dụng Spring Boot có CSS công khai, trang authenticated, API admin, diagnostic hạn chế và Actuator được bảo vệ.
- Kiểm tra các phản hồi 200, 401, 403, 404 bằng `curl` và `MockMvc`.
- Thiết kế health liveness/readiness không làm lộ chi tiết, quản lý management port, sanitization, CSRF và mạng.
- Nhận ra các anti-pattern dễ dẫn đến rò rỉ dữ liệu hoặc mất khả năng quan sát khi deploy.

## 2. Bảng phân loại tài nguyên và quyền truy cập

Trước khi viết security config, hãy lập danh sách endpoint và mức nhạy cảm:

| Nhóm | Ví dụ | Quy tắc khởi đầu | Lưu ý |
| --- | --- | --- | --- |
| Static public | `/css/site.css`, `/js/app.js`, logo, favicon | `permitAll()` cho path phù hợp | Vẫn giữ security headers; không đặt secrets vào static |
| Trang public | `/`, `/login`, `/about` | `permitAll()` có chủ đích | Đừng mở `/**` |
| Trang/API người dùng | `/account`, `/orders` | `authenticated()` + kiểm tra quyền dữ liệu | Login không đủ để xem dữ liệu user khác |
| Quản trị | `/admin/**` | `hasRole("ADMIN")` hoặc policy mạnh hơn | Protect mọi HTTP methods |
| Diagnostic riêng | `/internal/diagnostics` | `hasRole("OPS")`, giới hạn nội dung | Không coi “URL khó đoán” là bảo mật |
| Health probes | `/actuator/health`, `/livez`, `/readyz` khi bật | Truy cập vừa đủ cho LB/kubelet, output tối thiểu | Health DOWN có thể trả 503 |
| Metrics | `/actuator/metrics`, `/actuator/prometheus` | OPS/scraper nội bộ | Không dùng label chứa token hoặc user ID |
| Info về cấu trúc | `/actuator/beans`, `/actuator/mappings`, `/actuator/conditions` | Thường không expose ở production | Lộ cấu trúc app/beans/mappings |
| Cấu hình | `/actuator/env`, `/actuator/configprops` | Thường không expose | Sanitization không thay thế exposure control |
| Dữ liệu nhạy cảm | `/actuator/heapdump`, `/actuator/logfile`, `/actuator/httpexchanges` | Không expose trừ khi điều tra có kiểm soát | Có thể chứa secrets, PII, session data |
| Thao tác thay đổi | `/actuator/loggers` và `/actuator/shutdown` | Hạn chế rất chặt hoặc disabled | Một số operations có POST/PUT/DELETE |

**Mở đường dẫn HTTP không đồng nghĩa dữ liệu an toàn để công bố.** File ở `src/main/resources/static` có thể được Spring MVC đưa lên web; đặt nhầm `backup.zip`, key, export CSV khách hàng, log hoặc heap dump trong thư mục đó là lỗi thiết kế trước khi nói đến Spring Security.

## 3. Spring Security chọn filter chain và authorization rule

Trong ứng dụng Servlet, request đi qua `FilterChainProxy` của Spring Security. Có thể có nhiều `SecurityFilterChain`, mỗi chain có matcher để quyết định nó xử lý nhóm URL nào. Spring Security chọn **chain phù hợp đầu tiên**; trong chain, các authorization matchers được xét theo thứ tự rule.

```text
Browser / HTTP client
         |
         v
 Servlet filters -> Spring Security FilterChainProxy
         |
         +-- Chain #1: securityMatcher(EndpointRequest.toAnyEndpoint())
         |      +-- health -> permitAll
         |      +-- các endpoint Actuator khác -> ROLE_OPS
         |
         +-- Chain #2: còn lại
                +-- static CSS/JS/images -> permitAll
                +-- GET / -> permitAll
                +-- /admin/** -> ROLE_ADMIN
                +-- /internal/diagnostics -> ROLE_OPS
                +-- mọi route khác -> authenticated
         |
         v
 DispatcherServlet -> Controller/Resource Handler/Actuator
```

Hai khái niệm khác nhau:

- `http.securityMatcher(...)`: **toàn chain** có được áp dụng cho request hay không.
- `authorizeHttpRequests(...requestMatchers(...))`: **rule phân quyền trong chain đã match**.

Nếu chỉ có một chain match Actuator mà không có chain cho phần còn lại của app, những request không match Actuator có thể nằm ngoài bảo vệ như dự kiến. Tạo custom chain đồng nghĩa tác giả phải hiểu rõ security auto-configuration đã nhường quyền thế nào.

### 3.1. Authentication và authorization

- **Authentication** chứng minh người gọi là ai.
- **Authorization** quyết định người gọi đó có được thực hiện hành động cụ thể hay không.
- `authenticated()` chỉ yêu cầu danh tính đã xác thực; nó **không** kiểm tra user có sở hữu đơn hàng hoặc quyền quản trị.
- `hasRole("OPS")` mặc định kiểm tra authority `ROLE_OPS`, không phải chuỗi `OPS` đơn thuần.
- `hasAuthority("OPS")` kiểm tra chính authority `OPS`.
- `permitAll()` cho phép quyền truy cập theo rule, không có nghĩa request tự động bỏ qua headers, filters hoặc các biện pháp an toàn còn lại.

Phân quyền theo URL chỉ là một lớp. Với dữ liệu đa tenant, service còn phải kiểm tra user ID/tenant ID/record owner và các điều kiện nghiệp vụ.

### 3.2. Thứ tự rule rất quan trọng

**Sai** vì rule `/**` rộng đứng trước:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
);
```

Rule admin có thể không bao giờ được tới lượt. Sửa bằng cách đặt rule cụ thể trước fallback và kết thúc với `anyRequest().authenticated()` hoặc `denyAll()` tùy chính sách.

## 4. Static resources: permitAll thay vì ignoring

### 4.1. Static mapping của Spring Boot

Spring MVC/Boot 3.x thường tìm static resources ở:

```text
classpath:/META-INF/resources/
classpath:/resources/
classpath:/static/
classpath:/public/
```

`src/main/resources/static/css/site.css` được phục vụ theo mặc định tại `/css/site.css`. Có thể thay đổi `spring.mvc.static-path-pattern` hoặc `spring.web.resources.static-locations`. WebJars có xử lý đường dẫn `/webjars/**`.

Đừng nhầm file static với Thymeleaf template trong `templates`. Một trang HTML do controller render có thể yêu cầu CSS công khai; browser cần tải CSS ngay cả khi người dùng chưa login.

### 4.2. Cách mở đúng

Với Spring Boot 3.x Servlet:

```java
.requestMatchers(
    PathRequest.toStaticResources().atCommonLocations()
).permitAll()
```

Import `PathRequest` từ `org.springframework.boot.autoconfigure.security.servlet.PathRequest`. Matcher xử lý các nhóm tài nguyên phổ biến; nếu tự đổi resource locations hoặc static path pattern, hãy kiểm tra và bổ sung chính xác path cần public.

Các file như `robots.txt` hoặc favicon có thể cần rule thêm nếu không nằm trong common matcher:

```java
.requestMatchers("/favicon.ico", "/robots.txt").permitAll()
```

Đó là **snippet trong authorizeHttpRequests**, không phải chương trình độc lập.

### 4.3. Vì sao tránh web.ignoring?

Một pattern cũ:

```java
web.ignoring().requestMatchers("/css/**", "/js/**");
```

Nếu request bị bỏ hẳn khỏi security filter chain, nó có thể mất các security response headers do Spring Security thêm. Spring Security hiện khuyến nghị `permitAll` cho static resources; Spring Security 6 cũng đã cải thiện overhead của việc kiểm tra session cho các rule public.

`permitAll` **không** tự biến app thành an toàn hoàn toàn. Ví dụ Content Security Policy (CSP) phải được thiết kế theo từng web app; đừng giả định mọi header đều có default phù hợp.

### 4.4. Static “riêng tư” không còn đơn giản là static public

Nếu có tài liệu `/reports/private.pdf` hoặc file upload theo khách hàng, không đặt trong danh sách static `permitAll`. Dùng controller/download service có object-level authorization, hoặc protected object storage với signed URLs thời hạn ngắn. Nếu CDN hoặc NGINX phục vụ file trực tiếp mà không gọi Spring Boot, rules trong JVM **không chạy**. Cần bảo vệ ở CDN/storage/edge, không chỉ thêm `requestMatchers` phía backend.

## 5. Spring Boot Actuator: ba cánh cửa bảo mật khác nhau

Actuator cung cấp các endpoints vận hành như `health`, `info`, `metrics`, `env`, `beans`, `mappings`, `conditions`, `threaddump`, `heapdump` và `loggers`. Để một client thực sự dùng được một endpoint, phải thỏa đồng thời:

1. Endpoint tồn tại, được **enable** và có dependency cần thiết.
2. Endpoint được **expose** trên giao thức tương ứng (HTTP/JMX).
3. Request vượt qua **network policy** và **authentication/authorization**.

```text
Endpoint available?
     |
     +-- disabled/unavailable ---> không có endpoint tương ứng
     |
     v
Exposed over HTTP?
     |
     +-- no --------------------> không có HTTP mapping của endpoint
     |
     v
Network/proxy permits?
     |
     +-- no --------------------> bị chặn ngoài app
     |
     v
Spring Security permits?
     |
     +-- no --------------------> thường 401 hoặc 403
     |
     v
Endpoint trả thông tin hoặc thực hiện operation
```

**Boot 3.3 mặc định chỉ expose `health` qua HTTP/JMX.** Khi Spring Security có trên classpath và **không có** custom `SecurityFilterChain` bean, Boot tự bảo vệ các Actuator endpoint ngoài health. **Khi khai báo custom SecurityFilterChain**, Boot nhường quyền cấu hình web security và bạn phải bảo vệ Actuator lẫn các URL app khác.

### 5.1. Exposure và authorization là hai việc

Cấu hình chỉ expose ba endpoint:

```properties
management.endpoints.web.exposure.include=health,info,metrics
```

Dòng này không tự cho anonymous quyền đọc `metrics`. Ngược lại, cấu hình `hasRole("OPS")` cho `env` không tự expose `env` nếu chưa được include.

`management.endpoints.web.exposure.exclude` ưu tiên hơn `include`. Việc mở JMX dùng properties khác `management.endpoints.jmx.exposure.include/exclude`, nên đóng HTTP không đồng nghĩa đã đóng JMX.

**Không khuyến nghị production:**

```properties
management.endpoints.web.exposure.include=*
```

Cấu hình này có thể đưa nhiều endpoint được enable ra bề mặt HTTP, làm tăng rủi ro dù có Basic auth. Nếu cần điều tra tạm thời, ưu tiên chính xác ID cần dùng, private network, audit và rollback sau khi xong.

### 5.2. Bảng đánh giá độ nhạy của Actuator

| Endpoint | Dữ liệu/chức năng | Chính sách thường phù hợp |
| --- | --- | --- |
| `health` | Tình trạng dịch vụ | Output tối thiểu cho probes |
| `info` | Metadata được chủ động cung cấp | Kiểm tra không lộ build/commit/internal details không cần |
| `metrics`/`prometheus` | Metrics ứng dụng, JVM, HTTP | Chỉ OPS/scraper đáng tin; không dùng label có PII |
| `env`/`configprops` | Configuration/environment | Unexposed mặc định trong production, vẫn sanitize |
| `beans`/`mappings` | Cấu trúc Spring beans/HTTP routes | Không expose trừ trường hợp chẩn đoán được kiểm soát |
| `conditions` | Lý do auto-configuration | Thường không expose |
| `threaddump` | Thread stacks | Có thể tiết lộ thông tin nội bộ |
| `heapdump` | Ảnh chụp heap JVM | Rất nhạy cảm, có thể chứa secret, token, PII |
| `logfile` | Log ứng dụng | Có thể chứa session IDs, email, URLs, traces |
| `httpexchanges` | Metadata request/response gần đây, nếu có repository | Tiết lộ patterns và headers |
| `loggers` | Xem/chỉnh mức logging | Giới hạn role và thao tác ghi |
| `shutdown` | Dừng ứng dụng, disabled mặc định | Giữ disabled trừ nhu cầu cực kỳ đặc biệt |

“Đã authenticated” vẫn chưa đủ để tải heap dump hoặc thay đổi loggers. Thực tế cần phân quyền người và máy riêng, mạng quản trị, MFA/SSO, auditing và quy trình phê duyệt khi thích hợp.

## 6. Health endpoint và thông tin tối thiểu

`GET /actuator/health` có thể trả khi app đang khỏe:

```json
{"status":"UP"}
```

Đây là **ví dụ**; nếu app DOWN hoặc readiness chưa đạt, status và HTTP code có thể khác.

Spring Boot có:

```properties
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never
```

`show-details` chấp nhận `never`, `when-authorized`, `always`. Boot 3.3 mặc định `never`. Nếu chọn `when-authorized` mà không chỉ rõ `management.endpoint.health.roles`, mọi user authenticated có thể được xem là đủ điều kiện hiển thị details theo chính sách health endpoint; điều này đôi khi rộng hơn dự kiến.

**Không kết hợp `permitAll` cho health với `show-details=always` thiếu cân nhắc.** Cấu trúc database, cache, external APIs, health contributors hoặc thông báo lỗi không phải thông tin mà mọi client Internet cần biết.

### 6.1. Liveness và readiness

Trong Kubernetes, Boot có các health groups:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Boot hỗ trợ tự bật probes trong môi trường Kubernetes và có thể bật ở môi trường khác:

```properties
management.endpoint.health.probes.enabled=true
```

- **Liveness**: process còn hoạt động và có nên restart? Đừng đưa DB/shared dependency vào liveness chỉ để mỗi lần DB chết thì toàn bộ pods bị restart hàng loạt.
- **Readiness**: app có sẵn sàng nhận traffic? Cân nhắc external dependency theo khả năng phục vụ thực sự; không máy móc thêm toàn bộ dependencies.
- **Startup probe**: hữu ích với app khởi động chậm khi hạ tầng có nguy cơ kill trước khi xong startup.

Khi management chạy cổng riêng, probe chỉ kiểm tra management web server có thể bỏ sót lỗi trên main app port. Boot hỗ trợ:

```properties
management.endpoint.health.probes.add-additional-paths=true
```

để có `/livez` và `/readyz` trên main port trong điều kiện cấu hình phù hợp. Khi bật additional paths, cần cập nhật **application security chain** cho đúng hai đường này hoặc điều phối probe qua mạng đáng tin; đừng vô tình để kubelet nhận 401. Đồng thời không mở chúng rộng hơn nhu cầu hạ tầng.

## 7. Ví dụ Spring Boot 3.x Java 17+ chạy được

Demo gồm:

- `GET /`: text công khai.
- `GET /css/site.css`: CSS công khai qua Spring MVC static resource handling.
- `GET /account`: đòi user đăng nhập.
- `GET /admin/summary`: role ADMIN.
- `GET /internal/diagnostics`: role OPS.
- `GET /actuator/health`: health tối thiểu cho anonymous.
- `GET /actuator/info` và `/actuator/metrics`: chỉ role OPS.
- `/actuator/env`, `/heapdump` và các endpoint nhạy cảm khác **không được expose**.

Để kiểm thử nhanh bằng curl, dùng HTTP Basic và **hai user demo in-memory**. Đây chỉ là lab local, không dùng thông tin đăng nhập demo ở production.

### 7.1. Tạo dự án và dependencies

Dùng [Spring Initializr](https://start.spring.io/) chọn **Java 17+**, **Spring Boot 3.3.x** (hoặc bản 3.x tương thích), **Gradle/Groovy**, dependencies **Spring Web**, **Spring Security**, **Spring Boot Actuator**.

Trong `build.gradle` do Initializr tạo, khối dependency cốt lõi:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **snippet dependencies**, không phải `build.gradle` hoàn chỉnh độc lập. Initializr cung cấp plugins, repositories, version/BOM và Gradle Wrapper. Spring Security 6.x không dùng `WebSecurityConfigurerAdapter` theo các ví dụ cũ. Đừng trộn mã Spring Boot 4.x nếu chưa kiểm tra thay đổi starter/API.

Tạo các file:

```text
src/
  main/
    java/demo/
      SecureRuntimeApplication.java
      SecurityConfiguration.java
      ProtectedEndpoints.java
    resources/
      application.properties
      static/css/site.css
  test/
    java/demo/
      SecurityRulesTest.java
```

### 7.2. SecureRuntimeApplication.java

File `src/main/java/demo/SecureRuntimeApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecureRuntimeApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecureRuntimeApplication.class, args);
    }
}
```

Lớp khởi động ở package `demo` giúp phát hiện controller và cấu hình security cùng package.

### 7.3. SecurityConfiguration.java

File `src/main/java/demo/SecurityConfiguration.java`:

```java
package demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.autoconfigure.security.servlet.PathRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(EndpointRequest.to("health")).permitAll()
                .anyRequest().hasRole("OPS"))
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    PathRequest.toStaticResources().atCommonLocations())
                    .permitAll()
                .requestMatchers("/", "/favicon.ico").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/internal/diagnostics").hasRole("OPS")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        // Để Spring Security áp dụng CSRF mặc định.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(
            PasswordEncoder encoder,
            @Value("${demo.user-password}") String userPassword,
            @Value("${demo.ops-password}") String opsPassword) {
        return new InMemoryUserDetailsManager(
            User.withUsername("viewer")
                .password(encoder.encode(userPassword))
                .roles("USER")
                .build(),
            User.withUsername("operator")
                .password(encoder.encode(opsPassword))
                .roles("USER", "OPS", "ADMIN")
                .build());
    }
}
```

Giải thích:

1. `@Order(1)` làm Actuator chain được xét trước. `EndpointRequest.toAnyEndpoint()` match endpoints theo Actuator mapping hiện tại; nó phù hợp hơn hardcode `/actuator/**` nếu base path đổi.
2. `EndpointRequest.to("health")` match health và các subpaths của health group. Health được `permitAll`, mọi Actuator endpoint khác đã expose cần `ROLE_OPS`.
3. `@Order(2)` bảo vệ các URL còn lại. Static public được `permitAll`, route quản trị yêu cầu ADMIN, diagnostic riêng yêu cầu OPS.
4. `anyRequest().authenticated()` ngăn URL mới vô tình public khi chưa có rule riêng. Nó không thay object-level permission checks trong service.
5. `httpBasic` cho phép test curl. Không có `csrf.disable()` vì đây là ví dụ GET-only, và không có lý do tắt CSRF cho toàn ứng dụng.
6. Password demo được BCrypt hash khi khởi tạo. **BCrypt không biến các password ví dụ ngắn thành thông tin đăng nhập production phù hợp**; dùng identity provider/secret management thật ở hệ thống vận hành.

**Quan trọng:** custom `SecurityFilterChain` làm Boot auto-configuration bảo vệ Actuator nhường quyền. Phải có chain bảo vệ cả Actuator và application. Khi nhiều chains, quy tắc order và `securityMatcher` phải được test.

### 7.4. ProtectedEndpoints.java

File `src/main/java/demo/ProtectedEndpoints.java`:

```java
package demo;

import java.security.Principal;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProtectedEndpoints {

    @GetMapping("/")
    public String index() {
        return "public-page\n";
    }

    @GetMapping("/account")
    public ResponseEntity<String> account(Principal principal) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body("account=" + principal.getName() + "\n");
    }

    @GetMapping("/admin/summary")
    public ResponseEntity<String> adminSummary() {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body("admin-access=granted\n");
    }

    @GetMapping("/internal/diagnostics")
    public ResponseEntity<String> diagnostics() {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body("diagnostics=limited\n");
    }
}
```

`CacheControl.noStore()` dùng cho dữ liệu user/admin/diagnostic để hạn chế cache lưu response. Nó không thay authentication hoặc chống việc proxy/log ghi body. Endpoint `/internal/diagnostics` chỉ trả chuỗi ngắn; production diagnostic thực tế cần kiểm tra nội dung trả ra, masking và audit riêng.

### 7.5. Static CSS

File `src/main/resources/static/css/site.css`:

```css
body {
    margin: 2rem;
    font-family: sans-serif;
}

h1 {
    color: #234a75;
}
```

Nhờ static resource handler của Spring MVC, file này có thể truy cập bằng `GET /css/site.css`. Vì request đi qua security chain với `permitAll`, nó không cần Basic auth nhưng vẫn có thể nhận các security headers mặc định.

### 7.6. application.properties

File `src/main/resources/application.properties`:

```properties
server.port=8080

# Chỉ expose Actuator endpoints cần cho bài.
management.endpoints.web.exposure.include=health,info,metrics

# Không đưa thông tin component/health details cho khách ẩn danh.
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never

# Tắt discovery page; việc này KHÔNG thay security.
management.endpoints.web.discovery.enabled=false

# Không expose Actuator qua JMX trong ví dụ.
management.endpoints.jmx.exposure.exclude=*

# Giữ dữ liệu cấu hình được sanitize.
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never

# Giảm thông tin lỗi trả về từ Spring Boot.
server.error.include-message=never
server.error.include-stacktrace=never

# Chỉ dùng LOCAL DEMO. Production không dùng fallback passwords.
demo.user-password=${DEMO_USER_PASSWORD:local-user-only}
demo.ops-password=${DEMO_OPS_PASSWORD:local-ops-only}
```

Cần nhớ `management.endpoints.web.discovery.enabled=false` chỉ tắt trang liệt kê links, **không ngăn direct requests** tới endpoints đang expose. Bảo vệ chính vẫn là exposure list + security rules + network restrictions.

Trong production, không commit tài khoản demo/password cố định. Dùng secret manager, SSO, machine identity, MFA hoặc mTLS theo hệ thống; giới hạn cả số client có thể đến management port.

### 7.7. Khởi chạy

Tại thư mục project có Gradle Wrapper:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Đây là ứng dụng Spring có dependencies; `javac SecurityConfiguration.java` đơn lẻ không có classpath sẽ không biên dịch. Ứng dụng mặc định lắng nghe ở `http://localhost:8080` theo cấu hình demo nếu cổng chưa bị dùng.

Trong bài học, các mật khẩu fallback **chỉ cho local HTTP test**:

```text
viewer   / local-user-only
operator / local-ops-only
```

Để đặt mật khẩu khác bằng environment variables:

```bash
export DEMO_USER_PASSWORD='replace-local-user'
export DEMO_OPS_PASSWORD='replace-local-ops'
./gradlew bootRun
```

PowerShell:

```powershell
$env:DEMO_USER_PASSWORD = "replace-local-user"
$env:DEMO_OPS_PASSWORD = "replace-local-ops"
.\gradlew.bat bootRun
```

HTTP Basic gửi credential trong Authorization header có thể giải mã, nên **không dùng HTTP thường trên mạng không tin cậy**. Với production, dùng TLS và cơ chế identity được quản trị.

## 8. Kiểm chứng bằng curl: 200/401/403/404

### 8.1. Static công khai

```bash
curl -i http://localhost:8080/css/site.css
curl -i http://localhost:8080/
```

Kỳ vọng HTTP 200 cho cả hai. `/` trả text:

```text
public-page
```

Nếu CSS 404, kiểm tra file path và resource mapping; nếu CSS 401, xem matcher. **Không sửa CSS 404 bằng cách thêm permitAll bừa bãi.**

### 8.2. Trang cần authentication

```bash
curl -i http://localhost:8080/account
```

Kỳ vọng **401 Unauthorized** từ Basic security.

```bash
curl -i -u viewer:local-user-only \
  http://localhost:8080/account
```

Kỳ vọng 200 với body:

```text
account=viewer
```

### 8.3. Quản trị

```bash
curl -i -u viewer:local-user-only \
  http://localhost:8080/admin/summary
```

Kỳ vọng **403 Forbidden**: user đã login nhưng không có ROLE_ADMIN.

```bash
curl -i -u operator:local-ops-only \
  http://localhost:8080/admin/summary
```

Kỳ vọng 200, body:

```text
admin-access=granted
```

### 8.4. Diagnostic riêng

```bash
curl -i -u viewer:local-user-only \
  http://localhost:8080/internal/diagnostics

curl -i -u operator:local-ops-only \
  http://localhost:8080/internal/diagnostics
```

Kỳ vọng tương ứng 403 và 200; response khi đủ quyền:

```text
diagnostics=limited
```

### 8.5. Actuator health và metrics

```bash
curl -i http://localhost:8080/actuator/health

curl -i http://localhost:8080/actuator/metrics

curl -i -u viewer:local-user-only \
  http://localhost:8080/actuator/metrics

curl -i -u operator:local-ops-only \
  http://localhost:8080/actuator/metrics
```

Khi app khỏe, health thường 200 với status `UP` và không có component details. Metrics lần lượt 401, 403, 200 theo authentication và ROLE_OPS. Không tự giả định response health luôn 200: khi health DOWN, Boot có thể trả 503 theo status mapping.

### 8.6. Endpoint không được expose

`env` không nằm trong exposure list. Để tách lỗi route khỏi authentication, kiểm tra **bằng operator đã xác thực**:

```bash
curl -i -u operator:local-ops-only \
  http://localhost:8080/actuator/env
```

Kỳ vọng **404 Not Found** trong ví dụ. Anonymous gọi cùng URL có thể nhận 401 từ fallback application chain **trước khi MVC xác định URL không tồn tại**. Vì vậy 401 không chứng minh một endpoint đang expose, còn 404 không có nghĩa rule security đúng; cần xét cả exposure.

### 8.7. Ma trận kết quả

| Route | Anonymous | Viewer | Operator |
| --- | --- | --- | --- |
| `GET /` | 200 | 200 | 200 |
| `GET /css/site.css` | 200 | 200 | 200 |
| `GET /account` | 401 | 200 | 200 |
| `GET /admin/summary` | 401 | 403 | 200 |
| `GET /internal/diagnostics` | 401 | 403 | 200 |
| `GET /actuator/health` | 200 nếu UP | 200 nếu UP | 200 nếu UP |
| `GET /actuator/metrics` | 401 | 403 | 200 |
| `GET /actuator/env` | Có thể 401 từ fallback | 404 | 404 |

Bảng có điều kiện ứng dụng đang dùng HTTP Basic demo, Actuator exposure list và role assignments ở trên. Nếu đổi web stack, management context hoặc security entry point, status có thể khác; nên kiểm chứng theo môi trường thật.

## 9. Kiểm thử tự động bằng MockMvc

`spring-security-test` đã có trong dependency của mục 7.1. Tạo `src/test/java/demo/SecurityRulesTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void cssIsPublic() throws Exception {
        mvc.perform(get("/css/site.css"))
            .andExpect(status().isOk());
    }

    @Test
    void accountRequiresLogin() throws Exception {
        mvc.perform(get("/account"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotViewAdmin() throws Exception {
        mvc.perform(get("/admin/summary"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = {"USER", "OPS", "ADMIN"})
    void operatorCanViewAdmin() throws Exception {
        mvc.perform(get("/admin/summary"))
            .andExpect(status().isOk());
    }

    @Test
    void publicHealth() throws Exception {
        mvc.perform(get("/actuator/health"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(roles = "USER")
    void userCannotViewMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(roles = "OPS")
    void opsCanViewMetrics() throws Exception {
        mvc.perform(get("/actuator/metrics"))
            .andExpect(status().isOk());
    }
}
```

Chạy:

```bash
./gradlew test
```

`@WithMockUser` giả lập authentication trong test, không chứng minh password từ HTTP Basic được verify, cookie policy an toàn hoặc management port riêng đã cấu hình đúng. Kết hợp MockMvc, integration tests chạy HTTP thật và proxy/network tests. Nếu management được đưa sang web context/port khác, MockMvc của main application có thể không đại diện cho management listener đầy đủ.

## 10. Tách management port và network policy

Một cấu hình production có thể đặt Actuator ở một port khác:

```properties
server.port=8080
management.server.port=8081
management.server.address=127.0.0.1
management.endpoints.web.exposure.include=health,metrics
```

Đây là **phương án khác demo**, không phải các dòng thêm vào để giữ nguyên mọi test ở `:8080`. `management.server.address` chỉ có thể khác khi management port khác main port. Bind `127.0.0.1` hợp lý nếu scraper ở cùng host hoặc truy cập qua kênh port-forward có quyền; trong Kubernetes, pod khác không tự kết nối loopback của pod này được.

Nếu management port lắng nghe mọi interface và firewall mở ra Internet, chỉ tách port **không tạo ra mạng tin cậy**. Cần Security Groups/NetworkPolicy/service mesh/ingress ACL, TLS/mTLS và identity phù hợp.

Các Actuator security rules có thể chạy trong management web context riêng; kiểm chứng trên **port thật**, đừng suy rằng cấu hình filter của main server tự bảo vệ đúng mọi routes của management server. Đồng thời tránh expose public ingress tới `/actuator/**` chỉ vì monitoring từng cần truy cập.

### 10.1. Health probes qua main port

Boot 3.3 hỗ trợ additional paths:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Thông thường có `/livez`, `/readyz` ở main application port; health qua cổng management riêng không nhất thiết phát hiện vấn đề trên main port. Nếu bật additional paths, application chain ở ví dụ đang có `anyRequest().authenticated()` nên một kubelet không credentials có thể nhận 401. Cần mở **đúng paths**, giới hạn network nguồn probe và kiểm tra kết quả trong quá trình rolling deployment. Không dùng `anyRequest().permitAll()` để chữa probe fail.

## 11. Không để thông tin chẩn đoán lộ qua HTTP

### 11.1. env và configprops

`/actuator/env` và `/actuator/configprops` có thể công bố tên properties, nguồn cấu hình, và các giá trị được cho phép. Boot 3.3 mặc định **sanitize values** (ví dụ `******`). Để giữ chính sách rõ ràng:

```properties
management.endpoint.env.show-values=never
management.endpoint.configprops.show-values=never
```

`when-authorized` có thể cho phép authenticated users xem values tùy `management.endpoint.env.roles` hoặc roles riêng của endpoint; khi không đặt roles, điều kiện “authorized” có thể rộng hơn dự kiến. `always` tăng nguy cơ lộ dữ liệu; không bật bừa ở production. Dù values được che, tên properties/sources vẫn có thể tiết lộ kiến trúc. **Unexpose nếu không cần** là lớp phòng vệ đầu tiên.

### 11.2. Heap dumps và thread dumps

`heapdump` có thể chứa mật khẩu, session attributes, OAuth/access tokens, dữ liệu cá nhân còn trong memory. Nó không phải “file debug vô hại”. Lúc điều tra cần đường riêng, quyền cấp tạm, kiểm toán, mã hóa khi lưu và quy trình xóa. `threaddump` có thể tiết lộ tên classes, threads, stack frames và ngữ cảnh runtime; hạn chế tương tự.

Không đặt heapdump vào static directory hoặc public object storage sau khi lấy để chia sẻ nhanh. Đừng expose endpoint này qua CDN chỉ vì đã khóa bằng một Basic password yếu.

### 11.3. logfile, httpexchanges và metrics

Log file có thể chứa URI, headers, request IDs, email, exception và dữ liệu lỡ được ghi trong quá khứ. `httpexchanges` khi có repository phù hợp có thể ghi nhận metadata HTTP; kiểm soát retention và các fields nhạy cảm. Metrics nên dùng nhãn cardinality thấp như route template, status code, service; **không** gắn raw user ID, access token, URL chứa secret hay email vào metric tags. Một hệ thống observability tự nó cũng cần phân quyền, audit và retention.

### 11.4. loggers và các thao tác thay đổi trạng thái

Actuator `loggers` có thể hỗ trợ thay logging level khi endpoint/operation được expose; `shutdown` mặc định disabled. Tăng DEBUG/TRACE bất cẩn có thể làm tăng disk và in thông tin nhạy cảm. Một số Actuator operations dùng `POST`/`PUT`/`DELETE`, trong khi Spring Security có CSRF protection mặc định cho unsafe methods. User có ROLE_OPS nhưng thiếu CSRF token vẫn có thể nhận 403. **Đừng tắt CSRF toàn bộ**; thiết kế ngoại lệ hẹp cho machine clients đã có authentication/mTLS/network controls thích hợp nếu nghiệp vụ thật sự cần.

## 12. 401, 403, 404 và 503 không đồng nghĩa

| Mã | Tình huống thường gặp | Cách phân biệt |
| --- | --- | --- |
| 200 | Public static, health UP, authorized admin/metrics | Xem cả nội dung và headers |
| 401 | Chưa authentication hoặc Basic credentials sai | `WWW-Authenticate` hoặc entry point |
| 403 | Có authentication nhưng không đủ role; hoặc CSRF bị chặn | Kiểm tra security/CSRF logs |
| 404 | Route chưa được expose hoặc resource không tồn tại | Gọi bằng credential có quyền, so exposure list |
| 405 | Path có handler nhưng method không hỗ trợ | So HTTP method mapping |
| 503 | Health DOWN/unready theo status mapping | Xem status/health group/traffic readiness |

Một URL không có handler vẫn có thể bị Spring Security trả 401 trước khi tìm controller nếu fallback `authenticated()` match trước. Do đó đừng dùng 401 làm chứng cứ endpoint đã được expose. Và không sửa 404 bằng `permitAll` vì authorization không tạo file/route mới.

## 13. Static CDN, reverse proxy và security boundary

Nếu browser tải `/assets/app.js` từ CDN cache thay vì JVM, Spring Security sẽ **không chạy** trên request đó. Với public CSS/JS, đó là bình thường và có thể tối ưu tốt. Với tài nguyên riêng tư:

- Object storage bucket phải private; đừng chỉ ẩn URL.
- Dùng signed URL ngắn hạn hoặc download controller có permission/object-level validation.
- CDN caching phải tránh dùng chung response của user A cho user B.
- NGINX/ingress không được route public tới management port nếu không chủ đích.
- Không dựa vào `X-Forwarded-For` do client tự đặt để cấp quyền OPS/internal.

Bảo vệ management bằng nhiều lớp: không expose, network restrict, authentication/authorization và least-data response. Trong một hệ thống có nhiều pods, health probes thường đến từ kubelet nội bộ, metrics scraper đến từ monitoring namespace; điều đó khác với cho toàn Internet `permitAll` trên `/actuator/**`.

## 14. Error page, session, CSRF và CORS

### 14.1. Error response cũng có thể lộ thông tin

`server.error.include-stacktrace=always` hoặc custom exception handler trả raw exception message có thể làm lộ package names, database paths, secrets trong message. Dùng `server.error.include-stacktrace=never` và chỉ gửi thông điệp an toàn cho client; log chi tiết ở nơi được bảo vệ.

Khi `/error` bị security fallback chặn hoặc dispatcher type khác nhau, có thể thấy 401/redirect loop thay vì lỗi gốc. Hãy kiểm tra `DispatcherType.ERROR`/`FORWARD`, Spring Security filters và exception handling cho đúng phiên bản. Không mở `/**` chỉ để chữa một trang lỗi.

### 14.2. Cookie/session không phải hệ thống authorization

Với form login/session, cookie xác thực có thể còn tồn tại nhưng user vẫn phải có quyền tài nguyên. Với Basic auth demo, credentials chỉ chứng minh danh tính; role USER không được đọc admin. Với tải PDF theo tenant, phải check owner/tenant ở service bất kể user đã login.

### 14.3. CSRF và admin writes

Một POST thay logging level hoặc admin action có thể bị CSRF chặn dù role đủ; đó là một lớp bảo vệ cho browser-authenticated flows. Nếu dùng non-browser machine credentials, thiết kế CSRF phù hợp với threat model và chỉ giới hạn exception ở API phù hợp, không tắt protection trên toàn app mà không có lý do.

### 14.4. CORS không khóa endpoint

CORS quyết định browser JavaScript từ origin khác có thể đọc response hay không. `curl`, Prometheus, server-to-server client **không bị CORS cấm**. Actuator CORS mặc định không được bật trừ khi cấu hình; chỉ thêm allowed origins khi có nhu cầu rõ với frontend quản trị và permission/credentials policy.

## 15. WebFlux khác API Servlet

Bài mẫu dùng Spring MVC/Servlet `HttpSecurity` và import `PathRequest` thuộc package `servlet`. Với Spring WebFlux, dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và matcher reactive:

```java
import org.springframework.boot.autoconfigure.security.reactive.PathRequest;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

// Snippet bên trong một @Configuration bean cho dự án WebFlux:
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http.authorizeExchange(exchanges -> exchanges
            .matchers(PathRequest.toStaticResources().atCommonLocations())
                .permitAll()
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đây là **snippet** cần thêm import `@Bean`, nằm trong một dự án `spring-boot-starter-webflux`, **không phải class độc lập** và không copy vào app MVC. Reactive Actuator có `EndpointRequest` khác package và matcher phù hợp `ServerWebExchange`; phải bảo vệ actuator tương ứng. Đừng thêm cả Web và WebFlux starters rồi cho rằng mọi controller mặc định chạy reactive.

## 16. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| CSS của login page trả 401 | Static chưa `permitAll` | Dùng PathRequest hoặc đúng path |
| CSS không có security headers | Request bị web.ignoring | Giữ trong filter chain với permitAll |
| User thường đọc được admin | Rule rộng đứng trước, chain không match hoặc edge bypass | Sửa @Order/matchers, kiểm tra proxy |
| Metrics public sau refactor | Custom SecurityFilterChain làm Boot actuator security back off | Viết chain Actuator riêng |
| Metrics 404 | Thiếu exposure hoặc dependency | Kiểm tra `include` và starter |
| Metrics 401 | Chưa authentication | Dùng máy/người có credential hợp lệ |
| Metrics 403 | Thiếu ROLE_OPS hoặc policy khác | Kiểm tra authorities và security logs |
| Health bị 401 làm pod unready | Probe không được permit hoặc dùng sai port | Cho phép đúng health paths trên mạng đáng tin |
| Health tiết lộ DB/cache | show-details=always hoặc group cấu hình quá rộng | Giữ never/roles phù hợp |
| env lộ secret | Exposure/setting show-values quá rộng | Unexpose, sanitize, xử lý incident |
| heapdump tải được từ public internet | Management route hoặc CDN/storage mở | Tắt exposure, chặn network |
| POST loggers trả 403 dù role OPS | CSRF thiếu | Thiết kế token hoặc machine auth thích hợp |
| Admin data còn trong cache sau logout | Cache-Control/CDN policy sai | no-store/private, cache tests |
| Management port riêng vẫn bị scan | Port bind public/firewall mở | Hạn chế listener/NetworkPolicy/mTLS |
| Endpoint không tồn tại nhưng anonymous thấy 401 | Security chặn trước MVC route | Kiểm tra bằng authenticated test và exposure |
| Probes trên management port UP nhưng app port chết | Hai web servers không cùng đường phục vụ | Main-port additional probes hoặc kiểm tra riêng |

## 17. Bộ kiểm thử production nên có

1. **Anonymous** GET CSS/JS public: response 200, content-type và security headers phù hợp.
2. **Anonymous** GET account/admin/metrics: authentication challenge hoặc status được thiết kế.
3. **User authenticated** GET account: 200; GET admin/diagnostic/metrics: 403.
4. **OPS/ADMIN** GET endpoints đúng vai trò: 200; role khác: 403.
5. **Endpoint không expose**: bảo đảm 404 khi gọi bằng identity đủ quyền, không nhầm 401 của fallback.
6. **Health**: summary ít thông tin; liveness/readiness đáp ứng đúng cả khi startup, shutdown, dependency lỗi.
7. **CSRF**: unsafe admin operations không được thực hiện khi thiếu token ở browser flows.
8. **Static private**: user A không đọc file của B qua CDN, object storage hay URL đoán được.
9. **Proxy/Ingress**: public internet không gọi được management port hoặc đường chẩn đoán nội bộ ngoài ý muốn.
10. **Deployment**: thay đổi Spring Boot/Security version, actuator exposure, static mapping hoặc context path không mở thêm URL.
11. **Observability**: 401/403 anomalies, endpoint access logs và audit không ghi raw token/secret.
12. **Regression**: automated tests cho chain order, role mapping, health probe access và exposure list.

Ngoài MockMvc, dùng HTTP integration test ở các port thật và thử sau reverse proxy/CDN. Test trên JVM không thể phát hiện tất cả lỗi bucket policy/ingress/NetworkPolicy.

## 18. Bài tập ôn luyện

**1.** `/css/site.css` public; dùng `web.ignoring` hay `permitAll`?  
**Đáp án:** Ưu tiên `permitAll` để giữ security filters/headers, đồng thời bảo đảm resource thật sự không chứa dữ liệu riêng.

**2.** Có `SecurityFilterChain` custom cho `/admin/**`, Actuator auto bảo vệ đầy đủ như trước chắc chắn không?  
**Đáp án:** Không. Custom chain khiến Actuator web security auto-configuration nhường quyền. Cần policy/chain bao phủ các actuator endpoints.

**3.** `management.endpoints.web.exposure.include=health,metrics` có cho mọi người đọc metrics không?  
**Đáp án:** Không. Exposure chỉ tạo HTTP availability; authentication/authorization vẫn quyết định truy cập.

**4.** Health được `permitAll` và `show-details=always`, rủi ro gì?  
**Đáp án:** Có thể lộ dependency/component status cho anonymous; dùng summary tối thiểu hoặc policy roles rõ.

**5.** Vì sao `hasRole("OPS")` không match một user có authority chỉ là `OPS`?  
**Đáp án:** Quy tắc mặc định tìm `ROLE_OPS`. Dùng cơ chế role/authority nhất quán.

**6.** Một user logged-in bị 403 ở POST thay log level. Có chắc do thiếu role không?  
**Đáp án:** Không. Có thể do CSRF token thiếu hoặc policy khác; kiểm tra security logs và request.

**7.** Vì sao `/actuator/env` không expose có thể vẫn trả 401 với anonymous?  
**Đáp án:** Security fallback có thể chặn trước route lookup. Dùng credential thích hợp để phân biệt route 404 và auth 401.

**8.** CDN phục vụ `/private/report.csv` trực tiếp, rule Spring MVC `/private/** authenticated()` đủ chưa?  
**Đáp án:** Chưa, CDN không đi qua Spring Security; phải bảo vệ ở edge/storage hoặc chuyển qua authenticated controller.

**9.** Liveness dựa vào database. Database outage làm restart hàng loạt pods. Vấn đề?  
**Đáp án:** Liveness bị phụ thuộc hệ thống ngoài; nên phân biệt readiness và tránh cascade restarts.

**10.** Bật `management.server.port=8081` đã tự khóa được Actuator khỏi Internet?  
**Đáp án:** Không. Cần bind address đúng, firewall/NetworkPolicy, identity và kiểm tra ingress routing.

## 19. Checklist trước khi merge

- [ ] Phân loại routes: public static, user, admin, OPS, probes và diagnostic nhạy cảm.
- [ ] Static resources dùng `permitAll`, không bỏ khỏi toàn bộ SecurityFilterChain nếu không có lý do đặc biệt.
- [ ] Không có credentials, dump, backup hoặc user data trong static public directories.
- [ ] Rule cụ thể trước fallback; không có `/** permitAll` vô tình che rule admin.
- [ ] Multiple SecurityFilterChain có thứ tự và matcher rõ, được test.
- [ ] Custom security không bỏ sót Actuator hoặc main application routes.
- [ ] Exposure list tối thiểu, JMX exposure riêng, không dùng `include=*` trong production.
- [ ] Health chỉ công bố thông tin cần thiết; chi tiết/roles và probe paths được kiểm tra.
- [ ] Management port nằm trên mạng phù hợp, không tự mở ra public.
- [ ] Diagnostic không tiết lộ env values, user/session tokens, heap dumps hoặc logs.
- [ ] CSRF cho admin unsafe methods được giữ hoặc thay bằng biện pháp phù hợp threat model.
- [ ] User-level và object-level authorization được kiểm tra, không chỉ login.
- [ ] Cache của admin/user responses có chính sách không chia sẻ dữ liệu nhạy cảm.
- [ ] Ma trận 200/401/403/404 được thử bằng curl và automated tests.
- [ ] Proxy, CDN, ingress, object storage và monitoring network được kiểm tra riêng.
- [ ] Log/audit hoạt động nhưng không lưu secrets và tokens không cần thiết.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Spring Security](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
- [Spring Boot 3.3 — Actuator Endpoints, Exposure, Security, Health](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Spring Boot 3.3 — Monitoring/Management Over HTTP](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
- [Spring Boot 3.3 — Servlet Static Resources](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 — Servlet PathRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/PathRequest.html)
- [Spring Boot 3.3 — StaticResourceRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/security/servlet/StaticResourceRequest.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Boot 3.3 — Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html)

**Điều cần nhớ:** tài nguyên tĩnh cần **công khai đúng phạm vi**; endpoint quản trị cần **đúng danh tính, role và quyền nghiệp vụ**; thông tin chẩn đoán cần **hạn chế exposure, network và nội dung trả về**. Những lớp này phải được cấu hình và kiểm thử cùng nhau; một URL “ít người biết” hoặc một rule `authenticated()` chung không đủ bảo vệ runtime production.
