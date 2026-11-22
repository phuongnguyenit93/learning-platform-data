# Dọn `RequestContextHolder` để không rò trạng thái giữa bài

`RequestContextHolder` là cơ chế Spring dùng để lưu `RequestAttributes` gắn với thread hiện tại. Trong ứng dụng Servlet, các thành phần như `DispatcherServlet`, `RequestContextFilter` hoặc `RequestContextListener` có thể bind thông tin request vào holder để code phía dưới truy cập request hiện tại mà không phải truyền `HttpServletRequest` qua mọi phương thức.

Vì trạng thái này được giữ bằng `ThreadLocal` (hoặc `InheritableThreadLocal` nếu được yêu cầu), nó phải được gỡ khỏi thread khi request hoặc bài kiểm thử kết thúc. Nếu một test tự bind `RequestAttributes` rồi quên gọi `RequestContextHolder.resetRequestAttributes()`, thread chạy test có thể giữ lại request cũ. Khi JUnit hoặc executor tái sử dụng thread đó, bài test tiếp theo có thể nhìn thấy tenant, locale, session hoặc request attribute của test trước.

Trong kiểm thử Spring MVC qua `MockMvc`, Spring quản lý việc bind và cleanup trong vòng đời dispatch. Nhưng khi test gọi service trực tiếp, tự tạo `ServletRequestAttributes`, chạy tác vụ trên executor hoặc tự thao tác với `RequestContextHolder`, test phải chịu trách nhiệm về vòng đời trạng thái đã bind.

## 1. `RequestContextHolder` lưu những gì?

`RequestContextHolder` là một lớp tiện ích tĩnh cung cấp quyền truy cập tới `RequestAttributes` gắn với thread hiện tại. Trong môi trường Servlet, đối tượng thường được bind là `ServletRequestAttributes`, bao bọc `HttpServletRequest` và có thể cả `HttpServletResponse`.

Một số API chính:

| API | Ý nghĩa |
|---|---|
| `setRequestAttributes(attributes)` | Bind attributes vào thread hiện tại, không kế thừa sang child thread. |
| `setRequestAttributes(attributes, true)` | Bind bằng `InheritableThreadLocal`, cho phép thread con được tạo trong lúc bind kế thừa tham chiếu. |
| `getRequestAttributes()` | Lấy attributes hiện tại hoặc trả `null` nếu không có. |
| `currentRequestAttributes()` | Lấy attributes hiện tại; ném `IllegalStateException` nếu không có request context phù hợp. |
| `resetRequestAttributes()` | Xóa cả request attributes thường và inheritable khỏi thread hiện tại. |

Ví dụ đọc request attributes:

```java
RequestAttributes attributes = RequestContextHolder.currentRequestAttributes();
Object tenantId = attributes.getAttribute("tenantId", RequestAttributes.SCOPE_REQUEST);
```

Trong code Servlet, có thể lấy request thật từ `ServletRequestAttributes`:

```java
ServletRequestAttributes attributes =
        (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();

HttpServletRequest request = attributes.getRequest();
String requestId = request.getHeader("X-Request-Id");
```

Holder không tạo request mới và cũng không tự quản lý session hoặc transaction. Nó chỉ cung cấp tham chiếu tới `RequestAttributes` đang được bind trên thread. Nếu không có request context, gọi `currentRequestAttributes()` sẽ thất bại thay vì tự tạo một context giả.

## 2. Vì sao trạng thái có thể rò giữa các test?

`ThreadLocal` lưu giá trị theo thread, không theo test method. JUnit thường chạy nhiều test method trên các thread worker có thể được tái sử dụng. Nếu test A đặt request attributes và không reset, test B chạy trên cùng thread có thể đọc được trạng thái còn sót.

```text
JUnit worker thread T1
    |
    +--> Test A: setRequestAttributes(request-A)
    |
    +--> Test A kết thúc nhưng không reset
    |
    +--> Test B chạy trên T1
             |
             +--> currentRequestAttributes() trả request-A
```

Điều này có thể gây lỗi khó hiểu:

- Test B đọc nhầm header hoặc request parameter của test A.
- Bean request-scoped truy cập session hoặc tenant sai.
- Logic chọn locale hoặc người dùng hiện tại nhận dữ liệu cũ.
- Test phụ thuộc thứ tự chạy và chỉ thất bại khi chạy cả suite.
- Test chạy riêng thì pass nhưng chạy song song hoặc trên CI lại thất bại.

`RequestContextHolder` dùng `ThreadLocal` nên hai test chạy trên hai thread riêng thường không nhìn thấy trạng thái của nhau. Vấn đề xuất hiện khi cùng thread được tái sử dụng, hoặc khi dùng `InheritableThreadLocal` và tạo thread con trong lúc context đang bind.

## 3. Bind và reset thủ công trong unit test

Khi test một service cần đọc request context nhưng không chạy qua `DispatcherServlet`, có thể tạo `MockHttpServletRequest`, bọc trong `ServletRequestAttributes`, rồi bind vào holder.

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

class CurrentTenantServiceTest {

    @Test
    void readsTenantFromCurrentRequest() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-Tenant", "tenant-a");
        ServletRequestAttributes attributes = new ServletRequestAttributes(request);

        try {
            RequestContextHolder.setRequestAttributes(attributes);

            assertThat(RequestContextHolder.currentRequestAttributes())
                    .isSameAs(attributes);

            HttpServletRequest currentRequest =
                    ((ServletRequestAttributes)
                            RequestContextHolder.currentRequestAttributes()).getRequest();
            assertThat(currentRequest.getHeader("X-Tenant")).isEqualTo("tenant-a");
        } finally {
            RequestContextHolder.resetRequestAttributes();
            attributes.requestCompleted();
        }
    }
}
```

Điểm quan trọng là `resetRequestAttributes()` nằm trong `finally`. Dù assertion ném lỗi hay code trong test thất bại, cleanup vẫn được thực hiện trên chính thread đã bind context.

`ServletRequestAttributes.requestCompleted()` thông báo request đã hoàn tất và thực thi các callback hủy request scope thích hợp. Khi test tự tạo `ServletRequestAttributes`, nên gọi phương thức này trong cleanup nếu test sử dụng request-scoped destruction callback hoặc muốn mô phỏng đầy đủ kết thúc request. Với test chỉ kiểm tra một tham chiếu đơn giản, reset holder là thao tác bắt buộc để tránh rò thread-local; `requestCompleted()` bổ sung vòng đời cho attributes đã tạo.

Không gọi `resetRequestAttributes()` ở một thread khác với thread đã bind. `ThreadLocal` chỉ xóa giá trị của thread hiện tại.

## 4. Dùng try-with-resources để cleanup tự động

Nếu nhiều test cần bind request context, có thể tạo helper nhỏ triển khai `AutoCloseable` để cleanup luôn chạy khi ra khỏi block.

```java
final class BoundRequestContext implements AutoCloseable {

    private final ServletRequestAttributes attributes;

    BoundRequestContext(MockHttpServletRequest request) {
        this.attributes = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(attributes);
    }

    @Override
    public void close() {
        try {
            RequestContextHolder.resetRequestAttributes();
        } finally {
            attributes.requestCompleted();
        }
    }
}
```

Dùng helper trong test:

```java
@Test
void readsRequestScopedData() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    request.addHeader("X-Tenant", "tenant-b");

    try (BoundRequestContext ignored = new BoundRequestContext(request)) {
        assertThat(tenantService.currentTenant()).isEqualTo("tenant-b");
    }

    assertThat(RequestContextHolder.getRequestAttributes()).isNull();
}
```

`close()` chạy cả khi block kết thúc bình thường lẫn khi assertion ném exception. Helper này được thiết kế cho test sở hữu request context trên thread hiện tại và không dùng lồng với một request context khác. Nếu test cần hỗ trợ nested binding, cần lưu và khôi phục context trước đó một cách có chủ đích thay vì luôn reset về `null`.

## 5. Khôi phục trạng thái trước đó khi cần nested context

Một số helper có thể được gọi bên trong một scope đã bind sẵn. Trong trường hợp đó, reset thẳng về `null` sẽ xóa context của caller. Cần lưu giá trị trước đó và khôi phục khi thoát scope.

Với trường hợp đơn giản, không sử dụng inheritable binding:

```java
final class NestedRequestContext implements AutoCloseable {

    private final RequestAttributes previous;
    private final ServletRequestAttributes current;

    NestedRequestContext(MockHttpServletRequest request) {
        previous = RequestContextHolder.getRequestAttributes();
        current = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(current, false);
    }

    @Override
    public void close() {
        try {
            if (previous == null) {
                RequestContextHolder.resetRequestAttributes();
            } else {
                RequestContextHolder.setRequestAttributes(previous, false);
            }
        } finally {
            current.requestCompleted();
        }
    }
}
```

Ví dụ này lưu object `RequestAttributes` trước đó và khôi phục nó dưới dạng non-inheritable. Chỉ dùng cách này khi contract của helper đảm bảo context trước đó là non-inheritable hoặc việc chuyển về non-inheritable được chấp nhận. `getRequestAttributes()` không cho biết context trước đó được bind bằng ThreadLocal thường hay `InheritableThreadLocal`; nếu cần bảo toàn chính xác chế độ binding, không nên tạo nested helper dựa trên getter này. Cách an toàn hơn cho phần lớn test là không lồng context và dùng một scope độc lập có `try/finally` rõ ràng.

## 6. Dùng JUnit lifecycle để dọn trạng thái

Nếu test class có nhiều phương thức cần bind request context, có thể đặt cleanup trong `@AfterEach`:

```java
class RequestContextHolderTest {

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.resetRequestAttributes();
    }

    @Test
    void firstTest() {
        // Test có thể bind request context.
    }

    @Test
    void secondTest() {
        // Bắt đầu với thread không còn request attributes từ test trước.
    }
}
```

`@AfterEach` là nơi thích hợp để bảo đảm cleanup sau từng test method. Có thể thêm `@BeforeEach` để khẳng định trạng thái khởi đầu sạch:

```java
@BeforeEach
void ensureNoRequestContextIsBound() {
    RequestContextHolder.resetRequestAttributes();
}
```

Tuy nhiên, cleanup ở `@BeforeEach` không thay thế cleanup ở `@AfterEach`. Nếu chỉ reset trước test, trạng thái bị rò từ test cuối cùng vẫn tồn tại sau khi class kết thúc và có thể ảnh hưởng test class tiếp theo chạy trên cùng thread. Ngoài ra, reset trước test có thể che giấu một test trước đó đã quên cleanup. Vì vậy, hãy đặt cleanup tại nơi tạo binding và/hoặc trong `@AfterEach`; dùng `@BeforeEach` như một guard bổ sung khi có lý do cụ thể.

### Tạo JUnit extension dùng chung

Nếu nhiều test class cần chính sách dọn request context, có thể dùng extension:

```java
import org.junit.jupiter.api.extension.AfterEachCallback;
import org.junit.jupiter.api.extension.ExtensionContext;
import org.springframework.web.context.request.RequestContextHolder;

public class RequestContextCleanupExtension implements AfterEachCallback {

    @Override
    public void afterEach(ExtensionContext context) {
        RequestContextHolder.resetRequestAttributes();
    }
}
```

Áp dụng:

```java
@ExtendWith(RequestContextCleanupExtension.class)
class SomeServiceTest {
}
```

Extension hữu ích khi test suite có nhiều nơi tự bind request context. Nó chỉ cleanup thread thực hiện callback của JUnit. Nếu test tạo worker thread và bind request context ở worker đó, worker phải tự cleanup trên chính thread của nó.

## 7. Spring MVC và MockMvc tự quản lý request context

Khi test đi qua `MockMvc`, request được xử lý bởi `DispatcherServlet` và Spring quản lý request context trong vòng đời dispatch. Test thường không cần tự gọi `RequestContextHolder.setRequestAttributes(...)`.

Ví dụ:

```java
@WebMvcTest(CurrentRequestController.class)
class CurrentRequestControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void controllerReadsCurrentRequestHeader() throws Exception {
        mockMvc.perform(get("/current-request")
                        .header("X-Request-Id", "req-42"))
                .andExpect(status().isOk())
                .andExpect(content().string("req-42"));
    }
}
```

Controller có thể đọc request context:

```java
@RestController
class CurrentRequestController {

    @GetMapping("/current-request")
    String currentRequestId() {
        ServletRequestAttributes attributes =
                (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
        return attributes.getRequest().getHeader("X-Request-Id");
    }
}
```

`MockMvc.perform(...)` chạy request qua Servlet MVC test infrastructure. Spring bind request attributes trong quá trình xử lý và dọn chúng sau dispatch. Tự bind một request giả khác trước khi gọi MockMvc có thể làm test phức tạp hoặc che khuất hành vi thật của framework.

Nếu test cần xác nhận không còn request context sau khi request hoàn tất, có thể kiểm tra sau `perform(...)` trên cùng thread:

```java
mockMvc.perform(get("/current-request"))
        .andExpect(status().isOk());

assertThat(RequestContextHolder.getRequestAttributes()).isNull();
```

Kiểm tra này phù hợp với request dispatch đồng bộ trong test. Với async MVC, cần hiểu lifecycle và thread thực thi riêng, như phần dưới.

## 8. RequestContextFilter và RequestContextListener

Trong ứng dụng Servlet, request context có thể được bind bởi một trong các cơ chế Spring sau:

- `DispatcherServlet` bind request attributes trong quá trình dispatch MVC.
- `RequestContextFilter` là Servlet filter bind context trước chuỗi xử lý và reset sau khi chuỗi hoàn tất.
- `RequestContextListener` bind context theo lifecycle của Servlet request.

`RequestContextFilter` thường hữu ích khi code cần request context chạy ngoài `DispatcherServlet`, ví dụ một Servlet khác hoặc filter downstream. Filter cần được đăng ký trong Servlet container hoặc test context để hoạt động.

Spring quản lý bind/reset trong các cơ chế này. Không nên tự gọi `resetRequestAttributes()` giữa lúc request đang được xử lý, vì có thể làm code downstream mất request context hợp lệ. Việc cleanup thủ công chỉ nên thực hiện ở ranh giới mà test hoặc component sở hữu binding.

Nếu ứng dụng dùng nhiều cơ chế bind, tránh cấu hình trùng lặp không cần thiết. Cần xác định cơ chế nào sở hữu request lifecycle và bảo đảm nó luôn reset trạng thái trong `finally`, kể cả khi filter chain hoặc controller ném exception.

## 9. Thread pool và `InheritableThreadLocal`

`RequestContextHolder` mặc định dùng ThreadLocal thường. API overload với `inheritable = true` dùng `InheritableThreadLocal`, nghĩa là thread con được tạo trong khi context đang bind có thể kế thừa tham chiếu attributes từ thread cha.

Ví dụ:

```java
RequestContextHolder.setRequestAttributes(attributes, true);

try {
    // Tạo thread con trong scope này.
} finally {
    RequestContextHolder.resetRequestAttributes();
}
```

Điểm dễ nhầm là `InheritableThreadLocal` truyền giá trị khi thread con được tạo, không phải mỗi lần một tác vụ được submit vào thread pool. Thread pool thường tạo worker từ trước rồi tái sử dụng chúng. Vì thế:

- Worker được tạo trước khi request bind có thể không nhận context.
- Worker được tạo trong request có thể giữ tham chiếu request sau khi request cha reset.
- Một worker được tái sử dụng có thể giữ trạng thái từ request cũ nếu task không cleanup.

Không bật inheritable request context một cách tùy tiện với thread pool dùng chung. Request attributes có thể chứa request/response và session không còn hợp lệ sau khi request kết thúc. Việc một thread con giữ tham chiếu đó lâu hơn lifecycle request có thể dẫn đến lỗi hoặc truy cập trạng thái đã hết hạn.

### Cleanup phải chạy trên thread đã bind

Giả sử worker thread bind context trong lúc xử lý task:

```java
executor.submit(() -> {
    RequestContextHolder.setRequestAttributes(attributes);
    try {
        service.process();
    } finally {
        RequestContextHolder.resetRequestAttributes();
    }
});
```

Cleanup ở `finally` phải nằm trong task để chạy trên worker thread. Nếu thread gọi `executor.submit(...)` reset holder sau khi submit, thao tác đó chỉ xóa ThreadLocal của thread gọi, không xóa ThreadLocal của worker.

Nếu executor dùng `TaskDecorator` để truyền context, decorator cần snapshot dữ liệu được phép truyền, bind trong lúc chạy task và khôi phục/xóa trong `finally`. Không nên truyền nguyên `ServletRequestAttributes` qua ranh giới bất đồng bộ dài hạn nếu task có thể chạy sau khi request kết thúc.

## 10. Async request không đồng nghĩa request context được truyền tự động

`RequestContextHolder` gắn với thread. Khi một request chuyển sang async processing, công việc có thể tiếp tục trên thread khác. Không nên giả định `RequestContextHolder.currentRequestAttributes()` luôn có cùng giá trị trong mọi thread xử lý.

Trong Spring MVC, `Callable`, `DeferredResult` và `WebAsyncTask` có lifecycle async riêng. Spring quản lý request/dispatch context ở các điểm phù hợp của Servlet MVC, nhưng một executor tùy chỉnh hoặc tác vụ nền được submit thủ công không tự động có cùng request context.

Nếu tác vụ nền cần thông tin như tenant, user id hoặc correlation id, cách bền vững hơn thường là trích xuất giá trị cần thiết tại ranh giới request rồi truyền thành tham số hoặc immutable context object:

```java
record JobContext(String tenantId, String requestId) {
}

@PostMapping("/jobs")
ResponseEntity<Void> startJob(HttpServletRequest request) {
    JobContext context = new JobContext(
            request.getHeader("X-Tenant"),
            request.getHeader("X-Request-Id"));

    jobService.submit(context);
    return ResponseEntity.accepted().build();
}
```

Worker dùng dữ liệu tường minh thay vì đọc request thread-local sau khi request đã kết thúc. Cách này cũng làm rõ dữ liệu nào được phép tồn tại lâu hơn request.

## 11. Phân biệt RequestContextHolder với các ThreadLocal khác

Spring có nhiều holder dùng trạng thái theo thread. Reset một holder không tự reset các holder khác.

| Holder | Trạng thái thường lưu | Cleanup tương ứng |
|---|---|---|
| `RequestContextHolder` | `RequestAttributes` của request hiện tại | `RequestContextHolder.resetRequestAttributes()` |
| `SecurityContextHolder` | `SecurityContext` và authentication | `SecurityContextHolder.clearContext()` |
| `LocaleContextHolder` | Locale và time zone hiện tại | `LocaleContextHolder.resetLocaleContext()` |
| `TransactionSynchronizationManager` | Transaction resources và synchronization metadata | Được transaction manager quản lý; không tự reset tùy tiện trong test. |
| MDC của logging framework | Correlation/request metadata | Dùng API clear/remove của logging framework tương ứng. |

Nếu test tự bind nhiều loại context, phải cleanup từng loại theo đúng lifecycle. Không nên gọi API nội bộ để xóa transaction resources khi transaction manager vẫn đang quản lý transaction; hãy để transaction framework hoàn tất rollback/commit và cleanup.

`RequestContextHolder.resetRequestAttributes()` chỉ xóa request attributes. Nó không xóa SecurityContext, MDC, locale hoặc transaction state.

## 12. Kiểm tra rằng context đã được dọn

Sau khi cleanup, `getRequestAttributes()` nên trả về `null` nếu thread không có request context khác. `currentRequestAttributes()` nên ném `IllegalStateException`.

```java
@Test
void resetRemovesCurrentRequestAttributes() {
    MockHttpServletRequest request = new MockHttpServletRequest();
    ServletRequestAttributes attributes = new ServletRequestAttributes(request);

    RequestContextHolder.setRequestAttributes(attributes);
    assertThat(RequestContextHolder.getRequestAttributes()).isSameAs(attributes);

    try {
        // Thực hiện phần kiểm thử cần request context.
    } finally {
        RequestContextHolder.resetRequestAttributes();
        attributes.requestCompleted();
    }

    assertThat(RequestContextHolder.getRequestAttributes()).isNull();
    assertThatThrownBy(RequestContextHolder::currentRequestAttributes)
            .isInstanceOf(IllegalStateException.class);
}
```

Assertion sau cleanup là một phần hữu ích của test helper: nó xác nhận trạng thái đã được gỡ. Nếu test class dùng `@AfterEach`, có thể viết một test riêng cho helper hoặc extension để xác nhận policy cleanup hoạt động.

Không nên kiểm tra `RequestContextHolder` từ thread khác rồi kết luận thread đã bind được cleanup. Thread khác có ThreadLocal riêng; hãy kiểm tra trên đúng thread sở hữu binding.

## 13. Những lỗi thường gặp

### Bind context mà không dùng `finally`

Nếu assertion hoặc code test ném exception trước dòng reset, thread vẫn giữ request attributes. Đặt reset trong `finally` hoặc dùng `try-with-resources`.

### Chỉ reset trong `@BeforeEach`

Reset trước test giúp thread bắt đầu sạch nhưng không bảo đảm test hiện tại dọn trạng thái khi kết thúc. Dùng cleanup sau test hoặc tại scope tạo binding.

### Reset ở thread gọi thay vì thread worker

ThreadLocal thuộc thread hiện tại. Cleanup từ test thread không xóa binding đã được tạo trong executor worker. Đặt `finally` bên trong task.

### Dùng inheritable context với thread pool

Thread pool tái sử dụng worker và không tạo thread con mới cho mỗi task. Inheritance có thể không hoạt động như mong đợi hoặc giữ tham chiếu request cũ. Tránh bật inheritable cho executor dùng chung; truyền dữ liệu tường minh hoặc dùng cơ chế context propagation được kiểm soát.

### Tự bind trong MockMvc test không cần thiết

MockMvc đã chạy qua Spring MVC infrastructure. Bind thêm attributes thủ công có thể làm test đọc nhầm context do test tự tạo. Chỉ bind thủ công khi test gọi component trực tiếp ngoài request dispatch.

### Cho rằng reset RequestContextHolder sẽ reset mọi context

Security, locale, transaction và MDC có lifecycle riêng. Cleanup đúng holder tương ứng.

### Dùng request attributes sau khi request đã hoàn tất

Giữ `ServletRequestAttributes` trong tác vụ nền có thể làm code truy cập request/session sau khi container đã hoàn tất request. Trích xuất giá trị cần thiết thành object bất biến trước khi submit task.

## 14. Chiến lược cleanup theo loại test

| Loại test | Cách quản lý phù hợp |
|---|---|
| Unit test service đọc request context trực tiếp | Tạo `MockHttpServletRequest`, bind `ServletRequestAttributes`, cleanup trong `finally`. |
| Nhiều test method tự bind context | Dùng helper `AutoCloseable` hoặc `@AfterEach`/JUnit extension. |
| Spring MVC `MockMvc` test | Để `DispatcherServlet` và Spring Test quản lý request binding; kiểm tra cleanup sau dispatch nếu cần. |
| Test code chạy trên executor | Bind và reset trong cùng worker task; tránh giữ request attributes sau khi task kết thúc. |
| Async job sống lâu hơn request | Trích xuất tenant/user/correlation thành dữ liệu tường minh; không giữ `ServletRequestAttributes`. |
| Test nested request scope | Lưu và khôi phục context trước đó có chủ đích, đồng thời xét đến chế độ inheritable. |

## 15. Checklist cho RequestContextHolder trong test

- [ ] Xác định test có thực sự cần bind `RequestAttributes` thủ công hay Spring MVC đã quản lý request context.
- [ ] Nếu tự bind, dùng `try/finally` hoặc `AutoCloseable` để cleanup.
- [ ] Gọi `RequestContextHolder.resetRequestAttributes()` trên đúng thread đã bind.
- [ ] Gọi `ServletRequestAttributes.requestCompleted()` khi test sở hữu lifecycle attributes và cần hoàn tất request scope callbacks.
- [ ] Có assertion xác nhận `getRequestAttributes()` trả `null` sau cleanup nếu không có context bên ngoài.
- [ ] Dùng `@AfterEach` hoặc JUnit extension cho cleanup chung; không chỉ reset ở `@BeforeEach`.
- [ ] Không dùng `InheritableThreadLocal` tùy tiện với thread pool.
- [ ] Nếu task chạy trên worker, cleanup trong chính worker task.
- [ ] Không giữ request/session object trong tác vụ nền vượt quá request lifecycle.
- [ ] Cleanup riêng `SecurityContextHolder`, `LocaleContextHolder` hoặc MDC nếu test đã bind chúng.
- [ ] Không tự xóa transaction state do transaction manager sở hữu.

`RequestContextHolder` chỉ an toàn khi binding có ranh giới rõ ràng và được reset trên đúng thread. Spring tự quản lý request context trong Servlet dispatch thông thường; test tự bind phải cleanup trong `finally` hoặc lifecycle callback. Đặc biệt với executor và async processing, không truyền nguyên request attributes qua thời gian sống của request. Chỉ giữ dữ liệu cần thiết, truyền nó một cách tường minh và dọn mọi thread-local trước khi thread được tái sử dụng.
