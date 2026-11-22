# SecurityFilterChain, AuthenticationProvider và AuthenticationEntryPoint trong SSO

**Module:** Spring Security – federation  
**Nhóm kiến thức:** Nền tảng Spring  
**Bối cảnh kỹ thuật:** Ứng dụng Servlet/Spring MVC, Java 17+, Spring Boot 3.x và Spring Security 6.x. Các ví dụ chủ yếu sử dụng **OpenID Connect (OIDC) Authorization Code Flow**; OAuth 2.0 Resource Server được đưa vào để phân biệt luồng API với đăng nhập web.

## 1. Ba thành phần trả lời ba câu hỏi khác nhau

Trong một ứng dụng SSO, khi người dùng truy cập tài nguyên cần đăng nhập, Spring Security phải **chọn cơ chế bảo vệ request**, **xác minh bằng chứng xác thực** và **xác định cách phản hồi khi người dùng chưa có bằng chứng**.

| Thành phần | Câu hỏi giải quyết | Đặc điểm | Ví dụ trong SSO |
| --- | --- | --- | --- |
| **SecurityFilterChain** | Request này đi qua những security filter nào? | Mỗi chain có **RequestMatcher** và danh sách filter; **FilterChainProxy** chọn chain đầu tiên khớp | Web chạy OIDC login, API chạy Bearer JWT |
| **AuthenticationProvider** | Bằng chứng xác thực này có hợp lệ không và chủ thể là ai? | Thành phần chuyên xử lý một kiểu **Authentication**, được gọi thông qua **AuthenticationManager**, thường là **ProviderManager** | **OidcAuthorizationCodeAuthenticationProvider** xử lý OIDC code flow; **JwtAuthenticationProvider** xác minh access token cho API |
| **AuthenticationEntryPoint** | Khi chưa xác thực, ứng dụng yêu cầu client bắt đầu xác thực bằng cách nào? | Sinh response HTTP để khởi động cơ chế xác thực; thường được **ExceptionTranslationFilter** gọi | Web **302** tới trang/đường dẫn bắt đầu login; API **401** với **WWW-Authenticate: Bearer** |

**Dễ nhớ:** SecurityFilterChain chọn **đường xử lý request**; AuthenticationProvider kiểm tra **credentials/chứng cứ**; AuthenticationEntryPoint trả lời **“hãy xác thực theo cách này”** khi cần. Chúng hợp tác nhưng không có thành phần nào tự mình tạo ra toàn bộ quy trình SSO.

**Điểm quan trọng:** Trong Spring Security, **AuthenticationEntryPoint không phải Identity Provider**. “Entry point” là một chiến lược phản hồi HTTP bên trong ứng dụng của bạn, còn **OpenID Provider (OP)/Identity Provider (IdP)** là hệ thống bên ngoài thực sự xác thực người dùng.

## 2. Kiến trúc tổng quan của Spring Security Servlet

Một request HTTP đi qua chuỗi khái niệm sau:

~~~text
HTTP request (browser hoặc API client)
        |
        v
DelegatingFilterProxy
        |
        v
FilterChainProxy (springSecurityFilterChain)
        |
        | Chọn SecurityFilterChain ĐẦU TIÊN khớp RequestMatcher
        |
        +--> /api/**      -> BearerTokenAuthenticationFilter -> AuthenticationManager
        |                                                   -> JwtAuthenticationProvider
        |                                                   -> JwtDecoder
        |
        +--> /**          -> OAuth2AuthorizationRequestRedirectFilter
                            OAuth2LoginAuthenticationFilter -> AuthenticationManager
                                                              -> OIDC AuthenticationProvider
                            ExceptionTranslationFilter + AuthenticationEntryPoint
                            AuthorizationFilter
        |
        v
SecurityContext / Authorization / Controller
~~~

Đây là **sơ đồ khái niệm**, không phải thứ tự đầy đủ của mọi filter. Spring Security còn có filter về security context, CSRF, headers, logout, request cache, v.v. Thứ tự thật phụ thuộc cấu hình và phiên bản. **Không tự thay thứ tự filter** nếu chưa hiểu vị trí cần chèn.

### 2.1. SecurityFilterChain khác Servlet Filter thế nào?

- **SecurityFilterChain** không chỉ là một filter tự tạo. Nó khai báo **RequestMatcher + danh sách filter** cho một nhóm request. Spring Security dùng FilterChainProxy để phối hợp các chain.
- **FilterChainProxy** là cầu nối giữa servlet container và các filter của Spring Security; thông thường thông qua **DelegatingFilterProxy**.
- Có thể định nghĩa nhiều SecurityFilterChain bằng các bean khác nhau. Mỗi request chỉ được **chain khớp đầu tiên** xử lý theo thứ tự ưu tiên.
- Nếu **không chain nào khớp**, request không được bảo vệ bởi Spring Security filter chain đó. Vì vậy thường cần một **chain cuối bao phủ các URL còn lại**.
- Nếu không có lý do tách API và web, **một chain** cũng hoàn toàn có thể cấu hình SSO. Tách chain chỉ khi cơ chế xác thực/response thực sự khác nhau.

### 2.2. AuthenticationManager và ProviderManager nằm ở đâu?

Filter xử lý credentials thông thường tạo một đối tượng **Authentication chưa xác thực**, rồi gọi **AuthenticationManager.authenticate(authentication)**. Triển khai phổ biến là **ProviderManager**, thử các **AuthenticationProvider** tương ứng loại token. Khi thành công, một đối tượng **Authentication đã xác thực** được trả về và được filter cập nhật vào SecurityContext theo cơ chế của filter đó.

**AuthenticationProvider không trực tiếp lựa chọn HTTP URL; AuthenticationEntryPoint cũng không tự giải mã JWT hoặc trao đổi OAuth authorization code.**

## 3. SecurityFilterChain: chia vùng bảo vệ web SSO và REST API

Một ứng dụng có thể vừa là:

1. **OIDC Relying Party (RP):** dùng browser redirect đến OP để nhân viên đăng nhập, sau đó tạo **phiên ứng dụng**.
2. **OAuth 2.0 Resource Server:** nhận **Bearer access token** để bảo vệ REST API, không yêu cầu trình duyệt chuyển đến màn hình đăng nhập.
3. **OAuth 2.0 Client:** có thể xin và quản lý access token để gọi API khác; chức năng này không đồng nghĩa với resource server.

Vì cơ chế và kiểu client khác nhau, thông thường định nghĩa:

| Chain | Phạm vi | Cơ chế chính | Phản hồi khi chưa xác thực |
| --- | --- | --- | --- |
| **apiChain – @Order(1)** | **/api/** | **oauth2ResourceServer().jwt()**; Stateless | **401** Bearer challenge |
| **webChain – @Order(2)** | Các URL còn lại (**/**) | **oauth2Login()**; session cho browser | **302** vào luồng OIDC login |

### securityMatcher khác requestMatchers

**securityMatcher("/api/**")** nằm ở mức **chọn SecurityFilterChain**: toàn bộ danh sách filter của chain đó chỉ xử lý đường dẫn khớp.

**authorizeHttpRequests().requestMatchers("/public/**").permitAll()** chỉ quyết định **quyền truy cập** bên trong chain đã được chọn; nó không chuyển request sang chain khác.

Ví dụ:

- **GET /api/report** khớp chain API đứng trước. Dù webChain cũng có matcher mặc định bao phủ mọi request, **webChain sẽ không chạy cho request này**.
- **GET /dashboard** không khớp /api/** nên được webChain xử lý.
- **GET /login/oauth2/code/company** cũng phải đi qua webChain để **OAuth2LoginAuthenticationFilter** nhận callback; nếu webChain chỉ match **/app/** mà bỏ qua callback, login có thể hỏng.
- **/oauth2/authorization/company** là endpoint bắt đầu authorization request trong webChain; nó cũng phải nằm trong phạm vi được bảo vệ/điều phối đúng.
- Với nhiều chain chuyên biệt, sử dụng **@Order** rõ ràng; một matcher quá rộng có thể “nuốt” request của chain phía sau.

### Chain không tự động chứa mọi filter

Chọn chain bằng matcher chưa đủ. Muốn xử lý OIDC callback phải kích hoạt **oauth2Login()** (hoặc cấu hình tương đương). Muốn xác minh JWT Bearer phải bật **oauth2ResourceServer().jwt()** (hoặc cấu hình tương đương). Nếu chỉ cấu hình **anyRequest().authenticated()** nhưng không cung cấp cơ chế xác thực phù hợp, người dùng có thể gặp 401/403 mà không có luồng SSO mong đợi.

## 4. AuthenticationProvider: ai thực sự xác minh bằng chứng?

### 4.1. Authentication và ProviderManager

**Authentication** có thể biểu diễn yêu cầu chưa kiểm tra (ví dụ token mang authorization code hoặc Bearer token) hay chủ thể đã xác thực (principal, authorities, trạng thái authenticated).

**AuthenticationProvider** có hai phương thức cốt lõi:

~~~java
Authentication authenticate(Authentication authentication)
    throws AuthenticationException;

boolean supports(Class<?> authentication);
~~~

Đây là **chữ ký trích gọn của interface** để giải thích, không phải một tệp Java độc lập để biên dịch.

- **supports(type):** provider có thể xử lý loại Authentication này hay không.
- **authenticate(input):** trả về kết quả đã xác thực nếu thành công; **throw AuthenticationException** khi xác thực thất bại; có thể trả về **null** nếu không thể đưa ra kết luận để provider khác thử.
- **ProviderManager:** điều phối danh sách provider; nếu không provider nào xử lý được kiểu đầu vào, thường phát sinh **ProviderNotFoundException**.
- Provider **không tự động được gọi với mọi request**: phải có filter hoặc mã thực thi chuyển Authentication đến AuthenticationManager thích hợp.

Không nên hiểu rằng **supports() = true** có nghĩa credentials hợp lệ. Nó chỉ nói provider nhận dạng được loại Authentication.

### 4.2. Provider mặc định trong OIDC login

Luồng Spring Security OIDC sử dụng các thành phần có sẵn, ví dụ:

- **OAuth2AuthorizationRequestRedirectFilter:** tạo authorization request và đưa trình duyệt đến authorization endpoint; filter này khởi tạo flow, chưa xác minh ID token.
- **OAuth2LoginAuthenticationFilter:** xử lý callback authorization code, tạo **OAuth2LoginAuthenticationToken** và chuyển đến AuthenticationManager.
- **OidcAuthorizationCodeAuthenticationProvider:** provider chuyên xử lý **OIDC Authorization Code Flow**, trao code/token endpoint, xác minh ID token thông qua các thành phần OIDC và xây dựng principal dạng **OidcUser**.
- **OAuth2LoginAuthenticationProvider:** hỗ trợ **OAuth 2.0 Login** không dùng OIDC, trao code để nhận access token rồi lấy thuộc tính người dùng theo cơ chế OAuth2UserService.
- **OidcUserService** và **DefaultOAuth2UserService:** hỗ trợ tải/chuyển thông tin người dùng. Đây **không phải AuthenticationProvider**; không nhầm các service này với provider xác thực.

Khi client registration có scope **openid**, Spring Security sử dụng khả năng OIDC tương ứng. Nếu không có **openid**, OAuth 2.0 login thuần không cung cấp ID token và ngữ nghĩa xác thực tiêu chuẩn OIDC.

**Không cần tự viết AuthenticationProvider để thực hiện OIDC chuẩn**. Hãy dùng **oauth2Login()**, đăng ký đúng OP/issuer, client và redirect URI. Việc tự nhận JWT hoặc callback ở controller rất dễ bỏ qua xác minh signature, state, nonce, audience, issuer và các ràng buộc cần thiết.

### 4.3. Provider trong Resource Server

Với **oauth2ResourceServer().jwt()**:

1. **BearerTokenAuthenticationFilter** lấy Bearer token từ HTTP request và tạo **BearerTokenAuthenticationToken**.
2. Filter chuyển token cho AuthenticationManager được cấu hình.
3. **JwtAuthenticationProvider** dùng **JwtDecoder** để kiểm tra chữ ký, thuật toán cho phép, issuer, thời hạn và các JWT validator; ánh xạ quyền thành authorities.
4. Thành công sẽ trả **JwtAuthenticationToken**, principal thông thường là **Jwt**. Spring Security filter cập nhật SecurityContext.
5. Thất bại, filter xử lý lỗi xác thực và thường dùng Bearer AuthenticationEntryPoint để phát 401.

Nếu access token là **opaque** thì sử dụng cơ chế introspection/provider tương ứng thay vì JwtAuthenticationProvider.

**Sai lầm thường gặp:** API nhận bất kỳ ID token có chữ ký đúng như một Bearer access token. ID token dành cho **OIDC client/RP**, còn API phải kiểm tra access token **phát cho audience của API**, loại token theo profile triển khai, scope/quyền và issuer.

### 4.4. Khi nào cần AuthenticationProvider tùy biến?

Chỉ tự triển khai nếu ứng dụng cần **một loại credential khác** mà Spring Security chưa có hoặc cần tích hợp giao thức riêng đã được xác minh an toàn. Provider tùy biến phải ràng buộc đúng kiểu Authentication, xác minh nguồn/hiệu lực/replay/đích nhận, xử lý lỗi fail closed, trả kết quả không lộ bí mật. Nếu chỉ muốn:

- **đổi vai trò/authorities của OIDC user:** dùng **GrantedAuthoritiesMapper** hoặc một **OidcUserService** được ủy quyền cho mặc định;
- **giới hạn claim trong JWT access token:** cấu hình **JwtDecoder validators** và **JwtAuthenticationConverter**;
- **đổi đường dẫn login/response 401:** tùy chỉnh **AuthenticationEntryPoint** hoặc filter chain;
- **chặn tài khoản nội bộ sau SSO:** ánh xạ danh tính dựa trên **(issuer, subject)**, kiểm tra chính sách trong bước ánh xạ người dùng hoặc authorization.

Những việc đó **không bắt buộc** thay provider chuẩn. Việc đăng ký provider tự viết sai vị trí có thể làm hỏng OIDC login hoặc mở đường chấp nhận token giả.

## 5. AuthenticationEntryPoint: phản ứng khi chưa xác thực

### 5.1. Khi nào EntryPoint được gọi?

Sau khi chain xử lý, **ExceptionTranslationFilter** dịch các ngoại lệ bảo mật thích hợp thành phản hồi HTTP:

- **AuthenticationException**, hoặc truy cập bị từ chối khi request chưa được xác thực đầy đủ: bắt đầu xác thực bằng **AuthenticationEntryPoint**.
- **AccessDeniedException** đối với người dùng đã xác thực nhưng thiếu quyền: thường gọi **AccessDeniedHandler**, trả **403 Forbidden**, không khởi chạy SSO lại như một giải pháp phân quyền.
- Một số **authentication filter** tự bắt lỗi xác thực và gọi failure handler/entry point đã cấu hình. Ví dụ callback OIDC thất bại có thể đi tới login failure URL; không phải mọi lỗi đều xuất phát từ ExceptionTranslationFilter.

**EntryPoint không xác nhận mật khẩu, không gọi IdP thay mọi filter và không bảo đảm đăng nhập thành công.** Nó chỉ bắt đầu quá trình tương tác xác thực qua HTTP (redirect hoặc challenge).

### 5.2. LoginUrlAuthenticationEntryPoint cho browser

Ví dụ:

~~~java
new LoginUrlAuthenticationEntryPoint("/oauth2/authorization/company")
~~~

Khi browser chưa xác thực yêu cầu **/dashboard**, EntryPoint có thể trả **302 Location: /oauth2/authorization/company**. Request tiếp theo tới đường dẫn này được **OAuth2AuthorizationRequestRedirectFilter** xử lý để tạo **authorization request**, sau đó trả một **302 khác** tới OP/IdP.

Nói chính xác: **LoginUrlAuthenticationEntryPoint không tự xây authorization URL đầy đủ của OP**, nó hướng client đến endpoint mà Spring OAuth2 login dùng để bắt đầu flow.

Nếu ứng dụng có **nhiều IdP**, có thể chuyển đến trang chọn provider phù hợp hoặc dùng cơ chế chọn provider đã tin cậy; không chỉ nối tên miền IdP tùy ý theo input chưa xác minh.

### 5.3. BearerTokenAuthenticationEntryPoint cho REST API

Khi API chưa có token hoặc có token không hợp lệ, phản hồi điển hình:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Với token lỗi, challenge có thể thêm **error="invalid_token"** cùng tham số liên quan. Không trả về HTML login page hoặc 302 sang IdP cho API client tự động.

Nếu Bearer token **đã được xác thực** nhưng thiếu scope/quyền, API thường trả:

~~~http
HTTP/1.1 403 Forbidden
~~~

Resource server có thể kèm **WWW-Authenticate: Bearer error="insufficient_scope"** khi có ngữ cảnh quyền tương ứng. Chi tiết chính xác phụ thuộc Spring Security, handler và phiên bản.

### 5.4. Đừng đánh đồng AuthenticationEntryPoint với AuthenticationFailureHandler

| Tình huống | Bộ phận thường xử lý | Phản ứng thường gặp |
| --- | --- | --- |
| Người dùng ẩn danh vào trang web riêng tư | **ExceptionTranslationFilter → AuthenticationEntryPoint** | Redirect bắt đầu SSO |
| API thiếu Bearer | **Resource Server/EntryPoint** | 401 Bearer challenge |
| OP callback trả code sai/state không hợp lệ | **OAuth2LoginAuthenticationFilter + failure handler** | Thất bại đăng nhập, thường redirect **/login?error** |
| User có session nhưng thiếu role | **AccessDeniedHandler** | 403 |
| Token API signature/issuer/audience không hợp lệ | **BearerTokenAuthenticationFilter + authentication failure processing** | 401 |
| Xác thực thành công nhưng tenant không được cấp quyền | Authorization/policy hoặc kiểm tra user mapping | 403 hoặc thất bại login theo vị trí kiểm tra |

Đặt đúng trách nhiệm giúp tránh vòng lặp login và tránh chuyển lỗi phân quyền thành “hãy đăng nhập lại”.

## 6. Toàn bộ luồng SSO: từ request đến phiên đã đăng nhập

### Bước A – browser chưa có phiên truy cập /dashboard

1. **GET /dashboard** đi vào Servlet container → FilterChainProxy.
2. FilterChainProxy thử **apiChain** (matcher /api/**) → không khớp; sau đó chọn **webChain**.
3. **AuthorizationFilter** yêu cầu authenticated nhưng request chưa có phiên hợp lệ.
4. **ExceptionTranslationFilter** chuyển tình trạng này thành hành động bắt đầu xác thực.
5. **LoginUrlAuthenticationEntryPoint** trả 302 tới **/oauth2/authorization/company**.
6. **OAuth2AuthorizationRequestRedirectFilter** tạo authorization request với **state**, redirect URI, scope **openid** và các tham số cần thiết, đưa browser tới OP.
7. OP xác thực người dùng (hoặc tái sử dụng phiên SSO tại OP) và trả browser về callback đã đăng ký.

### Bước B – OP redirect về ứng dụng

8. Browser gọi **GET /login/oauth2/code/company?code=...&state=...**. Request đi qua webChain.
9. **OAuth2LoginAuthenticationFilter** nhận callback, lấy request đã lưu và kiểm tra các ràng buộc.
10. Filter gọi AuthenticationManager với **OAuth2LoginAuthenticationToken**.
11. **OidcAuthorizationCodeAuthenticationProvider** (trong cấu hình OIDC) xử lý code/token response, xác minh ID token và lấy thông tin OIDC cần thiết thông qua service phù hợp.
12. Khi thành công, SecurityContext được thiết lập/duy trì bằng cơ chế đăng nhập của Spring; thường có **HttpSession**/cookie cho browser. Success handler điều hướng browser về URL ban đầu nếu cấu hình request cache cho phép.
13. Truy cập trang được bảo vệ sử dụng **Authentication** đã có; việc phân quyền riêng vẫn có thể từ chối user thiếu role.

### Bước C – API nhận Bearer token

1. API client gọi **GET /api/reports** với **Authorization: Bearer ...**.
2. **apiChain** được chọn, **BearerTokenAuthenticationFilter** xử lý access token.
3. **JwtAuthenticationProvider** xác minh token và tạo **JwtAuthenticationToken** nếu thành công.
4. **AuthorizationFilter** yêu cầu authority **SCOPE_reports.read**.
5. Token đúng issuer/audience/chữ ký/thời gian và có scope phù hợp → xử lý request; nếu không → 401 hoặc 403 theo loại lỗi.

**Khác biệt:** Browser SSO thường duy trì phiên ứng dụng sau khi chứng thực với OP; API Bearer thường xác minh token **trên từng request** và không cần chuyển hướng/trình duyệt. Cùng một OP có thể cấp token cho cả hai, nhưng token của hai vai trò không được dùng lẫn.

## 7. Ví dụ Spring Boot 3.x: hai chain với EntryPoint khác nhau

Đây là **cấu hình Servlet/MVC cho Java 17+**, triển khai trong dự án Spring Boot 3.x có parent/BOM Maven. Các URL **example.org** là minh họa: bạn phải có một OP thật hỗ trợ discovery, đăng ký OIDC client và phát JWT access token cho audience của API trước khi thử luồng đăng nhập thực tế. Các mẫu class là mã hoàn chỉnh trong ngữ cảnh dự án Boot đã được cấu hình, không phải một chương trình Java độc lập chạy bằng javac thuần.

### 7.1. Dependencies

Thêm vào phần **dependencies** của pom.xml; phiên bản do Spring Boot parent/BOM quản lý:

~~~xml
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
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

### 7.2. Cấu hình client và JWT Resource Server

**src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid, profile, email
        provider:
          company:
            issuer-uri: https://login.example.org/realms/company
      resourceserver:
        jwt:
          issuer-uri: https://login.example.org/realms/company
          audiences:
            - urn:reports-api
~~~

**Giải thích:**

- **registration.company** định danh client OIDC theo **registrationId=company**; Spring tạo endpoint mặc định **/oauth2/authorization/company** và callback **/login/oauth2/code/company**.
- **scope: openid** bật ngữ nghĩa OIDC, từ đó RP xác minh ID token. **profile/email** chỉ yêu cầu thêm claim; không có nghĩa người dùng đương nhiên được cấp mọi quyền.
- **issuer-uri** chỉ định OP/Authorization Server tin cậy. Không lấy issuer tùy ý từ browser request hoặc JWT chưa xác minh để auto-add nhà phát hành.
- **resourceserver.jwt.audiences** buộc JWT API có audience **urn:reports-api**, ngăn ID token dành cho web client hoặc access token của API khác bị chấp nhận vì cùng issuer.
- **client-id** và **client-secret** phải từ registration thực tế, lưu bằng biến môi trường/secret manager; không commit secret.
- Cần đăng ký redirect URI chính xác ở OP: thường là **{baseUrl}/login/oauth2/code/company**; sau reverse proxy phải cấu hình đúng public base URL, scheme và forwarded headers qua proxy đáng tin.
- Việc có hai issuer-uri cùng URL minh họa **hai vai trò tin cậy khác nhau**: OIDC client xác minh ID token cho RP; resource server xác minh access token cho API.

**Authorization Code + PKCE:** bật PKCE theo loại client và khả năng OP; public client bắt buộc dùng PKCE và confidential client nên dùng PKCE theo khuyến nghị bảo mật hiện hành. Dùng HTTPS, giữ **state**/nonce phù hợp và không bỏ qua xác minh callback. Không tự chèn PKCE giả vào response handler.

### 7.3. SecurityConfig.java – cấu hình có thể dùng trong Boot

**src/main/java/com/example/sso/SecurityConfig.java**:

~~~java
package com.example.sso;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasAuthority("SCOPE_reports.read"))
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable);
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(
                    new LoginUrlAuthenticationEntryPoint(
                        "/oauth2/authorization/company")));
        return http.build();
    }
}
~~~

**Lưu ý về API chain:**

- Match **/api/** ưu tiên trước webChain nên API không tự chuyển sang SSO login.
- **oauth2ResourceServer().jwt()** gắn sẵn bộ filter và cơ chế provider để xử lý Bearer JWT; không cần tự viết **AuthenticationProvider**.
- Mặc định resource server cấu hình **BearerTokenAuthenticationEntryPoint** phù hợp cho API; không tùy tiện thay bằng LoginUrlAuthenticationEntryPoint.
- **hasAuthority("SCOPE_reports.read")** áp dụng ở tầng authorization sau khi token được xác thực. Spring mặc định có thể ánh xạ claim **scope/scp** thành authority có tiền tố **SCOPE_**.
- **STATELESS** tránh dùng HTTP session làm phương thức xác thực API. CSRF chỉ vô hiệu cho API trong ví dụ **vì API được thiết kế nhận Bearer token qua Authorization header**; nếu API cũng xác thực bằng cookie, phải xem lại bảo vệ CSRF.

**Lưu ý về web chain:**

- Web chain không gọi **securityMatcher**, vì cần bắt mọi request còn lại: trang web, endpoint bắt đầu OIDC và callback.
- **oauth2Login()** thêm những filter OAuth2/OIDC cần thiết. Mặc định nếu có nhiều IdP Spring có thể cung cấp trang chọn login; mẫu này cố ý redirect thẳng đến **company**.
- **exceptionHandling.authenticationEntryPoint** đổi phản hồi **khi chưa xác thực vào trang được bảo vệ** thành redirect bắt đầu OIDC; nó không tự chứng thực ID token hay đặt role.
- **anyRequest().authenticated()** có nghĩa chỉ cần xác thực cho web; bài toán role/permission nghiệp vụ cần chính sách riêng.
- **@Order(2)** đặt web chain sau API. Không gán matcher **/dashboard/** duy nhất khiến các endpoint OIDC nằm ngoài chain.

### 7.4. Main application và controller

**src/main/java/com/example/sso/SsoApplication.java**:

~~~java
package com.example.sso;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SsoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SsoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/sso/SsoController.java**:

~~~java
package com.example.sso;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SsoController {

    @GetMapping("/")
    public String home() {
        return "Public home page";
    }

    @GetMapping("/dashboard")
    public Map<String, String> dashboard(
            @AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getSubject()
        );
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports(
            @AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getClaimAsString("iss")
        );
    }
}
~~~

**Các response trên không có subject/issuer cố định**: chúng phụ thuộc OP và token thực tế. Đừng log ID token/access token hoặc trả thông tin nhạy cảm không cần thiết trong ứng dụng production. Phần API ví dụ dùng claim **sub**, nên OP phải đưa subject hợp lệ vào access token cho API; nếu API thực tế dùng client_credentials hoặc profile khác, thiết kế principal/response tương ứng.

### 7.5. Lệnh chạy và kết quả kỳ vọng

Trong dự án Spring Boot/Maven hợp lệ, thiết lập biến môi trường **OIDC_CLIENT_ID**, **OIDC_CLIENT_SECRET** và thay issuer bằng OP thực tế, sau đó chạy:

~~~bash
mvn spring-boot:run
~~~

Ví dụ thử resource public:

~~~bash
curl -i http://localhost:8080/
~~~

**Response body:**

~~~text
Public home page
~~~

Lệnh trên không yêu cầu OP vì endpoint **/** được cấu hình **permitAll**. Việc khởi động/khám phá metadata có thể phụ thuộc cấu hình và khả năng truy cập IdP; issuer minh họa không cho phép kiểm thử OIDC login thực.

Đối với **GET /dashboard** chưa có session, mong đợi chuỗi redirect:

~~~text
GET /dashboard
 -> 302 /oauth2/authorization/company
 -> 302 https://<issuer-thuc-te>/.../authorize?...
 -> xác thực tại OP
 -> GET /login/oauth2/code/company?code=...&state=...
 -> tạo phiên đăng nhập nếu ID token/flow hợp lệ
~~~

Đây là trình tự diễn giải, không phải chuỗi stdout HTTP tuyệt đối; redirect URI cuối, path login OP, headers và mã status có thể tùy triển khai.

Đối với API không gửi token:

~~~bash
curl -i http://localhost:8080/api/reports
~~~

**Phản hồi thường gặp:** **401 Unauthorized**, có header **WWW-Authenticate: Bearer**. API không nên trả 302 về login OP.

Khi có **access token thật** phát cho **urn:reports-api** với quyền **reports.read**, thử:

~~~bash
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:8080/api/reports
~~~

**YOUR_ACCESS_TOKEN** chỉ là ký hiệu trong tài liệu; muốn kiểm thử phải thay bằng token thật do OP được tin phát hành. Khi đúng, có thể nhận **200 OK** và JSON về issuer/subject; khi thiếu scope, thông thường **403 Forbidden**; token không hợp lệ thường **401 Unauthorized**.

## 8. Phân tích AuthenticationProvider cụ thể khi debug SSO

### 8.1. OIDC login qua code

~~~text
Callback: /login/oauth2/code/company?code=...&state=...
   |
OAuth2LoginAuthenticationFilter
   |
OAuth2LoginAuthenticationToken (chưa authenticated)
   |
AuthenticationManager / ProviderManager
   |
OidcAuthorizationCodeAuthenticationProvider
   |  - trao code lấy token tại token endpoint đúng OP
   |  - xác minh ID token: signature, issuer, audience, exp, nonce...
   |  - dùng OidcUserService khi cần dữ liệu user
   v
Authentication đã xác thực (principal OIDC)
   |
SecurityContext + phiên browser
~~~

Nếu cấu hình client không có **openid**, luồng xử lý **OAuth2LoginAuthenticationProvider** và user service tương ứng khác với ID token OIDC. Với bài toán SSO xác thực danh tính, nên dùng **OIDC** khi OP hỗ trợ.

### 8.2. Bearer JWT cho API

~~~text
GET /api/reports
Authorization: Bearer <access_token>
   |
BearerTokenAuthenticationFilter
   |
BearerTokenAuthenticationToken
   |
AuthenticationManager / ProviderManager
   |
JwtAuthenticationProvider
   |  - JwtDecoder kiểm tra signature/JWKS, exp, nbf, iss
   |  - audience validator kiểm tra urn:reports-api
   |  - JwtAuthenticationConverter ánh xạ scope/authorities
   v
JwtAuthenticationToken
   |
AuthorizationFilter kiểm tra SCOPE_reports.read
   |
Controller hoặc 403
~~~

Spring Security có thể đi qua **AuthenticationManagerResolver** để chọn manager cho từng request, nhất là khi cấu hình nhiều issuer. Không mặc định giả định mọi ứng dụng chỉ có một ProviderManager toàn cục.

### 8.3. Một ProviderManager có thể có nhiều provider

~~~text
ProviderManager
  - provider A: hỗ trợ OAuth2LoginAuthenticationToken theo OIDC
  - provider B: hỗ trợ OAuth2LoginAuthenticationToken cho OAuth2 login thường
  - provider C: xử lý loại Authentication khác nếu đã cấu hình
~~~

Danh sách là ví dụ khái niệm về cơ chế ủy quyền; không nên giả định **cả ba luôn nằm trong cùng một manager**. Tập provider thật có thể khác theo chain, cấu hình, phiên bản và loại credentials.

Đối với **supports()**, một provider không hỗ trợ kiểu đầu vào sẽ không xử lý yêu cầu. Nếu provider hỗ trợ nhưng xác minh thất bại, kết quả phụ thuộc exception/luật điều phối; không tự cho phép “fallback sang provider ít chặt hơn” để bỏ qua chữ ký hoặc sai issuer.

## 9. Tùy biến đúng chỗ: chọn cách ít rủi ro nhất

### 9.1. Cần giới hạn đối tượng đăng nhập web sau OIDC

Ví dụ tổ chức chỉ cho tài khoản đã liên kết nội bộ truy cập **/dashboard**. Có thể tùy biến **OidcUserService**, gọi service mặc định trước, sau đó ánh xạ tài khoản theo **(iss, sub)** và đưa ra quyết định theo policy. Đây là phần **post-authentication user mapping**, không thay thế ID token validation của provider.

Mã minh họa tích hợp (giả sử có dịch vụ nội bộ **AccountAccessService**):

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> oidcUserService(
        AccountAccessService accessService) {
    OidcUserService delegate = new OidcUserService();
    return request -> {
        OidcUser user = delegate.loadUser(request);
        String issuer = user.getIdToken().getClaimAsString("iss");
        String subject = user.getSubject();

        if (!accessService.isAllowed(issuer, subject)) {
            OAuth2Error error = new OAuth2Error("access_denied");
            throw new OAuth2AuthenticationException(
                error, "Account is not enabled for this application");
        }
        return user;
    };
}
~~~

Đây là **đoạn mở rộng, không phải class Java độc lập**. Các import cần thiết thuộc **org.springframework.security.oauth2.client.userinfo.OAuth2UserService**, **org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService**, **org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest**, **org.springframework.security.oauth2.core.oidc.user.OidcUser**, **org.springframework.security.oauth2.core.OAuth2Error**, **org.springframework.security.oauth2.core.OAuth2AuthenticationException**. **AccountAccessService** là abstraction nghiệp vụ do ứng dụng định nghĩa.

Gắn đoạn trên vào DSL web chain nếu chủ động sử dụng:

~~~java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(oidcUserService)))
~~~

Đoạn này thay **.oauth2Login(Customizer.withDefaults())** tại webChain, với biến hoặc bean **oidcUserService** đúng kiểu. Phương thức **isAllowed(issuer, subject)** phải truy vấn chính sách nội bộ tin cậy, không dựa duy nhất vào email domain hoặc client-supplied header. Không viết custom AuthenticationProvider chỉ để làm việc này.

### 9.2. Cần phân quyền JWT theo claim riêng

Dùng **JwtAuthenticationConverter** để ánh xạ claim đáng tin cậy thành authorities và **JwtDecoder/OAuth2TokenValidator** để kiểm tra issuer/audience/time. Converter không được tạo quyền admin chỉ vì một claim chưa được AS định nghĩa rõ. Với OIDC ID token, dùng user-identity mapping/authorities ở web chain thay vì nhận ID token như JWT resource server.

### 9.3. Cần response 401 JSON cho API

Nếu muốn luôn trả JSON trong môi trường REST, có thể cấu hình custom **AuthenticationEntryPoint** cho API, nhưng cần giữ semantics **401** và **WWW-Authenticate: Bearer** phù hợp RFC 6750. Thường default **BearerTokenAuthenticationEntryPoint** đã đủ tốt; đổi response không thay đổi logic kiểm tra token.

### 9.4. Cần nhiều OP/IdP

Tạo client registrations cố định cho các OP được duyệt, chọn provider theo request đã được ràng buộc, chống authorization-server mix-up; không tự phát sinh issuer hoặc JWKS URL từ URL query chưa được xác minh. API nhiều issuer có thể dùng **JwtIssuerAuthenticationManagerResolver** với allowlist issuer được duyệt và policy audience tương ứng; không mở trust động chỉ bằng claim **iss** của JWT chưa kiểm tra.

## 10. Lỗi thường gặp và cách tìm nguyên nhân

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| **/dashboard** trả 401 thay vì redirect | EntryPoint sai, request vào API chain hoặc không bật oauth2Login | Kiểm tra matcher, @Order, exceptionHandling trong webChain |
| **/api/reports** trả 302 tới IdP | Request API bị webChain nhận, hoặc API dùng login EntryPoint | Đặt API chain trước, dùng securityMatcher("/api/**"), bật resource server |
| Bắt đầu login được nhưng callback 404/401 | **/login/oauth2/code/company** không thuộc webChain, redirect URI không khớp, missing oauth2Login filter | Kiểm tra registrationId, callback matcher, redirect URI tại OP và reverse proxy |
| “No AuthenticationProvider found” | ProviderManager không có provider hỗ trợ Authentication đầu vào | Kiểm tra loại token và DSL đã bật; đừng đăng ký provider sai chain |
| Login OIDC thất bại khi đổi issuer | issuer/client/nonce/audience/chữ ký của ID token không phù hợp | Đọc log lỗi đã được làm sạch, metadata OP, cấu hình client registration |
| API báo invalid_token | JWT sai chữ ký, issuer, audience, thời gian hoặc decoder | Kiểm tra issuer-uri, audiences, JWKS, đồng hồ và token thực sự dành cho API |
| API trả 403 dù token hợp lệ | Thiếu authority **SCOPE_reports.read** hoặc bị policy nội bộ từ chối | Kiểm tra claim scope, converter và authorizeHttpRequests |
| User đăng nhập được nhưng role nội bộ không đúng | Chưa ánh xạ quyền từ danh tính OIDC, dùng claim không nhất quán | Ánh xạ **(iss, sub)** sang tài khoản/permission tại ứng dụng |
| Callback bị vòng lặp 302 | Session/cookie, SameSite, reverse-proxy scheme/host, redirect URI, request cache hoặc state không nhất quán | So sánh request/response và domain cookie; xác minh proxy/trust |
| API tự động có session sau khi gửi JWT | Chain API chưa thực sự stateless hoặc request bị webChain match | Kiểm tra @Order, securityMatcher, SessionCreationPolicy |
| Custom filter không được gọi | Đăng ký vào chain khác hoặc request không match | Xem danh sách filter thực tế, matchers và thứ tự |
| Exception có AuthenticationException nhưng không đi vào EntryPoint như mong đợi | Filter bắt lỗi bằng failure handler riêng | Xác định filter ném/catch ngoại lệ, kiểm tra OAuth2LoginAuthenticationFilter hoặc BearerTokenAuthenticationFilter |

### Debug có kiểm soát

Chỉ khi phát triển, có thể tạm bật:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Quan sát thông tin **chain nào được chọn**, filter nào được cấu hình, lỗi issuer/audience/callback, kết quả 401/403. Trong production cần kiểm soát log, tuyệt đối không ghi access token, ID token, authorization code, client secret, cookie/session ID hoặc thông tin nhạy cảm.

**Thứ tự tìm lỗi hiệu quả:** kiểm tra **URL → chain được chọn → filter áp dụng → AuthenticationProvider/token validation → authorities → EntryPoint/AccessDeniedHandler/failure handler**. Phân tách đúng tầng giúp tránh sửa sai chỗ.

## 11. Tình huống thực hành và lời giải

### Tình huống 1 – Nhầm chain

Ứng dụng đặt webChain **@Order(1)** không có securityMatcher, còn apiChain **@Order(2)** với /api/**. API thiếu token bị 302 sang OP.

**Giải thích:** webChain mặc định match tất cả request và được chọn đầu tiên; apiChain không nhận lượt. **Sửa:** đặt apiChain **@Order(1)**, webChain sau đó. Không cần custom AuthenticationProvider.

### Tình huống 2 – Người dùng chưa xác thực vào trang cá nhân

Browser gọi **GET /dashboard** không có phiên, webChain bắt request.

**Đúng:** AuthorizationFilter yêu cầu xác thực; ExceptionTranslationFilter/EntryPoint trả redirect đến endpoint bắt đầu OIDC; OAuth2AuthorizationRequestRedirectFilter mới tạo request tới OP. **Không gọi trực tiếp JwtAuthenticationProvider** để login browser.

### Tình huống 3 – Người dùng đã đăng nhập nhưng thiếu ROLE_ADMIN

Browser có OIDC session hợp lệ, truy cập **/admin** yêu cầu vai trò quản trị.

**Đúng:** authorization kiểm tra authorities và trả **403**/AccessDeniedHandler nếu thiếu quyền. **Không cần gọi OP lại** vì xác thực và phân quyền là hai bước khác nhau.

### Tình huống 4 – API thiếu Bearer token

Một automation gọi **GET /api/reports** không mang Authorization header.

**Đúng:** trả **401** và Bearer challenge để client bổ sung token. Chuyển API client sang trang web login bằng 302 là sai trải nghiệm và có thể làm hỏng giao thức client.

### Tình huống 5 – Cùng một OP nhưng audience khác

Web RP nhận OIDC ID token **aud=company-web**. Client đưa token này gọi API yêu cầu **aud=urn:reports-api**.

**Đúng:** API từ chối token; JWT có chữ ký hợp lệ chưa đủ. Cần access token đúng audience API, scope, loại token/claim theo profile và issuer đáng tin.

### Tình huống 6 – Tự viết AuthenticationProvider để “đọc payload”

Developer viết provider chỉ tách JWT và lấy **sub**, không xác minh chữ ký.

**Sai nghiêm trọng:** attacker có thể tạo payload giả. **Đúng:** dùng JwtAuthenticationProvider/JwtDecoder được cấu hình đúng issuer, JWKS, aud và validators; không tự parse credential rồi đặt authenticated=true.

### Tình huống 7 – Thêm provider địa phương có làm SSO an toàn hơn?

Một nhóm muốn thêm **DaoAuthenticationProvider** chỉ để có thể lấy role tài khoản nội bộ sau khi OIDC login.

**Không cần:** DaoAuthenticationProvider dành cho xác thực username/password, không phải truy vấn quyền OIDC user. Sử dụng user mapping/authorities hoặc policy service sau khi OIDC ID token được xác minh.

### Tình huống 8 – Có nhiều IdP cùng login

Ứng dụng hỗ trợ OP công ty và OP đối tác.

**Đúng:** cấu hình **hai client registrations đã duyệt**, gắn request và callback với provider đã chọn; xác minh issuer, audience, nonce, state và xử lý mix-up. **Không** chấp nhận URL issuer bất kỳ từ query parameter.

## 12. Checklist thiết kế SSO trước khi đưa vào production

- [ ] Mỗi kiểu request dùng đúng **SecurityFilterChain**; thứ tự @Order và securityMatcher được kiểm tra.
- [ ] Web login endpoint **/oauth2/authorization/{registrationId}** và callback **/login/oauth2/code/{registrationId}** được chain có **oauth2Login()** xử lý.
- [ ] API Bearer token dùng resource server chain và response **401**; browser unauthenticated dùng EntryPoint redirect vào login.
- [ ] **AuthenticationProvider** chuẩn được dùng cho OIDC/OAuth2/JWT phù hợp; không tự viết token parser hay bỏ xác minh.
- [ ] OIDC client registration khai báo **openid**, issuer đáng tin, client_id, redirect URI exact; có cơ chế bảo vệ state/PKCE/nonce và TLS.
- [ ] ID token xác minh signature, issuer, audience của RP, thời hạn; access token API xác minh signature/introspection, issuer, audience API, hạn và scope/quyền.
- [ ] **AuthenticationEntryPoint** khác **AccessDeniedHandler** và login **AuthenticationFailureHandler**; không biến 403 thành bắt login vô hạn.
- [ ] Browser session và API stateless được thiết kế rõ; cookie, CSRF, logout và session expiration theo đặc tính từng kênh.
- [ ] Người dùng SSO được liên kết bằng **(issuer, subject)**, phân quyền nội bộ dựa trên policy tin cậy.
- [ ] Đã thử các trường hợp **không token, token sai, session thiếu quyền, callback lỗi, audience sai, IdP unavailable, proxy/cookie issue**.
- [ ] Log vừa đủ để truy tìm **chain/filter/provider/entrypoint**, không lộ token/secret/cookie.

**Kết luận ghi nhớ:** **SecurityFilterChain quyết định request đi qua cơ chế bảo mật nào; AuthenticationProvider xác minh credential của cơ chế đó; AuthenticationEntryPoint khởi động quá trình xác thực khi request chưa được xác thực.** Với SSO web, kết quả thường là **redirect + OIDC ID token + phiên browser**; với API, thường là **Bearer access token + 401/403**, không redirect.

## 13. Nguồn chuẩn để đọc thêm

- [Spring Security 6.5 – Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): FilterChainProxy, filter chain, exception handling.
- [Spring Security 6.5 – Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): nhiều SecurityFilterChain, @Order, securityMatcher và requestMatchers.
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): ProviderManager, AuthenticationProvider, AuthenticationEntryPoint và SecurityContext.
- [Spring Security – OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/core.html): registration, authorization endpoint, callback và OIDC scope.
- [Spring Security – OAuth 2.0 Login Advanced](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): ánh xạ authorities và OidcUserService.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JwtAuthenticationProvider, JwtDecoder, issuer và audience.
- [Spring Boot – OAuth2](https://docs.spring.io/spring-boot/reference/security/oauth2.html): cấu hình client, resource server và redirect URL.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token và quy tắc xác minh danh tính.
- [RFC 9700 – OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): PKCE, CSRF, bảo vệ redirect và các khuyến nghị an toàn.
