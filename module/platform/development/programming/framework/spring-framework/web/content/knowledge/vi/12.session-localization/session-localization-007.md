# RequestContextHolder, LocaleContextHolder và giới hạn ThreadLocal trong Spring MVC

## 1. Mục tiêu và bối cảnh

Trong một HTTP request, nhiều thành phần cần truy cập **ngữ cảnh hiện tại**: request attributes, thông tin locale, múi giờ, ngôn ngữ dùng dịch thông điệp hoặc mã correlation ID. Spring MVC giúp gắn một phần ngữ cảnh này với **luồng Java đang xử lý request**. Hai API thường gặp là:

- `org.springframework.web.context.request.RequestContextHolder`: lấy `RequestAttributes` của request đang gắn với luồng hiện tại.
- `org.springframework.context.i18n.LocaleContextHolder`: lấy `LocaleContext`, `Locale` và đôi khi `TimeZone` đang gắn với luồng hiện tại.

Các holder rất tiện, nhưng **không phải kho lưu trạng thái toàn cục, không phải session, không phải API truyền context qua mọi executor**, và không thay thế dependency rõ ràng trong business logic.

Sau bài này bạn sẽ:

1. Phân biệt request attributes, servlet request, locale, timezone và HTTP session.
2. Sử dụng `getRequestAttributes()`, `currentRequestAttributes()`, `ServletRequestAttributes`, `LocaleContextHolder.getLocale()` đúng chỗ.
3. Hiểu `DispatcherServlet`, `RequestContextFilter` và `RequestContextListener` gắn/thu hồi context thế nào.
4. Phân biệt `ThreadLocal`, `InheritableThreadLocal`, `@Async`, `CompletableFuture`, servlet async `Callable` và request đã kết thúc.
5. Biết khi nào nên **truyền dữ liệu cần thiết một cách tường minh** thay vì cố sao chép `HttpServletRequest`/`RequestAttributes` vào worker thread.
6. Đọc ngôn ngữ từ `Accept-Language`, hiểu `LocaleResolver` và `MessageSource`, không nhầm locale với timezone.
7. Thực hành mã **Java 17+, Spring MVC/Spring Boot 3.x**, `curl` và MockMvc; chẩn đoán lỗi thiếu context và ngăn rò rỉ giữa request.

Bài tập trung **Spring MVC trên Servlet stack**, Spring Framework 6.x. Spring WebFlux dùng Reactor Context, không nên dùng hai ThreadLocal holder này làm nền tảng để truyền context trong reactive pipeline. Một số API thay đổi giữa Spring Boot 3 và 4; kiểm tra tài liệu đúng phiên bản đang chạy.

## 2. Bức tranh HTTP request và context gắn với luồng

```text
Browser/API client
      |
      | GET /context/info
      | Accept-Language: vi-VN
      v
Servlet container
      |
      v
Servlet Filter chain
      |
      v
DispatcherServlet
      |  - gắn RequestAttributes vào RequestContextHolder
      |  - gắn LocaleContext vào LocaleContextHolder
      |  - tìm controller
      v
Controller / Service (trong luồng request đang được gắn)
      |  - RequestContextHolder.getRequestAttributes()
      |  - LocaleContextHolder.getLocale()
      v
MessageSource / response DTO / view
      |
      v
DispatcherServlet hoàn tất dispatch
      |  - khôi phục/thu hồi thread-bound context
      v
Filter chain -> container -> client
```

Đây là mô hình **luồng đồng bộ thông thường**. Khi có servlet async, forward/error dispatch, executor hoặc filter tùy chỉnh, vòng đời gắn/thu hồi context có thể khác. `DispatcherServlet` và các thành phần khung quản lý request context theo vòng đời request/dispatch chứ không cho phép lưu tùy ý qua request khác.

Một ứng dụng Servlet thường dùng **thread pool**: luồng từng xử lý request A có thể xử lý request B sau này. Vì thế framework phải khôi phục/clear thread-bound state đúng lúc. Nếu tự gắn `ThreadLocal` mà quên `remove()` hoặc `finally`, request B có thể quan sát thông tin cũ của request A — đây vừa là bug vừa có thể là sự cố rò rỉ dữ liệu.

## 3. RequestContextHolder là gì?

`RequestContextHolder` là holder tĩnh của Spring Web, lưu một instance `RequestAttributes` theo thread. `RequestAttributes` là abstraction có scope/attribute operations; với servlet web request, implementation phổ biến là `ServletRequestAttributes`.

Phương thức quan trọng:

| API | Hành vi |
| --- | --- |
| `RequestContextHolder.getRequestAttributes()` | Trả `RequestAttributes` đang bind hoặc **null** khi không có |
| `RequestContextHolder.currentRequestAttributes()` | Trả context đang bind; nếu không có có thể fallback JSF context (nếu có), sau đó ném `IllegalStateException` khi thật sự không tìm được |
| `RequestContextHolder.setRequestAttributes(attrs)` | Gắn context vào **thread hiện tại**, không truyền kế thừa sang thread con |
| `setRequestAttributes(attrs, true)` | Gắn theo `InheritableThreadLocal`; có rủi ro lớn với thread pool |
| `resetRequestAttributes()` | Xóa request attributes ở thread hiện tại |

Spring lưu hai holder nội bộ: một `ThreadLocal` thông thường và một `InheritableThreadLocal` cho tùy chọn kế thừa. Gọi `setRequestAttributes(attrs, false)` dùng binding không kế thừa, và xóa binding chế độ còn lại trong thread đó.

### 3.1. Khi dùng trong controller

```java
@GetMapping("/info")
public String info() {
    RequestAttributes attrs =
            RequestContextHolder.currentRequestAttributes();
    return attrs.getClass().getSimpleName();
}
```

Đây là **method minh họa** cần đặt trong `@RestController` cùng các imports. Trong Spring MVC Servlet request thông thường, `attrs` thường là `ServletRequestAttributes`. Tuy nhiên, **đừng cast vô điều kiện trong mã thư viện dùng chung**: trong test, JSF hoặc hạ tầng khác, implementation có thể không phải Servlet.

### 3.2. Truy cập HttpServletRequest khi thực sự cần

```java
RequestAttributes attrs = RequestContextHolder.getRequestAttributes();

if (attrs instanceof ServletRequestAttributes servletAttrs) {
    HttpServletRequest request = servletAttrs.getRequest();
    String uri = request.getRequestURI();
}
```

Đây là đoạn minh họa **bên trong một method** với imports `jakarta.servlet.http.HttpServletRequest`, `RequestAttributes`, `RequestContextHolder` và `ServletRequestAttributes`; không phải tệp Java độc lập.

Nếu code thực sự cần request trong controller, cách dễ test và minh bạch hơn thường là **khai báo method parameter**:

```java
@GetMapping("/path")
public String path(HttpServletRequest request) {
    return request.getRequestURI();
}
```

Spring MVC có thể inject `HttpServletRequest` vào argument. Không cần đi vòng qua một static holder khi dependency có thể được truyền trực tiếp. Tương tự, service chỉ cần request ID hoặc user ID nên nhận **giá trị đó** qua tham số, không nhận toàn bộ servlet request.

### 3.3. RequestAttributes không phải session

`RequestAttributes.SCOPE_REQUEST` biểu diễn thuộc tính của request; `SCOPE_SESSION` liên quan phiên HTTP nếu có. Đừng nhầm một thread-bound holder với dữ liệu session sống lâu hơn request.

```java
attrs.setAttribute(
    "requestId", "R-123", RequestAttributes.SCOPE_REQUEST);
Object id = attrs.getAttribute(
    "requestId", RequestAttributes.SCOPE_REQUEST);
```

Hai dòng này là minh họa hoạt động trong request. Giá trị request-scope thường tồn tại theo **vòng đời request**, không thể an toàn giữ để dùng trong job chạy sau response. Thuộc tính session có vòng đời và quy tắc đồng thời riêng; việc dùng holder không tự tạo session id hay thay thế cơ chế session management.

### 3.4. currentRequestAttributes và getRequestAttributes khác nhau

Nếu helper có thể gọi trong cả request và unit test/scheduled job, ưu tiên:

```java
RequestAttributes attributes =
        RequestContextHolder.getRequestAttributes();

if (attributes == null) {
    // Không có request context. Chọn hành vi fallback có chủ đích.
}
```

`currentRequestAttributes()` phù hợp khi **request context là điều kiện bắt buộc**, và bạn muốn fail fast nếu đang ở sai lifecycle. Nó thường ném `IllegalStateException` với thông tin rằng không có thread-bound request. Bắt `IllegalStateException` rồi giả vờ có request rỗng sẽ che bug kiến trúc.

Không viết `RequestContextHolder.currentRequestAttributes()` trong constructor của singleton bean khởi tạo lúc startup; tại thời điểm đó không có một HTTP request đang xử lý.

## 4. Ai gắn request context: DispatcherServlet, Filter hay Listener?

Trong Spring MVC, `DispatcherServlet`/`FrameworkServlet` đã tự expose request attributes trong quá trình xử lý; **không phải cứ muốn dùng RequestContextHolder là phải đăng ký thêm filter**.

Ba lựa chọn thường gặp:

| Thành phần | Khi nào hữu ích | Ghi chú |
| --- | --- | --- |
| `DispatcherServlet` | Controller/handler được Spring MVC dispatch | Bình thường đã expose context |
| `RequestContextFilter` | Cần context ở các tầng **ngoài DispatcherServlet**, chẳng hạn filter hoặc servlet khác | Cần cấu hình mapping/order/dispatcher types phù hợp |
| `RequestContextListener` | Servlet listener để gắn request thread context ngoài DispatcherServlet | Chỉ dùng khi môi trường cần; xem lifecycle |

Nếu một filter chạy **trước** `DispatcherServlet` và gọi `RequestContextHolder.getRequestAttributes()`, bạn không được mặc định đã có context do DispatcherServlet cung cấp: nó chưa chạy. Nếu đặt `RequestContextFilter` và đăng ký đúng thứ tự, request/locale context có thể được expose ở filter path đó. Nhưng không thêm nhiều cơ chế chỉ vì “cho chắc”: cần xác định thành phần nào thực sự cung cấp context cho đoạn code cần nó.

`RequestContextFilter` có tùy chọn `setThreadContextInheritable(boolean)`, **mặc định false** để tránh rủi ro thread pool. Trong Spring 6.x, filter còn xét async và error dispatch để thiết lập context trên các dispatch tương ứng; behavior còn tùy servlet filter registration.

## 5. LocaleContextHolder: ngôn ngữ và múi giờ theo luồng

`LocaleContextHolder` lưu một `LocaleContext` gắn với thread, có thể gồm `Locale` và, khi context hỗ trợ, `TimeZone`. `DispatcherServlet` tự expose locale đã được MVC resolve.

Các API chính:

| API | Hành vi |
| --- | --- |
| `LocaleContextHolder.getLocaleContext()` | Trả context đang bind hoặc **null** |
| `LocaleContextHolder.getLocale()` | Trả locale của context; nếu không có, fallback tới Spring default/JVM default |
| `LocaleContextHolder.getTimeZone()` | Trả timezone của context; nếu không có, fallback tới Spring default/JVM default |
| `LocaleContextHolder.setLocale(locale)` | Gắn locale vào thread hiện tại, không kế thừa theo mặc định |
| `LocaleContextHolder.setLocaleContext(ctx)` | Gắn context, có thể có timezone; không kế thừa theo mặc định |
| `LocaleContextHolder.resetLocaleContext()` | Xóa context ở thread hiện tại |
| `setLocale(locale, true)` / `setLocaleContext(ctx, true)` | Cho phép kế thừa qua `InheritableThreadLocal` |
| `setDefaultLocale(...)` / `setDefaultTimeZone(...)` | Đặt **default dùng chung** của holder; không phải locale riêng của một user |

### 5.1. getLocale() không null chứng tỏ có request?

**Không.** Ngay cả khi không bind bất kỳ locale context nào, `getLocale()` vẫn thường trả default locale của Spring/JVM; tương tự `getTimeZone()` có default timezone. Muốn biết có context gắn với thread không, dùng `getLocaleContext() != null`.

```java
Locale locale = LocaleContextHolder.getLocale();
LocaleContext ctx = LocaleContextHolder.getLocaleContext();

boolean explicitlyBound = (ctx != null);
```

Đoạn này có imports `java.util.Locale` và `org.springframework.context.i18n.LocaleContext`. `explicitlyBound` cho biết có thread-bound LocaleContext, **không** bảo đảm có HTTP request hoặc có header Accept-Language; context có thể do test hay ứng dụng tự set.

### 5.2. Locale khác timezone

`Locale.forLanguageTag("vi-VN")` mô tả ngôn ngữ/region, không có nghĩa timezone là `Asia/Ho_Chi_Minh`. `Accept-Language: vi-VN` không truyền một timezone hợp lệ. Dùng IANA zone như `Asia/Ho_Chi_Minh` qua profile/user preference hoặc cơ chế riêng và truyền `ZoneId` tường minh trong business logic khi cần quy đổi thời điểm.

Ví dụ:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

String language = locale.toLanguageTag(); // "vi-VN"
String zoneText = zone.getId();            // "Asia/Ho_Chi_Minh"
```

`LocaleContextHolder.getTimeZone()` fallback tới default nếu context không cung cấp timezone; không nên dùng để suy ra vị trí vật lý của user, tài khoản hay request.

## 6. Accept-Language, LocaleResolver và MessageSource

Browser có thể gửi:

```http
GET /context/info HTTP/1.1
Accept-Language: vi-VN, en;q=0.8
```

Một cấu hình Spring MVC phổ biến dùng `AcceptHeaderLocaleResolver` để resolve locale từ header và các supported locales/default nếu cấu hình. `DispatcherServlet` đặt locale đã resolve vào `LocaleContextHolder` trong request. Hành vi chính xác phụ thuộc resolver và options.

**Phân biệt:**

- `Accept-Language` = ưu tiên ngôn ngữ của client.
- `LocaleResolver` / `LocaleContextResolver` = chính sách chọn locale của ứng dụng trên request.
- `LocaleContextHolder` = nơi **đọc context hiện tại theo thread**; không tự ghi cookie hay persist lựa chọn.
- `MessageSource` = tra cứu chuỗi đã bản địa hóa theo một `Locale`.
- `TimeZone` / `ZoneId` = quy tắc múi giờ, tách biệt ngôn ngữ.

Ví dụ:

```java
String title = messageSource.getMessage(
        "greeting",
        null,
        LocaleContextHolder.getLocale());
```

Đây là snippet trong một bean có `MessageSource messageSource` được inject. Nếu resource bundles chứa:

```properties
# messages_vi.properties
greeting=Xin chào
```

```properties
# messages_en.properties
greeting=Hello
```

Khi locale là Vietnamese/English và cấu hình MessageSource tìm được key, chuỗi phù hợp được lấy. Đừng gắn chặt business layer với thread holder nếu đã biết locale trong method signature; truyền `Locale` vào service làm code dễ test hơn.

### Có nên gọi setLocale để thay ngôn ngữ cho toàn phiên?

`LocaleContextHolder.setLocale(locale)` chỉ thay đổi **binding thread hiện tại**; nó không tự thay `Accept-Language` và không ghi session/cookie. Nếu ứng dụng cho phép user chọn ngôn ngữ trên giao diện, cần chiến lược `LocaleResolver` hỗ trợ ghi và có thể dùng `LocaleChangeInterceptor` hoặc endpoint cập nhật preference được thiết kế rõ.

`AcceptHeaderLocaleResolver` không hỗ trợ `setLocale` như một nơi ghi preference tùy ý; nếu cần thay locale bằng query/session/cookie, cân nhắc `SessionLocaleResolver`/`CookieLocaleResolver` và cấu hình đúng. Không đưa `setLocale` vào một request rồi mong request kế tiếp của user chắc chắn có cùng locale.

## 7. Tại sao ThreadLocal có giới hạn?

Java `ThreadLocal<T>` đặt một ô dữ liệu riêng cho **mỗi thread**. Nó không tự đồng bộ hoặc tự sao chép giữa thread. Giá trị được set trong request thread chỉ có mặt trong thread đó, cho đến khi `remove()`/reset.

### 7.1. Ví dụ Java thuần, chạy bằng javac

Tệp `ThreadLocalDemo.java`:

```java
public class ThreadLocalDemo {
    private static final ThreadLocal<String> LANGUAGE =
            new ThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        LANGUAGE.set("vi-VN");
        try {
            System.out.println("main=" + LANGUAGE.get());

            Thread child = new Thread(
                    () -> System.out.println(
                            "child=" + LANGUAGE.get()));
            child.start();
            child.join();
        } finally {
            LANGUAGE.remove();
        }

        System.out.println("mainAfter=" + LANGUAGE.get());
    }
}
```

Lệnh:

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

Stdout chính xác:

```text
main=vi-VN
child=null
mainAfter=null
```

`ThreadLocal` tiêu chuẩn không tự copy `"vi-VN"` sang child thread. Đây là Java thuần, không yêu cầu Spring hay web server.

### 7.2. InheritableThreadLocal không giải quyết thread pool

`InheritableThreadLocal` có thể sao chép tham chiếu từ parent khi một **thread mới được tạo**. Nó không cập nhật giá trị mỗi lần một pooled worker chạy một task. Trong `ExecutorService`/`ThreadPoolExecutor`:

- Worker thread có thể đã được tạo từ trước khi request A bắt đầu.
- Worker tạo khi request A đang active có thể kế thừa context A.
- Worker sau đó được **tái sử dụng** cho request B, trong khi giá trị kế thừa cũ chưa được clear.
- Nếu context chứa `HttpServletRequest`/`ServletRequestAttributes`, nó có thể tham chiếu dữ liệu **đã hết lifecycle** hoặc thông tin user trước.

Spring Javadoc của `RequestContextFilter` cảnh báo không bật inheritance với pool có khả năng tạo thread mới theo nhu cầu. Vì thế **không đặt `threadContextInheritable=true` làm cách sửa tổng quát cho @Async hoặc executor**.

Một thread con chỉ sống đúng trong phạm vi request có thể kế thừa context nếu chủ động thiết kế; tuy nhiên vẫn cần lifecycle/cleanup và nên cân nhắc liệu thật sự cần truyền cả request hay chỉ vài giá trị bất biến.

## 8. @Async, CompletableFuture và ExecutorService

Những tình huống sau **không đảm bảo** nhìn thấy `RequestContextHolder`/`LocaleContextHolder` của request ban đầu:

```java
CompletableFuture.supplyAsync(
        () -> LocaleContextHolder.getLocale());

executorService.submit(
        () -> RequestContextHolder.getRequestAttributes());

@Async
public void doWork() {
    // Chạy trên executor thread khác, không mặc nhiên có request context.
}
```

Đây là **ba snippet độc lập**, không phải một chương trình Java hoàn chỉnh. `getLocale()` vẫn có thể trả JVM default dù không hề nhận locale từ request; do đó “không bị null” không chứng minh propagation thành công. `getRequestAttributes()` trong pooled thread thường là null; `currentRequestAttributes()` có thể ném `IllegalStateException`.

### Cách nên dùng: snapshot dữ liệu cần thiết, rồi truyền tham số

Trong controller:

```java
@GetMapping("/enqueue")
public String enqueue(
        Locale locale,
        @RequestHeader(name = "X-Request-Id", required = false)
        String requestId) {

    String id = (requestId == null) ? "none" : requestId;
    jobService.enqueue(locale.toLanguageTag(), id);
    return "QUEUED";
}
```

Đây là method **minh họa** trong `@RestController` đã có bean `jobService`; không phải file biên dịch độc lập. `jobService.enqueue` có thể tạo job command gồm hai `String` bất biến. Job không cần `HttpServletRequest`, `ServletRequestAttributes` hay một thread-bound context còn sống.

Nếu job cần user identity, chỉ truyền **ID/các quyền cần kiểm tra lại** theo thiết kế bảo mật, không coi thông tin từ request header do client tự gửi là trusted identity. Khi job xử lý sau, hãy re-authorize theo chính sách phù hợp; tránh mang nguyên security/session/request context ra khỏi lifecycle.

### Khi nào TaskDecorator hợp lý?

Spring `TaskDecorator` có thể giúp propagate **một số context được phép** vào task trên executor, với việc khôi phục context cũ trong `finally`. Có thể dùng cho `LocaleContext` hoặc logging correlation ID khi tác vụ ngắn, không chứa tài nguyên request đã đóng. Tuy nhiên propagate request attributes nguyên trạng qua pool là rủi ro.

Ví dụ an toàn hơn cho locale, không mang servlet request:

```java
package com.example.demo;

import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.core.task.TaskDecorator;

public class LocaleTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        // Chụp locale context tại thời điểm submit/decorate task.
        LocaleContext captured = LocaleContextHolder.getLocaleContext();

        return () -> {
            LocaleContext previous =
                    LocaleContextHolder.getLocaleContext();
            try {
                LocaleContextHolder.setLocaleContext(captured);
                task.run();
            } finally {
                LocaleContextHolder.setLocaleContext(previous);
            }
        };
    }
}
```

Dùng với `ThreadPoolTaskExecutor.setTaskDecorator(new LocaleTaskDecorator())` trong cấu hình executor. Snippet này là **lớp Java độc lập trong dự án Spring có dependencies**, không tự khởi động web server. Nó copy `LocaleContext`, không copy `RequestAttributes`. Khi ngữ cảnh gốc null, `setLocaleContext(null)` reset thread-bound locale trên worker; `finally` khôi phục trạng thái trước đó. Với logging MDC, security context hoặc trace context, có cơ chế propagation và cleanup riêng; không tự cho rằng copy locale đồng nghĩa copy tất cả.

Lưu ý khi dùng `@Async`: framework có thể tạo wrapper task/future; TaskDecorator can thiệp vào runnable được executor chạy, không nhất thiết trực tiếp vào đúng đoạn code người dùng nghĩ. Hãy test thực tế và tránh dùng một static holder làm giao ước dài hạn của job.

## 9. Servlet async do Spring MVC quản lý khác task tự spawn

Spring MVC hỗ trợ controller trả `Callable<T>` hoặc `WebAsyncTask<T>`; framework điều phối Servlet async processing. Spring có cơ chế gắn request/locale context trong những giai đoạn thích hợp của xử lý async do MVC quản lý, và có thể dispatch lại vào Servlet.

**Không được suy từ đó rằng mọi `CompletableFuture.supplyAsync` hoặc background job của bạn sẽ được gắn đúng context.** Thread pool tùy ý chạy bên ngoài MVC async lifecycle là chuyện khác.

Ví dụ controller trả `Callable` an toàn với snapshot dữ liệu:

```java
@GetMapping("/async-safe")
public Callable<LanguageResponse> asyncSafe(Locale locale) {
    final String tag = locale.toLanguageTag();
    return () -> new LanguageResponse(tag);
}
```

Method này **không phụ thuộc vào locale ThreadLocal ở worker**; `tag` đã được lấy khi controller ở request context hợp lệ. `Callable` do MVC quản lý có lifecycle/async dispatch riêng, nhưng code vẫn tường minh và dễ test.

Nếu tự chạy asynchronous streaming hoặc gửi sự kiện `SseEmitter` sau khi response đã commit, request có thể không còn sống. Đừng lưu `ServletRequestAttributes` để dùng trong callback nhiều phút sau. Trong ứng dụng với virtual threads (Java 21+), mỗi task có thể có thread riêng nhưng **ThreadLocal vẫn là cơ chế theo thread**, không tự thay đổi semantics request lifetime hay propagation; Java 17 demo không dùng virtual threads.

## 10. Mã mẫu chạy được: Spring Boot 3 / Spring MVC

Ví dụ này minh họa ba cách đọc context:

- `GET /context/info`: đọc request và locale từ hai holder trong MVC dispatch; đồng thời nhận `Locale` và `HttpServletRequest` trực tiếp để so sánh.
- `GET /context/async-safe`: dùng `Callable` và **snapshot locale tag** từ request trước khi task async bắt đầu.
- `GET /context/messages`: lấy message từ `MessageSource` theo `Locale` đang được MVC resolve.

Dự án Maven từ Spring Initializr với Java 17+, `spring-boot-starter-web`, `spring-boot-starter-test`. Với `Locale`/MessageSource, thêm các tệp messages bên dưới; không cần database và không cần `RequestContextFilter` riêng vì controller chạy trong `DispatcherServlet`.

### 10.1. src/main/java/com/example/demo/DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 10.2. src/main/java/com/example/demo/ContextController.java

```java
package com.example.demo;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.MessageSource;
import org.springframework.context.i18n.LocaleContext;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.RequestAttributes;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import java.util.Locale;
import java.util.concurrent.Callable;

@RestController
public class ContextController {

    private final MessageSource messages;

    public ContextController(MessageSource messages) {
        this.messages = messages;
    }

    @GetMapping("/context/info")
    public ContextResponse info(
            HttpServletRequest request,
            Locale locale) {

        RequestAttributes attrs =
                RequestContextHolder.getRequestAttributes();
        LocaleContext localeContext =
                LocaleContextHolder.getLocaleContext();

        boolean servletBound =
                attrs instanceof ServletRequestAttributes;
        boolean localeBound = localeContext != null;

        String path = request.getRequestURI();
        String tag = locale.toLanguageTag();
        String holderTag = LocaleContextHolder.getLocale()
                .toLanguageTag();

        return new ContextResponse(
                path, tag, holderTag, servletBound, localeBound);
    }

    @GetMapping("/context/async-safe")
    public Callable<LanguageResponse> asyncSafe(Locale locale) {
        String captured = locale.toLanguageTag();

        // Callable được Spring MVC xử lý như servlet async.
        return () -> new LanguageResponse(captured);
    }

    @GetMapping("/context/messages")
    public MessageResponse messages(Locale locale) {
        String resolved = messages.getMessage(
                "greeting", null, locale);
        return new MessageResponse(
                locale.toLanguageTag(), resolved);
    }

    public record ContextResponse(
            String path,
            String locale,
            String holderLocale,
            boolean requestBound,
            boolean localeBound) {}

    public record LanguageResponse(String locale) {}

    public record MessageResponse(
            String locale, String greeting) {}
}
```

Vì code nằm trong controller `@RestController`, Spring MVC resolve argument `HttpServletRequest`/`Locale` qua method arguments, rồi Jackson serialize DTO record. `ServletRequestAttributes` được kiểm tra bằng `instanceof` thay vì cast mù. Không cần tạo static field chứa request; controller bean thường là singleton, trong khi request là tài nguyên có vòng đời riêng.

**Phần quan trọng của demo:** `info()` nhận `Locale` làm parameter, nhưng đồng thời đọc `LocaleContextHolder.getLocale()`. Hai kết quả thông thường cùng locale trong MVC dispatch. `requestBound` và `localeBound` là boolean có thể kiểm chứng chứ không khẳng định mọi request phải có timezone.

### 10.3. src/main/resources/messages_vi.properties

```properties
greeting=Xin chào
```

### 10.4. src/main/resources/messages_en.properties

```properties
greeting=Hello
```

Có thể thêm `src/main/resources/messages.properties` làm fallback:

```properties
greeting=Hello
```

Đây là ba file riêng; messages bundle được Spring Boot auto-configure khi đặt đúng nguồn và có fallback `messages.properties`. Không cần gọi `LocaleContextHolder.setLocale` để dịch vì handler đã nhận `Locale` của request.

### 10.5. Chạy ứng dụng

```bash
./mvnw spring-boot:run
```

PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Cổng mặc định thường là 8080 nếu không chỉnh `server.port`. Những source này không biên dịch bằng `javac ContextController.java` khi chưa có Spring Boot dependencies; sử dụng dự án Maven đã tạo từ Spring Initializr.

## 11. Kiểm chứng HTTP bằng curl

### Request context và locale

```bash
curl -s -H "Accept-Language: vi-VN" \
  http://localhost:8080/context/info
```

Với cấu hình locale resolver tiêu chuẩn đọc Accept-Language, JSON kỳ vọng có các giá trị:

```json
{
  "path": "/context/info",
  "locale": "vi-VN",
  "holderLocale": "vi-VN",
  "requestBound": true,
  "localeBound": true
}
```

Thứ tự JSON keys có thể khác; không dùng snapshot chuỗi nguyên JSON để kiểm tra. Nếu ứng dụng đã cấu hình `LocaleResolver` riêng, `defaultLocale`, `supportedLocales` hay gateway sửa header, locale có thể khác: cần điều chỉnh test theo contract.

### MessageSource theo ngôn ngữ

```bash
curl -s -H "Accept-Language: vi-VN" \
  http://localhost:8080/context/messages
```

Kỳ vọng `greeting` = `"Xin chào"`, `locale` = `"vi-VN"`. Với:

```bash
curl -s -H "Accept-Language: en-US" \
  http://localhost:8080/context/messages
```

Kỳ vọng `greeting` = `"Hello"` theo bundle English. Bài này chọn key `greeting`, không phụ thuộc database hay request session.

### Servlet async an toàn

```bash
curl -s -H "Accept-Language: vi-VN" \
  http://localhost:8080/context/async-safe
```

Kỳ vọng response sau async dispatch chứa `{"locale":"vi-VN"}`. Locale tag được snapshot **trước** khi Callable chạy; không phụ thuộc worker đọc ThreadLocal.

## 12. MockMvc: kiểm tra bound context, locale và async

Tạo `src/test/java/com/example/demo/ContextControllerTest.java`, phụ thuộc `spring-boot-starter-test`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Locale;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void requestAndLocaleContextAreBoundInsideMvc() throws Exception {
        mvc.perform(get("/context/info")
                .locale(Locale.forLanguageTag("vi-VN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.path").value("/context/info"))
            .andExpect(jsonPath("$.locale").value("vi-VN"))
            .andExpect(jsonPath("$.holderLocale").value("vi-VN"))
            .andExpect(jsonPath("$.requestBound").value(true))
            .andExpect(jsonPath("$.localeBound").value(true));
    }

    @Test
    void messageSourceUsesResolvedLocale() throws Exception {
        mvc.perform(get("/context/messages")
                .locale(Locale.forLanguageTag("vi-VN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.greeting").value("Xin chào"));
    }

    @Test
    void asyncResponseUsesCapturedValue() throws Exception {
        MvcResult initial = mvc.perform(get("/context/async-safe")
                .locale(Locale.forLanguageTag("vi-VN")))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(initial))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.locale").value("vi-VN"));
    }
}
```

Chạy:

```bash
./mvnw test
```

Windows:

```powershell
.\mvnw.cmd test
```

Đây là **mẫu test có thể chạy trong project Boot 3 đã khai báo dependencies**; không phải kết quả đã thực thi trong repo cụ thể. Nếu bật Spring Security, custom locale resolver hoặc filter, test có thể cần mock user, allow-list và cấu hình locale tương ứng.

**Vì sao test async không gọi ThreadLocal trên worker?** Mục tiêu là chứng minh cách truyền snapshot ổn định, không giả định tất cả worker luôn có HTTP request context. Để test cơ chế MVC async binding riêng, viết test có kiểm soát theo Spring Framework version và lifecycle, không lấy behavior ngẫu nhiên của một `ExecutorService` làm contract.

## 13. Unit test thiếu request context

Trong unit test ngoài MVC, `RequestContextHolder.getRequestAttributes()` có thể là null. Có thể kiểm tra rõ mà không cần web server:

```java
import org.junit.jupiter.api.Test;
import org.springframework.web.context.request.RequestContextHolder;

import static org.junit.jupiter.api.Assertions.*;

class NoRequestContextTest {

    @Test
    void noRequestContextOnOrdinaryTestThread() {
        RequestContextHolder.resetRequestAttributes();

        assertNull(RequestContextHolder.getRequestAttributes());
        assertThrows(IllegalStateException.class,
                RequestContextHolder::currentRequestAttributes);
    }
}
```

Đây là **lớp test độc lập trong source test của một dự án Spring có JUnit**; file cần package phù hợp nếu project yêu cầu. Với môi trường JSF có `FacesContext` đang active, `currentRequestAttributes()` có thể fallback thay vì throw; test trên giả định unit test Java thông thường không có JSF FacesContext.

Nếu viết test cho `LocaleContextHolder`, phải nhớ `getLocale()` fallback default nên **không assert null**. Dùng `LocaleContextHolder.getLocaleContext()` để biết có context gắn với thread hay không. Unit test dùng `setLocaleContext`/`setRequestAttributes` thủ công phải cleanup trong `finally` hoặc teardown; không tạo state rò rỉ giữa các test cùng test worker.

## 14. Khi thật sự cần gắn context thủ công

Trong code tùy chỉnh, nếu cần tạm gắn một `LocaleContext`, hãy **khôi phục trạng thái trước đó**, không đơn giản luôn reset một context do framework đang sở hữu.

```java
LocaleContext old = LocaleContextHolder.getLocaleContext();
try {
    LocaleContextHolder.setLocale(Locale.forLanguageTag("vi-VN"));
    doSomethingThatNeedsLocale();
} finally {
    LocaleContextHolder.setLocaleContext(old);
}
```

Đoạn này là snippet trong method đã có import `Locale`/`LocaleContext` và method `doSomethingThatNeedsLocale()`. Nó không tự lập trình session/cookie cho user và không nên được dùng trong controller chỉ để đổi locale của ứng dụng qua nhiều request.

Với `RequestContextHolder`, tự tạo `ServletRequestAttributes` và gắn vào custom thread chỉ có thể hợp lý trong phạm vi một request **còn active**, có quản lý cleanup và không làm sai lifecycle. Không nên dùng `new ServletRequestAttributes(mockRequest)` trong production chỉ để dập `IllegalStateException`, và càng không dùng request attributes từ request A cho background job của request B.

Nếu cần xử lý tác vụ có id người gọi/ngôn ngữ, truyền immutable data và authorize đúng. Context propagation framework chỉ nên là bổ trợ cho những cross-cutting concerns đã hiểu vòng đời.

## 15. Cạm bẫy và xử lý lỗi

1. **Đọc context trong constructor singleton:** constructor chạy khi khởi động, không có request, dẫn đến `IllegalStateException`.
2. **Dùng currentRequestAttributes ngoài thread web:** trong `@Scheduled`, `@Async` hoặc pooled worker có thể ném exception.
3. **Cho rằng getLocale() không null nghĩa là request đã propagate:** sai; nó fallback Spring/JVM default.
4. **Bật inheritable=true cho thread pool:** có thể rò rỉ context từ request cũ vào pooled worker.
5. **Lưu ServletRequestAttributes trong static map/cache:** tạo memory leak và tham chiếu request đã hết vòng đời.
6. **Quên cleanup ThreadLocal trong code tự set:** worker giữ dữ liệu cũ khi tái sử dụng.
7. **Cố lấy userId từ request header và coi là trusted identity:** header client tự kiểm soát; xác thực/ủy quyền riêng.
8. **Đổi locale qua LocaleContextHolder.setLocale rồi mong session nhớ:** nó chỉ thay thread-bound context; dùng resolver/persist preference phù hợp.
9. **Nhầm Accept-Language với timezone:** ngôn ngữ/region không xác định múi giờ thực của user.
10. **Đọc RequestContextHolder trong filter chạy trước DispatcherServlet:** holder có thể chưa được framework bind; cần xác định filter/listener và thứ tự.
11. **Copy HttpServletRequest vào CompletableFuture:** request có thể đã kết thúc; chỉ snapshot thông tin cần.
12. **TaskDecorator set locale mà không finally restore:** pooled worker có thể mang locale của user khác.
13. **Mang toàn bộ SecurityContext một cách vô điều kiện:** cần dùng cơ chế security propagation và lifecycle, không tự copy credentials.
14. **Dựa vào ThreadLocal để duy trì business transaction qua thread:** transaction và persistence context có cơ chế riêng, không được tự mang qua worker.
15. **Dùng Locale.getDefault() để suy locale của client:** đó là JVM default, không phải Accept-Language.
16. **Nhận HTTP 500 khi không có request rồi sửa bằng RequestContextFilter ở mọi nơi:** nếu call site là scheduled job, filter không chạy ở đó; sửa dependency của job.
17. **Gắn context mà không phân biệt REQUEST/ERROR/ASYNC dispatch:** thread/dispatch có thể khác; inspect lifecycle thực.
18. **Để message key không tồn tại:** MessageSource có thể ném `NoSuchMessageException` nếu không có default phù hợp, không phải lỗi ThreadLocal.
19. **Dùng holder static làm API business:** khó test, che dependency và giới hạn reuse qua CLI, batch, messaging.
20. **Kết luận propagation từ test chạy “thỉnh thoảng đúng”:** executor thread reuse/timing có thể tạo tình trạng không ổn định; test với giá trị snapshot.
21. **Đọc request sau khi response hoàn tất:** request scope đã hết; dù reference vẫn còn không có nghĩa an toàn.
22. **Không phân biệt SessionLocaleResolver với AcceptHeaderLocaleResolver:** chính sách lưu locale khác nhau; cần thiết kế rõ giao diện đổi ngôn ngữ.
23. **Bỏ qua test cô lập đa luồng:** có thể có cross-request leak không lộ ra trong happy-path.
24. **Trộn thread-context với Reactor Context trong WebFlux:** model lập trình khác, hãy dùng đúng API của reactive stack.

## 16. Quy trình debug khi locale/request context “biến mất”

1. Xác định đoạn code chạy trên **thread nào**; log tên thread/correlation ID có kiểm soát, không log dữ liệu nhạy cảm.
2. Nó chạy trong MVC controller/service đồng bộ, servlet filter, `@Async`, `Callable`, `CompletableFuture` hay scheduled task?
3. Nếu `RequestContextHolder.getRequestAttributes() == null`, xem có vào DispatcherServlet chưa, filter/listener có được đăng ký không.
4. Nếu `currentRequestAttributes()` ném IllegalStateException trong background job, không thêm Filter một cách mù quáng: chuyển sang snapshot input hoặc thiết kế truyền tham số.
5. Nếu `LocaleContextHolder.getLocale()` ra locale mặc định, kiểm tra `getLocaleContext()` để phân biệt context thiếu với locale được resolve là mặc định.
6. Xem `LocaleResolver` và header `Accept-Language` thật; client, gateway hay test có thể override locale.
7. Xem task executor/thread pool và cờ inheritable; tránh patch bằng `setThreadContextInheritable(true)`.
8. Kiểm tra cleanup trong `finally` của mọi đoạn code tự set ThreadLocal, kể cả khi task ném exception.
9. Nếu lỗi xảy ra khi async response, xem Servlet async lifecycle, ERROR/ASYNC dispatch và thời điểm response đã commit.
10. Đo bằng unit test không có request, MockMvc trong request và integration test executor thực; không gộp ba kết quả này thành một tình huống.
11. Nếu kết quả phụ thuộc request ID/timezone, truyền hai giá trị đó dưới kiểu immutable vào worker thay vì request object.
12. Kiểm tra chính sách user/tenant, session/cookie và authorization riêng; thread-bound locale không chứng minh đã xác thực.

## 17. Checklist thiết kế an toàn

- [ ] Controller có thể nhận trực tiếp `HttpServletRequest`, `Locale` hoặc principal qua method arguments khi cần?
- [ ] Service nhận dữ liệu cần thiết dưới dạng tham số rõ ràng thay vì truy cập holder tĩnh?
- [ ] Code dùng `currentRequestAttributes()` chỉ khi đang chắc chắn ở request lifecycle?
- [ ] Code có fallback đúng khi `getRequestAttributes()==null`?
- [ ] Không lưu `ServletRequestAttributes`/`HttpServletRequest` vào background queue, cache hoặc static field?
- [ ] Không bật inheritable context cho pooled executor?
- [ ] Mọi ThreadLocal tự set đều được restore/clear bằng `finally`?
- [ ] Locale resolver phản ánh đúng hợp đồng `Accept-Language`/session/cookie?
- [ ] Locale và timezone được phân biệt; timezone lấy từ nguồn hợp lệ riêng?
- [ ] I18n message được lookup bằng locale explicit hoặc context đã được xác nhận?
- [ ] Servlet async và worker thread được kiểm thử riêng?
- [ ] Có test chống leak giữa những tác vụ/user khác nhau khi dùng custom decorators?
- [ ] Request-specific business data có authorization; không tin header client tự chọn?
- [ ] HTTP/error response không lộ request context hoặc dữ liệu cá nhân?
- [ ] Code có khả năng chạy từ batch/event/CLI mà không phụ thuộc HTTP thread nếu use case cần?

## 18. Câu hỏi tự kiểm tra

**1.** `RequestContextHolder.currentRequestAttributes()` và `getRequestAttributes()` khác nhau ra sao?

**Đáp án:** `getRequestAttributes()` trả null nếu không có thread-bound context. `currentRequestAttributes()` yêu cầu context, có thể fallback JSF, sau đó ném IllegalStateException nếu vẫn không có.

**2.** Vì sao `LocaleContextHolder.getLocale()` không phải cách kiểm tra request đã được bind?

**Đáp án:** Nó fallback Spring/JVM default ngay cả khi không có context. Dùng `getLocaleContext()` để xem có locale context gắn thread hay không.

**3.** `Locale.forLanguageTag("vi-VN")` có nghĩa timezone = Asia/Ho_Chi_Minh?

**Đáp án:** Không. Locale/region và timezone là hai thông tin khác nhau.

**4.** Có phải Spring MVC controller đồng bộ nào cũng cần thêm RequestContextFilter mới đọc được RequestContextHolder?

**Đáp án:** Không. DispatcherServlet đã expose request context trong xử lý MVC thông thường.

**5.** Vì sao không bật `setThreadContextInheritable(true)` cho thread pool?

**Đáp án:** Pooled worker có thể tạo lúc request A active rồi được tái sử dụng cho B, giữ context A hoặc context đã hết vòng đời, gây rò rỉ và sai dữ liệu.

**6.** Có thể lấy request locale tự động trong `CompletableFuture.supplyAsync` không?

**Đáp án:** Không được giả định. Executor thread khác; snapshot locale và truyền tường minh, hoặc dùng decorator chuyên biệt có cleanup nếu thực sự cần.

**7.** `@Async` có làm HttpServletRequest tồn tại lâu hơn response không?

**Đáp án:** Không. Background task có lifecycle riêng; không nắm giữ request attributes sau khi request hoàn tất.

**8.** `LocaleContextHolder.setLocale` có tạo cookie cho request sau không?

**Đáp án:** Không. Nó sửa context của thread hiện tại. Muốn persist lựa chọn ngôn ngữ cần resolver/session/cookie/preference mechanism phù hợp.

**9.** Khi nào `TaskDecorator` phù hợp?

**Đáp án:** Khi cần propagate context nhỏ và an toàn (như locale, trace metadata) vào tác vụ đã quản lý, có `try/finally` khôi phục. Không copy nguyên ServletRequestAttributes vào job dài hạn.

**10.** Cách đơn giản để service không phụ thuộc RequestContextHolder?

**Đáp án:** Controller lấy `Locale`/request id/user id từ framework, tạo input DTO/snapshot immutable rồi truyền vào service qua tham số.

## 19. Tài liệu tham khảo

- Spring Framework — RequestContextHolder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/context/request/RequestContextHolder.html
- Spring Framework — LocaleContextHolder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/context/i18n/LocaleContextHolder.html
- Spring Framework — RequestContextFilter và inheritable context: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/filter/RequestContextFilter.html
- Spring Framework — RequestContextListener: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/web/context/request/RequestContextListener.html
- Spring Framework — LocaleResolver / LocaleContextResolver: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/localeresolver.html
- Spring Framework — MVC Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — MVC Async Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — TaskDecorator API: https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/task/TaskDecorator.html
- Java 17 — ThreadLocal Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java 17 — InheritableThreadLocal Javadoc: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html
- Jakarta Servlet specification: https://jakarta.ee/specifications/servlet/
