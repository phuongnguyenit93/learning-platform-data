# Các loại dispatch REQUEST, FORWARD, INCLUDE, ERROR và ASYNC

Trong ứng dụng **Spring Framework Web dùng Spring MVC trên Servlet stack**, một HTTP request có thể đi qua **nhiều lần phân phối (dispatch)** ở tầng Servlet trước khi response hoàn tất. Mỗi lần phân phối được gắn một giá trị thuộc enum `jakarta.servlet.DispatcherType`: `REQUEST`, `FORWARD`, `INCLUDE`, `ERROR` hoặc `ASYNC`.

Đây là **khái niệm của Jakarta Servlet**, không phải tên năm loại HTTP request và cũng không phải năm loại Spring controller. Chúng quyết định cách Servlet container chuyển một request tới Servlet/resource và chọn những Servlet Filter nào chạy trong một lần dispatch. `DispatcherServlet` của Spring MVC là **một Servlet cụ thể** có thể nhận các lần dispatch ấy nếu mapping phù hợp.

Hiểu đúng dispatcher type giúp giải thích vì sao filter có lúc chạy hai lần, có lúc không chạy, vì sao chuyển tiếp phía server khác redirect, vì sao một HTTP 500 không nhất thiết đi qua `ERROR` dispatch, và vì sao async request có thể quay lại `DispatcherServlet` sau khi thread ban đầu đã rời đi.

## 1. Nền tảng: một request có thể có nhiều dispatch

Ví dụ client gửi đúng **một** request:

```http
GET /forward HTTP/1.1
Host: localhost:8080
```

Servlet đích `/forward` dùng `RequestDispatcher.forward(...)` để chuyển cùng request sang `/target`. Về mặt mạng, trình duyệt **không gửi thêm request HTTP** chỉ vì thao tác forward. Nhưng phía container có hai giai đoạn:

```text
Client -- HTTP GET /forward -->
    Servlet container
      └── dispatch REQUEST → Servlet /forward
                               │ RequestDispatcher.forward("/target")
                               ▼
                           dispatch FORWARD → Servlet /target
                                              │
                                              └── response → Client
```

Giá trị `request.getDispatcherType()` đổi theo **lần dispatch đang thực thi**. Không nên nhầm với `request.getMethod()` (`GET`, `POST`...), cũng không nhầm với **thread** hay **URL**. Một dispatch không tương đương một thread; một thread có thể thực hiện các lời gọi dispatch lồng nhau, còn async dispatch có thể xảy ra trên thread khác.

**Ba tầng cần tách:**

| Tầng | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| HTTP | Client yêu cầu phương thức và tài nguyên nào? | `GET /forward` |
| Servlet dispatch | Container đang phân phối request theo tình huống nào? | `DispatcherType.FORWARD` |
| Spring MVC routing | Trong `DispatcherServlet`, handler nào khớp request? | `@GetMapping("/target")` |

Giá trị `DispatcherType` có thể truy vấn bằng `ServletRequest.getDispatcherType()`. Một filter được đăng ký theo những dispatcher type nhất định; container chọn filter có **mapping URL/Servlet khớp** và **dispatcher type khớp** ở từng lần phân phối.

## 2. Bảng phân biệt đủ năm loại

| DispatcherType | Điều gì khởi phát? | Resource tiếp nhận | Đặc điểm cần nhớ |
| --- | --- | --- | --- |
| `REQUEST` | Container tiếp nhận request ban đầu từ client rồi chọn web component | Servlet/resource khớp mapping ban đầu | Là loại đầu tiên của request; **không đồng nghĩa HTTP GET** |
| `FORWARD` | Code server gọi `RequestDispatcher.forward(request,response)` | Resource đích của forward | Chuyển quyền xử lý phía server; URL trên browser không đổi; response cần chưa committed |
| `INCLUDE` | Code server gọi `RequestDispatcher.include(request,response)` | Resource được nhúng vào output caller | Resource được include đóng góp body; không được thay status/header của response bao ngoài |
| `ERROR` | Container thực hiện cơ chế điều phối đến error page đã cấu hình | Error page/handler đích | Xảy ra khi cơ chế error dispatch thực sự được kích hoạt, **không phải mọi status 4xx/5xx** |
| `ASYNC` | Request ở chế độ async được redispatch bằng `AsyncContext.dispatch(...)` hoặc cơ chế framework tương đương | Resource đích của async dispatch | Có thể đến sau khi thread xử lý ban đầu kết thúc; response vẫn đang mở |

**Chính xác về vòng đời:** `ASYNC` chỉ gắn với **lần phân phối lại** khi có dispatch; lời gọi `startAsync()` ban đầu chưa tự biến dispatch đang chạy thành `ASYNC`. Tương tự, `sendError(500)` không làm cho mọi câu lệnh tiếp theo trong servlet hiện tại tức thì thấy `ERROR`; cơ chế error page của container quyết định bước điều phối tới resource lỗi.

Các ví dụ trong bài sử dụng Spring Boot 3.x/Spring MVC với các API Jakarta (`jakarta.servlet.*`), phù hợp Spring Framework 6.x. Dự án Spring 5.x cũ thường dùng `javax.servlet.*`; không trộn hai namespace.

## 3. REQUEST — lần vào ban đầu

Khi browser hoặc HTTP client gửi request trực tiếp tới web application, Servlet container thực hiện **REQUEST dispatch** ban đầu. Ví dụ:

```java
@Override
protected void doGet(HttpServletRequest request,
                     HttpServletResponse response)
        throws IOException {
    response.setContentType("text/plain;charset=UTF-8");
    response.getWriter().print(request.getDispatcherType());
}
```

Nếu servlet được map tới `/direct` và client gọi `GET /direct` bình thường, body là:

```text
REQUEST
```

`GET`, `POST`, `PUT` vẫn là **HTTP method**, trong khi `REQUEST` là **dispatcher type**. Nếu cùng servlet hỗ trợ `POST`, một HTTP POST ban đầu cũng có dispatcher type `REQUEST`.

Mặc định chuẩn khi khai báo Servlet filter mapping **không chỉ rõ dispatcher types** bằng `web.xml` là `REQUEST`. Tuy nhiên các API đăng ký và framework có thể đặt dispatcher types riêng, vì vậy muốn biết filter thực sự chạy ở đâu phải xem cấu hình đã đăng ký tại runtime.

Spring MVC `DispatcherServlet` tiếp nhận dispatch `REQUEST` nếu mapping của nó trúng URL. Các `HandlerMapping`/`HandlerAdapter` bên trong mới tìm và gọi controller. `REQUEST` không có nghĩa tất cả request đều vào `DispatcherServlet`: có URL do Servlet khác hoặc resource mặc định xử lý.

## 4. FORWARD — chuyển quyền xử lý hoàn toàn phía server

### 4.1. Cơ chế

Một Servlet có thể chuyển sang Servlet/JSP/resource khác thuộc web application bằng:

```java
RequestDispatcher dispatcher =
        request.getRequestDispatcher("/target");
dispatcher.forward(request, response);
```

`/target` là đường dẫn của resource trong context web application theo cách lấy dispatcher trên `ServletRequest`. Container thực hiện dispatch có type **FORWARD** tới resource đích. Caller cần thực hiện forward trước khi response committed; nếu đã committed, `forward()` có thể ném `IllegalStateException`. Nội dung còn trong response buffer chưa committed bị dọn trước khi forward.

Request/response tiếp tục được chuyển phía server (có thể thông qua wrapper). Các request attributes có thể đi cùng request. Đích nhìn thấy thông tin path theo ngữ nghĩa forward và có thể truy cập thông tin request gốc qua các thuộc tính do Servlet specification quy định như `jakarta.servlet.forward.request_uri`.

### 4.2. Forward khác redirect

**Forward:** một request HTTP bên ngoài; browser vẫn hiển thị URL ban đầu. Đích render/xử lý trong server:

```text
Browser GET /old → server forward("/new") → target /new → response
Browser URL: /old
```

**Redirect:** server trả HTTP status 3xx kèm `Location`; client **có thể gửi request mới** tới URL mới:

```http
HTTP/1.1 302 Found
Location: /new
```

```text
Browser GET /old → response 302 → Browser GET /new → new REQUEST dispatch
Browser URL sau điều hướng: /new
```

Một request HTTP mới sau redirect là một **REQUEST dispatch mới** ở server đích, không phải `FORWARD` của request cũ. Đừng dùng redirect thay forward khi cần giữ request attributes; chúng không tự được chuyển sang HTTP request mới.

Trong Spring MVC với controller phục vụ view, có thể thấy:

```java
@GetMapping("/old")
String oldPage() {
    return "forward:/new";
}
```

Đây là **đoạn minh họa** trong MVC controller dùng cơ chế view resolution phù hợp. `forward:` được hiểu như chỉ dẫn forward cho view, không phải một HTTP redirect. Trong `@RestController`, chuỗi trả về thông thường là response body, nên không thể mặc định `"forward:/new"` ở đó sẽ thực hiện forward.

### 4.3. Filter/interceptor ở forward

Một filter map chỉ `REQUEST` có thể chạy ở `/old` nhưng **không chạy thêm cho FORWARD** tại `/new`. Muốn quan sát/bảo vệ cả đích forward, mapping filter cần bao gồm `FORWARD` và khớp resource đích. Nhưng việc thêm `FORWARD` có thể khiến một request đi qua cùng filter nhiều lần; logic ghi audit, rate limit hay mutation cần biết có muốn mỗi dispatch hay mỗi logical HTTP request.

**Tính đúng đắn bảo mật:** không chỉ dựa vào việc “đường dẫn không thể gọi trực tiếp” để bảo vệ resource. Khi filter auth có dispatcher mapping khác nhau, phải đánh giá cả request trực tiếp lẫn forward và điểm kiểm tra authorization thực tế.

## 5. INCLUDE — nhúng output của resource khác

### 5.1. Cơ chế

Servlet A đang tạo response nhưng muốn thêm output do Servlet/JSP B sinh ra:

```java
response.getWriter().print("Trước|");
request.getRequestDispatcher("/fragment")
       .include(request, response);
response.getWriter().print("|Sau");
```

Khi servlet `/fragment` được gọi trong `include(...)`, dispatcher type của nó là **INCLUDE**. Giả sử `/fragment` in `Giữa`, body của response cuối có thể là:

```text
Trước|Giữa|Sau
```

Khác với forward, caller A **tiếp tục** sau khi phần include trả về. Resource được include chủ yếu đóng góp nội dung cho response; nó **không được thay đổi HTTP status hoặc response headers** của response bên ngoài. Những lời gọi thay status/header trong included resource bị container bỏ qua theo quy tắc Servlet.

### 5.2. Request path và attributes khi INCLUDE

Có một điểm dễ gây lỗi: trong `INCLUDE`, các path element của request có thể giữ giá trị theo request của caller; thông tin resource được include được biểu diễn qua attributes như:

- `jakarta.servlet.include.request_uri`
- `jakarta.servlet.include.context_path`
- `jakarta.servlet.include.servlet_path`
- `jakarta.servlet.include.path_info`
- `jakarta.servlet.include.query_string`

Chỉ một số attribute có ý nghĩa/phát sinh tùy mapping. Do đó, nếu debug included resource chỉ bằng `request.getRequestURI()`, bạn có thể hiểu sai resource đang xử lý. Quan sát thêm dispatcher type và các include attributes tương ứng.

`INCLUDE` thường xuất hiện khi lắp ghép output trang ở Servlet/JSP. Với API JSON hiện đại, thường dễ hơn nếu code Java gọi service và tự tạo response thống nhất; không nên ép `include` vào mọi API vì việc tổng hợp response có các ràng buộc status/header/body.

### 5.3. Filter trong INCLUDE

Filter chỉ đăng ký `REQUEST` **không mặc nhiên chạy lại** cho included resource. Filter có mapping `INCLUDE` có thể chạy nếu URL/servlet mapping tương ứng khớp. Hãy nhớ response header do included resource đặt sẽ không có hiệu lực; một filter chạy trong include cũng không thể dựa vào việc tự thay header để cung cấp chính sách response bao ngoài.

## 6. ERROR — dispatch đến error page của container

### 6.1. Điều kiện kích hoạt

`ERROR` phát sinh khi **Servlet container chuyển xử lý sang error resource** theo error page mapping, ví dụ khi:

- Servlet gọi `response.sendError(404)` hay `response.sendError(500)` và container dùng cơ chế error page;
- Có exception chưa được xử lý, container thực hiện error handling đã cấu hình.

Ví dụ file `web.xml` theo cách truyền thống:

```xml
<error-page>
    <error-code>500</error-code>
    <location>/errors/internal</location>
</error-page>
```

Khi container thực hiện dispatch đến `/errors/internal`, resource đích thấy `request.getDispatcherType() == DispatcherType.ERROR`. Mã HTTP cuối, body và khả năng còn ghi response phụ thuộc tình huống, thời điểm commit, mapping và container.

**Không được đồng nhất “HTTP 500” với `ERROR` dispatch**. Một controller có thể tự trả:

```java
return ResponseEntity.status(500).body("Không xử lý được");
```

Đây là cách đặt status/body trong pipeline MVC; không mặc định kích hoạt error page dispatch. Tương tự, `@ExceptionHandler` hoặc `@ControllerAdvice` có thể giải quyết exception ngay bên trong `DispatcherServlet`, không cần thêm `ERROR` dispatch. Cơ chế chuẩn của Spring Boot có endpoint `/error` trong một số cấu hình, nhưng phải xác định đường đi thực tế theo ứng dụng.

### 6.2. Error request attributes

Trong error dispatch, container cung cấp metadata để error handler chẩn đoán, thường gồm các thuộc tính chuẩn:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `jakarta.servlet.error.status_code` | HTTP status gắn với error |
| `jakarta.servlet.error.exception` | Exception gây lỗi, nếu có |
| `jakarta.servlet.error.exception_type` | Class của exception, nếu có |
| `jakarta.servlet.error.message` | Thông tin lỗi do container cung cấp |
| `jakarta.servlet.error.request_uri` | URI của request gây lỗi |
| `jakarta.servlet.error.servlet_name` | Servlet liên quan, nếu có |

Mã Java lấy thuộc tính mà không giả định kiểu luôn có:

```java
Object status =
        request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
Object originalUri =
        request.getAttribute(RequestDispatcher.ERROR_REQUEST_URI);
```

Import `jakarta.servlet.RequestDispatcher`. Không trả stack trace, đường dẫn filesystem, token hoặc thông tin nhạy cảm trực tiếp cho client. Ghi log an toàn ở server và cung cấp response lỗi ổn định theo nhu cầu API.

### 6.3. Filter trong ERROR dispatch

Nếu cần audit/error correlation hoặc xử lý request context ở error page, filter phải được map `ERROR` khi mong chờ được gọi trong lần dispatch ấy. Tuy nhiên response có thể đã committed hoặc error processing có thể lồng nhau ở một số container. Không được tự ý thay đổi response status/body từ mọi filter error. Đối với `OncePerRequestFilter`, cần xét cả phương thức `shouldNotFilterErrorDispatch()` và xử lý nested error nếu cần.

## 7. ASYNC — request rời thread ban đầu rồi được dispatch lại

### 7.1. Vòng đời Servlet async

Servlet 3.0+ hỗ trợ async để thread xử lý ban đầu không phải chờ kết quả lâu trên cùng call stack. Khi Servlet/mapping/filter cho phép async, code có thể gọi `startAsync()`:

```text
HTTP request đến
  ↓
REQUEST dispatch vào Servlet
  ↓
startAsync()                         → request được đặt ở chế độ async
  ↓
thread REQUEST trở về container     → response vẫn mở
  ↓
tác vụ nền hoàn tất / dữ liệu sẵn sàng
  ↓
AsyncContext.dispatch("/target")    → ASYNC dispatch
  ↓
Servlet /target hoàn tất response
```

Điểm phân biệt: request đi vào ban đầu vẫn có type **REQUEST**; `startAsync()` chỉ bắt đầu chu kỳ async. `AsyncContext.dispatch(...)` tạo lần phân phối lại type **ASYNC**. Nếu thay bằng `AsyncContext.complete()` thì có thể kết thúc response **không có** redispatch `ASYNC`.

Cơ chế async không có nghĩa “request chắc chắn xử lý trên một thread riêng biệt mãi mãi”. Bộ lập lịch, executor, container và Spring MVC có thể dùng nhiều thread ở các giai đoạn khác nhau. Mọi trạng thái dựa trên `ThreadLocal`, transaction context, MDC/log correlation hoặc security context cần được xử lý theo đúng ranh giới async và chính sách framework; không mặc định chúng tự đi sang thread khác.

### 7.2. ASYNC trong Spring MVC

Khi controller trả về `Callable<T>` hoặc `DeferredResult<T>` trong Spring MVC Servlet stack, framework có thể bắt đầu Servlet async handling, giải phóng thread Servlet ban đầu và **dispatch lại** vào container khi có kết quả. `DispatcherServlet` có thể được gọi lại ở phase `ASYNC` để hoàn tất mapping/serialize và xử lý exception theo pipeline MVC.

Ví dụ minh họa controller Spring MVC:

```java
@RestController
class AsyncGreetingController {

    @GetMapping("/slow-greeting")
    Callable<String> greeting() {
        return () -> "Xin chào từ Callable";
    }
}
```

Đây là **đoạn Spring MVC**, cần import `org.springframework.web.bind.annotation.*` và `java.util.concurrent.Callable`, đặt trong ứng dụng đã có dependency MVC. Nó không phải file Java chạy độc lập bằng `javac` trần.

Trong thực tế, với `Callable`, Spring MVC dùng `AsyncTaskExecutor`; với `DeferredResult`, ứng dụng có thể cung cấp kết quả qua một callback/tác vụ khác. Cần cấu hình executor và timeout phù hợp cho tải thực tế. Trả `Callable` không tự biến I/O blocking thành non-blocking; nếu trong task vẫn gọi I/O blocking, thread chạy task vẫn bị chặn.

**Phân biệt `@Async`** của Spring (kích hoạt gọi method bất đồng bộ qua proxy/executor với điều kiện phù hợp) và **Servlet async dispatch**. Một method gắn `@Async` không tự đảm bảo đã có `DispatcherType.ASYNC` cho HTTP request.

### 7.3. Interceptor trong chu kỳ async

Trong Spring MVC, `AsyncHandlerInterceptor` có callback `afterConcurrentHandlingStarted(...)`. Khi handler bắt đầu async:

- `preHandle(...)` đã có thể chạy ở dispatch ban đầu;
- thay vì `postHandle(...)`/`afterCompletion(...)` của đường đi đồng bộ thông thường, framework gọi `afterConcurrentHandlingStarted(...)` để phần interceptor có cơ hội dọn context thread;
- khi kết quả được dispatch trở lại, framework có thể gọi lại `preHandle`, rồi `postHandle` và `afterCompletion` ở giai đoạn hoàn tất.

Nếu timeout hoặc lỗi mạng làm vòng đời kết thúc mà không có redispatch thông thường, **không mặc định** `afterCompletion`/`postHandle` sẽ được gọi. Dùng callbacks của `DeferredResult`, `WebAsyncManager` và các async processing interceptor phù hợp để xử lý cleanup/thống kê khi cần.

## 8. Filter dispatcher mapping quyết định điều gì chạy lại

Servlet filter chạy ở tầng container, **trước hoặc sau** target Servlet trong filter chain; Spring MVC interceptor chạy **bên trong `DispatcherServlet`** đối với handler mà MVC quản lý. Mỗi lần dispatch, container xây dựng/chọn chain dựa trên dispatcher types và URL/Servlet mapping.

### 8.1. Mapping theo web.xml

Ví dụ muốn filter chạy cho request ban đầu và cho lần forward, nhưng không chạy trong include, error hoặc async:

```xml
<filter-mapping>
    <filter-name>auditFilter</filter-name>
    <url-pattern>/*</url-pattern>
    <dispatcher>REQUEST</dispatcher>
    <dispatcher>FORWARD</dispatcher>
</filter-mapping>
```

Nếu không có `<dispatcher>`, mặc định chuẩn của filter mapping theo deployment descriptor là `REQUEST`. Muốn map `ERROR` hoặc `ASYNC`, cần khai báo phù hợp. Với async còn phải đảm bảo các Servlet/Filter trên đường đi hỗ trợ async (`async-supported`), nếu không việc gọi `startAsync()` có thể thất bại với `IllegalStateException`.

### 8.2. Mapping bằng Java/Spring Boot

Với Spring Boot MVC, có thể đăng ký filter và dispatcher types tường minh bằng `FilterRegistrationBean`:

```java
@Bean
FilterRegistrationBean<MyFilter> myFilter() {
    FilterRegistrationBean<MyFilter> registration =
            new FilterRegistrationBean<>(new MyFilter());

    registration.addUrlPatterns("/*");
    registration.setDispatcherTypes(
            DispatcherType.REQUEST,
            DispatcherType.FORWARD,
            DispatcherType.INCLUDE,
            DispatcherType.ERROR,
            DispatcherType.ASYNC);
    registration.setAsyncSupported(true);
    return registration;
}
```

Đây là **mảnh mã cấu hình minh họa**: cần import `org.springframework.context.annotation.Bean`, `org.springframework.boot.web.servlet.FilterRegistrationBean`, `jakarta.servlet.DispatcherType` và có lớp `MyFilter implements Filter`. Mục 9 cung cấp một dự án đầy đủ.

`setDispatcherTypes(...)` quyết định filter áp dụng ở các dispatch type nào; `setAsyncSupported(true)` nói filter cho phép chu kỳ Servlet async đi qua. **Hai lựa chọn giải quyết hai việc khác nhau**. Chọn đủ năm type không phải luôn tốt nhất: có thể ghi log nhiều lần hoặc áp dụng lại authentication/authorization/response wrapper sai thời điểm.

### 8.3. `OncePerRequestFilter` không bảo đảm “chỉ một lần cho toàn bộ vòng đời HTTP”

Spring cung cấp `OncePerRequestFilter` để hỗ trợ lọc một lần **trong mỗi request dispatch / luồng request đang xử lý theo semantics của class**, dựa trên marker attribute. Một logical request có thể có `REQUEST`, `ASYNC` và `ERROR` dispatch, vì thế không được đọc tên class rồi suy ra toàn bộ HTTP request chỉ chạy filter đúng một lần.

Ở Spring Framework 6.x, mặc định:

- `shouldNotFilterAsyncDispatch()` thường trả `true`: bỏ qua các async dispatch tiếp theo.
- `shouldNotFilterErrorDispatch()` thường trả `true`: bỏ qua error dispatch.
- Có thể override về `false` theo chủ đích để tham gia async/error, **nhưng Servlet filter mapping của container cũng phải bao gồm dispatcher type tương ứng**.
- Trên một số Servlet container, `ERROR` có thể lồng trong `REQUEST`; `doFilterNestedErrorDispatch(...)` là hook riêng khi cần xử lý request/response wrapper đúng cách.

Nếu cần log một **logical HTTP request** đúng một lần, tự xác định policy theo request id hoặc request attribute, đồng thời quyết định có ghi lúc bắt đầu, lúc hoàn tất, hay ở cả hai phase. Nếu cần đếm **mỗi lần dispatch**, đếm theo type thay vì dùng “once” của filter như một quy tắc thống kê nghiệp vụ.

### 8.4. `DispatcherServlet` và Servlet dispatcher type là hai khái niệm riêng

`DispatcherServlet` là Front Controller của Spring MVC; `DispatcherType` là enum của Servlet API. Đúng hoặc sai dispatcher mapping có thể làm filter không chạy trong một forward/error/async dispatch, **ngay cả khi controller Spring MVC xử lý request đúng**.

Một forward có thể đến JSP/Servlet khác và không đi vào controller MVC. Một Servlet ERROR dispatch có thể đến trang lỗi không thuộc `DispatcherServlet`. Tương tự, lỗi đã được `@ExceptionHandler` xử lý bên trong MVC không nhất thiết đi qua ERROR dispatch ở container.

## 9. Thực hành đầy đủ: quan sát cả năm loại bằng một ứng dụng

Ví dụ dùng **Java 17+ và Spring Boot 3.5.7**, `spring-boot-starter-web` (Servlet MVC), chạy với Gradle. Thay vì dựa vào browser hay suy đoán log, chương trình in trực tiếp `request.getDispatcherType()` từ Servlet nhận dispatch và filter. Đây là **ứng dụng Spring Boot dùng Servlet API trực tiếp để minh họa hành vi của Servlet container**, không phải bộ ví dụ controller REST dùng cho thiết kế API production.

### 9.1. Cấu trúc và dependency

Cấu trúc:

```text
dispatch-demo/
  build.gradle
  settings.gradle
  src/main/java/demo/dispatch/DispatchDemoApplication.java
```

`settings.gradle`:

```groovy
rootProject.name = 'dispatch-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Cần có Gradle wrapper hoặc Gradle tương thích cài sẵn. Nếu đã tạo dự án Spring Initializr với cùng dependency và version, giữ file cấu hình của dự án đó rồi thêm lớp Java bên dưới.

### 9.2. Một file Java chạy được khi đủ Spring dependency

`src/main/java/demo/dispatch/DispatchDemoApplication.java`:

```java
package demo.dispatch;

import java.io.IOException;
import java.util.EnumSet;

import jakarta.servlet.AsyncContext;
import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.server.ErrorPage;
import org.springframework.boot.web.server.ErrorPageRegistrar;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;

@SpringBootApplication
public class DispatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }

    @Bean
    ServletRegistrationBean<EntryServlet> entryServlet() {
        var bean = new ServletRegistrationBean<>(
                new EntryServlet(),
                "/direct", "/forward", "/include", "/fail", "/async");
        bean.setName("entry");
        bean.setAsyncSupported(true);
        return bean;
    }

    @Bean
    ServletRegistrationBean<TargetServlet> targetServlet() {
        var bean = new ServletRegistrationBean<>(
                new TargetServlet(), "/target", "/fragment");
        bean.setName("target");
        bean.setAsyncSupported(true);
        return bean;
    }

    @Bean
    ServletRegistrationBean<ErrorServlet> errorServlet() {
        var bean = new ServletRegistrationBean<>(
                new ErrorServlet(), "/error-page");
        bean.setName("errorPage");
        bean.setAsyncSupported(true);
        return bean;
    }

    @Bean
    ErrorPageRegistrar exampleErrorPage() {
        return registry -> registry.addErrorPages(
                new ErrorPage(HttpStatus.INTERNAL_SERVER_ERROR,
                        "/error-page"));
    }

    @Bean
    FilterRegistrationBean<DispatchLogFilter> logFilter() {
        var bean = new FilterRegistrationBean<>(
                new DispatchLogFilter());
        bean.addUrlPatterns("/*");
        bean.setDispatcherTypes(EnumSet.allOf(DispatcherType.class));
        bean.setAsyncSupported(true);
        return bean;
    }

    static final class DispatchLogFilter implements Filter {
        @Override
        public void doFilter(ServletRequest request,
                             ServletResponse response,
                             FilterChain chain)
                throws IOException, ServletException {
            System.out.println("FILTER " + request.getDispatcherType());
            chain.doFilter(request, response);
        }
    }

    static final class EntryServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException, ServletException {
            response.setContentType("text/plain;charset=UTF-8");

            switch (request.getServletPath()) {
                case "/direct" ->
                    response.getWriter().print(
                            "TYPE=" + request.getDispatcherType());

                case "/forward" ->
                    request.getRequestDispatcher("/target")
                           .forward(request, response);

                case "/include" -> {
                    response.getWriter().print("before|");
                    request.getRequestDispatcher("/fragment")
                           .include(request, response);
                    response.getWriter().print("|after");
                }

                case "/fail" ->
                    response.sendError(500);

                case "/async" -> {
                    AsyncContext context = request.startAsync();
                    context.start(() -> context.dispatch("/target"));
                }

                default -> response.sendError(404);
            }
        }
    }

    static final class TargetServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print(
                    "TYPE=" + request.getDispatcherType());
        }
    }

    static final class ErrorServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest request,
                             HttpServletResponse response)
                throws IOException {
            response.getWriter().print(
                    "TYPE=" + request.getDispatcherType());
        }
    }
}
```

**Giải thích các cơ chế ảnh hưởng kết quả:**

- `ServletRegistrationBean` đăng ký các Servlet URL cụ thể trong embedded Servlet container. Spring Boot vẫn có thể cung cấp `DispatcherServlet` cho MVC, nhưng những URL demo này được phục vụ bởi **các Servlet đăng ký riêng**.
- `entryServlet()` tạo entry points `/direct`, `/forward`, `/include`, `/fail`, `/async`.
- `targetServlet()` là đích `/target` hoặc `/fragment`; nó in dispatcher type **tại chính đích**, sau khi container phân phối.
- `ErrorPageRegistrar` định tuyến lỗi status 500 tới `/error-page`, cho phép `ErrorServlet` quan sát `ERROR`. Nếu thay đổi error configuration hoặc có response đã committed, kết quả có thể khác.
- Filter đặt `EnumSet.allOf(DispatcherType.class)` để log **mọi loại dispatch** đi qua URL pattern `/*`; `asyncSupported=true` tránh chặn việc khởi động Servlet async ở đường đi thử nghiệm.
- `context.start(...)` dùng cơ chế async của container để gọi `dispatch("/target")`. Servlet ban đầu không viết body sau khi start async; response được hoàn tất ở đích redispatch.
- Lệnh `System.out.println` trong filter phục vụ quan sát, có thể xen kẽ khi nhiều request đồng thời; không dùng nó làm bằng chứng thứ tự toàn cục giữa các request.

### 9.3. Chạy và đọc kết quả

Từ thư mục dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ở terminal thứ hai, gọi từng URL:

| Lệnh | Response body dự kiến | Ý nghĩa |
| --- | --- | --- |
| `curl -s http://localhost:8080/direct` | `TYPE=REQUEST` | Lần dispatch từ client |
| `curl -s http://localhost:8080/forward` | `TYPE=FORWARD` | Target nhận server-side forward |
| `curl -s http://localhost:8080/include` | `before\|TYPE=INCLUDE\|after` | Caller tiếp tục sau khi include |
| `curl -s http://localhost:8080/fail` | `TYPE=ERROR` | Error page target nhận ERROR dispatch |
| `curl -s http://localhost:8080/async` | `TYPE=ASYNC` | Target nhận async redispatch |

Trong ô response của lệnh `include`, các ký tự gạch dọc thực tế là `|` (bảng Markdown dùng `\|` để escape ký tự phân cột). Với `/fail`, dùng `curl -i` để thấy HTTP **500**; `-s` chỉ im lặng về thanh tiến trình, không thay đổi status.

Ở console ứng dụng, số log filter dự kiến theo **mỗi request đơn lẻ**:

```text
GET /direct   → FILTER REQUEST
GET /forward  → FILTER REQUEST, FILTER FORWARD
GET /include  → FILTER REQUEST, FILTER INCLUDE
GET /fail     → FILTER REQUEST, FILTER ERROR
GET /async    → FILTER REQUEST, FILTER ASYNC
```

Đây là mô hình log kỳ vọng khi ứng dụng được đăng ký đúng và không có can thiệp từ filter khác; dòng thực tế có thể xen kẽ giữa request, và một số container có khác biệt về thời điểm error dispatch. Đừng xem thứ tự chính xác của log giữa nhiều client concurrent là bất biến.

**Thử thách:** đổi mapping của filter từ `EnumSet.allOf(DispatcherType.class)` sang `EnumSet.of(DispatcherType.REQUEST)` rồi chạy lại. Body đích của forward/include/error/async vẫn có thể cho thấy type mới, nhưng filter **không log** các dispatch bổ sung; đó là cách trực tiếp chứng minh filter mapping quyết định việc filter chạy, không quyết định luôn loại dispatch của target.

Sau đó thử cho filter chỉ chạy `REQUEST` và `ASYNC`. Gọi `/async`, quan sát hai lần log. Nếu bỏ `setAsyncSupported(true)` khỏi filter nằm trên đường request mà servlet gọi `startAsync()`, request có thể thất bại vì toàn bộ chain không cho phép async.

## 10. Trường hợp phức tạp và những giới hạn cần biết

### 10.1. Một request có thể có chuỗi dispatch khác bảng minh họa

Không có quy tắc “một request chỉ có hai dispatch”. Code có thể forward qua nhiều resource, include lồng nhau, error handler có thể được kích hoạt từ đường xử lý khác, và async có thể có nhiều giai đoạn. Servlet specification và container quy định các giới hạn hợp lệ; đừng tạo vòng forward/include vô hạn. Các chu kỳ bất thường dễ dẫn đến lỗi stack, lặp log và khó phân tích.

Nếu mục tiêu là **một lần thực hiện logic nghiệp vụ**, quyết định ở service/transaction/idempotency chứ không dựa duy nhất vào số filter invocations.

### 10.2. Dispatcher type không biểu diễn đầy đủ outcome

`ERROR` chỉ thể hiện một **error-page dispatch**; không bảo đảm status cuối là 500 hoặc exception nào. `ASYNC` chỉ thể hiện redispatch; không bảo đảm tác vụ trước đó thành công. `FORWARD` và `INCLUDE` nói về cách container đưa request tới resource khác; không nói rằng resource đó thuộc Spring MVC.

Muốn chẩn đoán, cần quan sát phối hợp:

- `request.getDispatcherType()`;
- method, URI, servlet path, attributes `jakarta.servlet.forward.*`, `jakarta.servlet.include.*`, `jakarta.servlet.error.*`;
- status response khi hoàn tất;
- Servlet/filter mapping và `asyncSupported`;
- Spring MVC handler mapping, interceptor, exception handler và async callbacks khi request đi qua `DispatcherServlet`.

Không log raw cookie, Authorization header, session ID hoặc dữ liệu nhạy cảm chỉ để debug dispatch.

### 10.3. Filter chạy nhiều lần: chuyện thường gặp

Một số lỗi phát sinh khi filter vô tình giả định chỉ có một dispatch:

1. **Double counting** metric request: `REQUEST` và `ERROR` cùng tăng một counter đại diện cho *một* HTTP request.
2. **Double wrapping** request/response: filter áp dụng wrapper ở `REQUEST` rồi lại xử lý wrapper khác trong `FORWARD`, `INCLUDE` hoặc nested `ERROR`.
3. **Audit duplicate**: một hành động người dùng bị ghi hai bản vì sau `REQUEST` có `ASYNC` redispatch.
4. **MDC/ThreadLocal leak**: context được tạo trên thread ban đầu nhưng không cleanup khi request chuyển async hoặc khi thread container được tái sử dụng.
5. **Authorization gap**: filter chỉ gắn URL hoặc dispatcher type không bao phủ đường tới tài nguyên nhạy cảm.
6. **Status sai trong INCLUDE**: included resource cố set status/header nhưng thay đổi bị bỏ qua.
7. **Lẫn redirect với FORWARD**: client nhận 3xx rồi tạo HTTP request mới, log hiển thị `REQUEST` mới là chính xác.
8. **Hiểu sai 500**: controller trả `ResponseEntity.status(500)` nhưng không có `ERROR` dispatch, vì không đi qua cơ chế error page.

### 10.4. Quy tắc đánh giá thứ tự filter và MVC interceptor

Một cách hình dung:

```text
Servlet container:
    Filter chain đã match dispatcher type
        ↓
    Servlet đang được dispatch tới
        ↓
    nếu là DispatcherServlet của Spring MVC:
        HandlerMapping → HandlerInterceptor → Controller → View/Body
        ↑                                   ↓
        └──────── lifecycle MVC callbacks ─┘
```

Nếu có một `FORWARD` tới resource do MVC quản lý, container có thể xây lại filter chain theo type FORWARD rồi `DispatcherServlet` mới chọn handler khác. Nếu forward đến một JSP hoặc custom Servlet, Spring MVC interceptor của controller **không tự chạy tại đó**.

Đối với async controller, interceptor callback ở dispatch ban đầu và ở async dispatch hoàn tất khác đường đồng bộ, như mục 7.3. Nơi bảo vệ authentication/authorization nên dùng những thành phần bảo mật phù hợp toàn stack thay vì tự giả định mọi Servlet/resource đều đi qua MVC interceptor.

## 11. Checklist thiết kế và tự kiểm tra

**Khi thêm Servlet Filter:**

1. Xác định filter cần xử lý **mỗi HTTP request** hay **mỗi dispatch**.
2. Đăng ký dispatcher types phù hợp (REQUEST, FORWARD, INCLUDE, ERROR, ASYNC).
3. Kiểm tra URL/servlet mapping và thứ tự filter chain.
4. Nếu dùng async, kiểm tra `asyncSupported` trên các thành phần liên quan.
5. Nếu dùng `OncePerRequestFilter`, xác định rõ `shouldNotFilterAsyncDispatch`/`shouldNotFilterErrorDispatch`.
6. Test cả trường hợp thông thường, forward/include, lỗi và async; xác nhận không rò `ThreadLocal` hay nhân đôi metric.

**Tự trả lời:**

1. Tại sao hai request `GET /direct` và `POST /direct` đều có thể là `DispatcherType.REQUEST`?
2. Vì sao `forward("/target")` không đổi URL browser, còn `sendRedirect("/target")` thường dẫn tới REQUEST dispatch mới?
3. Ở `INCLUDE`, vì sao included servlet không thể sửa status/header của response ngoài?
4. Khi controller MVC trả HTTP 500 trực tiếp, vì sao chưa đủ cơ sở nói đã có `ERROR` dispatch?
5. `startAsync()` và `AsyncContext.dispatch(...)` thay đổi vòng đời request khác nhau ở bước nào?
6. Filter mapping chỉ REQUEST có chạy lại trong ASYNC/ERROR không? Phải cấu hình những gì nếu muốn nó chạy?
7. `OncePerRequestFilter` có nghĩa chắc chắn chỉ một lần suốt tất cả dispatch của một HTTP request không?
8. Nếu Spring MVC `Callable` hoàn tất và có redispatch, interceptor cần xử lý cleanup ở giai đoạn nào?
9. Trong ví dụ runnable, vì sao body của `/include` chứa `TYPE=INCLUDE` dù request bên ngoài bắt đầu là `REQUEST`?
10. Vì sao phải phân biệt `DispatcherServlet` với `DispatcherType` khi đọc trace?

**Kết quả cần đạt:** Có thể xác định type của từng dispatch trong một request, dự đoán filter nào tham gia dựa trên dispatcher mapping, chọn `forward`/`include`/`sendError`/`startAsync` đúng mục đích, và giải thích callback của Spring MVC trong chu kỳ async. Đây là nền tảng quan trọng để hiểu luồng xử lý MVC và chẩn đoán những lỗi filter, error page và async khó tái hiện.

## Tài liệu tham khảo

- Jakarta Servlet Specification: https://jakarta.ee/specifications/servlet/6.1/
- Jakarta Servlet API, `ServletRequest.getDispatcherType()`: https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/ServletRequest.html
- Jakarta Servlet API, `RequestDispatcher`: https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/RequestDispatcher.html
- Spring Framework — Asynchronous Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework API — `OncePerRequestFilter`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
