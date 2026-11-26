# Cookie XSRF và header do frontend gửi

## Mục tiêu bài học

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, ta tìm hiểu một cơ chế rất thường gặp trong SPA: server phát cookie **XSRF-TOKEN**, frontend đọc cookie đó bằng JavaScript và gửi giá trị trong header **X-XSRF-TOKEN** khi thực hiện thao tác thay đổi trạng thái. Server kiểm tra token từ request trước khi cho phép controller chạy.

Đây là một cách phối hợp **CSRF protection của Spring Security** với frontend dùng Fetch, Axios, Angular, React hoặc Vue. Bài học đi từ cơ chế HTTP đến cấu hình **Servlet** và **Reactive**, từ token raw/XOR trong Spring Security đến cookie scope, CORS, SameSite, login/logout, kiểm thử và chẩn đoán lỗi triển khai.

Sau bài học, người học có thể:

- Giải thích vì sao cần cả **cookie XSRF** và **header được JavaScript chủ động gửi**, và vì sao chúng khác cookie đăng nhập.
- Triển khai **CookieCsrfTokenRepository**, khởi tạo token đúng lúc và đọc token từ cookie trên trình duyệt.
- Hiểu sự khác nhau giữa **token raw** trong cookie và **token được XOR-mask** ở request attribute trên Spring Security hiện đại.
- Cấu hình đúng request handler cho SPA trên Servlet, xác định phương án tương ứng trong WebFlux.
- Đánh giá phạm vi cookie, khác origin/cùng site, CORS, SameSite, XSS và rủi ro cookie injection.
- Kiểm thử thiếu/sai/đúng token, vòng đời sau xác thực và phân biệt lỗi 403 do CSRF với lỗi phân quyền.

## 1. XSRF là gì? Tại sao phải có header do frontend gửi?

**Cross-Site Request Forgery (CSRF)** là hành vi dụ trình duyệt đã đăng nhập gửi một request ngoài ý muốn đến ứng dụng. Browser có thể tự đính kèm **JSESSIONID**, cookie JWT hoặc thông tin xác thực được quản lý tự động. Vì vậy server thấy request đã xác thực, nhưng chưa biết nó đến từ giao diện đáng tin cậy hay một trang độc hại.

Ví dụ request ghi dữ liệu chỉ dựa vào cookie:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=abc123
Content-Type: application/x-www-form-urlencoded

displayName=Changed
~~~

Nếu endpoint chấp nhận cookie làm xác thực mà không kiểm tra tính chủ ý, một trang khác có thể gây request tương tự trong những bối cảnh browser cho phép gửi cookie. **JSON API** và **backend stateless** không tự động loại trừ CSRF nếu thông tin xác thực vẫn do browser tự gửi.

Một SPA hợp lệ dùng cơ chế XSRF thường gửi:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=abc123; XSRF-TOKEN=csrf-raw-value
X-XSRF-TOKEN: csrf-raw-value
Content-Type: application/json

{"displayName":"New Name"}
~~~

Có ba yếu tố cần phân biệt:

| Thành phần | Ai tạo/gửi? | Vai trò |
| --- | --- | --- |
| **JSESSIONID** hoặc cookie xác thực khác | Server cấp; browser tự gửi khi phù hợp | Xác định danh tính/phiên; không chứng minh ý định |
| **XSRF-TOKEN** | CSRF repository cấp; browser tự gửi cookie phù hợp | Giúp frontend tiếp cận token; bản thân cookie vẫn là dữ liệu browser tự gửi |
| **X-XSRF-TOKEN** | JavaScript hợp lệ chủ động đọc token và thêm header | Thể hiện request đi qua logic frontend có thể đọc cookie token; server kiểm tra tính hợp lệ |

Nếu browser gửi **cả JSESSIONID và XSRF-TOKEN** nhưng **không có X-XSRF-TOKEN**, request ghi vẫn phải bị từ chối. Một trang ngoài origin thường không thể đọc cookie qua JavaScript theo Same-Origin Policy. Đồng thời HTML form thông thường không thể tự tạo custom header tùy ý.

**Tên cookie/header chỉ là quy ước.** Spring Security có thể dùng **XSRF-TOKEN** và **X-XSRF-TOKEN** khi chọn CookieCsrfTokenRepository; nếu tự đổi tên, frontend và backend phải đồng nhất.

### 1.1. Không nhầm XSRF token với access token

Cookie đăng nhập thường phải **HttpOnly** để giảm nguy cơ JavaScript lấy trực tiếp. Cookie XSRF trong mô hình này cần được JavaScript **đọc**, nên được đặt **HttpOnly=false** theo chủ đích. Đừng vì vậy đặt **JSESSIONID** hoặc cookie refresh token thành JavaScript-readable.

CSRF token không thay thế login, phân quyền, validation, HTTPS hoặc chống XSS. Nếu mã độc chạy được ngay trong origin đáng tin cậy (XSS), nó có thể đọc cookie XSRF và tự gửi header như ứng dụng thật.

### 1.2. Mô hình Double-submit cookie

Luồng **cookie → JavaScript → header → server** thường được gọi là *double-submit cookie*. Với Spring Security, CookieCsrfTokenRepository lưu token thông qua cookie và đối chiếu giá trị được gửi từ request với token nạp từ repository.

Đây là một lớp phòng vệ hữu ích, nhưng **chỉ so sánh cookie với header chưa chứng minh toàn bộ hệ thống an toàn**. Nếu một subdomain không đáng tin cậy có thể đặt hoặc ghi đè cookie thuộc Domain rộng, có thể xuất hiện biến thể **cookie injection**. Với ứng dụng nhạy cảm, xem xét **signed double-submit token** có HMAC và ràng buộc an toàn với phiên/danh tính, cookie host-only và quản trị subdomain. CookieCsrfTokenRepository không tự biến token thành signed double-submit ràng buộc với phiên đăng nhập.

## 2. Luồng request khi SPA khởi động và gửi POST

~~~mermaid
sequenceDiagram
    autonumber
    participant SPA as Frontend SPA
    participant SEC as Spring Security
    participant API as Controller
    SPA->>SEC: GET /api/csrf (bootstrap)
    SEC->>SEC: Tải hoặc tạo token trong CookieCsrfTokenRepository
    SEC-->>SPA: Set-Cookie: XSRF-TOKEN=raw; 204 hoặc 200
    Note over SPA: JavaScript đọc XSRF-TOKEN từ document.cookie
    SPA->>SEC: POST /api/orders + JSESSIONID + XSRF-TOKEN
    Note over SPA,SEC: Header X-XSRF-TOKEN: raw
    SEC->>SEC: Kiểm tra raw header so với token repository
    alt Token hợp lệ, xác thực và quyền phù hợp
        SEC->>API: Chuyển request đến controller
        API-->>SPA: Kết quả nghiệp vụ
    else Thiếu hoặc sai CSRF token
        SEC-->>SPA: Thường là 403 Forbidden
    end
~~~

Một request GET thông thường **không nhất thiết tự tạo XSRF cookie** vì Spring Security có thể trì hoãn việc tạo/nạp token (*deferred token*). Ứng dụng nên có điểm bootstrap rõ ràng, hoặc cấu hình request handler buộc token được hiện thực hóa. Sau login/logout và những lần đổi phiên, frontend phải lấy token mới khi repository/token cũ bị vô hiệu hóa.

Trong luồng mặc định, Spring Security thường **không** yêu cầu CSRF token cho **GET, HEAD, OPTIONS, TRACE**, còn phương thức thay đổi trạng thái thường cần token. Không dùng GET cho thao tác ghi; cookie SameSite=Lax vẫn có thể được gửi trong một số điều hướng GET cấp cao.

## 3. Cấu hình Spring Security Servlet cho SPA đọc XSRF cookie

Phần này giả định **Spring Boot 3, Spring Security 6.1+ và Java 17+**, backend xác thực bằng session cookie và SPA cùng origin. Điểm đáng chú ý là **request handler** khi kết hợp cookie token raw với cơ chế XOR/masking của Spring Security.

### 3.1. Cấu hình CookieCsrfTokenRepository

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        CookieCsrfTokenRepository repository =
            CookieCsrfTokenRepository.withHttpOnlyFalse();

        // Áp dụng khi ứng dụng triển khai HTTPS ở production.
        repository.setCookieCustomizer(cookie -> cookie
            .secure(true)
            .sameSite("Lax")
            .path("/")
        );

        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(repository)
                .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
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

Đoạn trên sử dụng **setCookieCustomizer** trên phiên bản Spring Security hỗ trợ API này. Trên phiên bản khác cần kiểm tra các tùy chọn cookie tương ứng. Ở môi trường development HTTP, cookie **Secure** sẽ không được gửi trong bối cảnh HTTP thông thường; hãy dùng HTTPS local hoặc cấu hình theo môi trường, tránh bỏ Secure ở production.

**Các quyết định bảo mật của ví dụ:**

- **withHttpOnlyFalse()** dành riêng cho cookie **XSRF-TOKEN** mà frontend phải đọc. Cookie session vẫn HttpOnly theo cấu hình riêng của session.
- **Secure=true** bảo đảm cookie XSRF chỉ được gửi qua HTTPS trong môi trường triển khai thông thường.
- **SameSite=Lax** giảm một số tình huống cross-site, nhưng các origin khác nhau cùng site vẫn cần được đánh giá.
- Không cấu hình **Domain** thì cookie thường là **host-only**, tránh chia sẻ tự động cho mọi subdomain.
- **Path=/** cho phép JavaScript trên các đường dẫn của cùng hostname đọc cookie; nếu cần thu hẹp phạm vi, phải bảo đảm bootstrap và API ghi vẫn hoạt động.
- **formLogin** minh họa một luồng dùng session cookie. Dự án thực tế có thể có JSON login, OAuth/OIDC hoặc BFF thay thế; cần giữ CSRF cho các endpoint dùng cookie.

### 3.2. Vì sao cần SpaCsrfTokenRequestHandler?

Với Spring Security 6, handler mặc định có thể đưa ra **token đã XOR-mask** trên request attribute để giảm rủi ro kiểu **BREACH** khi token xuất hiện trong HTML có nén. Nhưng cookie **XSRF-TOKEN** chứa **raw token**, frontend đọc và gửi lại nguyên raw token trong **X-XSRF-TOKEN**.

Nếu backend xử lý header như một token XOR-mask, request sẽ có thể bị từ chối **403 InvalidCsrfTokenException** dù cookie và header hiển thị cùng giá trị.

Một handler SPA cho Servlet có thể dùng **XOR** khi đưa token ra request attribute (để giữ cơ chế masking cho trường hợp render HTML), nhưng dùng handler **plain** khi token đến từ header:

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

        // Giữ masking trên request attribute cho HTML/SSR khi cần.
        this.xor.handle(request, response, csrfToken);

        // Buộc deferred token được nạp/tạo để XSRF cookie có thể được phát.
        csrfToken.get().getToken();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {

        String headerValue = request.getHeader(csrfToken.getHeaderName());

        // Header của SPA mang raw token từ XSRF cookie.
        // Tham số form (nếu có) dùng handler XOR tương ứng.
        return (StringUtils.hasText(headerValue) ? this.plain : this.xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

**Cơ chế cần hiểu:**

1. **XorCsrfTokenRequestAttributeHandler** đặt token ở request attribute với định dạng phù hợp masking.
2. **csrfToken.get().getToken()** kích hoạt deferred token, giúp repository phát cookie khi cần (đổi lại có thêm việc nạp/tạo token).
3. Nếu request có header **X-XSRF-TOKEN**, **CsrfTokenRequestAttributeHandler** đọc raw token; Spring Security đối chiếu với repository.
4. Nếu token lấy từ parameter của form server-side, handler XOR xử lý định dạng masked.

Cách trên phục vụ luồng SPA cookie raw và HTML dùng masked token. Nếu ứng dụng chỉ có API JSON và không render token vào HTML, có thể cấu hình đơn giản hơn bằng **new CsrfTokenRequestAttributeHandler()** cho toàn bộ luồng raw token, nhưng hãy hiểu sự đánh đổi đối với masking/BREACH. Không sao chép đồng thời hai biến thể handler rồi mong chúng hoạt động giống nhau.

### 3.3. Endpoint bootstrap tạo XSRF cookie

Có thể cấp endpoint nhẹ để client khởi tạo token trước khi gửi POST:

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
        // Truy cập token để chắc chắn deferred token đã được hiện thực hóa.
        token.getToken();

        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Trong cấu hình handler ở trên, việc tạo cookie có thể đã được kích hoạt ngay trong filter; endpoint vẫn giúp SPA có thời điểm bootstrap rõ ràng và tránh phụ thuộc một request ngẫu nhiên. **204 No Content** là hợp lệ vì client lấy token từ **cookie**, không cần nội dung JSON.

Response điển hình (chỉ minh họa):

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
Set-Cookie: XSRF-TOKEN=...; Path=/; Secure; SameSite=Lax
~~~

Cookie thực tế có thể được phát trong request khác nếu đã có token, và Set-Cookie có thể vắng khi giá trị cũ đã tồn tại. Khi cần cấp token trực tiếp cho SPA **khác origin**, endpoint **GET /api/csrf trả JSON** có thể thuận tiện và an toàn về mặt phạm vi cookie hơn (xem phần 7).

## 4. Frontend: đọc cookie rồi thêm X-XSRF-TOKEN

Ở cùng origin, frontend có thể đọc cookie bằng **document.cookie**. Code dưới đây không dựa vào framework cụ thể; cùng tư tưởng áp dụng cho React, Vue, Angular hoặc Fetch service chung.

### 4.1. Hàm đọc cookie và bootstrap

~~~javascript
const API_BASE = "";

function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const part = document.cookie
    .split("; ")
    .find(item => item.startsWith(prefix));

  return part ? decodeURIComponent(part.slice(prefix.length)) : null;
}

let bootstrapPromise = null;

async function ensureXsrfReady() {
  // Có thể dùng cookie sẵn có; ví dụ gọi bootstrap khi vừa mở SPA.
  const current = readCookie("XSRF-TOKEN");
  if (current) return current;

  if (!bootstrapPromise) {
    bootstrapPromise = fetch(API_BASE + "/api/csrf", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store"
    }).then(response => {
      if (!response.ok) {
        throw new Error("XSRF bootstrap failed: " + response.status);
      }

      const token = readCookie("XSRF-TOKEN");
      if (!token) {
        throw new Error("XSRF cookie was not created");
      }
      return token;
    }).finally(() => {
      bootstrapPromise = null;
    });
  }

  return bootstrapPromise;
}
~~~

**Ý nghĩa của Promise chung:** Nhiều component có thể cùng gọi API khi SPA vừa khởi động. Cơ chế trên giúp chúng đợi cùng một request bootstrap và không gửi POST trước khi token sẵn sàng.

Ví dụ cần có HTTPS và cookie scope phù hợp. Nếu đang test ở **http://localhost**, cookie **Secure** của cấu hình production có thể không hoạt động như kỳ vọng; xem DevTools/Application và response **Set-Cookie**.

### 4.2. Gắn header vào request không an toàn

~~~javascript
async function createOrder(order) {
  const csrf = await ensureXsrfReady();

  const response = await fetch(API_BASE + "/api/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": csrf
    },
    body: JSON.stringify(order)
  });

  if (response.status === 403) {
    throw new Error("Forbidden: check CSRF token and permissions");
  }
  if (!response.ok) {
    throw new Error("Failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

Header **X-XSRF-TOKEN** nên được thêm khi request ghi thực sự cần CSRF. Một HTTP interceptor có thể quản lý việc này tập trung để các thao tác **POST/PUT/PATCH/DELETE** không bỏ quên header.

Không tạo header tùy chỉnh với một chuỗi token giả do frontend tự sinh: **server phát token và quyết định tính hợp lệ**. Cũng không đưa CSRF token vào query string hay log.

### 4.3. Dùng Fetch interceptor đơn giản

~~~javascript
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

async function apiFetch(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  if (UNSAFE_METHODS.has(method)) {
    const token = await ensureXsrfReady();
    headers.set("X-XSRF-TOKEN", token);
  }

  return fetch(API_BASE + path, {
    ...options,
    method,
    credentials: "same-origin",
    headers
  });
}
~~~

Trong ứng dụng thực tế cần giới hạn rõ **API_BASE/path** để không gửi token tới URL không tin cậy. Không lấy URL tùy ý từ người dùng rồi thêm header CSRF và cookie vào request. Hàm minh họa trên dành cho **đường dẫn API cùng origin**.

### 4.4. Angular, Axios và các client khác

Một số HTTP client có hỗ trợ sẵn việc đọc **XSRF-TOKEN** và gắn **X-XSRF-TOKEN**. Ví dụ Angular HttpClient có cơ chế XSRF protection tích hợp; các phiên bản Angular hiện đại cho phép cấu hình tên cookie/header khi đăng ký HttpClient. Tuy nhiên, **đường dẫn tương đối, URL same-origin và URL cross-origin** có thể được xử lý khác nhau, đặc biệt khi client chỉ tự thêm XSRF header cho URL đủ điều kiện.

Với Axios, tùy phiên bản, cấu hình **xsrfCookieName**, **xsrfHeaderName**, và chính sách có tự thêm header XSRF trong request cross-origin hay không cần được kiểm tra. Không chỉ thấy tên cookie/header đúng rồi kết luận Axios hoặc Angular đã gửi header; hãy xem **Network** của request thật và kiểm thử các endpoint ghi.

Trường hợp client vừa có API same-origin vừa gọi dịch vụ thứ ba, nên cấu hình interceptor **chỉ cho phép gửi XSRF token tới backend đáng tin cậy**.

## 5. Cookie bảo mật: quy tắc quan trọng

Cookie **XSRF-TOKEN** cần JavaScript đọc được trong cơ chế này. Điều đó không đồng nghĩa có thể bỏ qua các thuộc tính bảo mật còn lại.

| Thuộc tính | Nên cân nhắc | Điều cần nhớ |
| --- | --- | --- |
| **HttpOnly** | **false** riêng cho XSRF cookie nếu JavaScript đọc | Cookie xác thực nên **HttpOnly=true** |
| **Secure** | **true** trên HTTPS production | HTTP thông thường không gửi Secure cookie |
| **SameSite** | **Lax** hoặc **Strict** khi tương thích luồng đăng nhập | Không phân biệt origin khác nhau nhưng cùng site |
| **Domain** | Ưu tiên bỏ trống (host-only) | Domain rộng như .example.com mở phạm vi cho các subdomain |
| **Path** | Phù hợp SPA và API, thường / | JS và browser phải thấy cookie trong đường dẫn cần dùng |
| **Max-Age/Expires** | Phù hợp vòng đời token | Token tồn tại quá lâu có thể không khớp chính sách đăng nhập |
| **Tên cookie** | Có thể dùng tiền tố __Host- nếu đủ điều kiện | __Host- cần Secure, Path=/, không có Domain; frontend phải đọc đúng tên mới |

**HttpOnly=false không biến token thành thông tin xác thực đầy đủ.** Một kẻ tấn công đọc được XSRF cookie qua XSS thường cũng có khả năng gọi API dưới quyền người dùng. Vì vậy phải phòng XSS qua encoding đúng ngữ cảnh, CSP phù hợp, quản lý script và thư viện bên thứ ba.

**SameSite=Lax/Strict** là lớp phòng vệ phụ trợ. Cookie Lax vẫn có thể đi cùng một số điều hướng GET cấp cao; không để GET thực thi tác động nghiệp vụ. Origin cùng site nhưng khác subdomain vẫn là trường hợp cần xét độ tin cậy của subdomain.

### 5.1. Cookie injection và rủi ro double-submit

Nếu cookie CSRF đặt **Domain=.example.com**, một subdomain không đáng tin cậy có thể có khả năng cố đặt cookie thuộc miền cha hoặc gây tình trạng nhiều cookie trùng tên/path. Browser và framework có thể lựa chọn cookie khác với dự kiến trong những cấu hình này.

**Không coi cookie + header có cùng chuỗi là bảo đảm mật mã mạnh** nếu người tấn công có cách tác động đến cookie. Nên kết hợp:

- Cookie host-only và giới hạn scope, ưu tiên tiền tố **__Host-** nếu kiến trúc cho phép.
- HTTPS cùng HSTS và bảo vệ subdomain khỏi bị chiếm quyền.
- Tránh chia sẻ cookie CSRF với subdomain bên thứ ba không đáng tin cậy.
- Với yêu cầu cao, dùng **signed double-submit token** có ràng buộc cryptographic với phiên/đăng nhập, hoặc một kiến trúc token đồng bộ phù hợp.
- Kiểm tra **Origin/Referer** hoặc Fetch Metadata như lớp phụ trợ có chính sách xử lý header thiếu rõ ràng.

**CookieCsrfTokenRepository** giúp triển khai mô hình cookie-header thông dụng; nó không mặc định tạo chữ ký HMAC liên kết token CSRF với JWT hay session đăng nhập.

## 6. Vòng đời token sau login/logout và session rotation

Spring Security có thể xóa token khi xác thực thành công (**CsrfAuthenticationStrategy**) hoặc logout (**CsrfLogoutHandler**). Với CookieCsrfTokenRepository, việc xóa token có thể dẫn đến Set-Cookie làm hết hạn cookie XSRF. SPA không nên giữ một bản sao token lâu dài và dùng mãi sau khi thay đổi trạng thái đăng nhập.

Luồng khuyến nghị:

~~~text
Mở SPA → GET /api/csrf → nhận XSRF-TOKEN=A
POST /login kèm cookie phiên và X-XSRF-TOKEN=A
Login thành công → server có thể xóa token A
GET /api/csrf lại trong ngữ cảnh phiên hiện tại → nhận token B
POST /api/orders kèm X-XSRF-TOKEN=B
POST /logout với token đang hợp lệ → token/cookie có thể bị xóa
Nếu tiếp tục dùng SPA anonymous → GET /api/csrf để khởi tạo lại
~~~

Tùy handler, token có thể được tạo lại trên request kế tiếp; frontend nên **chủ động đồng bộ token khi trạng thái xác thực đổi**, không chờ một request POST thất bại.

~~~javascript
async function afterLoginOrLogout() {
  // Nếu SPA vẫn hoạt động sau sự kiện xác thực:
  await fetch("/api/csrf", {
    credentials: "same-origin",
    cache: "no-store"
  });

  const token = readCookie("XSRF-TOKEN");
  if (!token) throw new Error("Cannot refresh XSRF token");
  return token;
}
~~~

Trong SPA thật, có thể dùng biến trạng thái và kiểm soát race giữa login/logout và các request đang chạy. Nếu login xảy ra ở tab A còn tab B vẫn mở, token/cookie ở tab B có thể thay đổi; kiểm thử nhiều tab và session timeout.

**Không tự retry nguyên POST** ngay khi gặp 403: 403 cũng có thể do thiếu quyền. Khi lỗi rõ là token cũ, lấy lại token và chỉ thực hiện lại thao tác sau khi kiểm tra tính an toàn/khả năng trùng lặp nghiệp vụ.

## 7. SPA khác origin: khi nào frontend không đọc được cookie?

Giả sử SPA ở **https://app.example.com** và API ở **https://api.example.com**. Đây là **hai origin khác nhau**, dù thường cùng site.

Nếu server API cấp cookie **XSRF-TOKEN** host-only cho **api.example.com**, JavaScript tại **app.example.com** **không đọc được cookie này qua document.cookie**. CORS cho phép đọc response không thay đổi phạm vi đọc cookie trên DOM. Chỉ thêm **credentials: "include"** cũng không cho JavaScript đọc cookie host-only của origin khác.

### 7.1. Một lựa chọn tốt: endpoint JSON trả token

Với topology khác origin, có thể dùng endpoint **GET /api/csrf** trả token trong JSON, được CORS allowlist chỉ cho SPA tin cậy đọc. Frontend gửi token đó qua header vào POST. Cookie XSRF vẫn có thể tồn tại phía API để repository so khớp, nhưng JS không cần đọc cookie trực tiếp.

Ví dụ Servlet controller tương ứng:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CrossOriginCsrfController {

    record TokenResponse(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<TokenResponse> csrf(CsrfToken token) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new TokenResponse(token.getHeaderName(), token.getToken()));
    }
}
~~~

**Lưu ý raw/XOR quan trọng:** Với **SpaCsrfTokenRequestHandler** ở phần 3.2, token lấy từ request attribute có thể là **masked token**. Handler trong ví dụ được thiết kế để **header của SPA nhận raw token từ cookie**, vì vậy **không được trộn tùy tiện token JSON masked với luồng header raw**. Nếu chọn phương án JSON cho SPA khác origin, cấu hình request handler phải thống nhất: chẳng hạn dùng **CsrfTokenRequestAttributeHandler** để nhận token raw trong cả JSON và header (với đánh giá BREACH phù hợp), hoặc thiết kế handler có khả năng nhận định dạng tương ứng một cách rõ ràng và có kiểm thử.

Với API **chỉ trả JSON**, không nhúng token vào HTML, một cấu hình đơn giản cho trường hợp cần token raw cả ở endpoint JSON lẫn header là:

~~~java
// Biến thể riêng: thay handler SPA của phần 3 khi dùng raw token JSON.
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
)
~~~

Nếu ứng dụng đồng thời render token trong HTML cần cơ chế masking, nên tách cách cấp token/định dạng hoặc xây dựng request handler hỗ trợ cả hai theo phiên bản Spring Security và kiểm thử BREACH. Không áp dụng hai cấu hình cùng lúc.

### 7.2. Fetch khác origin cần credentials và CORS

~~~javascript
const API = "https://api.example.com";

const bootstrap = await fetch(API + "/api/csrf", {
  credentials: "include",
  cache: "no-store"
});
if (!bootstrap.ok) throw new Error("Cannot bootstrap CSRF");
const { headerName, token } = await bootstrap.json();

const response = await fetch(API + "/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    [headerName]: token
  },
  body: JSON.stringify({ sku: "P100", quantity: 1 })
});
~~~

Servlet CORS cấu hình cho origin SPA cụ thể:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.com"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    config.setAllowedHeaders(List.of(
        "Content-Type", "X-XSRF-TOKEN", "X-CSRF-TOKEN"));
    config.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);
    return source;
}
~~~

Kết nối cấu hình CORS với HttpSecurity qua **.cors(Customizer.withDefaults())**. Browser phải gửi cookie trong cả GET bootstrap và POST bằng **credentials: "include"**, đồng thời cookie phải phù hợp SameSite, Secure, Domain, Path và chính sách chặn third-party cookies.

Không phản chiếu mọi **Origin** rồi bật **Access-Control-Allow-Credentials**. Nếu SPA và API **khác site** thực sự, có thể cần **SameSite=None; Secure**, nhưng việc browser cho phép third-party cookie vẫn không được bảo đảm. Cân nhắc BFF/cùng site thay vì mở rộng phạm vi cookie không kiểm soát.

### 7.3. So sánh cookie-header và JSON-header

| Tiêu chí | Đọc XSRF cookie trực tiếp | Lấy token qua JSON |
| --- | --- | --- |
| SPA và API cùng host | Phù hợp | Phù hợp |
| SPA và API khác subdomain, cookie host-only | Không đọc được từ origin SPA | Có thể dùng nếu CORS tin cậy |
| Token gửi trong header | Raw cookie token | Giá trị JSON do server cấp, raw/masked tùy handler |
| Bootstrap | GET tạo XSRF cookie hoặc filter buộc token load | GET trả token JSON |
| CORS | Khi khác origin vẫn cần CORS cho POST | CORS cả GET cấp token và POST |
| Rủi ro cần kiểm soát | Cookie injection, XSS, scope cookie | Token lộ qua cache/log/Origin mở, định dạng handler |
| Cookie xác thực | Vẫn cần cookie/session đúng | Vẫn cần cookie/session đúng |

## 8. Spring Security WebFlux/Reactive

WebFlux sử dụng **SecurityWebFilterChain**, **ServerHttpSecurity** và **CsrfWebFilter**, cùng khái niệm token repository và request handler riêng của Reactive.

Với SPA cùng origin muốn đọc **XSRF-TOKEN** cookie raw, có thể cấu hình **CookieServerCsrfTokenRepository** và handler nhận raw token thay cho XOR mặc định, với cùng lưu ý về masking nếu render HTML:

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

Trong WebFlux, endpoint bootstrap có thể lấy **Mono<CsrfToken>** từ request attribute và subscribe khi trả response:

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
                new IllegalStateException("Reactive CSRF filter is missing"));
        }

        return csrfMono.map(token -> {
            token.getToken(); // Buộc materialize để cookie có thể được ghi.
            return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
        });
    }
}
~~~

Không gọi **block()** trong WebFlux controller. Với repository Reactive mặc định dùng WebSession, chiến lược cấp token khác so với cookie repository; mã trên minh họa **chính xác phương án CookieServerCsrfTokenRepository**.

Nếu SPA khác origin cần CORS, dùng **CorsWebFilter** hoặc cấu hình CORS Reactive qua các class thuộc package **org.springframework.web.cors.reactive**, tránh dùng nhầm class Servlet. Khi phiên bản Spring Security dùng **XorServerCsrfTokenRequestAttributeHandler** mặc định, token raw từ cookie và định dạng masked ở response/request cần được xử lý nhất quán, tương tự Servlet.

### 8.1. Không nhầm WebSession với CSRF cookie

Cookie **XSRF-TOKEN** ở cấu hình trên không phải cookie **SESSION** hay thông tin xác thực. Có thể có WebSession hoặc JWT cookie để đăng nhập, trong khi token CSRF được lưu ở cookie riêng. Xác thực, kiểm tra CSRF và phân quyền là các bước độc lập.

## 9. Kiểm thử Servlet: cookie và header phải khớp

Bài kiểm thử tốt cần xác nhận: browser có thể nhận cookie XSRF, request không có header bị chặn, header sai bị chặn, header đúng đi qua CSRF filter và vẫn phải đáp ứng xác thực/phân quyền.

Ví dụ **MockMvc** sau giả định đã cấu hình Servlet ở phần 3, có handler **POST /api/orders** trả 2xx khi dữ liệu hợp lệ, cùng dependency **spring-security-test**.

~~~java
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
class XsrfCookieHeaderTests {

    @Autowired MockMvc mvc;

    @Test
    void cookieWithoutHeaderFailsButMatchingHeaderPasses() throws Exception {
        MvcResult boot = mvc.perform(get("/api/csrf"))
            .andExpect(status().isNoContent())
            .andReturn();

        Cookie xsrf = boot.getResponse().getCookie("XSRF-TOKEN");
        assertNotNull(xsrf, "Bootstrap should set XSRF-TOKEN cookie");

        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .cookie(xsrf)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", "invalid-token")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", xsrf.getValue())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Chú ý về kiểm thử:** Với bài thực tế, nên kiểm tra **dữ liệu không thay đổi** ở hai request bị chặn. Helper **user("alice")** mô phỏng principal đã đăng nhập, **không** thay thế test login/session cookie thật.

Nếu token không nằm trong response Set-Cookie vì repository đã có token hoặc môi trường MockMvc xử lý response khác, phải giữ cookie jar như browser và kiểm tra header/cookie từ toàn bộ luồng. Không giả định **GET /api/csrf luôn phát lại Set-Cookie** trong mọi request.

### 9.1. Test WebFlux

Có thể dùng **WebTestClient** với **spring-security-test** để kiểm tra hành vi lọc cơ bản:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

// webTestClient gắn Spring Security và có POST /api/orders handler.
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

Đây là đoạn thân test, cần khai báo **WebTestClient**, **java.util.Map** và handler. **csrf()** mô phỏng token ở tầng security test; một integration test cần GET bootstrap thật, lấy cookie **XSRF-TOKEN**, POST với cookie và header raw tương ứng để kiểm tra request handler Reactive đã cấu hình.

### 9.2. Ma trận kiểm thử hành vi

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| SPA mở lần đầu, GET /api/csrf | Cookie XSRF được tạo khi repository cần và JS cùng origin đọc được |
| POST có cookie xác thực, cookie XSRF nhưng thiếu header | Bị từ chối, thường 403; dữ liệu không đổi |
| POST có cookie XSRF nhưng header sai | Bị từ chối và dữ liệu không đổi |
| POST có raw token đúng trong header | Vượt kiểm tra CSRF; vẫn phải có quyền và input hợp lệ |
| POST có header đúng nhưng cookie XSRF không có | Bị từ chối theo repository đã cấu hình |
| Token hợp lệ nhưng không đăng nhập/không đủ quyền | Bị từ chối do authentication/authorization |
| Token cũ sau login/logout/session rotation | Không được giả định hợp lệ; SPA lấy lại token khi cần |
| SPA khác subdomain đọc cookie API host-only | document.cookie không đọc được; cần JSON token hoặc kiến trúc khác |
| Preflight từ origin không được phép | Browser chặn request cần preflight, nhưng backend vẫn phải có CSRF |
| Header X-XSRF-TOKEN bị proxy/gateway xóa | Request ghi có thể 403; kiểm tra request thực tế |
| Subdomain không tin cậy có thể đặt cookie trùng tên | Đánh giá cookie injection, host-only/signed token |
| XSS chạy cùng origin SPA | Có thể đọc XSRF cookie/gửi header; CSRF token không thay thế chống XSS |

## 10. Chẩn đoán xung đột phổ biến

### “Cookie XSRF-TOKEN có nhưng POST vẫn báo InvalidCsrfTokenException”

Kiểm tra **X-XSRF-TOKEN** có thật sự xuất hiện trong request hay không; giá trị token có khớp cookie không; request handler có đang mong **XOR-masked token** trong khi frontend gửi **raw token** không. Đây là lỗi thường gặp khi chuyển từ Spring Security cũ sang mặc định có masking. Kiểm tra các security chain có dùng cùng repository/handler không.

### “Ứng dụng chỉ gọi GET, sao chưa thấy XSRF-TOKEN?”

Deferred token có thể chưa được tạo. Triển khai **GET /api/csrf** và truy cập token, hoặc dùng handler SPA buộc token hiện thực hóa. Kiểm tra **Set-Cookie** ở Network và cookie scope trong Application/Storage.

### “Dùng withHttpOnlyFalse() có làm lộ session không?”

**Không trực tiếp.** Phương thức này chỉ làm cookie **XSRF-TOKEN** JavaScript-readable. Cookie xác thực **JSESSIONID** hoặc cookie JWT phải được cấu hình độc lập và vẫn nên **HttpOnly**. Cần lưu ý XSS có thể dùng token XSRF để thực hiện yêu cầu và phải phòng XSS riêng.

### “Angular/Axios đọc được cookie nhưng header không xuất hiện”

Kiểm tra cấu hình interceptor, phương thức request, URL là tương đối/same-origin hay cross-origin và điều kiện tự thêm header trong phiên bản client đang dùng. Dùng DevTools Network để xác minh chính request POST thật. Với URL cross-origin, client có thể cố ý không thêm header XSRF.

### “SPA ở app.example.com còn API ở api.example.com: document.cookie không có XSRF-TOKEN”

Đây có thể là hành vi đúng của cookie **host-only**. CORS không cho phép JavaScript đọc cookie thuộc host khác. Ưu tiên endpoint JSON trả token cho origin được tin cậy, kèm request handler thống nhất; tránh chia sẻ cookie với toàn bộ subdomain chỉ để tiện cho frontend.

### “OPTIONS preflight bị 401/403”

**X-XSRF-TOKEN** là custom header, nên request khác origin thường cần preflight. Cấu hình CORS trước lớp authentication và cho phép đúng origin, method, header. Không đòi cookie/token CSRF ở chính OPTIONS preflight; request thật vẫn phải kiểm tra CSRF.

### “Sau login/logout, POST đầu tiên lỗi 403”

CsrfAuthenticationStrategy hoặc CsrfLogoutHandler có thể xóa token cũ. SPA cần gọi bootstrap lại và đọc cookie mới, kiểm tra cookie có bị chặn bởi SameSite/Secure hay không. Không tự gửi lại nguyên POST không an toàn khi chưa biết nguyên nhân.

### “Header đúng nhưng server vẫn 403”

403 có thể là **access denied** do thiếu quyền, không phải CSRF. Kiểm tra authentication, roles/scopes, filter chain, request method và thông tin exception/log an toàn; không log nguyên token. Phân biệt **MissingCsrfTokenException**, **InvalidCsrfTokenException** và các lỗi phân quyền.

### “Có SameSite, CSP, HSTS và HTTP firewall, còn cần token?”

Mỗi lớp có mục tiêu riêng: SameSite hạn chế một số bối cảnh browser gửi cookie; **CSP** giảm nguy cơ XSS; **HSTS** giúp bảo vệ HTTPS; **HTTP firewall** loại bỏ request bất thường; **CORS** quản lý JavaScript khác origin. Chúng hỗ trợ phòng vệ tổng thể, nhưng không tự thay thế cơ chế kiểm tra ý định trong request đã xác thực bằng cookie.

## 11. Bài tập thực hành

**Bài 1 — Same-origin Servlet:** Bật CookieCsrfTokenRepository, tạo GET /api/csrf, viết fetch lấy cookie và gửi X-XSRF-TOKEN trên POST. Xác nhận ba trạng thái thiếu/sai/đúng token; không chỉ xem status mà phải kiểm tra dữ liệu.

**Bài 2 — Raw và XOR:** Dùng handler XOR mặc định với cookie raw và thử POST. Quan sát lỗi nếu xảy ra, sau đó áp dụng SpaCsrfTokenRequestHandler và xác minh request thành công. Giải thích vì sao masking trong HTML và raw cookie là hai đường xử lý khác nhau.

**Bài 3 — Login/logout:** Trước login khởi tạo XSRF cookie và gửi POST login với header. Sau login tải token mới, POST một thao tác ghi; logout rồi thử dùng token cũ để quan sát vòng đời.

**Bài 4 — React/Vue/Angular hoặc Axios:** Tạo interceptor chỉ thêm header cho endpoint ghi cùng origin. Thử gọi API bên thứ ba, xác nhận token không bị gửi nhầm; kiểm tra client có tự thêm header với absolute URL hay không.

**Bài 5 — Khác subdomain:** SPA ở app.example.com, API ở api.example.com với cookie host-only. Chứng minh JavaScript không đọc XSRF cookie của API, sau đó dùng endpoint JSON và CORS allowlist đúng để truyền token trong header.

**Bài 6 — Subdomain không tin cậy:** Kiểm tra Cookie Domain/Path và khả năng xuất hiện cookie trùng tên trong môi trường test. Đề xuất cookie host-only, kiểm soát subdomain và signed double-submit hoặc phương án tương đương cho hệ thống nhạy cảm.

## 12. Nguyên tắc cần nhớ

1. **Cookie XSRF** giúp frontend đọc token; **header do JavaScript thêm** là phần server cần kiểm tra. Chỉ có cookie XSRF tự gửi là chưa đủ.
2. **XSRF-TOKEN khác cookie đăng nhập**. Chỉ cookie CSRF cần HttpOnly=false trong mô hình này; cookie xác thực nên giữ HttpOnly.
3. **Spring Security 6 có cơ chế XOR/masking**: header raw đọc từ cookie cần request handler tương thích; không trộn masked token từ JSON với raw handler thiếu kiểm chứng.
4. **Deferred token** có thể chưa sinh trên GET thông thường; bootstrap rõ ràng và kiểm tra Set-Cookie giúp client khởi tạo chắc chắn.
5. **Origin, site, SameSite, CORS và Domain/Path** quyết định JS có đọc cookie được và browser có gửi credential hay không.
6. **Đổi phiên/login/logout cần đồng bộ token**. Không dùng mãi token cũ hoặc retry POST một cách tự động và thiếu kiểm soát.
7. **Double-submit cookie có giới hạn** trước cookie injection và XSS; dùng host-only, HTTPS/HSTS, CSP và token design phù hợp.
8. **Kiểm thử đầy đủ** từ bootstrap đến POST thiếu/sai/đúng token, xác thực, quyền, Servlet/Reactive, lỗi khác origin và tác động lên dữ liệu.

Khi xây dựng SPA dùng Spring Security, đường đi an toàn là **server cấp XSRF token → frontend đọc token trong phạm vi được phép → frontend gửi header ở thao tác ghi → server kiểm tra đúng repository và định dạng token**. Cấu hình cookie, request handler, CORS và vòng đời xác thực phải nhất quán thì luồng này mới hoạt động đúng và an toàn.
