# Điều kiện phiên bản và phạm vi hỗ trợ của One-Time Token Login

**One-Time Token Login (OTT Login)** là cơ chế đăng nhập bằng **token chỉ dùng một lần** do Spring Security hỗ trợ trực tiếp từ **Spring Security 6.4**. Người dùng nhập định danh như username/email, hệ thống sinh token ngắn hạn và gửi token qua một kênh được thiết kế riêng (thường là email chứa *magic link*). Người sở hữu token còn hạn gửi token lại để đăng nhập; sau khi được tiêu thụ thành công, **chính token đó không được dùng lại**.

Bài học tập trung vào hai câu hỏi của việc tích hợp: **(1) Phiên bản Java/Spring Boot/Spring Security nào đủ điều kiện dùng API tích hợp sẵn? (2) Framework đã hỗ trợ những gì, còn ứng dụng phải tự làm những gì?** Điều này đặc biệt quan trọng vì tên gọi OTT dễ bị nhầm với OTP/TOTP, xác thực hai yếu tố hoặc Bearer token, trong khi phạm vi tính năng khác nhau.

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.x**, **Spring Security 6.5.x đã vá lỗ hổng tương ứng**, ứng dụng **Servlet/MVC**. Các package/method Java bên dưới được đối chiếu theo API Spring Security 6.4/6.5; ứng dụng WebFlux cũng được hỗ trợ nhưng có **API reactive khác**.

## 1. One-Time Token là gì, không phải là gì?

| Cơ chế | Cách hoạt động | Có phải tính năng OTT Login? |
| --- | --- | --- |
| **Spring Security OTT** | Server sinh token dùng một lần, gắn với người dùng, có hạn, chuyển qua kênh riêng rồi tiêu thụ để tạo phiên đăng nhập | **Có** |
| **Magic link** | Cách giao token dưới dạng liên kết; người dùng mở link rồi hoàn tất đăng nhập | Thường là **phương thức chuyển OTT**, không phải tên của một loại token mới |
| **TOTP** | Mã từ authenticator dựa trên secret được chia sẻ trước và thời gian, ví dụ RFC 6238 | **Không**; cần cơ chế TOTP riêng |
| **HOTP** | Mã sinh từ shared secret và bộ đếm, ví dụ RFC 4226 | **Không**; cần cơ chế HOTP riêng |
| **OTP gửi SMS/email do ứng dụng tự xây** | Có thể là mã tự thiết kế, không nhất thiết dùng Spring OTT service | Không mặc định; cần quyết định và tích hợp |
| **OAuth2 Bearer access token/JWT** | Token dùng để gọi API, có thể được sử dụng nhiều lần trong thời gian hiệu lực | **Không phải** OTT Login |
| **Password reset token** | Chứng minh quyền thao tác đổi mật khẩu, mục đích khác đăng nhập | **Không** mặc định |
| **MFA/2FA** | Yêu cầu thêm yếu tố xác thực độc lập ngoài yếu tố chính | **Không tự động**; OTT mặc định là một cách đăng nhập, không tự làm yếu tố thứ hai |

**OTT không đòi người dùng cấu hình trước một secret TOTP** hay cài authenticator app; nó phụ thuộc vào kênh nhận token và cách ứng dụng xác minh người nhận. Nếu email bị chiếm quyền, người khác có thể nhận magic link. Vì vậy “không dùng mật khẩu” **không có nghĩa** “miễn nhiễm phishing/đánh cắp tài khoản”.

OTT có thể là một phương pháp **passwordless login**, nhưng chỉ tự chứng minh quyền sở hữu token tại thời điểm tiêu thụ; các yêu cầu chống gian lận, xác minh email ban đầu, device trust hoặc MFA phải do hệ thống thiết kế bổ sung.

## 2. Phiên bản tối thiểu và ma trận tương thích

### 2.1. Spring Security là phiên bản quyết định API

| Phiên bản Spring Security | One-Time Token Login tích hợp sẵn | Ý nghĩa |
| --- | --- | --- |
| **6.3.x và cũ hơn** | **Không có DSL OTT tích hợp được mô tả ở đây** | Không thể copy `http.oneTimeTokenLogin(...)` và kỳ vọng compile; cần nâng cấp hoặc tự làm giải pháp khác |
| **6.4.x** | **Có**, đây là nhánh đưa OTT vào framework | Servlet và reactive có API riêng; cần xem patch/security advisory của đúng phiên bản |
| **6.5.x** | **Có** | Tiếp tục hỗ trợ OTT; bổ sung khả năng tùy chỉnh request generation qua `GenerateOneTimeTokenRequestResolver`; ưu tiên patch đã khắc phục các lỗi bảo mật liên quan |
| **7.0.x và các nhánh 7.x tiếp theo** | **Có** | API OTT vẫn tồn tại; thay đổi nền tảng Spring Framework/Boot và các điểm extension cần kiểm theo Javadoc của phiên bản đang dùng |

**Điểm giới thiệu chính thức:** `OneTimeToken`, `OneTimeTokenService`, `OneTimeTokenAuthenticationProvider`, `OneTimeTokenLoginConfigurer`, các API reactive tương ứng mang dấu `Since: 6.4` trong Javadoc. Không nhầm một bài viết cũ/chưa cập nhật với kiểm tra dependency thực tế của project.

### 2.2. Spring Boot quản lý phiên bản nào?

Trong project Spring Boot, dependency management/BOM thường quyết định Spring Security cụ thể; không được suy phiên bản Security chỉ qua một annotation hoặc import.

| Dòng Spring Boot | Spring Security khi bắt đầu dòng tương ứng | Gợi ý sử dụng OTT |
| --- | --- | --- |
| **3.3.x** | Thông thường **6.3.x** | Mặc định **chưa có** DSL OTT 6.4; muốn dùng phải có kế hoạch nâng cấp tương thích, không chỉ thêm một dòng Java |
| **3.4.x** | Thông thường **6.4.x** | Hỗ trợ OTT từ framework, nhưng phải kiểm **patch** của Security và các dependency |
| **3.5.x** | Thông thường **6.5.x** | Hỗ trợ OTT, các API cấu hình thuận tiện hơn; cần bản đã vá nếu dùng JDBC OTT |
| **4.x** | Dòng Spring Security **7.x** tương ứng | Có OTT, nhưng phải kiểm tra hướng dẫn di trú và API đúng phiên bản; không copy máy móc config 6.x |

Đây là **quan hệ của các dòng khi ra mắt**, không phải lời cam kết mọi patch Boot đều mang một patch Security cố định. Quản trị thực tế phải **in cây dependency đã resolve**.

Một ứng dụng **Java 17+** là nền tảng phù hợp cho Spring Boot 3.x/Spring Security 6.x. Với Java 8 hoặc 11, không dùng được stack Boot 3/Security 6 theo cấu hình tiêu chuẩn. Việc project có mã nguồn Java 17 **chưa đủ** nếu build đang kéo Spring Security 6.3 hoặc các module Spring Security bị trộn phiên bản.

### 2.3. Kiểm tra phiên bản thực sự trong dự án

Với project Gradle Spring Boot:

~~~bash
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-core \
  --configuration runtimeClasspath

./gradlew --version
~~~

Trên Windows PowerShell/CMD, dùng `gradlew.bat` thay cho `./gradlew`. Với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.security
mvn --version
~~~

Cần kiểm tra **version đã resolve**, không chỉ `build.gradle`/`pom.xml`: dependency overrides, platform hoặc Spring Boot plugin có thể ảnh hưởng tới kết quả. Cây dependency phải nhất quán; không chọn `spring-security-web:6.5` trong khi `spring-security-config:6.3` rồi mong DSL hoạt động.

**Dấu hiệu đủ điều kiện:** project compile được lệnh `http.oneTimeTokenLogin(...)` và các lớp `org.springframework.security.authentication.ott.*`; dependency tree chỉ ra Spring Security **>=6.4** và phiên bản patch an toàn cho storage đã chọn. Nếu IDE báo `Cannot resolve method 'oneTimeTokenLogin'`, kiểm tra **Spring Security config module và JDK** trước khi tự viết filter thủ công.

### 2.4. Điều kiện bản vá bảo mật khi dùng JDBC OTT

Một cảnh báo chính thức ngày **21/04/2026**, **CVE-2026-22751**, mô tả race condition **TOCTOU** ở `JdbcOneTimeTokenService`: nhiều request đồng thời sử dụng cùng token có thể cùng hoàn tất đăng nhập, vi phạm kỳ vọng chỉ dùng một lần.

| Dòng Spring Security | Các bản ảnh hưởng theo advisory | Bản được công bố đã sửa |
| --- | --- | --- |
| 6.4.x | 6.4.0 – 6.4.15 | **6.4.16** (*Enterprise Support Only*) |
| 6.5.x | 6.5.0 – 6.5.9 | **6.5.10** |
| 7.0.x | 7.0.0 – 7.0.4 | **7.0.5** |

Advisory nói rõ **`InMemoryOneTimeTokenService` mặc định không bị ảnh hưởng bởi lỗ hổng này**, trong khi các ứng dụng **tự cấu hình `JdbcOneTimeTokenService`** ở phiên bản lỗi có rủi ro. Không suy ra rằng chỉ đổi sang bộ nhớ tạm là đã đủ cho production nhiều node; đó là một quyết định kiến trúc khác.

**Khuyến nghị cho hệ thống mới:** ưu tiên nhánh được bảo trì và patch bảo mật hiện hành, tối thiểu đảm bảo không dùng bản JDBC OTT trong danh sách ảnh hưởng. Không dựa vào nhãn `Spring Boot 3.5` để mặc định rằng Spring Security đã lên `6.5.10+`; phải kiểm dependency lock/BOM đã resolve. Không cần và không nên tự viết workaround xóa token thiếu atomicity khi bản vá chính thức có sẵn.

## 3. Phạm vi hỗ trợ: Servlet và Reactive khác API

| Phân lớp | **Servlet / Spring MVC** | **Reactive / Spring WebFlux** |
| --- | --- | --- |
| Cấu hình bảo mật | `HttpSecurity` | `ServerHttpSecurity` |
| Bean filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| DSL | `http.oneTimeTokenLogin(...)` | `http.oneTimeTokenLogin(...)` trên `ServerHttpSecurity` |
| Service sinh/tiêu thụ token | `OneTimeTokenService` | `ReactiveOneTimeTokenService` |
| Mặc định in-memory | `InMemoryOneTimeTokenService` | `InMemoryReactiveOneTimeTokenService` |
| Handler chuyển token | `OneTimeTokenGenerationSuccessHandler` | `ServerOneTimeTokenGenerationSuccessHandler` |
| Đối tượng request handler | `HttpServletRequest`, `HttpServletResponse` | `ServerWebExchange` và Reactor `Mono<Void>` |
| Bộ lọc sinh token | `GenerateOneTimeTokenFilter` | `GenerateOneTimeTokenWebFilter` |
| Bộ lọc nhận token | `OneTimeTokenAuthenticationFilter` | Bộ lọc OTT tương ứng trong WebFlux |
| Hình thức đăng nhập | Web/browser session + endpoint OTT của Servlet Security | WebFlux login/session + bộ lọc OTT reactive |

Cả hai stack có tài liệu One-Time Token Login từ nhánh 6.4, nhưng **không thể mang implementation Servlet handler sang WebFlux** vì signature khác. Đặc biệt, `OneTimeTokenService#generate` trả `OneTimeToken` đồng bộ, còn `ReactiveOneTimeTokenService#generate` trả `Mono<OneTimeToken>`. Chọn starter web hoặc webflux khớp môi trường thực, không trộn hai filter chain.

**Không được hiểu “Spring Security hỗ trợ OTT” là framework sẽ tự gửi email/SMS hoặc tích hợp mọi IdP.** Đây là một **cơ chế xác thực đăng nhập trong ứng dụng**, không phải một giao thức liên thông OAuth2/OIDC hay WebAuthn được bật miễn phí.

## 4. Cấu phần framework cung cấp và phần cần tự triển khai

### 4.1. Những gì đã có sẵn khi bật DSL

Spring Security Servlet cung cấp:

1. **Filter yêu cầu tạo token**: mặc định xử lý `POST /ott/generate`.
2. **One-time token object/service**: tạo token gắn với username, expiration; `OneTimeTokenService#generate(...)` và `#consume(...)`.
3. **Filter tiếp nhận token**: mặc định xử lý yêu cầu đăng nhập tới `POST /login/ott`. Không phải GET magic link tự đăng nhập; trang submit có thể điền token để người dùng gửi tiếp.
4. **Authentication provider**: dùng token được tiêu thụ và nạp tài khoản tương ứng thông qua `UserDetailsService`.
5. **Trang login/submit mặc định** tùy DSL và cấu hình giao diện; có thể kết hợp với `formLogin()` hoặc thay bằng UI của ứng dụng.
6. **SecurityContext/session thông thường** sau khi xác thực thành công; user không cần giữ OTT để gửi mỗi API request như OAuth2 access token.

**Mục đích token:** tạo chứng minh quyền kiểm soát một lần để khởi tạo authentication. Sau khi tiêu thụ token, những request tiếp theo dùng cơ chế lưu xác thực/session của ứng dụng theo cấu hình, **không dùng lại OTT**.

### 4.2. Những phần không được tự động cung cấp

| Hạng mục | Vì sao cần tự triển khai |
| --- | --- |
| **Chuyển token qua email/SMS** | Framework không biết tài khoản nào có mailbox/số điện thoại nào, cũng không biết hạ tầng gửi |
| **Xác minh người nhận** | Username/email do người gửi request khai báo không tự chứng minh thuộc về họ; phải truy vấn địa chỉ đã xác minh trong nguồn người dùng |
| **Template mail và magic link** | Phải xây base URL tin cậy, nội dung và UX |
| **Rate limiting / chống lạm dụng** | Ngăn gửi email hàng loạt, quét tài khoản và spam |
| **Chống user enumeration** | Trả phản hồi đồng nhất dù định danh không tồn tại |
| **Lưu trữ đa node bền vững** | Mặc định in-memory không dùng chung giữa instance, mất khi restart |
| **Chính sách tài khoản** | Trạng thái bị khóa, vô hiệu hóa, xác minh email/tenant, giới hạn quyền |
| **Giám sát và audit** | Theo dõi số yêu cầu/tiêu thụ thất bại, nhưng không log token |
| **MFA, chống phishing mạnh, device binding** | OTT đơn lẻ không tự thêm những thuộc tính đó |

Quan trọng: **Token delivery handler** thường là phần tích hợp bắt buộc. Interface Servlet `OneTimeTokenGenerationSuccessHandler` có phương thức:

~~~java
void handle(
    HttpServletRequest request,
    HttpServletResponse response,
    OneTimeToken oneTimeToken
) throws IOException, ServletException;
~~~

Đây là **chữ ký phương thức trong interface**, không phải một class Java độc lập. `OneTimeToken` có `getTokenValue()`, `getUsername()`, `getExpiresAt()`. Khi gửi email, chỉ dùng **địa chỉ email đã được ứng dụng xác minh trước** tương ứng với `getUsername()`, không gửi theo một địa chỉ tùy ý do caller đưa vào mà chưa được xác nhận.

## 5. Luồng ứng dụng OTT theo đúng trách nhiệm

~~~text
Người dùng nhập định danh tại trang đăng nhập
          │ gửi POST /ott/generate + CSRF token
          ▼
GenerateOneTimeTokenFilter (Servlet)
          │
          ▼
OneTimeTokenService.generate(GenerateOneTimeTokenRequest)
          │ tạo token: username + random token + expiresAt
          ▼
OneTimeTokenGenerationSuccessHandler (của ứng dụng)
          │ tra cứu mailbox đáng tin; gửi Magic Link qua kênh ngoài
          ▼
Người dùng mở link GET /login/ott?token=...
          │ trang submit điền sẵn token; GET chưa phải xác thực
          ▼
POST /login/ott (token + CSRF token)
          │
          ▼
OneTimeTokenAuthenticationFilter
          │
          ▼
OneTimeTokenAuthenticationProvider
          │ gọi OneTimeTokenService.consume(...)
          ├── token không tồn tại / đã dùng / hết hạn → từ chối
          │
          └── token hợp lệ + user hợp lệ
                   │ nạp UserDetails/authorities
                   ▼
           Authenticated SecurityContext
                   │
                   ▼
           Redirect vào trang bảo vệ/phiên đăng nhập
~~~

Ở đây, đường dẫn mặc định và cơ chế xử lý GET/POST là chi tiết của **Servlet OTT Login**; không dùng như API Bearer `Authorization: Bearer ...`. Khi thay URL bằng DSL, cần điều chỉnh form, CSRF, magic link và đường redirect theo cùng một hợp đồng.

### Tại sao không gửi token qua response trả về cho người yêu cầu?

Nếu người dùng chỉ nhập `victim@example.test` và server trả token ngay trong HTTP response, attacker cũng có thể nhập email này rồi lấy token để đăng nhập dưới tài khoản nạn nhân. Vì vậy token phải đến **kênh ngoài** mà chủ tài khoản kiểm soát (hoặc kênh xác thực được thiết kế tương đương). Trong production, không log token và không hiện token trên trang xác nhận.

### Vì sao CSRF vẫn quan trọng?

Các endpoint tạo và tiêu thụ OTT sử dụng HTTP POST; khi CSRF đang bật, request POST từ browser thường phải mang token CSRF hợp lệ. Form mặc định Spring Security hỗ trợ CSRF theo cấu hình; nếu tự viết frontend, phải gửi CSRF token đúng cách. **Không tắt CSRF cho toàn bộ ứng dụng chỉ vì POST /ott/generate bị 403 khi test bằng curl.** Hãy phân biệt 403 do thiếu CSRF, lỗi rate limiting và lỗi token hết hạn.

## 6. Ví dụ tối thiểu Java 17+ với Spring Boot 3.5 / Spring Security 6.5 đã vá

Ví dụ Servlet bên dưới minh họa đầy đủ cấu hình **OTT-only**, sinh magic link và gửi vào mailbox thử nghiệm. Nó dùng **SMTP sink ở localhost** để người học quan sát email trong môi trường lab; không hoạt động end-to-end nếu chưa cấu hình mail server hoặc dùng email/recipient không tồn tại.

Điều kiện:

- JDK **17+**.
- Spring Boot **3.5.x** với bộ Spring Security **6.5.10+** đã resolve khi dùng JDBC OTT; ví dụ dùng **in-memory**.
- Project có Spring Boot plugin/BOM và Gradle wrapper.
- Một SMTP test server nhận thư ở `127.0.0.1:1025`, mailbox lab `student@example.test`.
- Browser truy cập qua `http://localhost:8080` chỉ trong môi trường local; production cần HTTPS và DNS public phù hợp.

### 6.1. Dependencies

Đoạn trong `build.gradle` (Groovy DSL, đặt trong project Spring Boot hiện có):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-mail` cho `JavaMailSender`; nếu chỉ dựng filter/handler mà chưa cấu hình SMTP, app có thể lỗi bean hoặc lỗi khi gửi mail. Không yêu cầu starter OAuth2 Resource Server cho bài OTT này, vì OTT **không phải** JWT Bearer authentication.

### 6.2. Cấu hình ứng dụng

`src/main/resources/application.properties`:

~~~properties
server.port=8080
spring.mail.host=127.0.0.1
spring.mail.port=1025
app.ott.public-base-url=http://localhost:8080
~~~

Các giá trị chỉ dành cho local. Production phải lấy `public-base-url` từ cấu hình tin cậy, dùng HTTPS và hostname chuẩn, **không xây link đăng nhập từ Host/X-Forwarded-Host header do client kiểm soát**.

### 6.3. Application và security configuration

Tệp `src/main/java/example/ott/OttDemoApplication.java`:

~~~java
package example.ott;

import java.util.Map;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@SpringBootApplication
public class OttDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OttDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler mailHandler)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/ott/sent").permitAll()
                .anyRequest().authenticated());

        http.oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(mailHandler));

        // Không bật formLogin trong ví dụ OTT-only.
        // Giữ CSRF mặc định cho các biểu mẫu POST.
        return http.build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        // Chỉ một user lab. Password random nhằm tránh thông tin
        // đăng nhập cố định nếu sau này ai đó bật formLogin.
        String unknownPassword = UUID.randomUUID().toString();
        UserDetails student = User.withUsername("student")
                .password("{bcrypt}" + new BCryptPasswordEncoder()
                        .encode(unknownPassword))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler mailHandler(
            JavaMailSender sender,
            @Value("${app.ott.public-base-url}") String publicBaseUrl) {

        // Demo: ánh xạ tài khoản -> mailbox đã xác minh.
        // Production: lấy mapping từ cơ sở dữ liệu người dùng.
        Map<String, String> registeredEmails =
                Map.of("student", "student@example.test");

        return (request, response, token) -> {
            String recipient = registeredEmails.get(token.getUsername());

            if (recipient != null) {
                String magicLink = UriComponentsBuilder
                        .fromUriString(publicBaseUrl)
                        .path("/login/ott")
                        .queryParam("token", token.getTokenValue())
                        .build()
                        .encode()
                        .toUriString();

                SimpleMailMessage email = new SimpleMailMessage();
                email.setFrom("no-reply@example.test");
                email.setTo(recipient);
                email.setSubject("Your one-time login link");
                email.setText("Open this single-use link before expiry: "
                        + magicLink);
                sender.send(email);
            }

            // Không tiết lộ username có tồn tại hay không.
            response.sendRedirect(request.getContextPath() + "/ott/sent");
        };
    }
}

@RestController
class DemoPages {
    @GetMapping("/ott/sent")
    String sent() {
        return "If the account exists, check your inbox.";
    }

    @GetMapping("/private")
    String privatePage() {
        return "Signed in.";
    }
}
~~~

**Tại sao code như vậy?**

1. `HttpSecurity.oneTimeTokenLogin(...)` là DSL tích hợp từ 6.4, thay vì tự viết authentication filter/password reset logic.
2. Bean `OneTimeTokenGenerationSuccessHandler` có đúng method signature Servlet; handler gửi token qua SMTP thay vì trả về body HTTP. Nó không dùng tên host từ request, tránh tạo magic link dẫn đến host do attacker cung cấp.
3. `UserDetailsService` cung cấp user/roles sau khi token hợp lệ. Tài khoản lab `student` gắn email test, còn user không có mapping sẽ không được gửi token. Trong production cần cơ sở dữ liệu user thực, chính sách khóa và kiểm tra email verified.
4. Không bật `formLogin` nhằm giữ ví dụ là **OTT-only**. Nếu muốn có **cả password + OTT** thì có thể thêm `formLogin(Customizer.withDefaults())` sau khi bảo đảm tài khoản có credential/password policy riêng và kiểm thử cả hai luồng.
5. `anyRequest().authenticated()` bảo vệ trang `/private`; `/ott/sent` được cho phép để hiển thị thông báo chung.
6. Không tắt CSRF; browser cần sử dụng form/CSRF đúng cách. Không cần biến magic link thành GET endpoint tự xác thực; GET `/login/ott?token=...` dẫn tới submit page, còn đăng nhập xử lý qua POST.
7. Dữ liệu token mặc định được giữ in-memory nên app demo chỉ phù hợp **một instance** và sẽ mất token chưa dùng khi khởi động lại.

Tệp có một class public là `OttDemoApplication`, cùng package với `DemoPages`. Các class còn lại đến từ Spring Boot/Framework/Security 6.5 và starter mail. Không có controller tự nhận POST `/ott/generate` hay `/login/ott` vì các filter do DSL tạo xử lý chúng.

### 6.4. Chạy và thử

Trong project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Các bước kiểm thử browser khi SMTP sink đang chạy:

1. Mở `http://localhost:8080/login` để dùng trang login mặc định hoặc trang request OTT của cấu hình Security hiện hành.
2. Điền username `student` ở mẫu **One-Time Token** rồi gửi form; Spring Security sinh token và handler gửi email đến hộp thư thử nghiệm.
3. Mở magic link nhận được từ test SMTP. Trang `/login/ott` hiển thị token/form submit.
4. Gửi form; sau khi token hợp lệ được tiêu thụ, truy cập `/private` sẽ thấy:

~~~text
Signed in.
~~~

5. Đăng xuất hoặc dùng phiên browser khác rồi thử **lại token cũ**; kết quả phải bị từ chối. Thử token hết hạn cũng phải bị từ chối. Nếu đã đăng nhập trong session hiện tại, truy cập `/private` vẫn có thể thành công vì **session vẫn hợp lệ**, không có nghĩa token đã dùng lại được.

**Không dùng lệnh POST curl thiếu CSRF token để kết luận OTT không hoạt động.** Trong cấu hình mặc định, request không có CSRF hợp lệ có thể bị 403 trước khi đến logic sinh/tiêu thụ OTT. Không xuất token thật ra console, logs hoặc ảnh chụp màn hình công khai.

### 6.5. Một bài kiểm thử đơn vị xác minh single-use và expiry

Với dependency `spring-boot-starter-test`/JUnit Jupiter, có thể kiểm thử **dịch vụ in-memory** độc lập với email, UI và HTTP. Tệp `src/test/java/example/ott/OneTimeTokenServiceTest.java`:

~~~java
package example.ott;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.ott.GenerateOneTimeTokenRequest;
import org.springframework.security.authentication.ott.InMemoryOneTimeTokenService;
import org.springframework.security.authentication.ott.OneTimeToken;
import org.springframework.security.authentication.ott.OneTimeTokenAuthenticationToken;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class OneTimeTokenServiceTest {

    @Test
    void tokenCanBeConsumedOnlyOnce() {
        InMemoryOneTimeTokenService service =
                new InMemoryOneTimeTokenService();

        OneTimeToken token = service.generate(
                new GenerateOneTimeTokenRequest(
                        "student", Duration.ofMinutes(5)));

        assertNotNull(service.consume(
                new OneTimeTokenAuthenticationToken(
                        token.getTokenValue())));

        assertNull(service.consume(
                new OneTimeTokenAuthenticationToken(
                        token.getTokenValue())));
    }

    @Test
    void expiredTokenCannotBeConsumed() {
        InMemoryOneTimeTokenService service =
                new InMemoryOneTimeTokenService();

        Clock start = Clock.fixed(
                Instant.parse("2026-11-06T00:00:00Z"),
                ZoneOffset.UTC);
        service.setClock(start);

        OneTimeToken token = service.generate(
                new GenerateOneTimeTokenRequest(
                        "student", Duration.ofMinutes(1)));

        service.setClock(
                Clock.offset(start, Duration.ofMinutes(2)));

        assertNull(service.consume(
                new OneTimeTokenAuthenticationToken(
                        token.getTokenValue())));
    }
}
~~~

Chạy test:

~~~bash
./gradlew test --tests example.ott.OneTimeTokenServiceTest
~~~

Test dùng `setClock` nên không phụ thuộc thời gian thực của CI. Nếu các giả định đúng, hai test pass và Gradle thông báo build thành công; output chi tiết thay đổi theo phiên bản plugin. Đây **chỉ là kiểm thử `InMemoryOneTimeTokenService`**, **không** chứng minh `JdbcOneTimeTokenService` bảo vệ được race condition khi 2+ request đồng thời, cũng không kiểm tra việc SMTP gửi mail hoặc CSRF của browser. Với JDBC phải thêm integration test nhiều thread/nhiều instance và dùng bản framework đã vá.

## 7. Phạm vi lưu trữ token và môi trường triển khai

### 7.1. Dùng mặc định InMemoryOneTimeTokenService khi nào?

**Phù hợp:**

- Workshop và local demo.
- Ứng dụng chỉ có một instance và chấp nhận token chưa dùng bị mất khi restart.
- Test unit xác minh cơ chế single-use/expiry.

**Giới hạn:**

- Lưu trong RAM của instance hiện tại, không chia sẻ token giữa các node; request sinh token tới node A nhưng request xác thực tới node B có thể thất bại.
- Nếu ứng dụng restart, token chưa dùng có thể mất.
- Không cung cấp high availability/durability theo cách database.
- Vì token gắn với state của service, không đối xử với nó như một **JWT stateless** mà node nào cũng tự verify chữ ký.

Spring Security dùng `InMemoryOneTimeTokenService` mặc định cho Servlet khi không cấu hình `OneTimeTokenService` khác. Reactive cũng có `InMemoryReactiveOneTimeTokenService` nhưng không dùng chung Java interface/method đồng bộ.

### 7.2. JDBC và clustered deployment

`JdbcOneTimeTokenService` lưu token trong cơ sở dữ liệu qua `JdbcOperations` và bảng theo schema Spring Security. Điều này phù hợp hơn cho nhiều replica **nếu** mọi instance dùng chung kho dữ liệu và thao tác tiêu thụ là atomic theo bản đã vá.

Không chỉ thêm bean JDBC và cho rằng xong. Cần:

- Tạo schema theo tài liệu của **đúng phiên bản** Spring Security.
- Dùng phiên bản đã vá **CVE-2026-22751** nếu nằm trong các nhánh được nêu.
- Kiểm thử 2–N request **đồng thời** với cùng token: tối đa một request được xác thực; những request còn lại thất bại.
- Kiểm tra TTL, cleanup, transaction/isolation, đồng hồ giữa các node, database availability và xử lý retry.
- Bảo vệ dữ liệu token trong database, backup và log theo chính sách; token là **credential ngắn hạn**, không phải dữ liệu vô hại.

**Lỗi về concurrency không được phát hiện bởi test tuần tự** “consume lần 1 thành công, consume lần 2 thất bại”. Test đó chỉ chứng minh single-use khi request xảy ra lần lượt. Trong TOCTOU, hai request song song có thể cùng nhìn thấy token trước khi xóa. Vì thế cần test race có barrier/multiple workers và xác minh **chính xác một successful authentication**.

## 8. Tùy chỉnh thời hạn và API khác nhau giữa 6.4 và 6.5

Trong mặc định tài liệu Spring Security, một request OTT có **thời hạn khoảng 5 phút**. Đây là giá trị của cơ chế tạo token, không phải thời hạn session sau đăng nhập. Thời hạn thực tế cần kiểm qua `GenerateOneTimeTokenRequest#getExpiresIn()` và chính sách service đã chọn.

Từ 6.5, Spring Security bổ sung điểm mở rộng `GenerateOneTimeTokenRequestResolver` trong DSL, giúp ứng dụng tùy chỉnh request trước khi generate; lớp mặc định Servlet là `DefaultGenerateOneTimeTokenRequestResolver`.

Ví dụ *cấu hình bổ sung*, áp dụng **khi phiên bản có resolver API tương ứng**:

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.web.authentication.ott.DefaultGenerateOneTimeTokenRequestResolver;
import org.springframework.security.web.authentication.ott.GenerateOneTimeTokenRequestResolver;

// Đặt bên trong một @Configuration class.
@Bean
GenerateOneTimeTokenRequestResolver generateOneTimeTokenRequestResolver() {
    DefaultGenerateOneTimeTokenRequestResolver resolver =
            new DefaultGenerateOneTimeTokenRequestResolver();
    resolver.setExpiresIn(Duration.ofMinutes(10));
    return resolver;
}
~~~

Đây là đoạn **trích thành viên config**, không phải file Java độc lập với các import nằm bên ngoài class đã tồn tại. Chỉ dùng trên phiên bản có API đã xác minh; không áp dụng mù quáng cho 6.4. Nếu service/provider tùy chỉnh, phải kiểm thử thời hạn thực tế ở cả bước generate và consume.

Đổi TTL từ 5 lên 10 phút **tăng cửa sổ lạm dụng nếu token bị lộ**. Chọn TTL theo đường gửi email/SMS, độ trễ thực tế, khả năng người dùng thao tác và mức độ nhạy cảm. Đừng đổi expiration của OTP/JWT theo giả định OTT dùng cùng policy.

### API thay đổi, tên phương thức phải theo Javadoc

Một số tài liệu/trang phiên bản khác nhau có tên mẫu DSL khác nhau khi tùy chỉnh endpoint. Với Servlet `OneTimeTokenLoginConfigurer` nhánh 6.4/6.5, phương thức được Javadoc xác minh là:

~~~java
http.oneTimeTokenLogin(ott -> ott
        .tokenGeneratingUrl("/ott/request")
        .loginProcessingUrl("/login/ott")
        .tokenGenerationSuccessHandler(mailHandler));
~~~

Đây là **đoạn cấu hình bên trong phương thức `SecurityFilterChain` đã có biến `http` và `mailHandler`**, không phải class độc lập. Khi đổi URL mặc định, UI request và magic link phải khớp. Không tự sao chép tên phương thức từ ví dụ WebFlux ở nhánh khác và assume luôn compile.

### Servlet và WebFlux không dùng chung handler

**Servlet:**

~~~java
OneTimeTokenGenerationSuccessHandler handler =
        (request, response, oneTimeToken) -> {
            response.sendRedirect(request.getContextPath() + "/ott/sent");
        };
~~~

Ví dụ này minh họa method signature, **chưa cung cấp delivery** nên không được dùng đơn độc làm production handler.

**Reactive/WebFlux:** interface tương ứng `ServerOneTimeTokenGenerationSuccessHandler` nhận `ServerWebExchange` và `OneTimeToken`, trả về `Mono<Void>`. Service là `ReactiveOneTimeTokenService`. Nếu đang dùng Spring WebFlux, phải viết handler không chặn event loop, chẳng hạn tích hợp mail delivery qua reactive client/service phù hợp; không gọi send SMTP blocking trực tiếp trên event loop.

## 9. Giới hạn bảo mật và điều kiện vận hành production

### 9.1. Sinh token phải đi cùng ràng buộc danh tính

Nếu endpoint nhận username/email do người lạ nhập:

- Chỉ gửi đến **địa chỉ đã xác minh**, lấy từ dữ liệu nội bộ của user, không dùng `request.getParameter("email")` làm destination mà không kiểm tra.
- Không tiết lộ tài khoản tồn tại hay không thông qua response status, message, timing rõ rệt hoặc tên redirect.
- Có rate limiting theo IP/account/device, cooldown và chống email bombing.
- Có giới hạn số token còn hiệu lực, chính sách invalidate token cũ nếu phát hành lại, giới hạn request và số lần nhập sai.
- Kiểm tra trạng thái khóa/vô hiệu hóa/tenant/chính sách đăng nhập tại thời điểm **tiêu thụ** token, không chỉ lúc yêu cầu sinh.

Tài liệu các phiên bản gần đây nêu rằng `OneTimeTokenAuthenticationProvider` **không tự động coi mọi cờ account status như một điều kiện từ chối**, ví dụ locked/disabled/expired; có thể bổ sung `AccountStatusUserDetailsChecker` qua `setUserDetailsChecker(...)` ở các phiên bản hỗ trợ. Không nên dựa vào một giả định không được kiểm thử: hãy có test “disabled account + OTT hợp lệ → vẫn bị từ chối” trên phiên bản đang vận hành.

### 9.2. Giữ bí mật magic link

Magic link thường chứa token trong query string `/login/ott?token=...`. Điều này thuận tiện nhưng có rủi ro bị sao chép qua history, screenshots, analytics, reverse proxy logs, referrer hoặc browser extensions.

Biện pháp cần xem xét:

- HTTPS cho trang nhận token; không cho phép kênh HTTP production.
- Không nhúng third-party analytics/asset trên trang chứa token; cấu hình `Referrer-Policy: no-referrer` phù hợp.
- Không lưu token raw trong access logs, APM hoặc error reports; che query parameter `token`.
- Giới hạn TTL; tiêu thụ token qua POST, không tự đăng nhập trên GET.
- Có kế hoạch xử lý trình đọc email tự động quét magic link: chỉ GET để xem trang không nên làm mất token.
- Không đưa token vào email được forward sang người khác như một mã kiểm chứng vô hại.

### 9.3. Không gán OTT thành MFA mà chưa thiết kế

Một đăng nhập OTT duy nhất qua email là một yếu tố phụ thuộc **quyền kiểm soát email**. Muốn MFA, cần thêm chính sách xác thực độc lập và ràng buộc các bước với cùng người dùng/session theo mô hình đe dọa cụ thể. Việc gọi endpoint `/ott/generate` sau khi nhập password **không tự động tạo ra MFA an toàn** nếu không có cơ chế xác nhận bước thứ nhất, chống session fixation và kiểm soát trạng thái xác thực từng bước.

### 9.4. Login session và logout

OTT được dùng để **khởi tạo Authentication**, không phải access token dùng mỗi request. Một token đã consumed **không được dùng lại**, nhưng session được tạo sau lần đăng nhập trước đó có thể tiếp tục tồn tại cho tới logout hoặc hết hạn. Do đó:

- Tái sử dụng OTT cũ phải thất bại ngay cả khi một browser còn session.
- Logout nên xóa session phù hợp và token browser/session, nhưng không mặc nhiên ngăn email token mới được sinh về sau.
- Không suy ra hết hạn OTT = hết hạn session; là hai thời hạn khác nhau.
- Nếu tài khoản bị khóa sau khi đăng nhập, cần có chính sách thu hồi session và quyền ứng dụng riêng.

## 10. Ma trận kiểm thử điều kiện phiên bản và phạm vi hỗ trợ

| ID | Kiểm tra | Kỳ vọng |
| --- | --- | --- |
| V01 | Project Spring Security 6.3 gọi `oneTimeTokenLogin` | Không có DSL tích hợp; xác minh dependency thay vì tự đoán |
| V02 | Boot 3.4 + Spring Security 6.4.x đã resolve | Có DSL Servlet/Reactive và OTT core APIs |
| V03 | Boot 3.5 + Spring Security 6.5.x đã resolve | Có OTT DSL, tùy chỉnh resolver theo API tương ứng |
| V04 | Module Security core/config/web khác version | Build không đáng tin, cần đồng bộ phiên bản |
| V05 | Reactive app dùng Servlet `SecurityFilterChain` và handler | Sai stack; phải dùng `SecurityWebFilterChain` và reactive API |
| V06 | OTT-only Servlet app không tích hợp mail handler thực | Không có đường delivery để người dùng hoàn thành đăng nhập |
| V07 | GET magic link sau khi token tạo | Hiện trang submit; không tự consumed chỉ vì mở GET |
| V08 | POST submit token lần đầu | Thành công nếu token còn hạn, đúng user và policy |
| V09 | Submit lại cùng token sau khi đã consume | Thất bại |
| V10 | Submit token sau `expiresAt` | Thất bại |
| V11 | Hai request song song cùng token, với store JDBC | **Tối đa một** authentication thành công; cần bản đã vá CVE |
| V12 | Chạy nhiều instance với in-memory store không chia sẻ | Xảy ra thiếu token ở node khác; không đáp ứng HA mặc định |
| V13 | Người không tồn tại gửi yêu cầu token | Response không làm lộ user tồn tại; không gửi token cho địa chỉ tùy ý |
| V14 | User bị disabled/locked nhưng có token hợp lệ | Bị từ chối theo account policy được cấu hình và kiểm thử |
| V15 | Form POST không có CSRF token, CSRF bật | Bị chặn theo CSRF, không tự disable toàn hệ thống |
| V16 | Token bị lộ qua logs/referrer/screenshot | Quy trình phát hiện/giảm thiểu; tokens không xuất hiện trong telemetry |
| V17 | Chưa cài OTP authenticator nhưng muốn TOTP | OTT không tự cung cấp TOTP/HOTP |
| V18 | Gửi OTT vào Authorization Bearer mỗi API request | Không phải mô hình OTT Login mặc định |
| V19 | SMTP bị lỗi, mailbox không truy cập được | Không tạo phiên đăng nhập chỉ vì token đã sinh; xử lý lỗi gửi và retry an toàn |
| V20 | Spring Security JDBC 6.5.9, test cạnh tranh | Nằm trong danh sách phiên bản bị ảnh hưởng; phải upgrade trước production |

### Đọc kết quả kiểm thử cho đúng

- Một test thành công của `InMemoryOneTimeTokenService` không chứng minh tính đúng đắn của transaction trong DB.
- Một request tới `/ott/generate` trả redirect không chứng minh email đã được chuyển cho đúng user.
- Một GET magic link được trả HTTP 200 không chứng minh Authentication đã thành công; cần POST submit và kiểm tra SecurityContext/session.
- Một user đã đăng nhập xem được `/private` khi thử token cũ không chứng minh token tái sử dụng được. Hãy thử token trong phiên **chưa xác thực** hoặc kiểm tra trực tiếp service.
- Dùng `curl` thiếu CSRF có thể bị 403 dù code OTT đúng; bài test browser phải lấy CSRF token đúng cách.

## 11. Lỗi thường gặp khi nâng cấp OTT

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `Cannot resolve method oneTimeTokenLogin` | Spring Security trước 6.4 hoặc thiếu module config | Kiểm cây dependency, nâng đúng Boot/Security |
| IDE có class nhưng build runtime lỗi | Module Spring Security lệch version | Để BOM quản lý đồng bộ các artifact |
| Không có mail nào được gửi | Chưa có handler, SMTP config sai hoặc user email chưa map | Kiểm tra `OneTimeTokenGenerationSuccessHandler` và SMTP sink |
| OTP authenticator không tạo được mã tương thích | Nhầm OTT với TOTP/HOTP | Dùng giải pháp OTP đúng chuẩn |
| Link đúng nhưng token bị từ chối | Hết hạn, đã dùng, node khác, mất state khi restart, URL sai | Kiểm tra expiresAt, storage và endpoint |
| Gọi endpoint từ SPA bị 403 | CSRF token thiếu hoặc URL/form sai | Tích hợp CSRF chuẩn, không tắt bừa |
| Một token JDBC đăng nhập được hai lần khi race | Dùng phiên bản ảnh hưởng CVE-2026-22751 | Nâng bản đã vá, kiểm concurrency |
| Test local pass nhưng cluster fail | In-memory store theo từng instance | Chọn storage chung và kiểm atomic consume |
| Link dẫn đến domain lạ | Xây magic link từ Host header tùy ý | Dùng public base URL cố định theo môi trường |
| Tài khoản disabled vẫn có session | Chưa kiểm tra trạng thái account hoặc session cũ chưa thu hồi | Thêm checker/policy và integration test |
| Token xuất hiện ở access log | Query param bị ghi nguyên văn | Che token, điều chỉnh log và Referrer-Policy |
| Form login vẫn hoạt động ngoài mong đợi | Dùng chung `formLogin` và OTT | Quyết định rõ passwordless-only hay song song với password |

## 12. Cách ra quyết định triển khai

**Dùng OTT tích hợp khi:** ứng dụng web cần passwordless login qua mailbox/số điện thoại đã được xác minh; chạy Spring Security **>=6.4**; có tầng gửi token an toàn, user storage, CSRF và phiên đăng nhập phù hợp.

**Chưa nên triển khai OTT ngay khi:** vẫn dùng Java 8/11 + Boot 2.x/Security 5.x, không thể nâng cấp; chưa có kênh giao token đáng tin; yêu cầu là TOTP/MFA nhưng chưa thiết kế tích hợp; hay hệ nhiều node cần storage dùng một lần an toàn mà chưa nâng bản JDBC đã vá.

**Chọn Servlet hay Reactive:** căn cứ architecture web đang chạy. MVC dùng `HttpSecurity` + `OneTimeTokenService`; WebFlux dùng `ServerHttpSecurity` + `ReactiveOneTimeTokenService`. Hành vi người dùng tương tự nhưng code và chính sách threading khác nhau.

**Chọn store:** in-memory để học/đơn node; JDBC/đồng bộ hóa ở cluster phải dùng bản đã vá và test concurrent consume. Đừng dùng database chỉ vì “production” mà bỏ qua đúng phiên bản bảo mật.

### Checklist cuối

- [ ] Đã xác minh Java >=17, Spring Security >=6.4, Boot/Security modules cùng dòng tương thích.
- [ ] Nếu JDBC OTT: đã kiểm tra patch khắc phục CVE-2026-22751.
- [ ] Chọn đúng Servlet hoặc Reactive stack, không trộn DSL/handler.
- [ ] Biết OTT khác TOTP/HOTP, JWT Bearer, password-reset và MFA.
- [ ] Có `OneTimeTokenGenerationSuccessHandler` / `ServerOneTimeTokenGenerationSuccessHandler` gửi token thật.
- [ ] Mailbox/phone của user đã xác minh; anti-enumeration và rate limit được thực hiện.
- [ ] Có HTTPS, CSRF, chống rò token trong URL/log, TTL hợp lý.
- [ ] Store phù hợp số node, kiểm được single-use và expiry cả tuần tự lẫn đồng thời.
- [ ] Có kiểm tra trạng thái user, thu hồi session khi cần và test quyền sau đăng nhập.
- [ ] Đã thử lỗi SMTP, token expired/used, restart node, race và user không tồn tại.

## 13. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/onetimetoken.html)
- [Spring Security 6.5 — Reactive One-Time Token Login](https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/onetimetoken.html)
- [Spring Security 6.4 — OneTimeTokenLoginConfigurer API](https://docs.spring.io/spring-security/site/docs/6.4.x/api/org/springframework/security/config/annotation/web/configurers/ott/OneTimeTokenLoginConfigurer.html)
- [Spring Security — OneTimeTokenService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/ott/OneTimeTokenService.html)
- [Spring Security 6.5 — What's New](https://docs.spring.io/spring-security/reference/6.5/whats-new.html)
- [Spring Boot 3.4 Release Notes: Spring Security 6.4](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
- [Spring Boot 3.5 Release Notes: Spring Security 6.5](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.5-Release-Notes)
- [CVE-2026-22751 — Spring Security JdbcOneTimeTokenService one-time-token reuse](https://spring.io/security/cve-2026-22751)
