# FilterChainProxy chọn SecurityFilterChain

Một ứng dụng Spring Boot có thể vừa có API dành cho máy (`/api/**`), giao diện quản trị (`/admin/**`) và trang web sử dụng form login (`/web/**`). Ba nhóm request này có thể cần **cơ chế xác thực, lưu phiên, xử lý lỗi và chính sách phân quyền khác nhau**. Vậy khi một HTTP request đi vào Servlet container, Spring Security biết phải chạy những security filter nào?

Đây là nhiệm vụ của **`FilterChainProxy`**: nó lần lượt xem các `SecurityFilterChain` đã cấu hình theo thứ tự ưu tiên, **chọn chain khớp đầu tiên**, rồi thực thi **chỉ các security filter trong chain ấy**. Nó **không cộng dồn** filter của tất cả chain khớp. Nếu không chain nào khớp, request đi tiếp mà **không được Spring Security bảo vệ** bằng các filter của những chain đó.

Bài học giải thích đầy đủ đường đi Servlet Filter → `DelegatingFilterProxy` → `FilterChainProxy` → `SecurityFilterChain` → DispatcherServlet, cách `@Order` và `securityMatcher` quyết định chain, khác biệt với `requestMatchers` trong phân quyền, những lỗ hổng khi matcher sai/thiếu fallback, và cách kiểm thử chính hành vi chọn chain trên ứng dụng Java 17+.

Đây là kiến thức về **Spring Security Servlet/Spring MVC**. Với Spring WebFlux, hệ thống dùng `SecurityWebFilterChain`/`WebFilterChainProxy` và reactor-specific context; không copy các class `jakarta.servlet.Filter` sang WebFlux.

## 1. Đầu tiên phải hiểu hai loại filter chain khác nhau

Servlet container (Tomcat/Jetty/Undertow...) quản lý một **Servlet `FilterChain`** cho request. Spring Security không thay thế Servlet container; nó tham gia như một filter trong chain của container.

~~~text
Browser / API client
        |
        v
Servlet Container (Tomcat)
        |
        v
Filter A của container, nếu có
        |
        v
DelegatingFilterProxy ("springSecurityFilterChain")
        |
        v
Spring Bean: FilterChainProxy
        |
        +-- Request matching --> SecurityFilterChain thứ nhất khớp
        |                               |
        |                               +--> Spring Security Filter 1
        |                               +--> Spring Security Filter 2
        |                               +--> ...
        |                               +--> Spring Security Filter N
        |
        v
Các Servlet Filters tiếp theo (nếu có)
        |
        v
DispatcherServlet -> Controller -> Service
~~~

Phân biệt ba kiểu dễ nhầm:

| Kiểu | Thuộc hệ nào | Nhiệm vụ |
| --- | --- | --- |
| `jakarta.servlet.FilterChain` | Servlet API | Điều phối các filter/container và Servlet cho request |
| `org.springframework.security.web.FilterChainProxy` | Spring Security | Một Servlet Filter đặc biệt, lựa chọn security chain và điều phối các security filters |
| `org.springframework.security.web.SecurityFilterChain` | Spring Security | Mô tả **`RequestMatcher`** và danh sách security filters áp dụng khi request khớp |

**`SecurityFilterChain` không phải Servlet `FilterChain` trực tiếp.** Nó là cấu hình mà `FilterChainProxy` sử dụng. Khi bạn khai báo `@Bean SecurityFilterChain`, Spring Security lấy các bean đó và xây cấu trúc thực thi tương ứng.

Không cần tự tạo `FilterChainProxy` hoặc tự đăng ký mọi security filter với Servlet container trong ứng dụng Spring Boot thông thường. Framework và Boot thực hiện phần kết nối này.

### Servlet Filter có quyền làm gì?

Một `Filter` có thể:

1. Đọc/sửa request hoặc response phù hợp.
2. Gọi `chain.doFilter(request,response)` để request đi tiếp.
3. **Không gọi** `chain.doFilter` khi quyết định chặn hoặc hoàn tất response (ví dụ trả 401/403).
4. Thực hiện công việc sau khi downstream xử lý, nếu response/lifecycle cho phép.

Vì vậy một `SecurityFilterChain` có thể dừng request **trước controller**. Khi thấy API trả 401, không được mặc định rằng controller đã chạy và ném lỗi.

## 2. DelegatingFilterProxy: cầu nối Servlet container với Spring Bean

Servlet container biết về chuẩn `jakarta.servlet.Filter`, còn Spring quản lý bean trong `ApplicationContext`. `DelegatingFilterProxy` của Spring Framework nối hai thế giới:

~~~text
Tomcat
  |
  +--> DelegatingFilterProxy
              |
              +--> Tìm Spring Bean theo tên
                           |
                           v
                 "springSecurityFilterChain"
                           |
                           v
                      FilterChainProxy
~~~

Trong hệ Spring Security Servlet, bean được delegate thường mang tên **`springSecurityFilterChain`**. Tên này dễ làm nhầm với interface `SecurityFilterChain`: ở đây nó là **tên của Spring Bean đại diện cho proxy filter**, không phải tên của một chain duy nhất.

Mã giả:

~~~java
// Pseudocode: không dùng để thay thế DelegatingFilterProxy thật.
void doFilter(ServletRequest req, ServletResponse res, FilterChain chain) {
    Filter springManaged = findBean("springSecurityFilterChain");
    springManaged.doFilter(req, res, chain);
}
~~~

Bạn thường chỉ định nghĩa những `SecurityFilterChain @Bean` ở lớp cấu hình. `DelegatingFilterProxy` được đăng ký trong Servlet container qua tích hợp Boot/Spring Security. Không nên tạo một bản proxy thứ hai tùy tiện, vì request có thể bị chạy bộ lọc bảo mật trùng.

**Vòng đời:** Servlet container quản lý lifecycle của proxy/filter đã đăng ký; các Spring Security filter bên trong do Spring quản lý. `FilterChainProxy` không gọi `init/destroy` chuẩn của Servlet cho từng filter do Spring quản lý theo cách bạn mong đợi nếu tự gắn thủ công. Hãy dùng bean lifecycle phù hợp khi tạo custom filter.

## 3. FilterChainProxy thật sự chọn chain như thế nào?

Mỗi `SecurityFilterChain` gồm hai phần thiết yếu:

- **Matcher:** `matches(HttpServletRequest)` quyết định request hiện tại có thuộc chain này không.
- **Filters:** danh sách `jakarta.servlet.Filter` theo thứ tự, chỉ được thực thi khi chain được chọn.

Một mô hình cực đơn giản:

~~~java
// Pseudocode mô tả FIRST MATCH; framework có firewall, wrappers,
// exception handling và nhiều chi tiết khác.
for (SecurityFilterChain candidate : orderedChains) {
    if (candidate.matches(request)) {
        runOnly(candidate.getFilters(), request, response, servletChain);
        return;
    }
}
servletChain.doFilter(request, response); // không có security chain
~~~

Hãy đọc kỹ hai từ: **FIRST MATCH**. Không phải “tìm chain cụ thể nhất bằng cách tự chấm điểm” và cũng không phải “gộp tất cả chain cùng match”.

Giả sử có cấu hình:

| Thứ tự | Chain | Matcher | Loại xác thực |
| --- | --- | --- | --- |
| 1 | API | `/api/**` | HTTP Basic hoặc bearer token |
| 2 | Admin | `/admin/**` | Chính sách quản trị |
| 3 | Web fallback | Mọi request còn lại | Form login |

Đường đi:

~~~text
Request GET /api/orders
    |
    +--> Chain #1 /api/**: MATCH!
    |        |
    |        +--> Chỉ API security filters
    |
    +--> KHÔNG xét tiếp #2 hay #3

Request GET /admin/panel
    |
    +--> Chain #1 /api/**: no
    +--> Chain #2 /admin/**: MATCH!
    |        |
    |        +--> Chỉ Admin security filters
    |
    +--> KHÔNG xét #3

Request GET /web/profile
    |
    +--> Chain #1 /api/**: no
    +--> Chain #2 /admin/**: no
    +--> Chain #3 catch-all: MATCH!
             |
             +--> Chỉ Web security filters
~~~

**Nếu API chain trả 401 hoặc 403, `FilterChainProxy` không chuyển request sang Web fallback để thử đăng nhập kiểu khác.** Một chain đã match là xong giai đoạn chọn chain. Logic phân quyền hoặc thất bại xác thực diễn ra **bên trong chain được chọn**, không khiến bộ chọn thử chain tiếp theo.

### Thứ tự không phải độ dài đường dẫn

Cấu hình:

~~~text
Order 1: /**             (catch-all)
Order 2: /api/**         (specific)
~~~

Sẽ khiến `/**` khớp ngay trước khi `/api/**` có cơ hội. Dù API pattern có vẻ cụ thể hơn, Spring Security **không tự đảo lại thứ tự theo độ cụ thể** khi chạy `FilterChainProxy`. Bạn phải sắp xếp rõ: **nhóm đặc thù trước, fallback sau**.

Có thể có matcher kiểm tra HTTP method, header, dispatcher type hoặc logic phức tạp hơn URL; nguyên tắc first-match vẫn đúng. Nếu hai matcher chồng lấn, thứ tự `@Order` là một phần của chính sách bảo mật.

## 4. Vai trò của @Order với nhiều SecurityFilterChain bean

Trong cấu hình Java hiện đại, bạn có thể khai báo nhiều bean:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain admin(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .authorizeHttpRequests(a -> a.anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(3)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đây là **fragment** trong `@Configuration`, cần imports, users, password encoder và ứng dụng. Phần 7 có project đầy đủ.

Quy tắc:

- Số `@Order` **nhỏ hơn được xét trước**: 1 trước 2.
- Bean **không có `@Order`** thường có độ ưu tiên thấp hơn bean đã gắn `@Order(1)`; không nên dựa vào thứ tự khai báo method trong file.
- Tránh hai chain có cùng priority nếu bạn cần thứ tự tuyệt đối; thứ tự có thể không như giả định.
- Chain fallback không gọi `securityMatcher` nên giữ matcher mặc định **khớp mọi request**.
- `@Order` là thứ tự **giữa các SecurityFilterChain**, khác với thứ tự **các Security Filters bên trong một chain**.

Đừng nhầm thứ tự `@Order` trên chain với annotation `@Order` của một `@Component Filter` được container đăng ký riêng: chúng chi phối hai tầng khác nhau.

## 5. securityMatcher và requestMatchers: sự khác biệt quan trọng nhất

Hai lời gọi có tên gần giống nhưng tác động ở tầng khác:

~~~java
http.securityMatcher("/api/**");
~~~

Nghĩa là: **chain này chỉ dành cho request khớp `/api/**`**. Đây là quyết định để `FilterChainProxy` có dùng chain đó hay không.

~~~java
http.authorizeHttpRequests(a -> a
    .requestMatchers("/api/public").permitAll()
    .anyRequest().authenticated()
);
~~~

Nghĩa là: **một khi chain đã được chọn, rule phân quyền nào áp dụng cho request?** Đây không phải bộ chọn chain bên ngoài.

Kết hợp:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/public").permitAll()
        .anyRequest().authenticated()
    );
~~~

Hành vi:

| Request | Có vào API chain? | Rule bên trong chain |
| --- | --- | --- |
| `GET /api/public` | Có | `permitAll()` |
| `GET /api/orders` | Có | `authenticated()` |
| `GET /admin/panel` | Không | Rule API **không được xét** |
| `GET /web/private` | Không | Rule API **không được xét** |

Trong ví dụ này, `anyRequest()` có nghĩa “mọi request **đang được xử lý bởi chain hiện tại**”, chứ không có nghĩa “mọi đường dẫn toàn ứng dụng”. Nếu chain có `securityMatcher("/api/**")`, thì `.anyRequest().authenticated()` **không che phủ** `/admin/**` hoặc `/web/**`.

### Ví dụ cấu hình tưởng đúng nhưng hở

~~~java
// CÓ LỖ HỞ nếu đây là SecurityFilterChain DUY NHẤT:
return http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .anyRequest().authenticated()
    )
    .build();
~~~

Các endpoint ngoài `/api/**` **không có security chain nào khớp**, do đó không được các Spring Security filters bảo vệ; controller của chúng có thể nhận request trực tiếp. Khuyến nghị: có chain fallback bảo vệ mọi request còn lại, hoặc bảo đảm việc không bảo vệ là quyết định rõ ràng đã được kiểm thử.

**`permitAll` và “không có chain match” hoàn toàn khác nhau**. `permitAll` vẫn ở trong pipeline Spring Security, còn không match có thể bỏ qua tất cả những bảo vệ đó.

### Tại sao một rule permitAll không làm chain đổi chỗ?

Nếu request `/api/public` khớp API chain và rule `permitAll`, Spring Security **không chuyển request sang web chain** chỉ vì endpoint công khai. Chain selection đã xong; permitAll chỉ quyết định quyền truy cập bên trong API chain ấy.

Ngược lại, nếu web chain có `requestMatchers("/api/public").permitAll()` nhưng API chain đứng trước và match, rule permitAll của web chain **không được chạy**. Phải đặt rule ở **chain thật sự được chọn**.

## 6. HttpFirewall: trước khi so match cần có đường dẫn đáng tin

`FilterChainProxy` còn tích hợp **`HttpFirewall`** để kiểm tra và bọc request trước khi các matcher sử dụng đường dẫn. Implementation thường dùng là `StrictHttpFirewall`, với chính sách chặn một số URL bất thường và cách biểu diễn path có thể gây nhầm lẫn.

Vấn đề ví dụ:

~~~text
/api/users
/api//users
/api/../admin/panel
/api/users;something=value
/api/%2e%2e/admin/panel
~~~

Những chuỗi trên **không đương nhiên được server xử lý giống nhau**. Servlet container, reverse proxy, URL decoder, firewall và framework router có thể diễn giải path khác nhau. Nếu tầng chọn chain thấy một đường dẫn, nhưng tầng controller thấy đường dẫn khác, có thể xảy ra **path-based security bypass**.

`HttpFirewall` cố giúp chuẩn hóa/kiểm soát những đầu vào rủi ro trước khi so khớp. Không nên mặc định **tắt StrictHttpFirewall hoặc bật cho phép encoded slash/semicolon** chỉ để sửa một endpoint đang lỗi 400; cần phân tích path handling từ reverse proxy đến Spring MVC và xác định threat model.

**Điều quan trọng:** filter chain selection có thể dựa vào các thuộc tính của `HttpServletRequest`, không chỉ raw URI string. Với matcher tùy biến, hãy hiểu `contextPath`, `servletPath`, `pathInfo`, encoding, query string và matcher implementation của đúng phiên bản Spring Security bạn dùng.

### PathPatternRequestMatcher và các tài liệu cũ

Ở Spring Security hiện đại, việc dùng `securityMatcher("/api/**")` hoặc `requestMatchers("/api/**")` có cơ chế xây matcher theo cấu hình framework. Trong Spring Security 7, không nên copy máy móc mọi hướng dẫn cũ dựa trên `antMatcher(...)` hoặc `antMatchers(...)` từ API thời `WebSecurityConfigurerAdapter`. Hãy kiểm tra tài liệu version đang chạy.

Khi matcher phải giới hạn theo method, host, dispatcher type hoặc predicate riêng, có thể dùng một `RequestMatcher` phù hợp, nhưng cần kiểm thử cả các trường hợp URL tương đương và reverse proxy đã chỉnh path. Một matcher quá rộng hoặc không đúng ngữ nghĩa có thể chọn sai security chain.

## 7. Project thực hành hoàn chỉnh: ba chain, hai kiểu login, một fallback

Ví dụ dùng:

- Java **17+**.
- Spring Boot **4.1.2**, Spring Security do Boot BOM quản lý.
- Spring MVC/Servlet trên Tomcat embedded.
- HTTP Basic cho `/api/**` và `/admin/**`, đều theo stateless session policy của Spring Security.
- Form login mặc định cho các request còn lại.
- User demo có role `USER`; admin demo có role `ADMIN`.
- `@Order(1)`, `@Order(2)`, `@Order(3)` cùng `securityMatcher` để chứng minh first-match.
- `MockMvc` và `spring-security-test` để đi qua filter chain thật.

Mục tiêu là thấy được **request vào đâu, chain nào được chọn, kết quả 200/302/401/403 do cấu hình nào tạo ra**. Tất cả credentials ở đây là giả cho máy local. Không chạy API dùng HTTP Basic không mã hóa trên Internet.

### 7.1. Cấu trúc dự án

~~~text
filter-chain-proxy-lab/
  pom.xml
  src/main/java/com/example/filterlab/
    FilterChainLabApplication.java
    SecurityConfiguration.java
    DemoController.java
  src/test/java/com/example/filterlab/
    FilterChainSelectionTest.java
~~~

### 7.2. pom.xml

Tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>filter-chain-proxy-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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
~~~

Trong Boot 4, starter Servlet MVC là `spring-boot-starter-webmvc`, không cần thêm `spring-boot-starter-webflux`. Test dependency được quản lý bởi Boot parent. Trong ứng dụng Boot thật, không chỉ định version Spring Security riêng trừ khi có chủ đích và đã kiểm tra tương thích.

### 7.3. Main class

Tạo `src/main/java/com/example/filterlab/FilterChainLabApplication.java`:

~~~java
package com.example.filterlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterChainLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(FilterChainLabApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfiguration.java — trái tim bài học

Tạo `src/main/java/com/example/filterlab/SecurityConfiguration.java`:

~~~java
package com.example.filterlab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("user")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain adminSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/admin/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().hasRole("ADMIN")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            // KHÔNG securityMatcher: chain fallback cho request còn lại.
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .build();
    }
}
~~~

**Cách đọc code:**

1. `@Order(1)` khiến API chain được thử trước. Matcher `/api/**` quyết định phạm vi **chain**, không phải là rule phân quyền.
2. API chain có `requestMatchers("/api/public").permitAll()` nhưng các đường `/api/**` khác cần login.
3. `@Order(2)` là chain dành riêng `/admin/**`. Mọi request đã vào chain này cần `ROLE_ADMIN`; không có `formLogin()` ở chain ấy.
4. `@Order(3)` không đặt matcher riêng, trở thành **fallback** cho `/web/**`, `/public` và `/login`.
5. `InMemoryUserDetailsManager` dùng dữ liệu demo; passwords được băm bcrypt, không đưa plaintext vào `UserDetails`.
6. `SessionCreationPolicy.STATELESS` ở API/Admin nghĩa hai chain này không dựa vào `HttpSession` để khôi phục `SecurityContext`; chúng chứng thực theo request Basic.
7. **Không cấu hình `csrf.disable()` trong ví dụ.** Các endpoint minh họa chỉ có GET. Nếu bạn thêm POST/PUT/DELETE, cần đánh giá CSRF theo việc browser có tự gửi credentials hay không, không đơn giản tắt CSRF vì thấy chữ API.

**Một chi tiết lớn:** `@Order(3)` trên web fallback không hề biến nó thành “vô hiệu” khi API đã match. Khi một request vào `/api/data`, `FilterChainProxy` dừng xét chain từ API. Nó sẽ không chạy `UsernamePasswordAuthenticationFilter` của form-login chain.

### 7.5. DemoController.java

Tạo `src/main/java/com/example/filterlab/DemoController.java`:

~~~java
package com.example.filterlab;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/public")
    public String publicApi() {
        return "api-public";
    }

    @GetMapping("/api/data")
    public String apiData(Authentication authentication) {
        return "api-data:" + authentication.getName();
    }

    @GetMapping("/admin/panel")
    public String adminPanel(Authentication authentication) {
        return "admin-panel:" + authentication.getName();
    }

    @GetMapping("/public")
    public String publicWeb() {
        return "web-public";
    }

    @GetMapping("/web/private")
    public String privateWeb(Authentication authentication) {
        return "web-private:" + authentication.getName();
    }
}
~~~

Controller không chọn `SecurityFilterChain`; việc ấy xảy ra **trước controller**. Nó chỉ hoạt động với `Authentication` đã được security chain tương ứng chấp nhận. Đừng tự quyết định quyền quản trị bằng `request.getParameter("role")` hoặc truyền `Authentication` tự tạo từ input người dùng.

### 7.6. Kiểm thử bằng MockMvc: đúng chain, đúng kết quả

Tạo `src/test/java/com/example/filterlab/FilterChainSelectionTest.java`:

~~~java
package com.example.filterlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterChainSelectionTest {

    @Autowired
    MockMvc mvc;

    @Test
    void apiPublicIsAllowedByApiChain() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("api-public"));
    }

    @Test
    void apiPrivateNeedsBasicCredentials() throws Exception {
        mvc.perform(get("/api/data"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/data")
                .with(httpBasic("user", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("api-data:user"));
    }

    @Test
    void adminChainRequiresAdminRole() throws Exception {
        mvc.perform(get("/admin/panel")
                .with(httpBasic("user", "demo-password")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin/panel")
                .with(httpBasic("admin", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-panel:admin"));
    }

    @Test
    void webFallbackAllowsPublicAndRedirectsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("web-public"));

        mvc.perform(get("/web/private"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void webFallbackUsesFormLoginAndSession() throws Exception {
        MvcResult login = mvc.perform(
                formLogin().user("user").password("demo-password"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/web/private").session(session))
            .andExpect(status().isOk())
            .andExpect(content().string("web-private:user"));
    }
}
~~~

Đây là các bài test HTTP qua Spring MVC và Spring Security filter chain, không chỉ test controller trực tiếp. Các tình huống quan trọng:

| Test | Request | Chain phải được chọn | Kết quả |
| --- | --- | --- | --- |
| API public | GET `/api/public` không credentials | API | 200, `api-public` |
| API private anonymous | GET `/api/data` | API | 401 (Basic challenge) |
| API private user | GET `/api/data` với Basic user | API | 200, `api-data:user` |
| Admin với USER | GET `/admin/panel` với Basic user | Admin | 403 |
| Admin với ADMIN | GET `/admin/panel` với Basic admin | Admin | 200, `admin-panel:admin` |
| Web public | GET `/public` | Web fallback | 200, `web-public` |
| Web anonymous | GET `/web/private` | Web fallback | 3xx redirect login |
| Web form login | POST `/login`, tiếp GET `/web/private` bằng session | Web fallback | 3xx rồi 200, `web-private:user` |

Vì `formLogin()` của Spring Security Test mô phỏng các tham số và CSRF liên quan, bạn không cần tắt CSRF để làm test login. HTTP Basic requests trong ví dụ là GET, không thay đổi dữ liệu.

**Vì sao đây là bằng chứng chọn chain?** Cùng một user `user` có thể truy cập `/api/data` với HTTP Basic nhưng bị từ chối quyền admin ở `/admin/panel`; còn `/web/private` dùng form login và session. Nếu catch-all chain đứng sai thứ tự, hoặc API chain không match, các hành vi này có thể đổi (đặc biệt 401 thành redirect login).

### 7.7. Build và kiểm tra thủ công

Tại thư mục project:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Khi ứng dụng chạy ở `http://localhost:8080`, mở terminal khác để thử **chỉ với tài khoản giả trong local**:

~~~bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/data
curl -i -u user:demo-password http://localhost:8080/api/data
curl -i -u user:demo-password http://localhost:8080/admin/panel
curl -i -u admin:demo-password http://localhost:8080/admin/panel
curl -i http://localhost:8080/public
curl -i http://localhost:8080/web/private
~~~

Response dự kiến:

~~~text
GET /api/public                 -> 200
GET /api/data (anonymous)       -> 401
GET /api/data (Basic USER)      -> 200
GET /admin/panel (Basic USER)   -> 403
GET /admin/panel (Basic ADMIN)  -> 200
GET /public                     -> 200
GET /web/private (anonymous)    -> 302 redirect tới login
~~~

Đây là kết quả thiết kế của SecurityFilterChain và controller; các status/challenge/redirect có thể bị ảnh hưởng nếu có proxy, custom entry point hoặc filter khác. **Không** sử dụng mật khẩu thật trong lệnh `curl -u` vì shell history hoặc process inspection có thể làm lộ credentials.

Khi mở trang `/web/private` bằng trình duyệt, bạn sẽ đến trang login mặc định. Sau khi đăng nhập bằng `user`/`demo-password`, Spring Security quản lý session cho web fallback theo flow form login.

## 8. First-match khác với “hợp nhất chính sách”

Hãy xem hai chain:

~~~text
Chain A: /api/**    -> HTTP Basic, authenticated()
Chain B: /**        -> formLogin, role ADMIN cho /api/admin/**
~~~

Request `/api/admin/report` khớp A đầu tiên. **Rule role ADMIN của B không được thực thi** vì B chưa bao giờ được chọn cho request ấy. Đây là lỗi cấu hình khá phổ biến: người phát triển nghĩ có thể đặt một nhóm rule chung ở catch-all và rule khác ở chain cụ thể rồi cả hai sẽ được áp dụng.

Quy tắc khắc phục:

- Mọi authorization rule bắt buộc cho `/api/**` phải nằm trong API chain (hoặc trong một lớp bảo vệ độc lập chắc chắn áp dụng, chẳng hạn method security).
- Không dựa vào một chain ở sau để “bồi thêm” CSRF, security headers, session policy hoặc quyền cho chain ở trước.
- Nếu cần áp cùng một chính sách ở nhiều chain, có thể trích xuất một component/cấu hình chung **và áp nó rõ ràng cho từng `HttpSecurity`**.
- Nếu không thật sự cần nhiều chain, ưu tiên **một SecurityFilterChain với `requestMatchers` theo URL** để giảm nguy cơ cấu hình chồng lấn. Tạo nhiều chain khi **bản thân bộ filters hoặc authentication mechanism** cần khác nhau.

### Quy tắc fallback: để request “không khớp” phải là điều cố ý

Một cấu hình nguy hiểm:

~~~java
@Bean
@Order(1)
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Nếu đây là bean chain duy nhất, `/admin/**` và `/web/**` không được Spring Security bảo vệ. Bạn có thể nghĩ Spring Boot sẽ “tự thêm một chain mặc định” đằng sau; nhưng khi bạn cung cấp cấu hình `SecurityFilterChain` của mình, auto-configuration thường **lùi lại**, không bảo đảm tạo thêm một fallback chain khác.

Một fallback an toàn thông thường:

~~~java
@Bean
@Order(99)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        // Không đặt securityMatcher -> match mọi request còn lại.
        .authorizeHttpRequests(a -> a.anyRequest().denyAll())
        .build();
}
~~~

Mảnh code này minh họa **fallback deny-all**, không phải thay thế mặc định cho web form login. Nó hữu ích khi ứng dụng chỉ nên phơi bày một số route nhất định; các request ngoài danh sách hợp lệ bị từ chối thay vì vô tình bỏ qua mọi Spring Security filter. Tùy thiết kế bạn cũng có thể dùng fallback `authenticated()` và formLogin như phần 7.

**Kiểm thử negative paths** rất quan trọng: `/health`, `/error`, `/admin`, `/api` (không có dấu `/` cuối), `/api/`, path trùng/encoded, và URL do reverse proxy rewrite. Đừng chỉ thử mỗi `/api/users` rồi kết luận `/api/**` bao phủ tất cả biến thể.

## 9. Các endpoint do filter sinh ra cũng phải nằm trong chain tương ứng

Một chain không chỉ chọn controller nào được bảo vệ; nó còn quyết định **những authentication filters nào được gọi**. Một số endpoint được xử lý bởi filter chứ không cần controller riêng:

- `POST /login` khi dùng form login mặc định.
- `GET /login` có thể được filter tạo login page nếu không có custom page.
- Endpoint logout tùy `LogoutFilter`.
- Endpoint OAuth2 authorization/callback hoặc SAML2 login tùy cơ chế và cấu hình.

Vấn đề xảy ra khi bạn thu hẹp web chain:

~~~java
http.securityMatcher("/web/**")
    .formLogin(Customizer.withDefaults());
~~~

Nếu login page và POST processing vẫn ở `/login` **ngoài `/web/**`**, request `/login` không vào chain đó; filter sinh/nhận login sẽ không được gọi. Người dùng có thể gặp **404** dù `formLogin` đã bật, hoặc một chain khác bất ngờ xử lý URL ấy.

Ba cách giải quyết có chủ đích:

1. Dùng fallback web chain khớp `/login` như ví dụ đầy đủ.
2. Cấu hình login URL và processing URL dưới namespace mà chain nhận, rồi kiểm thử cả GET/POST.
3. Dùng một `RequestMatcher` tổng hợp cho chain để bao gồm cả các endpoint authentication phụ trợ nếu thực sự cần.

Ví dụ custom URL fragment:

~~~java
http
    .securityMatcher("/web/**")
    .formLogin(form -> form
        .loginPage("/web/login")
        .loginProcessingUrl("/web/login")
        .permitAll()
    );
~~~

Nếu dùng fragment này, bạn **phải tự cung cấp trang GET /web/login** (và CSRF token thích hợp cho form), thay vì dựa vào default-generated login page của Spring Security khi chỉ định `loginPage`. Bảo đảm route xử lý được các URL và method cần thiết, không để form GET nhưng POST trỏ sang chain khác.

**Đối với OAuth2/OIDC:** callback như `/login/oauth2/code/*` cũng phải đi vào chain có filter OAuth2 login; URL login/callback/authorization redirect phải nhất quán với path matching và reverse proxy base path.

## 10. permitAll so với web.ignoring(): nhìn giống nhưng khác lớp bảo vệ

Hai thiết kế có thể đều trả nội dung public, nhưng không tương đương:

~~~java
// Endpoint công khai nhưng VẪN chạy trong SecurityFilterChain.
http.authorizeHttpRequests(a -> a
    .requestMatchers("/public", "/assets/**").permitAll()
    .anyRequest().authenticated()
);
~~~

So với:

~~~java
// Fragment: WebSecurityCustomizer; cố tình bỏ qua Spring Security filters.
@Bean
WebSecurityCustomizer ignoringStaticFiles() {
    return web -> web.ignoring().requestMatchers("/assets/**");
}
~~~

Sự khác nhau:

| Hành vi | `permitAll()` | `web.ignoring()` |
| --- | --- | --- |
| Request có đi qua Spring Security chain không? | Có | Không qua các security filters được ignore |
| Authorization rule cụ thể cho URL | Cho phép | Không được thực thi vì bỏ qua |
| Security headers và các bảo vệ ở filter | Có thể vẫn áp dụng | Có thể bị bỏ qua |
| Csrf/security context/other filters | Vẫn tham gia theo chain | Bỏ qua tương ứng |
| Khi nào nên dùng | Public URLs trong ứng dụng đã được bảo vệ | Chỉ dùng có chủ đích, hiểu hệ quả |

Tài liệu Spring Security thường khuyến nghị dùng `permitAll` cho tài nguyên tĩnh công khai thay vì bỏ qua toàn bộ filter chain, nhất là khi muốn giữ security headers. Mỗi phiên bản có tối ưu hóa xử lý session cho `permitAll`, nên đừng mặc định “permitAll đắt vì luôn query session”.

Một cấu hình `web.ignoring()` không phải chỉ thêm một `requestMatchers` phân quyền; nó thay đổi việc Spring Security có xử lý request hay không. Hãy audit điều này như một lựa chọn bảo mật.

## 11. FilterChainProxy còn làm gì ngoài chọn chain?

Theo tài liệu chính thức, `FilterChainProxy` là điểm tập trung cho Servlet security, vì vậy còn có trách nhiệm như:

1. **Áp dụng `HttpFirewall`** để bảo vệ và thống nhất cách xem request path.
2. **Điều phối đúng thứ tự security filters** của chain đã match.
3. **Dọn `SecurityContext`** sau request theo lifecycle phù hợp, tránh lẫn danh tính khi Servlet thread được tái sử dụng.
4. Cho phép cơ chế matcher khác nhau dựa trên thuộc tính của `HttpServletRequest`.
5. Trở thành điểm debug quan trọng để biết chain/filter nào đang được gọi.

Việc bỏ qua `FilterChainProxy` và đăng ký từng security filter như một Servlet filter riêng lẻ có thể khiến bạn mất các lợi ích đó, đặc biệt kiểm soát path/firewall và thứ tự bảo mật. Khi tự viết một filter nghiệp vụ, nên quyết định rõ nó thuộc Spring Security chain hay là một Servlet filter độc lập.

### Filter bên trong chain có thứ tự riêng

Một `SecurityFilterChain` có thể có các filter về CSRF, SecurityContext, authentication, exception translation, authorization và nhiều cơ chế khác. Thứ tự của chúng **quan trọng**, ví dụ xác thực thông thường cần có trước quyết định authorization dựa vào danh tính.

Bạn có thể thêm filter riêng:

~~~java
// Fragment khi customFilter là Servlet Filter phù hợp, đã được
// thiết kế và kiểm thử tránh chạy trùng.
http.addFilterBefore(customFilter, AuthorizationFilter.class);
~~~

Đừng sắp xếp bằng cách tự gọi `chain.doFilter` ở controller. `HttpSecurity` cung cấp các điểm `addFilterBefore`, `addFilterAfter`, `addFilterAt` theo kiểu filter class.

**Rủi ro đăng ký hai lần:** nếu một custom `Filter` là `@Component`, Spring Boot có thể tự đăng ký nó vào Servlet container **ngoài** Spring Security. Nếu đồng thời thêm cùng filter vào `HttpSecurity`, nó có thể chạy hai lần hoặc ở vị trí không mong muốn. Hãy quản lý registration rõ (ví dụ `FilterRegistrationBean` disabled khi cần) và kiểm thử request thực.

Không đặt `@Order` trên filter một cách tùy tiện để “ép nó đứng sau UsernamePasswordAuthenticationFilter” trong chain Spring Security; thứ tự của filters **trong chain** nên điều chỉnh qua API `HttpSecurity`.

## 12. 401, 403, 302 và 404 nói gì về chain được chọn?

HTTP response giúp **gợi ý** chain nhưng chưa đủ để chứng minh tuyệt đối.

| Kết quả | Có thể do | Không nên kết luận ngay |
| --- | --- | --- |
| `401 Unauthorized` | Basic/Bearer entry point yêu cầu credentials hợp lệ | Request đã vào web form chain |
| `403 Forbidden` | Thiếu role, CSRF token sai, AccessDeniedHandler | Mật khẩu chắc chắn sai |
| `302 Found` tới login | Form-login entry point cần người dùng đăng nhập | Controller đã được chạy |
| `404 Not Found` | URL không có handler hoặc endpoint do filter không tồn tại trong chain đang match | Spring Security chắc chắn đã chặn |
| `200 OK` | Request được phép, hoặc không có security chain bảo vệ | Đã xác thực và được phân quyền đúng |

Ví dụ `/api/data` trả `302 /login` thay vì 401 có thể là tín hiệu request đã rơi vào web form-login fallback, hoặc API chain có entry point bị cấu hình khác. Cần xem **matchers, chain order, security filter logs** và test cùng request.

**Không đủ an toàn nếu chỉ có một test xác nhận “GET /public trả 200”.** Endpoint công khai trả 200 dù không có filter chain. Cần những negative tests xem request riêng tư có bị chặn khi anonymous, và kiểm thử first-match đúng.

## 13. Khi có nhiều lớp URL routing: contextPath, servletPath và reverse proxy

Hãy đặt một ứng dụng chạy sau reverse proxy:

~~~text
Client:  https://example.com/service/api/orders
Proxy:   /service/api/orders -> /api/orders
App:     context path hoặc servlet path được cấu hình riêng
~~~

Spring Security match request **theo request mà Servlet stack thực sự nhận**, qua matcher implementation và firewall, không nhất thiết theo URL đầy đủ trên thanh địa chỉ. Cần xác định:

- `server.servlet.context-path` và cách matcher xử lý context path.
- Servlet mapping khi dùng nhiều `DispatcherServlet`.
- Proxy path stripping, forwarded headers và cấu hình tin cậy reverse proxy.
- Encoded slash, semicolon, query string và normalization.
- Các đường `/api` và `/api/` có nằm trong phạm vi matcher dự kiến không.
- URL có thể đi qua `FORWARD`, `ERROR` hoặc `ASYNC` dispatch không.

**Không tự bỏ tiền tố context path khỏi pattern** theo suy đoán; kiểm thử ngay trên môi trường triển khai có proxy hoặc xây test phản ánh chính xác container path mapping. Một rule `securityMatcher("/api/**")` chỉ hữu ích nếu URL mà matcher quan sát được có đúng phạm vi bạn định bảo vệ.

### HTTP method cũng có thể là ranh giới chain

Có hệ thống cần chain khác nhau cho `GET /api/**` và `POST /api/**`. Một `RequestMatcher` tùy chỉnh có thể xét method, nhưng khi làm vậy bạn cần chắc chắn **mọi method còn lại** đều có fallback bảo vệ. Ví dụ `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS` và `TRACE` không được âm thầm bỏ qua do người viết chỉ nhớ GET/POST.

Thông thường, nếu các method chỉ khác quyền truy cập mà dùng cùng bộ filters, dùng `authorizeHttpRequests().requestMatchers(HttpMethod.GET,...)` bên trong **một chain** dễ an toàn hơn là tách thành nhiều chain.

### CORS preflight không phải login lỗi

Browser có thể gửi `OPTIONS /api/data` kèm CORS headers mà **không có credentials** trước actual request. Nếu security chain bắt request OPTIONS như một login bình thường và từ chối sai, frontend có thể báo lỗi CORS thay vì giải thích đúng. Cấu hình CORS cần phối hợp với Spring Security, có nguồn origins đáng tin và policy theo endpoint. **Không giải quyết bằng cách cho toàn bộ `OPTIONS /**` bỏ qua mọi security filter** trừ khi đó là quyết định đã được đánh giá.

## 14. DispatcherType: một URL có thể đi qua nhiều dispatch

Servlet hỗ trợ các dispatcher type như `REQUEST`, `FORWARD`, `ERROR` và `ASYNC`. Khi container dispatch sang `/error`, một security filter chain có thể tham gia tùy registration và security config.

Một số lỗi thường gặp:

- `/error` bị chặn làm che lỗi gốc từ API.
- Custom filter có side effect chạy lặp khi `FORWARD` hoặc `ERROR`.
- `SecurityContext` bị dọn/khôi phục ở các thời điểm dispatch khác nhau.
- Rule áp cho request ban đầu nhưng không được xét khi internal forward sang vùng nhạy cảm.
- Trả 401/403 sau error dispatch thay vì response dự định.

Khi cần quyết định theo dispatcher type, Spring Security có matcher tương ứng, nhưng phải hiểu filter registration của Servlet container và tránh biến forward thành cách vượt authorization. `permitAll` trên một dispatcher type là quyết định có phạm vi, không phải lời hứa controller đích an toàn.

Không nên tự khai báo `springSecurityFilterChain` nhiều lần cho các dispatcher types mà không kiểm tra tác dụng. Spring Boot/Spring Security có cơ chế tích hợp mặc định; chỉ override khi có lý do và test thực tế.

## 15. Quan sát chính xác chain đang được chọn

Trong môi trường dev/test, có thể tăng logging:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

Hoặc dùng log level DEBUG cho phạm vi nhỏ hơn:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=DEBUG
~~~

Thông tin có thể giúp xem request đi qua security filters nào. Dạng text chính xác của log thay đổi theo phiên bản; không viết test production dựa trên từng chữ của dòng log.

Một số cách debug:

1. Xem danh sách `SecurityFilterChain` được tạo trong startup và thứ tự của chúng.
2. Đặt breakpoint ở `FilterChainProxy.doFilterInternal` hoặc logic chọn `getFilters` khi debug.
3. Kiểm tra `matches(HttpServletRequest)` của từng chain với request đã qua firewall/mapping phù hợp.
4. Xem filter authentication nào có mặt trong chain: Basic, UsernamePassword, Bearer...
5. Kiểm tra `AuthorizationFilter`/entry point/AccessDeniedHandler và rule đúng chain.
6. Dùng `MockMvc` kiểm thử cả expected allow và expected deny cho từng namespace.
7. Kiểm tra `springSecurityFilterChain` có được Servlet container đăng ký, không bị disable hoặc đặt sai dispatcher registration.

Nếu bạn dùng Actuator hoặc logging HTTP, **không in raw Authorization header, cookie, session ID, mật khẩu, JWT hay full Authentication** vào log. Khi cần trace, dùng correlation ID và thông tin route/chain đã lọc dữ liệu nhạy cảm.

### Introspection FilterChainProxy trong test

Có thể inject bean `FilterChainProxy` và đọc các chain:

~~~java
// Fragment JUnit/Spring test, không phải standalone Java.
@Autowired
FilterChainProxy springSecurityFilterChain;

@Test
void expectedNumberOfSecurityChains() {
    assertEquals(3, springSecurityFilterChain.getFilterChains().size());
}
~~~

Đây là kiểm tra **số lượng chain trong cấu hình demo**, không tự chứng minh matcher đúng; các integration/extension khác có thể thêm chain. Cần import `org.springframework.security.web.FilterChainProxy` và JUnit assertions.

Test mạnh hơn dùng requests thật qua `MockMvc` như phần 7, hoặc tạo `MockHttpServletRequest` với servletPath/contextPath chính xác để kiểm tra `SecurityFilterChain.matches(request)` theo từng case. Không nên mock đơn giản `getRequestURI` nhưng quên `getServletPath` rồi kết luận matcher hỏng.

## 16. Java 17 thuần: mô phỏng thuật toán first-match, không có Spring

Để nhớ cơ chế một cách chắc chắn, đây là chương trình Java 17 **không cần thư viện**. Nó chỉ mô phỏng thứ tự xét matcher; **không phải** triển khai `FilterChainProxy` thay thế cho Spring Security.

Tạo `ChainSelectionModel.java`:

~~~java
import java.util.List;
import java.util.function.Predicate;

public final class ChainSelectionModel {

    record Chain(String name, Predicate<String> matches) {}

    static String select(List<Chain> ordered, String requestPath) {
        for (Chain chain : ordered) {
            if (chain.matches().test(requestPath)) {
                return chain.name();
            }
        }
        return "NONE";
    }

    public static void main(String[] args) {
        List<Chain> chains = List.of(
            new Chain("API", path -> path.startsWith("/api/")),
            new Chain("ADMIN", path -> path.startsWith("/admin/")),
            new Chain("WEB", path -> true)
        );

        for (String path : List.of(
                "/api/data", "/admin/panel", "/web/private")) {
            System.out.println(path + " -> " + select(chains, path));
        }

        // Đặt fallback lên đầu: mọi request bị nó lấy trước.
        List<Chain> wrongOrder = List.of(
            new Chain("WEB", path -> true),
            new Chain("API", path -> path.startsWith("/api/"))
        );
        System.out.println("wrong-order -> "
                + select(wrongOrder, "/api/data"));
    }
}
~~~

Chạy bằng JDK 17:

~~~bash
javac ChainSelectionModel.java
java ChainSelectionModel
~~~

Stdout:

~~~text
/api/data -> API
/admin/panel -> ADMIN
/web/private -> WEB
wrong-order -> WEB
~~~

Điều chương trình cho thấy: **cùng một danh sách matchers, chỉ thay thứ tự cũng có thể đổi chain được chọn**. Nhưng đừng dùng `String.startsWith` để viết một production `RequestMatcher` thay cho cơ chế Spring Security có firewall và path matching an toàn; đây chỉ là mô hình tư duy.

## 17. Ma trận cấu hình và kiểm thử cần có

Với một dự án nhiều chain, nên lập bảng bao phủ tất cả namespace quan trọng:

| Request | Chain dự định | Auth mechanism | Điều cần assert |
| --- | --- | --- | --- |
| `GET /api/public` | API | Public trong API chain | 200 và header security phù hợp |
| `GET /api/data` anonymous | API | Basic | 401 chứ không redirect form |
| `GET /api/data` với USER | API | Basic | 200 với đúng principal |
| `GET /admin/panel` với USER | Admin | Basic | 403 |
| `GET /admin/panel` với ADMIN | Admin | Basic | 200 |
| `GET /public` anonymous | Web | Permit all | 200 |
| `GET /web/private` anonymous | Web | Form | Redirect login |
| `POST /login` với CSRF/login hợp lệ | Web | Form | Tạo login/session hợp lệ |
| `GET /web/private` sau login form | Web | Session | 200, đúng username |
| `GET /unknown` | Web fallback | Authenticated | Không được bypass |
| `GET /api` không có slash | Phải định nghĩa rõ | Theo chủ đích | Không bypass do edge path |
| `GET /admin` không có slash | Phải định nghĩa rõ | Theo chủ đích | Không bypass quản trị |
| `OPTIONS /api/data` preflight | API/CORS theo thiết kế | CORS | Không lỗi do chain bất ngờ |
| URL encoded/double slash | Firewall + matcher | Theo policy | Không diễn giải path lệch để bypass |
| `/error` ERROR dispatch | Theo security config | Error handling | Không lộ dữ liệu và không che nguyên nhân |
| URL sau reverse proxy rewrite | Chain đúng với path thực | Theo endpoint | Không rơi vào fallback sai |
| Filter tự viết | Chỉ chain dự định | Chính sách riêng | Không chạy hai lần |
| Không chain match trong cấu hình thử nghiệm | NONE | Không có Spring Security filter | Test cảnh báo lỗ hổng |

**Không chạy các test “hệ thống tự phục hồi” bằng cách xóa fallback trong production**. Hãy dùng môi trường test và test cấu hình theo matcher ma trận để phát hiện vùng không được bảo vệ.

### Có nên gộp role rules vào một chain?

Nếu khác biệt chỉ là:

~~~text
/api/report -> hasAuthority("REPORT_READ")
/api/admin  -> hasRole("ADMIN")
/api/data   -> authenticated()
~~~

và cả ba đều dùng cùng cơ chế Bearer, cùng session policy, cùng CSRF/CORS, thì **một chain** với nhiều `requestMatchers` có thể đơn giản và an toàn hơn. Dùng nhiều `SecurityFilterChain` khi cần tách hẳn bộ filters (ví dụ Basic cho máy, form login cho web, OAuth2 resource server cho API).

## 18. Các lỗi thường gặp cần tự phát hiện

1. **“SecurityFilterChain là servlet FilterChain.”** Không; `FilterChainProxy` dùng nó để chọn danh sách security filters.
2. **“DelegatingFilterProxy tự quyết định API hay Web.”** Nó là cầu nối đến bean `FilterChainProxy`; proxy mới chọn chain.
3. **“FilterChainProxy chọn chain có pattern dài nhất.”** Không; first-match theo thứ tự được cấu hình.
4. **“Nếu hai chain cùng match, cả hai đều chạy.”** Không; chỉ chain đầu tiên.
5. **“API bị 403 thì FilterChainProxy chuyển sang Web.”** Không; lỗi permission nằm trong chain đã chọn.
6. **“`requestMatchers` quyết định chain nào được chạy.”** Không: nó quyết định rule authorization **bên trong chain**.
7. **“`anyRequest()` trong API chain bảo vệ mọi URL ứng dụng.”** Không; chỉ request đã match API chain.
8. **“Chain không có `securityMatcher` sẽ bị bỏ qua.”** Ngược lại, default match-all và có thể nuốt request.
9. **“`@Order(99)` phải chạy trước `@Order(1)` vì số lớn hơn.”** Sai; số thấp ưu tiên trước.
10. **“Khai báo method `apiSecurity` trước `webSecurity` đã đủ bảo đảm order.”** Không nên dựa vào thứ tự source; dùng `@Order`.
11. **“Không cần fallback vì Boot sẽ luôn tự thêm một chain.”** Không; custom chains thường khiến default back off.
12. **“PermitAll cũng giống không có security chain.”** Không; permitAll vẫn đi qua Spring Security.
13. **“Static resources luôn nên dùng web.ignoring().”** Không mặc định; có thể mất security headers/bảo vệ.
14. **“Có `formLogin()` ở chain /web/** thì `/login` luôn tồn tại.”** Không nếu login endpoints ngoài matcher.
15. **“Mọi 404 ở /login đều do controller chưa viết.”** Có thể login page/filter không nằm trong chain.
16. **“`SessionCreationPolicy.STATELESS` tự tạo JWT validation.”** Không; cần filter/decoder và cấu hình tương ứng.
17. **“HTTP Basic sai password nên trả 403.”** Thường 401; 403 thường cho thiếu quyền/CSRF.
18. **“Một custom Filter @Component chỉ được chạy trong HttpSecurity.”** Có thể Boot đăng ký nó thêm ở container.
19. **“Thêm @Order trên custom filter là thay được thứ tự Spring Security filters.”** Không; hai tầng thứ tự khác nhau.
20. **“`HttpFirewall` chỉ là optimization không ảnh hưởng an toàn.”** Nó bảo vệ path matching khỏi đầu vào bất thường.
21. **“Encoded path, contextPath và reverse proxy rewrite không cần test.”** Có thể làm sai chain selection.
22. **“`/api` và `/api/**` chắc chắn tương đương trên mọi matcher.”** Không nên giả định.
23. **“OPTIONS preflight luôn có Authorization header.”** Không; browser có thể gửi preflight riêng.
24. **“Một request 200 chứng minh đã được authentication/authorization.”** Không; có thể request không vào security chain.
25. **“`/admin` có role check trong fallback nên đủ dù API chain đã match.”** Không; first-match chặn fallback.
26. **“Spring Security chỉ kiểm tra URL, không thể so method/header.”** `RequestMatcher` có thể xem thuộc tính của request.
27. **“TRACE logging có thể bật vĩnh viễn trên production để kiểm tra chain.”** Không nên; giảm mức log và lọc secrets.
28. **“Một SecurityFilterChain dùng Spring MVC có thể copy nguyên sang WebFlux.”** Không; dùng stack/filter API khác.
29. **“Xóa `SecurityContextHolder` ở controller là logout mọi session.”** Không; xử lý session/token riêng.
30. **“Role ADMIN trong một chain bảo vệ cả multi-tenant tự động.”** Không; owner/tenant/resource-level authorization vẫn cần.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao ứng dụng có thể có nhiều `SecurityFilterChain` nhưng container chỉ thấy một proxy filter đại diện Spring Security?

*Trả lời:* `DelegatingFilterProxy` kết nối container với bean `FilterChainProxy`; proxy nhận nhiều cấu hình `SecurityFilterChain` và chọn danh sách filters cho từng request.

**Câu 2.** Nếu `/api/orders` match cả `/api/**` và `/**`, chain nào chạy?

*Trả lời:* Chain xuất hiện **trước** trong danh sách được `FilterChainProxy` xét. Với cấu hình API `@Order(1)`, fallback `@Order(3)`, chỉ API chain chạy.

**Câu 3.** Khi đã chọn API chain, `AuthorizationFilter` từ fallback web chain có tiếp tục chạy không?

*Trả lời:* Không. Chỉ các filters thuộc chain đã được chọn, theo cơ chế điều phối của proxy, được thực thi. Bảo vệ chung phải áp dụng trong API chain hoặc lớp khác chắc chắn chạy.

**Câu 4.** `securityMatcher("/api/**")` khác `requestMatchers("/api/public").permitAll()` ở đâu?

*Trả lời:* `securityMatcher` chọn **chain**; `requestMatchers` trong `authorizeHttpRequests` chọn **rule phân quyền** sau khi chain đã được chọn.

**Câu 5.** Nếu chỉ có chain `securityMatcher("/api/**")`, chuyện gì xảy ra với `GET /admin/panel`?

*Trả lời:* Không có Spring Security chain nào khớp, request có thể đi tiếp mà không được Spring Security bảo vệ. Cần fallback hoặc một chain khác bao phủ `/admin/**`.

**Câu 6.** Một chain `/**` `@Order(1)` và API chain `/api/**` `@Order(2)` có ổn không?

*Trả lời:* Không nếu bạn muốn API policy riêng: catch-all match trước và nuốt API. Đổi thứ tự chain cụ thể trước fallback.

**Câu 7.** Vì sao bật formLogin trong một chain chỉ match `/web/**` có thể khiến `POST /login` không hoạt động?

*Trả lời:* Login-processing URL ngoài phạm vi chain, nên filter xử lý login không được gọi. Đưa URL login vào matcher hoặc đổi login endpoints vào namespace đúng.

**Câu 8.** `permitAll` có tắt CSRF, security headers và toàn bộ Spring Security filters không?

*Trả lời:* Không. Nó là quyết định authorization cho phép, trong khi các filters khác vẫn hoạt động theo chain đã chọn.

**Câu 9.** Tại sao không nên register một custom Filter vừa là @Component vừa addFilterBefore?

*Trả lời:* Nó có thể được container đăng ký bên ngoài Spring Security và đồng thời chạy trong chain, dẫn tới chạy lặp hoặc sai thứ tự.

**Câu 10.** Một `403` ở API có chứng minh được chain nào chạy không?

*Trả lời:* Không hoàn toàn. Có thể do authorization hoặc CSRF. Phải xem matcher, logs, cấu hình và request-specific integration tests.

**Câu 11.** `FilterChainProxy` có vai trò gì với path firewall?

*Trả lời:* Nó áp dụng `HttpFirewall` để kiểm tra/bọc request trước matching và security filters, giúp giảm rủi ro diễn giải URL không thống nhất.

**Câu 12.** Khi nào nên dùng một chain với nhiều authorization rules thay vì nhiều chains?

*Trả lời:* Khi các endpoint dùng cùng bộ security filters/authentication mechanism/session policy, chỉ khác role/permission theo URL; một chain thường dễ kiểm soát hơn.

**Câu 13.** Nếu một API request có Basic user hợp lệ nhưng thiếu `ROLE_ADMIN`, proxy có chuyển sang chain khác để “tìm thêm quyền” không?

*Trả lời:* Không. Lỗi authorization trong chain đã chọn được xử lý ở đó, thường 403; proxy không thử chain phía sau.

**Câu 14.** Tại sao test `/api/public=200` chưa đủ chứng minh cấu hình đúng?

*Trả lời:* Endpoint public có thể trả 200 ngay cả khi bị bỏ khỏi Spring Security filters. Cần test `/api/data` anonymous phải 401 và kiểm tra rule/chain thực sự áp dụng.

## 20. Checklist trước khi triển khai

- [ ] Đã xác định ứng dụng dùng Spring MVC/Servlet và API đúng `FilterChainProxy`/`SecurityFilterChain`, không nhầm với WebFlux.
- [ ] Chỉ có một đường đăng ký `DelegatingFilterProxy` đại diện `springSecurityFilterChain`, không tự tạo proxy thừa.
- [ ] Mỗi `SecurityFilterChain` có phạm vi matcher rõ ràng; chain đặc thù được xét trước catch-all.
- [ ] `@Order` được gắn cụ thể, tránh phụ thuộc vào thứ tự methods hoặc cùng priority bất định.
- [ ] Hiểu `securityMatcher` chọn chain, `requestMatchers` chọn authorization rule trong chain.
- [ ] Có fallback rõ ràng bảo vệ các URL không thuộc API/admin; không vô tình bỏ request khỏi Spring Security.
- [ ] Đã kiểm thử cả `/api`, `/api/`, `/admin`, `/admin/` và các URL biên của pattern.
- [ ] Form login, logout, OAuth2 callback hay endpoint do filter cung cấp nằm trong chain có filter tương ứng.
- [ ] Rule bảo vệ quan trọng **có mặt trong chain thật sự match**, không trông chờ chain ở sau.
- [ ] Có negative tests cho 401/403 và không chỉ kiểm tra endpoint public 200.
- [ ] Có test cho Basic/Bearer/form entry point để phát hiện API trả redirect bất ngờ.
- [ ] Không tắt CSRF đại trà chỉ vì chain dùng API; hiểu browser credentials và phương thức ghi.
- [ ] CORS preflight/OPTIONS được xử lý đúng mà không bỏ qua toàn bộ security filter không chủ đích.
- [ ] `HttpFirewall` và path matching không bị nới lỏng tùy tiện; test encoded/path traversal và reverse proxy routing.
- [ ] Nếu dùng filter riêng, chắc chắn chỉ được đăng ký một lần và đúng thứ tự bên trong chain.
- [ ] Session policy của từng chain được xác định; stateless API không mặc định thừa hưởng web session.
- [ ] Authorization còn kiểm tra owner/tenant/resource-level; role chung không tự cho phép mọi bản ghi.
- [ ] Dispatcher types ERROR/FORWARD/ASYNC có chính sách rõ và không làm lộ context.
- [ ] Có quan sát/log khi debug, nhưng không ghi cookies, session ID, passwords, bearer tokens hoặc full Authentication.
- [ ] Khi nhiều chain mới được thêm, chạy lại ma trận test toàn bộ routes và edge cases.
- [ ] Đã đối chiếu tài liệu đúng phiên bản Spring Security và Spring Boot hiện triển khai.

### Tổng kết

**`FilterChainProxy` không hỏi “request có quyền gì?” trước tiên; nó hỏi “request này thuộc `SecurityFilterChain` nào?”** Sau khi tìm được chain khớp đầu tiên, chỉ filters của chain đó chạy để xác thực, bảo vệ chống khai thác và phân quyền theo cấu hình. **`securityMatcher` chọn phạm vi chain; `requestMatchers` trong `authorizeHttpRequests` chọn rule quyền.**

Tư duy đúng là thiết kế chuỗi điều kiện ưu tiên rõ, đặt chain chuyên biệt trước, có fallback bảo vệ, đưa login/callback endpoints vào đúng chain và test cả đường được phép lẫn đường phải bị chặn. Đừng mặc định các chain được gộp hoặc Spring Security sẽ tự bảo vệ những đường không được matcher nào nhận.

### Tài liệu tham khảo

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Java Configuration, Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — FilterChainProxy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security — SecurityFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html)
- [Spring Security — DefaultSecurityFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/DefaultSecurityFilterChain.html)
- [Spring Security — RequestMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html)
- [Spring Security — HttpFirewall API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/HttpFirewall.html)
- [Spring Security — StrictHttpFirewall API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/firewall/StrictHttpFirewall.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Adding Custom Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-security-filters)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Boot 4.1.2 Release Note](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
