# SpringSessionWebSessionStore và ReactiveSessionRepository

Spring WebFlux quản lý phiên qua API `WebSession`. Khi cần chia sẻ phiên giữa nhiều instance, Spring Session cung cấp một lớp tích hợp để thay nơi lưu trữ của WebFlux bằng repository dùng chung. Hai thành phần cốt lõi của tích hợp này là `SpringSessionWebSessionStore` và `ReactiveSessionRepository`.

`ReactiveSessionRepository` chịu trách nhiệm tạo, tìm, lưu và xóa đối tượng `Session` theo cách reactive. `SpringSessionWebSessionStore` là adapter nối repository đó với hợp đồng `WebSessionStore` của Spring WebFlux: nó chuyển đối tượng `Session` do repository quản lý thành `WebSession` mà WebFlux và controller sử dụng.

Nhờ ranh giới này, controller tiếp tục làm việc với `WebSession`, còn Spring Session và repository quyết định dữ liệu được lưu ở Redis hoặc một kho reactive khác. Ứng dụng không phải tự đọc cookie, tự truy vấn Redis hay tự chuyển đổi từng thuộc tính phiên trong mỗi handler.

## Mục tiêu

Sau bài học, bạn có thể:

- Phân biệt `WebSession`, `Session`, `WebSessionStore` và `ReactiveSessionRepository`.
- Giải thích vai trò của `SpringSessionWebSessionStore` trong tích hợp WebFlux.
- Hiểu hợp đồng reactive của các phương thức repository.
- Bật tích hợp bằng `@EnableSpringWebSession` hoặc `@EnableRedisWebSession`.
- Phân biệt repository trong bộ nhớ với repository chia sẻ giữa nhiều instance.
- Tránh gọi blocking API trong luồng xử lý reactive.
- Kiểm thử vòng đời phiên qua `WebTestClient` và repository thật.

## 1. Vì sao WebFlux cần tích hợp riêng?

Ứng dụng Servlet thường dùng `HttpSession` và filter để thay thế session của container. WebFlux dùng mô hình reactive và API `WebSession`, nên Spring Session cung cấp một cơ chế tích hợp tương ứng với kiến trúc này.

Mục tiêu là để WebFlux có thể tiếp tục cung cấp `WebSession` cho handler, trong khi dữ liệu phiên được lưu bởi repository của Spring Session. Khi repository nằm trong Redis dùng chung, request ở instance A có thể tạo phiên và request tiếp theo ở instance B có thể tải lại phiên bằng cùng session ID.

WebFlux không cần biết cấu trúc Redis, tên key hoặc cách serialize thuộc tính. Nó chỉ cần một `WebSessionManager` được cấu hình với store phù hợp.

## 2. Vai trò của từng thành phần

| Thành phần | Vai trò | API chính |
|---|---|---|
| `WebSession` | API phiên mà handler WebFlux sử dụng | Đọc/ghi attributes, xem ID và timeout, invalidate |
| `Session` | Mô hình phiên độc lập với web framework của Spring Session | ID, thời điểm truy cập, timeout và attributes |
| `WebSessionManager` | Điều phối việc phân giải session ID và lấy phiên cho request | Tạo hoặc truy xuất `WebSession` |
| `WebSessionIdResolver` | Đọc session ID từ request và ghi/xóa ID ở response | Cookie hoặc header |
| `WebSessionStore` | SPI của Spring WebFlux để tạo, tìm, cập nhật thời gian truy cập và xóa `WebSession` | `createWebSession`, `retrieveSession`, `updateLastAccessTime`, `removeSession` |
| `SpringSessionWebSessionStore` | Adapter triển khai `WebSessionStore` bằng Spring Session | Bọc `Session` thành `WebSession` |
| `ReactiveSessionRepository` | Hợp đồng lưu trữ reactive cho đối tượng `Session` | `createSession`, `findById`, `save`, `deleteById` |

Có thể hình dung các lớp theo hướng phụ thuộc:

~~~text
WebFlux handler
      |
      v
   WebSession
      |
      v
WebSessionManager
      |
      v
SpringSessionWebSessionStore
      |
      v
ReactiveSessionRepository
      |
      v
Redis / Map / repository reactive tùy chỉnh
~~~

`SpringSessionWebSessionStore` không phải repository lưu trữ. Nó chuyển đổi giữa hai API. `ReactiveSessionRepository` mới là abstraction thực hiện thao tác với kho dữ liệu.

## 3. SpringSessionWebSessionStore làm gì?

`SpringSessionWebSessionStore<S extends Session>` nằm trong package:

~~~java
org.springframework.session.web.server.session
~~~

Lớp này triển khai `WebSessionStore` và nhận một `ReactiveSessionRepository<S>` trong constructor:

~~~java
SpringSessionWebSessionStore<S extends Session>
        implements WebSessionStore {

    public SpringSessionWebSessionStore(
            ReactiveSessionRepository<S> reactiveSessionRepository) {
        // Repository được dùng để tải và lưu Session.
    }
}
~~~

Đây là chữ ký rút gọn để minh họa quan hệ giữa hai abstraction, không phải mã nguồn đầy đủ của lớp framework. Trong ứng dụng thông thường, không cần tự tạo adapter này. Cấu hình Spring Session sẽ kết nối repository với WebFlux và đăng ký `WebSessionManager`.

Các thao tác store tương ứng với vòng đời phiên:

| Phương thức của store | Công việc |
|---|---|
| `createWebSession()` | Yêu cầu repository tạo `Session`, sau đó bọc nó thành `WebSession` |
| `retrieveSession(sessionId)` | Tìm `Session` theo ID và chuyển thành `WebSession`; nếu không có phiên phù hợp thì kết quả rỗng |
| `updateLastAccessTime(session)` | Cập nhật thời điểm truy cập của phiên và trả về phiên đã được quản lý |
| `removeSession(sessionId)` | Yêu cầu repository xóa phiên theo ID |

Adapter cũng phải giữ đúng ngữ nghĩa của WebFlux: các thao tác lưu/truy xuất được biểu diễn bằng `Mono`, không chặn event loop để chờ database trả kết quả.

## 4. ReactiveSessionRepository là hợp đồng lưu trữ

`ReactiveSessionRepository<S extends Session>` thuộc package:

~~~java
org.springframework.session
~~~

Interface này định nghĩa bốn thao tác:

| Phương thức | Kiểu trả về | Ý nghĩa |
|---|---|---|
| `createSession()` | `Mono<S>` | Tạo một đối tượng `Session` mới có thể được repository lưu |
| `findById(String id)` | `Mono<S>` | Tìm phiên theo ID; nếu không có phiên thì publisher hoàn tất mà không phát ra giá trị |
| `save(S session)` | `Mono<Void>` | Lưu phiên được tạo hoặc tải từ chính repository đó |
| `deleteById(String id)` | `Mono<Void>` | Xóa phiên theo ID; nếu không tìm thấy thì có thể hoàn tất mà không có lỗi |

`Mono` biểu diễn một kết quả bất đồng bộ có tối đa một phần tử. Publisher thường chỉ thực hiện công việc khi được subscribe thông qua chuỗi reactive của framework. Vì vậy, không nên gọi `block()` trong controller hoặc handler để chờ repository hoàn tất.

Repository có thể tối ưu bằng cách trả về một `Session` theo dõi các thay đổi. Khi `save` được gọi, implementation chỉ ghi phần dữ liệu đã thay đổi thay vì serialize và ghi toàn bộ session. Một số implementation có thể ghi thay đổi ngay trong quá trình cập nhật, vì vậy `save` có thể không cần làm thêm nhiều việc.

Một quy tắc quan trọng là dùng `Session` do repository tạo hoặc trả về. Không tự tạo một object `Session` bất kỳ rồi truyền cho repository nếu implementation yêu cầu theo dõi metadata hoặc thay đổi nội bộ.

## 5. Luồng xử lý của một request

Khi request mang cookie session đến WebFlux, các thành phần phối hợp như sau:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant M as WebSessionManager
    participant I as WebSessionIdResolver
    participant W as SpringSessionWebSessionStore
    participant R as ReactiveSessionRepository
    participant H as WebFlux Handler
    C->>M: Request kèm session cookie
    M->>I: Đọc session ID từ request
    I-->>M: Session ID hoặc không có ID
    M->>W: retrieveSession(session ID)
    W->>R: findById(id)
    R-->>W: Session hoặc kết quả rỗng
    W-->>M: WebSession
    M-->>H: Cung cấp WebSession cho request
    H->>H: Đọc/ghi attributes
    H-->>M: Hoàn tất xử lý reactive
    M->>W: Lưu thay đổi hoặc xóa phiên
    W->>R: save(session) hoặc deleteById(id)
    R-->>W: Hoàn tất Mono
    W-->>M: Hoàn tất thao tác store
    M->>I: Cập nhật hoặc hết hạn session ID nếu cần
    I-->>C: Response có Set-Cookie nếu cần
~~~

Sơ đồ thể hiện luồng khái niệm. Thời điểm chính xác phát cookie, bắt đầu session và lưu thay đổi phụ thuộc trạng thái `WebSession`, resolver và repository. Một request không nhất thiết tạo hoặc lưu session mới nếu handler không sử dụng phiên.

## 6. Bật tích hợp tổng quát bằng @EnableSpringWebSession

Nếu ứng dụng đã có một `ReactiveSessionRepository`, có thể dùng `@EnableSpringWebSession` để đăng ký `WebSessionManager` cho WebFlux.

Ví dụ với repository trong bộ nhớ:

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
public class WebFluxSessionConfiguration {

    @Bean
    ReactiveSessionRepository<MapSession> reactiveSessionRepository() {
        return new ReactiveMapSessionRepository(
                new ConcurrentHashMap<>());
    }
}
~~~

`@EnableSpringWebSession` nhập cấu hình tích hợp WebFlux. Cấu hình đó tìm một bean `ReactiveSessionRepository` và tạo bean `WebSessionManager` có tên `webSessionManager`. Manager sử dụng `SpringSessionWebSessionStore` để chuyển các phiên repository thành `WebSession`.

`ReactiveMapSessionRepository` lưu phiên trong một `Map`. Cách này hữu ích cho test hoặc ví dụ chạy một tiến trình. Dữ liệu nằm trong bộ nhớ của JVM, mất khi ứng dụng khởi động lại và không tự chia sẻ giữa nhiều instance. Không dùng repository này làm session store dùng chung cho cụm production.

Annotation tổng quát không tự tạo mọi hạ tầng hết hạn phiên. Việc cleanup và expiration phụ thuộc implementation của repository. Khi dùng repository tùy chỉnh hoặc in-memory, ứng dụng phải hiểu rõ cách phiên hết hạn và được dọn dẹp.

## 7. Dùng Redis cho session chia sẻ giữa nhiều instance

Với ứng dụng WebFlux cần chia sẻ session, có thể dùng `@EnableRedisWebSession`. Annotation này cấu hình repository reactive dựa trên Redis và đăng ký `WebSessionManager` cho WebFlux.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.session.data.redis.config.annotation.web.server.EnableRedisWebSession;

@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession
public class RedisWebFluxSessionConfiguration {

    @Bean
    ReactiveRedisConnectionFactory redisConnectionFactory() {
        return new LettuceConnectionFactory();
    }
}
~~~

Ví dụ dùng Lettuce và cấu hình kết nối mặc định. Trong ứng dụng thực tế, cấu hình host, port, TLS, authentication, database, timeout và connection pool theo môi trường. Với Spring Boot đã tự cấu hình `ReactiveRedisConnectionFactory`, không tạo thêm bean thứ hai nếu không cần thay đổi cách kết nối.

Dependency cần có các thành phần Spring WebFlux, Spring Session Data Redis và Spring Data Redis reactive tương thích với phiên bản Spring Boot/Spring Session của dự án. Dùng dependency management của Spring Boot để giữ các phiên bản thư viện đồng bộ.

`@EnableRedisWebSession` tự tạo cấu hình repository và `webSessionManager`. Không đồng thời khai báo thêm `@EnableSpringWebSession` cùng một repository Redis nếu không có cấu hình tùy chỉnh rõ ràng; hai annotation đều nhằm cấu hình WebSessionManager và có thể tạo bean cạnh tranh.

Khi nhiều instance cùng kết nối một Redis dùng chung, session tạo ở instance A có thể được instance B tải lại. Tất cả node phải thống nhất namespace Redis, serializer, timeout, resolver và chính sách bảo mật cookie.

## 8. Dùng WebSession trong handler reactive

Controller WebFlux thường lấy phiên qua `ServerWebExchange.getSession()`. Phương thức này trả về `Mono<WebSession>`, do đó thao tác với phiên cần nằm trong chuỗi reactive:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class PreferenceController {

    @GetMapping("/preferences")
    public Mono<String> preferences(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    String theme = session.getAttribute("theme");
                    if (theme == null) {
                        theme = "light";
                    }

                    session.getAttributes().put("theme", theme);
                    return "Theme: " + theme;
                });
    }
}
~~~

Ví dụ đọc và ghi một thuộc tính nhỏ. Việc lưu `WebSession` được WebFlux/Spring Session phối hợp thực hiện theo vòng đời request; controller không cần tự gọi `ReactiveSessionRepository.save`.

Để invalidate phiên:

~~~java
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.server.WebSession;

@PostMapping("/logout")
public Mono<Void> logout(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
~~~

Trong ứng dụng Spring Security, nên dùng logout flow đã cấu hình để xóa SecurityContext và thực hiện các handler liên quan. Ví dụ trên chỉ minh họa thao tác invalidate WebSession.

Không gọi `block()` hoặc `subscribe()` thủ công bên trong controller:

~~~java
// Không nên trong WebFlux handler:
WebSession session = exchange.getSession().block();
~~~

`block()` có thể chặn event loop và làm giảm khả năng xử lý đồng thời. Tự gọi `subscribe()` còn tách công việc khỏi lifecycle của request, khiến framework khó theo dõi lỗi và thời điểm hoàn tất. Hãy trả về `Mono` hoặc `Flux` để framework điều phối subscription.

## 9. Session ID resolver và cookie

`ReactiveSessionRepository` không tự đọc cookie. Việc lấy session ID từ request và phát ID về client thuộc trách nhiệm của `WebSessionIdResolver`, thường là cookie resolver trong ứng dụng web.

`WebSessionManager` phối hợp resolver với store:

1. Resolver đọc ID từ cookie hoặc header.
2. Manager yêu cầu store tìm phiên theo ID.
3. Nếu không tìm thấy hoặc không có ID, manager có thể tạo phiên mới khi handler cần phiên.
4. Khi phiên bắt đầu hoặc ID thay đổi, resolver phát cookie phù hợp.
5. Khi phiên bị invalidate, resolver phát cookie hết hạn.

Có thể cung cấp một bean `WebSessionIdResolver` để tùy chỉnh tên cookie và thuộc tính bảo mật. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();
    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(cookie -> cookie
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));
    return resolver;
}
~~~

Đoạn cấu hình này có thể đặt cùng cấu hình Spring Session WebFlux. Trong môi trường local chỉ chạy HTTP, thuộc tính `Secure` cần được điều chỉnh theo profile; production phải dùng HTTPS và cookie `Secure`. `SameSite` cần phù hợp với cách frontend/backend giao tiếp, đồng thời vẫn phải có cơ chế CSRF thích hợp.

## 10. Reactive có nghĩa là repository không chặn

Tên `ReactiveSessionRepository` không chỉ nói rằng phương thức trả về `Mono`. Implementation phải thực hiện I/O theo cách phù hợp với mô hình reactive để không chặn event loop của WebFlux.

Các implementation có sẵn gồm:

- `ReactiveMapSessionRepository`: lưu trong Map, hữu ích cho test và ứng dụng một tiến trình.
- `ReactiveRedisSessionRepository`: lưu session qua Spring Data Redis reactive.
- `ReactiveRedisIndexedSessionRepository`: repository Redis reactive có thêm khả năng index theo principal trong phiên bản hỗ trợ.

Không có repository JDBC blocking tiêu chuẩn nào trở thành reactive chỉ bằng cách đổi kiểu trả về thành `Mono`. Nếu ứng dụng cần SQL reactive, hãy xem xét R2DBC và một implementation `ReactiveSessionRepository` tương thích. Nếu buộc phải gọi API blocking, phải cô lập công việc trên scheduler phù hợp và đánh giá kỹ tải, connection pool, cancellation và timeout; không chạy JDBC blocking trực tiếp trên event loop.

Ví dụ sai:

~~~java
public Mono<MySession> findById(String id) {
    // JDBC blocking chạy ngay trên thread gọi phương thức.
    MySession session = jdbcTemplate.queryForObject(...);
    return Mono.just(session);
}
~~~

`Mono.just` không làm thao tác JDBC ở trên trở thành bất đồng bộ. Lệnh SQL đã chạy trước khi `Mono` được trả về.

## 11. Yêu cầu khi tự triển khai ReactiveSessionRepository

Chỉ nên viết repository riêng khi các implementation có sẵn không đáp ứng yêu cầu lưu trữ. Một implementation cần bảo đảm:

- `createSession()` tạo ID duy nhất và trả về một `Session` có thể được lưu bởi chính repository đó.
- `findById()` trả về `Mono` rỗng khi ID không tồn tại hoặc phiên đã hết hạn theo chính sách.
- `save()` lưu metadata và thuộc tính, cập nhật thời gian truy cập/expiration phù hợp.
- `deleteById()` xóa phiên và dữ liệu phụ trợ liên quan.
- Các thao tác I/O không chặn event loop.
- Lỗi lưu trữ được phát thành error signal, không bị nuốt hoặc biến thành session rỗng ngoài ý muốn.
- Các thay đổi thuộc tính được xử lý an toàn khi nhiều request cùng truy cập phiên.
- Serialization có phiên bản và tương thích giữa các instance.

`createSession()` nên tạo đối tượng có thể theo dõi thay đổi để repository có thể ghi delta nếu phù hợp. Điều này giảm dữ liệu phải serialize và cập nhật, đặc biệt khi session có nhiều thuộc tính.

Repository cũng cần quy định rõ cách xử lý hết hạn. Interface cơ bản không tự định nghĩa một scheduler cleanup cho mọi implementation. Redis có TTL và cơ chế expiration riêng; repository in-memory hoặc custom store phải tự cung cấp cách phát hiện và dọn phiên quá hạn.

## 12. Timeout và vòng đời phiên

`Session` cung cấp thông tin thời gian tạo, lần truy cập gần nhất và khoảng không hoạt động tối đa. `SpringSessionWebSessionStore` chuyển các giá trị đó sang semantics của `WebSession`.

Khi một request sử dụng phiên, thời điểm truy cập cần được cập nhật. Khi phiên vượt quá thời gian inactivity, repository không nên trả về phiên như một phiên còn hoạt động. Việc xóa vật lý có thể diễn ra ngay hoặc thông qua cleanup/TTL tùy implementation.

Không nhầm:

- Cookie lifetime: thời gian trình duyệt giữ cookie session ID.
- Session inactivity timeout: khoảng không hoạt động trước khi phiên hết hiệu lực ở server.
- Cleanup schedule: thời điểm repository dọn dữ liệu hết hạn khỏi kho lưu trữ.

Ba mốc này liên quan nhưng không đồng nhất. Cookie còn tồn tại không chứng minh session trong repository còn hợp lệ.

## 13. Kiểm thử tích hợp WebFlux và repository

Nên kiểm thử qua HTTP để xác minh toàn bộ đường đi từ cookie tới repository, thay vì chỉ gọi trực tiếp một method của repository.

Các tình huống cơ bản:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Request đầu tiên chưa có session cookie | Handler lấy phiên mới khi cần; response phát session ID |
| Request sau gửi cookie hợp lệ | WebFlux tải lại cùng session và đọc được thuộc tính trước đó |
| Handler thay đổi thuộc tính | Request tiếp theo đọc được giá trị đã cập nhật |
| Invalidate phiên | Repository xóa hoặc vô hiệu hóa phiên; response hết hạn cookie |
| Gửi lại cookie cũ | Repository không trả phiên đã bị xóa/hết hạn |
| Session vượt timeout | Request mới không được sử dụng phiên hết hạn |
| Hai instance dùng chung Redis | Phiên tạo ở instance A được đọc ở instance B |
| Redis không khả dụng | Request nhận lỗi theo chính sách; lỗi được quan sát và không bị biến thành phiên mới âm thầm |

Ví dụ test khái niệm với `WebTestClient`:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebSessionIntegrationTests {

    @Autowired
    WebTestClient client;

    @Test
    void sessionAttributeIsAvailableOnNextRequest() {
        EntityExchangeResult<String> first = client.get()
                .uri("/preferences")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().exists("Set-Cookie")
                .expectBody(String.class)
                .returnResult();

        String setCookie = first.getResponseHeaders()
                .getFirst("Set-Cookie");

        // Tách cookie pair theo chính sách test, rồi gửi lại ở request sau.
        client.get()
                .uri("/preferences")
                .header("Cookie", extractCookiePair(setCookie))
                .exchange()
                .expectStatus().isOk();
    }
}
~~~

Đây là khung minh họa; `extractCookiePair` là helper của test cần tự triển khai để bỏ các thuộc tính `Path`, `HttpOnly`, `SameSite` khỏi header `Set-Cookie`. Với test thực tế, có thể dùng cookie store của HTTP client hoặc `WebTestClient` builder phù hợp để quản lý cookie.

Khi dùng Redis, chạy test với Redis test instance thay vì chỉ mock `ReactiveSessionRepository`. Mock xác minh handler gọi đúng API, nhưng không chứng minh TTL, serialization, cookie và khả năng chia sẻ phiên giữa hai instance.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `@EnableSpringWebSession` báo thiếu repository | Không có bean `ReactiveSessionRepository` hoặc bean sai kiểu | Cung cấp đúng một reactive repository |
| Mỗi request tạo session mới | Cookie resolver không đọc được ID hoặc repository không tìm thấy phiên | Kiểm tra cookie, resolver, namespace và repository |
| Ứng dụng WebFlux bị chậm hoặc treo | Gọi `block()` hoặc thực hiện JDBC blocking trên event loop | Giữ chuỗi reactive; dùng repository reactive phù hợp |
| Session chỉ tồn tại ở một instance | Dùng `ReactiveMapSessionRepository` trong từng JVM | Dùng repository chia sẻ như reactive Redis |
| Không thấy dữ liệu được lưu | Publisher không được nối vào lifecycle hoặc thay đổi session không được commit theo cách dự kiến | Trả `Mono` từ handler và kiểm thử request tiếp theo |
| Cookie bị phát nhưng request sau không dùng được | Cookie path/domain/SameSite/Secure không phù hợp hoặc session đã hết hạn | Kiểm tra `Set-Cookie`, request Cookie và TTL server |
| Phiên hết hạn nhưng dữ liệu vẫn còn | Repository cleanup hoặc TTL chưa dọn vật lý | Phân biệt hiệu lực phiên với cleanup vật lý |
| Redis lỗi bị coi như phiên mới | Error signal bị nuốt và thay bằng `Mono.empty()` không đúng ngữ nghĩa | Phân biệt “không tìm thấy” với lỗi kết nối; phát lỗi lưu trữ rõ ràng |

## 15. Checklist triển khai

- [ ] Ứng dụng dùng Spring WebFlux và API `WebSession`.
- [ ] Có đúng một `ReactiveSessionRepository` phù hợp với môi trường.
- [ ] Hiểu `SpringSessionWebSessionStore` là adapter giữa repository và `WebSessionStore`.
- [ ] `WebSessionManager` được đăng ký thông qua `@EnableSpringWebSession` hoặc `@EnableRedisWebSession`.
- [ ] Không tạo đồng thời nhiều cấu hình session manager cạnh tranh.
- [ ] Repository thực hiện I/O theo cách reactive, không chặn event loop.
- [ ] Mọi instance dùng chung repository, namespace, serializer và timeout.
- [ ] Cookie resolver được cấu hình đúng cho HTTPS, path, domain và SameSite.
- [ ] Timeout và cleanup được triển khai theo khả năng của repository.
- [ ] Có test tạo, đọc, cập nhật, invalidate và hết hạn session.
- [ ] Có integration test với Redis và nhiều instance nếu chạy theo cụm.
- [ ] Log không ghi session ID, cookie hoặc thuộc tính nhạy cảm.

`ReactiveSessionRepository` là hợp đồng lưu trữ reactive cho đối tượng `Session`; `SpringSessionWebSessionStore` chuyển hợp đồng đó thành `WebSessionStore` để WebFlux sử dụng. `@EnableSpringWebSession` kết nối một repository reactive do ứng dụng cung cấp, còn `@EnableRedisWebSession` cấu hình tích hợp Redis reactive. Hãy chọn repository phù hợp với yêu cầu chia sẻ phiên, giữ I/O không blocking và kiểm thử toàn bộ vòng đời cookie-session trên môi trường gần production.
