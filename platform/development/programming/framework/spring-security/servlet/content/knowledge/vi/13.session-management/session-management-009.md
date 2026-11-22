# Cookie phiên: Secure, HttpOnly, SameSite, path và thời gian sống

## 1. Session cookie trong Spring Security Servlet

Trong ứng dụng **Spring Boot 3.x / Spring Security 6.x trên Servlet stack**, đăng nhập bằng form thường dựa vào **HttpSession**. Server giữ trạng thái phiên (có thể gồm `SecurityContext` và `Authentication`); trình duyệt giữ cookie chứa **mã định danh phiên**, mặc định thường là `JSESSIONID` khi dùng embedded Tomcat. Browser tự gửi cookie trong những request phù hợp để server tìm lại session.

~~~text
Browser                              Spring Security + Tomcat
   |                                         |
   | POST /login, credentials + CSRF         |
   |---------------------------------------->|
   |                                         | xác thực người dùng
   |                                         | bảo vệ session fixation
   |                                         | tạo/cập nhật HttpSession
   |<----------------------------------------|
   | Set-Cookie: JSESSIONID=<opaque>;        |
   |             Path=/; Secure;             |
   |             HttpOnly; SameSite=Lax      |
   |                                         |
   | GET /private                            |
   | Cookie: JSESSIONID=<opaque>             |
   |---------------------------------------->|
   |                                         | tìm session còn hiệu lực
   |                                         | áp dụng authorization
   |<----------------------------------------|
   | 200 hoặc redirect/error theo policy     |
~~~

`<opaque>` là một chỗ minh họa, không phải session ID thật. **Session ID là credential nhạy cảm:** ai lấy được ID còn hợp lệ có thể tái sử dụng phiên nếu không có biện pháp giảm thiểu khác. Không in, chia sẻ hoặc ghi lại giá trị thực vào log, URL, issue hay tài liệu.

Điều cần phân biệt:

| Thành phần | Bản chất |
| --- | --- |
| `HttpSession` | Phiên **phía server**, có thời gian sống, invalidate và nơi lưu |
| Cookie `JSESSIONID` | Một mã tham chiếu browser giữ và gửi về để tìm session |
| `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` | Điều kiện browser lưu/gửi/truy cập cookie |
| `Max-Age`, `Expires` | Tuổi thọ cookie ở **browser** |
| `server.servlet.session.timeout` | Thời gian phiên không hoạt động ở **server**, không phải cookie Max-Age |
| Spring Security | Authentication, security context, CSRF, session fixation, authorization và logout |

Mô hình trên dành cho **session authentication**. Nếu API dùng Bearer header hoặc Spring WebFlux, cần xem cơ chế khác; không sao chép cấu hình Servlet và suy luận giống nhau.

## 2. Đọc header Set-Cookie đúng cách

Ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=example-session; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json
~~~

`example-session` chỉ minh họa. Header **`Set-Cookie`** do server gửi là nơi khai báo cookie và thuộc tính. Header **`Cookie`** trong request từ browser thường chỉ có cặp tên/giá trị:

~~~http
GET /private HTTP/1.1
Host: app.example.test
Cookie: JSESSIONID=example-session
~~~

Browser quyết định có gửi dựa trên URL, site/origin, thời hạn và privacy policy. Trên client không phải browser, các chính sách này có thể không được áp dụng giống vậy; vì thế **cookie attributes không thay backend authorization**.

| Thuộc tính | Ý nghĩa | Không nên hiểu nhầm |
| --- | --- | --- |
| `Secure` | Chỉ gửi cookie qua transport an toàn theo browser, thông thường HTTPS | Không tự cài TLS hay mã hóa cookie ở bộ nhớ |
| `HttpOnly` | Chặn JavaScript thông thường đọc cookie qua `document.cookie` | Không vô hiệu hóa XSS hoặc CSRF |
| `SameSite=Strict` | Chặn nhiều trường hợp gửi cookie cross-site | Có thể làm hỏng deep link, SSO/callback |
| `SameSite=Lax` | Cho phép same-site và một số top-level navigation an toàn | Không thay CSRF token; GET vẫn có thể mang cookie |
| `SameSite=None` | Cho phép cross-site trong phạm vi browser policy | Cần `Secure`; third-party cookie vẫn có thể bị chặn |
| `Path` | Giới hạn các request path có thể gửi cookie | Không phải quyền truy cập hay cách ly hai app đáng tin |
| `Domain` | Phạm vi hostname/subdomain | Host-only thường an toàn hơn Domain quá rộng |
| `Max-Age` | Thời gian giữ cookie tương đối, **tính bằng giây** trên wire | Không tự kéo dài HttpSession |
| `Expires` | Thời điểm cookie hết hạn | Chịu ảnh hưởng clock và browser policy |

## 3. Secure: HTTPS và reverse proxy

### 3.1. Secure bảo vệ điều gì?

~~~http
Set-Cookie: JSESSIONID=opaque; Secure; HttpOnly; Path=/
~~~

Khi đặt `Secure`, browser thông thường **không gửi cookie trên HTTP không mã hóa**. Trên website production, yêu cầu TLS/HTTPS và cấu hình Secure là nền tảng giảm nguy cơ lộ mã định danh phiên trên đường truyền.

Nhưng Secure không:
- Tự biến website HTTP thành HTTPS; TLS phải do app/proxy/ingress cung cấp.
- Bảo đảm session ID không bị đánh cắp qua XSS, log, backup hoặc lỗi hạ tầng.
- Mã hóa giá trị cookie trên đĩa hoặc trong bộ nhớ browser.
- Thay HSTS, xử lý mixed content hoặc session fixation protection.
- Có ý nghĩa như cơ chế quyền truy cập cho backend.

Spring Boot 3 cấu hình:

~~~properties
server.servlet.session.cookie.secure=true
~~~

Một số browser có ngoại lệ về Secure cookie với `localhost`, nhưng **không dựa vào ngoại lệ để thiết kế production**. Nếu local HTTP không duy trì được login, hãy dùng local profile riêng, không tắt Secure cho môi trường Internet.

### 3.2. HTTPS ở phía ngoài, HTTP nội bộ

~~~text
Browser --HTTPS--> Ingress / Reverse proxy --HTTP private--> Spring Boot
                       TLS termination                        Tomcat
~~~

Nếu proxy kết thúc TLS, Tomcat có thể nhận request HTTP và không tự biết URL công khai của browser là HTTPS. Khi đó một số URL redirect, tự nhận biết scheme hoặc cookie policy có thể sai.

Một lựa chọn khi đứng sau **proxy được kiểm soát**:

~~~properties
server.forward-headers-strategy=framework
server.servlet.session.cookie.secure=true
~~~

`forward-headers-strategy=framework` **không phải cấu hình bắt buộc** ở mọi deployment. Proxy phải **xóa và đặt lại** các header `Forwarded`/`X-Forwarded-*` của client và backend cần giới hạn truy cập trực tiếp không đáng tin. Nếu tin header do attacker tự gửi, có thể dẫn đến sai scheme/host/redirect.

**Kiểm chứng** ở response công khai: `Set-Cookie` thực sự có `Secure`. Đừng chỉ đọc cấu hình rồi cho là xong.

## 4. HttpOnly: giảm lộ cookie qua JavaScript

~~~http
Set-Cookie: JSESSIONID=opaque; HttpOnly; Secure; Path=/
~~~

`HttpOnly` chặn JavaScript bình thường lấy giá trị cookie qua `document.cookie`:

~~~javascript
console.log(document.cookie);
~~~

Cookie `JSESSIONID` có HttpOnly sẽ không xuất hiện qua API đó. Nhưng một script XSS **vẫn có thể gửi request** tới cùng origin và browser vẫn có thể tự đính kèm HttpOnly cookie, rồi script có thể đọc dữ liệu mà same-origin policy cho phép. Vì thế HttpOnly **không thay** chống XSS, CSP, CSRF, authorization hay kiểm tra dữ liệu đầu vào.

Lưu ý:
- Developer Tools vẫn có thể hiển thị cookie; không có nghĩa JavaScript web đã đọc được nó.
- Nếu mã session ID bị đánh cắp theo cách khác, HttpOnly không tự vô hiệu hóa session.
- Không tắt HttpOnly cho `JSESSIONID` để SPA đọc session ID; frontend thường không cần đọc credential đó.
- Một cookie phục vụ mô hình CSRF token kiểu JavaScript-readable có thể có chính sách khác, nhưng không nên áp dụng chính sách ấy cho cookie phiên.

Property:

~~~properties
server.servlet.session.cookie.http-only=true
~~~

## 5. SameSite: Strict, Lax, None và sự khác biệt với CORS

### 5.1. Site không giống origin

Origin xác định bởi scheme, hostname, port; còn site thường dựa trên scheme và registrable domain (schemeful SameSite). Vì vậy:

~~~text
https://app.example.com -> https://api.example.com
  Khác origin, nhưng có thể cùng site.

https://app.example.com -> https://external.test
  Khác site.

https://app.example.com -> http://app.example.com
  Trong schemeful SameSite có thể được coi là khác site.
~~~

**CORS và SameSite khác nhau**. Cross-origin JavaScript cần CORS cho credentialed requests nếu backend cho phép; nhưng hai origin khác nhau vẫn có thể same-site. CORS không tự phòng CSRF của các HTML form cross-site.

### 5.2. SameSite=Strict

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

Browser có thể không gửi cookie ngay lần người dùng click link từ site khác tới trang đã đăng nhập, khiến app tạm coi user chưa đăng nhập. Một số luồng email deep link, SSO, OIDC/SAML hoặc payment callback có thể bị ảnh hưởng. Strict phù hợp khi app thật sự không cần điều hướng cross-site dùng cookie và đã có test các luồng liên quan.

### 5.3. SameSite=Lax

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser gửi cookie trong request same-site và **một số top-level cross-site navigations dùng phương thức an toàn**, thường là GET khi user nhấn link từ website khác. Cross-site POST thông thường không mang Lax cookie nếu được khai báo tường minh.

**GET không được dùng để gây thay đổi trạng thái có rủi ro**: nếu `GET /delete-account` được dùng để xóa tài khoản, top-level link cross-site vẫn có thể gửi Lax cookie. Cần tuân thủ HTTP safe methods và CSRF token cho thao tác thay đổi trạng thái.

Một số browser có hành vi Lax-by-default khi **thiếu** thuộc tính SameSite, với các ngoại lệ trong một số trường hợp. Điều đó không đồng nghĩa mọi browser luôn xử lý cookie thiếu SameSite giống `SameSite=Lax` khai báo rõ.

### 5.4. SameSite=None

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=None
~~~

Có thể cần cho iframe hoặc integration cross-site. Browser hiện đại yêu cầu `SameSite=None` đi kèm `Secure`; nếu không, cookie có thể bị từ chối. Ngay cả khi có Secure, browser vẫn có thể chặn third-party cookie do tracking prevention, partitioning và privacy controls.

Khi dùng None cho session authentication, **CSRF là yếu tố phải xử lý**; không tắt CSRF chỉ để gửi cookie cross-site. Với credentialed CORS, không dùng wildcard `Access-Control-Allow-Origin: *` để chia sẻ credentials. Chỉ cho phép origin đáng tin, và vẫn phải bảo vệ quyền, CSRF, cookie policy.

### 5.5. Chọn SameSite theo luồng thật

| Use case | Cân nhắc | Điều cần test |
| --- | --- | --- |
| Web session thông thường, user nhấn link từ site khác | `Lax` | CSRF, external links, redirect và login |
| Portal nội bộ không phụ thuộc external navigation | `Strict` | SSO, deep link và email links |
| Ứng dụng nhúng iframe khác site | `None + Secure` | Third-party cookie blocking, CORS, CSRF |
| SPA ở subdomain cùng site, API ở subdomain khác | Có thể dùng `Lax` | Origin, CORS credentials, cookie host/Domain |
| SSO/OIDC/SAML callback | Tùy redirect/binding | GET/POST callbacks và browser behavior |

Spring Boot cấu hình:

~~~properties
server.servlet.session.cookie.same-site=lax
~~~

Các giá trị thường dùng là `strict`, `lax` và `none`. Kiểm tra phiên bản Spring Boot/container và response thật, đặc biệt khi Spring Session có cookie serializer riêng.

## 6. Path và Domain: giới hạn phạm vi, không phải authorization

### 6.1. Path

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Browser thường gửi cookie tới `/portal` và `/portal/profile`, nhưng không gửi tới `/portals` hoặc `/admin`. Cookie Path matching có xét ranh giới dấu `/`, không chỉ là mọi chuỗi bắt đầu bằng `/portal`.

**Path không phải security boundary mạnh**. Không thể dùng `Path=/admin` thay `SecurityFilterChain` hoặc `hasRole("ADMIN")`. Hai app không tin nhau trên cùng host vẫn có các rủi ro cookie, same-origin và shared host khác; nên tách bằng origin/host và backend policy khi cần.

Cấu hình:

~~~properties
server.servlet.session.cookie.path=/
~~~

Với ứng dụng nằm dưới `/portal`, có thể dùng:

~~~properties
server.servlet.context-path=/portal
server.servlet.session.cookie.path=/portal
~~~

Nếu reverse proxy rewrite path, browser chỉ biết public URL, không biết servlet path nội bộ. Cần bảo đảm Path phù hợp URL browser sẽ gọi. Path quá hẹp gây lỗi “đăng nhập xong lại về login”, vì cookie không được gửi vào endpoint cần xác thực.

### 6.2. Domain và host-only cookie

Khi không có `Domain`, cookie thường là **host-only**. Khi có `Domain=example.com`, cookie có thể được gửi cho domain và subdomain hợp lệ. Domain rộng làm tăng phạm vi cookie bị gửi/lộ và không tự tạo shared login giữa các server khác nhau.

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Header này không đặt Domain, phù hợp nếu app chỉ cần host hiện tại. Với các SPA/API khác origin nhưng cùng site, có thể gửi credential tới chính hostname API theo CORS/credential policy mà không cần Domain rộng.

Tiền tố tên cookie `__Host-` là một cách browser enforce hardening khi có Secure, Path=/ và không có Domain; không nên đổi tên cookie session tùy tiện nếu container/proxy/session store chưa được cấu hình đồng bộ.

### 6.3. Xóa cookie phải khớp name/Path/Domain

~~~http
Set-Cookie: JSESSIONID=; Path=/; Max-Age=0; Secure; HttpOnly
~~~

Lệnh xóa cookie cần phạm vi tương thích với cookie đã phát. Nếu cookie gốc `Path=/portal` nhưng logout gửi xóa ở `Path=/`, browser có thể giữ cookie gốc. Các cookie trùng tên nhưng khác Domain/Path có thể cùng tồn tại, làm debug khó.

**Chỉ xóa cookie browser là chưa đủ**: phải invalidate `HttpSession` trên server để session ID bị đánh cắp không còn có thể tái sử dụng.

## 7. Max-Age, Expires và thời gian sống server session

### 7.1. Session cookie của browser

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không có `Max-Age` hay `Expires` nghĩa là browser-session cookie. Browser quản lý thời gian lưu theo chính sách riêng, có thể phục hồi qua restart; đóng một tab không nhất thiết làm cookie biến mất.

### 7.2. Persistent cookie

~~~http
Set-Cookie: JSESSIONID=opaque; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=3600
~~~

`Max-Age=3600` trên HTTP nghĩa là browser lưu khoảng **3600 giây (1 giờ)** kể từ khi nhận. `Expires` là mốc thời gian tuyệt đối, còn Max-Age thường được ưu tiên khi cả hai tồn tại theo cơ chế cookie hiện đại.

**Không đặt Max-Age=0 để tạo browser-session cookie:** Max-Age=0 là chỉ thị xóa. Nếu muốn session cookie, **bỏ hẳn cấu hình max-age**.

Spring Boot property `server.servlet.session.cookie.max-age=1h` dùng cú pháp thời lượng, khác với số giây trong header HTTP. Nhưng kéo dài thời gian lưu cookie **không tự kéo dài thời gian phiên phía server**.

### 7.3. Server HttpSession idle timeout

~~~properties
server.servlet.session.timeout=20m
~~~

Trong cấu hình Servlet container phổ biến, đây là **idle timeout**: phiên hết hạn sau khoảng 20 phút không hoạt động, tùy cơ chế repository/container. Request hợp lệ có thể cập nhật lần truy cập cuối, nên đây **không phải absolute session lifetime**. Nếu yêu cầu phải reauthenticate sau 8 giờ kể từ login bất kể hoạt động, cần áp dụng chính sách absolute expiration riêng.

### 7.4. Hai đồng hồ hoạt động độc lập

~~~text
Cookie: Max-Age = 2h
HttpSession: idle timeout = 20m
Sau 30 phút không hoạt động:
   Browser vẫn có thể gửi cookie chưa hết hạn.
   Server đã hết hạn session -> user không còn logged in.

Cookie: browser-session, không Max-Age
HttpSession: idle timeout = 20m
   Browser vẫn có thể giữ cookie cũ.
   Server vẫn có quyền từ chối session đã hết hạn.

Cookie: Max-Age = 10m
HttpSession: idle timeout = 20m
   Browser có thể ngừng gửi cookie trước server timeout.
   Server vẫn phải cleanup và revoke theo chính sách.
~~~

`Remember-me` trong Spring Security có thể dùng cookie/token riêng để tự login lại khi HttpSession hết hạn; nó có vòng đời và rủi ro riêng, không chỉ là đặt JSESSIONID Max-Age thật dài.

Với **Spring Session Redis/JDBC**, timeout và lưu trữ có thể do `SessionRepository` và `spring.session.timeout` quản lý. Không mặc định property Tomcat `server.servlet.session.timeout` luôn là nguồn hiệu lực cuối cùng.

## 8. Mẫu cấu hình Spring Boot 3 cho từng môi trường

### 8.1. Production HTTPS

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m

# Không đặt cookie.max-age -> browser-session cookie.
# Không đặt cookie.domain nếu chỉ cần host-only cookie.
~~~

Cấu hình này dùng cho ứng dụng session web thông thường tại root context, được phục vụ qua HTTPS. Nếu nhiều app chung host hoặc có Spring Session, điều chỉnh scoping/serializer cho phù hợp. **Không** chỉ copy rồi kết luận mọi SSO/cross-site use case sẽ chạy.

### 8.2. Local HTTP profile chỉ cho thử nghiệm

~~~properties
# src/main/resources/application-local.properties
server.servlet.session.cookie.secure=false
~~~

Chỉ bật profile này trên môi trường local không mang dữ liệu thật. Production phải dùng HTTPS và Secure=true. Giữ SameSite=Lax; không dùng SameSite=None+Secure=false vì nhiều browser sẽ chặn.

### 8.3. Biến thể persistent cookie (không phải mặc định)

~~~properties
server.servlet.session.cookie.max-age=1h
server.servlet.session.timeout=20m
~~~

Nó giữ cookie ở browser tới một giờ nhưng server có thể hết session sau 20 phút idle. Nếu muốn remember-me/revoke/rotation, cần cơ chế phù hợp chứ không chỉ max-age.

### 8.4. Biến thể cross-site (cần threat model)

~~~properties
server.servlet.session.cookie.same-site=none
server.servlet.session.cookie.secure=true
~~~

Chỉ dùng khi browser cần gửi cookie trong cross-site context và ứng dụng đã có CSRF, CORS, HTTPS, third-party browser compatibility được kiểm tra.

## 9. Project Java 17+ runnable: form login và quan sát Set-Cookie

Ví dụ dùng **Spring Boot 3.3.13**, Spring Security 6, Spring MVC, Tomcat embedded và Maven. Nó cố ý tạo HttpSession ở `GET /session-demo` để quan sát cookie; endpoint này **chỉ dùng học tập**, không đưa nguyên trạng lên Internet vì tạo session công khai có thể tiêu thụ tài nguyên.

### 9.1. Cấu trúc file

~~~text
session-cookie-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/sessioncookie/
    │   │   ├── SessionCookieApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       ├── application.properties
    │       └── application-local.properties
    └── test/java/com/example/sessioncookie/
        └── SessionCookieIntegrationTest.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>session-cookie-demo</artifactId>
  <version>1.0.0</version>
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
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
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

**`src/main/java/com/example/sessioncookie/SessionCookieApplication.java`**

~~~java
package com.example.sessioncookie;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCookieApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/sessioncookie/SecurityConfig.java`**

~~~java
package com.example.sessioncookie;

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
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/session-demo", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .invalidateHttpSession(true)
                .deleteCookies("JSESSIONID"))
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}
~~~

`formLogin` mặc định cung cấp trang login, cần CSRF token trong POST. `logout` được cấu hình invalidate HttpSession và gửi chỉ dẫn xóa JSESSIONID phù hợp với path root của demo; nếu đổi context path/Domain hoặc dùng Spring Session, cần xem lại việc xóa cookie.

**`src/main/java/com/example/sessioncookie/DemoController.java`**

~~~java
package com.example.sessioncookie;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/session-demo")
    public Map<String, String> createSession(HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute("demo", "created");
        // Không đưa session.getId() vào response: session ID là secret.
        return Map.of("status", "session-created");
    }

    @GetMapping("/private")
    public Map<String, String> privatePage(Authentication authentication) {
        return Map.of("user", authentication.getName());
    }
}
~~~

**`src/main/resources/application.properties`**

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.path=/
server.servlet.session.timeout=20m

# KHÔNG đặt server.servlet.session.cookie.max-age.
~~~

**`src/main/resources/application-local.properties`**

~~~properties
# Chỉ chạy local HTTP, không deploy production.
server.servlet.session.cookie.secure=false
~~~

### 9.2. Integration test quan sát Set-Cookie từ embedded Tomcat

**`src/test/java/com/example/sessioncookie/SessionCookieIntegrationTest.java`**

~~~java
package com.example.sessioncookie;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionCookieIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Test
    void sessionCookieHasExpectedFlags() {
        ResponseEntity<String> response = rest.getForEntity(
            "http://localhost:" + port + "/session-demo", String.class
        );

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();

        String setCookie = response.getHeaders()
            .getFirst(HttpHeaders.SET_COOKIE);
        assertThat(setCookie).isNotBlank();

        String lower = setCookie.toLowerCase(Locale.ROOT);
        assertThat(lower).contains("jsessionid=");
        assertThat(lower).contains("; path=/");
        assertThat(lower).contains("; secure");
        assertThat(lower).contains("; httponly");
        assertThat(lower).contains("; samesite=lax");

        // Browser-session cookie, không Max-Age/Expires.
        assertThat(lower).doesNotContain("max-age=");
        assertThat(lower).doesNotContain("expires=");
    }
}
~~~

Test này dùng **server HTTP thật và đọc response header**; nó không kiểm tra browser có nhận và gửi Secure cookie trên HTTP hay không. `secure=true` cố ý gắn thuộc tính Secure trong Set-Cookie dù embedded test chạy HTTP. Để kiểm tra hành vi browser thật, dùng HTTPS hoặc local profile. Nếu CI kích hoạt profile `local`, assertion Secure flag sẽ khác, nên test mặc định không kích hoạt profile đó.

### 9.3. Chạy Maven và xem kết quả

Cần Java 17+, Maven và khả năng tải dependencies:

~~~bash
mvn test
mvn spring-boot:run
~~~

**Kết quả kỳ vọng:** test pass nếu project được tạo đầy đủ và môi trường phù hợp. Mã trong tài liệu **chưa được Maven chạy thực tế ở đây**.

Khi server chạy, dùng:

~~~bash
curl -i http://localhost:8080/session-demo
~~~

Response kỳ vọng:

~~~http
HTTP/1.1 200
Set-Cookie: JSESSIONID=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json

{"status":"session-created"}
~~~

Thứ tự cookie attributes và các header khác có thể khác, nên test kiểm tra sự tồn tại flag thay vì nguyên văn toàn header.

Để login thủ công bằng browser ở **local HTTP**, chạy profile local:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
~~~

PowerShell có thể cần quote đối số `"-Dspring-boot.run.profiles=local"`. Vào `http://localhost:8080/login` với user demo `alice` / `demo-pass` rồi mở `/private`. Local profile có Secure=false chỉ cho môi trường học tập; production yêu cầu HTTPS và Secure=true.

## 10. Kiểm tra và gỡ lỗi trong browser

Trong **Network** của DevTools, xem response `Set-Cookie`. Trong **Application/Storage → Cookies**, xem cookie có được browser nhận hay không và thuộc tính thực tế của nó. Ở request kế tiếp, xem có header `Cookie` phù hợp với URL, scheme, site và Path.

Các bước chẩn đoán:

1. Server đã phát `Set-Cookie` đúng tên và thuộc tính chưa?
2. Browser có thông báo từ chối cookie (Secure trên HTTP, SameSite=None thiếu Secure, third-party blocking) không?
3. Cookie được lưu có đúng Domain/Path để gửi đến endpoint không?
4. Browser có gửi cookie ở request tiếp theo không? Nếu có mà vẫn anonymous, kiểm tra `HttpSession` phía server.
5. Session bị invalidated, timeout, hoặc đang ở node khác khi load balancer phân phối request không?
6. Sau logout, mã session cũ có còn được server chấp nhận không?
7. Nếu có SSO/iframe, kiểm tra toàn bộ redirect/callback chain, không chỉ request đầu tiên.

Dùng `curl -c cookies.txt` có thể ghi cookie jar chứa **session ID thật** vào file. Chỉ dùng trên môi trường test và không chia sẻ/commit file đó. `curl` không mô phỏng đầy đủ SameSite/third-party behavior của browser.

### Tình huống phổ biến

| Hiện tượng | Nguyên nhân nghi vấn |
| --- | --- |
| Login trả 302 nhưng browser không lưu cookie | HTTPS/Secure mismatch, browser chặn cookie |
| Cookie lưu nhưng không gửi tới `/portal` | Path/Domain/host không khớp |
| Cookie có gửi mà user mất login | Server session đã expired, repo/store khác node, context chưa persist |
| Chạy local ổn, reverse proxy lỗi | Scheme/forwarded headers hoặc path rewrite |
| Click link từ email không vào được trang login sẵn có | SameSite=Strict trên cross-site navigation |
| Iframe cross-site không giữ login | SameSite Lax/Strict hoặc third-party restrictions |
| Browser còn cookie sau idle timeout | Browser cookie lifetime và HttpSession TTL khác nhau |
| Logout vẫn vào được bằng ID cũ | Server chưa invalidate session, hoặc có remember-me/token khác |

## 11. Phối hợp với Spring Security: fixation, CSRF, logout

**Session fixation protection:** Nếu attacker khiến browser dùng một session ID được biết trước, việc giữ nguyên ID sau login có thể nguy hiểm. Spring Security session authentication thường bảo vệ bằng cách thay session ID khi login, tùy cơ chế; custom login cần xử lý `SessionAuthenticationStrategy` và lưu security context đúng.

~~~text
Trước login: JSESSIONID=A (chưa authenticated)
Sau login:  JSESSIONID=B (đã authenticated, ID được đổi)
~~~

Đó là minh họa chính sách bảo vệ, không phải cam kết mọi loại authentication luôn thay ID.

**CSRF:** Cookie session do browser tự gửi. SameSite=Lax hỗ trợ giảm nguy cơ CSRF nhưng **không thay CSRF tokens**, nhất là khi GET được phép trong một số điều hướng cross-site hoặc có thay đổi browser policy. Spring Security Servlet thường bật CSRF mặc định; đừng tắt vì endpoint trả JSON nếu auth vẫn dựa vào session cookie.

**Logout:** Cần invalidate HttpSession ở server, xóa security context, gửi cookie deletion đúng Path/Domain và xem xét remember-me/SSO/refresh token khác. Xóa cookie ở browser mà không invalidate session ở server không ngăn replay mã định danh đã bị đánh cắp.

**Cross-site API:** Không tùy tiện tắt CSRF vì API là REST. Nếu browser gửi cookie tự động để xác thực, CSRF cần được đánh giá riêng. CORS, SameSite và CSRF có vai trò khác nhau.

## 12. Spring Session và nhiều máy chủ

Với Tomcat mặc định, HttpSession thường lưu trên một instance. Nếu load balancer chuyển request tới node không biết session, user có thể bị đưa về login dù cookie còn nguyên. Dùng **Spring Session Redis/JDBC** hoặc một cơ chế shared session store có thể giải quyết quản lý phiên đa instance, nhưng phải cấu hình TTL, security, cookie serializer và logout đồng bộ.

Spring Session có thể dùng tên cookie **`SESSION`** thay vì `JSESSIONID`. Khi đó đừng cứng hóa test/middleware theo tên cookie mặc định của Tomcat. Kiểm tra `spring.session.timeout`, session repository, cookie name, SameSite/Secure/HttpOnly/Path/Domain và cookie deletion thực tế; các property `server.servlet.session.cookie.*` có thể không còn là nguồn kiểm soát duy nhất.

Trên proxy có TLS termination, backend phải tin Forwarded headers **chỉ từ nguồn đáng tin cậy**. Khi thay context path hoặc domain, kiểm tra cả public URL và phạm vi cookie; đừng chỉ điều chỉnh rule Spring Security.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| Secure mã hóa cookie lưu trong máy người dùng | Secure kiểm soát gửi cookie qua HTTPS/transport phù hợp |
| HttpOnly làm ứng dụng miễn nhiễm XSS/CSRF | Chỉ chặn JS thông thường đọc cookie trực tiếp |
| Strict luôn tốt hơn Lax | Strict có thể hỏng deep links và SSO |
| Lax thay token CSRF | Không: top-level GET và nhiều tình huống khác vẫn cần CSRF protection |
| None chắc chắn làm iframe login được | Cần Secure; browser có thể chặn third-party cookie |
| Path là lớp phân quyền | Path chỉ lọc nơi browser gửi cookie |
| Domain rộng tự tạo SSO | Shared cookie không có nghĩa shared session server-side |
| Không Max-Age nghĩa là đóng tab xóa cookie | Browser-session có thể sống qua session restore |
| Max-Age=0 nghĩa là không hết hạn | Nó thường là chỉ dẫn xóa cookie |
| Session timeout=20m nghĩa browser xóa cookie sau 20m | Đây là timeout server-side idle |
| Xóa cookie đủ để logout | Phải invalidate session phía server |
| Spring Session luôn dùng JSESSIONID | Tên/serializer có thể khác |
| HTTPS proxy luôn tự khiến cookie Secure đúng | Cần cấu hình và test actual Set-Cookie |

## 14. Checklist triển khai

1. Bật HTTPS trên production, `Secure=true` và `HttpOnly=true` cho session cookie.
2. Chọn `SameSite` theo flow: web login cơ bản có thể dùng Lax; test SSO/iframe/cross-site callbacks.
3. Giữ cookie host-only khi không cần domain rộng, chọn `Path` phù hợp public URL.
4. Không đặt Max-Age=0 để tạo browser-session cookie; bỏ Max-Age/Expires nếu muốn cookie theo phiên browser.
5. Xác định server idle timeout và, nếu cần, absolute session lifetime riêng.
6. Giữ CSRF protection cho cookie-based auth, chống XSS và bảo vệ authorization.
7. Chống session fixation khi login, invalidate server session khi logout và xóa cookie đúng scope.
8. Nếu có Spring Session/multi-node, kiểm tra repository/TTL/cookie serializer/rotation.
9. Kiểm tra trên browser thực, không chỉ qua curl hoặc file properties.
10. Không log hoặc chia sẻ session ID; khi nghi mất cookie/session cần revoke rồi điều tra.

## 15. Câu hỏi tự kiểm tra

**1.** `Secure` làm được gì và có thay HTTPS không?

**Đáp:** Secure hạn chế gửi cookie qua kết nối không an toàn theo browser. Nó không tự tạo HTTPS và không bảo vệ cookie đã bị đánh cắp từ nơi khác.

**2.** Vì sao HttpOnly không phòng mọi CSRF/XSS?

**Đáp:** Nó chặn JavaScript đọc cookie trực tiếp, nhưng browser vẫn có thể tự gửi cookie; script XSS vẫn có thể phát request trong origin.

**3.** SameSite Strict và Lax khác nhau ra sao khi user nhấn link từ một site khác?

**Đáp:** Strict thường không gửi cookie trong điều hướng cross-site ban đầu; Lax có thể gửi trong top-level navigation an toàn như GET.

**4.** Vì sao SameSite=None có thể bị browser từ chối?

**Đáp:** Browser hiện đại yêu cầu Secure, nhưng third-party/privacy restrictions vẫn có thể chặn.

**5.** `Path=/portal` có làm `/portal/admin` tự yêu cầu ROLE_ADMIN không?

**Đáp:** Không. Path chỉ chọn URL gửi cookie, authorization là việc của Spring Security/server.

**6.** `server.servlet.session.timeout=20m` có bắt browser xóa JSESSIONID sau đúng 20 phút không?

**Đáp:** Không. Nó là server idle timeout; browser cookie có lifecycle riêng.

**7.** Vì sao Max-Age=0 không nên dùng để “tạo cookie chỉ sống trong phiên trình duyệt”?

**Đáp:** Max-Age=0 thường chỉ thị browser xóa cookie ngay. Muốn session cookie thì bỏ Max-Age/Expires.

**8.** Sau logout, client xóa JSESSIONID nhưng server không invalidate session. Đã an toàn chưa?

**Đáp:** Chưa. Một session ID cũ đã lộ có thể tiếp tục được dùng; phải revoke/invalidate server-side.

**9.** Với Spring Session Redis, tên cookie chắc chắn là JSESSIONID không?

**Đáp:** Không. Cookie name, serializer, TTL và property điều khiển có thể khác; phải kiểm tra Set-Cookie và repository thực.

**10.** Vì sao app chạy sau HTTPS reverse proxy vẫn có thể phát cookie sai?

**Đáp:** Backend có thể nhìn scheme nội bộ HTTP; cần chính sách Secure rõ ràng và xử lý forwarded headers từ proxy tin cậy.

**Ghi nhớ:** **`Secure` kiểm soát transport, `HttpOnly` giới hạn JavaScript đọc cookie, `SameSite` kiểm soát cross-site sending, `Path`/`Domain` giới hạn phạm vi, còn `Max-Age`/`Expires` quyết định tuổi thọ cookie ở browser. `HttpSession` có idle timeout và invalidate riêng ở server.**