# Mẫu synchronizer token và cách gắn token với phiên người dùng

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Giải thích **Synchronizer Token Pattern** (mẫu token đồng bộ) bảo vệ một yêu cầu HTTP thay đổi trạng thái như thế nào.
- Phân biệt **session ID**, **CSRF token lưu phía máy chủ** và **token được đưa vào form/header**; mô tả mối quan hệ giữa chúng.
- Trình bày quy trình **sinh token → lưu theo phiên → chuyển cho client hợp lệ → gửi lại → kiểm chứng → xử lý hoặc từ chối**.
- Phân tích lựa chọn token theo phiên hay theo yêu cầu, vòng đời token khi đăng nhập, đăng xuất, hết hạn phiên và chạy nhiều instance.
- Vận dụng cơ chế mặc định và cấu hình rõ ràng trên **Spring Security Servlet** và **Spring Security Reactive/WebFlux**, cùng cách thử request hợp lệ, thiếu token, sai token hoặc không khớp phiên.
- Nhận diện các lỗi triển khai như lưu token trong cookie mà không kiểm chứng, dùng token chung cho mọi tài khoản, đưa token vào URL hoặc tắt CSRF để tránh lỗi `403`.

## 1. Vì sao cần Synchronizer Token Pattern?

Giả sử ứng dụng có endpoint đổi email:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=new@example.test
~~~

Máy chủ kiểm tra cookie và xác định được đây là phiên đã đăng nhập của người dùng A. Nhưng **chỉ biết request mang phiên A không đủ để biết người dùng A chủ động thực hiện thao tác**. Trình duyệt có thể tự gắn cookie khi nhận yêu cầu gửi form từ một trang khác, nếu chính sách cookie và ngữ cảnh request cho phép.

**Synchronizer Token Pattern** bổ sung một bằng chứng mà trang hợp lệ có thể nhận được còn một website ở origin khác thường không thể đọc được: **CSRF token được máy chủ phát hành và liên kết với phiên của người dùng**. Khi gửi request thay đổi trạng thái, client hợp lệ gửi lại token này trong trường form hoặc header. Server chỉ cho qua nếu token khớp giá trị đã lưu cho **chính phiên của request**.

Đây là một cơ chế **xác minh tính hợp lệ của request**. Nó không thay thế xác thực, phân quyền hay kiểm tra dữ liệu đầu vào.

> **Mối quan hệ cốt lõi:** Cookie/session ID giúp server tìm *phiên nào* đang gửi request; CSRF token giúp server xác minh request thay đổi trạng thái này có mang bằng chứng do ứng dụng phát hành cho *đúng phiên đó* hay không.

Mẫu này đặc biệt phù hợp với ứng dụng web dùng phiên HTTP. Trong module **SPRING_SECURITY_HTTP_PROTECTION**, nó là một lớp phòng vệ HTTP/trình duyệt bên cạnh CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Cơ chế áp dụng cho cả ứng dụng **Servlet** lẫn **Reactive**, dù API triển khai khác nhau.

## 2. Ba thành phần dễ bị nhầm lẫn

| Thành phần | Nằm ở đâu? | Mục đích | Ai gửi trong request? |
|---|---|---|---|
| **Session ID** (ví dụ `JSESSIONID`) | Cookie ở trình duyệt; server tra thông tin phiên tương ứng | Định danh phiên để tra trạng thái đăng nhập và dữ liệu liên quan | **Trình duyệt tự gửi** nếu cookie phù hợp |
| **CSRF token gốc (token kỳ vọng)** | Kho lưu phía server, gắn với một phiên cụ thể | Giá trị dùng làm chuẩn khi kiểm chứng | **Không cần gửi như một cookie tự động** trong mẫu synchronizer |
| **CSRF token đưa cho client** | Trong HTML form hoặc được client hợp lệ đưa vào header | Cho phép client chủ động chứng minh request được tạo từ luồng ứng dụng | **Form/client hợp lệ chủ động gửi** |

Với triển khai đơn giản, token gốc và token hiển thị trong form là cùng một chuỗi. Trong Spring Security hiện đại, token **hiển thị** có thể được **che bằng một giá trị ngẫu nhiên (XOR masking)** nhằm giảm nguy cơ khai thác nén phản hồi kiểu BREACH. Khi đó giá trị được gửi qua form có thể thay đổi qua từng lần hiển thị mặc dù token gốc trong phiên không đổi. Handler của Spring Security giải mã biểu diễn đó trước khi kiểm chứng.

Điều quan trọng là **sự liên kết logic**, không phải việc phải nhúng session ID vào token. Thông thường server quản lý một bản ghi như sau:

~~~text
Session store phía server
┌────────────────────────────────────────────────────┐
│ Session A (khóa tra cứu từ cookie SESSION_A)         │
│   principal: alice                                  │
│   csrfToken: random-secret-for-A                    │
│                                                    │
│ Session B (khóa tra cứu từ cookie SESSION_B)         │
│   principal: bob                                    │
│   csrfToken: random-secret-for-B                    │
└────────────────────────────────────────────────────┘
~~~

Một request mang cookie của phiên A nhưng gửi token của phiên B **phải bị từ chối**. Nếu mọi phiên đều chấp nhận cùng một token toàn cục, attacker có thể lấy token ở phiên của họ và sử dụng nó để giả mạo request cho phiên của nạn nhân; như vậy đã đánh mất một thuộc tính bảo vệ trọng yếu.

## 3. Quy trình hoạt động từ đầu đến cuối

### 3.1. Phát hành token khi hiển thị trang hợp lệ

1. Người dùng mở một trang có form thay đổi trạng thái, ví dụ `GET /profile/edit`, kèm cookie phiên nếu có.
2. Server xác định phiên đang xử lý; nếu chưa có CSRF token cho phiên, repository **sinh token khó đoán** và lưu theo phiên. Việc phát hành có thể **trì hoãn đến lúc trang thực sự cần token**.
3. Server đưa một biểu diễn token vào form HTML, thường là trường ẩn `_csrf`. Trang này được phục vụ từ ứng dụng đích.
4. Browser hiển thị form và giữ cookie phiên theo cơ chế cookie thông thường.

Ví dụ phản hồi HTML:

~~~html
<form method="post" action="/profile/email">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>
  <input type="hidden" name="_csrf" value="TOKEN_DA_DUOC_SERVER_PHAT_HANH">
  <button type="submit">Lưu thay đổi</button>
</form>
~~~

`TOKEN_DA_DUOC_SERVER_PHAT_HANH` là ký hiệu minh họa. Ứng dụng phải đặt **giá trị thực** theo cách mà cơ chế token handler của Spring Security mong đợi; không tự viết một chuỗi cố định vào form.

### 3.2. Kiểm chứng trên request thay đổi trạng thái

Khi người dùng gửi form:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=new@example.test&_csrf=TOKEN_CUA_PHIEN_A
~~~

Server lần lượt:

1. Xác định phiên A từ request; **nếu không có phiên hợp lệ** thì không được suy ra quyền của nạn nhân.
2. Lấy token kỳ vọng đã lưu **cho phiên A**.
3. Đọc token client gửi qua **form field hoặc header được cấu hình**.
4. Giải mã biểu diễn token nếu handler đang sử dụng masking; so khớp token được gửi với token kỳ vọng theo cơ chế của framework.
5. **Thiếu, sai hoặc không khớp phiên:** từ chối request trước khi thực hiện thay đổi nghiệp vụ, thường với HTTP `403 Forbidden` theo cấu hình Spring Security.
6. **Token hợp lệ:** request qua được bước kiểm tra CSRF nhưng vẫn phải đáp ứng **xác thực, phân quyền, validation và quy tắc nghiệp vụ**.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant S as Ứng dụng Spring Security
    participant R as Session/token repository

    U->>B: Mở /profile/edit
    B->>S: GET + session cookie
    S->>R: Đọc token gắn với phiên
    opt Phiên chưa có CSRF token
        S->>R: Sinh và lưu token cho phiên
    end
    R-->>S: CSRF token
    S-->>B: HTML form chứa token
    U->>B: Bấm Lưu thay đổi
    B->>S: POST + session cookie + token form/header
    S->>R: Đọc token kỳ vọng của phiên hiện tại
    R-->>S: Token kỳ vọng
    alt Token hợp lệ và khớp phiên
        S->>S: Kiểm tra quyền, dữ liệu và cập nhật
        S-->>B: Phản hồi nghiệp vụ
    else Thiếu/sai token
        S-->>B: 403 Forbidden
    end
~~~

**Tại sao attacker thường không có token?** Trang tấn công có thể khiến trình duyệt gửi form liên trang nhưng thông thường không được đọc nội dung HTML do `app.example.com` trả về vì Same-Origin Policy. Cookie có thể tự đi cùng request; token nằm trong form hoặc được client hợp lệ chủ động đặt vào header thì **không tự đi theo yêu cầu từ website ngoài**.

Đây là lý do mẫu synchronizer token có hiệu lực ngay cả khi attacker **không cần biết session cookie** của nạn nhân.

## 4. “Gắn token với phiên” chính xác là gắn như thế nào?

### 4.1. Liên kết bằng trạng thái phía máy chủ

Với synchronizer token, token kỳ vọng được lưu **cùng ngữ cảnh phiên** hoặc trong một kho phía server có khóa tra cứu gắn với phiên. Cách hoạt động có thể hình dung bằng mã giả:

~~~text
GET /profile/edit
    session = findSession(request.cookie)
    expected = session.get("csrf-token")

    if expected is absent:
        expected = secureRandomToken()
        session.put("csrf-token", expected)

    renderForm(csrfToken = encodeForClient(expected))

POST /profile/email
    session = findSession(request.cookie)
    supplied = readCsrfTokenFromFieldOrHeader(request)
    expected = session.get("csrf-token")

    if supplied is absent or expected is absent:
        rejectRequest(403)

    resolved = decodeSubmittedTokenIfNeeded(supplied)

    if not verify(resolved, expected):
        rejectRequest(403)

    requireAuthenticatedUserAndAuthorization()
    validateInputAndApplyChange()
~~~

Đây là **mô hình khái niệm**, không phải bản cài đặt trực tiếp cho Spring Security. Khi dùng framework, nên để các filter/repository/handler quản lý sinh, lưu, đọc và so khớp token; tránh tự xây logic bảo mật trùng lặp.

Token **không nhất thiết chứa** username, session ID, thời điểm hay JWT claims. Một chuỗi ngẫu nhiên đủ khó đoán, gắn với phiên và được so khớp phía server là thiết kế cơ bản. Việc thêm dữ liệu nhận diện vào token không thay thế được kiểm chứng token theo phiên.

### 4.2. Một người dùng có thể có nhiều phiên

Ví dụ cùng tài khoản `alice` đăng nhập trên hai thiết bị:

| Ngữ cảnh | Session | CSRF token kỳ vọng |
|---|---|---|
| Laptop | A | `T_A` |
| Điện thoại | B | `T_B` |

Cả hai phiên đều được xác thực là `alice`, nhưng **token A không được tự động chấp nhận trong phiên B**. Gắn token với tài khoản (username) mà không gắn với phiên có thể cho phép sử dụng chéo token giữa các session.

Đồng thời, **hai tab cùng chia sẻ một phiên trình duyệt** thường dùng cùng token gốc nếu chọn chính sách token theo phiên. Điều đó thuận tiện cho trải nghiệm người dùng; không cần phát token gốc hoàn toàn mới trên mọi lần mở tab.

### 4.3. Session ID có phải là CSRF token không?

**Không.** Session ID là credential để định danh/truy xuất phiên, vốn thường do browser **tự gửi**. Dùng session ID làm token gắn trong form sẽ khiến một bí mật xác thực rất nhạy cảm bị đưa vào HTML/DOM và có thể lộ qua các luồng không mong muốn.

Một token chống CSRF nên **được sinh độc lập**, có mục đích kiểm chứng request và được bảo vệ khỏi rò rỉ. Kẻ tấn công không cần đoán được session ID nếu có thể khai thác việc browser tự gửi cookie.

## 5. Thuộc tính bảo mật của token tốt

| Thuộc tính | Vì sao cần |
|---|---|
| **Không dự đoán được** | Kẻ tấn công không thể tạo token hợp lệ từ những giá trị biết trước. Dùng nguồn số ngẫu nhiên mật mã (CSPRNG) đủ mạnh. |
| **Ràng buộc với phiên phù hợp** | Token lấy từ phiên của attacker không dùng được trong phiên nạn nhân. |
| **Kiểm chứng ở server** | Server so sánh với token kỳ vọng; chỉ nhìn thấy trường `_csrf` tồn tại là chưa đủ. |
| **Truyền qua kênh được bảo vệ** | Dùng HTTPS; tránh truyền token trong URL/query string vì có thể lộ qua lịch sử, log hoặc `Referer`. |
| **Có vòng đời rõ ràng** | Khi phiên hết hạn hoặc token bị vô hiệu hóa, request mang token cũ phải bị từ chối. |
| **Không chia sẻ tùy ý với bên thứ ba** | Không đưa token vào mã nhúng, telemetry, URL hoặc tài nguyên cache công khai. |
| **Có lớp phòng vệ bổ sung** | Kết hợp chống XSS, kiểm soát session, cookie `Secure`/`HttpOnly`/`SameSite` và kiểm soát nguồn request phù hợp. |

Đối với logic so sánh token tự triển khai, có thể cân nhắc phép so sánh có thời gian thực thi ít phụ thuộc dữ liệu. Với Spring Security, hãy sử dụng **cơ chế kiểm tra của framework**. Bảo vệ token khỏi bị lộ quan trọng hơn việc tự thay đổi thuật toán so khớp mà không có lý do rõ ràng.

### 5.1. Token theo phiên so với token theo từng yêu cầu

**Token theo phiên (per-session):** Một token gốc được lưu trong phiên và có thể được sử dụng lại cho nhiều form/request cho đến khi hết hiệu lực. Cách này thường đơn giản, dễ dùng cho nhiều tab và form cũ.

**Token theo yêu cầu (per-request):** Giá trị token gốc thay đổi hoặc bị tiêu thụ sau một request theo thiết kế. Giới hạn cơ hội tái sử dụng nếu token bị lộ, nhưng cần xử lý cạnh tranh giữa các tab, nút Back, gửi lại form, nhiều request song song và retry.

Đừng nhầm **token gốc mới mỗi request** với **biểu diễn token được XOR/mask lại mỗi lần render**: trong Spring Security, một token gốc của phiên có thể được render thành các chuỗi khác nhau mà vẫn kiểm chứng với cùng giá trị kỳ vọng.

Chọn vòng đời token căn cứ mô hình đe dọa và trải nghiệm người dùng; việc luân phiên token gốc không phải lúc nào cũng cần thiết cho mọi request.

### 5.2. Token có phải “bằng chứng người dùng đã bấm nút” tuyệt đối?

**Không.** Synchronizer token là bằng chứng request sở hữu một giá trị mà trang hợp lệ được cấp, rất hữu ích chống website ngoài không đọc được dữ liệu ứng dụng đích. Nó không thay thế:

- **Xác thực và phân quyền**: người dùng vẫn cần quyền thực hiện thao tác.
- **Chống XSS**: mã độc chạy cùng origin của ứng dụng có thể đọc hoặc sử dụng token.
- **Xác nhận thao tác nhạy cảm**: những nghiệp vụ có rủi ro cao có thể cần nhập lại mật khẩu, MFA hoặc xác nhận bổ sung.
- **Validation/idempotency**: token CSRF không ngăn gửi trùng hoặc sửa nội dung dữ liệu khi client hợp lệ gửi yêu cầu.

## 6. Mẫu synchronizer token trong Spring Security Servlet

### 6.1. Các thành phần chính

Trong Spring Security phía Servlet:

- `CsrfFilter` thực thi kiểm tra CSRF trên các request cần bảo vệ.
- `CsrfTokenRepository` quản lý việc tạo, lưu và tải token.
- `HttpSessionCsrfTokenRepository` lưu token trong `HttpSession`, nên token được liên kết với **phiên đang xử lý**.
- `CsrfTokenRequestHandler` điều phối cách đưa token đến request và cách trích token phía client. Cấu hình mặc định của các phiên bản Spring Security 6 hiện đại có thể **mask token khi render** bằng handler kiểu `XorCsrfTokenRequestAttributeHandler` để bảo vệ trước BREACH.

Spring Security mặc định bật CSRF cho cấu hình web điển hình; về nguyên tắc, các phương thức được xem là an toàn (`GET`, `HEAD`, `TRACE`, `OPTIONS`) thường không phải gửi CSRF token. Bởi vậy **endpoint GET không được tạo thay đổi trạng thái**.

Một cấu hình rõ ràng cho ứng dụng session/form login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository())
            );

        return http.build();
    }
}
~~~

Đây là ví dụ **cấu hình tường minh repository theo session**; ứng dụng sử dụng cơ chế mặc định có thể không cần khai báo repository này. Không cần tự tạo CSRF token trong controller nếu Spring Security đã chịu trách nhiệm quản lý.

### 6.2. Đưa token vào HTML form

Spring MVC + Thymeleaf có thể hiển thị token được Spring Security cung cấp qua request attribute `_csrf`:

~~~html
<!-- templates/profile/edit.html -->
<form th:action="@{/profile/email}" method="post">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Lưu</button>
</form>
~~~

`_csrf.parameterName` thường có giá trị `_csrf`, còn `_csrf.token` là giá trị cần gửi trong form theo handler đang áp dụng.

Với tích hợp Spring MVC/Thymeleaf phù hợp, framework có thể **tự thêm hidden CSRF field** khi xử lý `th:action`. Vì vậy khi dùng đoạn minh họa trên, hãy kiểm tra HTML cuối cùng trong trình duyệt để tránh thêm trường trùng lặp không cần thiết. Điểm quan trọng là **form thực sự gửi đúng token do Spring Security cung cấp**.

Ví dụ controller nghiệp vụ:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
class ProfileController {

    @GetMapping("/profile/edit")
    String editForm() {
        return "profile/edit";
    }

    @PostMapping("/profile/email")
    String updateEmail(@RequestParam String email) {
        // Ví dụ: xác thực người dùng hiện tại, kiểm tra quyền,
        // validate email và cập nhật dữ liệu trong service.
        return "redirect:/profile/edit?updated";
    }
}
~~~

Controller không cần tự kiểm tra trường `_csrf`; kiểm tra này xảy ra trong chuỗi filter **trước khi request đến controller**, nếu CSRF đang được bật và request thuộc phạm vi bảo vệ.

### 6.3. Token qua header khi dùng JavaScript

Khi ứng dụng dùng JavaScript gửi `POST`, client hợp lệ có thể gửi CSRF token bằng header mà `CsrfTokenRepository`/request handler đang mong đợi, chẳng hạn `X-CSRF-TOKEN` trong cấu hình thông thường:

~~~javascript
// Giá trị lấy từ HTML do chính ứng dụng phát hành.
const token = document.querySelector('meta[name="_csrf"]').content;
const headerName = document.querySelector('meta[name="_csrf_header"]').content;

await fetch("/profile/email", {
  method: "POST",
  headers: {
    [headerName]: token,
    "Content-Type": "application/json"
  },
  credentials: "same-origin",
  body: JSON.stringify({ email: "new@example.test" })
});
~~~

Để ví dụ này hoạt động, template cần **thực sự render** hai meta tag tương ứng từ các thuộc tính CSRF của Spring Security, và endpoint phải hỗ trợ JSON. Chẳng hạn:

~~~html
<meta name="_csrf" th:content="${_csrf.token}">
<meta name="_csrf_header" th:content="${_csrf.headerName}">
~~~

Header name phải lấy từ cấu hình framework; tránh giả định mọi ứng dụng đều dùng cùng tên. Nếu ứng dụng có frontend ở origin khác, cần xử lý CORS, cookie, `credentials` và mô hình phát token tương ứng; **cho phép CORS không thay thế kiểm tra CSRF**.

## 7. Mẫu synchronizer token trong Spring Security Reactive/WebFlux

WebFlux có cùng mô hình bảo mật nhưng sử dụng API reactive:

- `CsrfWebFilter` kiểm tra CSRF cho các request thuộc phạm vi áp dụng.
- `ServerCsrfTokenRepository` quản lý token trong ngữ cảnh `ServerWebExchange`.
- `WebSessionServerCsrfTokenRepository` lưu token trong **WebSession**, tương ứng synchronizer token gắn với phiên reactive.
- Để template hiển thị token, có thể lấy một `Mono<CsrfToken>` từ thuộc tính `ServerWebExchange` rồi giải quyết giá trị này theo luồng reactive.

Cấu hình minh họa:

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
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository())
            )
            .build();
    }
}
~~~

`WebSessionServerCsrfTokenRepository` là repository theo phiên cho WebFlux. Ví dụ chỉ minh họa cách chọn repository, không giả định mọi ứng dụng WebFlux đều xác thực bằng session; API chỉ dùng bearer header chủ động cần được đánh giá theo mô hình xác thực thực tế.

Với một handler WebFlux cần chủ động chuyển token vào model cho view:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.stereotype.Controller;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveProfilePage {

    @GetMapping("/profile/edit")
    Mono<Rendering> edit(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf = exchange.getAttribute(CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("profile/edit")
                .modelAttribute("_csrf", token)
                .build()
        );
    }
}
~~~

Ví dụ giả định request đã đi qua Spring Security `CsrfWebFilter`, nơi đặt `Mono<CsrfToken>` vào exchange attribute. Việc **subscribe/giải quyết Mono** giúp token sẵn sàng cho view trong trường hợp repository tải hoặc sinh token theo yêu cầu. Nhiều tích hợp template cung cấp sẵn cơ chế gắn token; hãy dùng cơ chế thích hợp với stack thay vì tự tạo token ngẫu nhiên trong handler.

Ở cả Servlet và Reactive, điểm kiểm chứng bất biến là: **server tra token gốc theo phiên hiện tại và đối chiếu với token request đưa lên**.

## 8. Vòng đời token và những tình huống triển khai thường gặp

### 8.1. Lần đầu truy cập và deferred token

Một số cơ chế Spring Security hiện đại **trì hoãn việc tạo/tải token** đến khi token thực sự cần dùng. Khi một GET chỉ trả về dữ liệu công khai và không hiển thị form, có thể chưa phải tạo session chỉ để lưu CSRF token. Khi render form cần token hoặc nhận request thay đổi trạng thái, framework xử lý token theo cấu hình.

Hệ quả: **không nên tự giả định cứ có GET là token đã được lưu ngay**. Khi xây SPA, cần thiết kế cách nhận token theo cơ chế token handler/repository tương ứng.

### 8.2. Đăng nhập và đăng xuất

Tại ranh giới xác thực, việc vô hiệu hóa token cũ giúp tránh dùng token phát sinh trong ngữ cảnh phiên trước đó. Với Spring Security phía Servlet, các thành phần như `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` tham gia xóa token ở các thời điểm xác thực/đăng xuất phù hợp; token mới được sinh khi cần tiếp.

Vì vậy có thể xảy ra tình huống:

1. Client tải trang hoặc nhận token trước khi đăng nhập.
2. Đăng nhập thành công làm vô hiệu hóa token cũ.
3. Client gửi một POST mới với token trước đăng nhập.
4. Server từ chối vì token không còn khớp.

Cách xử lý là **tải/nhận token mới theo thiết kế ứng dụng**, không phải tắt CSRF chỉ để tránh `403`. Tương tự, các tab giữ form cũ lâu ngày có thể phải tải lại sau khi phiên thay đổi.

**Chính request đăng nhập/đăng xuất cũng cần xem xét CSRF.** Ví dụ login CSRF có thể khiến nạn nhân đăng nhập vào tài khoản do attacker kiểm soát. Không mặc định miễn kiểm tra chỉ vì người dùng chưa đăng nhập.

### 8.3. Hết hạn phiên hoặc thay session ID

Khi session hết hạn, repository không còn token kỳ vọng cũ; một token từ HTML form mở sẵn không đủ làm request mới hợp lệ. Nếu phiên bị thay hoặc token bị xóa tại thời điểm chuyển trạng thái đăng nhập, form ở tab khác có thể chứa token cũ.

Thông báo cho người dùng tải lại form hoặc làm mới token là giải pháp phù hợp. Không được chấp nhận token của một phiên cũ chỉ vì cookie/token cũ còn trong trình duyệt.

### 8.4. Nhiều tab và nhiều request đồng thời

Một token gốc theo phiên giúp nhiều tab cùng dùng form mà không làm token vô hiệu hóa lẫn nhau sau mỗi lần gửi. Tuy nhiên, khi ứng dụng **chủ động thay token gốc** (sau đăng nhập, đăng xuất hoặc theo chính sách tùy biến), cần tính đến:

- Form được mở trước khi thay token;
- Nhiều request bất đồng bộ gửi song song;
- Nút Back và thao tác gửi lại form;
- Tải lại nội dung sau khi phiên được tạo mới.

Đây là vấn đề về **vòng đời token**. Không nên thay token sau mọi POST theo cách làm hỏng form cũ khi chưa có chiến lược đồng bộ phía client.

### 8.5. Triển khai nhiều instance và session store

Nếu token nằm trong `HttpSession` hoặc `WebSession`, mọi instance có khả năng xử lý cùng phiên cần nhìn thấy trạng thái token nhất quán. Hệ thống có thể dùng **session affinity** hoặc một giải pháp **lưu phiên dùng chung** theo kiến trúc của mình.

Ví dụ: GET form đến node A tạo token và ghi vào session tại A; POST đến node B không thấy token tương ứng sẽ bị từ chối. Cần kiểm tra cấu hình session store/replication, load balancer và chiến lược quản lý phiên. Không nên “khắc phục” bằng cách bỏ qua kiểm tra token.

### 8.6. BREACH masking và giá trị token trong HTML

Trong Spring Security Servlet hiện đại, request handler có thể đưa ra giá trị token đã XOR/mask khi render. Khi xem nguồn HTML qua hai lần tải, người học có thể nhận thấy token **khác nhau** dù đang dùng cùng phiên.

Điều này không nhất thiết có nghĩa repository đã sinh token gốc mới. Cơ chế masking tách **biểu diễn token trên response** với **token gốc lưu trong session**, và request handler phục hồi giá trị để kiểm tra. Nếu frontend đọc token rồi gửi qua header theo cách tùy biến, cần hiểu handler đang cấu hình để tránh lỗi token không hợp lệ.

Không tự lấy token gốc từ session để lắp vào request theo một định dạng khác với định dạng mà request handler đang kiểm chứng.

## 9. So sánh với các biện pháp thường bị nhầm

| Cơ chế | Token được lưu/kiểm tra thế nào? | Khác biệt đáng nhớ |
|---|---|---|
| **Synchronizer token (server-side session)** | Server lưu token kỳ vọng theo phiên; form/header gửi lại để đối chiếu với đúng phiên đó. | Cần trạng thái phía server hoặc kho token có thể tra theo phiên. |
| **Double-submit cookie** | Client gửi token theo **cookie và form/header**; server so khớp theo thiết kế, loại mạnh thường dùng token ký/ràng buộc session. | Cần thận trọng với nguy cơ cookie injection và token không được ràng buộc; **không giống** lưu token gốc trong server session. |
| **SameSite cookie** | Trình duyệt hạn chế gửi cookie tùy ngữ cảnh site/điều hướng. | Là lớp phòng vệ bổ sung; không thay kiểm chứng CSRF token cho mọi tình huống. |
| **Kiểm tra Origin/Referer** | Server xác minh nguồn request theo header. | Hữu ích bổ sung hoặc trong mô hình bảo vệ phù hợp; cần xử lý header thiếu và proxy. |
| **CORS** | Kiểm soát truy cập phản hồi cross-origin và preflight của một số request JavaScript. | Không tự chặn được mọi form submission cross-site và không phải synchronizer token. |
| **Content Security Policy (CSP)** | Hạn chế nguồn tài nguyên/script được chạy theo chính sách. | Hỗ trợ giảm nguy cơ XSS; không trực tiếp ràng buộc mọi POST với CSRF token. |

**Lưu ý quan trọng với Spring Security:** `CookieCsrfTokenRepository` là lựa chọn phổ biến cho một số SPA cần đọc token từ cookie, nhưng nó thuộc **mô hình token trong cookie** và không đồng nhất với `HttpSessionCsrfTokenRepository`/`WebSessionServerCsrfTokenRepository`. Khi bài toán yêu cầu “mẫu synchronizer token gắn token với phiên”, cần nhận diện rõ repository nào đang thực sự dùng.

## 10. Thực hành kiểm thử mẫu synchronizer token

Hãy chỉ thử trên ứng dụng/môi trường được phép, với một endpoint thực sự đi qua chuỗi bảo mật. Có thể bắt đầu từ form `POST /profile/email`.

### 10.1. Ma trận hành vi kỳ vọng

| Trường hợp | Cookie phiên | CSRF token gửi lên | Kỳ vọng |
|---|---|---|---|
| Form hợp lệ | Phiên A | Token đúng của A | Qua kiểm tra CSRF; vẫn cần authentication/authorization/validation. |
| Thiếu token | Phiên A | Không có | Từ chối (thường `403`). |
| Token sai | Phiên A | Chuỗi ngẫu nhiên không khớp | Từ chối (thường `403`). |
| Dùng token phiên khác | Phiên A | Token đúng của B | Từ chối: không khớp phiên. |
| Phiên hết hạn | Cookie cũ | Token cũ | Không thực hiện thao tác dưới phiên đã hết hạn. |
| GET đọc dữ liệu | Có thể có phiên | Không có token | Theo mặc định không yêu cầu token, **với điều kiện GET không thay đổi trạng thái**. |
| XSS chạy được trong origin đích | Phiên nạn nhân | Có thể lấy/dùng token hợp lệ | Synchronizer token **không thay thế** phòng vệ XSS. |

Kết quả HTTP cụ thể có thể khác do entry point xác thực, failure handler hoặc yêu cầu nghiệp vụ. Đừng suy ra nguyên nhân chỉ từ `403`.

### 10.2. Kiểm thử Servlet bằng Spring Security Test

Với một `MockMvc` được cấu hình áp dụng security filters và controller POST trả redirect như ví dụ ở trên:

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
class CsrfServletTests {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectPostWithoutToken() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void rejectPostWithInvalidToken() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void allowValidTokenThroughCsrfCheck() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf())
                .param("email", "new@example.test"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

`with(csrf())` là hỗ trợ của Spring Security Test giúp tạo request mang token hợp lệ; nó không cần trích token thủ công từ HTML như một browser thật. Test cuối giả định controller hợp lệ chuyển hướng khi hoàn thành. Khi có kiểm tra nghiệp vụ hoặc quyền khác, cần điều chỉnh kết quả kỳ vọng phù hợp.

Để kiểm chứng **ràng buộc token với phiên**, cần thêm kiểm thử tích hợp qua flow tải form với session A/B rồi hoán đổi token của chúng; chỉ gọi một `csrf()` mới chưa đủ chứng minh không có lỗ hổng sử dụng token chung.

### 10.3. Kiểm thử WebFlux bằng WebTestClient

Với `WebTestClient` đã gắn Spring Security test configurer, có thể minh họa:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringBootTest
class CsrfWebFluxTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient
            .bindToApplicationContext(context)
            .apply(SecurityMockServerConfigurers.springSecurity())
            .build();
    }

    @Test
    void rejectPostWithoutToken() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .bodyValue("email=new@example.test")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tokenAllowsRequestPastCsrfFilter() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/profile/email")
            .bodyValue("email=new@example.test")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

Ví dụ cuối giả định ứng dụng WebFlux có endpoint tương ứng và trả redirect nếu hợp lệ; nếu endpoint nhận JSON/form hoặc trả status khác, cần điều chỉnh `Content-Type`, body và assertion. Các test này minh họa **cách gắn security test support** trên reactive; chúng không thay cho bài kiểm thử token của hai WebSession thực sự.

### 10.4. Kiểm thử luồng thực tế trong trình duyệt

Ngoài unit/integration test, hãy dùng DevTools để kiểm tra:

1. Mở form hợp lệ, xem trường/token được render và cookie phiên được gửi tới ứng dụng.
2. Submit form đúng, xác nhận request mang field/header CSRF và đạt kết quả nghiệp vụ mong đợi.
3. Xóa hoặc đổi token rồi submit lại, xác nhận server không cập nhật dữ liệu.
4. Đăng xuất, đăng nhập lại hoặc để phiên hết hạn; thử submit form cũ và xem ứng dụng hướng dẫn làm mới token thế nào.
5. Kiểm tra hai phiên độc lập. Token của phiên A không được hợp lệ khi request đi cùng cookie phiên B.
6. Trong kịch bản cross-site, kiểm tra **cookie có thực sự được browser gửi** theo `SameSite`/chính sách bên thứ ba hay không, thay vì mô phỏng bằng một HTTP client có thể tùy ý ép header `Cookie`.

## 11. Chẩn đoán khi triển khai thất bại

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| GET form thành công, POST trả `403` | Form thiếu token, field/header sai tên, token không đúng phiên hoặc handler decode không khớp. | Kiểm tra HTML đã render, request thực tế, repository và request handler. |
| Chỉ lỗi sau đăng nhập | Token cũ bị xóa/rotate khi xác thực. | Cấp lại token cho các form/SPA sau đăng nhập. |
| Chỉ lỗi sau một thời gian | Phiên hết hạn, form cũ hoặc session store mất trạng thái. | Làm mới form/token; rà soát timeout và lưu phiên. |
| Lỗi thất thường sau khi tăng node | Một node không đọc được session/token của node khác. | Kiểm tra session affinity hoặc kho phiên dùng chung. |
| Token nhìn khác sau mỗi GET | Token được mask khi render để giảm BREACH; không nhất thiết token gốc thay đổi. | Kiểm chứng bằng luồng handler chuẩn, không so bằng mắt chuỗi HTML. |
| Chỉ frontend SPA lỗi | Header token thiếu, token không được làm mới, browser không gửi cookie, hoặc cấu hình CORS/credentials lệch. | Kiểm tra riêng cookie, token, header và phản hồi preflight. |
| Tắt CSRF thì request chạy | Có thể đúng là token bị thiếu/sai, nhưng cũng có thể cấu hình đang quá rộng. | Xác định nguyên nhân và phạm vi áp dụng; tránh tắt toàn bộ chỉ để qua lỗi. |

Nếu cần miễn CSRF cho một endpoint đặc biệt (ví dụ webhook xác thực bằng chữ ký riêng, không dựa cookie trình duyệt), hãy lập luận từ **cơ chế xác thực và mô hình đe dọa của chính endpoint đó**, rồi cấu hình phạm vi bỏ qua thật hẹp. Không suy luận rằng toàn bộ REST API đều miễn CSRF.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Alice có phiên A, Bob có phiên B. Server chấp nhận token do Bob lấy trong form của phiên B khi Alice gửi cookie phiên A. Vấn đề là gì?

**Đáp án:** Token không được kiểm chứng theo **đúng phiên**; mẫu synchronizer token bị triển khai sai. Cần mỗi phiên có token kỳ vọng riêng và server tra theo session của request.

**Câu 2.** Người dùng mở hai tab form. Token trong HTML thay đổi qua hai lần tải nhưng cả hai form hợp lệ. Có chắc server dùng per-request token gốc không?

**Đáp án:** Không. Spring Security có thể dùng **masking** cho biểu diễn token trên response; token gốc lưu theo session vẫn giữ nguyên.

**Câu 3.** API lưu JWT trong cookie `HttpOnly` và không lưu phiên phía server. Synchronizer token mặc định theo session có phù hợp không?

**Đáp án:** JWT trong cookie vẫn là credential browser tự gửi và có thể gây CSRF. Tuy nhiên, synchronizer token **đòi hỏi trạng thái liên kết phiên phía server**, nên API thực sự stateless cần chọn chiến lược phòng vệ phù hợp khác hoặc thiết kế nơi lưu token kỳ vọng. Không được kết luận API an toàn chỉ vì nó dùng JWT.

**Câu 4.** Vì sao form GET không cần CSRF token theo mặc định, và nguy cơ nằm ở đâu?

**Đáp án:** Spring Security mặc định coi GET là phương thức an toàn. Nếu một GET thực tế xóa dữ liệu, thiết kế endpoint đã vi phạm giả định này; cần sửa để hành động thay đổi trạng thái dùng phương thức phù hợp và được bảo vệ CSRF.

## Kết luận

**Synchronizer Token Pattern** bảo vệ request thay đổi trạng thái bằng một token khó đoán được **lưu và kiểm chứng gắn với phiên người dùng**. Browser có thể tự gửi session cookie nhưng một website ngoài thường không thể đọc token được cấp trong trang hợp lệ để gắn vào form/header. Server phải so khớp token request với token kỳ vọng của **chính session hiện tại** và từ chối request thiếu, sai hoặc không khớp.

Trên Spring Security **Servlet**, mô hình này thường dựa vào `CsrfFilter` và `HttpSessionCsrfTokenRepository`; trên **Reactive/WebFlux**, các thành phần tương ứng là `CsrfWebFilter` và `WebSessionServerCsrfTokenRepository`. Cấu hình đúng còn cần quản lý vòng đời token khi xác thực, hết hạn phiên, nhiều tab/nhiều node và các request handler bảo vệ biểu diễn token. Đây là một lớp trong phòng vệ HTTP tổng thể, được hỗ trợ thêm bởi kiểm soát session, cookie, CORS, security headers, CSP, HSTS và thiết kế endpoint an toàn.
