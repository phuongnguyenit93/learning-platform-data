# WebTestClient và phạm vi kiểm thử WebSession

Spring WebFlux dùng WebSession để giữ trạng thái giữa các request trong ứng dụng reactive. Khi tích hợp Spring Session, WebSession được lưu qua một reactive session repository dùng chung, chẳng hạn Redis, để nhiều instance có thể khôi phục cùng phiên. WebTestClient cho phép kiểm thử request/response WebFlux, cookie, filter, controller và vòng đời WebSession mà không cần viết client mạng riêng.

Điểm quan trọng khi kiểm thử là chọn đúng phạm vi. Một test chỉ bind vào controller có thể đang dùng WebSession store mặc định trong bộ nhớ và không hề đi qua Spring Session. Test đó hữu ích cho logic controller, nhưng không chứng minh Redis repository, cookie resolver hoặc tính nhất quán giữa các instance hoạt động đúng. Bài học này phân biệt các cấp kiểm thử, chỉ cách giữ cookie giữa các request, kiểm tra tạo/sửa/hết hạn/invalidate WebSession và xác minh tích hợp reactive session store.

## 1. WebSession trong Spring WebFlux là gì?

WebSession là abstraction session của Spring WebFlux, thuộc package org.springframework.web.server. Nó cung cấp trạng thái theo từng client qua nhiều request và có các thao tác như:

- getId(): lấy định danh hiện tại của session.
- getAttributes(): đọc và thay đổi các thuộc tính session.
- start(): đánh dấu session cần được tạo nếu chưa tồn tại.
- changeSessionId(): thay định danh session, trả về Mono<Void>.
- invalidate(): vô hiệu hóa session, trả về Mono<Void>.
- save(): yêu cầu lưu session, trả về Mono<Void>.
- getCreationTime(), getLastAccessTime() và getMaxIdleTime(): xem metadata vòng đời.
- setMaxIdleTime(Duration): thay đổi thời gian không hoạt động tối đa.

WebSession không phải javax.servlet.http.HttpSession hoặc jakarta.servlet.http.HttpSession. Ứng dụng WebFlux dùng WebSession và WebSessionManager; ứng dụng Servlet dùng HttpSession và filter/repository tương ứng. Không lấy một test WebFlux rồi kết luận rằng SessionRepositoryFilter, servlet cookie configuration hoặc JDBC Servlet repository đã được kiểm thử.

Trong kiến trúc reactive, Spring Session tích hợp qua ReactiveSessionRepository và cơ chế WebSessionStore của WebFlux. Repository reactive chịu trách nhiệm đọc/ghi session bằng các publisher reactive. Các thao tác lưu trữ phải được compose trong Reactor pipeline; không chặn event loop bằng JDBC blocking call.

## 2. WebTestClient kiểm thử những gì?

WebTestClient là client kiểm thử theo mô hình HTTP. Nó gửi request và cho phép xác minh status, header, cookie, body và lỗi. Có thể bind với các phạm vi khác nhau:

| Cách tạo client | Phạm vi | Điều có thể xác minh |
|---|---|---|
| bindToController(...) | Controller được chọn và hạ tầng WebFlux tối thiểu | Mapping, response và logic handler |
| bindToRouterFunction(...) | Functional endpoints | Router function và handler |
| bindToApplicationContext(...) | WebFlux application context | Handler mapping, WebFilter, WebSessionManager và cấu hình được import |
| bindToServer() | Server đang chạy | HTTP thật, cookie, proxy, network và cấu hình triển khai |
| Spring Boot với RANDOM_PORT và WebTestClient | Ứng dụng khởi động đầy đủ trên cổng ngẫu nhiên | Auto-configuration và session repository thật nếu đã cấu hình |

Phạm vi test quyết định điều gì được chứng minh. bindToController thường phù hợp với unit/slice test, nhưng có thể dùng store mặc định trong bộ nhớ. Muốn xác minh Spring Session reactive repository, hãy bind vào ApplicationContext có cấu hình repository hoặc khởi động ứng dụng đầy đủ với store kiểm thử thật.

WebTestClient có thể được dùng trong một số kịch bản kiểm thử Spring MVC thông qua MockMvcWebTestClient. Tuy nhiên, bài học này nói về WebFlux và WebSession; việc dùng WebTestClient không tự biến HttpSession thành WebSession.

## 3. Chọn test slice hay integration test?

Một chiến lược hợp lý chia kiểm thử thành các lớp:

1. **Unit test handler/service:** kiểm tra logic nghiệp vụ và phản hồi với session được giả lập hoặc store test.
2. **WebFlux slice test:** kiểm tra routing, codec, WebFilter và controller trong phạm vi được nạp.
3. **WebSession integration test:** nạp WebSessionManager và Spring Session reactive repository để kiểm tra cookie round-trip, save, lookup, invalidate và expiration.
4. **Multi-instance test:** khởi động hai ứng dụng dùng chung store và xác minh node thứ hai đọc được session do node thứ nhất tạo.
5. **Deployment smoke test:** gửi request qua reverse proxy hoặc ingress để kiểm tra cookie, TLS, path và header ngoài môi trường test.

Không cần chạy tất cả các lớp cho mọi thay đổi. Sửa logic controller có thể chỉ cần unit/slice test; thay đổi session repository, cookie resolver hoặc serialization cần integration test tương ứng.

### 3.1. Lưu ý với @WebFluxTest

@WebFluxTest thường chỉ nạp một phần cấu hình WebFlux và các controller được chọn. Cấu hình Spring Session reactive có thể không được tự động nạp vào slice. Khi đó, test vẫn tạo và đọc WebSession, nhưng dùng store mặc định thay vì repository mà production sử dụng.

Nếu muốn giữ slice test, import rõ cấu hình session liên quan hoặc mock abstraction mà controller phụ thuộc. Nếu mục tiêu là xác minh Spring Session repository, ưu tiên test ApplicationContext đầy đủ và store thật. Hãy xác nhận trong test rằng bean/session manager đang dùng đúng implementation dự kiến; chỉ kiểm tra endpoint trả 200 là chưa đủ.

## 4. Cấu hình WebFlux với Spring Session reactive

Ví dụ dùng Redis reactive:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession
public class ReactiveSessionConfiguration {
}
~~~

Annotation này bật tích hợp Spring Session cho WebFlux và cấu hình reactive Redis session repository theo phiên bản tương ứng. Trong Spring Boot, có thể dùng auto-configuration và các thuộc tính spring.session.redis thay cho cấu hình thủ công.

Điều kiện quan trọng:

- Ứng dụng thực sự chạy WebFlux, có WebSessionManager.
- Dependency Spring Session reactive phù hợp với dòng Spring Framework/Spring Boot.
- Redis endpoint, credentials, TLS và namespace được cấu hình cho môi trường test.
- Các node dùng cùng namespace và định dạng dữ liệu.
- Cookie resolver dùng tên cookie, path, domain và thuộc tính bảo mật mà test mong đợi.

Không giả định Spring Session JDBC Servlet repository có thể được cắm trực tiếp vào WebFlux. JdbcIndexedSessionRepository là repository đồng bộ dành cho Servlet session; WebSession cần reactive repository. Nếu hệ thống bắt buộc dùng JDBC, hãy thiết kế adapter reactive có kiểm soát hoặc chọn kiến trúc phù hợp, tránh gọi JDBC blocking trực tiếp trên event loop. Một adapter tự viết cần giải quyết transaction, backpressure, thread scheduling và semantics của WebSession.

## 5. Tạo endpoint kiểm thử WebSession

Để kiểm tra session qua nhiều request, có thể tạo endpoint test-only tăng một bộ đếm trong WebSession:

~~~java
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
class SessionTestController {

    @GetMapping("/test/session/count")
    Mono<Map<String, Integer>> count(ServerWebExchange exchange) {
        return exchange.getSession().map(session -> {
            session.start();
            Integer previous = (Integer) session.getAttributes().get("count");
            int next = previous == null ? 1 : previous + 1;
            session.getAttributes().put("count", next);
            return Map.of("count", next);
        });
    }

    @PostMapping("/test/session/invalidate")
    Mono<Void> invalidate(ServerWebExchange exchange) {
        return exchange.getSession().flatMap(WebSession::invalidate);
    }
}
~~~

Đây là endpoint fixture cho test, không phải API production. Nó chủ động start session, cập nhật attribute và trả bộ đếm. WebFlux lưu WebSession theo vòng đời response; sau khi response hoàn tất, session manager thực hiện lưu cần thiết và resolver có thể ghi cookie session vào response.

Không trả session ID trong body để tiện debug. Test có thể đọc cookie từ response và gửi lại cookie ở request tiếp theo. Nếu cần kiểm tra rotation, hãy so sánh cookie trước/sau nhưng không in giá trị cookie vào log.

## 6. Giữ cookie giữa các request WebTestClient

WebTestClient không nên được xem như trình duyệt có cookie jar tự động dùng chung cho mọi exchange. Trong test session, hãy chủ động lấy cookie từ response đầu tiên rồi gửi lại ở request kế tiếp. Tên cookie phải lấy từ cấu hình thực tế; Spring Session WebFlux thường dùng tên SESSION mặc định, nhưng ứng dụng có thể đổi tên.

Ví dụ:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;

class WebSessionIntegrationTests {

    private static final String SESSION_COOKIE = "SESSION";

    @Autowired
    private WebTestClient client;

    @Test
    void keepsSessionAcrossRequests() {
        EntityExchangeResult<byte[]> first = this.client.get()
            .uri("/test/session/count")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.count").isEqualTo(1)
            .returnResult();

        ResponseCookie cookie =
            first.getResponseCookies().getFirst(SESSION_COOKIE);
        assertThat(cookie).isNotNull();

        this.client.get()
            .uri("/test/session/count")
            .cookie(SESSION_COOKIE, cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.count").isEqualTo(2);
    }
}
~~~

Đoạn mã giả định đã inject WebTestClient và cookie name khớp cấu hình. Trong một test fixture thực tế, có thể dùng constructor injection với JUnit/Spring extension hoặc field injection theo cấu hình test. Không hard-code SESSION nếu ứng dụng đã đổi cookie name.

ResponseCookie trong test chỉ nên được giữ trong bộ nhớ của test. Không ghi cookie.getValue() ra console, assertion message, report hoặc CI artifact. Cookie session là thông tin truy cập.

### 6.1. Tách cookie theo từng test

Mỗi test nên tạo session riêng. Không dùng một cookie tĩnh cho toàn bộ test suite vì test có thể chạy song song hoặc làm thay đổi trạng thái của test khác. Nếu cần helper, hãy tạo một đối tượng nhỏ lưu tên cookie và giá trị cookie trong phạm vi một test method.

Khi kiểm thử với store thật, dùng namespace riêng cho test run hoặc dữ liệu có định danh riêng. Không flush toàn bộ Redis database dùng chung hoặc xóa toàn bộ session của môi trường tích hợp khác.

## 7. Kiểm tra tạo session và thuộc tính

Các assertion cơ bản:

- Request đầu tiên tạo session khi handler gọi start() hoặc thêm attribute.
- Response có Set-Cookie với cookie name được cấu hình.
- Request thứ hai gửi lại cookie và nhận được giá trị attribute đã lưu.
- Hai client không chia sẻ cookie sẽ nhận trạng thái session riêng.
- Attribute bị xóa không còn xuất hiện ở request tiếp theo.

Có thể kiểm tra cookie tồn tại bằng:

~~~java
client.get()
    .uri("/test/session/count")
    .exchange()
    .expectStatus().isOk()
    .expectCookie().exists("SESSION");
~~~

Tên SESSION chỉ là ví dụ. Trong test thực tế, lấy tên cookie từ cùng cấu hình mà ứng dụng dùng. Nếu endpoint không start session hoặc không thay đổi attribute, response có thể không tạo cookie mới; điều đó không nhất thiết là lỗi.

Đừng assert toàn bộ giá trị cookie bằng một chuỗi cố định. Session ID được sinh ngẫu nhiên nên mỗi test run có giá trị khác nhau. Hãy kiểm tra cookie tồn tại, thuộc tính bảo mật và việc round-trip hoạt động.

## 8. Kiểm tra WebSession.invalidate()

Invalidate phải làm cho session hiện tại không còn được khôi phục như một session hợp lệ. Test nên:

1. Gọi endpoint count để tạo session và lấy cookie.
2. Gửi cookie tới endpoint invalidate.
3. Gửi lại cookie cũ tới endpoint count.
4. Xác nhận server tạo một session mới và bộ đếm bắt đầu lại.
5. Kiểm tra cookie/response theo chính sách resolver của ứng dụng.

Ví dụ:

~~~java
client.post()
    .uri("/test/session/invalidate")
    .cookie(cookieName, oldCookieValue)
    .exchange()
    .expectStatus().isOk();

client.get()
    .uri("/test/session/count")
    .cookie(cookieName, oldCookieValue)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.count").isEqualTo(1);
~~~

Ví dụ giả định endpoint invalidate trả response 200 và request sau tạo session mới. Nếu ứng dụng dùng logout endpoint có CSRF, redirect hoặc status khác, hãy kiểm tra theo hợp đồng API thật.

Một số resolver có thể gửi cookie xóa hoặc thay cookie trong response invalidate. Không chỉ nhìn vào response body; hãy xác minh request tiếp theo với cookie cũ không truy cập được dữ liệu cũ. Nếu store hỗ trợ tra cứu trực tiếp, có thể kiểm tra repository trong test nội bộ mà không log session ID.

## 9. Kiểm tra đổi session ID

WebSession.changeSessionId() trả về Mono<Void>. Trong test, cần chờ publisher hoàn tất trước khi đánh giá response và cookie mới.

Một endpoint test-only có thể gọi:

~~~java
@PostMapping("/test/session/rotate")
Mono<Void> rotate(ServerWebExchange exchange) {
    return exchange.getSession()
        .flatMap(WebSession::changeSessionId);
}
~~~

Test nên xác minh:

- Cookie mới được gửi sau rotation.
- ID mới khác ID cũ.
- Attribute session vẫn được giữ theo hợp đồng.
- ID cũ không còn khôi phục phiên đã xác thực.
- Request gửi cookie mới truy cập được session.
- Các node khác cũng tìm thấy session bằng cookie mới.

Không in giá trị ID ra log để so sánh. Assertion có thể so sánh hai giá trị trong memory và chỉ báo pass/fail. Trong production, nên để Spring Security session fixation protection thực hiện rotation sau xác thực thay vì gọi endpoint tùy chỉnh.

## 10. Kiểm tra idle timeout và expiration

WebSession có max idle time. Khi vượt quá khoảng không hoạt động, session phải được xem là hết hạn khi repository/manager xử lý request tiếp theo. Việc xóa vật lý dữ liệu trong Redis hoặc cleanup nền có thể diễn ra muộn hơn thời điểm logic hết hạn.

Để kiểm thử:

1. Cấu hình timeout ngắn trong profile test.
2. Tạo session và lưu cookie.
3. Không gửi request trong thời gian vượt timeout.
4. Gửi lại cookie cũ.
5. Xác nhận session mới được tạo hoặc request bị xử lý theo chính sách ứng dụng.
6. Nếu cần, kiểm tra cleanup eventual riêng.

Không dùng sleep cố định dài trong mọi test. Có thể dùng Awaitility hoặc polling có deadline để chờ trạng thái backend, đồng thời giữ timeout test hữu hạn. Nếu dùng virtual time của Reactor, chỉ những publisher/scheduler được thiết kế dùng virtual scheduler mới bị điều khiển; TTL bên ngoài Redis không tự chạy theo virtual time của Reactor.

Phân biệt hai assertion:

- **Logical expiration:** repository không trả session hết hạn cho request.
- **Physical cleanup:** key/dòng đã được xóa khỏi store.

Không bắt buộc hai việc xảy ra cùng mili giây. Test repository nên xác minh logic hết hạn; test cleanup nên cho phép độ trễ theo lịch và cấu hình backend.

## 11. Kiểm tra max idle time và thay đổi thuộc tính

Nếu handler thay max idle time, hãy xác minh giá trị được lưu và có hiệu lực trong request sau. WebSession cung cấp getMaxIdleTime() và setMaxIdleTime(Duration). Cần lưu ý một số repository hoặc cấu hình có giới hạn/giá trị mặc định riêng.

Test nên bao gồm:

- Session dùng timeout mặc định.
- Session thay timeout trong request.
- Session có timeout rất ngắn.
- Session được truy cập trước khi hết hạn và last access time được cập nhật.
- Session không được gia hạn chỉ vì server gửi dữ liệu ra client.

Với Spring Session reactive, các thay đổi WebSession được persist qua reactive repository. Không dùng một test chỉ đọc object trong cùng request để kết luận dữ liệu đã được lưu; phải tạo request mới với cookie và xác minh giá trị sau round-trip.

## 12. Phân biệt WebSession mặc định và Spring Session repository

Đây là nguồn nhầm lẫn thường gặp. WebFlux có thể chạy với WebSessionStore mặc định trong bộ nhớ. Một test bindToController hoặc context không nạp Spring Session có thể vẫn tạo cookie và giữ attribute giữa request, nhưng dữ liệu không đi qua Redis repository.

Để chứng minh Spring Session:

- Xác nhận cấu hình reactive Spring Session được nạp vào ApplicationContext.
- Xác nhận WebSessionManager đang dùng store/repository được cấu hình.
- Dùng Redis test instance hoặc backend reactive tương ứng.
- Tạo session ở một application context/instance và đọc ở context/instance khác.
- Restart node tạo session rồi đọc lại từ node khác.
- Kiểm tra logout/expiration tác động đến dữ liệu repository.

Không chỉ dựa vào tên cookie. Cả WebSession mặc định và Spring Session có thể dùng cookie; cookie không chứng minh loại store.

## 13. Cấu hình integration test với Spring Boot

Ví dụ cấu trúc test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.beans.factory.annotation.Autowired;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveSessionRepositoryIntegrationTests {

    @Autowired
    WebTestClient client;

    // Tests use a real reactive session repository configured for the test profile.
}
~~~

Test profile phải cấu hình store độc lập và cookie name phù hợp. Nếu dùng Redis, có thể chạy Redis container riêng cho test suite và cung cấp connection details bằng DynamicPropertySource hoặc cơ chế cấu hình test của dự án.

Không để test vô tình kết nối Redis production hoặc shared development. Dùng database/index/namespace riêng và cleanup đúng phạm vi. Nếu test chạy song song, tránh dùng cùng key namespace cho nhiều suite.

## 14. Kiểm thử hai instance cùng dùng một repository

Mục tiêu của Spring Session là cho phép nhiều node khôi phục session từ cùng store. Test đa instance có thể:

1. Khởi động ứng dụng A và B với cùng reactive repository backend, cùng namespace và cùng cookie policy.
2. Gửi request tạo session tới A.
3. Lấy cookie từ response A.
4. Gửi request tiếp theo tới B với cookie đó.
5. Xác nhận B đọc được attribute đã ghi tại A.
6. Invalidate session qua A rồi xác minh B không còn khôi phục trạng thái cũ.

Hai instance phải có cấu hình tương thích về serialization, namespace, session ID resolver và security context. Nếu mỗi instance dùng namespace khác nhau, test sẽ không chứng minh shared session.

Không dùng sticky routing trong test này, vì mục tiêu là xác minh session có thể được đọc qua node khác. Nếu load balancer luôn đưa request về cùng node, hãy gọi trực tiếp hai port test hoặc dùng routing có thể xác định.

## 15. Kiểm thử Spring Security và xác thực

Nếu ứng dụng dùng Spring Security WebFlux, cần phân biệt test authorization với test lưu SecurityContext trong session.

- Dùng mock user hoặc security test support để kiểm tra route có yêu cầu role hay không.
- Dùng CSRF test support cho endpoint thay đổi trạng thái nếu CSRF được bật.
- Đăng nhập qua flow thực tế và tái sử dụng cookie để xác minh SecurityContext được khôi phục từ session repository.
- Logout qua endpoint thật và kiểm tra cookie/session bị vô hiệu hóa.
- Kiểm tra session fixation/ID rotation sau authentication.

Mock principal giúp kiểm tra authorization filter nhưng không nhất thiết chứng minh quá trình đăng nhập đã ghi SecurityContext vào Spring Session store. Muốn kiểm tra persistence, phải đi qua authentication flow hoặc cấu hình integration tương đương.

Không tắt security chỉ để test session persistence nếu production yêu cầu xác thực. Có thể dùng profile test riêng nhưng phải giữ filter và session integration liên quan đến hành vi đang kiểm tra.

## 16. Kiểm thử lỗi và trường hợp biên

Một bộ test WebSession tốt nên bao gồm:

| Trường hợp | Kết quả cần xác minh |
|---|---|
| Không có cookie | Tạo session mới khi endpoint cần session |
| Cookie sai định dạng | Không khôi phục nhầm session; xử lý như session không hợp lệ |
| Cookie trỏ đến ID không tồn tại | Tạo session mới hoặc trả lỗi theo chính sách |
| Repository timeout | Lỗi được chuyển thành response phù hợp; không cấp quyền mặc định |
| Redis unavailable | Request thất bại an toàn theo chính sách ứng dụng |
| Serialization lỗi | Không dùng dữ liệu session hỏng để xác thực |
| Invalidate | Session cũ không còn dùng được |
| Rotation | ID mới hoạt động, ID cũ bị từ chối |
| Expiration | Session hết hạn không được khôi phục |
| Hai request song song | Không giả định read-modify-write tự nguyên tử |
| Node restart | Node khác vẫn đọc được session nếu store còn hợp lệ |
| Cookie policy | Secure, HttpOnly, SameSite, Path và Domain đúng cấu hình |

Không để lỗi repository khiến ứng dụng fallback sang một session rỗng đã xác thực. Nếu store không khả dụng, xử lý theo fail-closed cho các thao tác cần trạng thái xác thực.

## 17. Kiểm tra cookie mà không làm lộ session ID

Cookie assertion nên tập trung vào thuộc tính:

- Cookie có tồn tại khi session được tạo.
- HttpOnly được bật nếu client không cần đọc cookie bằng JavaScript.
- Secure được bật trong môi trường HTTPS.
- SameSite phù hợp luồng điều hướng và cross-site request của ứng dụng.
- Path/Domain giới hạn cookie theo phạm vi cần thiết.
- Max-Age/Expires phù hợp chính sách session.

Không copy giá trị cookie vào log hoặc báo cáo test. Nếu test cần xác minh rotation, giữ hai giá trị trong memory và so sánh; không đưa chúng vào assertion message có thể xuất hiện trong CI log.

Tên cookie và thuộc tính có thể khác giữa môi trường test và production. Test nên lấy cấu hình từ cùng property hoặc configuration bean thay vì giả định mặc định trong mọi môi trường.

## 18. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Test WebSession pass nhưng Redis không có dữ liệu | bindToController dùng store mặc định hoặc session config không được nạp | Test ApplicationContext đầy đủ với reactive repository |
| Request thứ hai nhận count = 1 | Không gửi lại cookie từ response đầu | Trích ResponseCookie và gọi cookie() ở request sau |
| Cookie không xuất hiện | Handler không start session hoặc không thay đổi attributes | Tạo session trong fixture và kiểm tra response commit |
| Test chạy riêng pass, chạy song song fail | Chia sẻ cookie hoặc namespace/store key | Session riêng cho mỗi test và namespace cô lập |
| @WebFluxTest không thấy session config | Slice không import cấu hình Spring Session | Import config hoặc dùng full integration test |
| JDBC repository bị gọi trên event loop | Dùng blocking Servlet repository trong WebFlux | Dùng reactive repository hoặc adapter có scheduler/transaction phù hợp |
| Expiration test chập chờn | Dựa vào sleep hoặc nhầm logical expiry với physical cleanup | Dùng timeout test có deadline và polling |
| Mock user pass nhưng login persistence fail | Mock principal không chạy authentication flow thật | Kiểm thử đăng nhập và cookie round-trip |
| Multi-node test không thấy session | Namespace, serializer hoặc store config khác nhau | Đồng bộ cấu hình giữa các node |
| Cookie bị thiếu qua proxy | Domain, Path, Secure, SameSite hoặc header bị thay đổi | Kiểm tra response tại từng hop và cấu hình ingress |

## 19. Quy trình thiết kế test

Khi thêm hoặc sửa tính năng dùng WebSession:

1. Xác định endpoint có tạo hoặc thay đổi WebSession không.
2. Chọn phạm vi test: controller, WebFlux slice, application context hay server thật.
3. Nếu mục tiêu là Spring Session, xác nhận reactive repository được nạp.
4. Tạo session bằng request đầu tiên và lấy cookie từ response.
5. Gửi lại cookie rõ ràng trong request tiếp theo.
6. Kiểm tra attribute, last access, max idle time và response.
7. Kiểm tra invalidate, rotation và expiration.
8. Nếu chạy nhiều instance, tạo session ở node A và đọc/xóa ở node B.
9. Cô lập store, namespace và cookie cho mỗi test.
10. Xác nhận log/CI artifact không chứa session ID hoặc token.

## 20. Nguyên tắc triển khai

- Dùng WebTestClient để kiểm thử request/response WebFlux và WebSession.
- Phân biệt WebSession với Servlet HttpSession.
- Phân biệt store mặc định trong bộ nhớ với Spring Session reactive repository.
- Dùng bindToApplicationContext hoặc full Spring Boot context khi cần xác minh filter, WebSessionManager và repository.
- Dùng reactive repository cho WebFlux; không gọi JDBC blocking trên event loop.
- Trích cookie từ response đầu tiên và gửi lại rõ ràng trong request kế tiếp.
- Kiểm tra create, attribute persistence, rotation, invalidate và expiration.
- Tách logical expiration khỏi cleanup vật lý trong backend.
- Dùng store và namespace cô lập; không flush backend dùng chung.
- Kiểm thử authentication flow thật khi cần xác minh SecurityContext persistence.
- Kiểm thử nhiều instance để chứng minh shared repository hoạt động.
- Không ghi session ID, cookie hoặc token vào log, assertion output hay CI artifact.

WebTestClient giúp kiểm tra WebSession từ góc nhìn HTTP, nhưng giá trị của test phụ thuộc vào hạ tầng được nạp. Test controller có thể xác nhận logic handler; chỉ integration test dùng Spring Session reactive repository mới chứng minh cookie round-trip, persistence, expiration và invalidate trên store dùng chung. Khi chọn đúng phạm vi, giữ cookie có kiểm soát và kiểm thử qua nhiều instance, nhóm phát triển có thể phát hiện sớm lỗi session trước khi triển khai WebFlux ra production.
