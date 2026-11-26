# Cookie đăng nhập và cách đánh giá CSRF cho API JSON

## Mục tiêu bài học

Trong một ứng dụng Spring Security, API trả về và nhận JSON vẫn có thể bị **Cross-Site Request Forgery (CSRF)** nếu trình duyệt tự động đính kèm thông tin đăng nhập vào yêu cầu. Nội dung này tập trung vào cách nhận diện rủi ro khi SPA gọi API bằng cookie phiên, đối chiếu với API dùng Bearer token, thiết kế biện pháp phòng vệ và kiểm thử trên cả **Spring MVC (Servlet)** lẫn **Spring WebFlux (Reactive)**.

Sau bài học, bạn có thể:

- Giải thích vì sao việc dùng JSON, REST hoặc CORS không tự động loại bỏ CSRF.
- Phân biệt **origin**, **site**, cookie **SameSite**, cơ chế **credentials** và tác động của từng yếu tố.
- Đánh giá một endpoint thay đổi trạng thái có thể bị kích hoạt bởi trang web độc hại hay không.
- Cấu hình CSRF token cho SPA dùng session cookie, lựa chọn cách chuyển token qua JSON hoặc cookie và xử lý tình huống khác origin.
- Viết kiểm thử yêu cầu thiếu/sai/đúng CSRF token và chẩn đoán lỗi 403 trong môi trường thực tế.

## 1. CSRF phụ thuộc vào cách gửi thông tin xác thực

CSRF là tình huống kẻ tấn công khiến **trình duyệt đang đăng nhập của nạn nhân** gửi một yêu cầu ngoài ý muốn đến hệ thống đích. Điểm mấu chốt là trình duyệt có thể tự gắn thông tin xác thực, chẳng hạn cookie phiên, cho yêu cầu hợp lệ về mặt đăng nhập.

Giả sử người dùng đã đăng nhập vào **https://api.example.com** và có cookie phiên:

~~~http
Cookie: JSESSIONID=abc123
~~~

Nếu API cập nhật thông tin tài khoản dựa trên phiên đó, một yêu cầu không chủ ý vẫn có thể được xử lý như hành động của người dùng:

~~~http
POST /api/account/email HTTP/1.1
Host: api.example.com
Cookie: JSESSIONID=abc123
Content-Type: application/json

{"email":"new@example.com"}
~~~

Ở đây, **cookie chứng minh trình duyệt đang giữ phiên**; nó không chứng minh người dùng cố ý thực hiện thao tác. CSRF token là một tín hiệu bổ sung giúp máy chủ phân biệt yêu cầu hợp lệ do ứng dụng của mình khởi tạo với yêu cầu chỉ dựa vào cookie tự động gửi.

| Kiểu xác thực của API | Browser có tự gửi thông tin đăng nhập? | Hướng đánh giá CSRF |
| --- | --- | --- |
| Session cookie, ví dụ **JSESSIONID** | Có, khi quy tắc cookie và chế độ credentials cho phép | Phải xem xét CSRF đối với thao tác thay đổi trạng thái. |
| JWT lưu trong cookie và máy chủ xác thực từ cookie | Có | Về CSRF, rủi ro tương tự session cookie; JWT không tự giải quyết vấn đề. |
| **Authorization: Bearer ...** do JavaScript chủ động thêm, máy chủ chỉ chấp nhận header này | Thông thường không tự thêm từ website khác | CSRF truyền thống thường không phải mối đe dọa chính; vẫn phải chống XSS, rò rỉ token và phân quyền sai. |
| HTTP Basic đã được trình duyệt ghi nhớ hoặc xác thực trình duyệt tự gửi | Có thể có | Phải đánh giá khả năng gửi xác thực tự động tương tự cookie. |
| Mobile/server-to-server dùng Bearer token, không dùng cookie phiên từ trình duyệt | Không trong mô hình browser thông thường | Tập trung vào xác thực, phân quyền, giới hạn truy cập và bảo vệ token. |

**Quy tắc quyết định:** Đừng hỏi “đây có phải API JSON không?” trước tiên. Hãy hỏi “**một trang khác có thể khiến trình duyệt gửi yêu cầu đã được xác thực mà người dùng không đồng ý không?**”.

## 2. Vì sao JSON và CORS không đủ để kết luận an toàn?

### 2.1. Browser có thể gửi yêu cầu dù không đọc được phản hồi

Chính sách **Same-Origin Policy** hạn chế JavaScript trên một origin đọc dữ liệu từ origin khác. Nhưng CSRF thường **không cần đọc phản hồi**: mục đích là kích hoạt thao tác như đổi email, tạo đơn hàng hoặc cập nhật cấu hình.

**CORS** điều chỉnh việc trình duyệt cho phép JavaScript thực hiện và đọc các yêu cầu khác origin. Với yêu cầu cần preflight, CORS cũng có thể chặn yêu cầu thực tế. Tuy nhiên, CORS không thay thế được kiểm soát tính chủ ý của một hành động:

- Biểu mẫu HTML có thể tạo các yêu cầu **GET/POST** với kiểu dữ liệu đơn giản mà không cần preflight.
- Yêu cầu có **Content-Type: application/json** từ JavaScript khác origin thường cần preflight; cấu hình CORS từ chối preflight làm giảm khả năng khai thác qua đường này.
- Nếu API cũng chấp nhận **application/x-www-form-urlencoded**, **multipart/form-data** hoặc **text/plain**, hoặc tự diễn giải JSON từ kiểu dữ liệu không đúng, kẻ tấn công có thể tận dụng đường gửi không cần preflight.
- CORS cho phép credentials từ origin không đáng tin cậy, kiểm tra Origin lỏng lẻo hoặc cho phép origin theo cách phản chiếu tùy tiện đều có thể làm tăng rủi ro.
- Endpoint **GET** gây thay đổi trạng thái là lỗi thiết kế nguy hiểm; cookie SameSite=Lax vẫn có thể đi cùng một số yêu cầu điều hướng GET ở cấp cao nhất.

Ví dụ sau chỉ có thể gây thay đổi trạng thái nếu API **thực sự chấp nhận** body dạng **text/plain** và browser gửi được cookie theo chính sách hiện hành:

~~~javascript
// Minh họa kịch bản tấn công để đánh giá ứng dụng được phép kiểm thử.
fetch("https://api.example.com/api/preferences", {
  method: "POST",
  mode: "no-cors",
  credentials: "include",
  headers: { "Content-Type": "text/plain" },
  body: JSON.stringify({ emailNotifications: false })
});
~~~

Đoạn mã không thể giả mạo một header CSRF hợp lệ chỉ bằng cách biết URL API. Nếu API từ chối **text/plain** và chỉ nhận **application/json**, đường gửi này sẽ không tương thích. Đó là một lớp giảm thiểu hữu ích, nhưng cần kiểm chứng cả cấu hình cookie, CORS, endpoint khác và cách máy chủ kiểm tra token.

### 2.2. Phân biệt origin với site

**Origin** gồm bộ ba **scheme + host + port**. **Site** trong chính sách SameSite hiện đại được xác định theo scheme và miền đăng ký được (registrable domain); cổng không quyết định site.

| Trang gọi | API đích | Quan hệ | Ý nghĩa |
| --- | --- | --- | --- |
| https://app.example.com | https://app.example.com | Cùng origin | Fetch mặc định có thể gửi cookie theo chế độ **same-origin**. |
| https://app.example.com | https://api.example.com | Khác origin, thường cùng site | JavaScript cần CORS và thường cần **credentials: "include"**; cookie **SameSite=Lax** vẫn có thể được gửi vì cùng site. |
| https://evil.example.com | https://api.example.com | Khác origin nhưng cùng site | **SameSite** không ngăn mọi tình huống; phải xét độ tin cậy của các subdomain. |
| https://untrusted.test | https://api.example.com | Khác site | Cookie **Lax/Strict** có thể chặn nhiều yêu cầu, nhưng không phải mọi kiểu điều hướng hay mô hình sử dụng. |

Vì vậy, một hệ thống có nhiều subdomain cần đánh giá cả **subdomain do bên thứ ba kiểm soát**, subdomain bị chiếm quyền và trường hợp ứng dụng web, API đặt khác origin. Ngay cả khi request là same-site, JavaScript giữa hai subdomain vẫn bị ràng buộc bởi quy tắc origin và CORS.

### 2.3. SameSite và thuộc tính cookie hỗ trợ, không thay CSRF token

| Thuộc tính | Tác dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| **HttpOnly** | Ngăn JavaScript đọc cookie bằng **document.cookie** | Trình duyệt vẫn tự gửi cookie trong những request phù hợp; không trực tiếp chặn CSRF. |
| **Secure** | Chỉ gửi cookie trên kết nối an toàn, với một số ngoại lệ trình duyệt/localhost | Không bảo đảm yêu cầu xuất phát từ UI hợp lệ. |
| **SameSite=Strict** | Hạn chế cookie trong bối cảnh cross-site | Có thể ảnh hưởng luồng điều hướng, đăng nhập liên kết và tích hợp. |
| **SameSite=Lax** | Hạn chế nhiều request cross-site không an toàn | Có các trường hợp điều hướng cấp cao bằng phương thức an toàn; không chặn yêu cầu từ origin khác nhưng cùng site. |
| **SameSite=None; Secure** | Cho phép cookie trong bối cảnh cross-site khi trình duyệt cho phép | Mở rộng bề mặt CSRF và có thể bị chính sách chặn third-party cookie ảnh hưởng. |
| **Domain/Path** | Điều khiển phạm vi cookie | Cookie chia sẻ cho nhiều subdomain có thể tạo thêm rủi ro nếu subdomain kém tin cậy. |

Trong ứng dụng dùng phiên, cookie xác thực nên được cấu hình **HttpOnly**, **Secure** trên HTTPS và một giá trị **SameSite** phù hợp luồng sử dụng. Không đặt cookie **JSESSIONID** thành JavaScript-readable chỉ để xử lý CSRF; token CSRF và cookie đăng nhập có vai trò khác nhau.

## 3. Quy trình đánh giá CSRF cho từng endpoint API JSON

Thực hiện lần lượt các câu hỏi sau; một kết luận tốt phải dựa trên hành vi thực tế ở trình duyệt và máy chủ:

1. **Thông tin xác thực đến từ đâu?** Kiểm tra request đã đăng nhập trong DevTools/Network: **Cookie**, **Authorization**, HTTP Basic hay kết hợp nhiều cơ chế? Nếu máy chủ chấp nhận cookie làm xác thực dự phòng, cần đánh giá theo nhánh cookie dù SPA chủ yếu gửi Bearer token.
2. **Trình duyệt có gửi được xác thực trong bối cảnh tấn công?** Xem scheme, domain, path, SameSite, phương thức HTTP, cùng site/khác site và giá trị **credentials** của Fetch/Axios. Kiểm tra request thực tế thay vì suy đoán từ tên miền.
3. **Endpoint có tác động hay không?** Liệt kê **POST/PUT/PATCH/DELETE**, đăng nhập/đăng xuất, upload, thay đổi cấu hình và mọi **GET** vô tình thay đổi dữ liệu. Không coi idempotent đồng nghĩa với miễn CSRF: PUT và DELETE vẫn có tác động.
4. **Kiểu request nào được máy chủ tiếp nhận?** Kiểm tra ràng buộc **Content-Type**, parser, form endpoint, **text/plain**, override HTTP method và khả năng CORS/preflight. Không mặc định một endpoint “JSON” chỉ chấp nhận JSON vì tài liệu API ghi như vậy.
5. **Máy chủ xác minh sự chủ ý bằng gì?** Kiểm tra token CSRF có gắn với phiên hoặc được bảo vệ chống giả mạo không; header token có được bắt buộc ở thao tác nguy hiểm không; quy trình cấp mới token có dùng đúng phiên không.
6. **Biện pháp phụ trợ có chính xác không?** Xem kiểm tra **Origin/Referer**, Fetch Metadata (**Sec-Fetch-Site**), SameSite, CORS allowlist, giới hạn domain cookie và HTTPS. Đây là các lớp phòng vệ bổ sung, không nên mặc định thay token.
7. **Kiểm thử yêu cầu thiếu, sai và hợp lệ.** Ghi lại mã trạng thái và việc dữ liệu thực sự thay đổi hay không; lặp lại sau đăng nhập mới, đăng xuất, session hết hạn và từ subdomain khác origin.

### Ma trận ra quyết định thực hành

| Tình huống | Kết luận hành động |
| --- | --- |
| SPA đăng nhập bằng session cookie; JSON POST cập nhật dữ liệu | **Bật CSRF protection** cho các phương thức không an toàn, chuyển token qua header. |
| API chỉ dùng Bearer token trong header, backend không nhận cookie làm xác thực | Có thể **không cần CSRF** cho chuỗi xử lý hoàn toàn stateless này; phải xác minh các giả định và bảo vệ token. |
| API dùng cookie nhưng chỉ nhận JSON và CORS chặt | Rủi ro tấn công cross-site cổ điển thấp hơn; vẫn giữ CSRF để chống lỗi cấu hình, các điểm vào khác và thay đổi về sau. |
| SPA ở subdomain riêng, API dùng cookie host-only | Cần CORS đúng origin, **credentials: "include"** và kênh cấp token SPA đọc được; chú ý không thể đọc cookie host-only của API bằng JS ở subdomain khác. |
| Có subdomain không đáng tin cậy cùng site | Không dựa vào SameSite làm ranh giới tin cậy; giữ CSRF token, thu hẹp phạm vi cookie, quản lý subdomain. |

## 4. Cấu hình Servlet: API JSON dùng session cookie

Với **Spring Security Servlet**, CSRF mặc định được bật trong cấu hình web thông thường. Những request không an toàn như **POST/PUT/PATCH/DELETE** cần token hợp lệ; các request **GET/HEAD/OPTIONS/TRACE** mặc định không yêu cầu CSRF token. Đây là điểm xuất phát tốt cho ứng dụng SPA sử dụng cookie phiên.

### 4.1. Cách ưu tiên: cấp token qua endpoint JSON

Mô hình này giữ cookie xác thực **HttpOnly** và có thể dùng **HttpSessionCsrfTokenRepository** (repository mặc định của Servlet). SPA lấy token qua một GET cùng phiên, rồi gửi token bằng header trong yêu cầu thay đổi dữ liệu.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().permitAll()
            )
            .build();
    }
}
~~~

Endpoint sau truy xuất token do Spring Security gắn vào request và gọi **getToken()** để hiện thực hóa token nếu đang được tải trì hoãn:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfController {
    @GetMapping("/api/csrf")
    Map<String, String> csrf(HttpServletRequest request) {
        CsrfToken csrfToken =
            (CsrfToken) request.getAttribute(CsrfToken.class.getName());

        if (csrfToken == null) {
            throw new IllegalStateException("CSRF protection is unavailable");
        }

        return Map.of(
            "headerName", csrfToken.getHeaderName(),
            "token", csrfToken.getToken()
        );
    }
}
~~~

Với Spring Security hiện đại, giá trị token xuất hiện qua request attribute có thể được **mask** để giảm rủi ro BREACH; hãy gửi lại chính token được endpoint cung cấp. Bộ xử lý CSRF của Spring Security tương ứng sẽ xác minh đúng định dạng. Đừng tự cắt, giải mã hoặc thay đổi token.

Ở phía SPA cùng origin:

~~~javascript
async function createOrder(order) {
  // GET phải dùng cùng phiên đăng nhập với yêu cầu POST phía dưới.
  const tokenResponse = await fetch("/api/csrf", {
    credentials: "same-origin"
  });
  if (!tokenResponse.ok) throw new Error("Cannot obtain CSRF token");

  const { headerName, token } = await tokenResponse.json();

  const response = await fetch("/api/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [headerName]: token
    },
    body: JSON.stringify(order)
  });

  if (!response.ok) throw new Error("Order request failed: " + response.status);
  return response.json();
}
~~~

**Dòng chảy cần nhớ:** trình duyệt gửi cookie phiên → Spring Security cấp token gắn với phiên → SPA đọc token qua phản hồi được phép → SPA gửi token trong header → máy chủ kiểm tra **cả xác thực lẫn CSRF** trước khi xử lý thay đổi trạng thái.

Trong ứng dụng thực, cập nhật lại token khi đăng nhập/đăng xuất, thay đổi phiên, nhận lỗi CSRF do token cũ hoặc khi ứng dụng khởi tạo phiên mới. Spring Security có thể xóa token cũ trong quá trình xác thực và logout; việc SPA lưu token mãi trong bộ nhớ sẽ gây lỗi 403 sau những chuyển trạng thái này. Không đặt token phiên vào URL hoặc log.

### 4.2. Lựa chọn khác: cookie XSRF-TOKEN cho SPA cùng origin

Một số SPA muốn đọc token trực tiếp từ cookie **XSRF-TOKEN** và gửi lại trong header **X-XSRF-TOKEN**. Spring Security Servlet hỗ trợ **CookieCsrfTokenRepository**:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;

// Thay phần cấu hình csrf(...) ở ví dụ trên:
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
)
~~~

**withHttpOnlyFalse()** chỉ phù hợp cho cookie **token CSRF** mà JavaScript cần đọc; cookie xác thực vẫn giữ **HttpOnly=true**. **CsrfTokenRequestAttributeHandler** cho phép nhận token nguyên bản từ cookie qua header. Cấu hình minh họa dành cho API JSON không nhúng token vào HTML; nếu ứng dụng đồng thời render biểu mẫu HTML, cần cân nhắc bộ xử lý SPA bảo toàn cơ chế masking/BREACH theo phiên bản Spring Security đang dùng.

Đảm bảo SPA kích hoạt việc tạo token (chẳng hạn gọi **GET /api/csrf** như trên) vì Spring Security có cơ chế deferred token; không mặc định cookie sẽ xuất hiện khi chưa có thao tác nào truy cập token.

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const entry = document.cookie.split("; ").find(part => part.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}

async function updateProfile(profile) {
  const token = readCookie("XSRF-TOKEN");
  if (!token) throw new Error("CSRF cookie is missing");

  return fetch("/api/profile", {
    method: "PATCH",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify(profile)
  });
}
~~~

Đây là biến thể **double-submit cookie**. Khi dùng, cần cân nhắc nguy cơ chèn/ghi đè cookie từ subdomain không đáng tin cậy, giới hạn **Domain/Path**, HTTPS và lựa chọn repository phù hợp. Không lấy việc JS có thể đọc token làm lý do cho phép JS đọc session cookie. XSS có thể vượt qua nhiều hàng rào CSRF, nên vẫn phải xử lý XSS độc lập.

## 5. SPA khác origin: CORS, credentials và phạm vi cookie

Giả sử SPA tại **https://app.example.com** gọi API tại **https://api.example.com**:

- Hai địa chỉ **khác origin**: Fetch mặc định **credentials: "same-origin"** sẽ không gửi cookie khi gọi API. SPA thường phải dùng **credentials: "include"**.
- Server phải cho phép origin chính xác của SPA và cho phép credentials qua CORS; preflight cho request có header CSRF/JSON phải được xử lý đúng.
- Cookie phiên cần được trình duyệt chấp nhận theo **SameSite**, **Secure**, chính sách cookie và bối cảnh same-site/cross-site; cấu hình CORS đúng **không thể** cưỡng ép trình duyệt gửi một cookie đã bị chặn.
- Cookie **XSRF-TOKEN** do **api.example.com** cấp theo phạm vi host-only không đọc được bằng **document.cookie** trên **app.example.com**. Phương án thường rõ ràng hơn là cho SPA gọi **GET /api/csrf** và nhận token trong JSON qua CORS được kiểm soát.

Ví dụ cấu hình CORS phía Servlet khi thực sự có SPA khác origin:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    config.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Kết nối cấu hình này với Spring Security:

~~~java
// Thêm vào chuỗi cấu hình HttpSecurity:
.cors(Customizer.withDefaults())
~~~

**Không** phản chiếu tùy ý mọi **Origin** kết hợp với cho phép credentials. Khi xác thực bằng cookie, client cần **credentials: "include"** ở cả lần lấy token và lần gửi thao tác; API chỉ cấp dữ liệu token cho origin được tin cậy. Nếu ứng dụng và API ở **khác site** thực sự, cookie có thể cần **SameSite=None; Secure** và vẫn chịu chính sách third-party cookie của trình duyệt. Khi đó cần đánh giá kiến trúc đăng nhập (ví dụ BFF/cùng site), thay vì chỉ nới CORS.

Ví dụ phía client khác origin:

~~~javascript
const API = "https://api.example.com";

const csrf = await fetch(API + "/api/csrf", {
  credentials: "include"
}).then(response => {
  if (!response.ok) throw new Error("CSRF fetch failed");
  return response.json();
});

await fetch(API + "/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ sku: "P100", quantity: 1 })
});
~~~

## 6. WebFlux/Reactive: giữ nguyên nguyên tắc

Với **Spring Security WebFlux**, cơ chế tương ứng nằm ở **SecurityWebFilterChain** và thường sử dụng token lưu trong **WebSession**. API Reactive dùng cookie phiên vẫn cần CSRF protection trên những phương thức thay đổi dữ liệu.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Bean
SecurityWebFilterChain webFluxSecurity(ServerHttpSecurity http) {
    return http
        .csrf(Customizer.withDefaults())
        .authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().permitAll()
        )
        .build();
}
~~~

Có thể cấp token qua endpoint JSON bằng cách lấy **Mono<CsrfToken>** mà CSRF filter đặt trong **ServerWebExchange**:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

@RestController
class ReactiveCsrfController {
    @GetMapping("/api/csrf")
    Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException("CSRF protection is unavailable"));
        }

        return token.map(t -> Map.of(
            "headerName", t.getHeaderName(),
            "token", t.getToken()
        ));
    }
}
~~~

Việc đăng ký/subscribe **Mono** giúp token được hiện thực hóa trước khi trả về JSON. Tùy phiên bản Spring Security, cấu hình mặc định có thể sử dụng cơ chế masking và deferred loading; SPA nên dùng token do endpoint cung cấp, không giả định format token. Nếu chuyển sang repository cookie trong WebFlux, lớp liên quan là **CookieServerCsrfTokenRepository**; cần cấu hình và kiểm thử request handler Reactive phù hợp, không bê nguyên lớp Servlet vào WebFlux.

## 7. Kiểm thử CSRF: nhìn vào kết quả máy chủ và trạng thái dữ liệu

Để đánh giá đúng, cần kiểm thử **cả yêu cầu bị từ chối lẫn yêu cầu hợp lệ**. Đừng chỉ kiểm tra có header hay cookie; phải xác nhận thao tác nguy hiểm không thực thi khi thiếu token.

### 7.1. Spring MVC với MockMvc

Đoạn kiểm thử sau giả định có endpoint **POST /api/orders**, với người dùng đã xác thực:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderCsrfTests {
    @Autowired MockMvc mockMvc;

    @Test
    void rejectsPostWithoutCsrf() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void acceptsPostWithCsrf() throws Exception {
        mockMvc.perform(post("/api/orders")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**spring-security-test** cung cấp **csrf()** và **user()**; phải thêm dependency kiểm thử tương ứng. Khi một endpoint có quy tắc nghiệp vụ khác, điều chỉnh status thành công được kỳ vọng. Bổ sung test với token sai (**csrf().useInvalidToken()**) và kiểm tra dữ liệu vẫn nguyên trạng. Những test này xác nhận Spring Security filter; nên có thêm kiểm thử tích hợp sử dụng cookie, login và luồng cấp token thực tế để phát hiện lỗi sau session rotation hoặc CORS.

### 7.2. Spring WebFlux với WebTestClient

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// webTestClient đã gắn cấu hình Spring Security:
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

Các đoạn Reactive trên là phần thân test minh họa; trong test thực tế cần chuẩn bị **WebTestClient**, controller/handler và import **Map**. Nếu chỉ có test thông qua mock mà không kiểm tra trình duyệt, bạn vẫn có thể bỏ sót lỗi cookie SameSite, CORS và giới hạn origin.

### 7.3. Kịch bản kiểm thử trình duyệt nên có

| Trường hợp | Kỳ vọng |
| --- | --- |
| POST/PATCH/DELETE có cookie đăng nhập nhưng **không có CSRF token** | Bị từ chối, thường **403**, không thay đổi dữ liệu. |
| Token sai hoặc token cũ của phiên khác | Bị từ chối, không thay đổi dữ liệu. |
| Có cookie phiên và token hợp lệ từ cùng phiên | Vượt kiểm tra CSRF; kết quả cuối tùy quyền truy cập và dữ liệu đầu vào. |
| Token hợp lệ nhưng không đăng nhập/không đủ quyền | Vẫn bị chặn bởi xác thực/phân quyền; CSRF token không cấp quyền. |
| Trang ngoài origin cố gửi **application/json** kèm custom header | Preflight bị từ chối nếu origin không nằm trong CORS allowlist. |
| Trang ngoài origin cố gửi form hoặc **text/plain** | Không được thực thi thao tác; API nên từ chối kiểu dữ liệu ngoài hợp đồng và kiểm tra token. |
| Đăng nhập lại hoặc đăng xuất rồi dùng token cũ | Token cũ không còn được xem là hợp lệ theo vòng đời token/phiên; SPA có cách lấy token mới. |
| SPA tại subdomain được phép gửi cookie và lấy token JSON | Header token, cookie và CORS hoạt động đúng cho origin được tin cậy. |

Khi tái hiện tấn công, dùng môi trường bạn được phép kiểm thử. Quan sát **Network** để xác nhận request có thực sự đến máy chủ và có kèm cookie không. Một lỗi **CORS trên console**, lỗi **401** do chưa đăng nhập và lỗi **403** do thiếu CSRF có nguyên nhân khác nhau.

## 8. Chẩn đoán các xung đột triển khai thường gặp

### “API đã yêu cầu JSON, sao vẫn có 403?”

Spring Security kiểm tra CSRF trước khi controller xử lý nội dung; một POST có JSON hợp lệ vẫn thiếu token nếu SPA không gửi header. Kiểm tra **X-CSRF-TOKEN** hoặc **X-XSRF-TOKEN**, repository đang sử dụng, tên header thực tế và phiên cấp token. Đối chiếu log filter để phân biệt **MissingCsrfTokenException** với **InvalidCsrfTokenException** khi có cấu hình log phù hợp.

### “GET /api/csrf thành công nhưng POST tiếp theo thất bại”

Kiểm tra hai request có dùng **cùng cookie phiên** không. Với SPA khác origin, quên **credentials: "include"** là lỗi phổ biến. Xem thêm token cũ sau login/logout, cookie bị chặn bởi SameSite, header có bị proxy xóa, và token có bị ứng dụng tự xử lý sai định dạng masked/raw không.

### “CORS đã cho phép mà cookie vẫn không gửi”

CORS và cookie là hai lớp quyết định khác nhau. Kiểm tra **credentials**, **Set-Cookie**, **Secure**, **SameSite**, Domain, Path, HTTPS và chính sách third-party cookies. **Access-Control-Allow-Credentials: true** không ép trình duyệt bỏ qua SameSite.

### “JS không đọc được XSRF-TOKEN”

Kiểm tra cookie đã được cấp hay chưa, **HttpOnly**, Domain, Path và origin của trang. Tại **app.example.com**, JS không đọc cookie host-only của **api.example.com**; dùng endpoint trả token bằng JSON với CORS phù hợp thay vì mở rộng Domain một cách tùy tiện.

### “Muốn tắt CSRF cho toàn bộ /api/** vì API là REST”

Đây là quyết định dựa trên **cơ chế xác thực**, không dựa vào tiền tố URL. Nếu **/api/** có endpoint đăng nhập bằng cookie, việc bỏ CSRF mở ra khả năng kích hoạt thao tác bằng phiên của nạn nhân. Chỉ xem xét bỏ CSRF trong một **SecurityFilterChain** riêng thực sự stateless, dùng Bearer token và không chấp nhận cookie/browser-managed credentials; kiểm thử thứ tự matcher giữa các chain.

### “Có SameSite và kiểm tra Origin rồi, còn cần token không?”

SameSite chặn một tập hành vi cross-site; nó không phân biệt tốt các origin cùng site. Kiểm tra **Origin**, **Referer** hay **Sec-Fetch-Site** có thể thêm lớp phát hiện và từ chối yêu cầu đáng ngờ nhưng phải xét header vắng mặt, điều hướng, proxy và các client hợp lệ. CSRF token gắn với phiên/yêu cầu vẫn là biện pháp chủ đạo cho API dùng cookie phiên.

## 9. Những nguyên tắc cần giữ khi thiết kế

1. **Giữ CSRF protection** cho API JSON khi trình duyệt tự gửi session cookie hoặc thông tin xác thực tương đương.
2. **Không dùng GET để thay đổi trạng thái**; kiểm tra phương thức và **Content-Type** nghiêm ngặt.
3. **Đặt cookie đăng nhập HttpOnly, Secure và SameSite thích hợp**; chỉ cho JS đọc cookie token CSRF khi kiến trúc thực sự yêu cầu.
4. **Cấp token cho SPA qua kênh tin cậy**, gửi token ở header của request nguy hiểm; lấy lại token khi phiên hoặc trạng thái xác thực thay đổi.
5. **CORS giới hạn origin và credentials**, nhất là khi SPA khác origin với API; kiểm tra cả preflight và browser cookie policy.
6. **Phân biệt Servlet và Reactive**: lần lượt dùng **SecurityFilterChain/CsrfToken** và **SecurityWebFilterChain/Mono<CsrfToken>**, đúng repository và request handler của từng stack.
7. **Kiểm thử thiếu/sai/đúng token**, kiểm tra dữ liệu không thay đổi ở trường hợp bị chặn, rồi chạy thêm luồng đăng nhập và trình duyệt thật.

Khi đánh giá CSRF, **nguồn xác thực**, **khả năng trình duyệt tự gắn xác thực**, **kiểu yêu cầu thực sự được backend chấp nhận** và **biện pháp xác minh chủ ý** luôn quan trọng hơn nhãn “REST”, “SPA” hay “JSON”.
