# AsyncContext, executor và giới hạn của việc truyền ngữ cảnh trong Spring Security

## 1. Mục tiêu: ngữ cảnh request không tự đi theo mọi công việc bất đồng bộ

Một request đến API Spring Boot được xác thực dưới tên **Alice**. Controller có thể đọc:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Nhưng sau khi controller đưa công việc sang thread khác, `Authentication` có còn sẵn ở đó không? Đáp án không chỉ phụ thuộc việc task “bất đồng bộ” mà còn phụ thuộc **ai tạo task, ai đưa task vào executor, cơ chế tích hợp Spring Security nào đã hoạt động và ngữ cảnh được chụp lúc nào**.

Ba tình huống phải tách riêng:

1. **Servlet `AsyncContext.start(Runnable)`**: Spring Security có tích hợp để truyền `SecurityContext` cho `Runnable` được khởi chạy qua wrapper request/async context đúng chuỗi filter.
2. **Spring MVC trả `Callable<T>`**: Spring Security tích hợp với `WebAsyncManager` và tự thiết lập `SecurityContext` trong thread xử lý `Callable` thông qua cơ chế async MVC.
3. **`DeferredResult<T>`, `Executor`, `@Async`, `CompletableFuture` hoặc thread tự tạo**: không nên mặc định có cùng `SecurityContext`; thường phải dùng cơ chế truyền ngữ cảnh tường minh, ví dụ `DelegatingSecurityContextExecutor` hoặc `DelegatingSecurityContextAsyncTaskExecutor`.

**Mục tiêu bài học** là hiểu đường truyền `SecurityContextHolder → task → worker thread → cleanup`, lựa chọn API phù hợp, ngăn rò rỉ danh tính giữa task của nhiều người dùng, phân biệt security context với request context/transaction và nhận biết giới hạn bảo mật của việc “copy danh tính”.

Nội dung dành cho **Spring Security Servlet/Spring MVC trên Java 17+**, không phải một hướng dẫn riêng cho Spring WebFlux Reactor Context. Ví dụ có dấu “fragment” phải được đặt trong project Spring Boot có dependency/cấu hình phù hợp; ví dụ Java 17 độc lập ở phần sau có lệnh biên dịch và stdout.

## 2. Những đối tượng cần hiểu đúng

| Thành phần | Vai trò | Có tự truyền qua thread bất kỳ không? |
| --- | --- | --- |
| `SecurityContextHolder` | Điểm truy cập ngữ cảnh bảo mật hiện hành | **Không**, mặc định dựa trên ThreadLocal |
| `SecurityContext` | Đối tượng giữ `Authentication` | Có thể được truyền bằng wrapper, nhưng không tự đi theo mọi API |
| `Authentication` | Danh tính, trạng thái xác thực, `GrantedAuthority` | Là dữ liệu trong `SecurityContext`, không thay thế policy |
| `HttpServletRequest` | Ngữ cảnh HTTP của request | Không tự trở thành request hợp lệ cho một background job |
| `AsyncContext` | Điều khiển lifecycle bất đồng bộ của Servlet request/response | Có tích hợp propagation khi dùng `AsyncContext.start` đúng cách |
| `WebAsyncManager` | Quản lý Servlet async xử lý của Spring MVC | Có tích hợp cho MVC `Callable` |
| `Executor`/`ExecutorService` | Hạ tầng chạy task trên thread khác | **Không** tự truyền SecurityContext |
| `DelegatingSecurityContextRunnable` | Bọc một `Runnable` với ngữ cảnh cần dùng | Có: thiết lập trong worker rồi cleanup |
| `DelegatingSecurityContextExecutor` | Bọc các task gửi tới một `Executor` | Có: capture context theo kiểu constructor/cấu hình |
| `DelegatingSecurityContextAsyncTaskExecutor` | Bọc `Runnable`/`Callable` của Spring `AsyncTaskExecutor` | Có: hỗ trợ async task khi dùng đúng executor |

**Quan điểm quan trọng:** `SecurityContext` không phải “request”, không phải “session”, không tự làm sống lại transaction và không bảo đảm principal vẫn có quyền tại thời điểm task thực sự chạy. Propagation giải quyết *đặt thông tin vào đúng thread*, còn authorization nghiệp vụ phải được kiểm tra bằng policy đáng tin.

### 2.1. Context có thể được tạo trên một request thread

Ví dụ request `GET /api/reports/r7` sau khi xác thực:

```text
Servlet thread: http-nio-8080-exec-2

SecurityContextHolder
  └─ SecurityContext
       └─ Authentication
           ├─ principal: alice
           ├─ authenticated: true
           └─ authorities: [ROLE_USER, report:read]
```

Khi code chuyển xử lý sang worker từ một pool:

```text
Worker thread: report-pool-1

SecurityContextHolder
  └─ Không có Authentication của Alice
     (nếu không có cơ chế propagation)
```

Nếu worker cố dùng `@PreAuthorize("hasAuthority('report:read')")`, nó có thể bị từ chối vì không có danh tính hợp lệ. Nguy hiểm hơn, nếu một đoạn mã cũ tự `setContext` rồi không dọn dẹp, worker có thể giữ nhầm context của request trước khi phục vụ request mới.

### 2.2. SecurityContextHolder thường dùng ThreadLocal

Spring Security mặc định sử dụng `SecurityContextHolder.MODE_THREADLOCAL`. Trong cùng thread, code có thể truy cập `SecurityContextHolder.getContext()` mà không cần truyền tham số qua từng hàm.

Điều này thuận tiện nhưng có **ranh giới thread**:

- Tạo task trên thread A không tự gắn context của A vào thread B.
- Một thread pool có thể dùng lại B cho nhiều user khác nhau.
- Sau request, Spring Security dọn ngữ cảnh ở filter chain để tránh rò rỉ trên servlet threads.
- Worker tự tạo bên ngoài chuỗi filter phải có trách nhiệm đặt và **xóa/khôi phục** ngữ cảnh một cách an toàn.

**Không suy rằng request đã authenticated nghĩa là mọi tác vụ sinh ra từ request đều authenticated.**

## 3. Ma trận: luồng bất đồng bộ nào được tự động hỗ trợ?

| Kiểu xử lý | Cơ chế chạy | SecurityContext được tự truyền? | Hành động phù hợp |
| --- | --- | --- | --- |
| Code đồng bộ bên trong controller/service | Cùng thread request | Thường có | Kiểm tra quyền tại web/service |
| Servlet `AsyncContext.start(Runnable)` | Runnable thông qua Servlet async context được Spring Security bọc | **Có trong cấu hình tích hợp đúng** | Bảo đảm async support, lifecycle và test |
| MVC controller trả `Callable<T>` | Spring WebAsyncManager + Spring Security integration | **Có** cho thread thực thi Callable | Dùng MVC async API đúng cách |
| MVC controller trả `DeferredResult<T>` | Tác vụ được ứng dụng tự hoàn thành | **Không tự động cho user task** | Bọc executor hoặc task |
| `CompletableFuture.supplyAsync(...)` không truyền executor | ForkJoin common pool | **Không mặc định** | Truyền context-aware executor phù hợp |
| `new Thread(...)` | Thread tạo thủ công | **Không mặc định** | Tránh tự tạo tràn lan; dùng wrapper nếu buộc phải làm |
| `ExecutorService.submit(...)` | Pooled worker | **Không mặc định** | Bọc `ExecutorService`/task |
| `@Async` | Spring `TaskExecutor` | **Chỉ khi executor được cấu hình truyền context** | Dùng `DelegatingSecurityContextAsyncTaskExecutor`/cơ chế tương đương |
| `@Scheduled` | Scheduler chạy độc lập request | Không có user request tự nhiên | Dùng service identity + policy rõ ràng |
| Message consumer/queue job | Worker độc lập tiến trình/request | Không được truyền qua HTTP ThreadLocal | Truyền thông tin actor tối thiểu có tin cậy và xác thực/ủy quyền lại |

**Lưu ý về phiên bản:** tài liệu Spring Security Servlet hiện đại mô tả rõ integration với `AsyncContext.start` và Spring MVC `Callable`, đồng thời nói **không có auto integration cho `DeferredResult`** vì ứng dụng tự điều khiển công việc. Đây là phân biệt về API/lifecycle, không phải lỗi cần “bật thêm flag” cho mọi loại task.

## 4. Servlet AsyncContext: khác với việc tự gọi new Thread

### 4.1. AsyncContext dùng để giữ request/response mở

Servlet asynchronous processing cho phép controller/filter rời thread ban đầu mà response chưa phải hoàn tất. Lời gọi:

```java
AsyncContext async = request.startAsync();
```

đánh dấu request chuyển sang chế độ async. Sau đó có thể dùng:

- `async.start(Runnable)`: nhờ container chạy task được gắn với request async.
- `async.dispatch(...)`: yêu cầu dispatch trở lại xử lý Servlet khi thích hợp.
- `async.complete()`: kết thúc response async.
- `async.setTimeout(...)` và `AsyncListener`: quản lý timeout/lifecycle.

**Không nhầm `async.start(...)` với `executor.execute(...)`:** mặc dù cả hai làm code chạy ở thread khác, Spring Security có tích hợp propagation cụ thể cho `AsyncContext.start(Runnable)` trong đường Servlet request đã được security wrapper xử lý. Một `Executor` tự tạo không tự nhận tích hợp đó.

### 4.2. Tại sao Spring Security truyền được ở AsyncContext.start?

Theo tài liệu Spring Security, framework bọc `AsyncContext` để khi bạn gọi `async.start(Runnable)`, `Runnable` được chạy với `SecurityContext` phù hợp đã có tại thời điểm chuyển giao. Nền tảng là bộ wrapper tương tự `DelegatingSecurityContextRunnable`.

Mô hình:

```text
REQUEST thread (alice)
    │
    ├─ request.startAsync()
    │
    └─ async.start(runnable)
          │
          └─ Spring Security/Servlet integration
               ├─ capture context
               ├─ worker thread: set context Alice
               ├─ runnable.run()
               └─ cleanup SecurityContextHolder
    │
    └─ original request thread có thể trả về pool
```

Điều này **không** có nghĩa mọi `Runnable` chạy từ `new Thread` sau `request.startAsync()` đều được truyền. Wrapper chỉ áp dụng khi đi qua đúng API integration.

### 4.3. Ví dụ Servlet fragment

Đoạn sau đặt trong một Spring-managed controller có mapping GET phù hợp, dùng Jakarta Servlet API. Đây là **fragment tích hợp**, chưa bao gồm imports, toàn bộ class, security config hay exception handler:

```java
@GetMapping("/api/me/async")
public void readCurrentUser(HttpServletRequest request) {
    AsyncContext async = request.startAsync();
    async.setTimeout(10_000L);

    async.start(() -> {
        HttpServletResponse response =
                (HttpServletResponse) async.getResponse();
        try {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null || !authentication.isAuthenticated()) {
                response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            } else {
                response.setStatus(HttpServletResponse.SC_OK);
                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write(authentication.getName());
            }
        } catch (IOException ex) {
            // Tích hợp với logging/error policy của project;
            // không ghi secret hoặc token vào log.
            throw new UncheckedIOException(ex);
        } finally {
            async.complete();
        }
    });
}
```

Các kiểu cần import theo dự án gồm `jakarta.servlet.AsyncContext`, `jakarta.servlet.http.HttpServletRequest`, `HttpServletResponse`, `IOException`, `UncheckedIOException` và các kiểu Spring Security. Response/writer có thể lỗi do client ngắt kết nối; ví dụ đảm bảo gọi `async.complete()` trong `finally` nhưng **không** thay thế error-handling hoặc timeout listener của production. Nếu code có nhiều đường xử lý timeout/cancel, tránh gọi `complete()` lặp không kiểm soát.

**Security rule** cho route trên vẫn phải yêu cầu authentication:

```java
.requestMatchers(HttpMethod.GET, "/api/me/async").authenticated()
.anyRequest().denyAll()
```

Việc thread worker đọc được `Authentication` không bảo đảm route được bảo vệ nếu HTTP config vô tình đặt `permitAll` quá rộng ở trước.

### 4.4. Điều kiện Servlet async support

Với cấu hình Servlet 3.x+/Spring Boot tương ứng, các servlet/filter liên quan phải hỗ trợ async. Với `web.xml` tự quản lý, cần `async-supported=true` và dispatcher mappings phù hợp (chẳng hạn REQUEST và ASYNC) cho `springSecurityFilterChain` nếu runtime yêu cầu. Trong cấu hình Boot Java hiện đại, Spring Security chuẩn thường đã hỗ trợ, nhưng **custom filters hoặc cấu hình container** có thể khiến `request.startAsync()` thất bại vì async không được hỗ trợ.

Hãy kiểm tra:

- `request.isAsyncSupported()` khi chẩn đoán.
- Filter/Servlet registration thực tế và các `DispatcherType` được áp dụng.
- Timeout, cancellation và lỗi I/O của response.
- Security filters xử lý async redispatch theo cấu hình.
- Không truy cập request/response sau khi lifecycle đã kết thúc.

### 4.5. AsyncContext không phải hàng đợi xử lý lâu dài

Một HTTP request async vẫn bị giới hạn bởi **thời gian sống request**, timeout, kết nối client và tài nguyên container. Không nên giữ `AsyncContext` hàng phút/giờ chỉ để làm tác vụ gửi email, trích xuất video hoặc xử lý batch dài hạn.

Nếu công việc phải tồn tại sau khi client ngắt kết nối, dùng queue/job riêng, trả `202 Accepted` cùng mã job và thực hiện authorization khi tạo job và khi truy vấn kết quả. **Không đưa nguyên `SecurityContext` và `HttpServletRequest` vào queue**.

## 5. Spring MVC Callable: có hỗ trợ tích hợp tự động

### 5.1. Callable là kết quả bất đồng bộ do MVC quản lý

Spring MVC cho phép controller trả `Callable<T>`. Framework chuyển việc gọi `Callable.call()` sang executor của MVC và hoàn tất response sau đó. Spring Security tích hợp với `WebAsyncManager` để cung cấp `SecurityContext` cho thread thực thi `Callable`.

Ví dụ:

```java
@GetMapping("/api/me/callable")
public Callable<ResponseEntity<String>> currentUser() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return ResponseEntity.status(401).body("Unauthenticated");
        }
        return ResponseEntity.ok(authentication.getName());
    };
}
```

Đây là fragment trong controller Spring MVC, không phải chương trình Java chạy riêng. Kiểu `ResponseEntity` từ Spring Web và `Callable` từ `java.util.concurrent`. Với default integration, `Callable` chạy trên thread do MVC quản lý nhưng có `SecurityContext` hiện hành.

**Mốc capture chính xác:** tài liệu nêu `SecurityContext` gắn với `Callable` là context có trong `SecurityContextHolder` khi `WebAsyncManager.startCallableProcessing` được gọi, không phải bất kỳ context ngẫu nhiên ở thời điểm sau này.

### 5.2. WebAsyncManagerIntegrationFilter làm gì?

Spring Security có `WebAsyncManagerIntegrationFilter`, tích hợp với Spring MVC `WebAsyncManager` thông qua `SecurityContextCallableProcessingInterceptor`. Vai trò của nó là hỗ trợ ngữ cảnh trong processing `Callable`.

Không cần người học tự thêm một `new WebAsyncManagerIntegrationFilter()` trong cấu hình mặc định nếu Spring Security đã đăng ký thành phần cần thiết. Khi custom security filter chain hoặc thay đổi quá nhiều framework defaults, kiểm thử integration trước khi tự sửa filter order.

### 5.3. Không suy ra mọi callback trong Callable đều có context

Nếu bên trong `Callable.call()` lại làm:

```java
return () -> {
    CompletableFuture<String> nested =
            CompletableFuture.supplyAsync(() ->
                    SecurityContextHolder.getContext()
                            .getAuthentication().getName());
    return ResponseEntity.ok(nested.join());
};
```

`Callable` được tích hợp context **không có nghĩa** task mới do `supplyAsync` chạy trên common pool cũng có context. Có thể nhận `NullPointerException` hoặc principal trống. Nếu cần tác vụ nested, dùng context-aware executor đúng cách, hoặc chuyển dữ liệu identity tối thiểu cho service với validation.

### 5.4. Authorization trong Callable vẫn cần điểm thực thi đúng

Một controller đã được bảo vệ `hasAuthority("report:read")` có thể trả `Callable` để đọc báo cáo. Nhưng nếu service bên trong `Callable` phải kiểm tra owner/tenant, policy đó cần chạy ở **service thực thi**, không chỉ dựa vào việc controller trước đó đã được vào.

Khi sử dụng `@PreAuthorize` ở service Spring-managed bean, đảm bảo lời gọi đi qua Spring proxy và security context đã được truyền. Nếu controller/bean tự gọi method `@PreAuthorize` nội bộ (self-invocation), interceptor có thể bị bỏ qua; không liên quan trực tiếp tới async nhưng là rủi ro đáng kiểm thử.

## 6. DeferredResult: ứng dụng tự hoàn tất nên không có auto propagation

### 6.1. DeferredResult khác Callable về chủ sở hữu task

Spring MVC `DeferredResult<T>` cho phép controller trả ngay một **đối tượng chờ kết quả**. Ứng dụng tự chọn callback, thread, executor, message listener hoặc event nào sẽ gọi `setResult(...)`/`setErrorResult(...)`.

Vì Spring không kiểm soát phần thực thi tùy ý đó, Spring Security **không tự động truyền `SecurityContext` cho mọi công việc hoàn tất DeferredResult**. Đây là điều được tài liệu Spring Security MVC ghi rõ.

```text
MVC Callable:
  MVC sở hữu quá trình chạy Callable
  → Spring Security có điểm tích hợp

MVC DeferredResult:
  Ứng dụng sở hữu việc hoàn tất kết quả
  → ứng dụng phải quyết định propagation
```

### 6.2. Ví dụ sai: raw executor trong DeferredResult

```java
@GetMapping("/api/reports/{id}/deferred")
public DeferredResult<ResponseEntity<String>> read(@PathVariable String id) {
    DeferredResult<ResponseEntity<String>> result =
            new DeferredResult<>(5_000L);

    plainExecutor.execute(() -> {
        Authentication a =
                SecurityContextHolder.getContext().getAuthentication();
        // a có thể null hoặc không mang principal của request.
        result.setResult(ResponseEntity.ok(a.getName()));
    });
    return result;
}
```

Đây là **anti-pattern minh họa**, không phải code production: `plainExecutor` là executor thường; `a.getName()` có thể ném lỗi. Dù controller được phân quyền, task trên executor đó không tự có SecurityContext.

### 6.3. Dùng context-aware executor khi hoàn tất DeferredResult

Giả sử đã inject một `Executor` có tên `securityContextExecutor`, được tạo bằng `DelegatingSecurityContextExecutor` (xem phần 7):

```java
@GetMapping("/api/reports/{id}/deferred")
public DeferredResult<ResponseEntity<String>> read(@PathVariable String id) {
    DeferredResult<ResponseEntity<String>> result =
            new DeferredResult<>(5_000L);

    securityContextExecutor.execute(() -> {
        try {
            // Đây phải là Spring-managed service có policy thật:
            String data = reportService.loadVisibleReport(id);
            result.setResult(ResponseEntity.ok(data));
        } catch (Exception ex) {
            result.setErrorResult(ex);
        }
    });

    return result;
}
```

Đây là fragment trong controller với `securityContextExecutor` và `reportService` đã được dependency injection. Tên method `loadVisibleReport` chỉ minh họa ý nghĩa nghiệp vụ; project phải tự triển khai và kiểm tra quyền trên report. Executor được bọc có thể capture context khi submit và cài vào worker trước khi gọi service.

**Ranh giới:** `setResult` hoàn tất response, không làm phát sinh quyền mới. Nếu user đã bị thu hồi quyền trong lúc task chờ, cần policy kiểm tra lại theo dữ liệu quyền hiện hành khi nghiệp vụ thực thi. Dùng timeout callback và kiểm tra `result.isSetOrExpired()`/lifecycle phù hợp phiên bản để tránh công việc muộn làm side effect không mong muốn.

### 6.4. DeferredResult không phải background job durable

Khi HTTP client ngắt kết nối hoặc request timeout, việc set kết quả có thể không còn ý nghĩa. Với tác vụ lâu dài, trả `202` cùng mã job và theo dõi kết quả qua endpoint riêng. Lúc truy cập kết quả, **phải kiểm tra chủ sở hữu/tenant/job scope**, không chỉ dựa vào token từng có ở request khởi tạo.

## 7. DelegatingSecurityContextRunnable và Callable

### 7.1. Cơ chế wrapper chuẩn của Spring Security

`DelegatingSecurityContextRunnable` là lớp hỗ trợ trong package `org.springframework.security.concurrent`. Về mặt khái niệm, nó làm:

```java
public void run() {
    try {
        SecurityContextHolder.setContext(contextForTask);
        actualRunnable.run();
    } finally {
        SecurityContextHolder.clearContext();
    }
}
```

Code trên là **pseudocode giản lược từ cơ chế**, không phải source đầy đủ hay lời hứa về từng chi tiết nội bộ của mọi phiên bản. Điểm quan trọng là **try/finally cleanup**: kể cả task ném exception, worker không được vô tình dùng context cũ cho task kế tiếp.

### 7.2. Bọc Runnable tường minh

```java
SecurityContext captured = SecurityContextHolder.getContext();

Runnable actualTask = () -> reportService.generateAllowedReport();

Runnable securedTask =
        new DelegatingSecurityContextRunnable(actualTask, captured);

executor.execute(securedTask);
```

Đây là fragment tích hợp; `executor` và `reportService` phải tồn tại. Khi gửi task, context của caller được chỉ định tường minh. Nếu service có `@PreAuthorize`, bảo đảm bean được gọi qua proxy.

Có shortcut constructor:

```java
Runnable securedTask =
        new DelegatingSecurityContextRunnable(actualTask);
```

Dạng này dùng context của `SecurityContextHolder` khi wrapper được tạo theo contract lớp. **Đừng tạo wrapper một lần ở application startup rồi tái dùng cho request của nhiều user**, vì khi đó context có thể không phải user của request hiện tại.

### 7.3. Callable có wrapper tương ứng

`DelegatingSecurityContextCallable<V>` bọc `Callable<V>`. Khi công việc trả kết quả hoặc ném exception, Spring Security đảm nhận việc set/cleanup context trên worker theo contract wrapper.

```java
Callable<String> actual = () -> reportService.getCurrentUserReport();

Callable<String> secured =
        new DelegatingSecurityContextCallable<>(actual);

Future<String> future = executorService.submit(secured);
```

Đoạn trên là fragment tích hợp, chỉ dùng khi `executorService` là JDK `ExecutorService` đã được quản lý. Tránh `future.get()` vô hạn trên request thread nếu mục tiêu là bất đồng bộ; cần timeout/cancellation hoặc dùng MVC async API để không chặn servlet thread.

### 7.4. Wrapper không làm thay công việc nghiệp vụ

Nó không:

- Tự xác minh access token ở thời điểm worker bắt đầu.
- Tự kiểm tra `report:read` hay tenant/owner.
- Tự gia hạn JWT hết hạn.
- Tự cấp transaction, request scope, MDC, locale hoặc tracing context.
- Tự ghi nhận exception vào audit log.
- Tự bảo đảm caller còn quyền sau khi logout/role bị thu hồi.

**Context propagation là cơ chế truyền dữ liệu xác thực, không phải authorization policy.**

## 8. DelegatingSecurityContextExecutor và ExecutorService

### 8.1. Executor raw không tự lấy danh tính user gửi task

Một `Executor` chỉ nhận `Runnable` rồi quyết định chạy ở thread nào:

```java
Executor pool = Executors.newFixedThreadPool(4);
pool.execute(() -> {
    Authentication a =
            SecurityContextHolder.getContext().getAuthentication();
    // Không có bảo đảm a là caller của request gửi task.
});
```

Hơn nữa, đoạn ví dụ trên tạo pool nhưng không đóng, nên **không nên dùng như code production hoàn chỉnh**. Hãy quản lý lifecycle, pool size, queue, saturation và shutdown.

### 8.2. Bọc Executor để capture ngữ cảnh theo mỗi lần submit

```java
Executor rawExecutor = ...; // Executor được quản lý bởi ứng dụng.

Executor securedExecutor =
        new DelegatingSecurityContextExecutor(rawExecutor);

// Được gọi từ request thread sau authentication:
securedExecutor.execute(() -> reportService.generateAllowedReport());
```

Khi khởi tạo `DelegatingSecurityContextExecutor` **không truyền một `SecurityContext` cố định**, wrapper dùng context hiện hành ở thời điểm `execute` được gọi để bọc task. Theo tài liệu Spring Security, đây là cách làm để task chạy dưới danh tính **người gửi task tại thời điểm submit**.

Điểm khác với một worker đọc context sau này:

```text
Submit:
  request thread: Alice
      └─ securedExecutor.execute(task)
            └─ capture Alice

Execute:
  worker thread:
      ├─ install captured SecurityContext
      ├─ run(task)
      └─ cleanup
```

**Lưu ý thời điểm capture:** nếu gửi task từ thread **đã mất context** (ví dụ callback khác, scheduler hoặc main application thread), wrapper không thể tự suy ra user cũ. Tên bean có chữ `secured` không khiến danh tính xuất hiện từ hư không.

### 8.3. Constructor nhận SecurityContext cố định: công cụ khác, rủi ro khác

```java
SecurityContext fixed = SecurityContextHolder.createEmptyContext();
// Cần Authentication được tạo/xác minh hợp lệ theo mô hình ứng dụng.

Executor privilegedExecutor =
        new DelegatingSecurityContextExecutor(rawExecutor, fixed);
```

Constructor nhận context cố định nghĩa là **mọi task của executor đó dùng context đã chỉ định**, không phải principal của request submit. Điều này hữu ích với tác vụ vận hành có **service identity** được kiểm soát, nhưng là rủi ro nếu vô tình cấu hình bằng context ADMIN của một request rồi để mọi user gửi việc vào pool đó.

Không dùng context của một admin user để “chữa lỗi thiếu quyền” cho mọi task. Nếu thật sự cần service principal, mô tả rõ permissions, thời hạn, audit, nguồn cấp tin cậy và cơ chế kiểm tra đối tượng.

### 8.4. ExecutorService và ScheduledExecutorService

Nếu dùng JDK `ExecutorService`, Spring Security cung cấp `DelegatingSecurityContextExecutorService`; với scheduler, có `DelegatingSecurityContextScheduledExecutorService` và các lớp cho Spring Task.

```java
ExecutorService raw = Executors.newFixedThreadPool(4);
ExecutorService secured =
        new DelegatingSecurityContextExecutorService(raw);

// Tại request thread:
Future<String> result = secured.submit(
        () -> reportService.getCurrentUserReport());
```

Đây là fragment, cần quản lý lifecycle của `raw`/`secured` và xử lý `Future`. Việc bọc service hỗ trợ task chạy dưới context của caller; không làm kết quả trở nên được ủy quyền vĩnh viễn. Scheduled jobs định kỳ **không có request user tự nhiên** và không nên kế thừa một principal từng submit mãi mãi mà không thiết kế chính sách.

## 9. @Async và Spring TaskExecutor: đặt wrapper ở đâu?

### 9.1. @Async chạy bằng task executor, không tự bảo đảm context

`@Async` của Spring chuyển lời gọi method sang `TaskExecutor` khi invocation đi qua Spring proxy/async infrastructure. Nhưng `@Async` không đồng nghĩa `SecurityContextHolder` tự hiện diện trong worker đối với mọi executor. Cần xác định executor nào đang chạy task.

Ví dụ bean config:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
public class AsyncExecutorConfig {

    @Bean("rawAsyncExecutor")
    ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("secure-work-");
        return executor;
    }

    @Bean("securedAsyncExecutor")
    AsyncTaskExecutor securedAsyncExecutor(
            ThreadPoolTaskExecutor rawAsyncExecutor) {
        return new DelegatingSecurityContextAsyncTaskExecutor(
                rawAsyncExecutor);
    }
}
```

**Đây là class cấu hình dùng trong project Spring Boot**, cần dependency Spring Security và cấu hình `@EnableAsync` ở vị trí phù hợp nếu muốn dùng `@Async`. `ThreadPoolTaskExecutor` là bean được Spring quản lý lifecycle. Nếu ứng dụng có nhiều bean cùng type, dùng `@Qualifier("rawAsyncExecutor")` ở tham số injection để tránh ambiguity.

### 9.2. Dùng tên bean ở @Async

```java
@Service
public class ExportService {

    @Async("securedAsyncExecutor")
    public CompletableFuture<String> exportForCurrentUser(String reportId) {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        // Bảo vệ object/tenant trong service thật.
        String result = "requested by " + authentication.getName();
        return CompletableFuture.completedFuture(result);
    }
}
```

Đây là fragment của Spring-managed service, chưa có `@EnableAsync`/`SecurityFilterChain`/policy resource thật. Khi gọi method từ **bean khác qua proxy**, `@Async` đưa việc thực thi vào secured executor; wrapper có thể truyền context của thread gửi task.

**Rủi ro self-invocation:** `this.exportForCurrentUser(...)` gọi từ một method khác của chính bean có thể bỏ qua proxy nên **không chạy async**. Ngoài ra, thứ tự AOP/authorization interceptor khi kết hợp `@PreAuthorize` và `@Async` phụ thuộc cấu hình; hãy test ở điểm service thật và không suy rằng annotation tự chạy ở đúng thread nếu chưa kiểm chứng.

### 9.3. Không dùng pool mặc định mà không biết nó là gì

Nếu viết:

```java
@Async
public void doWork() { ... }
```

mà không chỉ định executor, Spring có cơ chế chọn executor mặc định theo cấu hình/bean. Kết quả có thể khác giữa project. Với chức năng cần danh tính user, hãy **chỉ định và test executor thật**, thay vì giả định mọi `@Async` trong hệ thống đã được bọc.

### 9.4. Ngoại lệ và kết quả

- Method `@Async` trả `CompletableFuture`/`Future`: caller cần quan sát thất bại, timeout, cancellation.
- Method trả `void`: exception có thể đi qua `AsyncUncaughtExceptionHandler`, không tự xuất hiện trên request thread.
- `SecurityContext` được truyền không làm dữ liệu request tồn tại mãi; không giữ reference tới `HttpServletRequest` sau khi request hoàn tất.
- Thread pool có giới hạn queue/pool; nếu request tạo quá nhiều task, có thể cạn tài nguyên dù propagation chính xác.

## 10. CompletableFuture, nested async và giới hạn của propagation

### 10.1. ForkJoin common pool không lấy context của request

```java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() ->
            SecurityContextHolder.getContext()
                    .getAuthentication().getName());
```

**Anti-pattern minh họa:** overload không truyền `Executor` có thể chạy trên `ForkJoinPool.commonPool()` hoặc hành vi được JDK chọn; ThreadLocal user không được tự truyền. Có thể `NullPointerException` hoặc thiếu quyền ở service.

### 10.2. Truyền context-aware Executor cho từng stage cần thiết

```java
Executor securedExecutor = ...; // DelegatingSecurityContextExecutor

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> reportService.buildAuthorizedReport(), securedExecutor)
            .thenApplyAsync(
                result -> reportService.decorateAuthorizedResult(result),
                securedExecutor);
```

Đây là fragment tích hợp; cả `buildAuthorizedReport` và `decorateAuthorizedResult` cần chính sách đáng tin. Dùng executor tường minh giúp mỗi stage được chạy trên một nơi có cơ chế propagation.

**Cảnh báo nâng cao về thời điểm capture:** `DelegatingSecurityContextExecutor` không có context cố định sẽ capture từ **thread gọi `execute`**. Một stage tiếp theo có thể được schedule bởi thread khác, sau khi context đã dọn, hoặc trước/sau khi request kết thúc; vì vậy không được mặc định mọi stage tùy ý luôn mang đúng user nếu chỉ truyền cùng một wrapper. Với pipeline phức tạp, định nghĩa rõ context tại điểm handoff, dùng context cố định cho **riêng tác vụ đó** khi thật sự phù hợp, hoặc truyền actor ID/permissions theo policy có kiểm soát thay vì một SecurityContext mutable sống lâu.

### 10.3. thenApply khác thenApplyAsync

`thenApply` có thể chạy trên thread hoàn tất stage trước hoặc thread gọi khi stage đã hoàn tất, tùy thời điểm. `thenApplyAsync` thường đưa stage lên executor mặc định hoặc executor được chỉ định. Từ khóa “không Async” không có nghĩa luôn chạy trên HTTP request thread có context.

Khi code callback cần security identity, luôn kiểm tra **thread thực thi** và cách wrapper cài context; đừng dựa vào cảm giác rằng callback “là một phần của cùng future”.

### 10.4. parallelStream, virtual threads và reactive pipelines

`parallelStream()` thường dùng ForkJoin workers, không tự kế thừa context request theo nghĩa Spring Security `ThreadLocal`. Với Java virtual threads, mô hình thread và lifecycle khác pool thường, nhưng **không thể suy rằng một task chạy trên thread mới sẽ có đúng SecurityContext**. Spring Security Servlet vẫn phải sử dụng cơ chế rõ ràng để truyền identity khi đổi ranh giới thực thi. WebFlux dùng Reactor Context và API khác: không mang nguyên tutorial `ThreadLocal` của Servlet sang reactive pipeline.

### 10.5. Không đóng băng quyền trong CompletableFuture dài hạn

Nếu user được cấp quyền tại thời điểm tạo future rồi bị thu hồi role trước lúc stage ghi dữ liệu, **context được capture có thể chứa authority cũ**. Đối với thao tác nhạy cảm, kiểm tra quyền trên resource và membership hiện hành ngay trước commit hoặc theo mô hình transactional phù hợp; cần thiết kế chính sách revocation/cache riêng.

## 11. MODE_INHERITABLETHREADLOCAL không phải giải pháp mặc định cho thread pool

### 11.1. Ba chiến lược thường được nhắc tới

Spring Security cung cấp các chế độ `SecurityContextHolder`:

| Chiến lược | Ý nghĩa chính | Có phù hợp làm giải pháp mặc định cho pooled workers? |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Context theo thread hiện tại | Mặc định phù hợp đa số Servlet app |
| `MODE_INHERITABLETHREADLOCAL` | Child thread mới có thể kế thừa context khi tạo thread | **Không nên xem như giải pháp cho thread pool** |
| `MODE_GLOBAL` | Chia sẻ một context toàn JVM | Nguy hiểm trong ứng dụng nhiều user |

### 11.2. Vì sao inheritable context có thể gây nhầm user?

Một pool thường tạo worker **một lần**, sau đó dùng worker cho hàng nghìn task của các request khác nhau. `InheritableThreadLocal` truyền giá trị lúc **thread con được tạo**, không phải mỗi lần một `Runnable` được submit.

Giả sử:

```text
10:00 Pool tạo worker-1 khi Alice đang có context.
10:01 Alice gửi task A; worker-1 chạy.
10:02 Bob gửi task B; worker-1 được tái sử dụng.
```

Nếu dựa sai vào inheritable context, worker có thể mang danh tính Alice cũ hoặc giá trị không xác định theo vòng đời thread; Bob có thể bị xử lý sai quyền. Việc bật `MODE_INHERITABLETHREADLOCAL` toàn cục không thiết kế được propagation theo task và còn mở rộng nguy cơ rò rỉ khi tạo nhiều thread.

**Khuyến nghị:** giữ `MODE_THREADLOCAL` và dùng wrapper theo **đúng task/executor**, dọn context trong `finally`, kiểm tra isolation bằng test hai user khác nhau.

### 11.3. Không đổi strategy giữa khi ứng dụng đang phục vụ request

`SecurityContextHolder.setStrategyName(...)` thay đổi chiến lược toàn cục; đổi nhiều lần hoặc khi threads đang chạy có thể gây race/ảnh hưởng thread hiện tại. Không dùng trong từng controller/request để “bật truyền ngữ cảnh”; nếu phải cấu hình strategy đặc biệt, làm ở startup và có test đủ.

## 12. Propagation không thay thế re-authorization

### 12.1. Quyền lúc submit khác quyền lúc execute

Ví dụ:

```text
T0: Alice có report:export; gửi task xuất file r7.
T1: SecurityContext của Alice được capture và queue.
T2: Admin thu hồi report:export của Alice.
T3: Worker bắt đầu chạy export.
```

Nếu worker chỉ đọc authorities từ object `Authentication` được capture ở T0, nó có thể vẫn nhìn thấy quyền cũ. Truyền context không tự tải lại role từ database/JWT và không tự phát hiện revocation.

Giải pháp phụ thuộc nghiệp vụ:

- Tác vụ ít nhạy cảm: ghi nhận actor/requester ID, kiểm tra policy khi submit, dùng audit.
- Tác vụ nhạy cảm hoặc có thay đổi tiền: xác minh quyền/membership/trạng thái ở thời điểm thực thi và trước commit, cân nhắc thời hạn chấp thuận.
- Job chạy lâu: có chính sách khi quyền thay đổi, có thể hủy hoặc yêu cầu cấp lại trước hành động nhạy cảm.
- Lệnh từ queue: dùng identity đáng tin và policy/tenant scope, không tin vào JSON client tự khai `isAdmin=true`.

### 12.2. Copy context khác chụp giá trị bất biến

`SecurityContext` thường là một **đối tượng mutable** có reference tới `Authentication`. Nếu bạn chuyển nguyên object sang worker, không có bảo đảm nó là bản snapshot bất biến của toàn bộ thông tin quyền. Có thể có update đồng thời, context bị clear/replace hoặc Authentication chứa details mà không an toàn khi dùng giữa threads.

Khi bắt buộc tách object context giữa task và caller, có thể tạo context mới:

```java
SecurityContext source = SecurityContextHolder.getContext();

SecurityContext copy = SecurityContextHolder.createEmptyContext();
copy.setAuthentication(source.getAuthentication());
```

**Cảnh báo:** ví dụ này chỉ tạo **SecurityContext container mới**; `Authentication` vẫn là **cùng reference**, không phải deep copy/snapshot immutable. Không xem đây là giải pháp cho revocation hay concurrency nếu Authentication/details cũng mutable. Với workflow dài hạn, prefer actor ID + dữ liệu có nguồn tin cậy và kiểm tra lại theo nghiệp vụ.

### 12.3. Authorization theo đối tượng vẫn bắt buộc

Request `GET /api/files/f9` có `file:read` không mặc nhiên được phép đọc mọi file. Dù worker có `SecurityContext` chính xác, service vẫn cần:

```text
ALLOW =
    authenticated
    AND hasAuthority("file:read")
    AND sameTenant(actor, file)
    AND canReadOwnerOrShare(actor, file)
    AND file.status permits read
```

Các hàm là **pseudo-policy domain**, không phải method có sẵn của Spring Security. Với Spring MVC `Callable` hoặc `DeferredResult`, quy tắc theo file nên đặt ở service và repository/query layer có thể test, không chỉ trong controller.

### 12.4. Transaction, request scope, MDC không tự đi theo

Propagation của `SecurityContext` không tự truyền:

- Transaction và EntityManager ràng buộc với request thread.
- Request-scoped bean hoặc `RequestContextHolder`.
- MDC/logging correlation IDs hoặc distributed tracing baggage.
- Locale/time zone của user.
- Thread-bound resource locks.
- Servlet response lifecycle, timeout và connection state.

Mỗi loại context có **cơ chế propagation riêng**. Đừng giả định `DelegatingSecurityContextExecutor` khiến mọi `ThreadLocal` trong ứng dụng tự được truyền.

## 13. Ví dụ Java 17 chạy độc lập: truyền context và dọn worker

Chương trình sau không dùng thư viện Spring, tự mô phỏng:

- một `ThreadLocal<Caller>` chứa danh tính của thread;
- một `ExecutorService` tạo **một worker thread tái sử dụng**;
- một `Executor` bọc task và **capture caller khi submit**;
- hành động `finally` khôi phục context cũ của worker để tránh rò rỉ;
- hai người dùng Alice/Bob được gửi nối tiếp qua cùng pool;
- một task lỗi vẫn được cleanup.

Đây là demo **khái niệm** tương ứng với wrapper propagation, **không phải implementation của `SecurityContextHolder` hoặc authorization framework thật**. Mẫu giản lược để học, không nên đưa nguyên xi vào production thay `DelegatingSecurityContextExecutor`.

Tạo file `ContextHandoffDemo.java`:

```java
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;

public class ContextHandoffDemo {

    record Caller(String username, Set<String> authorities) {}

    private static final ThreadLocal<Caller> CURRENT =
            new ThreadLocal<>();

    private static String describe() {
        Caller caller = CURRENT.get();
        if (caller == null) {
            return "NO_CONTEXT";
        }
        boolean canRead = caller.authorities().contains("report:read");
        return caller.username() + "/read=" + canRead;
    }

    private static Executor contextual(Executor delegate) {
        return command -> {
            // Capture trên thread đang GỬI task.
            Caller captured = CURRENT.get();

            delegate.execute(() -> {
                Caller previous = CURRENT.get();
                try {
                    if (captured == null) {
                        CURRENT.remove();
                    } else {
                        CURRENT.set(captured);
                    }
                    command.run();
                } finally {
                    // Khôi phục trạng thái trước task, tránh lây qua pool.
                    if (previous == null) {
                        CURRENT.remove();
                    } else {
                        CURRENT.set(previous);
                    }
                }
            });
        };
    }

    private static <T> T call(
            Executor executor, Callable<T> work) throws Exception {
        FutureTask<T> future = new FutureTask<>(work);
        executor.execute(future);
        return future.get();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService rawPool = Executors.newSingleThreadExecutor();
        Executor secured = contextual(rawPool);

        try {
            Caller alice = new Caller(
                    "alice", Set.of("ROLE_USER", "report:read"));
            Caller bob = new Caller(
                    "bob", Set.of("ROLE_USER"));

            CURRENT.set(alice);
            System.out.println("main-alice=" + describe());
            System.out.println("raw-alice="
                    + call(rawPool, ContextHandoffDemo::describe));
            System.out.println("wrapped-alice="
                    + call(secured, ContextHandoffDemo::describe));

            CURRENT.set(bob);
            System.out.println("wrapped-bob="
                    + call(secured, ContextHandoffDemo::describe));
            System.out.println("raw-after-bob="
                    + call(rawPool, ContextHandoffDemo::describe));

            // Task cố ý lỗi để kiểm tra finally vẫn dọn context.
            FutureTask<String> failing = new FutureTask<>(
                    () -> { throw new IllegalStateException("demo"); });
            secured.execute(failing);
            try {
                failing.get();
            } catch (ExecutionException expected) {
                System.out.println("failure-caught="
                        + expected.getCause().getClass().getSimpleName());
            }

            System.out.println("raw-after-failure="
                    + call(rawPool, ContextHandoffDemo::describe));
            System.out.println("main-bob=" + describe());

            CURRENT.remove();
            System.out.println("wrapped-without-caller="
                    + call(secured, ContextHandoffDemo::describe));
        } finally {
            CURRENT.remove();
            rawPool.shutdown();
            if (!rawPool.awaitTermination(5, TimeUnit.SECONDS)) {
                rawPool.shutdownNow();
            }
        }
    }
}
```

Chạy với **JDK 17+**:

```bash
javac ContextHandoffDemo.java
java ContextHandoffDemo
```

Stdout xác định theo logic tuần tự của `FutureTask.get()`:

```text
main-alice=alice/read=true
raw-alice=NO_CONTEXT
wrapped-alice=alice/read=true
wrapped-bob=bob/read=false
raw-after-bob=NO_CONTEXT
failure-caught=IllegalStateException
raw-after-failure=NO_CONTEXT
main-bob=bob/read=false
wrapped-without-caller=NO_CONTEXT
```

### 13.1. Diễn giải kết quả

1. `main-alice`: caller thread có danh tính Alice và permission đọc.
2. `raw-alice=NO_CONTEXT`: worker pool không tự nhận `ThreadLocal` của request thread.
3. `wrapped-alice`: wrapper capture Alice **khi submit**, sau đó cài Alice vào worker.
4. `wrapped-bob`: cùng worker được dùng lại nhưng wrapper đúng làm xuất hiện Bob, không phải Alice.
5. `raw-after-bob=NO_CONTEXT`: cuối task của Bob, worker đã sạch; không có identity leak.
6. Task ném `IllegalStateException` nhưng `FutureTask` ghi nhận exception, wrapper `finally` vẫn chạy.
7. `raw-after-failure=NO_CONTEXT` chứng minh cleanup cả khi có lỗi.
8. `main-bob` cho thấy ngữ cảnh của caller thread độc lập với worker.
9. `wrapped-without-caller=NO_CONTEXT`: wrapper không tự tạo danh tính khi submit từ thread không có caller.

### 13.2. Những khác biệt với Spring Security thật

- Demo dùng `ThreadLocal<Caller>` thay vì `SecurityContextHolder`.
- Demo không triển khai `SecurityContextHolderStrategy`, authentication managers, JWT hoặc method security.
- Demo khôi phục `previous` của worker; Spring Security wrappers có contract đặt/dọn ngữ cảnh phù hợp với phiên bản API.
- Demo không có ranh giới request/HTTP, timeout, cancellation, CSRF hoặc asynchronous servlet dispatch.
- Demo không kiểm tra quyền tenant/resource; nó chỉ cho thấy cơ chế cài và dọn danh tính.

**Giá trị học tập:** trước khi dùng Spring Security APIs, hãy nắm rõ ngữ cảnh được capture ở đâu, sử dụng trên thread nào, và được xóa/khôi phục khi nào.

## 14. Testing: xác minh propagation, isolation và authorization

### 14.1. Ma trận tối thiểu

| Tình huống | Kết quả mong đợi |
| --- | --- |
| HTTP request đồng bộ có auth Alice | Controller/service thấy Alice |
| MVC `Callable` của Alice | Thread thực thi Callable thấy Alice khi integration hoạt động |
| Servlet `AsyncContext.start` qua wrapped request | Runnable thấy Authentication Alice |
| Raw `ExecutorService` của Alice | Không mặc định có Alice; service bảo mật phải fail closed |
| `DeferredResult` hoàn tất qua raw executor | Không có auto propagation |
| `DeferredResult` hoàn tất qua secured executor | Task thấy context được capture đúng |
| `@Async` với executor không bọc | Không giả định có đúng principal |
| `@Async` với Delegating wrapper | Context được truyền khi submit đúng điểm |
| Alice và Bob submit vào cùng pool | Mỗi task thấy đúng người, không lây chéo |
| Task ném exception | Worker không còn principal của task trước |
| Task submit khi không có context | Không được tự nhận context của user cũ |
| Quyền bị thu hồi trước khi worker thực thi | Policy re-check theo yêu cầu; không tin snapshot cũ |
| Request thiếu permission | Bị từ chối dù propagation thành công |
| Async timeout/cancel | Không leak context, không double complete/side effect |
| Nhiều filter chains và ASYNC dispatch | Đúng chain, authz không bị bypass |

### 14.2. MockMvc kiểm thử Spring MVC Callable

Đây là **test fragment** yêu cầu `MockMvc`, Spring Security Test, controller `GET /api/me/callable` ở phần 5, security filter chain và imports:

```java
@Test
@WithMockUser(username = "alice", authorities = "report:read")
void callableGetsRequestPrincipal() throws Exception {
    MvcResult result = mockMvc.perform(get("/api/me/callable"))
            .andExpect(request().asyncStarted())
            .andReturn();

    mockMvc.perform(asyncDispatch(result))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
}
```

Snippet cần các static imports từ `MockMvcRequestBuilders`, `MockMvcResultMatchers` và `SecurityMockMvcRequestPostProcessors` khi có dùng. Nếu controller return `ResponseEntity<String>`, response body như ví dụ là `alice`. `@WithMockUser` tạo Authentication test, không kiểm tra JWT converter production.

**Đừng chỉ test rằng `Callable` chạy**. Test nội dung user quan sát được hoặc service security decision, rồi test thiếu quyền/anonymous theo cùng route.

### 14.3. Kiểm thử DeferredResult bằng hai user

Với pool có một worker để lộ rõ lỗi rò rỉ:

1. Alice submit một task qua secured executor → task thấy Alice.
2. Bob submit một task qua cùng executor → task thấy Bob.
3. Gửi raw task không có wrapper → không thấy Alice/Bob sót lại.
4. Cho task Alice cố ý ném exception → task tiếp theo vẫn không thấy Alice.
5. Gửi một task khi request thread đã logout/clear context → không được tự nhận user cũ.
6. Dùng countdown latch để điều khiển thời điểm submit/execute nếu cần test chính xác concurrency và revocation; không dựa vào `Thread.sleep` để tạo race ngẫu nhiên.

### 14.4. Kiểm thử @Async và @PreAuthorize

`@Async` gọi qua proxy khác với self-invocation. Nên test từ một bean/controller khác; xác minh:

- executor mà `@Async` lựa chọn chính là bean đã bọc;
- context được capture khi submit có đúng Authentication test;
- service method có `@PreAuthorize` được gọi qua Spring proxy;
- user chỉ có `report:read` không được gọi use case cần `report:export`;
- với object ngoài tenant, method vẫn bị từ chối dù role đúng;
- exception của task được phản ánh qua `Future`/`CompletableFuture` hoặc handler đã cấu hình.

Đặc biệt, đừng giả định `@PreAuthorize` trên một method `@Async` luôn được đánh giá ở thread caller hay worker trong mọi thứ tự AOP; kiểm tra trên version/cấu hình cụ thể và đặt policy quan trọng ở service boundary đáng tin.

### 14.5. Test servlet AsyncContext với embedded container khi cần

`MockMvc` có hỗ trợ một số Servlet async flow, nhưng nếu test của bạn phụ thuộc `AsyncContext.start`, dispatcher registrations, timeout, request wrappers hoặc behavior container, cần integration test với **embedded server thật**. Kiểm tra status, response, thread cleanup, dispatch type và không phát sinh exception khi client cancel.

### 14.6. Test fail-closed khi context vắng

Khi `Authentication` là null hoặc anonymous, code không nên làm:

```java
// Anti-pattern: không tự cho phép nếu worker thiếu auth.
if (SecurityContextHolder.getContext().getAuthentication() == null) {
    return exportEverything();
}
```

Thay vào đó, chặn hoặc dùng policy thực sự tương ứng với system actor, audit lý do. Nếu anonymous hợp lệ cho một công việc đọc công khai, ghi rõ route/policy public; không mở nhầm đường có dữ liệu người dùng.

## 15. Các tình huống phức tạp và cách quyết định

### 15.1. Scheduled job không có request user

Một `@Scheduled` job tổng hợp báo cáo mỗi đêm **không có request** và không nên tự đòi `SecurityContextHolder` của một user ngẫu nhiên. Có thể:

- Thiết kế một **service account/principal** với quyền tối thiểu cho tác vụ.
- Chạy qua domain API có cơ chế system action riêng và audit.
- Kiểm tra tenant, dữ liệu và scope mà job được phép xử lý.
- Không tạo `ROLE_ADMIN` toàn cục cho job chỉ để bypass mọi permission.

Với multi-tenant batch, chạy dưới một service identity có hạn chế scope cụ thể thay vì tận dụng principal request cuối cùng trên một thread.

### 15.2. Queue/event consumer

Không thể truyền một Java object `SecurityContext` qua Kafka/RabbitMQ như thể nó vẫn là request session. Job payload có thể lưu actor ID, tenant ID, action ID và correlation ID, nhưng **đây là dữ liệu do producer gửi**. Consumer phải xác minh nguồn message, tính toàn vẹn, chính sách idempotency và authorization theo security boundary của mình.

Nếu một consumer dùng claim `role=ADMIN` do payload client gửi mà không kiểm chứng, đó là **bypass authorization**. Khi cần làm đúng thay người dùng, áp dụng delegation/impersonation có kiểm soát, TTL, audit và khả năng thu hồi.

### 15.3. Async work sau khi HTTP response đã trả

Nếu controller trả 202 rồi worker xử lý lâu:

- `SecurityContext` ở worker có thể đã được capture tại lúc tạo task.
- Session/JWT có thể hết hạn sau response.
- Người dùng có thể đổi role, bị khóa hoặc rời tenant.
- Trạng thái resource có thể đã thay đổi.

Vì vậy, với tác vụ quan trọng, dùng job ID và workflow authorization rõ ràng: **submit allowed?**, **execute still allowed?**, **view/download result allowed?**. Không giữ request/response object làm “bảo hiểm” cho quyền.

### 15.4. AsyncContext, Callable hay DeferredResult cho loại việc nào?

| Nhu cầu | Lựa chọn thường phù hợp | Cảnh báo |
| --- | --- | --- |
| Servlet cấp thấp cần tự điều khiển response async | `AsyncContext` | Lifecycle/timeout/filter/response do app chịu trách nhiệm |
| MVC controller muốn trả kết quả từ tác vụ async đơn giản | `Callable<T>` | Context auto-integrated nhưng nested tasks không tự được truyền |
| Result được tạo bởi event/callback về sau | `DeferredResult<T>` | Task hoàn tất do app sở hữu, cần context wrapper |
| Service method async với Spring AOP | `@Async` + configured executor | Proxy, @EnableAsync, context-aware executor, error handling |
| Pipeline nhiều stage | `CompletableFuture` với chiến lược executor rõ | Capture timing và nested stages |
| Công việc dài hạn/durable | Queue/job store | Không truyền nguyên context; re-authorization, audit |

### 15.5. Khi nào không cần truyền SecurityContext?

Không phải task nào cũng nên mượn danh tính caller. Ví dụ định dạng ảnh public hoặc gửi metrics hệ thống không cần security context, có thể chạy dưới worker không có principal. Càng ít context được truyền thì càng giảm nguy cơ lộ thông tin và coupling.

Nếu API nghiệp vụ yêu cầu biết **ai khởi tạo tác vụ** để audit, có thể truyền `actorId` như một **giá trị dữ liệu** đã xác minh thay vì truyền `Authentication` chứa credentials/authorities. Khi action có rủi ro, consumer/service vẫn phải kiểm tra quyền từ nguồn tin cậy. **Không coi actorId trong message do client điều khiển là bằng chứng xác thực.**

## 16. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| `SecurityContextHolder.getContext().getAuthentication() == null` trong executor | ThreadLocal không tự được truyền | Bọc Executor/Callable, xác minh submit thread |
| MVC Callable thấy user nhưng CompletableFuture nested không thấy | Nested task chạy ở pool khác | Truyền executor phù hợp cho stage |
| DeferredResult không có principal | Không có auto integration cho user task | Dùng context-aware executor/explicit actor |
| `AsyncContext.start` không chạy đúng | Servlet/filter không hỗ trợ async hoặc lifecycle lỗi | Kiểm tra asyncSupported, dispatcher, timeout |
| `new Thread` thấy null Authentication | Không qua Spring integration | Dùng wrapper, tránh tự tạo thread thủ công |
| Bob thấy authorities của Alice | Worker bị giữ ThreadLocal cũ, thiếu cleanup hoặc inheritable mode sai | Dùng wrapper chuẩn, test pool reuse 2 user |
| `@Async` chạy trên caller thread | Self-invocation/proxy chưa bật | Kiểm tra `@EnableAsync` và cross-bean call |
| `@Async` chạy nhưng không có user | Executor chưa được bọc hoặc chọn sai bean | Kiểm tra @Async qualifier và executor instance |
| `Future` lỗi nhưng controller trả 200 | Không quan sát exception/await result đúng cách | Ghi nhận completion/error rõ |
| Authorization pass ở submit nhưng fail khi execute | Context đổi hoặc policy theo dữ liệu hiện tại khác | Rà soát capture timing, re-check |
| Authorization pass sau khi role bị thu hồi | Snapshot authorities cũ được dùng lâu | Kiểm tra revocation, TTL, policy at execution |
| Job tự có admin dù caller là user thường | Executor dùng context cố định nhiều quyền | Không dùng privileged fixed context bừa bãi |
| Tác vụ async làm hỏng DB transaction | Transaction thread-bound không tự truyền | Thiết kế transaction riêng trong worker |
| MDC/tracing mất trên worker | SecurityContext wrapper chỉ xử lý security | Thêm propagation theo từng context loại khác |
| Request đã complete nhưng worker vẫn ghi response | Sai lifecycle AsyncContext | Timeout/cancel/complete đúng |
| Test MockMvc pass, server production fail | Container/filters/async redispatch khác | Integration test cùng servlet stack |

### Năm câu hỏi khi gỡ lỗi

1. **Task thực chạy trên thread nào?** Log thread name có kiểm soát.
2. **Ai submit task và tại thời điểm nào?** Có SecurityContext ở thread submit không?
3. **Executor/cơ chế nào đang thực thi?** `AsyncContext.start`, MVC Callable, raw pool, @Async hay callback?
4. **Context được cleanup không?** Gửi Alice → Bob → raw task vào cùng pool để kiểm tra rò rỉ.
5. **Policy đã chạy lại ở nơi thực hiện side effect chưa?** Đúng permission, object, tenant, thời gian hiệu lực?

Không sửa lỗi bằng cách chuyển mọi thứ sang `MODE_GLOBAL` hoặc cấp `ROLE_ADMIN` mặc định cho task không có user.

## 17. Quy trình áp dụng vào dự án thực tế

**Bước 1 — Phân loại asynchronous boundary.** Tìm các điểm dùng `request.startAsync`/`AsyncContext.start`, controller `Callable`/`DeferredResult`, `ExecutorService`, `@Async`, `CompletableFuture`, scheduler và message consumers. Xác định **nơi nào thật sự đổi thread**.

**Bước 2 — Vẽ điểm capture và execution.** Ghi rõ SecurityContext của user ở đâu, task được submit từ thread nào, worker có thể chạy trễ bao lâu và task dùng authority nào.

**Bước 3 — Chọn cơ chế propagation đúng.** Dùng tích hợp Servlet `AsyncContext.start`/MVC `Callable` khi có; với `DeferredResult`, raw pool hoặc @Async, dùng wrapper thuộc Spring Security phù hợp. Không lồng nhiều wrapper không cần thiết và đừng tạo context cố định toàn app ngoài chủ đích.

**Bước 4 — Bảo vệ thread pool.** Quản lý kích thước pool, queue, timeout, shutdown, saturation và exception. Đảm bảo worker cleanup context trong mọi nhánh. Tránh raw `SecurityContextHolder.setContext` thiếu `finally`.

**Bước 5 — Giữ ranh giới authorization.** HTTP route/Method security kiểm tra chức năng; service kiểm tra object/tenant/state; với job chạy trễ có chính sách re-authorization/revocation.

**Bước 6 — Không trộn các ThreadLocal.** Transaction, request scope, MDC, locale, tracing và SecurityContext có cơ chế khác nhau; cấu hình từng loại khi thực sự cần, tránh gửi credentials sang nơi không cần.

**Bước 7 — Test hai principal và exception.** Alice/Bob trên cùng pool, wrapper có/không có context, task ném lỗi, timeout/cancel, user bị thu hồi quyền, khác tenant.

**Bước 8 — Test đúng runtime.** Với MVC Callable dùng MockMvc asyncDispatch; với Servlet AsyncContext và dispatcher configuration dùng embedded server; với @Async test Spring proxy và executor bean.

**Bước 9 — Rà soát các nhiệm vụ vượt request.** Đưa tác vụ lâu dài sang job/queue, lưu actor ID đã được xác minh + metadata tối thiểu, có TTL/audit và authorization ở bước execute/result download.

**Bước 10 — Đối chiếu phiên bản.** API wrappers và Spring MVC integration có mặt trong Spring Security 6.x/7.x, nhưng cấu hình cụ thể có thể đổi. Dựa trên resolved dependency/BOM/Javadoc, không chỉ dựa vào snippet "current" hoặc assume same behavior giữa Servlet và WebFlux.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `SecurityContextHolder` trong một raw `ExecutorService` có thể không có user dù request caller đã đăng nhập?

**Đáp án:** `SecurityContextHolder` mặc định dựa trên `ThreadLocal`. Worker pool là thread khác và không tự nhận context của thread HTTP. Dùng cơ chế propagation đúng tại điểm submit.

**Câu 2.** `AsyncContext.start(Runnable)` và `new Thread(runnable).start()` có tương đương về Spring Security context không?

**Đáp án:** Không. Spring Security có tích hợp với `AsyncContext.start` qua Servlet request/async wrapper. `new Thread` không tự đi qua integration ấy.

**Câu 3.** Spring MVC controller trả `Callable<String>`. Có cần tự bọc Callable theo mặc định không?

**Đáp án:** Thường không trong cấu hình tích hợp Spring Security/MVC chuẩn. `WebAsyncManager` truyền context cho thread thực thi `Callable`. Nhưng task nested do ứng dụng tự tạo bên trong vẫn cần cơ chế riêng.

**Câu 4.** Spring MVC controller trả `DeferredResult<String>` và dùng raw thread pool để gọi `setResult`. Có auto propagation không?

**Đáp án:** Không cho user task tự thực thi. Dùng context-aware executor/explicit propagation hoặc thiết kế actor data đáng tin phù hợp.

**Câu 5.** `DelegatingSecurityContextExecutor(raw)` không truyền context cố định sẽ lấy context của user ở đâu?

**Đáp án:** Tại thời điểm `execute` nhận task, từ `SecurityContextHolder` của thread submit. Nếu thread submit không có user, wrapper không tự tìm được user cũ.

**Câu 6.** Khác nhau giữa constructor `DelegatingSecurityContextExecutor(raw)` và `DelegatingSecurityContextExecutor(raw, fixedContext)`?

**Đáp án:** Dạng đầu capture context của từng submit; dạng sau dùng context cố định cho các task. Dạng cố định cần review quyền đặc biệt để không dùng một user/ADMIN cho mọi caller.

**Câu 7.** Có nên bật `MODE_INHERITABLETHREADLOCAL` cho toàn app để sửa lỗi propagation trong pooled workers?

**Đáp án:** Không nên. Inheritable context được truyền khi **tạo child thread**, không phải mỗi lần pool nhận task; có rủi ro nhầm/leak danh tính giữa user.

**Câu 8.** Wrapper làm `getAuthentication()` trả Alice, vậy Alice còn quyền report:export tại lúc task chạy chắc chắn không?

**Đáp án:** Không. Context đã capture có thể chứa quyền cũ. Với tác vụ nhạy cảm cần tái kiểm tra policy/membership/tenant theo thời điểm thực thi.

**Câu 9.** `@Async("securedAsyncExecutor")` không chạy bất đồng bộ khi gọi từ chính bean của nó. Khả năng nào xảy ra?

**Đáp án:** Self-invocation bỏ qua Spring AOP proxy. Cần gọi từ bean khác qua proxy và bật `@EnableAsync`, đồng thời test executor được chọn.

**Câu 10.** Có `SecurityContext` ở worker thì transaction và MDC có tự được truyền không?

**Đáp án:** Không. Transaction, request context, MDC, locale và tracing là các loại context khác; cần thiết kế propagation riêng khi cần.

**Câu 11.** Vì sao cần `finally` dọn context?

**Đáp án:** Thread pool tái sử dụng worker. Nếu task lỗi mà context không được dọn, task sau có thể nhìn thấy user trước, tạo lỗ hổng dữ liệu/authorization.

**Câu 12.** Một job được tạo từ HTTP request phải tiếp tục chạy nhiều giờ sau khi logout. Có nên giữ nguyên `HttpServletRequest` và `SecurityContext` của user?

**Đáp án:** Không. Chuyển sang job durable, lưu metadata người yêu cầu đã xác minh ở mức tối thiểu, có authorization/revocation/audit khi execute và khi truy vấn kết quả.

**Tóm tắt:** `AsyncContext.start` và MVC `Callable` có hỗ trợ truyền `SecurityContext` trong Spring Security Servlet khi integration hoạt động; `DeferredResult`, raw executors, `@Async` và nested futures đòi kiểm soát điểm handoff. Truyền đúng principal **không** thay cho authorization trên action/object và không cho phép giữ quyền cũ mãi mãi. Với pooled workers, luôn nghĩ tới **capture → set → execute → cleanup → re-check khi cần**.

## Tài liệu tham khảo chính thức

- Spring Security — Servlet API integration, `AsyncContext.start(Runnable)` và async dispatch: https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html
- Spring Security — Spring MVC Async Integration, `Callable`, giới hạn `DeferredResult`: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html
- Spring Security — Concurrency Support và danh sách DelegatingSecurityContext*: https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html
- Spring Security — Servlet Authentication Architecture và `SecurityContextHolder`: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security 7.0 — `WebAsyncManagerIntegrationFilter` Javadoc: https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/web/context/request/async/WebAsyncManagerIntegrationFilter.html
- Spring Security 7.0 — `DelegatingSecurityContextAsyncTaskExecutor` API: https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html
- Spring Security — Method Security và method interceptors: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework — Asynchronous Requests của Spring MVC: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — Task Execution, @Async và scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Security — HTTP authorization và dispatcher types: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
