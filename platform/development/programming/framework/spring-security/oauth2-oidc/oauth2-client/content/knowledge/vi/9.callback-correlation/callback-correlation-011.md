# 9.11. Cookie, SameSite, session và reverse proxy trong bước callback

## 1. Bối cảnh: callback đúng URL nhưng đăng nhập vẫn thất bại

Giả sử một **Employee Portal** được xây dựng bằng **Spring Boot**, **Spring Security OAuth 2.0 Client** và **OpenID Connect (OIDC)**. Người dùng nhấn **Đăng nhập bằng tài khoản công ty**. Portal chuyển trình duyệt đến Identity Provider (IdP), người dùng nhập thông tin xác thực, IdP xác nhận thành công và chuyển browser về:

~~~text
https://portal.example.test/login/oauth2/code/company?code=...&state=...
~~~

Mặc dù URL callback có vẻ đúng, Portal lại báo lỗi, chẳng hạn:

- Không tìm thấy authorization request ban đầu.
- Giá trị `state` không tương ứng với request đã khởi tạo.
- Sau callback người dùng bị chuyển về trang login hoặc gặp vòng lặp đăng nhập.
- Ở local đăng nhập bình thường, nhưng khi đi qua ingress/reverse proxy ở staging hoặc production thì lỗi.
- Cookie có trong phản hồi khi bắt đầu login nhưng không có trong request callback.

Những tình huống này liên quan chặt chẽ đến **HTTP session**, **session cookie**, chính sách **SameSite** của trình duyệt, cách triển khai **reverse proxy**, cũng như cơ chế **correlation** trong OAuth 2.0 Authorization Code Flow.

Bài học tập trung vào điều kiện để callback có thể **được định tuyến đến đúng filter**, **tìm lại authorization request đã lưu**, **đối chiếu giao dịch**, rồi **hoàn tất OIDC login**. Các ví dụ dùng Java 17+, Spring Boot 3, Spring Security 6 trên **Servlet stack (Spring MVC)**. Hostname và secret chỉ dùng để minh họa.

## 2. Các thành phần cùng tham gia callback

| Thành phần | Trách nhiệm |
|---|---|
| **Browser** | Giữ cookie của Portal, điều hướng đến IdP và quay lại callback theo redirect hoặc form POST |
| **Employee Portal** | OAuth 2.0 Client/OIDC Relying Party; lưu trạng thái authorization trong session, xác minh callback, tạo phiên đăng nhập |
| **Authorization Server / OpenID Provider** | Xác thực người dùng, trả authorization code và state, cấp token khi Portal đổi code |
| **Reverse proxy / ingress** | Nhận HTTPS từ browser, chuyển request vào ứng dụng, kiểm soát thông tin host/scheme/prefix được forward |
| **Session store** | Lưu dữ liệu phiên mà Portal cần để đối chiếu authorization response |
| **Orders API** | Resource Server được Portal gọi sau login bằng access token; không trực tiếp tham gia callback của Portal |

Cần phân biệt bốn đối tượng thường được gọi chung là “token/trạng thái đăng nhập”:

1. **Session cookie của Portal**, ví dụ `JSESSIONID`, là giá trị định danh phiên mà browser gửi đến Portal.
2. **Authorization request đang chờ** chứa `state`, redirect URI, client registration và thông tin PKCE/OIDC cần cho bước tiếp theo. Dữ liệu này thường được lưu **phía server**, gắn với session.
3. **Authorization code** được IdP trả về ở callback; Portal dùng code để đổi token tại token endpoint.
4. **ID Token, access token và refresh token** (nếu được cấp) là kết quả của bước đổi code và xác thực; chúng không phải session cookie của Portal.

**Cookie session không phải OAuth access token.** Trong mô hình web server-side/BFF, browser không cần giữ access token để Portal đăng nhập và gọi API thay mặt người dùng.

## 3. Toàn cảnh luồng authorization và callback trên Servlet

Spring Security thường dùng:

- `OAuth2AuthorizationRequestRedirectFilter` để khởi tạo authorization request.
- `OAuth2AuthorizationRequestResolver` để xây dựng request gửi tới IdP.
- `HttpSessionOAuth2AuthorizationRequestRepository` để lưu authorization request trước khi redirect.
- `OAuth2LoginAuthenticationFilter` để nhận callback và phối hợp kiểm tra authorization response.
- `SecurityContext` và session để duy trì trạng thái đăng nhập thành công.

Sơ đồ minh họa:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant P as Reverse proxy
    participant A as Spring Boot Portal
    participant S as HTTP Session Store
    participant I as OIDC Provider

    U->>B: Nhấn Đăng nhập công ty
    B->>P: GET /oauth2/authorization/company
    P->>A: Forward request
    A->>A: Sinh state, nonce/PKCE khi áp dụng
    A->>S: Lưu OAuth2AuthorizationRequest theo session
    A-->>P: 302 đến IdP, Set-Cookie nếu tạo session mới
    P-->>B: Location và session cookie của Portal
    B->>I: Theo redirect, xác thực tại IdP
    I-->>B: Redirect với code và state
    Note over B: Browser quyết định có gửi cookie Portal theo SameSite/Secure/Path/Domain
    B->>P: GET callback?code=...&state=... + Cookie (nếu được phép)
    P->>A: Forward callback
    A->>S: Tìm authorization request của session
    S-->>A: Request gốc nếu session còn hợp lệ
    A->>A: Đối chiếu state và thông tin giao dịch
    A->>I: Đổi code lấy token qua token endpoint
    I-->>A: Token response
    A->>S: Lưu SecurityContext và authorized client phù hợp
    A-->>B: Redirect đến trang ứng dụng
~~~

**Điểm then chốt:** IdP có thể trả `code` và `state` hoàn toàn đúng, nhưng nếu browser **không gửi cookie session của Portal** khi callback quay về, ứng dụng có thể không tìm được authorization request đã lưu để đối chiếu.

## 4. Session được sử dụng ở những thời điểm nào?

### 4.1. Khi bắt đầu login

Browser truy cập:

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
~~~

Spring Security tạo `OAuth2AuthorizationRequest`, gồm những thông tin quan trọng như:

- **client registration** được chọn, ví dụ `company`.
- **redirect URI** của Portal.
- **state** là giá trị dùng để gắn response với request.
- **nonce** của OIDC, nếu áp dụng.
- **PKCE code verifier** được giữ cho bước đổi code khi sử dụng PKCE.

Với cấu hình Servlet thường gặp, `HttpSessionOAuth2AuthorizationRequestRepository` lưu đối tượng request vào **HTTP session**. Nếu chưa có session, ứng dụng có thể tạo session và trả cookie định danh phiên.

Ví dụ response minh họa:

~~~http
HTTP/1.1 302 Found
Location: https://login.example.test/oauth2/authorize?response_type=code&client_id=...
Set-Cookie: JSESSIONID=<session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Không phải mọi lần redirect đều phải có header `Set-Cookie`: nếu session đã tồn tại, browser có thể đã giữ cookie từ request trước. Ví dụ trên thể hiện trường hợp ứng dụng tạo và gửi cookie mới.

### 4.2. Khi callback quay về

IdP chuyển browser về Portal:

~~~http
GET /login/oauth2/code/company?code=<authorization-code>&state=<state> HTTP/1.1
Host: portal.example.test
Cookie: JSESSIONID=<session-id>
~~~

Server dùng cookie để truy cập đúng HTTP session, tìm authorization request đã lưu và đối chiếu với authorization response. Nếu session không tồn tại hoặc request đã bị xóa/tiêu thụ, bước tương quan có thể thất bại dù URI callback khớp.

### 4.3. Sau khi login thành công

Spring Security hoàn tất xác thực OIDC và tạo `Authentication`. Trạng thái đăng nhập có thể được lưu qua `SecurityContextRepository` vào HTTP session, tùy cấu hình bảo mật.

Spring Security cũng có thể thực hiện **session fixation protection**, ví dụ đổi session ID sau khi đăng nhập. Vì vậy thấy **session cookie thay đổi sau khi login thành công** không tự nó là dấu hiệu lỗi. Cần phân biệt cookie của phiên **đang chờ callback** với cookie của phiên đã xác thực.

Session có thể hết hạn do timeout, bị xóa khi logout, bị thay đổi bởi chính sách ứng dụng hoặc không được tìm thấy ở node khác. Cookie trong browser **không bảo đảm** dữ liệu session ở backend còn tồn tại.

## 5. Các thuộc tính cookie tác động trực tiếp đến callback

| Thuộc tính | Tác dụng | Điểm cần lưu ý cho OAuth2/OIDC |
|---|---|---|
| **Name** | Tên cookie, ví dụ `JSESSIONID` | Các ứng dụng trên cùng host cần tránh đè cookie nhau |
| **Value** | Định danh session | Phải khó đoán và được bảo vệ; không ghi vào log |
| **Secure** | Chỉ gửi cookie qua kết nối HTTPS, với ngoại lệ phát triển cục bộ tùy browser | Bật cho production dùng HTTPS |
| **HttpOnly** | Ngăn JavaScript đọc cookie qua `document.cookie` | Bật để giảm rủi ro đánh cắp session qua JavaScript |
| **SameSite** | Quy định cookie có được gửi trong ngữ cảnh điều hướng/request cross-site hay không | Đặc biệt quan trọng khi browser quay từ IdP về Portal |
| **Path** | Giới hạn đường dẫn nào được gửi cookie | Callback phải nằm trong phạm vi path của cookie |
| **Domain** | Giới hạn host/domain nhận cookie | Mặc định host-only thường an toàn hơn mở rộng toàn bộ domain |
| **Max-Age / Expires** | Tuổi thọ cookie phía browser nếu được đặt | Khác với timeout và hiệu lực dữ liệu session phía server |

Ví dụ khi cookie có:

~~~http
Set-Cookie: JSESSIONID=abc...; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Browser có thể gửi cookie cho đường dẫn `/portal/login/oauth2/code/company`, nhưng **không gửi cookie cho `/login/oauth2/code/company`** nếu đường dẫn đó nằm ngoài `Path=/portal`. Đây là lỗi thường gặp khi ứng dụng thay đổi context path hoặc proxy rewrite URL nhưng cookie path không được cập nhật phù hợp.

**Domain** cũng quan trọng: cookie host-only được tạo bởi `portal.example.test` không được tự động gửi cho `login.example.test`. Điều này là bình thường, vì IdP không cần cookie session của Portal. Cookie của Portal cần được gửi **khi browser quay lại đúng host của Portal**.

## 6. Hiểu SameSite đúng với bước callback

**SameSite** là thuộc tính cookie giúp trình duyệt quyết định có gửi cookie trong ngữ cảnh giữa các **site** hay không. Khái niệm **site** không hoàn toàn giống **origin**: hai origin khác nhau có thể được xem là cùng site trong một số trường hợp; trình duyệt hiện đại còn xem xét scheme trong mô hình schemeful same-site.

Nếu Portal là `https://portal.example.test` và IdP là `https://login.company-idp.test`, việc browser quay từ IdP về Portal thường là **cross-site navigation**. Nếu cả hai thực sự cùng site theo quy tắc của browser thì quyết định cookie có thể khác; không suy ra chỉ từ việc host khác nhau.

Ba giá trị chính:

| SameSite | Điều hướng top-level **GET** từ IdP khác site về Portal | **POST** cross-site từ IdP về Portal | Nhận xét |
|---|---|---|---|
| **Strict** | Thường **không gửi** cookie | **Không gửi** | Dễ làm mất session trong callback cross-site |
| **Lax** | Thường **gửi** cookie | Thường **không gửi** cookie | Phù hợp với callback Authorization Code dạng redirect GET thông dụng |
| **None** | Cho phép gửi theo quy tắc cookie còn lại | Cho phép gửi theo quy tắc cookie còn lại | Cần `Secure`; vẫn chịu chính sách chặn cookie khác của browser |

Điều kiện quan trọng:

- **SameSite=Lax** áp dụng với **top-level navigation sử dụng phương thức an toàn như GET**; đừng nhầm với lời gọi fetch/XHR cross-site hoặc iframe.
- **SameSite=Strict** có thể khiến browser **không gửi cookie của Portal khi IdP trả redirect từ một site khác**, dẫn tới mất authorization request.
- **SameSite=None** phải đi cùng **Secure** trong các trình duyệt hiện đại và chỉ có ích khi cookie vẫn đáp ứng Domain, Path, expiry và các chính sách chặn cookie khác.
- Không khai báo SameSite **không phải** cách đáng tin cậy để bảo đảm hỗ trợ POST callback; nhiều trình duyệt mặc định xử lý cookie chưa khai báo theo chính sách gần với Lax, với một số ngoại lệ triển khai không nên dựa vào.

**SameSite không thay thế CSRF protection**, cũng không thay thế `state`, `nonce` hoặc PKCE của OAuth2/OIDC.

## 7. Callback mặc định bằng GET: SameSite=Lax thường phù hợp

Với **Authorization Code Flow** sử dụng callback qua query string, IdP thường trả HTTP redirect để browser điều hướng về Portal:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.test/login/oauth2/code/company?code=<code>&state=<state>
~~~

Browser thực hiện **top-level GET navigation** đến Portal. Khi cookie có `SameSite=Lax`, `Secure`, Domain và Path phù hợp, browser thường gửi session cookie của Portal.

Nhờ đó:

1. `OAuth2LoginAuthenticationFilter` nhận callback ở đường dẫn phù hợp.
2. AuthorizationRequestRepository tìm được request đã lưu trong session.
3. Spring Security kiểm tra tương quan của `state` và những dữ liệu cần thiết khác.
4. Portal đổi authorization code lấy token và hoàn tất OIDC login.

Đây là lý do **Lax là một lựa chọn thông dụng** cho session cookie của ứng dụng web dùng OIDC Authorization Code Flow với callback dạng GET.

Tuy nhiên, Lax **không bảo đảm login thành công trong mọi cấu hình**. Nếu cookie có `Path` sai, host khác, thiếu HTTPS cho cookie Secure, session ở backend đã mất hoặc proxy định tuyến sai, callback vẫn có thể lỗi.

## 8. Callback bằng form_post: cần xem xét SameSite=None và CSRF

Một số OpenID Provider hỗ trợ **`response_mode=form_post`**, trong đó IdP trả về một trang HTML có form và trình duyệt **POST** trực tiếp đến callback URL của Portal.

Ví dụ dạng request:

~~~http
POST /login/oauth2/code/company HTTP/1.1
Host: portal.example.test
Content-Type: application/x-www-form-urlencoded
Cookie: JSESSIONID=<session-id>

code=<authorization-code>&state=<state>
~~~

Vì đây có thể là **cross-site POST**, cookie đặt `SameSite=Lax` thường **không được gửi**. Hệ quả là Portal thiếu session cần cho correlation.

Nếu hệ thống thực sự cần `form_post`, cần đánh giá đồng thời:

1. **Cookie policy:** Có cần `SameSite=None; Secure` cho phiên dùng tại callback hay không?
2. **TLS và browser:** HTTPS có được triển khai đúng? Browser có chặn cookie trong ngữ cảnh cụ thể dù SameSite=None không?
3. **Callback filter:** Spring Security và phiên bản thư viện sử dụng có xử lý được method/form parameters của response mode được chọn không?
4. **CSRF protection:** Filter CSRF có chặn callback POST trước khi filter OAuth2 Login xử lý không?
5. **AuthorizationRequestRepository:** Session và state ban đầu có còn truy cập được không?
6. **Cấu hình IdP:** Provider có chấp nhận và thực sự trả callback theo response mode đã yêu cầu không?

Nếu cần ngoại lệ CSRF cho một **OAuth callback POST** đã được phân tích và xác định chính xác, chỉ giới hạn ngoại lệ vào callback đó, rồi giữ nguyên các kiểm tra `state`, PKCE, nonce và validation của OIDC. Không tắt CSRF cho toàn bộ Portal vì lỗi callback.

**Quan trọng:** `SameSite=None` làm cookie dễ xuất hiện hơn trong các request cross-site theo quy tắc trình duyệt, vì vậy những endpoint dùng cookie để thay đổi trạng thái cần được bảo vệ bằng CSRF token/chính sách phù hợp. Một số trình duyệt còn có cơ chế chống tracking, giới hạn third-party cookie, iframe hoặc webview; `SameSite=None` không bảo đảm vượt qua các giới hạn đó.

Với một Portal thông thường, chọn callback **top-level GET** khi phù hợp thường giảm yêu cầu đặc biệt về session cookie. Tuy nhiên, lựa chọn response mode phải đúng với IdP và mô hình bảo mật đã thống nhất.

## 9. Cấu hình Spring Boot cho session cookie

Ví dụ trong môi trường production, Portal nhận HTTPS ở public endpoint:

~~~yaml
# src/main/resources/application-prod.yml
server:
  forward-headers-strategy: framework
  servlet:
    session:
      timeout: 30m
      cookie:
        name: JSESSIONID
        http-only: true
        secure: true
        same-site: lax
~~~

Ý nghĩa:

- `http-only: true` hạn chế JavaScript đọc cookie.
- `secure: true` yêu cầu cookie được gửi qua HTTPS ở phía browser.
- `same-site: lax` là lựa chọn phổ biến cho callback top-level GET cross-site.
- `timeout: 30m` mô tả cấu hình session timeout của Servlet container; đây không phải thời hạn access token hoặc phiên IdP.
- `forward-headers-strategy: framework` giúp Spring xem thông tin public scheme/host do proxy đáng tin cậy forward, nếu hạ tầng đã cấu hình đúng.

Ở local chạy **HTTP** trực tiếp, cookie Secure có thể không hoạt động như trên HTTPS production; dùng cấu hình local riêng:

~~~yaml
# src/main/resources/application-local.yml
server:
  port: 8080
  servlet:
    session:
      cookie:
        http-only: true
        secure: false
        same-site: lax
~~~

Ví dụ local chỉ phục vụ phát triển trên loopback. Môi trường staging/production phải dùng HTTPS và cấu hình secret, session phù hợp.

Nếu dùng `form_post` và đã xác nhận cần cookie cross-site POST, lựa chọn `same-site: none` trên đúng môi trường phải đi kèm `secure: true`, TLS và bảo vệ CSRF tương ứng. Không đổi toàn bộ môi trường sang `None` theo thói quen nếu callback GET với Lax đã đáp ứng nhu cầu.

### 9.1. Cẩn thận khi sửa Path và Domain

Spring Boot/Servlet container có thể mặc định đặt cookie path theo context path. Đừng tự gán `Path=/` cho mọi ứng dụng nếu Portal được mount tại `/portal` và có ứng dụng khác cùng host.

Khi cần cấu hình path rõ ràng:

~~~yaml
server:
  servlet:
    session:
      cookie:
        path: /portal
~~~

chỉ sử dụng nếu **callback public URL thực sự nằm trong `/portal`** và cách proxy chuyển request vào ứng dụng nhất quán. Tương tự, tránh mở rộng `Domain=.example.test` chỉ để “sửa lỗi cookie” khi callback thực ra dùng đúng host của Portal.

Cookie có phạm vi càng rộng thì càng cần đánh giá nguy cơ xung đột giữa ứng dụng cùng domain và khả năng bị ảnh hưởng từ subdomain khác.

## 10. Cấu hình OIDC Client và SecurityFilterChain tối thiểu

Để thấy quan hệ giữa callback và session, xét client registration có đường dẫn mặc định:

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

`OIDC_CLIENT_SECRET` cần được nạp qua biến môi trường hoặc secret manager. Không đặt secret thật vào Git, browser hoặc frontend bundle.

Lớp security dùng session cho web login:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Spring Security mặc định dùng:

~~~text
URL bắt đầu đăng nhập:
  /oauth2/authorization/company

Callback được OAuth2LoginAuthenticationFilter xử lý:
  /login/oauth2/code/company

Redirect URI template:
  {baseUrl}/login/oauth2/code/{registrationId}
~~~

Trong thiết lập này, **không cần tự tạo controller `@GetMapping("/login/oauth2/code/company")`**; callback do filter xử lý.

Không cấu hình `SessionCreationPolicy.STATELESS` cho chuỗi filter OAuth2 Login dựa vào HTTP session nếu không đồng thời thiết kế lại hoàn chỉnh cơ chế lưu authorization request, SecurityContext và tương quan callback. Với ứng dụng MVC/OIDC login thông dụng, cơ chế session mặc định đáp ứng nhu cầu tốt hơn.

## 11. Reverse proxy tạo ra hai góc nhìn về URL

Khi deploy Portal sau reverse proxy/ingress:

~~~text
Browser
   |
   | HTTPS https://portal.example.test
   v
Reverse proxy / ingress (TLS termination)
   |
   | HTTP http://portal-service:8080
   v
Spring Boot Portal
~~~

Browser chỉ biết địa chỉ public `https://portal.example.test`. Spring Boot có thể chỉ thấy request nội bộ `http://portal-service:8080`.

Nếu ứng dụng dùng:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

và không nhận diện được URL public, Spring Security có thể sinh:

~~~text
http://portal-service:8080/login/oauth2/code/company
~~~

thay vì:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

IdP thường đối chiếu `redirect_uri` với các callback được đăng ký. Địa chỉ nội bộ, scheme HTTP hoặc port sai có thể dẫn đến `redirect_uri_mismatch` trước cả khi IdP gọi callback.

### 11.1. Forwarded headers cho scheme, host, port và prefix

Proxy có thể chuyển các thông tin như:

~~~http
X-Forwarded-Proto: https
X-Forwarded-Host: portal.example.test
X-Forwarded-Port: 443
~~~

Hoặc dùng header chuẩn `Forwarded`, và trong trường hợp có path prefix có thể dùng `X-Forwarded-Prefix` theo hạ tầng.

Phía Spring Boot:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

có thể giúp Servlet request được xem với public scheme/host do proxy tin cậy truyền vào.

**Điều kiện bắt buộc về trust:** proxy ở ranh giới tin cậy cần **loại bỏ/ghi đè forwarded headers do client bên ngoài tự gửi**, đồng thời chỉ forward host hợp lệ. Không coi mọi `X-Forwarded-*` từ Internet là đáng tin: điều đó có thể khiến ứng dụng dựng URL redirect hoặc thông tin bảo mật theo host/scheme do kẻ tấn công chọn.

### 11.2. Secure cookie khi TLS kết thúc ở proxy

Đôi khi backend giao tiếp HTTP với proxy nhưng trình duyệt giao tiếp HTTPS. Điều browser quan tâm là cookie trong phản hồi public có:

~~~http
Set-Cookie: JSESSIONID=<value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

và callback thực tế đi qua HTTPS ở host/path phù hợp.

Để tránh phụ thuộc hoàn toàn vào việc backend tự nhận diện request HTTPS khi TLS kết thúc ở proxy, production thường **chủ động cấu hình `server.servlet.session.cookie.secure=true`**, cùng với forwarded headers đúng và yêu cầu HTTPS từ client.

Đừng tắt `Secure` ở production chỉ vì Spring Boot nhận HTTP nội bộ. Đó là dấu hiệu cần kiểm tra thiết kế TLS termination và forwarded headers, hoặc đặt cookie Secure tường minh.

### 11.3. Context path và path prefix

Giả sử public Portal nằm dưới:

~~~text
https://apps.example.test/portal
~~~

Callback public là:

~~~text
https://apps.example.test/portal/login/oauth2/code/company
~~~

Có ít nhất hai cách triển khai:

**Cách A — Servlet context path `/portal`:**

~~~yaml
server:
  servlet:
    context-path: /portal
~~~

Lúc này, browser gửi path có `/portal`, nhưng Spring Security callback matcher thường được viết theo **đường dẫn bên trong Servlet context**:

~~~text
/login/oauth2/code/*
~~~

**Cách B — Proxy nhận `/portal` rồi strip prefix trước khi forward:**

~~~text
Browser:
  /portal/login/oauth2/code/company

Backend nhận:
  /login/oauth2/code/company
~~~

Ứng dụng phải được cung cấp thông tin public prefix đúng khi dựng `{baseUrl}` và các redirect, đồng thời cookie Path phải tương thích với public URL.

Không nên cấu hình **cả servlet context path và proxy strip/add prefix một cách chồng chéo**. Nếu xuất hiện 404 callback hoặc redirect đến `/portal/portal/login/oauth2/code/...`, hãy phân tích đường dẫn browser gửi, proxy forward và matcher trong Servlet trước khi sửa.

## 12. Đối chiếu redirect URI, callback matcher và cookie

Ba yếu tố này cùng cần đúng:

| Kiểm tra | Ví dụ chuẩn | Nếu sai |
|---|---|---|
| **Redirect URI tại ClientRegistration** | `https://portal.example.test/login/oauth2/code/company` | IdP có thể từ chối callback |
| **Allowed redirect tại IdP** | Cùng URI đầy đủ | Authorization Server báo mismatch |
| **redirectionEndpoint matcher** | `/login/oauth2/code/*` | Spring Security không xử lý callback |
| **Cookie Domain/Path** | Host `portal.example.test`, Path bao trùm callback | Browser không gửi session cookie |
| **Cookie SameSite** | `Lax` với top-level GET callback cross-site | Cookie có thể bị chặn trên request trở về |
| **Cookie Secure và TLS** | HTTPS public + `Secure` | Cookie có thể bị browser từ chối/không gửi |
| **Session store** | Session còn tồn tại và đúng node/store | Không tìm được authorization request |
| **State** | Giá trị callback khớp request đã lưu | Correlation thất bại |

Ví dụ khi muốn đổi callback path thành:

~~~text
https://portal.example.test/auth/callback/company
~~~

cần thay đồng bộ:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            redirect-uri: "{baseUrl}/auth/callback/{registrationId}"
~~~

và:

~~~java
http.oauth2Login(oauth2 -> oauth2
    .redirectionEndpoint(redirection ->
        redirection.baseUri("/auth/callback/*"))
);
~~~

sau đó đăng ký URL công khai chính xác ở IdP. Đồng thời kiểm tra cookie `Path` có bao gồm `/auth/callback/company` hay không.

**Đổi `redirectionEndpoint.baseUri` không tự cập nhật client registration hay cookie Path**. Đây là ba khía cạnh độc lập của cùng một luồng callback.

## 13. Phiên trên nhiều instance: đúng cookie vẫn có thể mất state

Giả sử Portal có hai node:

~~~text
                           +--> Portal A (session A)
Browser -> Load Balancer --|
                           +--> Portal B (session B)
~~~

Luồng xảy ra:

1. Browser bắt đầu login và được định tuyến đến **Portal A**.
2. Authorization request được lưu trong session A.
3. Browser nhận cookie rồi đi đến IdP.
4. Callback quay về load balancer, nhưng lần này được định tuyến đến **Portal B**.
5. Nếu Portal B **không truy cập được cùng dữ liệu session**, request gốc có thể không tìm thấy dù browser đã gửi đúng cookie.

Có hai chiến lược vận hành thông dụng:

| Cách | Mô tả | Lưu ý |
|---|---|---|
| **Session affinity / sticky session** | Cố gắng đưa cùng session về cùng instance | Có thể mất phiên khi node bị thay, restart hoặc scale |
| **Shared session store** | Các instance cùng truy cập một kho session được bảo vệ | Cần thiết kế tính sẵn sàng, quyền truy cập, TTL và bảo vệ dữ liệu nhạy cảm |

**Spring Session** có thể được dùng để lưu session chia sẻ, ví dụ với Redis. Khi đó dữ liệu authorization request và SecurityContext có thể được truy cập từ các node, tùy cách cấu hình repository/serialization và vòng đời session.

Ví dụ dependency của Portal:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Chỉ bổ sung khi dùng Spring Session với Redis:
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ cấu hình runtime cho môi trường có Redis quản lý riêng:

~~~yaml
spring:
  data:
    redis:
      host: ${SESSION_REDIS_HOST}
      port: ${SESSION_REDIS_PORT:6379}
  session:
    redis:
      namespace: employee-portal:sessions
~~~

Ví dụ này chỉ biểu diễn việc kết nối và namespace. Khi triển khai thật phải cung cấp xác thực Redis, TLS, quyền truy cập mạng, chính sách TTL và cơ chế high availability thích hợp theo nền tảng. Không lưu credential Redis trực tiếp trong repository.

**Redis hay shared store không tự sửa các lỗi SameSite, Secure hoặc Path.** Nếu browser không gửi cookie, backend không có session ID để truy cập kho chia sẻ, dù mọi node dùng cùng một Redis.

## 14. Session fixation, session timeout và nhiều tab đăng nhập

### 14.1. Session ID thay đổi sau khi login

Spring Security thường áp dụng biện pháp chống **session fixation** khi xác thực thành công, ví dụ thay session ID. Khi quan sát Network panel, có thể thấy cookie `JSESSIONID` được cập nhật sau callback.

Điều cần kiểm tra là:

- Cookie của phiên **trước callback** được gửi để tìm authorization request.
- Callback được xác minh thành công.
- Sau login, browser nhận và tiếp tục gửi cookie của phiên đã xác thực.

Không gán mọi trường hợp session ID thay đổi là lỗi.

### 14.2. Hết hạn session khi người dùng xác thực lâu

Nếu người dùng ở lại trang IdP quá lâu, HTTP session của Portal có thể hết hạn trước khi callback xảy ra. Khi đó cookie vẫn có thể còn trên browser nhưng backend không còn authorization request, gây lỗi correlation.

Timeout phải cân bằng giữa thời gian người dùng có thể hoàn tất MFA/consent và chính sách bảo vệ session. **Không tăng timeout vô hạn** để né mọi lỗi callback; cần xử lý thông báo lỗi và khả năng bắt đầu lại login.

### 14.3. Nhiều tab hoặc nhiều lần khởi động login

Người dùng có thể mở hai tab cùng khởi động đăng nhập, hoặc nhấn login nhiều lần liên tiếp. Tùy cách `AuthorizationRequestRepository` lưu các request đang chờ, authorization request trước có thể bị thay hoặc callback không tìm thấy giao dịch tương ứng.

Ứng dụng dùng repository tùy chỉnh cần định nghĩa rõ cách lưu **nhiều giao dịch đồng thời**, ràng buộc state với đúng request và khi nào xóa request đã hoàn tất. Không dùng một biến static hoặc một state dùng chung cho tất cả người dùng.

Nếu cùng một callback bị gửi lại sau khi code đã dùng hoặc authorization request đã bị tiêu thụ, login có thể thất bại. Đây là hành vi có thể kỳ vọng của cơ chế bảo vệ chống tái sử dụng.

## 15. SameSite, CSRF, CORS và OIDC state là các vấn đề khác nhau

Các thuật ngữ này đều xuất hiện trong luồng đăng nhập nhưng tác động ở những lớp khác nhau:

| Cơ chế | Nó kiểm soát điều gì? | Vai trò trong callback |
|---|---|---|
| **Cookie SameSite** | Browser có gửi cookie theo ngữ cảnh site/method hay không | Quyết định Portal có nhận session cookie ở callback |
| **CSRF protection** | Ngăn một site khác khiến browser thực hiện thao tác thay đổi trạng thái được xác thực bằng cookie | Quan trọng ở các endpoint nghiệp vụ và callback POST nếu áp dụng |
| **OAuth2 state** | Liên kết authorization response với authorization request đã bắt đầu | Chống nhầm/ghép giao dịch và login CSRF theo thiết kế OAuth |
| **OIDC nonce** | Ràng buộc ID Token với giao dịch xác thực theo điều kiện của OIDC | Bổ sung kiểm tra ở lớp OIDC |
| **PKCE** | Ràng buộc authorization code với code verifier của client khởi tạo | Bảo vệ code exchange |
| **CORS** | Quy định browser có cho JavaScript đọc response của cross-origin fetch/XHR hay không | Không quyết định top-level redirect login theo cách SameSite quyết định cookie |

**Không dùng CORS wildcard để “sửa” cookie không đến ở OIDC callback.** Một top-level redirect từ IdP không hoạt động như fetch/XHR cross-origin. Việc sửa CORS có thể không tác động gì đến SameSite hoặc mất session.

Tương tự, **tắt CSRF toàn cục** không thể khiến browser tự gửi một cookie bị SameSite/Path/Domain chặn. Nếu callback không có session cookie, phải sửa nguyên nhân thuộc browser cookie policy hoặc URL/session architecture.

## 16. Cookie của IdP khác cookie của Portal

Khi người dùng đăng nhập ở IdP, IdP có thể đặt cookie riêng, ví dụ:

~~~text
Host: login.company-idp.test
Cookie: IDP_SESSION=...
~~~

Portal cũng có cookie riêng:

~~~text
Host: portal.example.test
Cookie: JSESSIONID=...
~~~

Hai cookie phục vụ hai chức năng:

- **Cookie IdP** duy trì phiên xác thực hoặc SSO phía nhà cung cấp danh tính.
- **Cookie Portal** xác định phiên đang chờ callback và phiên đăng nhập ứng dụng.

Khi browser được đưa sang IdP, cookie của Portal thường **không được gửi cho IdP**; điều này không phải lỗi. Khi browser quay lại Portal, IdP cookie thường **không được gửi cho Portal**; Portal chỉ cần cookie của chính mình và authorization response hợp lệ.

Do đó, người dùng có thể còn đăng nhập SSO ở IdP nhưng mất session Portal, hoặc đã logout khỏi Portal nhưng IdP session vẫn còn. Chúng là hai vòng đời phiên khác nhau.

## 17. Quan sát request thực tế bằng browser Developer Tools

Cần tìm đúng ranh giới mà cookie hoặc session bị mất. Trong môi trường phát triển/kiểm thử đã được cho phép, mở tab **Network**, bật ghi lại request trước khi nhấn login và kiểm tra lần lượt:

### 17.1. Request bắt đầu authorization

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: portal.example.test
~~~

Ở response chuyển hướng đến IdP, xem:

- Có `Location` đúng authorization endpoint không?
- `redirect_uri` bên trong Location sau decode có đúng URL public không?
- Nếu session được tạo, response có `Set-Cookie` không?
- Cookie có `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain` phù hợp không?
- Browser có thông báo cookie bị chặn hoặc bị từ chối không?

### 17.2. Request callback trở về

Tìm request đến `/login/oauth2/code/company` hoặc callback đã tùy biến. Xem:

- Request dùng **GET** hay **POST**?
- Browser có gửi **session cookie của Portal** không? Chỉ cần xác nhận sự có mặt, không sao chép giá trị.
- Host/scheme/path có giống public callback đã đăng ký không?
- Nếu dùng form POST, SameSite và CSRF đang tương tác ra sao?
- Request có được route tới đúng ứng dụng/filter không?

### 17.3. Kết quả tại server

Với thông tin log đã che dữ liệu nhạy cảm, xác định:

- Spring Security callback filter có xử lý request hay không?
- AuthorizationRequestRepository có tìm được request trước đó không?
- Có lỗi state/correlation hay lỗi đổi code tại token endpoint?
- Nếu chạy nhiều node, callback vào node nào và session data có dùng chung không?

**Không log hoặc đưa vào tài liệu công khai** giá trị `JSESSIONID`, authorization code, state, nonce, PKCE verifier, ID Token, access token, refresh token hoặc client secret. Những dữ liệu đó có thể bị dùng để tấn công phiên hoặc liên kết giao dịch.

### 17.4. Vì sao curl không đủ để kiểm tra SameSite?

Có thể kiểm tra HTTP redirect cơ bản:

~~~bash
curl -i "https://portal.example.test/oauth2/authorization/company"
~~~

Hoặc quản lý cookie trong curl jar khi thử endpoint:

~~~bash
curl -i -c cookies.txt "https://portal.example.test/oauth2/authorization/company"
~~~

Nhưng **curl không thực thi chính sách SameSite theo ngữ cảnh điều hướng của browser như một trình duyệt thật**. Một thử nghiệm curl có gửi cookie thành công không chứng minh cookie sẽ được browser gửi sau cross-site POST/redirect. Khi nghi ngờ SameSite, cần quan sát trình duyệt thật và chính sách cookie của nó. Đừng tải cookie jar chứa session thật lên ticket hoặc repository.

## 18. Tình huống lỗi thường gặp và cách khoanh vùng

| Triệu chứng | Khả năng liên quan | Cần kiểm tra |
|---|---|---|
| IdP báo `redirect_uri_mismatch` | Proxy làm sai scheme/host/prefix, client registration hoặc IdP whitelist sai | Giá trị `redirect_uri` thật trong request sang IdP |
| Browser callback đúng URL nhưng không gửi `JSESSIONID` | SameSite, Secure, Domain, Path hoặc browser policy | Cookie Attributes, request method, Network cookie warnings |
| GET callback cross-site mất cookie khi SameSite=Strict | Strict chặn cookie trong cross-site navigation | Chính sách SameSite; cân nhắc Lax nếu luồng phù hợp |
| POST `form_post` mất cookie khi SameSite=Lax | Cookie không gửi trong cross-site POST | Response mode, SameSite=None+Secure nếu phù hợp, CSRF |
| Cookie có trên request nhưng không tìm được authorization request | Session hết hạn, dữ liệu không có ở node nhận callback, repository không nhất quán | Session TTL, session store, load balancer, repository |
| Callback vào `http://internal-host` hoặc sai hostname | Sai forwarded headers/redirect template | Trusted proxy, `{baseUrl}`, Location |
| Callback bị 404 | Prefix/path bị rewrite hoặc redirectionEndpoint matcher không khớp | Public path, backend path, filter matcher |
| Đăng nhập được ở một node, lỗi khi scale | Session local hoặc affinity không ổn định | Shared session store/affinity |
| Đăng nhập xong vẫn quay lại trang login | Session cookie mới không lưu/gửi, SecurityContext không được duy trì | Cookie sau login, session fixation, session store |
| Callback bị CSRF 403 | POST callback bị filter CSRF chặn | Response mode và chính sách CSRF scoped cho endpoint |
| Lỗi `invalid_state` | Session/request gốc không tồn tại hoặc state không khớp | Cookie, session, thời hạn, nhiều tab, callback bị dùng lại |
| Token endpoint trả `invalid_client` | Sai client secret/phương thức xác thực | Client registration và secret runtime, không phải SameSite |
| Token endpoint trả `invalid_grant` | Code hết hạn/đã dùng, PKCE hoặc redirect URI không nhất quán | Bước code exchange và cấu hình IdP |

Không suy ra nguyên nhân chỉ dựa vào mã HTTP như 302, 401, 403 hoặc 404. Cùng một mã phản hồi có thể đến từ entry point, CSRF filter, callback filter, controller hoặc reverse proxy.

## 19. Ba kịch bản thực hành

### Kịch bản A: callback GET với SameSite=Lax

Thiết lập:

~~~text
Portal:  https://portal.example.test
IdP:     https://login.company-idp.test
Cookie:  Secure; HttpOnly; SameSite=Lax; Path=/
Callback method: GET
~~~

Khi IdP trả redirect về Portal bằng **top-level GET**, browser thường gửi cookie session của Portal. Nếu login vẫn thất bại, tập trung tiếp vào **state**, session store, routing và token exchange thay vì tự đổi cookie sang None.

### Kịch bản B: callback form_post với SameSite=Lax

Thiết lập:

~~~text
Portal:  https://portal.example.test
IdP:     https://login.company-idp.test
Cookie:  Secure; HttpOnly; SameSite=Lax; Path=/
Callback method: POST (cross-site form_post)
~~~

Browser thường không gửi cookie trong cross-site POST. Spring Security có thể không tìm thấy authorization request gốc. Hướng xử lý là **xác nhận yêu cầu response mode**, đánh giá SameSite=None+Secure và xử lý CSRF callback có phạm vi, cùng với các biện pháp bảo mật tương ứng.

### Kịch bản C: HTTPS public, HTTP nội bộ

Thiết lập:

~~~text
Public callback:
  https://portal.example.test/login/oauth2/code/company

Backend URL:
  http://portal-service:8080

Sai redirect_uri được sinh:
  http://portal-service:8080/login/oauth2/code/company
~~~

Đây là vấn đề **public URL/proxy**, không phải SameSite. Cần kiểm tra forwarded headers, `server.forward-headers-strategy`, allowlist hostname và đăng ký redirect URI chính xác ở IdP. Sau khi sửa URI, vẫn cần quan sát session cookie trong callback.

## 20. Bài tập kiểm tra hiểu biết

**Bài 1.** Portal có cookie:

~~~http
Set-Cookie: JSESSIONID=...; Path=/portal; Secure; HttpOnly; SameSite=Lax
~~~

Nhưng IdP chuyển browser về:

~~~text
https://portal.example.test/login/oauth2/code/company
~~~

Hỏi: Vì sao cookie không đến, dù SameSite=Lax có hỗ trợ top-level GET callback?

**Gợi ý:** Cookie `Path=/portal` không bao phủ đường dẫn `/login/oauth2/code/company`. Cần thiết kế đúng path công khai và cookie path/context path, không chỉ thay SameSite.

**Bài 2.** Portal đang dùng callback GET và cookie SameSite=Strict. IdP ở site khác. Đăng nhập trở về báo thiếu authorization request.

**Gợi ý:** Strict thường chặn cookie khi browser điều hướng cross-site về Portal; Lax phù hợp hơn với top-level GET callback trong trường hợp thông dụng. Vẫn phải xác minh Domain, Path, Secure và session store.

**Bài 3.** Production có hai node; request bắt đầu authorization vào node A, callback vào node B. Browser gửi đúng JSESSIONID nhưng authorization request không tìm thấy.

**Gợi ý:** Phải kiểm tra cơ chế chia sẻ session hoặc session affinity. SameSite không giải quyết dữ liệu session chỉ tồn tại trong node A.

**Bài 4.** Browser đang nhận đúng cookie ở callback, nhưng IdP báo `invalid_redirect_uri` ngay tại bước khởi tạo.

**Gợi ý:** Xem `redirect_uri` do Portal sinh, public scheme/host/prefix được forward, và URI đã đăng ký ở IdP. Lỗi xảy ra trước khi browser quay về callback.

**Bài 5.** Nhóm kỹ thuật tắt CSRF trên toàn bộ Portal để hỗ trợ `response_mode=form_post`, nhưng browser vẫn không gửi JSESSIONID.

**Gợi ý:** CSRF filter không điều khiển việc browser gửi cookie. Phải kiểm tra SameSite, Secure, HTTPS, Domain/Path và chính sách browser; sau đó thiết kế xử lý CSRF có phạm vi phù hợp.

## 21. Tổng kết kiến trúc

Trong callback OAuth 2.0/OIDC trên Spring Security Servlet, **URI đúng chỉ là một phần của điều kiện thành công**. Browser còn phải gửi **session cookie phù hợp**, Portal phải truy cập được **authorization request đã lưu**, và Spring Security phải đối chiếu được **state** trước khi đổi authorization code lấy token.

Với callback **top-level GET**, `SameSite=Lax` thường cho phép cookie quay về từ IdP khác site. Với callback **cross-site POST** như `form_post`, có thể phải thiết kế `SameSite=None; Secure` kết hợp bảo vệ CSRF và các chính sách trình duyệt khác. Trong cả hai trường hợp, **HttpOnly, Secure, Path, Domain, thời hạn session và session store** đều cần được hiểu đúng.

Khi Portal chạy sau reverse proxy, URL public, forwarded headers, cookie và callback matcher phải cùng mô tả một đường đi: browser thấy **HTTPS và hostname công khai**, proxy chuyển tiếp có kiểm soát, và backend xử lý đúng path. Khi triển khai nhiều replica, phiên phải được định tuyến hoặc lưu chia sẻ phù hợp. Nắm được các ranh giới này giúp chẩn đoán chính xác lỗi callback và xây dựng luồng đăng nhập liên kết ổn định, an toàn giữa local, staging và production.
