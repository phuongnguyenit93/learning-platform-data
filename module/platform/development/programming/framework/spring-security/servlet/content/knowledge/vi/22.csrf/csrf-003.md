# CsrfToken, CsrfTokenRepository và CsrfTokenRequestHandler trong Spring Security Servlet

> **Phạm vi:** ứng dụng Spring MVC/Servlet sử dụng Spring Security 6.x, Java 17+ (thường đi cùng Spring Boot 3.x). Bài này tập trung vào cơ chế CSRF của **Servlet filter chain**, không áp dụng nguyên xi cho Spring WebFlux. Cấu hình và ví dụ giả định ứng dụng xác thực người dùng bằng cookie phiên.

## 1. Vì sao cần CSRF token?

**Cross-Site Request Forgery (CSRF)** xảy ra khi trình duyệt của nạn nhân đang đăng nhập một website, rồi một website khác khiến trình duyệt gửi yêu cầu thay đổi trạng thái đến website đó. Trình duyệt có thể tự đính kèm cookie đăng nhập; nếu máy chủ chỉ kiểm tra cookie, nó khó phân biệt yêu cầu do người dùng chủ động gửi với yêu cầu bị dụ gửi.

Ví dụ: người dùng đăng nhập `https://app.example`, sau đó truy cập trang độc hại chứa form gửi `POST /profile/change-email`. Nếu backend chỉ dựa vào cookie phiên, yêu cầu giả mạo có thể được xử lý. Khi bật CSRF protection, backend yêu cầu một **token khó đoán, gắn với ngữ cảnh hợp lệ**, đi kèm yêu cầu thay đổi dữ liệu. Trang ngoài nguồn gốc không thể tùy ý đọc token từ website đích trong mô hình trình duyệt thông thường.

- Các phương thức được xem là an toàn về mặt ngữ nghĩa HTTP (`GET`, `HEAD`, `OPTIONS`, `TRACE`) thường không bị yêu cầu CSRF token theo cấu hình mặc định. `POST`, `PUT`, `PATCH`, `DELETE` thuộc diện phải kiểm tra. Vì vậy **GET không được thực hiện hành động thay đổi trạng thái**.
- CSRF đặc biệt quan trọng khi **trình duyệt tự gửi thông tin xác thực**, chẳng hạn session cookie. Một API chỉ nhận Bearer token do JavaScript chủ động đưa vào `Authorization` có thể có mô hình rủi ro khác, nhưng phải đánh giá toàn bộ cơ chế xác thực thực tế trước khi loại trừ CSRF.
- `SameSite` cookie, CORS, kiểm tra `Origin`/`Referer` và CSRF token giải quyết các khía cạnh khác nhau. CORS không ngăn mọi kiểu gửi request từ website khác; `SameSite` có giới hạn theo cách triển khai. Không thay thế việc đánh giá CSRF bằng giả định “API chỉ nhận JSON”.
- CSRF token **không phải biện pháp chống XSS**. Nếu kẻ tấn công chạy được JavaScript trên chính origin tin cậy, họ thường có thể sử dụng luồng gửi request hợp lệ.

## 2. Ba thành phần: ai giữ token, ai lưu, ai đọc request?

| Thành phần | Trách nhiệm chính | Không có trách nhiệm |
| --- | --- | --- |
| `CsrfToken` | Mô tả token cần gửi: tên header, tên request parameter, giá trị token. | Không tự đọc request hoặc quản lý kho lưu trữ. |
| `CsrfTokenRepository` | Sinh token, lưu token, tải token từ nơi lưu trữ; hỗ trợ truy xuất trì hoãn. | Không quyết định token client vừa gửi nằm trong header hay form, không quyết định cách mask giá trị hiển thị. |
| `CsrfTokenRequestHandler` | Đưa token vào request attribute cho tầng hiển thị và giải quyết **giá trị token do client gửi** (header/parameter, có thể cần giải mã dạng mask). | Không quyết định token đúng/sai bằng cách tự kiểm tra kho lưu trữ. |
| `CsrfFilter` | Điều phối repository và handler, kiểm tra token trên request cần bảo vệ, từ chối request không hợp lệ. | Không thay thế các thành phần trên bằng một đối tượng duy nhất. |

Mối quan hệ trong một yêu cầu Servlet:

~~~text
HTTP request
    |
    v
Spring Security filter chain
    |
    v
CsrfFilter
    |--- CsrfTokenRepository: lấy DeferredCsrfToken
    |--- CsrfTokenRequestHandler.handle(...): chuẩn bị request attribute
    |
    +--- Request an toàn (thường GET) --> xử lý tiếp;
    |        nếu view/controller truy cập token thì token được load/generate
    |
    +--- Request cần bảo vệ (thường POST/PUT/PATCH/DELETE)
             |--- tải token kỳ vọng qua repository
             |--- requestHandler.resolveCsrfTokenValue(...): lấy token gửi lên
             |--- so sánh token gửi lên với token kỳ vọng
                     |--- hợp lệ --> filter chain tiếp tục
                     +--- thiếu/sai --> AccessDeniedHandler (thường HTTP 403)
~~~

Điểm cốt lõi: repository trả lời **“server đang mong token nào?”**; request handler trả lời **“client thực sự gửi token nào, dưới dạng nào?”**; `CsrfFilter` đối chiếu hai kết quả.

## 3. `CsrfToken`: hợp đồng dữ liệu nhỏ nhưng quan trọng

`org.springframework.security.web.csrf.CsrfToken` là interface có ba phương thức:

~~~java
public interface CsrfToken {
    String getHeaderName();
    String getParameterName();
    String getToken();
}
~~~

- `getHeaderName()`: tên HTTP header client có thể gửi token, ví dụ `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN`.
- `getParameterName()`: tên form parameter, mặc định thường là `_csrf`.
- `getToken()`: giá trị cần trình bày/gửi theo cơ chế request handler. Cần phân biệt **token gốc được lưu** với **giá trị đã mask dùng trong form** ở mục 5.

`DefaultCsrfToken` là một implementation dùng để mang ba thuộc tính này. Không tự tạo token bằng chuỗi cố định hoặc đưa token vào source code. Token phải được sinh và quản lý theo vòng đời phù hợp, bởi repository.

Ví dụ về một request form hợp lệ theo hướng server-rendered:

~~~html
<form method="post" action="/profile">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_RENDER">
  <button type="submit">Lưu thay đổi</button>
</form>
~~~

`TOKEN_DO_SERVER_RENDER` là **ký hiệu minh họa**, không phải giá trị thật hay câu lệnh có thể copy nguyên. Tầng template phải chèn đúng token dành cho request hiện tại. Với Thymeleaf và Spring Security, có thể lấy token từ request attribute `_csrf`:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

Spring Security có thể tự thêm hidden field trong các form được tích hợp đúng với cơ chế render của Spring MVC/Thymeleaf; nếu tự dựng form, cần kiểm tra HTML thực tế để chắc chắn token đã được gửi. Với handler dạng XOR, giá trị render cho form có thể **khác chuỗi token gốc** mà repository lưu; điều này là chủ đích.

## 4. `CsrfTokenRepository`: sinh, lưu, tải và trì hoãn tải token

Hợp đồng cốt lõi:

~~~java
public interface CsrfTokenRepository {
    CsrfToken generateToken(HttpServletRequest request);

    void saveToken(
        CsrfToken token,
        HttpServletRequest request,
        HttpServletResponse response
    );

    CsrfToken loadToken(HttpServletRequest request);
}
~~~

Các bản Spring Security hiện đại còn hỗ trợ `loadDeferredToken(request, response)`, trả về `DeferredCsrfToken` để trì hoãn việc tải/sinh token cho đến khi cần. Tính trì hoãn giúp tránh tạo session hoặc truy xuất dữ liệu phiên ở những request không hề sử dụng CSRF token. Khi mã xử lý thực sự truy cập token, quá trình lấy/sinh/lưu mới xảy ra.

### Hai repository thường gặp

**`HttpSessionCsrfTokenRepository`**

- Lưu token trong `HttpSession` trên server; thích hợp cho ứng dụng MVC đăng nhập bằng session và form server-rendered.
- Token được đối chiếu với dữ liệu thuộc session của trình duyệt. Trình duyệt thường chỉ cần cookie session; form/JS nhận token riêng để gửi lên.
- Đây là cách lưu mặc định thông dụng của Spring Security Servlet. Không cần tự chuyển sang cookie repository nếu ứng dụng chỉ dùng form và session.

**`CookieCsrfTokenRepository`**

- Lưu token trong cookie; tên cookie mặc định thường là `XSRF-TOKEN`, HTTP header mặc định là `X-XSRF-TOKEN` và parameter là `_csrf`. Mô hình này thường được dùng khi một SPA cần lấy token từ cookie và đính vào header.
- Cookie chứa CSRF token **khác với cookie xác thực**. Client vẫn phải gửi token qua header/parameter tương ứng; chỉ có cookie tự gửi kèm không đủ làm bằng chứng chủ động của request.
- `CookieCsrfTokenRepository.withHttpOnlyFalse()` cho phép JavaScript đọc cookie CSRF để đặt header. Chỉ dùng khi luồng client cần làm vậy; thuộc tính `HttpOnly=false` khiến giá trị này có thể bị script trên origin đọc. Bảo vệ XSS và chính sách cookie vẫn quan trọng.
- Cần cấu hình `Secure`, `SameSite`, `Path`, miền cookie và reverse proxy theo môi trường triển khai. Không giả định mọi SPA hoặc cross-origin deployment đều hoạt động với thiết lập mặc định.

### Sinh và xóa token

- `generateToken` tạo một `CsrfToken` mới; `saveToken` chịu trách nhiệm lưu. `loadToken` trả về token đã lưu hoặc `null` khi chưa có.
- `saveToken(null, request, response)` được dùng để xóa/đánh dấu mất hiệu lực token đã lưu; cách xóa phụ thuộc repository. Các cơ chế authentication thành công/logout có thể dọn token cũ nhằm tránh tiếp tục dùng token trước biến cố bảo mật.
- Khi token bị xóa và việc tạo token mới bị trì hoãn, SPA có thể phải gọi lại một request khởi tạo CSRF trước lần `POST` tiếp theo. Điều này giải thích trường hợp “đăng nhập xong, POST đầu tiên nhận 403” dù phiên đăng nhập đã hợp lệ.

Không lưu token vào log, analytics hoặc URL query string. Không nhúng token dùng chung cho mọi người dùng vào HTML tĩnh được cache công khai.

## 5. `CsrfTokenRequestHandler`: request attribute và cách đọc token gửi lên

Hai phương thức quyết định của `CsrfTokenRequestHandler`:

~~~java
void handle(
    HttpServletRequest request,
    HttpServletResponse response,
    Supplier<CsrfToken> deferredCsrfToken
);

String resolveCsrfTokenValue(
    HttpServletRequest request,
    CsrfToken csrfToken
);
~~~

`handle` nhận supplier để chuẩn bị cách token được công bố cho request hiện tại, chẳng hạn thuộc tính `_csrf` trong MVC. Nó không nhất thiết phải gọi `get()` ngay, nên có thể giữ cơ chế deferred. `resolveCsrfTokenValue` nhận request cùng token kỳ vọng để tìm hoặc biến đổi **giá trị do client nộp**; `CsrfFilter` mới là nơi kiểm tra xem hai giá trị có khớp hay không.

### `CsrfTokenRequestAttributeHandler`: giá trị thông thường

Handler này công bố token trong request attribute và đọc giá trị được gửi qua header hoặc parameter. Với luồng không mask, giá trị hiển thị thường tương ứng trực tiếp với token gốc. Nó phù hợp khi muốn xử lý token “plain”, nhưng **không tự mang lại cơ chế mask chống BREACH** cho các token được đưa vào HTML.

### `XorCsrfTokenRequestAttributeHandler`: mask để giảm rủi ro BREACH

Spring Security 6 sử dụng `XorCsrfTokenRequestAttributeHandler` theo mặc định trong cấu hình Servlet CSRF phổ biến. Khi token xuất hiện trong phản hồi nén (ví dụ HTML form), việc lặp lại token gốc có thể tạo tín hiệu cho tấn công kiểu **BREACH**. Handler XOR thêm nhiễu ngẫu nhiên/mask lên giá trị công bố trong mỗi lần render, rồi giải mã giá trị form gửi về để so sánh với token gốc.

Cần phân biệt:

- **Token gốc**: giá trị repository đang lưu; không có nghĩa thay đổi sau mỗi GET.
- **Giá trị token đã mask**: có thể khác nhau giữa các lần render, nhưng vẫn đại diện cho cùng token gốc.
- **Giá trị client gửi**: form server-rendered có thể gửi giá trị đã mask; SPA đọc token từ cookie lại có **giá trị gốc**. Vì vậy, dùng sai handler để đọc loại giá trị này có thể dẫn đến HTTP 403.

Không được hiểu “token thay đổi trên mỗi lần render” là “repository đã sinh token mới mỗi lần”. Đó có thể chỉ là khác biệt ở cách biểu diễn bảo vệ BREACH.

### Chọn handler đúng với đường gửi token

| Luồng client | Token lấy ở đâu | Cách gửi | Yêu cầu với request handler |
| --- | --- | --- | --- |
| Form MVC/Thymeleaf | Request attribute do Spring Security công bố | Hidden parameter `_csrf` | Handler tương thích token render, mặc định XOR đáp ứng. |
| JavaScript lấy token từ cookie | Cookie `XSRF-TOKEN` đọc được qua JS | Header `X-XSRF-TOKEN` | Phải chấp nhận token gốc từ header. |
| Ứng dụng vừa render form vừa dùng SPA | Form: mask; JS: cookie gốc | Parameter và header | Handler phải xử lý đúng **cả hai dạng**, không tự đồng nhất chúng. |

## 6. Cấu hình ứng dụng MVC thông thường: giữ mặc định

Với ứng dụng server-rendered đăng nhập bằng session, thường chỉ cần cấu hình authentication và authorization, còn CSRF dùng mặc định. Đoạn sau là một lớp cấu hình Spring Boot có dependency `spring-boot-starter-security` và `spring-boot-starter-web`; không chạy độc lập bằng lệnh `javac` khi thiếu thư viện Spring:

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Khi trang GET hiển thị form thay đổi dữ liệu, template lấy token từ `_csrf` và gắn vào form POST. Browser gửi session cookie cùng hidden parameter; `CsrfFilter` tìm token kỳ vọng qua session repository, nhờ handler giải mã token đã mask (nếu có), rồi đối chiếu. Nếu thiếu/sai token, response thường là 403 ngay tại filter, trước khi controller xử lý nghiệp vụ.

**Lưu ý:** nên dùng cấu hình này **hoặc** cấu hình SPA ở mục 7 cho một filter chain tương ứng. Không copy cả hai bean `SecurityFilterChain` có matcher bao trùm mọi request vào cùng một ứng dụng.

## 7. Trường hợp SPA đọc cookie: phối hợp repository và handler

Ví dụ này dành cho SPA **cùng origin** với backend, xác thực bằng cookie phiên, cần đọc `XSRF-TOKEN` để gửi header. Nó giữ XOR cho form/server-rendered, nhưng nhận raw token khi request có header. Đây là một phương án cấu hình có chủ đích; không phải mặc định phù hợp với mọi kiến trúc.

**Tệp `SpaCsrfTokenRequestHandler.java`:**

~~~java
package demo.security;

import java.util.function.Supplier;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> deferredCsrfToken) {
        // Giữ giá trị đã mask cho form HTML.
        xor.handle(request, response, deferredCsrfToken);

        // Buộc load/generate token để repository có thể gửi cookie.
        deferredCsrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());

        // Header SPA: raw token; form parameter: token đã mask.
        CsrfTokenRequestHandler handler =
                headerValue != null && !headerValue.isBlank()
                        ? plain
                        : xor;

        return handler.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

**Tệp `SpaSecurityConfig.java`:**

~~~java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

@Configuration
@EnableWebSecurity
public class SpaSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/csrf", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
                .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()));

        return http.build();
    }
}
~~~

**Tệp `CsrfBootstrapController.java`:**

~~~java
package demo.security;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfBootstrapController {

    @GetMapping("/csrf")
    public ResponseEntity<Void> bootstrap() {
        // CSRF filter đã kích hoạt load token trước controller.
        return ResponseEntity.noContent().build();
    }
}
~~~

Ở đây, `GET /csrf` chỉ là request khởi tạo để response có cơ hội phát hành cookie; controller không trả token trong body. Với `SpaCsrfTokenRequestHandler`, `deferredCsrfToken.get()` bảo đảm token được load hoặc sinh, thay vì chỉ dựa vào việc MVC view có đọc token hay không.

**JavaScript client (minh họa cho same-origin browser):**

~~~javascript
// Khởi tạo lại token khi mở app và sau những lần đổi trạng thái auth.
await fetch("/csrf", { credentials: "same-origin" });

const pair = document.cookie
    .split("; ")
    .find(value => value.startsWith("XSRF-TOKEN="));

if (!pair) {
    throw new Error("Thiếu XSRF-TOKEN cookie; kiểm tra GET /csrf và cookie policy");
}

const csrfToken = decodeURIComponent(pair.slice("XSRF-TOKEN=".length));

const response = await fetch("/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": csrfToken
    },
    body: JSON.stringify({ displayName: "Lan" })
});

if (!response.ok) {
    throw new Error("Lưu hồ sơ thất bại: HTTP " + response.status);
}
~~~

Cần có endpoint `POST /profile` và người dùng đăng nhập phù hợp; đoạn JavaScript không tạo ra các thành phần đó. `GET /csrf` có thể vẫn phải gọi lại sau login/logout vì token cũ đã bị vô hiệu. Nếu ứng dụng vận hành nhiều origin, phải bổ sung phân tích cookie/CORS/credentials/CSRF riêng, không dùng nguyên ví dụ same-origin.

### Vì sao chỉ đặt `CookieCsrfTokenRepository.withHttpOnlyFalse()` có thể chưa đủ?

Repository quyết định token trong cookie và header mong đợi; **request handler** mặc định vẫn có thể mong token đã mask theo cơ chế XOR. Nếu JavaScript đọc **raw token** từ cookie và gửi header trong khi handler giải mã như token XOR, request có thể bị 403. Handler phối hợp trong ví dụ phân nhánh dựa vào header để chọn cách giải quyết, đồng thời tiếp tục công bố giá trị mask cho form.

Không dùng `CsrfTokenRequestAttributeHandler` không mask trên mọi request chỉ để chữa 403 mà không đánh giá tác động BREACH lên các trang phản hồi có token trong HTML.

## 8. Vòng đời cụ thể: đọc, tạo, sử dụng, làm mới

### 8.1 Trang MVC server-rendered

1. Trình duyệt gửi `GET /profile` cùng session cookie.
2. `CsrfFilter` lấy deferred token từ repository. Handler chuẩn bị request attribute `_csrf`.
3. Khi view truy cập `_csrf.token`, token được load/sinh. Nếu dùng XOR handler, token công bố cho form là phiên bản mask.
4. View render hidden field với đúng tên parameter và giá trị token.
5. Trình duyệt gửi `POST /profile` với cookie phiên và parameter `_csrf`.
6. Filter lấy token server kỳ vọng, handler giải mã/đọc token trong request; hợp lệ thì controller mới được chạy.

### 8.2 SPA dùng cookie CSRF

1. SPA gọi `GET /csrf` để trình duyệt nhận hoặc cập nhật cookie `XSRF-TOKEN`.
2. Client đọc cookie, gửi token gốc trong `X-XSRF-TOKEN` trên yêu cầu thay đổi trạng thái.
3. Filter tải token kỳ vọng qua `CookieCsrfTokenRepository`; handler phân nhánh dùng đường đọc plain header.
4. Sau login/logout hoặc khi đổi session, client thực hiện bước khởi tạo lại token nếu token cũ bị xóa.

### 8.3 Token thiếu hoặc không hợp lệ

- Không có token kỳ vọng trong repository: request bảo vệ bị từ chối, thông thường 403.
- Có token phía server nhưng client không gửi parameter/header: thông thường 403.
- Client gửi token của session khác, token đã cũ, tên header sai hoặc token raw đi vào handler kỳ vọng mask: thông thường 403.
- Một 403 **không tự chứng minh** rằng lỗi nằm ở CSRF; authentication, authorization, exception handling hoặc controller cũng có thể gây lỗi. Xác định filter/exception thực sự trước khi sửa.

## 9. Kiểm thử CSRF bằng MockMvc

Đối với Spring MVC, dependency test `org.springframework.security:spring-security-test` cung cấp `csrf()`. Ví dụ sau giả định ứng dụng ở mục 6 có controller `POST /profile` trả HTTP 200 khi đã qua security:

~~~java
package demo.security;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @PostMapping("/profile")
    public String saveProfile() {
        return "saved";
    }
}
~~~

~~~java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfContractTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rejectPostWithoutCsrf() throws Exception {
        mvc.perform(post("/profile").with(user("alice")))
           .andExpect(status().isForbidden());
    }

    @Test
    void acceptPostWithCsrf() throws Exception {
        mvc.perform(post("/profile")
                .with(user("alice"))
                .with(csrf()))
           .andExpect(status().isOk());
    }

    @Test
    void rejectInvalidToken() throws Exception {
        mvc.perform(post("/profile")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
           .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ yêu cầu project Spring Boot với MVC, Security, `spring-security-test`, JUnit 5 và ứng dụng khởi động được. Đặt cả cấu hình, controller và test trong package được Spring Boot component-scan. Chạy qua Gradle/Maven của dự án (ví dụ `./gradlew test`), **không** kỳ vọng có thể biên dịch độc lập chỉ bằng `javac`. Test này minh họa contract CSRF của cấu hình MVC ở mục 6; khi kiểm tra SPA, nên có thêm integration test sử dụng cookie repository, header `X-XSRF-TOKEN` và cơ chế load token thực tế.

Kiểm tra cả trường hợp thành công **và** thất bại. Một endpoint trả 403 vì chưa đăng nhập chưa chứng minh CSRF hoạt động; đó là lý do test cấp quyền cho user trước khi kiểm tra token.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Form POST trả 403 dù đã đăng nhập | Form thiếu `_csrf`, render sai tên/giá trị, session mất, token đã bị vô hiệu. | Kiểm tra HTML form, request payload và session; dùng token của request hiện tại. |
| SPA POST đầu tiên sau login trả 403 | Token cookie bị xóa khi đổi trạng thái auth; token mới chưa được khởi tạo do deferred loading. | Gọi bootstrap GET làm phát sinh token/cookie sau login rồi mới POST. |
| Cookie `XSRF-TOKEN` tồn tại nhưng header vẫn không hợp lệ | Client không gửi `X-XSRF-TOKEN`; gửi sai giá trị; handler cố giải XOR giá trị raw. | Kiểm tra header thực tế và chiến lược request handler. |
| Token trong HTML đổi sau mỗi reload | Handler XOR sinh biểu diễn mask mới. | Phân biệt mask với token gốc trước khi kết luận repository đang rotate. |
| Dùng `csrf().disable()` thì hết 403 | Chính sách CSRF đang chặn request, có thể do client truyền sai token. | Sửa đường phát hành/gửi/resolve token; chỉ vô hiệu CSRF nếu threat model cho phép và đúng filter chain. |
| Cùng một POST hoạt động qua MockMvc nhưng lỗi trên browser | Browser còn ràng buộc cookie path/domain, SameSite, Secure, credentials, Origin. | Kiểm tra Network request/response headers và môi trường reverse proxy. |
| Form GET có side effect | Thiết kế endpoint vi phạm ngữ nghĩa safe method; GET thường không cần CSRF token. | Chuyển thao tác thay đổi dữ liệu sang phương thức bảo vệ và thêm token. |

Khi chẩn đoán:

1. Xác định request đang đi vào `SecurityFilterChain` nào; với nhiều chain, CSRF config có thể khác nhau.
2. Xác định repository đang lưu ở session hay cookie, và request thật có mang đúng session/cookie hay không.
3. Xác định handler đang nhận **plain header** hay **masked parameter**; kiểm tra tên header/parameter thay vì giả định.
4. So sánh sự hiện diện và vòng đời token mà **không ghi giá trị bí mật vào log**. Bật log debug cho security có kiểm soát, tránh log request body/header chứa token trong môi trường thực.
5. Kiểm tra biến cố login, logout, session expiration, cookie domain/path, proxy và trình duyệt. Chỉ sau đó mới điều chỉnh matcher hay cấu hình CSRF.

## 11. Khi nào nên tùy chỉnh?

- **Ứng dụng form/session tiêu chuẩn:** ưu tiên mặc định `HttpSessionCsrfTokenRepository` và XOR handler. Phần lớn ứng dụng không cần tự triển khai repository/handler.
- **SPA dùng cookie phiên và tự thêm CSRF header:** cân nhắc `CookieCsrfTokenRepository` và handler hiểu đúng raw header; quyết định rõ có cần `HttpOnly=false` và cách khởi tạo token.
- **Tích hợp đặc thù:** chỉ viết `CsrfTokenRepository` tùy chỉnh khi thực sự cần một kho lưu trữ/chu kỳ token khác (ví dụ hệ thống lưu phân tán với ràng buộc rõ); kiểm thử sinh/lưu/tải/xóa, concurrent requests và session boundary.
- **Webhook/API không dùng cookie xác thực:** xem xét cấu hình chain/matcher tách biệt nếu request không thể bị lợi dụng thông qua cơ chế browser tự xác thực. Webhook vẫn cần cơ chế xác thực riêng (chữ ký/HMAC hoặc tương đương), không chỉ loại CSRF.
- **Multi-chain application:** dùng `securityMatcher`/thứ tự chain có chủ đích; cấu hình CSRF của một chain không có nghĩa tự áp dụng cho request xử lý bởi chain khác.

## 12. Tự kiểm tra kiến thức

1. Khi `POST /transfer` thiếu CSRF token, thành phần nào đọc token kỳ vọng, thành phần nào giải quyết token client gửi và thành phần nào từ chối request? **Đáp án:** repository, request handler, rồi `CsrfFilter`.
2. Vì sao `_csrf.token` ở HTML có thể khác mỗi lần render nhưng token trong session không đổi? **Đáp án:** XOR handler tạo biểu diễn mask khác, không nhất thiết tạo token gốc mới.
3. Vì sao chuyển từ session repository sang cookie repository có thể làm SPA 403? **Đáp án:** tên/nguồn token, khả năng JS đọc cookie, việc gửi header và cách handler giải plain/masked token phải tương thích.
4. Khi nào cần gọi `GET /csrf` sau login? **Đáp án:** khi token cũ bị xóa và token mới được load/generate theo yêu cầu; SPA cần nhận token trước request thay đổi trạng thái.
5. Vì sao `with(csrf())` trong test chưa đủ kết luận toàn bộ authorization đúng? **Đáp án:** helper chỉ cung cấp CSRF token hợp lệ; authentication/authorization và nghiệp vụ vẫn được kiểm tra riêng.

**Ghi nhớ:** `CsrfToken` mang dữ liệu token; `CsrfTokenRepository` quản lý token phía server; `CsrfTokenRequestHandler` định dạng/công bố token và đọc giá trị client nộp; `CsrfFilter` điều phối và quyết định chặn request không có token hợp lệ.