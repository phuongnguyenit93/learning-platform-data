# HTTP Basic: Xác thực từng yêu cầu và mối quan hệ với chính sách phiên

## Mục tiêu học tập

Sau bài này, bạn có thể:
- Giải thích vì sao HTTP Basic thường yêu cầu gửi thông tin xác thực trên **mỗi HTTP request** và vì sao điều đó khác với đăng nhập duy trì bằng session.
- Theo dõi đường đi của một request qua **BasicAuthenticationFilter**, **AuthenticationManager**, **SecurityContextHolder** và bước phân quyền.
- Phân biệt bốn giá trị **SessionCreationPolicy**; đặc biệt là **NEVER** và **STATELESS**.
- Cấu hình, chạy thử HTTP Basic không lưu trạng thái trong Spring Security Servlet và nhận diện các dấu hiệu cấu hình sai.

## 1. HTTP Basic xác thực một request như thế nào?

HTTP Basic là cơ chế xác thực ở tầng HTTP: client gửi header **Authorization** chứa cặp tên người dùng và mật khẩu, được mã hóa Base64 theo dạng **username:password**.

Ví dụ với tài khoản thực hành **demo** / **change-me**:

~~~http
GET /me HTTP/1.1
Host: localhost:8080
Authorization: Basic ZGVtbzpjaGFuZ2UtbWU=
~~~

Chuỗi Base64 trên giải mã thành **demo:change-me**. Base64 chỉ là biểu diễn dữ liệu, **không phải mã hóa bảo mật**: bất kỳ ai đọc được header đều có thể khôi phục thông tin đăng nhập. Vì vậy HTTP Basic phải dùng qua **HTTPS/TLS** trong môi trường thực tế; tránh ghi header này vào log hoặc telemetry.

Khi truy cập tài nguyên được bảo vệ mà chưa có thông tin xác thực hợp lệ, phản hồi điển hình là:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Realm"
~~~

Header **WWW-Authenticate** cho biết máy khách có thể gửi lại request kèm thông tin Basic. Tên **realm** là vùng bảo vệ do server cấu hình; giá trị và các header khác tùy ứng dụng. Browser có thể hiển thị hộp thoại đăng nhập và tự gửi lại thông tin đã ghi nhớ. Một số phản hồi dành cho AJAX có thể được cấu hình để không phát challenge cho trình duyệt; không nên coi hộp thoại đăng nhập là bằng chứng duy nhất của Basic.

**Không có bước đăng nhập bắt buộc riêng** như POST /login trong chính giao thức Basic. Mỗi request mang credential của nó hoặc trông cậy vào một cơ chế duy trì xác thực được cấu hình độc lập.

## 2. Đường đi của request trong Spring Security Servlet

Xét request đến **GET /me** khi ứng dụng cấu hình HTTP Basic:

1. **SecurityFilterChain** chọn chuỗi filter phù hợp với URL. **BasicAuthenticationFilter** kiểm tra header Authorization có scheme **Basic** hay không.
2. Nếu cần xác thực từ header, filter giải mã cặp username/password, tạo **UsernamePasswordAuthenticationToken** chưa xác thực và chuyển tới **AuthenticationManager**. Cơ chế cụ thể (ví dụ **DaoAuthenticationProvider**, **UserDetailsService**, **PasswordEncoder**) kiểm tra credential.
3. Khi thành công, kết quả **Authentication** chứa principal và authorities được đặt vào **SecurityContext** trong **SecurityContextHolder** của request hiện tại. Các filter phía sau và controller có thể lấy danh tính đó.
4. **AuthorizationFilter** kiểm tra quy tắc truy cập, ví dụ **authenticated()** hoặc **hasRole("ADMIN")**. Xác thực đúng không đồng nghĩa được phép vào mọi endpoint.
5. Khi request kết thúc, security context của luồng xử lý được dọn theo cơ chế filter. Việc danh tính có xuất hiện trong request kế tiếp hay không phụ thuộc **SecurityContextRepository** và các cơ chế xác thực khác, chứ không phải do bản thân biến trong **SecurityContextHolder** tồn tại mãi.

Nếu xác thực thất bại, Spring Security xóa context phù hợp và kích hoạt **AuthenticationEntryPoint** để trả lỗi xác thực, thường là **401** cùng challenge Basic. Nếu đã xác thực nhưng thiếu quyền, phản hồi thường là **403 Forbidden**.

Trường hợp request không gửi Authorization mà chưa được xác thực: **AuthorizationFilter** từ chối, **ExceptionTranslationFilter** chuyển sang khởi động xác thực qua entry point. Với Basic, **RequestCache** thường không cần lưu request gốc vì client có thể tự gửi lại.

### Hình dung ba request độc lập

~~~text
Request 1: GET /me, không Authorization
    -> chưa có Authentication -> 401 (+ WWW-Authenticate)

Request 2: GET /me, Authorization: Basic <credential hợp lệ>
    -> xác thực -> SecurityContext của request -> 200

Request 3: GET /me, không Authorization, không cơ chế lưu đăng nhập
    -> không có Authentication từ request trước -> 401
~~~

Điểm cốt lõi: **trạng thái xác thực trong phạm vi request** khác với **trạng thái đăng nhập được lưu giữa nhiều request**. Chính sách phiên quyết định Spring Security có thể dựa vào HttpSession để khôi phục SecurityContext hay không.

## 3. Basic, HttpSession và SecurityContextRepository là ba khái niệm khác nhau

- **HTTP Basic** mô tả cách client trình credential trong header HTTP. Nó không mặc nhiên định nghĩa một phiên đăng nhập trên server.
- **HttpSession** là đối tượng phiên của Servlet container, thường được nhận diện qua cookie **JSESSIONID**. Session có thể lưu nhiều loại dữ liệu, trong đó có hoặc không có SecurityContext.
- **SecurityContextHolder** cung cấp Authentication cho **request đang xử lý**. Đây không phải kho lưu phiên lâu dài.
- **SecurityContextRepository** quyết định cách tải và lưu SecurityContext giữa các request. **HttpSessionSecurityContextRepository** có thể dùng HttpSession, còn **NullSecurityContextRepository** không lưu/đọc context lâu dài.

Trong thiết kế API HTTP Basic không trạng thái, mỗi request được xác thực từ header và kết quả chỉ cần tồn tại trong request đó. Khi request kế tiếp đến, server không lấy danh tính từ phiên: **client phải gửi Authorization hợp lệ một lần nữa**.

Tuy nhiên, đừng suy luận rằng “cứ bật Basic thì Spring Security luôn gọi bộ kiểm tra mật khẩu trên mọi request”. Nếu ứng dụng đã khôi phục một Authentication hợp lệ bằng session hoặc cơ chế khác, filter có thể không cần xác thực lại cùng danh tính; remember-me nếu được bật cũng thay đổi hành vi. Muốn khẳng định xác thực từng request độc lập, phải xét **cả cơ chế Basic lẫn cấu hình lưu SecurityContext**.

## 4. Bốn chính sách tạo và sử dụng session

Spring Security Servlet cung cấp **SessionCreationPolicy**:

| Chính sách | Spring Security tạo HttpSession? | Có thể lấy SecurityContext từ HttpSession cũ? | Ý nghĩa khi dùng Basic |
| --- | --- | --- | --- |
| **ALWAYS** | Có, chủ động tạo | Có, tùy repository | Cho phép kiến trúc dựa vào session; không biến Basic thành đăng nhập qua session một cách tự động |
| **IF_REQUIRED** | Chỉ khi cần | Có, tùy repository | Session có thể xuất hiện do những thành phần khác; không cam kết Basic được lưu lại |
| **NEVER** | Không chủ động tạo | **Có**, nếu session đã tồn tại | Không tương đương stateless; dữ liệu xác thực có thể được khôi phục từ session có sẵn |
| **STATELESS** | Không tạo vì mục đích security context | **Không** dùng session để lấy SecurityContext | Phù hợp Basic xác thực độc lập từng request |

**Phân biệt quan trọng:**

- **NEVER**: Spring Security không chủ động tạo HttpSession, nhưng nếu session có từ trước, cấu hình cho phép dùng nó để lấy security context. Một component khác vẫn có thể tạo session.
- **STATELESS**: Spring Security không tạo HttpSession cho security context và không dùng HttpSession để khôi phục SecurityContext. Cơ chế ứng dụng khác vẫn có thể tự tạo session; vì vậy “STATELESS” không có nghĩa toàn bộ server tuyệt đối không bao giờ phát cookie.
- **ALWAYS** hoặc **IF_REQUIRED** chỉ điều khiển chính sách phiên, **không bảo đảm** rằng BasicAuthenticationFilter tự ghi Authentication của nó vào HttpSession.

Trong Spring Security hiện đại, việc lưu Authentication phụ thuộc vào repository được cài cho bộ lọc. Nếu muốn cố ý lưu kết quả Basic vào session, cần cấu hình thích hợp cho **BasicAuthenticationFilter** và kiểm tra chính sách phiên tương ứng. Chỉ đổi **STATELESS** sang **IF_REQUIRED** không phải cách đáng tin để có “đăng nhập một lần”.

### Hai tình huống cần phân biệt

**A. Basic + STATELESS (API điển hình)**

~~~text
GET /me + Authorization đúng  -> 200
GET /me không Authorization   -> 401
GET /me + JSESSIONID cũ       -> 401, nếu không có cơ chế xác thực khác
GET /me + Authorization đúng  -> 200
~~~

Vì không khôi phục Authentication từ session, mỗi request được bảo vệ cần credential hoặc một cơ chế xác thực khác hoạt động cho chính request đó.

**B. Basic + lưu Authentication trong HttpSession (cấu hình chủ động)**

~~~text
GET /me + Authorization đúng  -> Authentication được lưu trong session
GET /me + cookie phiên hợp lệ -> có thể được xác thực bằng context từ session
Hết hạn/xóa phiên             -> request không credential lại bị yêu cầu xác thực
~~~

Ở tình huống B, server phải quản lý thời hạn, hủy phiên, cookie và bảo vệ session. Đây là một thiết kế có trạng thái; việc Basic xuất hiện trong request đầu tiên không biến những request sau thành “Basic trên mọi request”. Không giả định tình huống B xảy ra chỉ vì đã bật HTTP Basic.

## 5. Ví dụ Spring Boot Servlet: Basic xác thực từng request, không dựa vào phiên

Ví dụ dùng **Java 17+**, Spring Boot Servlet với dependency **spring-boot-starter-web** và **spring-boot-starter-security**. Tạo file **src/main/java/com/example/basicauth/BasicAuthApplication.java** trong một ứng dụng Spring Boot có plugin Gradle/Maven tương ứng:

~~~java
package com.example.basicauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
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
public class BasicAuthApplication {

    public static void main(String[] args) {
        SpringApplication.run(BasicAuthApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                .password(encoder.encode("change-me"))
                .roles("READER")
                .build()
        );
    }

    @RestController
    static class Api {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/me")
        String me(Authentication authentication) {
            return "hello, " + authentication.getName();
        }

        @GetMapping("/admin")
        String admin() {
            return "admin";
        }
    }
}
~~~

Giải thích các lựa chọn:

1. **httpBasic(Customizer.withDefaults())** bật xử lý Authorization: Basic trong SecurityFilterChain đã cấu hình.
2. **sessionCreationPolicy(STATELESS)** đặt chính sách không khôi phục SecurityContext từ HttpSession; đây là phần giúp ví dụ có hành vi xác thực độc lập mỗi request.
3. **/public** cho phép truy cập ẩn danh; **/me** yêu cầu người dùng đã xác thực; **/admin** cần role ADMIN. Người dùng demo chỉ có role READER.
4. **PasswordEncoderFactories.createDelegatingPasswordEncoder()** băm mật khẩu trong ví dụ với encoder thích hợp; mật khẩu dạng chữ rõ chỉ là dữ liệu khởi tạo để thực hành. Trong production, dùng quản lý người dùng/secret an toàn và mật khẩu băm đã lưu, không nhúng credential trong mã nguồn.
5. Ví dụ chỉ mở endpoint GET nên giữ cấu hình bảo vệ CSRF mặc định. Với các phương thức thay đổi dữ liệu, quyết định CSRF phải dựa vào loại client và cách trình duyệt gửi credential.

Đây là **một file Java hoàn chỉnh trong dự án Spring Boot có dependency**, không phải chương trình chỉ dựa vào thư viện chuẩn JDK; lệnh **javac BasicAuthApplication.java** riêng lẻ sẽ thiếu classpath Spring. Với dự án Gradle Spring Boot, chạy từ thư mục dự án:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell dùng **.\gradlew.bat bootRun**. Nếu sử dụng Maven Spring Boot, lệnh tương ứng là **./mvnw spring-boot:run**. Mặc định ví dụ phục vụ tại **localhost:8080**, trừ khi cấu hình server.port khác.

### Gửi request và kiểm chứng

~~~bash
curl -sS http://localhost:8080/public
# public

curl -sS -u demo:change-me http://localhost:8080/me
# hello, demo

curl -i http://localhost:8080/me
# HTTP/1.1 401 ... (trích phần trạng thái)
# WWW-Authenticate: Basic realm="Realm" (thông thường)

curl -i -u demo:wrong http://localhost:8080/me
# HTTP/1.1 401 ... (sai credential)

curl -i -u demo:change-me http://localhost:8080/admin
# HTTP/1.1 403 ... (đã xác thực, thiếu role ADMIN)
~~~

Các dòng bắt đầu bằng **#** trong khối lệnh là phần kết quả hoặc trạng thái dự kiến để đối chiếu, không phải toàn bộ HTTP response. Header chi tiết có thể khác theo cấu hình và phiên bản. Hai phản hồi body đầu tiên lần lượt là **public** và **hello, demo** (không kèm newline do controller).

Hãy chú ý thử hai lệnh theo thứ tự: gọi **/me** với **-u demo:change-me** thành công, rồi gọi lại **/me** mà không có **-u**. Lệnh thứ hai vẫn trả **401**. Điều này không phải “mất phiên bất thường”: mỗi lần gọi curl là một request khác và chính sách **STATELESS** không cho phép dùng Authentication của lần trước từ HttpSession.

Trong ví dụ này, **/public** không cần đăng nhập. Tuy nhiên, nếu client chủ động gửi header Basic vào /public, filter vẫn có thể xử lý credential; quy tắc **permitAll()** chỉ có nghĩa tài nguyên không đòi hỏi xác thực để được truy cập.

## 6. Khi nào request thực sự được xác thực lại?

Gọi mỗi request là **R1**, **R2** với cùng người dùng:

| Cấu hình và header của R2 | Nguồn Authentication của R2 | Kết quả thường gặp |
| --- | --- | --- |
| **STATELESS**, R2 có Basic hợp lệ | Kiểm tra Basic trong R2 | Có thể truy cập tài nguyên được phép |
| **STATELESS**, R2 không có Basic | Không có context từ R1 để khôi phục | 401 với tài nguyên yêu cầu đăng nhập |
| **STATELESS**, R2 có Basic sai | Thử xác thực bằng credential sai | 401, dù R1 từng thành công |
| Context được lưu đúng cách trong HttpSession, R2 có cookie phiên | Có thể lấy Authentication từ session | Không nhất thiết phải gửi lại Basic |
| Có remember-me hoặc cơ chế khác | Có thể dùng cơ chế thay thế | Không thể khẳng định mỗi request đều tái kiểm tra mật khẩu |

Vì thế, phát biểu chính xác là: **trong mô hình HTTP Basic thuần stateless, request được bảo vệ phải tự mang credential và thường được xác thực độc lập**. Cần xem toàn bộ **SecurityFilterChain**, repository và các phương thức xác thực đang bật trước khi kết luận cho ứng dụng cụ thể.

## 7. Tác động về bảo mật, vận hành và lựa chọn kiến trúc

**Gửi mật khẩu nhiều lần:** Basic mang thông tin đăng nhập có thể khôi phục trên các request. Bắt buộc HTTPS, giới hạn nơi lưu/log header, xoay vòng secret và áp dụng biện pháp chống dò mật khẩu. Dù mã hóa TLS bảo vệ trên đường truyền, rò rỉ log hoặc client vẫn là nguy cơ.

**Thu hồi quyền và đổi mật khẩu:** Khi xác thực credential mới trên mỗi request, việc thay đổi mật khẩu/khóa tài khoản có thể có hiệu lực ở request tiếp theo, tùy cơ chế cache của provider. Khi dùng session, một Authentication đã lưu có thể tồn tại cho đến khi phiên hết hạn hoặc bị hủy; thay đổi dữ liệu người dùng không mặc nhiên xóa mọi phiên đang hoạt động.

**Logout:** Với Basic thuần stateless, server không có “phiên Basic” để hủy. Client hoặc browser có thể tiếp tục tự gửi Authorization đã nhớ. Gọi endpoint logout hoặc xóa JSESSIONID không bảo đảm browser ngừng gửi header Basic; cần ngừng gửi credential, xóa cache credential phía client hoặc thu hồi/đổi mật khẩu theo nhu cầu.

**CSRF:** Stateless không đồng nghĩa miễn nhiễm CSRF. **Trình duyệt có thể tự đính kèm HTTP Basic credential** vào request đến cùng origin; nếu ứng dụng có thao tác thay đổi trạng thái, vẫn phải đánh giá và áp dụng bảo vệ CSRF phù hợp. Không tắt CSRF chỉ vì đã chọn **STATELESS**. Với API dùng client không phải browser và cơ chế credential không tự gửi, quyết định có thể khác dựa vào threat model thực tế.

**Hiệu năng:** Tái xác thực mỗi request có thể làm tăng số lần tra cứu người dùng và kiểm tra mật khẩu; cần đo tải, dùng cache có kiểm soát và giới hạn tần suất. Không dùng lưu session một cách ngẫu nhiên chỉ để che đi vấn đề hiệu năng mà chưa xem tác động bảo mật.

**Phạm vi phù hợp:** Basic đơn giản cho client kỹ thuật hoặc dịch vụ nội bộ đã kiểm soát, qua TLS, với thông tin xác thực được quản lý chặt. Nếu cần trải nghiệm đăng nhập trình duyệt, logout rõ ràng, MFA hoặc đăng nhập liên kết, nên đánh giá cơ chế phù hợp như form session hoặc OIDC/OAuth2 thay vì kỳ vọng Basic cung cấp các tính năng đó.

## 8. Lỗi hiểu sai và cách chẩn đoán

| Triệu chứng hoặc nhận định | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| “GET đầu thành công, GET kế không Authorization trả 401” | Đây là hành vi mong đợi của Basic stateless | Kiểm tra client có gửi Authorization trên **mọi request được bảo vệ** hay không |
| “Đặt NEVER nên chắc chắn không có session” | NEVER vẫn có thể sử dụng session đã tồn tại; nơi khác có thể tạo session | Kiểm tra HttpSession, RequestCache và các thành phần gọi getSession() |
| “Đặt IF_REQUIRED thì Basic tự ghi đăng nhập vào session” | Policy không thay cấu hình lưu Authentication của Basic filter | Kiểm tra **SecurityContextRepository** được sử dụng khi xác thực thành công |
| “Bật STATELESS thì không bao giờ có JSESSIONID” | Ứng dụng hoặc thư viện khác vẫn có thể tạo HttpSession | Truy vết nơi tạo session; phân biệt servlet session và security context |
| “Có Basic đúng mà /admin trả 403 là lỗi xác thực” | Xác thực thành công nhưng thiếu quyền | Kiểm tra authorities/roles và yêu cầu hasRole/hasAuthority |
| “Logout rồi browser vẫn gọi API được” | Browser tiếp tục gửi Authorization đã lưu | Quan sát request thực tế; đổi/thu hồi credential nếu cần |
| “Không gửi Basic nhưng vẫn được truy cập” | Context có thể được khôi phục qua session, remember-me, hoặc cơ chế khác; cũng có thể endpoint permitAll | Kiểm tra rule URL, filter chain, repository và cookie |

Khi debug, xem **status 401 hay 403**, header **Authorization** (chỉ kiểm tra có/không, không ghi giá trị bí mật), **Cookie/JSESSIONID**, filter chain khớp với URL và nguồn Authentication trong request. Bật log Spring Security ở môi trường an toàn có kiểm soát; tránh log mật khẩu hoặc Base64 credential.

## 9. Tự kiểm tra hiểu bài

1. Request R1 gửi Basic đúng và nhận 200. R2 không gửi Authorization, ứng dụng dùng STATELESS, không có cơ chế đăng nhập khác. Vì sao R2 nhận 401? **Vì Authentication của R1 không được phục hồi từ HttpSession; R2 phải tự xác thực.**
2. Vì sao **NEVER** không giống **STATELESS**? **NEVER không chủ động tạo session nhưng có thể dùng session đã tồn tại; STATELESS không dùng session để lấy SecurityContext.**
3. Có thể dùng HTTP Basic và session cùng lúc không? **Có, khi chủ động cấu hình lưu/khôi phục Authentication qua repository và quản lý session tương ứng; Basic tự nó không yêu cầu điều đó.**
4. Vì sao client dùng Basic đúng vẫn bị 403? **Vì danh tính đã xác thực chưa đủ quyền cho endpoint.**
5. Có nên tắt CSRF chỉ vì đã cấu hình STATELESS? **Không; browser có thể tự gửi Basic credential, nên cần đánh giá nguy cơ CSRF từ hành vi client.**

## Tài liệu tham khảo

- [Spring Security Reference — Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html)
- [Spring Security Reference — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [SessionCreationPolicy API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/http/SessionCreationPolicy.html)
- [Spring Security Reference — CSRF](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
