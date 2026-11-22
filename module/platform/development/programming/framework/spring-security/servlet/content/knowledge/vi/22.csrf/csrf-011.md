# Phân tích CSRF cho API dùng cookie, HTTP Basic hoặc Bearer header

## 1. CSRF thực sự phụ thuộc vào điều gì?

**Cross-Site Request Forgery (CSRF)** là tình huống một trang do kẻ tấn công kiểm soát khiến trình duyệt của nạn nhân gửi yêu cầu đến ứng dụng mà nạn nhân đã đăng nhập. Máy chủ nhìn thấy thông tin xác thực hợp lệ nhưng không xác nhận được thao tác có thực sự do người dùng chủ động thực hiện trên giao diện đáng tin cậy hay không.

Điều kiện quan trọng không phải ứng dụng gọi là “REST API”, “stateless” hay token có định dạng JWT. Cần hỏi **trình duyệt có tự đính kèm thông tin xác thực khi một nguồn không tin cậy kích hoạt request không?**

Một CSRF điển hình cần đồng thời:

1. Người dùng có trạng thái đăng nhập/thông tin xác thực mà trình duyệt có thể tự gửi đến đích.
2. Kẻ tấn công có thể tạo một request mà trình duyệt sẽ gửi (ví dụ một biểu mẫu HTML).
3. Endpoint có tác dụng thay đổi dữ liệu hoặc trạng thái, và không kiểm tra bằng chứng độc lập về ý định của người dùng.
4. Cookie hoặc credential thực sự được trình duyệt đính kèm theo các quy tắc hiện hành; nếu bị SameSite hoặc cơ chế khác chặn, kịch bản cụ thể đó không thành công.

Ví dụ, trang độc hại có thể gửi form:

~~~html
<form action="https://shop.example/api/address" method="post">
  <input type="hidden" name="address" value="Dia chi cua ke tan cong">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Đây là ví dụ về **cách tạo request**, không phải một khai thác chắc chắn thành công: endpoint phải chấp nhận dữ liệu form và credential phải được gửi. Kẻ tấn công thường **không cần đọc phản hồi**. Vì vậy cơ chế *same-origin policy* ngăn đọc dữ liệu và việc không bật CORS không tự động chặn CSRF từ một form hợp lệ.

**Phân biệt:** CSRF lợi dụng quyền xác thực tự động của trình duyệt. XSS là thực thi JavaScript trái phép trong origin tin cậy; XSS có thể đọc hoặc sử dụng CSRF token mà ứng dụng cho phép JavaScript truy cập, nên chống CSRF không thay thế chống XSS.

## 2. Ma trận quyết định theo cơ chế gửi credential

| Cách API xác thực | Trình duyệt tự gửi credential từ một request do trang khác kích hoạt? | Kết luận đối với CSRF |
| --- | --- | --- |
| Session cookie (ví dụ `JSESSIONID`) | **Có**, nếu quy tắc cookie, SameSite và chính sách trình duyệt cho phép | **Có nguy cơ**; cần CSRF defense cho thao tác thay đổi trạng thái |
| JWT/access token đặt trong cookie | **Có**, với các điều kiện cookie tương tự | **Có nguy cơ**, dù token là JWT và backend không lưu session |
| HTTP Basic do trình duyệt quản lý/cache | **Có thể có**: trình duyệt có thể tự gửi `Authorization: Basic ...` trong phạm vi xác thực đã ghi nhớ | **Có nguy cơ** khi truy cập qua browser; không nên mặc định tắt CSRF chỉ vì “stateless Basic” |
| Bearer token do JavaScript chủ động lấy rồi đặt vào `Authorization: Bearer ...` | **Không tự động**: form, ảnh hoặc điều hướng đến trang đích không biết token để điền header | **Thông thường không có nguy cơ CSRF cổ điển** nếu endpoint chỉ chấp nhận Bearer header và không có đường xác thực tự động khác |
| Bearer token chỉ tồn tại ở app native, CLI hoặc máy chủ gọi máy chủ | Không có cơ chế browser ambient credentials | CSRF trên trình duyệt không phải mối đe dọa trực tiếp của client đó |
| Bearer token nằm trong cookie rồi được gateway/BFF dùng để xác thực | **Có** với cookie mà browser gửi | Đánh giá như **cookie**, không dựa vào chữ “Bearer” ở bước xử lý phía máy chủ |

Quy tắc suy luận là **xem từng endpoint và từng cách nó chấp nhận credential**. Một API chấp nhận cả Bearer header lẫn session cookie có thể vẫn dễ bị CSRF qua đường cookie, dù request hợp lệ của SPA thường sử dụng Bearer.

### 2.1. Cookie: session hay JWT đều cần xét CSRF

Một trang bên ngoài có thể khiến browser gửi request đến ứng dụng. Khi cookie xác thực đi kèm, phía máy chủ chỉ thấy người dùng đã xác thực. Thuộc tính `HttpOnly` giúp ngăn JavaScript đọc cookie nhưng **không ngăn browser tự gửi cookie**, vì thế không giải quyết CSRF. Cookie chứa JWT cũng vậy: định dạng token không thay đổi cơ chế vận chuyển.

Các yếu tố giảm rủi ro:

- **CSRF token kiểu synchronizer**: máy chủ liên kết token với phiên, render hoặc cung cấp token cho client hợp lệ và đối chiếu trên các request làm thay đổi trạng thái. Token cần khó đoán, đúng phiên, không dựa đơn thuần vào credential tự động gửi.
- **Double-submit cookie**: client gửi cùng một token qua cookie và header/field riêng. Với biến thể không lưu server-side, nên dùng token có chữ ký/ràng buộc với phiên; kiểu so sánh hai giá trị do cookie bên ngoài có thể bị can thiệp, đặc biệt khi có subdomain không đáng tin.
- **SameSite cookie**: giúp giảm yêu cầu cross-site nhưng có giới hạn. `Strict` chặn gửi cookie trong nhiều ngữ cảnh cross-site; `Lax` thường cho phép điều hướng top-level dùng phương thức an toàn như GET, không cho POST cross-site thông thường; `None; Secure` cho phép gửi cross-site theo các chính sách cookie hiện hành. Một số trình duyệt có ngoại lệ đối với cookie mới được đặt khi ứng dụng **bỏ trống** thuộc tính SameSite, nên hãy cấu hình tường minh.
- **Kiểm tra Origin/Referer hoặc Fetch Metadata** như lớp bổ sung, đặc biệt cho endpoint nhạy cảm. Không bỏ qua lỗi cấu hình host, proxy và allowlist.
- **Không biến GET/HEAD thành thao tác ghi**. Chỉ đổi phương thức thành GET để né CSRF token là lỗi thiết kế.

Lưu ý: **same-site không đồng nghĩa same-origin**. Hai subdomain có thể cùng “site” nhưng khác origin; ứng dụng cần xét cả trường hợp một subdomain bị chiếm hoặc không đáng tin. Cookie có `SameSite=Lax` hay `Strict` không phải giấy phép để bỏ kiểm tra ý định cho mọi tác vụ nhạy cảm.

### 2.2. HTTP Basic: phụ thuộc ai gắn Authorization

Trong cơ chế Basic do browser quản lý, sau khi người dùng xác thực, browser có thể lưu thông tin và tự áp dụng cho request thuộc protection space tương ứng. Trang độc hại không cần biết mật khẩu; nếu browser tự bổ sung header Basic cho request đến API thì điều kiện CSRF tương tự cookie. SameSite chỉ kiểm soát cookie, **không kiểm soát Basic Authorization**.

Ngược lại, khi một script hoặc CLI mỗi lần đều **chủ động** gắn `Authorization: Basic ...` và browser không có credential được lưu dùng tự động, request từ website độc hại không có sẵn header đó. Đừng kết luận chỉ từ tên scheme; kiểm tra luồng browser thực tế, cách lưu/nhớ Basic và các fallback xác thực.

API dùng Basic thường được mô tả là “stateless”, nhưng **stateless không đồng nghĩa an toàn trước CSRF**. Nếu hỗ trợ browser và Basic được tự gửi, bảo vệ CSRF cho các phương thức thay đổi trạng thái hoặc thiết kế lại cơ chế nhận credential.

### 2.3. Bearer trong Authorization header: khi nào thường không cần CSRF token?

Ví dụ SPA tải access token rồi chủ động gửi:

~~~http
POST /api/orders HTTP/1.1
Host: api.example
Authorization: Bearer eyJ...
Content-Type: application/json

{"productId":42}
~~~

Một form HTML từ website khác không thể tự điền `Authorization: Bearer ...`. JavaScript của website độc hại cũng không được tự đọc biến, bộ nhớ hay localStorage của origin ứng dụng. Nếu nó thử gửi cross-origin fetch với header `Authorization`, request thường phải qua CORS preflight; nhưng ngay cả khi server bật CORS, attacker vẫn phải có **token hợp lệ** để xác thực.

Vì vậy, có thể **không dùng CSRF token** cho route thật sự chỉ nhận access token từ Bearer header do client chủ động gửi, với điều kiện không nhận session cookie, HTTP Basic tự động hoặc cookie-based fallback trên cùng route. Điều này **không** nói Bearer là “an toàn tuyệt đối”: lưu token trong localStorage có rủi ro bị lấy khi XSS; dùng cookie để giữ refresh token kéo theo CSRF cho endpoint làm việc với cookie; CORS cấu hình sai có thể làm tăng khả năng lộ dữ liệu. Phải xử lý XSS, lưu token, phân quyền, TLS và cấu hình CORS độc lập.

Một mô hình BFF có thể sử dụng Bearer **giữa BFF và API**, trong khi browser xác thực với BFF bằng cookie. Khi đó endpoint BFF nhận request từ browser vẫn thuộc **mô hình CSRF của cookie**.

## 3. Vì sao CORS, Content-Type và SameSite không thay thế CSRF defense?

**CORS** chủ yếu quy định script từ origin khác có được truy cập phản hồi hoặc gửi các request cross-origin cần preflight hay không. Một form HTML gửi kiểu `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain` thường không cần CORS preflight. Server có thể đã thực hiện thay đổi trạng thái dù browser không cho attacker đọc response.

API chỉ nhận `application/json` và đòi một custom header làm cho một số request cross-origin phải preflight. Đây là **rào cản bổ trợ**, nhưng phải kiểm soát Content-Type thực sự, không tự parse kiểu dữ liệu khác, không cho phép preflight từ origin tùy ý kèm credentials, và không mặc định mọi request đều có preflight. Header `Origin` và Fetch Metadata (ví dụ `Sec-Fetch-Site`) có thể tăng khả năng chặn request không mong muốn; các giá trị thiếu/cũ cần chính sách xử lý rõ ràng.

**SameSite** là thuộc tính cookie; nó không ngăn trường hợp HTTP Basic tự được browser gửi, không sửa endpoint thực hiện ghi bằng GET và không đảm bảo phân biệt được request từ subdomain cùng site nhưng khác origin.

**CSRF token** phải được server xác thực, thường nằm ở header hoặc body của request thay đổi trạng thái. Đừng đặt token trong URL vì dễ lọt vào log, history hay Referer. Nếu cung cấp token qua endpoint JSON, chỉ để client tin cậy đọc được, không cấu hình CORS credentials cho origin lạ và tránh cache dùng chung.

## 4. Áp dụng cho Spring Security Servlet

Trong ứng dụng Servlet dùng Spring Security, `CsrfFilter` kiểm tra CSRF khi cơ chế CSRF được bật; cấu hình mặc định bảo vệ các HTTP method không thuộc nhóm an toàn `GET`, `HEAD`, `OPTIONS`, `TRACE`. Các method thay đổi trạng thái như `POST`, `PUT`, `PATCH`, `DELETE` cần token hợp lệ trừ khi được loại trừ có chủ đích. Khi thiếu hoặc sai token, thường nhận **HTTP 403** trước khi đến handler nghiệp vụ.

Với ứng dụng dùng session/cookie, Spring Security có `HttpSessionCsrfTokenRepository` để lưu token theo phiên; browser vẫn có thể giữ cookie xác thực ở chế độ `HttpOnly`. Không cần tắt CSRF chỉ vì frontend là SPA hay đường dẫn bắt đầu bằng `/api/`.

Mẫu cấu hình sau **là một đoạn tích hợp trong dự án Spring Boot 3 / Spring Security 6+, Java 17+**, có Spring Web, Spring Security và OAuth2 Resource Server. Route `/api/token/**` chỉ nhận Bearer JWT, còn các route browser/session/Basic giữ CSRF. Dự án phải tự cấu hình `JwtDecoder` (issuer/JWK) và người dùng thực tế; đây không phải một file Java độc lập để chạy bằng `javac`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    @Order(1)
    SecurityFilterChain bearerApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/token/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserApi(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/csrf").permitAll()
                .anyRequest().authenticated())
            .csrf(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Giải thích ranh giới:

- `@Order(1)` chọn chain Bearer **trước** cho `/api/token/**`; chain này không đăng ký form login/Basic và dự kiến không dùng cookie để xác thực. Tắt CSRF tại chain này **chỉ phù hợp nếu giả định đó đúng**. Cần rà lại filter/entry point khác, reverse proxy và bất kỳ cơ chế fallback nào.
- `@Order(2)` là chain còn lại; nó cho phép session login và HTTP Basic từ browser nên **giữ CSRF**. Không tắt CSRF toàn cục chỉ vì hệ thống có một số API Bearer.
- `SessionCreationPolicy.STATELESS` áp dụng cho Bearer chain; bản thân chính sách stateless không chứng minh API miễn nhiễm CSRF.
- Với endpoint như webhook cần bỏ qua CSRF vì nhận yêu cầu trực tiếp từ hệ thống khác, hãy giới hạn ngoại lệ đúng endpoint và xác minh chữ ký/xác thực riêng. Không dùng `/api/**` làm ngoại lệ bao trùm khi trong đó vẫn có cookie/Basic.

### 4.1. Cấp CSRF token cho frontend dùng session/cookie

Với repository theo phiên mặc định, một endpoint GET có thể cho SPA lấy tên header và token. Controller minh họa sau thuộc dự án có Spring MVC; `CsrfFilter` cần chạy trên `/api/csrf`:

~~~java
import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {
    @GetMapping("/api/csrf")
    public Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken)
            request.getAttribute(CsrfToken.class.getName());
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
~~~

Lời gọi `getToken()` cũng khiến token deferred được materialize khi cần (hành vi Spring Security hiện đại). Frontend cùng origin sau khi xác thực lấy token rồi gửi kèm thao tác ghi:

~~~javascript
const csrfResponse = await fetch("/api/csrf", {
  credentials: "same-origin"
});
if (!csrfResponse.ok) throw new Error("Cannot obtain CSRF token");
const { headerName, token } = await csrfResponse.json();

const response = await fetch("/api/orders", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ productId: 42 })
});
if (!response.ok) throw new Error("Order request rejected");
~~~

Đoạn JavaScript chỉ minh họa request đến endpoint nghiệp vụ `/api/orders`; ứng dụng cần có controller, dữ liệu và quyền phù hợp. Vì session/token có thể thay đổi sau login/logout hoặc khi token bị xoay vòng, client nên **lấy lại CSRF token sau khi đăng nhập hoặc đổi phiên**, xử lý 403 có kiểm soát và tránh ghi token vào log.

Nếu chọn `CookieCsrfTokenRepository.withHttpOnlyFalse()` để SPA đọc cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN`, lưu ý:

1. Cookie **CSRF token** có thể cần JavaScript đọc; điều đó **không có nghĩa** phải bỏ `HttpOnly` khỏi cookie xác thực.
2. Spring Security 6 có cơ chế che/mask token để giảm rủi ro BREACH, cùng xử lý deferred token. Đọc token **thô** từ cookie rồi gửi vào header cần `CsrfTokenRequestHandler` tương thích (mô hình SPA do Spring Security hướng dẫn), không thể luôn chỉ đổi repository là đủ.
3. Cookie CSRF cần cấu hình `Secure`, `Path`, `Domain` và chính sách SameSite phù hợp. Không tin cậy subdomain có quyền ghi cookie cho domain cha; cân nhắc ràng buộc token với phiên và host-only cookie.

### 4.2. Nếu chỉ có Bearer header trong một API riêng

Một API resource server thuần Bearer không có đăng nhập bằng cookie/Basic tự động có thể tắt CSRF trên đúng security chain, như `bearerApi` trong ví dụ. Sau đó xác thực access token, phạm vi quyền (scope/authority), thời hạn, chữ ký, issuer/audience và chống XSS/lộ token vẫn phải được bảo đảm.

**Không nhầm lẫn:** token JWT được gửi trong `Cookie` thì đánh giá như cookie; token OAuth2 trong `Authorization: Bearer` do client tự gắn thì đánh giá như header. Câu “API dùng JWT nên tắt CSRF” thiếu thông tin về kênh vận chuyển và cơ chế browser.

## 5. Kiểm thử các tình huống và diễn giải kết quả

Hãy dùng một endpoint thay đổi trạng thái có authentication thực sự. Trong integration test, gửi cùng request với từng nhóm credential và kiểm tra dữ liệu server-side có bị thay đổi không, chứ không chỉ nhìn status code.

| Thử nghiệm | Dự kiến khi cấu hình đúng |
| --- | --- |
| Cookie/session hợp lệ, POST thiếu CSRF token | Bị chặn, thường `403 Forbidden`; dữ liệu không đổi |
| Cookie/session hợp lệ, token CSRF sai hoặc thuộc phiên khác | Bị chặn; dữ liệu không đổi |
| Cookie/session hợp lệ, CSRF token đúng và được gửi bằng header/field được hỗ trợ | Qua kiểm tra CSRF; kết quả tiếp theo tùy quyền và logic nghiệp vụ |
| Browser đã ghi nhớ Basic credential, POST bị kích hoạt từ origin lạ, thiếu CSRF token | Bị chặn nếu browser thực tế tự gửi Basic và route bật CSRF |
| Bearer-only endpoint, POST không có Bearer header | Bị từ chối ở bước xác thực, thường `401`; kết quả có thể phụ thuộc entry point |
| Bearer-only endpoint, Bearer hợp lệ, không có CSRF token | Có thể qua lớp CSRF vì chain không yêu cầu token; vẫn kiểm tra authz và nghiệp vụ |
| Endpoint hỗn hợp nhận cả cookie lẫn Bearer, POST từ trang lạ chỉ có cookie | Phải được bảo vệ theo đường cookie; không được dựa vào sự hiện diện của chế độ Bearer ở request khác |
| Login/logout hoặc thao tác nhạy cảm bằng GET | Thiết kế cần được sửa; không dùng GET có side effect để né kiểm tra CSRF |

Khi thử nghiệm bằng `curl`/Postman, nhớ rằng chúng **không tự tái hiện** quy tắc gửi cookie, cache Basic, SameSite và CORS của trình duyệt. Dùng DevTools/automated browser test để xác nhận cookie/header thật sự được gửi từ tình huống cross-site. Một POST thất bại vì thiếu credential hoặc bị SameSite chặn không chứng minh toàn bộ cấu hình CSRF an toàn.

Phân biệt trong log và test: `401` thường liên quan thiếu/sai xác thực; `403` có thể do CSRF **hoặc** thiếu quyền. Kiểm tra filter chain, exception, SecurityContext và có/không thay đổi dữ liệu để kết luận đúng nguyên nhân.

## 6. Quy trình quyết định cho một endpoint cụ thể

1. **Liệt kê mọi phương thức xác thực** route chấp nhận: session cookie, JWT cookie, cached Basic, Bearer header, proxy/BFF hay fallback. Đừng chỉ nhìn nhãn “JWT/REST/stateless”.
2. **Xác định client nào khởi tạo request:** browser, SPA, mobile, CLI, hệ thống server-to-server. Nếu có browser, kiểm tra credential có được gắn tự động khi nguồn khởi tạo là trang khác hay không.
3. **Đánh dấu request làm thay đổi trạng thái**, gồm login/logout, đổi mật khẩu, giao dịch, cấu hình và tác dụng phụ giấu trong GET.
4. **Nếu có đường ambient credential từ browser**, yêu cầu CSRF token hoặc một biện pháp kiểm chứng ý định đủ mạnh cho phương thức nguy hiểm; áp dụng SameSite, Origin/Fetch Metadata như lớp bổ sung.
5. **Nếu route chỉ nhận Bearer header do client chủ động gửi**, có thể loại trừ CSRF có chủ đích trên chain đó; kiểm tra cấu hình để chắc rằng không có cookie/Basic fallback.
6. **Thử nghiệm bằng cả request hợp lệ và request bị cưỡng ép**, kể cả origin/subdomain không tin cậy. Xác nhận không có ghi dữ liệu trong trường hợp bị chặn.

### Các sai lầm thường gặp

- “Dùng JWT là không có CSRF”: sai nếu JWT nằm trong cookie tự gửi.
- “HTTP Basic là stateless nên tắt CSRF”: sai khi browser nhớ và tự gửi Basic.
- “Đã `HttpOnly` thì hết CSRF”: `HttpOnly` chỉ giới hạn đọc cookie từ JavaScript.
- “Không bật CORS thì form độc hại không gửi được POST”: không đúng với các form đơn giản.
- “Chỉ cho JSON nên mặc nhiên an toàn”: còn phụ thuộc enforcement Content-Type, CORS/preflight, endpoint khác và phương thức nhập liệu.
- “`SameSite=Lax` bảo vệ mọi request”: còn top-level GET có side effect, same-site khác origin và chính sách browser.
- “Tắt CSRF cho tất cả `/api/**`”: có thể vô hiệu hóa bảo vệ cho API dùng session hoặc Basic.
- “Chỉ cần token hợp lệ, mọi tấn công khác đều hết”: CSRF token không chống XSS, đánh cắp token, phân quyền sai hoặc clickjacking.

**Nguyên tắc ghi nhớ:** Câu hỏi quyết định không phải “cookie, Basic hay Bearer nghe có an toàn không?”, mà là **browser có thể tự gửi credential được server tin tưởng khi attacker kích hoạt request hay không**. Với cookie và Basic được browser quản lý, hãy mặc định xét CSRF. Với Bearer header do ứng dụng chủ động đặt, thường không cần CSRF token cho route thật sự chỉ chấp nhận Bearer, nhưng luôn kiểm tra đường xác thực thực tế của endpoint.
