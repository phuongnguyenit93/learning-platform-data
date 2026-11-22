# OncePerRequestFilter và hành vi với async/error dispatch trong Spring MVC

## 1. Tại sao “once per request” có thể gây hiểu nhầm?

Trong một ứng dụng Spring MVC, ta thường muốn ghi trace ID, đo thời gian xử lý, thêm HTTP headers hoặc tạo context phục vụ logging. Đặt logic tại Servlet Filter là hợp lý vì Filter hoạt động trước/sau servlet trong chuỗi xử lý.

Nhưng một HTTP request có thể được container **dispatch nhiều lần**:

- Lần đầu: `DispatcherType.REQUEST`.
- Ứng dụng bắt đầu xử lý bất đồng bộ và kết quả được dispatch trở lại: `DispatcherType.ASYNC`.
- Servlet container chuyển tới trang/endpoint lỗi: `DispatcherType.ERROR`.

Nếu một filter chạy lại trong cùng request, việc tạo trace mới, đếm request, gửi sự kiện nghiệp vụ hoặc bọc response nhiều lần có thể gây sai lệch. Spring cung cấp `org.springframework.web.filter.OncePerRequestFilter` để quản lý việc filter **chỉ thực hiện một lần trong một request dispatch trên một thread**, với quy tắc rõ về xử lý lại ở `ASYNC` hoặc `ERROR`.

**Không hiểu tên class thành “doFilterInternal chạy đúng một lần duy nhất trong toàn bộ vòng đời một HTTP request bất kể dispatch/thread”.** Nếu bạn chủ động bật tham gia `ASYNC`/`ERROR`, `doFilterInternal` có thể chạy ở những dispatch riêng sau đó. Còn một `ERROR` dispatch lồng bên trong chuỗi `REQUEST` có thể đi qua `doFilterNestedErrorDispatch` thay vì `doFilterInternal`.

### Mục tiêu

Sau bài học bạn có thể:

1. Phân biệt Servlet `Filter`, Spring MVC `HandlerInterceptor`, `OncePerRequestFilter` và các kiểu dispatch.
2. Giải thích chính xác “already filtered” request attribute, cách set/remove bằng `try/finally` và hệ quả cho nhiều dispatch.
3. Phân tích `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()`, `shouldNotFilter(HttpServletRequest)`, `isAsyncDispatch()`, `isAsyncStarted()`, `doFilterNestedErrorDispatch()`.
4. Kết hợp **hai lớp cấu hình**: filter được Servlet container **đăng ký cho dispatcher types nào** và filter **có chủ đích skip dispatch nào**.
5. Thiết kế logic tracing, logging, wrapping, thread-local, security và cleanup không bị chạy lặp sai.
6. Viết demo Spring Boot 3/Java 17 và kiểm thử bằng các Servlet mocks; hiểu giới hạn của `MockMvc` khi mô phỏng `ERROR` dispatch thực.

**Bối cảnh:** Spring MVC Servlet stack, Spring Framework 6.2.x, Spring Boot 3.x, Java 17+, Jakarta Servlet API. Trong Spring Boot 3/Spring Framework 6 các import là `jakarta.servlet.*`, không phải `javax.servlet.*` của hệ thống đời cũ.

## 2. Filter nằm ở đâu trong luồng HTTP?

Luồng synchronous điển hình:

```text
Client
   │ HTTP request
   ▼
Servlet container (Tomcat/Jetty/Undertow)
   │
   ├─ Filter A.doFilter(...)
   │    ├─ mã trước filterChain
   │    ▼
   │    Filter B.doFilter(...)
   │         └─ DispatcherServlet
   │              └─ Spring MVC HandlerInterceptor
   │                   └─ Controller
   │                   └─ View/HTTP message converter
   │
   ├─ mã sau filterChain của Filter B
   └─ mã sau filterChain của Filter A
   ▼
HTTP response
```

Servlet Filter thuộc **Servlet container filter chain**, nên có thể thấy request trước khi Spring MVC chọn handler, kể cả đường đi không tới controller (tùy mapping). `HandlerInterceptor` thuộc **Spring MVC HandlerExecutionChain** và hoạt động sau handler mapping; interceptor không thay thế hoàn toàn Servlet Filter.

Khi một controller dùng `Callable<T>`, `DeferredResult<T>` hoặc cơ chế Servlet async, thread ban đầu có thể trả quyền điều khiển về container **trước khi response hoàn tất**. Filter chain có thể kết thúc một lượt `REQUEST` rồi có lượt `ASYNC` mới. Điều này ảnh hưởng tới việc đo thời gian, kết thúc trace, set header và dọn dẹp thread-local.

### 2.1. Bảng DispatcherType

| DispatcherType | Khi nào có thể xuất hiện | Điểm cần lưu ý |
| --- | --- | --- |
| `REQUEST` | Client gửi yêu cầu HTTP ban đầu | Đây là dispatch đầu tiên thường gặp |
| `ASYNC` | Servlet async hoàn tất một giai đoạn và dispatch lại | Có thể chạy trên thread khác; không tự động được mọi filter tham gia |
| `ERROR` | Container thực hiện error-page dispatch | Có thể tách thành filter chain mới hoặc lồng trong REQUEST |
| `FORWARD` | Một servlet forward nội bộ | Một request có thể có nhiều lượt dispatch |
| `INCLUDE` | Một servlet/include resource khác | Tùy cách đăng ký filter có được gọi lại |

`OncePerRequestFilter` đặc biệt có API skip cho `ASYNC` và `ERROR`. Với `FORWARD`/`INCLUDE`, cơ chế “already filtered” và dispatcher mapping vẫn quan trọng; không được suy diễn rằng class chỉ bao giờ liên quan tới ba kiểu đầu. Trong Spring MVC, `forward:...` có thể tạo `FORWARD` dispatch nhưng chỉ khi Servlet container thực hiện dispatch tương ứng.

**Không đồng nhất HTTP request với Servlet dispatch:** một HTTP request có thể đi qua nhiều dispatch, và một dispatch chỉ là một chặng của quá trình xử lý.

## 3. OncePerRequestFilter cung cấp gì?

Class trừu tượng:

```java
public abstract class OncePerRequestFilter extends GenericFilterBean {

    @Override
    public final void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        // Spring quản lý việc skip, marker và gọi doFilterInternal.
    }

    protected abstract void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException;
}
```

*Đây là trích yếu API mang tính giáo dục, không phải bản sao đầy đủ mã nguồn Spring. Nên override `doFilterInternal`, không override phương thức `doFilter` của base class.*

Sơ đồ quyết định đơn giản hóa từ implementation Spring 6.2:

```text
doFilter(request,response,chain)
       │
       ├─ Request/response không phải HTTP?
       │      └─ lỗi ServletException
       │
       ├─ Dispatch bị bỏ qua theo shouldNotFilterAsyncDispatch /
       │  shouldNotFilterErrorDispatch hoặc shouldNotFilter?
       │      └─ chain.doFilter, KHÔNG gọi doFilterInternal
       │
       ├─ Đã có marker "already filtered" trên request?
       │      ├─ DispatcherType.ERROR
       │      │     └─ doFilterNestedErrorDispatch(...)
       │      └─ Kiểu khác
       │            └─ chain.doFilter, không chạy doFilterInternal
       │
       └─ Chưa có marker
             ├─ request.setAttribute(marker, true)
             ├─ doFilterInternal(...)
             │     └─ thường gọi chain.doFilter(...)
             └─ finally request.removeAttribute(marker)
```

Đây không phải một khóa toàn cục hoặc bộ nhớ “request ID đã xử lý trong 24 giờ”. Marker là **request attribute**, tồn tại trong phạm vi lượt filter đang thực thi và bị dọn ở `finally` của lượt đó.

### 3.1. Already-filtered attribute

Base class mặc định xây tên attribute từ tên filter cụ thể cộng hậu tố `.FILTERED`; khi chưa có tên đầy đủ có thể dùng class name. API:

- `getAlreadyFilteredAttributeName()`: xác định tên marker, có thể override khi thật sự cần.
- `ALREADY_FILTERED_SUFFIX`: hằng hậu tố dùng cho marker.
- Marker thường được đặt trước khi gọi `doFilterInternal`, xóa trong `finally` sau khi nó hoàn thành, kể cả khi chain ném exception.

Ví dụ minh họa:

```text
request.getAttribute("auditFilter.FILTERED") == null
    → set TRUE
    → chạy doFilterInternal
        → nếu trong đó chain khiến cùng filter được gọi lồng:
           marker vẫn TRUE → không chạy doFilterInternal lần nữa
    → finally remove attribute
```

Tên chính xác phụ thuộc filter registration/bean name. **Đừng cài logic ứng dụng phụ thuộc vào chuỗi marker nội bộ**, và đừng tự gán/chỉnh marker của framework nếu không có lý do được kiểm chứng.

**Hệ quả:** nếu `REQUEST` đã kết thúc lượt filter và request sau đó đi vào `ASYNC` dispatch, marker trước đã bị gỡ; nếu filter được đăng ký và không skip `ASYNC`, `doFilterInternal` có thể chạy tiếp một lượt mới. Đây là hành vi có chủ đích.

### 3.2. Filter không tự gọi chain thì sao?

Một filter chặn request có thể không gọi `filterChain.doFilter(...)` (ví dụ từ chối request do xác thực); controller không chạy. Nếu đã gọi chain, logic sau chain có thể chạy lại khi Servlet đã async-started nhưng **response chưa hoàn tất**. Để phân biệt, xem `isAsyncStarted(request)`.

Mọi đoạn code phải giữ nguyên contract Servlet: không ghi response hai lần, không sử dụng response sau khi đã commit, và không bỏ qua exception/cleanup một cách tình cờ.

## 4. ASYNC dispatch: cùng HTTP request nhưng nhiều lượt xử lý

Một controller minh họa:

```java
@GetMapping("/slow")
Callable<String> slow() {
    return () -> "finished";
}
```

*Đây là handler body minh họa; đặt trong `@RestController` với import `Callable`, `GetMapping`. Chạy thực tế còn phụ thuộc Servlet async support.*

Trình tự khái quát:

```text
Thread T1                                      Thread T2 / T3
─────────                                      ──────────────
HTTP REQUEST
  → Filter.dispatch=REQUEST
  → DispatcherServlet/controller
  → MVC bắt đầu async
  → REQUEST filter chain return
  → marker finally removed
                                               Callable chạy trong executor
                                               result được lưu
                                               Servlet ASYNC dispatch
                                                 → Filter.dispatch=ASYNC (*)
                                                 → DispatcherServlet hoàn tất response
                                                 → filter chain return
Response hoàn tất
```

(*) Chỉ khi filter **được map cho ASYNC** và không skip ASYNC.

### 4.1. shouldNotFilterAsyncDispatch()

Mặc định method trả **true**: `OncePerRequestFilter` bỏ qua các lượt `ASYNC` trong logic `doFilterInternal`.

```java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return false; // muốn doFilterInternal tham gia ASYNC dispatch
}
```

Trả `false` **không đủ nếu Servlet container chưa đăng ký filter cho DispatcherType.ASYNC**. Cần cấu hình cả filter registration, ví dụ `FilterRegistrationBean#setDispatcherTypes(REQUEST, ASYNC)` và `setAsyncSupported(true)` nếu ứng dụng dùng async.

Khi trả false, filter có thể chạy **một lần trong từng thread/dispatch tham gia**. Điều đó hữu ích cho:

- Thiết lập thread-local MDC/trace context cho thread xử lý lượt ASYNC.
- Áp dụng context phục vụ response trong giai đoạn sau.
- Dọn tài nguyên theo lifecycle của từng dispatch.
- Thêm header sau khi response thật sự hoàn tất (nếu chưa commit).

Nhưng **không** dùng nó để mặc định gửi email, ghi hóa đơn hoặc tăng số “số lượng HTTP requests” ở mỗi lần `doFilterInternal`: một HTTP request có thể làm các side effect ấy xảy ra nhiều lần.

### 4.2. isAsyncDispatch() khác isAsyncStarted()

| API | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| `isAsyncDispatch(request)` | “Lượt hiện tại có là ASYNC dispatch không?” | Trong lượt xử lý tiếp theo sau async |
| `isAsyncStarted(request)` | “Request đang ở chế độ async, lượt hiện tại chưa phải lượt cuối?” | Sau controller tạo Callable nhưng trước khi hoàn tất request |

Dùng trong filter:

```java
boolean redispatch = isAsyncDispatch(request);
try {
    filterChain.doFilter(request, response);
} finally {
    boolean stillAsync = isAsyncStarted(request);
    if (!stillAsync) {
        // Trong nhiều luồng thông thường, đây là lúc
        // có thể thực hiện tác vụ hoàn tất của lượt xử lý.
    }
}
```

Đây chỉ là mẫu quan sát trạng thái. Nếu filter **không tham gia ASYNC dispatch**, nó không có cơ hội chạy `finally` ở lượt cuối; khi đó cần `AsyncListener`, callback MVC hoặc cơ chế phù hợp khác để phát sự kiện “HTTP request thực sự hoàn tất”.

### 4.3. AsyncListener khi cần theo dõi toàn bộ vòng đời

Để đo thời gian end-to-end từ request đầu tiên tới khi async hoàn tất, các lựa chọn gồm:

- Đặt start timestamp vào request attribute ngay lượt `REQUEST`, không reset trên redispatch.
- Nếu filter tham gia mọi ASYNC dispatch, kết thúc đo khi response thật sự hoàn tất và lifecycle đã rõ; không đo lặp trên mỗi lần dispatch.
- Với workflow đặc biệt, đăng ký `AsyncListener#onComplete` / `onError` / `onTimeout` và xử lý đăng ký lại ở `onStartAsync` khi async cycle mới bắt đầu; cần hiểu rằng việc gắn listener có thể phụ thuộc thời điểm gọi `request.startAsync()`.
- Spring MVC còn có `CallableProcessingInterceptor` và `DeferredResultProcessingInterceptor` cho những điểm hook MVC-specific.
- Tránh dùng một thread-local duy nhất để ghi trạng thái toàn HTTP request khi request có thể chuyển thread.

**Lưu ý về context propagation:** request attributes đi theo object Servlet request, nhưng `ThreadLocal`/MDC **không tự di chuyển sang executor thread**. Filter tham gia `ASYNC` dispatch cũng không nhất thiết chạy trên thread mà `Callable` được execute. Muốn truyền context vào worker thread, hãy cấu hình executor decorator/context propagation phù hợp.

## 5. ERROR dispatch: tách chain và nested dispatch

Servlet container có thể tiến hành xử lý lỗi theo một trong hai hình thức cần phân biệt.

### 5.1. ERROR dispatch riêng sau REQUEST

Lược đồ thường gặp:

```text
REQUEST dispatch
  → filter.doFilterInternal(REQUEST)
  → downstream báo lỗi / sendError
  → filter cleanup/finally, marker bị remove

ERROR dispatch mới (có thể thread khác)
  → filter.doFilterInternal(ERROR), NẾU:
       • filter registration có DispatcherType.ERROR
       • shouldNotFilterErrorDispatch() == false
  → /error hoặc error page
```

Theo mặc định, `shouldNotFilterErrorDispatch()` trả **true**, tức là không đưa `ERROR` dispatch vào `doFilterInternal`.

Để tham gia:

```java
@Override
protected boolean shouldNotFilterErrorDispatch() {
    return false;
}
```

Dù vậy, không có registration `DispatcherType.ERROR` thì container không gọi filter ở error chain. Và “doFilterInternal chạy trong ERROR” không có nghĩa filter tự nhận được mọi Java exception: exceptions có thể đã được xử lý ở controller bằng `@ExceptionHandler` mà không có Servlet ERROR dispatch.

### 5.2. Nested ERROR dispatch trong cùng REQUEST chain

Trên một số Servlet container, sau `response.sendError(...)` hoặc tình huống tương tự, ERROR dispatch có thể xảy ra **lồng ngay trong REQUEST chain cùng thread**, khi marker still present.

```text
Filter.doFilter(REQUEST)
  └── set already-filtered marker = TRUE
      └── doFilterInternal(REQUEST)
          └── chain.doFilter(...)
              └── container nested ERROR dispatch
                  └── Filter.doFilter(ERROR)
                      ├── marker vẫn TRUE
                      └── doFilterNestedErrorDispatch(...)
  └── finally remove marker
```

Trong trường hợp nested, Spring gọi `doFilterNestedErrorDispatch(...)`, **không tự gọi lại `doFilterInternal(...)`**, nếu filter không skip ERROR. Mặc định nested-error hook chỉ chuyển tiếp `filterChain.doFilter(...)`.

Một số container có thể đưa request/response về wrapper gốc ở nested ERROR. Nếu filter đã bọc request/response để sửa input/body/header, subclass có thể cần **bọc lại trong `doFilterNestedErrorDispatch`** để giữ hành vi mong muốn.

### 5.3. Override doFilterNestedErrorDispatch

```java
@Override
protected void doFilterNestedErrorDispatch(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain filterChain) throws ServletException, IOException {

    // Nếu filter đang dùng custom wrappers, có thể bọc lại
    // request/response tại đây sau khi đánh giá đúng container.
    filterChain.doFilter(request, response);
}
```

Hook này được Spring Framework thêm từ 5.1.9. **Đừng gọi `doFilterInternal` một lần nữa chỉ để “có log”** trừ khi bạn thật sự muốn lặp đúng toàn bộ logic và đã chứng minh an toàn. Nếu dùng wrapper, có thể cần riêng một hàm nhỏ “wrap only” cho nested-error.

### 5.4. Bảng đối chiếu

| Trạng thái | Marker còn? | Mặc định skip? | Nếu không skip và filter đã được map |
| --- | --- | --- | --- |
| REQUEST đầu tiên | Không | Không | `doFilterInternal(REQUEST)` |
| REQUEST lồng, marker còn | Có | Không | Chỉ `chain.doFilter` |
| ASYNC dispatch riêng sau REQUEST | Thường đã remove | **Có** | `doFilterInternal(ASYNC)` |
| ERROR dispatch riêng sau REQUEST | Thường đã remove | **Có** | `doFilterInternal(ERROR)` |
| ERROR lồng khi REQUEST marker còn | Có | **Có** | `doFilterNestedErrorDispatch(ERROR)` |
| FORWARD/INCLUDE lồng khi marker còn | Có | Không có flag async/error áp dụng | Thường chỉ `chain.doFilter` |

Không suy đoán số lần chạy tuyệt đối chỉ từ bảng: filter registration, container, async cycles và cách MVC trả lỗi quyết định các dispatch có thật. Có nhiều lượt ASYNC trong một request nếu async lifecycle tiếp tục; mỗi lượt phải được xét theo semantics của container và marker.

## 6. Hai lớp quyết định: FilterRegistrationBean và shouldNotFilter*

Một nhầm lẫn thường gặp là nghĩ override `shouldNotFilterAsyncDispatch() = false` **tự đăng ký** filter với servlet container. Thực tế phải xét đồng thời:

1. **Registration layer**: filter được map vào URL patterns và `DispatcherType.REQUEST/ASYNC/ERROR/...` nào; có cho phép async không?
2. **OncePerRequestFilter layer**: nếu filter đã được gọi, `shouldNotFilterAsyncDispatch()`, `shouldNotFilterErrorDispatch()` và `shouldNotFilter(request)` có bỏ qua logic hay không?

Ví dụ đăng ký tường minh trong Spring Boot 3:

```java
@Bean
FilterRegistrationBean<DispatchTraceFilter> traceRegistration() {
    FilterRegistrationBean<DispatchTraceFilter> reg =
            new FilterRegistrationBean<>(new DispatchTraceFilter());

    reg.setName("dispatchTraceFilter");
    reg.setUrlPatterns(List.of("/*"));
    reg.setDispatcherTypes(EnumSet.of(
            DispatcherType.REQUEST,
            DispatcherType.ASYNC,
            DispatcherType.ERROR));
    reg.setAsyncSupported(true);
    reg.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
    return reg;
}
```

*Đoạn minh họa của project đầy đủ ở mục 9; cần import `FilterRegistrationBean`, `DispatcherType`, `EnumSet`, `List`, `Ordered` và `@Bean`.*

Nếu không cần async/error, chỉ map REQUEST để giảm side effects và overhead. Nếu cần, đặt mapping và flags nhất quán rồi kiểm thử trên Servlet container sẽ triển khai thực tế. `setAsyncSupported(true)` không có nghĩa mọi handler tự chạy async; nó chỉ cho phép request chuyển sang async khi các phần còn lại hỗ trợ.

**Tránh đăng ký filter hai lần**: một class gắn `@Component` đồng thời lại tự tạo `FilterRegistrationBean<>(filter)` có thể dẫn đến mapping trùng hoặc hành vi khó đoán tùy auto registration. Chọn một chiến lược đăng ký rõ ràng. Demo tạo `new DispatchTraceFilter()` chỉ bên trong bean registration, **không gắn @Component cho filter**.

### 6.1. shouldNotFilter(HttpServletRequest)

Override khi một số URL hoặc yêu cầu không cần filter:

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return request.getRequestURI().startsWith("/assets/");
}
```

Nếu ứng dụng chạy với context path, kiểm tra cách tạo path. Không dựa vào `getRequestURI()` và prefix một cách thiếu kiểm thử khi mapping có forwarded paths, percent-encoding hoặc context path. Với bảo mật, ưu tiên framework matchers đúng semantics; không tự tạo lỗ hổng vì skip endpoint nhạy cảm.

**Thứ tự thực thi:** `shouldNotFilter(request)` được xét khi filter đã nhận request. Nó không thay thế Servlet URL pattern mapping hay Spring Security authorization.

## 7. Dùng filter cho từng mục đích mà không bị lặp sai

### 7.1. Correlation/trace ID

Một request có thể đi qua REQUEST, ASYNC, ERROR. Tạo ID **một lần** và lưu trong request attribute:

```java
static final String TRACE_KEY = "example.traceId";

String trace = (String) request.getAttribute(TRACE_KEY);
if (trace == null) {
    trace = UUID.randomUUID().toString();
    request.setAttribute(TRACE_KEY, trace);
}

try {
    MDC.put("traceId", trace);
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("traceId");
}
```

*Đây là đoạn minh họa bên trong một filter, cần import UUID và MDC/logging API. Nó không bao trùm executor thread của Callable; phần truyền context cho worker cần cấu hình riêng.*

Với nhiều dispatch, request attribute lưu trace ID xuyên qua các lượt, còn MDC là **per-thread** và phải set/remove khi vào/ra từng thread. Filter tham gia ASYNC redispatch chỉ gắn MDC cho chính thread redispatch. Dùng executor decoration, task wrapper hoặc Spring context-propagation phù hợp nếu muốn trace trong thread thực thi `Callable`.

### 7.2. Đo thời gian toàn request

Không đo “tổng request time” bằng một biến local bắt đầu lại trong mỗi `doFilterInternal`:

```java
long start = System.nanoTime();
filterChain.doFilter(request, response);
long elapsed = System.nanoTime() - start;
```

Với async, elapsed trên lượt REQUEST có thể chỉ phản ánh giai đoạn khởi động async, không phải thời gian tới khi response xong.

Một thiết kế tốt hơn:

1. Tạo start timestamp **một lần** trong request attribute.
2. Chọn một điểm “request completed” rõ ràng: listener `AsyncListener#onComplete`, callback async MVC hoặc giai đoạn cuối nếu lifecycle đã được kiểm chứng.
3. Dùng marker khác để đảm bảo metric summary được phát đúng một lần, ngay cả ERROR dispatch.
4. Dùng monotonic clock (`System.nanoTime()`) để tính duration; dùng wall clock nếu cần timestamp hiển thị.
5. Tách metric **dispatcher count** (có thể > 1) khỏi metric **HTTP request count** (mục tiêu 1).

### 7.3. Security/filter chain

Spring Security cũng dùng Servlet Filters và nhiều implementation có cơ chế kiểu once-per-request, async/error handling riêng. Không áp chính sách “bỏ qua ASYNC/ERROR” một cách ngẫu nhiên vì có thể ảnh hưởng tới context, response hoặc error pages. Trình tự filter và dispatcher mapping thuộc thiết kế security.

Không nên tự làm authentication bằng kiểm tra token đơn giản trong filter demo rồi coi như tương đương Spring Security. Ưu tiên cấu hình Spring Security đầy đủ và kiểm thử cả trạng thái anonymous/authenticated, ASYNC và ERROR khi có yêu cầu.

### 7.4. Request/response wrappers

Một filter có thể bọc request/response để ghi payload hoặc điều chỉnh header. Các rủi ro:

- Đọc request body trong filter trước controller mà không hỗ trợ cached/re-readable body khiến controller không đọc được nữa.
- Bọc response rồi quên copy buffer ra response gốc.
- Với ERROR nested dispatch, container có thể thay wrapper về bản gốc. Override `doFilterNestedErrorDispatch` để bọc lại khi thật sự cần.
- Async cần wrapper có lifecycle phù hợp; không đọc response đã commit.
- Logging body có thể lộ mật khẩu, token, thông tin cá nhân; giới hạn kích thước và mask dữ liệu nhạy cảm.

Nếu dùng `ContentCachingRequestWrapper` hoặc `ContentCachingResponseWrapper`, hãy đọc Javadoc: request wrapper không tự đọc body trước nếu downstream chưa đọc; response wrapper cần thao tác copy body phù hợp. Đừng giả định chỉ việc tạo wrapper là có thể đọc lại response ở mọi dispatch.

## 8. Ví dụ thông thường vs async vs error

### 8.1. REQUEST đồng bộ

```text
Client GET /sync
  → REQUEST filter doFilterInternal: count=1
  → Controller "sync"
  → Filter complete
  → HTTP 200
```

### 8.2. REQUEST bắt đầu async và ASYNC dispatch

```text
Client GET /async
  → REQUEST filter doFilterInternal: count=1
  → Callable trả về / MVC bắt đầu async
  → filter REQUEST kết thúc, marker bị remove
  → Servlet ASYNC dispatch
  → ASYNC filter doFilterInternal: count=2
  → MVC hoàn tất response
  → HTTP 200
```

Mô hình trên chỉ xảy ra khi filter được map với ASYNC và `shouldNotFilterAsyncDispatch() == false`. Nếu dùng mặc định skip async, số lần `doFilterInternal` trong mô hình sẽ chỉ là 1.

### 8.3. Exception được MVC xử lý khác ERROR dispatch

Một controller có:

```java
@GetMapping("/problem")
String fail() {
    throw new IllegalArgumentException("invalid");
}

@ExceptionHandler(IllegalArgumentException.class)
ResponseEntity<String> handle(IllegalArgumentException ex) {
    return ResponseEntity.badRequest().body("bad");
}
```

*Đoạn minh họa, cần đặt vào controller/advice có imports.*

Nếu exception resolver của Spring MVC xử lý và ghi response 400, Servlet container **không nhất thiết thực hiện ERROR dispatch**. Vì vậy `shouldNotFilterErrorDispatch() == false` không có nghĩa filter nhận thêm lượt xử lý lỗi cho mọi exception. Khi cần ghi metric lỗi, có thể dùng exception handling hoặc quan sát HTTP status/final outcome theo điểm phù hợp.

### 8.4. ERROR dispatch riêng

```text
REQUEST filter bắt đầu
  → Servlet/application báo lỗi
  → REQUEST filter kết thúc, marker xóa
ERROR dispatch do container khởi tạo
  → ERROR filter nhận lượt mới, nếu đã map và không skip
  → endpoint/error page render
```

### 8.5. Nested ERROR dispatch

```text
REQUEST filter đang active; marker TRUE
  → downstream sendError
  → container nested ERROR (trong cùng chain/thread)
  → filter được gọi tiếp với dispatcherType=ERROR
  → marker TRUE → doFilterNestedErrorDispatch
  → không tự tăng số lần doFilterInternal
```

**Không viết unit test mà chỉ gọi REQUEST rồi gọi ERROR sau khi REQUEST hoàn tất để khẳng định đã kiểm thử nested behavior.** Hai tình huống khác nhau và có nhánh xử lý khác nhau.

## 9. Ứng dụng Spring Boot 3 + Java 17 chạy được

Dùng Spring Boot **3.3.13**, Java 17+, Maven. Demo minh họa filter ghi số lần logic chạy trên **cùng request object**, endpoint sync/async và error handler đơn giản. Test Servlet mock kiểm tra các nhánh ASYNC/ERROR đáng tin hơn việc kỳ vọng MockMvc tự dựng một error-page dispatch của container.

Cấu trúc:

```text
once-filter-dispatch-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── DispatchDemoApplication.java
    │   ├── DispatchTraceFilter.java
    │   └── DispatchController.java
    └── test/java/example/
        ├── DispatchTraceFilterTest.java
        └── DispatchControllerTest.java
```

### 9.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>once-filter-dispatch-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
```

### 9.2. DispatchTraceFilter.java

```java
package example;

import java.io.IOException;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.web.filter.OncePerRequestFilter;

public class DispatchTraceFilter extends OncePerRequestFilter {

    public static final String INTERNAL_COUNT =
            "example.trace.internalCount";

    public static final String NESTED_COUNT =
            "example.trace.nestedErrorCount";

    public static final String FIRST_DISPATCH =
            "example.trace.firstDispatcherType";

    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false; // filter tham gia lượt ASYNC nếu container có map
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false; // filter tham gia lượt ERROR nếu container có map
    }

    private static int next(HttpServletRequest request, String name) {
        Integer current = (Integer) request.getAttribute(name);
        int updated = current == null ? 1 : current + 1;
        request.setAttribute(name, updated);
        return updated;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        int count = next(request, INTERNAL_COUNT);

        if (request.getAttribute(FIRST_DISPATCH) == null) {
            request.setAttribute(
                    FIRST_DISPATCH, request.getDispatcherType().name());
        }

        try {
            filterChain.doFilter(request, response);
        } finally {
            // Khi REQUEST đã async-started, response thường chưa hoàn tất.
            // Không set một header "đã hoàn thành" quá sớm.
            if (!isAsyncStarted(request) && !response.isCommitted()) {
                response.setHeader("X-Trace-Dispatches",
                        Integer.toString(count));
            }
        }
    }

    @Override
    protected void doFilterNestedErrorDispatch(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        next(request, NESTED_COUNT);
        filterChain.doFilter(request, response);
    }
}
```

Đây là **instrumentation để học**, không phải metrics production:

- Counter lưu trên request attribute nên được dùng lại qua dispatch của **cùng request**.
- `doFilterInternal` tăng `INTERNAL_COUNT` từng lượt mà filter thực sự xử lý.
- `doFilterNestedErrorDispatch` tăng counter **riêng**; nested error không tự làm tăng internalCount.
- `response.isCommitted()` giúp tránh sửa header khi HTTP response đã commit; demo chỉ quan sát được header trong tình huống phù hợp.
- Nếu ERROR dispatch riêng bắt đầu trên cùng request sau khi response bị commit, set header có thể không còn khả thi.
- Counter không phải số HTTP requests. Một HTTP request có thể có internalCount = 2 khi có ASYNC redispatch.

### 9.3. DispatchDemoApplication.java

```java
package example;

import java.util.EnumSet;
import java.util.List;

import jakarta.servlet.DispatcherType;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;

@SpringBootApplication
public class DispatchDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }

    @Bean
    FilterRegistrationBean<DispatchTraceFilter> traceFilterRegistration() {
        FilterRegistrationBean<DispatchTraceFilter> registration =
                new FilterRegistrationBean<>(new DispatchTraceFilter());

        registration.setName("dispatchTraceFilter");
        registration.setUrlPatterns(List.of("/*"));
        registration.setDispatcherTypes(EnumSet.of(
                DispatcherType.REQUEST,
                DispatcherType.ASYNC,
                DispatcherType.ERROR));
        registration.setAsyncSupported(true);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);

        return registration;
    }
}
```

Class `DispatchTraceFilter` **không** gắn `@Component`. Chỉ `FilterRegistrationBean` đăng ký nó với Servlet container. Kể cả khi Spring Boot tự đăng ký các Servlet filters khác, cấu hình này chỉ kiểm soát dispatch types của chính filter demo.

### 9.4. DispatchController.java

```java
package example;

import java.util.concurrent.Callable;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DispatchController {

    @GetMapping("/sync")
    public ResponseEntity<String> sync(HttpServletRequest request) {
        Integer n = (Integer) request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT);
        return ResponseEntity.ok("sync-" + n);
    }

    @GetMapping("/async")
    public Callable<String> async() {
        return () -> "async-ok";
    }

    @GetMapping("/handled-error")
    public ResponseEntity<String> handledError() {
        // Đây là lỗi do controller tự trả trực tiếp, không yêu cầu
        // Servlet container chạy ERROR dispatch.
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body("bad");
    }

    @GetMapping("/unhandled-error")
    public String unhandledError() {
        throw new ResponseStatusException(
                HttpStatus.INTERNAL_SERVER_ERROR, "demo failure");
    }
}
```

`/sync` giúp quan sát request attribute: controller thấy counter đã được filter tăng lên 1 trước khi method chạy. `/async` dùng MVC async support với `Callable<String>`; kiểu return ở `@RestController` sẽ được viết như body khi hoàn tất. `/handled-error` trả 400 theo business logic mà không mặc nhiên tạo ERROR dispatch. `/unhandled-error` minh họa lỗi server, nhưng **không hứa rằng mọi container sẽ dispatch ERROR theo một chuỗi chính xác giống nhau**; điều này phải được integration test trên container thực.

### 9.5. Lệnh chạy và kết quả

Từ thư mục chứa `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Dùng terminal khác:

```bash
curl -i http://localhost:8080/sync
curl -i http://localhost:8080/async
curl -i http://localhost:8080/handled-error
```

Kết quả cơ bản dự kiến:

- `GET /sync` → HTTP 200; body `sync-1`; header `X-Trace-Dispatches: 1` khi response chưa commit lúc filter kết thúc.
- `GET /async` → HTTP 200; body `async-ok`. Nếu container thực sự thực hiện ASYNC redispatch qua filter và response còn sửa header được, `X-Trace-Dispatches` có thể phản ánh 2 lượt. Điều kiện/điểm commit cần kiểm chứng bằng log hoặc integration test; đừng coi số header này là giá trị contract bất biến.
- `GET /handled-error` → HTTP 400 và body `bad`; status 400 **không tự chứng minh có ERROR dispatch**.

Thứ tự headers và các headers khác phụ thuộc Servlet container; không coi cURL output gồm toàn bộ headers là chuỗi stdout cố định.

## 10. Unit test filter theo từng dispatcher type

Để kiểm tra logic filter độc lập với container, dùng `MockHttpServletRequest` và `MockHttpServletResponse` từ spring-test. Những test này **mô phỏng dispatcherType**, không tuyên bố tái hiện đầy đủ cách container khởi tạo async/error dispatch.

File `src/test/java/example/DispatchTraceFilterTest.java`:

```java
package example;

import java.io.IOException;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DispatchTraceFilterTest {

    @Test
    void firstRequestDispatchExecutesInternalOnce() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        FilterChain end = (req, res) -> { };
        filter.doFilter(request, response, end);

        assertEquals(1, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
        assertEquals("REQUEST", request.getAttribute(
                DispatchTraceFilter.FIRST_DISPATCH));
        assertNull(request.getAttribute(
                filterAlreadyFilteredName(filter)));
    }

    @Test
    void asyncRedispatchCanRunInternalAgain() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain end = (req, res) -> { };

        // Lượt REQUEST ban đầu đã kết thúc, marker của base class
        // đã bị remove trong finally.
        filter.doFilter(request, response, end);

        request.setDispatcherType(DispatcherType.ASYNC);
        filter.doFilter(request, response, end);

        assertEquals(2, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
    }

    @Test
    void separateErrorDispatchCanRunInternalAgain() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain end = (req, res) -> { };

        filter.doFilter(request, response, end);
        request.setDispatcherType(DispatcherType.ERROR);
        filter.doFilter(request, response, end);

        assertEquals(2, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
        assertNull(request.getAttribute(
                DispatchTraceFilter.NESTED_COUNT));
    }

    @Test
    void nestedErrorUsesDedicatedHookNotInternal() throws Exception {
        DispatchTraceFilter filter = new DispatchTraceFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        FilterChain end = (req, res) -> { };
        FilterChain requestChain = (req, res) -> {
            // Mô phỏng ERROR dispatch lồng ngay trong REQUEST chain
            // khi already-filtered marker vẫn còn.
            request.setDispatcherType(DispatcherType.ERROR);
            filter.doFilter(request, response, end);
        };

        filter.doFilter(request, response, requestChain);

        assertEquals(1, request.getAttribute(
                DispatchTraceFilter.INTERNAL_COUNT));
        assertEquals(1, request.getAttribute(
                DispatchTraceFilter.NESTED_COUNT));
    }

    @Test
    void baseDefaultsSkipAsyncAndError() throws Exception {
        class DefaultFilter extends OncePerRequestFilter {
            int calls;

            @Override
            protected void doFilterInternal(
                    jakarta.servlet.http.HttpServletRequest request,
                    jakarta.servlet.http.HttpServletResponse response,
                    FilterChain chain)
                    throws ServletException, IOException {
                calls++;
                chain.doFilter(request, response);
            }
        }

        DefaultFilter filter = new DefaultFilter();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain end = (req, res) -> { };

        filter.doFilter(request, response, end);
        request.setDispatcherType(DispatcherType.ASYNC);
        filter.doFilter(request, response, end);
        request.setDispatcherType(DispatcherType.ERROR);
        filter.doFilter(request, response, end);

        assertEquals(1, filter.calls);
    }

    private static String filterAlreadyFilteredName(
            DispatchTraceFilter filter) {
        // Trong unit test chưa có tên filter đầy đủ do container set.
        // Base class fallback sang class name + ALREADY_FILTERED_SUFFIX.
        return filter.getClass().getName()
                + OncePerRequestFilter.ALREADY_FILTERED_SUFFIX;
    }
}
```

Chạy `mvn test`. Test `nestedErrorUsesDedicatedHookNotInternal` là điểm quan trọng: nó bắt lượt ERROR **khi REQUEST vẫn đang ở trong chain**. Trong khi đó, test `separateErrorDispatchCanRunInternalAgain` gọi ERROR **sau khi REQUEST filter đã thoát**, vì marker đã bị remove.

Test `baseDefaultsSkipAsyncAndError` cho thấy mặc định của base class. `DispatcherType` trong mocks được set thủ công, vì unit test không chứng minh filter đã được Servlet container map đúng types. Phần mapping sẽ được kiểm chứng riêng trên ứng dụng chạy thực.

### 10.1. Kiểm thử Spring MVC endpoint async

File `src/test/java/example/DispatchControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DispatchControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void synchronousControllerReturnsBody() throws Exception {
        mvc.perform(get("/sync"))
            .andExpect(status().isOk())
            .andExpect(content().string("sync-1"));
    }

    @Test
    void asyncControllerRequiresAsyncDispatchInMockMvc() throws Exception {
        MvcResult pending = mvc.perform(get("/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("async-ok"));
    }

    @Test
    void handledErrorDoesNotRequireServletErrorDispatch()
            throws Exception {
        mvc.perform(get("/handled-error"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string("bad"));
    }
}
```

Ở MockMvc, phương thức `asyncDispatch(pending)` mô phỏng bước MVC redispatch để lấy kết quả `Callable`; **không dùng kết quả test này để khẳng định mọi cấu hình Servlet container/FilterRegistrationBean sẽ gọi filter đúng hai lần**. Để kiểm chứng DispatcherType.ASYNC/ERROR mapping trong deploy thật, dùng bài kiểm thử HTTP tới server được khởi động trên random port hoặc quan sát log trong Tomcat/Jetty tương ứng.

### 10.2. Khi nào cần @SpringBootTest(webEnvironment = RANDOM_PORT)?

Các unit tests giả lập được trạng thái của `OncePerRequestFilter`; `MockMvc` kiểm tra MVC async pipeline; nhưng **chỉ embedded Servlet container thực** mới cho bạn độ tin cậy cao về:

- Filter registration có đưa vào REQUEST/ASYNC/ERROR không.
- Container có chuyển `sendError` sang ERROR dispatch riêng/lồng không.
- Request/response wrappers có bị thay lại trong nested ERROR không.
- Header có còn ghi được ở điểm filter hoàn tất hay response đã commit.
- Cách Spring Security/Servlet filters khác ảnh hưởng filter chain.

Với production, hãy thêm integration test phù hợp môi trường Tomcat/Jetty/Undertow đang dùng. Không viết assertion rằng mọi container sẽ có thứ tự lỗi giống nhau; số ERROR dispatch và thời điểm lỗi có thể khác tùy cách exception được xử lý.

## 11. Checklist cấu hình đúng

Trước khi triển khai một OncePerRequestFilter, nên trả lời:

1. **Mục tiêu của filter là gì?** Tracing/logging, security, header, wrapping, metrics hay kiểm tra request?
2. Có cần tham gia `ASYNC` và `ERROR` không, hay chỉ `REQUEST`?
3. FilterRegistrationBean hoặc `web.xml` đã map đúng `DispatcherType` chưa?
4. Nếu muốn async, filter/mapping có `asyncSupported` và container hỗ trợ async không?
5. `shouldNotFilterAsyncDispatch` và `shouldNotFilterErrorDispatch` đã khớp mục tiêu chưa?
6. Nếu skip theo URL, `shouldNotFilter` có bỏ nhầm endpoint quan trọng không?
7. Logic có dùng request attribute cho thông tin xuyên dispatch và MDC/thread-local đúng thread không?
8. Nếu error nested, cần override `doFilterNestedErrorDispatch` để bọc request/response lại không?
9. Khi async started, có vô tình set header, ghi response, tính duration hoặc close resource quá sớm không?
10. Có tránh side effect nghiệp vụ phát lặp khi REQUEST + ASYNC + ERROR đi qua không?
11. Test đã phân biệt separate ERROR và nested ERROR chưa?
12. Đã kiểm tra cả MockMvc/Servlet mocks lẫn embedded container với dispatcher mapping thật chưa?

## 12. Những lỗi phổ biến

| Hiểu nhầm/lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| “OncePerRequestFilter chỉ chạy đúng 1 lần cho mọi HTTP request” | Sai khi bật async/error redispatch | Hiểu guarantee theo dispatch/thread |
| Override `shouldNotFilterAsyncDispatch=false` nhưng không map ASYNC | Không bao giờ thấy ASYNC tại filter | Cấu hình dispatcher types **và** flag |
| Override `shouldNotFilterErrorDispatch=false` nhưng không map ERROR | Không nhận error dispatch | Map ERROR ở Servlet registration |
| Quên `setAsyncSupported(true)` khi filter nằm trong async chain | Async có thể bị từ chối hoặc cấu hình không đầy đủ | Đăng ký async-supported hợp lệ |
| Tăng metric HTTP request ở mọi `doFilterInternal` | Một HTTP request bị đếm nhiều lần | Phân biệt dispatch counter vs request counter |
| Đo duration ngay khi REQUEST chain return | Bỏ mất giai đoạn bất đồng bộ | Dùng completion hook/lifecycle đúng |
| Đặt MDC mà không `remove()` trong finally | Trộn trace giữa các request trên thread pool | Dọn thread-local trong finally |
| Nghĩ tham gia ASYNC redispatch là MDC sẽ có trong Callable thread | Log Callable thiếu trace | Propagate context vào executor |
| Chỉ nhìn 500 và nghĩ đã có ERROR dispatch | Kết luận sai về behavior | Phân biệt MVC exception handler và container error |
| Unit test gọi ERROR sau REQUEST mà gọi là nested ERROR | Không test nhánh nested | Trigger nested trước khi outer filter return |
| Wrapper mất tác dụng ở nested ERROR | Container có thể đưa wrapper về bản gốc | Override nested error hook và re-wrap khi cần |
| Gắn filter `@Component` và tạo FilterRegistrationBean thêm | Khó kiểm soát registration/trùng execution | Chọn một cách đăng ký |
| Dùng `@Order` nhưng bỏ dispatcher type mapping | Filter không nhận lượt dispatch mong muốn | Thứ tự và mapping là hai lớp khác nhau |
| Đọc request body sớm không dùng buffering đúng | Controller không còn body | Thiết kế cached request wrapper phù hợp |
| Response đã commit vẫn chỉnh header | Header không xuất hiện hoặc exception | Kiểm tra lifecycle/commit; đặt header đúng thời điểm |
| Bọc response nhưng không copy body ra output thực | Response rỗng | Copy body đúng lúc, xử lý async/error |
| Dùng `ThreadLocal` thay request attribute để giữ dữ liệu xuyên async | Mất dữ liệu qua thread | Request attribute + explicit propagation |
| Tắt filter cho mọi ERROR vì “không quan trọng” | Bỏ qua log/security/error handling mong muốn | Quyết định chính sách theo loại response |
| Tưởng servlet Filter giống MVC interceptor | Hook không được gọi khi không có handler hoặc error dispatch | Chọn layer phù hợp |

## 13. Câu hỏi tự kiểm tra

**1.** Vì sao `OncePerRequestFilter` có thể gọi `doFilterInternal` hai lần trong một HTTP request?  
**Đáp án:** request có thể có REQUEST và ASYNC (hoặc ERROR) dispatch riêng; marker đã remove sau lượt trước; nếu filter được map và không skip, lượt sau có thể gọi lại.

**2.** Mặc định `shouldNotFilterAsyncDispatch()` trả gì?  
**Đáp án:** `true`, tức bỏ qua async dispatch.

**3.** Mặc định `shouldNotFilterErrorDispatch()` trả gì?  
**Đáp án:** `true`, tức bỏ qua error dispatch.

**4.** Nếu return `false` ở cả hai method trên thì filter tự tham gia ASYNC/ERROR chưa?  
**Đáp án:** chưa chắc; Servlet registration còn phải map đúng DispatcherType.

**5.** Ý nghĩa của already-filtered marker?  
**Đáp án:** tránh `doFilterInternal` chạy lồng thêm khi request attribute báo filter đang xử lý một lượt; marker được gỡ trong finally.

**6.** Marker có tồn tại vĩnh viễn tới khi HTTP response xong không?  
**Đáp án:** không; nó bị remove khi lời gọi filter tương ứng kết thúc.

**7.** `isAsyncDispatch()` và `isAsyncStarted()` khác gì?  
**Đáp án:** một cái nhận diện kiểu dispatch hiện tại, một cái cho biết request đang ở async mode nên chưa hoàn tất trên lượt hiện tại.

**8.** ERROR dispatch riêng khác nested ERROR thế nào?  
**Đáp án:** separate ERROR thường sau khi REQUEST filter chain kết thúc và marker đã remove; nested ERROR vào khi marker còn, nên gọi `doFilterNestedErrorDispatch`.

**9.** Khi nào cần override `doFilterNestedErrorDispatch`?  
**Đáp án:** khi cần xử lý tình huống container thay request/response wrappers hoặc công việc đặc thù trong nested ERROR; tránh chạy lại logic tổng thể không cần thiết.

**10.** Khi một `@ExceptionHandler` xử lý lỗi 400, có nhất thiết nhận Servlet ERROR dispatch không?  
**Đáp án:** không, MVC có thể xử lý hoàn toàn mà không có ERROR dispatch.

**11.** MDC có tự xuất hiện trong thread thực thi `Callable` không?  
**Đáp án:** không được bảo đảm; cần context propagation vào executor.

**12.** Nếu đo request latency trong REQUEST filter nhưng controller trả Callable thì sai ở đâu?  
**Đáp án:** filter có thể kết thúc trước khi async xử lý xong; cần lifecycle completion hook.

**13.** `MockMvc` có thể kiểm tra chắc việc Servlet container tái dispatch ERROR không?  
**Đáp án:** không đầy đủ; dùng Servlet mocks cho logic class và integration test với embedded container cho registration/lifecycle.

**14.** Tại sao không đếm HTTP requests bằng số lần doFilterInternal?  
**Đáp án:** một HTTP request có thể có nhiều dispatcher invocations.

**15.** `FilterRegistrationBean#setOrder` có thay thế `setDispatcherTypes` không?  
**Đáp án:** không; một cái quyết định thứ tự filter, một cái quyết định dispatch types.

## 14. Nguồn chính thức

1. [Spring Framework 6.2 — OncePerRequestFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): base class, marker, flags mặc định, async/error/nested dispatch.
2. [Spring Framework 6.2 — Web Async](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-async.html): mô hình async MVC, Callable, DeferredResult, async dispatch.
3. [Spring Boot 3.3 — Servlet Filters](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): registration Servlet components/FilterRegistrationBean.
4. [Jakarta Servlet API — DispatcherType](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/dispatchertype): REQUEST, ASYNC, ERROR, FORWARD, INCLUDE.
5. [Jakarta Servlet API — AsyncListener](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/asynclistener): lifecycle callbacks.
6. [Spring Test — MockMvc](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html): kiểm thử controller, asyncDispatch và request/response.
7. [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.3/servlet/architecture.html): filter chain trong bảo mật Servlet và vấn đề thứ tự/dispatch.

**Tóm lại:** `OncePerRequestFilter` đảm bảo logic filter **không chạy trùng trong cùng lượt request dispatch**, chứ không đảm bảo chỉ một lượt xử lý bất kể ASYNC/ERROR. Muốn tham gia ASYNC/ERROR phải thiết lập **cả dispatcher mapping lẫn cờ skip**; với nested ERROR hãy dùng đúng hook riêng. Thiết kế trace/metrics/cleanup theo **toàn HTTP lifecycle** và phân biệt request count với dispatch count.
