# Thiết kế ngữ cảnh yêu cầu bằng ScopedValue và kiểm thử xử lý đồng thời

## 1. Bài toán: truyền ngữ cảnh xuyên qua nhiều tầng xử lý

Một request HTTP thường đi qua nhiều lớp: controller, application service, repository, HTTP client, logging và audit. Một số dữ liệu cần được dùng ở nhiều lớp nhưng không phải dữ liệu nghiệp vụ của từng method, ví dụ:

- Request ID để liên kết log và sự kiện.
- Trace ID để nối các span quan sát.
- Tenant ID để áp dụng ranh giới dữ liệu.
- ID người dùng hoặc principal đã được xác thực.
- Thời điểm request bắt đầu để tính thời gian xử lý.

Nếu truyền tất cả các giá trị này qua từng tham số, nhiều method phải nhận tham số chỉ để chuyển tiếp cho method sâu hơn. Nếu dùng `ThreadLocal`, code phải tự quản lý `set`/`remove`, và giá trị có thể tồn tại trên worker thread sau khi request hoàn tất nếu cleanup bị bỏ sót.

**ScopedValue** cung cấp một cách truyền ngữ cảnh theo phạm vi thực thi. Caller bind một giá trị cho một operation; các method được gọi trực tiếp hoặc gián tiếp trong operation đó có thể đọc giá trị bằng cùng một key. Khi operation kết thúc bình thường hoặc ném exception, binding tự động trở về trạng thái trước đó.

Trong Java 25, Scoped Values là tính năng permanent theo **JEP 506**. Bài thực hành dùng `ScopedValue` để thiết kế request context bất biến, kiểm tra nested scope, kiểm tra cleanup khi exception và xác minh nhiều request chạy đồng thời không đọc nhầm context của nhau.

### Kết quả cần đạt

Sau bài học, bạn có thể:

1. Xác định dữ liệu nào phù hợp để đặt trong request context.
2. Tạo `ScopedValue<RequestContext>` và bind dữ liệu trong phạm vi request.
3. Đọc context ở tầng service/repository mà không truyền tham số qua mọi method.
4. Hiểu `get()`, `isBound()`, `orElse()`, `run()` và `call()`.
5. Dùng nested binding và hiểu cách binding cha được khôi phục.
6. Kiểm thử binding được dọn khi code ném exception.
7. Hiểu giới hạn truyền context sang thread mới và task executor.
8. Chủ động bind context trong từng task bất đồng bộ.
9. Kiểm thử tính cô lập của nhiều request chạy đồng thời trên virtual threads.
10. Biết khi nào nên dùng `ScopedValue`, tham số tường minh hoặc một cơ chế context propagation của framework.

> **Phạm vi Java 25:** `ScopedValue` đã permanent, không cần `--enable-preview`. `StructuredTaskScope` trong Java 25 vẫn là preview; bài lab chính không phụ thuộc API đó. `ExecutorService` và virtual-thread-per-task executor là API đã ổn định, nhưng task gửi vào executor phải được bind context tường minh.

## 2. Chọn đúng dữ liệu cho request context

### 2.1. Dữ liệu phù hợp

Request context nên chứa những thông tin xuyên suốt nhiều tầng xử lý, có vòng đời gần với request và không cần thay đổi trong quá trình xử lý.

Ví dụ:

| Trường | Mục đích | Ghi chú |
|---|---|---|
| `requestId` | Liên kết log, audit và lỗi | Nên duy nhất trong phạm vi hệ thống |
| `traceId` | Liên kết trace phân tán | Có thể đến từ tracing framework |
| `tenantId` | Xác định tenant của request | Phải được xác minh ở boundary tin cậy |
| `principalId` | Nhận diện principal đã xác thực | Chỉ lưu định danh, không lưu credential |
| `startedAt` | Đo thời gian xử lý | Dùng `Instant` bất biến |

Không đưa bearer token, password, private key, mutable request object, `HttpServletRequest`, connection hoặc transaction handle vào context. Các đối tượng đó có vòng đời và quyền truy cập riêng; chia sẻ ngầm có thể tạo rò rỉ dữ liệu hoặc lỗi đồng thời.

### 2.2. Dùng một record thay vì nhiều scoped values

JDK thiết kế Scoped Values cho số lượng key tương đối nhỏ. Nếu cần truyền nhiều trường có liên quan, gom chúng vào một record bất biến rồi bind một key duy nhất.

```java
record RequestContext(
    String requestId,
    String traceId,
    String tenantId,
    String principalId,
    Instant startedAt
) {}
```

Record có các field `final`, nhưng tính bất biến chỉ là bất biến nông. Nếu record chứa `List`, `Map` hoặc object mutable, các thành phần đó vẫn có thể bị thay đổi. Ưu tiên `String`, `Instant`, enum, primitive và collection bất biến.

### 2.3. ScopedValue là key/capability

Một `ScopedValue` vừa là key để truy cập binding, vừa là capability cho code được phép giữ key đó. Nên khai báo key là `private static final` trong lớp quản lý context:

```java
private static final ScopedValue<RequestContext> CURRENT =
    ScopedValue.newInstance();
```

Không công khai key rộng rãi nếu không cần thiết. Cung cấp các method có chủ đích như `current()` hoặc `withContext(...)` để kiểm soát nơi bind và nơi đọc.

### 2.4. Khi nào không nên dùng ScopedValue?

Không dùng ScopedValue chỉ vì muốn tránh viết tham số. Hãy giữ tham số tường minh khi:

- Dữ liệu là đầu vào nghiệp vụ chính của method.
- Method cần hoạt động độc lập, dễ gọi từ nhiều nguồn.
- Dữ liệu phải được lưu lâu hơn một operation.
- Giá trị cần được cập nhật liên tục trong quá trình xử lý.
- Một component cần nhận nhiều context khác nhau cùng lúc và quan hệ giữa chúng không rõ ràng.

ScopedValue phù hợp với ngữ cảnh xuyên suốt một luồng xử lý, không phải kho chứa trạng thái tổng quát.

## 3. Cách hoạt động của ScopedValue

### 3.1. Tạo key và bind giá trị

Một key được tạo bằng `ScopedValue.newInstance()`:

```java
private static final ScopedValue<String> REQUEST_ID =
    ScopedValue.newInstance();
```

Bind key trong phạm vi một operation bằng `where(...).run(...)`:

```java
ScopedValue.where(REQUEST_ID, "req-42").run(() -> {
    System.out.println(REQUEST_ID.get());
});
```

Trong lambda và các method được gọi từ lambda, `REQUEST_ID.get()` trả về `"req-42"`. Khi `run` kết thúc, binding được khôi phục về trạng thái trước đó.

### 3.2. Chạy operation và nhận kết quả

Dùng `run()` khi operation không trả kết quả:

```java
ScopedValue.where(REQUEST_ID, "req-42")
    .run(() -> auditService.record("request-started"));
```

Dùng `call()` khi operation trả về kết quả:

```java
String result = ScopedValue.where(REQUEST_ID, "req-42")
    .call(() -> orderService.handle("order-17"));
```

`call()` nhận `ScopedValue.CallableOp`, có thể ném exception. Exception được truyền về caller; binding vẫn được khôi phục trước khi exception thoát khỏi operation.

### 3.3. Các API đọc binding

| API | Ý nghĩa |
|---|---|
| `get()` | Lấy giá trị đang bind trên thread hiện tại; ném `NoSuchElementException` nếu key chưa được bind |
| `isBound()` | Kiểm tra key có binding trên thread hiện tại hay không |
| `orElse(other)` | Lấy giá trị nếu có binding, nếu không trả về giá trị thay thế |
| `orElseThrow(supplier)` | Lấy giá trị hoặc ném exception do supplier tạo |

Ví dụ:

```java
if (REQUEST_ID.isBound()) {
    log.info("requestId={}", REQUEST_ID.get());
}

String requestId = REQUEST_ID.orElse("no-request");
```

Ở code yêu cầu bắt buộc phải có context, ưu tiên `get()` để lỗi thiếu binding lộ ra sớm. Dùng `orElse()` cho code thực sự có thể chạy ngoài request, chẳng hạn một tác vụ nền không gắn request.

### 3.4. Binding là bất biến trong phạm vi

Sau khi bind, không có thao tác `set()` để thay đổi giá trị tại chỗ. Muốn dùng giá trị khác, tạo một nested scope:

```java
ScopedValue.where(REQUEST_ID, "parent").run(() -> {
    System.out.println(REQUEST_ID.get()); // parent

    ScopedValue.where(REQUEST_ID, "child").run(() -> {
        System.out.println(REQUEST_ID.get()); // child
    });

    System.out.println(REQUEST_ID.get()); // parent
});
```

Nested scope giúp code tạm thời thay context cho một operation con. Khi operation con kết thúc, binding trước đó tự động được khôi phục.

### 3.5. Binding có phạm vi theo thread

ScopedValue binding gắn với thread đang thực thi `run()` hoặc `call()`. Các method được gọi đồng bộ trên cùng thread nhìn thấy binding đó.

Điều này không có nghĩa mọi thread được tạo trong thời gian binding đều tự động nhận context. Tự động kế thừa chỉ được hỗ trợ trong cấu trúc concurrency có quan hệ cha/con được quản lý, cụ thể là `StructuredTaskScope` trong Java 25 (API preview). Với `ExecutorService` thông thường, phải truyền context và bind lại trong task.

## 4. Thiết kế lớp RequestContextScope

Ta sẽ xây một lớp quản lý duy nhất cho key và các thao tác bind. Lớp này giữ key ở private scope để tầng nghiệp vụ không thể tùy ý thay đổi binding.

### 4.1. Record bất biến

```java
import java.time.Instant;
import java.util.Objects;

record RequestContext(
    String requestId,
    String traceId,
    String tenantId,
    String principalId,
    Instant startedAt
) {
    RequestContext {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(traceId, "traceId");
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(principalId, "principalId");
        Objects.requireNonNull(startedAt, "startedAt");
    }
}
```

Constructor compact kiểm tra các trường bắt buộc. Việc từ chối `null` ở đây là quy tắc của model ứng dụng; nó cũng tránh tình trạng binding tồn tại nhưng context lại không có giá trị hữu ích.

### 4.2. Lớp quản lý binding

```java
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.Callable;
import java.lang.ScopedValue;

final class RequestContextScope {

    private static final ScopedValue<RequestContext> CURRENT =
        ScopedValue.newInstance();

    private RequestContextScope() {}

    static void runWith(RequestContext context, Runnable action) {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");

        ScopedValue.where(CURRENT, context).run(action);
    }

    static <T> T callWith(
            RequestContext context,
            Callable<T> action
    ) throws Exception {
        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");

        return ScopedValue.where(CURRENT, context).call(action::call);
    }

    static RequestContext current() {
        return CURRENT.get();
    }

    static Optional<RequestContext> currentOptional() {
        return CURRENT.isBound()
            ? Optional.of(CURRENT.get())
            : Optional.empty();
    }

    static boolean isBound() {
        return CURRENT.isBound();
    }
}
```

`runWith` dùng cho operation không trả kết quả. `callWith` dùng cho operation trả kết quả và giữ nguyên checked exception của `Callable`. Cả hai đều tạo binding qua `ScopedValue.where`.

`current()` là lựa chọn cho code chỉ hợp lệ khi đang xử lý request. `currentOptional()` dành cho thành phần có thể chạy cả trong và ngoài request. Không nên dùng `currentOptional()` để âm thầm bỏ qua context bắt buộc.

### 4.3. Vì sao key phải private?

Nếu nhiều package cùng giữ key và tự bind, code có thể vô tình ghi đè context của nhau hoặc tạo nested scope khó kiểm soát. Khi key private:

- Chỉ lớp quản lý có quyền tạo binding.
- Code nghiệp vụ chỉ đọc thông qua API `current()`.
- Quy tắc kiểm tra và quyền truy cập được tập trung.
- Có thể thay đổi cấu trúc record mà ít ảnh hưởng tới caller.

Nếu framework cần tích hợp, hãy cung cấp adapter có phạm vi rõ ràng thay vì công khai key cho toàn bộ ứng dụng.


## 5. Đưa context vào request boundary

### 5.1. Tạo context tại điểm tin cậy

Context nên được tạo sau khi ứng dụng đã xác thực request và xác định tenant/principal. Không lấy `tenantId` hoặc `principalId` từ header tùy ý rồi xem đó là danh tính đã xác minh.

Ví dụ tại application boundary:

```java
RequestContext context = new RequestContext(
    request.requestId(),
    traceContext.traceId(),
    authenticatedTenant.id(),
    authenticatedPrincipal.id(),
    Instant.now()
);

String response = RequestContextScope.callWith(
    context,
    () -> orderService.handle(request.orderId())
);
```

Tại đây, `callWith` mở scope cho toàn bộ quá trình xử lý đồng bộ của request. Nếu service gọi repository, audit service hoặc HTTP client theo cùng call stack, các lớp đó có thể đọc context mà không cần nhận thêm tham số.

### 5.2. Đọc context ở tầng sâu

Ví dụ service không cần nhận request ID và tenant ID chỉ để chuyển tiếp:

```java
final class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    String handle(String orderId) {
        return repository.load(orderId);
    }
}

final class OrderRepository {
    String load(String orderId) {
        RequestContext context = RequestContextScope.current();

        return "order=" + orderId
            + ", tenant=" + context.tenantId()
            + ", request=" + context.requestId()
            + ", trace=" + context.traceId();
    }
}
```

Context không thay thế tham số nghiệp vụ `orderId`. Nó chỉ mang thông tin xuyên suốt request. Đây là ranh giới quan trọng: dữ liệu quyết định kết quả của method vẫn nên được truyền tường minh.

### 5.3. Operation không cần kết quả

Nếu request handler ghi audit hoặc thực hiện một operation không trả kết quả, dùng `runWith`:

```java
RequestContextScope.runWith(context, () -> {
    auditService.recordRequestStarted();
    notificationService.scheduleConfirmation();
});
```

Mọi method được gọi đồng bộ bên trong lambda có thể đọc context. Sau khi lambda kết thúc, binding được khôi phục tự động.

### 5.4. Không bind context quá sớm hoặc quá rộng

Không bind context toàn cục khi ứng dụng khởi động, cũng không bind một context dùng chung cho nhiều request. Mỗi request phải có context riêng và scope phải bao quanh đúng operation.

Nếu một request được chuyển sang callback chạy sau khi response đã kết thúc, callback đó có vòng đời riêng. Hãy quyết định rõ callback có cần một bản snapshot context hay không, rồi bind snapshot khi bắt đầu callback.

## 6. Nested scope và khôi phục binding

### 6.1. Tạm thời thay context cho operation con

Một operation con đôi khi cần context dẫn xuất, ví dụ tạo request ID con để phân biệt một nhánh xử lý. Không sửa record hiện tại; tạo một record mới và bind trong nested scope.

```java
RequestContext parent = new RequestContext(
    "req-100",
    "trace-abc",
    "tenant-a",
    "user-7",
    Instant.now()
);

RequestContext child = new RequestContext(
    parent.requestId() + "/inventory",
    parent.traceId(),
    parent.tenantId(),
    parent.principalId(),
    parent.startedAt()
);

RequestContextScope.runWith(parent, () -> {
    check(RequestContextScope.current().equals(parent), "parent binding");

    RequestContextScope.runWith(child, () -> {
        check(RequestContextScope.current().equals(child), "child binding");
        inventoryService.reserve();
    });

    check(RequestContextScope.current().equals(parent), "parent restored");
});
```

Sau nested scope, context cha được khôi phục. Cách này giúp log của nhánh con có thể phân biệt được mà không làm thay đổi context của phần request còn lại.

### 6.2. Binding được khôi phục khi exception

Không cần viết `finally` để gọi `remove()`. ScopedValue khôi phục binding khi operation kết thúc, kể cả khi exception thoát khỏi lambda.

```java
RequestContext context = createContext();

try {
    RequestContextScope.runWith(context, () -> {
        service.doWork();
        throw new IllegalStateException("simulated failure");
    });
} catch (IllegalStateException expected) {
    // Xử lý lỗi request.
}

check(!RequestContextScope.isBound(), "binding must be cleared");
```

Nếu có binding cha, sau exception của scope con, binding cha được khôi phục. Nếu không có binding cha, key trở về trạng thái unbound.

### 6.3. Không bắt exception rồi tiếp tục với context sai

Nếu một nested operation thất bại, hãy xử lý lỗi ở đúng boundary. Không giữ một biến context mutable bên ngoài rồi sửa nó để “khôi phục” trạng thái. Hãy để scope đảm nhận việc khôi phục binding; business error vẫn được xử lý theo hợp đồng của service.

### 6.4. Đọc giá trị khi không có binding

`get()` ném `NoSuchElementException` nếu key chưa được bind trên thread hiện tại. Đây là hành vi hữu ích để phát hiện code gọi sai boundary.

Nếu một component hợp lệ khi chạy cả trong và ngoài request, kiểm tra `isBound()` hoặc dùng `currentOptional()`. Không bắt mọi `NoSuchElementException` chung chung rồi bỏ qua, vì exception đó cũng có thể phát sinh từ logic khác.

## 7. Truyền context sang task bất đồng bộ

### 7.1. Vì sao executor không tự nhận binding?

ScopedValue binding là per-thread. Khi code trong request gọi `executor.submit(...)`, executor chạy task trên một thread khác. Với `ExecutorService` thông thường, binding của thread gửi task không tự động được copy sang thread thực thi task.

Đoạn sau không hợp lệ về mặt context propagation:

```java
RequestContextScope.runWith(context, () -> {
    executor.submit(() -> {
        // Không được giả định context của thread gửi task có ở đây.
        return RequestContextScope.current();
    });
});
```

Task có thể chạy trên thread chưa bind context; `current()` khi đó ném `NoSuchElementException`.

### 7.2. Chụp context và bind trong task

Cách rõ ràng là đọc snapshot tại nơi submit và bind lại bên trong task:

```java
RequestContext captured = RequestContextScope.current();

Future<String> future = executor.submit((Callable<String>) () ->
    RequestContextScope.callWith(captured, () -> {
        RequestContext taskContext = RequestContextScope.current();
        return inventoryClient.check(taskContext.tenantId());
    })
);
```

Mỗi task nhận một context cụ thể. Binding chỉ tồn tại trong lúc callable chạy và tự khôi phục khi task hoàn tất.

Nếu task được submit từ ngoài request, hãy truyền context đầu vào tường minh hoặc chạy task trong một scope nền được thiết kế riêng. Không tạo context giả bằng cách đọc một key chưa bind.

### 7.3. Dùng virtual-thread-per-task executor

Virtual threads đã là tính năng permanent từ Java 21. Với workload có nhiều tác vụ chờ I/O, có thể dùng:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    RequestContext captured = RequestContextScope.current();

    Future<String> inventory = executor.submit((Callable<String>) () ->
        RequestContextScope.callWith(captured, () -> inventoryClient.check())
    );

    Future<String> pricing = executor.submit((Callable<String>) () ->
        RequestContextScope.callWith(captured, () -> pricingClient.quote())
    );

    return combine(inventory.get(), pricing.get());
}
```

`newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task được submit. `ExecutorService` trong Java hiện đại là `AutoCloseable`; khi thoát try-with-resources, `close()` đợi các task đã submit kết thúc.

Virtual threads giúp tăng khả năng phục vụ nhiều tác vụ blocking I/O; chúng không làm một phép tính CPU-bound chạy nhanh hơn. Với công việc CPU-intensive, hãy giới hạn parallelism theo tài nguyên CPU.

### 7.4. Tự động kế thừa trong StructuredTaskScope

Java 25 có thể kế thừa scoped bindings sang các child tasks được fork trong `StructuredTaskScope`. Tuy nhiên, `StructuredTaskScope` ở Java 25 vẫn là preview API. Nếu hệ thống chưa chấp nhận preview, không lấy cơ chế đó làm nền tảng cho code production.

Bài lab dùng executor ổn định và bind tường minh trong mỗi task. Cách này làm rõ dữ liệu nào được truyền qua ranh giới bất đồng bộ và không phụ thuộc preview flag.

### 7.5. Context phải bất biến khi chia sẻ

Khi cùng một context được nhiều task đọc, record và các thành phần bên trong phải bất biến hoặc được đồng bộ đúng cách. ScopedValue không biến một `ArrayList` thành immutable; nó chỉ cố định binding giữa key và object trong scope.

Không dùng context làm nơi lưu mutable accumulator, kết quả từng task hoặc trạng thái cần cập nhật. Hãy trả kết quả qua `Future`, record kết quả hoặc một abstraction đồng bộ phù hợp.

## 8. Thiết kế kiểm thử xử lý đồng thời

Một test đơn luồng chỉ chứng minh code đọc đúng context khi có một binding. Nó không chứng minh nhiều request đồng thời được cô lập. Bài lab sẽ kiểm tra các tình huống sau:

| Kiểm thử | Điều cần chứng minh |
|---|---|
| Không có binding | `isBound()` là false và `get()` báo lỗi |
| Call stack đồng bộ | Tầng sâu đọc được đúng request context |
| Nested scope | Context con có hiệu lực trong scope con; context cha được khôi phục |
| Exception | Binding được khôi phục dù operation thất bại |
| Executor boundary | Task executor không tự nhận binding của thread submit |
| Explicit propagation | Task đọc đúng context đã bind lại |
| Concurrent isolation | Nhiều task cùng chạy không đọc nhầm request ID hoặc tenant ID |
| Worker thread reuse | Scope kết thúc thì task tiếp theo không thấy binding cũ |

### 8.1. Dùng barrier để tăng khả năng tái hiện race

Nếu submit một task rồi đợi xong mới submit task kế tiếp, test không tạo được nhiều request hoạt động đồng thời. Dùng `CountDownLatch` để các task sẵn sàng trước, sau đó thả chúng cùng lúc.

Mỗi task có request ID và tenant ID riêng. Khi chạy, task đọc context và so sánh với context mong đợi. Nếu context bị chia sẻ sai, test sẽ thất bại.

### 8.2. Kiểm thử thread reuse

Dùng một single-thread executor để nhiều task lần lượt chạy trên cùng worker thread. Task đầu bind context rồi kết thúc; task kế tiếp kiểm tra `isBound()` phải là false. Điều này kiểm tra binding đã được khôi phục trước khi worker nhận task mới.

### 8.3. Không chỉ kiểm tra số lượng kết quả

Kết quả có đủ số dòng không chứng minh dữ liệu thuộc đúng request. Test phải xác minh quan hệ giữa request ID, tenant ID và kết quả trả về. Dùng map hoặc record expected theo từng task để đối chiếu chính xác.


## 9. Bài lab: triển khai và kiểm thử request context

### 9.1. Cấu trúc chương trình

Tạo file `ScopedRequestContextDemo.java`. Để bài lab tự chạy mà không cần thư viện test bên ngoài, chương trình dùng các hàm assertion nhỏ và ném `AssertionError` nếu điều kiện không đúng.

Code gồm:

- `RequestContext`: record bất biến chứa metadata của request.
- `RequestContextScope`: giữ key private, bind và đọc context.
- `OrderService` và `OrderRepository`: mô phỏng call stack nhiều tầng.
- Các test cho unbound, nested scope, exception, executor boundary, thread reuse và concurrent isolation.

### 9.2. Code hoàn chỉnh

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class ScopedRequestContextDemo {

    private record RequestContext(
            String requestId,
            String traceId,
            String tenantId,
            String principalId,
            Instant startedAt
    ) {
        RequestContext {
            Objects.requireNonNull(requestId, "requestId");
            Objects.requireNonNull(traceId, "traceId");
            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(principalId, "principalId");
            Objects.requireNonNull(startedAt, "startedAt");
        }
    }

    private static final class RequestContextScope {
        private static final ScopedValue<RequestContext> CURRENT =
            ScopedValue.newInstance();

        private RequestContextScope() {}

        static void runWith(RequestContext context, Runnable action) {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(action, "action");
            ScopedValue.where(CURRENT, context).run(action);
        }

        static <T> T callWith(
                RequestContext context,
                Callable<T> action
        ) throws Exception {
            Objects.requireNonNull(context, "context");
            Objects.requireNonNull(action, "action");
            return ScopedValue.where(CURRENT, context).call(action::call);
        }

        static RequestContext current() {
            return CURRENT.get();
        }

        static boolean isBound() {
            return CURRENT.isBound();
        }
    }

    private static final class OrderService {
        private final OrderRepository repository = new OrderRepository();

        String handle(String orderId) {
            return repository.load(orderId);
        }
    }

    private static final class OrderRepository {
        String load(String orderId) {
            RequestContext context = RequestContextScope.current();

            return "order=" + orderId
                + ";request=" + context.requestId()
                + ";tenant=" + context.tenantId()
                + ";trace=" + context.traceId();
        }
    }

    public static void main(String[] args) throws Exception {
        testUnboundBehavior();
        testCallStack();
        testNestedScopeAndException();
        testExecutorBoundaryAndThreadReuse();
        testConcurrentIsolation();

        check(!RequestContextScope.isBound(),
            "main thread must finish without a request binding");

        System.out.println("All ScopedValue tests passed.");
    }

    private static void testUnboundBehavior() {
        check(!RequestContextScope.isBound(), "initial state must be unbound");

        try {
            RequestContextScope.current();
            throw new AssertionError("get() should fail when unbound");
        } catch (NoSuchElementException expected) {
            // Expected: no context exists on this thread.
        }
    }

    private static void testCallStack() throws Exception {
        RequestContext context = context("req-sync", "tenant-blue");
        OrderService service = new OrderService();

        String result = RequestContextScope.callWith(
            context,
            () -> service.handle("order-17")
        );

        check(result.contains("request=req-sync"), "request ID missing");
        check(result.contains("tenant=tenant-blue"), "tenant ID missing");
        check(result.contains("trace=trace-req-sync"), "trace ID missing");
        check(!RequestContextScope.isBound(), "scope must end after call()");
    }

    private static void testNestedScopeAndException() throws Exception {
        RequestContext parent = context("req-parent", "tenant-a");
        RequestContext child = context("req-child", "tenant-a");

        RequestContextScope.callWith(parent, () -> {
            check(RequestContextScope.current().equals(parent),
                "parent context must be active");

            RequestContextScope.runWith(child, () ->
                check(RequestContextScope.current().equals(child),
                    "child context must be active")
            );

            check(RequestContextScope.current().equals(parent),
                "parent context must be restored after nested scope");

            try {
                RequestContextScope.runWith(child, () -> {
                    throw new IllegalStateException("expected test failure");
                });
                throw new AssertionError("exception was expected");
            } catch (IllegalStateException expected) {
                // Expected: nested scope exits exceptionally.
            }

            check(RequestContextScope.current().equals(parent),
                "parent context must be restored after exception");

            return null;
        });

        check(!RequestContextScope.isBound(),
            "parent binding must be cleared after outer call()");
    }

    private static void testExecutorBoundaryAndThreadReuse()
            throws Exception {
        RequestContext context = context("req-executor", "tenant-green");

        try (var executor = Executors.newSingleThreadExecutor()) {
            boolean inherited = RequestContextScope.callWith(context,
                () -> executor.submit((Callable<Boolean>) RequestContextScope::isBound)
                    .get(5, TimeUnit.SECONDS)
            );

            check(!inherited,
                "ordinary executor task must not inherit the caller binding");

            String requestId = executor.submit((Callable<String>) () ->
                RequestContextScope.callWith(context,
                    () -> RequestContextScope.current().requestId())
            ).get(5, TimeUnit.SECONDS);

            check(requestId.equals("req-executor"),
                "explicitly propagated context must be visible in task");

            boolean leaked = executor.submit((Callable<Boolean>) RequestContextScope::isBound)
                .get(5, TimeUnit.SECONDS);

            check(!leaked,
                "worker thread must not retain the previous task binding");
        }
    }

    private static void testConcurrentIsolation() throws Exception {
        final int taskCount = 200;
        CountDownLatch ready = new CountDownLatch(taskCount);
        CountDownLatch start = new CountDownLatch(1);

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> futures = new ArrayList<>();

            for (int i = 0; i < taskCount; i++) {
                final int taskId = i;
                RequestContext expected = context(
                    "req-" + taskId,
                    "tenant-" + (taskId % 7)
                );

                futures.add(executor.submit(() -> {
                    ready.countDown();

                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new TimeoutException("start barrier timed out");
                    }

                    return RequestContextScope.callWith(expected, () -> {
                        Thread.sleep(taskId % 5L);

                        RequestContext actual = RequestContextScope.current();
                        if (!actual.equals(expected)) {
                            throw new AssertionError(
                                "context crossed between concurrent tasks");
                        }

                        return actual.requestId() + "|" + actual.tenantId();
                    });
                }));
            }

            boolean allReady;
            try {
                allReady = ready.await(10, TimeUnit.SECONDS);
            } finally {
                // Always release tasks, including when the wait is interrupted.
                start.countDown();
            }

            check(allReady, "not all tasks reached the start barrier");

            Set<String> observed = new HashSet<>();
            for (Future<String> future : futures) {
                String result = future.get(10, TimeUnit.SECONDS);
                check(observed.add(result), "duplicate task context: " + result);
            }

            check(observed.size() == taskCount,
                "every task must return its own request and tenant");
        }
    }

    private static RequestContext context(
            String requestId,
            String tenantId
    ) {
        return new RequestContext(
            requestId,
            "trace-" + requestId,
            tenantId,
            "principal-" + requestId,
            Instant.now()
        );
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
```

### 9.3. Vì sao test executor có hai lần submit?

Test dùng một single-thread executor để tái sử dụng cùng worker thread:

1. Task đầu tiên được submit khi thread gọi đang bind context. Task executor kiểm tra `isBound()` và phải nhận `false`, vì binding không tự truyền sang executor.
2. Task tiếp theo bind snapshot bằng `callWith`, đọc đúng request ID rồi kết thúc.
3. Task thứ ba chạy trên worker thread đó và xác nhận `isBound()` lại là `false`.

Ba bước chứng minh context không tự truyền sang executor và binding không bị giữ lại sau khi task hoàn tất.

### 9.4. Vì sao dùng 200 task đồng thời?

Test concurrent tạo 200 virtual threads, mỗi task có request ID và tenant riêng. `CountDownLatch` giữ các task tại barrier cho đến khi gần như tất cả đã sẵn sàng; sau đó chúng được thả chạy đồng thời.

Mỗi task bind context riêng, đọc lại context sau một khoảng chờ ngắn và so sánh với giá trị mong đợi. Test cũng xác minh không có hai task trả về cùng cặp request/tenant.

Số lượng 200 chỉ là tải thử nghiệm nhỏ để tái hiện lỗi context propagation. Nó không phải benchmark năng lực tối đa của virtual threads.

## 10. Biên dịch và chạy trên JDK 25

`ScopedValue` đã permanent trong Java 25, do đó không cần bật preview.

```bash
javac --release 25 ScopedRequestContextDemo.java
java ScopedRequestContextDemo
```

Kết quả mong đợi:

```text
All ScopedValue tests passed.
```

Nếu dùng JDK 25 nhưng `javac` báo không tìm thấy `ScopedValue`, kiểm tra `java --version` và `javac --version`. Đảm bảo cả hai trỏ tới JDK 25 trở lên và IDE/build tool dùng đúng toolchain.

Không thêm `--enable-preview` chỉ để dùng ScopedValue. Preview flag chỉ cần cho các preview feature khác nếu dự án chủ động sử dụng chúng.

### 10.1. Chạy lặp để phát hiện lỗi không ổn định

Chạy chương trình nhiều lần trong môi trường CI hoặc local:

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  java ScopedRequestContextDemo || exit 1
done
```

Mỗi lần chạy tạo executor và request context mới. Nếu test thất bại không ổn định, lưu exception, stack trace và JDK build để tái hiện. Không tăng số task liên tục mà chưa hiểu giới hạn tài nguyên của máy test.

## 11. Đọc kết quả và mở rộng kiểm thử

### 11.1. Diễn giải test thành công

Khi chương trình in `All ScopedValue tests passed.`, các hành vi sau đã được kiểm tra trong phạm vi lab:

- Key chưa bind sẽ không đọc được bằng `get()`.
- Context đi theo call stack đồng bộ.
- Nested binding thay context trong scope con và khôi phục context cha.
- Exception không để binding tồn tại sau scope.
- Executor task không tự nhận binding của thread submit.
- Task được bind tường minh đọc đúng context.
- Worker thread được tái sử dụng không giữ binding cũ.
- 200 task đồng thời không đọc chéo request/tenant context.

Đây là kiểm thử logic của context scope. Nó chưa kiểm tra tracing framework, web framework, transaction manager hoặc tenant authorization thực tế.

### 11.2. Mở rộng với fixed thread pool

Có thể chạy test concurrent isolation trên fixed thread pool thay vì virtual-thread executor. Giữ nguyên cách bind context trong mỗi task. Mục tiêu là xác minh nhiều task chạy trên một nhóm worker thread vẫn không đọc nhầm context.

Không bỏ bước bind tường minh khi đổi executor. Cơ chế truyền context không tự thay đổi chỉ vì executor dùng platform threads hay virtual threads.

### 11.3. Thêm kiểm thử tenant isolation

Tạo các request thuộc hai tenant khác nhau và giả lập repository đọc tenant từ `RequestContextScope.current()`. Xác minh kết quả truy vấn luôn dùng tenant tương ứng với request.

Không chỉ kiểm tra log. Trong ứng dụng thật, tenant context thường tham gia quyết định dữ liệu được phép truy cập; cần test ở tầng repository/query hoặc authorization boundary để tránh rò rỉ dữ liệu giữa tenant.

### 11.4. Kiểm thử cancellation và timeout

Nếu task bất đồng bộ có thể bị hủy hoặc timeout, hãy kiểm tra:

- Task kết thúc do interrupt vẫn thoát khỏi binding.
- Kết quả muộn không được gắn nhầm vào request mới.
- Callback hoàn tất sau request có context snapshot riêng nếu cần.
- Error handler không đọc context của một operation khác.

ScopedValue tự khôi phục binding khi operation thoát; việc hủy task, timeout và xử lý kết quả vẫn thuộc trách nhiệm của executor/application logic.


## 12. ScopedValue và ThreadLocal: chọn đúng công cụ

### 12.1. Khác biệt về mô hình dữ liệu

`ThreadLocal` gắn một giá trị có thể thay đổi với thread. Code có thể gọi `set()` nhiều lần và phải tự gọi `remove()` khi kết thúc. `ScopedValue` gắn một giá trị trong phạm vi operation; code đọc binding nhưng không thay đổi binding tại chỗ.

| Tiêu chí | ThreadLocal | ScopedValue |
|---|---|---|
| Mục đích phù hợp | Trạng thái mutable riêng của thread | Truyền một chiều dữ liệu context xuống call stack |
| Thay đổi giá trị | Có thể gọi `set()` | Tạo nested binding mới |
| Kết thúc vòng đời | Tự cleanup, thường bằng `remove()` | Binding tự khôi phục khi `run()`/`call()` kết thúc |
| Nested operation | Phải tự lưu/khôi phục | Có rebinding và tự khôi phục binding trước |
| Truyền sang child thread | Phụ thuộc loại thread và cơ chế kế thừa | Tự động trong `StructuredTaskScope`; executor thông thường cần bind tường minh |
| Chia sẻ dữ liệu | Mỗi thread có value riêng | Mỗi thread có binding riêng; object nên immutable khi chia sẻ |

### 12.2. Không phải thay thế mọi ThreadLocal

ScopedValue phù hợp khi mục tiêu là truyền context bất biến như request ID, tenant ID, trace ID hoặc principal ID theo vòng đời operation.

ThreadLocal vẫn có thể phù hợp với trạng thái mutable thực sự gắn với thread và có lifecycle rõ ràng. Không thay đổi một ThreadLocal chỉ để chạy theo API mới nếu code đang cần mutable per-thread state; trước tiên hãy xác định semantics của dữ liệu.

### 12.3. Chuyển từ set/remove sang scope

Mô hình cũ:

```java
CURRENT_CONTEXT.set(context);
try {
    processRequest();
} finally {
    CURRENT_CONTEXT.remove();
}
```

Mô hình ScopedValue:

```java
RequestContextScope.runWith(context, () -> processRequest());
```

Cách viết mới giảm trách nhiệm cleanup thủ công. Nhưng nếu code cũ phụ thuộc vào việc thay đổi context giữa một operation, cần thiết kế lại bằng nested scope hoặc truyền tham số thay vì cố mô phỏng `set()`.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NoSuchElementException` từ `get()` | Code chạy ngoài scope hoặc task executor chưa bind context | Kiểm tra boundary; bind snapshot trong task |
| Context cha bị thay đổi sau operation con | Dùng object mutable hoặc tự lưu context vào biến dùng chung | Dùng record/collection bất biến và nested binding |
| Task executor không đọc thấy context | ScopedValue không tự truyền qua executor thông thường | Chụp context tại nơi submit và gọi `callWith`/`runWith` trong task |
| Task sau đọc nhầm context task trước | Dùng ThreadLocal hoặc cơ chế custom không cleanup | Dùng scope cho từng task và kiểm thử worker reuse |
| `currentOptional()` luôn rỗng | Boundary chưa bind hoặc context được tạo ở tầng sai | Bind tại điểm request đã xác thực |
| Tenant bị dùng sai | Lấy tenant từ input chưa xác minh hoặc context bị chia sẻ | Xác minh tenant ở boundary và kiểm thử tenant isolation |
| Context có dữ liệu thay đổi giữa các task | Record chứa collection/object mutable | Dùng dữ liệu immutable hoặc đồng bộ đầy đủ |
| Code compile cần preview flag | Đang dùng thêm preview API, chẳng hạn StructuredTaskScope của Java 25 | Tách API preview khỏi code dùng ScopedValue permanent |
| Context vẫn còn sau request | Scope không bao trùm đúng operation hoặc có callback chạy ngoài scope | Bind context snapshot riêng cho callback và kiểm thử lifecycle |

### 13.1. Không dùng orElse để che lỗi boundary

Nếu mọi đường xử lý của repository đều phải có request context, dùng `current()` để lỗi thiếu binding được phát hiện ngay. Dùng `currentOptional()` hoặc giá trị mặc định chỉ khi code thực sự được phép chạy ngoài request.

Nếu mặc định mọi request đều có tenant nhưng code dùng `orElse("default")`, một lỗi propagation có thể biến thành truy vấn nhầm tenant. Giá trị mặc định không được dùng để che lỗi bảo mật.

### 13.2. Không chia sẻ mutable object

Binding của ScopedValue không làm object trở thành immutable. Ví dụ record có field `List<String>` vẫn có thể chứa một list mutable. Nếu nhiều task đọc hoặc sửa list đó đồng thời, vẫn có data race.

Dùng `List.copyOf`, `Map.copyOf`, immutable value object hoặc cơ chế đồng bộ rõ ràng trước khi chia sẻ context giữa các thread.

### 13.3. Không để scope vượt quá vòng đời task

Với task được fork trong structured concurrency, scope cha phải còn sống cho tới khi child tasks hoàn tất. Với executor thông thường, bind riêng trong callable để vòng đời binding trùng với vòng đời task.

Không trả một callback đóng trên request context rồi lưu vào hàng đợi chạy vô thời hạn mà không xác định context snapshot và chính sách dữ liệu đi kèm.

## 14. Áp dụng trong dịch vụ thực tế

### 14.1. Ranh giới request

Tạo context tại nơi đã xác thực request, sau đó bind quanh application operation. Đừng để controller, repository hoặc client tự tạo context độc lập cho cùng request.

Nếu framework đã có cơ chế tracing hoặc request context, viết adapter ở boundary để ánh xạ dữ liệu cần thiết vào record. Tránh duy trì hai nguồn sự thật cho trace ID hoặc tenant ID.

### 14.2. Logging và tracing

Logging có thể đọc request ID/trace ID qua một helper lấy context hiện tại. Nếu logging framework cần MDC, hãy đồng bộ MDC trong boundary hoặc dùng integration chính thức của framework. ScopedValue không tự động ghi dữ liệu vào MDC.

Với tracing phân tán, ưu tiên API context propagation của tracing framework khi framework đã quản lý span và baggage. ScopedValue có thể là một phần adapter nội bộ, nhưng không tự thay thế W3C Trace Context hoặc giao thức truyền trace qua HTTP/message.

### 14.3. Message consumer và scheduled job

Message consumer hoặc scheduled job có thể chạy mà không có HTTP request. Có thể tạo một context nền riêng với job ID/message ID, sau đó bind trong phạm vi xử lý:

```java
RequestContext jobContext = new RequestContext(
    "job-" + job.id(),
    traceContext.traceId(),
    job.tenantId(),
    "system-worker",
    Instant.now()
);

RequestContextScope.runWith(jobContext, () -> jobProcessor.process(job));
```

Chỉ tạo tenant context sau khi xác minh quyền và nguồn của message. Một message chứa tenant ID không tự chứng minh producer được phép truy cập tenant đó.

### 14.4. Giới hạn hiệu năng

ScopedValue được thiết kế cho số lượng key tương đối nhỏ. Gom nhiều metadata vào một record thường giúp giữ số binding thấp và làm context dễ kiểm soát.

Không tuyên bố ScopedValue luôn nhanh hơn ThreadLocal cho mọi workload. Đo trên JDK, workload và concurrency thực tế của hệ thống. Virtual threads hướng tới tăng throughput cho nhiều tác vụ chờ I/O, không phải tăng tốc tính toán CPU-bound.

### 14.5. Bảo mật context

- Không lưu password, bearer token hoặc private key trong request context.
- Chỉ bind tenant/principal sau khi xác thực và authorization boundary.
- Giữ key ở private scope; hạn chế nơi có thể đọc context.
- Không ghi toàn bộ context vào log nếu có trường nhạy cảm.
- Không dùng context làm bằng chứng duy nhất cho quyền truy cập dữ liệu.
- Không chia sẻ mutable collection giữa các request.
- Xác minh callback, async task và message consumer có context snapshot đúng vòng đời.

## 15. Checklist nghiệm thu và tài liệu chính thức

### 15.1. Checklist thiết kế

- [ ] Chỉ đặt metadata xuyên suốt operation vào request context.
- [ ] Dùng record bất biến và kiểm tra các trường bắt buộc.
- [ ] Giữ key ScopedValue trong private static final field.
- [ ] Tạo context sau authentication/tenant validation.
- [ ] Dùng get ở code bắt buộc có context; chỉ dùng fallback khi hợp đồng cho phép.
- [ ] Không đưa credential hoặc mutable request object vào context.
- [ ] Dùng nested binding thay vì thay đổi object context dùng chung.

### 15.2. Checklist đồng thời

- [ ] Đã test binding không tồn tại và hành vi get khi unbound.
- [ ] Đã test nested scope khôi phục binding cha.
- [ ] Đã test exception không để binding rò rỉ.
- [ ] Đã xác minh executor task không tự nhận binding của caller.
- [ ] Đã bind snapshot tường minh trong từng async task.
- [ ] Đã test worker thread reuse.
- [ ] Đã test nhiều request với request ID và tenant ID khác nhau cùng lúc.
- [ ] Đã kiểm tra timeout, cancellation và callback chạy sau request.
- [ ] Context được chia sẻ giữa các task là immutable hoặc đồng bộ đúng cách.

### 15.3. Checklist triển khai

- [ ] Dùng JDK 25 trở lên; ScopedValue không cần preview flag.
- [ ] Không vô tình đưa StructuredTaskScope preview vào code production nếu chưa có quyết định dùng preview.
- [ ] Dùng virtual threads cho workload phù hợp, đặc biệt tác vụ blocking I/O.
- [ ] Giữ context propagation tracing theo chuẩn của framework.
- [ ] Có test tenant isolation ở tầng dữ liệu/authorization.
- [ ] Không log token, secret hoặc toàn bộ context nhạy cảm.
- [ ] Đo throughput, latency và memory trên workload thật trước khi kết luận hiệu năng.

### 15.4. Tài liệu tham khảo

- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): Scoped Values được hoàn thiện trong Java 25.
- [Java SE 25 — ScopedValue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): binding theo thread, nested rebinding, get, isBound, orElse và giới hạn inheritance.
- [Java SE 25 — ScopedValue.Carrier](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.Carrier.html): where, run, call và quy tắc khôi phục binding.
- [Oracle Java 25 — Scoped Values](https://docs.oracle.com/en/java/javase/25/core/scoped-values.html): hướng dẫn sử dụng Scoped Values trong core libraries.
- [Java SE 25 — Executors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): executor service, fixed thread pool và virtual-thread-per-task executor.
- [Java SE 25 — ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html): lifecycle, shutdown và close.
- [Oracle Java 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): mô hình virtual thread và cách dùng executor.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads được hoàn thiện trong JDK 21.
- [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái preview của Structured Concurrency trong Java 25.

*Phạm vi đối chiếu: 27/11/2026.* Scoped Values là tính năng permanent từ Java 25. Bài lab dùng `ExecutorService` và virtual threads đã ổn định; context được bind tường minh trong từng task. Tự động kế thừa binding qua `StructuredTaskScope` được ghi nhận như khả năng của API preview Java 25, không phải điều kiện để sử dụng ScopedValue trong luồng xử lý đồng bộ hoặc executor thông thường.


