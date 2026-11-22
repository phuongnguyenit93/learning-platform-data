# 25.9. Đổi provider hoặc đăng nhập bằng tài khoản khác

## 1. Bối cảnh: một ứng dụng, nhiều phương thức đăng nhập

Một ứng dụng Spring Security OAuth 2.0/OIDC Client có thể cho phép người dùng đăng nhập bằng nhiều OpenID Provider (OP) hoặc OAuth2 providers:

- **Company SSO** dành cho nhân viên.
- **Partner Identity Provider** dành cho đối tác.
- Một provider hỗ trợ nhiều tài khoản đã đăng nhập đồng thời trong browser.

Giả sử người dùng đăng nhập vào portal bằng tài khoản nhân viên tại Company SSO, sau đó muốn dùng tài khoản đối tác; hoặc người dùng đang đăng nhập bằng tài khoản <code>alice@example.org</code> tại cùng provider nhưng muốn đổi sang <code>bob@example.org</code>.

Hai yêu cầu nghe tương tự nhưng khác nhau về giao thức và phiên:

1. **Đổi provider (switch provider):** Chọn một <code>ClientRegistration</code> khác và bắt đầu authorization flow mới ở một OP khác.
2. **Đổi tài khoản tại cùng provider (switch account):** Vẫn dùng <code>ClientRegistration</code> cũ nhưng muốn OP xác thực một danh tính khác, thay vì tự động tái sử dụng SSO session hiện tại.

Một hệ thống nhiều provider phải hiểu rằng:

> **Đổi provider không tự đồng nghĩa đăng xuất toàn bộ OP; xóa session ở ứng dụng không tự xóa SSO cookie tại OP; có ID Token mới không có nghĩa được phép gộp hai tài khoản thành một.**

Trong Spring Security, lựa chọn provider diễn ra tại authorization initiation, còn danh tính thực sự chỉ được xác định sau callback và validation. Ứng dụng không được tin một query parameter như <code>user=bob</code> để quyết định principal sẽ đăng nhập.

## 2. Mục tiêu bài học

Sau bài này, bạn sẽ:

1. Phân biệt **đổi provider**, **đổi tài khoản trong cùng provider**, **local logout**, **RP-Initiated Logout** và **account linking**.
2. Sử dụng đúng <code>/oauth2/authorization/{registrationId}</code> để chọn provider đã được đăng ký.
3. Hiểu vì sao người dùng có thể bị đăng nhập lại vào tài khoản cũ do SSO session tại OP.
4. Sử dụng các OIDC parameters như <code>prompt=select_account</code>, <code>prompt=login</code>, <code>max_age=0</code> và <code>login_hint</code> đúng mục đích.
5. Thiết kế thao tác đổi danh tính qua **POST có CSRF protection**, invalidate local session và bắt đầu authorization request mới.
6. Xử lý đúng <code>SecurityContext</code>, <code>OAuth2AuthorizedClient</code>, authorization request repository và session rotation.
7. Tránh nhầm danh tính giữa providers, đặc biệt khi hai ID Token có cùng email nhưng khác <code>iss</code>/<code>sub</code>.
8. Cấu hình luồng tương ứng trong **Servlet** và hiểu sự khác biệt với **Reactive WebFlux**.
9. Xây chính sách account linking, tenant isolation, step-up, redirect và token cleanup phù hợp.
10. Kiểm thử multi-provider login, switch-account, SSO, lỗi callback và multi-instance.

## 3. Phân biệt các khái niệm trước khi lập trình

| Nhu cầu | Thao tác chính | Có bắt buộc kết thúc phiên OP không? | Lưu ý |
|---|---|---|---|
| Đăng nhập lần đầu bằng Company | Bắt đầu OAuth2/OIDC authorization với registration <code>company</code> | Không | Cần state/nonce/PKCE/ID Token validation theo flow |
| Chuyển từ Company sang Partner | Kết thúc hoặc thay local authentication theo policy, bắt đầu registration <code>partner</code> | Không nhất thiết | Đổi issuer, Client ID, scopes và principal |
| Chuyển từ Alice sang Bob tại Company | Đăng nhập lại qua Company, yêu cầu OP cho chọn tài khoản | Không nhất thiết, tùy OP | <code>prompt=select_account</code> chỉ là yêu cầu đối với OP |
| Bắt buộc nhập lại credential | Yêu cầu xác thực mới tại OP | Có thể không cần logout toàn bộ OP | <code>prompt=login</code> hoặc <code>max_age=0</code> khi được OP hỗ trợ |
| Logout khỏi portal | Invalidate local session/SecurityContext | Không | SSO session tại OP có thể còn |
| Logout khỏi OP | RP-Initiated Logout, nếu OP hỗ trợ | Có | Có thể ảnh hưởng SSO trên ứng dụng khác |
| Gắn hai đăng nhập vào một tài khoản ứng dụng | Account linking có kiểm tra quyền sở hữu | Không | Không tự link chỉ vì email giống nhau |
| Đổi tenant/organization trong cùng tài khoản | Authorization/business context switching | Không nhất thiết | Không đồng nhất tenant switch với OAuth provider switch |

Ví dụ: người dùng có thể giữ tài khoản Alice tại Company SSO, đồng thời liên kết Partner account với profile nội bộ. Khi chuyển provider, sản phẩm phải quyết định đó là **đổi người dùng đang hoạt động** hay **kết nối thêm một danh tính vào tài khoản hiện có**. Hai nghiệp vụ có mức rủi ro và luồng xác minh khác nhau.

## 4. Cấu trúc đa provider trong Spring Security

### 4.1. ClientRegistration là điểm chọn provider

Trong Spring Security OAuth2 Client, mỗi registration có một <code>registrationId</code>, <code>clientId</code>, provider metadata, grant type, scopes và callback template.

Ví dụ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-op
            client-id: portal-company
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          partner:
            provider: partner-op
            client-id: portal-partner
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile

        provider:
          company-op:
            issuer-uri: https://idp.example.org/realms/company
          partner-op:
            issuer-uri: https://login.partner.example.org
~~~

Hai issuer, Client IDs, scopes và secrets đều là ví dụ. Mỗi provider phải được cấu hình dựa trên metadata tin cậy và redirect URI đăng ký chính xác.

Khi dùng OIDC Discovery, <code>issuer-uri</code> giúp Spring Boot/Spring Security nạp metadata như authorization/token endpoints, JWK Set và UserInfo endpoint nếu có. **Issuer phải được xác minh chính xác**, không suy đoán bằng domain email.

### 4.2. Đường dẫn bắt đầu login

Spring Security mặc định có authorization initiation URL:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Tương ứng:

~~~text
GET /oauth2/authorization/company
    → Authorization Endpoint của Company OP

GET /oauth2/authorization/partner
    → Authorization Endpoint của Partner OP
~~~

Đường dẫn chỉ chọn **registration đã được khai báo**. Browser không nên được phép truyền tùy ý:

~~~text
/oauth2/authorization?issuer=https://unknown.example
~~~

rồi khiến server gửi authorization request hoặc credential tới issuer không được tin cậy.

### 4.3. Callback tương ứng với registration

Ví dụ:

~~~text
Company callback:
    /login/oauth2/code/company

Partner callback:
    /login/oauth2/code/partner
~~~

Spring Security phải đối chiếu callback với authorization request ban đầu, registration, <code>state</code>, PKCE/nonce khi áp dụng, và xác minh ID Token theo **issuer/audience của registration đã chọn**.

Không xử lý callback theo cách: “JWT có email thuộc company, vậy đổi sang ClientRegistration company”. Callback phải gắn với request và issuer tin cậy, không với claim chưa xác minh hoặc email tự khai.

## 5. Luồng đổi provider an toàn

Xét user đang đăng nhập Company, muốn chuyển sang Partner:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant APP as Spring Security Portal
    participant C as Company OP
    participant P as Partner OP
    U->>B: Chọn "Đổi sang Partner"
    B->>APP: POST /account/switch (CSRF + provider=partner)
    APP->>APP: Kiểm tra provider allowlist, kết thúc local session
    APP-->>B: Redirect /oauth2/authorization/partner
    B->>APP: GET /oauth2/authorization/partner
    APP->>APP: Tạo state, nonce/PKCE khi áp dụng
    APP-->>B: 302 tới Partner Authorization Endpoint
    B->>P: Authorization request
    P->>U: Login hoặc SSO theo policy
    P-->>B: Redirect code + state
    B->>APP: GET /login/oauth2/code/partner
    APP->>P: Token exchange
    P-->>APP: Access token + ID Token
    APP->>APP: Validate ID Token, tạo principal Partner
    APP->>APP: Tạo Authentication/session mới
    APP-->>B: Redirect tới trang an toàn sau login
~~~

Lưu ý:

- Không cần gửi request logout đến Company OP để bắt đầu authorization với Partner OP. Việc logout khỏi Company OP là một **quyết định sản phẩm riêng**.
- Local session Company phải được dọn theo policy trước khi coi Partner là principal đang hoạt động.
- Nếu sản phẩm hỗ trợ nhiều identities trong một session, cần thiết kế rõ “active identity” và permission boundary. Không đơn giản ghi đè field <code>currentProvider</code> trong session rồi dùng token của người khác.
- Request mới phải tạo **state mới** và dùng registration đúng issuer.
- Sau callback, ứng dụng phải áp dụng authorization/tenant policy của Partner principal chứ không kế thừa role từ Company principal.

### 5.1. Vì sao nên bắt đầu bằng POST có CSRF?

Một link GET đến <code>/oauth2/authorization/partner</code> là cách tiêu chuẩn để **khởi tạo login**. Tuy nhiên, khi người dùng đã đăng nhập và yêu cầu **thay danh tính đang hoạt động**, ta thường muốn có thao tác có chủ đích:

~~~http
POST /account/switch HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=...

provider=partner&<CSRF_FORM_FIELD>=...
~~~

Ứng dụng xác thực request, kiểm tra CSRF, provider allowlist và chỉ sau đó kết thúc session cũ rồi redirect sang flow mới.

Điều này tránh biến một URL đổi danh tính thành thao tác gây side effect mà website bên ngoài có thể ép browser thực hiện bằng ảnh/iframe/link.

**Không đồng nghĩa phải cấm authorization initiation GET**. Login initiation vẫn dùng URL chuẩn; POST riêng dùng cho thao tác đổi account khi **đang authenticated**.

### 5.2. Không tự ghép redirect URL với dữ liệu chưa kiểm tra

Sai:

~~~java
return "redirect:" + request.getParameter("nextUrl");
~~~

Nếu <code>nextUrl</code> do browser kiểm soát, đây có thể là open redirect dẫn tới phishing hoặc OAuth flow confusion.

Đúng hơn là chỉ redirect đến một đường dẫn nội bộ được xác định từ allowlist:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Nếu cần <code>returnTo</code>, dùng route IDs/relative paths được validate, hoặc lưu lựa chọn nội bộ vào server-side state và kiểm tra quyền sau login. Không đưa một URI tùy ý vào <code>redirect_uri</code> gửi OP.

## 6. Luồng đổi tài khoản trong cùng OpenID Provider

Giả sử người dùng đang dùng Alice tại Company:

~~~text
Portal session: Alice
Company OP session: Alice
~~~

Người dùng click “Đăng nhập bằng tài khoản Company khác”. Ứng dụng xóa portal session rồi redirect tới:

~~~text
/oauth2/authorization/company
~~~

Browser vẫn có SSO cookie của Company OP. OP có thể lập tức trả code cho **Alice**, không hỏi chọn account.

~~~mermaid
flowchart TD
    A["User Alice đã login ở Portal"] --> B["Portal local logout"]
    B --> C["Authorization request tới cùng OP"]
    C --> D{"OP SSO cookie còn hiệu lực?"}
    D -->|Có| E["OP có thể SSO vào Alice ngay"]
    D -->|Không / cần interaction| F["OP hiển thị login/account chooser"]
    E --> G["Callback có thể vẫn là Alice"]
    F --> H["Người dùng chọn Alice hoặc Bob"]
    H --> I["Callback với danh tính OP đã xác thực"]
~~~

**Xóa local session không tự điều khiển account-selection UI của provider.**

Khi muốn chọn tài khoản khác, cần cơ chế do OP cung cấp, thường thông qua OIDC authorization request parameters.

## 7. Các tham số OIDC ảnh hưởng chọn tài khoản

### 7.1. prompt=select_account

Trong OIDC, tham số <code>prompt</code> có giá trị <code>select_account</code> để yêu cầu Authorization Server/OP hiển thị lựa chọn tài khoản.

Ví dụ khái niệm:

~~~http
GET /authorize?response_type=code&client_id=portal-company&scope=openid%20profile&state=RANDOM_STATE&redirect_uri=https%3A%2F%2Fportal.example.org%2Flogin%2Foauth2%2Fcode%2Fcompany&prompt=select_account HTTP/1.1
Host: idp.example.org
~~~

OP có thể:

- Cho người dùng chọn một account đang có SSO session.
- Hiển thị login UI để thêm tài khoản mới.
- Không hỗ trợ giá trị prompt này hoặc thực hiện hành vi riêng.

**Không cam kết <code>select_account</code> sẽ luôn hiển thị một chooser giống nhau ở mọi provider**. Ứng dụng phải kiểm thử bằng đúng OP, tenant, browser và policy.

### 7.2. prompt=login

<code>prompt=login</code> yêu cầu OP xác thực lại End-User.

Nó không đồng nghĩa “hiển thị danh sách tất cả tài khoản”. Một OP có thể yêu cầu Alice nhập mật khẩu lại, nhưng người dùng vẫn là Alice.

Ví dụ:

~~~text
prompt=login
~~~

phù hợp khi cần **reauthentication**, không phải chỉ thay account.

### 7.3. max_age=0

<code>max_age</code> là thời gian tối đa tính từ lần active authentication gần nhất mà Client chấp nhận. Với:

~~~text
max_age=0
~~~

OIDC yêu cầu OP thực hiện xác thực chủ động lại, và ID Token cần có <code>auth_time</code> để Client đánh giá.

Điểm quan trọng:

- <code>max_age=0</code> là yêu cầu **authentication freshness**.
- Nó không chỉ định danh tính phải là Bob.
- Với account switching, có thể kết hợp với cơ chế chọn tài khoản khi OP hỗ trợ, nhưng phải kiểm tra chính sách provider.
- Không dùng <code>iat</code> của ID Token thay cho <code>auth_time</code> để kết luận lần xác thực thật gần đây.

### 7.4. prompt=login select_account

OIDC cho phép nhiều giá trị prompt cách nhau bằng khoảng trắng:

~~~text
prompt=login select_account
~~~

Điều này thể hiện yêu cầu OP vừa xử lý reauthentication vừa account selection. Tuy nhiên, không phải OP nào cũng hỗ trợ hoặc xử lý hai giá trị theo cùng một cách.

Không tự thêm các tham số chưa được provider công nhận vào tất cả authorization requests rồi cho rằng login luôn ổn định.

### 7.5. login_hint

<code>login_hint</code> có thể gợi ý account OP nên chọn, ví dụ email hoặc một định danh khác:

~~~text
login_hint=bob@example.org
~~~

Đây là **gợi ý UI**, không phải bằng chứng Bob đã được xác thực.

Rủi ro:

- Browser hoặc bookmark có thể cung cấp hint sai.
- Email là dữ liệu cá nhân; không đưa vào analytics/logs không cần thiết.
- OP có thể bỏ qua hint.
- Dùng hint không thay thế callback state và ID Token verification.

### 7.6. prompt=none

<code>prompt=none</code> yêu cầu OP không hiển thị UI; có thể dẫn tới lỗi <code>login_required</code> hoặc <code>interaction_required</code> nếu không thể SSO im lặng.

**Không dùng <code>prompt=none</code> để yêu cầu người dùng chọn tài khoản khác**. Nó có mục đích gần như ngược lại.

### 7.7. Bảng chọn nhanh

| Mục tiêu | Tham số thường xem xét | Kết luận cần tránh |
|---|---|---|
| Hiện lựa chọn account | <code>prompt=select_account</code> | Không bảo đảm provider luôn hiển thị chooser |
| Bắt buộc xác thực lại | <code>prompt=login</code> | Không mặc nhiên đổi account |
| Giới hạn tuổi phiên xác thực | <code>max_age</code> | Không thay cho account selection |
| Gợi ý account | <code>login_hint</code> | Hint không phải authentication |
| SSO không UI | <code>prompt=none</code> | Không dùng để đổi account |

## 8. Không nhầm local logout với OP logout

Trong các ứng dụng SSO, có ít nhất hai phiên:

~~~text
Portal HTTP session             Company OP SSO session
    app-session-123                  op-session-456
          |                               |
  Spring Security                         Browser cookie
  SecurityContext                         tại idp.example.org
~~~

Local logout ở portal thường invalidate <code>app-session-123</code>. Nó **không thể trực tiếp xóa cookie thuộc domain của OP**.

### 8.1. Khi nào chỉ cần local logout?

Ví dụ user muốn đổi từ Company sang Partner:

- Kết thúc local Authentication của Company.
- Không bắt buộc logout Company OP nếu không có yêu cầu global SSO logout.
- Bắt đầu authorization ở Partner OP.

Phương án này ít gây ảnh hưởng tới các ứng dụng khác đang dùng Company SSO.

### 8.2. Khi nào cân nhắc RP-Initiated Logout?

Nếu sản phẩm có yêu cầu “đăng xuất toàn bộ khỏi Company” hoặc OP không hỗ trợ account chooser phù hợp, có thể dùng **OIDC RP-Initiated Logout** khi provider hỗ trợ.

Spring Security Servlet có <code>OidcClientInitiatedLogoutSuccessHandler</code>; WebFlux có <code>OidcClientInitiatedServerLogoutSuccessHandler</code> ở các phiên bản tương ứng.

Nhưng OP logout có thể ảnh hưởng SSO của nhiều ứng dụng khác và đôi khi nhiều account sessions, tùy provider.

Không tự gọi OP logout khi user chỉ muốn xem danh sách provider nếu không có yêu cầu sản phẩm.

### 8.3. Back-Channel Logout không phải account chooser

OIDC Back-Channel Logout cho phép OP gửi Logout Token để RP kết thúc local sessions. Nó giải quyết **đồng bộ logout**, không phải cách chọn Bob thay Alice trong Authorization Code Flow.

Không xây account switch bằng cách phát Logout Token giả hoặc tự POST đến back-channel endpoint của ứng dụng.

## 9. Mẫu triển khai Servlet: hai OIDC providers

Ví dụ dùng Java 17, Spring Boot 3/Spring Security 6 với MVC/Servlet. Cần lựa chọn API cụ thể theo phiên bản dự án.

### 9.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Nếu dùng view templates, thêm template engine phù hợp. Ví dụ dưới chỉ trình bày security logic, không buộc framework UI nào.

### 9.2. SecurityFilterChain có trang chọn provider

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/error", "/assets/**")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"));

        return http.build();
    }
}
~~~

Giải thích:

- <code>/login</code> là trang riêng để người dùng chọn registration.
- <code>/oauth2/authorization/company</code> và <code>/oauth2/authorization/partner</code> do Spring Security OAuth2 Login xử lý, nếu registration tồn tại.
- Spring Security sẽ tạo authorization request/state và callback theo registration được chọn.
- Cấu hình **không tắt CSRF**; route POST đổi account tiếp theo cần CSRF token hợp lệ.

### 9.3. Trang đăng nhập lựa chọn provider

Một trang HTML khái niệm:

~~~html
<h1>Chọn phương thức đăng nhập</h1>
<ul>
  <li><a href="/oauth2/authorization/company">
      Đăng nhập bằng Company SSO
  </a></li>
  <li><a href="/oauth2/authorization/partner">
      Đăng nhập bằng Partner ID
  </a></li>
</ul>
~~~

Controller nếu dùng MVC template:

~~~java
package example.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginPageController {

    @GetMapping("/login")
    String loginPage() {
        return "login";
    }
}
~~~

Mẫu này giả định có template <code>login</code>. Nếu không dùng template engine, có thể cung cấp static page/controller view theo lựa chọn ứng dụng.

### 9.4. Đường dẫn đã đăng ký phải chính xác

Ví dụ callback Company:

~~~text
https://portal.example.org/login/oauth2/code/company
~~~

Callback Partner:

~~~text
https://portal.example.org/login/oauth2/code/partner
~~~

Mỗi provider phải đăng ký chính xác URI phù hợp; sai scheme/host/path dẫn đến lỗi <code>redirect_uri_mismatch</code>.

Với reverse proxy, Spring Boot phải tính đúng public host/HTTPS và chỉ tin forwarded headers của proxy được kiểm soát.

## 10. Mẫu triển khai Servlet: POST đổi provider

Một cách thiết kế rõ ràng là có route POST riêng khi user đang authenticated:

~~~text
POST /account/switch
    provider=company | partner
    CSRF token hợp lệ
~~~

### 10.1. Controller kiểm tra provider rồi local logout

~~~java
package example.web;

import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Controller
public class AccountSwitchController {

    private static final Set<String> ALLOWED =
        Set.of("company", "partner");

    @PostMapping("/account/switch")
    String switchProvider(
            @RequestParam("provider") String provider,
            Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {

        // Chỉ cho phép registrationIds đã cấu hình.
        if (!ALLOWED.contains(provider)) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "Invalid provider");
        }

        // Spring Security CSRF filter phải kiểm tra POST trước controller.
        // Kết thúc Authentication + HttpSession hiện tại.
        var localLogout = new SecurityContextLogoutHandler();
        localLogout.logout(request, response, authentication);

        // Spring sẽ bắt đầu authorization flow mới ở provider đã chọn.
        return "redirect:/oauth2/authorization/" + provider;
    }
}
~~~

Điều kiện để dùng mẫu:

1. <code>/account/switch</code> được bảo vệ bởi <code>authenticated()</code>.
2. CSRF protection được bật cho POST.
3. Form cung cấp CSRF token đúng cách.
4. Provider được so với **allowlist server-side**.
5. Local logout được thực hiện trước khi bắt đầu identity mới.
6. Authorized-client cleanup riêng được xem xét ở các mục sau.

<code>SecurityContextLogoutHandler</code> có thể invalidate HTTP session và clear SecurityContext; nó **không** tự bảo đảm revoke access/refresh token của OP hoặc xóa tất cả token records trong persistent authorized-client service.

**Đây là một ví dụ triển khai**, không phải quy tắc sản phẩm bắt buộc. Nếu ứng dụng có tài khoản nội bộ với multiple linked identities, phải phân biệt “switch active identity” và “link identity” trước khi xóa principal hiện hành.

### 10.2. Form HTML với CSRF token

Ví dụ khái niệm dùng Thymeleaf:

~~~html
<form th:action="@{/account/switch}" method="post">
    <button type="submit" name="provider" value="company">
        Chuyển sang Company
    </button>
    <button type="submit" name="provider" value="partner">
        Chuyển sang Partner
    </button>
</form>
~~~

Khi dùng Thymeleaf và Spring Security CSRF integration đúng cấu hình, token có thể được thêm vào form tự động. Nếu dùng template engine khác, cần lấy CSRF token từ framework và gửi theo cách được hỗ trợ; không copy form thiếu token rồi tắt CSRF để “sửa” lỗi 403.

### 10.3. Tại sao không chỉ đổi một field trong session?

Sai:

~~~java
session.setAttribute("activeProvider", "partner");
~~~

Sau dòng này, <code>Authentication</code> có thể **vẫn là Company user**, trong khi code truy xuất access token Partner theo một nguồn khác. Nếu không kiểm tra cẩn thận, controller có thể hiển thị dữ liệu của user A nhưng dùng quyền API của user B.

Đổi danh tính phải cập nhật nhất quán:

- Authentication/SecurityContext.
- Principal và internal account context.
- Authorized-client selection.
- Tenant/role/permission.
- Saved request và redirect.
- Token caching và request-scoped data.

Không xử lý như thay theme hoặc language preference.

## 11. Bắt buộc hiển thị account chooser ở cùng provider

Mẫu POST ở trên xử lý **local logout và provider selection**. Nhưng nếu user chọn lại Company, OP có thể SSO ngay vào Alice.

Để yêu cầu OP hiện account chooser, có thể thêm:

~~~text
prompt=select_account
~~~

vào **authorization request do Spring Security tạo**.

### 11.1. Không đưa prompt vào redirect_uri

Sai:

~~~text
redirect_uri=https://portal.example.org/login/oauth2/code/company?prompt=select_account
~~~

<code>prompt</code> là parameter của **Authorization Endpoint request**, không phải query của callback <code>redirect_uri</code>.

Việc tự đổi redirect URI cũng có thể làm registration mismatch, mở đường cho OAuth mix-up hoặc open redirect nếu không kiểm tra.

### 11.2. Sử dụng OAuth2AuthorizationRequestResolver

Trong Servlet, Spring Security có <code>DefaultOAuth2AuthorizationRequestResolver</code> và interface <code>OAuth2AuthorizationRequestResolver</code>. Có thể bọc resolver mặc định, giữ nguyên state, PKCE, nonce và các thuộc tính correlation, chỉ bổ sung <code>prompt</code> ở authorization request phù hợp.

Ví dụ class minh họa một lựa chọn <code>?choose=true</code>:

~~~java
package example.security;

import java.util.Set;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestRedirectFilter;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizationRequestResolver;
import org.springframework.security.oauth2.core.endpoint.OAuth2AuthorizationRequest;
import org.springframework.security.oauth2.core.endpoint.OAuth2ParameterNames;

public final class AccountChoiceAuthorizationRequestResolver
        implements OAuth2AuthorizationRequestResolver {

    private final DefaultOAuth2AuthorizationRequestResolver delegate;
    private final Set<String> oidcRegistrations;

    public AccountChoiceAuthorizationRequestResolver(
            ClientRegistrationRepository repository,
            Set<String> oidcRegistrations) {

        this.delegate = new DefaultOAuth2AuthorizationRequestResolver(
            repository,
            OAuth2AuthorizationRequestRedirectFilter
                .DEFAULT_AUTHORIZATION_REQUEST_BASE_URI);
        this.oidcRegistrations = Set.copyOf(oidcRegistrations);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request) {
        return applyChooser(delegate.resolve(request), request);
    }

    @Override
    public OAuth2AuthorizationRequest resolve(
            HttpServletRequest request,
            String clientRegistrationId) {
        return applyChooser(
            delegate.resolve(request, clientRegistrationId),
            request);
    }

    private OAuth2AuthorizationRequest applyChooser(
            OAuth2AuthorizationRequest original,
            HttpServletRequest request) {

        if (original == null
                || !"true".equals(request.getParameter("choose"))) {
            return original;
        }

        Object registrationId =
            original.getAttributes()
                .get(OAuth2ParameterNames.REGISTRATION_ID);

        if (!(registrationId instanceof String id)
                || !oidcRegistrations.contains(id)) {
            return original;
        }

        return OAuth2AuthorizationRequest.from(original)
            .additionalParameters(parameters ->
                parameters.put("prompt", "select_account"))
            .build();
    }
}
~~~

Mục đích của lớp trên:

- **Delegate** việc tạo request cho resolver mặc định.
- Chỉ thêm <code>prompt=select_account</code> nếu request có <code>choose=true</code>.
- Chỉ áp dụng với registration IDs cho OIDC providers đã được kiểm tra hỗ trợ.
- **Không tự tạo lại state, nonce, PKCE hay redirect_uri**.

Nếu Spring Security version cụ thể đặt registration ID trong attributes theo key khác hoặc có API tùy biến riêng, cần điều chỉnh theo version đó. Điều không được phép thay đổi là **binding giữa request gốc, ClientRegistration và callback state**.

### 11.3. Gắn resolver vào SecurityFilterChain

Nếu sử dụng resolver ở trên, thay cấu hình <code>oauth2Login()</code> tại mục 9.2 bằng:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        ClientRegistrationRepository registrations) throws Exception {

    var resolver = new AccountChoiceAuthorizationRequestResolver(
        registrations, Set.of("company", "partner"));

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/", "/login", "/error", "/assets/**")
                .permitAll()
            .anyRequest().authenticated())
        .oauth2Login(oauth2 -> oauth2
            .loginPage("/login")
            .authorizationEndpoint(endpoint ->
                endpoint.authorizationRequestResolver(resolver)));

    return http.build();
}
~~~

Ở đây:

~~~text
GET /oauth2/authorization/company
    → login thường

GET /oauth2/authorization/company?choose=true
    → authorization request có prompt=select_account
~~~

**Hai phương án SecurityFilterChain ở mục 9.2 và 11.3 là lựa chọn thay thế**, không khai báo cùng lúc hai bean với matcher giống nhau để mong Spring tự ghép.

### 11.4. Liên kết lựa chọn account với POST switch

Muốn yêu cầu chọn tài khoản tại OP, sau khi local logout có thể redirect tới:

~~~text
/oauth2/authorization/company?choose=true
~~~

Trong controller switch ở mục 10.1, với một mode an toàn đã được sản phẩm quyết định, có thể trả:

~~~java
return "redirect:/oauth2/authorization/" + provider
    + "?choose=true";
~~~

Ở đây <code>provider</code> đã được kiểm tra allowlist trước. Cờ <code>choose=true</code> chỉ yêu cầu OP hiển thị UI; nó **không cấp quyền mới** và không được tin là bằng chứng account đã đổi.

Trong một hệ thống có provider không hỗ trợ <code>select_account</code>, nên chỉ thêm cờ cho các registration phù hợp thay vì áp dụng mặc định cho mọi provider.

### 11.5. Chống lạm dụng các custom query parameters

Không cho browser truyền tùy ý:

~~~text
prompt=none
redirect_uri=https://attacker.example
client_id=another-client
scope=admin
issuer=https://untrusted.example
~~~

rồi tự copy tất cả vào authorization request.

Nếu cần cho browser chọn giữa <code>login</code> hoặc <code>select_account</code>, sử dụng **allowlist các mode đã định nghĩa**, kiểm tra registration và chính sách sản phẩm. Redirect URI, Client ID, provider issuer và scopes nên lấy từ cấu hình server tin cậy.

## 12. Callback mới phải tạo Authentication mới, không “đổi tên” principal

Sau authorization code callback:

~~~text
GET /login/oauth2/code/partner?code=...&state=...
~~~

Spring Security:

1. Load authorization request gốc.
2. Kiểm tra state/registration/correlation.
3. Gửi code cùng client authentication/PKCE verifier phù hợp đến Token Endpoint.
4. Xác minh token response, ID Token và OIDC claims cho registration đã chọn.
5. Tải UserInfo khi phù hợp.
6. Tạo <code>OAuth2AuthenticationToken</code> và principal mới.
7. Lưu <code>SecurityContext</code> và authorized client theo cơ chế đã cấu hình.

Không thực hiện:

~~~java
oldAuthentication.setName("bob@example.org");
~~~

<code>Authentication</code> không nên bị biến đổi để mạo danh một identity khác. Việc đăng nhập mới phải đi qua flow xác thực chuẩn và được liên kết với một issuer/subject đã xác minh.

### 12.1. Phân biệt OAuth2User và OidcUser

Nếu registration có <code>openid</code> và provider hỗ trợ OIDC, principal thường là <code>OidcUser</code>.

Nếu provider chỉ có OAuth2 Login không OIDC, principal có thể là <code>OAuth2User</code> với cấu trúc user attributes riêng.

Code chuyển provider phải kiểm tra loại principal. Đừng ép một OAuth2-only provider thành OIDC issuer bằng cách đọc <code>email</code> từ UserInfo rồi tự tạo ID Token.

### 12.2. Không dùng email làm danh tính toàn cục

OIDC định danh user bằng cặp:

~~~text
(issuer, subject)
~~~

Ví dụ:

~~~text
("https://idp.example.org/realms/company", "u-123")
("https://login.partner.example.org",     "u-123")
~~~

Dù cùng <code>sub=u-123</code>, đây là **hai identity khác nhau**.

Ngược lại:

~~~text
Company: alice@example.org
Partner: alice@example.org
~~~

Hai providers có thể báo cùng email, nhưng không tự chứng minh cùng người. Email có thể được thay đổi, tái sử dụng, chưa verified hoặc thuộc các trust domains khác nhau.

## 13. Đọc provider hiện tại từ Authentication

Trong Spring Security Servlet, <code>OAuth2AuthenticationToken</code> chứa registration ID của authorized client đã dùng cho đăng nhập:

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@RestController
public class CurrentIdentityController {

    @GetMapping("/account/current")
    Map<String, String> current(Authentication authentication) {

        if (!(authentication instanceof OAuth2AuthenticationToken token)) {
            throw new ResponseStatusException(
                HttpStatus.UNAUTHORIZED,
                "No OAuth2 login principal");
        }

        return Map.of(
            "registrationId", token.getAuthorizedClientRegistrationId(),
            "principalName", token.getName());
    }
}
~~~

Giải thích:

- <code>getAuthorizedClientRegistrationId()</code> cho biết registration đã tạo OAuth2 login hiện tại.
- <code>getName()</code> là principal name do framework/provider quyết định; không mặc định là email.
- Không trả access token, ID Token, refresh token hoặc toàn bộ claims cho frontend.

Nếu ứng dụng có principal từ form login, API key, Resource Server JWT hay WebFlux, cần xử lý đúng kiểu Authentication. Ví dụ trên chủ ý chỉ phục vụ OAuth2 Login.

### 13.1. Khi cần issuer và subject của OIDC

~~~java
if (token.getPrincipal() instanceof OidcUser oidcUser) {
    String issuer = oidcUser.getIdToken()
        .getIssuer().toString();
    String subject = oidcUser.getSubject();
    // Dùng issuer + subject cho identity mapping nội bộ.
}
~~~

Import:

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
~~~

Chỉ dùng ID Token/claims sau khi Spring Security OIDC flow đã xác minh. Không làm identity mapping bằng cách Base64URL decode JWT do browser tùy ý cung cấp.

## 14. SecurityContext, session và token state khi switch

Đổi account tác động ít nhất ba lớp:

~~~mermaid
flowchart LR
    OLD["Active identity A"] --> LOGOUT["Local logout / identity switch"]
    LOGOUT --> SEC["SecurityContext / HTTP session"]
    LOGOUT --> AUTH["OAuth2 authorization request state"]
    LOGOUT --> TOK["OAuth2AuthorizedClient storage"]
    SEC --> NEW["New identity B"]
    AUTH --> NEW
    TOK --> POLICY["Cleanup theo policy riêng"]
~~~

### 14.1. Session đăng nhập

Nếu ứng dụng chỉ cho **một active identity per session**, local logout thường invalidate old HTTP session và clear SecurityContext trước flow mới.

Session fixation protection/session ID rotation trong quá trình authentication cần được Spring Security quản lý theo cấu hình; đừng tự gán lại old session ID cho account mới.

### 14.2. Authorization request repository

Mỗi authorization flow cần <code>state</code> mới, và có thể kèm <code>nonce</code>/<code>PKCE</code>. Trước khi bắt đầu flow mới, không tái sử dụng authorization request cũ của Company cho Partner.

Nếu browser mở nhiều tabs, hai flows có thể cạnh tranh cùng một authorization request repository tùy implementation. Cần hỗ trợ nhiều flows song song hoặc thông báo cho user, không bỏ state validation.

### 14.3. Authorized-client store

<code>OAuth2AuthorizedClient</code> có thể nằm trong:

- HTTP session qua <code>HttpSessionOAuth2AuthorizedClientRepository</code>.
- Một <code>OAuth2AuthorizedClientService</code> theo registration/principal.
- Redis/JDBC/custom token vault theo thiết kế.

**Invalidate HTTP session không bảo đảm xóa authorized client trong service-based store.**

Do đó sau khi switch:

~~~text
SecurityContext mới = Partner Bob
Token store còn record = Company Alice
~~~

Đây có thể là trạng thái hợp lệ nếu sản phẩm cho phép account linking/multi-connection với policy riêng, nhưng là rủi ro nếu code vô tình dùng token của Alice khi Bob đang là active user.

### 14.4. Khi nào xóa authorized client cũ?

Không có câu trả lời chung:

| Token storage policy | Khi switch identity nên cân nhắc |
|---|---|
| Per-session token | Invalidate session thường xóa dữ liệu session, nếu repository thật sự session-scoped |
| Per-principal shared token | Cân nhắc giữ/xóa theo lifetime/consent; xóa có thể ảnh hưởng browser session khác |
| Per-device/authorization | Chỉ xóa grant/session tương ứng theo key |
| Multiple linked accounts | Có thể giữ token của những kết nối đã xác minh, nhưng không lẫn active principal |
| High-security logout | Có thể yêu cầu revocation ở OP và invalidate sessions khác theo policy |

Không gọi <code>removeAuthorizedClient(registrationId, principalName)</code> theo tên user chưa xác minh hoặc do browser gửi. Nếu xóa token cũ, phải lấy identity/storage key từ server-side context tin cậy **trước khi làm mất authentication cũ**.

### 14.5. Refresh token có thể còn hiệu lực sau local logout

Local logout không mặc định thu hồi refresh token ở OP. Nếu sản phẩm yêu cầu user không còn có thể được ủy quyền sau switch, cân nhắc token revocation (RFC 7009) theo capability của provider.

Ngược lại, revoke toàn bộ token khi user chỉ muốn thêm/đổi provider có thể phá các integration khác đang sử dụng grant được giữ hợp lệ.

## 15. Một user liên kết nhiều providers: không nhầm account linking với switch

Một mô hình thường gặp:

~~~text
InternalAccount #105
    ├── Linked identity:
    │     issuer=Company OP, sub=user-abc
    └── Linked identity:
          issuer=Partner OP, sub=partner-xyz
~~~

Ứng dụng có thể cho user đăng nhập bằng một trong hai identities và ánh xạ về cùng InternalAccount #105.

**Account linking là một hành động cấp quyền/định danh nhạy cảm**, khác với việc đăng xuất user A rồi đăng nhập user B.

### 15.1. Nguy cơ chiếm tài khoản bằng email

Sai:

~~~text
Company user: email=alex@example.org
Partner user: email=alex@example.org

⇒ tự động gộp thành một internal account
~~~

Vì:

- Email có thể chưa được verified hoặc provider không có claim <code>email_verified</code>.
- Một provider không đáng tin có thể cho phép self-service đặt email theo người khác.
- Email có thể được tái sử dụng khi người dùng đổi tổ chức.
- Hai trust domains có thể có chính sách chứng minh sở hữu email khác nhau.
- Có <code>email_verified=true</code> ở một provider không mặc nhiên cho phép account linking với mọi provider.

### 15.2. Luồng account linking có chủ đích

Một thiết kế an toàn:

1. User đã đăng nhập vào internal account A.
2. User chọn chức năng **Liên kết provider B**, phân biệt rõ với **Đổi tài khoản đang đăng nhập**.
3. Với hành động nhạy cảm, yêu cầu reauthentication/MFA nếu policy cần.
4. Bắt đầu authorization flow mới tới provider B với **linking transaction/state** riêng.
5. Sau callback, validate toàn bộ OIDC response, lấy <code>(iss, sub)</code> của identity B.
6. Kiểm tra identity B chưa được liên kết với internal account khác.
7. Yêu cầu xác nhận hoặc áp dụng chính sách chứng minh quyền sở hữu cả hai identities.
8. Ghi liên kết trong transaction nhất quán, có unique constraint cho <code>(issuer, subject)</code>.
9. Log security event an toàn và thông báo cho account owner khi cần.
10. Giữ internal identity A làm principal hoặc chuyển theo policy **có kiểm soát**, không tự đổi giữa chừng.

### 15.3. Một sơ đồ account linking

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User đã login ở Account A
    participant APP as Portal
    participant OP as Provider B
    participant DB as Identity Mapping DB
    U->>APP: POST /account/link/provider-b (CSRF)
    APP->>APP: Kiểm tra A, reauth/step-up nếu cần
    APP->>APP: Tạo linking transaction với state mới
    APP-->>U: Redirect tới Provider B
    U->>OP: Login/chứng minh sở hữu identity B
    OP-->>APP: Authorization response code + state
    APP->>APP: Validate callback + ID Token của B
    APP->>DB: Kiểm tra (issuerB, subB) chưa thuộc account khác
    DB-->>APP: Có thể link
    APP->>DB: Commit link với internalAccountId=A
    APP-->>U: Xác nhận kết nối đã được thêm
~~~

**Không dùng session invalidation đơn giản của account switch làm account linking flow**, vì linking cần giữ chứng cứ user A đã xác thực để chứng minh ai yêu cầu gắn identity B.

### 15.4. Chống race khi link

Nếu hai internal accounts đồng thời cố link cùng <code>(issuer,sub)</code>, cần ràng buộc uniqueness/transaction ở DB. Chỉ kiểm tra trước bằng một SELECT rồi INSERT không có constraint có thể tạo liên kết trùng khi concurrency cao.

## 16. Multiple providers và OAuth2 mix-up protection

Khi một Client nói chuyện với nhiều Authorization Servers, cần phòng tránh **mix-up attacks**: response của provider A bị liên kết nhầm với request hoặc token endpoint của provider B.

Các nguyên tắc:

1. Authorization request phải gắn với registration/issuer đã chọn và <code>state</code> được lưu đáng tin.
2. Callback chỉ được đổi code với **đúng Token Endpoint** của request gốc.
3. Với OIDC, validate <code>iss</code>, <code>aud</code>, signature, expiration, nonce khi áp dụng.
4. Redirect URI của từng registration được đăng ký và xử lý chính xác.
5. Không dựa vào email hoặc query <code>provider=...</code> mới tại callback để thay registration.
6. Xem xét issuer identification trong authorization response theo RFC 9207 và biện pháp mix-up phù hợp với hỗ trợ framework/provider.
7. Khi dùng cùng callback path cho nhiều providers, cần chứng minh response được ràng buộc với issuer gốc, không chỉ đọc code.

### 16.1. Ví dụ nguy hiểm

~~~text
User bắt đầu login Company.
Ứng dụng lưu provider=Company.
Callback đến với ?provider=Partner&code=...
Ứng dụng tin query provider và gửi code sang Partner Token Endpoint.
~~~

Đây là xử lý sai. Registration của authorization code flow phải đến từ **authorization request được bảo vệ và correlate bằng state**, không phải từ tham số mới chưa tin cậy.

### 16.2. Tách login callback đúng provider

Sử dụng:

~~~text
/login/oauth2/code/company
/login/oauth2/code/partner
~~~

là một cách rõ ràng để cấu hình redirect URIs. Nhưng path riêng **không thay thế** state, issuer và token validation.

## 17. SavedRequest, redirect và dữ liệu giữa hai phiên

Sau OIDC Login, Spring Security có thể redirect user về URL ban đầu họ muốn xem thông qua request cache/success handler.

Khi user đổi danh tính, URL ban đầu có thể được lưu từ phiên cũ:

~~~text
Alice mở /admin/reports/finance
Alice chọn Switch to Bob
Bob login thành công
SavedRequest đưa Bob về /admin/reports/finance
~~~

Nếu Bob không được phép truy cập, backend phải trả 403. Tuy nhiên UX có thể gây nhầm lẫn; hơn nữa nếu code bỏ qua authorization để hiển thị nội dung đã cache từ Alice, đó là lỗi nghiêm trọng.

### 17.1. Quy tắc redirect sau switch

- Ưu tiên đưa user đến **trang trung lập an toàn**, ví dụ <code>/home</code> hoặc <code>/account/current</code>.
- Không giữ dữ liệu nghiệp vụ của identity cũ trong session mới.
- Nếu giữ <code>returnTo</code>, validate route nội bộ và authorization sau login.
- Không để browser gửi một URL tuyệt đối tùy ý vào OAuth state rồi redirect không kiểm tra.
- Sau switch, cache chứa dữ liệu tenant/user cũ cần được làm mới hoặc phân vùng theo identity.

### 17.2. Trường hợp browser có nhiều tabs

Browser thường dùng cùng cookie cho nhiều tabs:

~~~text
Tab A: đang xem dữ liệu Company Alice
Tab B: switch sang Partner Bob
Tab A: bấm thao tác ghi dữ liệu
~~~

Request mới ở Tab A có thể chạy trong session Bob sau khi switch. Nếu frontend hiển thị dữ liệu Alice nhưng request gửi dưới quyền Bob, dễ tạo thao tác sai đối tượng.

Biện pháp:

- Sau switch, phát event/poll identity version để tabs khác biết đã thay account.
- Gắn internal-account/tenant context vào API authorization, kiểm tra lại mỗi request.
- Không dựa vào UI cũ để cấp quyền.
- Với thao tác nhạy cảm, kiểm tra identity context và yêu cầu xác nhận/step-up khi cần.

### 17.3. Account switch generation

Trong hệ thống đòi tính nhất quán cao, có thể gắn một <code>identityGeneration</code> hoặc session generation:

~~~text
Old request: generation=17, identity=Alice
Switch:      generation=18, identity=Bob
~~~

Trước khi commit thao tác nhạy cảm, backend so sánh generation của request với identity hiện hành. Đây là **biện pháp bổ sung ở tầng ứng dụng**, không phải tính năng OAuth2 mặc định.

## 18. Chuyển provider trong Reactive WebFlux

WebFlux dùng cùng giao thức OAuth2/OIDC nhưng abstraction HTTP và security khác Servlet.

| Servlet | Reactive WebFlux |
|---|---|
| <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| <code>HttpSession</code> | <code>WebSession</code> |
| <code>SecurityContextHolder</code> theo thread context | <code>ReactiveSecurityContextHolder</code> / Reactor Context |
| <code>OAuth2AuthorizationRequestResolver</code> | <code>ServerOAuth2AuthorizationRequestResolver</code> |
| <code>OAuth2AuthorizedClientRepository</code> | <code>ServerOAuth2AuthorizedClientRepository</code> |
| <code>OidcClientInitiatedLogoutSuccessHandler</code> | <code>OidcClientInitiatedServerLogoutSuccessHandler</code> |

### 18.1. Cấu hình Reactive login và trang chọn provider

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveLoginSecurityConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .authenticationEntryPoint(
                    new org.springframework.security.web.server
                        .authentication.RedirectServerAuthenticationEntryPoint(
                            "/login")))
            .build();
    }
}
~~~

Snippet trên minh họa một reactive chain. Với phiên bản Spring Security cụ thể, cách cấu hình authentication entry point, login page hoặc exception handling có thể khác; giữ nguyên ý tưởng sử dụng **reactive components**, không copy <code>HttpSecurity</code> vào WebFlux.

Trang <code>/login</code> vẫn có thể cung cấp hai link:

~~~text
/oauth2/authorization/company
/oauth2/authorization/partner
~~~

Spring Security Reactive giải quyết callback bằng WebFilters/WebSession, không bằng Servlet filters.

### 18.2. Switch qua logout rồi chọn provider

Một phương án Reactivity-friendly:

1. Browser gửi **POST có CSRF** tới logout endpoint của WebFlux app.
2. Reactive logout handlers invalidate <code>WebSession</code>/SecurityContext theo cấu hình.
3. Logout success handler redirect tới <code>/login?choose=1</code>.
4. User chọn provider trên trang login.
5. Bắt đầu <code>/oauth2/authorization/{registrationId}</code> mới.

Ví dụ cấu hình redirect sau logout:

~~~java
import java.net.URI;

import org.springframework.security.web.server.authentication.logout
    .RedirectServerLogoutSuccessHandler;

RedirectServerLogoutSuccessHandler redirect =
    new RedirectServerLogoutSuccessHandler();
redirect.setLogoutSuccessUrl(URI.create("/login?choose=1"));

http.logout(logout ->
    logout.logoutSuccessHandler(redirect));
~~~

Đây là **đoạn cấu hình bổ sung** cho reactive chain, không phải một class đầy đủ. Người dùng có thể chọn provider sau khi logout. Muốn tự động chuyển thẳng sang provider đã chọn, cần custom success handler đọc lựa chọn đã được validate theo đúng Reactive API, tuyệt đối không gán session hiện hành bằng mutable singleton.

### 18.3. Reactive custom authorization request resolver

Với WebFlux, cần dùng **<code>ServerOAuth2AuthorizationRequestResolver</code>** và reactive WebExchange-based API. Không dùng <code>DefaultOAuth2AuthorizationRequestResolver</code> Servlet trong reactive pipeline.

Ý tưởng tương tự:

~~~text
Reactive default resolver
    → tạo OAuth2AuthorizationRequest chuẩn
    → nếu request dùng mode choose=true và registration là OIDC:
         bổ sung prompt=select_account
    → giữ state, nonce, PKCE, redirect URI, issuer binding
~~~

Nếu provider không hỗ trợ <code>select_account</code>, dùng flow/UX tương ứng hoặc RP-Initiated Logout có chủ đích. Không gọi <code>.block()</code> trong reactive filter để đọc/ghi WebSession.

### 18.4. Reactor Context sau khi đổi principal

<code>ReactiveSecurityContextHolder</code> gắn Authentication với reactive subscription. Đừng lưu Authentication cũ trong static field hoặc cache theo thread rồi tái sử dụng sau switch.

Các request sau login B phải đọc principal mới qua WebFlux security context, và token lookup phải dùng registration/principal tương ứng.

## 19. Multi-instance và session phân tán

Trong môi trường load balancer:

~~~text
Browser
   ↓
Load Balancer
   ├── Instance A
   └── Instance B
         ↓
    Shared session store
         ↓
    Authorized client store
~~~

Một flow có thể:

1. POST switch trên instance A, session cũ invalidated.
2. Authorization request mới được tạo trên A.
3. Callback provider B được điều phối sang instance B.
4. B cần tìm state/nonce/PKCE và session correlation từ shared session store hoặc session affinity phù hợp.
5. B ghi Authentication mới và authorized client đúng storage.

**Không chỉ lưu SecurityContext mà bỏ quên authorization request repository.** State của authorization flow mới phải còn khi callback đi qua node khác.

### 19.1. Một số nguy cơ

- In-memory session/authorization request state ở A khiến B báo <code>invalid_state</code>.
- Authorized client còn ở <code>InMemoryOAuth2AuthorizedClientService</code> của node cũ.
- User A và user B cùng key <code>principalName</code> nếu app không namespace theo issuer/tenant.
- Concurrent requests vẫn dùng token cũ trong lúc switch.
- Token refresh race hoặc failure handler xóa nhầm token đã được cập nhật.
- Logout session chỉ ở một node nhưng service token store chia sẻ toàn cluster.

### 19.2. Cơ chế giảm rủi ro

- Spring Session Redis/JDBC phù hợp Servlet/WebFlux để chia sẻ HTTP/WebSession.
- Authorized-client storage phân vùng đúng registration và trusted principal key.
- Identity generation hoặc session version cho tác vụ nhạy cảm khi cần.
- Chính sách cleanup/revocation rõ cho token của identity cũ.
- Không dùng single in-memory registry/lock để điều phối cluster.
- Kiểm tra session serialization compatibility khi rolling deployment.

Nếu sử dụng refresh token rotation giữa nhiều replica, việc chia sẻ token store không tự ngăn hai node cùng refresh R0. Khi cần, thêm single-flight coordination, reread after lock, CAS/conditional update và stale conditional delete.

## 20. Authorization và tenant isolation sau switch

Đăng nhập thành công **không có nghĩa mọi tài nguyên trước đây vẫn được phép**.

Ví dụ:

~~~text
Company Alice:
    role = FINANCE_ADMIN
    tenant = COMPANY_A

Partner Bob:
    role = PARTNER_VIEWER
    tenant = PARTNER_B
~~~

Sau switch sang Bob:

- Không kế thừa <code>FINANCE_ADMIN</code>.
- Không lấy dữ liệu từ cache key chỉ dựa vào route như <code>/reports</code>.
- Không dùng access token cũ của Company để gọi Partner API.
- Không giữ tenant mặc định Company trong request/session mới.
- Resource Server phải kiểm tra audience, scope, role và ownership độc lập.

### 20.1. Cache phải phân vùng theo identity

Sai:

~~~text
cacheKey = "dashboard"
~~~

Nếu dashboard có dữ liệu user/tenant, một user khác có thể nhận nhầm kết quả.

Tốt hơn:

~~~text
cacheKey = appId + internalAccountId + tenantId + dashboardVersion
~~~

Các thành phần key phải đến từ backend trusted context, không từ query parameters do browser tự khẳng định. Khi account switch, có thể invalidate user-specific caches nếu cần.

### 20.2. Quyền được đánh giá lại tại mỗi endpoint

Ngay cả nếu frontend biết user đang ở Partner, backend vẫn phải authorize mỗi action theo Authentication hiện tại. Không tin:

~~~http
X-Active-Account: company-admin
~~~

như bằng chứng cấp quyền. Header tùy ý từ browser chỉ có thể là request preference cần validation, không phải identity proof.

### 20.3. Provider choice khác consent scopes

Một account mới ở cùng provider có thể cấp ít scopes hơn account cũ. <code>ClientRegistration.getScopes()</code> là danh sách yêu cầu, không phải bảo đảm Token Endpoint cấp đủ.

Sau login, kiểm tra token scopes thực cấp, Resource Server audience và quyền nghiệp vụ. Đừng refresh liên tục một token <code>403 insufficient_scope</code> rồi mong tự nâng quyền.

## 21. Người dùng chọn account khác nhưng OP vẫn trả account cũ

Đây là trường hợp thường gặp nhất khi thử switch account.

### 21.1. Phân tích nguyên nhân

1. Local session đã bị xóa chưa?
2. Browser còn OP SSO cookie không?
3. Authorization request có thật sự chứa <code>prompt=select_account</code> không?
4. Provider có hỗ trợ tham số này không?
5. Provider có account-selection policy riêng hoặc giới hạn tenant không?
6. Browser đang có bao nhiêu sessions tại OP?
7. Có <code>login_hint</code> vô tình ép UI trở lại Alice không?
8. Token callback đã validate và trả <code>iss/sub</code> nào?

### 21.2. Không cố thay subject phía Client

Sai:

~~~text
OP trả ID Token: sub=alice
Ứng dụng muốn Bob
⇒ tự ghi principalName=bob
~~~

Việc làm này tạo danh tính không khớp authentication proof. Cách đúng là yêu cầu một **authorization/authentication flow khác** để OP thực sự xác thực Bob, hoặc báo người dùng không thể đổi theo capability hiện tại của provider.

### 21.3. Có thể dùng RP-Initiated Logout không?

Có, nếu OP hỗ trợ và người dùng đồng ý ảnh hưởng SSO. Sau logout OP, browser có thể được chuyển về trang chọn provider hoặc login lại.

Tuy nhiên ngay cả RP-Initiated Logout cũng không cam kết UI sẽ cho chọn account nào; hành vi cuối cùng phụ thuộc OP, SSO federation và browser cookies.

## 22. Hướng dùng RP-Initiated Logout trong Servlet

Với OIDC provider có <code>end_session_endpoint</code>, Spring Security có thể hỗ trợ redirect browser sang OP logout.

Ví dụ:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout
    .OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class GlobalOidcLogoutConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            ClientRegistrationRepository registrations)
            throws Exception {

        var success =
            new OidcClientInitiatedLogoutSuccessHandler(
                registrations);
        success.setPostLogoutRedirectUri("{baseUrl}/login");

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(success));

        return http.build();
    }
}
~~~

**Đây là cấu hình thay thế cho SecurityFilterChain đơn giản trước đó**, không ghép các bean chain trùng matcher.

Khi user logout:

1. Local session được xử lý bởi logout filters.
2. OIDC logout success handler xác định OP liên quan từ authentication/OIDC client configuration theo framework.
3. Handler redirect browser tới OP logout endpoint.
4. OP có thể kết thúc SSO session và redirect lại tới <code>/login</code> nếu post-logout redirect đã đăng ký/được phép.

Với nhiều providers, cần kiểm tra rằng logout success handler chọn đúng registration của **authentication hiện tại**. Không gửi <code>id_token_hint</code> của provider A tới provider B.

Không dùng global OP logout cho thao tác “đổi provider” nếu sản phẩm chỉ muốn local identity switch. Hai UX khác nhau cần được trình bày rõ.

### 22.1. Post-logout redirect URI

<code>{baseUrl}/login</code> là redirect nội bộ ví dụ. OP có thể yêu cầu đăng ký <code>post_logout_redirect_uri</code> chính xác.

Không cho browser đặt một URL tùy ý vào post-logout redirect, tránh open redirect/phishing và rò rỉ token/hint.

### 22.2. Trường hợp provider không phải OIDC

Một provider chỉ hỗ trợ OAuth2 Login không nhất thiết có OIDC <code>end_session_endpoint</code> hoặc ID Token. OIDC logout success handler có thể không thực hiện OP logout theo cách tương tự.

Với provider không OIDC, cần xem provider-specific logout protocol và local session policy; không giả lập một ID Token để dùng OIDC logout.

## 23. Failure handling trong switch-account flow

Sau khi local logout và bắt đầu login mới, một số lỗi có thể xảy ra:

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| User hủy login ở OP | Không có Authentication mới | Đưa về trang chọn provider; không phục hồi phiên cũ tùy tiện |
| OP trả <code>access_denied</code> | User từ chối consent hoặc policy | Thông báo an toàn, cho chọn lại |
| OP báo <code>login_required</code> | Silent login không thực hiện được | Dùng interactive flow nếu cần |
| OP không hiểu <code>prompt</code> | Request bị từ chối hoặc bỏ qua | Kiểm tra provider capability, fallback UX |
| <code>redirect_uri_mismatch</code> | Authorization initiation/callback lỗi | Sửa registration/proxy/OP config |
| Callback <code>invalid_state</code> | Correlation không đạt | Kiểm tra session/state repository; không bỏ state validation |
| Token Endpoint từ chối code | Không tạo principal mới | Kiểm tra code lifetime, PKCE, Client auth |
| ID Token sai issuer/audience | Login bị từ chối | Kiểm tra registration và OP, không bỏ validation |
| Account B bị khóa nội bộ | OIDC authentication có thể thành công nhưng app từ chối truy cập | Áp dụng business account policy |
| Account B thiếu role/tenant | App/API trả 403 | Không kế thừa quyền từ A |
| OP SSO vẫn chọn A | Switch-account không đạt mục tiêu UX | Dùng account chooser/reauth theo provider |
| Token cũ vẫn trong service store | Có thể gây stale token nếu app dùng sai principal | Kiểm tra token cleanup/isolation |

### 23.1. Không tự phục hồi session cũ khi login mới thất bại

Nếu sản phẩm chọn cách **invalidate session trước khi switch**, một lỗi login mới không nên tự khôi phục Authentication cũ từ token cache mà không chứng minh nó còn hợp lệ.

Nếu muốn UX “chuyển account nhưng có thể hủy và quay lại”, cần thiết kế transaction riêng cho switching, ràng buộc session và thời gian hiệu lực, không dùng một biến browser <code>oldUser=alice</code> để phục hồi.

### 23.2. Phân biệt lỗi xác thực và lỗi liên kết tài khoản

OIDC Login của Bob có thể thành công nhưng thao tác link Bob vào internalAccount Alice thất bại do đã được liên kết với account khác.

Đây là **lỗi account linking policy**, không phải token signature mismatch. Cần trả thông báo an toàn, không hiển thị danh tính của account khác nếu không được phép.

## 24. Những lỗi triển khai phổ biến

| Sai lầm | Vì sao có vấn đề | Cách làm phù hợp |
|---|---|---|
| Đổi provider bằng <code>session.setAttribute("provider")</code> | SecurityContext vẫn là identity cũ | Dùng OAuth2/OIDC login mới |
| Chỉ xóa local session và chắc chắn OP hiện account chooser | OP SSO cookie vẫn tồn tại | Dùng <code>prompt=select_account</code> nếu OP hỗ trợ |
| Dùng <code>prompt=login</code> để khẳng định đã chọn Bob | Reauth có thể vẫn xác thực Alice | Đọc <code>iss/sub</code> từ ID Token đã validate |
| Dùng <code>login_hint</code> như authentication | Hint không phải bằng chứng danh tính | Chỉ coi là UX hint |
| Tin <code>provider</code> query lúc callback | Có thể gây mix-up | Binding với state và ClientRegistration gốc |
| Cho browser nhập issuer/token endpoint tùy ý | SSRF/token leakage/mix-up | Allowlist registrations |
| Gộp account theo email giống nhau | Account takeover risk | Linking có xác minh <code>(iss,sub)</code> |
| Giữ authorized client token của user A làm token mặc định sau switch | Rò rỉ quyền user A sang B | Token scoped theo registration/principal |
| Chọn registration theo tên domain email | Không đảm bảo OP/tenant trusted | Provider selection server-side |
| Không invalidate/rotate session ở identity switch | Session fixation và dữ liệu phiên cũ | Dùng SecurityContextLogoutHandler/standard filters |
| Tắt CSRF để nút switch POST không bị 403 | Làm yếu browser routes | Gửi CSRF token đúng |
| Dùng OP logout cho mọi switch provider | Có thể đăng xuất user khỏi ứng dụng khác | Phân biệt local switch và global logout |
| Bỏ <code>state</code> khi nhiều tabs callback lỗi | Mở OAuth login CSRF/mix-up | Thiết kế repository nhiều flows hoặc UX |
| Caching profile theo tên route | Cross-account data leakage | Partition cache theo identity/tenant |
| Dùng cùng ID Token như access token gửi API | Sai token purpose/audience | Dùng access token đúng Resource Server |
| In raw tokens vào logs lúc debug | Lộ credential | Log metadata đã làm sạch |
| Không xét multi-instance | Callback/token store mất state giữa replicas | Shared session/storage phù hợp |

## 25. Quy trình chẩn đoán có hệ thống

Nếu user nói “Tôi đã chọn Bob nhưng trang vẫn là Alice”:

~~~text
Người dùng đã bấm switch-account?
    |
    v
POST /account/switch có qua CSRF và allowlist?
    |
    v
Local session cũ có bị kết thúc?
    |
    v
Authorization initiation có chọn đúng ClientRegistration?
    |
    v
Authorization request có prompt/select_account nếu cần?
    |
    v
OP có hỗ trợ prompt và đưa ra UI chọn account?
    |
    v
Callback có state/nonce/PKCE đúng?
    |
    v
ID Token mới đã validate có (iss,sub) nào?
    |
    +-- Vẫn là Alice
    |      → OP SSO/chooser policy chưa tạo identity khác
    |
    +-- Là Bob
           |
           v
      SecurityContext được lưu với Bob?
           |
           v
      Authorized client dùng token của Bob?
           |
           v
      Internal account/tenant/cache đã cập nhật?
           |
           v
      API authorization quyết định quyền của Bob?
~~~

Nếu ID Token đã xác minh là Bob mà UI vẫn hiển thị Alice, vấn đề thường ở **session/security context/caching hoặc internal identity mapping**, không phải OP chưa xác thực Bob.

### 25.1. Log phục vụ điều tra

Những field có thể hữu ích:

~~~text
requestId=...
switchMode=provider
previousRegistration=company
selectedRegistration=partner
oauth2CallbackStateValidation=success
oidcIssuerAlias=partner-idp
internalAccountMappingOutcome=found
newPrincipalKeyHash=...
sessionRotated=true
authorizedClientRegistration=partner
~~~

Không log:

~~~text
authorization_code
code_verifier
state / nonce thật
id_token JWT
access_token / refresh_token
client_secret
session cookie
~~~

Nếu cần phân tích identity, dùng hashed/correlated identifiers theo chính sách và kiểm soát retention/access. Không đưa email raw vào metric labels.

## 26. Thiết kế UX để người dùng không nhầm thao tác

Một trang tài khoản nên phân biệt ba hành động:

**Đổi tài khoản đang dùng**

> Kết thúc phiên làm việc hiện tại và đăng nhập bằng một tài khoản khác. Những dữ liệu chưa lưu có thể mất.

**Đổi phương thức đăng nhập**

> Chọn một nhà cung cấp danh tính khác để đăng nhập vào ứng dụng.

**Liên kết một tài khoản khác**

> Giữ tài khoản hiện tại, xác minh thêm một danh tính từ provider khác và liên kết theo chính sách.

Nếu giao diện chỉ có một nút “Add account” nhưng code lại invalidate session và thay active principal, user có thể hiểu sai và mất công việc đang làm.

### 26.1. Xác nhận trước khi switch

Nếu có tác vụ đang sửa:

- Cảnh báo dữ liệu chưa lưu.
- Cho user xác nhận đổi identity.
- Đưa về trang an toàn sau login.
- Cập nhật tabs khác về identity mới.
- Không tự động gửi lại các request ghi dữ liệu cũ dưới quyền user mới.

### 26.2. Phân biệt scope và quyền

Sau switch, UI có thể thay đổi role/tenant. Nhưng UI không phải enforcement point: backend và Resource Server vẫn phải kiểm tra authorization.

## 27. Các tình huống kiểm thử cần có

| Kịch bản | Kỳ vọng |
|---|---|
| User chưa login chọn Company | Redirect đúng Company OP |
| User chưa login chọn Partner | Redirect đúng Partner OP |
| User Company POST switch sang Partner có CSRF | Session cũ kết thúc, flow mới được khởi tạo |
| User Company POST switch thiếu CSRF | Request bị từ chối |
| User gửi provider không thuộc allowlist | 400/validation failure, không redirect tới issuer lạ |
| User Company switch lại Company, không có prompt | Có thể SSO trở lại cùng account; UX cần diễn đạt đúng |
| User Company switch lại Company với <code>select_account</code> | OP được yêu cầu cho chọn account nếu hỗ trợ |
| User Company switch sang Bob | Callback tạo verified <code>(iss,sub)</code> của Bob |
| OP trả <code>access_denied</code> | Không tạo Authentication Bob |
| Callback state sai | Không tạo phiên authenticated mới |
| ID Token từ Company đưa vào callback Partner | Bị từ chối do issuer/audience/correlation |
| Hai providers có email giống nhau | Không tự động account linking |
| User B thiếu quyền của A | API chặn theo B, không kế thừa role A |
| Authorized-client store chứa token A và B | Request B chỉ chọn đúng registration/principal |
| User logout một session khác của cùng principal | Cleanup token theo policy, không xóa ngoài phạm vi |
| Two-tab switch | Không dùng stale principal/data để ghi tài nguyên |
| Callback sang instance khác | State/session/token storage hoạt động hoặc thất bại an toàn |

## 28. Bài tập thực hành

### Bài 1 — Đổi provider

Ứng dụng đang authenticated bằng Company. Người dùng chọn Partner và đăng nhập thành công qua Partner.

**Câu hỏi:** Cần đổi thuộc tính nào để Spring Security bắt đầu Partner authorization flow?

**Đáp án:** Dùng đúng <code>registrationId=partner</code> tại <code>/oauth2/authorization/partner</code> sau khi xử lý local identity-switch policy. Không sửa issuer/Client ID bằng query parameter từ browser.

### Bài 2 — SSO tự động quay lại Alice

User local logout rồi gọi <code>/oauth2/authorization/company</code>. OP trả code ngay cho Alice.

**Câu hỏi:** Đây có phải bug state validation không?

**Đáp án:** Không nhất thiết. OP vẫn có SSO session của Alice. Cân nhắc <code>prompt=select_account</code> hoặc account-selection flow provider hỗ trợ.

### Bài 3 — Select_account và login

**Câu hỏi:** <code>prompt=login</code> có luôn đảm bảo chọn Bob thay Alice?

**Đáp án:** Không. Nó yêu cầu reauthentication, không phải một lệnh xác định account. <code>prompt=select_account</code> phù hợp hơn để yêu cầu account chooser, nhưng provider có thể có giới hạn.

### Bài 4 — max_age=0

Provider yêu cầu reauthentication và ID Token trả <code>iat</code> mới nhưng <code>auth_time</code> cũ.

**Câu hỏi:** Có nên chỉ nhìn <code>iat</code> để kết luận user vừa nhập lại mật khẩu không?

**Đáp án:** Không. <code>iat</code> là thời điểm phát ID Token; <code>auth_time</code> mới phản ánh thời điểm authentication theo OIDC. Cần validation đúng yêu cầu <code>max_age</code>.

### Bài 5 — Trùng email

Company và Partner cùng trả email <code>alice@example.org</code>, nhưng issuer/sub khác nhau.

**Câu hỏi:** Có thể tự động link hai account không?

**Đáp án:** Không. Phải có linking flow có chủ đích, xác minh quyền sở hữu/consent theo policy và tránh account takeover.

### Bài 6 — POST không CSRF

Một link ngoài website gọi GET <code>/account/switch?provider=partner</code> làm portal invalidate session.

**Câu hỏi:** Có vấn đề gì?

**Đáp án:** Request có side effect qua GET, có thể bị ép điều hướng. Dùng POST với CSRF protection, kiểm tra provider và xác thực user hiện tại.

### Bài 7 — Invalid provider

Browser gửi <code>provider=https://attacker.example</code>.

**Câu hỏi:** Hệ thống có nên tạo <code>ClientRegistration</code> động cho URL đó không?

**Đáp án:** Không theo mô hình bài này. Chỉ dùng allowlisted registrations/issuers do server quản lý; tránh SSRF, OAuth mix-up và credential leakage.

### Bài 8 — Token cũ trong JDBC

Session Alice đã invalidated nhưng <code>JdbcOAuth2AuthorizedClientService</code> còn token của Alice.

**Câu hỏi:** Có phải Spring Security logout tự động sai?

**Đáp án:** Không nhất thiết. Session invalidation và service-backed authorized-client cleanup là hai vòng đời riêng. Cần token retention/revocation policy và đảm bảo Bob không dùng token Alice.

### Bài 9 — Hai tab

Tab A hiện dữ liệu của Company, Tab B switch sang Partner. Tab A gửi POST thay đổi dữ liệu.

**Câu hỏi:** Bảo vệ ở đâu?

**Đáp án:** Backend phải authorize theo Authentication và tenant hiện hành; có thể thêm identity/session generation để ngăn stale actions. Không tin UI cũ.

### Bài 10 — Account linking

Bob tại Partner đã liên kết với internalAccount #200. Alice tại Company muốn link Bob vào internalAccount #105.

**Câu hỏi:** Hệ thống có nên chuyển link tự động không?

**Đáp án:** Không. Có unique constraint và policy kiểm soát ownership; cần chặn hoặc quy trình được ủy quyền riêng, không tạo liên kết cùng identity tới hai accounts một cách im lặng.

### Bài 11 — Multi-instance callback

Login Partner bắt đầu trên node A, callback được load balancer gửi tới B, báo <code>invalid_state</code>.

**Câu hỏi:** Có thể bỏ state validation để giải quyết không?

**Đáp án:** Không. Cần shared session/authorization request repository hoặc routing phù hợp, kiểm tra cookies và proxy.

### Bài 12 — Wrong-issuer callback

User bắt đầu Company flow, một response của Partner được chuyển tới callback Company.

**Câu hỏi:** Hệ thống phải làm gì?

**Đáp án:** Từ chối khi state/registration/issuer/audience hoặc OIDC validation không đạt. Không chọn lại provider theo email/query để “cứu” flow.

### Bài 13 — Thiết kế switching flow

Hãy xây một ứng dụng có:

1. Hai OIDC ClientRegistrations <code>company</code> và <code>partner</code>.
2. Trang <code>/login</code> chọn provider.
3. <code>SecurityFilterChain</code> có <code>oauth2Login()</code>.
4. POST <code>/account/switch</code> với CSRF và registration allowlist.
5. Local session logout rồi redirect tới OAuth2 initiation.
6. Resolver tùy biến <code>prompt=select_account</code> cho cùng provider khi hỗ trợ.
7. Callback/ID Token validation đúng state, issuer, audience, nonce.
8. Identity mapping theo <code>(iss,sub)</code>.
9. Authorized client token isolation và cleanup theo policy.
10. Redirect post-switch về trang an toàn, không giữ cache dữ liệu user cũ.
11. Test cùng browser nhiều tabs và cluster hai instances.
12. Log metadata an toàn, không log token, code, state, session cookie.

Giải thích vì sao **“chuyển provider” không tự thực hiện “liên kết tài khoản”**, và vì sao **“local logout” không tự ép OP hiển thị account chooser**.

## 29. Ghi nhớ

- **Đổi provider** là bắt đầu authorization flow bằng <code>ClientRegistration</code> khác; **đổi account tại cùng provider** là yêu cầu OP xác thực một identity khác bằng cùng registration.
- <code>/oauth2/authorization/{registrationId}</code> dùng chọn provider đã đăng ký, không cho browser tự cấu hình issuer/token endpoint.
- **Local logout chỉ kết thúc phiên ở Client.** Browser vẫn có thể giữ SSO session tại OP và tự login lại cùng tài khoản.
- Với OIDC, <code>prompt=select_account</code> yêu cầu account chooser; <code>prompt=login</code> yêu cầu reauthentication; <code>max_age=0</code> yêu cầu authentication freshness; <code>login_hint</code> chỉ là gợi ý.
- Không có tham số nào cho phép Client tự quyết định <code>sub=Bob</code>. Identity phải được OP xác thực và callback được validate đầy đủ.
- Khi đổi danh tính đang hoạt động, nên dùng thao tác **POST có CSRF**, allowlist registration, invalidate/rotate local session và bắt đầu flow mới với state/nonce/PKCE mới.
- **SecurityContext, authorization request repository và OAuth2AuthorizedClient storage là ba trạng thái khác nhau.** Invalidate session không tự xóa token trong persistent service.
- Trong nhiều providers, OIDC identity phải được xác định bằng **<code>(issuer, subject)</code>**, không tự gộp theo email hoặc <code>sub</code> không có issuer.
- **Account switching khác account linking.** Linking cần xác minh cả hai identities, chính sách quyền sở hữu, unique constraint và bảo vệ chống account takeover.
- Không để token, role, tenant, cached data hoặc saved requests của user A vô tình theo sang user B sau switch.
- Với multiple Authorization Servers, cần chống mix-up bằng state/registration binding, exact callbacks, issuer/audience/nonce validation và biện pháp phù hợp theo RFC 9207 khi được hỗ trợ.
- Trong WebFlux, dùng reactive security/session/resolver; trong Servlet dùng <code>HttpSecurity</code>, <code>SecurityFilterChain</code> và Servlet request APIs. Không trộn stack.
- Với nhiều instance, chia sẻ session/correlation state và token storage đúng phạm vi; theo dõi refresh concurrency và token cleanup.

### Tài liệu tham khảo

- **Spring Security Reference — OAuth2 Login (Servlet):** <code>oauth2Login()</code>, login page, authorization initiation, ClientRegistration, success/failure handling.
- **Spring Security Java API — DefaultOAuth2AuthorizationRequestResolver:** tùy biến authorization request parameters theo registration và request context.
- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClient</code>, repository/service, token lifecycle và authorized client manager.
- **Spring Security Reference — Reactive OAuth2 Login:** <code>SecurityWebFilterChain</code>, WebSession, reactive authorization request resolver.
- **Spring Security Reference — Servlet và Reactive Logout:** <code>SecurityContextLogoutHandler</code>, <code>OidcClientInitiatedLogoutSuccessHandler</code>, <code>OidcClientInitiatedServerLogoutSuccessHandler</code>.
- **OpenID Connect Core 1.0:** Authorization Code Flow, <code>prompt</code>, <code>login_hint</code>, <code>max_age</code>, <code>auth_time</code>, ID Token, <code>iss</code>/<code>sub</code>.
- **OpenID Connect RP-Initiated Logout 1.0:** <code>end_session_endpoint</code>, <code>id_token_hint</code>, post-logout redirect.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Token Endpoint và <code>state</code>.
- **RFC 7636 — Proof Key for Code Exchange:** PKCE và authorization code binding.
- **RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification:** issuer identification và mix-up mitigation.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** authorization response protection, redirect URI, session/token security.
- **OWASP Authentication Cheat Sheet và Session Management Cheat Sheet:** session fixation, reauthentication, session lifecycle và account security.
