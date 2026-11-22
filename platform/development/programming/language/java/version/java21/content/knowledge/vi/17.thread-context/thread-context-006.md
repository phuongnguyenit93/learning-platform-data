# Truyền request context bằng tham số hoặc wrapper tường minh

Request context là tập thông tin đi cùng một request trong suốt quá trình xử lý, chẳng hạn request ID, tenant, người dùng đã xác thực, deadline, locale hoặc trace metadata. Khi một request chuyển qua service, executor, virtual thread hoặc `CompletableFuture`, các thông tin cần thiết phải tiếp tục đến đúng tác vụ.

Một cách rõ ràng để thực hiện việc đó là truyền context qua tham số phương thức hoặc đóng gói nó trong một `Runnable`/`Callable` wrapper. Cách làm này khiến luồng dữ liệu có thể nhìn thấy ngay trong chữ ký API, không phụ thuộc vào thread đang chạy task. Trong Java 21, đây là lựa chọn phù hợp khi muốn giữ request context nhất quán qua nhiều ranh giới thực thi.

## 1. Request context là gì?

Request context là dữ liệu mô tả môi trường của một request, không phải dữ liệu nghiệp vụ chính của request. Tùy ứng dụng, context có thể chứa:

- **Request ID hoặc correlation ID:** liên kết log và các thao tác phát sinh từ cùng một request.
- **Tenant ID:** xác định phạm vi dữ liệu của khách hàng trong hệ thống multi-tenant.
- **Principal hoặc subject ID:** định danh người dùng đã được xác thực.
- **Deadline:** thời điểm request cần hoàn tất hoặc dừng xử lý.
- **Locale hoặc timezone:** phục vụ định dạng và xử lý theo vùng.
- **Trace metadata:** thông tin cần thiết để liên kết các span hoặc bước xử lý.

Java 21 không định nghĩa một kiểu `RequestContext` dùng chung cho mọi ứng dụng. Đây thường là kiểu do ứng dụng tự thiết kế dựa trên dữ liệu thực sự cần truyền qua các tầng xử lý.

Context nên nhỏ, có ý nghĩa ổn định và chỉ chứa dữ liệu cần thiết. Không nên đưa toàn bộ HTTP request/response, connection, entity mutable lớn hoặc access token vào context chỉ để tiện truy cập ở mọi nơi.

## 2. Thiết kế RequestContext bất biến

Một `record` là cách phù hợp để biểu diễn context dạng dữ liệu. Các thành phần của record được khai báo `final`, accessor được sinh tự động và giá trị có thể được truyền qua nhiều tầng mà không cần setter.

```java
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

public record RequestContext(
        String requestId,
        String tenantId,
        String subjectId,
        Instant deadline,
        Map<String, String> attributes) {

    public RequestContext {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(subjectId, "subjectId");
        Objects.requireNonNull(deadline, "deadline");
        attributes = Map.copyOf(attributes);
    }
}
```

Compact constructor xác thực các thành phần bắt buộc và tạo bản sao không thể sửa đổi của `attributes`. `Instant` và `String` là các kiểu bất biến; việc sao chép map giúp tránh việc bên gọi sửa cấu trúc map sau khi context được tạo.

Record chỉ bất biến nông. Nếu context chứa một object mutable, tham chiếu đến object đó vẫn có thể được dùng để thay đổi trạng thái bên trong. Ưu tiên các kiểu bất biến, collection được sao chép hoặc giá trị đơn giản để context có thể được chia sẻ an toàn giữa các task.

Tạo context tại ranh giới tiếp nhận request, sau khi đã xác thực thông tin đáng tin cậy:

```java
RequestContext context = new RequestContext(
        validatedRequestId,
        authenticatedTenant.id(),
        authenticatedPrincipal.subjectId(),
        requestDeadline,
        Map.of("source", "web"));
```

Không lấy `tenantId` hoặc `subjectId` từ header do client tự khai báo rồi xem đó là danh tính đã xác thực. Hãy tạo context từ kết quả xác thực và phân quyền của hệ thống. Context giúp truyền thông tin, nhưng bản thân nó không thay thế kiểm tra authorization ở những thao tác cần bảo vệ.

## 3. Truyền context trực tiếp qua tham số phương thức

Cách đơn giản và minh bạch nhất là đưa context vào chữ ký của những phương thức cần nó:

```java
public OrderReceipt createOrder(
        RequestContext context,
        CreateOrderCommand command) {

    logger.info("Creating order requestId={} tenantId={}",
            context.requestId(), context.tenantId());

    return orderRepository.insert(
            context.tenantId(),
            context.subjectId(),
            command);
}
```

Caller nhìn thấy ngay phương thức cần những thông tin nào. Khi đọc code, có thể lần theo context từ điểm nhận request đến service, repository hoặc client bên ngoài.

Không nhất thiết truyền toàn bộ `RequestContext` đến mọi lớp. Nếu một lớp chỉ cần `tenantId`, hãy cân nhắc truyền riêng `tenantId`; nếu nhiều thao tác cần request ID, deadline và tenant cùng lúc, truyền context có thể giúp chữ ký gọn và thống nhất. Chọn mức trừu tượng theo trách nhiệm của từng lớp.

### Truyền context xuyên qua nhiều tầng

```java
public final class OrderService {
    private final InventoryService inventoryService;
    private final OrderRepository orderRepository;

    public OrderReceipt create(
            RequestContext context,
            CreateOrderCommand command) {

        inventoryService.checkAvailability(
                context.tenantId(), command.items());

        return orderRepository.save(context, command);
    }
}
```

Mỗi lời gọi thể hiện rõ phần context mà tầng tiếp theo cần. Nếu `InventoryService` chỉ cần tenant ID thì không cần nhận toàn bộ context; repository có thể nhận context nếu cần thêm request ID hoặc thông tin audit.

Ưu điểm của truyền tham số là dễ kiểm thử, dễ đọc, không phụ thuộc thread và không có trạng thái ẩn cần dọn dẹp. Nhược điểm là các phương thức cần context phải khai báo nó trong chữ ký; khi có quá nhiều tham số rời rạc, một record context có thể gom các metadata liên quan thành một đơn vị rõ ràng.

## 4. Truyền context qua executor bằng lambda

Khi submit một lambda, lambda có thể capture biến context từ phạm vi bên ngoài. Nếu context là bất biến, task có thể dùng cùng giá trị đó dù executor chạy task trên thread khác:

```java
Future<Report> future = executor.submit(
        () -> reportService.generate(context, reportId));
```

Đây là truyền context tường minh: lambda đóng gói tham chiếu đến `context`, còn service nhận context như một tham số thông thường. Không cần giả định worker thread đã kế thừa dữ liệu từ thread submit.

Khi dùng `CompletableFuture`, cần capture context ở từng stage cần nó:

```java
CompletableFuture<Invoice> invoice = CompletableFuture
        .supplyAsync(() -> invoiceService.load(context, invoiceId), executor)
        .thenApplyAsync(
                loaded -> invoiceService.enrich(context, loaded), executor);

CompletableFuture<InvoiceView> view = invoice.thenApply(
        loaded -> invoiceMapper.toView(context, loaded));
```

Các callback có thể chạy trên những thread khác nhau, tùy loại stage và executor. Context vẫn được truyền vì mỗi lambda giữ tham chiếu đến biến context đã capture. Với stage không có hậu tố `Async`, callback có thể chạy trên thread hoàn tất stage trước đó hoặc thread gọi; không nên dựa vào thread cụ thể để tìm request context.

## 5. Dùng wrapper Callable và Runnable

Khi cần áp dụng cùng một cách truyền context cho nhiều task, có thể tạo wrapper rõ ràng. Wrapper nhận context và một hành động có tham số context; khi executor chạy wrapper, nó gọi hành động với context đã đóng gói.

```java
import java.util.Objects;
import java.util.concurrent.Callable;

@FunctionalInterface
interface ContextCallable<V> {
    V call(RequestContext context) throws Exception;
}

final class ContextTasks {
    private ContextTasks() {
    }

    static <V> Callable<V> callable(
            RequestContext context,
            ContextCallable<V> action) {

        Objects.requireNonNull(context, "context");
        Objects.requireNonNull(action, "action");
        return () -> action.call(context);
    }
}
```

Sử dụng wrapper với `ExecutorService.submit()`:

```java
Future<Report> future = executor.submit(
        ContextTasks.callable(
                context,
                ctx -> reportService.generate(ctx, reportId)));
```

`ContextTasks.callable` trả về `Callable<Report>` chuẩn. Executor không cần biết `RequestContext`; context được chuyển vào hành động ngay bên trong wrapper.

Với task không trả kết quả, có thể tạo wrapper `Runnable` tương tự:

```java
import java.util.Objects;

@FunctionalInterface
interface ContextRunnable {
    void run(RequestContext context);
}

static Runnable contextualRunnable(
        RequestContext context,
        ContextRunnable action) {

    Objects.requireNonNull(context, "context");
    Objects.requireNonNull(action, "action");
    return () -> action.run(context);
}
```

Sử dụng:

```java
executor.execute(contextualRunnable(context, ctx -> {
    auditService.record(ctx.requestId(), "ORDER_CREATED");
}));
```

Wrapper không sửa thread, không ghi dữ liệu vào `ThreadLocal` và không yêu cầu executor đặc biệt. Nó chỉ gói context cùng hành động để việc truyền dữ liệu có thể nhìn thấy trong code.

## 6. Tạo ContextualExecutor cho API nội bộ

Nếu nhiều nơi trong ứng dụng cần submit task có context, có thể xây một adapter có API nhận context trực tiếp:

```java
import java.util.Objects;
import java.util.concurrent.Executor;
import java.util.function.Consumer;

public final class ContextualExecutor {
    private final Executor delegate;

    public ContextualExecutor(Executor delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    public void execute(
            RequestContext context,
            Consumer<RequestContext> action) {

        Objects.requireNonNull(context);
        Objects.requireNonNull(action);
        delegate.execute(() -> action.accept(context));
    }
}
```

Caller sử dụng:

```java
contextualExecutor.execute(context, ctx -> {
    notificationService.sendOrderCreated(ctx, orderId);
});
```

Adapter vẫn sử dụng executor được truyền vào để quyết định nơi chạy. Phần khác biệt là chữ ký `execute(context, action)` buộc caller cung cấp context ngay tại điểm submit.

Đây là API nội bộ của ứng dụng, không phải lớp thay thế cho `java.util.concurrent.Executor`. Khi cần kết quả hoặc checked exception, dùng wrapper `Callable` và `ExecutorService.submit()` thay vì ép mọi công việc vào `Consumer`/`Runnable`.

## 7. Truyền context qua nhiều ranh giới bất đồng bộ

Context phải được truyền ở mỗi lần tạo task mới. Nếu một task nhận context rồi submit task con, task con cũng cần nhận context tường minh:

```java
Future<?> parent = executor.submit(
        ContextTasks.callable(context, ctx -> {
            auditService.recordStarted(ctx.requestId());

            executor.execute(contextualRunnable(ctx, childContext -> {
                reportService.writeAuditFile(childContext, reportId);
            }));

            return null;
        }));
```

Task con không tự động lấy context từ worker chạy task cha. Wrapper đóng gói cùng context đã nhận ở task cha và chuyển tiếp nó sang task con.

Với pipeline `CompletableFuture`, hãy capture context trong từng callback cần dùng. Nếu tách một stage thành phương thức riêng, truyền context thành tham số của phương thức đó thay vì giả định stage mới chạy trên cùng thread.

## 8. Virtual thread không thay đổi nguyên tắc truyền context

Virtual thread là một `Thread`, nhưng task có thể được mount lên các carrier khác nhau trong suốt vòng đời. Context gắn với biến hoặc wrapper của task vẫn đi cùng task, không phụ thuộc carrier.

Ví dụ:

```java
Thread task = Thread.ofVirtual().start(() -> {
    orderService.create(context, command);
});

task.join();
```

Lambda capture context giống như khi dùng platform thread. Nếu virtual thread thực hiện thao tác blocking và unmount, tham chiếu đến context vẫn nằm trong trạng thái thực thi của virtual thread. Khi task tiếp tục trên carrier khác, nó vẫn dùng cùng context.

Với `Executors.newVirtualThreadPerTaskExecutor()`, mỗi task có thể chạy trên virtual thread riêng, nhưng executor không tự định nghĩa một request context của ứng dụng. Hãy truyền context vào task khi submit:

```java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<Result> future = executor.submit(
            ContextTasks.callable(context,
                    ctx -> service.process(ctx, input)));
    Result result = future.get();
}
```

## 9. So sánh truyền tham số, wrapper và ThreadLocal

| Cách làm | Context được lưu ở đâu? | Ưu điểm | Điểm cần chú ý |
|---|---|---|---|
| Tham số phương thức | Trong lời gọi và call stack | Rõ ràng, dễ kiểm thử, phụ thuộc ít | Chữ ký phương thức phải thể hiện context |
| Lambda capture | Trong closure của task | Ngắn gọn, tự nhiên với executor và future | Phải capture đúng context cho từng task |
| `Runnable`/`Callable` wrapper | Trong object task | Chuẩn hóa cách truyền qua executor | Phải tạo wrapper ở mọi ranh giới async |
| `ThreadLocal` | Gắn với thread hiện tại | Hữu ích khi tích hợp API yêu cầu ambient context | Executor tái sử dụng thread; cần quản lý set/remove và tránh rò rỉ giữa task |

`ThreadLocal` không tự biến thành request context theo task. Khi dùng thread pool, cùng một worker có thể chạy nhiều request nối tiếp; nếu không xóa giá trị đúng cách, request sau có thể nhìn thấy dữ liệu của request trước. Ngược lại, nếu task chuyển sang worker khác, dữ liệu `ThreadLocal` của worker ban đầu không tự đi theo task.

`InheritableThreadLocal` cũng không phải giải pháp tổng quát cho executor: giá trị được kế thừa khi tạo thread con, không phải mỗi lần submit task. Worker của thread pool thường được tạo một lần rồi tái sử dụng cho nhiều task. Với virtual thread, việc kế thừa khi tạo thread có thể diễn ra, nhưng điều đó vẫn không thay thế hợp đồng truyền context rõ ràng giữa các thành phần và các task lồng nhau.

Nếu một thư viện logging hoặc tracing yêu cầu ambient context, có thể cần adapter ở ranh giới tích hợp. Hãy giữ mô hình nghiệp vụ dựa trên tham số hoặc wrapper tường minh; adapter chịu trách nhiệm thiết lập và dọn dẹp context cho đúng phạm vi task, thay vì để mọi lớp tự đọc trạng thái ẩn.

## 10. Deadline và cancellation cần được truyền riêng

Có request ID trong context không có nghĩa task tự động bị hủy khi request gốc kết thúc. Tương tự, lưu deadline không tự đặt timeout cho các API gọi bên ngoài. Mỗi tầng cần sử dụng thông tin đó để áp dụng timeout phù hợp.

Ví dụ tính thời gian còn lại trước khi gọi một HTTP service:

```java
import java.time.Duration;
import java.time.Instant;

static Duration remaining(RequestContext context) {
    Duration duration = Duration.between(Instant.now(), context.deadline());
    if (duration.isNegative() || duration.isZero()) {
        throw new IllegalStateException("Request deadline has expired");
    }
    return duration;
}
```

Tầng gọi có thể dùng thời gian còn lại làm request timeout. Cần cân nhắc clock và deadline khi truyền giữa nhiều máy; với hệ thống phân tán, nên truyền deadline tuyệt đối hoặc ngân sách thời gian theo một quy ước rõ ràng, đồng thời dự phòng sai lệch đồng hồ.

Nếu cần hủy task, hãy dùng cơ chế cancellation phù hợp như `Future.cancel(true)`, interrupt hoặc API cancellation của thư viện. Context chỉ mang metadata và deadline; nó không tự interrupt thread hoặc hủy I/O.

## 11. Bảo mật và vòng đời context

Request context thường đi qua nhiều tầng, vì vậy cần giới hạn nội dung và thời gian sống:

- Chỉ đưa vào context các định danh và metadata thật sự cần thiết.
- Tạo tenant/principal từ thông tin đã xác thực; không tin giá trị do client tự gửi.
- Không lưu password, access token, session secret hoặc dữ liệu nhạy cảm không cần thiết.
- Không dùng context thay cho kiểm tra quyền ở thao tác đọc/ghi dữ liệu.
- Dùng collection bất biến hoặc defensive copy để tránh thay đổi sau khi submit task.
- Không giữ context lâu hơn task hoặc workflow cần nó; task bị treo có thể giữ toàn bộ object graph mà context tham chiếu.
- Khi log, ưu tiên request ID và định danh đã được phép ghi; tránh đưa payload nhạy cảm vào log.

Context có thể được chia sẻ giữa các task nếu bất biến. Nếu cần bổ sung metadata, tạo context mới thay vì sửa object dùng chung. Điều này giúp tránh race condition và làm rõ task nào nhận phiên bản context nào.

## 12. Kiểm thử việc truyền context

Kiểm thử nên xác nhận context đến đúng task, kể cả khi task chạy trên executor khác hoặc hoàn tất bất đồng bộ. Có thể dùng một context với request ID cố định và kiểm tra kết quả được tạo từ chính context đó.

```java
RequestContext context = new RequestContext(
        "req-123", "tenant-a", "user-7",
        Instant.now().plusSeconds(5), Map.of());

Future<String> future = executor.submit(
        ContextTasks.callable(context,
                ctx -> ctx.requestId() + ":" + ctx.tenantId()));

assertEquals("req-123:tenant-a", future.get());
```

Các trường hợp đáng kiểm tra:

1. Hai request đồng thời có request ID và tenant khác nhau, không bị trộn context.
2. Task con nhận đúng context của task cha đã submit.
3. Callback `CompletableFuture` dùng đúng context dù callback chạy trên thread khác.
4. Context không bị thay đổi sau khi task đã được submit.
5. Deadline hết hạn được xử lý rõ ràng ở tầng gọi I/O hoặc tầng nghiệp vụ.

## 13. Nguyên tắc thiết kế

1. Tạo context tại ranh giới request sau khi xác thực danh tính và tenant.
2. Dùng record hoặc kiểu bất biến để biểu diễn metadata cần chia sẻ.
3. Truyền context thành tham số ở các phương thức thực sự cần nó.
4. Dùng lambda capture hoặc `Runnable`/`Callable` wrapper để chuyển context qua executor.
5. Truyền lại context tường minh cho task con và từng callback bất đồng bộ.
6. Không giả định executor, platform thread hoặc virtual thread tự kế thừa request context theo từng task.
7. Giữ context nhỏ, tránh secret và không dùng nó thay cho authorization.
8. Truyền deadline và cancellation bằng cơ chế có hiệu lực; chỉ lưu metadata là chưa đủ.

## 14. Tổng kết

Truyền request context bằng tham số hoặc wrapper tường minh giúp dữ liệu request đi cùng tác vụ thay vì phụ thuộc vào thread đang chạy. Một `RequestContext` bất biến có thể được truyền qua chữ ký phương thức, capture trong lambda, đóng gói trong `Callable`/`Runnable` hoặc chuyển qua các stage của `CompletableFuture`.

Cách làm này hoạt động nhất quán với platform thread, executor và virtual thread vì context được gắn với task bằng tham chiếu rõ ràng. Hãy tạo context từ dữ liệu đáng tin cậy, giữ nó nhỏ và bất biến, truyền lại tại mọi ranh giới bất đồng bộ, đồng thời quản lý deadline, cancellation và bảo mật riêng. `ThreadLocal` vẫn có thể hữu ích ở ranh giới tích hợp cần ambient context, nhưng không nên là cơ chế ngầm duy nhất để truyền request context qua executor.

## Tài liệu tham khảo

- [Java SE 21 API — Executor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html) — hợp đồng thực thi task và ranh giới submit.
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) — submit, task lifecycle và quản lý executor.
- [Java SE 21 API — Callable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html) và [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html) — biểu diễn task có kết quả và quan sát completion.
- [Java SE 21 API — CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html) — truyền xử lý qua completion stages và executor.
- [Java SE 21 API — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html) — trạng thái gắn với thread và các lưu ý khi thread được tái sử dụng.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444) — mô hình thực thi virtual thread và sự khác biệt giữa task với carrier thread.
