# Bản đồ các cách đăng nhập: mật khẩu, phiên, token, chứng thư và passkey

**Module:** Spring Security – authentication. **Phạm vi:** Tổng quan về cách chứng minh danh tính, duy trì trạng thái đăng nhập và xác thực từng request.

## 1. Năm tên gọi nhưng không cùng một tầng

**Authentication (AuthN)** xác minh chủ thể gửi yêu cầu là ai dựa trên một bằng chứng đáng tin. **Authorization (AuthZ)** quyết định chủ thể đó có quyền thực hiện hành động cụ thể hay không. Đăng nhập thành công không đồng nghĩa được phép truy cập mọi tài nguyên.

Những khái niệm trong tiêu đề thực ra nằm ở ba tầng:

| Khái niệm | Tầng chính | Ý nghĩa | Thường kết hợp với |
| --- | --- | --- | --- |
| **Mật khẩu (password)** | Bằng chứng xác thực ban đầu | Người dùng chứng minh biết một bí mật; server kiểm tra với hash đã lưu | Session hoặc token sau đăng nhập |
| **Phiên (session)** | Duy trì kết quả xác thực | Client giữ session ID; server giữ/truy xuất trạng thái đăng nhập | Mật khẩu, passkey, đăng nhập qua IdP |
| **Token** | Trình bằng chứng đã được cấp | Client gửi bearer access token tới API; server xác minh token | Mật khẩu, passkey, OAuth2/OIDC hoặc luồng máy |
| **Chứng thư X.509 (certificate)** | Chứng minh bằng khóa mật mã ở lớp TLS | Trong mTLS, client chứng minh sở hữu private key đi với chứng thư đáng tin | Danh tính service, hệ thống nội bộ; đôi khi session |
| **Passkey (WebAuthn/FIDO2)** | Bằng chứng xác thực ban đầu | Authenticator ký challenge gắn với website; server xác minh public key | Session hoặc token sau đăng nhập |

Không nên hỏi “chọn password hay session?”: **password** trả lời cách kiểm tra người dùng ban đầu, còn **session** trả lời cách nhận diện người dùng ở request kế tiếp. Tương tự, passkey thường **không thay thế** session/token; nó thay thế hoặc bổ sung **bước chứng minh danh tính**.

~~~text
Bước 1: CHỨNG MINH DANH TÍNH
        password / passkey / client certificate / IdP
                           |
                           v
Bước 2: XÁC THỰC VÀ GẮN DANH TÍNH ỨNG DỤNG
        principal + authorities -> Authentication -> SecurityContext
                           |
                           v
Bước 3: REQUEST TIẾP THEO
        session cookie / bearer access token / mTLS
                           |
                           v
Bước 4: AUTHORIZATION
        tài nguyên được cho phép hay bị từ chối?
~~~

Tất cả các cách truyền credential đều cần kênh TLS đúng chuẩn. **HTTPS thông thường xác thực server đối với client** và bảo mật đường truyền; nó không tự động đăng nhập người dùng.

## 2. Mật khẩu: yếu tố “điều người dùng biết”

Luồng form login phổ biến trong Spring Security Servlet:

1. Browser nhận form qua HTTPS; người dùng nhập username/email và password.
2. Request đăng nhập đi vào chuỗi security filter. Với username-password thông thường, bộ lọc tạo một Authentication chưa được xác thực rồi chuyển đến AuthenticationManager.
3. AuthenticationManager (thường là ProviderManager) chọn AuthenticationProvider phù hợp. DaoAuthenticationProvider có thể nạp người dùng bằng UserDetailsService và dùng PasswordEncoder để kiểm tra password.
4. Nếu bằng chứng và trạng thái tài khoản hợp lệ, Authentication được đánh dấu đã xác thực và chứa principal cùng authorities. Nếu không, trả lỗi không làm lộ thông tin tài khoản.
5. Cơ chế hậu đăng nhập có thể thiết lập session cookie hoặc cấp token; các request tiếp theo dùng cơ chế đã chọn để xác thực lại danh tính theo cách phù hợp.

**Lưu trữ:** Không lưu plaintext password; không mã hóa có thể giải mã để lấy lại. Sử dụng password-hashing chuyên dụng có salt như Argon2id/bcrypt với cấu hình đủ mạnh, nâng cấp tham số khi cần, và không nhầm với SHA-256 trần. Thiết kế giới hạn thử đăng nhập, giám sát credential stuffing, luồng reset password và MFA; đừng làm lộ “username tồn tại/không tồn tại” qua lỗi.

**HTTP Basic là một biến thể khác:** Header Authorization mang username/password được biểu diễn Base64 trong **mỗi request**, khác browser form + session. Base64 không phải mã hóa; bắt buộc dùng HTTPS, tránh dùng Basic ở môi trường không phù hợp.

**Nhược điểm chính của mật khẩu:** có thể bị đoán, dùng lại và bị đánh cắp qua phishing. MFA giảm tác động, còn passkey/WebAuthn cung cấp hướng đăng nhập chống phishing tốt hơn.

## 3. Phiên (session): giữ kết quả đăng nhập ở server

Session thường dành cho các ứng dụng browser sử dụng cookie. Khi xác thực ban đầu thành công, server tạo một phiên chứa/truy xuất SecurityContext. Browser nhận **session ID ngẫu nhiên** (ví dụ cookie JSESSIONID), rồi tự động gửi cookie trong request sau.

~~~text
POST /login + form
   -> xác thực password thành công
   -> tạo/cập nhật session phía server
   <- Set-Cookie chứa session ID

GET /profile + Cookie chứa session ID
   -> server tìm session tương ứng
   -> khôi phục SecurityContext/Authentication
   -> kiểm tra quyền -> controller hoặc từ chối

POST /logout
   -> vô hiệu hóa phiên server-side và xử lý cookie
~~~

**Session ID là một bí mật dạng bearer:** ai có ID hợp lệ có thể chiếm phiên dù không biết password. ID phải khó đoán, được tạo bằng nguồn ngẫu nhiên an toàn, thay đổi phù hợp sau khi login để chống session fixation, có giới hạn idle/absolute timeout, và vô hiệu hóa được khi logout hoặc nghi ngờ rủi ro.

Với cookie, cần kiểm soát **HttpOnly**, **Secure**, **SameSite**, Domain/Path và HTTPS/HSTS theo kiến trúc. HttpOnly cản JavaScript đọc cookie nhưng không ngăn mọi hậu quả của XSS. Vì browser tự động đính cookie, request thay đổi trạng thái thường cần **CSRF protection**; SameSite hỗ trợ giảm CSRF nhưng không luôn thay thế CSRF token. Kiểm soát cả concurrent sessions và hành vi khi reset password, khóa tài khoản.

**Spring Security Servlet:** SecurityContextRepository đọc/lưu SecurityContext qua request. Khi tự viết custom authentication filter/controller, chỉ đặt Authentication vào SecurityContextHolder của request hiện tại có thể chưa đủ để duy trì login: cần lưu context theo hợp đồng của phiên bản Spring Security. Với form login chuẩn, nên dùng cơ chế Spring Security hỗ trợ thay vì tự xử lý session.

**Khi nên dùng:** web app cùng backend, server-rendered app, dashboard nội bộ hoặc browser + BFF cần session tập trung, logout/thu hồi nhanh, kiểm soát vòng đời phía server. Nếu dùng nhiều instance, cần cân nhắc kho session dùng chung, tính sẵn sàng và consistency.

## 4. Token: chứng nhận quyền truy cập cho API

**Access token** là bằng chứng do bên phát hành tin cậy cấp cho client. Với cơ chế Bearer, client gắn token trong header Authorization của request HTTPS, resource server kiểm tra token rồi xác định danh tính/quyền. Token có thể được cấp sau một lần đăng nhập bằng password, passkey hoặc federation; cũng có luồng service-to-service không có người dùng.

~~~text
Client -- đăng nhập/ủy quyền --> Authorization server
Client <-- access token ------- Authorization server
Client -- Bearer token -------> Resource server
                              -> validate token
                              -> tạo Authentication cho request
                              -> authorize -> kết quả
~~~

Hai loại thường gặp:

| Kiểu token | Kiểm chứng | Đánh đổi |
| --- | --- | --- |
| **JWT access token** | Kiểm tra chữ ký, thuật toán được phép, issuer, audience, exp/nbf và chính sách claim | Có thể kiểm tra cục bộ; thu hồi tức thời trước hạn cần cơ chế bổ sung |
| **Opaque access token** | Thường introspection với authorization server hoặc tra trạng thái tin cậy | Dễ tham chiếu trạng thái trung tâm; phụ thuộc chi phí/khả dụng hệ thống kiểm chứng |

Một JWT **đọc/giải mã được** không đồng nghĩa **đáng tin**. Đừng chỉ decode payload rồi chấp nhận role. Server cần kiểm tra chữ ký bằng khóa tin cậy, algorithm policy, **iss** (nơi phát hành), **aud** (API nhận token), thời gian và quyền hạn đúng ngữ cảnh. **ID token OIDC** dùng để client hiểu kết quả xác thực người dùng, không mặc nhiên là **access token** hợp lệ của một API. Scope có thể được ánh xạ thành authorities nhưng vẫn cần kiểm tra quyền nghiệp vụ.

Token bearer bị lộ có thể bị **replay**. Thiết kế access token ngắn hạn, quyền tối thiểu, kho lưu an toàn, xử lý refresh token/rotation, revocation, thay khóa, logout và token bị đánh cắp. Token nằm trong cookie tự gửi khiến ứng dụng vẫn phải đánh giá CSRF; token lưu nơi JavaScript đọc được, đặc biệt localStorage, dễ bị chiếm khi có XSS. Một **backend-for-frontend** có thể giữ token ở server và chỉ cấp cookie phiên tới browser khi hợp lý.

Resource Server của Spring Security có cơ chế xử lý bearer JWT/opaque token. **Resource server xác minh token**; cấu hình resource server đơn thuần **không tự phát hành** token. Phát hành thuộc authorization server hoặc cơ chế cấp credential riêng.

**Stateless** nghĩa là API không cần HTTP session lưu Authentication giữa các request; mỗi request tự mang chứng cứ và được kiểm tra. Nhưng JWT không làm toàn hệ thống tuyệt đối không trạng thái: khóa, danh sách thu hồi, quyền đang thay đổi và refresh token vẫn có thể có state.

## 5. Chứng thư X.509: danh tính mật mã trong mutual TLS

Cần phân biệt hai trường hợp:

- **TLS/HTTPS thông thường:** browser/client kiểm tra certificate của **server**; mới xác thực danh tính server.
- **mTLS (mutual TLS):** server yêu cầu **client certificate**. Client chứng minh sở hữu private key gắn với certificate trong TLS handshake; server xác minh chứng thư và chính sách trust.

Luồng:

~~~text
Service / client sở hữu certificate + private key
    -> TLS handshake, server yêu cầu client certificate
    -> xác minh private-key possession và chuỗi tin cậy
    -> Spring Security X.509 nhận danh tính client đã được TLS xác minh
    -> ánh xạ certificate subject/SAN vào principal + authorities
    -> authorize request
~~~

**Certificate hợp lệ về kỹ thuật chưa đồng nghĩa có quyền hệ thống.** Phải xác minh CA/trust anchor đúng, thời hạn, key usage/extended key usage phù hợp, danh tính thực của chủ thể và chính sách revocation nếu hệ thống yêu cầu. Sau đó mới ánh xạ principal và cấp quyền tối thiểu. Cần có kế hoạch rotation/renewal, bảo vệ private key, cấp lại và thu hồi.

**Cẩn thận với gateway:** Nếu TLS kết thúc ở reverse proxy/load balancer, app không được tin header tùy ý client gửi mang tên subject/certificate. Gateway phải xác thực thực sự, loại bỏ header giả và chuyển danh tính qua hop tin cậy được bảo vệ. Đây là một trust boundary rõ ràng.

**Khi nên dùng:** service-to-service, client doanh nghiệp, thiết bị được quản lý, workload identity nơi có PKI và quy trình vận hành certificate tốt. Với người dùng browser đại chúng, cài đặt và thu hồi client certificate thường khó vận hành hơn password/passkey.

## 6. Passkey/WebAuthn: xác thực bằng khóa công khai

Passkey dùng **WebAuthn/FIDO2**. Authenticator tạo khóa riêng và khóa công khai; dịch vụ chỉ cần lưu public key và credential metadata. Private key không được gửi tới server. Trình duyệt bảo đảm credential gắn với **RP ID/origin** đúng, qua đó chống kiểu phishing đánh cắp mật khẩu và dùng credential ở tên miền giả.

**Giai đoạn đăng ký credential:**

1. Server khởi tạo một phiên đăng ký sau khi đã xác minh tài khoản bằng cách đáng tin, phát challenge ngẫu nhiên cùng RP ID và chính sách.
2. Browser gọi WebAuthn create; authenticator tạo credential mới, có thể yêu cầu PIN/sinh trắc học/cử chỉ xác nhận.
3. Server xác minh response, challenge, origin, RP ID và các chính sách, sau đó lưu credential ID + public key liên kết với tài khoản.

**Giai đoạn đăng nhập:**

1. Server phát challenge ngẫu nhiên mới, có thời gian sống giới hạn và không được tái sử dụng.
2. Browser gọi WebAuthn get với thông tin RP/challenge; authenticator xác nhận người dùng theo yêu cầu và ký dữ liệu với private key.
3. Server tìm public key đã đăng ký, kiểm tra chữ ký, challenge, origin, RP ID, trạng thái user presence/user verification theo chính sách và kiểm soát replay.
4. Nếu hợp lệ, ứng dụng tạo Authentication, sau đó có thể cấp **session cookie** hoặc **access token**.

Sự bảo đảm chống phishing đến từ **ràng buộc mật mã với website** và challenge, không phải gửi dấu vân tay/khuôn mặt lên server. PIN/sinh trắc học thường chỉ mở khóa thao tác cục bộ trên authenticator. Passkey có thể **đồng bộ giữa thiết bị** hoặc **gắn phần cứng riêng**; đừng mặc định mọi passkey đều không thể đồng bộ.

Vẫn phải bảo vệ: luồng recovery khi mất thiết bị, đăng ký passkey mới, thay đổi tài khoản, rủi ro session/token bị đánh cắp sau khi login và cấu hình HTTPS/secure context. Một cổng khôi phục quá yếu có thể làm vô hiệu lợi thế chống phishing của passkey.

**Spring Security** có hỗ trợ WebAuthn/passkeys với cấu hình và dependency phụ thuộc phiên bản; cần đối chiếu tài liệu của phiên bản dự án. Với session store phân tán và xác minh người dùng bắt buộc, luôn áp dụng bản vá bảo mật mới phù hợp để tránh các lỗi triển khai đã được công bố.

## 7. Bản đồ ghép thực tế và lựa chọn

| Trường hợp | Cách ghép phù hợp thường gặp | Kiểm soát trọng tâm |
| --- | --- | --- |
| Website server-rendered | Password **hoặc passkey** → session cookie | CSRF, session fixation, logout, timeout, MFA/step-up |
| Browser SPA cùng backend | Password/passkey/IdP → BFF hoặc backend session | Cookie SameSite, CSRF, CORS, XSS, bảo vệ token phía server |
| Mobile và public API | Luồng xác thực → access token → resource server kiểm tra bearer | Issuer/audience, scope, token lifetime, refresh, storage |
| Service-to-service | Client cert mTLS và/hoặc access token cho workload | PKI, trust boundary, key rotation, policy quyền tối thiểu |
| Website cần chống phishing | Passkey → session hoặc token | RP ID/origin, recovery, device enrollment, session protection |

~~~text
[BROWSER]
   |-- password hoặc WebAuthn passkey --> [Spring Security AuthN]
   |                                         |
   |                                         +--> Authentication
   |                                         +--> server session
   +-- cookie session ---------------------> [Web backend]
                                             +--> AuthZ từng request

[MOBILE / API CLIENT]
   |-- xác thực theo flow được hỗ trợ --> [Authorization Server]
   +-- nhận access token -----------------+
   +-- Bearer access token -----------------> [Resource Server]
                                              +--> validate + AuthZ

[SERVICE A có client certificate] -- mTLS --> [Gateway / Service B]
                                               +--> identity mapping + AuthZ
~~~

Đừng chọn một công nghệ chỉ vì “microservice là phải JWT” hay “passkey không cần cookie”. Lựa chọn bắt đầu từ **ai gọi hệ thống**, **ai xác thực ban đầu**, **ai giữ trạng thái qua request**, **mức thu hồi/step-up**, và **ranh giới tin cậy**.

## 8. Các thành phần Spring Security nằm ở đâu?

Đối với **Servlet/Spring MVC**:

~~~text
HTTP request
 -> FilterChainProxy / SecurityFilterChain
 -> bộ lọc hoặc cơ chế Authentication phù hợp
 -> AuthenticationManager -> AuthenticationProvider (nếu cần)
 -> SecurityContext chứa Authentication
 -> AuthorizationManager kiểm tra quyền
 -> Controller hoặc 401/403/redirect tùy tình huống
~~~

- **Authentication:** kết quả hoặc yêu cầu xác thực, chứa principal và GrantedAuthority.
- **AuthenticationManager/ProviderManager:** điều phối provider có khả năng xác thực loại credential tương ứng.
- **AuthenticationProvider:** kiểm chứng bằng chứng (ví dụ password hoặc JWT), không tự quyết định mọi quyền nghiệp vụ.
- **SecurityContext/SecurityContextHolder:** mang danh tính trong luồng xử lý request; với Servlet thông thường liên quan ThreadLocal.
- **SecurityContextRepository:** đọc/lưu context qua request nếu dùng mô hình persistence.
- **AuthenticationEntryPoint:** yêu cầu client xác thực khi chưa đăng nhập, ví dụ redirect login hoặc 401.
- **AuthorizationManager:** thực thi quyết định được phép/không được phép; thiếu quyền thường dẫn tới 403.

**Ví dụ Java/Spring Boot Servlet:** lớp cấu hình này mô tả **form password + session**. Nó phải là một phần trong ứng dụng Spring Boot có starter web và security, controller và điểm vào ứng dụng; riêng file này **không** phải chương trình Java độc lập chạy bằng javac/java. User in-memory và mật khẩu tĩnh chỉ để học tập:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
                .password(encoder.encode("demo-only-change-this-secret"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

Nếu ứng dụng có endpoint được bảo vệ, browser chưa đăng nhập sẽ được chuyển tới trang login mặc định; sau xác thực có thể tiếp tục với session. Lớp cấu hình không có stdout riêng hay endpoint tự sinh ngoài những cơ chế bảo mật đã bật. Không hard-code secret của tài khoản thật và không giữ user demo trong sản phẩm.

Với API nhận JWT, hướng cấu hình là **OAuth2 Resource Server**, JwtDecoder/validator và issuer/audience chuẩn; nếu API **chỉ** nhận bearer header và không dùng browser cookie có thể chọn SessionCreationPolicy.STATELESS. Không sao chép cấu hình tắt CSRF từ API bearer sang trang dùng session cookie.

Với **Reactive/WebFlux**, các lớp tương ứng là SecurityWebFilterChain, ServerHttpSecurity và ReactiveAuthenticationManager; reactive security context không hoạt động giống Servlet ThreadLocal. Không trộn cấu hình Servlet và Reactive.

## 9. Các nhầm lẫn gây lỗi bảo mật

1. **Password đồng nghĩa session:** sai; password là credential, session là cách duy trì authentication.
2. **Session cookie chứa luôn password:** thông thường sai; cookie mang session identifier, máy chủ giữ trạng thái.
3. **JWT decode được tức là tin được:** sai; phải validate chữ ký, issuer, audience, thời gian và chính sách.
4. **JWT luôn mã hóa dữ liệu:** sai; JWT ký không mặc nhiên giấu payload khỏi người đọc.
5. **ID token OIDC có thể dùng thay access token của API:** sai; khác mục đích và đối tượng nhận.
6. **Bearer token lộ nhưng không nguy hiểm vì sắp hết hạn:** sai; token còn hiệu lực có thể bị replay.
7. **JWT ở cookie thì không cần CSRF:** sai; browser có thể tự gửi cookie khi bị lừa.
8. **HttpOnly ngăn mọi XSS:** sai; nó chủ yếu ngăn script trực tiếp đọc cookie.
9. **Passkey là dấu vân tay được gửi lên backend:** sai; backend kiểm chứng chữ ký/public key.
10. **Passkey loại bỏ mọi nguy cơ chiếm phiên:** sai; sau WebAuthn, cookie/token vẫn có thể bị đánh cắp.
11. **HTTPS certificate của server là xác thực user:** sai; cần mTLS hoặc login khác cho client identity.
12. **Header client-certificate do browser tự khai có thể tin:** sai; phải dựa vào TLS/gateway đáng tin.
13. **Xác thực thành công đồng nghĩa có quyền admin:** sai; AuthZ luôn tách khỏi AuthN.
14. **Stateless luôn nhanh/an toàn hơn:** không mặc định; cần phân tích revocation, key management và trust.
15. **Tắt CSRF là cách sửa mọi lỗi 403 khi POST:** sai; trước hết kiểm tra mô hình cookie và CSRF token.

## 10. Bài tập tự kiểm tra tư duy

**Câu 1.** Người dùng dùng passkey đăng nhập rồi nhận cookie session. Request tiếp theo có phải ký WebAuthn mỗi lần?  
**Đáp:** Thông thường không. Server dựa vào session còn hạn; thao tác nhạy cảm có thể yêu cầu xác thực bổ sung.

**Câu 2.** API nhận JWT chứa role ADMIN trong payload. Đã đủ để cấp quyền admin?  
**Đáp:** Không. Phải xác minh token hợp lệ cho API này, chuyển claim thành authorities đúng chính sách và kiểm tra authorization.

**Câu 3.** TLS tại gateway xác minh client certificate hợp lệ. Backend được nhận đại header “X-Client-User: admin” từ Internet?  
**Đáp:** Không. Gateway phải lọc header tự khai, truyền danh tính đã xác minh qua kênh được tin, backend kiểm quyền.

**Câu 4.** Bảo vệ website dùng cookie session bằng HttpOnly và SameSite đã chắc chắn không có CSRF?  
**Đáp:** Không. Cần đánh giá CSRF theo hành vi gửi cookie và bảo vệ request thay đổi trạng thái.

**Câu 5.** Doanh nghiệp muốn login chống phishing nhưng cần logout tức thời trên browser: kết hợp gì?  
**Đáp:** Passkey/WebAuthn cho xác thực ban đầu và session do server kiểm soát, kèm lifecycle, CSRF và AuthZ phù hợp.

## 11. Nguồn học sâu

- [Spring Security: Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html) — manager, provider, principal, security context.
- [Spring Security: Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html) — đăng nhập bằng form và filter.
- [Spring Security: Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html) — SecurityContextRepository, persistence, session.
- [Spring Security: JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html) — JWT validation và claims.
- [Spring Security: X.509 Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/x509.html) — client certificate.
- [Spring Security: Passkeys](https://docs.spring.io/spring-security/reference/servlet/authentication/passkeys.html) và [MDN: Passkeys](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys) — WebAuthn, challenge, RP/origin.
- [OWASP: Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html) và [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet) — kiểm soát rủi ro thực tế.

**Điều cần nhớ:** Cách **chứng minh danh tính**, cách **mang kết quả xác thực qua nhiều request** và cách **xác định quyền** là ba quyết định kiến trúc khác nhau; kết hợp đúng chúng mới tạo luồng đăng nhập an toàn.