# Base64 không phải mã hóa bảo mật và yêu cầu dùng HTTPS trong HTTP Basic

> **Ý chính:** HTTP Basic gửi cặp tên người dùng và mật khẩu dưới dạng Base64. Base64 chỉ là cách biểu diễn dữ liệu, không giấu được bí mật. Khi dùng HTTP Basic, mọi yêu cầu chứa thông tin xác thực phải được truyền qua HTTPS với chứng chỉ được kiểm tra hợp lệ.

## 1. HTTP Basic thực sự gửi những gì?

Theo RFC 7617, ứng dụng khách tạo chuỗi **username:password**, chuyển chuỗi đó thành các byte theo bộ mã ký tự đã thỏa thuận rồi mã hóa Base64. Phần Base64 được gắn vào header **Authorization** cùng tiền tố **Basic**.

Ví dụ với tài khoản minh họa **alice** và mật khẩu giả **demo-pass**:

~~~http
GET /hello HTTP/1.1
Host: api.example.com
Authorization: Basic YWxpY2U6ZGVtby1wYXNz
~~~

Chuỗi **YWxpY2U6ZGVtby1wYXNz** có thể được giải mã ngược tức thì thành **alice:demo-pass**. Việc nhìn thấy ký tự khó đọc không có nghĩa là chúng đã được bảo mật. Mật khẩu trong ví dụ chỉ dùng để học, tuyệt đối không dùng mật khẩu thật trong tài liệu hoặc lệnh minh họa.

Luồng HTTP Basic thường diễn ra như sau:

1. Client yêu cầu tài nguyên cần xác thực nhưng chưa cung cấp thông tin.
2. Server trả **401 Unauthorized**, thông thường kèm một lời thách thức **WWW-Authenticate** để thông báo phương thức Basic và realm.
3. Client gửi lại yêu cầu kèm **Authorization: Basic ...**. Một số client có thể chủ động gửi header này ngay từ yêu cầu đầu tiên.
4. Spring Security dùng **BasicAuthenticationFilter** để đọc thông tin, tạo **UsernamePasswordAuthenticationToken** và chuyển cho **AuthenticationManager** kiểm tra.
5. Đúng mật khẩu và đủ quyền thì request được xử lý; thông tin xác thực sai thường dẫn tới **401**. Nếu đã xác thực nhưng thiếu quyền, server thường trả **403 Forbidden**.

Ví dụ một lời thách thức:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
~~~

Không nên xem lời thách thức là điều kiện tiên quyết để gửi mật khẩu: client được cấu hình gửi Basic trước có thể đặt header **Authorization** vào yêu cầu đầu tiên. Vì vậy, ngay cả một lần truy cập HTTP rồi mới chuyển hướng sang HTTPS cũng có thể làm lộ mật khẩu.

## 2. Encoding khác encryption và hashing như thế nào?

| Cơ chế | Mục đích | Có thể đảo ngược? | Vai trò trong bài |
| --- | --- | --- | --- |
| **Base64 encoding** | Biểu diễn byte bằng ký tự phù hợp với giao thức văn bản | Có, không cần khóa | Đóng gói cặp username/password cho HTTP Basic |
| **Encryption** | Bảo vệ tính bí mật bằng thuật toán và khóa | Có, với khóa phù hợp | TLS mã hóa dữ liệu khi truyền qua HTTPS |
| **Password hashing** | Lưu và kiểm tra mật khẩu mà không cần lưu mật khẩu rõ | Không có phép giải mã trực tiếp; kiểm tra bằng đối chiếu | BCrypt/Argon2 dùng khi lưu mật khẩu phía server |

Chỉ đổi Base64 sang hex, URL encoding hoặc một kiểu biến đổi chuỗi khác vẫn không tạo ra bảo mật. **Base64 không phải phép mã hóa mật mã, không dùng khóa, không có độ bí mật.** Đổi thuật toán biểu diễn không giải quyết vấn đề nghe lén trên mạng.

### Thí nghiệm có thể chạy với Java 17+

Lưu đoạn mã sau vào tệp **BasicBase64Demo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class BasicBase64Demo {
    public static void main(String[] args) {
        String credentials = "alice:demo-pass";

        String token = Base64.getEncoder().encodeToString(
                credentials.getBytes(StandardCharsets.UTF_8));

        String restored = new String(
                Base64.getDecoder().decode(token),
                StandardCharsets.UTF_8);

        System.out.println("Token: " + token);
        System.out.println("Decoded: " + restored);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac BasicBase64Demo.java
java BasicBase64Demo
~~~

Kết quả chính xác:

~~~text
Token: YWxpY2U6ZGVtby1wYXNz
Decoded: alice:demo-pass
~~~

Không cần mật khẩu hay khóa giải mã nào để khôi phục cặp thông tin. Đoạn Java dùng UTF-8 để thí nghiệm nhất quán; với HTTP Basic thực tế, cần chú ý quy tắc charset và khả năng tương thích client/server theo RFC 7617 khi dùng ký tự ngoài ASCII.

## 3. Vì sao phải dùng HTTPS/TLS?

Nếu gửi header Basic qua **HTTP**, một người có thể đọc được lưu lượng trên đường truyền có thể thu header, giải mã Base64 và lấy mật khẩu. Sau đó họ có thể dùng lại mật khẩu đó để mạo danh người dùng. HTTP cũng không tự bảo vệ tính toàn vẹn, nên kẻ đứng giữa có thể sửa nội dung request/response.

**HTTPS** thiết lập kết nối TLS trước khi gửi các thông điệp HTTP. Với chứng chỉ server được xác minh đúng tên miền và chuỗi tin cậy, TLS giúp:

- **Bảo mật dữ liệu truyền:** header Authorization, đường dẫn và nội dung HTTP nằm trong phần được mã hóa trên kết nối TLS.
- **Bảo vệ tính toàn vẹn:** phát hiện việc thay đổi dữ liệu trái phép trên đường truyền.
- **Xác thực đầu cuối TLS:** client có căn cứ xác minh đang kết nối đúng máy chủ được cấp chứng chỉ, hạn chế tấn công giả mạo trung gian.

Ví dụ so sánh:

| Tình huống | Hệ quả |
| --- | --- |
| HTTP + Basic | Header chứa Base64 có thể bị đọc và đảo ngược thành mật khẩu nếu lưu lượng bị nghe lén. **Không an toàn.** |
| HTTPS + Basic, chứng chỉ hợp lệ | Người quan sát thụ động trên đường truyền không thể đọc trực tiếp header HTTP. **Đây là yêu cầu tối thiểu khi dùng Basic.** |
| HTTPS nhưng ứng dụng/proxy ghi Authorization vào log | Người đọc log vẫn lấy được credential. TLS không bảo vệ dữ liệu sau khi giải mã tại điểm kết thúc TLS. |
| HTTPS tới reverse proxy nhưng đoạn proxy → backend dùng HTTP | Dữ liệu trên đoạn backend đó có thể bị lộ nếu mạng trung gian không tin cậy; cần bảo vệ hop nội bộ theo mô hình đe dọa. |
| HTTP trả 301/302 chuyển sang HTTPS | Yêu cầu HTTP đầu tiên có thể đã mang credential. Chuyển hướng **không bù được** việc gửi bí mật trước khi TLS được thiết lập. |

Ba điều cần phân biệt:

1. **HTTPS bảo vệ lúc truyền**, không có nghĩa mật khẩu lưu trong database đã an toàn: phía server vẫn cần hàm băm mật khẩu phù hợp.
2. **HTTPS kết thúc tại đâu thì ở đó dữ liệu được giải mã**: web server, load balancer hay reverse proxy có thể thấy header; phải kiểm soát log, quyền truy cập và các chặng sau điểm kết thúc TLS.
3. **HTTPS không thay thế chính sách xác thực**: HTTP Basic vẫn dùng lại cùng credential theo yêu cầu; cần mật khẩu mạnh, kiểm soát quyền, giới hạn thử sai và cơ chế thu hồi/đổi mật khẩu.

### Redirect và HSTS hỗ trợ, nhưng không thay thế HTTPS

Có thể cấu hình Spring Security chuyển yêu cầu HTTP sang HTTPS và gửi header **Strict-Transport-Security** trên phản hồi HTTPS để trình duyệt ưu tiên HTTPS cho lần truy cập sau. Nhưng trình duyệt chỉ học được HSTS sau khi đã nhận chính sách qua một kết nối HTTPS đáng tin cậy (trừ trường hợp preload). Với API client, cần cấu hình URL HTTPS ngay từ đầu, không gửi credential tới URL HTTP và không bỏ qua lỗi chứng chỉ.

Cách triển khai chặt chẽ là chỉ công bố endpoint HTTPS cho API chứa Basic; nếu cần cổng HTTP cho mục đích chuyển hướng, phải đảm bảo client không gửi thông tin xác thực trên cổng đó.

## 4. Áp dụng trong Spring Security (Servlet)

Ví dụ này dành cho một ứng dụng Spring Boot theo **Servlet/MVC**, Java 17+, có dependency **Spring Web** và **Spring Security**. Dưới đây là các lớp đầy đủ cần đặt trong package **com.example.demo** của một project Spring Boot tạo bằng Spring Initializr; phần bootstrap Spring Boot do project cung cấp. Ví dụ có thể dùng với API cấu hình hiện đại của Spring Security 6.5+/7.x.

### 4.1. Bật HTTP Basic và yêu cầu HTTPS

Tạo **src/main/java/com/example/demo/SecurityConfig.java**:

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
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

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .redirectToHttps(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String rawPassword) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(rawPassword))
                        .roles("READER")
                        .build());
    }
}
~~~

Giải thích:

- **httpBasic(...)** thêm cơ chế xử lý header Basic vào chuỗi filter. Có SecurityFilterChain tự cấu hình thì nên bật HTTP Basic tường minh.
- **authorizeHttpRequests(...)** yêu cầu người dùng đã đăng nhập với mọi endpoint.
- **redirectToHttps(...)** hỗ trợ chuyển yêu cầu HTTP sang HTTPS **nếu** máy chủ/proxy có nhận request HTTP. Nó không tạo chứng chỉ và không tự mở cổng TLS: phần TLS phải được cấu hình ở server hoặc reverse proxy.
- **BCryptPasswordEncoder** băm mật khẩu khi lưu phía server. Nó không thay đổi việc Basic truyền password trong header, nên vẫn cần HTTPS.
- Mật khẩu demo được đọc từ biến môi trường, không đặt trực tiếp trong mã nguồn. Ví dụ dùng user trong bộ nhớ để tập trung vào Basic; ứng dụng thực tế dùng kho người dùng thích hợp.

Tạo **src/main/java/com/example/demo/HelloController.java**:

~~~java
package com.example.demo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello(Authentication authentication) {
        return "Xin chao, " + authentication.getName() + "!";
    }
}
~~~

### 4.2. Cấu hình HTTPS cho Spring Boot

Trong **src/main/resources/application.properties**:

~~~properties
server.port=8443
server.ssl.key-store=file:./local-demo.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=local-demo
demo.user.password=${DEMO_USER_PASSWORD}
~~~

Cho bài thực hành trên localhost, tạo keystore PKCS#12 và xuất chứng chỉ tin cậy cục bộ bằng JDK **keytool**. Chạy lệnh tại thư mục gốc project:

~~~bash
keytool -genkeypair -alias local-demo -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore local-demo.p12 -storepass local-only-demo -dname "CN=localhost" -ext SAN=dns:localhost
keytool -exportcert -rfc -alias local-demo -keystore local-demo.p12 -storepass local-only-demo -file local-demo.crt
~~~

Ví dụ môi trường POSIX (Linux/macOS):

~~~bash
export TLS_KEYSTORE_PASSWORD=local-only-demo
export DEMO_USER_PASSWORD=demo-pass
./mvnw spring-boot:run
~~~

Trong PowerShell trên Windows, đặt hai biến bằng **$env:TLS_KEYSTORE_PASSWORD = "local-only-demo"** và **$env:DEMO_USER_PASSWORD = "demo-pass"**, sau đó chạy Maven wrapper **mvnw.cmd spring-boot:run** trong thư mục project.

**Chỉ dùng chứng chỉ tự ký và mật khẩu trên cho localhost.** Không commit tệp PKCS#12 có private key, mật khẩu hay chứng chỉ phát hành thử lên repository. Với môi trường thật, dùng chứng chỉ hợp lệ, quản lý secret tập trung và cấu hình TLS tại web server hoặc ingress.

Với cấu hình HTTPS của Spring Boot ở trên, ứng dụng lắng nghe cổng **8443** bằng TLS và mặc định không còn HTTP connector tại **8080**. Vì vậy, việc không truy cập được HTTP port là điều bình thường; không cần mở thêm cổng HTTP chỉ để thấy redirect.

### 4.3. Kiểm tra với curl

Sau khi ứng dụng chạy, thực hiện trong thư mục chứa **local-demo.crt**:

~~~bash
curl --cacert local-demo.crt -i https://localhost:8443/hello
curl --cacert local-demo.crt -i -u alice:demo-pass https://localhost:8443/hello
curl --cacert local-demo.crt -i -u alice:sai https://localhost:8443/hello
~~~

Kết quả kỳ vọng theo thứ tự:

1. **401 Unauthorized**: chưa gửi thông tin xác thực.
2. **200 OK**, body **Xin chao, alice!**: thông tin xác thực chính xác.
3. **401 Unauthorized**: mật khẩu không đúng.

Tham số **--cacert** cho curl kiểm tra chứng chỉ tự ký bằng chứng chỉ đã xuất cho localhost; không dùng **-k/--insecure** để bỏ qua xác minh TLS. Tham số **-u alice:demo-pass** chỉ dùng với credential giả trong phòng thí nghiệm: trên máy thật, dòng lệnh và lịch sử shell có thể làm lộ mật khẩu; dùng phương thức nhập secret an toàn cho từng môi trường.

## 5. Checklist triển khai an toàn

- **Buộc client dùng URL https:// ngay từ lần gửi đầu tiên.** Từ chối cấu hình API client trỏ đến http://; không xem Base64 hoặc redirect là biện pháp bảo mật.
- **Xác minh chứng chỉ TLS.** Kiểm tra hostname, chuỗi tin cậy, hiệu lực chứng chỉ; không vô hiệu hóa xác minh để làm cho ứng dụng “chạy được”.
- **Thiết lập HTTPS ở đúng chặng.** Nếu TLS kết thúc tại load balancer hoặc API gateway, đánh giá và bảo vệ kết nối tới backend. Chỉ tin **Forwarded/X-Forwarded-Proto** do proxy tin cậy thiết lập; ngăn client bên ngoài tự giả các header này.
- **Không ghi bí mật.** Che hoặc loại bỏ Authorization, cookie, mật khẩu khỏi access log, tracing, thông báo lỗi và ảnh chụp công cụ debug. Không đặt credential trong URL.
- **Lưu mật khẩu đúng cách.** Dùng PasswordEncoder mạnh (như BCrypt), chính sách mật khẩu, giới hạn thử sai, khóa/thu hồi hoặc xoay vòng credential khi thích hợp.
- **Giữ các lớp bảo vệ khác.** HTTPS không thay thế phân quyền, chống CSRF cho các trường hợp ứng dụng cần, giám sát truy cập hay bảo mật trình duyệt. Không tắt CSRF chỉ để làm ví dụ HTTP Basic hoạt động.
- **Đánh giá mức phù hợp của Basic.** Với API nội bộ đơn giản hoặc client máy-máy có quản lý secret, Basic qua HTTPS có thể chấp nhận theo thiết kế. Khi cần đăng nhập người dùng, MFA, phân quyền theo phiên hoặc token ngắn hạn, cân nhắc giải pháp hiện đại; bất kỳ bearer token nào cũng vẫn cần TLS.

## 6. Hiểu đúng qua các câu hỏi nhanh

**Hỏi: Header Basic trông như chuỗi bí mật; sao không đủ an toàn?** Vì bất cứ ai có token Base64 đều có thể giải mã nó thành username:password. Không cần tìm khóa.

**Hỏi: Mật khẩu đã được BCrypt trong database, có thể dùng HTTP không?** Không. BCrypt bảo vệ bản ghi lưu ở server; HTTP Basic vẫn đưa mật khẩu do client biết vào header trên đường truyền. Hai lớp bảo vệ giải quyết hai rủi ro khác nhau.

**Hỏi: Chuyển hướng HTTP sang HTTPS là đủ?** Không bảo đảm. Nếu client gửi Authorization trong request HTTP đầu tiên, thông tin đã bị phơi lộ trước phản hồi redirect. Client phải bắt đầu từ HTTPS.

**Hỏi: HTTPS có bảo vệ khi reverse proxy đã giải mã request rồi ghi toàn bộ header vào log?** Không. TLS chỉ bảo vệ luồng giữa các điểm kết thúc TLS; log vẫn phải được kiểm soát và lọc secret.

**Hỏi: Có HTTPS thì Basic có trở thành đăng nhập an toàn tuyệt đối không?** Không. TLS giảm nguy cơ nghe lén và sửa dữ liệu trên đường truyền, nhưng mật khẩu vẫn có thể bị lộ bởi endpoint bị xâm nhập, lừa đảo, log hoặc client bị chiếm quyền.

## 7. Tài liệu tham khảo

- [RFC 7617 — The Basic HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): định nghĩa token Base64, credential và cảnh báo bảo mật.
- [Spring Security — Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): luồng BasicAuthenticationFilter và SecurityFilterChain.
- [Spring Security — HTTP/HTTPS Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/http.html): redirect HTTPS, HSTS và cấu hình proxy.
- [Spring Boot — Embedded Web Servers / SSL](https://docs.spring.io/spring-boot/how-to/webserver.html): cấu hình server.ssl và khác biệt giữa HTTP connector với HTTPS connector.
