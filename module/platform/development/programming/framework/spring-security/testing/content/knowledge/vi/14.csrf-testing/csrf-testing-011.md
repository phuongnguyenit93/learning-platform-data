# CSRF trì hoãn hoặc mã hóa token theo phiên bản và cấu hình

Khi kiểm thử CSRF, không phải lúc nào giá trị token nhìn thấy trong HTML, JSON hoặc cookie cũng giống hệt giá trị được repository lưu. Các phiên bản Spring Security hiện đại có thể **trì hoãn việc tải/tạo token** cho đến khi có thành phần thực sự cần dùng, đồng thời **che (mask) token bằng phép XOR** khi đưa vào nội dung phản hồi để giảm rủi ro BREACH. Vì vậy, một test chỉ đọc token từ session rồi gửi lại có thể không mô phỏng đúng client thật.

Bài học này giải thích ba khái niệm cần tách biệt:

- **Deferred token:** token được biểu diễn bằng supplier và chỉ được tải/tạo khi cần.
- **XOR/BREACH masking:** giá trị được đưa vào request attribute hoặc render cho client có thể được che khác với token gốc trong repository.
- **Request handler:** thành phần quyết định cách token được đưa ra cho view và cách đọc giá trị client gửi lại.

Ta sẽ xem tác động của phiên bản/cấu hình, cách kiểm thử bằng MockMvc và HTTP thật, cũng như trường hợp SPA đọc token raw từ cookie rồi gửi qua header. Nội dung thuộc **Spring Security Testing**: mục tiêu là kiểm tra đúng luồng token trên ứng dụng Servlet và nhận biết ranh giới với WebFlux.

## 1. Phân biệt token gốc, token được render và token client gửi

Một CSRF token có thể đi qua nhiều dạng biểu diễn:

| Dạng | Ý nghĩa |
| --- | --- |
| **Token gốc (repository token)** | Giá trị mà `CsrfTokenRepository` lưu hoặc tải, ví dụ trong HTTP session hay cookie. |
| **Token được cung cấp cho request/view** | Giá trị `CsrfToken` mà request handler đặt vào request attribute để controller/template truy cập. Giá trị này có thể đã được XOR-mask. |
| **Token client gửi lại** | Parameter hoặc header mà browser gửi trong request thay đổi trạng thái. Request handler giải quyết giá trị này trước khi so sánh với token gốc. |

Với handler mặc định dùng XOR, token render có thể thay đổi giữa các response dù token gốc trong repository không đổi. Đây là hành vi có chủ đích, không nhất thiết là token bị rotate hay session bị thay mới.

Đừng so sánh chuỗi token trong HTML với giá trị đọc trực tiếp từ session/cookie rồi kết luận chúng phải giống nhau. Hãy kiểm tra token theo đúng cách client nhận và gửi lại nó.

## 2. Deferred token: chỉ tải hoặc tạo khi cần

Trong cơ chế deferred, filter CSRF có thể làm việc với một supplier của `CsrfToken` thay vì buộc repository tải/tạo token ngay khi request bắt đầu. Khi không có thành phần nào cần token, ứng dụng có thể tránh tạo session hoặc cookie CSRF không cần thiết.

Luồng khái quát:

1. Request vào security filter chain.
2. `CsrfFilter` nhận một đối tượng deferred đại diện cho token.
3. Request handler được gọi với supplier token.
4. Nếu request cần kiểm tra CSRF, filter cần token để so sánh.
5. Nếu controller/view truy cập token để render hoặc trả về client, supplier được gọi và token được tải/tạo.

Điều này có ý nghĩa với endpoint chỉ đọc: một request `GET` không render token có thể không làm phát sinh token/session. Ngược lại, trang form hoặc endpoint bootstrap truy cập token sẽ khiến repository cung cấp token.

Ví dụ endpoint bootstrap chủ động materialize token:

~~~java
@RestController
class CsrfBootstrapController {

    @GetMapping("/csrf")
    ResponseEntity<CsrfToken> csrf(CsrfToken csrfToken) {
        // Truy cập token để materialize deferred value.
        csrfToken.getToken();
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(csrfToken);
    }
}
~~~

Đoạn code minh họa cho Servlet MVC. Khi response serialize `CsrfToken`, client có thể nhận `token`, `parameterName` và `headerName`. Với session repository, token được lưu trong session; với cookie repository, việc truy cập token có thể làm response phát cookie CSRF.

Không cần tạo endpoint bootstrap nếu ứng dụng server-rendered form đã render token trực tiếp. Dù dùng cách nào, response chứa token nên tránh cache dùng chung giữa các user/session.

## 3. XOR masking và BREACH protection

BREACH là một nhóm tấn công side-channel nén HTTP: kẻ tấn công có thể suy luận một phần nội dung bí mật dựa trên thay đổi độ dài response nén khi dữ liệu bí mật và dữ liệu do kẻ tấn công kiểm soát cùng xuất hiện. Nếu CSRF token ổn định được render lặp lại trong response nén, token có thể trở thành mục tiêu suy luận.

XOR masking làm giá trị token được render thay đổi theo mask ngẫu nhiên. Về mặt khái niệm:

- Repository giữ token gốc.
- Request handler tạo một mask ngẫu nhiên và kết hợp với token bằng phép XOR.
- Giá trị đã mask được đưa vào request attribute/view.
- Khi client gửi lại giá trị đó, handler dùng mask được nhúng trong giá trị để khôi phục token gốc trước khi so sánh.

Đây là **che giá trị khi render**, không phải mã hóa token như một bí mật độc lập, không thay thế HTTPS và không bảo vệ khỏi XSS. Client không cần tự thực hiện XOR; hãy gửi lại nguyên giá trị server đã render.

Ví dụ HTML form minh họa:

~~~html
<form method="post" action="/profile">
  <input type="text" name="displayName" value="Lan">
  <input type="hidden" name="_csrf" value="masked-token-do-server-render">
  <button type="submit">Lưu</button>
</form>
~~~

Nếu trang được tải hai lần, giá trị hidden input có thể khác nhau do mask mới, dù token gốc trong session vẫn như cũ. Cả hai giá trị được render đúng cách đều có thể được handler giải quyết và chấp nhận trong ngữ cảnh tương ứng.

## 4. Phiên bản và cấu hình ảnh hưởng hành vi ra sao?

Hành vi mặc định phụ thuộc phiên bản Spring Security và các thành phần được cấu hình:

| Bối cảnh | Điều cần lưu ý |
| --- | --- |
| Các phiên bản cũ trước cơ chế deferred/XOR mặc định | Token thường được tải sớm hơn và cách render có thể không dùng XOR masking mặc định. |
| Spring Security 5.8 | Một số API/hành vi mới được cung cấp để chuẩn bị chuyển đổi; hãy kiểm tra chính xác cấu hình và migration guide của patch version đang dùng. |
| Spring Security 6.x | Deferred token và XOR-based request handling là hành vi mặc định quan trọng cần tính đến khi nâng cấp. |
| Có `CsrfTokenRequestHandler` tùy chỉnh | Cách expose token và resolve header/parameter có thể khác mặc định. |
| Có `CsrfTokenRepository` tùy chỉnh | Nơi lưu token, thời điểm phát token và dữ liệu client cần giữ có thể thay đổi. |

Khi nâng cấp Spring Security, không chỉ kiểm tra test compile thành công. Hãy xác minh:

1. Repository hiện tại có còn là repository được chain sử dụng không?
2. Request handler nào đang được cấu hình?
3. Token render cho form có được mask không?
4. SPA gửi raw cookie token hay token đã render?
5. Các test trước đây đọc token trực tiếp từ session/cookie có còn mô phỏng đúng request client không?

Đừng giả định mọi phiên bản 5.x đều có một hành vi giống nhau hoặc mọi ứng dụng 6.x không thể tùy chỉnh. Hãy xem dependency version thực tế và cấu hình của chain đang kiểm thử.

## 5. MockMvc: kiểm tra token đã render thay vì tự thêm token

`.with(csrf())` tạo token cho request test, rất phù hợp để kiểm tra filter chấp nhận/từ chối. Nhưng khi muốn kiểm tra XOR masking và deferred token, cần lấy giá trị token từ chính response bootstrap hoặc HTML rồi gửi lại.

Giả sử ứng dụng có endpoint:

~~~java
@RestController
class CsrfController {

    @GetMapping("/csrf")
    ResponseEntity<CsrfToken> csrf(CsrfToken token) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(token);
    }
}

@RestController
class ProfileController {

    @PostMapping("/profile")
    ResponseEntity<Void> update() {
        return ResponseEntity.noContent().build();
    }
}
~~~

Với chain dùng `HttpSessionCsrfTokenRepository` và request handler XOR mặc định, một test có thể:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class XorCsrfTokenTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    @WithMockUser(username = "lan")
    void renderedTokenCanBeSentBack() throws Exception {
        MvcResult bootstrap = mockMvc.perform(get("/csrf"))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) bootstrap.getRequest().getSession(false);
        JsonNode json = objectMapper.readTree(
            bootstrap.getResponse().getContentAsString());

        String token = json.get("token").asText();
        String parameterName = json.get("parameterName").asText();

        assertNotNull(session);
        assertFalse(token.isBlank());

        mockMvc.perform(post("/profile")
                .session(session)
                .param(parameterName, token))
            .andExpect(status().isNoContent());
    }
}
~~~

Test này kiểm tra token được expose qua endpoint và gửi lại trong cùng session. Không dùng `csrf()` trong request POST vì mục tiêu là kiểm tra giá trị được server cung cấp.

### Hai response có thể có token render khác nhau

Với XOR masking, cùng một token gốc có thể được render thành các giá trị masked khác nhau qua hai response. Test có thể lấy token hai lần trong cùng session rồi xác nhận từng giá trị được render đều được chấp nhận:

~~~java
@Test
@WithMockUser(username = "lan")
void eachRenderedMaskedValueCanBeResolved() throws Exception {
    MvcResult first = mockMvc.perform(get("/csrf"))
        .andExpect(status().isOk())
        .andReturn();

    MockHttpSession session =
        (MockHttpSession) first.getRequest().getSession(false);
    String firstToken = objectMapper.readTree(
        first.getResponse().getContentAsString())
        .get("token").asText();

    MvcResult second = mockMvc.perform(get("/csrf").session(session))
        .andExpect(status().isOk())
        .andReturn();
    String secondToken = objectMapper.readTree(
        second.getResponse().getContentAsString())
        .get("token").asText();

    assertNotEquals(firstToken, secondToken);

    mockMvc.perform(post("/profile")
            .session(session)
            .param("_csrf", firstToken))
        .andExpect(status().isNoContent());

    mockMvc.perform(post("/profile")
            .session(session)
            .param("_csrf", secondToken))
        .andExpect(status().isNoContent());
}
~~~

Phép so sánh hai chuỗi khác nhau chỉ là kỳ vọng khi test thực sự dùng XOR handler tạo mask mới cho mỗi lần expose token. Nếu ứng dụng dùng handler không mask, repository khác hoặc request handler tùy chỉnh, không áp dụng assertion này. Điều cần bảo đảm là token lấy từ response được gửi lại theo đúng cách handler giải quyết.

## 6. Cookie repository và SPA: raw token khác token được render

Một SPA thường đọc cookie CSRF rồi gửi token qua header. Với `CookieCsrfTokenRepository`, cookie mặc định thường là `XSRF-TOKEN` và header thường là `X-XSRF-TOKEN`. Tuy nhiên, khi handler XOR được dùng để render token, giá trị cookie raw có thể khác giá trị token được render vào request attribute.

Nếu SPA gửi raw cookie value nhưng server cố giải mã header như một XOR-masked value, request có thể bị từ chối. Cấu hình SPA thường cần request handler phân biệt:

- **Header:** nhận raw token do JavaScript đọc từ cookie.
- **Parameter/form:** xử lý giá trị masked theo XOR handler để bảo vệ nội dung render.

Một handler minh họa cho Servlet:

~~~java
final class SpaCsrfTokenRequestHandler
        extends CsrfTokenRequestAttributeHandler {

    private final XorCsrfTokenRequestAttributeHandler xor =
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
        String header = request.getHeader(csrfToken.getHeaderName());
        if (StringUtils.hasText(header)) {
            return super.resolveCsrfTokenValue(request, csrfToken);
        }
        return this.xor.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Handler này buộc token được materialize khi xử lý response và dùng XOR delegate để render. Khi resolve, header có giá trị được xem là raw token; trường hợp parameter dùng XOR delegate. Đăng ký cùng cookie repository:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler()));
~~~

Đây là mẫu cho SPA, không phải cấu hình bắt buộc cho mọi ứng dụng. Hãy kiểm tra hướng dẫn Spring Security đúng phiên bản và cách client thực sự lấy token. Nếu client gửi giá trị masked từ HTML, không được xử lý nó như raw cookie header.

### Kiểm thử raw cookie/header qua HTTP thật

Với cookie repository và handler SPA trên, luồng kiểm thử:

1. Gọi endpoint bootstrap bằng cookie jar.
2. Đọc cookie `XSRF-TOKEN` từ response.
3. Giữ nguyên cookie jar và gửi giá trị cookie trong header `X-XSRF-TOKEN`.
4. Xác nhận request được chấp nhận.
5. Giữ cookie nhưng gửi header sai hoặc bỏ header; xác nhận request bị từ chối.

Không chỉ kiểm tra cookie xuất hiện. Test phải xác minh cặp cookie/header được server giải quyết đúng, và chữ ký/logic nghiệp vụ khác vẫn hoạt động.

## 7. Deferred token và session/cookie được tạo khi nào?

Một khác biệt đáng kiểm tra là request an toàn có tạo session/token hay không. Trong cấu hình deferred, một request `GET` không truy cập token có thể không cần materialize token. Nhưng nếu view render hidden input hoặc controller gọi `getToken()`, token sẽ được tải/tạo.

Ví dụ so sánh hai endpoint:

| Request | Có truy cập CSRF token? | Kỳ vọng với deferred token |
| --- | --- | --- |
| `GET /health` chỉ trả text | Không | Không nhất thiết tạo token/session chỉ vì CSRF filter chạy. |
| `GET /csrf` trả `CsrfToken` | Có | Token được materialize và trả cho client. |
| `GET /profile/edit` render form có hidden token | Có | Token được materialize để view render. |
| `POST /profile` thuộc matcher CSRF | Có, để kiểm tra request | Repository được yêu cầu cung cấp token để so sánh. |

Không dùng việc “GET không có session” làm assertion chung cho mọi ứng dụng: security context persistence, request cache, login mechanism hoặc code ứng dụng khác có thể tạo session vì lý do riêng. Nếu cần test lazy creation, cô lập cấu hình và kiểm tra đúng nguyên nhân tạo session.

## 8. Những lỗi thường gặp khi test token deferred/XOR

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Đọc token trong session rồi gửi vào form parameter nhưng nhận 403 | Request handler mong giá trị đã XOR-mask được render cho client | Lấy token từ HTML/JSON request attribute và gửi lại nguyên giá trị. |
| Token trong hai response khác nhau | XOR tạo mask mới, không nhất thiết token gốc đã đổi | Kiểm tra từng token render có được chấp nhận; không so với raw repository token. |
| SPA gửi cookie raw qua header nhưng nhận 403 | Handler mặc định đang giải quyết header như token masked hoặc không đúng convention SPA | Cấu hình request handler SPA tương thích và test raw header riêng. |
| GET bootstrap không phát cookie | Deferred token chưa được truy cập/materialize | Gọi `csrfToken.getToken()` hoặc render token theo cách ứng dụng cần. |
| Test với `.with(csrf())` luôn pass nhưng browser fail | Helper không kiểm tra quá trình phát token/cookie và cách client gửi | Thêm HTTP integration/browser test với cookie jar. |
| Sau login token cũ không dùng được | Authentication strategy xóa token và/hoặc đổi session | Lấy token mới sau login và giữ cookie/session mới. |
| Nâng cấp framework khiến test cũ fail | Default handler/deferred behavior thay đổi | Kiểm tra version, repository, request handler và cách lấy token trong test. |

Khi thấy `403`, đừng lập tức tắt XOR handler. Trước tiên xác định client đang gửi raw token hay masked token, header hay parameter, và handler nào được cấu hình.

## 9. Kiểm thử HTML form và JavaScript theo đúng representation

Với form server-rendered, hãy lấy hidden input từ HTML thực tế rồi submit nguyên giá trị:

~~~text
GET /profile/edit
  -> cookie/session được giữ
  -> HTML chứa hidden input name="_csrf", value="<masked-token>"

POST /profile
  Cookie: <session-cookie>
  Body: displayName=Lan&_csrf=<masked-token-tu-HTML>
  -> request handler giải quyết token
~~~

Với SPA dùng cookie repository và handler tương thích raw header:

~~~text
GET /csrf
  -> Set-Cookie: XSRF-TOKEN=<raw-token>

POST /profile
  Cookie: XSRF-TOKEN=<raw-token>; <session-cookie-neu-co>
  X-XSRF-TOKEN: <raw-token>
  -> request handler đọc raw header và repository đối chiếu
~~~

Hai luồng này không được trộn lẫn. Token masked render trong form và raw cookie value có thể là hai representation khác nhau. Client cần gửi đúng representation mà server request handler chờ đợi.

## 10. Đối chiếu với WebFlux

Reactive có các abstraction tương ứng nhưng API khác Servlet:

- `ServerCsrfTokenRepository` quản lý token cho WebFlux.
- `ServerCsrfTokenRequestHandler` xử lý cách expose/resolve token.
- Các handler XOR phía Reactive có thể áp dụng masking tương tự, tùy phiên bản.
- `WebTestClient` dùng mutator `csrf()` để kiểm tra filter, còn HTTP integration test cần lấy token/cookie từ response thật.

Không dùng `CsrfTokenRequestHandler` của Servlet hoặc `MockMvc RequestPostProcessor` trong ứng dụng Reactive. Khi kiểm thử deferred/XOR trên WebFlux, hãy kiểm tra implementation và API có trong đúng phiên bản Spring Security Reactive mà ứng dụng đang dùng.

## 11. Checklist khi nâng cấp hoặc tùy chỉnh CSRF

- [ ] Ghi nhận phiên bản Spring Security thực tế của ứng dụng.
- [ ] Xác định `CsrfTokenRepository` đang dùng.
- [ ] Xác định request handler mặc định hay custom.
- [ ] Biết token nào là raw repository token và token nào được render/mask.
- [ ] Endpoint bootstrap có materialize token khi client cần không?
- [ ] Response token có `Cache-Control: no-store` không?
- [ ] Form submit lại đúng giá trị token render không?
- [ ] SPA gửi đúng raw/masked representation theo header/parameter không?
- [ ] Cookie/session được giữ giữa các request không?
- [ ] Có ca thiếu token, token sai và token hợp lệ không?
- [ ] Có test sau login/logout/session rotation không?
- [ ] Không dùng `.with(csrf())` làm bằng chứng duy nhất cho luồng browser thật.
- [ ] Với WebFlux, dùng đúng repository và request handler Reactive.

## Bài tập thực hành

Một ứng dụng Servlet nâng từ Spring Security 5.7 lên 6.x. Ứng dụng dùng session repository và form Thymeleaf, đồng thời có SPA dùng cookie repository ở một chain riêng.

Hãy thiết kế test để chứng minh:

1. Endpoint bootstrap trả token và giữ đúng session.
2. Hai lần render form có thể cho giá trị XOR khác nhau nhưng mỗi giá trị đều gửi lại được.
3. Form submit dùng token masked lấy từ HTML.
4. SPA nhận raw token từ cookie và gửi trong header theo request handler đã cấu hình.
5. Header sai hoặc thiếu bị từ chối.
6. Sau login/session rotation, client lấy token mới nếu token cũ đã bị xóa.

Giải thích vì sao một test dùng `.with(csrf())` có thể pass nhưng chưa chứng minh browser thực sự gửi đúng representation.

## Ghi nhớ

Deferred token quyết định **khi nào** repository được yêu cầu tải/tạo token; XOR/BREACH handler quyết định **giá trị nào** được expose và cách giải quyết giá trị client gửi lại. Repository token, token masked trong form và raw cookie token không nhất thiết giống nhau. Hãy kiểm tra theo đúng phiên bản, repository và request handler, lấy token từ response thật rồi gửi lại bằng cùng session/cookie. Helper `csrf()` kiểm tra filter, còn test HTTP thật chứng minh vòng đời và representation của token.
