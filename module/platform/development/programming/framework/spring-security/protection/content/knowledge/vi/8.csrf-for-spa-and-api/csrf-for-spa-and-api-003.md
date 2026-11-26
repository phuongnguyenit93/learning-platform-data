# Ứng dụng stateless và các nguồn thông tin xác thực trình duyệt vẫn có thể tự gửi

## Mục tiêu bài học

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, có một nhầm lẫn thường dẫn đến cấu hình bảo mật sai: “API không tạo session trên máy chủ (**stateless**) thì chắc chắn không cần bảo vệ CSRF”. Kết luận này **không đúng**. Một ứng dụng có thể hoàn toàn không lưu phiên đăng nhập ở backend nhưng trình duyệt vẫn **tự gửi thông tin xác thực** cùng request, ví dụ JWT trong cookie. Khi đó, trang web bên ngoài có thể lợi dụng quyền đăng nhập của trình duyệt để kích hoạt thao tác ngoài ý muốn.

Bài học giải thích sự khác biệt giữa **trạng thái xác thực ở máy chủ** và **cách browser gửi credential**, trình bày các nguồn xác thực tự động, cách đánh giá CSRF trong kiến trúc SPA/API, cấu hình **Spring Security Servlet** và **Spring Security WebFlux (Reactive)**, cùng các kiểm thử và dấu hiệu xung đột với CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session.

Sau bài học, bạn có thể:

- Chứng minh vì sao **stateless không đồng nghĩa với miễn CSRF** bằng một ví dụ JWT trong cookie.
- Phân loại cookie phiên, cookie JWT, HTTP Basic, SSO, mTLS và Bearer header theo khả năng browser tự gửi.
- Đánh giá một endpoint nguy hiểm dựa trên **đường xác thực thực tế**, chính sách cookie, origin/site và hành vi máy chủ.
- Giữ hoặc bỏ kiểm tra CSRF có điều kiện trong các **SecurityFilterChain** Servlet và Reactive.
- Kiểm thử cả trường hợp thiếu/sai/đúng token lẫn đường xác thực cookie bị bỏ sót.

## 1. Stateless nói về máy chủ; CSRF nói về hành vi của trình duyệt

**Stateless authentication** thường có nghĩa backend không phải lưu một bản ghi session đăng nhập cho mỗi client giữa các request. Mỗi request mang đủ dữ liệu để server xác minh, chẳng hạn JWT đã ký hoặc opaque access token được kiểm tra với authorization server.

**CSRF (Cross-Site Request Forgery)** là việc bên tấn công khiến **trình duyệt của người dùng đang được xác thực** gửi request mà người dùng không chủ ý thực hiện. CSRF khai thác sự khác nhau giữa:

- **Request được xác thực**: backend nhận được credential hợp lệ.
- **Request do người dùng chủ ý phát sinh**: thao tác thật sự xuất phát từ UI/luồng tương tác đáng tin cậy.

Cookie phiên có thể làm request được xác thực nhưng không chứng minh ý định. Cookie JWT stateless cũng vậy.

### 1.1. Ví dụ: JWT stateless trong cookie

Giả sử API **https://api.example.com** xác thực JWT được ký bởi hệ thống và không có bảng session. Sau đăng nhập, server cấp:

~~~http
HTTP/1.1 200 OK
Set-Cookie: AUTH_TOKEN=eyJ...; Path=/; HttpOnly; Secure; SameSite=None
Content-Type: application/json

{"message":"signed in"}
~~~

Ở request tiếp theo, browser có thể tự gửi cookie theo các điều kiện cookie/chính sách browser:

~~~http
POST /api/payment-methods HTTP/1.1
Host: api.example.com
Cookie: AUTH_TOKEN=eyJ...
Content-Type: application/x-www-form-urlencoded

methodId=new-default
~~~

Backend chỉ cần **xác minh chữ ký, hạn dùng, issuer, audience và quyền của JWT**, không cần đọc một session từ database. Nhưng nếu website độc hại khiến browser gửi POST đã đính kèm cookie, backend vẫn thấy JWT hợp lệ. **Đây là CSRF trong hệ thống stateless.**

Nếu cookie dùng **SameSite=None**, browser có thể gửi trong nhiều bối cảnh cross-site được cho phép; nếu dùng **Lax/Strict**, phạm vi gửi có thể hẹp hơn. Dù vậy, thuộc tính SameSite không thay thế việc kiểm tra ý định đối với mọi kịch bản, nhất là các origin khác nhau nhưng cùng site.

### 1.2. So sánh với Bearer token do JavaScript gửi

Một SPA giữ access token trong bộ nhớ có thể gọi:

~~~javascript
await fetch("https://api.example.com/api/payment-methods", {
  method: "POST",
  credentials: "omit",
  headers: {
    "Content-Type": "application/json",
    Authorization: "Bearer " + accessToken
  },
  body: JSON.stringify({ methodId: "new-default" })
});
~~~

Nếu backend **chỉ** chấp nhận **Authorization: Bearer** và không nhận bất cứ cookie hoặc cơ chế browser-managed nào để xác thực, trang ngoài origin không tự đọc được token của SPA và không thể tạo request đã xác thực chỉ bằng cách gửi form. Trong trường hợp này, CSRF truyền thống thường không phải mối đe dọa chính. Tuy nhiên, XSS, rò rỉ token và lỗi phân quyền vẫn là các rủi ro quan trọng.

| Thuộc tính | JWT lưu trong cookie và API đọc cookie | JWT do JS gửi trong Bearer header |
| --- | --- | --- |
| Máy chủ có cần lưu session không? | Có thể **không** | Có thể **không** |
| Browser có thể tự gửi credential? | **Có**, nếu cookie phù hợp | **Không tự lấy** Bearer token đang nằm trong SPA |
| Một form HTML giả mạo có sẵn credential? | Có thể có cookie | Không có Bearer header do SPA chủ động tạo |
| Có thể có CSRF? | **Có** | Thường không, nếu thực sự chỉ Bearer |
| Vấn đề bảo vệ chính | CSRF, cookie policy, XSS, JWT validation, phân quyền | XSS, bảo vệ token, JWT validation, phân quyền, CORS |

**Điểm phân định là đường đưa credential đến API, không phải JWT có state hay không.**

## 2. Những nguồn xác thực browser có thể tự gửi

Không phải ứng dụng nào cũng sử dụng cookie. Trình duyệt, hệ điều hành và proxy đôi khi tham gia xác thực theo cách ứng dụng JavaScript không trực tiếp điều khiển.

| Nguồn xác thực | Cơ chế phát sinh request | Khi nào cần đánh giá CSRF? |
| --- | --- | --- |
| **JSESSIONID** hoặc session cookie của framework | Browser gửi cookie dựa vào domain, path, SameSite, Secure và loại request | Khi API chấp nhận session cookie để thực hiện thao tác |
| **JWT/access token trong cookie** | Browser gửi cookie; backend tự xác minh JWT không cần session | Khi cookie đủ để xác thực endpoint đổi trạng thái |
| **Refresh token trong cookie HttpOnly** | Browser có thể gửi đến endpoint refresh/rotate/logout | Khi endpoint dựa trên cookie có tác động đến trạng thái xác thực hoặc hành vi khác |
| **HTTP Basic / Digest đã được browser ghi nhớ** | Browser có thể dùng lại credentials đã lưu trong một protection space | Khi ứng dụng dựa vào xác thực browser-managed cho request có tác động |
| **Kerberos/Negotiate SSO** | Browser/hệ điều hành có thể tự thương lượng với origin được tin cậy theo chính sách | Khi server cho phép thao tác chỉ dựa vào SSO được gửi tự động |
| **Chứng chỉ client TLS (mTLS)** | Browser có thể trình chứng chỉ đã chọn cho server yêu cầu, phụ thuộc chính sách | Khi backend coi danh tính mTLS đủ để thực hiện thao tác từ browser |
| **Cookie ở reverse proxy/BFF** | Proxy xác thực cookie rồi chuyển danh tính/credential cho backend | Khi backend stateless nhưng browser vẫn xác thực qua proxy bằng cookie |
| **Bearer token chủ động thêm trong JavaScript** | Mã SPA tự gắn **Authorization: Bearer ...** | CSRF truyền thống thường thấp nếu không có cơ chế xác thực tự động thay thế |

Các cơ chế như **HTTP Basic, Negotiate và mTLS** phụ thuộc browser, môi trường và policy triển khai; không khẳng định mọi browser luôn tự gửi chúng trong mọi request cross-origin. Cần quan sát request thực tế và tái hiện trong môi trường kiểm thử.

### 2.1. Backend stateless nhưng gateway lại xác thực bằng cookie

Một kiến trúc phổ biến:

~~~mermaid
flowchart LR
    A["SPA trong trình duyệt"] -->|"Cookie đăng nhập"| B["Gateway / BFF"]
    B -->|"Header danh tính hoặc access token nội bộ"| C["API stateless"]
    D["Trang bên ngoài"] -.->|"Request có thể mang cookie"| B
    B --> E{"Kiểm tra CSRF và policy origin"}
    E -->|"Hợp lệ"| C
    E -->|"Không hợp lệ"| F["Từ chối request"]
~~~

API nội bộ có thể nhận Bearer token từ gateway và hoàn toàn không giữ session. Nhưng nếu gateway chỉ dựa trên cookie tự gửi để cấp quyền, **điểm cần phòng CSRF là ranh giới browser → gateway**, trước khi gateway cấp credential nội bộ hoặc thực hiện thao tác. Không thể kết luận an toàn chỉ vì code Java phía sau không đọc cookie.

### 2.2. “Có Authorization header” vẫn chưa đủ

Header **Authorization** có nhiều scheme:

~~~http
Authorization: Basic YWxpY2U6cGFzc3dvcmQ=
~~~

hoặc:

~~~http
Authorization: Bearer eyJ...
~~~

Đối với Basic/Digest, browser có thể quản lý credentials sau khi người dùng đăng nhập. Đối với Bearer do SPA tự thêm, browser không tự lấy giá trị từ bộ nhớ của SPA để thêm vào request của website khác. Vì vậy cần xem **ai tạo header** và **server có chấp nhận cách đăng nhập thay thế không**.

## 3. Phân biệt origin, site, SameSite và Fetch credentials

Để biết browser có gửi cookie hay không, phải phân biệt:

- **Origin** = scheme + host + port, ví dụ **https://app.example.com:443**.
- **Site** theo mô hình schemeful SameSite thường xét scheme và registrable domain. Hai subdomain **app.example.com** và **api.example.com** có thể **khác origin nhưng cùng site**.
- **SameSite** là chính sách cookie liên quan đến ngữ cảnh cùng site/khác site.
- **Fetch credentials mode** quyết định việc gửi credentials trình duyệt và chấp nhận credential trong response; đây là yếu tố **phía JavaScript gọi request**, không phải thuộc tính của JWT.

| Đường gọi | Khác origin? | Thường cùng site? | Hệ quả với cookie |
| --- | --- | --- | --- |
| **https://app.example.com** → **https://app.example.com** | Không | Có | Fetch mặc định **same-origin** có thể gửi cookie phù hợp |
| **https://app.example.com** → **https://api.example.com** | Có | Có | Thường cần **credentials: "include"** nếu muốn fetch gửi cookie; SameSite=Lax không tự chặn chỉ vì khác subdomain |
| **https://evil.example.com** → **https://api.example.com** | Có | Có | Nếu subdomain kém tin cậy, SameSite không tạo ranh giới bảo vệ đầy đủ |
| **https://attacker.test** → **https://api.example.com** | Có | Không | Cookie Lax/Strict chặn nhiều bối cảnh; cookie None được phép gửi tùy browser, request và chính sách third-party cookies |

### 3.1. Cookie thuộc tính nào có ý nghĩa?

| Cookie attribute | Ý nghĩa | Không giải quyết được |
| --- | --- | --- |
| **HttpOnly** | JavaScript không đọc cookie bằng **document.cookie** | Browser vẫn có thể tự gửi cookie theo chính sách |
| **Secure** | Chỉ gửi trên kết nối an toàn theo hành vi browser | Không chứng minh người dùng chủ ý phát sinh request |
| **SameSite=Strict** | Hạn chế mạnh cookie trong bối cảnh cross-site | Không phân biệt origin tin cậy và origin không tin cậy cùng site |
| **SameSite=Lax** | Hạn chế nhiều request cross-site không an toàn | Một số điều hướng cấp cao bằng GET vẫn mang cookie; GET không được tạo tác dụng phụ |
| **SameSite=None; Secure** | Cho phép cookie trong bối cảnh cross-site theo chính sách browser | Có thể mở rộng bề mặt CSRF và vẫn chịu chặn third-party cookies |
| **Domain** và **Path** | Giới hạn phạm vi browser gửi cookie | Cookie với Domain chia sẻ cho nhiều subdomain có thể tăng rủi ro cookie injection |

Cookie xác thực nên dùng **Secure**, **HttpOnly** và chính sách SameSite phù hợp; cân nhắc cookie host-only và tiền tố **__Host-** (đòi hỏi Secure, Path=/ và không đặt Domain) khi phù hợp kiến trúc. Không đổi **HttpOnly=false** cho cookie xác thực chỉ vì SPA cần CSRF token.

### 3.2. SameSite=Lax không phải biện pháp duy nhất

Với **SameSite=Lax**, nhiều cross-site POST sẽ không gửi cookie, nhưng một số điều hướng cấp cao GET vẫn có thể gửi. Nếu ứng dụng tạo đơn, hủy tài khoản, đổi email hoặc kích hoạt chuyển tiền bằng **GET**, CSRF có thể xảy ra dù cookie Lax. Ngoài ra, **cùng site không đồng nghĩa cùng origin**: một subdomain bị chiếm quyền có thể nằm trong cùng site với API.

Thực tế browser còn có sự khác nhau đối với cookie thiếu thuộc tính SameSite, mặc định Lax và thời gian ân hạn cho một số request sau khi tạo cookie. Do đó cần **kiểm thử hành vi thực**, không dựa hoàn toàn vào phỏng đoán.

## 4. CORS và JSON có vai trò gì trong đánh giá?

CORS kiểm soát khả năng JavaScript từ origin khác **gửi/đọc yêu cầu theo quy tắc browser**. CSRF lại tập trung vào việc kẻ tấn công có khiến browser **thực hiện hành động đã xác thực** hay không, thường không cần đọc phản hồi.

- Một **HTML form** có thể gửi POST với các kiểu body đơn giản mà không cần CORS preflight.
- Fetch gửi **Content-Type: application/json** hoặc header tùy biến như **X-CSRF-TOKEN** từ origin khác thường gây **OPTIONS preflight**.
- CORS từ chối preflight có thể ngăn request thực tế của đường gọi này, nhưng API vẫn phải từ chối các request trái phép bằng xác thực, phân quyền và CSRF khi cần.
- Nếu backend “API JSON” còn nhận **application/x-www-form-urlencoded**, **multipart/form-data** hoặc **text/plain** rồi tự diễn giải dữ liệu, trang tấn công có thể chọn dạng request không cần preflight.
- **CORS đúng** không bắt browser gửi cookie bị chặn bởi SameSite, Domain, Path, Secure hoặc third-party cookie policy.
- **CORS mở quá rộng**, nhất là phản chiếu Origin không kiểm soát và cho phép credentials, có thể làm lộ dữ liệu cho origin không đáng tin cậy; không dùng cấu hình này để “chữa lỗi” đăng nhập.

Ví dụ minh họa trên môi trường bạn được phép kiểm thử:

~~~html
<!-- Khả thi về mặt gửi request; có khai thác được hay không
     còn phụ thuộc cookie policy, loại body API nhận và kiểm tra CSRF. -->
<form action="https://api.example.com/api/preferences" method="post">
  <input type="hidden" name="publicProfile" value="true">
  <button type="submit">Submit</button>
</form>
~~~

Nếu ứng dụng stateless đọc JWT từ cookie và chấp nhận **form body**, form này có thể tạo thao tác đã xác thực trong những ngữ cảnh browser gửi cookie. Nếu API **chỉ** chấp nhận JSON và không có đường khác, form sẽ không đáp ứng hợp đồng; đó là một lớp phòng vệ có ích nhưng **không chứng minh toàn bộ API miễn CSRF**.

## 5. Sơ đồ quyết định: khi nào phải giữ CSRF?

~~~mermaid
flowchart TD
    A["Endpoint thay đổi trạng thái?"] -->|Không| B["GET/HEAD chỉ đọc và không tác dụng phụ"]
    A -->|Có| C{"Browser tự gửi credential được server chấp nhận?"}
    C -->|"Có: cookie JWT/session, Basic, SSO, mTLS, gateway cookie"| D["Đánh giá CSRF và bật phòng vệ phù hợp"]
    C -->|"Không: chỉ Bearer header do client chủ động gắn"| E["CSRF browser truyền thống thường không áp dụng"]
    D --> F["Token CSRF / Origin / SameSite / kiểm thử"]
    E --> G["JWT validation / authorization / chống XSS"]
    C -->|"Có nhiều đường xác thực"| H["Tách route/chain hoặc bảo vệ đường credential tự động"]
    H --> D
~~~

Các câu hỏi đánh giá cho một route cụ thể:

1. **Ai xác thực request?** Spring Security, API gateway, reverse proxy, BFF, filter tự viết hay một hệ thống SSO? Kiểm tra toàn bộ đường đi.
2. **Có credential nào tự gắn không?** Cookie phiên, cookie JWT, refresh cookie, Basic đã lưu, chứng chỉ client hoặc SSO.
3. **Endpoint tác động gì?** POST/PUT/PATCH/DELETE, login/logout, rotate refresh token, đổi cấu hình, cập nhật tài khoản; phát hiện GET gây thay đổi trạng thái.
4. **Browser nào được hỗ trợ?** SameSite, cookie scope, HTTPS, Credentials của Fetch, điều hướng/form, policy subdomain và third-party cookies.
5. **Có biện pháp chứng minh ý định?** CSRF token gắn với session hoặc cơ chế double-submit được bảo vệ tốt, kiểm tra Origin/Referer, Fetch Metadata và hợp đồng Content-Type nghiêm ngặt.
6. **Hệ thống có đường dự phòng không?** Bearer được ưu tiên nhưng thiếu Bearer thì backend nhận cookie? Gateway cấp Bearer nội bộ từ cookie? Những đường này phải được kiểm tra riêng.
7. **Kết quả thử có xác minh dữ liệu không?** Request bị từ chối chưa đủ nếu thao tác được thực hiện trước khi filter trả lỗi.

| Mô hình | Server lưu session? | Browser tự gửi credential? | Quyết định CSRF |
| --- | --- | --- | --- |
| Session cookie **JSESSIONID** | Thường có | Có | Bật CSRF cho thao tác không an toàn |
| JWT stateless lưu **AUTH_TOKEN** cookie | Không nhất thiết | Có | **Vẫn cần phòng CSRF** |
| Bearer JWT chỉ trong **Authorization** do SPA chủ động gửi | Không nhất thiết | Thường không | Có thể miễn CSRF cho riêng Bearer-only route sau khi xác minh |
| Bearer access token + refresh token cookie | Không nhất thiết | Có trên route refresh | Đánh giá các route Bearer và route cookie **riêng biệt** |
| API stateless phía sau BFF xác thực bằng cookie | API nội bộ không | Có ở cổng BFF | Giữ bảo vệ CSRF tại ranh giới browser → BFF |
| SSO browser-managed hoặc mTLS | Không nhất thiết | Có thể | Đánh giá theo browser/chính sách thực tế; không mặc định miễn CSRF |

## 6. Spring Security Servlet: STATELESS không tự tắt CSRF

Trong Servlet, **SessionCreationPolicy.STATELESS** cấu hình Spring Security không tạo **HttpSession** và không dùng nó để lấy **SecurityContext**. Quyết định này **không tự tắt CsrfFilter**, cũng không chứng minh cookie xác thực không tồn tại.

### 6.1. Cấu hình CSRF cho API dùng JWT trong cookie

Ví dụ dưới đây minh họa **phần phòng CSRF** cho API stateless dùng cookie. Ứng dụng phải bổ sung một **authentication filter** xác minh JWT cookie bằng cơ chế tin cậy trước khi coi request là đã đăng nhập. Đoạn code không tự triển khai filter JWT và không coi sự hiện diện của cookie là bằng chứng đủ để cấp quyền.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

@Configuration
class CookieJwtSecurityConfig {

    @Bean
    SecurityFilterChain cookieJwtApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    CookieCsrfTokenRepository.withHttpOnlyFalse())
                // Nhận token dạng raw từ header X-XSRF-TOKEN của SPA.
                .csrfTokenRequestHandler(
                    new CsrfTokenRequestAttributeHandler()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .anyRequest().authenticated())
            .build();
    }
}
~~~

**Cách hiểu đúng mã ví dụ:**

- **STATELESS** chỉ điều chỉnh việc dùng session cho security context; CSRF vẫn được bật.
- **CookieCsrfTokenRepository** lưu token CSRF trong cookie, tránh phụ thuộc vào HttpSession của server. Với **withHttpOnlyFalse()**, JavaScript cùng phạm vi cookie có thể đọc **XSRF-TOKEN**.
- **CsrfTokenRequestAttributeHandler** được chọn để chấp nhận raw token qua header **X-XSRF-TOKEN** trong luồng SPA này. Đây là lựa chọn có cân nhắc về cơ chế masking/BREACH nếu ứng dụng đồng thời nhúng token vào HTML; cần đối chiếu request handler của phiên bản Spring Security và cách hiển thị token.
- Cookie **JWT xác thực** vẫn phải **HttpOnly**, **Secure** và có SameSite thích hợp. Chỉ cookie **token CSRF** cần đọc bằng JavaScript trong biến thể này.
- Chain trên **chưa có authentication filter đọc/kiểm tra JWT từ cookie**; nếu không bổ sung một cách xác thực đúng, **/api/** sẽ không coi cookie JWT là đăng nhập hợp lệ. Authentication filter nên xử lý signature/issuer/audience/expiry, phân quyền và lỗi 401 theo thiết kế.

**Cảnh báo kiến trúc double-submit:** Khi CSRF token được lưu trong cookie và client gửi lại chính giá trị đó qua header, phải kiểm soát khả năng chèn/ghi đè cookie từ subdomain hoặc thành phần không đáng tin cậy. **CookieCsrfTokenRepository không tự chứng minh token được ký HMAC và ràng buộc với phiên đăng nhập**. Đối với hệ thống nhạy cảm, cân nhắc mẫu **signed double-submit token** gắn với danh tính/phiên theo khuyến nghị bảo mật, giới hạn phạm vi cookie và bảo vệ subdomain; hoặc thay đổi kiến trúc để sử dụng token đồng bộ được lưu server-side khi phù hợp.

### 6.2. Cấp token cho SPA đúng lúc

Spring Security có thể tải hoặc tạo token trì hoãn. SPA nên kích hoạt việc tạo token trước khi gửi request thay đổi trạng thái:

~~~java
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ApiCsrfController {

    @GetMapping("/api/csrf")
    Map<String, String> csrf(CsrfToken token) {
        // Gọi getToken() để token được hiện thực hóa.
        return Map.of(
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
~~~

Ví dụ client **cùng origin**:

~~~javascript
async function updatePreferences(settings) {
  const csrfResponse = await fetch("/api/csrf", {
    credentials: "same-origin"
  });
  if (!csrfResponse.ok) throw new Error("Cannot get CSRF token");
  const { headerName, token } = await csrfResponse.json();

  const response = await fetch("/api/preferences", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [headerName]: token
    },
    body: JSON.stringify(settings)
  });
  if (!response.ok) throw new Error("Update failed: " + response.status);
  return response;
}
~~~

Tùy yêu cầu ứng dụng, SPA cũng có thể đọc cookie **XSRF-TOKEN** và gửi header **X-XSRF-TOKEN** thay vì đọc token JSON. **Khi SPA ở app.example.com còn API ở api.example.com**, JS không đọc được cookie **host-only** do api.example.com cấp; endpoint trả JSON qua CORS chỉ cho origin tin cậy là một lựa chọn rõ ràng hơn.

**Không đưa token CSRF vào URL**, vì URL dễ xuất hiện trong history, log, analytics và header Referer. Đối với token có vòng đời gắn với phiên/đăng nhập, hãy cấp lại khi người dùng đăng nhập hoặc thay đổi trạng thái xác thực. Với double-submit stateless, vòng đời và cách chống tái sử dụng phải được thiết kế phù hợp; không mặc định mỗi lần login tự động làm token cũ vô hiệu nếu không có cơ chế ràng buộc.

### 6.3. API Bearer-only stateless: ví dụ cấu hình khác

Khi đã xác nhận một nhóm endpoint **chỉ** chấp nhận JWT Bearer trong header, có thể tách một chain và bỏ CSRF cho **riêng nhóm đó**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain bearerOnly(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/machine-api/**")
        .sessionManagement(session ->
            session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .csrf(AbstractHttpConfigurer::disable)
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Đây là mẫu **JWT Resource Server**. Để hoạt động thực tế, cần cấu hình issuer/JWKs hoặc JwtDecoder đáng tin cậy và kiểm tra issuer, audience, thời hạn, chữ ký và quyền. **Chỉ** bỏ CSRF nếu chain Bearer-only không có xác thực cookie, Basic, SSO, mTLS hoặc fallback do gateway cung cấp.

Nếu cùng ứng dụng còn trang đăng nhập cookie/session, chain của chúng phải giữ bảo vệ CSRF phù hợp. Với nhiều chain, kiểm tra **@Order** và **securityMatcher**, tránh một chain tổng quát không chủ ý bắt hết request trước chain chuyên biệt.

## 7. Spring Security WebFlux: cùng nguyên tắc, thành phần khác

Reactive dùng **SecurityWebFilterChain** và **ServerHttpSecurity**. Một API có thể không lưu **SecurityContext** trong WebSession nhưng vẫn xác thực bằng cookie JWT mà browser tự gửi.

Đoạn mã sau minh họa **phần CSRF và lưu SecurityContext**, chưa bao gồm filter xác thực JWT từ cookie:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Bean
SecurityWebFilterChain reactiveCookieApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .securityContextRepository(
            NoOpServerSecurityContextRepository.getInstance())
        .csrf(csrf -> csrf.csrfTokenRepository(
            CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .anyExchange().authenticated())
        .build();
}
~~~

Để hoàn thiện luồng trên, cần:

1. Đăng ký authentication **WebFilter** (hoặc cơ chế xác thực Reactive tương đương) đọc và xác minh JWT cookie; không tự cấp quyền từ cookie chưa xác minh.
2. Chọn **ServerCsrfTokenRequestHandler** và cách client gửi token phù hợp phiên bản Spring Security. Cơ chế masking token trong request attribute và token raw đọc từ cookie **có thể khác nhau**; đừng ghép chúng tùy tiện.
3. Cấp CSRF token cho SPA và bảo đảm token được subscribe/materialize trước khi client gửi request nguy hiểm.
4. Bảo vệ cookie xác thực, cookie CSRF, CORS, subdomain và các endpoint login/refresh/logout theo cùng mô hình đã đánh giá ở Servlet.
5. Kiểm tra toàn bộ pipeline có vô tình tạo **WebSession** từ thành phần khác không nếu hệ thống yêu cầu stateless nghiêm ngặt.

Ví dụ endpoint trả token qua JSON trong WebFlux:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

@RestController
class ReactiveCsrfEndpoint {

    @GetMapping("/api/csrf")
    Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());
        if (token == null) {
            return Mono.error(new IllegalStateException("CSRF not configured"));
        }
        return token.map(value -> Map.of(
            "headerName", value.getHeaderName(),
            "token", value.getToken()
        ));
    }
}
~~~

Khi SPA gọi endpoint từ origin khác, cần cấu hình **CORS Reactive** với origin cụ thể và credentials phù hợp. Đừng lấy **CorsConfigurationSource/UrlBasedCorsConfigurationSource** của Servlet cho đường WebFlux; dùng loại thuộc package **org.springframework.web.cors.reactive** cùng filter/integration tương ứng.

## 8. Stateless CSRF token: đâu là điểm cần quyết định?

Một API không lưu session có hai lựa chọn tiêu biểu để kiểm tra ý định request dùng cookie:

| Cách bảo vệ | Cách vận hành | Ưu/nhược điểm |
| --- | --- | --- |
| **Synchronizer token** gắn với server-side session | Server lưu token bí mật trong session và đối chiếu header/form | Chống giả mạo rõ ràng nhưng cần state trên server cho token/phiên |
| **Double-submit cookie** | Browser nhận CSRF cookie; client JS đọc token hoặc lấy qua JSON rồi gửi lại trong header; server đối chiếu | Có thể tránh state phía server, nhưng phải thiết kế chống cookie injection, cân nhắc chữ ký/ràng buộc xác thực |
| **Signed double-submit** | Token CSRF chứa nonce và thông tin ràng buộc, có HMAC được server xác minh | Có thể stateless, mạnh hơn trước cookie injection nếu secret, định dạng và ràng buộc được thiết kế đúng |
| **Origin/Referer và Fetch Metadata** | Chặn các nguồn request không đáng tin cậy dựa trên header browser gửi | Hữu ích như lớp bổ sung; phải xử lý header vắng mặt, proxy, subdomain và các client hợp lệ |
| **SameSite, chặn form/simple request và Content-Type nghiêm** | Thu hẹp khả năng browser gửi credential hoặc tạo request có tác động | Giảm bề mặt tấn công; không phải bằng chứng ý định đầy đủ cho mọi luồng |

**Quan trọng:** Đối với double-submit, chỉ so sánh giá trị cookie với header là chưa đủ để khẳng định đã chống mọi biến thể tấn công. Một subdomain có thể kiểm soát cookie scope rộng hoặc response injection có thể làm giả cookie trong một số kiến trúc. Ưu tiên cookie host-only, HTTPS, HSTS, tránh subdomain không đáng tin cậy và cân nhắc HMAC ràng buộc với phiên/danh tính xác thực cho hệ thống có yêu cầu cao.

Mỗi lựa chọn phải phù hợp **kiến trúc và rủi ro**. “Bật STATELESS” không tự sinh CSRF token an toàn; “bật CSRF” cũng không tự động bảo vệ khi client không gửi được token.

## 9. Kiểm thử Servlet: chứng minh CSRF vẫn tồn tại khi stateless

Giả định API **POST /api/preferences** thực hiện thay đổi dữ liệu và được cấu hình **STATELESS** nhưng vẫn có CSRF protection. Với **spring-security-test**, có thể kiểm tra filter độc lập với cơ chế xác thực JWT:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class StatelessCookieCsrfTests {

    @Autowired MockMvc mockMvc;

    @Test
    void postWithoutCsrfIsRejectedEvenIfUserIsAuthenticated() throws Exception {
        mockMvc.perform(post("/api/preferences")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"emailAlerts\":false}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfCanReachBusinessHandler() throws Exception {
        mockMvc.perform(post("/api/preferences")
                .with(user("alice"))
                .with(csrf().asHeader())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"emailAlerts\":false}"))
            .andExpect(status().is2xxSuccessful());
    }

    @Test
    void postWithInvalidCsrfIsRejected() throws Exception {
        mockMvc.perform(post("/api/preferences")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"emailAlerts\":false}"))
            .andExpect(status().isForbidden());
    }
}
~~~

Đoạn kiểm thử giả định controller và nghiệp vụ tương ứng tồn tại, với response **2xx** cho dữ liệu hợp lệ. **user("alice")** mô phỏng người dùng đã được xác thực để kiểm tra riêng filter CSRF; nó **không chứng minh bộ lọc JWT cookie đang hoạt động**. Với repository/header handler tùy chỉnh, test helper cần tương thích cách token được cấp và gửi.

Để xác minh toàn bộ kiến trúc, phải có **integration test với cookie JWT thật**, decoder/authentication filter và trình duyệt hoặc HTTP client kiểm soát cookie:

1. Gửi request không có cookie, không token: phải từ chối.
2. Gửi **AUTH_TOKEN** hợp lệ nhưng **thiếu CSRF header**: phải từ chối và dữ liệu không đổi.
3. Gửi cookie hợp lệ và **token CSRF sai**: phải từ chối và dữ liệu không đổi.
4. Lấy token CSRF từ cơ chế đã cấu hình rồi gửi cùng cookie xác thực: request vượt kiểm tra CSRF, sau đó vẫn phải chịu phân quyền và validation.
5. Dùng JWT hết hạn, sai chữ ký, issuer hoặc audience: phải từ chối **kể cả khi CSRF token hợp lệ**.
6. Gửi cookie từ trang độc hại hoặc subdomain không tin cậy trong môi trường test: kiểm tra SameSite, CORS, Origin/Fetch Metadata và kết quả không thay đổi dữ liệu.

### 9.1. Kiểm thử Reactive

Trong **spring-security-test** cho WebFlux có thể dùng **WebTestClient** và cấu hình hỗ trợ **mockUser()**, **csrf()**:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// webTestClient đã gắn Spring Security và /api/preferences có handler.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/preferences")
    .bodyValue(Map.of("emailAlerts", false))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/preferences")
    .bodyValue(Map.of("emailAlerts", false))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Đây là đoạn thân test, cần **java.util.Map**, WebTestClient và handler khi đưa vào test class. Tương tự Servlet, **mockUser()** kiểm tra luồng filter và quyền ở mức mô phỏng; kiểm thử cookie JWT và CSRF token thực tế cần môi trường integration.

### 9.2. Ma trận kết quả

| Tình huống | Kết quả kỳ vọng |
| --- | --- |
| Stateless JWT cookie, POST thiếu CSRF | **403** hoặc phản hồi từ chối tương ứng, không thay đổi dữ liệu |
| Stateless JWT cookie, POST token CSRF giả/cũ không hợp lệ | Từ chối, không thay đổi dữ liệu |
| Stateless JWT cookie, CSRF đúng nhưng JWT sai/hết hạn | Từ chối vì xác thực, không thay đổi dữ liệu |
| JWT cookie và CSRF hợp lệ, thiếu quyền ghi | **403** do phân quyền, không thay đổi dữ liệu |
| Stateless JWT cookie, token CSRF và quyền đều hợp lệ | Cho phép thao tác nếu input và nghiệp vụ hợp lệ |
| Bearer-only, có cookie session cũ nhưng không Authorization | **401**/từ chối, nếu thật sự không có cookie fallback |
| Bearer-only, có Authorization hợp lệ nhưng không CSRF | Có thể xử lý nếu chain đã miễn CSRF hợp lệ và quyền đủ |
| Form/simple POST từ website ngoài | Không thực thi thao tác; cookie có gửi hay không tùy browser, nhưng server vẫn phải có phòng vệ phù hợp |
| CORS preflight từ origin không được phép | Browser không gửi request thực tế của luồng cần preflight |

Những mã trạng thái trên là kết quả điển hình, **không phải bất biến**. Filter order, entry point, access denied handler và backend có thể thay đổi response. Bằng chứng quan trọng là không có hành động trái phép nào được thực thi.

## 10. Chẩn đoán xung đột trong triển khai

### “Đã đặt STATELESS nhưng POST không có CSRF vẫn bị 403”

Đây có thể là **hành vi chính xác** nếu API nhận JWT từ cookie và CsrfFilter còn bật. Kiểm tra **CookieCsrfTokenRepository**, token có được tạo hay chưa, tên header **X-XSRF-TOKEN**, request handler đang dùng và trạng thái cookie. Chỉ tắt CSRF khi đã xác minh route hoàn toàn không dựa vào credentials browser tự gửi.

### “Đã tắt CSRF nhưng API vẫn nhận JSESSIONID”

**STATELESS** chỉ giới hạn cách Spring Security sử dụng HttpSession cho security context, không cấm mọi code khác tạo cookie hoặc session. Xem filter xác thực, controller, session middleware, gateway và các chain khác. Kiểm thử request **chỉ có cookie, không Bearer** để biết cookie đó thực sự có thể xác thực hay không.

### “Cookie có HttpOnly nên không thể CSRF”

**HttpOnly** chỉ ngăn JavaScript đọc cookie, không ngăn browser gửi cookie. Đây là một trong những hiểu nhầm nguy hiểm nhất đối với JWT-cookie stateless. Token CSRF có thể cung cấp qua endpoint JSON hoặc cookie riêng, còn cookie xác thực vẫn nên HttpOnly.

### “SameSite=Lax mà trang khác vẫn kích hoạt request”

Xem request có xuất phát từ **origin khác nhưng cùng site** (đặc biệt subdomain kém tin cậy) hay không. Kiểm tra việc GET có tác dụng phụ, cách browser xử lý SameSite mặc định và cookie bị thiết lập lại gần đây. Không chỉ dựa vào SameSite để chứng minh bảo vệ đầy đủ.

### “SPA khác origin gọi /api/csrf thành công nhưng POST thiếu cookie”

Fetch mặc định dùng **credentials: "same-origin"**, nên một lời gọi từ **app.example.com** tới **api.example.com** có thể không gửi cookie. Cần dùng **credentials: "include"** nếu thực sự muốn xác thực bằng cookie; CORS phải cho phép origin cụ thể cùng credentials, đồng thời cookie phải được browser chấp nhận. Nếu dùng token CSRF từ JSON, browser không cần cho JS đọc cookie host-only của API.

### “CORS báo lỗi trước khi thấy 401/403”

Kiểm tra **OPTIONS preflight**, allowed origins, methods, headers, **Access-Control-Allow-Credentials** và thứ tự filter CORS/xác thực. Console CORS error có thể che response thật; xem tab Network. CORS failure khác với JWT validation, thiếu CSRF token và lỗi phân quyền.

### “Đã có CSP, HSTS và HTTP firewall nên không cần CSRF”

**CSP** giảm rủi ro thực thi script không tin cậy; **HSTS** hỗ trợ buộc HTTPS; **HTTP firewall** từ chối các request bất thường; **CORS** quản lý quyền truy cập khác origin. Không cơ chế nào tự xác nhận ý định của request đã được browser gắn cookie. Chúng cần được dùng cùng xác thực, phân quyền, chống XSS và CSRF khi mô hình đe dọa yêu cầu.

### “Refresh token nằm trong cookie, access token nằm trong header Bearer”

Cần chia nhóm route. API chỉ chấp nhận access token ở header có thể miễn CSRF có điều kiện, nhưng **/auth/refresh**, **/logout** và các endpoint đọc refresh cookie phải được đánh giá độc lập. Một request từ bên thứ ba có thể tác động đến việc xoay vòng token hoặc thay đổi trạng thái xác thực ngay cả khi không đọc được phản hồi.

## 11. Tình huống thực hành

**Tình huống 1 — Stateless JWT cookie:** API thanh toán đọc cookie **AUTH_TOKEN** đã ký, không dùng HttpSession; giao diện gửi request POST có cookie.  
**Kết luận:** JWT được kiểm tra hợp lệ không chứng minh người dùng chủ ý thanh toán. Cần CSRF protection và kiểm soát cookie, phương thức, Origin, quyền thanh toán.

**Tình huống 2 — Stateless JWT Bearer:** SPA giữ JWT trong memory, gửi Authorization header; backend chỉ nhận JWT Bearer, không có cookie fallback.  
**Kết luận:** Trang ngoài origin không tự có token; CSRF truyền thống thường không áp dụng. Cần chú trọng XSS, token exfiltration, audience/scope, CSP và CORS.

**Tình huống 3 — Backend stateless, gateway dùng cookie:** API chỉ tin header danh tính từ gateway, nhưng gateway xác thực browser bằng session cookie.  
**Kết luận:** Kiểm tra CSRF phải đặt tại gateway/BFF hoặc ranh giới đáng tin cậy trước khi cấp quyền thao tác. API stateless phía sau không xóa bề mặt CSRF phía trước.

**Tình huống 4 — Intranet SSO:** Một ứng dụng không lưu session nhưng browser dùng Negotiate/SSO để truy cập nội bộ.  
**Kết luận:** Phải kiểm tra chính sách browser và sự tự động xác thực. Nếu browser tự gửi credential cho request không chủ ý, cần CSRF protection hoặc cơ chế bảo vệ tương đương.

**Tình huống 5 — Double-submit qua nhiều subdomain:** SPA đọc XSRF cookie từ miền cha để gửi header, trong khi subdomain thử nghiệm do bên thứ ba kiểm soát.  
**Kết luận:** Cần cân nhắc cookie injection, phạm vi Domain, host-only cookie và signed double-submit hoặc thiết kế token khác. Chỉ nhìn thấy hai giá trị cookie/header trùng nhau chưa đủ chứng minh an toàn.

## 12. Tổng hợp nguyên tắc

1. **Stateless** chỉ mô tả việc server có giữ session hay không; nó **không nói** browser có tự gửi credential hay không.
2. **JWT đặt trong cookie** vẫn tạo bề mặt CSRF nếu backend dùng cookie xác thực thao tác thay đổi trạng thái.
3. **Bearer token do JavaScript chủ động gắn** có mô hình CSRF khác; chỉ bỏ CSRF cho route đã xác minh không có cookie/Basic/SSO/mTLS fallback.
4. **Gateway, BFF, refresh endpoint và login/logout** phải được đánh giá như một phần của đường xác thực, kể cả khi API nội bộ hoàn toàn stateless.
5. **CSRF token, Origin/Referer, Fetch Metadata, SameSite và Content-Type** bảo vệ các lớp khác nhau; phối hợp và kiểm thử đúng theo kiến trúc.
6. **STATELESS không tự vô hiệu hóa CSRF** trong Spring Security; hãy cấu hình rõ ràng cho Servlet/Reactive và phân tách security chain theo loại xác thực.
7. **Kiểm thử kết quả thực:** cookie có tự đi qua không, request không token có bị chặn không, Bearer-only có vô tình nhận cookie không và dữ liệu có thay đổi trái phép không.

Khi thiết kế phòng vệ HTTP cho SPA và API, câu hỏi quyết định là **“trình duyệt có thể tự cung cấp một credential mà máy chủ chấp nhận cho hành động này hay không?”**. Nếu có, tính stateless của backend không đủ để loại bỏ nhu cầu đánh giá và bảo vệ CSRF.
