# Xây dựng bản WebFlux dùng ReactiveSessionRepository

## Mục tiêu bài thực hành

Bài thực hành xây dựng một ứng dụng Spring WebFlux có thể lưu WebSession bằng Spring Session thông qua ReactiveSessionRepository. Ứng dụng cung cấp một API nhỏ để tạo, đọc, cập nhật, đổi định danh và hủy phiên. Khi dùng Redis reactive làm kho lưu trữ, nhiều instance WebFlux có thể khôi phục cùng một phiên từ cookie mà không phụ thuộc bộ nhớ của một node.

WebFlux sử dụng WebSession và các API reactive Mono/Flux. Vì vậy, bài thực hành cần giữ luồng I/O không chặn từ HTTP handler đến repository. Không dùng HttpSession, SessionRepository đồng bộ hoặc JDBC blocking trên event-loop. Spring Session cung cấp ReactiveSessionRepository để tạo, tìm, lưu và xóa Session theo cách reactive; WebFlux tích hợp repository này qua WebSessionManager.

Sau bài thực hành, bạn có thể:

- Tạo project Spring Boot WebFlux với dependency phù hợp.
- Phân biệt WebSession, ReactiveSessionRepository và WebSessionManager.
- Chọn ReactiveMapSessionRepository cho test cục bộ hoặc Redis repository cho nhiều instance.
- Cấu hình Redis bằng @EnableRedisWebSession hoặc auto-configuration của Boot.
- Cấu hình cookie định danh WebSession.
- Viết controller reactive để tạo và đọc thuộc tính session.
- Đổi Session ID và invalidate WebSession đúng cách.
- Lưu SecurityContext trong WebSession khi ứng dụng cần đăng nhập duy trì.
- Kiểm thử repository bằng StepVerifier và kiểm thử HTTP bằng WebTestClient.
- Kiểm thử persistence, expiration, logout và khả năng chia sẻ session giữa hai instance.
- Nhận biết các lỗi do blocking call, serializer, TTL, cookie hoặc dependency cấu hình sai.

## 1. Kiến trúc cần xây dựng

Ứng dụng gồm các lớp:

1. Spring Boot khởi động Spring WebFlux.
2. WebFlux tạo ServerWebExchange và quản lý WebSession.
3. Spring Session cung cấp WebSessionManager dựa trên ReactiveSessionRepository.
4. ReactiveSessionRepository đọc và ghi Session qua Redis hoặc implementation khác.
5. CookieWebSessionIdResolver đọc Session ID từ cookie và phát cookie mới khi session bắt đầu hoặc đổi ID.
6. Spring Security, nếu được bật, lưu SecurityContext vào WebSession.
7. Controller trả Mono hoặc Flux và không chặn event-loop.

Sơ đồ:

~~~mermaid
flowchart TD
    C[Browser / API client] -->|Cookie SESSION| W[Spring WebFlux]
    W --> E[ServerWebExchange]
    E --> M[WebSessionManager]
    M --> R[ReactiveSessionRepository]
    R --> RR[Reactive Redis Operations]
    RR --> L[Lettuce / Reactive Redis Connection]
    L --> DB[(Redis)]
    E --> S[Spring Security WebFilter]
    S --> SC[SecurityContext in WebSession]
    E --> H[Reactive Controller]
    H -->|Mono / Flux| E
~~~

Với nhiều instance, các node cùng dùng một Redis repository và cùng namespace:

~~~text
                 Load balancer
                 /           \
                v             v
          WebFlux Node A   WebFlux Node B
                |               |
                +-------+-------+
                        |
                 Shared Redis
                 WebSession data
~~~

Client gửi cùng cookie đến A hoặc B. Mỗi node tải session từ Redis bằng Session ID. Session object trong heap của A và B vẫn độc lập; điều được chia sẻ là dữ liệu session trong repository.

### Phân biệt ba API

| Thành phần | Vai trò |
|---|---|
| WebSession | API session mà controller WebFlux sử dụng |
| ReactiveSessionRepository | Hợp đồng reactive để tạo, tìm, lưu và xóa Session |
| WebSessionManager | Tạo và quản lý WebSession cho ServerWebExchange, dùng repository phía dưới |

Ứng dụng thông thường nên thao tác với WebSession qua ServerWebExchange hoặc controller argument. Không cần tự gọi repository trong mọi endpoint. Truy cập trực tiếp repository phù hợp cho test repository, adapter tùy chỉnh hoặc công việc hạ tầng có chủ đích.

## 2. Tạo project WebFlux

Tạo ứng dụng Spring Boot với Java và Spring WebFlux. Không thêm Spring MVC nếu mục tiêu là chạy reactive server.

### Dependency Maven cho Boot 3

Ví dụ với Spring Boot 3.x, dùng module Spring Session Redis cùng Spring Data Redis:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.session</groupId>
        <artifactId>spring-session-data-redis</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Các dependency version nên do Spring Boot BOM quản lý. Không tự ghi version riêng cho Spring Session, Spring Data Redis hoặc Spring Security nếu Boot đã quản lý chúng.

### Dependency với Boot 4

Ở các dòng Spring Boot mới có starter session riêng, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-session-data-redis</artifactId>
</dependency>
~~~

Tên artifact thay đổi theo generation Boot. Hãy chọn đúng starter theo phiên bản dự án. Không thêm đồng thời nhiều cách cấu hình nếu chưa xác định Boot auto-configuration sẽ chọn repository nào.

### Không thêm Spring MVC ngoài ý muốn

Nếu cùng classpath có cả spring-boot-starter-web và spring-boot-starter-webflux, Spring Boot thường chọn Spring MVC. Điều này có thể khiến ứng dụng không chạy WebFlux như dự định.

Kiểm tra dependency tree và log khởi động để xác nhận reactive web application type. Nếu dự án buộc phải có cả hai starter, có thể cấu hình rõ WebApplicationType.REACTIVE, nhưng hãy xem lại vì sao cần đưa MVC vào classpath.

## 3. Cấu hình Redis connection

Trong local development, có thể chạy Redis ở localhost:6379. Với Spring Boot, cấu hình kết nối trong application.yml:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s

  session:
    timeout: 30m
    data:
      redis:
        namespace: "shop:webflux:session"
~~~

Trong production, cung cấp host, credential và TLS qua secret/configuration management. Không commit password hoặc URI chứa secret vào Git.

Spring Boot auto-configure RedisConnectionFactory. Với Lettuce, factory hỗ trợ cả thao tác đồng bộ và reactive. Spring Session WebFlux cần ReactiveRedisConnectionFactory.

Kiểm tra kết nối bằng health indicator hoặc integration test. Không đưa thao tác ping/blocking vào request path để xác nhận Redis đang sống.

### Redis namespace

Namespace tách key session của ứng dụng khỏi các ứng dụng khác dùng chung Redis. Chọn prefix ổn định theo ứng dụng và môi trường, ví dụ:

~~~text
shop:dev:webflux:session
shop:staging:webflux:session
shop:prod:webflux:session
~~~

Namespace không phải ranh giới bảo mật. Hãy kết hợp Redis ACL để service account chỉ truy cập key pattern cần thiết.

## 4. Bật Spring Session Redis cho WebFlux

Có hai cách chính:

- Để Spring Boot auto-configure reactive Redis session khi dependency và điều kiện phù hợp có mặt.
- Cấu hình tường minh bằng @EnableRedisWebSession.

### Cách A: Dùng auto-configuration

Nếu phiên bản Spring Boot hỗ trợ reactive Redis session auto-configuration và dependency phù hợp có mặt, Boot tạo WebSessionManager backed by Spring Session. Khi đó, cấu hình timeout và namespace qua properties.

Không cần đồng thời thêm @EnableRedisWebSession nếu Boot đã tạo WebSessionManager. Khi khai báo annotation thủ công, auto-configuration liên quan có thể back off.

### Cách B: Dùng annotation

Nếu muốn kiểm soát rõ cấu hình Spring Session:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession(
        maxInactiveIntervalInSeconds = 1800,
        redisNamespace = "shop:webflux:session"
)
public class ReactiveSessionConfiguration {
}
~~~

@EnableRedisWebSession đăng ký WebSessionManager dựa trên ReactiveRedisSessionRepository. Cấu hình cần một ReactiveRedisConnectionFactory trong application context. Spring Boot Redis auto-configuration thường cung cấp factory đó khi dependency và properties đúng.

maxInactiveIntervalInSeconds đặt idle timeout mặc định cho session. Giá trị 1800 tương ứng 30 phút. Repository chịu trách nhiệm lưu session và áp dụng expiration theo implementation.

Không dùng @EnableRedisHttpSession trong ứng dụng WebFlux. Annotation đó cấu hình HttpSession/Servlet filter, không phải WebSessionManager.

## 5. Tạo ReactiveSessionRepository trong môi trường test cục bộ

Để hiểu hợp đồng repository, có thể dùng ReactiveMapSessionRepository:

~~~java
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.MapSession;
import org.springframework.session.ReactiveMapSessionRepository;
import org.springframework.session.ReactiveSessionRepository;
import org.springframework.session.config.annotation.web.server.EnableSpringWebSession;

@Configuration(proxyBeanMethods = false)
@EnableSpringWebSession
public class InMemoryWebSessionConfiguration {

    @Bean
    ReactiveSessionRepository<MapSession> reactiveSessionRepository() {
        return new ReactiveMapSessionRepository(new ConcurrentHashMap<>());
    }
}
~~~

@EnableSpringWebSession tạo WebSessionManager từ một ReactiveSessionRepository bean. Nếu không có repository duy nhất phù hợp, context không thể cấu hình WebSessionManager.

ReactiveMapSessionRepository hữu ích cho:

- Unit test và slice test.
- Demo API.
- Local development không cần Redis.
- Kiểm tra logic WebSession đơn giản.

Nó không phải lựa chọn production cho nhiều instance vì map nằm trong heap của một JVM. Restart sẽ mất dữ liệu và node khác không nhìn thấy session. Annotation EnableSpringWebSession cũng không tự cấu hình toàn bộ expiration infrastructure cho mọi custom repository; việc dọn session hết hạn phụ thuộc implementation.

Không dùng in-memory repository trong cluster rồi kỳ vọng client có thể đi đến bất kỳ node nào.

## 6. Hợp đồng ReactiveSessionRepository

ReactiveSessionRepository<S extends Session> cung cấp bốn thao tác chính:

| Method | Kiểu trả về | Ý nghĩa |
|---|---|---|
| createSession() | Mono<S> | Tạo một Session mới có thể được lưu |
| findById(id) | Mono<S> | Tìm session theo ID; empty nếu không có |
| save(session) | Mono<Void> | Lưu trạng thái session |
| deleteById(id) | Mono<Void> | Xóa session theo ID |

Ví dụ dùng repository trực tiếp trong một test:

~~~java
@Test
void savesAndLoadsSession() {
    StepVerifier.create(
            repository.createSession()
                    .flatMap(session -> {
                        session.setAttribute("theme", "dark");
                        String id = session.getId();

                        return repository.save(session)
                                .then(repository.findById(id));
                    })
    )
    .assertNext(session ->
            assertThat(session.getAttribute("theme")).isEqualTo("dark"))
    .verifyComplete();
}
~~~

Ví dụ giả định repository được inject và có kiểu generic phù hợp. Không gọi block() trong ứng dụng reactive chỉ để lấy Session. Hãy compose Mono/Flux đến tận HTTP response.

### Trách nhiệm khi tự viết repository

Nếu tự triển khai ReactiveSessionRepository, cần bảo đảm:

- ID session đủ ngẫu nhiên và không đoán được.
- createSession tạo session mới chưa bị persist sai thời điểm.
- findById trả Mono.empty khi session không tồn tại hoặc không còn hợp lệ.
- save ghi các thuộc tính và metadata cần thiết.
- maxInactiveInterval và expiration được áp dụng nhất quán.
- deleteById có thể gọi lặp an toàn.
- I/O thật sự non-blocking.
- Serializer xử lý được các thuộc tính được phép lưu.
- Lỗi backend được truyền thành reactive error signal.
- Có chiến lược cleanup và giới hạn dung lượng.
- Các thao tác cạnh tranh không làm hỏng dữ liệu ngoài invariant đã định.

Không bọc JDBC blocking trong Mono.just rồi tuyên bố repository đã reactive. Mono.just chỉ phát ra giá trị; thao tác JDBC vẫn chạy đồng bộ trên thread gọi nó. Nếu cần relational store reactive, đánh giá R2DBC và tự thiết kế repository phù hợp; không nhầm JDBC với R2DBC.

## 7. Xây dựng WebFlux controller thao tác WebSession

Controller có thể nhận ServerWebExchange và lấy WebSession bằng exchange.getSession(). Phương thức trả về Mono<WebSession>, nên mọi xử lý tiếp theo cần nằm trong reactive chain.

DTO:

~~~java
public record UpdateSessionRequest(
        String theme,
        Integer cartCount
) {
}

public record SessionView(
        boolean started,
        String theme,
        Integer cartCount
) {
}
~~~

Controller:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/session")
public class SessionController {

    @PostMapping
    public Mono<SessionView> update(
            @RequestBody UpdateSessionRequest request,
            ServerWebExchange exchange
    ) {
        return exchange.getSession().map(session -> {
            session.getAttributes().put("theme", request.theme());
            session.getAttributes().put("cartCount", request.cartCount());

            return view(session);
        });
    }

    @GetMapping
    public Mono<SessionView> read(ServerWebExchange exchange) {
        return exchange.getSession().map(this::view);
    }

    @PostMapping("/change-id")
    public Mono<String> changeId(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(session -> {
                    String oldId = session.getId();

                    return session.changeSessionId()
                            .thenReturn(oldId);
                });
    }

    @DeleteMapping
    public Mono<ResponseEntity<Void>> invalidate(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(WebSession::invalidate)
                .thenReturn(ResponseEntity.noContent().build());
    }

    private SessionView view(WebSession session) {
        return new SessionView(
                session.isStarted(),
                session.getAttribute("theme"),
                session.getAttribute("cartCount")
        );
    }
}
~~~

Đây là ví dụ học tập. Endpoint change-id chỉ trả ID cũ để minh họa; không nên trả Session ID trong API production. Trong thực tế có thể trả trạng thái đã đổi mà không tiết lộ định danh.

### Vì sao dùng map và flatMap?

- map chuyển một giá trị WebSession thành DTO đồng bộ.
- flatMap dùng khi thao tác trả về Mono, ví dụ changeSessionId() hoặc invalidate().
- then() bỏ giá trị trung gian và chỉ giữ tín hiệu hoàn tất.
- Không gọi subscribe() thủ công trong controller; framework quản lý subscription.
- Không gọi block() để chờ repository.

Khi thay đổi session attributes, WebSession được đánh dấu cần lưu theo lifecycle của WebFlux. Session manager lưu dữ liệu khi response được hoàn tất/commit theo implementation.

### getSession() có thể tạo session mới

exchange.getSession() cung cấp WebSession cho exchange và có thể tạo session mới khi cần. Nếu chỉ muốn kiểm tra session tồn tại, không nên dựa vào endpoint probe gọi getSession() rồi kết luận cookie cũ hợp lệ. Kiểm thử phải phân biệt session mới được tạo với session đã được tải từ cookie.

## 8. Đổi Session ID và invalidate

WebSession có các thao tác reactive:

- changeSessionId(): Mono<Void> đổi định danh phiên.
- invalidate(): Mono<Void> kết thúc phiên.
- save(): Mono<Void> lưu phiên.
- start(): đánh dấu phiên cần bắt đầu/lưu theo lifecycle.

### Đổi ID

Đổi ID sau authentication giúp giảm session fixation. API changeSessionId() trả Mono<Void>, vì vậy phải chờ thao tác hoàn tất trong pipeline trước khi tạo response phụ thuộc vào ID mới.

Client cần dùng cookie mới do WebSessionIdResolver phát ra. Không tiếp tục gửi ID cũ trong request sau.

### Invalidate

invalidate() kết thúc WebSession. Request tiếp theo không được khôi phục trạng thái xác thực từ ID đã bị hủy. Cookie resolver có thể phát cookie hết hạn để client xóa cookie; server-side invalidation vẫn là điều kiện bảo mật quan trọng.

Nếu cần invalidate mọi session của một người dùng, repository cơ bản tìm theo ID là chưa đủ. Cần principal index hoặc một cơ chế quản lý phiên riêng, đồng thời kiểm tra quyền người gọi.

## 9. Cấu hình cookie WebSession

WebFlux dùng WebSessionIdResolver để đọc và ghi Session ID. Mặc định là CookieWebSessionIdResolver.

Có thể cấu hình tên cookie và thuộc tính:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration(proxyBeanMethods = false)
public class WebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(builder -> builder
                .path("/")
                .httpOnly(true)
                .sameSite("Lax"));

        return resolver;
    }
}
~~~

Ở production HTTPS, cân nhắc bật Secure theo policy. Test chạy HTTP local có thể không gửi Secure cookie như browser production; hãy kiểm tra Set-Cookie header riêng và có test HTTPS nếu cần xác minh client behavior.

Các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| Name | Tên cookie mang Session ID |
| Path | Phạm vi URL gửi cookie |
| Domain | Host hoặc domain được phép nhận cookie |
| Secure | Chỉ gửi qua HTTPS |
| HttpOnly | JavaScript không đọc cookie qua document.cookie |
| SameSite | Giới hạn gửi cookie trong ngữ cảnh cross-site |
| Max-Age/Expires | Thời hạn cookie phía client nếu được cấu hình |

Không dùng wildcard domain hoặc SameSite=None mà không bật Secure và hiểu rõ luồng cross-site. Cookie session là bearer credential; bảo vệ nó như bí mật xác thực.

### Cookie và CORS

Nếu frontend ở origin khác backend, cần cấu hình CORS credentials phù hợp. Browser chỉ gửi cookie cross-origin khi client bật credentials và server trả Access-Control-Allow-Credentials cùng origin cụ thể. Không kết hợp credentials với Access-Control-Allow-Origin wildcard.

CORS không thay CSRF protection. Với cookie authentication, cần đánh giá CSRF theo cách frontend gửi request thay đổi trạng thái.

## 10. Tích hợp Spring Security reactive

Nếu ứng dụng cần login duy trì giữa các request, SecurityContext phải được lưu trong WebSession.

Spring Security WebFlux dùng ServerSecurityContextRepository. Với cookie-based session, WebSessionServerSecurityContextRepository là lựa chọn phổ biến.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration(proxyBeanMethods = false)
public class ReactiveSecurityConfiguration {

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository
    ) {
        return http
                .authorizeExchange(authorize -> authorize
                        .pathMatchers("/health", "/login").permitAll()
                        .anyExchange().authenticated()
                )
                .securityContextRepository(repository)
                .formLogin(form -> form
                        .securityContextRepository(repository)
                )
                .build();
    }
}
~~~

Đây là cấu hình khung. Thêm user details, authentication provider, CSRF policy và success/failure handler theo ứng dụng.

Với API stateless dùng bearer token, có thể dùng NoOpServerSecurityContextRepository và xác thực mỗi request. Không chọn NoOp nếu mong muốn session cookie duy trì đăng nhập.

### Không dùng ThreadLocal SecurityContextHolder trong reactive flow

Dùng ReactiveSecurityContextHolder để đọc Authentication trong Mono/Flux. Không giả định ThreadLocal đi theo pipeline khi scheduler chuyển thread.

### Logout

Logout cần invalidate WebSession và xóa SecurityContext. Với Spring Security reactive, cấu hình logout handler phù hợp và test request sau logout bằng cookie cũ. Cookie bị xóa ở client chưa đủ chứng minh repository đã invalidate session.

## 11. Cấu hình timeout và expiration

Idle timeout của WebSession được biểu diễn bằng max idle interval. Khi không có hoạt động trong khoảng thời gian cấu hình, session hết hạn.

Có thể cấu hình timeout qua Boot property:

~~~yaml
spring:
  session:
    timeout: 30m
~~~

Khi dùng @EnableRedisWebSession thủ công, cấu hình maxInactiveIntervalInSeconds trên annotation hoặc cấu hình repository tương ứng. Khi tự dùng @EnableSpringWebSession với custom repository, chính implementation phải xử lý expiration; annotation tổng quát không tự cung cấp toàn bộ cleanup infrastructure.

### Redis expiration

Reactive Redis repository lưu session và áp dụng TTL. Khi session được truy cập hoặc cập nhật, thời gian hết hạn được điều chỉnh theo policy repository. Cần kiểm tra:

- TTL thực tế của key session.
- maxInactiveInterval của WebSession.
- Hành vi refresh TTL khi có request.
- Cleanup và expiration metadata nếu repository dùng.
- Redis keyspace notifications nếu ứng dụng cần session expiration events.

Không giả định key vật lý bị xóa chính xác tại millisecond timeout. Redis expiration có thể được xử lý theo cơ chế lazy/active expiration. Quan trọng là request sau timeout không được khôi phục session đã hết hiệu lực.

### Session timeout và cookie expiration khác nhau

Server-side session timeout quyết định session còn hợp lệ hay không. Cookie Max-Age/Expires quyết định browser giữ cookie bao lâu. Hai thời hạn này không nhất thiết giống nhau.

Ngay cả khi cookie vẫn còn, server phải từ chối Session ID đã hết hạn. Ngược lại, browser có thể xóa cookie trước khi session server hết hạn, khiến session tồn tại đến TTL nhưng client không còn dùng được.

## 12. Serializer và thuộc tính session

Redis repository phải serialize thuộc tính session. Chọn serializer phù hợp với kiểu dữ liệu và chiến lược nâng cấp ứng dụng.

Các giá trị đơn giản như String, Integer, Boolean thường dễ xử lý. DTO phức tạp cần serializer được cấu hình và tương thích giữa các version.

Không nên lưu:

- Password hoặc credential thô.
- Access token không cần thiết.
- Entity JPA lớn.
- Object chứa connection, file handle hoặc thread.
- Dữ liệu không ổn định về class name hoặc schema.
- Payload lớn làm tăng Redis memory và latency.

Ưu tiên lưu ID hoặc snapshot nhỏ. Dữ liệu nghiệp vụ quan trọng nên nằm trong database nghiệp vụ; session chỉ giữ trạng thái cần cho trải nghiệm và xác thực.

### Tương thích khi rolling deployment

Nếu node cũ và node mới cùng đọc Redis, serializer phải tương thích trong giai đoạn rollout. Nếu class hoặc type metadata thay đổi, node cũ có thể không đọc được session do node mới ghi.

Lập kế hoạch expand-contract hoặc chấp nhận invalidation có chủ đích. Không xóa toàn bộ Redis session để xử lý lỗi serializer trước khi đánh giá tác động người dùng.

## 13. Tạo custom ReactiveSessionRepository

Trong phần lớn ứng dụng, nên dùng repository có sẵn như ReactiveRedisSessionRepository. Chỉ tự triển khai khi cần một backend hoặc semantics đặc biệt.

Khung ý tưởng:

~~~java
public final class CustomReactiveSessionRepository
        implements ReactiveSessionRepository<CustomSession> {

    @Override
    public Mono<CustomSession> createSession() {
        return Mono.fromSupplier(CustomSession::new);
    }

    @Override
    public Mono<CustomSession> findById(String id) {
        return store.find(id);
    }

    @Override
    public Mono<Void> save(CustomSession session) {
        return store.save(session).then();
    }

    @Override
    public Mono<Void> deleteById(String id) {
        return store.delete(id).then();
    }
}
~~~

Đây là pseudocode: store là API reactive của backend do ứng dụng cung cấp; CustomSession cần triển khai Session. Không thể biên dịch nguyên mẫu nếu chưa định nghĩa các kiểu đó.

Đăng ký repository:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableSpringWebSession
class CustomWebSessionConfiguration {

    @Bean
    ReactiveSessionRepository<CustomSession> reactiveSessionRepository(
            CustomStore store
    ) {
        return new CustomReactiveSessionRepository(store);
    }
}
~~~

Một repository custom cần được kiểm thử riêng về ID, expiration, save, delete, serialization, concurrent update, error propagation và cleanup. Nếu backend chỉ có API blocking, hãy đánh giá lại lựa chọn công nghệ hoặc cô lập blocking operation trên scheduler phù hợp; không chạy nó trực tiếp trên Netty event-loop.

## 14. Kiểm thử ReactiveSessionRepository với StepVerifier

StepVerifier kiểm tra tín hiệu Mono/Flux: giá trị tiếp theo, hoàn tất và lỗi.

Ví dụ test lưu rồi tải session:

~~~java
@Test
void savesAndReadsSession() {
    StepVerifier.create(
            repository.createSession()
                    .flatMap(session -> {
                        session.setAttribute("theme", "dark");
                        String id = session.getId();

                        return repository.save(session)
                                .then(repository.findById(id));
                    })
    )
    .assertNext(session ->
            assertThat(session.getAttribute("theme")).isEqualTo("dark"))
    .verifyComplete();
}
~~~

Test xóa:

~~~java
@Test
void deletesSession() {
    StepVerifier.create(
            repository.createSession()
                    .flatMap(session -> {
                        String id = session.getId();
                        return repository.save(session)
                                .then(repository.deleteById(id))
                                .then(repository.findById(id));
                    })
    )
    .verifyComplete();
}
~~~

Test thứ hai kỳ vọng findById trả Mono.empty sau delete. Nếu repository custom có tombstone hoặc eventual consistency, xác định hợp đồng rõ ràng và kiểm thử theo semantics đã chọn.

### Test lỗi backend

Dùng mock hoặc test double để xác minh lỗi kết nối được truyền thành reactive error. Không nuốt lỗi bằng onErrorResume trả empty nếu empty có nghĩa "session không tồn tại"; như vậy lỗi Redis có thể bị hiểu nhầm thành anonymous request.

## 15. Kiểm thử HTTP với WebTestClient

WebTestClient là công cụ phù hợp cho WebFlux. Không dùng MockMvc như công cụ chính để kiểm tra WebSession reactive.

Test tạo session:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSessionIntegrationTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void sessionAttributesSurviveAcrossRequests() {
        EntityExchangeResult<byte[]> created =
                webTestClient.post()
                        .uri("/api/session")
                        .bodyValue(new UpdateSessionRequest("dark", 3))
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody()
                        .returnResult();

        ResponseCookie cookie =
                created.getResponseCookies().getFirst("SESSION");

        assertThat(cookie).isNotNull();

        webTestClient.get()
                .uri("/api/session")
                .cookie("SESSION", cookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.theme").isEqualTo("dark")
                .jsonPath("$.cartCount").isEqualTo(3);
    }
}
~~~

Ví dụ giả định cookie tên SESSION. Nếu ứng dụng đổi tên cookie hoặc dùng resolver khác, hãy dùng tên đã cấu hình.

### Vì sao phải gửi cookie thủ công?

Một request độc lập không tự biết session của request trước. Test cần lấy cookie từ response đầu và gửi lại trong request tiếp theo. Nếu không, server có thể tạo một session khác và test không còn kiểm tra persistence.

### Kiểm tra đổi ID

- Tạo session và lấy cookie cũ.
- Gửi request change-id với cookie cũ.
- Lấy cookie mới từ response.
- Xác minh giá trị cookie mới khác cookie cũ.
- Gửi request tiếp theo với cookie mới và xác minh thuộc tính còn nguyên.
- Gửi request mới với cookie cũ và xác minh không tải lại session cũ.

### Kiểm tra invalidate

- Tạo session.
- Giữ bản sao cookie.
- Gửi request invalidate.
- Xác minh response cookie được hết hạn theo resolver.
- Gửi request mới với cookie cũ.
- Xác minh session không còn khôi phục thuộc tính hoặc SecurityContext.

Nếu endpoint gọi getSession() để đọc, nó có thể tạo session mới. Hãy thiết kế test probe phân biệt session mới với session được tải từ ID cũ.

## 16. Kiểm thử với Redis thật bằng Testcontainers

Mock repository không xác minh Redis serialization, TTL, key namespace hoặc connection behavior. Dùng Redis test instance hoặc Testcontainers cho integration test.

Ví dụ khung cấu hình:

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RedisWebSessionIntegrationTests {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7.4-alpine")
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }
}
~~~

Cấu hình Testcontainers và package imports cần khớp version Testcontainers trong dự án. Không dùng container test như một thay thế cho kiểm thử Redis production topology; cluster, TLS, ACL và failover cần test riêng.

Các test cần có:

- Tạo session và đọc lại.
- Cập nhật attributes.
- Đổi Session ID.
- Invalidate.
- Expiration/TTL.
- Serialization của DTO.
- Hai application context cùng Redis.
- Redis unavailable và reconnect.
- ACL user giới hạn nếu production dùng ACL.

## 17. Kiểm thử nhiều instance

Để chứng minh session được chia sẻ, cần hai application instance độc lập dùng chung Redis.

Kịch bản:

1. Khởi động WebFlux A và WebFlux B với cùng Redis endpoint.
2. Gửi POST tạo session đến A.
3. Lấy cookie từ response A.
4. Gửi GET đọc session đến B bằng cookie đó.
5. Xác minh thuộc tính được khôi phục.
6. Cập nhật thuộc tính tại B.
7. Gửi request mới đến A và xác minh giá trị được lưu theo repository semantics.
8. Invalidate tại B.
9. Gửi cookie cũ đến A và xác minh session không còn hợp lệ.

Không dùng hai WebTestClient cùng một application context để tuyên bố đã kiểm thử nhiều JVM. Có thể khởi động hai server port độc lập trong test process hoặc chạy hai container application độc lập.

### Sticky session

Sticky session có thể giảm request đổi node nhưng không phải điều kiện để Spring Session chia sẻ session. Kiểm thử phải chủ động đưa request đến từng node để chứng minh repository dùng chung.

### Race condition

Hai request cùng đọc rồi sửa một thuộc tính có thể gây lost update tùy save/flush mode và repository. Shared Redis không tự biến mọi read-modify-write thành atomic operation. Nếu dữ liệu có invariant nghiệp vụ, đặt atomicity tại database/Redis operation phù hợp và test cạnh tranh riêng.

## 18. Kiểm thử timeout và expiration

Cấu hình timeout ngắn trong profile test. Sau khi session không hoạt động đủ lâu:

- Repository không trả session còn hợp lệ.
- WebFlux không khôi phục SecurityContext cũ.
- Request bảo vệ yêu cầu xác thực lại.
- Cookie cũ không thể tạo lại phiên đã hết hạn.
- Cleanup vật lý có thể xảy ra sau thời điểm session không còn hợp lệ.

Không yêu cầu Redis key biến mất đúng một millisecond sau TTL. Test bằng eventual assertion có timeout hợp lý. Phân biệt session hết hạn về mặt logic với key đã được dọn khỏi Redis.

Nếu test dùng ReactiveMapSessionRepository, tự xác định cách cleanup và thời gian kiểm tra vì repository map không cung cấp cùng expiration infrastructure như Redis implementation.

## 19. Bảo mật và vận hành

### Redis ACL và network

Tài khoản runtime chỉ cần quyền trên namespace của ứng dụng và command repository thực sự sử dụng. Không cấp +@all, quyền CONFIG hoặc FLUSHALL. Dùng TLS và private network theo policy hạ tầng.

### Cookie

- HttpOnly bật cho cookie session.
- Secure bật trong HTTPS production.
- SameSite phù hợp luồng frontend.
- Path và Domain giới hạn hợp lý.
- Không ghi cookie hoặc Session ID vào log.

### Observability

Theo dõi:

- Redis connection errors và latency.
- Session create/read/save/delete failures.
- Số session active hoặc dung lượng tổng hợp.
- Expiration và cleanup behavior.
- Request chuyển thành anonymous bất thường.
- Serialization errors.
- Connection pool saturation.

Không log payload session hoặc SecurityContext. Dùng correlation ID không nhạy cảm.

### Graceful degradation

Nếu Redis không khả dụng, ứng dụng cần có policy rõ ràng. Không tự động fallback sang in-memory repository trong production nếu điều đó tạo ra hai miền session không đồng nhất giữa các node. Thường nên trả lỗi có kiểm soát hoặc dùng resilience policy đã được thiết kế và kiểm thử.

## 20. Những lỗi thường gặp

**Dùng HttpSession trong WebFlux.**  
Dùng WebSession và ServerWebExchange.

**Dùng SessionRepository đồng bộ.**  
WebFlux cần ReactiveSessionRepository; không chạy blocking repository trên event-loop.

**Bật @EnableRedisHttpSession.**  
Đó là cấu hình Servlet. Dùng @EnableRedisWebSession hoặc Boot reactive auto-configuration.

**Bật @EnableSpringWebSession nhưng không cung cấp repository.**  
Annotation cần một ReactiveSessionRepository bean duy nhất.

**Dùng ReactiveMapSessionRepository cho nhiều instance.**  
Map nằm trong một JVM, không chia sẻ và mất dữ liệu khi restart.

**Cho rằng @EnableSpringWebSession tự cấu hình TTL cho mọi repository.**  
Expiration và cleanup phụ thuộc implementation; custom repository phải tự xử lý.

**Dùng block() hoặc subscribe() trong controller.**  
Điều đó phá reactive composition, có thể chặn event-loop hoặc làm framework không quản lý được lifecycle.

**Không gửi cookie giữa các request trong test.**  
Request sau không khôi phục session cũ. Lấy cookie response và gửi lại rõ ràng.

**Chỉ test StepVerifier.**  
StepVerifier không chứng minh HTTP cookie, WebSessionManager hoặc persistence qua request.

**Không kiểm tra serializer.**  
Session có thể lưu thành công nhưng không tải lại được sau khi class thay đổi.

**Nhầm timeout cookie và server session.**  
Cookie còn tồn tại không có nghĩa session vẫn hợp lệ; server phải kiểm tra repository.

**Trộn WebFlux và MVC starter.**  
Spring Boot có thể tự cấu hình MVC. Kiểm tra classpath và application type.

## 21. Checklist hoàn thành bài thực hành

### Project và cấu hình

- Có spring-boot-starter-webflux.
- Có module/starter Spring Session Redis phù hợp Boot version.
- Có Spring Data Redis và ReactiveRedisConnectionFactory.
- Ứng dụng khởi động ở reactive mode.
- Không có Servlet HttpSession configuration không cần thiết.
- WebSessionManager được tạo đúng một lần.
- Redis endpoint và namespace được cấu hình.

### Session lifecycle

- Tạo session và cookie.
- Đặt và đọc attributes qua request độc lập.
- Cập nhật attributes và xác minh persistence.
- Đổi Session ID và nhận cookie mới.
- Invalidate và từ chối cookie cũ.
- Timeout và expiration hoạt động.
- Serializer đọc được dữ liệu đã ghi.

### Reactive discipline

- Controller trả Mono/Flux.
- Không gọi block() trong request path.
- Không subscribe() thủ công trong controller.
- Repository I/O không chặn.
- Lỗi backend được giữ thành error signal.
- Test StepVerifier kiểm tra các nhánh thành công và lỗi.

### Security và cluster

- SecurityContext được lưu trong WebSession nếu dùng form login.
- NoOp repository chỉ dùng cho stateless authentication.
- Logout invalidate session.
- Hai instance dùng chung Redis.
- Request node A tạo session, node B đọc được.
- Test Redis unavailable và reconnect.
- Không log cookie, Session ID hoặc SecurityContext.

## 22. Tự kiểm tra

1. WebFlux sử dụng HttpSession hay WebSession?
2. ReactiveSessionRepository có những method chính nào?
3. WebSessionManager làm nhiệm vụ gì?
4. Vì sao @EnableSpringWebSession cần ReactiveSessionRepository bean?
5. Khi nào dùng ReactiveMapSessionRepository?
6. Vì sao ReactiveMapSessionRepository không phù hợp cho nhiều instance?
7. @EnableRedisWebSession tạo thành phần nào?
8. Spring Boot auto-configuration có thể thay thế annotation nào?
9. Vì sao không dùng @EnableRedisHttpSession cho WebFlux?
10. WebSession.changeSessionId() trả về kiểu gì?
11. Vì sao không gọi block() trong controller?
12. CookieWebSessionIdResolver dùng để làm gì?
13. Session timeout khác cookie Max-Age ra sao?
14. Vì sao cần Testcontainers hoặc Redis thật cho integration test?
15. StepVerifier và WebTestClient kiểm tra những lớp nào?
16. Làm thế nào chứng minh hai node chia sẻ cùng session?
17. Vì sao shared Redis không tự giải quyết mọi race condition?
18. Nếu custom repository dùng JDBC blocking, vấn đề gì có thể xảy ra?
19. Vì sao không nên fallback tự động sang map repository khi Redis lỗi?
20. Những thuộc tính nào cần quan sát mà không làm lộ Session ID?

### Gợi ý trả lời

1. WebFlux dùng WebSession.
2. createSession, findById, save và deleteById.
3. Quản lý WebSession cho ServerWebExchange và dùng ReactiveSessionRepository phía dưới.
4. Annotation cần repository để tạo WebSessionManager.
5. Unit test, demo hoặc ứng dụng cục bộ một JVM.
6. Map chỉ nằm trong heap của một node, không chia sẻ và mất khi restart.
7. WebSessionManager dựa trên ReactiveRedisSessionRepository và ReactiveRedisConnectionFactory.
8. Reactive Redis session auto-configuration của Boot có thể tạo WebSessionManager, thay cho @EnableRedisWebSession khi điều kiện phù hợp.
9. Annotation đó cấu hình Servlet HttpSession.
10. Mono<Void>.
11. Có thể chặn Netty event-loop và phá reactive pipeline.
12. Đọc Session ID từ cookie và phát cookie mới/hết hạn.
13. Server timeout quyết định session hợp lệ; cookie Max-Age điều khiển browser giữ cookie.
14. Vì cần kiểm tra serialization, TTL, connection và repository behavior thực tế.
15. StepVerifier kiểm tra reactive signal; WebTestClient kiểm tra HTTP, filter chain, cookie và WebSession persistence.
16. Tạo ở A, lấy cookie, đọc ở B qua cùng Redis.
17. Đọc-sửa-ghi vẫn có thể cạnh tranh; cần atomic operation hoặc concurrency control cho invariant nghiệp vụ.
18. Blocking JDBC có thể làm nghẽn event-loop và giảm throughput.
19. Mỗi node có thể tạo session cục bộ khác nhau, làm mất tính nhất quán và gây lỗi xác thực.
20. Latency, lỗi repository, số session tổng hợp, expiration, serialization và connection pool; không log Session ID/cookie.

## Kết luận

Để xây dựng Spring WebFlux dùng ReactiveSessionRepository, hãy bắt đầu với WebFlux và một repository reactive. Với thử nghiệm cục bộ, ReactiveMapSessionRepository giúp hiểu WebSessionManager và lifecycle; với production nhiều instance, dùng ReactiveRedisSessionRepository hoặc implementation reactive dùng chung khác. @EnableRedisWebSession là cách cấu hình tường minh; Spring Boot reactive auto-configuration có thể thay thế annotation khi dependency và điều kiện phù hợp.

Controller nên thao tác qua WebSession và trả Mono/Flux, không dùng HttpSession, SessionRepository đồng bộ, block() hoặc JDBC blocking trên event-loop. Kiểm thử cần kết hợp StepVerifier cho repository và reactive context, WebTestClient cho cookie và HTTP lifecycle, Redis thật cho serialization/TTL, cùng test hai instance để chứng minh session được chia sẻ. Hoàn tất khi tạo, đọc, đổi ID, invalidate, timeout, SecurityContext và multi-node behavior đều được xác minh bằng repository thực tế.

## Tài liệu chính thức

- [Spring Session WebSession integration](https://docs.spring.io/spring-session/reference/web-session.html)
- [Spring Session API: ReactiveSessionRepository](https://docs.spring.io/spring-session/reference/api.html)
- [Spring Session Redis configuration](https://docs.spring.io/spring-session/reference/configuration/redis.html)
- [Spring Boot Spring Session](https://docs.spring.io/spring-boot/reference/web/spring-session.html)
- [Spring Boot Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)

