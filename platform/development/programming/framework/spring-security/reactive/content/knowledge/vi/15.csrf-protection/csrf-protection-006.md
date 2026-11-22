# Đọc Mono<CsrfToken> và bảo đảm token được tạo khi cần

> **Chủ đề:** Spring Security – reactive  
> **Nhóm kiến thức:** Bảo vệ CSRF  
> **Trọng tâm:** Đọc đúng `Mono<CsrfToken>` từ `ServerWebExchange`, kích hoạt việc tải/tạo/lưu CSRF token **bằng subscription có chủ đích** trong luồng WebFlux, xuất token cho HTML form hoặc client cùng origin và kiểm thử request sử dụng lại token với cùng phiên.

## 1. Vấn đề thực tế: vì sao trang GET không có token?

Ứng dụng Spring WebFlux sử dụng Spring Security để bảo vệ một form:

```html
<form action="/api/form" method="post">
    <input type="text" name="message">
    <button type="submit">Gửi</button>
</form>
```

Nếu form chỉ có hai trường này mà không gửi CSRF token, `POST /api/form` thường bị Spring Security trả **403 Forbidden**. Đây không nhất thiết là lỗi đăng nhập, role hay controller. `CsrfWebFilter` mặc định yêu cầu CSRF token hợp lệ cho các HTTP method có thể thay đổi trạng thái, chẳng hạn POST.

Trong Spring Security **reactive**, một điều dễ bỏ sót là CSRF token **không phải lúc nào cũng đã được tạo ngay** khi request GET vào ứng dụng. Framework đưa vào `ServerWebExchange` một **publisher**:

```java
Mono<CsrfToken>
```

Khi publisher này được **subscribe**, token dự kiến được tải từ repository hoặc tạo/lưu mới nếu chưa có. Chỉ lấy thuộc tính hoặc gọi `doOnNext` mà bỏ quên publisher sẽ không bảo đảm việc tạo token xảy ra.

Ví dụ lõi:

```java
@GetMapping("/csrf")
Mono<CsrfView> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> tokenMono =
        exchange.getAttribute(CsrfToken.class.getName());

    if (tokenMono == null) {
        return Mono.error(
            new IllegalStateException("CSRF publisher unavailable"));
    }

    return tokenMono.map(token -> new CsrfView(
        token.getHeaderName(),
        token.getParameterName(),
        token.getToken()));
}
```

Đây là **snippet**, cần `CsrfView`/imports và security configuration. Vì controller **trả về publisher có sử dụng `tokenMono`**, WebFlux subscribe để tạo HTTP response, kích hoạt đường tải/tạo token. Phần project đầy đủ ở mục 8 minh họa cả việc giữ session cookie và gửi token ở POST.

### Mục tiêu học tập

Sau bài này bạn có thể:

1. Giải thích nguy cơ CSRF và vì sao token cần đi cùng session/credential của browser.
2. Xác định đúng thuộc tính **`CsrfToken.class.getName()`** chứa `Mono<CsrfToken>` trong `ServerWebExchange`.
3. Phân biệt **publisher chưa subscribe** với `CsrfToken` đã được phát ra; dùng `map`/`flatMap`/`then` thay vì `block()` hoặc `subscribe()` thủ công.
4. Hiểu vai trò `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler`, repository dựa trên `WebSession` và Xor handler chống BREACH.
5. Chủ động tạo token khi cần hiển thị form hoặc cung cấp endpoint lấy token, nhưng **không bắt buộc tạo cho mọi GET vô ích**.
6. Đặt token vào hidden field `_csrf` hoặc HTTP header `X-CSRF-TOKEN` và gửi lại với **cùng session cookie**.
7. Kiểm thử request GET nhận token, POST đúng/sai/thiếu token, session khác và luồng lazy bằng `WebTestClient` + `StepVerifier`.

## 2. Tại sao phải bảo vệ CSRF?

CSRF (Cross-Site Request Forgery) lợi dụng việc browser có thể tự gửi các credentials gắn với một website, ví dụ session cookie hoặc credentials HTTP authentication đã được ghi nhớ. Một website độc hại có thể khiến trình duyệt người dùng gửi POST tới website đích mà người dùng không chủ ý.

```text
Người dùng đã đăng nhập shop.example
          |
          v
Browser giữ session cookie của shop.example
          |
          v
Người dùng mở website lạ attacker.example
          |
          v
Trang lạ cố khiến browser gửi POST shop.example/api/change
          |
          v
Browser có thể tự gửi cookie đủ điều kiện cho shop.example
          |
          v
Nếu server chỉ dựa vào cookie => có nguy cơ request giả mạo
Nếu server yêu cầu token bí mật ràng buộc session => bị chặn
```

CSRF token theo **synchronizer-token pattern** là một giá trị khó đoán mà server lưu/kiểm tra theo ngữ cảnh hợp lệ. Client phải gửi token ở một vị trí browser **không tự động gắn vào request từ trang lạ** — thường là hidden form parameter hoặc HTTP header do JavaScript của cùng origin đặt.

**Phân biệt với các cơ chế khác:**

| Cơ chế | Giải quyết vấn đề gì? | Không thay thế cho |
| --- | --- | --- |
| Session cookie | Giữ danh tính/phiên | CSRF token khi browser tự gửi cookie |
| HTTP Basic | Xác thực username/password | CSRF nếu browser có thể tự gửi credentials |
| CSRF token | Xác nhận request unsafe phát sinh từ luồng được server cấp token | Authentication, authorization, kiểm tra nghiệp vụ |
| CORS | Giới hạn trình duyệt đọc phản hồi/gửi một số cross-origin requests | CSRF token; form POST cross-site vẫn có thể xảy ra |
| SameSite cookie | Hạn chế nhiều trường hợp cookie gửi cross-site | Defense-in-depth, không bảo đảm thay thế mọi CSRF policy |
| XSS protection | Ngăn script độc hại chạy trong origin đáng tin | CSRF token không chống được XSS trong cùng origin |

Các phương thức HTTP **GET, HEAD, OPTIONS, TRACE** được coi là safe theo matcher mặc định của CSRF; ứng dụng phải bảo đảm chúng **không làm thay đổi trạng thái**. Không thiết kế `GET /delete-account` rồi mong CSRF filter ngăn request đó theo cấu hình mặc định.

Spring Security WebFlux mặc định bật bảo vệ CSRF khi không bị tắt bởi cấu hình. Đừng tùy tiện `.csrf(csrf -> csrf.disable())` chỉ vì gặp 403; hãy xác định client có dùng browser credentials tự động hay không và threat model cụ thể.

## 3. Chính xác có những object nào?

Đây là các thành phần dễ bị trộn:

| Tên | Loại | Công việc |
| --- | --- | --- |
| `CsrfToken` | Interface, đồng bộ | Cung cấp `getToken()`, `getHeaderName()`, `getParameterName()` |
| `Mono<CsrfToken>` | Reactor Publisher | Mô tả thao tác lấy/tạo token, chỉ thực thi khi được subscribe |
| `CsrfWebFilter` | `org.springframework.web.server.WebFilter` | Đưa publisher vào exchange, kiểm tra token cho request cần CSRF |
| `ServerWebExchange` | WebFlux request/response context | Chứa attributes, `WebSession`, request/response |
| `ServerCsrfTokenRepository` | Interface reactive | `loadToken`, `generateToken`, `saveToken` |
| `WebSessionServerCsrfTokenRepository` | Repository mặc định | Lưu token dự kiến trong `WebSession` |
| `CookieServerCsrfTokenRepository` | Repository thay thế | Lưu token qua cookie; cần cân nhắc security/SPA |
| `ServerCsrfTokenRequestHandler` | Request handler/resolver | Đưa token ra exchange và đọc token do client gửi |
| `XorServerCsrfTokenRequestAttributeHandler` | Handler mặc định từ Spring Security 6 | Mặt nạ token mỗi request để hỗ trợ chống BREACH |

**Package WebFlux đúng:**

```java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.CsrfWebFilter;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
```

Đây là **danh sách import minh họa**; không phải tất cả đều cần trong cùng file. Đừng thay nhầm bằng `org.springframework.security.web.csrf.CsrfToken` (Servlet) hoặc `HttpSessionCsrfTokenRepository`. Với WebFlux, các class nằm trong package có **`.web.server.csrf`**, và repository trả `Mono`.

### 3.1. Khóa attribute cực kỳ quan trọng

Trong Spring Security WebFlux 6.5, `CsrfWebFilter` expose publisher dưới khóa:

```java
CsrfToken.class.getName()
```

Giá trị chuỗi tương ứng:

```text
org.springframework.security.web.server.csrf.CsrfToken
```

Code đọc đúng:

```java
Mono<CsrfToken> csrfToken =
    exchange.getAttribute(CsrfToken.class.getName());
```

`exchange.getAttribute(...)` trả giá trị từ attribute map, không thực thi chính publisher. Nếu publisher null, thường có lỗi cấu hình/chain (`CsrfWebFilter` không chạy, CSRF bị disable, request match chain khác); đừng làm giả token hoặc silently cho phép POST. Ví dụ project trả lỗi rõ ràng từ server thay vì trả một form thiếu hidden field.

Một điều **không giống nhau**:

```text
CsrfToken.class.getName()  -> khóa chứa Mono<CsrfToken> từ framework
"_csrf"                    -> tên form parameter/attribute view phổ biến
"X-CSRF-TOKEN"             -> tên request header phổ biến
"XSRF-TOKEN"               -> tên cookie phổ biến của cookie repository
```

Đừng gọi `exchange.getAttribute("_csrf")` rồi mặc định đó là `Mono<CsrfToken>`. Một view integration hoặc `@ControllerAdvice` có thể expose **CsrfToken đã resolve** dưới tên `_csrf` cho template; chúng là các tầng khác nhau.

### 3.2. Ba getter của CsrfToken

```java
// Snippet bên trong .map(token -> ...):
String headerName = token.getHeaderName();
String parameterName = token.getParameterName();
String renderedToken = token.getToken();
```

- `getToken()`: giá trị **đưa cho client theo handler hiện hành**. Với Xor handler mặc định, giá trị expose có thể là token được mask; **không lấy raw token từ repository để tự thay thế**.
- `getHeaderName()`: tên header client phải dùng, thường `X-CSRF-TOKEN` với WebSession repository mặc định.
- `getParameterName()`: tên form field, thường `_csrf`.

Mã HTML/JS nên dùng tên lấy từ token hoặc từ cấu hình đã thống nhất thay vì hardcode nhiều chỗ; nếu ứng dụng thay `setHeaderName`/`setParameterName` mà frontend giữ tên cũ, POST sẽ bị 403.

## 4. Cơ chế lazy: vì sao phải subscribe?

Trong Reactor, một `Mono<T>` là mô tả của một pipeline. Tạo biến `Mono` hoặc gắn một operator trung gian **không đồng nghĩa pipeline đã chạy**.

```text
GET /csrf
   |
   v
CsrfWebFilter lấy/tạo publisher Mono<CsrfToken>
   |
   v
ServerCsrfTokenRequestHandler đưa publisher vào exchange attributes
   |
   v
Controller đọc attribute Mono<CsrfToken>
   |
   +-- Controller bỏ qua Mono, trả text tĩnh
   |       |
   |       +--> không có bảo đảm token mới được tạo/lưu
   |
   +-- Controller trả tokenMono.map(CsrfView::new)
           |
           v
      WebFlux subscribe để tạo response
           |
           v
      Repository: load existing token / generate new / save
           |
           v
      Response chứa tên field/header + token đã expose
```

Tài liệu API `CsrfWebFilter` nêu rõ: nếu token chưa có, token mới được **lưu tự động khi publisher được subscribe**. Do đó, bài toán không phải “gọi thủ công `generateToken()` trên mọi request”, mà là **đưa đúng publisher vào pipeline thực sự được subscribe khi UI cần token**.

### 4.1. Sai: chỉ lấy attribute

```java
@GetMapping("/bad")
Mono<String> bad(ServerWebExchange exchange) {
    Mono<CsrfToken> csrf =
        exchange.getAttribute(CsrfToken.class.getName());
    // Không sử dụng publisher trong response.
    return Mono.just("HTML không có token");
}
```

Đây là snippet minh họa anti-pattern. `csrf` chỉ là reference; việc tạo/lưu token chưa được kích hoạt bởi controller. Đừng coi việc có một attribute là đã có token được persist trong session.

### 4.2. Sai: doOnNext nhưng bỏ publisher mới

```java
Mono<CsrfToken> csrf =
    exchange.getAttribute(CsrfToken.class.getName());

// Sai nếu bỏ qua giá trị Mono được trả về:
csrf.doOnNext(token -> exchange.getAttributes().put("_csrf", token));

return Mono.just("view");
```

`doOnNext` tạo một publisher mới có side effect khi subscribe; ở đây không có ai subscribe publisher đó, nên side effect không chạy theo đường controller đã viết. Phải **trả/compose** publisher được biến đổi.

### 4.3. Đúng: compose và để framework subscribe

```java
Mono<CsrfToken> csrf =
    exchange.getAttribute(CsrfToken.class.getName());

return csrf.map(token -> token.getToken());
```

Khi method WebFlux trả `Mono<String>`, response writer subscribe vào publisher. Nhờ đó token được load/generate/save nếu cần; không có `block()` hoặc một subscription phụ.

### 4.4. Đúng: cần kết hợp tác vụ khác thì dùng flatMap/then

```java
// Minh họa: auditService là dependency reactive do ứng dụng cung cấp.
return csrfMono.flatMap(token ->
    auditService.record("csrf-view-generated")
        .thenReturn(token.getToken()));
```

`auditService.record` phải trả publisher reactive. Đây là snippet ý tưởng, không phải file Java chạy riêng. Không log chính giá trị token trong audit; chỉ log sự kiện cần thiết.

### 4.5. Không dùng block()/subscribe() trong controller

```java
// Sai ở request path của WebFlux:
CsrfToken token = csrfMono.block();

// Cũng sai: subscription rời, không chờ lưu token hoàn tất.
csrfMono.subscribe(token -> exchange.getAttributes().put("_csrf", token));
return Mono.just("render ngay");
```

`.block()` có thể chặn event loop và gây lỗi trên scheduler không cho phép blocking. `.subscribe()` thủ công khiến thao tác tạo/lưu token có lifecycle tách rời response, không bảo đảm thứ tự, lỗi và cancellation. Thay bằng `map`/`flatMap` và **trả Mono** cho WebFlux.

## 5. BREACH/XOR: token lộ ra view có thể khác token lưu trong session

Từ Spring Security **6.0**, handler mặc định của WebFlux là `XorServerCsrfTokenRequestAttributeHandler`, giúp chống kênh rò rỉ thông tin BREACH bằng **mask CSRF token** khi nó được đưa ra trong response. Bản ghi lưu trong repository và giá trị đưa lên form có thể trông khác nhau, kể cả khi dựa trên cùng expected token.

```text
WebSessionServerCsrfTokenRepository
      |
      v
Expected raw token (lưu trong WebSession)
      |
      v
XorServerCsrfTokenRequestAttributeHandler
      |
      v
CsrfToken được expose cho view
      |
      v
form input / header chứa token đã mask
      |
      v
Client gửi token
      |
      v
Request handler giải mask / resolve
      |
      v
CsrfWebFilter so khớp với token dự kiến trong repository
```

**Hệ quả quan trọng:**

1. Đừng mong `token.getToken()` luôn bằng đúng giá trị raw đang lưu trong session.
2. Đừng đặt assertion “hai trang GET liên tiếp phải có cùng chuỗi token hiển thị”. Với XOR mask, giá trị expose có thể thay đổi theo request, trong khi raw expected token ở server vẫn dùng được.
3. Client nên gửi **chính token đã nhận từ response/form**, không tự tạo hoặc giải mã/mask ở frontend.
4. Nếu đổi `csrfTokenRequestHandler` về `ServerCsrfTokenRequestAttributeHandler`, bạn đang thay đổi cơ chế chống BREACH — **không làm chỉ để sửa test**.
5. Với cookie-based CSRF trong SPA, cookie thường chứa giá trị raw trong khi Xor handler mặc định kỳ vọng masked request token. Không giả định copy trực tiếp `XSRF-TOKEN` cookie vào `X-XSRF-TOKEN` header luôn hoạt động trên mọi cấu hình; cần một request handler/SPA integration tương thích và integration test.

### 5.1. Request token không phải mật khẩu

CSRF token là một giá trị bảo mật nhạy cảm theo session, không phải credential đăng nhập. Nhưng lộ token cho đúng browser/user là **điều bắt buộc** của synchronizer token pattern. Cần chống rò qua URL, analytics, logging, cross-origin response, HTTP cache, referrer và XSS.

Trong ví dụ, endpoint `GET /csrf` trả JSON **không cache**. Với ứng dụng có authentication state nhạy cảm, có thể chỉ cho phép lấy token theo chính sách và kiểm soát CORS. Cross-site script không được đọc token nhờ same-origin policy khi CORS chặt, nhưng **XSS trong cùng origin** có thể đọc token; CSRF không thay thế XSS protection.

## 6. Hiển thị form: bảo đảm Mono được tiêu thụ

### 6.1. Render trực tiếp từ Mono

Mẫu được ưu tiên khi render HTML thủ công:

```java
@GetMapping(value = "/form", produces = MediaType.TEXT_HTML_VALUE)
Mono<String> form(ServerWebExchange exchange) {
    Mono<CsrfToken> csrf =
        exchange.getAttribute(CsrfToken.class.getName());

    if (csrf == null) {
        return Mono.error(new IllegalStateException("CSRF unavailable"));
    }

    return csrf.map(token -> {
        String field = HtmlUtils.htmlEscape(token.getParameterName());
        String value = HtmlUtils.htmlEscape(token.getToken());
        return "<form action='/api/form' method='post'>"
            + "<input type='hidden' name='" + field
            + "' value='" + value + "'>"
            + "<button type='submit'>Gửi</button></form>";
    });
}
```

Snippet này cần imports và class có đầy đủ wiring. Trong project đầy đủ ở mục 8 có một implementation tương đương, thêm text input để test POST. Điểm quyết định là **`return csrf.map(...)`**, không phải một `String` đồng bộ xây trước khi CSRF publisher được subscribe.

`HtmlUtils.htmlEscape` tránh đưa giá trị vào HTML attribute một cách thiếu an toàn. Dù token mặc định dùng ký tự an toàn trong Base64/UUID, render HTML **vẫn cần escaping** khi ghép chuỗi.

### 6.2. @ControllerAdvice + @ModelAttribute cho template engine

Nếu dùng view technology tích hợp `RequestDataValueProcessor`, Spring Security hướng dẫn expose token dưới attribute `_csrf`. Ví dụ:

```java
// Snippet minh họa (đặt trong class @ControllerAdvice, đủ imports).
@ModelAttribute
Mono<CsrfToken> csrfToken(ServerWebExchange exchange) {
    Mono<CsrfToken> publisher =
        exchange.getAttribute(CsrfToken.class.getName());
    if (publisher == null) {
        return Mono.error(new IllegalStateException("CSRF unavailable"));
    }
    return publisher.doOnSuccess(token ->
        exchange.getAttributes().put(
            CsrfRequestDataValueProcessor.DEFAULT_CSRF_ATTR_NAME,
            token));
}
```

Import `CsrfRequestDataValueProcessor` từ Spring Security WebFlux. Mục đích là **khi model publisher được subscribe**, đưa token đã resolve vào attribute `_csrf` cho `CsrfRequestDataValueProcessor`/view. Đừng tạo `Mono` mới rồi bỏ qua nó. Thymeleaf với Spring Security integration có thể tự xử lý phần boilerplate; nếu dùng cơ chế render khác hãy xác minh việc subscription.

Form được render có thể chứa:

```html
<form action="/api/form" method="post">
    <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_CUNG_CAP">
    <input name="message" value="hello">
    <button type="submit">Lưu</button>
</form>
```

`TOKEN_DO_SERVER_CUNG_CAP` ở đây chỉ là **placeholder trong giải thích**, không phải giá trị bạn phải gửi. Với code chạy thật, hidden input được điền từ `token.getToken()`; token được mask theo handler hiện hành. Trong template, đừng hardcode tên field nếu repository có thể được cấu hình khác.

### 6.3. JSON/API endpoint cho client cùng origin

Nếu frontend gửi JSON, không thể tự cho `_csrf` vào form parameter của một body JSON. Thay vào đó, lấy token hợp lệ rồi đặt nó vào **HTTP header**:

```http
GET /csrf
Cookie: SESSION=<cookie-phiên-đang-có>
```

Phản hồi minh họa:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "<giá-trị-token-do-server-cấp>"
}
```

Client gửi request unsafe:

```http
POST /api/change
Cookie: SESSION=<cùng-cookie-phiên>
Authorization: Basic <credentials-demo>
X-CSRF-TOKEN: <giá-trị-token-do-server-cấp>
Content-Type: application/json

{"message":"hello"}
```

Hai request này phải thuộc **cùng session** nếu server dùng `WebSessionServerCsrfTokenRepository`. Một token lấy cho session A không được dùng với session B, ngay cả khi request B có username/password hợp lệ.

## 7. Không phải GET nào cũng cần ép tạo token

Việc CSRF token được tạo/lưu có thể khiến ứng dụng tạo session trên request lẽ ra chỉ đọc dữ liệu. Với website có rất nhiều traffic cacheable, **ép subscribe trên mọi GET** có thể gây tăng WebSession, làm giảm khả năng cache và làm phức tạp vận hành.

| GET request | Có thật sự cần token? | Cách xử lý |
| --- | --- | --- |
| `GET /public` chỉ hiển thị nội dung công khai | Thường không | Không subscribe chỉ để ép tạo CSRF |
| `GET /form` hiển thị form POST | **Có** | Consume `Mono<CsrfToken>` khi render hidden input |
| `GET /csrf` cấp token cho JavaScript same-origin | **Có** | Return publisher `Mono<CsrfView>`; no-store |
| `GET /health` | Thường không | Giữ lightweight, không tự tạo session |
| `GET /dashboard` không có form/action | Tùy UX | Nếu không cần unsafe action, đừng tạo token vô ích |
| JSON-only stateless API với Bearer header | Phụ thuộc threat model | Đánh giá CSRF riêng; không tắt CSRF theo cảm tính |

**Bảo đảm token được tạo khi cần** nghĩa là để request/path có nhu cầu token **consume publisher** và để framework lưu token, không phải gọi `generateToken` thủ công trên mọi GET.

### 7.1. Luồng repository: load, generate, save

`ServerCsrfTokenRepository` có ba method:

```java
Mono<CsrfToken> loadToken(ServerWebExchange exchange);
Mono<CsrfToken> generateToken(ServerWebExchange exchange);
Mono<Void> saveToken(ServerWebExchange exchange, CsrfToken token);
```

**Đây là các chữ ký API minh họa**, không phải một interface tự định nghĩa. `CsrfWebFilter` dùng repository để có expected token và tự lưu token mới khi Mono được subscribe. Bạn thường **không cần** gọi trực tiếp generate/save trong controller chỉ để render form. Một thuật toán mô tả:

```text
Nếu repo.loadToken(exchange) tìm thấy expected token:
    dùng existing token
Ngược lại, khi CSRF Mono được subscribe:
    repo.generateToken(exchange)
    repo.saveToken(exchange, generated)
    cung cấp token cho handler/view
```

Nếu bạn tự implement repository, phải đảm bảo `loadToken`/`saveToken` trả publisher đúng, không blocking và không vô tình tạo token mới vô hạn trên mỗi attempt. `saveToken(exchange, null)` theo interface tương đương xóa token; trong vòng đời login/logout hoặc session invalidation, token có thể cần cấp lại.

## 8. Project WebFlux Java 17+ runnable

Dự án sử dụng **Spring Boot 3.5.16** để có baseline học tập cụ thể với Spring Security 6.5.x và Java 17. Nhánh 3.5 đã hết OSS support; production mới năm 2026 nên dùng nhánh Spring Boot còn được hỗ trợ và kiểm tra migration notes, không coi version ở đây là lựa chọn production mới.

Cấu trúc:

```text
reactive-csrf-on-demand/
├── pom.xml
└── src/
    ├── main/java/demo/csrf/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── CsrfController.java
    └── test/java/demo/csrf/
        ├── CsrfFlowTests.java
        └── CsrfMonoSemanticsTests.java
```

**Thiết kế:**

- `GET /public`: public, **không cần subscribe CSRF token**.
- `GET /csrf`: trả `CsrfView` gồm headerName/parameterName/token, kích hoạt load hoặc generate/save nếu cần.
- `GET /form`: trả HTML form có hidden CSRF field, kích hoạt cùng publisher.
- `GET /api/profile`: cần Basic authentication nhưng không cần CSRF vì là GET.
- `POST /api/change`: cần Basic và CSRF header, nhận JSON.
- `POST /api/form`: cần Basic và CSRF form parameter.
- CSRF vẫn được bật, dùng `WebSessionServerCsrfTokenRepository` tường minh và request handler XOR mặc định.
- Tài khoản `alice` password `demo123` chỉ cho local test; lưu BCrypt hash, không triển khai bằng credential hardcoded thật.

### 8.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-csrf-on-demand</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Vì `spring-boot-starter-webflux` có Spring WebFlux và Jackson, JSON response của Java record được encode tự động. `spring-boot-starter-security` cấu hình security cho WebFlux. `spring-boot-starter-test` và `spring-security-test` dùng trong tests.

### 8.2. src/main/java/demo/csrf/Application.java

```java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 8.3. src/main/java/demo/csrf/SecurityConfiguration.java

```java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public", "/csrf", "/form").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            // Không disable CSRF. Giữ mặc định XOR request handler.
            .csrf(csrf -> csrf.csrfTokenRepository(
                new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
```

**Chú giải:**

1. `.csrf(...)` chỉ khai báo repository; CSRF vẫn **bật**. Handler mặc định 6.x tiếp tục là `XorServerCsrfTokenRequestAttributeHandler`.
2. `WebSessionServerCsrfTokenRepository` lưu expected token trong WebSession. Token đã mask đưa ra từ handler không nên được so trực tiếp với chuỗi raw của session.
3. `permitAll()` trên `GET /csrf` **không tắt CSRF** cho các POST sau đó; GET là safe method còn POST cần token.
4. `httpBasic(...)` giúp test authentication độc lập; Basic đúng **không bỏ qua** CSRF.
5. `.formLogin(...disable())` chỉ tắt form-login authentication mặc định, **không tắt HTML form mẫu** của ứng dụng.
6. Bản demo chỉ dùng localhost; khi triển khai phải dùng HTTPS và quản lý secret thay vì hardcode password.

### 8.4. src/main/java/demo/csrf/CsrfController.java

```java
package demo.csrf;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.HtmlUtils;
import reactor.core.publisher.Mono;

@RestController
public class CsrfController {

    public record CsrfView(
            String headerName, String parameterName, String token) {}

    public record ChangeRequest(String message) {}

    // Lấy publisher do CsrfWebFilter đặt vào exchange.
    private Mono<CsrfToken> tokenPublisher(ServerWebExchange exchange) {
        Mono<CsrfToken> publisher =
            exchange.getAttribute(CsrfToken.class.getName());

        if (publisher == null) {
            return Mono.error(
                new IllegalStateException("CSRF filter did not expose token"));
        }

        return publisher;
    }

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    // Endpoint cùng origin: consume publisher, token mới được lưu khi cần.
    @GetMapping(value = "/csrf",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders().setCacheControl("no-store");

        return tokenPublisher(exchange)
            .map(token -> new CsrfView(
                token.getHeaderName(),
                token.getParameterName(),
                token.getToken()));
    }

    // Render một form HTML nhỏ, escape mọi giá trị đặt vào attribute.
    @GetMapping(value = "/form",
            produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> form(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders().setCacheControl("no-store");

        return tokenPublisher(exchange).map(token -> {
            String parameterName =
                HtmlUtils.htmlEscape(token.getParameterName());
            String value = HtmlUtils.htmlEscape(token.getToken());

            return """
                <!doctype html>
                <html lang="vi">
                <head><meta charset="utf-8"><title>CSRF demo</title></head>
                <body>
                  <form method="post" action="/api/form">
                    <input type="hidden" name="%s" value="%s">
                    <input type="text" name="message" value="hello">
                    <button type="submit">Lưu</button>
                  </form>
                </body>
                </html>
                """.formatted(parameterName, value);
        });
    }

    // GET an toàn không cần gửi CSRF token.
    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("profile OK");
    }

    @PostMapping(value = "/api/change",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<String> change(@RequestBody Mono<ChangeRequest> body) {
        return body.map(request -> "saved:" + request.message());
    }

    @PostMapping(value = "/api/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> submitForm(ServerWebExchange exchange) {
        return exchange.getFormData()
            .map(data -> "form:" + data.getFirst("message"));
    }
}
```

**Điểm quan trọng nhất trong file này:** `GET /csrf` và `GET /form` đều **trả publisher được compose từ `tokenPublisher(exchange)`**. Chính subscription do WebFlux thực hiện khi ghi response khiến `CsrfWebFilter`/repository có cơ hội tạo và lưu token mới. Trái lại, `GET /public` không đọc và không ép tạo token.

`GET /csrf` chứa token ở JSON, response đặt `Cache-Control: no-store` để giảm nguy cơ token bị cache ngoài ý muốn. Trong sản phẩm, còn cần chính sách CORS/Cache, xác minh same-origin và hạn chế public caching của proxy. Client dùng `CsrfView.headerName` cùng `CsrfView.token` cho unsafe request, **không tạo token ở client**.

## 9. Integration tests: lấy token thật, giữ cùng WebSession, POST mới hợp lệ

Ví dụ test dùng **Spring Boot chạy Netty trên random port**, thay vì chỉ gọi controller thuần, để có một chu trình HTTP, CSRF filter, session cookie và Basic authentication thật. `@SpringBootTest(webEnvironment=RANDOM_PORT)` cùng `@AutoConfigureWebTestClient` tạo một `WebTestClient` kết nối server thực.

### 9.1. src/test/java/demo/csrf/CsrfFlowTests.java

```java
package demo.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfFlowTests {

    @Autowired
    WebTestClient client;

    private record Issued(
        CsrfController.CsrfView csrf, String sessionId) {}

    // GET này subscribe Mono<CsrfToken>, từ đó tạo/lưu token khi cần.
    private Issued issue() {
        EntityExchangeResult<CsrfController.CsrfView> result =
            client.get().uri("/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody(CsrfController.CsrfView.class)
                .returnResult();

        CsrfController.CsrfView csrf = result.getResponseBody();
        assertNotNull(csrf);
        assertNotNull(csrf.token());
        assertNotNull(csrf.headerName());
        assertNotNull(csrf.parameterName());

        ResponseCookie cookie =
            result.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie, "new WebSession must have a cookie");

        return new Issued(csrf, cookie.getValue());
    }

    private WebTestClient.ResponseSpec postJson(
            Issued issued, String submittedCsrfToken) {

        return client.post().uri("/api/change")
            .cookie("SESSION", issued.sessionId())
            .headers(headers -> {
                headers.setBasicAuth("alice", "demo123");
                if (submittedCsrfToken != null) {
                    headers.set(
                        issued.csrf().headerName(), submittedCsrfToken);
                }
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange();
    }

    @Test
    void publicGetDoesNotNeedCsrfToken() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void csrfGetCreatesTokenAndWebSessionCookieWhenNeeded() {
        Issued issued = issue();
        assertEquals("X-CSRF-TOKEN", issued.csrf().headerName());
        assertEquals("_csrf", issued.csrf().parameterName());
        assertTrue(!issued.csrf().token().isBlank());
        assertTrue(!issued.sessionId().isBlank());
    }

    @Test
    void csrfResponseIsNotCacheable() {
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .valueMatches(HttpHeaders.CACHE_CONTROL, ".*no-store.*");
    }

    @Test
    void safeGetWorksWithoutCsrfButRequiresAuthentication() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile OK");
    }

    @Test
    void postWithoutCsrfIsRejectedEvenWithValidBasicCredentials() {
        Issued issued = issue();
        postJson(issued, null)
            .expectStatus().isForbidden();
    }

    @Test
    void postWithWrongCsrfIsRejected() {
        Issued issued = issue();
        postJson(issued, "invalid-csrf-token")
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfFromSameSessionAllowsJsonPost() {
        Issued issued = issue();
        postJson(issued, issued.csrf().token())
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("saved:hello");
    }

    @Test
    void validCsrfCanBeUsedWithSubsequentPostInSameSession() {
        Issued issued = issue();
        postJson(issued, issued.csrf().token())
            .expectStatus().isOk();
        postJson(issued, issued.csrf().token())
            .expectStatus().isOk();
    }

    @Test
    void tokenWithoutItsSessionCookieIsRejected() {
        Issued issued = issue();

        client.post().uri("/api/change")
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .header(issued.csrf().headerName(), issued.csrf().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tokenFromDifferentSessionIsRejected() {
        Issued a = issue();
        Issued b = issue();
        assertNotEquals(a.sessionId(), b.sessionId());

        postJson(b, a.csrf().token())
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() {
        Issued issued = issue();

        client.post().uri("/api/change")
            .cookie("SESSION", issued.sessionId())
            .header(issued.csrf().headerName(), issued.csrf().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicPasswordStillReturns401WithValidCsrf() {
        Issued issued = issue();

        client.post().uri("/api/change")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .header(issued.csrf().headerName(), issued.csrf().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void formPageIncludesHiddenCsrfInput() {
        EntityExchangeResult<String> result =
            client.get().uri("/form")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String html = result.getResponseBody();
        assertNotNull(html);
        assertTrue(html.contains("name=\"_csrf\""));
        assertTrue(html.contains("type=\"hidden\""));
        assertNotNull(result.getResponseCookies().getFirst("SESSION"));
    }

    @Test
    void validCsrfFormParameterAllowsPost() {
        Issued issued = issue();

        client.post().uri("/api/form")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("message", "hello")
                .with(issued.csrf().parameterName(), issued.csrf().token()))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("form:hello");
    }

    @Test
    void formPostWithoutCsrfIsRejected() {
        Issued issued = issue();

        client.post().uri("/api/form")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("message", "hello"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void formPostWithInvalidCsrfIsRejected() {
        Issued issued = issue();

        client.post().uri("/api/form")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("message", "hello")
                .with(issued.csrf().parameterName(), "invalid"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Bộ integration có **16 phương thức `@Test`**. Nó kiểm tra token mới được cấp trên GET, session cookie xuất hiện, POST hợp lệ khi **cùng phiên**, CSRF sai/thiếu bị 403, Basic sai/thiếu bị 401 sau khi CSRF hợp lệ, JSON header và form parameter đều được framework tiếp nhận.

**Tại sao giữ cookie thủ công?** `WebTestClient` trong ví dụ không được cấu hình như browser tự động lưu cookies, nên helper `issue()` lấy cookie `SESSION` rồi gửi lại trong POST. Đây chính là phép kiểm chứng rằng token mới tạo đã được **lưu trong WebSession** và không thể sử dụng qua session khác. Khi dùng browser thật, cookie được browser quản lý theo chính sách SameSite/Secure/HttpOnly, không được copy cookie giữa người dùng.

### 9.2. Đọc kết quả đúng cách

| Trường hợp | Kết quả dự kiến | Ý nghĩa |
| --- | --- | --- |
| GET `/csrf` | 200 + CSRF view + session cookie | Mono được consume, token mới có thể được tạo/lưu |
| GET `/public` | 200 | Không bắt buộc tạo token cho trang public |
| GET `/api/profile` với Basic đúng | 200 | GET safe không phải gửi CSRF token |
| POST JSON không CSRF, Basic đúng | **403** | `CsrfWebFilter` từ chối trước controller |
| POST JSON sai CSRF, Basic đúng | **403** | Giá trị không khớp expected token |
| POST JSON đúng CSRF + cùng SESSION + Basic đúng | **200** | CSRF và authentication đều hợp lệ |
| POST JSON đúng token nhưng **không** có SESSION tương ứng | **403** | Token không phù hợp session mới |
| POST JSON token A, cookie session B | **403** | Không được mượn token giữa các phiên |
| POST JSON CSRF đúng nhưng không Basic | **401** | CSRF không thay thế authentication |
| POST JSON CSRF đúng nhưng Basic password sai | **401** | Authentication thất bại |
| GET `/form` | 200 + hidden input + session cookie | Template đã subscribe token publisher |
| POST form đúng hidden token/cookie/Basic | **200** | Framework đọc form param `_csrf` |
| POST form thiếu/sai token | **403** | Form không vượt qua CSRF check |

Không dùng `@WithMockUser` một mình để kết luận session-cookie/token round trip đã hoạt động. `mutateWith(csrf())` hữu ích cho **bài test controller không quan tâm token lifecycle**, nhưng ở đây muốn kiểm tra chính **tạo/lưu/đọc Mono<CsrfToken>**, nên test phải lấy token từ endpoint thật và gửi lại.

## 10. Test ngữ nghĩa lazy Publisher bằng StepVerifier

Các test này minh họa **quy tắc Reactor**: `Mono.defer(...)` không chạy callback cho tới lúc subscribe. Chúng **không thay thế** integration tests ở mục 9, bởi một `Mono` tự tạo không chứng minh `CsrfWebFilter` đã lưu cookie/session.

### src/test/java/demo/csrf/CsrfMonoSemanticsTests.java

```java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.DefaultCsrfToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CsrfMonoSemanticsTests {

    private static Mono<CsrfToken> deferredToken(AtomicInteger counter) {
        return Mono.defer(() -> {
            counter.incrementAndGet();
            return Mono.just(new DefaultCsrfToken(
                "X-CSRF-TOKEN", "_csrf", "example-token"));
        });
    }

    @Test
    void creatingMonoDoesNotGenerateTokenYet() {
        AtomicInteger counter = new AtomicInteger();
        Mono<CsrfToken> csrf = deferredToken(counter);

        assertEquals(0, counter.get());

        StepVerifier.create(csrf)
            .expectNextMatches(token ->
                "example-token".equals(token.getToken()))
            .verifyComplete();

        assertEquals(1, counter.get());
    }

    @Test
    void operatorChainIsAlsoLazyUntilSubscribed() {
        AtomicInteger counter = new AtomicInteger();

        Mono<String> rendered = deferredToken(counter)
            .map(token -> "value=" + token.getToken());

        assertEquals(0, counter.get());

        StepVerifier.create(rendered)
            .expectNext("value=example-token")
            .verifyComplete();

        assertEquals(1, counter.get());
    }

    @Test
    void ignoringTheReturnedMonoDoesNotExecuteSideEffect() {
        AtomicInteger generated = new AtomicInteger();
        AtomicInteger observed = new AtomicInteger();

        Mono<CsrfToken> original = deferredToken(generated);
        original.doOnNext(token -> observed.incrementAndGet());

        assertEquals(0, generated.get());
        assertEquals(0, observed.get());

        StepVerifier.create(original)
            .expectNextCount(1)
            .verifyComplete();

        assertEquals(1, generated.get());
        // doOnNext đã bị bỏ qua, không nằm trong subscription.
        assertEquals(0, observed.get());
    }
}
```

Ba test chứng minh:

1. Chỉ **khai báo `Mono`** không khiến công việc bên trong `defer` chạy.
2. **`map`** cũng lazy; việc render xảy ra khi subscriber thực thi.
3. `doOnNext` tạo một publisher mới: nếu bỏ qua publisher được trả về, side effect gắn ở nhánh đó không chạy.

Trong ứng dụng thật, `CsrfWebFilter` dùng logic tạo/lưu token của Spring Security; ví dụ `DefaultCsrfToken("...")` trong test chỉ là **test value**, không được gửi cho Spring Security của ứng dụng như token có thể xác thực.

## 11. Chạy Maven, thử browser và xác minh stdout/kết quả

### 11.1. Yêu cầu

- JDK 17+, Maven tương thích Spring Boot 3.5;
- Các file nằm đúng package `demo.csrf`;
- Cổng localhost không bị ứng dụng khác chiếm dụng nếu chạy Boot bằng lệnh.

Tại thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Theo mã ví dụ, có **19 tests**: 16 HTTP `WebTestClient` và 3 Reactor `StepVerifier`. Kỳ vọng sau khi cài đúng dependencies, Maven Surefire cho `Tests run: 19, Failures: 0, Errors: 0` và `BUILD SUCCESS`. Đây là **kết quả dự kiến**, không phải tuyên bố bộ test đã được chạy trong môi trường này. Nếu có lỗi, đọc `target/surefire-reports` và kiểm tra chính xác Spring Boot/JDK/test dependencies.

Khởi động:

```bash
mvn spring-boot:run
```

Mở browser:

```text
http://localhost:8080/form
```

Browser nhận HTML chứa `<input type="hidden" name="_csrf" value="...">`. Lúc này `Mono<CsrfToken>` được subscribe khi HTML response được tạo. Với form action `/api/form`, trình duyệt có thể được yêu cầu HTTP Basic credentials; dùng user demo `alice`/`demo123` và cùng session cookie của tab đang mở.

Thử bằng curl (localhost, không dùng secrets thật trong shell history):

```bash
# Lấy token JSON cùng với Set-Cookie: SESSION=...
curl -i http://localhost:8080/csrf

# HTML form có hidden CSRF input
curl -i http://localhost:8080/form

# GET public không cần CSRF
curl -i http://localhost:8080/public

# Request GET đã xác thực, không cần CSRF
curl -i -u alice:demo123 http://localhost:8080/api/profile

# POST thiếu CSRF => 403 (nếu credentials hợp lệ)
curl -i -u alice:demo123 -H "Content-Type: application/json" \
  -d '{"message":"hello"}' http://localhost:8080/api/change
```

Với PowerShell, dùng `curl.exe` nếu `curl` trỏ tới alias khác. Trên Windows shell có thể phải đổi cú pháp quoting cho JSON. Nếu muốn gửi POST **hợp lệ** bằng curl, cần lưu **cả** cookie `SESSION` từ GET vào cookie jar và lấy trường `token` từ JSON, sau đó gửi đúng `headerName` + `token` ở POST. Một lệnh `curl -X POST` có Basic đúng nhưng **không giữ WebSession** sẽ không chứng minh CSRF hoạt động đúng; cách tự động và chắc chắn nhất là test ở mục 9.

### 11.2. Vì sao không ghi cứng token vào README?

Token được generate ngẫu nhiên, thường được mask theo request; không có “stdout token chính xác” áp dụng mọi lần chạy. Bài học chỉ nêu ví dụ shape:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "<generated-masked-token>"
}
```

Giá trị token thực được test lấy từ `/csrf` tại runtime. Không mong hai lần `GET /csrf` trả **cùng một chuỗi masked token**. Không dùng token giả `<generated-masked-token>` để gửi POST; đó chỉ là ký hiệu giải thích.

## 12. Khi cần CookieServerCsrfTokenRepository cho SPA

Có thể cấu hình repository lưu token trong cookie:

```java
// Snippet trong SecurityWebFilterChain configuration:
.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

**Đoạn này không nằm trong project runnable của mục 8.** Nó cần import `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository`. Cookie default tên `XSRF-TOKEN`, client convention có thể gửi `X-XSRF-TOKEN`, hoặc `_csrf` parameter. `withHttpOnlyFalse()` cho JavaScript đọc cookie, nên tăng bề mặt tiếp xúc với XSS; chỉ dùng khi frontend thật sự cần đọc cookie trực tiếp, nếu không thì dùng cookie HttpOnly hoặc WebSession repository phù hợp.

**Đừng coi đây là switch một dòng cho SPA:** XOR request handler mặc định có masking/BREACH behavior, còn token trong cookie thường là raw token. Một SPA copy cookie sang header có thể không được default XOR resolver diễn giải như masked token. Cần cấu hình **request handler tương thích** với mô hình SPA, test GET tạo cookie, POST gửi header, refresh token sau login/logout khi thích hợp, và kiểm tra cookie SameSite/Secure/HttpOnly/CORS. Không vô hiệu hóa BREACH protection chỉ vì integration test chưa đúng.

Để bám sát đề bài “đọc `Mono<CsrfToken>` và đảm bảo tạo khi cần”, ví dụ chính dùng **WebSessionServerCsrfTokenRepository + token expose từ handler**, tránh nhập nhằng raw cookie với masked token.

## 13. Những thời điểm cần tạo/lấy lại token

| Tình huống | Cần làm gì | Không nên làm |
| --- | --- | --- |
| Lần đầu mở form POST | Consume `Mono<CsrfToken>` khi render | Render form rỗng rồi chờ frontend tự đoán token |
| Client SPA chuẩn bị gửi unsafe request | Lấy token từ endpoint cùng origin / cơ chế integration phù hợp | Lấy token từ một session khác |
| Trang GET public chỉ đọc | Không ép tạo token nếu không dùng | Tạo session không cần thiết |
| Session vừa hết hạn | Tải trang/token mới và gửi lại cookie mới | Reuse token cũ với cookie cũ đã hết hiệu lực |
| Login/logout làm đổi/clear security state/token | Xác nhận vòng đời token, cấp lại khi cần | Giữ token cũ mà không test |
| Cookie/session bị xóa | Tạo session/token mới | Gửi header cũ và mong vượt qua CSRF |
| CORS/cross-origin frontend | Thiết kế CORS/credentials/trusted origins cụ thể | Cho wildcard access vào token endpoint |
| Multi-instance WebFlux | Dùng session store chia sẻ hoặc sticky/session strategy đã kiểm thử | Mỗi node tự giữ state in-memory mà không đồng bộ |
| Browser giữ form quá lâu | Xử lý session timeout, hướng dẫn reload/token refresh | Tắt CSRF để tránh form hết hạn |

### 13.1. Token sau session timeout

Với repository WebSession, nếu session đã hết hạn thì expected token cũng không còn trong session đó. POST với token từ trang cũ sẽ bị 403. UX phù hợp là thông báo phiên đã hết hạn và tải lại trang/form để lấy token mới, không mở một lối “bỏ qua CSRF” cho request lỗi.

### 13.2. Cấu hình nhiều SecurityWebFilterChain

Nếu `GET /csrf` match chain A có CSRF bật, còn `POST /api/change` match chain B dùng repository hoặc cookie policy khác, token có thể không tương thích. Đảm bảo chuỗi filter, request matcher, repository và handler **phù hợp cho cả route cấp token lẫn route kiểm tra token**. Đừng chẩn đoán “Mono không chạy” khi thực tế hai URL đang được bảo vệ bởi hai security chains khác nhau.

### 13.3. HTTP form, AJAX và multipart

- Form `application/x-www-form-urlencoded`: hidden parameter theo `CsrfToken.getParameterName()`.
- AJAX/JSON: dùng header theo `CsrfToken.getHeaderName()`, không nhét token vào JSON rồi mặc nhiên nghĩ framework sẽ tìm được.
- Multipart upload: đọc token từ multipart body có thể khiến server phải parse/ghi phần upload trước khi xác thực CSRF; Spring Security WebFlux có option `tokenFromMultipartDataEnabled(true)` khi thực sự cần, nhưng cân nhắc đặt token trong header để giảm chi phí và rủi ro DoS.
- Không nhét CSRF token vào URL/query string khi có thể tránh, vì URLs có thể xuất hiện trong browser history, referrer hoặc logs.

## 14. Debug: vì sao token null hoặc POST vẫn 403?

| Hiện tượng | Nguyên nhân khả dĩ | Cách giải quyết |
| --- | --- | --- |
| `exchange.getAttribute(CsrfToken.class.getName())` trả null | CSRF filter không được áp dụng, bị disable hoặc request match chain khác | Xác minh chain, bật CSRF và đúng package WebFlux |
| Có `Mono<CsrfToken>`, nhưng session không có token mới | Publisher chưa được subscribe | Return/compose `Mono` trong response/render |
| Đã gọi `doOnNext` nhưng không thấy thuộc tính `_csrf` | Bỏ qua Mono mới tạo | Dùng publisher được trả về hoặc `@ModelAttribute` được view subscribe |
| `block()` gây exception/hang | Blocking trên event loop | Dùng `map`/`flatMap`, để WebFlux subscribe |
| Token form rỗng | Template không resolve CSRF publisher | Bật view integration hoặc render trực tiếp từ `Mono` |
| Form có token nhưng POST 403 | Token sai, hết session, cookie không đi theo, handler/repo khác | Kiểm tra cùng SESSION, đúng field/header, method |
| GET token ở session A, POST session B | Expected token không cùng session | Giữ session cookie đúng, không trộn user |
| GET trả token mới mỗi lần nhìn khác nhau | XOR mask đổi giá trị expose | Không so chuỗi masked token qua các GET; test round-trip |
| SPA copy XSRF-TOKEN cookie sang header rồi 403 | Raw-cookie token vs XOR-masked resolver | Thiết kế SPA request handler tương thích và test |
| Client gửi `X-XSRF-TOKEN` nhưng repo mặc định trông `X-CSRF-TOKEN` | Tên header không khớp | Dùng `getHeaderName()` hoặc cấu hình đồng bộ |
| Client đặt token trong JSON body | Default resolver không đọc field JSON đó | Gửi header hoặc form parameter |
| 403 khi POST `/login` | CSRF login được bảo vệ | Render login form có token, dùng `csrf()` trong test phù hợp |
| POST hết session bị 403 | Token expected đã mất | Lấy token/session mới |
| Request GET làm thay đổi dữ liệu | Safe method matcher bỏ qua CSRF | Đổi sang POST/PUT/DELETE và dùng token |
| HTTP Basic đúng nhưng POST thiếu token bị 403 | Authentication không thay CSRF | Gửi token + session hợp lệ |
| Token bị ghi vào log/APM | Secrets/anti-CSRF leak | Redact `X-CSRF-TOKEN`, `_csrf`, cookies |
| Token API bị cache public | Rò token cho client khác | `Cache-Control: no-store`, CORS/cache policy |
| Test dùng `mockUser` và `csrf()` thành công nhưng GET token vẫn lỗi | Mock không test generation/saving lifecycle | Round-trip GET /csrf + same session + POST |
| Session bị thay khi đăng nhập/logout | Token quay vòng hoặc bị clear tùy flow | Refresh token sau thay đổi security state khi cần |

### 14.1. Quy trình phân tích lỗi trong dự án thật

1. Phân biệt 401 authentication và 403 CSRF/authorization. Đừng kết luận mọi 403 là thiếu role.
2. Kiểm tra URL GET cấp token và POST cần CSRF có match cùng cấu hình security không.
3. Kiểm tra attribute **`CsrfToken.class.getName()`**, **kiểu `Mono<CsrfToken>`**.
4. Kiểm tra có publisher được **subscribe thực sự** trong view/response không.
5. Xác nhận session cookie từ GET xuất hiện và POST gửi lại đúng session, còn hiệu lực.
6. Đặt đúng token theo `getHeaderName()` hoặc `getParameterName()`; không tự chuyển đổi masked/raw.
7. Kiểm tra form encoding, Content-Type, CORS preflight và cookie SameSite.
8. Nếu SPA dùng Cookie repo, xem request handler XOR/cookie raw có tương thích không.
9. Kiểm tra browser cache, session timeout, token rotation và nhiều application instances.
10. Gỡ debug logs chứa token/secret sau khi điều tra; không để token trong ticket/screenshot.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `CsrfWebFilter` đặt object `CsrfToken` hay `Mono<CsrfToken>` ở `ServerWebExchange`?  
**Đáp án:** Publisher `Mono<CsrfToken>`, dưới khóa `CsrfToken.class.getName()`.

**Câu 2.** Chỉ viết `Mono<CsrfToken> t = exchange.getAttribute(...)` đã bảo đảm token mới được tạo và lưu chưa?  
**Đáp án:** Chưa. Phải **consume/subscribe publisher** trong luồng cần token.

**Câu 3.** Trong WebFlux controller, nên dùng `t.block()`, `t.subscribe()` hay `return t.map(...)`?  
**Đáp án:** `return t.map(...)` hoặc compose publishers; không block/subscribe thủ công trong request path.

**Câu 4.** CSRF token dự kiến được lưu ở đâu theo mặc định của Spring Security WebFlux?  
**Đáp án:** `WebSession` nhờ `WebSessionServerCsrfTokenRepository`.

**Câu 5.** Vì sao hai token được expose từ hai GET có thể không giống nhau?  
**Đáp án:** Default XOR request handler mask token cho từng request để chống BREACH; expected raw token trong repository có thể vẫn là một giá trị ổn định.

**Câu 6.** Token ở session A có dùng được với cookie của session B không?  
**Đáp án:** Không. Expected token được ràng buộc với session theo repository.

**Câu 7.** User đã xác thực bằng Basic, POST không CSRF token nhận 403 có hợp lý không?  
**Đáp án:** Có. Basic kiểm tra danh tính, còn CSRF kiểm tra request unsafe có token hợp lệ. Hai bước khác nhau.

**Câu 8.** Nếu view technology không subscribe `Mono<CsrfToken>`, có thể dùng cách gì?  
**Đáp án:** Render từ publisher trực tiếp hoặc `@ControllerAdvice` + `@ModelAttribute` theo Spring Security, đảm bảo model token được subscribe trước khi render.

**Câu 9.** Có nên tạo CSRF token bắt buộc ở mọi GET `/public`?  
**Đáp án:** Không nhất thiết; nếu trang không cần form/unsafe request, việc tạo token/session không cần thiết có thể tăng tài nguyên.

**Câu 10.** Vì sao `XSRF-TOKEN` cookie copy sang `X-XSRF-TOKEN` header đôi khi không hợp với mặc định XOR handler?  
**Đáp án:** Cookie thường chứa token raw, handler XOR có thể kỳ vọng request token được mask. Cần request handler phù hợp với SPA và test tương thích.

**Câu 11.** `mutateWith(csrf())` có chứng minh endpoint GET tự tạo và lưu token đúng không?  
**Đáp án:** Không. Nó có thể cấp token hợp lệ vào request test, nhưng không kiểm tra vòng đời GET tạo token + session cookie. Cần round-trip integration test như mục 9.

**Câu 12.** CSRF token có chống được XSS không?  
**Đáp án:** Không. XSS trong cùng origin có thể đọc/sử dụng token; cần chống XSS, CSP khi phù hợp và hạn chế rò secret.

**Câu 13.** Chỉ cần CORS là đủ chống CSRF không?  
**Đáp án:** Không. Browser có thể gửi một số cross-origin form requests ngay cả khi script không đọc được response. CORS và CSRF là hai cơ chế khác nhau.

**Câu 14.** Khi token hết hiệu lực vì WebSession hết hạn, cách xử lý phù hợp là gì?  
**Đáp án:** Lấy token/session mới và cho người dùng thử lại; không disable CSRF để bỏ qua lỗi.

## 16. Checklist production và tài liệu tham khảo

- [ ] Dùng đúng **WebFlux** `CsrfToken`, `CsrfWebFilter`, `ServerWebExchange`.
- [ ] Đọc `Mono<CsrfToken>` qua `CsrfToken.class.getName()`, không nhầm với `_csrf`.
- [ ] Form/token endpoint **compose và return publisher** để subscription tạo/lưu token khi cần.
- [ ] Không gọi `block()`/`subscribe()` thủ công trong request path.
- [ ] Không tạo token vô ích cho mọi GET public.
- [ ] Biết repository nào đang dùng (WebSession/cookie/custom).
- [ ] Xử lý đúng **masked token** với XOR handler; không so raw string từ storage với token render.
- [ ] Form/JSON client gửi đúng parameter/header và cùng session cookie.
- [ ] Mọi endpoint unsafe được bảo vệ, HTTP safe methods không có side effects.
- [ ] Có `Cache-Control: no-store` và CORS/origin/caching policy trên nơi expose token.
- [ ] Cookie/session dùng Secure, HttpOnly, SameSite khi phù hợp; HTTPS/TLS cho production.
- [ ] Không log token, session cookie hoặc credentials; chống XSS.
- [ ] Multi-instance dùng session store nhất quán, test rotation/timeout/login/logout.
- [ ] Unit test lazy publisher và integration test **GET token → POST cùng session**.
- [ ] Không tắt CSRF chỉ vì test hoặc form trả 403.

**Tóm tắt:** Đọc `Mono<CsrfToken>` từ `ServerWebExchange` **chưa đủ**; ở Spring Security WebFlux, điều kiện quyết định để token mới được tạo và lưu là **publisher phải được subscribe trong luồng phản hồi cần token**. Return `Mono` từ controller/template, để WebFlux quản lý subscription; sau đó client gửi giá trị token đã expose với đúng session, header/form field và cơ chế request handler.

**Tài liệu chính thức:**

- Spring Security 6.5 – CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 – `CsrfWebFilter` API (new token saved on subscription): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html
- Spring Security 6.5 – `ServerCsrfTokenRepository` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html
- Spring Security 6.5 – `WebSessionServerCsrfTokenRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html
- Spring Security 6.5 – `XorServerCsrfTokenRequestAttributeHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security 6.5 – Testing with CSRF in WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot 3.5 – Testing a running server with WebTestClient: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- OWASP – Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
