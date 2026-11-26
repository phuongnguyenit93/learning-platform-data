# Các endpoint được miễn CSRF và giới hạn của ngoại lệ

Một số endpoint cần nhận request từ hệ thống bên ngoài hoặc từ client không dùng cookie phiên trình duyệt. Trong những trường hợp đó, ứng dụng có thể **miễn kiểm tra CSRF cho một phạm vi request được xác định rõ**. Với Spring Security Servlet, cấu hình thường gặp là **csrf.ignoringRequestMatchers(...)**. Tuy nhiên, miễn CSRF chỉ bỏ qua một lớp kiểm tra trong filter chain; endpoint vẫn cần cơ chế xác thực, xác minh nguồn gửi và bảo vệ nghiệp vụ phù hợp.

Bài học thuộc module **Spring Security Testing** hướng dẫn cách chọn endpoint được miễn, giới hạn ngoại lệ theo path/method, phân biệt **ignoringRequestMatchers**, **permitAll()** và **csrf.disable()**, đồng thời kiểm chứng bằng MockMvc. Phần cuối đối chiếu cách tư duy tương tự trong ứng dụng Reactive và các giới hạn cần giữ khi thiết kế webhook/API.

## 1. Khi nào một endpoint có thể được miễn CSRF?

CSRF chủ yếu là rủi ro khi trình duyệt tự động đính kèm thông tin xác thực, chẳng hạn cookie phiên, vào request mà website khác có thể kích hoạt. Token CSRF giúp server xác nhận request thay đổi trạng thái có token hợp lệ gắn với ngữ cảnh người dùng.

Một endpoint có thể cần miễn CSRF khi giao thức tích hợp đã có cơ chế xác minh request riêng và không dựa vào credential tự động gửi bởi trình duyệt. Ví dụ:

- **Webhook server-to-server:** nhà cung cấp gửi sự kiện đến endpoint của ứng dụng; ứng dụng xác minh chữ ký HMAC hoặc chữ ký bất đối xứng trên nội dung request.
- **Callback từ hệ thống tin cậy:** request được xác thực bằng chữ ký, mTLS hoặc một cơ chế credential server-to-server được thiết kế rõ ràng.
- **API dùng Bearer token trong Authorization header:** client chủ động gắn access token vào header và server không dùng cookie phiên trình duyệt để xác thực endpoint đó. Cần đánh giá cách token được lưu và gửi thực tế.

Đây không phải danh sách miễn trừ tự động. Nếu API dùng cookie để xác thực, hoặc browser tự gửi credential khi gọi endpoint, nguy cơ CSRF vẫn có thể tồn tại. Một endpoint có tên /api/**, /webhook/** hay được gọi là “stateless” cũng không tự nhiên an toàn trước CSRF.

### Các trường hợp thường không cần miễn

- Form web thay đổi hồ sơ, địa chỉ hoặc mật khẩu dùng session cookie: giữ CSRF bật.
- Endpoint quản trị hoặc endpoint nội bộ vẫn được truy cập bằng cookie phiên: vẫn cần CSRF.
- Endpoint có **permitAll()** nhưng nhận request từ browser: vẫn có thể cần CSRF.
- Endpoint chỉ đọc dữ liệu bằng HTTP method an toàn: matcher mặc định thường không yêu cầu token; không cần tạo ngoại lệ riêng chỉ để cho GET đi qua.

Đặc biệt, không thiết kế thao tác thay đổi trạng thái bằng GET với lý do “GET không cần CSRF”. GET phải an toàn theo ngữ nghĩa HTTP: không tạo giao dịch, không xóa dữ liệu, không cập nhật trạng thái hoặc kích hoạt tác vụ có tác dụng phụ.

## 2. Ba cấu hình rất khác nhau

| Cấu hình | Phạm vi tác động | Điều gì vẫn được kiểm tra? |
| --- | --- | --- |
| **csrf.ignoringRequestMatchers("/webhooks/**")** | Bỏ qua kiểm tra CSRF cho request khớp matcher trong chain đang cấu hình | Authentication, authorization, các filter khác, chữ ký webhook, validation và nghiệp vụ vẫn hoạt động. |
| **authorizeHttpRequests(...permitAll())** | Cho phép request đi qua quy tắc phân quyền mà không cần user đăng nhập | CSRF vẫn được kiểm tra nếu request khớp matcher CSRF. |
| **csrf.disable()** | Tắt CSRF cho toàn bộ chain đang cấu hình | Các cơ chế khác vẫn có thể chạy, nhưng chain không còn bảo vệ CSRF cho các endpoint của nó. |

Ví dụ, hai cấu hình sau **không tương đương**:

~~~java
// Chỉ miễn CSRF cho đường dẫn webhook.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/**"));
~~~

~~~java
// Tắt CSRF trên toàn bộ SecurityFilterChain này.
http.csrf(csrf -> csrf.disable());
~~~

Chỉ dùng **csrf.disable()** khi đã quyết định rõ toàn bộ chain không cần bảo vệ CSRF theo mô hình xác thực của nó. Không tắt CSRF toàn ứng dụng chỉ để một webhook hoạt động.

Một điểm dễ nhầm khác:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/submit").permitAll());
~~~

Request POST /public/submit vẫn cần token nếu CSRF đang bật và matcher CSRF yêu cầu bảo vệ. **permitAll()** không có tác dụng miễn CSRF.

## 3. Giới hạn ngoại lệ bằng matcher cụ thể

Ví dụ Servlet có webhook dưới path /webhooks/**:

~~~java
@Configuration
@EnableWebSecurity
class IntegrationSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf
                .ignoringRequestMatchers("/webhooks/**"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/webhooks/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Trong ví dụ, mọi request path khớp /webhooks/** được bỏ qua kiểm tra CSRF trong chain này. Các request khác tiếp tục dùng chính sách mặc định. Quy tắc **permitAll()** chỉ cho phép webhook đi qua bước authorization mà không cần đăng nhập; endpoint vẫn phải tự xác minh chữ ký hoặc credential của nhà cung cấp.

### Ngoại lệ theo path và method

Pattern /webhooks/** miễn CSRF cho **mọi method** trên path khớp, không chỉ POST. Nếu yêu cầu chỉ miễn một method cụ thể, hãy dùng một **RequestMatcher** diễn đạt cả method và path:

~~~java
RequestMatcher webhookPost = request ->
    "POST".equals(request.getMethod())
        && request.getServletPath().startsWith("/webhooks/");

http.csrf(csrf -> csrf
    .ignoringRequestMatchers(webhookPost));
~~~

Matcher minh họa trên khớp POST dưới servlet path bắt đầu bằng /webhooks/. Hãy điều chỉnh theo context path, servlet mapping và cách ứng dụng định tuyến. Nếu webhook cần PUT hoặc một đường dẫn gốc cụ thể, hãy khai báo rõ thay vì mở rộng ngoại lệ cho mọi method.

Với path quan trọng, có thể tạo matcher tường minh và kiểm thử các ranh giới:

| Request | Có khớp ngoại lệ /webhooks/**? | CSRF |
| --- | --- | --- |
| POST /webhooks/events | Có | Bỏ qua trong chain đã cấu hình. |
| PUT /webhooks/events/42 | Có | Bỏ qua nếu matcher không giới hạn method. |
| POST /profile/update | Không | Vẫn cần token theo matcher mặc định. |
| POST /webhook/events | Không | Vẫn cần token; path không phải /webhooks/**. |
| POST /webhooks-admin/events | Không | Không khớp path segment /webhooks/. |

Không dựa vào tên gần giống hoặc prefix rộng như /web*. Một matcher quá rộng có thể miễn CSRF ngoài dự định, đặc biệt khi sau này nhóm phát triển thêm endpoint thay đổi dữ liệu dưới cùng prefix.

## 4. Bảo vệ webhook sau khi miễn CSRF

Webhook thường cần nhận request mà không có session cookie hoặc CSRF token của ứng dụng. Nhưng việc miễn CSRF **không xác minh người gửi**. Nếu endpoint chỉ có **permitAll()** và xử lý mọi payload nhận được, bất kỳ client nào biết URL đều có thể giả mạo sự kiện.

Một thiết kế webhook nên kiểm tra ít nhất:

1. **Chữ ký:** xác minh chữ ký trên raw request body bằng secret/public key đã đăng ký với nhà cung cấp.
2. **Toàn vẹn nội dung:** chữ ký phải gắn với đúng byte body nhận được; tránh parse rồi serialize lại trước khi xác minh nếu giao thức yêu cầu raw bytes.
3. **Timestamp và chống replay:** kiểm tra timestamp trong giới hạn cho phép; lưu event ID hoặc nonce để không xử lý lặp.
4. **Nguồn và giao thức:** HTTPS; có thể kiểm tra mTLS hoặc IP allowlist như lớp bổ sung nếu nhà cung cấp có dải IP ổn định.
5. **Idempotency:** cùng một event gửi lại không tạo tác dụng phụ lặp.
6. **Giới hạn tài nguyên:** giới hạn kích thước body, tốc độ, thời gian xử lý và số lần retry.
7. **Quan sát:** ghi event ID, kết quả xác minh và correlation ID; không ghi secret, chữ ký nhạy cảm hoặc dữ liệu cá nhân không cần thiết.

IP allowlist hoặc một header có tên bí mật không nên là cơ chế xác thực duy nhất. Chữ ký phải được xác minh bằng thuật toán và cách canonicalization đúng theo tài liệu giao thức của nhà cung cấp.

Ví dụ controller gọi một thành phần xác minh chữ ký:

~~~java
@RestController
class WebhookController {

    private final WebhookVerifier verifier;
    private final WebhookService webhookService;

    WebhookController(
            WebhookVerifier verifier,
            WebhookService webhookService) {
        this.verifier = verifier;
        this.webhookService = webhookService;
    }

    @PostMapping(
        path = "/webhooks/events",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    ResponseEntity<Void> receive(
            @RequestHeader("X-Webhook-Signature") String signature,
            @RequestBody byte[] rawBody) {

        if (!verifier.isValid(rawBody, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        webhookService.process(rawBody);
        return ResponseEntity.accepted().build();
    }
}
~~~

Đây là ví dụ về ranh giới trách nhiệm; cách đọc raw body, parse payload, xác minh HMAC, timestamp và replay phải theo giao thức webhook thật. Không tự phát minh định dạng chữ ký hoặc thuật toán hash. Endpoint được miễn CSRF vẫn phải từ chối chữ ký không hợp lệ và không gọi service nghiệp vụ.

## 5. Kiểm thử ngoại lệ với MockMvc

Giả sử ứng dụng có:

- POST /webhooks/events: miễn CSRF, public ở bước authorization, controller trả 202 Accepted nếu chữ ký hợp lệ.
- POST /profile/update: yêu cầu user đăng nhập và CSRF.
- POST /public/submit: public bằng **permitAll()** nhưng **không** được miễn CSRF.

Test cần có **spring-security-test** và MockMvc được cấu hình để chạy filter chain thật:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CsrfExemptionTest {

    @Autowired
    MockMvc mockMvc;
}
~~~

### Webhook đúng phạm vi ngoại lệ: không cần token

~~~java
@Test
void webhookWithoutCsrfToken_reachesSignatureVerification() throws Exception {
    mockMvc.perform(post("/webhooks/events")
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Webhook-Signature", "valid-test-signature")
            .content("{\"eventId\":\"evt-100\"}"))
        .andExpect(status().isAccepted());
}
~~~

Test giả định verifier được cấu hình để chấp nhận chữ ký test. Nó chứng minh request không bị CsrfFilter chặn khi thiếu token và tiếp tục tới xử lý xác minh. Với hệ thống thực, nên mock verifier hoặc dùng chữ ký test hợp lệ theo implementation.

### Webhook chữ ký sai vẫn bị từ chối

~~~java
@Test
void webhookWithInvalidSignature_isRejected() throws Exception {
    mockMvc.perform(post("/webhooks/events")
            .contentType(MediaType.APPLICATION_JSON)
            .header("X-Webhook-Signature", "invalid-signature")
            .content("{\"eventId\":\"evt-101\"}"))
        .andExpect(status().isUnauthorized());
}
~~~

Kết quả 401 ở đây đến từ logic xác minh webhook minh họa, không phải CSRF. Hãy xác minh service nghiệp vụ không được gọi khi chữ ký sai.

### Request ngoài phạm vi ngoại lệ vẫn cần token

~~~java
@Test
@WithMockUser
void profileUpdateWithoutToken_isForbidden() throws Exception {
    mockMvc.perform(post("/profile/update"))
        .andExpect(status().isForbidden());
}

@Test
@WithMockUser
void profileUpdateWithToken_isAllowedByCsrf() throws Exception {
    mockMvc.perform(post("/profile/update").with(csrf()))
        .andExpect(status().isNoContent());
}
~~~

Hai ca đối chứng cho thấy ngoại lệ webhook không làm thay đổi CSRF trên các URL khác.

### permitAll không miễn CSRF

~~~java
@Test
void publicPostWithoutToken_isForbidden() throws Exception {
    mockMvc.perform(post("/public/submit"))
        .andExpect(status().isForbidden());
}

@Test
void publicPostWithToken_passesCsrf() throws Exception {
    mockMvc.perform(post("/public/submit").with(csrf()))
        .andExpect(status().isAccepted());
}
~~~

Endpoint public không yêu cầu đăng nhập nhưng vẫn chịu CSRF. **permitAll()** chỉ bỏ yêu cầu authentication/authorization cho request đó; nó không thay đổi matcher CSRF.

### Path gần giống nhưng không được miễn

Nếu có handler cho POST /webhook/events (số ít), test request này không token để xác nhận matcher /webhooks/** không vô tình bao phủ:

~~~java
@Test
void singularWebhookPath_isNotExempt() throws Exception {
    mockMvc.perform(post("/webhook/events"))
        .andExpect(status().isForbidden());
}
~~~

Các test trên giả định handler và cấu hình tương ứng tồn tại. Khi endpoint không có mapping, response 404/405 không thể chứng minh matcher CSRF đã hoạt động như mong đợi; cần tạo handler test hoặc kiểm tra request được chặn trước MVC bằng một setup phù hợp.

## 6. Ma trận kiểm thử cho ngoại lệ

| Request | Có token? | Kết quả mong đợi | Điều được chứng minh |
| --- | --- | --- | --- |
| POST /webhooks/events, chữ ký hợp lệ | Không | 202 | Request khớp ngoại lệ CSRF và vượt xác minh chữ ký. |
| POST /webhooks/events, chữ ký sai | Không | 401 theo ví dụ | Ngoại lệ CSRF không bỏ qua xác minh webhook. |
| POST /profile/update | Không | 403 | Endpoint ngoài ngoại lệ vẫn được bảo vệ. |
| POST /profile/update | Hợp lệ | 204 theo ví dụ | Token hợp lệ được chấp nhận. |
| POST /public/submit với permitAll() | Không | 403 | Public access không đồng nghĩa miễn CSRF. |
| POST /public/submit với permitAll() | Hợp lệ | 202 theo ví dụ | Request qua CSRF và authorization public. |
| POST /webhook/events | Không | 403 nếu handler tồn tại và chain yêu cầu CSRF | Matcher ngoại lệ có ranh giới path chính xác. |

Khi viết test, nên kiểm tra cả side effect:

- Webhook chữ ký sai: verifier từ chối, webhookService không được gọi.
- Request profile thiếu token: controller/service cập nhật hồ sơ không được gọi.
- Request hợp lệ: service được gọi đúng một lần với dữ liệu mong đợi.

Không chỉ assert status, vì response handler có thể thay đổi mã trạng thái và body.

## 7. Nhiều SecurityFilterChain: ngoại lệ chỉ có hiệu lực trong chain tương ứng

Ứng dụng có thể khai báo nhiều SecurityFilterChain, ví dụ API và web dùng chính sách khác nhau:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .csrf(csrf -> csrf.disable())
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .csrf(Customizer.withDefaults())
        .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Ví dụ chỉ nhằm minh họa chain API khớp /api/** được xử lý trước và chain web phía sau dùng CSRF mặc định. Chain đầu tiên có matcher phù hợp được chọn; các cấu hình của chain sau không tự cộng thêm vào chain đã chọn.

Điều đó có nghĩa:

- csrf.disable() trong API chain không tắt CSRF ở web chain.
- ignoringRequestMatchers(...) trong một chain không tạo ngoại lệ cho chain khác.
- Nếu matcher của chain đầu tiên quá rộng, request có thể vào nhầm chain và nhận chính sách ngoài dự kiến.
- Cần test một URL đại diện cho mỗi chain, cả request có và không có token nếu chain đó bật CSRF.

Không suy ra chính sách bảo mật chỉ từ prefix URL hoặc tên bean; hãy kiểm tra securityMatcher, @Order và request thực tế.

## 8. Giới hạn và rủi ro của ngoại lệ

| Rủi ro | Vì sao nguy hiểm | Cách giới hạn |
| --- | --- | --- |
| Matcher quá rộng | Miễn CSRF cho nhiều endpoint thay đổi trạng thái ngoài ý định | Dùng path cụ thể, giới hạn method và test path gần giống. |
| Chỉ dùng permitAll() | Endpoint công khai vẫn có thể nhận request CSRF từ browser | Giữ CSRF nếu dùng cookie/session; xác định rõ mô hình credential. |
| Tắt CSRF cả chain | Các trang web/session khác trong chain mất lớp bảo vệ | Chỉ tắt cho chain có thiết kế xác thực phù hợp, phạm vi URL hẹp. |
| Webhook không xác minh chữ ký | Kẻ khác có thể giả mạo sự kiện | Verify signature, timestamp, replay và idempotency. |
| Dùng IP allowlist làm bảo vệ duy nhất | IP có thể thay đổi, bị chia sẻ hoặc cấu hình sai | Dùng chữ ký/credential mạnh; IP chỉ là lớp bổ sung. |
| Đặt tác dụng phụ trước khi xác minh | Payload giả mạo có thể tạo dữ liệu trước khi bị từ chối | Xác minh đầy đủ trước khi gọi service xử lý. |
| Bỏ qua test path ranh giới | Ngoại lệ có thể vô tình bao phủ URL mới | Test cả path nằm trong và ngoài matcher. |
| Tin rằng API stateless luôn miễn CSRF | Token có thể được lưu trong cookie hoặc browser tự gửi credential | Đánh giá credential transport thực tế. |

Một webhook không cần CSRF vẫn cần bảo vệ chống giả mạo, replay và lạm dụng tài nguyên. Miễn CSRF không phải là “đánh dấu endpoint đáng tin cậy”; nó chỉ nói rằng một cơ chế cụ thể không được áp dụng cho request khớp matcher.

## 9. Đối chiếu với WebFlux/Reactive

Trong ứng dụng Reactive, cấu hình bảo mật dùng SecurityWebFilterChain và ServerHttpSecurity; không dùng HttpSecurity hoặc ignoringRequestMatchers(...) của Servlet. CSRF Reactive sử dụng ServerWebExchangeMatcher để xác định request nào cần bảo vệ.

Khi muốn miễn một webhook, thiết kế matcher Reactive sao cho:

- Method an toàn tiếp tục theo chính sách mặc định của CSRF.
- Request webhook được loại khỏi tập request cần CSRF.
- Các request thay đổi trạng thái còn lại vẫn được yêu cầu token.

Matcher cần được kết hợp với quy tắc mặc định hoặc tự bảo toàn việc loại trừ các method an toàn. Không viết matcher “mọi request trừ webhook” mà vô tình khiến GET cũng phải có token.

Test Reactive dùng WebTestClient đã gắn Spring Security:

~~~java
webTestClient
    .post()
    .uri("/webhooks/events")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(payload)
    .exchange()
    .expectStatus().isAccepted();
~~~

Với endpoint đã miễn CSRF, request không cần gọi mutator csrf(). Để kiểm tra endpoint Reactive còn được bảo vệ, dùng mutateWith(csrf()) cho ca hợp lệ và request không có token cho ca âm tính. Cấu hình matcher và hành vi thực tế cần được kiểm chứng trong SecurityWebFilterChain của ứng dụng.

## 10. Checklist trước khi thêm ngoại lệ CSRF

- [ ] Xác định endpoint có thực sự nhận credential tự động từ browser hay không.
- [ ] Xác định giao thức thay thế để xác thực request (chữ ký, mTLS, Bearer token...).
- [ ] Giới hạn matcher bằng path và method cần thiết.
- [ ] Không nhầm permitAll() với miễn CSRF.
- [ ] Không tắt CSRF toàn chain chỉ để xử lý một webhook.
- [ ] Xác minh webhook signature trước mọi tác dụng phụ.
- [ ] Có test request trong phạm vi ngoại lệ không token.
- [ ] Có test request ngoài phạm vi ngoại lệ thiếu token bị từ chối.
- [ ] Có test chữ ký sai và xác minh service không chạy.
- [ ] Kiểm tra các SecurityFilterChain và thứ tự @Order.
- [ ] Với WebFlux, dùng matcher Reactive và WebTestClient API phù hợp.

## Bài tập thực hành

Một ứng dụng nhận callback tại POST /integrations/payments/events. Nhóm phát triển muốn miễn CSRF cho callback vì nhà cung cấp ký HMAC trên raw body. Các trang /account/** dùng session cookie và vẫn cần CSRF.

Hãy đề xuất cấu hình và test để chứng minh:

1. Callback chữ ký hợp lệ không cần CSRF token và được xử lý.
2. Callback chữ ký sai không được gọi service.
3. POST /account/email không token bị từ chối.
4. POST /account/email token hợp lệ đi tiếp nếu user đủ quyền.
5. POST /integrations/payments-admin/events không vô tình được miễn nếu matcher chỉ dành cho path callback đã chọn.

**Tự kiểm tra:** Nếu thêm permitAll() cho callback mà quên ignoringRequestMatchers(...), callback còn cần CSRF không? Có. Nếu miễn CSRF nhưng không xác minh HMAC, request giả mạo có thể kích hoạt xử lý sự kiện trái phép; vì vậy ngoại lệ phải đi cùng cơ chế xác minh riêng.

## Ghi nhớ

Chỉ miễn CSRF cho request có phạm vi rõ ràng và có mô hình xác thực thay thế phù hợp. **ignoringRequestMatchers(...)** bỏ qua CSRF cho matcher trong một chain; **permitAll()** chỉ tác động phân quyền; **csrf.disable()** tắt CSRF trên toàn chain. Hãy giới hạn path/method, kiểm thử ranh giới ngoại lệ và xác minh webhook bằng chữ ký hoặc credential phù hợp. Các filter, authorization và nghiệp vụ khác vẫn phải được kiểm tra.
