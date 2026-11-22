# Servlet Filter, FilterChain và DispatcherServlet trong luồng yêu cầu

Trong ứng dụng **Spring MVC trên Servlet stack**, một HTTP request không đi thẳng từ client vào `@RestController`. Trước khi controller được gọi, **Servlet container** chọn các `jakarta.servlet.Filter` phù hợp, thực thi chúng theo thứ tự trong một `FilterChain` rồi mới gọi **Servlet đích**. Với Spring MVC, Servlet đích thông thường chính là **`DispatcherServlet`**. Spring Security khai thác cơ chế này để xác thực, kiểm tra quyền, bảo vệ CSRF và nhiều lớp bảo mật **trước khi** business controller xử lý.

Nếu chỉ nhớ một sơ đồ, hãy nhớ:

```text
Client (HTTP)
   |
   v
Servlet container (Tomcat / Jetty / Undertow)
   |
   v
Servlet Filter A (trước)
   |
   v
DelegatingFilterProxy("springSecurityFilterChain")
   |
   v
FilterChainProxy
   |
   +-- Chọn SecurityFilterChain ĐẦU TIÊN khớp request
   |      |
   |      +-- SecurityContext / exploit protection
   |      +-- Authentication
   |      +-- Authorization
   |      +-- Các security filter khác tùy cấu hình
   |
   v
Servlet Filter B (nếu có và được đăng ký tại vị trí đó)
   |
   v
DispatcherServlet (Servlet của Spring MVC)
   |
   +-- HandlerMapping -> tìm controller/handler
   +-- HandlerAdapter -> gọi handler đúng giao thức
   +-- HandlerInterceptor -> preHandle/postHandle/afterCompletion theo flow
   +-- Controller -> Service -> Repository
   +-- HttpMessageConverter / ViewResolver / HandlerExceptionResolver
   |
   v
HTTP response
   |
   +-- Filter B (phần sau chain.doFilter)
   +-- Spring Security filters (unwind)
   +-- Filter A (phần sau chain.doFilter)
   |
   v
Client
```

Sơ đồ mô tả **một đường request điển hình**; thứ tự thực tế phụ thuộc các filter registrations, `DispatcherType`, danh sách security filters, security matchers và cấu hình Spring Boot. Đặc biệt, Spring Security có thể **chặn request** trước `DispatcherServlet`, nên controller không phải lúc nào cũng được gọi. Một số request đã được MVC/controller xử lý lại có thể kích hoạt một dispatch `ERROR` hoặc `ASYNC` riêng.

Bài này dành cho **Java 17+, Spring Boot 3, Spring Security 6.x, Spring MVC/Servlet**. Các API cơ bản dựa trên Jakarta Servlet (`jakarta.servlet.*`), không phải import `javax.servlet.*` của nhiều tài liệu cũ. Cuối bài có **chương trình Java 17 chạy độc lập**, project Spring Boot minh họa hai tầng filter và các bài kiểm thử MockMvc.

## 1. Phân biệt chính xác các khái niệm

| Khái niệm | Thuộc tầng nào? | Vai trò | Có trực tiếp gọi Controller không? |
| --- | --- | --- | --- |
| `jakarta.servlet.Filter` | Servlet API/container | Chặn, bọc hoặc xử lý request/response trước/sau downstream | Không cần biết controller; gọi `chain.doFilter` |
| `jakarta.servlet.FilterChain` | Servlet API/container | Đại diện phần filter chain còn lại và Servlet đích | Tiếp tục đến Servlet khi hết filter |
| `DispatcherServlet` | Spring MVC | Front controller của Spring MVC; tìm và gọi handler | Có, qua HandlerMapping và HandlerAdapter |
| `HandlerMapping` | Spring MVC | Chọn handler theo path, HTTP method và điều kiện khác | Chỉ xác định handler/interceptors |
| `HandlerAdapter` | Spring MVC | Thực thi handler đã tìm ra theo contract phù hợp | Có |
| `HandlerInterceptor` | Spring MVC | Can thiệp ở giai đoạn xử lý handler bên trong MVC | Có liên quan handler, nhưng không phải Servlet Filter |
| `DelegatingFilterProxy` | Spring Web/Servlet bridge | Là Filter được container gọi, chuyển tiếp tới một Spring bean | Không trực tiếp |
| `FilterChainProxy` | Spring Security | Filter quản lý một hoặc nhiều `SecurityFilterChain` | Không trực tiếp; tiếp tục original chain nếu được phép |
| `SecurityFilterChain` | Spring Security | Matcher và danh sách filter bảo vệ request | Không phải container FilterChain |
| `SecurityContextHolder` | Spring Security | Cho biết Authentication của context hiện hành | Không phải filter/servlet |
| `@ControllerAdvice` | Spring MVC | Xử lý lỗi/logic MVC theo phạm vi tương ứng | Không mặc nhiên bắt lỗi phát sinh trước MVC |

**Không đồng nhất:** `FilterChain` (interface Servlet API), `SecurityFilterChain` (contract Spring Security) và “chuỗi các HandlerInterceptor” của Spring MVC là ba khái niệm ở ba chỗ khác nhau.

### 1.1. Servlet container chịu trách nhiệm điều gì?

Ví dụ Tomcat nhận request. Container chọn Servlet đích từ servlet mappings và chọn những Filter đã đăng ký phù hợp với URL pattern/Servlet name/dispatcher type. Nó xây đường `Filter -> Filter -> ... -> Servlet`, gọi Filter đầu tiên và cung cấp một `FilterChain` để từng filter quyết định có đi tiếp hay không.

Trong Spring Boot có embedded Tomcat mặc định (khi sử dụng Web starter thường gặp), `DispatcherServlet` được Boot tự đăng ký. Bạn hiếm khi cần tạo Servlet này bằng tay trong ứng dụng MVC đơn giản.

### 1.2. DispatcherServlet không phải là một Filter

`DispatcherServlet` kế thừa `HttpServlet`; nó là **Servlet đích**, không phải `jakarta.servlet.Filter`. Nó chỉ bắt đầu xử lý khi các filter phía trước cho request đi tiếp. Nhiệm vụ MVC là mapping/handler binding, controller, chuyển đổi request/response và giải quyết exception theo contract MVC; nó không thay thế FilterChainProxy của Spring Security.

### 1.3. FilterChain không phải “danh sách Filter để bạn tự for”

Trong `Filter.doFilter`, biến `chain` là **phần xử lý còn lại** được container cung cấp:

```java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain) throws IOException, ServletException {

    // Trước khi request đi tới Filter tiếp theo hoặc Servlet.
    chain.doFilter(request, response);
    // Sau khi downstream đã quay lại (nếu không có exception thoát ra).
}
```

Nếu **không gọi** `chain.doFilter`, downstream filter và Servlet không được gọi trong nhánh hiện tại. Nếu gọi `chain.doFilter`, code phía sau lời gọi chỉ chạy khi downstream trả về bình thường; dùng `finally` nếu cần đảm bảo giải phóng tài nguyên/log completion khi downstream ném exception.

## 2. Cơ chế “đi vào và quay ra” của FilterChain

Giả sử có hai filter A, B và một servlet MVC:

```text
request --> A.before --> B.before --> DispatcherServlet --> Controller
                     <-- B.after <-- A.after <-- response
```

Đó là cấu trúc **nested calls**, không phải “chạy A rồi B rồi controller rồi kết thúc ngay”. Nếu code dùng `try/finally`:

```java
public void doFilter(ServletRequest request, ServletResponse response,
                     FilterChain chain)
        throws IOException, ServletException {
    logBefore(request);
    try {
        chain.doFilter(request, response);
    } finally {
        logAfter(request);
    }
}
```

thì `logAfter` vẫn được thực thi khi downstream ném lỗi, nhưng **không có nghĩa HTTP response chưa được commit**. Đừng giả định luôn có thể sửa header/status/body trong `finally`: ứng dụng có thể đã flush/commit response từ controller hoặc một filter downstream.

### 2.1. Khi một filter từ chối đi tiếp

Một filter có thể kết thúc request bằng cách trả lỗi và `return`:

```java
if (!allowed) {
    httpResponse.sendError(HttpServletResponse.SC_FORBIDDEN);
    return; // Không gọi chain.doFilter.
}

chain.doFilter(request, response);
```

Nếu filter A chặn, Filter B và DispatcherServlet không chạy. Nếu security filter chặn vì thiếu credentials hoặc thiếu quyền, controller cũng có thể không chạy. Khi debug câu hỏi “vì sao breakpoint controller không hit?”, hãy bắt đầu từ container filters và security filters.

### 2.2. Request/response wrapper

Filter có thể bọc `HttpServletRequest` hoặc `HttpServletResponse` rồi chuyển wrapper xuống downstream. Ví dụ request wrapper hỗ trợ đọc body nhiều lần, response wrapper ghi nhận nội dung để compression hoặc caching. Nhưng việc đọc trước request body có thể **tiêu thụ input stream**; nếu wrapper không cache/replay đúng, `@RequestBody` ở controller sẽ đọc thấy dữ liệu rỗng.

Không tự log request body/chứa password, access token hoặc session cookie. Với bảo mật, tracing nên ghi request ID, method, path chuẩn hóa, status và latency thay vì bí mật.

### 2.3. Filter order rất quan trọng

Một bộ filter chỉ hoạt động đúng khi thứ tự hợp lý. Trong security flow, cần có context/authentication trước các bước authorization phụ thuộc identity. Một logging filter ngoài security chain có thể thấy request chưa được authenticated; một filter sau authentication có thể lấy principal đã được xác minh.

Order phải được thiết kế ở **đúng tầng**: thứ tự registration của servlet filter không giống thứ tự các filter trong một `SecurityFilterChain`.

## 3. Cách Spring Security đi vào Servlet FilterChain

Spring Security Servlet không thay thế Servlet container. Nó tích hợp bằng một filter được đăng ký tại container là `DelegatingFilterProxy`, thông thường ủy quyền cho Spring bean có tên `springSecurityFilterChain`; bean này thường là `FilterChainProxy`.

```text
Servlet container FilterChain
   |
   +-- Servlet Filter 1
   |
   +-- DelegatingFilterProxy
   |       |
   |       +-- Spring Bean: springSecurityFilterChain
   |                   |
   |                   +-- FilterChainProxy
   |                           |
   |                           +-- Chọn SecurityFilterChain khớp
   |                           +-- Chạy danh sách Spring Security filters
   |                           +-- Trả về container FilterChain nếu không chặn
   |
   +-- Servlet Filter tiếp theo (nếu đăng ký)
   |
   +-- DispatcherServlet
```

**`DelegatingFilterProxy` làm cầu nối lifecycle:** Servlet container biết Filter được đăng ký, còn Spring ApplicationContext quản lý Spring bean. Nhờ vậy security filter beans có thể dùng dependency injection và security configuration mà không phải khai báo hàng loạt trong `web.xml`.

### 3.1. FilterChainProxy chọn SecurityFilterChain

`FilterChainProxy` nhận một danh sách `SecurityFilterChain`, mỗi chain có một matcher và các security filters. Với request hiện tại, nó chọn **chain đầu tiên khớp theo thứ tự đã cấu hình**. Những chain khác dù cũng có path khớp **không được cộng dồn**.

Ví dụ:

```text
@Order(1): chain API      securityMatcher("/api/**")
                         -> API authentication + authorization

@Order(2): chain website  match any request
                         -> form login + browser protections

GET /api/orders -> chọn API chain (đầu tiên khớp)
GET /home       -> chọn website chain
```

Đây là minh họa rule matching; Spring Security Boot sample thực tế phía dưới chỉ dùng **một** chain để tránh phân tán logic của bài.

**Quan trọng:** Nếu không chain nào match request, request có thể **không được Spring Security bảo vệ** dù vẫn đi qua container/DispatcherServlet. Nếu không có lý do đặc biệt, hãy có fallback chain bảo vệ toàn bộ request phù hợp.

### 3.2. securityMatcher khác requestMatchers

- `http.securityMatcher("/api/**")`: quyết định **chính SecurityFilterChain này** có áp dụng cho request không.
- `authorizeHttpRequests(auth -> auth.requestMatchers("/api/admin").hasRole("ADMIN"))`: là **rule authorization bên trong chain** đã được chọn.
- `.anyRequest().authenticated()`: áp dụng cho các request còn lại **nằm trong phạm vi chain**.
- `permitAll()`: cho phép truy cập ở **bước authorization**, nhưng request **vẫn đi qua security chain** và có thể bị security filters khác xử lý (ví dụ CSRF, headers, CORS).
- `web.ignoring()`: loại request khỏi Spring Security filter chain, khác permitAll và có thể bỏ qua cả security headers/other filters. Chỉ dùng khi hiểu tác động.

**Anti-pattern:**

```java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    );
```

Nếu đây là **chain duy nhất**, đường `/admin` nằm ngoài `/api/**` có thể không có một chain nào bảo vệ. Không suy từ `anyRequest().authenticated()` rằng toàn bộ website đã an toàn.

### 3.3. Các security filters làm việc gì?

Tùy chain, những loại filter thường gặp gồm:

| Nhóm | Thành phần tiêu biểu | Trách nhiệm |
| --- | --- | --- |
| Context | `SecurityContextHolderFilter`, repository liên quan | Tải/quản lý SecurityContext cho request |
| Exploit protection | `HeaderWriterFilter`, `CsrfFilter`, CORS config | Thêm headers, xử lý CSRF/CORS tùy cấu hình |
| Login/authentication | `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, bearer token filter phù hợp | Tạo/kiểm tra Authentication |
| Anonymous/context | `AnonymousAuthenticationFilter` | Cấp anonymous Authentication khi chưa có principal |
| Exception translation | `ExceptionTranslationFilter` | Chuyển AuthenticationException/AccessDeniedException downstream thành xử lý phù hợp |
| Authorization | `AuthorizationFilter` | Quyết định request có được phép đi tiếp |
| Logout/session | `LogoutFilter`, các session-related filters | Xử lý logout/session security theo flow |

Đây không phải danh sách **bắt buộc và theo đúng thứ tự** cho mọi cấu hình. Filter list thay đổi theo form login, HTTP Basic, JWT, CSRF, version và ứng dụng. Đọc log lúc startup hoặc bật DEBUG/TRACE có kiểm soát để biết chain thực tế.

### 3.4. FilterChainProxy có các trách nhiệm không nên né tránh

`FilterChainProxy` là điểm tập trung của Spring Security Servlet, liên quan tới clearing `SecurityContext` và `HttpFirewall`. Đừng bypass FilterChainProxy bằng cách tự đăng ký một số “security filters” rời rạc rồi nghĩ đã nhận đủ các đảm bảo của framework.

## 4. DispatcherServlet: front controller của Spring MVC

Khi Servlet container đã chạy xong các filter và gọi Servlet đích, `DispatcherServlet` xử lý phần Spring MVC:

```text
DispatcherServlet
   |
   +-- HandlerMapping
   |       tìm handler và HandlerExecutionChain
   |
   +-- HandlerAdapter
   |       resolve method args, gọi @Controller/@RestController
   |           |
   |           +-- HandlerInterceptor.preHandle()
   |           +-- Business Service / Repository
   |           +-- Return value
   |           +-- HandlerInterceptor.postHandle() (khi thích hợp)
   |
   +-- Message converters / View resolvers
   |
   +-- HandlerExceptionResolver nếu có lỗi MVC được xử lý
   |
   +-- HandlerInterceptor.afterCompletion() theo lifecycle
   |
   +-- HTTP response trả về Servlet filters
```

Sơ đồ này là mô hình khái niệm, **không** cam kết thứ tự chi tiết của mọi callback trong tất cả tình huống (đặc biệt `@ResponseBody`, async và exception). Spring MVC `HandlerMapping` có thể tìm handler và interceptors, `HandlerAdapter` thực thi handler và xử lý argument binding/return values.

### 4.1. HandlerMapping và HandlerAdapter

Ví dụ:

```java
@RestController
@RequestMapping("/api")
class OrdersController {
    @GetMapping("/orders/{id}")
    Map<String, Object> getOrder(@PathVariable long id) {
        return Map.of("id", id);
    }
}
```

Khi request `GET /api/orders/42` qua filters:

1. DispatcherServlet sử dụng HandlerMapping để tìm handler thích hợp.
2. HandlerAdapter gọi method với argument `id=42` sau khi chuyển đổi kiểu.
3. Return value được viết ra response qua cơ chế message conversion, ví dụ Jackson JSON.
4. Response quay ngược qua các Servlet Filter đã gọi `chain.doFilter`.

Đoạn này là fragment, không phải class Java độc lập: cần Spring MVC dependencies và import `java.util.Map`, `org.springframework.web.bind.annotation.*`.

### 4.2. HttpMessageConverter không phải Servlet Filter

Với `@RequestBody`, message converter có thể parse JSON và đưa đối tượng vào controller; với `@ResponseBody` hoặc `@RestController`, converter có thể serialize return value thành JSON. Đó là xử lý **bên trong Spring MVC**, sau khi security filter cho phép tiếp tục.

Không dùng `HttpMessageConverter` để thay thế kiểm tra Authorization header hoặc request-level protection ở filter layer. Ngược lại, không cần tự parse mọi JSON body trong một Servlet Filter nếu MVC đã có cơ chế binding/validation đúng.

### 4.3. MVC ExceptionResolver khác security exception translation

`@ControllerAdvice` và `HandlerExceptionResolver` xử lý các lỗi nằm trong MVC request processing, chẳng hạn `ResponseStatusException` hoặc exception business do controller ném.

`ExceptionTranslationFilter` của Spring Security xử lý **AuthenticationException** và **AccessDeniedException** được ném từ các filter/logic **downstream** trong security chain theo những điều kiện phù hợp. Nó có thể khởi động `AuthenticationEntryPoint` (ví dụ 401/redirect login) hoặc `AccessDeniedHandler` (ví dụ 403).

**Đừng mặc định** một exception được ném từ servlet filter **trước DispatcherServlet** sẽ được `@ControllerAdvice` bắt. Khi lỗi xuất phát trước MVC, cần handler ở tầng tương ứng, error dispatch hoặc cấu hình exception handling chuyên biệt.

## 5. So sánh Servlet Filter và HandlerInterceptor

| Tình huống | Servlet Filter | HandlerInterceptor |
| --- | --- | --- |
| Chạy trước khi DispatcherServlet tìm handler? | Có, nếu được đăng ký phía trước | Không, cần HandlerMapping tìm được handler |
| Chặn request không đi tới controller? | Có | Có thể chặn sau khi đã chọn handler |
| Có sẵn handler method và annotations? | Không mặc định | Có thể xem `handler` là `HandlerMethod` nếu thích hợp |
| Bọc HttpServletRequest/Response? | Có | Có nhưng không phải cơ chế wrapper container phổ quát |
| Dùng cho authentication nền tảng? | **Thường đúng tầng** (Spring Security Filters) | Không nên thay Spring Security |
| Dùng cho logic MVC-specific? | Có thể nhưng thiếu ngữ cảnh handler | **Phù hợp hơn**, ví dụ đo thời gian một controller handler |
| Bảo vệ request không có handler MVC? | Có | Có thể không chạy nếu không tìm handler |
| Bắt trước static/default Servlet resources? | Tùy registration/mapping | Chỉ với handler MVC phù hợp |
| Ordering | Servlet filter registration và security chain | HandlerMapping + `InterceptorRegistry` |
| Async/error dispatch | Theo DispatcherType, filter policy | Theo lifecycle async/handler mapping của MVC |

`HandlerInterceptor` có `preHandle`, `postHandle`, `afterCompletion`. Nếu viết một interceptor cho authorization, phải hiểu những URL không thuộc MVC handler đó có thể không đi qua interceptor; đó là lý do Spring Security thường thực hiện authentication/authorization request level ở Servlet filter layer.

### 5.1. Interceptor snippet

```java
public class DurationInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {
        request.setAttribute("startedNanos", System.nanoTime());
        return true;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        Long start = (Long) request.getAttribute("startedNanos");
        if (start != null) {
            long elapsed = System.nanoTime() - start;
            // Ghi metric an toàn; không log credentials.
        }
    }
}
```

Đây là fragment cần imports Spring Web MVC/Jakarta Servlet. Nó không chạy độc lập bằng JDK thuần. Interceptor phải được đăng ký thông qua `WebMvcConfigurer.addInterceptors` hoặc một cơ chế MVC phù hợp. Nó không thay thế AuthenticationManager, SecurityFilterChain hay các chính sách CSRF.

## 6. Thứ tự thực thi có thể thay đổi bởi đâu?

Các yếu tố tác động bao gồm:

1. **Servlet Filter registration order**: thứ tự các filter được đăng ký ở Servlet container.
2. **URL patterns và servlet mappings**: filter có được áp dụng cho request không.
3. **Dispatcher types**: `REQUEST`, `FORWARD`, `INCLUDE`, `ASYNC`, `ERROR`.
4. **SecurityFilterChain matchers**: FilterChainProxy chọn **first matching chain**.
5. **Filter order trong chain**: `HttpSecurity.addFilterBefore/After/At` hoặc defaults.
6. **Một filter có gọi `chain.doFilter` không**: nếu không, downstream dừng.
7. **Async/error dispatch và container error page**: có thể bắt đầu một dispatch mới.
8. **HandlerMapping và MVC interceptors**: sau khi DispatcherServlet thực sự được gọi.
9. **Proxy/load balancer/gateway**: có thể xử lý request trước khi tới Servlet container, nhưng không phải Servlet Filter của JVM này.

Đừng vẽ một sơ đồ rồi coi là bảo đảm giống hệt ở mọi request. Hãy test trực tiếp filter chain đang được cấu hình.

### 6.1. Registration của filter trong Spring Boot

Một filter container có thể được đăng ký thông qua `FilterRegistrationBean`:

```java
@Bean
FilterRegistrationBean<MyFilter> myFilterRegistration() {
    FilterRegistrationBean<MyFilter> bean =
        new FilterRegistrationBean<>(new MyFilter());
    bean.addUrlPatterns("/*");
    bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    return bean;
}
```

Đây là fragment cần `MyFilter`, imports và Spring Boot. `setOrder` điều khiển **container registration order**, còn `setDispatcherTypes` giới hạn loại dispatch. Filter ngoài security chain có thể chạy trước hoặc sau DelegatingFilterProxy tùy thứ tự thực tế.

### 6.2. Custom security filter phải được thêm đúng chỗ

Ví dụ một filter cần principal đã được xác thực và chạy trước authorization:

```java
http.addFilterBefore(
    new MyAuditFilter(),
    AuthorizationFilter.class
);
```

Đây là fragment và vị trí chỉ minh họa. Một filter cần authentication nên được đặt **sau** bước authentication thích hợp; đặt sai trước Basic/Bearer/filter login có thể thấy `AnonymousAuthenticationToken` hoặc chưa có Authentication.

**Cảnh báo double registration:** Nếu bạn đánh dấu một custom `Filter` là `@Component`/**`@Bean`** và đồng thời đưa chính instance đó vào `HttpSecurity.addFilterBefore`, Spring Boot có thể **đăng ký nó trực tiếp vào Servlet container** và Spring Security lại gọi nó trong FilterChainProxy. Từ đó filter có thể chạy hai lần hoặc chạy sai vị trí. Nếu chỉ muốn nằm trong security chain, có thể tạo bằng `new` trong chain hoặc vô hiệu hóa container registration cho bean đó qua `FilterRegistrationBean.setEnabled(false)`.

### 6.3. addFilterAt có thay thế filter cũ không?

Tên API dễ gây hiểu nhầm. `addFilterAt(filter, SomeFilter.class)` đặt custom filter vào một vị trí được framework biết, nhưng không nên giả định nó **loại bỏ** một filter cùng vị trí đã tồn tại. Hãy đọc Javadoc/version và kiểm tra chain thực tế, tránh vô tình tạo hai filter ở cùng order.

## 7. OncePerRequestFilter có thật sự “một lần cho toàn bộ HTTP request” không?

`OncePerRequestFilter` của Spring Web giúp triển khai filter với guard chống chạy lại trong một **request dispatch** theo chính sách của class. Nó không tự đảm bảo rằng filter chỉ xuất hiện ở đúng một chain hoặc chỉ có đúng một lần qua **toàn bộ vòng đời** có async/error/forward dispatch.

Các method quan trọng:

- `doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain)` để viết logic;
- `shouldNotFilter(HttpServletRequest)` nếu muốn bỏ qua request cụ thể;
- `shouldNotFilterAsyncDispatch()` để điều khiển async dispatch;
- `shouldNotFilterErrorDispatch()` để điều khiển error dispatch;
- `isAsyncDispatch(...)` và `isAsyncStarted(...)` để nhận diện async state.

**Quan trọng:** DispatcherType và filter registration vẫn phải khớp. Nếu container không map filter cho `ASYNC`, việc override `shouldNotFilterAsyncDispatch()` một mình không khiến container tự gọi filter ở async dispatch.

### 7.1. DispatcherType và các dispatch mới

| DispatcherType | Ngữ cảnh điển hình | Hậu quả |
| --- | --- | --- |
| `REQUEST` | HTTP request ban đầu | Filter thường được gọi ở đây |
| `FORWARD` | Forward nội bộ qua Servlet container | Filter chỉ chạy nếu mapping hỗ trợ loại dispatch |
| `INCLUDE` | Include tài nguyên khác | Tương tự, phụ thuộc mapping |
| `ASYNC` | Servlet async dispatch tiếp tục xử lý | Có thể ở thread khác, filter có thể chạy lại |
| `ERROR` | Servlet error dispatch (ví dụ lỗi 500/`/error`) | Có thể đi qua filters theo cấu hình ERROR |

Vì Spring Boot có thể mapping `/error` qua DispatcherServlet, khi debug lỗi bạn có thể thấy thêm lượt xử lý cho ERROR dispatch. Không đếm log filter một cách đơn giản rồi suy ra controller đã chạy hai lần. Với async, `ThreadLocal` của SecurityContext và MDC cần propagation/lifecycle phù hợp; không tùy tiện giữ mutable state dùng chung giữa threads.

### 7.2. Dùng filter cho trace an toàn

Nếu cần đo request duration, có thể ghi thời điểm trước `chain.doFilter` và ghi kết quả ở `finally`. Nhưng khi response đã commit, không được tùy tiện ghi lỗi JSON thứ hai. Ghi log/metric/trace span phù hợp, không cố ghi thêm body.

## 8. Các trường hợp HTTP và điểm nào xử lý chúng?

| Yêu cầu | Điểm có thể quyết định | Kết quả minh họa | Controller có chạy? |
| --- | --- | --- | --- |
| `GET /public` | Authorization cho phép → DispatcherServlet | 200 | Có nếu mapping tồn tại |
| `GET /api/hello` không Basic credentials | Security authorization/entry point | Thường 401 khi HTTP Basic | Không |
| `GET /api/hello` Basic đúng | Provider xác thực → authorization → MVC | 200 | Có |
| `GET /api/admin` user chỉ có ROLE_USER | Security AuthorizationFilter | Thường 403 | Không |
| `GET /unknown` đã được permitAll, không có MVC handler | DispatcherServlet/handler lookup | 404 | Không có controller phù hợp |
| `POST /public` thiếu CSRF token khi bật CSRF | CsrfFilter | Thường 403 | Không |
| `POST /public` đủ CSRF, chỉ có @GetMapping | MVC handler matching | 405 | Không chạy GET controller |
| `GET /api/fail` controller ném lỗi nghiệp vụ | HandlerExceptionResolver/@ControllerAdvice | Theo mapping lỗi | Có, rồi lỗi được giải quyết |
| URL bị HTTP firewall từ chối | FilterChainProxy/HttpFirewall | Trạng thái tùy request rejection handling | Không |
| SecurityFilterChain không match, không fallback | Không có Spring Security authorization cho URL đó | Tùy MVC/other filters | Có thể có, và có nguy cơ bypass |

Mã 401/403/404/405 phụ thuộc security mechanism/entry point, exception handler, HTTP method, URL mappings và CSRF state. **Không suy ra chỉ từ status rằng controller đã chạy**.

## 9. Ứng dụng Spring Boot 3 minh họa hai tầng Filter và DispatcherServlet

Ta sẽ tạo một Spring MVC application độc lập trong project Boot 3 đã cấu hình Java 17. Mục tiêu là ghi một **trace sự kiện trong HttpServletRequest** để phân biệt:

- Một Servlet Filter được container đăng ký bằng `FilterRegistrationBean`;
- Một `OncePerRequestFilter` **chỉ** nằm trong Spring Security chain;
- `DispatcherServlet` tìm và gọi controller;
- Khi authentication/authorization chặn, controller không chạy;
- Response đi ngược ra các filter gọi `chain.doFilter`.

**Giới hạn:** Trace bằng `request.setAttribute` là để học, dùng `ArrayList` cho request **đồng bộ**. Không giữ trace trong singleton bean hoặc static mutable list dùng chung. Ví dụ không chứng minh thứ tự của mọi filter framework; `TraceSecurityFilter` được đặt ngay trước `AuthorizationFilter`. Không áp dụng nguyên mẫu vào async processing hay production logging chứa credentials.

Cấu trúc:

```text
src/main/java/example/filterflow/
    FilterFlowApplication.java
    TraceEvents.java
    ContainerTraceFilter.java
    SecurityTraceFilter.java
    SecurityConfig.java
    DemoController.java

src/test/java/example/filterflow/
    FilterFlowTest.java
```

### 9.1. Dependencies

Trong project Spring Boot 3 có Gradle plugin, repositories và Java 17 toolchain; thêm vào `build.gradle` Groovy:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây **chỉ là phần dependencies**, không phải build file đầy đủ. Với Maven, dùng starters tương đương và `spring-security-test` ở test scope. Dùng Spring Boot dependency management/BOM cho các phiên bản Spring Security tương thích; không tự ghép JAR Spring Framework và Spring Security khác generation.

### 9.2. FilterFlowApplication.java

```java
package example.filterflow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterFlowApplication.class, args);
    }
}
```

### 9.3. TraceEvents.java: ghi trace theo từng request

```java
package example.filterflow;

import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.http.HttpServletRequest;

public final class TraceEvents {

    private static final String KEY =
        TraceEvents.class.getName() + ".events";

    private TraceEvents() {}

    @SuppressWarnings("unchecked")
    public static List<String> events(HttpServletRequest request) {
        Object current = request.getAttribute(KEY);

        if (current != null) {
            return (List<String>) current;
        }

        List<String> created = new ArrayList<>();
        request.setAttribute(KEY, created);
        return created;
    }

    public static void add(HttpServletRequest request, String event) {
        events(request).add(event);
    }
}
```

List này thuộc một `HttpServletRequest`, không phải cache toàn ứng dụng. Cast trong demo dựa trên giả định chỉ `TraceEvents` ghi attribute KEY; production cần tránh tên attribute collision và điều phối concurrency/async đúng. Không thêm user passwords hoặc Authorization header vào trace.

### 9.4. ContainerTraceFilter.java: Filter ở Servlet container

```java
package example.filterflow;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

public class ContainerTraceFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        TraceEvents.add(http, "container:before");

        try {
            chain.doFilter(request, response);
        } finally {
            TraceEvents.add(http, "container:after");
        }
    }
}
```

Filter này là **Servlet container filter**; nó không tự là thành viên trong Spring SecurityFilterChain. Phần `finally` chạy sau downstream khi call stack unwind. Do JSON body thường được tạo ở controller **trước** phần unwind, những sự kiện `:after` có thể không xuất hiện trong body trả về; integration test đọc trace attribute sau khi request hoàn thành.

### 9.5. SecurityTraceFilter.java: filter nằm trong SecurityFilterChain

```java
package example.filterflow;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class SecurityTraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        TraceEvents.add(request, "security:before");

        try {
            chain.doFilter(request, response);
        } finally {
            TraceEvents.add(request, "security:after");
        }
    }
}
```

**Không đánh dấu `@Component` ở class này.** Nếu đăng ký nó với container và thêm vào Spring Security chain, có nguy cơ double registration. Nó chỉ được tạo bên trong `SecurityConfig`.

### 9.6. SecurityConfig.java: đăng ký outer filter và security filter đúng tầng

```java
package example.filterflow;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    FilterRegistrationBean<ContainerTraceFilter> containerTrace() {
        FilterRegistrationBean<ContainerTraceFilter> registration =
            new FilterRegistrationBean<>(
                new ContainerTraceFilter()
            );

        registration.addUrlPatterns("/*");
        registration.setDispatcherTypes(DispatcherType.REQUEST);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-secret"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-secret"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public", "/unknown", "/error")
                    .permitAll()
                .requestMatchers("/api/hello")
                    .authenticated()
                .requestMatchers("/api/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .addFilterBefore(
                new SecurityTraceFilter(),
                AuthorizationFilter.class
            )
            .build();
    }
}
```

Giải thích từng quyết định:

1. `containerTrace()` trả `FilterRegistrationBean` nên Spring Boot đăng ký `ContainerTraceFilter` với Servlet container; nó được map cho `REQUEST` và `/*`, với order rất sớm để dễ quan sát phần ngoài security. Những filter khác của framework vẫn có thể tồn tại; không suy ra chỉ có đúng hai filter.
2. `SecurityTraceFilter` được đưa vào **bên trong** `FilterChainProxy` bằng `addFilterBefore`. Vì nó không là Filter bean độc lập, Boot không tự đăng ký thêm ở container.
3. `AuthorizationFilter` là điểm neo để minh họa vị trí; trong cấu hình HTTP Basic thông thường, authentication filter được thực thi trước bước authorization. Với một kiến trúc khác, phải xem order thực.
4. `httpBasic` chỉ cho demo localhost. Base64 trong Basic không mã hóa bảo mật; production yêu cầu HTTPS.
5. `/public` được permitAll, **nhưng vẫn đi qua các security filters**.
6. `/api/hello` chỉ cho authenticated user; `/api/admin` yêu cầu `ROLE_ADMIN`.
7. `/unknown` được permitAll nhưng không có controller, nên minh họa MVC 404 thay vì bị Security chặn; `/error` được mở để error dispatch không bị vòng lặp từ chối không cần thiết.
8. `anyRequest().denyAll()` từ chối các URL khác chưa định nghĩa.
9. CSRF không bị tắt. Với POST từ browser/session, security filter có thể trả 403 nếu thiếu CSRF token dù path permitAll.

### 9.7. DemoController.java: DispatcherServlet chọn handler

```java
package example.filterflow;

import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    Map<String, Object> publicInfo(HttpServletRequest request) {
        TraceEvents.add(request, "mvc:controller");
        List<String> steps = List.copyOf(TraceEvents.events(request));

        return Map.of(
            "message", "public",
            "steps", steps
        );
    }

    @GetMapping("/api/hello")
    Map<String, Object> hello(
            HttpServletRequest request,
            Authentication authentication) {

        TraceEvents.add(request, "mvc:controller");
        List<String> steps = List.copyOf(TraceEvents.events(request));

        return Map.of(
            "username", authentication.getName(),
            "steps", steps
        );
    }

    @GetMapping("/api/admin")
    Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
```

Khi `/public` hoặc `/api/hello` chạy, controller copy danh sách event **tại thời điểm nó được gọi**. Vì vậy JSON response chứa `container:before` nếu container filter được áp dụng và `security:before` nếu security filter đã thực thi; JSON không buộc phải chứa các event `:after` xảy ra lúc stack quay ra. `TraceEvents.events(request)` trong test sau request giúp thấy cả các event unwind.

**Không đưa toàn bộ request/response/Authentication object vào JSON** trong ứng dụng thật: có thể lộ cookie, secrets hoặc metadata nhạy cảm.

### 9.8. Chạy ứng dụng với Gradle

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Giả sử app mở ở `http://localhost:8080`, thử:

```bash
# Anonymous public: tới controller
curl -i http://localhost:8080/public

# Anonymous private: security chặn, thường 401
curl -i http://localhost:8080/api/hello

# Password đúng: controller được gọi
curl -i -u reader:reader-demo-secret \
  http://localhost:8080/api/hello

# Password sai: 401, không tới controller
curl -i -u reader:wrong-secret \
  http://localhost:8080/api/hello

# Reader thiếu ROLE_ADMIN: 403
curl -i -u reader:reader-demo-secret \
  http://localhost:8080/api/admin

# Admin được phép: 200
curl -i -u admin:admin-demo-secret \
  http://localhost:8080/api/admin

# Security permitAll nhưng MVC không có handler: 404
curl -i http://localhost:8080/unknown
```

Kỳ vọng JSON của `GET /public` trên embedded container trong một request `REQUEST` thông thường:

```json
{
  "message": "public",
  "steps": [
    "container:before",
    "security:before",
    "mvc:controller"
  ]
}
```

Thứ tự/việc có thêm event khác nếu bạn thay đổi code hoặc filter registration có thể khác. Response này **chỉ mô tả các event do ba class demo ghi**, không liệt kê mọi filter và callback framework. Những HTTP statuses ở trên là kết quả **dự kiến**, không phải log đã chạy trong bài.

Lưu ý bảo mật: HTTP Basic chỉ dùng Base64; sử dụng HTTPS với credential thật. `curl -u` đưa password demo vào command line và có thể bị ghi vào history/process list, nên chỉ thử với local credentials học tập.

## 10. Kiểm thử với Spring Security và MockMvc

Tạo `src/test/java/example/filterflow/FilterFlowTest.java`:

```java
package example.filterflow;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicRequestPassesThroughSecurityFilterAndMvc()
            throws Exception {

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"))
            .andExpect(jsonPath(
                "$.steps", hasItem("security:before")));
    }

    @Test
    void anonymousPrivateRequestIsRejectedBeforeController()
            throws Exception {
        mvc.perform(get("/api/hello"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicCredentialsReachController()
            throws Exception {
        mvc.perform(get("/api/hello")
                .with(httpBasic(
                    "reader", "reader-demo-secret")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"))
            .andExpect(jsonPath(
                "$.steps", hasItem("mvc:controller")));
    }

    @Test
    void invalidBasicCredentialsAreRejected() throws Exception {
        mvc.perform(get("/api/hello")
                .with(httpBasic("reader", "wrong-secret")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedReaderCannotEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "reader", "reader-demo-secret")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithRoleCanEnterAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic(
                    "admin", "admin-demo-secret")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }

    @Test
    void permitAllDoesNotCreateAMvcHandler() throws Exception {
        mvc.perform(get("/unknown"))
            .andExpect(status().isNotFound());
    }

    @Test
    void postWithoutCsrfIsBlockedEvenOnPublicPath()
            throws Exception {
        mvc.perform(post("/public"))
            .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfButOnlyGetMappingIsMethodNotAllowed()
            throws Exception {
        mvc.perform(post("/public").with(csrf()))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void downstreamReturnsThroughSecurityFilterFinally()
            throws Exception {
        MvcResult result = mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andReturn();

        List<String> completedTrace =
            TraceEvents.events(result.getRequest());

        assertThat(completedTrace).containsSubsequence(
            "security:before",
            "mvc:controller",
            "security:after"
        );
    }
}
```

Chạy:

```bash
./gradlew test --tests example.filterflow.FilterFlowTest
```

Windows:

```powershell
.\gradlew.bat test --tests example.filterflow.FilterFlowTest
```

**Kỳ vọng:** cả **10 phương thức test** pass trên một project Spring Boot 3/Spring Security 6.x tương thích khi ghép đúng các file và dependencies. Kết quả này **chưa phải log biên dịch/test đã chạy**; chỉ là expected behavior theo code được trình bày.

Một số điểm tinh tế:

- `@AutoConfigureMockMvc` dựng môi trường servlet mock và Spring Security filters để test MVC/HTTP; nó không phải một embedded Tomcat chạy trên socket thật.
- Vì cách adapter MockMvc đăng ký container filters có thể khác embedded server, test cố ý **không assert bắt buộc `container:before`** trong JSON. Test chỉ dựa vào security filter và controller thuộc chain test.
- `TraceEvents.events(result.getRequest())` cho phép đọc event `security:after` **sau** khi `MockMvc.perform` hoàn tất. Chúng ta kiểm tra thứ tự subsequence chứ không đòi list chỉ có ba event.
- Request `POST /public` không có CSRF token nhận 403 trước MVC. Khi thêm `csrf()`, MVC nhận POST cho URL chỉ có `@GetMapping` và trả 405; điều này minh họa 403 và 405 là lỗi ở **hai tầng khác nhau**.
- Chỉ dùng `@WithMockUser` để kiểm tra authorization là chưa đủ chứng minh HTTP Basic/password authentication thực sự chạy; ở đây test `httpBasic(...)` dùng credentials của user store demo.
- Test 404 chứng minh `permitAll` của security không tự tạo một controller handler.
- `SecurityTraceFilter` được đặt trước `AuthorizationFilter`. Do BasicAuthenticationFilter có thể short-circuit khi credentials sai, không giả định mỗi request sai password đều đã chạy custom trace filter phía sau.
- Các bài test chưa chứng minh filter registration order, async dispatch hoặc error dispatch trên server thật; với nhu cầu đó cần thêm integration test dùng random port/embedded server và logging có kiểm soát.

## 11. Java 17 thuần: mô phỏng FilterChain và “unwind”

Chương trình sau **không dùng Spring hoặc Servlet API**. Nó tự mô phỏng hai Filter, một `Next` chain và một DispatcherServlet giả để bạn tự nhìn thấy cơ chế **trước → xuống sâu → quay lên**. Mô hình cố ý đơn giản, nhưng **biên dịch bằng javac của JDK 17** và cho stdout xác định.

Tạo file `ServletChainModel.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ServletChainModel {

    static class Exchange {
        final boolean authenticated;
        final List<String> events = new ArrayList<>();
        int status = 200;

        Exchange(boolean authenticated) {
            this.authenticated = authenticated;
        }
    }

    @FunctionalInterface
    interface Next {
        void proceed(Exchange exchange);
    }

    @FunctionalInterface
    interface MiniFilter {
        void run(Exchange exchange, Next next);
    }

    static Next buildChain(List<MiniFilter> filters, Next target) {
        Next current = target;

        for (int i = filters.size() - 1; i >= 0; i--) {
            MiniFilter filter = filters.get(i);
            Next downstream = current;
            current = exchange -> filter.run(exchange, downstream);
        }
        return current;
    }

    public static void main(String[] args) {

        MiniFilter outer = (exchange, next) -> {
            exchange.events.add("outer:before");
            try {
                next.proceed(exchange);
            } finally {
                exchange.events.add("outer:after");
            }
        };

        MiniFilter security = (exchange, next) -> {
            exchange.events.add("security:before");
            try {
                if (!exchange.authenticated) {
                    exchange.status = 401;
                    exchange.events.add("security:deny");
                    return; // Không gọi downstream.
                }
                next.proceed(exchange);
            } finally {
                exchange.events.add("security:after");
            }
        };

        Next dispatcher = exchange -> {
            exchange.events.add("dispatcher:handler-mapping");
            exchange.events.add("controller:run");
            exchange.status = 200;
        };

        Next chain = buildChain(
            List.of(outer, security), dispatcher
        );

        for (boolean allowed : new boolean[] {true, false}) {
            Exchange request = new Exchange(allowed);
            chain.proceed(request);

            System.out.println(allowed ? "ALLOWED" : "DENIED");
            for (String event : request.events) {
                System.out.println(event);
            }
            System.out.println("status=" + request.status);
        }
    }
}
```

Chạy:

```bash
javac ServletChainModel.java
java ServletChainModel
```

**Stdout chính xác theo code:**

```text
ALLOWED
outer:before
security:before
dispatcher:handler-mapping
controller:run
security:after
outer:after
status=200
DENIED
outer:before
security:before
security:deny
security:after
outer:after
status=401
```

Diễn giải:

- Khi `authenticated=true`, outer filter cho gọi security filter; security filter cho gọi dispatcher; sau controller, execution quay lại `security:after` rồi `outer:after`.
- Khi `authenticated=false`, security filter set 401 và **không gọi `next.proceed`**. Vì vậy không có `dispatcher:handler-mapping` hoặc `controller:run` trong trace DENIED.
- Hai khối `finally` vẫn chạy dù security filter `return` sớm.
- Đây chỉ là mô phỏng nested call/short-circuit: **không có thực tế** Servlet request, `DelegatingFilterProxy`, `FilterChainProxy`, username/password verification, CSRF hoặc HttpMessageConverter trong chương trình này. Bài mẫu Spring Boot mới minh họa stack thực.

## 12. Khi nào dùng Filter, Interceptor hay lớp bảo mật khác?

| Nhu cầu | Điểm mở rộng thường phù hợp | Cảnh báo |
| --- | --- | --- |
| Logging request ID từ lúc vào Servlet container | `Filter`/`OncePerRequestFilter` với registration đúng | Không log Authorization header/body nhạy cảm |
| Xác thực HTTP Basic, JWT bearer, form login | Spring Security filter chain | Không tự viết auth lại trong controller |
| Phân quyền endpoint | `authorizeHttpRequests` và method security | Đừng chỉ dựa vào URL; kiểm tra object/owner/tenant tại service |
| Bảo vệ CSRF cho cookie-based browser | `CsrfFilter`/Spring Security config | `permitAll` không bỏ CSRF |
| CORS | CORS config tích hợp đúng thứ tự | Preflight cần xử lý trước authentication chặn |
| Gắn correlation ID trên toàn request | Servlet Filter | Tránh MDC leak sang thread/async |
| Kiểm tra thông tin HandlerMethod cụ thể | `HandlerInterceptor` hoặc annotation/method security | Không bao phủ request chưa được MVC map |
| Validate JSON request body | `@Valid`/Bean Validation + MVC | Filter đọc body tùy tiện có thể làm mất stream |
| Đổi HTTP status của lỗi controller | `@ControllerAdvice`/HandlerExceptionResolver | Không chắc bắt lỗi của filter trước MVC |
| Cross-cutting nghiệp vụ tại method | AOP/Service layer | Không thay request security của servlet |
| API Gateway, WAF, reverse proxy | Hạ tầng trước ứng dụng | Không có nghĩa security trong service đã đủ |

### 12.1. Bộ lọc dùng để xác định tenant có nên tin X-Tenant-ID?

Không. Header `X-Tenant-ID` là dữ liệu do client có thể gửi. Một filter có thể parse/normalize nó, nhưng **không được coi nó là bằng chứng user có quyền tenant đó**. Phải xác minh từ principal đã authenticated và server-side membership/claims hợp lệ. Với request cần truy vấn dữ liệu, service/repository còn phải giới hạn theo tenant, owner và data-level authorization.

### 12.2. SecurityContext ở đâu khi đã tới controller?

Với Servlet stack đồng bộ, `SecurityContextHolder` thường sử dụng `ThreadLocal` để giữ Authentication trong xử lý request. Spring Security filter infrastructure có trách nhiệm làm sạch context đúng lifecycle. Không tự lưu SecurityContextHolder trong static global hay tái sử dụng giữa request.

Khi async chuyển threads, không tự giả định ThreadLocal context được lan truyền. Dùng cơ chế tích hợp propagation do Spring Security hỗ trợ khi thực sự cần, kèm kiểm thử async dispatch và thread pool.

## 13. Debug thực tế theo triệu chứng

| Triệu chứng | Nơi bắt đầu kiểm tra | Lý do có thể |
| --- | --- | --- |
| Request không tới controller, 401 | `SecurityFilterChain`, Basic/Bearer filter, entry point | Chưa authenticated hoặc credentials sai |
| Request không tới controller, 403 | CsrfFilter/AuthorizationFilter | CSRF thiếu hoặc user thiếu quyền |
| Request đã permitAll nhưng 404 | HandlerMapping/DispatcherServlet | Không có handler đúng path |
| Đường /api/** được bảo vệ, /admin thì không | `securityMatcher`/fallback chain | Không chain nào match /admin |
| Custom filter chạy hai lần | Boot FilterRegistrationBean/@Component và addFilterBefore | Double registration hoặc dispatch khác |
| ControllerAdvice không bắt lỗi | Lỗi phát sinh ở Filter trước MVC | Không đi qua MVC exception resolver |
| SecurityContext luôn anonymous trong filter | Filter chạy trước authentication | Sai vị trí filter |
| `@RequestBody` rỗng sau filter | Filter đọc stream mà không replay | Request body đã bị tiêu thụ |
| Log filter before có, after không | Exception/response commit, không dùng finally | Path/exception flow |
| Filter chạy lại ở /error | DispatcherType.ERROR | Container tạo error dispatch |
| Async request mất Authentication | Thread switch/context propagation | ThreadLocal không tự đi theo thread |
| Static assets bị 401 | Security matcher/authorization/registration | Static route không permitAll, hoặc khác servlet mapping |
| Login test pass khi @WithMockUser nhưng Basic fail | Test bỏ qua credential verification | Cần test HTTP Basic/form auth thật |
| Response có header sai sau filter finally | Response đã commit | Đặt header sớm hoặc dùng wrapper đúng |
| Phân quyền endpoint pass nhưng lộ dữ liệu user khác | Service thiếu owner/tenant checks | URL rule không thay object-level policy |

### 13.1. Log chain có kiểm soát

Với Spring Security 6.x, bật logging ở môi trường dev:

```properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.web.servlet.DispatcherServlet=DEBUG
```

Không dùng TRACE dài hạn ở production nếu có nguy cơ log lộ dữ liệu nhạy cảm; cần kiểm tra chính xác log format và redaction. Tại startup, Spring Security có thể log danh sách filters được dùng cho mỗi DefaultSecurityFilterChain. Khi debug hãy đối chiếu **URL, HTTP method, dispatcher type, securityMatcher, requestMatcher, filter order và selected handler**.

### 13.2. Có thể đặt breakpoint tại đâu?

Điểm gợi ý:

1. `DelegatingFilterProxy.doFilter` — request có đi qua bridge không?
2. `FilterChainProxy.doFilter` — security chain nào match?
3. Custom `OncePerRequestFilter.doFilterInternal` — có chạy, và lúc đó auth là gì?
4. `AuthorizationFilter` — vì sao cho phép/từ chối?
5. `DispatcherServlet.doDispatch` — đã vào Spring MVC chưa?
6. `RequestMappingHandlerMapping` — handler nào được chọn?
7. `RequestMappingHandlerAdapter` — controller method có được gọi?
8. `HandlerExceptionResolver` — lỗi MVC được giải quyết ở đâu?
9. Servlet container error/async dispatch — có một dispatch khác không?

Đừng gọi `DispatcherServlet` “filter cuối cùng” hay gọi `FilterChainProxy` “Servlet xử lý controller”; hai tên ở hai tầng khác nhau.

## 14. Các lỗi và anti-pattern cần tránh

**1. Nhầm FilterChain với SecurityFilterChain.** Servlet FilterChain chạy filter registrations và Servlet; SecurityFilterChain là danh sách security filters do FilterChainProxy chọn.

**2. Cho rằng DispatcherServlet được gọi đầu tiên.** Servlet filters thường chạy trước; security có thể từ chối không tới MVC.

**3. Dùng Servlet Filter để tự thực hiện mọi authorization.** Dễ bỏ sót SecurityContext, CSRF, exception translation, audit. Tận dụng Spring Security và service-level access policy.

**4. Đặt custom auth filter sai vị trí.** Nếu chạy trước context/authentication setup, current Authentication chưa sẵn hoặc anonymous.

**5. Tạo filter @Component rồi addFilterBefore mà không kiểm tra registration.** Boot có thể auto-register thêm ở container.

**6. Chỉ tạo một SecurityFilterChain cho /api/** và quên fallback.** URL khác có thể không bị Spring Security bảo vệ.

**7. Coi permitAll giống ignoring.** permitAll vẫn qua filters; ignoring có thể bỏ security headers và protection.

**8. Nghĩ filter luôn gọi chain.doFilter.** Nó có thể short-circuit 401/403, redirect hoặc trực tiếp trả response.

**9. Không xử lý finally khi cần cleanup.** Exception downstream có thể làm code sau chain không chạy; dùng try/finally nhưng đừng sửa body nếu response đã commit.

**10. Đọc request InputStream rồi để controller đọc lại.** Có thể khiến `@RequestBody` rỗng; cần wrapper/caching đúng cách.

**11. Nghĩ ControllerAdvice bắt mọi filter exception.** MVC exception resolution có phạm vi riêng; security exception translator cũng có vị trí và loại exception riêng.

**12. Nhầm 404 là Security không hoạt động.** 404 có thể do không có MVC handler trong khi security permitAll vẫn chạy.

**13. Nhầm 403 là role sai.** CSRF cũng thường trả 403 dù path permitAll.

**14. Coi OncePerRequestFilter nghĩa “một lần cho mọi dispatch mãi mãi”.** Async/error/forward có lifecycle và registration riêng.

**15. Hardcode thứ tự filter từ một bài cũ.** Phiên bản/cấu hình quyết định filter list; xem log và test.

**16. Coi ThreadLocal SecurityContext tự lan truyền qua mọi thread.** Async/threadpool cần propagation và cleanup phù hợp.

**17. Test chỉ controller với direct method call.** Bỏ qua filter chain, auth/CSRF, encoding và handler mapping. Cần MockMvc hoặc integration test HTTP thật.

**18. Log URL đầy đủ chứa reset token/query secrets.** Correlation ID không được biến thành nguồn leak credentials.

**19. Dùng @Order của SecurityFilterChain thay FilterRegistrationBean order.** Đây là hai cấp chọn/thứ tự khác nhau.

**20. Bỏ kiểm tra owner/tenant vì API đã có hasRole.** Role cấp tính năng không chứng minh được quyền trên từng resource.

## 15. Checklist khi thiết kế một request flow

**Container/Servlet**

- [ ] Biết Servlet nào thực sự nhận URL, mapping là gì?
- [ ] Nắm những FilterRegistrationBean/web.xml/Servlet filters đang được dùng?
- [ ] Filter order và DispatcherType phù hợp với threat model?
- [ ] Filter nào có thể short-circuit hoặc wrap request/response?
- [ ] Async/error dispatch và response commit được xử lý an toàn?

**Spring Security**

- [ ] `DelegatingFilterProxy` đã nối `FilterChainProxy` đúng không?
- [ ] Mỗi URL quan trọng đều match một SecurityFilterChain dự định?
- [ ] Có fallback chain khi cấu hình nhiều chains?
- [ ] `securityMatcher` khác `authorizeHttpRequests.requestMatchers` được dùng đúng?
- [ ] Custom security filter không double registration?
- [ ] Đặt filter sau context/authentication và trước authorization khi phù hợp?
- [ ] AuthenticationEntryPoint, AccessDeniedHandler và CSRF hoạt động đúng?
- [ ] Có authorization trên method/object/tenant khi yêu cầu?
- [ ] Không log credentials, token, cookie và dữ liệu nhạy cảm?

**Spring MVC**

- [ ] `DispatcherServlet` map tới handler/controller đúng?
- [ ] Có test 404/405 và lỗi binding/validation?
- [ ] MVC interceptor chỉ được dùng cho đúng trách nhiệm?
- [ ] `@ControllerAdvice`/exception resolver không bị dùng nhầm cho filter errors?
- [ ] HttpMessageConverter xử lý request/response body đúng?
- [ ] Test JSON/handler mapping và security cùng lúc bằng MockMvc?

**Kiểm thử và quan sát**

- [ ] Có integration test request public, authenticated, wrong credential và forbidden?
- [ ] Có test CSRF 403 so với authorization 403?
- [ ] Có trace trước/sau chain và short-circuit minh họa?
- [ ] Có xem security startup logs/selected chain đúng môi trường?
- [ ] Test filter double-registration/async/ERROR nếu ứng dụng thực có?
- [ ] Không khẳng định kết quả chưa thực thi là log chạy thật?

## 16. Tự kiểm tra kiến thức

**1.** Trong Spring MVC Servlet stack, component nào thường được Servlet container gọi trước DispatcherServlet?  
**Đáp án:** Những Servlet Filter đã đăng ký phù hợp với request, theo filter chain.

**2.** `jakarta.servlet.FilterChain` làm gì?  
**Đáp án:** Cho filter tiếp tục gọi các filter còn lại và Servlet đích thông qua `chain.doFilter`.

**3.** Nếu một filter không gọi `chain.doFilter` thì sao?  
**Đáp án:** Những downstream filters và Servlet không chạy trong nhánh đó.

**4.** Vì sao output “A before, B before, Controller, B after, A after” hợp lý?  
**Đáp án:** Do các lời gọi lồng nhau và stack unwind khi downstream trả về.

**5.** DispatcherServlet là Servlet hay Filter?  
**Đáp án:** Là Servlet/front controller của Spring MVC.

**6.** `DelegatingFilterProxy` làm gì?  
**Đáp án:** Bridge container Filter với Spring-managed Filter bean, thường là springSecurityFilterChain.

**7.** `FilterChainProxy` chọn bao nhiêu SecurityFilterChain khi nhiều matcher cùng khớp?  
**Đáp án:** Chain đầu tiên khớp theo thứ tự, không hợp nhất tất cả.

**8.** `securityMatcher` khác `requestMatchers` trong authorizeHttpRequests ra sao?  
**Đáp án:** Cái đầu chọn phạm vi security chain, cái sau đặt rule trong chain đó.

**9.** Tại sao permitAll không đồng nghĩa bỏ qua CSRF?  
**Đáp án:** Authorization rule permitAll không vô hiệu hóa CsrfFilter/security filters.

**10.** `HandlerMapping` và `HandlerAdapter` khác nhau chỗ nào?  
**Đáp án:** Mapping tìm handler; adapter dùng contract phù hợp để thực thi handler.

**11.** HandlerInterceptor thuộc trước hay sau DispatcherServlet?  
**Đáp án:** Bên trong MVC handler execution sau khi DispatcherServlet bắt đầu xử lý và tìm handler thích hợp.

**12.** Vì sao ControllerAdvice không chắc bắt được exception từ Filter trước DispatcherServlet?  
**Đáp án:** Nó tham gia MVC exception handling, không bao trùm mọi Servlet filter ngoài MVC.

**13.** Vì sao custom Filter vừa @Component vừa addFilterBefore có thể chạy hai lần?  
**Đáp án:** Có thể bị Spring Boot đăng ký trực tiếp với Servlet container và FilterChainProxy gọi thêm.

**14.** SecurityContext có tự động đi qua mọi thread trong async không?  
**Đáp án:** Không. ThreadLocal cần propagation/lifecycle đúng.

**15.** GET URL permitAll nhưng không có controller thường gặp status nào?  
**Đáp án:** 404 từ MVC/container khi không có handler phù hợp.

**16.** Vì sao POST vào endpoint public có thể 403 dù user không cần login?  
**Đáp án:** CSRF protection vẫn áp dụng cho unsafe HTTP methods với cấu hình mặc định.

**17.** Có nên sửa headers/body ở finally của Filter bất kể response đã commit?  
**Đáp án:** Không; cần thiết kế response wrapper/lifecycle đúng, tránh ghi khi đã commit.

**18.** Nếu Filter chỉ chạy ở REQUEST, override `shouldNotFilterErrorDispatch()` có chắc làm nó chạy ở ERROR không?  
**Đáp án:** Không; còn cần container registration mapping phù hợp với `DispatcherType.ERROR`.

## 17. Tài liệu tham khảo chính thức

- [Spring Security 6.5 – Servlet Architecture: FilterChain, DelegatingFilterProxy, FilterChainProxy](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – Configuring Multiple SecurityFilterChains](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Framework 6.2 – DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html)
- [Spring Framework 6.2 – DispatcherServlet Request Processing](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/sequence.html)
- [Spring Framework 6.2 – Special Bean Types](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/special-bean-types.html)
- [Spring Framework 6.2 – Servlet Filters and OncePerRequestFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Boot 3.5 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/)
