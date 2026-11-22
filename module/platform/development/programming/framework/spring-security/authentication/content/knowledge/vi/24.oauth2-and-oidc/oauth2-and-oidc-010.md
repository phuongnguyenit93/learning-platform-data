# Đăng xuất cục bộ, đăng xuất OIDC và ranh giới với vòng đời token

## 1. Mục tiêu và bối cảnh

Trong ứng dụng Spring Security có đăng nhập qua OpenID Connect (OIDC), nút **Đăng xuất** nghe có vẻ là một hành động duy nhất. Thực tế, ứng dụng có thể giữ một phiên đăng nhập (session) riêng, nhà cung cấp danh tính (OpenID Provider, **OP**) giữ phiên SSO riêng, còn hệ thống OAuth 2.0 phát hành các token có thời gian sống và chính sách thu hồi độc lập. Vì vậy, đóng phiên ở một nơi không tự bảo đảm rằng mọi nơi còn lại đã mất quyền truy cập.

Sau bài này, bạn cần thực hiện được:

1. Phân biệt **local logout tại Relying Party (RP)**, **RP-Initiated Logout tại OP**, **OP-Initiated Back-Channel/Front-Channel Logout** và **OAuth 2.0 token revocation**.
2. Giải thích chính xác ảnh hưởng của từng thao tác tới session của RP, cookie của trình duyệt, phiên SSO tại OP, ID token, access token và refresh token.
3. Cấu hình local logout và OIDC RP-Initiated Logout bằng Spring Security Servlet; nhận biết API tương ứng cho Spring WebFlux.
4. Hiểu cách một logout token đã được OP ký kích hoạt back-channel logout của RP, vì sao cần kiểm tra `iss`, `aud`, `events`, `sid`/`sub` và vì sao callback không được tin chỉ vì “đến từ URL quen”.
5. Đưa ra chính sách rõ ràng với access/refresh tokens khi logout, thay vì mặc định token sẽ hết hiệu lực ngay sau khi xóa cookie.
6. Kiểm thử các tình huống liên quan SSO, đa thiết bị, JWT đã cấp, refresh token, CSRF, gateway/reverse proxy và session store nhiều node.

**Phạm vi:** Spring Security + OAuth 2.0/OIDC. Phần demo Servlet dùng Spring Boot 3.x và Java 17+. Phần WebFlux là cấu hình reactive riêng; không sử dụng lẫn `HttpSecurity` với `ServerHttpSecurity`. Thực hành logout OIDC cần một OP thật hỗ trợ OIDC Discovery và logout endpoint; URL mẫu trong bài cần được thay bằng cấu hình của OP thử nghiệm.

## 2. Năm loại trạng thái phải phân biệt

Hãy xét một người đăng nhập vào ứng dụng quản lý công việc `https://tasks.example.org` thông qua OP `https://id.example.org`. Trình duyệt hiện có session cookie của cả hai bên. RP có thể giữ OAuth 2.0 authorized client để gọi API; API có thể kiểm tra access token theo nhiều cách.

| Thành phần | Ai sở hữu / kiểm soát? | Công dụng | Logout tại RP có tự xóa không? |
| --- | --- | --- | --- |
| **RP local session** (ví dụ `JSESSIONID` ở Servlet, `WebSession` ở WebFlux) | Ứng dụng RP và session store của RP | Ghi nhớ `SecurityContext`, dữ liệu HTTP session, trạng thái đã đăng nhập ở ứng dụng | **Có**, nếu logout handler/session invalidation được cấu hình đúng |
| **OP SSO session** (thường có cookie miền OP) | OP | Cho phép SSO giữa nhiều RP mà không nhập lại credential | **Không**; cần giao thức đăng xuất được OP hỗ trợ |
| **ID token** (OIDC) | OP ký/phát hành; RP tiêu thụ | Chứng minh sự kiện xác thực và các claims cho RP; có thể dùng làm `id_token_hint` | Không thể “xóa token đã phát hành” chỉ bằng hủy local session; token không phải access token API |
| **Access token** (OAuth 2.0) | Authorization Server (AS) phát hành; Resource Server (RS) kiểm tra | Ủy quyền truy cập API trong phạm vi `aud`/`scope`/quyền | **Không mặc định**; token đã phát hành có thể còn hiệu lực đến khi hết hạn hoặc bị vô hiệu hóa theo cơ chế RS/AS |
| **Refresh token** (OAuth 2.0) | AS quản lý và RP/native app lưu giữ theo kiến trúc | Xin access token mới mà không cần người dùng nhập lại thông tin | **Không mặc định**; việc xóa token khỏi storage và việc AS thu hồi token là hai hành động khác nhau |

Một số ứng dụng không giữ session server-side, chẳng hạn API chỉ xác thực Bearer JWT hoặc SPA lưu token ở phía client. Khi đó “local logout” có thể chỉ là xóa trạng thái/token khỏi client và **không có HTTP session để hủy**. Cần mô tả rõ kiến trúc trước khi hứa hẹn hiệu quả của một nút logout.

### Khác biệt giữa RP, OP, AS và RS

- **RP (Relying Party)**: ứng dụng dùng OIDC để xác thực người dùng; Spring Security `oauth2Login()` hoạt động ở đây.
- **OP (OpenID Provider)**: xác thực người dùng và phát hành ID token; OP thường đồng thời đóng vai trò Authorization Server của OAuth 2.0.
- **AS (Authorization Server)**: phát hành access/refresh token, có thể cung cấp revocation/introspection endpoints.
- **RS (Resource Server)**: API nhận Bearer access token, xác minh token và quyết định quyền truy cập.
- **Client registration**: thông tin RP đã đăng ký ở OP, bao gồm `client_id`, redirect URI và có thể `post_logout_redirect_uri`.

Một hệ thống có thể kiêm nhiều vai trò, nhưng **không vì thế mà các hợp đồng vòng đời token/session trở thành một**.

## 3. Bốn thao tác có tên “logout” nhưng hậu quả khác nhau

| Thao tác | Ai khởi xướng? | Đường giao tiếp | Kết quả chủ yếu | Không bảo đảm |
| --- | --- | --- | --- | --- |
| **Local logout** | Người dùng tại RP | Browser → RP `POST /logout` | RP xóa security context và hủy session theo cấu hình | OP SSO session chấm dứt; token đã cấp bị revoke |
| **RP-Initiated OIDC Logout** | RP sau yêu cầu của người dùng | Browser → OP `end_session_endpoint`, có thể quay lại RP | OP được yêu cầu kết thúc phiên SSO; RP nên đã xử lý local logout | OP luôn chấp nhận/hoàn tất; tất cả client và token lập tức vô hiệu |
| **OP-Initiated Front-Channel Logout** | OP | OP → browser → từng RP | RP nhận tín hiệu logout thông qua user agent | Mọi RP đều nhận tín hiệu (trình duyệt có thể chặn third-party cookie/iframe) |
| **OP-Initiated Back-Channel Logout** | OP | Server-to-server `POST` gửi logout token | RP xác minh thông điệp và hủy phiên tương ứng | Access JWT tại RS hết hiệu lực ngay |
| **OAuth Token Revocation (RFC 7009)** | OAuth client/đơn vị có thẩm quyền | Client → AS revocation endpoint | AS thu hồi token/grant theo quy tắc của mình | RS xác minh JWT offline thấy việc thu hồi ngay |

Một thao tác logout theo nghiệp vụ có thể **phối hợp** nhiều hàng ở bảng trên: ví dụ RP xóa local session, chuyển người dùng đến OP để kết thúc SSO, rồi backend chủ động yêu cầu revocation đối với refresh token còn nằm trong hệ thống. Tuy nhiên, không có một lệnh `logout()` của Spring Security tự động thực hiện toàn bộ các bước đó cho mọi kiến trúc.

### Ví dụ trực quan về hậu quả

Giả sử trước khi logout:

```text
Trình duyệt:
  [RP session đang hoạt động] [OP SSO session đang hoạt động]

RP/backend:
  [access token A, còn 5 phút] [refresh token R]

Resource server:
  [chấp nhận access token A nếu chữ ký/iss/aud/exp hợp lệ]
```

Nếu người dùng chỉ logout RP:

```text
RP session:           ĐÃ XÓA
OP SSO session:       CÓ THỂ VẪN CÒN
Access token A:       CÓ THỂ VẪN DÙNG ĐƯỢC đến exp
Refresh token R:      TÙY policy lưu trữ/thu hồi; không tự coi đã revoke
```

Nếu người dùng nhấn “Sign in with OIDC” ngay sau đó, OP có thể còn phiên SSO và cấp authorization code mới mà không hỏi lại mật khẩu. **Điều này không chứng minh local logout thất bại**; nó phản ánh OP session vẫn còn.

Ngược lại, nếu đã logout OP nhưng access JWT được một RS kiểm tra offline và còn hạn, RS vẫn có thể chấp nhận JWT đó tới khi hết hạn nếu không triển khai trạng thái thu hồi. **Điều này không chứng minh OIDC logout chưa diễn ra**; logout phiên và kiểm tra token là hai hợp đồng khác nhau.

## 4. Local logout trong Spring Security: chính xác xóa cái gì?

### 4.1. Servlet / Spring MVC

Spring Security có endpoint `/logout` mặc định khi bật Security filter chain. Với CSRF protection mặc định:

- `GET /logout` thường là trang xác nhận đăng xuất; nó **không phải** cách khuyến nghị để làm thay đổi session.
- `POST /logout` với CSRF token hợp lệ sẽ chạy các `LogoutHandler` được cấu hình. Mặc định thường bao gồm hủy `HttpSession`, xóa `SecurityContext`, xử lý remember-me/CSRF token và phát sự kiện logout theo những tính năng đã bật.
- Sau khi local logout thành công, `LogoutSuccessHandler` quyết định redirect hoặc response. Redirect tới OP là bước **bổ sung** khi triển khai OIDC RP-Initiated Logout.

```text
Browser POST /logout (+ CSRF token)
        |
        v
Spring Security LogoutFilter
        |
        +--> local LogoutHandler(s)
        |      - invalidate HttpSession
        |      - clear SecurityContext
        |      - cleanup liên quan theo cấu hình
        |
        +--> LogoutSuccessHandler
               - local redirect, HOẶC
               - chuyển tới OIDC OP end_session_endpoint
```

**Đừng xóa thủ công một cookie rồi kết luận đã logout.** Xóa cookie ở browser có thể bỏ định danh phiên phía client, nhưng server-side session và các bản ghi liên kết vẫn còn cho tới khi được invalidated/expired. Ngược lại, hủy session server-side là ranh giới bảo mật thực tế dù trình duyệt có thể giữ một cookie cũ không còn hợp lệ.

Trình duyệt phải gửi request logout theo đúng CSRF policy; tránh chuyển `POST /logout` thành GET để dễ gắn với một thẻ liên kết. Attacker có thể lợi dụng logout CSRF để làm người dùng bị logout ngoài ý muốn. Nếu ứng dụng dùng Thymeleaf/Spring MVC và form rendering được Spring Security tích hợp, mẫu nút logout có thể là:

```html
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất</button>
</form>
```

Đây là **mẫu template Thymeleaf**, không phải HTML tĩnh: cơ chế xử lý form phải phát hành CSRF token tương ứng. Nếu frontend tự xây dựng form hoặc request, hãy gửi token trong field/header theo `CsrfTokenRepository` được cấu hình. Không tắt CSRF toàn ứng dụng chỉ để nút logout hoạt động.

### 4.2. WebFlux / Spring Security Reactive

Ở WebFlux, Spring Security dùng `LogoutWebFilter`, `ServerLogoutHandler`, `ServerLogoutSuccessHandler` và `ServerSecurityContextRepository`. Không dùng `SecurityContextLogoutHandler` của Servlet cho reactive.

Trong các bản Spring Security, local logout reactive xóa các dữ liệu bảo mật qua handler mặc định, nhưng nếu yêu cầu **hủy toàn bộ WebSession**, cần kiểm tra và cấu hình `WebSessionServerLogoutHandler` rõ ràng cho phiên bản sử dụng. Ví dụ cấu hình ở phần 7 phối hợp `SecurityContextServerLogoutHandler` và `WebSessionServerLogoutHandler`. Đừng giả định chỉ gọi một API có tên giống Servlet sẽ có cùng tác động lên session store.

### 4.3. Local logout có xóa OAuth2 authorized client không?

Một RP dùng `oauth2Login` có thể lưu authorized client (access/refresh token) qua `OAuth2AuthorizedClientService` hoặc `OAuth2AuthorizedClientRepository`, tùy cấu hình (session, JDBC, repository riêng, v.v.). Khi session bị hủy, token lưu **chỉ trong session đó** có thể trở nên không còn truy cập được từ RP. Nếu token nằm trong database/Redis hoặc một storage chung, cần đánh giá liệu bản ghi authorized client có phải bị xóa sau logout không.

Hai khái niệm phải phân biệt:

1. **Local removal**: ứng dụng xóa bản sao token hoặc bản ghi authorized client khỏi storage; token đã phát hành ở AS không nhất thiết bị thu hồi.
2. **Revocation ở AS**: ứng dụng gọi đúng endpoint/protocol của AS để yêu cầu token không còn hợp lệ; RS có thể cần cơ chế xác minh phù hợp mới nhận ra điều đó.

Một custom `LogoutHandler` có thể xử lý cleanup mà ứng dụng sở hữu, nhưng không được coi việc xóa local record là lời gọi revocation. Việc đặt cleanup trước hoặc sau OP logout cần cân nhắc **dữ liệu cần thiết để gọi revocation hoặc cung cấp `id_token_hint`**; đừng xóa thông tin cần thiết rồi mới phát hiện thiếu để hoàn tất quy trình.

## 5. OIDC RP-Initiated Logout: yêu cầu OP kết thúc phiên SSO

OIDC [RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) định nghĩa cách RP yêu cầu OP logout người dùng. Đây là một **giao thức điều phối phiên**, không phải OAuth token revocation.

### 5.1. Luồng chính

```text
User              Browser                  RP (Spring Security)            OP
 | Click Logout      |                                |                       |
 |------------------>|  POST /logout + CSRF          |                       |
 |                   |------------------------------->|                       |
 |                   |     Local session invalidated  |                       |
 |                   |<------- 302 redirect ----------|                       |
 |                   |       tới end_session_endpoint                         |
 |                   |------------------------------------------------------->|
 |                   |                                  OP kiểm tra yêu cầu   |
 |                   |                                  và kết thúc OP session|
 |                   |<--------------- redirect về registered URI -----------|
 |                   |------------------------------->| /signed-out           |
 |                   |<------------- response ---------|                       |
```

Trong thực tế OP có thể cần người dùng xác nhận, có thể không hỗ trợ protocol logout, hoặc lỗi kết nối/trình duyệt ngắt trước khi quay lại RP. Do đó RP nên thiết kế rõ hậu quả của **local logout đã xảy ra** ngay cả khi OP logout không hoàn tất.

### 5.2. Discovery và các tham số chuẩn

RP thường tìm URL OP logout ở `end_session_endpoint` trong OIDC Discovery metadata, nếu OP hỗ trợ. Các tham số quan trọng:

| Tham số | Vai trò | Lưu ý |
| --- | --- | --- |
| `id_token_hint` | ID token OP đã phát hành cho RP, **được khuyến nghị** để giúp OP nhận diện phiên và client | Không phải access token hoặc refresh token; tránh log toàn bộ giá trị |
| `post_logout_redirect_uri` | Nơi OP chuyển browser về sau xử lý logout | Phải trùng URI đã đăng ký với OP; không lấy redirect tùy ý từ query của client |
| `state` | Giá trị opaque RP dùng đối chiếu response/redirect và duy trì tính nhất quán của flow | Sinh/kiểm tra theo thiết kế ứng dụng; không dùng làm credential |
| `client_id` | Có thể dùng để nhận diện client trong trường hợp chuẩn cho phép | OP phải kiểm tra client tương ứng với `id_token_hint` nếu có cả hai |
| `logout_hint` | Gợi ý danh tính hoặc phiên cho OP, tùy provider | Không mặc nhiên được mọi OP chấp nhận |

Ví dụ **đường dẫn minh họa** (đã bỏ giá trị token thực):

```text
GET https://id.example.org/connect/endsession
    ?id_token_hint=(ID token da duoc phat hanh)
    &post_logout_redirect_uri=https%3A%2F%2Ftasks.example.org%2Fsigned-out
    &state=(gia tri opaque)
```

Không tự xây URL bằng cách nối chuỗi một cách thiếu kiểm soát hoặc gửi token qua URL tùy ý. Handler chuẩn của Spring Security dùng `ClientRegistration` và metadata đã cấu hình để dựng redirect. Redirect endpoint và scheme nên dùng HTTPS ở production; tên host ngoài reverse proxy phải đúng với URI đăng ký.

**Đăng xuất OP không đồng nghĩa global logout mọi RP.** Một OP có thể hỗ trợ truyền thông báo đến các RP khác bằng front-channel/back-channel/session management, hoặc chỉ kết thúc OP session. Độ phủ phụ thuộc tính năng OP, registration, browser và implementation của từng RP.

### 5.3. Thứ tự local logout và OIDC logout

OIDC spec cho phép RP quyết định có xóa local session trước khi redirect sang OP hay đợi OP gửi logout notification. Trong Spring Security, `OidcClientInitiatedLogoutSuccessHandler` (Servlet) và `OidcClientInitiatedServerLogoutSuccessHandler` (WebFlux) là **success handler của local logout**, nên được gọi sau local logout handler. Đó là lý do cấu hình đúng nằm ở `logout(...logoutSuccessHandler(...))`, không phải tự đặt logic redirect trong controller rồi bỏ qua logout filter.

Nếu OP không có `end_session_endpoint`/provider không hỗ trợ RP-Initiated Logout, cần thiết kế **local logout fallback** phù hợp. Không hứa hẹn redirect OP thành công trong mọi môi trường.

### 5.4. Frontend phải thực sự điều hướng top-level browser

Nếu frontend dùng `fetch("/logout", {method: "POST", ...})`, HTTP client của JavaScript thường xử lý redirect trong request nền; **trình duyệt không tự chuyển trang top-level** tới OP. Với RP-Initiated Logout dựa trên redirect, nút logout nên dùng navigation/form POST ở top-level, hoặc một giải pháp frontend có kiểm soát để browser thực sự đi qua OP logout.

Đừng tạo logout URL chứa token rồi trả JSON cho client để client tự log/debug/sao chép. Tránh làm lộ `id_token_hint` trong analytics, referrer, server logs và error pages.

## 6. Ví dụ Spring Boot Servlet hoàn chỉnh: local + OIDC RP-Initiated Logout

Ví dụ này sử dụng **Spring Boot 3.x + Spring Security 6.x + Java 17+**, theo mô hình browser/web app với server-side session. Cần một OP thật và client registration được đăng ký đúng; domain `id.example.org` chỉ là minh họa và không phải endpoint dùng được ngay. Các lớp Java dưới đây compile trong một project có các starter thích hợp.

### 6.1. Dependency cho dự án Gradle Spring Boot đã tạo

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

Không trộn `spring-boot-starter-web` và `spring-boot-starter-webflux` chỉ để dùng chung snippet; chọn đúng servlet/reactive stack theo kiến trúc ứng dụng.

### 6.2. Cấu hình provider (thay bằng thông tin thật)

Đặt ở `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: web-application
            client-secret: "${OIDC_CLIENT_SECRET}"
            scope: openid,profile,email
        provider:
          corp:
            issuer-uri: "${OIDC_ISSUER_URI}"
```

Cung cấp biến môi trường `OIDC_CLIENT_SECRET` và `OIDC_ISSUER_URI` thực tế, không commit client secret. OP phải expose Discovery metadata cho issuer và, nếu muốn RP-Initiated Logout, phải có `end_session_endpoint` thích hợp. Ở OP, đăng ký ít nhất:

- Login redirect URI: `https://tasks.example.org/login/oauth2/code/corp`.
- Post-logout redirect URI: `https://tasks.example.org/signed-out`.

Tên `corp` là registration ID, nhất quán trong config/URL. Với môi trường local, có thể dùng `http://localhost:8080` và redirect URI chính xác nếu OP cho phép. URI đăng ký login và post-logout là **hai URI khác chức năng**, không dùng lẫn.

### 6.3. Java 17: security chain và controller

Lưu thành `src/main/java/demo/logout/OidcLogoutDemoApplication.java`:

```java
package demo.logout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OidcLogoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcLogoutDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            ClientRegistrationRepository registrations) throws Exception {

        OidcClientInitiatedLogoutSuccessHandler oidcLogout =
                new OidcClientInitiatedLogoutSuccessHandler(registrations);

        // Phải trùng post-logout redirect URI đã đăng ký tại OP.
        oidcLogout.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/signed-out", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutSuccessHandler(oidcLogout));

        // Giữ nguyên CSRF protection mặc định.
        return http.build();
    }

    @RestController
    static class Pages {

        @GetMapping("/")
        String home() {
            return "Home. Open /me to log in, then GET /logout to see "
                    + "the logout confirmation form.";
        }

        @GetMapping("/me")
        String me(@AuthenticationPrincipal OidcUser user) {
            return "OIDC subject: " + user.getSubject();
        }

        @GetMapping("/signed-out")
        String signedOut() {
            return "Returned from logout flow.";
        }
    }
}
```

Đoạn mã **không tự định nghĩa `/logout`** vì Spring Security đã có logout endpoint/filter. Nếu cố làm thêm controller `@PostMapping("/logout")` mà không hiểu filter chain, rất dễ bỏ qua local cleanup/CSRF. Code không tự revoke access/refresh tokens.

### 6.4. Chạy và quan sát đúng kết quả

Từ project đã có Spring Boot Gradle plugin và Java 17+, chạy:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Trình duyệt truy cập `http://localhost:8080/me` (hoặc URL đã cấu hình), thực hiện OIDC login. Sau khi đăng nhập:

1. Mở `GET /logout` để thấy confirmation page được Spring Security tạo, hoặc submit form POST hợp lệ có CSRF token.
2. Quan sát HTTP request `POST /logout` đến RP. Spring Security hủy local session theo cấu hình.
3. Quan sát redirect tới OP `end_session_endpoint`. Nếu OP hỗ trợ và nhận đúng ID token/redirect URI, OP xử lý SSO logout.
4. OP có thể redirect về `/signed-out`. Endpoint này chỉ hiển thị thông báo điều hướng; **không tự chứng minh** mọi token và mọi RP khác đã bị vô hiệu.
5. Quay lại `/me`: phải cần OIDC login mới ở RP. Việc OP có yêu cầu nhập lại mật khẩu hay không phụ thuộc session/SSO policy tại OP.

Không có stdout cố định từ ví dụ OIDC thật vì `sub`, host và bước người dùng/OP phụ thuộc môi trường. Hãy kiểm tra status, Location header và cookies trong browser DevTools, nhưng không lưu ID token hoặc client secret nguyên văn trong log.

### 6.5. Local-only logout trong cùng ứng dụng

Nếu yêu cầu nghiệp vụ chỉ là **đóng phiên RP**, có thể bỏ `.logoutSuccessHandler(oidcLogout)`, để handler mặc định chuyển tới trang login/logout thành công của RP. Khi đó RP session đã được đóng, nhưng OP có thể tiếp tục giữ phiên SSO. Đây là lựa chọn có chủ đích trong nhiều hệ thống cho phép “switch account”/“sign out from this app”; UI nên giải thích đúng phạm vi.

## 7. Cấu hình tương ứng trong WebFlux Reactive

Spring WebFlux dùng `SecurityWebFilterChain` và `ServerHttpSecurity` thay vì `SecurityFilterChain`/`HttpSecurity` của Servlet. Ví dụ sau là **một class cấu hình độc lập** cho dự án Boot 3.x dùng `spring-boot-starter-webflux`, `spring-boot-starter-security` và `spring-boot-starter-oauth2-client`, cùng client registration OIDC hợp lệ.

Lưu thành `src/main/java/demo/logout/ReactiveOidcLogoutConfig.java` khi ứng dụng reactive đã có main application class:

```java
package demo.logout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOidcLogoutConfig {

    @Bean
    SecurityWebFilterChain security(
            ServerHttpSecurity http,
            ReactiveClientRegistrationRepository registrations) {

        OidcClientInitiatedServerLogoutSuccessHandler oidc =
                new OidcClientInitiatedServerLogoutSuccessHandler(
                        registrations);
        oidc.setPostLogoutRedirectUri("{baseUrl}/signed-out");

        // Xóa security context và hủy WebSession theo yêu cầu cụ thể.
        DelegatingServerLogoutHandler local =
                new DelegatingServerLogoutHandler(
                        new SecurityContextServerLogoutHandler(),
                        new WebSessionServerLogoutHandler());

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/", "/signed-out").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutHandler(local)
                        .logoutSuccessHandler(oidc))
                .build();
    }
}
```

Ở đây `DelegatingServerLogoutHandler` ghép hai xử lý local thành một logout handler; sau đó OIDC logout success handler dựng redirect tới OP. Điều này không thay thế chính sách cleanup token được lưu ở database, và không tự gọi revocation endpoint. Không áp dụng đồng thời cấu hình Servlet ở phần 6 và WebFlux ở phần này trong cùng một ứng dụng rồi mong hai security chains tương tác.

**CSRF với WebFlux:** mặc định `LogoutWebFilter` bảo vệ thao tác logout bằng HTTP POST và CSRF; front-end phải gửi token hợp lệ. Vì OIDC logout handler trả redirect, cần trình duyệt thực hiện navigation tương ứng (ví dụ HTML form POST ở top-level). Tránh logout bằng GET chỉ vì “tiện mở link”.

**Lưu ý phiên bản:** OIDC back-channel APIs và chi tiết handler/session registry có thay đổi giữa các dòng Spring Security; đối với các API bên dưới hãy kiểm tra đúng version đang dùng. Mã local + RP-initiated ở trên dựa trên các API được Spring Security 6.x hỗ trợ.

## 8. OP-Initiated Logout: khi OP đăng xuất người dùng trước

Một người dùng có thể đăng xuất trực tiếp ở OP, hoặc quản trị viên thu hồi phiên đăng nhập. Nếu RP không nhận được tín hiệu, nó vẫn có thể giữ local session và tiếp tục cho người dùng sử dụng RP cho tới khi session local kết thúc hoặc chính sách của RP phát hiện thay đổi.

### 8.1. Front-channel logout

OP dùng **user agent** để gửi thông báo/logout URL đến một hoặc nhiều RP, ví dụ bằng navigation hoặc iframe theo profile đã đăng ký. Phương án này có thể bị chặn bởi cookie SameSite/third-party restrictions, iframe policy, browser đóng sớm hoặc mạng gián đoạn. Vì thế không nên coi front-channel là cơ chế đáng tin cậy tuyệt đối cho logout bắt buộc trên mọi session.

### 8.2. Back-channel logout

Theo [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html), OP gửi HTTP POST **trực tiếp từ server tới RP**, với field `logout_token` là một JWT đã ký. Browser của người dùng **không cần đang mở tab RP**.

```text
User/Admin                  OP                       RP
    | Logout ở OP             |                        |
    |------------------------>|                        |
    |                     Kết thúc OP session           |
    |                         |                         |
    |                         | POST back_channel URI   |
    |                         | logout_token=<JWT>      |
    |                         |------------------------>|
    |                         |               Xác minh token:
    |                         |               signature, iss, aud,
    |                         |               iat/exp/jti, events,
    |                         |               sid/sub, no nonce
    |                         |               -> tìm/hủy RP session
    |                         |<-------------- HTTP 200/400 ... |
```

**Logout token không phải ID token, access token hoặc refresh token.** Nó là tín hiệu đã ký theo định dạng riêng; không thể chỉ decode JWT rồi tin `sub`. Các kiểm tra bắt buộc/quan trọng bao gồm:

- `iss` đúng OP đã đăng ký, `aud` chứa client ID của RP và chữ ký/thuật toán hợp lệ; không nhận `alg=none`.
- `iat`, `exp` và `jti` để đánh giá thời điểm, chống replay theo yêu cầu thiết kế; không dùng thông điệp hết hạn.
- `events` phải chứa khóa `http://schemas.openid.net/event/backchannel-logout` theo chuẩn, với object value.
- **Phải có ít nhất một** trong `sub` hoặc `sid`; `nonce` **không được xuất hiện** trong logout token.
- `sid` liên hệ một OP session cụ thể nếu có; chỉ `sub` có thể tác động các session của user tại RP cho client/issuer tương ứng theo chính sách của chuẩn.
- Session registry phải phân biệt **issuer + audience/client + subject/session id**. Không xóa tất cả user có cùng email ở mọi tenant khi nhận một logout token.

Nếu không tìm được session tương ứng vì user đã logout từ trước, xử lý logout có thể coi là thành công; phải bảo đảm thao tác an toàn khi lặp. Nếu token không hợp lệ phải từ chối, không hủy session chỉ vì client gọi đúng endpoint.

### 8.3. Spring Security tích hợp back-channel logout

Tùy phiên bản Spring Security, WebFlux có thể đăng ký:

```java
// Trích đoạn trong cấu hình SecurityWebFilterChain reactive.
// Cần import các API tương ứng với phiên bản Spring Security.
http.oauth2Login(Customizer.withDefaults());
http.oidcLogout(oidc -> oidc
        .backChannel(Customizer.withDefaults()));
```

Spring Security documentation mô tả endpoint mặc định tương tự:

```text
POST /logout/connect/back-channel/{registrationId}
Content-Type: application/x-www-form-urlencoded

logout_token=<JWT của OP>
```

Trong cấu hình back-channel của từng phiên bản, có thể cần publish `OidcBackChannelServerLogoutHandler` như Spring Security hướng dẫn. Chẳng hạn trong API reactive được tài liệu Spring Security giới thiệu:

```java
// Trích đoạn bean, trong @Configuration đã import đúng lớp.
@Bean
OidcBackChannelServerLogoutHandler oidcLogoutHandler() {
    return new OidcBackChannelServerLogoutHandler();
}
```

**Đây là đoạn cấu hình minh họa, không phải cả project runnable**: muốn dùng phải kiểm tra dependency, Spring Security version, endpoint đã đăng ký tại OP, cách session được lưu, và tên session cookie thực tế. `oidcLogout` yêu cầu có `oauth2Login`. Spring Security documentation lưu ý correlation của back-channel logout thường dùng `JSESSIONID`, trong khi Spring Session có thể dùng `SESSION`; tên không khớp sẽ làm việc invalidation không hoạt động như mong đợi. Ở triển khai nhiều node, cần session registry/store chia sẻ phù hợp, không mặc định registry in-memory đủ dùng.

Đối với Servlet, cấu hình tương ứng nằm ở `HttpSecurity.oidcLogout(...backChannel(...))`, không phải lớp WebFlux. Theo tài liệu Spring Security Servlet, cấu hình đa node còn cần quan tâm `HttpSessionEventPublisher` và cơ chế đồng bộ hóa session registry.

**Không disable CSRF toàn ứng dụng để “cho phép OP callback”.** Dùng đúng integration back-channel đã xác thực logout token và cấu hình riêng cho endpoint nếu framework/version yêu cầu. Tuyệt đối không viết endpoint `POST /logout-by-email` nhận email rồi hủy session mà không xác minh thông điệp OP.

## 9. Token lifecycle: vì sao xóa phiên không làm access token mất hiệu lực?

OAuth 2.0 tách biệt vòng đời **user session**, **authorization grant** và **token**. Các token có thể được dùng giữa các hệ thống độc lập, không chịu tác động trực tiếp từ session cookie của RP.

### 9.1. Access token

- **Opaque access token:** RS có thể gọi AS qua Token Introspection (RFC 7662) để biết token còn active không; độ trễ và cache của RS ảnh hưởng thời điểm chính sách thu hồi được phản ánh.
- **JWT access token tự chứa:** RS có thể xác minh chữ ký, `iss`, `aud`, `exp`, `nbf`/scope hoàn toàn offline. Khi đó **AS revoke token không tự gửi tín hiệu tới RS**, RS có thể vẫn chấp nhận JWT đến `exp` nếu không có denylist, introspection hoặc cơ chế phối hợp khác.
- **Token ngắn hạn:** giảm cửa sổ lộ token nhưng không thay thế thu hồi phiên/refresh token khi có rủi ro. Cân đối thời gian sống với trải nghiệm và yêu cầu an toàn.
- **Khi token đã bị copy:** xóa token khỏi browser/authorized-client store **không thu hồi bản copy** trong tay bên thứ ba.

Một API chỉ chạy `oauth2ResourceServer().jwt()` xác minh Bearer token **không có session đăng nhập người dùng mặc định để logout theo nghĩa OIDC browser**. Gọi `POST /logout` của một session browser (nếu tồn tại) không có nghĩa JWT đã cấp bị vô hiệu. Đối với yêu cầu “đăng xuất mọi thiết bị”, cần thiết kế AS revocation, policy token và quản lý session/grant theo mô hình hệ thống.

### 9.2. Refresh token

Refresh token cho phép xin access token mới. Nếu user logout nhưng refresh token chưa bị revoke, một client còn giữ refresh token có thể tiếp tục đổi token cho tới khi bị AS từ chối do expiry, rotation, inactivity, revocation hoặc chính sách grant.

- **Revoke refresh token:** thường là ưu tiên khi client chấm dứt ủy quyền thông thường hoặc phát hiện compromise, theo khả năng endpoint và chính sách AS.
- **Refresh token rotation:** AS cấp refresh token mới khi đổi; token cũ có thể không dùng lại được, nhưng semantics family revocation/reuse detection tùy AS. Không giả định rotation tự xảy ra trong mọi provider.
- **Offline access:** refresh token phát hành với quyền/thuộc tính `offline_access` có thể có lifecycle độc lập với phiên SSO; OIDC Back-Channel Logout spec thậm chí phân biệt chính sách đối với refresh token offline và không offline. Do đó **không được tuyên bố OP logout luôn revoke mọi refresh token**.
- **Local removal khác revoke:** chỉ xóa bản lưu local khiến app không còn token để tiếp tục dùng; nếu token bị đánh cắp trước đó, nó có thể còn hợp lệ ở AS.

### 9.3. ID token

ID token là bằng chứng của **sự kiện xác thực OIDC** dành cho RP, không phải “thẻ vào cửa” của mọi API. Việc local logout không thể làm chữ ký trong ID token đã phát hành biến mất. ID token cũng có `exp` riêng; OP có thể chấp nhận ID token cũ làm `id_token_hint` theo quy tắc OIDC logout kể cả khi token hết hạn, nhưng đó là quyết định của OP và không cho phép dùng ID token như access token.

### 9.4. Logout token

Logout token của back-channel là **thông điệp sự kiện** do OP ký để RP hủy session liên quan. Nó không phải credential để truy cập API và không nên được lưu/đưa vào `Authorization: Bearer` như access token. Nếu chấp nhận sai `logout_token`, attacker có thể gây logout cưỡng bức cho người khác hoặc tenant khác.

## 10. OAuth 2.0 Token Revocation (RFC 7009)

[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009) định nghĩa một revocation endpoint tại AS. Client có thẩm quyền gửi token cần thu hồi, có thể kèm `token_type_hint`, và xác thực client theo phương thức AS yêu cầu.

### 10.1. HTTP request mẫu

```http
POST /oauth2/revoke HTTP/1.1
Host: id.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials>

token=<refresh-token-value>&token_type_hint=refresh_token
```

Đây là **mẫu giao thức**; endpoint path và cách xác thực client do AS/Discovery/quy định provider quyết định. Không sao chép `Basic <client-credentials>` vào browser hoặc public SPA: client secret phải được bảo vệ trong backend/confidential client. Không in token thực vào log, URL query, analytics hoặc command history.

`token_type_hint` là một gợi ý, không phải bằng chứng token thuộc loại đó. AS có thể làm mất hiệu lực các token liên quan/grant theo policy riêng. RFC 7009 nêu rằng response **200** có thể được trả cả khi token đã được revoke lẫn khi token không hợp lệ, nên **HTTP 200 không chứng minh token từng tồn tại**. Lỗi xác thực client, unsupported token type hoặc lỗi mạng cần được xử lý theo hợp đồng cụ thể.

### 10.2. Revocation làm thay đổi điều gì?

Giả sử AS thu hồi refresh token R, các token access A đã cấp trước đó có thể vẫn được RS chấp nhận. Khi đó:

```text
Refresh R:  không dùng để đổi access token mới được (nếu AS đã revoke)
Access A:   có thể vẫn được RS chấp nhận tới exp/cache invalidation
RP cookie:  có thể đã bị xóa riêng
OP cookie:  có thể vẫn còn riêng
```

Muốn “ngừng mọi access ngay lập tức” cần định nghĩa yêu cầu end-to-end: AS phải có trạng thái thu hồi, RS phải kiểm tra/nhận trạng thái ấy và giới hạn cache, tất cả session/client liên quan phải được xác định đúng. Không thể đạt bảo đảm này bằng một redirect browser duy nhất.

### 10.3. Quy trình an toàn ở BFF / confidential web client

Một **Backend For Frontend (BFF)** giữ refresh token trong backend có thể triển khai yêu cầu logout có trình tự rõ:

1. Nhận logout request đã qua CSRF/authentication check của RP.
2. Xác định phiên và authorized client liên quan bằng định danh đã xác thực (không nhận token/client ID tùy ý từ payload browser).
3. Khi chính sách yêu cầu, gửi revocation từ backend tới AS theo thông số provider và xử lý lỗi/timeout có kiểm soát.
4. Xóa token/authorized-client record mà backend sở hữu, hủy session RP, xóa cookie theo policy.
5. Nếu muốn kết thúc SSO, điều hướng browser tới OP logout endpoint với tham số hợp lệ và URL quay về đã đăng ký.

Thứ tự cụ thể tùy policy: một số hệ thống cần giữ ID token tới khi dựng redirect; một số hệ thống cần bảo đảm **local logout diễn ra dù AS revocation tạm thời thất bại**. Xác định kết quả và retry/telemetry cho từng bước, không khóa người dùng trong một session đang hoạt động chỉ vì một endpoint bên ngoài lỗi.

## 11. “Logout mọi nơi” là yêu cầu sản phẩm cần diễn giải thành hợp đồng

“Sign out”, “Sign out of this app”, “Sign out of all devices” và “Revoke this app's access” không tương đương.

| Yêu cầu người dùng | Điều kiện tối thiểu cần thực hiện | Tài nguyên có thể nằm ngoài tầm kiểm soát |
| --- | --- | --- |
| Đăng xuất khỏi ứng dụng này ở tab/browser hiện tại | Hủy RP local session, dọn trạng thái client đúng scope | OP vẫn có SSO session; token đã cấp ở nơi khác |
| Đăng xuất cả khỏi OP / SSO | Local logout + RP-Initiated OP logout, kiểm tra hỗ trợ provider | RP khác có nhận notification hay không; token offline |
| Đăng xuất mọi session của cùng RP | Liệt kê và vô hiệu session của user ở session store/registry phù hợp | OP/ứng dụng khác vẫn hoạt động |
| Chấm dứt ủy quyền cấp token | Revoke grant/refresh token tại AS theo chức năng AS | Access JWT đã cấp và còn hạn |
| Khóa tài khoản sau sự cố | Vô hiệu tài khoản/credential, thu hồi sessions/grants/tokens theo policy, cập nhật RS | Cache/độ trễ propagation và hệ thống ngoài miền tin cậy |

Một OP có thể cung cấp API quản lý phiên đa thiết bị hoặc logout toàn bộ, nhưng **không phải chuẩn RP-Initiated Logout tự bảo đảm điều đó**. Đăng xuất RP A cũng không có nghĩa RP B đã xóa session trừ khi OP thông báo và RP B xử lý thành công.

### Hai thiết bị và một người dùng

Nếu Alice đăng nhập trên laptop và điện thoại, logout trên laptop thường chỉ hủy session laptop tại RP. Một back-channel logout token chứa `sid` có thể nhắm tới một phiên tương ứng; thông điệp chỉ có `sub` có thể yêu cầu RP hủy tất cả các session của subject thuộc client/issuer đó theo cơ chế hỗ trợ. Đừng gộp session theo email vì email có thể thay đổi hoặc không duy nhất giữa issuer.

## 12. Kiến trúc browser / SPA / mobile / service-to-service

### 12.1. Web app với session ở server

Servlet/Spring MVC `oauth2Login` thường dùng server-side session để lưu authentication và OAuth2 authorized client tùy repository. Local logout đóng phiên RP; RP-Initiated OIDC logout đi theo browser redirect; token revocation là chính sách bổ sung.

### 12.2. SPA dùng OIDC Authorization Code + PKCE

Ứng dụng SPA thường có trạng thái đăng nhập ở browser và token được giữ theo thiết kế thư viện/kiến trúc. Khi logout:

- Xóa state/token khỏi đúng storage nếu ứng dụng sở hữu, không để UI hiển thị thông tin người dùng cũ.
- Dùng cơ chế logout của OIDC client library để điều hướng OP và quản lý `state`/callback an toàn khi provider hỗ trợ.
- Không nhúng client secret vào JS hoặc gọi revocation endpoint yêu cầu confidential client credentials từ browser.
- Thận trọng với refresh token trong browser, XSS, các tab đồng thời và trạng thái SSO còn ở OP.
- Không nhận định API Bearer access token mất hiệu lực chỉ vì localStorage/sessionStorage được xóa.

Nếu muốn giảm bề mặt token trong trình duyệt, xem xét mô hình BFF giữ token ở backend và cung cấp phiên same-site cho browser; logout BFF sẽ cần cleanup ở cả server lẫn provider theo chính sách.

### 12.3. Mobile / native app

Đăng xuất thường gồm xóa credential khỏi secure storage, yêu cầu OP logout qua browser system/session cơ chế được provider hỗ trợ, và thu hồi token khi cần. Session cookie trong system browser có thể còn, làm tài khoản tự đăng nhập lại ở lần sau. Không áp dụng máy móc `JSESSIONID` của Spring MVC cho native mobile app.

### 12.4. Machine-to-machine / client credentials

Một service sử dụng client credentials grant thường **không có end-user OP SSO session** để logout. Dừng client, xóa token local, thu hồi token nếu AS hỗ trợ, rotate/revoke client credential và ngăn cấp token mới theo policy. Gọi OIDC `end_session_endpoint` cho một client credentials token không phải cơ chế phù hợp.

### 12.5. Resource server thuần stateless

Nếu service chỉ xử lý `Authorization: Bearer <access_token>` và xác minh JWT, nó không thể hủy một cookie/session mà không tồn tại. Để dừng access token trước `exp` phải phối hợp AS, denylist/session version, introspection hoặc kỹ thuật tương đương phù hợp. Tránh cung cấp endpoint `/logout` giả tạo chỉ xóa `SecurityContextHolder` cho request hiện tại rồi trả “token revoked”.

## 13. Reverse proxy, redirect URI và cookie: những điểm dễ sai

### 13.1. `{baseUrl}` khi đặt phía sau gateway

Spring Security logout success handler có thể dùng `{baseUrl}` làm giá trị `post_logout_redirect_uri`. Nếu app chạy nội bộ `http://app:8080` nhưng người dùng truy cập `https://tasks.example.org`, URI sinh ra có thể sai nếu proxy và ứng dụng xử lý forwarded headers không đúng. Hãy:

- Đăng ký đúng URI public ở OP và đối chiếu thực tế HTTP `Location`.
- Chỉ tin `Forwarded` / `X-Forwarded-*` từ reverse proxy được kiểm soát; xóa header không đáng tin ở ingress.
- Không cho client tự quyết định target logout thông qua `returnUrl` không được kiểm tra allowlist.

### 13.2. Cookie domain, SameSite, Secure và path

RP cookie (`JSESSIONID`/`SESSION`) và OP SSO cookie thường thuộc **domain khác nhau**. RP không thể tùy ý xóa cookie thuộc domain OP; browser chỉ nhận cookie deletion hợp lệ từ domain/phạm vi tương ứng. Hãy kiểm tra `Secure` và `SameSite` để luồng callback/logout phù hợp với HTTPS và browser policy, nhưng không hạ các thuộc tính bảo mật chỉ để giải quyết một lỗi chưa khoanh vùng.

### 13.3. Cookie deletion không thay server invalidation

Logout handler phải chấm dứt phiên trong session store, không chỉ trả header `Set-Cookie: JSESSIONID=; Max-Age=0`. Trong hệ thống Redis/session cluster, xóa đúng session key và liên kết session cần thiết; nếu có caching, kiểm tra replication/TTL.

### 13.4. Back-channel trên hạ tầng nhiều node

Back-channel request thường không đi qua browser và **không mang RP cookie của người dùng**. RP cần session registry để tìm đúng local sessions theo OP `sid`/`sub`/`iss`/`aud`. Nếu registry nằm memory mỗi node mà logout đến node khác, sẽ xuất hiện phiên không bị xóa. Cần cơ chế registry/store chia sẻ, eviction, sự kiện session invalidation và kiểm thử concurrency/replay.

## 14. Các lỗi thường gặp và cách sửa

| Biểu hiện | Nguyên nhân khả dĩ | Cách xác định/sửa |
| --- | --- | --- |
| Bấm logout rồi vào `/me` lại không hỏi mật khẩu | Local logout thành công nhưng OP SSO session còn | Xem redirect tới `end_session_endpoint`, đăng ký post-logout URL và OP policy; không kết luận RP session còn |
| Logout xong API vẫn nhận Bearer JWT cũ | JWT còn hạn, RS kiểm tra offline, thiếu revoke/denylist | Đo chính sách AS/RS, token exp, cache; thiết kế revocation/end-to-end semantics |
| `GET /logout` chỉ hiện trang xác nhận | CSRF mặc định yêu cầu POST để logout | Dùng form POST có CSRF token; không tắt CSRF để bỏ xác nhận |
| SPA gọi fetch logout, OP không hiện ra | Redirect xảy ra trong fetch thay vì top-level navigation | Dùng form hoặc navigation flow phù hợp OIDC client library |
| OP báo redirect URI không hợp lệ | `post_logout_redirect_uri` khác URI đã đăng ký, sai scheme/host/path | Đối chiếu URI public chính xác, proxy headers, provider registration |
| Logout OP rồi vẫn có session ở RP khác | RP khác không nhận/không xử lý front/back-channel notification | Kiểm tra hỗ trợ OP/RP, back-channel endpoint, session registry |
| Back-channel nhận request nhưng không hủy session | Token bị reject, sai client/issuer, cookie name hoặc registry không đồng bộ | Kiểm tra kết quả validation, correlation `sid`, `JSESSIONID`/`SESSION`, multi-node |
| Logout ở một thiết bị xóa quá nhiều phiên | Mapping theo username/email thay vì issuer + client + `sid` | Tách chính sách một phiên/tất cả, dùng registry định danh chuẩn |
| Refresh token vẫn đổi được sau logout | Chỉ xóa RP cookie; AS chưa revoke refresh token | Kiểm tra chức năng revocation, offline access, refresh token policy |
| Token revocation trả 200 nhưng JWT vẫn dùng được | RFC 7009 cho phép 200 cả với token không hợp lệ; RS chưa nhận trạng thái | Test trực tiếp trên RS, exp/introspection/cache thay vì dựa HTTP 200 |
| Logout thất bại khi OP tạm ngừng | Ứng dụng phụ thuộc đồng bộ vào OP | Đảm bảo local session được chấm dứt, có fallback và log cảnh báo đúng scope |
| Người dùng mất session nhưng token còn ở DB | Authorized client lưu ngoài session | Làm rõ cleanup repository và gọi AS revocation theo policy |
| Front-channel logout lúc được lúc không | Browser chặn iframe/third-party cookies/đóng tab | Ưu tiên back-channel nếu tính năng OP/RP có, kiểm thử SameSite và browser |

## 15. Kiểm thử có thể lặp lại và tiêu chí PASS

Không chỉ test rằng HTTP redirect xuất hiện; cần quan sát **từng tầng trạng thái**. Bộ test có thể thực hiện trên môi trường tích hợp với OP thật hoặc test provider có logout/revocation chức năng tương ứng.

| # | Tình huống | Dấu hiệu cần khẳng định |
| --- | --- | --- |
| 1 | User đăng nhập OIDC, gọi endpoint bảo vệ | RP tạo session hợp lệ; chỉ người đã xác thực truy cập được |
| 2 | `POST /logout` hợp lệ, chế độ local-only | RP session invalidated; vào endpoint bảo vệ yêu cầu login; OP SSO có thể còn |
| 3 | `GET /logout` hoặc POST thiếu CSRF | Không làm thay đổi session ngoài chủ đích của chính sách CSRF |
| 4 | RP-Initiated logout, OP hỗ trợ end-session | RP local logout thành công; browser đi qua OP logout; URI quay về đã đăng ký |
| 5 | OP không hỗ trợ hoặc từ chối end-session | RP không giữ phiên đã logout; có fallback/report rõ, không khẳng định SSO toàn cục đã đóng |
| 6 | JWT access token được cấp trước logout | Gọi RS trước/sau logout; ghi nhận còn được chấp nhận theo `exp`/revocation policy |
| 7 | Revoke refresh token tại AS | Refresh request với token cũ bị từ chối theo chính sách AS, kể cả local session đã mất |
| 8 | Logout từ OP qua back-channel | Logout token hợp lệ dẫn tới đúng local session invalidation |
| 9 | Back-channel logout token sai chữ ký/issuer/audience/exp/events hoặc có nonce | RP từ chối, **không hủy session hợp lệ** |
| 10 | Hai session cùng user, khác `sid` | Logout theo `sid` chỉ ảnh hưởng session liên quan, không nhầm thiết bị |
| 11 | Nhiều tenant/issuer cùng claim `sub` hoặc email | Không hủy nhầm session của issuer/client khác |
| 12 | Multi-node và Spring Session | Back-channel đến node nào cũng vô hiệu session tương ứng |
| 13 | Đăng nhập lại sau RP local logout | Nếu OP session còn, SSO có thể cấp login mới; nếu OP logout thành công, kiểm tra OP theo policy |
| 14 | Frontend gửi logout bằng fetch vs form top-level | Form/navigation đưa browser tới OP theo dự kiến; fetch đơn thuần không thay trang |
| 15 | API thuần JWT không giữ session | Không tuyên bố “logout xong JWT vô hiệu” nếu chưa có cơ chế ở RS |

Với ứng dụng Servlet, có thể dùng `MockMvc` và `spring-security-test` để kiểm tra POST/CSRF, nhưng mock logout test không chứng minh OP thật đã kết thúc SSO hoặc RS thật đã ngừng nhận JWT. Với WebFlux, dùng `WebTestClient` và integration test tương ứng. Thử cả đường browser redirect và server-to-server back-channel trên hạ tầng triển khai thực tế.

### Bài tập tự kiểm tra: chứng minh các trạng thái độc lập bằng Java 17 thuần

Ví dụ nhỏ sau là **mô hình trạng thái giả lập**; nó không giao tiếp với Spring Security hoặc OP. Nó giúp thấy rằng các cập nhật state khác nhau cần hành động riêng, không thể suy từ một flag. Lưu thành `LogoutBoundaryDemo.java`:

```java
public class LogoutBoundaryDemo {
    record State(boolean rp, boolean op, boolean access, boolean refresh) {
        @Override
        public String toString() {
            return "rp=" + rp + ", op=" + op
                    + ", access=" + access + ", refresh=" + refresh;
        }
    }

    public static void main(String[] args) {
        State before = new State(true, true, true, true);

        // Mô phỏng local logout: chỉ chắc chắn mất RP session.
        State local = new State(false, before.op(), before.access(),
                before.refresh());

        // Mô phỏng OP logout thành công: kết thúc thêm OP session.
        State afterOp = new State(local.rp(), false, local.access(),
                local.refresh());

        // Mô phỏng AS xác nhận thu hồi refresh token.
        State afterRevoke = new State(afterOp.rp(), afterOp.op(),
                afterOp.access(), false);

        System.out.println("before:      " + before);
        System.out.println("local:       " + local);
        System.out.println("op logout:   " + afterOp);
        System.out.println("revoke R:    " + afterRevoke);
    }
}
```

Chạy với JDK 17+:

```bash
javac LogoutBoundaryDemo.java
java LogoutBoundaryDemo
```

Stdout chính xác:

```text
before:      rp=true, op=true, access=true, refresh=true
local:       rp=false, op=true, access=true, refresh=true
op logout:   rp=false, op=false, access=true, refresh=true
revoke R:    rp=false, op=false, access=true, refresh=false
```

Sự thật quan trọng: chương trình này **chỉ mô phỏng hậu quả được chỉ định**, không khẳng định mọi provider luôn giữ access token sau logout hay mọi AS luôn thu hồi refresh token theo cách giống nhau. Khi triển khai hệ thống thật, cần test AS/RS/RP policy cụ thể.

## 16. Checklist thiết kế trước khi đưa vào production

1. **Định nghĩa scope của nút đăng xuất:** logout RP hiện tại, logout SSO ở OP, logout mọi thiết bị, hay revoke access/grant? UI và API phải có lời hứa đúng với cơ chế.
2. **Chỉ định nơi lưu session/token:** Servlet `HttpSession`, reactive `WebSession`, Spring Session, OAuth2 authorized client service, browser storage; ai có quyền cleanup?
3. **Giữ CSRF cho browser logout:** POST và CSRF token đúng; không thêm GET logout vô tình cho phép logout cưỡng bức.
4. **Dùng OIDC handler chuẩn:** `OidcClientInitiatedLogoutSuccessHandler` hoặc `OidcClientInitiatedServerLogoutSuccessHandler` cho RP-Initiated, không tự nối URL từ input không tin cậy.
5. **Đăng ký URI đúng:** OIDC Discovery có `end_session_endpoint`, `post_logout_redirect_uri` đăng ký khớp public URL; xác định có hay không OP logout confirmation.
6. **Xử lý sự cố OP:** vẫn hủy RP session local theo chính sách; có fallback và telemetry, không nói “logout all devices” khi OP thất bại.
7. **Bật back-channel khi yêu cầu global SSO:** kiểm tra phiên bản Spring Security, OP registration, logout token signature/claims, session registry đa node, tên cookie và replay policy.
8. **Quyết định token revocation:** AS endpoint, client authentication, refresh vs access, JWT/opaque, RS cache/denylist, offline access và vòng đời authorization grant.
9. **Giới hạn token trong browser:** lưu ở nơi thích hợp, chống XSS/CSRF, hạn chế log `id_token_hint`/`logout_token`/access/refresh token.
10. **Kiểm thử end-to-end:** đa RP, đa browser, nhiều session, hai user/tenant, OP session còn, access JWT còn hạn, back-channel bị trễ, revoked refresh token và proxy.
11. **Quan sát dữ liệu an toàn:** log kết quả từng bước và correlation ID; không log raw token, cookie, client secret hoặc đầy đủ nội dung ID token.
12. **Ràng buộc phiên bản:** kiểm tra tài liệu/contract đúng Spring Security version và OP đang dùng, nhất là back-channel và session registry, tránh sao chép cấu hình từ stack Servlet sang Reactive.

Nguyên tắc xuyên suốt: **local logout đóng phiên ứng dụng; OIDC logout điều phối phiên của nhà cung cấp danh tính và các RP; OAuth token revocation là hợp đồng riêng với Authorization Server.** Tính bảo mật cuối cùng phụ thuộc cách Resource Server thực thi thời hạn và trạng thái token.

## 17. Tài liệu chuẩn để đối chiếu

- [Spring Security — Servlet OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): local logout, RP-Initiated logout và back-channel logout.
- [Spring Security — Reactive OIDC Logout](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html): `OidcClientInitiatedServerLogoutSuccessHandler`, `oidcLogout`, back-channel session registry.
- [Spring Security — Servlet Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): `POST /logout`, CSRF, `SecurityContextLogoutHandler` và default cleanup.
- [Spring Security — Reactive Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): `LogoutWebFilter`, local security context và `WebSessionServerLogoutHandler`.
- [Spring Security — Reactive CSRF/Logout](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): lý do nên dùng POST với CSRF.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): `end_session_endpoint`, `id_token_hint` và `post_logout_redirect_uri`.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): cấu trúc/validation của `logout_token`, `sid` và `sub`.
- [OpenID Connect Front-Channel Logout 1.0](https://openid.net/specs/openid-connect-frontchannel-1_0.html): thông báo qua browser và giới hạn front-channel.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): revocation endpoint và semantics HTTP 200.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): token active status và cách RS hỏi AS.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): các claim JWT như `iss`, `aud`, `exp`.
