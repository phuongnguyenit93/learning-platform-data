# Phiên tại ứng dụng, phiên tại IdP và trải nghiệm đăng nhập một lần (SSO)

Trong hệ thống đăng nhập liên kết (federation), người dùng có thể đăng nhập vào ứng dụng A rồi mở ứng dụng B mà không phải nhập lại mật khẩu. Trải nghiệm này gọi là **Single Sign-On (SSO)**. Tuy nhiên, **SSO không có nghĩa các ứng dụng dùng chung một phiên**: mỗi ứng dụng duy trì phiên riêng, còn nhà cung cấp định danh (Identity Provider – IdP) quản lý phiên xác thực của chính IdP.

Bài học áp dụng cho **Spring Security Servlet** với ví dụ **Spring Boot 3.x / Spring Security 6.x, Java 17+, OpenID Connect (OIDC)**. Sự khác biệt giữa các phiên cũng áp dụng cho nhiều nền tảng web khác.

## 1. Ba lớp cần phân biệt

| Khái niệm | Chủ sở hữu | Browser gửi gì? | Vai trò |
| --- | --- | --- | --- |
| **Phiên ứng dụng (local/RP session)** | Mỗi ứng dụng A, B | Cookie phiên của miền ứng dụng đó, thường là **JSESSIONID** | Giữ Authentication/SecurityContext và trạng thái đăng nhập cục bộ. |
| **Phiên IdP (IdP/OP session)** | Nhà cung cấp định danh | Cookie đăng nhập thuộc miền IdP, tên do IdP quy định | Giúp IdP biết người dùng đã xác thực trước đó khi trình duyệt quay lại. |
| **SSO** | Trải nghiệm phối hợp qua các lần chuyển hướng tới IdP | Trình duyệt có thể gửi cookie IdP khi ở miền IdP | B có thể hoàn tất luồng đăng nhập mới mà người dùng không phải nhập lại thông tin đăng nhập. |

**Relying Party (RP)** là ứng dụng nhận kết quả xác thực từ IdP; **OpenID Provider (OP)** là vai trò OIDC của IdP. A và B có thể tin cậy cùng OP mà vẫn có cookie, session ID, timeout, phân quyền và thao tác logout riêng. Trình duyệt không gửi cookie A cho B nếu khác miền; cookie IdP cũng không trở thành cookie phiên A/B.

Ba sai lầm thường gặp: “cùng IdP nghĩa là chung JSESSIONID”, “SSO nghĩa là cùng access token” và “logout một ứng dụng tự động logout toàn hệ thống”. Không điều nào được bảo đảm chỉ bằng cách bật OIDC login.

### Phân biệt session với các token OIDC/OAuth2

- **Session ID** là định danh bí mật giúp server ứng dụng tìm trạng thái phiên; tên cookie hay gặp là JSESSIONID, nhưng có thể đổi.
- **ID token** là kết quả OIDC mô tả danh tính cho một client cụ thể; cần xác minh issuer, audience, hạn dùng, nonce và các điều kiện của giao thức.
- **Access token** được cấp cho việc truy cập API/resource theo audience/scope của nó; không phải cookie phiên ứng dụng và không tự tạo SSO.
- **Refresh token** (khi được cấp) giúp xin access token mới theo chính sách; có refresh token không chứng minh cookie IdP còn hợp lệ.

IdP session, local session và token đều có vòng đời khác nhau. Một ID token hết hạn không mặc nhiên xóa local session đã được tạo; local session còn sống không chứng minh IdP session vẫn còn. Cách Spring lưu authorized client/token tùy repository/service và kiến trúc: không được giả định mọi token luôn nằm trong HttpSession.

## 2. Luồng đăng nhập liên kết qua hai ứng dụng

Giả sử A và B là hai ứng dụng web, cùng tin cậy IdP I; mỗi ứng dụng có OIDC client registration và redirect URI hợp lệ.

1. Người dùng truy cập trang bảo vệ của **A** khi chưa có phiên A. Spring Security bắt đầu **oauth2Login()**, chuyển hướng trình duyệt đến authorization endpoint của I.
2. Trình duyệt đến **miền I**, mang cookie IdP nếu có. Khi chưa có phiên IdP hoặc chính sách yêu cầu, I hiển thị đăng nhập/MFA rồi duy trì phiên IdP theo cấu hình của nó.
3. I chuyển trình duyệt về callback của A với authorization code. A kiểm tra **state**, đổi code lấy token qua kênh server; kết quả OIDC được kiểm tra theo protocol (gồm ID token, issuer, audience, nonce khi áp dụng). **PKCE** hỗ trợ bảo vệ authorization code flow, đặc biệt cần thiết cho public client và được khuyến nghị ở các cấu hình phù hợp.
4. A tạo Authentication trong SecurityContext và, theo mô hình **stateful** mặc định của ứng dụng Servlet, duy trì phiên local; trình duyệt nhận cookie phiên của A.
5. Người dùng mở trang bảo vệ ở **B**. Vì B không đọc cookie/session A, B vẫn tạo một **yêu cầu OIDC mới** và chuyển hướng tới I.
6. Trình duyệt đi tới miền I với cookie IdP hiện có. Nếu I chấp nhận phiên còn hoạt động, không yêu cầu xác thực lại, I hoàn tất authorization flow cho B mà không hiện màn hình nhập mật khẩu.
7. B xác minh kết quả và tạo **phiên B độc lập**. Người dùng cảm nhận “đăng nhập một lần”, trong khi hệ thống có một phiên IdP và hai phiên local khác nhau.

Sơ đồ đơn giản:

~~~text
Browser ── trang bảo vệ ──> A
Browser <── redirect OIDC ── A
Browser ── yêu cầu OIDC ─> IdP ── có thể yêu cầu login/MFA
Browser <── code/redirect ─ IdP
A ── đổi code, kiểm tra token ──> IdP
A ── tạo session A ──> Browser

Browser ── trang bảo vệ ──> B
Browser <── redirect OIDC ── B
Browser ── cookie IdP ──> IdP ── có thể dùng phiên IdP cũ
Browser <── code/redirect ─ IdP
B ── đổi code, kiểm tra token ──> IdP
B ── tạo session B ──> Browser
~~~

**B hỏi IdP để xác thực người dùng, không hỏi A để lấy phiên A.** Phiên IdP giúp lần xác thực thứ hai dễ hơn; RP vẫn phải tạo và kiểm soát phiên của chính mình.

### Khi nào IdP vẫn yêu cầu nhập lại mật khẩu?

SSO phụ thuộc phiên IdP còn hiệu lực, cùng profile trình duyệt có cookie IdP, chính sách đăng nhập, yêu cầu MFA/consent, mức độ tin cậy của lần xác thực và tham số OIDC. **prompt=login** hoặc **max_age** có thể buộc reauthentication dù IdP có phiên. Trình duyệt ẩn danh, trình duyệt khác hoặc thiết bị khác thường không chia sẻ cookie IdP từ profile ban đầu.

Không nhầm trải nghiệm SSO bằng **top-level redirect** với cơ chế **silent authentication trong iframe**: cookie bên thứ ba trong iframe thường chịu thêm hạn chế bảo mật/trình duyệt. Không thể cam kết “không thấy màn hình IdP” trong mọi trường hợp.

## 3. Phiên ứng dụng và phiên IdP hết hạn độc lập

| Trạng thái | Điều thường xảy ra |
| --- | --- |
| A session còn sống, IdP session còn sống | Request mới vào A được phục vụ nhờ local session, không nhất thiết cần truy cập IdP. |
| A session hết hạn, IdP session còn sống | A redirect tới IdP, IdP có thể xác thực không cần hỏi mật khẩu rồi A tạo phiên mới. |
| A session còn sống, IdP session hết hạn | A thường vẫn phục vụ tới khi local session hết hạn hoặc có cơ chế vô hiệu hóa/kiểm tra bổ sung. |
| Cả A session và IdP session đều hết hạn | Lần truy cập tài nguyên bảo vệ tiếp theo thường yêu cầu đăng nhập lại tại IdP. |
| User logout local ở A, B session vẫn còn | B thường vẫn đăng nhập; IdP session có thể vẫn tồn tại. |
| User logout tại IdP, local session A/B còn sống | A/B thường không tự hủy phiên nếu không có Single Logout hoặc cơ chế đồng bộ phiên. |

Ví dụ: A dùng timeout **20 phút không hoạt động**, IdP cho phép phiên SSO **8 giờ**. Sau 30 phút không dùng A, khi mở lại, A có thể redirect tới IdP. Nếu IdP session còn hợp lệ, người dùng không nhập mật khẩu; tuy nhiên A có thể vừa **tạo một phiên mới**, không phải hồi sinh session A cũ.

Cần phân biệt **idle timeout** (hết hạn do không hoạt động) với **absolute lifetime** (thời gian tối đa tuyệt đối). “Remember me”, chính sách MFA và refresh token có thể thay đổi trải nghiệm nhưng không làm các phiên trở thành một thực thể. Local session và IdP session có thể bị hủy độc lập tại những thời điểm khác nhau.

## 4. Spring Security quản lý phiên local như thế nào?

Trong **Spring Security Servlet** stateful, security filter chain khôi phục SecurityContext cho request tương ứng với phiên local; Authentication mô tả principal đã xác thực. **oauth2Login()** xử lý đăng nhập qua OAuth2/OIDC, còn SecurityContextRepository và session policy quyết định cách trạng thái local được lưu giữa các request.

- Cookie JSESSIONID là tên mặc định thông dụng của Servlet session; ứng dụng có thể đổi tên và chính sách cookie. Cookie thuộc miền/path tương ứng, không dùng để chia sẻ phiên giữa RP độc lập.
- Spring Security hỗ trợ chống **session fixation** khi đăng nhập theo mô hình stateful; việc xoay session ID phụ thuộc cấu hình và servlet container.
- **SessionCreationPolicy.STATELESS** làm việc theo mô hình khác, thường dùng cho API Resource Server kiểm tra Bearer token trên mỗi request. Không suy ra API stateless có phiên web kiểu trên.
- **OAuth2 Login** và **OAuth2 Resource Server** là hai vai trò khác nhau. Ứng dụng có thể dùng cả hai nếu cần, nhưng access token cho API không thay thế session IdP.

### Ví dụ chạy được với Spring Boot 3.3.5 + Java 17

Điều kiện: có OpenID Provider hỗ trợ discovery; đăng ký **confidential web client** tên **demo**, nhận client ID/secret và cho phép redirect URI **http://localhost:8080/login/oauth2/code/demo**. Thay **issuer-uri** mẫu bằng issuer thực tế của OP. Đặt các file dưới đúng thư mục package sau.

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>federation-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
            <artifactId>spring-boot-starter-oauth2-client</artifactId>
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

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope:
              - openid
              - profile
              - email
        provider:
          demo:
            issuer-uri: https://idp.example.com/realms/demo
server:
  servlet:
    session:
      timeout: 30m
~~~

**src/main/java/com/example/federation/FederationDemoApplication.java**

~~~java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/federation/SecurityConfig.java**

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

**src/main/java/com/example/federation/DemoController.java**

~~~java
package com.example.federation;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/")
    public String publicPage() {
        return "Trang cong khai";
    }

    @GetMapping("/me")
    public String me(@AuthenticationPrincipal OidcUser user) {
        return "Hello, " + user.getSubject();
    }
}
~~~

Thiết lập hai biến môi trường **OIDC_CLIENT_ID** và **OIDC_CLIENT_SECRET** từ ứng dụng đã đăng ký, cấu hình issuer thật và chạy:

~~~bash
mvn spring-boot:run
~~~

- **GET http://localhost:8080/** trả chính xác văn bản **Trang cong khai**.
- **GET http://localhost:8080/me** trước khi có session sẽ redirect vào quy trình OIDC; sau đăng nhập, endpoint trả chuỗi dạng **Hello, <subject OP cung cấp>**. Subject phụ thuộc tài khoản, nên không thể đưa một output cố định.
- Spring Security dùng điểm khởi đầu đăng nhập **/oauth2/authorization/demo** và callback **/login/oauth2/code/demo** theo mặc định. Chỉ khi có IdP/registration hợp lệ mới hoàn tất được đăng nhập.

Đoạn Java là ứng dụng đầy đủ có thể biên dịch khi dependencies được tải; địa chỉ issuer mẫu phải đổi thành OP thật. HTTP localhost phục vụ thử nghiệm; production phải sử dụng HTTPS/cookie an toàn. Không commit client secret vào mã nguồn.

### Tại sao ứng dụng vẫn cần session sau callback?

Callback OIDC chứng minh người dùng đã được IdP xác thực khi hoàn thành flow. Để tránh redirect toàn bộ OIDC cho mỗi request web, ứng dụng thường giữ Authentication trong local session. Chính ứng dụng quyết định thời gian sống, hạn truy cập và cách vô hiệu hóa session của mình. Nếu triển khai nhiều instance, cần kiến trúc đảm bảo instance xử lý request tìm được session (ví dụ lưu trữ phiên chung bằng Spring Session) hoặc chiến lược định tuyến phù hợp.

## 5. Logout ứng dụng, logout IdP và Single Logout

### Logout local

Ở cấu hình cơ bản trên, Spring Security thực hiện **local logout**: xóa trạng thái xác thực, vô hiệu hóa HttpSession theo cấu hình. Với CSRF mặc định bật, logout thường được gửi bằng **POST /logout** kèm CSRF token hợp lệ; GET /logout có thể hiển thị trang xác nhận. **Không dùng GET như request thay đổi trạng thái**, và không tắt CSRF chỉ để logout dễ gọi.

Local logout A **không buộc** IdP hoặc B kết thúc phiên. Khi mở lại A ngay sau logout local, A có thể redirect tới IdP và đăng nhập lại tự động nhờ cookie IdP vẫn còn. Đây không nhất thiết là lỗi logout; có thể A logout đúng nhưng SSO đưa user vào phiên A mới.

### RP-Initiated Logout tại OP

Nếu OP hỗ trợ OIDC **end_session_endpoint**, RP có thể chuyển hướng browser tới endpoint đó sau logout để yêu cầu kết thúc phiên IdP. Với Spring Security Servlet, có thể thay **toàn bộ** SecurityConfig ở ví dụ bằng:

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        var oidcLogout = new OidcClientInitiatedLogoutSuccessHandler(registrations);
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/");

        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout.logoutSuccessHandler(oidcLogout));
        return http.build();
    }
}
~~~

Chỉ dùng **một** trong hai SecurityConfig, không khai báo bean giống nhau hai lần. OP phải công bố và hỗ trợ logout endpoint, chấp nhận client/redirect URI phù hợp. Handler này phối hợp logout tại OP khi được hỗ trợ; việc IdP hết phiên **vẫn không bảo đảm** local session ở mọi RP khác biến mất ngay.

### Single Logout (SLO) là tính năng riêng

- **Front-channel logout:** thông báo qua trình duyệt/điều hướng hoặc iframe giữa IdP và RP; phụ thuộc trình duyệt, cookie, cách các bên triển khai.
- **Back-channel logout:** IdP gửi logout message server-to-server; RP xác minh message và ánh xạ subject/session identifier để hủy đúng local session. Phụ thuộc khả năng hỗ trợ của OP, RP và phiên bản framework.
- **Token revocation:** thu hồi token không tự động xóa mọi HttpSession. Một API có thể từ chối token, trong khi ứng dụng giao diện vẫn còn local session.
- **Thiết bị khác nhau:** logout một browser session không đồng nghĩa logout mọi thiết bị.

Yêu cầu nghiệp vụ “Logout tất cả ứng dụng ngay lập tức” phải chỉ ra hệ thống nào tham gia, độ trễ cho phép và cách đồng bộ/hủy phiên; **oauth2Login() một mình không đáp ứng yêu cầu đó**.

## 6. Các điểm bảo mật và vận hành

**Thời hạn phiên:** thiết kế idle timeout và absolute lifetime riêng cho app và IdP. Một phiên ứng dụng dài có thể duy trì truy cập sau khi IdP hết phiên; một phiên ứng dụng ngắn cùng IdP session dài thường dẫn tới redirect đăng nhập nhanh nhưng tạo local session mới.

**Cookie và HTTPS:** giới hạn Domain/Path đúng, đặt **Secure** khi dùng HTTPS, **HttpOnly**, và **SameSite** phù hợp flow. IdP kiểm soát cookie IdP; ứng dụng không đọc hay tự chia sẻ cookie ấy. Đằng sau reverse proxy, forwarded headers, scheme/host và cookie cần đúng để redirect URI/callback ổn định. Không log session ID, authorization code hoặc token.

**Xác minh OIDC:** bảo đảm state, nonce, ID token, issuer, audience, redirect URI và PKCE theo giao thức/cấu hình. Không tự bỏ bước xác minh chữ ký hoặc tin tưởng dữ liệu browser. Hạn chế redirect URI tại IdP về danh sách cho phép.

**CSRF:** app dựa trên cookie local vẫn cần bảo vệ CSRF cho thao tác thay đổi trạng thái. OIDC login có cơ chế state riêng nhưng không thay thế CSRF protection của mọi form/action nội bộ.

**Phân quyền:** SSO chỉ giải quyết xác thực người dùng. A và B vẫn phải kiểm tra authorization riêng cho URL/tác vụ và không coi một scope/claim được cấp là quyền truy cập vô điều kiện.

**MFA/step-up:** IdP có thể buộc MFA hay reauthentication theo prompt/max_age/acr/auth_time khi nghiệp vụ cần. Việc user đang có phiên local không chứng minh họ vừa xác thực lại đủ mới cho thao tác rủi ro cao.

**Thay đổi quyền/khóa tài khoản:** Authentication hoặc role/claim trong local session có thể cũ sau khi IdP đổi trạng thái tài khoản. Hãy cân nhắc vòng đời session, tra cứu quyền theo request, session revocation hoặc SLO tùy yêu cầu bảo mật.

**Cụm server:** nếu quản lý phiên local ở server, nhiều instance cần cùng truy cập được dữ liệu session hoặc có định tuyến phù hợp. Không đổ lỗi cho IdP khi A mất session giữa hai request vì vấn đề load balancer/session store.

## 7. Kịch bản kiểm chứng với A, B và trình duyệt

Đăng ký hai OIDC client A và B dùng chung một IdP, có redirect URI riêng; bật DevTools để theo dõi Network và cookie theo đúng origin.

1. **Browser profile mới:** vào A. Quan sát redirect qua IdP, nhập thông tin đăng nhập và browser được cấp local cookie A sau callback.
2. **Mở B trong cùng profile:** B vẫn redirect tới IdP. Nếu cookie IdP phù hợp, user không nhập lại mật khẩu; browser nhận local cookie B khác A.
3. **Làm hết hạn session A, giữ session IdP:** truy cập lại A; quan sát một vòng redirect và một session A mới, thường không phải nhập lại mật khẩu.
4. **Logout A local:** gửi POST /logout với CSRF hợp lệ; B vẫn thường đăng nhập. Nếu vào lại A mà được đăng nhập ngay, kiểm tra IdP session còn hay không.
5. **Logout IdP:** kiểm tra một flow mới tới IdP có yêu cầu nhập lại mật khẩu hay không. Đồng thời quan sát A đang có local session: A có thể vẫn hoạt động nếu không cấu hình cơ chế SLO.
6. **Profile ẩn danh:** thường không có cookie IdP của profile cũ; không được suy ra người dùng sẽ SSO xuyên profile hoặc thiết bị.
7. **Chính sách xác thực mới:** thử prompt=login/max_age hoặc yêu cầu MFA của IdP để hiểu vì sao “đã SSO” vẫn có thể cần xác thực lại.

Quan sát **Network** cho authorization redirect/callback/status và **Application/Storage → Cookies** cho từng domain. Không chia sẻ giá trị cookie, token, code hoặc client secret trong log, screenshot hay ticket.

### Tình huống chẩn đoán

| Triệu chứng | Điều cần kiểm tra |
| --- | --- |
| Logout A rồi vào A lại ngay không cần nhập mật khẩu | A đã hủy local session chưa? IdP cookie vẫn sống? Đã dùng RP-initiated logout thật sự chưa? |
| Login A xong mà B vẫn hỏi mật khẩu | B có cùng IdP/tenant? Phiên IdP còn không? Có prompt/max_age/MFA/consent, profile hay chính sách cookie khác? |
| Logout IdP nhưng A vẫn hoạt động | Local session A độc lập; đã triển khai SLO/back-channel logout và ánh xạ phiên chưa? |
| Lặp redirect hoặc state mismatch | Cookie A có mất giữa redirect/callback? HTTPS, SameSite, reverse proxy, load balancer, redirect URI, đồng hồ có đúng? |
| Invalid issuer, audience hay redirect_uri | Discovery issuer, registration client và redirect URI thực tế có khớp tuyệt đối không? |
| API vẫn chấp nhận Bearer token sau browser logout | Token còn thời hạn không? API có kiểm tra revocation/introspection hoặc chỉ chữ ký + exp? Logout browser có thiết kế liên quan đến token/API không? |

## 8. Câu hỏi tự kiểm tra

**1. A vẫn còn phiên local, IdP hết phiên. A có lập tức từ chối người dùng không?**  
Không mặc nhiên. A có thể tiếp tục chấp nhận local session đến khi nó hết hạn/bị vô hiệu hoặc có cơ chế kiểm tra bổ sung.

**2. B không biết JSESSIONID của A, vì sao user không nhập lại mật khẩu ở B?**  
B yêu cầu IdP xác thực qua một flow mới. Tại miền IdP, browser gửi cookie phiên IdP, cho phép IdP nhận biết lần đăng nhập trước nếu chính sách cho phép.

**3. POST /logout tại A thành công thì B có logout theo không?**  
Thường không. Local logout, logout phiên IdP và Single Logout nhiều RP là các thao tác với phạm vi khác nhau.

**4. Dùng chung access token giữa các ứng dụng có phải là SSO không?**  
Không. Access token có audience/scope/mục đích riêng; SSO OIDC là trải nghiệm do quy trình xác thực lại qua IdP và phiên IdP đem lại.

## 9. Ghi nhớ

- **Một người dùng có thể có nhiều phiên ứng dụng độc lập và một phiên IdP hỗ trợ đăng nhập cho từng ứng dụng.**
- **SSO là trải nghiệm tránh nhập lại thông tin đăng nhập khi IdP cho phép, không phải chia sẻ JSESSIONID.**
- **Hết phiên ứng dụng, hết phiên IdP và hết hạn token là ba sự kiện khác nhau.**
- **Logout local, RP-initiated logout và Single Logout phải được chọn, cấu hình và kiểm thử theo phạm vi mong muốn.**
- Spring Security cung cấp **oauth2Login()**, còn ứng dụng vẫn chịu trách nhiệm về session, authorization, CSRF, cookie, logout và quyền truy cập.
