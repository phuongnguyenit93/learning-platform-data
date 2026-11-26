# useInvalidToken để kiểm tra nhánh từ chối trong MockMvc

Trong **Spring Security Testing**, một request có CSRF token nhưng mang giá trị không hợp lệ phải bị từ chối giống như request thiếu token. Với ứng dụng Servlet kiểm thử bằng **MockMvc**, `csrf().useInvalidToken()` là cách ngắn gọn để tạo request thuộc trường hợp này. Nó cho phép kiểm tra trực tiếp nhánh từ chối của bộ lọc CSRF mà không cần tự chế chuỗi token hoặc tự dựng session.

Bài học tập trung vào cách dùng `useInvalidToken()` để xác nhận server từ chối request, cách kết hợp với `asHeader()`, cách viết ca đối chứng có token hợp lệ và cách chứng minh logic nghiệp vụ không chạy khi CSRF thất bại. Trọng tâm là **nhánh từ chối trong MockMvc**; các mutator của WebTestClient thuộc API Reactive riêng.

## 1. `useInvalidToken()` giải quyết trường hợp nào?

Một bộ kiểm thử CSRF tối thiểu thường có ba trường hợp:

| Trường hợp | Request gửi đi | Kết quả thường mong đợi |
| --- | --- | --- |
| Thiếu token | Không có CSRF parameter hoặc header | Bị từ chối, thường là `403 Forbidden`. |
| Token hợp lệ | Có token phù hợp với token server mong đợi | Qua bước CSRF và tiếp tục xử lý request. |
| Token không hợp lệ | Có token nhưng giá trị không khớp token server mong đợi | Bị từ chối, thường là `403 Forbidden`. |

Hai trường hợp âm tính không giống nhau. Request thiếu token kiểm tra server có bắt buộc token hay không; request có token sai kiểm tra server có xác minh **giá trị** token hay chỉ kiểm tra sự hiện diện của một trường. `useInvalidToken()` giúp tạo trường hợp thứ hai.

Với MockMvc, import phương thức `csrf`:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
~~~

Sau đó gắn post-processor vào request:

~~~java
mockMvc.perform(post("/transfers")
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
~~~

`csrf()` trả về một `RequestPostProcessor` chuyên chuẩn bị CSRF token cho request MockMvc. `useInvalidToken()` cấu hình post-processor gửi giá trị token không hợp lệ. Khi request đi qua `CsrfFilter` và thuộc diện cần bảo vệ, bộ lọc từ chối request trước khi controller xử lý.

Không cần tự đặt tên parameter, tự tạo header hoặc đoán một chuỗi token sai. Cũng không nên phụ thuộc vào giá trị chuỗi cụ thể mà helper tạo ra: điều cần kiểm tra là **token bị từ chối**, không phải nội dung nội bộ của token thử nghiệm.

## 2. Điều kiện để phép thử thực sự kiểm tra CSRF

Trước khi viết assertion `403`, xác nhận các điều kiện sau:

1. Ứng dụng đang dùng cấu hình Servlet và request được xử lý bởi `SecurityFilterChain` có CSRF bật.
2. HTTP method và path khớp quy tắc yêu cầu CSRF. Theo matcher mặc định, `POST`, `PUT`, `PATCH`, `DELETE` cần token; `GET`, `HEAD`, `OPTIONS`, `TRACE` thường không cần.
3. Request không nằm trong ngoại lệ như `ignoringRequestMatchers(...)` và không đi qua chain khác đã gọi `csrf.disable()`.
4. Người dùng thử nghiệm đã đăng nhập và có quyền thực hiện thao tác, để kết quả `403` không bị nhầm với lỗi phân quyền.
5. MockMvc có đăng ký các filter bảo mật. Nếu bỏ qua filter, request có thể tới controller dù token sai.

Ví dụ cấu hình Servlet:

~~~java
@Configuration
@EnableWebSecurity
class TransferSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.POST, "/transfers").hasRole("USER")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Ví dụ dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để nạp ứng dụng cùng filter chain:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TransferCsrfTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

Nếu tự dựng MockMvc từ `WebApplicationContext`, phải gắn Spring Security:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Với `standaloneSetup(controller)` không gắn security filter hoặc `@AutoConfigureMockMvc(addFilters = false)`, phép thử không thể chứng minh hành vi của `CsrfFilter`.

## 3. Tạo request có token không hợp lệ

Giả sử endpoint `POST /transfers` nhận JSON và gọi service để tạo giao dịch:

~~~java
record TransferCommand(String recipient, long amount) {}

interface TransferService {
    void create(TransferCommand command);
}

@RestController
class TransferController {

    private final TransferService transferService;

    TransferController(TransferService transferService) {
        this.transferService = transferService;
    }

    @PostMapping(
        path = "/transfers",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<Void> create(@RequestBody TransferCommand command) {
        transferService.create(command);
        return ResponseEntity.noContent().build();
    }
}
~~~

Request kiểm thử có token sai:

~~~java
@Test
@WithMockUser(username = "alice", roles = "USER")
void invalidCsrfToken_isRejected() throws Exception {
    mockMvc.perform(post("/transfers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "recipient": "bob",
                  "amount": 500
                }
                """)
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
}
~~~

`@WithMockUser` tạo danh tính đã xác thực với role `USER`. JSON và URL giống request hợp lệ; khác biệt cần kiểm tra là giá trị CSRF token. Với cấu hình mặc định, `CsrfFilter` từ chối request sai token và controller không được gọi.

Khi dùng phiên bản Java chưa hỗ trợ text block, thay `.content("""...""")` bằng chuỗi JSON thông thường đã escape hoặc một object được serialize bằng `ObjectMapper`.

## 4. Viết ba ca đối chứng trong cùng lớp test

Chỉ kiểm tra token sai bị `403` vẫn chưa đủ. Hãy giữ nguyên user, URL, method và body, sau đó so sánh request thiếu token, token hợp lệ và token không hợp lệ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TransferCsrfTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    TransferService transferService;

    private static final String BODY = """
        {
          "recipient": "bob",
          "amount": 500
        }
        """;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void missingToken_isForbiddenAndDoesNotCreateTransfer() throws Exception {
        mockMvc.perform(post("/transfers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY))
            .andExpect(status().isForbidden());

        verifyNoInteractions(transferService);
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void validToken_reachesController() throws Exception {
        mockMvc.perform(post("/transfers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY)
                .with(csrf()))
            .andExpect(status().isNoContent());

        verify(transferService).create(
            new TransferCommand("bob", 500)
        );
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void invalidToken_isForbiddenAndDoesNotCreateTransfer() throws Exception {
        mockMvc.perform(post("/transfers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(BODY)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        verifyNoInteractions(transferService);
    }
}
~~~

`@MockBean` được dùng rộng rãi trong các dự án Spring Boot để thay bean service bằng mock. Ở các phiên bản Spring Boot mới có thể ưu tiên `@MockitoBean` theo phiên bản Spring Framework đang sử dụng. Mục tiêu của ví dụ là xác minh controller/service không thực hiện thao tác khi CSRF thất bại.

Ba phép thử tạo ra bằng chứng rõ ràng:

- Request thiếu token bị từ chối và service không được gọi.
- Request có token hợp lệ vượt qua CSRF, controller gọi service.
- Request có token sai bị từ chối và service không được gọi.

Spring Boot Test mặc định reset mock giữa các phương thức kiểm thử theo cấu hình thông dụng của `@MockBean`. Nếu dự án thay đổi chế độ reset hoặc dùng mock dùng chung theo cách khác, cần bảo đảm tương tác của từng test được cô lập.

Nếu service được gọi gián tiếp bởi listener hoặc thành phần khác trong quá trình khởi tạo test, `verifyNoInteractions` có thể quá nghiêm. Khi đó, xác minh tương tác cụ thể liên quan tới lệnh tạo giao dịch, hoặc kiểm tra trạng thái dữ liệu sau request. Điều quan trọng là chứng minh thao tác được bảo vệ không xảy ra.

## 5. Dùng `useInvalidToken()` với request parameter

Mặc định, `csrf()` gắn token vào request parameter. Do đó, cách dùng sau kiểm tra nhánh từ chối khi token parameter có giá trị sai:

~~~java
@Test
@WithMockUser(roles = "USER")
void invalidParameterToken_isForbidden() throws Exception {
    mockMvc.perform(post("/transfers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"recipient\":\"bob\",\"amount\":500}")
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());
}
~~~

Trong request builder, `useInvalidToken()` vẫn được áp dụng qua `RequestPostProcessor`. Không cần tự gọi `.param("_csrf", "wrong")`, bởi tên parameter và token được helper lấy từ cơ chế CSRF của Spring Security trong ngữ cảnh kiểm thử.

Nếu ứng dụng tùy chỉnh `CsrfTokenRepository` hoặc `CsrfTokenRequestHandler`, hãy kiểm tra cấu hình thực tế. Một phép thử với post-processor tiêu chuẩn không tự chứng minh rằng form HTML của ứng dụng render đúng field hoặc client gửi đúng cách qua HTTP thật.

## 6. Dùng `useInvalidToken()` với HTTP header

JavaScript thường gửi CSRF token qua header. MockMvc có thể kiểm tra nhánh từ chối này bằng cách kết hợp `asHeader()` và `useInvalidToken()`:

~~~java
@Test
@WithMockUser(roles = "USER")
void invalidHeaderToken_isForbidden() throws Exception {
    mockMvc.perform(post("/transfers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"recipient\":\"bob\",\"amount\":500}")
            .with(csrf().asHeader().useInvalidToken()))
        .andExpect(status().isForbidden());
}
~~~

Để đối chiếu, gửi header với token hợp lệ:

~~~java
@Test
@WithMockUser(roles = "USER")
void validHeaderToken_isAccepted() throws Exception {
    mockMvc.perform(post("/transfers")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"recipient\":\"bob\",\"amount\":500}")
            .with(csrf().asHeader()))
        .andExpect(status().isNoContent());
}
~~~

`asHeader()` yêu cầu post-processor gửi token bằng header thay vì request parameter. Tên header cụ thể phụ thuộc `CsrfToken`/repository được sử dụng; với cấu hình Servlet mặc định thường là `X-CSRF-TOKEN`, còn `CookieCsrfTokenRepository` thường dùng `X-XSRF-TOKEN`. Helper giúp test tạo request theo tên header tương ứng, vì vậy không nên hard-code một tên header rồi cho rằng nó đúng với mọi cấu hình.

Khi ứng dụng có JavaScript client, test trên chứng minh server từ chối token header sai. Nó không thay thế kiểm thử trình duyệt lấy token từ meta tag/cookie, giữ session và gửi header qua `fetch`.

## 7. Vì sao không nên tự tạo chuỗi token sai?

Một cách viết dễ gặp là:

~~~java
mockMvc.perform(post("/transfers")
        .param("_csrf", "wrong-token"))
    .andExpect(status().isForbidden());
~~~

Cách này gắn cứng tên parameter `_csrf` và giả định giá trị `"wrong-token"` luôn sai. Nó có thể không phù hợp khi:

- Ứng dụng đổi tên parameter hoặc header qua repository tùy chỉnh.
- Request handler có cách biểu diễn/giải mã token riêng.
- Request đang gửi token qua header thay vì parameter.
- Cấu hình CSRF thay đổi theo chain hoặc môi trường kiểm thử.

`csrf().useInvalidToken()` thể hiện rõ ý định của test: tạo một request có token không hợp lệ theo post-processor của Spring Security Test. Nó cũng giúp người đọc phân biệt ngay ca **token sai** với ca **không gửi token**.

Không assert nội dung token được tạo ra, không log token thật ra output test và không sao chép token giữa các test/session. Token là dữ liệu bảo mật gắn với ngữ cảnh request; bài kiểm thử chỉ cần quan sát hành vi chấp nhận hoặc từ chối.

## 8. Đọc đúng kết quả `403`

`403 Forbidden` là kết quả thường gặp khi `CsrfFilter` từ chối request, nhưng không phải mã trạng thái chỉ dành riêng cho CSRF. Phân quyền cũng có thể trả `403`. Một số ứng dụng cấu hình `AccessDeniedHandler` riêng để đổi status, response body hoặc định dạng lỗi.

| Kết quả quan sát | Điều cần xác minh |
| --- | --- |
| Token sai trả `403`, token hợp lệ trả `204` với cùng user | Bằng chứng tốt cho nhánh CSRF từ chối. |
| Cả token sai và token hợp lệ đều trả `403` | Có thể user thiếu quyền, URL khớp chain khác hoặc controller/security rule khác từ chối. |
| Token sai trả `204` | Có thể CSRF bị tắt, request được miễn, filter không chạy hoặc request không khớp matcher. |
| Token sai trả `401` hoặc redirect | Kiểm tra authentication entry point và thứ tự xử lý; user thử nghiệm có thể chưa được xác thực như dự kiến. |
| Token hợp lệ trả `400` | CSRF có thể đã qua nhưng body, validation hoặc định dạng request không hợp lệ. |

Khi chẩn đoán, kiểm tra lần lượt:

1. `SecurityFilterChain` nào khớp request và thứ tự `@Order`.
2. CSRF có bật trong chain đó không; request có nằm trong `ignoringRequestMatchers(...)` không.
3. MockMvc có chạy security filter không.
4. Người dùng thử nghiệm có role/scope cần thiết không.
5. `CsrfTokenRepository` và `CsrfTokenRequestHandler` có được tùy chỉnh không.
6. Response có bị `AccessDeniedHandler`, exception handler hoặc filter riêng thay đổi không.

Đừng sửa một ca test trả `403` bằng cách thêm `csrf()` ngay lập tức. Trước hết hãy xác định test đang kiểm tra nhánh CSRF hay nhánh phân quyền.

## 9. Ranh giới với WebTestClient và ứng dụng Reactive

`csrf().useInvalidToken()` trong bài này là API của `SecurityMockMvcRequestPostProcessors` dành cho **Servlet/MockMvc**. WebFlux dùng `SecurityWebFilterChain`, `WebTestClient` và `SecurityMockServerConfigurers`; không đưa `RequestPostProcessor` của MockMvc sang Reactive.

Ví dụ Reactive cho token hợp lệ:

~~~java
webTestClient
    .mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .post()
    .uri("/transfers")
    .exchange()
    .expectStatus().isNoContent();
~~~

Ở đây `csrf()` là mutator của `WebTestClient`, không phải cùng đối tượng `RequestPostProcessor` với MockMvc. Khi cần kiểm thử giá trị sai qua HTTP thật trên Reactive, lấy token do ứng dụng cấp, giữ đúng cookie/session, gửi lại một giá trị đã thay đổi theo header/parameter mà cấu hình Reactive hỗ trợ. Đừng tự suy ra API hoặc hành vi của WebTestClient từ `useInvalidToken()` phía Servlet.

## 10. Checklist cho nhánh từ chối

Trước khi hoàn tất một test dùng `useInvalidToken()`, kiểm tra các điểm sau:

- [ ] Test dùng đúng API `SecurityMockMvcRequestPostProcessors.csrf()` của MockMvc.
- [ ] Request method/path thực sự thuộc diện cần CSRF.
- [ ] Security filter chain đang chạy trong MockMvc.
- [ ] User được xác thực và có đủ quyền để đi tới controller nếu token hợp lệ.
- [ ] Có ca đối chứng dùng `.with(csrf())` với cùng method, path, user và body.
- [ ] Có thể phân biệt ca thiếu token với ca token sai.
- [ ] Assertion kiểm tra status phù hợp với error handler của ứng dụng.
- [ ] Xác minh service/dữ liệu không thay đổi khi token sai.
- [ ] Nếu kiểm tra header, dùng `.asHeader()` và đúng cấu hình repository/handler.
- [ ] Không phụ thuộc vào chuỗi token nội bộ hoặc ghi token ra log.

## Bài tập ngắn

Endpoint `POST /orders` yêu cầu role `CUSTOMER` và CSRF. Controller gọi `orderService.placeOrder(...)` rồi trả `201 Created`. Hãy viết ba phép thử với cùng user `CUSTOMER` và cùng JSON body:

1. Không gửi token: kỳ vọng bị từ chối và `orderService` không được gọi.
2. Gửi `.with(csrf())`: kỳ vọng `201 Created` và service được gọi.
3. Gửi `.with(csrf().useInvalidToken())`: kỳ vọng bị từ chối và service không được gọi.

Sau đó đổi hai ca âm tính sang gửi token qua header. Ca token sai cần dùng `.with(csrf().asHeader().useInvalidToken())`; ca hợp lệ dùng `.with(csrf().asHeader())`. So sánh kết quả để chắc chắn server xử lý đúng cả hai vị trí truyền token.

## Ghi nhớ

`csrf().useInvalidToken()` là công cụ tạo **request có CSRF token không hợp lệ** trong MockMvc. Dùng nó để kiểm tra nhánh từ chối, kết hợp `asHeader()` nếu client gửi token qua header, và luôn so sánh với request token hợp lệ trong cùng điều kiện xác thực/phân quyền. Một test tốt còn chứng minh controller/service không chạy và dữ liệu không đổi khi CSRF token sai.
