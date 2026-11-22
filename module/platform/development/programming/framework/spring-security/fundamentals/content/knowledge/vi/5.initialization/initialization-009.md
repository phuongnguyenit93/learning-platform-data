# Vai trò của cấu hình tự động và các điều kiện để cấu hình riêng có hiệu lực

Bạn tạo dự án Spring Boot, thêm `spring-boot-starter-security` rồi chạy ứng dụng. Đột nhiên một API trước đó trả `200 OK` lại yêu cầu đăng nhập. Bạn khai báo `SecurityFilterChain` để cho phép `/public/**`; yêu cầu bắt đầu hoạt động. Nhưng màn hình đăng nhập vẫn có một tài khoản thử nghiệm `user` do Spring Boot tạo, dù bạn đã “cấu hình Security riêng”.

Đây là tình huống rất tốt để hiểu **Spring Boot auto-configuration (cấu hình tự động)**: Boot đăng ký các bean mặc định **theo điều kiện**. Khi ứng dụng khai báo bean cùng vai trò phù hợp, *một phần* mặc định sẽ rút lui (*back off*). Điều đó không có nghĩa thêm một `@Configuration` bất kỳ là toàn bộ Spring Security mặc định biến mất.

Mục tiêu bài học: giải thích **Boot tự cấu hình những gì**, **điều kiện nào khiến cấu hình riêng thực sự được dùng**, **cách phân biệt cấu hình cho request với cấu hình tài khoản**, và **cách xác nhận cấu hình đang có hiệu lực bằng log, condition report và kiểm thử HTTP**.

Phạm vi chính là **Spring Boot servlet/Spring MVC + Spring Security**, với ví dụ Java 17 và Spring Boot 3.5.16. Các ý tưởng về điều kiện còn áp dụng cho Boot 4, nhưng tên lớp và cách tổ chức module auto-configuration có thể thay đổi giữa các major. Cuối bài có phần phân biệt WebFlux.

## 1. Auto-configuration của Spring Boot là gì?

Spring Boot không “đọc ý nghĩ” của ứng dụng. Nó quan sát **classpath**, **kiểu ứng dụng**, **các bean đã khai báo**, **thuộc tính cấu hình** và **những điều kiện khác** để quyết định có đăng ký bean mặc định hay không.

Ví dụ tổng quát:

~~~text
@SpringBootApplication
       |
       +--> kích hoạt @EnableAutoConfiguration
       |
       +--> tìm các auto-configuration có trên classpath
                 |
                 v
          Đánh giá @Conditional...
                 |
        +--------+---------+
        |                  |
  Điều kiện khớp      Không khớp
        |                  |
        v                  v
  Đăng ký bean         Bỏ qua cấu hình
  mặc định cần thiết   (không đăng ký bean đó)
        |
        v
  Spring ApplicationContext hoàn thiện
~~~

`@SpringBootApplication` kết hợp cấu hình ứng dụng, component scan và kích hoạt auto-configuration. Các cấu hình mặc định thường dùng những điều kiện như:

| Điều kiện | Nó hỏi điều gì? | Tình huống thường gặp |
| --- | --- | --- |
| `@ConditionalOnClass` | Có lớp/thư viện trên classpath? | Có lớp Spring Security để bật phần cấu hình bảo mật |
| `@ConditionalOnMissingBean` | Chưa có bean của một kiểu cần tìm? | Chưa có `SecurityFilterChain` riêng thì có thể thêm chain mặc định |
| `@ConditionalOnBean` | Đã có bean mà tính năng cần phụ thuộc? | Chỉ bổ sung một tính năng khi bean liên quan tồn tại |
| `@ConditionalOnWebApplication` | Ứng dụng là servlet, reactive hay một loại web thích hợp? | Servlet filter khác reactive web filter |
| `@ConditionalOnProperty` | Thuộc tính môi trường có giá trị phù hợp? | Một tính năng chỉ bật khi property thỏa điều kiện |
| `@ConditionalOnMissingClass` | Không có thư viện/lớp cụ thể? | Tránh cấu hình không phù hợp với một dependency khác |

Mỗi auto-configuration có thể có **nhiều điều kiện kết hợp**, và bean riêng của ứng dụng thường có thể khiến một nhánh mặc định rút lui. Đừng hiểu `@ConditionalOnMissingBean` là điều kiện luôn đúng nếu chưa thấy lớp đó trong file Java hiện tại: Spring kiểm tra **bean definitions trong ApplicationContext**, không chỉ tìm tên lớp bằng văn bản.

Một chi tiết nữa: điều kiện có thể nằm ở **cấp class** hoặc **cấp phương thức `@Bean`**. Nếu đặt ở class, cả nhóm bean trong cấu hình ấy có thể không được đăng ký; nếu đặt ở một phương thức, chỉ bean tương ứng bị bỏ qua. Do đó “auto-configuration bị tắt” cần nói rõ là **phần nào**.

### Auto-configuration khác với Spring Security framework defaults

Có hai lớp cần phân biệt:

1. **Spring Boot auto-configuration** quyết định **tạo những bean nào** trong ứng dụng, dựa trên điều kiện.
2. **Spring Security** triển khai filter chain, authentication và authorization khi các bean được tạo, với những mặc định bên trong `HttpSecurity` và các configurer.

Thêm một `SecurityFilterChain` tự định nghĩa là cách thay *cấu hình web security mặc định của Boot*. Nhưng bản thân Spring Security vẫn hoạt động; các filter cần thiết vẫn được dùng theo cấu hình `HttpSecurity`, và những feature bạn chưa cấu hình có thể còn mặc định tương ứng. `http.build()` tạo một chain có thật, không phải “tắt Spring Security”.

## 2. Khi vừa thêm starter-security, Boot cấu hình gì?

Ở một ứng dụng **Spring Boot 3.5 servlet** thông thường có `spring-boot-starter-web` và `spring-boot-starter-security`, chưa tự đăng ký các bean bảo mật thay thế:

- Các request web được yêu cầu xác thực theo chính sách mặc định.
- Tùy kiểu request và `Accept` header, client có thể gặp trang login hoặc HTTP Basic challenge.
- Boot có thể tạo `UserDetailsService` lưu trong bộ nhớ với một tài khoản thử nghiệm tên `user`, mật khẩu ngẫu nhiên được thông báo trong log khi khởi động.
- Boot cũng có thể cung cấp `DefaultAuthenticationEventPublisher` nếu chưa có bean tương ứng.
- Những endpoint như `/error` và endpoints của Actuator cũng cần được xét trong chính sách bảo mật, không mặc nhiên là “công khai”.

Những hành vi trên là **điểm khởi đầu cho development**. Tài khoản và mật khẩu ngẫu nhiên do Boot tạo không phải cách xây dựng hệ thống tài khoản production. Khi bước vào ứng dụng thật, cần dùng nguồn người dùng, provider, secrets và chính sách rõ ràng.

Trong Boot 3.5, tài liệu mô tả các cấu hình liên quan gồm `SecurityAutoConfiguration`, `SpringBootWebSecurityConfiguration` và `UserDetailsServiceAutoConfiguration`. Ở Boot 4, mô-đun và một số tên lớp thay đổi (ví dụ `ServletWebSecurityAutoConfiguration`); nguyên tắc **back off theo loại bean và điều kiện** vẫn là chìa khóa.

### “Mặc định bảo vệ mọi URL” không đồng nghĩa có controller cho mọi URL

Boot không tự tạo route `GET /orders` hay tài khoản nghiệp vụ. Nó đặt một lớp security bao quanh những request tới ứng dụng. Vì vậy một URL không có controller có thể nhận `401`/redirect trước khi đến xử lý `404`, tùy filter chain và client. Đừng từ mã status đó suy ra chắc chắn controller đã tồn tại hoặc vắng mặt.

## 3. Hai nhánh cấu hình phải tách bạch: web policy và user store

Điểm quan trọng nhất trong bài là **`SecurityFilterChain` và `UserDetailsService` đáp ứng hai nhiệm vụ độc lập**.

| Bạn thêm bean gì? | Ảnh hưởng trực tiếp đến mặc định Boot | Điều KHÔNG nên suy ra |
| --- | --- | --- |
| `SecurityFilterChain` | Cấu hình chain bảo vệ web mặc định của Boot sẽ nhường chỗ cho chain do bạn định nghĩa | Không tự xóa tài khoản thử nghiệm `user` |
| `UserDetailsService` | `UserDetailsService` trong bộ nhớ do Boot tạo theo mặc định sẽ nhường chỗ cho bean của bạn | Không tự thay chính sách URL của filter chain |
| `AuthenticationProvider` hoặc `AuthenticationManager` phù hợp | Cũng có thể khiến `UserDetailsService` mặc định của Boot không được tạo theo điều kiện tương ứng | Không tự mở hoặc khóa mọi endpoint theo ý muốn |
| `AuthenticationEventPublisher` | Cho phép thay bean publisher mặc định liên quan đến sự kiện xác thực | Không tự thay filter chain hoặc nguồn người dùng |
| `PasswordEncoder` | Cung cấp cách encode/matches mật khẩu cho những thành phần được cấu hình dùng nó | Không mặc nhiên thay chain, tài khoản hay toàn bộ provider |
| `@EnableMethodSecurity` | Kích hoạt cơ chế kiểm tra bảo mật tại method theo cấu hình | Không tự thay tất cả điều kiện lọc URL hoặc tải người dùng |

Tài liệu Boot 3.5 mô tả rõ: khai báo `SecurityFilterChain` tùy biến làm Boot **không tạo web security default chain**, còn `UserDetailsService` mặc định chỉ rút lui khi có **loại bean cho xác thực** tương ứng hoặc các điều kiện classpath khác (ví dụ một số module OAuth2/SAML).

Sơ đồ tư duy:

~~~text
                       ApplicationContext
                               |
             +-----------------+------------------+
             |                                    |
     Nhánh web security                    Nhánh user/authentication
             |                                    |
Có SecurityFilterChain @Bean?        Có UserDetailsService/Provider/Manager?
     /               \                           /            \
   Có                Không                       Có            Không
   |                   |                         |                |
Dùng chain của     Boot có thể tạo       Không tạo user       Boot có thể tạo
ứng dụng            default chain         mặc định              user mặc định*
   |                   |                         |                |
   +--------- lọc HTTP request ------------------+------ xác thực tài khoản
~~~

`*` Các điều kiện bổ sung (như module OAuth2 client/resource server/SAML trên classpath và phiên bản Spring Boot) cũng có thể làm cấu hình user mặc định rút lui. Không dùng sơ đồ như một thuật toán tuyệt đối trong mọi stack.

**Trường hợp dễ gây nhầm:** bạn đã tự đặt `@Bean SecurityFilterChain`, nhưng khi khởi động vẫn thấy một mật khẩu ngẫu nhiên trong log. Đó **không có nghĩa** custom chain bị bỏ qua. Có thể chain riêng đang hoạt động, còn Boot vẫn tạo tài khoản thử nghiệm vì bạn chưa cung cấp nguồn xác thực. Hãy quan sát hai nhánh riêng.

## 4. Điều kiện để một cấu hình riêng thực sự có hiệu lực

Chỉ viết class cấu hình chưa đủ. Một bean cần **thực sự được đăng ký và được thành phần sử dụng nó tham chiếu**.

### 4.1. Có dependency phù hợp

Một dự án servlet dùng Spring Security cần các module phù hợp trên classpath. Với Spring Boot, thêm starter rồi để BOM quản lý các phiên bản:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
~~~

Không ghi thêm một phiên bản `spring-security-web` tùy ý khi Boot đang quản lý các module, vì có thể dẫn đến classpath không tương thích.

### 4.2. Cấu hình phải thuộc ApplicationContext

Class chứa `@Configuration` có thể được Spring nhận ra nhờ component scanning hoặc `@Import`. Ví dụ main class ở `com.example.app` sẽ quét các package con như `com.example.app.security`, nhưng không mặc định quét package nằm ngoài cây đó. Đặt class ở nơi không được scan khiến method `@Bean` không hề được gọi, dù file Java đã biên dịch.

Nếu dùng `@Bean`, **giá trị trả về** phải có loại mà điều kiện của Boot và consumer mong đợi. Với servlet security, chữ ký điển hình:

~~~java
@Bean
SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(a -> a.anyRequest().authenticated())
            .build();
}
~~~

Đây là **mảnh mã trong một `@Configuration` hợp lệ** và chỉ minh họa loại bean; không phải một file Java độc lập.

### 4.3. Có điều kiện được thỏa

Không phải một bean được khai báo bằng `@Conditional...` sẽ xuất hiện trong mọi hoàn cảnh. Điều kiện có thể không khớp vì thiếu class, ứng dụng không phải servlet, property sai, hoặc đã có bean thay thế. Với cấu hình bảo mật, **đừng “sửa” bằng cách loại bỏ điều kiện một cách mù quáng**; hãy đọc condition report trước.

### 4.4. Đúng mô hình servlet hay reactive

- Servlet MVC dùng `HttpSecurity` và bean `SecurityFilterChain` (`jakarta.servlet.Filter` đi qua Spring Security `FilterChainProxy`).
- WebFlux dùng `ServerHttpSecurity` và bean `SecurityWebFilterChain`; mặc định liên quan `ReactiveUserDetailsService`.
- Các loại bean này **không thay thế lẫn nhau**. Một `SecurityFilterChain` servlet không làm biến mất mặc định bảo vệ WebFlux theo cùng cách.

Khi lỡ thêm đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot có logic quyết định kiểu ứng dụng; phải xem kiểu runtime thực tế, không đoán từ một dependency đơn lẻ.

### 4.5. Có đúng thứ tự chain và phạm vi URL

Khi có nhiều `SecurityFilterChain`, bean tồn tại chưa có nghĩa mọi request đi qua nó. `FilterChainProxy` chọn **chain đầu tiên khớp request** theo thứ tự; trong chain đó, các luật `requestMatchers` mới xét quyền truy cập.

Nếu một chain bị giới hạn vào `/api/**`, nó không xử lý `/admin/**` hoặc `/login` nếu các đường dẫn ấy không khớp. Cần chain còn lại bao phủ các đường dẫn khác, thường là fallback `anyRequest()`.

### 4.6. Bean phải được dùng bởi đúng quá trình xác thực

Một `PasswordEncoder` bean không bảo đảm tự động đăng nhập bằng DB nếu ứng dụng chưa có `UserDetailsService`/provider tương ứng. Một `AuthenticationProvider` tùy chỉnh không bảo đảm được gọi nếu bạn tạo `AuthenticationManager` khác và không đưa provider vào đó. Cần xem đồ thị bean và luồng thực tế, thay vì dựa vào số lượng `@Bean` trong source.

## 5. Ví dụ Java 17+ và Spring Boot 3.5: tùy chỉnh cả web policy lẫn user store

Ví dụ dưới đây có thể khởi động bằng Maven, không cần database. Nó cho thấy **hai loại bean tự định nghĩa**:

- `SecurityFilterChain` định nghĩa endpoint công khai, endpoint cần login và endpoint yêu cầu admin.
- `UserDetailsService` định nghĩa người dùng thử nghiệm riêng, để Boot không tạo `user` ngẫu nhiên.
- `PasswordEncoder` mã hóa mật khẩu thử nghiệm trong memory.

Phiên bản tham chiếu của ví dụ là **Spring Boot 3.5.16** (Spring Security do Boot BOM quản lý), JDK **17+** và Maven phù hợp. Tài khoản/mật khẩu đặt trong code chỉ phục vụ **bài thực hành local**, không dùng trong production.

### 5.1. Tạo project

Cấu trúc:

~~~text
auto-security-lab/
  pom.xml
  src/main/java/com/example/lab/AutoSecurityLabApplication.java
  src/main/java/com/example/lab/SecurityConfiguration.java
~~~

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
    <artifactId>auto-security-lab</artifactId>
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

Dependency Security không ghi version riêng; Boot parent quản lý các module liên quan.

Tệp `src/main/java/com/example/lab/AutoSecurityLabApplication.java`:

~~~java
package com.example.lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class AutoSecurityLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AutoSecurityLabApplication.class, args);
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "pong";
    }

    @GetMapping("/private/whoami")
    public String whoami(Authentication authentication) {
        return authentication.getName();
    }

    @GetMapping("/admin/secret")
    public String adminOnly() {
        return "admin-only";
    }
}
~~~

Tệp `src/main/java/com/example/lab/SecurityConfiguration.java`:

~~~java
package com.example.lab;

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
    SecurityFilterChain appSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/public/**").permitAll()
                    .requestMatchers("/admin/**").hasRole("ADMIN")
                    .anyRequest().authenticated()
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
            User.withUsername("learner")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
~~~

Những gì code thực sự thiết lập:

1. Spring Boot tìm thấy hai class vì chúng cùng package `com.example.lab`; `@SpringBootApplication` kích hoạt component scan và auto-configuration.
2. Bean `appSecurity` có kiểu `SecurityFilterChain`, nên Boot bỏ web security chain mặc định để ứng dụng kiểm soát rule.
3. Bean `users` có kiểu `UserDetailsService`, nên Boot bỏ user thử nghiệm `user` mặc định của nó.
4. Bean `passwordEncoder` dùng bcrypt cho người dùng thử nghiệm.
5. `httpBasic` cho phép thử bằng `curl -u`; ứng dụng không cấu hình form login trong chain này.
6. Người dùng `learner` chỉ có `ROLE_USER`, nên **không đủ** `ROLE_ADMIN`.

Đối với ứng dụng thật, không hardcode mật khẩu, không lưu người dùng production bằng in-memory demo và cần chính sách tài khoản, session, audit và các hình thức xác thực phù hợp.

### 5.2. Chạy và kiểm tra response

Với JDK 17 trở lên, Maven và mạng tới Maven Central ở lần lấy dependency đầu:

~~~bash
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Giữ ứng dụng chạy rồi mở terminal khác. Với shell bash, thử:

~~~bash
curl -s http://localhost:8080/public/ping
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/private/whoami
curl -s -u learner:demo-password http://localhost:8080/private/whoami
curl -s -u learner:demo-password -o /dev/null -w '%{http_code}\n' http://localhost:8080/admin/secret
~~~

Đầu ra của bốn lệnh theo thứ tự (mỗi lệnh in một dòng):

~~~text
pong
401
learner
403
~~~

Trên Windows PowerShell, dùng `curl.exe` khi cần tránh alias `curl` của hệ thống. `-u learner:demo-password` là credentials **chỉ phục vụ local demo** và có thể xuất hiện trong lịch sử shell; không dùng cách này với mật khẩu thật. Có thể dùng HTTP client của IDE thay vì lệnh chứa secret.

Vì sao các mã phản hồi như trên?

- `/public/ping` khớp `permitAll()` nên 200 + body `pong`.
- `/private/whoami` không có credentials, gặp `authenticated()` và `httpBasic` nên thường là 401.
- Cũng endpoint ấy với tài khoản `learner` hợp lệ: Spring Security đưa `Authentication` đến controller; `getName()` trả `learner`.
- `/admin/secret` với `learner` đã xác thực nhưng thiếu `ROLE_ADMIN`, nên 403.

Cấu hình và đầu ra trên là **kết quả theo logic API nêu trong ví dụ**; khi đổi cổng, context path, chain, entry point hoặc web stack, phải kiểm tra lại. Không suy ra mọi hệ thống đều trả cùng một response body cho 401/403.

## 6. Thử thay đổi một bean để thấy auto-configuration rút lui theo từng phần

Trong project thực hành phía trên, có thể làm các thí nghiệm riêng (mỗi lần sửa một phần rồi khởi động lại).

| Thí nghiệm | Hiệu ứng cần quan sát | Vì sao |
| --- | --- | --- |
| Giữ cả ba bean như ban đầu | Rule riêng và user `learner` có hiệu lực | Hai nhánh mặc định đều nhường chỗ |
| Bỏ riêng phương thức `users(...)` | Boot có thể tạo user `user` mặc định và password ngẫu nhiên | Không còn `UserDetailsService` riêng/alternative authentication |
| Giữ `users(...)`, bỏ riêng `appSecurity(...)` | Boot có thể tạo chain bảo vệ web mặc định | Không còn `SecurityFilterChain` do ứng dụng định nghĩa |
| Chỉ thêm `PasswordEncoder`, không có user store riêng | Không tự tạo user nghiệp vụ hay custom rule | Encoder không thay nguồn user/authorization |
| Di chuyển `SecurityConfiguration` ra ngoài vùng component scan, không `@Import` | Những bean cấu hình riêng không được đăng ký | Spring chưa nhận class ấy trong context |
| Thêm chain chỉ khớp `/api/**` nhưng không có fallback | Những path ngoài `/api/**` có thể không đi qua Spring Security | Không có matching `SecurityFilterChain` cho phần URL còn lại |

Bảng dùng từ “có thể” với các mặc định Boot vì classpath, property và những bean khác của ứng dụng cũng ảnh hưởng điều kiện. Khi thí nghiệm, hãy ghi nhận **những bean được tạo thực tế** và response HTTP.

Lưu ý: **không cần thêm `@EnableWebSecurity` như phản xạ mặc định** khi Boot đã tích hợp Spring Security. Nhiều ví dụ standalone của Spring Security có annotation này; trong ứng dụng Boot, hãy hiểu vì sao cần trước khi thêm. Nó không thay cho việc đặt `SecurityFilterChain` ở package được scan.

## 7. Nhiều SecurityFilterChain: có bean không có nghĩa mọi URL đều khớp

Nếu cần cách đăng nhập khác nhau cho API và trang web, có thể dùng nhiều chain:

~~~java
// Mảnh cấu hình trong class @Configuration của ứng dụng servlet.
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Các import bổ sung gồm `org.springframework.core.annotation.Order`. Đây là **mảnh cấu hình minh họa**, chưa đầy đủ thành class/các user providers để chạy độc lập.

Cách Spring Security chọn:

~~~text
GET /api/orders
     |
     v
FilterChainProxy
     |
  @Order(1) securityMatcher("/api/**") ? -- Có --> dùng apiSecurity
     |
    Không
     v
  @Order(2) matcher mặc định mọi request ? -- Có --> dùng webSecurity
     |
    Không
     v
  Không có Spring Security chain khớp request
~~~

**`securityMatcher` và `requestMatchers` không cùng nhiệm vụ**:

- `http.securityMatcher("/api/**")` quyết định **toàn bộ SecurityFilterChain có áp dụng** cho URL không.
- `http.authorizeHttpRequests(...requestMatchers(...))` quyết định **quyền truy cập bên trong chain đã chọn**.
- `anyRequest()` ở chain đầu tiên chỉ có nghĩa “mọi URL mà chain đầu tiên khớp”; nó không bảo vệ toàn bộ website nếu `securityMatcher` đã giới hạn phạm vi.

Spring Security chọn **chain đầu tiên khớp**, không gộp mọi filter của hai chain lại thành một. `@Order(1)` ưu tiên hơn `@Order(2)`; cần sắp xếp từ điều kiện cụ thể đến tổng quát.

Nếu bỏ chain thứ hai, `/public/ping` và `/admin/secret` sẽ nằm ngoài `/api/**` và có thể không qua Spring Security. Đó là một lỗi cấu hình nguy hiểm dù code có `anyRequest().authenticated()` ở chain API. Vì vậy thường cần một chain **không giới hạn `securityMatcher`** làm fallback, bao phủ mọi đường còn lại.

Một trường hợp tinh tế: `formLogin()` có thể đăng ký endpoint xử lý đăng nhập như `POST /login`. Nếu bạn đặt form login bên trong chain chỉ khớp `/api/**`, endpoint `/login` bên ngoài phạm vi không được chain ấy phục vụ. Phải bảo đảm URL xử lý login nằm trong chain phù hợp hoặc dùng một chain riêng bao phủ nó.

## 8. Khi có Actuator, phải cấu hình cả endpoint quản trị

Spring Boot Actuator mang các endpoint như `/actuator/health`, `/actuator/metrics`, `/actuator/beans`, `/actuator/conditions`. Một số endpoint chứa thông tin vận hành nhạy cảm và **không nên mở công khai**.

Điểm dễ nhầm: **khi ứng dụng tự cung cấp `SecurityFilterChain`, cấu hình bảo vệ Actuator mặc định từ Boot cũng có thể rút lui**. Khi đó các rule của bạn phải xét cả Actuator. Không chỉ viết:

~~~java
// KHÔNG đủ để bảo vệ toàn bộ ứng dụng nếu dùng sai phạm vi.
.requestMatchers("/api/**").authenticated()
.anyRequest().permitAll()
~~~

Đoạn trên sẽ cho phép tất cả những đường không thuộc `/api/**` ở chain khớp, có thể bao gồm endpoint vận hành khi đã được expose.

Cách thiết kế an toàn hơn: quyết định rõ endpoint nào được expose/được phép, dùng matcher do Boot cung cấp khi phù hợp, ví dụ `EndpointRequest`. Mảnh cấu hình:

~~~java
// Cần import: org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest
// Yêu cầu dependency actuator và @Configuration servlet phù hợp.
http.authorizeHttpRequests(auth -> auth
        .requestMatchers(EndpointRequest.to("health")).permitAll()
        .requestMatchers(EndpointRequest.toAnyEndpoint()).hasRole("OPS")
        .anyRequest().authenticated());
~~~

**Lưu ý:** `EndpointRequest` chỉ có khi dùng phần Actuator tương ứng; đoạn này là fragment, không nằm trong project demo cơ bản. Phải có `ROLE_OPS` được cấp từ nguồn tin cậy nếu dùng ví dụ trên.

Việc endpoint **có sẵn/được expose** khác với việc **được phép truy cập**. Spring Boot có những thiết lập Actuator quyết định endpoint nào được expose qua HTTP; Spring Security tiếp tục kiểm tra những request tới endpoint đã mở. Dùng cấu hình least privilege và bảo vệ endpoint `conditions`, `env`, `beans` khỏi truy cập không được phép.

## 9. Cách tìm lý do auto-configuration có hoặc không có hiệu lực

Khi thấy behavior không như dự đoán, hãy tìm **bằng chứng chạy thực tế**.

### 9.1. Xem Condition Evaluation Report

Có thể chạy Boot với tham số `--debug`:

~~~bash
java -jar target/auto-security-lab-0.0.1-SNAPSHOT.jar --debug
~~~

Hoặc với Maven Boot plugin:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Boot xuất báo cáo điều kiện (*conditions report*) khi bật debug. Các nhóm thông tin thường gồm:

| Nhóm báo cáo | Ý nghĩa |
| --- | --- |
| Positive matches | Cấu hình/nhánh có điều kiện thỏa |
| Negative matches | Điều kiện không thỏa, kèm lý do |
| Unconditional classes | Một số lớp cấu hình không cần điều kiện tương ứng |
| Exclusions | Các cấu hình đã bị yêu cầu loại trừ |

Tìm tên auto-configuration liên quan Security, `SecurityFilterChain`, `UserDetailsService` hoặc nhánh điều kiện `@ConditionalOnMissingBean`. Nhiều bản Boot hiển thị lý do cụ thể như đã tìm thấy một bean do ứng dụng cung cấp. Không nhìn thấy log mật khẩu ngẫu nhiên **không đủ** để kết luận user mặc định không tồn tại: mức log và property có thể ảnh hưởng hiển thị.

Với Actuator được cài và đã **bảo vệ đúng cách**, endpoint `conditions` cũng có thể cung cấp điều kiện cấu hình. Không expose công khai endpoint này chỉ để debug.

### 9.2. Kiểm tra danh sách bean

Trong môi trường test, có thể đếm các bean theo kiểu:

~~~java
// Mảnh mã kiểm tra trong một context/test có sẵn.
String[] chains = context.getBeanNamesForType(SecurityFilterChain.class);
String[] users = context.getBeanNamesForType(UserDetailsService.class);
System.out.println("SecurityFilterChain beans: " + chains.length);
System.out.println("UserDetailsService beans: " + users.length);
~~~

Tuy nhiên **đếm bean vẫn chưa chứng minh hành vi đúng**. Một ứng dụng có thể có nhiều chain nhưng thứ tự sai, một chain không khớp URL cần bảo vệ, hoặc một bean provider được đăng ký nhưng không được dùng trong cấu hình manager thực tế. Kết hợp danh sách bean với kiểm tra request thực tế và chính sách phân quyền.

### 9.3. Bật log security một cách có kiểm soát

Để chẩn đoán filter chain và các quyết định request trong môi trường phát triển:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Tăng lên `TRACE` chỉ khi thật cần, trong môi trường an toàn, rồi tắt sau kiểm tra. Log bảo mật có thể chứa thông tin về các URL và trạng thái xác thực; không đẩy log gỡ lỗi nhạy cảm vào nơi nhiều người có thể truy cập.

### 9.4. Kiểm tra package scan, profile và dependencies

Khi tự tạo `@Bean` nhưng Boot vẫn dùng cấu hình mặc định, lần lượt kiểm tra:

1. Class `@Configuration` có nằm dưới package main application hoặc được `@Import` chưa?
2. Có `@Profile` và active profile đúng không?
3. Có `@Conditional...` bị false không?
4. Có bean cùng tên/kiểu khác làm logic phức tạp không?
5. Ứng dụng thực sự chạy Web MVC/Servlet hay WebFlux?
6. Build đã compile lại mã mới và chạy đúng artifact/port chưa?
7. `spring.autoconfigure.exclude` hoặc `@SpringBootApplication(exclude=...)` có loại trừ cấu hình liên quan không?
8. Startup report cho thấy bean nào được tạo và vì sao?

Không nên “sửa” bằng cách thêm liên tục `@EnableWebSecurity`, `@Order`, `@Primary`, hoặc vô hiệu hóa CSRF mà chưa xác định nguyên nhân thật.

## 10. Trường hợp không dùng MVC: WebFlux có loại bean khác

Với ứng dụng **reactive WebFlux**, Spring Security có các kiểu khác:

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| Servlet `FilterChainProxy` | Reactive `WebFilterChainProxy` |
| `authorizeHttpRequests` | `authorizeExchange` |

Ví dụ **mảnh cấu hình** cho WebFlux, yêu cầu starter và dependencies reactive:

~~~java
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

Không dùng `SecurityFilterChain` servlet để suy luận rằng auto-configuration WebFlux mặc định sẽ rút lui. Tương tự, `ReactiveUserDetailsService` liên quan nguồn user trong reactive stack. Khi dùng cả MVC lẫn WebFlux trong build, xem kiểu web application mà Boot đã chọn và quy tắc tương ứng.

## 11. Các lỗi lập luận thường gặp

1. **“Thêm starter-security là Boot chặn mọi URL mãi mãi.”** Mặc định có thể được thay bằng một `SecurityFilterChain` hợp lệ của ứng dụng.
2. **“Tôi đã khai báo SecurityFilterChain nên tài khoản `user` mặc định biến mất.”** Không tự động; nguồn người dùng là nhánh auto-configuration riêng.
3. **“Tôi khai báo UserDetailsService nên endpoint `/admin` được bảo vệ theo role.”** User store không tự tạo chính sách URL mong muốn; cần chain phù hợp.
4. **“Tạo một PasswordEncoder bean là đã xác thực bằng database.”** Không; cần nguồn user và provider/manager thực sự sử dụng encoder.
5. **“Chỉ viết file `SecurityConfiguration.java` là Spring tự thấy.”** Nó phải được scan/import và bean phải đăng ký thành công.
6. **“Một chain có `anyRequest().authenticated()` sẽ bảo vệ toàn bộ app.”** Chưa chắc khi chain bị giới hạn bằng `securityMatcher("/api/**")` và không có fallback.
7. **“Hai SecurityFilterChain sẽ cùng áp dụng cho mỗi request.”** Không; `FilterChainProxy` chọn chain đầu tiên khớp.
8. **“`securityMatcher` giống `requestMatchers`.”** Một cái chọn chain; cái kia chọn rule trong chain.
9. **“Tự thêm rule web không ảnh hưởng Actuator.”** Có thể Boot đã nhường cấu hình mặc định; ứng dụng phải bảo vệ cả endpoint quản trị.
10. **“`permitAll` là cách tắt toàn bộ filter.”** Không; request đi qua chain vẫn chịu các cơ chế filter thích hợp. `permitAll` chỉ ảnh hưởng quyết định quyền truy cập của rule tương ứng.
11. **“Biến mất log mật khẩu là chứng minh custom config có hiệu lực.”** Không; cần đọc bean/condition report và thử request.
12. **“Bật `@EnableMethodSecurity` thì không cần kiểm tra URL và quyền dữ liệu.”** Method security là một lớp bổ sung; phải kiểm tra đường gọi và chính sách truy cập.
13. **“Tắt toàn bộ auto-configuration là cách tốt nhất để kiểm soát.”** Thường không cần; nên ghi đè chính xác phần ứng dụng muốn tự quản lý.
14. **“Custom config làm Spring Security bị tắt.”** Sai: nó chỉ thay phần mặc định đã chọn và vẫn cần chính sách bảo vệ đúng.

## 12. Checklist triển khai cấu hình riêng an toàn

Trước khi công nhận cấu hình là có hiệu lực, hãy xác minh:

- [ ] Dependency Spring Security có trên classpath và version do Spring Boot quản lý phù hợp.
- [ ] Main app có `@SpringBootApplication` và class `@Configuration` được scan/import.
- [ ] Bean trả đúng loại `SecurityFilterChain` (servlet) hoặc `SecurityWebFilterChain` (reactive).
- [ ] Có một chain phù hợp với mỗi nhóm URL cần bảo vệ, và fallback cho đường chưa khớp.
- [ ] Các chain được sắp xếp đúng với `@Order`; chain cụ thể trước, tổng quát sau.
- [ ] Quy tắc `requestMatchers` phù hợp với HTTP method và tài nguyên cần bảo vệ.
- [ ] Nguồn `UserDetailsService`/provider/manager phù hợp; không dùng tài khoản mẫu của Boot trong production.
- [ ] `PasswordEncoder` được dùng nhất quán cho dữ liệu mật khẩu.
- [ ] Những endpoint Actuator có rủi ro đã được hạn chế exposure và authorization.
- [ ] CSRF, session, CORS, login/logout và headers được xét đúng loại client; không disable bừa vì lỗi 403.
- [ ] Conditions report xác nhận auto-config nào khớp, không khớp và tại sao.
- [ ] Đã thử request công khai, request chưa xác thực, đã xác thực thiếu quyền và đủ quyền.
- [ ] Đã kiểm thử cả các đường gọi service, method security và quyền trên dữ liệu nếu ứng dụng có.

## 13. Tự kiểm tra kiến thức

**Câu 1.** Bạn có `@Bean SecurityFilterChain` nhưng ứng dụng vẫn in mật khẩu ngẫu nhiên cho tài khoản `user`. Cấu hình riêng đã thất bại chưa?

*Trả lời:* Chưa thể kết luận. Custom chain khiến web security default rút lui; user store mặc định là nhánh khác. Cần thêm nguồn user/provider/manager phù hợp nếu muốn thay nó, và xác nhận điều kiện bằng condition report.

**Câu 2.** Bạn thêm `@Bean UserDetailsService` nhưng `/public/ping` vẫn yêu cầu login. Vì sao?

*Trả lời:* Vì user store chỉ thay cách lấy tài khoản; chain bảo vệ URL mặc định có thể vẫn yêu cầu xác thực. Muốn cho `/public/**` công khai cần `SecurityFilterChain` phù hợp.

**Câu 3.** Một chain có `securityMatcher("/api/**")` và `anyRequest().authenticated()`. Tại sao `/billing` vẫn có thể không được Spring Security bảo vệ?

*Trả lời:* `/billing` không khớp `securityMatcher` nên không đi vào chain đó; cần một chain khác bao phủ.

**Câu 4.** Vì sao `@Configuration` chứa `@Bean SecurityFilterChain` ở package ngoài component scan có thể không thay mặc định?

*Trả lời:* Spring không đăng ký bean nếu class cấu hình không được quét hoặc import. Auto-configuration vẫn thấy thiếu bean và có thể tạo mặc định.

**Câu 5.** Bạn định nghĩa hai chain trùng matcher, nhưng `@Order` khiến chain rộng được xét trước. Hệ quả là gì?

*Trả lời:* Chain rộng có thể bắt request trước chain cụ thể, làm rule ở chain sau không được áp dụng. Sắp xếp chain cụ thể trước fallback tổng quát.

**Câu 6.** Vì sao không nên dùng `anyRequest().permitAll()` để “tạm chữa” 403 khi bật CSRF?

*Trả lời:* `permitAll` điều chỉnh quyền truy cập, không phải giải pháp xác minh CSRF token; nó cũng có thể mở dữ liệu riêng tư ngoài ý muốn. Hãy tìm lỗi thật ở điều kiện xác thực, quyền và CSRF.

**Câu 7.** Muốn biết chính xác vì sao `UserDetailsServiceAutoConfiguration` không tạo bean, nên xem gì?

*Trả lời:* Conditions report (`--debug` hoặc Actuator `conditions` được bảo vệ) cùng danh sách bean và dependency graph; xem điều kiện nào không khớp.

**Câu 8.** Một bean `SecurityFilterChain` của servlet có thay cho `SecurityWebFilterChain` của WebFlux được không?

*Trả lời:* Không. Hai stack có cơ chế và kiểu bean khác nhau; phải khai báo đúng theo loại ứng dụng.

## Tài liệu chính thức

- [Spring Boot 3.5 — Spring Security Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Boot 4 — Spring Security](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — Conditions Endpoint](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Spring Security — Java Configuration and Multiple Filter Chains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
