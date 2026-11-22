# AuthenticationManager và AuthenticationProvider trong luồng xác thực Servlet

## 1. Bài toán và các trách nhiệm

Khi người dùng gửi username/password hoặc một loại credential tới ứng dụng Spring Boot, có ba việc cần phân biệt: đọc credential từ HTTP, kiểm chứng credential và quyết định danh tính ấy được truy cập tài nguyên gì.

Trong Spring Security dùng Servlet:

- **AuthenticationManager** là interface tiếp nhận yêu cầu xác thực và trả về kết quả xác thực hoặc lỗi. Nó tạo ranh giới chung giữa code nhận credential và code kiểm chứng.
- **AuthenticationProvider** là interface của thành phần thực sự kiểm tra một loại Authentication, ví dụ username/password qua database hoặc một loại token được cấu hình.
- **ProviderManager** là triển khai phổ biến của AuthenticationManager, điều phối danh sách AuthenticationProvider.
- **Authentication filter** nhận credential từ HTTP, tạo token đầu vào, gọi manager và xử lý kết quả trong luồng request.
- **SecurityContext** giữ Authentication đang áp dụng cho request; **authorization** sau đó đánh giá quyền truy cập của danh tính đã biết.

**AuthenticationManager khác AuthorizationManager**: một bên xác thực danh tính, bên còn lại kiểm tra quyền dùng tài nguyên. Một người có thể đăng nhập đúng nhưng vẫn bị từ chối khi yêu cầu endpoint của ADMIN.

Ví dụ trong bài dùng Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x và Spring MVC/Servlet. WebFlux có WebFilter và reactive security context khác Servlet; API của DaoAuthenticationProvider cũng thay đổi qua các phiên bản Spring Security, nên cần đối chiếu Javadoc đúng version khi nâng cấp.

Sau bài này, bạn sẽ nhận diện được từng thành phần, vẽ được luồng request Basic/form login, hiểu supports/null/exception khi nhiều provider, đọc được cấu hình AuthenticationManager tường minh và dự đoán các kết quả HTTP 200, 401, 403.

## 2. Bản đồ thành phần

| Thành phần | Đầu vào / nhiệm vụ | Kết quả hoặc giới hạn |
| --- | --- | --- |
| **Authentication** | Principal, credentials, authorities, authenticated | Có thể là yêu cầu chưa kiểm chứng hoặc danh tính đã xác thực |
| **AuthenticationManager** | Phương thức authenticate(Authentication) | Trả Authentication được xác thực hoặc ném AuthenticationException |
| **ProviderManager** | Danh sách AuthenticationProvider | Chọn provider phù hợp và xử lý kết quả |
| **AuthenticationProvider** | supports(Class) và authenticate(Authentication) | Kiểm chứng một loại Authentication |
| **DaoAuthenticationProvider** | Username/password, UserDetailsService, PasswordEncoder | Xác thực user/password, trả principal và authorities |
| **UserDetailsService** | loadUserByUsername(username) | Chỉ tải thông tin user, không tự so khớp password |
| **PasswordEncoder** | encode và matches | Băm/kiểm tra mật khẩu, không quyết định quyền API |
| **BasicAuthenticationFilter** | Header Authorization: Basic | Gọi manager, xử lý Basic và thiết lập SecurityContext |
| **UsernamePasswordAuthenticationFilter** | Form login username/password | Gọi manager, xử lý success/failure theo cấu hình |
| **SecurityContextHolder** | Ngữ cảnh Authentication trong Servlet | Cung cấp danh tính hiện hành, không xác thực thay provider |
| **AuthorizationFilter** | Quy tắc request và Authentication hiện hành | Cho phép hoặc từ chối gọi Controller |

Có thể nhớ ngắn: **Filter biết lấy credential ở đâu; Manager biết giao ai kiểm tra; Provider biết kiểm tra ra sao; Context giữ kết quả; Authorization quyết định có được vào tài nguyên hay không.**

## 3. Authentication: vừa là đầu vào vừa là kết quả

Interface Authentication được Spring Security dùng ở hai thời điểm.

**Trước xác thực:** BasicAuthenticationFilter hoặc UsernamePasswordAuthenticationFilter có thể tạo UsernamePasswordAuthenticationToken với principal là tên do client khai, credentials là password và trạng thái authenticated=false. Token mới tạo **chưa đáng tin**.

Ví dụ một đoạn Java minh họa, nằm trong phương thức có import Spring Security cần thiết:

~~~java
Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        "alice", "learn123"
    );
~~~

Đoạn này chỉ tạo **yêu cầu xác thực**, không chứng minh alice đã đăng nhập. Không lấy role do client tự khai rồi tạo Authentication được tin cậy.

**Sau xác thực:** Provider có thể trả Authentication với principal là UserDetails đã kiểm chứng, authenticated=true và authorities đáng tin, ví dụ ROLE_USER. Credentials nhạy cảm có thể được xóa sau xác thực.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| principal | Danh tính | UserDetails alice |
| credentials | Chứng cứ xác thực | Password của request |
| authorities | Quyền được cấp | ROLE_USER |
| details | Metadata bổ sung, tùy cơ chế | Dữ liệu request phụ trợ |
| isAuthenticated() | Trạng thái token | true sau khi xác minh |

Với cấu hình thông dụng, **roles("USER")** tạo **ROLE_USER**. Rule **hasRole("ADMIN")** kiểm tra authority **ROLE_ADMIN**. Đăng nhập đúng không đồng nghĩa đủ quyền với mọi endpoint hoặc bản ghi.

## 4. Luồng Servlet: HTTP request đến AuthenticationManager

Giả sử client gọi endpoint riêng tư với HTTP Basic:

~~~http
GET /private HTTP/1.1
Host: localhost:8080
Authorization: Basic YWxpY2U6bGVhcm4xMjM=
~~~

Header ví dụ chứa Base64 của alice:learn123. Base64 là encoding, **không phải cơ chế mã hóa bảo mật**; credentials thật phải dùng HTTPS khi giao tiếp qua mạng.

Luồng khái quát:

~~~text
HTTP client
    |
    v
Servlet container
    |
    v
DelegatingFilterProxy -> FilterChainProxy
    |
    v
SecurityFilterChain phù hợp
    |
    v
BasicAuthenticationFilter
    |-- Đọc Authorization: Basic ...
    |-- Tạo UsernamePasswordAuthenticationToken chưa xác thực
    v
AuthenticationManager.authenticate(...)
    |
    v
ProviderManager
    |-- Chọn AuthenticationProvider có supports phù hợp
    v
DaoAuthenticationProvider
    |-- UserDetailsService.loadUserByUsername("alice")
    |-- PasswordEncoder.matches(raw, encoded)
    |-- Kiểm tra trạng thái tài khoản
    |-- Trả Authentication đã xác thực
    v
ProviderManager -> BasicAuthenticationFilter
    |-- Xử lý credentials sau xác thực
    |-- Filter đưa kết quả vào SecurityContext
    v
AuthorizationFilter
    |-- /private yêu cầu authenticated()
    +-- Cho phép -> DispatcherServlet -> Controller -> 200
    +-- Từ chối -> cơ chế xử lý từ chối
~~~

Đây là **sơ đồ theo trách nhiệm**, không liệt kê đầy đủ và tuyệt đối thứ tự mọi security filter. Luồng thực tế còn các filter về SecurityContext, CSRF, exception translation, anonymous authentication và nhiều cơ chế tùy cấu hình.

### Ai ghi SecurityContext?

**BasicAuthenticationFilter** nhận Authentication đã xác thực và thiết lập vào SecurityContext của request. **ProviderManager không tự đặt kết quả vào SecurityContextHolder chỉ vì authenticate trả về thành công**.

Một câu lệnh Java riêng:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

chỉ trả kết quả xác thực hoặc ném lỗi. Nó **không tự tạo HTTP session**, không tự lưu kết quả cho request kế tiếp, không tự gửi redirect và không tự phát hành access token.

### Khi request không có credentials

Nếu endpoint yêu cầu authenticated và chưa có danh tính hợp lệ, tầng authorization có thể từ chối; với Basic, AuthenticationEntryPoint thường phát HTTP 401/challenge. Với form login, người dùng có thể nhận 302 redirect tới trang đăng nhập. Mã HTTP này là trách nhiệm của **filter và handler**, không phải return value của AuthenticationManager.

## 5. AuthenticationManager là hợp đồng gì?

Interface AuthenticationManager có phương thức cốt lõi:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
~~~

Nó nhận một Authentication cần được xác minh. Khi thành công, trả Authentication đáng tin với danh tính và authorities phù hợp; khi thất bại, ném AuthenticationException.

Điều interface **không tự làm**: đọc HTTP request, chọn trang login, tạo cookie, đặt SecurityContext, lưu session, phân quyền URL hoặc kiểm tra ownerId của bản ghi. Những công việc đó nằm ở các thành phần khác.

Tách manager khỏi filter giúp nhiều cách thu thập credential (form, Basic hoặc token) dùng chung cơ chế kiểm chứng. Tách manager khỏi provider cũng cho phép thay cách xác thực mà không tự viết lại toàn bộ filter HTTP.

## 6. ProviderManager xử lý nhiều AuthenticationProvider như thế nào?

ProviderManager giữ danh sách AuthenticationProvider theo thứ tự và thực thi hợp đồng:

1. Kiểm tra **supports(authentication.getClass())** để biết provider nào có thể xử lý loại token.
2. Bỏ qua provider không hỗ trợ.
3. Gọi **authenticate(authentication)** với provider phù hợp.
4. Kết quả **Authentication khác null** thể hiện provider đã xác thực thành công; ProviderManager dùng kết quả đó.
5. Nếu provider trả **null**, provider này không giải quyết request và có thể thử provider phù hợp tiếp theo.
6. Nếu provider ném **AuthenticationException**, manager xử lý theo loại lỗi; một số lỗi có thể được lưu để thử provider sau, một số lỗi dừng ngay.
7. Nếu cấu hình parent AuthenticationManager, parent có thể được dùng trong trường hợp các provider hiện tại không giải quyết được.
8. Nếu không provider nào hỗ trợ token, có thể xuất hiện ProviderNotFoundException.

### supports() không kiểm tra mật khẩu

supports chỉ trả lời liệu provider **có thể xử lý một class Authentication** hay không. Một provider hỗ trợ UsernamePasswordAuthenticationToken vẫn có thể từ chối mật khẩu sai. Việc supports=true **không** biến request thành đã xác thực.

### Trả null và ném exception là hai hành vi khác nhau

**Trả null**: provider không đưa ra kết quả xác thực cho token này, cho phép cơ chế khác thử theo hợp đồng.

**Ném AuthenticationException**: provider phát hiện việc xác thực thất bại. Đối với password sai, thường gặp BadCredentialsException. Một số loại như **AccountStatusException** làm ProviderManager ngừng thử các provider còn lại theo quy định.

Không xây chuỗi fallback để một provider nghiêm ngặt từ chối password sai nhưng provider khác lại chấp nhận theo một cơ chế kém an toàn.

### Parent manager và thứ tự providers

Hai provider có thể cùng supports một class. Khi đó **thứ tự** và cách chúng trả về kết quả rất quan trọng. Nhiều SecurityFilterChain cũng có thể dùng manager riêng hoặc dùng parent chung trong cấu hình phù hợp. Hãy xác định chính xác manager của filter đang xử lý request.

### Xóa credentials và sự kiện

ProviderManager mặc định cố xóa credentials khỏi Authentication thành công nếu đối tượng hỗ trợ **CredentialsContainer**. Không nên giữ password trong SecurityContext để dùng về sau. Nếu cache UserDetails chia sẻ cùng tham chiếu đã bị xóa mật khẩu, cần giải quyết thiết kế cache chứ không vội tắt credential erasure.

ProviderManager có thể kết hợp AuthenticationEventPublisher cho sự kiện xác thực. Một manager được tạo thủ công cần kiểm tra cấu hình event publisher nếu hệ thống muốn audit; không giả định mọi event tự động xuất hiện hoặc log raw credentials.

## 7. DaoAuthenticationProvider, UserDetailsService và PasswordEncoder

**DaoAuthenticationProvider** là một AuthenticationProvider phổ biến cho username/password. Nó lấy thông tin user từ UserDetailsService và nhờ PasswordEncoder kiểm tra password mà client cung cấp.

~~~text
UsernamePasswordAuthenticationToken("alice", rawPassword)
                  |
                  v
DaoAuthenticationProvider
      |               |
      |               +--> UserDetailsService.loadUserByUsername("alice")
      |                            |
      |                            +--> UserDetails:
      |                                 username=alice
      |                                 encodedPassword=<hash>
      |                                 authorities=[ROLE_USER]
      |
      +--> PasswordEncoder.matches(rawPassword, encodedPassword)
      |
      +--> Các kiểm tra account enabled/non-locked/expiry
      |
      v
Authentication đã xác thực hoặc AuthenticationException
~~~

**UserDetailsService chỉ tải user**, không tự xác minh password. Việc tìm được username trong database không đồng nghĩa người gọi đang thực sự sở hữu tài khoản đó.

**PasswordEncoder** dùng **encode(raw)** khi tạo hash lưu trữ và **matches(raw, storedHash)** khi đăng nhập. Không so sánh raw password với storedHash bằng equals; không lưu mật khẩu plaintext.

Các cơ chế như BCrypt và Argon2 được dùng để hash mật khẩu với chi phí tính toán phù hợp. Cần cân nhắc thuật toán, chi phí, nâng cấp hash và chính sách quản lý tài khoản. Khi user bị khóa, vô hiệu hóa hoặc hết hạn, provider có thể từ chối ngay cả khi password khớp.

### Provider khác DaoAuthenticationProvider

| Provider | Cơ chế thường gặp |
| --- | --- |
| DaoAuthenticationProvider | Username/password và UserDetailsService |
| LdapAuthenticationProvider | Xác thực tích hợp LDAP theo cấu hình |
| JwtAuthenticationProvider | Xác minh JWT ở OAuth2 Resource Server theo decoder và validators |
| Custom AuthenticationProvider | Cơ chế credential riêng đã được thiết kế và kiểm chứng |

Không phải cứ thêm một AuthenticationProvider bean là mọi filter sẽ tự dùng nó đúng như mong muốn. Cần kiểm tra manager, filter chain, kiểu token và phạm vi áp dụng.

## 8. Ví dụ chạy được: tự ghép ProviderManager và DaoAuthenticationProvider

Ví dụ sử dụng **Spring Boot 3.3.x, Spring Security 6.3.x, Java 17+, Spring MVC/Servlet**. Hai tài khoản trong memory chỉ phục vụ học tập. Ta cố ý khai báo AuthenticationManager tường minh để thấy rõ manager chứa provider nào.

### Dependency

Trong dự án Spring Boot có Gradle Groovy DSL, bổ sung:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Đây là phần dependencies của một **dự án Boot đã tạo**, không phải file build.gradle đầy đủ. Version starter do Spring Boot quản lý.

### File Java hoàn chỉnh

Tạo file **src/main/java/com/example/authflow/AuthFlowApplication.java**:

~~~java
package com.example.authflow;

import java.security.Principal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
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
public class AuthFlowApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthFlowApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("learn123"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin123"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        // Spring Security 6.3: constructor nhận PasswordEncoder.
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider(encoder);
        dao.setUserDetailsService(users);
        return new ProviderManager(dao);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationManager manager) throws Exception {
        return http
            .authenticationManager(manager)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}

@RestController
class DemoController {

    @GetMapping("/public")
    String publicEndpoint() {
        return "public OK";
    }

    @GetMapping("/private")
    String privateEndpoint(Principal principal) {
        return "hello " + principal.getName();
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Class public trùng tên file; DemoController nằm cùng package nên Spring Boot component scanning phát hiện. Controller lấy Principal đã được filter xác thực.

**Các Bean hoạt động như sau:**

1. PasswordEncoder tạo BCryptPasswordEncoder.
2. UserDetailsService tạo Alice có ROLE_USER và admin có ROLE_ADMIN; password được hash trước khi lưu trong memory.
3. AuthenticationManager là ProviderManager, chứa một DaoAuthenticationProvider có UserDetailsService và PasswordEncoder.
4. HttpSecurity.authenticationManager(manager) gắn manager vào SecurityFilterChain đang xây dựng.
5. HTTP Basic được bật; form login tắt để bài tập quan sát 401 thay vì redirect.
6. GET /public cho anonymous, GET /private yêu cầu authenticated, GET /admin yêu cầu ROLE_ADMIN, còn lại denyAll.

**Về version:** Spring Security 6.3 có constructor DaoAuthenticationProvider(PasswordEncoder) và phương thức setUserDetailsService(UserDetailsService). Một số phiên bản Spring Security mới có constructor khác; luôn tra tài liệu đúng phiên bản dependency trước khi nâng cấp. Code này thiết kế cho Spring Boot 3.3.x / Security 6.3.x.

### Chạy từ thư mục dự án

~~~bash
./gradlew bootRun
~~~

Trên PowerShell dùng **.\gradlew.bat bootRun**. Sau khi server khởi động ở localhost:8080, thử:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Trong PowerShell có thể dùng **curl.exe** nếu curl là alias. Không dùng password demo hoặc HTTP Basic qua HTTP không mã hóa trên mạng thật.

| Request | Status dự kiến | Nội dung / nguyên nhân |
| --- | --- | --- |
| /public không credential | 200 | Body: public OK |
| /private không credential | 401 | Thiếu xác thực |
| /private với alice:wrong | 401 | Provider từ chối credentials |
| /private với alice:learn123 | 200 | Body: hello alice |
| /admin với alice:learn123 | 403 | Đúng credentials, thiếu ROLE_ADMIN |
| /admin với admin:admin123 | 200 | Body: admin OK |

Các kết quả trên **được suy ra từ cấu hình**, không phải log một tiến trình đã chạy trong bài viết. Nếu thêm filter/chain/handler hoặc proxy riêng, cần kiểm thử kết quả thực tế.

## 9. Ba đường đi quan trọng

### 9.1. Đăng nhập đúng và đủ quyền

~~~text
curl -u alice:learn123 GET /private
     |
     v
BasicAuthenticationFilter đọc header
     |
     v
Token UsernamePasswordAuthenticationToken chưa xác thực
     |
     v
ProviderManager -> DaoAuthenticationProvider
     |
     +-- loadUserByUsername("alice")
     +-- PasswordEncoder.matches(...) = true
     |
     v
Authentication(principal=alice, ROLE_USER, authenticated=true)
     |
     v
Filter thiết lập SecurityContext của request
     |
     v
AuthorizationFilter kiểm tra authenticated()
     |
     v
DemoController trả "hello alice" -> HTTP 200
~~~

### 9.2. Sai password

~~~text
curl -u alice:wrong GET /private
     |
     v
BasicAuthenticationFilter -> ProviderManager
     |
     v
DaoAuthenticationProvider: password không khớp
     |
     v
AuthenticationException
     |
     v
AuthenticationEntryPoint / filter xử lý lỗi -> HTTP 401
~~~

Controller không được gọi. Lỗi xác thực có thể còn do tài khoản khóa/hết hạn, sai UserDetailsService hoặc PasswordEncoder, không chỉ password sai.

### 9.3. Đúng password nhưng thiếu quyền

~~~text
curl -u alice:learn123 GET /admin
     |
     v
ProviderManager và DaoAuthenticationProvider thành công
     |
     v
Authentication có ROLE_USER
     |
     v
AuthorizationFilter cần ROLE_ADMIN
     |
     v
Từ chối -> HTTP 403
~~~

AuthenticationManager đã làm đúng công việc ở nhánh này. Lỗi 403 là quyết định authorization, không phải bằng chứng rằng provider kiểm tra password thất bại.

## 10. Form login và HTTP Basic có dùng chung manager được không?

Có. Cả hai thường đưa UsernamePasswordAuthenticationToken tới AuthenticationManager. Khác biệt chính là **filter nhận credential** và **hành vi HTTP sau khi xác thực**.

| Thuộc tính | HTTP Basic | Form login |
| --- | --- | --- |
| Nguồn credential | Authorization: Basic | Form POST login |
| Filter | BasicAuthenticationFilter | UsernamePasswordAuthenticationFilter |
| Token điển hình | UsernamePasswordAuthenticationToken | UsernamePasswordAuthenticationToken |
| Provider điển hình | DaoAuthenticationProvider | DaoAuthenticationProvider |
| Khi chưa đăng nhập | 401/challenge | Có thể 302 redirect trang login |
| Khi thành công | Tiếp tục request | Success handler, thường redirect |
| Trạng thái đăng nhập | Client thường gửi Basic ở mỗi request | Thường lưu bằng session và SecurityContextRepository |

Đừng nói HTTP Basic **luôn stateless** chỉ vì đã bật httpBasic(). Session, request cache hoặc filter khác còn tùy policy. Nếu cần API stateless, phải thiết kế SessionCreationPolicy và các thành phần liên quan rõ ràng.

Một flow form login còn có CSRF, session fixation protection, login success/failure handler và context persistence. AuthenticationManager chỉ kiểm chứng credentials; nó không thay thế các phần đó.

## 11. Cấu hình nhiều manager, nhiều provider và chain

Một hệ thống có thể có khu vực admin dùng form login, API dùng JWT Bearer và dịch vụ nội bộ dùng cơ chế khác. Có thể thiết kế các SecurityFilterChain có manager riêng, hoặc manager chung trong trường hợp thích hợp.

Khi debug, luôn hỏi:

1. Request được SecurityFilterChain nào chọn?
2. Filter nào đọc credential?
3. Filter tạo Authentication class nào?
4. Filter đang tham chiếu AuthenticationManager nào?
5. Manager chứa các AuthenticationProvider nào và theo thứ tự nào?
6. Provider nào có supports=true?
7. Thành công, null hay AuthenticationException?
8. Kết quả có được filter đưa vào SecurityContext?
9. AuthorizationFilter yêu cầu authority nào?

Đăng ký bean AuthenticationProvider nhưng quên gắn vào manager đang dùng, hoặc đặt thứ tự chain sai, có thể khiến ứng dụng không gọi provider dù đã viết code đúng.

### Có nên tự viết AuthenticationProvider?

Chỉ khi cơ chế sẵn có không phù hợp với giao thức xác thực cần thiết. Interface có hai phương thức chính:

~~~java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;

boolean supports(Class<?> authentication);
~~~

Đây là **chữ ký minh họa**, không phải file Java khai báo lại interface có sẵn của Spring Security.

Nếu xây custom provider, cần xác minh nguồn credential đáng tin, không lấy role từ client, xử lý credential expiry/revocation khi áp dụng, bảo vệ khóa/secret, định nghĩa rõ null vs exception, tránh fallback kém an toàn và kiểm thử cả nhánh lỗi.

Đừng viết một provider đánh dấu authenticated=true dựa trên tên người dùng tự khai hoặc API key hard-code. Đối với LDAP, OAuth2, JWT và login thường gặp, ưu tiên cơ chế Spring Security hỗ trợ.

## 12. SecurityContext và phiên đăng nhập

SecurityContextHolder là điểm truy cập SecurityContext hiện hành trong stack Servlet. Filter xác thực có thể cập nhật Authentication ở context; cách lưu/khôi phục context qua HTTP request phụ thuộc **SecurityContextRepository, session policy và filter tương ứng**.

Một lời gọi riêng:

~~~java
Authentication verified = manager.authenticate(attempt);
~~~

**không tự tạo cookie, không tự phát JWT, không tự lưu session và không tự thiết lập context**. Custom login endpoint cần triển khai cả phần sau xác thực, xử lý lỗi, session/token, CSRF theo mô hình browser, logout và bảo mật credentials.

Nếu dùng luồng Spring Security tích hợp, để filter đảm nhiệm phần lifecycle đúng thay vì tự đặt SecurityContextHolder trong Controller rồi cho rằng request sau sẽ tự có danh tính.

## 13. Lỗi thường gặp và cách kiểm tra

| Hiện tượng / ngộ nhận | Điểm cần kiểm tra |
| --- | --- |
| UserDetailsService tìm được user nên coi là đăng nhập | Chưa xác minh password; cần DaoAuthenticationProvider/PasswordEncoder |
| supports=true nên token đã hợp lệ | supports chỉ nhận diện khả năng xử lý class |
| ProviderManager luôn thử mọi provider | Success và một số loại exception dừng việc thử |
| Bean AuthenticationManager tồn tại nhưng không được gọi | Filter/chain có thể dùng manager khác |
| User đúng password nhưng bị 403 | Kiểm tra authorities và authorization rule |
| /private trả 401 | Kiểm tra credential header, provider, account status, encoder |
| Password hash không khớp | Kiểm tra encode/matches và thuật toán hash lưu trữ |
| Authentication được tạo trong Controller nhưng request sau vẫn anonymous | Chưa xử lý SecurityContextRepository/session |
| Tưởng role là quyền sở hữu tài nguyên | Cần kiểm tra ownerId và dữ liệu nghiệp vụ |
| Credentials bị xóa khỏi UserDetails cache | Kiểm tra tham chiếu cache và credential erasure |
| Dùng HttpSecurity ở ứng dụng WebFlux | Cần ServerHttpSecurity và reactive security context |
| Ghi raw credentials vào log debug | Loại bỏ log password/token, bảo vệ log |

Khi bật log debug trong môi trường phát triển, tránh ghi raw Authorization, password, token, cookie hoặc đối tượng chứa secret. Tốt hơn là log **tên provider, loại Authentication và kết quả** ở mức phù hợp, không ghi credential.

## 14. Bài tập tự kiểm tra

**Câu 1.** Filter HTTP Basic và DaoAuthenticationProvider khác nhau thế nào?  
**Đáp:** Filter đọc header, tạo token, gọi manager và xử lý HTTP/context; provider kiểm tra username/password nhờ nguồn user và encoder.

**Câu 2.** ProviderManager trả null có nghĩa xác thực thành công không?  
**Đáp:** Không. Provider có thể trả null để provider khác thử; chỉ Authentication thành công khác null mới là kết quả xác thực.

**Câu 3.** Provider ném AccountStatusException có nhất thiết được bỏ qua để thử hết danh sách không?  
**Đáp:** Không. Đây là nhóm ngoại lệ có thể dừng quá trình.

**Câu 4.** Alice có ROLE_USER, đăng nhập đúng vào /admin yêu cầu ADMIN. Vì sao bị 403?  
**Đáp:** Authentication thành công; authorization từ chối vì thiếu ROLE_ADMIN.

**Câu 5.** Tự gọi manager.authenticate() trong Controller có tự đăng nhập cho browser ở request sau?  
**Đáp:** Không. Cần lưu và phục hồi SecurityContext hoặc cơ chế session/token phù hợp cùng các bước bảo mật khác.

**Câu 6.** Tại sao không dùng trực tiếp loadUserByUsername() rồi trả thành công?  
**Đáp:** Chỉ tìm thấy user, chưa kiểm tra credential của client.

**Câu 7.** Vì sao code DaoAuthenticationProvider có thể cần sửa khi đổi Spring Security version?  
**Đáp:** Constructor và API có thể thay đổi. Ví dụ dùng API 6.3 và phải đối chiếu Javadoc của dependency thực tế.

**Câu 8.** Một API xác thực Alice đúng nhưng trả đơn hàng của Bob. Manager sai ở đâu?  
**Đáp:** Chưa đủ dữ kiện kết luận manager sai; rất có thể thiếu authorization theo bản ghi ở tầng Service.

## 15. Tài liệu chính thức

- Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/architecture.html
- Username/Password Authentication: https://docs.spring.io/spring-security/reference/6.3/servlet/authentication/passwords/index.html
- DaoAuthenticationProvider API 6.3.3: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/authentication/dao/DaoAuthenticationProvider.html
- ProviderManager API 6.3.x: https://docs.spring.io/spring-security/site/docs/6.3.x/api/org/springframework/security/authentication/ProviderManager.html
- AuthenticationProvider API 6.3.9: https://docs.spring.io/spring-security/site/docs/6.3.9/api/org/springframework/security/authentication/AuthenticationProvider.html
- BasicAuthenticationFilter API 6.3.3: https://docs.spring.io/spring-security/site/docs/6.3.3/api/org/springframework/security/web/authentication/www/BasicAuthenticationFilter.html
- Authorization Architecture: https://docs.spring.io/spring-security/reference/6.3/servlet/authorization/architecture.html
