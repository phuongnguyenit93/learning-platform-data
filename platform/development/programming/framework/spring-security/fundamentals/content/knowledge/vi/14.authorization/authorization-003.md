# hasRole, hasAuthority và tiền tố ROLE_ trong Spring Security

## 1. Mục tiêu và câu hỏi cốt lõi

Khi viết quy tắc phân quyền trong Spring Security, ba câu hỏi dễ gây nhầm lẫn là:

1. **hasRole("ADMIN")** khác **hasAuthority("ADMIN")** ở đâu?
2. Vì sao tài khoản có quyền **ADMIN** nhưng vẫn không qua được **hasRole("ADMIN")**?
3. Tiền tố **ROLE_** xuất hiện khi nào, được thêm ở đâu và có nên lưu nguyên trong hệ thống cấp quyền?

Để hiểu đúng, cần phân biệt **role** (vai trò, ví dụ ADMIN) với **GrantedAuthority** (một quyền được cấp, biểu diễn thành chuỗi như ROLE_ADMIN hoặc document:read). Spring Security ra quyết định dựa trên tập GrantedAuthority có trong đối tượng Authentication. **ROLE_ là quy ước đặt tên và đối chiếu authority cho các phép kiểm tra role mặc định**, không phải một loại quyền riêng được JVM, HTTP hay database tự hiểu.

Sau bài này, bạn sẽ đọc được một quy tắc hasRole/hasAuthority, dự đoán chính xác ai được phép truy cập, xây dựng ví dụ có thể chạy và biết cách chẩn đoán lỗi 403 vì sai tiền tố.

## 2. Spring Security thực sự giữ thông tin quyền ở đâu?

Trong luồng xử lý thông thường:

~~~text
Request có credentials
       |
       v
Authentication mechanism (form login, HTTP Basic, JWT, ...)
       |
       v
Xác thực thành công -> Authentication
                         |
                         +-- principal: danh tính
                         +-- authenticated: trạng thái xác thực
                         +-- authorities: Collection<? extends GrantedAuthority>
                                           |
                                           +-- "ROLE_ADMIN"
                                           +-- "document:read"
                                           +-- "invoice:approve"
       |
       v
AuthorizationManager / method security / expression
       |
       +-- So khớp yêu cầu quyền với các authority hiện có
       |
       +-- Cho phép hoặc từ chối
~~~

Trong Java, các hợp đồng liên quan có thể hình dung qua các đoạn rút gọn sau (chỉ để giải thích API, **không phải** chương trình độc lập):

~~~java
// org.springframework.security.core.GrantedAuthority
String getAuthority();

// org.springframework.security.core.Authentication
Collection<? extends GrantedAuthority> getAuthorities();
~~~

**SimpleGrantedAuthority("ROLE_ADMIN")** là một cách phổ biến để biểu diễn authority bằng chuỗi. Khi so khớp authority thông thường, Spring Security quan tâm đến giá trị **getAuthority()**. Hai chuỗi **ADMIN** và **ROLE_ADMIN** khác nhau; chữ hoa/thường cũng có ý nghĩa.

Ví dụ một Authentication có các authority:

~~~text
["ROLE_ADMIN", "document:read"]
~~~

Nó thỏa điều kiện **ROLE_ADMIN** và **document:read**. Nó **không** tự động có authority **ADMIN**, **ROLE_USER** hoặc **document:write**. Quy tắc kế thừa role, nếu cần, phải được cấu hình riêng; ADMIN không mặc nhiên bao hàm USER.

**Authentication thành công chưa đồng nghĩa authorization thành công.** Người dùng có thể đã đăng nhập nhưng thiếu authority cần thiết nên nhận phản hồi 403.

## 3. hasAuthority: so khớp giá trị authority cụ thể

Với cách sử dụng mặc định:

~~~java
.hasAuthority("ADMIN")
.hasAuthority("ROLE_ADMIN")
.hasAuthority("document:read")
~~~

Mỗi điều kiện yêu cầu Authentication chứa một GrantedAuthority có chuỗi **đúng bằng** giá trị truyền vào:

| Quy tắc | Authority cần có | Có tự thêm ROLE_ không? |
| --- | --- | --- |
| hasAuthority("ADMIN") | ADMIN | Không |
| hasAuthority("ROLE_ADMIN") | ROLE_ADMIN | Không |
| hasAuthority("document:read") | document:read | Không |
| hasAuthority("SCOPE_orders.read") | SCOPE_orders.read | Không |

Từ đó, **hasAuthority("ADMIN") không tương đương với hasAuthority("ROLE_ADMIN")**. Quy tắc authority rất phù hợp với các quyền nghiệp vụ cụ thể như product:edit, invoice:approve, report:export hoặc tên authority đã chuẩn hóa từ identity provider.

Cần phân biệt **authority được cấp** với **quy tắc đòi hỏi authority**: viết hasAuthority("document:read") không tự cấp quyền document:read cho người dùng. Quyền phải được đưa vào Authentication ở bước xác thực hoặc ánh xạ quyền.

## 4. hasRole: lối viết ngắn cho authority có tiền tố role

Theo mặc định của Spring Security 6.x, khi viết:

~~~java
.hasRole("ADMIN")
~~~

quy tắc yêu cầu authority có tên:

~~~text
ROLE_ADMIN
~~~

Vì vậy, khi dùng **tiền tố mặc định ROLE_**:

~~~text
hasRole("ADMIN")          ~  hasAuthority("ROLE_ADMIN")
hasRole("USER")           ~  hasAuthority("ROLE_USER")
hasAnyRole("ADMIN","USER") ~ hasAnyAuthority("ROLE_ADMIN","ROLE_USER")
~~~

Dấu ~ ở đây thể hiện **tương đương về tập authority yêu cầu trong cấu hình mặc định**, không có nghĩa mọi API hai bên luôn xử lý giống nhau khi dự án tùy biến role prefix, role hierarchy hoặc authorization manager.

### Bảng chân trị quan trọng

Giả sử không có role hierarchy hay logic cấp quyền bổ sung:

| Authorities của người dùng | hasRole("ADMIN") | hasAuthority("ADMIN") | hasAuthority("ROLE_ADMIN") |
| --- | --- | --- | --- |
| ["ROLE_ADMIN"] | Có | Không | Có |
| ["ADMIN"] | Không | Có | Không |
| ["ROLE_USER"] | Không | Không | Không |
| ["ADMIN", "ROLE_ADMIN"] | Có | Có | Có |
| ["ROLE_ADMIN", "document:read"] | Có | Không | Có |
| [] | Không | Không | Không |

Tình huống hay gặp: hệ thống đăng nhập đọc từ database cột role = ADMIN, rồi tạo Authentication có **new SimpleGrantedAuthority("ADMIN")**. Một endpoint cấu hình **hasRole("ADMIN")** vẫn từ chối vì lúc này nó đang tìm **ROLE_ADMIN**, không tìm ADMIN.

### Viết "ROLE_" ở vị trí nào?

- Trong các DSL fluent thường dùng như **authorizeHttpRequests(...).requestMatchers(...).hasRole("ADMIN")**, hãy truyền **ADMIN**, không truyền **ROLE_ADMIN**. API hasRole của nhóm này tự thêm tiền tố mặc định và có thể từ chối tham số đã có ROLE_.
- Với **hasAuthority("ROLE_ADMIN")**, bạn phải ghi đúng nguyên chuỗi được cấp, nên có ROLE_ nếu Authentication lưu ROLE_ADMIN.
- Với biểu thức **@PreAuthorize("hasRole('ADMIN')")**, cú pháp thường dùng vẫn là role logic ADMIN. Expression handler có quy tắc xử lý prefix riêng; không suy diễn rằng mọi nơi sử dụng hasRole xử lý chuỗi đã có prefix giống hệt nhau.

**Tiền tố không được thêm vào Authentication bởi hasRole.** Phép kiểm tra chỉ xây dựng yêu cầu quyền để so khớp. Đường tạo/cấp quyền vẫn phải đảm bảo Authentication chứa authority được mong đợi.

## 5. Nguồn gốc ROLE_: roles(...) khác authorities(...)

Trong **org.springframework.security.core.userdetails.User.UserBuilder**, hai API sau có ý nghĩa khác nhau:

~~~java
UserDetails alice = User.withUsername("alice")
        .password("{noop}demo123")
        .roles("ADMIN")
        .build();

UserDetails bob = User.withUsername("bob")
        .password("{noop}demo123")
        .authorities("ADMIN")
        .build();

UserDetails carol = User.withUsername("carol")
        .password("{noop}demo123")
        .authorities("ROLE_ADMIN")
        .build();
~~~

Đây là fragment minh họa và cần import User, UserDetails từ Spring Security:

| Người dùng | Cách tạo | Authority thực tế |
| --- | --- | --- |
| alice | roles("ADMIN") | ROLE_ADMIN |
| bob | authorities("ADMIN") | ADMIN |
| carol | authorities("ROLE_ADMIN") | ROLE_ADMIN |

**roles("ADMIN")** là tiện ích của UserBuilder; nó **chuyển giá trị role thành authority có ROLE_**. **authorities("ADMIN")** giữ đúng tên ADMIN. Nếu gọi **roles("ROLE_ADMIN")** trong UserBuilder, đầu vào không hợp lệ vì roles(...) không nhận role đã mang tiền tố.

Không nên gọi liên tiếp roles(...) và authorities(...) trên cùng một UserBuilder rồi giả định hai danh sách luôn được cộng dồn. Khi cần nhiều quyền, hãy xây dựng tập authorities chủ động và kiểm tra bằng **getAuthorities()** sau khi tạo người dùng.

**Lưu ý:** {noop} là cách mã hóa mật khẩu chỉ dùng cho bài thử cục bộ. Trong production phải dùng mật khẩu băm và PasswordEncoder phù hợp; không hard-code mật khẩu thật vào mã nguồn.

### Database và identity provider có thể lưu tên khác

Một hệ thống có thể lưu bảng quyền với giá trị ADMIN và ánh xạ sang ROLE_ADMIN khi tạo Authentication. Hệ thống khác có thể lưu trực tiếp ROLE_ADMIN. Cả hai hướng đều khả thi nếu nhất quán. Đừng đổi cách lưu trữ và thêm prefix ở nhiều tầng cùng lúc, dễ tạo nhầm **ROLE_ROLE_ADMIN**.

~~~text
DB role = "ADMIN"
      |
      |  ánh xạ rõ ràng ở bước tạo GrantedAuthority
      v
Authentication.authorities = ["ROLE_ADMIN"]
      |
      +--> hasRole("ADMIN"): qua
      +--> hasAuthority("ROLE_ADMIN"): qua
      +--> hasAuthority("ADMIN"): không qua
~~~

Khi dùng JWT/OAuth2 Resource Server, tên authority thường được ánh xạ từ claims (chẳng hạn scope thành **SCOPE_...** theo cấu hình mặc định của converter phổ biến). **SCOPE_orders.read** không tự tương đương **ROLE_ADMIN**; cần viết rule khớp authority thực tế hoặc cấu hình converter rõ ràng.

## 6. Ví dụ Spring Boot chạy được: cùng tên ADMIN, kết quả khác nhau

Ví dụ này dùng **Spring MVC/Servlet** để cô lập chính xác bài học về role và authority. Nguyên tắc GrantedAuthority và tiền tố vẫn áp dụng khi học cấu hình Spring Security WebFlux, nhưng API DSL của WebFlux dùng **SecurityWebFilterChain**, **ServerHttpSecurity** và **authorizeExchange** thay vì HttpSecurity/SecurityFilterChain.

### 6.1. Chuẩn bị dự án

Tạo dự án **Gradle, Java 17+**, Spring Boot **3.x**, dependencies **Spring Web** (spring-boot-starter-web) và **Spring Security** (spring-boot-starter-security). Với Spring Initializr, dùng group **com.example** và artifact **demo** để package là **com.example.demo**.

Tạo file **src/main/java/com/example/demo/RoleAuthorityDemoApplication.java** có toàn bộ nội dung:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class RoleAuthorityDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RoleAuthorityDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/role")
                            .hasRole("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/plain")
                            .hasAuthority("ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/prefixed")
                            .hasAuthority("ROLE_ADMIN")
                        .requestMatchers(HttpMethod.GET, "/api/read")
                            .hasAuthority("document:read")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}demo123")
                .roles("ADMIN")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password("{noop}demo123")
                .authorities("ADMIN")
                .build();

        UserDetails reader = User.withUsername("reader")
                .password("{noop}demo123")
                .authorities("document:read")
                .build();

        return new InMemoryUserDetailsManager(alice, bob, reader);
    }
}

@RestController
class DemoController {

    @GetMapping("/api/role")
    String role() {
        return "role-ok";
    }

    @GetMapping("/api/plain")
    String plain() {
        return "plain-ok";
    }

    @GetMapping("/api/prefixed")
    String prefixed() {
        return "prefixed-ok";
    }

    @GetMapping("/api/read")
    String read() {
        return "read-ok";
    }
}
~~~

Tại thư mục gốc dự án, chạy:

~~~bash
./gradlew bootRun
~~~

Trên Windows dùng **gradlew.bat bootRun**. Sau khi ứng dụng khởi động tại cổng mặc định 8080, thử các request sau (trên PowerShell dùng **curl.exe** để tránh alias curl):

~~~bash
curl -i -u alice:demo123 http://localhost:8080/api/role
curl -i -u bob:demo123 http://localhost:8080/api/role
curl -i -u bob:demo123 http://localhost:8080/api/plain
curl -i -u alice:demo123 http://localhost:8080/api/plain
curl -i -u alice:demo123 http://localhost:8080/api/prefixed
curl -i -u reader:demo123 http://localhost:8080/api/read
curl -i http://localhost:8080/api/role
~~~

### 6.2. Kết quả mong đợi

| Request | Authorities của tài khoản | Rule | HTTP status | Body khi thành công |
| --- | --- | --- | --- | --- |
| alice -> /api/role | ROLE_ADMIN | hasRole("ADMIN") | **200** | role-ok |
| bob -> /api/role | ADMIN | hasRole("ADMIN") | **403** | — |
| bob -> /api/plain | ADMIN | hasAuthority("ADMIN") | **200** | plain-ok |
| alice -> /api/plain | ROLE_ADMIN | hasAuthority("ADMIN") | **403** | — |
| alice -> /api/prefixed | ROLE_ADMIN | hasAuthority("ROLE_ADMIN") | **200** | prefixed-ok |
| reader -> /api/read | document:read | hasAuthority("document:read") | **200** | read-ok |
| Không credentials -> /api/role | Chưa xác thực | hasRole("ADMIN") | **401** | — |

Đây là **kết quả dự kiến từ cấu hình ví dụ**, không phải log một lần chạy thực tế. Header, JSON lỗi hoặc HTML lỗi có thể phụ thuộc cấu hình Boot/Security. Ví dụ chỉ gửi GET nên không đụng quy tắc CSRF cho các HTTP method thay đổi trạng thái.

**Phân tích cụ thể:**

1. Alice được tạo bằng roles("ADMIN") nên nhận **ROLE_ADMIN**. hasRole("ADMIN") cần đúng authority đó và cho qua.
2. Bob được tạo bằng authorities("ADMIN") nên **chỉ** mang ADMIN. Tài khoản đã được HTTP Basic xác thực nhưng thiếu ROLE_ADMIN, do đó nhận **403**.
3. hasAuthority("ADMIN") cho Bob qua vì so khớp chuỗi ADMIN; Alice không được phép vào endpoint đó.
4. hasAuthority("ROLE_ADMIN") cho Alice qua, cùng authority mà hasRole("ADMIN") kiểm tra trong cấu hình mặc định.
5. Reader chỉ có quyền nghiệp vụ document:read; điều này không tự cấp role ADMIN.
6. Request không credentials cần xác thực để có đủ authority; HTTP Basic trả **401** và yêu cầu đăng nhập.

**401 vs 403:** 401 thường nghĩa là request chưa xác thực hợp lệ và được authentication entry point xử lý; 403 thường nghĩa là đã xác thực nhưng không đủ quyền. Không nên chỉ nhìn status mà bỏ qua cấu hình authentication mechanism và exception handling. Tùy entry point, một ứng dụng dùng form login có thể chuyển hướng (302) thay vì trả 401 cho khách chưa đăng nhập.

## 7. Tương ứng trong ba nơi cấu hình phân quyền

### 7.1. Servlet URL authorization (Spring MVC)

Fragment dưới đây phải đặt trong cấu hình **HttpSecurity** của một ứng dụng Servlet, không phải source file độc lập:

~~~java
http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .requestMatchers("/documents/**").hasAuthority("document:read")
        .anyRequest().authenticated());
~~~

Phần **requestMatchers** xác định request nào chịu quy tắc; **hasRole/hasAuthority** xác định quyền cần có. Đặt matcher cụ thể trước quy tắc bao phủ chung vì các quy tắc được xét theo thứ tự.

### 7.2. Reactive URL authorization (Spring WebFlux)

Fragment tương ứng dùng **ServerHttpSecurity**, thuộc một SecurityWebFilterChain:

~~~java
http.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .pathMatchers("/documents/**").hasAuthority("document:read")
        .anyExchange().authenticated());
~~~

Đoạn mã giả định biến **http** có kiểu ServerHttpSecurity. Trong hệ thống reactive, nguồn authority vẫn là Authentication; lỗi "ADMIN" và "ROLE_ADMIN" không khớp nhau vẫn có thể xuất hiện.

### 7.3. Method security (@PreAuthorize)

Method security bảo vệ lời gọi tới method được Spring Security áp dụng AOP, thay vì chỉ bảo vệ đường dẫn HTTP. Trong ứng dụng Servlet, bật **@EnableMethodSecurity** rồi đặt annotation phù hợp vào service được Spring quản lý:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void archiveOldRecords() {
    // Bảo vệ thao tác quản trị.
}

@PreAuthorize("hasAuthority('document:read')")
public String readDocument() {
    return "document";
}
~~~

Đây là **fragment** minh họa hai method; cần đặt trong lớp bean hợp lệ. **@EnableMethodSecurity** cần có trong cấu hình, và phải gọi method qua Spring-managed proxy để interception hoạt động như dự kiến (self-invocation có thể bỏ qua AOP). Với reactive method security, dùng cấu hình **@EnableReactiveMethodSecurity** và API reactive thích hợp.

Cách viết biểu thức SpEL có dấu nháy **'ADMIN'** khác DSL Java có chuỗi **"ADMIN"**, nhưng ý nghĩa quyền được kiểm tra trong cấu hình prefix mặc định là như nhau.

**Tại sao bảo vệ method hữu ích?** Nếu cùng service được gọi từ HTTP controller, scheduled job hoặc một luồng nghiệp vụ khác, quy tắc chỉ có ở request URL có thể không bảo vệ mọi đường đi. Method security giúp đặt kiểm tra gần thao tác cần bảo vệ; vẫn cần thiết kế quyền/ủy quyền phù hợp.

## 8. Những biến thể thường gặp

### hasAnyRole và hasAnyAuthority

~~~java
.hasAnyRole("ADMIN", "MANAGER")
.hasAnyAuthority("ROLE_ADMIN", "ROLE_MANAGER")
.hasAnyAuthority("document:read", "document:write")
~~~

Trong cấu hình mặc định, hasAnyRole("ADMIN","MANAGER") cho phép khi người dùng có **ít nhất một** trong ROLE_ADMIN hoặc ROLE_MANAGER. hasAnyAuthority cũng là **OR**, không đòi tất cả authority. Nếu nghiệp vụ yêu cầu nhiều điều kiện cùng đúng, phải dùng AuthorizationManager phối hợp hoặc cấu hình tương ứng, không hiểu sai hasAny thành AND.

### Role hierarchy

Sự hiện diện của **ROLE_ADMIN** không tự động mang theo **ROLE_USER**. Nếu dự án cấu hình RoleHierarchy theo quan hệ ADMIN > USER, một authorization manager có tích hợp hierarchy mới có thể coi ADMIN đạt yêu cầu USER. Vì vậy, khi đánh giá một ứng dụng thực tế cần xem cả hierarchy và nơi nó được áp dụng; không mặc định bảng kiểm tra chuỗi luôn phản ánh toàn bộ policy nâng cao.

### Đổi tiền tố ROLE_

Spring Security hỗ trợ cấu hình tiền tố role trong một số cơ chế. Chẳng hạn, với **method-security expression**, có thể khai báo **GrantedAuthorityDefaults** để đổi tiền tố:

~~~java
@Bean
static GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APP_ROLE_");
}
~~~

Đây là fragment trong class cấu hình (cần import **org.springframework.security.config.core.GrantedAuthorityDefaults**). Khi áp dụng đúng với expression handler tương ứng, **hasRole("ADMIN")** sẽ tìm tên authority theo tiền tố mới, ví dụ APP_ROLE_ADMIN.

**Không tự suy ra một bean GrantedAuthorityDefaults sẽ thay đổi đồng loạt mọi DSL/AuthorizationManager ở mọi phiên bản.** Một số API fluent hasRole tạo manager với tiền tố riêng hoặc có cơ chế factory riêng. Nếu buộc phải tùy biến prefix, hãy kiểm tra phiên bản Spring Security đang dùng, cấu hình của từng authorization manager và chạy test cho cả URL lẫn method security. Cách ít rủi ro hơn thường là giữ quy ước ROLE_ nhất quán và sử dụng hasAuthority khi muốn kiểm tra chính xác một quyền tùy biến.

## 9. Chẩn đoán lỗi thực tế

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Có role ADMIN từ DB nhưng hasRole("ADMIN") vẫn 403 | Authentication chứa ADMIN chứ không phải ROLE_ADMIN | Quan sát Authentication.getAuthorities(); chuẩn hóa ánh xạ khi tạo authority hoặc chọn hasAuthority cho giá trị thật. |
| hasAuthority("ADMIN") thất bại dù users().roles("ADMIN") | roles(...) đã tạo ROLE_ADMIN | Dùng hasAuthority("ROLE_ADMIN") hoặc hasRole("ADMIN"). |
| Dùng hasRole("ROLE_ADMIN") gây lỗi cấu hình | Fluent API hasRole tự thêm tiền tố và có thể từ chối role đã có ROLE_ | Đổi thành hasRole("ADMIN"). |
| Nhận ROLE_ROLE_ADMIN | Tiền tố bị thêm hai lần ở các tầng ánh xạ | Quy định duy nhất nơi xây dựng tên authority; kiểm tra dữ liệu sau mapping. |
| ADMIN không truy cập được URL yêu cầu USER | Không có ROLE_USER hoặc hierarchy phù hợp | Cấp authority cần thiết hoặc cấu hình role hierarchy đúng nơi áp dụng. |
| JWT đã đăng nhập nhưng hasRole("ADMIN") thất bại | Converter tạo SCOPE_... hoặc tên claim khác | Kiểm tra converter và authorities thực tế; ánh xạ role/permission rõ ràng. |
| Chưa đăng nhập nhận 401, đăng nhập nhận 403 | Xác thực đã thành công nhưng thiếu quyền | Tách debug authentication khỏi authorization. |
| @PreAuthorize không có tác dụng | Chưa bật method security hoặc lời gọi đi vòng qua Spring proxy | Kiểm tra @EnableMethodSecurity/@EnableReactiveMethodSecurity, bean lifecycle và đường gọi method. |
| Rule dự kiến không được chọn | Request matcher tổng quát đứng trước matcher cụ thể | Sắp xếp matcher theo độ đặc hiệu, cấu hình denyAll/đường dự phòng rõ ràng. |

Để điều tra trong môi trường phát triển, có thể bật logging có kiểm soát:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Đọc log cùng response HTTP, kiểm tra Authentication.getAuthorities() ở điểm tin cậy sau xác thực (không ghi password/token hoặc thông tin nhạy cảm vào log). Nên dùng test có danh sách authority kỳ vọng để bảo vệ việc đổi converter, prefix hoặc nâng phiên bản.

## 10. Nguyên tắc thiết kế chính sách quyền

- **Dùng role cho nhóm chức năng lớn** như ADMIN/MANAGER/USER; nếu chọn hasRole thì định danh role logic không bao gồm ROLE_ ở lời gọi DSL.
- **Dùng authority cho quyền nghiệp vụ hẹp** như order:refund, inventory:write, report:export. hasAuthority diễn đạt chính xác permission cần có và tránh lệ thuộc quy ước ROLE_.
- **Chọn một quy ước cấp quyền xuyên suốt** từ DB/IdP → mapper → Authentication → policy. Ghi rõ giá trị thực tế lưu ở mỗi tầng.
- **Không coi tên role là quyền truy cập dữ liệu cụ thể.** Ví dụ có ROLE_MANAGER chưa đủ để khẳng định người dùng được xem mọi đơn hàng; vẫn cần kiểm tra tenant, ownership hoặc điều kiện nghiệp vụ khi cần.
- **Test cả trường hợp cho phép và từ chối.** Tối thiểu thử user có ROLE_ADMIN, chỉ có ADMIN, có authority nghiệp vụ và không xác thực. Test 401/403 theo entry point thực tế.

## 11. Bài tập tự đánh giá

1. Authentication có ["ROLE_USER", "invoice:approve"]. Các điều kiện **hasRole("USER")**, **hasAuthority("USER")**, **hasAuthority("invoice:approve")** lần lượt đúng hay sai?
2. So sánh **User.withUsername(...).roles("ADMIN")** và **.authorities("ADMIN")**: authority nào được tạo?
3. Vì sao **hasRole("ADMIN")** và **hasAuthority("ROLE_ADMIN")** thường tương đương, nhưng không nên coi chúng là hai API hoàn toàn có thể thay thế trong mọi cấu hình tùy biến prefix?
4. Nếu chỉ có authority **SCOPE_profile**, điều kiện **hasRole("PROFILE")** có thành công không? Cần thay đổi gì để đáp ứng?
5. Một tài khoản có **ROLE_ADMIN** có mặc định thỏa **hasRole("USER")** không? Khi nào câu trả lời có thể thay đổi?
6. Vì sao request không credentials và request đã xác thực nhưng thiếu role có thể cho hai status khác nhau?
7. Với quyền **document:read**, bạn sẽ chọn hasRole hay hasAuthority? Giải thích tên authority thực tế cần xuất hiện trong Authentication.

**Ghi nhớ:** Spring Security kiểm tra **GrantedAuthority**. **hasAuthority("X")** yêu cầu authority đúng chuỗi X; **hasRole("X")** theo mặc định yêu cầu authority ROLE_X. **roles("X")** của UserBuilder thêm ROLE_ khi **tạo authority**, còn hasRole thêm ROLE_ khi **xây dựng yêu cầu kiểm tra**. Phân biệt hai thời điểm đó sẽ giải quyết phần lớn lỗi phân quyền liên quan đến tiền tố.

## Tài liệu chính thức để đối chiếu

- Spring Security 6.5 — Authorization Architecture: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/architecture.html
- Spring Security 6.5 — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Reactive request authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security API — User.UserBuilder (roles/authorities): https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/core/userdetails/User.UserBuilder.html
