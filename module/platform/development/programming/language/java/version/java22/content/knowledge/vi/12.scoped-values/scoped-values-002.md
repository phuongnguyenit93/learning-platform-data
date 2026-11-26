# Truyền ngữ cảnh bất biến theo phạm vi động và đối chiếu với ThreadLocal

Trong một request, nhiều tầng xử lý có thể cần cùng một thông tin như request ID, người dùng hiện tại, tenant hoặc locale. Nếu truyền các giá trị này qua mọi lời gọi method, chữ ký của nhiều method sẽ phải mang thêm tham số chỉ để chuyển tiếp ngữ cảnh. `ThreadLocal` từng là cách phổ biến để tránh việc đó, nhưng giá trị có thể tồn tại lâu hơn request và phải được dọn thủ công.

`ScopedValue` cung cấp một cách truyền dữ liệu ngữ cảnh theo **phạm vi thực thi động**. Caller gắn một giá trị vào key trong lúc chạy một khối công việc; các method được gọi trực tiếp hoặc gián tiếp trong khối đó có thể đọc giá trị. Khi khối kết thúc, binding tự động được khôi phục hoặc trở về trạng thái chưa được gắn.

Scoped Values được chuẩn hóa trong Java 25 theo JEP 506. Trên JDK 25 LTS và JDK 27, `ScopedValue` là API final, không cần bật preview. Trong Java 22, tính năng này vẫn ở trạng thái preview; các API preview cũ chỉ có ý nghĩa lịch sử và không được dùng trong ví dụ hiện hành của bài này.

## 1. ScopedValue giải quyết vấn đề gì?

Giả sử một request đi qua controller, service và repository. Cả ba tầng cần request ID để ghi log:

```text
HTTP request
    |
    v
Controller
    |
    v
OrderService
    |
    v
OrderRepository
```

Nếu truyền request ID bằng tham số, mỗi method trung gian phải nhận rồi chuyển tiếp giá trị đó, dù có thể không trực tiếp sử dụng nó:

```java
controller.handle(requestId);
service.createOrder(requestId);
repository.insertOrder(requestId);
```

Với `ScopedValue`, caller gắn ngữ cảnh một lần. Các method nằm trong phạm vi gọi có thể đọc key khi cần:

```java
ScopedValue.where(REQUEST_ID, "req-42").run(() -> {
    controller.handle();
});
```

`controller`, `service` và `repository` không cần khai báo tham số `requestId` chỉ để chuyển tiếp. Chúng truy cập cùng một key `REQUEST_ID` trong thời gian xử lý request.

## 2. Khai báo và sử dụng ScopedValue

Tạo một key bằng `ScopedValue.newInstance()`. Thông thường, key được khai báo trong field `private static final` để giới hạn những thành phần có thể truy cập dữ liệu:

```java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();
```

Gắn giá trị trong một phạm vi bằng `ScopedValue.where(key, value).run(...)`:

```java
ScopedValue.where(REQUEST_ID, "req-42").run(() -> {
    System.out.println(REQUEST_ID.get());
});
```

Khi `run` kết thúc, binding `req-42` tự động hết hiệu lực. Nếu gọi `REQUEST_ID.get()` khi key chưa được gắn trong thread hiện tại, phương thức ném `NoSuchElementException`.

Các phương thức thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `ScopedValue.newInstance()` | Tạo key ban đầu chưa được gắn giá trị |
| `ScopedValue.where(key, value)` | Tạo `Carrier` chứa một binding để chạy trong phạm vi |
| `Carrier.run(Runnable)` | Chạy tác vụ không trả về kết quả với các binding đã cấu hình |
| `Carrier.call(CallableOp)` | Chạy tác vụ trả về kết quả với các binding đã cấu hình |
| `get()` | Lấy giá trị đang gắn trong thread hiện tại; ném `NoSuchElementException` nếu chưa gắn |
| `isBound()` | Kiểm tra key có đang được gắn trong thread hiện tại không |
| `orElse(other)` | Lấy giá trị nếu đã gắn, nếu không thì trả về giá trị mặc định |
| `orElseThrow(supplier)` | Lấy giá trị hoặc ném exception do supplier tạo ra |

### 2.1. Ví dụ hoàn chỉnh với request context

Một record bất biến có thể gom nhiều giá trị ngữ cảnh vào cùng một key:

```java
public class ScopedValueRequestExample {
    private static final ScopedValue<RequestContext> CONTEXT =
            ScopedValue.newInstance();

    record RequestContext(String requestId, String userId, String tenantId) {}

    public static void main(String[] args) {
        var context = new RequestContext("req-42", "user-7", "tenant-a");

        ScopedValue.where(CONTEXT, context).run(
                ScopedValueRequestExample::handleRequest
        );
    }

    private static void handleRequest() {
        validateUser();
        createOrder();
    }

    private static void validateUser() {
        RequestContext context = CONTEXT.get();
        System.out.println("Validate user " + context.userId());
    }

    private static void createOrder() {
        RequestContext context = CONTEXT.get();
        System.out.printf("Create order for %s, request=%s, tenant=%s%n",
                context.userId(), context.requestId(), context.tenantId());
    }
}
```

Kết quả:

```text
Validate user user-7
Create order for user-7, request=req-42, tenant=tenant-a
```

`CONTEXT` chỉ được gắn ở đầu request. Các method phía dưới có thể đọc cùng `RequestContext` mà không phải nhận và chuyển tiếp nó qua từng tham số.

## 3. Phạm vi động và tự động khôi phục binding

Binding tồn tại trong thời gian thực thi của `run` hoặc `call`, bao gồm các method được gọi trực tiếp và gián tiếp từ operation đó. Khi operation hoàn tất bình thường hoặc ném exception, binding được khôi phục về trạng thái trước đó.

```java
private static final ScopedValue<String> USER = ScopedValue.newInstance();

static void process() {
    ScopedValue.where(USER, "alice").run(() -> {
        System.out.println(USER.get()); // alice
        service();
    });

    System.out.println(USER.isBound()); // false nếu trước đó chưa có binding
}

static void service() {
    repository();
}

static void repository() {
    System.out.println("Repository user=" + USER.get()); // alice
}
```

Không cần gọi `remove()` trong `finally`. Cơ chế phạm vi của API khôi phục binding khi operation kết thúc, kể cả khi exception lan ra ngoài.

### 3.1. Binding lồng nhau (rebinding)

Một key có thể được gắn lại trong một phạm vi con. Khi phạm vi con kết thúc, giá trị trước đó được khôi phục:

```java
private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

static void nestedScopes() {
    ScopedValue.where(REQUEST_ID, "outer-request").run(() -> {
        System.out.println(REQUEST_ID.get()); // outer-request

        ScopedValue.where(REQUEST_ID, "inner-request").run(() -> {
            System.out.println(REQUEST_ID.get()); // inner-request
        });

        System.out.println(REQUEST_ID.get()); // outer-request
    });
}
```

Điều này hữu ích khi xử lý một tác vụ con có ngữ cảnh riêng, chẳng hạn gọi một dịch vụ nội bộ với correlation ID phụ. Sau khi tác vụ con hoàn tất, request ID của phạm vi cha tiếp tục có hiệu lực.

### 3.2. Chạy operation có giá trị trả về bằng call

Nếu operation cần trả kết quả, dùng `call`:

```java
public class ScopedValueCallExample {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    private static String buildResponse() {
        return "Completed request " + REQUEST_ID.get();
    }

    public static String executeRequest() {
        return ScopedValue.where(REQUEST_ID, "req-42")
                .call(ScopedValueCallExample::buildResponse);
    }

    public static void main(String[] args) {
        System.out.println(executeRequest());
    }
}
```

`call` trả về kết quả của operation. Nếu operation ném exception, exception được truyền ra caller và binding vẫn được khôi phục.

## 4. Đọc giá trị khi chưa biết binding có tồn tại

`get()` phù hợp khi chương trình yêu cầu ngữ cảnh phải có mặt. Nếu việc không có binding là tình huống hợp lệ, dùng `isBound`, `orElse` hoặc `orElseThrow`:

```java
if (REQUEST_ID.isBound()) {
    System.out.println("Request: " + REQUEST_ID.get());
}

String requestId = REQUEST_ID.orElse("no-request");

String requiredRequestId = REQUEST_ID.orElseThrow(
        () -> new IllegalStateException("Request context is missing")
);
```

Không nên dùng `orElse` để che giấu một lỗi thiết kế nếu mọi đường xử lý đều bắt buộc phải nằm trong request scope. Khi thiếu binding là lỗi, `get()` hoặc `orElseThrow()` giúp phát hiện sớm vấn đề.

## 5. Gắn nhiều ScopedValue bằng Carrier

Nếu cần truyền một vài giá trị riêng biệt, có thể nối nhiều lệnh `where` để tạo một `Carrier`:

```java
private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();
private static final ScopedValue<String> USER_ID = ScopedValue.newInstance();

static void handle() {
    ScopedValue.where(REQUEST_ID, "req-42")
            .where(USER_ID, "user-7")
            .run(() -> {
                System.out.println(REQUEST_ID.get());
                System.out.println(USER_ID.get());
            });
}
```

`Carrier` là đối tượng bất biến và thread-safe. Mỗi lần gọi `where` trả về một carrier mới; carrier trước đó không bị thay đổi.

Tài liệu API khuyến nghị chỉ dùng một số lượng nhỏ `ScopedValue` đang hoạt động. Nếu cần truyền nhiều trường liên quan, nên gom chúng vào một record như `RequestContext` ở phần trước rồi gắn record bằng một key. Cách này cũng giúp ngữ cảnh có cấu trúc và dễ kiểm tra hơn.

## 6. So sánh ScopedValue với ThreadLocal

`ThreadLocal` lưu một giá trị riêng cho mỗi thread. Mã trong thread đó có thể đọc, thay đổi hoặc xóa giá trị bằng `get()`, `set()` và `remove()`. Đây là mô hình hữu ích cho trạng thái mutable gắn với thread, nhưng có một số điểm cần quản lý khi dùng để truyền request context.

| Tiêu chí | `ScopedValue` | `ThreadLocal` |
| --- | --- | --- |
| Mục đích phù hợp | Truyền dữ liệu ngữ cảnh một chiều trong phạm vi động | Lưu trạng thái riêng của từng thread |
| Cách gắn giá trị | `where(key, value).run/call(...)` | `set(value)` |
| Thay đổi binding bên trong phạm vi | Không có thao tác `set`; có thể rebinding trong scope lồng nhau | Có thể gọi `set` bất cứ lúc nào |
| Vòng đời | Tự kết thúc hoặc khôi phục khi scope kết thúc | Có thể tồn tại đến hết đời thread hoặc đến khi gọi `remove()` |
| Cleanup | Được quản lý theo phạm vi | Lập trình viên cần gọi `remove()` đúng lúc nếu giá trị không còn cần thiết |
| Đọc trong call chain | Các method có quyền truy cập key có thể gọi `get()` | Các method có quyền truy cập biến ThreadLocal có thể gọi `get()` |
| Chia sẻ sang tác vụ con | Được kế thừa trong `StructuredTaskScope` | `ThreadLocal` thông thường không tự truyền sang thread khác; `InheritableThreadLocal` có cơ chế riêng |
| Trạng thái object được lưu | Binding không thể bị thay thế trong scope, nhưng object bên trong vẫn có thể mutable | Giá trị có thể bị thay thế hoặc sửa đổi qua `set()` và thao tác trên object |

### 6.1. Ví dụ ThreadLocal cần cleanup

Với `ThreadLocal`, request context thường được gắn và xóa bằng `try/finally`:

```java
public class ThreadLocalContextExample {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    static void handleRequest(String requestId) {
        try {
            REQUEST_ID.set(requestId);
            service();
        } finally {
            REQUEST_ID.remove();
        }
    }

    static void service() {
        System.out.println("Request=" + REQUEST_ID.get());
    }
}
```

Nếu dùng thread pool mà quên `remove()`, thread có thể được tái sử dụng cho request tiếp theo trong khi giá trị cũ vẫn còn. Điều đó có thể làm rò rỉ ngữ cảnh giữa các tác vụ hoặc giữ dữ liệu lâu hơn dự kiến.

Với `ScopedValue`, cùng tình huống được biểu diễn bằng phạm vi:

```java
public class ScopedValueContextExample {
    private static final ScopedValue<String> REQUEST_ID = ScopedValue.newInstance();

    static void handleRequest(String requestId) {
        ScopedValue.where(REQUEST_ID, requestId).run(
                ScopedValueContextExample::service);
    }

    static void service() {
        System.out.println("Request=" + REQUEST_ID.get());
    }
}
```

Khi `run` kết thúc, binding được khôi phục. Không cần thao tác dọn thủ công.

### 6.2. Khi nào vẫn nên dùng ThreadLocal?

Không phải mọi `ThreadLocal` đều cần thay bằng `ScopedValue`. `ThreadLocal` vẫn phù hợp khi:

- Một thư viện hoặc framework yêu cầu API `ThreadLocal`.
- Cần trạng thái mutable riêng cho từng thread, chẳng hạn một buffer tái sử dụng hoặc đối tượng làm việc không chia sẻ.
- Giá trị được thiết kế để tồn tại theo vòng đời thread thay vì theo một request hoặc một lời gọi động.
- Cần dùng các thao tác `set`/`remove` để quản lý trạng thái theo quy tắc riêng của thành phần.

Nếu dùng `ThreadLocal` trong thread pool, hãy xác định rõ ai chịu trách nhiệm gọi `remove()` và bảo đảm cleanup cả khi exception xảy ra.

## 7. ScopedValue và đa luồng

Binding của `ScopedValue` là per-thread. Khi một thread gọi `run` hoặc `call`, binding có hiệu lực trong thread đó. Không nên giả định một thread mới tạo bằng `new Thread(...)` hoặc một task gửi vào `ExecutorService` sẽ tự động nhận binding hiện tại.

### 7.1. Kế thừa binding trong StructuredTaskScope

`ScopedValue` hỗ trợ chia sẻ ngữ cảnh sang các subtask trong `StructuredTaskScope`. Khi scope được mở, nó chụp các binding hiện tại; những thread chạy subtask được tạo bằng `fork` sẽ kế thừa các binding đó. Scope chỉ đóng sau khi các subtask kết thúc, giúp binding không bị khôi phục trước khi tác vụ con còn đang sử dụng.

**Giới hạn phiên bản:** `ScopedValue` là API final từ Java 25, nhưng `StructuredTaskScope` vẫn là preview API trên JDK 27 (JEP 533). Do đó, khả năng kế thừa qua `StructuredTaskScope` cần bật preview khi biên dịch và chạy ứng dụng trên JDK 27. Không được hiểu rằng bản thân `ScopedValue` vẫn là preview.

Nếu dự án quyết định thử Structured Concurrency trên JDK 27, cần bật preview cho đúng release:

```bash
javac --enable-preview --release 27 -d out Main.java
java --enable-preview -cp out Main
```

Các lệnh trên minh họa yêu cầu bật preview của `StructuredTaskScope`; phần `ScopedValue` vẫn dùng API final. Vì StructuredTaskScope còn preview, chữ ký và hành vi của API này có thể thay đổi ở bản Java tiếp theo. Ứng dụng cần tương thích lâu dài có thể dùng ScopedValue trong phạm vi một thread mà chưa cần phụ thuộc vào StructuredTaskScope.

### 7.2. Giá trị được chia sẻ phải an toàn

Binding không thể bị thay thế trong phạm vi hiện tại, nhưng điều đó không làm object được gắn trở thành immutable. Ví dụ, nếu gắn một `ArrayList`, các method cùng truy cập vẫn có thể sửa danh sách đó.

Khi chia sẻ qua các subtask, hãy dùng object immutable như record chỉ chứa các giá trị immutable, hoặc đồng bộ mọi truy cập đến object mutable. Không dùng ScopedValue để chia sẻ một mutable context rồi giả định rằng API sẽ tự bảo vệ dữ liệu khỏi race condition.

## 8. Những lưu ý khi thiết kế ScopedValue

1. **Dùng key có phạm vi truy cập rõ ràng.** Thường khai báo key trong field `private static final`; chỉ cung cấp method đọc hoặc wrapper để mở scope khi cần.
2. **Gắn giá trị ở ranh giới tác vụ.** Ví dụ, bind context khi nhận request, chạy job hoặc xử lý một message.
3. **Ưu tiên object immutable.** Binding chỉ cố định ánh xạ key-value trong scope; nó không tự làm sâu object trở nên immutable.
4. **Không tạo quá nhiều key.** Gom các trường ngữ cảnh liên quan vào một record nếu cần truyền nhiều giá trị.
5. **Không giữ binding qua tác vụ bất đồng bộ tùy ý.** Executor hoặc thread thông thường không tự động kế thừa binding; hãy truyền context rõ ràng hoặc dùng structured scope đã được xác minh.
6. **Phân biệt API final và preview.** ScopedValue final từ Java 25; StructuredTaskScope vẫn preview trên JDK 27.
7. **Không dùng API từ các bản preview cũ.** Ví dụ hiện hành phải dùng `ScopedValue.where(...).run(...)` hoặc `.call(...)`, không dùng các tên method preview cũ đã bị loại bỏ trong quá trình hoàn thiện API.

## 9. Chọn ScopedValue hay ThreadLocal?

| Nhu cầu | Lựa chọn nên cân nhắc |
| --- | --- |
| Truyền request ID, user context hoặc tenant context qua call chain | `ScopedValue` |
| Truyền context bất biến vào các method được gọi gián tiếp | `ScopedValue` |
| Dùng context trong subtask của StructuredTaskScope | `ScopedValue`; lưu ý StructuredTaskScope là preview trên JDK 27 |
| Lưu buffer mutable riêng cho từng thread | `ThreadLocal` có thể phù hợp |
| Tích hợp với thư viện đã yêu cầu ThreadLocal | Tiếp tục dùng `ThreadLocal` theo hợp đồng của thư viện |
| Cần truyền dữ liệu sang executor task không có structured scope | Truyền context rõ ràng qua task hoặc dùng cơ chế context propagation phù hợp; không giả định ScopedValue tự kế thừa |

## 10. Trạng thái API theo phiên bản Java

| Phiên bản | Trạng thái Scoped Values | Ghi chú |
| --- | --- | --- |
| Java 21 | Preview | Giai đoạn thử nghiệm ban đầu |
| Java 22 | Preview lần thứ hai | JEP 464; không dùng API preview cũ làm ví dụ hiện hành |
| Java 23–24 | Tiếp tục preview | API được điều chỉnh trước khi hoàn thiện |
| Java 25 | Final theo JEP 506 | Không cần `--enable-preview` cho ScopedValue |
| Java 27 | Final | JDK 27 là feature release mới nhất tại ngày 25-11-2026; JDK 25 là LTS mới nhất |

`StructuredTaskScope` là một API khác với vòng đời riêng. Trên JDK 27, nó vẫn preview theo JEP 533. Sự kết hợp giữa hai API không làm thay đổi trạng thái final của `ScopedValue`.

## 11. Tài liệu tham khảo

- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506)
- [ScopedValue — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.html)
- [ScopedValue.Carrier — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ScopedValue.Carrier.html)
- [StructuredTaskScope — Java SE 27 API (Preview)](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html)
- [JEP 533 — Structured Concurrency (Seventh Preview)](https://openjdk.org/jeps/533)
- [ThreadLocal — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ThreadLocal.html)
- [JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25-relnote-issues.html)
