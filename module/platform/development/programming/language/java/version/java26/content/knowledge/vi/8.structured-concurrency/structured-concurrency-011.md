# Kế thừa ngữ cảnh ScopedValue và quan hệ với virtual thread

Một request thường mang theo ngữ cảnh cần dùng ở nhiều tầng xử lý: request ID để ghi log, tenant ID để chọn dữ liệu, hoặc thông tin tracing để nối các span. Truyền từng giá trị qua mọi tham số làm chữ ký phương thức phình to, còn lưu trạng thái trong một biến theo thread có thể khiến dữ liệu tồn tại lâu hơn phạm vi nghiệp vụ.

Java cung cấp `ScopedValue` để truyền ngữ cảnh theo một phạm vi thực thi có giới hạn. Khi kết hợp với `StructuredTaskScope`, binding hiện tại được chụp lúc mở scope và tự kế thừa sang các thread chạy subtask. `StructuredTaskScope` mặc định chạy mỗi subtask trên một virtual thread. Ba khái niệm có vai trò riêng: `ScopedValue` mang ngữ cảnh, virtual thread thực thi tác vụ, còn structured concurrency quản lý quan hệ và vòng đời giữa các tác vụ.

## 1. Trạng thái API theo JDK

| Thành phần | JDK bắt đầu ổn định | Trạng thái trên JDK 26 |
|---|---:|---|
| `ScopedValue<T>` | JDK 25, JEP 506 | API final, không cần preview |
| Virtual thread | JDK 21, JEP 444 | API final, không cần preview |
| `StructuredTaskScope` | JDK 28 theo JEP 543 | Preview lần thứ sáu theo JEP 525; cần bật preview |

Structured concurrency tiếp tục là preview lần thứ bảy trong JDK 27 theo JEP 533. JEP 543 đã tích hợp việc final hóa API vào nhánh JDK 28 mà không thay đổi API so với preview JDK 27. Tại ngày 27-11-2026, JDK 28 vẫn là Early Access và GA dự kiến tháng 03-2027. Vì vậy, nếu dự án đang chạy JDK 26, chỉ phần `StructuredTaskScope` cần cờ preview; `ScopedValue` và virtual thread đã là API ổn định.

## 2. ScopedValue truyền ngữ cảnh trong một phạm vi

`ScopedValue<T>` là một key để truy cập giá trị được bind trong một khoảng thực thi. Khai báo key thường là `private static final` để giới hạn code có khả năng đọc ngữ cảnh:

```java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();
```

Bind giá trị bằng `ScopedValue.where(...)`, sau đó gọi `run()` nếu không cần kết quả hoặc `call()` nếu cần trả về một giá trị:

```java
static void handle(String requestId) {
    ScopedValue.where(REQUEST_ID, requestId).run(() -> processRequest());
}

static void processRequest() {
    System.out.println("Handling request " + REQUEST_ID.get());
}
```

Trong thời gian `run()` thực thi, code gọi trực tiếp hoặc gián tiếp có quyền truy cập key `REQUEST_ID` đều có thể đọc giá trị bằng `get()`. Khi `run()` kết thúc bình thường hoặc bằng exception, binding được khôi phục về trạng thái trước đó. Binding là theo từng thread; hai thread có thể bind cùng key với hai giá trị khác nhau mà không ghi đè lẫn nhau.

Nếu một đoạn code có thể được gọi khi key chưa bind, dùng `isBound()`, `orElse(...)` hoặc `orElseThrow(...)` để xác định hành vi. Gọi `get()` khi chưa có binding sẽ ném `NoSuchElementException`.

### 2.1. Rebinding trong phạm vi lồng nhau

Một phương thức có thể tạo binding mới cho cùng key trong phạm vi con. Khi phạm vi con kết thúc, giá trị cũ tự được khôi phục:

```java
private static final ScopedValue<String> TENANT = ScopedValue.newInstance();

static void handleTenant(String tenantId) {
    ScopedValue.where(TENANT, tenantId).run(() -> {
        audit(TENANT.get()); // tenant ban đầu

        ScopedValue.where(TENANT, "system").run(() -> {
            audit(TENANT.get()); // system trong phạm vi con
        });

        audit(TENANT.get()); // trở lại tenant ban đầu
    });
}
```

Rebinding hữu ích khi một tác vụ con cần ngữ cảnh chuyên biệt trong một đoạn xử lý giới hạn. Không cần tự lưu và phục hồi giá trị cũ bằng biến mutable hoặc `finally`.

### 2.2. Giá trị ngữ cảnh nên bất biến

`ScopedValue` kiểm soát vòng đời của binding; nó không tự làm object được bind trở thành immutable. Nếu bind một object có trạng thái mutable, mọi thread cùng nhận object đó vẫn có thể quan sát thay đổi của nhau. Hãy ưu tiên record chứa dữ liệu bất biến:

```java
record RequestContext(String requestId, String tenantId, String traceId) {}

private static final ScopedValue<RequestContext> CONTEXT =
        ScopedValue.newInstance();
```

Một record như trên phù hợp để mang nhiều trường ngữ cảnh trong một binding. Nếu thành phần bên trong record mutable, cần đồng bộ mọi truy cập hoặc thay bằng kiểu bất biến.

## 3. Virtual thread là đơn vị thực thi mặc định của subtask

Virtual thread là thread do JVM quản lý và lập lịch trên các platform thread. Từ JDK 21, có thể tạo virtual thread trực tiếp bằng API `Thread` hoặc `Executors`, nhưng khi dùng `StructuredTaskScope.open()` mặc định, ứng dụng không cần tự tạo executor: mỗi lần `fork()` tạo một virtual thread cho subtask.

```java
try (var scope = StructuredTaskScope.open()) {
    var profile = scope.fork(() -> loadProfile());
    var orders = scope.fork(() -> loadOrders());

    scope.join();
    return new Dashboard(profile.get(), orders.get());
}
```

Hai subtask chạy đồng thời. Owner thread chờ tại `join()`, đọc kết quả sau khi join thành công, rồi đóng scope. Virtual thread giúp cách viết blocking I/O dễ đọc và có thể mở rộng tới nhiều tác vụ chờ I/O; nó không làm phép tính CPU-bound chạy nhanh hơn và không làm database, connection pool hoặc dịch vụ bên ngoài có năng lực vô hạn.

`StructuredTaskScope` cũng cho phép cấu hình `ThreadFactory`. Nếu không đặt factory riêng, scope tạo virtual thread không tên cho mỗi subtask. Khi cấu hình factory khác, loại thread thực thi có thể thay đổi, nhưng quan hệ vòng đời của scope vẫn được giữ.

## 4. StructuredTaskScope chụp và kế thừa ScopedValue bindings

Điểm kết nối giữa ba cơ chế nằm ở thời điểm mở scope:

1. Owner thread bind `ScopedValue` với request context.
2. Owner gọi `StructuredTaskScope.open()` trong binding đó.
3. Scope chụp các binding đang có trên owner thread.
4. Khi `fork()`, thread chạy subtask kế thừa các binding đã chụp.
5. `close()` đợi các thread subtask kết thúc trước khi owner rời phạm vi scope và binding bên ngoài được khôi phục.

Vì vậy, code trong nhiều tầng gọi ở các subtask có thể đọc cùng request ID hoặc tenant context mà không phải truyền thêm tham số:

```java
import java.lang.ScopedValue;
import java.util.concurrent.StructuredTaskScope;

record RequestContext(String requestId, String tenantId) {}
record UserProfile(String displayName) {}
record Permissions(boolean canExport) {}
record Page(UserProfile profile, Permissions permissions) {}

private static final ScopedValue<RequestContext> CONTEXT =
        ScopedValue.newInstance();

static Page loadPage(RequestContext context) throws Exception {
    return ScopedValue.where(CONTEXT, context).call(() -> {
        try (var scope = StructuredTaskScope.open()) {
            var profile = scope.fork(() -> profileService.load(
                    CONTEXT.get().tenantId()));
            var permissions = scope.fork(() -> permissionService.load(
                    CONTEXT.get().tenantId()));

            scope.join();
            return new Page(profile.get(), permissions.get());
        }
    });
}
```

Đây là mẫu JDK 26: `ScopedValue` là API final, còn `StructuredTaskScope` là preview. Hai subtask đều đọc cùng binding `CONTEXT`; `profileService` và `permissionService` không cần nhận thêm `requestId` nếu chúng chỉ cần tenant context. Trong hệ thống thực tế, có thể bind cả request ID và trace ID trong cùng record để giảm số key cần quản lý.

### 4.1. Vì sao phải bind trước khi mở scope?

Scope chụp binding tại thời điểm được tạo. Khi fork, JDK kiểm tra các binding hiện tại có khớp với binding đã chụp không. Điều này ngăn một subtask kế thừa binding khác với phạm vi mà scope dự định quản lý.

Mẫu đúng:

```java
ScopedValue.where(CONTEXT, context).run(() -> {
    try (var scope = StructuredTaskScope.open()) {
        scope.fork(() -> readTenant(CONTEXT.get().tenantId()));
        scope.join();
    }
});
```

Mẫu sai về cấu trúc:

```java
try (var scope = StructuredTaskScope.open()) {
    ScopedValue.where(CONTEXT, context).run(() ->
            scope.fork(() -> readTenant(CONTEXT.get().tenantId())));
    scope.join();
}
```

Trong mẫu sai, scope được mở khi `CONTEXT` chưa bind, nhưng `fork()` xảy ra bên trong binding mới. JDK có thể ném `StructureViolationException` vì binding lúc fork không khớp snapshot lúc mở scope. Hãy chuyển binding ra ngoài và mở scope bên trong binding.

## 5. Kế thừa theo cây scope và thay đổi ngữ cảnh ở nhánh con

Một subtask có thể mở scope mới. Scope mới chụp binding đang có trên thread của subtask; các subtask cấp tiếp theo kế thừa binding đó. Như vậy, ngữ cảnh được truyền theo cây tác vụ, không chỉ ở một cấp.

```java
static void handleRequest(RequestContext context) throws Exception {
    ScopedValue.where(CONTEXT, context).run(() -> {
        try (var requestScope = StructuredTaskScope.open()) {
            requestScope.fork(() -> {
                // Nhánh này kế thừa context của request.
                return loadCustomerPage(CONTEXT.get().tenantId());
            });

            requestScope.fork(() -> {
                // Có thể tạo binding lồng nhau cho một tác vụ hệ thống.
                return ScopedValue.where(CONTEXT,
                        new RequestContext(CONTEXT.get().requestId(), "system"))
                        .call(() -> {
                            try (var auditScope = StructuredTaskScope.open()) {
                                auditScope.fork(() -> writeAudit(CONTEXT.get()));
                                auditScope.join();
                                return null;
                            }
                        });
            });

            requestScope.join();
        }
    });
}
```

Ví dụ cho thấy scope cấp hai kế thừa binding đang hiệu lực ở nhánh cha. Trong nhánh audit, `CONTEXT` được rebind thành tenant `system` trong một dynamic scope lồng nhau; `auditScope` mở bên trong binding mới nên subtask audit nhận binding mới. Khi phần audit kết thúc, binding của nhánh cha được khôi phục; nhánh khác vẫn giữ context ban đầu.

Trong ứng dụng thực tế, không nên dùng chuỗi tenant giả lập như `system` để bỏ qua kiểm tra quyền. Rebinding chỉ thay ngữ cảnh được truyền; nó không tự xác thực danh tính hay cấp quyền. Mọi thay đổi tenant/security context phải được kiểm tra theo chính sách truy cập của ứng dụng.

## 6. ScopedValue và ThreadLocal: chọn đúng cơ chế truyền dữ liệu

`ThreadLocal` vẫn là API Java hợp lệ và có trường hợp sử dụng riêng, nhưng với mục tiêu truyền một chiều dữ liệu ngữ cảnh qua chuỗi lời gọi, `ScopedValue` có các đặc điểm phù hợp hơn:

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
|---|---|---|
| Hướng truyền dữ liệu | Một chiều từ caller đến callee | Có thể đọc và thay đổi từ nhiều tầng |
| Vòng đời | Gắn với dynamic scope; tự khôi phục khi scope kết thúc | Có thể tồn tại sau khi phương thức kết thúc cho đến khi được remove hoặc thread kết thúc |
| Thay binding | Rebinding trong scope lồng nhau, sau đó tự khôi phục | Có thể set lại giá trị trên thread |
| Truyền sang subtask có cấu trúc | `StructuredTaskScope` chụp và kế thừa binding | Không có cùng hợp đồng kế thừa theo cây scope |
| Phù hợp | Request ID, tenant context, tracing, security context chỉ đọc | Trạng thái gắn riêng với thread hoặc trường hợp cần cập nhật theo thread |

Không cần thay mọi `ThreadLocal` trong ứng dụng bằng `ScopedValue`. Nếu một thư viện cần trạng thái mutable riêng cho từng thread, `ThreadLocal` vẫn có thể phù hợp. Nếu mục tiêu chỉ là truyền context bất biến theo request và sang các subtask, `ScopedValue` diễn đạt đúng vòng đời hơn.

## 7. Những lỗi cần tránh

- **Bind sau khi mở scope.** Scope đã chụp binding cũ; binding mới ở thời điểm fork có thể gây `StructureViolationException`.
- **Rời binding trước khi subtask kết thúc.** Dùng `try-with-resources` và `join()` bên trong binding để `close()` đợi mọi subtask kết thúc trước khi binding được khôi phục.
- **Chia sẻ object mutable mà không đồng bộ.** Các virtual thread kế thừa cùng tham chiếu; hãy dùng context immutable hoặc đồng bộ tất cả truy cập.
- **Gọi `get()` khi key chưa bind.** Kiểm tra `isBound()` hoặc dùng `orElse()`/`orElseThrow()` nếu context là tùy chọn.
- **Tạo quá nhiều ScopedValue keys.** Gom request ID, tenant ID và trace ID vào một record context khi chúng có cùng vòng đời.
- **Dùng context như bằng chứng xác thực.** Binding chỉ truyền dữ liệu; nó không tự chứng minh user/tenant được phép truy cập tài nguyên.
- **Cho rằng virtual thread không giới hạn tài nguyên.** Vẫn cần connection pool, semaphore, rate limit và timeout cho dịch vụ downstream.
- **Dùng scope cho công việc fire-and-forget.** Khi scope đóng, các subtask phải kết thúc; công việc nền cần cơ chế quản lý vòng đời riêng.

## 8. Khả năng quan sát và cấu hình virtual thread

Scope có thể được đặt tên qua `Configuration.withName()` để nhận diện nhóm tác vụ trong công cụ quan sát. Thread dump JSON của JDK có thể thể hiện quan hệ giữa virtual thread và scope cha, giúp điều tra nhánh nào đang chờ hoặc chưa dừng. Không đưa dữ liệu nhạy cảm như access token, email hoặc nội dung request vào tên scope.

Mặc định, mỗi `fork()` tạo một virtual thread. Có thể cấu hình `ThreadFactory` nếu có yêu cầu thực thi khác, nhưng cần giữ nguyên các quy tắc owner, join, close và kế thừa binding. Không dùng custom thread factory để biến structured scope thành executor dùng chung hoặc để tác vụ con thoát khỏi vòng đời scope.

## 9. Điều kiện sử dụng theo JDK 26, 27 và 28

| JDK | `ScopedValue` | `StructuredTaskScope` | Cách chạy |
|---|---|---|---|
| JDK 26 | Final từ JDK 25 | Preview lần 6, JEP 525 | Bật preview cho compile và runtime vì scope dùng API preview |
| JDK 27 | Final | Preview lần 7, JEP 533; API có `R_X` và `timeout()` | Bật preview cho compile và runtime; cập nhật mã theo API JDK 27 |
| JDK 28 build có JEP 543 | Final | API final | Bỏ `--enable-preview`; JDK 28 vẫn là EA trước GA |

Ví dụ lệnh JDK 26:

```bash
javac --release 26 --enable-preview ContextFanOut.java
java --enable-preview ContextFanOut
```

Khi nâng JDK 27, đổi xử lý exception của scope theo JEP 533 (`ExecutionException` hoặc exception `R_X` tùy Joiner) và dùng callback `timeout()` trong Joiner tùy chỉnh. Khi dùng JDK 28 build có JEP 543, API giữ nguyên thiết kế JDK 27 và không cần bật preview. Không chạy bytecode preview JDK 26 trên JDK khác; hãy biên dịch lại bằng JDK đích.

## Tài liệu tham khảo

- [JEP 506: Scoped Values (JDK 25)](https://openjdk.org/jeps/506)
- [JEP 444: Virtual Threads (JDK 21)](https://openjdk.org/jeps/444)
- [JEP 525: Structured Concurrency, Sixth Preview (JDK 26)](https://openjdk.org/jeps/525)
- [JEP 533: Structured Concurrency, Seventh Preview (JDK 27)](https://openjdk.org/jeps/533)
- [JEP 543: Structured Concurrency (JDK 28)](https://openjdk.org/jeps/543)
- [Java SE 26 API: ScopedValue](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ScopedValue.html)
- [Java SE 26 API: StructuredTaskScope](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [Java SE 26 Core Libraries Guide: Scoped Values](https://docs.oracle.com/en/java/javase/26/core/scoped-values.html)
