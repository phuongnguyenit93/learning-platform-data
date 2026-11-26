# Xử lý token gốc trong cookie cùng token được che của request handler

## Mục tiêu bài học

Trong chương **CSRF cho SPA và API** của module **SPRING_SECURITY_HTTP_PROTECTION**, một tình huống rất dễ gây lỗi **403 Forbidden** là: frontend đọc đúng cookie **XSRF-TOKEN**, gửi nguyên giá trị đó qua **X-XSRF-TOKEN**, nhưng Spring Security lại xử lý request theo cơ chế **XOR-masked CSRF token**. Cookie và header có vẻ giống nhau, trong khi request handler lại kỳ vọng một biểu diễn khác.

Bài học này giải thích cách **token gốc (raw token)** được lưu trong cookie hoặc repository, cách **XorCsrfTokenRequestAttributeHandler** đưa token đã che (*masked token*) vào request attribute, vì sao Spring Security sử dụng masking để giảm nguy cơ **BREACH**, và cách thiết kế hợp đồng giữa frontend với backend trên cả **Servlet** và **Reactive (WebFlux)**. Ta cũng kiểm tra sự tương tác với session, cookie, CORS, CSP, HTTPS/HSTS, HTTP firewall và các kiểm thử tấn công web.

Sau bài học, bạn có thể:

- Phân biệt **giá trị CSRF token gốc trong repository** với **biểu diễn đã XOR-mask** dành cho HTML/request attribute.
- Giải thích vì sao token đã mask có thể **thay đổi giữa các response**, ngay cả khi cookie lưu token gốc không đổi.
- Biết lúc nào chọn **CsrfTokenRequestAttributeHandler**, **XorCsrfTokenRequestAttributeHandler**, hoặc một handler SPA kết hợp cả hai.
- Cấu hình **CookieCsrfTokenRepository.withHttpOnlyFalse()** để JavaScript đọc token gốc mà không bỏ masking cho các form render phía server.
- Tránh trộn nhầm luồng **token đọc từ cookie** với **token lấy qua JSON/HTML**, gây InvalidCsrfTokenException.
- Viết test chứng minh token raw trong header, token masked trong form và token sai được xử lý đúng.
- Đưa ra quyết định tương ứng cho **Spring Security WebFlux** và kiểm tra những sai khác theo phiên bản framework.

## 1. Vấn đề xuất hiện ở ranh giới repository và request handler

Khi bật CSRF, Spring Security thực hiện hai nhiệm vụ khác nhau:

1. **CsrfTokenRepository** nạp, tạo và lưu giá trị CSRF token được server chấp nhận; với cookie repository, token gốc thường nằm trong cookie **XSRF-TOKEN**.
2. **CsrfTokenRequestHandler** đặt CSRF token vào request attribute cho các thành phần render và **giải quyết giá trị token do client gửi**, từ header hoặc form parameter.

Hai thành phần này **không đồng nhất**. Một giá trị server dùng để lưu trữ có thể được trình bày bằng một chuỗi khác trong HTML.

Ví dụ sau là mô hình đơn giản khi SPA cùng origin dùng cookie:

~~~http
HTTP/1.1 204 No Content
Set-Cookie: XSRF-TOKEN=raw-token-A; Path=/; Secure; SameSite=Lax
~~~

Ở request ghi:

~~~http
POST /api/orders HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=session-1; XSRF-TOKEN=raw-token-A
X-XSRF-TOKEN: raw-token-A
Content-Type: application/json

{"sku":"P100","quantity":2}
~~~

**Cookie và header cùng mang token gốc** vì frontend đọc **XSRF-TOKEN** bằng JavaScript rồi thêm **X-XSRF-TOKEN**. Spring Security cần một request handler biết rằng **giá trị header này là raw token**, không phải masked token.

Trong khi đó, ở một trang HTML được render phía server, một thuộc tính như **_csrf.token** có thể mang **masked token** thay vì raw token. Form POST sẽ gửi chuỗi đã mask qua tham số **_csrf**, và request handler phải giải mã trước khi so khớp với repository.

### 1.1. Tại sao không chỉ so sánh hai chuỗi?

Hãy phân biệt ba vị trí dữ liệu:

| Vị trí | Giá trị điển hình | Ai tạo/đọc? |
| --- | --- | --- |
| **XSRF-TOKEN cookie** | Raw token | Repository phát, browser lưu, SPA có thể đọc nếu không có HttpOnly |
| **CSRF request attribute trong Servlet** | Masked token khi dùng XOR handler | Spring Security cung cấp cho controller/template |
| **X-XSRF-TOKEN header** | Raw **hoặc** masked, tùy hợp đồng đã chọn | Frontend chủ động gửi, handler đọc và diễn giải |
| **_csrf form parameter** | Thường masked nếu template lấy từ XOR request attribute | Form render phía server gửi |
| **CsrfTokenRepository** | Raw token cần đối chiếu | Bộ lọc CSRF dùng để xác minh |

**Một header có đúng tên không bảo đảm giá trị có đúng biểu diễn.** Hợp đồng frontend/backend phải nêu rõ header chứa raw hay masked token.

## 2. XOR masking là gì và nó giúp chống BREACH như thế nào?

### 2.1. Không phải hai khóa xác thực khác nhau

Giả sử raw token được biểu diễn bằng chuỗi **T**. Khi cung cấp token cho một response có thể được nén, Spring Security có thể sinh một **mask ngẫu nhiên M**, rồi biểu diễn một giá trị tương tự:

~~~text
Raw token trong repository:     T
Mask ngẫu nhiên cho response:   M
Biểu diễn truyền đi:           encode(M || (T XOR M))
~~~

Đây là mô hình khái niệm; định dạng byte, encoding và độ dài thực tế do framework quản lý. Khi client gửi masked token trở lại, handler giải mã, tách mask và khôi phục **T**, sau đó CSRF filter so khớp **T** với giá trị từ repository.

Điều quan trọng:

- **T vẫn là cùng token gốc** cho tới khi repository hoặc vòng đời xác thực thay đổi nó.
- **M có thể khác mỗi lần token được trình bày**, khiến chuỗi masked khác nhau dù T không đổi.
- XOR ở đây nhằm **randomize biểu diễn trên response**, không phải mã hóa bảo mật để thay thế HTTPS.
- Frontend **không cần và không nên tự thực hiện XOR**, giải mã Base64 hoặc cắt phần mask; hãy gửi đúng biểu diễn mà server đã cung cấp theo hợp đồng.

### 2.2. Nguy cơ BREACH và response compression

**BREACH** là nhóm tấn công side-channel lợi dụng độ dài response nén khi attacker có thể đưa nội dung có kiểm soát vào response chứa một bí mật ổn định. Nếu token CSRF cố định xuất hiện trong HTML có nén, thông tin về token có thể bị rò rỉ dần trong một số điều kiện tấn công.

Spring Security sử dụng **XorCsrfTokenRequestAttributeHandler** để làm cho biểu diễn token xuất hiện trong response khó giữ nguyên qua nhiều request. Điều đó **giảm rủi ro** ở một lớp, nhưng không thay thế:

- HTTPS và HSTS;
- phòng XSS, template output encoding và CSP;
- không đưa token vào log, URL, analytics hoặc cache dùng chung;
- hạn chế phản hồi chứa token tới origin không đáng tin cậy;
- lựa chọn cấu hình nén và kiến trúc response phù hợp.

**XOR masking không có nhiệm vụ ngăn JavaScript hợp lệ đọc raw token từ cookie trong mô hình SPA.** Đây là hai đường biểu diễn có mục tiêu khác nhau.

### 2.3. Hai GET, một raw token, hai masked token

Một trường hợp gây nhầm lẫn:

~~~text
Lần 1:
  XSRF-TOKEN cookie = T
  _csrf.token trong request attribute = masked(T, M1)

Lần 2:
  XSRF-TOKEN cookie = T
  _csrf.token trong request attribute = masked(T, M2)

Trong đó:
  masked(T, M1) != masked(T, M2) (thông thường)
  raw token trong cookie vẫn là T
~~~

Không kết luận phiên đã đổi hoặc CSRF bị lỗi chỉ vì masked token trong hai response không giống nhau. Ngược lại, không giả định raw token luôn cố định qua login/logout hoặc token rotation.

## 3. Hai hợp đồng frontend: cookie-raw và response-masked

Hệ thống nên chọn một hợp đồng nhất quán, tránh việc một số component gửi raw token còn component khác gửi masked token qua cùng header.

### 3.1. Hợp đồng A: SPA đọc raw token từ cookie

~~~mermaid
sequenceDiagram
    autonumber
    participant UI as JavaScript SPA
    participant B as Browser
    participant SS as Spring Security
    UI->>SS: GET /api/csrf
    SS->>B: Set-Cookie XSRF-TOKEN = raw T
    B-->>UI: document.cookie chứa raw T
    UI->>SS: POST /api/orders + X-XSRF-TOKEN = raw T
    SS->>SS: Handler plain đọc raw header
    SS->>SS: Repository cho raw T; đối chiếu
    SS-->>UI: Cho xử lý nếu xác thực, quyền và dữ liệu hợp lệ
~~~

Trong mô hình này:

- Cookie **XSRF-TOKEN** phải được JavaScript đọc được tại trang SPA (thông thường **HttpOnly=false**, Domain/Path phù hợp).
- Cookie phiên **JSESSIONID** hoặc cookie JWT xác thực nên giữ **HttpOnly=true**.
- Frontend gửi raw token qua header **X-XSRF-TOKEN**.
- Handler của server phải **đọc raw header**; nếu cùng ứng dụng còn HTML form lấy token đã mask, dùng handler kết hợp.

Đây là mô hình trung tâm của bài học.

### 3.2. Hợp đồng B: frontend nhận masked token từ response

Ví dụ server trả JSON:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "token": "masked-representation-from-handler"
}
~~~

Nếu endpoint lấy **CsrfToken** qua request attribute đang do **XorCsrfTokenRequestAttributeHandler** quản lý, trường **token** có thể là **masked token**. Khi đó frontend cần gửi đúng chuỗi được cấp, và backend phải dùng handler **giải mã masked token** trên header.

Hợp đồng B phù hợp với SPA lấy token qua JSON từ API khác origin hoặc ứng dụng server-side rendering; nó **khác** với “đọc raw token từ cookie”. CORS của endpoint JSON phải giới hạn đúng origin tin cậy và response không được cache chung.

**Cạm bẫy lớn:** Nếu dùng handler SPA “có header thì xử lý plain”, rồi lại lấy **masked token từ JSON** và gửi qua header, handler sẽ coi masked token là raw, khiến request **403**. Không thể chỉ thay nguồn token phía frontend mà giữ nguyên logic giải quyết header.

### 3.3. Bảng chọn hợp đồng

| Kiến trúc | Nguồn token của frontend | Định dạng gửi | Handler cần thiết |
| --- | --- | --- | --- |
| SPA cùng hostname, cookie XSRF JS-readable | **document.cookie** | Raw qua **X-XSRF-TOKEN** | Plain cho header raw; tùy chọn XOR cho form |
| SSR/Thymeleaf form | **_csrf.token** từ request attribute | Masked qua form parameter | XOR để unmask |
| SPA lấy token JSON từ XOR request attribute | Response JSON | Masked qua header phù hợp | XOR khi đọc header |
| SPA lấy token JSON raw theo handler plain | Response JSON | Raw qua header | Plain |
| SPA/BFF khác subdomain với cookie host-only | Response JSON qua CORS tin cậy | Raw hoặc masked theo API contract | Chọn handler đồng nhất với giá trị JSON |

Không trộn các dòng trong bảng bằng cách suy đoán token nhìn giống base64 hay có độ dài đặc biệt. Định dạng là chi tiết server phải định nghĩa rõ.

## 4. Servlet Spring Security 6: repository cookie + handler kết hợp

Bài học minh họa **Spring Boot 3, Spring Security 6, Java 17+** cho ứng dụng có SPA gọi API JSON cùng origin và có thể còn trang HTML/form phía server.

### 4.1. CookieCsrfTokenRepository giữ raw token

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
class SpaSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        CookieCsrfTokenRepository repository =
            CookieCsrfTokenRepository.withHttpOnlyFalse();

        // Cấu hình production HTTPS; API này có trong các bản 6.x hỗ trợ.
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

Giải thích:

1. **withHttpOnlyFalse()** chỉ thay chính sách đọc của **cookie CSRF XSRF-TOKEN**; không biến **JSESSIONID** thành JavaScript-readable.
2. **setCookieCustomizer** cho phép cấu hình thuộc tính CSRF cookie. Nếu dự án dùng bản Spring Security khác, kiểm tra API tương ứng trong phiên bản đã chọn.
3. **Secure=true** phù hợp HTTPS production. Môi trường chỉ dùng HTTP có thể không gửi cookie Secure; ưu tiên HTTPS ở local thay vì hạ bảo mật production.
4. **SameSite=Lax** giúp giảm một số bối cảnh cross-site nhưng không thay toàn bộ CSRF protection, đặc biệt khi subdomain kém tin cậy nằm cùng site.
5. **Path=/** giúp SPA trên những route cùng hostname đọc cookie; thu hẹp Path nếu kiến trúc cho phép và đã kiểm thử.
6. **formLogin** chỉ là ví dụ một luồng web dùng session cookie. Một ứng dụng thật có thể dùng OAuth/OIDC, JSON login hoặc BFF, nhưng vẫn phải bảo vệ các endpoint xác thực bằng cookie.
7. **SpaCsrfTokenRequestHandler** bên dưới quyết định trình bày token masked và nhận raw header.

### 4.2. Implement SpaCsrfTokenRequestHandler

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

    // Dùng để nhận raw token do JS đọc từ XSRF-TOKEN cookie.
    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    // Dùng để cung cấp/giải mã masked token trong HTML/form.
    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {

        // Request attribute giữ cách biểu diễn XOR để chống BREACH.
        this.xor.handle(request, response, csrfToken);

        // Buộc deferred token được nạp/tạo để cookie XSRF được cấp khi cần.
        csrfToken.get().getToken();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {

        String headerValue = request.getHeader(csrfToken.getHeaderName());

        // SPA đặt raw token trong header X-XSRF-TOKEN.
        // Nếu header không có, form parameter dùng đường XOR.
        return (StringUtils.hasText(headerValue) ? this.plain : this.xor)
            .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Cách đọc code:

- **handle** gọi **xor.handle(...)** để giá trị xuất hiện trong request attribute được mask đúng cách.
- **csrfToken.get().getToken()** làm deferred token được hiện thực hóa. Điều này có thể tạo cookie CSRF ngay trong các request được bảo vệ; nếu không muốn cookie được nạp sớm ở mọi request, chọn cơ chế bootstrap rõ ràng và điều chỉnh phù hợp.
- **resolveCsrfTokenValue** kiểm tra có header phù hợp hay không. Có header thì đường **plain** giải quyết **raw token**; không có header thì đường **xor** giải quyết masked token gửi dưới dạng tham số form.
- Spring Security tiếp tục so khớp giá trị raw đã giải quyết với token gốc trong repository.

**Ranh giới của mẫu:** Đây là hợp đồng **raw header + masked form parameter**. Nếu bạn gửi masked token qua header từ JSON, điều kiện “có header → plain” không còn phù hợp. Muốn hỗ trợ cả hai qua cùng header, phải thiết kế protocol riêng có phân biệt nguồn/kiểu biểu diễn rõ ràng và kiểm thử đầy đủ; không nên giải đoán bằng độ dài chuỗi.

### 4.3. Các endpoint bootstrap cho SPA đọc cookie

Một endpoint GET dùng để kích hoạt việc cấp token:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CookieCsrfBootstrapController {

    @GetMapping("/api/csrf")
    ResponseEntity<Void> csrf(CsrfToken csrfToken) {
        // Nếu token còn deferred, gọi getToken() để hiện thực hóa.
        csrfToken.getToken();

        return ResponseEntity.noContent()
            .cacheControl(CacheControl.noStore())
            .build();
    }
}
~~~

Trong trường hợp cookie mới, browser có thể nhận:

~~~http
HTTP/1.1 204 No Content
Cache-Control: no-store
Set-Cookie: XSRF-TOKEN=raw-T; Path=/; Secure; SameSite=Lax
~~~

Endpoint trả **204**, không đưa masked token vào JSON nên frontend buộc phải **đọc raw token từ cookie**, phù hợp handler kết hợp đã cấu hình. Nếu token cookie đã tồn tại, server không nhất thiết phát lại Set-Cookie ở mọi request.

**Lưu ý:** Token có thể chưa được sinh chỉ vì một request GET đi qua Spring Security. Deferred loading yêu cầu token được truy cập hoặc pipeline được subscribe tương ứng. Handler SPA ở phần 4.2 chủ động nạp token; endpoint GET này cũng tạo một điểm khởi tạo rõ ràng cho ứng dụng.

### 4.4. Biến thể JSON-only nhận raw token

Nếu ứng dụng **chỉ** có JSON API, không render masked token vào HTML và frontend muốn lấy raw token qua JSON thay vì cookie, có thể cân nhắc một handler plain đơn giản:

~~~java
// Thay riêng phần csrf(...) khi chọn hợp đồng JSON raw.
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new CsrfTokenRequestAttributeHandler())
)
~~~

Sau đó endpoint có thể trả CsrfToken từ request attribute qua JSON và frontend gửi đúng token đó qua header. Mẫu này **không dùng masking cho token xuất hiện trong response**; cần đánh giá rủi ro BREACH nếu response có nén và chứa token cùng nội dung attacker kiểm soát. Khi SPA không cần đọc cookie mà dùng JSON, cũng không bắt buộc giữ cookie CSRF JavaScript-readable; có thể chọn **HttpSessionCsrfTokenRepository** hoặc repository khác theo kiến trúc.

**Không kết hợp tùy tiện** handler JSON raw này với SpaCsrfTokenRequestHandler của phần 4.2 trong cùng chain.

## 5. Frontend: đọc đúng raw cookie, gửi đúng header

### 5.1. Đọc cookie bằng tên chính xác

~~~javascript
function readCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const item = document.cookie
    .split("; ")
    .find(cookie => cookie.startsWith(prefix));

  return item ? decodeURIComponent(item.slice(prefix.length)) : null;
}
~~~

Chỉ đọc **XSRF-TOKEN**:

~~~javascript
const rawXsrf = readCookie("XSRF-TOKEN");

if (!rawXsrf) {
  // Chưa được cấp, cookie bị chặn hoặc scope không phù hợp.
  throw new Error("XSRF cookie not available");
}

// Không đọc hoặc log JSESSIONID; cookie phiên nên có HttpOnly.
~~~

**HttpOnly=false** chỉ áp dụng cho CSRF cookie trong phương án này. Cookie xác thực vẫn nên **HttpOnly=true**, **Secure** và **SameSite** phù hợp.

### 5.2. Bootstrap tránh race giữa nhiều component

~~~javascript
let bootstrapPromise = null;

async function getRawCsrfToken() {
  const current = readCookie("XSRF-TOKEN");
  if (current) return current;

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

      const cookie = readCookie("XSRF-TOKEN");
      if (!cookie) {
        throw new Error("Missing or unreadable XSRF cookie");
      }

      return cookie;
    })().finally(() => {
      bootstrapPromise = null;
    });
  }

  return bootstrapPromise;
}
~~~

Nếu một SPA có nhiều component, dùng Promise chung giúp tránh gửi POST khi token chưa sẵn sàng. Cookie có thể đổi sau login/logout; không giữ token raw trong localStorage lâu dài để tiếp tục gửi lại mà không kiểm tra trạng thái hiện tại.

### 5.3. Gửi request POST với raw header

~~~javascript
async function createOrder(order) {
  const rawToken = await getRawCsrfToken();

  const response = await fetch("/api/orders", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": rawToken
    },
    body: JSON.stringify(order)
  });

  if (response.status === 403) {
    throw new Error(
      "Forbidden: CSRF mismatch or authorization failure");
  }
  if (!response.ok) {
    throw new Error("API failed: " + response.status);
  }

  return response.status === 204 ? null : response.json();
}
~~~

Client không cần biết mask **M**, không tự thực hiện XOR và không đọc token đã mask của HTML để thay vào header. **X-XSRF-TOKEN** chứa raw giá trị từ cookie đúng với hợp đồng handler kết hợp.

Có thể tạo HTTP interceptor chỉ thêm header cho **POST, PUT, PATCH, DELETE** đến backend được tin cậy. Không gửi token hoặc cookie tới URL tùy ý do người dùng cung cấp.

### 5.4. Angular và Axios có thể khác hành vi với URL

Nhiều HTTP client có hỗ trợ XSRF cookie/header tự động nhưng có điều kiện theo **same-origin, URL tương đối hoặc URL khác origin**. Hãy kiểm tra phiên bản đang dùng và xem DevTools **Network** trên chính request ghi:

- Có cookie **XSRF-TOKEN** không?
- Có header **X-XSRF-TOKEN** không?
- Giá trị header có phải raw cookie token không?
- Request có đi qua proxy/gateway loại bỏ header không?
- Nếu khác origin, preflight có cho phép header không?

**Đừng coi việc nhìn thấy cookie trên tab Application là bằng chứng header đã được gửi.** Hai thao tác này khác nhau.

## 6. Cùng lúc có SPA và form HTML render phía server

Một ứng dụng có thể phục vụ cả SPA JSON và trang SSR/Thymeleaf truyền thống:

~~~mermaid
flowchart TD
    R["Raw CSRF token T trong repository/cookie"] --> A["Cookie XSRF-TOKEN = T"]
    R --> B["XorCsrfTokenRequestAttributeHandler"]
    A --> C["JavaScript đọc cookie"]
    C --> D["X-XSRF-TOKEN = raw T"]
    B --> E["Request attribute: masked(T, M)"]
    E --> F["Form HTML: _csrf = masked(T, M)"]
    D --> G["SpaCsrfTokenRequestHandler: plain branch"]
    F --> H["SpaCsrfTokenRequestHandler: XOR branch"]
    G --> I["Khôi phục/đọc raw T"]
    H --> I
    I --> J["CSRF filter so khớp repository"]
~~~

Điểm mạnh của hybrid handler là giữ được hai tính chất đồng thời:

1. **SPA dễ tích hợp** với cookie raw header.
2. **Form HTML có masked token**, giảm rủi ro khi HTML response có nén và bí mật token xuất hiện lặp lại.

### 6.1. Form HTML cần dùng đúng giá trị masked

Ví dụ template engine đặt CSRF token từ request attribute vào một hidden input có tên **_csrf**. Khi form submit, parameter mang giá trị masked đã được Spring Security đưa vào template. Hybrid handler sẽ chọn XOR nếu không có header CSRF.

~~~http
POST /account/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...; XSRF-TOKEN=raw-T
Content-Type: application/x-www-form-urlencoded

_csrf=masked-value&emailAlerts=true
~~~

Nếu trong cùng request lại gửi **header X-XSRF-TOKEN** với giá trị khác, handler kết hợp sẽ **ưu tiên header plain**, không dùng form parameter. Vì vậy tránh để interceptor thêm một header XSRF không đồng bộ vào form submit hoặc request HTML.

### 6.2. Vì sao masked token có thể thay đổi còn cookie không đổi?

Handler XOR có thể sinh mask mới khi token được trình bày. Tương tự:

~~~text
GET /settings:
  Cookie:  XSRF-TOKEN = raw-T
  Form:    _csrf = mask(raw-T, random-1)

GET /settings lần nữa:
  Cookie:  XSRF-TOKEN = raw-T
  Form:    _csrf = mask(raw-T, random-2)
~~~

Không “chuẩn hóa” masked token bằng cách so sánh chuỗi form giữa các request. Đối chiếu cần diễn ra **sau khi handler giải quyết giá trị request về raw token**.

## 7. Reactive/WebFlux: quy tắc giống nhau, API khác Servlet

Trong Spring Security WebFlux, các lớp tương ứng là **SecurityWebFilterChain**, **ServerHttpSecurity**, **ServerCsrfTokenRepository** và **ServerCsrfTokenRequestHandler**. Với cookie repo, sử dụng **CookieServerCsrfTokenRepository**.

### 7.1. Cấu hình raw token cho API Reactive JSON-only

Ví dụ ứng dụng JSON-only, SPA cùng origin đọc cookie raw và gửi **X-XSRF-TOKEN**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;

@Bean
SecurityWebFilterChain reactiveApiSecurity(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf
            .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse())
            // Handler plain dùng cho raw token từ XSRF cookie.
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

Đây là **biến thể JSON-only nhận raw token**. Nếu cùng ứng dụng còn render HTML với token masked và request parameter, cần request handler Reactive kết hợp **XorServerCsrfTokenRequestAttributeHandler** cho đường masked cùng **ServerCsrfTokenRequestAttributeHandler** cho raw header, tương tự tư tưởng Servlet. **Không copy class Servlet hoặc chữ ký phương thức Servlet sang WebFlux**, vì Reactive API sử dụng **Mono**, **ServerWebExchange** và các interface riêng.

Cần đối chiếu API của phiên bản Spring Security đang sử dụng để thiết kế hybrid Reactive phù hợp; không giả định một đoạn mã Servlet đã có thể chạy nguyên xi trên WebFlux.

### 7.2. Deferred token trong WebFlux

WebFlux thường đưa **Mono<CsrfToken>** vào **ServerWebExchange**. Endpoint khởi tạo cần subscribe vào Mono để repository nạp/tạo token khi cần:

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
        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(
                new IllegalStateException("Reactive CSRF is not configured"));
        }

        return tokenMono.map(csrf -> {
            csrf.getToken();
            return ResponseEntity.noContent()
                .cacheControl(CacheControl.noStore())
                .build();
        });
    }
}
~~~

**Không gọi block()** trong Reactive controller. Với CookieServerCsrfTokenRepository, hãy xem cookie **XSRF-TOKEN** được tạo khi Mono thực sự chạy, không chỉ khi cấu hình repository.

### 7.3. Những điều cần phân biệt với Servlet

| Nội dung | Servlet | WebFlux |
| --- | --- | --- |
| Security chain | SecurityFilterChain | SecurityWebFilterChain |
| CSRF repository cho cookie | CookieCsrfTokenRepository | CookieServerCsrfTokenRepository |
| Raw handler | CsrfTokenRequestAttributeHandler | ServerCsrfTokenRequestAttributeHandler |
| XOR handler | XorCsrfTokenRequestAttributeHandler | XorServerCsrfTokenRequestAttributeHandler |
| Request context | HttpServletRequest | ServerWebExchange |
| Deferred value | Supplier<CsrfToken> trong luồng filter | Mono<CsrfToken> |
| Bootstrap | Controller truy cập getToken() | Subscribe Mono rồi truy cập getToken() |
| Kiểm thử | MockMvc, spring-security-test | WebTestClient, spring-security-test |

**Kiểm tra phiên bản framework** trước khi tùy biến handler và các tùy chọn cookie; mục tiêu là hiểu đường dữ liệu, không phải biến một class tuỳ chỉnh thành API ổn định mãi mãi.

## 8. CORS và cookie khi SPA khác origin

Giả sử:

- SPA: **https://app.example.com**.
- API: **https://api.example.com**.

Hai địa chỉ **khác origin** dù có thể **cùng site**. Nếu API phát cookie XSRF host-only cho **api.example.com**, JavaScript tại **app.example.com** **không đọc được cookie này** qua **document.cookie**.

Một lựa chọn an toàn và rõ ràng hơn là:

1. API cấp CSRF token trong **GET /api/csrf JSON** cho đúng origin SPA đáng tin cậy.
2. Frontend gọi GET với **credentials: "include"** nếu API dùng cookie xác thực.
3. Server cho phép CORS đúng origin, method, header và credentials; không cho wildcard origin.
4. Frontend gửi token JSON qua header trong POST.
5. **Backend dùng request handler hiểu đúng định dạng token JSON**: nếu token JSON masked, phải dùng handler XOR để giải mã header; nếu token JSON raw, dùng handler plain tương ứng.

Nếu chọn hợp đồng JSON-masked, đừng sử dụng **SpaCsrfTokenRequestHandler** của phần 4 mà mặc định header là raw.

### 8.1. CORS ví dụ cho Servlet

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE"));
    cors.setAllowedHeaders(List.of(
        "Content-Type", "X-XSRF-TOKEN", "X-CSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Trong **HttpSecurity** bổ sung **.cors(Customizer.withDefaults())** để preflight được xử lý phù hợp trước xác thực. WebFlux cần cấu hình CORS **Reactive**, không dùng nhầm UrlBasedCorsConfigurationSource thuộc Servlet.

**Không mở rộng Domain XSRF cookie sang tất cả subdomain chỉ để JavaScript đọc được** nếu có thể dùng JSON endpoint hoặc BFF cùng origin. Domain rộng tăng rủi ro cookie injection và không tự giải quyết CORS, SameSite, third-party cookie policy.

### 8.2. Cookie policy không thay handler mismatch

Các thuộc tính:

- **HttpOnly=false**: giúp JavaScript đọc XSRF cookie.
- **Secure=true**: giới hạn gửi cookie trên kết nối an toàn.
- **SameSite=Lax/Strict/None**: giới hạn hành vi gửi cookie theo ngữ cảnh site.
- **Domain/Path**: giới hạn phạm vi cookie được gửi/đọc.

Chúng **không biến raw token thành XOR-masked token**. Nếu request bị 403 vì handler giải sai định dạng, thay đổi SameSite hoặc mở CORS không sửa đúng nguyên nhân. Phải kiểm tra header value và request handler đang chạy.

## 9. Security implications: masking không chữa XSS hay cookie injection

### 9.1. XSS có thể đọc raw XSRF cookie

Nếu kẻ tấn công chạy được script trong origin của SPA, JavaScript đó có thể đọc **XSRF-TOKEN** khi HttpOnly=false và chủ động gửi header đúng. Cookie phiên có HttpOnly vẫn được browser tự gửi với fetch hợp lệ.

Vì vậy:

- **Masking** giảm một dạng side-channel khi token được trình bày trong response nén; nó **không** ngăn script XSS đã chạy cùng origin.
- **HttpOnly** trên cookie phiên giảm việc đọc trực tiếp session ID, nhưng không ngăn script độc hại thực hiện thao tác qua fetch.
- **CSP**, output encoding, kiểm soát HTML/DOM và quản lý script bên thứ ba vẫn cần thiết.
- **HTTPS/HSTS** bảo vệ đường truyền; **HTTP firewall** xử lý một lớp input/request bất thường; chúng không thay CSRF token.

### 9.2. Cookie injection và double-submit

Nếu cookie XSRF có Domain rộng, một subdomain không đáng tin cậy có thể có cơ hội can thiệp cookie trong một số kiến trúc. Chỉ so sánh token trong cookie và header **không tự chứng minh** phòng vệ mạnh trước mọi dạng cookie injection.

Các cách giảm thiểu:

- Ưu tiên cookie **host-only** thay vì Domain chung cho subdomain không đáng tin.
- Cân nhắc tên cookie bắt đầu bằng **__Host-** khi đáp ứng điều kiện Secure, Path=/ và không có Domain, đồng bộ tên trong frontend/repository.
- Hạn chế quyền set-cookie của các thành phần/ngõ vào không đáng tin cậy.
- Với nghiệp vụ nhạy cảm, cân nhắc **signed double-submit token** được ràng buộc mật mã với ngữ cảnh xác thực, hoặc synchronizer token gắn với session nếu phù hợp.
- Có thể bổ sung kiểm tra **Origin/Referer** và **Fetch Metadata** theo chính sách rõ ràng.

**CookieCsrfTokenRepository không mặc định tạo signed double-submit token có HMAC ràng buộc với session.** XOR masking là một cơ chế hoàn toàn khác; đừng nhầm mask ngẫu nhiên với chữ ký xác thực.

## 10. Kiểm thử Servlet: raw header và masked form

Kiểm thử cần tách ba khía cạnh: cookie/repository cấp đúng token, request handler đọc đúng biểu diễn, và filter không cho phép dữ liệu thay đổi khi token không hợp lệ.

### 10.1. Test raw cookie trong header bằng MockMvc

Giả định sử dụng cấu hình cookie + hybrid handler ở phần 4, có controller **POST /api/orders** nhận JSON và trả 2xx với input hợp lệ, kèm dependency **spring-security-test**:

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
class RawXsrfHeaderTests {

    @Autowired MockMvc mvc;

    @Test
    void rawCookieValueInHeaderIsAccepted() throws Exception {
        MvcResult boot = mvc.perform(get("/api/csrf"))
            .andExpect(status().isNoContent())
            .andReturn();

        Cookie xsrf = boot.getResponse().getCookie("XSRF-TOKEN");
        assertNotNull(xsrf);

        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .cookie(xsrf)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .cookie(xsrf)
                .header("X-XSRF-TOKEN", "wrong")
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

**Giới hạn:** **user("alice")** mô phỏng principal để tập trung vào CsrfFilter; test này không thay thế login và session cookie thực tế. Nếu cookie XSRF đã tồn tại hoặc repository/response khác, GET có thể không phát lại Set-Cookie; khi đó cần giữ cookie jar của cùng client và lấy token từ vòng đời thực.

Để chứng minh hệ thống an toàn, nên bổ sung assertion rằng **đơn hàng không bị tạo** trong hai request bị chặn. Một status 403 không đủ nếu nghiệp vụ đã có side effect trước khi bị từ chối.

### 10.2. Test masked form parameter

Tạo một endpoint test/trang HTML được phép hiển thị giá trị **_csrf.token** từ request attribute do XOR handler cấp. Client (hoặc test) thực hiện:

~~~text
GET /form
  → nhận masked token trong hidden field
  → giữ XSRF-TOKEN cookie gốc

POST /form
  Cookie: XSRF-TOKEN=raw-T
  Content-Type: application/x-www-form-urlencoded

  _csrf=masked-token-from-GET&value=1
~~~

Nếu request không mang header **X-XSRF-TOKEN**, hybrid handler chọn **XOR branch** để giải quyết masked parameter, và request hợp lệ đi tiếp. Với parameter **raw-T** thay vì masked value, XOR handler có thể từ chối.

Hãy kiểm tra trường hợp **cố ý gắn thêm một header raw không khớp vào form POST**: handler sẽ chọn plain header và có thể từ chối dù parameter masked hợp lệ. Điều này chứng minh thứ tự ưu tiên header/parameter là một phần hợp đồng.

### 10.3. Test sự khác nhau giữa cookie và request attribute

Có thể ghi nhận bằng assertion **boolean/trạng thái**, không log bí mật:

- Raw token trong cookie không đổi qua hai lần GET bình thường khi repository vẫn giữ một giá trị.
- Masked token hiển thị trong HTML có thể khác nhau giữa hai lần do mask ngẫu nhiên.
- Cả hai masked token (khi còn hợp lệ) đều có thể được handler XOR khôi phục và so khớp cùng raw token.
- Sau login/logout, raw token có thể bị xóa hoặc thay; phải khởi tạo lại token cho phiên mới.

Không dùng việc so sánh chuỗi trực tiếp giữa cookie raw và request attribute masked để kết luận bug.

## 11. Kiểm thử Reactive và trình duyệt

### 11.1. WebTestClient

Với WebFlux và **spring-security-test**, có thể kiểm tra hành vi chung của CsrfWebFilter:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test; cần WebTestClient và handler /api/orders có thật.
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

**csrf()** mô phỏng token phù hợp ở tầng test, nhưng không chứng minh client đã đọc raw cookie hoặc handler Reactive xử lý raw/XOR chính xác. Cần thêm integration test:

1. **GET /api/csrf** với cùng client và cookie jar.
2. Lấy **XSRF-TOKEN** do API phát.
3. **POST /api/orders** kèm cookie và **X-XSRF-TOKEN** raw; xác minh thành công khi đủ quyền.
4. Gửi header sai/thiếu; xác minh bị chặn và dữ liệu không đổi.
5. Nếu ứng dụng có form masked, kiểm thử riêng khả năng giải mã parameter masked với request handler Reactive đã chọn.

### 11.2. Ma trận kiểm thử liên tầng

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| GET /api/csrf khi chưa có cookie XSRF | Token được hiện thực hóa và cookie được cấp khi cần |
| POST có XSRF cookie nhưng thiếu header | Bị chặn, thường 403 |
| POST có raw header sai | Bị chặn, dữ liệu không đổi |
| POST có raw header đúng, hybrid handler dùng plain | Vượt qua CSRF, vẫn chịu xác thực và phân quyền |
| Form POST có masked parameter và không có header | Hybrid handler dùng XOR, request hợp lệ được xử lý |
| Form gửi raw token vào parameter đòi XOR | Bị từ chối hoặc không khớp |
| JSON endpoint trả masked token, hybrid handler xử lý header plain | Bị từ chối: **hợp đồng frontend/server không khớp** |
| JSON endpoint trả masked token, XOR handler xử lý header | Vượt CSRF nếu token hợp lệ và cùng repository/phiên |
| Hai response HTML có masked token khác nhau | Có thể hoàn toàn bình thường do mask ngẫu nhiên |
| Sau login/logout/session rotation dùng token cũ | Không được giả định hợp lệ; bootstrap lại |
| SPA khác subdomain đọc cookie host-only API | JavaScript không đọc được qua document.cookie |
| Preflight CORS từ origin không được phép | Browser chặn request cần preflight; server vẫn phải bảo vệ CSRF |
| Script XSS trong origin SPA | Có thể đọc cookie XSRF và gửi header; CSRF không thay thế chống XSS |

### 11.3. Những gì nên xem trong DevTools

Với ứng dụng chạy trong môi trường được phép kiểm thử:

1. **Application/Storage → Cookies:** xác định XSRF-TOKEN có tồn tại, HttpOnly có tắt riêng cho cookie này, JSESSIONID vẫn HttpOnly, Domain/Path/SameSite có đúng.
2. **Network → GET /api/csrf:** kiểm tra trạng thái 204 hoặc JSON, Set-Cookie khi token mới, Cache-Control no-store.
3. **Network → POST /api/orders:** nhìn xem header **X-XSRF-TOKEN** có được client thêm, cookie có được browser gửi và request có đi qua CORS preflight không.
4. **Backend security logs** ở chế độ kiểm thử có kiểm soát: phân biệt **MissingCsrfTokenException**, **InvalidCsrfTokenException**, AuthenticationException và AccessDeniedException, không log giá trị token.
5. **Test dữ liệu sau request:** xác minh đơn hàng/thiết lập không đổi khi request bị từ chối.

## 12. Chẩn đoán lỗi thường gặp

### “Cookie XSRF-TOKEN và header X-XSRF-TOKEN giống nhau mà vẫn 403”

Kiểm tra request handler. Nếu đang dùng **XorCsrfTokenRequestAttributeHandler** để giải quyết header, nó có thể mong token masked, trong khi frontend gửi raw token từ cookie. Chọn handler plain cho raw header hoặc SpaCsrfTokenRequestHandler phù hợp, rồi test request thật.

### “Token trong form HTML khác giá trị cookie, có phải bị giả mạo?”

Không nhất thiết. Form có thể chứa **masked token** được tính từ raw token và một mask ngẫu nhiên. XOR handler giải mã form trước khi so khớp repository; không đòi hai chuỗi biểu diễn bằng nhau.

### “Hai lần GET form làm token thay đổi liên tục”

Kiểm tra giá trị nào thay đổi: **masked representation** có thể thay dù raw cookie không đổi. Nếu raw cookie cũng bị xóa/tạo lại mỗi request, cần xem login/logout, filter, repository, Domain/Path, cookie bị browser chặn hoặc nhiều chain đang tạo token khác nhau.

### “GET /api/csrf thành công nhưng không thấy XSRF-TOKEN”

Có thể deferred token chưa được truy cập, repository không phải CookieCsrfTokenRepository, cookie bị chặn vì Secure/Domain/Path, hoặc endpoint qua một SecurityFilterChain khác. Xem Set-Cookie, handler có gọi token supplier hay không và chính sách cookie của browser.

### “SPA lấy token qua JSON rồi gửi header nhưng handler hybrid từ chối”

Kiểm tra token JSON có phải masked token từ XOR request attribute hay không. Handler hybrid ở đây **chọn plain khi có header**. Hãy nhất quán: dùng JSON raw + plain handler, hoặc JSON masked + XOR handler, hoặc phân tách protocol rõ ràng.

### “Angular/Axios gửi header ở localhost nhưng không gửi với URL production”

Nhiều HTTP client chỉ tự thêm XSRF header cho request cùng origin hoặc URL thỏa điều kiện. Kiểm tra hành vi phiên bản client, request URL có absolute/cross-origin không, interceptor và preflight; đừng mở rộng cookie Domain hoặc CORS quá mức để chữa sai cấu hình.

### “CSRF token đúng nhưng request vẫn 401/403”

CSRF token không cấp danh tính. Kiểm tra session/JWT cookie, authorization rules, scope, trạng thái đăng nhập và SecurityFilterChain được chọn. **403** có thể là thiếu quyền, không phải InvalidCsrfTokenException.

### “Có CSP/HSTS/SameSite/HTTP firewall, có thể bỏ CSRF không?”

Không suy luận như vậy. **CSP** giảm rủi ro XSS, **HSTS** tăng bảo vệ HTTPS, **SameSite** giới hạn một số hành vi gửi cookie, **HTTP firewall** chặn request bất thường, **CORS** điều khiển JavaScript khác origin. Chúng hỗ trợ nhưng không tự thay thế việc kiểm tra CSRF ở endpoint xác thực bằng cookie.

## 13. Bài tập thực hành

**Bài tập A — Nhận diện định dạng token.** Bật CookieCsrfTokenRepository và XOR request handler; mở trang form hai lần, so sánh dạng biểu diễn ở form với cookie (không in bí mật vào log). Giải thích vì sao masked token có thể thay đổi trong khi raw token giữ nguyên.

**Bài tập B — Reproduce 403.** Để handler XOR mặc định, frontend đọc raw XSRF cookie và gửi X-XSRF-TOKEN. Quan sát lỗi. Thay sang SpaCsrfTokenRequestHandler và chứng minh raw header được chấp nhận khi request hợp lệ.

**Bài tập C — Hai đường dùng chung chain.** Dùng SPA POST JSON với raw header và form HTML POST với masked parameter. Test cả hai nhánh trong handler; xác nhận thiếu/sai token vẫn bị chặn.

**Bài tập D — Đổi sang JSON token.** Thiết kế endpoint GET /api/csrf trả JSON, kiểm tra token trả về là raw hay masked trong cấu hình đã chọn. Chỉnh handler hoặc contract frontend để không trộn nhầm định dạng.

**Bài tập E — Session và login/logout.** Lấy token khi chưa đăng nhập, login, sau đó gửi POST dùng token cũ và token mới. Quan sát cookie CSRF và session để hiểu việc xóa token trong chiến lược xác thực.

**Bài tập F — Khác subdomain.** Đặt SPA tại app.example.com và API tại api.example.com; dùng cookie host-only. Chứng minh JavaScript không thể đọc cookie API, sau đó thiết kế endpoint JSON CORS allowlist với hợp đồng token nhất quán.

**Bài tập G — Reactive.** Triển khai raw cookie + ServerCsrfTokenRequestAttributeHandler và WebTestClient. Kiểm thử GET bootstrap, POST thiếu/sai/đúng token; so sánh với Servlet về repository và request handler tương ứng.

## 14. Nguyên tắc cần ghi nhớ

1. **Token gốc và token XOR-masked là hai biểu diễn của cùng một bí mật CSRF**, không phải hai quyền xác thực.
2. **CookieCsrfTokenRepository** lưu raw token; **XorCsrfTokenRequestAttributeHandler** có thể đưa masked token vào request attribute/HTML để giảm rủi ro BREACH.
3. **SPA đọc XSRF-TOKEN cookie thường gửi raw token qua X-XSRF-TOKEN**. Handler phải hiểu raw header này.
4. **Form HTML dùng token masked** phải được handler XOR giải mã trước khi so khớp repository.
5. **Hybrid SpaCsrfTokenRequestHandler** giữ đường XOR cho form và đường plain cho header raw; nó **không** tự chấp nhận masked token JSON gửi trong header.
6. **Deferred token** cần được hiện thực hóa khi khởi tạo SPA; một GET bình thường chưa chắc đã phát cookie.
7. **Servlet và Reactive dùng các class handler khác nhau** nhưng cùng nguyên tắc. Kiểm thử phiên bản cụ thể và đừng sao chép nguyên code giữa hai stack.
8. **CORS, SameSite, Domain/Path, HttpOnly và Secure** ảnh hưởng khả năng gửi/đọc cookie, nhưng không tự sửa lỗi định dạng raw/XOR.
9. **CSRF không thay chống XSS, token validation hoặc authorization.** XOR masking không phải HMAC và không tự giải quyết cookie injection.
10. **Kiểm thử cả đường dữ liệu và hậu quả thực tế:** cookie raw, header raw, parameter masked, 403 thiếu/sai token, login/logout, CORS và dữ liệu không bị sửa ngoài ý muốn.

Khi xử lý CSRF cho SPA trong Spring Security, hãy xác định rành mạch **giá trị lưu ở repository**, **giá trị hiển thị cho client**, **giá trị client gửi lại** và **request handler giải quyết giá trị đó như thế nào**. Chỉ khi bốn phần nhất quán, mô hình cookie raw và masked token mới vừa dễ tích hợp frontend vừa duy trì đúng lớp phòng vệ trình duyệt.
