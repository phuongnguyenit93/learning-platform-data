# RelayState và khôi phục đích truy cập sau đăng nhập SAML 2.0

## 1. Tại sao cần ghi nhớ đích truy cập?

Một người dùng mở trực tiếp đường dẫn được bảo vệ, chẳng hạn `https://app.example.org/portal/orders/42`, nhưng chưa có phiên đăng nhập ở Service Provider (SP). Spring Security đưa browser sang Identity Provider (IdP) để đăng nhập. Sau khi IdP xác thực thành công và gửi `SAMLResponse` về Assertion Consumer Service (ACS), người dùng mong được **trở lại đơn hàng 42**, thay vì luôn về trang chủ.

Trong SAML 2.0, **`RelayState`** là tham số tùy chọn đi kèm thông điệp trên các browser binding, giúp bên tạo giao dịch mang một giá trị ngữ cảnh xuyên qua hành trình SP → IdP → SP. Nhưng trong Spring Security Servlet còn có cơ chế **`RequestCache` / `SavedRequest`** để ghi nhớ URL mà người dùng đã yêu cầu trước khi bị chuyển sang đăng nhập. Hai cơ chế có quan hệ nhưng **không đồng nhất**.

Bài học này thuộc chủ đề **Luồng đăng nhập SAML2** của Spring Security federation. Sau khi học, bạn có thể:

- Giải thích chính xác `RelayState` là gì, xuất hiện ở HTTP-Redirect/POST binding như thế nào, khi nào IdP phải gửi lại nguyên giá trị.
- Phân biệt ba trạng thái: **SAML protocol request correlation**, **RelayState**, **đích trang ban đầu lưu trong RequestCache**.
- Theo dõi SP-initiated SSO từ URL tài nguyên ban đầu, qua `AuthnRequest`, IdP và ACS đến redirect sau đăng nhập.
- Sử dụng `SavedRequestAwareAuthenticationSuccessHandler` với Spring Security SAML 2.0 login trên Servlet stack.
- Xử lý trường hợp người dùng truy cập trực tiếp trang login, IdP-initiated login, hết phiên, nhiều tab hoặc cookie bị chặn.
- Thiết kế redirect đích an toàn, chống open redirect, login CSRF và giả mạo RelayState; hiểu giới hạn độ dài 80 **byte** của chuẩn.
- Biết cách kiểm thử một đường dẫn sâu (deep link) và phân loại lỗi đúng tầng.

Ví dụ hướng đến **Java 17+ / Spring Boot 3.x / Spring Security 6.x, ứng dụng Servlet/MVC**. Tên miền `.example.org` và số liệu định danh trong bài là minh họa. Các API Spring Security có thể thay đổi trong bản mới; cần đối chiếu tài liệu đúng phiên bản ứng dụng.

## 2. Ba khái niệm dễ bị nhập làm một

| Khái niệm | Chứa gì? | Ai tạo và lưu/kiểm tra? | Mục tiêu |
| --- | --- | --- | --- |
| **`RelayState`** | Chuỗi opaque ngắn đi cùng `SAMLRequest`/`SAMLResponse` | SP hoặc IdP tạo; phía nhận dùng theo thỏa thuận; IdP phản hồi đúng giá trị trong SP-initiated flow | Giữ ngữ cảnh/correlation xuyên đường đi browser |
| **`AuthnRequest ID / InResponseTo`** | ID giao dịch SAML, ví dụ `_req123` trong XML | SP phát request; SP kiểm tra sự tương ứng trong Response và SubjectConfirmation theo profile | Chống nhận nhầm response/replay, ràng buộc response với request |
| **`SavedRequest` trong RequestCache** | Dữ liệu request HTTP ban đầu như URL được bảo vệ, method/headers tùy loại cache | Spring Security ở **SP** lưu khi bắt đầu login và dùng sau khi xác thực | Khôi phục trang mà người dùng định truy cập |

**Một RelayState có thể là key tra trạng thái**, không bắt buộc chứa URL đích. SP có thể tạo random handle, lưu ánh xạ server-side tới request ban đầu rồi nhận lại handle qua IdP. Trong cách Spring Security mặc định, đích ban đầu thường nằm trong **`HttpSessionRequestCache`**, còn `AuthnRequest` được lưu trong **`HttpSessionSaml2AuthenticationRequestRepository`**; cả hai đều dựa vào session trong nhiều cấu hình nhưng phục vụ mục tiêu khác nhau.

Không nên hiểu:
- “Đã trả đúng RelayState” đồng nghĩa người dùng đã xác thực.
- “Có SavedRequest” nghĩa SAML assertion có chữ ký hợp lệ.
- “Có InResponseTo” là có thể redirect tới bất kỳ URL nào từ request.
- “RelayState luôn bằng URL gốc.” Đây chỉ là một thỏa thuận thiết kế có thể tồn tại ở một số hệ thống, không phải yêu cầu bắt buộc của chuẩn SAML.

## 3. RelayState được mang theo qua HTTP như thế nào?

Trong **HTTP-Redirect binding**, SP thường tạo `AuthnRequest`, nén DEFLATE, Base64 rồi URL-encode thành tham số `SAMLRequest`. `RelayState` đi kèm ở tham số query **riêng**:

~~~http
HTTP/1.1 302 Found
Location: https://idp.example.org/sso?SAMLRequest=COMPRESSED_BASE64_VALUE&RelayState=RANDOM_HANDLE
~~~

Browser gửi một GET mới đến IdP. Khi có Redirect-binding signature, giá trị `RelayState` tham gia chuỗi query được ký cùng `SAMLRequest` và `SigAlg` theo quy tắc binding. Tuy nhiên nếu không có chữ ký binding hợp lệ, không được suy rằng RelayState có tính toàn vẹn chỉ vì đang ở HTTPS.

Trong **HTTP-POST binding**, IdP thường trả HTML form cho browser, trong đó `SAMLResponse` đã Base64-encode và `RelayState` là hidden input khác:

~~~html
<form method="post" action="https://app.example.org/login/saml2/sso/corp">
  <input type="hidden" name="SAMLResponse" value="BASE64_SAML_RESPONSE">
  <input type="hidden" name="RelayState" value="RANDOM_HANDLE">
  <button type="submit">Continue</button>
</form>
~~~

Browser gửi:

~~~http
POST /login/saml2/sso/corp HTTP/1.1
Host: app.example.org
Content-Type: application/x-www-form-urlencoded

SAMLResponse=BASE64_SAML_RESPONSE&RelayState=RANDOM_HANDLE
~~~

Form trên chỉ là minh họa, không chứa Response đã ký. Việc form auto-submit bằng JavaScript là chi tiết trình duyệt; SP không lấy form body làm chứng cứ định danh trước khi **xác minh SAML Response và assertion**.

**Quy tắc phản hồi của chuẩn:** khi SAML request đi kèm RelayState, SAML responder phải đặt **đúng giá trị đã nhận** vào tham số RelayState của response qua một binding có hỗ trợ tham số đó. “Đúng” ở đây là không tự diễn giải hoặc sửa nội dung opaque. Nếu IdP chỉ nhận request mà bỏ RelayState khi trả về, SP có thể không nối lại được ngữ cảnh, dù phần SAML assertion có thể hợp lệ.

## 4. Giới hạn 80 byte và tính toàn vẹn

Đặc tả SAML 2.0 HTTP-Redirect và HTTP-POST binding quy định **RelayState không quá 80 byte** (không phải 80 ký tự Unicode). Với UTF-8, một ký tự tiếng Việt có thể cần nhiều byte. Vì khả năng tương tác, cách thực tế tốt là **random token ASCII ngắn** hoặc một opaque reference.

Ví dụ kích thước:

| Giá trị | Nhận xét |
| --- | --- |
| `RANDOM_HANDLE` | Opaque, ngắn và không chứa URL hay dữ liệu cá nhân |
| Base64url của 18 byte random | 24 ký tự ASCII, tức 24 byte, dưới 80 byte |
| `/portal/orders/42` | Có thể là đường dẫn hợp lệ về mặt kích thước, nhưng cần chính sách target và không nên mặc định tin |
| URL dài cùng query/filter | Có thể vượt 80 byte, dễ gặp sự khác biệt IdP/vendor |
| Toàn bộ JWT/cookie/JSON user profile | Không phù hợp: quá dài, lộ dữ liệu và khó chứng minh tính toàn vẹn |

Trong thực tế một số IdP/SP có ngoại lệ vượt giới hạn chuẩn vì yêu cầu sản phẩm; muốn tích hợp phải kiểm tra và thống nhất khả năng tương tác. **Bản thiết kế mới nên tuân giới hạn 80 byte** và không dựa vào vendor nới lỏng.

Tính toàn vẹn:
- Với **HTTP-Redirect binding** được ký đúng, chữ ký query bao gồm RelayState theo SAML 2.0 errata.
- Với **HTTP-POST**, RelayState nằm ngoài nội dung XML đã ký; **chữ ký XML trên SAMLResponse không tự bảo vệ trường hidden input RelayState**. SP nên dùng token khó đoán ánh xạ đến trạng thái server-side, hoặc cơ chế xác thực/tính toàn vẹn độc lập phù hợp.
- Mọi trường do browser gửi đều có thể bị thay đổi. Server phải xác minh correlation trước khi dùng trạng thái và target.
- **Không lưu password, token đăng nhập, số định danh nhạy cảm hay quyền truy cập trong RelayState**.

Chữ ký bảo đảm một thông điệp chưa bị sửa theo cơ chế tương ứng; nó không thay chính sách **URL nào được phép redirect** sau login.

## 5. Luồng SP-initiated: từ deep link đến deep link

Giả sử user chưa đăng nhập, mở:

~~~text
https://app.example.org/portal/orders/42?tab=history
~~~

Một luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant SP as Spring Security SP
    participant I as IdP
    B->>SP: GET /portal/orders/42?tab=history
    SP->>SP: RequestCache lưu SavedRequest của URL gốc
    SP-->>B: 302 đến trang hoặc endpoint đăng nhập
    B->>SP: GET /saml2/authenticate/corp
    SP->>SP: Tạo và lưu AuthnRequest, RelayState
    SP-->>B: Redirect đến IdP?SAMLRequest=...&RelayState=h
    B->>I: GET tới IdP SSO
    I-->>B: Login/MFA hoặc dùng phiên IdP sẵn có
    I-->>B: Form POST SAMLResponse + RelayState=h
    B->>SP: POST /login/saml2/sso/corp
    SP->>SP: Verify assertion + InResponseTo + session
    SP->>SP: Tạo Authentication và phiên SP
    SP->>SP: SuccessHandler lấy SavedRequest
    SP-->>B: 302 /portal/orders/42?tab=history
    B->>SP: GET trang đích với cookie phiên SP
    SP-->>B: Nội dung đơn hàng nếu được phép
~~~

**Giải thích các bước quan trọng:**

1. `ExceptionTranslationFilter` nhận diện request bị yêu cầu xác thực. Trước khi gọi authentication entry point, cơ chế `RequestCache` có thể lưu request gốc trong HttpSession.
2. Khi khởi tạo SAML, `Saml2WebSsoAuthenticationRequestFilter` phát `AuthnRequest`. `HttpSessionSaml2AuthenticationRequestRepository` lưu request SAML để tương quan.
3. Browser tới IdP và nhận lại `SAMLResponse` cùng RelayState qua form POST. **RelayState không dùng để tự xác nhận người dùng**, và không chứng minh SavedRequest đúng.
4. `Saml2WebSsoAuthenticationFilter` và authentication provider xác minh chữ ký/issuer/audience/destination/subject confirmation/time/correlation theo cấu hình.
5. Sau khi xác thực thành công, Spring Security tạo `Authentication`; success handler chọn nơi đưa browser tiếp tục. Với cấu hình `SavedRequestAwareAuthenticationSuccessHandler`, handler lấy SavedRequest và redirect tới URL gốc nếu có.
6. Khi browser GET lại trang đơn hàng, việc được phép xem đơn đó còn phụ thuộc **authorization của tài nguyên**, không chỉ SAML login.

**Điểm dễ bỏ sót:** nếu SavedRequest chứa `?tab=history` thì redirect thường có thể khôi phục URL đầy đủ. Tuy nhiên **không dùng SavedRequest như cơ chế “replay mọi POST”**. Với thao tác thay đổi dữ liệu, ứng dụng nên thiết kế GET trang hoặc lưu draft an toàn, rồi yêu cầu user xác nhận POST sau login. Không tự phát lại thao tác thanh toán/đặt hàng chỉ vì user vừa xác thực.

## 6. RequestCache khác Saml2AuthenticationRequestRepository

Hai repository hoàn toàn có thể cùng lưu trong một HTTP session nhưng có API và lý do tồn tại khác nhau.

| Cơ chế Spring Security | Đối tượng lưu | Bắt đầu lưu khi nào? | Khi nào sử dụng? |
| --- | --- | --- | --- |
| `RequestCache` | `SavedRequest`, ví dụ GET `/portal/orders/42` | Request bảo vệ bị ngăn vì chưa xác thực | Sau login chọn URL đích, và khi browser truy cập lại URL đó |
| `Saml2AuthenticationRequestRepository` | `AbstractSaml2AuthenticationRequest`, chứa thông tin AuthnRequest/RelayState | Khi tạo SAML AuthnRequest | Khi nhận response/ACS để đối chiếu giao dịch |
| `RelyingPartyRegistrationRepository` | SP–IdP registration, issuer, SSO URL, cert | Cấu hình app, thường lúc khởi động | Tạo request và xác minh response |
| HTTP session/SecurityContext repository | Principal và thông tin phiên xác thực | Sau khi login được chấp nhận | Những request tiếp theo cần xác thực |

Spring Security dùng `HttpSessionSaml2AuthenticationRequestRepository` làm triển khai mặc định cho việc lưu AuthnRequest trong các bản Servlet được mô tả trong tài liệu. Có tùy chọn cache/distributed repository, nhưng không nên thay chỉ để tiết kiệm một cookie mà chưa đánh giá login fixation và CSRF.

### Khi Session lưu một số trạng thái

Trong một cách nhìn đơn giản:

~~~text
HTTP Session của browser:
  SavedRequest:
    originalUrl = /portal/orders/42?tab=history
  SAML authentication request:
    requestId = _request-abc
    relayState = opaque-handle
    registrationId = corp
  Sau khi thành công:
    SecurityContext -> authenticated principal
~~~

Sơ đồ chỉ giải thích khái niệm. **Không khẳng định đây là các key/đối tượng session nội bộ thật của phiên bản Spring Security cụ thể**; không dựa vào tên key hoặc format nội bộ để viết integration.

Khi lỗi “RelayState not found” và lỗi “SavedRequest missing” xảy ra, cần kiểm tra **hai đường lưu riêng**.

## 7. SavedRequestAwareAuthenticationSuccessHandler làm gì?

`SavedRequestAwareAuthenticationSuccessHandler` là success handler của Spring Security dùng `RequestCache` để trả user về tài nguyên ban đầu. Nó hữu ích không riêng cho SAML mà cho nhiều cơ chế xác thực trong Servlet stack.

Sau thành công, về cơ bản handler lựa chọn:

1. Nếu cấu hình **`alwaysUseDefaultTargetUrl=true`**, bỏ qua SavedRequest và đi tới target mặc định.
2. Nếu cấu hình **`targetUrlParameter`** và request có tham số đó, nó có thể ưu tiên giá trị target do tham số cung cấp. **Không bật cơ chế này với target do browser nhập tùy ý** nếu chưa có validation chặt.
3. Nếu còn SavedRequest trong `RequestCache`, redirect về URL ban đầu.
4. Nếu không có SavedRequest, dùng cách chọn target mặc định của `SimpleUrlAuthenticationSuccessHandler`, ví dụ `/portal` nếu bạn đã cấu hình.

Bởi vậy, việc đổi `defaultTargetUrl` không đủ để buộc mọi login đi trang chủ; phải xét `alwaysUseDefaultTargetUrl` và trạng thái SavedRequest. Ngược lại nếu buộc luôn dùng default, tính năng khôi phục deep link sẽ biến mất.

**Sự khác nhau với RelayState:** Success handler không cần giải mã RelayState thành URL để chuyển hướng. Một SP có thể giữ RelayState opaque chỉ cho SAML correlation, đồng thời dùng SavedRequest riêng để biết URL gốc.

### Dữ liệu đến từ browser cần trust policy

Ngay cả SavedRequest cũng nên được tạo thông qua **request thực sự tới tài nguyên do ứng dụng quản lý** và cấu hình proxy/host chuẩn. Nếu hostname/forwarded headers bị tin nhầm, một URL tuyệt đối không mong muốn có thể lọt vào cache. Đừng biến thành công login thành điều kiện đủ để redirect đến host tùy ý.

## 8. Ví dụ Spring Security Servlet: khôi phục đích đã lưu

Ví dụ sau thuộc **dự án Spring Boot 3.x có Spring Security SAML2 SP** và `RelyingPartyRegistrationRepository` hợp lệ. Tệp:

`src/main/java/com/example/federation/SamlLoginConfiguration.java`

~~~java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.security.web.savedrequest.HttpSessionRequestCache;
import org.springframework.security.web.savedrequest.RequestCache;

@Configuration
public class SamlLoginConfiguration {

    @Bean
    RequestCache requestCache() {
        return new HttpSessionRequestCache();
    }

    @Bean
    SavedRequestAwareAuthenticationSuccessHandler samlSuccessHandler(
            RequestCache requestCache) {
        var handler = new SavedRequestAwareAuthenticationSuccessHandler();
        handler.setRequestCache(requestCache);
        handler.setDefaultTargetUrl("/portal");
        handler.setAlwaysUseDefaultTargetUrl(false);
        return handler;
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            RequestCache requestCache,
            SavedRequestAwareAuthenticationSuccessHandler samlSuccessHandler)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/public/**", "/error").permitAll()
                        .anyRequest().authenticated())
                .requestCache(cache -> cache.requestCache(requestCache))
                .saml2Login(saml -> saml.successHandler(samlSuccessHandler))
                .build();
    }
}
~~~

**Đây là cấu hình Spring**, không phải một chương trình Java độc lập có `main`. Nó chỉ biên dịch/chạy khi đặt trong project Boot có dependencies tương thích và metadata IdP thực. Không có stdout cố định; kết quả quan sát được là các response HTTP và URL điều hướng.

Giải thích:

- `HttpSessionRequestCache` lưu request tài nguyên bị chặn; đây là nguồn của URL khôi phục.
- `handler.setRequestCache(requestCache)` và `.requestCache(cache -> cache.requestCache(requestCache))` khiến filter chain và handler cùng dùng một cache.
- `setDefaultTargetUrl("/portal")` là fallback khi không có SavedRequest (ví dụ user khởi tạo login trực tiếp).
- `setAlwaysUseDefaultTargetUrl(false)` cho phép ưu tiên saved deep link.
- `.saml2Login(saml -> saml.successHandler(...))` gắn handler vào SAML 2.0 login thành công; nó **không thay phần xác minh SAML**.
- Quy tắc `anyRequest().authenticated()` bảo vệ mọi URL khác; trong dự án thật cần thêm chính sách phân quyền theo nghiệp vụ và tránh các redirect loop do trang login/public không được permit.
- Không cấu hình `targetUrlParameter` vì một tham số đích có thể bị browser thay đổi, cần kiểm soát open redirect.

Trong Spring Security nhiều dự án, default success handler vốn đã hỗ trợ saved request. Ví dụ này **làm rõ cơ chế** và nơi cấu hình để đảm bảo hành vi ổn định khi ứng dụng có nhiều authentication mechanism. Không cần override handler nếu dự án hiện tại đã làm đúng.

### Cần dependency gì?

Trong module ứng dụng Boot Servlet, những phụ thuộc chính thường có:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-saml2-service-provider'
}
~~~

Đây chỉ là đoạn `dependencies` trong Gradle project **đã cấu hình Boot BOM và repository OpenSAML/Shibboleth thích hợp**. Không gắn version Spring Security trái BOM. Cần IdP metadata và registration thực để chạy SAML; không thể thử login chỉ bằng việc thêm ba dependency.

### Cấu hình IdP minh họa

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
~~~

Cần đặt metadata XML **đã xác minh** vào `src/main/resources/saml/corp-idp.xml` và đăng ký SP entity ID/ACS bên IdP. Không dùng một XML tự bịa có chứa bất kỳ certificate tùy ý để gọi là IdP tin cậy.

## 9. Luồng khi không có SavedRequest

Có nhiều cách bắt đầu login:

**A. Người dùng mở deep link khi chưa xác thực:** Spring lưu `SavedRequest`, sau login quay về URL đó. Đây là luồng mong muốn cho `/portal/orders/42`.

**B. Người dùng nhấn nút “Đăng nhập” ở trang công khai:** browser đi thẳng đến `/saml2/authenticate/corp` mà trước đó **không có request bảo vệ** cần lưu. Sau login, success handler dùng `defaultTargetUrl("/portal")`.

**C. Người dùng mở bookmark IdP hoặc vào SSO từ cổng doanh nghiệp:** có thể xảy ra **IdP-initiated SSO**, browser POST SAMLResponse về ACS mà trước đó SP không tạo AuthnRequest. Khi đó không có SavedRequest từ resource bị bảo vệ và cũng có thể không có request correlation thông thường. Chỉ chấp nhận unsolicited response nếu **chính sách SP cho phép** và provider/version xử lý an toàn; target nên là default hoặc được xác định từ allow-list đã thỏa thuận với IdP.

**D. Người dùng đã đăng nhập SP:** truy cập `/portal/orders/42` đi thẳng tới controller nếu được phân quyền, không cần RelayState hoặc SavedRequest mới.

**Không nên coi RelayState từ IdP-initiated response là chỉ thị redirect URL an toàn.** Đối với login không có request tương quan, nó là dữ liệu đầu vào ít tin cậy hơn và phải được gắn với chính sách/hợp đồng cụ thể.

## 10. Nếu muốn đặt đích trong RelayState thì thiết kế ra sao?

Một số hệ thống cần giữ ngữ cảnh do business flow phức tạp, nhiều bước hoặc nhiều IdP, và không thể dựa hoàn toàn vào request cache. Cách thiết kế an toàn:

1. Khi user mở URL hợp lệ ở SP, lấy **path thuộc ứng dụng** hoặc một mã định danh nghiệp vụ, validate và lưu server-side.
2. SP sinh **opaque random handle** đủ khó đoán (chẳng hạn 128–192 bit), dưới 80 byte khi encode ASCII.
3. Lưu ánh xạ `handle -> {registrationId, requestId, sessionBinding, localDestination, createdAt, expiresAt, consumed=false}` trong store với TTL ngắn. Không lưu nguyên URL ngoài miền hoặc thông tin nhạy cảm dưới dạng RelayState.
4. Đưa **chỉ handle** vào RelayState khi khởi tạo AuthnRequest theo API/custom resolver mà phiên bản Spring Security hỗ trợ.
5. Khi SAMLResponse về ACS, **xác minh SAML trước**: chữ ký, issuer, audience, destination, thời hạn, `InResponseTo` và các điều kiện.
6. Sau khi xác minh, tra handle trong server-side store, **ràng buộc với giao dịch browser/session/requestId**; kiểm tra TTL, registration, trạng thái một lần.
7. Tiêu thụ/đánh dấu handle **nguyên tử**, lấy đích đã được phép. Nếu bất kỳ kiểm tra nào fail, bỏ handle và về fallback an toàn (hoặc từ chối giao dịch tùy rủi ro).
8. Chỉ redirect đến **đường dẫn nội bộ** hoặc allow-list chính thức; user vẫn cần authorization để xem tài nguyên.

Đây là **một kiến trúc tùy chỉnh**, không phải mô tả cách Spring Security mặc định lưu chính xác các trường. Một số API cho phép dựng authentication request và set RelayState theo resolver; nếu không có nhu cầu đặc biệt, **dùng RequestCache mặc định** thường đơn giản và ít lỗi hơn.

### Tại sao phải ràng buộc với phiên browser?

Giả sử kẻ tấn công mở login cho **tài khoản của chính họ** và gửi callback/RelayState cho browser nạn nhân. Nếu SP dùng một store toàn cục chỉ dựa trên RelayState hoặc InResponseTo để tìm request rồi chấp nhận response, nạn nhân có thể bị đăng nhập vào tài khoản của kẻ tấn công (**login CSRF / login fixation**). Chỉ có một random handle không đảm bảo request đó thật sự do browser nạn nhân khởi tạo.

Spring Security lưu AuthnRequest trong **HttpSession** mặc định vì phiên browser là một ràng buộc quan trọng: response của giao dịch khác thường không có request phù hợp trong phiên này. Nếu thay bằng distributed cache toàn cục, phải đánh giá lại chống login fixation và thiết kế binding bổ sung; không tin mọi response “tra được key” là đủ an toàn.

## 11. Lưu AuthnRequest trong session hay cache phân tán?

Spring Security cung cấp interface `Saml2AuthenticationRequestRepository`. Mặc định nó dùng `HttpSessionSaml2AuthenticationRequestRepository`. Tài liệu các phiên bản gần đây cũng mô tả `CacheSaml2AuthenticationRequestRepository` để lưu AuthnRequest vào cache phân tán, tra bằng RelayState.

| Chọn nơi lưu | Điểm thuận lợi | Rủi ro/cần kiểm tra |
| --- | --- | --- |
| **Session mặc định** | Gắn request SAML với browser session, hữu ích chống login fixation | Cookie session phải quay về ACS; cần chính sách SameSite/replica/session persistence |
| **Distributed cache theo RelayState** | Có thể tra request khi session không sẵn có; thuận tiện cho nhiều node | Phải tự đánh giá/thiết kế chống login fixation, binding session và replay/TTL |
| **Custom repository** | Tùy chỉnh multi-tenant, tracing/correlation, storage | Tăng bề mặt lỗi: race condition, stale state, key collision, dọn dẹp và bảo mật |

Trong Spring Security 7.x có thể xuất bean `CacheSaml2AuthenticationRequestRepository` theo hướng dẫn chính thức; availability và constructor/config phải đối chiếu đúng **version**. **Không đổi repository chỉ vì muốn tùy chỉnh URL sau login**: lựa chọn này chủ yếu về trạng thái SAML, còn URL gốc thuộc `RequestCache`.

Nếu chạy nhiều replica mà dùng session memory từng node, callback đi node khác có thể mất trạng thái. Có thể cần sticky session hoặc Spring Session phân tán; điều này không có nghĩa RelayState phải chứa session token.

## 12. Cookie SameSite khiến luồng POST về ACS mất trạng thái

Luồng Web SSO thường bắt đầu tại SP, chuyển sang IdP khác site, rồi IdP trả form HTTP POST tới ACS ở SP. Browser có thể không gửi cookie SP khi đó, tùy `SameSite`:

- `SameSite=Strict`: cookie không được gửi trong request cross-site. Đối với login federated, rất dễ mất session trong các bước quay về.
- `SameSite=Lax`: thường gửi cookie cho điều hướng top-level cross-site bằng **phương thức an toàn như GET**, không thể dựa vào cookie Lax ở cross-site POST thông thường.
- `SameSite=None; Secure`: cho phép gửi cookie trong nhiều ngữ cảnh cross-site qua HTTPS, nhưng cần chính sách CSRF/chống login CSRF đầy đủ.
- Còn có chính sách browser chặn third-party cookies khi nhúng iframe; login top-level khác login embedded. Một số browser có ngoại lệ tạm khi cookie không khai báo SameSite, không nên dùng làm thiết kế.

**Biểu hiện:** IdP có thể đã xác thực user, form POST `SAMLResponse` về đúng ACS, nhưng SP không tìm thấy AuthnRequest trong session. Kết quả thường là lỗi correlation/unsolicited, không nhất thiết là lỗi signature.

Hướng điều tra:
1. Xem browser request POST ACS có header `Cookie` chứa session phù hợp không.
2. So `Set-Cookie` trước redirect với cookie request ở ACS: SameSite, Secure, Domain, Path, expiry.
3. Xem proxy/TLS offload và public host có khiến cookie bị đánh nhầm là insecure/cross-site không.
4. Kiểm tra session store/sticky session trong triển khai nhiều node.
5. Chỉ dùng giải pháp thay cookie/session/request repository sau khi đánh giá login CSRF, không bỏ `InResponseTo` để tránh lỗi.

**Phân biệt:** mất **AuthnRequest session** có thể làm SAML Response bị từ chối; mất **SavedRequest** có thể khiến login vẫn thành công nhưng user về trang fallback. Hai trường hợp cần kiểm tra khác nhau.

## 13. Open redirect: lỗi nguy hiểm khi dùng RelayState làm URL

Một cách làm thiếu an toàn:

~~~text
POST /login/saml2/sso/corp
RelayState=https://attacker.example.org/phishing

Sau khi SAML login thành công:
302 Location: https://attacker.example.org/phishing
~~~

Nếu SP chuyển browser tới **URL bất kỳ lấy trực tiếp từ RelayState**, kẻ tấn công có thể lợi dụng uy tín domain SP để dẫn user tới website giả hoặc khởi động chuỗi tấn công tiếp theo. Dù assertion là hợp lệ, **đích redirect có thể bị kẻ xấu điều khiển**.

Không chấp nhận những dạng target không được phê duyệt như:

- URL tuyệt đối ngoài miền: `https://evil.example.org`.
- Scheme-relative URL: `//evil.example.org/path`.
- Scheme nguy hiểm/khác dự kiến: `javascript:`, `data:`.
- Dạng encoding nhiều lớp hoặc backslash làm thư viện/browser diễn giải khác: `/%2F%2Fevil...`, `\\evil.example.org`.
- Host bị sửa qua header `Host`/`X-Forwarded-Host` không đáng tin, dẫn đến SavedRequest hoặc absolute redirect URL sai.

**Ưu tiên:** redirect tới **local path nằm trong allow-list** và lấy từ trạng thái server-side gắn đúng giao dịch. Nếu không thể bảo đảm, chọn fallback an toàn. Chỉ kiểm tra `startsWith("/")` là quá yếu: chuỗi `//evil.example.org` cũng bắt đầu bằng dấu gạch chéo.

### Quy tắc thực hành

1. Đích lấy từ **RequestCache do SP kiểm soát** là lựa chọn cơ bản cho SSO deep link.
2. Nếu cho client đề xuất target, chuyển nó thành **route ID** theo bảng định tuyến allow-list và lưu server-side.
3. Không dùng raw `Referer` để chọn trang sau login; header có thể thiếu hoặc bị thay đổi.
4. Không mở `setTargetUrlParameter("redirect")` mà không xác minh chặt cả origin, path, encoding và authorization.
5. Không dùng `RelayState` như quyền truy cập: ngay cả target hợp lệ, route vẫn phải kiểm tra quyền từng user.

## 14. Java 17 chạy độc lập: chọn đích theo allow-list

Mục tiêu ví dụ là cho thấy cách **không tin một path do bên ngoài gửi**, đồng thời tạo một RelayState ASCII ngắn. Đây là chương trình Java 17 **độc lập**, dùng JDK Standard Library, **không thực hiện SAML login và không tạo session server thực**.

Lưu tệp `SafeRelayStateDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Set;

public class SafeRelayStateDemo {

    private static final Set<String> ALLOWED_PATHS = Set.of(
            "/portal",
            "/portal/orders",
            "/portal/profile"
    );

    static String safeTarget(String proposed) {
        return ALLOWED_PATHS.contains(proposed) ? proposed : "/portal";
    }

    static String newRelayState() {
        byte[] random = new byte[18];
        new SecureRandom().nextBytes(random);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(random);
    }

    public static void main(String[] args) {
        String relay = newRelayState();
        System.out.println("RelayState bytes: "
                + relay.getBytes(StandardCharsets.US_ASCII).length);
        System.out.println("RelayState URL-safe: "
                + relay.matches("[A-Za-z0-9_-]+"));

        System.out.println("Known path: "
                + safeTarget("/portal/orders"));
        System.out.println("External URL: "
                + safeTarget("https://evil.example.org/phishing"));
        System.out.println("Protocol-relative URL: "
                + safeTarget("//evil.example.org"));
    }
}
~~~

Biên dịch/chạy với JDK 17+:

~~~bash
javac SafeRelayStateDemo.java
java SafeRelayStateDemo
~~~

**Stdout chính xác** (token random không được in ra):

~~~text
RelayState bytes: 24
RelayState URL-safe: true
Known path: /portal/orders
External URL: /portal
Protocol-relative URL: /portal
~~~

Giải thích:
- 18 random byte → 24 ký tự Base64url không padding → **24 byte ASCII**, dưới giới hạn 80 byte.
- `SecureRandom` phù hợp hơn `Math.random()` để tạo handle khó đoán.
- `Set.contains` chỉ cho phép **đường dẫn nằm trong danh sách đã duyệt**, không phải parser URL tổng quát. Ví dụ cố ý không hỗ trợ query/path parameter động; muốn có `/portal/orders/42` thì lưu **route ID và order ID đã được validate server-side**, sau đó dùng builder framework tạo đường dẫn nội bộ.
- Token RelayState cần ánh xạ có TTL, binding session/request, one-time consume ở server. **Chỉ sinh token random như ví dụ chưa đủ bảo vệ login CSRF và replay.**
- Mã này không chứa Spring dependency. Không dùng `newRelayState()` một mình như thay thế SAML authentication request repository.

## 15. Điều gì xảy ra nếu nhiều tab cùng yêu cầu login?

Kịch bản:

- Tab A mở `/portal/orders/42`, tạo SavedRequest A và AuthnRequest A.
- Tab B mở `/portal/profile`, tạo SavedRequest B và AuthnRequest B.
- User đăng nhập trong tab A, nhưng session/request repository hoặc RequestCache của ứng dụng lưu theo một slot/trạng thái không phân biệt từng tab.
- Sau callback, user có thể về trang của tab B hoặc gặp lỗi correlation, tùy cách lưu và phiên bản.

**Không khẳng định Spring Security luôn làm hỏng multi-tab**: kết quả thực tế phụ thuộc repository, session, cấu hình và thứ tự request. Nhưng đây là tình huống cần kiểm thử vì SavedRequest và SAML request là những state riêng, có thể bị thay thế hoặc hết hạn.

Biện pháp thiết kế:
- Đừng dựa vào “một URL gốc cho mọi tab” nếu sản phẩm yêu cầu giữ nhiều flow song song.
- Nếu lưu đích theo opaque RelayState, ánh xạ phải phân biệt **giao dịch**, `requestId`, session/browser binding và thời điểm, không chỉ theo một global property.
- Hết hạn, consume một lần và loại dữ liệu cũ; dùng thao tác atomic khi nhận response.
- Trường hợp phức tạp có thể phải thay `RequestCache`/SAML request repository hoặc UX cho phép quay lại URL mà người dùng chọn, thay vì cố replay âm thầm.
- Luôn kiểm tra authorizations trên route cuối.

## 16. Các edge case ảnh hưởng đến khôi phục đích

| Tình huống | Hành vi hợp lý | Điều cần kiểm tra |
| --- | --- | --- |
| User mở URL bảo vệ rồi login thành công | Trả về URL ban đầu | SavedRequest được lưu và success handler dùng cùng RequestCache |
| User bắt đầu login từ trang công khai | Trả về fallback được cấu hình | Không có SavedRequest |
| IdP trả RelayState khác giá trị SP gửi | Từ chối/không dùng trạng thái bị sai tùy policy, không redirect theo dữ liệu giả | Correlation, tính toàn vẹn và log dạng redact |
| SAMLResponse hợp lệ nhưng SavedRequest đã mất | Có thể về fallback, **không tạo URL từ RelayState không tin cậy** | Session/RequestCache, timeout, cookie |
| SAMLResponse không hợp lệ | Không coi là login thành công, không điều hướng tới đích bảo vệ với Authentication mới | Signature, issuer, audience, time, destination, InResponseTo |
| Session mất trước callback | Login có thể fail vì thiếu AuthnRequest; đừng bỏ xác minh | Cookie SameSite, distributed sessions |
| Session SP hết hạn giữa flow | Thường phải bắt đầu login mới hoặc hiển thị lỗi có thể khôi phục | TTL, session state, IdP session |
| User mở nhiều tab | Có thể nhầm đích/correlation nếu state dùng chung | RequestCache và SAML repository theo giao dịch |
| User gửi link POST/PUT bảo vệ | Không replay hành động gây tác dụng phụ | Thiết kế GET/resume flow, xác nhận lại |
| URL sau login có query chứa token | Tránh ghi token vào URL/log; thiết kế token management riêng | RequestCache logging, redirect strategy |
| Proxy tạo URL `http://internal:8080` | URL khôi phục/ACS có thể sai | Trusted forwarded headers, base URL, HTTPS |
| User logout SP và truy cập deep link mới | Login lại nếu không có session; không tái dùng stale RelayState | Session invalidation, one-time handle |
| IdP-initiated login không có request | Chỉ chấp nhận nếu policy rõ, dùng fallback/allow-list | Unsolicited response/login fixation risk |

Khi có “login thành công nhưng sai trang”, nên điều tra RequestCache/success handler trước. Khi có “SAMLResponse bị từ chối”, điều tra AuthnRequest/RelayState/correlation và các validation trên ACS trước.

## 17. Login CSRF, session fixation và replay

### Login CSRF

Đây là việc làm browser nạn nhân nhận một kết quả đăng nhập mà nạn nhân **không khởi tạo giao dịch phù hợp**, có thể bị đăng nhập dưới danh tính của kẻ tấn công. Vì vậy cần kiểm tra các liên kết giữa browser, AuthnRequest, SAML Response và session trước khi chấp nhận.

Chỉ kiểm tra “Response có chữ ký của IdP” có thể chưa đủ để chứng minh response thuộc login do browser đó yêu cầu. Cần xử lý `InResponseTo`, request repository, session binding và profile IdP-initiated/unsolicited một cách phù hợp.

### Session fixation

Sau khi xác thực thành công, cần bảo đảm session được quản lý theo chính sách chống session fixation của Spring Security. Nếu sử dụng custom authentication filter, response handler hoặc SessionAuthenticationStrategy, đừng bỏ qua các bước mặc định có tác dụng đổi session ID/khởi tạo SecurityContext.

### Replay

Một RelayState đã dùng để lấy đích thường không nên có thể dùng lại vô hạn. Với trạng thái cache tùy chỉnh:
- Gắn TTL ngắn theo login transaction.
- One-time consume bằng thao tác atomic.
- So request ID và tenant/registration.
- Không cấp quyền từ token tự thân.
- Cleanup khi logout, timeout hoặc authentication failure.

Đối với response SAML, kiểm tra thời hạn, subject confirmation và cơ chế chống replay **không thể thay bằng** một bộ đếm RelayState đơn giản.

## 18. Bảo mật redirect sau login trên Spring Security

`SavedRequestAwareAuthenticationSuccessHandler` có khả năng khôi phục URL gốc, nhưng ứng dụng cần quyết định cách xử lý query/host cụ thể trong môi trường reverse proxy:

1. Cấu hình **public canonical URL** cho ứng dụng, chỉ tin `Forwarded`/`X-Forwarded-Host` từ reverse proxy tin cậy.
2. Kiểm tra host được chấp nhận ở ingress/application; không để một request Host header giả tạo URL tuyệt đối dùng trong redirect.
3. Nếu dùng custom success handler, chỉ cho redirect nội bộ hoặc URL nằm trong allow-list chặt và được chuẩn hóa.
4. Không dựa vào `Referer` của browser hoặc một query `?returnUrl=` không được validate để ghi đè SavedRequest.
5. Không ghi nguyên authorization code, SAMLResponse, assertion, RelayState, cookie hoặc private key vào log sản xuất.
6. Bảo vệ trang đích bằng authorization sau login; chẳng hạn user không sở hữu order 42 vẫn bị 403/404 dù SavedRequest đưa họ trở lại đúng path.
7. Thận trọng với custom “always redirect to dashboard” vì có thể phá UX deep link mà không tạo thêm tính an toàn.

Nếu yêu cầu nghiệp vụ cần redirect sang **một ứng dụng khác**, hãy sử dụng hợp đồng integration riêng, destination allow-list với origin cố định, hoặc tạo flow SSO sang ứng dụng kia; đừng tùy tiện nhận URL ngoài origin từ RelayState.

## 19. Cách kiểm thử bằng browser và HTTP trace

**Chuẩn bị:** một SP test có URL bảo vệ, IdP test đã cấu hình và browser độc lập. Không kiểm thử với SAML assertion thật trên công cụ chia sẻ công khai.

### Test A: deep link trước đăng nhập

1. Xóa/đặt lại phiên test SP, mở browser Network → Preserve log.
2. Mở `https://app.example.org/portal/orders/42?tab=history`.
3. Quan sát response từ SP khi chưa xác thực: redirect tới login/SAML start, session cookie và URL bắt đầu.
4. Quan sát `GET /saml2/authenticate/corp`, tiếp theo request tới IdP có `SAMLRequest` và có thể có `RelayState`.
5. Sau IdP login, quan sát browser POST `SAMLResponse` về đúng ACS của SP cùng RelayState mà IdP đã chuyển lại.
6. Chỉ khi SP xác minh thành công, browser mới nhận redirect quay về `/portal/orders/42?tab=history`.
7. Refresh trang đích: không cần login lại khi phiên SP hợp lệ; vẫn phải kiểm tra quyền của user với order 42.

**Kỳ vọng:** URL gốc được khôi phục, không có redirect tới domain lạ, không có request SAML lỗi và nội dung bảo vệ chỉ hiển thị sau login hợp lệ.

### Test B: login trực tiếp

Mở `/saml2/authenticate/corp` từ trang công khai khi không có SavedRequest. Sau login nên tới fallback `/portal` theo ví dụ cấu hình, không tới một URL ngẫu nhiên từ RelayState.

### Test C: thay RelayState

Dùng test harness kiểm soát được môi trường, thay RelayState inbound thành giá trị không tồn tại, giá trị của flow khác hoặc chuỗi dài. **Kết quả an toàn:** không dùng biến bị thay đổi làm URL đích, không bỏ validation SAML/Request ID. Tùy repository/policy, authentication phải bị từ chối hoặc đích custom bị bỏ và fallback, nhưng không được “nhảy” tới website tùy ý.

### Test D: callback không còn session

Tái hiện bằng cách để cookie SP không được gửi trong callback POST hoặc session server hết hạn. Kiểm tra lỗi báo thiếu request correlation; đừng tự động nhận unsolicited response chỉ để test pass. Ghi rõ SameSite trên cookie và trạng thái store.

### Test E: replay

Một response hoặc RelayState đã sử dụng không được tái sử dụng để tạo login không được yêu cầu hoặc đi tới target được lưu từ phiên khác. Quan sát logic consume và giao dịch một lần nếu có custom server-side store.

### Test F: nhiều tab

Mở hai deep link khác nhau trong cùng browser, khởi tạo hai login gần nhau, hoàn tất theo thứ tự khác nhau. Kiểm tra ứng dụng có chuyển đúng tab/URL, có thể hiển thị lỗi tương quan phù hợp, và không chia sẻ nhầm trạng thái nhạy cảm.

### Test G: proxy/host

Lặp lại trên public HTTPS domain qua reverse proxy. Đảm bảo `Location`, ACS và cookie dùng đúng scheme/host; không xuất hiện URL nội bộ như `http://localhost:8080`.

**Không đưa vào báo cáo công khai:** `SAMLResponse` gốc, cookie phiên, RelayState thực, SAML assertion, token, URL có dữ liệu cá nhân. Với HAR/log, hãy redact giá trị nhạy cảm và chỉ lưu method, path đã làm sạch, status, thời điểm, host.

## 20. Bảng chẩn đoán nhanh

| Triệu chứng | Vùng lỗi khả dĩ | Việc cần làm |
| --- | --- | --- |
| Login thành công nhưng luôn về `/portal` | SavedRequest không có, handler buộc default | Kiểm tra `alwaysUseDefaultTargetUrl`, RequestCache và cách khởi tạo login |
| Login thành công nhưng về URL của tab khác | SavedRequest bị thay trong multi-tab | Xem cơ chế lưu theo phiên/giao dịch, test thứ tự callback |
| Login thành công nhưng URL sai host/protocol | Host/forwarded headers | Kiểm tra proxy được tin và URL canonical |
| IdP không trả lại RelayState | IdP/binding/integration | So request/response và cấu hình IdP, không bịa giá trị |
| RelayState bị cắt/ngắn | Giới hạn bên IdP, encoding | Kiểm tra độ dài **byte** (80 byte theo chuẩn), giá trị ASCII/URL encoding |
| RelayState khác nhưng app vẫn redirect ngoài domain | Custom handler không validate | Bỏ xử lý target trực tiếp, dùng opaque handle + allow-list |
| SAMLResponse không có request tương ứng | Session mất, IdP-initiated hoặc correlation fail | Xem `InResponseTo`, repository, session/cookie SameSite |
| Response ký hợp lệ nhưng login fixation | Chấp nhận response của flow không thuộc browser | Ràng buộc session/request, policy unsolicited, không tin cache key toàn cục |
| POST ACS báo 403 | Filter chain/CSRF hoặc validation | Phân biệt CSRF từ authentication failure, không disable toàn cục |
| Trang deep link 403 sau login | Authorization không cho user | Phân quyền tài nguyên, không sửa RelayState |
| Query URL gốc biến mất | Success handler/custom redirect bỏ query | Dùng SavedRequest URL/URI xây dựng đúng, test query |
| Redirect loop sau login | Session cookie không được lưu, chain không nhận Authentication | So cookie/SP session, host/path/secure, login success |
| TargetUrlParameter bị lợi dụng | Open redirect | Tắt tham số tùy ý hoặc validate theo allow-list nghiêm ngặt |
| RelayState không còn khi timeout | TTL quá ngắn, cache bị evict | Policy hết hạn/hướng bắt đầu login lại; không bỏ checks |
| Dữ liệu SAML xuất hiện trong access log | Logging quá rộng | Redact hoặc tắt ghi raw query/body chứa dữ liệu nhạy cảm |

## 21. Bài tập tự kiểm tra

**Bài 1.** User chưa login mở `/portal/orders/42`. Sau SAML response hợp lệ, SP chuyển họ về `/portal`. Hãy nêu hai cơ chế nên kiểm tra trước.

**Đáp án:** (1) `RequestCache` có lưu SavedRequest khi truy cập URL bảo vệ không? (2) `SavedRequestAwareAuthenticationSuccessHandler` có dùng cùng cache hay bị cấu hình `alwaysUseDefaultTargetUrl=true` không? RelayState không nhất thiết chứa URL gốc.

**Bài 2.** Request đi IdP có `RelayState=xyz`, response quay về `RelayState=abc`. Khi nào SP được dùng “abc” làm đích?

**Đáp án:** không dùng trực tiếp làm URL vì không phải giá trị đã phát cho giao dịch. Phải xử lý mismatch theo chính sách bảo mật và correlation; response SAML cần được xác minh độc lập. Với custom opaque store, không tìm thấy đúng handle thì không có target hợp lệ.

**Bài 3.** IdP trả đúng RelayState, SAMLResponse đã ký, nhưng cookie SP không có trong ACS POST. Có chắc login thành công không?

**Đáp án:** không. Spring SP có thể không tìm thấy AuthnRequest session để so `InResponseTo`. Chữ ký/RelayState đúng chưa chứng minh browser có request tương ứng trong session; cần phân tích SameSite, session store và request repository.

**Bài 4.** Người dùng nhập `https://evil.example.org` vào `?returnUrl=`, hệ thống cho chuyển tới đó sau SAML login. Đây là lỗi gì?

**Đáp án:** **open redirect**. Không tin URL ngoài do user/RelayState cung cấp; dùng allow-list route/opaque server-side state và kiểm soát origin.

**Bài 5.** Có nên chứa JSON gồm email, role, JWT, URL và browser cookie trong RelayState để khỏi cần session không?

**Đáp án:** không. RelayState có giới hạn byte, đi qua browser, có thể bị sửa/quan sát và không phải kho chứng thực. Giữ opaque handle ngắn, lưu dữ liệu tối thiểu phía server và bảo vệ thông tin xác thực đúng lớp.

**Bài 6.** Phân biệt hai lỗi: (A) SAMLResponse bị từ chối vì thiếu request trong repository và (B) SAML login thành công nhưng không còn URL gốc.

**Đáp án:** (A) thiếu hoặc không khớp **AuthnRequest/SAML correlation**, điều tra session/Saml2AuthenticationRequestRepository; (B) mất **SavedRequest** hoặc cấu hình success handler/RequestCache, điều tra điều hướng sau login.

**Bài 7.** User bắt đầu SAML login bằng nút tại homepage rồi về `/portal`. Đây có phải lỗi RelayState không?

**Đáp án:** không. Không có deep link được bảo vệ trước đó thì không có SavedRequest; `/portal` là fallback hợp lý.

**Bài 8.** RelayState gồm 36 ký tự ASCII và assertion được gửi qua POST. Chữ ký XML trên assertion có tự bảo đảm RelayState không bị sửa không?

**Đáp án:** không. RelayState là form field riêng; cần bảo vệ state bằng cơ chế riêng và đối chiếu giao dịch. Trong Redirect binding có ký query, RelayState có thể nằm trong chuỗi được ký theo chuẩn/errata, nhưng không suy tương đương cho POST.

## 22. Checklist triển khai

- [ ] Đã xác định URL deep link mong khôi phục và điều kiện authorization của route.
- [ ] Biết rõ RelayState, AuthnRequest/InResponseTo và SavedRequest là ba đối tượng khác nhau.
- [ ] `RelayState` là giá trị ngắn, opaque, dưới **80 byte**, không chứa secret/thông tin người dùng.
- [ ] IdP chuyển lại RelayState đúng nguyên giá trị trong SP-initiated flow.
- [ ] SAML Response/Assertion được kiểm tra chữ ký, issuer, audience, recipient/destination, thời hạn, correlation trước khi tạo Authentication.
- [ ] RequestCache lưu request ban đầu khi user đi vào URL bảo vệ; success handler được cấu hình khôi phục đích.
- [ ] Có fallback an toàn khi login trực tiếp hoặc không có SavedRequest.
- [ ] Không bật target URL parameter hoặc đọc raw Referer/RelayState để redirect ngoài miền.
- [ ] Nếu dùng custom token store, có session/browser binding, TTL, one-time consume, registration/request ID correlation, kiểm soát replay.
- [ ] Đã đánh giá trường hợp IdP-initiated login và unsolicited response riêng; không mặc nhiên tin request không do browser khởi tạo.
- [ ] Cookie/session phù hợp với cross-site POST ACS, SameSite/Secure và multi-node.
- [ ] Đã kiểm thử nhiều tab, timeout, login thất bại, query path, quyền truy cập và host header/proxy.
- [ ] Đã ẩn SAMLResponse, assertion, cookie, RelayState và dữ liệu cá nhân trong log/HAR.

## 23. Ghi nhớ

**RelayState giúp mang ngữ cảnh của SAML flow qua IdP; RequestCache giữ HTTP request ban đầu; AuthnRequest/InResponseTo ràng buộc phản hồi với giao dịch SAML.** Sau khi xác minh SAML thành công, success handler có thể lấy SavedRequest để đưa browser trở về deep link. Muốn giữ URL sau đăng nhập mà vẫn an toàn, **đừng biến RelayState thành một URL redirect bất kỳ do browser kiểm soát**.

### Tài liệu kỹ thuật

- Spring Security — Producing SAML AuthnRequests, HttpSessionSaml2AuthenticationRequestRepository và CacheSaml2AuthenticationRequestRepository: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Servlet Architecture / Saving Requests Between Authentication: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security API — SavedRequestAwareAuthenticationSuccessHandler: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html
- Spring Security API — RequestCache: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html
- Spring Security — SAML 2.0 Login Overview: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- OASIS — SAML 2.0 Bindings, mục 3.4.3 và 3.5.3 RelayState: https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf
- OASIS — SAML 2.0 Approved Errata E1 (RelayState thuộc chữ ký Redirect query): https://docs.oasis-open.org/security/saml/v2.0/sstc-saml-approved-errata-2.0-cd-02.html
