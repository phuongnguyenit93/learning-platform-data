# HttpSecurity và bước build SecurityFilterChain trong ứng dụng Servlet

Khi bắt đầu cấu hình Spring Security bằng Java, bạn sẽ thường gặp một phương thức như sau:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
    );
    return http.build();
}
~~~

Ba dòng ở giữa mô tả **chính sách bảo mật mong muốn**. Lệnh `http.build()` tạo ra **một `SecurityFilterChain` hoàn chỉnh** để Spring Security dùng khi xử lý HTTP request. Tại thời điểm đó chưa có request cụ thể nào được đăng nhập hay phân quyền; bạn đang xây dựng cấu hình để phục vụ các request về sau.

Hiểu rõ mối quan hệ này giúp giải thích vì sao khai báo `SecurityFilterChain` có hiệu lực, vì sao nhiều filter chạy theo thứ tự riêng, và tại sao một URL đôi khi không được bảo vệ dù mã nguồn có `anyRequest().authenticated()`.

Bài tập trung vào **Servlet/Spring MVC**, ví dụ sử dụng Java 17+, Spring Boot 3.5.16 và Spring Security do Boot quản lý. Đây là phiên bản minh họa có tài liệu 6.5 tương ứng; nhánh Boot 3.5 đã kết thúc hỗ trợ OSS từ tháng 6/2026, nên khi khởi tạo hệ thống production mới cần chọn nhánh Boot đang được hỗ trợ và đối chiếu API theo phiên bản đó. Các khái niệm `HttpSecurity`, `SecurityFilterChain` và `FilterChainProxy` vẫn là nền tảng trong cấu hình Servlet hiện đại.

## 1. Nhận diện chính xác ba đối tượng dễ bị nhầm

| Đối tượng | Vai trò | Tồn tại ở thời điểm nào? |
| --- | --- | --- |
| `HttpSecurity` | **Builder**, nhận DSL và các `SecurityConfigurer` để xây dựng bộ lọc | Chủ yếu trong quá trình tạo bean cấu hình khi ứng dụng khởi động |
| `SecurityFilterChain` | **Sản phẩm của builder**, gồm `RequestMatcher` và danh sách filter đã được cấu hình/sắp xếp | Sau khi `http.build()` thành công; được giữ để xử lý các request |
| `FilterChainProxy` | **Filter điều phối**, chọn `SecurityFilterChain` nào khớp với từng request | Khi Servlet container nhận request và chuyển vào Spring Security |

`HttpSecurity` thuộc package `org.springframework.security.config.annotation.web.builders`. `SecurityFilterChain` thuộc `org.springframework.security.web`. Một implementation thông dụng của kết quả build là `DefaultSecurityFilterChain`. Các kiểu này **không phải tên khác nhau của cùng một object**.

Bạn có thể hình dung:

~~~text
HttpSecurity                    -- builder/bản thiết kế
   |
   +-- authorizeHttpRequests    -- quy tắc truy cập
   +-- httpBasic hoặc formLogin -- cách nhận bằng chứng xác thực
   +-- csrf / headers / cors    -- lớp bảo vệ liên quan
   +-- sessionManagement        -- lựa chọn về phiên
   +-- securityMatcher          -- phạm vi của chain
   |
   v
http.build()                    -- hoàn tất cấu hình
   |
   v
DefaultSecurityFilterChain      -- matcher + filters đã sắp thứ tự
   |
   v
FilterChainProxy                -- giữ danh sách các chain
   |
   v
Request đến sau này             -- chọn và chạy chain phù hợp
~~~

`SecurityFilterChain` **không phải** đối tượng được gọi `build()` để tạo controller, và bản thân nó cũng **không** thực thi kiểm tra mật khẩu ngay tại thời điểm build. Nó nói cho `FilterChainProxy` biết khi nào và chạy những servlet filter nào.

## 2. HttpSecurity làm gì trước khi build?

`HttpSecurity` triển khai kiểu builder cấu hình của Spring Security. Trong cấu hình Java, những lời gọi fluent API như `authorizeHttpRequests`, `httpBasic` hay `csrf` cung cấp thông số cho các *configurer*. Mỗi configurer sẽ bổ sung các thành phần phù hợp khi builder được hoàn thiện.

Ví dụ:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/public/**").permitAll()
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated())
    .httpBasic(Customizer.withDefaults())
    .csrf(Customizer.withDefaults());

return http.build();
~~~

Các tác dụng cần phân biệt:

- `authorizeHttpRequests`: thiết lập **quy tắc phân quyền cho request**. Với cách cấu hình này, một `AuthorizationFilter` sẽ phối hợp với `AuthorizationManager` để đánh giá các rule.
- `httpBasic`: bật cơ chế đọc HTTP Basic credentials phù hợp và xử lý yêu cầu xác thực; trong chain có thể xuất hiện `BasicAuthenticationFilter`.
- `csrf`: cấu hình bảo vệ Cross-Site Request Forgery. Với ứng dụng web kiểu Servlet, CSRF được bật mặc định và thường kiểm tra các phương thức HTTP không an toàn.
- `headers`: quy tắc thêm các security response headers; một số giá trị đã có mặc định.
- `sessionManagement`: cách ứng dụng quản lý phiên, chính sách tạo session và một số hành vi liên quan.
- `exceptionHandling`: cách phản ứng khi cần đăng nhập hoặc quyền bị từ chối, chẳng hạn `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- `formLogin`: cấu hình hình thức đăng nhập qua form trong một chuỗi bảo mật có trạng thái phù hợp.
- `oauth2ResourceServer`: nếu thêm dependency/cấu hình thích hợp, thiết lập xác thực bearer token cho resource server.
- `securityMatcher`: giới hạn **toàn bộ chain này** áp dụng cho request nào.

Không nên suy rằng **mỗi lời gọi DSL luôn sinh đúng một filter**. Một configurer có thể tạo nhiều đối tượng, dùng chung thành phần hoặc thay đổi thứ tự/quan hệ giữa các filter. Tên từng filter phụ thuộc phiên bản và các cơ chế được bật.

### Vì sao dùng Customizer và lambda?

Trong Java DSL hiện đại, lambda giúp nhóm các tùy chọn cùng chủ đề:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
);
~~~

Biến `authorize` là một đối tượng cấu hình do framework cung cấp; bạn không cần tự khởi tạo nó. `Customizer.withDefaults()` có nghĩa là **bật/cấu hình thành phần theo mặc định của configurer**, chứ không phải cho phép tất cả request. Cụ thể, `httpBasic(Customizer.withDefaults())` không hề cấp sẵn `ROLE_ADMIN` cho người dùng.

Hãy ưu tiên DSL lambda của nhánh Spring Security đang dùng; nhiều bài hướng dẫn cũ sử dụng `WebSecurityConfigurerAdapter` hoặc cách gọi không còn phù hợp.

## 3. Trong bước http.build() thực sự diễn ra điều gì?

`HttpSecurity` kế thừa cơ chế `AbstractConfiguredSecurityBuilder`. Khi `build()` được gọi, builder thực hiện vòng đời tạo thành phần mà tài liệu API mô tả. Ở mức khái niệm:

1. **Giai đoạn khởi tạo:** các configurer được đăng ký nhận cơ hội `init(...)`, chuẩn bị cấu hình và các shared objects cần thiết.
2. **Giai đoạn cấu hình:** các configurer thực hiện `configure(...)`, bổ sung filter, handler và đối tượng liên quan theo thông số của DSL.
3. **Hoàn tất đối tượng:** `HttpSecurity.performBuild()` tạo `DefaultSecurityFilterChain` với request matcher và danh sách filter có thứ tự.
4. **Bean được đăng ký:** kết quả từ `@Bean SecurityFilterChain` đi vào Spring `ApplicationContext`, nơi cơ chế web security sử dụng nó.

Đây là mô tả logic của framework, không phải mã giả cần tự chép vào `@Configuration`:

~~~text
Ứng dụng khởi động
      |
Spring gọi @Bean securityFilterChain(HttpSecurity http)
      |
      +--> DSL gắn các configurer và rule
      |
      +--> http.build()
                 |
                 +--> init các configurer
                 +--> configure các configurer
                 +--> sắp xếp filter theo thứ tự Spring Security
                 +--> tạo DefaultSecurityFilterChain
      |
      v
SecurityFilterChain bean được đưa vào context
      |
FilterChainProxy có các chain sẵn sàng
      |
[Thời điểm khác] Request HTTP đến
      |
FilterChainProxy chọn matching chain và chạy filters
~~~

**Build là công việc tạo cấu hình, không phải xử lý một request.** Spring thường gọi bean factory method trong giai đoạn khởi tạo `ApplicationContext`; không gọi `http.build()` mỗi khi có request đến. Do `AbstractSecurityBuilder` bảo vệ thao tác build một lần, đừng gọi `build()` lặp lại trên **cùng builder** hoặc tái sử dụng một `HttpSecurity` đã hoàn tất rồi tiếp tục thêm rule.

`http.build()` thường trả về một `DefaultSecurityFilterChain`, nhưng chữ ký public của bean nên dùng giao diện `SecurityFilterChain` để mã ứng dụng ít phụ thuộc implementation.

### Vì sao không tự new HttpSecurity?

Trong Spring Boot/Spring Security, container cấp một `HttpSecurity` đã được chuẩn bị với những shared objects, các configurer và khả năng liên kết với hệ sinh thái bean. Vì vậy cách tiêu chuẩn là nhận nó qua tham số method `@Bean`:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .build();
}
~~~

Việc tự `new HttpSecurity(...)` bên ngoài cơ chế của Spring Security dễ bỏ sót dependency/shared object và không phải lựa chọn cho ứng dụng thông thường. Cũng không cần tự tạo `FilterChainProxy` hay đăng ký từng security filter bằng tay trong một dự án Boot tiêu chuẩn.

## 4. Ai chạy các filter được build khi request đến?

Trong môi trường Servlet, HTTP request đi qua chuỗi filter của servlet container trước khi tới `DispatcherServlet`. Spring Security được nối vào cơ chế này theo mô hình:

~~~text
Browser / HTTP client
         |
         v
Servlet container's FilterChain
         |
         v
DelegatingFilterProxy (cầu nối sang Spring Bean)
         |
         v
FilterChainProxy (thường là bean springSecurityFilterChain)
         |
         +--> chọn SecurityFilterChain đầu tiên khớp request
                        |
                        v
             Các Security filters trong chain
                        |
                        +--> nạp/thiết lập SecurityContext khi cần
                        +--> bảo vệ CSRF/headers và các cơ chế khác
                        +--> xử lý authentication (nếu được cấu hình)
                        +--> đánh giá authorization
                        |
                        v
                DispatcherServlet
                        |
                        v
                     Controller
~~~

Hai tên có chữ “filter chain” dễ nhầm:

- **Servlet FilterChain** là cơ chế của container để điều phối filter và servlet của toàn bộ ứng dụng.
- **SecurityFilterChain** là một *danh sách filter bảo mật + request matcher* mà Spring Security quản lý bên trong `FilterChainProxy`.

`DelegatingFilterProxy` giúp servlet container gọi một Spring Bean. `FilterChainProxy` là filter điều phối các security chain. `SecurityFilterChain` mà bạn return từ `http.build()` là một cấu hình được `FilterChainProxy` tiêu thụ; **không phải mỗi bean `SecurityFilterChain` đều được container đăng ký thành servlet filter độc lập**.

Spring Boot xử lý việc đăng ký cầu nối trong một ứng dụng được cấu hình tiêu chuẩn; bạn không cần tự khai báo `web.xml` để nối từng chain.

### Các filter chạy theo thứ tự nào?

Spring Security có thứ tự tiêu chuẩn cho các filter; framework sắp xếp chúng khi xây dựng chain. Với cấu hình có CSRF, Basic authentication và `authorizeHttpRequests`, bạn có thể gặp thứ tự liên quan như:

~~~text
... SecurityContext/headers/CSRF ...
            |
 BasicAuthenticationFilter (nếu bật HTTP Basic)
            |
 ... AnonymousAuthenticationFilter ...
            |
 ExceptionTranslationFilter
            |
 AuthorizationFilter
            |
 DispatcherServlet / Controller
~~~

Đây là **sơ đồ rút gọn**, không phải danh sách filter đầy đủ hoặc thứ tự cố định áp dụng cho mọi bản/cấu hình. Điều quan trọng là các bước xác thực và bảo vệ có cơ hội xử lý **trước** quyết định phân quyền và controller.

Đừng cố thay đổi thứ tự filter chỉ bằng cách đảo thứ tự gọi `httpBasic(...)` và `authorizeHttpRequests(...)` trong Java DSL. Filter ordering thuộc cơ chế của Spring Security, không đơn giản là thứ tự câu lệnh trong file.

## 5. SecurityFilterChain gồm những gì?

Giao diện `SecurityFilterChain` về mặt ý nghĩa cần trả lời hai câu hỏi:

1. **Request này có khớp với chain không?** (request matcher).
2. **Nếu khớp, những `Filter` nào sẽ chạy?** (danh sách filter của chain).

Có thể biểu diễn:

~~~text
SecurityFilterChain A
  matcher = /api/**
  filters = [các filter dùng cho HTTP Basic/API...]

SecurityFilterChain B
  matcher = mọi request khác
  filters = [các filter dùng cho form login/web...]

GET /api/orders   -> A
GET /profile      -> B
~~~

`DefaultSecurityFilterChain` là implementation thường được tạo khi `HttpSecurity` build. Không cần `new DefaultSecurityFilterChain` khi đã dùng DSL; builder làm việc đó.

Đây cũng là lý do mã `http.build()` không trả về `FilterChainProxy`. `FilterChainProxy` quản lý **một hoặc nhiều** `SecurityFilterChain` và chọn chain phù hợp theo từng request.

## 6. Hai cấp matcher: securityMatcher và requestMatchers

Đây là một trong những phân biệt quan trọng nhất của cấu hình nhiều chain.

| Cấu hình | Cấp áp dụng | Câu hỏi nó giải quyết |
| --- | --- | --- |
| `http.securityMatcher("/api/**")` | **Toàn bộ SecurityFilterChain** | Chain này có tham gia xử lý request không? |
| `authorizeHttpRequests(a -> a.requestMatchers("/api/admin/**").hasRole("ADMIN"))` | **Rule phân quyền bên trong chain đã chọn** | Request thuộc chain này cần quyền nào? |
| `authorizeHttpRequests(a -> a.anyRequest().authenticated())` | Rule cuối trong **chain hiện tại** | Các request còn lại trong chain cần điều kiện gì? |

Ví dụ:

~~~java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Với bean này, `GET /api/orders` khớp `/api/**`, rồi rule `anyRequest().authenticated()` được xét. Nhưng **`GET /profile` không khớp `securityMatcher("/api/**")`**, nên nó không đến `anyRequest()` của chain API. Nếu toàn ứng dụng chỉ khai báo chain này và không có chain khác phù hợp, `/profile` **không được Spring Security bảo vệ bởi các chain hiện có**.

Đừng nghĩ `anyRequest()` trong một chain giới hạn bằng `securityMatcher` sẽ tự lan ra cả website.

### Mặc định securityMatcher của một chain là gì?

Khi không gọi `securityMatcher`, matcher của `HttpSecurity` thường là “mọi request”. Với **một** chain web duy nhất, điều đó bảo vệ toàn bộ các đường đi theo các rule được khai báo. Với **nhiều** chain, phải sắp thứ tự để chain cụ thể được kiểm tra trước chain bao phủ.

Thứ tự rule bên trong `authorizeHttpRequests` cũng quan trọng: hệ thống áp dụng **rule khớp đầu tiên**. Một `anyRequest().permitAll()` đặt trước các điều kiện chặt hơn (hoặc dùng sai vị trí) có thể vô hiệu hóa chính sách mong muốn; hãy khai báo rule cụ thể trước điều kiện tổng quát.

## 7. Ví dụ đầy đủ Java 17+: build một chain và kiểm tra hành vi HTTP

Ví dụ sử dụng Spring Boot **3.5.16** làm phiên bản học tập, Spring Security tương ứng do Boot quản lý. Ứng dụng có ba endpoint GET và một endpoint POST. Nó khởi tạo một `SecurityFilterChain` qua `HttpSecurity`, dùng HTTP Basic để dễ thử với `curl` và một kho người dùng in-memory cho thực hành local.

Các mục tiêu kiểm tra:

- `/public/ping` được truy cập không đăng nhập.
- `/private/whoami` chỉ truy cập sau xác thực.
- `/admin/report` yêu cầu role `ADMIN`, nên người dùng thông thường bị từ chối.
- `POST /private/change` không có CSRF token bị chặn dù client gửi credentials HTTP Basic, vì ví dụ giữ bảo vệ CSRF mặc định.

Đây là demo học tập, tài khoản và mật khẩu cố định **không phù hợp production**. Với hệ thống thực tế, cần provider, mật khẩu/secret, HTTPS và các biện pháp bảo mật phù hợp.

### 7.1. Cấu trúc project

~~~text
security-chain-lab/
  pom.xml
  src/main/java/com/example/securitychain/
    SecurityChainApplication.java
    SecurityConfiguration.java
  src/test/java/com/example/securitychain/
    SecurityRulesTest.java
~~~

### 7.2. Maven POM

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>security-chain-lab</artifactId>
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
~~~

Maven chỉ khóa phiên bản **Spring Boot** trong parent; các module Security nhận phiên bản tương thích từ Boot BOM. Java 17 là mức Java của ví dụ. Spring Boot 3.5.16 được dùng để minh họa API có tài liệu ổn định, nhưng do nhánh 3.5 đã hết OSS support, dự án production mới cần kiểm tra nhánh Boot đang nhận bản vá trước khi chốt.

### 7.3. Main class và endpoints

Tạo `src/main/java/com/example/securitychain/SecurityChainApplication.java`:

~~~java
package com.example.securitychain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class SecurityChainApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityChainApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/private/whoami")
    public String whoami(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin/report")
    public String report() {
        return "admin-report";
    }

    @PostMapping("/private/change")
    public String change() {
        return "changed";
    }
}
~~~

Bốn endpoint được khai báo rõ ràng. Phần bảo mật nằm trong filter chain; controller không cần tự đọc username/password và không tự kiểm tra role bằng `if`.

### 7.4. Cấu hình HttpSecurity và gọi build()

Tạo `src/main/java/com/example/securitychain/SecurityConfiguration.java`:

~~~java
package com.example.securitychain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
    SecurityFilterChain appChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password(encoder.encode("demo-user"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-admin"))
                .roles("ADMIN")
                .build()
        );
    }
}
~~~

Hãy đọc phương thức `appChain` theo từng bước:

1. Spring nhận diện class cấu hình vì nó nằm cùng package gốc của `@SpringBootApplication`.
2. Spring cung cấp `HttpSecurity` làm tham số cho bean factory method.
3. `authorizeHttpRequests` khai báo ba nhánh rule, với `anyRequest` làm fallback.
4. `httpBasic` bật authentication HTTP Basic, thích hợp để quan sát response 401 và gửi credentials trong bài thực hành.
5. `csrf(Customizer.withDefaults())` giữ CSRF mặc định. Trong cấu hình servlet, thao tác POST không mang CSRF token có thể bị chặn trước khi vào controller.
6. `http.build()` tạo chain và trả cho Spring đăng ký thành `SecurityFilterChain` bean.
7. `users` và `passwordEncoder` phục vụ việc kiểm tra tài khoản demo. `UserDetailsService` là nhánh riêng với chính sách URL, không phải filter chain.
8. Mặc định chain này áp dụng cho mọi request vì không có `securityMatcher` giới hạn.

Không có `formLogin` trong demo: HTTP Basic là cơ chế xác thực được chủ động bật để thuận tiện kiểm thử API. `httpBasic` không làm cho đăng nhập an toàn qua HTTP trần ngoài môi trường local; hệ thống thật cần HTTPS và cách quản lý credentials phù hợp.

### 7.5. Build và chạy ứng dụng

Với JDK 17+ và Maven đã cài:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Sau khi ứng dụng chạy ở cổng 8080, mở terminal thứ hai và kiểm tra bằng `curl`. Những username/password dưới đây **chỉ là dữ liệu giả của demo**, không dùng cho tài khoản thật; trên Windows PowerShell, dùng `curl.exe` nếu `curl` bị ánh xạ sang lệnh khác.

~~~bash
curl -s -o /dev/null -w 'public=%{http_code}\n' http://localhost:8080/public/ping
curl -s -o /dev/null -w 'private-anon=%{http_code}\n' http://localhost:8080/private/whoami
curl -s -o /dev/null -w 'private-mai=%{http_code}\n' -u mai:demo-user http://localhost:8080/private/whoami
curl -s -o /dev/null -w 'admin-mai=%{http_code}\n' -u mai:demo-user http://localhost:8080/admin/report
curl -s -o /dev/null -w 'admin-admin=%{http_code}\n' -u admin:demo-admin http://localhost:8080/admin/report
curl -s -o /dev/null -w 'post-no-csrf=%{http_code}\n' -u mai:demo-user -X POST http://localhost:8080/private/change
~~~

Kết quả status dự kiến:

~~~text
public=200
private-anon=401
private-mai=200
admin-mai=403
admin-admin=200
post-no-csrf=403
~~~

Giải thích từng trường hợp:

- **Public = 200** vì `/public/ping` khớp `permitAll`.
- **Private anonymous = 401** vì `/private/whoami` cần xác thực và cấu hình dùng HTTP Basic.
- **Private Mai = 200** vì credentials demo hợp lệ, `getName()` cung cấp `mai`.
- **Admin Mai = 403** vì Mai có `ROLE_USER` nhưng không có `ROLE_ADMIN`.
- **Admin admin = 200** vì tài khoản admin có `ROLE_ADMIN`.
- **POST thiếu CSRF = 403** vì chain bật cơ chế bảo vệ unsafe methods. Đây là một hành vi đúng trong demo, không có nghĩa `http.build()` đã lỗi.

Khi dùng `curl -u`, credentials có thể nằm trong history hoặc danh sách process; ví dụ chỉ cho localhost với bí mật giả. Lưu ý response body/headers, redirect, proxy và cấu hình security khác có thể thay đổi kết quả trong dự án thật.

### 7.6. Kiểm thử bằng MockMvc

Tạo `src/test/java/com/example/securitychain/SecurityRulesTest.java`:

~~~java
package com.example.securitychain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityRulesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointIsOpen() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointRequiresAuthentication() throws Exception {
        mvc.perform(get("/private/whoami"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void userCanOpenPrivateEndpoint() throws Exception {
        mvc.perform(get("/private/whoami"))
                .andExpect(status().isOk())
                .andExpect(content().string("mai"));
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void userCannotOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanOpenAdminEndpoint() throws Exception {
        mvc.perform(get("/admin/report"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "mai", roles = "USER")
    void unsafePostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/private/change"))
                .andExpect(status().isForbidden());
    }
}
~~~

`@WithMockUser` đưa một danh tính thử nghiệm vào `SecurityContext` của bài test; nó **không kiểm tra mật khẩu của `InMemoryUserDetailsManager`**. Vì thế nên dùng cả bài test rule ở trên và request thực tế (hoặc MockMvc HTTP Basic) nếu muốn kiểm tra toàn bộ flow đăng nhập. Test `post` thiếu CSRF token kiểm tra một lớp bảo vệ khác với authorization.

Với môi trường thật, cần thêm các bài test về quyền theo bản ghi, tenant và trạng thái nghiệp vụ; `hasRole("ADMIN")` không tự giải quyết object-level authorization.

## 8. Từ mã nguồn đến hành vi: phân biệt ba thời điểm

Một cách tự kiểm tra những điều đang xảy ra:

| Thời điểm | Công việc thực sự | Thành phần tham gia |
| --- | --- | --- |
| **Biên dịch** | Java compiler kiểm tra cú pháp và type `HttpSecurity`, `SecurityFilterChain` | JDK, Maven/Gradle, thư viện trên classpath |
| **Khởi động context** | Spring tạo bean, chạy DSL, gọi `http.build()`, sắp filter và hoàn tất chain | Spring `ApplicationContext`, `HttpSecurity`, configurers |
| **Nhận request** | `FilterChainProxy` chọn chain, các filter xử lý, endpoint được cho phép/từ chối | Servlet container, `DelegatingFilterProxy`, `FilterChainProxy`, filters, MVC |

Nếu một cấu hình bị sai và `http.build()` ném exception lúc khởi tạo bean, ứng dụng có thể **không khởi động**. Nhưng nếu app khởi động mà `GET /admin/report` trả 403, đây thường là **kết quả của logic phân quyền ở runtime**, không phải lỗi build.

Ví dụ khác: `GET /public/ping` trả 404 nhưng filter log cho thấy `permitAll`. Điều này có thể chỉ nghĩa là request đã qua security thành công nhưng Spring MVC không tìm thấy controller/route; không phải mọi mã khác 200 đều là lỗi Security.

## 9. Tạo nhiều chain bằng nhiều lần build()

Một ứng dụng có thể muốn `/api/**` dùng HTTP Basic, còn phần website dùng form login. Ta định nghĩa **hai phương thức `@Bean` khác nhau**, mỗi phương thức nhận `HttpSecurity` và build một chain riêng:

~~~java
// Mảnh cấu hình trong class @Configuration của Servlet app.
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
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Đoạn này là **fragment minh họa**: cần class, imports (`@Order`, `HttpSecurity`, `Customizer`, v.v.), nguồn người dùng và controller phù hợp trước khi chạy.

Cách `FilterChainProxy` lựa chọn:

~~~text
GET /api/orders
    |
    +--> chain @Order(1), matcher /api/** -> khớp
           |  dùng các filters/rules của apiChain
           v
         dừng chọn chain tiếp theo

GET /profile
    |
    +--> chain @Order(1), matcher /api/** -> không khớp
    |
    +--> chain @Order(2), matcher mọi request -> khớp
           |  dùng filters/rules của webChain
           v
         dừng chọn chain
~~~

**Chỉ chain đầu tiên khớp request được chọn.** Spring Security không chạy cả hai chain rồi kết hợp quyền của chúng. `@Order` ở đây quyết định thứ tự xét chain, **khác** với thứ tự của từng filter bên trong một chain.

Nên có một chain dự phòng bao phủ các request còn lại. Nếu cả hai chain đều dùng `securityMatcher` hạn chế, một URL nằm ngoài mọi matcher sẽ **không đi qua Spring Security filter chain**. Đây là một lỗi cấu hình nguy hiểm khi nghĩ rằng `anyRequest().authenticated()` trong chain đầu tiên đã bảo vệ toàn ứng dụng.

### Chú ý endpoint do filter cung cấp

Một số endpoint như `POST /login` hoặc `POST /logout` có thể được xử lý bởi Spring Security filter, không phải controller của ứng dụng. Nếu đặt `formLogin` trong một chain bị `securityMatcher("/api/**")` giới hạn nhưng URL login là `/login`, endpoint đó có thể **không nằm trong chain** để được xử lý. Phải thiết kế URL login phù hợp với phạm vi chain.

Nếu có Actuator, sau khi khai báo chain riêng, ứng dụng phải xem xét bảo vệ các endpoint quản trị đã expose. Spring Boot sẽ nhường web security default khi đã có `SecurityFilterChain` bean; đừng giả định bộ rule Boot mặc định tiếp tục bảo vệ Actuator thay bạn.

## 10. Chọn vị trí filter tùy biến

Một số ứng dụng cần filter tự viết để đọc header, kiểm tra tenant hoặc ghi sự kiện audit. `HttpSecurity` có các phương thức như:

~~~java
http.addFilterBefore(customFilter, UsernamePasswordAuthenticationFilter.class);
http.addFilterAfter(customFilter, BasicAuthenticationFilter.class);
http.addFilterAt(customFilter, SomeKnownFilter.class);
~~~

Đây chỉ là **minh họa chữ ký/cách định vị**, với `customFilter` và `SomeKnownFilter` là tên giả để nói về ý tưởng. Không copy nguyên đoạn này vào project khi chưa có lớp filter hợp lệ.

- `addFilterBefore`: chèn filter trước một filter được Spring Security nhận diện về thứ tự.
- `addFilterAfter`: chèn sau một filter được nhận diện.
- `addFilterAt`: đăng ký tại vị trí tương ứng với một filter đã biết; **không nên giả định tự động thay hoàn toàn filter cũ**. Hai filter ở cùng một vị trí có thể khiến thứ tự không xác định.

Đặt filter sai vị trí có thể làm nó chạy trước khi thông tin xác thực sẵn sàng, hoặc sau khi authorization đã ra quyết định. Cần xác định filter đang giải quyết vấn đề gì: xác thực, phân quyền, bảo vệ request hay audit.

Khi một `Filter` được khai báo vừa là **Servlet container Filter bean** vừa được thêm trực tiếp vào `HttpSecurity`, có nguy cơ filter bị gọi hai lần (một lần từ container, một lần trong Spring Security). Cần kiểm soát đăng ký và chỉ áp dụng đúng một cơ chế mong muốn.

Trước khi thêm filter, hãy cân nhắc liệu vấn đề thực sự thuộc về một `AuthorizationManager`, `AuthenticationProvider`, `OncePerRequestFilter` hoặc service nghiệp vụ. Việc tự thêm filter không nên trở thành cách xử lý mọi quy tắc bảo mật.

## 11. Những khác biệt nhỏ nhưng ảnh hưởng lớn khi viết DSL

### 11.1. permitAll không có nghĩa bypass Spring Security

Nếu cấu hình:

~~~java
.requestMatchers("/public/**").permitAll()
~~~

request công khai **vẫn đi qua security filter chain** khi matcher của chain khớp, nên có thể nhận security headers và các biện pháp bảo vệ khác. `permitAll` chỉ nói rằng rule phân quyền không yêu cầu một authority nào ở đường dẫn đó.

Ngược lại, `WebSecurityCustomizer.ignoring()` có thể làm request **bỏ qua Spring Security** hoàn toàn. Với static resources, tài liệu Spring Security hiện đại thường khuyên dùng `permitAll` để vẫn hưởng headers và những bảo vệ cơ bản.

### 11.2. Cấu hình CSRF và Authentication không trùng nhau

`authorizeHttpRequests(...).permitAll()` không làm `CsrfFilter` biến mất. Một POST tới URL công khai vẫn có thể cần CSRF token tùy chính sách và cơ chế xác thực. Lỗi 403 của POST có thể do thiếu CSRF **ngay cả khi role đã đủ**.

Trong demo, `POST /private/change` với Basic credentials nhưng thiếu CSRF được dự kiến trả 403. Tắt toàn bộ CSRF chỉ vì kiểm thử POST báo 403 có thể mở lỗ hổng cho browser sử dụng cookie; hãy hiểu client, cách gửi credentials và đánh giá biện pháp phòng thủ trước.

### 11.3. Rule URL không thay thế quyền trên dữ liệu

~~~java
.requestMatchers("/documents/**").hasAuthority("DOC_READ")
~~~

Rule này kiểm tra một authority khi truy cập chức năng. Nó không tự biết người dùng có quyền xem **document ID cụ thể** hay không. Service/repository vẫn cần chính sách owner/tenant/chia sẻ cho từng tài nguyên.

### 11.4. Tên method @Bean không phải URL matcher

Bạn có thể đặt method `adminChain` nhưng nếu không cấu hình `securityMatcher("/admin/**")`, tên method ấy **không giới hạn** request vào `/admin/**`. Chính request matcher và rule DSL mới điều khiển phạm vi.

### 11.5. HttpSecurity của Servlet khác ServerHttpSecurity của WebFlux

Spring MVC/Servlet dùng `HttpSecurity` và `SecurityFilterChain`. WebFlux/Reactive dùng `ServerHttpSecurity` và `SecurityWebFilterChain`; security filter chạy trong cơ chế reactive. Cách khai báo và thành phần không thể tráo đổi chỉ bằng cách đổi tên import.

## 12. Chẩn đoán lỗi ở build và runtime

Khi thấy cấu hình không như mong đợi, lần lượt kiểm tra:

| Hiện tượng | Hướng điều tra |
| --- | --- |
| Bean `SecurityFilterChain` chưa xuất hiện | Class `@Configuration` có được scan/import? Có `@Profile`/condition sai? |
| Application startup thất bại ở `http.build()` | Đọc exception gốc, rule DSL/configurer gây xung đột, bean còn thiếu |
| Thấy filter chain mặc định thay vì chain riêng | Kiểm tra bean thực tế, package scan và điều kiện auto-configuration của Boot |
| Request đi qua chain sai | `@Order`, `securityMatcher`, kiểu request, dispatcher type |
| Một URL không có security filter nào | Có chain fallback bao phủ URL đó không? |
| Trả 401 dù đã gửi credentials | Đúng provider và cơ chế xác thực chưa? HTTP Basic/form/token có đang bật? |
| Trả 403 dù đã đăng nhập | Thiếu authority, CSRF token hoặc điều kiện policy khác |
| Trả 302 tới `/login` | Có thể là `AuthenticationEntryPoint` của form login, chưa phải lỗi |
| Trả 404 sau khi được permit | Controller/route có tồn tại không? 404 không đồng nghĩa Security từ chối |
| Filter tùy biến chạy hai lần | Filter có được đăng ký cả trong container và Security chain? |

Bật log bảo mật có kiểm soát ở môi trường phát triển:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Có thể chọn `TRACE` khi thật cần phân tích filter cụ thể, nhưng log có thể chứa đường dẫn, thông tin liên quan xác thực và metadata nhạy cảm; không bật log chi tiết bừa bãi ở production.

Kiểm tra thêm **Condition Evaluation Report** của Boot bằng tùy chọn `--debug` nếu muốn biết vì sao cấu hình tự động rút lui. Dù thấy `SecurityFilterChain` bean, vẫn cần thử request trên từng đường dẫn quan trọng để chắc chắn đúng chain được chọn.

### Có thể kiểm tra danh sách filter đã build không?

Trong một ứng dụng đang chạy, `FilterChainProxy` quản lý các `SecurityFilterChain`. Khi debug, có thể dùng điểm dừng tại `FilterChainProxy` hoặc log phù hợp để xem matcher nào khớp và các filter nào đã được sử dụng. Đây là bằng chứng gần với runtime hơn so với chỉ đọc DSL.

Không viết test chỉ để so sánh số lượng filter mặc định, vì các bản Spring Security hoặc tùy chọn có thể thêm/bớt filter mà chính sách vẫn đúng. Test có giá trị hơn là **request bị chặn hay được cho phép đúng theo nghiệp vụ**.

## 13. Những lỗi tư duy thường gặp

1. **“`HttpSecurity` là filter xử lý mọi request.”** Sai: nó là builder; chain sau khi build mới chứa filter để chạy.
2. **“`http.build()` xác thực người dùng ngay.”** Sai: build xảy ra lúc tạo cấu hình, không có request cụ thể.
3. **“Đảo thứ tự `httpBasic()` và `csrf()` sẽ đảo thứ tự filter.”** Không đúng; Spring Security xác định filter ordering riêng.
4. **“Bean `SecurityFilterChain` chính là servlet filter tên `springSecurityFilterChain`.”** Không hoàn toàn: `FilterChainProxy` điều phối các chain và được nối vào servlet filter chain qua `DelegatingFilterProxy`.
5. **“`anyRequest()` luôn bao phủ toàn website.”** Chỉ bao phủ các request đã chọn vào chain; `securityMatcher` có thể giới hạn phạm vi.
6. **“Nhiều `SecurityFilterChain` sẽ cùng chạy trên một request.”** `FilterChainProxy` chỉ dùng chain khớp đầu tiên.
7. **“Tôi có `SecurityFilterChain` riêng thì Boot không tạo user mặc định nữa.”** Web security chain và user store là hai nhánh cấu hình khác nhau.
8. **“Cứ `permitAll` là bỏ qua mọi filter, kể cả CSRF.”** Sai: `permitAll` là rule authorization.
9. **“Một API POST 403 là do `hasRole` sai.”** Có thể do CSRF; cần xem filter và chính sách.
10. **“Filter tự viết có thể thêm vào vị trí bất kỳ.”** Sai: vị trí quyết định SecurityContext và cơ chế nào đã sẵn sàng.
11. **“`addFilterAt` chắc chắn xóa filter cũ.”** Không nên dựa vào giả định này; cần xem cơ chế đăng ký và thứ tự thật.
12. **“Cấu hình đã chạy một lần trên máy nghĩa là production an toàn.”** Còn phải kiểm thử quyền theo tài nguyên, CSRF, session, secrets, TLS và logging.
13. **“Đã có chain API thì mọi request kể cả Actuator đều bảo vệ.”** Không chắc nếu matcher giới hạn hoặc fallback mở.
14. **“WebSecurityConfigurerAdapter là cách bắt buộc để cấu hình.”** Không; Java DSL với `SecurityFilterChain` bean là cách hiện đại.

## 14. Bài tập kiểm tra hiểu đúng bước build

**Câu 1.** `http.build()` trả về loại đối tượng nào khi dùng Servlet DSL, và lúc đó đã có người dùng nào được đăng nhập chưa?

*Trả lời:* Nó tạo một `SecurityFilterChain` (thường là `DefaultSecurityFilterChain`) gồm matcher và các filter; không xác thực một request cụ thể tại bước build.

**Câu 2.** `securityMatcher("/api/**")` và `requestMatchers("/api/admin/**")` khác nhau thế nào?

*Trả lời:* Cái thứ nhất quyết định **chain có được chọn** cho request không. Cái thứ hai quyết định **rule phân quyền** bên trong chain khi chain đã được chọn.

**Câu 3.** Một chain API có `securityMatcher("/api/**")` và `anyRequest().authenticated()`. Điều đó có bảo vệ `GET /profile` không?

*Trả lời:* Không, nếu không có chain khác khớp. `GET /profile` không đi vào chain API, nên `anyRequest()` trong chain đó không được xét.

**Câu 4.** Vì sao `@Order(1)` quan trọng khi có nhiều `SecurityFilterChain`?

*Trả lời:* Nó ảnh hưởng thứ tự xét chain của `FilterChainProxy`; chỉ chain khớp đầu tiên xử lý request. Nó không phải lệnh đảo filter order bên trong từng chain.

**Câu 5.** Một user có `ROLE_USER`, gọi POST được rule `authenticated()` cho phép nhưng không có CSRF token. Kết quả có thể là gì?

*Trả lời:* Vẫn có thể bị từ chối, thường 403, vì CSRF là cơ chế khác với kiểm tra Authentication/authority.

**Câu 6.** Vì sao `@Bean SecurityFilterChain` riêng không tự xóa user thử nghiệm do Boot sinh?

*Trả lời:* Web security chain và auto-configuration nguồn người dùng là hai nhánh điều kiện khác nhau. Cần `UserDetailsService`, `AuthenticationProvider` hoặc `AuthenticationManager` phù hợp nếu muốn thay phần user mặc định.

**Câu 7.** Khi `http.build()` thành công nhưng request vẫn được chuyển tới `/login`, đây có phải lỗi build?

*Trả lời:* Không nhất thiết. Runtime có thể đang dùng form-login entry point vì request cần xác thực. Phải xem chain được chọn và `AuthenticationEntryPoint` thực tế.

**Câu 8.** Nếu thêm một custom filter bằng `addFilterBefore`, nên xem điều gì ngoài việc code biên dịch?

*Trả lời:* Thứ tự so với các filter xác thực/CSRF/authorization, việc đăng ký một hay hai lần, matcher của chain, và các HTTP test đảm bảo hành vi đúng.

## 15. Checklist khi hoàn tất cấu hình HttpSecurity

- [ ] Dự án đúng **Servlet/Spring MVC**, dùng `HttpSecurity` và `SecurityFilterChain`, không nhầm với WebFlux.
- [ ] Class `@Configuration` được Spring quét/nhập, method `@Bean` trả chain sau khi `http.build()` chạy thành công.
- [ ] Mỗi chain được build từ một `HttpSecurity` hợp lệ; không build lại cùng builder.
- [ ] Có quy tắc `authorizeHttpRequests` minh bạch, đặt rule cụ thể trước fallback.
- [ ] `securityMatcher` và `@Order` phù hợp nếu có nhiều chain.
- [ ] Không có URL quan trọng bị rơi ra ngoài toàn bộ chain; có fallback phù hợp.
- [ ] Endpoint xử lý login/logout và các endpoint Actuator được bảo vệ đúng phạm vi.
- [ ] Các provider/user store, `PasswordEncoder` và cơ chế authentication thực tế được cấu hình hợp lệ.
- [ ] CSRF, security headers, CORS, session và exception handling được xem xét theo loại client.
- [ ] Không tắt filter/CSRF chỉ để biến 401/403 thành 200.
- [ ] Có test cho public/anonymous/user/admin, POST có hoặc không có CSRF token, các URL ngoài matcher.
- [ ] Đã xem log/condition report khi behavior khác dự kiến và kiểm tra request thực tế.

Khi đọc một `@Bean SecurityFilterChain`, hãy tách ba câu hỏi theo thứ tự: **`HttpSecurity` đang định nghĩa chính sách gì → `build()` tạo chain nào với matcher/filter nào → `FilterChainProxy` sẽ chọn và chạy chain đó cho request nào?** Trả lời đúng cả ba giúp hiểu được cấu hình Servlet từ lúc khởi động đến khi bảo vệ URL thật.

### Tài liệu tham khảo

- [Spring Security 6.5 — Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security — HttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html)
- [Spring Security — AbstractConfiguredSecurityBuilder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/AbstractConfiguredSecurityBuilder.html)
- [Spring Boot 3.5 — Security Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 3.5.16 release and OSS support notice](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
