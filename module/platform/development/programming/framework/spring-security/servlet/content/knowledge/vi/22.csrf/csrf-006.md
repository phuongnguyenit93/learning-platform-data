# Token CSRF tải trì hoãn và cơ chế che token để giảm rủi ro BREACH

> **Phạm vi:** Spring Security trên Servlet stack (Spring MVC, Spring Boot 3.x, Spring Security 6.x; Java 17+). Bài này giải thích hai cơ chế liên quan đến CSRF nhưng giải quyết hai vấn đề khác nhau: **deferred CSRF token** giúp không tải/tạo token khi chưa cần, còn **XOR masking** thay đổi giá trị token được đưa ra phản hồi để hạn chế rò rỉ qua kênh phụ dựa trên nén HTTP (BREACH). Cả hai vẫn hoạt động cùng `CsrfFilter` và `CsrfTokenRepository`.

## 1. Nắm đúng vấn đề trước khi cấu hình

CSRF (Cross-Site Request Forgery) xuất hiện khi trình duyệt tự đính kèm thông tin xác thực (đặc biệt là session cookie) vào một yêu cầu do trang khác kích hoạt. Nếu máy chủ chỉ kiểm tra cookie, kẻ tấn công có thể tìm cách khiến người dùng đã đăng nhập gửi yêu cầu thay đổi trạng thái. Token CSRF là một giá trị khó đoán mà trang hợp lệ phải đưa thêm vào yêu cầu; máy chủ đối chiếu giá trị này với token gắn với ngữ cảnh người dùng.

BREACH là một kiểu tấn công kênh phụ khác: khi phản hồi HTTPS **có nén**, phản hồi đồng thời chứa một bí mật ổn định và dữ liệu mà đối thủ có thể ảnh hưởng, kích thước bản nén qua nhiều lần truy vấn có thể tiết lộ từng phần bí mật. TLS không tự che giấu kích thước phản hồi. Nếu một form HTML luôn nhúng nguyên văn cùng một token CSRF của session, token đó có thể trở thành mục tiêu của kênh phụ nén trong những điều kiện thích hợp.

| Cơ chế | Câu hỏi cần giải quyết | Hiệu quả chính |
| --- | --- | --- |
| **Tải trì hoãn** (`deferred token`) | Request này có thực sự cần đọc/tạo token từ repository không? | Tránh truy cập session hoặc tạo token không cần thiết trên các request chỉ đọc không dùng token. |
| **Che token bằng XOR** (`XorCsrfTokenRequestAttributeHandler`) | Làm sao tránh phản hồi liên tiếp chứa cùng chuỗi token bí mật? | Mỗi lần token được đưa vào phản hồi, tạo một biểu diễn ngẫu nhiên khác nhau; khi nhận request, giải mã để kiểm tra token gốc. |

**Không nhầm lẫn:** tải trì hoãn là tối ưu vòng đời token; XOR masking là biện pháp giảm rủi ro lộ token qua nén. Tắt một cơ chế không phải là cách bật cơ chế kia. Masking không thay thế kiểm tra CSRF, xác thực, kiểm soát XSS hoặc chính sách cookie.

## 2. Token đi qua Servlet filter chain như thế nào?

Trong luồng thông thường:

1. `CsrfFilter` nhận request và lấy một đối tượng **deferred token** từ `CsrfTokenRepository`. Repository thường lưu token gốc trong HTTP session (`HttpSessionCsrfTokenRepository`), hoặc lưu trong cookie nếu ứng dụng chọn `CookieCsrfTokenRepository`.
2. `CsrfTokenRequestHandler` công bố token cho phần còn lại của request (chẳng hạn thuộc tính `_csrf` dùng trong template). Với request handler có XOR, giá trị công bố để render là **giá trị đã che**, không phải giá trị gốc.
3. Với phương thức an toàn (ví dụ GET/HEAD/OPTIONS/TRACE), bộ lọc theo mặc định không bắt buộc đối chiếu CSRF token. Nếu controller/view không đọc token, supplier có thể không bị kích hoạt.
4. Nếu template truy cập `_csrf.token`, hoặc một endpoint cố ý trả token, token sẽ được tải/tạo và biểu diễn để gửi cho client. Nếu request thuộc nhóm cần bảo vệ (thường POST/PUT/PATCH/DELETE), `CsrfFilter` phải lấy token mong đợi và giá trị client gửi để so sánh.
5. Với token gửi từ form/header ở **dạng đã che**, request handler khôi phục giá trị gốc trước khi đối chiếu với token trong repository. Thiếu hoặc sai token thường dẫn đến HTTP **403 Forbidden**.

Có thể hình dung:

~~~text
GET trang không dùng CSRF
  -> CsrfFilter -> deferred token -> view không đọc token
  -> có thể không tải/tạo token

GET trang form
  -> CsrfFilter -> deferred token -> view đọc _csrf.token
  -> repository lấy/tạo token gốc S
  -> XorCsrfTokenRequestAttributeHandler tạo biểu diễn che M
  -> HTML chứa M

POST form (cookie phiên + M)
  -> CsrfFilter -> đọc token gốc S từ repository
  -> request handler giải che M thành S'
  -> so sánh S' với S -> hợp lệ thì đi tiếp
~~~

Mục tiêu không phải là có token khác trong repository sau mọi GET: **token gốc vẫn có thể giữ nguyên trong cùng session**, còn giá trị đã che được đưa vào HTML thay đổi giữa các lần hiển thị.

## 3. Deferred loading: khi nào token thực sự được tải?

### Cơ chế

Các API liên quan dùng `Supplier<CsrfToken>` hoặc cơ chế deferred tương đương để trì hoãn thao tác tải/tạo. `CsrfTokenRepository` là nơi quyết định cách lưu token; request handler quyết định cách công bố và đọc lại giá trị token. Trong Spring Security 6, việc trì hoãn tải token là hành vi mặc định trong quy trình CSRF thông thường.

**Ví dụ theo tình huống:**

- `GET /health` không cần token và không có thành phần khác buộc tải session: không cần đọc/tạo CSRF token chỉ vì bộ lọc CSRF chạy.
- `GET /account/edit` render form có `_csrf.token`: token được hiện thực hóa; nếu chưa tồn tại, repository có thể tạo và lưu.
- `POST /account` cần kiểm tra CSRF: phải đọc token mong đợi; cơ chế trì hoãn không có nghĩa bỏ qua kiểm tra.
- `GET /csrf` trả token cho frontend: endpoint cố ý truy cập token nên sẽ buộc token hiện thực hóa.

Đừng xem việc **một request có session** hay **có header Set-Cookie** là chỉ báo duy nhất về CSRF. Các thành phần khác (đăng nhập, lưu SecurityContext, ứng dụng riêng) cũng có thể tạo session/cookie. Để xác nhận lazy loading, cần quan sát repository và request cụ thể.

### Lợi ích và đánh đổi

Với ứng dụng nhiều request đọc hoặc API không render form, deferred loading có thể giảm thao tác với session store, tránh tạo session chỉ để chứa CSRF token và tránh phát sinh cookie không cần thiết. Mức giảm thực tế phụ thuộc cách ứng dụng dùng session và cách handler truy cập token.

Nếu ứng dụng chủ động gọi `getToken()` hoặc `Supplier.get()` trên **mọi** request, lợi ích tải trì hoãn sẽ mất ở những request đó. Khi cần token từ JavaScript, thường hợp lý hơn là cung cấp một endpoint phát token có chủ đích, thay vì ép sinh token trên mọi GET.

## 4. XOR masking: che cái gì và giải che ra sao?

Giả sử token gốc lưu ở repository là chuỗi `S`. Mỗi lần cần đưa token ra phản hồi, handler tạo một chuỗi byte ngẫu nhiên mới `R` có độ dài phù hợp, rồi tạo dạng biểu diễn (mô tả ý tưởng):

~~~text
S_bytes = UTF-8(S)
R       = bytes ngẫu nhiên mới
X       = R XOR S_bytes
M       = Base64URL(R || X)
~~~

Khi client gửi lại `M`, handler tách `R` và `X`, tính `R XOR X` để khôi phục `S_bytes`, rồi so khớp với token gốc trong repository. Cách biểu diễn thực tế được thư viện quản lý; ứng dụng không nên tự triển khai decoder theo mô tả này.

Điểm cốt lõi:

- **Cùng một `S` có thể tạo vô số `M` khác nhau** vì mỗi lần dùng mặt nạ `R` mới. Đây là điều giúp giá trị phản chiếu trong phản hồi nén không ổn định như token gốc.
- **`M` không phải bản mã bảo mật:** bên có thể đọc trực tiếp toàn bộ `M` cũng có đủ dữ liệu để khôi phục `S`. Bảo vệ bí mật token vẫn dựa vào cùng origin, chống XSS, quyền truy cập phản hồi và kiểm soát phiên.
- XOR masking **không sửa token đã lưu** trong session/cookie và không tự thay đổi token gốc sau từng GET.
- Masking giúp giảm một đường khai thác BREACH nhắm vào token CSRF, **không chứng minh mọi bí mật trong response đều an toàn** trước tấn công nén. Những bí mật khác phản chiếu ổn định vẫn cần đánh giá riêng.

Trong Spring Security 6, `XorCsrfTokenRequestAttributeHandler` là lựa chọn mặc định phục vụ BREACH protection đối với giá trị CSRF token công bố trong request. Nếu ứng dụng thay bằng `CsrfTokenRequestAttributeHandler` đơn thuần, cần hiểu rằng giá trị công bố không còn được XOR-mask như trước.

## 5. Cấu hình Servlet điển hình

Ví dụ sau dùng Spring Boot 3.x + Spring Security 6.x và Java 17+. Đây là **lớp cấu hình trong ứng dụng có dependency Spring Web/Security**, không phải chương trình Java độc lập chạy bằng một lệnh `javac` không có thư viện. Cấu hình nêu tường minh repository và handler để dễ nhận diện; đối với cấu hình thông thường của Spring Security 6, cả session repository và XOR handler đã là mặc định.

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/csrf").permitAll()
                .anyRequest().authenticated())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository())
                .csrfTokenRequestHandler(new XorCsrfTokenRequestAttributeHandler()));

        return http.build();
    }
}
~~~

Giải thích:

- `HttpSessionCsrfTokenRepository` giữ **token gốc** gắn với session; cookie phiên liên kết request với session đó.
- `XorCsrfTokenRequestAttributeHandler` quản lý biểu diễn **đã che** khi token xuất hiện trong request attribute và khi client gửi token đã che trở lại.
- Deferred loading được thực hiện bởi đường đi của `CsrfFilter`/repository; đoạn cấu hình trên **không cần tự tạo Supplier** hoặc bật thêm cờ riêng.
- `authorizeHttpRequests` là kiểm soát **xác thực/ủy quyền**; nó không đồng nghĩa với bỏ CSRF. `permitAll()` đối với `/login` hoặc `/csrf` cũng không tự tắt cơ chế CSRF cho POST.

### Render form HTML phía server

Với Spring MVC + Thymeleaf, có thể đưa token từ request attribute vào hidden field:

~~~html
<form action="/profile" method="post">
    <label>
        Tên hiển thị
        <input name="displayName" type="text">
    </label>
    <input type="hidden"
           th:name="${_csrf.parameterName}"
           th:value="${_csrf.token}">
    <button type="submit">Lưu</button>
</form>
~~~

Khi template đọc `_csrf.token`, token được hiện thực hóa và giá trị render là **giá trị đã che**. Trình duyệt gửi hidden field cùng session cookie; server giải che rồi so sánh. Trong một số tích hợp Spring MVC/Thymeleaf, cơ chế tự chèn hidden CSRF field đã hoạt động: **không chèn trùng** nếu template hiện tại đã sinh field đó tự động. Khi ứng dụng chạy dưới context path khác `/`, hãy tạo URL action theo cơ chế của template/router thay vì hard-code như ví dụ.

Ví dụ kiểm tra thủ công: tải cùng form hai lần bằng **cùng một session**. Hidden token có thể khác nhau giữa hai phản hồi dù token gốc của session chưa đổi; cả hai biểu diễn vẫn hợp lệ khi session và token gốc còn hiệu lực. Đừng viết logic dựa trên giả định `_csrf.token` phải bằng nhau giữa các lần GET.

## 6. JavaScript / SPA: chọn đúng cách cấp token

Ứng dụng SPA dùng **session cookie tự động gửi theo request** vẫn cần giải pháp CSRF. Điều dễ nhầm là SPA thường đọc token thô từ cookie, trong khi handler XOR mặc định mong đợi **giá trị được che** khi phân tích token từ request.

### Cách A — Endpoint trả token cho JavaScript (giữ đường đi XOR)

Một controller cùng origin có thể trả `CsrfToken` cho frontend:

~~~java
package example.web;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

Trên đường đi mặc định có XOR handler, token được công bố cho controller là dạng phù hợp để client gửi lại qua request parameter/header. Đọc token tại endpoint này sẽ kích hoạt deferred loading. Frontend cần giữ cookie phiên và dùng **tên header** trả về (không tự suy đoán):

~~~javascript
const csrfResponse = await fetch("/csrf", {
  credentials: "same-origin",
  cache: "no-store"
});
if (!csrfResponse.ok) throw new Error("Cannot obtain CSRF token");

const csrf = await csrfResponse.json();

const saveResponse = await fetch("/api/profile", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    [csrf.headerName]: csrf.token
  },
  body: JSON.stringify({ displayName: "Lan" })
});
if (!saveResponse.ok) throw new Error("Save failed");
~~~

Đây là đoạn JavaScript minh họa **tích hợp với endpoint có sẵn**, không phải ví dụ chạy độc lập. Endpoint thực tế cần cùng origin, dùng HTTPS và chính sách cache phù hợp (ưu tiên `Cache-Control: no-store` cho phản hồi token). `csrf.token` gắn với ngữ cảnh phiên hiện tại; sau thay đổi phiên/xác thực phải lấy lại khi cần.

**Ưu điểm:** không cần JavaScript đọc cookie CSRF thô; handler XOR mặc định vẫn giải được token; những GET khác không buộc tải CSRF token chỉ để tạo cookie cho SPA.

### Cách B — SPA đọc cookie `XSRF-TOKEN` và gửi header thô

`CookieCsrfTokenRepository.withHttpOnlyFalse()` cho phép JavaScript đọc cookie CSRF (thường là `XSRF-TOKEN`) để gửi lại qua header (thường `X-XSRF-TOKEN`). Giá trị trong cookie là **token gốc**, khác với biểu diễn XOR từ request attribute. Nếu SPA gửi trực tiếp token thô trong header mà server dùng bộ giải XOR cho mọi nguồn, request có thể nhận **403**.

Một cách tương thích là dùng request handler chọn cách giải theo nơi token được gửi: header từ SPA được đọc **nguyên dạng**, token từ form/request parameter được **giải XOR**. Ví dụ lớp sau dành cho Spring Security 6.x:

~~~java
package example.security;

import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;

public final class SpaCsrfTokenRequestHandler implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
            new CsrfTokenRequestAttributeHandler();
    private final CsrfTokenRequestHandler xor =
            new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);
        csrfToken.get(); // Cookie cần được tạo/ghi ra cho SPA đọc được.
    }

    @Override
    public String resolveCsrfTokenValue(HttpServletRequest request,
                                        CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        CsrfTokenRequestHandler resolver =
                headerValue != null && !headerValue.isBlank() ? plain : xor;
        return resolver.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Đăng ký vào cấu hình CSRF:

~~~java
// Thay phần cấu hình csrf(...) của SecurityFilterChain ở ví dụ trên:
.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()))
~~~

Đoạn đăng ký này cần import `org.springframework.security.web.csrf.CookieCsrfTokenRepository` và chỉ là **mảnh thay thế** trong cấu hình hoàn chỉnh, không phải lệnh Java độc lập.

**Đánh đổi cần nhớ:** gọi `csrfToken.get()` trong `handle` cố tình hiện thực hóa token trên mọi request đi qua handler, nhằm bảo đảm cookie có mặt cho SPA. Vì vậy giải pháp cookie thô này đánh đổi một phần lợi ích **deferred loading**. Nếu không bắt buộc frontend đọc cookie token, cách A thường đơn giản hơn và giữ việc tải theo nhu cầu. Dù chọn cách nào, vẫn bảo đảm ứng dụng có cùng định dạng token ở nơi **phát ra** và nơi **nhận lại**.

Sau đăng nhập thành công hoặc logout, các thành phần CSRF liên quan xác thực có thể xóa token cũ; SPA nên lấy token mới (gọi `/csrf` hoặc kích hoạt đường đi tạo cookie tương ứng). Không tái sử dụng vô hạn token đã lấy trước khi phiên đổi.

## 7. Điều kiện đúng và giới hạn bảo vệ

- **CSRF protection cần khi browser tự gửi credential:** session cookie, và tùy kiến trúc là HTTP Basic hoặc cơ chế credential khác tự đính kèm. API trả JSON vẫn có thể bị CSRF nếu xác thực dựa trên cookie.
- **Request chỉ dùng Bearer token do JavaScript tự gắn vào Authorization header** có threat model khác; quyết định có áp dụng CSRF dựa vào toàn bộ luồng xác thực, không dựa vào tên "REST API" hoặc vì có JSON.
- **SameSite cookie** giúp giảm một số đường tấn công nhưng là lớp bổ trợ; không tự chứng minh mọi trường hợp an toàn. Kiểm soát CORS, origin và HTTPS vẫn phải đúng.
- **XSS có thể vô hiệu hóa giả định bảo mật của CSRF token:** script độc hại chạy trong cùng origin có thể đọc form/endpoint token hoặc gửi request hợp lệ. Cần xử lý XSS độc lập.
- **XOR masking chỉ giảm nguy cơ BREACH đối với token được mask**. Khi phản hồi nén còn phản chiếu bí mật khác hoặc ứng dụng tự in token gốc ra HTML/JSON, đánh giá lại khả năng lộ qua nén. Có thể hạn chế nén trên response chứa bí mật nhạy cảm tùy threat model.
- **Không ghi token vào URL/query string hoặc log**, vì URL dễ đi vào lịch sử/referrer/log và giá trị token có thể xuất hiện ở nơi không mong muốn. Ưu tiên hidden form field hoặc header.
- **Token phải gắn với phiên/cookie đúng:** có token đẹp và đúng định dạng nhưng dùng cookie của phiên khác vẫn bị từ chối. Tránh cache response chứa token giữa người dùng.

## 8. Kiểm chứng hành vi và xử lý lỗi

### Checklist tích hợp

1. **GET không cần token:** gửi request vào endpoint chỉ đọc không render CSRF; kiểm tra xem chính đường đi CSRF có tránh tải/tạo token hay không. Không quy kết mọi session mới là do CSRF.
2. **GET form hai lần trong cùng session:** xem hai hidden field nhận các giá trị đã che khác nhau; cùng với session hợp lệ, mỗi giá trị vẫn có thể gửi về server.
3. **POST không có token hoặc token sai:** kỳ vọng bị chặn ở lớp CSRF, thường HTTP 403; phân biệt với lỗi xác thực/ủy quyền có thể xuất hiện trước hoặc sau.
4. **POST có token đúng:** với cookie phiên phù hợp, request vượt qua kiểm tra CSRF; kết quả cuối còn phụ thuộc validation, controller và quyền truy cập.
5. **SPA gửi header:** xác nhận header name, cách lấy token (masked từ endpoint hay raw từ cookie), `credentials` và repository/handler dùng khớp nhau.
6. **Đăng nhập, logout, hết hạn session:** lấy lại token theo phiên mới; thử request với token cũ để bảo đảm đường đi từ chối đúng.
7. **Nén và cache:** bảo đảm không vô tình đưa token gốc hoặc bí mật ổn định vào một phản hồi nén có thể bị đo kích thước; không cache token endpoint dùng chung giữa người dùng.

Với Spring Security Test/MockMvc, `spring-security-test` cung cấp `.with(csrf())` và `.with(csrf().asHeader())` để kiểm tra nhánh có token khi test controller. Những post-processor đó tiện cho bài test 403/đường đi ứng dụng, nhưng **không thay thế** bài kiểm thử tích hợp quan sát masked token trong HTML hoặc cách client gửi header/cookie thật.

### Những triệu chứng dễ gây hiểu nhầm

| Triệu chứng | Nguyên nhân cần xem | Hướng xử lý |
| --- | --- | --- |
| GET không sinh CSRF cookie/session | Deferred token chưa được truy cập; có thể hoàn toàn đúng. | Chỉ kích hoạt token tại form hoặc endpoint `/csrf` khi client cần. |
| Hidden token đổi ở mỗi lần render | XOR mask mới trên cùng token gốc. | Không so sánh giá trị hidden giữa các GET như tiêu chuẩn ổn định. |
| SPA gửi cookie token vào header mà POST bị 403 | Token header là **raw**, handler đang kỳ vọng **masked**. | Dùng endpoint cấp masked token hoặc handler phân biệt raw-header/masked-form như trên. |
| POST đúng token nhưng vẫn 403 | Cookie session không khớp, token đã xoay, endpoint khác origin, hoặc lỗi ủy quyền riêng. | Kiểm tra session, request header/parameter, handler, cookie flags và log. |
| Sau login/logout request kế tiếp bị 403 | Token cũ đã bị xóa/đổi theo chuyển tiếp xác thực. | Lấy lại token trước lần ghi tiếp theo. |
| Tưởng đã bật lazy loading nhưng mỗi GET đều có token | Handler/controller/template luôn gọi `get()`/`getToken()`. | Xác định nơi ép hiện thực hóa; chỉ làm ở request cần token. |
| Bật XOR rồi cho rằng BREACH hết rủi ro | Response vẫn chứa bí mật khác, hoặc token gốc bị phản chiếu ở vị trí khác. | Kiểm tra toàn bộ response nhạy cảm và chính sách nén/caching. |

## 9. Chọn cách triển khai

- **Server-rendered forms, session cookie:** giữ mặc định Spring Security 6, dùng deferred token + `XorCsrfTokenRequestAttributeHandler`; view lấy `_csrf` khi cần. Đây là luồng đơn giản nhất.
- **SPA có session cookie và chấp nhận gọi endpoint cấp token:** dùng `GET /csrf`, nhận masked token, gửi lại đúng header; vẫn giữ lợi ích tải theo nhu cầu ở các GET không dùng token.
- **SPA bắt buộc đọc cookie CSRF thô:** dùng `CookieCsrfTokenRepository` cùng request handler tương thích raw-header/masked-form; hiểu rằng ép materialize cookie trên mọi request làm tăng tải token.
- **Ứng dụng có yêu cầu bảo mật về BREACH:** tránh xuất token gốc ổn định trong phản hồi nén; đánh giá cả các bí mật khác và mô hình đo kích thước phản hồi, không xem XOR là giải pháp phổ quát.

**Ghi nhớ:** repository bảo quản **token gốc**, deferred loading quyết định **lúc nào lấy/tạo token**, XOR handler quyết định **biểu diễn nào đưa ra client và cách đọc lại biểu diễn đó**. Cả ba cần khớp nhau để vừa bảo vệ POST khỏi CSRF, vừa giảm chi phí request không cần token và hạn chế kênh phụ BREACH liên quan đến token được render.