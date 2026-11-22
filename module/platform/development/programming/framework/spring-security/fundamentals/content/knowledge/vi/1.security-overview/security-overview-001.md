# Spring Security là gì và giải quyết những vấn đề nào?

## 1. Vì sao ứng dụng Spring cần bảo mật?

Hãy hình dung một hệ thống bán hàng gồm API xem sản phẩm, xem đơn hàng và quản trị tài khoản. Controller có thể xử lý đúng nghiệp vụ nhưng nếu không có kiểm soát bảo mật, ai biết URL cũng có thể thử gọi endpoint. Hệ thống phải trả lời ít nhất ba câu hỏi:

1. **Ai gửi yêu cầu?** Danh tính người dùng được xác minh bằng cách nào?
2. **Người đó được làm gì?** Người dùng thường có thể gọi chức năng admin, hoặc đọc đơn hàng của người khác không?
3. **Yêu cầu có bị lợi dụng không?** Trình duyệt có thể vô tình gửi một yêu cầu thay đổi dữ liệu do trang độc hại kích hoạt không?

**Spring Security** là một framework trong hệ sinh thái Spring cung cấp hạ tầng cho **xác thực (authentication)**, **phân quyền (authorization)** và **bảo vệ trước một số kiểu tấn công web phổ biến**. Framework tích hợp vào đường xử lý request của ứng dụng, hỗ trợ chính sách bảo mật thống nhất cho Spring MVC, REST API, và một stack riêng cho Spring WebFlux.

Spring Security không phải cơ sở dữ liệu người dùng, không phải JWT, không phải một identity provider và không tự thay thế HTTPS hoặc các kiểm tra nghiệp vụ. Nó cung cấp các thành phần để ứng dụng **xác minh danh tính và thực thi chính sách truy cập**.

## 2. Spring Security giải quyết những vấn đề nào?

| Nhu cầu | Cách Spring Security hỗ trợ | Tình huống |
| --- | --- | --- |
| Xác minh người dùng | Authentication, AuthenticationManager/AuthenticationProvider, tích hợp nguồn danh tính | Chỉ tài khoản đăng nhập đúng được vào trang hồ sơ |
| Phân quyền truy cập | Luật tại URL và method, role/authority, biểu thức phân quyền | ADMIN được quản trị, USER không được |
| Duy trì ngữ cảnh bảo mật | SecurityContext, cơ chế session hoặc xác thực theo từng request | Service biết người dùng hiện hành |
| Nhiều phương thức xác thực | Form login, HTTP Basic, OAuth2/OIDC client và resource server khi được cấu hình | Website dùng session; API nhận Bearer token |
| Giảm rủi ro tấn công web | CSRF protection, kiểm soát phiên, security headers phù hợp | Chặn yêu cầu POST giả mạo dựa trên cookie |
| Tập trung quy tắc | SecurityFilterChain, method security | Nhiều endpoint cùng được bảo vệ trước khi vào Controller |

Khả năng có sẵn **không có nghĩa mọi tính năng đều được tự động kích hoạt đúng cho mọi ứng dụng**. Developer cần xác định cơ chế xác thực, cấu hình chính sách và kiểm thử chúng.

### 2.1. Xác thực — Authentication

Authentication trả lời **“Bạn là ai?”**. Người dùng có thể cung cấp username/password, browser session hoặc Bearer token. Spring Security chuyển thông tin đó qua cơ chế xác thực đã cấu hình; nếu hợp lệ, kết quả **Authentication** thể hiện principal (danh tính) và các authorities liên quan.

Ví dụ: tài khoản “linh” đăng nhập đúng mật khẩu và được nhận diện là “linh”. Điều đó chỉ xác nhận danh tính, **chưa chứng minh** linh được xem mọi đơn hàng.

Với mật khẩu, hệ thống thật nên lưu **mật khẩu đã băm một chiều với thuật toán thích hợp**, chẳng hạn BCrypt hoặc Argon2 thông qua PasswordEncoder. Không lưu plaintext, không dựa vào mã hóa có thể giải ngược, và không xem việc gọi SHA-256 đơn thuần là một cơ chế lưu mật khẩu hoàn chỉnh.

### 2.2. Phân quyền — Authorization

Authorization trả lời **“Danh tính này được phép làm gì trên tài nguyên cụ thể?”**. Một số mức kiểm tra:

- Yêu cầu **authenticated**: đã được xác thực mới được xem hồ sơ.
- Yêu cầu **role/authority**: chỉ ADMIN được gọi chức năng quản trị.
- Yêu cầu **quyền nghiệp vụ**: USER chỉ được xem đơn hàng có ownerId trùng với danh tính của mình.
- Yêu cầu **theo trạng thái**: người có quyền duyệt cũng không được duyệt một đơn đã hủy.

Spring Security hỗ trợ phân quyền theo request và theo phương thức Java (ví dụ @PreAuthorize khi ứng dụng bật method security). Tuy nhiên, các điều kiện dựa trên dữ liệu thực như **quyền sở hữu đơn hàng** phải được cài đặt đúng. Nếu chỉ kiểm tra role USER mà bỏ kiểm tra ownerId thì vẫn có thể mắc lỗi IDOR/BOLA.

| Trường hợp | Authentication | Authorization |
| --- | --- | --- |
| Khách chưa đăng nhập truy cập /private | Chưa có | Không cấp quyền |
| USER đã đăng nhập truy cập /admin | Thành công | Từ chối |
| USER xem hồ sơ của mình | Thành công | Được phép theo chính sách |
| USER xem đơn hàng của USER khác | Thành công | Phải bị từ chối theo quyền sở hữu |

### 2.3. Bảo vệ trước những rủi ro web thường gặp

**CSRF (Cross-Site Request Forgery):** Trang web độc hại có thể kích hoạt request đến website mà nạn nhân đã đăng nhập; trình duyệt có thể tự gửi kèm cookie. Trong cấu hình servlet mặc định, Spring Security bật CSRF protection cho các HTTP method không an toàn như POST, PUT, PATCH và DELETE. Kiểm tra CSRF token giúp chống các request thay đổi trạng thái bị giả mạo. Không tắt toàn bộ CSRF chỉ vì gọi ứng dụng là “REST API”; phải xét browser có tự gửi credentials hay không. Ứng dụng dùng cookie hoặc HTTP Basic trong trình duyệt vẫn có thể cần bảo vệ CSRF.

**Session security:** Framework có cơ chế hỗ trợ quản lý phiên, session fixation protection và xử lý logout. Cấu hình session phải phù hợp với kiểu ứng dụng; chẳng hạn một API xác thực bằng token ở mỗi request có nhu cầu khác website dùng session/cookie.

**HTTP security headers:** Spring Security có thể đặt một số response headers giúp giảm rủi ro. Cần hiểu giới hạn của từng header: Content-Security-Policy (CSP) không tự xuất hiện thành chính sách phù hợp cho mọi website; HTTPS/TLS và an toàn cookie cần cấu hình đúng trên toàn hệ thống.

**Phân biệt CSRF, CORS và XSS:** CSRF là mạo dụng yêu cầu người dùng; CORS quy định quyền đọc response khác origin trong trình duyệt; XSS là thực thi mã không tin cậy trong trang. Bật CORS không thay thế xác thực, phân quyền hoặc kiểm tra CSRF.

## 3. Spring Security chặn request ở đâu?

Trong ứng dụng **Spring MVC/Servlet**, Spring Security thường chạy ở tầng **Servlet filters**, trước khi Controller được gọi. Luồng điển hình:

~~~text
HTTP Client
   |
   v
Servlet container
   |
   v
DelegatingFilterProxy -> FilterChainProxy
   |
   v
SecurityFilterChain được chọn cho request
   |-- security context, CSRF, authentication, authorization, ...
   |         |
   |         +-- Thất bại -> từ chối / yêu cầu đăng nhập
   |
   v
DispatcherServlet -> Controller -> Service -> Repository
   |
   v
HTTP response
~~~

Các thành phần quan trọng:

- **SecurityFilterChain:** Tập các security filters phù hợp với một nhóm request. Một hệ thống có thể dùng nhiều filter chain, mỗi chain có phạm vi matcher khác nhau. Luật cần được đặt đúng chain và đúng thứ tự.
- **AuthenticationManager / AuthenticationProvider:** Tham gia xác minh credentials theo phương thức authentication cụ thể; có thể kết nối UserDetailsService, password encoder hoặc provider khác.
- **Authentication:** Thể hiện principal và authorities sau khi xác thực.
- **SecurityContext:** Chứa Authentication đang áp dụng. Với Servlet, SecurityContextHolder thường dùng chiến lược ThreadLocal; không được giả định cơ chế đó áp dụng nguyên xi cho WebFlux hay mọi luồng bất đồng bộ.
- **Authorization:** Ra quyết định cho phép hoặc từ chối trước khi chạy mã được bảo vệ; có thể kiểm tra ở tầng HTTP hoặc method.

Spring WebFlux dùng **reactive WebFilter và reactive security context**, không cấu hình bằng HttpSecurity như ví dụ Servlet phía dưới.

### HTTP 401, 403 và chuyển hướng đăng nhập

- **401 Unauthorized:** Client chưa gửi thông tin xác thực phù hợp hoặc xác thực thất bại cho endpoint yêu cầu đăng nhập.
- **403 Forbidden:** Danh tính đã xác thực nhưng thiếu quyền, hoặc bị từ chối bởi chính sách bảo mật khác như CSRF.
- **302 Redirect:** Trong ứng dụng dùng form login, người chưa đăng nhập có thể được chuyển đến trang đăng nhập thay vì nhận 401.

Chính xác status code phụ thuộc entry point và exception handling được cấu hình. Không nên mặc định mọi ứng dụng Spring Security sẽ trả giống nhau.

## 4. Thực hành Java 17+: phân biệt public, private và admin

Ví dụ sau dùng **Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet**. Cần một dự án Spring Boot Java 17+ đã có plugin Boot và build tool. Trong file **build.gradle** (Groovy DSL), bổ sung dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Tạo file **src/main/java/com/example/securitydemo/SecurityDemoApplication.java**:

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/private").authenticated()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("learner")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint() {
        return "private OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Mã nguồn trên là một file Java hợp lệ: một class public tên **SecurityDemoApplication**, một class package-private tên **DemoController**. Spring Boot quét component cùng package và nhận diện Controller. Phiên bản dependency lấy từ BOM của Spring Boot, không cần tự gắn version vào hai dòng dependencies.

**Phân tích cấu hình:**

1. **/public** dùng permitAll nên ai cũng gọi được; **/private** yêu cầu authenticated; **/admin** dùng hasRole("ADMIN"). Spring Security hiểu hasRole("ADMIN") là yêu cầu authority **ROLE_ADMIN**.
2. **anyRequest().denyAll()** từ chối những request chưa được xác định rõ trong demo. Dự án thật phải thêm các endpoint cần thiết, chẳng hạn health check hoặc static resources, bằng chính sách có chủ đích.
3. **httpBasic** dùng HTTP Basic cho thử nghiệm với curl. **formLogin(form -> form.disable())** bỏ chuyển hướng trang đăng nhập trong demo; không có nghĩa mọi ứng dụng phải vô hiệu hóa form login.
4. **InMemoryUserDetailsManager** tạo tài khoản thử **learner** với role USER; không có role ADMIN. BCryptPasswordEncoder băm mật khẩu trước khi lưu trong bộ nhớ.
5. Demo có các endpoint GET nên **không tắt CSRF**. Nếu bổ sung POST/PUT/DELETE, cần thiết kế token hoặc chính sách CSRF phù hợp với phương pháp xác thực.

Chạy ở thư mục gốc của dự án (có Gradle Wrapper):

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell sử dụng **.\gradlew.bat bootRun**. Khi khởi động thành công và ứng dụng lắng nghe ở localhost:8080, thử:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u learner:learn123 http://localhost:8080/private
curl -i -u learner:learn123 http://localhost:8080/admin
~~~

Trên PowerShell, dùng **curl.exe** nếu **curl** bị ánh xạ thành lệnh khác. Các status mong đợi:

| Request | HTTP status | Nội dung/ý nghĩa |
| --- | --- | --- |
| /public, không credentials | 200 | Response body: public OK |
| /private, không credentials | 401 | HTTP Basic yêu cầu xác thực |
| /private, learner:learn123 | 200 | Response body: private OK |
| /admin, learner:learn123 | 403 | Xác thực thành công, thiếu ROLE_ADMIN |

Nếu gửi sai mật khẩu, /private không trả 200. Nếu một tài khoản thực sự được cấp role ADMIN, /admin mới có thể trả 200. Đây là cách kiểm tra rõ ràng sự khác biệt giữa **authentication** và **authorization**.

**Giới hạn demo:** Tài khoản và mật khẩu hard-code chỉ phục vụ học tập. Trong sản phẩm thật phải dùng nguồn danh tính được quản lý, lưu secret an toàn, dùng **HTTPS**, chính sách phiên/token đúng và cơ chế chống brute-force. HTTP Basic truyền credentials dạng Base64, **không mã hóa mật khẩu**, nên không được truyền qua HTTP thuần trên mạng thật.

## 5. Session, JWT, OAuth2 và OIDC liên quan thế nào?

Spring Security hỗ trợ các cơ chế này nhưng chúng phục vụ những vai trò khác nhau:

| Lựa chọn | Cách hoạt động khái quát | Điều cần thiết kế |
| --- | --- | --- |
| Session + cookie | Máy chủ lưu trạng thái đăng nhập, trình duyệt gửi cookie | Cookie Secure/HttpOnly/SameSite, session timeout, CSRF |
| HTTP Basic | Client gửi username/password trong Authorization header | Bắt buộc HTTPS, giới hạn mục đích sử dụng |
| Bearer token/JWT | Client trình token để API xác minh chữ ký và claims | Issuer, audience, expiry, keys, quyền và thu hồi |
| OAuth2 | Chuẩn cấp quyền ủy thác; có client, authorization server, resource server | Flow, scopes, quản lý token và trust |
| OpenID Connect | Lớp danh tính trên OAuth2, có ID token và cơ chế đăng nhập | Xác minh ID token, issuer, audience, nonce khi phù hợp |

Ví dụ: API nhận access token JWT từ một identity provider. Spring Security có khả năng xác minh Bearer JWT khi cấu hình đúng **OAuth2 Resource Server**. Chỉ cài spring-boot-starter-security **không tự cấp JWT**, không tự làm máy chủ đăng nhập SSO và không khiến mọi API stateless.

JWT là **định dạng token**, không đồng nghĩa dữ liệu bên trong đã được mã hóa hoặc có quyền truy cập mọi resource. Kiểm tra chữ ký thành công không thay thế kiểm tra authorization ở từng endpoint và tài nguyên.

## 6. Spring Boot mặc định làm gì khi có Spring Security?

Trong một ứng dụng Spring Boot web chưa tự khai báo cấu hình bảo mật thay thế, việc đưa Spring Security vào classpath thường khiến HTTP endpoints yêu cầu xác thực. Boot tạo **một user phát triển** với mật khẩu ngẫu nhiên được in trong log và có thể dùng form login hoặc HTTP Basic tùy yêu cầu/Accept header.

Đây là **mặc định phòng ngừa** khi mới thêm thư viện, không phải hệ thống xác thực production. Khi tự định nghĩa **SecurityFilterChain**, chính sách URL mặc định của Boot sẽ nhường chỗ cho policy của ứng dụng. Khi tự định nghĩa **UserDetailsService**, tài khoản mặc định của Boot cũng không cần được tạo.

Không nên kỳ vọng mặc định tự phân quyền dữ liệu theo ownerId, cấu hình OAuth2/JWT, bảo vệ mọi endpoint business hay vận hành rate limiting cho hệ thống.

## 7. Lỗi nhận thức và cấu hình phổ biến

1. **“Đã bật Spring Security là ứng dụng an toàn.”** Sai: permitAll quá rộng, thiếu kiểm tra dữ liệu hoặc lỗ hổng nghiệp vụ vẫn gây rò rỉ.
2. **“Đã đăng nhập thì được truy cập dữ liệu của mọi người.”** Sai: cần chính sách sở hữu tài nguyên, permission và trạng thái nghiệp vụ.
3. **“JWT là tính năng đăng nhập tự có của starter-security.”** Sai: phải thiết kế nhà cấp token, resource server và bộ xác minh.
4. **“REST API thì cứ disable CSRF.”** Sai: mô hình cookies/credentials tự gửi vẫn có nguy cơ CSRF dù trả JSON.
5. **“CORS giúp server xác minh người dùng.”** Sai: CORS chỉ là chính sách trình duyệt về cross-origin.
6. **“Role USER đủ để phân quyền các đơn hàng.”** Sai: role không chứng minh ownerId trùng người đăng nhập.
7. **“Mật khẩu có thể lưu plaintext hoặc mã hóa giải ngược.”** Sai: dùng password hashing có salt/cost phù hợp.
8. **“SecurityFilterChain tự chống SQL injection, XSS, SSRF, lộ secret.”** Sai: còn cần validation, truy vấn tham số hóa, encode output, kiểm soát outbound request, secret management và quy trình cập nhật dependency.
9. **“401 và 403 luôn giống nhau ở mọi ứng dụng.”** Sai: tùy auth scheme, entry point, CSRF và exception handler; form login có thể trả redirect.
10. **“Filter check role là đủ bảo vệ nghiệp vụ.”** Sai: nhiều điều kiện chỉ có dữ liệu ở tầng Service/Repository; cần kiểm tra với danh tính thật.

## 8. Checklist áp dụng vào ứng dụng thực tế

1. **Lập danh sách endpoint:** public, cần authenticated, admin, method-specific và tài nguyên có owner.
2. **Chọn cơ chế danh tính:** session hay OAuth2/OIDC/token; nguồn tài khoản và cách quản lý credentials.
3. **Cấu hình policy:** matcher có thứ tự rõ, mặc định deny cho đường dẫn chưa xác định, sử dụng method security khi cần.
4. **Bảo vệ dữ liệu:** kiểm tra quyền sở hữu dữ liệu từ database và trạng thái nghiệp vụ, không chỉ kiểm tra role.
5. **Bảo vệ tầng web:** HTTPS, cookie an toàn, CSRF theo risk model, CORS và security headers được cấu hình có chủ đích.
6. **Kiểm thử người dùng khác nhau:** anonymous, sai mật khẩu, USER, ADMIN, USER A thử xem dữ liệu USER B; kiểm tra cả status và payload.
7. **Vận hành:** audit event, giám sát lạm dụng, rate limiting, quản lý secret, cập nhật dependencies và rà soát bảo mật định kỳ.

## 9. Tự kiểm tra

**Câu 1.** USER đăng nhập thành công nhưng bị 403 khi truy cập /admin. Bước nào thất bại?  
**Đáp:** Authorization; authentication đã thành công.

**Câu 2.** Vì sao authenticated() ở /orders/123 không đủ an toàn?  
**Đáp:** authenticated() không kiểm tra người dùng hiện tại có sở hữu order 123 hay không.

**Câu 3.** Spring Security có tự phát hành JWT khi thêm starter-security không?  
**Đáp:** Không. Cần triển khai/cấu hình các thành phần cấp token, verify token và policy tương ứng.

**Câu 4.** Một API dùng cookie đăng nhập có nên tắt CSRF vì chỉ nhận JSON không?  
**Đáp:** Không thể kết luận như vậy. Cần đánh giá cơ chế trình duyệt tự đính kèm cookie, HTTP method và cách chống request giả mạo.

## 10. Tài liệu chính thức

- Kiến trúc Servlet: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/index.html
- Authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/index.html
- CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Boot security auto-configuration: https://docs.spring.io/spring-boot/reference/web/spring-security.html
