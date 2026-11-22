# Xử lý xác thực thất bại mà không tiết lộ sự tồn tại của tài khoản

## 1. Bài toán: thông báo lỗi đăng nhập có thể làm lộ danh sách người dùng

Giả sử một hệ thống có endpoint POST /login hoặc một API được bảo vệ bởi HTTP Basic. Kẻ tấn công chưa biết mật khẩu nhưng muốn kiểm tra xem tài khoản **alice@example.com** có tồn tại trong hệ thống hay không.

Hai phản hồi sau đều là lỗi đăng nhập, nhưng chúng tiết lộ lượng thông tin rất khác nhau:

~~~text
Username không tồn tại  -> "Không tìm thấy tài khoản"
Username có thật, sai mật khẩu -> "Mật khẩu không chính xác"
~~~

Chỉ bằng cách thử nhiều username, người ngoài có thể lập danh sách tài khoản thật. Sau đó họ có thể dùng danh sách để thực hiện **credential stuffing, password spraying, phishing có chủ đích, tấn công reset password** hoặc thăm dò tài khoản quản trị.

Ngay cả khi cả hai trường hợp đều hiện một dòng “Sai tên đăng nhập hoặc mật khẩu”, ứng dụng vẫn có thể tiết lộ sự tồn tại của tài khoản qua **HTTP status, redirect, URL, header, kích thước response, thời gian xử lý, giới hạn tốc độ, thông báo email** hoặc hành vi khóa tài khoản.

**Mục tiêu:** Xử lý thất bại theo cách khiến một người gọi **chưa được xác thực** không phân biệt được “username không tồn tại”, “username có thật nhưng password sai”, “tài khoản bị khóa” hay “tài khoản bị vô hiệu hóa” dựa trên những phản hồi mà họ quan sát được, trong giới hạn threat model đã thiết kế.

Ví dụ dùng **Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet** để giải thích API. Các phiên bản này được chọn cho bối cảnh học tập; một số bản Spring Security 6.3 có advisory bảo mật về timing được nêu ở mục 8, **không dùng phiên bản có lỗ hổng đã biết cho production**.

### Bạn sẽ học được

1. User enumeration là gì và thông tin rò rỉ nằm ở những đâu.
2. Phân biệt AuthenticationException, UsernameNotFoundException, BadCredentialsException, LockedException và DisabledException.
3. Tại sao không để nguyên exception nội bộ trở thành message hoặc status công khai.
4. Cách DaoAuthenticationProvider mặc định ẩn khác biệt giữa username không tồn tại và password sai.
5. Vì sao chỉ dùng một thông báo lỗi chưa đủ để chống timing side channel.
6. Xây HTTP Basic API trả cùng mã lỗi và cùng JSON cho các trường hợp xác thực không thành công.
7. Viết kiểm thử MockMvc cho hợp đồng lỗi công khai và biết giới hạn của kiểm thử này.
8. Áp dụng nguyên tắc tương tự cho form login, reset password, đăng ký, mã OTP và tài khoản khóa.
9. Thiết kế rate limiting, logging và hỗ trợ người dùng mà không tạo kênh lộ thông tin mới.

## 2. User enumeration là lỗ hổng thuộc lớp nào?

**User enumeration** là khả năng suy ra một định danh (username/email/số điện thoại/account ID) có tồn tại trong hệ thống hay không từ phản hồi của các chức năng có thể truy cập mà chưa cần chứng minh quyền sở hữu tài khoản.

Nó không đồng nghĩa với việc attacker đã đăng nhập được. Tuy nhiên, việc biết tài khoản nào có thật **giảm không gian tìm kiếm và tăng hiệu quả tấn công tiếp theo**.

Ví dụ API:

~~~http
POST /login HTTP/1.1
Content-Type: application/json

{"username":"alice","password":"wrong"}
~~~

Phản hồi **không nên** nói rằng alice tồn tại nhưng password sai, cũng không nên trả một định danh nội bộ hoặc trạng thái account. Với các request đăng nhập không hợp lệ tương đương, giao diện công khai nên dùng một lỗi chung như:

~~~json
{
  "error": "invalid_credentials"
}
~~~

Một ứng dụng web có thể dùng thông báo ngắn cho người dùng: **“Không thể đăng nhập bằng thông tin đã cung cấp.”** Nội dung không tiết lộ username có tồn tại, password sai, account bị khóa hay trạng thái kích hoạt.

### 2.1. Những điểm có thể rò rỉ

| Kênh quan sát | Phản hồi không an toàn | Hướng thiết kế |
| --- | --- | --- |
| Thông báo hiển thị | “Email không tồn tại” so với “Sai mật khẩu” | Một lỗi chung cho authentication thất bại |
| HTTP status | Unknown user 404, password sai 401 | Cùng status cho các lỗi đăng nhập tương đương |
| JSON body | Trả enum USER_NOT_FOUND, LOCKED | Một error code public; giữ chi tiết ở hệ thống nội bộ |
| Redirect | /login?not-found so với /login?bad-password | Cùng login failure URL hoặc flow |
| Response headers | X-Account-Exists: true | Không đưa account state vào headers |
| Response size | Trang lỗi user tồn tại dài hơn nhiều | Cùng template và cấu trúc phản hồi |
| Thời gian xử lý | Không thấy user thì return ngay; có user thì BCrypt | Tránh early exit; dùng provider/phiên bản có mitigation phù hợp |
| Rate limit/lockout | User có thật nhanh bị khóa, user giả không có thay đổi | Thiết kế anti-abuse không biến account existence thành tín hiệu |
| Reset password | “Đã gửi email” chỉ khi email tồn tại | Câu trả lời chung cho yêu cầu hợp lệ |
| Đăng ký | “Email đã tồn tại” từ endpoint công khai | Dùng quy trình xác minh/đăng ký hạn chế enumeration phù hợp sản phẩm |
| OTP/resend code | “Số điện thoại chưa đăng ký” | Phản hồi chung, xử lý gửi mã chỉ ở backend |
| Log/analytics public | Trả raw exception trong response/log client thấy | Tách internal reason khỏi public contract |

Một hệ thống chỉ thay câu chữ nhưng để status khác nhau hoặc cho thời gian phản hồi rất khác nhau vẫn có thể bị suy đoán tài khoản.

### 2.2. Không phải lúc nào cũng cần che mọi trạng thái

Khi một người đã **xác minh quyền sở hữu tài khoản** và đi qua bước authentication thích hợp, hệ thống có thể hiển thị thông tin cụ thể hơn như yêu cầu đổi mật khẩu, tài khoản hết hạn hoặc các phương án khôi phục an toàn. Đừng nhầm nhu cầu hỗ trợ người dùng với việc cho **người gọi chưa xác thực** biết một username bất kỳ có thật.

Trong nội dung sau, “thống nhất lỗi” áp dụng chủ yếu cho **giao diện đăng nhập và các chức năng phục hồi công khai**. Khi một user đã đăng nhập gọi endpoint không có quyền, HTTP 403 là nhánh authorization khác với login thất bại 401.

## 3. Luồng xác thực và vị trí nên chuẩn hóa lỗi

Trong Spring Security Servlet, một request username/password thường có các bước:

~~~text
Client
  |
  | username/password
  v
BasicAuthenticationFilter hoặc UsernamePasswordAuthenticationFilter
  |
  | UsernamePasswordAuthenticationToken chưa xác thực
  v
AuthenticationManager / ProviderManager
  |
  v
DaoAuthenticationProvider
  |
  +-- UserDetailsService.loadUserByUsername(username)
  |      +-- Không thấy user -> UsernameNotFoundException nội bộ
  |
  +-- PasswordEncoder.matches(rawPassword, storedHash)
  |      +-- Password sai -> BadCredentialsException
  |
  +-- Account status checks
  |      +-- Locked/disabled/expired -> AuthenticationException tương ứng
  |
  +-- Success -> Authentication đã xác thực
  |
  +-- Failure -> AuthenticationException
                  |
                  v
Filter + AuthenticationEntryPoint hoặc AuthenticationFailureHandler
                  |
                  v
HTTP 401/redirect + public error message thống nhất
~~~

**Hai tầng cần tách:**

- **Tầng xác thực nội bộ** cần biết lý do để audit, chống lạm dụng, hỗ trợ người dùng và giám sát.
- **Tầng phản hồi công khai** chỉ nên tiết lộ kết quả cần thiết để client tiếp tục hoặc sửa thông tin.

Ví dụ UserDetailsService có thể ném UsernameNotFoundException và provider có thể gặp DisabledException. Nhưng từ hai exception đó **không được tự động tạo hai body hoặc hai URL lỗi khác nhau** gửi cho client chưa đăng nhập.

### 3.1. Phân biệt filter, manager và handler

| Thành phần | Trách nhiệm chính |
| --- | --- |
| Authentication filter | Nhận credentials từ request và gọi AuthenticationManager |
| AuthenticationManager | Thực thi hợp đồng authenticate hoặc ném AuthenticationException |
| AuthenticationProvider | Kiểm chứng credential/ trạng thái user theo kiểu Authentication |
| UserDetailsService | Tải tài khoản; không so password |
| PasswordEncoder | Kiểm tra raw password với hash |
| AuthenticationEntryPoint | Bắt đầu quá trình authentication hoặc trả lỗi cho request chưa được xác thực, ví dụ HTTP Basic 401 |
| AuthenticationFailureHandler | Xử lý thất bại của cơ chế interactive login, thường là form login |
| AccessDeniedHandler | Xử lý thiếu quyền đối với người dùng đã xác thực, thường HTTP 403 |

AuthenticationManager **không trực tiếp trả HTTP 401 hoặc redirect**. HTTP response là trách nhiệm của tầng filter/handler. Vì vậy chuẩn hóa response tại đúng boundary thường dễ bảo trì hơn cố giấu mọi exception bằng cách sửa service hoặc DAO.

## 4. Những loại thất bại thường gặp

| Trường hợp | Ngoại lệ/diễn biến thường gặp | Điều client chưa xác thực nên biết |
| --- | --- | --- |
| Username không có trong kho | UsernameNotFoundException, có thể được provider chuyển thành BadCredentialsException | Thông tin đăng nhập không hợp lệ |
| Username có nhưng password sai | BadCredentialsException | Cùng lỗi chung |
| Account locked | LockedException hoặc trạng thái tương ứng | Không xác nhận account tồn tại |
| Account disabled | DisabledException | Không xác nhận trạng thái account |
| Account expired | AccountExpiredException | Không phân biệt với các lỗi login khác |
| Password/credentials expired | CredentialsExpiredException | Cân nhắc luồng khôi phục có xác minh |
| Token malformed/expired/invalid signature | OAuth2/Bearer exception theo cơ chế | Không trả chi tiết chứa secret hoặc phân biệt danh tính tùy ý |
| DB/auth backend tạm thời lỗi | InternalAuthenticationServiceException hoặc sự cố hệ thống | Thông báo hệ thống chung, không công bố SQL/stack trace |
| IP/user vượt giới hạn số lần thử | 429/challenge/cooldown tùy policy | Cùng chính sách cho các username không xác minh được |
| User đã login nhưng thiếu role | AccessDeniedException | 403 theo authorization, không phải user enumeration qua login |

**Không đánh đồng mọi exception:** lỗi hệ thống thật có thể cần status 503 và telemetry riêng theo chính sách vận hành; mục tiêu là không dùng lỗi để tiết lộ user tồn tại. Không nên “nuốt” database outage rồi báo “sai mật khẩu” trong mọi trường hợp, vì có thể làm gián đoạn khôi phục và audit.

### 4.1. 401 và 403 được dùng khi nào?

Trong ví dụ HTTP Basic:

- **401 Unauthorized:** thiếu hoặc sai thông tin xác thực; cơ chế entry point có thể gửi WWW-Authenticate.
- **403 Forbidden:** đã xác thực nhưng thiếu quyền đối với tài nguyên hoặc bị policy như CSRF từ chối.

Nếu user có ROLE_USER vào endpoint cần ROLE_ADMIN, trả 403 là đúng. Không cần cố biến **mọi 403 thành 401** để chống enumeration; đó là một bài toán quyền khác. Điều cần thống nhất là **các nhánh authentication failure có cùng mức thông tin công khai**.

## 5. DaoAuthenticationProvider đã giúp gì?

Trong Spring Security 6.x, với username/password thông thường, **DaoAuthenticationProvider** sử dụng UserDetailsService và PasswordEncoder. Nó kế thừa hành vi từ **AbstractUserDetailsAuthenticationProvider**.

### 5.1. hideUserNotFoundExceptions

Mặc định **hideUserNotFoundExceptions=true** ở AbstractUserDetailsAuthenticationProvider. Khi UserDetailsService không tìm thấy username, provider có thể chuyển UsernameNotFoundException thành **BadCredentialsException**, tương tự trường hợp mật khẩu sai.

Điều này giúp giảm khác biệt có thể thấy qua exception loại cơ bản. Không nên gọi **setHideUserNotFoundExceptions(false)** trong flow công khai chỉ để hiện “Tài khoản không tồn tại”, vì như vậy sẽ mở lại kênh tiết lộ danh sách user.

Một chú ý quan trọng: mặc dù backend nội bộ có thể phân loại khác nhau, **exception message và cause cũng không được serialize trực tiếp ra JSON**, nhất là khi custom failure handler hoặc global exception resolver có thể xuất hiện.

### 5.2. Không dùng UserDetailsService thay authentication

Đây là cách suy nghĩ sai:

~~~java
UserDetails user = users.loadUserByUsername(username);
// Tìm được user không có nghĩa password người gọi đúng.
return UsernamePasswordAuthenticationToken.authenticated(
    user, null, user.getAuthorities()
);
~~~

Đoạn này là **anti-pattern minh họa**, tuyệt đối không dùng để triển khai đăng nhập.

Nó chưa xác minh raw password, chưa xét đầy đủ trạng thái tài khoản và có nguy cơ cấp danh tính cho người chỉ biết username. Hãy dùng provider Spring Security có sẵn, hoặc một cơ chế đã được thiết kế/kiểm thử bảo mật.

### 5.3. PasswordEncoder.matches

PasswordEncoder kiểm tra password dạng raw với hash đã lưu. Với BCrypt hoặc Argon2, password hash là phép tính có chi phí; do đó nhánh user có thật thường thực hiện công việc tốn thời gian hơn nhánh không tìm thấy user.

Nếu tùy tiện return ngay khi username không tồn tại, attacker có thể đo thời gian nhiều lần và suy ra sự khác biệt dù message/status giống hệt nhau.

DaoAuthenticationProvider có kỹ thuật giảm timing discrepancy cho nhánh user không tồn tại bằng việc thực hiện phép so khớp với một hash giả. Nhưng **đừng coi kỹ thuật mặc định này là cam kết thời gian phản hồi bằng nhau trong mọi nhánh và mọi version**.

## 6. Vì sao chỉ thống nhất message chưa đủ?

### 6.1. Early exit tạo timing side channel

Pseudo-code dễ gặp:

~~~text
if (!accountExists(username)):
    return genericFailure

if (!passwordEncoder.matches(rawPassword, storedHash)):
    return genericFailure
~~~

Bên ngoài cả hai đều thấy “Không thể đăng nhập”, nhưng nhánh đầu có thể kết thúc sau lookup, còn nhánh thứ hai phải tính BCrypt/Argon2. Sau nhiều mẫu đo, sự khác biệt thống kê có thể tiết lộ account tồn tại.

**Hướng giải quyết:** dùng thành phần authentication đã được bảo trì và có kỹ thuật chống timing phù hợp; kiểm tra bản vá mới nhất, tránh early return tự chế. Nếu bắt buộc viết custom provider, cần phân tích cả nhánh unknown user, account locked/disabled, cache hit/miss, DB lookup, encoder work và độ chênh lệch khác thường.

### 6.2. Không dùng Thread.sleep cố định để “chống timing”

Ví dụ gọi Thread.sleep(200) chỉ trên nhánh unknown user **không bảo đảm bằng thời gian**: khối lượng CPU, database, cache, retry, GC và tải server khác nhau. Delay cố định còn có thể làm giảm throughput hoặc tạo kênh đo mới. Chọn cơ chế được chuyên gia kiểm thử, giới hạn tốc độ và phân tích side channel thực tế.

Không cần cam kết mọi request có thời gian xử lý giống hệt nhau ở mức nanosecond; mục tiêu là loại bỏ khác biệt **ổn định, có thể khai thác**, và có các lớp hạn chế thử nghiệm quy mô lớn.

### 6.3. Kích thước và cấu trúc body cũng là tín hiệu

Hai body:

~~~json
{"error":"invalid_credentials"}
~~~

và:

~~~json
{"error":"invalid_credentials","hint":"reset_password_for_existing_user"}
~~~

dùng cùng error prefix nhưng khác nội dung/kích thước và gợi ý sự tồn tại của tài khoản. Nếu cần hướng dẫn, hãy đặt một **liên kết khôi phục mật khẩu chung** cho mọi lỗi đăng nhập, thay vì chỉ hiện cho user thật.

### 6.4. Redirect và HTTP headers

Form login có thể cùng thông báo trên UI nhưng redirect:

~~~text
Không có account -> /login?error=user_missing
Có account       -> /login?error=wrong_password
~~~

Query parameter tự nó tiết lộ sự khác biệt. Tương tự, custom headers như X-Account-Status hoặc mã HTTP 404/423 riêng cho account không xác minh được là một kênh lộ thông tin.

Cần kiểm thử **status, Location, WWW-Authenticate, Content-Type, Cache-Control, body và kích thước body** giữa các lỗi tương đương.

## 7. Ví dụ Spring Boot: phản hồi 401 nhất quán cho mọi lỗi login

Ví dụ dùng HTTP Basic để dễ kiểm tra bằng curl. Nó giữ nguyên DaoAuthenticationProvider/UserDetailsService/PasswordEncoder tiêu chuẩn và đặt một **AuthenticationEntryPoint chung** cho lỗi authentication.

**Phạm vi:** Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x, Spring MVC/Servlet. Code phù hợp cú pháp nhóm version này, nhưng **phần thời gian phản hồi của bản 6.3.x cần xem CVE ở mục 8**. Ví dụ chỉ chứng minh public response được chuẩn hóa, không chứng minh đã loại bỏ mọi timing side channel. Triển khai thật phải dùng dependency được cập nhật bản vá bảo mật.

### 7.1. Dependency Gradle

Trong dự án Spring Boot có plugin Gradle và Gradle Wrapper, file **build.gradle** (Groovy DSL) cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là đoạn **dependencies** của dự án đã cấu hình Spring Boot plugin và Java 17, không phải toàn bộ file build.gradle độc lập. Spring Boot quản lý version của các starter theo BOM đã chọn.

### 7.2. File Java đầy đủ

Tạo file **src/main/java/com/example/safeauth/SafeAuthApplication.java**:

~~~java
package com.example.safeauth;

import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SafeAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(SafeAuthApplication.class, args);
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
                .build(),
            User.withUsername("locked")
                .password(encoder.encode("locked123"))
                .roles("USER")
                .accountLocked(true)
                .build(),
            User.withUsername("disabled")
                .password(encoder.encode("disabled123"))
                .roles("USER")
                .disabled(true)
                .build()
        );
    }

    // Cùng một phản hồi cho authentication failure.
    @Bean
    AuthenticationEntryPoint genericFailureEntryPoint() {
        return (request, response, exception) -> {
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(StandardCharsets.UTF_8.name());
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"lesson\"");
            response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
            response.getWriter()
                .write("{\"error\":\"invalid_credentials\"}");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, AuthenticationEntryPoint genericFailure)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/private").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(genericFailure)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(genericFailure)
                .accessDeniedHandler((request, response, exception) -> {
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding(
                        StandardCharsets.UTF_8.name());
                    response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
                    response.getWriter()
                        .write("{\"error\":\"access_denied\"}");
                })
            )
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
    String privateEndpoint() {
        return "private OK";
    }

    @GetMapping("/admin")
    String adminEndpoint() {
        return "admin OK";
    }
}
~~~

Đây là **một file Java trong dự án Spring Boot**: public class cùng tên file, DemoController là class cùng package được component scanning phát hiện. Java 17 hỗ trợ lambda; Spring Boot 3 dùng namespace jakarta.servlet.

Các account **alice, admin, locked, disabled** và password trong source **chỉ dành cho bài học local**. Không dùng password demo trong production; không tạo tài khoản bị khóa/disable với mật khẩu cố định ở môi trường thật. Ở hệ thống thực, dùng nguồn danh tính được quản trị, Secret Manager và chính sách mật khẩu phù hợp.

### 7.3. Giải thích cấu hình

**UserDetailsService** cung cấp bốn trạng thái minh họa:

- alice: tài khoản hoạt động, ROLE_USER.
- admin: tài khoản hoạt động, ROLE_ADMIN.
- locked: tài khoản đã bị khóa.
- disabled: tài khoản bị vô hiệu hóa.

**PasswordEncoder** dùng BCrypt. Khi có UserDetailsService và PasswordEncoder beans, Spring Security có thể cấu hình DaoAuthenticationProvider cho cơ chế username/password thông thường.

**genericFailureEntryPoint** chịu trách nhiệm public contract khi request không có authentication hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/json
WWW-Authenticate: Basic realm="lesson"
Cache-Control: no-store

{"error":"invalid_credentials"}
~~~

Trong ví dụ, cả HTTP Basic filter và exception handling đều dùng entry point này. Nhờ đó nhánh request không có credential, sai password, unknown username, locked/disabled account có thể được xử lý với **cùng một status, cùng header quan trọng và cùng body**.

**AccessDeniedHandler** trả 403 với error code access_denied khi người dùng đã được xác thực nhưng thiếu role. Đây là nhánh **authorization**, khác với authentication failure.

**formLogin.disable** chỉ làm demo Basic dễ kiểm thử; nếu ứng dụng browser dùng form login, nên có AuthenticationFailureHandler/URL xử lý form riêng được chuẩn hóa như mục 10.

### 7.4. Không lộ exception qua response

Lambda AuthenticationEntryPoint nhận đối số exception nhưng **không đưa exception.getMessage(), exception.getClass(), cause hoặc stack trace ra client**. Đây là chủ ý quan trọng.

Trong ứng dụng thực tế, hệ thống vẫn cần log/audit lỗi theo chính sách nội bộ để phát hiện tấn công và hỗ trợ người dùng. Nhưng log đó phải được phân quyền, giới hạn retention và không chứa raw password, token, Authorization header hoặc dữ liệu nhận diện vượt nhu cầu.

### 7.5. Phân biệt response consistency và timing security

Ví dụ chứng minh **cấu trúc phản hồi thống nhất**. Nó **không bảo đảm** thời gian xử lý của locked/disabled user giống unknown user trên các bản Spring Security có advisory.

Muốn chặn enumeration trong production phải kết hợp **phiên bản đã vá, kiểm thử timing có kiểm soát, rate limiting, monitoring, giới hạn metadata công khai** và thiết kế tài khoản/khôi phục phù hợp. Không đánh giá an toàn chỉ qua JSON.

## 8. Lưu ý bảo mật theo phiên bản: CVE-2026-22746

Ngày **20/04/2026**, Spring công bố advisory **CVE-2026-22746 — User Attribute Enumeration when Using DaoAuthenticationProvider**. Theo advisory, khi dùng các trạng thái **isEnabled, isAccountNonExpired hoặc isAccountNonLocked**, cơ chế giảm timing attack của DaoAuthenticationProvider có thể bị vượt qua với tài khoản bị disabled, expired hoặc locked trên những phiên bản bị ảnh hưởng.

Các khoảng phiên bản Spring Security được advisory liệt kê:

| Nhánh | Bản bị ảnh hưởng | Phiên bản vá được công bố |
| --- | --- | --- |
| 6.3 | 6.3.0 đến 6.3.15 | 6.3.16, Enterprise Support Only |
| 6.4 | 6.4.0 đến 6.4.15 | 6.4.16, Enterprise Support Only |
| 6.5 | 6.5.0 đến 6.5.9 | 6.5.10, OSS |
| 7.0 | 7.0.0 đến 7.0.4 | 7.0.5, OSS |
| 5.8 | 5.8.0 đến 5.8.24 | 5.8.25, Enterprise Support Only |

Nguồn: https://spring.io/security/cve-2026-22746/

**Ý nghĩa đối với bài:** demo ở Spring Boot 3.3.x/Security 6.3.x là ví dụ về API/cấu hình, không phải blueprint production đã khắc phục timing. Cả khi cùng 401 + JSON, việc user bị khóa/disabled có thể bị phân biệt qua thời gian trên các phiên bản được advisory nêu.

**Hành động thực tế:** kiểm tra phiên bản Spring Security được quản lý bởi BOM; nâng lên một bản đã sửa và còn được hỗ trợ, đồng thời bảo đảm tương thích Spring Boot và kiểm thử toàn bộ authentication flow. Không tự ép version Security 6.5 vào ứng dụng Boot 3.3 một cách tùy tiện chỉ vì có một số version đã vá. Làm theo release/security advisory tương ứng với hệ thống của bạn.

Bản vá được Spring giới thiệu thêm cấu hình **DaoAuthenticationProvider.setAlwaysPerformAdditionalChecksOnUser**; không tắt cơ chế mới chỉ để giảm chi phí xử lý mà chưa phân tích rủi ro. Không khẳng định cấu hình đã an toàn chỉ vì không thấy UsernameNotFoundException trong response.

### 8.1. Vì sao cần nhắc lỗ hổng này khi học kiến thức cơ bản?

Bởi vì chống enumeration có **hai tầng**:

1. **Output behavior:** message, HTTP status, redirect, body, header không phân biệt tài khoản có thật.
2. **Processing behavior:** đường đi và thời gian xử lý phải không có khác biệt ổn định dễ khai thác giữa các trạng thái.

Một bài chỉ dừng ở generic error message có thể khiến người học bỏ sót tầng thứ hai, đặc biệt khi hệ thống có locked/disabled accounts.

## 9. Thực hành curl: kiểm tra các lỗi giống nhau

Tại thư mục có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng **.\gradlew.bat bootRun**. Giả sử server lắng nghe localhost:8080.

Dùng curl:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/private
curl -i -u ghost:anything http://localhost:8080/private
curl -i -u alice:wrong http://localhost:8080/private
curl -i -u locked:locked123 http://localhost:8080/private
curl -i -u disabled:disabled123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/private
curl -i -u alice:learn123 http://localhost:8080/admin
curl -i -u admin:admin123 http://localhost:8080/admin
~~~

Trên PowerShell có thể phải dùng **curl.exe** vì curl là alias. Đối với credential thật, dùng **curl -u alice URL** để curl hỏi password thay vì đưa password vào shell history. HTTP Basic cần HTTPS khi đi qua mạng; các password ví dụ chỉ dùng với localhost cô lập.

### 9.1. Ma trận kết quả dự kiến

| Request | Status | Body/ý nghĩa |
| --- | --- | --- |
| GET /public anonymous | **200** | public OK |
| GET /private anonymous | **401** | {"error":"invalid_credentials"} |
| GET /private unknown user ghost | **401** | **Cùng body** |
| GET /private alice password sai | **401** | **Cùng body** |
| GET /private locked password đúng | **401** | **Cùng body** |
| GET /private disabled password đúng | **401** | **Cùng body** |
| GET /private alice password đúng | **200** | private OK |
| GET /admin alice password đúng | **403** | {"error":"access_denied"} |
| GET /admin admin password đúng | **200** | admin OK |

Bảng là **kỳ vọng theo cấu hình demo**, không phải log một phiên chạy đã đo. MockMvc ở mục sau xác nhận các contract HTTP nhưng vẫn không kiểm tra timing side channel.

Đối với các nhánh 401, cần so sánh thêm WWW-Authenticate, Content-Type, Cache-Control và Location (nếu có). Header **Date** hoặc thông tin vận hành có thể thay đổi theo request, nhưng không nên khác **theo trạng thái tài khoản**.

### 9.2. Vì sao các response 401 nên có WWW-Authenticate nhất quán?

HTTP Basic là một cơ chế HTTP authentication. WWW-Authenticate cho biết client cần gửi Basic credentials trong realm. Nếu thiếu hoặc dùng realm khác nhau tùy username có tồn tại, chính header ấy tạo một kênh phân biệt.

Ví dụ code đặt **Basic realm="lesson"** như nhau cho mọi authentication failure. Đây là realm demo; production chọn realm rõ phạm vi bảo mật và không đưa tên account/trạng thái user vào realm.

### 9.3. Đăng nhập đúng nhưng thiếu quyền không phải lỗi username enumeration

alice đăng nhập đúng vào /admin bị 403. Hệ thống đã biết danh tính và xử lý authorization theo ROLE_ADMIN. **Không cần trả generic invalid_credentials cho trường hợp này**, vì làm vậy sẽ đánh đồng authorization với authentication và gây khó debug.

## 10. Với form login thì xử lý thế nào?

Form login thường khác HTTP Basic về response: khi người dùng POST form login thất bại, Spring Security dùng **AuthenticationFailureHandler**, thường redirect về trang login có tham số error.

Nếu muốn kiểm soát failure handler, có thể dùng cấu hình:

~~~java
.formLogin(form -> form
    .failureUrl("/login?error")
)
~~~

Đây là **snippet đặt trong SecurityFilterChain có form login và đường dẫn /login phù hợp**, không phải file Java độc lập. Với login page tự định nghĩa, controller/template cần được viết và route cần được permitAll đúng cách.

Nguyên tắc:

- Unknown username → cùng redirect /login?error.
- Existing username + wrong password → cùng redirect.
- Locked/disabled → cùng redirect cho người chưa xác minh.
- Trang login hiển thị **một thông báo chung**, không render exception.getMessage().
- Không append username, trạng thái account, mã nội bộ hoặc tên exception vào URL.
- Kiểm tra cookie, session, CSRF token và request cache trong flow browser.
- Khi trang public có thể bị cache, dùng cache controls phù hợp để không lộ trạng thái cá nhân.

**Không dùng param /login?error=user_not_found và /login?error=locked.** Dù template chỉ hiện một câu chung, URL vẫn là output công khai mà attacker đọc được.

### 10.1. Vì sao có thể để người dùng tìm trợ giúp?

Trang lỗi chung có thể chứa cùng một liên kết “Quên mật khẩu?” hoặc “Liên hệ hỗ trợ” cho tất cả trường hợp. Nếu người dùng thực sự sở hữu tài khoản, flow khôi phục được thiết kế đúng sẽ giúp họ tiếp tục mà không cần tiết lộ sự tồn tại của account cho người ngoài.

Một trang hỗ trợ được cá nhân hóa sau xác minh có thể cung cấp nhiều thông tin hơn so với trang login công khai.

## 11. Password reset và quên tên đăng nhập

User enumeration thường dễ xảy ra hơn ở **reset password** vì developer muốn cho người dùng biết email họ nhập có được đăng ký hay không.

Ví dụ không an toàn:

~~~text
POST /forgot-password với email có thật  -> 200 "Đã gửi email"
POST /forgot-password với email không có -> 404 "Email chưa đăng ký"
~~~

Hướng tốt hơn cho request có cú pháp hợp lệ:

~~~json
{
  "message": "Nếu địa chỉ được cung cấp có tài khoản phù hợp, hướng dẫn khôi phục sẽ được gửi qua kênh đã đăng ký."
}
~~~

Cùng body/status cho email có và không có tài khoản, và không đưa internal account ID/token vào response. Hệ thống thực hiện gửi thông báo **chỉ khi có account phù hợp**, nhưng người ngoài không nên suy ra điều đó bằng phản hồi đồng bộ.

### 11.1. Không để thời gian gửi email tiết lộ sự tồn tại

Nếu nhánh email có thật thực hiện SMTP call ngay trong request còn email không có thì trả tức thì, response time có thể khác nhau. Nên cân nhắc **queue/async message dispatch**, thống nhất đường xử lý phù hợp và rate limiting. Không cần tạo email giả cho địa chỉ không tồn tại nếu điều đó có nguy cơ spam hoặc chi phí; mục tiêu là hạn chế tín hiệu từ request công khai.

### 11.2. Token reset phải có thuộc tính riêng

Token reset cần khó đoán, giới hạn thời gian, sử dụng một lần, gắn với account phù hợp và được lưu/bảo vệ an toàn. Không đưa token vào log, analytics URL hoặc trang lỗi. Sau khi reset, cân nhắc vô hiệu hóa session/token cũ và thông báo thay đổi qua kênh đã xác minh.

**Generic response không thay thế thiết kế reset token.** Nó chỉ bảo vệ một khía cạnh của việc công bố account existence.

## 12. Đăng ký tài khoản, resend OTP và MFA

### 12.1. Đăng ký bằng email

Với endpoint đăng ký công khai, kiểm tra email trùng lặp có thể lộ user nào đã tồn tại. Trải nghiệm sản phẩm có thể cần nói “email đã được sử dụng”, nhưng hệ thống nhạy cảm nên thiết kế **phản hồi chung và kênh xác minh quyền sở hữu email** trước khi công bố trạng thái.

Một hướng là chấp nhận yêu cầu đăng ký hợp lệ bằng cùng response, sau đó gửi thư hướng dẫn phù hợp tới email được kiểm soát bởi người dùng. Cần kiểm soát abuse, không tạo nhiều tài khoản trùng và không tiết lộ nội dung thông qua timing.

### 12.2. Resend OTP

Endpoint resend mã xác minh có thể tiết lộ số điện thoại/email có account nếu trả “Không tìm thấy số điện thoại”. Thay vào đó, trả thông báo chung về việc xử lý yêu cầu nếu thông tin hợp lệ, và đặt rate limit phù hợp để tránh spam SMS/email.

### 12.3. MFA

Ở những flow cần MFA, không nên cho phép một endpoint công khai trả “Tài khoản alice chưa bật MFA” trước khi người gọi chứng minh danh tính. Sau khi password đã được xác minh và flow MFA được liên kết an toàn với session tạm thời, hệ thống có thể hướng dẫn bước kế tiếp.

Cần giới hạn thời gian challenge, chống replay, giới hạn số lần thử OTP, và không dùng nội dung challenge làm kênh xác nhận một account tùy ý có tồn tại.

## 13. Rate limiting, lockout và anti-abuse

Thông báo lỗi chung giúp che account existence ở một request, nhưng attacker có thể thử hàng nghìn username và đo khác biệt. Vì vậy cần **defense in depth**:

- Giới hạn số lần thử theo IP hoặc nhóm mạng, đồng thời xem xét account identifier đã chuẩn hóa.
- Giới hạn đồng thời và quy mô trên toàn dịch vụ, nhất là login, forgot password, register và OTP.
- Dùng backoff/challenge theo rủi ro thay vì chỉ dựa vào một CAPTCHA dễ bị vượt.
- Theo dõi password spraying (ít password trên nhiều user) và credential stuffing (nhiều cặp user/password).
- Tránh khóa vĩnh viễn tài khoản của nạn nhân chỉ vì người ngoài cố tình gửi nhiều password sai.
- Thiết kế 429, Retry-After hoặc challenge sao cho không tiết lộ account có thật qua khác biệt chính sách.
- Cân nhắc chính sách phục hồi tài khoản đã được xác minh và kênh hỗ trợ.

### 13.1. Chỉ giới hạn theo IP chưa đủ

Attacker có thể dùng nhiều proxy/IP, còn nhiều người dùng hợp lệ có thể đi chung NAT. Kết hợp nhiều tín hiệu: IP, client/device reputation, normalized identifier, thời gian, session, khu vực, số lần thử gần đây và mẫu hành vi.

Việc lưu attempt counters theo username phải **không làm endpoint công khai tiết lộ account existence**. Ví dụ một username có thật bị chuyển ngay sang trang “Account locked” trong khi username giả tiếp tục nhận “Bad password” sẽ tạo tín hiệu lộ account.

### 13.2. Không dùng lockout làm công cụ DoS

Khóa một account sau vài lần sai password có thể bị attacker lạm dụng để ngăn chủ account đăng nhập. Cần cân bằng security và availability: backoff có giới hạn, policy xác minh, kênh khôi phục, bot defenses và monitoring.

Không có ngưỡng khóa/rate-limit cố định đúng cho mọi sản phẩm; điều chỉnh dựa trên rủi ro, quy mô, khả năng phục hồi, threat intelligence và đo lường.

### 13.3. Phản hồi rate-limit phải nhất quán ở cùng điều kiện

Có thể trả HTTP 429 khi áp dụng throttle, nhưng đừng để **chỉ username có thật** mới nhận 429 trong cùng kịch bản thử. Hãy kiểm tra chính sách counters và trigger conditions; một lỗi công khai chung trong vòng 429 cũng có thể làm lộ account qua tần suất hoặc thời điểm xuất hiện.

## 14. Logging và audit: đủ chi tiết cho vận hành, không lộ dữ liệu cho client

Security team cần biết có bao nhiêu authentication failures, các loại lỗi và dấu hiệu tấn công. Vì vậy không nhất thiết **xóa toàn bộ lý do nội bộ**.

Một chiến lược logging có thể gồm:

| Trường log | Hướng xử lý |
| --- | --- |
| Event name | AUTH_FAILURE hoặc tương tự |
| Timestamp, request ID | Ghi để tương quan và điều tra |
| Failure category nội bộ | Có thể ghi với quyền truy cập giới hạn |
| Client IP | Áp dụng chính sách dữ liệu cá nhân và retention |
| Username/email | Tránh ghi raw ở luồng phổ thông; nếu thật sự cần, dùng hình thức giảm nhận diện, phân quyền chặt |
| Raw password, Authorization, OTP, token | **Không bao giờ ghi** |
| Full Authentication/Principal | Không log nguyên object nếu có khả năng chứa secret/PII |
| Exception stack trace | Chỉ trong hệ thống nội bộ được kiểm soát, không đưa ra response |
| HTTP response public | Mã và body chung theo hợp đồng |

Một lỗi rất thường gặp là viết:

~~~java
// Không nên dùng trong production:
log.warn("Login failed for {}: {}", username, exception);
~~~

Câu lệnh này có thể chứa username do client tự khai, thông tin trạng thái và chi tiết exception; logs có thể bị đẩy sang hệ thống tập trung hoặc dashboard có nhiều người xem. Đừng in raw Authentication hoặc request headers để “debug nhanh”.

Với hệ thống thực, nên dùng **audit pipeline riêng, field allowlist, log redaction, phân quyền xem và retention**, để security responders điều tra mà không tạo ra một kho bí mật ngoài ý muốn.

### 14.1. Đừng đưa internal reason vào response

Không làm:

~~~java
response.getWriter().write(
    "{\"error\":\"" + authenticationException.getClass().getSimpleName() + "\"}"
);
~~~

Đây là **anti-pattern minh họa**, không phải code an toàn. Exception type có thể phân biệt UsernameNotFoundException, LockedException, DisabledException hay InternalAuthenticationServiceException.

Cần map sang **một public code thống nhất** cho các lỗi authentication thích hợp, ví dụ invalid_credentials; chi tiết giữ trong hệ thống được phân quyền.

## 15. Kiểm thử MockMvc cho hợp đồng lỗi công khai

Kiểm thử response có giá trị hơn việc chỉ mở browser và nhìn cùng một dòng tiếng Việt. Hãy kiểm tra **status, body và WWW-Authenticate** cho những trường hợp tương đương.

Sau khi đã thêm testImplementation spring-boot-starter-test ở mục 7, tạo file **src/test/java/com/example/safeauth/SafeAuthApplicationTest.java**:

~~~java
package com.example.safeauth;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SafeAuthApplicationTest {

    @Autowired
    MockMvc mvc;

    private String basic(String user, String password) {
        String pair = user + ":" + password;
        String value = Base64.getEncoder()
            .encodeToString(pair.getBytes(StandardCharsets.UTF_8));
        return "Basic " + value;
    }

    private MvcResult expectSameFailure(String user, String password)
            throws Exception {
        return mvc.perform(get("/private")
                .header(HttpHeaders.AUTHORIZATION, basic(user, password)))
            .andExpect(status().isUnauthorized())
            .andExpect(content().json(
                "{\"error\":\"invalid_credentials\"}"))
            .andReturn();
    }

    @Test
    void failedLoginsDoNotRevealAccountStateInHttpBody()
            throws Exception {

        MvcResult unknown = expectSameFailure("ghost", "anything");
        MvcResult wrong = expectSameFailure("alice", "wrong");
        MvcResult locked = expectSameFailure("locked", "locked123");
        MvcResult disabled = expectSameFailure(
            "disabled", "disabled123");

        String publicBody = unknown.getResponse().getContentAsString();

        assertEquals(publicBody,
            wrong.getResponse().getContentAsString());
        assertEquals(publicBody,
            locked.getResponse().getContentAsString());
        assertEquals(publicBody,
            disabled.getResponse().getContentAsString());

        String challenge = unknown.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE);

        assertEquals(challenge, wrong.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE));
        assertEquals(challenge, locked.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE));
        assertEquals(challenge, disabled.getResponse()
            .getHeader(HttpHeaders.WWW_AUTHENTICATE));
    }

    @Test
    void authenticationAndAuthorizationRemainSeparate()
            throws Exception {
        mvc.perform(get("/private")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("alice", "learn123")))
            .andExpect(status().isOk())
            .andExpect(content().string("private OK"));

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("alice", "learn123")))
            .andExpect(status().isForbidden())
            .andExpect(content().json(
                "{\"error\":\"access_denied\"}"));

        mvc.perform(get("/admin")
                .header(HttpHeaders.AUTHORIZATION,
                    basic("admin", "admin123")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin OK"));
    }
}
~~~

Đây là một **file test đầy đủ** trong cùng project demo, chỉ dùng MockMvc và header Basic được tạo bằng Base64. Nó không cần spring-security-test chỉ để kiểm thử HTTP Basic vì header được tự tạo trong helper.

Chạy:

~~~bash
./gradlew test
~~~

Trong PowerShell sử dụng **.\gradlew.bat test**.

### 15.1. Test này chứng minh được gì?

- Các nhánh unknown user, wrong password, locked, disabled cùng trả 401.
- Body JSON của các nhánh lỗi bằng nhau.
- WWW-Authenticate header của các nhánh lỗi bằng nhau.
- Alice đăng nhập đúng vẫn được vào endpoint authenticated.
- Alice thiếu role ADMIN nhận 403 và không bị báo là sai credentials.
- Admin có role đúng nhận 200.

### 15.2. Test này chưa chứng minh được gì?

- **Không chứng minh chống timing side channel.** MockMvc không phản ánh đầy đủ mạng, DB thật, cache, CPU, JIT, GC, contention, SSL/proxy và phân phối độ trễ.
- Không chứng minh đã cấu hình rate limiting, CAPTCHA, account recovery hay audit.
- Không kiểm tra email side effects của reset/registration.
- Không bảo đảm body của mọi exception từ mọi filter bên ngoài SecurityFilterChain đều theo cùng schema.
- Không thay thế review security advisory và các integration/performance tests trên dependency đã vá.

Đo timing phải thực hiện trong môi trường kiểm thử có quyền, có dữ liệu thử được kiểm soát và phương pháp thống kê phù hợp. **Không lấy một vài lệnh curl đơn lẻ để kết luận hệ thống đã chống timing.**

## 16. Kỹ thuật kiểm thử phòng thủ: ma trận không tiết lộ danh tính

Hãy đặt các cột sau cho một bài kiểm thử login:

| Tình huống | Status | Public code/body | Redirect/headers | Rủi ro cần xét |
| --- | --- | --- | --- | --- |
| Username không tồn tại | 401 | Chung | Chung | Lookup nhanh, timing |
| Username có, password sai | 401 | Chung | Chung | Hash cost |
| Account disabled | 401 | Chung | Chung | Pre-check timing, advisory |
| Account locked | 401 | Chung | Chung | Trạng thái account/rate limit |
| Account expired | 401 | Chung | Chung | Pre-check, recovery path |
| Password đúng, user hợp lệ | 200 | Kết quả đăng nhập | Theo auth mechanism | Không lộ secret |
| Đã login nhưng không đủ role | 403 | access_denied | Theo authorization | Không nhầm với login |
| Login service tạm lỗi | Chính sách vận hành | Lỗi hệ thống chung | Không nêu chi tiết SQL | Availability/error handling |

Ma trận này là **mục tiêu thiết kế**, không phải khẳng định mọi cơ chế/phiên bản Spring Security đều tự cung cấp. Khi ứng dụng có nhiều SecurityFilterChain, cần kiểm tra entry point và failure handler **trong từng chain**. Không mặc định cấu hình chung của một chain áp dụng cho chain khác.

### 16.1. Tại sao cần kiểm tra network response thay vì chỉ UI?

UI có thể ẩn một status khác trong Developer Tools, hoặc JavaScript gọi API nhận error code nội bộ rồi chỉ hiển thị chung. Attacker trực tiếp gọi API vẫn thấy sự khác biệt. Phải quan sát **response thực từ endpoint**, kể cả status, headers, body, redirect và thời gian.

### 16.2. Kiểm thử form login

Với form login, so sánh cho unknown/wrong/locked/disabled:

- Có cùng URL redirect không?
- Cùng method/status và cùng query params không?
- Cùng template lỗi và response size tương đương không?
- Có branch render câu “Tài khoản bị khóa” không?
- Session/cookie flow có khác theo trạng thái account không?
- Có sự kiện email/SMS để người ngoài suy ra outcome không?

Trường hợp UI cần hỗ trợ account đã xác minh có thể có flow riêng sau khi chứng minh quyền sở hữu; không đưa các nhánh ấy vào endpoint thử username công khai.

## 17. Một số sai lầm nguy hiểm trong code

### 17.1. Trả message trực tiếp từ AuthenticationException

~~~java
// Sai: exception có thể tiết lộ account state.
response.getWriter().write(exception.getMessage());
~~~

Ngay cả khi default message là “Bad credentials” hôm nay, thay provider, localization hoặc custom exception sau này có thể biến message thành thông tin nhạy cảm. Chọn public error code tường minh.

### 17.2. Dùng UsernameNotFoundException làm HTTP 404

~~~text
UsernameNotFoundException -> HTTP 404
BadCredentialsException   -> HTTP 401
~~~

Điều này tạo ra một kênh xác nhận tài khoản. Với endpoint đăng nhập, sự tồn tại của resource user **không** nên quyết định status công khai theo cách này.

### 17.3. Khóa tài khoản rồi thông báo khóa cho mọi người

Nếu bất cứ ai nhập username locked đều thấy “Tài khoản này đã bị khóa vì 5 lần sai”, attacker biết account có thật. Có thể gây DoS bằng việc cố ý khóa tài khoản nạn nhân. Cần kết hợp authentication flow, throttling và recovery an toàn.

### 17.4. Kiểm tra user bằng API riêng trước khi login

Một endpoint như GET /users/exists?email=... công khai có thể làm vô hiệu mọi cố gắng chống enumeration ở /login. Đánh giá **toàn bộ bề mặt sản phẩm**: autocomplete, invitation, support, reset, register, resend activation, change email và profile lookup.

### 17.5. Luôn trả 200 nhưng body khác nhau

Trả HTTP 200 cho tất cả lỗi không đủ an toàn nếu JSON gồm field accountFound hoặc hint khác nhau. Không dùng một status duy nhất như “lá chắn”, trong khi response vẫn phân nhánh theo sự tồn tại.

### 17.6. Tự so sánh password bằng equals

Password phải được lưu dưới dạng hash phù hợp, dùng PasswordEncoder.matches. So sánh String.equals(raw, storedHash), lưu plaintext hoặc tạo hash bằng thuật toán không phù hợp đều làm sai luồng xác thực và tăng rủi ro credentials.

### 17.7. Bỏ qua lỗi của dependency

Một handler chung chỉ chuẩn hóa public response; nó không sửa một timing vulnerability bên trong provider. Cần đối chiếu advisory và nâng dependency lên bản đã được sửa, không chỉ che thông báo.

### 17.8. Dựa vào câu “tài khoản không tồn tại” để hỗ trợ người dùng

Một người dùng thật có thể nhập sai email, nhưng thông báo cụ thể cho anonymous là cơ hội enumeration. Hãy dùng hướng dẫn chung, đường quên mật khẩu và một luồng hỗ trợ có xác minh quyền sở hữu để vẫn giúp người dùng hợp lệ.

## 18. Checklist triển khai

Trước khi đưa tính năng login hoặc password reset ra production, rà soát:

1. **Đăng nhập lỗi:** user không tồn tại, password sai, account locked/disabled/expired có cùng public code/body/status trong flow tương đương.
2. **Không lộ qua headers/redirect:** không có tên exception, account status hoặc URL riêng.
3. **Timing:** không tự viết early exit, đã đánh giá các branch lookup/hash/status/cache và dùng phiên bản provider đã vá.
4. **Authentication provider:** dùng cơ chế được bảo trì; không đổi hideUserNotFoundExceptions thành false cho luồng công khai nếu không có lý do được đánh giá.
5. **Đăng nhập thành công:** principal/authorities đến từ nguồn tin cậy; không chứa password/secret trong JSON.
6. **Thiếu quyền:** HTTP 403 đúng nghĩa khi đã xác thực, không bị báo nhầm “sai password”.
7. **Reset/registration/OTP:** kiểm tra enumeration ở các endpoint liên quan, kể cả side effects.
8. **Rate limiting:** giới hạn tấn công tự động mà không tạo tín hiệu account existence hoặc gây khóa hàng loạt.
9. **Logging:** không log password/token/Authorization, giới hạn raw identifier, audit reason chỉ ở hệ thống được phân quyền.
10. **Session và token:** CSRF, HTTPS, cookie flags, TTL, logout và revocation theo cơ chế client.
11. **Test:** kiểm thử contract HTTP, redirect, headers, case normalization, cache và timing trong môi trường được cho phép.
12. **Dependencies:** đối chiếu Spring Security/BOM với security advisory; kiểm thử sau nâng cấp.
13. **Đường lỗi hệ thống:** không phát tán SQL/stack trace, tránh gắn trạng thái lỗi hệ thống với account tồn tại.
14. **Nội dung UI:** chỉ thông báo chung cho người chưa xác minh; trợ giúp cụ thể phải nằm sau bước chứng minh quyền sở hữu.
15. **Monitoring:** phát hiện password spraying, credential stuffing, lockout abuse và sự gia tăng thất bại.

## 19. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** Vì sao “Sai mật khẩu” khi có user và “Không tìm thấy user” khi không có user là nguy hiểm?  
**Đáp:** Hai response cho phép xác nhận user tồn tại mà không cần biết password, hỗ trợ user enumeration.

**Câu 2.** Cùng một lỗi JSON có đủ chống enumeration không?  
**Đáp:** Không. Status, redirect, headers, response size, timing, rate-limit và side effects cũng có thể tiết lộ account state.

**Câu 3.** AbstractUserDetailsAuthenticationProvider có cơ chế nào liên quan UsernameNotFoundException?  
**Đáp:** hideUserNotFoundExceptions mặc định true, thường chuyển unknown username thành BadCredentialsException thay vì phân biệt công khai.

**Câu 4.** Có nên bật setHideUserNotFoundExceptions(false) để giúp debug login?  
**Đáp:** Không trong flow công khai nếu chưa đánh giá bảo mật; dùng audit/observability nội bộ an toàn thay thế.

**Câu 5.** Tại sao username không có trong DB có thể phản hồi nhanh hơn password sai của user thật?  
**Đáp:** Nhánh không tìm thấy user có thể bỏ qua phép so hash tốn chi phí, tạo timing side channel.

**Câu 6.** Spring Security có bảo đảm luôn chống timing đối với account locked/disabled không?  
**Đáp:** Không. Cần xem version và security advisory; CVE-2026-22746 ghi nhận các phiên bản bị ảnh hưởng.

**Câu 7.** Trong demo, ghost, alice password sai, locked và disabled nên nhận gì?  
**Đáp:** Cùng HTTP 401, cùng body invalid_credentials và cùng WWW-Authenticate; riêng timing cần đánh giá tiếp.

**Câu 8.** Alice đăng nhập thành công nhưng vào endpoint admin bị 403 có phải user enumeration không?  
**Đáp:** Không; đó là authorization đã biết danh tính, cần giữ phân biệt với authentication failure.

**Câu 9.** Reset password nên phản hồi ra sao nếu email không có account?  
**Đáp:** Trả một thông báo chung cho request hợp lệ, ví dụ “Nếu có tài khoản phù hợp, hướng dẫn sẽ được gửi”, không công bố account existence.

**Câu 10.** Vì sao chỉ giới hạn login theo IP chưa đủ?  
**Đáp:** Attacker có thể phân tán qua nhiều IP, trong khi nhiều user hợp lệ có thể dùng chung một IP/NAT.

**Câu 11.** Có nên log toàn bộ AuthenticationException.getMessage() lên response để hỗ trợ khách hàng?  
**Đáp:** Không. Internal reason có thể lộ account state; chỉ công bố code chung và giữ audit chi tiết ở hệ thống được bảo vệ.

**Câu 12.** MockMvc kiểm tra cùng body/status đã chứng minh chặn CVE timing chưa?  
**Đáp:** Chưa. Nó kiểm tra HTTP contract, không kiểm thử phân phối thời gian hoặc dependency chưa vá.

**Câu 13.** Tài khoản bị khóa mà vẫn hiện “Account locked” ở trang login công khai có rủi ro gì?  
**Đáp:** Người ngoài có thể xác nhận username có tồn tại; nên dùng lỗi chung và kênh khôi phục có xác minh.

**Câu 14.** Vì sao không nên tự thêm Thread.sleep vào nhánh unknown user?  
**Đáp:** Delay cố định không cân bằng được mọi biến động xử lý, có thể tạo side channel khác và làm giảm khả năng phục vụ.

## 20. Tài liệu tham khảo chính thức

- OWASP Authentication Cheat Sheet — Authentication Responses, User Enumeration và Rate Limiting: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- Spring Security Advisory CVE-2026-22746 (20/04/2026): https://spring.io/security/cve-2026-22746/
- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — DaoAuthenticationProvider: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/dao-authentication-provider.html
- Spring Security — HTTP Basic Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security — Form Login Authentication: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security — Password Storage: https://docs.spring.io/spring-security/reference/features/authentication/password-storage.html
- Spring Security — Servlet Security Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorization HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot 3.3 — Spring Security Configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
