# Filter chain, thứ tự đăng ký và các loại dispatch trong Spring MVC

## 1. Vì sao một filter có thể chạy sai thứ tự hoặc chạy nhiều lần?

Trong ứng dụng Spring MVC chạy trên **Servlet container**, HTTP request đi qua **chuỗi Servlet Filter** trước khi tới `DispatcherServlet`. Filter có thể làm việc trước và sau thành phần kế tiếp, chẳng hạn chuẩn hóa encoding, đọc forwarded headers đã được tin cậy, xác thực, ghi correlation ID hoặc quan sát thời gian xử lý.

Những sự cố phổ biến:

- Filter giải mã body chạy trước filter thiết lập character encoding khiến dữ liệu Unicode bị đọc sai.
- Filter CORS hoặc proxy headers đặt sau Spring Security khiến preflight request bị từ chối hoặc URL được tạo sai.
- Một filter vô tình đăng ký **hai lần**, một lần với Servlet container và một lần trong `SecurityFilterChain`.
- Filter hoạt động với request ban đầu nhưng không chạy khi `forward`, khi Servlet container xử lý lỗi hoặc khi async dispatch hoàn tất.
- Developer nghĩ `OncePerRequestFilter` có nghĩa “chỉ một lần từ lúc request bắt đầu đến mọi dispatch về sau”, trong khi nó bảo đảm theo **mỗi request dispatch trong một request thread**, tùy cấu hình async/error và quy tắc already-filtered.
- Dùng `@Order` cho interceptor rồi mong nó thay đổi thứ tự Servlet Filter.

Bài này giải thích **hai chiều cấu hình độc lập**:

1. **Filter được đăng ký ở đâu, áp dụng trên URL/Servlet nào và ở vị trí nào?**
2. **Filter có tham gia loại Servlet dispatch hiện tại không?**

Sau đó là code Spring Boot 3.x/Java 17+ thực thi được và kiểm thử bằng HTTP qua embedded Servlet container để nhìn thấy thứ tự thật, bao gồm request thông thường và `FORWARD`.

## 2. Servlet Filter chain: mô hình trước/sau

Mỗi Servlet Filter thực hiện `doFilter(request, response, chain)`. Gọi `chain.doFilter(...)` là chuyển tiếp tới filter tiếp theo hoặc đích servlet. Khi lời gọi đó kết thúc, phần code sau nó trong filter hiện tại được thực thi theo chiều **ngược lại**.

```text
Browser
  |
  v
[Filter A] trước chain.doFilter         A-before
  |
  v
[Filter B] trước chain.doFilter         B-before
  |
  v
[Filter C] trước chain.doFilter         C-before
  |
  v
DispatcherServlet -> Spring MVC controller
  |
  v
[Filter C] sau chain.doFilter           C-after
  ^
  |
[Filter B] sau chain.doFilter           B-after
  ^
  |
[Filter A] sau chain.doFilter           A-after
  |
  v
HTTP response
```

Dạng source:

```java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    // Chuẩn bị request, context hoặc wrapper.
    before(request);

    try {
        chain.doFilter(request, response);
    } finally {
        // Dọn tài nguyên, đo duration, clear ThreadLocal...
        cleanup();
    }
}
```

Đây là **fragment của class implements `jakarta.servlet.Filter`**, chưa kèm định nghĩa `before` và `cleanup`; không phải một file Java tự chạy. Ý nghĩa quan trọng của `finally`: cleanup vẫn được thực hiện nếu downstream ném exception. Không phải lúc nào sau `chain.doFilter` cũng còn khả năng **đổi status/headers/body**, vì response có thể đã được commit.

Nếu filter **không gọi `chain.doFilter`**, request dừng tại filter. Điều này hợp lệ khi filter chủ động gửi 401/403/429 hoặc xử lý response hoàn chỉnh, nhưng sai nếu vô tình bỏ qua chain và khiến controller không bao giờ được gọi.

### 2.1. Phân biệt Servlet Filter và MVC interceptor

| Tiêu chí | Servlet `Filter` | Spring MVC `HandlerInterceptor` |
| --- | --- | --- |
| Cấp thực thi | Servlet container/filter chain, trước servlet được nhắm tới | Bên trong `DispatcherServlet` sau khi chọn handler |
| Phạm vi | Có thể áp dụng cho servlet khác, resource, dispatch types theo mapping | Áp dụng cho handler MVC phù hợp |
| Lựa chọn đối tượng | URL patterns, servlet registrations, `DispatcherType` | `InterceptorRegistry`, handler và include/exclude path |
| Thứ tự | Filter registration/order trong container | Thứ tự interceptor được thêm vào chain MVC |
| Bao request/response | Có thể wrap ServletRequest/ServletResponse | Không là Servlet Filter; dùng `preHandle`/`postHandle`/`afterCompletion` |
| Dữ liệu đầu vào | Xử lý ở biên Servlet, phù hợp encoding/security/logging | Phù hợp metadata gắn với handler, đo request MVC |
| Thay thế Security filter? | Spring Security có chain riêng dựa trên Servlet filter | Không đủ để bảo vệ mọi servlet path |

`HandlerInterceptor` không có cơ chế `DispatcherType` mapping tương đương một Servlet Filter đăng ký. Vì vậy đặt logic bảo mật bắt buộc chỉ trong interceptor rồi cho rằng nó bảo vệ toàn bộ application thường không đúng.

## 3. Hai ý nghĩa của từ “chain” khi dùng Spring Security

Trong Spring MVC có thể gặp:

**A. Servlet container filter chain** — Servlet specification sắp xếp các registrations phù hợp với URL, servlet name và dispatcher type.

```text
Request
  |
  v
EncodingFilter
  |
  v
springSecurityFilterChain (DelegatingFilterProxy)
  |
  v
TraceFilter
  |
  v
DispatcherServlet
```

**B. Spring Security `FilterChainProxy` và `SecurityFilterChain`** — nằm **bên trong** filter có tên thông dụng `springSecurityFilterChain`. `FilterChainProxy` chọn một `SecurityFilterChain` khớp request; các security filters trong chain đó có thứ tự riêng.

```text
DelegatingFilterProxy (Servlet filter)
  |
  v
FilterChainProxy
  |
  +-- matching SecurityFilterChain
        |
        +-- SecurityContext...
        +-- Authentication...
        +-- Authorization...
  |
  v
trả về Servlet chain bên ngoài
```

Do đó:

- `FilterRegistrationBean#setOrder(...)` điều chỉnh **vị trí đăng ký Servlet filter**.
- `HttpSecurity#addFilterBefore` / `addFilterAfter` / `addFilterAt` điều chỉnh **vị trí filter bên trong Spring Security filter chain**.
- Hai loại order **không thay thế nhau**. Một filter custom cần tham gia authentication/authorization phải được cấu hình đúng nơi; không đơn giản đặt order số nhỏ để giả làm security filter.
- Nếu filter custom đồng thời là một bean `Filter` mà Boot auto-register với container **và** được thêm vào `HttpSecurity`, nó có thể chạy hai lần. Để tránh double registration, cân nhắc disable Servlet registration cho bean chỉ dành cho Security (xem phần 11).

Bài này không tái triển khai Spring Security; chỉ làm rõ nơi đặt filter và cách xác minh hành vi.

## 4. Các `DispatcherType` của Servlet

`jakarta.servlet.DispatcherType` là enum cho **loại dispatch hiện tại**, không phải HTTP method. Một HTTP request có thể liên quan **hơn một dispatch**.

| `DispatcherType` | Khi nào xuất hiện | Lưu ý quan trọng |
| --- | --- | --- |
| **`REQUEST`** | Request ban đầu được container chuyển tới servlet/đích | Loại phổ biến nhất |
| **`FORWARD`** | Server gọi `RequestDispatcher.forward(...)` hoặc Spring view `forward:...` | Cùng request phía server; URL/servlet target có thể khác |
| **`INCLUDE`** | Server thực hiện `RequestDispatcher.include(...)` | Gộp nội dung resource khác vào response; quy tắc response khác forward |
| **`ASYNC`** | Một async request được redispatch từ async context vào servlet chain | Có thể chạy trên thread khác; không giống một request HTTP client mới |
| **`ERROR`** | Container phân phối tới error page/error handler | Thường đi qua error mapping; có thể có nested error dispatch |

Một filter chỉ chạy trong dispatch nếu **cả hai điều kiện** đúng:

1. Filter registration **map tới resource mục tiêu**: URL pattern/servlet name tương ứng.
2. Registration **bao gồm dispatcher type** hiện tại.

Sau đó, filter code vẫn có thể chủ động bỏ qua request theo đường dẫn, request attributes hoặc logic của `OncePerRequestFilter`. Filter được map `REQUEST` sẽ không tự nhận `ERROR` chỉ vì nó đã thấy request ban đầu.

### 4.1. Ví dụ: request có thể đi qua filter lần thứ hai khi forward

```text
GET /api/demo/forward           dispatcher=REQUEST
       |
       +-- Filter A [REQUEST]    chạy
       +-- Filter B [REQUEST]    chạy
       +-- MVC handler trả "forward:/api/demo/echo"
                         |
                         v
  server FORWARD tới /api/demo/echo      dispatcher=FORWARD
       |
       +-- Filter A [FORWARD]    chạy nếu registration có FORWARD
       +-- Filter B [REQUEST]    KHÔNG chạy ở FORWARD
       +-- MVC handler echo
```

Đây là **server-side forward**, không phải `302/303` redirect. Browser không nhận request URL mới, vì container tự dispatch bên trong. Nếu handler trả `"redirect:/api/demo/echo"` thì client tạo HTTP request mới, dispatcher của request đó thường là **`REQUEST`**, không phải `FORWARD`.

### 4.2. `ERROR` và đường dẫn `/error`

Một sự cố có thể tạo luồng:

```text
GET /api/orders/1 (REQUEST)
   |
  lỗi chưa được xử lý / sendError
   |
Servlet container ERROR dispatch -> /error
   |
BasicErrorController / error view (tùy Spring Boot)
```

**Filter muốn thấy `ERROR` phải đăng ký `DispatcherType.ERROR` và mapping phải khớp đích error dispatch.** Ví dụ filter map chỉ `/api/orders/*` có thể **không** chạy ở error target `/error` dù registration có `ERROR`. Filter map `/*` có thể thấy cả hai, nhưng còn bị `OncePerRequestFilter` skip nếu cấu hình mặc định của class đó bỏ qua ERROR.

Không phải mọi response lỗi 4xx/5xx đều tạo ERROR dispatch: `@ControllerAdvice` hoặc handler có thể trả `ResponseEntity`/`ProblemDetail` trực tiếp trong **cùng REQUEST dispatch**. Ngược lại, filter/security/container có thể gây error handling trước khi MVC chạy. Hãy kiểm tra thực tế thay vì suy đoán từ status code.

### 4.3. `ASYNC` dispatch

Trong Spring MVC, một handler trả `Callable<T>`, `DeferredResult<T>` hoặc cơ chế bất đồng bộ khác có thể bắt đầu async processing. Thread phục vụ request ban đầu có thể thoát; kết quả async được redispatch về Servlet container để hoàn thiện HTTP response.

```text
HTTP request (REQUEST)
   |
Filter A -> DispatcherServlet
                 |
                 +-- controller trả Callable
                 +-- request startAsync
   |
REQUEST thread có thể kết thúc
   |
worker thread tính toán kết quả
   |
Servlet ASYNC dispatch
   |
Filter A [ASYNC] nếu đã map và không tự skip
   |
DispatcherServlet render/ghi response
```

Filter có dùng `ThreadLocal` phải quản lý set/clear **cho từng thread/dispatch phù hợp**, không tin context tự truyền sang worker thread. Khi Servlet Filter cần tham gia request bất đồng bộ, phải kiểm tra **`setAsyncSupported(true)`**, dispatcher mapping, Servlet/filters trong toàn chain, và logic filter class. “Có `ASYNC` trong mapping” không tự cho phép mọi filter bất đồng bộ nếu async support của toàn chain không hợp lệ.

### 4.4. `INCLUDE`

`RequestDispatcher.include(...)` khiến một resource đóng góp output cho response của request đang chạy. Servlet Filter có thể tham gia **INCLUDE** khi registration map loại đó. Các thay đổi status/headers trong included resource bị giới hạn bởi Servlet semantics; không dùng filter INCLUDE như cơ chế thay thế cho response controller chính. Các template engine hiện đại thường dùng cơ chế fragment của riêng chúng, **không đồng nghĩa Servlet INCLUDE dispatch**.

## 5. Các cách đăng ký Servlet Filter trong Spring Boot

### 5.1. Khai báo bean `Filter` để Boot tự đăng ký

Trong ứng dụng Boot có embedded Servlet container, một bean `Filter` được phát hiện và thường được Boot tự đăng ký vào ServletContext:

```java
@Bean
Filter simpleFilter() {
    return (request, response, chain) -> {
        // Trước downstream...
        chain.doFilter(request, response);
        // Sau downstream...
    };
}
```

Đây là **bean factory method fragment** trong class `@Configuration`, cần imports `jakarta.servlet.Filter` và `org.springframework.context.annotation.Bean`. Boot mặc định map filter bean theo quy tắc filter registration, thường `/*`.

Đường này tiện khi không cần tùy chỉnh URL pattern, dispatchers hoặc order sâu. Nhưng nếu ứng dụng cần **chính xác** thứ tự/dispatcher/URL, nên dùng `FilterRegistrationBean` hoặc API registration thích hợp.

### 5.2. `FilterRegistrationBean<T>`: cấu hình rõ ràng

`org.springframework.boot.web.servlet.FilterRegistrationBean<T>` đăng ký một filter với embedded Servlet container và cho phép:

- `setFilter(filter)` hoặc constructor nhận filter.
- `setOrder(int)` chỉ định thứ tự registration.
- `addUrlPatterns(...)` / `setUrlPatterns(...)` giới hạn URL.
- `setDispatcherTypes(DispatcherType...)` hoặc `setDispatcherTypes(EnumSet<DispatcherType>)`.
- `setAsyncSupported(boolean)`.
- `setName(...)`, init parameters, servlet names và một số chi tiết mapping khác.

Ví dụ:

```java
@Bean
FilterRegistrationBean<AuditFilter> auditRegistration() {
    FilterRegistrationBean<AuditFilter> registration =
            new FilterRegistrationBean<>(new AuditFilter());

    registration.setName("auditFilter");
    registration.addUrlPatterns("/api/*");
    registration.setDispatcherTypes(
            DispatcherType.REQUEST, DispatcherType.ERROR);
    registration.setOrder(100);
    registration.setAsyncSupported(true);
    return registration;
}
```

Đây là **fragment**: `AuditFilter` là filter class do ứng dụng phải định nghĩa. Ý tưởng là đăng ký **một filter instance thông qua một registration bean**. Không tự gắn đồng thời `@Component`/`@WebFilter` vào chính filter rồi lại đăng ký nó riêng theo cách gây double registration.

### 5.3. `@WebFilter` và `@ServletComponentScan`

Servlet API có `@WebFilter` để khai báo filter và URL/dispatcher mappings bằng annotation. Trong Spring Boot embedded container, muốn tự động quét Servlet components theo cách tương ứng thường dùng `@ServletComponentScan` (với Boot 3 dùng `jakarta.servlet.annotation.WebFilter`).

```java
@WebFilter(
    filterName = "legacyAudit",
    urlPatterns = "/legacy/*",
    dispatcherTypes = {
        DispatcherType.REQUEST, DispatcherType.FORWARD
    }
)
public class LegacyAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        chain.doFilter(request, response);
    }
}
```

Đây là **class fragment** với imports cần thêm, phải đặt trong file `LegacyAuditFilter.java` và cấu hình Servlet component scan nếu dùng Boot executable JAR. Ở Spring Boot mới, có thêm những lựa chọn annotation registration do Boot cung cấp; luôn đối chiếu version thực tế trước khi sao chép.

Không coi `@WebFilter` tự có đầy đủ Spring dependency injection như `@Component` trong mọi kiểu deployment. Cần phân biệt ai quản lý lifecycle/filter instance.

### 5.4. `web.xml` / `ServletContext#addFilter`

Trong WAR hoặc Servlet application truyền thống, bạn có thể đăng ký filter trong `web.xml` hoặc programmatically thông qua `ServletContext`. Chúng tuân theo Servlet specification và hoạt động ngoài cơ chế `FilterRegistrationBean` của Boot. Khi migrate WAR sang embedded Boot, tránh để filter được đăng ký ở **cả hai đường** mà không có chủ đích.

## 6. Thứ tự FilterRegistrationBean, @Order và số ưu tiên

Khi dùng Boot registration, **số order nhỏ hơn chạy trước** trong nhóm các filters có order được Spring Boot quản lý. Ví dụ:

| Filter | Order | Trên đường vào | Trên đường ra |
| --- | ---: | --- | --- |
| Filter A | `10` | Trước B | Sau B |
| Filter B | `20` | Sau A | Trước A |
| Filter C | `100` | Sau B | Trước B và A |

Nếu hai filters cùng order, **đừng dựa vào thứ tự không được quy định rõ** giữa chúng. Tạo giá trị order rõ và kiểm thử khi thứ tự ảnh hưởng semantics. Các filter do framework thêm (encoding, form content, Security, forwarded headers...) cũng có order, vì vậy số `10` của ứng dụng không khẳng định “chạy đầu tiên trong tất cả filters”.

Theo tài liệu Boot 3.5, có ba cách cần phân biệt:

- Đặt `@Order` trên **class Filter** hoặc implement `Ordered` đối với filter bean có auto-registration.
- Đặt `setOrder(int)` trên **`FilterRegistrationBean`** khi muốn chắc chắn cho một registration.
- **Không trông cậy `@Order` chỉ trên `@Bean method` trả Filter** để thiết lập thứ tự của Servlet filter registration; Boot khuyến nghị dùng `FilterRegistrationBean` hoặc order trên chính Filter class/instance.

Một filter wrap request (để sửa headers, đọc cached body, forwarded data...) có thể cần chạy rất sớm. Nhưng không tùy tiện đặt filter đọc body tại `Ordered.HIGHEST_PRECEDENCE`: theo Spring Boot, nó có thể chạy **trước cả character encoding config**. Hãy cân đối thứ tự các filter đã có, đặc biệt Security, CORS, body wrappers và encoding.

### 6.1. Thứ tự registration khác với thứ tự `addFilterBefore` trong Spring Security

Nếu định nghĩa:

```java
http.addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
```

Đây là **fragment cấu hình Spring Security**, không phải thứ tự của tất cả Servlet filters. Nó xác định vị trí **bên trong** một `SecurityFilterChain`; Servlet filter registration của Spring Security nằm ở tầng bên ngoài. Không dùng `@Order(1)` trên custom security filter và mặc định rằng nó đứng trước Spring Security authentication filter.

## 7. Thứ tự filter không giải quyết việc filter có chạy hay không

Một filter có thể **không chạy** dù order sớm vì:

1. URL request/dispatch **không khớp URL pattern** hoặc servlet name mapping.
2. Registration **không chứa dispatcher type** hiện tại.
3. Filter class **chủ động skip** bằng điều kiện riêng, ví dụ `OncePerRequestFilter#shouldNotFilter(...)`.
4. Với async/error, `OncePerRequestFilter` có `shouldNotFilterAsyncDispatch()` và `shouldNotFilterErrorDispatch()`.
5. `OncePerRequestFilter` phát hiện **already-filtered attribute** trong cùng dispatch/context và tránh thực thi `doFilterInternal` lần nữa.
6. Một filter trước đó không gọi `chain.doFilter(...)`.
7. Spring Security `FilterChainProxy` chọn một security chain khác, hoặc filter custom không được thêm vào chain khớp request.
8. Filter không đăng ký thành công, registration bị disable hoặc application dùng Servlet context/route khác.

Một filter có thể **chạy hai lần** dù order “đúng” khi:

- Một instance (hoặc hai instances cùng chức năng) được đăng ký độc lập ở cả Servlet và Security chain.
- Filter thường `implements Filter` được mapped tới nhiều dispatch types; mỗi dispatch là một lần đi qua chain.
- `REQUEST` dẫn tới `FORWARD`; filter map cả hai chạy ở cả hai.
- Error handling tạo `ERROR` dispatch mới; filter map ERROR chạy thêm.
- Async request redispatch nhiều lần; nếu filter map ASYNC và logic cho phép, có thêm execution.

**“Thứ tự” và “số lần chạy” là hai câu hỏi riêng**: muốn tìm nguyên nhân cần log filter name, dispatcher type, request URI, thread và request correlation ID.

## 8. `OncePerRequestFilter`: “once” nghĩa là gì?

`org.springframework.web.filter.OncePerRequestFilter` là base class Spring triển khai `Filter`, chủ yếu cung cấp `doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain)`. Nó dùng một **already-filtered request attribute** để tránh xử lý lặp trong những tình huống request dispatch lồng nhau.

```java
class RequestTagFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        request.setAttribute("serverTag", "from-filter");
        try {
            chain.doFilter(request, response);
        } finally {
            request.removeAttribute("serverTag");
        }
    }
}
```

Đây là **class fragment**, cần imports Jakarta Servlet và `OncePerRequestFilter`, cùng cấu hình registration. Khi filter chạy, downstream nhận `serverTag`; sau khi downstream trả về, attribute được dọn.

Các điểm dễ sai:

- `OncePerRequestFilter` **không tự đăng ký** với Servlet container. Vẫn cần Filter bean/FilterRegistrationBean/registration khác.
- Base class mặc định **bỏ qua async dispatch** bằng `shouldNotFilterAsyncDispatch() == true` và **bỏ qua error dispatch** bằng `shouldNotFilterErrorDispatch() == true`.
- Override `shouldNotFilterAsyncDispatch()` trả `false` nếu muốn `doFilterInternal` được tham gia trong `ASYNC` dispatch phù hợp, **nhưng** registration của Servlet Filter cũng phải bao gồm `DispatcherType.ASYNC`.
- Override `shouldNotFilterErrorDispatch()` trả `false` nếu muốn xử lý `ERROR`; registration cũng cần `DispatcherType.ERROR` và URL/Servlet mapping khớp target error.
- Với **nested error dispatch**, một số Servlet container có thể xử lý `ERROR` lồng trong `REQUEST` trước khi filter chain gốc hoàn toàn thoát. Spring có hook `doFilterNestedErrorDispatch(...)` để xử lý trường hợp này; hành vi không được tóm gọn thành “always once forever”.
- `FORWARD` có thể dùng lại cùng request và đụng already-filtered marker. Vì vậy một filter `OncePerRequestFilter` đăng ký cả REQUEST/FORWARD **không nhất thiết gọi `doFilterInternal` thêm lần nữa** khi forward nằm lồng trong `chain.doFilter` ban đầu.
- Base class dùng request attribute đánh dấu đã chạy cho **filter instance/name**; tránh cố sửa tên/key marker thủ công mà không hiểu tác động.

Ví dụ khi cần quan sát async và error:

```java
class AsyncErrorContextFilter extends OncePerRequestFilter {

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        try {
            // Set per-thread context nếu cần.
            chain.doFilter(request, response);
        } finally {
            // Clear ThreadLocal/MDC nếu đã set.
        }
    }
}
```

Đây là **class minh họa**, chưa có logic ThreadLocal cụ thể. Nó vẫn cần một registration kiểu:

```java
registration.setDispatcherTypes(
        DispatcherType.REQUEST,
        DispatcherType.ASYNC,
        DispatcherType.ERROR);
registration.setAsyncSupported(true);
```

Chỉ có override method nhưng quên registration → không thấy async/error. Chỉ có registration nhưng giữ default skip behavior → có thể vào `doFilter(...)` nhưng không chạy `doFilterInternal(...)` ở những dispatch đó.

## 9. Ví dụ Java 17+ Spring Boot 3.x chạy qua embedded Servlet container

Ví dụ này cố ý dùng **plain `Filter`** thay vì `OncePerRequestFilter` để thấy rõ hai lần thực thi trên `REQUEST` và `FORWARD`. Hai filters được tạo trực tiếp trong `FilterRegistrationBean`, **không** đánh dấu `@Component` để tránh vô tình đăng ký trùng.

Trong project Spring Boot 3.x (Servlet MVC) đã có Boot plugin, repositories và dependency management, thêm dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment `build.gradle`**, không phải một build file hoàn chỉnh. `spring-boot-starter-web` ở Boot 3 có Servlet stack embedded container. Các imports dưới dùng `jakarta.servlet.*`, không dùng `javax.servlet.*` cũ của Boot 2.

Tạo **`src/main/java/demo/filterchain/FilterChainApplication.java`**:

```java
package demo.filterchain;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.EnumSet;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class FilterChainApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterChainApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<RecordingFilter> firstRegistration() {
        FilterRegistrationBean<RecordingFilter> registration =
                new FilterRegistrationBean<>(new RecordingFilter("A"));

        registration.setName("demoFilterA");
        registration.addUrlPatterns("/api/filters/*");
        registration.setOrder(10);
        registration.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.FORWARD,
                DispatcherType.INCLUDE,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        registration.setAsyncSupported(true);
        return registration;
    }

    @Bean
    FilterRegistrationBean<RecordingFilter> secondRegistration() {
        FilterRegistrationBean<RecordingFilter> registration =
                new FilterRegistrationBean<>(new RecordingFilter("B"));

        registration.setName("demoFilterB");
        registration.addUrlPatterns("/api/filters/*");
        registration.setOrder(20);
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setAsyncSupported(true);
        return registration;
    }
}

class RecordingFilter implements Filter {
    static final String EVENTS_KEY = "demo.filter.events";

    private final String label;

    RecordingFilter(String label) {
        this.label = label;
    }

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;

        @SuppressWarnings("unchecked")
        List<String> previous =
                (List<String>) http.getAttribute(EVENTS_KEY);

        List<String> events = previous;
        if (events == null) {
            events = new CopyOnWriteArrayList<>();
            http.setAttribute(EVENTS_KEY, events);
        }

        // Ghi nhận ở chiều đi vào; "before" chạy theo order tăng dần.
        events.add(label + ":" + http.getDispatcherType().name());

        // Luôn chuyển tiếp tới filter/servlet tiếp theo trong ví dụ.
        chain.doFilter(request, response);
    }

    static List<String> events(HttpServletRequest request) {
        @SuppressWarnings("unchecked")
        List<String> result =
                (List<String>) request.getAttribute(EVENTS_KEY);

        if (result == null) {
            return List.of();
        }
        return List.copyOf(result);
    }
}

@RestController
class EchoController {

    @GetMapping(
            path = "/api/filters/echo",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String echo(HttpServletRequest request) {
        List<String> events = new java.util.ArrayList<>(
                RecordingFilter.events(request));

        events.add("handler:" + request.getDispatcherType().name());
        return String.join(" | ", events);
    }

    @GetMapping(
            path = "/api/plain",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String plain() {
        return "plain";
    }
}

@Controller
class ForwardController {
    @GetMapping("/api/filters/forward")
    String forwardToEcho() {
        return "forward:/api/filters/echo";
    }
}
```

**Tính biên dịch:** đây là một file Java 17 hợp lệ khi build bằng Spring Boot 3.x + Servlet dependencies, vì chỉ `FilterChainApplication` là `public`. `RecordingFilter` và hai controllers là package-private; Spring Boot component scanning từ `demo.filterchain` vẫn tìm controllers. Không dùng `javac FilterChainApplication.java` mà thiếu Spring/Servlet classpath; dùng build tool của project.

### 9.1. Tại sao filter A và B chạy theo thứ tự đó?

- Hai registration cùng map URL `/api/filters/*`, cùng tham gia **`REQUEST`**.
- A có `order=10`, B có `order=20`; ở chiều vào: **A trước B**.
- B **chỉ map `REQUEST`**. A map `REQUEST` và `FORWARD` cùng những dispatcher types khác.
- Method `EchoController#echo` đọc event list **trước khi response body được ghi**; nó phản ánh các bước vào của filter đã xảy ra. Nếu sau `chain.doFilter` filter còn cleanup/log, các sự kiện sau đó **không tự xuất hiện trong body** đã render.
- `CopyOnWriteArrayList` được dùng để tránh race trong việc đọc danh sách sự kiện nếu có xử lý async; đây là demo observability, không phải thiết kế high-throughput logging tối ưu.

### 9.2. Request bình thường

```bash
./gradlew bootRun
curl -i 'http://localhost:8080/api/filters/echo'
```

Với registration như trên và Servlet container embedded thông thường, status **200 OK**, `Content-Type` tương thích `text/plain`, body:

```text
A:REQUEST | B:REQUEST | handler:REQUEST
```

`/api/plain` không khớp URL pattern `/api/filters/*` nên body chỉ:

```text
plain
```

Spring Boot vẫn có thể có các **framework filters khác** chạy trên cả hai endpoint; ví dụ chỉ ghi lại hai custom filters A/B. Không suy ra filter chain toàn ứng dụng chỉ có đúng A và B.

### 9.3. Server-side forward

```bash
curl -i 'http://localhost:8080/api/filters/forward'
```

Trong Servlet container hỗ trợ MVC forward như ví dụ, luồng được ghi:

```text
A:REQUEST | B:REQUEST | A:FORWARD | handler:FORWARD
```

Lý do:

1. Request đầu `/api/filters/forward` đi qua A và B (cùng map REQUEST).
2. MVC `ForwardController` trả `forward:/api/filters/echo`; server thực hiện `FORWARD` trong cùng HTTP request.
3. Ở forward dispatch, A vẫn map `FORWARD` và đích `/api/filters/echo`; B **không** map `FORWARD`.
4. `EchoController` được gọi với dispatcher type `FORWARD` và đọc request attribute list đã tích lũy.

Ví dụ dùng **plain Filter**, nên không có already-filtered marker của `OncePerRequestFilter` tự ngăn A lần thứ hai. Hành vi thực tế còn phụ thuộc URL mappings và container. Trong phần test tiếp theo, dùng server thật của `@SpringBootTest(RANDOM_PORT)` để kiểm tra thay vì chỉ mô phỏng với MockMvc.

### 9.4. Những giới hạn chủ ý của ví dụ

- Chỉ quan sát trực tiếp REQUEST/FORWARD. Đăng ký `ASYNC`/`ERROR`/`INCLUDE` cho A **không tự tạo** những dispatch này; muốn kiểm thử phải có async handler, error mapping hoặc Servlet include phù hợp.
- `ERROR` thường target `/error` ở Boot. Vì A chỉ map `/api/filters/*`, nó **có thể không thấy ERROR dispatch tới `/error`** dù đã đăng ký ERROR. Muốn theo dõi error dispatch, cần mapping target error thích hợp (thường `/*` hoặc `/error`).
- `FilterRegistrationBean#setAsyncSupported(true)` cho phép registration tham gia async, nhưng chỉ dùng async thực sự khi Servlet và các filters liên quan đều hỗ trợ.
- App dùng embedded container và không có Spring Security tùy chỉnh; nếu thêm security, có thêm filters trong chuỗi.
- Tránh dùng `CopyOnWriteArrayList` để tích lũy lượng lớn log request trong production; thay bằng structured logs/tracing, cleanup và giới hạn dữ liệu.
- Ví dụ không tự log các sự kiện “sau chain” để response body luôn phản ánh chính xác trạng thái tại thời điểm handler chạy.

## 10. Integration test với embedded container, không chỉ MockMvc

Một số chi tiết filter registration như dispatcher types, URL patterns và forward/error mapping được **Servlet container thực thi**. `MockMvc` rất hữu ích để test controller nhưng có thể không tái hiện đầy đủ dynamic filter registration/container forward/error dispatch như runtime thật.

Với `spring-boot-starter-test` của Boot 3, tạo **`src/test/java/demo/filterchain/FilterChainApplicationTests.java`**:

```java
package demo.filterchain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class FilterChainApplicationTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void requestDispatchRunsAThenBThenController() {
        ResponseEntity<String> response = http.getForEntity(
                "/api/filters/echo", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "A:REQUEST | B:REQUEST | handler:REQUEST",
                response.getBody());
    }

    @Test
    void servletForwardDispatchRunsOnlyAAgain() {
        ResponseEntity<String> response = http.getForEntity(
                "/api/filters/forward", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                "A:REQUEST | B:REQUEST | A:FORWARD | handler:FORWARD",
                response.getBody());
    }

    @Test
    void customFiltersDoNotMatchOtherUrlPattern() {
        ResponseEntity<String> response = http.getForEntity(
                "/api/plain", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("plain", response.getBody());
    }
}
```

Chạy:

```bash
./gradlew test
```

**Kỳ vọng ba test pass** với cấu hình Spring Boot 3.x Servlet embedded như ví dụ, không có security/filter phụ thay đổi route/response. Đây là kết quả mong đợi từ logic source; **không phải log thực thi đã thu được**. Nếu môi trường sử dụng servlet container khác hoặc có custom filters, kiểm tra dispatching/registration trên server thực tế thay vì ép test output để che sai khác.

Ưu thế của `RANDOM_PORT`: ứng dụng khởi chạy Servlet container và nhận HTTP qua port thật, nên đo được filter registration. Nó chậm hơn `MockMvc` nhưng phù hợp kiểm tra URL mapping/dispatcher types. Với Spring Boot 4, test infrastructure/module và API TestRestTemplate có thể đổi; ví dụ này có baseline Boot 3.

### 10.1. Test ASYNC và ERROR cần tình huống riêng

Để xác minh `ASYNC`:

- Tạo handler MVC trả `Callable<String>` hoặc `DeferredResult<String>` và bảo đảm async được enabled ở toàn servlet/filter chain.
- Đăng ký filter theo `DispatcherType.REQUEST` và `ASYNC`.
- Nếu dùng `OncePerRequestFilter`, quyết định rõ có override `shouldNotFilterAsyncDispatch()` hay không.
- Log riêng dispatcher type, thread ID, request correlation ID trong từng phase; assert chính xác số lần theo contract của filter.
- Test bằng embedded server thực và đảm bảo không dựa vào timing ngẫu nhiên.

Để xác minh `ERROR`:

- Tạo tình huống lỗi đi qua **container error dispatch**, ví dụ Servlet có error mapping phù hợp.
- Đảm bảo filter map `DispatcherType.ERROR` và **URL target error** phù hợp.
- Nếu filter là `OncePerRequestFilter`, cấu hình `shouldNotFilterErrorDispatch()`; kiểm tra nested ERROR behavior của container.
- Không dùng mỗi một `@RestControllerAdvice` trả 400/500 trực tiếp rồi kết luận container đã chạy ERROR dispatch.

Để xác minh `INCLUDE`, dùng `RequestDispatcher.include(...)` theo Servlet API và xác nhận filter registration/URL mapping, không dùng Thymeleaf fragment inclusion rồi mong `DispatcherType.INCLUDE` xuất hiện.

## 11. Spring Security filter chain và nguy cơ đăng ký trùng

Trong ứng dụng có Spring Security, container thường thấy một Servlet filter proxy (`DelegatingFilterProxy`) điều phối vào bean `springSecurityFilterChain`. Bên trong `FilterChainProxy`, có một hoặc nhiều `SecurityFilterChain` khớp URL theo rule của Spring Security.

Một cấu hình ví dụ (fragment Java dành cho Spring Security 6.x):

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        ApiAuditFilter audit) throws Exception {

    http.securityMatcher("/api/**")
        .authorizeHttpRequests(registry ->
                registry.anyRequest().authenticated())
        .addFilterBefore(
                audit, UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
```

Đây là **fragment**, cần dependency Spring Security, các imports tương ứng và bean `ApiAuditFilter`. Method `addFilterBefore` thao tác trong Spring Security chain, **không** dùng `FilterRegistrationBean#setOrder`.

Nếu `ApiAuditFilter` là Spring bean và implements `Filter`, Spring Boot có thể **auto-register** nó thành Servlet filter. Lúc đó cùng logic audit có thể chạy:

1. Một lần trong container chain do Boot tự đăng ký.
2. Một lần bên trong Spring Security chain do `addFilterBefore`.

Một kỹ thuật để ngăn Servlet auto registration khi filter được sử dụng **chỉ ở Spring Security**:

```java
@Bean
FilterRegistrationBean<ApiAuditFilter> disableServletRegistration(
        ApiAuditFilter filter) {

    FilterRegistrationBean<ApiAuditFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

Đây là fragment trong `@Configuration`, cần `ApiAuditFilter` do ứng dụng định nghĩa. Khi có filter đăng ký riêng hoặc nhiều context, hãy kiểm tra thực tế auto-registration và đảm bảo không làm mất đăng ký mong muốn của chính mình.

**Vấn đề CORS:** preflight `OPTIONS` có thể không mang session cookie/credentials, nên CORS phải được xử lý **trước lớp security authorization phù hợp**. Trong app có Spring Security, nên dùng cơ chế CORS tích hợp của Security và MVC (hoặc CORS filter sắp xếp đúng), tránh có nhiều nguồn CORS headers mâu thuẫn.

**Vấn đề CSRF:** Servlet filter chain và security chain ảnh hưởng các HTTP methods thay đổi state; không bỏ CSRF protection tùy tiện chỉ vì filter custom gặp 403.

## 12. Request/response wrappers và filter order

Filter có thể bọc request/response:

```java
HttpServletRequest wrapped =
        new HttpServletRequestWrapper(originalRequest) {
            // Override method cần thiết theo mục đích.
        };

chain.doFilter(wrapped, response);
```

Đây là **fragment**, cần `HttpServletRequestWrapper` và biến `originalRequest`. Wrapper có thể thêm headers, cache body hoặc thay đổi cách downstream nhìn thấy request. Nếu đặt wrapper quá muộn, một filter trước nó đã đọc dữ liệu cũ; nếu đặt quá sớm không phù hợp encoding, có thể phá decoding.

Những mối quan tâm:

- **Character encoding:** xác định charset **trước khi ai đó đọc parameters/body**; việc set encoding sau khi body đã đọc không sửa được dữ liệu.
- **HTTP body stream:** request body thông thường chỉ đọc được một lần nếu không dùng caching wrapper đúng; không log dữ liệu nhạy cảm, không đọc toàn body vô điều kiện.
- **Forwarded headers:** `ForwardedHeaderFilter` có thể wrap request để downstream nhìn scheme/host/prefix do reverse proxy truyền vào. Filter này phải chạy trước các thành phần cần dùng forwarded view; chỉ tin headers từ proxy đã cấu hình an toàn.
- **ContentCachingRequestWrapper`:** có thể lưu bytes **đã được downstream đọc**; không mặc định rằng chỉ wrap là có sẵn toàn bộ body. Lưu ý memory và max payload.
- **Async & ERROR:** wrapper có thể bị thay thế hoặc không còn như cũ khi dispatch xảy ra ở thread khác hoặc nested ERROR; kiểm tra base filter hỗ trợ `doFilterNestedErrorDispatch` nếu cần giữ wrapper semantics.
- **Response wrapper:** response có thể đã committed; không cố đọc/thay bytes sau `chain.doFilter` mà không có thiết kế buffer đúng và giới hạn dung lượng.

Một custom filter chỉ cần correlation ID thường không nên wrap toàn body; đặt header/request attribute hoặc logging MDC ở đúng scope là đủ.

## 13. Logging và chẩn đoán filter chain

Để tìm filter chạy sai thứ tự, nên log tối thiểu:

- Filter name và registration order (tại startup).
- Dispatcher type: `request.getDispatcherType()`.
- HTTP method, request URI, servlet path và context path.
- Correlation ID do server hoặc hạ tầng tin cậy cấp.
- Thread name/ID nếu đang điều tra ASYNC.
- Sự kiện `before`/`after` và thời gian đo.
- Thông tin lỗi đã được phân loại, không lộ token/session ID/body nhạy cảm.

Trong Boot 3 có thể bật:

```properties
logging.level.web=debug
```

Theo tài liệu Boot, điều này hữu ích để thấy filter registrations tại startup, bao gồm order/URL mapping. Có thể cần logger package cụ thể cho Servlet container và Spring Security để xem chi tiết runtime chain; đừng mở DEBUG/TRACE toàn cục trong production vì vừa tốn chi phí vừa có nguy cơ log dữ liệu nhạy cảm.

### 13.1. Dấu hiệu và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Filter không bao giờ chạy | Không đăng ký, registration disabled hoặc URL pattern sai | Startup logs và request tới URL khớp |
| Filter chỉ chạy với GET thường, không chạy khi forward | Registration không map FORWARD hoặc `OncePerRequestFilter` skip nested dispatch | Log dispatcher type và target URL |
| Filter không chạy ở `/error` | Chỉ map REQUEST hoặc URL không khớp `/error` | Đăng ký ERROR + mapping đích, test container |
| Filter không chạy ở async completion | Thiếu ASYNC mapping, asyncSupported false, OncePerRequestFilter skip | Kiểm tra cả registration và override |
| Filter chạy hai lần trên mỗi request | Auto-registration + Security chain hoặc multiple registrations | Liệt kê registration, security chain, filter IDs |
| URL ghi vào Location sai phía sau proxy | Forwarded header filter chạy sai order/trust | Kiểm tra external request vs nội bộ |
| 401/403 trước khi controller chạy | Security filter chain từ chối | Debug security matcher và authentication |
| 400 do body parse bất ngờ | Body bị đọc trước converter hoặc encoding sai | Kiểm tra filter body wrapper/order |
| Request không đến controller, client “treo” | Filter quên `chain.doFilter` hoặc không tự trả response | Trace before/after và breakpoints |
| ThreadLocal chứa data từ user trước | Không clear trong `finally` hoặc bị reuse thread | Audit MDC context lifetime |
| Chỉ lỗi ở cluster, không tái hiện local | Filter state singleton/local, session store khác | Kiểm tra node ID, sticky sessions, shared state |

### 13.2. Cách cô lập lỗi

1. Xác nhận request **có đi vào Servlet container** hay bị gateway/WAF chặn trước.
2. In danh sách filter registrations và URL patterns.
3. Log `DispatcherType` ở filter đầu tiên, không suy từ HTTP method.
4. Nếu dùng Spring Security, log matching `SecurityFilterChain`.
5. Nếu lỗi xảy ra khi forward/error/async, tạo một integration test với dispatch tương ứng.
6. Kiểm tra filter đã gọi `chain.doFilter` đúng và cleanup `ThreadLocal` trong `finally`.
7. Đọc response status/headers/body **trước khi quyết định tầng nào xử lý lỗi**.
8. So sánh embedded container ở dev/test với container/proxy production nếu hai môi trường khác nhau.

## 14. Khi nào dùng Filter, Interceptor hay ControllerAdvice?

| Bài toán | Lựa chọn thường hợp lý | Giải thích |
| --- | --- | --- |
| Character encoding, HTTP wrapper, request correlation tại ingress | Servlet Filter | Cần trước MVC handler |
| Authentication/authorization | Spring Security filter chain | Cơ chế security chuyên dụng |
| CORS | Spring MVC/Spring Security CORS tích hợp hoặc CorsFilter đúng order | Cần xử lý OPTIONS trước auth phù hợp |
| Bổ sung model attribute cho view | `@ModelAttribute` method | MVC model, không cần filter |
| Quyết định theo handler được chọn, audit tên handler | `HandlerInterceptor` | Có context handler MVC |
| Kiểm tra DTO/request body | `@Valid`/`@Validated` + controller/service validation | Không nên deserialize JSON tùy tiện trong filter |
| Chuyển exception MVC/domain thành HTTP error | `@RestControllerAdvice` / `ResponseEntityExceptionHandler` | Tập trung error contract |
| Xử lý lỗi authentication từ Security | `AuthenticationEntryPoint` / `AccessDeniedHandler` | Nằm ở filter layer phù hợp |
| Truyền context nội bộ giữa methods | Tham số rõ ràng hoặc request attributes | Tránh lạm dụng ThreadLocal |
| Theo dõi async/error across dispatch | Servlet Filter có dispatcher mapping + lifecycle phù hợp | Không chỉ interceptor REQUEST đơn giản |

**Không đặt nghiệp vụ chính hoặc truy vấn DB nặng vào mọi Servlet Filter** nếu chỉ một endpoint cần. Filter nên tập trung vào cross-cutting concern liên quan HTTP; giới hạn phạm vi để tránh ảnh hưởng cả health checks, static files và trang lỗi.

## 15. Phân biệt Spring Framework / Boot theo phiên bản

| Nền tảng | Filter registration / dispatch notes |
| --- | --- |
| Spring Framework 5.x + Boot 2.x | Servlet Filter API thường là `javax.servlet.*`, `OncePerRequestFilter` và `FilterRegistrationBean` đã có |
| Spring Framework 6.x + Boot 3.x | Java 17+, Jakarta Servlet `jakarta.servlet.*`; `FilterRegistrationBean`/`OncePerRequestFilter` dùng như trong ví dụ |
| Spring Framework 7.x + Boot 4.x | Servlet filter semantics và `OncePerRequestFilter` tiếp tục có; Boot 4 có điều chỉnh module, starter, registration annotation và test infrastructure; đọc đúng Javadoc/BOM của version đang dùng |

Ở mọi version, **Servlet spec dispatcher types khác nhau** không biến `REQUEST` thành `ASYNC` chỉ vì code có CompletableFuture. Ứng dụng cần thực sự kích hoạt Servlet asynchronous processing thì mới có redispatch ASYNC.

Một thay đổi khi migrate Boot 2 → Boot 3 thường gặp: imports `javax.servlet.Filter`, `javax.servlet.DispatcherType` phải đổi sang `jakarta.servlet.*`. Thay đổi dependency Jackson, validation hay Spring Security có thể ảnh hưởng các filters khác, nên sau nâng cấp phải kiểm tra filter registration, order, URL mapping và dispatcher types bằng test thật.

## 16. Checklist đưa filter vào production

- [ ] Phạm vi URL/Servlet registration được giới hạn đúng nhu cầu; không mặc định mọi filter cần `/*`.
- [ ] Order rõ ràng khi có phụ thuộc, không rely vào filter order bằng nhau.
- [ ] Biết filter thuộc Servlet chain hay Spring Security chain; không đăng ký hai lần.
- [ ] `DispatcherType.REQUEST`/`FORWARD`/`INCLUDE`/`ASYNC`/`ERROR` được chọn có chủ đích.
- [ ] Nếu cần ASYNC, thiết lập async support và policy `OncePerRequestFilter` cho từng thread/dispatch.
- [ ] Nếu cần ERROR, map cả target error dispatch; kiểm tra nested error case.
- [ ] Filter luôn gọi `chain.doFilter` nếu không chủ động hoàn tất response.
- [ ] ThreadLocals/MDC/resource cleanup dùng `try/finally`, không leak giữa requests.
- [ ] Không sửa response headers sau khi đã committed.
- [ ] Encoding/body wrapper đặt đúng chỗ, có giới hạn memory và tránh log bí mật.
- [ ] Forwarded headers chỉ được tin từ proxy cấu hình; auth/CORS/Security order được kiểm tra.
- [ ] Có test request bình thường, forward, async, error khi những dispatch này nằm trong contract.
- [ ] Thứ tự/registration được kiểm thử với container thật ít nhất ở integration tests quan trọng.
- [ ] Có logging/tracing giúp truy nguyên loại dispatcher, filter name và lỗi production.

## 17. Bài tập thực hành

1. Trong app phần 9, đổi `registration.setOrder(10)` của A thành `30`. Điều gì thay đổi trong body `GET /api/filters/echo`? Vì sao chiều return sau chain (nếu có) lại theo hướng ngược?
2. Bỏ `DispatcherType.FORWARD` khỏi A rồi gọi `/api/filters/forward`. Chuỗi sự kiện dự kiến còn gì? Test server thật.
3. Thay A bằng subclass `OncePerRequestFilter`. Ở nested forward trong `chain.doFilter`, tại sao `doFilterInternal` có thể **không** chạy lần thứ hai ngay cả khi registration có FORWARD?
4. Đăng ký A chỉ map `/api/filters/*` và map ERROR. Một exception dẫn tới error page `/error`. Vì sao A có thể không chạy ở error dispatch?
5. Thêm một `Callable<String>` controller và filter async-aware. Phân biệt `setAsyncSupported`, dispatcher mapping ASYNC và `shouldNotFilterAsyncDispatch()`.
6. Một filter implements `Filter` là bean Spring và được thêm vào `HttpSecurity.addFilterBefore`. Tại sao có nguy cơ xử lý hai lần? Hãy disable container registration nhưng giữ security chain.
7. Đặt filter đọc body ở order cực nhỏ trước character encoding filter. Những lỗi nào có thể xuất hiện với form data UTF-8?
8. Dùng `MockMvc` và `@SpringBootTest(RANDOM_PORT)` để test. Loại nào phù hợp hơn để chứng minh Servlet container đăng ký FORWARD/ERROR? Vì sao?
9. Bổ sung `RequestDispatcher.include(...)` vào một Servlet. Filter có map INCLUDE sẽ chạy khi nào, và sự khác biệt với Thymeleaf template fragment là gì?
10. Nếu filter không gọi `chain.doFilter`, cần làm gì để không gây response dang dở? Nêu một ví dụ chặn request hợp lệ và một trường hợp bug.
11. Phân biệt `HandlerInterceptor#preHandle`, Servlet Filter `doFilter` và Spring Security `SecurityFilterChain` trong một app có cả ba.
12. Thiết kế correlation ID được ghi trong REQUEST và cả ERROR dispatch nhưng không leak sang thread/client khác; giải thích cleanup theo `finally`.

## 18. Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — Servlet Filters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html): filter chain, built-in filters, wrappers, forwarded headers và dispatch.
- [Spring Framework 6.2 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): already-filtered marker, async/error skipping và nested ERROR dispatch.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): Servlet filter beans, order, registration và startup debug logging.
- [Spring Boot 3.5 — FilterRegistrationBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/FilterRegistrationBean.html): URL patterns, order, Servlet registrations, dispatcher types.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): dispatcher types defaults và filter registration.
- [Spring Security — Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): FilterChainProxy, SecurityFilterChain và order.
- [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): thứ tự CORS và Spring Security.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/6.0/): Servlet Filter, dispatcher types, request dispatch và async handling.
