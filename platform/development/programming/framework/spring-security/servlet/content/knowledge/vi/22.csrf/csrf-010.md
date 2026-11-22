# CSRF trong Spring Security Servlet: token thiếu, token sai, phiên hết hạn và phản hồi lỗi phù hợp

## 1. Bối cảnh và mục tiêu

CSRF (Cross-Site Request Forgery) là cuộc tấn công khiến trình duyệt người dùng đã đăng nhập gửi một yêu cầu thay đổi trạng thái ngoài ý muốn tới ứng dụng. Trình duyệt thường tự đính kèm cookie phiên (`JSESSIONID` hoặc cookie xác thực), vì vậy chỉ có cookie chưa chứng minh request được tạo bởi giao diện hợp lệ. Với ứng dụng **Spring Security Servlet dùng session/cookie**, cơ chế CSRF kiểm tra thêm token khó đoán của đúng ngữ cảnh.

Bài này giải thích bốn trường hợp **token thiếu, token sai, phiên hết hạn và phản hồi lỗi phù hợp**. Sau khi học, bạn cần phân biệt nguyên nhân server quan sát được với nguyên nhân suy luận, xác định status HTTP chính xác và xử lý 403 mà không bỏ bảo vệ CSRF.

## 2. Spring Security kiểm tra CSRF như thế nào?

Mặc định, `CsrfFilter` bảo vệ các phương thức HTTP **khác** `GET`, `HEAD`, `TRACE`, `OPTIONS`. Các phương thức `POST`, `PUT`, `PATCH`, `DELETE` thường cần token hợp lệ. Những method được miễn phải thực sự an toàn, không thay đổi trạng thái; ví dụ `GET /delete` vẫn nguy hiểm dù filter không đòi token.

Một chu trình tiêu biểu của ứng dụng sử dụng session:

1. Trình duyệt gọi một `GET` an toàn, nhận cookie phiên và CSRF token qua form HTML, endpoint cấp token hoặc tích hợp framework.
2. Client gửi request thay đổi dữ liệu, đính kèm **cùng cookie phiên** và token qua tham số form `_csrf` hoặc header tương ứng, thường là `X-CSRF-TOKEN`.
3. `CsrfFilter` yêu cầu token kỳ vọng từ `CsrfTokenRepository` (thường là `HttpSessionCsrfTokenRepository`), rồi so sánh với token trong request.
4. Nếu không có token kỳ vọng hoặc token client không khớp, filter chặn trước controller; mặc định đáp ứng **403 Forbidden**.

```text
Browser                             Servlet Security Filter Chain
GET /api/csrf --------------------> cung cấp token + session cookie
              <------------------ token và cookie
POST /api/demo + cookie + token --> CsrfFilter
                                    |-- khớp  -> controller -> 2xx
                                    |-- lỗi   -> AccessDeniedHandler -> 403
```

CSRF token **khác** JWT/Bearer access token: CSRF token không xác thực danh tính hay đại diện cho quyền. API chỉ dùng Bearer trong header do client tự gắn, không dựa vào credential mà browser tự gửi, có mô hình nguy cơ khác; việc miễn CSRF phải dựa trên kiến trúc thật. Không tắt CSRF trên toàn bộ session-backed web chỉ vì một request bị 403.

### Token được lưu, phát và thay đổi

- Repository session lưu token kỳ vọng gắn với `HttpSession`. Khi session mất, token kỳ vọng cũng có thể mất.
- Spring Security 6 hỗ trợ **deferred CSRF token**: token có thể chưa được tạo/lưu cho tới khi thực sự truy cập. GET thành công không tự động đảm bảo SPA đã nhận token dùng được.
- Sau login/logout hoặc thay đổi vòng đời xác thực, token cũ ở tab trước có thể bị xóa/không còn hợp lệ. Nhiều tab giữ cache token cũ là tình huống cần kiểm thử.
- Spring Security 6 dùng handler chống BREACH cho token được biểu diễn trên request. Khi tự ghép `CookieCsrfTokenRepository` với SPA, phải có `CsrfTokenRequestHandler` tương thích raw cookie/header và token được che, không tự giả định mọi raw cookie token gửi qua header đều hợp lệ.
- Với cookie phiên và token, client phải giữ cùng một phiên. Token của tab/session A không được ghép với cookie phiên B.

## 3. Token thiếu, token sai và hết phiên khác nhau ở đâu?

| Tình huống | Điều filter quan sát | Kết quả thường gặp | Cách phục hồi |
| --- | --- | --- | --- |
| Server đã có token kỳ vọng nhưng request không gửi token | Token gửi lên rỗng/không khớp; thường là `InvalidCsrfTokenException` | 403 | Sửa header/hidden input và cơ chế lấy token |
| Repository không còn token kỳ vọng | Thường là `MissingCsrfTokenException` | 403 | Kiểm tra vòng đời session, phát token mới |
| Request gửi token giả/sai/cũ | `InvalidCsrfTokenException` | 403 | Đồng bộ lại session và token; kiểm tra nhiều tab |
| Session timeout trước request POST | Session cũ không còn; token kỳ vọng có thể mất | Có thể 403 CSRF; tùy luồng còn có 401/redirect | Đăng nhập lại nếu cần, làm mới token rồi gửi lại có kiểm soát |
| Không đăng nhập, không có CSRF error chặn trước | `AuthenticationEntryPoint` | 401 cho API hoặc 302 tới login với form web | Xác thực |
| Có đăng nhập, token hợp lệ nhưng thiếu quyền | `AccessDeniedHandler` | 403 phân quyền | Xin quyền phù hợp; không làm mới token vô ích |

**Phân biệt chính xác hai exception:**

- `MissingCsrfTokenException`: **không tìm thấy token kỳ vọng từ repository**. Không thể dựa vào tên exception để kết luận client quên header. Một session bị timeout hoặc repository/session store mất dữ liệu đều có thể gây trạng thái này.
- `InvalidCsrfTokenException`: **token từ request không khớp giá trị kỳ vọng**. Client có thể gửi sai giá trị hoặc hoàn toàn không gửi token trong khi server vẫn lưu token kỳ vọng.
- **Hết phiên không phải một loại CSRF exception riêng.** Một 403 CSRF không tự chứng minh phiên hết hạn. Có thể do CORS/credentials không gửi cookie, token phát sai ngữ cảnh, load balancer đi sang node thiếu session, đổi token sau login, v.v.

Ví dụ chẩn đoán: Nếu GET cấp token, POST không gửi header nhưng vẫn giữ đúng session, server thường báo invalid token. Nếu người dùng điền form quá lâu, session timeout, rồi gửi POST kèm token cũ, server có thể báo missing expected token. Hai request đều bị 403 nhưng hướng xử lý khác.

## 4. Dùng status và error contract phù hợp

**403 Forbidden** là HTTP status mặc định khi CsrfFilter từ chối request. **401 Unauthorized** nên dành cho trường hợp cơ chế authentication xác định client cần đăng nhập/xác thực lại; đừng biến mọi CSRF failure thành 401. Form login có thể redirect 302 tới trang login tùy entry point. Mã 419/440 được một số hệ thống dùng cho timeout nhưng không phải status chuẩn mặc định của Spring Security.

Ví dụ **application/problem+json** cho API:

```http
HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Yêu cầu không vượt qua kiểm tra CSRF.",
  "code": "CSRF_TOKEN_INVALID"
}
```

`code` là mã **do ứng dụng định nghĩa**, không tự được Spring Security phát. Mã nội bộ `CSRF_TOKEN_MISSING` nên được hiểu là “không có expected token trong repository”, không mặc định là “thiếu header”; `CSRF_TOKEN_INVALID` là giá trị gửi lên không hợp lệ. Client dựa vào status/code ổn định, không dò chuỗi message.

Phản hồi tốt cần đảm bảo:
- Không gửi expected token, session ID, stack trace, khóa bảo mật hoặc thông tin session store ra client.
- Thông báo cho người dùng vừa đủ: “Mã bảo vệ biểu mẫu không còn hợp lệ. Hãy tải lại trang hoặc đăng nhập lại nếu được yêu cầu.”
- Không chẩn đoán “phiên đã hết hạn” khi chỉ có CSRF exception và chưa có bằng chứng xác thực riêng.
- Ghi log `requestId`, method, đường dẫn và **loại exception**; tránh log giá trị token, cookie hoặc payload nhạy cảm.
- Với thao tác thay đổi dữ liệu, không retry vô hạn. Chỉ mời gửi lại khi xác định thao tác cũ bị chặn trước khi xử lý; các thao tác quan trọng cần xác nhận lại/idempotency key.

## 5. Ví dụ Spring Boot 3 / Spring Security 6 (Java 17+)

Các đoạn mã dưới là **file trong một ứng dụng Spring Boot Servlet** đã có lớp `@SpringBootApplication`, dependency `spring-boot-starter-web` và `spring-boot-starter-security`; không phải chương trình độc lập có thể chạy bằng `javac` thuần. Endpoint `permitAll` chỉ để cô lập bài kiểm thử CSRF; nghiệp vụ thực phải gắn quy tắc authentication/authorization thích hợp.

### 5.1. SecurityFilterChain và handler trả 403 JSON

File `SecurityConfig.java`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Map;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.InvalidCsrfTokenException;
import org.springframework.security.web.csrf.MissingCsrfTokenException;

@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http,
                                            ObjectMapper mapper) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/demo").permitAll()
                .anyRequest().authenticated())
            .csrf(Customizer.withDefaults())
            .exceptionHandling(errors -> errors.accessDeniedHandler(
                (request, response, exception) -> {
                    String code = "ACCESS_DENIED";
                    if (exception instanceof MissingCsrfTokenException) {
                        code = "CSRF_TOKEN_MISSING";
                    } else if (exception instanceof InvalidCsrfTokenException) {
                        code = "CSRF_TOKEN_INVALID";
                    }

                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setCharacterEncoding("UTF-8");
                    response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
                    mapper.writeValue(response.getOutputStream(), Map.of(
                        "type", "about:blank",
                        "title", "Forbidden",
                        "status", 403,
                        "detail", "Request was rejected.",
                        "code", code
                    ));
                }));
        return http.build();
    }
}
```

CSRF filter sử dụng `AccessDeniedHandler` khi request bị từ chối; cấu hình `exceptionHandling` điều chỉnh handler cho chain. Mã error có thể dùng chung hình thức với lỗi phân quyền, nhưng **không gộp ý nghĩa** của `CSRF_TOKEN_INVALID` và `ACCESS_DENIED`. Trong ứng dụng có nhiều `SecurityFilterChain`, cần đảm bảo chính xác chain khớp `/api/**`. Đối với UI HTML, dùng trang 403/thông báo giao diện phù hợp thay vì áp cùng JSON cho mọi request.

### 5.2. Endpoint lấy token và endpoint POST

File `CsrfDemoController.java`:

```java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfDemoController {
    @GetMapping("/api/csrf")
    Map<String, String> csrf(HttpServletRequest request) {
        Object value = request.getAttribute(CsrfToken.class.getName());
        if (!(value instanceof CsrfToken token)) {
            throw new IllegalStateException("CSRF token is unavailable");
        }
        return Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        );
    }

    @PostMapping("/api/demo")
    Map<String, String> demo() {
        return Map.of("result", "saved");
    }
}
```

Đọc `token.getToken()` giúp materialize deferred token khi cần. Client phải gửi đúng cookie của lần GET token khi POST. Endpoint trả token là tài nguyên nhạy cảm cho client đáng tin: sử dụng TLS, chính sách cache/CORS phù hợp, không công khai token qua log hoặc URL.

Thử bằng cURL sau khi Spring Boot chạy. Thay `TOKEN_TU_GET` bằng trường `token` nhận ở phản hồi đầu, **giữ nguyên cookies.txt**:

```bash
# Lấy token và lưu cookie phiên.
curl -i -c cookies.txt http://localhost:8080/api/csrf

# Thiếu token: 403; controller chưa thực thi.
curl -i -b cookies.txt -X POST http://localhost:8080/api/demo

# Sai token: 403.
curl -i -b cookies.txt -X POST \
  -H 'X-CSRF-TOKEN: sai-token' http://localhost:8080/api/demo

# Đúng token và đúng cookie phiên: 200.
curl -i -b cookies.txt -X POST \
  -H 'X-CSRF-TOKEN: TOKEN_TU_GET' http://localhost:8080/api/demo
```

Đối với cấu hình ví dụ, trạng thái mong đợi lần lượt là **403, 403, 200**. POST hợp lệ trả JSON chứa `"result":"saved"`. Một POST token sai phải bị chặn *trước* method `demo()`; không có side effect.

### 5.3. Form HTML và JavaScript

Với form server-rendered Thymeleaf có `_csrf` trong request:

```html
<form method="post" action="/api/demo">
  <input type="hidden" th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}" />
  <button type="submit">Gửi</button>
</form>
```

Với SPA dùng endpoint lấy token:

```javascript
const csrfResponse = await fetch("/api/csrf", {
  credentials: "same-origin",
  cache: "no-store"
});
if (!csrfResponse.ok) throw new Error("Cannot get CSRF token");
const csrf = await csrfResponse.json();

const response = await fetch("/api/demo", {
  method: "POST",
  credentials: "same-origin",
  headers: { [csrf.headerName]: csrf.token }
});
if (response.status === 403) {
  // Hiển thị hướng dẫn làm mới token / đăng nhập khi cần.
}
```

`credentials: "same-origin"` giữ cookie cho yêu cầu cùng origin. Frontend/backend khác origin cần quyết định riêng về CORS, `credentials` và thuộc tính `SameSite`/`Secure` của cookie. Không đặt token trong query string hay URL vì dễ lọt vào history, log và `Referer`.

## 6. Phiên hết hạn: thiết kế luồng phục hồi

Phiên mất có thể do timeout, logout, người dùng xóa cookie, policy concurrent sessions, session store bị xóa hoặc các node không chia sẻ dữ liệu. Khi CSRF token nằm trong session, POST mang token cũ sau timeout có thể nhận 403; không có cách đáng tin để phân biệt timeout với tất cả nguyên nhân khác chỉ từ `MissingCsrfTokenException`.

Luồng đề xuất:

1. **HTML form:** nếu bị 403, thông báo biểu mẫu cần tải lại; giữ dữ liệu người dùng nhập nếu phù hợp bảo mật, rồi tạo form/token mới.
2. **SPA:** gọi GET an toàn để nhận token mới và đồng bộ cookie/session; nếu authentication thực sự hết hạn, yêu cầu đăng nhập lại. Chỉ thử gửi lại thay đổi dữ liệu khi xác định POST cũ chưa chạy và có chiến lược ngăn thao tác lặp.
3. **Authentication:** endpoint cần đăng nhập nên để `AuthenticationEntryPoint` quyết định 401 (API) hoặc redirect login (web), nhưng đừng mặc định mọi POST hết session đều đi tới entry point; `CsrfFilter` có thể từ chối trước.
4. **Session không hợp lệ:** `invalidSessionStrategy` có thể xử lý session ID không hợp lệ trong cấu hình phù hợp, nhưng không đảm bảo luôn chạy trước CSRF trên request unsafe. Kiểm tra filter order và test request thực.
5. **Sau login/logout hoặc session fixation protection:** lấy token mới theo cơ chế framework. Token giữ ở tab cũ có thể không dùng được.

Trong môi trường nhiều node, xác minh sticky session hoặc shared session store, cookie domain/path và session timeout nhất quán. Không “sửa” 403 ngẫu nhiên bằng `csrf(csrf -> csrf.disable())`.

## 7. Kiểm thử thiếu token, sai token và token đúng

Thêm `spring-boot-starter-test` và `spring-security-test`. File `CsrfDemoTest.java` (bên trong project Spring Boot):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDemoTest {
    @Autowired
    MockMvc mvc;

    @Test
    void noTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/demo"))
           .andExpect(status().isForbidden());
    }

    @Test
    void wrongTokenIsForbidden() throws Exception {
        mvc.perform(post("/api/demo").with(csrf().useInvalidToken()))
           .andExpect(status().isForbidden());
    }

    @Test
    void correctTokenIsAllowed() throws Exception {
        mvc.perform(post("/api/demo").with(csrf()))
           .andExpect(status().isOk());
    }
}
```

`csrf()` ở đây là **Spring Security Test request post-processor**; `useInvalidToken()` cố ý cấp token sai. Test này xác minh CSRF filter mà không cần tự điền chuỗi token. Endpoint demo được `permitAll` để tránh nhập nhằng với thiếu authentication; tại endpoint thực phải kiểm tra thêm quyền truy cập.

Bảng kịch bản tích hợp:

| Kịch bản | Cách dựng | Điều phải kiểm chứng |
| --- | --- | --- |
| Thiếu token từ client | POST giữ session cookie nhưng bỏ header/input | 403; controller không chạy; dữ liệu không đổi |
| Token sai/cũ | POST với token giả hoặc token của session khác | 403; không side effect |
| Token hợp lệ | GET cấp token rồi POST cùng session | 2xx theo nghiệp vụ |
| Session timeout thật | Lấy token, invalidate/expire session trong server, POST lại token cũ | Có thể 403 CSRF; không side effect; client được hướng dẫn phục hồi |
| Logout/login lại | Giữ tab/form cũ qua chuyển đổi trạng thái xác thực | Token được cấp lại đúng; form cũ không thể dùng sai ngữ cảnh |
| Chưa đăng nhập | Endpoint yêu cầu authentication, token hợp lệ nếu method unsafe | 401 hoặc redirect login theo entry point |
| Thiếu quyền | Người dùng đã auth, token hợp lệ, không có authority | 403 phân quyền; code/log khác CSRF |
| Nhiều node | Gửi các request tới node khác nhau theo hạ tầng thực | Session/token vẫn được đọc nhất quán |
| GET an toàn | GET không có CSRF token | Không cần token; GET không gây thay đổi trạng thái |

**Test timeout phải làm session server thật sự hết hạn.** Chỉ bỏ header token là test thiếu token từ request, không phải test timeout. Sau mỗi test 403, xác nhận không có ghi dữ liệu, gửi email hay tác vụ nghiệp vụ đã diễn ra.

## 8. Checklist điều tra 403 và lỗi thường gặp

Quy trình khi gặp lỗi:

1. Kiểm tra HTTP method, URL, đúng `SecurityFilterChain` và rule bảo vệ/ngoại lệ của CSRF.
2. So sánh cookie phiên giữa lần lấy token và POST; xác minh form hidden input/header `X-CSRF-TOKEN` có mặt. Tránh xuất token/cookie ra ticket hoặc log.
3. Kiểm tra thời điểm token được materialize, cách SPA giữ token và `fetch.credentials`, các sự kiện login/logout hoặc nhiều tab.
4. Kiểm tra `CsrfTokenRepository`, session timeout, cookie path/domain, load balancer và session store.
5. Đọc exception thực tế từ log server: expected token **không tồn tại** hay request token **không khớp**. Không quy tất cả thành timeout.
6. Chạy bộ test của mục 7; xác định 403 trả về định dạng hợp đồng API, có correlation ID an toàn và không side effect.

Sai lầm phổ biến: nhầm CSRF token với JWT; dùng 401 cho mọi CSRF failure; coi `MissingCsrfTokenException` là chắc chắn thiếu request header; retry POST vô hạn; lấy token bằng một session nhưng gửi POST cùng cookie khác; giữ token cũ sau login; gửi token trong URL; ghi token vào log; tắt CSRF toàn cục; dùng POST làm endpoint phát token; thay đổi dữ liệu trong GET; mặc định `invalidSessionStrategy` luôn bắt timeout trước CsrfFilter.

## 9. Checklist áp dụng

- [ ] Request thay đổi trạng thái qua session/cookie luôn gửi token đúng session; request GET không làm thay đổi dữ liệu.
- [ ] Form/SPA có đường cấp mới token sau login, logout và tab mở lâu; xử lý deferred token đúng cách.
- [ ] CSRF 403 được phân biệt với 403 phân quyền; 401 chỉ dùng khi xác thực yêu cầu.
- [ ] API trả lỗi có cấu trúc, không lộ secret, không tuyên bố session timeout nếu thiếu bằng chứng.
- [ ] Không tự động retry thao tác nghiệp vụ nguy hiểm và không gây side effect khi CSRF bị chặn.
- [ ] Có test thiếu, sai, đúng, timeout thật, login/logout, nhiều node và quyền truy cập.

**Điểm cần nhớ:** Trong Spring Security Servlet, cả token thiếu và token sai thường khiến `CsrfFilter` trả **403 trước controller**. Timeout phiên có thể tạo triệu chứng tương tự, nhưng phải kiểm chứng riêng. Đồng bộ token + session, trả lỗi trung thực và kiểm thử đúng đường đi là cách giải quyết.
