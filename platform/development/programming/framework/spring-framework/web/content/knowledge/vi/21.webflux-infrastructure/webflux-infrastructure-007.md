# WebSession, LocaleContext và Reactor Context trong Spring WebFlux

## 1. Mục tiêu và ngữ cảnh

Khi chuyển từ Spring MVC Servlet sang **Spring WebFlux**, ta vẫn phải xử lý trạng thái người dùng, ngôn ngữ giao diện, tracing, correlation ID, security và các thông tin cần đi qua pipeline bất đồng bộ. Nhưng không thể mang nguyên các giả định `HttpSession`, `LocaleContextHolder` hay `ThreadLocal` của mô hình request-thread cũ sang Reactor mà không kiểm tra vòng đời dữ liệu.

Spring WebFlux cung cấp ba khái niệm liên quan nhưng **khác bản chất**:

- **`WebSession`**: phiên server-side, mang session attributes qua **nhiều HTTP requests** của cùng client khi có session ID hợp lệ; có vòng đời và kho lưu trữ.
- **`LocaleContext`**: thông tin ngôn ngữ/vùng miền (và tùy resolver có thể có múi giờ) được xác định cho **HTTP exchange hiện tại**; thông thường dựa trên `Accept-Language`.
- **Reactor `Context`/`ContextView`**: tập metadata immutable-key/value đi theo **một reactive subscription**, truyền qua async operators mà không đòi hỏi một thread cố định. Nó không phải database session hay HTTP session.

Sau bài này, bạn sẽ có thể:

1. Phân biệt **`WebSession`**, `ServerWebExchange`, `LocaleContext`, Reactor `Context` và `ThreadLocal` theo scope/lifetime.
2. Dùng `ServerWebExchange.getSession()` hoặc argument `WebSession` để đọc, ghi, invalidate, rotate session ID và đặt idle timeout đúng cách.
3. Biết **đọc session không đồng nghĩa tạo cookie phiên mới**; session chỉ khởi động khi ghi attributes hoặc `start()` rõ ràng.
4. Dùng `ServerWebExchange.getLocaleContext()` và `LocaleContextResolver`; hiểu `AcceptHeaderLocaleContextResolver` mặc định và lý do `setLocaleContext` có thể không được hỗ trợ.
5. Sử dụng `Mono.deferContextual`, `contextWrite` và `WebFilter` truyền request correlation ID qua `publishOn`/`flatMap` đúng Reactor semantics.
6. Tích hợp Spring Security reactive qua `ReactiveSecurityContextHolder` mà không nhầm với `SecurityContextHolder`/Servlet session.
7. Xây ứng dụng **Java 17+, Spring Boot 3.x + Spring WebFlux**, có stateful endpoint, Locale, Reactor Context và kiểm thử HTTP thật bằng `WebTestClient`.
8. Nhận diện rủi ro lưu dữ liệu mutable trong session, client không gửi cookie, mất context do subscribe thủ công, leak session ID, cache/CORS/SameSite và tình huống scale nhiều instance.

**Phiên bản thực hành:** Spring Framework **6.x**, Spring Boot **3.x**, Reactor 3.x, Java 17+. Ví dụ dùng WebFlux trên reactive HTTP server; không thêm `spring-boot-starter-web` để tránh Boot chọn MVC khi đồng thời có hai web starters. Cú pháp/conventions có thể đổi khi lên Spring Framework 7/Boot 4; tra tài liệu theo version đang sử dụng.

## 2. Bản đồ vòng đời: ba context không thể thay thế nhau

| Đối tượng | Phạm vi | Tồn tại qua HTTP requests? | Giữ dữ liệu ở đâu? | Truy cập thông thường |
| --- | --- | --- | --- | --- |
| `WebSession` | Session của client/server | **Có**, nếu session còn hạn và ID được trả lại | `WebSessionStore`, mặc định in-memory hoặc Spring Session backend | `exchange.getSession()`/`WebSession` |
| `ServerWebExchange` attributes | **Một** HTTP exchange | Không tự động | Map request/exchange-scoped | `exchange.getAttributes()` |
| `LocaleContext` | Locale của HTTP exchange | Không tự động | Resolver đọc request/strategy | `exchange.getLocaleContext()` |
| Reactor `Context` | **Một reactive subscriber/subscription** | Không tự động | Context gắn vào subscriber chain | `Mono.deferContextual`, `contextWrite` |
| Java `ThreadLocal` | Một JVM thread | Không có bảo đảm phù hợp với request/reactive signals | Thread hiện tại | `ThreadLocal.get()` |
| Reactive security context | Reactive subscription/request security chain | Chỉ khi security có cơ chế lưu/auth thích hợp | Reactor Context, security repository khi cấu hình | `ReactiveSecurityContextHolder` |

Một request thực tế có thể cùng lúc có cả bốn thứ:

~~~text
Browser ---- Cookie: SESSION=... ----> ServerWebExchange
                                        |
                                        +-- WebSession
                                        |     savedTheme=dark
                                        |
                                        +-- LocaleContext
                                        |     locale=vi-VN (Accept-Language)
                                        |
                                        +-- exchange.attributes
                                        |     requestId=req-001
                                        |
                                        +-- WebFilter
                                              |
                                              v
                                        Reactor subscription Context
                                              requestId=req-001
                                              security context ...
                                              |
                                  publishOn / flatMap / WebClient...
                                              |
                                              v
                                        HTTP response
~~~

**Quan trọng:** Reactor Context không biến dữ liệu thành trạng thái lâu dài của user. Khi request kết thúc, request-scoped Context không tự được lưu. Nếu cần giữ một tùy chọn cho request sau, chọn phương án phù hợp như WebSession, database/user profile hoặc cookie tùy use case và threat model.

## 3. WebSession là gì?

`org.springframework.web.server.WebSession` là hợp đồng session server-side của WebFlux. Nó **không phải** `jakarta.servlet.http.HttpSession`, và việc dùng WebFlux trên một Servlet container cũng không có nghĩa controller reactive nên phụ thuộc trực tiếp HttpSession.

Các API đáng nhớ:

| API | Ý nghĩa | Chú ý |
| --- | --- | --- |
| `getId()` | ID của session | Cần coi là dữ liệu nhạy cảm, không trả ra JSON/log |
| `getAttributes()` | Map chứa attributes | Có thể chứa mutable objects, cần đồng bộ/thiết kế state |
| `getAttribute(name)` | Đọc một attribute | Không bảo đảm đã tồn tại hoặc đúng kiểu |
| `getAttributeOrDefault(...)` | Đọc kèm fallback | Hữu ích cho tùy chọn nhỏ |
| `getCreationTime()` | Mốc tạo session | Không phải thời gian đăng nhập |
| `getLastAccessTime()` | Mốc truy cập gần nhất | Tùy store và hoạt động phiên |
| `getMaxIdleTime()` | Khoảng idle tối đa | Không phải cookie max-age hoặc absolute expiry |
| `setMaxIdleTime(Duration)` | Cập nhật thời gian idle | Cân nhắc policy chung |
| `isStarted()` | Session đã được start chưa | Chỉ `getSession()` không tự start |
| `start()` | Buộc session bắt đầu | Dẫn tới cookie/session ID khi lưu |
| `invalidate()` | Invalidate và xóa session storage | **Trả `Mono<Void>`**, phải compose/subscription |
| `changeSessionId()` | Rotate session ID | **Trả `Mono<Void>`**, cần hoàn thành thật |
| `save()` | Lưu session ở store | Thường được framework tự gọi trước khi response commit |

### 3.1. Lấy session mà không khởi tạo phiên lưu trữ

`ServerWebExchange.getSession()` trả:

~~~java
Mono<WebSession> sessionMono = exchange.getSession();
~~~

Dạng method minh họa với `ServerWebExchange exchange`. WebSessionManager bảo đảm có một `WebSession` mới hoặc session khớp ID client (nếu tồn tại và chưa hết hạn), nhưng **đọc/nhận một đối tượng WebSession không tự tạo session cookie**.

Ví dụ đọc:

~~~java
public Mono<String> theme(ServerWebExchange exchange) {
    return exchange.getSession()
            .map(session ->
                    session.getAttributeOrDefault("theme", "light"));
}
~~~

Nếu request chưa có session started, đoạn này thường không bắt browser lưu session mới. Khi request có cookie phiên cũ hợp lệ, nó có thể đọc `theme` được lưu trước đó.

### 3.2. Thêm attribute → session được start ngầm

~~~java
public Mono<Void> chooseTheme(ServerWebExchange exchange) {
    return exchange.getSession()
            .doOnNext(session ->
                    session.getAttributes().put("theme", "dark"))
            .then();
}
~~~

Khi attribute được thêm vào session mới, `WebSession` thường được start ngầm. Trong WebFlux mặc định, framework gọi lưu session đúng lifecycle trước khi response commit. **Không tự `session.save().block()` trên event loop**; `save()` vốn là reactive và framework chủ động quản lý.

Hãy nhớ: thêm attribute vào Map là một thao tác trong memory của session object, không biến Map thành transaction DB. Với distributed session store, persistence/serialization/synchronization là vấn đề riêng.

### 3.3. start() khi không có attribute

~~~java
public Mono<String> start(ServerWebExchange exchange) {
    return exchange.getSession().map(session -> {
        session.start();
        return "started";
    });
}
~~~

Đây là method minh họa. `start()` ép phiên bắt đầu kể cả Map attributes đang trống. Chỉ dùng khi nghiệp vụ cần thực sự tạo session; **đừng start mọi request theo thói quen**, làm tăng số session/cookie và chi phí storage không cần thiết.

### 3.4. Invalidate và rotate session ID đúng kiểu reactive

~~~java
@PostMapping("/logout")
public Mono<Void> logout(WebSession session) {
    return session.invalidate();
}
~~~

~~~java
@PostMapping("/rotate")
public Mono<Void> rotate(WebSession session) {
    return session.changeSessionId();
}
~~~

Hai snippet là handler minh họa, cần class controller và imports. Vì `invalidate()`/`changeSessionId()` trả `Mono<Void>`, **phải return hoặc compose Publisher**. Chỉ gọi method rồi bỏ giá trị:

~~~java
session.invalidate(); // sai: không subscribe/return
return Mono.empty();
~~~

có thể khiến công việc invalidate chưa được thực thi. Tương tự, không tự gọi `.subscribe()` để fire-and-forget vì có thể phá error propagation, cancellation và lifecycle response.

Session ID rotation là một lớp phòng vệ session fixation khi authentication state thay đổi; **không tự ý coi chỉ gọi rotate là toàn bộ thiết kế bảo mật**. Khi ứng dụng dùng Spring Security, để security framework quản lý session/authentication policies theo đúng chain.

## 4. WebSessionManager, WebSessionStore và cookie/session ID

Luồng quản trị session:

~~~text
Browser
  | Cookie: SESSION=<opaque-id>
  v
WebSessionIdResolver
  | resolveSessionIds(exchange)
  v
WebSessionManager (DefaultWebSessionManager)
  | lookup hoặc tạo session object
  v
WebSessionStore
  | retrieve/store/expire
  v
WebSession.getAttributes()

Before HTTP response commit:
  WebSession.save() -> store + WebSessionIdResolver response cookie
~~~

Các thành phần:

- **`WebSessionManager`**: lấy session theo HTTP exchange. Mặc định `DefaultWebSessionManager`.
- **`WebSessionIdResolver`**: lấy/gửi ID giữa client và server. Mặc định thường dùng `CookieWebSessionIdResolver`, cookie tên **`SESSION`** trong cấu hình WebFlux thông thường.
- **`WebSessionStore`**: lưu và truy xuất session. Mặc định WebFlux có thể dùng **in-memory store**, không dùng chung giữa nhiều instances.
- **Spring Session**: có thể cung cấp persistent/distributed reactive session store (ví dụ Redis) khi cấu hình dependency và repository tương thích.

**Đừng nhầm cookie chứa session ID với dữ liệu session:** ở phương án mặc định, giá trị `theme` hay `cart` được giữ server-side; cookie chủ yếu chứa một ID ngẫu nhiên/opaque dùng để lookup. Ai lấy được một session ID hợp lệ có thể thử chiếm phiên, nên áp dụng TLS, Secure/HttpOnly/SameSite, session rotation và bảo vệ XSS/CSRF phù hợp.

### 4.1. Đặt thời gian sống

Hai khái niệm khác nhau:

- **Idle timeout trên WebSession**: nếu không có user activity sau `getLastAccessTime()` trong khoảng `maxIdleTime`, session bị coi là expired.
- **Cookie Max-Age/Expires**: browser còn giữ/gửi cookie bao lâu. Cookie vẫn tồn tại không bảo đảm server-side session chưa expired, và cookie bị xóa không nhất thiết ngay lập tức xóa storage server khi không có logout request.

Spring Boot 3.5 có nhóm cấu hình reactive session, ví dụ:

~~~properties
server.reactive.session.timeout=30m
server.reactive.session.cookie.same-site=lax
server.reactive.session.cookie.secure=true
~~~

Đây là cấu hình **minh họa deployment HTTPS production**, không phải cấu hình bắt buộc cho bài chạy trên `http://localhost`: cookie `Secure` có thể không được client gửi qua HTTP thường. Tên properties phải kiểm tra theo **Spring Boot version đang chạy** (Boot 3.x có khác biệt giữa các minor versions và auto-configuration). Những thuộc tính được dẫn theo Boot 3.5 docs; nếu dùng Boot 3.0/3.1 hãy kiểm tra reference tương ứng.

Không đặt `setMaxIdleTime(Duration.ofMinutes(...))` trên mọi request nếu đã có policy tập trung mà không có lý do; mất kiểm soát session TTL giữa các endpoints. Một số stores có expiration semantics riêng và cleanup chậm, cần giám sát.

### 4.2. Cookie security và CORS

Khi frontend chạy ở origin khác gọi backend có session cookie:
- `fetch` có thể cần `credentials: "include"` và server CORS cho phép origin cụ thể + `Access-Control-Allow-Credentials: true`.
- Cookie vẫn phải thỏa `SameSite`, `Secure`, `Domain`, `Path`, expiry và third-party cookie restrictions.
- **CORS không thay CSRF protection**. Với cookie auth, unsafe methods POST/PUT/DELETE vẫn cần cơ chế chống CSRF thích hợp.
- `HttpOnly` hạn chế JavaScript đọc cookie; không ngăn browser gửi cookie trong requests đủ điều kiện.
- Không sử dụng `allowedOrigins("*")` cùng credentialed CORS; Spring/browser không chấp nhận tổ hợp ấy.

Nếu test bằng `curl` không lưu cookie, mỗi request sẽ có một WebSession mới. Nếu test bằng browser có cookie nhưng session store là memory ở node A còn load balancer chuyển qua node B, phiên có thể mất; cần sticky sessions đúng chính sách hoặc shared session repository.

## 5. Session attributes: kiểu dữ liệu, concurrency và memory

Tránh lưu cả object graph nặng hoặc object khó serialize trong session. Hợp lý hơn:

~~~java
session.getAttributes().put("preferredLanguage", "vi");
session.getAttributes().put("favoriteColor", "blue");
~~~

Không nên đặt:

~~~java
session.getAttributes().put("password", rawPassword);
session.getAttributes().put("request", exchange);
session.getAttributes().put("openStream", inputStream);
~~~

Ba dòng trên là **anti-pattern**, với biến chưa định nghĩa. Session có thể sống qua nhiều requests; giữ request/stream có thể làm resource leak, credentials trong session có thể bị đánh cắp khi storage/log leak, và distributed serialization sẽ gặp lỗi.

### 5.1. Mutable session state có thể bị race

Giả sử hai AJAX requests cùng session chạy đồng thời và cập nhật một `ArrayList` hoặc map đếm giỏ hàng. `session.getAttributes()` **không có nghĩa** các object con của session tự động thread-safe, không có database transaction. Hai request có thể mất cập nhật hoặc ghi lại phiên bản session cũ vào shared store.

Một lựa chọn an toàn hơn cho dữ liệu quan trọng là **DB với transaction/optimistic locking**, lưu session tối thiểu các identifiers:

~~~java
session.getAttributes().put("cartId", cartId);
~~~

Đoạn minh họa dùng `cartId` đã tạo từ server và validate. Không dùng mutable session attributes làm nguồn sự thật cho tồn kho, số dư, quyền truy cập hoặc các thao tác đa bước cần consistency mạnh.

### 5.2. @SessionAttribute và @SessionAttributes

- `@SessionAttribute` trên argument đọc **attribute đã tồn tại** trong session và có thể dùng khi attribute được quản lý bên ngoài controller, ví dụ filter.
- `@SessionAttributes` trên **class @Controller** dùng cho một workflow nhiều request, lưu một số model attributes giữa các request, thường kết hợp `SessionStatus.setComplete()` để đánh dấu kết thúc.
- Để chủ động thêm/xóa attributes, dùng `WebSession` trực tiếp thường minh bạch hơn.

Đừng nhầm `@SessionAttributes` (số nhiều) với `@SessionAttribute` (số ít) hoặc một annotation có thể cấu hình tất cả security/session TTL.

## 6. LocaleContext của WebFlux được lấy từ đâu?

`LocaleContext` nằm ở `org.springframework.context.i18n.LocaleContext`. Với WebFlux, `ServerWebExchange.getLocaleContext()` trả thông tin từ bean **`LocaleContextResolver`** tương ứng.

Theo Spring Framework 6.2, strategy mặc định là **`AcceptHeaderLocaleContextResolver`**, đọc `Accept-Language` từ request. Ví dụ:

~~~http
GET /api/context/state HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9,en-US;q=0.5
~~~

Nếu không cấu hình danh sách supported locales hạn chế, locale được resolver chọn có thể là `vi-VN`. Một request khác từ browser `en-US` sẽ nhận locale khác **mà không có bất kỳ WebSession attribute nào thay đổi**.

Đọc trong handler:

~~~java
@GetMapping("/language")
public Mono<String> language(ServerWebExchange exchange) {
    LocaleContext context = exchange.getLocaleContext();
    Locale locale = context.getLocale();
    String tag = locale == null ? "und" : locale.toLanguageTag();
    return Mono.just(tag);
}
~~~

Đây là method minh họa trong controller, cần import `LocaleContext`, `Locale`, `Mono` và annotation. `"und"` là language tag biểu thị **undetermined** khi không có locale, không bắt buộc response của mọi resolver.

### 6.1. Locale khác timezone

`Locale` thường mô tả ngôn ngữ/quốc gia dùng hiển thị (ví dụ `vi-VN`, `en-US`), **không phải** timezone. `LocaleContext` có thể được mở rộng bởi `TimeZoneAwareLocaleContext`, nhưng **`AcceptHeaderLocaleContextResolver` mặc định không cung cấp timezone** theo cơ chế đó.

Đoạn minh họa nhận timezone có điều kiện:

~~~java
LocaleContext lc = exchange.getLocaleContext();
TimeZone zone = lc instanceof TimeZoneAwareLocaleContext aware
        ? aware.getTimeZone()
        : null;
~~~

Đoạn trên cần `java.util.TimeZone`, `TimeZoneAwareLocaleContext`, `LocaleContext`, biến exchange. Không tự suy `Asia/Ho_Chi_Minh` chỉ vì `Locale.forLanguageTag("vi-VN")`; locale và timezone là hai dữ liệu độc lập.

### 6.2. AcceptHeaderLocaleContextResolver không phải nơi lưu locale tùy ý

`LocaleContextResolver` định nghĩa:
- `resolveLocaleContext(ServerWebExchange)`
- `setLocaleContext(ServerWebExchange, LocaleContext)`

Nhưng `AcceptHeaderLocaleContextResolver` **không hỗ trợ lưu/đổi locale qua `setLocaleContext`**: request header `Accept-Language` do client gửi. Gọi `setLocaleContext` có thể ném `UnsupportedOperationException` theo API. Nếu user chọn ngôn ngữ bằng UI và muốn ghi nhớ, bạn phải:
- Lưu lựa chọn ở profile database, WebSession hoặc cookie theo business design.
- Xây một resolver/filter/controller có chính sách lựa chọn hợp lệ (ví dụ ưu tiên profile/session hơn Accept-Language).
- Xác định precedence một cách rõ ràng và dùng locale thực tế khi format.
- Không ghi `LocaleContextHolder.setLocale(...) ` rồi cho rằng reactive pipeline luôn nhận đúng qua các async thread shifts.

### 6.3. Cấu hình supported locales

Ví dụ Spring Framework 6.2:

~~~java
@Configuration
public class LocaleWebConfig {
    @Bean(name = "localeContextResolver")
    public LocaleContextResolver localeContextResolver() {
        AcceptHeaderLocaleContextResolver resolver =
                new AcceptHeaderLocaleContextResolver();
        resolver.setSupportedLocales(
                List.of(Locale.forLanguageTag("vi-VN"),
                        Locale.forLanguageTag("en-US")));
        resolver.setDefaultLocale(Locale.forLanguageTag("vi-VN"));
        return resolver;
    }
}
~~~

**Đây là class minh họa bổ sung, không phải phần buộc phải thêm vào demo ở mục 10.** Imports cần: `Configuration`, `Bean`, `LocaleContextResolver` từ `org.springframework.web.server.i18n`, `AcceptHeaderLocaleContextResolver`, `List`, `Locale`. Trong application có Spring Boot auto-configuration, phải kiểm tra chính sách bean overriding/conditional config nếu đã có resolver từ Boot hoặc thư viện; không tạo hai beans cùng tên.

Javadoc của `setSupportedLocales` nhấn mạnh matching có yêu cầu tương thích cụ thể **language và country**. Ví dụ nếu chỉ hỗ trợ `en-US`, request `en-GB` hoặc `en` có thể không match và sẽ quay về default/first requested locale tùy cấu hình. Muốn hỗ trợ language-only, liệt kê `Locale.ENGLISH` trong supported set hoặc thiết kế normalization thích hợp.

**Không mặc định** controller sẽ lưu `Accept-Language` vào session. Đó là hai cơ chế độc lập.

## 7. Reactor Context: metadata per subscription, không phải WebSession

Reactor `Context` là cấu trúc **immutable** kiểu key/value liên kết với subscriber. `ContextView` cung cấp read-only view, còn `Context` hỗ trợ `put`, `delete` bằng cách tạo context mới.

Một ví dụ Reactor thuần:

~~~java
Mono<String> message =
        Mono.deferContextual(view ->
                Mono.just(view.getOrDefault("requestId", "missing")))
            .contextWrite(ctx ->
                ctx.put("requestId", "req-42"));
~~~

Khi có subscriber, `message` emit **`req-42`**. Điểm then chốt:

- `Mono.deferContextual` đọc Context **ở thời điểm subscription**, không nhất thiết ở lúc controller method được gọi.
- `contextWrite` không mutate một biến global; nó tạo một Context mới cho các upstream operators theo Reactor subscriber semantics.
- Context **không tự gửi cookie**, không tự persist qua request tiếp theo.
- Một Reactor Context key là object; có thể dùng `String` nhưng trong library lớn nên tránh collision, ví dụ dùng constant duy nhất hoặc class key.

### 7.1. Hướng truyền của contextWrite

Một nguyên tắc dễ nhầm: **Context truyền từ phía subscriber lên phía publisher** trong subscription, trong khi signals/data thường đi từ publisher xuống subscriber.

~~~text
Source publisher --- map --- flatMap --- contextWrite --- Subscriber
                 <------------------- Context -------
                 -------------------- onNext ------->
~~~

`contextWrite` **ở phía downstream** trong biểu thức chain thường làm context khả dụng cho `deferContextual`/operators **upstream**. Không phải mọi operator phía dưới nó đều nhìn thấy context được viết bởi nó.

Ví dụ đúng:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("correlationId", "missing")))
    .contextWrite(c -> c.put("correlationId", "abc123"));
~~~

Khi subscribe, `result` emit **`abc123`**.

### 7.2. Không coi ThreadLocal như Reactor Context

Ví dụ dễ lỗi:

~~~java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

Mono<String> result = Mono.just("start")
        .publishOn(Schedulers.parallel())
        .map(v -> REQUEST_ID.get());
~~~

Đây là **anti-pattern khái niệm**, không phải file độc lập. Nếu request ID được set trên thread nhận HTTP, `publishOn` có thể chuyển xử lý sang thread khác và `REQUEST_ID.get()` thành `null` (hoặc mang giá trị từ task khác nếu quản lý sai). Không dựa vào `InheritableThreadLocal` cho Reactor event loops/worker pools.

Thay bằng:

~~~java
Mono<String> result = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("correlationId", "missing")))
    .publishOn(Schedulers.parallel())
    .flatMap(id -> Mono.deferContextual(ctx ->
            Mono.just(id + "/" +
                    ctx.getOrDefault("correlationId", "missing"))))
    .contextWrite(c -> c.put("correlationId", "abc123"));
~~~

Kết quả subscriber nhận **`abc123/abc123`** vì Context đi theo reactive subscriber dù scheduling chuyển thread. Không tự suy luận mọi custom library sẽ truyền context nếu nó thoát khỏi Reactor chain vào callback/executor độc lập.

### 7.3. Không tạo side subscription vô chủ

Tránh:

~~~java
@GetMapping("/wrong")
public Mono<String> wrong() {
    service.call().subscribe(); // fire-and-forget
    return Mono.just("accepted");
}
~~~

Mẫu phản diện này có thể đánh mất cancellation, errors, trace context và không chứng minh tác vụ đã hoàn thành trước response. Tốt hơn **return composed Publisher**:

~~~java
@GetMapping("/right")
public Mono<String> right() {
    return service.call().thenReturn("done");
}
~~~

Đây là snippet có `service` bên ngoài, chưa chạy độc lập. Với background jobs thật, dùng queue/scheduler có ownership, retry, audit và idempotency rõ, không fire-and-forget tùy tiện từ HTTP handler.

## 8. Đưa Reactor Context vào pipeline từ WebFilter

Spring WebFlux `WebFilter` nhận `ServerWebExchange` và `WebFilterChain`:

~~~java
public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain) {

    String id = "req-42";
    return chain.filter(exchange)
            .contextWrite(ctx -> ctx.put("requestId", id));
}
~~~

Đây là method minh họa. Cách này đặt `requestId` vào Context **cho phần chain upstream khi được subscribe**, thường gồm downstream handler/service và nested reactive operators.

Tách biệt hai nơi chứa thông tin:

1. `exchange.getAttributes().put("requestId", id)` đặt metadata **ở HTTP exchange hiện tại**; tiện cho các filters/handler cùng nhìn thấy exchange, nhưng không tự đi theo mọi nested reactive requests.
2. `.contextWrite(ctx -> ctx.put("requestId", id))` đặt metadata **ở reactive subscriber context**; thuận tiện cho `Mono.deferContextual` và các operators/filters tham gia chuỗi.

Nếu dùng `WebClient`, một `ExchangeFilterFunction` cũng có thể đọc Reactor Context khi WebClient publisher được subscribe trong cùng pipeline:

~~~java
WebClient client = WebClient.builder()
        .filter((request, next) ->
                Mono.deferContextual(ctx -> {
                    String id = ctx.getOrDefault(
                            "requestId", "missing");

                    ClientRequest updated = ClientRequest
                            .from(request)
                            .header("X-Request-Id", id)
                            .build();

                    return next.exchange(updated);
                }))
        .build();
~~~

Đây là snippet minh họa cần imports `WebClient`, `ClientRequest`, `Mono` và một HTTP URI cho lời gọi thực. Chỉ truyền correlation ID đã validate tới hệ thống **tin cậy**; không tự đính kèm token/session ID vào mọi outbound request hoặc gọi URL không kiểm soát.

## 9. Reactive Security Context và WebSession

Spring Security có reactive APIs:
- `ReactiveSecurityContextHolder.getContext()`: đọc security context từ Reactor subscriber Context.
- `ReactiveSecurityContextHolder.withAuthentication(...)` hoặc `withSecurityContext(...)`: tạo context cần thiết theo hợp đồng security.
- `SecurityWebFilterChain`: filter chain cho WebFlux (khác `SecurityFilterChain` của servlet).
- `ServerSecurityContextRepository`: contract lưu và tải context khi ứng dụng có stateful authentication.
- `WebSessionServerSecurityContextRepository`: một implementation có thể lưu `SecurityContext` trong WebSession khi cấu hình thích hợp.
- `ReactorContextWebFilter`: dùng security context repository để đưa security context vào Reactor Context.

**Không đồng nhất ba điều:**
- `WebSession` tồn tại;
- người dùng đã authentication;
- Reactor `SecurityContext` hiện diện ở subscriber hiện tại.

Một WebSession có thể chứa chỉ tùy chọn giao diện mà không có authentication. Một API dùng bearer token/stateless resource server có thể **không cần server-side session** nhưng vẫn có Reactive SecurityContext cho mỗi request.

Đoạn code minh họa đọc username qua reactive security:

~~~java
public Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .defaultIfEmpty("anonymous");
}
~~~

Đây là **method minh họa**, cần Spring Security reactive dependency. Khi `Authentication` null hoặc unauthenticated, ứng dụng cần policy rõ ràng; không mặc nhiên dùng `getName()` như kiểm tra authorization. Hãy để Security chain/authorization rules bảo vệ endpoint, không chỉ dựa vào trường tên.

### Bảo mật session và chống fixation

- Khi đăng nhập bằng session, framework security phải thực hiện chính sách session fixation protection hợp lý.
- Dùng `WebSession.changeSessionId()` đúng theo lifecycle; không tự gửi ID qua query parameter.
- Đặt cookie `Secure`, `HttpOnly`, `SameSite` theo use case và deployment; HTTPS là cơ sở.
- Logout cần invalidate hoặc clear server authentication state theo chính sách. Không chỉ xóa localStorage trên frontend.
- Cần CSRF protection khi dùng browser cookie-based authentication và các thao tác thay đổi trạng thái.
- Không truyền `Authentication`, cookie hoặc token qua custom Reactor Context đến các service không đáng tin; Context không tự mã hóa dữ liệu.

## 10. Ứng dụng Spring Boot 3.x chạy được

Bài thực hành sử dụng:
- **WebSession** để ghi/đọc lựa chọn màu `favoriteColor` qua hai HTTP requests.
- **LocaleContext** từ `Accept-Language` để trả language tag `vi-VN`/ `en-US`.
- **Reactor Context** để truyền `X-Request-Id` qua `WebFilter`, `publishOn` và nested `flatMap`.
- `WebTestClient` để xác minh session cookie, các header, JSON và context propagation bằng **HTTP server thật trên random port**.

Dự án chỉ cần Java 17+, Spring Boot 3.x với `spring-boot-starter-webflux` và `spring-boot-starter-test`. Chưa thêm Spring Security/Micrometer vì mục tiêu của runnable demo là kiểm chứng ba khái niệm của đề bài **không phụ thuộc một hệ thống authentication hoặc tracing bên ngoài**.

### 10.1. Maven và cấu trúc dự án

Dùng Spring Initializr tạo project Java 17+, Maven, package `com.example.demo`. Trong `pom.xml` có dependencies:

~~~xml
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
~~~

Đây là **fragment** nằm trong project Maven đã được Spring Initializr tạo (có parent/BOM, Java version và build plugins), không phải toàn bộ `pom.xml` độc lập. Tránh thêm `spring-boot-starter-web` để giữ web application type là reactive.

Tạo:

~~~text
src/main/java/com/example/demo/
  DemoApplication.java
  RequestContextFilter.java
  ContextController.java
src/test/java/com/example/demo/
  ContextControllerTest.java
~~~

### 10.2. DemoApplication.java

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 10.3. RequestContextFilter.java

~~~java
package com.example.demo;

import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
public class RequestContextFilter implements WebFilter {

    public static final String REQUEST_ID_CONTEXT_KEY =
            RequestContextFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        String supplied = exchange.getRequest()
                .getHeaders().getFirst("X-Request-Id");

        String id = supplied != null &&
                supplied.matches("[A-Za-z0-9_-]{1,48}")
                ? supplied : UUID.randomUUID().toString();

        exchange.getAttributes().put("requestId", id);
        exchange.getResponse().getHeaders().set("X-Request-Id", id);

        return chain.filter(exchange)
                .contextWrite(context ->
                        context.put(REQUEST_ID_CONTEXT_KEY, id));
    }
}
~~~

**Giải thích:**

1. Filter sinh request ID hoặc nhận header từ client chỉ khi nó khớp allowlist 1–48 ký tự, tránh lưu CR/LF và dữ liệu tùy ý vào log/header.
2. Cùng `id` được đưa vào **exchange attributes**, **response header**, và **Reactor Context**. Mỗi nơi có vòng đời riêng.
3. Filter không tạo `WebSession`, không gọi database và không tự giữ request ID vào global static mutable field.
4. `contextWrite` nằm **sau** `chain.filter(exchange)` theo chuỗi, vì context hướng từ subscriber tới upstream.
5. Trong production, không dùng client-supplied ID làm một bằng chứng danh tính; correlation ID từ gateway tin cậy vẫn phải validate và không dùng như authorization token.
6. Import `HttpHeaders` trong file này là không bắt buộc (không sử dụng trực tiếp) nhưng không làm lỗi biên dịch; có thể loại bỏ nếu bật style checks cho unused imports.

### 10.4. ContextController.java

~~~java
package com.example.demo;

import java.util.Locale;

import org.springframework.context.i18n.LocaleContext;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/context")
public class ContextController {

    @GetMapping("/state")
    public Mono<StateView> state(
            WebSession session,
            ServerWebExchange exchange) {

        String language = localeTag(exchange);
        String color = session.getAttribute("favoriteColor");

        return Mono.deferContextual(context ->
                Mono.just(new StateView(
                        language,
                        color,
                        context.getOrDefault(
                                RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                "missing"),
                        session.isStarted())));
    }

    @PostMapping("/favorite/{color}")
    public Mono<StateView> favorite(
            @PathVariable("color") String color,
            ServerWebExchange exchange) {

        if (!color.matches("[a-z]{1,16}")) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid color"));
        }

        return exchange.getSession()
                .flatMap(session -> {
                    session.getAttributes().put("favoriteColor", color);

                    return Mono.deferContextual(context ->
                            Mono.just(new StateView(
                                    localeTag(exchange),
                                    color,
                                    context.getOrDefault(
                                      RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                      "missing"),
                                    session.isStarted())));
                });
    }

    @PostMapping("/invalidate")
    public Mono<Void> invalidate(WebSession session) {
        return session.invalidate();
    }

    @PostMapping("/rotate")
    public Mono<Void> rotate(WebSession session) {
        return session.changeSessionId();
    }

    @GetMapping("/hop")
    public Mono<HopView> hop() {
        return Mono.deferContextual(context ->
                        Mono.just(context.getOrDefault(
                                RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                "missing")))
                .publishOn(Schedulers.parallel())
                .flatMap(before -> Mono.deferContextual(context ->
                        Mono.just(new HopView(
                                before,
                                context.getOrDefault(
                                  RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                  "missing")))));
    }

    private static String localeTag(ServerWebExchange exchange) {
        LocaleContext context = exchange.getLocaleContext();
        Locale locale = context.getLocale();
        return locale == null ? "und" : locale.toLanguageTag();
    }

    public record StateView(
            String locale,
            String favoriteColor,
            String requestId,
            boolean sessionStarted) {}

    public record HopView(
            String beforeHop,
            String afterHop) {}
}
~~~

**Quan sát ba cơ chế hoạt động:**

- `state`: framework có thể inject `WebSession` vào handler, lấy `favoriteColor` nếu có. Gọi handler này **không tự start session** khi chỉ đọc attribute.
- `favorite`: `exchange.getSession()` trả `Mono<WebSession>`; thêm attribute `favoriteColor` khiến session bắt đầu, framework ghi session ID vào cookie khi lưu.
- `localeTag`: đọc locale theo `LocaleContextResolver`, trong default config chịu tác động `Accept-Language`; không đổi dữ liệu session.
- `Mono.deferContextual`: đọc request ID từ reactive subscriber Context; không dùng `ThreadLocal`.
- `hop`: có `publishOn(Schedulers.parallel())` để chuyển execution context qua scheduler; `beforeHop` và `afterHop` vẫn được lấy từ cùng Reactor Context. Không assert tên thread vì scheduler implementation/timing không phải business contract.
- `invalidate` và `rotate`: trả publisher gốc cho framework subscribe. Không gọi `.block()` trong event-loop thread.

**Cảnh báo thiết kế:** demo dùng `favoriteColor` chỉ là dữ liệu nhỏ, không nhạy cảm. Không nên cho client tự gửi một serialized object tùy ý vào session hoặc lưu tokens/passwords/raw request ở đây.

### 10.5. ContextControllerTest.java

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
        .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ContextControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readOnlyRequestDoesNotStartNewSession() {
        EntityExchangeResult<ContextController.StateView> result =
                client.get()
                        .uri("/api/context/state")
                        .header(HttpHeaders.ACCEPT_LANGUAGE, "vi-VN")
                        .header("X-Request-Id", "req-read")
                        .exchange()
                        .expectStatus().isOk()
                        .expectHeader().valueEquals(
                                "X-Request-Id", "req-read")
                        .expectBody(ContextController.StateView.class)
                        .returnResult();

        ContextController.StateView body = result.getResponseBody();
        assertNotNull(body);
        assertEquals("vi-VN", body.locale());
        assertEquals("req-read", body.requestId());
        assertFalse(body.sessionStarted());
    }

    @Test
    void webSessionPersistsAcrossRequestsWithCookie() {
        EntityExchangeResult<ContextController.StateView> created =
                client.post()
                        .uri("/api/context/favorite/blue")
                        .header("X-Request-Id", "req-save")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(ContextController.StateView.class)
                        .returnResult();

        ContextController.StateView saved = created.getResponseBody();
        assertNotNull(saved);
        assertTrue(saved.sessionStarted());
        assertEquals("blue", saved.favoriteColor());

        ResponseCookie cookie =
                created.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie);

        client.get()
                .uri("/api/context/state")
                .cookie("SESSION", cookie.getValue())
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en-US")
                .header("X-Request-Id", "req-read-again")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.locale").isEqualTo("en-US")
                .jsonPath("$.favoriteColor").isEqualTo("blue")
                .jsonPath("$.requestId").isEqualTo("req-read-again")
                .jsonPath("$.sessionStarted").isEqualTo(true);
    }

    @Test
    void reactorContextSurvivesSchedulerHop() {
        client.get()
                .uri("/api/context/hop")
                .header("X-Request-Id", "req-hop")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.beforeHop").isEqualTo("req-hop")
                .jsonPath("$.afterHop").isEqualTo("req-hop");
    }

    @Test
    void invalidColorIsRejected() {
        client.post()
                .uri("/api/context/favorite/RED123")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

**Vì sao test này hữu ích?**

- `@SpringBootTest(RANDOM_PORT)` và `@AutoConfigureWebTestClient` tạo HTTP integration test với embedded reactive server, không phải chỉ gọi Java method trực tiếp.
- Test đầu khẳng định **đọc session chưa started** và Locale từ request; nếu một security filter/library khác cố ý start session, điều kiện phải được thiết kế lại vì lúc đó chính sách đã thay đổi.
- Test thứ hai lấy cookie `SESSION` từ response **đầu**, chủ động gửi lại trong request **sau** và xác minh `favoriteColor` được duy trì.
- Test `hop` khẳng định Reactor Context vẫn sẵn có sau `publishOn` và `flatMap`; không dựa vào ThreadLocal hay tên thread.
- Test cuối minh họa validation ở controller, không liên quan đến session ID.
- Test không mặc định rằng một client HTTP tự động duy trì cookie jar; nó **lấy và gửi cookie tường minh** để kiểm tra request isolation.

Khi chạy trên production hoặc thêm Spring Security, bạn phải điều chỉnh tests phù hợp authentication/CSRF rules. Ví dụ không thêm Security dependency nên `POST` đơn giản hoạt động.

### 10.6. Chạy và kiểm tra bằng curl

Chạy:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows dùng `mvnw.cmd spring-boot:run`; nếu không có wrapper và Maven đã cài, dùng `mvn spring-boot:run`.

Đọc trạng thái request không có cookie:

~~~bash
curl -i   -H "Accept-Language: vi-VN"   -H "X-Request-Id: req-001"   http://localhost:8080/api/context/state
~~~

Body kỳ vọng có các fields tương ứng:

~~~json
{
  "locale": "vi-VN",
  "favoriteColor": null,
  "requestId": "req-001",
  "sessionStarted": false
}
~~~

Giá trị `favoriteColor: null` có thể bị Jackson omission nếu dự án đã cấu hình bỏ null properties. Quan trọng là trạng thái không có color, và WebSession chưa được start. Không dựa vào thứ tự JSON keys.

Lưu cookie khi chọn màu:

~~~bash
curl -i -c cookies.txt   -X POST   -H "X-Request-Id: req-save"   http://localhost:8080/api/context/favorite/blue
~~~

Browser/client thường nhận `Set-Cookie: SESSION=...` khi session được start/lưu. Lệnh `-c cookies.txt` cho curl ghi cookie vào jar file.

Đọc lại session:

~~~bash
curl -i -b cookies.txt   -H "Accept-Language: en-US"   -H "X-Request-Id: req-next"   http://localhost:8080/api/context/state
~~~

Kỳ vọng favoriteColor vẫn **blue**, locale **en-US**, requestId **req-next**. Đó là minh họa rõ ràng cho ba scopes độc lập: session giữ state qua HTTP requests, locale đổi theo header từng request, Reactor Context được tạo lại cho mỗi subscription.

Thử scheduler hop:

~~~bash
curl -i   -H "X-Request-Id: rid-hop"   http://localhost:8080/api/context/hop
~~~

JSON kỳ vọng:

~~~json
{"beforeHop":"rid-hop","afterHop":"rid-hop"}
~~~

**Không gửi session ID đến log công khai hoặc sao chép cookie file chứa ID lên hệ thống khác.** Curl cookie jar nên chỉ dùng cho thử nghiệm local và có thể chứa thông tin nhạy cảm.

## 11. Cách dùng Context qua nested WebClient calls

Reactor Context có ích khi một `WebFilter` nhận correlation metadata, sau đó `WebClient` gửi request đến microservice khác. Spring WebFlux hỗ trợ đọc Context trong `ExchangeFilterFunction` thông qua `Mono.deferContextual`.

Một service minh họa:

~~~java
@Service
public class PartnerClient {
    private final WebClient client;

    public PartnerClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://partner.example.com")
                .filter((request, next) ->
                        Mono.deferContextual(context -> {
                            String rid = context.getOrDefault(
                                RequestContextFilter.REQUEST_ID_CONTEXT_KEY,
                                "missing");
                            ClientRequest withId = ClientRequest
                                    .from(request)
                                    .header("X-Request-Id", rid)
                                    .build();
                            return next.exchange(withId);
                        }))
                .build();
    }

    public Mono<String> getInfo(long id) {
        return client.get()
                .uri("/data/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

**Đây là class minh họa bổ sung**, không chạy độc lập cùng ví dụ mục 10 vì `partner.example.com` chỉ là sample domain; cần service thật và dependencies phù hợp. Imports gồm `@Service`, `WebClient`, `ClientRequest`, `Mono`. Trong code thật, xác minh upstream trust boundary, timeout, retry, TLS và không truyền dữ liệu nhạy cảm vào header ngoài ý định.

Một lưu ý quan trọng: context propagation qua Reactor chain hoạt động khi **WebClient Publisher được subscribe như một phần chain có Context phù hợp**. Nếu service tách ra tạo `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, hoặc `subscribe()` riêng, việc truyền context không được bảo đảm tự động. Khi buộc đổi concurrency model, chụp metadata bất biến hoặc dùng Micrometer Context Propagation đúng cách.

## 12. Reactor Context, MDC và Micrometer: observability

Nhiều hệ thống dùng SLF4J MDC:

~~~java
MDC.put("requestId", "rid-1");
~~~

Nhưng MDC phần lớn dựa trên **ThreadLocal**. Trong WebFlux, signals của một request có thể đi qua các threads khác nhau. Đặt MDC một lần trong filter rồi cho rằng mọi callback đọc được nó là **không an toàn**.

Cách tiếp cận:
1. Giữ correlation metadata trong **Reactor Context** hoặc tracing/observation context mà instrumentation hỗ trợ.
2. Dùng **Micrometer Context Propagation** và các registered `ThreadLocalAccessor` khi cần bridge tới MDC/ThreadLocal-based APIs.
3. Chọn rõ cơ chế automatic vs explicit context propagation phù hợp Reactor/Spring version; không vô tình bật nhiều global hooks không kiểm soát.
4. Khi dùng custom `TaskDecorator`, cần capture/restore trong `finally` và không giả định điều đó tự propagate mọi reactor subscriber Context.
5. Không đặt bearer token, raw session ID, password hoặc PII vào tracing baggage/logs.
6. Kiểm tra trace ID xuyên `publishOn`, `flatMap`, WebClient, retry và error/cancellation.

Ví dụ an toàn hơn để truy cập ID trong business pipeline là `Mono.deferContextual(ctx -> ...)` thay vì `MDC.get(...)`. Nếu đã có Spring Boot Actuator, Micrometer tracing và security integration, ưu tiên cấu hình theo tài liệu cùng phiên bản trước khi viết thủ công một cơ chế context global mới.

## 13. Quan hệ với Spring Session reactive và scaling

In-memory session store phù hợp demo hoặc ứng dụng đơn instance. Trong deployment nhiều replicas:

~~~text
Browser
   |
Load balancer
   +---- Pod A: local WebSessionStore
   +---- Pod B: local WebSessionStore
   +---- Pod C: local WebSessionStore
~~~

Nếu browser gửi một ID phiên được lưu ở Pod A nhưng lần sau tới Pod B, Pod B có thể không tìm thấy session tương ứng. Giải pháp có thể là:
- Sticky session theo thiết kế hạ tầng (có giới hạn, failover khó hơn).
- **Spring Session** với Redis/compatible reactive session repository để chia sẻ storage theo ứng dụng.
- Stateless auth hoặc lưu preference vào database profile và tránh HTTP session khi không cần.

Với Spring Session reactive:
- Bảo đảm dependency/repository hỗ trợ WebFlux, reactive connection factory, serialization và expiration.
- Không lưu object graph không serializable hoặc dữ liệu mutable mà nhiều requests sửa đồng thời mà không có conflict control.
- Đo latency/availability của Redis/session store — session lookup trở thành I/O trên mỗi request cần đọc.
- Áp dụng TTL và security cho Redis credentials, network, backups và key namespace.
- Nếu Spring Security lưu SecurityContext trong WebSession, kiểm tra hành vi của security context repository, session fixation và logout.

**Không suy ra WebSession mặc định là một Redis database session.** Nó chỉ là interface; cơ chế lưu phụ thuộc cấu hình.

## 14. Locale được lựa chọn theo user profile hay WebSession?

Giả sử ứng dụng đa ngôn ngữ cho phép user chọn tiếng Việt ngay trong web UI. Có nhiều nguồn locale:

1. `Accept-Language` của browser — gợi ý do client tự gửi cho mỗi request.
2. Language preference trong **user profile** (bền vững qua thiết bị và đăng nhập).
3. Language preference trong **WebSession** (chỉ liên quan session hiện hành).
4. URL locale segment như `/vi/.../` hoặc query param `lang=vi`.
5. Default locale của product.

Bạn cần thiết kế thứ tự ưu tiên, ví dụ:

~~~text
Authenticated user profile
   > explicit validated language selection in current session
   > Accept-Language compatible supported locale
   > product default
~~~

Đây chỉ là **policy minh họa**: ứng dụng có thể dùng URL locale ưu tiên hơn session để phục vụ SEO/bookmark, tùy thiết kế.

Khi xử lý user lựa chọn language:
- Chỉ nhận locale trong allowlist `vi-VN`, `en-US`, v.v.
- Nếu ghi vào session, hãy áp dụng rõ trong locale resolution pipeline cho request sau. Chỉ `put("language", "vi")` **không khiến** `AcceptHeaderLocaleContextResolver` tự đọc session đó.
- Đừng suy đoán timezone từ locale; lưu timezone user riêng, ví dụ IANA ZoneId.
- Đối với response được cache, `Content-Language`, `Vary: Accept-Language` và user-specific caching phải nhất quán.
- Khi localization ảnh hưởng API error messages, hãy tránh để cùng một shared cache key dùng cho hai biến thể ngôn ngữ.

## 15. Khi nào dùng session, exchange attributes hay Reactor Context?

| Tình huống | Giải pháp ưu tiên | Lý do |
| --- | --- | --- |
| User chọn giao diện dark mode dùng qua nhiều requests | WebSession hoặc profile DB | Cần trạng thái có vòng đời dài hơn request |
| Correlation ID của HTTP request hiện tại | Reactor Context + HTTP response header | Propagate qua reactive pipeline, request-scoped |
| Một filter cần gắn flag cho handler trong cùng exchange | `exchange.getAttributes()` | Dùng chung object exchange hiện tại |
| Định dạng ngày/giờ theo locale hiện hành | `LocaleContext` + timezone policy | Locale cho request, timezone xử lý riêng |
| Lưu cart/tồn kho cần concurrency transaction | DB, không chỉ session attribute | Consistency/locking |
| Authentication principal trong reactive code | `ReactiveSecurityContextHolder` | Security model nhất quán |
| Client OAuth bearer token | Security filter/authentication, thường stateless | Không buộc phải khởi tạo WebSession |
| Truyền request ID qua WebClient nested call | Reactor Context + WebClient filter | Subscriber metadata đi theo chain |
| Java thread khác không tham gia Reactor chain | Explicit immutable snapshot/propagation bridge | Reactor Context không tự teleport qua thread tùy ý |
| Locale cố định toàn hệ thống | Fixed/accept-header locale resolver config | Không cần lưu locale vào session |
| Ghi log trong thư viện chỉ biết MDC | Micrometer context propagation/bridge | MDC thread-local không tự được đảm bảo |
| Gửi session ID tới upstream service | **Thông thường không nên** | Rò credential/trust boundary |

Đừng tạo stateful session chỉ để truyền một request ID, cũng đừng đặt giỏ hàng vào Reactor Context và nghĩ request sau vẫn có giá trị đó.

## 16. Các lỗi thường gặp và chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `getSession()` được gọi nhưng không có cookie SESSION | Session chỉ được đọc, chưa start | Kiểm tra `isStarted()`, write attribute/start |
| Chọn màu rồi GET tiếp không nhớ | Client không gửi cookie, session expired hoặc node khác | Network Cookie/Set-Cookie, store, load balancer |
| Session ID có nhưng state sai | Concurrent writes, reset store, mutable attributes | Kiểm tra store và race/lifecycle |
| Logout chỉ gọi `invalidate()` mà vẫn giữ session | Bỏ qua publisher, không return/subscribe | Return `session.invalidate()` trong chain |
| `getLocaleContext()` luôn giống request header | Default AcceptHeader resolver | Muốn đổi preference cần resolver riêng |
| `setLocaleContext` ném UnsupportedOperationException | AcceptHeader resolver không cho thay header client | Custom policy hoặc profile/session storage |
| Locale vi-VN nhưng timezone sai | Locale không tự xác định timezone | Dùng ZoneId riêng, TimeZoneAware context nếu có |
| `MDC.get("rid")` mất sau publishOn | Thread-local không theo scheduler hop | Reactor Context hoặc propagation bridge |
| `contextWrite` không đến vị trí mong đợi | Đặt sai phía subscribe hoặc tạo chain khác | Quan sát `deferContextual` và operator order |
| Request được trả response nhưng background task lỗi im lặng | `subscribe()` riêng trong handler | Return/composition Publisher, central job queue nếu cần |
| Spring Security `SecurityContextHolder` null | Nhầm servlet thread-local với reactive security model | ReactiveSecurityContextHolder / SecurityWebFilterChain |
| WebSession cookie hoạt động ở local nhưng mất khi scale | In-memory store không chia sẻ giữa pods | Spring Session reactive Redis hoặc sticky sessions |
| HTTP response đã commit, session changes không persist | Ghi session quá muộn sau response | Sắp xếp async lifecycle và session save đúng |
| SameSite/CORS khiến cookie không gửi | Cross-site policy/credentials mismatch | DevTools, cookie flags, allow-origin/credentials |
| Một session chứa nhiều bí mật | Lưu credentials/PII không cần thiết | Giảm dữ liệu session, mã hóa storage, access policy |
| Bật Secure cookie trên HTTP test làm cookie không gửi | Browser chặn Secure qua HTTP thường | Test HTTPS hoặc dùng cookie policy theo môi trường |
| Request ID từ header có CRLF | Không validate input | Regex allowlist, generate ID server-side |
| Endpoint có Mono nhưng JDBC blocking | Blocking library không biến mất | Dùng reactive driver hoặc bounded scheduler phù hợp |

### Debug có hệ thống

1. Bắt đúng request và response headers bằng DevTools/curl: `Cookie`, `Set-Cookie`, `Accept-Language`, `X-Request-Id`.
2. Xác định session đã **started** chưa, ID có được browser gửi lại không, session store đang chạy ở node nào và TTL.
3. Kiểm tra `WebSession` attributes thực tế, loại dữ liệu lưu, concurrent requests và phiên bản saved.
4. Đọc loại `LocaleContextResolver` đang đăng ký, cách match supported locales, timezone strategy và default locale.
5. Chụp Reactor pipeline trước và sau `publishOn`/`flatMap`, đọc qua `Mono.deferContextual`; đừng suy luận từ MDC.
6. Nếu thêm Spring Security, kiểm tra `SecurityWebFilterChain` và repository mà reactive auth đang dùng, không tự gán state.
7. Test quyền/CSRF/CORS trên browser, session cookie rotation/logout và session timeout ngoài test demo.
8. Khi scale, giám sát Redis/store, eviction, serialized session size, cookie count, p95 latency, failure modes.

## 17. Bảo mật và hiệu năng: review checklist

### Bảo mật

- Session cookie có Secure trên HTTPS, HttpOnly/SameSite theo ứng dụng và auth flow.
- Session ID là credential nhạy cảm: không log, không đưa trong URL, không đưa qua Reactor Context sang bên thứ ba.
- Session fixation protection và logout/invalidate do security policy điều phối.
- CSRF protection với cookie-based session auth và unsafe methods.
- WebSession storage có TTL, quota, network access controls; tránh ghi credentials/passwords hoặc object graphs nặng.
- CORS chỉ cho origin được phép, đặc biệt khi `credentials: include`.
- Correlation ID input được validate, không dùng như user identity hoặc ACL.
- Không tiết lộ security context trong JSON/log; lựa chọn principal phải được authorize riêng.
- Dữ liệu user preferences được validate (ngôn ngữ, timezone, theme, v.v.).
- Với đa tenant, session và caches luôn gắn đúng tenant/user, không trộn session state vào static singleton mutable fields.

### Hiệu năng

- Không khởi tạo session trên mọi anonymous GET nếu không có nhu cầu.
- Không lưu list/cart lớn vào WebSession gây tăng memory/Redis traffic.
- Với Redis-backed Spring Session, đo lookup/save latency và serialization cost; session store cũng có thể là bottleneck.
- Không dùng ThreadLocal để truyền request state xuyên Reactor scheduler shifts.
- Giới hạn `WebClient` connections, Reactor scheduler/buffers và API concurrency; context propagation không thay quota.
- Nếu cần cross-request preference thường xuyên, cân nhắc profile DB/cache có thiết kế invalidation rõ.
- Thiết kế session idle timeout và cookie max age nhất quán.
- Tách correlation ID request-scoped khỏi profile state, tránh lưu trace baggage quá nhiều.
- Test thật trong môi trường nhiều nodes/proxy, không chỉ một embedded server local.

## 18. Câu hỏi ôn tập

**1. `ServerWebExchange.getSession()` có luôn tạo cookie không?**

Không. Nó trả WebSession object hiện hữu hoặc mới; session mới chỉ start khi thêm attributes hoặc gọi `start()`, rồi được lưu theo lifecycle.

**2. Tại sao `session.invalidate(); return Mono.empty();` sai?**

Vì `invalidate()` trả reactive Publisher; nếu không compose/return thì không bảo đảm nó được subscribe/thực thi. Hãy return Publisher từ handler.

**3. `WebSession` có phải `HttpSession` của Servlet không?**

Không. WebSession là reactive session contract của Spring WebFlux, có resolver/store riêng. Đừng tự chuyển cast sang Servlet HttpSession.

**4. Locale vi-VN có tự suy ra múi giờ Asia/Ho_Chi_Minh không?**

Không. Locale và timezone độc lập; resolver mặc định đọc Accept-Language không tự cung cấp timezone.

**5. Nếu user chọn `en-US` lưu trong WebSession, resolver mặc định có tự dùng nó không?**

Không. `AcceptHeaderLocaleContextResolver` dựa vào header và cấu hình supported/default locales. Cần logic/custom resolver để áp dụng session preference.

**6. Reactor Context có sống qua HTTP requests không?**

Không tự động. Nó gắn với reactive subscription. Muốn giữ preference qua request mới, dùng session/profile DB/cookie.

**7. Vì sao `ThreadLocal`/MDC bị mất sau `publishOn`?**

Signals có thể chạy trên thread khác; ThreadLocal gắn với JVM thread chứ không theo subscriber. Dùng Reactor Context và propagation bridge khi cần.

**8. `contextWrite` truyền context theo hướng nào?**

Trong subscription, Context truyền từ phía subscriber (downstream) tới các upstream operators; dữ liệu `onNext` thường truyền chiều ngược lại.

**9. API bearer-token stateless có nhất thiết phải tạo WebSession để có security context không?**

Không. Spring Security reactive có thể đặt SecurityContext theo mỗi request/subscription mà không tạo session server-side.

**10. Dùng in-memory session store trên ba pods có rủi ro gì?**

Một cookie ID của Pod A có thể không tìm được state ở Pod B. Cần shared reactive session store hoặc infrastructure routing phù hợp.

**11. Trong demo test, yêu cầu đầu locale `vi-VN`, yêu cầu sau locale `en-US` nhưng vẫn giữ blue có ý nghĩa gì?**

`WebSession` giữ favoriteColor qua requests nhờ cookie, Locale thay theo từng request, và Reactor Context request ID cũng được tạo riêng cho mỗi subscription.

**12. Có thể dùng Reactor Context làm một nơi lưu giỏ hàng session không?**

Không phù hợp. Nó không persist xuyên requests; lưu giỏ hàng vào DB hoặc state store/session theo yêu cầu consistency.

## 19. Checklist áp dụng thực tế

1. Xác định **scope** trước: multi-request user state → WebSession/profile; single exchange metadata → exchange attributes; reactive subscription metadata → Reactor Context; locale request → LocaleContextResolver.
2. Khi chỉ đọc session, không `start()` nếu không có nhu cầu; khi ghi hoặc logout, compose các reactive operations đúng lifecycle.
3. Với session ID, dùng TLS, cookie flags, CSRF, rotation, invalidation và auth policies.
4. Giới hạn session attribute kích thước; tránh mutable state, secrets và object graph khó serialize.
5. Thiết kế shared session repository khi scale nhiều instances; test cookie, TTL, failover và concurrency.
6. Dùng `exchange.getLocaleContext()` trong reactive handlers; không suy timezone từ locale.
7. Xác định precedence cho ngôn ngữ từ URL/profile/session/Accept-Language và custom resolver khi cần.
8. Dùng `Mono.deferContextual`/`contextWrite` để truyền correlation/tracing metadata qua Reactor chain; không dựa vào ThreadLocal của request.
9. Không tự `subscribe()` trong controller cho nghiệp vụ cần report kết quả; return composed Publisher.
10. Tích hợp `ReactiveSecurityContextHolder` trong WebFlux security, phân biệt với Session và Servlet SecurityContextHolder.
11. Test `WebTestClient` trên HTTP socket thật: session cookie trước/sau, locale headers, context scheduler hop, logout và lỗi dữ liệu.
12. Đánh giá CORS, CSRF, session store/Redis, latency, memory, context propagation và tracing dưới tải production phù hợp.

## Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — WebFlux reactive core, WebSessionManager và LocaleContextResolver](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html)
- [Spring Framework 6.2 — WebSession Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework 6.2 — ServerWebExchange Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html)
- [Spring Framework 6.2 — LocaleContextResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/i18n/LocaleContextResolver.html)
- [Spring Framework 6.2 — AcceptHeaderLocaleContextResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/server/i18n/AcceptHeaderLocaleContextResolver.html)
- [Spring Framework 6.2 — WebClient Reactor Context](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-context.html)
- [Spring Framework 6.2 — WebFlux @SessionAttributes](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/sessionattributes.html)
- [Spring Boot 3.5 — Common Application Properties (reactive session)](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Security 6.x — Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/index.html)
- [Project Reactor — Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [Spring Session — WebFlux custom cookies](https://docs.spring.io/spring-session/reference/guides/boot-webflux-custom-cookie.html)
