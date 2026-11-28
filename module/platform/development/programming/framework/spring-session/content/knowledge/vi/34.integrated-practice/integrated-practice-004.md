# Đăng nhập bằng Spring Security và kiểm tra đổi định danh phiên

Khi người dùng đăng nhập, ứng dụng chuyển từ một request chưa xác thực sang một phiên đã có danh tính và quyền. Nếu ứng dụng tiếp tục dùng nguyên session ID mà client đã biết trước khi đăng nhập, kẻ tấn công có thể lợi dụng session fixation: họ chuẩn bị hoặc biết trước một session ID, khiến nạn nhân đăng nhập bằng ID đó, rồi dùng lại ID để truy cập phiên đã xác thực.

Spring Security có cơ chế bảo vệ session fixation khi xác thực thành công. Trong ứng dụng Servlet dùng Spring Session, cơ chế này phải phối hợp với Servlet API, SessionRepositoryFilter, repository lưu session và resolver phát hành session ID qua cookie hoặc header. Bài thực hành này xây dựng một luồng đăng nhập có session trước xác thực, xác nhận session ID được đổi sau đăng nhập, kiểm tra cookie mới, chứng minh ID cũ không còn xác thực và xác minh dữ liệu session được giữ hoặc loại bỏ đúng theo chiến lược đã chọn.

## 1. Session fixation là gì?

Session fixation xảy ra khi kẻ tấn công biết hoặc kiểm soát session ID trước khi nạn nhân đăng nhập, sau đó lợi dụng việc ứng dụng giữ nguyên ID sau khi xác thực.

Một kịch bản:

1. Ứng dụng cấp session ID OLD-ID cho một request chưa đăng nhập.
2. Kẻ tấn công biết hoặc ép nạn nhân sử dụng ID này.
3. Nạn nhân đăng nhập thành công nhưng ứng dụng vẫn giữ OLD-ID.
4. Kẻ tấn công gửi OLD-ID và được khôi phục session đã xác thực.

Biện pháp cốt lõi là đổi định danh session tại thời điểm chuyển sang trạng thái xác thực. Session ID mới phải được phát hành cho client hợp lệ; ID cũ không còn được chấp nhận như phiên đã đăng nhập.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant S as Spring Security
    participant F as SessionRepositoryFilter
    participant R as Shared Session Repository

    B->>F: Request trước đăng nhập
    F->>R: Tạo/lưu session OLD-ID
    R-->>F: Session OLD-ID
    F-->>B: Set-Cookie OLD-ID
    B->>S: POST /login + OLD-ID
    S->>S: Xác thực credentials
    S->>F: Session fixation protection
    F->>R: Đổi ID và lưu session mới
    R-->>F: Session NEW-ID
    F-->>B: Set-Cookie NEW-ID
    B->>F: Request bảo vệ + NEW-ID
    F->>R: Tải NEW-ID
    R-->>F: Session đã xác thực
    F-->>B: Cho phép truy cập
    Note over B,R: OLD-ID không còn khôi phục được phiên đã xác thực
~~~

Session fixation khác session hijacking. Đổi ID ngăn kẻ tấn công tiếp tục dùng một ID được biết trước từ trước khi đăng nhập. Nếu kẻ tấn công đánh cắp cookie mới sau đăng nhập, họ vẫn có thể chiếm phiên. Vì vậy, vẫn cần TLS, cookie an toàn, bảo vệ XSS, CSRF, kiểm soát thiết bị và thu hồi phiên.

## 2. Vai trò của Spring Security và Spring Session

Trong ứng dụng Servlet, Spring Security quản lý quá trình xác thực và áp dụng SessionAuthenticationStrategy sau khi authentication thành công. Spring Session thay nơi lưu HttpSession mặc định của Servlet container bằng một repository như Redis hoặc JDBC.

Các thành phần liên quan:

| Thành phần | Vai trò |
| --- | --- |
| Authentication | Danh tính và authorities sau khi xác thực |
| SecurityContext | Chứa Authentication hiện tại |
| SessionAuthenticationStrategy | Áp dụng chính sách session sau xác thực |
| Session fixation strategy | Đổi ID hoặc tạo session mới theo chính sách |
| SessionRepositoryFilter | Bọc request/response để dùng session do Spring Session quản lý |
| SessionRepository | Tạo, lưu, tìm và xóa session trong Redis/JDBC |
| HttpSessionIdResolver | Đọc và phát hành session ID qua cookie hoặc header |

Luồng thành công thường là: Spring Security xác thực credentials, gọi chiến lược session, lưu SecurityContext và hoàn tất response. Spring Session đảm nhận persistence và đồng bộ định danh mới với kho session.

Điều quan trọng là ứng dụng phải dùng một session policy có trạng thái. Nếu cấu hình SessionCreationPolicy.STATELESS và không sử dụng HttpSession cho authentication, không có session ID để xoay theo luồng này. Không dùng cấu hình stateless cho bài test có mục tiêu xác nhận session fixation protection.

## 3. Các chiến lược bảo vệ session fixation

Spring Security cung cấp các cách xử lý khác nhau. Chọn chiến lược theo Servlet container, phiên bản Spring Security và yêu cầu bảo toàn session attributes.

| Chiến lược | Hành vi | Khi cân nhắc |
| --- | --- | --- |
| changeSessionId | Đổi ID của session hiện tại bằng Servlet API | Lựa chọn phổ biến trên Servlet 3.1+; giữ session và attributes |
| migrateSession | Tạo session mới và sao chép attributes từ session cũ | Khi cần cơ chế migrate session thay cho đổi ID trực tiếp |
| newSession | Tạo session mới, không sao chép các application attributes cũ; các thuộc tính cần cho Spring Security được xử lý theo contract của phiên bản | Khi muốn loại bỏ dữ liệu pre-authentication |
| none | Không thực hiện bảo vệ session fixation | Không phù hợp với ứng dụng session-based thông thường |

Trên Servlet 3.1+, Spring Security thường dùng changeSessionId làm chiến lược mặc định. Tuy nhiên, không nên dựa vào mặc định không được kiểm tra: cấu hình, container và phiên bản có thể khác nhau. Nên khai báo rõ chiến lược nếu hành vi này là yêu cầu bảo mật cần kiểm thử.

### 3.1. changeSessionId

Chiến lược này gọi HttpServletRequest.changeSessionId() để thay ID của session hiện tại. Các attributes trong session tiếp tục tồn tại dưới ID mới. Với Spring Session, request đã được SessionRepositoryFilter bọc nên thao tác đổi ID được chuyển tới session abstraction và repository tương ứng.

Đây là lựa chọn phù hợp khi muốn:

- Xoay ID sau khi xác thực.
- Giữ các attributes hợp lệ như locale hoặc trạng thái giỏ hàng.
- Tránh sao chép toàn bộ session object sang một session khác.

### 3.2. migrateSession

Chiến lược này tạo session mới và sao chép các attributes từ session trước đó. Nó cũng thay đổi định danh session. Vì attributes được chuyển, ứng dụng cần xem xét dữ liệu nào được tạo trước xác thực và có còn đáng tin sau đăng nhập hay không.

Không nên lưu dữ liệu nhạy cảm hoặc quyền hạn do client kiểm soát vào session pre-authentication rồi tin cậy vô điều kiện sau khi migrate.

### 3.3. newSession

Chiến lược này tạo session mới và không sao chép các application attributes cũ. Các attributes nội bộ cần cho Spring Security được xử lý theo quy tắc của phiên bản Spring Security. Dùng chiến lược này khi muốn loại bỏ trạng thái pre-authentication không cần thiết, nhưng phải kiểm tra tác động tới trải nghiệm như giỏ hàng, ngôn ngữ hoặc workflow đang dở.

### 3.4. none

Không đổi session ID sau xác thực. Chỉ cân nhắc khi một kiến trúc đặc biệt đã có biện pháp chống fixation tương đương và đã được đánh giá. Với ứng dụng dùng cookie session thông thường, tắt bảo vệ này tạo ra rủi ro không cần thiết.

## 4. Cấu hình Spring Security có session fixation protection

Ví dụ cấu hình Servlet với Spring Security hiện đại:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                "/login",
                                "/test/pre-auth")
                        .permitAll()
                        .anyRequest()
                        .authenticated())
                .formLogin(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation ->
                                fixation.changeSessionId()))
                .build();
    }
}
~~~

Đây là ví dụ cấu hình theo Spring Security 6.x. Với phiên bản cũ, DSL có thể khác. Hãy xác nhận API đúng với dependency management của ứng dụng.

Điểm cần chú ý:

- Ứng dụng dùng session-based authentication.
- Session fixation protection được khai báo rõ.
- Các endpoint kiểm thử tạo session trước login được cho phép truy cập.
- Các endpoint nghiệp vụ còn lại yêu cầu authentication.
- Không cấu hình SessionCreationPolicy.STATELESS cho luồng này.

Spring Boot có thể tự cấu hình filter chain nếu ứng dụng không khai báo bean riêng. Khi đã tự khai báo SecurityFilterChain, phải đảm bảo các rule authorization và form login phù hợp với ứng dụng.

## 5. Spring Session tham gia vào việc đổi ID như thế nào?

SessionRepositoryFilter thay HttpServletRequest/HttpSession bằng wrapper kết nối với Spring Session. Khi Spring Security gọi changeSessionId, wrapper thực hiện thay đổi trên session do repository quản lý. Khi request hoàn tất, Spring Session lưu trạng thái và HttpSessionIdResolver phát định danh mới theo cơ chế cấu hình.

Với cookie-based resolver:

1. Browser gửi cookie chứa session ID cũ.
2. Resolver đọc ID và repository khôi phục session.
3. Spring Security xác thực người dùng.
4. Session fixation strategy đổi ID.
5. Repository lưu session dưới ID mới và xử lý ID cũ theo semantics của implementation.
6. Resolver phát cookie mới trong response.
7. Request sau dùng cookie mới để khôi phục Authentication.

Với header-based resolver, ID mới được phát qua header thay vì cookie. Test phải kiểm tra đúng cơ chế resolver đang dùng; không được luôn giả định có Set-Cookie.

Không hard-code cấu trúc key nội bộ Redis hoặc tên bảng JDBC để kiểm tra rotation. Dùng SessionRepository hoặc HTTP behavior để xác nhận kết quả. Storage implementation có thể thay đổi giữa các phiên bản.

## 6. Cookie và session ID resolver

Spring Session Servlet thường dùng CookieHttpSessionIdResolver hoặc một resolver tùy chỉnh. Cookie name mặc định có thể khác cấu hình ứng dụng; một số ứng dụng đổi tên thành SESSION, tên riêng theo domain hoặc dùng header.

Khi kiểm thử cookie, cần biết:

- Cookie name thực tế.
- Path và Domain.
- HttpOnly.
- Secure.
- SameSite.
- Thời hạn cookie nếu được đặt.
- Resolver có phát cookie mới sau khi ID thay đổi không.

Không ghi giá trị session ID vào log. Cookie session ID là bearer credential: ai có được cookie có thể thử sử dụng phiên đó.

Ví dụ cấu hình resolver có cookie name riêng:

~~~java
@Bean
HttpSessionIdResolver httpSessionIdResolver() {
    CookieHttpSessionIdResolver resolver =
            new CookieHttpSessionIdResolver();

    DefaultCookieSerializer serializer =
            new DefaultCookieSerializer();
    serializer.setCookieName("APPSESSION");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");

    resolver.setCookieSerializer(serializer);
    return resolver;
}
~~~

Đây là ví dụ cho ứng dụng Servlet dùng Spring Session. Trong test chạy HTTP thường, cookie Secure sẽ chỉ được browser gửi qua HTTPS; MockMvc không thực hiện đầy đủ quy tắc browser. Nếu cần kiểm thử hành vi Secure cookie thực tế, dùng HTTPS embedded container hoặc test client được cấu hình phù hợp. Không tắt Secure trong production chỉ để làm test HTTP đơn giản hơn.

## 7. Tạo session trước khi đăng nhập để kiểm thử rotation

Một test chỉ gửi login request mà chưa có session trước xác thực chưa chứng minh được session ID đã được xoay. Ứng dụng có thể tạo một session mới sau login và test chỉ thấy một cookie mới mà không biết ID cũ có được thay hay không.

Hãy chủ động tạo pre-authentication session:

~~~java
@RestController
class SessionTestController {

    @GetMapping("/test/pre-auth")
    Map<String, Object> createPreAuthenticationSession(
            HttpServletRequest request) {
        HttpSession session = request.getSession(true);
        session.setAttribute(
                "preAuthMarker",
                "created-before-authentication");

        return Map.of("prepared", true);
    }

    @GetMapping("/test/private")
    Map<String, Object> privateResource(
            Authentication authentication,
            HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        Object marker = session == null
                ? null
                : session.getAttribute("preAuthMarker");

        return Map.of(
                "principal", authentication.getName(),
                "preAuthMarker", marker == null ? "" : marker);
    }
}
~~~

Controller này chỉ dành cho test profile hoặc test source. Không để endpoint tạo session tùy ý và endpoint trả principal/attributes thử nghiệm mở ra trong production.

Sau request /test/pre-auth, response phải phát session ID. Test lưu ID đó thành oldId. Request login tiếp theo phải gửi lại cookie chứa oldId; nếu không gửi, test không chứng minh được việc đổi ID của session đã tồn tại.

## 8. Kiểm thử tích hợp bằng MockMvc

MockMvc phù hợp để kiểm tra Spring MVC, Spring Security filter chain và Spring Session filter trong application context. Cần bảo đảm test khởi tạo cấu hình thật và không thay repository bằng mock.

Ví dụ khung test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class SessionFixationIntegrationTests {

    private static final String SESSION_COOKIE = "APPSESSION";

    @Autowired
    MockMvc mockMvc;

    @Autowired
    SessionRepository<? extends Session> sessionRepository;

    @Test
    void rotatesSessionIdAfterSuccessfulLogin() throws Exception {
        MvcResult preAuth = mockMvc.perform(
                        get("/test/pre-auth"))
                .andExpect(status().isOk())
                .andReturn();

        Cookie oldCookie =
                preAuth.getResponse().getCookie(SESSION_COOKIE);
        assertThat(oldCookie).isNotNull();
        String oldId = oldCookie.getValue();
        assertThat(oldId).isNotBlank();

        MvcResult login = mockMvc.perform(
                        post("/login")
                                .cookie(oldCookie)
                                .param("username", "alice")
                                .param("password", "test-password")
                                .with(csrf()))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie newCookie =
                login.getResponse().getCookie(SESSION_COOKIE);
        assertThat(newCookie).isNotNull();
        String newId = newCookie.getValue();
        assertThat(newId).isNotBlank();
        assertThat(newId).isNotEqualTo(oldId);

        mockMvc.perform(
                        get("/test/private")
                                .cookie(newCookie))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.principal").value("alice"))
                .andExpect(jsonPath("$.preAuthMarker")
                        .value("created-before-authentication"));

        assertThat(sessionRepository.findById(oldId)).isNull();
        assertThat(sessionRepository.findById(newId)).isNotNull();

        mockMvc.perform(
                        get("/test/private")
                                .cookie(oldCookie))
                .andExpect(status().is3xxRedirection());
    }
}
~~~

Đây là ví dụ minh họa cho cấu hình cookie-based có tên APPSESSION và form login. Test cần có user fixture alice, mật khẩu fixture và endpoint test controller như phần trước. Các static import của MockMvc, Spring Security Test, AssertJ và JSONPath được lược bớt.

Nếu ứng dụng dùng cookie name khác, thay SESSION_COOKIE bằng tên resolver thực tế. Nếu dùng header resolver, lấy ID từ header response và gửi lại header request thay vì đọc Cookie.

Assertion quan trọng:

- Pre-authentication request thực sự tạo session.
- Login request gửi lại cookie cũ.
- Login thành công.
- Response phát ID mới khác ID cũ.
- ID mới khôi phục đúng principal.
- Attributes được giữ lại theo chiến lược changeSessionId.
- Repository không còn session dưới ID cũ.
- Cookie cũ không truy cập được resource bảo vệ.

## 9. Vì sao cần kiểm tra cả cookie và repository?

Chỉ kiểm tra Set-Cookie có giá trị khác không đủ. Một ứng dụng có thể phát cookie mới nhưng lưu session sai, khiến request tiếp theo không khôi phục được Authentication.

Chỉ kiểm tra repository có session mới cũng chưa đủ. Resolver có thể vẫn phát cookie cũ hoặc không phát cookie mới, khiến browser tiếp tục gửi định danh không hợp lệ.

Kiểm tra hai mặt:

| HTTP/client | Repository |
| --- | --- |
| Response login có cookie/header mới | Session mới được lưu |
| ID mới khác ID trước login | Session mới chứa SecurityContext |
| Request với ID mới được xác thực | findById(newId) tìm thấy session |
| Request với ID cũ không được xác thực | findById(oldId) không còn session |
| Logout làm cookie hết hạn | Session mới bị invalidate/delete |

Nếu repository có index principal, có thể kiểm tra session mới xuất hiện dưới principal đúng sau khi authentication được persist. Tuy nhiên, principal index là dữ liệu phụ trợ; nó không thay thế kiểm tra SecurityContext và request bảo vệ.

## 10. Kiểm tra bảo toàn attributes theo chiến lược

Kết quả về attributes phụ thuộc strategy:

| Strategy | preAuthMarker mong đợi |
| --- | --- |
| changeSessionId | Được giữ vì session hiện tại đổi ID |
| migrateSession | Được sao chép sang session mới |
| newSession | Không được giữ như application attribute thông thường |
| none | Có thể vẫn còn trên session cũ; ID không được bảo vệ |

Test không nên luôn assert attributes được giữ mà không biết strategy đang chọn. Nếu yêu cầu bảo toàn giỏ hàng hoặc locale, chọn changeSessionId/migrateSession phù hợp và kiểm tra. Nếu muốn bỏ toàn bộ trạng thái pre-authentication, test theo newSession và xác nhận ứng dụng tái tạo các dữ liệu cần thiết.

Đặc biệt, không coi marker hoặc dữ liệu do client kiểm soát trước đăng nhập là quyền hạn. Sau authentication, quyền phải lấy từ nguồn tin cậy và được Spring Security kiểm tra.

## 11. Kiểm tra ID cũ không còn được dùng

Sau khi ID đã đổi:

- Repository nên không còn trả session theo ID cũ.
- Request bảo vệ gửi ID cũ phải bị coi là chưa xác thực.
- ID cũ không được tự động ánh xạ tới session mới.
- Không có node nào trong cluster tiếp tục chấp nhận ID cũ.

Một số implementation có thể lưu metadata phụ hoặc shadow key cho event/expiration. Vì vậy, không truy vấn key nội bộ bằng tên hard-code để kết luận session cũ còn tồn tại. Dùng API repository và HTTP request behavior làm bằng chứng.

Nếu request với cookie cũ vẫn được xác thực, kiểm tra:

- Test có vô tình dùng lại cookie jar đã cập nhật sang ID mới không.
- SessionRepositoryFilter có thực sự được đăng ký trước Spring Security filter chain không.
- Có một local session store khác đang được dùng không.
- Custom SessionAuthenticationStrategy có được gọi không.
- Login filter tùy chỉnh có bỏ qua session fixation protection không.
- Có cache hoặc reverse proxy đang gắn nhầm cookie không.

## 12. Kiểm tra logout sau khi xoay ID

Logout phải thu hồi session mới. Xóa cookie ở browser không đủ để chứng minh server-side session đã bị xóa.

Test:

1. Tạo pre-auth session.
2. Đăng nhập và nhận newId.
3. Gửi request logout với cookie mới.
4. Xác nhận response hết hạn cookie theo resolver.
5. Xác nhận repository không còn session theo newId.
6. Gửi request bảo vệ với cookie cũ và cookie mới; cả hai đều không được khôi phục Authentication.

Nếu logout endpoint dùng POST và CSRF đang bật, gửi CSRF token theo cấu hình. Không tắt CSRF trong test tích hợp chỉ để làm request logout dễ hơn.

Nếu ứng dụng hỗ trợ logout mọi thiết bị, kiểm tra principal index/session registry riêng. Đổi ID sau login chỉ xử lý fixation của phiên hiện tại; nó không tự thu hồi những session khác của cùng principal.

## 13. Kiểm thử thất bại đăng nhập

Session fixation protection thường được áp dụng sau khi authentication thành công. Một lần đăng nhập sai không được tạo Authentication hợp lệ hoặc cho phép truy cập resource bảo vệ.

Test nên xác minh:

- Sai mật khẩu trả về login failure theo cấu hình.
- Request sau đó không được xác thực.
- Không có SecurityContext hợp lệ được lưu cho principal.
- Ứng dụng không vô tình chuyển pre-auth session thành authenticated.
- Nếu session ID thay đổi do một policy khác, test vẫn xác minh ID mới không có Authentication.

Không khẳng định mọi implementation bắt buộc giữ nguyên ID sau login thất bại; custom failure handler hoặc chính sách session có thể tạo/xóa session. Điều cần bảo đảm là không có quyền xác thực được cấp và không rò rỉ session state.

## 14. Đăng nhập qua custom authentication filter

Form login chuẩn của Spring Security tích hợp với SessionAuthenticationStrategy. Nếu ứng dụng tự viết authentication filter hoặc endpoint login, cần bảo đảm luồng thành công vẫn gọi đúng strategy.

Một lỗi phổ biến là:

1. Custom controller xác minh username/password.
2. Controller tự tạo Authentication.
3. Controller tự đặt SecurityContextHolder.
4. Controller trả success mà không gọi session authentication strategy hoặc lưu context theo cơ chế đúng.

Kết quả có thể là Authentication tồn tại trong thread hiện tại nhưng session ID không được xoay hoặc SecurityContext không được persist qua request kế tiếp.

Với custom authentication, tích hợp theo cơ chế Spring Security được hỗ trợ cho phiên bản đang dùng. Đảm bảo:

- SessionAuthenticationStrategy được gọi sau khi authentication thành công.
- Session fixation protection được áp dụng.
- SecurityContext được lưu bằng repository phù hợp.
- Response phát ID mới.
- Request kế tiếp khôi phục đúng Authentication.

Không tự viết logic xoay ID song song với strategy của Spring Security; hai cơ chế có thể tạo nhiều lần rotation, mất attributes hoặc phát cookie không nhất quán.

## 15. Kiểm thử với Spring Session Redis hoặc JDBC

Để xác minh integration thật, test cần dùng repository tương ứng:

- Redis: khởi động Redis test instance/container và bật cấu hình Spring Session Redis mà ứng dụng sử dụng.
- JDBC: dùng database test, schema Spring Session đúng phiên bản và transaction phù hợp.
- Custom repository: dùng implementation thật cùng storage test riêng.

Không mock SessionRepository trong test có mục tiêu xác nhận ID cũ bị xóa và ID mới được lưu. Mock chỉ phù hợp với unit test logic của service hoặc filter riêng.

Với Redis/JDBC, kiểm tra:

- Session mới có thể được đọc từ repository sau login.
- ID cũ không còn đọc được.
- Attributes và SecurityContext được serialize/deserialize đúng.
- TTL vẫn được giữ hoặc tính lại theo session lifecycle.
- Index principal được cập nhật nếu repository hỗ trợ.
- Request từ node khác có thể dùng ID mới.

Không phụ thuộc vào tên key Redis hoặc SQL nội bộ nếu API repository đã cung cấp bằng chứng. Nếu cần kiểm tra storage-level behavior, dùng schema/key format của đúng phiên bản và cô lập test data.

## 16. Kiểm thử qua nhiều instance

Trong triển khai nhiều node, session ID mới phải có hiệu lực trên mọi instance dùng chung repository. ID cũ phải không được chấp nhận ở bất kỳ node nào.

Kịch bản:

1. Request trước login tới node A và tạo oldId.
2. Login thành công qua node A, nhận newId.
3. Request với newId tới node B.
4. Node B khôi phục đúng principal và session attributes theo strategy.
5. Request với oldId tới node B.
6. Node B từ chối xác thực.
7. Logout ở node B.
8. Request newId tới node A bị từ chối.

Test hai node phải dùng hai application context hoặc process riêng, cùng trỏ vào Redis/JDBC test store. Hai client gọi cùng một bean singleton không chứng minh khả năng multi-node.

Nếu load balancer dùng sticky session, vẫn cần test cross-node vì deployment, restart hoặc failover có thể chuyển request sang instance khác. Sticky routing không thay thế shared session repository.

## 17. Cookie security và giới hạn của session ID rotation

Session ID rotation chỉ giảm rủi ro fixation. Nó không thay thế:

- HTTPS/TLS để bảo vệ cookie trên đường truyền.
- HttpOnly để hạn chế JavaScript đọc cookie.
- Secure để chỉ gửi cookie qua HTTPS.
- SameSite phù hợp với luồng ứng dụng.
- CSRF protection cho thao tác thay đổi trạng thái.
- XSS prevention và Content Security Policy phù hợp.
- Chính sách timeout, logout và thu hồi session.
- Entropy đủ mạnh của session ID.

Không đưa session ID vào URL, query string, log, analytics hoặc referrer. Không gửi cookie qua kênh không tin cậy.

Sau khi người dùng nâng quyền, đổi mật khẩu hoặc hoàn thành re-authentication, ứng dụng có thể cần rotation bổ sung hoặc revoke session theo threat model. Hãy dùng cơ chế session/security được hỗ trợ, tránh tự quản lý session ID bằng cách ghi đè cookie thủ công.

## 18. Các lỗi cấu hình và tích hợp thường gặp

- **Dùng STATELESS:** không có session state để xác minh rotation.
- **Không tạo session trước login trong test:** không chứng minh ID đã thay đổi.
- **Login request không gửi cookie cũ:** test vô tình tạo một session mới độc lập.
- **Chỉ kiểm tra Set-Cookie:** chưa chứng minh repository lưu session mới.
- **Chỉ kiểm tra repository:** chưa chứng minh browser nhận ID mới.
- **Không kiểm tra ID cũ:** session cũ có thể vẫn truy cập được.
- **Dùng none:** bỏ qua bảo vệ session fixation.
- **Chọn newSession nhưng mong giữ mọi attributes:** sai với semantics của strategy.
- **Custom filter bỏ qua SessionAuthenticationStrategy:** Authentication thành công nhưng ID không được xoay.
- **SessionRepositoryFilter đăng ký sai thứ tự:** Spring Security có thể thao tác với session container thay vì session Spring Session.
- **Cookie name hard-code sai:** test đọc nhầm cookie hoặc bỏ lỡ cookie mới.
- **Chỉ test một node:** không phát hiện node khác còn chấp nhận ID cũ.
- **Log cookie/session ID:** rò rỉ bearer credential.

## 19. Ma trận kiểm thử đề xuất

| Kịch bản | Assertion chính |
| --- | --- |
| Pre-auth session | Có session ID trước login |
| Successful login | Session ID sau login khác ID trước login |
| Cookie/header rotation | Resolver phát định danh mới |
| Authenticated request | ID mới khôi phục đúng principal |
| Old ID request | Không truy cập được resource bảo vệ |
| Repository lookup | ID cũ không còn session; ID mới tồn tại |
| Attribute migration | Kết quả đúng theo changeSessionId/migrateSession/newSession |
| Failed login | Không có Authentication hợp lệ |
| Logout | ID mới bị invalidate và cookie được hết hạn |
| Custom filter | Strategy vẫn được gọi |
| Multi-instance | Node B chấp nhận ID mới và từ chối ID cũ |
| Redis/JDBC integration | Persistence, serialization và TTL đúng |

Nên có ít nhất một test tích hợp qua filter chain thật và repository thật. Unit test strategy riêng có thể bổ sung nhưng không thay thế test end-to-end.

## 20. Checklist trước khi phát hành

- [ ] Ứng dụng dùng session-based authentication cho luồng cần kiểm tra.
- [ ] Session fixation protection được bật và strategy được xác định rõ.
- [ ] Session ID được tạo trước login trong test.
- [ ] Login request gửi lại đúng cookie/header cũ.
- [ ] Response login phát session ID mới khác ID cũ.
- [ ] Request với ID mới khôi phục Authentication đúng.
- [ ] Request với ID cũ không truy cập được resource bảo vệ.
- [ ] Repository không còn session hợp lệ theo ID cũ.
- [ ] Attributes được bảo toàn hoặc loại bỏ đúng strategy.
- [ ] Custom authentication filter gọi SessionAuthenticationStrategy.
- [ ] SessionRepositoryFilter được đăng ký đúng thứ tự trước Spring Security.
- [ ] Logout thu hồi session mới ở repository.
- [ ] Cookie name và flags khớp resolver thực tế.
- [ ] Test dùng Redis/JDBC repository thật khi cần xác minh persistence.
- [ ] Có kiểm thử cross-node nếu ứng dụng chạy nhiều instance.
- [ ] Không log session ID, cookie value hoặc token.

## 21. Tự kiểm tra kiến thức

Bạn đã nắm được bài học nếu có thể trả lời:

- Session fixation khác session hijacking như thế nào?
- Vì sao phải tạo một session trước login để kiểm tra rotation?
- SessionAuthenticationStrategy được gọi ở thời điểm nào?
- changeSessionId khác migrateSession và newSession ở việc bảo toàn attributes ra sao?
- SessionRepositoryFilter giúp Spring Security đổi ID trong Spring Session như thế nào?
- Vì sao phải kiểm tra cả cookie/header và repository state?
- Làm thế nào chứng minh ID cũ không còn truy cập được?
- Custom authentication filter cần làm gì để không bỏ qua session fixation protection?
- Vì sao phải test đổi ID trên hai instance cùng dùng repository?
- Session ID rotation không bảo vệ được những loại tấn công nào?

Khi đăng nhập thành công, ứng dụng phải chuyển sang một session identity mới theo chiến lược session fixation đã chọn. Với Spring Session, việc đổi ID cần đi qua request wrapper và repository để ID mới được lưu, ID cũ không còn xác thực, và resolver phát định danh mới cho client. Bài kiểm thử tốt phải bắt đầu bằng một pre-auth session thực, gửi lại cookie cũ trong login request, rồi xác minh ID mới, Authentication, attributes, repository state, old-ID rejection và logout trên cả đường HTTP lẫn storage dùng chung.
