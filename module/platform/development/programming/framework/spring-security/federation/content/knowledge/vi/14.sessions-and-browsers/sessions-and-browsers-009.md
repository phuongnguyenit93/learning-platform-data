# Giới hạn cookie bên thứ ba và ảnh hưởng tới đăng nhập hoặc đăng xuất qua trình duyệt

Trong **Spring Security federation**, trình duyệt giữ vai trò trung gian vận chuyển thông điệp giữa ứng dụng **Service Provider (SP/Relying Party)** và **Identity Provider (IdP/Asserting Party)**. Trình duyệt cũng giữ cookie phiên của từng website. Vì thế một luồng SAML 2.0 có chữ ký và cấu hình IdP hoàn toàn chính xác vẫn có thể thất bại chỉ vì **cookie không được gửi ở bước quay về**, hoặc **iframe không được phép đọc/ghi cookie của website đang được nhúng**.

Bài học này giải thích chính xác hai cơ chế thường bị gộp làm một:

1. **Third-party cookie blocking/partitioning:** trình duyệt hạn chế cookie của một website khi website đó xuất hiện **như thành phần nhúng** bên trong website khác, chẳng hạn IdP chạy trong iframe của SP hoặc SP nhận thông điệp logout trong iframe của IdP.
2. **`SameSite`:** thuộc tính của từng cookie quy định khi nào cookie được gửi theo tính chất *same-site/cross-site* của request. **Cross-site top-level POST** từ IdP về SAML Assertion Consumer Service (**ACS**) có thể làm cookie `SameSite=Lax` không được gửi, dù request không nằm trong iframe.

**Kết luận quan trọng:** đặt `SameSite=None; Secure` có thể giúp session cookie đi theo một **cross-site POST** hợp lệ, nhưng **không tự vô hiệu hóa chính sách chặn third-party cookie** của Safari, Firefox hoặc chế độ bảo vệ của Chrome. Thiết kế bền vững phải ưu tiên đăng nhập bằng **top-level redirect**, giữ request/session correlation an toàn và không phụ thuộc vào iframe ẩn để khẳng định Single Logout đã hoàn tất.

## 1. Các khái niệm: origin, site, first-party và third-party

Giả sử hai bên liên kết:

~~~text
SP Portal:
https://portal.example.com

IdP:
https://login.partner-b.example

ACS của SP:
https://portal.example.com/login/saml2/sso/partner-b

SAML2 start của SP:
https://portal.example.com/saml2/authenticate/partner-b

SAML2 SLO của SP:
https://portal.example.com/logout/saml2/slo
~~~

Tên miền `.example` là địa chỉ dùng trong ví dụ, không thể sử dụng làm IdP/SP production.

| Khái niệm | Giải thích | Dễ nhầm với |
| --- | --- | --- |
| **Origin** | Scheme + hostname + port; ví dụ `https://portal.example.com:443` | *Site* không nhất thiết trùng origin |
| **Site** | Thường dựa trên scheme + registrable domain (schemeful site) | Không đồng nghĩa full hostname |
| **First-party/top-level context** | Website đang ở ngữ cảnh trang trên cùng của tab/cửa sổ | Không có nghĩa mọi request từ trang đó là same-site |
| **Third-party/embedded context** | Một site khác được nhúng trong trang top-level, ví dụ `iframe src=https://idp.example` | Không phải mọi cross-site redirect đều là iframe |
| **Session cookie** | Cookie tham chiếu trạng thái HTTP session, ví dụ `JSESSIONID` hoặc `SESSION` | Không phải SAML Assertion hay `RelayState` |
| **`SameSite`** | Chỉ dẫn browser có gửi cookie ở request same-site/cross-site hay không | Không phải CORS, cũng không phải SAML signature |
| **Third-party cookie blocking** | Chính sách privacy của browser với cookie trong third-party context | Không thể sửa hoàn toàn chỉ bằng `SameSite=None` |
| **Storage partitioning** | Tách cookie/storage theo *top-level site* | Không duy trì một IdP session toàn cầu ở mọi site nhúng |
| **`HttpOnly`** | JavaScript của trang không đọc được cookie | Không cản browser tự gửi cookie trong HTTP request |
| **`Secure`** | Cookie chỉ gửi qua HTTPS (với ngoại lệ localhost của một số browser) | Không thay cho TLS đúng tại reverse proxy |

### Same-origin và same-site không giống nhau

Ví dụ `https://app.company.example` và `https://idp.company.example` là **khác origin** vì hostname khác, nhưng thường **same-site** vì chung registrable domain và scheme HTTPS. Dù request same-site, cookie đặt **host-only** bởi `app.company.example` cũng **không** được gửi tới `idp.company.example` chỉ vì same-site. Cookie còn bị giới hạn bởi `Domain`, `Path`, `Secure` và trạng thái lưu trữ.

Ngược lại, `https://portal.example.com` tới `https://login.partner-b.example` rõ ràng là **cross-site**; `SameSite=Lax/Strict/None` ảnh hưởng trực tiếp request quay về SP.

**Đừng dùng việc hai miền cùng do một doanh nghiệp sở hữu làm bằng chứng chúng same-site.** Browser dùng quy tắc domain/scheme, không đọc hợp đồng tổ chức.

## 2. SAML Web Browser SSO sử dụng cookie ở đâu?

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as SP Portal
    participant IdP as IdP B
    B->>SP: GET /reports
    SP-->>B: Set-Cookie JSESSIONID (state trước SSO)
    SP-->>B: Redirect tới /saml2/authenticate/partner-b
    B->>SP: GET /saml2/authenticate/partner-b
    SP->>SP: Tạo AuthnRequest, lưu ID/RelayState trong session
    SP-->>B: Redirect/POST AuthnRequest tới IdP
    B->>IdP: Request tới IdP, dùng cookie IdP theo context
    IdP->>IdP: Xác thực hoặc sử dụng IdP session hiện có
    IdP-->>B: Form POST SAMLResponse
    B->>SP: POST /login/saml2/sso/partner-b
    SP->>SP: Khôi phục session + AuthnRequest, kiểm SAMLResponse
    SP-->>B: Authentication thành công hoặc lỗi
~~~

Có hai bộ cookie **khác nhau**:

- **Cookie của SP:** giúp Spring lấy đúng `HttpSession`/`SecurityContext` và `AuthnRequest` đã lưu trước khi đi IdP.
- **Cookie của IdP:** giúp IdP nhận ra user đã có phiên và có thể cấp SSO mà không bắt nhập mật khẩu lại.

Một cookie IdP bị thiếu có thể dẫn tới **đăng nhập lại tại IdP** hoặc không thể silent SSO. Một cookie SP bị thiếu khi **POST SAMLResponse về ACS** có thể làm Spring không tìm được `AuthnRequest` cũ, `RelayState`/`InResponseTo` không khớp, hoặc nhận diện session mới thay vì session ban đầu.

Hai sự cố nhìn giống “SAML login thất bại”, nhưng sửa khác nhau. Không nên mặc định tăng thời hạn Assertion hoặc tắt kiểm `InResponseTo` để che lỗi cookie.

## 3. Tình huống gây nhầm: top-level redirect khác iframe nhúng

Có bốn tình huống cần tách bạch:

| Browser context | Ví dụ | `SameSite=Lax` có gửi cookie SP? | Third-party blocking tác động ra sao? |
| --- | --- | --- | --- |
| **Same-site request** tới SP | `GET /reports` khi user đang ở SP | Thường có, nếu Domain/Path/Secure đúng | Không phải third-party context |
| **Cross-site top-level GET** tới SP | IdP redirect browser về URL GET của SP | **Có** với Lax thông thường | Browser đã điều hướng top-level sang SP, khác iframe |
| **Cross-site top-level POST** tới ACS | IdP trả form SAMLResponse POST tới SP | **Không** với `SameSite=Lax` tường minh | Vấn đề chính thường là SameSite; không đánh đồng với iframe third-party blocking |
| **Cross-site iframe** tải SP | Trang IdP nhúng `iframe` tới SP SLO | **Không** với Lax/Strict | `SameSite=None` vẫn có thể bị browser chặn/partition |
| **Cross-site iframe** tải IdP | SP nhúng IdP để “silent login” | Cookie IdP Lax không đi theo embedded request | Privacy controls có thể chặn cookie IdP dù None |

**Giải thích quan trọng:** `SameSite=Lax` cho phép cookie trong cross-site navigation **ở top-level với phương thức an toàn như GET**. Nó **không** cho phép cookie cho cross-site `POST` theo quy tắc chuẩn. `SameSite=Strict` còn từ chối cả top-level GET cross-site. `SameSite=None` cho phép gửi cookie trên cả các request cross-site nếu kèm `Secure` và không bị chính sách khác chặn.

Một số Chromium browser có ngoại lệ tạm thời **Lax-allowing-unsafe** cho cookie **không chỉ định `SameSite`**, được đặt trong thời gian rất ngắn (thường nêu là khoảng hai phút). **Đừng dựa vào ngoại lệ này**: nó không có nghĩa `SameSite=Lax` tường minh luôn đi theo POST và có thể khác giữa các browser, phiên bản, ngữ cảnh.

### Khi nào POST ACS vẫn hoạt động dù `SameSite=Lax`?

Để chẩn đoán, phải kiểm thực tế: có thể ứng dụng không cần khôi phục session từ trước, IdP và SP vô tình same-site, browser áp một ngoại lệ với cookie không khai báo `SameSite`, hoặc request có chiến lược state khác. Việc một máy dev chạy được **không chứng minh** cookie policy đúng cho mọi người dùng. Luôn kiểm `Cookie` request header và session/request correlation thực tế.

## 4. So sánh SameSite=Strict, Lax và None đối với SAML

| Thuộc tính | Top-level cross-site GET tới SP | Top-level cross-site POST tới SP | Third-party iframe | Khuyến nghị |
| --- | --- | --- | --- | --- |
| `Strict` | Không gửi cookie | Không gửi cookie | Không gửi cookie | Phù hợp nhiều cookie cần tính cô lập cao, nhưng có thể làm hỏng SAML browser flow |
| `Lax` | Thường gửi cookie | **Không** với Lax tường minh | Không | Hợp lý cho nhiều website thông thường; phải test SAML POST callback |
| `None; Secure` | Có thể gửi | Có thể gửi | Chỉ có thể gửi nếu browser/policy cho phép third-party context | Chỉ dùng cho cookie thực sự cần cross-site, kèm bảo vệ CSRF và HTTPS |
| Không khai báo `SameSite` | Hành vi tùy browser/default | Có thể khác, không ổn định | Tùy browser/privacy | Không nên dựa vào mặc định/ngoại lệ thời gian |

Đây là **mô hình quy tắc phổ biến**, không thay việc kiểm trên browser/OS thực tế. Khi `SameSite=None` nhưng quên `Secure`, browser hiện đại thường **từ chối cookie**. Đặt `Secure` mà trang thực chạy HTTP cũng gây lỗi cookie trong môi trường không dùng HTTPS.

### Cookie thuộc chính sách nào?

Spring Boot Servlet thường có `JSESSIONID` do servlet container phát. Khi dùng Spring Session, session cookie có thể là `SESSION`. Reverse proxy/load balancer, gateway SSO hoặc upstream còn có cookie riêng. Nếu chỉ sửa `JSESSIONID` mà `SESSION` hoặc cookie IdP bị chặn, lỗi vẫn tồn tại.

**Đừng nhầm `Set-Cookie` trên response và `Cookie` trên request**:

~~~text
Response từ SP:
Set-Cookie: JSESSIONID=...; Path=/; Secure; HttpOnly; SameSite=None

Request quay về ACS:
Cookie: JSESSIONID=...
~~~

Phải xác nhận cả hai bước. Không dán giá trị cookie thật vào ticket/chat/log. `Set-Cookie` thành công chưa chắc browser đã lưu, và lưu rồi chưa chắc browser được phép **gửi lại** trong context cross-site.

## 5. Vì sao SP mất AuthnRequest khi IdP POST Response về?

Theo tài liệu Spring Security 7.x, `Saml2WebSsoAuthenticationRequestFilter` tạo `AuthnRequest` và dùng `Saml2AuthenticationRequestRepository` để lưu. Mặc định `HttpSessionSaml2AuthenticationRequestRepository` lưu request trong `HttpSession`. Khi nhận `SAMLResponse`, `Saml2WebSsoAuthenticationFilter`/`Saml2AuthenticationTokenConverter` cần tìm request đã lưu để xử lý correlation.

Ví dụ trạng thái trước và sau:

~~~text
Trước khi đi IdP:
SP response Set-Cookie: JSESSIONID=sid-A; SameSite=Lax
SP HttpSession sid-A:
  AuthnRequest ID=_req-123
  RelayState=_state-abc
  registrationId=partner-b

IdP trả top-level POST tới SP:
POST /login/saml2/sso/partner-b
Cookie: [không có JSESSIONID vì SameSite=Lax]

SP nhìn HTTP request:
Không thể tra sid-A qua cookie
Có thể tạo session sid-B hoặc không tìm thấy request
InResponseTo=_req-123 không có request tương ứng trong sid-B

Kết quả:
SSO fail hoặc retry/redirect loop
~~~

**Thông điệp có chữ ký hợp lệ vẫn không đủ** để chứng minh browser đang nhận nó là browser đã khởi tạo SP-initiated SSO. Việc mất request/session correlation là một tín hiệu bảo mật quan trọng, không chỉ là lỗi UX.

Không “fix” bằng cách **bỏ `InResponseTo`, vô hiệu hóa validator, hay tự chấp nhận mọi unsolicited SAMLResponse**. Những cách đó làm yếu bảo vệ chống login CSRF/login fixation.

## 6. Bật cookie hỗ trợ cross-site POST ở Spring Boot Servlet khi thật cần

Với Spring Boot 3.x/4.x có các properties tương ứng, có thể cấu hình `application.yml`:

~~~yaml
server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: none
~~~

Hoặc `application.properties`:

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=none
~~~

**Tác dụng:** chỉ dẫn servlet container hoặc Spring Session (tùy phiên bản) phát session cookie với `SameSite=None; Secure; HttpOnly`, giúp browser có thể gửi cookie khi IdP thực hiện **cross-site top-level POST** về ACS. Kiểm dependency, runtime servlet container, các session/cookie custom và response header thực tế. Dòng Spring Boot 3.3/3.5/4.0 có tài liệu chính thức cho `server.servlet.session.cookie.same-site`; các phiên bản cũ hoặc custom container có thể xử lý khác.

**Không coi đây là “cấu hình mặc định tốt nhất cho mọi ứng dụng”.** `SameSite=None` làm cookie dễ được gửi cùng nhiều cross-site requests hơn `Lax`, vì vậy cần bảo vệ CSRF đầy đủ, phân tách các endpoint và giới hạn phạm vi cookie theo `Path`/`Domain` nếu thiết kế cho phép. Chỉ triển khai sau khi đánh giá threat model và test trình duyệt thực.

### Đường đi qua HTTPS reverse proxy

Nếu browser đi qua `https://portal.example.com` nhưng Spring container chạy nội bộ qua `http://app:8080`, cần:

- Bảo đảm public URL là HTTPS thật, TLS cấu hình đúng.
- Phát `Secure` cho cookie cần cross-site.
- Chỉ tin `Forwarded`/`X-Forwarded-*` từ proxy đã được xác minh và lọc bỏ các header do Internet tự gửi.
- Kiểm `Domain`, `Path`, context path, session cookie name, và các trường hợp nhiều subdomain.
- Kiểm không có hai `Set-Cookie` cùng tên/path/domain nhưng khác SameSite làm browser chọn cookie bất ngờ.
- Không phát `Domain=.example.com` quá rộng chỉ để “chia sẻ đăng nhập”; có thể tăng rủi ro subdomain takeover/session fixation.
- Dùng `HttpOnly` để ngăn JS đọc session cookie; giữ CSRF token và CSP theo chính sách.

Khi custom session cookie là `SESSION` từ Spring Session, xác nhận `CookieSerializer`/`DefaultCookieSerializer` hoặc cơ chế phiên bản cụ thể có áp cùng attributes. Đừng chỉ đọc YAML rồi kết luận cookie đã đúng.

## 7. Spring Security JavaConfig cho SAML login và logout

Ví dụ **cấu hình trong dự án Spring Security Servlet**, không phải Java 17 standalone:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SamlBrowserSecurityConfig {

    @Bean
    SecurityFilterChain samlSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .saml2Logout(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Code giả định có `spring-security-saml2-service-provider` và `RelyingPartyRegistrationRepository` hợp lệ, IdP metadata, certificates và SLO support đúng hợp đồng. Nó bật các luồng SAML2; **không tự cấu hình cookie**. Cookie được đặt qua Spring Boot/container/Spring Session; cần đồng bộ với logic `HttpSession` và `Saml2AuthenticationRequestRepository`.

**Đừng tạo controller tự đọc Base64 `SAMLResponse` rồi lập session chỉ để tránh SameSite.** Mọi login vẫn phải qua provider xác minh signature, issuer, audience, recipient, NotBefore/NotOnOrAfter, request correlation và anti-replay.

### Nếu một request đi qua SecurityFilterChain khác

Một ứng dụng nhiều chain có thể cho `/login/saml2/sso/**` đi vào chain không bật SAML, dẫn đến 404/302/403. Chẩn đoán cookie phải đi cùng chẩn đoán filter chain; một ACS không match filter có thể bị hiểu lầm là cookie bị chặn.

## 8. Nếu cần lưu AuthnRequest ngoài HttpSession

Spring Security cung cấp `Saml2AuthenticationRequestRepository` và trong tài liệu hiện đại có `CacheSaml2AuthenticationRequestRepository` để hỗ trợ thiết kế lưu AuthnRequest ở cache phân tán khi session-cookie không đi qua mọi bước. Ví dụ dạng bean theo tài liệu hiện hành:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.web.authentication.CacheSaml2AuthenticationRequestRepository;
import org.springframework.security.saml2.provider.service.web.authentication.Saml2AuthenticationRequestRepository;

@Configuration
public class SamlRequestRepositoryConfiguration {

    @Bean
    Saml2AuthenticationRequestRepository<?> authenticationRequestRepository() {
        return new CacheSaml2AuthenticationRequestRepository();
    }
}
~~~

**Cần kiểm package/API của đúng Spring Security version** trước khi biên dịch và cách ứng dụng cung cấp cache. Code chỉ cấu hình một bean repository, không phải một quy trình cache tự bảo đảm an toàn. Tài liệu Spring Security nhấn mạnh một rủi ro quan trọng: nếu lookup AuthnRequest **chỉ từ `InResponseTo` hoặc `RelayState`** mà không ràng buộc nó với browser/session đã khởi tạo, một attacker có thể dùng giao dịch của mình để gây **login fixation** cho nạn nhân.

Vì vậy khi thay repository mặc định, phải thiết kế rõ:

1. State ngẫu nhiên, khó đoán, đủ entropy và có thời hạn ngắn.
2. Ràng buộc request tới browser/tab/session hoặc một cơ chế chống CSRF/login fixation có sức mạnh tương đương.
3. Lưu đúng issuer/registration, AuthnRequest ID, relay state và public ACS.
4. Kiểm `InResponseTo`, `Recipient`, `Destination`, `Audience`, signature và thời gian như trước.
5. Ngăn reuse sau khi login, cơ chế atomic consume-once và anti-replay.
6. Xóa state hết hạn; tránh lộ state ở log, referrer, analytics hoặc browser history.
7. Kiểm việc nhiều tab khởi tạo hai SSO flow có làm state xung đột không.
8. Nếu state được ký/mã hóa hoặc chứa browser-bound secret, thiết kế/test theo threat model cụ thể.

**Không có “cache workaround thần kỳ”** cho mọi browser chặn third-party cookie: nó có thể giúp một số flow nhưng đánh đổi cơ chế ràng buộc request mà session trước đây cung cấp. Ưu tiên giữ top-level login và session phù hợp nếu có thể.

## 9. Cookie của IdP trong embedded login/iframe

Một phương thức cũ để “đăng nhập thầm lặng” là nhúng iframe:

~~~html
<iframe src="https://login.partner-b.example/silent-sso"></iframe>
~~~

Với trang top-level `https://portal.example.com`, site `login.partner-b.example` nằm trong **third-party context**. Các browser hạn chế hoặc partition cookie của IdP theo chế độ privacy. Dù cookie IdP có `SameSite=None; Secure`, browser vẫn có thể:

- Không gửi cookie IdP trong iframe.
- Cô lập cookie theo site top-level, không tái sử dụng IdP session đã tạo ở tab riêng.
- Chặn cookie mới trong iframe.
- Yêu cầu Storage Access API và tương tác của người dùng trong một số trường hợp.
- Chặn frame embedding do `Content-Security-Policy: frame-ancestors` hoặc `X-Frame-Options` dù cookie không phải vấn đề.

**Hậu quả:** silent SSO không tìm thấy IdP session, iframe trả login form không tương tác được, timeout, hoặc lặp redirect. Đây không phải bằng chứng signing certificate SAML bị sai.

### Thay iframe bằng top-level redirect khi phù hợp

Ưu tiên luồng:

~~~text
Browser top-level SP
  -> top-level navigation tới IdP
  -> IdP dùng first-party session cookie của chính nó
  -> trình duyệt POST SAMLResponse về SP ACS
  -> SP xác minh và thiết lập session
~~~

Điều hướng top-level tới IdP giúp IdP hoạt động trong first-party context của chính mình, không phụ thuộc cookie trong iframe. Tuy nhiên **vế quay về ACS bằng POST vẫn cần kiểm SameSite cookie SP** như các phần trước. Một thay đổi UI sang redirect chưa tự giải quyết toàn bộ cookie/session correlation.

Nếu ứng dụng là SPA, đừng đưa SAML XML assertion cho JavaScript để tự verify. Có thể dùng mô hình backend xử lý SAML tại ACS rồi cung cấp phiên ứng dụng theo origin, hoặc BFF (backend-for-frontend), giữ SAML verification ở server.

## 10. Third-party cookie restrictions theo browser (cập nhật nguồn chính thức)

Mỗi trình duyệt có privacy defaults, exceptions và cơ chế lưu trữ khác nhau. Trạng thái cần kiểm theo **version/OS/profile thực tế**; đừng đưa một tuyên bố “tất cả Chrome đã chặn cookie bên thứ ba” thành tiền đề thiết kế.

| Browser hoặc chế độ | Thông tin nền tảng đã công bố | Ý nghĩa với SAML |
| --- | --- | --- |
| **Safari/WebKit** | WebKit công bố **full third-party cookie blocking** mặc định, có Storage Access API trong điều kiện nhất định | Iframe IdP/SP có thể mất cookie; top-level redirect thường phù hợp hơn |
| **Firefox** | **Total Cookie Protection** cô lập cookie/storage third-party theo từng top-level site và có cơ chế hạn chế tracker | Một IdP cookie trong iframe của SP A không đương nhiên dùng chung với iframe của SP B |
| **Chrome thông thường** | Google thông báo ngày **22/04/2025** duy trì lựa chọn third-party cookie hiện có và không triển khai lời nhắc mới riêng; người dùng vẫn có thể chặn trong Settings | Không giả định mặc định chặn toàn bộ; vẫn phải test trường hợp đã bật block |
| **Chrome Incognito** | Google nêu third-party cookies bị chặn theo mặc định ở chế độ Incognito | Test riêng Incognito và bình thường |
| **Chrome/Edge có policy doanh nghiệp hoặc extension** | Chính sách quản trị/tracker blockers có thể hạn chế cookie theo site | Kết quả khác giữa profile/công ty là bình thường |
| **Brave / privacy-focused modes** | Có cơ chế hạn chế cookie/tracker mạnh | Embedded SSO/SLO cần fallback rõ, không phụ thuộc exception |

Điểm quan trọng về thời gian: không suy từ một roadmap cũ rằng đến 2026 Chrome chắc chắn đã loại bỏ mọi cookie bên thứ ba. Thông tin chính thức Google ngày 22/04/2025 nêu **duy trì user choice**, và tài liệu MDN mô tả Chrome không chặn toàn bộ mặc định trong normal browsing nhưng có ở Incognito hoặc khi người dùng chọn. **Browser chính sách có thể đổi**, nên xác minh behavior trên chính browser đang triển khai.

Không khuyến nghị người dùng tắt toàn bộ tracking protection chỉ để một công cụ hoạt động. Hãy sửa thiết kế/flow trước; ngoại lệ privacy nếu có phải do quản trị bảo mật phê duyệt, giới hạn theo site và được truyền đạt rõ ràng.

## 11. Storage partitioning, CHIPS và Storage Access API có giải quyết được không?

### 11.1. Partitioned cookie / CHIPS

Ví dụ một cookie có attributes:

~~~http
Set-Cookie: __Host-embed_session=...; Path=/; Secure; HttpOnly; SameSite=None; Partitioned
~~~

Cookie `Partitioned` tách state theo site top-level; `__Host-` còn yêu cầu `Secure`, `Path=/` và không khai báo `Domain` theo browser hỗ trợ. CHIPS phù hợp một số sản phẩm **embedded widget** có state riêng cho từng site nhúng.

**Không thể coi CHIPS là cách thay thế trực tiếp một IdP session toàn cục.** Nếu cùng IdP B được nhúng dưới SP A và SP C, hai top-level sites có thể có hai phân vùng cookie khác nhau. “Đã login ở IdP khi mở tab riêng” không mặc định đồng nghĩa “iframe IdP ở mọi SP thấy cookie ấy”. Với SAML SLO, một cookie partitioned của SP theo top-level IdP có thể không trùng cookie session SP đã tạo trong top-level SP context.

### 11.2. Storage Access API

Storage Access API cho phép nội dung nhúng xin quyền truy cập một số loại storage/cookie unpartitioned trong những tình huống được browser hỗ trợ và user/policy cho phép. Nó thường đòi **tương tác của người dùng, điều kiện về lịch sử truy cập hoặc quyền**, và mỗi browser áp dụng khác nhau.

Không nên:

- Giả định `document.requestStorageAccess()` sẽ tự thành công trong iframe ẩn.
- Bỏ kiểm `frame-ancestors`/CSP để cho phép iframe mọi domain.
- Lạm dụng popup hoặc user-gesture trick nhằm né policy privacy.
- Coi quyền truy cập storage là bằng chứng đã xác thực SAML.

Nếu thực sự cần IdP UI nhúng, kiểm API hỗ trợ, tương tác, hợp đồng IdP, CSP và fallback sang **top-level redirect**. Với hệ thống doanh nghiệp, thiết kế không phụ thuộc silent iframe thường bền hơn.

### 11.3. Cùng top-level site và reverse proxy

Có hệ thống đặt SP và IdP dưới các host cùng registrable domain để chúng **same-site**. Điều đó có thể giảm một số SameSite restrictions, nhưng không tự chia sẻ host-only cookie, không bảo đảm SAML trust, và có thể mở rộng bề mặt tấn công (shared parent-domain cookie, subdomain takeover). Không tự “đổi DNS” hoặc reverse proxy IdP chỉ để né third-party policy nếu chưa được đội security và IdP phê duyệt.

## 12. Ảnh hưởng tới SAML Single Logout (SLO)

SAML2 Single Logout gồm hai luồng cơ bản:

- **RP-initiated:** người dùng logout tại SP; SP tạo và ký `LogoutRequest` gửi IdP; IdP xử lý rồi gửi `LogoutResponse`.
- **AP-initiated:** logout bắt đầu ở IdP; IdP phát `LogoutRequest` tới SP; SP xác minh, xử lý logout và gửi `LogoutResponse`.

Spring Security Servlet có `Saml2LogoutRequestFilter`, `Saml2LogoutResponseFilter`, `Saml2LogoutRequestRepository` (mặc định thường dựa trên `HttpSessionLogoutRequestRepository`), signing credentials và validators cho SLO. **Trạng thái request/response và cookie/session ảnh hưởng khả năng liên kết `InResponseTo`**, giống nhưng không đồng nhất với SSO.

### 12.1. RP-initiated qua top-level navigation

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant SP as SP Portal
    participant IdP as IdP B
    U->>SP: POST /logout (same-site, CSRF hợp lệ)
    SP->>SP: Xử lý local logout và tạo SAML LogoutRequest
    SP-->>U: Redirect/POST tới IdP SLO
    U->>IdP: LogoutRequest
    IdP->>IdP: Kiểm signature, NameID, SessionIndex
    IdP-->>U: Trả SAML LogoutResponse
    U->>SP: Redirect hoặc POST về SP SLO
    SP->>SP: Kiểm chữ ký, Destination, InResponseTo, Status
    SP-->>U: Trang/kết quả logout
~~~

Khi Response quay lại SP qua **cross-site POST**, cookie `SameSite=Lax` của SP có thể không được gửi. Nếu SLO repository cần session để lấy original LogoutRequest, correlation có thể thất bại. Nếu dùng **top-level GET Redirect binding** và Lax, cookie có thể được gửi theo quy tắc Lax, nhưng binding, signing rules và security policy phải được IdP/SP hỗ trợ. **Không tự ép đổi SLO POST thành GET** hoặc coi GET là phương thức không ảnh hưởng security.

Lưu ý thêm: tùy cấu hình Spring Security, local logout có thể đã kết thúc HTTP session khi phát LogoutRequest. Phải kiểm **lifecycle của repository và session** trong đúng version, không chỉ giả định giữ nguyên JSESSIONID cũ sau logout.

### 12.2. AP-initiated hoặc front-channel logout qua iframe

Một số hệ thống triển khai **front-channel logout** bằng cách IdP gửi request tới nhiều SP qua iframe ẩn để đóng phiên. Với trang top-level IdP, mỗi SP được nhúng lại ở **third-party context**. Nếu browser chặn/partition cookie SP, request SLO tới SP có thể **không mang JSESSIONID của phiên user đang dùng** tại SP.

Kết quả có thể là:

- SP không nhận ra đúng session cần thu hồi.
- SP nhận một signed LogoutRequest hợp lệ nhưng không tìm thấy SAML principal/session tương ứng.
- Một iframe trả HTTP 200 nhưng session ở tab SP còn tồn tại.
- Một số SP logout thành công, một số không, làm xuất hiện **partial logout**.
- Trong thời gian chuyển trang, user quay lại SP và được IdP tự SSO lại nếu IdP session chưa thật sự kết thúc.

**Không gọi HTTP 200 trên iframe là bằng chứng global logout.** Cần xác minh cookie/session bị thu hồi thực tế, chữ ký/correlation/NameID/SessionIndex, và kết quả `LogoutResponse` theo từng SP.

Nếu thiết kế yêu cầu thu hồi nhiều server sessions độc lập với browser, cân nhắc back-channel/server-side mechanism phù hợp **chuẩn và năng lực của IdP/SP**, hoặc quản lý session tập trung/revocation API trong phạm vi được phê duyệt. **Spring Security SAML2 SLO chuẩn tài liệu tập trung POST/Redirect front channel**, không được tự tuyên bố đã có SOAP/back-channel SLO chỉ vì một IdP hỗ trợ nó.

## 13. SLO và logout tại ứng dụng khác: cái gì có thể bảo đảm?

Một hệ thống có thể chứa:

~~~text
IdP B
  ├── SP Portal A
  ├── SP Reports C
  └── SP HR D
~~~

Khi user logout ở Portal A:

1. Portal A có thể chấm dứt local session ngay.
2. Portal A phát LogoutRequest (nếu SLO được hỗ trợ/cấu hình).
3. IdP có thể điều phối logout tại C và D qua các binding đã đăng ký.
4. Browser privacy policy có thể ngăn một iframe hoặc cross-site POST mang cookie của C/D.
5. Một SP có thể lỗi, timeout, hoặc trả status khác.
6. IdP có thể trả `PartialLogout` hoặc biểu thị thông tin thất bại.

**Chỉ có bằng chứng app A logout không đủ để nói C/D đã logout.** Quy trình vận hành nên phân biệt `LOCAL_LOGOUT_DONE`, `SAML_SLO_CONFIRMED`, `SAML_SLO_PARTIAL` và `SAML_SLO_UNKNOWN` trong telemetry và thông báo người dùng, thay vì sử dụng một Boolean `loggedOutEverywhere` không có căn cứ.

## 14. Bảo vệ CSRF khi dùng SameSite=None

Một lỗi dễ xuất hiện: sau khi phát `SameSite=None` để SAML POST mang cookie, developer cho rằng “SAML có chữ ký nên toàn bộ web không cần CSRF”. Đây là suy luận sai.

- `SameSite` là **hỗ trợ phòng CSRF** ở tầng browser, không thay token hoặc kiểm `Origin`/`Referer` cho endpoints phù hợp.
- `SameSite=None` cho phép cookie được gửi theo nhiều yêu cầu cross-site hơn; **CSRF protection càng cần chú ý**.
- SAML ACS là **cross-site POST hợp lệ**; Spring Security có cơ chế tích hợp/ngoại lệ đúng để tiếp nhận SAMLResponse, nhưng **không đồng nghĩa tắt CSRF cho mọi POST**.
- Endpoint SAML ACS phải xác minh signature, issuer, audience, recipient, `InResponseTo` và thời gian theo profile.
- `POST /logout` khởi tạo logout nội bộ cần CSRF bảo vệ theo chính sách của Spring, khác SAML `LogoutRequest` do IdP gửi.
- Với SLO endpoint nhận SAMLRequest/Response, phải xác minh chữ ký/đích/correlation và quản lý CSRF exemption **hẹp** theo đúng filter/route.

**Không triển khai kiểu sau chỉ vì lỗi POST ACS:**

~~~java
// Sai hướng sửa lỗi cookie/csrf cho cả ứng dụng:
http.csrf(csrf -> csrf.disable());
~~~

Một `403` ở ACS có thể đến từ CSRF matcher, filter chain, session/correlation hoặc SAML validation. Điều tra nguyên nhân trước khi sửa rule. Thay đổi `SameSite` cũng không đồng nghĩa thay đổi thuật toán verify ký SAML.

## 15. Dùng cookie chuyên biệt hay tách state có giúp không?

Trong thiết kế phức tạp, có thể cân nhắc:

- Session cookie chung của ứng dụng giữ `Lax` và một cookie state/callback **riêng** có `SameSite=None; Secure` nếu framework/architecture hỗ trợ, để giảm phạm vi gửi cookie nhạy cảm.
- Một backend-for-frontend thực hiện SAML ACS server-side rồi chuyển sang session same-site cho SPA.
- Request repository có state được mã hóa/ký, TTL ngắn, consume-once và browser binding.
- OIDC Authorization Code + PKCE với redirect top-level nếu sản phẩm và IdP hỗ trợ, nhưng đó là **thay đổi giao thức**, không phải “mẹo” áp trực tiếp cho SAML.
- Định tuyến SAML callbacks sao cho browser luôn quay lại public host ổn định, không thay host tùy môi trường.

**Cảnh báo:** phiên SAML và `SecurityContext` thường gắn với một HTTP session. Chỉ “thêm cookie callback” không tự khiến `Saml2WebSsoAuthenticationFilter` tra được session cũ; cần thiết kế repository/transport tương ứng và kiểm login fixation. Không khuyên tự viết session ID vào URL, LocalStorage hoặc query string: rủi ro rò rỉ qua referrer/log/history và session hijacking.

## 16. Chẩn đoán bằng Developer Tools

Để xử lý một lỗi SAML login hoặc logout:

1. Mở tab Network trong DevTools trước khi nhấn nút SSO.
2. Bật **Preserve log** để giữ các request qua redirect/POST sang domain khác.
3. Đăng nhập bằng account test, không chụp/đăng raw SAMLResponse hoặc cookie.
4. Tìm request bắt đầu `/saml2/authenticate/{registrationId}` và response `Set-Cookie` của SP.
5. Tìm POST `/login/saml2/sso/{registrationId}`; xem **request có header `Cookie` hay không** và tab Cookies/Issues có nêu lý do blocked không.
6. Kiểm cookie `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`, `Partitioned`, thời hạn và có đang dùng `JSESSIONID` hay `SESSION`.
7. Xem request là **top-level POST** hay nằm trong **iframe**; cùng host nhưng khác context có thể thay đổi kết quả.
8. So sánh browser thường, Incognito/private, Firefox, Safari và thiết bị di động.
9. Kiểm Spring debug/audit an toàn: repository có tìm đúng AuthnRequest không? `InResponseTo` có khớp không? Có tạo session mới do cookie vắng mặt không?
10. Với logout, ghi nhận `LogoutRequest`/`LogoutResponse` có được xử lý và session thật đã hết hiệu lực chưa.

**Nhận diện lỗi cookie cụ thể:** DevTools thường ghi “cookie blocked due to SameSite”, “third-party cookie blocked”, “Secure attribute required” hoặc “partitioned”. Đừng coi chúng là một lỗi duy nhất. Ghi lại browser/version, URL/HTTP method, response/request cookie attributes **không chứa giá trị secret** và kết quả test.

### Lệnh curl có ích nhưng có giới hạn

~~~bash
curl -I https://portal.example.com/
curl -i https://portal.example.com/saml2/authenticate/partner-b
~~~

Có thể xem response headers/status nhưng **curl không áp chính sách third-party cookie/SameSite của browser** giống Chromium/Safari/Firefox và không tự mô phỏng SAML Browser SSO đầy đủ. Dùng curl để kiểm `Set-Cookie`/redirect cơ bản, **không dùng kết quả curl thành công làm bằng chứng browser flow đúng**.

Nếu có `Set-Cookie` trước redirect và `Cookie` thiếu tại ACS, hãy điều tra browser policy; nếu cookie được gửi nhưng Spring vẫn không tìm request, kiểm session ID, repository, load balancer, timeout, concurrency/multiple-tab và filter chain.

## 17. Java 17 độc lập: mô phỏng những quy tắc cookie cơ bản

Đoạn Java 17 sau **không chạy browser và không xác thực SAML**. Nó minh họa một phần quy tắc `SameSite` trong các bối cảnh điển hình: request same-site, top-level cross-site GET, top-level cross-site POST, iframe cross-site. Tách rõ “`SameSite=None` cho phép” với “browser vẫn chặn third-party context”.

Tạo file **`CookieContextDemo.java`**:

~~~java
public class CookieContextDemo {

    enum SameSite { STRICT, LAX, NONE }
    enum Context {
        SAME_SITE,
        CROSS_SITE_TOP_LEVEL_GET,
        CROSS_SITE_TOP_LEVEL_POST,
        CROSS_SITE_IFRAME
    }

    static boolean cookieSent(
            SameSite mode, boolean secure,
            Context context, boolean blockThirdParty) {

        if (mode == SameSite.NONE && !secure) {
            return false;
        }

        if (context == Context.CROSS_SITE_IFRAME
                && blockThirdParty) {
            return false;
        }

        return switch (mode) {
            case STRICT -> context == Context.SAME_SITE;
            case LAX -> context == Context.SAME_SITE
                    || context == Context.CROSS_SITE_TOP_LEVEL_GET;
            case NONE -> true;
        };
    }

    public static void main(String[] args) {
        System.out.println("Same-site Lax: " + cookieSent(
                SameSite.LAX, true, Context.SAME_SITE, true));

        System.out.println("Cross-site GET Lax: " + cookieSent(
                SameSite.LAX, true,
                Context.CROSS_SITE_TOP_LEVEL_GET, true));

        System.out.println("Cross-site POST Lax: " + cookieSent(
                SameSite.LAX, true,
                Context.CROSS_SITE_TOP_LEVEL_POST, true));

        System.out.println("Cross-site POST None Secure: " + cookieSent(
                SameSite.NONE, true,
                Context.CROSS_SITE_TOP_LEVEL_POST, true));

        System.out.println("Iframe None Secure with block: " + cookieSent(
                SameSite.NONE, true,
                Context.CROSS_SITE_IFRAME, true));

        System.out.println("Iframe None Secure with allow: " + cookieSent(
                SameSite.NONE, true,
                Context.CROSS_SITE_IFRAME, false));

        System.out.println("None without Secure: " + cookieSent(
                SameSite.NONE, false,
                Context.CROSS_SITE_TOP_LEVEL_POST, false));

        System.out.println("Strict cross-site GET: " + cookieSent(
                SameSite.STRICT, true,
                Context.CROSS_SITE_TOP_LEVEL_GET, false));
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac CookieContextDemo.java
java CookieContextDemo
~~~

**Stdout chính xác:**

~~~text
Same-site Lax: true
Cross-site GET Lax: true
Cross-site POST Lax: false
Cross-site POST None Secure: true
Iframe None Secure with block: false
Iframe None Secure with allow: true
None without Secure: false
Strict cross-site GET: false
~~~

**Vì sao:**

- `Same-site Lax: true`: request cùng site, không bị giới hạn cross-site.
- `Cross-site GET Lax: true`: top-level GET là safe navigation được Lax cho phép.
- `Cross-site POST Lax: false`: response SAML từ IdP POST về SP bị hạn chế bởi Lax tường minh.
- `Cross-site POST None Secure: true`: trong mô hình top-level, None/Secure cho phép gửi cookie ngay cả khi chính sách 3PC áp vào iframe.
- `Iframe None Secure with block: false`: dù cookie có None/Secure, browser third-party blocking vẫn có thể ngăn.
- `Iframe None Secure with allow: true`: trong điều kiện không chặn và domain/path hợp lệ, cookie có thể được gửi.
- `None without Secure: false`: trình duyệt hiện đại yêu cầu Secure cho SameSite=None.
- `Strict cross-site GET: false`: Strict không đi theo cross-site navigation thông thường.

**Giới hạn cố ý:** đây chỉ là mô hình khái niệm cho HTTPS. Nó **không** mô phỏng Domain/Path, expiry, public-suffix list, schemeful-site đầy đủ, browser-specific Lax-by-default 2-minute exception, CHIPS partition key, Storage Access API, tracking protection policy, request redirects/POST replay hay session cookie rotation. Chương trình **không dùng được** để quyết định bảo mật production; phải kiểm trên browser và Spring Security thật.

## 18. Bảng chẩn đoán triệu chứng → nguyên nhân → hướng sửa

| Triệu chứng | Nguyên nhân có thể | Hướng sửa không làm yếu bảo mật |
| --- | --- | --- |
| Safari iframe IdP hiện login lại | IdP cookie bị third-party blocking | Dùng top-level redirect, không dựa silent iframe |
| Firefox iframe IdP không thấy phiên từ SP khác | Total Cookie Protection partition theo top-level site | Thiết kế first-party IdP navigation/fallback |
| Chrome bình thường được, Incognito lỗi | Chế độ chặn cookie bên thứ ba khác nhau | Test incognito, loại bỏ phụ thuộc iframe |
| SAML POST ACS thiếu `JSESSIONID` | `SameSite=Lax/Strict` hoặc Domain/Path/Secure | Kiểm Set-Cookie và POST header; cấu hình có policy `None; Secure` khi cần |
| ACS POST có cookie nhưng báo `InResponseTo` lạ | Session repo, request state, multi-tab, load-balancer khác node | Kiểm HttpSession repository/session sharing và correlation |
| Login lặp mãi sau ACS | Cookie không được lưu sau login, host/path sai, session rotate sai | Kiểm Set-Cookie, public host và redirect |
| `SameSite=None` nhưng cookie bị browser từ chối | Thiếu `Secure` hoặc HTTP không phù hợp | Phục vụ HTTPS, phát Secure đúng |
| `None; Secure` vẫn lỗi trong iframe | Third-party cookie blocking không được None giải quyết | Top-level flow hoặc cơ chế storage access có policy |
| SP bị logout từ IdP nhưng tab còn login | Front-channel iframe không truy cập đúng SP session | Kiểm SLO message/session mapping, không khẳng định global logout |
| RP logout về SP SLO bị lỗi correlation | SLO request repository mất session hoặc `RelayState` khác | Kiểm binding, cookie policy, repository và lifecycle logout |
| Một tenant dùng được, tenant khác không | Khác registrable domain, cookie Domain/Path hoặc IdP policies | So hostname, scheme và registration theo tenant |
| Chỉ bản mobile Safari lỗi | WebKit ITP, third-party blocking, session persistence khác | Test thiết bị thật; ưu tiên redirect top-level |
| Backend báo 403 ở ACS | Có thể CSRF/filter hoặc SAML validation chứ không chỉ cookie | Phân loại lỗi qua logs an toàn và chain |
| Tăng clock skew vẫn lỗi | Vấn đề thực là cookie/session request correlation | Phục hồi state, không bỏ timestamp/inResponseTo |
| Có session nhưng role sai | SAML principal/authorities mapping riêng | Kiểm local authorization, không quy cho SameSite |

Lưu ý: cookie được gửi **không** đồng nghĩa assertion SAML hợp lệ; assertion SAML hợp lệ **không** đồng nghĩa user được cấp quyền dữ liệu. Phải kiểm cả authentication và authorization.

## 19. Ma trận kiểm thử đa trình duyệt

Để chứng minh tính bền vững, tạo một IdP lab cùng SP staging và thử:

| Browser/context | SP-initiated SSO (top-level redirect) | ACS cross-site POST | Embedded IdP login | RP/AP SLO |
| --- | --- | --- | --- | --- |
| Chrome bình thường | Có | Có | Có | Có |
| Chrome Incognito | Có | Có | **Bắt buộc test** | Có |
| Chrome chặn third-party cookie thủ công | Có | Có | **Bắt buộc test** | Có |
| Firefox Standard / Total Cookie Protection | Có | Có | **Bắt buộc test** | Có |
| Firefox Strict | Có | Có | **Bắt buộc test** | Có |
| Safari macOS / iOS | Có | Có | **Bắt buộc test** | Có |
| Edge với enterprise privacy policy | Có | Có | **Bắt buộc test** | Có |
| Mobile WebView / app nhúng | Có, nếu sản phẩm hỗ trợ | Có | Bắt buộc kiểm riêng | Có |

Các ô “Có” là **test case phải chạy**, không phải khẳng định mọi tổ hợp đã PASS. Trong mỗi tổ hợp, kiểm:

1. **Bắt đầu SSO:** request session/`AuthnRequest` lưu đúng.
2. **IdP session:** cookie IdP có được gửi trong top-level/iframe theo policy không.
3. **ACS:** POST về đúng URL public, session cookie SP có/không, correlation đúng.
4. **Authentication:** issuer, signature, audience, recipient, thời gian và `InResponseTo` được xác minh.
5. **User session:** login xong truy cập trang bảo vệ mà không bị lặp.
6. **Logout local:** `POST /logout` có CSRF, session SP hết hiệu lực.
7. **RP SLO:** LogoutRequest/LogoutResponse được ký/kiểm và `InResponseTo` đúng.
8. **AP SLO:** yêu cầu từ IdP đến đúng SP và không xóa nhầm phiên.
9. **Global/partial result:** các SP khác được xác minh thực sự đã logout hoặc báo partial chính xác.
10. **Security negative:** iframe cookie bị chặn không được dẫn đến bypass validation hoặc cưỡng bức logout user khác.

**Kết quả QA phải ghi version/browser/OS, context top-level vs iframe, cookie attributes (không có secret), HTTP method và các trạng thái SAML đã xác minh.** Đừng nói “Safari lỗi” chung chung khi chưa biết request nào mất cookie.

## 20. Kế hoạch cải tiến kiến trúc theo mức ưu tiên

**Ưu tiên A — giữ SAML login đúng bảo mật trong browser hiện đại**

1. Chuyển IdP login từ silent iframe sang top-level redirect/navigate khi có thể.
2. Kiểm cookie session SP khi IdP POST về ACS; chỉ cấu hình `SameSite=None; Secure` nếu bắt buộc bởi flow và đã đánh giá CSRF.
3. Giữ `HttpOnly`, HTTPS, public hostname ổn định và `Path/Domain` chính xác.
4. Giữ `HttpSessionSaml2AuthenticationRequestRepository` khi phù hợp; không bỏ correlation vì cookie bị chặn.
5. Nếu state không thể phụ thuộc session, thiết kế `Saml2AuthenticationRequestRepository` tùy chỉnh có binding/TTL/anti-replay và kiểm login fixation.
6. Test Chrome/Firefox/Safari, thường + private mode, desktop + mobile.

**Ưu tiên B — làm logout trung thực, chống lỗi iframe**

1. Kiểm IdP/SP SLO metadata, bindings và chữ ký.
2. Chạy RP-initiated SLO bằng top-level redirect khi hệ thống hỗ trợ.
3. Không phụ thuộc iframe ẩn để bảo đảm logout toàn bộ hệ thống.
4. Với AP-initiated, xác minh LogoutRequest rồi xác định đúng session/NameID/SessionIndex theo khả năng hỗ trợ; đừng dùng raw NameID làm lệnh xóa tùy ý.
5. Ghi lại `LogoutResponse Status`, `PartialLogout`, timeout và session state của từng SP.
6. Cân nhắc server-side session revocation/back-channel theo giao thức/IdP đã thỏa thuận cho yêu cầu doanh nghiệp cao, không tự tuyên bố SAML POST/Redirect sẽ hoạt động như vậy.

**Ưu tiên C — giảm lỗi vận hành**

1. Gắn metrics về callback cookie missing, session mismatch, AuthnRequest missing, correlation failure, 3PC block và SLO partial/failure.
2. Đưa browser/version + policy vào báo lỗi; không thu thập cookie value hoặc raw SAMLResponse.
3. Giám sát thay đổi chính sách cookie của browser và dependencies Spring/Boot.
4. Có runbook rollback cookie attributes và các test an ninh tương ứng.
5. Đào tạo support phân biệt “không còn cookie tại ACS” với “IdP sai certificate” hoặc “user thiếu role”.

## 21. Bài tập tình huống để kiểm tra hiểu biết

### Tình huống A — login Chrome được, Safari iframe không được

SP nhúng trang login IdP trong iframe. Chrome bình thường login được, Safari báo IdP không thấy session.

**Giải thích:** Safari ITP hạn chế third-party cookies khi IdP được nhúng. `SameSite=None; Secure` không bảo đảm vượt qua chính sách chặn. Cách bền hơn là top-level redirect tới IdP để nó xử lý first-party cookie, rồi kiểm ACS POST tại SP.

### Tình huống B — IdP xác thực xong, SP báo thiếu AuthnRequest

Trước SSO, SP phát `JSESSIONID` với `SameSite=Lax`. IdP trả form HTTP POST `SAMLResponse` sang ACS thuộc site khác.

**Giải thích:** Lax tường minh không gửi cookie trên cross-site top-level POST, nên SP có thể không lấy được HttpSession đã lưu `AuthnRequest`. Cần kiểm DevTools `Cookie` header và Set-Cookie trước đó; cân nhắc cookie phù hợp với cross-site POST, giữ CSRF/SAML correlation, không tắt `InResponseTo`.

### Tình huống C — đã đặt None, nhưng logout iframe vẫn không hoạt động

Một ứng dụng đổi session cookie thành `SameSite=None; Secure` nhưng IdP vẫn gửi LogoutRequest bằng iframe ẩn và SP không thấy session.

**Giải thích:** Browser chặn hoặc partition third-party cookie ngay cả khi SameSite=None. Tìm giải pháp SLO không phụ thuộc third-party iframe; kiểm session mapping/correlation, có fallback trung thực cho partial logout.

### Tình huống D — request quay về có cookie nhưng sai registration

SP tích hợp IdP B và C; cookie SP vẫn được gửi, nhưng `InResponseTo` trỏ request của C trong khi Response đến từ B.

**Kết quả:** phải từ chối. Đây là sai quan hệ tin cậy/correlation, không sửa bằng cách đổi SameSite. Kiểm registration mapping và request repository.

### Tình huống E — cùng doanh nghiệp nhưng khác origin

SP là `https://app.company.example`, IdP là `https://login.company.example`. Hai bên cùng registrable domain/scheme, nhưng cookie `JSESSIONID` của SP không có ở request tới IdP.

**Giải thích:** Same-site không đồng nghĩa cookie dùng chung giữa hai host. Một cookie host-only của SP chỉ gửi tới SP; IdP có cookie riêng. Không nên mở rộng `Domain` bừa bãi.

### Tình huống F — công ty đề xuất bỏ CSRF toàn web

Đội vận hành thấy login tốt hơn khi đặt `SameSite=None` và `csrf.disable()`.

**Phân tích:** Nếu lỗi thực sự do CSRF ở ACS, phải sửa matcher/exception **chỉ cho SAML endpoints cần thiết**. Tắt CSRF trên mọi form nghiệp vụ tăng rủi ro và không giải quyết vấn đề third-party cookie blocking trong iframe. Những endpoint SAML vẫn phải kiểm chữ ký, recipient, issuer và request correlation.

### Tình huống G — “Đăng xuất khỏi mọi hệ thống” nhưng Reports C còn phiên

IdP có gửi SLO tới Portal A và Reports C; iframe tới Reports C bị chặn cookie nên local session C vẫn còn.

**Kết quả:** không thể báo tất cả đã logout chỉ dựa `HTTP 200` của iframe. Phải đo session C thực sự hết hiệu lực, SAML LogoutResponse hợp lệ và trạng thái partial/failure của IdP.

## 22. Checklist cuối bài

- [ ] Đã phân biệt *third-party cookie blocking* với `SameSite` trên cross-site top-level POST.
- [ ] Đã xác định `JSESSIONID` hay `SESSION` là session cookie của SP.
- [ ] Đã xác định cookie IdP và cookie SP thuộc hai origin/site khác nhau.
- [ ] Đã test `SameSite=Strict`, `Lax` và `None; Secure` theo đúng browser/context.
- [ ] Không dựa vào ngoại lệ Lax-allowing-unsafe trong vài phút để login “tình cờ” hoạt động.
- [ ] Có `Secure`, `HttpOnly`, HTTPS và `Domain/Path` chính xác.
- [ ] Không mở rộng parent-domain cookie hoặc tắt CSRF toàn hệ thống để né lỗi.
- [ ] Có AuthnRequest repository và `InResponseTo`/`RelayState` correlation an toàn.
- [ ] Không chấp nhận unsolicited Response hoặc cache state từ client mà thiếu browser binding.
- [ ] Không triển khai SAML parsing/XML signature verification bằng JavaScript frontend.
- [ ] Có flow SSO top-level redirect, không phụ thuộc silent iframe.
- [ ] Đã test Safari ITP, Firefox Total Cookie Protection, Chrome normal/Incognito/block-3PC.
- [ ] Đã hiểu CHIPS/partitioning không bảo đảm IdP session dùng chung giữa mọi SP.
- [ ] Nếu dùng Storage Access API, có user-consent/interaction và fallback hợp lệ.
- [ ] SAML SLO ký/kiểm LogoutRequest/Response, Destination, InResponseTo và SessionIndex.
- [ ] Khi logout iframe thất bại, không báo global logout thành công sai thực tế.
- [ ] Đã kiểm reverse proxy, context path, session replication và cookie rotation.
- [ ] Có test HTTP method top-level GET vs POST, embedded iframe và các đường logout.
- [ ] Có telemetry đủ chẩn đoán nhưng không thu thập raw cookie/SAML assertion.
- [ ] Có hướng dẫn và chính sách cập nhật khi browser/IdP/Spring thay đổi.

## 23. Tài liệu chính thức để tự xác minh

1. [MDN — Set-Cookie / SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): `Strict`, `Lax`, `None; Secure`, top-level GET/POST và ngoại lệ Lax-by-default ngắn hạn.
2. [MDN — Third-party cookies](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies): phân biệt browser third-party policies, privacy và ảnh hưởng tới website nhúng.
3. [MDN — Partitioned cookies / CHIPS](https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies/Partitioned_cookies): semantics `Partitioned` theo top-level site.
4. [WebKit — Tracking Prevention](https://webkit.org/tracking-prevention/): Intelligent Tracking Prevention, full third-party cookie blocking và giới hạn lưu trữ.
5. [Mozilla Firefox — Total Cookie Protection](https://www.firefox.com/en-US/features/total-cookie-protection/): partitioned cookie jars và ảnh hưởng embedded content.
6. [Google Privacy Sandbox — Next steps (22/04/2025)](https://privacysandbox.google.com/blog/privacy-sandbox-next-steps): chính sách third-party cookie choice của Chrome và Incognito.
7. [Spring Security — Producing AuthnRequests](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html): `HttpSessionSaml2AuthenticationRequestRepository`, `CacheSaml2AuthenticationRequestRepository` và cảnh báo login fixation nếu chỉ tra `RelayState`.
8. [Spring Security — Authenticating SAML Responses](https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html): ACS, `Saml2AuthenticationTokenConverter` và các lớp xác thực.
9. [Spring Security — Performing Single Logout](https://docs.spring.io/spring-security/reference/servlet/saml2/logout.html): RP/AP-initiated SLO, request repository, signature và response processing.
10. [Spring Boot 3.3 — Servlet SameSite Cookies](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): `server.servlet.session.cookie.same-site` trong ứng dụng Servlet.
11. [Spring Boot 4.0 — Servlet SameSite Cookies](https://docs.spring.io/spring-boot/4.0/reference/web/servlet.html): cấu hình và phạm vi hỗ trợ các phiên bản hiện đại.
12. [OWASP — CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): `SameSite` không thay thế các lớp chống CSRF và cần cân nhắc subdomain/embedded contexts.

**Ghi nhớ:** một lần SAML SSO đúng cần cả **cookie session/SP request correlation** và **message SAML được xác minh**. Cookie `SameSite=Lax` có thể bị loại khỏi **cross-site top-level POST tại ACS**; cookie `SameSite=None; Secure` giúp giải quyết trường hợp đó nhưng **không buộc iframe vượt chính sách third-party cookie của browser**. Với SLO, chặn cookie/partition trong front-channel iframe có thể khiến phiên ở một số SP chưa bị thu hồi. Ưu tiên top-level redirect, giữ những kiểm chứng SAML bắt buộc và báo trạng thái logout trung thực.