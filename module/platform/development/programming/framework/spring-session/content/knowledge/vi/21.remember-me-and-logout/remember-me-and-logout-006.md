# Invalidate, xóa dữ liệu kho và xóa cookie hoặc định danh header

Spring Session lưu trạng thái HttpSession ở một kho dùng chung như Redis hoặc JDBC. Khi người dùng đăng xuất, quản trị viên thu hồi một phiên hoặc ứng dụng phát hiện credential bị lộ, cần kết thúc phiên ở cả hai phía: dữ liệu session phía server phải bị vô hiệu hóa và định danh session phía client phải được xử lý đúng cách.

Ba thao tác thường bị nhầm lẫn là HttpSession.invalidate(), xóa session trực tiếp bằng SessionRepository.deleteById() và xóa cookie hoặc header chứa session ID. Chúng liên quan với nhau nhưng có trách nhiệm khác nhau. Invalidate là thao tác vòng đời session ở API ứng dụng; repository deletion xóa bản ghi phía server theo ID; cookie/header cleanup khiến client ngừng gửi định danh cũ. Chỉ xóa một trong các phần này có thể để lại trạng thái không mong muốn.

## 1. Session ID và dữ liệu session nằm ở đâu?

Trong mô hình Servlet, trình duyệt thường gửi session ID trong cookie SESSION hoặc JSESSIONID. Spring Session dùng HttpSessionIdResolver để đọc ID từ request và ghi/xóa định danh trong response. SessionRepositoryFilter thay thế cách lưu session mặc định của servlet container bằng repository được cấu hình.

Với Redis hoặc JDBC:

- Cookie/header chứa định danh phiên, không chứa toàn bộ dữ liệu session.
- Repository lưu session attributes, thời gian tạo, thời gian truy cập và thời hạn.
- SessionRepositoryFilter cung cấp HttpSession cho controller và Spring Security.
- Khi request kết thúc, filter phối hợp lưu thay đổi và cập nhật định danh ở response theo trạng thái session.

Luồng khái quát:

~~~mermaid
flowchart TD
    A["Browser gửi cookie hoặc header chứa session ID"] --> B["HttpSessionIdResolver"]
    B --> C["SessionRepositoryFilter"]
    C --> D["SessionRepository.findById"]
    D --> E[("Redis / JDBC: session data")]
    E --> F["HttpSession trong request"]
    F --> G{"Invalidate?"}
    G -->|Không| H["Lưu các thay đổi cần thiết"]
    G -->|Có| I["Xóa session trong repository"]
    I --> J["Expire cookie hoặc xóa định danh header"]
    H --> K["Response"]
    J --> K
~~~

Session ID là credential dạng bearer: ai có ID hợp lệ và có thể gửi nó đến ứng dụng có thể sử dụng phiên tương ứng nếu không có lớp bảo vệ bổ sung. Không ghi session ID vào log, URL hoặc thông báo lỗi.

## 2. Phân biệt invalidate, xóa thuộc tính và xóa repository

HttpSession.invalidate() kết thúc phiên hiện tại. Sau khi invalidate, session không còn hợp lệ; các thuộc tính của phiên bị loại bỏ và những lần truy cập tiếp theo vào session object đã bị vô hiệu hóa có thể ném IllegalStateException.

Xóa một thuộc tính bằng removeAttribute() chỉ loại bỏ dữ liệu đó. Session vẫn còn hiệu lực, session ID vẫn có thể được dùng và các thuộc tính khác vẫn tồn tại.

SessionRepository.deleteById(sessionId) xóa session có ID được chỉ định trực tiếp khỏi repository. Đây là thao tác ở tầng lưu trữ, thường hữu ích khi quản trị viên cần thu hồi một phiên khác với phiên hiện tại.

| Thao tác | Phạm vi | Client identifier |
| --- | --- | --- |
| session.removeAttribute(name) | Xóa một thuộc tính | Không tự hết hạn cookie/header |
| session.invalidate() | Kết thúc phiên hiện tại qua API HttpSession | Session filter/resolver xử lý định danh trong response |
| repository.deleteById(id) | Xóa bản ghi session theo ID ở kho lưu trữ | Không tự xóa cookie trên thiết bị khác |
| Xóa cookie hoặc header ở client | Ngăn client gửi ID cũ | Không tự xóa dữ liệu session phía server |

Đối với logout thông thường, ưu tiên invalidate qua HttpSession hoặc dùng logout flow của Spring Security. Chỉ xóa repository trực tiếp khi có lý do quản trị hoặc nghiệp vụ rõ ràng và đã xác định cách xử lý identifier ở client.

## 3. Invalidate phiên hiện tại bằng HttpSession

Ví dụ một endpoint Servlet thu hồi phiên hiện tại:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class LogoutController {

    @PostMapping("/api/logout")
    ResponseEntity<Void> logout(HttpServletRequest request) {
        HttpSession session = request.getSession(false);
        if (session != null) {
            session.invalidate();
        }
        return ResponseEntity.noContent().build();
    }
}
~~~

getSession(false) trả về session hiện có nếu request đã có một phiên; nó không tạo session mới khi không tìm thấy. Đây là lựa chọn phù hợp cho logout vì endpoint không nên vô tình tạo một session mới chỉ để invalidate nó.

Khi SessionRepositoryFilter đang quản lý HttpSession, lệnh invalidate() được chuyển thành thao tác kết thúc phiên trong Spring Session repository. Filter và HttpSessionIdResolver xử lý việc hết hạn định danh trên response theo cơ chế tích hợp.

Đoạn code trên chỉ minh họa phần session. Nếu ứng dụng dùng Spring Security, nên để Spring Security logout filter xử lý SecurityContext, authentication và các logout handler khác. Một controller tự gọi invalidate() có thể chưa xóa hết trạng thái bảo mật nếu bỏ qua security logout flow.

Không tiếp tục dùng session object sau khi đã invalidate. Nếu cần dữ liệu để ghi audit, hãy lấy principal hoặc mã tương quan trước khi invalidate và chỉ ghi thông tin không nhạy cảm.

## 4. Invalidate không giống xóa từng attribute

Đôi khi ứng dụng muốn làm sạch giỏ hàng, trạng thái wizard hoặc dữ liệu tạm nhưng vẫn giữ đăng nhập. Khi đó, xóa attribute phù hợp hơn:

~~~java
HttpSession session = request.getSession(false);
if (session != null) {
    session.removeAttribute("temporaryWorkflow");
    session.removeAttribute("shoppingCartDraft");
}
~~~

Session vẫn còn hiệu lực và có thể tiếp tục được sử dụng. Không xóa SPRING_SECURITY_CONTEXT bằng tay như một cách thay thế logout nếu Spring Security đang quản lý context. Hãy dùng security logout handler để xóa authentication và session theo đúng thứ tự.

Nếu mục tiêu là đăng xuất, thu hồi quyền truy cập hoặc kết thúc phiên bị xâm phạm, phải invalidate toàn bộ session thay vì chỉ xóa một vài thuộc tính mà ứng dụng cho rằng quan trọng.

## 5. Xóa trực tiếp bằng SessionRepository

SessionRepository<S> cung cấp deleteById(String id) để xóa session khỏi kho dữ liệu. Ví dụ:

~~~java
import org.springframework.session.Session;
import org.springframework.session.SessionRepository;
import org.springframework.stereotype.Service;

@Service
class SessionRevocationService {

    private final SessionRepository<? extends Session> sessionRepository;

    SessionRevocationService(
            SessionRepository<? extends Session> sessionRepository) {
        this.sessionRepository = sessionRepository;
    }

    void revokeSession(String sessionId) {
        sessionRepository.deleteById(sessionId);
    }
}
~~~

Ví dụ này minh họa tầng service; session ID phải đến từ một nguồn đáng tin cậy và được kiểm tra quyền trước khi gọi. Không nhận một ID tùy ý từ client rồi xóa mà không xác nhận người gọi có quyền quản lý phiên đó.

Xóa trực tiếp trong repository không có đủ ngữ cảnh của response hiện tại để xóa cookie trên trình duyệt. Nếu ID thuộc một thiết bị khác, server cũng không thể gửi response đến thiết bị đó ngay tại thời điểm thu hồi. Thiết bị sẽ tiếp tục giữ ID cũ cho đến khi client tự xóa hoặc nhận được response phù hợp; request tiếp theo gửi ID cũ phải bị repository từ chối vì session không còn tồn tại.

Đối với phiên hiện tại, dùng HttpSession.invalidate() giúp filter phối hợp repository và resolver. Đối với phiên từ xa, repository deletion là một phần của quy trình thu hồi; cần thêm cách thông báo cho client hoặc chấp nhận rằng client sẽ phát hiện phiên đã bị thu hồi ở request tiếp theo.

## 6. Rủi ro khi xóa repository trong lúc request đang chạy

Một request có thể đã tải session vào bộ nhớ của instance A. Trong lúc request đó chưa kết thúc, instance B hoặc một tác vụ quản trị xóa session ID khỏi repository. Nếu request A tiếp tục sửa session và filter lưu thay đổi khi response hoàn tất, tùy implementation và thời điểm thao tác, dữ liệu có thể được ghi trở lại hoặc phát sinh race giữa save và delete.

Vì vậy, deleteById() không tự tạo ra một cơ chế thu hồi nguyên tử đối với mọi request đang chạy. Với yêu cầu thu hồi mạnh:

- Kiểm tra quyền và trạng thái tài khoản ở backend cho mỗi request quan trọng.
- Dùng authentication/session generation hoặc version ở cấp người dùng để từ chối session cũ.
- Có thể duy trì danh sách thu hồi/denylist với thời hạn phù hợp nếu mô hình bảo mật yêu cầu.
- Phối hợp việc khóa tài khoản, thay đổi mật khẩu hoặc thu hồi credential với việc xóa session.
- Kiểm thử trường hợp một request đang chạy đồng thời với thao tác thu hồi.

Đối với các thao tác nhạy cảm, không chỉ dựa vào việc session ID còn tồn tại trong repository. Xác minh trạng thái tài khoản và quyền hiện tại để giảm nguy cơ một request đã bắt đầu trước khi logout tiếp tục thực hiện hành động sau khi quyền bị thu hồi.

## 7. Xóa cookie khi dùng CookieHttpSessionIdResolver

Khi dùng cookie resolver, Spring Session có thể phát một Set-Cookie có thời hạn bằng 0 để yêu cầu trình duyệt xóa cookie session. Cấu hình cookie phải nhất quán với cookie đã phát hành.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.CookieHttpSessionIdResolver;
import org.springframework.session.web.http.DefaultCookieSerializer;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
class SessionCookieConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        CookieHttpSessionIdResolver resolver =
            new CookieHttpSessionIdResolver();

        DefaultCookieSerializer serializer = new DefaultCookieSerializer();
        serializer.setCookieName("SESSION");
        serializer.setCookiePath("/");
        serializer.setUseHttpOnlyCookie(true);
        serializer.setUseSecureCookie(true);
        serializer.setSameSite("Lax");

        resolver.setCookieSerializer(serializer);
        return resolver;
    }
}
~~~

Ví dụ này dùng cookie tên SESSION, Path /, HttpOnly, Secure và SameSite=Lax. Cần chọn các giá trị theo domain, HTTPS, kiến trúc frontend và yêu cầu cross-site thực tế. Nếu ứng dụng đã có bean HttpSessionIdResolver, hãy cấu hình tại bean hiện hữu thay vì tạo nhiều resolver cạnh tranh.

Trình duyệt nhận lệnh xóa cookie qua Set-Cookie với cùng tên và phạm vi cookie, thường là Max-Age=0 hoặc thời điểm hết hạn trong quá khứ. JavaScript không thể đọc header Set-Cookie trong browser và cũng không cần tự xóa cookie HttpOnly.

### Tên, Path và Domain phải khớp

Cookie được trình duyệt phân biệt theo tên và phạm vi domain/path. Nếu cookie ban đầu được phát với:

~~~text
Name=SESSION
Path=/portal
Domain=example.com
~~~

nhưng response logout chỉ xóa cookie cùng tên ở Path=/ hoặc host-only domain, cookie ban đầu có thể vẫn tồn tại. Vì vậy:

- Giữ nguyên cookie name.
- Dùng đúng Path đã phát.
- Dùng đúng Domain hoặc host-only policy đã phát.
- Kiểm tra nhiều cookie trùng tên ở các path khác nhau.
- Đảm bảo reverse proxy và ứng dụng thống nhất context path/domain.

HttpOnly, Secure và SameSite không phải khóa nhận diện chính của cookie, nhưng vẫn nên được giữ nhất quán theo chính sách bảo mật và hành vi browser.

## 8. Cookie clearing với Spring Security logout

Spring Security có thể xóa cookie được chỉ định trong logout DSL:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityLogoutConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .logout(logout -> logout
                .logoutUrl("/logout")
                .invalidateHttpSession(true)
                .clearAuthentication(true)
                .deleteCookies("SESSION")
            );
        return http.build();
    }
}
~~~

Đây là cấu hình khung. Nếu ứng dụng đã có SecurityFilterChain, hãy bổ sung cấu hình logout vào chain đó. deleteCookies("SESSION") tạo handler xóa cookie theo cấu hình của Spring Security; nếu cookie Spring Session dùng Path hoặc Domain tùy chỉnh, cần xác nhận handler phát đúng thuộc tính để browser xóa được cookie ban đầu.

Trong tích hợp Spring Session, invalidate session thường đã khiến HttpSessionIdResolver hết hạn định danh. Không thêm cookie clearing trùng lặp nếu không cần thiết; trước tiên kiểm tra response thực tế. Dùng deleteCookies cho cookie bổ sung như cookie giao diện hoặc cookie riêng của ứng dụng khi chúng không được resolver quản lý.

Giữ CSRF protection và dùng POST cho logout trong ứng dụng session-cookie. Không tạo GET endpoint làm thay đổi trạng thái bảo mật vì link hoặc crawler có thể kích hoạt request ngoài ý muốn.

## 9. Xóa định danh khi dùng HeaderHttpSessionIdResolver

Một số API không dùng cookie mà gửi session ID trong HTTP header, ví dụ x-auth-token. Spring Session cung cấp HeaderHttpSessionIdResolver để đọc và ghi định danh ở header:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.http.HeaderHttpSessionIdResolver;
import org.springframework.session.web.http.HttpSessionIdResolver;

@Configuration
class HeaderSessionConfiguration {

    @Bean
    HttpSessionIdResolver httpSessionIdResolver() {
        return HeaderHttpSessionIdResolver.xAuthToken();
    }
}
~~~

Client gửi header x-auth-token trong các request cần dùng session. Khi Spring Session tạo session, resolver ghi session ID vào response header. Khi session bị invalidate, resolver có thể phát giá trị header rỗng để báo cho client rằng định danh đã hết hiệu lực theo hợp đồng của resolver.

Khác với cookie HttpOnly, JavaScript hoặc ứng dụng mobile thường tự quản lý giá trị header. Client cần xóa ID đã lưu khỏi bộ nhớ hoặc secure storage khi logout hoặc khi server trả tín hiệu hết hạn. Nếu client tiếp tục gửi ID cũ, repository không tìm thấy session và ứng dụng phải yêu cầu xác thực lại.

Header chứa session ID cũng là bearer credential. Dùng HTTPS, không log header, giới hạn CORS origin và không lưu token trong localStorage nếu có thể tránh. Nếu frontend cần đọc response header tùy chỉnh qua CORS, cấu hình Access-Control-Expose-Headers cho đúng header; không mở CORS rộng cho mọi origin.

Header-based session ID không tự động được trình duyệt gửi như cookie. Điều này có thể giảm một số rủi ro CSRF do browser tự động đính kèm cookie, nhưng không thay thế authorization, kiểm soát CORS hoặc bảo vệ khỏi XSS đánh cắp credential.

## 10. So sánh cookie và header khi logout

| Đặc điểm | Cookie resolver | Header resolver |
| --- | --- | --- |
| Nơi client gửi ID | Cookie request | Header request như x-auth-token |
| Cách server phát ID | Set-Cookie | Response header |
| Cách server báo hết hạn | Cookie có Max-Age=0/Expires trong quá khứ | Header được resolver làm rỗng theo implementation |
| Client cần tự xóa? | Browser xử lý cookie; HttpOnly không cần JavaScript | Ứng dụng client phải xóa giá trị header đã lưu |
| Phạm vi gửi tự động | Browser tự gửi theo domain/path/SameSite | Client chỉ gửi khi code thêm header |
| Rủi ro cần chú ý | CSRF, cookie scope và cookie theft | XSS/token theft, CORS và header logging |

Chọn resolver theo kiến trúc client. Ứng dụng browser truyền thống thường dùng cookie HttpOnly. API client hoặc ứng dụng mobile có thể dùng header resolver nếu có quy trình lưu trữ và thu hồi credential phù hợp.

Không cấu hình cookie resolver và header resolver như hai cơ chế song song nếu chưa có thiết kế rõ. HttpSessionIdResolver là chiến lược xác định session ID; cần một resolver phù hợp và thống nhất trên mọi instance.

## 11. Thu hồi session của thiết bị khác

Khi người dùng chọn “Đăng xuất khỏi thiết bị khác”, server cần tìm session thuộc principal đã xác thực rồi xóa các ID tương ứng bằng repository. Cookie hoặc header ở thiết bị khác không thể bị xóa ngay bằng response của thiết bị hiện tại.

Một quy trình quản trị có thể:

1. Lấy principal từ Authentication của người gọi, không tin principal tùy ý từ request.
2. Kiểm tra người dùng có quyền thu hồi các session thuộc principal đó.
3. Tra cứu các session theo principal bằng indexed repository nếu implementation hỗ trợ.
4. Giữ lại ID của session hiện tại nếu nghiệp vụ chỉ muốn đăng xuất các thiết bị khác.
5. Gọi deleteById() cho các session cần thu hồi.
6. Ghi audit kết quả bằng mã tương quan, không ghi session ID.
7. Yêu cầu các thiết bị khác xử lý response 401/unauthorized hoặc tín hiệu session revoked ở request/message tiếp theo.

Kết quả tra cứu là snapshot. Một phiên mới có thể được tạo đồng thời với thao tác thu hồi. Nếu cần bảo đảm tất cả session cũ và mới đều không thể dùng sau một thời điểm, cần cơ chế thu hồi cấp tài khoản như auth version/session generation, khóa đăng nhập tạm thời hoặc kiểm tra trạng thái tài khoản ở mỗi request.

## 12. Session event và tác vụ phụ trợ

Spring Session có thể phát các sự kiện như SessionDeletedEvent khi session bị xóa và SessionExpiredEvent khi session hết hạn, tùy repository và cấu hình. Ứng dụng có thể lắng nghe để dọn metadata phụ trợ, cập nhật presence hoặc ghi audit.

Ví dụ:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.session.events.SessionDeletedEvent;
import org.springframework.stereotype.Component;

@Component
class SessionCleanupListener {

    @EventListener
    void onSessionDeleted(SessionDeletedEvent event) {
        // Dọn dữ liệu phụ trợ theo cách idempotent.
        // Không ghi session ID hoặc toàn bộ attributes vào log.
    }
}
~~~

Không coi listener event là cơ chế duy nhất để thu hồi quyền. Event có thể phụ thuộc repository, notification và trạng thái kết nối. Request phải kiểm tra session còn hợp lệ ở repository và xác thực/authorization hiện tại. Nếu một tác vụ phụ trợ quan trọng cần bảo đảm bền vững, hãy ghi nó vào hàng đợi hoặc outbox có thể retry.

Khi xóa trực tiếp bằng repository, kiểm thử xem implementation phát sự kiện nào và thời điểm nào. Không giả định mọi đường xóa, mọi backend hoặc mọi phiên bản đều phát event giống nhau.

## 13. Kiểm thử invalidate, repository deletion và identifier cleanup

Kiểm thử cần xác nhận cả ba lớp: session API, kho dữ liệu và định danh phía client.

| Kịch bản | Thao tác | Kết quả cần xác nhận |
| --- | --- | --- |
| Logout hiện tại | Gọi HttpSession.invalidate() | Session không còn tải được; response hết hạn cookie/header |
| Không có session | Gọi logout với getSession(false) | Không tạo session mới; response vẫn hoàn tất an toàn |
| Xóa một attribute | Gọi removeAttribute() | Session vẫn hợp lệ và cookie/header vẫn được giữ |
| Xóa repository theo ID | Gọi deleteById(id) | Repository không tìm thấy ID đó; client ở thiết bị khác vẫn cần xử lý ID cũ |
| Cookie path tùy chỉnh | Logout với cookie Path/Domain riêng | Browser xóa đúng cookie đã phát |
| Header resolver | Logout với x-auth-token | Response báo hết hạn theo resolver; client xóa ID đã lưu |
| Session đã bị xóa | Gửi lại cookie/header cũ | Server không khôi phục session; yêu cầu xác thực lại |
| Hai request đồng thời | Một request đang chạy khi admin xóa session | Xác định có nguy cơ request đang chạy lưu lại session hay không |
| Logout Spring Security | Gửi POST logout | Authentication bị xóa, session invalidate và cookie được xử lý |
| Nhiều instance | Xóa ở instance A, request sau đến B | B không chấp nhận session đã bị thu hồi |

Với Redis hoặc JDBC, dùng repository test thật hoặc Testcontainers để xác nhận dữ liệu thực sự bị xóa. Mock HttpSession.invalidate() không chứng minh key Redis hoặc bản ghi JDBC đã biến mất.

Khi kiểm thử cookie, kiểm tra header Set-Cookie gồm tên, Path, Domain, Max-Age/Expires, Secure, HttpOnly và SameSite. Khi kiểm thử header resolver, kiểm tra response header và hành vi client xóa ID cũ.

## 14. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Logout xong browser vẫn gửi cookie | Cookie chưa được expire hoặc Path/Domain không khớp | Kiểm tra Set-Cookie và serializer |
| Cookie đã mất nhưng session vẫn tồn tại | Chỉ xóa cookie, chưa invalidate session | Gọi logout handler/invalidate ở server |
| deleteById() xong thiết bị khác vẫn gửi ID cũ | Client chưa nhận response xóa định danh | Từ chối session cũ và yêu cầu client xóa khi nhận lỗi |
| Session xuất hiện lại sau khi admin xóa | Request đang chạy có thể lưu session sau thao tác delete | Dùng generation/revocation check và kiểm thử race |
| Gọi invalidate gây IllegalStateException | Code tiếp tục truy cập session đã invalid hoặc invalidate lặp | Không dùng session object sau invalidate; kiểm tra getSession(false) |
| Header ID không bị xóa ở client | Client không xử lý response header rỗng | Cập nhật client logout flow và kiểm tra header resolver |
| Logout Spring Security không xóa cookie tùy chỉnh | Handler xóa cookie không khớp Path/Domain hoặc resolver đã quản lý riêng | Kiểm tra response và cấu hình một nguồn xóa định danh |
| Event cleanup không chạy | Repository/configuration không phát event như giả định | Kiểm tra implementation và không phụ thuộc event cho quyền truy cập |

## 15. Nguyên tắc triển khai

- Dùng HttpSession.invalidate() hoặc Spring Security logout cho phiên hiện tại.
- Dùng SessionRepository.deleteById() cho thao tác thu hồi theo ID ở phía server, sau khi xác minh quyền.
- Phân biệt xóa attribute với invalidate toàn bộ session.
- Để SessionRepositoryFilter và HttpSessionIdResolver phối hợp lưu/xóa định danh trong response.
- Với cookie, giữ đúng tên, Path và Domain khi expire.
- Với header resolver, phát tín hiệu hết hạn và yêu cầu client xóa ID đã lưu.
- Không giả định xóa repository từ xa có thể xóa cookie trên thiết bị khác ngay lập tức.
- Xử lý race giữa request đang chạy và thao tác thu hồi; dùng auth version/session generation nếu cần bảo đảm mạnh.
- Kiểm thử cả session store, response identifier, logout và nhiều instance.
- Không ghi session ID, cookie hoặc session attributes nhạy cảm vào log.

invalidate() kết thúc phiên qua API HttpSession; deleteById() xóa bản ghi theo ID ở repository; cookie/header cleanup khiến client ngừng gửi định danh cũ. Một quy trình logout hoặc thu hồi đáng tin cậy cần phối hợp cả trạng thái phía server và định danh phía client. Với Spring Session, hãy dùng resolver và filter đúng cách, kiểm thử cookie/header thực tế, đồng thời tính đến request đang chạy và các thiết bị khác trong hệ thống nhiều instance.
