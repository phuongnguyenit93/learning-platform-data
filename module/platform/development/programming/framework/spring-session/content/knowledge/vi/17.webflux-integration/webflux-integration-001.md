# WebSession và khác biệt với HttpSession của Servlet

Spring Session có thể quản lý phiên cho cả ứng dụng Servlet và ứng dụng reactive dùng Spring WebFlux. Hai stack đều cung cấp khái niệm phiên để giữ dữ liệu giữa nhiều request, nhưng API và vòng đời của chúng khác nhau. Servlet sử dụng `HttpSession` với các thao tác đồng bộ; WebFlux sử dụng `WebSession` và các publisher reactive để phối hợp việc tải, lưu, đổi ID hoặc vô hiệu hóa phiên mà không chặn event loop.

Khi dùng WebFlux, request được biểu diễn bởi `ServerWebExchange`, phiên được truy cập qua `exchange.getSession()` trả về `Mono<WebSession>`. Spring Session kết nối `WebSession` với một repository reactive như Redis để nhiều instance có thể đọc cùng trạng thái. Vì vậy, không thể chỉ thay kiểu `HttpSession` thành `WebSession` trong mã Servlet rồi mong mọi filter, security configuration và repository hoạt động giống nhau.

## 1. Hai mô hình phiên phục vụ hai web stack

`HttpSession` thuộc Servlet API. Servlet container quản lý phiên và cung cấp đối tượng đồng bộ cho request. Spring Session tích hợp vào stack này bằng `SessionRepositoryFilter`, bọc `HttpServletRequest` và `HttpServletResponse` để chuyển thao tác `HttpSession` sang repository.

`WebSession` thuộc Spring WebFlux. Nó được truy cập trong reactive request qua `ServerWebExchange`. WebFlux dùng `WebSessionManager` để tìm hoặc tạo phiên, và `WebSessionStore` là abstraction lưu trữ phía dưới. Spring Session cung cấp tích hợp để store dùng repository reactive, chẳng hạn repository reactive cho Redis.

| Tiêu chí | Servlet `HttpSession` | WebFlux `WebSession` |
| --- | --- | --- |
| Web stack | Spring MVC/Servlet | Spring WebFlux/reactive server |
| Request context | `HttpServletRequest` | `ServerWebExchange` |
| Lấy session | `request.getSession()` hoặc `getSession(false)` | `exchange.getSession()` trả `Mono<WebSession>` |
| Kiểu thao tác | API đồng bộ | API có các thao tác lifecycle trả publisher reactive |
| Đọc/ghi attribute | `getAttribute`, `setAttribute`, `removeAttribute` | `getAttributes()` trả map; thay đổi map được quản lý trong vòng đời WebSession |
| Đổi session ID | `request.changeSessionId()` trả ID mới | `webSession.changeSessionId()` trả `Mono<Void>` |
| Vô hiệu hóa | `session.invalidate()` đồng bộ | `webSession.invalidate()` trả `Mono<Void>` |
| Lưu phiên | Servlet/Spring Session lưu theo vòng đời request và filter | WebFlux lưu qua lifecycle của WebSession và response commit; `save()` là reactive |
| Security integration | `SecurityContextRepository` và Servlet filter chain | `ServerSecurityContextRepository` và `SecurityWebFilterChain` |
| Tích hợp Spring Session | `SessionRepositoryFilter` | `WebSessionManager`/`WebSessionStore` với reactive repository |

Hai API có cùng mục tiêu nhưng không cùng kiểu và không thay thế trực tiếp cho nhau. Ứng dụng cần chọn đúng Spring Session integration theo web stack mà nó thực sự chạy.

## 2. Vòng đời của WebSession

Trong WebFlux, controller hoặc filter lấy phiên bằng `ServerWebExchange.getSession()`. Phương thức trả `Mono<WebSession>` vì việc tìm hoặc tạo phiên có thể cần truy cập repository bất đồng bộ. Mã ứng dụng cần kết hợp publisher này với các toán tử Reactor như `map`, `flatMap` hoặc `switchIfEmpty` theo đúng kiểu dữ liệu.

`WebSession` có thể được tạo một cách lazy. Việc lấy đối tượng session chưa nhất thiết có nghĩa một bản ghi mới đã được ghi vào kho dữ liệu. Phiên bắt đầu khi ứng dụng gọi `start()` hoặc thêm thuộc tính; khi đó WebFlux có thể phát session ID trong response và lưu trạng thái theo lifecycle. Cách hoạt động chi tiết còn phụ thuộc `WebSessionManager`, `WebSessionStore` và repository được cấu hình.

Các phương thức thường dùng của `WebSession`:

| Phương thức | Mục đích |
| --- | --- |
| `getId()` | Lấy session ID hiện tại |
| `getAttributes()` | Lấy map các thuộc tính phiên |
| `getCreationTime()` | Thời điểm tạo phiên |
| `getLastAccessTime()` | Thời điểm truy cập gần nhất |
| `getMaxIdleTime()` / `setMaxIdleTime(...)` | Đọc hoặc thay đổi idle timeout |
| `isStarted()` | Kiểm tra phiên đã bắt đầu hay chưa |
| `isExpired()` | Kiểm tra trạng thái hết hạn |
| `start()` | Bắt đầu phiên nếu chưa bắt đầu |
| `changeSessionId()` | Đổi định danh phiên, trả `Mono<Void>` |
| `invalidate()` | Vô hiệu hóa phiên, trả `Mono<Void>` |
| `save()` | Lưu phiên, trả `Mono<Void>` |

Trong request thông thường, WebFlux quản lý việc lưu phiên theo lifecycle và response commit. Phần lớn controller không cần tự gọi `save()` sau mỗi lần sửa thuộc tính. Gọi `save()` tường minh chỉ khi hiểu rõ lifecycle và có nhu cầu cụ thể; không dùng nó để thay thế việc trả publisher đúng cách hoặc để ép ghi đồng bộ lên event loop.

## 3. Lấy và cập nhật WebSession trong controller

Ví dụ controller reactive đọc trạng thái giỏ hàng từ session:

```java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;
import reactor.core.publisher.Mono;

@RestController
class CartController {

    @GetMapping("/api/cart")
    Mono<ResponseEntity<CartState>> getCart(ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> {
                    CartState cart = (CartState) session.getAttributes()
                            .get("cartState");
                    if (cart == null) {
                        cart = new CartState();
                    }
                    return ResponseEntity.ok(cart);
                });
    }
}
```

Đoạn mã trên chỉ đọc thuộc tính và trả DTO. Nếu request không cần tạo trạng thái phiên, không ghi attribute chỉ để kiểm tra xem session có tồn tại hay không. Tạo session không cần thiết có thể làm tăng số phiên ẩn danh và dữ liệu trong kho.

Ví dụ cập nhật thuộc tính:

```java
@PostMapping("/api/cart/items")
Mono<ResponseEntity<Void>> addItem(
        @RequestBody AddCartItem command,
        ServerWebExchange exchange) {

    return exchange.getSession()
            .map(session -> {
                CartState current = (CartState) session.getAttributes()
                        .getOrDefault("cartState", new CartState());
                CartState updated = current.add(command.productId());
                session.getAttributes().put("cartState", updated);
                return ResponseEntity.noContent().build();
            });
}
```

Ví dụ giả định `CartState` là DTO nhỏ, an toàn để serialize và có method `add` trả về trạng thái mới. Không lưu entity ORM, request object hoặc tài nguyên mở vào WebSession. Nếu giỏ hàng có giá trị nghiệp vụ, cần xác minh lại giá và tồn kho từ database khi thanh toán; dữ liệu trong session chỉ là trạng thái điều hướng hoặc lựa chọn tạm thời.

Một cách khác là nhận `WebSession` trực tiếp làm method argument trong controller WebFlux nếu cấu hình handler method hỗ trợ kiểu này. Dùng `ServerWebExchange` là cách minh họa rõ ràng nguồn của phiên và phù hợp khi controller cần thêm thông tin request/response.

## 4. Các thao tác lifecycle đều nằm trong reactive pipeline

Một điểm khác biệt quan trọng là các thao tác thay đổi vòng đời WebSession có thể trả `Mono<Void>`. Phải kết hợp publisher này vào pipeline để framework biết khi nào thao tác hoàn tất.

Ví dụ đổi ID sau một bước xác thực tùy biến:

```java
Mono<Void> rotateSessionId(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::changeSessionId);
}
```

Sau khi publisher hoàn tất, response lifecycle sẽ xử lý ID mới theo `WebSessionIdResolver` đang cấu hình. Trong luồng Spring Security dựng sẵn, session fixation protection được tích hợp theo cấu hình security; không tự đổi ID lần nữa nếu security handler đã thực hiện việc đó.

Ví dụ vô hiệu hóa phiên:

```java
Mono<Void> invalidateCurrentSession(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
```

Không gọi `invalidate()` rồi bỏ publisher, vì thao tác reactive có thể chưa được thực thi. Cũng không gọi `.block()` để chờ trong controller hoặc WebFilter. Hãy trả publisher về WebFlux để framework quản lý subscription, lỗi và completion.

## 5. Cookie và cách trao đổi session ID trong WebFlux

WebFlux dùng `WebSessionIdResolver` để đọc session ID từ request và ghi ID vào response. Resolver mặc định thường dùng cookie thông qua `CookieWebSessionIdResolver`. Đây là abstraction của WebFlux; nó khác với `HttpSessionIdResolver` hoặc `DefaultCookieSerializer` thường gặp trong Spring Session Servlet integration.

Ví dụ tùy chỉnh cookie resolver:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class WebSessionCookieConfiguration {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();
        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(builder -> builder
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));
        return resolver;
    }
}
```

Ví dụ đặt cookie `HttpOnly`, `Secure` và `SameSite=Lax`. Trong production, `Secure` phù hợp với HTTPS. Nếu TLS kết thúc ở reverse proxy, ứng dụng cần nhận biết đúng scheme hoặc đặt chính sách cookie secure tường minh; forwarded headers chỉ được tin khi proxy biên ghi lại và backend chỉ nhận request từ proxy tin cậy.

Nếu luồng đăng nhập cần cookie cross-site, có thể phải dùng `SameSite=None` và `Secure`, đồng thời đánh giá CSRF, CORS, credentials và callback flow. Không thay `SameSite` chỉ để khắc phục cookie không được gửi mà chưa kiểm tra domain, path, HTTPS và chính sách trình duyệt.

Không dùng session ID trong URL hoặc log. Session ID là bearer credential; ai có ID hợp lệ có thể được nhận diện như chủ phiên. Cookie chỉ mang định danh; dữ liệu phiên nằm ở repository reactive.

## 6. WebSessionManager, WebSessionStore và repository reactive

WebFlux sử dụng `WebSessionManager` để cung cấp session cho `ServerWebExchange`. Manager dùng `WebSessionStore` để tạo, tìm và quản lý phiên. Khi tích hợp Spring Session, store kết nối với một `ReactiveSessionRepository` để dữ liệu được lưu ngoài bộ nhớ của một instance.

`ReactiveSessionRepository` cung cấp các thao tác dạng publisher, điển hình gồm:

| Thao tác | Kiểu kết quả |
| --- | --- |
| Tạo phiên | `Mono<S>` |
| Tìm theo ID | `Mono<S>` |
| Lưu phiên | `Mono<Void>` |
| Xóa theo ID | `Mono<Void>` |

Repository reactive giúp WebFlux không phải chờ đồng bộ khi truy cập kho session. Với Redis, dùng implementation reactive tương ứng và cấu hình mọi instance cùng kết nối tới một kho dữ liệu, cùng namespace và serializer tương thích.

Spring Session có thể được bật cho WebFlux bằng cấu hình hỗ trợ như `@EnableRedisWebSession` hoặc auto-configuration tương ứng với phiên bản Spring Boot. Cấu hình chính xác phụ thuộc dependency và phiên bản đang dùng. Trước khi tự khai báo `WebSessionManager` hoặc store, hãy kiểm tra auto-configuration hiện tại để tránh tạo hai manager hoặc hai repository cho cùng ứng dụng.

Không sử dụng `SessionRepositoryFilter` trong WebFlux. Filter đó tích hợp Servlet `HttpSession`. Trong WebFlux, việc kết nối session store được thực hiện qua `WebSessionManager`/`WebSessionStore` và các thành phần reactive tương ứng.

## 7. Vì sao repository JDBC blocking không thể dùng như reactive repository?

JDBC là API blocking: gọi truy vấn thường chiếm thread cho tới khi database trả kết quả. WebFlux được thiết kế để không chặn event-loop khi xử lý I/O. Nếu gọi JDBC trực tiếp trong một controller reactive, một truy vấn chậm có thể giữ event-loop và làm giảm khả năng xử lý nhiều request đồng thời.

Spring Session JDBC truyền thống cung cấp repository blocking cho Servlet `HttpSession`. Nó không tự trở thành `ReactiveSessionRepository` chỉ vì được gọi từ WebFlux. Việc bọc lời gọi blocking trong `Mono.just(repository.findById(id))` vẫn thực hiện truy vấn ngay trước khi publisher được tạo, nên event-loop vẫn bị chặn.

Nếu một tích hợp blocking là bắt buộc, cần cô lập công việc trên scheduler phù hợp, ví dụ `Schedulers.boundedElastic()`, và giới hạn concurrency. Tuy nhiên, cách bọc này chỉ chuyển thao tác blocking sang thread pool; nó không biến JDBC thành I/O reactive và cần đánh giá tải, pool size, backpressure và timeout. Với session store cốt lõi của WebFlux, ưu tiên repository reactive được hỗ trợ.

Ví dụ minh họa cách cô lập một lời gọi blocking bên ngoài session integration:

```java
Mono<Result> callLegacyBlockingService() {
    return Mono.fromCallable(legacyService::load)
            .subscribeOn(Schedulers.boundedElastic());
}
```

Không dùng ví dụ này để tự bọc toàn bộ Spring Session JDBC thành WebSession store nếu chưa thiết kế đầy đủ các thao tác tạo, lưu, xóa, timeout và đồng bộ. Một adapter tự viết phải bảo đảm reactive contract, xử lý lỗi, transaction và concurrency; chỉ chuyển thread là chưa đủ.

## 8. Spring Security lưu trạng thái xác thực ở đâu?

Servlet Spring Security và WebFlux Spring Security có filter chain và security context repository riêng.

| Servlet | WebFlux |
| --- | --- |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `FilterChainProxy` và Servlet filters | `WebFilter` và `WebFilterChain` |
| `SecurityContextRepository` | `ServerSecurityContextRepository` |
| `HttpSessionSecurityContextRepository` | `WebSessionServerSecurityContextRepository` |
| `HttpSession` | `WebSession` |

Trong cơ chế đăng nhập dựa trên session, WebFlux Spring Security có thể lưu `SecurityContext` vào `WebSession` thông qua `WebSessionServerSecurityContextRepository`. Request sau khôi phục context từ phiên. Các cấu hình stateless có thể dùng repository không lưu context vào WebSession, ví dụ `NoOpServerSecurityContextRepository`, nếu authentication được cung cấp theo request bằng cơ chế khác.

Ví dụ cấu hình WebFlux security:

```java
@Bean
SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/public/**", "/login").permitAll()
                    .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .build();
}
```

Ví dụ sử dụng security defaults của WebFlux; không khai báo Servlet `SecurityFilterChain` cho cùng reactive application. Nếu cần tùy chỉnh nơi lưu context, cấu hình `ServerSecurityContextRepository` phù hợp và xác minh hành vi qua request kế tiếp.

CSRF protection trong WebFlux cũng có thể sử dụng WebSession để lưu token theo cấu hình mặc định. Vì vậy, request công khai vẫn có thể khiến session được tạo khi một thành phần bảo mật cần lưu trạng thái. `permitAll()` chỉ cho phép truy cập endpoint; nó không bảo đảm request không tạo WebSession.

## 9. Khác biệt về filter, interceptor và request context

Servlet dùng `Filter` và Spring MVC `HandlerInterceptor`. WebFlux dùng `WebFilter` và `HandlerFilterFunction` hoặc các thành phần WebFlux tương ứng. Không thể đưa một `OncePerRequestFilter` Servlet vào reactive filter chain và mong nó chạy đúng. Cũng không thể lấy `HttpServletRequest` trong WebFlux controller.

Nếu cần kiểm tra session trước controller, viết `WebFilter` và kết hợp `exchange.getSession()` trong reactive chain. Nếu cần principal đã xác thực, lấy từ reactive security context thay vì `SecurityContextHolder` dựa trên `ThreadLocal`.

Ví dụ khung WebFilter đọc một thuộc tính phiên:

```java
public class SessionMarkerWebFilter implements WebFilter {

    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        return exchange.getSession()
                .doOnNext(session -> {
                    Object marker = session.getAttributes().get("marker");
                    exchange.getAttributes().put("sessionMarker", marker);
                })
                .then(chain.filter(exchange));
    }
}
```

Đoạn mã minh họa đọc session trước khi gọi chain. Nếu endpoint không cần session, việc gọi `getSession()` ở mọi request có thể tạo session không cần thiết; chỉ dùng khi thực sự cần. Nếu filter cần dữ liệu từ authentication, hãy đặt logic ở đúng security filter/web filter lifecycle thay vì giả định principal đã có sẵn tại mọi vị trí.

## 10. Reactive pipeline và các lỗi blocking thường gặp

Trong WebFlux, `Mono` và `Flux` mô tả các phép tính reactive. Gọi một method trả publisher nhưng không kết hợp publisher vào chain có thể khiến thao tác không được thực thi. Ngược lại, gọi `.block()` trong event-loop biến xử lý non-blocking thành chờ đồng bộ.

Các lỗi thường gặp:

- Gọi `.block()` trên `exchange.getSession()` trong controller.
- Gọi repository JDBC blocking trực tiếp trong `map` hoặc `flatMap` chạy trên event-loop.
- Gọi `subscribe()` thủ công trong controller rồi trả response trước khi thao tác session hoàn tất.
- Dùng `ThreadLocal` hoặc `SecurityContextHolder` như thể một request luôn ở cùng thread.
- Giữ `ServerWebExchange`, request body hoặc resource đang mở trong session để dùng ở request sau.
- Bỏ qua publisher từ `invalidate()` hoặc `changeSessionId()`.

Thay vì tự subscribe, hãy trả publisher:

```java
@PostMapping("/logout")
Mono<Void> logout(ServerWebExchange exchange) {
    return exchange.getSession()
            .flatMap(WebSession::invalidate);
}
```

Spring WebFlux sẽ subscribe và quản lý completion/error khi xử lý response. Với lỗi repository, dùng `onErrorMap`, `onErrorResume` hoặc handler tập trung để chuyển đổi lỗi phù hợp. Không biến mọi lỗi Redis thành “không có session”, vì lỗi kết nối khác với session ID không tồn tại.

## 11. Thời hạn, đồng thời và nhiều instance

`WebSession` có idle timeout. Repository reactive phải duy trì metadata và hết hạn theo cấu hình. Cookie còn trong trình duyệt không có nghĩa session phía server còn hợp lệ. Khi session hết hạn hoặc bị invalidate, request sau phải được xem như không có phiên hợp lệ.

Nhiều request reactive của cùng trình duyệt có thể chạy đồng thời và được xử lý bởi các thread khác nhau hoặc instance khác nhau. Không giả định WebSession là một transaction hay một khóa đồng bộ cho mọi thao tác trên attributes. Hai request có thể cùng đọc snapshot cũ rồi ghi thay đổi cạnh tranh.

Các khuyến nghị:

- Giữ session attributes nhỏ, ưu tiên DTO immutable.
- Không dùng mutable collection trong session như kho giao dịch nếu có request đồng thời.
- Dữ liệu quan trọng như đơn hàng, tồn kho và quyền phải được xác minh trong database/service.
- Dùng repository reactive và cùng namespace trên tất cả instance.
- Đổi session ID sau xác thực và invalidate khi logout.
- Kiểm thử request tới instance khác bằng cùng cookie.

## 12. Kiểm thử WebSession và khác biệt với HttpSession

Kiểm thử WebFlux nên dùng WebTestClient hoặc integration test với reactive server. `MockMvc` hướng tới Servlet/MVC và không chứng minh đầy đủ lifecycle của WebSession.

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Request đầu chưa có cookie | WebFlux không tạo session nếu không có thành phần cần bắt đầu phiên |
| Ghi một attribute | Session bắt đầu, response phát ID theo resolver và repository lưu dữ liệu |
| Request tiếp theo gửi cookie | WebSession khôi phục đúng attribute |
| Đổi session ID | ID mới được gửi về client; ID cũ không còn dùng cho phiên đã xác thực |
| Invalidate | Phiên bị thu hồi và cookie/ID được xử lý theo resolver |
| Idle timeout | Phiên hết hạn không được khôi phục như phiên hợp lệ |
| Spring Security login | SecurityContext được khôi phục ở request sau theo repository cấu hình |
| Hai instance | Session tạo ở instance A đọc được ở instance B |
| Redis timeout | Lỗi hạ tầng được xử lý riêng với trường hợp không có phiên |
| Không blocking | Không có `.block()` hoặc JDBC I/O trên event-loop |

Với repository Redis reactive, dùng Redis thật hoặc Testcontainers để xác minh lưu/đọc/xóa và TTL. Khi kiểm tra nhiều instance, gửi cookie nhận từ response của instance A sang instance B. Kiểm tra logout tại A rồi gửi cookie cũ tới B để xác nhận việc thu hồi được chia sẻ.

Đối với security, kiểm thử qua login flow thực tế thay vì chỉ dùng mock principal nếu cần xác minh việc lưu `SecurityContext` trong WebSession. Kiểm tra cả cookie attributes và response commit để bảo đảm session ID được gửi đúng.

## 13. Lỗi thường gặp và cách chẩn đoán

**Mã WebFlux không tìm thấy `HttpSession`.** Đây là khác biệt web stack. Dùng `ServerWebExchange.getSession()` và `WebSession`; không cố lấy Servlet request trong reactive controller.

**Đã thêm thuộc tính nhưng request sau không thấy.** Kiểm tra publisher từ `exchange.getSession()` đã được kết hợp và hoàn tất chưa, attribute có được đặt trong map đúng cách không, WebSession có được lưu khi response commit không, cookie ID có được gửi lại không và repository có dùng cùng namespace trên các instance không.

**Cookie không được phát hoặc trình duyệt không gửi lại.** Kiểm tra session đã bắt đầu chưa, resolver có được cấu hình không, `Set-Cookie` có đúng name/path/domain/SameSite/Secure không và ứng dụng có nhận biết HTTPS qua proxy không.

**Event-loop bị chặn.** Tìm `.block()`, JDBC/JPA blocking hoặc thư viện I/O đồng bộ trong reactive chain. Dùng API reactive; nếu bắt buộc dùng legacy blocking service, cô lập trên scheduler phù hợp và kiểm soát concurrency.

**Đăng nhập thành công nhưng request sau thành anonymous.** Kiểm tra `ServerSecurityContextRepository`, WebSession persistence, cookie và request đi qua cùng repository. Xác minh security chain là WebFlux chain, không phải Servlet chain.

**Logout trả response nhưng session vẫn dùng được.** Đảm bảo publisher `invalidate()` được trả về và hoàn tất; kiểm tra repository xóa phiên dùng chung và resolver xử lý cookie ID. Thử gửi cookie cũ tới instance khác.

**Dữ liệu session bị ghi đè khi nhiều request cùng chạy.** Kiểm tra mutable attributes và race giữa các request. Chuyển trạng thái quan trọng sang database có transaction hoặc dùng cập nhật nguyên tử ở tầng dữ liệu.

## 14. Quy trình lựa chọn và tích hợp

1. Xác nhận ứng dụng chạy Servlet hay WebFlux; không suy ra chỉ từ việc có dependency WebFlux trong build.
2. Với Servlet, dùng `HttpSession`, `SessionRepositoryFilter` và repository phù hợp; với WebFlux, dùng `WebSession`, `WebSessionManager`/`WebSessionStore` và reactive repository.
3. Cấu hình cookie/session ID resolver phù hợp với stack và HTTPS/proxy.
4. Nếu dùng Spring Security, cấu hình đúng `SecurityFilterChain` hoặc `SecurityWebFilterChain` cùng security context repository tương ứng.
5. Không gọi JDBC blocking trực tiếp trên event-loop và không dùng `.block()` trong request pipeline.
6. Giữ session attributes nhỏ, serialize được và không phụ thuộc request, transaction hoặc tài nguyên mở.
7. Kiểm thử login, attribute persistence, ID rotation, logout, timeout, nhiều instance và lỗi repository bằng công cụ kiểm thử đúng stack.

`HttpSession` và `WebSession` giải quyết cùng nhu cầu lưu trạng thái giữa các request nhưng phản ánh hai mô hình xử lý khác nhau. Servlet cung cấp API đồng bộ được tích hợp qua filter; WebFlux cung cấp session reactive được quản lý qua exchange, manager và reactive store. Khi chọn đúng repository, resolver, security integration và cách xử lý publisher, Spring Session có thể lưu phiên dùng chung cho ứng dụng reactive mà không chặn event loop hoặc phụ thuộc vào bộ nhớ của một instance.
