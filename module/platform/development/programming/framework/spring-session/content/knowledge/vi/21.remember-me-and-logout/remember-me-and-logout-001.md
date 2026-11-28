# Cookie tồn tại lâu, phiên tồn tại lâu và đăng nhập ghi nhớ là các cơ chế khác nhau

Trong ứng dụng Spring, một trình duyệt có thể giữ cookie trong nhiều ngày, server có thể giữ dữ liệu HttpSession trong nhiều giờ, và Spring Security có thể tự xác thực lại người dùng khi phiên thông thường đã hết hạn. Ba hành vi này liên quan đến nhau nhưng không phải cùng một cơ chế.

- **Cookie session ID tồn tại lâu** chỉ quyết định trình duyệt giữ và gửi định danh phiên trong bao lâu.
- **Session tồn tại lâu** phụ thuộc thời hạn không hoạt động và chính sách lưu trữ của Spring Session repository.
- **Remember-me login** là cơ chế xác thực dài hạn riêng của Spring Security, dùng credential ghi nhớ để tạo lại Authentication khi người dùng quay lại.

Nếu kéo dài Max-Age của cookie mà không thay đổi TTL server, cookie vẫn có thể trỏ đến một session đã hết hạn. Nếu kéo dài TTL server mà trình duyệt đã xóa cookie, client không còn ID để tìm lại phiên. Nếu dùng remember-me, Spring Security có thể xác thực lại và tạo một session mới sau khi session cũ hết hạn, tùy chính sách session của ứng dụng.

Bài học đặt trong bối cảnh ứng dụng Servlet dùng Spring Session với Redis hoặc JDBC và Spring Security stateful. Mục tiêu là chọn đúng cơ chế theo trải nghiệm người dùng, hiểu ranh giới lưu trữ và xác thực, rồi kiểm thử logout, hết hạn và thu hồi credential.

## 1. Ba vòng đời độc lập

Một lần đăng nhập có thể liên quan đến ít nhất ba loại dữ liệu:

1. Cookie chứa session ID, ví dụ **SESSION**.
2. Bản ghi HttpSession trong Redis hoặc JDBC.
3. Cookie remember-me và, với persistent-token approach, bản ghi token phía server.

Các dữ liệu này có vòng đời khác nhau:

| Cơ chế | Nơi giữ | Điều khiển thời hạn bởi | Mục đích |
|---|---|---|---|
| Session ID cookie | Browser cookie jar | Cookie Max-Age/Expires và browser policy | Gửi session ID ở request sau |
| HttpSession | Spring Session repository | Max inactive interval / TTL repository | Giữ trạng thái giữa các request |
| Remember-me cookie | Browser cookie jar | Remember-me token validity và cookie expiry | Cho phép xác thực lại sau khi session không còn |
| Persistent remember-me token | Repository token phía server | Token validity, rotation và revoke | Xác minh và quản lý credential ghi nhớ |

Không nên gọi cả ba là “remember me”. Cookie session ID dài hạn không tự kích hoạt Spring Security remember-me; session TTL dài không tự làm cookie tồn tại; remember-me token không phải session ID.

## 2. Cookie session ID tồn tại lâu có nghĩa gì?

Cookie session ID là phương tiện để trình duyệt gửi lại định danh phiên. Với Spring Session Servlet, resolver cookie thường dùng tên **SESSION**. Cookie có thể là session cookie, thường bị browser loại bỏ khi phiên trình duyệt kết thúc, hoặc persistent cookie với Max-Age/Expires.

Spring Session cho phép tùy chỉnh cookie bằng DefaultCookieSerializer:

~~~java
@Bean
public CookieSerializer cookieSerializer() {
    DefaultCookieSerializer serializer = new DefaultCookieSerializer();
    serializer.setCookieName("SESSION");
    serializer.setCookiePath("/");
    serializer.setUseHttpOnlyCookie(true);
    serializer.setUseSecureCookie(true);
    serializer.setSameSite("Lax");
    serializer.setCookieMaxAge(Duration.ofDays(7));
    return serializer;
}
~~~

Ví dụ trên làm cookie session ID tồn tại tối đa bảy ngày ở phía browser. Nó không tự thay đổi thời gian sống của session trong Redis/JDBC. setCookieMaxAge chỉ tác động cookie; repository timeout được cấu hình riêng.

Một số điểm cần nhớ:

- Persistent cookie có thể được giữ sau khi đóng browser, tùy browser và cài đặt.
- Session cookie thường được browser quản lý theo phiên trình duyệt; khôi phục phiên browser có thể làm hành vi khác nhau.
- Xóa cookie làm client mất session ID nhưng không nhất thiết xóa bản ghi server ngay lập tức.
- Cookie còn tồn tại không chứng minh session trong repository còn hợp lệ.
- Không đưa session ID vào URL hoặc lưu trong log để thay thế cookie.

Nếu cần cookie dài hạn, hãy quyết định thời hạn dựa trên thiết bị dùng chung hay riêng, độ nhạy cảm của dữ liệu và khả năng thu hồi khi mất thiết bị.

## 3. Session tồn tại lâu là chính sách phía server

HttpSession có thời gian không hoạt động tối đa, thường được biểu diễn bằng maxInactiveInterval. Spring Session lưu metadata này trong repository. Khi phiên không được truy cập trong thời gian cấu hình, repository xem phiên đã hết hạn và không tiếp tục khôi phục phiên như một session hợp lệ.

Ví dụ cấu hình timeout 30 phút:

~~~yaml
spring:
  session:
    timeout: 30m
~~~

Với cấu hình Java bật Redis-backed session, timeout cũng có thể được đặt theo API của phiên bản đang dùng:

~~~java
@Configuration
@EnableRedisHttpSession(maxInactiveIntervalInSeconds = 1800)
class SessionConfiguration {
}
~~~

Đối với JDBC, cần dùng module và cấu hình Spring Session JDBC phù hợp; metadata hết hạn được lưu trong bảng session và cleanup job xử lý bản ghi hết hạn theo cơ chế repository.

Session timeout khác cookie Max-Age:

- Cookie có thể còn bảy ngày nhưng server session chỉ không hoạt động 30 phút.
- Server session có thể được giữ lâu hơn cookie, nhưng browser đã xóa cookie nên không còn ID để khôi phục.
- Một request hợp lệ có thể cập nhật last accessed time và gia hạn thời điểm hết hạn theo chính sách repository.
- Thời hạn chính xác và cách dọn dữ liệu phụ thuộc repository; không nên dựa vào thời điểm vật lý xóa key/row để quyết định quyền truy cập.

Kéo dài session timeout làm tăng thời gian tồn tại của trạng thái đăng nhập và dữ liệu phiên phía server. Hãy chỉ làm vậy khi có yêu cầu nghiệp vụ rõ ràng và đã đánh giá nguy cơ thiết bị bị mất hoặc dùng chung.

## 4. Ví dụ cookie dài hơn session

Giả sử ứng dụng cấu hình:

- SESSION cookie Max-Age: 7 ngày.
- HttpSession max inactive interval: 30 phút.
- Remember-me: chưa bật.

Người dùng đăng nhập lúc 09:00, sau đó không truy cập ứng dụng trong hai giờ. Browser vẫn giữ cookie SESSION, nhưng repository đã hết hạn session sau 30 phút không hoạt động.

Khi người dùng quay lại lúc 11:00:

1. Browser gửi cookie SESSION cũ.
2. Spring Session tìm session ID trong repository.
3. Session không còn hợp lệ hoặc đã bị dọn.
4. Request được xử lý như chưa có session đăng nhập.
5. Nếu endpoint tạo session, ứng dụng có thể tạo một session mới nhưng chưa có Authentication.

Kết quả: cookie dài hạn không duy trì trạng thái đăng nhập khi session phía server đã hết hạn. Người dùng phải đăng nhập lại nếu không có cơ chế xác thực dài hạn khác.

## 5. Remember-me của Spring Security là gì?

Remember-me là cơ chế xác thực cho phép Spring Security tự động khôi phục Authentication khi người dùng quay lại mà session đăng nhập thông thường không còn. Khi đăng nhập thành công và người dùng chọn “Ghi nhớ tôi”, ứng dụng phát một remember-me cookie có thời hạn dài hơn session thông thường.

Ở request sau, nếu SecurityContext không có Authentication nhưng remember-me cookie hợp lệ, RememberMeAuthenticationFilter gọi RememberMeServices để xác minh credential. Nếu hợp lệ, Spring Security tạo một RememberMeAuthenticationToken và đặt Authentication vào SecurityContext. Tùy SecurityContextRepository và SessionCreationPolicy, context có thể được lưu vào HttpSession mới để request tiếp theo tiếp tục dùng stateful session.

Luồng tổng quát:

    Người dùng đăng nhập
           |
           +--> Authentication thành công
           |        |
           |        +--> Lưu SecurityContext vào HttpSession
           |        |
           |        +--> Nếu chọn remember-me:
           |                 phát remember-me cookie
           |
           v
    Session thường hết hạn
           |
           v
    Người dùng quay lại, gửi remember-me cookie
           |
           v
    RememberMeAuthenticationFilter
           |
           v
    RememberMeServices xác minh token
           |
           v
    Tạo RememberMeAuthenticationToken
           |
           v
    SecurityContext được thiết lập
           |
           v
    Có thể tạo/lưu HttpSession mới theo policy

Remember-me không giữ nguyên HttpSession cũ. Nó cho phép xác thực lại bằng credential ghi nhớ. Giỏ hàng hoặc trạng thái wizard nằm trong session đã hết hạn có thể không còn; chỉ trạng thái được khôi phục từ nguồn khác hoặc được tạo lại mới tồn tại.

## 6. Cấu hình remember-me trong Spring Security

Với form login, người dùng thường chọn checkbox có tên remember-me. Spring Security hỗ trợ cấu hình remember-me qua DSL.

Ví dụ cơ bản:

~~~java
@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        UserDetailsService userDetailsService) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/public/**").permitAll()
            .requestMatchers("/account/**").authenticated()
            .anyRequest().denyAll()
        )
        .formLogin(Customizer.withDefaults())
        .rememberMe(remember -> remember
            .key("load-this-from-secret-configuration")
            .tokenValiditySeconds(14 * 24 * 60 * 60)
            .userDetailsService(userDetailsService)
        )
        .build();
}
~~~

Ví dụ đặt thời hạn remember-me là 14 ngày. Giá trị key trong ví dụ chỉ là placeholder; production phải lấy secret từ secret manager hoặc cấu hình bảo mật, không commit vào source control.

Một số cấu hình thường gặp:

| Cấu hình | Ý nghĩa |
|---|---|
| key | Bí mật dùng trong cơ chế tạo/xác minh token của remember-me service |
| tokenValiditySeconds | Thời gian hiệu lực token |
| userDetailsService | Tải user và kiểm tra trạng thái/tài khoản khi xác thực lại |
| rememberMeParameter | Tên form parameter của checkbox |
| rememberMeCookieName | Tên cookie remember-me |
| tokenRepository | Kho lưu token khi dùng persistent-token approach |

Remember-me cần một cách tải thông tin người dùng, thường qua UserDetailsService. Nếu ứng dụng tự viết authentication mechanism hoặc dùng nhiều loại client, cần xác định rõ luồng nào được phép phát remember-me cookie. Không phát credential ghi nhớ cho tài khoản chưa xác thực thành công.

## 7. Hai cách triển khai remember-me

Spring Security có hai cách tiếp cận phổ biến:

1. Token-based remember-me: token được xác minh bằng dữ liệu trong cookie, thời hạn và chữ ký/hash gắn với thông tin người dùng cùng key.
2. Persistent-token remember-me: cookie mang token ngẫu nhiên có trạng thái tương ứng được lưu ở repository phía server.

| Đặc điểm | Token-based | Persistent-token |
|---|---|---|
| Trạng thái server | Không cần bản ghi token riêng cho mỗi thiết bị | Lưu token/series trong PersistentTokenRepository |
| Thu hồi từng thiết bị | Khó hơn nếu không có denylist hoặc key riêng | Có thể quản lý theo series/token nếu repository và service hỗ trợ |
| Phát hiện token cũ bị dùng lại | Không có cùng cơ chế rotation/series của persistent-token | Có thể phát hiện token cũ sau rotation và xử lý nghi ngờ bị đánh cắp |
| Vận hành | Ít thành phần lưu trữ hơn | Cần schema hoặc repository token riêng |
| Phù hợp | Nhu cầu đơn giản, chấp nhận thu hồi thô hơn | Cần quản lý nhiều thiết bị và thu hồi token phía server |

Với token-based approach, token thường gắn với username, thời điểm hết hạn, key và thông tin xác thực như password hash. Khi password hoặc key thay đổi, token cũ có thể không còn hợp lệ. Khả năng thu hồi riêng một browser/device hạn chế hơn vì server không giữ một bản ghi riêng cho từng token.

Với persistent-token approach, mỗi browser/client nhận một token gắn với series và token value. Server lưu bản ghi để xác minh. Sau khi sử dụng thành công, token có thể được xoay vòng. Nếu một token cũ đã bị thay thế lại xuất hiện, implementation tiêu chuẩn có thể coi đó là dấu hiệu token bị sao chép và thu hồi các token của user. Cần đọc tài liệu phiên bản đang dùng để hiểu chính xác hành vi và phạm vi revoke.

## 8. Cấu hình persistent remember-me token

Spring Security cung cấp PersistentTokenRepository để lưu token. Với JDBC có thể dùng JdbcTokenRepositoryImpl và schema remember-me token tương ứng.

Ví dụ:

~~~java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
~~~

Sau đó cấu hình remember-me:

~~~java
.rememberMe(remember -> remember
    .key("load-this-from-secret-configuration")
    .tokenValiditySeconds(14 * 24 * 60 * 60)
    .userDetailsService(userDetailsService)
    .tokenRepository(persistentTokenRepository)
)
~~~

Schema JDBC cho persistent remember-me token là dữ liệu riêng của Spring Security, không phải bảng SPRING_SESSION của Spring Session. Ứng dụng phải tạo schema đúng theo tài liệu Spring Security và phiên bản database. Không nhầm persistent remember-me token repository với SessionRepository của Spring Session.

Nếu session được lưu trong Redis nhưng remember-me token lưu trong JDBC, đó vẫn là kiến trúc hợp lệ nếu được thiết kế và vận hành rõ ràng. Hai kho phục vụ hai loại dữ liệu khác nhau. Cần bảo đảm backup, quyền truy cập, thời hạn và tính sẵn sàng cho cả hai.

## 9. Remember-me không phải là session TTL dài

Một lỗi thiết kế phổ biến là kéo dài maxInactiveInterval lên nhiều ngày rồi gọi đó là remember-me. Điều này chỉ làm session server tồn tại lâu hơn. Nếu session chứa SecurityContext, người dùng có thể tiếp tục được xác thực từ session đó trong thời gian dài mà không cần cơ chế xác thực lại độc lập.

Remember-me có mục tiêu khác: khi session thông thường hết hạn, một credential riêng có thể khôi phục Authentication. Điều này giúp giữ timeout session ngắn hơn để giảm thời gian tồn tại của trạng thái phiên, trong khi vẫn cung cấp trải nghiệm đăng nhập tiện lợi.

| Mục tiêu | Cơ chế nên xem xét |
|---|---|
| Giữ giỏ hàng trong thời gian dài | Lưu giỏ hàng ở kho nghiệp vụ hoặc tăng session TTL có cân nhắc |
| Giữ session đăng nhập không hoạt động lâu | Tăng session timeout nếu chính sách bảo mật cho phép |
| Tự xác thực lại sau khi session hết hạn | Spring Security remember-me |
| Cho browser giữ session ID sau khi đóng | Persistent session cookie, nhưng server session vẫn có TTL riêng |
| Thu hồi token ghi nhớ theo thiết bị | Persistent-token approach hoặc mô hình device credential riêng |

Không dùng remember-me để thay thế việc lưu dữ liệu nghiệp vụ lâu dài. Nếu người dùng cần giỏ hàng tồn tại qua nhiều lần đăng nhập hoặc nhiều thiết bị, hãy lưu giỏ hàng theo user ID trong database/service nghiệp vụ.

## 10. Mức độ tin cậy của remember-me authentication

Remember-me authentication không nên được xem ngang với việc người dùng vừa nhập mật khẩu hoặc hoàn tất MFA. Spring Security có thể phân biệt remember-me Authentication với fully authenticated Authentication thông qua AuthenticationTrustResolver.

Điều này cho phép ứng dụng yêu cầu xác thực mạnh hơn cho thao tác nhạy cảm:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/profile").authenticated()
    .requestMatchers("/payments/confirm").fullyAuthenticated()
);
~~~

Trong ví dụ, người dùng có remember-me authentication có thể truy cập profile nếu policy cho phép, nhưng cần xác thực đầy đủ trước khi xác nhận thanh toán.

Các thao tác nên cân nhắc step-up authentication:

- Đổi mật khẩu hoặc email đăng nhập.
- Thêm hoặc xóa phương thức MFA.
- Xem hoặc thay đổi thông tin thanh toán nhạy cảm.
- Chuyển tiền hoặc phê duyệt giao dịch.
- Tạo API key hoặc thay đổi quyền tài khoản.
- Thu hồi thiết bị đáng tin cậy.

Remember-me cookie là bearer credential. Ai có cookie còn hiệu lực có thể có khả năng được xác thực như người dùng. Hãy giới hạn quyền và yêu cầu xác thực lại khi hành động có rủi ro cao.

## 11. Cookie attributes và bảo vệ remember-me credential

Remember-me cookie cần được bảo vệ tương tự session cookie:

- Chỉ truyền qua HTTPS; bật Secure.
- Bật HttpOnly để JavaScript không đọc cookie.
- Chọn SameSite phù hợp với luồng đăng nhập và redirect.
- Giới hạn Domain và Path.
- Không ghi cookie vào access log, trace hoặc telemetry.
- Dùng token đủ ngẫu nhiên, thời hạn ngắn nhất đáp ứng trải nghiệm.
- Không lưu password thô trong cookie.
- Có cơ chế thu hồi khi logout, đổi password hoặc tài khoản bị khóa.

Cookie remember-me thường có tên riêng, ví dụ remember-me; cookie session ID thường là SESSION. Không dùng cùng một tên cho hai loại credential. Điều đó giúp browser, proxy và nhóm vận hành phân biệt đúng vai trò.

Nếu ứng dụng cần tùy chỉnh thuộc tính cookie do remember-me service phát, hãy dùng cấu hình hoặc RememberMeServices tùy chỉnh được hỗ trợ trong phiên bản Spring Security. Không giả định DefaultCookieSerializer của Spring Session cũng điều khiển cookie remember-me của Spring Security; hai thành phần phát cookie độc lập.

SameSite không thay thế CSRF protection. Nếu ứng dụng dùng cookie tự động gửi theo request, hãy giữ CSRF policy phù hợp. CORS cũng không ngăn XSS sử dụng credential cùng origin.

## 12. Logout phải thu hồi session và remember-me credential

Logout cần xử lý cả session hiện tại và credential ghi nhớ. Nếu chỉ invalidate HttpSession nhưng remember-me cookie còn hợp lệ, request tiếp theo có thể tự động xác thực lại người dùng và tạo session mới. Điều đó có thể khiến người dùng nghĩ rằng logout không hoạt động.

Trong cấu hình Spring Security chuẩn, RememberMeServices tham gia logout qua LogoutHandler để xóa cookie và xử lý token theo implementation. Khi tự xây dựng hoặc thay thế logout handlers, cần xác nhận remember-me service vẫn được gọi.

Ví dụ cấu hình logout:

~~~java
http.logout(logout -> logout
    .logoutUrl("/logout")
    .invalidateHttpSession(true)
    .clearAuthentication(true)
    .deleteCookies("SESSION")
);
~~~

Ở đây SESSION là cookie session ID. Remember-me cookie cần được xóa bởi RememberMeServices đã cấu hình. Nếu tự quản lý cookie hoặc custom service, cần xóa đúng cookie remember-me và revoke token server-side tương ứng.

Các bước logout nên gồm:

1. Xác định principal hiện tại.
2. Xóa Authentication/SecurityContext theo logout flow.
3. Invalidate HttpSession để Spring Session xóa phiên trong Redis/JDBC.
4. Xóa session ID cookie ở client.
5. Xóa remember-me cookie.
6. Thu hồi persistent remember-me token theo chính sách.
7. Ghi audit event không chứa credential thô.

Xóa cookie ở browser mà không revoke token phía server có thể không đủ, nhất là khi token đã bị sao chép. Ngược lại, revoke server-side nhưng response không tới browser có thể khiến browser tiếp tục gửi token cũ; server phải từ chối token đó.

## 13. Logout một thiết bị và logout mọi thiết bị

Một người dùng có thể có nhiều browser profile và nhiều remember-me token. Mỗi thiết bị có thể có một session và một remember-me credential riêng.

Với persistent-token approach, repository lưu các series/token theo user. Điều này tạo khả năng quản lý token theo từng thiết bị nếu ứng dụng có giao diện và service phù hợp. Tuy nhiên, API revoke cụ thể phụ thuộc PersistentTokenRepository và RememberMeServices đang dùng.

Các mục tiêu cần phân biệt:

| Hành động | Session | Remember-me token |
|---|---|---|
| Logout phiên hiện tại | Invalidate session hiện tại | Xóa/revoke credential ghi nhớ hiện tại theo service |
| Logout một thiết bị | Xóa các session gắn với device đó | Revoke token/series của device đó |
| Logout mọi thiết bị | Xóa tất cả session theo principal | Revoke tất cả remember-me token của principal |
| Đổi mật khẩu | Có thể thu hồi các session theo policy | Token-based thường không còn hợp lệ nếu hash phụ thuộc password; persistent token cần revoke rõ ràng |
| Khóa tài khoản | Chặn Authentication và thu hồi session | Revoke token ghi nhớ và kiểm tra trạng thái tài khoản khi auto-login |

Không giả định xóa tất cả Spring Session records tự động xóa persistent remember-me tokens. Đây là hai repository và hai vòng đời riêng. Nếu sản phẩm yêu cầu “đăng xuất mọi nơi”, service phải phối hợp cả hai.

Với token-based remember-me không có bản ghi riêng cho từng thiết bị, việc revoke riêng lẻ khó hơn. Có thể cần đổi key, đổi password hoặc duy trì denylist/credential version; các lựa chọn này có phạm vi ảnh hưởng rộng hơn. Nếu cần quản lý thiết bị cụ thể, persistent-token hoặc device credential repository thường dễ kiểm soát hơn.

## 14. Xử lý đổi mật khẩu, khóa tài khoản và thu hồi token

Remember-me chỉ an toàn khi mỗi lần tự xác thực đều kiểm tra trạng thái tài khoản hiện tại. UserDetailsService hoặc cơ chế xác thực tương ứng cần phản ánh account disabled, locked, expired hoặc credential thay đổi.

Các sự kiện nghiệp vụ quan trọng nên kích hoạt chính sách thu hồi:

- Người dùng đổi mật khẩu.
- Quản trị viên khóa tài khoản.
- Người dùng báo mất thiết bị.
- Phát hiện token bị dùng lại sau rotation.
- Người dùng chọn logout all devices.
- Tài khoản bật MFA hoặc thay đổi chính sách bảo mật.

Đối với persistent token, có thể xóa các bản ghi token của user hoặc token series cụ thể theo repository/service. Đối với token-based, thay đổi password/key có thể làm token cũ không còn xác minh được, nhưng phải hiểu ảnh hưởng đến tất cả thiết bị.

Không chỉ dựa vào việc cookie hết hạn. Server cần từ chối token đã bị revoke hoặc không còn phù hợp với trạng thái tài khoản. Với endpoint nhạy cảm, kiểm tra trạng thái tài khoản và yêu cầu xác thực mạnh hơn ngay cả khi remember-me token vẫn hợp lệ.

## 15. Tương tác giữa remember-me và SessionCreationPolicy

Remember-me tạo Authentication cho request, nhưng việc Authentication có được lưu vào HttpSession hay không còn phụ thuộc SecurityContextRepository và SessionCreationPolicy.

| SessionCreationPolicy | Tác động với HttpSession |
|---|---|
| ALWAYS | Security chain tạo session khi cần theo policy |
| IF_REQUIRED | Tạo session khi thành phần bảo mật hoặc ứng dụng cần |
| NEVER | Không chủ động tạo session nhưng có thể dùng session đã tồn tại |
| STATELESS | Không dùng HttpSession để lưu SecurityContext |

Nếu ứng dụng muốn remember-me tự xác thực lại rồi duy trì trạng thái đăng nhập qua các request bằng HttpSession, cần cấu hình stateful phù hợp, thường là IF_REQUIRED. Nếu đặt STATELESS, không mong SecurityContext được lưu vào session sau remember-me; mỗi request phải xác thực theo cơ chế stateless được thiết kế.

Cần kiểm thử cấu hình thực tế, vì endpoint hoặc filter tùy chỉnh cũng có thể tạo session. SessionCreationPolicy.STATELESS không ngăn mọi code nghiệp vụ gọi request.getSession() để lưu dữ liệu riêng; nó chỉ điều khiển cách Spring Security sử dụng session cho security context.

## 16. Vận hành nhiều instance

Trong môi trường nhiều instance, Spring Session repository chia sẻ HttpSession giữa các node. Remember-me credential cũng phải được xác minh nhất quán trên mọi instance.

Với token-based remember-me, các instance phải dùng cùng key và cùng cách tải UserDetails. Nếu key khác nhau, token phát ở node A có thể bị node B từ chối.

Với persistent-token approach:

- Các instance dùng chung PersistentTokenRepository.
- Schema và serialization tương thích.
- Mỗi instance dùng cùng key/configuration.
- Token rotation và phát hiện reuse có hành vi nhất quán.
- Đồng hồ hệ thống được đồng bộ để kiểm tra expiry.
- Logout hoặc revoke từ node A có hiệu lực khi request tiếp theo đến node B.

Luồng kiểm thử quan trọng:

    Login tại instance A
          |
          +--> SESSION cookie
          |
          +--> remember-me cookie
          |
          v
    Session hết hạn hoặc bị xóa
          |
          v
    Request quay lại instance B
          |
          v
    B xác minh remember-me token
          |
          v
    B tải user hiện tại và tạo Authentication
          |
          v
    SecurityContext được thiết lập
          |
          v
    Có thể lưu session mới vào repository dùng chung

Nếu instance A và B không chia sẻ remember-me key hoặc token repository, người dùng có thể đăng nhập ghi nhớ thành công trên node này nhưng thất bại ngẫu nhiên khi load balancer chuyển sang node khác.

## 17. Kiểm thử các vòng đời riêng biệt

Không nên chỉ kiểm thử checkbox remember-me làm xuất hiện cookie. Cần kiểm thử các vòng đời độc lập và tương tác giữa chúng.

Các trường hợp nên có:

1. Đăng nhập không chọn remember-me; xác nhận chỉ có session credential theo cấu hình.
2. Đăng nhập chọn remember-me; xác nhận remember-me cookie được phát với thời hạn dự kiến.
3. Để session hết hạn nhưng remember-me còn hạn; request tiếp theo được xác thực lại theo policy.
4. Để remember-me hết hạn; request không còn tự xác thực.
5. Cookie SESSION còn nhưng server session đã hết hạn; xác nhận session cũ không được khôi phục.
6. Server session còn nhưng browser mất cookie; xác nhận client không thể tìm phiên bằng ID đã mất.
7. Logout; xác nhận session bị xóa và remember-me token/cookie bị thu hồi.
8. Gửi lại persistent token cũ sau rotation; xác nhận hành vi phát hiện reuse theo implementation.
9. Đổi password hoặc khóa user; xác nhận remember-me không còn cấp Authentication trái policy.
10. Kiểm tra fullyAuthenticated endpoint từ chối remember-me authentication nếu yêu cầu xác thực mạnh.
11. Đăng nhập từ hai browser profile và xác nhận token/series được quản lý độc lập nếu dùng persistent-token.
12. Logout một thiết bị và xác nhận thiết bị khác còn hoạt động theo policy.
13. Logout all devices và xác nhận cả session lẫn remember-me credential đều bị thu hồi.
14. Gửi request qua hai instance và xác nhận cùng kết quả xác thực.
15. Kiểm tra cookie flags Secure, HttpOnly, SameSite, Path và Domain.
16. Kiểm tra log/proxy/trace không ghi session ID hoặc remember-me token.

Dùng MockMvc cho filter chain và cookie behavior; dùng repository JDBC/Redis thật hoặc môi trường tích hợp tương thích để kiểm tra session TTL và persistent-token persistence. Không dùng mock để kết luận TTL hoặc token rotation hoạt động trong production.

## 18. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Browser giữ cookie nhưng user bị đăng xuất | Session server đã hết hạn | Kiểm tra Max-Age cookie và repository timeout riêng |
| User được tự đăng nhập lại sau khi logout | Remember-me cookie/token chưa bị thu hồi | Kiểm tra RememberMeServices và logout handlers |
| Remember-me cookie có nhưng không tạo Authentication | Token hết hạn, key khác, user không hợp lệ hoặc repository không tìm token | Kiểm tra clock, key, UserDetailsService và token store |
| Node A chấp nhận token, node B từ chối | Key hoặc token repository không dùng chung | So sánh cấu hình các instance |
| Logout một thiết bị làm mất mọi thiết bị | Service xóa token theo user thay vì theo series/device | Kiểm tra phạm vi revoke |
| Đổi password nhưng token cũ vẫn hoạt động | Persistent token chưa được thu hồi hoặc user state không được kiểm tra | Revoke token và kiểm tra account status |
| Session mới không được tạo sau remember-me | STATELESS policy hoặc SecurityContextRepository không lưu session | Kiểm tra SessionCreationPolicy và save context |
| Cookie remember-me bị browser bỏ | Secure/SameSite/Domain/Path không phù hợp | Kiểm tra Set-Cookie và browser policy |
| Tự động đăng nhập nhưng thao tác thanh toán bị từ chối | Endpoint yêu cầu fully authenticated | Đây có thể là hành vi bảo mật mong muốn |

Khi điều tra, kiểm tra riêng cookie session, bản ghi session, remember-me cookie, remember-me token repository và Authentication được tạo. Không suy luận lỗi từ một cookie duy nhất.

## 19. Quy trình chọn chính sách

Khi thiết kế “Ghi nhớ tôi”, hãy trả lời các câu hỏi:

1. Người dùng cần giữ trạng thái đăng nhập sau khi đóng browser hay chỉ cần session sống trong thời gian hoạt động?
2. Thiết bị có phải máy cá nhân hay máy dùng chung?
3. Thời hạn session server cần bao lâu?
4. Remember-me token có thể sống bao lâu?
5. Có cần logout riêng từng thiết bị không?
6. Có cần phát hiện token bị sao chép/reuse không?
7. Đổi password hoặc khóa tài khoản có thu hồi tất cả token không?
8. Thao tác nào yêu cầu xác thực đầy đủ hoặc MFA?
9. Các instance có chia sẻ cùng key và token repository không?
10. Người dùng có thể xem và quản lý thiết bị đã ghi nhớ không?

Gợi ý lựa chọn:

| Yêu cầu | Hướng phù hợp |
|---|---|
| Không cần giữ đăng nhập sau khi browser đóng | Session cookie + session timeout |
| Muốn giữ session ID sau khi browser đóng, nhưng session vẫn có timeout ngắn | Persistent session cookie; hiểu rõ server session có thể hết hạn trước |
| Muốn tự xác thực lại sau khi session hết hạn | Spring Security remember-me |
| Cần thu hồi remember-me theo từng thiết bị | Persistent-token approach hoặc device credential store |
| Cần logout mọi nơi | Thu hồi cả Spring Session records và remember-me tokens |
| Dữ liệu nghiệp vụ phải tồn tại nhiều ngày | Lưu ở database/service nghiệp vụ, không dựa vào session |

## Kết luận

Cookie session ID dài hạn, HttpSession timeout dài và Spring Security remember-me là ba cơ chế có vòng đời độc lập. Cookie Max-Age chỉ điều khiển browser giữ ID; Spring Session timeout quyết định server còn chấp nhận session; remember-me cookie là credential riêng để Spring Security tạo Authentication mới khi session thường không còn. Hãy giữ session timeout phù hợp, chọn token-based hoặc persistent-token remember-me theo nhu cầu thu hồi, yêu cầu fully authenticated cho thao tác nhạy cảm, phối hợp logout để xóa cả session lẫn token và kiểm thử trên nhiều instance.
