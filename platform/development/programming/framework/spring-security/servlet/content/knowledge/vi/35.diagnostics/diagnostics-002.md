# Bật DEBUG, TRACE hoặc chế độ debug trong môi trường kiểm soát — Spring Security Servlet

## 1. Vấn đề: khi HTTP status không đủ để chẩn đoán

Trong ứng dụng **Spring Security Servlet**, cùng một triệu chứng HTTP có thể xuất phát từ nhiều cơ chế:

- **401 Unauthorized**: chưa có Authentication hợp lệ, thông tin xác thực không đúng hoặc AuthenticationEntryPoint đã phản hồi.
- **403 Forbidden**: người dùng đã xác thực nhưng không được phép, **hoặc** request thay đổi trạng thái bị CSRF protection chặn, **hoặc** một thành phần khác từ chối.
- **302 Redirect**: web application chuyển tới form login, OAuth2/OIDC login hoặc một đích khác; không đồng nghĩa với 401.
- **400 Bad Request**: đường dẫn bị HttpFirewall hoặc servlet container từ chối; không nhất thiết lỗi nằm ở Controller.
- **404 Not Found**: thiếu route, sai context path/prefix hoặc một lớp khác xử lý request, không đủ chứng minh FilterChainProxy đã chạy.
- **200 OK** trên endpoint công khai nhưng không có các security headers mong đợi: request có thể đi qua một filter chain khác, bị bỏ qua hoàn toàn, hoặc header bị proxy ghi đè.

Khi xảy ra các tình huống đó, **DEBUG/TRACE logging** giúp quan sát các lớp **FilterChainProxy**, authentication, authorization, exception handling, method security và xử lý request. Tuy nhiên việc bật quá rộng có thể ghi lại thông tin nhạy cảm, tạo log lớn, làm chậm hệ thống và vi phạm quy tắc bảo mật dữ liệu.

**Mục tiêu của bài:** biết nên bật mức log nào, bật ở logger nào, dùng Spring Security web debug filter khi nào, phân tích log ra sao, thử lại bằng request có kiểm soát và khôi phục cấu hình an toàn sau khi chẩn đoán.

Bối cảnh là **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet**, không dùng WebFlux. Cú pháp cấu hình và tên class ví dụ chỉ áp dụng cho các phiên bản hỗ trợ tương ứng; đầu ra log thực tế có thể thay đổi theo từng release.

## 2. Phân biệt DEBUG, TRACE và chế độ web debug

### 2.1. Logger level của Spring Boot/SLF4J

Spring Boot thường quản lý log theo category/package/class thông qua logging framework được tích hợp (mặc định với starter là Logback). Một logger có mức hiệu lực như **INFO**, **DEBUG** hoặc **TRACE**.

| Mức | Nội dung thường hữu ích | Chi phí và chú ý |
| --- | --- | --- |
| **INFO** | Sự kiện chung và các cảnh báo quan trọng | Phù hợp làm nền trong production, nhưng thường không có đủ chi tiết cho lỗi filter |
| **DEBUG** | Thông tin lựa chọn security chain, request đang được bảo vệ, một số quyết định xác thực/phân quyền | Tăng log volume; thông tin chi tiết tùy class/version |
| **TRACE** | Chi tiết nhiều bước hơn, ví dụ gọi qua từng filter hoặc các decision points | Rất nhiều log; chỉ bật trên phạm vi hẹp và trong thời gian ngắn |
| **WARN/ERROR** | Cảnh báo và lỗi | Không đủ để hiểu toàn bộ đường đi của một request thành công hay bị deny |

**Mức TRACE bao gồm các thông điệp DEBUG cùng với các thông điệp TRACE của logger được bật**. Nhưng không phải mọi class đều ghi log ở mọi mức, và log không phải một hợp đồng API ổn định. Đừng viết hệ thống kiểm thử dựa trên một câu log cụ thể rồi cho rằng Spring Security bắt buộc luôn phát câu đó.

Bật log chung:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Điều này thường làm các logger bên dưới **org.springframework.security** ghi thông tin DEBUG, không có nghĩa ghi toàn bộ HTTP payload; cũng **không bảo đảm** không có bí mật xuất hiện từ thành phần khác.

Muốn xem chi tiết filter chain mà không bật TRACE cả ứng dụng:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Chọn logger hẹp trước khi mở rộng, ví dụ **org.springframework.security.web**, **org.springframework.security.authorization** hoặc **org.springframework.security.authentication**. Trong một ứng dụng thật, hãy dựa vào tên logger thực sự xuất hiện để điều chỉnh tiếp, tránh đoán rằng một package luôn sinh đúng một loại sự kiện.

### 2.2. Spring Security web debug filter: khác logger TRACE

Spring Security Servlet còn có **chế độ debug cho tầng web security**, được bật thông qua **WebSecurityCustomizer / WebSecurity.debug(true)** hoặc một cách cấu hình tương đương như **@EnableWebSecurity(debug = true)** ở cấu hình phù hợp.

Chế độ này có thể tạo **DebugFilter** với thông tin rất chi tiết về request và security filter chain, hữu ích khi không biết request đang đi vào chain nào. **Nó có cảnh báo an toàn đặc biệt: không dành cho môi trường production.** Output có thể chứa headers, thông tin request hoặc security details nhạy cảm. Đây **không phải** một bản thay thế trung tính cho INFO logging.

Ba lựa chọn khác nhau:

| Cách bật | Ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| **logging.level.org.springframework.security=DEBUG** | Bật DEBUG cho logger category | Bước đầu khi cần chẩn đoán; giới hạn bằng profile và thời gian |
| **logging.level.org.springframework.security.web.FilterChainProxy=TRACE** | Theo dõi chi tiết FilterChainProxy | Chỉ request thử nghiệm và logger hẹp |
| **web.debug(true)** hoặc **@EnableWebSecurity(debug=true)** | Bật debug filter của Spring Security Web | Chỉ môi trường local/staging cô lập, tuyệt đối không mặc định bật production |

**Spring Boot --debug / debug=true là một chuyện khác.** Nó chủ yếu mở rộng chẩn đoán của Spring Boot, bao gồm báo cáo điều kiện auto-configuration và một số logger lõi; không thể suy ra các filter của Spring Security đã bật TRACE hoặc DebugFilter. Để chẩn đoán security, cấu hình **logging.level...** hoặc web debug một cách tường minh.

### 2.3. Không có “một nút DEBUG” an toàn cho mọi vấn đề

Một lỗi 401 có thể cần logger authentication; một lỗi 403 vì quyền cần logger authorization; một request không chọn chain cần xem FilterChainProxy và securityMatcher; một request bị firewall chặn có thể cần **org.springframework.security.web.firewall** hoặc log container; còn request chưa đến ứng dụng thì không có log Spring Security để xem.

**Chiến lược tốt** là bắt đầu từ trạng thái HTTP, một request tái hiện nhỏ, xác định tầng nghi ngờ rồi mới tăng log level ở category tương ứng. Đừng bật **logging.level.root=TRACE** hay đưa mọi header/token vào log để “cho chắc”.

## 3. Môi trường kiểm soát là gì?

“Chỉ bật trong môi trường kiểm soát” phải có quy tắc vận hành cụ thể, không chỉ thêm chữ **DEBUG** vào tên profile.

Một môi trường chẩn đoán thích hợp cần:

1. **Cô lập truy cập**: local, staging riêng hoặc test environment có hạn chế mạng/identity; không có lưu lượng công khai không liên quan.
2. **Dữ liệu thử nghiệm**: tài khoản giả, secret/token thử nghiệm, dữ liệu không phải thông tin cá nhân production; hạn chế dùng bản sao production.
3. **Phạm vi logger nhỏ**: một package/class và một khoảng thời gian ngắn thay vì toàn bộ root logger.
4. **Giới hạn thu thập**: không sao chép log chi tiết lên issue tracker công khai, chat hoặc dashboard mà mọi thành viên có thể đọc; quản lý retention và access.
5. **Không ghi credentials**: không log Authorization, Cookie, Set-Cookie, token, session ID, password, OTP, OAuth2 code/state hoặc request body nhạy cảm. Đừng giả định log mặc định luôn che mọi trường.
6. **Có kế hoạch hoàn nguyên**: ghi rõ mức log trước đó, người bật, thời điểm bật, thời điểm tắt và cách xác minh đã tắt.
7. **Có phương án ứng phó**: nếu lỡ ghi token/session/secret, xem đó là sự kiện cần bảo vệ log và đánh giá thu hồi/rotation, không chỉ xóa một dòng console.

**Không dùng DebugFilter của Spring Security trên production** chỉ vì cần xử lý một sự cố khẩn cấp. Có thể chọn telemetry ít xâm lấn hơn như request ID, HTTP status, security event được tổng hợp và logger hẹp đã kiểm soát. Đối với môi trường production, mọi thay đổi log cần quy trình phê duyệt và giới hạn dữ liệu rõ ràng.

## 4. Cấu hình profile chẩn đoán để không ảnh hưởng mặc định

### 4.1. Tách cấu hình log khỏi application.yml production

Giữ **src/main/resources/application.yml** cho cấu hình chung, không bật TRACE toàn ứng dụng. Tạo tệp riêng:

**src/main/resources/application-security-diagnostics.yml**

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Spring Boot sẽ áp file này khi profile **security-diagnostics** được kích hoạt. Việc tách profile giúp team thấy rõ cấu hình chỉ dành cho chẩn đoán; nhưng **profile không tự tạo ranh giới bảo mật**. Tên profile không ngăn được deploy nhầm lên production.

Chạy trong dự án có Gradle wrapper:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=security-diagnostics'
~~~

Trên Windows PowerShell (trong thư mục gốc dự án):

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=security-diagnostics"
~~~

**Không** nên chỉnh production application.yml thành TRACE rồi quên revert. Với một lỗi ở authorization, có thể thay FilterChainProxy TRACE bằng logger hẹp của **org.springframework.security.authorization**. Tên logger và event chi tiết phụ thuộc vào tính năng Spring Security đang dùng.

### 4.2. Bật tạm logger bằng startup argument

Khi chỉ cần một category:

~~~bash
./gradlew bootRun --args='--logging.level.org.springframework.security=DEBUG'
~~~

Hoặc chỉ bật TRACE cho FilterChainProxy trong lần chạy thử:

~~~bash
./gradlew bootRun --args='--logging.level.org.springframework.security.web.FilterChainProxy=TRACE'
~~~

Đây là **startup configuration**; các argument của ví dụ làm thay đổi ứng dụng chạy ở lần khởi động đó, không phải đang thay đổi một tiến trình khác. Cẩn trọng với môi trường k8s/CI: các argument có thể được giữ trong deployment manifest, process metadata hoặc job log. Đừng đặt secret ở command line.

### 4.3. Bật web debug chỉ ở một profile cách ly

Nếu thực sự cần thông tin DebugFilter, một cấu hình Spring có thể là:

**src/main/java/com/example/securitydiagnostics/WebDebugOnlyConfiguration.java**

~~~java
package com.example.securitydiagnostics;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;

@Configuration(proxyBeanMethods = false)
@Profile("security-debug")
public class WebDebugOnlyConfiguration {

    @Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        // Chỉ local/staging được cô lập, KHÔNG bật trong production.
        return web -> web.debug(true);
    }
}
~~~

Trong môi trường Spring Boot Servlet có cấu hình Spring Security Web phù hợp, bean WebSecurityCustomizer sẽ được framework áp dụng cho **WebSecurity**. Nếu dùng profile này, hãy thực sự kiểm tra debug filter có chạy và xem output riêng trong môi trường test. Không trộn profile **security-debug** vào profile mặc định của hệ thống.

Khi cần tái hiện bằng cách bật cả hai profile:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=security-diagnostics,security-debug'
~~~

**Cảnh báo:** Web debug filter có thể làm lộ thông tin nhạy cảm từ request hoặc SecurityContext. Không phát log này tới hệ thống tập trung nếu chưa có bảo vệ truy cập, chính sách lưu giữ và biện pháp lọc phù hợp. Việc log framework có thể che một số thông tin ở một phiên bản không đủ để bảo đảm mọi bản ghi đều vô hại.

### 4.4. Vì sao không lấy Boot --debug làm phép thử security?

Lệnh:

~~~bash
./gradlew bootRun --args='--debug'
~~~

có thể cung cấp báo cáo điều kiện auto-configuration hoặc log bổ sung của framework, hữu ích khi bean SecurityFilterChain không được tạo như dự tính. Nhưng nếu muốn nhìn từng filter đang thực thi, **chỉ --debug là không đủ cơ sở để khẳng định**. Hãy quan sát các logger Spring Security mục tiêu và lựa chọn web debug trong môi trường được kiểm soát nếu cần.

## 5. Ứng dụng demo Spring Boot 3.x / Security 6.x / Java 17+

Để thấy sự khác nhau giữa authentication và authorization, tạo ba endpoint:

- **GET /public/ping**: công khai, trả **pong**.
- **GET /private/me**: phải đăng nhập, trả tên người dùng.
- **GET /private/admin**: yêu cầu role **ADMIN**.

Ví dụ sử dụng **HTTP Basic** và một user giả để không cần IdP/SSO/JWT. Trong hệ thống thực, phương thức đăng nhập có thể khác; bài học về logger và filter chain vẫn áp dụng, nhưng loại log và entry point có thể thay đổi.

### 5.1. Gradle dependencies

Trong **build.gradle** của một dự án Boot 3.x đã có Gradle wrapper:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đảm bảo dự án dùng Java 17+ và cấu hình plugin/dependency management Spring Boot theo phiên bản đang sử dụng. Khối trên là phần **dependencies** cần thêm, không phải toàn bộ file build.gradle độc lập.

### 5.2. Main application và SecurityFilterChain

Tệp **src/main/java/com/example/securitydiagnostics/SecurityDiagnosticsApplication.java**:

~~~java
package com.example.securitydiagnostics;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SecurityDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityDiagnosticsApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET,
                                "/private/me").authenticated()
                        .requestMatchers(HttpMethod.GET,
                                "/private/admin").hasRole("ADMIN")
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories
                .createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService demoUsers(PasswordEncoder encoder) {
        // User chỉ dành cho local test, tuyệt đối không đưa lên public.
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-demo-password"))
                        .roles("USER")
                        .build());
    }
}

@RestController
class DiagnosticController {

    @GetMapping("/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/private/me")
    String currentUser(Authentication authentication) {
        return "hello " + authentication.getName();
    }

    @GetMapping("/private/admin")
    String admin() {
        return "admin only";
    }
}
~~~

**Điều cần nắm từ cấu hình:**

1. **Spring Security filters** vẫn áp dụng cho public endpoint. **permitAll()** không giống **web.ignoring()**: request được phép truy cập công khai vẫn có thể nhận các security headers của Spring Security.
2. Endpoint **/private/me** cần Authentication; thiếu credential trong cấu hình HTTP Basic thường dẫn đến **401**.
3. User alice có **ROLE_USER** chứ không có **ROLE_ADMIN**. Vì vậy GET **/private/admin** với Basic credentials hợp lệ dự kiến nhận **403**.
4. **Không có endpoint sửa trạng thái** trong ví dụ: không cần tắt CSRF. Trong ứng dụng có cookie/session và POST/PUT/DELETE, CSRF failure là một hướng chẩn đoán riêng.
5. Password ở đây chỉ là dữ liệu demo trong môi trường local; không đặt credential production trong source code, README hoặc command mẫu.
6. Cấu hình security giữ chức năng authorization ngay cả khi bật logging. **Bật DEBUG không bao giờ là cách cho qua một lỗi 401/403** và không nên sửa bằng permitAll để “test cho dễ”.

### 5.3. Chạy ba request đối chứng

Khởi động app với profile diagnostics rồi dùng terminal khác.

GET public:

~~~bash
curl -i 'http://localhost:8080/public/ping'
~~~

Kỳ vọng: **200** và body **pong**.

GET private không có credential:

~~~bash
curl -i 'http://localhost:8080/private/me'
~~~

Kỳ vọng: **401 Unauthorized**, thường có **WWW-Authenticate: Basic ...**. Body và chi tiết header còn tùy cấu hình và phiên bản.

GET private với user demo:

~~~bash
curl -i -u alice:local-demo-password \
  'http://localhost:8080/private/me'
~~~

Kỳ vọng: **200** và body **hello alice**.

GET admin với user demo thiếu quyền:

~~~bash
curl -i -u alice:local-demo-password \
  'http://localhost:8080/private/admin'
~~~

Kỳ vọng: **403 Forbidden**. Việc này là hành vi bảo mật đúng của policy, không phải sự cố phải “sửa” bằng cách tắt authorization.

**Lưu ý về an toàn:** Cú pháp **-u alice:...** chỉ sử dụng credential giả trên localhost. Với credentials thật, không đặt mật khẩu trong command line hoặc CI log vì có thể xuất hiện trong shell history/process listing; hãy sử dụng kênh truyền bí mật an toàn và kết nối HTTPS.

## 6. Cách đọc DEBUG/TRACE theo đường đi của request

### 6.1. FilterChainProxy và việc chọn chain

**FilterChainProxy** là trung tâm của cơ chế lọc Servlet Spring Security. Khi TRACE được bật, bạn có thể thấy thông tin kiểu:

~~~text
DEBUG ... FilterChainProxy : Securing GET /private/me
TRACE ... FilterChainProxy : Invoking ... (filter ...)
DEBUG ... FilterChainProxy : Secured GET /private/me
~~~

Đây là **mẫu minh họa kiểu log**, không phải output cam kết sẽ xuất hiện nguyên văn. Tên filter, số thứ tự, logger, thread, timestamp, cách format và sự có mặt của từng dòng thay đổi theo Spring Security version và cấu hình.

Các câu hỏi nên trả lời:

- Request có đến **FilterChainProxy** không?
- Matcher nào chọn SecurityFilterChain nào?
- Những filter nào xuất hiện trong chain đó?
- Request bị dừng ở Authentication, Authorization, CSRF, ExceptionTranslationFilter hay bị reject trước đó?
- Request có đi tiếp vào DispatcherServlet/controller không?

Nếu **không thấy log** dù đã bật đúng category, đừng kết luận “security không có tác dụng”. Có thể logger bị override, request chưa tới ứng dụng, một filter khác chặn sớm, test không gắn filter chain, hoặc log bị ghi ở nơi khác.

### 6.2. Authentication: vì sao 401?

Một request private thiếu Basic credentials thường đi qua các bước:

~~~text
GET /private/me
   │
   ├─ SecurityContext chưa có user đã được xác thực
   ├─ Authentication-related filters không tạo Authentication hợp lệ
   ├─ Authorization yêu cầu authenticated()
   └─ ExceptionTranslationFilter / AuthenticationEntryPoint
        → 401 + WWW-Authenticate (với HTTP Basic)
~~~

Đừng dựa vào một message “AnonymousAuthenticationFilter ...” để khẳng định nguyên nhân cuối cùng. Xem cả đường đi filter, security rule, entry point và HTTP response.

Tùy kiểu đăng nhập:

- **HTTP Basic**: thiếu hoặc sai credentials thường là **401**.
- **formLogin**: truy cập URL bảo vệ từ browser có thể là **302 đến /login**.
- **OAuth2 Resource Server Bearer**: token không hợp lệ có thể là **401** và header **WWW-Authenticate: Bearer**.
- **OAuth2 Login/OIDC**: có thể có redirect tới authorization endpoint của IdP; phải bảo vệ **code, state, nonce, client_secret, tokens** trong log.

Đừng tự chuyển mọi status về một kiểu: cùng một policy có thể tạo biểu hiện HTTP khác nhau tùy AuthenticationEntryPoint và app type.

### 6.3. Authorization: vì sao 403?

Request với alice tới **/private/admin** có Authentication nhưng thiếu role cần thiết. Security HTTP authorization xét **hasRole("ADMIN")**, trong khi alice chỉ có ROLE_USER, nên request bị deny.

Ở lớp authorization, log thường giúp xác định **rule đang áp dụng** và trạng thái quyết định; nhưng log message không nên là nguồn chứng cứ duy nhất. Chứng minh bằng test có user đủ quyền và thiếu quyền qua cùng endpoint.

**403 không chỉ có nghĩa sai role.** Một POST có thể bị CSRF chặn trước; CORS preflight sai origin cũng có thể trả 403; method security có thể ném AccessDeniedException từ service. Phải xác định filter/handler hoặc tầng thực sự tạo response.

### 6.4. Bẫy nhiều SecurityFilterChain

Nếu hệ thống có nhiều chain:

~~~text
Request /api/orders
   → chain với securityMatcher("/api/**")
   → Bearer authentication

Request /admin/panel
   → chain với securityMatcher("/admin/**")
   → form login

Request /unknown
   → chain fallback (nếu có)
~~~

Cấu hình **securityMatcher** quyết định **toàn bộ chain có áp dụng** hay không; cấu hình **requestMatchers** bên trong authorizeHttpRequests quyết định quyền khi request đã nằm trong chain. Một URL không khớp bất kỳ chain nào có thể không nhận đúng filter/header bạn nghĩ.

Khi chẩn đoán, kiểm tra:

1. Thứ tự chain (**@Order**, matcher ưu tiên).
2. Matcher nào nhận URL thực tế, bao gồm context path/path prefix sau proxy.
3. AuthenticationEntryPoint của chain được chọn.
4. Có một fallback chain không; không mặc định rằng chain dùng cho **/api/** cũng bảo vệ **/admin/**.
5. Có cấu hình **web.ignoring()** hay không. Nếu URL bị ignore, request có thể không qua các security filters/header writers.
6. Nếu không thấy controller được gọi, request bị chặn trước hay chỉ bị deny trong một method-security proxy?

DEBUG/TRACE hỗ trợ trả lời, nhưng **thêm integration test cho từng đường** mới biến kết luận thành một kiểm soát có thể lặp lại.

### 6.5. CSRF, CORS và HttpFirewall

Các lỗi này có thể giống authorization nếu chỉ xem status:

| Nhóm | Dấu hiệu | Điểm kiểm tra |
| --- | --- | --- |
| **CSRF** | POST/DELETE từ cookie session trả 403, GET vẫn hoạt động | CsrfFilter, token repository, session/cookie, method an toàn hay không |
| **CORS preflight** | OPTIONS từ browser bị 401/403 dù GET có token hợp lệ | CorsFilter, CorsConfigurationSource, Origin, Access-Control-Request-Method/Headers |
| **HttpFirewall** | Path có semicolon/%2F/%5C/dot segments bị từ chối | RequestRejectedException, StrictHttpFirewall và parsing ở container |
| **Security headers** | Response 200 nhưng thiếu CSP/HSTS hoặc nosniff | Header writers của chain, HTTPS detection, reverse proxy, response do edge tạo |
| **Method security** | HTTP chain cho phép nhưng service method ném AccessDeniedException | @EnableMethodSecurity, @PreAuthorize, AOP proxy/self-invocation |
| **Session/async context** | Request chính có user nhưng worker thread không thấy Authentication | SecurityContextHolder ThreadLocal, executor propagation |

**HttpFirewall** có thể xử lý request trước khi chọn filter chain. Nếu container hoặc reverse proxy đã từ chối URI không chuẩn, log ở Spring Security sẽ không có sự kiện tương ứng. Dùng raw HTTP test và log tầng ngoài để xác định nơi request bị chặn.

**HSTS** thường chỉ được phát cho secure request. Nếu TLS kết thúc ở reverse proxy và backend nhìn HTTP nội bộ, thiếu HSTS có thể liên quan trusted forwarded headers hoặc edge configuration, không phải vì DEBUG chưa đủ mạnh.

## 7. Test bằng MockMvc: xác minh hành vi thay vì khẳng định nội dung log

Một hệ thống quan sát đáng tin nên có cả **diagnostic logging** và **regression tests**. Logging giúp điều tra, còn test quyết định cấu hình bảo mật hoạt động đúng.

Tạo **src/test/java/com/example/securitydiagnostics/SecurityDiagnosticsTest.java**:

~~~java
package com.example.securitydiagnostics;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(properties = {
        "logging.level.org.springframework.security=DEBUG"
})
@AutoConfigureMockMvc
class SecurityDiagnosticsTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointWorksWithoutAuthentication() throws Exception {
        mvc.perform(get("/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void privateEndpointWithoutCredentialsIs401() throws Exception {
        mvc.perform(get("/private/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsAuthenticate() throws Exception {
        mvc.perform(get("/private/me")
                    .with(httpBasic(
                            "alice", "local-demo-password")))
                .andExpect(status().isOk())
                .andExpect(content().string("hello alice"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleIs403() throws Exception {
        mvc.perform(get("/private/admin")
                    .with(httpBasic(
                            "alice", "local-demo-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/private/me")
                    .with(httpBasic(
                            "alice", "incorrect-password")))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests com.example.securitydiagnostics.SecurityDiagnosticsTest
~~~

PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.securitydiagnostics.SecurityDiagnosticsTest
~~~

**Kỳ vọng:** năm test đạt trên project Spring Boot 3.x/Spring Security 6.x được cấu hình đúng. Chúng kiểm tra HTTP **200/401/403** của các request khác nhau, chứ **không khẳng định một thông báo DEBUG cụ thể**. Không có test nào ở đây chạy DebugFilter vì profile **security-debug** không được kích hoạt.

**Đây là kỳ vọng tĩnh của ví dụ, không phải kết quả đã chạy.** Nếu bạn muốn kiểm tra log, có thể dùng output-capture trong một bài test riêng, nhưng tránh assert nguyên câu log nội bộ dễ thay đổi theo framework version. Tốt hơn là assert HTTP response, Authentication/authority và side effect; chỉ dùng log để tìm nguyên nhân khi test thất bại.

### Kiểm tra filter chain trong MockMvc

**@SpringBootTest + @AutoConfigureMockMvc** tạo Spring Test context và thường đăng ký các filter trong MockMvc theo cấu hình Boot, nhờ đó test chạy qua Spring Security filter chain. Nếu tự dùng:

~~~java
MockMvcBuilders.standaloneSetup(controller).build();
~~~

thì MockMvc standalone không tự bao gồm **FilterChainProxy** chỉ vì ứng dụng có Spring Security dependency. Code trên chỉ là snippet, không có biến **controller** được khai báo, dùng để mô tả anti-pattern khi test controller đơn lẻ.

Nếu muốn tự tạo MockMvc, dùng cấu hình có **springSecurity()** hoặc đăng ký FilterChainProxy thích hợp và bảo đảm SecurityContextHolder được xử lý đúng. Không gán mọi kết quả từ standalone test cho chính sách Spring Security production.

### Đọc log theo một ca test

Trước khi chạy test, đánh dấu một request cụ thể bằng test method hoặc request ID **không chứa bí mật**. Quan sát:

1. Một request đã thực sự được gửi.
2. HTTP status và response headers.
3. Log theo đúng thread/trace ID và đúng thời điểm.
4. Filter chain phù hợp với route.
5. Authentication được tạo ra hoặc vì sao bị từ chối.
6. Authorization rule được đánh giá hoặc vì sao không tới bước đó.
7. Nếu có controller/service side effect, xác minh nó không chạy khi bị deny.

Một test pass về status không chứng minh mọi thông điệp log luôn hiện ra; một log rất chi tiết cũng không thay thế được test bảo mật âm.

## 8. Điều chỉnh logger khi ứng dụng đang chạy bằng Actuator (chỉ nếu được phép)

Trong một môi trường staging cô lập, Spring Boot Actuator có endpoint **loggers** để xem effective logger level và thay đổi mức log lúc runtime mà không cần restart. Đây là một **bề mặt quản trị nhạy cảm**: nếu public user có thể gọi nó, họ có thể tăng log verbosity hoặc ảnh hưởng quan sát hệ thống.

Dependency bổ sung trong **build.gradle** (ngoài dependencies của ví dụ):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Ví dụ profile riêng **src/main/resources/application-local-loggers.yml**:

~~~yaml
management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: "health,loggers"
~~~

Chỉ dùng ở **môi trường local đáng tin**. Địa chỉ loopback ở đây là **loopback của nơi tiến trình chạy**; khi ứng dụng ở container/k8s, 127.0.0.1 nằm trong network namespace tương ứng, không tự tạo một hệ thống truy cập quản trị hoàn chỉnh. Production cần bảo vệ endpoint bằng authentication/authorization, network policy, TLS và audit nếu thực sự cho phép thay đổi log level.

Giả sử app chạy local với profile **local-loggers**, xem logger:

~~~bash
curl -i \
  'http://127.0.0.1:9091/actuator/loggers/org.springframework.security.web.FilterChainProxy'
~~~

Bật tạm TRACE cho đúng category:

~~~bash
curl -i -X POST \
  'http://127.0.0.1:9091/actuator/loggers/org.springframework.security.web.FilterChainProxy' \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":"TRACE"}'
~~~

Sau khi đã tái hiện đúng **một vài request thử nghiệm**, **khôi phục mức cấu hình trước đó**. Nếu ban đầu category kế thừa mức log từ parent (không có configuredLevel riêng), có thể xóa override bằng:

~~~bash
curl -i -X POST \
  'http://127.0.0.1:9091/actuator/loggers/org.springframework.security.web.FilterChainProxy' \
  -H 'Content-Type: application/json' \
  -d '{"configuredLevel":null}'
~~~

Việc gửi **null** có nghĩa là xóa cấu hình mức log trực tiếp trên category để nó kế thừa; **không phải** đặt OFF. Nếu trước đó configuredLevel là INFO/DEBUG, hãy khôi phục đúng giá trị đã ghi nhận thay vì mặc định dùng null.

**Không triển khai endpoint loggers public chỉ vì debug tiện.** Nên dùng local loopback, SSH tunnel hoặc hạ tầng quản trị có kiểm soát, chặn truy cập Internet và không đưa token admin vào shell history. Với một số policy, việc bật loggers runtime trên production phải bị cấm hoàn toàn.

## 9. Một quy trình chẩn đoán có thể kiểm toán

### Bước 1 — Tái hiện tối thiểu, không dùng dữ liệu thật

Ghi rõ:

- URL và method, ví dụ **GET /private/admin**.
- Principal test và authorities mong đợi; không ghi raw Basic password, Bearer JWT hay session cookie.
- HTTP status/response header liên quan.
- Thời gian, deployment, request/correlation ID đã được làm sạch.
- Tình trạng TLS/proxy/path prefix nếu có.

Đặt kỳ vọng: user **alice** không có ROLE_ADMIN phải nhận **403**. Chỉ “người dùng báo lỗi 403” chưa đủ để kết luận có bug.

### Bước 2 — Chọn mức chẩn đoán thấp nhất

Khởi đầu:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Nếu cần biết filter nào được gọi, tạm thêm:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Nếu cần lần theo method authorization, xem logger trong **org.springframework.security.authorization** hoặc category cụ thể đang phát sự kiện. Bật hẹp hơn luôn tốt hơn bật tất cả TRACE.

### Bước 3 — Gửi một request, đối chiếu kết quả

~~~text
Request: GET /private/admin
Credential: tài khoản thử nghiệm alice
Expected: HTTP 403

Quan sát:
- Có qua FilterChainProxy?
- SecurityFilterChain nào được chọn?
- HTTP Basic tạo Authentication cho alice?
- Authorization yêu cầu ROLE_ADMIN?
- Vì sao bị deny?
- Controller có chạy không?
~~~

Dòng log chỉ mang tính định hướng; xác minh bằng test HTTP, context, breakpoint tạm thời trong local nếu cần và dữ liệu policy đáng tin.

### Bước 4 — Mở rộng một tầng nếu cần

Nếu request **không xuất hiện** trong log Spring Security:

- Kiểm tra reverse proxy, WAF, load balancer, servlet container logs.
- Kiểm tra URL context path/public prefix và rewrite rules.
- Kiểm tra SecurityFilterChain matcher, web.ignoring hoặc MockMvc test context.
- Kiểm tra logging appender, sampling và dynamic logger level.

Nếu request tới Spring Security nhưng không tới controller:

- Xem authentication/authorization rule, CSRF, CORS, firewall, exception handling.
- So sánh request success với request failure **cùng path**.
- Không tắt security rule chỉ để chứng minh controller hoạt động.

### Bước 5 — Tắt log, xác minh và lưu kết luận

- Hoàn nguyên logger category hoặc tắt profile **security-diagnostics / security-debug**.
- Kiểm tra **effective logger level** đã trở về mức dự kiến và DebugFilter không còn hoạt động.
- Không giữ sample header/payload nhạy cảm trong issue, screenshot, build artifact hoặc log aggregator.
- Nếu thông tin xác thực đã bị thu thập ngoài dự kiến, xử lý theo chính sách incident response.
- Ghi lại nguyên nhân thật, bản sửa chính sách và một regression test **độc lập với log string**.
- Theo dõi impact về log volume, latency và ổ đĩa trong thời gian bật diagnostic.

Đây là quy trình **quan sát → giả thuyết → kiểm thử → khôi phục**, không phải đổi cấu hình đến khi thấy HTTP 200.

## 10. Những rủi ro của log security chi tiết

### 10.1. Dữ liệu nhạy cảm và dữ liệu cá nhân

Log security có thể đi cùng các trường sau từ framework, ứng dụng, gateway, access log hoặc custom filter:

- **Authorization: Bearer ...**, **Authorization: Basic ...**, Cookie, Set-Cookie, session identifier.
- OAuth2/OIDC authorization code, ID token, access token, refresh token, **state**, **nonce**.
- Password, OTP, reset token, API key, private URL có query parameter nhạy cảm.
- Tên người dùng, role/authority, IP, URL chi tiết, tenant ID hoặc metadata của request.
- Payload hoặc claim chứa dữ liệu cá nhân.

Mặc dù một số Spring Security log hoặc serializer có thể che thông tin cụ thể, **không dựa vào giả định mọi phiên bản đều mask toàn bộ dữ liệu**. Không bật request/response body logging trên authentication endpoints trong môi trường chứa dữ liệu thật. Giữ log tránh truy cập công khai, mã hóa lưu trữ/chuyển tải theo chính sách và giới hạn retention.

**Cảnh báo riêng với web.debug(true):** DebugFilter có thể in/request-dump nhiều trường mà DEBUG logging bình thường không tạo. Cảnh báo “not for production” phải được xem là giới hạn vận hành, không chỉ là gợi ý.

### 10.2. Tác động hiệu năng và vận hành

TRACE có thể sinh bản ghi cho nhiều filter **trên mỗi request**, nhân với số lượng request đang chạy. Ngay cả khi CPU và heap còn đủ, logger appender, I/O và log shipper có thể bị nghẽn. Những hậu quả:

- Tăng độ trễ, I/O, dung lượng lưu trữ và chi phí log.
- Làm khó tìm tín hiệu quan trọng trong một lượng log lớn.
- Vô tình đẩy secret sang một hệ thống lưu trữ tập trung.
- Trễ hoặc bỏ log vì queue/appender bị quá tải.
- Thay đổi timing của lỗi race/async, khiến lỗi khó tái hiện.

Dùng log sampling, logger hẹp, thử lượng request nhỏ và tự động tắt theo quy trình vận hành. Không cho rằng TRACE “chỉ đọc” nên không có tác động lên hệ thống.

### 10.3. Correlation ID: đủ để truy vết nhưng không lộ secret

Một request ID ngẫu nhiên do tầng tin cậy tạo hoặc xác minh có thể giúp ghép các bản ghi **proxy → servlet → security → controller**. Chỉ log request ID, path template, status, thời gian và mã lỗi chung thay vì raw credential.

Đừng lấy nguyên giá trị **X-Request-ID** từ Internet rồi dùng làm dữ liệu truy vấn không được sanitize; attacker có thể đặt ký tự điều khiển và gây log injection. Hãy chuẩn hóa hoặc tạo lại ID tại ingress tin cậy. Nếu dùng MDC trong async thread, cần context propagation và cleanup; DebugFilter hoặc SecurityContextHolder không tự truyền MDC cho mọi executor.

## 11. Troubleshooting: chọn đúng logger cho triệu chứng

| Triệu chứng | Quan sát cần kiểm tra | Hành động có kiểm soát |
| --- | --- | --- |
| **401** với HTTP Basic | Credential có được xử lý, AuthenticationEntryPoint nào trả lời? | DEBUG Spring Security, so request thiếu/sai/đúng Basic credentials test |
| **401** với Bearer JWT | Decoder có xác thực chữ ký, exp, iss, aud không? | DEBUG category liên quan OAuth2 Resource Server/JWT; không log nguyên token |
| **302** tới login không mong đợi | Chain nào chọn formLogin/OAuth2 login? | TRACE FilterChainProxy và kiểm tra AuthenticationEntryPoint |
| **403** dù user tưởng có role | Authorities thật, matcher, method-security policy | DEBUG/TRACE authorization logger hẹp; test role đúng/sai |
| **403** với POST, GET vẫn chạy | CSRF, CORS hoặc endpoint authorization | Kiểm tra CsrfFilter/CorsFilter và request headers đúng chức năng |
| **404** ở public route sau proxy | Path prefix rewrite, context path, matching | Log edge/container + FilterChainProxy; không chỉ log controller |
| Request không xuất hiện trong Spring logs | Proxy/container chặn hoặc log category không bật | Kiểm tra tầng mạng và logger effective level |
| **400** với path %2F, ;, %5C | HttpFirewall hoặc servlet container | So log RequestRejectedException với container HTTP parser |
| Mất **security headers** | Filter chain bị bypass/ignore, response do gateway tạo, HTTP không secure | Kiểm tra chain, header writers và final edge response |
| **@PreAuthorize** không chạy | Self-invocation, method security chưa bật, proxy mismatch | Test qua bean/proxy thật và @EnableMethodSecurity |
| **@Async** không có Authentication | ThreadLocal không tự truyền qua worker | Kiểm tra executor và DelegatingSecurityContextAsyncTaskExecutor |
| TRACE tăng rất nhiều log | Mức quá rộng hoặc lưu lượng lớn | Giới hạn category, request sampling, hoàn nguyên sớm |
| Không có output dù đã bật DEBUG | Profile không active, logger override, appender/sampling, request chưa tới process | Kiểm tra effective logger config/actuator và đúng instance |

**Quan trọng:** đừng xem không có log là bằng chứng không có attack, và đừng xem một dòng “Secured ...” là bằng chứng authorization cho dữ liệu đã chính xác. Vẫn cần xác minh quyền ở cấp role, tenant, ownership và route thật.

## 12. Checklist trước, trong và sau một lần bật debug

**Trước khi bật:**

- Xác định bug, request tái hiện và trạng thái mong đợi.
- Chọn local/staging riêng, dùng credential giả và chặn lưu lượng người dùng thật.
- Chọn category nhỏ nhất và level thấp nhất đáp ứng mục tiêu.
- Ghi nhận baseline logger levels và bảo đảm có quyền revert.
- Kiểm tra nơi log sẽ đến, ai đọc được, chính sách retention/redaction.
- Với Actuator, hạn chế network/identity và không public endpoint loggers.
- Tránh dùng **web.debug(true)** khi có dữ liệu production.

**Trong khi bật:**

- Chỉ gửi số lượng request tối thiểu, không gửi token/secret thật.
- Đối chiếu status, header, request ID, filter chain và tầng từ chối.
- Phân biệt authentication, authorization, CSRF, CORS và firewall.
- Tránh thay security rule để “làm xanh” request đang kiểm thử.
- Quan sát log volume và performance, dừng nếu có dấu hiệu lộ dữ liệu hoặc quá tải.

**Sau khi bật:**

- Hoàn nguyên profile/logger, xác nhận debug filter không còn.
- Xác minh lại HTTP behavior bằng regression tests độc lập với log.
- Bảo vệ/loại bỏ log nhạy cảm theo quy trình bảo mật và đánh giá thu hồi bí mật nếu cần.
- Ghi lại nguyên nhân gốc, bản sửa, test ngăn tái phát và điểm cần quan sát lâu dài.
- Không để lại TRACE/DEBUG mở vô thời hạn trên staging chia sẻ hoặc production.

**Kết luận:** DEBUG và TRACE là công cụ để **nhìn rõ quyết định bảo mật**, không phải cách sửa lỗi bằng cách nới quyền. Trong Spring Security Servlet, ưu tiên **logger DEBUG theo category**, chỉ nâng lên **TRACE hẹp** khi cần chi tiết filter; **web.debug(true)** chỉ dành cho môi trường cô lập vì nguy cơ lộ thông tin. Điều tra xong phải tắt chế độ chẩn đoán, bảo vệ log và biến phát hiện thành kiểm thử bảo mật có thể chạy lại.
