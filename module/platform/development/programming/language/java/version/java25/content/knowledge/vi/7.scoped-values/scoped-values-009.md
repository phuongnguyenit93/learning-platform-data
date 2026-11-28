# Quan hệ giữa ScopedValue, virtual threads và phạm vi tác vụ có cấu trúc

> **Chương:** ScopedValue  
> **Phiên bản:** Java 25.  
> **Trọng tâm:** Truyền ngữ cảnh theo phạm vi động bằng `ScopedValue`, xử lý tác vụ bằng virtual threads và chia sẻ binding an toàn qua các tác vụ con thuộc `StructuredTaskScope`.

## 1. Ba cơ chế giải quyết ba vấn đề liên quan

Một request web có thể cần đọc hồ sơ, quyền truy cập và danh sách đơn hàng từ các dịch vụ khác nhau. Trong suốt quá trình xử lý, những tầng sâu trong call stack cần biết một số thông tin chung như tenant, user hoặc trace ID.

Có ba vấn đề riêng:

1. **Truyền ngữ cảnh:** Làm thế nào để một method sâu trong call stack biết tenant/user hiện tại mà không phải truyền thêm tham số qua hàng chục method trung gian?
2. **Thực thi đồng thời:** Làm thế nào chạy nhiều tác vụ I/O đồng thời với chi phí thread hợp lý?
3. **Quản lý vòng đời tác vụ:** Làm thế nào bảo đảm các tác vụ con kết thúc trước khi tác vụ cha rời khỏi phạm vi, đồng thời xử lý lỗi/hủy theo một đơn vị công việc?

Java có ba cơ chế liên quan:

| Cơ chế | Vai trò chính | Trạng thái trong Java 25 |
|---|---|---|
| `ScopedValue` | Truyền dữ liệu chỉ đọc theo phạm vi động trong call chain | **Chính thức**, JEP 506 |
| Virtual threads | Đại diện cho từng tác vụ bằng thread nhẹ, phù hợp công việc chờ I/O | **Chính thức** từ JDK 21, JEP 444 |
| `StructuredTaskScope` | Gom nhóm tác vụ con, quản lý join/cancel/lifetime | **Preview** trong JDK 25, JEP 505 |

Ba cơ chế bổ sung cho nhau nhưng không đồng nhất. `ScopedValue` không tạo thread; virtual thread không tự tạo quan hệ cha-con có cấu trúc; `StructuredTaskScope` cung cấp phạm vi tác vụ và cơ chế kế thừa binding của `ScopedValue` cho các thread được fork trong scope.

### Sơ đồ tổng quan

~~~mermaid
flowchart TD
    A["Request / tác vụ cha"] --> B["ScopedValue.where(REQUEST, context)"]
    B --> C["Call chain trên thread hiện tại"]
    C --> D["Mở StructuredTaskScope"]
    D --> E["fork task A"]
    D --> F["fork task B"]
    E --> G["Virtual thread A\nkế thừa ScopedValue binding"]
    F --> H["Virtual thread B\nkế thừa ScopedValue binding"]
    G --> I["join / tổng hợp kết quả"]
    H --> I
    I --> J["Đóng scope"]
    J --> K["Thoát binding ScopedValue"]
~~~

Sơ đồ cho thấy quan hệ trong trường hợp dùng `StructuredTaskScope`: binding được đặt ở thread cha trước khi mở scope, scope ghi nhận binding đó, các tác vụ con được fork kế thừa, và scope đợi các tác vụ kết thúc trước khi binding ở cha được khôi phục.

## 2. ScopedValue là gì?

`ScopedValue<T>` là một key cho phép chia sẻ một giá trị tới các method được gọi trực tiếp hoặc gián tiếp trong **phạm vi thực thi động**. Thay vì truyền dữ liệu qua từng tham số method, code có quyền truy cập key có thể đọc giá trị đang được bind.

Ví dụ:

~~~java
private static final ScopedValue<String> USER =
        ScopedValue.newInstance();

static void handleRequest() {
    System.out.println("user = " + USER.get());
}

public static void main(String[] args) {
    ScopedValue.where(USER, "alice").run(() -> handleRequest());
}
~~~

Khi chạy, `handleRequest()` đọc được `alice` dù không nhận tham số `user`. Binding chỉ tồn tại trong thời gian lambda của `run` được thực thi. Sau khi `run` hoàn thành, key trở lại trạng thái chưa bind (hoặc binding bên ngoài nếu đây là một phạm vi lồng nhau).

**ScopedValue đã là API chính thức trong JDK 25** (JEP 506). Không cần `--enable-preview` để sử dụng các API ổn định của `ScopedValue` như `newInstance()`, `where(...)`, `run(...)`, `call(...)`, `get()`, `isBound()`, `orElse(...)`.

### So sánh với ThreadLocal

| Đặc điểm | `ThreadLocal` | `ScopedValue` |
|---|---|---|
| Cách truyền | Theo thread hiện tại | Theo thread hiện tại trong một phạm vi động |
| Ai có thể thay giá trị? | Code có quyền truy cập có thể gọi `set()` | Caller thiết lập binding; callee đọc binding, không có API `set()` tương đương |
| Kết thúc phạm vi | Thường phải tự `remove()`/quản lý vòng đời | Tự khôi phục binding khi `run`/`call` kết thúc |
| Rebinding lồng nhau | Phải tự lưu/khôi phục | Có hỗ trợ phạm vi lồng nhau |
| Chia sẻ qua tác vụ con | Phụ thuộc loại thread và cơ chế kế thừa | Kế thừa có kiểm soát qua `StructuredTaskScope` |
| Phù hợp | Trạng thái theo thread, tích hợp thư viện cũ cần mutable thread state | Truyền một chiều dữ liệu context như tenant, user, trace metadata |

`ScopedValue` không phải bản thay thế cho mọi trường hợp dùng `ThreadLocal`. Nếu dữ liệu cần thay đổi tùy ý trong một thread hoặc một thư viện yêu cầu API `ThreadLocal`, hãy chọn công cụ phù hợp với hợp đồng đó. Khi mục tiêu chỉ là truyền context từ caller đến các method sâu hơn, `ScopedValue` thường có vòng đời rõ ràng và ít rủi ro quên dọn trạng thái hơn.

## 3. Khởi tạo key và thiết lập binding

Một key thường được khai báo là `private static final` để giới hạn nơi có thể đọc context:

~~~java
private static final ScopedValue<RequestContext> REQUEST =
        ScopedValue.newInstance();
~~~

Một key ban đầu chưa bind cho bất kỳ thread nào. Gọi `get()` khi chưa bind sẽ ném `NoSuchElementException`. Có thể kiểm tra bằng `isBound()`, dùng giá trị dự phòng qua `orElse(...)`, hoặc dùng `orElseThrow(...)`.

### 3.1. run() và call()

- `run(Runnable)`: dùng khi operation không trả kết quả.
- `call(CallableOp)`: dùng khi operation trả kết quả hoặc có thể ném exception.

~~~java
private static final ScopedValue<String> TRACE_ID =
        ScopedValue.newInstance();

static void logStart() {
    System.out.println("trace=" + TRACE_ID.get());
}

static String calculate() {
    return "processed:" + TRACE_ID.get();
}

static void runExample() {
    ScopedValue.where(TRACE_ID, "trace-001")
            .run(() -> logStart());
}

static String callExample() throws Exception {
    return ScopedValue.where(TRACE_ID, "trace-002")
            .call(() -> calculate());
}
~~~

Sau khi operation kết thúc bình thường hoặc bằng exception, binding được khôi phục tự động. Không cần gọi `remove()` như cách thường làm với `ThreadLocal`.

### 3.2. Đọc khi chưa bind

~~~java
if (TRACE_ID.isBound()) {
    System.out.println(TRACE_ID.get());
} else {
    System.out.println("no trace context");
}

String trace = TRACE_ID.orElse("no-trace");
~~~

Nếu context là bắt buộc, dùng `orElseThrow` để báo lỗi rõ ràng:

~~~java
RequestContext context = REQUEST.orElseThrow(
        () -> new IllegalStateException("request context is missing"));
~~~

Không nên thay mọi lần gọi `get()` bằng kiểm tra `isBound()` nếu ngữ cảnh bắt buộc phải có. Trong code xử lý request, việc thiếu context thường là lỗi cấu hình hoặc lỗi luồng gọi cần phát hiện sớm.

### 3.3. Binding lồng nhau (rebinding)

Một phạm vi con có thể bind cùng key với giá trị mới. Khi phạm vi con kết thúc, giá trị ở phạm vi cha được khôi phục:

~~~java
private static final ScopedValue<String> TENANT =
        ScopedValue.newInstance();

static void printTenant() {
    System.out.println(TENANT.get());
}

public static void main(String[] args) {
    ScopedValue.where(TENANT, "tenant-A").run(() -> {
        printTenant();

        ScopedValue.where(TENANT, "tenant-B").run(() -> {
            printTenant();
        });

        printTenant();
    });
}
~~~

Kết quả:

~~~text
tenant-A
tenant-B
tenant-A
~~~

Rebinding hữu ích khi xử lý một tác vụ con cần context khác, chẳng hạn chạy một bước giả lập tenant hoặc một phần công việc dưới quyền hạn đã giới hạn. Hãy giữ phạm vi ngắn và có chủ đích để người đọc hiểu rõ giá trị nào đang có hiệu lực.

## 4. Chọn giá trị context bất biến

Một `ScopedValue` bind một tham chiếu tới object. API không tự biến object đó thành immutable. Nếu cùng một context được nhiều tác vụ con đọc đồng thời, object nên bất biến; nếu có mutable state, mọi truy cập phải được đồng bộ đúng cách.

Ví dụ dùng record:

~~~java
record RequestContext(
        String requestId,
        String traceId,
        String tenantId,
        String userId) {
}
~~~

Khai báo key:

~~~java
private static final ScopedValue<RequestContext> REQUEST =
        ScopedValue.newInstance();
~~~

Binding:

~~~java
RequestContext context = new RequestContext(
        "req-1001",
        "trace-abc",
        "tenant-north",
        "user-42");

ScopedValue.where(REQUEST, context).run(() -> {
    service.handle();
});
~~~

Một record với các thành phần là kiểu immutable như `String` phù hợp cho ví dụ. Nếu record chứa `ArrayList`, `HashMap` hoặc object mutable khác, bản thân record chỉ bất biến nông; cần bảo vệ các thành phần đó hoặc chuyển thành cấu trúc immutable trước khi chia sẻ đồng thời.

**Không bind một đối tượng request mutable lớn vào context chỉ vì tiện.** Chỉ đưa dữ liệu cần thiết và không nhạy cảm vào key; giữ dữ liệu nghiệp vụ chính trong tham số method hoặc object chuyên trách.

## 5. Virtual threads: thread cho từng tác vụ

Virtual thread là một loại `java.lang.Thread` được JVM lập lịch, không chiếm một OS thread riêng trong toàn bộ vòng đời. Khi code thực hiện blocking I/O phù hợp, JVM có thể suspend virtual thread và giải phóng carrier thread cho tác vụ khác.

Virtual threads là tính năng chính thức từ JDK 21 (JEP 444), nên khi dùng JDK 25 không cần bật preview.

~~~java
Thread worker = Thread.ofVirtual().start(() -> {
    System.out.println(Thread.currentThread().isVirtual());
});

worker.join();
~~~

Một cách dùng theo mô hình một virtual thread cho mỗi task:

~~~java
try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
    Future<String> future = executor.submit(() -> fetchRemoteData());
    String result = future.get();
    System.out.println(result);
}
~~~

Virtual threads đặc biệt hữu ích cho ứng dụng có nhiều tác vụ chờ I/O như gọi HTTP, đọc dữ liệu hoặc truy vấn database. Chúng giúp tăng khả năng xử lý đồng thời và throughput; **không làm CPU-bound code chạy nhanh hơn** và không thay thế việc giới hạn tài nguyên như connection pool, rate limit hoặc semaphore.

### Virtual thread không tự động nhận ScopedValue binding

Binding của `ScopedValue` là **per-thread**. Tạo một virtual thread độc lập bằng `Thread.ofVirtual().start(...)` hoặc gửi task qua `Executors.newVirtualThreadPerTaskExecutor()` không đồng nghĩa binding của thread cha tự động được kế thừa.

Cơ chế kế thừa được tài liệu Java 25 xác định rõ cho trường hợp structured: khi dùng `StructuredTaskScope`, binding của thread mở scope được capture và kế thừa cho các thread được tạo qua `fork`. Với virtual thread độc lập, nếu cần context, hãy truyền context bất biến vào task rồi bind lại trong thread con.

Đây là điểm quan trọng khi chuyển từ ứng dụng một thread sang mô hình virtual thread. Đừng dựa vào `ScopedValue.get()` trong task con nếu bạn chưa xác định rõ cách binding đến thread đó.

## 6. Ví dụ ổn định: ScopedValue kết hợp virtual thread với binding tường minh

Ví dụ sau chỉ dùng API đã ổn định trong Java 25: `ScopedValue`, `Thread.ofVirtual`/virtual-thread executor và `ExecutorService`. Không cần `--enable-preview`.

Tạo file `ScopedValueVirtualThreadDemo.java`:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ScopedValueVirtualThreadDemo {

    private static final ScopedValue<RequestContext> REQUEST =
            ScopedValue.newInstance();

    record RequestContext(
            String traceId,
            String tenantId,
            String userId) {
    }

    static String downstreamService() {
        RequestContext context = REQUEST.get();

        return "trace=" + context.traceId()
                + ", tenant=" + context.tenantId()
                + ", user=" + context.userId()
                + ", virtual=" + Thread.currentThread().isVirtual();
    }

    static String process(RequestContext context) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {

            // Truyền snapshot context rõ ràng vào task.
            Future<String> future = executor.submit(() ->

                // Bind context trên chính virtual thread đang chạy task.
                ScopedValue.where(REQUEST, context)
                        .call(() -> downstreamService())
            );

            return future.get();
        }
    }

    public static void main(String[] args) throws Exception {
        var context = new RequestContext(
                "trace-001", "tenant-A", "user-42");

        System.out.println(process(context));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ScopedValueVirtualThreadDemo.java
java ScopedValueVirtualThreadDemo
~~~

Kết quả dự kiến:

~~~text
trace=trace-001, tenant=tenant-A, user=user-42, virtual=true
~~~

Luồng thực hiện:

1. Tác vụ caller có một object context bất biến.
2. Caller gửi context đó vào lambda của executor.
3. Executor tạo virtual thread cho task.
4. Trên virtual thread, task gọi `ScopedValue.where(REQUEST, context)` để thiết lập binding riêng.
5. Các method sâu hơn như `downstreamService()` đọc được context bằng `REQUEST.get()`.
6. Khi `call()` kết thúc, binding trên virtual thread được khôi phục; khi task hoàn thành, executor thu hồi vòng đời task.

**Tại sao phải bind lại?** Vì executor tạo virtual thread độc lập, không phải child thread được fork trong `StructuredTaskScope`. Ví dụ này là cách làm ổn định, tường minh và không phụ thuộc preview.

### Dùng Thread.ofVirtual() trực tiếp

Nếu chỉ có một task nhỏ, có thể truyền context vào closure rồi bind trong thread con:

~~~java
static void startWorker(RequestContext context) throws InterruptedException {
    Thread worker = Thread.ofVirtual().start(() ->
        ScopedValue.where(REQUEST, context).run(() -> {
            System.out.println(downstreamService());
        })
    );

    worker.join();
}
~~~

Phần cốt lõi vẫn giống nhau: task nhận context một cách tường minh và mở binding trên chính thread chạy task.

## 7. StructuredTaskScope: phạm vi tác vụ có cấu trúc

Structured concurrency xem một tác vụ cha và các tác vụ con liên quan như **một đơn vị công việc**. Tác vụ cha mở scope, fork các tác vụ con, join để đợi kết quả hoặc lỗi, rồi đóng scope. Vòng đời các tác vụ con được giới hạn bởi block của scope.

Trong JDK 25, `StructuredTaskScope` là **preview API** theo JEP 505 (fifth preview). Không được nhầm trạng thái của nó với `ScopedValue` và virtual threads:

- `ScopedValue`: API chính thức từ JDK 25.
- Virtual threads: API chính thức từ JDK 21.
- `StructuredTaskScope`: preview trong JDK 25; muốn thử phải bật preview ở compile và runtime.

Trong JDK 25, `StructuredTaskScope.open()` mặc định tạo scope dùng virtual thread cho mỗi task con được fork. Scope có owner thread; chỉ owner được gọi `fork`, `join`, `close`. `join()` đợi các task con hoàn tất hoặc scope bị hủy; `close()` bảo đảm các thread trong scope đã kết thúc trước khi luồng owner đi tiếp.

### Vì sao ScopedValue phù hợp với StructuredTaskScope?

Khi code thực thi `ScopedValue.where(...).call(...)` trên thread cha rồi mở `StructuredTaskScope` bên trong:

1. Scope capture các ScopedValue binding đang có ở thread cha khi scope được mở.
2. Mỗi lời gọi `fork(...)` tạo thread con trong scope và kế thừa các binding đã capture.
3. Code chạy trong các task con có thể gọi cùng key `ScopedValue.get()` để đọc context.
4. Scope không cho luồng cha rời `close()` cho tới khi các task con kết thúc, nên binding ở cha không bị khôi phục quá sớm trong khi task con vẫn chạy.
5. Nếu binding thay đổi không phù hợp giữa thời điểm mở scope và fork, API có thể phát hiện structure violation thay vì âm thầm truyền context sai.

~~~mermaid
sequenceDiagram
    participant P as Parent thread
    participant S as StructuredTaskScope
    participant V1 as Virtual thread task 1
    participant V2 as Virtual thread task 2

    P->>P: bind REQUEST = context
    P->>S: open() captures current bindings
    P->>S: fork(task 1)
    S->>V1: start child, inherit binding
    P->>S: fork(task 2)
    S->>V2: start child, inherit binding
    V1->>V1: REQUEST.get()
    V2->>V2: REQUEST.get()
    P->>S: join()
    S-->>P: all subtasks complete / failure
    P->>S: close()
    P->>P: return from ScopedValue scope
~~~

Đây là mối liên hệ đặc biệt giữa ba cơ chế: **ScopedValue mang context, StructuredTaskScope quản lý quan hệ tác vụ, và các task con mặc định chạy trên virtual threads**.

## 8. Ví dụ preview Java 25: truyền context vào các task con

Ví dụ này minh họa kế thừa binding tự động qua `StructuredTaskScope`. Nó **chỉ để thử nghiệm với JDK 25 preview**, không phải ví dụ dùng API stable-only.

Tạo file `ScopedValueStructuredScopePreview.java`:

~~~java
import java.util.concurrent.StructuredTaskScope;

public class ScopedValueStructuredScopePreview {

    private static final ScopedValue<RequestContext> REQUEST =
            ScopedValue.newInstance();

    record RequestContext(String tenantId, String userId) {}
    record Profile(String name) {}
    record Dashboard(Profile profile, String orderSummary) {}

    static Profile loadProfile(String userId) {
        var context = REQUEST.get();
        return new Profile("profile-" + userId + "@" + context.tenantId());
    }

    static String loadOrders(String userId) {
        var context = REQUEST.get();
        return "orders-for-" + userId + "@" + context.tenantId();
    }

    static Dashboard dashboard(RequestContext context) throws Exception {
        return ScopedValue.where(REQUEST, context).call(() -> {

            // Scope mở trong khi REQUEST đang được bind.
            try (var scope = StructuredTaskScope.open()) {

                var profile = scope.fork(
                        () -> loadProfile(REQUEST.get().userId()));

                var orders = scope.fork(
                        () -> loadOrders(REQUEST.get().userId()));

                // Đợi các task hoàn tất; lỗi task được phản ánh qua join().
                scope.join();

                return new Dashboard(profile.get(), orders.get());
            }
        });
    }

    public static void main(String[] args) throws Exception {
        var context = new RequestContext("tenant-A", "user-42");
        System.out.println(dashboard(context));
    }
}
~~~

Với JDK 25, biên dịch và chạy bằng preview flag:

~~~bash
javac --release 25 --enable-preview -d out ScopedValueStructuredScopePreview.java
java --enable-preview -cp out ScopedValueStructuredScopePreview
~~~

Kết quả minh họa:

~~~text
Dashboard[profile=Profile[name=profile-user-42@tenant-A], orderSummary=orders-for-user-42@tenant-A]
~~~

Ở ví dụ này:

- `REQUEST` được bind trên thread owner trước khi gọi `StructuredTaskScope.open()`.
- Scope capture binding `tenant-A/user-42`.
- Hai task con đọc cùng context qua `REQUEST.get()` mà không nhận tham số context riêng.
- Default scope của JDK 25 dùng virtual thread cho từng task.
- `join()` đợi task hoàn tất; `profile.get()` và `orders.get()` chỉ được đọc sau khi join thành công.
- Khi try-with-resources đóng scope rồi `call()` kết thúc, binding ở thread cha được khôi phục.

**Không mở scope trước khi bind context** nếu muốn các task con kế thừa context đó. Scope capture binding tại thời điểm mở; nếu bạn mở scope lúc chưa bind rồi mới bind sau, trạng thái tại lúc fork không khớp với trạng thái đã capture và có thể gây `StructureViolationException`.

### Xử lý lỗi và hủy

Default `StructuredTaskScope.open()` của JDK 25 đợi tất cả task thành công hoặc task đầu tiên thất bại. Khi một task lỗi, scope hủy các task còn lại bằng interrupt; `join()` ném `StructuredTaskScope.FailedException` với lỗi gốc làm cause.

Task con phải phản hồi interrupt và kết thúc sớm. Nếu task bị chặn trong một API không interruptible hoặc bỏ qua interrupt, `close()` có thể phải chờ lâu. Structured concurrency không biến mọi tác vụ thành có thể hủy tức thì.

## 9. Trạng thái preview và cách dùng an toàn

Bảng sau là điều cần nhớ khi làm dự án:

| API / tính năng | Trạng thái | Cách dùng |
|---|---|---|
| `ScopedValue` | Final trong JDK 25 (JEP 506) | Có thể dùng như API Java SE ổn định |
| Virtual threads | Final từ JDK 21 (JEP 444) | Có thể dùng trong production theo đặc tính tải và giới hạn tài nguyên |
| `StructuredTaskScope` | Preview trong JDK 25 (JEP 505, fifth preview) | Dùng thử nghiệm; cần `--enable-preview`, API có thể đổi |
| Kế thừa ScopedValue qua `StructuredTaskScope.fork` | Có trong API preview của JDK 25 | Chỉ dựa vào khi đã chấp nhận phụ thuộc preview |
| Kế thừa ScopedValue qua virtual thread thông thường | Không tự động | Truyền context rõ ràng và bind lại trong task |

JEP 525 tiếp tục đưa Structured Concurrency vào vòng preview tiếp theo. Vì API vẫn còn preview trong các bản phát triển tiếp sau, không nên xem `StructuredTaskScope` là một API đã ổn định cho codebase production chỉ vì nó có mặt trong JDK 25.

**Hướng đi an toàn cho ứng dụng cần API stable-only:**

- Dùng `ScopedValue` cho context trong từng call chain.
- Dùng virtual threads để thực thi tác vụ I/O độc lập.
- Truyền context bất biến qua tham số task, rồi bind bằng `ScopedValue.where(...)` ngay trong virtual thread con.
- Quản lý vòng đời task bằng API ổn định mà dự án đang dùng (ví dụ `ExecutorService` và `Future`), hoặc chờ structured concurrency được hoàn thiện trước khi phụ thuộc vào API preview.

Nếu nhóm chấp nhận preview trong môi trường thử nghiệm, hãy pin JDK cụ thể, bật preview đồng bộ ở compile/runtime, viết integration tests cho cancellation/interrupt/context inheritance và có kế hoạch nâng cấp khi API thay đổi.

## 10. Những giới hạn cần tránh

### 10.1. Không bind object mutable rồi chia sẻ đồng thời

`ScopedValue` không làm object được bind trở nên thread-safe. Nếu nhiều task con cùng sửa một `HashMap` trong context, vẫn có race condition. Dùng immutable record/collection hoặc cơ chế đồng bộ thích hợp.

### 10.2. Không coi ScopedValue như ThreadLocal có thể set tùy ý

`ScopedValue` hướng đến truyền dữ liệu một chiều từ caller tới callee. Nếu callee cần thay đổi context cho một đoạn lồng nhau, dùng rebinding trong phạm vi nhỏ. Nếu cần trạng thái mutable theo thread, đánh giá đúng use case của `ThreadLocal` hoặc truyền object trạng thái qua tham số.

### 10.3. Không mong virtual thread độc lập tự kế thừa binding

Đừng dựa vào việc thread cha đã bind context rồi tạo một virtual thread bất kỳ. Với virtual thread độc lập, hãy truyền context rõ ràng và bind lại. Kế thừa đặc biệt được đảm bảo trong mô hình `StructuredTaskScope` qua `fork`.

### 10.4. Không để task con sống ngoài phạm vi context

Với structured scope, đợi các task con hoàn tất trước khi thoát binding. Với executor thông thường, phải quản lý Future/lifecycle để task không tiếp tục dùng context sau khi request đã kết thúc. Nếu cần task nền sống độc lập với request, hãy tạo một context riêng cho task đó thay vì giữ tham chiếu vào request context đã hết hạn.

### 10.5. Không bind dữ liệu nhạy cảm một cách tùy tiện

Key `ScopedValue` là một capability: code có quyền truy cập key có thể đọc giá trị khi đang bind. Giữ key private trong class/nest phù hợp, không đặt secret/token hoặc dữ liệu nhạy cảm vào context nếu không cần. Không ghi toàn bộ context vào log.

## 11. Kiểm thử phạm vi và truyền context

Một bài test tốt nên kiểm tra cả trường hợp có binding, không có binding, nested rebinding và truyền sang task con.

Ví dụ JUnit 5 cho API ổn định `ScopedValue`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class ScopedValueTest {

    private static final ScopedValue<String> TENANT =
            ScopedValue.newInstance();

    @Test
    void bindingIsVisibleOnlyInsideDynamicScope() {
        assertFalse(TENANT.isBound());

        ScopedValue.where(TENANT, "tenant-A").run(() -> {
            assertTrue(TENANT.isBound());
            assertEquals("tenant-A", TENANT.get());
        });

        assertFalse(TENANT.isBound());
    }

    @Test
    void nestedBindingRestoresOuterValue() {
        ScopedValue.where(TENANT, "outer").run(() -> {
            assertEquals("outer", TENANT.get());

            ScopedValue.where(TENANT, "inner").run(() -> {
                assertEquals("inner", TENANT.get());
            });

            assertEquals("outer", TENANT.get());
        });
    }

    @Test
    void bindingIsRestoredWhenOperationThrows() {
        assertThrows(IllegalStateException.class, () ->
            ScopedValue.where(TENANT, "tenant-A").run(() -> {
                assertEquals("tenant-A", TENANT.get());
                throw new IllegalStateException("test failure");
            })
        );

        assertFalse(TENANT.isBound());
    }
}
~~~

Test này không cần preview flag. Với ứng dụng thật, bổ sung test cho:

- Context truyền vào virtual thread qua tham số task và bind lại đúng key.
- Nhiều task song song không đọc nhầm tenant/user của nhau.
- Giá trị context dùng chung là immutable hoặc được bảo vệ đúng cách.
- Nếu thử `StructuredTaskScope`, task con đọc được binding đã capture; scope join/close trước khi binding cha kết thúc.
- Task bị hủy phản hồi interrupt; lỗi gốc được truyền tới caller.

## 12. Ma trận lựa chọn theo tình huống

| Tình huống | Cách tiếp cận phù hợp | Lý do |
|---|---|---|
| Nhiều method đồng bộ cần đọc tenant/trace ID | `ScopedValue` | Truyền context theo dynamic scope, tự khôi phục binding |
| Server xử lý nhiều request chủ yếu chờ I/O | Virtual thread cho mỗi task + `ScopedValue` | Mỗi task có thread riêng, context được bind trong thread đó |
| Task cha fork nhiều tác vụ con và cần join/cancel cùng nhau | `StructuredTaskScope` (preview ở JDK 25) | Gom lifetime và xử lý lỗi thành một đơn vị |
| Virtual thread độc lập được tạo bởi executor | Capture context bất biến, truyền qua task và bind lại | Không có tự động inheritance như structured scope |
| Dữ liệu mutable cần giữ theo thread | Đánh giá `ThreadLocal` hoặc truyền object qua tham số | ScopedValue phù hợp hơn cho truyền một chiều, không phải mutable thread state |
| Tác vụ nền phải sống sau request | Tạo context độc lập cho background task | Không giữ binding/request context đã hết phạm vi |

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `NoSuchElementException` từ `ScopedValue.get()` | Key chưa bind trên thread hiện tại | Kiểm tra vị trí `where(...)`, dùng `isBound()` hoặc `orElseThrow()` theo hợp đồng |
| Thread cha đọc được nhưng virtual thread con không đọc được | Task con được tạo độc lập, không có binding tự động | Truyền context bất biến vào task và bind lại trong thread con |
| Task con của scope đọc được context cũ/không đúng | Mở scope ngoài phạm vi binding hoặc thay binding sau khi mở scope | Bind trước `StructuredTaskScope.open()`; giữ binding không đổi cho tới khi scope đóng |
| `StructureViolationException` khi fork | Binding tại thời điểm fork khác binding được capture lúc mở scope | Không thay đổi các binding đã capture giữa open và fork; mở scope bên trong đúng phạm vi |
| Preview API không biên dịch | Chưa bật preview hoặc compiler không đúng JDK 25 | Dùng `javac --release 25 --enable-preview` và runtime `java --enable-preview` |
| JDK khác báo API `StructuredTaskScope` thay đổi | API preview đã được sửa qua các release | Đọc Javadoc/JEP của đúng JDK, không sao chép code preview giữa các bản |
| Data race khi nhiều task đọc context | Object được bind chứa mutable state và bị sửa đồng thời | Dùng immutable value hoặc đồng bộ |
| Context biến mất trước khi task con hoàn tất | Scope/task không được join/close đúng vòng đời | Đợi tác vụ kết thúc trước khi rời phạm vi binding |
| ThreadLocal và ScopedValue cho kết quả khác nhau | Khác quy tắc binding/lifetime/inheritance | Kiểm tra API đang đọc và thread đang thực thi; không giả định hai loại tự đồng bộ |

## 14. Checklist thực hành

- [ ] Xác minh `java --version` và `javac --version` là JDK 25 khi chạy ví dụ.
- [ ] Khai báo key `ScopedValue` bằng `private static final` trong phạm vi truy cập phù hợp.
- [ ] Dùng `where(...).run(...)` hoặc `where(...).call(...)` để mở binding.
- [ ] Biết `get()` ném lỗi khi chưa bind và biết dùng `isBound()`/`orElse(...)`.
- [ ] Kiểm tra nested rebinding và tự khôi phục sau exception.
- [ ] Dùng object context immutable hoặc đồng bộ đúng khi chia sẻ.
- [ ] Hiểu binding per-thread và không mong virtual thread độc lập tự nhận context.
- [ ] Khi dùng virtual thread executor, truyền context tường minh và bind trong task.
- [ ] Hiểu scope capture binding lúc open và child task kế thừa binding qua fork.
- [ ] Ghi rõ `StructuredTaskScope` là preview trong JDK 25; chỉ bật preview cho bài thử nghiệm.
- [ ] Quản lý join/close, cancellation và interruption để task không sống ngoài phạm vi context.
- [ ] Không dùng request context đã hết hạn cho background task độc lập.

### Bài tập tổng hợp

Một request có `traceId`, `tenantId` và `userId`. Hãy xây dựng chương trình:

1. Định nghĩa `RequestContext` là record.
2. Khai báo một key `ScopedValue<RequestContext>`.
3. Tạo hàm `currentTenant()` chỉ đọc context qua `get()`.
4. Bind context quanh một service call và xác nhận nested scope khôi phục giá trị ban đầu.
5. Tạo hai virtual thread độc lập bằng `newVirtualThreadPerTaskExecutor()`; truyền context vào từng task và bind lại trong task.
6. Chứng minh hai task không đọc nhầm tenant của nhau.
7. Nếu bật preview, chuyển hai task thành `StructuredTaskScope.fork(...)`, mở scope bên trong binding, rồi xác nhận cả hai task đọc được cùng context mà không phải truyền context vào từng callable.
8. So sánh mã stable-only với mã preview và ghi lại các cờ build/run cần thiết.

## 15. Tài liệu chính thức

- [JEP 506 — Scoped Values](https://openjdk.org/jeps/506): trạng thái và thiết kế ScopedValue được hoàn thiện trong JDK 25.
- [Java SE 25 — ScopedValue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ScopedValue.html): binding per-thread, dynamic scope, rebinding, inheritance và API `get/where/run/call`.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads được hoàn thiện trong JDK 21.
- [Oracle Java 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): cách tạo virtual thread, executor và đặc tính tải.
- [JEP 505 — Structured Concurrency (Fifth Preview)](https://openjdk.org/jeps/505): trạng thái preview của Structured Concurrency trong JDK 25.
- [Java SE 25 — StructuredTaskScope API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/StructuredTaskScope.html): open/fork/join/close và quy tắc kế thừa ScopedValue.
- [JEP 525 — Structured Concurrency (Sixth Preview)](https://openjdk.org/jeps/525): vòng preview tiếp theo của Structured Concurrency; cần kiểm tra API theo đúng JDK mục tiêu.

> **Ghi nhớ:** `ScopedValue` mang context trong phạm vi động của một thread; virtual threads cung cấp thread nhẹ cho từng tác vụ; `StructuredTaskScope` (preview trong JDK 25) quản lý cây tác vụ con và cho phép chúng kế thừa binding đã capture. Với virtual thread độc lập, hãy truyền context tường minh rồi bind lại trong task.
