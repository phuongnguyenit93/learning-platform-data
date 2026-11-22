# Xóa remember-me và những thông tin đăng nhập được lưu lâu dài khi đăng xuất

> **Mục tiêu:** Thiết kế chức năng **logout** trong Spring Security sao cho người dùng không bị tự đăng nhập lại bằng remember-me cookie vừa bị bỏ quên; đồng thời hiểu rõ phần nào phải xóa tại **trình duyệt**, phần nào phải **thu hồi trên server**, giới hạn của logout trên một thiết bị và trường hợp còn **refresh token, OAuth2/OIDC, nhiều phiên hoặc dữ liệu đăng nhập bền vững**. Trọng tâm là **Spring Boot 3.x, Spring Security 6.x, Servlet/MVC, Java 17+**.

## 1. Đăng xuất không chỉ là chuyển hướng về trang đăng nhập

Một ứng dụng dùng session cookie có thể còn lưu nhiều loại bằng chứng đăng nhập dài hạn. Chẳng hạn:

1. **JSESSIONID**: tham chiếu đến phiên HTTP có SecurityContext.
2. **Remember-me cookie**: credential cho phép Spring Security tự xác thực lại khi không có session.
3. **Persistent remember-me token**: bản ghi **series/token** trong database, được dùng để kiểm tra cookie và có thể tồn tại qua restart.
4. **Access token / refresh token**: nếu ứng dụng dùng OAuth2 hoặc tự cấp token, chúng có thể nằm ở client, server-side token store hoặc OAuth2AuthorizedClientService.
5. **Session tại Identity Provider (IdP)**: người dùng có thể còn login ở nhà cung cấp danh tính dù đã logout khỏi ứng dụng.
6. **Browser storage**: localStorage, sessionStorage, IndexedDB, cache, Service Worker hoặc state trong frontend, nếu ứng dụng đã đưa thông tin đăng nhập vào đó.

Nếu chỉ thực hiện:

~~~java
return "redirect:/login";
~~~

thì mới thay đổi nơi trình duyệt được điều hướng. Session cũ có thể vẫn hợp lệ, remember-me cookie vẫn có thể được gửi và token server chưa chắc đã bị thu hồi. Sau khi redirect, **RememberMeAuthenticationFilter** có thể tự dựng lại Authentication, khiến người dùng tưởng logout không hoạt động.

**Bất biến của chức năng logout an toàn:** sau khi thao tác hoàn tất, các credential thuộc phạm vi logout mà người dùng yêu cầu **không thể tiếp tục khôi phục phiên xác thực**. Phải có test chứng minh điều này bằng cách **dùng lại cookie/token cũ** sau logout.

## 2. Ma trận thứ cần xóa và ai có quyền xóa

| Dữ liệu | Nơi tồn tại | Logout cần làm gì? | Lưu ý |
| --- | --- | --- | --- |
| SecurityContext | SecurityContextHolder và repository | Clear Authentication, xóa/lưu context rỗng đúng cơ chế | Không chỉ set biến trong controller |
| HTTP session | Servlet container / Spring Session | **Invalidate** session hoặc thu hồi ID | Xóa cookie ở client không đủ |
| JSESSIONID | Browser | Gửi cookie hết hạn khi phù hợp; kiểm tra Path/Domain | Server invalidation mới là biện pháp quyết định |
| Remember-me cookie | Browser | Phát **Set-Cookie** hủy cookie đúng name, Path, Domain | Client vẫn có thể giữ bản sao nếu không tuân theo header |
| Persistent remember-me token | Database / token repository | Thu hồi bản ghi tương ứng theo chính sách | Cần xử lý trường hợp authentication null |
| Hash-based remember-me cookie | Browser và công thức ký phía server | Hủy cookie; muốn thu hồi bản bị đánh cắp cần thay password/hash hoặc key/chính sách denylist | Không có bản ghi per-device mặc định để xóa |
| Refresh token do ứng dụng phát hành | Client + hệ thống cấp token | Revoke/đánh dấu không hợp lệ phía server nếu hệ thống hỗ trợ | Xóa client mà không revoke vẫn có nguy cơ replay |
| OAuth2AuthorizedClient | Session, database, service/repository | Xóa authorized client/token lưu trong ứng dụng theo kiến trúc | Không tự revoke token ở Authorization Server |
| Session ở OIDC IdP | Nhà cung cấp danh tính | Nếu cần SSO logout, thực hiện luồng logout của IdP | Local logout không mặc nhiên logout IdP |
| Browser localStorage/IndexedDB | Browser origin ứng dụng | Frontend xóa khóa/tập dữ liệu thuộc quyền quản lý | Server Set-Cookie không xóa tất cả storage tùy ý |
| Password Manager | Browser hoặc hệ điều hành | Không thuộc quyền xóa tùy tiện của ứng dụng | Không hứa xóa được mật khẩu đã được người dùng lưu |

**Xóa ở client** giúp browser ngừng gửi credential. **Thu hồi ở server** khiến bản sao đã bị đánh cắp cũng không còn được chấp nhận. Để logout có ý nghĩa bảo mật, phải ưu tiên cả hai nơi khi credential có server-side state.

## 3. LogoutFilter của Spring Security xử lý điều gì?

Khi dùng cấu hình Spring Security Servlet chuẩn, **LogoutFilter** xử lý endpoint logout trước khi request đến controller, thông thường là **POST /logout** khi CSRF được bật. **GET /logout** có thể hiển thị trang xác nhận, không nên coi một đường GET là thao tác thay đổi trạng thái trong ứng dụng có CSRF.

~~~text
Browser
  |
  | POST /logout
  | Cookie: JSESSIONID=...
  | Cookie: remember-me=...
  | CSRF token hợp lệ
  v
SecurityFilterChain
  |
  +-- CsrfFilter: từ chối nếu token sai/thiếu
  |
  +-- LogoutFilter
        |
        +-- SecurityContextLogoutHandler
        |     +-- invalidate HttpSession
        |     +-- clear Authentication / SecurityContextHolder
        |     +-- clear SecurityContextRepository
        |
        +-- RememberMeServices.logout(...)
        |     +-- hủy remember-me cookie
        |     +-- nếu persistent và có Authentication:
        |            removeUserTokens(username)
        |
        +-- CsrfLogoutHandler: xóa CSRF token đã lưu
        |
        +-- Các LogoutHandler bổ sung nếu cấu hình
        |
        v
      LogoutSuccessHandler
        |
        v
      Redirect /login?logout hoặc JSON 200/204 theo API contract
~~~

Điểm quan trọng:

- **LogoutFilter** và các LogoutHandler được Spring Security cấu hình sẵn khi dùng **logout()** và **rememberMe()** đúng cách. Không nên tự viết một endpoint chỉ gọi **session.invalidate()** rồi giả định mọi remember-me token cũng đã thu hồi.
- **SecurityContextLogoutHandler** làm sạch session/context. Nó không tự thu hồi token ở một kho nhớ đăng nhập do ứng dụng tùy biến xây dựng.
- **RememberMeServices** triển khai **LogoutHandler**. Với hash-based service, nó hủy cookie; với **PersistentTokenBasedRememberMeServices**, triển khai chuẩn còn gọi **PersistentTokenRepository.removeUserTokens(authentication.getName())** khi **Authentication không null**.
- **LogoutSuccessHandler** chỉ quyết định phản hồi sau xử lý (redirect/JSON). Một response **200** hoặc **302** không chứng minh mọi token thật sự đã bị revoke.
- Custom LogoutHandler dành cho cleanup được kỳ vọng không gây lỗi làm đứt luồng. Nếu thao tác revoke ở remote service có thể thất bại, cần quy tắc lỗi/compensation và quan sát riêng, không âm thầm xác nhận “đã đăng xuất mọi nơi” khi chưa hoàn tất.

### 3.1. Vì sao phải giữ CSRF cho logout bằng cookie?

Browser tự gửi session/remember-me cookie khi request thỏa điều kiện. Nếu một site khác có thể kích hoạt logout bằng **GET** hoặc POST không được kiểm tra, kẻ tấn công có thể ép người dùng logout (logout CSRF) hoặc tạo nhầm lẫn phiên. Với Spring Security có CSRF bật, **POST /logout** phải có CSRF token hợp lệ; **GET /logout** chủ yếu là trang xác nhận.

Đừng tắt **csrf()** chỉ để một lệnh curl POST /logout chạy được. Trong browser, form/logout client phải gửi token hợp lệ. Nếu ứng dụng chỉ dùng bearer token trong Authorization header và không có credential được browser tự gắn, thiết kế CSRF có thể khác, nhưng đó là quyết định dựa trên threat model.

### 3.2. Thứ tự xử lý khi có nhiều SecurityFilterChain

Nếu app có chain **/api/**, chain **/web/** và fallback, endpoint **/logout** phải nằm trong chain có **LogoutFilter**/RememberMeServices tương ứng. Ví dụ chain web dùng **securityMatcher("/web/**")** nhưng logout URL là **/logout** ngoài phạm vi: request logout có thể bị fallback chặn hoặc xử lý bởi chain khác.

**Một request chỉ được chain đầu tiên khớp xử lý.** Không có cơ chế “logout thất bại ở chain này thì chạy LogoutFilter của chain tiếp theo”. Test cả URL và matcher, không chỉ kiểm tra controller/route name.

## 4. Hash-based remember-me và persistent remember-me xóa khác nhau

### 4.1. Hash-based (TokenBasedRememberMeServices)

Cookie hash-based được Spring Security phát từ username, thời điểm hết hạn, thông tin mật khẩu lưu trong UserDetails và một key server kiểm soát. Cookie đã phát không cần bản ghi token riêng trong DB.

Khi logout:

1. Service gửi hướng dẫn hủy cookie remember-me trên browser.
2. Session hiện tại bị invalidate theo logout handler.
3. **Nếu attacker đã sao chép cookie trước khi logout**, bản sao có thể còn hợp lệ cho đến khi hết hạn vì server không có per-cookie record mặc định để đánh dấu revoke.
4. Muốn vô hiệu hóa rộng hơn, thay **password hash**, thay key (có thể ảnh hưởng mọi user) hoặc triển khai một cơ chế denylist/token version có kiểm tra phía server.

**Kết luận:** xóa cookie là cần thiết cho user bình thường nhưng không tương đương thu hồi mọi bản sao của hash-based cookie. Không hứa “logout khỏi tất cả thiết bị” nếu giải pháp chỉ gửi cookie hết hạn cho thiết bị hiện tại.

### 4.2. Persistent-token (PersistentTokenBasedRememberMeServices)

Cookie persistent theo implementation mặc định chứa **series** và **token** ngẫu nhiên. Repository trên server lưu thông tin tương ứng:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Khi auto-login, service tra series, kiểm tra token, xoay token và cập nhật last_used. Cookie được coi như **bearer credential**: bản sao token có thể bị dùng lại, vì vậy table và backup phải được bảo vệ như secret.

**Đặc điểm logout của triển khai mặc định:** khi có **Authentication** hợp lệ truyền vào **PersistentTokenBasedRememberMeServices.logout(...)**, nó gọi **removeUserTokens(username)**. Hợp đồng **PersistentTokenRepository** chuẩn có hàm xóa **theo username**, không phải theo series. Vì vậy **một logout có thể thu hồi tất cả remember-me records của user**, không chỉ một thiết bị.

~~~text
Trước logout:
  alice:
     series-A => token-A (laptop)
     series-B => token-B (mobile)
     series-C => token-C (tablet)

POST /logout có Authentication = alice
  -> PersistentTokenRepository.removeUserTokens("alice")

Sau logout:
  alice: không còn series-A/B/C
  -> cookie remember-me từ cả ba thiết bị không tự login được
~~~

**Cần quyết định rõ chính sách sản phẩm:** logout thiết bị hiện tại, hay logout mọi remembered device? Với repository/service mặc định, việc xóa theo user là hành vi đáng chú ý. Nếu cần thu hồi **một thiết bị**, phải thiết kế custom repository/service có quản lý series, quyền sở hữu, revocation và giao dịch; không gọi removeUserTokens rồi diễn giải là xóa một thiết bị.

### 4.3. Trường hợp Authentication null

Trong triển khai persistent, **removeUserTokens(...) chỉ chạy khi Authentication khác null**. Khi browser gửi logout sau khi session đã hết, hoặc custom logout xử lý sai SecurityContext, có thể chỉ có cookie được hủy trong response trong khi bản ghi server chưa được xóa.

Một browser tuân thủ Set-Cookie sẽ ngừng dùng cookie, nhưng **bản sao token bị đánh cắp vẫn có thể còn hợp lệ**. Nếu yêu cầu mạnh là “thu hồi cả token dù không có session”, hệ thống phải thiết kế một quy trình xác minh quyền sở hữu token/account phù hợp rồi revoke phía server, hoặc yêu cầu người dùng xác thực lại để revoke toàn bộ. **Không** cho client gửi tự do username rồi xóa tokens của username đó mà không xác thực: có thể thành công nhưng sẽ tạo khả năng logout tài khoản người khác.

### 4.4. Logout khi DB không khả dụng

Nếu repository lỗi hoặc database timeout, thao tác hủy cookie tại client có thể vẫn thành công nhưng revoke server chưa hoàn tất. Không thể dựa vào HTTP response đẹp để khẳng định revoke. Tùy yêu cầu bảo mật, cần có các hành vi như:

- Đánh dấu yêu cầu revoke/incident vào một hệ thống đáng tin nếu DB chính không khả dụng và có cơ chế đồng bộ lại.
- Trả lỗi phù hợp thay vì thông báo “đã đăng xuất mọi thiết bị” khi chưa bảo đảm.
- Sử dụng chính sách session/token ngắn, fail closed khi kiểm tra persistent token không có DB.
- Theo dõi retry có giới hạn và audit; không ghi raw token vào queue/log.

Không được để lỗi token store khiến hệ thống **bỏ qua bước kiểm tra mà vẫn cho auto-login thành công**.

## 5. Phân biệt logout một thiết bị, mọi phiên và toàn bộ hệ thống SSO

Một sản phẩm nên định nghĩa ít nhất ba thao tác:

| Mục tiêu người dùng | Thứ cần thu hồi | Có sẵn mặc định không? |
| --- | --- | --- |
| **Đăng xuất tại đây** | Session hiện tại + remember-me cookie và server token theo chính sách | Spring Security hỗ trợ, nhưng persistent service mặc định có thể revoke theo username |
| **Đăng xuất tất cả thiết bị** | Mọi session hiện hữu và mọi long-lived token/series của user | Cần tích hợp SessionRepository/registry, token store và xử lý đa thiết bị |
| **Đăng xuất cả tài khoản SSO/IdP** | Local app + phiên IdP + phiên của các relying parties nếu giao thức hỗ trợ | Cần luồng logout của IdP/protocol (OIDC RP-initiated logout, SAML SLO...) |

**Không trộn các khái niệm:**

- **removeUserTokens(username)** xóa persistent remember-me token records của user; **không tự invalidate tất cả HTTP sessions đang sống** ở các máy khác.
- **session.invalidate()** vô hiệu session hiện tại; **không tự revoke mọi remember-me token hoặc refresh token**.
- **Clear-Site-Data** xóa dữ liệu phía browser trong phạm vi được hỗ trợ; **không tự thu hồi token ở database hoặc IdP**.
- Logout local của một ứng dụng OAuth2 **không mặc nhiên logout từ IdP**; user có thể được SSO login trở lại mà không nhập mật khẩu.

Khi product có nút “Log out of all devices”, hãy xây một **revoke workflow** có danh sách storage/issuer liên quan, policy nhất quán, idempotency và test end-to-end. Không gắn nhãn ấy cho một POST /logout mặc định.

## 6. Ví dụ Spring Boot 3.x, Spring Security 6.x, Java 17+: persistent remember-me và logout

Ví dụ dùng **Spring MVC/Servlet**, **form login**, **JDBC persistent remember-me** và **H2** cho môi trường học tập. Nó minh họa việc logout chuẩn thu hồi session, hủy cookie và xóa records phía server. Không có custom logout endpoint để tránh bỏ qua chuỗi LogoutHandler của Spring Security.

### 6.1. Khởi tạo dự án

Dùng Spring Initializr chọn **Java 17+**, **Spring Boot 3.x**, Maven và các dependency: **Spring Web**, **Spring Security**, **Spring JDBC**, **H2 Database**, **Spring Boot Starter Test**. Thêm dependency **spring-security-test** scope test.

Phần dependencies tiêu biểu của **pom.xml**:

~~~xml
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
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là phần của Maven project đã có Spring Boot parent/BOM và plugin do Initializr tạo; không phải toàn bộ pom độc lập. Tất cả Java classes dưới đây đặt trong **src/main/java/com/example/logoutdemo/**.

### 6.2. Cấu hình local

Tệp **src/main/resources/application.properties**:

~~~properties
server.port=8080

# H2 file phục vụ demo. Production dùng DB được quản lý, migration và TLS.
spring.datasource.url=jdbc:h2:file:./logout-demo;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Server session là cấu trúc KHÁC remember-me token.
server.servlet.session.timeout=15m
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax

# Secret bắt buộc cấp từ biến môi trường/secret manager.
demo.user.password=${DEMO_USER_PASSWORD}
demo.remember.key=${REMEMBER_ME_KEY}
~~~

Ví dụ đặt **secure=true** cho session và remember-me cookie. Để browser sử dụng thực, phải phục vụ HTTPS (có thể dùng reverse proxy HTTPS local hoặc cấu hình TLS trực tiếp). HTTP port 8080 ở đây chỉ để học luồng backend; browser có thể không gửi Secure cookie trên HTTP ngoài ngoại lệ localhost. **Production bắt buộc có HTTPS và kiểm tra certificate**.

H2 file **logout-demo.mv.db** chứa credential nhạy cảm, phải ở thư mục local được bảo vệ và được đưa vào **.gitignore**. Không chia sẻ file DB, bản backup hay key. Khi muốn test lặp lại với trạng thái sạch, dùng một database test riêng thay vì xóa tùy tiện dữ liệu production.

Tệp **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Trong production, dùng Flyway/Liquibase và chính sách backup. Không để file schema tự chạy/mutate dữ liệu production nếu không có quy trình duyệt.

### 6.3. Entry point ứng dụng

Tệp **LogoutDemoApplication.java**:

~~~java
package com.example.logoutdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogoutDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LogoutDemoApplication.class, args);
    }
}
~~~

### 6.4. Cấu hình UserDetailsService và remember-me repository

Tệp **SecurityConfig.java**:

~~~java
package com.example.logoutdemo;

import javax.sql.DataSource;
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
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfig {

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
                        .roles("USER")
                        .build());
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        // schema.sql đã tạo bảng: không bật createTableOnStartup.
        return repository;
    }

    @Bean
    RememberMeServices rememberMeServices(
            UserDetailsService users,
            PersistentTokenRepository tokens,
            @Value("${demo.remember.key}") String key) {
        var service = new PersistentTokenBasedRememberMeServices(
                key, users, tokens);
        service.setParameter("remember-me");
        service.setCookieName("remember-me");
        service.setTokenValiditySeconds(7 * 24 * 60 * 60);
        service.setUseSecureCookie(true);
        service.setCookieCustomizer(cookie -> {
            cookie.setSecure(true);
            cookie.setHttpOnly(true);
            cookie.setPath("/");
            cookie.setAttribute("SameSite", "Lax");
        });
        return service;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RememberMeServices rememberMeServices,
            @Value("${demo.remember.key}") String key) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .requestMatchers("/account/security")
                            .fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .rememberMe(remember -> remember
                        .key(key)
                        .rememberMeServices(rememberMeServices))
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .logoutSuccessUrl("/login?logout"))
                .build();
    }
}
~~~

**Ý nghĩa và ranh giới:**

1. **JdbcTokenRepositoryImpl** là kho lưu series/token của nhớ đăng nhập persistent; nguồn account demo là **InMemoryUserDetailsManager**.
2. **PersistentTokenBasedRememberMeServices** phát cookie khi user đăng nhập form với tham số **remember-me**, sau đó kiểm tra và rotate token khi cần auto-login.
3. **setCookieCustomizer(...)** đảm bảo cookie remember-me có **Secure, HttpOnly, SameSite=Lax, Path=/**. Đây là cookie riêng, không được suy diễn từ **server.servlet.session.cookie.*** của JSESSIONID.
4. **.rememberMe(...rememberMeServices(...))** gắn service chuẩn vào chain để cả filter nhận remember-me cookie và logout infrastructure dùng đúng service.
5. **logout()** sử dụng LogoutFilter chuẩn, không tự cắt bỏ RememberMeServices. Theo triển khai persistent thông thường, **logout có Authentication** dẫn tới **removeUserTokens(username)**.
6. **fullyAuthenticated()** chặn RememberMeAuthenticationToken tại route nhạy cảm, buộc xác thực tương tác đầy đủ (hoặc step-up theo thiết kế).
7. Không tắt CSRF. Form login/logout cần CSRF token hợp lệ.
8. Key demo phải ổn định giữa các node/restart nếu muốn mô hình tin cậy nhất quán; không commit key production vào source.

**Cấu hình local này minh họa security flow, chưa có HTTPS server trên port 8080.** Muốn thử bằng browser production-like, cấu hình chứng chỉ TLS/local ingress. Không thay **secure=true** bằng false cho production để dễ debug.

### 6.5. Controller quan sát Authentication

Tệp **ProfileController.java**:

~~~java
package com.example.logoutdemo;

import java.util.Map;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public")
    public String welcome() {
        return "public";
    }

    @GetMapping("/private")
    public Map<String, Object> privateEndpoint(
            Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "remembered",
                authentication instanceof RememberMeAuthenticationToken);
    }

    @GetMapping("/account/security")
    public String securitySettings() {
        return "fresh login required";
    }
}
~~~

Sau đăng nhập form thành công, **/private** thông thường trả **remembered=false**. Nếu session đã mất nhưng cookie remember-me còn hợp lệ, có thể auto-login và trả **remembered=true**. Sau logout đúng và server token đã bị xóa, cookie cũ phải **không** phục hồi Authentication; request mới tới **/private** sẽ chuyển hướng về login.

### 6.6. Khởi động demo và những giới hạn cần nhớ

Đặt biến môi trường với mật khẩu giả và remember-me key do secret manager cấp:

~~~bash
export DEMO_USER_PASSWORD=demo-pass
export REMEMBER_ME_KEY="$(openssl rand -hex 32)"
./mvnw spring-boot:run
~~~

Trên Windows PowerShell:

~~~powershell
$env:DEMO_USER_PASSWORD = "demo-pass"
$env:REMEMBER_ME_KEY = "<secret-on-dinh-cua-moi-truong-local>"
.\mvnw.cmd spring-boot:run
~~~

**Lưu ý:** lệnh openssl sinh key mới mỗi lần shell chạy. Để kiểm tra nhớ đăng nhập xuyên restart, phải dùng key ổn định và DB bền vững trong cùng môi trường; nếu không, kết quả thử sẽ bị nhiễu vì thay key.

Do cookie Secure, nên khi dùng browser để thử, đặt HTTPS trước ứng dụng. Không gửi mật khẩu thật qua HTTP, không bỏ qua certificate verification. Kiểm tra Set-Cookie tại điểm browser thực sự kết nối, kể cả khi TLS kết thúc ở reverse proxy.

## 7. Kiểm thử chức năng xóa remember-me bằng MockMvc và JDBC

Test quan trọng nhất là **đăng nhập thật → nhận cookie → kiểm tra DB token → logout → kiểm tra cookie bị hủy, DB bị xóa → thử dùng lại token cũ**. Test chỉ gọi **@WithMockUser** không phát remember-me cookie thực và không thể chứng minh toàn bộ flow.

### 7.1. Test source

Tệp **src/test/java/com/example/logoutdemo/RememberMeLogoutTest.java**:

~~~java
package com.example.logoutdemo;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.user.password=demo-pass",
        "demo.remember.key=test-only-key-not-for-production",
        "spring.datasource.url=jdbc:h2:mem:logout_test;DB_CLOSE_DELAY=-1",
        "server.servlet.session.cookie.secure=true"
})
@AutoConfigureMockMvc
class RememberMeLogoutTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void resetPersistentTokens() {
        jdbc.update("DELETE FROM persistent_logins");
    }

    private int rememberedDeviceCount() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM persistent_logins WHERE username = ?",
                Integer.class,
                "alice");
        return count == null ? 0 : count;
    }

    private MvcResult loginWithRememberMe() throws Exception {
        return mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass")
                    .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();
    }

    @Test
    void logoutRevokesDatabaseTokenAndCookie()
            throws Exception {

        MvcResult login = loginWithRememberMe();

        Cookie originalRememberMe =
                login.getResponse().getCookie("remember-me");
        assertNotNull(originalRememberMe);
        assertEquals(7 * 24 * 60 * 60,
                originalRememberMe.getMaxAge());
        assertTrue(originalRememberMe.getSecure());
        assertTrue(originalRememberMe.isHttpOnly());
        assertEquals(1, rememberedDeviceCount());

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        MvcResult logout = mvc.perform(post("/logout")
                    .session(session)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/login?logout"))
                .andReturn();

        // Server-side revocation: cookie đã sao chép không dùng lại được.
        assertEquals(0, rememberedDeviceCount());

        // LogoutHandler phát cookie mới với Max-Age=0.
        Cookie cleared =
                logout.getResponse().getCookie("remember-me");
        assertNotNull(cleared);
        assertEquals(0, cleared.getMaxAge());

        // Không gửi session; cố tình replay remember-me cookie cũ.
        mvc.perform(get("/private").cookie(originalRememberMe))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutOfOneSessionRevokesAllRememberedSeriesByDefault()
            throws Exception {

        MvcResult firstLogin = loginWithRememberMe();
        MvcResult secondLogin = loginWithRememberMe();

        // Mỗi login có remember-me tạo một series mới.
        assertEquals(2, rememberedDeviceCount());

        MockHttpSession firstSession =
                (MockHttpSession) firstLogin
                        .getRequest().getSession(false);
        assertNotNull(firstSession);

        mvc.perform(post("/logout")
                    .session(firstSession)
                    .with(csrf()))
                .andExpect(status().is3xxRedirection());

        // Repository mặc định xóa theo username, không chỉ một series.
        assertEquals(0, rememberedDeviceCount());

        Cookie secondDeviceCookie =
                secondLogin.getResponse().getCookie("remember-me");
        assertNotNull(secondDeviceCookie);

        mvc.perform(get("/private").cookie(secondDeviceCookie))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void logoutWithoutCsrfIsRejectedAndTokenRemains()
            throws Exception {

        MvcResult login = loginWithRememberMe();
        assertEquals(1, rememberedDeviceCount());

        MockHttpSession session =
                (MockHttpSession) login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/logout").session(session))
                .andExpect(status().isForbidden());

        assertEquals(1, rememberedDeviceCount());
    }

    @Test
    void loginWithoutRememberMeDoesNotCreatePersistentToken()
            throws Exception {

        mvc.perform(post("/login")
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo-pass"))
                .andExpect(status().is3xxRedirection());

        assertEquals(0, rememberedDeviceCount());
    }
}
~~~

**Test có ý nghĩa gì?**

- **logoutRevokesDatabaseTokenAndCookie** kiểm tra cả client và server: Set-Cookie Max-Age=0 chưa đủ; DB phải hết bản ghi và cookie cũ không login lại được.
- **logoutOfOneSessionRevokesAllRememberedSeriesByDefault** kiểm tra hệ quả thực tế của **removeUserTokens(username)** trong implementation chuẩn. Product phải quyết định có mong muốn thu hồi tất cả thiết bị remembered hay không.
- **logoutWithoutCsrfIsRejectedAndTokenRemains** cho thấy POST logout không hợp lệ không được đổi trạng thái bảo mật.
- **loginWithoutRememberMeDoesNotCreatePersistentToken** bảo đảm remember-me không bị bật cho mọi user ngoài ý muốn.

**Các test mô phỏng HTTP qua MockMvc và dùng H2 in-memory.** Chúng không thay cho kiểm thử container/browser về SameSite, Path, Domain, TLS và cookie store. Nếu implementation/schema/version khác, cần điều chỉnh assertion theo cấu hình thực tế; không sửa kỳ vọng chỉ để test xanh mà chưa hiểu hành vi bảo mật.

### 7.2. Chạy bài test

~~~bash
./mvnw test
./mvnw -Dtest=RememberMeLogoutTest test
~~~

PowerShell:

~~~powershell
.\mvnw.cmd test
.\mvnw.cmd '-Dtest=RememberMeLogoutTest' test
~~~

Expected result: các test hoàn tất thành công khi dự án nguồn và dependency đúng. **Không đưa stdout hay số test đã PASS nếu chưa thực sự chạy trong môi trường của bạn.**

### 7.3. Ma trận nghiệm thu mở rộng

| Tình huống | Điều phải kiểm tra |
| --- | --- |
| Login đúng và chọn remember-me | DB có token, cookie có Secure/HttpOnly/SameSite/Path/Max-Age |
| Login đúng nhưng không chọn | Không tạo long-lived remember-me token |
| Sai password | Không phát remember-me cookie và không thêm DB token |
| Logout session hợp lệ, CSRF hợp lệ | Session invalid, SecurityContext clear, remember-me cookie expired, DB revoke |
| Logout thiếu CSRF | Bị 403; không vô tình revoke dữ liệu do request giả |
| Dùng lại cookie remember-me cũ sau logout | Không tự xác thực được |
| Cookie bị đánh cắp trước logout | Bản sao vẫn bị từ chối nếu DB token đã revoke |
| Logout khi session đã hết | Kiểm tra rõ DB token có bị xóa không; không tin chỉ có cookie clearing |
| Logout từ một remembered device | Với service mặc định, test tác động tới tất cả series của username |
| User đổi password | Tích hợp policy revoke remember-me token, refresh token và sessions thích hợp |
| User bị locked/disabled | Token cũ không được dựng Authentication hợp lệ |
| DB outage lúc logout | Phản hồi đúng policy, có sự kiện/audit và không tuyên bố revoke thành công khi chưa có |
| Logout trong nhiều tab | Tab khác không phục hồi session bằng token cũ; state frontend được đồng bộ |
| Request concurrent ngay lúc logout | Xem rủi ro request đang chạy dùng context cũ và revoke eventual consistency |
| IdP session còn sống | Local logout không đồng nghĩa IdP logout; kiểm tra SSO re-login |
| Refresh token còn sống | Revoke ở token issuer hoặc token store, không chỉ xóa localStorage |
| Multi-instance / Redis / Spring Session | Invalidate đúng shared session store; không chỉ xóa state ở một node |

## 8. Xóa cookie đúng cách: name, Path, Domain và prefix

Cookie trên browser được phân biệt theo **name + domain + path**. Việc gửi:

~~~http
Set-Cookie: remember-me=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

yêu cầu trình duyệt xóa cookie cùng phạm vi tương ứng. Nếu cookie gốc có **Path=/app**, còn header hủy có **Path=/**, trình duyệt có thể giữ cookie gốc. Tương tự, **Domain** không khớp có thể tạo hoặc xóa nhầm cookie khác.

**Quy tắc:**

1. Ghi nhận chính xác **name**, **Path**, **Domain** của cookie lúc phát hành.
2. Khi logout, hủy cookie với phạm vi khớp. Đảm bảo URL logout nằm trên host/path phù hợp để browser chấp nhận Set-Cookie hủy.
3. Gửi **Max-Age=0** hoặc Expires trong quá khứ. Đừng gửi Max-Age dài hơn do nhầm thông số.
4. Giữ Secure và HttpOnly theo chính sách; dùng HTTPS đúng cách.
5. Kiểm tra **Application/Storage → Cookies** và **Network → Set-Cookie** trên browser thực; đừng đoán từ config.
6. Nếu thay cookie name hoặc path qua các phiên bản ứng dụng, cân nhắc giai đoạn hỗ trợ xóa cookie legacy.

### 8.1. Session cookie JSESSIONID

Spring Security **SecurityContextLogoutHandler** mặc định invalidate session; thông thường điều này ngăn dùng lại ID cũ. Nếu cần xóa trực quan cookie JSESSIONID, Spring Security cho phép:

~~~java
.logout(logout -> logout
    .deleteCookies("JSESSIONID"))
~~~

Đây chỉ là **đoạn DSL minh họa**, không thay toàn bộ SecurityFilterChain. Hiệu quả xóa cookie phụ thuộc Servlet container, Path và Domain nên phải test ở deployment thực. **Không thay thế server-side invalidate bằng deleteCookies**: nếu ai đó đã sao chép session ID và server vẫn giữ session, bản sao còn rủi ro.

### 8.2. Clear-Site-Data

Header:

~~~http
Clear-Site-Data: "cookies"
~~~

yêu cầu browser xóa cookies thuộc phạm vi hỗ trợ. Spring Security có thể cấu hình:

~~~java
var clearCookies = new HeaderWriterLogoutHandler(
    new ClearSiteDataHeaderWriter(
        ClearSiteDataHeaderWriter.Directive.COOKIES));

http.logout(logout -> logout
    .addLogoutHandler(clearCookies));
~~~

Đây là đoạn minh họa trong cấu hình Java; cần import các class từ gói **org.springframework.security.web.authentication.logout** và **org.springframework.security.web.header.writers** tương ứng. **Clear-Site-Data** có thể ảnh hưởng nhiều cookie/dữ liệu hơn chủ đích, tùy directive và browser; cần đánh giá việc dùng chung origin với ứng dụng khác và khả năng tương thích browser. Nếu xóa storage/cache, ảnh hưởng có thể lớn hơn việc xóa cookie session.

**Clear-Site-Data không gọi PersistentTokenRepository và không revoke refresh token.** Nó là thao tác ở browser, không phải nguồn thu hồi server.

## 9. Dữ liệu đăng nhập lâu dài ngoài remember-me

### 9.1. Refresh token / access token do ứng dụng cấp

Một SPA hoặc ứng dụng di động có thể dùng access token ngắn hạn cùng refresh token dài hạn. Logout an toàn thường cần:

~~~text
Client gửi yêu cầu logout hợp lệ
    |
    +-- Xác định refresh token/session cần thu hồi
    +-- Server thu hồi refresh token/token family theo policy
    +-- Xóa client-held token khỏi nơi lưu
    +-- Invalidate session nếu mô hình có session
    +-- Trả trạng thái và đồng bộ giữa tab/thiết bị
~~~

**Access token JWT đã phát có thể vẫn được API chấp nhận tới hạn exp** nếu hệ thống xác minh offline và không kiểm tra revoke/denylist/epoch. Xóa token khỏi localStorage không làm bản sao đã bị đánh cắp hết hiệu lực. Nếu yêu cầu “logout ngay”, cần thiết kế **token revocation, reference token, denylist, session epoch hoặc thời hạn access token ngắn** phù hợp.

**Refresh token rotation**: nếu dùng token family, logout nên revoke đúng family hoặc tất cả families theo lựa chọn người dùng, đồng thời kiểm tra replay. Đừng coi một cookie tên refresh-token là remember-me token của Spring Security; hai cơ chế có service/issuer khác nhau.

### 9.2. OAuth2AuthorizedClientService và IdP

Với Spring Security OAuth2 Client, ứng dụng có thể lưu **OAuth2AuthorizedClient** gồm access token và refresh token được phát cho ứng dụng. Khi logout, có thể cần xóa authorized client khỏi service/repository phía ứng dụng. Tuy nhiên:

- Xóa **OAuth2AuthorizedClient** nội bộ **không tự gọi revocation endpoint** của Authorization Server.
- Logout khỏi ứng dụng **không tự xóa session SSO** tại IdP. Khi user quay lại, IdP có thể đăng nhập tự động.
- Nếu mục tiêu là **OIDC RP-Initiated Logout**, dùng luồng endpoint của IdP với id_token_hint, post_logout_redirect_uri và các thông số được hỗ trợ; phải kiểm tra cấu hình của provider.
- **SAML Single Logout** hoặc back-channel logout có cơ chế riêng; không giả định một endpoint local logout bao phủ mọi relying party.

Chỉ tuyên bố “đăng xuất toàn bộ” khi giao thức và các hệ thống liên quan thực sự hoàn tất bước thu hồi. Nếu IdP không hỗ trợ, ghi rõ giới hạn cho người dùng.

### 9.3. Browser localStorage, sessionStorage, IndexedDB và cache

Nếu frontend có lưu dữ liệu đăng nhập:

~~~javascript
// Minh họa frontend chạy trên origin của ứng dụng.
localStorage.removeItem("app-access-token");
localStorage.removeItem("app-user");
sessionStorage.removeItem("app-draft-auth-state");
~~~

Các key chỉ là ví dụ cho một ứng dụng tự định nghĩa; không phải API do Spring Security tạo. Đừng dùng **localStorage.clear()** trên origin dùng chung mà không hiểu sẽ xóa luôn dữ liệu hợp lệ của thành phần khác. Nếu token còn trong IndexedDB hoặc cache, xóa theo schema/tên đã quản lý, đồng thời clear state trong memory và các tab bằng cơ chế phù hợp như **BroadcastChannel**.

Với cookie HttpOnly, JavaScript **không** đọc hoặc xóa cookie bằng **document.cookie** như cookie thường. Server phải phát Set-Cookie hủy đúng phạm vi. **Service Worker** và ứng dụng PWA có thể còn cache dữ liệu nhạy cảm; cần có chiến lược clear cache phù hợp.

**Mật khẩu được lưu trong password manager của browser/hệ điều hành không thể và không nên bị ứng dụng xóa tùy ý.** Đăng xuất không tương đương xóa tài khoản hoặc xóa mọi thiết lập autofill của người dùng.

## 10. Khi cần endpoint logout JSON cho SPA

Ứng dụng REST thường muốn trả **204 No Content** hoặc JSON 200 thay vì redirect. Cách tốt là **vẫn để LogoutFilter xử lý**, nhưng thay **LogoutSuccessHandler**:

~~~java
.logout(logout -> logout
    .logoutUrl("/api/logout")
    .logoutSuccessHandler((request, response, authentication) -> {
        response.setStatus(204);
        response.setHeader("Cache-Control", "no-store");
    }))
~~~

Đây là **đoạn cấu hình rút gọn**, không phải một SecurityFilterChain độc lập. Đảm bảo **/api/logout** nằm trong chính SecurityFilterChain chứa LogoutFilter và RememberMeServices. Với session cookie, POST logout vẫn cần CSRF nếu bảo vệ được bật.

Không thay bằng một **@PostMapping("/api/logout")** chỉ thực hiện:

~~~java
// Ví dụ CỐ TÌNH SAI: chỉ xóa một cookie ở browser,
// không invalidate session, không revoke database tokens.
response.addHeader("Set-Cookie",
        "remember-me=; Max-Age=0; Path=/");
~~~

Request có thể trả HTTP 200/204 và frontend đóng modal nhưng **persistent_logins** vẫn chứa token. Nếu cần custom endpoint thực sự, hãy sử dụng **LogoutHandler** phù hợp (SecurityContextLogoutHandler, RememberMeServices, CSRF logout, custom revoke handler), bảo vệ CSRF/authorization và kiểm thử toàn bộ vòng đời. Không duplicate logout logic mà bỏ sót một handler.

### 10.1. API logout có nên idempotent?

Về mặt hành vi người dùng, logout nhiều lần nên không tạo lại session/credential hoặc làm lộ thông tin. Nếu request thứ hai đã hết session, trả status theo contract API có thể là 204/401 tùy thiết kế, nhưng **không được xác nhận đã revoke token cụ thể chưa kiểm tra được**.

Đừng để API nhận username tùy ý trong body và gọi **removeUserTokens(username)** không cần xác thực; đây là một điểm có thể bị lạm dụng để ép logout tài khoản khác. Khi revoke theo user, xác định user từ principal đã tin cậy hoặc từ credential token đã xác minh đầy đủ.

## 11. Khi nào cần buộc xóa mọi thông tin đăng nhập lâu dài?

| Sự kiện | Xử lý khuyến nghị | Vì sao |
| --- | --- | --- |
| Logout bình thường | Invalidate session, clear remember-me cookie; revoke remember tokens theo policy | Tránh auto-login trở lại |
| Logout mọi thiết bị | Revoke mọi remembered series, sessions và refresh-token families | Loại bỏ quyền đăng nhập từ thiết bị khác |
| Đổi mật khẩu | Cân nhắc revoke nhớ đăng nhập, refresh tokens và các session cũ | Credential cũ có thể đã bị lộ |
| Khóa hoặc vô hiệu tài khoản | Chặn login + auto-login, revoke dài hạn | Không cho tiếp tục truy cập bằng token cũ |
| Phát hiện cookie bị đánh cắp | Revoke series/token, điều tra session reuse và các phiên liên quan | Cookie là bearer credential |
| Database persistent_logins bị lộ | Giả định có nguy cơ replay; revoke token có thể bị lộ, đánh giá backup | Raw series/token trong DB là bí mật |
| Signing key hash-based lộ | Xoay key, đánh giá password hash đã lộ và revoke khi cần | Chữ ký cookie có thể bị giả mạo |
| User rút quyền OAuth2 | Xóa authorized-client data và revoke token ở issuer nếu hỗ trợ | Token còn ở Authorization Server |
| User yêu cầu xóa tài khoản | Quy trình riêng gồm revoke, retention, audit và xóa dữ liệu theo chính sách | Logout không phải account deletion |

Với hệ thống đa instance, **revoke phải nhìn thấy được từ mọi node**. Nếu session nằm ở Redis/Spring Session, phải xóa đúng entry trong shared store. Nếu có cache credential/token validation, phải có TTL/invalidation bảo đảm bản ghi revoke không bị bỏ qua bởi cache stale.

## 12. Lỗi thường gặp khi xóa thông tin đăng nhập

### 12.1. Chỉ chuyển hướng tới /login

User có thể vẫn có SecurityContext hoặc remember-me cookie hợp lệ. **Sửa:** dùng LogoutFilter, kiểm tra session invalidate, cookie cancel và token store.

### 12.2. Chỉ xóa JSESSIONID

RememberMeAuthenticationFilter có thể tự tạo Authentication từ remember-me cookie ngay sau đó. **Sửa:** hủy cookie remember-me và revoke persistent token.

### 12.3. Chỉ xóa remember-me cookie

Một bản sao cookie đã bị đánh cắp có thể được dùng lại nếu persistent record chưa bị revoke. **Sửa:** kiểm tra **removeUserTokens** hoặc custom revocation server-side.

### 12.4. Cho rằng logout mặc định chỉ thu hồi thiết bị hiện tại

PersistentTokenBasedRememberMeServices chuẩn gọi **removeUserTokens(username)** khi có Authentication, thường thu hồi **tất cả series** của user. **Sửa:** test chính sách và thiết kế per-device revoke riêng nếu cần.

### 12.5. Tin rằng đổi password tự xóa persistent tokens

Token DB không mặc nhiên dựa trên password hash như hash-based cookie. **Sửa:** gắn explicit revoke vào password change/disable-account flow.

### 12.6. Đổi remember-me key để revoke persistent tokens

Đổi key không đồng nghĩa xóa token series/token vẫn nằm trong database. **Sửa:** chủ động revoke persistent records.

### 12.7. Xóa cookie với sai Path/Domain

Browser giữ cookie cũ dù response có Max-Age=0 cho một cookie khác cùng tên. **Sửa:** phát hủy cookie đúng scope và test DevTools.

### 12.8. POST /logout không có CSRF nhưng coi 403 là lỗi password

CsrfFilter có thể chặn trước LogoutFilter. **Sửa:** gửi token hợp lệ, không tắt CSRF để sửa test.

### 12.9. Custom controller chỉ gọi session.invalidate()

Không đủ nếu SecurityContextRepository, remember-me token, CSRF token và storage riêng chưa được xử lý. **Sửa:** dùng built-in logout infrastructure hoặc gọi toàn bộ handler đã thiết kế.

### 12.10. Quên dữ liệu lưu bởi SPA hoặc OAuth2AuthorizedClientService

Xóa browser cookie không xóa bearer/refresh tokens lưu nơi khác. **Sửa:** liệt kê các credential stores, revoke và dọn frontend state theo kiến trúc.

### 12.11. Thông báo “logout tất cả” khi IdP session còn sống

User có thể trở lại và login tự động qua SSO. **Sửa:** tích hợp OIDC/SAML logout nếu được hỗ trợ, và mô tả rõ phạm vi local vs global.

### 12.12. Ghi raw token vào log để debug

Remember-me token, refresh token, session ID và Authorization header đều là bí mật có thể bị replay. **Sửa:** redact, dùng correlation ID và trạng thái revoke thay cho raw values.

## 13. Checklist nghiệm thu production

- [ ] Logout dùng **POST** và bảo vệ CSRF khi ứng dụng xác thực bằng browser cookies.
- [ ] Endpoint thuộc đúng SecurityFilterChain; không bị matcher fallback che.
- [ ] Session hiện tại được invalidate; SecurityContextHolder và repository được clear.
- [ ] RememberMeServices thật được gắn vào SecurityFilterChain và logout flow.
- [ ] Cookie nhớ đăng nhập bị hủy bằng Set-Cookie phù hợp **name/Path/Domain/Secure**.
- [ ] JSESSIONID bị vô hiệu phía server; cookie được xóa khi phù hợp.
- [ ] Với persistent-token: repository thực sự xóa row theo chính sách; test dùng lại cookie cũ.
- [ ] Xác định phạm vi **logout hiện tại** hay **logout mọi remembered device**; không nói sai hành vi mặc định.
- [ ] Kiểm tra trường hợp **Authentication null** hoặc DB lỗi để không xác nhận revoke giả.
- [ ] Khi đổi password/disable-account/incident, có chính sách revoke remember-me và refresh tokens.
- [ ] Nếu cấp access/refresh tokens riêng, logout có server-side revocation và client-side cleanup thích hợp.
- [ ] Nếu dùng OAuth2/OIDC/SAML SSO, phân biệt local logout và IdP/global logout.
- [ ] Browser storage, service worker/cache và state nhiều tab được dọn có kiểm soát.
- [ ] Không tiết lộ raw cookie/token trong logs, test output, crash dumps hoặc tickets.
- [ ] Kiểm thử replay token sau logout, concurrent requests, multi-instance, Redis/database consistency.
- [ ] Các endpoint nhạy cảm yêu cầu **fullyAuthenticated()** hoặc step-up authentication thay vì tin remember-me vô thời hạn.
- [ ] Có monitoring cho logout failure/revocation failure và quy trình incident-response.

## 14. Câu hỏi tự kiểm tra

**1. Vì sao logout khỏi session nhưng user vẫn được nhận diện?** Vì remember-me cookie còn hợp lệ và RememberMeAuthenticationFilter có thể tự xác thực lại sau khi session mất. Cần kiểm tra cả cookie lẫn token store.

**2. Xóa remember-me cookie trên browser có đủ để thu hồi token bị đánh cắp không?** Không, đặc biệt khi token có bản sao ở nơi khác. Với persistent-token phải revoke server-side record; với hash-based cần cân nhắc thay password/key hoặc giải pháp revoke bổ sung.

**3. Logout một lần với PersistentTokenBasedRememberMeServices chuẩn có thể ảnh hưởng bao nhiêu thiết bị?** Khi Authentication hợp lệ được cung cấp, implementation gọi **removeUserTokens(username)**; có thể xóa mọi series của user. Phải test và mô tả đúng phạm vi.

**4. Khi Authentication null thì persistent logout có bảo đảm xóa tất cả token trong DB không?** Không. Việc xóa theo username của implementation thông thường phụ thuộc Authentication. Cần design riêng nếu muốn revoke cả khi session đã hết.

**5. Xóa JSESSIONID có xóa access token ở OAuth2AuthorizedClientService không?** Không mặc nhiên. Token lưu ở server hoặc Authorization Server có vòng đời riêng; cần cleanup/revoke đúng thành phần.

**6. Vì sao không được gọi GET /logout để thay đổi trạng thái một cách tùy tiện?** Request GET dễ bị kích hoạt qua điều hướng; Spring Security thường dùng GET cho trang xác nhận và POST với CSRF để logout thực sự.

**7. Dùng Clear-Site-Data: "cookies" có tương đương thu hồi refresh token không?** Không. Nó yêu cầu browser xóa cookie; phải revoke phía server/issuer nếu token còn hiệu lực.

## 15. Tài liệu tham khảo

- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): chuỗi LogoutHandler, session/context, remember-me cleanup, Clear-Site-Data và logout endpoint.
- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html): hash-based và persistent remember-me, cookie, UserDetailsService và schema.
- [PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html): logout(), token rotation, CookieTheftException và repository.
- [PersistentTokenRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenRepository.html): removeUserTokens(username), create/update/get token.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): invalidate session, cookie clearing và session policy.
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF token và logout của ứng dụng dùng cookie.
- [Spring Security 6.5 — OAuth2 Login / OIDC Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): cấu hình logout với OpenID Connect nếu cần.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Max-Age, Path, Domain, Secure, HttpOnly, SameSite.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session expiration, revocation và cookie security.
