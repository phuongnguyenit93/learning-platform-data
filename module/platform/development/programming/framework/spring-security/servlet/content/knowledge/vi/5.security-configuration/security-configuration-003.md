# Nhiều SecurityFilterChain và ý nghĩa của @Order trong Spring Security Servlet

## 1. Khi nào cần nhiều SecurityFilterChain?

Ứng dụng Spring Boot sử dụng **Spring MVC/Servlet** có thể phục vụ nhiều nhóm HTTP endpoint với các cơ chế bảo mật khác nhau. Ví dụ: `/api/**` là API cần HTTP Basic hoặc Bearer token; các trang web dùng form login và session; `/admin/**` yêu cầu quyền quản trị. Khi chỉ khác **quyền truy cập URL**, một `SecurityFilterChain` với nhiều `requestMatchers` thường đã đủ. Khi khác **bộ filter, cơ chế đăng nhập, session/CSRF/CORS, cách xử lý lỗi 401/302 hoặc phạm vi bảo mật**, nhiều chain giúp cấu hình rõ ràng hơn.

**Quy tắc cốt lõi:** `FilterChainProxy` của Spring Security chọn **SecurityFilterChain đầu tiên khớp request**, theo thứ tự ưu tiên. Request không chạy lần lượt qua tất cả các chain để cộng dồn quyền. Annotation `@Order` xác định **thứ tự thử chain**; `securityMatcher` xác định **chain khớp URL nào**; sau khi chọn chain, `requestMatchers` và `anyRequest` bên trong `authorizeHttpRequests` mới quyết định quyền truy cập.

Bài này dành cho **Servlet stack** với Spring Boot 3.x, Spring Security 6.x, `SecurityFilterChain` và `HttpSecurity`. Với Spring WebFlux, cơ chế là `SecurityWebFilterChain`/`ServerHttpSecurity` và ví dụ Servlet không áp dụng nguyên xi.

## 2. Kiến trúc: từ Servlet container đến một SecurityFilterChain

~~~text
HTTP client
    |
    v
Tomcat / Servlet container
    |
    v
Servlet Filter chain (container quản lý)
    |
    +-- DelegatingFilterProxy("springSecurityFilterChain")
           |
           v
       FilterChainProxy (Spring Security)
           |
           +-- thử chain #1: @Order(1), securityMatcher("/api/**")
           |       nếu khớp -> CHỌN #1, không thử các chain tiếp
           |
           +-- thử chain #2: @Order(2), securityMatcher("/admin/**")
           |       nếu khớp -> CHỌN #2, không thử tiếp
           |
           +-- thử chain #3: @Order(3), matcher mọi request
                   nếu khớp -> CHỌN #3 (fallback)
           |
           v
       Các security filter thuộc CHAIN ĐƯỢC CHỌN
           -> xác thực / phân quyền theo cấu hình của chain
           -> cho phép -> chuyển tiếp Servlet Filter chain
    |
    v
DispatcherServlet -> Controller -> Service -> Response
~~~

Đây là sơ đồ nguyên lý, không phải thứ tự chính xác của mọi filter con trong mọi phiên bản. Cần phân biệt ba loại “thứ tự”:

| Loại thứ tự | Cơ chế | Ý nghĩa |
| --- | --- | --- |
| Thứ tự **Servlet Filter** | Đăng ký filter với Servlet container, Boot filter registration | `DelegatingFilterProxy` đứng ở đâu so với filter khác trong container |
| Thứ tự **SecurityFilterChain** | `@Order`, `Ordered` trên bean chain | `FilterChainProxy` thử chain nào trước |
| Thứ tự **security filter bên trong một chain** | `HttpSecurity`, các cấu hình Spring Security, vị trí filter | Authentication, context, authorization, exception translation... chạy theo thứ tự nào |

Bên trong một chain còn có thứ tự **authorization rule**: rule matcher cụ thể phải đứng trước `anyRequest`. `@Order` không thay thế thứ tự rule này.

**Ví dụ chọn chain:** Với #1 khớp `/api/**`, #2 khớp `/admin/**`, #3 khớp mọi URL: `GET /api/me` dùng #1; `GET /admin/users` dùng #2; `GET /about` dùng #3. Nếu #1 từ chối request vì chưa đăng nhập, Spring Security **không thử lại chain #2 hoặc #3**.

## 3. @Order thực sự làm gì?

Đặt trên bean `SecurityFilterChain`:

~~~java
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
@Order(2)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Hai method trên **chỉ minh họa bean cấu hình** và cần đặt trong class `@Configuration` cùng các import phù hợp. Project hoàn chỉnh ở phần 6.

Quy tắc chi tiết:

1. **Giá trị @Order nhỏ hơn được thử trước.** `@Order(1)` ưu tiên trước `@Order(2)`. Vị trí method trong file hoặc tên method không quyết định thứ tự này.
2. **@Order không quyết định URL được bảo vệ.** `securityMatcher` của từng chain mới xác định phạm vi; một chain ưu tiên cao nhưng không khớp sẽ bị bỏ qua cho request đó.
3. **Hai chain cùng khớp thì chain đầu tiên thắng.** Không có việc chạy filter của chain thứ nhất rồi chuyển sang chain thứ hai vì bị 401/403.
4. **Thứ tự bằng nhau dễ gây mơ hồ.** Nếu các matcher chồng lấp, hãy dùng giá trị `@Order` rõ ràng, duy nhất để tránh dựa vào thứ tự đăng ký bean.
5. **Không khai báo @Order** thường đặt bean gần cuối trong thứ tự mặc định so với `@Order(1)` và `@Order(2)`; khi tính đúng đắn phụ thuộc ưu tiên fallback, ghi rõ order giúp người đọc và người kiểm thử hiểu thiết kế.
6. `@Order` **không thay đổi thứ tự filter con**. Nếu muốn thêm custom authentication filter, nghiên cứu `http.addFilterBefore` / `addFilterAfter` và vị trí chuẩn của Spring Security, không điều khiển bằng order của bean chain.

`Ordered.HIGHEST_PRECEDENCE` có giá trị nhỏ nhất, `Ordered.LOWEST_PRECEDENCE` rất lớn; không cần dùng các giá trị cực hạn nếu `1`/`2`/`3` diễn đạt đủ ý.

Một nguyên tắc dễ nhớ: **@Order trả lời “thử chain nào trước?”, không trả lời “chain đó khớp cái gì?” hoặc “filter nào chạy trước trong chain?”**

## 4. securityMatcher khác requestMatchers như thế nào?

Ví dụ:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public").permitAll()
        .requestMatchers("/api/admin").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
~~~

- `securityMatcher("/api/**")` là matcher **cấp chain**: những request nào có thể đi vào chain này.
- `requestMatchers("/api/public").permitAll()` là **quy tắc authorization** cho request đã đi vào chain. `permitAll` không bỏ qua toàn bộ security filters.
- `requestMatchers("/api/admin").hasRole("ADMIN")` là một rule khác **trong cùng chain**.
- `anyRequest().authenticated()` áp dụng cho **mọi request còn lại đã thuộc chain**, chứ không mở rộng `/api/**` để bao phủ `/admin`, `/reports` hoặc `/login`.
- Nếu không khai báo `securityMatcher(...)`, một `SecurityFilterChain` mặc định dùng matcher bao phủ **mọi request**, rất phù hợp để làm chain dự phòng đặt cuối.

Cấu hình `authorizeHttpRequests` được xét theo thứ tự quy tắc được khai báo. Đặt rule cụ thể trước `anyRequest`; tránh tưởng rằng `anyRequest` có thể được viết đầu rồi những rule phía sau còn cơ hội chạy.

Trong môi trường Spring MVC, matcher tạo bởi overload nhận chuỗi có thể dựa vào các thành phần matching của MVC. Không mặc định chúng luôn là Ant matcher. Nếu ứng dụng có context path, servlet path tùy chỉnh hoặc nhiều servlet, cần kiểm tra request matcher và cách nó diễn giải path. Không dùng header/path mà client tự khai làm bằng chứng quyền truy cập.

### Hai tầng quyết định độc lập

~~~text
securityMatcher() -> chain này có áp dụng cho request không?
    |
    +-- Không -> thử SecurityFilterChain tiếp theo
    |
    +-- Có   -> chọn chain; chạy filter của chain
                    |
                    v
            authorizeHttpRequests()
                    |
                    +-- requestMatchers cụ thể
                    +-- anyRequest cho phần còn lại
                    |
                    v
            Cho phép hoặc từ chối
~~~

Một request bị từ chối tại bước authorization của chain đã chọn **không quay lại** bước chọn chain để tìm lựa chọn “dễ hơn”.

## 5. Thứ tự chain và tình huống matcher chồng lấp

Giả sử ba chain:

| Chain | @Order | securityMatcher | Chính sách mô tả |
| --- | --- | --- | --- |
| API | 1 | `/api/**` | `/api/public` public, `/api/admin` ADMIN; API khác authenticated |
| Admin | 2 | `/admin/**` | Toàn bộ cần ADMIN |
| Web | 3 | Mọi request | `/public` public, còn lại authenticated |

| Request | Chain được chọn | Giải thích |
| --- | --- | --- |
| `GET /api/public` | API | Khớp ngay chain #1 |
| `GET /api/admin` | API | Quyền ADMIN được kiểm tra **trong API chain** |
| `GET /admin/users` | Admin | API không khớp, Admin khớp |
| `GET /public` | Web | Hai chain đầu không khớp |
| `GET /reports` | Web | Fallback bắt mọi URL còn lại |

Bảng trên chỉ xác định chain, **không khẳng định HTTP status**. Status phụ thuộc danh tính, role, mechanism login, CSRF, CORS, MVC và exception handler.

### Lỗi shadowing: chain quá rộng được đặt trước

~~~java
@Bean
@Order(1)
SecurityFilterChain catchAll(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("API_USER"))
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Đây là snippet **minh họa một lỗi**, chưa có class/import độc lập. Chain `catchAll` mặc định khớp mọi request và được thử đầu tiên, nên mọi `/api/**` đều bị nó nhận. Chain `api` ở order 2 không còn cơ hội áp dụng `hasRole("API_USER")`.

**Cách sửa:** đặt chain hẹp trước chain rộng; ví dụ `@Order(1)` cho `securityMatcher("/api/**")` và `@Order(2)` cho fallback. Việc Spring nhận biết `/api/**` “cụ thể hơn” **không tự** khiến nó thắng: chỉ thứ tự thử được cấu hình quyết định.

### Hai chain cùng match không cộng quyền

Giả sử chain thứ nhất yêu cầu `ROLE_USER` và chain thứ hai yêu cầu `ROLE_ADMIN` cho cùng `/api/admin/**`. Người dùng **không tự phải có cả hai role**. Chỉ chính sách của chain được chọn có hiệu lực. Nếu nghiệp vụ cần nhiều điều kiện, đặt chúng trong authorization policy của chain được chọn hoặc sử dụng method security/kiểm tra quyền tại service, không dựa vào hai chain chạy nối tiếp.

## 6. Ví dụ đầy đủ: API dùng HTTP Basic, web dùng form login

Mục tiêu của ví dụ chạy được:

- Chain API `@Order(1)` chỉ khớp `/api/**`, dùng HTTP Basic.
- Chain web `@Order(2)` không giới hạn `securityMatcher`, nên là fallback; dùng form login.
- Hai chain cùng dùng `UserDetailsService` trong bộ nhớ với user `alice` (USER) và `admin` (ADMIN).
- `/api/public` và `/public` công khai. `/api/admin` và `/admin` cần ADMIN. Các URL còn lại yêu cầu đã đăng nhập.

Ứng dụng dùng **Java 17+**, Spring Boot 3.3.x, Spring Security 6.x và Spring MVC. Mật khẩu trong ví dụ chỉ dùng để thực hành trên máy local, được băm bằng BCrypt khi khởi tạo. Ứng dụng thật cần nguồn danh tính, secret management và HTTPS thích hợp.

### 6.1. Cấu trúc

~~~text
security-multiple-chains/
├── pom.xml
└── src/main/java/com/example/multichain/
    ├── MultipleChainsApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>security-multiple-chains</artifactId>
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
~~~

**`src/main/java/com/example/multichain/MultipleChainsApplication.java`**

~~~java
package com.example.multichain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MultipleChainsApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultipleChainsApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/multichain/SecurityConfig.java`**

~~~java
package com.example.multichain;

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

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            // Không đặt securityMatcher: fallback cho các URL còn lại.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/login").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**`src/main/java/com/example/multichain/DemoController.java`**

~~~java
package com.example.multichain;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String apiPublic() {
        return "api public";
    }

    @GetMapping("/api/me")
    public String apiMe(Authentication authentication) {
        return "api hello " + authentication.getName();
    }

    @GetMapping("/api/admin")
    public String apiAdmin() {
        return "api admin";
    }

    @GetMapping("/public")
    public String webPublic() {
        return "web public";
    }

    @GetMapping("/me")
    public String webMe(Authentication authentication) {
        return "web hello " + authentication.getName();
    }

    @GetMapping("/admin")
    public String webAdmin() {
        return "web admin";
    }
}
~~~

### 6.2. Giải thích cấu hình

- Hai bean `SecurityFilterChain` được đăng ký khi startup. Boot thường **không tạo thêm default HTTP security chain** khi ứng dụng đã cung cấp chain riêng; bạn cần tự bao phủ URL cần bảo vệ.
- Chain API có matcher `/api/**` và order 1. HTTP Basic filter xử lý credentials phù hợp cho request API; rule `hasRole("ADMIN")` yêu cầu authority `ROLE_ADMIN`.
- Chain web order 2 được thử khi API không khớp. Nó kích hoạt form login và có thể tạo trang login mặc định `/login`. Không bật Basic trong chain web.
- Hai chain dùng chung `UserDetailsService`. Cùng user store **không có nghĩa** cơ chế đăng nhập/entry point trong hai chain giống nhau.
- `permitAll` cho `/api/public` hoặc `/public` vẫn cho request đi qua chain đã chọn, nhưng bỏ yêu cầu đăng nhập ở authorization rule tương ứng.
- Ví dụ **giữ cấu hình CSRF mặc định**. Các endpoint chỉ minh họa HTTP GET. Với request thay đổi trạng thái, đánh giá CSRF theo cách client gửi credentials thay vì tắt CSRF chung chỉ vì đường dẫn là API.

### 6.3. Chạy và kiểm tra bằng curl

Tại thư mục có `pom.xml`, dùng Maven và JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Khi tải dependency lần đầu, Maven cần mạng. Mặc định server chạy `http://localhost:8080`. Trong Windows PowerShell có thể dùng `curl.exe` nếu `curl` bị ánh xạ thành lệnh khác.

Các dòng bắt đầu `#` dưới đây là **kết quả dự kiến** khi chạy đúng project demo; không phải kết quả đã đo trực tiếp tại môi trường hiện tại.

~~~bash
curl -s http://localhost:8080/api/public
# api public

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/api/me
# 401

curl -s -u alice:demo-pass http://localhost:8080/api/me
# api hello alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo-pass http://localhost:8080/api/admin
# 403

curl -s -u admin:demo-pass http://localhost:8080/api/admin
# api admin

curl -s http://localhost:8080/public
# web public

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/me
# 302

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/login
# 200

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo-pass http://localhost:8080/me
# 302
~~~

Diễn giải:

| Request | Chain | Kết quả và nguyên nhân |
| --- | --- | --- |
| `/api/public` chưa đăng nhập | API | 200, `permitAll` |
| `/api/me` chưa đăng nhập | API | 401, HTTP Basic entry point |
| `/api/me` với alice Basic | API | 200, `api hello alice` |
| `/api/admin` với alice Basic | API | 403, thiếu role ADMIN |
| `/api/admin` với admin Basic | API | 200, `api admin` |
| `/public` chưa đăng nhập | Web | 200, `permitAll` |
| `/me` chưa đăng nhập | Web | 302, chuyển đến form login |
| `/login` chưa đăng nhập | Web | 200, trang login mặc định |
| `/me` có Basic header nhưng chưa có web session | Web | 302, vì chain web không bật HTTP Basic |

Đây là điểm đáng quan sát: **Basic header không làm fallback web chain tự kích hoạt BasicAuthenticationFilter**. Để truy cập `/me` qua form login thật, client phải hoàn tất login POST phù hợp, gửi CSRF token và giữ cookie/session. Trình duyệt giúp quan sát luồng này thuận tiện hơn.

Khi `/api/me` bị 401, API chain đã được chọn và từ chối; **không có fallback sang form login chain**. Khi `/api/admin` bị 403 vì role, cũng không có lần thử thứ hai ở chain web.

## 7. Nếu không có chain dự phòng?

Ví dụ ứng dụng chỉ có:

~~~java
@Bean
SecurityFilterChain apiOnly(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Snippet trên không phải file Java độc lập; cần đặt trong class cấu hình và import phù hợp. Nó chỉ bao phủ `/api/**`. Nếu `GET /admin` **không khớp chain nào**, `FilterChainProxy` không chạy một Spring Security filter chain cho request đó; request có thể tiếp tục đến MVC. Nếu controller `/admin` không có lớp bảo vệ khác, đây là lỗ hổng bảo mật.

**Đừng kỳ vọng Boot tự bổ sung chain mặc định** sau khi bạn đã cung cấp bean `SecurityFilterChain`. Trong tình huống Spring Boot Servlet thông thường, auto-configuration dành cho HTTP chain mặc định lùi lại khi ứng dụng có chain riêng. Hãy chủ động thêm một fallback chain bảo vệ tất cả URL còn lại khi phù hợp.

Một phương án nghiêm ngặt là fallback **từ chối mặc định**:

~~~java
@Bean
@Order(99)
SecurityFilterChain denyUnlisted(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

Đây cũng là snippet độc lập về ý tưởng, **không** đặt cạnh web fallback trong ví dụ hoàn chỉnh nếu chưa thiết kế lại thứ tự. Nó từ chối tất cả request không vào chain trước, kể cả trang login hay asset nếu không được cho phép ở chain trước. Ứng dụng web có thể cần fallback `authenticated()` cộng các rule public cụ thể; lựa chọn theo yêu cầu và phải kiểm tra cả login, error, static files, Actuator.

### permitAll khác với không có chain match

`requestMatchers("/public").permitAll()` **vẫn** để Spring Security xử lý request trong chain đã chọn, nên các filter/headers phù hợp còn tác dụng. Nếu request không khớp bất kỳ `SecurityFilterChain` nào, hoặc bị loại khỏi Spring Security qua `web.ignoring()`, hành vi khác đáng kể. Đối với URL public thông thường, `permitAll` thường tốt hơn việc bỏ qua toàn bộ Spring Security.

## 8. Khi matcher chồng lấp: đặt chain cụ thể trước

Tình huống:

~~~text
Chain A: @Order(1), securityMatcher("/api/**")
Chain B: @Order(2), securityMatcher("/api/admin/**")
~~~

`GET /api/admin/users` khớp cả hai, nhưng **A thắng** vì được xét trước. Nếu muốn API admin dùng filter riêng, đảo ưu tiên:

~~~text
Chain Admin:    @Order(1), securityMatcher("/api/admin/**")
Chain API:      @Order(2), securityMatcher("/api/**")
Chain Fallback: @Order(3), matcher mọi URL
~~~

Spring Security **không** tự hiểu matcher cụ thể hơn có ưu tiên cao hơn. `@Order` thể hiện quyết định thiết kế của lập trình viên.

Một URL `/api/orders` không khớp Admin chain sẽ được thử tiếp ở API chain và chọn API. Rule `anyRequest` bên trong Admin chain **không** được đánh giá nếu matcher cấp Admin chain không khớp.

### Không dùng nhiều chain để kết hợp quyền

Nếu yêu cầu cả `ROLE_USER` và `ROLE_ADMIN`, đừng tạo hai chain cùng match URL và kỳ vọng cả hai rule áp dụng. Hãy đặt logic quyền phù hợp **trong chain được chọn**, hoặc thêm method security ở service. Tương tự, bảo vệ ownership của từng bản ghi (IDOR/BOLA) thường cần kiểm tra tại tầng nghiệp vụ; `@Order` không giải quyết quyền trên dữ liệu.

### Chain matching phức tạp

Có thể dùng `RequestMatcher` tùy biến để xét method, host hoặc header. Khi đó cần xét reverse proxy, dữ liệu client tự gửi và cách matcher vận hành. Không dùng header có thể bị giả mạo như bằng chứng role. Với servlet path/context path tùy chỉnh, phải xác định phạm vi URL mà matcher thật sự nhận được.

## 9. Các cấu hình mang tính riêng từng chain

**Cơ chế authentication:** Chain API có thể bật HTTP Basic, OAuth2 Resource Server bearer token hoặc bộ lọc tùy chỉnh; web chain bật form login. Khi request khớp một chain, chỉ những authentication filter của chain đó hoạt động. `AuthenticationManager` hoặc `AuthenticationProvider` có thể chia sẻ hoặc tách theo cấu hình cụ thể; `@Order` không tự tách danh tính.

**CSRF:** Mỗi chain có cấu hình CSRF riêng. Trên trình duyệt sử dụng cookie/session, cần chú ý các request thay đổi trạng thái. API chỉ dùng token do client chủ động đặt có mô hình CSRF khác, nhưng **không nên tắt CSRF chỉ vì URL bắt đầu bằng /api**; HTTP Basic có thể được trình duyệt tự gửi credentials đã nhớ.

**CORS:** Browser preflight `OPTIONS` có thể không mang credentials. CORS nên được xử lý trước khi authorization từ chối preflight; khi dùng Spring Security, tích hợp cấu hình CORS phù hợp vào chain cần nó. CORS không phải cơ chế authentication và không ngăn client ngoài trình duyệt gọi API.

**Session/security context:** API token có thể dùng `SessionCreationPolicy.STATELESS`; web form login dùng session. Việc tách thành nhiều chain **không tự tạo** hai hệ thống identity hoặc cookie độc lập. Cần xem việc lưu/đọc security context, session cookie, authentication repository theo cấu hình thật.

**Login/logout URL:** Nếu một chain chỉ khớp `/secured/**` nhưng form login vẫn xử lý `/login`, login URL có thể nằm **ngoài phạm vi** của chain có form-login filter. Hãy đảm bảo login page và login processing URL khớp chain cần thiết, được cho phép khi phù hợp, và không bị chain trước chiếm.

**Security headers:** Endpoint đi qua chain sẽ hưởng các filter/headers của chain đó theo cấu hình. URL không khớp chain nào sẽ không nhận security headers do Spring Security chain cung cấp. Đây là lý do cần rà soát fallback và tránh `web.ignoring()` quá rộng.

**Actuator:** Khi ứng dụng tự cung cấp chain, cần chủ động xem các management endpoint đã exposed như health, metrics, info và chính sách truy cập. Không mặc định sẽ có một auto-config fallback cho mọi URL quản trị.

**Method security:** `@EnableMethodSecurity` và `@PreAuthorize` kiểm tra quyền tại method/service; đây là cơ chế bổ sung. Nó **không** thay đổi chain selection của `FilterChainProxy`. Khi request vượt qua HTTP authorization, vẫn cần kiểm tra owner/tenant/đối tượng nghiệp vụ nếu chính sách yêu cầu.

## 10. Debug và xác minh chain thực tế

### Bật log Spring Security trong development

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Có thể dùng `TRACE` cho phân tích rất chi tiết, nhưng không bật log nhạy cảm trên production. Khi đọc log, tìm request path/method, security chain được chọn, authentication filter, entry point, access denied handler và authorization decision. Đừng phụ thuộc một dòng log cố định vì format thay đổi giữa các phiên bản.

### Phân biệt điều kiện startup và request-time

Muốn biết Boot có tạo chain mặc định hay không, bật debug Boot:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

**Condition Evaluation Report** giải thích vì sao auto-configuration được áp dụng hoặc bị bỏ qua. Nhưng nó không đủ để chứng minh `GET /api/orders` đã đi vào chain nào. Muốn biết request đi vào chain nào, cần matcher, order và log/test xử lý HTTP.

Thông báo “generated security password” nếu có chỉ liên quan tới nhánh **user mặc định**, không chứng minh HTTP chain mặc định đang chạy. Bean `SecurityFilterChain` tùy chỉnh có thể tồn tại cùng user mặc định nếu ứng dụng chưa cung cấp nguồn danh tính riêng.

### Bản đồ kiểm thử cần có

Khi thay nhiều chain, kiểm tra theo thứ tự:

1. URL chắc chắn chỉ khớp **chain cụ thể**.
2. URL nằm trong **vùng giao** của hai matcher.
3. URL chỉ khớp chain tổng quát hơn.
4. URL **ngoài các matcher cụ thể** phải được fallback bảo vệ.
5. Login page/processing URL, `/error`, static asset và Actuator endpoint cần thiết.
6. Mỗi URL với anonymous, user thường, admin, credentials hợp lệ/không hợp lệ.
7. Nếu dùng POST/PUT/DELETE, kiểm tra CSRF và CORS/preflight theo đúng loại client.

Quan sát phản hồi: **401** thường thiếu authentication; **403** thường do access denied hoặc CSRF; **302** có thể là redirect đến login. Nhưng status do entry point/handler cấu hình quyết định, vì vậy **không suy ra chain chỉ từ status code**. Dựa vào matching và log để xác nhận.

Một chuỗi chẩn đoán hợp lý:

~~~text
HTTP request thực tế
 -> securityMatcher + @Order
 -> chain đầu tiên khớp
 -> filter authentication (có đúng mechanism không?)
 -> rule authorizeHttpRequests (có khớp và đủ quyền không?)
 -> DispatcherServlet / Controller / Service
 -> response / exception handling
~~~

## 11. Lỗi phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`@Order(1)` bảo vệ mọi URL trước chain khác.” | Chỉ được chọn khi **matcher cấp chain khớp** |
| “Request chạy qua tất cả `SecurityFilterChain`.” | `FilterChainProxy` chọn **chain đầu tiên khớp** |
| “Dùng `requestMatchers("/api/**")` là đã giới hạn chain ở API.” | Đó là **authorization rule**; `securityMatcher("/api/**")` mới giới hạn chain |
| “`anyRequest().authenticated()` trong chain API bảo vệ cả website.” | Chỉ áp dụng request **đã thuộc chain API** |
| “Chain hẹp tự thắng chain rộng.” | Thứ tự lựa chọn do `@Order` quyết định |
| “Nếu không có chain match, Boot sẽ tạo fallback.” | Không nên trông chờ; custom chain thường làm default HTTP chain của Boot lùi lại |
| “@Order làm BasicAuthenticationFilter chạy sớm hơn.” | Thứ tự filter **bên trong chain** là cơ chế khác |
| “`permitAll` tắt Spring Security cho endpoint.” | Vẫn đi qua chain và security filter đã match |
| “Cùng UserDetailsService thì cả hai chain đều tự hỗ trợ Basic.” | Mỗi chain chỉ có cơ chế authentication đã được bật |
| “Có @PreAuthorize nên không cần phân biệt chain HTTP.” | Method security và HTTP security có trách nhiệm khác nhau |

**Tình huống cần sửa:** Một app cấu hình `@Order(1)` cho chain không có `securityMatcher` với `anyRequest().permitAll()`, sau đó `@Order(2)` cho `securityMatcher("/admin/**")` với `hasRole("ADMIN")`. `/admin/users` khớp chain đầu tiên và **không nhận** rule ADMIN của chain thứ hai. Sửa bằng cách đặt chain admin lên trước, thiết kế lại fallback và chỉ mở public các URL thực sự cần public. Chỉ sửa `hasRole` ở chain thứ hai mà không xử lý shadowing sẽ vô ích.

## 12. Câu hỏi tự kiểm tra

**1.** Có chain `@Order(1)` khớp `/api/**` và chain `@Order(2)` khớp `/admin/**`. `GET /admin/jobs` thuộc chain nào?

**Đáp:** Chain `/admin/**`, vì chain thứ nhất không khớp dù ưu tiên cao.

**2.** `GET /api/me` bị 401 trong chain API. Có tự chuyển sang web fallback không?

**Đáp:** Không. Chain được chọn theo matcher; authentication/authorization thất bại không khiến Spring Security thử chain tiếp theo.

**3.** Tại sao `anyRequest().authenticated()` trong `securityMatcher("/api/**")` không bảo vệ `/reports`?

**Đáp:** `/reports` không được chọn vào chain API. `anyRequest` chỉ bao phủ request đã nằm trong phạm vi chain đó.

**4.** Hai chain match `/api/admin/**`. Làm thế nào để chain admin dùng filter riêng được ưu tiên?

**Đáp:** Đặt chain hẹp cho `/api/admin/**` với `@Order` nhỏ hơn chain `/api/**`, kiểm thử vùng chồng lấp và giữ fallback phù hợp.

**5.** `@Order` có đổi vị trí `AuthorizationFilter` so với `BasicAuthenticationFilter` không?

**Đáp:** Không. Nó xếp thứ tự các bean chain; thứ tự filter con được Spring Security/`HttpSecurity` quyết định.

**6.** Vì sao Basic header gửi tới `/me` vẫn redirect 302 trong demo?

**Đáp:** `/me` thuộc web chain chỉ có form login; HTTP Basic chỉ bật trong API chain.

**7.** Nếu app chỉ khai báo một chain khớp `/api/**`, `/admin` có mặc định bị chặn không?

**Đáp:** Không thể kết luận như vậy. Nếu không có chain khác khớp, `/admin` có thể đi tiếp mà không qua Spring Security filter chain nào. Cần fallback hoặc biện pháp bảo vệ được thiết kế và kiểm thử rõ ràng.

**Ghi nhớ:** **`@Order` chọn thứ tự xét chain; `securityMatcher` quyết định chain có khớp request; `requestMatchers` và `anyRequest` quyết định quyền bên trong chain đã chọn. Mỗi request dùng chain khớp đầu tiên.**