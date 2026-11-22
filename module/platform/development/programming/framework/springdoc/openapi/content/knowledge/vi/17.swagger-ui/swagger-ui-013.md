# Giới hạn đặt cookie và các header do trình duyệt quản lý

Swagger UI chạy trong trình duyệt và gửi request bằng cơ chế mạng của trình duyệt. Vì vậy, dù OpenAPI mô tả được header hoặc cookie, JavaScript của Swagger UI vẫn không thể tự do đặt mọi giá trị vào HTTP request. Trình duyệt kiểm soát một số header, tự quản lý cookie theo chính sách bảo mật và áp dụng CORS trước khi cho phép JavaScript đọc response.

Đây là điểm quan trọng khi tài liệu API có xác thực bằng session cookie, cần gửi header tùy chỉnh hoặc dùng nút Try it out để gọi API ở origin khác. Nếu mô tả một header bị trình duyệt cấm ghi, giao diện có thể hiển thị trường nhập nhưng request thực tế vẫn không chứa giá trị đó.

## 1. Phân biệt OpenAPI, Swagger UI và trình duyệt

Ba lớp tham gia vào một request từ Swagger UI:

1. **OpenAPI** mô tả hợp đồng: path, method, parameter, security scheme, request body và response.
2. **Swagger UI** đọc hợp đồng, hiển thị form và tạo request từ thao tác của người dùng.
3. **Trình duyệt** thực hiện request, áp dụng cookie jar, Fetch/XHR, CORS và các giới hạn bảo mật.

OpenAPI có thể khai báo header hoặc cookie hợp lệ về mặt đặc tả. Điều đó không có nghĩa browser cho phép script đặt header đó. Khi Try it out hoạt động, request vẫn chịu cùng chính sách như một ứng dụng JavaScript thông thường.

Ví dụ, API có thể cần:

- Header Authorization chứa access token.
- Cookie SESSION do server cấp sau khi đăng nhập.
- Header X-Request-Id do client tạo để truy vết.
- Header Origin do trình duyệt tự gửi để server thực hiện CORS.

Các giá trị này có cách quản lý khác nhau. Authorization và X-Request-Id thường có thể được đặt bằng JavaScript nếu CORS cho phép. Cookie được browser gửi từ cookie jar theo domain, path, SameSite, Secure và credentials mode. Origin do browser xác định; script không thể tùy ý giả mạo nó.

## 2. Forbidden request headers là gì?

Fetch Standard định nghĩa một tập tên header mà mã JavaScript không được tự đặt trực tiếp. Các header này thường được gọi là **forbidden request-header names**. Trình duyệt giữ quyền kiểm soát vì chúng liên quan đến định tuyến, giao thức, thông tin nguồn hoặc cơ chế bảo mật.

Một số ví dụ thường gặp:

| Header | Lý do không thể tùy ý đặt từ JavaScript |
| --- | --- |
| Cookie | Browser tự tạo từ cookie jar theo chính sách cookie |
| Host | Browser xác định host của request URL |
| Content-Length | Browser tính theo nội dung request |
| Origin | Browser xác định origin gửi request |
| Connection | Thuộc quản lý kết nối HTTP |
| Keep-Alive | Thuộc quản lý kết nối |
| Accept-Encoding | Browser và network stack thương lượng encoding |
| Access-Control-Request-Method | Browser tự tạo trong CORS preflight |
| Access-Control-Request-Headers | Browser tự tạo trong CORS preflight |
| Sec-* | Dành cho thông tin và cơ chế bảo mật do user agent quản lý |
| Proxy-* | Thuộc nhóm header proxy bị hạn chế |

Danh sách đầy đủ do Fetch Standard quy định và có thể thay đổi theo chuẩn cũng như cách triển khai của browser. Một số header bị trình duyệt bỏ qua âm thầm, một số thao tác có thể phát sinh lỗi. Không nên dựa vào việc một browser cụ thể có vẻ chấp nhận header để thiết kế hợp đồng API.

**Referer** cũng do browser kiểm soát theo referrer policy. JavaScript có thể tác động đến chính sách thông qua các tùy chọn được hỗ trợ như referrerPolicy, nhưng không thể tùy ý đặt giá trị Referer như một header thông thường.

**Authorization** không thuộc nhóm forbidden request header. Script có thể đặt header này, nhưng khi gọi cross-origin, nó thường làm phát sinh CORS preflight vì đây không phải CORS-safelisted request header.

## 3. Cookie là dữ liệu do browser quản lý

Cookie không phải một header tùy chỉnh mà Swagger UI có thể tự do nhập và gửi. Server gửi **Set-Cookie** trong response; browser quyết định có lưu cookie hay không. Ở request tiếp theo, browser tự tạo header **Cookie** từ các cookie phù hợp với URL và chính sách bảo mật.

Ví dụ server trả:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Browser có thể lưu cookie SESSION. Khi request sau thỏa điều kiện domain, path, Secure, SameSite và credentials mode, browser tự gửi:

~~~http
Cookie: SESSION=abc123
~~~

JavaScript không được tự đặt header Cookie bằng Fetch API. Không nên khai báo Cookie như một header parameter để người dùng nhập trong Swagger UI rồi kỳ vọng browser sẽ gửi giá trị đó.

### Các thuộc tính cookie quan trọng

| Thuộc tính | Tác dụng | Lưu ý |
| --- | --- | --- |
| Domain | Xác định host hoặc phạm vi subdomain nhận cookie | Bỏ qua Domain sẽ tạo host-only cookie |
| Path | Giới hạn các đường dẫn request được gửi cookie | Không phải ranh giới bảo mật |
| Secure | Chỉ gửi cookie qua kênh an toàn, thông thường là HTTPS | Cần dùng cho cookie nhạy cảm |
| HttpOnly | Ngăn JavaScript đọc cookie qua document.cookie | Browser vẫn tự gửi cookie phù hợp |
| SameSite | Kiểm soát gửi cookie trong ngữ cảnh cross-site | None yêu cầu Secure trong browser hiện đại |
| Max-Age | Tuổi thọ tối đa tính bằng giây | Thường được ưu tiên hơn Expires |
| Expires | Thời điểm cookie hết hạn | Có thể bị giới hạn bởi chính sách browser |

**Domain:** Nếu không đặt Domain, cookie chỉ thuộc host đã tạo nó. Chỉ đặt Domain khi thực sự cần chia sẻ cookie giữa các subdomain. Không thể đặt cookie cho public suffix như .com.

**Path:** Path quyết định request path nào có thể mang cookie. Đây là cơ chế định tuyến cookie, không nên dùng thay cho kiểm soát truy cập.

**Secure:** Cookie chỉ được gửi trên kết nối an toàn theo quy tắc browser. Môi trường production nên dùng HTTPS.

**HttpOnly:** JavaScript không đọc được cookie này qua document.cookie. Thuộc tính giúp giảm nguy cơ script đánh cắp session cookie, nhưng không ngăn browser tự gửi cookie trong request.

**SameSite:** Strict hạn chế gửi cookie trong ngữ cảnh cross-site; Lax cho phép một số điều hướng cấp cao nhất an toàn; None cho phép gửi trong ngữ cảnh cross-site khi đáp ứng điều kiện Secure và các chính sách browser khác.

**Max-Age/Expires:** Dùng để xác định thời gian tồn tại. Session cookie có thể được browser xóa khi phiên kết thúc, nhưng khái niệm phiên browser có thể khác nhau giữa các trình duyệt.

Browser còn có chính sách riêng về số lượng cookie, kích thước mỗi cookie, tổng dung lượng theo site và cookie bên thứ ba. Không nên coi một giới hạn số byte hoặc số lượng cụ thể là giống nhau ở mọi browser. Giữ cookie nhỏ, chỉ lưu định danh phiên hoặc dữ liệu tối thiểu; không nhét toàn bộ profile hay token lớn vào cookie.

Với cookie nhạy cảm, có thể cân nhắc các prefix do browser hỗ trợ:

- **__Secure-** yêu cầu cookie được đặt từ secure origin và có thuộc tính Secure.
- **__Host-** yêu cầu Secure, Path=/ và không có thuộc tính Domain; cookie vì vậy bị giới hạn ở host đã tạo nó.

Ví dụ tên cookie **__Host-SESSION** giúp tránh việc subdomain khác đặt cookie cùng tên trong phạm vi Domain rộng. Cần kiểm tra yêu cầu prefix của browser mục tiêu trước khi áp dụng.

## 4. Cấu hình cookie trong Spring Boot

Spring Framework cung cấp ResponseCookie để tạo giá trị Set-Cookie có thuộc tính rõ ràng:

~~~java
import java.time.Duration;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SessionController {

    private final SessionService sessionService;

    SessionController(SessionService sessionService) {
        this.sessionService = sessionService;
    }

    @PostMapping("/api/session")
    ResponseEntity<SessionView> createSession() {
        String sessionId = sessionService.createSession();

        ResponseCookie cookie = ResponseCookie
            .from("SESSION", sessionId)
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .path("/")
            .maxAge(Duration.ofHours(8))
            .build();

        return ResponseEntity.ok()
            .header(HttpHeaders.SET_COOKIE, cookie.toString())
            .body(new SessionView("authenticated"));
    }
}
~~~

Ví dụ giả định SessionService tạo và lưu session phía server. Trong ứng dụng thực tế, session ID cần đủ ngẫu nhiên, khó đoán, có thời hạn và được thu hồi khi logout hoặc hết hạn. Không dùng giá trị cố định như abc123 trong production.

Kiểu response minh họa:

~~~java
public record SessionView(String status) {}
~~~

Nếu cần chia sẻ cookie giữa các subdomain, có thể cấu hình Domain sau khi đánh giá ranh giới tin cậy:

~~~java
ResponseCookie cookie = ResponseCookie
    .from("SESSION", sessionId)
    .domain("example.com")
    .path("/")
    .secure(true)
    .httpOnly(true)
    .sameSite("Lax")
    .build();
~~~

Cookie Domain rộng hơn khiến nhiều subdomain cùng nhận cookie. Nếu một subdomain ít tin cậy bị chiếm quyền, phạm vi chia sẻ rộng có thể làm tăng ảnh hưởng. Ưu tiên host-only cookie khi không cần chia sẻ.

Khi logout, gửi cookie cùng tên với thời hạn bằng 0 và dùng đúng Domain/Path đã cấp:

~~~java
ResponseCookie expired = ResponseCookie
    .from("SESSION", "")
    .path("/")
    .secure(true)
    .httpOnly(true)
    .sameSite("Lax")
    .maxAge(Duration.ZERO)
    .build();
~~~

Nếu cookie ban đầu được tạo với Domain cụ thể, response xóa cookie cũng phải dùng đúng phạm vi Domain/Path tương ứng. Nếu không, browser có thể giữ lại cookie cũ.

## 5. Same-origin, same-site và CORS là ba khái niệm khác nhau

**Origin** gồm scheme, host và port. Ví dụ https://docs.example.com và https://api.example.com là hai origin khác nhau dù cùng domain gốc.

**Site** là khái niệm được browser dùng cho một số chính sách như SameSite cookie. Hai subdomain cùng scheme và registrable domain thường được xem là same-site, dù vẫn khác origin.

**CORS** là cơ chế cho phép hoặc từ chối JavaScript đọc response cross-origin. CORS không phải cơ chế xác thực người dùng và cũng không thay thế cookie policy.

| Tình huống | Origin | Site | CORS |
| --- | --- | --- | --- |
| Swagger UI và API cùng scheme/host/port | Same-origin | Same-site | Không cần CORS |
| UI ở docs.example.com, API ở api.example.com, cùng HTTPS | Cross-origin | Thường same-site | Cần cấu hình CORS |
| UI ở docs.example.net, API ở api.example.com | Cross-origin | Cross-site | Cần CORS; cookie còn chịu SameSite và chính sách third-party |

Nếu Swagger UI và API khác origin, browser chỉ gửi cookie cross-origin khi credentials mode, cookie attributes và CORS response đều cho phép. Việc cấu hình CORS đúng không thể ép browser bỏ qua SameSite hoặc chính sách chặn third-party cookie.

## 6. Gửi cookie trong request cross-origin

Fetch API có credentials mode:

| Giá trị | Hành vi |
| --- | --- |
| omit | Không gửi credentials |
| same-origin | Gửi credentials cho same-origin; đây là mặc định của Fetch |
| include | Cho phép gửi credentials cả cross-origin, nếu các chính sách khác cho phép |

Swagger UI có tùy chọn **withCredentials** để bật gửi credentials trong request cross-origin. Khi cấu hình tùy chọn này, browser vẫn kiểm tra cookie Domain, Path, Secure, SameSite, quyền third-party cookie và CORS.

Ví dụ cấu hình Swagger UI độc lập:

~~~javascript
SwaggerUIBundle({
    url: "/v3/api-docs",
    dom_id: "#swagger-ui",
    withCredentials: true
});
~~~

Khi springdoc quản lý Swagger UI, cách truyền cấu hình phụ thuộc phiên bản springdoc và cách ứng dụng tùy biến Swagger UI. Hãy kiểm tra cấu hình Swagger UI mà phiên bản đang dùng hỗ trợ; không giả định mọi thuộc tính JavaScript đều có cùng tên trong application.yml.

## 7. Cấu hình CORS cho cookie và header tùy chỉnh

Với request cross-origin có credentials, server cần trả:

- Access-Control-Allow-Origin bằng origin cụ thể của Swagger UI; không dùng dấu sao *.
- Access-Control-Allow-Credentials: true.
- Access-Control-Allow-Methods chứa method cần gọi.
- Access-Control-Allow-Headers cho các header tùy chỉnh mà client được phép gửi.
- Vary: Origin khi response thay đổi theo origin được cho phép.

Ví dụ cấu hình Spring MVC:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class CorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id",
                "X-CSRF-TOKEN"
            )
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Không thêm Cookie vào allowedHeaders với mục đích cho phép JavaScript tự đặt header Cookie. Browser tự gửi cookie từ cookie jar; Cookie là forbidden request header và không được xử lý như một custom header thông thường.

Nếu ứng dụng dùng Spring Security, cấu hình CORS cần được tích hợp đúng với security filter chain. CORS preflight OPTIONS phải được xử lý trước khi cơ chế xác thực từ chối request do không có session cookie.

Khi request có Authorization hoặc X-Request-Id, browser có thể gửi OPTIONS preflight để hỏi server có cho phép origin, method và header đó hay không. Nếu server không trả lời đúng các header CORS, request chính sẽ không được gửi hoặc response không được JavaScript đọc.

## 8. Mô tả cookie authentication trong OpenAPI

OpenAPI hỗ trợ API key security scheme đặt trong cookie. Cách này mô tả rằng API sử dụng cookie có tên cụ thể để xác thực:

~~~yaml
components:
  securitySchemes:
    sessionCookie:
      type: apiKey
      in: cookie
      name: SESSION

security:
  - sessionCookie: []
~~~

Nếu chỉ một số operation yêu cầu session cookie, đặt security requirement ở operation tương ứng thay vì cấp tài liệu:

~~~yaml
paths:
  /api/profile:
    get:
      security:
        - sessionCookie: []
      responses:
        '200':
          description: Thông tin người dùng hiện tại
~~~

Có thể khai báo bằng annotation Swagger:

~~~java
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeIn;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "sessionCookie",
    type = SecuritySchemeType.APIKEY,
    in = SecuritySchemeIn.COOKIE,
    paramName = "SESSION",
    description = "Session cookie do server cấp sau khi đăng nhập"
)
class OpenApiCookieSecurityConfiguration {}
~~~

Gắn requirement lên controller hoặc operation:

~~~java
@SecurityRequirement(name = "sessionCookie")
@GetMapping("/api/profile")
ProfileView getProfile() {
    return profileService.getCurrentProfile();
}
~~~

Security scheme mô tả hợp đồng xác thực. Nó không tạo cookie và không yêu cầu browser gửi cookie nếu cookie chưa tồn tại hoặc không phù hợp với request URL.

Swagger UI có thể hiển thị ô nhập cho API key scheme, nhưng browser không cho script tự đặt header Cookie. Vì vậy, không nên dựa vào việc nhập SESSION vào ô Authorize để browser gửi cookie thủ công. Với session cookie, luồng phù hợp thường là đăng nhập qua cùng origin hoặc một cơ chế đăng nhập được browser xử lý để server trả Set-Cookie; sau đó browser tự gửi cookie khi gọi Try it out.

## 9. Vì sao không nên khai báo Cookie như header parameter?

Khai báo sau dễ gây hiểu nhầm:

~~~yaml
parameters:
  - name: Cookie
    in: header
    required: true
    schema:
      type: string
~~~

Nó mô tả một header mà JavaScript không được tự đặt. Swagger UI có thể dựng trường nhập từ OpenAPI, nhưng Fetch API sẽ không cho phép script tự tạo Cookie header theo cách này.

Nếu API xác thực bằng cookie, dùng security scheme **type: apiKey**, **in: cookie**, **name: SESSION**. Nếu API cần một cookie nghiệp vụ không dùng để xác thực, OpenAPI có thể mô tả Parameter Object với **in: cookie**, nhưng vẫn phải nhớ rằng browser tự quản lý header Cookie. Không kỳ vọng Try it out sẽ gửi một giá trị cookie tùy ý do JavaScript đặt.

Không khai báo Host, Origin, Content-Length, Connection hoặc các header Sec-* như trường nhập do client điều khiển. Chúng thuộc quyền quản lý của browser/network stack.

## 10. Mô tả Set-Cookie trong response

OpenAPI có thể mô tả response header Set-Cookie để người đọc hiểu server cấp cookie nào:

~~~yaml
responses:
  '200':
    description: Đăng nhập thành công
    headers:
      Set-Cookie:
        description: Browser lưu session cookie theo các thuộc tính được cấp
        schema:
          type: string
~~~

Đây là metadata cho người đọc hợp đồng. Trong thực tế, server có thể gửi nhiều header Set-Cookie riêng biệt. Không gộp nhiều Set-Cookie thành một chuỗi phân tách bằng dấu phẩy vì thuộc tính Expires có thể chứa dấu phẩy và mỗi cookie cần được xử lý riêng.

Set-Cookie là forbidden response-header name đối với JavaScript. Frontend không thể đọc giá trị này qua response.headers.get("Set-Cookie"), kể cả khi server thêm Set-Cookie vào Access-Control-Expose-Headers. Browser vẫn có thể xử lý Set-Cookie và lưu cookie nếu request/response đáp ứng điều kiện credentials, CORS và cookie policy.

Điều này giải thích vì sao Swagger UI có thể đăng nhập thành công và browser lưu session cookie, nhưng mã JavaScript của giao diện không đọc được nội dung Set-Cookie.

## 11. Cookie tự động gửi kéo theo yêu cầu chống CSRF

Browser tự gửi cookie phù hợp với request URL. Đây là tiện ích cho session authentication, nhưng cũng tạo nguy cơ CSRF: một trang web khác có thể khiến browser của người dùng gửi request đến API đang đăng nhập.

Các biện pháp thường dùng:

- Dùng SameSite phù hợp, thường là Lax hoặc Strict nếu kiến trúc cho phép.
- Với request thay đổi trạng thái, kiểm tra CSRF token hoặc cơ chế chống CSRF tương đương.
- Kiểm tra Origin hoặc Referer theo chính sách server khi phù hợp.
- Giới hạn CORS vào origin tin cậy; không bật credentials cho mọi origin.
- Không coi CORS là biện pháp chống CSRF duy nhất.
- Dùng Secure và HttpOnly cho session cookie nhạy cảm.

Nếu API dùng cookie session, Swagger UI cần gửi thêm CSRF token theo cơ chế ứng dụng. Header như X-CSRF-TOKEN có thể do Swagger UI gửi nếu nó có token và server cho phép header đó trong CORS. Cookie CSRF và header CSRF có thể phối hợp theo mô hình double-submit hoặc synchronizer token tùy framework.

## 12. Khi cần header mà browser không cho phép đặt

Trước khi tìm cách thay đổi request, hãy xác định header đó có thực sự cần do client cung cấp hay không.

| Nhu cầu | Cách xử lý phù hợp |
| --- | --- |
| Gửi session cookie | Để server cấp Set-Cookie; browser tự gửi cookie phù hợp |
| Gửi Authorization bearer token | Dùng HTTP bearer security scheme và CORS allow Authorization khi cross-origin |
| Gửi correlation ID | Dùng header tùy chỉnh như X-Request-Id; cho phép trong CORS |
| Đặt Origin hoặc Host | Để browser tạo từ URL và ngữ cảnh request |
| Đặt Content-Length | Để browser tính từ request body |
| Gọi API cần header nội bộ đặc biệt | Xem xét backend-for-frontend hoặc server-side integration có kiểm soát |

Nếu thật sự cần một hệ thống trung gian gửi header mà browser không được phép đặt, có thể xây dựng backend-for-frontend (BFF) hoặc proxy phía server. Browser gọi endpoint của BFF; BFF xác thực người dùng, kiểm tra quyền, rồi gọi API đích bằng HTTP client phía server.

Proxy phải giới hạn đích đến, tránh SSRF, không chuyển tiếp cookie hoặc credential tùy tiện, kiểm tra header được phép và ghi log an toàn. Không tạo proxy nhận URL bất kỳ từ người dùng rồi gửi request đến URL đó.

Không dùng proxy chỉ để lách một giới hạn bảo mật của browser. Nếu API cần một header do client thực sự kiểm soát, hãy thiết kế lại hợp đồng bằng header hợp lệ hoặc chuyển trách nhiệm tạo header sang server.

## 13. Kiểm tra bằng Swagger UI và Developer Tools

Khi Try it out không gửi cookie hoặc header như mong đợi, kiểm tra request thực tế trong Developer Tools:

1. Mở tab Network trước khi bấm Execute.
2. Chọn request OPTIONS nếu có preflight, sau đó chọn request API chính.
3. Kiểm tra Request URL, method, Origin và các header được gửi.
4. Kiểm tra browser có gửi Cookie hay không; nếu không, xem Domain, Path, Secure, SameSite và credentials mode.
5. Kiểm tra response có Set-Cookie và browser có lưu cookie trong Application/Storage hay không.
6. Kiểm tra lỗi CORS trong Console và response header của preflight.
7. Kiểm tra cookie có bị chặn bởi chính sách third-party cookie hoặc thiết lập riêng tư của browser không.

Không thể kết luận browser sẽ gửi Cookie chỉ từ nội dung OpenAPI hoặc từ việc Swagger UI hiển thị một ô nhập. Network panel cho thấy request browser thực sự đã gửi.

### Phân biệt thử bằng curl và thử bằng browser

curl cho phép người dùng đặt nhiều header mà JavaScript trong browser không được đặt:

~~~bash
curl -i \
  -H "Cookie: SESSION=abc123" \
  -H "X-Request-Id: req-1001" \
  https://api.example.com/api/profile
~~~

Lệnh này có thể thành công trong khi Swagger UI không gửi được Cookie header nhập tay. Đó không phải mâu thuẫn: curl là HTTP client độc lập, không chịu Fetch forbidden-header restrictions hoặc chính sách cookie của browser.

Để kiểm thử cookie trong browser, hãy thực hiện luồng đăng nhập để server trả Set-Cookie, xác minh browser lưu cookie, sau đó gọi API bằng Swagger UI với credentials mode phù hợp.

## 14. Lỗi thường gặp

**Swagger UI hiển thị Cookie header nhưng request không có Cookie.** JavaScript không được tự đặt forbidden Cookie header. Dùng cookie jar của browser và luồng Set-Cookie từ server.

**Cookie được cấp nhưng không gửi trong Try it out.** Kiểm tra domain, path, Secure, SameSite, thời hạn, credentials mode và chính sách third-party cookie.

**Cookie cross-origin không được lưu.** Kiểm tra request dùng credentials, server trả Access-Control-Allow-Credentials: true và Access-Control-Allow-Origin là origin cụ thể. Kiểm tra SameSite=None; Secure nếu thực sự cần cross-site cookie.

**Server trả Access-Control-Allow-Origin là dấu sao.** CORS không cho phép wildcard origin khi request dùng credentials. Trả đúng origin đã được cho phép.

**Frontend không đọc được Set-Cookie.** Đây là header bị cấm đọc từ JavaScript. Browser có thể lưu cookie dù mã ứng dụng không đọc được header này.

**Thêm Cookie vào Access-Control-Allow-Headers nhưng vẫn không gửi được.** Header Cookie không phải custom request header mà JavaScript được phép đặt. Browser tự quản lý cookie.

**Nhập SESSION trong Authorize nhưng API vẫn 401.** Swagger UI không thể ép browser đặt Cookie header tùy ý. Xác nhận cookie đã được cấp cho đúng host/path và được browser gửi tự động.

**curl chạy được nhưng Swagger UI thất bại.** curl không áp dụng CORS và forbidden-header restrictions của browser. Kiểm tra bằng Network panel và cấu hình browser.

**Cookie SameSite=None nhưng vẫn bị chặn.** Kiểm tra Secure, HTTPS và chính sách chặn third-party cookie của browser. SameSite=None không đảm bảo browser cho phép mọi third-party cookie.

**Logout nhưng cookie vẫn còn.** Kiểm tra response xóa cookie có cùng tên, Domain và Path với cookie ban đầu, đồng thời đặt Max-Age bằng 0 hoặc Expires trong quá khứ.

## 15. Checklist thiết kế API và Swagger UI với cookie/header

- [ ] Phân biệt header do client đặt với header do browser/network stack quản lý.
- [ ] Không yêu cầu Swagger UI tự đặt Cookie, Host, Origin hoặc Content-Length.
- [ ] Dùng security scheme apiKey với in=cookie để mô tả cookie authentication.
- [ ] Để server cấp session cookie bằng Set-Cookie.
- [ ] Chọn Domain, Path, Secure, HttpOnly, SameSite và thời hạn theo nhu cầu.
- [ ] Giữ cookie nhỏ và tránh lưu dữ liệu nhạy cảm không cần thiết.
- [ ] Nếu gọi cross-origin, cấu hình credentials mode và CORS với origin cụ thể.
- [ ] Không dùng Access-Control-Allow-Origin: * cùng credentials.
- [ ] Cho phép header tùy chỉnh thực sự cần thiết trong CORS preflight.
- [ ] Xây dựng CSRF protection cho API xác thực bằng cookie.
- [ ] Kiểm tra request/response trong browser Developer Tools.
- [ ] Không dùng kết quả curl để kết luận browser sẽ gửi cùng header.
- [ ] Chỉ dùng BFF/proxy khi có nhu cầu kiến trúc rõ ràng và kiểm soát đích đến.

## 16. Kết luận

Swagger UI tạo request trong browser nên chịu giới hạn của Fetch, cookie policy và CORS. OpenAPI mô tả được cookie và header, nhưng không thể cấp quyền cho JavaScript đặt các header do browser quản lý. Với session cookie, server cần cấp Set-Cookie cùng thuộc tính phù hợp để browser lưu và tự gửi. Với request cross-origin, cần phối hợp credentials mode, CORS, SameSite và chính sách riêng tư của browser. Khi kiểm thử, hãy quan sát Network panel để biết chính xác header nào đã được gửi thay vì chỉ dựa vào form Try it out.

## 17. Nguồn tham khảo

- [Fetch Standard — Forbidden request-header names](https://fetch.spec.whatwg.org/#forbidden-request-header): danh sách và quy tắc header mà script không được tự đặt.
- [MDN — Forbidden request header](https://developer.mozilla.org/en-US/docs/Glossary/Forbidden_request_header): giải thích các header do browser kiểm soát.
- [MDN — HTTP cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies): Set-Cookie, cookie attributes và cookie security.
- [MDN — CORS](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, credentials và response headers.
- [Swagger UI — Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/): cấu hình Swagger UI, bao gồm withCredentials.
- [OpenAPI Specification — Security Scheme Object](https://spec.openapis.org/oas/v3.1.1.html#security-scheme-object): mô tả API key security scheme trong cookie.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cấu hình CORS trong Spring MVC.
