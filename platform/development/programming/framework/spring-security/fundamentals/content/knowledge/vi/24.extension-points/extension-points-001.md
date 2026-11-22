# Chọn cấu hình có sẵn trước khi viết thành phần bảo mật riêng

## 1. Ý tưởng cốt lõi

Spring Security là một framework có sẵn **các cơ chế bảo vệ, các chiến lược mở rộng và một DSL để ghép chúng thành cấu hình**. Khi một yêu cầu mới xuất hiện, câu hỏi đầu tiên nên là: **Spring Security đã có bộ lọc, provider, handler hoặc tùy chọn cấu hình giải quyết yêu cầu này chưa?** Chỉ tạo thành phần mới khi cấu hình chuẩn và các extension point nhỏ không thể đáp ứng hành vi nghiệp vụ.

Đây là nguyên tắc đặc biệt quan trọng ở chủ đề **Điểm mở rộng**: biết cách mở rộng không có nghĩa là phải mở rộng. Việc tự viết `Filter`, tự phân tích JWT, tự quản lý phiên hoặc tự cài luồng đăng nhập thường kéo theo trách nhiệm về thứ tự bộ lọc, ngoại lệ, bảo vệ CSRF, session fixation, response, logging và cập nhật bảo mật mà framework đã giải quyết.

**Mục tiêu học tập:** nhận diện nhu cầu bảo mật; chọn đúng DSL hoặc thành phần chuẩn; phân biệt cấu hình, thay chiến lược và viết cơ chế mới; hiểu một ứng dụng mẫu chạy được; biết khi nào cần `SecurityFilterChain` riêng, `AuthenticationProvider`, `AuthorizationManager` hay filter tùy biến; và đánh giá rủi ro trước khi tự xây dựng.

Phạm vi ví dụ chạy chính là **Spring MVC/Servlet với Java 17 và Spring Boot 3.5.7 (Spring Security 6.x)**. Phần cuối chỉ rõ tên cấu hình tương ứng với **WebFlux/reactive**. Cú pháp API có thể khác giữa các nhánh phiên bản, vì vậy khi triển khai thực tế cần dùng tài liệu đúng phiên bản được quản lý bởi Spring Boot BOM.

## 2. Hiểu đúng ba cấp độ can thiệp

| Cấp độ | Việc làm | Ví dụ | Mức ưu tiên |
| --- | --- | --- | --- |
| **1. Dùng cấu hình có sẵn** | Khai báo chính sách và bật cơ chế đã có | `authorizeHttpRequests`, `httpBasic`, `formLogin`, `oauth2ResourceServer`, `csrf` | Nên thử đầu tiên |
| **2. Cắm chiến lược tại điểm mở rộng** | Thay đúng một thành phần mà framework chủ động gọi | `UserDetailsService`, `PasswordEncoder`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, `JwtAuthenticationConverter` | Khi cấu hình mặc định chưa đủ |
| **3. Viết cơ chế mới** | Tạo provider, manager, handler hoặc filter mới, xác định hợp đồng và vị trí của nó | `AuthenticationProvider` tùy biến, `OncePerRequestFilter` | Chỉ khi có yêu cầu cụ thể chưa được API chuẩn giải quyết |

Sự khác nhau: cấp 1 thay **quy tắc**, cấp 2 thay **một chiến lược**, cấp 3 bổ sung **cơ chế xử lý**. Khi chỉ cần chuyển `/admin` từ “đã đăng nhập” sang “cần ADMIN”, không có lý do để viết thêm một filter. Khi lưu user trong database, thay `UserDetailsService` thường đã đủ; không cần tự viết `UsernamePasswordAuthenticationFilter`.

Một cách hình dung ngắn gọn:

```text
Yêu cầu bảo mật mới
        |
        v
Có thể mô tả bằng HttpSecurity / ServerHttpSecurity DSL?
        | Có -> cấu hình DSL -> kiểm thử
        | Không
        v
Có thành phần chuẩn và extension point nhỏ phù hợp?
        | Có -> cấu hình thành phần đó -> kiểm thử
        | Không
        v
Định nghĩa hợp đồng, vị trí, luồng lỗi và kiểm thử
cho cơ chế riêng trước khi triển khai
```

## 3. Tra cứu khả năng chuẩn theo từng yêu cầu

| Nhu cầu | Chọn công cụ có sẵn trước | Tránh tự viết ngay |
| --- | --- | --- |
| Phân quyền URL theo vai trò hoặc HTTP method | `authorizeHttpRequests`, `requestMatchers`, `hasRole`, `hasAuthority`, `access` | Filter tự so URL và trả 403 |
| Quyền trên phương thức service | `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize` | Thêm logic phân quyền lặp trong mọi controller |
| Form đăng nhập cho trình duyệt | `formLogin` | Servlet tự kiểm mật khẩu, tự quản lý phiên |
| API username/password đơn giản | `httpBasic` (khi yêu cầu phù hợp, chạy qua HTTPS) | Bộ lọc tự đọc, decode và kiểm Basic header |
| Tài khoản từ database | `UserDetailsService` + `PasswordEncoder` + provider chuẩn | Tự tạo authentication pipeline chỉ để truy vấn bảng user |
| Đăng nhập qua OAuth2/OIDC | `oauth2Login` + OAuth2 Client | Tự làm state, redirect, code exchange, token validation |
| API nhận Bearer JWT | `oauth2ResourceServer(o -> o.jwt(...))` + `issuer-uri` / `JwtDecoder` | Tự tách chuỗi JWT, giải mã và tin claims |
| API nhận opaque token | Resource Server `opaqueToken` / introspection | Tự gọi introspection endpoint trong filter |
| 401, 403, chuyển hướng khi chưa đăng nhập | `exceptionHandling`, `AuthenticationEntryPoint`, `AccessDeniedHandler` | Tự catch mọi ngoại lệ ở đầu chuỗi |
| Bảo vệ CSRF, security headers | `csrf`, `headers` và cấu hình chuẩn | Tự làm CSRF token hoặc bỏ toàn bộ bảo vệ |
| CORS cho browser client | `cors` + `CorsConfigurationSource` / Spring MVC CORS | Filter tự trả các header `Access-Control-*` |
| Chính sách session, logout, request cache | `sessionManagement`, `logout`, `requestCache` | Quản lý session thủ công |
| Nhiều vùng URL có chính sách độc lập | Nhiều `SecurityFilterChain` với `securityMatcher` và `@Order` | Filter lớn phân nhánh theo mọi đường dẫn |
| Chạy WebFlux | `SecurityWebFilterChain` + `ServerHttpSecurity` | Sử dụng servlet filter trong reactive pipeline |

**Chọn cơ chế theo kiến trúc hệ thống:**

- Ứng dụng web phục vụ HTML và dùng session: thường bắt đầu với `formLogin`, bảo vệ CSRF cho thao tác thay đổi trạng thái và chính sách URL/method.
- API chỉ được gọi bởi client có credentials hợp lệ: xem xét `httpBasic` hoặc, phổ biến trong hệ thống có identity provider, `oauth2ResourceServer`; thiết kế theo giao thức thực tế.
- API OAuth2 kiểm tra access token: dùng **Resource Server**, không dùng `oauth2Login` chỉ vì token có chữ “OAuth2”. `oauth2Login` phục vụ đăng nhập người dùng qua provider; Resource Server kiểm tra Bearer token đến API.
- Một hệ thống vừa có web session vừa có REST API: kiểm tra khả năng khai báo nhiều `SecurityFilterChain` trước khi thêm filter tự nhận biết loại request.

**Lưu ý:** thành phần có sẵn vẫn cần cấu hình đúng. Đừng mặc định rằng “có Spring Security dependency” nghĩa là endpoint, issuer, CSRF/CORS và các vai trò đều đã đúng yêu cầu.

## 4. Spring Boot tự cấu hình những gì, và giới hạn của nó

Khi ứng dụng Servlet thêm `spring-boot-starter-security` mà chưa cung cấp cấu hình bảo mật riêng, Spring Boot tạo cấu hình web mặc định theo điều kiện của auto-configuration. Trong tình huống cơ bản, các request yêu cầu xác thực; form login và HTTP Basic được hỗ trợ; môi trường demo thường có user mặc định và mật khẩu ngẫu nhiên được ghi ở log khởi động.

Điều này chỉ giúp ứng dụng **có bảo vệ cơ bản**, không thay thế thiết kế security cho sản phẩm. Nếu tự khai báo `@Bean SecurityFilterChain`, chính sách web mặc định của Boot có thể được thay bằng chain của bạn. Hãy khai báo đầy đủ matcher, cơ chế xác thực, exception handling và fallback phù hợp; đừng cho rằng mọi cài đặt trước đó tiếp tục tồn tại như cũ.

Bộ lọc thực tế được chọn qua `FilterChainProxy` và `SecurityFilterChain`; mỗi filter làm một nhiệm vụ, chạy theo thứ tự mà Spring Security quản lý. Việc thêm một custom filter làm phát sinh trách nhiệm về thứ tự, lỗi, lifecycle và nguy cơ chạy trùng. Trong phần lớn trường hợp, nên để Spring Security xây dựng chuỗi từ cấu hình DSL.

**Một hiểu nhầm phổ biến:** `permitAll()` cho phép request qua **quy tắc ủy quyền**, còn request vẫn đi qua chuỗi Spring Security và có thể nhận security headers, CSRF hoặc các chính sách khác. `web.ignoring()` bỏ qua chuỗi bảo mật cho URL được chỉ định; đây là thay đổi rộng hơn, không nên dùng để “sửa 401” cho API public.

## 5. Ví dụ Java 17+ chạy được: giải quyết yêu cầu chỉ bằng cấu hình chuẩn

**Yêu cầu:** `GET /public` được truy cập tự do; `GET /profile` yêu cầu đăng nhập; `GET /admin` yêu cầu vai trò ADMIN. Người dùng demo có USER; API sử dụng HTTP Basic để dễ kiểm chứng bằng `curl`. Toàn bộ yêu cầu có thể giải bằng DSL và `UserDetailsService` chuẩn, không tạo custom filter.

Cấu trúc thư mục:

```text
built-in-security/
├── pom.xml
└── src/main/java/demo/
    └── BuiltInSecurityApplication.java
```

**`pom.xml`** — Spring Boot 3.5.7 quản lý phiên bản dependency tương thích:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>built-in-security</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

**`src/main/java/demo/BuiltInSecurityApplication.java`**:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BuiltInSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuiltInSecurityApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public").permitAll()
                        .requestMatchers("/admin").hasRole("ADMIN")
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder passwordEncoder) {
        UserDetails learner = User.withUsername("learner")
                .password(passwordEncoder.encode("demo-password"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicPage() {
            return "public";
        }

        @GetMapping("/profile")
        String profile() {
            return "profile";
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
```

**Giải thích từng lựa chọn:**

1. `SecurityFilterChain` cho Spring Security cấu hình chuỗi chuẩn. Không có `new JwtFilter()`, `OncePerRequestFilter` hay `AuthenticationManager` tự tạo.
2. `authorizeHttpRequests` gán chính sách từ cụ thể đến tổng quát. `permitAll()` cho `/public`; `hasRole("ADMIN")` kiểm tra authority `ROLE_ADMIN`; `anyRequest().authenticated()` là fallback bảo vệ các URL còn lại.
3. `httpBasic` dùng bộ xử lý HTTP Basic có sẵn. Vô hiệu hóa **riêng** form login giúp thử bằng `curl` không nhầm với điều hướng tới trang đăng nhập; đây là lựa chọn của ví dụ API, không phải khuyến nghị tắt form login cho mọi ứng dụng.
4. `UserDetailsService` cung cấp user và `PasswordEncoder` xử lý hash mật khẩu; framework dùng provider hỗ trợ username/password. Việc tạo user “learner” không cần tự viết filter xác thực.
5. Demo **không chỉnh CSRF** và chỉ có GET. Nếu mở thêm POST/PUT/DELETE, hãy thiết kế CSRF dựa trên việc client dùng cookie/session hay Bearer token, thay vì tắt mặc định cho mọi endpoint.
6. Mật khẩu `demo-password` được ghi trực tiếp trong **mã demo** để kiểm thử; ứng dụng thực tế phải dùng nguồn secrets và kho user an toàn. `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo encoder có định dạng id và hỗ trợ chiến lược nâng cấp, tốt hơn việc dùng `{noop}` cho tài khoản thực.

**Chạy thử** (cần Java 17+ và Maven; thực hiện từ thư mục có `pom.xml`):

```bash
mvn -q -DskipTests package
java -jar target/built-in-security-0.0.1-SNAPSHOT.jar
```

Mở terminal thứ hai:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/profile
curl -i -u learner:demo-password http://localhost:8080/profile
curl -i -u learner:demo-password http://localhost:8080/admin
curl -i -u learner:wrong http://localhost:8080/profile
```

| Request | Kết quả mong đợi | Giải thích |
| --- | --- | --- |
| `GET /public`, không credentials | `200 OK`, body `public` | Rule `permitAll` |
| `GET /profile`, không credentials | `401 Unauthorized` | HTTP Basic yêu cầu xác thực |
| `GET /profile`, đúng credentials | `200 OK`, body `profile` | Provider mặc định xác thực thành công |
| `GET /admin`, user chỉ có USER | `403 Forbidden` | Người dùng đã xác thực nhưng thiếu `ROLE_ADMIN` |
| `GET /profile`, sai password | `401 Unauthorized` | Thông tin xác thực không hợp lệ |

`curl -i` hiển thị status và header. Với HTTP Basic, hãy kiểm tra header xác thực `WWW-Authenticate` do cơ chế chuẩn quản lý. Không đoán body của phản hồi lỗi từ status; framework và cấu hình có thể không sinh body giống nhau.

**Kết quả:** Tất cả yêu cầu mẫu đã được giải quyết bằng API chuẩn. Viết thêm một filter “kiểm tra admin” sẽ trùng vai trò với kiểm tra ủy quyền có sẵn, làm tăng số điểm cần audit và khả năng sinh lỗi.

## 6. Thay đổi yêu cầu: chọn cấu hình nào trước?

### Tình huống A — Ứng dụng web cần giao diện đăng nhập

Nếu hệ thống sử dụng trình duyệt, session và trang login thì nên dùng `formLogin`. Trong cấu hình ở mục 5, thay phần `httpBasic/formLogin` bằng:

```java
.formLogin(Customizer.withDefaults())
```

Đây là **đoạn cấu hình thay thế** trong cùng `SecurityFilterChain`, không phải chương trình Java độc lập. Khi chưa đăng nhập, một endpoint được bảo vệ thường dẫn người dùng tới trang login; không nhất thiết trả 401 JSON. Giữ bảo vệ CSRF cho request làm thay đổi trạng thái. Nếu có login page riêng, dùng `formLogin(form -> form.loginPage("/login"))` và bảo đảm ứng dụng thực sự cung cấp trang/endpoint phù hợp; khai báo path không tự sinh trang giao diện tùy chỉnh.

### Tình huống B — Chỉ cần truy vấn user trong cơ sở dữ liệu

Bắt đầu bằng `UserDetailsService#loadUserByUsername` (hoặc `ReactiveUserDetailsService` ở WebFlux) và `PasswordEncoder`. Chuyển đổi bản ghi user sang `UserDetails`, bao gồm account flags và granted authorities. Spring Security có `DaoAuthenticationProvider` để dùng các thành phần đó.

Ví dụ rút gọn về hợp đồng, **không phải lớp chạy độc lập**:

```java
@Override
public UserDetails loadUserByUsername(String username)
        throws UsernameNotFoundException {
    // Tra cứu user từ repository có sẵn của ứng dụng.
    // Nếu không tìm thấy, ném UsernameNotFoundException.
    // Trả UserDetails gồm password hash và authorities.
}
```

Một nhiệm vụ truy vấn dữ liệu user **không đủ** để biện minh cho việc tự triển khai `AuthenticationProvider`: provider có sẵn đã thực hiện so khớp password, kiểm tra trạng thái tài khoản và tương tác với manager. Nếu có giao thức xác thực không phải username/password, lúc đó mới đánh giá provider riêng.

### Tình huống C — API nhận Bearer JWT từ identity provider

Không tự parse JWT trong filter bằng cách cắt chuỗi tại dấu chấm và decode Base64. JWT cần được kiểm tra chữ ký, thuật toán, thời gian hiệu lực, issuer, audience khi cần, khóa ký và quy tắc mapping quyền. Dùng **OAuth2 Resource Server** của Spring Security.

Thêm dependency Maven `spring-boot-starter-oauth2-resource-server`. Trên cấu hình ứng dụng, cung cấp issuer thật mà token phát ra:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
```

Giá trị URL trên **chỉ là ví dụ**; phải thay bằng issuer chính xác của hệ thống thực. Khi tự định nghĩa `SecurityFilterChain`, bật resource server trên chain bảo vệ API:

```java
.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(Customizer.withDefaults()))
```

Framework cung cấp cơ chế lấy khóa công khai và xác thực token theo cấu hình decoder; với quyền theo scope, quy tắc như `hasAuthority("SCOPE_read")` được áp dụng khi mapping chuẩn tương ứng. Chỉ viết `JwtAuthenticationConverter` riêng khi cần chuyển claim/quyền theo quy ước riêng; nếu provider dùng **opaque token**, chọn `opaqueToken`/introspection thay vì giả định token nào cũng là JWT.

Không chuyển một access token chưa được verify vào `SecurityContext`. Đừng biến sự tồn tại của chuỗi `Authorization` thành bằng chứng người dùng đã xác thực.

### Tình huống D — Cần phân quyền theo thuộc tính nghiệp vụ

Thử `@EnableMethodSecurity` và `@PreAuthorize` cho chính sách ở lớp service. Ví dụ này là **đoạn minh họa gắn vào service đã có**, không phải một chương trình độc lập:

```java
@PreAuthorize("hasRole('ADMIN') or #owner == authentication.name")
public Invoice readInvoice(String owner, long invoiceId) {
    // Sau khi kiểm tra quyền, kiểm tra tiếp rằng invoiceId
    // thực sự thuộc về owner ở tầng truy cập dữ liệu.
    // ...
}
```

Biểu thức chỉ kiểm tra giá trị tham số `owner` so với người đăng nhập; riêng ví dụ này **chưa** chứng minh người dùng sở hữu hóa đơn. Tầng dữ liệu vẫn phải kiểm tra quan hệ sở hữu thật. Khi logic truy cập phức tạp, dùng bean policy/`AuthorizationManager` có thể được kiểm thử riêng, thay vì viết filter kiểm tra dữ liệu ở mọi request.

### Tình huống E — Frontend khác origin bị CORS preflight chặn

Cấu hình `cors(Customizer.withDefaults())` cùng `CorsConfigurationSource` hoặc cấu hình CORS Spring MVC phù hợp. Preflight thường không mang cookie; Spring Security hỗ trợ tích hợp CORS đúng thứ tự. Trước khi tự thêm filter chỉ để set header, hãy kiểm tra allowed origins, methods, headers và credentials.

Không sửa CORS bằng `permitAll("/**")` hoặc tắt toàn bộ security. CORS là cơ chế dành cho trình duyệt; nó không thay cho xác thực/ủy quyền phía server.

### Tình huống F — Hai vùng có cách đăng nhập khác nhau

Ví dụ `/api/**` dùng HTTP Basic, các trang web còn lại dùng form login. Spring Security cho phép **nhiều `SecurityFilterChain`**. Đoạn sau là cấu hình thay thế cho bean `securityFilterChain(...)` ở mục 5; không giữ đồng thời bean cũ nếu nó gây chồng chính sách không mong muốn.

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

@Bean
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public").permitAll()
                    .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Đoạn này cần `import org.springframework.core.annotation.Order;` và các import của cấu hình chính. `@Order(1)` xét chain API trước. `securityMatcher("/api/**")` quyết định **chain nào có hiệu lực**, còn `requestMatchers(...)` trong `authorizeHttpRequests` quyết định **quyền bên trong chain đã chọn**. Chain sau không có `securityMatcher` sẽ làm fallback cho các request còn lại. Nếu không chain nào khớp, request có thể không được bảo vệ bởi Spring Security. Đừng tạo hai chain cùng matcher và trông chờ cả hai chạy liên tiếp.

Với cấu hình API thực tế, chọn cơ chế xác thực đúng (Bearer thay cho Basic khi dùng OAuth2), bảo vệ CSRF đúng theo loại client, và kiểm thử cả đường dẫn ngoài `/api/**`.

## 7. Khi nào một extension point thực sự cần thiết?

Thay đúng **mảnh** phát sinh yêu cầu, giữ framework thực hiện phần còn lại:

| Yêu cầu khác mặc định | Mảnh tùy biến phù hợp | Vì sao chưa cần custom filter |
| --- | --- | --- |
| Tài khoản lấy từ DB, directory đặc thù | `UserDetailsService` / `ReactiveUserDetailsService` | Framework vẫn xử lý mật khẩu, kết quả đăng nhập và context |
| Chính sách hash mật khẩu | `PasswordEncoder` | Không phải cơ chế đọc/ủy quyền request |
| Bản ghi audit sau login | `AuthenticationSuccessHandler`, event listener | Có điểm móc chính xác khi đăng nhập thành công |
| Tùy chỉnh response khi chưa xác thực hoặc bị cấm | `AuthenticationEntryPoint`, `AccessDeniedHandler` | Đã có cơ chế điều phối ngoại lệ |
| Mapping claim JWT thành authority nội bộ | `JwtAuthenticationConverter` hoặc converter phù hợp | Resource Server vẫn verify token và áp dụng chính sách |
| Quyền phụ thuộc dữ liệu đối tượng | Method security, `AuthorizationManager` hoặc bean policy | Kiểm tra theo nghiệp vụ mà không tự quản lý filter chain |
| Xác thực bằng một credential/protocol thật sự mới | `AuthenticationConverter` / `AuthenticationProvider` tùy biến cùng cơ chế Spring Security | Có thể tận dụng infrastructure chuẩn thay vì viết mọi thứ từ đầu |

**Viết `AuthenticationProvider` riêng** khi cần định nghĩa cách xác thực mà provider chuẩn không hỗ trợ. Provider phải xử lý loại `Authentication` phù hợp (`supports`), kiểm tra credential đúng cách và trả kết quả đã xác thực hoặc exception đúng hợp đồng. Provider không nên tự trả HTTP response từ tầng nghiệp vụ. Kết hợp provider với filter/endpoint đúng loại client thay vì gắn mọi quyết định vào một lớp.

**Chỉ viết filter riêng** nếu yêu cầu thực sự cần chặn/xử lý HTTP request tại vị trí cụ thể và không có cơ chế chuẩn thay thế (ví dụ giao thức chứng thực đặc thù bắt buộc trích xuất header và chuyển sang manager). Đối với Servlet, `HttpSecurity` cung cấp `addFilterBefore`, `addFilterAfter` và `addFilterAt`; vị trí phụ thuộc việc cần context, authentication và authorization đã được thiết lập hay chưa. Đối với WebFlux, đó là `WebFilter` và `SecurityWebFiltersOrder` trong `ServerHttpSecurity`.

Cần ghi rõ hợp đồng về filter ordering, cách xử lý `AuthenticationException`/`AccessDeniedException`, khi nào gọi tiếp chain, thread safety, cách tạo/giải phóng tài nguyên và idempotency. Một Servlet `Filter` là Spring bean có thể được Boot đăng ký với container **và** thêm vào Spring Security chain, dẫn tới chạy hai lần; hãy kiểm soát registration thay vì chỉ thêm `@Component` một cách máy móc.

## 8. Kiểm thử trước và sau khi lựa chọn

Một cấu hình được coi là đáp ứng yêu cầu khi đã kiểm tra ít nhất các kịch bản liên quan:

1. Anonymous truy cập đường dẫn public và protected: 200/401/redirect đúng chính sách.
2. Credentials/token hợp lệ và sai: phân biệt authentication failure với authorization denied.
3. User có và thiếu role/scope: 200 hoặc 403 đúng; xác minh prefix `ROLE_` hay `SCOPE_`.
4. HTTP method khác nhau, URL lồng nhau, request không khớp matcher, fallback chain và thứ tự `@Order`.
5. POST/PUT/DELETE trong ứng dụng dùng cookie: có CSRF token hợp lệ/không hợp lệ; không vô tình tắt bảo vệ.
6. Request `OPTIONS` preflight từ origin được phép/không được phép, nếu sử dụng CORS.
7. Basic có challenge phù hợp; Bearer có status/header `WWW-Authenticate` đúng giao thức; form login chuyển hướng đúng.
8. Test service-level authorization, đặc biệt quyền dựa trên chủ sở hữu đối tượng; đừng chỉ kiểm tra URL.
9. Xác minh log/metrics đủ để điều tra nhưng không xuất mật khẩu, bearer token, session id hoặc stack trace ra response.

Ví dụ kiểm tra nhanh `/admin`: một request **không có credentials** thường nhận 401 khi HTTP Basic, trong khi request của user chỉ có `ROLE_USER` nhận 403. Nếu cả hai cùng 200 thì chính sách đã sai. Nếu đều nhận 403, cần xem xét ngoại lệ CSRF, matcher, entry point hoặc tình trạng xác thực trước khi viết thêm filter.

## 9. Những sai lầm thường gặp khi “tự viết cho linh hoạt”

- **Tự parse và xác minh JWT** trong filter rồi tin `sub` hoặc `roles` chưa xác thực chữ ký, issuer, thời hạn. Giải pháp: resource server có sẵn; customize converter chỉ khi cần.
- **Thay `SecurityFilterChain` của Boot bằng một bean quá sơ sài** và vô tình bỏ rule fallback hoặc cơ chế đăng nhập. Giải pháp: xác định chính sách cuối cùng của toàn bộ đường dẫn, không mặc định cấu hình Boot tự ghép vào bean mới.
- **Đăng ký custom filter ở cả servlet container và security chain**, gây gọi hai lần. Giải pháp: quản lý đăng ký và vị trí chính xác; ưu tiên DSL.
- **Lạm dụng `web.ignoring`** cho URL công khai. Giải pháp: dùng `permitAll` khi cần giữ các lớp bảo vệ khác của Spring Security.
- **Tắt CSRF vì mọi POST đều bị 403**, dù ứng dụng dùng cookie/session. Giải pháp: kiểm tra loại client, CSRF token và nguyên nhân 403.
- **Xử lý login, Basic, OAuth2 và Bearer bằng một filter “đa năng”**. Giải pháp: dùng cơ chế tiêu chuẩn riêng và chia chain khi thật sự cần.
- **Nhầm phân quyền URL với quyền đối tượng**: cho phép `GET /invoice/42` nhưng không kiểm tra người dùng có sở hữu invoice 42. Giải pháp: kiểm tra ở service/data-access layer.
- **Gọi `hasRole("ROLE_ADMIN")`** thay vì `hasRole("ADMIN")` (với prefix `ROLE_` mặc định). Đối với authority tên khác, cân nhắc `hasAuthority(...)` và kiểm thử mapping.
- **Sao chép các API đã lỗi thời** như `WebSecurityConfigurerAdapter` hoặc `antMatchers` từ tutorial cũ vào dự án dùng Spring Security 6/7. Giải pháp: dùng `SecurityFilterChain` và lambda DSL, đọc tài liệu đúng phiên bản.
- **Dùng servlet security API trong WebFlux**, hoặc ngược lại. Giải pháp: chọn đúng runtime và giao diện reactive.

## 10. Đối chiếu nhanh với WebFlux/reactive

Bản WebFlux dùng `SecurityWebFilterChain`, `ServerHttpSecurity`, `authorizeExchange` và `WebFilter`. Ví dụ sau chỉ là **bean cấu hình** đặt trong ứng dụng WebFlux đã có dependency WebFlux + Spring Security; nó không thể chạy độc lập nếu không có ứng dụng/config phù hợp:

```java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex
                    .pathMatchers("/public").permitAll()
                    .pathMatchers("/admin").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

Những vai trò vẫn tương tự nhưng tên API khác:

| Servlet/MVC | WebFlux/reactive |
| --- | --- |
| `HttpSecurity`, `SecurityFilterChain` | `ServerHttpSecurity`, `SecurityWebFilterChain` |
| `authorizeHttpRequests`, `requestMatchers` | `authorizeExchange`, `pathMatchers` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| `AuthenticationEntryPoint`, `AccessDeniedHandler` | `ServerAuthenticationEntryPoint`, `ServerAccessDeniedHandler` |
| Servlet `Filter` / `OncePerRequestFilter` | Reactive `WebFilter` |

Trước khi tạo `WebFilter` thủ công, thử DSL `httpBasic`, `formLogin`, `oauth2ResourceServer`, `csrf`, `cors` và các server-side handler. Reactive code nên trả `Mono`/`Flux` cho pipeline xử lý; không gọi `block()`/`subscribe()` tùy tiện trong authentication handler. Cần đặt đúng request matcher và thứ tự các `SecurityWebFilterChain`.

## 11. Quy trình ra quyết định có thể áp dụng trong code review

Khi một yêu cầu security mới được giao, hãy trả lời theo thứ tự:

1. **Tài sản được bảo vệ là gì?** URL, method, object, business operation, browser session hay Bearer API?
2. **Đăng nhập theo chuẩn nào?** HTTP Basic, form, OAuth2 Login/OIDC, Resource Server JWT/opaque, LDAP, X.509… Có starter và config tương ứng chưa?
3. **Chỉ cần đổi quy tắc?** Thử matcher, role, authority, method security, session/CSRF/CORS/header DSL.
4. **Chỉ cần đổi dữ liệu hoặc cách ánh xạ?** Thử `UserDetailsService`, `PasswordEncoder`, converters, handlers, repositories.
5. **Mới thật sự cần component riêng?** Viết rõ contract, security boundary, vị trí trong chain, lỗi và những phần framework vẫn chịu trách nhiệm.
6. **Đã test kịch bản thất bại chưa?** Credentials sai, thiếu quyền, CSRF, token hết hạn, bearer challenge, nhiều chain và URL không khớp.
7. **Có thể giảm code mà vẫn đúng yêu cầu không?** Nếu một custom filter chỉ làm lại logic của DSL/provider chuẩn, loại bỏ nó để giảm bề mặt phải bảo trì.

Ví dụ quyết định: “API phải nhận JWT với quyền đọc dữ liệu” → `spring-boot-starter-oauth2-resource-server` + `issuer-uri` + `oauth2ResourceServer(jwt)` + `hasAuthority("SCOPE_read")`. Chỉ thêm converter nếu issuer dùng claim quyền riêng. Việc viết `JwtFilter` ngay từ đầu bỏ qua các bước quan trọng đã có trong framework.

## 12. Câu hỏi tự luyện

1. Vì sao việc chuyển `/admin` sang `hasRole("ADMIN")` không cần một `Filter` riêng?
2. `securityMatcher` và `requestMatchers` khác nhau ở bước nào trong quá trình chọn chain và kiểm tra quyền?
3. Khi user được lưu trong database, lý do nào để chọn `UserDetailsService` trước `AuthenticationProvider` tự viết?
4. Khi API đã có Bearer JWT, vì sao dùng Resource Server an toàn hơn một filter chỉ Base64-decode token?
5. Khi nào `@PreAuthorize` cần phối hợp với kiểm tra chủ sở hữu thực ở database?
6. Khi thêm `SecurityFilterChain` tự định nghĩa, điều gì phải kiểm tra lại về auto-configuration và URL fallback?
7. Trong ứng dụng WebFlux, vì sao `OncePerRequestFilter` và `HttpSecurity` không phải cặp API phù hợp?

## 13. Tài liệu chính thức

- [Spring Security — Servlet Architecture / Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Username/Password Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/index.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)

**Nguyên tắc ghi nhớ:** dùng DSL để diễn đạt chính sách, dùng extension point nhỏ để thay đổi chi tiết cần thiết, chỉ viết cơ chế mới khi có yêu cầu thực sự vượt khả năng chuẩn. Đó là cách mở rộng Spring Security mà vẫn giữ được các lớp bảo vệ đã được framework kiểm tra và duy trì.
