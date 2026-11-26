# Token truyền qua trường form hoặc HTTP header

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Giải thích vì sao một yêu cầu thay đổi trạng thái cần truyền **CSRF token do client chủ động gửi** ngoài cookie xác thực được trình duyệt tự gắn.
- Chọn giữa **hidden field trong form HTML** và **HTTP header** cho các tình huống submit form truyền thống, `fetch`, Ajax và API nhận JSON.
- Xác định đúng **tên tham số, tên header, giá trị token** theo cấu hình `CsrfToken`, repository và request handler của Spring Security.
- Hiểu đường đi của token từ server đến client rồi quay về `CsrfFilter` hoặc `CsrfWebFilter`, bao gồm trường hợp **token gốc** và **token được che (masked/XOR)**.
- Viết và kiểm tra cấu hình **Servlet** lẫn **Reactive/WebFlux**, đồng thời xử lý các tình huống sai token, sai phiên, thiếu header, phiên hết hạn hoặc cấu hình CORS không phù hợp.
- Kiểm thử cả hai đường truyền, từ request hợp lệ đến request giả mạo, và phân biệt lỗi CSRF với lỗi phân quyền/xác thực.

## 1. Vì sao phải đưa token vào request qua một kênh chủ động?

Ứng dụng web thường dựa vào cookie session hoặc cookie chứa thông tin xác thực. Khi trình duyệt phát sinh request tới đúng máy chủ, nó có thể **tự gắn cookie** theo các thuộc tính `Domain`, `Path`, `Secure`, `SameSite` và chính sách trình duyệt. Điều đó giúp server xác định phiên, nhưng chưa chứng minh người dùng đã chủ động gửi thao tác từ giao diện hợp lệ.

Ví dụ một trang ngoài có thể tạo form POST:

~~~html
<form action="https://app.example.com/profile/email" method="post">
  <input type="hidden" name="email" value="attacker@example.test">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Nếu request mang cookie phiên của nạn nhân và server chỉ kiểm tra phiên, hành động có thể được thực hiện như thể do nạn nhân gửi.

**CSRF token** là một bằng chứng bổ sung. Trang hợp lệ lấy token được server phát hành và **chủ động đưa token vào trường form hoặc header**. Trang tấn công bên ngoài thường không đọc được token trong nội dung ứng dụng đích vì Same-Origin Policy, cũng không thể bắt trình duyệt tự tạo một header tùy chỉnh chứa token hợp lệ bằng một form HTML thông thường.

> **Hai kênh khác nhau:** Cookie xác thực được browser tự đính kèm để nhận diện phiên. CSRF token được form hoặc mã ứng dụng chủ động gửi để chứng minh request đáp ứng chính sách chống CSRF của server.

Dù truyền token qua cách nào, máy chủ phải **kiểm tra nó theo đúng ngữ cảnh**. Chỉ nhìn thấy tên `_csrf` hoặc một header `X-CSRF-TOKEN` không phải bằng chứng rằng token hợp lệ.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, CSRF là một lớp phòng vệ HTTP và trình duyệt đi cùng CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session. Việc chọn kênh truyền token phải xét cả ứng dụng **Spring Security Servlet** lẫn **Reactive/WebFlux**.

## 2. Sơ đồ một request được bảo vệ CSRF

Một form hợp lệ và một client gọi API đều phải đi qua hai giai đoạn: **nhận token từ ứng dụng** và **gửi lại token trong request thay đổi trạng thái**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser / client hợp lệ
    participant S as Spring Security
    participant R as CSRF token repository
    participant C as Controller / handler

    U->>B: Mở trang chỉnh sửa
    B->>S: GET /profile/edit
    S->>R: Tải hoặc sinh expected token khi cần
    R-->>S: Token gắn với ngữ cảnh request
    S-->>B: HTML / dữ liệu chứa token để dùng
    U->>B: Submit form hoặc kích hoạt Ajax
    alt Form HTML
        B->>S: POST + cookie xác thực + form _csrf=...
    else Ajax / JSON
        B->>S: POST + cookie xác thực + header X-CSRF-TOKEN: ...
    end
    S->>R: Lấy expected token cho ngữ cảnh hiện tại
    S->>S: Resolve submitted token, đối chiếu expected
    alt Token hợp lệ
        S->>C: Tiếp tục kiểm tra quyền và xử lý
        C-->>B: Kết quả nghiệp vụ
    else Thiếu hoặc sai token
        S-->>B: Từ chối, thường 403
    end
~~~

Tùy cấu hình, **expected token** có thể được lưu trong `HttpSession`/`WebSession` hoặc được repository tải từ cookie CSRF theo mô hình double-submit. Token client gửi phải phù hợp **repository, request handler và phiên/ngữ cảnh hiện tại**. Đối chiếu chuỗi đơn thuần chỉ đầy đủ khi chính sách token thực tế cho phép.

### 2.1. Tên tham số và tên header không phải lúc nào cũng giống nhau

Một đối tượng `CsrfToken` của Spring Security cung cấp thông tin:

| Thuộc tính/method | Ý nghĩa | Ví dụ thường gặp |
|---|---|---|
| `getParameterName()` | Tên trường form để gửi token | `_csrf` |
| `getHeaderName()` | Tên header server dự kiến đọc | `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` |
| `getToken()` | Giá trị token mà client cần đưa vào request theo handler | Chuỗi khó đoán, có thể ở dạng masked |
| Token lưu bởi repository | Giá trị kỳ vọng để kiểm tra | Có thể là raw token khác biểu diễn trong HTML |

Ví dụ với `HttpSessionCsrfTokenRepository`, tên mặc định thường là **`_csrf`** và **`X-CSRF-TOKEN`**. Với `CookieCsrfTokenRepository`, header mặc định thường là **`X-XSRF-TOKEN`** và cookie thường là **`XSRF-TOKEN`**. Tên có thể được tùy chỉnh; hãy dùng giá trị thật từ cấu hình hoặc từ `CsrfToken`.

Cần phân biệt **cookie có tên `XSRF-TOKEN`** với **header `X-XSRF-TOKEN`**: đây là hai vị trí truyền khác nhau, dù tên gợi nhớ tương tự.

## 3. Truyền token qua hidden field của form HTML

### 3.1. Form truyền thống

Cách phổ biến nhất khi gửi form server-rendered là trường ẩn:

~~~html
<form action="/profile/email" method="post">
  <label for="new-email">Email mới</label>
  <input id="new-email" name="email" type="email" required>

  <input type="hidden" name="_csrf" value="SERVER_ISSUED_TOKEN">

  <button type="submit">Lưu thay đổi</button>
</form>
~~~

Ở đây `SERVER_ISSUED_TOKEN` chỉ là ký hiệu minh họa, **không phải một hằng số có thể sử dụng**. Server phải cấp giá trị thực cho request và render vào form. Khi submit, trình duyệt tạo một request tương tự:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=alice%40example.test&_csrf=SERVER_ISSUED_TOKEN
~~~

Cookie `JSESSIONID` có thể do browser tự đính kèm. Trường `_csrf` xuất hiện vì **trang hợp lệ đã đặt nó vào form**. Khi bảo vệ CSRF hoạt động, request thiếu hoặc sai `_csrf` sẽ bị chặn ngay cả khi cookie phiên vẫn hợp lệ.

### 3.2. Gắn token qua Spring MVC + Thymeleaf

Một template Thymeleaf có thể lấy tên parameter và giá trị token từ request attribute `_csrf` do Spring Security cung cấp:

~~~html
<!-- templates/profile/edit.html -->
<form action="/profile/email" method="post">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Cập nhật</button>
</form>
~~~

Sau khi Thymeleaf render, thuộc tính `th:name`/`th:value` được thay bằng tên và token thật.

Với các tích hợp Spring MVC/Thymeleaf, sử dụng `th:action` có thể kích hoạt cơ chế tự thêm hidden CSRF field qua tích hợp form của framework. Vì vậy cần **kiểm tra HTML cuối cùng** để tránh chèn hai trường `_csrf` trùng nhau không cần thiết. Đoạn trên dùng `action` tĩnh để thấy rõ cách truyền token thủ công.

Nếu viết ứng dụng dùng JSP, template engine khác hoặc form HTML tự sinh, nguyên tắc vẫn là: server cần **render token thực** vào form, không gắn một chuỗi cố định.

### 3.3. Form tải động và nhiều form trên một trang

Một trang có thể có nhiều form POST/PATCH/DELETE. Mỗi request được bảo vệ cần mang token hợp lệ theo cấu hình. Nếu repository dùng **token gốc theo phiên**, nhiều form trong cùng session thường có thể dùng chung expected token; biểu diễn masked trong HTML có thể khác nhau giữa các lần render.

Nếu ứng dụng thay token khi đăng nhập/đăng xuất, các form mở trước đó có thể chứa token cũ. Người dùng cần tải lại form hoặc nhận token mới. Không nên cố “sửa” lỗi bằng cách bỏ kiểm tra CSRF trên toàn ứng dụng.

### 3.4. Form upload `multipart/form-data`

Một form tải tệp vẫn có thể mang CSRF token qua hidden field:

~~~html
<form action="/documents/upload" method="post"
      enctype="multipart/form-data">
  <input type="file" name="file" required>
  <input type="hidden" name="_csrf" value="SERVER_ISSUED_TOKEN">
  <button type="submit">Tải lên</button>
</form>
~~~

Đặc điểm cần chú ý ở **Servlet**: để đọc được hidden field của multipart request, hệ thống có thể cần xử lý multipart trước `CsrfFilter`. Nếu multipart parser xử lý trước lớp CSRF, server có thể tốn tài nguyên hoặc tạo dữ liệu tạm cho một request sau đó bị chặn. Nếu xử lý sau, filter có thể chưa đọc được form parameter như mong đợi. Đây là đánh đổi về thứ tự filter/parser và việc tải tệp tạm.

Với luồng upload từ JavaScript, đưa CSRF token vào **header** là một cách tránh phụ thuộc vào việc filter phải parse body multipart để đọc hidden field. Không tự đặt `Content-Type: multipart/form-data` với boundary thiếu chính xác khi dùng `FormData` và `fetch`; để trình duyệt tạo boundary.

## 4. Truyền token qua HTTP header trong Ajax và API JSON

### 4.1. Vì sao API JSON thường dùng header?

Form parameter chuẩn được lấy từ form body, còn một JSON request như:

~~~http
POST /api/profile HTTP/1.1
Content-Type: application/json

{"email":"alice@example.test","_csrf":"something"}
~~~

**không bảo đảm** `CsrfFilter` hoặc `CsrfWebFilter` tự tìm và đọc field `"_csrf"` bên trong JSON. Nếu client gửi JSON, lựa chọn rõ ràng là đặt token vào **header mà request handler dự kiến đọc**:

~~~http
POST /api/profile HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json
X-CSRF-TOKEN: SERVER_ISSUED_TOKEN

{"email":"alice@example.test"}
~~~

Token nằm trong header là **submitted token**. Cookie xác thực có vai trò nhận diện ngữ cảnh đăng nhập và có thể là đường gửi tự động.

### 4.2. Render token thành meta tag cho JavaScript

Với HTML server-rendered, ứng dụng có thể cung cấp token và tên header qua meta tag:

~~~html
<head>
  <meta name="_csrf" th:content="${_csrf.token}">
  <meta name="_csrf_header" th:content="${_csrf.headerName}">
</head>
~~~

JavaScript đọc hai meta tag rồi gửi POST:

~~~javascript
const tokenElement = document.querySelector('meta[name="_csrf"]');
const headerElement = document.querySelector('meta[name="_csrf_header"]');

if (!tokenElement?.content || !headerElement?.content) {
  throw new Error("Trang chưa có CSRF token hợp lệ");
}

const response = await fetch("/api/profile", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    [headerElement.content]: tokenElement.content,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ displayName: "Alice" })
});

if (!response.ok) {
  throw new Error("Cập nhật thất bại: HTTP " + response.status);
}
~~~

Hai meta tag phải được render bằng giá trị thật từ `CsrfToken`. Khi dùng `fetch` với URL cùng origin, `credentials: "same-origin"` cũng là mặc định thường gặp, nhưng ghi rõ để dễ hiểu vì sao cookie phiên được gửi. Header CSRF được **mã ứng dụng đặt chủ động**, khác với cookie.

Nếu frontend là một SPA tĩnh không có server-rendered HTML, phải xây một luồng **lấy token an toàn** riêng hoặc dùng repository cookie phù hợp. Không tự giả định rằng một file `index.html` tĩnh sẽ có sẵn `_csrf`.

### 4.3. Khi submit form bằng fetch

Một form HTML đã chứa hidden token có thể được gửi bằng `FormData`, token vẫn ở trong body:

~~~javascript
const form = document.querySelector("#profile-form");
form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const response = await fetch(form.action, {
    method: "POST",
    credentials: "same-origin",
    body: new FormData(form)
  });

  if (!response.ok) {
    throw new Error("Không gửi được form");
  }
});
~~~

Với cách này, browser đưa các trường form (bao gồm hidden `_csrf`) vào request body. **Không cần tạo thêm CSRF header** nếu Spring Security đã nhận form parameter đúng định dạng và token đúng phiên. Ngược lại, khi chuyển sang `JSON.stringify(...)`, hidden field không tự đi cùng body; nên gửi token qua header.

### 4.4. Lỗi thường gặp khi dùng header

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Token hiển thị trên trang nhưng POST trả `403` | JavaScript không đưa header vào request | Mở DevTools → Network → Request Headers |
| Header có token nhưng vẫn `403` | Sai tên header hoặc token hết hạn/sai phiên | Đối chiếu `_csrf.headerName`, token repository và phiên |
| JSON có `_csrf` nhưng vẫn bị từ chối | Handler không lấy token từ JSON body | Chuyển token sang header được hỗ trợ |
| Cùng token hoạt động qua form nhưng không qua SPA | Header chứa raw token còn handler mong đợi masked token, hoặc ngược lại | Kiểm tra handler và dạng token gửi thực tế |
| Chỉ lỗi khi gọi API khác origin | CORS preflight, cookie `SameSite` hoặc `credentials` | Tách riêng lỗi trình duyệt không gửi request với lỗi server `403` |
| Lỗi đầu tiên sau login | Token cũ bị vô hiệu hóa khi xác thực | Tải token mới và cập nhật state phía client |

## 5. Token được truyền đến Spring Security bằng cách nào?

### 5.1. Nguồn token dự kiến

Cần phân biệt rõ hai giá trị:

- **Expected token:** repository cung cấp từ phiên hoặc nguồn tin cậy.
- **Submitted token:** request handler đọc từ field/header của HTTP request.

Ví dụ synchronizer token:

~~~text
Session A:
    expected = T_A

POST /transfer
    Cookie: JSESSIONID=SESSION_A
    Header X-CSRF-TOKEN: T_A

--> submitted == expected của Session A: qua bước CSRF
~~~

Nếu cùng request gửi `T_B` của session B thì phải bị từ chối. Việc server từng phát hành `T_B` cho người dùng khác không khiến token đó hợp lệ với session A.

### 5.2. Request handler chịu trách nhiệm giải quyết giá trị client gửi

Trong Spring Security Servlet, `CsrfTokenRequestHandler` chịu trách nhiệm đưa token vào request attribute và xác định submitted token từ request. Các handler có thể khác nhau về cách nhận token:

- Handler thường có thể đọc token **raw** theo tên header/parameter.
- `XorCsrfTokenRequestAttributeHandler` có thể che token khi render form và giải mã biểu diễn đã che khi nhận lại.

Vì vậy, nếu trình duyệt gửi `_csrf=M1` được render từ HTML, server có thể cần **bỏ mask M1 trước khi so với token gốc R**. Giá trị trong form không nhất thiết phải trùng văn bản với chuỗi raw ở session.

Minh họa:

~~~text
Repository lưu expected raw token: R

Lần render 1: token trong HTML = xorMask(R, random_1) = M1
Lần render 2: token trong HTML = xorMask(R, random_2) = M2

POST với M1 hoặc M2:
    request handler giải mã --> R
    filter so sánh với expected R
~~~

Lưu ý: đây là **masking biểu diễn** nhằm hỗ trợ phòng vệ trước kênh rò rỉ như BREACH; nó không có nghĩa server tự tạo token gốc mới ở mỗi GET. Cũng không nên nhầm XOR masking với **HMAC signing**, vốn là một thiết kế xác minh tính toàn vẹn/ràng buộc phiên khác.

### 5.3. Thứ tự đối chiếu khái niệm

~~~mermaid
flowchart TD
    A[Request đến ứng dụng] --> B{Request thuộc phạm vi kiểm tra CSRF?}
    B -- Không --> G[Tiếp tục security chain]
    B -- Có --> C[Repository tải expected token cho ngữ cảnh request]
    C --> D[Handler đọc submitted từ form/header]
    D --> E[Giải mã biểu diễn nếu được cấu hình]
    E --> F{Expected và submitted hợp lệ, khớp nhau?}
    F -- Không --> X[Từ chối, thường HTTP 403]
    F -- Có --> G
    G --> H[Authentication, authorization, validation, nghiệp vụ]
~~~

Trong Spring Security, thứ tự thực thi chi tiết của các filter có thể ảnh hưởng mã phản hồi và cách xác thực. Sơ đồ mô tả **điều kiện kiểm chứng**; không suy ra rằng mọi lỗi `403` đều do CSRF.

### 5.4. Form hay header: so sánh nhanh

| Tiêu chí | Hidden field `_csrf` | HTTP header CSRF |
|---|---|---|
| Phù hợp nhất | Form HTML submit truyền thống | Ajax, SPA, JSON API |
| Ai đưa token vào request? | HTML form đã render | JavaScript hoặc HTTP client hợp lệ |
| Ví dụ | `_csrf=TOKEN` trong form body | `X-CSRF-TOKEN: TOKEN` |
| Với JSON | Không được tự động đọc từ JSON body | Thường là cách rõ ràng để gửi token |
| Với multipart | Có thể cần parser xử lý form field | Tránh phụ thuộc vào việc đọc multipart field trong filter |
| Với CORS | Form đơn giản có thể gửi cross-site không cần preflight | Header tùy chỉnh trong JS cross-origin thường phát sinh preflight |
| Lưu ý | Phải render token thật, không bị trùng/sai tên | Đúng header name, token format, refresh token khi cần |

Một ứng dụng có thể hỗ trợ **cả hai** kênh. Điều quan trọng là token hợp lệ và được kiểm chứng đúng chính sách, không phải luôn bắt buộc có đồng thời form parameter lẫn header.

## 6. Spring Security Servlet: ví dụ triển khai

### 6.1. Cấu hình session-based CSRF

Với Spring MVC và cookie phiên, `HttpSessionCsrfTokenRepository` lưu expected token trong `HttpSession`. `CsrfFilter` kiểm tra token khi request thuộc phạm vi áp dụng; thông thường CSRF được bật mặc định trong cấu hình web Spring Security.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
            .build();
    }
}
~~~

Repository này làm rõ nguồn expected token là phiên server. Nếu không có yêu cầu tùy chỉnh, ứng dụng có thể dùng cấu hình CSRF mặc định tương ứng.

Controller minh họa:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;

@Controller
class ProfileController {

    @GetMapping("/profile/edit")
    String form() {
        return "profile/edit";
    }

    @PostMapping("/profile/email")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void update(@RequestParam String email) {
        // Service thật cần xác định user hiện tại, kiểm tra quyền,
        // validate email và cập nhật dữ liệu.
    }
}
~~~

Khi request POST qua security chain, controller **không cần tự đọc và kiểm tra** `_csrf`. Nếu token thiếu hoặc sai, `CsrfFilter` chặn trước khi controller chạy.

### 6.2. Chọn cách truyền theo loại client

Với **form MVC**: sử dụng hidden field `_csrf`, được render từ request attribute.

Với **JavaScript gọi API MVC**: sử dụng header lấy từ `_csrf.headerName`. Một header `X-CSRF-TOKEN` gửi token hợp lệ sẽ cho phép request vượt bước CSRF ngay cả khi request body chứa JSON. Endpoint và content type phải được triển khai phù hợp.

Không nhầm `POST` chỉ gửi form với `GET` chỉ đọc. Mặc định Spring Security thường bỏ qua CSRF token cho `GET`, `HEAD`, `OPTIONS` và `TRACE`; thao tác làm thay đổi trạng thái phải dùng phương thức HTTP thích hợp.

### 6.3. Dùng CookieCsrfTokenRepository cho SPA: raw token và XOR handler

Đối với SPA, ứng dụng có thể chọn `CookieCsrfTokenRepository` để frontend cùng origin đọc cookie `XSRF-TOKEN` và gửi token trong header `X-XSRF-TOKEN`.

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Ví dụ repository cho SPA đọc token bằng JavaScript.
CookieCsrfTokenRepository repository =
        CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Đây là **cookie-based token repository**, không tự triển khai biến thể **signed double-submit HMAC ràng buộc phiên**. Nếu dùng repository cookie, cần đánh giá cookie injection, phạm vi cookie và mô hình đe dọa tương ứng. Cookie **xác thực** và cookie **CSRF** có vai trò khác nhau; thường chỉ cookie CSRF cần đọc từ JavaScript.

Ở các phiên bản Spring Security Servlet có `XorCsrfTokenRequestAttributeHandler` mặc định, **token raw đọc từ cookie** và gửi qua header có thể không tương thích cách handler giải mã token masked của form. Có thể dùng handler tùy chỉnh để:

- Vẫn dùng XOR/masking cho token xuất ra HTML/form.
- Đọc **raw token** từ header của SPA.
- Bảo đảm token cookie được tải/phát cho client khi cần.

Ví dụ một handler ứng dụng minh họa cách phân nhánh này:

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
        csrfToken.get(); // Buộc tải token để repository có thể phát cookie.
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request, CsrfToken csrfToken) {

        boolean hasHeader = StringUtils.hasText(
                request.getHeader(csrfToken.getHeaderName()));

        return (hasHeader ? plain : xor)
                .resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Gắn vào security chain, **thay cho** cấu hình `.csrf(...)` trước đó:

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
~~~

Đây là lớp **tự định nghĩa** (`SpaCsrfTokenRequestHandler`), không phải API class có sẵn. Cần kiểm tra phiên bản Spring Security, cookie scope, phát lại token sau đăng nhập/đăng xuất và khả năng XSS. Nếu ứng dụng chỉ dùng form MVC với session repository, không nhất thiết phải dùng handler SPA này.

### 6.4. Frontend gửi raw token đọc từ cookie

Với cơ chế cookie repository ở trên, token raw có thể lấy từ cookie cùng origin:

~~~javascript
function cookieValue(name) {
  const encodedName = encodeURIComponent(name) + "=";
  const entry = document.cookie
      .split("; ")
      .find(part => part.startsWith(encodedName));

  return entry
      ? decodeURIComponent(entry.substring(encodedName.length))
      : null;
}

const token = cookieValue("XSRF-TOKEN");
if (!token) {
  throw new Error("Chưa nhận CSRF cookie; cần lấy token mới");
}

await fetch("/api/preferences", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-XSRF-TOKEN": token
  },
  body: JSON.stringify({ theme: "dark" })
});
~~~

Server phải thực sự cấp cookie trước khi JavaScript đọc nó, ví dụ thông qua một endpoint tải token hoặc render trang có truy xuất token. Với **deferred CSRF token**, việc GET bất kỳ không đảm bảo cookie đã được phát; kiểm tra `Set-Cookie` thực tế. Sau login/logout, CSRF token cũ có thể bị vô hiệu hóa và SPA phải nhận token mới.

## 7. Spring Security Reactive/WebFlux: form và header

Trên Reactive, `CsrfWebFilter` giữ vai trò bảo vệ request; `ServerCsrfTokenRepository` chịu trách nhiệm sinh/lưu/tải token. Với web app dùng `WebSession`, repository theo phiên là `WebSessionServerCsrfTokenRepository`.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/assets/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

Ở WebFlux, token có thể được cung cấp dưới dạng `Mono<CsrfToken>` trong exchange attribute để view engine render. Ví dụ:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveProfilePageController {

    @GetMapping("/profile/edit")
    Mono<Rendering> form(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf = exchange.getAttribute(
                CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("profile/edit")
                .modelAttribute("_csrf", token)
                .build());
    }
}
~~~

Ví dụ giả định request đi qua `CsrfWebFilter` nên attribute chứa `Mono<CsrfToken>`. Việc giải quyết `Mono` để render giúp token được tải/sinh khi cần. Tùy phiên bản và tích hợp template, view có thể nhận token theo cơ chế tự động; cần kiểm tra request thật thay vì tự phát token trong controller.

Khi gửi form, WebFlux tiếp nhận submitted token từ form parameter theo cấu hình; khi dùng `fetch`/JSON, dùng header theo repository/handler đang áp dụng. Các điểm quan trọng giữ nguyên giữa hai stack:

1. **Đúng tên** form parameter hoặc header.
2. **Đúng giá trị và biểu diễn** token mà request handler dự kiến.
3. **Đúng ngữ cảnh** (phiên, cookie repository hoặc xác minh ký nếu triển khai).
4. **Request đi qua security web filter chain**.

WebFlux cũng hỗ trợ `CookieServerCsrfTokenRepository` nếu cần token dựa trên cookie cho SPA. Repository cookie thông thường không tự trở thành signed double-submit; nếu dùng token raw từ cookie, phải kiểm tra request handler được phiên bản Spring Security hiện tại cấu hình phù hợp.

## 8. SameSite, CORS và kênh header: hiểu đúng ranh giới

### 8.1. Cross-origin không đồng nghĩa cross-site

`https://ui.example.com` và `https://api.example.com` là **hai origin khác nhau**, nhưng có thể thuộc **cùng site** theo cách phân loại dựa trên scheme và registrable domain. Cookie `SameSite=Lax`/`Strict` không nhất thiết bị loại chỉ vì request đi giữa hai subdomain cùng site.

Nếu frontend và API khác origin, client phải xem cả CORS và cookie:

~~~javascript
await fetch("https://api.example.com/profile", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": token
  },
  body: JSON.stringify({ displayName: "Alice" })
});
~~~

Đây là ví dụ cho **client đã có token hợp lệ**. `credentials: "include"` cho phép trình duyệt cân nhắc gửi credential trong cross-origin request nhưng **không vô hiệu hóa** `SameSite`, `Secure` hoặc chính sách chặn cookie bên thứ ba.

Một request JavaScript cross-origin mang header tùy chỉnh thường **cần CORS preflight**. Server phải cấu hình origin, phương thức, header và credentials phù hợp. Không dùng `Access-Control-Allow-Origin: *` cho credentialed CORS response. Việc preflight thất bại khác với việc POST đến server nhưng bị `403` do CSRF.

### 8.2. Vì sao chỉ dựa vào CORS vẫn không đủ?

CORS chủ yếu quản lý việc JavaScript ở origin khác được đọc phản hồi và kiểm soát một số request cần preflight. HTML form đơn giản có thể kích hoạt POST cross-site **không cần preflight**; nếu cookie được gửi và server không bảo vệ, thao tác vẫn có thể xảy ra dù trang ngoài không đọc được phản hồi.

Vì thế, giữ **kiểm tra token** cho những request thay đổi trạng thái dùng credential tự gửi. Cookie `SameSite` là lớp hỗ trợ nhưng không thay thế đầy đủ CSRF token, nhất là khi có các luồng same-site cross-origin hoặc endpoint GET sai thiết kế.

### 8.3. Header có thực sự chặn được trang tấn công?

Một form HTML ngoài origin không thể tự đặt header tùy chỉnh `X-CSRF-TOKEN`. Với JavaScript ở origin ngoài, yêu cầu có header đó thường bị ràng buộc preflight. Tuy nhiên, nếu cấu hình CORS quá rộng hoặc một thành phần bị XSS trong origin đích, attacker có thể tìm thêm đường tác động. **Header chỉ là kênh truyền**, còn token phải đủ khó đoán và được server xác minh đúng.

## 9. Vòng đời token ảnh hưởng đến form và header

### 9.1. Khi token được phát hành trì hoãn

Các phiên bản Spring Security hiện đại có thể **defer** việc tải/sinh token đến khi một form hoặc handler thực sự truy cập. Nếu SPA đợi cookie `XSRF-TOKEN` nhưng chỉ tải một tài nguyên tĩnh, cookie có thể chưa tồn tại. Cần chủ động khởi tạo luồng cấp token phù hợp với repository đang dùng.

### 9.2. Sau đăng nhập hoặc đăng xuất

Token có thể bị xóa hoặc thay ở ranh giới xác thực; một form đang mở hoặc SPA giữ token trong memory có thể tiếp tục gửi token cũ.

Cần làm mới token khi luồng xác thực chuyển trạng thái. Không nên tắt CSRF toàn cục để làm request cũ “chạy được”. Đối với luồng login/logout, cũng cần xem xét CSRF vì các endpoint xác thực có thể bị lạm dụng.

### 9.3. Session hết hạn hoặc thay đổi giữa các tab

Khi session hết hạn, expected token của phiên cũ không còn hợp lệ. Form cũ phải được tải lại hoặc client nhận token mới khi đã có phiên thích hợp. Nếu mỗi tab dùng cùng session, token gốc thường có thể dùng lại theo chính sách per-session; nếu ứng dụng chủ động luân phiên token gốc, cần xử lý cạnh tranh giữa các tab và nhiều request đồng thời.

### 9.4. Nhiều instance

Nếu expected token nằm trong `HttpSession`/`WebSession`, các instance xử lý cùng phiên cần truy cập trạng thái nhất quán. Nếu GET form qua node A nhưng POST qua node B không thấy expected token, request có thể bị từ chối. Xem lại session store hoặc định tuyến, không miễn CSRF vì lỗi đồng bộ.

## 10. Kiểm thử đường form và header

### 10.1. Ma trận ca kiểm thử

| Request | Token qua form | Token qua header | Kỳ vọng |
|---|---|---|---|
| POST form hợp lệ | Token của phiên hiện tại | Không cần | Qua kiểm tra CSRF |
| POST JSON hợp lệ | Không cần | Token của phiên hiện tại | Qua kiểm tra CSRF |
| POST thiếu token | Không | Không | Bị từ chối |
| POST form sai token | Token sai | Không | Bị từ chối |
| POST header sai token | Không | Token sai | Bị từ chối |
| POST token phiên B đi cùng cookie phiên A | Token B | Hoặc token B | Bị từ chối nếu expected lưu theo phiên |
| POST có token đúng nhưng user thiếu quyền | Đúng | Hoặc đúng | Có thể qua CSRF nhưng vẫn bị từ chối bởi authorization |
| GET chỉ đọc | Không | Không | Thường không bị yêu cầu CSRF token |
| POST từ trang ngoài với cookie tự gửi | Không có token hợp lệ | Không có token hợp lệ | Bị từ chối |

Khi một request có **cả form token và header**, hành vi chọn nguồn phụ thuộc request handler. Không nên cố gửi cả hai khi không cần thiết; hãy dùng một kênh đúng theo cơ chế client.

### 10.2. Spring Security Test cho Servlet: kiểm thử riêng form và header

Với endpoint `POST /profile/email` nhận form data và trả `204 No Content` khi thành công, `MockMvc` có thể kiểm tra hai đường truyền:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfTransportTests {

    @Autowired
    MockMvc mvc;

    @Test
    void formFieldTokenIsAccepted() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf())
                .param("email", "new@example.test"))
            .andExpect(status().isNoContent());
    }

    @Test
    void headerTokenIsAccepted() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().asHeader())
                .param("email", "new@example.test"))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidHeaderTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().asHeader().useInvalidToken())
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }
}
~~~

Các helper `csrf()` và `csrf().asHeader()` giúp tạo request test có token phù hợp theo dạng parameter hoặc header; chúng không yêu cầu test tự đọc token từ HTML. Test giả định có controller `204`, security filter chain hoạt động và user mock có quyền. Với repository/handler tùy biến, cần test bổ sung luồng token thực, không coi helper là bằng chứng mọi đường trình duyệt đều đúng.

Để kiểm chứng session binding, thiết lập **hai session thật** A/B, lấy token từ form của từng phiên rồi gửi token A cùng cookie phiên B. Đường token theo phiên phải từ chối phép hoán đổi đó.

### 10.3. Spring Security Test cho Reactive

Với `WebTestClient` được liên kết với Spring Security web filter chain:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveCsrfTransportTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void postWithoutTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void postWithValidTokenReachesHandler() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isNoContent();
    }
}
~~~

Ví dụ giả định API WebFlux có endpoint trả `204`, xử lý request body phù hợp và mock user được phép. `csrf()` ở đây xác minh cấu hình bảo vệ ở mức framework. Muốn kiểm tra chính xác **form parameter** so với **header**, hãy viết thêm kiểm thử HTTP tích hợp: tải token và session thật qua GET, gửi POST cùng cookie với từng kênh, quan sát request/response; không suy luận kênh truyền từ tên helper.

### 10.4. Kiểm tra trên DevTools và công cụ HTTP

Trong môi trường được phép:

1. Mở form HTML, xác nhận hidden `_csrf` tồn tại trong HTML **sau khi render**, có giá trị không rỗng.
2. Submit form và xem Network → Request Payload/Form Data có trường `_csrf` theo tên đúng.
3. Với SPA, xem Request Headers có `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` đúng cấu hình hay không.
4. Xóa token trong field/header rồi thử POST; thao tác không được hoàn thành.
5. Sửa token hoặc dùng token từ phiên khác; request phải bị từ chối khi repository ràng buộc phiên.
6. Đăng xuất/đăng nhập lại rồi gửi token cũ; xác minh quy tắc vòng đời token.
7. Với request cross-origin, tách biệt **preflight CORS bị chặn**, **cookie không được gửi** và **POST đến server nhưng token sai**.

Công cụ cURL/Postman có thể tự gắn cookie và header, hữu ích để thử logic server. Tuy nhiên, một HTTP client tự chọn header `Cookie` **không chứng minh** browser nạn nhân sẽ gửi cookie đó trong một yêu cầu cross-site. Cần đối chiếu với trình duyệt thật và chính sách cookie.

## 11. Chẩn đoán HTTP 403 và những nhầm lẫn thường gặp

| Hiện tượng | Câu hỏi cần đặt | Hướng xử lý |
|---|---|---|
| Form nhìn đúng nhưng POST `403` | Token có nằm trong HTML cuối cùng, đúng tên `_csrf`, đúng phiên không? | Kiểm tra template, filter, token repository và request thực tế |
| SPA gửi header mà vẫn `403` | Header name và định dạng raw/masked có khớp request handler không? | Điều chỉnh kênh token/handler theo cấu hình đang dùng |
| CORS báo lỗi trong browser | Preflight được gửi và phản hồi ra sao? | Sửa CORS cho origin/phương thức/header hợp lệ, giữ CSRF |
| Lỗi ngay sau login/logout | Token cũ có bị invalidated không? | Cấp và nhận token mới sau chuyển trạng thái |
| Lỗi chỉ với multipart | Form parameter có được parser cung cấp đúng lúc CsrfFilter kiểm tra không? | Rà soát thứ tự xử lý multipart; cân nhắc header trong upload bằng JS |
| Lỗi trên một vài node | Expected token có được lưu/truy xuất nhất quán không? | Kiểm tra session store và định tuyến |
| Header có giá trị nhưng token bị reject | Token từ phiên khác hoặc token trong cookie bị tiêm? | Kiểm tra nơi lưu expected, binding, signature/cookie scope |
| Tất cả POST chạy khi tắt CSRF | Có thể client đang không gửi token đúng | Khắc phục đường phát/đọc token, không vô hiệu hóa rộng |
| Có token hợp lệ nhưng vẫn `403` | Tầng authorization hoặc cơ chế khác có chặn không? | Xem security chain, failure handler và kết quả nghiệp vụ |

Trong Servlet có thể gặp `MissingCsrfTokenException` hoặc `InvalidCsrfTokenException`; với WebFlux cần xem nhánh xử lý của `CsrfWebFilter`. Không log đầy đủ CSRF token hoặc session ID vào hệ thống quan sát. Các dữ kiện an toàn hơn là **có/không header**, tên nguồn token, token đã hết hạn chưa và bộ lọc nào đưa ra quyết định.

## 12. Tự kiểm tra qua tình huống

**Tình huống A — form có cookie nhưng thiếu field.** Người dùng đã đăng nhập, form POST gửi `JSESSIONID` hợp lệ nhưng không có `_csrf`. **Kết luận:** request phải bị từ chối nếu nằm trong phạm vi kiểm tra CSRF; cookie xác thực không thay thế submitted token.

**Tình huống B — JSON gửi field `"_csrf"`.** SPA gửi token như một thuộc tính trong JSON, không có header, và server dùng request handler mặc định. **Kết luận:** không nên mặc định Spring Security sẽ đọc thuộc tính JSON đó; nên dùng header CSRF đúng cấu hình.

**Tình huống C — cùng phiên, token form thay đổi sau refresh.** Hai lần render form cho hai chuỗi khác nhau nhưng cả hai request đều hợp lệ. **Kết luận:** token có thể được XOR/mask lại mỗi lần hiển thị; không chứng minh raw token gốc đổi sau từng GET.

**Tình huống D — token header của phiên khác.** Header mang token của phiên B, cookie xác thực thuộc phiên A. **Kết luận:** với synchronizer token theo phiên, server phải lấy expected từ A và từ chối token B.

**Tình huống E — SPA đọc cookie raw và gửi header nhưng 403.** Ứng dụng dùng `CookieCsrfTokenRepository` và handler XOR cho token form. **Kết luận:** kiểm tra request handler có tiếp nhận raw header hay không, cùng tên header, việc token đã được phát và làm mới sau login.

**Tình huống F — multipart upload.** File upload form có hidden token nhưng CSRF filter không thấy parameter do multipart chưa được phân tích. **Kết luận:** cần xem thứ tự filter/parser hoặc gửi token qua header khi dùng JavaScript, đồng thời cân nhắc tài nguyên lưu tệp tạm và giữ kiểm chứng CSRF.

## Kết luận

Có hai kênh phổ biến để truyền **submitted CSRF token**: **hidden field** trong HTML form và **HTTP header** do JavaScript/client hợp lệ chủ động gắn. Form phù hợp với các luồng server-rendered và form submission; header phù hợp với Ajax/JSON và một số luồng upload. Trong cả hai trường hợp, token phải do ứng dụng phát hành, có nguồn **expected token** đáng tin cậy và được server kiểm chứng theo ngữ cảnh đang xử lý.

Spring Security **Servlet** sử dụng các thành phần như `CsrfFilter`, `CsrfTokenRepository` và `CsrfTokenRequestHandler`; **Reactive/WebFlux** sử dụng `CsrfWebFilter` và `ServerCsrfTokenRepository`. Cấu hình và kiểm thử đúng cần quan tâm tên parameter/header, token raw hay masked, vòng đời sau xác thực, cookie/session, CORS khi khác origin và lỗi `403`. Phòng vệ CSRF phối hợp với các lớp HTTP/browser khác của **SPRING_SECURITY_HTTP_PROTECTION** như CORS, CSP, HSTS, security headers, HTTP firewall và bảo vệ session; mỗi lớp giải quyết một nhóm rủi ro khác nhau.
