# Phân biệt cấu hình tự động của Spring Boot với cấu hình bảo mật do ứng dụng cung cấp

## 1. Mục tiêu và phạm vi

Khi thêm `spring-boot-starter-security` vào **Spring Boot dùng Servlet/Spring MVC**, ứng dụng thường được bảo vệ ngay cả khi lập trình viên chưa viết lớp cấu hình Spring Security nào. Đó là kết quả của **auto-configuration** của Spring Boot: Boot kiểm tra classpath, loại ứng dụng và các bean hiện có, rồi cung cấp các bean mặc định *khi điều kiện phù hợp*.

Ngược lại, **cấu hình do ứng dụng cung cấp** là những bean và quy tắc mà lập trình viên chủ động khai báo để đáp ứng chính sách truy cập cụ thể. Điểm quan trọng nhất: **mặc định của Boot dành cho HTTP security chain và mặc định của Boot dành cho người dùng trong bộ nhớ là hai nhánh riêng**. Tạo `SecurityFilterChain` riêng thường làm Boot ngừng tạo **chain HTTP mặc định**, nhưng **không tự động ngừng tạo tài khoản mặc định**. Và tạo `UserDetailsService` riêng có thể làm Boot ngừng tạo **tài khoản mặc định**, trong khi **chain HTTP mặc định vẫn được dùng**.

Bài này tập trung vào **giai đoạn khởi tạo cấu hình bảo mật Servlet**, cách Spring Boot quyết định tạo bean nào và cách thay thế mặc định an toàn. Không áp dụng nguyên xi cho WebFlux, vốn dùng `SecurityWebFilterChain` thay vì Servlet `SecurityFilterChain`.

Sau khi học, bạn cần trả lời được:

- Security đến từ Spring Security framework hay từ Spring Boot auto-configuration?
- Khi nào Boot cung cấp `SecurityFilterChain`, `UserDetailsService` và mật khẩu được sinh?
- Việc khai báo một bean tùy chỉnh khiến **phần mặc định nào** ngừng hoạt động?
- Vì sao có thể có cấu hình HTTP tùy chỉnh mà log vẫn hiện mật khẩu mặc định?
- Làm cách nào kiểm tra chain thật sự được dùng và bảo đảm không bỏ sót URL?

## 2. Hai vai trò khác nhau: Spring Security và Spring Boot

**Spring Security** là framework xử lý xác thực, phân quyền, security context, CSRF, security headers, cơ chế đăng nhập, v.v. Trong ứng dụng Servlet, lõi xử lý HTTP thường bắt đầu từ một Servlet `DelegatingFilterProxy`, chuyển sang bean `springSecurityFilterChain` kiểu `FilterChainProxy` và chọn một `SecurityFilterChain` phù hợp với request.

**Spring Boot** giúp cấu hình và kết nối các thành phần này trong Spring ApplicationContext. Khi dependency và điều kiện phù hợp, Boot:

1. Kích hoạt/lắp ghép hạ tầng bảo mật HTTP cho ứng dụng Servlet.
2. Cung cấp một `SecurityFilterChain` HTTP mặc định nếu ứng dụng chưa cung cấp chain tùy chỉnh.
3. Có thể tạo một `UserDetailsService` chứa tài khoản phát triển mặc định nếu chưa có cơ chế quản lý danh tính phù hợp.
4. Áp dụng một số thuộc tính như `spring.security.user.name`, `spring.security.user.password`, `spring.security.user.roles` **cho tài khoản mặc định của Boot**, khi nhánh mặc định đó còn hiệu lực.

Sự phân công này giải thích vì sao “Boot tự bảo vệ ứng dụng” **không có nghĩa** Spring Security chỉ hoạt động nhờ Boot. Khi bạn tự tạo `SecurityFilterChain`, Spring Security vẫn xử lý filter, authentication và authorization theo cấu hình mới.

### Hình dung hai nhánh quyết định độc lập

~~~text
Spring Boot Servlet application + Spring Security trên classpath
                           |
                           v
                 Auto-configuration
                           |
             +-------------+-------------+
             |                           |
             v                           v
   HTTP security mặc định        User đăng nhập mặc định
   Có SecurityFilterChain        Có cấu hình identity khác
   do ứng dụng khai báo?         (UserDetailsService/provider/
             |                   AuthenticationManager...)?
       +-----+-----+                    |
       |           |                +---+---+
      Không        Có              Không    Có
       |           |                |       |
       v           v                v       v
 Boot có thể    Boot lùi lại     Boot có   Boot lùi lại
 tạo default    ở default       thể tạo   ở default
 chain          chain           default   user
                               user
~~~

Sơ đồ này mô tả **điển hình** của Spring Boot 3.x với Spring Security 6.x trên Servlet stack. Điều kiện thật còn phụ thuộc các bean, thư viện và kiểu ứng dụng khác (chẳng hạn OAuth2 resource server/client). Luôn kiểm tra cấu hình và Condition Evaluation Report của phiên bản đang sử dụng.

## 3. Khi không khai báo cấu hình bảo mật nào

Giả sử ứng dụng Spring MVC có dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Và chỉ khai báo endpoint:

~~~java
@RestController
class HelloController {

    @GetMapping("/hello")
    String hello() {
        return "hello";
    }
}
~~~

Nếu không có bean bảo mật tùy chỉnh và các điều kiện mặc định được đáp ứng, Boot cung cấp chuỗi bảo mật HTTP tương đương về ý tưởng với:

~~~java
@Bean
SecurityFilterChain defaultLikeChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

**Đây là mã minh họa chính sách mặc định, không phải đoạn cần chép thêm vào ứng dụng đang muốn để Boot tự cấu hình.** Trong tình huống điển hình, tất cả URL cần đăng nhập. Khi gọi `GET /hello` không có credentials, client API thường nhận **401** kèm cơ chế HTTP Basic; trình duyệt yêu cầu HTML có thể được **chuyển hướng tới trang đăng nhập**. Đây là hai cách phản hồi khác nhau cho request chưa xác thực, không phải dấu hiệu Boot tạo hai lớp bảo mật trái ngược.

Nếu chưa có nguồn người dùng tùy chỉnh phù hợp, Boot có thể tạo user mặc định tên **`user`** với mật khẩu ngẫu nhiên được thông báo ở log lúc khởi động, hoặc lấy tên/mật khẩu từ các thuộc tính `spring.security.user.*`. Việc dùng mật khẩu mặc định chỉ tiện cho phát triển và không phải giải pháp đăng nhập production.

Một request đơn giản đi qua đường xử lý:

~~~text
GET /hello
   -> Servlet container
   -> DelegatingFilterProxy
   -> FilterChainProxy
   -> SecurityFilterChain do Boot cung cấp
   -> authentication + authorization
      -> chưa xác thực: entry point (401 hoặc redirect phù hợp)
      -> hợp lệ: DispatcherServlet -> HelloController
~~~

Chú ý: Spring MVC không “tự bảo vệ” controller trên chỉ vì có `@RestController`. Spring Security chặn trước MVC khi policy yêu cầu.

## 4. Khi nào Boot lùi lại để nhường cho ứng dụng?

### 4.1. Lùi lại ở cấu hình HTTP: bạn cung cấp `SecurityFilterChain`

Trong cấu hình Servlet điển hình, Boot tạo **default web security chain** chỉ khi không có bean `SecurityFilterChain` do ứng dụng hoặc thư viện khác cung cấp. Chỉ cần có một bean thuộc loại này, Boot sẽ không thêm **default chain** của mình.

Ví dụ:

~~~java
@Configuration
class ApplicationSecurity {

    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Sau khi bean này tồn tại, cấu hình HTTP mặc định của Boot (mặc định kết hợp form login và HTTP Basic) **không được cộng thêm hoặc ghép tự động** vào các quy tắc trên. Chain ứng dụng chủ động sử dụng `httpBasic`; vì không khai báo `formLogin`, ví dụ không chủ động bật giao diện form login.

Tuy nhiên, các thành phần framework còn hoạt động: `FilterChainProxy`, security context, cơ chế filter, authorization, v.v. Boot “lùi lại ở default chain” **không đồng nghĩa** tắt Spring Security hoặc xóa toàn bộ auto-configuration khác.

### 4.2. Lùi lại ở user mặc định: bạn cung cấp nguồn danh tính

Một nhánh khác của Boot, thường do `UserDetailsServiceAutoConfiguration` đảm trách trong trường hợp username/password thông thường, có thể tạo `InMemoryUserDetailsManager` mặc định. Nhánh này lùi lại khi đã có những thành phần xác thực thích hợp, ví dụ:

- Bean `UserDetailsService` do ứng dụng cung cấp.
- Bean `AuthenticationProvider` hoặc `AuthenticationManager` do ứng dụng cung cấp.
- Các cơ chế xác thực/module đặc thù có điều kiện auto-configuration riêng, chẳng hạn một số cấu hình OAuth2.

Không nên diễn giải danh sách ví dụ này như bản sao đầy đủ điều kiện của mọi phiên bản Boot; kiểm tra điều kiện thực tế nếu ứng dụng có nhiều starter.

Ví dụ chỉ cung cấp người dùng:

~~~java
@Bean
UserDetailsService users(PasswordEncoder encoder) {
    UserDetails alice = User.withUsername("alice")
        .password(encoder.encode("local-dev-password"))
        .roles("USER")
        .build();
    return new InMemoryUserDetailsManager(alice);
}
~~~

Khi bean này được Spring quản lý và nhánh default user đủ điều kiện lùi lại, user `user`/mật khẩu ngẫu nhiên của Boot không còn được tạo từ nhánh ấy. **Nếu ứng dụng vẫn chưa khai báo `SecurityFilterChain`, Boot có thể vẫn cung cấp default HTTP chain yêu cầu đăng nhập ở mọi URL.**

Đoạn Java trên là **một method `@Bean` minh họa**, cần đặt trong `@Configuration` và có bean `PasswordEncoder`; ví dụ chạy hoàn chỉnh được cung cấp ở phần 6.

### 4.3. Bảng bốn tình huống cần nhớ

Giả định ứng dụng Servlet thông thường, có starter security và không có cấu hình đặc biệt khác:

| `SecurityFilterChain` của ứng dụng? | Nguồn identity phù hợp của ứng dụng? | HTTP chain mặc định Boot | Default user của Boot |
| --- | --- | --- | --- |
| Không | Không | **Có** | **Có** |
| **Có** | Không | **Không**; dùng chain ứng dụng | **Có thể vẫn có** |
| Không | **Có** | **Có** | **Không** |
| **Có** | **Có** | **Không**; dùng chain ứng dụng | **Không** |

Hàng thứ hai là lỗi hiểu phổ biến: khai báo `@Bean SecurityFilterChain` mà startup log **vẫn có generated security password** không có nghĩa chain tùy chỉnh thất bại. Log ấy liên quan tới **default user**, không tự chứng minh chain nào đang áp dụng.

Hàng thứ ba cũng quan trọng: thêm `UserDetailsService` **không mở public** các endpoint. Với default chain của Boot, HTTP authorization vẫn yêu cầu xác thực, chỉ có tập user hoặc cách xác thực là khác.

### 4.4. Properties không thay thế bean tùy chỉnh

Ví dụ:

~~~yaml
spring:
  security:
    user:
      name: local
      password: dev-only-password
      roles: USER
~~~

Các thuộc tính này dùng để cấu hình **user in-memory mặc định do Boot tạo ra** trong tình huống phù hợp. Chúng **không** phải DSL tổng quát để khai báo URL nào `permitAll`/`hasRole`. Khi ứng dụng có `UserDetailsService` riêng, đừng kỳ vọng `spring.security.user.password` sẽ tự sửa mật khẩu do service tùy chỉnh quản lý.

Trong môi trường thật, tránh lưu mật khẩu ứng dụng production ở file cấu hình được commit. Dùng cơ chế identity, quản lý secret và password hashing phù hợp. Snippet YAML ở trên **chỉ minh họa thuộc tính**, không phải hướng dẫn đưa mật khẩu mẫu vào production.

## 5. Thứ tự khởi tạo: điều kiện và sự hiện diện của bean

Boot không “chạy lớp bảo mật mặc định trước, sau đó chờ ứng dụng ghi đè từng rule”. Auto-configuration được khai báo theo những điều kiện như:

- **Có class trên classpath** (ví dụ các lớp Spring Security liên quan).
- **Ứng dụng có kiểu web phù hợp**, ở đây là Servlet.
- **Có hoặc thiếu bean cụ thể trong ApplicationContext**, thường dùng logic kiểu `@ConditionalOnMissingBean`.
- **Các auto-configuration khác đã được kích hoạt** hay không, thứ tự cấu hình, và các điều kiện module.

Spring Boot thu thập các định nghĩa bean và áp dụng điều kiện, nên cấu hình ứng dụng có thể làm nhánh mặc định không được đăng ký. Sau khi context sẵn sàng, phần request-time của Spring Security mới vận hành theo các bean đã hình thành. Đừng lẫn **quyết định tạo bean lúc startup** với **quyết định cấp quyền lúc có request**.

~~~text
STARTUP                                REQUEST
-------                                -------
Đọc classpath, properties              HTTP request đến container
    -> đánh giá auto-config                -> DelegatingFilterProxy
    -> thu thập custom @Bean                -> FilterChainProxy
    -> tạo chain/user/provider               -> chọn SecurityFilterChain
    -> hoàn tất ApplicationContext           -> authenticate / authorize
                                               -> MVC + service nếu được phép
~~~

**Bean name** của ứng dụng (ví dụ `applicationChain`) không cần là một chuỗi cố định; quan trọng là **kiểu `SecurityFilterChain` và cơ chế đăng ký bean trong Spring context**. Ngược lại, `springSecurityFilterChain` là tên bean hạ tầng mà `DelegatingFilterProxy` thường tham chiếu.

Một bean `SecurityFilterChain` có thể đến từ thư viện bổ sung, không chỉ từ file `SecurityConfig.java` do bạn tự viết. Vì thế, khi kết quả khác dự kiến, hãy kiểm tra **toàn bộ bean trong context**, không chỉ một file cấu hình.

## 6. Ví dụ Spring Boot 3.x / Spring Security 6.x chạy được

Ví dụ này dùng **Java 17+, Spring MVC và HTTP Basic**. Nó cung cấp cả `SecurityFilterChain` lẫn `UserDetailsService`, qua đó thay thế **hai nhánh mặc định độc lập**. Tài khoản ở bộ nhớ và mật khẩu mẫu chỉ phục vụ học tập; mật khẩu được băm bằng BCrypt tại runtime.

### 6.1. Cấu trúc project

~~~text
boot-security-choice/
├── pom.xml
└── src/main/java/com/example/securitychoice/
    ├── SecurityChoiceApplication.java
    ├── SecurityConfig.java
    └── DemoController.java
~~~

**`pom.xml`:**

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
    <artifactId>boot-security-choice</artifactId>
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
~~~

**`SecurityChoiceApplication.java`:**

~~~java
package com.example.securitychoice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityChoiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityChoiceApplication.class, args);
    }
}
~~~

**`SecurityConfig.java`:**

~~~java
package com.example.securitychoice;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    // Custom HTTP chain: Boot không tạo default HTTP chain nữa.
    @Bean
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    // Custom user store: Boot không tạo default user trong bộ nhớ nữa.
    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-pass"))
            .roles("ADMIN")
            .build();
        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
~~~

**`DemoController.java`:**

~~~java
package com.example.securitychoice;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/profile")
    public String profile(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin OK";
    }
}
~~~

Mã này minh họa:

- `/public` được `permitAll()`: request có thể không cần đăng nhập nhưng vẫn đi qua security chain.
- `/profile` yêu cầu danh tính hợp lệ vì `anyRequest().authenticated()`.
- `/admin` yêu cầu authority `ROLE_ADMIN` theo quy ước mặc định của `hasRole("ADMIN")`.
- `alice` chỉ có `ROLE_USER`; `admin` có `ROLE_ADMIN`. Authentication không đồng nghĩa có mọi quyền.
- `SecurityFilterChain` tự cung cấp chính sách HTTP; `UserDetailsService` tự cung cấp user. Không có lý do Boot phải tạo user `user` hoặc default HTTP chain khi hai nhánh này đã được ứng dụng thay thế.

**Đây là cấu hình HTTP Basic minh họa, không phải mẫu production hoàn chỉnh.** Với ứng dụng dùng cookie/session và endpoint thay đổi trạng thái, cần thiết kế CSRF, session, đăng xuất, CORS và login phù hợp; ví dụ chỉ có các HTTP GET nên không vô hiệu hóa CSRF.

### 6.2. Chạy và kiểm tra

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Mặc định server chạy trên cổng 8080. Dùng các lệnh sau trong shell có `curl` thật (Windows PowerShell có thể cần `curl.exe`). Các comment `# ...` là **kết quả dự kiến**, phụ thuộc ứng dụng chạy nguyên trạng và không có cấu hình/port khác.

~~~bash
curl -s http://localhost:8080/public
# public OK

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/profile
# 401

curl -s -u alice:demo-pass http://localhost:8080/profile
# hello alice

curl -s -o /dev/null -w '%{http_code}\n' -u alice:demo-pass http://localhost:8080/admin
# 403

curl -s -u admin:demo-pass http://localhost:8080/admin
# admin OK

curl -s -o /dev/null -w '%{http_code}\n' -u user:anything http://localhost:8080/profile
# 401
~~~

Giải thích: user `user` không có trong custom `InMemoryUserDetailsManager`; mật khẩu cấu hình của Boot (nếu từng có) không còn điều khiển nguồn user này. Nếu bạn thấy startup log liên quan generated default password khi đã tạo cả hai bean như ví dụ, hãy kiểm tra bean registration và điều kiện configuration cụ thể thay vì kết luận theo một dấu hiệu.

### 6.3. Thí nghiệm phân biệt hai nhánh

**Thí nghiệm A — Giữ custom chain, bỏ bean custom user store.** Trong bản sao dự án demo, bỏ riêng method `@Bean UserDetailsService users(...)`; có thể giữ `PasswordEncoder`. Khi không có cơ chế xác thực nào khác làm Boot back off, Boot có thể cung cấp default user in-memory; policy `/public`, `/profile`, `/admin` vẫn xuất phát từ **custom `applicationChain`**. User mặc định mang `ROLE_USER` nên không đạt `hasRole("ADMIN")`.

**Thí nghiệm B — Giữ custom user store, bỏ bean custom chain.** Bỏ riêng method `@Bean SecurityFilterChain applicationChain(...)`. Khi không có chain khác, Boot có thể cung cấp **default chain**: cả `/public` lẫn `/profile`/`/admin` đều yêu cầu authentication, vì Boot không biết các rule `permitAll` và `hasRole` mà bạn vừa bỏ. Login bằng `alice` hoặc `admin` dựa trên custom user store; tên user mặc định `user` không xuất hiện.

**Thí nghiệm C — Bỏ cả hai bean tùy chỉnh.** Với cấu hình mặc định, Boot có thể cung cấp cả chain bảo vệ toàn bộ endpoint lẫn user mặc định. So sánh log và HTTP status của từng thí nghiệm để xác nhận cái gì đã thay đổi.

Chạy các thí nghiệm bằng **cách thay đổi code, build và khởi động lại**, không xóa bean khỏi một ứng dụng đang chạy rồi mong auto-configuration tái đánh giá ngay trong mỗi request. Các thí nghiệm A/B là biến thể riêng của ví dụ hoàn chỉnh, **không đồng thời là cấu hình của một project**.

## 7. Có nhiều SecurityFilterChain: Boot không tự thêm fallback

Một lỗi tinh vi là tự khai báo chain chỉ khớp `/api/**` rồi cho rằng các URL khác vẫn do chain mặc định của Boot bảo vệ. Trên Servlet stack, một khi ứng dụng cung cấp `SecurityFilterChain`, không nên trông chờ Boot tạo thêm default chain để bảo vệ các URL còn lại.

Ví dụ **sai khi muốn bảo vệ tất cả endpoint**:

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

Bean này chỉ giới hạn chain trong `/api/**`. Nếu không có chain khác khớp `/profile`, request đến `/profile` có thể đi qua ứng dụng **mà không nhận các bảo vệ của Spring Security filter chain**; đây là lỗi bao phủ vùng URL. Không sửa bằng `requestMatchers("/**")` *ở bên trong chain chỉ khớp `/api/**`*, vì matcher cấp chain đã loại URL khác từ trước.

Một phương án là cung cấp **hai chain** với thứ tự rõ ràng:

~~~java
@Configuration
class MultiChainSecurity {

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
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Đoạn này minh họa **một cấu hình thay thế** cho `SecurityConfig` ở phần 6; để đưa vào project Java cần bổ sung các import tương ứng (`@Configuration`, `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`), không khai báo cạnh `applicationChain` mà không thiết kế thứ tự. Mỗi request được `FilterChainProxy` chọn **chain khớp đầu tiên**: `/api/**` dùng chain API, còn lại vào fallback. `securityMatcher(...)` xác định chain áp dụng cho request nào; `requestMatchers(...)` trong `authorizeHttpRequests` quyết định quyền **bên trong chain ấy**.

Trước khi sử dụng nhiều chain, vẽ bản đồ URL: API, web pages, static assets, login, error, management/Actuator endpoints. Bảo đảm các endpoint cần bảo vệ khớp một chain dự kiến. Nếu dùng Actuator, cần hiểu chính sách bảo mật endpoint quản trị và những phần auto-configuration nào lùi lại khi bạn tự cung cấp chain.

## 8. Không nhầm các dạng cấu hình

| Cách cấu hình | Quyết định chủ yếu | Giới hạn cần nhớ |
| --- | --- | --- |
| Thêm `spring-boot-starter-security` | Đưa Spring Security vào classpath, kích hoạt điều kiện auto-config của Boot | Không tạo user/domain policy cụ thể của ứng dụng |
| `spring.security.user.*` | Điều chỉnh user in-memory mặc định của Boot khi nhánh đó hoạt động | Không khai báo URL rules và không điều khiển custom user store |
| `@Bean SecurityFilterChain` | Quy tắc HTTP request: URL, authentication/authorization, CSRF, form/basic, v.v. | Làm Boot không tạo default HTTP chain; ứng dụng chịu trách nhiệm bao phủ |
| `@Bean UserDetailsService` | Cách tải user và credentials cho luồng username/password | Không tự thay đổi `permitAll`, `hasRole` và mọi HTTP matcher |
| `@Bean AuthenticationProvider` | Cách xác minh credentials cụ thể | Không thay thế việc bảo vệ URL |
| `@Bean AuthenticationManager` | Điều phối authentication theo cơ chế ứng dụng | Không phải định nghĩa trực tiếp mọi HTTP authorization rule |
| `@EnableMethodSecurity` + `@PreAuthorize` | Quyền ở cấp method/service | Không tự bật chỉ vì thêm starter; không thay thế HTTP policy |
| `@EnableWebSecurity` | Bật cấu hình Spring Security web qua annotation trong các ứng dụng cần | Spring Boot Servlet thông dụng đã thiết lập cơ chế web security khi starter và auto-config phù hợp; thường chỉ cần `SecurityFilterChain` bean để tùy chỉnh |

`@EnableMethodSecurity` là lựa chọn riêng cho method security. Có thể dùng `@PreAuthorize("hasRole('ADMIN')")` trên service để bảo vệ hành động nghiệp vụ, nhưng nó **không phải cách thay thế** cho endpoint matcher. Ngược lại, `hasRole("ADMIN")` trong HTTP chain không tự kiểm tra ownership của từng đơn hàng trong database.

Đừng mang công thức cũ dựa trên `WebSecurityConfigurerAdapter` vào dự án Spring Security 6/Spring Boot 3; Spring Security hiện đại ưu tiên mô hình bean `SecurityFilterChain`.

## 9. Cách xác định cấu hình thực tế đang chạy

### Kiểm tra 1 — Tìm bean, không suy từ tên file

Tìm `@Bean SecurityFilterChain`, `@Bean UserDetailsService` và các bean `AuthenticationProvider`/`AuthenticationManager` trong ứng dụng và thư viện đi kèm. Kiểm tra package chứa `@Configuration` có nằm trong vùng component scan của `@SpringBootApplication` hay không. Nếu lớp cấu hình không được quét, bean mong muốn có thể không tồn tại và Boot áp dụng default.

### Kiểm tra 2 — Xem Condition Evaluation Report

Bật chế độ debug của Spring Boot trong môi trường phát triển:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Boot in báo cáo các điều kiện auto-configuration được áp dụng hoặc không được áp dụng. Tìm các nhóm liên quan `SecurityAutoConfiguration`, `SpringBootWebSecurityConfiguration` và `UserDetailsServiceAutoConfiguration`. Tên và thông tin điều kiện có thể khác theo bản Boot. Báo cáo trả lời **vì sao một bean mặc định được cân nhắc hoặc bị nhường chỗ**; không trực tiếp chứng minh một endpoint cụ thể đã được bảo vệ tốt.

Nếu có Spring Boot Actuator và endpoint `/actuator/conditions` đã được bật/phơi bày theo cấu hình, có thể xem condition report qua đó. Không công khai endpoint quản trị hoặc thông tin cấu hình nhạy cảm cho người dùng không được phép.

### Kiểm tra 3 — Xem chain và request ở Spring Security

Trong local development, có thể bật:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Dùng log để quan sát request, filter chain và một số quyết định bảo mật. Khi thật sự cần phân tích rất sâu, `TRACE` cung cấp nhiều thông tin hơn nhưng cũng gây nhiễu. Không log credentials, tokens hay dữ liệu bí mật; tránh để debug security hoạt động tùy tiện trên production.

**Phân biệt hai câu hỏi khi debug:**

- **Boot có tạo bean default hay không?** → nhìn condition report và danh sách bean.
- **Request `GET /api/orders` đi qua chain nào và bị từ chối ở đâu?** → nhìn chain match, authentication/authorization log, status HTTP và controller/service trace.

### Kiểm tra 4 — Gọi endpoint với các danh tính khác nhau

Tạo bảng kiểm thử đơn giản: unauthenticated, role thường, role quản trị; với mỗi loại gọi URL public, URL cần login và URL admin. Chỉ cần một cấu hình sai cũng có thể khiến `/public` nhận 401 hoặc `/admin` nhận 200 cho người không đủ quyền. Đây là bằng chứng về **hành vi request-time**; bổ sung bằng đọc bean và condition report để tìm nguyên nhân.

## 10. Lỗi thường gặp và cách sửa

**Lỗi 1: “Đã khai báo SecurityFilterChain nên Boot không còn sinh password.”** Sai về mặt điều kiện. Default chain và default user là hai nhánh; cung cấp source danh tính hoặc provider phù hợp nếu muốn thay default user.

**Lỗi 2: “Thêm UserDetailsService thì endpoint sẽ tự public.”** Không. Boot có thể vẫn áp dụng HTTP chain mặc định `anyRequest().authenticated()`. Cần custom `SecurityFilterChain` nếu muốn `permitAll` hay chính sách role riêng.

**Lỗi 3: “Chỉ cần `spring.security.user.roles=ADMIN` là /admin tự được bảo vệ.”** Property ấy chỉ liên quan authority của default user. Quy tắc URL `/admin` phải được khai báo trong authorization policy; nếu default chain yêu cầu authentication cho mọi URL, role không được dùng để tách riêng endpoint.

**Lỗi 4: “Custom chain cho /api/** xong các URL khác sẽ vào default chain của Boot.”** Không bảo đảm; việc tạo bean chain đã làm Boot lùi lại ở chain mặc định. Cần fallback chain bao phủ phần còn lại khi phù hợp.

**Lỗi 5: “`permitAll` tương đương bỏ qua Spring Security.”** Không. Một request `permitAll` vẫn thuộc chain và có thể hưởng security headers cùng các filter cần thiết. Cơ chế bỏ qua filter chain hoàn toàn (như `web.ignoring()`) khác biệt về hậu quả.

**Lỗi 6: “Cứ thấy 401 nghĩa là Boot default chain đang chạy.”** 401 cũng có thể do custom chain sử dụng HTTP Basic/bearer hoặc các entry point khác. Xem matching chain và auto-config report; đừng suy từ status một mình.

**Lỗi 7: “Tùy chỉnh SecurityFilterChain bắt buộc phải tắt hết CSRF.”** Không. Các cấu hình mặc định khác của `HttpSecurity` còn tùy ứng dụng; với web sử dụng cookie, CSRF thường quan trọng. Ví dụ chỉ GET không đòi hỏi thay đổi cài đặt CSRF.

**Lỗi 8: “Có `@PreAuthorize` là tự chạy.”** Nếu chưa bật `@EnableMethodSecurity` hoặc lời gọi bỏ qua Spring proxy (self-invocation), bạn có thể không nhận hiệu quả như mong muốn. Kiểm tra method security riêng với HTTP policy.

**Lỗi 9: “Ứng dụng đã khai báo @Configuration mà Boot vẫn bỏ qua.”** Kiểm tra component scan, profile, conditional bean, cấu hình bị loại khỏi context và lỗi startup. Chỉ một file Java tồn tại trong project **chưa chắc** bean đã được tạo.

## 11. Câu hỏi tự kiểm tra

1. Ứng dụng có `SecurityFilterChain` riêng nhưng chưa có `UserDetailsService`/provider khác; tại sao vẫn có generated password?
   - Vì cấu hình user mặc định và HTTP chain mặc định độc lập; Boot có thể vẫn tạo user mặc định.
2. Ứng dụng chỉ thay `UserDetailsService`; tại sao `GET /public` vẫn trả 401?
   - Vì default HTTP chain có thể vẫn yêu cầu `authenticated()` cho mọi request. Tên đường dẫn “public” không tự tạo rule công khai.
3. Tại sao `securityMatcher("/api/**")` không đủ bảo vệ `/admin`?
   - Nó chỉ chọn chain cho đường dẫn `/api/**`. Phải có chain khác khớp `/admin` nếu endpoint cần Spring Security bảo vệ.
4. Lệnh nào giúp tìm lý do Boot tạo hay không tạo default bean?
   - Bật `--debug` của Boot và đọc **Condition Evaluation Report**; kết hợp kiểm tra bean thực tế.
5. Đâu là ranh giới giữa “startup auto-configuration” và “request authorization”?
   - Startup quyết định những bean/chains nào tồn tại; lúc có request, Spring Security chọn chain và kiểm tra danh tính/quyền theo các bean đó.

**Ghi nhớ:** Trong Spring Boot Servlet, hãy hỏi **“bean nào do Boot cung cấp, bean nào do ứng dụng cung cấp, và điều kiện nào làm Boot lùi lại?”** trước khi hỏi **“request đi qua chain nào, gặp rule nào?”**. Khi tách được hai thời điểm và hai nhánh (HTTP chain so với nguồn user), bạn sẽ hiểu phần lớn trường hợp tưởng như auto-configuration “tự ghi đè” cấu hình ứng dụng.