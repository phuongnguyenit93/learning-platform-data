# Lựa chọn ScopedValue, tham số tường minh hoặc ThreadLocal theo nhu cầu chia sẻ trạng thái

> **Chương:** ScopedValue  
> **Học phần:** `JAVA_VERSION_JAVA25` — các khả năng Java 25 còn phù hợp với phát triển Java hiện đại, gồm compact source files, module import, flexible constructor bodies, ScopedValue, KDF API, AOT cache và JFR.  
> **Mục tiêu:** Chọn đúng cơ chế truyền dữ liệu xuyên nhiều tầng gọi trong một luồng xử lý: tham số tường minh, `ScopedValue` hay `ThreadLocal`; hiểu vòng đời, khả năng lồng phạm vi, chia sẻ qua thread và các rủi ro khi dùng sai.

## 1. Bài toán: dữ liệu cần đi qua nhiều tầng gọi

Một request HTTP đi qua controller, application service, domain service, repository và logging. Một số dữ liệu được nhiều tầng sử dụng:

- `requestId` để nối log và trace.
- `tenantId` để giới hạn dữ liệu theo tenant.
- `userId` hoặc thông tin principal đã được xác thực.
- locale, correlation ID hoặc thông tin chính sách xử lý.

Có ba cách phổ biến để đưa dữ liệu đến nơi cần dùng:

1. **Tham số tường minh:** truyền dữ liệu qua danh sách tham số của từng method.
2. **`ScopedValue`:** bind một giá trị trong phạm vi thực thi; các method được gọi trực tiếp hoặc gián tiếp có thể đọc giá trị qua một key.
3. **`ThreadLocal`:** lưu một giá trị riêng cho thread hiện tại để các method chạy trên thread đó đọc được.

Không có cơ chế nào tốt nhất cho mọi trường hợp. Quyết định phụ thuộc vào **ý nghĩa của dữ liệu**, **ai được phép thay đổi**, **phạm vi sống**, **cách thực thi bất đồng bộ** và **khả năng quan sát khi debug**.

Ví dụ: `orderId` là dữ liệu nghiệp vụ đầu vào của `findOrder`, nên nên là tham số. `requestId` là metadata xuyên nhiều tầng, nhiều tầng không cần biết hoặc thay đổi nó, nên có thể phù hợp với `ScopedValue`. Một thư viện cũ chỉ đọc `ThreadLocal` có thể buộc ứng dụng tiếp tục duy trì cơ chế đó ở ranh giới tích hợp.

## 2. Ba cơ chế khác nhau ở đâu?

| Tiêu chí | Tham số tường minh | `ScopedValue` (Java 25 final) | `ThreadLocal` |
|---|---|---|---|
| Cách truy cập | Method nhận tham số trực tiếp | Method đọc key đang được bind trong dynamic scope | Method đọc biến gắn với thread hiện tại |
| Ai thấy dữ liệu? | Các method nhận tham số | Code có quyền truy cập key và chạy trong phạm vi bind | Code có quyền truy cập biến `ThreadLocal` trên cùng thread |
| Cách thay giá trị | Gọi method với giá trị khác | Tạo nested binding mới; binding ngoài được khôi phục khi nested scope kết thúc | `set()` ghi giá trị mới cho thread |
| Kết thúc vòng đời | Theo object/biến và luồng gọi | Tự động hết binding khi `run`/`call` kết thúc | Không tự hết khi method kết thúc; cần `remove()` hoặc quản lý riêng |
| Phù hợp với | Dữ liệu nghiệp vụ, dependency rõ ràng | Context chỉ đọc được truyền một chiều qua call chain | State thực sự gắn với thread, thư viện/framework cần ThreadLocal |
| Qua thread khác | Truyền như tham số khi tạo task | Mặc định binding là per-thread; có hỗ trợ thừa kế trong cấu trúc concurrency được chỉ định | Không tự chia sẻ; `InheritableThreadLocal` có quy tắc riêng |
| Rủi ro chính | Chữ ký dài, phải truyền qua nhiều tầng trung gian | Key bị lộ, value mutable, nhầm lẫn về async scope | Rò rỉ state khi tái sử dụng thread, quên dọn, khó theo dõi dependency ẩn |

Có thể ghi nhớ:

- **Tham số** mô tả dependency rõ nhất trong chữ ký.
- **ScopedValue** phù hợp với context cần truyền một chiều trong một phạm vi thực thi có ranh giới.
- **ThreadLocal** phù hợp khi state thực sự thuộc về thread hoặc cần tương thích với API vốn dùng ThreadLocal.

`ThreadLocal` vẫn là API Java hiện hành trong Java 25. ScopedValue không làm ThreadLocal trở thành API lỗi thời và cũng không phải lý do để chuyển mọi biến thread-local sang cơ chế mới.

## 3. `ScopedValue` là gì trong Java 25?

`ScopedValue` là API chuẩn trong `java.lang`, được hoàn tất qua **JEP 506 — Scoped Values** ở Java 25. Nó cho phép caller bind một giá trị vào key trong một phạm vi thực thi; các method được gọi trong phạm vi đó và có quyền truy cập key có thể đọc giá trị mà không phải nhận thêm tham số.

Ví dụ tối thiểu:

```java
import java.lang.ScopedValue;

public class ScopedValueDemo {
    private static final ScopedValue<String> REQUEST_ID =
            ScopedValue.newInstance();

    public static void main(String[] args) {
        ScopedValue.where(REQUEST_ID, "req-42")
                .run(ScopedValueDemo::handleRequest);
    }

    private static void handleRequest() {
        loadOrder();
    }

    private static void loadOrder() {
        System.out.println("requestId = " + REQUEST_ID.get());
    }
}
```

Kết quả:

```text
requestId = req-42
```

`handleRequest()` gọi `loadOrder()`. Hai method không nhận `requestId` qua tham số, nhưng `loadOrder()` vẫn đọc được vì nó chạy trong dynamic scope do `ScopedValue.where(...).run(...)` thiết lập.

`ScopedValue` có những đặc điểm cốt lõi:

- Key được tạo bằng `ScopedValue.newInstance()`.
- `where(key, value)` tạo một `ScopedValue.Carrier` chứa binding.
- `run(Runnable)` thực thi tác vụ không trả kết quả với binding đang hoạt động.
- `call(ScopedValue.CallableOp)` thực thi tác vụ có trả kết quả.
- `get()` đọc giá trị đang bind; nếu key chưa được bind trong thread hiện tại, `get()` ném `NoSuchElementException`.
- `isBound()`, `orElse(...)` và `orElseThrow(...)` cho phép xử lý trường hợp chưa có binding.
- Khi `run` hoặc `call` kết thúc bình thường hay bằng exception, binding tự trở về trạng thái trước đó (unbound hoặc giá trị outer scope).

Không có `set()` hoặc `remove()` trên `ScopedValue`. Caller thiết lập binding khi mở scope; code được gọi đọc giá trị trong scope đó.

### Java 25 không cần preview flag cho ScopedValue

`ScopedValue` là **API final** từ Java 25. Có thể dùng với JDK 25 mà không cần `--enable-preview`:

```bash
javac --release 25 ScopedValueDemo.java
java ScopedValueDemo
```

Các ví dụ ScopedValue ở Java 21–24 từng cần preview flag. Khi học Java 25, không tiếp tục sao chép hướng dẫn cũ yêu cầu bật preview cho chính API `ScopedValue`. Những API khác, ví dụ `StructuredTaskScope` trong Java 25, vẫn có trạng thái preview riêng; trạng thái của chúng không làm `ScopedValue` quay lại preview.

## 4. Phạm vi động và vòng đời binding

Một binding tồn tại trong **dynamic scope**: khoảng thời gian thực thi của operation được truyền vào `run` hoặc `call`, bao gồm các method được gọi trực tiếp/gián tiếp trong khoảng đó.

```java
private static final ScopedValue<String> TENANT =
        ScopedValue.newInstance();

static void processRequest() {
    System.out.println(TENANT.get());
}

static void main() {
    ScopedValue.where(TENANT, "tenant-a").run(() -> {
        processRequest(); // Đọc được tenant-a
    });

    // Binding đã hết ở đây.
    System.out.println(TENANT.isBound()); // false
}
```

Điểm quan trọng: binding không kéo dài theo object, request ID hoặc thread suốt đời. Nó chỉ tồn tại trong khoảng thực thi được bind.

### 4.1. Tự khôi phục khi có exception

```java
private static final ScopedValue<String> OPERATION =
        ScopedValue.newInstance();

static void execute() {
    try {
        ScopedValue.where(OPERATION, "create-order").run(() -> {
            throw new IllegalStateException("database unavailable");
        });
    } catch (IllegalStateException ex) {
        System.out.println(ex.getMessage());
    }

    System.out.println(OPERATION.isBound()); // false
}
```

Ngay cả khi operation ném exception, `run` vẫn khôi phục binding. Đây là ưu điểm quan trọng so với `ThreadLocal`: không cần nhớ gọi `remove()` ở mọi nhánh thoát chỉ để kết thúc một binding có phạm vi.

### 4.2. Nested binding và rebinding

Một scope bên trong có thể bind lại cùng key. Khi scope bên trong kết thúc, giá trị trước đó được khôi phục:

```java
private static final ScopedValue<String> USER =
        ScopedValue.newInstance();

static void main() {
    ScopedValue.where(USER, "alice").run(() -> {
        System.out.println(USER.get()); // alice

        ScopedValue.where(USER, "system").run(() -> {
            System.out.println(USER.get()); // system
        });

        System.out.println(USER.get()); // alice
    });
}
```

Đây là **rebinding trong scope lồng nhau**, không phải ghi đè vĩnh viễn binding của scope ngoài. Mô hình này hữu ích khi một thao tác cần chạy dưới context đặc biệt (ví dụ service identity) nhưng sau đó quay lại context caller.

### 4.3. Bind nhiều giá trị cùng lúc

Nếu cần truyền nhiều metadata, `Carrier` có thể tích lũy nhiều cặp key/value:

```java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

private static final ScopedValue<String> TENANT_ID =
        ScopedValue.newInstance();

static void handle() {
    var carrier = ScopedValue.where(REQUEST_ID, "req-42")
            .where(TENANT_ID, "tenant-a");

    carrier.run(() -> {
        System.out.println(REQUEST_ID.get());
        System.out.println(TENANT_ID.get());
    });
}
```

`ScopedValue.Carrier` là immutable và thread-safe; mỗi lần gọi `where` trả về một carrier mới với mapping được bổ sung/thay thế. Không cần tạo một `ScopedValue` cho từng trường nhỏ nếu chúng luôn đi cùng nhau; phần 9 sẽ minh họa dùng một record context để giảm số key.

## 5. Khi nào nên dùng tham số tường minh?

Tham số tường minh vẫn là lựa chọn mặc định tốt khi dữ liệu là **đầu vào thật sự của nghiệp vụ** hoặc dependency cần thể hiện rõ trong API.

Ví dụ:

```java
record RequestContext(String requestId, String tenantId) {}

record OrderId(String value) {}

final class OrderService {
    Order findOrder(OrderId orderId, RequestContext context) {
        // Dùng tenantId để giới hạn truy vấn.
        return repositoryFind(orderId, context.tenantId());
    }

    private Order repositoryFind(OrderId orderId, String tenantId) {
        // Minh họa truy vấn theo orderId + tenantId.
        return null;
    }
}
```

Ở đây `orderId` và `tenantId` quyết định kết quả nghiệp vụ. Truyền chúng tường minh giúp người đọc method biết ngay dữ liệu nào ảnh hưởng đến kết quả; compiler và IDE cũng hỗ trợ tìm tất cả call sites.

**Ưu điểm:**

- Dependency hiển thị trong chữ ký; không có context ẩn.
- Dễ unit test: truyền dữ liệu giả trực tiếp.
- Dễ tái sử dụng method trong job, batch, CLI, message consumer mà không cần mở một scope toàn cục.
- Không phụ thuộc thread hoặc dynamic scope.
- Hữu ích cho các ranh giới module/API: caller và callee có hợp đồng rõ.

**Đánh đổi:** nếu một metadata không ảnh hưởng trực tiếp đến logic của từng method nhưng phải truyền qua 10 tầng trung gian chỉ để đến logger/audit/tracing, nhiều chữ ký có thể bị phình và kéo context xuyên qua những lớp không cần biết đến nó. Khi đó `ScopedValue` có thể phù hợp hơn.

Không dùng `ScopedValue` để che giấu mọi dependency. Nếu `tenantId` quyết định quyền truy cập dữ liệu, hãy bảo đảm API nghiệp vụ thể hiện hoặc kiểm chứng rõ chính sách tenant. Có thể bind tenant context để logging/audit tiện hơn, nhưng không để một biến context ẩn thay thế việc kiểm soát quyền ở repository/service.

## 6. Khi nào nên dùng `ThreadLocal`?

`ThreadLocal<T>` gắn một giá trị riêng với **mỗi thread**. Mỗi thread gọi `get()`/`set()` có bản sao độc lập; giá trị tồn tại cho tới khi được thay đổi hoặc xóa, hoặc thread kết thúc.

Ví dụ:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

static void handle(String requestId) {
    REQUEST_ID.set(requestId);
    try {
        serviceCall();
    } finally {
        REQUEST_ID.remove();
    }
}

static void serviceCall() {
    System.out.println(REQUEST_ID.get());
}
```

`ThreadLocal` vẫn hữu ích khi:

- Một thư viện hoặc framework yêu cầu dữ liệu thread-bound.
- State thực sự thuộc về thread, không phải một request/task có vòng đời ngắn.
- Cần một vùng lưu mutable per-thread (ví dụ formatter hoặc buffer được thiết kế an toàn cho từng thread).
- Đang tích hợp với API cũ chỉ đọc `ThreadLocal` và chưa thể thay đổi hợp đồng.

### 6.1. Rủi ro với thread pool

Trong thread pool, một worker có thể xử lý nhiều request liên tiếp. Nếu request đầu `set()` nhưng không `remove()`, request sau chạy trên cùng worker có thể đọc nhầm context của request trước. Điều này gây rò rỉ dữ liệu giữa người dùng/tenant và tạo lỗi khó tái hiện.

Với nested context, chỉ `remove()` có thể chưa đủ vì có thể xóa binding của caller. Khi tự quản lý ThreadLocal có nesting, cần lưu giá trị trước, đặt giá trị mới, rồi khôi phục trong `finally`:

```java
private static final ThreadLocal<String> TENANT =
        new ThreadLocal<>();

static void withTenant(String tenant, Runnable action) {
    String previous = TENANT.get();
    TENANT.set(tenant);
    try {
        action.run();
    } finally {
        if (previous == null) {
            TENANT.remove();
        } else {
            TENANT.set(previous);
        }
    }
}
```

Ví dụ giả định `null` không phải giá trị tenant hợp lệ. Nếu ứng dụng cần phân biệt “chưa bind” với “đã bind null”, phải thiết kế trạng thái rõ ràng hơn.

### 6.2. `InheritableThreadLocal` không phải giải pháp truyền context qua mọi task

`InheritableThreadLocal` sao chép giá trị từ parent thread sang child thread **khi child thread được tạo**. Nó không tự động sao chép context tại mỗi lần submit task vào thread pool. Một worker được tạo trước đó có thể không nhận context của request submit task sau này.

Vì vậy, không dùng `InheritableThreadLocal` với giả định rằng mọi executor, `CompletableFuture` hay thread pool đều tự động truyền request context chính xác. Nếu cần context propagation qua task bất đồng bộ, phải dùng cơ chế được thiết kế cho executor/framework đó, hoặc capture và truyền dữ liệu một cách tường minh.

## 7. Bảng quyết định: chọn theo bản chất dữ liệu

| Câu hỏi | Nếu câu trả lời là “có” | Lựa chọn nên xem xét |
|---|---|---|
| Dữ liệu là đầu vào nghiệp vụ, ảnh hưởng trực tiếp đến kết quả method? | Caller và callee cần hợp đồng rõ | **Tham số tường minh** |
| Dữ liệu chỉ là metadata dùng xuyên nhiều tầng trong một lần xử lý? | Nhiều method trung gian không cần khai báo tham số | **ScopedValue** |
| Giá trị cần được thay đổi tùy ý trong suốt vòng đời thread? | API được thiết kế xoay quanh state per-thread | **ThreadLocal** |
| Dữ liệu phải tự động theo mọi executor/thread? | Cần propagation được kiểm soát, không chỉ per-thread | Xem context propagation của framework hoặc truyền task context tường minh |
| Dữ liệu cần tồn tại sau khi request kết thúc hoặc qua restart? | Đây là state bền vững | Lưu trong database/message/persistence; **không** dùng ScopedValue/ThreadLocal |
| Method được gọi độc lập từ CLI, HTTP, scheduled job và message consumer? | Context phải được khai báo rõ ở từng entry-point | Tham số tường minh hoặc adapter tạo scope tại từng entry-point |
| Chỉ một thư viện cũ đọc ThreadLocal? | Chưa thể đổi API thư viện | Dùng ThreadLocal ở adapter, giới hạn phạm vi và cleanup |
| Cần chia sẻ context chỉ đọc cho task con có cấu trúc? | Task con sống trong phạm vi parent theo mô hình hỗ trợ | ScopedValue với cơ chế structured concurrency tương thích |

**Quy tắc thực tế:** bắt đầu bằng tham số tường minh cho dữ liệu nghiệp vụ; dùng ScopedValue cho context xuyên call chain có phạm vi rõ và chỉ cần đọc; giữ ThreadLocal khi state thực sự thuộc thread hoặc ranh giới thư viện yêu cầu nó.

## 8. Ví dụ thực tế: request context dùng chung trong nhiều tầng service

Giả sử ứng dụng nhận request tạo đơn hàng. `requestId`, `tenantId` và `userId` được logging/audit dùng ở nhiều tầng, nhưng mỗi method không cần khai báo ba tham số đó. Đây là một trường hợp phù hợp để cân nhắc ScopedValue.

### 8.1. Tạo context bất biến

```java
public record RequestContext(
        String requestId,
        String tenantId,
        String userId) {
}
```

Record giúp biểu diễn context gọn và hạn chế thay đổi sau khi tạo. Tuy nhiên, record chỉ bảo đảm **shallow immutability**: nếu một component là `List` hoặc `Map` mutable, caller vẫn có thể thay nội dung bên trong. Hãy dùng các thành phần immutable hoặc defensive copy nếu cần.

### 8.2. Đóng gói key, không công khai trực tiếp

```java
import java.lang.ScopedValue;
import java.util.Objects;
import java.util.function.Supplier;

public final class RequestContextScope {
    private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

    private RequestContextScope() {}

    public static <T> T call(
            RequestContext context, Supplier<T> operation) {
        Objects.requireNonNull(context);
        Objects.requireNonNull(operation);

        return ScopedValue.where(CURRENT, context)
                .call(operation::get);
    }

    public static void run(
            RequestContext context, Runnable operation) {
        Objects.requireNonNull(context);
        Objects.requireNonNull(operation);

        ScopedValue.where(CURRENT, context).run(operation);
    }

    public static RequestContext current() {
        return CURRENT.orElseThrow(() ->
                new IllegalStateException("Request context is not bound"));
    }
}
```

Key `CURRENT` là `private static final`, không trả trực tiếp ra ngoài. Những class được phép đọc context gọi `RequestContextScope.current()`. Cách đóng gói này giới hạn nơi có quyền truy cập key; nó là một phần của thiết kế capability, không thay thế authorization hoặc kiểm soát dữ liệu.

### 8.3. Bind ở entry-point, đọc ở tầng sâu

```java
public final class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    public OrderResponse create(
            AuthenticatedPrincipal principal,
            CreateOrderRequest request) {

        RequestContext context = new RequestContext(
                request.requestId(),
                principal.tenantId(),
                principal.userId());

        return RequestContextScope.call(context, () ->
                orders.create(request));
    }
}
```

Trong service:

```java
public final class OrderService {
    private final OrderRepository repository;
    private final AuditLog audit;

    public OrderService(OrderRepository repository, AuditLog audit) {
        this.repository = repository;
        this.audit = audit;
    }

    public OrderResponse create(CreateOrderRequest request) {
        RequestContext context = RequestContextScope.current();

        audit.record(
                context.requestId(),
                context.userId(),
                "order.create");

        return repository.insert(
                context.tenantId(),
                request.toOrder());
    }
}
```

`OrderService.create` không cần nhận `RequestContext` nếu đó chỉ là metadata xuyên tầng. Dữ liệu nghiệp vụ `request` vẫn là tham số tường minh. Đây là cách kết hợp hai cơ chế thay vì buộc chọn một cho toàn ứng dụng.

**Ranh giới bảo mật:** `tenantId` trong context chỉ là dữ liệu để thực thi chính sách. Repository/service vẫn phải kiểm tra quyền truy cập theo principal đã xác thực và tenant được phép. Không tin `tenantId` do client tự gửi; entry-point phải lấy từ danh tính đã xác minh.

Trong ứng dụng thật, `request.requestId()` ở ví dụ cần là ID do middleware tin cậy tạo hoặc xác thực; không dùng một ID tùy ý từ payload client làm định danh tương quan nếu hệ thống cần bảo đảm duy nhất.

## 9. Khi nào nên bind một record thay vì nhiều ScopedValue?

ScopedValue được thiết kế để sử dụng với **số lượng key tương đối nhỏ**. JDK 25 implementation có cache theo thread; tạo quá nhiều key được bind và sử dụng luân phiên có thể làm giảm tỷ lệ cache hit. Nếu các trường luôn đi cùng nhau, một record context thường dễ quản lý hơn nhiều key độc lập.

Không nên tạo một key cho từng thuộc tính nhỏ như `REQUEST_ID`, `TENANT_ID`, `USER_ID`, `LOCALE`, `REGION`, `FEATURE_FLAG` nếu chúng luôn thuộc một context thống nhất. Có thể dùng:

```java
record ExecutionContext(
        String requestId,
        String tenantId,
        String userId,
        Locale locale) {
}

private static final ScopedValue<ExecutionContext> CONTEXT =
        ScopedValue.newInstance();
```

Rồi bind một lần:

```java
ExecutionContext context = new ExecutionContext(
        "req-42", "tenant-a", "user-7", Locale.forLanguageTag("vi"));

ScopedValue.where(CONTEXT, context).run(() -> processOrder());
```

Ngược lại, nếu hai giá trị có **vòng đời và quyền truy cập khác nhau**, hoặc một giá trị chỉ cần ở một phần của call chain, tách key có thể giúp giới hạn khả năng truy cập tốt hơn. Cần cân bằng giữa số key, sự gắn kết dữ liệu và ranh giới capability.

## 10. Chia sẻ qua thread: điều gì tự động và điều gì không?

Một binding ScopedValue là **per-thread**. Trong thread đang chạy `run`/`call`, các method được gọi đồng bộ có thể đọc binding. Nhưng không nên giả định một tác vụ bất kỳ được submit sang executor khác sẽ tự động nhận binding của thread gửi.

### 10.1. Executor thông thường không tự truyền ScopedValue

Ví dụ không an toàn về giả định propagation:

```java
RequestContextScope.run(context, () -> {
    executor.submit(() -> {
        // Worker không tự nhận binding của thread gửi.
        processInBackground();
    });
});
```

`executor` có thể dùng một worker thread khác. Binding được thiết lập trên thread gọi `run`, nên code ở worker không mặc nhiên đọc được giá trị đó. `ThreadLocal` cũng không tự động truyền theo từng task vào một worker đã tồn tại.

### 10.2. Capture context và bind lại trong task

Nếu nghiệp vụ yêu cầu truyền context tới task, capture dữ liệu cần thiết tại nơi submit và bind lại **trong thân task**:

```java
RequestContext captured = RequestContextScope.current();

executor.submit(() ->
        RequestContextScope.run(captured, () -> {
            backgroundOrderWork();
        }));
```

Với tác vụ trả kết quả:

```java
RequestContext captured = RequestContextScope.current();

CompletableFuture<Order> future =
        CompletableFuture.supplyAsync(
                () -> RequestContextScope.call(
                        captured,
                        () -> orderService.loadOrder(orderId)),
                executor);
```

Cách này thể hiện rõ dữ liệu nào được mang qua ranh giới async. Chỉ capture các trường thật sự cần thiết; không giữ toàn bộ request object, servlet request, mutable security context hoặc resource đã hết vòng đời. Task cũng cần có chính sách timeout/cancellation và không được tiếp tục sử dụng context sau khi nghiệp vụ đã kết thúc.

Nếu một framework đã cung cấp context propagation riêng cho tracing/security/observability, hãy sử dụng cơ chế tương thích của framework thay vì tự viết một lớp truyền context cạnh tranh với nó.

### 10.3. Structured concurrency trong Java 25: phân biệt API final và preview

ScopedValue hỗ trợ chia sẻ binding trong những tình huống structured concurrency: binding được capture khi tạo `StructuredTaskScope` và được thừa kế bởi các thread con do scope fork. Parent scope đợi các task con kết thúc trước khi rời scope, giúp vòng đời binding được giới hạn có cấu trúc.

Tuy nhiên, **`StructuredTaskScope` trong Java 25 vẫn là preview API** (JEP 505, lần preview thứ năm). `ScopedValue` là final; `StructuredTaskScope` không vì thế mà trở thành final. Nếu dự án chủ động thử structured concurrency trên JDK 25, phải bật preview theo quy trình build/runtime và chấp nhận API có thể thay đổi. Không dùng `StructuredTaskScope` như dependency production ổn định trong một bài học chỉ yêu cầu API final.

Khi chỉ cần dùng ScopedValue trong call chain đồng bộ hoặc tự capture/rebind context ở executor, **không cần** StructuredTaskScope và không cần `--enable-preview` cho ScopedValue.

## 11. ScopedValue và virtual threads

Virtual threads là thread Java nhẹ, được thiết kế để hỗ trợ nhiều tác vụ blocking đồng thời. `ThreadLocal` vẫn hoạt động trên virtual thread, nhưng mỗi virtual thread có state riêng. Nếu tạo rất nhiều virtual threads và mỗi thread giữ nhiều giá trị ThreadLocal hoặc object lớn, phần bộ nhớ đó vẫn cần được tính vào ngân sách.

ScopedValue phù hợp với dữ liệu context **chỉ đọc, có phạm vi** trong mô hình virtual-thread/structured concurrency vì binding không cần duy trì mutable map suốt vòng đời một worker thread tái sử dụng. Tuy nhiên:

- ScopedValue không tự động truyền sang mọi virtual thread được tạo thủ công.
- `Thread.startVirtualThread(...)` hoặc executor virtual-thread không đồng nghĩa với structured inheritance của `StructuredTaskScope`.
- Khi cần propagation qua task độc lập, capture dữ liệu và bind lại trong task, hoặc dùng cơ chế context propagation được framework hỗ trợ.
- Không chọn ScopedValue chỉ vì nghĩ rằng nó luôn nhanh hơn ThreadLocal. Hãy đo workload thực tế, số key, số lần bind/get và lượng context giữ trong memory.

Nếu code hiện có dùng ThreadLocal đúng cách và không gặp vấn đề về cleanup/propagation, không cần chuyển đổi chỉ để chạy trên virtual threads. Hãy thay đổi khi semantics của dữ liệu phù hợp hơn với phạm vi bất biến của ScopedValue.

## 12. Bảo mật, khả năng thay đổi và quyền truy cập key

Oracle mô tả ScopedValue key như một **capability**: code có key có thể đọc giá trị khi key được bind. Vì vậy, việc thiết kế quyền truy cập key rất quan trọng.

Các nguyên tắc:

1. Khai báo key ở phạm vi hẹp, thường là `private static final` trong class hoặc nest có trách nhiệm quản lý context.
2. Expose method đọc có kiểm soát (`currentTenant()`, `requestId()`) nếu module khác thực sự cần, thay vì public key dùng toàn hệ thống.
3. Bind một object context bất biến hoặc chỉ đọc; ScopedValue không tự biến object được bind thành immutable.
4. Không bind credential, access token hoặc secret chỉ vì tiện truy cập. Nếu buộc phải truyền thông tin nhạy cảm, giới hạn phạm vi, quyền đọc và thời gian sống; ưu tiên handle an toàn thay vì dữ liệu bí mật thô.
5. Không coi `ScopedValue` là security boundary độc lập. Authentication/authorization vẫn phải được kiểm tra tại điểm truy cập tài nguyên.
6. Không để callback/task bất đồng bộ giữ context lâu hơn phạm vi nghiệp vụ cần thiết.

### Value mutable có nguy cơ gì?

```java
record MutableContext(Map<String, String> attributes) {}
```

Record này không thực sự immutable nếu map bên trong còn thay đổi được. Hai task con cùng đọc một binding nhưng một task sửa map có thể tạo data race hoặc làm task kia quan sát trạng thái khác nhau.

Có thể tạo bản copy bất biến:

```java
record SafeContext(Map<String, String> attributes) {
    SafeContext {
        attributes = Map.copyOf(attributes);
    }
}
```

`Map.copyOf` tạo map không sửa được qua reference trả về; các value bên trong cũng cần immutable nếu muốn bảo đảm sâu. Với dữ liệu phức tạp, dùng object immutable hoặc đồng bộ hóa mọi truy cập chia sẻ.

## 13. So sánh vòng đời bằng một ví dụ ThreadLocal và ScopedValue

Cùng một mục đích là truyền `requestId` tới các method phía dưới, hai API có khác biệt đáng kể.

**ScopedValue:**

```java
private static final ScopedValue<String> REQUEST_ID =
        ScopedValue.newInstance();

static void handle(String requestId) {
    ScopedValue.where(REQUEST_ID, requestId).run(() -> {
        serviceCall();
    });
}

static void serviceCall() {
    System.out.println(REQUEST_ID.get());
}
```

Khi `run` kết thúc, binding được tự động khôi phục. Không có lệnh dọn thủ công.

**ThreadLocal:**

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();

static void handle(String requestId) {
    REQUEST_ID.set(requestId);
    try {
        serviceCall();
    } finally {
        REQUEST_ID.remove();
    }
}

static void serviceCall() {
    System.out.println(REQUEST_ID.get());
}
```

Ở đây lập trình viên chịu trách nhiệm dọn state. Nếu bỏ `finally`, worker thread được tái sử dụng có thể mang `requestId` cũ sang request tiếp theo. Nếu có nested context, cần khôi phục giá trị trước thay vì luôn `remove()`.

| Tình huống | ScopedValue | ThreadLocal |
|---|---|---|
| Kết thúc method xử lý | Binding tự kết thúc khi operation kết thúc | Giá trị còn cho tới khi set/remove hoặc thread kết thúc |
| Exception | Binding được khôi phục tự động | Phải cleanup trong `finally` |
| Nested scope | Binding mới được lồng, giá trị ngoài được khôi phục | Phải tự lưu/khôi phục giá trị trước |
| Cập nhật value trong cùng scope | Không có `set`; tạo nested binding mới | Có thể `set` bất kỳ lúc nào |
| Dùng trong executor | Capture và bind lại hoặc propagation hỗ trợ | Capture/set/remove theo task; không dựa vào worker state cũ |

Đây là khác biệt về **semantics và vòng đời**, không phải một benchmark. Nếu ứng dụng thực sự cần một biến mutable sống suốt vòng đời thread, ThreadLocal vẫn phù hợp hơn.

## 14. Hiệu năng: tối ưu sau khi đo, không chỉ dựa vào tên API

ScopedValue được thiết kế để dùng với **số lượng key tương đối nhỏ**. JDK 25 implementation có cơ chế cache per-thread cho binding gần nhất; số key lớn được sử dụng luân phiên có thể làm giảm cache hit và khiến lookup phải tìm lại các enclosing scope. Vì vậy, gom các giá trị có vòng đời chung vào một immutable record thường là lựa chọn hợp lý.

Khi đánh giá hiệu năng, đo riêng:

- Chi phí tạo key/binding và chạy `run`/`call`.
- Số lần `get()` trong một request/task.
- Số key được bind đồng thời và số scope lồng nhau.
- Throughput, allocation rate, GC và latency p95/p99.
- Số lượng virtual threads và dung lượng context được giữ.
- Chi phí propagation khi submit qua executor.

Không tuyên bố ScopedValue nhanh hơn ThreadLocal trong mọi workload. Kết quả phụ thuộc JDK patch, số key, độ sâu call chain, thread model, loại value và cách benchmark. Dùng JMH hoặc benchmark đại diện có warmup/fork phù hợp; so sánh cùng JDK 25, cùng workload, không benchmark một vòng lặp nhỏ rồi suy ra toàn hệ thống.

Không tùy chỉnh các system properties nội bộ của ScopedValue chỉ vì thấy chúng trong implementation note. Trước tiên dùng API chuẩn và đo bottleneck. Nếu cân nhắc property phụ thuộc implementation, phải kiểm tra tài liệu của đúng bản JDK vendor/patch và kiểm thử lại sau nâng cấp.

## 15. Kiểm thử và checklist chọn cơ chế

### 15.1. Những ca cần kiểm thử với ScopedValue

| Ca kiểm thử | Hành vi mong đợi |
|---|---|
| `get()` trong scope đã bind | Trả đúng value |
| `get()` khi chưa bind | Ném `NoSuchElementException` |
| `isBound()` ngoài scope | `false` |
| `orElse(default)` ngoài scope | Trả giá trị mặc định |
| Scope kết thúc bình thường | Binding hết hoặc khôi phục outer binding |
| Operation ném exception | Binding vẫn được khôi phục |
| Nested binding cùng key | Scope trong thấy value mới; scope ngoài thấy lại value cũ |
| Hai thread bind hai giá trị riêng | Mỗi thread đọc binding của chính nó |
| Submit task vào executor thường | Không mặc định thấy binding của thread gửi |
| Task capture/rebind tường minh | Task đọc đúng context đã capture |
| Context có collection mutable | Kiểm tra race và thay đổi ngoài ý muốn |
| Nhiều key được bind | Đánh giá có nên gom vào một record |

### 15.2. Test tối thiểu không cần preview

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.ScopedValue;
import org.junit.jupiter.api.Test;

class ScopedValueTest {
    private static final ScopedValue<String> KEY =
            ScopedValue.newInstance();

    @Test
    void bindingIsRestoredAfterRun() {
        assertFalse(KEY.isBound());

        ScopedValue.where(KEY, "outer").run(() -> {
            assertEquals("outer", KEY.get());

            ScopedValue.where(KEY, "inner").run(() ->
                    assertEquals("inner", KEY.get()));

            assertEquals("outer", KEY.get());
        });

        assertFalse(KEY.isBound());
    }

    @Test
    void bindingIsRestoredWhenOperationThrows() {
        assertThrows(IllegalStateException.class, () ->
            ScopedValue.where(KEY, "temporary").run(() -> {
                assertEquals("temporary", KEY.get());
                throw new IllegalStateException("expected");
            }));

        assertFalse(KEY.isBound());
    }
}
```

Ví dụ cần JUnit Jupiter trong test classpath. `ScopedValue` đã final trong Java 25 nên test không cần `--enable-preview`. Mỗi test nên có key riêng hoặc bảo đảm không chạy các test chia sẻ key theo cách làm rò rỉ scope.

### 15.3. Checklist quyết định trong code review

- Dữ liệu là **nghiệp vụ** hay **metadata xuyên tầng**?
- Nếu là nghiệp vụ, có thể truyền tham số để thể hiện dependency rõ không?
- Nếu là metadata, phạm vi bind bắt đầu và kết thúc ở đâu?
- Method nào được quyền đọc key? Key có bị public rộng hơn cần thiết không?
- Value có immutable không, hoặc có được đồng bộ khi chia sẻ không?
- Có executor, CompletableFuture hoặc thread khác trong call chain không?
- Có đang giả định `ThreadLocal`/ScopedValue tự truyền qua task không?
- Với ThreadLocal, `remove()`/restore đã được bảo đảm ở mọi đường thoát chưa?
- Với virtual threads, lượng context được giữ trên mỗi task có hợp lý không?
- Có benchmark chứng minh cần tối ưu không, hay chỉ đang đổi API theo xu hướng?

## 16. Bài tập thực hành và tiêu chí hoàn thành

### Bài tập 1 — Chọn tham số hay ScopedValue

Một method `calculateShipping(Order order, ShippingPolicy policy)` cần `order` và `policy`; logger ở 5 tầng phía dưới cần `requestId`. Hãy xác định dữ liệu nào nên là tham số và dữ liệu nào phù hợp với ScopedValue. Giải thích theo dependency và vòng đời.

### Bài tập 2 — Lỗi rò rỉ ThreadLocal

Một web server dùng thread pool 20 worker. Request A gọi `CURRENT_TENANT.set("tenant-A")` rồi ném exception trước `remove()`. Request B sau đó chạy trên cùng worker và đọc được tenant nào? Hãy sửa bằng `try/finally`, đồng thời giải thích vì sao ScopedValue giảm rủi ro này.

### Bài tập 3 — Nested binding

Bind `USER = "alice"`, bên trong bind lại `USER = "service"`, rồi ném exception trong scope trong. Giá trị nhìn thấy sau khi bắt exception ở scope ngoài là gì? Viết test chứng minh binding outer được khôi phục.

### Bài tập 4 — Async propagation

Một request bind `requestId` bằng ScopedValue rồi submit task vào `ExecutorService`. Vì sao task không nên mặc định đọc binding của thread gửi? Viết wrapper capture `RequestContext` và bind lại bên trong task.

### Bài tập 5 — Chia sẻ mutable context

Một record context chứa `Map<String, Object>` mutable được bind cho ScopedValue. Vì sao key binding không làm map bất biến? Đề xuất cách tạo immutable snapshot và xác định trường hợp cần đồng bộ.

### Bài tập 6 — Virtual threads và preview API

Phân biệt `ThreadLocal`, `ScopedValue` và `StructuredTaskScope` trong Java 25. API nào đã final, API nào còn preview? Vì sao không nên dùng StructuredTaskScope như API production ổn định trong một dự án không bật preview?

### Tiêu chí đạt

Bạn hoàn thành bài học khi có thể:

1. Giải thích ScopedValue là API final từ Java 25, biết `newInstance`, `where`, `run`, `call`, `get`, `isBound`, `orElse` và `orElseThrow`.
2. Mô tả dynamic scope, tự khôi phục sau return/exception và nested rebinding.
3. Chọn tham số tường minh cho dữ liệu nghiệp vụ, ScopedValue cho context một chiều có phạm vi, ThreadLocal cho state gắn thread/khả năng tương thích cần thiết.
4. Không nhầm binding per-thread với propagation tự động qua executor hoặc thread tùy ý.
5. Thiết kế key có phạm vi truy cập hẹp và value immutable/được đồng bộ đúng cách.
6. Kiểm soát cleanup ThreadLocal và hiểu hành vi thread pool/virtual threads.
7. Phân biệt ScopedValue final với StructuredTaskScope preview ở Java 25; không yêu cầu preview flag cho ScopedValue.
8. Đưa ra quyết định dựa trên semantics và benchmark đại diện, không chỉ giả định về tốc độ.

### Tài liệu tham khảo

1. [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): lý do thiết kế và việc hoàn tất API trong Java 25.
2. [Java SE 25 API — `ScopedValue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): binding, dynamic scope, rebinding, per-thread semantics, inheritance và implementation notes.
3. [Java SE 25 API — `ScopedValue.Carrier`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html): `where`, `run`, `call`, carrier immutable.
4. [Java SE 25 API — `ThreadLocal`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ThreadLocal.html): state độc lập theo từng thread.
5. [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái preview của StructuredTaskScope trong Java 25.
6. [Oracle Java 25 — Scoped Values guide](https://docs.oracle.com/en/java/javase/25/core/scoped-values.html): cách dùng ScopedValue trong core libraries.

> **Ghi chú hiện hành:** ScopedValue đã là API chuẩn từ Java 25 và tiếp tục là API Java SE ở các JDK sau. ThreadLocal vẫn được hỗ trợ; chọn theo semantics chứ không coi là legacy. StructuredTaskScope trong Java 25 vẫn preview, nên bài chỉ nêu giới hạn tương thích và không dùng nó làm ví dụ production bắt buộc.
