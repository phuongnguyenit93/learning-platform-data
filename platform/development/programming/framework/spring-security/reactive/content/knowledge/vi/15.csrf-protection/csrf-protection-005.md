# CookieServerCsrfTokenRepository và gửi token từ ứng dụng JavaScript

## Mục tiêu học tập

Bài học thuộc nhóm **Bảo vệ CSRF** trong **Spring Security reactive / Spring WebFlux**. Sau khi học, bạn có thể:

- Giải thích CSRF xảy ra khi trình duyệt **tự gửi credential** (đặc biệt cookie phiên) cho một request thay đổi trạng thái, và vì sao HTTP Basic, session-cookie authentication hoặc một số cách lưu token trên trình duyệt có thể liên quan.
- Phân biệt `WebSessionServerCsrfTokenRepository` mặc định với `CookieServerCsrfTokenRepository`: nơi lưu token kỳ vọng, tên cookie, header và form parameter.
- Cấu hình `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` khi JavaScript cùng origin cần đọc cookie `XSRF-TOKEN` để gửi lại token qua header `X-XSRF-TOKEN`.
- Hiểu một điểm rất dễ sai ở Spring Security 6.x: request handler mặc định **XOR-masking/BREACH** có thể không hiểu token **raw** mà JS lấy từ cookie; có thể tùy biến cách xử lý header raw trong khi vẫn giữ masked token cho HTML form.
- Khởi tạo hoặc làm mới cookie token qua endpoint **GET /csrf** bằng cách subscribe vào `Mono<CsrfToken>` do WebFlux cung cấp, nhất là sau khi login/logout.
- Viết ví dụ **Java 17 + Spring Boot + WebFlux** và JavaScript `fetch` same-origin cho POST JSON, kèm kiểm thử 403 khi thiếu/sai token và 200 khi gửi đúng.
- Chọn chính sách `HttpOnly`, `Secure`, `SameSite`, `Path` và CORS hợp lý; không coi CSRF token là thay thế cho Authentication/Authorization hoặc biện pháp chống XSS.

> **Phạm vi:** Spring Security **reactive**. Trong WebFlux dùng `CookieServerCsrfTokenRepository` và `ServerHttpSecurity`, không phải `CookieCsrfTokenRepository`/`HttpSecurity` của Servlet MVC. Một cấu hình cookie tương tự về ý tưởng chưa chắc dùng cùng class, cùng response handler hoặc cùng flow trong hai stack.

## 1. CSRF là gì, và JavaScript liên quan thế nào?

**Cross-Site Request Forgery (CSRF)** là tình huống một website/trang độc hại làm browser của nạn nhân gửi yêu cầu tới một ứng dụng mà nạn nhân đã đăng nhập. Nếu browser **tự đính kèm cookie phiên** cho request, server có thể nhầm hành động ấy là ý định thực sự của người dùng.

Ví dụ:

~~~text
Người dùng đã đăng nhập tại https://shop.example.test
    |
    +-- Browser giữ cookie SESSION=...
    |
    v
Người dùng ghé một website không đáng tin
    |
    v
Website đó tìm cách tạo POST /api/orders/cancel
    |
    +-- Browser có thể tự gửi session cookie
    |
    v
Nếu server chỉ tin cookie -> có nguy cơ thay đổi dữ liệu trái ý muốn
~~~

**CSRF token** tạo thêm yêu cầu: request thay đổi trạng thái phải chứa một token khó đoán ở **nơi không được browser tự thêm** (ví dụ một custom header do JavaScript chủ động đặt, hoặc hidden field của form do ứng dụng hợp lệ render). Server kiểm tra token gửi lại so với token kỳ vọng.

Một ứng dụng JavaScript thường gửi JSON bằng `fetch`:

~~~javascript
await fetch("/api/orders", {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ itemId: 42 })
});
~~~

Đoạn trên **chưa gửi CSRF token**. Nếu server có CSRF protection và dựa vào cookie, request POST có thể bị **403 Forbidden**, kể cả khi session vẫn hợp lệ. Chính nội dung bài này là cấu hình nơi lưu token và thêm header một cách đúng đắn.

### 1.1. Các phương thức nào cần CSRF?

Spring Security WebFlux mặc định áp dụng CSRF cho các request có phương thức **không an toàn**; `GET`, `HEAD`, `OPTIONS` và `TRACE` thường được xem là safe methods. `POST`, `PUT`, `PATCH` và `DELETE` thường phải có CSRF token hợp lệ khi filter được bật.

- `GET /csrf`: đọc/khởi tạo token để client sử dụng; không nên thay đổi dữ liệu nghiệp vụ.
- `GET /api/me`: đọc danh tính, thường không yêu cầu header CSRF.
- `POST /api/notes`: thao tác thay đổi trạng thái, thường yêu cầu token.
- `POST /login` và `POST /logout`: trong ứng dụng cookie/session cũng cần bảo vệ CSRF; login CSRF và logout CSRF là những vấn đề thực sự.
- Nếu một endpoint **GET** lại chuyển tiền/xóa dữ liệu, đó là lỗi thiết kế HTTP; CSRF matcher mặc định thường **không bảo vệ** GET. Hãy sửa method, không dựa vào việc “ẩn nút bấm”.

**CSRF không thay thế Authentication.** Có token hợp lệ không chứng minh user có quyền gọi API; việc kiểm tra session/password/token và authorization vẫn phải được duy trì độc lập.

## 2. CookieServerCsrfTokenRepository lưu cái gì?

`CookieServerCsrfTokenRepository` là một `ServerCsrfTokenRepository` dành cho WebFlux, lưu **token kỳ vọng** trong một cookie, thay vì lưu trong `WebSession` như repository mặc định. Nó phù hợp khi giao diện JavaScript cùng origin cần truy cập token từ `document.cookie`.

Theo mặc định của repository:

| Thành phần | Tên mặc định | Được dùng như thế nào? |
|---|---|---|
| Cookie lưu token kỳ vọng | `XSRF-TOKEN` | Server gửi bằng `Set-Cookie` và đọc lại ở request sau. |
| Header chứa token do JavaScript gửi | `X-XSRF-TOKEN` | Client chủ động đọc giá trị từ cookie rồi **copy vào header** trên request unsafe. |
| Form parameter | `_csrf` | Form HTML có thể gửi token trong form field; với JSON thường dùng header. |
| Session cookie | Thường `SESSION`, tùy cấu hình | Dùng cho đăng nhập; **khác** cookie CSRF. |
| Bean/repository | `ServerCsrfTokenRepository` | Tạo, lưu và load CSRF token; không phải Authentication repository. |

Không nhầm `XSRF-TOKEN` với `SESSION`: cookie thứ nhất chứa token chống CSRF, cookie thứ hai thường là ID phiên đăng nhập. Một website hoàn toàn có thể có CSRF token trước khi user login.

### 2.1. Cookie được gửi tự động, nhưng header thì không

Browser **tự gửi cookie** theo các quy tắc cookie (origin/domain/path/SameSite/Secure). Còn header tùy biến `X-XSRF-TOKEN` phải do ứng dụng JavaScript hoặc một client tự thêm.

~~~text
Browser có cookie:
  SESSION=<session-id>
  XSRF-TOKEN=<raw-csrf-token>

JavaScript:
  token = đọc XSRF-TOKEN qua document.cookie
  fetch("/api/notes", {
    method: "POST",
    headers: { "X-XSRF-TOKEN": token },
    credentials: "same-origin"
  })

Browser thực sự gửi:
  Cookie: SESSION=...; XSRF-TOKEN=...
  X-XSRF-TOKEN: <raw-csrf-token>

Server:
  CookieServerCsrfTokenRepository.loadToken(exchange)
  + ServerCsrfTokenRequestHandler đọc token từ request
  + CsrfWebFilter so sánh
  -> cho đi tiếp hoặc 403
~~~

**Đừng nói “chỉ cần đặt cookie XSRF-TOKEN là đã có CSRF protection”.** Attacker có thể khiến browser tự gửi cookie (vì cookie tự động đính kèm). Điều tạo khác biệt ở mô hình JavaScript là token phải được gửi thêm ở một **custom header**; cross-origin site thông thường không thể tự tùy ý đặt header đó và đọc token của origin nạn nhân nếu browser/SOP/CORS được cấu hình đúng.

### 2.2. withHttpOnlyFalse() làm gì?

~~~java
CookieServerCsrfTokenRepository repository =
    CookieServerCsrfTokenRepository.withHttpOnlyFalse();
~~~

Factory method đặt cookie **`HttpOnly=false`**, cho phép JavaScript cùng origin truy cập nó qua `document.cookie`. Điều này cần thiết **nếu client trực tiếp đọc cookie**. Nếu ứng dụng **không cần JS đọc cookie**, nên dùng:

~~~java
CookieServerCsrfTokenRepository repository =
    new CookieServerCsrfTokenRepository();
~~~

Cấu hình này giữ `HttpOnly` theo mặc định an toàn hơn cho cookie CSRF, và có thể truyền token tới form/meta tag qua server-rendered view.

**Ranh giới bảo mật:** CSRF token **không phải mật khẩu đăng nhập**; tuy nhiên làm cookie đọc được bằng JS mở rộng phạm vi rủi ro trước **XSS**. Nếu attacker chạy script trong chính origin, họ thường có thể gửi request được chấp nhận dù có CSRF token. Vì vậy phải giữ biện pháp chống XSS (encode output, CSP, dependencies an toàn, hạn chế script không tin cậy) và giữ session cookie **HttpOnly**.

## 3. Cấu hình cơ bản trên Spring Security WebFlux

Theo tài liệu chính thức WebFlux:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf.csrfTokenRepository(
            CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .build();
}
~~~

Đây là **mảnh cấu hình** trong một class Spring có import `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `CookieServerCsrfTokenRepository`. Nó cho thấy cách thay default `WebSessionServerCsrfTokenRepository` bằng repository dùng cookie.

**Nhưng cấu hình này chưa đủ để khẳng định mọi bản Spring Security 6.x sẽ chấp nhận header chứa token raw từ `document.cookie`.** Vấn đề nằm ở lớp request handler và kỹ thuật che token BREACH; mục tiếp theo xử lý rõ ràng.

### 3.1. Cấu hình tùy biến cookie

Trong Spring Security 6.1+, repository có `setCookieCustomizer(...)` để chỉnh cookie attributes:

~~~java
CookieServerCsrfTokenRepository repository =
    CookieServerCsrfTokenRepository.withHttpOnlyFalse();

repository.setCookieCustomizer(cookie -> cookie
    .path("/")
    .sameSite("Lax"));
~~~

Đây là **mảnh code** cần đặt trước khi truyền repository vào `csrfTokenRepository(...)`. `path("/")` đảm bảo JavaScript ở các đường dẫn cùng host có thể nhìn thấy cookie; `SameSite=Lax` là lựa chọn phù hợp với demo same-origin. Trong production HTTPS, cân nhắc đặt thêm `.secure(true)`; nếu dùng `SameSite=None` thì phải có `Secure` trên browser hiện đại.

Không tự đặt `Domain=.example.com` để chia sẻ cookie CSRF cho mọi subdomain chỉ vì tiện, vì subdomain không đáng tin có thể tăng nguy cơ **cookie injection**. Cookie có `Path`, `Domain`, `Secure` và `SameSite` phải được thiết kế theo kiến trúc domain, proxy và TLS thực tế.

## 4. Điểm khó ở Spring Security 6: XOR-masked token và token raw từ cookie

Spring Security WebFlux từ 6.0 mặc định dùng `XorServerCsrfTokenRequestAttributeHandler`. Nó có khả năng **mask** giá trị token đưa ra view để giảm rủi ro **BREACH** (tấn công suy đoán secret trong response nén). Nó cũng có thể giải mã token masked khi client gửi trở lại qua form field/header.

Trong khi đó `CookieServerCsrfTokenRepository` lưu **raw token** trong cookie `XSRF-TOKEN`, và JavaScript chỉ đọc được raw value. Vì vậy có tình huống:

~~~text
Expected token trong cookie:       T (raw)
View nhận token từ XOR handler:    M(T, random) (masked)
HTML form gửi masked token:        M(T, random)
JS document.cookie lấy được:       T (raw)
JS X-XSRF-TOKEN gửi:               T (raw)

XOR resolver được viết để giải masked token.
Nếu đưa T raw cho XOR resolver, validation có thể FAIL (403).
~~~

Vì vậy **không nên chỉ đặt `withHttpOnlyFalse()` rồi kết luận ứng dụng JavaScript luôn hoạt động**. Có hai hướng triển khai:

1. **Đơn giản cho một API JavaScript chỉ dùng header raw:** dùng `new ServerCsrfTokenRequestAttributeHandler()` để xử lý token raw. Tài liệu Spring Security nêu rõ đây là cách tắt XOR/BREACH masking; nó có trade-off bảo mật nếu còn đưa cùng token raw vào response HTML.
2. **Cân bằng hơn cho SPA kết hợp form:** giữ XOR để tạo token masked cho view/form; riêng khi request có header `X-XSRF-TOKEN`, dùng plain handler để resolve **raw header**. Đây là cách được dùng trong ví dụ chính của bài: cho phép JS đọc raw cookie và vẫn giữ đường form masked.

### 4.1. Tùy chọn đơn giản: chỉ nhận raw token

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(
        new ServerCsrfTokenRequestAttributeHandler()))
~~~

Đây là mảnh DSL WebFlux cần import `org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler`. Khi dùng cách này, server không áp dụng XOR masking theo mặc định. Không áp dụng mà không hiểu khi ứng dụng có HTML render token, vì BREACH protection được thiết kế để tránh phản chiếu cùng một secret raw vào response có thể nén.

### 4.2. Tùy chọn kết hợp: raw header + masked form

Có thể cung cấp `ServerCsrfTokenRequestHandler` riêng:

~~~java
ServerCsrfTokenRequestHandler handler =
    new ServerCsrfTokenRequestHandler() {
        private final XorServerCsrfTokenRequestAttributeHandler xor =
            new XorServerCsrfTokenRequestAttributeHandler();
        private final ServerCsrfTokenRequestAttributeHandler plain =
            new ServerCsrfTokenRequestAttributeHandler();

        @Override
        public void handle(
            ServerWebExchange exchange, Mono<CsrfToken> token) {

            xor.handle(exchange, token);
        }

        @Override
        public Mono<String> resolveCsrfTokenValue(
            ServerWebExchange exchange, CsrfToken token) {

            boolean rawHeaderPresent = exchange.getRequest()
                .getHeaders().containsKey(token.getHeaderName());

            return rawHeaderPresent
                ? plain.resolveCsrfTokenValue(exchange, token)
                : xor.resolveCsrfTokenValue(exchange, token);
        }
    };
~~~

Đây là **mảnh code bên trong method cấu hình**; đủ logic để ghép vào Java class ở phần thực hành. Nó thể hiện chính xác hai việc độc lập của request handler:

- `handle(...)` dùng XOR để **expose token cho view** với protection chống BREACH.
- `resolveCsrfTokenValue(...)` đọc **header raw** khi client JavaScript chủ động đặt `X-XSRF-TOKEN`; nếu không có header, xử lý **form value masked** bằng XOR.
- Không tự viết thuật toán kiểm tra `equals` token; `CsrfWebFilter` vẫn so sánh token kỳ vọng với token đã được resolver lấy ra.

**Điều kiện rõ ràng:** Nếu bạn gửi một masked token trong header `X-XSRF-TOKEN` với handler này, nó sẽ được xử lý như raw và có thể bị từ chối. Client JS ở bài này luôn gửi raw cookie value; form dùng masked field. Khi có nhiều client với conventions khác nhau, phải thiết kế matcher/handler hoặc quy ước riêng và viết test.

### 4.3. Vì sao không tự gửi cookie làm header ở gateway?

Nếu reverse proxy tự tạo `X-XSRF-TOKEN` bằng cách copy cookie cho mọi request, kể cả request từ site khác, bạn đã loại bỏ yêu cầu client **chủ động** trình token. Mô hình bảo vệ CSRF của double-submit phụ thuộc vào việc untrusted site không thể cung cấp một header hợp lệ (và không thể đọc token). Đừng cấu hình hạ tầng tự biến cookie thành header một cách mù quáng.

## 5. Deferred CSRF token: vì sao không thấy XSRF-TOKEN sau GET?

Spring Security có cơ chế **deferred token loading**: token được cung cấp dưới dạng `Mono<CsrfToken>` và có thể chỉ được tạo/lưu khi một subscriber thực sự dùng token. Vì vậy:

- Một GET public bất kỳ **không chắc** làm response có `Set-Cookie: XSRF-TOKEN=...`.
- Đặt repository cookie mà không bao giờ consume `Mono<CsrfToken>` có thể khiến frontend không thấy cookie.
- Sau login hoặc logout, CSRF token cũ thường bị xóa/refresh; SPA phải lấy token mới trước request unsafe tiếp theo.

Trong WebFlux, `CsrfWebFilter` expose một exchange attribute tại key `CsrfToken.class.getName()`, có kiểu `Mono<CsrfToken>`. Một endpoint GET có thể subscribe vào Mono ấy để token được tạo và cookie được lưu:

~~~java
@GetMapping("/csrf")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
        exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(new IllegalStateException(
            "CSRF attribute unavailable"));
    }

    return token.then();
}
~~~

Đây là **mảnh method controller**; phần thực hành có class đầy đủ. `then()` subscribe vào token Mono trong pipeline, bỏ qua giá trị token trong body và trả phản hồi HTTP 204. Quan trọng là **để WebFlux subscribe**, không gọi `token.subscribe()` thủ công. Cookie được gửi qua header `Set-Cookie` của response, không nhất thiết có body JSON.

### 5.1. Tại sao GET /csrf nên same-origin và no-store?

Token có giá trị bảo mật trong phạm vi phiên/trình duyệt; endpoint khởi tạo token nên được bảo vệ khỏi cache và chia sẻ cross-origin không cần thiết. Với frontend:

~~~javascript
const response = await fetch("/csrf", {
  method: "GET",
  credentials: "same-origin",
  cache: "no-store"
});
if (!response.ok) {
  throw new Error("Không lấy được CSRF token");
}
~~~

`credentials: "same-origin"` gửi cookie cho request cùng origin, không làm lộ token sang một origin khác. `cache: "no-store"` tránh dùng lại kết quả GET cache khi cần cookie mới. Phía server nên có chính sách cache headers thích hợp; Spring Security thường cung cấp cache-control mặc định nhưng ứng dụng vẫn cần kiểm tra khi có CDN/proxy.

### 5.2. Vòng đời login/logout

~~~text
GET /csrf (before login) --> issue XSRF-TOKEN A
POST /login + token A  --> authentication thành công
                           CSRF token A có thể bị clear
GET /csrf (after login) --> issue XSRF-TOKEN B
POST /api/notes + B     --> 200 nếu user đủ quyền
POST /logout + B        --> logout / CSRF token có thể bị clear
GET /csrf (after logout)--> issue token mới C nếu cần
~~~

Không giả định giá trị token luôn ổn định mãi giữa lần load trang, login, logout, session expiration, tab khác hoặc refresh cookie. **JS nên lấy/refresh token sau khi login/logout** và xử lý 403 do token hết hiệu lực bằng một flow an toàn (không retry vô hạn; không tự replay thao tác nguy hiểm không idempotent).

## 6. Gửi X-XSRF-TOKEN từ JavaScript cùng origin

Với cookie `HttpOnly=false`, JavaScript có thể đọc `document.cookie`. Browser tự gửi cookie trong request; JavaScript phải chủ động copy giá trị sang `X-XSRF-TOKEN`.

### 6.1. Đọc cookie

~~~javascript
function getCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const entry = document.cookie
    .split(";")
    .map(part => part.trim())
    .find(part => part.startsWith(prefix));

  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}

const csrfToken = getCookie("XSRF-TOKEN");
if (!csrfToken) {
  throw new Error("Chưa có cookie XSRF-TOKEN");
}
~~~

Đây là hàm JS đơn giản dành cho **same-origin demo**. Nó không đọc được cookie `HttpOnly=true` và cũng không thể đọc cookie của một origin không thuộc quyền truy cập của trang. Nếu cookie cùng tên tồn tại ở nhiều path/domain, browser có thể có nhiều cookie và cách chọn theo chuỗi đơn giản không đủ tin cậy; tốt nhất thiết kế cookie path/host rõ ràng.

### 6.2. Thêm header cho POST JSON

~~~javascript
async function createNote(text) {
  await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  const token = getCookie("XSRF-TOKEN");
  if (!token) {
    throw new Error("Không lấy được CSRF cookie");
  }

  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify({ text })
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  return response.json();
}
~~~

Đoạn này là mảnh JavaScript có hàm `getCookie` đã khai báo trước. Phần thực hành dùng version kiểm tra kỹ hơn (status 302/login HTML, JSON và 403).

**Không** truyền token trong URL/query string như `?csrf=...`: URL dễ lọt vào browser history, reverse-proxy logs, analytics hoặc referrer. Với JSON request, custom header là lựa chọn rõ ràng. Tránh cố trộn `_csrf` vào JSON body mà không có một parser CSRF chuyên dụng: Spring Security thường tìm token qua **header hoặc form parameter**, không tự đọc mọi JSON field.

### 6.3. Fetch gửi cookie thế nào?

| `credentials` | Ý nghĩa | Khi nào sử dụng? |
|---|---|---|
| `same-origin` | Gửi cookie/credential cho request cùng origin. | **Mặc định khuyến nghị** của ví dụ SPA cùng origin. |
| `include` | Có thể gửi credential cho cross-origin nếu browser/CORS/cookie policy cho phép. | Chỉ dùng khi thiết kế cross-origin có kiểm soát. |
| `omit` | Không gửi cookie/credential. | API stateless hoặc request không cần session; có thể khiến user thành anonymous. |

Đặt custom header **không tự đính kèm cookie session** nếu bạn đã dùng `credentials:"omit"`. Ngược lại, gửi cookie **mà không có header CSRF** có thể bị 403. Hai việc có vai trò độc lập.

### 6.4. Tránh gửi token ra ngoài origin

Client nên sử dụng đường dẫn tương đối như `"/api/notes"` hoặc kiểm tra URL đích trước khi thêm header. Không cấu hình interceptor toàn cục để gắn `X-XSRF-TOKEN` cho mọi request đến CDN, analytics, API của bên thứ ba hoặc redirect ngoại domain. Token là giá trị gắn với origin/session; gửi ra nơi khác không mang lại lợi ích và tăng rủi ro rò rỉ.

## 7. Ví dụ Java 17 chạy độc lập: Spring Boot WebFlux + cookie CSRF + SPA

Bài thực hành dùng **Java 17**, **Spring Boot 3.5.16**, Spring Security reactive và một trang HTML/JavaScript **được phục vụ từ cùng origin** với backend. Spring Boot quản lý phiên bản Spring Security tương ứng qua dependency management; bản release nên được cập nhật theo hỗ trợ bảo mật của dự án thực tế.

**Các mục tiêu quan sát:**

1. `GET /csrf` tạo `XSRF-TOKEN` cookie đọc được bằng JavaScript.
2. `POST /api/notes` nếu thiếu header CSRF → **403**.
3. Có cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN` cùng raw value → cho qua CSRF; cần user authenticated để vào controller.
4. Dùng `formLogin` để website có session-cookie authentication; `httpBasic` cũng được bật **chỉ để integration test HTTP không cần thao tác giao diện**.
5. `GET /app.html` tải trang có form JS; người học đăng nhập tại `/login` trước khi gọi API.
6. `POST /api/notes` chỉ trả lại một xác nhận demo, **không lưu vào cơ sở dữ liệu**.

### 7.1. Cấu trúc project

~~~text
cookie-csrf-webflux-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/CookieCsrfWebFluxDemo.java
    ├── main/resources/static/app.html
    └── test/java/example/CookieCsrfIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cookie-csrf-webflux-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Cần JDK 17+ và Gradle tương thích với Spring Boot 3.5. Nếu có Gradle Wrapper thì nên dùng wrapper. Không thêm dependency `spring-boot-starter-web` của Servlet vì ví dụ cần stack WebFlux.

### 7.2. Ứng dụng đầy đủ

`src/main/java/example/CookieCsrfWebFluxDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestHandler;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class CookieCsrfWebFluxDemo {

    public static void main(String[] args) {
        SpringApplication.run(CookieCsrfWebFluxDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Chỉ dành cho localhost, không dùng {noop} ở production.
        UserDetails user = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var csrfCookie = CookieServerCsrfTokenRepository.withHttpOnlyFalse();

        // Local demo dùng HTTP; ở production HTTPS đặt secure(true).
        csrfCookie.setCookieCustomizer(cookie -> cookie
            .path("/")
            .sameSite("Lax"));

        var xor = new XorServerCsrfTokenRequestAttributeHandler();
        var plain = new ServerCsrfTokenRequestAttributeHandler();

        ServerCsrfTokenRequestHandler spaHandler =
            new ServerCsrfTokenRequestHandler() {

                @Override
                public void handle(
                    ServerWebExchange exchange, Mono<CsrfToken> token) {

                    // Giữ masked token khi expose cho form/view.
                    xor.handle(exchange, token);
                }

                @Override
                public Mono<String> resolveCsrfTokenValue(
                    ServerWebExchange exchange, CsrfToken token) {

                    // JS gửi raw cookie value trong X-XSRF-TOKEN.
                    boolean headerPresent = exchange.getRequest()
                        .getHeaders().containsKey(token.getHeaderName());

                    return headerPresent
                        ? plain.resolveCsrfTokenValue(exchange, token)
                        : xor.resolveCsrfTokenValue(exchange, token);
                }
            };

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/csrf", "/app.html", "/login").permitAll()
                .anyExchange().authenticated())
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfCookie)
                .csrfTokenRequestHandler(spaHandler))
            .formLogin(Customizer.withDefaults())
            // Cho phép integration test gửi Basic, không cần login form.
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    public record NoteRequest(String text) {
    }

    @RestController
    static class Api {

        // Subscribe vào token Mono -> cookie XSRF-TOKEN được tạo khi cần.
        @GetMapping("/csrf")
        @ResponseStatus(HttpStatus.NO_CONTENT)
        Mono<Void> csrf(ServerWebExchange exchange) {
            Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

            if (token == null) {
                return Mono.error(new IllegalStateException(
                    "CSRF token attribute unavailable"));
            }

            return token.then();
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal ->
                    Map.of("username", principal.getName()));
        }

        @PostMapping("/api/notes")
        Mono<Map<String, String>> create(
            @RequestBody Mono<NoteRequest> body,
            ServerWebExchange exchange) {

            // Chỉ xác nhận request, không ghi cơ sở dữ liệu.
            return exchange.getPrincipal()
                .zipWith(body)
                .map(pair -> Map.of(
                    "acceptedBy", pair.getT1().getName(),
                    "text", pair.getT2().text()));
        }
    }
}
~~~

**Điểm quan trọng của Java code:**

- `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` để `document.cookie` đọc token.
- `setCookieCustomizer` đặt path và SameSite; trong local demo chưa bật `Secure` vì chạy `http://localhost`. Production phải bảo vệ kết nối TLS và cân nhắc `Secure` bắt buộc.
- `XorServerCsrfTokenRequestAttributeHandler` vẫn dùng để expose token cho form/view; `ServerCsrfTokenRequestAttributeHandler` xử lý raw header JS.
- `.csrf(...)` không bị disable. Các POST thiếu/sai CSRF token bị `CsrfWebFilter` từ chối.
- `formLogin(...)` tạo login form/session cho người dùng browser; `httpBasic(...)` bổ sung cách gọi từ integration test. Trong production nên chỉ bật các cơ chế login thực sự cần.
- `GET /csrf` public để client khởi tạo token; nó **không chứng minh user authenticated** và được dùng để chuẩn bị cho login POST cũng như thao tác sau login.
- `GET /app.html` public phục vụ trang JavaScript; controller POST `/api/notes` chỉ xử lý khi user đã authenticated và CSRF hợp lệ.
- `NoteRequest` là Java record (Java 17), Jackson của Spring Boot có thể chuyển JSON `{"text":"..."}` thành object.
- Không dùng `block()` hoặc `subscribe()` thủ công; tất cả trả `Mono` cho WebFlux xử lý.

### 7.3. Giao diện JavaScript cùng origin

`src/main/resources/static/app.html`:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebFlux CSRF Cookie Demo</title>
</head>
<body>
  <h1>POST JSON với X-XSRF-TOKEN</h1>
  <p>Trước tiên đăng nhập qua <a href="/login">/login</a>
     bằng learner / demo-pass (chỉ local).</p>

  <form id="noteForm">
    <input id="noteText" value="Xin chào WebFlux" required>
    <button type="submit">Gửi POST</button>
  </form>
  <pre id="result" aria-live="polite"></pre>

  <script type="module">
    "use strict";

    function readCookie(name) {
      const prefix = encodeURIComponent(name) + "=";
      const entry = document.cookie
        .split(";")
        .map(part => part.trim())
        .find(part => part.startsWith(prefix));

      return entry
        ? decodeURIComponent(entry.slice(prefix.length))
        : null;
    }

    async function getFreshCsrfToken() {
      const response = await fetch("/csrf", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error("Lấy CSRF cookie thất bại: HTTP "
          + response.status);
      }

      const token = readCookie("XSRF-TOKEN");
      if (!token) {
        throw new Error("Không tìm thấy cookie XSRF-TOKEN");
      }

      return token;
    }

    async function submitNote(text) {
      // Gọi lại sau login vì token cũ có thể được xóa/rotate.
      const token = await getFreshCsrfToken();

      const response = await fetch("/api/notes", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-XSRF-TOKEN": token
        },
        body: JSON.stringify({ text })
      });

      // Với form login, fetch có thể follow redirect và nhận HTML login.
      const contentType = response.headers.get("Content-Type") || "";

      if (response.redirected || !contentType.includes("application/json")) {
        throw new Error("Hãy đăng nhập tại /login trước khi gửi POST");
      }

      const data = await response.json();

      if (!response.ok) {
        throw new Error("POST bị từ chối: HTTP " + response.status);
      }

      return data;
    }

    document.getElementById("noteForm")
      .addEventListener("submit", async event => {
        event.preventDefault();

        const result = document.getElementById("result");
        const text = document.getElementById("noteText").value;

        result.textContent = "Đang gửi...";

        try {
          const data = await submitNote(text);
          result.textContent = JSON.stringify(data, null, 2);
        } catch (error) {
          result.textContent = String(error.message || error);
        }
      });
  </script>
</body>
</html>
~~~

**Cách chạy trang:** truy cập `http://localhost:8080/login`, đăng nhập `learner / demo-pass`, rồi mở `http://localhost:8080/app.html` và click **Gửi POST**. JavaScript sẽ GET `/csrf`, đọc cookie raw `XSRF-TOKEN`, gửi header `X-XSRF-TOKEN` và JSON đến `/api/notes`. Sau khi cookie session/CSRF hợp lệ, server phản hồi JSON tương tự `{"acceptedBy":"learner","text":"Xin chào WebFlux"}`.

Kết quả thật có thể có thứ tự field JSON khác. Đây là **HTTP response** chứ không phải stdout của Java application. Demo không ghi dữ liệu vào database; `acceptedBy` chỉ cho biết principal đã xác thực, còn `text` là dữ liệu được echo.

### 7.4. Các bước chạy

Trong thư mục `cookie-csrf-webflux-demo`:

~~~bash
gradle bootRun
~~~

Nếu đã có Gradle Wrapper: `./gradlew bootRun` trên Linux/macOS hoặc `gradlew.bat bootRun` trên Windows. Khi app đang chạy, mở trình duyệt theo hướng dẫn trên. Trong developer tools có thể kiểm tra:

- Response của `GET /csrf` có thể chứa `Set-Cookie: XSRF-TOKEN=...; Path=/; SameSite=Lax` (cookie được refresh/lưu khi token thực sự tạo).
- Request `POST /api/notes` gửi cookie `SESSION` (nếu browser đã đăng nhập), cookie `XSRF-TOKEN` và header `X-XSRF-TOKEN` mang cùng **raw token**.
- Trong Network tab, nếu POST trả 403, kiểm tra chính xác token, cookie, handler và path thay vì tắt CSRF.
- Không copy/paste cookie, session token hoặc credential thật vào ticket/log. Dùng giá trị thử nghiệm và xóa dữ liệu nhạy cảm khỏi ảnh debug.

### 7.5. Kiểm tra thủ công bằng curl (HTTP Basic dành riêng demo)

Có thể bỏ qua bước browser login trong phép thử cơ chế CSRF bằng cách dùng HTTP Basic có sẵn trong demo. Dùng **cookie jar** để đảm bảo request POST gửi lại token do server đã tạo:

~~~bash
# 1. Server tạo cookie XSRF-TOKEN.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf

# 2. POST có Basic đúng nhưng THIẾU X-XSRF-TOKEN: thường 403.
curl -i -b cookies.txt -u learner:demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"missing header"}' \
  http://localhost:8080/api/notes

# 3. POST có CSRF header giả: 403.
curl -i -b cookies.txt -u learner:demo-pass \
  -H 'Content-Type: application/json' \
  -H 'X-XSRF-TOKEN: invalid-token' \
  -d '{"text":"wrong header"}' \
  http://localhost:8080/api/notes
~~~

Để thử POST thành công, đọc **giá trị cookie XSRF-TOKEN** từ cookie jar một cách an toàn và truyền lại đúng giá trị vào header:

~~~bash
# Dành cho demo; không in token thật vào log/ticket.
TOKEN=$(awk '$6=="XSRF-TOKEN"{print $7}' cookies.txt)

curl -i -b cookies.txt -u learner:demo-pass \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $TOKEN" \
  -d '{"text":"valid header"}' \
  http://localhost:8080/api/notes
~~~

Đây là cú pháp **Bash/GNU awk**; trên Windows PowerShell, dùng `curl.exe` và một cách đọc cookie tương thích. Thứ tự các cột trong file cookie jar của curl tuân dạng Netscape; việc cookie tồn tại phụ thuộc response `GET /csrf` thật sự được tạo. Nếu command đầu không có cookie, kiểm tra deferred token và việc endpoint đã subscribe vào `Mono<CsrfToken>`.

Không dùng mật khẩu thật với `-u` trong shell history/process listing; ở đây là account demo local. Không gửi HTTP Basic qua mạng không mã hóa ngoài localhost.

## 8. Integration tests bằng WebTestClient

Tệp `src/test/java/example/CookieCsrfIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CookieCsrfIntegrationTest {

    @Autowired
    WebTestClient client;

    private ResponseCookie csrfCookie() {
        var result = client.get().uri("/csrf")
            .exchange()
            .expectStatus().isNoContent()
            .returnResult(Void.class);

        ResponseCookie cookie =
            result.getResponseCookies().getFirst("XSRF-TOKEN");

        assertNotNull(cookie, "GET /csrf phải tạo XSRF-TOKEN");
        assertFalse(cookie.isHttpOnly(),
            "JS phải đọc được cookie trong demo này");
        return cookie;
    }

    @Test
    void missingHeaderIsForbiddenEvenWithValidCredential() {
        ResponseCookie cookie = csrfCookie();

        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .cookie("XSRF-TOKEN", cookie.getValue())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CookieCsrfWebFluxDemo.NoteRequest("missing"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongHeaderIsForbidden() {
        ResponseCookie cookie = csrfCookie();

        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .cookie("XSRF-TOKEN", cookie.getValue())
            .header("X-XSRF-TOKEN", "invalid-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CookieCsrfWebFluxDemo.NoteRequest("wrong"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rawCookieTokenInHeaderAllowsPost() {
        ResponseCookie cookie = csrfCookie();

        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .cookie("XSRF-TOKEN", cookie.getValue())
            .header("X-XSRF-TOKEN", cookie.getValue())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CookieCsrfWebFluxDemo.NoteRequest("allowed"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.acceptedBy").isEqualTo("learner")
            .jsonPath("$.text").isEqualTo("allowed");
    }

    @Test
    void safeGetDoesNotNeedCsrfHeader() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

Hoặc `./gradlew test` / `gradlew.bat test` với wrapper. Kỳ vọng bốn test đạt **khi** code/dependency/cấu hình trên chạy chính xác; cần thực thi thật để xác nhận. Trong bài test, Basic chỉ chứng minh authentication thành công độc lập với cookie CSRF; trong browser thực tế, form login + session cookie mới là bối cảnh CSRF quan trọng nhất.

### 8.1. Test gì để khẳng định code an toàn hơn?

Bộ test trên chỉ là mức cơ bản. Trước production cần bổ sung:

1. Sau form login, cookie CSRF cũ bị xóa/rotate đúng và client lấy được token mới.
2. Sau logout, token trước đó không được chấp nhận trái policy; endpoint token có thể phát mới nếu cần.
3. Request POST có token đúng nhưng **không authenticated** phải bị authentication policy chặn.
4. Token đúng nhưng user thiếu role vẫn bị authorization từ chối.
5. Cross-origin POST không có header tùy biến bị 403; preflight CORS không được mở rộng bừa bãi.
6. Nhiều browser tab với token được rotate có hành vi retry/refresh rõ ràng.
7. Cookie Path/Domain/Secure/SameSite phù hợp với origin thực sau reverse proxy/TLS termination.
8. 403 từ CSRF được phân biệt trong server audit với 403 do thiếu quyền, không tiết lộ chi tiết token cho caller.

Đừng xem một test `POST 200` là bằng chứng đã bảo vệ chống mọi CSRF/XSS; cần kiểm thử threat model, CORS và cookie injection riêng.

## 9. CORS, SPA đặt ở origin khác và các vấn đề cookie

Ví dụ chính **same-origin**: trang được serve từ `localhost:8080`, API cũng ở `localhost:8080`. Đó là mô hình đơn giản nhất để đọc `XSRF-TOKEN` và gửi custom header.

Nếu SPA nằm tại `https://ui.example.test` còn API tại `https://api.example.test`:

- Hai địa chỉ là **khác origin** (scheme/host/port), dù có thể cùng site theo quy tắc SameSite.
- JS ở origin UI không mặc nhiên đọc cookie host-only của API qua `document.cookie`.
- `fetch(..., {credentials:"include"})` chỉ yêu cầu trình duyệt gửi credential theo policy; nó **không** cấp quyền đọc cookie của origin khác cho JavaScript.
- Header `X-XSRF-TOKEN` và Content-Type JSON có thể tạo **CORS preflight**. Server cần allowlist origin cụ thể, phương thức và header; credentialed CORS không dùng `Access-Control-Allow-Origin: *`.
- Nếu thật sự dùng third-party cookies, các hạn chế browser mới có thể chặn chúng; `SameSite=None` cần `Secure`, nhưng không bảo đảm third-party cookie luôn hoạt động.
- Có thể dùng mô hình BFF/reverse proxy để UI/API cùng origin, hoặc endpoint lấy CSRF token theo cơ chế authenticated CORS được kiểm soát; cần kiểm tra thông tin token có bị lộ qua API public cross-origin hay không.
- Không chia sẻ cookie CSRF cho toàn bộ các subdomain chỉ để vượt qua Same-Origin Policy mà không đánh giá subdomain takeover/cookie tossing.

### 9.1. CORS không phải là toàn bộ CSRF protection

CORS chủ yếu hạn chế **JavaScript ở origin khác đọc response và gửi request đặc biệt**; browser vẫn có thể gửi một số cross-origin request dạng form/navigation. Vì vậy đừng nói “đã bật CORS là không cần CSRF”. CSRF token/Origin checking/SameSite và các ranh giới server-side vẫn cần được đánh giá tùy auth model.

### 9.2. Cookie injection và double-submit

Khi expected token nằm trong cookie, hệ thống phải xét các tình huống attacker có khả năng **đặt/ghi cookie với tên trùng** thông qua một subdomain bị chiếm, cấu hình Domain quá rộng hoặc các lỗi liên quan. Một chiến lược phòng thủ có thể gồm:

- Không dùng Domain chung khi không thực sự cần; ưu tiên **host-only cookie**.
- Ở production HTTPS, cân nhắc cookie prefix `__Host-` (yêu cầu `Secure`, `Path=/` và **không có Domain**) cùng tên JS tương ứng; phải cấu hình repository và code để dùng cùng tên.
- Kiểm tra Origin/Referer và `Sec-Fetch-Site` khi phù hợp với threat model, không thay thế token bằng một header tự chế không được kiểm chứng.
- Đừng để untrusted proxy copy cookie raw sang CSRF request header cho mọi request.
- Với ứng dụng rủi ro cao, cân nhắc synchronizer token được ràng buộc với session hoặc mô hình signed, session-bound double-submit nếu thiết kế cho phép.

**Cookie CSRF token không phải một lớp chống XSS.** XSS chạy trên cùng origin thường có thể đọc non-HttpOnly cookie và gửi request tùy biến. Đó là lý do cả hai biện pháp phải song hành.

## 10. HttpOnly, Secure, SameSite, Path: chọn ra sao?

| Thuộc tính | Gợi ý cho XSRF-TOKEN ở SPA same-origin | Lưu ý |
|---|---|---|
| `HttpOnly` | `false` **nếu JS thật sự phải đọc cookie** | Nếu không cần đọc, nên giữ `true` qua `new CookieServerCsrfTokenRepository()`. |
| `Secure` | `true` trên HTTPS production | Local HTTP demo có thể không đặt; production cần TLS end-to-end phù hợp. |
| `SameSite` | Thường `Lax` hoặc `Strict` theo UX | Cross-site kiến trúc khác có thể cần None+Secure, có trade-off. |
| `Path` | `/` nếu JS/API nằm nhiều route trên cùng host | Path hẹp có thể làm JS không thấy cookie ở trang hiện hành. |
| `Domain` | Ưu tiên **không đặt** (host-only) | Domain quá rộng làm tăng bề mặt cookie injection. |
| `Max-Age` | Phù hợp vòng đời token; xem xét session/login/logout | Không để token tồn tại quá lâu nếu policy yêu cầu rotate. |

**Đừng gán HttpOnly=false cho session cookie chỉ vì CSRF cookie cần JS đọc.** `SESSION` chứa định danh phiên đăng nhập và nên duy trì HttpOnly. Hai cookie phục vụ hai mục đích khác nhau.

**Đừng đặt Secure=false trong production HTTPS** để xử lý lỗi CORS hoặc “không thấy cookie”. Hãy kiểm tra proxy/TLS configuration, domain/path và browser policies.

## 11. Lỗi thường gặp và cách xử lý

**Lỗi 1 — Không tìm thấy cookie XSRF-TOKEN sau GET.**

Nguyên nhân có thể là deferred CSRF token chưa được subscribe/được sử dụng, endpoint GET không đi qua CSRF filter, cookie path khác, hoặc Set-Cookie bị proxy/browser chặn. Sửa: dùng `GET /csrf` có `Mono<CsrfToken>.then()`, kiểm tra Network response Set-Cookie và Path/Domain/Secure/SameSite.

**Lỗi 2 — Có cookie, gửi đúng raw header mà vẫn 403.**

Với Spring Security 6.x, `XorServerCsrfTokenRequestAttributeHandler` mặc định kỳ vọng masked token trong nhiều trường hợp. Dùng custom resolver raw-header + masked-form như ví dụ hoặc chọn plain handler có hiểu trade-off BREACH; test cả POST đúng/sai.

**Lỗi 3 — Chỉ gửi cookie, không gửi X-XSRF-TOKEN.**

Cookie thường được browser gửi tự động và không chứng minh hành động chủ động. JS phải thêm token vào header trên request unsafe. `credentials:"same-origin"` không tự tạo CSRF header.

**Lỗi 4 — Gửi token trong JSON field và mong Spring tự đọc.**

Repository mặc định đọc từ header `X-XSRF-TOKEN` hoặc form parameter `_csrf`; JSON `{"_csrf":"..."}` không mặc nhiên được CsrfWebFilter parse. Dùng header.

**Lỗi 5 — Không refresh token sau login/logout.**

Authentication success/logout có thể clear token; cookie cũ trở nên vô hiệu. Trước POST tiếp theo, GET /csrf để nhận token mới, xử lý trường hợp session hết hạn hoặc re-login.

**Lỗi 6 — Đặt cookie HttpOnly=true rồi đọc document.cookie.**

JS không thể đọc cookie HttpOnly; dùng `withHttpOnlyFalse()` **chỉ khi cần**, hoặc chọn cách đưa token qua meta/form/API response với security thích hợp.

**Lỗi 7 — Dùng CookieCsrfTokenRepository của Servlet.**

WebFlux cần `CookieServerCsrfTokenRepository`. Class Servlet có API nhận HttpServletRequest/Response, không tương thích reactive.

**Lỗi 8 — Tắt CSRF để chữa 403.**

Làm vậy có thể khiến browser cookie auth dễ bị CSRF. Phải kiểm tra token source/header, request handler, cookie attributes và security matcher trước. Không dùng `csrf.disable()` như một giải pháp debug lâu dài.

**Lỗi 9 — Đưa token vào URL/query string.**

Token có thể lọt vào log, history, analytics, referrer. Dùng custom header cho JSON requests.

**Lỗi 10 — Gửi token cho mọi origin qua interceptor.**

Nếu request tới domain không tin cậy cũng có `X-XSRF-TOKEN`, token bị lộ. Giới hạn origin rõ ràng, dùng relative URLs hoặc allowlist host.

**Lỗi 11 — Dùng CORS wildcard với credential.**

Credentialed CORS không nên có wildcard origin; phải allowlist origin tin cậy và phương thức/headers cần thiết. CORS không thay thế CSRF.

**Lỗi 12 — Nghĩ CSRF token cho phép bất kỳ thao tác nào.**

CSRF chỉ giúp chống request giả mạo từ site khác; quyền nghiệp vụ vẫn do Authentication + Authorization quyết định.

**Lỗi 13 — XSS có thể chạy cùng origin nhưng chỉ dựa vào CSRF token.**

XSS có thể đọc cookie non-HttpOnly và gửi request. Cần CSP/output encoding/dependency hygiene; không coi CSRF là XSS defense.

**Lỗi 14 — Gọi token.subscribe() trong controller.**

Có thể tạo cookie/ghi response không đúng thời điểm, mất lỗi hoặc cạnh tranh commit. Trả reactive publisher qua WebFlux.

**Lỗi 15 — Nhầm 401 và 403.**

Đã authenticated nhưng CSRF sai thường nhận 403; chưa login thì authentication entry point có thể redirect 302 (form login) hoặc trả 401 (Basic). Không xử lý mọi 403 bằng cách yêu cầu đăng nhập lại hoặc retry POST vô hạn.

**Lỗi 16 — GET thay đổi dữ liệu nhưng bỏ qua CSRF.**

GET là safe method theo mặc định; hãy sửa endpoint sang POST/PUT/PATCH/DELETE phù hợp. Không dựa vào việc “frontend chỉ có nút đúng” để bảo vệ.

**Lỗi 17 — Cookie trùng tên ở nhiều path/domain.**

JS có thể đọc nhầm một cookie khác; thiết kế host-only + Path nhất quán, có thể dùng tiền tố `__Host-` trên HTTPS.

**Lỗi 18 — Reuse token giữa nhiều tài khoản/session mà không đánh giá.**

CSRF cookie có vòng đời riêng với login session và có thể cần rotate; đánh giá rủi ro theo threat model và đảm bảo client lấy token mới khi state auth đổi.

## 12. Checklist review trước production

1. Có thực sự dùng cookie/session hoặc cơ chế credential browser tự gửi không? CSRF threat model đã được mô tả?
2. Cookie repository có đúng là **`CookieServerCsrfTokenRepository`** của WebFlux?
3. Client cần đọc cookie? Nếu có, `HttpOnly=false` chỉ áp dụng cho XSRF-TOKEN, không phải SESSION?
4. Server có phát cookie sau GET /csrf thực sự subscribe token Mono?
5. JS có gửi custom header `X-XSRF-TOKEN` trên POST/PUT/PATCH/DELETE cần bảo vệ?
6. Cookie XSRF-TOKEN và header có cùng raw token như policy handler?
7. Với Spring Security 6, có xử lý khác biệt **raw header** và **XOR masked form**?
8. Missing/wrong CSRF token có bị từ chối 403; correct token cho phép tiếp tục authorization?
9. Token đúng nhưng user không đủ quyền có vẫn bị 403 vì authorization?
10. Token đúng nhưng user chưa đăng nhập có bị yêu cầu authentication?
11. Sau login/logout, frontend refresh token và xử lý session expiry/403 rõ ràng?
12. Không vô tình ghi token vào URL/log/third-party request/cross-origin analytics?
13. Cookie có Path, Domain, SameSite, Secure phù hợp origin thực qua HTTPS/proxy?
14. CORS có allowlist cụ thể, không dùng wildcard với credential, xử lý preflight header?
15. Không đặt cookie chia sẻ subdomain rộng nếu không cần; có cân nhắc cookie injection?
16. XSS defense (CSP, output encoding) được duy trì, không ỷ lại CSRF?
17. HTTP safe methods không có side effect nghiệp vụ?
18. Mọi code xử lý CSRF có dùng reactive publishers đúng, không block/subscribe thủ công?
19. Các test thực tế có đủ cookie+header happy path, missing/wrong header, login/logout refresh, multi-tab?
20. Đã thử trong browser/HTTP client thật và kiểm tra sự khác biệt giữa 302, 401 và 403?

## 13. Tự kiểm tra kiến thức

**1.** Có `XSRF-TOKEN` cookie được browser tự gửi trên POST. Vậy đã đủ CSRF protection chưa?

**Đáp án:** Chưa. Browser tự gửi cookie ở cả request hợp lệ và một số request bị lừa; JS hoặc form phải cung cấp token ở **header/form parameter** mà attacker không thể dễ dàng tạo cho origin được bảo vệ.

**2.** Khi nào dùng `CookieServerCsrfTokenRepository.withHttpOnlyFalse()`?

**Đáp án:** Khi JS cùng origin cần đọc cookie và gửi lại raw token qua header. Nếu không cần JS đọc, ưu tiên giữ cookie HttpOnly để giảm bề mặt XSS.

**3.** Tên mặc định của cookie và header là gì?

**Đáp án:** Cookie `XSRF-TOKEN`, header `X-XSRF-TOKEN`. Form parameter mặc định `_csrf`.

**4.** Vì sao gửi raw token từ cookie với default XOR handler của Spring Security 6 có thể nhận 403?

**Đáp án:** XOR handler được thiết kế để giải masked token được đưa ra view; raw cookie value không phải masked representation. Cần raw-header resolver hoặc handler plain với trade-off đã hiểu.

**5.** `GET /csrf` có cần ghi body JSON chứa token không?

**Đáp án:** Không. Có thể subscribe `Mono<CsrfToken>` để framework tạo cookie và trả 204; JS đọc cookie non-HttpOnly.

**6.** Sau login/logout, có thể dùng mãi token cũ không?

**Đáp án:** Không nên giả định. CSRF token có thể được clear/rotate, nên SPA phải khởi tạo/refresh cookie token phù hợp.

**7.** `credentials:"include"` có cho phép JavaScript ở origin UI đọc cookie host-only của API origin khác không?

**Đáp án:** Không. Nó ảnh hưởng việc trình duyệt gửi credential theo policy, không bỏ Same-Origin Policy của `document.cookie`.

**8.** Cookie CSRF non-HttpOnly có giống session cookie cần bảo vệ danh tính không?

**Đáp án:** Không. Cookie CSRF dùng để kiểm tra request; session cookie là credential xác thực phiên và nên HttpOnly. Dù vậy XSS có thể lấy CSRF token và gửi request, nên vẫn phải chống XSS.

**9.** Vì sao custom header giúp chống CSRF tốt hơn chỉ gửi cookie?

**Đáp án:** Request cross-origin đơn giản có thể đính kèm cookie tự động; custom header cần JS có quyền gửi (và CORS preflight nếu cross-origin), tạo ranh giới thêm với attacker không có quyền đọc token.

**10.** API dùng Bearer token được JS gắn thủ công trong mỗi request và không có credential browser tự gửi thì có cần CSRF không?

**Đáp án:** Nguy cơ CSRF truyền thống có thể thấp hơn, nhưng cần đánh giá cách token được lưu, CORS, XSS và các loại cookie khác. Không mặc định tắt CSRF cho toàn app chỉ vì API được gọi là REST.

## Tài liệu chính thức

- Spring Security 6.5 — CSRF for WebFlux (cookie repository, XOR handler, AJAX/JSON header): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — `CookieServerCsrfTokenRepository` API (`withHttpOnlyFalse`, `setCookieCustomizer`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html
- Spring Security 6.5 — `ServerCsrfTokenRequestHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestHandler.html
- Spring Security 6.5 — `ServerCsrfTokenRequestAttributeHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html
- Spring Security 6.5 — `XorServerCsrfTokenRequestAttributeHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security — `ServerHttpSecurity.CsrfSpec` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Testing CSRF with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- OWASP — Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
