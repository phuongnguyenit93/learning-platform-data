# Phân biệt điều kiện chọn chuỗi với điều kiện chọn quy tắc truy cập

> **Điểm mấu chốt trong cấu hình Spring Security hiện đại:** Có hai lần “match” khác nhau. `http.securityMatcher(...)` xác định **SecurityFilterChain nào phụ trách request**; còn `requestMatchers(...)` trong `authorizeHttpRequests(...)` xác định **request đó phải đáp ứng quy tắc cấp quyền nào bên trong chain đã chọn**. Nhầm hai cấp chọn lọc này có thể làm endpoint đi ngoài mọi filter bảo mật hoặc đặt một rule đúng ở chain không bao giờ được dùng.

Bài học thuộc nhóm **Cấu hình hiện đại** của **Spring Security – fundamentals**, tập trung vào ứng dụng **Spring MVC/Servlet, Spring Security 6.x**. Các ví dụ dùng Java 17 và API cấu hình `SecurityFilterChain`/`HttpSecurity`; WebFlux có cấu trúc tương tự nhưng dùng `SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange` và matcher dành riêng cho WebFlux.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Giải thích chính xác `securityMatcher`, `requestMatchers`, `anyRequest` và `@Order` thực hiện nhiệm vụ nào, theo thứ tự nào.
2. Dự đoán chain/rule và kết quả dự kiến cho request có path, HTTP method và authentication khác nhau.
3. Hiểu vì sao `anyRequest().denyAll()` trong một chain có `securityMatcher("/api/**")` **không thể** bảo vệ `/admin` ở ngoài phạm vi chain đó.
4. Thiết kế nhiều chain theo hướng **specific first, catch-all last**, tránh để request lọt ngoài Spring Security.
5. Nhận ra trường hợp URL form login/logout do filter cung cấp nằm ngoài `securityMatcher`, khiến endpoint đăng nhập không hoạt động.
6. Tự xây ứng dụng nhỏ và kiểm thử cả trường hợp được phép, 401, 403, sai method, CSRF và đường ngoài API.
7. Chọn khi nào nên tách nhiều chain và khi nào chỉ cần **một chain** với nhiều quy tắc phân quyền.

## 2. Có hai cấp ra quyết định

Một request ví dụ:

```http
GET /api/reports HTTP/1.1
Host: localhost:8080
Authorization: Basic ...
```

Đối với Servlet, luồng đơn giản hóa:

```text
HTTP request
    |
    v
Servlet FilterChain
    |
    v
DelegatingFilterProxy -> FilterChainProxy (Spring Security)
    |
    +-- [CẤP 1: CHỌN SECURITY FILTER CHAIN]
    |      Thử chain @Order(1): match("/api/**")?
    |         YES -> chọn API chain, không thử chain thấp hơn nữa
    |         NO  -> thử chain kế tiếp
    |      Chain fallback: match mọi request
    |
    v
Các security filter thuộc MỘT chain đã chọn
    |
    +-- Authentication, SecurityContext, CSRF, ...
    |
    +-- [CẤP 2: CHỌN RULE PHÂN QUYỀN]
    |      Với API chain:
    |        GET  /api/reports -> REPORT_READ?
    |        POST /api/reports -> REPORT_WRITE?
    |        GET  /api/admin   -> ROLE_ADMIN?
    |        các request còn lại của API -> DENY
    |
    +-- Cho phép: đi tiếp đến Spring MVC controller
    +-- Từ chối: 401 / 403 / redirect tùy ngữ cảnh
```

Lưu ý: cấp 1 **không tự cấp quyền truy cập**. Chọn một chain chỉ quyết định bộ lọc và chính sách nào được áp dụng. Cấp 2 thực hiện quyết định phân quyền HTTP. Sau khi qua cấp 2, service vẫn cần kiểm tra quyền trên đối tượng, tenant, trạng thái nghiệp vụ. Cả hai cấp đều không tự biết báo cáo số 42 thuộc khách hàng nào.

### 2.1. Bảng phân biệt

| Khía cạnh | Chọn chuỗi (chain selection) | Chọn quy tắc truy cập (request authorization) |
| --- | --- | --- |
| API điển hình | `http.securityMatcher("/api/**")` | `http.authorizeHttpRequests(a -> a.requestMatchers(...).hasAuthority(...))` |
| Nơi diễn ra | `FilterChainProxy` chọn `SecurityFilterChain` | `AuthorizationFilter` sử dụng `AuthorizationManager` bên trong chain |
| Câu hỏi trả lời | “Chain nào xử lý request?” | “Request này có được vào handler không?” |
| Dữ liệu dùng để match | `RequestMatcher`, thường path và có thể gồm method hoặc điều kiện tùy chỉnh | `RequestMatcher` cho từng rule, thường path + method |
| Thứ tự | Ưu tiên chain theo `@Order`; **chain đầu tiên khớp** | Theo thứ tự khai báo; **rule đầu tiên khớp** trong chain đó |
| Khi không match | Thử chain tiếp; nếu hết chain thì không có Spring Security chain bảo vệ | Thử rule tiếp; đến `anyRequest()` nếu đã khai báo |
| Tác động của `anyRequest()` | Không đổi phạm vi chọn chain | Chỉ bao phủ request **đã thuộc chain hiện tại** |
| Kết quả | Một tập filter được áp dụng hoặc không có chain nào | `permitAll`, `denyAll`, `authenticated`, `hasRole`, `hasAuthority`... |
| Sai lầm thường gặp | Không có catch-all, endpoint lọt ngoài Spring Security | Rule quá rộng đặt trước, rule đặc thù không được xét |

**Hai mức “first match” không giống nhau.** Một request chỉ qua **một `SecurityFilterChain` được chọn đầu tiên**, sau đó mới xét **một quy tắc đầu tiên khớp** ở phần authorization của chain đó. Nếu rule từ chối, Spring Security **không tìm chain sau để thử cho phép**.

## 3. Hiểu đúng từng API

### 3.1. `securityMatcher(...)`: phạm vi sống của cả chain

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đoạn code này là **snippet** trong class cấu hình Spring; toàn bộ chương trình có thể chạy sẽ được cung cấp ở mục 7.

- `securityMatcher("/api/**")` thay matcher mặc định của chain bằng điều kiện áp dụng cho path bắt đầu bởi `/api/`.
- Khi `GET /api/reports` đến, chain này **có thể được chọn** (nếu chưa có chain ưu tiên cao hơn khớp).
- Khi `GET /admin` đến, chain này **không nhận request**; `anyRequest().authenticated()` ở đây **không có cơ hội chạy**.
- Một chain **không khai báo `securityMatcher`** mặc định có matcher khớp mọi request; vì thế thường được dùng làm fallback.
- `securityMatcher` kiểm tra request khi chain được lựa chọn, không phải việc “đăng ký controller path” hay “bật role”.

Với matcher Java overload, có thể cung cấp một `RequestMatcher` cụ thể nếu phải xét HTTP method, servlet path, host hoặc điều kiện phức tạp. Đừng dùng path-only matcher rồi mặc nhiên nghĩ nó chỉ nhận GET: nếu path khớp, POST/DELETE cũng vào chain, sau đó rule phân quyền bên trong sẽ quyết định.

### 3.2. `requestMatchers(...)`: điều kiện của từng rule

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/reports")
        .hasAuthority("REPORT_READ")
    .requestMatchers(HttpMethod.POST, "/api/reports")
        .hasAuthority("REPORT_WRITE")
    .anyRequest().denyAll()
)
```

Trong **chain đã được chọn**:

1. Spring Security xét `GET /api/reports` trước; nếu khớp, yêu cầu authority `REPORT_READ`.
2. Nếu không khớp, xét `POST /api/reports`; nếu khớp, yêu cầu `REPORT_WRITE`.
3. Các request còn lại của **chain hiện tại** bị `denyAll`.
4. Những rule sau rule đầu tiên khớp **không** được xét; không có ý nghĩa “gom tất cả role của nhiều rule lại rồi mới quyết định”.

Ví dụ Alice có `REPORT_READ` nhưng không có `REPORT_WRITE`: Alice được gọi GET, song không thể gọi POST chỉ vì URL giống nhau. Đổi HTTP method là đổi thao tác cần phân quyền. Với POST, PUT, PATCH, DELETE, **CSRF protection** cũng có thể chặn request độc lập với quyền, tùy cơ chế xác thực và cấu hình.

### 3.3. `anyRequest()`: phần còn lại của chain, không phải của cả ứng dụng

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .anyRequest().denyAll()
    );
```

Ý nghĩa chính xác:

- `GET /api/public` đi vào chain API và được phép theo rule.
- `GET /api/private` đi vào chain API rồi bị `denyAll` nếu không có rule cụ thể khác.
- `GET /admin` **không vào chain API**; việc có được bảo vệ hay không tùy chain khác.
- `/api/public` dù được `permitAll` vẫn đi qua các filter liên quan của chain (ví dụ security headers, CSRF nếu request là POST có CSRF enabled).

Đây là lý do **không thể thay thế catch-all SecurityFilterChain bằng một dòng `anyRequest().denyAll()` bên trong chain hẹp**.

### 3.4. `@Order`: thứ tự thử các chain

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception { /* ... */ }

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception { /* ... */ }
```

Mã này chỉ minh họa signature; `/* ... */` đại diện body sẽ được cung cấp ở ví dụ đầy đủ.

- Chain `@Order(1)` được thử trước chain không có `@Order` (thường đứng sau các chain có thứ tự ưu tiên cụ thể).
- Chain đầu tiên match sẽ được chọn, dù role của người dùng **không đáp ứng policy** của chain đó.
- Khi chain đầu tiên khớp và từ chối, **không có bước “thử chain tiếp theo”**.
- Catch-all ưu tiên cao đặt trước chain API có thể “nuốt” toàn bộ request: chain API không bao giờ chạy.
- Không dựa vào tên bean hay thứ tự method trong file Java để phỏng đoán thứ tự.

### 3.5. `securityMatchers(...)` và custom `RequestMatcher`

`HttpSecurity` còn có API `securityMatchers(...)` để cấu hình một tập matcher ở phạm vi chain. Nó phục vụ **cùng cấp chọn chuỗi** với `securityMatcher`, khác cách biểu diễn khi có nhiều pattern. `requestMatchers(...)` bên trong `authorizeHttpRequests` vẫn là **cấp chọn rule**.

```java
// Snippet cấp CHUỖI: chain dành cho hai nhánh API.
http.securityMatchers(matchers -> matchers
    .requestMatchers("/api/**", "/internal/**"));
```

Nếu cùng dùng nhiều overload/matcher builder, hãy kiểm tra API và semantics thực tế của Spring Security version đang chạy; không lặp bừa `securityMatcher(...)` rồi kỳ vọng các điều kiện tự cộng dồn. Với request matcher tùy chỉnh, phải bảo đảm nó sử dụng đúng nguồn thông tin đáng tin (path đã được normalise, servlet path, method...), không tin header `X-Role` hoặc `X-User` do client tự gửi để cấp quyền.

**Phân biệt thêm:** `web.ignoring()`/`WebSecurityCustomizer` loại request khỏi Spring Security filter chain; còn `permitAll` cho phép request **ở bước authorization trong chain**. Đối với static resources hoặc endpoint công khai, thường nên ưu tiên `permitAll` để vẫn có các filter bảo vệ liên quan.

## 4. Dự đoán hành vi trên một bản đồ có hai chain

Giả sử ứng dụng có:

```text
@Order(1) API CHAIN
  securityMatcher("/api/**")
  GET  /api/reports -> REPORT_READ
  POST /api/reports -> REPORT_WRITE
  GET  /api/admin   -> ROLE_ADMIN
  anyRequest        -> denyAll

FALLBACK CHAIN
  securityMatcher: không khai báo -> match mọi request còn lại
  GET /public       -> permitAll
  GET /profile      -> authenticated
  anyRequest        -> denyAll
```

Bảng bên dưới giả định tài khoản đã được xác thực khi có nêu user; CSRF token hợp lệ được gửi khi cần.

| Request | Chain được chọn | Rule được chọn | Kết quả nếu... |
| --- | --- | --- | --- |
| `GET /api/reports` | API | `REPORT_READ` | Reader có `REPORT_READ` → `200` |
| `GET /api/reports` | API | `REPORT_READ` | Admin chỉ có `ROLE_ADMIN` → `403` |
| `POST /api/reports` | API | `REPORT_WRITE` | Writer có `REPORT_WRITE` + CSRF hợp lệ → `200` |
| `POST /api/reports` | API | `REPORT_WRITE` | Reader thiếu quyền → `403` |
| `GET /api/admin` | API | `ROLE_ADMIN` | Admin đúng role → `200` |
| `GET /api/admin` | API | `ROLE_ADMIN` | Reader có `REPORT_READ` → `403` |
| `GET /public` | Fallback | `permitAll` | Không login → `200` |
| `GET /profile` | Fallback | `authenticated` | Anonymous → `401` với HTTP Basic |
| `GET /profile` | Fallback | `authenticated` | Reader đăng nhập → `200` |
| `GET /unknown` | Fallback | `denyAll` | Reader → `403` |
| `GET /api/unknown` | API | `denyAll` | Reader → `403` |
| `DELETE /api/reports` | API | `denyAll` | Writer dù có `REPORT_WRITE` cũng bị chặn |

Với một ứng dụng có HTTP Basic được cấu hình, request thiếu credentials thường nhận `401` kèm header `WWW-Authenticate`; request được xác thực nhưng thiếu authority thường nhận `403`. Với form login/session, browser có thể nhận redirect `302`. Cấu hình `AuthenticationEntryPoint`, CSRF, handler lỗi và proxy có thể ảnh hưởng chi tiết, vì vậy cần integration test theo chính dự án của bạn.

**Ví dụ phân tích GET `/api/admin`:** Dù fallback có policy “admin” giả định mạnh hơn, fallback **không được thử** vì `/api/**` đã chọn API chain. Mọi quy tắc cho `/api/admin` phải nằm trong API chain hoặc chính sách method/service được áp dụng sau khi đi qua chain.

## 5. Trường hợp nguy hiểm: một chain hẹp và không có fallback

```java
@Configuration
class IncompleteSecurityConfig {
    @Bean
    SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đoạn trên biên dịch được khi đặt trong dự án có các import và starter phù hợp, nhưng **cấu hình thiếu lớp bảo vệ cho phần còn lại**. Nếu `GET /internal/export` không match `/api/**`, request đó **không chịu Spring Security của chain `onlyApi`**. Nếu controller `/internal/export` tồn tại và không có biện pháp bảo vệ khác, endpoint có nguy cơ bị truy cập trái phép. Dòng `anyRequest().denyAll()` trong `onlyApi` không cứu được đường ngoài phạm vi.

Cách sửa phổ biến:

```java
@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Hoặc nếu ứng dụng **không cần các cơ chế filter khác nhau giữa các khu vực**, dùng **một chain duy nhất**, bỏ `securityMatcher(...)`, rồi đặt nhiều `requestMatchers(...)` trong một `authorizeHttpRequests(...)`. Đây thường là phương án đơn giản và ít rủi ro hơn khi số lượng route chưa lớn.

## 6. Khi nào cần nhiều chain, khi nào chỉ cần một chain?

Một chain với nhiều authorization rule là đủ khi các endpoint dùng cùng kiểu đăng nhập/session, cùng CSRF, CORS, security headers và các filter chính. Ví dụ:

```java
@Bean
SecurityFilterChain oneChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/public").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/reports")
                .hasAuthority("REPORT_READ")
            .requestMatchers(HttpMethod.POST, "/api/reports")
                .hasAuthority("REPORT_WRITE")
            .anyRequest().denyAll())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Nhiều chain trở nên hữu ích nếu **chính cơ chế bảo mật ở cấp filter khác nhau**, chẳng hạn:

- API chỉ nhận Bearer token từ Resource Server, còn trang quản trị dùng OIDC browser login/session.
- Endpoint quản trị cần một bộ authentication filters và session policy khác với API stateless.
- Nhóm endpoint nội bộ sử dụng một tập custom filters hoặc chính sách CSRF/CORS riêng có lý do.
- Cần policy khác nhau **ở cấp chain**, không chỉ yêu cầu role khác nhau.

Đừng tự tạo chain riêng cho mỗi role nếu mọi chain thực chất dùng cùng filter, chỉ thay `hasRole(...)`. Những sự khác biệt ấy thường thuộc **requestMatchers**. Mỗi chain tăng số vùng cần kiểm thử: path ngoài phạm vi, thứ tự chọn, CSRF, entry point, login/logout endpoint, static files, fallback và request chưa liệt kê.

## 7. Ứng dụng hoàn chỉnh: Java 17, Spring Boot 3.5.16

Ví dụ này dùng Spring Boot **3.5.16** và Spring Security 6.5.x do BOM quản lý để trình bày DSL `SecurityFilterChain` ổn định. Spring Boot 3.5.16 đã phát hành tháng 06/2026 và là bản OSS cuối của dòng 3.5.x; với dự án production mới cần chọn nhánh Spring Boot còn được hỗ trợ và cập nhật bản vá. Tài khoản in-memory cùng password mẫu **chỉ dành cho local/test**.

### 7.1. Cấu trúc dự án

```text
matcher-boundary-demo/
├── pom.xml
└── src/
    ├── main/java/demo/matching/MatchingApplication.java
    └── test/java/demo/matching/MatchingApplicationTests.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>matcher-boundary-demo</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. `MatchingApplication.java` — hai chain rõ ràng

Tạo file `src/main/java/demo/matching/MatchingApplication.java`:

```java
package demo.matching;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MatchingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatchingApplication.class, args);
    }

    // Chain 1: chỉ dành cho /api/**, xét trước fallback.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("REPORT_READ")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("REPORT_WRITE")
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            // CSRF vẫn bật theo default; POST cần token hợp lệ.
            .build();
    }

    // Chain 2: không securityMatcher => nhận mọi request còn lại.
    @Bean
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Cho phép servlet ERROR dispatch render lỗi;
                // request ban đầu vẫn phải chịu rule của chain.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/profile").authenticated()
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
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("demo-pass"))
                .authorities("REPORT_READ").build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("REPORT_READ", "REPORT_WRITE").build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN").build()
        );
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/profile")
    String profile(Authentication authentication) {
        return "profile:" + authentication.getName();
    }

    @GetMapping("/api/reports")
    String readReport(Authentication authentication) {
        return "report:" + authentication.getName();
    }

    @PostMapping("/api/reports")
    String writeReport(Authentication authentication) {
        // Chỉ minh họa quyền thực hiện POST; không có ghi database.
        return "written-by:" + authentication.getName();
    }

    @GetMapping("/api/admin")
    String apiAdmin() {
        return "admin-ok";
    }
}
```

**Giải thích chính xác:**

1. `@Order(1)` và `securityMatcher("/api/**")` khiến API chain được thử trước; tất cả đường có prefix tương ứng được đánh giá trong chain này. Đường khác được đưa đến fallback.
2. `requestMatchers(GET, "/api/reports")` không tự mở chain khác. Nó chỉ được xét **sau khi request đã vào API chain**, rồi yêu cầu `REPORT_READ`.
3. `requestMatchers(POST, "/api/reports")` đặt rule riêng cho thao tác ghi. Dù writer có `REPORT_WRITE`, một POST thiếu CSRF token vẫn có thể bị `403` bởi `CsrfFilter`.
4. `GET /api/admin` cần `ROLE_ADMIN`; `hasRole("ADMIN")` tự thêm prefix `ROLE_` theo quy ước mặc định. Admin không có `REPORT_READ`, nên không được gọi `GET /api/reports`.
5. `anyRequest().denyAll()` ở API chỉ chặn những request đã match `/api/**`; fallback chặn đường chưa khai báo bên ngoài API.
6. `DispatcherType.ERROR` được cho phép ở fallback để error dispatch của Servlet container có thể render error response. Đây không phải mở quyền cho một URL công khai tùy ý; request ban đầu vẫn phải match rule.
7. Cả hai chain đều dùng HTTP Basic, chỉ để học cách chọn chain. Với ứng dụng thật, mật khẩu/token phải đi trên HTTPS, và cần xác thực, phân quyền sở hữu tài nguyên, hạn mức, logging an toàn.
8. Không khai báo `formLogin` trong ví dụ này, nên browser không có form login mặc định do các chain này cung cấp; client Basic nhận challenge `401` khi anonymous.

### 7.4. `MatchingApplicationTests.java` — chứng minh hai cấp chọn lọc

Tạo file `src/test/java/demo/matching/MatchingApplicationTests.java`:

```java
package demo.matching;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MatchingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void fallbackAndApiHaveDifferentPathScopes() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/profile"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/profile")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("profile:reader"));

        // /unknown nằm ngoài /api/** nên fallback deny.
        mvc.perform(get("/unknown")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());

        // /api/unknown nằm trong /api/** nên API chain deny.
        mvc.perform(get("/api/unknown")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void apiRulesDependOnMethodAndAuthority() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("report:reader"));

        // ROLE_ADMIN không tự đồng nghĩa với REPORT_READ.
        mvc.perform(get("/api/reports")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("reader", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-ok"));

        // Method không được cấp quyền thì deny.
        mvc.perform(delete("/api/reports")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void postRequiresBothPermissionAndCsrf() throws Exception {
        // Writer có REPORT_WRITE nhưng không có CSRF token.
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        // Có CSRF nhưng reader không có REPORT_WRITE.
        mvc.perform(post("/api/reports")
                .with(httpBasic("reader", "demo-pass")).with(csrf()))
            .andExpect(status().isForbidden());

        // Có permission đúng và CSRF token hợp lệ.
        mvc.perform(post("/api/reports")
                .with(httpBasic("writer", "demo-pass")).with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("written-by:writer"));
    }
}
```

Bộ test này kiểm tra **hành vi thực** qua Spring Security filter chain và controller, không cần assert tên class filter nội bộ. `httpBasic(...)` tạo HTTP Basic header để bộ xác thực thật của ứng dụng dùng `UserDetailsService`/`PasswordEncoder` xử lý. `csrf()` cung cấp token hợp lệ trong request test; trong sản phẩm dùng browser/session, client cần lấy token đúng qua cơ chế đã cấu hình. Không dùng `@WithMockUser` để kết luận cơ chế kiểm tra password hoạt động, vì mock user bỏ qua bước xác thực credential.

### 7.5. Chạy thử

Ở thư mục có `pom.xml`, cần JDK 17+ và Maven tương thích Spring Boot:

```bash
mvn test
mvn spring-boot:run
```

Với app ở máy local, thử (Windows PowerShell cũ có thể cần `curl.exe`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u reader http://localhost:8080/profile
curl -i http://localhost:8080/api/reports
curl -i -u reader http://localhost:8080/api/reports
curl -i -u admin http://localhost:8080/api/admin
curl -i -u admin http://localhost:8080/api/reports
```

Dùng `curl -u reader` / `curl -u admin` để curl hỏi mật khẩu tương tác; nhập `demo-pass` trong môi trường **local**. Không nhúng secret vào lệnh để tránh lưu trong command history. Kết quả dự kiến theo thứ tự: `200` với body `public`; `401`; `200 profile:reader`; `401`; `200 report:reader`; `200 admin-ok`; `403`.

Với POST, `curl -u writer -X POST http://localhost:8080/api/reports` thiếu CSRF token thường nhận `403`. Không nên tắt CSRF chỉ để làm curl POST trả 200; bài test `MockMvc` ở trên chứng minh cả token và permission. Nếu muốn tích hợp form/browser thực, cần chọn `CsrfTokenRepository`, expose token và gửi đúng token/credential theo threat model.

**Độ tin cậy của kết quả:** HTTP body/header lỗi có thể khác theo Boot/version/proxy, nhưng test kiểm tra các mã và body thành công đã định nghĩa. Mã dùng API Spring Security 6.5, chưa thay bằng API được nâng cấp ở Spring Security 7; cần kiểm tra guide tương ứng khi đổi version.

## 8. Bẫy thứ tự: chain rộng ưu tiên hơn chain hẹp

Cấu hình sai về ý tưởng:

```java
// Ví dụ bố cục sai; hai method bên dưới là snippet, không phải app đầy đủ.
@Bean
@Order(1)
SecurityFilterChain allFirst(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().permitAll())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain apiLater(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

`allFirst` không có `securityMatcher`, nên nó match mọi URL. `/api/private` đã được chain ưu tiên 1 nhận; Spring Security **không chạy tiếp** chain `apiLater`. Kết quả có thể là API public trái ý định, dù code có vẻ khai báo `hasRole("ADMIN")` ở nơi khác.

**Sửa:** đặt API chain hẹp trước, fallback sau. Đồng thời kiểm tra rule bên trong mỗi chain, không dựa vào việc “tên class đặt AdminSecurityConfig” để đảm bảo mức bảo vệ.

Một lỗi khác là đặt rule rộng trước rule hẹp trong **cùng chain**:

```java
.authorizeHttpRequests(a -> a
    .requestMatchers("/api/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().denyAll()
)
```

Ở đây, ngay khi `/api/admin/settings` khớp `/api/**`, rule `hasRole("ADMIN")` phía sau **không bao giờ được xét**. Đúng hơn là đặt rule `/api/admin/**` trước rule rộng và xem xét có nên cho `/api/**` công khai hay không.

## 9. Bẫy các endpoint do filter cung cấp: login/logout

`formLogin()` có thể cung cấp endpoint xử lý `POST /login`, và Spring Security có thể sinh trang `GET /login` khi dùng cấu hình mặc định. Nhưng nếu bạn đặt:

```java
http
    .securityMatcher("/secured/**")
    .authorizeHttpRequests(a -> a.anyRequest().authenticated())
    .formLogin(Customizer.withDefaults());
```

thì `GET /login` và `POST /login` **không thuộc `/secured/**`**. Chain đó không nhận các request login mặc định, nên các filter của nó không thể cung cấp/handle chúng. Nếu không có endpoint thích hợp ở chain khác, login có thể 404 hoặc bị từ chối bởi fallback. Đây là hệ quả của **chain selection**, không phải do `requestMatchers(...).permitAll()` chưa thêm.

Cách giải quyết:

- Chọn matcher bao gồm URL login/logout thực sự và định nghĩa policy tương ứng, hoặc dùng một chain rộng cho khu vực browser.
- Khi cấu hình URL login tùy chỉnh, kiểm tra cả `loginPage(...)`, `loginProcessingUrl(...)` và logout URL; nếu đặt custom login page, ứng dụng phải cung cấp trang HTML/controller tương ứng.
- Gửi login form với CSRF token theo cấu hình khi CSRF protection áp dụng.
- Viết test cho **trang login, POST login, logout và callback** thay vì chỉ kiểm tra đường nghiệp vụ.
- Không đặt rule `permitAll("/login")` ở chain `/secured/**` rồi kỳ vọng `/login` tự đi vào chain đó; rule không thể mở rộng phạm vi matcher của chain.

Một điểm liên quan: `permitAll` không có nghĩa Spring Security bỏ qua toàn bộ các filter; `web.ignoring()` mới là một cách loại request khỏi security chain, thường không phù hợp làm mặc định cho tài nguyên công khai.

## 10. Những chi tiết matcher có thể khiến production khác local

### 10.1. HTTP method

`.requestMatchers("/api/reports").hasAuthority("REPORT_READ")` thường xét path mà không cố định HTTP method. Nếu app thêm `POST /api/reports`, rule path-only này có thể vô tình cho POST theo quyền đọc. Hãy khai báo `requestMatchers(HttpMethod.GET, ...)` và `requestMatchers(HttpMethod.POST, ...)` với permission khác nhau khi nghiệp vụ khác nhau.

### 10.2. Query parameters

Các path matcher thông thường không coi `?id=42` là phân quyền ownership. `GET /api/reports?id=42` và `GET /api/reports?id=43` có thể cùng match một URL rule; service phải kiểm tra ID, owner, tenant và ACL từ server. Nếu cần match tham số query ở cấp HTTP policy, dùng `RequestMatcher` tùy chỉnh, nhưng không thay kiểm tra resource ở domain.

### 10.3. Servlet path, context path và nhiều DispatcherServlet

Spring Security matcher thường làm việc với path theo quy tắc Servlet, không lấy nguyên URL đầy đủ từ browser gồm scheme/host/port. Khi app có context path khác mặc định, nhiều servlet hoặc mapping servlet đặc biệt, cú pháp path/string matcher có thể khác kỳ vọng. Cần kiểm tra `DispatcherServlet` mapping, servlet path, URL normalization, encoded slash, path traversal và phiên bản Spring Security. Dùng `RequestMatcher` cụ thể nếu cần làm rõ đối tượng được match.

Không tự ghép string `request.getRequestURI()` rồi kiểm tra `startsWith("/api")` trong custom filter như một thay thế đơn giản cho matcher đã được framework chuẩn hóa.

### 10.4. Dispatcher type: REQUEST, ERROR, FORWARD

`AuthorizationFilter` có thể áp dụng cho cả các dispatch nội bộ. Khi Spring MVC chuyển đến error page hoặc forward tới view, một rule quá chặt có thể khiến response lỗi bị thay bằng lỗi 403 khác. Nếu phù hợp, cho phép `DispatcherType.ERROR` và `FORWARD` với policy rõ ràng, đồng thời **không mở request ban đầu ra ngoài phạm vi bảo vệ**. Test ca exception/error dispatch, chứ không chỉ GET thành công.

### 10.5. CORS và CSRF trong nhiều chain

CORS preflight (OPTIONS) có thể không mang credential, còn CSRF thường kiểm tra thao tác thay đổi trạng thái. Cấu hình CORS/CSRF phải gắn với chain thực sự nhận request. Nếu API chain được chọn, không được giả định CORS/CSRF của fallback sẽ chạy tiếp. Chọn strategy theo kiểu authentication: cookie/session khác API Bearer token không tự đính kèm. Kiểm thử OPTIONS, POST/PUT/DELETE và request cross-origin thật ở mức hợp lý.

### 10.6. Nâng cấp framework

Tài liệu Spring Security phiên bản mới có thể thay đổi matcher implementation được lựa chọn tự động (ví dụ khi có Spring MVC hoặc `PathPatternRequestMatcher.Builder`). Các ví dụ trong bài sử dụng overload string được Spring Security 6.5 hỗ trợ; khi nâng lên Spring Security 7 hoặc chuyển stack, kiểm tra migration guide về matcher/path handling và chạy lại negative tests. Không thay tất cả cấu hình bằng wildcard trong quá trình nâng cấp.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng `securityMatcher` cho chain duy nhất, không có fallback | Đường ngoài phạm vi không chịu Spring Security | Thêm chain catch-all hoặc bỏ matcher hẹp |
| Đặt fallback `@Order(1)` trước API | API chain không bao giờ được chọn | Đặt chain đặc thù ưu tiên hơn chain rộng |
| Cho rằng chain bị 403 sẽ thử chain khác | Hiểu sai xử lý và debugging | Chỉ chain đầu tiên khớp được dùng; sửa rule đúng chain |
| Đặt `requestMatchers("/api/**").permitAll()` trước admin rule | Admin có thể trở nên public | Sắp rule cụ thể trước rule bao quát |
| Dùng path-only matcher cho mọi method | Quyền READ có thể áp cho WRITE | Match cả `HttpMethod` phù hợp |
| `anyRequest().denyAll()` trong API được xem như chặn cả app | Bỏ sót trang/endpoint ngoài API | Fallback bao phủ toàn bộ phần còn lại |
| Form login ở URL ngoài `securityMatcher` | Login không được chính chain đó xử lý | Đưa URL login vào phạm vi chain, thiết kế login riêng |
| CSRF 403 bị hiểu là matcher không match | Tắt bảo vệ hoặc sửa sai lớp | Kiểm tra CSRF độc lập với permission |
| Cho static resource đi qua `web.ignoring` không cần thiết | Mất security headers và filter của chain | Dùng `permitAll` khi phù hợp |
| Tách quá nhiều chain cho từng role | Dễ bỏ sót matcher và policy khác nhau | Dùng một chain với nhiều request rule nếu cùng cơ chế |
| Kiểm tra URL mà không kiểm tra resource | IDOR/BOLA, lộ dữ liệu đa tenant | Kiểm tra owner/tenant/action/state tại service/repository |
| Chỉ có test đường thành công | Không phát hiện endpoint public trái ý | Test anonymous, sai role, sai method, đường ngoài chain |

## 12. Quy trình review cấu hình một cách có hệ thống

Mỗi lần thêm endpoint hoặc chia chain, hãy đi theo trình tự:

1. **Liệt kê request cần bảo vệ:** path, HTTP method, servlet mapping, session/token, các endpoint login/logout/health/actuator/webhook.
2. **Xác định cơ chế bảo mật:** Các request này có cần filter khác nhau thật không? Nếu không, ưu tiên một chain với nhiều rule.
3. **Ghi các chain theo đúng thứ tự:** `@Order(1)` cho chain đặc thù, tiếp đến các chain hẹp khác, và **fallback không có matcher hẹp**.
4. **Xét từng request vào chain nào:** Không nhìn role trước; nhìn `securityMatcher` và `@Order`. Nếu không có chain nào nhận, đó là tình huống cần xử lý.
5. **Xét rule phân quyền trong chain:** Đọc `requestMatchers` từ trên xuống; rule đầu tiên khớp sẽ quyết định yêu cầu. Cuối chain có `anyRequest().denyAll()` hoặc chính sách fallback được chọn có chủ ý.
6. **Xem các filter khác:** HTTP Basic, form login, CSRF, CORS, session, headers, OAuth2/JWT, custom filters có nằm ở chain thực tế không?
7. **Viết test âm tính:** Anonymous; user thiếu permission; method khác; URL ngoài chain; không CSRF; error dispatch; identity khác tenant/owner.
8. **Kiểm tra transport và nghiệp vụ:** HTTPS bảo vệ credential, service kiểm tra owner/tenant. URL matcher không thay các lớp này.
9. **Review sau nâng cấp:** Matcher implementation, cấu hình Boot auto-configuration và endpoint filter cung cấp có thể thay đổi; kiểm tra bằng test hành vi thật.

### Ma trận test tối thiểu cho nhiều chain

| Trường hợp | Điều cần chứng minh |
| --- | --- |
| URL trong API, đúng permission | Request thành công |
| URL trong API, sai permission | Không fallback sang chain khác |
| URL trong API, sai HTTP method | Không dùng nhầm quyền GET cho POST |
| URL ngoài API, anonymous | Chịu fallback đúng chính sách |
| URL ngoài API, user hợp lệ nhưng không được phép | Bị từ chối bởi fallback |
| API có POST, CSRF đang bật | Thiếu token bị chặn dù permission đủ |
| URL login/logout/CSRF | Có filter và endpoint phù hợp với chain |
| Resource tồn tại nhưng thuộc owner khác | Service từ chối dù chain cho phép action |
| Thêm một endpoint mới | Mặc định từ chối nếu chưa định nghĩa rule |
| Có nhiều servlet/dispatcher/error | Matcher và error rendering đúng ý định |

## 13. Bài tập tư duy và đáp án

**Câu 1.** Chain A có `securityMatcher("/api/**")`, trong chain đặt `anyRequest().denyAll()`. Không có chain B. `GET /internal/secrets` có bị Spring Security từ chối không?

**Đáp án:** Không thể kết luận bị từ chối bởi Spring Security, vì chain A không match. Nếu không có chain khác, đường đó **không được bảo vệ bởi Spring Security chain**. Cần fallback hoặc cấu hình một chain bao phủ toàn bộ.

**Câu 2.** Chain A `@Order(1)` match `/api/**` và yêu cầu `ROLE_USER`. Chain B `@Order(2)` cũng match `/api/admin/**` và yêu cầu `ROLE_ADMIN`. Admin không có `ROLE_USER`. Chain nào xử lý `GET /api/admin/dashboard`?

**Đáp án:** Chain A xử lý vì match đầu tiên; request admin có thể bị 403 do thiếu `ROLE_USER`. Chain B không được thử. Phải sửa matcher/thứ tự: chain admin hẹp trước chain API rộng, hoặc đưa rule admin vào API chain.

**Câu 3.** Trong một chain, rule `requestMatchers("/api/**").permitAll()` xuất hiện trước `requestMatchers("/api/admin/**").hasRole("ADMIN")`. Điều gì xảy ra với đường admin?

**Đáp án:** Rule rộng khớp trước và cho phép, nên rule admin không được xét. Sắp xếp lại quy tắc và hạn chế `permitAll` cho các endpoint thực sự công khai.

**Câu 4.** `anyRequest().denyAll()` có luôn an toàn nếu không cấu hình các rule nào khác không?

**Đáp án:** Nó từ chối tất cả request **mà chain hiện tại đã chọn**, nhưng không ảnh hưởng đường không match chain. Hơn nữa, deny-all có thể làm login, error handling và asset cần thiết không chạy; cần thiết kế allowlist phù hợp.

**Câu 5.** Ở REST API dùng POST, người dùng có đúng `REPORT_WRITE` nhưng nhận 403. Có phải `securityMatcher` sai?

**Đáp án:** Chưa chắc. Request có thể đã chọn đúng chain, nhưng `CsrfFilter` chặn vì thiếu token, hoặc policy khác từ chối. Kiểm tra bằng logs và test có/không `csrf()` trước khi sửa matcher.

**Câu 6.** Khi chỉ cần phân quyền `/api/admin/**` theo ADMIN và `/api/user/**` theo USER nhưng mọi route dùng cùng HTTP Basic filter, có cần tạo hai SecurityFilterChain?

**Đáp án:** Thường không. Một chain với hai `requestMatchers` được sắp xếp đúng và `anyRequest().denyAll()` là đủ; tách chain có ích khi bộ filter/cơ chế bảo mật ở hai nhóm thực sự khác nhau.

**Câu 7.** Dùng `securityMatcher("/secured/**")` + `formLogin(withDefaults())` nhưng đường `GET /login` bị lỗi. Lý do?

**Đáp án:** `/login` không match `/secured/**`, nên filter trong chain đó không thể cung cấp login URL mặc định. Cần thiết kế endpoint login nằm trong phạm vi được bảo vệ/cho phép đúng và controller trang login nếu custom.

## 14. Ghi nhớ

- **Chọn chain trước, phân quyền request sau.** `securityMatcher` và `requestMatchers` không thay thế nhau.
- **Hai lần first match:** chỉ chain khớp đầu tiên chạy; chỉ rule phù hợp đầu tiên trong chain đó quyết định quyền HTTP.
- **`anyRequest` chỉ sống trong chain hiện tại**; fallback catch-all rất quan trọng khi có nhiều chain.
- **Bộ lọc không cộng dồn qua nhiều chain.** Mỗi chain phải tự có cơ chế authentication, CSRF, headers và policy phù hợp.
- **Chỉ tách nhiều chain khi cần khác biệt cấp filter;** nếu chỉ khác quyền URL, nhiều rule trong một chain dễ kiểm soát hơn.
- **Kiểm thử cả trường hợp phải bị từ chối** và kiểm tra owner/tenant ở service, vì policy URL chưa bảo đảm quyền với từng tài nguyên.

## Tài liệu tham khảo

- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity, securityMatcher vs requestMatchers](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authorize HTTP Requests, Security Matchers](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — Servlet Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — MockMvc Security Test Setup](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/setup.html)
- [Spring Security 6.5 — MockMvc CSRF Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Boot 3.5.16 release and OSS support](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
