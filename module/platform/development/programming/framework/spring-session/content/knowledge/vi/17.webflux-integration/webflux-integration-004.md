# Bean webSessionManager và cấu hình thay thế kho phiên

Trong ứng dụng Spring WebFlux, trạng thái phiên được biểu diễn bằng `WebSession`. WebFlux không dùng `HttpSession` và Servlet `Filter` để quản lý session như ứng dụng MVC/Servlet. Thay vào đó, WebFlux lấy một `WebSessionManager` để tìm hoặc tạo phiên cho mỗi `ServerWebExchange`. Manager này dùng `WebSessionStore` để thao tác với kho phiên và `WebSessionIdResolver` để đọc/ghi định danh phiên qua cookie hoặc header.

Spring Session tích hợp với WebFlux bằng `ReactiveSessionRepository`. Adapter `SpringSessionWebSessionStore` chuyển đổi giữa repository reactive và hợp đồng `WebSessionStore` của Spring WebFlux. Vì vậy, ứng dụng có thể thay kho lưu session mà vẫn tiếp tục dùng API `WebSession` trong controller, handler và Spring Security.

## 1. Các thành phần trong quản lý WebSession

Các thành phần chính có vai trò riêng:

| Thành phần | Vai trò |
|---|---|
| `WebSession` | API phiên của WebFlux: ID, attributes, thời điểm tạo/truy cập, idle timeout, invalidate và save |
| `WebSessionManager` | Tìm hoặc tạo `WebSession` cho một `ServerWebExchange` |
| `DefaultWebSessionManager` | Manager mặc định, phối hợp resolver và store |
| `WebSessionStore` | Hợp đồng lưu trữ mà WebFlux manager sử dụng để tạo, tìm, cập nhật và xóa WebSession |
| `SpringSessionWebSessionStore` | Adapter của Spring Session nối `ReactiveSessionRepository` với `WebSessionStore` |
| `ReactiveSessionRepository` | API reactive tạo, tìm, lưu và xóa session trong kho dữ liệu |
| `WebSessionIdResolver` | Đọc session ID từ request và ghi/xóa ID trên response |
| `CookieWebSessionIdResolver` | Resolver dùng cookie để truyền session ID |

Trong quá trình xử lý request, WebFlux lấy `WebSessionManager` từ application context. Manager gọi resolver để lấy session ID, sau đó dùng store để nạp session. Nếu không có session hợp lệ, manager có thể tạo phiên mới khi ứng dụng cần. Khi response hoàn tất, các thay đổi được lưu qua store và repository theo vòng đời WebSession.

## 2. WebSessionManager là điểm nối của WebFlux

`WebSessionManager` có phương thức cốt lõi `getSession(ServerWebExchange)`, trả về `Mono<WebSession>`. Vì kết quả là `Mono`, thao tác lấy session nằm trong reactive pipeline và không yêu cầu chặn thread để chờ database hoặc Redis.

```java
public interface WebSessionManager {
    Mono<WebSession> getSession(ServerWebExchange exchange);
}
```

Đoạn mã trên minh họa hợp đồng API. `ServerWebExchange` đại diện cho request/response hiện tại trong WebFlux. Các thành phần phía trên như controller, WebFilter hoặc Spring Security có thể truy cập session thông qua exchange.

Ví dụ controller đọc và cập nhật một thuộc tính:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
class WebFluxSessionController {

    @PostMapping("/web/session/start")
    Mono<ResponseEntity<String>> start(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(session -> {
                    session.getAttributes().put("cartId", "CART-42");
                    return session.save()
                            .thenReturn(ResponseEntity.ok("Session saved"));
                });
    }

    @GetMapping("/web/session/cart")
    Mono<ResponseEntity<String>> cart(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    String cartId = session.getAttribute("cartId");
                    return cartId == null
                            ? ResponseEntity.<String>notFound().build()
                            : ResponseEntity.ok(cartId);
                });
    }
}
```

`exchange.getSession()` trả về `Mono<WebSession>`. Việc gọi `save()` tường minh trong ví dụ làm rõ điểm lưu; WebFlux/Spring Session cũng quản lý việc lưu phiên theo vòng đời request/response và trạng thái session. Hãy giữ các thao tác repository bên trong reactive chain, không gọi `block()` trong controller hoặc WebFilter.

## 3. ReactiveSessionRepository và SpringSessionWebSessionStore

`ReactiveSessionRepository<S extends Session>` là abstraction lưu trữ phiên theo kiểu reactive. Các thao tác chính thường gồm:

| Phương thức | Kết quả | Ý nghĩa |
|---|---|---|
| `createSession()` | `Mono<S>` | Tạo session mới |
| `findById(String id)` | `Mono<S>` | Tìm session theo ID; có thể rỗng nếu không tồn tại/hết hạn |
| `save(S session)` | `Mono<Void>` | Lưu session hoặc thay đổi của session |
| `deleteById(String id)` | `Mono<Void>` | Xóa session theo ID |

Repository không phải là `SessionRepository` imperative dùng cho Servlet. `JdbcIndexedSessionRepository` triển khai API đồng bộ; `ReactiveSessionRepository` yêu cầu các thao tác trả về publisher reactive. Hai hợp đồng này không thể thay thế trực tiếp cho nhau.

`SpringSessionWebSessionStore<S>` là adapter do Spring Session cung cấp. Nó nhận một `ReactiveSessionRepository<S>` và triển khai `WebSessionStore` để `DefaultWebSessionManager` làm việc với WebSession. Nhờ adapter, ứng dụng không cần tự viết mã chuyển đổi giữa `WebSession` và `Session` của Spring Session.

## 4. Để Spring Session cấu hình WebSessionManager mặc định

Với ứng dụng muốn dùng tích hợp tiêu chuẩn, `@EnableSpringWebSession` bật hỗ trợ Spring Session cho WebFlux. Ứng dụng cung cấp một bean `ReactiveSessionRepository`; cấu hình Spring Session tạo adapter và manager để WebFlux sử dụng.

Ví dụ repository in-memory phục vụ phát triển hoặc kiểm thử:

```java
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.MapReactiveSessionRepository;
import org.springframework.session.MapSession;
import org.springframework.session.ReactiveSessionRepository;
import org.springframework.session.config.annotation.web.server.EnableSpringWebSession;

@Configuration
@EnableSpringWebSession
class InMemoryWebSessionConfiguration {

    @Bean
    ReactiveSessionRepository<MapSession> reactiveSessionRepository() {
        return new MapReactiveSessionRepository(new ConcurrentHashMap<>());
    }
}
```

Repository in-memory phù hợp để minh họa API, kiểm thử đơn giản hoặc chạy một instance. Dữ liệu không được chia sẻ giữa các process và có thể mất khi ứng dụng khởi động lại. Không dùng repository này làm kho session dùng chung cho production nhiều instance.

Khi dùng `@EnableSpringWebSession`, hãy để cấu hình Spring Session cung cấp `WebSessionManager` mặc định. Chỉ khai báo manager riêng khi có yêu cầu thay đổi cách quản lý session và đã xác định rõ bean mặc định được đăng ký như thế nào trong phiên bản đang dùng.

## 5. Thay kho phiên bằng Redis reactive

Đối với ứng dụng WebFlux cần chia sẻ session giữa nhiều instance, Redis là lựa chọn phổ biến. Spring Session Data Redis cung cấp tích hợp reactive riêng cho WebFlux thông qua `@EnableRedisWebSession` và `ReactiveRedisSessionRepository`.

Ví dụ cấu hình cơ bản:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
class RedisWebSessionConfiguration {
    // RedisConnectionFactory/reactive Redis infrastructure được cấu hình trong context.
}
```

Annotation dành cho WebFlux nằm trong package `org.springframework.session.data.redis.config.annotation.web.server`. Không nhầm với `@EnableRedisHttpSession` dành cho Servlet. Cấu hình reactive tạo repository phù hợp và tích hợp với WebSession manager. Timeout trong ví dụ là 30 phút tính theo idle timeout.

Với Spring Boot, có thể cấu hình kết nối Redis và thời hạn phiên bằng các property được phiên bản Boot hỗ trợ:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  session:
    timeout: 30m
    redis:
      namespace: storefront:web-sessions
```

Kiểm tra property metadata của đúng phiên bản Spring Boot/Spring Session. Tên property và cơ chế auto-configuration có thể thay đổi giữa các release. Hãy xác nhận ứng dụng đang tạo reactive repository và WebSession manager tương ứng, không phải repository Servlet.

## 6. Tự khai báo bean webSessionManager khi cần thay store

Nếu cần tự điều khiển `WebSessionStore` hoặc resolver, có thể tạo `DefaultWebSessionManager` và đặt adapter `SpringSessionWebSessionStore` vào manager. Trong trường hợp này, application context chỉ nên có một manager được WebFlux sử dụng. Không đồng thời đăng ký một manager mặc định từ annotation và một manager tùy chỉnh mà không có cơ chế thay thế rõ ràng.

Ví dụ sau minh họa wiring manager với một reactive repository:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.session.ReactiveSessionRepository;
import org.springframework.session.Session;
import org.springframework.session.web.server.SpringSessionWebSessionStore;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.DefaultWebSessionManager;
import org.springframework.web.server.session.WebSessionManager;

@Configuration
class CustomWebSessionManagerConfiguration {

    @Bean
    WebSessionManager webSessionManager(
            ReactiveSessionRepository<? extends Session> repository) {
        return createManager(repository);
    }

    private static <S extends Session> WebSessionManager createManager(
            ReactiveSessionRepository<S> repository) {
        SpringSessionWebSessionStore<S> store =
                new SpringSessionWebSessionStore<>(repository);

        DefaultWebSessionManager manager = new DefaultWebSessionManager();
        manager.setSessionStore(store);

        CookieWebSessionIdResolver resolver = new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));
        manager.setSessionIdResolver(resolver);

        return manager;
    }
}
```

Đây là cấu hình thủ công cho trường hợp ứng dụng tự sở hữu bean `WebSessionManager`. Bean `ReactiveSessionRepository` phải được cung cấp riêng. Có thể dùng repository in-memory trong môi trường thử nghiệm hoặc repository reactive Redis trong production. Nếu dùng `@EnableRedisWebSession` hay `@EnableSpringWebSession` vốn đã đăng ký manager, hãy theo cơ chế tùy chỉnh/ghi đè được tài liệu đúng phiên bản hỗ trợ thay vì thêm manager thứ hai.

`secure(true)` phù hợp khi ứng dụng chạy qua HTTPS. Trong môi trường local HTTP, có thể dùng cấu hình profile phát triển riêng; không hạ cấu hình production chỉ để tiện kiểm thử. Nếu chạy sau reverse proxy, cần cấu hình forwarded headers và proxy tin cậy để scheme HTTPS được nhận diện chính xác.

## 7. Thay resolver cookie bằng header

`WebSessionIdResolver` độc lập với repository. Có thể giữ nguyên Redis repository nhưng thay cách truyền session ID từ cookie sang header. Ví dụ resolver header:

```java
import org.springframework.web.server.session.HeaderWebSessionIdResolver;

HeaderWebSessionIdResolver resolver =
        new HeaderWebSessionIdResolver("X-SESSION-ID");
manager.setSessionIdResolver(resolver);
```

Header resolver có thể phù hợp với một số API client không dùng cookie jar. Tuy nhiên, session ID vẫn là credential dạng bearer; phải bảo vệ header qua HTTPS, không ghi header vào access log và không đưa ID vào URL. Cần cân nhắc CSRF theo cách trình duyệt gửi credential: cookie tự động được đính kèm có đặc tính rủi ro khác với header do client chủ động thiết lập.

Với cookie resolver, cần cấu hình `HttpOnly`, `Secure`, `SameSite`, `Path` và domain theo kiến trúc. Cookie session ID không nên được đọc bằng JavaScript khi không có yêu cầu đặc biệt.

## 8. Thay đổi kho phiên không đồng nghĩa thay API WebSession

Điểm mạnh của `WebSessionManager` và `WebSessionStore` là tách API phiên khỏi backend. Controller tiếp tục thao tác `WebSession`; repository có thể đổi từ in-memory sang Redis hoặc một implementation reactive khác.

| Thay đổi | Thành phần cần thay |
|---|---|
| Từ in-memory sang Redis reactive | `ReactiveSessionRepository` và cấu hình Redis; manager có thể giữ nguyên nếu adapter không đổi |
| Đổi cookie name hoặc thuộc tính cookie | `WebSessionIdResolver` |
| Dùng header thay cookie | `WebSessionIdResolver` |
| Tùy chỉnh cách tạo/tìm phiên | `WebSessionManager` hoặc `WebSessionStore` |
| Dùng định dạng session riêng | `ReactiveSessionRepository` và serializer của backend |
| Thay đổi API controller | Thường không cần nếu vẫn dùng `WebSession` |

Không nên viết lại controller để gọi trực tiếp Redis khi chỉ cần thay backend session. Điều đó làm ứng dụng phụ thuộc cấu trúc lưu trữ và khó chuyển repository về sau.

## 9. Giới hạn JDBC trong WebFlux

Spring Session JDBC tiêu chuẩn dùng `JdbcIndexedSessionRepository`, một repository đồng bộ dành cho Servlet session. Nó không triển khai `ReactiveSessionRepository` và không thể cắm trực tiếp vào `SpringSessionWebSessionStore`.

Nếu ứng dụng WebFlux cần lưu phiên trong một cơ sở dữ liệu quan hệ, hãy chọn giải pháp có API reactive, ví dụ một `ReactiveSessionRepository` tùy chỉnh xây trên R2DBC. Không gọi JDBC blocking trực tiếp trên event-loop thread, không dùng `.block()` trong WebFlux và không giả định bọc một lệnh JDBC trong `Mono.fromCallable()` sẽ biến driver đồng bộ thành non-blocking.

Trong trường hợp chuyển tiếp bắt buộc dùng JDBC, tác vụ blocking phải được cô lập khỏi event loop bằng scheduler phù hợp như `boundedElastic`, có giới hạn concurrency và connection pool. Cách này chỉ cô lập blocking; nó không biến JDBC thành driver reactive và cần đánh giá kỹ throughput, timeout và áp lực thread. Với hệ thống mới, ưu tiên repository reactive thực sự.

## 10. Tích hợp với Spring Security reactive

Spring Security WebFlux dùng `SecurityContextRepository` reactive để lưu và khôi phục `SecurityContext`. Khi chính sách bảo mật lưu context trong WebSession, repository thường dùng là `WebSessionServerSecurityContextRepository`.

Khi `WebSessionManager` được cấu hình đúng, Spring Security và controller cùng truy cập WebSession theo cùng một luồng quản lý. Trong môi trường nhiều instance, Redis repository dùng chung giúp request được chuyển sang node khác vẫn có thể khôi phục context.

Không dùng `HttpSessionSecurityContextRepository` hoặc Servlet `SecurityContextPersistenceFilter` trong ứng dụng WebFlux thuần reactive. Hãy dùng cấu hình Spring Security reactive và kiểm tra chính sách session creation phù hợp với ứng dụng.

Nếu dùng bearer token stateless, ứng dụng có thể không cần tạo WebSession cho request đó. Tránh vô tình gọi `exchange.getSession()` trong filter logging hoặc tracing nếu không cần, vì thao tác này có thể khởi tạo session và tạo cookie không mong muốn tùy cách session được sử dụng.

## 11. Session ID rotation, timeout và invalidate

`WebSession` cung cấp các thao tác như `changeSessionId()`, `setMaxIdleTime(Duration)` và `invalidate()`. Đây là API reactive; thao tác lưu/xóa phải được kết nối vào pipeline.

Ví dụ kết thúc session:

```java
Mono<Void> logout(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
```

Trong ứng dụng Spring Security, nên dùng logout handler reactive để dọn `SecurityContext`, session và cookie theo cấu hình bảo mật. Không chỉ xóa cookie ở client mà bỏ session ở repository, và không chỉ xóa session server mà quên xử lý cookie resolver.

Idle timeout của WebSession thường được lưu cùng session và áp dụng khi repository xử lý request. Nó không thay thế absolute timeout. Nếu cần giới hạn tổng thời gian đăng nhập, lưu timestamp xác thực và kiểm tra trên mỗi request được bảo vệ.

## 12. Nhiều instance cùng dùng một reactive repository

Để session được chia sẻ khi load balancer chuyển request giữa các instance, mọi node cần thống nhất:

- Cùng Redis deployment hoặc reactive repository dùng chung.
- Cùng namespace, serializer và định dạng session attributes.
- Cùng cookie name, path, domain, SameSite và cách resolver đọc ID.
- Cùng idle timeout, absolute timeout và chính sách xác thực.
- Cùng phiên bản Spring Session/Spring Security hoặc khả năng tương thích dữ liệu trong rolling deployment.

Repository in-memory chỉ lưu dữ liệu trong process nên không thể chia sẻ giữa các node. Sticky session ở load balancer cũng không thay thế kho dùng chung: khi node restart hoặc failover, dữ liệu in-memory có thể mất.

Không để một node dùng reactive Redis repository trong khi node khác dùng in-memory repository hoặc một namespace khác. Người dùng có thể đăng nhập thành công ở node A nhưng bị xem là chưa có session ở node B.

## 13. Kiểm thử WebSessionManager và thay kho phiên

Kiểm thử nên xác nhận cả API WebFlux lẫn backend repository. Có thể dùng `WebTestClient` để kiểm tra cookie và request nối tiếp, cùng Redis test instance cho tích hợp thực tế.

Các kịch bản quan trọng:

1. **Tạo phiên:** gửi request tạo attribute và xác nhận response phát hành cookie session ID theo resolver.
2. **Đọc lại phiên:** gửi request tiếp theo cùng cookie và xác nhận attribute được khôi phục.
3. **Thay repository:** ghi bằng một request và xác nhận repository nhận đúng thao tác create/save/find/delete.
4. **Cookie policy:** kiểm tra `HttpOnly`, `Secure`, `SameSite`, `Path` và tên cookie.
5. **Header resolver:** nếu dùng header, xác nhận request đọc ID và response phát ID đúng header.
6. **Invalidate:** logout, xác nhận session bị xóa và cookie/header được xử lý phù hợp.
7. **Idle timeout:** đặt timeout ngắn và xác nhận session không còn được chấp nhận sau khoảng không hoạt động.
8. **Nhiều instance:** tạo session qua node A, gửi cookie tới node B và xác nhận dữ liệu được chia sẻ.
9. **Spring Security:** xác nhận SecurityContext và principal được khôi phục qua request reactive tiếp theo.
10. **Non-blocking:** kiểm tra không có `.block()` hoặc JDBC blocking trên event-loop thread.

Với repository tùy chỉnh, có thể dùng test double để xác nhận các phương thức reactive được gọi đúng. Nhưng test double không xác minh TTL, serialization hoặc tính chia sẻ. Cần integration test với Redis/R2DBC/database tương ứng trước khi triển khai.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Mỗi request tạo session mới | Cookie không được gửi lại, resolver khác nhau hoặc repository không tìm thấy ID | Kiểm tra `Set-Cookie`, request cookie/header và namespace |
| Bean `WebSessionManager` bị trùng | Kết hợp annotation auto-config với manager tùy chỉnh | Kiểm tra bean theo type/name; chỉ giữ một manager được WebFlux sử dụng |
| Session có ở node A nhưng không có ở B | Dùng repository in-memory, namespace khác hoặc serializer khác | So sánh repository và cấu hình giữa các node |
| Lỗi kiểu khi dùng repository | Inject `SessionRepository` imperative thay vì `ReactiveSessionRepository` | Kiểm tra generic type và implementation được tạo |
| WebFlux bị chậm hoặc treo event loop | Gọi `.block()` hoặc dùng JDBC blocking trên event loop | Kiểm tra thread dump, BlockHound/test và reactive chain |
| Cookie không xuất hiện qua HTTPS proxy | Scheme không được nhận diện hoặc resolver/cookie policy sai | Kiểm tra forwarded headers, proxy trust và `Secure` |
| Spring Security không giữ đăng nhập | Dùng Servlet security repository hoặc session manager không đúng | Kiểm tra reactive SecurityContextRepository và WebSessionManager |
| Logout nhưng ID cũ còn được gửi | Cookie path/domain khi xóa không khớp hoặc chưa invalidate session | Kiểm tra logout handler, repository và response cookie |

Khi điều tra, ghi nhận request correlation ID, tên instance, loại repository và kết quả tìm session. Không log session ID, cookie value, SecurityContext hoặc toàn bộ session attributes.

## 15. Nguyên tắc triển khai

- WebFlux dùng `WebSession` và `WebSessionManager`; Servlet dùng `HttpSession` và `SessionRepositoryFilter`.
- `WebSessionManager` phối hợp `WebSessionIdResolver` và `WebSessionStore` để tìm/tạo phiên.
- `SpringSessionWebSessionStore` nối `ReactiveSessionRepository` với WebFlux `WebSessionStore`.
- Dùng `@EnableSpringWebSession` cho tích hợp reactive tổng quát hoặc `@EnableRedisWebSession` cho Redis reactive theo phiên bản hỗ trợ.
- Khi tự khai báo bean `webSessionManager`, bảo đảm chỉ có một manager được WebFlux sử dụng và repository được cung cấp đúng kiểu reactive.
- `JdbcIndexedSessionRepository` đồng bộ không phải reactive repository; dùng R2DBC/custom reactive repository nếu cần lưu quan hệ trong WebFlux.
- Giữ thao tác session trong reactive pipeline; không chặn event loop bằng `.block()` hoặc JDBC blocking.
- Đồng bộ repository, cookie resolver, serializer và timeout giữa các instance.
- Kiểm thử cookie, đọc/ghi, invalidate, timeout, Spring Security và đọc chéo node bằng WebTestClient cùng backend thực tế.
