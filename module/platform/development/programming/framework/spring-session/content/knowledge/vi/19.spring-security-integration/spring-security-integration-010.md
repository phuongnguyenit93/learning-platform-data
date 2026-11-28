# Ứng dụng stateless và kiểm chứng không phát sinh phiên ngoài dự kiến

Spring Security có thể xác thực từng request mà không cần duy trì HttpSession giữa các request. Đây là mô hình stateless thường dùng cho REST API xác thực bằng access token trong header Authorization. Mỗi request mang thông tin xác thực của chính nó; server kiểm tra token, tạo Authentication cho request hiện tại và kết thúc request mà không lưu SecurityContext vào session.

Tuy nhiên, đặt SessionCreationPolicy.STATELESS không tự động bảo đảm toàn bộ ứng dụng không tạo session. Controller, filter tùy chỉnh, CSRF token repository, request cache, luồng đăng nhập form, OAuth2 login hoặc thư viện khác vẫn có thể gọi getSession(). Muốn kiểm chứng ứng dụng thật sự không phát sinh session ngoài dự kiến, cần kiểm tra toàn bộ security chain, mã ứng dụng và kho Spring Session.

Bài này giải thích ý nghĩa của stateless trong Spring Security, cách cấu hình API không dùng HttpSession, các thành phần có thể vô tình tạo session, cách phân biệt STATELESS với NEVER, và phương pháp kiểm thử nhiều lớp để chứng minh không có session hoặc cookie session được tạo.

## 1. Stateful và stateless khác nhau ở đâu?

Trong mô hình stateful, server lưu trạng thái đăng nhập giữa các request. Trình duyệt thường gửi cookie session ID; Spring Session dùng ID đó để tìm SecurityContext và các thuộc tính khác trong Redis hoặc JDBC.

Luồng stateful:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Application
    participant S as Spring Session
    participant R as Redis/JDBC
    B->>A: Request đăng nhập
    A->>S: Tạo HttpSession
    S->>R: Lưu session và SecurityContext
    A-->>B: Set-Cookie session ID
    B->>A: Request tiếp theo kèm cookie
    A->>S: Tải session theo ID
    S->>R: Đọc SecurityContext
    R-->>S: Session data
    S-->>A: Authentication context
~~~

Trong mô hình stateless, server không dùng HttpSession để duy trì trạng thái xác thực giữa các request. Client gửi token trên từng request; server xác minh token và dựng Authentication cho request hiện tại.

Luồng stateless với bearer token:

~~~mermaid
sequenceDiagram
    participant C as API Client
    participant A as API
    participant V as Token Validator
    C->>A: Request + Authorization: Bearer token
    A->>V: Kiểm tra chữ ký, issuer, audience, expiry
    V-->>A: Claims hợp lệ
    A->>A: Tạo Authentication cho request
    A-->>C: Response
    Note over A: Không lưu SecurityContext vào HttpSession
~~~

| Tiêu chí | Stateful | Stateless |
|---|---|---|
| Trạng thái xác thực giữa request | Lưu ở session/repository | Được gửi lại trong token hoặc credential mỗi request |
| Định danh phía client | Thường là session cookie | Thường là Authorization bearer token |
| Lưu SecurityContext | Có thể lưu trong HttpSession | Không lưu trong HttpSession |
| Logout | Có thể invalidate session | Thường thu hồi token, chờ token hết hạn hoặc dùng denylist/rotation |
| Chia sẻ trạng thái giữa instance | Cần session repository dùng chung | Mỗi node xác minh token theo cùng trust configuration |
| Khả năng thu hồi tức thời | Xóa session ở repository | Cần cơ chế thu hồi riêng nếu token chưa hết hạn |
| Tác động khi dùng Spring Session | Tạo, đọc, cập nhật và xóa session | Không cần tạo session cho API stateless |

Stateless không có nghĩa server không giữ bất kỳ trạng thái nào. Server vẫn có thể ghi audit, rate limit, refresh token, denylist hoặc dữ liệu nghiệp vụ. Ý nghĩa ở đây là request không phụ thuộc HttpSession để khôi phục SecurityContext.

## 2. SessionCreationPolicy.STATELESS có ý nghĩa gì?

Spring Security cung cấp các chính sách tạo session trong SessionCreationPolicy:

| Chính sách | Hành vi |
|---|---|
| ALWAYS | Luôn tạo HttpSession |
| IF_REQUIRED | Tạo HttpSession khi Spring Security cần |
| NEVER | Không chủ động tạo HttpSession, nhưng có thể dùng HttpSession đã tồn tại |
| STATELESS | Không tạo HttpSession và không dùng HttpSession để lấy SecurityContext |

Điểm phân biệt giữa NEVER và STATELESS rất quan trọng. NEVER có thể dùng một session đã tồn tại, do đó SecurityContext có thể vẫn được lấy từ session cũ. STATELESS không dùng HttpSession để khôi phục SecurityContext.

Ví dụ cấu hình:

~~~java
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
~~~

Với API xác thực bearer token, đây thường là chính sách phù hợp. Tuy nhiên, chính sách này mô tả hành vi của Spring Security. Nó không cấm code ứng dụng hoặc thư viện tùy chỉnh gọi request.getSession() một cách độc lập.

Nếu controller gọi:

~~~java
request.getSession();
~~~

Servlet container hoặc Spring Session có thể tạo session dù security policy là STATELESS. Do đó, cần kiểm tra cả mã ngoài Spring Security.

### STATELESS không đồng nghĩa tắt toàn bộ Spring Session

Nếu ứng dụng có Spring Session filter, filter có thể vẫn được đăng ký cho các request. Chỉ sự hiện diện của filter không nhất thiết tạo session. Session thường chỉ được tạo khi một thành phần yêu cầu getSession(true) hoặc sử dụng API làm phát sinh session.

Một ứng dụng có thể dùng Spring Session cho phần giao diện stateful và dùng một security chain stateless riêng cho /api/**. Trong trường hợp này, cần bảo đảm request API không bị các filter hoặc controller dùng session ngoài ý muốn.

## 3. Cấu hình API stateless bằng Spring Security

Ví dụ dưới đây minh họa một REST API sử dụng OAuth2 Resource Server với JWT bearer token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .securityContext(context -> context
                .securityContextRepository(new NullSecurityContextRepository())
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

Ví dụ này giả định API dùng bearer token trong Authorization header, token không được trình duyệt tự động gửi như cookie và không dựa vào cookie để xác thực. Khi API dùng cookie authentication hoặc credential tự động được trình duyệt đính kèm, phải đánh giá CSRF trước khi tắt bảo vệ CSRF.

Các cấu hình chính:

- securityMatcher giới hạn chain này cho /api/**.
- STATELESS chỉ ra Spring Security không dùng HttpSession cho SecurityContext.
- NullSecurityContextRepository không lưu hoặc tải SecurityContext qua session.
- NullRequestCache không lưu request cần tiếp tục sau đăng nhập.
- oauth2ResourceServer xác thực bearer token cho từng request.
- CSRF được tắt trong ví dụ với giả định API chỉ dùng bearer token không tự động gửi bởi trình duyệt.

Nếu ứng dụng có cả web UI stateful và API stateless, có thể khai báo chain riêng cho mỗi phạm vi. Chain có @Order cao hơn được xét trước; request phải khớp đúng matcher. Cần có chain fallback cho các URL còn lại nếu ứng dụng yêu cầu bảo vệ chúng.

Không sao chép nguyên cấu hình trên nếu API đang dùng cookie, HTTP Basic với browser-managed credentials, form login hoặc cơ chế xác thực khác có thể tự động gửi credential. Hãy xác định cách client mang credential trước khi quyết định CSRF và session policy.

## 4. SecurityContext được tạo và xóa trong mỗi request

Trong mô hình stateless, Spring Security vẫn cần SecurityContext trong lúc xử lý request. Khi bearer token hợp lệ, resource server tạo Authentication và đặt vào SecurityContextHolder để authorization kiểm tra principal và authorities.

Điều đó không yêu cầu lưu SecurityContext vào HttpSession. SecurityContext được dùng trong phạm vi request và được dọn khi request hoàn tất.

Với NullSecurityContextRepository, context không được lưu vào session để request kế tiếp tải lại. Request kế tiếp phải gửi token và được xác thực lại.

Một số cơ chế tùy chỉnh có thể thay đổi hành vi:

- SecurityContextRepository tùy chỉnh có thể lưu context vào HttpSession.
- Filter tự viết có thể gọi getSession() để lưu principal.
- AuthenticationSuccessHandler có thể tạo session hoặc lưu thông tin đăng nhập.
- RequestCache có thể lưu request trước khi chuyển tới trang login.
- Một filter chạy ngoài chain có thể tạo session trước khi Spring Security xử lý request.

Khi kiểm tra stateless, hãy tìm mọi nơi tạo hoặc lưu SecurityContext, không chỉ nhìn SessionCreationPolicy.

### RequestAttributeSecurityContextRepository

Trong một số ứng dụng, context có thể cần tồn tại giữa các dispatch của cùng một request, ví dụ ERROR dispatch. RequestAttributeSecurityContextRepository lưu context ở request attribute thay vì HttpSession. Đây vẫn là trạng thái trong phạm vi request, không phải session giữa nhiều request.

Nếu cần persistence qua nhiều request, phải chọn một cơ chế khác và hiểu rõ nó có tạo session hay không. Đối với bearer token stateless, thông thường mỗi request xác thực token lại.

## 5. RequestCache có thể tạo session

RequestCache lưu request gốc khi người dùng truy cập tài nguyên được bảo vệ nhưng chưa đăng nhập, để chuyển họ trở lại sau khi xác thực.

Trong ứng dụng web stateful, lưu request trong HttpSession là hành vi hữu ích. Trong API stateless, không có trang đăng nhập tương tác để quay lại URL cũ; lưu request có thể không cần thiết.

Dùng NullRequestCache:

~~~java
http.requestCache(cache -> cache
    .requestCache(new NullRequestCache())
);
~~~

Nếu API trả 401, client tự xử lý quy trình lấy token rồi gửi lại request. Server không cần giữ request ban đầu trong HttpSession.

Hãy kiểm tra cả RequestCache tùy chỉnh và các handler chuyển hướng. Một request cache tự viết có thể lưu dữ liệu trong session ngay cả khi SessionCreationPolicy là STATELESS.

## 6. CSRF và session: không tắt bảo vệ một cách máy móc

CSRF phụ thuộc vào cách browser gửi credential. Nếu trình duyệt tự động đính kèm cookie xác thực, một trang bên ngoài có thể kích hoạt request mang cookie đó tới ứng dụng. Khi ấy, CSRF vẫn là mối quan tâm dù ứng dụng đặt SessionCreationPolicy.STATELESS.

Một số trường hợp:

| Cách xác thực | Credential có tự động gửi theo request cross-site không? | Hướng xem xét |
|---|---|---|
| Bearer token trong Authorization header do JavaScript/client chủ động thêm | Thông thường không tự động | Có thể cấu hình CSRF khác cho API thuần bearer, sau khi kiểm tra toàn bộ credential |
| Session cookie | Có, theo cookie policy của trình duyệt | Cần CSRF protection |
| JWT đặt trong cookie | Có, nếu cookie được gửi tự động | Vẫn cần CSRF protection |
| HTTP Basic được browser lưu và tự gửi | Có thể tự động | Cần đánh giá CSRF |
| API key trong header do client tự thêm | Thông thường không tự động | Đánh giá theo cách client lưu và gửi key |

Nếu API chỉ dùng bearer token trong Authorization header, không dùng cookie xác thực và không có cơ chế credential tự động khác, có thể cấu hình CSRF disabled cho chain API. Nhưng nếu token được lưu trong cookie, STATELESS không loại bỏ nguy cơ CSRF.

Nếu cần CSRF token nhưng muốn tránh HttpSession, có thể dùng một repository khác như CookieCsrfTokenRepository theo mô hình double-submit cookie, kết hợp kiểm tra header token và cấu hình cookie phù hợp. Cookie CSRF và cookie xác thực có mục đích khác nhau; cần thiết kế cẩn thận để không tạo lỗ hổng.

CORS cũng không thay thế CSRF. CORS quyết định browser có cho JavaScript đọc response cross-origin hay không; CSRF liên quan tới việc request có thể được gửi kèm credential tự động hay không.

## 7. Các tính năng Spring Security thường cần session

Một API được đánh dấu STATELESS vẫn có thể gặp session nếu bật các tính năng được thiết kế cho luồng stateful.

| Thành phần/tính năng | Vì sao có thể dùng session | Cách xử lý cho API stateless |
|---|---|---|
| Form login | Lưu SecurityContext, request đã lưu và trạng thái đăng nhập | Dùng bearer/resource server cho API hoặc tách chain |
| RequestCache mặc định | Lưu request cần quay lại sau login | Dùng NullRequestCache |
| HttpSessionSecurityContextRepository | Lưu SecurityContext trong HttpSession | Dùng NullSecurityContextRepository cho chain stateless |
| CSRF với HttpSessionCsrfTokenRepository | Lưu CSRF token trong session | Chỉ tắt nếu credential không tự động gửi; nếu cần token, chọn repository phù hợp |
| OAuth2 Login | Authorization request/state thường cần được lưu qua redirect | Dùng chain riêng stateful cho browser login; không ép luồng redirect thành stateless nếu không có cơ chế lưu thay thế |
| SAML2 login | Request/relay state cần được duy trì giữa redirect | Tách khỏi API bearer stateless hoặc dùng cơ chế persistence phù hợp |
| Concurrent session control | Theo dõi và giới hạn session đăng nhập | Dùng token/session revocation strategy riêng cho API stateless |
| Session fixation protection | Thay ID session sau xác thực | Không cần cho bearer-only stateless nếu không có session |
| Saved request / redirect handler | Lưu đích đến sau login | Trả 401 cho API và để client quản lý |
| Custom filter | Có thể gọi getSession() để ghi trạng thái | Rà soát và bỏ phụ thuộc session trong API |
| Controller/service | Có thể gọi getSession() hoặc lưu thuộc tính | Dùng principal/request-scoped data thay vì session |

OAuth2 Login và SAML2 browser flow có những yêu cầu state qua redirect. Không nên đơn giản tắt session policy của chain đang xử lý browser login nếu chưa có cơ chế thay thế an toàn để lưu authorization request và kiểm tra state. Tách URL/API chain thường dễ kiểm soát hơn.

## 8. Tách chain stateful và stateless

Một ứng dụng có thể vừa phục vụ trang web dùng session vừa cung cấp API stateless.

Ví dụ khái niệm:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        )
        .securityContext(c -> c
            .securityContextRepository(new NullSecurityContextRepository())
        )
        .requestCache(c -> c.requestCache(new NullRequestCache()))
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(a -> a
            .requestMatchers("/assets/**", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Ví dụ này chỉ minh họa phân chia trách nhiệm; cần cấu hình CSRF và logout phù hợp cho web chain. Chain đầu tiên khớp /api/**; chain thứ hai xử lý phần còn lại. Nếu không có matcher phù hợp hoặc chain fallback, một số request có thể không được bảo vệ như dự kiến.

Đừng cấu hình STATELESS toàn ứng dụng nếu web UI vẫn cần form login, saved request hoặc OAuth2 login dựa trên session. Hãy phân định theo URL, host hoặc security matcher.

## 9. Những nơi ngoài Spring Security có thể tạo session

Session có thể được tạo bởi bất kỳ thành phần nào gọi API Servlet session. Một số nguồn thường bị bỏ sót:

- Controller gọi request.getSession() để lưu thông báo hoặc trạng thái UI.
- Service nhận HttpServletRequest và gọi getSession() sâu bên trong.
- Filter hoặc HandlerInterceptor tự ghi thuộc tính vào session.
- Framework MVC sử dụng flash attributes hoặc redirect workflow.
- Thư viện CAPTCHA, wizard nhiều bước hoặc upload tạm lưu trạng thái session.
- Template/view engine hoặc custom tag truy cập session.
- Error handler lưu thông tin request để hiển thị trang lỗi.
- CSRF token repository hoặc request cache tùy chỉnh.
- Test helper vô tình tạo session trước khi gửi request.

Cách tìm trong mã nguồn là tìm các lời gọi và kiểu phụ thuộc như:

~~~text
getSession(
getSession(true)
HttpSession
WebSession
setAttribute(
HttpSessionSecurityContextRepository
HttpSessionRequestCache
HttpSessionCsrfTokenRepository
~~~

Không phải mọi setAttribute đều liên quan tới session; cần xem đối tượng được gọi là gì. Hãy truy vết caller và kiểm tra đường đi từ controller tới repository.

Đặc biệt, nếu Spring Session được cấu hình toàn ứng dụng, một session được tạo ở bất kỳ filter hoặc controller nào cũng có thể được lưu vào Redis/JDBC và cookie session được phát. SessionCreationPolicy.STATELESS không chặn code ứng dụng chủ động tạo session.

## 10. Kiểm chứng không tạo session bằng nhiều lớp bằng chứng

Một kiểm thử đáng tin cậy nên kết hợp ít nhất ba loại bằng chứng:

1. **Request-level:** request không có HttpSession sau khi chạy qua filter chain, khi kiểm tra bằng getSession(false).
2. **Response-level:** response không phát Set-Cookie cho SESSION/JSESSIONID hoặc cookie session tùy chỉnh.
3. **Repository-level:** repository không tạo/lưu session mới cho request API stateless và kho dữ liệu không xuất hiện record/key session mới ngoài dự kiến.

Mỗi loại bằng chứng phát hiện một nhóm lỗi khác nhau. Không có Set-Cookie chưa đủ chứng minh không tạo session: session có thể được lưu mà resolver không phát cookie. Request không thấy session cũng chưa đủ nếu một filter khác tạo session sau khi request wrapper được kiểm tra. Repository-level observation giúp xác nhận dữ liệu thực tế.

### Kiểm tra request trong MockMvc

Ví dụ minh họa:

~~~java
@Test
void bearerApiDoesNotCreateHttpSession() throws Exception {
    MvcResult result = mockMvc.perform(
            get("/api/me")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + validToken)
        )
        .andExpect(status().isOk())
        .andReturn();

    assertThat(result.getRequest().getSession(false)).isNull();

    assertThat(result.getResponse().getHeaders(HttpHeaders.SET_COOKIE))
        .noneMatch(value ->
            value.startsWith("SESSION=") ||
            value.startsWith("JSESSIONID=")
        );
}
~~~

Test này cần chạy với filter chain và Spring Session filter thật. Không gắn MockHttpSession vào request khi kiểm tra. Nếu ứng dụng dùng cookie name tùy chỉnh, thêm tên cookie đó vào assertion. Nếu dùng HeaderWebSessionIdResolver, kiểm tra header tương ứng.

Tùy cấu trúc MockMvc và filter wrapper, result.getRequest() có thể là request được wrap hoặc request gốc. Nếu kiểm tra không phản ánh đầy đủ đường đi, bổ sung counting repository hoặc test qua embedded server thật.

### Theo dõi lệnh tạo session ở repository

Có thể bọc SessionRepository bằng decorator đếm số lần createSession() và save(). Trong test, reset bộ đếm trước request API và xác nhận không có create/save mới do request đó.

Ví dụ ý tưởng:

~~~java
AtomicInteger createdSessions = new AtomicInteger();

SessionRepository<?> countingRepository =
        new CountingSessionRepository(delegate, createdSessions);

// Gửi request API qua filter chain thật.
mockMvc.perform(get("/api/me")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + validToken))
    .andExpect(status().isOk());

assertThat(createdSessions.get()).isZero();
~~~

Đây là cấu trúc minh họa; decorator cần triển khai đúng generic SessionRepository của phiên bản đang dùng và được đăng ký làm repository mà SessionRepositoryFilter thực sự sử dụng. Chỉ spy một bean không nằm trong đường xử lý không tạo ra bằng chứng có giá trị.

Nếu dùng Redis hoặc JDBC thật, kiểm tra key/bản ghi trong namespace/schema test riêng trước và sau request. Không dùng wildcard delete trên kho dùng chung để dọn dữ liệu test.

## 11. Kiểm thử cả request thành công, thất bại và đường dẫn phụ

Một ứng dụng có thể không tạo session trong request thành công nhưng lại tạo session trong nhánh lỗi hoặc redirect. Bộ test nên bao phủ nhiều trường hợp:

| Ca kiểm thử | Request | Điều cần xác nhận |
|---|---|---|
| Token hợp lệ | GET API được bảo vệ | Authentication đúng, không tạo session |
| Không có token | GET API được bảo vệ | 401, không lưu saved request vào session |
| Token hết hạn | GET API được bảo vệ | 401, không tạo session mới |
| Token sai chữ ký/audience | GET API được bảo vệ | Từ chối xác thực, không tạo session |
| Không đủ quyền | Request trả 403 | Không lưu trạng thái lỗi vào session |
| Endpoint công khai | GET public API | Không tạo session |
| OPTIONS preflight | CORS preflight | Không tạo session ngoài dự kiến |
| Error dispatch | Handler phát sinh lỗi | Không tạo session để lưu lỗi |
| Logout API | Thu hồi token hoặc xử lý logout | Không tạo HttpSession |
| API sau nhiều request | Gửi token lặp lại | Mỗi request tự xác thực, không phụ thuộc session |

Đối với API stateless, request không có token thường trả 401 thay vì redirect tới form login. Redirect tới trang login có thể kéo theo request cache hoặc session state nếu chain không được cấu hình phù hợp.

Kiểm tra response headers trên cả đường thành công và lỗi. Một session cookie có thể chỉ xuất hiện khi lỗi, redirect hoặc CSRF token được truy cập.

## 12. Kiểm tra cookie và repository khi chạy Spring Session

Nếu ứng dụng có Spring Session Redis/JDBC, hãy kiểm tra theo namespace/schema dành riêng cho test.

Với Redis:

- Dùng namespace test riêng.
- Đếm key trước và sau request.
- Kiểm tra key session được tạo mới, không chỉ tìm cookie.
- Không in session ID hoặc nội dung hash ra report.
- Không dùng KEYS hoặc FLUSHDB trên Redis dùng chung.

Với JDBC:

- Dùng schema hoặc database test riêng.
- Đếm số dòng session trước và sau request.
- Kiểm tra cả bảng attributes.
- Không truy vấn hoặc xuất nội dung ATTRIBUTE_BYTES chứa SecurityContext.
- Xác nhận cleanup không làm nhiễu kết quả test.

Nếu request stateless đi qua Spring Session filter nhưng không gọi getSession(true), thông thường không nên có session mới. Tuy nhiên, request vẫn có thể mang cookie cũ từ một luồng stateful trước đó. Hãy xác định API chain có bỏ qua cookie đó và không dùng nó để khôi phục SecurityContext hay không.

Không nên kết luận stateless chỉ từ việc response không phát Set-Cookie. Một request có thể dùng session đã tồn tại mà không cần phát cookie mới nếu thành phần nào đó vẫn đọc nó. Cần xác nhận cả việc không đọc session và không tạo session.

## 13. Xác thực bearer token không lưu trạng thái đăng nhập vào session

Với OAuth2 Resource Server JWT, mỗi request gửi token trong header:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...
~~~

Resource Server xác minh các yếu tố như chữ ký, issuer, audience, thời điểm hết hạn và các claim cần thiết. Sau đó, Spring Security tạo Authentication cho request.

Không lưu token hoặc SecurityContext vào HttpSession. Token nên được bảo vệ ở client và gửi qua TLS. Không ghi token vào log, URL, trace hoặc metric.

JWT thường tự chứa claims và có thể được xác minh mà không truy vấn session store. Tuy nhiên, nếu ứng dụng cần thu hồi token trước thời hạn, có thể cần denylist, introspection hoặc token version. Những cơ chế đó là trạng thái riêng của token, không đồng nghĩa với việc dùng HttpSession.

Nếu dùng opaque token với introspection, server có thể gọi authorization server để kiểm tra token. Đây vẫn có thể là stateless theo nghĩa không dùng HttpSession; nhưng request phụ thuộc dịch vụ xác thực từ xa và cần timeout/cache phù hợp.

## 14. Logout trong mô hình stateless

Trong mô hình session, logout thường invalidate HttpSession và xóa cookie session. Với bearer token stateless, server không có session chung để invalidate.

Các chiến lược logout có thể gồm:

- Client xóa access token khỏi bộ nhớ hoặc nơi lưu an toàn.
- Dùng access token có thời hạn ngắn.
- Thu hồi refresh token ở authorization server.
- Dùng token introspection hoặc denylist cho trường hợp cần thu hồi access token trước hạn.
- Xoay vòng token và phát hiện refresh token reuse.

Chỉ xóa token ở client không thu hồi bản sao token đã bị đánh cắp. Nếu yêu cầu bảo mật cần thu hồi ngay, phải có cơ chế server-side kiểm tra trạng thái thu hồi. Không tạo HttpSession chỉ để ghi trạng thái logout nếu mục tiêu là API stateless; hãy dùng kho token revocation chuyên biệt.

Endpoint logout của API nên trả kết quả rõ ràng và không phụ thuộc session cookie. Nếu ứng dụng cũng có web UI stateful, logout của web chain có thể invalidate session trong khi logout API xử lý token riêng.

## 15. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| Đặt STATELESS là toàn ứng dụng không thể tạo session | Chỉ định chính sách Spring Security; code khác vẫn có thể gọi getSession() |
| NEVER giống STATELESS | NEVER có thể dùng session đã tồn tại; STATELESS không dùng session để lấy SecurityContext |
| Không có Set-Cookie nghĩa là không có session | Session có thể được tạo/lưu mà cookie không được phát trong response đó |
| Có Spring Session filter nghĩa là mọi request tạo session | Filter có thể wrap request mà không tạo session mới |
| Tắt CSRF vì API stateless luôn an toàn | Credential trong cookie vẫn được browser gửi tự động và có thể chịu CSRF |
| JWT nghĩa là không có bất kỳ trạng thái server-side nào | Denylist, refresh token, audit và rate limit vẫn có thể là state |
| Không dùng HttpSession nghĩa là không cần security context | Authentication vẫn tồn tại trong SecurityContextHolder trong request |
| Test controller không thấy session chứng minh toàn hệ thống stateless | Filter, error dispatch và repository cần được kiểm tra riêng |

## 16. Chẩn đoán khi API stateless vẫn tạo session

Khi phát hiện cookie SESSION/JSESSIONID hoặc dữ liệu session mới sau request API, kiểm tra theo thứ tự:

1. Request có đi vào đúng SecurityFilterChain stateless không?
2. Có chain khác được chọn do matcher hoặc thứ tự @Order sai không?
3. SessionCreationPolicy có thật sự là STATELESS cho chain đó không?
4. SecurityContextRepository có phải HttpSessionSecurityContextRepository hoặc custom repository ghi vào session không?
5. RequestCache có lưu request vào HttpSession không?
6. CSRF token repository có dùng HttpSession không?
7. Có bật formLogin, OAuth2 Login hoặc SAML2 login trong cùng chain không?
8. Custom filter, controller, interceptor hoặc service có gọi getSession() không?
9. Thư viện UI, flash attribute, error handler hoặc workflow có dùng session không?
10. Có một filter chạy trước Spring Security tạo session không?
11. Có request redirect/error dispatch nào tạo session sau response ban đầu không?
12. Spring Session filter có đang lưu session được tạo bởi thành phần ngoài security không?

Tìm nơi gọi getSession(true), getSession() và các wrapper tương đương. Nếu có thể, thêm instrumentation tạm thời quanh SessionRepository.createSession() để ghi stack trace đã loại bỏ dữ liệu nhạy cảm trong môi trường test/staging. Không ghi cookie hoặc session ID thật.

Nếu chỉ có cookie trong request nhưng không có record mới, đó có thể là cookie cũ từ một luồng stateful. Cần xác minh API stateless không sử dụng cookie đó để khôi phục SecurityContext. Nếu API không cần cookie, có thể cấu hình resolver/route phù hợp để tránh chia sẻ cookie giữa web và API.

## 17. Ma trận kiểm thử stateless trước khi phát hành

Một bộ kiểm thử hoàn chỉnh nên kiểm tra:

| Lớp | Bằng chứng | Tiêu chí đạt |
|---|---|---|
| Security configuration | Đúng chain matcher và SessionCreationPolicy | API được xử lý bởi chain STATELESS |
| SecurityContext | NullSecurityContextRepository hoặc cơ chế không dùng HttpSession | Không lưu context giữa request |
| Request cache | NullRequestCache | Không lưu saved request vào session |
| CSRF | Chính sách phù hợp với cách gửi credential | Không tắt CSRF khi browser tự gửi cookie xác thực |
| Request | getSession(false) sau filter chain | Không có session mới |
| Response | Set-Cookie headers | Không phát session cookie ngoài dự kiến |
| Repository | Counting decorator hoặc store test | Không tạo/lưu session mới |
| Error path | 401, 403, redirect/error dispatch | Không phát sinh session trong nhánh lỗi |
| Nhiều instance | Gửi request qua các node khác nhau | Mỗi node xác thực token độc lập, không phụ thuộc session |
| Quan sát production | Metric và log | Không ghi session ID/token; theo dõi createSession bất thường |

Kiểm thử với MockMvc rất hữu ích nhưng cần chạy cùng filter chain thật. Bổ sung integration test với embedded server và repository thật để xác nhận behavior của cookie, filter order và persistence. Nếu dùng Spring Session, nên có test namespace/schema riêng và đếm record/key trước/sau.

## 18. Checklist cấu hình và vận hành

Trước khi tuyên bố một API stateless, xác nhận:

- API dùng credential được client gửi rõ ràng, thường là bearer token trong Authorization header.
- SecurityFilterChain matcher chọn đúng API chain.
- SessionCreationPolicy.STATELESS được áp dụng.
- SecurityContextRepository không lưu/lấy context từ HttpSession.
- RequestCache không lưu saved request vào session.
- CSRF được quyết định dựa trên cách browser gửi credential, không chỉ dựa vào tên stateless.
- Không bật form login/OAuth2 login/SAML flow trong chain API nếu chúng cần session mà chưa có cơ chế lưu thay thế.
- Custom filter, controller, interceptor và service không gọi getSession() ngoài dự kiến.
- API trả 401/403 thay vì redirect tương tác nếu đó là hợp đồng API.
- Không phát SESSION/JSESSIONID hoặc cookie session tùy chỉnh.
- Repository không tạo session record/key mới do request API.
- Test bao gồm success, missing token, invalid token, 401, 403, OPTIONS và error dispatch.
- Nhiều instance dùng cùng trust configuration và không dựa vào sticky session.
- Logout/token revocation có chính sách riêng.
- Log, trace và metric không chứa token, cookie hoặc session ID.

Stateless là một thuộc tính của toàn bộ đường đi request, không chỉ một dòng cấu hình. SessionCreationPolicy.STATELESS và NullSecurityContextRepository giúp Spring Security không dùng HttpSession cho xác thực; NullRequestCache loại bỏ việc lưu request cần quay lại. Nhưng mọi filter, controller, CSRF mechanism và thư viện khác vẫn cần được rà soát. Chỉ khi request, response và repository cùng chứng minh không có session được tạo hoặc sử dụng ngoài dự kiến, ứng dụng mới có thể tin cậy rằng API đang vận hành stateless.

## Tài liệu tham khảo

- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — SecurityContext Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html)

