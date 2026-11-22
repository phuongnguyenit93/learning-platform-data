# FactorGrantedAuthority và @EnableMultiFactorAuthentication ở phiên bản Spring Security hỗ trợ

## 1. Mục tiêu và lưu ý quan trọng về phiên bản

**Multi-Factor Authentication (MFA)** yêu cầu người dùng chứng minh danh tính bằng nhiều yếu tố xác thực. Trong **Spring Security 7.0 trở lên (Servlet)**, framework đưa ra hai API đặc biệt hữu ích:

- `FactorGrantedAuthority`: một loại `GrantedAuthority` biểu thị **phương thức/yếu tố đã được dùng để xác thực**, kèm thời điểm yếu tố đó được ghi nhận.
- `@EnableMultiFactorAuthentication`: annotation hỗ trợ **thêm yêu cầu các yếu tố xác thực vào các authorization rules** thay vì phải lặp các biểu thức kiểm tra ở mọi endpoint.

**Ranh giới phiên bản bắt buộc phải nhớ:**

| Dòng phiên bản | Có thể sử dụng trực tiếp hai API của bài? | Cần làm gì? |
| --- | --- | --- |
| Spring Security 6.4/6.5 (Spring Boot 3.x) | **Không**: hai API này được giới thiệu từ Spring Security **7.0** | Không copy import/annotation 7.x; dùng giải pháp MFA tương thích 6.x hoặc nâng cấp theo migration guide |
| Spring Security 7.0 (thường dùng với Spring Boot 4.0) | **Có**: `FactorGrantedAuthority` và `@EnableMultiFactorAuthentication` | Cấu hình chính sách yếu tố và các phương thức login tương ứng |
| Spring Security 7.1+ | **Có**, và có thêm những cơ chế điều kiện như `MultiFactorCondition.WEBAUTHN_REGISTERED` trong tài liệu hiện hành | Kiểm tra Javadoc của phiên bản cụ thể trước khi dùng API bổ sung |
| Spring WebFlux/reactive | Không tự suy ra hỗ trợ giống Servlet | Kiểm tra tài liệu WebFlux đúng phiên bản; annotation MFA 7.0 công bố không áp dụng cho reactive |

Cả `FactorGrantedAuthority` và `@EnableMultiFactorAuthentication` đều có Javadoc ghi **Since: 7.0**. Trong bài này, các ví dụ cấu hình chính dùng **Spring Boot 4.0.x / Spring Security 7.0.x / Java 17+ / Servlet**. Phần có đánh dấu **7.1+** chỉ dùng khi dự án đã nâng đến nhánh hỗ trợ.

Sau khi học, bạn cần phân biệt được: **yếu tố đã được chứng minh**, **authority thể hiện yếu tố**, **rule đòi yếu tố** và **mechanism thật sự lấy chứng cứ xác thực**. Một annotation không tự biến một ứng dụng chỉ có mật khẩu thành MFA.

## 2. Factor là gì? Vì sao đăng nhập một lần chưa đủ?

Các loại bằng chứng người dùng thường gặp:

| Nhóm | Ví dụ | Điều cần đánh giá |
| --- | --- | --- |
| Something you know | Mật khẩu, PIN bí mật chỉ người dùng biết | Chống phishing, đoán mật khẩu, tái sử dụng |
| Something you have | Security key, thiết bị giữ passkey, kênh nhận OTT | Thiết bị hoặc kênh có thực sự độc lập với mật khẩu không? |
| Something you are | Vân tay/khuôn mặt kiểm tra cục bộ ở authenticator | RP có nhận bằng chứng user verification phù hợp không? |

Hai lần nhập **cùng một mật khẩu** không tạo thành hai factor độc lập. Hai mã gửi cùng một mailbox không tự bảo đảm đạt mức MFA mạnh. Một magic link qua email có thể dùng như yếu tố bổ sung nếu tổ chức chấp nhận mức bảo đảm của kênh email, nhưng thường **không phishing-resistant** bằng WebAuthn/passkey được thiết kế và xác minh đúng.

Spring Security tách **authentication mechanisms** (cách người dùng chứng minh) khỏi **authorization policy** (cần chứng minh những yếu tố nào để thực hiện hành động).

Ví dụ nghiệp vụ:

- Đọc bài viết thông thường: cần tài khoản đã xác thực.
- Xem thông tin cá nhân: cần bằng chứng mật khẩu và một-time token (OTT).
- Chuyển tiền hoặc đổi phương thức khôi phục: cần thêm điều kiện “yếu tố gần đây”, quyền nghiệp vụ và step-up authentication.
- Quản trị hệ thống: cần `ROLE_ADMIN` **và** các factor theo policy, chứ role không thay thế factor.

## 3. FactorGrantedAuthority là gì?

Trong Spring Security 7, class:

~~~java
org.springframework.security.core.authority.FactorGrantedAuthority
~~~

implements `GrantedAuthority`. Khác với `SimpleGrantedAuthority("ROLE_ADMIN")` là quyền nghiệp vụ, `FactorGrantedAuthority` biểu thị một **phương thức xác thực đã được framework ghi nhận**.

Các constants đáng nhớ:

| Constant | Giá trị authority | Bằng chứng tương ứng |
| --- | --- | --- |
| `FactorGrantedAuthority.PASSWORD_AUTHORITY` | `FACTOR_PASSWORD` | Đăng nhập bằng mật khẩu |
| `FactorGrantedAuthority.OTT_AUTHORITY` | `FACTOR_OTT` | One-Time Token login |
| `FactorGrantedAuthority.WEBAUTHN_AUTHORITY` | `FACTOR_WEBAUTHN` | WebAuthn/passkey login |
| `FactorGrantedAuthority.X509_AUTHORITY` | `FACTOR_X509` | X.509 client-certificate authentication |
| `FactorGrantedAuthority.BEARER_AUTHORITY` | `FACTOR_BEARER` | Bearer-token authentication |
| `FactorGrantedAuthority.AUTHORIZATION_CODE_AUTHORITY` | `FACTOR_AUTHORIZATION_CODE` | OAuth2 Authorization Code login |
| `FactorGrantedAuthority.SAML_RESPONSE_AUTHORITY` | `FACTOR_SAML_RESPONSE` | SAML authentication |
| `FactorGrantedAuthority.CAS_AUTHORITY` | `FACTOR_CAS` | CAS authentication |

**Chú ý:** các tên `FACTOR_*` biểu thị **cơ chế** đã được sử dụng, không có nghĩa hai cơ chế bất kỳ đều là hai yếu tố độc lập theo một chính sách MFA cụ thể. Ví dụ `FACTOR_BEARER` chỉ báo đã dùng bearer authentication, không chứng minh người cầm token có thêm một factor riêng.

### 3.1. issuedAt: yếu tố được xác thực lúc nào?

`FactorGrantedAuthority` còn có:

~~~java
Instant issuedAt = factorGrantedAuthority.getIssuedAt();
String authority = factorGrantedAuthority.getAuthority();
~~~

Ý nghĩa:

- `getAuthority()` trả tên yếu tố, ví dụ `FACTOR_PASSWORD`.
- `getIssuedAt()` trả thời điểm authority cho yếu tố đó được ghi nhận.
- Bản thân factor authority **không tự đặt TTL chung**. Cùng một lần xác thực có thể đáp ứng rule “trong 60 phút” nhưng không còn đáp ứng rule “trong 5 phút”.

Ví dụ: mật khẩu được nhập lúc 09:00, đến 09:45 có thể chưa đủ “password trong 30 phút” để thay đổi số điện thoại, dù phiên vẫn đăng nhập. Khi đó ứng dụng cần yêu cầu người dùng chứng minh lại yếu tố theo một luồng step-up an toàn.

### 3.2. Không tự gán factor giả

Trong Spring Security 7, framework thêm factor authority khi cơ chế xác thực tương ứng được thực hiện thành công. **Không** làm thế này để “bật MFA”:

~~~java
// SAI: tự phát authority mà không hề xác minh password/OTT.
var authorities = java.util.List.of(
    new org.springframework.security.core.authority.SimpleGrantedAuthority(
        FactorGrantedAuthority.PASSWORD_AUTHORITY),
    new org.springframework.security.core.authority.SimpleGrantedAuthority(
        FactorGrantedAuthority.OTT_AUTHORITY)
);
~~~

Đây là **đoạn phản ví dụ**, không phải chương trình độc lập. Những string `FACTOR_PASSWORD`/`FACTOR_OTT` không được lấy từ header do client gửi, JWT claim chưa kiểm hoặc cờ tự khai trong form. Tính bảo đảm nằm ở **authentication mechanisms** thực tế và sự quản lý `SecurityContext`, không nằm ở việc chèn chuỗi vào danh sách.

Khi triển khai custom authentication provider, hãy đọc API/contract của phiên bản Spring Security đang dùng trước khi phát một `FactorGrantedAuthority`, bảo đảm chỉ phát sau khi đã kiểm chứng yếu tố đúng và xử lý thời gian/session hợp lệ.

## 4. @EnableMultiFactorAuthentication làm gì?

Annotation đầy đủ:

~~~java
org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication
~~~

Cú pháp:

~~~java
@Configuration
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
class SecurityConfiguration {
    // Các bean SecurityFilterChain và authentication mechanisms đặt tại đây.
}
~~~

Đây là **mảnh cấu hình**, không phải file Java đầy đủ: phải import `@Configuration`, `@EnableMultiFactorAuthentication` và `FactorGrantedAuthority` từ đúng các package Spring Security 7.

Ý nghĩa của annotation:

1. Kích hoạt cơ chế hỗ trợ MFA ở lớp authorization.
2. Khi có `authorities`, tạo một `AuthorizationManagerFactory` kết hợp rule thông thường với **các factor bắt buộc**.
3. Các authorization rule như `authenticated()`, `hasRole("ADMIN")` khi được tạo qua factory có thể yêu cầu thêm cả `FACTOR_PASSWORD` và `FACTOR_OTT`.
4. Spring Security phối hợp entry point/flow để đưa người dùng tới bước xác thực cho **factor còn thiếu** khi những cơ chế tương ứng đã được cấu hình.

**Annotation không tự tạo mật khẩu hay dịch vụ gửi OTT.** Ứng dụng phải cấu hình cả:

~~~java
http
    .formLogin(Customizer.withDefaults())
    .oneTimeTokenLogin(Customizer.withDefaults());
~~~

Trong tích hợp Servlet 7.0, form login cung cấp password factor, còn One-Time Token Login (OTT) cung cấp OTT factor khi hoàn tất đúng quy trình. Không dùng hai lần gọi `formLogin()` làm hai yếu tố.

### 4.1. Role, scope và factor là các dimensions khác nhau

Giả sử một tài khoản có:

~~~text
ROLE_ADMIN
FACTOR_PASSWORD
FACTOR_OTT
~~~

Khi cấu hình global MFA cần PASSWORD + OTT:

| Rule | Yêu cầu thực tế |
| --- | --- |
| `anyRequest().authenticated()` | Người dùng đã xác thực và có cả PASSWORD lẫn OTT theo policy |
| `hasRole("ADMIN")` | Có `ROLE_ADMIN` **và** đủ hai factor |
| `hasAuthority("SCOPE_reports.write")` | Có scope cụ thể **và** đủ factor khi áp chung bằng factory |
| `hasRole("USER")` | Có role USER **và** đủ factor |

Không biến `ROLE_ADMIN` thành factor; không biến `FACTOR_OTT` thành quyền được chỉnh dữ liệu của tenant khác. Quyền theo tài nguyên/đối tượng vẫn cần kiểm tra riêng.

### 4.2. Factory phía sau annotation

Về khái niệm, annotation với hai authorities tương đương với việc cung cấp một factory như:

~~~java
@Bean
AuthorizationManagerFactory<Object> authorizationManagerFactory() {
    return AuthorizationManagerFactories.multiFactor()
        .requireFactors(
            FactorGrantedAuthority.PASSWORD_AUTHORITY,
            FactorGrantedAuthority.OTT_AUTHORITY
        )
        .build();
}
~~~

Đây là **mảnh bean minh họa**, sử dụng các class Spring Security 7 trong package phù hợp. Trong một ứng dụng, thường chọn **một** trong hai cách: annotation tạo factory hoặc tự cấu hình factory. Tránh khai báo trùng bean factory rồi suy rằng cả hai được kết hợp một cách tự động.

## 5. Luồng MFA password + OTT của Spring Security 7

Một luồng web Servlet phổ biến:

~~~text
Browser chưa đăng nhập
         |
         | GET /private
         v
Authorization cần FACTOR_PASSWORD + FACTOR_OTT
         |
         | chuyển tới password login
         v
POST /login (username/password đúng)
         |
         | Authentication có FACTOR_PASSWORD
         | nhưng chưa đủ FACTOR_OTT
         v
Redirect tới One-Time Token Login
         |
         | POST /ott/generate yêu cầu token cho account
         | Spring tạo one-time token ngắn hạn
         | success handler giao token qua kênh ngoài (email...)
         v
Người dùng nhận token, gửi tới /login/ott
         |
         | xác minh token chưa dùng, đúng account, còn hạn
         v
Authentication có đủ PASSWORD + OTT
         |
         | Authorization rule thành công
         v
GET /private -> 200
~~~

Trong hệ thống thật, Spring Security quản lý chuyển đổi/duy trì bằng chứng factor qua phiên theo cơ chế framework. Đừng tự ghép hai `Authentication` bất kỳ rồi lấy union authorities nếu không theo đúng contract; khi đổi principal, hết hạn, logout hoặc session fixation, phải bảo đảm factor của người cũ không bị tái sử dụng cho người mới.

**One-Time Token (OTT) khác OTP/TOTP/HOTP.** Spring Security `oneTimeTokenLogin()` (đã có từ 6.4) cung cấp token **một lần** do server sinh và phát qua handler/kênh ngoài như email/magic link. Đây không mặc nhiên là mã 6 số quay vòng theo TOTP mà app authenticator tính cục bộ.

MFA mạnh cần kiểm tra **tính độc lập của yếu tố**: nếu mật khẩu và email đều bị cùng một thiết bị/session đánh cắp, rủi ro vẫn còn. Đặc biệt magic link ở cùng browser có thể bị lộ qua URL/log; hệ thống quan trọng nên cân nhắc WebAuthn/phishing-resistant MFA.

## 6. Ví dụ Spring Boot 4.0 / Spring Security 7.0 (Java 17+)

Ví dụ hoàn chỉnh ở đây tạo ứng dụng Servlet sử dụng:

- Spring Boot **4.0.x** (ví dụ `4.0.9`) và Spring Security **7.0.x** theo BOM.
- Form login với user lab in-memory.
- One-Time Token Login; `OneTimeTokenGenerationSuccessHandler` gửi token qua SMTP **đến mailbox đã đăng ký**.
- `@EnableMultiFactorAuthentication` yêu cầu PASSWORD + OTT cho authorization rules.
- Route `/me` để quan sát kết quả sau khi xác thực; `/admin/info` còn yêu cầu role ADMIN.

**Điều kiện chạy end-to-end:** phải có SMTP/mail capture server (ví dụ Mailpit trong môi trường lab) và sử dụng browser giữ session cookie. Code Java/Maven có thể biên dịch và khởi động với dependency đúng; thao tác nhận OTP/OTT cần môi trường thư thật. Domain `example.test` chỉ là dữ liệu test, không phải email vận hành công cộng.

### 6.1. Cấu trúc thư mục

~~~text
mfa-demo/
├── pom.xml
└── src/main/
    ├── java/demo/mfa/MfaDemoApplication.java
    └── resources/application.properties
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>mfa-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-mail</artifactId>
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

Spring Boot 4 có starter mới `spring-boot-starter-webmvc` (thay cho tên starter web cũ). Parent BOM quản lý phiên bản Spring Security 7 tương thích; không tự override xuống `spring-security-core:6.x` vì class MFA sẽ không tồn tại.

### 6.3. application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
server.port=8080

# SMTP dev-only: Mailpit/công cụ capture mail chạy cục bộ.
spring.mail.host=127.0.0.1
spring.mail.port=1025

# Không đặt thông tin đăng nhập SMTP thật vào Git.
spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=5000
spring.mail.properties[mail.smtp.writetimeout]=5000
~~~

Mail capture SMTP test không gửi email ra Internet; người học đọc thư bằng giao diện mail capture riêng (ví dụ Mailpit thường mở `http://localhost:8025` nếu được cấu hình như vậy). Không triển khai máy chủ nhận mail công khai không xác thực cho môi trường production.

### 6.4. MfaDemoApplication.java

~~~java
package demo.mfa;

import java.util.Map;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.FactorGrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.ott.OneTimeTokenGenerationSuccessHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableWebSecurity
@EnableMultiFactorAuthentication(authorities = {
    FactorGrantedAuthority.PASSWORD_AUTHORITY,
    FactorGrantedAuthority.OTT_AUTHORITY
})
public class MfaDemoApplication {

    private static final String DEMO_USER = "learner@example.test";

    public static void main(String[] args) {
        SpringApplication.run(MfaDemoApplication.class, args);
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername(DEMO_USER)
                .password("{noop}lab-password")
                .roles("USER")
                .build()
        );
    }

    @Bean
    OneTimeTokenGenerationSuccessHandler sendOttViaMail(
            JavaMailSender mailSender) {
        return (request, response, token) -> {
            // Demo chỉ chấp nhận mailbox thuộc account đã provision.
            // Production phải lookup email đã xác minh ở server.
            if (DEMO_USER.equals(token.getUsername())) {
                SimpleMailMessage message = new SimpleMailMessage();
                message.setFrom("no-reply@example.test");
                message.setTo(DEMO_USER);
                message.setSubject("Your one-time login token");
                message.setText(
                    "One-time token (use it on the /login/ott form):\n"
                    + token.getTokenValue()
                );
                mailSender.send(message);
            }
            // Không hiển thị token trên HTTP response hoặc server log.
            response.sendRedirect(request.getContextPath() + "/login/ott");
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OneTimeTokenGenerationSuccessHandler ottHandler)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .oneTimeTokenLogin(ott -> ott
                .tokenGenerationSuccessHandler(ottHandler));

        return http.build();
    }

    @RestController
    static class DemoApi {

        @GetMapping("/me")
        Map<String, Object> currentUser(Authentication auth) {
            List<String> authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();

            return Map.of(
                "username", auth.getName(),
                "authorities", authorities
            );
        }

        @GetMapping("/admin/info")
        String adminInfo() {
            return "admin protected";
        }
    }
}
~~~

**Giải thích cấu hình:**

1. `@EnableMultiFactorAuthentication` ở class ứng dụng yêu cầu cả `FACTOR_PASSWORD` và `FACTOR_OTT` thông qua authorization factory.
2. `UserDetailsService` chỉ chứa `learner@example.test` với `ROLE_USER`; `{noop}` chỉ để chạy lab, **không bao giờ dùng password rõ trong sản xuất**.
3. `formLogin` bật xác thực bằng mật khẩu; `oneTimeTokenLogin` bật luồng tạo/tiêu thụ OTT.
4. `OneTimeTokenGenerationSuccessHandler` là phần **phải tùy chỉnh** để giao token cho người dùng. Framework không thể tự suy ra cách giao qua email/SMS. Bean trong ví dụ chỉ gửi đến mailbox đã provision, không dùng tùy tiện địa chỉ do attacker tự khai.
5. `mailSender.send` gọi SMTP nội bộ (đã cấu hình). Không dùng handler in token ra access log, URL phản hồi hoặc query parameter khi chưa có threat model.
6. `/me` trả dữ liệu cho học tập và chỉ truy cập khi đủ MFA. Endpoint `/admin/info` còn đòi `ROLE_ADMIN`; user demo có role USER nên vẫn không vào được dù hoàn thành cả hai factor.
7. Default form-login page và OTT submit page được framework hỗ trợ. Spring mặc định bảo vệ các HTTP POST thay đổi trạng thái bằng CSRF; trình duyệt cần dùng form/token đúng, không vô hiệu hóa CSRF chỉ để demo hoạt động.

**Đây là code lab**, không phải thiết kế MFA production hoàn chỉnh: cần user store/persistent OTT service, gửi token out-of-band đã xác minh, mail provider thật, rate limiting, audit, account status checking, recovery và session/HA policy.

### 6.5. Chạy lab và kết quả mong đợi

Cần JDK 17+, Maven và SMTP dev. Ví dụ nếu bạn đã cài Docker, có thể chạy mail capture:

~~~bash
docker run --rm -p 1025:1025 -p 8025:8025 axllent/mailpit:latest
~~~

Lệnh trên dùng image của công cụ mail capture bên thứ ba chỉ cho máy lab; môi trường chạy Docker phải có mạng để tải image nếu chưa có. Có thể dùng SMTP capture tool khác. Để production, cấu hình máy chủ SMTP thật, TLS/authentication và secrets từ vault.

Trong thư mục `mfa-demo`:

~~~bash
mvn spring-boot:run
~~~

Sau khi app khởi động:

1. Mở `http://localhost:8080/me` bằng browser chưa login.
2. Trang login của Spring yêu cầu password: username `learner@example.test`, password `lab-password`.
3. Mật khẩu đúng nhưng chưa có OTT thì rule MFA chưa thỏa; Spring Security đưa người dùng tới bước bổ sung.
4. Từ UI của OTT, yêu cầu tạo token cho account. Default token generation nhận username và handler gửi tới SMTP capture.
5. Mở giao diện mailbox dev (ví dụ `http://localhost:8025`), đọc mã OTT rồi nhập ở trang submit `/login/ott`.
6. Nếu token đúng, chưa hết hạn, chưa dùng và gắn đúng account, quay lại `/me` sẽ được 200. JSON trong môi trường Spring Security 7 thường chứa ít nhất các authority sau:

~~~json
{
  "username": "learner@example.test",
  "authorities": ["FACTOR_OTT", "FACTOR_PASSWORD", "ROLE_USER"]
}
~~~

Có thể có authority bổ sung tùy phiên bản và chính sách; khi viết integration test nên xác minh **có hai factor cần thiết** thay vì cố định toàn bộ danh sách.

Với account `learner@example.test`, truy cập `/admin/info` vẫn bị từ chối vì thiếu `ROLE_ADMIN`, dù MFA đã hoàn tất.

**Không sử dụng `curl -u` để kết luận MFA đã hoạt động.** Đây là luồng trình duyệt có session, form, CSRF và chuyển hướng tới factor còn thiếu; HTTP Basic hoặc Bearer token không tự tạo cùng quy trình tích lũy factor.

### 6.6. Tại sao cần test âm tính?

| Tình huống | Kỳ vọng |
| --- | --- |
| Chưa nhập password và chưa OTT | Không được xem `/me`; đưa tới login tương ứng |
| Chỉ password đúng, chưa OTT | Chưa được truy cập tài nguyên yêu cầu cả hai factor |
| OTT đúng nhưng chưa có password factor | Chưa được truy cập tài nguyên yêu cầu cả hai factor |
| Password + OTT đúng, cùng account/session, còn hiệu lực | Được truy cập `/me` |
| Token hết hạn | Không bổ sung được factor OTT |
| Dùng lại OTT đã tiêu thụ | Không được dùng lại làm bằng chứng hợp lệ |
| OTT của user A dùng trong flow user B | Không cấp factor cho user B |
| Đủ hai factor nhưng thiếu role ADMIN | Không được truy cập `/admin/info` |
| Logout rồi dùng session cũ | Không được tiếp tục dùng các factor đã xác thực |
| SMTP không phản hồi | Không âm thầm coi OTT đã được kiểm; fail closed |

Đối với ứng dụng Servlet có form-based authentication, trường hợp chưa đủ yếu tố có thể tạo **HTTP 302 tới trang login/step-up**, không nhất thiết trả 401/403 trực tiếp. Kiểm tra **không được cấp quyền**, redirect và session state thay vì hard-code tất cả trường hợp là 403.

## 7. Cấu hình MFA có chọn lọc: chỉ những endpoint nhạy cảm

Không phải hệ thống nào cũng cần MFA toàn cục. Ví dụ:

- `/dashboard/**`: chỉ cần authenticated.
- `/user/settings/**`: cần PASSWORD + OTT.
- `/admin/**`: cần PASSWORD + OTT + ROLE_ADMIN.

Nếu dùng annotation có `authorities = { PASSWORD, OTT }` **toàn cục**, nó không còn là chính sách “chỉ settings/admin”. Spring Security 7 hỗ trợ thiết kế chọn lọc bằng cách bật hỗ trợ annotation **không xuất bản factory bắt buộc chung**:

~~~java
@EnableMultiFactorAuthentication(authorities = {})
~~~

Rồi tạo factory **cục bộ trong cấu hình SecurityFilterChain**:

~~~java
// Đoạn phương thức @Bean minh họa cho Spring Security 7.0+.
@Bean
SecurityFilterChain selectiveSecurityFilterChain(HttpSecurity http)
        throws Exception {
    var mfa = AuthorizationManagerFactories.multiFactor()
        .requireFactors(
            FactorGrantedAuthority.PASSWORD_AUTHORITY,
            FactorGrantedAuthority.OTT_AUTHORITY
        )
        .build();

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/admin/**").access(mfa.hasRole("ADMIN"))
            .requestMatchers("/user/settings/**")
                .access(mfa.authenticated())
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .oneTimeTokenLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Đây là **phương thức cấu hình minh họa**, cần import Spring Security 7 và tích hợp handler giao OTT như mục 6. Khi dùng phương thức này, thay thế `securityFilterChain` toàn cục của ví dụ, **không** đồng thời tạo hai chain trùng matcher cho cùng URL mà thiếu thiết kế.

**Ý nghĩa:** chỉ `/admin/**` và `/user/settings/**` sử dụng `mfa` factory nên cần hai yếu tố. `anyRequest().authenticated()` dùng rule xác thực thông thường. Đừng khai báo `mfa` dưới dạng `@Bean` trong trường hợp này nếu không muốn rule bị áp toàn cục.

### 7.1. Dùng hasAllAuthorities khi policy đơn giản

Spring Security 7 có thể diễn đạt yêu cầu trực tiếp:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/admin/**").hasAllAuthorities(
        "ROLE_ADMIN",
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.OTT_AUTHORITY
    )
    .anyRequest().authenticated()
)
~~~

Đây chỉ là **mảnh DSL**, phải đặt bên trong `HttpSecurity` và cấu hình cả login mechanisms. Với nhiều route và chính sách phức tạp, lặp danh sách factor khiến khó bảo trì; `AuthorizationManagerFactory` giúp tái sử dụng chính sách. Chỉ có `hasAuthority("FACTOR_OTT")` không phải bắt buộc MFA hai yếu tố.

### 7.2. Dùng annotation ở method security

Trong Servlet Spring Security 7, Javadoc của `@EnableMultiFactorAuthentication` cho biết các yêu cầu có thể được sử dụng với `@EnableWebSecurity` và `@EnableMethodSecurity`. Ví dụ `@PreAuthorize("hasRole('ADMIN')")` có thể tham gia chính sách đã cấu hình phù hợp. Tuy nhiên bật MFA ở filter chain không có nghĩa mọi method/dispatcher path đều tự có cùng bảo đảm nếu method-security chưa bật hoặc có nhiều security chains. Thiết kế chính sách nhất quán và viết tests cho cả request và service methods.

## 8. Factor phải còn “mới”: validDuration và step-up

Một ứng dụng có thể muốn:

- Trang dashboard: xác thực bất kỳ, thời điểm không quan trọng ngoài session policy.
- Đổi số điện thoại: password mới xác minh trong **30 phút**.
- Chuyển tiền: password trong **30 phút** và OTT trong **5 phút**.

Từ `FactorGrantedAuthority.getIssuedAt()`, Spring Security 7 hỗ trợ cấu hình thời hạn ở **authorization rule**, ví dụ:

~~~java
// Mảnh cấu hình Spring Security 7.0+, không phải class độc lập.
var passwordFresh30m = AuthorizationManagerFactories.multiFactor()
    .requireFactor(factor -> factor
        .passwordAuthority()
        .validDuration(java.time.Duration.ofMinutes(30)))
    .build();

http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/change-phone/**")
        .access(passwordFresh30m.authenticated())
    .anyRequest().authenticated());
~~~

Với 45 phút đã trôi qua từ lúc nhập mật khẩu, rule “30 phút” không còn hợp lệ. Cùng một authority trong phiên vẫn có thể đáp ứng rule “trong 1 giờ” nếu policy đó cho phép.

**Mốc issuedAt không phải thời gian session hết hạn.** Yêu cầu tái xác thực yếu tố nhạy cảm phải được tính theo policy riêng, và khi hoàn thành phải ghi nhận thời điểm factor mới đúng cách. Nếu môi trường nhiều instance, đảm bảo đồng bộ clock, session persistence và chính sách step-up.

Có thể thiết kế nhiều yếu tố với validDuration khác nhau bằng các lần `requireFactor(...)` theo factory API hỗ trợ. Khi cần đủ **nhiều** factor, không chỉ kiểm tuổi của một factor rồi quên factor thứ hai.

## 9. Khi nào chỉ cần một phương thức mạnh thay cho “password + OTT”?

Passkey/WebAuthn có thể đưa ra bằng chứng sử dụng private key ràng buộc với RP ID và, khi yêu cầu UV, xác minh user tại authenticator. Tùy chính sách tổ chức, một phương thức phishing-resistant như passkey có thể đạt mức bảo đảm mong muốn mà không cần password và email OTT.

Đừng tự gán:

~~~text
FACTOR_WEBAUTHN = FACTOR_PASSWORD + FACTOR_OTT
~~~

Đó là **không phải đẳng thức trong Spring Security**. Nếu policy muốn cho phép:

- **WebAuthn**, hoặc
- **password AND OTT**,

thì phải biểu diễn quy tắc **OR giữa hai tổ hợp** bằng authorization manager. Spring Security 7 có `AllRequiredFactorsAuthorizationManager.anyOf(...)` để diễn tả policy này khi dùng đúng API phiên bản.

Ví dụ minh họa:

~~~java
// Mảnh cấu hình Spring Security 7.x; phần chain và WebAuthn
// registration/repository phải được cấu hình riêng.
AllRequiredFactorsAuthorizationManager<Object> passkey =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.webauthnAuthority())
        .build();

AllRequiredFactorsAuthorizationManager<Object> passwordAndOtt =
    AllRequiredFactorsAuthorizationManager.<Object>builder()
        .requireFactor(factor -> factor.passwordAuthority())
        .requireFactor(factor -> factor.ottAuthority())
        .build();

var alternatives = AllRequiredFactorsAuthorizationManager.anyOf(
    passkey, passwordAndOtt);
~~~

Mảnh này **không chạy độc lập** và không cung cấp WebAuthn enrollment, RP ID/origin hay OTT delivery; những thành phần đó cần được triển khai và kiểm thử theo module riêng. Khi kết hợp với AuthorizationManagerFactory, chỉ cấp quyền nếu một tổ hợp hợp lệ theo policy.

### 9.1. Điều kiện WebAuthn registered ở Spring Security 7.1+

Tài liệu Spring Security 7.1 giới thiệu ví dụ có điều kiện:

~~~java
// Chỉ dùng khi phiên bản thực tế hỗ trợ MultiFactorCondition.
@EnableMultiFactorAuthentication(
    authorities = {
        FactorGrantedAuthority.PASSWORD_AUTHORITY,
        FactorGrantedAuthority.WEBAUTHN_AUTHORITY
    },
    when = MultiFactorCondition.WEBAUTHN_REGISTERED
)
~~~

Cấu hình này minh họa yêu cầu password + WebAuthn **cho user đã đăng ký passkey**, cần các bean repository WebAuthn (`PublicKeyCredentialUserEntityRepository` và `UserCredentialRepository`) để xác định trạng thái registration. **Không copy thuộc tính `when` vào Spring Security 7.0** nếu annotation/Javadoc phiên bản đó chưa có nó. Nếu bảo mật đòi MFA cho toàn bộ user, tuyệt đối không dùng điều kiện “chỉ khi đã đăng ký” rồi bỏ mặc những user chưa đăng ký; phải có enrollment policy và fail-closed phù hợp.

## 10. Java 17 độc lập: minh họa authority, factor và thời hạn

Bài lab nhỏ dưới đây không dùng thư viện Spring và **không thực hiện authentication**. Nó giúp hiểu ba khái niệm tách biệt: quyền nghiệp vụ, factor đã ghi nhận và độ mới của factor.

Tạo tệp `FactorPolicyDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Set;

public class FactorPolicyDemo {

    record VerifiedFactor(String authority, Instant issuedAt) {}

    static boolean hasFactor(
            List<VerifiedFactor> factors, String expected) {
        return factors.stream()
                .anyMatch(f -> f.authority().equals(expected));
    }

    static boolean factorIsFresh(
            List<VerifiedFactor> factors,
            String expected,
            Instant now,
            Duration maximumAge) {
        return factors.stream().anyMatch(f ->
            f.authority().equals(expected)
            && !f.issuedAt().isAfter(now)
            && !f.issuedAt().plus(maximumAge).isBefore(now));
    }

    static boolean mayAdmin(
            Set<String> roles, List<VerifiedFactor> factors) {
        return roles.contains("ROLE_ADMIN")
                && hasFactor(factors, "FACTOR_PASSWORD")
                && hasFactor(factors, "FACTOR_OTT");
    }

    public static void main(String[] args) {
        Instant now = Instant.parse("2026-11-06T09:00:00Z");

        var factors = List.of(
            new VerifiedFactor("FACTOR_PASSWORD",
                now.minus(Duration.ofMinutes(45))),
            new VerifiedFactor("FACTOR_OTT",
                now.minus(Duration.ofMinutes(2)))
        );

        System.out.println("bothFactors=" +
            (hasFactor(factors, "FACTOR_PASSWORD")
                && hasFactor(factors, "FACTOR_OTT")));
        System.out.println("password30m=" +
            factorIsFresh(factors, "FACTOR_PASSWORD",
                now, Duration.ofMinutes(30)));
        System.out.println("ott5m=" +
            factorIsFresh(factors, "FACTOR_OTT",
                now, Duration.ofMinutes(5)));
        System.out.println("adminAsUser=" +
            mayAdmin(Set.of("ROLE_USER"), factors));
        System.out.println("adminWithRole=" +
            mayAdmin(Set.of("ROLE_ADMIN"), factors));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac --release 17 FactorPolicyDemo.java
java FactorPolicyDemo
~~~

Stdout **chính xác**:

~~~text
bothFactors=true
password30m=false
ott5m=true
adminAsUser=false
adminWithRole=true
~~~

Giải thích:

- Đã có **cả hai** factor, nhưng password đã cũ 45 phút nên không còn đáp ứng rule 30 phút.
- OTT xác minh 2 phút trước nên đáp ứng rule 5 phút.
- Người dùng có cả hai factor nhưng chỉ `ROLE_USER` không thể truy cập route yêu cầu `ROLE_ADMIN`.
- Khi có `ROLE_ADMIN` và đủ factor, rule đơn giản `mayAdmin` cho phép. Nếu route yêu cầu factor mới, cần kết hợp `factorIsFresh` vào policy.

**Không dùng chương trình này để thực hiện MFA thực tế.** Nó cố tình nhận một danh sách đã đặt tên `VerifiedFactor` mà không chứng minh password/OTT đã được kiểm. Trong hệ thống thật, chỉ framework/authentication providers đáng tin sau khi xác thực thành công mới được cấp factor authority.

## 11. Các lỗi phổ biến và hướng xử lý

| Hiện tượng / sai lầm | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Import `FactorGrantedAuthority` không tìm thấy | Đang dùng Spring Security 6.x | Chuyển sang 7.0+ cùng Boot 4 hoặc dùng giải pháp MFA phù hợp 6.x |
| `@EnableMultiFactorAuthentication` không compile | Sai version hoặc sai package | Dùng `org.springframework.security.config.annotation.authorization.EnableMultiFactorAuthentication` trên 7.0+ |
| Có annotation nhưng app vẫn chỉ hỏi password | Chưa bật mechanism OTT/WebAuthn hoặc chưa cấu hình handler/token delivery | Cấu hình các factor providers và kiểm luồng step-up |
| One-time token không gửi đến user | Chưa cung cấp `OneTimeTokenGenerationSuccessHandler` hoặc SMTP lỗi | Triển khai delivery channel, timeout, bảo vệ log |
| Token đến cùng browser nên MFA yếu | Kênh email/thiết bị không độc lập | Đánh giá threat model, cân nhắc passkey/hardware key |
| Đăng nhập đúng nhưng redirect vòng lặp | Session/context chưa lưu, factor missing không lấy được, endpoint matcher sai | Kiểm login entry points, session cookie, filter chain, token delivery |
| Ủy quyền sai khi chỉ dùng `hasRole("ADMIN")` mà muốn MFA | Không dùng factory có factor hoặc thiếu rule factor | Dùng global annotation/factory chọn lọc đúng |
| Dùng `permitAll` hoặc allowlist sai | Endpoint nhạy cảm bỏ qua check do matcher/order | Rà soát mọi SecurityFilterChain và route |
| Người dùng đủ factor nhưng bị 403 ở admin | Thiếu ROLE_ADMIN hoặc policy object-level | Kiểm authorities khác nhau giữa role và factor |
| Factor còn trong session quá lâu | Chưa yêu cầu validDuration/reauth cho hành động nhạy cảm | Dùng chính sách factor age và session timeout |
| Cùng một OTT dùng lại được | Token service/consumption không bảo đảm one-time | Persistent token store, atomic consume, TTL và test replay |
| OTT của account A hoàn thành cho account B | Binding username/session sai | Ràng buộc token với principal đúng, chặn session mix-up |
| Luồng đăng nhập mới giữ lại factor cũ của user khác | Session fixation/concurrency bug | Kiểm account switching, session invalidation, SecurityContext lifecycle |
| Custom JWT gắn chuỗi `FACTOR_OTT` theo client input | Factor bị giả mạo qua claims chưa đáng tin | Chỉ tin issuer/cơ chế đã xác minh, thiết kế claim contract chặt chẽ |
| Chưa hỗ trợ `MultiFactorCondition.WEBAUTHN_REGISTERED` | Dùng nhánh 7.0 hoặc thiếu repository | Kiểm version 7.1+, đăng ký WebAuthn repositories và enrollment |
| Dùng Servlet annotation trong WebFlux | Khác stack/security DSL | Đọc tài liệu reactive đúng phiên bản, không suy diễn hỗ trợ tương đương |

## 12. Giữ nguyên ý nghĩa bảo mật khi phát triển thực tế

### 12.1. OTT phải ngắn hạn và single-use

Một one-time token là credential nhạy cảm. Production cần:

- Token giá trị khó đoán, dùng CSPRNG.
- TTL ngắn, chỉ dùng một lần, atomic consumption để chống race.
- Ràng buộc token với đúng user và ceremony/login request theo cơ chế đã thiết kế.
- Delivery qua mailbox hoặc kênh đã xác minh, không dùng địa chỉ do client bất kỳ chỉ định.
- Rate limit token generation và validation; tránh spam email, account enumeration.
- Không log nguyên token, không đưa vào analytics/referrer hay support screenshots.
- Có cơ chế thống kê và cảnh báo hành vi bất thường.

Spring Security One-Time Token Login hỗ trợ service mặc định in-memory cho demo; production thường cần persistent service như JDBC và chính sách HA phù hợp. Nếu dùng thư token qua email, email inbox có thể bị xâm nhập nên không mặc định đạt assurance của phần cứng FIDO2.

### 12.2. Session và factor state

MFA trải qua **nhiều bước HTTP**. Hãy bảo vệ:

- Cookie `Secure`, `HttpOnly`, `SameSite` phù hợp.
- HTTPS mọi nơi, HSTS ở production.
- Session fixation protection sau authentication và step-up.
- CSRF protection cho form/OTT endpoints.
- Session timeout/invalidation khi logout, đổi account, reset credential.
- Shared session store khi load balancing đa instance, hoặc topology cho phép duy trì đúng state.
- Quy tắc reauthentication cho hành động cực kỳ nhạy cảm.
- Lưu dấu thời gian factor và kiểm lại khi policy yêu cầu.

Một JWT Resource Server **stateless** không tự tích lũy password + OTT qua phiên Servlet; nếu hệ thống dùng OAuth/OIDC, thiết kế bằng chứng MFA với IdP/AS và claims như `amr`/`acr` khi thích hợp, đồng thời kiểm issuer, audience, freshness và semantics đúng. Không thay toàn bộ MFA bằng việc client tự gửi `amr=["pwd","otp"]`.

### 12.3. Phân quyền vẫn cần sau MFA

MFA xác nhận chất lượng bằng chứng đăng nhập, không thay thế kiểm tra:

- `ROLE_ADMIN` cho chức năng quản trị.
- Tenant/organization authorization.
- Quyền trên object (bản ghi, tài khoản, báo cáo).
- Điều kiện rủi ro/step-up theo số tiền, IP, device posture khi chính sách yêu cầu.
- Phân quyền quản lý credential (thêm/xóa passkey, đổi email/phone, recovery code).

Tăng số factor không sửa được lỗi IDOR/BOLA hoặc policy cho phép quá rộng.

## 13. Ma trận kiểm thử đề xuất

### Chức năng

- [ ] Password đúng một mình chưa vượt qua route yêu cầu cả hai factor.
- [ ] OTT đúng một mình chưa vượt qua route yêu cầu cả hai factor.
- [ ] Password + OTT đúng cho cùng principal/session sẽ vượt qua rule cần MFA.
- [ ] Role ADMIN và hai factor đều cần cho `/admin/**`; thiếu một trong ba điều kiện sẽ bị từ chối.
- [ ] OTT hết hạn, dùng lại hoặc bị thay đổi không thể cấp `FACTOR_OTT`.
- [ ] OTP/TOTP không được nhầm với Spring OTT khi chưa có provider riêng.
- [ ] Logout, session expiration, đổi account sẽ mất các factor tương ứng.
- [ ] Password factor cũ 45 phút không thỏa route yêu cầu validDuration 30 phút.
- [ ] OTT 2 phút trước vẫn thỏa validDuration 5 phút.
- [ ] Với MFA chỉ ở settings/admin, dashboard có thể dùng authentication thông thường.

### Bảo mật và độ bền

- [ ] Không thể tự gửi `FACTOR_PASSWORD`/`FACTOR_OTT` trong form/header để vượt qua kiểm tra.
- [ ] OTT nhận ở đúng mailbox đã provision; gửi hàng loạt yêu cầu bị rate limit.
- [ ] Mã OTT không xuất hiện trong access log, exception log, query redirect hoặc analytics.
- [ ] SMTP lỗi/timeout không dẫn đến việc framework tự coi factor đã thành công.
- [ ] Chặn replay/race condition khi hai request cùng consume OTT.
- [ ] Multiple SecurityFilterChain không vô tình bỏ qua factory/MFA.
- [ ] Cluster/shared session/OTT store giữ đúng trạng thái khi request qua nhiều replica.
- [ ] Session cookie và CSRF không bị vô hiệu hóa để xử lý sự cố demo.
- [ ] Nếu có OAuth/OIDC/WebAuthn, kiểm riêng ranh giới trust, issuance và rp/issuer.

### Kiểm tra version

- [ ] Dùng `mvn dependency:tree` hoặc build tool để xác nhận **Spring Security 7.x** đang có trên classpath.
- [ ] Không import `FactorGrantedAuthority` trong project chỉ có Security 6.x.
- [ ] Không dùng thuộc tính annotation hay builder của 7.1+ trên 7.0 nếu Javadoc không có.
- [ ] Kiểm tài liệu Servlet/Reactive riêng thay vì giả định giống nhau.
- [ ] Có integration test cho redirect, phần mềm gửi OTT và yêu cầu nhiều factor.

## 14. Câu hỏi tự kiểm tra

1. Vì sao `ROLE_ADMIN` không được xem là một factor?
2. `FactorGrantedAuthority.PASSWORD_AUTHORITY` có giá trị authority nào? `OTT_AUTHORITY` là gì?
3. `getIssuedAt()` khác session expiration như thế nào?
4. `@EnableMultiFactorAuthentication` có tự tạo mã OTT hoặc gửi email không?
5. Tại sao ứng dụng cần cả `formLogin()` và `oneTimeTokenLogin()` khi policy đòi password + OTT?
6. Vì sao hai OTP cùng nhận bằng một mailbox không mặc nhiên là hai factor độc lập?
7. Vì sao không được tự thêm `SimpleGrantedAuthority("FACTOR_OTT")` để xử lý một yêu cầu đang bị từ chối?
8. Vì sao không thể copy mã dùng `@EnableMultiFactorAuthentication` từ Spring Security 7 vào Spring Security 6.5?
9. Nếu muốn MFA chỉ cho `/admin/**` và `/user/settings/**`, cần cấu hình global factory hay local factory?
10. Vì sao password đã dùng 45 phút trước vẫn có thể không đủ cho route đòi password trong 30 phút?
11. Khác nhau giữa password + OTT và đăng nhập WebAuthn có UV là gì về threat model?
12. Khi API dùng JWT stateless, việc thêm annotation Servlet có tự làm IdP phát token chứa bằng chứng MFA không?

**Kết luận:** `FactorGrantedAuthority` mô tả yếu tố **đã được chứng minh** và thời điểm chứng minh; `@EnableMultiFactorAuthentication` (Spring Security **7.0+**) bổ sung **chính sách bắt buộc factor** vào authorization. Để MFA thực sự tồn tại, ứng dụng còn cần các **authentication mechanisms đáng tin cậy**, kênh thu nhận bằng chứng, session/token lifecycle và kiểm quyền nghiệp vụ tương ứng.

## 15. Tài liệu chính thức và tham khảo

- [Spring Security 7.0 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/mfa.html)
- [Spring Security 7.1 — Multi-Factor Authentication](https://docs.spring.io/spring-security/reference/7.1/servlet/authentication/mfa.html)
- [Spring Security 7.0 — FactorGrantedAuthority API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/core/authority/FactorGrantedAuthority.html)
- [Spring Security 7.0 — @EnableMultiFactorAuthentication API](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/authorization/EnableMultiFactorAuthentication.html)
- [Spring Security 7.0 — One-Time Token Login](https://docs.spring.io/spring-security/reference/7.0/servlet/authentication/onetimetoken.html)
- [Spring Boot 4.0 — Getting Started and Maven Starters](https://docs.spring.io/spring-boot/4.0/tutorial/first-application/index.html)
- [Spring Boot 4.0 — Sending Email](https://docs.spring.io/spring-boot/4.0/reference/io/email.html)
- [OWASP — Multifactor Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
