# Quy định số lượng đối tượng, trạng thái dùng chung và cơ chế đồng bộ trong vòng đời plugin Java

## 1. Vì sao vòng đời plugin phải quy định rõ số lượng instance?

Một host Java có thể khám phá và nạp một **plugin implementation** qua `ServiceLoader`, class loader riêng, `ModuleLayer` hoặc factory do plugin cung cấp. Nhưng việc tìm được lớp và tạo được đối tượng **không trả lời** ba câu hỏi vận hành quan trọng:

1. **Một plugin có bao nhiêu instance?** Một instance cho toàn host, một instance cho mỗi phiên bản plugin, mỗi tenant, mỗi session, mỗi request, hay một pool có giới hạn?
2. **Trạng thái nào được chia sẻ?** Counter, cache, kết nối, cấu hình, trạng thái người dùng, transaction context và dữ liệu của từng lần gọi thuộc instance hay host?
3. **Những lời gọi đồng thời được xử lý ra sao?** Plugin có an toàn khi hai thread gọi cùng lúc? Host phải khóa, cấp instance riêng, giới hạn concurrency hay từ chối yêu cầu khi đang dừng?

Không làm rõ các câu hỏi trên sẽ dẫn đến kết quả khó đoán: mất cập nhật, sai dữ liệu giữa tenant, dùng object sau khi `close()`, rò rỉ class loader, deadlock khi callback, hoặc tạo quá nhiều đối tượng và tài nguyên.

Ví dụ host dùng một `Plugin` singleton chứa trường mutable `int requestCount` và hai thread cùng thực hiện `requestCount++`. Phép tăng này gồm đọc–cộng–ghi; nếu không có bảo đảm đồng bộ, nhiều cập nhật có thể bị mất. Ngược lại, nếu host tạo một instance cho mỗi request, race trên trường instance có thể ít đi nhưng chi phí khởi tạo database client, model hoặc interpreter lại tăng mạnh.

**Nguyên tắc:** số instance, quy tắc sở hữu state và concurrency là **một phần của hợp đồng host–plugin**, phải được khai báo, kiểm tra và thực thi xuyên suốt `create → initialize → start → invoke → quiesce → stop/close → unload`. Đừng để mỗi plugin tự suy đoán.

### 1.1. Phân biệt ba đại lượng dễ nhầm

- **Số instance đang tồn tại**: bao nhiêu đối tượng plugin đang được host giữ và có khả năng sử dụng.
- **Số instance từng được tạo**: số tích lũy từ lúc bắt đầu generation. Với `PER_CALL`, con số này tăng theo yêu cầu, dù các instance cũ đã đóng và được GC.
- **Số lời gọi đang thực thi (in-flight)**: bao nhiêu lời gọi chưa trả về. Một shared instance có thể xử lý nhiều in-flight nếu thread-safe; một pool 4 instance có thể cho tối đa 4 lượt dùng đồng thời nếu mỗi instance chỉ được cấp cho một borrower.

Các số này không bằng nhau. Vì vậy `maxInstances=4` không tự có nghĩa `maxConcurrentCalls=4`, và `singleton` cũng không tự có nghĩa `single-threaded`.

## 2. Những chính sách số lượng instance thường gặp

| Chính sách | Số instance điển hình | State được chia sẻ | Dùng khi | Cần cảnh giác |
| --- | --- | --- | --- | --- |
| **Singleton trong một host/generation** | 1 | Mọi lời gọi đến cùng object | Plugin rẻ, thread-safe hoặc cần registry chung | Race, state tenant rò rỉ, close ảnh hưởng mọi request |
| **Một instance cho mỗi lần gọi (per-call)** | 1 mới cho mỗi invoke | Ít chia sẻ trên instance | Plugin có mutable state, xử lý ngắn | Chi phí tạo/đóng; tổng số instance tích lũy lớn |
| **Per-session** | 1 mỗi session đang sống | State trong session | Workflow nhiều bước cần giữ ngữ cảnh | TTL, eviction, session concurrent requests |
| **Per-tenant** | 1 hoặc một tập theo tenant | Chỉ trong một tenant | Cấu hình/cache theo tenant | Phân tách dữ liệu, quota từng tenant |
| **Per-thread (thread-confined)** | Thường 1 mỗi thread liên quan | Trên thread đó | Thư viện thực sự có thread affinity | Thread pool tái sử dụng thread, `ThreadLocal` leak |
| **Object pool** | Tối đa N object trong pool | Có thể tái sử dụng có kiểm soát | Khởi tạo tốn kém, không thread-safe | Borrow/return, reset state, hỏng instance, backpressure |
| **Per-request scope + shared host service** | N plugin instance, ít host service | Chỉ service được host chia sẻ rõ ràng | Muốn isolation state nhưng giữ cache/connection chung | Quyền truy cập service, transaction và thread safety |

**Singleton trong host không phải singleton toàn JVM hay toàn cluster.** Khi plugin được nạp lại bởi class loader khác, class singleton hoặc static field trong loader mới có thể là một bản riêng. Nếu cần tính duy nhất **toàn cluster**, phải dùng một cơ chế bên ngoài như database lock, coordinator hoặc service được thiết kế cho phân tán; không thể dựa vào `static` hoặc `synchronized` trong một tiến trình.

### 2.1. Chọn theo tính chất plugin, không theo thói quen framework

Hãy đánh giá theo trục:

- **Chi phí khởi tạo**: parser/cache lớn, kết nối, native resource, thread riêng?
- **Khả năng tái sử dụng**: cùng instance xử lý request khác mà không mang theo dữ liệu cũ?
- **Thread safety**: có thể gọi `process` đồng thời trên cùng instance không?
- **Phạm vi state**: state toàn host, per tenant, per user, per transaction hay per invocation?
- **Khả năng bị chặn**: I/O có thể lâu, lock có nguy cơ làm nghẽn những request không liên quan?
- **Giới hạn tài nguyên**: memory, connection, file descriptor, thread, request backlog?
- **Thay version**: instance/plugin loader cũ còn phải phục vụ request đang chạy trong lúc generation mới bắt đầu không?

Ví dụ plugin xử lý một phép biến đổi thuần túy với cấu hình immutable thường phù hợp singleton. Một parser không thread-safe nhưng khởi tạo rẻ có thể per-call; parser không thread-safe và khởi tạo đắt có thể dùng pool kèm reset state. Cache riêng mỗi tenant không nên đặt trong singleton global mà không có partition key và kiểm soát quyền.

### 2.2. “Factory singleton” và “plugin singleton” là hai khái niệm khác nhau

Một `PluginFactory` có thể là một object được giữ duy nhất trong registry, nhưng mỗi lần gọi `factory.create()` vẫn trả **plugin instance mới**. Ngược lại, factory có thể trả cùng một object cho mọi lời gọi. Host phải **quy định scope bằng contract**, không suy ra từ số factory.

Hợp đồng có thể gồm metadata:

```java
enum Scope { SINGLETON, PER_CALL, PER_TENANT, POOLED }
enum ConcurrencyMode { THREAD_SAFE, SERIALIZED, CONFINED }

record PluginPolicy(
        Scope scope,
        ConcurrencyMode concurrency,
        int maxActiveCalls,
        int maxInstances,
        boolean reusableAfterFailure) {

    PluginPolicy {
        if (maxActiveCalls < 1 || maxInstances < 1) {
            throw new IllegalArgumentException("limits must be positive");
        }
    }
}
```

Đây là **mô hình API độc lập dùng minh họa**, không phải `PluginPolicy` có sẵn trong JDK và không phải code của demo chạy ở phần 6. Registry cần kiểm tra policy được công bố có đúng với implementation, version và tài nguyên thật; “plugin nói THREAD_SAFE” chưa thể thay cho test.

Một cách thiết kế tốt là host giữ quyền quyết định cuối cùng: một plugin chỉ hỗ trợ `SERIALIZED` không được bị host ép phục vụ nhiều lời gọi song song trên cùng instance. Nếu host cần throughput lớn hơn, có thể tạo nhiều instance độc lập hoặc dùng pool sau khi được plugin cho phép.

## 3. Phân loại trạng thái: cái gì được phép dùng chung?

Thay vì coi mọi field trên plugin là state giống nhau, nên tách theo ownership và lifetime.

| Loại state | Ví dụ | Chủ sở hữu lý tưởng | Quy tắc |
| --- | --- | --- | --- |
| Cấu hình immutable | Endpoint, feature flags, phiên bản API | Host/generation | Khởi tạo một lần, publish an toàn |
| State riêng của lời gọi | Request ID, input, response builder | Invocation | Không lưu vào field singleton |
| State riêng session | Workflow step, session token | Session | TTL, authorization, reset/cleanup |
| State riêng tenant | Tenant cache, quota, mapping | Tenant/partition | Khóa tenant, không chia cross-tenant |
| State chung có chủ đích | Metric counters, immutable lookup tables | Host hoặc shared plugin | Dùng atomic/lock/concurrent collections |
| External state | DB transaction, message offset, distributed lease | Service/DB | Transaction/idempotency và phân tán |
| Tài nguyên có vòng đời | Connection, executor, file handles | Host/factory/instance theo contract | Đóng đúng một lần, không đóng khi còn dùng |
| Class-level static state | Static map/cache trong plugin JAR | Defining class loader | Không mặc nhiên dùng chung giữa các loader/generation |

### 3.1. Immutable configuration là điểm khởi đầu tốt

Cấu hình nên được tạo thành object immutable (record hoặc final fields) và hoàn tất trước khi public plugin instance cho request thread. Việc xuất bản object phải có **happens-before** phù hợp: sử dụng constructor hoàn tất, final-field semantics và cơ chế registry/thread-safe publication; chỉ đặt field là `final` không sửa mọi data race nếu object tham chiếu tới collection mutable vẫn bị thay đổi.

Khi reload config, có thể thay cả immutable snapshot qua một reference `volatile` hoặc `AtomicReference<Config>`, nhưng phải quyết định một request đọc **một snapshot** xuyên suốt hay có thể thấy nhiều phiên bản giữa chừng.

### 3.2. Không lưu request data vào field singleton

Sai điển hình:

```java
class UnsafePlugin {
    private String currentUser; // thay đổi bởi các request

    String handle(String user) {
        currentUser = user;
        return "hello " + currentUser;
    }
}
```

Đây là **mã cảnh báo**, không phải code production. Nếu thread A ghi `"alice"` rồi thread B ghi `"bob"` trước khi A đọc lại, A có thể trả tên của B. Thêm `volatile` chỉ cải thiện visibility, **không biến một field global thành state riêng từng request**.

Cách đơn giản nhất là đặt dữ liệu vào biến local hoặc object context được truyền vào:

```java
record Request(String user) {}

String handle(Request request) {
    return "hello " + request.user();
}
```

Đây là **đoạn minh họa tích hợp**; method cần nằm trong một class hợp lệ và `Request` cần được host và plugin thống nhất kiểu runtime nếu đi qua boundary. Với API plugin, đặt request/response DTO ở shared contract và không để nhiều tenant chia sẻ mutable request object.

### 3.3. “Shared” không đồng nghĩa “không đồng bộ”

Nếu nhiều thread cập nhật cùng counter, `AtomicInteger.incrementAndGet()` hoặc `LongAdder.increment()` phù hợp tùy yêu cầu (ví dụ `LongAdder` thường tốt cho metric contention cao nhưng `sum()` không phải snapshot nguyên tử của mọi cập nhật concurrent).

Một `ConcurrentHashMap` hỗ trợ thao tác thread-safe trên map, nhưng không tự biến chuỗi lệnh “check → compute → put” nhiều bước thành transaction. Khi cập nhật dựa trên giá trị hiện có, dùng những thao tác nguyên tử thích hợp như `compute`/`merge`; cẩn trọng callback trong `compute` không nên chặn lâu, sửa map lồng nhau không phù hợp hoặc có side effect phức tạp.

Với invariant liên quan **nhiều field**, một atomic counter cho từng field có thể chưa đủ. Cần lock bảo vệ cả nhóm hoặc thay một immutable snapshot bằng `AtomicReference`/CAS. Quyết định theo tính đúng trước khi tối ưu throughput.

### 3.4. ThreadLocal không phải per-request mặc định

`ThreadLocal` gắn giá trị với **thread**. Trong server dùng thread pool, thread hôm nay phục vụ request A có thể ngày mai phục vụ request B. Quên `remove()` có thể giữ dữ liệu request, tenant, class hoặc class loader của plugin cũ.

Nếu một plugin buộc dùng `ThreadLocal`, hãy tạo/đọc/xóa trong `try/finally`, tuyệt đối không dựa vào thread identity như tenant identity. Với công việc asynchronous hoặc virtual threads, hãy thiết kế propagation của context có chủ đích; không giả định state thread-local tự chuyển đúng qua các executor.

## 4. Những cơ chế đồng bộ phù hợp với từng kiểu dữ liệu

| Công cụ Java | Tốt cho | Không thay thế |
| --- | --- | --- |
| `final` + immutable objects | Cấu hình/state không thay đổi | Coordination của resource mutable |
| `volatile` | Một reference/flag cần visibility | Atomicity của `counter++`, nhiều-field invariant |
| `AtomicInteger` / `AtomicLong` | Counter, CAS trên một giá trị | Transaction nhiều state |
| `LongAdder` | Metric đếm contention cao | Snapshot tuyến tính chính xác trong lúc ghi |
| `ConcurrentHashMap` | Map nhiều reader/writer | Workflow nhiều bước không nguyên tử |
| `synchronized` / `ReentrantLock` | Chặn truy cập đồng thời vào critical section | Cô lập dữ liệu tenant một cách tự động |
| `ReentrantReadWriteLock` | Nhiều reader, một writer; lifecycle gate | Đảm bảo plugin thread-safe khi nhiều reader vào cùng object |
| `Semaphore` | Giới hạn số lời gọi/borrower | Số instance đã được tạo hay thread safety tự thân |
| `BlockingQueue` | Hàng đợi có giới hạn cho pool | Việc reset/validate instance trước tái sử dụng |
| `CountDownLatch` / `Phaser` | Chờ điều kiện/phối hợp nhóm tác vụ | Cancel/quiescence policy đầy đủ |
| `ExecutorService` | Chạy và quản lý task | Tự chặn request khi plugin đã stop |

### 4.1. Tránh oversynchronize và undersynchronize

Nếu plugin singleton **thread-safe** và mỗi request chỉ đọc config immutable, host có thể cho concurrent calls. Nếu không thread-safe, có ba hướng: host **serialize** lời gọi; tạo instance riêng theo request; hoặc dùng pool instance được bảo đảm chỉ một borrower tại một thời điểm.

Serialize mọi lời gọi qua một lock chung có thể giảm throughput mạnh khi plugin làm I/O. Hơn nữa, lock bảo vệ state nội bộ của plugin không đồng nghĩa quản lý **vòng đời stop/unload**: host vẫn phải chặn yêu cầu mới và chờ các lời gọi đang chạy trước khi gọi `close()`.

### 4.2. Thứ tự khóa (lock order) phải được quy định

Trong hệ có nhiều layer (registry → plugin host → plugin instance → callback), nếu luồng A giữ `registryLock` rồi chờ `pluginLock`, trong khi luồng B giữ `pluginLock` rồi callback vào registry, có thể xảy ra deadlock. Cần thống nhất thứ tự lấy lock, tránh gọi arbitrary plugin code khi đang giữ registry lock phạm vi lớn, và không nâng từ read lock lên write lock một cách ngây thơ.

`ReentrantReadWriteLock` **không hỗ trợ nâng khóa read → write** theo cách an toàn thông thường: cùng thread giữ read lock rồi gọi hàm stop cần write lock có thể tự chặn. API lifecycle nên tránh cho callback `process()` đóng chính host đang giữ read lock, hoặc thiết kế giao thức dừng riêng không yêu cầu upgrade.

### 4.3. Giới hạn concurrency và backpressure

Nếu mỗi instance phục vụ tối đa một lời gọi, một pool kích thước N có thể giới hạn **số người mượn đồng thời** ở N. `Semaphore(N)` cũng có thể giới hạn N request đang chạy dù plugin thread-safe. Nhưng nếu host chỉ dùng semaphore mà mỗi khi có yêu cầu lại `new Plugin()`, tổng số instance từng được tạo vẫn có thể tăng vô hạn theo thời gian.

Trong production, phân biệt:

- `maxLiveInstances`: giới hạn object còn sống.
- `maxConcurrentCalls`: giới hạn in-flight.
- `maxQueuedCalls`: giới hạn request đang chờ.
- `acquireTimeout` và **rejection/backpressure policy** khi quá tải.
- Timeout của bản thân công việc, cancellation và cleanup khi client rời đi.

Các giới hạn phải có telemetry và test dưới load. Không để hàng đợi không giới hạn chỉ vì pool giới hạn số thread.

## 5. Giao thức dừng an toàn khi còn request đang chạy

Một vòng đời điển hình có thể mô tả như sau:

```text
DISCOVERED
    |
    v
CREATED -> INITIALIZING -> RUNNING
                         |
                         | stop requested
                         v
                    QUIESCING
                    (reject new calls,
                     finish/cancel in-flight)
                         |
                         v
                    STOPPING -> STOPPED -> eligible for unload
                         |
                         +--> FAILED if cleanup fails
```

Các nhãn là **mô hình state machine gợi ý** của host, không phải enum có sẵn trong JVM. Quan trọng là quy định các transition hợp lệ, ai được quyền gọi, trạng thái quan sát được và xử lý idempotent.

### 5.1. In-flight và stop phải phối hợp

Race thường gặp:

```text
Thread A: check running == true
Thread B: close(plugin)
Thread A: plugin.process(request)   // use-after-close
```

Chỉ thêm `volatile boolean running` là **chưa đủ**, vì check và bắt đầu công việc không tạo một thao tác admission nguyên tử với close. Có thể dùng **lifecycle gate**: read lock khi nhận/làm một invocation, write lock khi stop; hoặc active lease/reference count kết hợp condition để chờ số active về zero.

Trong ví dụ ở phần 6, host giữ **read lock** suốt thời gian gọi `process()`. `close()` cần **write lock**, vì vậy không thể đóng instance shared khi còn read-locked invocation. Sau khi write lock chuyển trạng thái `closed=true`, lần gọi tiếp theo lấy read lock sẽ kiểm tra và bị từ chối.

Đây là mô hình dễ hiểu và chứng minh được thứ tự, nhưng **có trade-off**: nếu plugin chạy vô hạn hoặc gọi ngược vào thao tác cần write lock, shutdown có thể treo. Production thường cần timeout, cancellation hợp tác và giao thức lease/condition để tránh giữ lock qua đoạn code không tin cậy; tuyệt đối không cưỡng bức bỏ lock một cách sai.

### 5.2. Đóng tài nguyên đúng owner

Plugin singleton có thể giữ connection/threads riêng và được đóng một lần khi host ngừng generation. Plugin per-call có thể đóng trong `finally` ngay sau invocation. Pool phải trả instance về pool, kiểm tra/reset state, và đóng tất cả instance khi pool shutdown.

Nếu một `DataSource`/`ExecutorService` được **host inject và chia sẻ**, plugin không nên tự đóng resource đó trừ khi hợp đồng xác định quyền sở hữu thuộc plugin. Một plugin đóng nhầm host-managed executor có thể ảnh hưởng tất cả plugin khác.

### 5.3. Idempotency và lỗi trong close

`close()` nên idempotent hoặc host phải bảo đảm chỉ gọi một lần, có cleanup khi một phần initialization đã thành công. Nếu cleanup ném exception, vẫn phải cố đóng tài nguyên độc lập khác, ghi nhận lỗi và quyết định trạng thái cuối cùng. Không “nuốt” mọi lỗi rồi báo STOPPED hoàn hảo khi các thread/resources còn chạy.

Với reload, tạo **generation mới** và chuyển routing trước/sau quiesce theo chiến lược rõ ràng. Không cố “thay bytecode” của class đang sống trong một class loader như thể đó là một instance có thể reset vô hạn.

## 6. Ví dụ Java 17+ hoàn chỉnh: shared instance, per-call instance và lifecycle lock

Ví dụ sau chỉ dùng Java chuẩn. Host thực thi 8 lời gọi bằng thread pool trong chế độ **`SHARED`**, sau đó chuyển sang chế độ **`PER_CALL`** cho 2 lời gọi độc lập.

Các đặc điểm của demo:

- `CountingPlugin` có counter `AtomicInteger` và cờ `AtomicBoolean`; do đó việc tăng counter an toàn khi nhiều thread gọi cùng một instance.
- `PluginHost(SHARED)` tạo **đúng một** `CountingPlugin` trong constructor.
- `PluginHost(PER_CALL)` chỉ tạo plugin khi có invocation, đóng plugin trong `finally` sau khi sử dụng.
- `ReentrantReadWriteLock(true)` dùng như lifecycle gate: nhiều invocation có thể đồng thời giữ read lock; `close()` dùng write lock để chờ các lời gọi bên trong gate hoàn tất và ngăn lời gọi mới sau khi closed.
- `AtomicInteger created` đếm **tổng instance từng tạo**, `AtomicInteger inFlight` đếm lời gọi đang chạy và `AtomicLong completed` đếm lượt thành công. Không dùng ba số đó thay cho nhau.
- Sau stop, invocation mới ném `IllegalStateException` và host không tạo thêm plugin.

Đặt toàn bộ source vào **`PluginLifecycleDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class PluginLifecycleDemo {
    enum Scope { SHARED, PER_CALL }

    interface Plugin extends AutoCloseable {
        int process(int input);
        int calls();
        @Override void close();
    }

    static final class CountingPlugin implements Plugin {
        private final AtomicInteger count = new AtomicInteger();
        private final AtomicBoolean stopped = new AtomicBoolean();

        @Override
        public int process(int input) {
            if (stopped.get()) {
                throw new IllegalStateException("plugin closed");
            }
            count.incrementAndGet();
            return Math.multiplyExact(input, 2);
        }

        @Override public int calls() { return count.get(); }
        @Override public void close() { stopped.set(true); }
    }

    static final class PluginHost implements AutoCloseable {
        private final Scope scope;
        private final ReentrantReadWriteLock lifecycle = new ReentrantReadWriteLock(true);
        private final AtomicInteger created = new AtomicInteger();
        private final AtomicInteger inFlight = new AtomicInteger();
        private final AtomicLong completed = new AtomicLong();
        private final CountingPlugin shared;
        // 'closed' must be accessed only under the lifecycle lock.
        private boolean closed;

        PluginHost(Scope scope) {
            this.scope = scope;
            this.shared = scope == Scope.SHARED ? newPlugin() : null;
        }

        private CountingPlugin newPlugin() {
            created.incrementAndGet();
            return new CountingPlugin();
        }

        int invoke(int input) {
            Lock read = lifecycle.readLock();
            read.lock();
            try {
                if (closed) throw new IllegalStateException("host stopped");
                CountingPlugin plugin =
                        scope == Scope.SHARED ? shared : newPlugin();
                inFlight.incrementAndGet();
                try {
                    int result = plugin.process(input);
                    completed.incrementAndGet();
                    return result;
                } finally {
                    try {
                        if (scope == Scope.PER_CALL) plugin.close();
                    } finally {
                        inFlight.decrementAndGet();
                    }
                }
            } finally {
                read.unlock();
            }
        }

        int instancesCreated() { return created.get(); }
        long completedCalls() { return completed.get(); }
        int activeCalls() { return inFlight.get(); }
        int sharedCalls() { return shared == null ? 0 : shared.calls(); }

        @Override
        public void close() {
            Lock write = lifecycle.writeLock();
            write.lock();
            try {
                if (!closed) {
                    closed = true;
                    if (shared != null) shared.close();
                }
            } finally {
                write.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        PluginHost shared = new PluginHost(Scope.SHARED);
        ExecutorService workers = Executors.newFixedThreadPool(4);
        try {
            List<Callable<Integer>> tasks = new ArrayList<>();
            for (int i = 1; i <= 8; i++) {
                final int input = i;
                tasks.add(() -> shared.invoke(input));
            }
            int sum = 0;
            for (Future<Integer> future : workers.invokeAll(tasks)) {
                sum += future.get();
            }
            System.out.println("shared sum: " + sum);
            System.out.println("shared instances: " + shared.instancesCreated());
            System.out.println("shared calls: " + shared.sharedCalls());
            System.out.println("shared active: " + shared.activeCalls());
        } finally {
            workers.shutdown();
            shared.close();
        }

        try {
            shared.invoke(10);
            System.out.println("after close: accepted");
        } catch (IllegalStateException expected) {
            System.out.println("after close: rejected");
        }

        try (PluginHost perCall = new PluginHost(Scope.PER_CALL)) {
            System.out.println("per-call values: " +
                    perCall.invoke(3) + "," + perCall.invoke(4));
            System.out.println("per-call instances: " + perCall.instancesCreated());
            System.out.println("per-call completed: " + perCall.completedCalls());
        }
    }
}
```

### 6.1. Biên dịch và chạy

Trên máy có JDK 17 hoặc mới hơn:

```bash
javac --release 17 PluginLifecycleDemo.java
java PluginLifecycleDemo
```

**Stdout chính xác**, đã được kiểm chứng bằng `javac --release 17` và `java`:

```text
shared sum: 72
shared instances: 1
shared calls: 8
shared active: 0
after close: rejected
per-call values: 6,8
per-call instances: 2
per-call completed: 2
```

### 6.2. Giải thích kết quả

1. **`shared sum: 72`**: tám input `1..8` đều được nhân đôi. Tổng là `2 × (1+2+...+8) = 72`. Thứ tự chạy task có thể khác nhau, nhưng phép cộng kết quả các future tạo ra tổng xác định.
2. **`shared instances: 1`**: constructor của host tạo một plugin dùng cho cả tám lời gọi, không tạo plugin mới theo từng thread.
3. **`shared calls: 8`**: một instance shared nhận tám lời gọi; `AtomicInteger.incrementAndGet()` bảo đảm không mất lần đếm do race.
4. **`shared active: 0`**: các `Future` đã hoàn tất trước khi đo `inFlight`. Kết quả không khẳng định mọi thời điểm trước đó active=0.
5. **`after close: rejected`**: sau `shared.close()`, host từ chối yêu cầu mới vì flag `closed` được bảo vệ bởi lifecycle lock.
6. **`per-call values: 6,8`**: hai lời gọi sinh output riêng, không dùng lại cùng plugin.
7. **`per-call instances: 2`**: tổng hai instance được tạo theo hai lời gọi. Chúng được đóng sau mỗi lần; số này là *cumulative*, không phải số live instance tại thời điểm in.
8. **`per-call completed: 2`**: cả hai lần xử lý thành công. `completed` không tăng cho một execution ném exception trước lúc cập nhật.

### 6.3. Phân tích tính đúng của đoạn đồng bộ

`PluginHost.invoke` nắm **read lock** từ lúc xác thực `closed` đến lúc plugin xử lý xong, cleanup xong và giảm `inFlight`. `PluginHost.close` nắm **write lock** để cập nhật `closed` rồi đóng singleton. Điều đó duy trì invariant:

> Không một `process()` hợp lệ nào trên shared plugin được bắt đầu **sau khi** `close()` của host đã chuyển sang trạng thái closed, và shared plugin không bị đóng khi một invocation đang còn nằm trong lifecycle gate.

Đây là invariant của **host**, không tự chứng minh mọi subclass `Plugin` đều thread-safe. Trong demo, `CountingPlugin` riêng nó dùng atomics, nên nhiều read-locked invocation có thể tăng count đồng thời. Nếu `CountingPlugin` dùng `HashMap` mutable hoặc `int counter++` không đồng bộ, chỉ có read lock **không sửa lỗi**, vì nhiều thread được giữ read lock cùng lúc.

Cần lưu ý:

- Fairness `true` giúp giảm nguy cơ writer bị các reader mới vượt mặt liên tục, nhưng **không bảo đảm** mọi task có deadline hoặc trình tự tuyệt đối.
- Nếu `process()` bị treo, `close()` có thể chờ vô hạn; demo không cung cấp timeout/cancellation.
- Nếu callback trong `process()` gọi `PluginHost.close()` trên cùng host và cùng thread, có nguy cơ deadlock do read → write lock upgrade.
- Nếu `CountingPlugin.close()` ném exception, host cần quy trình ghi nhận cleanup failure và xử lý tài nguyên còn lại. Demo dùng atomic flag nên close nhẹ và idempotent.
- Demo dùng chung API/implementation trong một chương trình để tập trung vào scope và đồng bộ; hệ plugin nạp động vẫn cần shared API/SPI type identity, class loader và lifecycle unload.

## 7. Kết hợp mô hình instance với cơ chế đồng bộ

### 7.1. Singleton: thread-safe hoặc serialized

Một singleton nên có giao diện công khai phù hợp:

- **Thread-safe**: có thể chạy `process` đồng thời; state mutable được bảo vệ bằng atomic/lock/immutable design.
- **Serialized**: host hoặc plugin nắm một mutex trong suốt mỗi invocation; chỉ một invocation được chạy một lúc.
- **Stateless**: lý tưởng cho singleton, nhưng nếu có shared cache/metric bên trong thì vẫn cần xét thread safety và cleanup.

Với plugin không thread-safe, cách đơn giản ở host có thể là một **per-plugin mutex** bên trong lifecycle gate. Tuy nhiên không giữ khóa global registry trong khi gọi plugin; phạm vi khóa càng lớn, nguy cơ deadlock và độ trễ càng cao. Nếu plugin thao tác I/O dài, pool instance riêng có thể tốt hơn serialization.

### 7.2. Per-call: isolation tốt hơn nhưng không miễn nhiễm race

Mỗi invocation có instance riêng sẽ tránh race trên field của các instance khác nhau, **nếu instance không tham chiếu tới shared mutable state**. Một plugin per-call vẫn có thể truy cập static map, shared database, host-provided cache, executor hoặc singleton service. Vì vậy scope instance không thay thế giao thức transaction và đồng bộ external resource.

Đừng coi per-call tự động an toàn về tài nguyên. Cần close trong `finally`, kiểm soát giới hạn số instance **đồng thời** và từ chối/backpressure khi quá tải. Với request đến hàng nghìn lượt/giây, khởi tạo heavy client trên mỗi request có thể gây CPU/memory pressure đáng kể.

### 7.3. Pool: instance độc quyền cho từng borrower

Quy tắc pool cơ bản:

```text
onRequest:
    acquire permit (bounded wait + timeout)
    lease = pool.borrow()
    try:
        validate lease
        result = lease.plugin.process(request)
        return result
    finally:
        if lease healthy:
            reset per-request state
            pool.return(lease)
        else:
            pool.discardAndReplaceWithinLimit(lease)
        release permit
```

Đây là **pseudocode**, không phải class Java có sẵn. Pool phải sở hữu resource, reset state trước khi giao cho borrower khác, bảo vệ double-return và rò rỉ lease, chỉ đóng instance khi không ai đang dùng. Một instance **không thread-safe** chỉ được cấp cho **một** borrower tại một thời điểm; không chỉ trông cậy `ConcurrentLinkedQueue` sẽ đảm bảo điều đó nếu workflow borrow/return sai.

Nếu instance bị lỗi giữa request, đừng trả lại pool như healthy object mà không kiểm tra. Khi pool shutdown, hãy ngừng phát lease, chờ hoặc hủy lease còn hiệu lực theo deadline, rồi đóng các object còn lại.

### 7.4. Per-tenant: đảm bảo phân vùng dữ liệu

Một registry per-tenant có thể map `TenantId → PluginSession`, nhưng phải xét:

- Tenant ID được xác thực từ host context, không đọc từ chuỗi script/plugin tự khai báo.
- Áp quota theo tenant và quota tổng; không để tenant bất kỳ tạo vô hạn instance.
- Nếu hai request của **cùng tenant** truy cập chung mutable state, vẫn cần đồng bộ.
- Nếu plugin instance giữ secret/credential riêng tenant, phải reset/destroy đúng lifetime và không chuyển sang tenant khác.
- Tenant eviction, idle TTL và unload phải phối hợp với in-flight calls để không đóng session đang xử lý.

## 8. ClassLoader, static fields và bản nâng cấp plugin

Trong Java, danh tính class gắn với binary name và **defining class loader**. Một class plugin có static singleton:

```java
public final class GlobalState {
    private static final java.util.concurrent.atomic.AtomicInteger COUNTER =
            new java.util.concurrent.atomic.AtomicInteger();

    public static int next() {
        return COUNTER.incrementAndGet();
    }
}
```

Đây là một **đoạn class minh họa**, không phải contract được JDK cung cấp. Nếu `GlobalState` được định nghĩa bởi hai plugin class loaders khác nhau, mỗi class definition có **static field riêng**. Nếu class lại được parent loader định nghĩa (do delegation) thì nhiều plugin có thể vô tình chia sẻ chính một static state.

Do đó, không dùng static singleton làm “global shared state” mà không biết class loader ownership. Nếu muốn chia sẻ counters/cache giữa nhiều generation của plugin, đặt dịch vụ đó trong **host-owned API/service** và xác định lifecycle riêng; không truyền trực tiếp mutable object thiếu đồng bộ qua ranh giới.

### 8.1. Hợp đồng chung qua boundary

Host có thể định nghĩa `Plugin`, `PluginFactory`, `PluginContext` trong loader cha. Plugin implementation ở loader con phải sử dụng **cùng định nghĩa type** để host có thể cast và gọi. Những DTO, callback và exception đi qua API cũng cần chính sách type identity nhất quán.

Mô hình lý tưởng:

```text
HostClassLoader
    |- api.Plugin
    |- api.PluginFactory
    |- api.Request, api.Response
    |- api.HostServices
             ^
             | parent delegation
    PluginLoader (generation 42)
    |- impl.MyPlugin
    |- private dependency v2
```

Một plugin có thể có **1 instance trong generation 42**, nhưng khi triển khai generation 43, plugin loader và singleton mới là hai thực thể riêng. Host phải giữ ranh giới rõ: không để object riêng generation cũ đi vào registry mới ngoài mục đích đã kiểm soát, và không đóng nhầm resource dùng chung của host.

### 8.2. ServiceLoader không quy định số instance tự động

`ServiceLoader` tìm và khởi tạo provider theo cơ chế SPI. Nó **không phải một plugin lifecycle manager** có sẵn với chính sách per-tenant, pooling, concurrency và safe shutdown. Việc gọi `iterator()`, `stream()` hoặc `reload()` cần được hiểu theo khả năng cache/discovery của `ServiceLoader` cụ thể; không mặc định mỗi lookup tạo instance mới hoặc mọi instance sẽ tự đóng đúng lúc.

Nếu hệ thống cần `Scope` rõ ràng, cách phổ biến là coi provider là **factory/descriptor** rồi host quyết định khi nào tạo plugin implementation, khi nào đăng ký, và khi nào dispose. Đừng đưa shared state của host vào constructor provider tùy ý mà không có boundary API và ownership.

## 9. Kiểm thử đồng thời và vòng đời

### 9.1. Các tình huống cần có test

| Tình huống | Bất biến mong muốn |
| --- | --- |
| 100 lời gọi concurrent vào singleton thread-safe | Số instance = 1; tất cả kết quả đúng; counter không mất |
| Singleton không thread-safe | Host serialize hoặc từ chối cấu hình, không silent race |
| Per-call với 100 request | 100 lần tạo (nếu không retry) và cleanup đúng; không rò instance |
| Per-tenant nhiều tenant | State không lẫn; quota theo tenant đúng |
| Pool size 4, 20 request | Không quá 4 lease đồng thời; borrower độc quyền |
| Stop trong lúc có in-flight | Không đóng instance đang dùng; request mới bị reject hoặc được route generation mới |
| Stop gọi lặp lại | Idempotent, không double close/double release |
| Initialization thất bại giữa chừng | Resource đã tạo được cleanup theo ownership |
| Update generation trong load cao | Không lỗi class identity, không phục vụ mới bằng instance đã stopped |
| Plugin callback gọi registry/stop | Không deadlock do lock order hoặc read→write upgrade |
| Request bị cancel/timeout | Counter in-flight và lease được thu hồi trong `finally` |
| Static caches/ThreadLocal sau reload | Không giữ plugin loader cũ ngoài ý muốn |

**Đừng chỉ test kết quả cuối cùng sau khi mọi thread đã xong.** Test race cần nhiều lượt chạy và đồng bộ start bằng `CountDownLatch`/`CyclicBarrier`, thử dừng giữa lúc đang chạy bằng latch có điều khiển, ghi nhận max concurrent calls, và xác nhận không có lời gọi bắt đầu **sau** cutover. `Thread.sleep(...)` với thời gian tùy ý thường làm test cạnh tranh chập chờn.

### 9.2. Metrics tối thiểu

Nên ghi metric có label plugin ID, generation, version và scope (có kiểm soát cardinality):

- `plugin_instances_live` và `plugin_instances_created_total`.
- `plugin_invocations_in_flight` và `plugin_invocations_completed_total`.
- `plugin_invocations_failed_total`, phân biệt lỗi do plugin và lỗi lifecycle.
- `plugin_queue_depth`, `plugin_rejected_total`, `plugin_wait_duration`.
- `plugin_start_duration`, `plugin_stop_duration` và số generation còn giữ reference.
- Pool borrow timeout, unhealthy/evicted instances, circuit-breaker state.

Nếu plugin có dữ liệu tenant nhạy cảm, không tự động gắn toàn bộ tenant ID/request ID vào metrics label gây cardinality vô hạn hoặc lộ thông tin; có thể dùng tracing/log với chính sách truy cập phù hợp.

### 9.3. Log transition theo generation

Khi xảy ra race, log trình tự `CREATED → RUNNING → QUIESCING → STOPPED` của **generation cụ thể**, cùng số in-flight, số instance live và nguyên nhân stop. Nếu chỉ log tên plugin mà không ghi generation, hai lần deploy song song rất dễ bị nhầm cùng một instance.

Đồng hồ và thứ tự sự kiện giữa nhiều thread có thể không thể suy luận chỉ bằng timestamp tường minh; nên dùng request/trace IDs, sequence numbers hoặc correlation hợp lệ khi cần dựng lại luồng.

## 10. Những sai lầm thường gặp

### 10.1. “Một instance” nghĩa là không có race?

Sai. Một singleton có thể nhận hàng trăm lời gọi đồng thời. Số instance bằng 1 không giới hạn số thread gọi method. Nếu instance không thread-safe, phải serialize hoặc thay đổi scope.

### 10.2. “Mỗi request một instance” nghĩa là không còn shared state?

Sai. Các instance vẫn có thể dùng static fields, host-injected cache, cùng database row, shared transaction hoặc native library. Phải liệt kê **tất cả shared mutable state**, không chỉ field trong plugin.

### 10.3. “Có AtomicInteger là an toàn”?

Chỉ đúng đối với thao tác của chính giá trị đó. Nếu invariant yêu cầu `processed <= admitted` và hai biến được cập nhật riêng, reader có thể thấy snapshot không nhất quán. Cần thiết kế atomic state transition hoặc khóa phù hợp.

### 10.4. “volatile running” làm stop an toàn?

Sai nếu check `running` và sử dụng plugin là hai thao tác tách biệt không được phối hợp với close. Cần admission gate, lease/quiescence hoặc một state machine có kiểm soát. `volatile` giúp visibility, không tự cung cấp phép “check-and-enter” nguyên tử.

### 10.5. “Synchronized ở plugin” giải quyết mọi deadlock?

Không. Đồng bộ đúng trên nội bộ plugin chưa xử lý khóa registry, host callback, stop/cancel, I/O chờ vô hạn, thread pool starvation hay reentrant close. Phân tích lock graph và giới hạn phạm vi khóa là bắt buộc.

### 10.6. “Đóng ClassLoader là unload ngay”

Sai. Với `URLClassLoader`, `close()` giải phóng tài nguyên mà loader quản lý, nhưng class/instance vẫn có thể còn sống khi static cache, thread, TCCL, listener hoặc host registry giữ tham chiếu. JVM chỉ có thể thu hồi class/loader khi điều kiện GC phù hợp.

### 10.7. “ClassLoader riêng là sandbox”

Sai. Phân tách class loader giúp namespace/version/lifecycle, không tự hạn chế plugin đọc file, mở mạng hay sử dụng những quyền runtime được cấp. Nếu plugin không tin cậy, cần boundary như tiến trình riêng, authorization, quotas và hạn chế hệ điều hành, ngoài chính sách concurrency.

## 11. Checklist thiết kế trước khi chấp nhận một plugin

1. **Hợp đồng số lượng:** plugin dùng `SINGLETON`, `PER_CALL`, `PER_SESSION`, `PER_TENANT` hay `POOLED`? Định nghĩa “một” theo host, generation và tenant cho rõ.
2. **Tài nguyên:** chi phí create/start/close? Ai sở hữu connection, executor, file, thread và cache? Khi cleanup fail xử lý thế nào?
3. **Thread safety:** một instance có hỗ trợ concurrent invocations không? Host có bảo đảm serialize nếu không?
4. **Shared state:** immutable config, state từng request, tenant, global, static và external state được phân loại rõ?
5. **Concurrency limit:** max in-flight, max live instances, max queue, thời gian chờ và từ chối khi quá tải?
6. **Lifecycle state machine:** transition hợp lệ, publish safely, quiesce, stop idempotent và tránh invocation sau close?
7. **Synchronization:** chọn atomic, mutex, read/write gate, lease/condition đúng invariant; không dùng `volatile` để che race?
8. **Lock order:** tránh callback giữ lock lớn, upgrade read→write và chờ vô hạn?
9. **Failure/cancellation:** mọi path đều cleanup trong `finally`; metric và root cause không bị mất?
10. **Tenant isolation:** identity được host xác thực, state/secret không leak và quota hợp lý?
11. **Class identity:** API/SPI/DTO chung dùng parent loader, implementation private có loader/generation phù hợp?
12. **Reload/unload:** tạo generation mới, route đúng, chờ bản cũ drain, bỏ mọi tham chiếu/thread/TCCL không còn dùng?
13. **Test và giám sát:** có stress test, stop-under-load test, metrics instance live/created/in-flight, tracing theo generation?
14. **Ranh giới bảo mật:** không xem scope hay class loader là cơ chế hạn chế code không tin cậy.

**Kết luận:** quản lý vòng đời plugin đáng tin cậy bắt đầu từ **hợp đồng số lượng đối tượng** (một hay nhiều, trong phạm vi nào), **sở hữu trạng thái** (ai được chia sẻ gì) và **cơ chế đồng bộ** (các thread, admission và stop được phối hợp ra sao). Host nên giữ quyền thực thi policy, đo lường những đại lượng khác nhau như instance live/created/in-flight, chặn request mới trước khi đóng plugin và tách API/SPI chung khỏi implementation theo generation. Khi ba trục này được thiết kế cùng nhau, việc chạy đồng thời và nâng cấp plugin mới có thể an toàn và kiểm chứng được.