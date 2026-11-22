# Request scope, session scope và dữ liệu dùng chung giữa các yêu cầu trong Spring MVC

## 1. Từ bản chất HTTP đến bài toán quản lý trạng thái

HTTP request là một lần trao đổi độc lập: client gửi phương thức, URI, headers và có thể có body; server xử lý rồi trả status, headers và body. HTTP **không tự mang toàn bộ biến Java từ request trước sang request sau**. Trong khi đó ứng dụng web lại thường cần nhớ dữ liệu:

- **Trong một request:** mã theo dõi, tenant đã xác thực, dữ liệu trung gian do filter hoặc interceptor tính toán.
- **Giữa nhiều request của cùng một người dùng/phiên:** lựa chọn ngôn ngữ, bước hiện tại của một wizard, giỏ hàng nhỏ hoặc tùy chọn giao diện.
- **Giữa các request từ mọi người dùng:** cấu hình chỉ đọc, feature catalog, bộ đếm toàn ứng dụng hoặc cache dùng chung.
- **Qua restart, qua nhiều máy chủ hoặc trong thời gian dài:** profile người dùng, đơn hàng, giỏ hàng cần bền vững, bản ghi trong database hoặc kho lưu trữ ngoài.

Spring MVC cung cấp **Servlet request/session** và các **Spring bean scopes** để biểu diễn vòng đời tương ứng. Tuy nhiên, “scope” không có nghĩa “dữ liệu tự động được lưu bền vững”; phải chọn đúng chủ sở hữu, thời hạn và nơi lưu trữ.

Hình dung ba request:

```text
Browser A                           Server
   | GET /api/scope/request  -------> request R1
   |                                  @RequestScope -> Bean R1
   | <------- response --------------- R1 kết thúc
   |
   | GET /api/scope/session  -------> request R2, session S-A
   |                                  @SessionScope -> Bean S-A
   | <------- Set-Cookie session-id -- session S-A còn sống
   |
   | GET /api/scope/session + cookie -> request R3, session S-A
   |                                  @RequestScope -> Bean R3 mới
   |                                  @SessionScope -> Bean S-A cũ
   | <------- response --------------- R3 kết thúc

Browser B
   | GET /api/scope/session  -------> request R4, session S-B
                                      Bean S-B khác S-A

@ApplicationScope / singleton:
cùng một ứng dụng web có thể được dùng bởi R1, R2, R3, R4
(nhưng không mặc định chia sẻ với JVM hoặc node triển khai khác).
```

**Mục tiêu bài học:** phân biệt thời gian sống và phạm vi nhìn thấy của dữ liệu, dùng `@RequestScope`/`@SessionScope`/`@ApplicationScope` đúng cách, tránh nhầm chúng với `HttpSession`/request attributes, hiểu session ID và cookie, kiểm thử bằng Java 17+ Spring MVC và lựa chọn cách lưu state an toàn trong hệ thống nhiều instance.

## 2. Phân biệt scope của Servlet và scope của Spring bean

Có hai lớp khái niệm cùng sử dụng từ “request” và “session”:

1. **Servlet attributes:** key-value nằm trong `HttpServletRequest`, `HttpSession` hoặc `ServletContext`, thường được đặt bằng `setAttribute(name, value)`.
2. **Spring bean scopes:** container quyết định một bean definition sẽ được tạo một instance cho mỗi request/session/application hay dùng một instance chung.

Hai lớp có quan hệ vòng đời nhưng **không phải API đồng nghĩa**. Khi bạn gọi `request.setAttribute("trace", "abc")`, Spring không tự biến chuỗi đó thành một bean `@RequestScope`. Khi đánh dấu `@SessionScope` cho một bean, bạn không cần tự gọi `session.setAttribute` để đăng ký bean; Spring quản lý instance qua scope của container.

| Phạm vi | Giá trị tồn tại trong | Ai thường sử dụng | Có đi qua request mới? | Chia sẻ giữa người dùng? |
| --- | --- | --- | --- | --- |
| Biến cục bộ method | Một lần gọi method | Bất kỳ Java method | Không | Không |
| Servlet **request attribute** | Một Servlet request | Filter, interceptor, controller | Không, trừ trường hợp cùng request được forward/dispatch | Không |
| Spring **request-scoped bean** | Một request trong web-aware context | Controller/service được DI | Không | Không |
| Servlet **session attribute** | HTTP session | Controller, auth/session manager | Có, nếu request mới tìm đúng session còn hiệu lực | Không theo mặc định |
| Spring **session-scoped bean** | HTTP session | Component có state của từng session | Có, khi đúng session và state còn hiệu lực | Không theo mặc định |
| Spring **application-scoped bean** | Một `ServletContext` | Thành phần dữ liệu cấp web app | Có | Có, trong cùng ServletContext |
| Spring **singleton bean** | Một Spring IoC container | Controller, service, repository thông thường | Có | Có, trong cùng container |
| Database/shared cache | Theo khóa, TTL và nghiệp vụ | Repository/service/cache | Có | Tùy khóa và phân quyền |

**Điểm dễ nhầm:** `@ApplicationScope` và Spring singleton có thể có vòng đời gần nhau trong một Spring Boot web app đơn giản, nhưng không đồng nhất về contract. Singleton là **một instance trên một bean definition trong một Spring IoC container**; application scope là **một instance trong ServletContext**. Khi có nhiều Spring ApplicationContext hoặc nhiều web applications, kết quả có thể khác.

Với **Spring WebFlux**, session abstraction là `WebSession`, không phải Servlet `HttpSession`. Ví dụ dưới đây chỉ dành cho Spring MVC Servlet, không copy nguyên imports sang WebFlux.

## 3. Request scope: dữ liệu chỉ cần trong một HTTP request

### 3.1. Servlet request attributes

`HttpServletRequest#setAttribute` cất object dưới một key trong **request hiện tại**:

```java
// Một Servlet Filter hoặc HandlerInterceptor đặt thông tin:
request.setAttribute("traceId", "trace-42");

// Một thành phần downstream đọc lại:
String traceId = (String) request.getAttribute("traceId");

// Có thể xóa:
request.removeAttribute("traceId");
```

Đây là **fragment Java**, giả định `request` là biến `jakarta.servlet.http.HttpServletRequest` đang được xử lý. Các giá trị không tự đi qua HTTP redirect (redirect tạo request mới). Khi Servlet **forward** một request đến resource khác, request có thể được dùng tiếp và attributes của nó vẫn có ý nghĩa; cần phân biệt forward với redirect.

Trong controller, thay vì dùng Servlet API trực tiếp, có thể khai báo:

```java
@GetMapping("/trace")
String trace(@RequestAttribute("traceId") String traceId) {
    return traceId;
}
```

`@RequestAttribute` trên tham số lấy **một attribute đã được đặt trước đó**. Nó không đọc trực tiếp JSON body, query parameter hoặc HTTP header cùng tên. Nếu dữ liệu có thể thiếu, dùng `@RequestAttribute(name="traceId", required=false)` hoặc `Optional<String>`, rồi có logic fallback rõ ràng.

Điều này có ích cho dữ liệu do server tính toán trong một request: correlation ID, kết quả tenant resolution, thông tin đã được xác thực và chuẩn hóa. Nếu attribute liên quan authentication/authorization, phải xác định nguồn tin cậy; một header tùy ý từ client **không tự trở thành danh tính đã xác thực**.

### 3.2. Spring bean `@RequestScope`

Bean có scope request được tạo khi Spring cần nó trong một request web phù hợp và được giữ để dùng lại **trong request đó**. Request khác tạo target bean mới.

```java
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
class RequestMarker {
    private final String id = UUID.randomUUID().toString();

    String getId() {
        return id;
    }
}
```

Đây là class hoàn chỉnh trong project Spring MVC (được sử dụng ở ví dụ ứng dụng phần 8). Khi hai method call đến `getId()` trên cùng scoped bean trong **cùng request**, nhận cùng ID; sang request mới, thường có ID mới. UUID chỉ để quan sát vòng đời, không được coi là token bảo mật hoặc định danh người dùng.

**Không nhầm** `@RequestScope` với `@RequestAttribute`:

| `@RequestScope` | `@RequestAttribute` |
| --- | --- |
| Annotation Spring đặt trên **bean class/factory method** | Annotation Spring MVC đặt trên **tham số handler** |
| Spring IoC quản lý vòng đời **instance bean** | MVC argument resolver đọc object theo key từ Servlet request |
| Có thể inject proxy vào singleton bean | Cần attribute đã được đặt trước khi handler resolve |
| Thích hợp component chứa context của một request | Thích hợp truyền giá trị ngắn, rõ key từ filter/interceptor |

Nếu chỉ cần một chuỗi `traceId`, không bắt buộc phải tạo cả scoped bean. Ngược lại, khi một object request có nhiều phụ thuộc và cần được inject ở vài lớp, request-scoped bean là lựa chọn dễ quản lý.

## 4. Session scope: nhiều request có thể chia sẻ state của cùng phiên

### 4.1. HTTP session và session ID

`HttpSession` là abstraction của Servlet container. Với cách quản lý thường gặp, server tạo một session rồi cấp cho browser một **session identifier** (ví dụ cookie `JSESSIONID`). Những request sau mang đúng session ID hợp lệ để server nhận ra cùng session.

```text
Browser                 Server
POST /preferences
  không cookie           tạo Session S-1
       ----------------->
  <--------------------- Set-Cookie: JSESSIONID=<opaque-id>

GET /preferences
  Cookie: JSESSIONID=...  tìm lại Session S-1
       ----------------->
  <--------------------- đọc language đã lưu

Browser khác/incognito
  không cookie hợp lệ     Session S-2 mới (nếu ứng dụng cần)
       ----------------->
```

Cookie thường lưu **session ID**, không phải toàn bộ Java object trong session. Các thuộc tính trong `HttpSession` thường nằm ở phía server/container hoặc session store bên ngoài. Đây khác với thiết kế cookie chứa dữ liệu client-readable hay JWT self-contained.

Session có thể hết hiệu lực vì timeout, logout, invalidate, session store không còn dữ liệu hoặc ứng dụng triển khai lại. **Không bao giờ coi việc có cookie `JSESSIONID` là bằng chứng session hợp lệ hoặc đã đăng nhập.**

### 4.2. Đọc và ghi Servlet session attributes

```java
@PostMapping("/preferences")
String save(@RequestParam String language, HttpSession session) {
    session.setAttribute("language", language);
    return "saved";
}

@GetMapping("/preferences")
String read(
        @SessionAttribute(name = "language", required = false)
        String language) {

    return language == null ? "unset" : language;
}
```

Các đoạn trên là **method fragment trong controller**, cần imports tương ứng. `@SessionAttribute` đọc attribute đã có trong HTTP session; `required=false` cho phép vắng mặt. Muốn ghi/xóa, thường dùng `HttpSession#setAttribute` / `removeAttribute` hoặc `WebRequest`.

**Cẩn thận với việc tạo session:**

```java
// Có thể tạo session nếu chưa có:
HttpSession session = request.getSession();

// Chỉ đọc session đã có, không tạo mới:
HttpSession existing = request.getSession(false);
if (existing != null) {
    Object value = existing.getAttribute("language");
}
```

`request` ở đây là `HttpServletRequest`. Inject tham số `HttpSession` vào handler hoặc truy cập `@SessionScope` bean có thể khiến session được tạo khi chưa có; khi endpoint cần **chỉ kiểm tra trạng thái cũ**, dùng `getSession(false)` để tránh tạo session không cần thiết.

Khi muốn logout hoặc bỏ mọi dữ liệu liên quan một session:

```java
HttpSession existing = request.getSession(false);
if (existing != null) {
    existing.invalidate();
}
```

`invalidate()` kết thúc session; không chỉ xóa một key. Nếu chỉ bỏ chọn ngôn ngữ, `existing.removeAttribute("language")` thích hợp hơn. Với hệ thống dùng Spring Security, logout/session fixation/concurrent session control cần đi qua cơ chế quản lý security chính thức thay vì coi mỗi lời gọi `invalidate()` tùy ý là luồng đăng xuất hoàn chỉnh.

### 4.3. Spring bean `@SessionScope`

`@SessionScope` là shortcut cho `@Scope("session")` và **mặc định tạo class-based scoped proxy** (TARGET_CLASS). Bean target thực được tạo riêng theo HTTP session và dùng lại trong cùng session.

```java
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.SessionScope;

@Component
@SessionScope
class SessionPreferences {
    private String language = "vi";

    synchronized String getLanguage() {
        return language;
    }

    synchronized void setLanguage(String language) {
        this.language = language;
    }
}
```

Đây là class minh họa quản lý preference cho một session. Cơ chế đồng bộ bảo vệ hai method trong **cùng JVM và cùng bean instance**, nhưng không bảo đảm đồng bộ đa node khi session object được serialize/copy qua Redis hoặc backend khác. Với data shared giữa các server, cần thiết kế nhất quán phù hợp kho lưu trữ.

Spring không tự ghi mọi mutable field của session bean ra database. Ở session store ngoài, object có thể cần **serialization** và cách phát hiện thay đổi phù hợp cấu hình `Spring Session`. Một implementation session bean dạng mutable không đương nhiên phù hợp cho cluster.

## 5. Vì sao session-scoped bean có thể inject vào singleton controller?

Spring `@Controller`/`@Service` thường là **singleton**, được tạo một lần cho mỗi Spring IoC container. Nếu inject trực tiếp một object thực có vòng đời request/session ngắn hơn vào singleton, sẽ xảy ra *scope mismatch*: singleton giữ reference đến một instance trong khi request/session sau cần instance khác.

Giải pháp thông dụng là **scoped proxy**:

```text
Singleton controller (một instance)
       |
       +--- injected RequestMarker proxy -------------+
       |                                              |
       |  Request R1: proxy.getId() -> RequestMarker-R1|
       |  Request R2: proxy.getId() -> RequestMarker-R2|
       |                                              |
       +--- injected SessionPreferences proxy --------+
                                                      |
          Session S-A: proxy.getLanguage() -> Bean S-A
          Session S-B: proxy.getLanguage() -> Bean S-B
```

`@RequestScope` và `@SessionScope` mặc định sử dụng `proxyMode=ScopedProxyMode.TARGET_CLASS`. Proxy có thể được inject một lần vào singleton; mỗi method call trong request hợp lệ sẽ chuyển đến **target của scope hiện tại**.

Ví dụ controller constructor injection:

```java
@RestController
class ContextController {
    private final RequestMarker requestMarker;
    private final SessionPreferences preferences;

    ContextController(
            RequestMarker requestMarker,
            SessionPreferences preferences) {
        this.requestMarker = requestMarker;
        this.preferences = preferences;
    }

    @GetMapping("/context")
    String context() {
        return requestMarker.getId() + ":" + preferences.getLanguage();
    }
}
```

Đây là **class minh họa**, chưa chứa toàn bộ imports/config. `ContextController` vẫn là singleton; đối tượng mà constructor nhận là scoped proxy, **không phải cùng target state cho mọi người dùng**.

Cần lưu ý:

1. Class-based proxy thường phải subclass được class target. **Không tạo class scoped bean là `final` hoặc đặt method cần proxy thành `final`** khi dùng TARGET_CLASS, vì CGLIB không thể override.
2. Nếu bean được truy cập ngoài HTTP request phù hợp (ví dụ trong background job), Spring có thể ném lỗi *scope not active*, không thể tìm request/session hiện tại.
3. Cách thay thế là inject `ObjectProvider<ScopedBean>` và chỉ gọi `getObject()` trong request hợp lệ; nó không biến request scope thành global.
4. Đừng giữ lại **target scoped object** hoặc `HttpServletRequest` làm field trong singleton/static/global map sau khi request/session kết thúc.
5. `@Scope("request")` thuần có thể không bật proxy mặc định; khác `@RequestScope` shortcut. Đọc đúng API annotation và proxy mode được cấu hình.

## 6. Application scope, singleton, prototype và dữ liệu dùng chung

### 6.1. `@ApplicationScope`

Bean `@ApplicationScope` có vòng đời theo `ServletContext` của web application. Những request từ các client khác nhau **trong cùng ServletContext** có thể dùng chung instance.

```java
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.ApplicationScope;

@Component
@ApplicationScope
class ApplicationCounter {
    private final AtomicLong total = new AtomicLong();

    long increment() {
        return total.incrementAndGet();
    }
}
```

`AtomicLong` giúp thao tác tăng số nguyên an toàn khi nhiều threads cùng dùng instance trong một JVM. Nó **không** giúp tổng toàn cụm khi hai JVM chạy trên hai nodes độc lập. Để có số đếm toàn cluster, dùng atomic operation trên database/Redis/hệ thống metrics phù hợp.

### 6.2. Singleton không có nghĩa một instance cho toàn internet

`@Service`, `@Component`, `@Controller` thường mặc định singleton:

```java
@Service
class CatalogService {
    // Tốt: phụ thuộc khác được inject và methods không giữ state user.
}
```

Singleton **một instance cho một bean definition trong Spring container**, không phải một instance duy nhất khi có nhiều instances service, pods hoặc JVMs. Đừng đặt trường `String currentUserId` mutable trong singleton controller/service: hai request có thể ghi đè nhau, dẫn tới lộ dữ liệu giữa người dùng.

Thay vào đó, nhận user ID đã xác thực qua tham số/`Principal`, để context theo request/session đúng lifecycle, và lưu state bền vững trong kho phù hợp.

### 6.3. Prototype cũng không đồng nghĩa request scope

`@Scope("prototype")` tạo instance mới **khi Spring container resolve bean**. Nếu một singleton inject prototype trực tiếp vào constructor đúng một lần, singleton sẽ giữ **một prototype instance được inject lúc tạo singleton**. Không có nghĩa mỗi HTTP request hoặc mỗi method call tự có prototype mới.

Nếu cần object mới mỗi lần dùng, gọi `ObjectProvider.getObject()`/factory tại thời điểm thích hợp; nếu cần đúng một object trong mỗi HTTP request, ưu tiên `@RequestScope`.

### 6.4. Dữ liệu ứng dụng chung nên đặt ở đâu?

| Loại dữ liệu | Khuyến nghị |
| --- | --- |
| Config chỉ đọc, object immutable, stateless service | Singleton bean/configuration properties |
| Giá trị mutable dùng chung trong một JVM | Bean application/singleton với concurrency control |
| Cache chung giữa nhiều application instances | Redis/distributed cache hoặc dịch vụ cache phù hợp |
| Dữ liệu nghiệp vụ cần durability và transaction | Database |
| Bộ đếm/metrics hệ thống | Metrics backend, database atomic operation hoặc cơ chế aggregation |
| Giỏ hàng theo user cần tồn tại qua logout/device | Domain storage gắn user ID, không chỉ HttpSession |
| Ngôn ngữ UI chỉ dành cho request hiện tại | LocaleResolver, `Accept-Language` hoặc query/header được xác thực theo contract |
| Tùy chọn ngôn ngữ theo user nhiều request | Session, cookie có chính sách phù hợp hoặc user profile DB |

## 7. Nhiều cơ chế “giữ dữ liệu” khác nhau trong Spring MVC

### 7.1. `@RequestAttribute` vs `@SessionAttribute`

Hai annotation ở **tham số controller** chỉ **đọc thuộc tính**:

```java
@GetMapping("/context")
String context(
        @RequestAttribute(name = "trace", required = false) String trace,
        @SessionAttribute(name = "language", required = false) String language) {

    String left = trace == null ? "none" : trace;
    String right = language == null ? "none" : language;
    return left + ":" + right;
}
```

Đây là method fragment cho controller. `trace` chỉ thuộc request đang xử lý; `language` có thể đến từ session request trước. Annotation không tự khai báo lifecycle của bean và không tự ghi attribute.

### 7.2. `@SessionAttributes` — có chữ “s”, dành cho model workflow

`@SessionAttributes` được đặt **ở class controller**, giúp Spring MVC tự động đẩy một số **model attributes** vào session để dùng cho nhiều bước của form/controller. Nó **khác** `@SessionAttribute` (đọc một key session đã có).

```java
@Controller
@SessionAttributes("draft")
class DraftController {

    @ModelAttribute("draft")
    DraftForm draft() {
        return new DraftForm();
    }

    @GetMapping("/draft")
    String start() {
        return "draft/form";
    }

    @PostMapping("/draft/finish")
    String finish(
            @ModelAttribute("draft") DraftForm draft,
            SessionStatus status) {

        // Lưu draft thành công theo nghiệp vụ trước khi kết thúc.
        status.setComplete();
        return "redirect:/draft/done";
    }
}
```

Đây là **fragment MVC form**, cần kiểu `DraftForm`, template/view và imports do app định nghĩa; không phải chương trình chạy độc lập. `SessionStatus#setComplete()` kết thúc **việc quản lý model attributes được khai báo bởi @SessionAttributes** trong controller, **không invalidate toàn bộ HTTP session** và không xóa mọi attribute khác.

### 7.3. Flash attributes — chỉ dành cho request tiếp theo sau redirect

Trong flow Post-Redirect-Get:

```java
@PostMapping("/preferences")
String save(RedirectAttributes redirects) {
    redirects.addFlashAttribute("notice", "Đã lưu lựa chọn");
    return "redirect:/preferences";
}
```

Flash attribute thường được giữ **tạm thời** trong session bởi `FlashMapManager`, rồi được chuyển vào model của request nhận redirect và bị loại khỏi flash storage. Nó **không phải session attribute sống lâu**. Dùng cho thông báo thành công ngắn, không dùng làm cơ sở dữ liệu.

Nếu dùng `redirects.addAttribute("notice", "...")` thay vì `addFlashAttribute`, dữ liệu có thể được chuyển thành query/path parameter trong URI — phải cân nhắc logging, browser history, URL length và dữ liệu nhạy cảm.

### 7.4. `RequestContextHolder` — context gắn với thread

`RequestContextHolder` có thể cấp `RequestAttributes` của request hiện tại theo cơ chế thread-bound:

```java
RequestAttributes attributes = RequestContextHolder.currentRequestAttributes();
Object traceId = attributes.getAttribute("traceId", RequestAttributes.SCOPE_REQUEST);
```

Đoạn này là **fragment**, cần import `org.springframework.web.context.request.RequestAttributes` và `RequestContextHolder`. Nó không phải kho dữ liệu toàn ứng dụng và có thể ném exception nếu thread hiện tại không có request context. `@Async`, custom executor và `CompletableFuture` không tự đảm bảo chuyển context sang thread khác. Tránh thiết kế service phụ thuộc sâu vào thread-local web context; truyền dữ liệu cần thiết qua tham số rõ ràng khi có thể.

## 8. Ứng dụng Spring Boot 3.x + Java 17: quan sát cả ba scope

Ứng dụng dưới đây minh họa đồng thời:

1. `@RequestScope`: cùng request nhận cùng mã ID; request mới có ID khác.
2. `@SessionScope`: lựa chọn ngôn ngữ và lượt xem tồn tại khi reuse cùng HTTP session.
3. `@ApplicationScope`: bộ đếm chung cho những request đến **một ServletContext**.
4. `@RequestAttribute`: giá trị do Servlet Filter cung cấp.
5. `@SessionAttribute`: đọc key đã được lưu trực tiếp vào Servlet session.

Sử dụng **Spring Boot 3.x / Spring Framework 6.x trên Servlet MVC**. `spring-boot-starter-web` mang Tomcat và MVC thông dụng; ứng dụng không cần Redis hay database.

### 8.1. Dependencies

Với dự án Gradle đã có Boot plugin, dependency management, repositories và Java toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **mảnh cấu hình `build.gradle`**, không phải file build độc lập. Không dùng `javac` trực tiếp không classpath cho project này; chạy thông qua Gradle/Maven của Spring Boot.

### 8.2. Một file Java chứa application, beans và controller

Tạo **`src/main/java/demo/scope/ScopeApplication.java`**:

```java
package demo.scope;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.SessionAttribute;
import org.springframework.web.context.annotation.ApplicationScope;
import org.springframework.web.context.annotation.RequestScope;
import org.springframework.web.context.annotation.SessionScope;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ScopeApplication {

    public static void main(String[] args) {
        SpringApplication.run(ScopeApplication.class, args);
    }

    @Bean
    OncePerRequestFilter serverTagFilter() {
        return new OncePerRequestFilter() {
            @Override
            protected void doFilterInternal(
                    HttpServletRequest request,
                    HttpServletResponse response,
                    FilterChain chain) throws ServletException, IOException {

                // Được đặt bởi phía server, không đọc từ header do client tự khai.
                request.setAttribute("serverTag", "from-filter");
                chain.doFilter(request, response);
            }
        };
    }
}

@Component
@RequestScope
class RequestMarker {
    private final String id = UUID.randomUUID().toString();

    String getId() {
        return id;
    }
}

@Component
@SessionScope
class SessionPreferences {
    private String language = "vi";
    private int visits;

    synchronized String getLanguage() {
        return language;
    }

    synchronized void setLanguage(String language) {
        this.language = language;
    }

    synchronized int nextVisit() {
        return ++visits;
    }
}

@Component
@ApplicationScope
class ApplicationCounter {
    private final AtomicLong total = new AtomicLong();

    long next() {
        return total.incrementAndGet();
    }
}

@RestController
@RequestMapping("/api/scope")
class ScopeController {
    private final RequestMarker requestMarker;
    private final SessionPreferences preferences;
    private final ApplicationCounter counter;

    ScopeController(
            RequestMarker requestMarker,
            SessionPreferences preferences,
            ApplicationCounter counter) {
        this.requestMarker = requestMarker;
        this.preferences = preferences;
        this.counter = counter;
    }

    @GetMapping("/request")
    Map<String, String> requestInfo(
            @RequestAttribute("serverTag") String tag) {

        return Map.of(
                "first", requestMarker.getId(),
                "second", requestMarker.getId(),
                "tag", tag);
    }

    @GetMapping("/session")
    Map<String, Object> sessionInfo() {
        return Map.of(
                "language", preferences.getLanguage(),
                "visits", preferences.nextVisit());
    }

    @PostMapping("/session/language")
    Map<String, String> setLanguage(
            @RequestParam String language,
            HttpSession session) {

        if (!language.equals("vi") && !language.equals("en")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "Unsupported language");
        }

        preferences.setLanguage(language);
        session.setAttribute("uiLanguage", language);
        return Map.of("language", language);
    }

    @GetMapping("/session/raw")
    Map<String, String> rawSessionAttribute(
            @SessionAttribute(name = "uiLanguage", required = false)
            String language) {

        return Map.of(
                "language", language == null ? "not-set" : language);
    }

    @PostMapping("/session/end")
    ResponseEntity<Void> endSession(HttpServletRequest request) {
        HttpSession current = request.getSession(false);
        if (current != null) {
            current.invalidate();
        }
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/application")
    Map<String, Long> applicationInfo() {
        return Map.of("total", counter.next());
    }
}
```

**Đây là một file Java 17 hợp lệ khi đặt trong dự án Boot 3 nêu trên:** chỉ `ScopeApplication` có modifier `public`; các beans/controller khác không public và cùng package `demo.scope`. Spring Boot component scan từ package này tìm được cả ba `@Component` và `@RestController`.

Giải thích luồng:

- `ScopeController` là singleton mặc định và giữ các **proxy** được inject cho request/session/application scoped beans.
- `GET /api/scope/request` gọi `requestMarker.getId()` hai lần trong cùng request, nên `first` và `second` bằng nhau. Request sau được request-scoped target khác, nên ID khác (UUID không có cam kết tuyệt đối về uniqueness, nhưng trùng ngẫu nhiên thực tế rất khó).
- Servlet Filter đặt `serverTag`; `@RequestAttribute("serverTag")` đọc đúng attribute. Nếu controller chạy qua pipeline không có filter và thuộc tính bắt buộc vắng, request có thể lỗi binding.
- `GET /api/scope/session` dùng `@SessionScope` bean của session hiện tại và tăng số lượt xem. Client mới có language mặc định `vi` và lượt xem ban đầu `1`.
- `POST /api/scope/session/language` ghi cùng lựa chọn vào hai nơi **chỉ để đối chiếu API**: field của `@SessionScope` bean và key `uiLanguage` trong `HttpSession`. Chúng là hai cơ chế khác nhau, không tự đồng bộ nếu một bên đổi độc lập.
- `GET /api/scope/session/raw` dùng `@SessionAttribute(required=false)` để đọc riêng attribute `uiLanguage`. Với session mới chưa có key, trả `not-set`; không dùng endpoint này để buộc tạo session.
- `POST /api/scope/session/end` invalidate session đã tồn tại, trả **204 No Content**. Không sử dụng proxy session bean sau khi invalidate trong cùng method.
- `GET /api/scope/application` tăng bộ đếm thuộc `ServletContext` hiện tại. Các client khác nhau có thể nhìn giá trị tăng chung; không có cơ sở dữ liệu nên restart hoặc node khác có bộ đếm riêng.

**Không áp dụng lựa chọn ngôn ngữ tự động cho `MessageSource` trong ví dụ này.** Field `language` chỉ là chuỗi lưu state demo. Muốn điều khiển localization thật, cần tích hợp `LocaleResolver`/`LocaleChangeInterceptor` hoặc giải pháp i18n phù hợp; xem phần 12.

### 8.3. Quan sát bằng curl và cookie jar

Chạy dự án:

```bash
./gradlew bootRun
```

Hai request không cần session:

```bash
curl -sS 'http://localhost:8080/api/scope/request'
curl -sS 'http://localhost:8080/api/scope/request'
```

Body minh họa (UUID khác nhau theo từng request):

```json
{"first":"<uuid-A>","second":"<uuid-A>","tag":"from-filter"}
```

Dòng JSON trên là **sơ đồ giá trị**, dấu `<uuid-A>` không phải UUID thực tế. Lần tiếp theo `first` và `second` sẽ chứa UUID B khác A. **Không thể công bố stdout cụ thể** cho UUID sinh ngẫu nhiên trước khi chạy.

Dùng cookie jar để giữ cùng session:

```bash
curl -i -c session-a.txt \
  'http://localhost:8080/api/scope/session'

curl -i -b session-a.txt -c session-a.txt \
  -X POST \
  -d 'language=en' \
  'http://localhost:8080/api/scope/session/language'

curl -sS -b session-a.txt \
  'http://localhost:8080/api/scope/session'

curl -sS -b session-a.txt \
  'http://localhost:8080/api/scope/session/raw'
```

Body phản hồi theo thứ tự, nếu server mới và không có client khác chạm vào cùng session:

```json
{"language":"vi","visits":1}
{"language":"en"}
{"language":"en","visits":2}
{"language":"en"}
```

JSON key order có thể khác, không thuộc hợp đồng. `-c session-a.txt` lưu cookie do server trả; `-b session-a.txt` gửi cookie đó trong request tiếp. Không gửi cookie từ session A thì request mới không mặc nhiên dùng session A.

Tạo session của client B qua cookie jar khác:

```bash
curl -i -c session-b.txt \
  'http://localhost:8080/api/scope/session'
```

Giá trị mong đợi (session B chưa từng được dùng): `{"language":"vi","visits":1}`, độc lập với session A. Không commit các file `session-a.txt` / `session-b.txt` vào repository: chúng chứa session identifier nhạy cảm.

Kết thúc session A:

```bash
curl -i -b session-a.txt \
  -X POST \
  'http://localhost:8080/api/scope/session/end'
```

Kỳ vọng status **204 No Content**. Sau đó session ID cũ không còn hợp lệ; request tiếp với cookie cũ có thể tạo session mới nếu endpoint cần session, tùy container và cấu hình cookie. Không dựa vào việc server “tự giữ” lại dữ liệu sau invalidate.

## 9. Test MockMvc để chứng minh request/session/application scope

Trong dự án trên, thêm file **`src/test/java/demo/scope/ScopeApplicationTests.java`**:

```java
package demo.scope;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ScopeApplicationTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper; // Jackson 2 của baseline Spring Boot 3.

    @Test
    void requestTargetReusedWithinOneRequestButNotTheNext()
            throws Exception {

        MvcResult first = mvc.perform(get("/api/scope/request"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.tag").value("from-filter"))
                .andReturn();

        MvcResult second = mvc.perform(get("/api/scope/request"))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode a = mapper.readTree(
                first.getResponse().getContentAsString());
        JsonNode b = mapper.readTree(
                second.getResponse().getContentAsString());

        assertEquals(a.get("first").asText(), a.get("second").asText());
        assertEquals(b.get("first").asText(), b.get("second").asText());
        assertNotEquals(a.get("first").asText(), b.get("first").asText());
    }

    @Test
    void sessionStateSurvivesOnlyWhenSameSessionIsReused()
            throws Exception {

        MvcResult first = mvc.perform(get("/api/scope/session"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.visits").value(1))
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                first.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/api/scope/session/language")
                        .session(session)
                        .param("language", "en"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"));

        mvc.perform(get("/api/scope/session").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"))
                .andExpect(jsonPath("$.visits").value(2));

        mvc.perform(get("/api/scope/session/raw").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("en"));

        // Request không tái sử dụng session cũ -> state riêng.
        mvc.perform(get("/api/scope/session"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("vi"))
                .andExpect(jsonPath("$.visits").value(1));
    }

    @Test
    void unknownSessionAttributeIsOptional() throws Exception {
        mvc.perform(get("/api/scope/session/raw"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.language").value("not-set"));
    }

    @Test
    void invalidSessionChoiceReturns400() throws Exception {
        mvc.perform(post("/api/scope/session/language")
                        .param("language", "unknown"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void applicationCounterIsSharedInsideTheWebApp()
            throws Exception {
        mvc.perform(get("/api/scope/application"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").isNumber());

        mvc.perform(get("/api/scope/application"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.total").isNumber());
    }

    @Test
    void sessionCanBeInvalidated() throws Exception {
        MvcResult first = mvc.perform(get("/api/scope/session"))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession session = (MockHttpSession)
                first.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(post("/api/scope/session/end").session(session))
                .andExpect(status().isNoContent());
        // Không tái sử dụng MockHttpSession đã bị invalidate.
    }
}
```

Chạy:

```bash
./gradlew test
```

Với **Spring Boot 3.x**, `spring-boot-starter-web`, `spring-boot-starter-test` và code đúng như phần 8, **sáu test được thiết kế để pass**. Đây là kỳ vọng sau rà soát, **không phải kết quả Gradle đã chạy thực tế**.

Giải thích một số assertions:

- Hai lời gọi `getId()` trong **cùng HTTP request** trả cùng một ID; request thứ hai nhận marker mới. UUID khác nhau là hành vi thực tế kỳ vọng trong test mẫu.
- Trong `MockMvc`, `.session(session)` gửi lại cùng `MockHttpSession` giữa nhiều request. **Không** tái sử dụng instance session thì request mới có state độc lập.
- `@SessionScope` tự xác định target bean qua request/session. Test không dựa vào Java static variables hay field của controller để giả lập session.
- `@SessionAttribute(required=false)` trả fallback khi key chưa tồn tại.
- Counter application được test ở mức output là số; một suite nhiều test hoặc có requests song song không nên assert tổng tuyệt đối bắt đầu từ 1.
- Test invalidate tránh dùng lại session đã bị đánh dấu invalid; nếu muốn kiểm tra hậu quả, hãy gửi request với session mới.

**Giới hạn:** `MockMvc` không kiểm tra browser cookie flags, network proxy, Redis, cluster, multiple JVMs hoặc lỗi serialize/deserialization session. Những đặc tính đó cần integration tests ở môi trường phù hợp. Test dùng `ObjectMapper` từ Jackson 2 vì baseline là Boot 3; Boot 4 chuyển đường JSON mặc định sang Jackson 3 `JsonMapper`, nên chính imports/test mapper cần rà soát khi migrate.

## 10. Request, session và application khi có nhiều threads đồng thời

### Request scope thường tách theo request, nhưng đừng nhầm với thread-safety tuyệt đối

Mỗi request có request-scoped bean riêng theo lifecycle. Trong xử lý đồng bộ thông thường, dữ liệu này không bị chia sẻ ngẫu nhiên giữa hai HTTP requests. Tuy nhiên, một request có thể có async dispatch/callback; framework và code cần quản lý context đúng, không tự giả định “request luôn chạy một thread duy nhất” trong mọi mô hình.

Nếu chuyển công việc sang executor, đừng giữ reference `HttpServletRequest` hoặc dựa vào `RequestContextHolder` trên worker thread không có context. Hãy lấy dữ liệu cần thiết trước rồi truyền immutable value hoặc context carrier đã thiết kế rõ ràng.

### Session scope có thể bị nhiều request truy cập cùng lúc

Hai tab hoặc nhiều HTTP calls của cùng browser có thể gửi request **đồng thời** với cùng session ID. Vì vậy:

```text
Session S-A có cartQuantity = 0

Request 1: đọc 0 ------+
                       +---- cùng ghi 1
Request 2: đọc 0 ------+

Kết quả có thể là 1 thay vì 2 nếu dùng read-modify-write không đồng bộ.
```

`HttpSession` **không tự biến object mutable bên trong thành thread-safe**. Các giải pháp:

- Dùng immutable value + cập nhật qua cơ chế atomic thích hợp.
- Với state tạm trong một JVM, khóa phù hợp hoặc atomic counter; đánh giá contention và lifecycle.
- Với cluster/Redis/DB, dùng transaction, optimistic locking, compare-and-set, atomic increments, database constraints hoặc chiến lược consistency phù hợp.
- Không đồng bộ bằng `synchronized(this)` của một scoped bean rồi mặc định nó có hiệu lực **trên nhiều nodes**.
- Không giữ session lock trong lúc gọi API bên ngoài chậm nếu không cần; có thể khiến các request của cùng user bị giữ lại quá lâu.

### Application scope và singleton càng phải chú ý concurrency

Dữ liệu dùng chung cho tất cả requests trong cùng instance chịu cạnh tranh nhiều hơn. Chẳng hạn một `HashMap` mutable đặt vào singleton không an toàn cho concurrent writes; dùng `ConcurrentHashMap` khi cần, và đồng thời nghĩ tới atomicity của cả thao tác nghiệp vụ.

**Scope quyết định “ai nhìn thấy cùng object”**, không quyết định “object tự đồng bộ” hoặc “dữ liệu được lưu bền vững”.

## 11. Session timeout, cookies, security và privacy

### 11.1. Cấu hình session trong Spring Boot Servlet

Một số properties thông dụng của Spring Boot Servlet:

```properties
# Ví dụ: session không hoạt động trong khoảng thời gian này sẽ hết hạn
server.servlet.session.timeout=30m

# Cookie session chỉ truyền trên HTTPS (triển khai phải dùng HTTPS thật)
server.servlet.session.cookie.secure=true

# Hạn chế JavaScript đọc cookie session
server.servlet.session.cookie.http-only=true

# Điều chỉnh cross-site cookie policy theo use case
server.servlet.session.cookie.same-site=lax
```

Đây là **một cấu hình mẫu**, không tự bật mọi setting trong môi trường có HTTP plaintext hoặc cross-site frontend. Cookie `Secure` cần kết nối HTTPS ở phía client; nếu bật trên môi trường local chỉ dùng HTTP, việc browser lưu/gửi cookie có thể khác kỳ vọng. `SameSite=None` thường cần `Secure` và phải đánh giá CSRF/CORS/authentication kỹ.

`server.servlet.session.timeout` là session inactivity timeout cấu hình; session có thể chấm dứt sớm do logout, invalidate, backend store failure hoặc thay đổi policy. Với Spring Session backend bên ngoài, TTL và timeout handling còn phụ thuộc cơ chế save/expiration của repository.

### 11.2. Session ID là bearer credential cần bảo vệ

- Session ID nên khó đoán, được truyền qua HTTPS và được quản lý qua cookie policy phù hợp.
- Tránh đưa session ID vào URL/query string, access logs, analytics, Referer hoặc screenshots.
- Chống **session fixation** khi đăng nhập; với Spring Security, dùng cơ chế session fixation protection do framework cung cấp theo phiên bản/cấu hình.
- Nếu dựa vào cookies cho authenticated form/actions, bảo vệ **CSRF**. `SameSite` có thể hỗ trợ nhưng không thay thế mọi lớp phòng thủ phù hợp.
- Đăng xuất cần xóa authentication state và kết thúc/revoke session theo chính sách; chỉ xóa một key ngôn ngữ không đăng xuất người dùng.
- Không lưu mật khẩu plaintext, refresh token thô, PII thừa hoặc object rất lớn trong session.
- Session bean/attribute có thể chứa object nội bộ không serializable; điều này gây lỗi khi clustering hoặc persist sessions. Kiểm tra thiết kế serialization/schema trước khi dùng store ngoài.

### 11.3. Session state không thay thế phân quyền

Một request mang cookie session hợp lệ chưa chứng minh endpoint được phép thay đổi mọi tài nguyên. Authorization cần dựa trên identity/principal đáng tin và kiểm tra quyền đối với tài nguyên cụ thể. Đừng chấp nhận tham số `userId` rồi truy cập state/session của người dùng khác chỉ theo ID đó.

Một số kiến trúc REST API không dùng server-side session mà dùng token đã xác minh theo từng request. **Stateless authentication** không đồng nghĩa ứng dụng hoàn toàn không có state: domain data vẫn nằm trong DB/cache; token cũng có thời hạn và chính sách revoke tùy yêu cầu.

## 12. Trạng thái ngôn ngữ: khi nào dùng session, locale và user profile?

Lựa chọn language là ví dụ dễ học về state nhưng có nhiều thiết kế hợp lệ.

### 12.1. Chỉ dùng ngôn ngữ client yêu cầu cho mỗi request

Client gửi `Accept-Language`, server dùng một cơ chế locale resolution thích hợp. Trong Spring MVC, `LocaleResolver`, `LocaleContextResolver` và `LocaleContextHolder` có vai trò với i18n. Khi không cần nhớ lựa chọn thủ công, dùng ngôn ngữ theo request/header là phù hợp.

```http
GET /products HTTP/1.1
Accept-Language: vi-VN,vi;q=0.9,en;q=0.7
```

Header do client gửi không bắt buộc được ứng dụng chấp nhận nguyên vẹn: cấu hình locale resolver, supported locales và fallback policy quyết định ngôn ngữ được chọn.

### 12.2. Người dùng chọn ngôn ngữ một lần cho session

Nếu UI có lựa chọn trong session, `@SessionScope`/`HttpSession` có thể nhớ language và dùng để cấu hình locale của các request sau. Nhưng **chỉ lưu chuỗi "en" trong `SessionPreferences` không tự khiến Spring MessageSource render tiếng Anh**. Ứng dụng phải tích hợp với `LocaleResolver`/locale change strategy phù hợp.

Không đặt bất kỳ giá trị ngôn ngữ nào từ request vào session mà không whitelist. Khi lựa chọn chỉ hỗ trợ `vi`/`en`, kiểm tra input như ví dụ phần 8.

### 12.3. Sở thích theo user trên nhiều thiết bị

Khi người dùng đăng nhập trên điện thoại và laptop, hai browsers thường có sessions riêng. Muốn cùng ngôn ngữ trên mọi thiết bị, nên lưu preference theo user ID trong DB và đưa vào locale selection sau authentication. Session có thể cache preference hiện tại nhưng không là nguồn dữ liệu bền vững.

## 13. Hệ thống nhiều instance: tại sao session có thể “mất” khi scale?

Khi triển khai hai pods:

```text
Load balancer
     |
     +---- App A (JVM A) -> HttpSession local A
     |
     +---- App B (JVM B) -> HttpSession local B

Browser gửi JSESSIONID từ App A
request tiếp theo được route sang App B
=> App B không mặc nhiên có session data của App A.
```

Các giải pháp cần cân nhắc:

1. **Sticky sessions** (load balancer giữ cùng client về một node): đơn giản, nhưng khi node lỗi/restart vẫn có thể mất session và mất cân bằng tải.
2. **Shared session store** (ví dụ Spring Session + Redis): thay thế implementation `HttpSession` bằng một backend dùng chung, để A/B có thể đọc cùng session ID.
3. **Database/domain store**: nếu dữ liệu cần bền vững lâu dài, lưu theo user/resource thay vì nhét tất cả vào HTTP session.
4. **Stateless API**: tránh HTTP session cho endpoint thích hợp, truyền authentication/context theo token và truy vấn storage thật.

**Spring Session** cung cấp tích hợp với Servlet `HttpSession` thông qua filter, backend như Redis/JDBC tùy dependency/cấu hình. Khi được thiết lập, code dùng `HttpSession` và nhiều cơ chế session của Spring MVC có thể tiếp tục hoạt động mà ít thay đổi, nhưng phải xử lý:

- Serialization/versioning của session attributes khi rolling deployments.
- TTL, cookie settings, backend availability, memory và chi phí lưu trữ.
- Concurrent writes vào cùng session và chiến lược lưu/flush.
- Thay đổi thiết kế ứng dụng để không chứa graph object quá lớn hoặc không serializable trong session.
- Observability và disaster recovery cho session store.

Ví dụ **mảnh dependency Boot 3** khi thật sự cấu hình Redis-backed sessions (không thêm vào project demo phần 8 nếu không có Redis):

```groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Trong project sử dụng Spring Boot BOM và auto-configuration phù hợp, còn cần cấu hình kết nối Redis và các session settings theo version. Đây không phải cấu hình Redis hoàn chỉnh. **Không coi “thêm dependency” là đủ chứng minh state đã chia sẻ an toàn qua nhiều node**; phải có integration tests kiểm tra hai app instances dùng chung Redis/session store.

Spring Session 4.x đi cùng thế hệ Spring Framework 7 / Boot 4, còn Boot 3.x thường sử dụng Spring Session 3.x do BOM quản lý. Không hardcode hai major không tương thích.

## 14. Khi nào nên tránh session?

Session có ích, nhưng không luôn là cách tốt nhất:

- **API stateless cần scale ngang:** request độc lập; server lấy state domain từ DB/cache với khóa user/resource.
- **Các tác vụ dài hoặc queue jobs:** trạng thái job phải có identity và persistence riêng, không biến session thành job repository.
- **Dữ liệu lớn:** lưu identifier và truy vấn DB/cache có thể hợp lý hơn sao chép cả danh sách entity vào session.
- **Thông tin toàn ứng dụng:** dùng configuration/singleton/cache chung, không nhân bản trong mỗi session.
- **Tùy chọn dài hạn:** lưu user preference bền vững; session chỉ là cache tạm.
- **Chuyển trạng thái giữa microservices:** dùng request metadata hoặc explicit context, không giả định hai service chia sẻ cùng Servlet `HttpSession` nếu chưa thiết kế.
- **Yêu cầu bí mật và audit:** không lưu thông tin nhạy cảm trong session tùy tiện, cân nhắc tính tuân thủ và quản lý vòng đời dữ liệu.

Một cách chọn nhanh:

| Câu hỏi | Nếu “Có” | Hướng thiết kế |
| --- | --- | --- |
| Dữ liệu chỉ phục vụ request hiện tại? | Có | Method parameter, request attribute, `@RequestScope` |
| Cần dữ liệu trong request kế sau **cùng session**? | Có | `HttpSession`/`@SessionScope`, nếu được phép stateful |
| Chỉ cần thông báo sau redirect? | Có | Flash attributes |
| Cần giữ model qua các bước của cùng wizard controller? | Có | `@SessionAttributes` + `SessionStatus` |
| Mọi người dùng của cùng web app dùng chung? | Có | Singleton/`@ApplicationScope` và bảo vệ concurrent access |
| Mọi node/pods đều phải thấy? | Có | Shared store hoặc distributed coordination |
| Dữ liệu phải còn sau restart/logout hoặc dùng nhiều thiết bị? | Có | Database/domain storage gắn user/resource |
| Đây là identity hay authorization? | Có | Spring Security/principal/permission check chính thức |

## 15. Những lỗi phổ biến cần nhận diện

### Lỗi A — giữ thông tin user trong singleton field

```java
@RestController
class UnsafeController {
    private String currentUserId; // Sai: singleton chia sẻ giữa nhiều request.

    @PostMapping("/select-user")
    String select(@RequestParam String userId) {
        currentUserId = userId;
        return currentUserId;
    }
}
```

Đây là **anti-pattern**, không dùng production. Hai users gửi request đồng thời có thể nhìn state của nhau. Cần identity đã được authenticate theo mỗi request, hoặc store đúng session/user với authorization.

### Lỗi B — tưởng request attribute sẽ qua redirect

```java
request.setAttribute("notice", "Đã lưu");
return "redirect:/summary";
```

Request mới tại `/summary` sẽ không tự có attribute `notice` từ request cũ. Sử dụng `RedirectAttributes.addFlashAttribute("notice",...)` nếu cần một thông báo ngắn cho request sau redirect.

### Lỗi C — inject trực tiếp request/session bean không có proxy vào singleton

Nếu tạo bean bằng `@Scope("session")` thuần, không có scoped proxy hay provider, singleton có thể gặp inactive scope trong lúc khởi tạo hoặc giữ sai object. Với Spring MVC, dùng `@SessionScope`/`@RequestScope` hoặc khai báo `proxyMode` phù hợp.

### Lỗi D — dùng `@SessionAttribute` để mong tự tạo giá trị

`@SessionAttribute("language")` không ghi language khi key chưa tồn tại. Khi `required=true` (mặc định), thiếu attribute là lỗi resolve argument; với optional cho phép logic fallback.

### Lỗi E — nhầm `@SessionAttributes` với `@SessionScope`

`@SessionAttributes("draft")` là marker trên controller class cho **model conversation**, dùng `SessionStatus#setComplete()` để dọn. `@SessionScope` là marker của **bean lifetime**. Chúng giải quyết hai nhu cầu khác nhau.

### Lỗi F — dùng session bean mutable mà không xử lý concurrency

Các request cùng browser/session có thể chạy song song. `private int cartCount; cartCount++;` không bảo đảm atomicity. Dùng giải pháp đồng bộ đúng phạm vi lưu trữ; đặc biệt chú ý Redis/cluster.

### Lỗi G — session timeout/restart làm mất state

Session không phải database. App mới restart, node khác, Redis key hết TTL hoặc user logout đều có thể khiến state biến mất. Với thông tin bền vững, lưu DB đúng contract.

### Lỗi H — session cookie không được gửi

Nếu browser không lưu cookie, `SameSite`/`Secure` sai môi trường, domain/path lệch hoặc CORS credentials không được thiết lập khi cross-origin, request mới có thể không tìm lại session. Kiểm tra `Set-Cookie`, request `Cookie`, scheme HTTPS, devtools và gateway.

### Lỗi I — truy cập scoped bean từ thread background

`@Async`, scheduler hay executor không có HTTP request context mặc định. Truy cập proxy request/session lúc đó có thể gây `ScopeNotActiveException`/“No thread-bound request”. Truyền immutable context qua tham số hoặc lưu trạng thái bền vững ngoài request.

### Lỗi J — coi application scope là cache toàn cluster

`@ApplicationScope` chỉ nằm trong một `ServletContext`. Khi scale hai pods, mỗi pod có instance riêng. Với global state, cần shared storage/cơ chế coordination.

### Lỗi K — tạo session khi chỉ muốn đọc

Dùng `request.getSession()` hay inject `HttpSession` khi lẽ ra chỉ cần “có session cũ hay không” có thể làm tăng số sessions. Sử dụng `getSession(false)` nếu mục tiêu là kiểm tra mà không tạo.

### Lỗi L — bỏ qua bảo mật session

Session ID có thể bị đánh cắp nếu thiếu HTTPS/cookie controls; CSRF có thể ảnh hưởng state-changing endpoints dựa trên cookie; session fixation phải được xử lý khi login. Đừng cho rằng bean có `@SessionScope` tự bảo đảm tính bảo mật.

## 16. Lưu ý khi nâng cấp Spring

| Nền tảng | Khác biệt thực hành |
| --- | --- |
| Spring Framework 5.x + Spring Boot 2.x | Web scopes request/session/application có sẵn; Servlet API thường ở `javax.servlet.*` |
| Spring Framework 6.x + Spring Boot 3.x | Java 17+, Servlet ở `jakarta.servlet.*`; ví dụ chạy phần 8 dùng baseline này |
| Spring Framework 7.x + Spring Boot 4.x | Cơ chế scope bean/HTTP session vẫn có, nhưng starters, Spring Session major version và JSON/test auto-configuration cần kiểm tra theo BOM mới |

`@RequestScope`, `@SessionScope`, `@ApplicationScope` là các annotation cấp Spring bean, không phụ thuộc JSON mapper. Vì vậy việc chuyển Jackson 2 → Jackson 3 khi lên Boot 4 **không tự thay lifecycle của bean scopes**, nhưng code test đọc JSON bằng `ObjectMapper` sẽ cần đổi nếu dự án dùng mapper mặc định Jackson 3.

Trong môi trường **AOT/native image**, khởi tạo bean/proxy/reflection cần được rà soát theo Spring Boot version; constructor/proxy target không tương thích có thể làm build native lỗi dù chạy JVM bình thường. Đừng bỏ qua smoke tests cho request/session scoping sau migration.

## 17. Checklist thiết kế state theo scope

- [ ] Mỗi giá trị có owner rõ: request, HTTP session, ServletContext/Spring context, database hoặc shared cache.
- [ ] Không chứa user-specific mutable state trong singleton controller/service.
- [ ] Session data chỉ dành cho user/session liên quan; không tin user ID tự khai.
- [ ] `@RequestScope` và `@SessionScope` được inject vào singleton qua scoped proxy hoặc provider đúng cách.
- [ ] Không giữ reference đến request object/servlet request ở async worker khi request kết thúc.
- [ ] Các session-scoped mutable objects được kiểm soát concurrent requests; thiết kế lại khi multi-node.
- [ ] Cookies session được bảo vệ bởi HTTPS, Secure/HttpOnly/SameSite phù hợp; authentication, CSRF và session fixation được xử lý.
- [ ] Đọc session cũ qua `getSession(false)` khi không muốn tạo session mới.
- [ ] Session có timeout, logout/invalidate policy, không lưu secrets/PII không cần thiết.
- [ ] Redirect dùng flash attributes thay cho request attrs để chuyển thông báo một lần.
- [ ] `@SessionAttributes` workflow được kết thúc bằng `SessionStatus#setComplete()`.
- [ ] Dữ liệu cần sau restart hoặc chia sẻ nhiều thiết bị được lưu vào DB.
- [ ] Dữ liệu cần qua nhiều nodes dùng shared store/cơ chế nhất quán.
- [ ] Có tests cho hai HTTP requests khác nhau, hai sessions khác nhau và request trùng session.
- [ ] Không assert counter toàn ứng dụng từ 1 nếu test suite có thể chạy song song hoặc có request khác.

## 18. Bài tập tự đánh giá

1. Một filter tính `traceId`. Hãy chọn giữa `request.setAttribute` + `@RequestAttribute` và `@RequestScope` bean. Cách nào hợp lý khi chỉ có một chuỗi? Cách nào hợp lý nếu cần một request context object có nhiều field?
2. Hai tabs của cùng browser gửi đồng thời `POST /cart/add`. Vì sao `@SessionScope` không bảo đảm `cartCount++` an toàn? Đề xuất giải pháp khi deployment một node và khi có Redis.
3. Thêm endpoint cho xem lựa chọn ngôn ngữ bằng `@SessionAttribute(name="uiLanguage",required=false)`. Khi key không có, có nên gọi `getSession()` để tạo mới không?
4. Trong ứng dụng mẫu, vì sao `requestMarker.getId()` hai lần trên cùng request trả cùng giá trị dù controller là singleton? Điều gì thay đổi khi request tiếp theo đến?
5. Dùng request attribute `notice` rồi redirect sang URL khác. Tại sao mất notice? Hãy sửa bằng `RedirectAttributes.addFlashAttribute` và phân biệt flash với long-lived session attribute.
6. Wizard form ba bước dùng `@SessionAttributes("draft")`: khi hoàn tất, `SessionStatus#setComplete()` có invalidate luôn session dùng để đăng nhập không?
7. Một service singleton có `private String lastUserId` cập nhật sau mỗi request. Dữ liệu có thể leak thế nào? Sửa thiết kế qua identity ở request và domain storage theo user ID.
8. Hai Spring Boot pods dùng local HttpSession, load balancer chuyển request ngẫu nhiên. Điều gì xảy ra với `@SessionScope`? Nêu hai chiến lược xử lý và trade-offs.
9. Người dùng muốn lựa chọn ngôn ngữ xuất hiện trên điện thoại khác sau khi đăng nhập. Vì sao lưu `language` trong session của laptop là chưa đủ? Đưa ra thiết kế DB preference + locale resolution.
10. Mở rộng MockMvc tests: lưu `language=en` ở session A, GET ở session B vẫn `vi`; invalidate session A và xác nhận request mới không thấy `en`.
11. Một `@Async` method gọi `RequestContextHolder.currentRequestAttributes()` và lỗi. Giải thích vì sao không nên “fix” bằng cách chia sẻ request object tùy tiện sang mọi thread.
12. Dữ liệu cấu hình chung cho tất cả users thay đổi mỗi phút. So sánh singleton local cache, `@ApplicationScope` và distributed cache; khi nào cần TTL/invalidation.

## 19. Tài liệu tham khảo chính thức

- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, request, session, application, scoped proxies.
- [Spring Framework 6.2 — Web Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): request/session/application trong nền tảng Spring 6.
- [Spring Framework — `@RequestScope` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/annotation/RequestScope.html): shortcut request scope và scoped proxy.
- [Spring Framework — `@SessionScope` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/context/annotation/SessionScope.html): session bean và proxyMode mặc định.
- [Spring MVC — `@RequestAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestattrib.html): đọc request attributes đã có.
- [Spring MVC — `@SessionAttribute`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattribute.html): đọc attributes đã có trong session.
- [Spring MVC — `@SessionAttributes`](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/sessionattributes.html): giữ model attributes tạm qua nhiều request, `SessionStatus`.
- [Spring MVC — Flash Attributes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/flash-attributes.html): lưu dữ liệu tạm giữa redirect và request kế tiếp.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): session timeout và cookie settings.
- [Spring Session — HttpSession Integration](https://docs.spring.io/spring-session/reference/http-session.html): session storage dùng chung và cách thay thế Servlet HttpSession.
