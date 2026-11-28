# Thuộc tính, thời gian truy cập, đổi định danh và invalidate

Trong ứng dụng Spring WebFlux, session được biểu diễn bằng WebSession và được thao tác theo mô hình reactive. Thay vì gọi API Servlet đồng bộ như HttpSession, mã WebFlux nhận một Mono<WebSession> từ ServerWebExchange rồi đọc hoặc cập nhật trạng thái trong chuỗi reactive. Spring Session có thể lưu WebSession vào kho chia sẻ như Redis để nhiều instance cùng truy cập phiên.

Các thao tác vòng đời thường gặp gồm đọc và ghi thuộc tính, kiểm tra thời gian truy cập gần nhất, đặt idle timeout, đổi session ID và vô hiệu hóa phiên. Những thao tác này ảnh hưởng đến xác thực, bảo mật và trạng thái người dùng. Vì vậy, cần hiểu cả ý nghĩa của API WebSession lẫn cách các thao tác reactive được thực thi và lưu xuống repository.

## 1. WebSession trong WebFlux

WebSession là abstraction session của Spring WebFlux. Một WebSession có:

- ID dùng để nhận diện phiên.
- Creation time ghi nhận thời điểm tạo.
- Last access time ghi nhận lần truy cập gần nhất.
- Max idle time quy định khoảng không hoạt động tối đa.
- Map attributes lưu trạng thái ứng dụng.
- Các thao tác reactive để đổi ID, invalidate và lưu phiên.

Trong WebFlux, ServerWebExchange cung cấp session thông qua exchange.getSession(), trả về Mono<WebSession>. Mã ứng dụng cần tiếp tục xử lý trong các toán tử reactive như map, flatMap, doOnNext hoặc then.

Luồng cơ bản:

~~~mermaid
flowchart TD
    A["HTTP request mang cookie session ID"] --> B["WebSessionManager"]
    B --> C["WebSessionIdResolver đọc ID"]
    C --> D["WebSessionStore / Spring Session repository"]
    D --> E["Mono<WebSession>"]
    E --> F["Controller hoặc WebFilter"]
    F --> G["Đọc hoặc cập nhật attributes"]
    F --> H["Đổi ID hoặc invalidate"]
    G --> I["WebSessionManager lưu khi response hoàn tất"]
    H --> I
    I --> J["Response và cookie session"]
~~~

Spring Session WebFlux tích hợp với WebSessionManager và WebSessionStore. Repository cụ thể có thể là kho trong bộ nhớ để thử nghiệm hoặc repository Redis reactive để chia sẻ dữ liệu giữa nhiều instance. Trình duyệt vẫn gửi session ID qua cookie; repository giữ dữ liệu phiên phía server.

Không dùng HttpSession hoặc SessionRepositoryFilter kiểu Servlet trong WebFlux thuần. Hai stack có API và vòng đời xử lý khác nhau. Ứng dụng cần dùng WebSession và cơ chế reactive tương ứng.

## 2. Truy cập session mà không chặn luồng

Ví dụ đọc một số thuộc tính và thời điểm truy cập:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class SessionInfoController {

    @GetMapping("/api/session/info")
    Mono<Map<String, String>> sessionInfo(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            String theme = session.getAttribute("theme");
            return Map.of(
                "theme", theme == null ? "system" : theme,
                "createdAt", session.getCreationTime().toString(),
                "lastAccessAt", session.getLastAccessTime().toString()
            );
        });
    }
}
~~~

Không trả session ID cho frontend chỉ để hiển thị thông tin phiên. ID là credential nhạy cảm và nên được trình duyệt quản lý qua cookie HttpOnly.

exchange.getSession() trả về Mono nên phần truy cập session chỉ chạy khi chuỗi reactive được subscribe. Trong controller WebFlux, framework subscribe vào publisher trả về từ handler. Không gọi block() để lấy WebSession bên trong controller hoặc WebFilter; block có thể chặn event loop và làm giảm khả năng xử lý đồng thời.

Một endpoint chỉ gọi exchange.getSession() có thể yêu cầu WebFlux tìm hoặc tạo một WebSession. Tuy nhiên, việc lấy session chưa nhất thiết đồng nghĩa phiên mới đã được lưu hoặc cookie mới đã được phát hành. Session thường được lưu khi nó được bắt đầu hoặc có thay đổi cần lưu theo cơ chế của WebSessionManager. Nếu endpoint không cần trạng thái, tránh tạo hoặc làm thay đổi session không cần thiết.

## 3. Đọc và ghi thuộc tính session

WebSession cung cấp Map thông qua getAttributes(). Có thể lấy giá trị bằng key và đặt giá trị mới bằng put:

~~~java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

record PreferenceRequest(String theme, String locale) {}

@PostMapping("/api/session/preferences")
Mono<Void> updatePreferences(
        @RequestBody Mono<PreferenceRequest> requestBody,
        ServerWebExchange exchange) {

    return requestBody.flatMap(request ->
        exchange.getSession().doOnNext(session -> {
            session.getAttributes().put("theme", request.theme());
            session.getAttributes().put("locale", request.locale());
        }).then()
    );
}
~~~

Khi cần xóa một thuộc tính, dùng remove:

~~~java
return exchange.getSession()
    .doOnNext(session -> session.getAttributes().remove("temporaryState"))
    .then();
~~~

Các thuộc tính session là trạng thái phía server. Chỉ lưu dữ liệu nhỏ, cần thiết và có thể serialize bằng repository đã cấu hình. Với Redis, kiểu dữ liệu cần tương thích với serializer; nếu các instance chạy nhiều phiên bản, dữ liệu phải đọc được giữa những phiên bản đó.

Không lưu trực tiếp ServerWebExchange, ServerHttpRequest, ServerHttpResponse, DataBuffer, Flux, Mono, Netty channel, connection hoặc đối tượng gắn với một request. Những đối tượng này thường có vòng đời ngắn, không phù hợp để lưu qua nhiều request và có thể không serialize được.

Đối với dữ liệu có cấu trúc, nên dùng DTO nhỏ với tên field và kiểu dữ liệu ổn định. Dữ liệu nghiệp vụ quan trọng như đơn hàng, quyền tài khoản hoặc số dư phải được lưu trong kho dữ liệu nghiệp vụ; session chỉ nên giữ tham chiếu hoặc trạng thái tạm thời phù hợp.

## 4. Creation time và last access time

WebSession cung cấp hai mốc thời gian:

- getCreationTime(): thời điểm session được tạo.
- getLastAccessTime(): thời điểm gần nhất session được hệ thống ghi nhận là đã được truy cập.

Last access time được dùng để đánh giá idle timeout. Khi một request lấy session qua WebSessionManager, thời điểm truy cập được cập nhật theo vòng đời session. Nếu session không được truy cập trong khoảng max idle time, nó có thể hết hạn và không còn được xem là hợp lệ.

Không nên tự cập nhật last access time bằng cách lưu một thuộc tính do ứng dụng đặt. WebSessionManager và repository chịu trách nhiệm theo dõi thời gian truy cập. Một endpoint kiểm tra trạng thái session cũng có thể được xem là một lần truy cập và làm mới idle timeout, tùy cách request lấy session và repository triển khai.

Last access time không phải thời điểm xác thực thành công gần nhất và cũng không phải absolute lifetime. Nếu nghiệp vụ yêu cầu đăng nhập lại sau một khoảng thời gian tuyệt đối, ứng dụng cần lưu mốc xác thực riêng và kiểm tra chính sách đó độc lập với idle timeout.

Ví dụ ghi nhận thời gian để trả về thông tin phiên:

~~~java
Mono<String> lastAccessTime(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> session.getLastAccessTime().toString());
}
~~~

Tránh dùng last access time làm căn cứ duy nhất cho các quyết định bảo mật có yêu cầu chính xác cao. Đồng hồ hệ thống, độ trễ request, cách repository cập nhật và thời điểm response được lưu đều có thể ảnh hưởng quan sát thực tế.

## 5. Đặt max idle time cho một session

WebSession cho phép đặt thời gian không hoạt động tối đa bằng setMaxIdleTime(Duration):

~~~java
import java.time.Duration;

Mono<Void> shortenSessionTimeout(ServerWebExchange exchange) {
    return exchange.getSession()
        .doOnNext(session ->
            session.setMaxIdleTime(Duration.ofMinutes(15))
        )
        .then();
}
~~~

Trong ví dụ, session được đặt idle timeout 15 phút. Nếu session không được truy cập trong khoảng thời gian đó, repository có thể coi phiên đã hết hạn. Giá trị này có thể được lưu cùng session tùy repository và integration.

Có thể đọc lại giá trị qua getMaxIdleTime():

~~~java
Mono<Duration> currentIdleTimeout(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> session.getMaxIdleTime());
}
~~~

Đối với chính sách chung, nên cấu hình timeout mặc định ở cấu hình Spring Boot/Spring Session nếu phiên bản đang dùng hỗ trợ. Timeout riêng trên WebSession phù hợp khi một nhóm luồng nghiệp vụ cần chính sách ngắn hơn hoặc dài hơn, ví dụ một quy trình nhạy cảm.

Khi đặt timeout:

- Chọn khoảng thời gian phù hợp với độ nhạy của dữ liệu và trải nghiệm người dùng.
- Không đặt thời hạn vô hạn nếu không có chính sách thu hồi và dọn phiên rõ ràng.
- Không nhầm idle timeout với thời hạn tuyệt đối của phiên.
- Kiểm thử việc truy cập session làm mới last access time theo mong đợi.
- Kiểm tra TTL thực tế trong repository reactive đang sử dụng.

Nếu một session có thời hạn ngắn hơn timeout mặc định, hãy kiểm thử trên mọi instance để bảo đảm chính sách được áp dụng nhất quán. Không để mỗi replica tự đặt timeout khác nhau cho cùng một loại session.

## 6. Đổi session ID bằng changeSessionId

WebSession cung cấp changeSessionId() để thay ID của phiên hiện tại. Đây là thao tác quan trọng sau khi xác thực thành công hoặc tại một thời điểm cần giảm rủi ro session fixation.

Session fixation xảy ra khi kẻ tấn công biết hoặc kiểm soát được session ID trước khi nạn nhân đăng nhập, rồi tìm cách tiếp tục sử dụng ID đó sau khi người dùng đã xác thực. Đổi ID sau xác thực giúp tách phiên trước đăng nhập khỏi phiên đã xác thực.

Ví dụ:

~~~java
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

Mono<Void> rotateSessionId(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::changeSessionId);
}
~~~

changeSessionId() trả về Mono<Void>. Phải đưa publisher này vào chuỗi reactive được trả về hoặc được compose; nếu chỉ gọi method mà không subscribe/compose, thao tác có thể không được thực thi.

Sau khi ID thay đổi, WebSessionManager cùng WebSessionIdResolver cập nhật cookie trong response theo cơ chế tích hợp. Frontend không cần tự đọc ID mới từ Set-Cookie. JavaScript không được phép đọc header Set-Cookie và không nên lưu session ID vào localStorage hoặc sessionStorage.

Đổi ID không đồng nghĩa với đổi người dùng, xác thực lại hoặc thay đổi quyền. Nó chỉ thay định danh phiên. Ứng dụng vẫn phải xác thực danh tính và kiểm tra quyền ở backend.

### Kết hợp với Spring Security

Nếu dùng Spring Security WebFlux, cơ chế quản lý session fixation của security stack có thể đã thực hiện đổi session ID trong quá trình xác thực. Hãy kiểm tra chiến lược session fixation và logout đang cấu hình trước khi tự gọi changeSessionId thêm lần nữa.

Không nên xoay ID tùy tiện ở mọi request. Đổi ID tại các ranh giới bảo mật có ý nghĩa, như sau đăng nhập hoặc nâng cấp mức xác thực, và kiểm thử để tránh cookie hoặc session state bị cập nhật hai lần ngoài dự kiến.

## 7. Invalidate session

invalidate() làm phiên hiện tại không còn hợp lệ. Đây là thao tác cần thực hiện khi người dùng đăng xuất hoặc khi ứng dụng thu hồi một phiên:

~~~java
Mono<Void> invalidateSession(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::invalidate);
}
~~~

Đây là API reactive, vì vậy phải compose Mono<Void> vào response pipeline. Không gọi invalidate() rồi bỏ qua publisher. Khi invalidate hoàn tất, session không còn được sử dụng như một phiên hợp lệ.

WebSessionManager và WebSessionIdResolver phối hợp để xử lý session ID ở response. Cookie phía trình duyệt cần được hết hạn/xóa theo phạm vi cookie đã phát hành. Nếu ứng dụng tự cấu hình resolver, cần kiểm tra cookie name, Path và Domain để thao tác logout xóa đúng cookie.

Invalidate session phía server và xóa cookie phía trình duyệt là hai phần của logout:

1. Repository xóa hoặc vô hiệu hóa dữ liệu session.
2. Response làm hết hạn cookie chứa session ID.

Chỉ xóa cookie mà không vô hiệu hóa session phía server có thể để lại phiên còn hiệu lực nếu ID bị lộ. Ngược lại, nếu server đã invalidate nhưng cookie cũ còn trong browser, request tiếp theo vẫn có thể gửi ID cũ; repository phải từ chối ID đó và ứng dụng có thể tạo phiên mới nếu luồng xử lý yêu cầu.

### Logout với Spring Security WebFlux

Trong ứng dụng có Spring Security, nên cấu hình logout handler để xóa SecurityContext và invalidate WebSession theo đúng security flow. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {
        return http
            .logout(logout -> logout
                .logoutUrl("/logout")
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated()
            )
            .build();
    }
}
~~~

Đây là cấu hình khung minh họa; xác thực, CSRF, CORS và các quyền truy cập cần được cấu hình theo ứng dụng. Spring Security WebFlux có logout handler tích hợp để xử lý session và security context. Không xây dựng endpoint logout thủ công nếu nó bỏ qua các handler bảo mật đang có.

## 8. Cookie và WebSessionIdResolver

WebSessionIdResolver quyết định cách lấy session ID từ request và cách ghi/xóa ID trên response. Với cookie, Spring Session WebFlux cung cấp CookieWebSessionIdResolver.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.web.server.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class WebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(builder -> builder
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
        );
        return resolver;
    }
}
~~~

Ví dụ dùng cookie tên SESSION, Path /, HttpOnly, Secure và SameSite=Lax. Chỉ bật Secure khi request production đi qua HTTPS; môi trường local HTTP cần cấu hình riêng. Chọn SameSite theo luồng điều hướng và xác thực cross-site của ứng dụng.

Không đưa session ID vào URL hoặc query parameter. Cookie nên được bảo vệ bằng HTTPS, HttpOnly và chính sách SameSite phù hợp. Nếu frontend gọi API cross-origin bằng cookie, cần cấu hình CORS credentials và cookie theo đúng origin/site; CORS không thay thế CSRF protection.

## 9. Lưu session và vòng đời response

WebSession hoạt động theo mô hình reactive. WebSessionManager thường điều phối việc tải session trước khi xử lý request và lưu các thay đổi khi response hoàn tất. Ứng dụng thường chỉ cần cập nhật attributes trong reactive chain; không cần tự gọi save() sau mọi lần put.

WebSession có API save() trả về Mono<Void> cho trường hợp cần yêu cầu lưu tường minh theo hợp đồng của phiên bản. Tuy nhiên, không gọi save() tùy tiện trong mọi controller vì WebSessionManager đã quản lý vòng đời lưu thông thường. Nếu cần save tường minh, phải compose publisher và hiểu tác động của repository, response commit và trạng thái session.

Một số trạng thái cần phân biệt:

- isStarted(): cho biết session đã được bắt đầu theo trạng thái WebSession.
- isExpired(): cho biết session đã hết hạn theo thời gian idle.
- save(): yêu cầu lưu session theo implementation.
- invalidate(): kết thúc phiên.

Không dựa vào việc gọi getSession() là bằng chứng session mới đã được ghi vào kho. Session mới có thể chưa được bắt đầu nếu chưa có thuộc tính hoặc thao tác làm nó cần lưu. Hãy kiểm thử cookie và repository thay vì suy luận từ việc Mono<WebSession> đã phát giá trị.

## 10. Xử lý cập nhật đồng thời

Session có thể được đọc và cập nhật bởi nhiều request cùng lúc. Ví dụ người dùng mở hai tab, cả hai request cùng đọc một thuộc tính cart, thay đổi rồi ghi lại. Nếu thao tác không được điều phối, cập nhật sau có thể ghi đè cập nhật trước.

Reactive không tự động làm cho session mutable trở nên thread-safe. Tránh chạy nhiều nhánh song song cùng sửa một WebSession hoặc cùng một object mutable trong attributes. Nếu cần cập nhật dữ liệu có tính nhất quán cao, nên đặt dữ liệu đó trong service/repository nghiệp vụ có transaction hoặc cơ chế đồng bộ thích hợp.

Một số nguyên tắc:

- Giữ thao tác đọc/ghi session ngắn và tuần tự trong một pipeline khi có thể.
- Không chia sẻ mutable session object giữa các publisher chạy song song.
- Không dùng session làm nơi lưu bộ đếm giao dịch cần tính chính xác khi có request đồng thời.
- Với dữ liệu quan trọng, dùng database nghiệp vụ và optimistic locking/transaction phù hợp.
- Kiểm thử hai request đồng thời cập nhật cùng thuộc tính để phát hiện lost update.

## 11. Kiểm thử thuộc tính, thời gian truy cập và invalidate

Nên dùng WebTestClient để kiểm thử endpoint reactive và xác nhận cookie được phát hành, gửi lại, đổi ID hoặc xóa khi cần.

Các kịch bản chính:

| Kịch bản | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Đọc session mới | Gọi endpoint chỉ đọc session | Không có thuộc tính nghiệp vụ nếu chưa được đặt |
| Ghi thuộc tính | Gửi request cập nhật theme hoặc locale | Request sau đọc lại được giá trị |
| Last access time | Gửi nhiều request có cùng cookie | Thời gian truy cập được cập nhật theo chính sách repository |
| Idle timeout | Đặt timeout ngắn rồi chờ quá hạn | Session không còn hợp lệ |
| Đổi ID | Gọi endpoint rotate sau xác thực | Response cấp cookie session ID mới |
| Invalidate | Gọi logout | Repository không còn session hợp lệ và cookie được xóa |
| Nhiều instance | Ghi ở instance A, đọc ở instance B | Cùng repository trả về cùng trạng thái |
| Request đồng thời | Hai request cập nhật cùng thuộc tính | Hành vi không tạo mất cập nhật ngoài dự kiến |

Khi kiểm thử cookie:

1. Đọc cookie từ response đầu tiên.
2. Gửi cookie đó trong request tiếp theo.
3. Sau changeSessionId, xác nhận response phát cookie mới và ID cũ không còn được chấp nhận.
4. Sau invalidate, xác nhận response hết hạn cookie và repository không tìm thấy phiên cũ.

Không ghi giá trị cookie hoặc session ID thật vào log kiểm thử dùng chung. Dùng dữ liệu giả và repository test riêng.

## 12. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Thuộc tính vừa đặt không xuất hiện ở request sau | Publisher không được compose, session chưa được lưu hoặc serializer lỗi | Trả về publisher đúng cách và kiểm tra repository |
| WebFlux bị chậm hoặc treo | Gọi block() trong event loop | Dùng flatMap/map/then và API non-blocking |
| Session ID không đổi sau đăng nhập | Không compose changeSessionId hoặc security strategy chưa cấu hình | Kiểm tra publisher và Spring Security session fixation |
| Logout xong vẫn có cookie | Resolver không xóa cookie đúng Path/Domain hoặc logout handler chưa chạy | Kiểm tra response Set-Cookie và cấu hình resolver |
| Session hết hạn sớm | Max idle time quá ngắn hoặc TTL repository không đồng nhất | Kiểm tra timeout toàn cục và timeout theo session |
| Một instance thấy dữ liệu, instance khác không thấy | Các instance không dùng cùng repository hoặc serializer | Kiểm tra Redis endpoint, namespace và serializer |
| Thuộc tính bị mất khi hai request đồng thời | Lost update do cùng sửa trạng thái mutable | Dùng cập nhật tuần tự hoặc kho nghiệp vụ có đồng bộ |

Khi điều tra, kiểm tra cả reactive chain và repository. Một thao tác trả về Mono nhưng không được compose có thể chưa bao giờ chạy. Đồng thời, kiểm tra cookie thực tế ở request/response, timeout và cấu hình store; không chỉ xem trạng thái trong một instance.

## 13. Nguyên tắc sử dụng

- Dùng WebSession và ServerWebExchange trong WebFlux thay vì HttpSession Servlet.
- Lấy session qua exchange.getSession() và tiếp tục trong Mono/WebFlux pipeline.
- Đọc, ghi hoặc xóa thuộc tính qua getAttributes().
- Dùng getCreationTime và getLastAccessTime để quan sát vòng đời; không nhầm idle timeout với absolute lifetime.
- Đặt timeout bằng setMaxIdleTime(Duration) khi cần chính sách riêng.
- Dùng changeSessionId sau ranh giới xác thực phù hợp và compose Mono<Void>.
- Dùng invalidate khi kết thúc phiên; kết hợp logout handler của Spring Security nếu có.
- Để WebSessionManager và WebSessionIdResolver quản lý lưu session và cookie.
- Không gọi block() hoặc đưa session ID vào JavaScript storage.
- Kiểm thử cookie, timeout, đổi ID, invalidate và cập nhật đồng thời trên repository thực.

WebSession cung cấp các thao tác vòng đời phiên theo mô hình reactive: attributes giữ trạng thái ứng dụng, last access time và max idle time quản lý thời gian không hoạt động, changeSessionId thay định danh để hỗ trợ chống session fixation, còn invalidate kết thúc phiên. Khi các publisher được compose đúng cách và repository reactive được dùng chung giữa các instance, Spring WebFlux có thể quản lý session phân tán mà không chặn event loop và vẫn duy trì hành vi xác thực nhất quán.
