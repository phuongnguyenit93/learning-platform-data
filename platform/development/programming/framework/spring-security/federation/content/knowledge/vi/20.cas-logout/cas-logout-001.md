# Phân biệt đăng xuất ứng dụng, đăng xuất CAS và Single Sign-Out

**Module:** Spring Security – federation  
**Chủ đề cha:** Đăng xuất CAS  
**Áp dụng:** CAS Protocol với Apereo CAS Server/Java CAS Client, Spring Security 6.x, Spring Boot 3.x, Java 17+, ứng dụng Servlet.

## 1. Ba kiểu đăng xuất không có cùng phạm vi

CAS đem lại **Single Sign-On (SSO)**: người dùng xác thực ở CAS Server, nhận Service Ticket (**ST**) để vào một hoặc nhiều ứng dụng. Nhưng sau khi ST được xác minh, mỗi ứng dụng thường tạo **HttpSession riêng**, do đó việc đăng xuất có ít nhất ba ý nghĩa:

1. **Đăng xuất ứng dụng (local/application logout):** portal xóa SecurityContext và HttpSession **của portal**, không đụng trực tiếp tới phiên CAS hoặc ứng dụng khác.
2. **Đăng xuất CAS (CAS logout):** CAS Server thu hồi Ticket-Granting Ticket (**TGT**) và trạng thái đăng nhập trung tâm, không tự có quyền xóa HttpSession trong JVM của từng ứng dụng.
3. **Single Sign-Out (SLO):** CAS Server gửi **logout notifications** tới những ứng dụng đã tham gia phiên SSO; từng CAS client cố gắng tìm và hủy **local session tương ứng**.

| Hành động | CAS TGT/SSO | Portal HttpSession | Reports HttpSession |
| --- | --- | --- | --- |
| Local logout tại portal | Có thể còn | **Hết** | Có thể còn |
| CAS logout, không SLO | **Hết** | Có thể còn | Có thể còn |
| CAS logout + SLO thành công toàn bộ | **Hết** | **Hết** | **Hết** |
| CAS logout + SLO thất bại ở reports | **Hết** | Hết nếu callback thành công | **Có thể còn** |

**Điểm quan trọng nhất:** một trang hiển thị “đã đăng xuất” chỉ có thể khẳng định phạm vi mà hệ thống **thực sự thu hồi**. CAS SLO được Apereo mô tả là **best effort**; mạng, browser, cấu hình hoặc session store có thể làm một vài ứng dụng bỏ sót thông báo.

## 2. CAS TGT/TGC, Service Ticket và phiên ứng dụng

~~~text
Browser
  +-- TGC cookie cho domain sso.example.org
  |      -> CAS Server -> TGT (SSO session)
  |
  +-- Cookie portal.example.org
  |      -> Portal HttpSession -> SecurityContext
  |
  +-- Cookie reports.example.org
         -> Reports HttpSession -> SecurityContext

CAS login có thể cấp:
  ST-P (chỉ dành cho portal)
  ST-R (chỉ dành cho reports)
~~~

- **TGT (Ticket-Granting Ticket):** trạng thái SSO trung tâm do CAS Server quản lý, có policy thời hạn/thu hồi riêng.
- **TGC (Ticket-Granting Cookie):** cookie browser tham chiếu tới TGT tại CAS. Cookie này không phải cookie ứng dụng.
- **ST (Service Ticket):** chứng từ opaque, service-bound, dùng **một lần thử xác minh**. Portal gửi ST tới CAS **/serviceValidate**, sau khi xác thực thành công tạo local Authentication.
- **SecurityContext/HttpSession:** trạng thái đăng nhập do mỗi Service Provider/CAS client quản lý, thường được Spring Security dùng cho các request tiếp theo.
- **ST→HttpSession mapping:** CAS client hỗ trợ SLO cần liên kết ticket identifier của lần login với session cục bộ để sau này hủy đúng phiên khi nhận SLO callback.

**ST hết hạn hoặc đã bị tiêu thụ không tự làm local HttpSession hết hạn.** Nó là bằng chứng dùng tại callback đăng nhập, không phải access token phải gửi lại mỗi request. **CAS TGT hết** cũng không mặc nhiên làm mọi ứng dụng biết ngay; app có thể vẫn sử dụng SecurityContext đã lưu.

## 3. Đăng xuất ứng dụng trong Spring Security

Một nút logout cục bộ thường gửi **POST /logout** kèm CSRF token hợp lệ. Spring Security 6 Servlet có **LogoutFilter**; các LogoutHandler chuẩn xử lý việc:

1. Invalidate local HttpSession.
2. Clear SecurityContext trong SecurityContextHolder và SecurityContextRepository.
3. Dọn các remember-me credentials/CSRF token đang dùng khi phù hợp.
4. Phát logout event và dùng LogoutSuccessHandler để chuyển tới trang thông báo.

Ví dụ Java DSL:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/logged-out").permitAll()
        .anyRequest().authenticated())
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

Đây là **fragment**, cần đặt trong một **SecurityFilterChain** hoàn chỉnh. Nó chỉ kết thúc **local session**, không gọi CAS **/logout**. Nếu user còn TGC/TGT hợp lệ, khi mở trang protected ở portal, Spring Security sẽ đưa browser về CAS login, CAS có thể cấp **ST mới** và người dùng quay lại portal **không cần nhập mật khẩu**.

Ví dụ dòng thời gian:

~~~text
09:00  Browser đăng nhập CAS và portal.
09:10  Browser POST /logout tại portal -> local session hết.
09:11  User GET /private tại portal -> redirect sang CAS /login.
09:11  CAS TGT vẫn còn -> cấp ST mới cho portal.
09:11  Portal validate ST mới -> tạo local HttpSession mới.
~~~

Không phải ST cũ đã được dùng lại. Nếu người dùng nói “logout xong vẫn đăng nhập lại được”, cần kiểm tra **TGT CAS còn không**, chứ không kết luận ngay SecurityContextLogoutHandler hỏng.

### Local idle timeout cũng độc lập

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
~~~

**30m** ở đây là idle timeout của Servlet HttpSession tại ứng dụng, **không phải** TGT timeout, cookie TGC lifetime hoặc Service Ticket TTL. CAS không phải session manager của portal/reports; mỗi bên có policy idle/absolute/revocation riêng.

## 4. Đăng xuất CAS Server

URL ví dụ:

~~~text
https://sso.example.org/cas/logout
~~~

Theo CAS Protocol, **/logout** kết thúc **CAS SSO session**, hủy/không cho sử dụng lại TGT hiện hành và xóa hoặc vô hiệu hóa TGC liên quan.

Khi CAS SSO session đã hết, lần sau browser tới **CAS /login** không thể dùng lại TGT đó để nhận ST như trước; người dùng có thể phải xác thực lại theo CAS policy. Tuy nhiên:

- Portal đã có local HttpSession có thể **vẫn đăng nhập** nếu không có SLO/revocation.
- Reports đã có local HttpSession cũng có thể **vẫn đăng nhập**.
- Ngay cả khi browser đã xóa TGC, cookie portal/reports là **cookie độc lập**.
- CAS Server không thể tự gọi HttpSession.invalidate() bên trong một JVM ứng dụng khác.
- Một session CAS trên máy này không nhất thiết đồng nghĩa toàn bộ thiết bị của user cũng được logout; chính sách all-device logout là bài toán khác.

CAS có thể cho phép redirect sau logout qua **service parameter** tùy phiên bản/cấu hình. Không lấy một return URL tự do từ browser để redirect (open redirect); đích phải thuộc **allowlist/registered services** và chức năng redirect phải được CAS Server cho phép.

### Đăng xuất CAS chưa đồng nghĩa với Single Sign-Out

Nếu portal chỉ redirect browser tới CAS /logout nhưng **reports không có SLO receiver**, CAS TGT có thể đã được thu hồi, trong khi reports local session vẫn cho phép truy cập.

Do đó phải định nghĩa “global logout” trong yêu cầu sản phẩm:

- Kết thúc **SSO session tại CAS**?
- Hủy các **application sessions được liên kết với TGT ấy**?
- Hay hủy **tất cả sessions trên mọi thiết bị**, gồm cả những hệ thống ngoài CAS?

Ba mục tiêu đó có độ khó và phạm vi khác nhau. Không ghi “logout mọi nơi” trên UI chỉ vì một lần redirect đến CAS /logout.

## 5. Single Sign-Out là cơ chế điều phối thu hồi local sessions

Khi một CAS TGT bị explicitly expired, CAS có thể phát SLO notifications tới những registered services mà user đã dùng trong SSO session. Các trường hợp idle timeout cũng có thể kích hoạt theo CAS implementation/policy.

~~~text
Browser          CAS Server           Portal SP            Reports SP
   |                 |                    |                     |
   | /cas/logout     |                    |                     |
   |---------------->| Xóa TGT/TGC        |                     |
   |                 |--- SLO callback -->|                     |
   |                 |                    | invalidate session  |
   |                 |------------------------------ SLO callback |
   |                 |                    |          invalidate  |
   |<----------------| logout page        |                     |
~~~

Thứ tự arrows minh họa, CAS có thể gửi asynchronous; một số callback có thể không thành công. **SLO là thông báo, không phải transaction ACID hay xác nhận tất cả ứng dụng đã thực thi thành công.**

CAS Server thường biết những service nào đã đăng nhập nhờ các ST cấp trong cùng SSO relationship. Mỗi CAS client cần cách mapping **ST identifier → local session**, rồi khi nhận notification, invalidate đúng local HttpSession.

### Những điều kiện để SLO có hiệu lực

1. CAS Server bật SLO cho **CAS Protocol** và đúng service registration.
2. Service registry công bố service URL hoặc **logoutUrl** mà CAS Server có thể liên lạc.
3. Ứng dụng có **SingleSignOutFilter** hoặc receiver tương đương của CAS client.
4. CAS client đã theo dõi login ticket và lưu mapping tới session cục bộ.
5. Callback được chuyển đến receiver qua đúng HTTP method/binding.
6. Receiver nhận/trust notification đúng chính sách bảo mật.
7. Mapping còn tồn tại và chỉ đến local HttpSession đang dùng.
8. Với nhiều node, session và correlation mapping có khả năng chia sẻ/định tuyến đúng.
9. Session được invalidate thật; browser request sau không còn SecurityContext trước đó.
10. Có monitoring và hành vi an toàn cho trường hợp SLO không hoàn tất.

**Không mặc định** mọi ứng dụng đã dùng CAS để login đều hỗ trợ SLO chỉ vì CAS Server bật nó. Mỗi service cần client library/receiver và cấu hình phù hợp.

## 6. Back-channel SLO: CAS Server gọi HTTP POST tới ứng dụng

**Back-channel** là CAS Server gửi callback **server-to-server**, không đợi browser người dùng mang thông báo tới từng ứng dụng.

~~~text
CAS Server
  |
  | POST tới registered service URL hoặc logoutUrl
  | form field logoutRequest = XML LogoutRequest
  v
SingleSignOutFilter tại Portal
  |
  | parse SessionIndex (CAS ST identifier)
  | lookup mapping từ ticket ID sang HttpSession
  v
HttpSession.invalidate()
  |
  +-- Browser request sau không còn Authentication cũ.
~~~

CAS Protocol truyền thống dùng XML **có dạng SAML 2.0 LogoutRequest**:

~~~xml
<samlp:LogoutRequest
    xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="_cas_logout_example"
    Version="2.0"
    IssueInstant="2026-11-07T05:00:00Z">
  <saml:NameID>employee-847</saml:NameID>
  <samlp:SessionIndex>ST-portal-login-example</samlp:SessionIndex>
</samlp:LogoutRequest>
~~~

Đây chỉ là **minh họa cấu trúc**, không phải request SLO hợp lệ để gửi tới ứng dụng thật. CAS Protocol SLO có thể dùng **SessionIndex là identifier của Service Ticket**; client tra mapping ST→HttpSession để hủy phiên.

**SessionIndex không phải JSESSIONID**. Nếu receiver chỉ gọi **request.getSession(false)**, thường sẽ không tìm được phiên browser cần hủy, vì back-channel request **từ CAS Server** thường không mang cookie phiên của user.

**Phân biệt giao thức:** XML CAS LogoutRequest có hình dạng tương tự SAML2, nhưng SLO của **CAS Protocol** không tự đồng nhất với **SAML 2.0 Web Browser Single Logout**. Không dùng Spring Security **saml2Logout()** như cách thay thế trực tiếp cho CAS client **SingleSignOutFilter**.

## 7. Front-channel SLO: thông báo đi qua browser

Apereo CAS cũng có các biến thể **front-channel** (ví dụ AJAX/JSONP hoặc iframe tùy server version/service policy). Browser đang ở trang logout CAS được yêu cầu liên lạc tới logout endpoints của các ứng dụng.

~~~text
CAS logout page trong browser
    |
    +--> portal front-channel logout callback
    +--> reports front-channel logout callback
    +--> billing front-channel logout callback
~~~

**Không mặc định Java CAS Client hỗ trợ mọi front-channel variant.** Một số phương án phụ thuộc browser, cookie SameSite, chính sách chặn third-party cookie, CORS/CSP, thời điểm tab bị đóng và endpoint có thể nhận GET/JSONP. Phải đối chiếu **CAS Server logoutType**, cấu hình client, network/browser và protocol tương ứng.

| Tiêu chí | Back-channel | Front-channel |
| --- | --- | --- |
| Đường truyền | CAS Server → app server | Qua browser người dùng |
| Cần browser ở lại trang logout? | Không phải điều kiện giao hàng chính | Thường có phụ thuộc |
| Mang cookie của user? | Không mặc định | Tùy cookie/browser policy |
| Khả năng thông báo khi browser rời trang | Có thể, nếu CAS Server vẫn gửi được | Thường giảm |
| Rủi ro | App unreachable, timeout, sai correlation/store | Browser bị chặn, cross-site cookie, đóng tab |
| Bảo vệ callback | Trust server-to-server, TLS, kiểm soát nguồn | Trust request, browser security, token/correlation |
| Độ chắc chắn | Vẫn **best effort** | Vẫn **best effort** |

**Không khẳng định back-channel bảo đảm thu hồi mọi session.** Nó chỉ giảm phụ thuộc browser; việc hủy đúng HttpSession vẫn do từng ứng dụng chịu trách nhiệm.

## 8. CAS SLO client map Service Ticket tới HttpSession ra sao?

~~~text
Lúc portal CAS login:
    GET /login/cas?ticket=ST-P
                |
                +--> CasAuthenticationFilter validate ST-P
                |
                +--> CAS SLO client lưu:
                     ST-P -> portal HttpSession P-1

Lúc CAS logout:
    POST logoutRequest
    SessionIndex = ST-P
                |
                +--> tra ST-P -> HttpSession P-1
                |
                +--> P-1.invalidate()
~~~

CAS client không cần biết full credential của user để invalidate session; nó cần **một correlation identifier đáng tin**. Không hủy tất cả sessions bằng cách so username lấy từ XML chưa được xác minh, đặc biệt khi có nhiều tenant hoặc cùng user ở nhiều thiết bị.

### 8.1. Vì sao cần listener?

Apereo Java CAS Client có **SingleSignOutHttpSessionListener**, giúp xóa session mapping khi HttpSession tự hết hạn/bị hủy, tránh giữ liên kết cũ trong bộ nhớ. Listener này chạy trong **ứng dụng Servlet**, không quản lý TGT của CAS.

### 8.2. Session fixation và session ID thay đổi

Spring Security có thể **changeSessionId** sau authentication để chống session fixation. Cần kiểm thử correlation ST→session vẫn tìm được **phiên đang hoạt động thật** sau khi session ID được đổi. Không tự lưu một JSESSIONID cố định rồi không cập nhật khi session strategy thay ID.

### 8.3. Nhiều node và shared session store

Ví dụ:

~~~text
Browser CAS callback -> portal node A: mapping ST-P tại A
CAS SLO callback     -> portal node B: B không có mapping
~~~

Thêm **Spring Session Redis** giúp chia sẻ HttpSession nhưng **không tự biến mọi static map của CAS client thành distributed map**. Nếu ST→session mapping nằm trong JVM A, callback vào B có thể không tìm được session.

Cần kiểm thử và thiết kế: shared correlation store, SLO routing/event bus, session revocation check hoặc triển khai CAS client tương thích cluster. Sticky browser session có thể không giúp back-channel vì CAS Server callback không mang cookie của user.

## 9. Spring Security 6: local logout cấu hình như thế nào?

Ví dụ Servlet SecurityFilterChain dùng CAS Protocol login và local logout. Có thể dùng riêng phần **logout DSL** sau để bổ sung vào một CAS client chain đang hoạt động:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/", "/logged-out", "/error").permitAll()
        .anyRequest().authenticated())
    .logout(logout -> logout
        .logoutUrl("/logout")
        .logoutSuccessUrl("/logged-out")
        .permitAll());
~~~

**Lưu ý:** Đây là fragment, không phải một Spring Boot application độc lập. Người dùng cần CAS login đã được cấu hình qua **spring-security-cas** với **CasAuthenticationFilter**, **CasAuthenticationProvider** và **TicketValidator**. **Local logout** chỉ clear HttpSession/SecurityContext, không thực hiện CAS /logout nếu không có handler hoặc UI flow tiếp theo.

### 9.1. Chuyển đến CAS logout sau local logout

Nếu mục tiêu sản phẩm là **nhấn logout thì kết thúc cả CAS SSO**, thay phần logout DSL nói trên bằng:

~~~java
// casLogoutUrl lấy từ cấu hình server-side đã được tin cậy,
// ví dụ https://sso.example.org/cas/logout
http.logout(logout -> logout
    .logoutUrl("/logout")
    .logoutSuccessHandler((request, response, authentication) ->
        response.sendRedirect(casLogoutUrl))
    .permitAll());
~~~

**Thứ tự:** Spring Security thực hiện các local LogoutHandlers **trước**, sau đó **LogoutSuccessHandler** redirect browser tới CAS logout URL. CAS Server xử lý TGT, sau đó có thể gửi SLO nếu bật và từng client hỗ trợ.

**Không đặt hai logoutSuccessHandlers trong cùng một DSL** rồi kỳ vọng cả hai hoạt động. Đây là **mẫu thay thế** cho local-only. casLogoutUrl là fixed HTTPS URL, không lấy từ query parameter hay returnUrl tùy ý. Redirect CAS lỗi thì local session có thể đã hết trong khi TGT chưa chắc được thu hồi; UI cần diễn giải đúng.

### 9.2. Hai lựa chọn logout trên UI

Nếu sản phẩm muốn có hai nút:

~~~text
"Đăng xuất khỏi ứng dụng này"
  -> POST /logout với CSRF
  -> local session hết
  -> /logged-out (trang công khai)
  -> CAS TGT có thể còn

"Đăng xuất khỏi SSO"
  -> local logout với CSRF
  -> redirect CAS /logout
  -> CAS TGT hết
  -> CAS SLO notifications đến các ứng dụng đã đăng ký
~~~

Hai nút này cần **hai flows được cấu hình rõ** (có thể là hai endpoints Spring Security hoặc trang local logged-out cung cấp liên kết CAS logout an toàn), không phải một POST /logout mặc định tự hiểu lựa chọn từ tên nút. Tuyệt đối không tạo GET /logout làm hành động thay đổi trạng thái mà không có CSRF/confirmation policy.

## 10. Spring Boot 3 + Java 17: CAS login và local logout tối thiểu

Bài này tập trung **scope logout**. Code Java bên dưới là cấu hình CAS Protocol client đủ để thấy nơi gắn **local logout**, không phải CAS Server. Để chạy tích hợp cần CAS Server HTTPS thật, service registry đúng, user **demo** trên CAS, metadata/trust TLS và phiên bản **CAS client Jakarta Servlet** tương thích Spring Boot 3.

### 10.1. Maven dependencies

Trong project có Spring Boot parent/BOM tương thích:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
~~~

CAS client library phải phù hợp **Jakarta Servlet** của Boot 3 và Spring Security 6; không ép dependency version cũ khi chưa kiểm tra tương thích.

### 10.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    logout-url: https://sso.example.org/cas/logout
    service-url: https://portal.example.org/login/cas

server:
  servlet:
    session:
      timeout: 30m
~~~

**service-url** phải đúng URL callback mà CAS Server allowlist. Các domain example.org là **giả định**, không phải dịch vụ đăng nhập hoạt động sẵn. **CAS logout-url** không phải local **/logout** của Spring Security.

### 10.3. Main application

**src/main/java/com/example/cas/CasApplication.java**

~~~java
package com.example.cas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasApplication.class, args);
    }
}
~~~

### 10.4. Security configuration

**src/main/java/com/example/cas/CasSecurityConfig.java**

~~~java
package com.example.cas;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String url) {
        ServiceProperties p = new ServiceProperties();
        p.setService(url);
        p.setSendRenew(false);
        return p;
    }

    @Bean
    CasAuthenticationEntryPoint entryPoint(
            ServiceProperties serviceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {
        CasAuthenticationEntryPoint p =
            new CasAuthenticationEntryPoint();
        p.setLoginUrl(loginUrl);
        p.setServiceProperties(serviceProperties);
        return p;
    }

    @Bean
    UserDetailsService demoUsers() {
        return name -> {
            if (!"demo".equals(name)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Unknown local user");
            }
            // CAS xác thực danh tính; password UserDetails không
            // được dùng trong vòng xác minh Service Ticket.
            return User.withUsername(name)
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build();
        };
    }

    @Bean
    CasAuthenticationProvider casProvider(
            ServiceProperties serviceProperties,
            UserDetailsService demoUsers,
            @Value("${app.cas.server-base-url}") String casBaseUrl) {
        CasAuthenticationProvider p = new CasAuthenticationProvider();
        p.setServiceProperties(serviceProperties);
        p.setTicketValidator(
            new Cas20ServiceTicketValidator(casBaseUrl));
        p.setUserDetailsService(demoUsers);
        p.setKey("portal-cas-v1");
        return p;
    }

    @Bean
    SecurityFilterChain browser(
            HttpSecurity http,
            ServiceProperties serviceProperties,
            CasAuthenticationEntryPoint entryPoint,
            CasAuthenticationProvider casProvider) throws Exception {

        SecurityContextRepository repo =
            new HttpSessionSecurityContextRepository();

        // Chỉ một CasAuthenticationFilter trong SecurityFilterChain,
        // không @Bean để tránh auto-register thêm ở Servlet container.
        CasAuthenticationFilter filter = new CasAuthenticationFilter();
        filter.setFilterProcessesUrl("/login/cas");
        filter.setServiceProperties(serviceProperties);
        filter.setAuthenticationManager(new ProviderManager(casProvider));
        filter.setSecurityContextRepository(repo);
        filter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/logged-out", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(sc -> sc.securityContextRepository(repo))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/logged-out")
                .permitAll())
            .addFilterAt(
                filter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Điểm đáng học:**

- **CasAuthenticationFilter** xác minh CAS ST tại callback **/login/cas**; không phải logout filter.
- **CasAuthenticationProvider** dùng CAS ticket validator cho CAS Protocol; không tự parse/query ST để tạo Authentication.
- **HttpSessionSecurityContextRepository** giữ Authentication qua những request sau khi CAS ST được validate.
- **.logout(...)** ở trên chỉ định **đăng xuất ứng dụng**, không tự gọi CAS logout.
- **UserDetailsService** cố tình giới hạn user demo; production phải kiểm tra local account enabled, tenant/roles/grants, không tự cấp quyền cho mọi subject CAS.
- CAS filter được tạo bằng **new** bên trong SecurityFilterChain; không đăng ký nó thêm một lần dưới dạng Servlet Filter bean.
- **CSRF mặc định** vẫn bảo vệ POST /logout và những hành động state-changing của ứng dụng.

### 10.5. Controller và chạy thử

**src/main/java/com/example/cas/CasController.java**

~~~java
package com.example.cas;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CasController {

    @GetMapping("/")
    public String home() {
        return "CAS logout scope demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(Principal principal) {
        return Map.of("user", principal.getName());
    }

    @GetMapping("/logged-out")
    public String loggedOut() {
        return "Local session ended. CAS SSO may remain active.";
    }
}
~~~

Trong một Maven project đầy đủ với CAS Server thật và JDK 17+:

~~~bash
mvn spring-boot:run
~~~

Kiểm tra endpoint công khai nếu ứng dụng khởi động:

~~~bash
curl -i http://localhost:8080/
~~~

Body theo controller:

~~~text
CAS logout scope demo
~~~

Để test logout, login CAS qua public HTTPS callback thật rồi dùng form POST /logout có CSRF token và browser session cookie. Nếu user khác demo, local account policy từ chối dù CAS xác thực thành công. Mẫu không thể tự login end-to-end nếu domain example.org không có CAS Server thực.

## 11. Thêm SingleSignOutFilter và listener: một biến thể Servlet

Tài liệu Java CAS Client mô tả **SingleSignOutFilter** và **SingleSignOutHttpSessionListener** cho CAS Protocol SLO. Ví dụ đăng ký **duy nhất một filter** trong Servlet container (không đồng thời add lại vào SecurityFilterChain):

**src/main/java/com/example/cas/CasSloConfig.java**

~~~java
package com.example.cas;

import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasSloConfig {

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> sloFilter() {
        FilterRegistrationBean<SingleSignOutFilter> b =
            new FilterRegistrationBean<>();
        b.setFilter(new SingleSignOutFilter());
        b.setName("casSingleSignOutFilter");
        b.addUrlPatterns("/*");
        // Chạy trước Spring Security; kiểm tra order thật khi deploy.
        b.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return b;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
    sloSessionListener() {
        return new ServletListenerRegistrationBean<>(
            new SingleSignOutHttpSessionListener());
    }
}
~~~

**Giải thích quan trọng:**

- **SingleSignOutFilter** là filter SLO của CAS Java Client, không phải **CasAuthenticationFilter** xử lý ST login.
- Filter SLO được đăng ký **một lần** trước security chain trong biến thể này, để theo dõi login ticket và xử lý CAS SLO callback.
- **SingleSignOutHttpSessionListener** giúp dọn association khi local session kết thúc.
- Nếu chọn cách thêm SLO filter **bên trong Spring Security chain** như ví dụ XML của Spring Security CAS, phải **không** giữ đăng ký Servlet filter trên. Chỉ chọn **một** phương án để tránh xử lý trùng.
- Kiểm tra thứ tự với CharacterEncodingFilter, CAS authentication filter, CSRF và phiên bản client. Mã chỉ là wiring tham khảo, không thay interoperability test.
- Khi dùng Spring Boot 3, **CAS client phải tương thích Jakarta Servlet**; kiểm tra dependency thật nếu gặp lỗi javax.servlet vs jakarta.servlet.
- Đây chưa phải bằng chứng CAS Server đã bật SLO cho service; server phải có registered service logoutType/channel/endpoint hợp lệ.

### Cảnh báo bảo mật callback SLO

CAS Protocol SLO truyền thống **không nên được mặc định coi là SAML2 logout XML có chữ ký được kiểm tra đầy đủ**. Một endpoint nhận POST **logoutRequest** từ Internet có thể thành mục tiêu **logout CSRF/DoS** nếu kẻ lạ có thể giả mạo thông điệp để hủy phiên.

Các biện pháp cần đánh giá:

1. HTTPS end-to-end giữa CAS Server và ứng dụng.
2. **mTLS hoặc một kênh xác thực được tại gateway/ingress** khi kiến trúc cho phép.
3. Network allowlist và chỉ tin forwarded headers từ reverse proxies được kiểm soát.
4. Ràng buộc message/correlation ID với session đã theo dõi.
5. Kiểm soát replay, sai SessionIndex, lỗi parse và giới hạn tốc độ.
6. Không cho source không tin cậy hủy sessions chỉ bằng NameID/username tự khai.
7. Cách áp CSRF cho **SLO server-to-server** phải tách khỏi CSRF của browser; **không disable toàn bộ CSRF**.
8. Vì SLO filter ở **trước** Spring Security trong biến thể này, đừng giả định SecurityFilterChain bên trong tự bảo vệ nó.

Tính năng xác thực/thẩm định cụ thể của SingleSignOutFilter phụ thuộc phiên bản và cấu hình CAS client; cần kiểm thử threat model với hệ thống thật. Đặc biệt đừng tự viết endpoint nhận một chuỗi SessionIndex rồi hủy mọi sessions có cùng username.

## 12. Java 17 runnable: mô phỏng sự độc lập của ba phạm vi

Ví dụ độc lập dưới đây không cần Spring/CAS Server. Nó làm rõ **trạng thái logic** của local logout, CAS logout và SLO thành công hoặc một phần.

**Tệp: CasLogoutScopeDemo.java**

~~~java
public final class CasLogoutScopeDemo {

    record Sessions(boolean casSso,
                    boolean portal,
                    boolean reports) { }

    static Sessions localPortalLogout(Sessions s) {
        return new Sessions(s.casSso(), false, s.reports());
    }

    static Sessions centralCasLogout(Sessions s) {
        return new Sessions(false, s.portal(), s.reports());
    }

    static Sessions successfulSlo(Sessions s) {
        return new Sessions(false, false, false);
    }

    static Sessions partialSlo(Sessions s) {
        return new Sessions(false, false, s.reports());
    }

    static Sessions reenterPortal(Sessions s) {
        if (!s.casSso()) {
            return s;
        }
        // CAS SSO còn hoạt động -> giả định CAS cấp một ST mới.
        return new Sessions(true, true, s.reports());
    }

    static String state(Sessions s) {
        return "cas=" + s.casSso()
            + ",portal=" + s.portal()
            + ",reports=" + s.reports();
    }

    public static void main(String[] args) {
        Sessions active = new Sessions(true, true, true);
        Sessions localOnly = localPortalLogout(active);

        System.out.println("start=" + state(active));
        System.out.println("localOnly=" + state(localOnly));
        System.out.println(
            "localThenReenter=" + state(reenterPortal(localOnly)));
        System.out.println(
            "casOnly=" + state(centralCasLogout(active)));
        System.out.println(
            "sloSuccess=" + state(successfulSlo(active)));
        System.out.println(
            "sloPartial=" + state(partialSlo(active)));
    }
}
~~~

Chạy:

~~~bash
javac CasLogoutScopeDemo.java
java CasLogoutScopeDemo
~~~

**Stdout xác định:**

~~~text
start=cas=true,portal=true,reports=true
localOnly=cas=true,portal=false,reports=true
localThenReenter=cas=true,portal=true,reports=true
casOnly=cas=false,portal=true,reports=true
sloSuccess=cas=false,portal=false,reports=false
sloPartial=cas=false,portal=false,reports=true
~~~

Giải thích:

- **localOnly:** portal session kết thúc, CAS và reports có thể còn.
- **localThenReenter:** TGT CAS còn, nên mô phỏng cho phép ST mới tạo portal session mới.
- **casOnly:** TGT CAS bị hủy, nhưng local sessions chưa tự mất.
- **sloSuccess:** CAS SSO và hai local sessions đều kết thúc.
- **sloPartial:** reports callback thất bại, nên reports session còn.

Đây là **state-machine học tập**, không parse CAS XML, không gọi network hoặc xác minh chữ ký. Trong production không sử dụng boolean do browser gửi để quyết định session đã được thu hồi.

## 13. Kiểm thử tích hợp: ba tình huống phải tách riêng

### 13.1. Local logout, TGT còn

**Given:** browser login portal/reports qua CAS; TGT còn hợp lệ.  
**When:** POST /logout ở portal với CSRF token.  
**Then:** portal HttpSession/SecurityContext bị xóa; reports có thể còn; CAS TGT có thể còn. Khi mở lại portal, CAS có thể cấp ST mới mà không hỏi password.

Đừng nhầm redirect login mới là local logout thất bại. Quan sát **session ID mới + ST mới**, không in raw ticket vào logs.

### 13.2. CAS logout không có SLO receiver

**Given:** portal và reports có local sessions.  
**When:** browser vào CAS /logout, nhưng các ứng dụng không hỗ trợ SLO.  
**Then:** TGT hết; request tới portal/reports bằng local session cookie trước khi hết hạn vẫn có thể thành công.

Không giải quyết bằng cách giảm ST TTL. ST đã dùng tại login; local session lifecycle là cơ chế khác.

### 13.3. CAS logout với SLO

**Given:** CAS Server có SLO enabled, service registrations đúng channel/endpoints, mỗi app có mapping ST→HttpSession và receiver tin cậy.  
**When:** CAS /logout được kích hoạt và callback được gửi tới portal/reports.  
**Then:** mỗi receiver invalidate đúng session; browser request tiếp theo không thể dùng SecurityContext cũ.

Nếu reports callback timeout, đây là **partial SLO outcome**. Ghi nhận failure và có biện pháp giảm rủi ro, không tuyên bố “đã xóa mọi phiên”.

## 14. Bộ test âm, lỗi và cách xử lý

| Test/lỗi | Kỳ vọng hoặc cách chẩn đoán |
| --- | --- |
| POST /logout không CSRF token | Bị từ chối nếu CSRF bật |
| Local logout xong user vào lại không cần mật khẩu | TGT còn, CAS cấp ST mới; kiểm tra local session trước và sau |
| CAS logout trang báo thành công nhưng portal vẫn vào được | Chưa có SLO hoặc portal session chưa invalidate |
| SLO callback không mang browser cookie | Receiver dùng ST→session mapping, không đoán request.getSession() |
| SessionIndex khác ST đã map | Không hủy nhầm phiên khác |
| Callback có username giống user khác | Không xóa tất cả sessions chỉ theo username |
| Callback giả từ Internet | Bị từ chối bởi trust/network/message controls |
| Callback replay | Không hủy nhầm user, xử lý idempotent/atomic theo policy |
| CAS Server gửi tới URL sai | Sửa service registry logoutUrl/callback path |
| CAS Server không reach app | Kiểm tra DNS, TLS, firewall, proxy, allowlist |
| SLO tới node khác node login | Kiểm tra shared ST→session mapping và session store |
| Spring Session Redis có nhưng CAS map ở JVM | Vẫn có nguy cơ logout thất bại |
| SLO filter chưa đặt trước security chain | Kiểm tra order/CSRF/matching và registration |
| SLO filter đăng ký hai lần | Dọn Servlet/Security duplicate registrations |
| CAS SLO XML giống SAML LogoutRequest | Không nhầm với SAML2 SP logout/LogoutResponse |
| Front-channel bị browser chặn | Test SameSite/CSP/CORS/third-party cookie, cân nhắc back-channel |
| Browser đóng tab khi đang logout CAS | Không mặc định front-channel hoàn tất |
| Local account disabled nhưng phiên còn | Authorization/revocation policy phải deny |
| SLO chỉ một CAS SSO session | Không tự báo logout mọi thiết bị |
| Callback trả HTTP 200 nhưng local session vẫn dùng được | Cần test HTTP resource sau callback, không chỉ status |
| Global logout redirect URL do user nhập | Chặn open redirect, dùng URL cố định/allowlist |
| API token độc lập CAS vẫn còn | Phải có token revocation riêng, SLO không tự thu hồi |
| Raw ST/TGT/cookie xuất hiện trong logs | Mask/query sanitization và giảm log PII |

### Những điều nên đo để xác định thành công thực tế

- CAS TGT revocation event (ID đã giảm thiểu, không raw TGT).
- SLO requests gửi theo từng registered service và loại channel.
- SLO callbacks nhận/parse và kiểm tra trust.
- Mapping ST→HttpSession tìm thấy/không tìm thấy.
- HttpSession thực sự invalidated trên từng app node.
- HTTP requests sau logout còn được chấp nhận hay đã bị redirect/401.
- Callback retry/timeout/error/partial failure.
- Sự khác biệt giữa CAS logout và **all-devices logout**.

**Không lưu nguyên văn** ST, TGC, TGT, SessionIndex, JSESSIONID hoặc logout XML trong APM/access logs. Dùng correlation ID không chứa secrets, retention policy và giới hạn người xem.

## 15. Kiểm soát SLO trên nhiều pod và các chính sách bù trừ

CAS SLO là một lớp hữu ích nhưng không nên là **biện pháp thu hồi duy nhất** cho dữ liệu nhạy cảm. Các lớp bù trừ:

1. **SP idle timeout** phù hợp với mức nhạy cảm; background polling có thể giữ session alive nên xem xét **absolute lifetime**.
2. **Local account enabled/disabled** được kiểm tra theo policy khi truy cập; user disabled không tự được quyền chỉ vì session cookie còn.
3. **Resource-level authorization** kiểm tra grants/tenant ở thời điểm hành động, không chỉ role snapshot tại login.
4. **Cluster-wide session invalidation** khi SLO callback hoặc admin revoke.
5. **SSO session duration** và yêu cầu reauthentication/fresh auth cho hoạt động nhạy cảm.
6. **Monitoring failures** khi CAS Server không thể gửi SLO tới SP.
7. **Fail closed** cho action nhạy cảm nếu nguồn quyền cục bộ không sẵn sàng.
8. Quy trình phản ứng sự cố khi người dùng báo “đã logout nhưng session ở ứng dụng khác vẫn hoạt động”.

Đặc biệt trong multi-tenant không hủy tùy tiện sessions của user cùng email/username nhưng khác tenant hoặc CAS server. Nên xác định rõ **CAS authority/TGT relationship + service ticket mapping + local session owner**.

## 16. Checklist production

- [ ] Sản phẩm mô tả rõ ba phạm vi **application logout, CAS logout, Single Sign-Out**.
- [ ] POST local logout có CSRF protection, invalidate HttpSession và clear SecurityContext.
- [ ] CAS logout URL là HTTPS cấu hình server-side, không open redirect.
- [ ] Không suy ra TGT bị xóa chỉ từ việc portal đã logout.
- [ ] Không suy ra local sessions bị xóa chỉ từ việc CAS /logout trả thành công.
- [ ] CAS Server service registry bật đúng SLO channel/endpoint cho từng ứng dụng.
- [ ] Mỗi ứng dụng SLO có **SingleSignOutFilter + SingleSignOutHttpSessionListener** hoặc tương đương đã kiểm thử.
- [ ] SingleSignOutFilter được đăng ký **một lần**, đúng thứ tự; không trộn Servlet và Security chain registrations.
- [ ] SLO back-channel **không phụ thuộc browser cookie**; có ST→HttpSession correlation mapping đáng tin.
- [ ] SessionIndex không bị nhầm với JSESSIONID hay username.
- [ ] Receiver không tin logoutRequest từ nguồn bất kỳ; có bảo vệ TLS/mTLS/network/replay theo architecture.
- [ ] Không dùng CAS Protocol SLO XML như một SAML2 logout transaction trọn vẹn nếu không có profile thực.
- [ ] Có kiểm thử phiên trên nhiều nodes, sticky session và shared mapping/store.
- [ ] Test partial SLO, callback timeout, browser close và IdP/CAS outage.
- [ ] Test local logout sau đó SSO login lại vì TGT còn.
- [ ] Không gọi SLO thành công toàn cục khi chưa xác minh downstream sessions.
- [ ] Có account/permission revocation, idle/absolute timeout như các lớp phòng thủ bổ sung.
- [ ] Logout một TGT không tự áp cho mọi thiết bị, trừ khi policy đặc biệt thực hiện.
- [ ] Không log raw tickets/cookies/SLO XML, có audit với correlation ID phù hợp.
- [ ] Khi triển khai Boot 3, kiểm tra CAS client hỗ trợ **Jakarta Servlet** và tất cả API đúng version.

**Kết luận:** **Application logout** xóa phiên của một ứng dụng; **CAS logout** kết thúc phiên SSO trung tâm; **Single Sign-Out** phối hợp yêu cầu các ứng dụng liên quan tự invalidate phiên của chúng. Ba trạng thái **độc lập theo mặc định**. Muốn logout xuyên ứng dụng đáng tin cần CAS SLO client đúng giao thức, ST-to-session mapping, bảo vệ callback, cluster consistency, kiểm thử và xử lý partial failures.

## 17. Tài liệu tham khảo

- [Apereo CAS 8.0.x – Logout & Single Logout](https://apereo.github.io/cas/8.0.x/installation/Logout-Single-Signout.html): application logout vs CAS logout, SLO best effort, back-/front-channel và service logoutType.
- [CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): /logout, Single Logout callback, Service Tickets và TGT.
- [Spring Security – CAS Authentication and Single Logout](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CAS SLO filter/listener và local vs central logout.
- [Spring Security 6.5 – Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): LogoutFilter, LogoutHandler, LogoutSuccessHandler, CSRF.
- [Apereo Java CAS Client README](https://github.com/apereo/java-cas-client/blob/master/README.md): SingleSignOutFilter, SingleSignOutHttpSessionListener và registration order.
- [Spring Boot – Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): FilterRegistrationBean và ServletListenerRegistrationBean.
- [Spring Session – Redis Guide](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): shared HttpSession; cần kiểm tra riêng distributed CAS correlation mapping.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session expiration, logout, CSRF, revocation và lifecycle.
