# Lưu giá trị dự kiến và nhận giá trị client gửi để đối chiếu

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Phân biệt **CSRF token dự kiến** (*expected token*) ở phía máy chủ với **CSRF token được client gửi** (*submitted token*) trong HTTP request.
- Trình bày quy trình sinh, lưu, tải, phát hành và xác minh token, đặc biệt là bước tra cứu **đúng phiên hoặc đúng ngữ cảnh tin cậy**.
- Giải thích tại sao cookie xác thực được trình duyệt tự gửi chưa đủ chứng minh yêu cầu được phát sinh từ giao diện hợp lệ.
- Phân tích các nơi lưu giá trị dự kiến: `HttpSession`, `WebSession`, cookie token và kho lưu tùy biến; xác định sự khác nhau giữa synchronizer token và double-submit cookie.
- Chỉ ra cách lấy giá trị client gửi qua **form parameter** hoặc **HTTP header**, phân biệt token gốc và token đã che (*masked/XOR*) trong các cấu hình Spring Security hiện đại.
- Cấu hình và kiểm thử đường kiểm chứng CSRF trên **Servlet** và **Reactive/WebFlux**, từ request hợp lệ đến request thiếu token, sai token và token thuộc phiên khác.
- Chẩn đoán lỗi `403 Forbidden` do CSRF mà không nhầm lẫn với lỗi xác thực, phân quyền hay CORS.

## 1. Bài toán: một request có hai nguồn thông tin khác nhau

Trong ứng dụng sử dụng cookie/session, trình duyệt có thể tự gắn cookie xác thực vào request đến đúng máy chủ. Nếu một trang bên ngoài kích hoạt form POST và các chính sách trình duyệt cho phép cookie đi cùng, server có thể nhận diện người dùng đang đăng nhập, dù người đó không chủ động thực hiện thao tác.

Ví dụ:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=attacker@example.test
~~~

Request có phiên A hợp lệ. Điều này **không chứng minh** người dùng A đã mở form đổi email của ứng dụng và chủ động gửi nó.

Một cơ chế chống CSRF dựa trên token bổ sung bước kiểm chứng:

- **Giá trị dự kiến (expected):** Giá trị mà server tin cậy vì đã tạo và lưu, hoặc có thể kiểm chứng bằng quy tắc mật mã gắn với ngữ cảnh phù hợp.
- **Giá trị client gửi (submitted/actual):** Giá trị xuất hiện trong **trường form hoặc header** của request cần bảo vệ.
- **Kết quả đối chiếu:** Server chỉ cho request vượt qua lớp CSRF khi token client gửi **hợp lệ theo giá trị dự kiến và ngữ cảnh hiện tại**.

Một POST có đủ cookie session nhưng **không có submitted CSRF token hợp lệ** phải bị từ chối nếu endpoint thuộc phạm vi bảo vệ CSRF.

> **Nguyên tắc:** Xác thực trả lời “request này gắn với người dùng/phiên nào?”. CSRF token trả lời thêm “request thay đổi trạng thái này có mang bằng chứng phù hợp với ngữ cảnh mà ứng dụng đã phát hành hay không?”.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, việc kiểm tra cặp giá trị *expected/submitted* là nền tảng cho lớp phòng vệ CSRF, hoạt động cùng CORS, security headers, CSP, HSTS, HTTP firewall và quản lý session ở cả **Servlet** lẫn **Reactive**.

## 2. Thuật ngữ cần thống nhất

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Authentication/session credential** | Bằng chứng xác thực mà browser có thể tự gửi | Cookie `JSESSIONID`, `SESSION` hoặc token xác thực trong cookie |
| **Expected CSRF token** | Token mà server tạo/lưu hoặc có thể xác minh theo một ngữ cảnh đáng tin cậy | Giá trị trong `HttpSession` hoặc `WebSession` |
| **Submitted CSRF token** | Token do form hoặc client gửi kèm một request thay đổi trạng thái | Tham số `_csrf` hoặc header `X-CSRF-TOKEN` |
| **Token repository** | Thành phần sinh, lưu và tải token kỳ vọng | `HttpSessionCsrfTokenRepository`, `WebSessionServerCsrfTokenRepository` |
| **Request handler** | Thành phần đưa token vào ngữ cảnh request và xác định token client thực sự nộp | `CsrfTokenRequestHandler`, cơ chế tương ứng ở WebFlux |
| **CSRF filter/web filter** | Thành phần quyết định request nào cần token, tra giá trị và kiểm tra | `CsrfFilter`, `CsrfWebFilter` |
| **Masked token** | Biểu diễn token có thêm ngẫu nhiên để tránh lộ token qua một số kênh phụ như nén phản hồi | Giá trị XOR được render trong HTML |
| **Raw token** | Token gốc mà repository lưu/kiểm tra | Có thể khác chuỗi masked được hiển thị trong HTML |

**Phân biệt quan trọng:** Giá trị dự kiến **không đồng nghĩa** với một chuỗi mà client tự khai báo là “đáng tin”. Nếu server lấy cả hai giá trị từ cùng request không có nguồn kiểm chứng độc lập, một attacker có thể tìm cách kiểm soát cả hai.

## 3. Luồng xử lý tổng quát

### 3.1. Khi trang hợp lệ cần một CSRF token

1. Trình duyệt gửi request tới ứng dụng, ví dụ `GET /profile/edit`.
2. Server xác định ngữ cảnh của request, thường là một HTTP session/WebSession.
3. Repository kiểm tra xem ngữ cảnh đó đã có token dự kiến chưa.
4. Nếu chưa có và cần token, repository sinh một token khó đoán và lưu đúng nơi.
5. Server cung cấp một biểu diễn token cho trang hợp lệ bằng hidden field, meta tag, một response phù hợp hoặc kênh mà client cùng origin được phép đọc.
6. Trình duyệt hiển thị form hoặc mã ứng dụng ghi nhớ giá trị cần gửi ở request tiếp theo.

Ví dụ HTML sau khi server render:

~~~html
<form method="post" action="/profile/email">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>
  <input type="hidden" name="_csrf" value="TOKEN_DUOC_SERVER_CAP">
  <button type="submit">Cập nhật</button>
</form>
~~~

`TOKEN_DUOC_SERVER_CAP` chỉ là ký hiệu minh họa. Trong ứng dụng thực tế, giá trị phải do Spring Security cung cấp theo repository/handler đang cấu hình.

### 3.2. Khi client gửi request thay đổi trạng thái

Trình duyệt gửi phiên xác thực bằng cookie, đồng thời **form hợp lệ** gửi token qua trường `_csrf`:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=alice-new@example.test&_csrf=TOKEN_CUA_PHIEN_A
~~~

Server thực hiện logic tương đương:

~~~text
Request POST
  1. Chọn xem request có cần kiểm tra CSRF không.
  2. Tải expected token từ repository, theo ngữ cảnh request.
  3. Nhận submitted token từ form parameter hoặc header.
  4. Giải mã/chuẩn hóa biểu diễn submitted token nếu handler yêu cầu.
  5. Nếu expected thiếu, submitted thiếu hoặc không hợp lệ: từ chối.
  6. Nếu token hợp lệ: tiếp tục chuỗi bảo mật và nghiệp vụ.
~~~

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant S as CSRF filter
    participant R as Token repository
    participant A as Controller/handler

    U->>B: Mở form
    B->>S: GET /profile/edit
    S->>R: Tải hoặc sinh token dự kiến khi cần
    R-->>S: Token theo phiên hiện tại
    S-->>B: Trả HTML có token để submit
    U->>B: Gửi form
    B->>S: POST + session cookie + submitted token
    S->>R: Tải expected token của phiên request
    R-->>S: Expected token
    S->>S: Resolve/decode submitted rồi đối chiếu
    alt Thiếu/sai/không khớp
        S-->>B: Từ chối, thường 403
    else Token hợp lệ
        S->>A: Chuyển request đến bước tiếp theo
        A-->>B: Kết quả sau xác thực, phân quyền và validation
    end
~~~

Ở những framework có **deferred token**, việc tạo/tải token có thể được hoãn cho đến khi token thực sự được dùng, chẳng hạn khi render form hoặc khi kiểm tra POST. Sơ đồ mô tả quy trình logic, không bắt buộc mỗi GET đều tạo một session mới.

## 4. Giá trị dự kiến được lưu ở đâu?

### 4.1. Synchronizer token lưu theo phiên trên server

Một phương án thông dụng là tạo token ngẫu nhiên, lưu trong một session do server quản lý:

~~~text
Session store
+-------------------------------------------------------+
| Session A                                             |
|   principal = alice                                   |
|   expectedCsrfToken = random-value-A                  |
|                                                       |
| Session B                                             |
|   principal = bob                                     |
|   expectedCsrfToken = random-value-B                  |
+-------------------------------------------------------+
~~~

Khi một POST mang cookie session A, server phải tìm **expected token A**. Nếu request mang token B, cần từ chối dù token B được ứng dụng thật sự cấp cho Bob.

| Request | Expected token được server tra | Submitted token | Kết quả CSRF |
|---|---|---|---|
| Cookie phiên A | A | A | Qua bước kiểm tra |
| Cookie phiên A | A | B | Từ chối |
| Cookie phiên B | B | A | Từ chối |
| Cookie phiên A | A | Không có | Từ chối |
| Cookie phiên A | Không còn token do phiên hết hạn | Token A cũ | Không được chấp nhận như token hợp lệ của phiên cũ |

Trong Spring Security:

- **Servlet:** `HttpSessionCsrfTokenRepository` lưu token theo `HttpSession`.
- **Reactive/WebFlux:** `WebSessionServerCsrfTokenRepository` lưu token theo `WebSession`.

Đây là cách hiểu trực tiếp nhất của **giá trị dự kiến**: server giữ chuẩn kiểm chứng; client nộp một giá trị khác để so.

### 4.2. Cookie token: repository lấy expected từ cookie

Một số ứng dụng SPA cần JavaScript cùng origin đọc CSRF token từ cookie rồi gửi token đó bằng header. Spring Security có:

- **Servlet:** `CookieCsrfTokenRepository`;
- **Reactive:** `CookieServerCsrfTokenRepository`.

Với mô hình cookie token đơn giản, repository đọc **giá trị từ cookie CSRF** của request làm expected token; request handler tiếp tục đọc **giá trị từ header/form** làm submitted token. Hai bản sao phải khớp.

~~~http
Cookie: JSESSIONID=SESSION_A; XSRF-TOKEN=csrf-cookie-value
X-XSRF-TOKEN: csrf-cookie-value
~~~

**Khác biệt bảo mật:** Giá trị expected được lấy từ cookie mà browser gửi, nên nếu attacker có thể **tiêm hoặc điều khiển cookie CSRF** (ví dụ qua subdomain/cookie scope), chỉ so hai bản sao có thể chưa đủ. Biến thể **signed double-submit** cần kiểm chứng HMAC/ràng buộc phiên riêng; `CookieCsrfTokenRepository` thông thường **không tự biến token thành token HMAC gắn phiên**.

Bài toán “lấy expected từ đâu?” phải được giải đáp trước khi phân tích “so token như thế nào?”. Chỉ thấy một cookie và một header có cùng chuỗi **không chứng minh** cơ chế bảo vệ toàn diện.

### 4.3. Repository tùy biến và token có chữ ký

Một hệ thống có thể dùng kho token dùng chung hoặc token được ký bằng khóa bí mật phía server. Khi đó:

- Expected token có thể được truy xuất theo khóa phiên từ kho đáng tin cậy.
- Hoặc server kiểm chứng tính toàn vẹn và ràng buộc phiên của token đã ký, không cần lưu bản sao của từng token trong session.

Đây là thiết kế đặc biệt, cần có kiểm chứng mật mã, vòng đời khóa, xử lý cookie và test rõ ràng. Không thay repository chỉ để bỏ qua một lỗi `403`, vì lỗi có thể xuất phát từ việc client chưa nhận đúng token.

### 4.4. Cần quản lý token theo phiên, không chỉ theo tài khoản

Hai trình duyệt có thể cùng đăng nhập một tài khoản nhưng dùng **hai session riêng**. Token theo session A không nên được chấp nhận dưới session B chỉ vì cả hai có username `alice`. Khi session bị vô hiệu hóa, token cũ không được tự coi là hợp lệ cho session mới.

Với token theo phiên, nhiều tab thuộc **cùng session** có thể dùng cùng một token gốc. Với chính sách token đổi sau mỗi yêu cầu, cần xử lý nhiều tab, thao tác Back và yêu cầu song song; không nhầm biến thể đó với **masking** chỉ làm đổi chuỗi hiển thị.

## 5. Nhận giá trị client gửi qua HTTP

### 5.1. Form parameter

Các form HTML truyền thống có thể chứa một hidden field:

~~~html
<form method="post" action="/settings">
  <input type="hidden" name="_csrf" value="TOKEN_THUC">
  <input type="text" name="displayName">
  <button type="submit">Lưu</button>
</form>
~~~

Khi gửi theo `application/x-www-form-urlencoded`, body thường chứa tham số `_csrf` cùng các trường nghiệp vụ.

Trong Spring Security Servlet, `CsrfToken` cung cấp tên parameter (`getParameterName()`), tên header (`getHeaderName()`) và biểu diễn token (`getToken()`). Dùng những giá trị do framework cung cấp thay vì hardcode khi ứng dụng có thể cấu hình tên khác.

**Không gửi token CSRF trong query string** như `/settings?_csrf=...`: URL có thể vào lịch sử, log, báo cáo lỗi hoặc header `Referer` của các request liên quan.

### 5.2. HTTP header trong request JavaScript

Một SPA có thể lấy token từ HTML được server render:

~~~html
<meta name="_csrf" content="TOKEN_THUC">
<meta name="_csrf_header" content="X-CSRF-TOKEN">
~~~

Sau đó gửi trong request:

~~~javascript
const token = document.querySelector('meta[name="_csrf"]').content;
const headerName = document.querySelector('meta[name="_csrf_header"]').content;

const response = await fetch("/api/profile", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    [headerName]: token,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ displayName: "Alice" })
});

if (!response.ok) {
  throw new Error("Không lưu được hồ sơ: HTTP " + response.status);
}
~~~

Ở ví dụ này, hai meta tag **phải được render bằng token và tên header thật** từ ứng dụng, ví dụ với Thymeleaf lấy từ `_csrf.token` và `_csrf.headerName`. Trình duyệt có thể tự gửi cookie xác thực, nhưng **JavaScript hợp lệ chủ động thêm CSRF header**.

Nếu frontend/API khác origin, cần xem riêng `credentials`, CORS, cookie và SameSite. CORS không thay thế việc kiểm tra CSRF trên server; một số form cross-site vẫn có thể gửi request mà không được cấp quyền đọc phản hồi.

### 5.3. Thư viện có thể tự gắn header từ cookie CSRF

Một số client HTTP được cấu hình để đọc cookie `XSRF-TOKEN` rồi đặt header `X-XSRF-TOKEN`. Điều đó chỉ đúng nếu:

1. Cookie token được phát hành và ở phạm vi client có thể đọc.
2. Cookie token không bị `HttpOnly` nếu JavaScript phải truy cập qua `document.cookie`.
3. Header name đúng với repository/request handler của server.
4. Client thực sự gửi header ở request cần bảo vệ.
5. Server đối chiếu token theo một chính sách bảo mật phù hợp; với signed double-submit còn phải kiểm tra chữ ký và phiên.

Đừng chỉ dựa vào tên framework/client để suy đoán header đã được gắn. Kiểm tra **request thực tế** bằng DevTools.

### 5.4. Cookie và header khác nhau ở điểm bảo mật nào?

| Đường gửi | Ai điều khiển? | Hệ quả |
|---|---|---|
| `Cookie: JSESSIONID=...` | Browser tự gắn khi phù hợp cookie policy | Không chứng minh request được tạo bởi trang hợp lệ |
| `Cookie: XSRF-TOKEN=...` | Browser tự gắn khi phù hợp cookie policy | Một mình chưa phải submitted token độc lập |
| Body `_csrf=...` | Form/page đưa giá trị vào body | Trang ngoài thường không biết giá trị hợp lệ từ trang đích |
| Header `X-CSRF-TOKEN: ...` | Mã client chủ động thiết lập | Form HTML đơn giản không thể tự thêm header tùy ý |

Header tùy chỉnh có thể tạo thêm rào cản với request JavaScript cross-origin vì preflight/CORS, nhưng **không vì thế mà server được bỏ bước kiểm tra submitted token**.

## 6. Đối chiếu đúng giá trị: “bằng nhau” chưa phải toàn bộ câu chuyện

Trong luồng token theo phiên, quy tắc kiểm chứng cơ bản là:

~~~text
if request cần kiểm tra CSRF:
    expected = repository.loadToken(trustedRequestContext)
    submitted = handler.resolveSubmittedToken(request, expected)

    if expected không tồn tại:
        từ chối
    if submitted không tồn tại:
        từ chối
    if submitted không hợp lệ với expected:
        từ chối
    ngược lại:
        cho qua bước CSRF
~~~

Khi tự xây logic chuyên biệt, phép so sánh bí mật nên tránh các rò rỉ thời gian không cần thiết; với Spring Security hãy dùng cơ chế kiểm chứng do filter/handler của framework thực hiện. Không dựa vào việc nhận được một parameter có tên `_csrf` là đủ.

### 6.1. Token gửi lên cần đúng phiên

Giả sử:

~~~text
session A --> expected A
session B --> expected B
~~~

Kẻ tấn công có thể mở chính ứng dụng và lấy token B của **phiên của họ**. Nếu server chấp nhận token B đi cùng cookie xác thực A, hệ thống đã đánh mất tính ràng buộc với phiên. Đây là một kiểm thử quan trọng hơn việc chỉ gửi một chuỗi ngẫu nhiên sai.

### 6.2. Token gốc so với token được XOR/mask khi render

Trong nhiều cấu hình Spring Security Servlet hiện đại, `XorCsrfTokenRequestAttributeHandler` giúp chống các kênh rò rỉ liên quan nén phản hồi (BREACH) bằng cách **che token trước khi xuất ra HTML**.

Có thể hình dung:

~~~text
expected raw token trong repository = R
render form lần 1 = mask(R, random1) = M1
render form lần 2 = mask(R, random2) = M2

M1 có thể khác M2 mặc dù R không đổi.
Khi POST: submitted M1 -> handler bỏ mask -> R -> so với expected R.
~~~

Do đó, **không nên lấy chuỗi masked trên HTML rồi so nguyên văn với token raw trong session**. Cần để request handler chuyển đổi submitted token về biểu diễn mà repository kiểm chứng.

Một lỗi phổ biến của SPA: frontend đọc **raw token từ cookie**, nhưng server đang cấu hình handler mặc định **mong đợi biểu diễn masked** từ một nguồn khác. Kết quả là `403` dù nhìn bằng mắt các giá trị có vẻ “đúng”. Trên Servlet có thể thiết kế handler phân biệt token form masked và header raw theo mô hình SPA; cần cấu hình có chủ đích, không tắt CSRF để tránh lỗi.

### 6.3. Không nhầm token có chữ ký với token được mask

| Đặc tính | Masking/XOR token | Signed/HMAC token |
|---|---|---|
| Mục tiêu chính | Che biểu diễn token khi đưa ra response | Chứng minh token do phía server có khóa bí mật ký |
| Có thể làm chuỗi token hiển thị thay đổi? | Có, dù token gốc giữ nguyên | Có khi phát nonce/token mới |
| Tự ràng buộc token vào phiên? | **Không**; vẫn cần repository/ngữ cảnh kiểm chứng | Chỉ có nếu HMAC **bao gồm binding phiên đáng tin cậy** |
| Tự thay thế lưu expected token? | Không | Có thể, nếu thiết kế xác minh stateless đầy đủ |

Masking là **lớp xử lý biểu diễn**; signed double-submit là **thiết kế kiểm chứng tính toàn vẹn và nguồn gốc token**. Hai chức năng phục vụ các vấn đề khác nhau.

## 7. Spring Security Servlet: lưu và đối chiếu token

### 7.1. Các thành phần trong đường đi request

Với Spring Security Servlet, chuỗi thành phần liên quan gồm:

- `CsrfFilter` xác định request nào cần CSRF và phối hợp việc kiểm chứng.
- `CsrfTokenRepository` cung cấp cách sinh, lưu, tải token.
- `HttpSessionCsrfTokenRepository` lưu expected token trong `HttpSession`.
- `CsrfTokenRequestHandler` tạo/đưa token vào request attribute và giải quyết submitted token từ HTTP request.
- `CsrfToken` mang tên header, tên parameter và giá trị token theo hợp đồng của Spring Security.

Một cấu hình minh họa cho web dùng session:

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
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                // Lưu expected token theo HttpSession hiện tại.
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()));

        return http.build();
    }
}
~~~

Ở cấu hình web phổ biến, CSRF đã được bật mặc định; đoạn trên chỉ **làm rõ repository theo session**. Nếu cấu hình ứng dụng không có session và chỉ dùng bearer header do client chủ động gắn, cần đánh giá mô hình đe dọa của từng endpoint trước khi quyết định phạm vi bảo vệ.

### 7.2. Render token vào form MVC/Thymeleaf

Khi Spring Security đưa đối tượng `_csrf` vào request, template có thể lấy đúng tên parameter/token:

~~~html
<!-- template: profile/edit.html -->
<form method="post" action="/profile/email">
  <label for="email">Email mới</label>
  <input id="email" name="email" type="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Cập nhật</button>
</form>
~~~

Trong môi trường Spring MVC + Thymeleaf, một số tích hợp form như `th:action` có thể **tự chèn CSRF hidden field**. Hãy kiểm tra HTML kết quả để tránh thêm token trùng không cần thiết; ví dụ dùng `action` tĩnh nhằm thể hiện rõ trường token cần gửi.

Khi HTML đã render, server kiểm tra token khi form POST; controller nghiệp vụ không cần tự đọc `_csrf` để so với session.

### 7.3. Vì sao dùng header khi gửi JSON?

Endpoint nhận JSON thường không đọc hidden field `_csrf` từ body JSON như một form parameter. Client nên đưa token vào **header** mà Spring Security chấp nhận:

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json
X-CSRF-TOKEN: TOKEN_DUNG_DINH_DANG

{"theme":"dark"}
~~~

Tên header mặc định ở một số repository có thể là `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN`; hãy lấy từ `CsrfToken.getHeaderName()` hoặc cấu hình repository đang dùng. `TOKEN_DUNG_DINH_DANG` phải tương thích request handler, có thể là raw hoặc masked tùy trường hợp.

**Không nhúng một field `"_csrf"` bên trong JSON rồi mặc định cho rằng `CsrfFilter` sẽ tìm thấy nó**. Với handler mặc định, đưa token đúng header thường là lựa chọn rõ ràng nhất cho API dùng JSON.

### 7.4. Những request nào được so sánh?

Trong cấu hình CSRF mặc định điển hình, phương thức được xem là an toàn (`GET`, `HEAD`, `OPTIONS`, `TRACE`) thường không bị yêu cầu CSRF token; các phương thức như `POST`, `PUT`, `PATCH` và `DELETE` thường cần token.

Hệ quả: endpoint `GET /account/delete` mà thật sự xóa dữ liệu là **thiết kế sai**. Phải chuyển thao tác thay đổi trạng thái sang phương thức thích hợp và bảo vệ nó, thay vì trông chờ bộ lọc CSRF chặn GET.

Ứng dụng có thể cấu hình vùng áp dụng CSRF bằng matcher; cần kiểm tra đường dẫn có thực sự chạy qua `SecurityFilterChain` mong đợi không, nhất là khi có nhiều chain.

## 8. Spring Security Reactive/WebFlux: expected và submitted trong luồng reactive

Ở WebFlux, khái niệm không đổi nhưng các API mang tính reactive:

- `CsrfWebFilter` kiểm soát request cần bảo vệ.
- `ServerCsrfTokenRepository` chịu trách nhiệm lưu/tải/sinh token theo `ServerWebExchange`.
- `WebSessionServerCsrfTokenRepository` liên kết token với phiên reactive.
- Token có thể được cung cấp qua `Mono<CsrfToken>` và chỉ được tải/sinh khi luồng reactive thực sự sử dụng.

Ví dụ cấu hình theo `WebSession`:

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
class ReactiveWebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/assets/**").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

Một handler trả HTML view có thể **giải quyết Mono token** rồi đưa đối tượng token vào model:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveProfileController {

    @GetMapping("/profile/edit")
    Mono<Rendering> showEdit(ServerWebExchange exchange) {
        Mono<CsrfToken> token = exchange.getAttribute(
                CsrfToken.class.getName());

        return token.map(csrf ->
                Rendering.view("profile/edit")
                    .modelAttribute("_csrf", csrf)
                    .build());
    }
}
~~~

Ví dụ giả định request đã đi qua `CsrfWebFilter` và attribute chứa `Mono<CsrfToken>` như cách tích hợp WebFlux liên quan. Trong hệ thống thật cần kiểm tra tích hợp với view engine và request handler của phiên bản Spring Security đang dùng. Khi chọn repository bằng cookie cho SPA, expected có thể lấy từ cookie token thay vì `WebSession`; các lưu ý về cookie injection và biểu diễn token vẫn áp dụng.

**Khác nhau giữa hai stack là API và cơ chế bất đồng bộ; điều kiện bảo vệ không đổi:** lấy expected đúng ngữ cảnh server tin cậy, nhận submitted từ request rồi kiểm tra trước khi thực hiện thao tác có tác động.

## 9. Vòng đời giá trị dự kiến

### 9.1. Token chưa tồn tại

Khi repository không thấy token cho phiên hiện tại, nó có thể sinh token mới nếu luồng cần phát token; hành vi này phụ thuộc trạng thái request và cơ chế **deferred loading**.

Với request POST thiếu token, server không được cho qua chỉ vì đã sinh được một token mới. Submitted token vẫn phải khớp token hợp lệ theo chính sách, không chấp nhận trường hợp “không có token thì bỏ qua”.

### 9.2. Sau đăng nhập, đăng xuất hoặc thay phiên

Một số cấu hình Spring Security vô hiệu hóa token cũ khi người dùng xác thực/đăng xuất, để token trước một ranh giới bảo mật không tự tiếp tục hợp lệ. Với Servlet, có các thành phần như `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` tham gia quản lý vòng đời này.

Hệ quả thường gặp:

- SPA có thể giữ token trước login nhưng token kỳ vọng đã bị xóa; POST sau login trả `403`.
- Một tab mở form trước logout/login lại chứa token cũ; submit cần bị từ chối hoặc yêu cầu người dùng tải lại form.
- Session đã hết hạn làm token cũ mất ngữ cảnh; không được gắn nó sang phiên mới và coi là hợp lệ.

Cách khắc phục là **phát và sử dụng token mới** theo luồng xác thực, đồng thời xử lý UX rõ ràng; đừng tắt CSRF chỉ để tránh các request lỗi.

### 9.3. Nhiều tab và nhiều instance

Nếu token gốc được lưu theo session, hai tab cùng phiên thường có thể gửi cùng token dự kiến, nhưng nếu ứng dụng tự luân phiên token liên tục, một tab có thể trở nên lỗi thời.

Nếu triển khai nhiều instance, token dự kiến trong `HttpSession`/`WebSession` phải được truy cập nhất quán bởi node nhận POST. Có thể dùng kho phiên dùng chung hoặc cấu hình định tuyến phù hợp. Không nên chấp nhận submitted token tùy ý khi node khác không nhìn thấy expected token.

### 9.4. Những chỗ không nên lưu hoặc xuất token

Không đưa CSRF token vào URL, analytics, log đầy đủ request, sự kiện telemetry công khai hoặc response cache dùng chung. CSRF token không phải mật khẩu nhưng là bằng chứng để vượt lớp kiểm tra request. Cần bảo vệ nó khỏi website ngoài và tránh rò rỉ qua XSS.

Cookie xác thực nên áp dụng `Secure`, `HttpOnly` và `SameSite` phù hợp. Với cookie **CSRF** mà SPA cần đọc từ `document.cookie`, `HttpOnly` có thể không được bật; điều đó khác với cookie phiên xác thực và phải được cân nhắc riêng.

## 10. Thực hành kiểm thử expected/submitted

Để xác minh cơ chế thực sự hoạt động, cần chạy request **qua security filter chain**, không chỉ gọi trực tiếp controller.

### 10.1. Ma trận kiểm thử cơ bản

| Trường hợp | Expected phía server | Submitted phía client | Kết quả mong đợi |
|---|---|---|---|
| Token đúng | Token A của phiên A | A | Qua bước CSRF |
| Thiếu submitted | Token A | Không có | Bị từ chối |
| Submitted sai | Token A | X | Bị từ chối |
| Hoán đổi phiên | Token A của phiên A | Token B của phiên B | Bị từ chối |
| Session hết hạn | Không còn expected A hợp lệ | Token A cũ | Không được thực hiện thao tác dưới phiên A |
| Request GET chỉ đọc | Có hoặc không | Không có | Không yêu cầu token theo mặc định |
| Request có token đúng nhưng không có quyền nghiệp vụ | Khớp | Khớp | Có thể qua CSRF, nhưng vẫn bị chặn ở xác thực/phân quyền |
| Token render masked | Raw token R | Masked M hợp lệ cho R | Qua kiểm tra sau khi handler xử lý M |

Trong các test có mock user, request không nhất thiết dùng cookie trình duyệt như sản phẩm thật. Các helper kiểm thử xác nhận hành vi cơ bản; muốn kiểm tra **liên kết phiên**, cần test thêm luồng tạo hai session thực và trao đổi token.

### 10.2. Kiểm thử Servlet với MockMvc

Với ứng dụng Spring Boot MVC đã có một endpoint POST hợp lệ và `spring-security-test`:

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
class CsrfServletTokenTests {

    @Autowired MockMvc mvc;

    @Test
    void missingSubmittedTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .param("email", "alice@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongSubmittedTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("email", "alice@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validTokenPassesCsrfCheck() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf())
                .param("email", "alice@example.test"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Test cuối giả định endpoint chuyển hướng thành công như một form MVC điển hình. Nếu endpoint trả JSON/`204` hoặc có validation/quyền riêng, assertion phải điều chỉnh. `with(csrf())` là helper của Spring Security Test, **không phải mô phỏng hoàn chỉnh** toàn bộ luồng browser lấy token từ HTML.

### 10.3. Kiểm thử WebFlux với WebTestClient

Với ứng dụng Reactive và `spring-security-test`, có thể gắn `springSecurity()` vào `WebTestClient`, rồi dùng `mockUser` và `csrf`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest
class CsrfReactiveTokenTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void missingTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .bodyValue("email=alice@example.test")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void submittedTokenPassesCsrfLayer() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/profile/email")
            .bodyValue("email=alice@example.test")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

Ở đây test cuối cũng giả định endpoint WebFlux thực tế trả redirect nếu hợp lệ. Đối với WebFlux có form parser/handler khác, cần đặt `Content-Type`, body và assertion phù hợp. Test helper xác nhận đường bảo vệ CSRF hoạt động, không tự xác minh kho phiên phân tán hoặc token signature tùy biến.

### 10.4. Kiểm tra trên trình duyệt thật

Một chuỗi kiểm thử tích hợp giúp phân biệt lỗi client với lỗi server:

1. Mở trang form; xem request GET có được phát token không, và HTML đã render ra token thực chưa.
2. Gửi form hợp lệ; xác minh trong Network có submitted token đúng **tên parameter/header**.
3. Xóa trường/header rồi gửi lại; xác minh thao tác không được thực hiện.
4. Sửa một phần token, gửi lại; xác minh bị từ chối.
5. Sử dụng hai phiên độc lập A/B; thử dùng token của A với cookie phiên B.
6. Đăng xuất/đăng nhập lại, gửi form cũ; xác minh token cũ không vượt qua kiểm chứng.
7. Thử trong trường hợp cross-site nếu cần đánh giá tấn công: xem cookie có **thực sự** được trình duyệt gửi theo `SameSite` và chính sách cookie hay không.

Một HTTP client có thể tùy ý gắn `Cookie`; điều đó hữu ích kiểm tra phía server nhưng **không đủ kết luận** trình duyệt nạn nhân sẽ gửi cookie tương tự trong một yêu cầu từ website ngoài.

## 11. Chẩn đoán các trường hợp không khớp

| Triệu chứng | Kiểm tra trước tiên | Cách khắc phục |
|---|---|---|
| HTML có form nhưng POST trả `403` | Hidden field `_csrf` có thật trong HTML cuối cùng không? | Đưa token thật từ framework vào form; tránh trường trùng/sai tên |
| SPA gửi JSON nhưng POST `403` | Có header CSRF không? Tên header đúng repository không? | Gửi token qua header cấu hình; không trông chờ server đọc field bất kỳ trong JSON |
| Cookie CSRF có nhưng header thiếu | Client có đọc được cookie và gắn header không? | Kiểm tra `HttpOnly`, cookie scope, khởi tạo token, HTTP client/interceptor |
| Header có raw token nhưng Spring báo invalid | Handler có kỳ vọng masked token không? | Cấu hình handler phù hợp với raw header và masked form |
| POST đầu tiên sau login thất bại | Token cũ bị xóa hoặc thay trong lúc xác thực? | Nhận token mới sau login trước khi POST |
| Một vài request lỗi sau scale-out | Node nhận POST có đọc đúng session/token không? | Đồng bộ session store hoặc chiến lược định tuyến |
| POST có token đúng nhưng `403` | Có thể bị chặn do authorization, matcher khác hoặc bảo vệ khác | Phân biệt lớp lỗi, kiểm tra filter chain và logs có kiểm soát |
| Tắt CSRF thì POST hoạt động | Đường gửi token sai hoặc cấu hình sai? | Sửa cơ chế phát/đọc/đối chiếu token, không tắt toàn cục |
| Có cookie và header giống nhau vẫn chưa an toàn | Token được xác minh theo phiên/HMAC chưa? Cookie có thể bị tiêm? | Đánh giá repository, cookie scope và cơ chế kiểm chứng |

Không nên log **toàn bộ token thật** để điều tra. Dùng thông tin như có/không token, tên nguồn, phiên bản cấu hình, filter xử lý và trạng thái kết quả đối chiếu. Với Servlet, có thể gặp các ngoại lệ như `MissingCsrfTokenException` hay `InvalidCsrfTokenException`; với Reactive phải nhìn đúng luồng `CsrfWebFilter` và cấu hình liên quan. HTTP `403` tự nó chưa đủ để xác định lỗi CSRF.

## 12. Bài tập tình huống

**Tình huống A — đúng tên trường nhưng sai phiên.**

Server có expected token `T_A` trong session A. Client gửi `T_B` do server phát hành cho session B trong tham số `_csrf`, đồng thời cookie xác thực vẫn trỏ đến session A.

**Phân tích:** Request phải bị từ chối. Server cần tải expected theo **session A của request**, không theo account hoặc theo submitted token.

**Tình huống B — token masked thay đổi khi refresh.**

Người dùng mở cùng form hai lần, thấy hai chuỗi token khác nhau trong HTML. Cả hai request POST tương ứng vẫn hợp lệ.

**Phân tích:** Hai chuỗi có thể là hai biểu diễn XOR khác nhau của cùng raw token theo phiên. Không được kết luận repository đã tự thay token gốc sau mỗi GET.

**Tình huống C — frontend chỉ gửi JSON field.**

SPA gửi `{"displayName":"Alice","_csrf":"T_A"}` dưới `Content-Type: application/json` nhưng `CsrfFilter` không đọc submitted token từ JSON body tùy ý.

**Phân tích:** Client nên gửi token trong **header CSRF** theo cấu hình của Spring Security. Không nên mở rộng parser không cần thiết chỉ để tạo một đường xử lý token mới.

**Tình huống D — expected lấy từ cookie.**

Server đọc cookie `XSRF-TOKEN=T` và nhận header `X-XSRF-TOKEN=T`, rồi cho rằng mọi request đều an toàn vì hai chuỗi khớp.

**Phân tích:** Đây là điều kiện equality của một dạng double-submit. Cần kiểm tra **attacker có thể điều khiển cookie CSRF hay không**, cách quản lý `Domain`/`Path`, khả năng duplicate cookie và cơ chế ký/ràng buộc phiên nếu dùng signed double-submit.

**Tình huống E — session hết hạn.**

Form chứa submitted token cũ được giữ mở qua lúc session hết hạn. Người dùng gửi lại và nhận `403` hoặc bị chuyển về đăng nhập.

**Phân tích:** Token không còn tương ứng với expected của một phiên hợp lệ. Nên yêu cầu tải lại form/nhận token mới sau khi xác thực thay vì chấp nhận token cũ.

## Kết luận

Phòng vệ CSRF bằng token xoay quanh hai giá trị: **expected token** đến từ repository/ngữ cảnh phía server tin cậy và **submitted token** được form hoặc client chủ động gửi trong HTTP request. Spring Security chọn request cần bảo vệ, tải giá trị dự kiến, giải quyết biểu diễn token client gửi rồi **đối chiếu chúng trước khi cho thao tác thay đổi trạng thái diễn ra**.

Trong **Servlet**, các thành phần tiêu biểu là `CsrfFilter`, `CsrfTokenRepository`, `HttpSessionCsrfTokenRepository` và `CsrfTokenRequestHandler`. Trong **Reactive**, vai trò tương ứng nằm ở `CsrfWebFilter`, `ServerCsrfTokenRepository` và `WebSessionServerCsrfTokenRepository`. Việc triển khai đúng đòi hỏi chọn nơi lưu expected rõ ràng, giữ đúng mối liên kết với phiên, gửi submitted qua field/header hợp lệ, xử lý masking và vòng đời token, rồi kiểm thử thiếu/sai/khác phiên trên chuỗi bảo mật thực tế. Đây là lớp bảo vệ quan trọng trong hệ thống Spring Security HTTP protection cùng bảo vệ session, cookie, CORS, CSP, security headers, HSTS và HTTP firewall.
