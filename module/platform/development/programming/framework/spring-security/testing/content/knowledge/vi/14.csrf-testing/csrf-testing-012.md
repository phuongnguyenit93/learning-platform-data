# Không tắt CSRF chỉ để làm một bài kiểm thử đi qua

Khi một bài kiểm thử HTTP nhận `403 Forbidden` vì thiếu CSRF token, cách sửa đúng thường là **chuẩn bị token trong request kiểm thử** hoặc sửa điều kiện test chưa đúng. Tắt CSRF để assertion chuyển sang `200`/`204` có thể làm test đi qua nhưng đồng thời loại bỏ chính lớp bảo vệ mà bài test cần kiểm tra.

Trong module **Spring Security Testing**, `MockMvc`, `WebTestClient`, `@WithMockUser` và các helper CSRF giúp mô phỏng những request được phép hoặc bị từ chối. Bài học này hướng dẫn chẩn đoán lỗi test, giữ nguyên chính sách bảo mật, phân biệt test dương tính với test âm tính và chỉ cấu hình ngoại lệ khi kiến trúc xác thực thực sự yêu cầu.

## 1. Vì sao không nên tắt CSRF để sửa test?

CSRF bảo vệ endpoint thay đổi trạng thái khỏi request giả mạo trong tình huống trình duyệt tự động gửi credential, thường là cookie phiên. Khi chain bật CSRF, request thuộc diện bảo vệ cần token hợp lệ. Nếu test gửi `POST` mà không có token, `CsrfFilter` từ chối request trước khi controller chạy.

Ví dụ một test ban đầu:

~~~java
mockMvc.perform(post("/profile"))
    .andExpect(status().isNoContent());
~~~

Nếu `POST /profile` cần CSRF, request trên thiếu token và thường nhận `403`. Tắt CSRF trong cấu hình để test nhận `204` sẽ làm thay đổi chính sách của ứng dụng. Test không còn chứng minh endpoint được bảo vệ; nó chỉ chứng minh controller chạy khi bộ lọc CSRF không tham gia.

Những cách sửa có thể che giấu lỗi:

- Gọi `csrf.disable()` trong cấu hình dùng chung chỉ để test pass.
- Thêm cấu hình test thay thế `SecurityFilterChain` bằng chain không có CSRF.
- Dùng `@AutoConfigureMockMvc(addFilters = false)` để bỏ qua toàn bộ servlet filter.
- Dựng `MockMvc` bằng `standaloneSetup(controller)` mà không gắn Spring Security.
- Xóa assertion về `403` hoặc đổi expected status mà không hiểu request bị từ chối ở đâu.

Mỗi cách trên đều có thể làm bài test mất khả năng kiểm tra bảo mật thực tế. Hãy xác định test đang cần chứng minh điều gì trước khi thay đổi request hoặc cấu hình.

## 2. Phân loại test trước khi thêm CSRF token

Không phải request nào cũng nên có token. Hãy xác định loại test:

| Loại test | Token cần gửi? | Kết quả cần chứng minh |
| --- | --- | --- |
| Request hợp lệ tới endpoint cần CSRF | Có token hợp lệ | Request qua CSRF rồi tiếp tục xác thực, phân quyền và nghiệp vụ. |
| Request thiếu token | Không | Server từ chối request thuộc diện bảo vệ. |
| Request có token sai | Có token không hợp lệ | Server từ chối giá trị không khớp. |
| Endpoint được miễn CSRF có chủ đích | Không | Request qua bước CSRF nhưng vẫn phải qua cơ chế bảo vệ riêng. |
| HTTP method an toàn theo matcher mặc định | Thường không | Không bị CSRF chặn; handler vẫn phải có ngữ nghĩa chỉ đọc. |

Một test dương tính cho thao tác thay đổi trạng thái nên gửi token hợp lệ. Một test âm tính kiểm tra CSRF phải cố ý bỏ token hoặc gửi token sai. Không thêm token vào tất cả request một cách máy móc, vì làm vậy sẽ xóa mất các ca âm tính.

## 3. Sửa test MockMvc bằng csrf() đúng mục đích

Với Servlet, Spring Security Test cung cấp `csrf()` dưới dạng `RequestPostProcessor`. Gắn nó vào request bằng `.with(csrf())`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProfileSecurityTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void updateProfile_withValidCsrfToken_succeeds() throws Exception {
        mockMvc.perform(post("/profile")
                .with(csrf()))
            .andExpect(status().isNoContent());
    }
}
~~~

`@WithMockUser` thiết lập danh tính và quyền trong `SecurityContext`; nó **không tự thêm CSRF token**. `csrf()` giải quyết phần token; hai công cụ phục vụ hai điều kiện độc lập.

Nếu ứng dụng nhận token qua header, có thể dùng:

~~~java
mockMvc.perform(post("/profile")
        .with(csrf().asHeader()))
    .andExpect(status().isNoContent());
~~~

Nếu muốn kiểm tra token sai:

~~~java
mockMvc.perform(post("/profile")
        .with(csrf().useInvalidToken()))
    .andExpect(status().isForbidden());
~~~

Đừng thêm `.with(csrf())` vào ca thiếu token hoặc ca token sai. Mỗi test phải giữ đúng ý định của nó.

## 4. Giữ đủ ba ca đối chứng: thiếu, hợp lệ và sai

Một bộ test nhỏ nhưng có ý nghĩa nên kiểm tra cả ba trường hợp trên cùng endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ProfileCsrfTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void missingToken_isForbidden() throws Exception {
        mockMvc.perform(post("/profile"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void validToken_allowsRequest() throws Exception {
        mockMvc.perform(post("/profile").with(csrf()))
            .andExpect(status().isNoContent());
    }

    @Test
    @WithMockUser(username = "lan", roles = "USER")
    void invalidToken_isForbidden() throws Exception {
        mockMvc.perform(post("/profile")
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }
}
~~~

Ba ca dùng cùng user, method và path; thay đổi duy nhất là trạng thái token. Nếu ca token hợp lệ vẫn trả `403`, hãy kiểm tra quyền, matcher, filter chain và controller trước khi kết luận CSRF sai.

Với thao tác ghi dữ liệu, nên xác minh thêm service không được gọi hoặc dữ liệu không đổi trong hai ca âm tính. Status `403` riêng lẻ không chứng minh request không tạo tác dụng phụ ở tầng khác.

## 5. Nếu test vẫn 403 sau khi đã thêm csrf()

Một request có token hợp lệ vẫn có thể bị từ chối bởi authentication, authorization, validation hoặc một filter khác. Kiểm tra theo thứ tự:

1. **Đúng filter chain:** URL có khớp `securityMatcher` và `@Order` như dự kiến không?
2. **CSRF matcher:** request có thực sự cần token không? Có custom matcher hoặc repository/request handler không?
3. **Filter có chạy:** MockMvc có được cấu hình với Spring Security không?
4. **Danh tính:** `@WithMockUser` hoặc `user()` có thiết lập đúng user không?
5. **Quyền:** `hasRole("EDITOR")` cần `ROLE_EDITOR`; `hasAuthority("reports:write")` cần đúng authority `reports:write`.
6. **Request:** path, method, content type, body và validation có hợp lệ không?
7. **Response handler:** `AccessDeniedHandler`, `AuthenticationEntryPoint` hoặc exception handler có tùy chỉnh status/body không?

Ví dụ test user thiếu role:

~~~java
@Test
@WithMockUser(username = "viewer", roles = "VIEWER")
void viewerWithValidToken_isForbiddenByAuthorization() throws Exception {
    mockMvc.perform(post("/reports").with(csrf()))
        .andExpect(status().isForbidden());
}
~~~

Ở đây token hợp lệ nhưng user thiếu role. Thêm hoặc sửa token không thể cấp role `EDITOR` cho user. Cần sửa dữ liệu test nếu mục tiêu là ca được phép, hoặc giữ test này nếu mục tiêu là kiểm tra authorization.

## 6. Đảm bảo MockMvc thực sự chạy Spring Security

Với Spring Boot, cách phổ biến là:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SecurityIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Nếu dựng MockMvc thủ công từ application context:

~~~java
MockMvc mockMvc = MockMvcBuilders
    .webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Cần import `SecurityMockMvcConfigurers.springSecurity`. Cấu hình này gắn Spring Security filter chain vào MockMvc.

Kiểm tra các cấu hình dễ vô tình bỏ filter:

- `@AutoConfigureMockMvc(addFilters = false)` tắt đăng ký filter cho MockMvc.
- `standaloneSetup(controller)` không tự nạp toàn bộ filter chain của ứng dụng.
- `@WebMvcTest` chỉ nạp một phần context; có thể cần import cấu hình security thực tế của slice test.
- `@TestConfiguration` khai báo `SecurityFilterChain` mới có thể thay đổi chính sách mà test đang dùng.

Nếu test cần chứng minh cấu hình production, hãy nạp chain tương ứng và xác nhận matcher của request. Không tạo một chain yếu hơn chỉ để test đi qua.

## 7. Không dùng profile test để âm thầm tắt CSRF

Một cấu hình như sau có thể làm test dễ chạy:

~~~java
@Profile("test")
@Bean
SecurityFilterChain testSecurity(HttpSecurity http) throws Exception {
    http.csrf(csrf -> csrf.disable());
    http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
    return http.build();
}
~~~

Nhưng nếu test đang được dùng để kiểm chứng chính sách bảo mật, cấu hình này khiến các assertion không còn đại diện cho chain cần kiểm tra. Một test chạy với profile `test` và CSRF bị tắt không chứng minh ứng dụng khi chạy với cấu hình thật sẽ từ chối request thiếu token.

Hãy phân biệt hai mục tiêu:

- **Test logic controller thuần:** có thể dùng unit test gọi trực tiếp service/controller mà không tuyên bố kiểm tra Spring Security.
- **Test tích hợp bảo mật:** phải nạp cấu hình filter chain cần xác minh, bao gồm CSRF và authorization.

Không dùng một cấu hình test yếu hơn rồi đặt tên test như thể nó đã xác minh CSRF.

## 8. Khi nào được miễn hoặc tắt CSRF?

Có trường hợp kiến trúc cho phép miễn CSRF cho một phạm vi request, ví dụ webhook server-to-server xác minh chữ ký hoặc API Bearer token không dùng credential tự động gửi bởi browser. Khi đó, quyết định phải dựa trên cách xác thực thực tế, không phải vì test gặp `403`.

Phân biệt:

| Cấu hình | Tác động |
| --- | --- |
| `csrf.ignoringRequestMatchers("/webhooks/**")` | Miễn CSRF cho request khớp matcher trong chain hiện tại. |
| `permitAll()` | Bỏ yêu cầu phân quyền/đăng nhập cho request đó; CSRF vẫn có thể bắt buộc. |
| `csrf.disable()` | Tắt CSRF cho toàn bộ chain đang cấu hình. |

Nếu chỉ webhook cần miễn, giới hạn matcher theo path và method cần thiết. Sau đó kiểm thử:

- Webhook không token nhưng chữ ký hợp lệ được xử lý.
- Webhook chữ ký sai bị từ chối và không gọi service.
- Endpoint web dùng session cookie ngoài ngoại lệ vẫn cần token.
- Path gần giống nhưng không thuộc ngoại lệ vẫn bị CSRF bảo vệ.

Không tắt CSRF cho cả chain web chỉ vì một endpoint tích hợp cần nhận request không có token. Nếu một API chain riêng được thiết kế không dùng cookie/session credential và dùng Bearer token trong `Authorization` header, có thể có chính sách CSRF riêng; test phải xác minh đúng chain đó và mô hình token không bị browser tự gửi.

## 9. Với WebTestClient, thêm token bằng API Reactive

Ứng dụng WebFlux dùng `SecurityWebFilterChain` và `WebTestClient`. Helper `csrf()` ở đây là mutator của WebTestClient, không phải RequestPostProcessor của MockMvc:

~~~java
webTestClient
    .mutateWith(mockUser("lan"))
    .mutateWith(csrf())
    .post()
    .uri("/profile")
    .exchange()
    .expectStatus().isNoContent();
~~~

Test âm tính thiếu token:

~~~java
webTestClient
    .mutateWith(mockUser("lan"))
    .post()
    .uri("/profile")
    .exchange()
    .expectStatus().isForbidden();
~~~

Đảm bảo client đã được cấu hình tích hợp Spring Security. Nếu test kết nối server thật, cần kiểm tra token/cookie được cấp và gửi lại theo `ServerCsrfTokenRepository` cùng request handler Reactive. Không dùng `csrf().useInvalidToken()` hoặc `asHeader()` từ API Servlet cho WebTestClient.

## 10. Một quy trình chẩn đoán thực tế

Khi một test bất ngờ nhận `403`, xử lý theo quy trình sau:

1. Đọc test để xác định đây là request dương tính hay âm tính.
2. Xác định endpoint có khớp CSRF matcher và chain nào được chọn.
3. Nếu là request dương tính, thêm token hợp lệ bằng helper phù hợp với loại ứng dụng.
4. Giữ nguyên user và request, chạy đối chứng với token thiếu/sai để xác nhận CSRF thực sự hoạt động.
5. Nếu token hợp lệ vẫn bị từ chối, kiểm tra authentication và authority.
6. Kiểm tra service invocation hoặc trạng thái dữ liệu để xác định request đã tới nghiệp vụ chưa.
7. Chỉ thay đổi cấu hình CSRF khi chính sách bảo mật của endpoint thực sự cần thay đổi; bổ sung test cho cả phạm vi được miễn và phạm vi vẫn phải bảo vệ.

Không sửa test bằng cách bỏ assertion hoặc nới quyền user trước khi biết test đang chứng minh điều gì. Nếu test nhằm kiểm tra user thiếu quyền, hãy giữ user thiếu quyền và cung cấp token hợp lệ; nếu test nhằm kiểm tra CSRF, dùng user đủ quyền để cô lập lớp CSRF.

## 11. Bảng lựa chọn cách sửa theo nguyên nhân

| Nguyên nhân | Cách sửa phù hợp |
| --- | --- |
| Request hợp lệ thiếu token trong MockMvc | Thêm `.with(csrf())`. |
| Client gửi token qua header | Dùng `.with(csrf().asHeader())` trong MockMvc. |
| Test cố ý kiểm tra thiếu token | Giữ request không có token và assert bị từ chối. |
| Test cố ý kiểm tra token sai | Dùng `.with(csrf().useInvalidToken())` trong MockMvc. |
| User thiếu quyền | Cấp đúng role/authority cho ca dương tính; giữ quyền thiếu cho ca authorization âm tính. |
| User chưa xác thực | Thiết lập authentication hợp lệ nếu test không nhằm kiểm tra authentication; nếu có, assert entry point tương ứng. |
| Filter không chạy trong MockMvc | Gắn `springSecurity()` hoặc dùng `@AutoConfigureMockMvc` với filter bật. |
| Endpoint thật sự được miễn CSRF | Cấu hình matcher hẹp và test cả endpoint trong/ngoài ngoại lệ. |
| HTTP integration test | Lấy token qua response thật, giữ cookie/session và gửi lại token. |

## Bài tập thực hành

Một test `POST /orders` nhận `403`, dù mục tiêu là xác nhận user `CUSTOMER` có thể đặt hàng. Hãy thực hiện:

1. Giữ nguyên cấu hình bảo mật và xác nhận endpoint có yêu cầu CSRF.
2. Thêm `@WithMockUser(roles = "CUSTOMER")` và `.with(csrf())` vào request hợp lệ.
3. Viết test thứ hai cùng user nhưng không token; kỳ vọng bị từ chối.
4. Viết test thứ ba với token sai bằng `csrf().useInvalidToken()`; kỳ vọng bị từ chối.
5. Viết test user chỉ có `VIEWER` nhưng token hợp lệ; kỳ vọng bị từ chối do authorization.
6. Xác minh service đặt hàng không được gọi ở các ca âm tính.

**Tự kiểm tra:** Nếu chỉ thêm `csrf.disable()` để test đầu tiên pass, test nào trong ba test âm tính còn chứng minh được CSRF? Không test nào; filter đã bị loại khỏi chính sách đang được kiểm tra.

## Ghi nhớ

Không tắt CSRF chỉ để làm một bài kiểm thử đi qua. Với request hợp lệ, gửi token bằng helper đúng loại ứng dụng; với request âm tính, giữ token thiếu hoặc sai để xác minh nhánh từ chối. Khi token hợp lệ vẫn bị `403`, kiểm tra quyền, authentication, matcher và filter chain. Chỉ miễn hoặc tắt CSRF khi mô hình xác thực của endpoint thực sự yêu cầu, giới hạn phạm vi rõ ràng và có test hồi quy cho cả request được miễn lẫn request vẫn phải được bảo vệ.
