# Giới hạn của đăng xuất ứng dụng khi vé Kerberos của máy người dùng còn hiệu lực

## 1. Vấn đề thực tế: logout thành công nhưng người dùng lại đăng nhập ngay

Nhân viên **alice@EXAMPLE.ORG** đã đăng nhập một máy Windows thuộc miền doanh nghiệp. Trình duyệt được phép dùng **Integrated Windows Authentication (IWA)** trên website **https://intranet.example.org**. Browser nhận challenge **HTTP 401 WWW-Authenticate: Negotiate**, dùng Kerberos credentials của máy, gửi **Authorization: Negotiate**, rồi Spring Security tạo một local Authentication và HttpSession.

Alice bấm **Đăng xuất**. Ứng dụng xóa SecurityContext, invalidate HttpSession và chuyển tới trang công khai. Nhưng khi alice mở lại URL **/private**, browser có thể tự xác thực Kerberos lần nữa mà **không hỏi mật khẩu**. Người dùng dễ kết luận nhầm rằng logout bị lỗi.

Hai điều này có thể cùng đúng:

- **Local logout thành công:** ứng dụng chấm dứt phiên HTTP cũ, SecurityContext không được tiếp tục dùng.
- **Kerberos SSO vẫn còn:** TGT hoặc service ticket của máy người dùng còn hiệu lực; browser có thể thực hiện **một lần authentication mới** để lấy một phiên ứng dụng mới.
- **Local authorization độc lập:** việc Kerberos nhận diện user không tự cấp lại quyền, roles/tenant membership hoặc active account đã bị thu hồi.

**Quy tắc quan trọng:** **Spring Security POST /logout không tự hủy TGT hoặc các service tickets trong kho Kerberos của hệ điều hành người dùng.** Đó là phạm vi khác của máy client và Kerberos KDC. Nút logout ở một ứng dụng web không thể hứa rằng người dùng đã đăng xuất khỏi toàn bộ workstation, domain hoặc mọi ứng dụng.

Bài học nằm trong **Tích hợp Kerberos / Spring Security - federation**, dùng ví dụ **Java 17+, Spring Boot 3.3.5, Spring Security 6.x và Spring Security Kerberos extension 2.1.0**. Domain **EXAMPLE.ORG** và URL **example.org** chỉ là ví dụ; đăng nhập Kerberos thật cần KDC/AD, SPN, keytab, DNS/HTTPS và browser policy tương ứng.

### Mục tiêu

1. Phân biệt **TGT, service ticket, GSS/SPNEGO authentication, SecurityContext, HttpSession, cookie và local account status**.
2. Mô tả **logout local → truy cập protected → HTTP Negotiate → silent reauthentication**.
3. Cấu hình **LogoutFilter, SecurityContextLogoutHandler, POST /logout, CSRF và logout success page** đúng Spring Security 6.x.
4. Tránh tự xác thực lại ngay tại trang /signed-out bằng **public filter chain không có SPNEGO filter**.
5. Phân biệt **logoff hệ điều hành**, xóa Kerberos cache, tắt user, thu hồi local sessions và **step-up authentication**.
6. Thiết kế hướng dẫn logout cho intranet, thiết bị dùng chung và doanh nghiệp nhiều ứng dụng.
7. Kiểm chứng session cũ không còn hợp lệ, đồng thời chứng minh login mới bằng Kerberos có thể xảy ra.
8. Giữ HTTPS, CSRF, ticket validation, local authorization và replay protections khi xử lý logout.

## 2. Những state độc lập nằm ở đâu?

| Trạng thái | Ai giữ? | Spring local logout có xóa không? |
| --- | --- | --- |
| **Windows/OS logon session** | Hệ điều hành workstation. | Không. |
| **TGT** | OS Kerberos credential cache, ví dụ Windows LSA hoặc MIT ccache. | Không. |
| **Kerberos service ticket** | Credential cache trên client, dành cho SPN cụ thể. | Không. |
| **GSS/SPNEGO exchange** | Browser/OS và server acceptor lúc HTTP authentication. | Không tự xóa mọi GSS credentials/context của thiết bị. |
| **Spring Authentication** | SecurityContext ở request hoặc persisted repository. | Có, khi LogoutFilter chạy đúng. |
| **Spring SecurityContextRepository** | HttpSession hoặc nơi lưu thích hợp. | Được xóa theo logout handler đúng cấu hình. |
| **HttpSession** | Servlet container hoặc Spring Session shared store. | Thường bị invalidate. |
| **JSESSIONID/SESSION cookie** | Browser, gắn với website, domain/path. | Có thể expire hoặc được xóa hỗ trợ, session cũ phải vô hiệu trên server. |
| **Local account, role và tenant membership** | App database/LDAP/IGA. | Không bị tự động xóa; vẫn cần kiểm. |
| **Phiên ứng dụng khác** | App B, SaaS, IdP, proxy khác. | Không tự bị logout bởi app A. |
| **SAML/OIDC IdP session** | Enterprise IdP/OP, nếu dùng bridge. | Không tự bị xóa khi logout một app Kerberos. |

**TGT không phải JSESSIONID**, và **service ticket không phải session cookie**. Client có TGT có thể xin service ticket cho **HTTP/intranet.example.org@EXAMPLE.ORG**; web server kiểm ticket đó bằng GSS-API/keytab. Sau khi authenticated, Spring có thể phát cookie để không phải chạy GSS exchange ở mỗi request.

**TGT khác service ticket:** TGT được dùng với KDC/TGS để xin tickets, còn service ticket gắn với một SPN và có thể đã được client cache. Xóa TGT mà giữ service ticket còn hạn **không nhất thiết** ngăn được client truy cập service. Ngược lại, service ticket không có, TGT còn nhưng KDC không reachable cũng có thể không xin được ticket mới.

## 3. Chuỗi HTTP và Kerberos sau local logout

~~~text
T0  User login Windows/domain
    Client OS cache: TGT còn hạn

T1  Browser GET /private
    SP: HTTP 401 WWW-Authenticate: Negotiate
    Browser: lấy service ticket theo SPN, gửi GSS token
    SP: GSS/Kerberos validator kiểm token + keytab + service policy
    SP: UserDetailsService map verified principal -> local account
    SP: tạo Authentication, lưu SecurityContext vào session S1
    GET /private -> HTTP 200 nếu có quyền

T2  User POST /logout với CSRF token hợp lệ
    Spring LogoutFilter:
       invalidate HttpSession S1
       clear Authentication và SecurityContext
       cleanup repository / CSRF state theo cấu hình
       redirect tới /signed-out
    OS workstation: TGT/ST không thay đổi

T3  GET /signed-out
    Public chain không chứa SpnegoAuthenticationProcessingFilter
    HTTP 200: "Phiên ứng dụng này đã kết thúc"

T4  User quay lại GET /private
    Protected chain: 401 Negotiate
    Browser: còn TGT/ST, tự gửi token Kerberos mới
    SP: xác minh lại, kiểm local account và quyền
    Nếu đạt -> local SecurityContext/session S2 mới
    S2 khác S1; người dùng có thể không nhập lại mật khẩu
~~~

**Logout không hồi sinh S1.** Nếu sau T2 người dùng có session S2, đó có thể là **authentication mới**, không phải session cũ còn hoạt động. Khi QA phải theo dõi session lifecycle và các events **KERBEROS_AUTHENTICATION** và **LOCAL_LOGOUT**, không chỉ nhìn browser có thấy trang private hay không.

### Ví dụ HTTP

Request logout trong mô hình bật CSRF:

~~~http
POST /logout HTTP/1.1
Host: intranet.example.org
Cookie: JSESSIONID=OLD_SESSION
Content-Type: application/x-www-form-urlencoded

_csrf=VALID_CSRF_TOKEN
~~~

Một response minh họa:

~~~http
HTTP/1.1 302 Found
Location: /signed-out
~~~

Servlet container và cookie settings quyết định có gửi thêm Set-Cookie expire JSESSIONID hay không; **không bắt buộc mọi triển khai có cùng headers byte-by-byte**. Điều cần xác minh là **OLD_SESSION đã invalidate tại server**.

Sau đó:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Negotiate
~~~

Browser có credentials hợp lệ có thể tự phản hồi:

~~~http
GET /private HTTP/1.1
Host: intranet.example.org
Authorization: Negotiate NEW_GSS_TOKEN_GENERATED_FOR_THIS_EXCHANGE
~~~

Raw token chỉ là ký hiệu minh họa. **Không copy/replay HTTP token cũ** rồi xem đó là Kerberos authentication: GSS/Kerberos acceptor vẫn phải kiểm authenticator, keytab, freshness, clock và replay. Với các browser/settings khác nhau có thể có nhiều vòng Negotiate và final token.

## 4. Spring Security logout thực sự xử lý những gì?

Theo Spring Security 6.x Servlet logout architecture:

- **GET /logout** với CSRF bật thường hiển thị trang xác nhận có form, không phải thao tác logout.
- **POST /logout + CSRF token hợp lệ** được **LogoutFilter** xử lý.
- **SecurityContextLogoutHandler** xóa Authentication, SecurityContext trong holder/repository và invalidate HttpSession theo cấu hình.
- Các logout handlers khác có thể xóa CSRF token, remember-me hoặc dữ liệu riêng của ứng dụng.
- **LogoutSuccessHandler** quyết định status/redirect sau logout, ví dụ tới **/signed-out**.
- **LogoutFilter chạy trước AuthorizationFilter**, nên không cần mở toàn bộ tài nguyên protected chỉ để thực thi logout.

**Nút Logout phải dùng POST**, hoặc cơ chế chống CSRF tương đương; không tắt CSRF chỉ để dùng GET /logout như một state-changing action.

### 4.1. Những API hay dùng

~~~java
// Mảnh Java DSL minh họa, đặt bên trong HttpSecurity configuration.
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessUrl("/signed-out")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("JSESSIONID")
    .permitAll());
~~~

- **invalidateHttpSession(true):** vô hiệu HttpSession của ứng dụng.
- **clearAuthentication(true):** xóa Authentication khỏi SecurityContext khi logout.
- **deleteCookies("JSESSIONID"):** hỗ trợ browser xóa cookie nếu phù hợp domain/path/config. Session server phải đã invalidated ngay cả khi browser vẫn gửi cookie cũ.
- **logoutSuccessUrl("/signed-out"):** redirect tới trang public; cần có route permitAll **và** tránh SPNEGO tự xác thực tại route đó.
- Không có lệnh nào ở đây xóa **Kerberos TGT/ST** trên workstation.

### 4.2. Clear-Site-Data và cookie không phải KDC logout

**Clear-Site-Data** là HTTP response header có thể yêu cầu browser xóa dữ liệu của website (cookies/storage/cache tùy directives và browser). Header này **không phải giao thức quản lý Kerberos tickets trong Windows LSA**. Xóa cookies của một web origin không tương đương sign-out khỏi Windows domain.

Cookie JSESSIONID có thể được phát với **Secure, HttpOnly và SameSite** thích hợp. Khi logout, việc thực sự chặn session hijacking phải dựa vào **server-side session invalidation**, không chỉ browser xóa cookie.

### 4.3. Vì sao public URL cũng có thể auto reauth?

Chỉ **permitAll("/signed-out")** không ngăn authentication filter chạy. Một browser đã dùng Negotiate có thể gửi **Authorization: Negotiate** chủ động trên request sau tùy HTTP auth cache/browser. Nếu SpnegoAuthenticationProcessingFilter vẫn nằm trong chain cho /signed-out, nó có thể xử lý header và tạo local Authentication ngay trên trang công khai.

Giải pháp minh họa bên dưới tách:

1. **Public/logout chain** cho **/**, **/logout** và **/signed-out**, không cài SPNEGO filter.
2. **Protected fallback chain** cho mọi URL còn lại, dùng SPNEGO entry point/filter/provider.

Tách chain giúp trang thông báo không tự challenge hoặc xử lý Negotiate **ở Spring**, nhưng **không ngăn tái đăng nhập** khi user thật sự truy cập /private. Nếu enterprise reverse proxy làm Kerberos acceptor trước Spring, còn phải exempt public logout URL tại **proxy**.

## 5. Vé Kerberos có thể còn hiệu lực theo nhiều trạng thái

| Client credentials sau logout | Hành vi có thể xảy ra |
| --- | --- |
| **TGT còn và KDC reachable; chưa cache ST** | Client xin service ticket mới qua TGS rồi có thể authenticate. |
| **ST đã cache còn hiệu lực, TGT không còn** | Client vẫn có thể dùng ST cho service tương ứng mà không hỏi KDC ngay. |
| **TGT còn nhưng KDC offline, không có ST** | Client có thể không lấy được ticket mới, Negotiate fail. |
| **TGT và ST đều hết hạn/mất, không có cách lấy lại** | Browser có thể không hoàn tất silent SSO; app tiếp tục challenge. |
| **Browser không allowlist site** | Browser có thể không gửi Negotiate tự động dù OS có TGT. |
| **SPN/keytab sai hoặc time skew/replay** | Server từ chối GSS validation dù ticket tồn tại ở client. |
| **User local account đã bị disable** | App có thể chặn login/access mới theo policy dù ticket Kerberos hợp lệ. |
| **Session S1 vẫn active trong app khác** | Logout app A không tự hủy phiên app B. |

TGT/ST có lifetime, renewable policies, encryption keys, KVNO và trust realms riêng. Không hứa rằng user bị disable trong Active Directory sẽ **mất ngay** mọi service ticket đã phát trước đó. Local app sessions, cached service tickets và permission caches có thể còn sống tới khi expiration hoặc revalidation. Muốn thu hồi quyền nhanh phải thiết kế **app-level authorization và session revocation**.

**Kerberos logout không giống CAS SLO/SAML2 SLO/OIDC RP-initiated logout.** Thậm chí khi IdP dùng Kerberos cho authentication đầu vào rồi phát SAML/OIDC ra SaaS, logout ở SaaS/IdP không tự xóa TGT của workstation.

## 6. Java 17 độc lập: mô phỏng local session khác tickets trên máy

**KerberosLogoutStateDemo.java** chạy chỉ với JDK 17, không cần KDC/AD/keytab. Đây là mô hình trạng thái, **không thực hiện Kerberos validation thật**. Khi code in **NEW_APP_SESSION_AFTER_KERBEROS**, nó **giả định** client đã có cách lấy ticket, GSS acceptor xác minh thành công và local account được cho phép; không thể thay bằng một boolean client gửi lên server trong production.

~~~java
public class KerberosLogoutStateDemo {
    record Tickets(boolean hasTgt, boolean hasServiceTicket,
                   boolean kdcReachable) {}

    static String accessPrivate(boolean localSession, Tickets tickets,
                                boolean activeAccount) {
        if (!activeAccount) {
            return "403 ACCOUNT_DISABLED";
        }
        if (localSession) {
            return "200 EXISTING_APP_SESSION";
        }

        boolean canTryKerberos = tickets.hasServiceTicket()
                || (tickets.hasTgt() && tickets.kdcReachable());
        if (!canTryKerberos) {
            return "401 NEED_KERBEROS_CREDENTIAL";
        }
        // Chỉ mô phỏng điều kiện, không xác minh GSS token.
        return "200 NEW_APP_SESSION_AFTER_KERBEROS";
    }

    public static void main(String[] args) {
        Tickets workstation = new Tickets(true, true, true);

        System.out.println("before logout: "
                + accessPrivate(true, workstation, true));

        // Logout local xóa app session, KHÔNG sửa OS credential cache.
        boolean appSession = false;
        System.out.println("after logout: session=" + appSession);
        System.out.println("cached tickets: tgt=" + workstation.hasTgt()
                + ", service=" + workstation.hasServiceTicket());

        System.out.println("signed-out page: 200 PUBLIC");
        System.out.println("revisit: "
                + accessPrivate(appSession, workstation, true));

        Tickets serviceOnly = new Tickets(false, true, false);
        System.out.println("cached service only: "
                + accessPrivate(false, serviceOnly, true));

        Tickets tgtWithKdc = new Tickets(true, false, true);
        System.out.println("TGT with KDC: "
                + accessPrivate(false, tgtWithKdc, true));

        Tickets offline = new Tickets(true, false, false);
        System.out.println("TGT without KDC: "
                + accessPrivate(false, offline, true));

        Tickets empty = new Tickets(false, false, false);
        System.out.println("no tickets: "
                + accessPrivate(false, empty, true));

        System.out.println("account revoked: "
                + accessPrivate(false, workstation, false));
    }
}
~~~

Chạy:

~~~bash
javac KerberosLogoutStateDemo.java
java KerberosLogoutStateDemo
~~~

**stdout chính xác:**

~~~text
before logout: 200 EXISTING_APP_SESSION
after logout: session=false
cached tickets: tgt=true, service=true
signed-out page: 200 PUBLIC
revisit: 200 NEW_APP_SESSION_AFTER_KERBEROS
cached service only: 200 NEW_APP_SESSION_AFTER_KERBEROS
TGT with KDC: 200 NEW_APP_SESSION_AFTER_KERBEROS
TGT without KDC: 401 NEED_KERBEROS_CREDENTIAL
no tickets: 401 NEED_KERBEROS_CREDENTIAL
account revoked: 403 ACCOUNT_DISABLED
~~~

**Điều học được:** xóa local session không xóa client tickets. Nếu user có ST còn hạn hoặc TGT và KDC reachable, có thể bắt đầu authentication mới. Kiểm local account active giúp chặn quyền theo policy. Trong thực tế, cached ticket vẫn có thể fail nếu sai SPN/keytab/clock/replay/realm/browser/GSS mechanism, nên demo **không tự định nghĩa chính sách chấp nhận Kerberos**.

## 7. Spring Boot 3.3.5 + Kerberos extension 2.1.0

Mẫu sau dùng **hai SecurityFilterChain** để cô lập public logout page khỏi custom SPNEGO filter. Điều kiện chạy Kerberos thật:

- KDC/Active Directory realm **EXAMPLE.ORG** tồn tại.
- User **alice@EXAMPLE.ORG** được realm và local app cho phép.
- SPN **HTTP/intranet.example.org** đăng ký đúng trên service account.
- Server có **keytab** chứa service keys đúng principal/KVNO/enctype và permission hạn chế.
- Browser IWA policy cho phép intranet.example.org; máy client có Kerberos credentials.
- HTTPS DNS/ingress phục vụ **https://intranet.example.org**; localhost HTTP không có cùng SPN.
- Session/CSRF cookies và reverse proxy được vận hành an toàn.

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>kerberos-local-logout</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties><java.version>17</java.version></properties>
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
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-core</artifactId>
            <version>2.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.security.kerberos</groupId>
            <artifactId>spring-security-kerberos-web</artifactId>
            <version>2.1.0</version>
        </dependency>
    </dependencies>
    <build><plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins></build>
</project>
~~~

**Spring Security Kerberos là extension**, không tự có chỉ vì starter-security. Ở family **2.x** dùng groupId **org.springframework.security.kerberos**; không copy API/coordinates 7.x sang Boot 3.3 mà chưa kiểm dependency compatibility. Mẫu phục vụ học, phải kiểm security advisories và test integration khi nâng version.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
server:
  port: 8080

app:
  kerberos:
    principal: "HTTP/intranet.example.org@EXAMPLE.ORG"
    keytab: "/etc/security/keytabs/http-intranet.keytab"
~~~

Đây là đường keytab giả định. Trong production mount file secret server-side, bảo vệ file ACL và rotation, không commit keytab vào Git. Đặt hostname public theo SPN, không tự dựng principal từ Host/X-Forwarded-Host chưa tin cậy.

### 7.3. Main class

**src/main/java/com/example/krblogout/KerberosLogoutApplication.java**

~~~java
package com.example.krblogout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosLogoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosLogoutApplication.class, args);
    }
}
~~~

### 7.4. SecurityConfig.java — public/logout và protected tách biệt

**src/main/java/com/example/krblogout/SecurityConfig.java**

~~~java
package com.example.krblogout;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository sessionContextRepository() {
        return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
    }

    @Bean
    UserDetailsService users() {
        return username -> {
            // Chỉ principal đã được provision trong local user store.
            if (!"alice@EXAMPLE.ORG".equals(username)) {
                throw new UsernameNotFoundException("Local account denied");
            }
            return User.withUsername(username)
                    .password("{noop}not-used-for-kerberos")
                    .authorities("ROLE_EMPLOYEE")
                    .build();
        };
    }

    @Bean
    SunJaasKerberosTicketValidator kerberosValidator(
            @Value("${app.kerberos.principal}") String principal,
            @Value("${app.kerberos.keytab}") String keytab) {
        SunJaasKerberosTicketValidator validator =
                new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(principal);
        validator.setKeyTabLocation(new FileSystemResource(keytab));
        return validator;
    }

    @Bean
    KerberosServiceAuthenticationProvider kerberosProvider(
            SunJaasKerberosTicketValidator validator,
            UserDetailsService users) {
        KerberosServiceAuthenticationProvider provider =
                new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(users);
        return provider;
    }

    @Bean
    @Order(1)
    SecurityFilterChain publicAndLogout(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        http
            .securityMatcher("/", "/signed-out", "/logout")
            .authorizeHttpRequests(auth -> auth
                .anyRequest().permitAll())
            .securityContext(sc -> sc
                .securityContextRepository(repository))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/signed-out")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("JSESSIONID")
                .permitAll());

        // Không đặt SpnegoAuthenticationProcessingFilter ở chain 1.
        // CSRF vẫn bật theo Spring Security default.
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain protectedApplication(
            HttpSecurity http, SecurityContextRepository repository,
            KerberosServiceAuthenticationProvider provider)
            throws Exception {

        SpnegoAuthenticationProcessingFilter spnego =
                new SpnegoAuthenticationProcessingFilter();
        spnego.setAuthenticationManager(new ProviderManager(provider));
        spnego.setSecurityContextRepository(repository);
        spnego.setSessionAuthenticationStrategy(
                new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(new SpnegoEntryPoint()))
            .securityContext(sc -> sc
                .securityContextRepository(repository))
            .authenticationProvider(provider)
            .addFilterBefore(spnego, BasicAuthenticationFilter.class);

        // Không đặt securityMatcher: chain 2 bảo vệ MỌI URL còn lại.
        return http.build();
    }
}
~~~

**Phân tích đúng phạm vi:**

1. **@Order(1)** chọn **/**, **/logout**, **/signed-out** và không gắn SPNEGO filter. Trên landing page public, Spring không tự kiểm Negotiate header hoặc gửi 401 challenge.
2. **LogoutFilter** của chain public xử lý **POST /logout** với CSRF token. GET /logout thường hiện confirmation form do Spring cung cấp.
3. **@Order(2)** là fallback protected chain **cho mọi URL không nằm ở chain 1**; không có lỗ hổng do khai báo matcher chỉ cho /private rồi bỏ quên route khác.
4. **SpnegoEntryPoint** gửi 401 Negotiate trên protected URLs khi anonymous.
5. **SpnegoAuthenticationProcessingFilter** nhận Authorization: Negotiate token và nhờ **ProviderManager** gọi **KerberosServiceAuthenticationProvider/SunJaasKerberosTicketValidator**.
6. **SecurityContextRepository** được chia sẻ giữa hai chains và filter, để logout xóa đúng persisted state và successful SPNEGO login có thể lưu session stateful.
7. **ChangeSessionIdAuthenticationStrategy** giúp giảm rủi ro session fixation khi tạo Authentication.
8. **UserDetailsService** giới hạn account có quyền; không auto-provision mọi user Kerberos thành admin.
9. **deleteCookies JSESSIONID** chỉ dọn cookie của app, không xóa OS TGT.
10. Không bật formLogin/Basic fallback ngầm hoặc disable CSRF chỉ để demo.
11. **Người dùng có vé Kerberos hợp lệ vẫn có thể authenticate lại trên /private**. Cấu hình này không giả vờ “block Kerberos re-login”.
12. Nếu có reverse proxy làm SPNEGO acceptor, phải kiểm authentication scope tại proxy ngoài Spring.

Đối với production, cần bổ sung phân quyền theo operation/resource/tenant, account revocation, session timeout/HA, keytab rotation, TLS, logs redaction và browser compatibility. Demo không tự sửa AD, KDC hoặc workstation.

### 7.5. Controller

**src/main/java/com/example/krblogout/Pages.java**

~~~java
package com.example.krblogout;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class Pages {

    @GetMapping("/")
    public String home() {
        return "Public home. Visit /private or GET /logout.";
    }

    @GetMapping("/signed-out")
    public String signedOut() {
        return "Local application session ended. "
            + "Kerberos tickets on your workstation may remain valid.";
    }

    @GetMapping("/private")
    public String privatePage(Authentication authentication) {
        return "Kerberos authenticated: " + authentication.getName();
    }
}
~~~

### 7.6. Run và quan sát

~~~bash
mvn spring-boot:run
~~~

Nếu app khởi động và keytab/KDC/browser sandbox được cấu hình đúng:

1. **GET /** trả public text, không dùng SPNEGO filter trong Spring.
2. **GET /private** khi anonymous có thể nhận 401 Negotiate; browser dùng IWA nếu hostname và policy cho phép.
3. **alice@EXAMPLE.ORG** có vé hợp lệ và được localUsers cho phép, GET /private trả **Kerberos authenticated: alice@EXAMPLE.ORG**.
4. **GET /logout** hiển thị trang xác nhận logout (nếu CSRF mặc định bật).
5. **POST /logout** với CSRF đúng làm local logout và redirect **/signed-out**.
6. **GET /signed-out** không tự chạy SPNEGO filter ở Spring, thông báo local logout thành công.
7. **GET /private lại** có thể tự đăng nhập Kerberos và tạo session mới, ngay cả khi user chưa nhập password.
8. Nếu local user bị disable hoặc role/tenant không đạt, ứng dụng phải deny theo local policy, không phụ thuộc việc có ticket.

Không có KDC/keytab thật thì không thể khẳng định end-to-end Kerberos login thành công. URL example.org trong bài là ví dụ, không phải một CAS/SAML IdP hay domain Kerberos thực.

## 8. Phân biệt ba kiểu “muốn ngăn truy cập lại”

### 8.1. Người dùng muốn thấy màn hình “đã đăng xuất”

Đây là yêu cầu UX. Dùng **POST logout + public /signed-out không SPNEGO** để hiển thị thông báo trước khi người dùng chủ động quay lại protected resource. Đừng hứa rằng thao tác này cấm Kerberos silent authentication về sau.

### 8.2. Doanh nghiệp muốn thu hồi mọi local sessions

Ứng dụng có thể dùng **Spring Session, SessionRegistry, indexed session repository** hoặc session version/revoked-before timestamp để invalidate những HttpSessions đang hoạt động của user theo policy, kể cả multi-node. Nhưng nếu user còn credentials Kerberos và account còn được local app chấp thuận, login **mới** vẫn có thể được cấp.

Cần **revoke application sessions + local account permission gate** nếu muốn chặn cả access sau đó. Một session đã được phát không tự nhận mọi thay đổi quyền từ AD nếu app không kiểm lại.

### 8.3. Tác vụ nhạy cảm bắt buộc user hiện diện hoặc MFA mới

Nếu user click Logout và chính sách đòi **xác thực có tương tác** trước khi vào payroll/admin, HTTP 401 Negotiate không đủ vì browser có thể silent reauth. Cần một **step-up assurance policy** (ví dụ WebAuthn/FIDO2 hoặc MFA được IdP/app chứng minh) và kiểm freshness, operation, device, account state trước khi cho phép. Có thể giữ Kerberos là bootstrap identity nhưng không coi nó tự thỏa yêu cầu fresh MFA.

**Không dùng mẹo tắt replay hoặc chấp nhận token GSS chưa kiểm** để giải quyết UI logout. Chấp nhận 401 Negotiate hoặc chuyển sang IdP chuẩn tùy policy; bảo vệ protocol trước tiên.

## 9. Các lệnh client Kerberos và giới hạn quyền

### Windows

Trên máy client trong logon session được phép:

~~~powershell
klist
klist tgt
klist tickets
~~~

**klist purge** có thể xóa Kerberos tickets của **logon session được chọn**. Chỉ thực hiện trong lab hoặc theo quy trình IT, vì nó ảnh hưởng nhiều ứng dụng dùng Kerberos, không chỉ một website:

~~~powershell
# CHỈ KHI ĐƯỢC PHÊ DUYỆT TRÊN MÁY/SESSION CỦA MÌNH:
klist purge
~~~

**Không chạy lệnh đó trên web server với kỳ vọng nó xóa tickets trên browser của người dùng.** Nó tác động tới credential cache của nơi/identity chạy lệnh, có tùy chọn nhắm logon session và privilege tương ứng. Ngay cả sau purge, một workstation đã login có thể reacquire tickets qua OS domain credentials/SSO policy. Việc purge không tự xóa active HttpSessions trên những ứng dụng khác.

### MIT Kerberos trên Linux/macOS

~~~bash
klist
# CHỈ trong environment được quản trị, hiểu rõ impact:
kdestroy
~~~

**kdestroy** xóa Kerberos credential cache được chọn trong môi trường MIT Kerberos, không phải một lệnh vô hiệu mọi browser/OS credentials trên mọi thiết bị. Với KCM, SSSD, keyring, ccache khác hoặc GSS contexts còn trong process, hành vi phụ thuộc platform.

### OS logoff so với lock screen

- **Sign-out/logoff khỏi workstation OS session** kết thúc phiên user ở cấp thiết bị theo platform policy, thường là phương án cần thiết khi rời máy dùng chung.
- **Lock screen** không xóa TGT; chỉ hạn chế truy cập máy nếu kẻ khác không thể mở khóa.
- **Đóng tab/browser hoặc dùng private window** không bảo đảm OS TGT biến mất.
- **Web JavaScript không có quyền phổ quát gọi lệnh OS để thu hồi Kerberos TGT** và không nên yêu cầu quyền ấy.

Đối với kiosk/hot desk, kết hợp logout ứng dụng, OS session management, user switching, device policy và local account/session timeouts. Không nói rằng logout web app đủ để một máy vẫn mở khóa trở thành an toàn cho người tiếp theo.

## 10. Account disable/AD revocation: không đồng nghĩa hủy mọi cached ticket

Khi AD admin disable user, KDC có thể từ chối cấp **tickets mới** theo policy, nhưng:

- **Service ticket phát trước đó** có thể còn hiệu lực tới khi hết hạn hoặc tới thời điểm service kiểm thêm policy.
- **TGT đã cấp** có lifetime riêng; hành vi KDC với ticket requests tiếp theo phụ thuộc account state và realm policy.
- **Local Spring session** đang tồn tại có thể tiếp tục được ứng dụng tin nếu không có revocation/session revalidation.
- **UserDetailsService cache** hoặc roles/tenant membership chưa refresh có thể giữ quyền đã thu hồi.
- **External proxy** hoặc upstream IdP có session của riêng nó.

Muốn thu hồi gần tức thì cho API nhạy cảm cần:

1. **Server-side local account state** là nguồn quyền có thể cập nhật.
2. Chặn cả **new Kerberos Authentication** cho account disabled, không tự provision lại.
3. Recheck **roles/tenant/resource permissions** theo risk-based TTL/version mỗi request/tác vụ nhạy cảm.
4. Revoke app sessions trên **mọi nodes** bằng shared store/session registry.
5. Xóa/revalidate permission caches và các issued tokens nội bộ khác.
6. Có monitoring/audit, reason codes và policy cho logout all devices.
7. Không quảng bá “đã thu hồi hết Kerberos tickets” nếu không có phương pháp chứng minh ở OS/KDC.

**Authorization khác authentication:** Kerberos ticket hợp lệ chỉ nhận diện principal; app quyết định account còn active và có được phép vào resource hay không.

## 11. Reverse proxy, browser auth cache và các race conditions

Nếu proxy (IIS, Apache, Nginx + module hoặc gateway) làm **Kerberos acceptor**, nó có thể authenticate browser **trước khi request tới Spring**. Spring app logout chỉ kết thúc local state; proxy vẫn có thể chứng thực lại browser và gửi **verified identity header** tới backend.

Khi đó:

- Public /signed-out phải được proxy **exempt authentication** nếu muốn tránh challenge.
- Backend chỉ tin identity header được proxy ghi đè qua trusted channel, không nhận trực tiếp **X-User/X-Remote-User** từ Internet.
- Chính sách forced logout/re-auth phải liên quan cả proxy session nếu có.
- Browser may send Negotiate token preemptively theo auth cache; test thực tế trên Edge/Firefox được doanh nghiệp quản trị.

Multi-tab/race:

- Tab A POST /logout khi Tab B đã bắt đầu request với S1; cần xác minh backend xử lý session invalidation an toàn.
- Tab B sau logout có thể lấy S2 mới qua silent SPNEGO; đừng coi đó là S1.
- Browser cached HTML/JS hoặc service worker có thể còn hiển thị dữ liệu nhạy cảm sau logout: áp dụng **Cache-Control: no-store** khi phù hợp và reset frontend state.
- Load balancer/cluster phải invalidate đúng shared session; kiểm Spring Session Redis/JDBC/sticky sessions.
- Session cookie cũ có thể còn trong browser nhưng phải bị server từ chối.

## 12. Chẩn đoán lỗi logout và silent login

| Biểu hiện | Khả năng thực tế | Cách kiểm |
| --- | --- | --- |
| Logout xong redirect /private và lập tức 200 | Protected URL trigger Kerberos SSO mới. | Redirect public /signed-out, đối chiếu S1/S2. |
| /signed-out permitAll nhưng app vẫn authenticate | SPNEGO filter xử lý preemptive Authorization. | Public chain không gắn filter, kiểm proxy. |
| POST /logout trả 403 | CSRF token thiếu/sai, không hẳn lỗi Kerberos. | GET confirmation, POST với CSRF. |
| GET /logout không invalidate session | Đúng CSRF default. | Dùng POST logout, không disable CSRF. |
| S1 còn được chấp nhận sau logout | LogoutFilter/repository/shared session invalidation thật sự lỗi. | Test old cookie S1, logs và session store. |
| /private trả 200 ngay cả sau xóa cookie | Browser reauth Kerberos, phát S2. | Trace Negotiate và session IDs. |
| klist purge mà browser vẫn silent login | Ticket được reacquire, purge sai logon session/cache hoặc OS policy. | Kiểm đúng client cache và IT policy. |
| AD account disabled nhưng user vẫn vào | Cached ST/local session hoặc permission cache còn. | Local account gate + session revocation. |
| Clear-Site-Data chạy mà TGT còn | Header không điều khiển OS credential cache. | Phân biệt browser site state và Kerberos. |
| Logout node A, node B vẫn authenticated | Session store/cluster không đồng bộ. | Test Redis/JDBC session, invalidation. |
| User thiếu role vẫn 200 sau login | Chỉ kiểm authenticated, chưa check resource permission. | Method/service authorization, tenant ACL. |
| Logout rồi tab khác hiển thị report | Frontend cache, request race hoặc silent reauth. | No-store, session trace, frontend reset. |
| 401 Negotiate loop khi app cần login | Browser không gửi ticket, keytab/SPN/clock lỗi hoặc filter không lưu context. | KDC/SPN, browser policy, SecurityContextRepository. |
| Trên kiosk người sau vào được dữ liệu | OS session vẫn mở và TGT còn. | OS logout/kiosk policy, step-up cho sensitive actions. |

Một báo cáo QA tốt phân biệt **LOCAL_LOGOUT** với **KERBEROS_REAUTH**, không lưu raw Authorization: Negotiate, JSESSIONID, keytab, TGT hoặc service tickets.

## 13. Ma trận test positive/negative

Dùng **Kerberos KDC/AD sandbox** cho integration tests; dùng Java 17 standalone ở phần 6 để giải thích logic không cần realm thật.

| # | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| 1 | POST /logout có CSRF đúng | Session S1 bị invalidated, SecurityContext cleared. |
| 2 | POST /logout thiếu CSRF | 403, không logout trái phép. |
| 3 | GET /logout với CSRF bật | Confirmation form thay vì state-changing GET. |
| 4 | GET /signed-out sau logout | Public 200, không HTTP Negotiate từ Spring. |
| 5 | Browser preemptive Negotiate tới /signed-out | Chain public không chạy SPNEGO filter. |
| 6 | Dùng lại cookie S1 sau logout | Server không chấp nhận session cũ. |
| 7 | TGT/ST còn, GET /private sau logout | Có thể Kerberos authentication mới tạo S2. |
| 8 | Không có TGT/ST và không thể acquire | Không tự tạo session; 401/fallback theo policy. |
| 9 | ST cached còn nhưng TGT hết | Browser có thể authenticate tới cùng SPN theo policy. |
| 10 | TGT còn, ST chưa cache, KDC reachable | Browser có thể xin ST mới. |
| 11 | TGT còn, ST chưa cache, KDC offline | Không lấy ST mới, fail nếu không có cơ chế khác. |
| 12 | Browser không allowlist intranet | Có thể không gửi Negotiate tự động. |
| 13 | Service ticket expired/replayed/for wrong SPN | Kerberos validator từ chối. |
| 14 | Account disabled locally | Không cấp quyền mới dù Kerberos ticket hợp lệ. |
| 15 | Active session nhưng role bị revoke | Policy revalidation chặn quyền nhạy cảm. |
| 16 | Request từ tab B sau tab A logout | S1 fail, S2 có thể tạo nếu Kerberos còn. |
| 17 | Multi-node shared session invalidation | Session bị revoke trên mọi nodes. |
| 18 | Clear-Site-Data chỉ xóa site data | TGT của OS vẫn còn nếu chưa bị quản trị xóa. |
| 19 | klist purge đúng user logon session | Tickets ở cache đó bị xóa; có thể reacquire theo OS policy. |
| 20 | kdestroy MIT cache | Cache được chọn bị xóa, không tự logout mọi app HTTP. |
| 21 | OS sign-out rồi user khác login | User mới không dùng lại old OS logon context. |
| 22 | Spring public chain không match unknown route | Protected fallback chain vẫn yêu cầu authentication. |
| 23 | Reverse proxy làm SPNEGO acceptor | Public logout scope ở proxy được test riêng. |
| 24 | Logout all application sessions | Sessions revoked nhưng new Kerberos login còn phụ thuộc account policy. |
| 25 | Sensitive action yêu cầu step-up | Silent SPNEGO không tự thỏa MFA freshness. |
| 26 | Application logout không ảnh hưởng app B | Đúng; B có session riêng. |
| 27 | Domain account disable, cached ticket vẫn tồn tại | Local authorization chặn access theo policy. |
| 28 | User nhìn thấy dữ liệu trong browser cache sau logout | Cache-Control/no-store/frontend reset theo risk. |
| 29 | Session fixation khi re-login Kerberos | Session ID rotation/strategy đúng. |
| 30 | Browser tiếp tục có TGT khi GET /signed-out | Trang công khai vẫn hiển thị mà không auto reauth ở Spring. |

**Không đánh giá logout chỉ bằng HTTP status 200 của /private.** Bắt buộc phân biệt **session cũ có bị hủy** và **authentication mới có được bắt đầu** hay không.

### Trace để QA

~~~text
POST /logout (CSRF OK)
  -> 302 /signed-out; S1 invalidated

GET /signed-out
  -> 200 PUBLIC; no Spring Negotiate challenge

GET /private
  -> 401 Negotiate
  -> browser may send Authorization Negotiate
  -> GSS validation + local UserDetails
  -> if permitted, new session S2
~~~

Ghi trace ID và internal actor ID đã xử lý privacy, không ghi raw session IDs/tickets. Trong các test tự động có thể so **S1 != S2** bằng test-only identifiers, không xuất chúng ra logs ngoài môi trường bảo mật.

## 14. Checklist vận hành

**Logout và session**

- [ ] POST /logout được xử lý bởi Spring LogoutFilter với CSRF protection.
- [ ] HttpSession invalidated, Authentication/SecurityContext/repository cleared.
- [ ] Session cookie cleanup tương thích name/domain/path, session cũ không hợp lệ.
- [ ] Public /signed-out không SPNEGO filter/challenge, kể cả preemptive Negotiate.
- [ ] Protected fallback chain không bỏ lọt endpoints ngoài allowlist.
- [ ] SecurityContextRepository đồng nhất giữa SPNEGO success và logout.
- [ ] Multi-node session invalidation, session fixation và concurrent requests được test.

**Kerberos và user policy**

- [ ] Không giả định web app có thể thu hồi TGT/ST trên workstation.
- [ ] Browser IWA/SPN/keytab/KDC/time/replay/TLS vẫn được bảo vệ.
- [ ] User disabled/membership revoked không tự được phép chỉ vì Kerberos pass.
- [ ] Không thực thi klist purge/kdestroy ở client khi user chỉ nhấn logout website.
- [ ] Thiết kế step-up/fresh MFA nếu tác vụ cần user presence.
- [ ] Với proxy Kerberos, public/logout exception được cấu hình ở proxy.
- [ ] Shared workstation có OS logoff/kiosk reset và thông điệp phù hợp.

**Kiểm thử và giám sát**

- [ ] Test logout S1, silent SPNEGO S2 và trường hợp không còn tickets.
- [ ] Test preemptive Negotiate trên landing page, browser policy, Firefox/Edge.
- [ ] Test account disable, permission revocation, multi-tab, app B và HA.
- [ ] Dữ liệu nhạy cảm có cache policy phù hợp, không leak qua frontend sau logout.
- [ ] Không log Kerberos tokens, ticket caches, credentials, raw cookies.
- [ ] Không gắn nhãn “global/domain logout” cho thao tác local logout.

## 15. Câu hỏi ôn tập

**1. Vì sao logout rồi lại vào intranet không cần mật khẩu?**  
Vì Spring đã xóa local session, nhưng client còn TGT/ST hoặc có thể xin ticket mới và thực hiện **một authentication mới** bằng Kerberos.

**2. POST /logout của Spring Security có hủy được Windows TGT không?**  
Không. Nó chỉ kiểm soát session/SecurityContext/cookie thuộc ứng dụng, không làm việc thay OS credential manager.

**3. TGT đã mất nhưng service ticket còn, browser có thể tiếp tục SSO không?**  
Có thể, nếu service ticket còn hợp lệ cho SPN đó và GSS acceptor chấp nhận theo policy.

**4. Vì sao chỉ permitAll cho /signed-out chưa đủ?**  
Authentication filters vẫn có thể chạy và xử lý Negotiate header; public chain **không chứa SpnegoFilter** giúp tránh silent reauth ngay tại thông báo.

**5. GET /logout và POST /logout khác nhau thế nào khi CSRF bật?**  
GET thường hiển thị confirmation form; POST có CSRF hợp lệ thực hiện logout.

**6. Xóa JSESSIONID mà user lại authenticated có chứng minh logout lỗi?**  
Không. Phải kiểm session cũ S1 có bị invalidated hay không; user có thể được phát session mới S2 sau Kerberos.

**7. Có thể chạy klist purge từ Spring server để xóa tickets trên client không?**  
Không. Lệnh tác động tới cache/logon session trên máy chạy lệnh, không phải remote browser.

**8. Tắt user trong AD có hủy tức thì mọi cached ST/session không?**  
Không thể khẳng định; còn phụ thuộc ticket lifetime, KDC, local session, service và permission cache. Cần local account gate/revocation.

**9. Muốn người dùng phải MFA sau logout dù vẫn có TGT nên làm thế nào?**  
Dùng explicit step-up/MFA freshness policy, không dựa vào 401 Negotiate để bắt browser nhập password.

**10. Nếu proxy xử lý Kerberos trước Spring, logout success page phải sửa ở đâu?**  
Cần cả **proxy authentication routing/exemption** lẫn Spring session policy; chỉ tách SecurityFilterChain phía backend có thể chưa đủ.

## 16. Tài liệu chuẩn và API

1. [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): GET/POST logout, CSRF, SecurityContextLogoutHandler và success handler.
2. [Spring Security 6.5 — LogoutConfigurer Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/LogoutConfigurer.html): invalidateHttpSession, clearAuthentication, deleteCookies, logoutSuccessUrl.
3. [Spring Security 6.5 — SecurityContextLogoutHandler](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/logout/SecurityContextLogoutHandler.html): clear context và invalidate session.
4. [Spring Security Kerberos — SpnegoAuthenticationProcessingFilter 2.x API](https://docs.spring.io/spring-security-kerberos/docs/current/api/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): filter, SecurityContextRepository, SessionAuthenticationStrategy.
5. [Spring Security Kerberos — Reference](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SPNEGO entry point, validator, provider.
6. [Microsoft Learn — klist on Windows](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/klist): TGT/service tickets, purge theo logon session.
7. [MIT Kerberos — kdestroy](https://web.mit.edu/kerberos/krb5-latest/doc/user/user_commands/kdestroy.html): client credential cache lifecycle.
8. [RFC 4120 — Kerberos V5](https://www.rfc-editor.org/rfc/rfc4120): TGT, service tickets, AS/TGS, ticket lifetime.
9. [RFC 4559 — SPNEGO HTTP authentication](https://www.rfc-editor.org/rfc/rfc4559): 401 Negotiate, GSS tokens và giới hạn HTTP protection.
10. [Microsoft Edge AuthServerAllowlist](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-browser-policies/authserverallowlist): integrated authentication theo browser/host policy.
11. [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): SecurityContextRepository, session fixation, concurrency.
12. [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF defense cho logout và state-changing operations.

**Kết luận:** Spring Security logout **chỉ kết thúc phiên của ứng dụng**; nó không xóa **TGT/service tickets** đang nằm trên workstation. Vì vậy browser vẫn có thể tự đăng nhập lại bằng **Kerberos SPNEGO** khi người dùng mở một URL được bảo vệ. Thiết kế đúng là **POST logout có CSRF, invalidate HttpSession/SecurityContext, public signed-out page không chạy SPNEGO**, đồng thời dùng **account authorization/revocation, step-up policy và OS session management** nếu cần ngăn truy cập tiếp.
