# Token repository, cookie và phiên cần kiểm tra khi dùng cơ chế thật

Khi kiểm thử CSRF bằng Spring Security, helper `csrf()` của MockMvc rất tiện để kiểm tra filter chấp nhận hay từ chối token. Tuy nhiên, một ứng dụng chạy thật còn có vòng đời token: server tạo token, lưu vào session hoặc cookie, browser nhận và giữ cookie, client gửi lại token qua form/header, rồi server đọc token theo đúng repository và request handler. Nếu chỉ dùng helper, ta chưa chắc đã kiểm tra được **cookie, session và quá trình lấy/gửi token của client**.

Bài học này tập trung vào hai cơ chế Servlet phổ biến: `HttpSessionCsrfTokenRepository` và `CookieCsrfTokenRepository`. Ta sẽ kiểm tra token được tạo và lưu ở đâu, vì sao phải giữ đúng cookie/session giữa các request, cách kiểm thử sau login/logout và những khác biệt cần lưu ý với deferred token/XOR handler. Cuối bài có cách tiếp cận tương ứng cho WebFlux.

## 1. Repository quyết định token được lưu ở đâu

`CsrfTokenRepository` là thành phần chịu trách nhiệm tạo, tải và lưu CSRF token. Filter CSRF dùng repository để lấy token dự kiến, sau đó request handler giải quyết giá trị token mà client gửi lên.

| Repository | Nơi lưu token | Dữ liệu client thường giữ/gửi |
| --- | --- | --- |
| `HttpSessionCsrfTokenRepository` | Thuộc tính trong HTTP session phía server | Browser giữ session cookie; token được render vào form hoặc gửi qua header/parameter. |
| `CookieCsrfTokenRepository` | Cookie CSRF phía client, thường tên `XSRF-TOKEN` | Browser gửi lại cookie; JavaScript thường đọc cookie và gửi giá trị tương ứng qua header `X-XSRF-TOKEN`. |

Với cấu hình Servlet mặc định, Spring Security thường sử dụng session-based repository. Nếu muốn cấu hình rõ ràng:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(new HttpSessionCsrfTokenRepository()));
~~~

Với SPA cần JavaScript đọc CSRF cookie:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

Không chọn repository chỉ theo framework giao diện. Hãy xác định credential xác thực được browser gửi như thế nào:

- Nếu ứng dụng dùng session cookie, token gắn với session là lựa chọn phổ biến.
- Nếu SPA dùng cookie để xác thực và cần đọc token từ cookie để gửi header, cookie repository có thể phù hợp, nhưng cần request handler tương thích.
- Nếu API chỉ nhận Bearer token do client chủ động gửi trong Authorization header và không dựa vào credential tự động gửi bởi browser, mô hình CSRF có thể khác. Cần xác nhận chính sách của security chain và cách token được lưu thực tế.

## 2. Luồng token với HttpSessionCsrfTokenRepository

Với session repository, token được lưu trong session phía server. Browser phải tiếp tục gửi cookie session để server tìm lại đúng session và token. Thông thường:

1. Browser truy cập trang/form cần CSRF.
2. Spring Security tạo hoặc tải token và lưu vào session khi token được sử dụng.
3. Trang render token trong hidden input hoặc meta tag.
4. Browser gửi session cookie cùng request thay đổi trạng thái và truyền token bằng parameter/header.
5. Server tải token từ session, giải quyết giá trị được gửi và so sánh.

Ví dụ form HTML:

~~~html
<form method="post" action="/profile">
  <input type="text" name="displayName" value="Lan">
  <input type="hidden" name="_csrf" value="token-do-server-render">
  <button type="submit">Lưu</button>
</form>
~~~

Tên parameter mặc định thường là `_csrf`, còn cookie session có thể là `JSESSIONID` hoặc tên do container cấu hình. Session cookie **không phải CSRF token**; nó giúp server tra cứu session chứa token.

### Điều gì xảy ra khi session thay đổi?

- Nếu client bỏ session cookie hoặc dùng session khác, server có thể không tìm được token tương ứng.
- Token lấy từ session A không nên dùng cho request thuộc session B.
- Sau khi đăng nhập thành công, Spring Security có thể áp dụng session fixation protection để đổi session ID; CSRF authentication strategy cũng làm token cũ bị xóa để yêu cầu token mới.
- Sau logout, token cũ được xóa theo logout handling. Khi người dùng đăng nhập lại hoặc bắt đầu phiên mới, client cần lấy token mới.

Vì vậy, test cơ chế session cần giữ cookie/session đúng ngữ cảnh, đồng thời có ca kiểm tra token cũ sau login/logout hoặc sau khi chuyển sang phiên khác.

## 3. Deferred token và XOR/BREACH: vì sao token nhìn thấy có thể khác token lưu

Các phiên bản Spring Security hiện đại có thể tải/tạo CSRF token theo cơ chế **deferred**: token chưa nhất thiết được tạo ngay ở đầu request. Khi view, controller hoặc request handler truy cập token, repository mới được yêu cầu tạo/lưu token.

Ngoài ra, request handler mặc định có thể dùng XOR masking để giảm rủi ro BREACH khi token được đưa vào nội dung phản hồi. Vì thế cần phân biệt:

- Token gốc được repository lưu.
- Token được đưa vào request attribute/render cho client.
- Giá trị token client gửi lại và cách request handler giải quyết giá trị đó.

Không giả định chuỗi hiển thị trong HTML/JSON luôn bằng byte token lưu trong session hoặc cookie. Hãy lấy token từ đúng response của ứng dụng và gửi lại theo đúng header/parameter mà ứng dụng cấu hình. Nếu tự đọc session attribute rồi nhét thẳng vào request, test có thể bỏ qua bước masking/unmasking và không mô phỏng client thật.

Một endpoint trả token cho SPA có thể dùng:

~~~java
@RestController
class CsrfBootstrapController {

    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
~~~

Đây là ví dụ endpoint cùng origin cung cấp token cho client; chỉ triển khai nếu kiến trúc giao diện cần endpoint như vậy và bảo đảm endpoint được phục vụ qua cùng chính sách bảo mật. Một trang server-rendered có thể render token trực tiếp trong form thay vì tạo endpoint riêng.

## 4. Kiểm thử session repository bằng MockMvc với cùng session

Để kiểm tra repository thực, không dùng `.with(csrf())` trong ca lấy và gửi token. Hãy lấy token từ response của ứng dụng, giữ session thu được và gửi lại giá trị đó.

Ví dụ controller:

~~~java
@RestController
class CsrfBootstrapController {

    @GetMapping("/csrf")
    CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}

@RestController
class ProfileController {

    @PostMapping("/profile")
    ResponseEntity<Void> updateProfile() {
        return ResponseEntity.noContent().build();
    }
}
~~~

Test với `HttpSessionCsrfTokenRepository`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionCsrfRepositoryTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void tokenFromSameSession_isAccepted() throws Exception {
        MvcResult bootstrap = mockMvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode tokenJson = objectMapper.readTree(
            bootstrap.getResponse().getContentAsString());
        String parameterName = tokenJson.get("parameterName").asText();
        String token = tokenJson.get("token").asText();
        MockHttpSession session =
            (MockHttpSession) bootstrap.getRequest().getSession(false);

        assertNotNull(session);
        assertFalse(token.isBlank());

        mockMvc.perform(post("/profile")
                .session(session)
                .param(parameterName, token))
            .andExpect(status().isNoContent());
    }
}
~~~

Test giả định security chain dùng session repository và endpoint `/profile` yêu cầu user đã đăng nhập. Khi response JSON được serialize, thuộc tính token được truy cập và deferred token được materialize; session chứa token có thể được lấy từ request đầu tiên rồi tái sử dụng ở request tiếp theo.

### Ba ca nên kiểm tra trong cùng session

Sau khi bootstrap token và lấy `session`/`parameterName` như ví dụ trên, gửi ba request:

~~~java
// 1. Cùng session nhưng thiếu parameter CSRF.
mockMvc.perform(post("/profile").session(session))
    .andExpect(status().isForbidden());

// 2. Cùng session nhưng parameter có giá trị sai.
mockMvc.perform(post("/profile")
        .session(session)
        .param(parameterName, "not-the-session-token"))
    .andExpect(status().isForbidden());

// 3. Cùng session và token vừa lấy từ response.
mockMvc.perform(post("/profile")
        .session(session)
        .param(parameterName, token))
    .andExpect(status().isNoContent());
~~~

Ba request cần cùng method, path, user và dữ liệu. Không thêm `csrf()` vào chúng, vì mục tiêu là kiểm tra token được cấp và lưu bởi repository thật.

### Kiểm tra token thuộc session khác

Lấy token và session A từ lần bootstrap thứ nhất, sau đó bootstrap session B. Gửi token A cùng session B: request phải bị từ chối trong mô hình session repository. Gửi token B cùng session B: request được chấp nhận. Đây là phép thử hữu ích để phát hiện client lưu token ở global state rồi vô tình dùng chéo giữa nhiều tài khoản/tab/phiên.

Khi thực hiện bằng MockMvc, giữ hai đối tượng `MockHttpSession` riêng biệt. Khi kiểm thử qua HTTP thật, dùng hai cookie jar riêng để không trộn cookie session.

## 5. CookieCsrfTokenRepository và double-submit cookie

`CookieCsrfTokenRepository` lưu token trong cookie. Cấu hình phổ biến:

~~~java
CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();

http.csrf(csrf -> csrf
    .csrfTokenRepository(repository));
~~~

Các tên mặc định thường gặp:

| Thành phần | Tên |
| --- | --- |
| Cookie chứa token | `XSRF-TOKEN` |
| Header client gửi lại | `X-XSRF-TOKEN` |
| Request parameter | `_csrf` |

`withHttpOnlyFalse()` cho phép JavaScript đọc cookie CSRF. Chỉ dùng tùy chọn này khi client thực sự cần đọc cookie; cookie vẫn nên được giới hạn domain/path phù hợp, bật Secure khi chạy HTTPS và thiết lập SameSite theo kiến trúc triển khai. Không bật JavaScript access cho cookie phiên đăng nhập.

Mô hình double-submit thường hoạt động như sau:

1. Server phát cookie CSRF cho browser.
2. JavaScript đọc giá trị cookie CSRF.
3. JavaScript gửi cùng giá trị trong header mà server mong đợi.
4. Server so sánh giá trị request với token trong cookie.

Cookie CSRF và cookie session có vai trò khác nhau. Cookie CSRF không phải session cookie; với repository cookie-based, token không được lưu trong HTTP session như cách session repository làm. Nếu ứng dụng dùng cookie session để xác thực, browser vẫn cần gửi cookie phiên cùng request.

### Cookie raw và token XOR được render

Với Spring Security hiện đại, handler mặc định có thể đưa token XOR-masked vào request attribute để render. Giá trị cookie do repository ghi có thể là token raw, trong khi giá trị token hiển thị trong HTML/JSON là giá trị masked. Nếu SPA đọc raw cookie rồi gửi raw value trong header, request handler mặc định có thể không giải mã theo cách SPA mong đợi.

Đối với SPA, cần cấu hình request handler hỗ trợ header raw từ cookie trong khi vẫn dùng XOR handler cho token render trong form. Một mẫu handler được Spring Security hướng dẫn có dạng:

~~~java
final class SpaCsrfTokenRequestHandler
        extends CsrfTokenRequestAttributeHandler {

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {
        this.xor.handle(request, response, csrfToken);
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        if (StringUtils.hasText(headerValue)) {
            return super.resolveCsrfTokenValue(request, csrfToken);
        }
        return this.xor.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Các import chính của ví dụ:

~~~java
import java.util.function.Supplier;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;
~~~

Đăng ký cùng cookie repository:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()));
~~~

Handler minh họa ưu tiên giá trị header raw theo quy ước SPA và dùng XOR delegate cho trường hợp khác như form parameter. Hãy đối chiếu với phiên bản Spring Security đang dùng và hướng dẫn SPA tương ứng; không sao chép custom handler nếu ứng dụng không dùng cookie raw header hoặc đã có request handler riêng.

## 6. Kiểm thử cookie repository bằng MockMvc

Để kiểm tra cookie thật do repository phát ra, gọi endpoint bootstrap, đọc cookie trong response rồi gửi cookie cùng header ở request tiếp theo. Ví dụ này giả định đã cấu hình `CookieCsrfTokenRepository` cùng SPA request handler ở mục trước:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CookieCsrfRepositoryTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void cookieAndMatchingHeader_areAccepted() throws Exception {
        MvcResult bootstrap = mockMvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        Cookie csrfCookie = bootstrap.getResponse().getCookie("XSRF-TOKEN");
        assertNotNull(csrfCookie);
        assertFalse(csrfCookie.getValue().isBlank());

        mockMvc.perform(post("/profile")
                .cookie(csrfCookie)
                .header("X-XSRF-TOKEN", csrfCookie.getValue()))
            .andExpect(status().isNoContent());
    }
}
~~~

Với cookie repository, test tập trung vào việc client gửi lại cookie và giá trị header tương ứng. Nếu endpoint xác thực bằng session cookie, phải giữ thêm session cookie trong cùng cookie jar; ví dụ `@WithMockUser` mô phỏng danh tính ở test nên không chứng minh vòng đời session login thật.

### Kiểm tra thiếu cookie, thiếu header và giá trị không khớp

Các trường hợp cần có:

| Cookie CSRF | Header CSRF | Kết quả khi endpoint cần CSRF |
| --- | --- | --- |
| Không có | Không có | Từ chối. |
| Có | Không có | Từ chối nếu request handler cần header/parameter. |
| Không có | Có | Từ chối vì repository không có token dự kiến để so khớp. |
| Có | Có, nhưng giá trị khác | Từ chối. |
| Có | Có, giá trị khớp | Qua CSRF và tiếp tục authentication/authorization. |

Ví dụ request có cookie nhưng header sai:

~~~java
mockMvc.perform(post("/profile")
        .cookie(csrfCookie)
        .header("X-XSRF-TOKEN", "different-value"))
    .andExpect(status().isForbidden());
~~~

Đừng kiểm tra riêng việc cookie xuất hiện rồi kết luận CSRF hoạt động. Cần chứng minh server từ chối khi header thiếu/sai và chấp nhận khi cặp cookie/header hợp lệ.

## 7. Cookie/session trong kiểm thử HTTP thật

MockMvc giữ request trong tiến trình test và cho phép gắn `MockHttpSession` hoặc cookie trực tiếp. Để xác minh browser/client thực sự lưu và gửi cookie, dùng HTTP client hoặc browser automation với cookie jar.

Một luồng kiểm thử HTTP thật cho session repository:

1. Đăng nhập bằng cơ chế thật (form login hoặc endpoint đăng nhập).
2. Lưu cookie session từ response.
3. Truy cập form hoặc endpoint cấp token trong cùng cookie jar.
4. Lấy token từ HTML/JSON được server trả về.
5. Gửi request thay đổi trạng thái với cookie session và token.
6. Gửi lại request thiếu token hoặc token sai trong cùng session; xác minh bị từ chối.
7. Đăng xuất/đăng nhập lại, lấy token mới và xác minh token cũ không còn dùng được.

Với cookie repository:

1. Gọi endpoint/trang cấp token và lưu cookie `XSRF-TOKEN`.
2. Giữ các cookie xác thực cần thiết trong cùng cookie jar.
3. Gửi giá trị cookie CSRF trong header đúng theo repository/request handler.
4. Thử header thiếu, header sai và cookie bị thiếu.
5. Kiểm tra cookie attributes như Path, Secure, HttpOnly, SameSite theo cấu hình triển khai.

Ví dụ lệnh HTTP minh họa:

~~~bash
# Lấy form/token và giữ cookie phiên.
curl -i -c cookies.txt -b cookies.txt https://app.example/profile/edit

# Gửi form với token lấy từ trang vừa nhận.
curl -i -c cookies.txt -b cookies.txt --data-urlencode "displayName=Lan" --data-urlencode "_csrf=<token-tu-cung-session>" https://app.example/profile

# Với SPA cookie repository, header phải khớp cấu hình thực tế.
curl -i -c cookies.txt -b cookies.txt -H "X-XSRF-TOKEN: <token-tu-cookie-XSRF-TOKEN>" -H "Content-Type: application/json" -d '{"displayName":"Lan"}' https://app.example/profile
~~~

Đây là lệnh mẫu; URL, cookie, token và header phải thay theo ứng dụng. Không copy token của phiên khác hoặc lưu token thật trong log/fixture lâu dài.

## 8. Login, logout và session fixation

Một lỗi phổ biến là giữ token cũ qua các thay đổi authentication:

- **Login thành công:** Spring Security có thể đổi session ID để chống session fixation và xóa CSRF token cũ. Client nên lấy token mới sau khi đăng nhập.
- **Logout:** CSRF logout handling xóa token hiện tại; sau logout không tiếp tục dùng token cũ.
- **Đăng nhập lại:** phiên mới hoặc token mới phải được bootstrap trước khi gửi request thay đổi trạng thái.
- **Nhiều tab/tài khoản:** nếu dùng cookie jar/session khác nhau, không chia sẻ token hoặc session state giữa chúng.

Một test tích hợp có thể mô tả:

~~~text
GET /csrf trước login -> token A
POST /login thành công -> session/authentication thay đổi
POST /profile với token A -> phải bị từ chối nếu token cũ đã bị xóa
GET /csrf sau login -> token B
POST /profile với token B và session mới -> được xử lý
POST /logout với token hợp lệ -> logout thành công
POST /profile với cookie/token cũ -> không còn được xác thực
~~~

Kết quả status của login/logout phụ thuộc cấu hình form login, entry point và logout success handler. Mục tiêu test là xác minh **token và session lifecycle**, không ép mọi ứng dụng phải trả cùng status.

## 9. CORS, SameSite và HttpOnly không thay thế nhau

| Cơ chế | Vai trò | Không thay thế |
| --- | --- | --- |
| CSRF token | Chứng minh request có token phù hợp | Authentication, authorization, XSS defense |
| SameSite cookie | Hạn chế một số tình huống browser gửi cookie cross-site | CSRF token trong mọi cấu hình |
| HttpOnly | Ngăn JavaScript đọc cookie được đánh dấu HttpOnly | Ngăn browser tự gửi cookie |
| CORS | Kiểm soát JavaScript từ origin khác có thể đọc/trao đổi response theo policy | Cơ chế xác thực request và CSRF |
| Secure | Chỉ gửi cookie qua HTTPS | Xác minh nguồn request |

Với cookie session, giữ HttpOnly thường là lựa chọn phù hợp vì JavaScript không cần đọc session ID. Với cookie CSRF, `HttpOnly=false` có thể cần cho SPA đọc token, nhưng tăng hậu quả nếu trang bị XSS; cần bảo vệ XSS và giới hạn cookie scope. SameSite là lớp bổ sung, không phải lý do tự động tắt CSRF.

Nếu frontend và backend khác origin, kiểm tra CORS allowlist, credential mode và cookie domain/SameSite/Secure. Không bật `Access-Control-Allow-Origin: *` cùng credentials; cũng không cho rằng preflight thành công có nghĩa request đã qua CSRF.

## 10. Các ca kiểm thử tối thiểu theo repository

| Repository | Ca cần có | Bằng chứng |
| --- | --- | --- |
| HttpSession | Lấy token và session từ response bootstrap | Token được tạo/lưu trong đúng session. |
| HttpSession | Gửi token cùng session | Request được chấp nhận. |
| HttpSession | Thiếu/sai token | Request bị từ chối. |
| HttpSession | Token A dùng với session B | Token không được chấp nhận ở phiên khác. |
| HttpSession | Sau login/logout | Client phải lấy token mới khi token cũ bị xóa. |
| Cookie | Response phát cookie CSRF | Repository tạo cookie theo cấu hình. |
| Cookie | Cookie và header khớp | Request được chấp nhận. |
| Cookie | Thiếu cookie/header hoặc giá trị khác | Request bị từ chối. |
| Cookie | Cookie attributes | Browser có thể gửi/đọc đúng theo yêu cầu triển khai. |
| Cả hai | Request token hợp lệ nhưng thiếu quyền | CSRF qua, authorization vẫn từ chối. |

Với các ca bị từ chối, xác minh controller/service không tạo tác dụng phụ. Với ca thành công, xác minh dữ liệu được cập nhật đúng. Một status `403` riêng lẻ chưa chứng minh lỗi đến từ CSRF; giữ user đủ quyền và dùng ca token hợp lệ làm đối chứng.

## 11. Reactive: repository và exchange context

Ứng dụng WebFlux dùng `ServerWebExchange` và `ServerCsrfTokenRepository`, không dùng `HttpSessionCsrfTokenRepository` hoặc `CookieCsrfTokenRepository` của Servlet. Các lựa chọn Reactive tương ứng có repository cho WebSession và cookie; cấu hình cụ thể cần theo phiên bản Spring Security đang dùng.

Khi kiểm thử bằng `WebTestClient`, mutator `csrf()` giúp tạo token cho phép thử filter. Để kiểm tra repository/cookie thật, cần gọi endpoint cấp token, đọc cookie/session từ response, giữ chúng giữa các exchange và gửi lại giá trị token theo request handler Reactive. Không dùng post-processor của MockMvc cho WebTestClient.

Các câu hỏi kiểm thử vẫn giống nhau:

- Token có được tạo và lưu trong đúng WebSession/cookie không?
- Cookie được gửi lại trong exchange tiếp theo không?
- Header/parameter có khớp cách request handler đọc token không?
- Token thiếu/sai có bị từ chối không?
- Sau authentication/logout, token/session cũ còn hợp lệ không?

## Bài tập thực hành

Một ứng dụng dùng session login và `HttpSessionCsrfTokenRepository`. Hãy viết test tích hợp cho quy trình:

1. Gọi GET `/csrf` để nhận token A và session A.
2. POST `/profile` với session A nhưng thiếu token: bị từ chối.
3. POST `/profile` với session A và token A: thành công.
4. Dùng token A cùng session B: bị từ chối.
5. Đăng xuất rồi đăng nhập lại, lấy token mới và xác minh token cũ không còn dùng được.

Sau đó chuyển ứng dụng sang `CookieCsrfTokenRepository` cho SPA. Bổ sung test xác nhận cookie `XSRF-TOKEN` được phát, header `X-XSRF-TOKEN` khớp thì request qua CSRF, header sai hoặc thiếu bị từ chối. Kiểm tra riêng request handler nếu ứng dụng dùng XOR/BREACH protection.

## Ghi nhớ

Khi kiểm thử cơ chế CSRF thật, phải kiểm tra **repository + request handler + cookie/session + cách client gửi token** như một luồng hoàn chỉnh. `HttpSessionCsrfTokenRepository` gắn token với session phía server; `CookieCsrfTokenRepository` lưu token trong cookie và thường dùng header cho SPA. Giữ đúng cookie jar giữa các request, lấy token mới sau login/logout khi cần, không giả định token raw và token XOR-render luôn giống nhau. `csrf()` vẫn hữu ích cho test filter, nhưng không thay thế kiểm thử vòng đời token và cookie thực tế.
