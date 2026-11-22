# Kiểm thử rò rỉ trạng thái giữa các yêu cầu và tác vụ đồng thời

Trong **Dependency Injection (DI)**, một service có thể nhận repository, HTTP client hoặc bộ xử lý tác vụ qua constructor và được composition root hay DI container quản lý như một **singleton**. Điều đó giúp tránh khởi tạo hạ tầng lặp lại, nhưng không đồng nghĩa service được phép lưu **dữ liệu riêng của một request** trong field rồi dùng lại cho request khác.

Hãy tưởng tượng hai yêu cầu gần nhau: yêu cầu A thuộc tenant A, yêu cầu B thuộc tenant B. Service nhận A, lưu `currentTenant = "A"` vào field rồi tạo tác vụ bất đồng bộ. Trước khi tác vụ A chạy, service nhận B và đổi field thành `"B"`. Khi tác vụ A đọc field, nó có thể dùng tenant B. Lỗi này không được sửa chỉ bằng constructor injection hoặc bằng cách để container quản lý vòng đời service.

Bài học thuộc chương **Đồng thời và bất đồng bộ** của module **Dependency Injection / Inversion of Control (IoC)**. Trọng tâm là **kiểm thử có thể phát hiện rò rỉ trạng thái giữa các request, job và tác vụ đồng thời**, thay vì chỉ hy vọng stress test tình cờ tạo đúng lịch chạy gây lỗi. Ta sử dụng **Java 17 thuần**, sau đó liên hệ với request scope, provider, executor và lifecycle trong DI container.

Sau bài này, bạn có thể:

- Phân biệt trạng thái **dùng chung hợp lệ** và trạng thái **chỉ thuộc một yêu cầu**.
- Nhận diện các đường rò: field singleton, closure bất đồng bộ đọc field mutable, `ThreadLocal` không được dọn và sai lệch scope.
- Viết test **có kiểm soát thứ tự thực thi** để tái hiện lỗi mà không cần `Thread.sleep()`.
- Dùng `ExecutorService`, `CompletableFuture` và timeout để kiểm thử nhiều tác vụ thực tế nhưng không treo vô hạn.
- Kiểm tra ranh giới scope, việc dọn `ThreadLocal` và quyền sở hữu tài nguyên sau khi tác vụ hoàn thành.
- Thiết kế lại bằng request data bất biến, tham số tường minh, constructor injection và composition root phù hợp.
- Nêu giới hạn của các bài test: pass một lần không chứng minh chương trình hoàn toàn thread-safe.

## 1. Rò rỉ trạng thái nghĩa là gì?

Trong ngữ cảnh này, **rò rỉ trạng thái** xảy ra khi dữ liệu chỉ được phép ảnh hưởng đến request/tác vụ A lại được đọc, ghi hoặc sử dụng bởi request/tác vụ B ngoài phạm vi cho phép.

Ví dụ dữ liệu thường phải tách biệt:

- `tenantId` hoặc khóa phân vùng dữ liệu của từng yêu cầu.
- Thông tin xác thực, quyền truy cập và người dùng hiện tại.
- Request ID, correlation ID, locale hoặc timezone của một request.
- Bộ đệm kết quả, danh sách lỗi, tiến trình xử lý của từng job.
- Unit of work, session hoặc context đang quản lý entity mutable.
- Cấu hình tạm thời chỉ áp dụng cho một lượt thực thi.

**Không phải mọi chia sẻ đều sai.** Một `DataSource` hoặc HTTP client được thiết kế an toàn luồng có thể dùng chung; một cấu hình bất biến có thể được inject vào nhiều service. Vấn đề là đối tượng dùng chung giữ và thay đổi dữ liệu **có ranh giới sở hữu ngắn hơn** chính nó.

| Đối tượng/trạng thái | Phạm vi thường phù hợp | Lưu ý |
| --- | --- | --- |
| Cấu hình ứng dụng bất biến | Application scope | Không chứa dữ liệu thay đổi theo request |
| HTTP client có API hỗ trợ dùng chung | Application scope | Xác minh thread-safety và shutdown của implementation |
| `RequestContext` chứa tenant/request ID | Mỗi yêu cầu hoặc truyền dưới dạng giá trị | Không giữ target của request cũ trong singleton |
| `WorkUnit` giữ entity đang thay đổi | Mỗi đơn vị công việc | Có quy tắc commit/discard, không chia sẻ giữa tác vụ tùy ý |
| Bộ đệm kết quả của một lần xuất báo cáo | Mỗi job/lần gọi | Không đặt vào field singleton mà nhiều job cùng ghi |
| `ExecutorService` | Thường do application runtime sở hữu | Consumer sử dụng, owner chịu trách nhiệm shutdown |

**DI scope quyết định một dependency instance được cấp lại trong bao lâu.** Nó không tự quyết định dữ liệu nào được phép lưu trong field. Kể cả singleton có một field `final` trỏ đến một đối tượng mutable, nội dung của đối tượng ấy vẫn có thể bị sửa bởi nhiều lời gọi.

## 2. Đường rò phổ biến: một field chung cho nhiều request

Xem một service có xử lý bất đồng bộ:

~~~java
// Minh họa thiết kế lỗi, không phải chương trình độc lập.
final class UnsafeHandler {
    private final Executor executor;
    private String currentTenant;

    UnsafeHandler(Executor executor) {
        this.executor = executor;
    }

    CompletableFuture<String> handle(Request request) {
        currentTenant = request.tenantId();

        return CompletableFuture.supplyAsync(
                () -> "Tenant: " + currentTenant, executor);
    }
}
~~~

`currentTenant` là trạng thái của **lần gọi hiện tại** nhưng lại được lưu trên **instance service**. Nếu instance ấy được dùng chung, một lần gọi khác có thể ghi đè nó trước khi lambda thực thi.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant S as Singleton service
    participant Q as Executor queue
    participant B as Request B
    A->>S: handle(A)
    S->>S: currentTenant = A
    S->>Q: enqueue task A
    B->>S: handle(B)
    S->>S: currentTenant = B
    S->>Q: enqueue task B
    Q->>S: task A đọc currentTenant
    Note over S: Có thể nhận B thay vì A
    Q->>S: task B đọc currentTenant
~~~

Trong Java, tác vụ có thể chạy **sớm, muộn hoặc đồng thời** tùy executor. Vì vậy lỗi dễ “biến mất” khi debug hoặc khi test chỉ gửi một request mỗi lần.

### Vì sao `volatile` hoặc `synchronized` chưa chắc sửa đúng vấn đề?

- Đặt `volatile` cho `currentTenant` giải quyết một phần **khả năng nhìn thấy giá trị giữa các thread**, nhưng không biến một field chung thành dữ liệu riêng của từng request. Sau khi B ghi đè, A vẫn có thể đọc B.
- `AtomicReference<String>` bảo đảm những thao tác trên tham chiếu theo quy tắc nguyên tử/visibility, nhưng **không tạo isolation theo request**.
- `synchronized` quanh đúng thao tác gán field cũng không đủ nếu lambda đọc field **sau khi đã nhả khóa**.
- Khóa bao toàn bộ chuỗi xử lý (kể cả chờ tác vụ) đôi khi tuần tự hóa mọi yêu cầu, làm mất khả năng đồng thời và có nguy cơ deadlock. Đây không phải cách mặc định để chữa một thiết kế scope sai.

**Cách sửa tốt hơn** khi tenant ID chỉ là dữ liệu đầu vào: truyền hoặc chụp nó thành **biến cục bộ bất biến cho từng tác vụ**, để lambda không đọc lại một field chung.

~~~java
// Minh họa cách an toàn hơn về ranh giới dữ liệu.
CompletableFuture<String> handle(Request request) {
    String tenantId = request.tenantId();
    return CompletableFuture.supplyAsync(
            () -> "Tenant: " + tenantId, executor);
}
~~~

Biến `tenantId` được capture cho lời gọi này. Nó không đổi khi service nhận một request khác. Tuy nhiên, nếu lambda capture một **object mutable** rồi object bị request khác sửa, vẫn có thể rò; cần xem tính bất biến và ownership của toàn bộ dữ liệu được capture.

## 3. Kiểm thử race condition: điều khiển lịch chạy, không dựa vào may mắn

Một test thường gặp là mở nhiều thread và chạy hàng nghìn lần, sau đó kiểm tra kết quả. Nó có thể phát hiện lỗi nhưng có hạn chế:

- Nếu lịch chạy không tạo đúng đoạn giao nhau, test pass dù code có lỗi.
- Nếu dùng `Thread.sleep(100)`, kết quả phụ thuộc tốc độ máy, CPU, debugger và CI.
- Lỗi xuất hiện một lần sau hàng nghìn lần dễ khó tái hiện.
- Nếu test không đặt timeout, một task bị kẹt có thể làm pipeline treo.

Nên kết hợp hai nhóm:

1. **Kiểm thử interleaving có chủ đích:** buộc thứ tự A ghi → B ghi → task A đọc. Một executor hàng đợi điều khiển thủ công hoặc `CountDownLatch`/`CyclicBarrier` có thể giúp tạo lịch chạy mong muốn.
2. **Kiểm thử đồng thời thực tế:** dùng `ExecutorService` để chạy nhiều tác vụ, xác minh kết quả, giới hạn thời gian và shutdown tài nguyên. Đây là phép bổ sung, không thay thế test lịch chạy xác định.

### Một lịch chạy đủ để chứng minh bug

~~~text
Bước 1: handle(A) cập nhật field = "TENANT-A" và xếp task A.
Bước 2: handle(B) cập nhật field = "TENANT-B" và xếp task B.
Bước 3: Executor mới cho task A thực thi.
Bước 4: Task A đọc field = "TENANT-B"  -> RÒ RỈ.
~~~

Ta không cần “hy vọng” hai thread đua nhau đúng thời điểm. Chỉ cần chứng minh **có một lịch chạy hợp lệ** khiến code vi phạm hợp đồng. Test có kiểm soát nên cố ý tạo đúng lịch đó.

Với các lỗi liên quan bộ nhớ/visibility thật sự, còn phải dùng công cụ và kỹ thuật kiểm thử đồng thời chuyên biệt. Một executor thủ công giúp tái hiện **lỗi truy cập trạng thái sai thời điểm**, nhưng **không mô phỏng mô hình bộ nhớ của nhiều thread**.

## 4. Thực hành Java 17: tái hiện rò rỉ bất đồng bộ một cách xác định

Chương trình dưới đây chạy với **Java 17+**, không cần framework hay thư viện ngoài. Nó có:

- `TenantRequest` và `TenantResponse` là các `record` bất biến.
- `LeakyAsyncHandler` — service có một field `currentTenant` bị ghi đè.
- `IsolatedAsyncHandler` — không giữ trạng thái theo request trong field.
- `QueuedExecutor` — lưu các task vào hàng đợi, chỉ thực thi khi được yêu cầu; công cụ này **minh họa lịch chạy**, không tạo nhiều thread.
- `TenantScope` — minh họa cách đặt và dọn context trong `ThreadLocal` khi thật sự cần bridge tới API theo thread.

Lưu toàn bộ đoạn sau vào `Main.java`:

~~~java
import java.util.ArrayDeque;
import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.function.Supplier;

record TenantRequest(String requestId, String tenantId) {
    TenantRequest {
        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException("Invalid requestId");
        }
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
    }
}

record TenantResponse(String requestId, String tenantId) {}

// Cùng hợp đồng cho implementation lỗi và implementation đúng.
interface AsyncTenantHandler {
    CompletableFuture<TenantResponse> handle(TenantRequest request);
}

// Chỉ phục vụ thử nghiệm: lưu task, điều khiển khi nào chạy.
final class QueuedExecutor implements Executor {
    private final Queue<Runnable> queued = new ArrayDeque<>();

    @Override
    public void execute(Runnable command) {
        queued.add(Objects.requireNonNull(command, "command"));
    }

    void runAll() {
        while (!queued.isEmpty()) {
            queued.remove().run();
        }
    }
}

// Sai: dữ liệu của request được giữ trong field dùng chung.
final class LeakyAsyncHandler implements AsyncTenantHandler {
    private final Executor executor;
    private String currentTenant;

    LeakyAsyncHandler(Executor executor) {
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    @Override
    public CompletableFuture<TenantResponse> handle(TenantRequest request) {
        Objects.requireNonNull(request, "request");
        currentTenant = request.tenantId();

        return CompletableFuture.supplyAsync(
                () -> new TenantResponse(
                        request.requestId(), currentTenant),
                executor);
    }
}

// Đúng với bài toán này: mỗi task đọc dữ liệu của chính request.
final class IsolatedAsyncHandler implements AsyncTenantHandler {
    private final Executor executor;

    IsolatedAsyncHandler(Executor executor) {
        this.executor = Objects.requireNonNull(executor, "executor");
    }

    @Override
    public CompletableFuture<TenantResponse> handle(TenantRequest request) {
        TenantRequest snapshot =
                Objects.requireNonNull(request, "request");

        return CompletableFuture.supplyAsync(
                () -> new TenantResponse(
                        snapshot.requestId(), snapshot.tenantId()),
                executor);
    }
}

// Context theo thread: chỉ nên dùng khi có lý do và cleanup chặt.
final class TenantScope {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantScope() {}

    static String current() {
        return CURRENT.get();
    }

    static <T> T run(String tenantId, Supplier<T> action) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        Objects.requireNonNull(action, "action");

        String previous = CURRENT.get();
        CURRENT.set(tenantId);
        try {
            return action.get();
        } finally {
            // Hỗ trợ nested scope; scope ngoài được phục hồi.
            if (previous == null) {
                CURRENT.remove();
            } else {
                CURRENT.set(previous);
            }
        }
    }
}

// Composition root cho chương trình minh họa.
public class Main {
    public static void main(String[] args) {
        TenantRequest a = new TenantRequest("REQ-A", "TENANT-A");
        TenantRequest b = new TenantRequest("REQ-B", "TENANT-B");

        QueuedExecutor queue = new QueuedExecutor();
        AsyncTenantHandler unsafe = new LeakyAsyncHandler(queue);

        CompletableFuture<TenantResponse> unsafeA = unsafe.handle(a);
        CompletableFuture<TenantResponse> unsafeB = unsafe.handle(b);

        // Cả A và B được nhận trước khi bất kỳ task nào chạy.
        queue.runAll();

        System.out.println("Unsafe A: " + unsafeA.join().tenantId());
        System.out.println("Unsafe B: " + unsafeB.join().tenantId());

        AsyncTenantHandler safe = new IsolatedAsyncHandler(queue);

        CompletableFuture<TenantResponse> safeA = safe.handle(a);
        CompletableFuture<TenantResponse> safeB = safe.handle(b);
        queue.runAll();

        System.out.println("Safe A: " + safeA.join().tenantId());
        System.out.println("Safe B: " + safeB.join().tenantId());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Main.java
java Main
~~~

Kết quả dự kiến:

~~~text
Unsafe A: TENANT-B
Unsafe B: TENANT-B
Safe A: TENANT-A
Safe B: TENANT-B
~~~

### Đọc đúng ý nghĩa của thí nghiệm

1. Composition root inject cùng một `QueuedExecutor` vào hai handler để chủ động điều khiển thời điểm chạy.
2. `LeakyAsyncHandler.handle(a)` ghi field `currentTenant = "TENANT-A"` và tạo một future chưa hoàn thành.
3. `handle(b)` ghi đè `currentTenant = "TENANT-B"` trước khi task A được chạy.
4. Khi `runAll()` thực thi các task, cả hai lambda của handler lỗi đều đọc field hiện có là `"TENANT-B"`.
5. Handler an toàn capture một `TenantRequest` bất biến riêng cho mỗi lời gọi. Khi chạy task A, nó đọc lại dữ liệu của A thay vì dữ liệu trong field chia sẻ.

**Quan trọng:** `QueuedExecutor` thực thi trên thread gọi `runAll()`, nên đây là **kiểm thử interleaving bất đồng bộ có tính xác định**, không phải kiểm thử tác vụ chạy đồng thời trên hai CPU. Ta sẽ bổ sung test với pool thực ở phần sau.

### Vì sao cùng một singleton handler có thể an toàn?

`IsolatedAsyncHandler` chỉ giữ `executor` trong field `final`. Executor là collaborator dùng chung do composition root sở hữu; request data được truyền dưới dạng giá trị bất biến. Vì vậy nhiều request có thể dùng **cùng instance handler** mà không cần một handler riêng cho mỗi request, miễn các collaborator được dùng theo đúng hợp đồng và thread-safe.

**Constructor injection không tự làm service thread-safe**. Nó chỉ giúp dependency và ownership rõ ràng. Quyết định giữ state ở field, cache, static variable hoặc context phải được đánh giá riêng.

## 5. Kiểm thử đồng thời thật bằng ExecutorService và Future

Một bước tiếp theo là dùng pool với nhiều worker để kiểm tra service dưới tải đồng thời **mà vẫn có giới hạn thời gian**. Đối với handler an toàn, ta có thể gửi nhiều request có tenant khác nhau và kiểm tra mỗi kết quả chỉ chứa tenant của request tương ứng.

Những quy tắc quan trọng khi viết test:

- Pool phải có đủ thread để những tác vụ cần chạy đồng thời có thể tiến triển.
- Mỗi yêu cầu có ID độc lập và kết quả được đối chiếu bằng ID/tenant, không dựa vào thứ tự hoàn thành.
- Dùng `CompletableFuture.allOf(...).get(timeout, unit)` hoặc `Future.get(timeout, unit)` để test không chờ vô hạn.
- **Không khẳng định test pass một lần là đã chứng minh không có mọi data race.** Kết hợp kiểm thử lịch chạy cố định và các bài test áp lực/quan sát production.
- Dùng `finally` để gọi `shutdownNow()` hoặc quy trình dừng thích hợp, và kiểm tra worker đã kết thúc; không để thread pool sống sau test.

Đối với một rò rỉ có thể tái hiện bằng lịch chạy, test với hàng đợi **mạnh hơn stress test may rủi** vì nó kiểm tra đúng trường hợp vi phạm. Đối với tính an toàn của các cấu trúc dùng chung (map/cache/counter), cần test đồng thời thật và phân tích JMM/happens-before tương ứng.

## 6. ThreadLocal: thread không phải request

`ThreadLocal<T>` cung cấp một giá trị riêng **cho từng thread**, không phải một giá trị tự động riêng cho mỗi request hay mỗi task. Trong server dùng thread pool, cùng một worker thread có thể xử lý request A rồi request B.

~~~text
Worker-1:
  Task A -> TenantContext.set("TENANT-A")
  Task A kết thúc nhưng quên remove()
  Task B -> TenantContext.get() = "TENANT-A"  (rò context cũ)
~~~

Nếu `Task B` không thiết lập context trước khi dùng, nó có thể lấy dữ liệu của task A. Đây là kiểu **rò rỉ do tái sử dụng thread**, khác với field singleton ở phần trước nhưng có cùng hệ quả: lẫn dữ liệu giữa các request.

### Cleanup bằng `try/finally` và hỗ trợ scope lồng nhau

`TenantScope.run(...)` trong chương trình Java đầy đủ làm ba việc:

1. Lưu giá trị hiện tại trên thread (nếu có).
2. Đặt tenant của tác vụ, thực thi callback.
3. **Trong `finally`**, khôi phục giá trị ngoài nếu đang có scope lồng nhau; nếu không có, gọi `remove()`.

Đây là ví dụ về cleanup **trên cùng thread**. Nó không truyền context sang thread khác. Nếu một task bên trong `TenantScope.run(...)` dùng `CompletableFuture.supplyAsync(...)`, callback có thể chạy ở worker khác, nơi `TenantScope.current()` chưa được đặt. Ngược lại, nếu chỉ `set` trên worker mà không `remove`, giá trị cũ có thể lọt sang task sau.

### Nên ưu tiên truyền dữ liệu tường minh khi có thể

~~~java
// Tách request data khỏi ambient state.
record RequestContext(String requestId, String tenantId) {}

CompletableFuture<Result> submit(
        RequestContext context,
        Executor executor) {
    return CompletableFuture.supplyAsync(
            () -> process(context), executor);
}
~~~

Đoạn trên là mã minh họa, `Result` và `process` chưa được định nghĩa. Ý tưởng là **capture dữ liệu bất biến được cấp rõ ràng** thay vì dựa vào một `ThreadLocal` “tự có” trong mọi thread.

Truyền qua tham số đặc biệt hữu ích với tenant, authorization context và correlation ID. Nếu framework tự truyền security/request context, cần biết **cơ chế propagation cụ thể**, giới hạn khi chạy async và thời điểm cleanup; không được mặc định context của HTTP thread sẽ tự đi theo mọi future hoặc executor.

## 7. Bài kiểm thử tổng hợp: interleaving, thread pool và cleanup

Tạo `StateIsolationTest.java` cạnh `Main.java` của phần 4. Bài test dùng ba kỹ thuật:

- Hàng đợi có kiểm soát để **chứng minh handler lỗi có đường rò** và handler an toàn không mắc lỗi trên cùng lịch chạy.
- Pool bốn worker để **kiểm tra kết quả của nhiều tác vụ chạy thật**.
- Pool một worker để **chứng minh `ThreadLocal` chưa cleanup có thể bị tái sử dụng**, rồi kiểm tra wrapper cleanup đúng.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.Future;

public class StateIsolationTest {
    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static void controlledInterleaving() {
        TenantRequest a = new TenantRequest("A", "TENANT-A");
        TenantRequest b = new TenantRequest("B", "TENANT-B");
        QueuedExecutor queue = new QueuedExecutor();

        LeakyAsyncHandler broken = new LeakyAsyncHandler(queue);
        CompletableFuture<TenantResponse> badA = broken.handle(a);
        CompletableFuture<TenantResponse> badB = broken.handle(b);
        queue.runAll();

        check(badA.join().tenantId().equals("TENANT-B"),
                "Broken handler must expose the forced interleaving");
        check(badB.join().tenantId().equals("TENANT-B"),
                "Second request has set the shared field");

        IsolatedAsyncHandler safe = new IsolatedAsyncHandler(queue);
        CompletableFuture<TenantResponse> goodA = safe.handle(a);
        CompletableFuture<TenantResponse> goodB = safe.handle(b);
        queue.runAll();

        check(goodA.join().tenantId().equals("TENANT-A"),
                "Safe handler must preserve A context");
        check(goodB.join().tenantId().equals("TENANT-B"),
                "Safe handler must preserve B context");
    }

    private static void realConcurrentTasks() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            IsolatedAsyncHandler handler = new IsolatedAsyncHandler(pool);
            List<CompletableFuture<TenantResponse>> tasks =
                    new ArrayList<>();

            for (int i = 0; i < 200; i++) {
                TenantRequest expected = new TenantRequest(
                        "REQUEST-" + i, "TENANT-" + (i % 7));

                CompletableFuture<TenantResponse> checked =
                        handler.handle(expected).thenApply(actual -> {
                            check(actual.requestId().equals(
                                    expected.requestId()),
                                    "Request ID changed");
                            check(actual.tenantId().equals(
                                    expected.tenantId()),
                                    "Tenant leaked across tasks");
                            return actual;
                        });
                tasks.add(checked);
            }

            CompletableFuture.allOf(
                    tasks.toArray(new CompletableFuture<?>[0]))
                    .get(10, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
            check(pool.awaitTermination(10, TimeUnit.SECONDS),
                    "Pool must terminate");
        }
    }

    private static void threadLocalReuse() throws Exception {
        // Một worker bảo đảm task thứ hai tái sử dụng cùng thread.
        ExecutorService one = Executors.newSingleThreadExecutor();
        ThreadLocal<String> forgotten = new ThreadLocal<>();

        try {
            one.submit(() -> {
                forgotten.set("TENANT-OLD");
            }).get(10, TimeUnit.SECONDS);

            Future<String> leaked = one.submit(forgotten::get);
            check("TENANT-OLD".equals(
                    leaked.get(10, TimeUnit.SECONDS)),
                    "Undeleted ThreadLocal must be visible in next task");

            // Test tự dọn context cố ý tạo ra ở trên.
            one.submit(forgotten::remove)
                    .get(10, TimeUnit.SECONDS);

            Future<String> inside = one.submit(
                    () -> TenantScope.run(
                            "TENANT-NEW", TenantScope::current));
            check("TENANT-NEW".equals(
                    inside.get(10, TimeUnit.SECONDS)),
                    "Scoped value is not visible inside task");

            Future<String> outside = one.submit(TenantScope::current);
            check(outside.get(10, TimeUnit.SECONDS) == null,
                    "TenantScope must remove value after task");

            Future<String> nested = one.submit(
                    () -> TenantScope.run("OUTER", () -> {
                        String inner = TenantScope.run(
                                "INNER", TenantScope::current);
                        check("INNER".equals(inner),
                                "Nested scope must see INNER");
                        return TenantScope.current();
                    }));
            check("OUTER".equals(
                    nested.get(10, TimeUnit.SECONDS)),
                    "Nested scope must restore outer value");

            Future<String> afterNested = one.submit(TenantScope::current);
            check(afterNested.get(10, TimeUnit.SECONDS) == null,
                    "Outer scope must be removed when complete");
        } finally {
            one.shutdownNow();
            check(one.awaitTermination(10, TimeUnit.SECONDS),
                    "Single-thread pool must terminate");
        }
    }

    public static void main(String[] args) throws Exception {
        controlledInterleaving();
        realConcurrentTasks();
        threadLocalReuse();
        System.out.println("PASS");
    }
}
~~~

Chạy:

~~~bash
javac Main.java StateIsolationTest.java
java StateIsolationTest
~~~

Kết quả cuối dự kiến: `PASS`. Lệnh test chủ động kiểm tra một handler lỗi **bằng chứng phản ví dụ**; việc test pass không có nghĩa `LeakyAsyncHandler` đã được sửa. Nó có nghĩa lịch chạy có kiểm soát đã làm lộ hành vi sai theo đúng dự kiến, và `IsolatedAsyncHandler` vượt qua các tình huống đã kiểm tra.

### Tại sao test `ThreadLocal` dùng pool một thread?

Nếu dùng pool có nhiều thread và hy vọng worker B dùng lại thread A, test có thể chạy trên **thread khác** rồi không thấy lỗi dù quên cleanup. `Executors.newSingleThreadExecutor()` đảm bảo các task được xếp tuần tự qua cùng worker thông thường; với ví dụ không có lỗi worker phải được thay, ta có thể quan sát rõ giá trị còn lại từ task trước.

### Tại sao có `get(timeout)`?

Nếu task vướng deadlock hoặc một callback không hoàn thành, `get(timeout, TimeUnit.SECONDS)` giới hạn thời gian test phải chờ. Nếu quá hạn, exception làm test thất bại thay vì chờ vô tận. `finally` yêu cầu dừng pool; khi triển khai thực tế còn cần xem **task có đáp ứng interruption không** và có tài nguyên nào phải đóng riêng không.

**Không nên dùng test này làm bằng chứng production bảo mật tenant.** Nó kiểm tra hành vi Java cụ thể và một số lịch chạy, không kiểm chứng đầy đủ authorization, truy cập DB theo tenant, context propagation của framework hay isolation giữa nhiều tiến trình.

## 8. Kiểm thử bằng latch/barrier khi cần đồng thời thực sự

`QueuedExecutor` rất phù hợp để đặt lịch cho tác vụ async, nhưng một số lỗi chỉ xảy ra khi hai thread **cùng thực thi mã**. Khi đó có thể dùng:

- `CountDownLatch`: đợi một sự kiện/thứ tự đã chỉ định (ví dụ task A đã nạp dữ liệu, task B đã thay trạng thái).
- `CyclicBarrier` hoặc `Phaser`: cho nhiều worker cùng đến một mốc rồi mới tiếp tục.
- `ExecutorService`: thực thi trên các thread thực, thu `Future` và lỗi từ các tác vụ.
- Atomic primitives và cấu trúc concurrent: thiết kế đồng bộ đúng, nhưng vẫn phải kiểm tra isolation theo yêu cầu nghiệp vụ.

Ví dụ minh họa một lịch chạy có kiểm soát với hai latch:

~~~java
// Pseudocode Java rút gọn; giả định shared đã có begin/finish
// và hai phương thức thao tác trên field currentTenant (thiết kế lỗi).
CountDownLatch aStarted = new CountDownLatch(1);
CountDownLatch bOverwrote = new CountDownLatch(1);

// Worker A:
shared.begin(requestA);      // currentTenant = A
aStarted.countDown();
bOverwrote.await();          // chờ B ghi đè
Result resultA = shared.finish(requestA); // có thể đọc B

// Worker B:
aStarted.await();
shared.begin(requestB);      // currentTenant = B
bOverwrote.countDown();
~~~

Đây là **mã mô tả các bước**, chưa phải file Java độc lập. Trong test thật, nên dùng `await(timeout, unit)` để tránh treo và trả lại exception của các worker lên thread chạy test. Latch giúp tạo thứ tự trước–sau (*happens-before*) cần thiết cho bài toán; nó không làm field dùng chung trở thành request-scoped.

### Khi nào test không nên đòi thứ tự hoàn thành?

Với xử lý song song, task B hoàn thành trước A có thể hoàn toàn hợp lệ. Test đúng nên so sánh:

- Mỗi response giữ đúng request ID và tenant ID tương ứng.
- Tác dụng phụ được ghi vào đúng phân vùng dữ liệu.
- Một session/context không bị dùng sau khi đã đóng.
- Số lần tạo/đóng tài nguyên đạt hợp đồng.
- Không có rò context hoặc trạng thái từ một job sang job khác.

Chỉ kiểm tra **thứ tự hoàn thành** nếu yêu cầu nghiệp vụ hoặc hợp đồng executor thật sự hứa thứ tự đó. Tránh khiến test thất bại vì lịch chạy hợp lệ mà không có liên quan đến rò trạng thái.

## 9. Request scope, singleton và provider trong DI container

Trong DI framework, các scope thường gặp là singleton, request, session, job hoặc custom scope. Container có thể giúp quản lý vòng đời một số dependency theo ranh giới đó, nhưng chọn scope sai vẫn gây lỗi.

| Cấu hình | Hệ quả | Cách kiểm tra |
| --- | --- | --- |
| Singleton stateless nhận request data qua tham số | Thường phù hợp với nhiều request | Kiểm tra không có field mutable chứa request data |
| Singleton giữ một `RequestContext` target từ request A | Rò dữ liệu hoặc dùng context đã hết hạn | Hai request liên tiếp phải không thấy state của nhau |
| Singleton giữ **scoped proxy** tới request context | Proxy có thể resolve target theo scope hiện tại | Test request A/B qua container, kiểm tra scope hợp lệ |
| Singleton giữ provider tạo context mới mỗi `get()` | Có thể tạo nhiều context cho cùng một công việc | Test identity của context trong **một** unit of work |
| Request-scoped service tạo task chạy lâu hơn request | Task có thể truy cập dependency đã hết scope | Test completion/cancellation và ownership của tài nguyên |
| ThreadLocal được framework truyền sang executor | Tùy cơ chế propagation và cleanup | Test pool tái sử dụng worker và các đường lỗi |

**Provider không đồng nghĩa request scope.** Một `Supplier<T>` hay `Provider<T>` chỉ là cách lấy dependency; khi `get()` tạo mới hay dùng lại phải được định nghĩa trong binding và contract. Nếu hai bước thuộc cùng unit of work cần một identity context, composition root nên tạo unit một lần rồi truyền cùng instance, hoặc dùng scoped provider có bảo đảm tương đương.

**Scoped proxy không làm target sống mãi.** Một singleton có thể giữ một proxy ổn định, nhưng target request thực sự thay đổi theo từng request. Việc cache target sau khi lấy qua proxy có thể phá ranh giới scope.

## 10. Bất đồng bộ và vòng đời: không được đóng context khi task vẫn chạy

Một lỗi khác là không rò sang tenant khác nhưng **dùng tài nguyên sau khi scope kết thúc**:

~~~java
// Minh họa lỗi thời điểm: task có thể chạy sau khi scope đóng.
CompletableFuture<Void> future;
try (WorkContext context = openWorkContext()) {
    future = CompletableFuture.runAsync(
            () -> process(context), executor);
}
// context đã close; future có thể chưa hoàn thành!
future.join();
~~~

Đoạn trên chưa khai báo `WorkContext`, `openWorkContext` và `process`; mục đích là minh họa thứ tự lifecycle. Tài nguyên do `context` sở hữu đã được đóng ở cuối khối `try`, trong khi task vẫn có thể truy cập nó.

Với một công việc cần context sống suốt xử lý async, một thiết kế dễ kiểm soát hơn là để **owner của công việc** chờ kết thúc (hoặc hủy và hoàn tất cleanup) trước khi đóng:

~~~java
try (WorkContext context = openWorkContext()) {
    CompletableFuture<Void> future = CompletableFuture.runAsync(
            () -> process(context), executor);

    future.join(); // Đảm bảo task hoàn thành trước khi close.
}
~~~

Đây vẫn chỉ là ví dụ khái niệm. Trong hệ thống thật, phải xử lý exception, timeout, interruption, cancellation và các tác vụ con (*structured concurrency* hoặc cơ chế điều phối tương đương) trước khi đóng tài nguyên. Chỉ gọi `cancel(true)` không tự chứng minh worker đã dừng hoặc không còn sử dụng context.

Một ứng dụng có thể chọn cách khác: truyền **snapshot bất biến của dữ liệu cần thiết** cho task và không giữ session/request context ngoài scope. Với nhiều bài toán, đây là cách giảm coupling và lỗi vòng đời rõ ràng hơn.

### Shutdown executor cũng là trách nhiệm lắp ghép

Nếu executor được tạo ở composition root và dùng chung cho nhiều service, service tiêu thụ thường **không tự `shutdown()`** sau mỗi request. Owner ứng dụng cần:

1. Dừng nhận công việc mới.
2. Đợi tác vụ đang chạy hoặc áp dụng chính sách hủy có kiểm soát.
3. Đóng scope, session hoặc resource khi không còn task sử dụng.
4. Shutdown executor và tài nguyên liên quan đúng thứ tự.

Nếu hủy job A nhưng callback của nó vẫn chạy sau khi context A bị tái sử dụng hoặc đóng, có thể phát sinh lỗi khó tái hiện. Kiểm thử shutdown và timeout cần tách khỏi unit test nghiệp vụ thông thường.

## 11. Thiết kế hợp đồng và test isolation giữa các tenant

Khi request có tenant hoặc user, kiểm thử rò trạng thái cần xem cả **đầu vào, kết quả và tác dụng phụ**. Một response ghi đúng tenant ID chưa chứng minh câu truy vấn DB đã được giới hạn theo tenant.

Ví dụ một `OrderRepository` có contract:

~~~java
interface TenantOrderRepository {
    void save(String tenantId, String orderId);
    boolean exists(String tenantId, String orderId);
}
~~~

Với cùng `orderId` ở hai tenant, contract có thể yêu cầu không được quan sát dữ liệu của tenant khác. Test sẽ tạo dữ liệu vào `TENANT-A` và `TENANT-B`, rồi kiểm tra cả kết quả và nơi dữ liệu được ghi.

**Dữ liệu đầu vào phải đủ phân biệt.** Nếu hai request vô tình dùng cùng tenant, cùng quyền và cùng kết quả, một lỗi hoán đổi context có thể không bị phát hiện. Dùng request ID, tenant ID và payload riêng biệt cho từng case.

Một ma trận kiểm thử hữu ích:

| Tình huống | Điều cần chứng minh |
| --- | --- |
| A rồi B tuần tự trên một singleton | Không có state A nằm lại khi xử lý B |
| A và B overlap qua executor | Mỗi response dùng context của chính request |
| A và B cùng khóa nghiệp vụ nhưng khác tenant | Không đọc/ghi nhầm phân vùng dữ liệu |
| Task A thất bại giữa chừng | Cleanup thực hiện và task B không nhận dữ liệu sót |
| Task A bị hủy hoặc timeout | Context/tài nguyên không bị dùng sau khi scope kết thúc |
| Thread pool reuse | `ThreadLocal` được dọn/khôi phục đúng |
| Một unit of work có nhiều bước | Các bước trong **cùng unit** chia sẻ đúng context |
| Hai unit of work độc lập | Không chia sẻ state mutable khi contract đòi cách ly |
| Request context được đưa sang callback async | Có chính sách truyền context rõ, không dựa vào thread hiện tại |
| Shutdown trong lúc còn job | Không đóng dependency dùng chung quá sớm |

Đối với dữ liệu nhạy cảm, không cần in token/secret thật trong log test. Dùng các ID giả rõ ràng là đủ để phát hiện đường truyền sai; môi trường kiểm thử còn cần bảo đảm không kết nối vào tài nguyên production ngoài ý muốn.

## 12. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai? | Thay vào đó |
| --- | --- | --- |
| “Service được inject vào singleton thì mọi trạng thái bên trong an toàn.” | Singleton chỉ nói về lifetime, không về isolation/thread-safety | Giữ service stateless hoặc đồng bộ theo hợp đồng đúng |
| “Field `final` làm request state bất biến.” | `final` giữ tham chiếu, không đóng băng object mutable được tham chiếu | Ưu tiên request snapshot bất biến và ownership rõ |
| “`volatile` sửa được rò tenant.” | Visibility không biến field chung thành field theo request | Không lưu tenant hiện tại trong singleton field |
| “`ThreadLocal` gắn với request.” | Thread pool tái sử dụng thread, task async có thể đổi thread | Dọn trong `finally`, hoặc truyền context tường minh |
| “`CompletableFuture` tự truyền security context.” | Propagation phụ thuộc framework/wrapper/executor | Thiết kế và kiểm thử context propagation thật |
| “Dùng provider là luôn có instance mới.” | `get()` có thể trả singleton hoặc scoped instance | Ghi rõ binding, scope và identity contract |
| “Chạy 100.000 lượt không lỗi nên chắc chắn thread-safe.” | Test có thể không tạo lịch chạy nguy hiểm | Test interleaving xác định + test đồng thời thực |
| “`Thread.sleep` làm test concurrency ổn định.” | Phụ thuộc tốc độ máy và scheduler | Latch, barrier, queue điều khiển và timeout |
| “Future hoàn thành nghĩa là các side effect đã được rollback nếu thất bại.” | Async completion không mang bảo đảm giao dịch | Thiết kế transaction, retry và idempotency riêng |
| “Đóng request scope không cần biết task còn chạy không.” | Task có thể dùng dependency hết vòng đời | Owner phải điều phối task completion và cleanup |

Một số test phải chạy **ở mức container thật**. Test Java thuần kiểm tra lớp và lịch chạy của ta; nó không thể xác nhận framework đã cấu hình request scope, security propagation, proxy và lifecycle callback đúng trong production.

## 13. Quy trình phát hiện và sửa rò trạng thái

1. **Vẽ object graph và đánh dấu lifetime:** dependency nào singleton, per-request, per-job, per-unit-of-work? Ai tạo và đóng?
2. **Liệt kê dữ liệu có tính riêng tư theo scope:** tenant ID, auth context, request ID, bộ đệm tạm, entity đang sửa, transaction/session.
3. **Rà field mutable trong object sống lâu:** tìm `currentUser`, `currentTenant`, `lastRequest`, mutable collections và singleton cache không phân vùng.
4. **Rà ranh giới async:** lambda capture field hay snapshot? Future chạy trên executor nào? Có callback chạy sau scope không?
5. **Rà `ThreadLocal` và context propagation:** đã `remove()`/restore trong `finally` chưa? Worker thread có được tái sử dụng không?
6. **Viết phản ví dụ xác định:** dùng controlled executor hoặc latch để buộc A/B chồng lấp và kiểm tra đúng context.
7. **Sửa đúng nguyên nhân:** truyền dữ liệu request bất biến bằng tham số, tách service stateless, tạo context theo công việc hoặc dùng provider/scoped proxy có hợp đồng phù hợp.
8. **Kiểm thử cả hành vi và side effect:** không chỉ response, còn partition/tenant của bản ghi, event, cache và tác động hạ tầng.
9. **Thêm concurrency test có timeout:** bảo đảm pool shutdown, thu exception từ task và kiểm tra nhiều request độc lập.
10. **Kiểm thử cleanup và lifecycle trên đường lỗi:** exception, timeout, cancellation, callback async, shutdown ứng dụng.
11. **Chạy wiring/integration test với DI container thật khi dùng framework:** kiểm tra scope, proxy, context propagation và transaction trong cấu hình thực.
12. **Theo dõi production có kiểm soát:** correlation ID, tenant ID giả định/đã được phép log, metrics về lỗi scope; không lộ credential hoặc dữ liệu nhạy cảm.

### Tự kiểm tra

**Tình huống A:** Một `PaymentService` singleton có field `String currentTenant`, được cập nhật ở mỗi lời gọi rồi sử dụng trong future. Có thể sửa chỉ bằng `volatile` không?

**Không.** `volatile` giúp visibility nhưng A vẫn có thể đọc tenant do B vừa ghi. Hãy truyền/capture tenant của mỗi request riêng, không dùng field chung cho dữ liệu có scope ngắn.

**Tình huống B:** Test gửi 500 request đồng thời và pass. Điều đó chứng minh không thể có rò state không?

**Không.** Một lịch chạy khác vẫn có thể làm lộ lỗi. Cần kết hợp test interleaving có chủ đích, đánh giá thiết kế scope/ownership và kiểm thử thực tế.

**Tình huống C:** Hai công việc dùng cùng `ExecutorService` nhưng mỗi việc truyền một `TenantRequest` bất biến vào handler stateless. Việc dùng chung executor có tự gây rò tenant không?

**Không tự động.** Dùng chung executor là bình thường nếu lifecycle và thread safety được quản lý. Rò xuất hiện khi có trạng thái ngầm/chung bị sử dụng sai, hoặc context theo thread không được xử lý đúng.

**Tình huống D:** Một tác vụ đặt `ThreadLocal` rồi quên `remove()`. Task tiếp theo trên cùng worker không đặt context mới. Có thể thấy context cũ không?

**Có.** ThreadLocal gắn với thread, còn worker thread có thể phục vụ nhiều tác vụ. Đặt/dọn bằng `try/finally` hoặc truyền context tường minh sẽ làm ranh giới rõ hơn.

**Tình huống E:** Request A bắt đầu tác vụ async rồi đóng `WorkContext` ngay khi controller trả response, trong khi tác vụ vẫn cần repository của context ấy. Có an toàn không?

**Không có bảo đảm.** Task có thể dùng dependency sau khi hết scope. Hãy chuyển ownership sang thời gian sống của task, đợi task kết thúc trước khi đóng hoặc truyền snapshot không cần context.

**Tình huống F:** Một singleton giữ scoped proxy tới request context. Có thể kết luận proxy và target đều là cùng instance trên mọi request?

**Không.** Proxy được inject có thể ổn định, nhưng target do nó resolve thay đổi theo request. Test phải kiểm tra dữ liệu của từng request qua đúng đường gọi, thay vì chỉ so sánh danh tính proxy.

## Ghi nhớ

**Kiểm thử rò rỉ trạng thái** không chỉ là chạy nhiều thread, mà là **chứng minh các yêu cầu/tác vụ độc lập không quan sát và không sửa nhầm trạng thái của nhau**. Bắt đầu bằng một lịch chạy xác định để phơi bày việc singleton giữ request data, dùng test thread pool để kiểm tra tác vụ đồng thời, và test worker reuse để phát hiện `ThreadLocal` chưa cleanup. Giữ service dùng chung **không giữ state request**, truyền dữ liệu bất biến qua tham số hoặc snapshot, tạo context theo đúng scope và để composition root quản lý lifecycle của executor cùng tài nguyên. **DI và DI container giúp cấp dependency; tính đúng về isolation, concurrency và bất đồng bộ vẫn là trách nhiệm của thiết kế và kiểm thử.**
