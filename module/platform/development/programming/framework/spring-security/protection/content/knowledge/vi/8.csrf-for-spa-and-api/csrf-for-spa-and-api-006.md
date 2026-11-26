# Quyền JavaScript đọc cookie CSRF và phân biệt với cookie phiên

## Mục tiêu và phạm vi

Trong chương **CSRF cho SPA và API** thuộc module **SPRING_SECURITY_HTTP_PROTECTION**, hai cookie thường xuất hiện cùng lúc nhưng có vai trò trái ngược về quyền truy cập JavaScript:

- **Cookie đăng nhập hoặc cookie phiên** (ví dụ **JSESSIONID**): trình duyệt tự gửi để máy chủ nhận diện người dùng; nên được bảo vệ bằng **HttpOnly** để JavaScript không đọc trực tiếp giá trị.
- **Cookie chứa CSRF token** (ví dụ **XSRF-TOKEN**): trong một thiết kế dành cho SPA, JavaScript **cần đọc giá trị token** và chủ động gửi lại qua **X-XSRF-TOKEN**. Vì thế cookie CSRF có thể được cấu hình **HttpOnly=false**, đồng thời vẫn dùng Secure, SameSite và phạm vi cookie hợp lý.

Hai quyết định này phục vụ hai mục đích khác nhau. **Cho phép JavaScript đọc CSRF cookie không có nghĩa cho phép JavaScript đọc cookie phiên**. Bài học làm rõ chính sách cookie trên trình duyệt, luồng phòng CSRF, lựa chọn khi SPA và API khác origin, cấu hình Spring Security **Servlet** và **WebFlux (Reactive)**, cùng cách kiểm thử và chẩn đoán lỗi.

Sau bài học, người học có thể:

1. Phân biệt một cookie **được JavaScript đọc** với cookie **tự được trình duyệt gửi** trong HTTP request.
2. Giải thích tác dụng của **HttpOnly, Secure, SameSite, Domain, Path** và ranh giới origin/site khi đọc và gửi cookie.
3. Cấu hình **CookieCsrfTokenRepository.withHttpOnlyFalse()** mà vẫn giữ cookie xác thực **HttpOnly**.
4. Triển khai luồng **XSRF-TOKEN → X-XSRF-TOKEN** cho SPA cùng origin; lựa chọn endpoint JSON khi khác subdomain.
5. Nhận diện rủi ro XSS, cookie injection, token raw/XOR và việc token không được tạo vì deferred loading.
6. Kiểm thử cả Servlet và Reactive, xác nhận request thiếu/sai CSRF header bị chặn dù browser tự gửi cookie.

## 1. Hai câu hỏi độc lập: JavaScript đọc được không, browser có gửi không?

Cookie do server phát qua **Set-Cookie**, trình duyệt lưu theo chính sách và tự cân nhắc gửi trong header **Cookie** của những request khớp phạm vi. JavaScript có thể đọc một phần cookie bằng **document.cookie**, nhưng quyền này không giống quyền gửi cookie của browser.

Ví dụ server phát hai cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=s%3Aopaque-session; Path=/; HttpOnly; Secure; SameSite=Lax
Set-Cookie: XSRF-TOKEN=csrf-random-value; Path=/; Secure; SameSite=Lax
Cache-Control: no-store
~~~

Trên một trang HTTPS cùng hostname, JavaScript có thể thấy:

~~~javascript
console.log(document.cookie);
// Ví dụ: "XSRF-TOKEN=csrf-random-value"
// JSESSIONID không xuất hiện vì có HttpOnly.
~~~

Tuy nhiên, khi frontend gửi request đến cùng hostname và cookie phù hợp quy tắc gửi, **browser vẫn có thể gửi cả hai cookie**:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=s%3Aopaque-session; XSRF-TOKEN=csrf-random-value
Content-Type: application/json

{"displayName":"Alice"}
~~~

Đây là điểm quyết định: việc **HttpOnly** ngăn JavaScript đọc **JSESSIONID** không ngăn browser tự gửi cookie đó. Do đó, HttpOnly **không trực tiếp chống CSRF**. Để chứng minh request ghi dữ liệu xuất phát từ luồng giao diện đáng tin cậy, SPA cần chủ động đưa token CSRF vào một nơi mà một HTML form tấn công thông thường không tự thêm được, như header **X-XSRF-TOKEN**.

### 1.1. So sánh chính xác cookie phiên và cookie CSRF

| Tiêu chí | Cookie phiên/xác thực | Cookie CSRF cho SPA đọc bằng JavaScript |
| --- | --- | --- |
| Ví dụ tên | **JSESSIONID**, **SESSION**, **AUTH_TOKEN** | **XSRF-TOKEN** |
| Ý nghĩa | Xác định session hoặc mang credential xác thực | Chứa token dùng để kiểm tra tính chủ ý của request |
| JavaScript có cần đọc không? | **Không** trong thiết kế session-cookie chuẩn | **Có**, nếu SPA đọc cookie để đưa vào header |
| HttpOnly phù hợp | **true** | **false** trong mô hình đọc cookie; có thể true ở mô hình cấp token bằng JSON |
| Browser có tự gửi không? | Có, khi cookie khớp chính sách | Có; riêng việc gửi cookie CSRF **không đủ** vượt kiểm tra |
| Frontend có gắn vào Authorization không? | Không; browser quản lý Cookie header | Không; frontend thường gắn vào **X-XSRF-TOKEN** |
| Server dùng để kiểm tra | Xác thực và quản lý phiên/người dùng | So khớp CSRF token theo repository/request handler |
| Nếu bị lộ | Có thể dẫn đến chiếm phiên tùy kiến trúc | Có thể làm yếu phòng CSRF; không mặc nhiên cấp quyền đăng nhập |
| Có cần Secure/SameSite/giới hạn scope? | Có | Có |

**JWT trong cookie cũng là cookie xác thực.** Việc backend không lưu server-side session không làm JWT cookie trở thành cookie CSRF. Nếu browser tự gắn JWT cookie và backend chấp nhận nó làm credential, API stateless vẫn có thể bị CSRF.

### 1.2. CSRF token không phải “mật khẩu phụ”

CSRF token là một tín hiệu giúp chống request giả mạo, thường dựa vào bí mật ngẫu nhiên mà attacker ngoài origin không lấy được. Nó **không thay thế** session cookie, Bearer access token, login, role hoặc quyền thao tác.

Nếu request có token CSRF đúng nhưng người dùng chưa đăng nhập hoặc không đủ quyền, API vẫn phải từ chối. Ngược lại, nếu cookie xác thực hợp lệ nhưng request nguy hiểm thiếu token CSRF, server vẫn nên từ chối.

## 2. Vì sao header X-XSRF-TOKEN mới có ý nghĩa?

Một biểu mẫu trên website không tin cậy có thể kích hoạt một POST mà không cần đọc response của API. Trong ngữ cảnh browser cho phép gửi cookie, biểu mẫu đó có thể mang cookie phiên của nạn nhân:

~~~html
<!-- Minh họa trong môi trường kiểm thử được phép -->
<form method="post" action="https://app.example.com/api/preferences">
  <input type="hidden" name="publicProfile" value="true">
  <button type="submit">Submit</button>
</form>
~~~

Một HTML form thông thường không có quyền tự thêm header tùy biến **X-XSRF-TOKEN**, và JavaScript từ origin khác thường không đọc được cookie CSRF thuộc hostname của ứng dụng theo chính sách cookie/origin. Vì vậy frontend hợp lệ thực hiện thêm một bước:

~~~mermaid
sequenceDiagram
    autonumber
    participant UI as SPA cùng origin
    participant B as Browser cookie jar
    participant SEC as Spring Security
    UI->>B: document.cookie tìm XSRF-TOKEN
    B-->>UI: Trả token nếu không có HttpOnly và phạm vi khớp
    UI->>SEC: POST + Cookie tự gửi + X-XSRF-TOKEN do JS gắn
    SEC->>SEC: So khớp token header với repository
    alt CSRF hợp lệ
        SEC-->>UI: Tiếp tục xác thực, phân quyền và xử lý
    else Thiếu hoặc sai token
        SEC-->>UI: Thường 403 Forbidden
    end
~~~

Request hợp lệ có thể trông như sau:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=s%3Aopaque-session; XSRF-TOKEN=csrf-random-value
X-XSRF-TOKEN: csrf-random-value
Content-Type: application/json

{"publicProfile":true}
~~~

**Không lấy giá trị có sẵn trong header Cookie làm đủ chứng cứ CSRF.** Browser tự gửi cookie CSRF không chứng minh script của ứng dụng chủ động lấy và gửi token. Repository và CSRF filter phải xác minh giá trị nhận qua header/parameter theo cơ chế đã thiết kế.

Một request chứa header tùy biến từ JavaScript khác origin thường cần **CORS preflight**. Việc preflight không được phép có thể ngăn browser gửi request thực tế theo đường đó, nhưng **CORS không thay thế CSRF protection** cho các đường request đơn giản như HTML form và các trường hợp cấu hình không như kỳ vọng.

## 3. Hiểu thuộc tính cookie theo hai chiều: đọc và gửi

### 3.1. HttpOnly: ranh giới đọc của JavaScript

**HttpOnly=true** khiến cookie không xuất hiện trong **document.cookie** và không được cung cấp cho các API đọc cookie ở JavaScript. Browser vẫn có thể gửi cookie đó qua network khi request phù hợp.

~~~http
Set-Cookie: JSESSIONID=secret; Path=/; Secure; HttpOnly; SameSite=Lax
Set-Cookie: XSRF-TOKEN=token123; Path=/; Secure; SameSite=Lax
~~~

~~~javascript
// Trên trang cùng hostname, HTTPS và đường dẫn /:
console.log(document.cookie.includes("JSESSIONID=")); // false
console.log(document.cookie.includes("XSRF-TOKEN=")); // true nếu cookie tồn tại
~~~

**Không sửa thuộc tính HttpOnly của cookie xác thực** để xử lý lỗi “SPA không thấy token”. Hãy dùng cookie CSRF riêng hoặc endpoint cấp token qua JSON.

Một script XSS chạy trong origin vẫn có thể **khởi tạo fetch với cookie HttpOnly được browser tự gửi**, dù không đọc được cookie. Vì vậy HttpOnly giúp giảm khả năng **đọc trực tiếp/đánh cắp giá trị**, nhưng không thay thế chống XSS và không tự chống CSRF.

### 3.2. Secure: quyết định ngữ cảnh truyền cookie

**Secure** làm browser chỉ gửi cookie qua kênh an toàn, với những ngoại lệ/khác biệt trình duyệt liên quan localhost. Với production dùng HTTPS, cả cookie xác thực lẫn cookie CSRF nên được cấu hình **Secure=true**. Trong môi trường phát triển dùng HTTP thuần, cookie Secure có thể không được gửi và làm quá trình bootstrap thất bại; nên dùng HTTPS local khi có thể.

**HSTS** giúp browser sử dụng HTTPS cho những hostname đã được thiết lập chính sách hợp lệ. HSTS hỗ trợ bảo vệ kênh truyền nhưng không thay thế HttpOnly, CSRF token hoặc kiểm soát origin.

### 3.3. Domain: host-only so với cookie dùng chung subdomain

Nếu server **api.example.com** cấp:

~~~http
Set-Cookie: XSRF-TOKEN=abc; Path=/; Secure; SameSite=Lax
~~~

và **không** đặt thuộc tính **Domain**, cookie thường là **host-only**, thuộc **api.example.com**. JavaScript tại **app.example.com** không đọc được cookie host-only này bằng **document.cookie**.

Nếu đặt:

~~~http
Set-Cookie: XSRF-TOKEN=abc; Domain=example.com; Path=/; Secure; SameSite=Lax
~~~

cookie có phạm vi rộng hơn, có thể được nhìn thấy bởi JavaScript tại các subdomain phù hợp khi không có HttpOnly và Path phù hợp. Điều đó giúp SPA ở subdomain khác đọc token, nhưng cũng tăng bề mặt lộ/chèn cookie qua **subdomain không đáng tin cậy**.

**Không mở rộng Domain chỉ để sửa lỗi frontend không đọc được XSRF cookie.** Một endpoint **GET /api/csrf** trả JSON qua CORS allowlist đáng tin cậy thường rõ ràng hơn (xem phần 7).

### 3.4. Path: ảnh hưởng đến document.cookie và request

Cookie có **Path=/api** có thể được browser gửi đến **/api/orders**, nhưng trang SPA đang chạy tại đường dẫn **/** có thể không thấy nó trong **document.cookie** theo quy tắc khớp Path. Vì vậy, nếu frontend đọc XSRF cookie tại các route SPA khác nhau, phạm vi Path phải phù hợp.

Ví dụ:

| Cookie | Trang JavaScript ở / | Trang JavaScript ở /api/view | Request tới /api/orders |
| --- | --- | --- | --- |
| XSRF-TOKEN; Path=/ | Có thể đọc | Có thể đọc | Browser có thể gửi |
| XSRF-TOKEN; Path=/api | Thường không đọc được | Có thể đọc | Browser có thể gửi |
| JSESSIONID; Path=/; HttpOnly | Không đọc được | Không đọc được | Browser có thể gửi |

**Path không phải ranh giới bảo mật vững chắc chống script đã chiếm cùng origin.** Nó chủ yếu quy định phạm vi áp dụng cookie. Không dựa vào Path để bảo vệ session khỏi XSS.

### 3.5. SameSite khác với same-origin

**Origin** gồm scheme, hostname và port. **Site** trong cookie SameSite hiện đại dựa vào scheme và miền đăng ký được. Hai URL **https://app.example.com** và **https://api.example.com** thường **khác origin nhưng cùng site**.

| Tình huống | Ý nghĩa |
| --- | --- |
| Script tại app.example.com gọi chính app.example.com | Cùng origin; Fetch mặc định credentials=same-origin có thể gửi cookie phù hợp |
| Script tại app.example.com gọi api.example.com | Khác origin; Fetch cần credentials=include nếu muốn gửi cookie; cần CORS phù hợp |
| Script tại evil.example.com gọi api.example.com | Khác origin nhưng có thể cùng site; SameSite không phải biên giới tin cậy giữa mọi subdomain |
| Script tại attacker.test gọi api.example.com | Khác site; SameSite=Lax/Strict hạn chế nhiều request, nhưng không phải mọi điều hướng hoặc mô hình ứng dụng |

**SameSite=Lax** hỗ trợ giảm nhiều request cross-site không an toàn. Nhưng nó không có nghĩa JavaScript được đọc mọi cookie cùng site; cũng không loại bỏ nguy cơ từ subdomain không đáng tin cậy hoặc GET làm thay đổi trạng thái.

### 3.6. Một bảng quyết định nhanh

| Thuộc tính/cơ chế | JavaScript đọc cookie? | Browser tự gửi cookie? | Tác động tới CSRF |
| --- | --- | --- | --- |
| **HttpOnly=true** | Không | Có thể | Giảm đọc trộm cookie, không trực tiếp chặn CSRF |
| **HttpOnly=false** | Có nếu phạm vi khớp | Có thể | Cần cho thiết kế XSRF cookie đọc qua JS, nhưng tăng khả năng XSS đọc token |
| **Secure=true** | Có thể đọc trên ngữ cảnh phù hợp | Chỉ trên kênh được cho phép | Bảo vệ vận chuyển, không chứng minh ý định |
| **SameSite=Lax/Strict** | Không trực tiếp quyết định quyền đọc | Hạn chế theo ngữ cảnh site | Lớp giảm thiểu phụ trợ |
| **Domain/Path** | Chỉ khi phạm vi khớp | Chỉ khi phạm vi khớp | Quyết định khả năng bootstrap/đọc của SPA và cookie injection |
| **CORS** | Không cấp quyền đọc document.cookie của host khác | Không tự ép browser gửi cookie | Kiểm soát request/response JavaScript cross-origin, không thay CSRF |
| **CSP** | Không định nghĩa thuộc tính cookie | Không trực tiếp thay đổi gửi cookie | Hỗ trợ giảm rủi ro XSS, nhưng không thay token |

**Set-Cookie** là response header đặc biệt mà JavaScript không được đọc trực tiếp qua **fetch(...).headers.get("Set-Cookie")**. Muốn biết cookie JS-readable đã được lưu, kiểm tra **document.cookie** trên hostname/path phù hợp hoặc DevTools; muốn cấp token ở response body, dùng endpoint JSON thiết kế riêng.

## 4. Spring Security Servlet: chỉ mở quyền đọc cho cookie CSRF

Trong Servlet, **CookieCsrfTokenRepository** là repository thông dụng cho SPA đọc XSRF cookie. Ở chế độ mặc định, repository có thể phát cookie **HttpOnly**; chỉ khi JavaScript cần tự đọc giá trị từ cookie, sử dụng **withHttpOnlyFalse()**.

Ví dụ cho ứng dụng **Spring Boot 3, Spring Security 6.1+ và Java 17+** chạy trên HTTPS:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        CookieCsrfTokenRepository csrfRepository =
            CookieCsrfTokenRepository.withHttpOnlyFalse();

        csrfRepository.setCookieCustomizer(cookie -> cookie
            .secure(true)
            .sameSite("Lax")
            .path("/")
        );

        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfRepository)
                // SPA gửi token raw từ cookie qua header X-XSRF-TOKEN.
                .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

**Giải thích các lựa chọn:**

1. **withHttpOnlyFalse()** chỉ ảnh hưởng cookie **XSRF-TOKEN** của repository, không tự tắt HttpOnly trên **JSESSIONID**.
2. **csrfRepository.setCookieCustomizer(...)** cấu hình cookie CSRF. API này có mặt ở những phiên bản Spring Security 6 mới; nếu dùng phiên bản cũ, cần kiểm tra API tương ứng.
3. **Secure=true** phù hợp production HTTPS; HTTP local có thể không gửi cookie. Không hạ bảo mật production chỉ để phù hợp môi trường dev.
4. **SameSite=Lax** và **Path=/** là quyết định có điều kiện; cân nhắc SSO, topology và phạm vi cookie thực tế.
5. **CsrfTokenRequestAttributeHandler** chấp nhận **raw token** đọc từ cookie và gửi trong header; ứng dụng cùng lúc nhúng token vào HTML có thể cần handler phối hợp với XOR/BREACH thay vì thay mặc định như ví dụ JSON-only này.
6. **formLogin** minh họa một ứng dụng có cookie phiên; hệ thống có OAuth/OIDC, JSON login hay BFF cần tích hợp theo cơ chế thực tế.

### 4.1. Giữ cookie phiên HttpOnly một cách độc lập

Trong **Spring Boot Servlet**, có thể đặt chính sách session cookie trong cấu hình của ứng dụng:

~~~properties
# Ví dụ cho production HTTPS sử dụng servlet session:
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Các tùy chọn này điều khiển cookie phiên do server/framework quản lý. Chúng **không** thay thế **CookieCsrfTokenRepository.withHttpOnlyFalse()**, vì XSRF-TOKEN là cookie khác.

Nếu backend dùng JWT trong cookie do authentication handler tự phát, hãy đặt **HttpOnly, Secure, SameSite, Domain và Path** trên chính JWT cookie đó. Không dựa vào cấu hình JSESSIONID để suy ra mọi cookie tự đặt đều được bảo vệ.

### 4.2. Bootstrap XSRF cookie khi SPA mới mở

Spring Security có thể trì hoãn việc tải/tạo CSRF token (*deferred token*). Một GET chỉ đi qua filter chưa chắc đã khiến XSRF cookie xuất hiện. Endpoint sau **truy cập getToken()** để hiện thực hóa giá trị:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfBootstrapController {

    @GetMapping("/api/csrf")
    ResponseEntity<Void> csrf(CsrfToken token) {
        token.getToken();

        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Response lần đầu có thể giống:

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
Set-Cookie: XSRF-TOKEN=...; Path=/; Secure; SameSite=Lax
~~~

Nếu token/cookie đã tồn tại, server không bắt buộc phát lại **Set-Cookie** ở mọi GET. Khi bootstrap, frontend nên xác minh cookie thực sự tồn tại và đọc được **tại trang đang chạy**, không chỉ dựa vào status code 204.

### 4.3. Token raw và XOR masking ở Spring Security 6

Một nguyên nhân phổ biến của lỗi **403** là trộn hai biểu diễn:

- **Raw token**: giá trị nằm trong cookie **XSRF-TOKEN**; SPA thường đưa nguyên giá trị vào **X-XSRF-TOKEN**.
- **XOR-masked token**: giá trị Spring Security có thể đưa vào request attribute/HTML để giảm khả năng khai thác kiểu **BREACH** khi token nằm trong response nén.

Với cấu hình mặc định dùng **XorCsrfTokenRequestAttributeHandler**, header được xử lý theo định dạng phù hợp với handler. Nếu SPA gửi **raw cookie token** mà backend đang mong **masked token**, request có thể bị từ chối. Ở cấu hình JSON-only phía trên, **CsrfTokenRequestAttributeHandler** được chọn chủ động để nhận raw token.

Nếu ứng dụng vừa là SPA vừa render form HTML có token, có thể cần handler kết hợp **XOR cho request attribute/form** và **plain cho header raw**. Mẫu rút gọn dưới đây minh họa nguyên tắc trên Servlet:

~~~java
import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);
        // Hiện thực hóa deferred token để có thể tạo cookie khi cần.
        csrfToken.get().getToken();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {
        String value = request.getHeader(csrfToken.getHeaderName());
        return (StringUtils.hasText(value) ? plain : xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Mẫu này là **biến thể thay thế** cho plain handler ở phần 4 khi ứng dụng cần cả raw header và masked form. Chỉ sử dụng một handler nhất quán trong mỗi SecurityFilterChain, kiểm thử cụ thể theo phiên bản Spring Security. Không tự Base64-decode token từ cookie rồi gửi một giá trị khác định dạng mà backend mong đợi.

## 5. JavaScript đọc XSRF cookie, giữ cookie phiên ngoài tầm đọc

### 5.1. Hàm đọc cookie an toàn theo tên

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const pair = document.cookie
    .split("; ")
    .find(item => item.startsWith(prefix));

  return pair ? decodeURIComponent(pair.slice(prefix.length)) : null;
}
~~~

Ví dụ, khi trang và cookie cùng scope:

~~~javascript
const xsrfToken = readCookie("XSRF-TOKEN");

console.log(Boolean(xsrfToken));      // true nếu token đã được cấp.
console.log(readCookie("JSESSIONID")); // null nếu JSESSIONID là HttpOnly.
~~~

Không ghi **xsrfToken** vào console, log giám sát hoặc analytics ở production. Ví dụ chỉ kiểm tra boolean có token, không in giá trị. Đừng cố giải mã cookie phiên HttpOnly; JavaScript không có quyền đọc trực tiếp loại cookie đó.

### 5.2. Bootstrap và gửi request ghi

~~~javascript
let bootstrapPromise = null;

async function ensureXsrfToken() {
  const existing = readCookie("XSRF-TOKEN");
  if (existing) return existing;

  if (!bootstrapPromise) {
    bootstrapPromise = (async () => {
      const response = await fetch("/api/csrf", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error("CSRF bootstrap failed: " + response.status);
      }

      const token = readCookie("XSRF-TOKEN");
      if (!token) {
        throw new Error("CSRF cookie missing or not readable");
      }
      return token;
    })().finally(() => {
      bootstrapPromise = null;
    });
  }

  return bootstrapPromise;
}

async function updateProfile(profile) {
  const token = await ensureXsrfToken();

  const response = await fetch("/api/profile", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify(profile)
  });

  if (!response.ok) {
    throw new Error("Update failed: HTTP " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

**credentials: "same-origin"** cho request cùng origin giúp browser gửi các cookie phù hợp. JavaScript chỉ đọc **XSRF-TOKEN**; **JSESSIONID** vẫn được browser tự gửi khi thích hợp. Chức năng ghi đợi token trước khi gửi request, tránh race khi nhiều component SPA khởi tạo.

### 5.3. Header chỉ nên được thêm tới backend tin cậy

Một interceptor có thể thêm header cho mọi phương thức không an toàn trong API cùng origin:

~~~javascript
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function apiFetch(path, options = {}) {
  // Chỉ chấp nhận đường dẫn tương đối đến API cùng origin.
  if (typeof path !== "string" || !path.startsWith("/api/") ||
      path.startsWith("//")) {
    throw new Error("Unsupported API path");
  }

  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  if (UNSAFE.has(method)) {
    headers.set("X-XSRF-TOKEN", await ensureXsrfToken());
  }

  return fetch(path, {
    ...options,
    method,
    credentials: "same-origin",
    headers
  });
}
~~~

Đừng gắn XSRF token vào request đến URL do người dùng tùy ý nhập hoặc một origin ngoài danh sách API tin cậy. Nếu dùng framework với interceptor tự động (Angular/Axios), kiểm tra cách framework xử lý **URL tương đối, absolute URL và cross-origin** ở phiên bản đang sử dụng; nhiều client chỉ tự gắn XSRF header cho request đủ điều kiện cùng origin.

### 5.4. Khi có XSS, HttpOnly vẫn chưa đủ

Nếu attacker chạy được JavaScript trong origin SPA, script đó có thể gọi **readCookie("XSRF-TOKEN")**, gửi header và để browser tự kèm **JSESSIONID HttpOnly**. Do đó:

- Cookie phiên **HttpOnly** giảm khả năng đọc trộm trực tiếp session ID.
- Cookie XSRF **HttpOnly=false** là lựa chọn phục vụ SPA, không phải cơ chế bảo vệ chống XSS.
- CSRF token **không bảo vệ được** khi script độc hại có quyền thực thi như frontend cùng origin.
- Phải phòng XSS qua encoding đúng ngữ cảnh, tránh HTML/DOM injection, quản lý script và **Content Security Policy (CSP)** phù hợp, cùng security headers và HTTPS/HSTS.

XSS có thể là lỗ hổng nghiêm trọng dù cookie phiên luôn ẩn khỏi document.cookie.

## 6. WebFlux/Reactive: hai cookie, hai vai trò tương tự

Trong **Spring Security WebFlux**, repository tương ứng là **CookieServerCsrfTokenRepository**, cấu hình qua **ServerHttpSecurity**. Ví dụ dưới đây dành cho SPA JSON đọc raw XSRF cookie trong cùng origin:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;

@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse())
            .csrfTokenRequestHandler(
                new ServerCsrfTokenRequestAttributeHandler())
        )
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().authenticated()
        )
        .build();
}
~~~

**CookieServerCsrfTokenRepository.withHttpOnlyFalse()** điều khiển cookie CSRF, không phải cookie xác thực của WebSession. Nếu ứng dụng dùng WebSession, session cookie và CSRF cookie có thể cùng được gửi trong request nhưng là hai đối tượng độc lập.

### 6.1. Bootstrap token Reactive

CSRF filter có thể đưa **Mono<CsrfToken>** vào **ServerWebExchange**. Để repository phát cookie, endpoint cần **subscribe** vào Mono và truy cập token:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Void>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> csrfMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (csrfMono == null) {
            return Mono.error(
                new IllegalStateException("Reactive CSRF is not configured"));
        }

        return csrfMono.map(csrf -> {
            csrf.getToken();
            return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
        });
    }
}
~~~

Không gọi **block()** trong controller Reactive. Trong các phiên bản dùng **XorServerCsrfTokenRequestAttributeHandler** mặc định, phải xem xét raw token từ cookie và định dạng masked tương tự Servlet; handler raw ở ví dụ được chọn có chủ đích cho JSON-only SPA.

Nếu cấu hình cookie session Reactive riêng, giữ **HttpOnly** trên session cookie. Không sao chép các thuộc tính **server.servlet.session.cookie...** của Servlet rồi mặc định chúng áp dụng cho WebFlux. Cấu hình WebSession/cookie cần dựa vào stack và triển khai thực tế.

## 7. Trường hợp SPA và API khác origin

Đây là nơi người học dễ nhầm: **JavaScript không thể đọc cookie host-only của hostname khác, dù hai hostname cùng site**.

Giả sử:

| Thành phần | Origin |
| --- | --- |
| SPA | **https://app.example.com** |
| API | **https://api.example.com** |

API phát cookie:

~~~http
Set-Cookie: XSRF-TOKEN=...; Path=/; Secure; SameSite=Lax
~~~

với **không có Domain**, tức cookie host-only của **api.example.com**.

Tại trang **app.example.com**, JavaScript gọi **document.cookie** không nhìn thấy cookie host-only đó. Thêm **credentials: "include"** trong fetch **không cấp quyền đọc cookie qua document.cookie**. CORS cũng **không cho phép JS ở app.example.com đọc cookie host-only của api.example.com**.

### 7.1. Lựa chọn hợp lý: lấy CSRF token bằng JSON

API có thể cấp token qua endpoint **GET /api/csrf**, trả **token trong response body** được CORS giới hạn cho origin SPA đáng tin cậy. SPA đọc response JSON rồi gửi token qua header, còn cookie phiên và cookie CSRF (nếu dùng repository cookie) vẫn do browser quản lý ở phạm vi API.

Nếu không cần cookie CSRF JavaScript-readable, backend có thể dùng **HttpSessionCsrfTokenRepository** với session cookie **HttpOnly**, hoặc một repository thích hợp khác, và trả token theo JSON. Khi chỉ sử dụng JSON, **không bắt buộc** đặt một cookie XSRF có HttpOnly=false.

Ví dụ Servlet dùng repository session mặc định:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class JsonCsrfController {

    record TokenPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<TokenPayload> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF filter not configured");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new TokenPayload(token.getHeaderName(), token.getToken()));
    }
}
~~~

Trong cấu hình CSRF Servlet mặc định của Spring Security 6, token JSON có thể được XOR-mask trong request attribute. Client nên gửi lại **đúng giá trị JSON**, dùng **headerName** server cung cấp; không tự thay bằng một giá trị raw đọc từ cookie. Nếu dùng **CookieCsrfTokenRepository** và handler raw, phải thống nhất định dạng token trong JSON và header rồi kiểm thử tương ứng.

Client khác origin:

~~~javascript
const API = "https://api.example.com";

const bootstrap = await fetch(API + "/api/csrf", {
  credentials: "include",
  cache: "no-store"
});

if (!bootstrap.ok) throw new Error("Cannot fetch CSRF token");
const { headerName, token } = await bootstrap.json();

const response = await fetch(API + "/api/profile", {
  method: "PATCH",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ displayName: "Alice" })
});
~~~

### 7.2. CORS phải cho phép đúng origin và credentials

Với Servlet:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Thêm **.cors(Customizer.withDefaults())** vào Servlet **HttpSecurity**; với WebFlux dùng **CorsWebFilter** hoặc cấu hình CORS Reactive tương ứng, không dùng nhầm UrlBasedCorsConfigurationSource của Servlet.

**Không phản chiếu mọi Origin** kết hợp với credentials. API phải chỉ cho phép những origin tin cậy đọc token CSRF trả trong JSON. Đồng thời browser có thể từ chối gửi/lưu cookie vì SameSite, Secure, Domain, Path hoặc chính sách third-party cookies, kể cả khi CORS đúng.

### 7.3. Có nên mở Domain cookie để SPA đọc?

Việc đặt **Domain=example.com** cho XSRF cookie có thể giúp JavaScript tại **app.example.com** đọc cookie do API cấp, nhưng cũng mở rộng phạm vi cho các subdomain khác. Nếu một subdomain có nội dung không đáng tin cậy hoặc bị chiếm quyền, nguy cơ rò rỉ hoặc **cookie injection** tăng.

Ưu tiên **cookie host-only** và endpoint JSON được CORS giới hạn, hoặc đặt SPA/API dưới cùng một origin thông qua **BFF/reverse proxy**. Đừng coi Domain cookie là giải pháp mặc định chỉ vì tiện frontend.

## 8. Cookie injection, double-submit và giới hạn bảo vệ

Với kiểu double-submit, server có thể so giá trị header X-XSRF-TOKEN với token nạp từ cookie XSRF-TOKEN. Bên tấn công ngoài origin thông thường không đọc được cookie để tạo header hợp lệ; đó là lý do mô hình có ích.

Nhưng một hệ thống có nhiều subdomain cần xem xét **cookie injection**: subdomain không tin cậy, response splitting hoặc đường kiểm soát cookie khác có thể làm attacker tác động tới giá trị cookie hoặc tạo nhiều cookie trùng tên. Khi frontend đọc và phản chiếu giá trị bị chèn, thuộc tính bảo mật của CSRF token có thể bị ảnh hưởng.

Các hướng giảm thiểu:

1. **Ưu tiên cookie host-only**, tránh Domain rộng nếu không cần thiết.
2. Dùng cookie **Secure** trên HTTPS, kết hợp HSTS phù hợp, tránh khả năng chèn cookie qua kênh thiếu bảo vệ.
3. Cân nhắc tiền tố **__Host-** cho cookie khi đáp ứng đủ điều kiện **Secure**, **Path=/** và **không có Domain**. Khi đổi tên cookie, frontend phải đọc đúng tên mới.
4. Quản lý subdomain không đáng tin cậy, tên miền hết hạn và các dịch vụ có thể tạo **Set-Cookie**.
5. Với yêu cầu cao, cân nhắc **signed double-submit cookie** có HMAC ràng buộc với ngữ cảnh xác thực/phiên. **CookieCsrfTokenRepository không mặc định cung cấp một signed double-submit được ràng buộc mật mã với session**.
6. Sử dụng kiểm tra Origin/Referer hoặc Fetch Metadata làm lớp phụ trợ khi phù hợp; xử lý trường hợp header thiếu và các client hợp lệ.
7. Kiểm thử luôn hành vi của browser và hậu quả trên dữ liệu, không chỉ kiểm tra hai chuỗi token giống nhau.

Token trong cookie JavaScript-readable còn có thể bị script XSS đọc. XSS phải được giải quyết độc lập; chỉ đổi XSRF cookie thành HttpOnly không tự sửa XSS hoặc chứng minh request có ý định hợp lệ.

## 9. Vòng đời: sau login/logout, session hết hạn và nhiều tab

Spring Security có thể xóa token CSRF cũ khi xác thực thành công (**CsrfAuthenticationStrategy**) hoặc đăng xuất (**CsrfLogoutHandler**). Cookie XSRF có thể bị hết hạn/xóa khi đó; SPA cần đảm bảo một token mới được tạo trước request ghi tiếp theo.

Ví dụ:

~~~text
Mở SPA → GET /api/csrf → XSRF-TOKEN=A
POST /login với cookie phiên và X-XSRF-TOKEN=A
Login thành công → Spring Security có thể xóa A
GET /api/csrf trong phiên mới → XSRF-TOKEN=B
POST /api/profile với X-XSRF-TOKEN=B
POST /logout dùng token hiện tại
Sau logout nếu SPA tiếp tục hoạt động → bootstrap XSRF token lại
~~~

**Không giả định token luôn đổi hoặc luôn giữ nguyên**; việc xoay vòng tùy repository, chiến lược xác thực và cấu hình Spring Security. Điều quan trọng là frontend **tái đồng bộ** khi trạng thái xác thực/phiên đổi.

Nếu session hết hạn, backend có thể trả **401** hoặc **403** tùy filter/entry point. **403** không đồng nghĩa chắc chắn với lỗi CSRF: nó cũng có thể biểu thị thiếu quyền. Không tự lặp lại POST gây tác dụng phụ chỉ vì nhận 403; cần phân loại nguyên nhân và xử lý có kiểm soát.

Khi nhiều tab cùng mở, cookie dùng chung có thể đổi theo đăng nhập/đăng xuất ở tab khác, còn bộ nhớ JavaScript của từng tab không tự đồng bộ. Nên kiểm thử token cũ trong tab khác và cung cấp luồng tải lại/đăng nhập lại hợp lý.

## 10. Kiểm thử Servlet: chứng minh hai vai trò cookie

Giả sử ứng dụng có GET **/api/csrf** như phần 4 và POST **/api/profile** cập nhật dữ liệu. Với **spring-security-test** và **MockMvc**, có thể kiểm thử rằng cookie XSRF được tạo, việc gửi cookie **mà thiếu header** bị từ chối, và token raw hợp lệ trong header mới vượt qua CsrfFilter.

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfCookieVisibilityTests {

    @Autowired MockMvc mvc;

    @Test
    void csrfCookieCanBeReadButCookieAloneDoesNotAuthorizePost()
            throws Exception {
        MvcResult bootstrap = mvc.perform(get("/api/csrf"))
            .andExpect(status().isNoContent())
            .andReturn();

        Cookie xsrf = bootstrap.getResponse().getCookie("XSRF-TOKEN");
        assertNotNull(xsrf, "Expected CSRF cookie after bootstrap");
        assertFalse(xsrf.isHttpOnly(), "Frontend must read XSRF cookie");

        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .cookie(xsrf)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", "invalid")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/profile")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", xsrf.getValue())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"displayName\":\"Alice\"}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Giới hạn cần hiểu:** **user("alice")** giả lập người dùng đã được xác thực để tập trung vào CSRF filter; nó **không kiểm chứng cookie JSESSIONID** hay login thực tế. Nên bổ sung integration test với browser hoặc HTTP client duy trì cookie jar để xác nhận session cookie có HttpOnly, CSRF cookie không có HttpOnly, và POST gửi đúng token mà vẫn chịu kiểm tra quyền.

Test giả định POST /api/profile tồn tại và trả 2xx khi hợp lệ. Hãy bổ sung assertion rằng **dữ liệu không thay đổi** với request thiếu/sai token. Với repository/handler khác hoặc cookie đã tồn tại, **Set-Cookie** không nhất thiết xuất hiện ở mọi GET.

### 10.1. Kiểm thử HttpOnly ở trình duyệt

1. Đăng nhập và mở DevTools **Application/Storage → Cookies**: cookie xác thực cần được đánh dấu **HttpOnly**, XSRF cookie có thể không đánh dấu nếu JS cần đọc.
2. Trên console của SPA, kiểm tra **document.cookie** thấy XSRF cookie nhưng không thấy JSESSIONID. Đừng in/đưa giá trị bí mật vào báo cáo; chỉ xác nhận tên/trạng thái.
3. Trong **Network → POST /api/profile**, kiểm tra browser có gửi cookie xác thực và frontend chủ động thêm **X-XSRF-TOKEN**.
4. Bỏ header trong request kiểm thử: kết quả phải bị chặn và dữ liệu không thay đổi, dù Cookie header vẫn có hai cookie.
5. Đổi session/login/logout rồi thử token cũ: frontend phải có khả năng đồng bộ token lại.

### 10.2. Test WebFlux bằng WebTestClient

Để kiểm tra bước lọc ở Reactive có thể dùng **spring-security-test**:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// webTestClient đã gắn Spring Security, POST /api/profile tồn tại:
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/profile")
    .bodyValue(Map.of("displayName", "Alice"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/profile")
    .bodyValue(Map.of("displayName", "Alice"))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Đây là đoạn thân test; cần **java.util.Map**, WebTestClient và handler thực tế. **csrf()** mô phỏng token hợp lệ ở tầng test, không tự xác nhận cookie XSRF thực tế có HttpOnly=false. Bổ sung integration test GET bootstrap, lấy cookie **XSRF-TOKEN** từ response và POST với cookie + header raw để đánh giá đúng cấu hình Reactive.

### 10.3. Ma trận test hành vi

| Kịch bản | Kỳ vọng |
| --- | --- |
| Cookie phiên **HttpOnly**, JavaScript gọi document.cookie | Không thấy giá trị cookie phiên |
| Cookie XSRF **HttpOnly=false**, phạm vi đúng | JavaScript đọc được token |
| Cookie XSRF đặt **HttpOnly=true** nhưng frontend đọc cookie | document.cookie không trả token; cần thay thiết kế hoặc cấp token JSON |
| POST có cookie xác thực và XSRF cookie nhưng thiếu header | Bị từ chối, thường 403; dữ liệu không đổi |
| POST có header token sai | Bị từ chối; dữ liệu không đổi |
| POST có token raw đúng và cookie/phiên hợp lệ | Vượt CSRF; vẫn chịu xác thực, phân quyền và validation |
| POST có CSRF token đúng nhưng chưa đăng nhập | Không được cấp quyền thao tác |
| SPA ở app.example.com đọc XSRF cookie host-only của api.example.com | Không đọc được qua document.cookie |
| Token JSON được trả cho origin không tin cậy qua CORS | **Lỗi cấu hình**; phải giới hạn origin và credentials |
| XSRF cookie Path=/api, SPA chạy tại / | JavaScript có thể không thấy cookie theo Path |
| Sau login/logout, dùng token cũ | Có thể bị từ chối; cần làm mới phù hợp vòng đời |
| Script độc hại chạy cùng origin SPA | Có thể sử dụng XSRF token và request với cookie HttpOnly; phải chống XSS độc lập |

## 11. Chẩn đoán lỗi phổ biến

### “JSESSIONID không xuất hiện trong document.cookie: session có bị mất không?”

Không. Nếu JSESSIONID có **HttpOnly**, JavaScript không thấy là **hành vi mong muốn**. Hãy xem cookie trong DevTools Application/Storage và request Cookie header trên Network. Kiểm tra server có xác thực được request hay không, không cố bỏ HttpOnly.

### “XSRF-TOKEN không xuất hiện trong document.cookie”

Kiểm tra cookie có thực sự được phát sau GET bootstrap chưa; **HttpOnly**, **Domain**, **Path**, **Secure**, hostname và trạng thái cookie trong browser. Nếu SPA đang ở subdomain khác API, một cookie host-only của API không được JavaScript tại SPA đọc.

### “XSRF-TOKEN có nhưng POST vẫn 403”

Xem frontend có gửi header **X-XSRF-TOKEN** không; token header là raw hay masked; repository và request handler cùng cấu hình không; cookie có bị đổi/xóa sau login/logout không. Tiếp tục phân biệt **InvalidCsrfTokenException**, **MissingCsrfTokenException** với lỗi authorization.

### “CORS đã allow origin nhưng JS vẫn không đọc được cookie API”

CORS cho phép frontend đọc một **response** được cấp quyền; nó **không thay đổi phạm vi document.cookie**. Dùng JSON endpoint trả token cho origin tin cậy hoặc thiết kế cùng origin qua BFF/reverse proxy.

### “HttpOnly=false cho XSRF có làm lộ cookie phiên không?”

Không trực tiếp; hai cookie độc lập. Đặt HttpOnly=false trên CSRF cookie không tự sửa thuộc tính JSESSIONID. Nhưng XSS vẫn có thể đọc token CSRF và gọi API dùng cookie HttpOnly, nên phải phòng XSS.

### “Backend stateless dùng JWT cookie nên không cần CSRF?”

Sai. Nếu backend chấp nhận cookie JWT do browser tự gửi làm xác thực, vẫn cần đánh giá CSRF cho thao tác có tác động. Chỉ một API thực sự Bearer-only (client chủ động gửi Authorization và không có cookie fallback) mới có thể kết luận CSRF truyền thống thường không áp dụng trong điều kiện đã xác minh.

### “Có SameSite, CSP, HSTS, CORS, HTTP firewall rồi có cần token?”

Đây là những lớp phòng vệ bổ sung có mục đích riêng. **SameSite** giới hạn bối cảnh cookie được gửi; **CSP** giảm rủi ro XSS; **HSTS** bảo vệ chuyển hướng HTTPS; **CORS** quản lý JavaScript cross-origin; **HTTP firewall** loại bỏ những request không hợp lệ. Không một cơ chế nào tự thay kiểm tra CSRF cho mọi thao tác xác thực bằng cookie.

## 12. Bài tập và câu hỏi tự kiểm tra

**Tình huống A:** SPA tại **https://app.example.com** có JSESSIONID HttpOnly và XSRF-TOKEN không có HttpOnly, cùng Path=/. Browser gửi cả hai cookie trong POST. Frontend quên header X-XSRF-TOKEN.

**Đánh giá:** POST phải bị CSRF filter chặn dù browser gửi hai cookie. Cookie XSRF chỉ là nguồn để JavaScript lấy token, không phải bằng chứng đủ khi tự gửi.

**Tình huống B:** API tại **https://api.example.com** phát XSRF cookie host-only. SPA chạy trên **https://app.example.com**, fetch sử dụng credentials=include. JavaScript đọc document.cookie nhưng không thấy XSRF-TOKEN.

**Đánh giá:** Đây là giới hạn của host-only cookie và origin/hostname, không được giải quyết bởi credentials=include hoặc CORS. Dùng endpoint JSON cấp token cho SPA qua CORS allowlist tin cậy.

**Tình huống C:** Developer bỏ HttpOnly trên JSESSIONID để Angular có thể đọc XSRF cookie.

**Đánh giá:** Không đúng vai trò. Giữ HttpOnly trên JSESSIONID, chỉ tạo cookie XSRF JavaScript-readable nếu cần, hoặc lấy token JSON.

**Tình huống D:** Ứng dụng dùng CookieCsrfTokenRepository.withHttpOnlyFalse() nhưng Spring Security 6 mặc định xử lý XOR-mask, còn SPA gửi raw cookie token.

**Đánh giá:** Có thể gặp 403 dù cookie và header khớp nhau về chuỗi. Chọn request handler nhất quán với raw header, đồng thời cân nhắc masking/BREACH khi render HTML.

**Tình huống E:** Subdomain bên thứ ba có quyền đặt cookie Domain=example.com, trong khi ứng dụng dùng double-submit cookie không có chữ ký ràng buộc.

**Đánh giá:** Cần xem xét cookie injection, dùng host-only hoặc tiền tố __Host- khi phù hợp, cân nhắc signed double-submit và kiểm soát subdomain.

## 13. Nguyên tắc cần ghi nhớ

1. **Cookie phiên bảo vệ danh tính, cookie CSRF hỗ trợ kiểm tra tính chủ ý.** Vai trò khác nhau dẫn đến chính sách HttpOnly khác nhau.
2. **Browser có thể tự gửi cookie HttpOnly**, nhưng JavaScript không đọc trực tiếp giá trị. Vì vậy HttpOnly không chống CSRF.
3. **XSRF-TOKEN JavaScript-readable** chỉ khi SPA cần đọc từ cookie; có thể thay bằng endpoint JSON mà không cần mở quyền đọc cookie.
4. **Chỉ gửi cookie XSRF là chưa đủ.** Frontend cần chủ động thêm **X-XSRF-TOKEN**, backend cần so khớp theo repository/handler.
5. **Domain và Path quyết định cookie nào JS nhìn thấy.** Cookie host-only của API ở subdomain khác không tự đọc được từ origin SPA; CORS không thay đổi điều này.
6. **Giữ cookie đăng nhập HttpOnly, Secure và SameSite phù hợp**, chỉ đặt HttpOnly=false cho cookie token CSRF khi kiến trúc yêu cầu.
7. **Raw token và XOR-masked token phải nhất quán** với Spring Security Servlet/Reactive; bootstrap cần hiện thực hóa deferred token.
8. **Chống XSS, cookie injection, bảo vệ subdomain và HTTPS/HSTS** song hành với CSRF; cookie HttpOnly không vô hiệu hóa mã độc đang chạy cùng origin.
9. **Kiểm thử bằng request thực và trạng thái dữ liệu**: thiếu/sai/đúng header, cookie scope, login/logout, CORS, Servlet/WebFlux và quyền truy cập.

Khi thiết kế SPA trên Spring Security, hãy giữ ranh giới rõ ràng: **cookie phiên được browser tự gửi và nên ẩn khỏi JavaScript; cookie CSRF có thể cho JavaScript đọc để tạo header chứng minh luồng frontend hợp lệ; cả hai vẫn phải chịu chính sách cookie và kiểm tra bảo mật độc lập**.
