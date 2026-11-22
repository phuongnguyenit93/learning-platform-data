# Cookie, bắt đầu phiên và hủy phiên trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Filter và phiên. Bài học giải thích hai cơ chế thường xuất hiện cùng nhau nhưng có vai trò khác nhau: HTTP cookie được trình duyệt gửi qua request/response, còn `WebSession` là trạng thái phía server được truy cập theo session ID. Nội dung đi từ `@CookieValue` và `ResponseCookie` tới tạo phiên, lưu attribute, đổi session ID, hết hạn, logout, cấu hình resolver/store, bảo mật và kiểm thử qua nhiều HTTP request.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc cookie từ annotated controller bằng `@CookieValue` hoặc từ request bằng `ServerWebExchange`/`ServerRequest`.
2. Tạo, cấu hình và xóa cookie bằng `ResponseCookie`, `ServerHttpResponse.addCookie` hoặc `ServerResponse.cookie`.
3. Phân biệt cookie chứa dữ liệu ứng dụng với cookie chỉ mang **session ID**.
4. Lấy `WebSession` bằng `ServerWebExchange.getSession()` hoặc tham số controller `WebSession`.
5. Hiểu khi nào session thực sự được bắt đầu, khi nào attribute được lưu và khi nào session ID được gửi về client.
6. Thực hiện login/session rotation, đọc và cập nhật session attribute, logout bằng `invalidate()` và đặt idle timeout.
7. Chọn `WebSessionIdResolver`, `WebSessionStore` và Spring Session Redis khi cần lưu phiên dùng chung nhiều instance.
8. Áp dụng `HttpOnly`, `Secure`, `SameSite`, CSRF protection và các quy tắc xử lý session ID an toàn.
9. Kiểm thử cookie/session bằng HTTP integration test có cookie jar, thay vì chỉ gọi method Java.

**Điểm phân biệt cốt lõi:** cookie là dữ liệu client gửi trong header `Cookie`; `WebSession` là abstraction trạng thái phía server. Cookie session thường chỉ mang một ID opaque để server tra cứu session. Không nhầm session ID với toàn bộ dữ liệu session.

## 2. Cookie HTTP hoạt động như thế nào?

Cookie là cặp tên/giá trị do server yêu cầu trình duyệt lưu. Server gửi cookie trong response header `Set-Cookie`; ở các request phù hợp, trình duyệt gửi lại cookie qua header `Cookie`.

~~~text
Lần đầu:
Browser  -- GET /profile --------------------------> Server
Browser  <-- 200 + Set-Cookie: theme=dark; Path=/ -- Server

Request tiếp theo:
Browser  -- GET /profile
             Cookie: theme=dark -------------------> Server
Browser  <-- 200 ----------------------------------- Server
~~~

Hai chiều này dùng header khác nhau:

| Chiều | Header | Nội dung |
| --- | --- | --- |
| Server → browser | `Set-Cookie` | Yêu cầu browser lưu/cập nhật/xóa cookie và các thuộc tính. |
| Browser → server | `Cookie` | Gửi các cặp tên/giá trị cookie áp dụng cho request hiện tại. |

Browser quyết định có gửi cookie hay không dựa trên domain, path, expiration, `Secure`, `SameSite` và các quy tắc cookie của trình duyệt. JavaScript không thể đọc cookie có `HttpOnly`; cookie `Secure` chỉ được gửi qua kết nối HTTPS (ngoại lệ localhost phụ thuộc quy tắc browser).

**Cookie không phải một nơi lưu trữ bí mật đáng tin cậy.** Người dùng có thể sửa các cookie không được bảo vệ và gửi giá trị tùy ý. Server phải validate mọi cookie nhận vào; nếu cần tin cậy dữ liệu phía client thì phải có chữ ký/MAC hoặc mã hóa và vẫn kiểm tra authorization ở server.

### 2.1. Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa | Cách chọn |
| --- | --- | --- |
| `Path` | Những đường dẫn request có thể gửi cookie | Chọn path hẹp nhất vẫn đáp ứng ứng dụng; `/` áp dụng toàn host/path. |
| `Domain` | Cho phép cookie áp dụng host và các subdomain phù hợp | Thường bỏ để cookie host-only; tránh mở rộng sang mọi subdomain nếu không cần. |
| `Max-Age` | Tuổi thọ tính từ thời điểm nhận cookie | Số dương là thời hạn; `0` xóa ngay; âm nghĩa không có Max-Age, thường là cookie phiên trình duyệt. |
| `Expires` | Thời điểm hết hạn tuyệt đối | Browser có thể dùng cùng Max-Age; Max-Age thường được ưu tiên. |
| `Secure` | Chỉ gửi cookie qua HTTPS | Bật cho cookie production, đặc biệt session/auth cookie. |
| `HttpOnly` | Không cho JavaScript đọc cookie qua `document.cookie` | Bật với session ID và credential cookie. |
| `SameSite` | Hạn chế gửi cookie trong ngữ cảnh cross-site | `Strict`, `Lax` hoặc `None` theo luồng điều hướng; `None` cần `Secure` trong browser hiện đại. |
| `Partitioned` | Cookie được phân vùng theo top-level site trong một số ngữ cảnh | Chỉ dùng khi có yêu cầu third-party/embedded cụ thể. |

`HttpOnly` giảm khả năng script lấy cookie qua XSS, nhưng không ngăn XSS thực hiện request dưới danh nghĩa người dùng. `SameSite` hỗ trợ giảm CSRF, nhưng không thay thế CSRF token/Origin validation và chính sách bảo mật phù hợp.

### 2.2. Cookie session và cookie dữ liệu ứng dụng khác nhau

| Loại | Ví dụ | Ai giữ dữ liệu chính? |
| --- | --- | --- |
| Cookie tùy chọn giao diện | `theme=dark` | Browser giữ giá trị; server đọc mỗi request. |
| Cookie ghi nhớ lựa chọn | `locale=vi` | Browser giữ giá trị không nhạy cảm. |
| Session ID cookie | `SESSION=<opaque-id>` | Browser giữ ID; server tra cứu `WebSession`. |
| Cookie token xác thực | Access/refresh token | Phải tuân theo thiết kế token, chữ ký, rotation, expiration và threat model riêng. |

Không đặt password, access token thô, thông tin thanh toán hoặc toàn bộ object session vào cookie thông thường. Với `WebSession`, cookie chỉ mang session ID; attribute nằm trong `WebSessionStore`/repository phía server.

## 3. Đọc cookie trong WebFlux

### 3.1. Annotated controller với `@CookieValue`

`@CookieValue` bind giá trị cookie vào method argument. Spring hỗ trợ type conversion nếu tham số không phải `String`.

~~~java
@RestController
class ThemeController {

    @GetMapping("/api/theme")
    Map<String, String> theme(
            @CookieValue(
                name = "theme",
                required = false,
                defaultValue = "system"
            ) String theme) {

        return Map.of("theme", theme);
    }
}
~~~

- Nếu request có `Cookie: theme=dark`, method nhận `"dark"`.
- Nếu không có cookie, `defaultValue` được dùng và `required` ngầm trở thành `false`.
- Nếu bỏ `required=false` và không có `defaultValue`, cookie mặc định là bắt buộc; thiếu cookie sẽ tạo lỗi resolve argument.
- Nếu khai báo tham số `int`, `long`, enum hoặc kiểu có converter, Spring có thể chuyển giá trị từ chuỗi sang kiểu đích.

Đừng dùng `@CookieValue` để đọc session ID của WebFlux nếu mục tiêu là truy cập session; hãy dùng `WebSession`. Đọc trực tiếp ID chỉ cần cho trường hợp tích hợp giao thức đặc biệt.

### 3.2. Đọc cookie qua `ServerWebExchange`

`ServerWebExchange` cung cấp request và response của HTTP exchange. Cookie request có thể đọc qua `ServerHttpRequest.getCookies()`:

~~~java
@GetMapping("/api/cookie-map")
Map<String, String> readCookie(ServerWebExchange exchange) {
    HttpCookie cookie = exchange.getRequest()
        .getCookies()
        .getFirst("theme");

    String value = cookie == null ? "system" : cookie.getValue();
    return Map.of("theme", value);
}
~~~

`getCookies()` là `MultiValueMap<String, HttpCookie>`; một tên cookie có thể xuất hiện nhiều giá trị tùy request/path/domain. `getFirst` lấy giá trị đầu tiên, vì vậy nếu hệ thống chấp nhận nhiều cookie trùng tên thì phải xác định quy tắc rõ thay vì tin rằng luôn chỉ có một.

### 3.3. WebFlux.fn đọc cookie bằng `ServerRequest`

Với functional endpoint, request cung cấp `cookies()`:

~~~java
Mono<ServerResponse> theme(ServerRequest request) {
    HttpCookie cookie = request.cookies().getFirst("theme");
    String value = cookie == null ? "system" : cookie.getValue();

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("theme", value));
}
~~~

Annotated controller và functional handler dùng cùng request cookie model; khác biệt nằm ở cách lấy dữ liệu.

## 4. Tạo và xóa cookie trong response

### 4.1. Dùng `ResponseCookie`

`ResponseCookie` mở rộng `HttpCookie` với các thuộc tính chỉ có ý nghĩa trong response `Set-Cookie`. Tạo cookie bằng builder:

~~~java
ResponseCookie cookie = ResponseCookie.from("theme", "dark")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(Duration.ofDays(30))
    .build();
~~~

Builder cho phép thiết lập name/value, path, domain, max-age, secure, http-only, same-site và partitioned. Trong ví dụ production, `Secure=true` yêu cầu HTTPS. Nếu demo chạy HTTP localhost, hãy tách cấu hình theo profile thay vì tắt `Secure` trong production.

### 4.2. Ghi cookie qua `ServerHttpResponse`

~~~java
@PostMapping("/api/theme")
Mono<ResponseEntity<Void>> setTheme(ServerHttpResponse response) {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofDays(30))
        .build();

    response.addCookie(cookie);
    return Mono.just(ResponseEntity.noContent().build());
}
~~~

`addCookie` thêm `ResponseCookie` vào response trước khi response commit. Không gọi sau khi response đã commit. Vì response reactive, hãy tạo cookie trước khi trả Publisher; đừng mở một subscription phụ để cố ghi header sau đó.

### 4.3. Xóa cookie

Muốn browser xóa cookie, server gửi lại cùng tên và cùng scope (`Path`, `Domain`) với `Max-Age=0` hoặc `Expires` trong quá khứ:

~~~java
ResponseCookie expired = ResponseCookie.from("theme", "")
    .path("/")
    .httpOnly(true)
    .secure(true)
    .sameSite("Lax")
    .maxAge(Duration.ZERO)
    .build();

response.addCookie(expired);
~~~

Nếu cookie gốc có `Domain=example.com` và `Path=/app`, cookie xóa phải dùng cùng scope. Gửi cookie cùng tên nhưng path/domain khác có thể tạo một cookie mới thay vì xóa cookie cũ.

### 4.4. Functional endpoint ghi cookie

~~~java
Mono<ServerResponse> setTheme() {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofDays(30))
        .build();

    return ServerResponse.noContent()
        .cookie(cookie)
        .build();
}
~~~

`ServerResponse` builder có `cookie(ResponseCookie)` và `cookies(...)`; server sẽ ghi `Set-Cookie` khi response được ghi. Chọn một response builder để sở hữu status/header/body/cookie của response đó.


## 5. WebSession là gì?

`WebSession` là abstraction của Spring WebFlux cho trạng thái server-side tồn tại qua nhiều HTTP request. Một session thường có:
- Session ID duy nhất.
- Map attribute (`getAttributes()`).
- Creation time, last access time.
- Maximum idle time.
- Trạng thái started/expired.
- Các thao tác đổi ID, lưu và invalidate.

`ServerWebExchange.getSession()` trả `Mono<WebSession>` cho request hiện tại. `WebSession` cũng có thể được inject trực tiếp vào annotated controller method:

~~~java
@GetMapping("/api/session/profile")
Mono<Profile> profile(WebSession session) {
    return Mono.justOrEmpty(session.<Profile>getAttribute("profile"));
}
~~~

Session không tự tạo dữ liệu chỉ vì method nhận `WebSession`. Việc lấy session đảm bảo có object phù hợp với session ID request hoặc một session mới; **nó không tự động start session**.

### 5.1. Cookie session ID và dữ liệu server-side

~~~text
Browser
  Cookie: SESSION=<opaque-session-id>
             |
             v
       WebSessionManager
             |
       WebSessionIdResolver
             |
       WebSessionStore / repository
             |
             v
     WebSession + attributes
       user = "Ada"
       cart = ...
       csrf state = ...
~~~

Browser gửi ID; server dùng ID để tìm session. Client không được coi ID là dữ liệu nghiệp vụ và không nên tự sửa giá trị đó. Nếu ID không có, không hợp lệ hoặc session đã hết hạn, manager tạo session mới.

### 5.2. `getSession()` không đồng nghĩa session đã started

~~~java
@GetMapping("/session-check")
Mono<String> check(ServerWebExchange exchange) {
    return exchange.getSession().map(session ->
        "started=" + session.isStarted());
}
~~~

Nếu session mới chưa có attribute và chưa gọi `start()`, `isStarted()` có thể là `false`. Chưa started nghĩa là ID không cần được gửi tới browser; session `save()` trong trạng thái đó về cơ bản không làm gì.

Có hai cách bắt đầu session:
1. Gọi `session.start()` nếu cần tạo session ngay cả khi chưa có attribute.
2. Thêm một session attribute; việc này bắt đầu session ngầm.

~~~java
Mono<String> startExplicitly(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.start();
        return "started=" + session.isStarted();
    });
}
~~~

Không cần gọi `start()` nếu ngay sau đó đã thêm attribute. Chọn explicit start khi session thực sự cần tồn tại mà chưa có dữ liệu.

## 6. Lưu và đọc session attributes

### 6.1. Ghi attribute

~~~java
Mono<SessionView> createSession(WebSession session) {
    session.getAttributes().put("user", "Ada");
    session.getAttributes().put("cartCount", 2);
    return Mono.just(new SessionView("Ada", 2));
}
~~~

`getAttributes()` trả map mutable. Attribute được giữ trong session store và có thể đọc ở request tiếp theo với cùng session ID. Dùng tên key ổn định, kiểu dữ liệu rõ và dữ liệu nhỏ; đừng đưa toàn bộ domain graph lớn vào session.

### 6.2. Đọc attribute an toàn

~~~java
Mono<SessionView> readSession(WebSession session) {
    String user = session.getAttribute("user");
    int cartCount = session.getAttributeOrDefault("cartCount", 0);

    if (user == null) {
        return Mono.empty();
    }

    return Mono.just(new SessionView(user, cartCount));
}
~~~

- `getAttribute(name)` trả `null` nếu không có giá trị.
- `getAttributeOrDefault(name, defaultValue)` cung cấp fallback.
- `getRequiredAttribute(name)` ném `IllegalArgumentException` nếu attribute thiếu.
- `getAttributes()` cho phép đọc/ghi trực tiếp map.

Nếu thiếu session attribute là một trường hợp nghiệp vụ bình thường, dùng `getAttribute` và xử lý rõ. Dùng `getRequiredAttribute` khi thiếu dữ liệu là invariant vi phạm.

### 6.3. Session được save khi nào?

`WebSession.save()` trả `Mono<Void>`, nhưng Javadoc quy định đây **không phải method ứng dụng thường gọi trực tiếp**. WebFlux tự gọi save ngay trước khi response được commit. Với session mới, nếu chưa `start()` hoặc chưa có attribute thì save không có tác dụng.

Điều này giúp session cookie được thêm vào response đúng lifecycle. Không gọi `session.save().subscribe()` trong controller; làm vậy tách thao tác lưu khỏi HTTP response, có thể tạo race với commit và làm lỗi khó quan sát. Hãy trả Publisher nghiệp vụ cho framework quản lý.

## 7. Bắt đầu, xoay ID và hủy session

### 7.1. Tạo session trong controller

~~~java
@PostMapping("/api/session/start")
Mono<SessionView> start(WebSession session) {
    session.setMaxIdleTime(Duration.ofMinutes(10));
    session.getAttributes().put("user", "Ada");
    session.getAttributes().put("visits", 0);

    return Mono.just(new SessionView("Ada", 0));
}
~~~

Thêm attribute làm session started. Khi response được commit, WebFlux save session và session ID resolver gửi ID cho browser (mặc định qua cookie). Client lưu cookie và gửi lại ở request sau.

### 7.2. Đổi session ID sau khi đăng nhập

Sau khi xác thực thành công, nên rotate session ID để giảm nguy cơ session fixation:

~~~java
Mono<Void> rotateAfterLogin(WebSession session) {
    return session.changeSessionId();
}
~~~

`changeSessionId()` phát `Mono<Void>`, tạo ID mới và cập nhật storage. Sau khi thành công, `getId()` trả ID mới. Không trả session ID trong JSON, log hoặc URL. Với flow login, hãy thực hiện rotation sau khi xác thực thành công và trước khi trả response xác nhận đăng nhập.

### 7.3. Logout bằng `invalidate()`

~~~java
@PostMapping("/api/session/logout")
Mono<ResponseEntity<Void>> logout(WebSession session) {
    return session.invalidate()
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

`invalidate()` xóa session hiện tại khỏi session storage và trả completion/error qua `Mono<Void>`. Session ID resolver phối hợp để browser ngừng dùng ID hiện tại. Sau logout, request tiếp theo với cookie cũ không được khôi phục dữ liệu session đã invalidate.

**Không chỉ xóa cookie ở browser mà bỏ session server-side.** Nếu chỉ xóa cookie, session record vẫn tồn tại cho tới khi hết hạn hoặc được dọn; ID bị đánh cắp trước đó vẫn có thể còn dùng được. Logout phải invalidate session server-side.

### 7.4. Đặt idle timeout

~~~java
session.setMaxIdleTime(Duration.ofMinutes(15));
~~~

`maxIdleTime` là khoảng thời gian tối đa không có hoạt động trước khi session được xem là expired. `getLastAccessTime()` cho biết lần truy cập gần nhất; `isExpired()` kiểm tra session đã hết idle time chưa. Khi session được retrieve, store có trách nhiệm kiểm tra expiration và cập nhật last access time.

Idle timeout phía server và cookie Max-Age phía browser là hai đồng hồ khác nhau:
- Browser có thể còn giữ cookie session ID nhưng server đã hết hạn session; lần request tiếp theo sẽ nhận session mới.
- Browser đóng cửa sổ có thể xóa cookie session nếu Max-Age không được đặt, nhưng session record server có thể còn đến khi hết idle time.
- Persistent cookie có thể sống lâu hơn session server; browser gửi ID nhưng server không còn state.

Vì vậy, hãy đặt timeout server-side theo chính sách đăng nhập và cân nhắc Max-Age cookie phù hợp. Không xem cookie còn tồn tại là bằng chứng session còn hợp lệ.

## 8. `@SessionAttribute` và `@SessionAttributes`

Hai annotation có mục đích khác nhau.

### 8.1. `@SessionAttribute`: đọc attribute đã được quản lý ở nơi khác

Dùng khi attribute đã được tạo bởi filter, authentication flow hoặc một thành phần toàn cục:

~~~java
@GetMapping("/api/current-user")
Mono<String> currentUser(
        @SessionAttribute(name = "user", required = false) String user) {
    return Mono.just(user == null ? "anonymous" : user);
}
~~~

Annotation này đọc attribute đã tồn tại trong `WebSession`; nó không phải API chính để thêm/xóa session attribute.

### 8.2. `@SessionAttributes`: giữ model attribute trong một controller workflow

~~~java
@Controller
@SessionAttributes("checkout")
class CheckoutController {

    @GetMapping("/checkout")
    String checkout(Model model) {
        model.addAttribute("checkout", new CheckoutDraft());
        return "checkout";
    }

    @PostMapping("/checkout/complete")
    String complete(CheckoutDraft checkout, SessionStatus status) {
        // Hoàn tất xử lý checkout...
        status.setComplete();
        return "redirect:/checkout/done";
    }
}
~~~

Spring promote model attribute `checkout` vào `WebSession` giữa các request. `SessionStatus.setComplete()` báo controller workflow hoàn tất và xóa các session attributes được khai báo qua `@SessionAttributes` của controller đó.

**`SessionStatus.setComplete()` không tương đương `WebSession.invalidate()`.** Nó dọn phần model state do controller quản lý; session tổng thể có thể vẫn được giữ cho authentication hoặc các mục đích khác.

## 9. Thời gian sống và nơi lưu session

Trong Spring Framework, các thành phần mặc định thường gặp:

| Thành phần | Vai trò |
| --- | --- |
| `WebSessionManager` | Lấy session tương ứng với một `ServerWebExchange`. |
| `DefaultWebSessionManager` | Phối hợp resolver và store để tìm/tạo session. |
| `WebSessionIdResolver` | Đọc ID từ request và gửi/xóa ID ở response. |
| `CookieWebSessionIdResolver` | Resolver dùng cookie; tên cookie mặc định là `SESSION`. |
| `HeaderWebSessionIdResolver` | Resolver dùng header, hữu ích cho một số API client. |
| `WebSessionStore` | Strategy tạo, lấy, xóa và cập nhật last access time của session. |
| `InMemoryWebSessionStore` | Store mặc định map-based trong bộ nhớ tiến trình. |

`DefaultWebSessionManager` mặc định dùng `CookieWebSessionIdResolver` và `InMemoryWebSessionStore`. Cookie session mặc định có tên `SESSION`; Max-Age mặc định là âm, tức không đặt thuộc tính Max-Age và browser thường xóa khi đóng phiên trình duyệt. `InMemoryWebSessionStore` có giới hạn số session mặc định 10.000 và idle time mặc định 30 phút trong Spring Framework 7.x.

**In-memory store phù hợp cho local development hoặc ứng dụng một instance với yêu cầu phù hợp.** Session mất khi process restart và không tự chia sẻ giữa nhiều replica. Với production nhiều instance, hãy dùng session repository phân tán nếu cần sticky-session độc lập.

### 9.1. Spring Session với Redis

Spring Session tích hợp trong suốt với `WebSession`; ứng dụng có thể thay store mặc định bằng implementation backed by `ReactiveSessionRepository`. Với Redis, cấu hình thường dùng `@EnableRedisWebSession` và `ReactiveSessionRepository` được cung cấp bởi Spring Session Data Redis.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableRedisWebSession
class RedisWebSessionConfiguration {

    @Bean
    LettuceConnectionFactory redisConnectionFactory() {
        return new LettuceConnectionFactory(
            new RedisStandaloneConfiguration("localhost", 6379));
    }
}
~~~

Đây là fragment cần Spring Session Data Redis, Spring Data Redis và Redis server. `@EnableRedisWebSession` đăng ký `WebSessionManager` backed by Redis. Trong ứng dụng Boot thật, cấu hình connection factory, password/TLS, timeout, serialization và TTL theo môi trường triển khai.

Spring Session giúp nhiều instance cùng đọc session repository. Redis không tự làm business state trở thành transaction an toàn; vẫn cần kiểm soát concurrent requests cùng session, race khi update attribute và chính sách logout/revocation.


## 10. Tùy biến session ID cookie

### 10.1. Đổi tên cookie và đặt thuộc tính

Có thể đăng ký `WebSessionIdResolver` bean để tùy biến cookie session:

~~~java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
        new CookieWebSessionIdResolver();

    resolver.setCookieName("__Host-SESSION");
    resolver.addCookieInitializer(builder -> builder
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax"));

    return resolver;
}
~~~

`CookieWebSessionIdResolver` cung cấp:
- `setCookieName(...)` để đổi tên session cookie.
- `setCookieMaxAge(...)` để đặt Max-Age.
- `addCookieInitializer(...)` để thêm `Path`, `Domain`, `Secure`, `HttpOnly`, `SameSite` và thuộc tính cookie khác.
- `expireSession(exchange)` để yêu cầu client kết thúc session hiện tại.

Ví dụ dùng tiền tố `__Host-` có quy tắc browser nghiêm ngặt: cookie phải có `Secure`, `Path=/` và không có `Domain`. Chỉ dùng tiền tố này khi ứng dụng chạy HTTPS, host scope và path đáp ứng điều kiện. Nếu app nằm sau reverse proxy, hãy cấu hình forwarded headers/proxy scheme chính xác để server hiểu request gốc là HTTPS.

### 10.2. HeaderWebSessionIdResolver

Một số native client hoặc hệ thống nội bộ có thể truyền session ID trong HTTP header thay vì cookie. `HeaderWebSessionIdResolver` là lựa chọn có sẵn; cần đặt tên header và bảo đảm header chỉ đi qua TLS, không bị log hoặc chuyển tiếp tới hệ thống không tin cậy.

Không chuyển session ID qua URL query/path. URL thường xuất hiện trong browser history, proxy/access log, analytics và Referer; cookie hoặc header an toàn hơn cho ID nhạy cảm.

## 11. Bảo mật cookie và session trong production

### 11.1. Cookie hardening

Với cookie chứa session ID hoặc thông tin xác thực, baseline thường gồm:

~~~text
Set-Cookie: __Host-SESSION=<opaque-id>;
            Path=/;
            Secure;
            HttpOnly;
            SameSite=Lax
~~~

- **Secure:** bắt buộc qua HTTPS để tránh gửi credential qua HTTP.
- **HttpOnly:** ngăn JavaScript đọc trực tiếp session cookie.
- **SameSite:** chọn Strict/Lax/None theo luồng điều hướng, SSO và cross-site integration.
- **Path/Domain:** giới hạn phạm vi cookie.
- **Max-Age:** phù hợp với session timeout và chính sách remember-me.
- **Rotation:** thay session ID sau authentication/privilege elevation.
- **Logout:** invalidate state phía server và expire ID cookie.

`SameSite=None` cần `Secure` theo yêu cầu của browser hiện đại. Nếu dùng OAuth/OIDC redirect hoặc cross-site flow, chọn SameSite theo giao thức và kiểm thử trên browser thật; không đổi `SameSite=None` một cách tùy tiện chỉ để “fix cookie”.

### 11.2. CSRF và cookie authentication

Browser tự động gửi cookie tới domain phù hợp. Vì vậy endpoint thay đổi trạng thái như POST/PUT/PATCH/DELETE cần xem xét CSRF:
- Dùng Spring Security CSRF protection theo loại ứng dụng.
- Kiểm tra Origin/Referer trong những flow phù hợp.
- Có thể dùng CSRF token/header hoặc cookie-to-header pattern nếu client cần.
- Không coi `SameSite` là lớp bảo vệ duy nhất.
- CORS không thay thế CSRF protection; CORS chủ yếu điều khiển browser có cho JavaScript đọc response hay không.

Nếu API dùng bearer token trong Authorization header do client chủ động gắn, threat model khác với cookie authentication tự động. Đừng áp dụng cùng giả định bảo mật cho mọi kiểu credential.

### 11.3. Session fixation và session hijacking

- Rotate session ID sau khi login bằng `changeSessionId()`.
- Không đưa session ID vào response JSON, URL, log hoặc tracing baggage.
- Bật TLS và Secure cookie.
- Đặt idle timeout hợp lý và absolute lifetime nếu domain yêu cầu.
- Invalidate session khi logout, revoke tài khoản hoặc thay đổi quyền quan trọng.
- Hạn chế quyền truy cập Redis/session repository và bật network encryption/authentication.
- Không lưu credential thô hoặc object quá lớn trong session.
- Không dùng session ID làm bằng chứng duy nhất cho authorization; kiểm tra user/permission theo chính sách.

### 11.4. Race khi nhiều request dùng cùng session

Một browser có thể gửi nhiều request song song với cùng session ID. Hai request cùng đọc `cartCount=2`, cùng tăng lên 3 và cùng lưu; một cập nhật có thể ghi đè cập nhật kia tùy store/logic. Không dùng session attribute như bộ đếm giao dịch hoặc kho dữ liệu có yêu cầu atomicity.

Với state quan trọng:
- Dùng database/Redis atomic operation hoặc transaction phù hợp.
- Giữ session attribute nhỏ, chủ yếu là context/UI state.
- Tránh lưu mutable object graph dùng chung giữa nhiều request.
- Nếu cần versioning, dùng optimistic locking hoặc command/idempotency.
- Không giả định Reactor serialize tất cả request của cùng session trên một thread.

## 12. WebFlux.fn: cookie và session trong functional endpoint

Functional handler đọc cookie từ `ServerRequest.cookies()` và lấy session bằng `ServerRequest.session()`:

~~~java
Mono<ServerResponse> sessionProfile(ServerRequest request) {
    return request.session().flatMap(session -> {
        String user = session.getAttribute("user");

        if (user == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
            .bodyValue(Map.of("user", user));
    });
}
~~~

Ghi cookie qua `ServerResponse`:

~~~java
Mono<ServerResponse> setTheme() {
    ResponseCookie cookie = ResponseCookie.from("theme", "dark")
        .path("/")
        .httpOnly(true)
        .secure(true)
        .sameSite("Lax")
        .maxAge(Duration.ofDays(30))
        .build();

    return ServerResponse.noContent()
        .cookie(cookie)
        .build();
}
~~~

Với `RouterFunction`, handler có thể ghép route, filter và error mapping. Session API vẫn là `WebSession`; khác biệt chỉ là lấy session từ `request.session()` thay vì method argument hoặc `exchange.getSession()`.

## 13. Cookie và session lifecycle: sơ đồ đầy đủ

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant R as WebFlux
    participant M as WebSessionManager
    participant S as WebSessionStore

    B->>R: POST /login
    Note over B,R: Chưa có SESSION cookie
    R->>M: getSession(exchange)
    M->>S: retrieveSession(id) hoặc createWebSession()
    S-->>M: WebSession mới
    M-->>R: WebSession
    R->>R: Xác thực user, ghi attributes
    R->>R: changeSessionId() nếu login cần rotate
    R-->>B: 200 + Set-Cookie: SESSION=<opaque-id>
    Note over R,S: save session trước response commit

    B->>R: GET /profile + Cookie: SESSION=id
    R->>M: resolve session id
    M->>S: retrieveSession(id), kiểm tra expiry
    S-->>R: WebSession + attributes
    R-->>B: 200 + profile

    B->>R: POST /logout + Cookie: SESSION=id
    R->>S: invalidate/remove session
    R-->>B: 204 + cookie hết hạn
    B->>R: GET /profile + cookie cũ (nếu còn)
    R-->>B: session mới, không có user attribute
~~~

Sơ đồ biểu diễn lifecycle logic. Thời điểm ghi cookie/session được framework phối hợp với response commit; ứng dụng không cần tự gọi `save()` ở mỗi controller.

## 14. Ví dụ HTTP thực tế

Giả sử server dùng default session cookie `SESSION`.

**1. Tạo session**

~~~http
POST /api/session/start HTTP/1.1
Host: localhost:8080
~~~

Response có thể gồm:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-id>; Path=/; HttpOnly
Content-Type: application/json

{"user":"Ada","visits":0}
~~~

Các thuộc tính cookie cụ thể phụ thuộc resolver/configuration; ví dụ trên chỉ minh họa tên cookie và session ID.

**2. Gửi lại cookie**

~~~http
GET /api/session/me HTTP/1.1
Host: localhost:8080
Cookie: SESSION=<opaque-id>
~~~

Server tìm được cùng session và đọc attribute `user`, `visits`.

**3. Logout**

~~~http
DELETE /api/session HTTP/1.1
Host: localhost:8080
Cookie: SESSION=<opaque-id>
~~~

Server invalidate session và resolver yêu cầu browser hết hạn cookie ID. Request sau đó không thể lấy lại session state đã xóa.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nhầm cookie với WebSession | Đưa toàn bộ dữ liệu session vào client | Cookie chỉ giữ ID; state nằm trong store. |
| Gọi `exchange.getSession()` rồi nghĩ session đã started | Browser không nhận session ID khi chưa start | Thêm attribute hoặc gọi `start()`. |
| Tự gọi `session.save().subscribe()` | Save chạy ngoài HTTP lifecycle, lỗi/race khó theo dõi | Trả Publisher, để framework save trước commit. |
| Logout chỉ xóa cookie browser | Server-side session vẫn còn hiệu lực | Gọi `WebSession.invalidate()`. |
| Chỉ invalidate storage nhưng quên session ID rotation khi login | Session fixation risk | `changeSessionId()` sau authentication. |
| Để cookie auth không có Secure/HttpOnly | Tăng rủi ro đánh cắp credential | Dùng HTTPS, Secure, HttpOnly và SameSite phù hợp. |
| Dùng SameSite như CSRF protection duy nhất | Vẫn có đường CSRF tùy browser/flow | Dùng Spring Security CSRF và kiểm tra Origin theo threat model. |
| Cookie xóa sai Path/Domain | Cookie cũ vẫn tồn tại | Gửi Max-Age=0 với cùng scope. |
| Cookie có Domain quá rộng | Subdomain khác có thể nhận cookie | Ưu tiên host-only cookie khi có thể. |
| Dùng cookie làm authorization source | Client có thể sửa giá trị | Validate, ký/mã hóa nếu cần và kiểm tra quyền server-side. |
| Session timeout quá dài | Session bị bỏ quên có thể còn hiệu lực | Đặt idle timeout và absolute lifetime hợp lý. |
| Dùng InMemoryWebSessionStore cho nhiều replica | Instance khác không tìm được session | Spring Session với Redis hoặc repository phân tán. |
| Đưa object lớn vào session | Tốn memory, serialization và network | Chỉ lưu state nhỏ hoặc ID tham chiếu. |
| Cập nhật session counter như dữ liệu giao dịch | Concurrent requests có thể ghi đè | Dùng atomic storage/transaction cho dữ liệu quan trọng. |
| Đưa session ID vào URL | ID rò rỉ qua history/log/Referer | Dùng cookie hoặc header qua TLS. |
| Dùng `JSESSIONID` như tên mặc định WebFlux | Debug nhầm giữa Servlet và reactive stack | WebFlux `CookieWebSessionIdResolver` mặc định dùng `SESSION`. |

## 16. Checklist production

- [ ] Phân biệt rõ cookie ứng dụng và cookie mang WebSession ID.
- [ ] Cookie input được xem là untrusted và được validate.
- [ ] Session cookie có Secure, HttpOnly, SameSite và Path phù hợp.
- [ ] Cookie deletion dùng đúng name/path/domain và Max-Age=0.
- [ ] Session chỉ bắt đầu khi cần; không tạo session vô tình cho mọi anonymous request.
- [ ] Attribute session nhỏ, kiểu dữ liệu rõ và không chứa credential thô.
- [ ] `save()` được framework quản lý; không subscribe thủ công.
- [ ] Login/privilege elevation rotate session ID.
- [ ] Logout/revocation invalidate session phía server.
- [ ] Idle timeout và cookie lifetime được thiết kế riêng nhưng tương thích.
- [ ] CSRF protection được cấu hình cho cookie-authenticated state-changing endpoints.
- [ ] In-memory store chỉ dùng khi lifecycle/single-instance phù hợp; multi-instance có session repository chung.
- [ ] Concurrent update quan trọng dùng atomic operation hoặc transaction.
- [ ] Integration tests kiểm tra Set-Cookie, Cookie request, session continuity, rotation và logout.

## 17. Bài tập thực hành

**Bài 1 – Đọc cookie.** Viết GET `/api/theme` dùng `@CookieValue` với default `system`. Gửi request có và không có cookie; so sánh body.

**Bài 2 – Set-Cookie.** Tạo cookie `theme=dark` bằng `ResponseCookie`; bật HttpOnly, Secure, SameSite và Path. Kiểm tra response header.

**Bài 3 – Xóa cookie.** Gửi cookie có Max-Age=0 và đúng Path/Domain. Kiểm tra browser/cookie jar không gửi lại cookie ở request tiếp theo.

**Bài 4 – Session lifecycle.** Tạo POST `/start` thêm `user` attribute. Gửi GET `/me` với cùng cookie; xác nhận server đọc lại `user`.

**Bài 5 – Session rotation.** Gọi `changeSessionId()` sau login. Xác nhận response gửi ID mới và session attributes vẫn tồn tại.

**Bài 6 – Logout.** Gọi `invalidate()`; dùng cookie jar kiểm tra request tiếp theo không còn attribute cũ.

**Bài 7 – Idle timeout.** Đặt max idle time ngắn, dùng `Clock`/store phù hợp trong test hoặc test tích hợp có kiểm soát thời gian để quan sát session hết hạn. Tránh `Thread.sleep` dài không cần thiết.

**Bài 8 – Redis session.** Thay store in-memory bằng Spring Session Redis; chạy hai instance và kiểm tra session tạo ở instance A được đọc ở instance B.

**Bài 9 – CSRF.** Bật Spring Security CSRF cho endpoint dùng cookie; gửi POST thiếu token và có token, kiểm tra status.

## 18. Tài liệu tham khảo chính thức

1. Spring Framework 7.0.8 Javadoc – `WebSession`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
2. Spring Framework – `@CookieValue` trong WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/cookievalue.html
3. Spring Framework – `@SessionAttribute`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattribute.html
4. Spring Framework – `@SessionAttributes`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/sessionattributes.html
5. Spring Framework Javadoc – `CookieWebSessionIdResolver`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
6. Spring Framework Javadoc – `WebSessionManager` / `DefaultWebSessionManager`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html
7. Spring Framework Javadoc – `WebSessionStore` / `InMemoryWebSessionStore`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionStore.html
8. Spring Framework Javadoc – `ResponseCookie`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ResponseCookie.html
9. Spring Session – WebSession Integration and Redis: https://docs.spring.io/spring-session/reference/web-session.html
10. Spring Security – Reactive WebFlux Security and CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html

**Tự đánh giá cuối:** Vì sao `getSession()` chưa chắc đã gửi cookie? Điều gì khác nhau giữa `changeSessionId()` và `invalidate()`? Vì sao xóa cookie browser mà không invalidate server-side session là chưa đủ? Nếu session hết idle time nhưng browser vẫn gửi ID cũ, server xử lý thế nào? Khi giải thích được cả cookie flow, session store và logout lifecycle, bạn đã hiểu cách quản lý cookie/phiên trong WebFlux.


## 19. Dự án Java 17+ chạy được: cookie và session lifecycle

Project dùng Spring Boot 4.0.9, Java 17+ và WebFlux. Nó minh họa:
- Tạo session và ghi attributes.
- Đọc session ở request sau bằng cùng cookie jar.
- Đổi session ID sau authentication.
- Logout bằng invalidate.
- Đọc cookie tùy chỉnh bằng `@CookieValue`.
- Ghi/xóa cookie có thuộc tính bảo mật.
- Kiểm thử HTTP bằng JDK `HttpClient` và `CookieManager`.

### 19.1. Cấu trúc thư mục

~~~text
webflux-cookie-session/
├── pom.xml
├── src/main/java/com/example/session/SessionCookieApplication.java
├── src/main/java/com/example/session/SessionView.java
├── src/main/java/com/example/session/SessionController.java
├── src/main/java/com/example/session/CookieController.java
└── src/test/java/com/example/session/SessionCookieIntegrationTest.java
~~~

### 19.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-cookie-session</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 19.3. SessionCookieApplication.java

~~~java
package com.example.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionCookieApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionCookieApplication.class, args);
    }
}
~~~

### 19.4. SessionView.java

~~~java
package com.example.session;

public record SessionView(String user, int visits) {}
~~~

### 19.5. SessionController.java

~~~java
package com.example.session;

import java.time.Duration;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/session")
public class SessionController {

    @PostMapping("/start")
    public Mono<SessionView> start(WebSession session) {
        session.setMaxIdleTime(Duration.ofMinutes(10));
        session.getAttributes().put("user", "Ada");
        session.getAttributes().put("visits", 0);

        return Mono.just(new SessionView("Ada", 0));
    }

    @GetMapping("/me")
    public Mono<ResponseEntity<SessionView>> me(WebSession session) {
        return Mono.defer(() -> {
            String user = session.getAttribute("user");

            if (user == null) {
                return Mono.just(
                    ResponseEntity.<SessionView>notFound().build());
            }

            int visits = session.getAttributeOrDefault("visits", 0) + 1;
            session.getAttributes().put("visits", visits);

            return Mono.just(ResponseEntity.ok(
                new SessionView(user, visits)));
        });
    }

    @PostMapping("/rotate")
    public Mono<ResponseEntity<SessionView>> rotate(WebSession session) {
        String user = session.getAttribute("user");

        if (user == null) {
            return Mono.just(
                ResponseEntity.<SessionView>notFound().build());
        }

        int visits = session.getAttributeOrDefault("visits", 0);

        return session.changeSessionId()
            .thenReturn(ResponseEntity.ok(
                new SessionView(user, visits)));
    }

    @DeleteMapping
    public Mono<ResponseEntity<Void>> logout(WebSession session) {
        return session.invalidate()
            .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

Giải thích:
- `/start` thêm attribute, do đó session được started ngầm; `setMaxIdleTime` đặt idle timeout 10 phút.
- `/me` đọc session đã có, tăng visits và trả `404` nếu không có user.
- `/rotate` đổi ID nhưng giữ session attributes; trong flow thật chỉ gọi sau khi xác thực thành công.
- `DELETE /api/session` invalidate session. Framework xử lý việc save/expire ID cookie theo lifecycle response.

Controller không tự subscribe và không gọi `session.save()`.

### 19.6. CookieController.java

~~~java
package com.example.session;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/cookies")
public class CookieController {

    @GetMapping("/theme")
    public Map<String, String> theme(
            @CookieValue(
                name = "theme",
                required = false,
                defaultValue = "system"
            ) String theme) {
        return Map.of("theme", theme);
    }

    @PostMapping("/theme")
    public ResponseEntity<Void> setTheme(
            ServerHttpResponse response) {

        ResponseCookie cookie = ResponseCookie.from("theme", "dark")
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .maxAge(Duration.ofDays(30))
            .build();

        response.addCookie(cookie);
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/theme")
    public ResponseEntity<Void> clearTheme(
            ServerHttpResponse response) {

        ResponseCookie expired = ResponseCookie.from("theme", "")
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax")
            .maxAge(Duration.ZERO)
            .build();

        response.addCookie(expired);
        return ResponseEntity.noContent().build();
    }
}
~~~

Cookie `theme` được đặt Secure để dùng trên HTTPS. Test gửi cookie thủ công khi kiểm tra `@CookieValue`; browser/client HTTP thường không gửi Secure cookie qua kết nối HTTP thường.

### 19.7. SessionCookieIntegrationTest.java

~~~java
package com.example.session;

import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SessionCookieIntegrationTest {

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> send(
            HttpClient client, String method, String path)
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .method(method, HttpRequest.BodyPublishers.noBody())
            .build();

        return client.send(
            request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void sessionPersistsRotatesAndIsInvalidatedOnLogout()
            throws Exception {

        CookieManager cookieManager =
            new CookieManager(null, CookiePolicy.ACCEPT_ALL);

        HttpClient client = HttpClient.newBuilder()
            .cookieHandler(cookieManager)
            .build();

        HttpResponse<String> start =
            send(client, "POST", "/api/session/start");

        assertEquals(200, start.statusCode());
        assertTrue(cookieManager.getCookieStore().getCookies()
            .stream().anyMatch(cookie ->
                cookie.getName().equals("SESSION")));

        String originalId = cookieManager.getCookieStore().getCookies()
            .stream()
            .filter(cookie -> cookie.getName().equals("SESSION"))
            .findFirst()
            .orElseThrow()
            .getValue();

        HttpResponse<String> firstRead =
            send(client, "GET", "/api/session/me");

        assertEquals(200, firstRead.statusCode());
        assertTrue(firstRead.body().contains("\"user\":\"Ada\""));
        assertTrue(firstRead.body().contains("\"visits\":1"));

        HttpResponse<String> rotate =
            send(client, "POST", "/api/session/rotate");

        assertEquals(200, rotate.statusCode());

        String rotatedId = cookieManager.getCookieStore().getCookies()
            .stream()
            .filter(cookie -> cookie.getName().equals("SESSION"))
            .findFirst()
            .orElseThrow()
            .getValue();

        assertNotEquals(originalId, rotatedId);

        HttpResponse<String> secondRead =
            send(client, "GET", "/api/session/me");

        assertEquals(200, secondRead.statusCode());
        assertTrue(secondRead.body().contains("\"visits\":2"));

        HttpResponse<String> logout =
            send(client, "DELETE", "/api/session");

        assertEquals(204, logout.statusCode());

        HttpResponse<String> afterLogout =
            send(client, "GET", "/api/session/me");

        assertEquals(404, afterLogout.statusCode());
    }

    @Test
    void cookieValueCanBeReadAndResponseCookieCanBeHardened()
            throws Exception {

        HttpClient client = HttpClient.newHttpClient();

        HttpRequest readRequest = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + "/api/cookies/theme"))
            .header("Cookie", "theme=dark")
            .GET()
            .build();

        HttpResponse<String> read = client.send(
            readRequest, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, read.statusCode());
        assertTrue(read.body().contains("\"theme\":\"dark\""));

        HttpResponse<String> set = send(
            client, "POST", "/api/cookies/theme");

        assertEquals(204, set.statusCode());

        String setCookie = set.headers()
            .allValues("Set-Cookie")
            .stream()
            .filter(value -> value.startsWith("theme="))
            .findFirst()
            .orElseThrow();

        assertTrue(setCookie.contains("Path=/"));
        assertTrue(setCookie.contains("Secure"));
        assertTrue(setCookie.contains("HttpOnly"));
        assertTrue(setCookie.contains("SameSite=Lax"));

        HttpResponse<String> clear = send(
            client, "DELETE", "/api/cookies/theme");

        assertEquals(204, clear.statusCode());

        String expiredCookie = clear.headers()
            .allValues("Set-Cookie")
            .stream()
            .filter(value -> value.startsWith("theme="))
            .findFirst()
            .orElseThrow();

        assertTrue(expiredCookie.contains("Max-Age=0"));
    }
}
~~~

Test dùng cookie jar thật cho session flow:
1. POST `/start` nhận `SESSION` cookie.
2. GET `/me` gửi lại cookie và thấy attribute.
3. POST `/rotate` nhận session ID mới nhưng giữ dữ liệu.
4. GET `/me` tiếp tục đọc cùng session.
5. DELETE logout invalidate; GET sau đó không còn user attribute.

Test cookie `theme` kiểm tra `@CookieValue`, `Set-Cookie` flags và `Max-Age=0`. `Secure` cookie được kiểm tra qua response header; test không dựa vào việc gửi nó qua HTTP.

### 19.8. Chạy và thử bằng curl

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Có thể dùng cookie jar của curl để giữ session ID qua nhiều request:

~~~bash
curl -i -c cookies.txt -X POST http://localhost:8080/api/session/start
curl -i -b cookies.txt http://localhost:8080/api/session/me
curl -i -b cookies.txt -c cookies.txt -X POST http://localhost:8080/api/session/rotate
curl -i -b cookies.txt -X DELETE http://localhost:8080/api/session
curl -i -b cookies.txt http://localhost:8080/api/session/me
~~~

Với cookie theme, do ví dụ đặt Secure=true, hãy thử trên HTTPS hoặc gửi cookie thủ công khi đang dùng localhost HTTP:

~~~bash
curl -i --cookie "theme=dark" http://localhost:8080/api/cookies/theme
curl -i -X POST https://localhost:8080/api/cookies/theme
curl -i -X DELETE https://localhost:8080/api/cookies/theme
~~~

**Kết quả mong đợi:** session `/start` tạo cookie `SESSION`; `/me` trả user Ada; `/rotate` thay ID; `/logout` trả 204 và xóa server-side state; request tiếp theo trả 404. Cookie theme được trả với `Path`, `Secure`, `HttpOnly`, `SameSite=Lax` và khi xóa có `Max-Age=0`.
