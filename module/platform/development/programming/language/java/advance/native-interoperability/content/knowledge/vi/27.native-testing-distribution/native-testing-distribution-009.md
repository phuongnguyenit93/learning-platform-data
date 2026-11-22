# Kiểm thử đóng nhiều lần, truy cập sau đóng và callback đến muộn trong Java/native interoperability

## 1. Mục tiêu và phạm vi của bài kiểm thử

Khi Java làm việc với một thư viện C/C++ qua JNI hoặc Foreign Function & Memory (FFM) API, một đối tượng Java có thể chỉ là **wrapper sở hữu** con trỏ, file descriptor, native handle, vùng nhớ ngoài heap hoặc hàm callback. Nếu wrapper được đóng sai thời điểm, lỗi thường nặng hơn một `IllegalStateException` thông thường: *double free*, *use-after-free* (UAF), đọc sai dữ liệu, leak, deadlock hoặc crash toàn bộ JVM.

Bài này tập trung vào ba tình huống cần kiểm thử trước khi phân phối một Java/native library:

1. **Đóng nhiều lần:** gọi `close()` hai lần, nhiều lần, đồng thời từ nhiều thread và khi dọn dẹp lỗi. Phải giải phóng native resource **tối đa một lần**; hành vi lần đóng tiếp theo phải đúng hợp đồng API.
2. **Truy cập sau đóng:** gọi thao tác Java/native sau khi hoàn tất đóng; đồng thời thử race giữa một thao tác đang chạy và một thread bắt đầu đóng. Phải **chặn trước khi chuyển con trỏ đã giải phóng vào native code**.
3. **Callback đến muộn:** callback đã được lên lịch hoặc đang chạy khi gọi `close()`; callback đến trong giai đoạn shutdown và cả sau khi đóng xong. Không được gọi listener không còn hợp lệ hoặc dùng `jobject`/function pointer đã giải phóng.

Ngữ cảnh cấp 1 là **Kiểm thử và phân phối**: vì vậy bài không dừng ở giải thích lifecycle. Ta cần một *test oracle* rõ ràng, cách chạy thử tự động lặp lại, điều kiện nghiệm thu trước release và quan sát lỗi native bằng công cụ phù hợp.

> **Nguyên tắc cốt lõi:** kiểm tra trạng thái Java chỉ bảo vệ tầng Java. Trước khi giải phóng bộ nhớ/registration native, cần có một cam kết từ native runtime rằng **không còn worker hoặc callback nào có thể sử dụng vùng nhớ đã thu hồi**.

## 2. Xác định hợp đồng sở hữu trước khi viết test

Một test tốt bắt đầu từ hợp đồng giữa Java wrapper và thư viện native, không suy đoán từ cách hiện tại của implementation.

| Câu hỏi hợp đồng | Cần ghi rõ |
| --- | --- |
| Ai sở hữu native handle? | Wrapper độc quyền, shared ownership theo reference count, hay borrowed handle chỉ mượn? |
| `close()` có idempotent không? | Wrapper chủ động định nghĩa “đóng lần sau là no-op” hay cố ý ném exception để phát hiện bug? |
| Sau `close()` được phép làm gì? | Getter metadata thuần Java có thể hợp lệ; mọi thao tác cần native pointer phải bị từ chối. |
| Native operation đang chạy thì sao? | `close()` đợi in-flight operations kết thúc, hủy an toàn, hay trả lỗi “busy”? |
| Callback được chuyển sang thread nào? | Event loop, Java executor, native worker có gắn JVM, hoặc thread của bên gọi? |
| Shutdown có đảm bảo quiescence? | `unregister` chỉ ngăn callback mới hay đồng thời **đợi callback cũ hoàn tất**? |
| Lỗi khi hủy resource thì sao? | Có trạng thái `FAILED`/retry có kiểm soát, hay chuyển thành lỗi không khôi phục; không đánh dấu “đã free” khi chưa biết. |
| Handle có thể được tái sử dụng? | Cần identifier thế hệ (*generation*) để tránh callback cũ nhầm với session mới (ABA). |

Đối với wrapper JNI tự thiết kế, **idempotent close** thường thuận tiện cho `try-with-resources`, cleanup trong `finally` và shutdown đồng thời. Tuy nhiên, đây là **hợp đồng của wrapper**, không phải quy tắc áp đặt cho mọi API native.

**Điểm khác biệt của FFM:** từ JDK 22, `Arena.ofConfined()` và `Arena.ofShared()` đóng được một lần; **`Arena.close()` không idempotent**. Đóng arena đã đóng sẽ ném `IllegalStateException`. Một wrapper bao ngoài có thể tự thiết kế idempotence mà vẫn chỉ đóng underlying arena đúng một lần. `Arena.ofGlobal()` và `Arena.ofAuto()` có lifecycle riêng, không thể coi như arena đóng thủ công.

### Bảng trạng thái khuyến nghị cho native wrapper

```text
            create succeeds
NEW --------------------------------> OPEN
                                       |
                                       | close() starts
                                       v
                                    CLOSING
                                     |   |
                  reject new use ----+   +---- stop registration
                                         |     wait for in-flight work
                                         |     free exactly once
                                         v
                                      CLOSED
```

Đối với một wrapper có hợp đồng *close idempotent*:

- `OPEN` → `OPEN`: thao tác thông thường; việc bắt đầu operation cần một **lease/in-flight counter** trước khi rời vùng đồng bộ.
- `OPEN` → `CLOSING`: một thread giành quyền điều phối close; ngăn operation/callback mới được chấp nhận.
- `CLOSING` → `CLOSED`: hủy đăng ký callback, đợi mọi operation/callback đã nhận hoàn thành, đồng bộ với worker native, hủy resource một lần, sau đó công bố closed.
- `CLOSING` và `CLOSED`: close lần tiếp theo chờ hoặc trả về theo hợp đồng; không thực hiện `free` thêm.
- Trong mọi trạng thái ngoài `OPEN`, operation mới ném `IllegalStateException` hoặc kết quả lỗi được tài liệu hóa. Callback muộn được **bỏ qua an toàn hoặc báo canceled**, không đụng native handle cũ.

Nếu bước hủy lỗi, một hệ thống thực tế phải thiết kế trạng thái lỗi riêng (`FAILED`) và chính sách retry/cleanup. Không coi một `finally { state = CLOSED; }` là bằng chứng native đã giải phóng thành công; ví dụ runnable ở phần sau dùng backend giả định thao tác unregister/destroy không thất bại để tập trung minh họa race.

## 3. Ma trận test cần có

| ID | Sắp xếp ban đầu | Kích hoạt | Điều kiện đạt |
| --- | --- | --- | --- |
| T01 | Resource `OPEN` | `close(); close(); close();` | Native destructor gọi đúng **1 lần**; các lần sau theo đúng contract. |
| T02 | Resource `OPEN` | 10 thread đồng thời gọi `close()` | Không double free, không treo; tất cả thread kết thúc trong deadline. |
| T03 | Resource `CLOSED` | `read/write/invoke` | Từ chối tại Java boundary; số lần gọi backend native không tăng. |
| T04 | Operation đã vào native, đang chặn bằng latch | Thread khác gọi `close()` | Resource chưa free cho đến khi operation trả về hoặc hủy theo protocol. |
| T05 | Callback đã được accept và đang xử lý | Thread khác gọi `close()` | Close đợi callback hoàn thành (hoặc protocol cancellation đã định nghĩa), rồi mới free. |
| T06 | `close()` đã chuyển sang `CLOSING` | Native callback đến | Callback không còn được deliver cho listener; không đọc handle bị đóng. |
| T07 | `close()` hoàn tất | Callback muộn/đã queued | Bỏ qua có kiểm soát; không crash/UAF, không gọi listener. |
| T08 | Handle cũ đã free, native tái sử dụng địa chỉ cho handle mới | Callback cũ mang generation cũ | Event cũ bị từ chối, không gắn nhầm session mới. |
| T09 | Native hủy registration nhưng callback vẫn in-flight | `close()` và callback đua nhau | Có hàng rào *quiescence* thật ở native, không giải phóng context quá sớm. |
| T10 | Trình tạo native lỗi giữa chừng | Cleanup sau lỗi và close lặp | Không leaked/duplicate cleanup; chỉ free thứ đã acquire. |
| T11 | Hủy native ném lỗi hoặc báo trạng thái không xác định | `close()`, rồi retry | Ghi nhận lỗi và trạng thái chính xác; không âm thầm gọi free hai lần. |
| T12 | Trên FFM shared/confined arena | Access hoặc close sai thời điểm/thread | Đúng exception của FFM; không gán semantics wrapper JNI sang Arena. |

Mỗi test cần quan sát **cả hai phía**: Java assertions (exception, số callback được nhận/bỏ, state) **và** native evidence (allocation/free counters, sanitizer, logs hoặc per-handle generation). Chỉ dựa vào một giá trị boolean `closed` là chưa đủ.

## 4. Ví dụ Java 17+ tự chạy: kiểm thử vòng đời bằng fake native backend

Bài lab dùng **một file Java thuần** để kiểm thử state machine một cách quyết định và không cần thư viện `.so/.dll/.dylib`. `FakePort` đóng vai trò JNI/native backend với bộ đếm `destroy`; trong production, thay interface này bằng JNI bindings và kiểm thử thêm bằng native instrumentation. Test dùng `CountDownLatch` và `Future.get(timeout)` thay cho “ngủ đại vài giây” để tạo race chủ động.

**Tạo file `NativeLifecycleTest.java`:**

```java
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.ConcurrentHashMap;

public final class NativeLifecycleTest {
    enum State { OPEN, CLOSING, CLOSED }

    interface NativePort {
        long create();
        void execute(long handle);
        void unregisterCallbacks(long handle);
        void destroy(long handle);
    }

    static final class FakePort implements NativePort {
        private final AtomicLong ids = new AtomicLong(900);
        private final ConcurrentHashMap<Long, AtomicBoolean> live =
                new ConcurrentHashMap<>();
        final AtomicInteger executions = new AtomicInteger();
        final AtomicInteger unregisters = new AtomicInteger();
        final AtomicInteger destroys = new AtomicInteger();

        public long create() {
            long h = ids.incrementAndGet();
            live.put(h, new AtomicBoolean(true));
            return h;
        }

        public void execute(long h) {
            AtomicBoolean alive = live.get(h);
            if (alive == null || !alive.get()) {
                throw new AssertionError("use after native free");
            }
            executions.incrementAndGet();
        }

        public void unregisterCallbacks(long h) {
            unregisters.incrementAndGet();
        }

        public void destroy(long h) {
            AtomicBoolean alive = live.get(h);
            if (alive == null || !alive.compareAndSet(true, false)) {
                throw new AssertionError("double native free");
            }
            destroys.incrementAndGet();
        }
    }

    static final class NativeOwner implements AutoCloseable {
        private final Object gate = new Object();
        private final NativePort port;
        private final long handle;
        private State state = State.OPEN;
        private int inFlight;
        private int delivered;
        private int ignored;
        // Test-only instrumentation; do not expose this in a public API.
        final CountDownLatch closeStarted = new CountDownLatch(1);

        NativeOwner(NativePort port) {
            this.port = port;
            this.handle = port.create();
        }

        void use(Runnable beforeNativeCall) {
            synchronized (gate) {
                if (state != State.OPEN) {
                    throw new IllegalStateException("resource is closing");
                }
                inFlight++;
            }
            try {
                beforeNativeCall.run();
                port.execute(handle);
            } finally {
                finishOperation();
            }
        }

        // Simulates a Java callback delivered through a valid native registration.
        void onCallback(Runnable listener) {
            synchronized (gate) {
                if (state != State.OPEN) {
                    ignored++;
                    return;
                }
                inFlight++;
            }
            try {
                listener.run();
                synchronized (gate) {
                    delivered++;
                }
            } finally {
                finishOperation();
            }
        }

        private void finishOperation() {
            synchronized (gate) {
                inFlight--;
                if (inFlight == 0) gate.notifyAll();
            }
        }

        int ignoredCallbacks() {
            synchronized (gate) {
                return ignored;
            }
        }

        int deliveredCallbacks() {
            synchronized (gate) {
                return delivered;
            }
        }

        @Override
        public void close() {
            boolean interrupted = false;
            synchronized (gate) {
                if (state == State.CLOSED) return;
                if (state == State.CLOSING) {
                    while (state != State.CLOSED) {
                        try {
                            gate.wait();
                        } catch (InterruptedException e) {
                            interrupted = true;
                        }
                    }
                    if (interrupted) Thread.currentThread().interrupt();
                    return;
                }
                state = State.CLOSING;
                closeStarted.countDown();
            }

            try {
                port.unregisterCallbacks(handle);
                synchronized (gate) {
                    while (inFlight != 0) {
                        try {
                            gate.wait();
                        } catch (InterruptedException e) {
                            interrupted = true;
                        }
                    }
                }
                port.destroy(handle);
            } finally {
                synchronized (gate) {
                    state = State.CLOSED;
                    gate.notifyAll();
                }
                if (interrupted) Thread.currentThread().interrupt();
            }
        }
    }

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void await(CountDownLatch latch) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError("latch timed out");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new AssertionError(e);
        }
    }

    static void mustReject(Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("closed resource accepted an operation");
        } catch (IllegalStateException expected) {
            // This is the specified rejection at the Java boundary.
        }
    }

    static void mustStillBeWaiting(Future<?> future) throws Exception {
        try {
            future.get(100, TimeUnit.MILLISECONDS);
            throw new AssertionError("closed before in-flight callback finished");
        } catch (TimeoutException expected) {
            // The close is intentionally waiting for its in-flight lease.
        }
    }

    static void testSequential() {
        FakePort port = new FakePort();
        NativeOwner owner = new NativeOwner(port);
        owner.use(() -> { });
        owner.onCallback(() -> { });
        owner.close();
        owner.close();
        owner.close();

        mustReject(() -> owner.use(() -> { }));
        owner.onCallback(() -> {
            throw new AssertionError("late callback must not run");
        });
        check(port.executions.get() == 1, "unexpected native execute");
        check(port.destroys.get() == 1, "resource freed more than once");
        check(port.unregisters.get() == 1, "unregistered more than once");
        check(owner.deliveredCallbacks() == 1, "lost early callback");
        check(owner.ignoredCallbacks() == 1, "late callback not ignored");
        System.out.println("sequential: PASS");
    }

    static void testRace() throws Exception {
        FakePort port = new FakePort();
        NativeOwner owner = new NativeOwner(port);
        CountDownLatch useStarted = new CountDownLatch(1);
        CountDownLatch allowUse = new CountDownLatch(1);
        CountDownLatch callbackStarted = new CountDownLatch(1);
        CountDownLatch allowCallback = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            Future<?> use = pool.submit(() -> owner.use(() -> {
                useStarted.countDown();
                await(allowUse);
            }));
            Future<?> callback = pool.submit(() -> owner.onCallback(() -> {
                callbackStarted.countDown();
                await(allowCallback);
            }));
            await(useStarted);
            await(callbackStarted);

            Future<?> firstClose = pool.submit(owner::close);
            await(owner.closeStarted);
            Future<?> repeatedClose = pool.submit(owner::close);

            mustReject(() -> owner.use(() -> { }));
            owner.onCallback(() -> {
                throw new AssertionError("callback during close delivered");
            });

            allowUse.countDown();
            use.get(2, TimeUnit.SECONDS);
            mustStillBeWaiting(firstClose);
            check(port.destroys.get() == 0,
                    "native destroy happened before callback completed");

            allowCallback.countDown();
            callback.get(2, TimeUnit.SECONDS);
            firstClose.get(2, TimeUnit.SECONDS);
            repeatedClose.get(2, TimeUnit.SECONDS);
            owner.close();

            owner.onCallback(() -> {
                throw new AssertionError("callback after close delivered");
            });

            check(port.executions.get() == 1, "lost native operation");
            check(port.destroys.get() == 1, "double free under race");
            check(port.unregisters.get() == 1, "double unregister");
            check(owner.deliveredCallbacks() == 1, "lost accepted callback");
            check(owner.ignoredCallbacks() == 2, "late callbacks not rejected");
            System.out.println("race: PASS");
        } finally {
            allowUse.countDown();
            allowCallback.countDown();
            pool.shutdownNow();
            check(pool.awaitTermination(2, TimeUnit.SECONDS),
                    "threads did not terminate");
        }
    }

    public static void main(String[] args) throws Exception {
        testSequential();
        testRace();
    }
}
```

**Biên dịch và chạy:**

```bash
javac NativeLifecycleTest.java
java NativeLifecycleTest
```

**Stdout mong đợi khi test thành công:**

```text
sequential: PASS
race: PASS
```

Nếu bất kỳ assertion sai, chương trình ném `AssertionError` và không được tính PASS. Deadline 2 giây chỉ phù hợp lab chạy trên máy bình thường; trong CI có môi trường ảo hóa chậm, có thể đặt timeout cấu hình được và lưu nguyên nhân timeout, thay vì lặp tùy tiện. `mustStillBeWaiting` dùng timeout ngắn để chứng minh close còn chờ trong một tình huống đã chặn callback bằng latch.

### Tại sao ví dụ chống được các race cụ thể?

- `inFlight++` thực hiện **trong cùng monitor** với kiểm tra `state == OPEN`. Nếu operation đã nhận lease trước close, nó được phép chạy; close phải đợi `inFlight == 0`.
- Khi close chuyển `OPEN → CLOSING` trong monitor, mọi operation/callback tới sau **không được cấp lease**, kể cả khi native handle chưa bị destroy.
- Không giữ Java monitor trong lúc `port.execute` hoặc gọi user listener. Làm vậy tránh nguy cơ close giữ lock trong lúc native đang chờ thread callback khác; tuy nhiên các phương án shutdown phức tạp vẫn cần phân tích deadlock và reentrancy riêng.
- Chỉ thread đầu tiên từ `OPEN` sang `CLOSING` gọi `unregisterCallbacks` và `destroy`; close lặp trong giai đoạn `CLOSING` chờ đến `CLOSED`. Các lệnh free/unregister được đếm bằng atomics.
- Test tạo **một use in-flight** và **một callback in-flight**, yêu cầu close vẫn chờ khi use đã kết thúc nhưng callback chưa xong, sau đó xác minh giải phóng đúng một lần.
- Callback tới trong `CLOSING` và sau `CLOSED` bị loại mà không gọi listener. Lớp `FakePort` kiểm tra không bao giờ `execute` sau free.

**Giới hạn chủ ý của bài lab:** `FakePort.unregisterCallbacks` không tự sinh native thread và không chứng minh native registration đã dừng. Ví dụ giả định `unregisterCallbacks`/`destroy` thành công, không mô phỏng native release failure, cancellation/reentrancy hay một callback đang ở C nhưng chưa vào Java. Khi tích hợp JNI thực, cần thêm **native worker join/quiescence** trước khi gọi `destroy` hoặc `DeleteGlobalRef`; các điều kiện này phải được xác minh trong test integration, không thể suy ra từ PASS của fake.

## 5. Quy trình hủy callback thật trong JNI

Một JNI callback có thể mang theo native context pointer, `JavaVM*`, đối tượng Java được giữ bằng global reference (`jobject`) và một worker thread C/C++. Thứ tự hủy phù hợp phải đến từ API native cụ thể. Mẫu chung:

```text
Java close()
    |
    +-- atomically transition OPEN -> CLOSING
    +-- reject new Java operations and callbacks
    +-- native_unregister_callback(handle)
    +-- signal native workers to stop accepting new work
    +-- join/drain in-flight native workers and callbacks
    +-- delete JNI global references (using valid JNIEnv* on calling thread)
    +-- native_destroy(handle) exactly once
    +-- publish CLOSED / wake waiting close callers
```

Đây là **sơ đồ thứ tự khái niệm**, không phải C code có thể chạy độc lập. Một API native có thể cần hủy context trước ref hoặc ngược lại, nhưng bắt buộc bảo đảm **không ai còn sử dụng đối tượng trước khi giải phóng nó**.

### 5.1. Những điều JNI phải giữ đúng

- Một local reference JNI thường chỉ sống trong phạm vi của lời gọi native hiện tại. Nếu native worker muốn giữ callback Java để gọi sau đó, phải tạo `NewGlobalRef` (hoặc cơ chế tham chiếu theo tài liệu), và xóa chính xác một lần bằng `DeleteGlobalRef` **khi đã hết mọi lời gọi callback có thể dùng ref ấy**.
- `JNIEnv*` là **theo thread**, không được lưu rồi sử dụng ở thread C khác. Worker không do Java tạo cần dùng `JavaVM*` và `AttachCurrentThread` (hoặc daemon variant khi phù hợp) để có `JNIEnv*` của chính nó; detach khi kết thúc theo contract. Không detach ngay khi còn Java frames trên stack.
- Sau `DeleteGlobalRef`, native không được dùng lại reference đã giải phóng, kể cả khi Java wrapper đã quyết định “bỏ callback”.
- Nếu C gọi một Java callback và Java ném exception, JNI phải kiểm tra/giải quyết pending exception theo hợp đồng. Không tùy tiện thực hiện thêm JNI calls trong trạng thái pending exception, không để native worker tiếp tục như thể callback đã thành công.
- Các địa chỉ con trỏ, handle và callback context mang qua `long` không được xem là an toàn chỉ nhờ Java `volatile closed`. Nếu Java kiểm tra `!closed` rồi thread khác free ngay trước khi JNI dùng handle, đó là classic check-then-use race.

**Deadlock dễ gặp:** thread A gọi `close()` và đợi worker B kết thúc; worker B gọi Java listener và đợi A xử lý trên cùng event loop đang bị A chặn. Cần quy ước callback delivery có thể chạy ở thread khác, thực hiện shutdown không block event loop, hoặc tổ chức completion theo hai pha. **Không gọi `close()` trực tiếp từ callback nếu close chờ chính callback đó drain**, trừ khi implementation có giao thức reentrancy đặc biệt.

### 5.2. Trường hợp callback đến muộn đặc biệt nguy hiểm

Một callback có thể được enqueue **trước** `unregister`, nhưng thực thi **sau** khi `unregister` trả về. Vì vậy phải kiểm tra API nói rõ “unregister returns only after callbacks have quiesced” hay chỉ “future dispatch is disabled”. Với loại thứ hai cần **join/flush/acknowledgement** khác và vẫn giữ callback context sống cho đến khi đạt quiescence.

Một callback có thể tồn tại **ngoài Java** trước khi bước vào `onCallback`; Java `inFlight` chỉ đếm callback **đã vào phương thức**. Giải phóng global ref hoặc function pointer ngay khi Java `inFlight == 0` là sai nếu native vẫn có callback đang bay tới.

Giải pháp điển hình là reference counting hoặc epoch/generation được quản lý **ở phía native**, kết hợp ngừng registration, ngừng worker, chờ các callback đang giữ lease native thoát, rồi mới free. Khi callback nhận event, nó kiểm tra context lifetime/generation **trước khi dereference**. Không được đọc generation bằng cách dereference một context pointer đã free: cần một control block còn sống đủ lâu hoặc một handle registry thread-safe riêng.

### 5.3. ABA: con trỏ được tái sử dụng

Giả sử session A có địa chỉ `0x1000`, đóng A và free. Allocator dùng lại `0x1000` cho session B. Callback cũ của A mang `0x1000` đến muộn, tìm thấy B và gửi dữ liệu nhầm. Kiểm tra “con trỏ != 0” hoặc so sánh địa chỉ không phân biệt được hai lifetime.

Một protocol có thể dùng cặp `(slotId, generation)`; mỗi lần tái sử dụng slot tăng generation, callback chỉ được chấp nhận khi đúng generation và session còn `OPEN`. Registry phải đồng bộ; kiểm tra & lấy lease trước khi access, và không cho xóa backing context khi còn lease. Test T08 chủ động ép tái sử dụng slot để xác minh event cũ bị loại.

## 6. FFM API: các bài test có ý nghĩa khác với JNI

Với **JDK 22+**, FFM cung cấp `Arena`/`MemorySegment` và kiểm tra lifetime khi truy cập segment qua Java API. Ví dụ độc lập sau đây cần JDK 22+ (không chạy trên JDK 17):

**File `ArenaLifetimeTest.java`:**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaLifetimeTest {
    public static void main(String[] args) {
        MemorySegment segment;
        try (Arena arena = Arena.ofConfined()) {
            segment = arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 7);
            System.out.println("value=" +
                    segment.get(ValueLayout.JAVA_INT, 0));
        }

        try {
            segment.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("access after close succeeded");
        } catch (IllegalStateException expected) {
            System.out.println("access after close: rejected");
        }

        Arena shared = Arena.ofShared();
        shared.close();
        try {
            shared.close();
            throw new AssertionError("double close succeeded");
        } catch (IllegalStateException expected) {
            System.out.println("double arena close: rejected");
        }
    }
}
```

**Chạy bằng JDK 22+:**

```bash
javac ArenaLifetimeTest.java
java ArenaLifetimeTest
```

**Stdout:**

```text
value=7
access after close: rejected
double arena close: rejected
```

FFM đảm bảo access qua `MemorySegment` được kiểm tra temporal safety, nhưng vẫn cần để ý:

- `Arena.ofConfined()` chỉ cho owner thread truy cập/đóng; gọi từ thread khác gây `WrongThreadException`. `Arena.ofShared()` cho phép nhiều thread truy cập, nhưng close có thể ném `IllegalStateException` nếu đang có access/downcall liên quan; test phải cover hành vi đồng thời.
- Khi đóng arena, segment do arena cấp không còn hợp lệ. **Đừng** thay đổi điều kiện test thành “FFM có thể đọc pointer tùy ý sau close” chỉ vì địa chỉ máy là một `long`.
- `Linker.upcallStub(...)` tạo function pointer gắn với lifetime của arena. Nếu C giữ function pointer rồi gọi sau khi arena đóng, nguy cơ crash JVM **vẫn tồn tại**; FFM không tự hủy đăng ký callback trong thư viện native.
- Một số thao tác như reinterpret từ địa chỉ tùy ý/unsafe native pointer có thể bỏ qua các kiểm tra vốn có của segment; cần tôn trọng owner và lifetime của vùng nhớ gốc.
- Nếu FFM downcall/upcall là restricted operation trên JDK đang dùng, cấu hình native access của module phù hợp với hướng dẫn JDK đích; đây là vấn đề **quyền truy cập**, độc lập với lỗi lifetime.

Không cố dùng `Arena.ofGlobal()` để “giải quyết” callback muộn; lifetime không giới hạn của global arena làm khó giải phóng tài nguyên và che giấu leak. Chọn đúng arena và protocol unregister/quiescence.

## 7. Kiểm thử race có hệ thống, tránh false PASS

**Dùng latch/barrier để tạo trật tự có chủ đích.** Ba điểm đáng kiểm chứng là: (a) operation đã nhận lease trước close, (b) close đã chuyển sang `CLOSING` khi operation vẫn bận, (c) callback mới đến sau transition. Tạo các test nhỏ có các điều kiện này sẽ ổn định hơn `Thread.sleep(...)`.

**Dùng deadline hữu hạn.** Mỗi latch, `Future.get` hoặc shutdown có timeout; nếu quá thời gian, test báo timeout với thread dump và trạng thái gần nhất thay vì treo CI. Một lần timeout có thể do máy tải cao; lặp trên môi trường được kiểm soát và thu evidence trước khi kết luận deadlock.

**Lặp nhiều interleaving.** Sau các test quyết định, chạy stress suite nhiều lần và thay đổi seed/lịch scheduling, bao gồm callback và close đồng thời, close từ nhiều thread, hủy trong khi đang khởi tạo, và executor shutdown. Nếu có thể, dùng model checker/concurrency-testing framework phù hợp để tìm thứ tự khó gặp; không suy ra an toàn tuyệt đối từ 1.000 lượt PASS.

**Native evidence:** tạo instrumentation per-handle ở C/C++ với atomic counters và trạng thái; log `allocate(handle, generation)`, `register`, `unregister`, `callback_enter`, `callback_exit`, `free`. Test không được kết thúc khi `freeCount==1` nhưng thread native vẫn còn chạy sau test; đợi quiescence trước assertions cuối.

### Chạy test thật với JVM và native instrumentation

Khi tích hợp JNI native, một số cách tăng khả năng phát hiện:

```bash
# Test class chỉ là ví dụ tên trong ứng dụng thật:
java -Xcheck:jni -cp app-and-tests.jar com.acme.NativeIntegrationTests
```

`-Xcheck:jni` kiểm tra nhiều lỗi sử dụng JNI (tham chiếu sai, pending exception, sai thread...), nhưng **không phải memory sanitizer tổng quát** và không chứng minh absence of UAF.

Với thư viện native C/C++, build riêng cho kiểm thử bằng AddressSanitizer/UndefinedBehaviorSanitizer khi toolchain và JVM runtime tương thích:

```bash
# Min họa cờ biên dịch/link dùng cho chính native library test build:
gcc -g -O1 -fno-omit-frame-pointer \
    -fsanitize=address,undefined -fPIC -shared \
    -o libbridge-test.so bridge.c
```

Đoạn trên là **mẫu build flags**, không thể chạy riêng nếu không có `bridge.c` của dự án cùng các JNI include/link dependencies. Sanitizer runtime phải được nạp đúng theo toolchain/OS; nếu gặp lỗi liên kết/preload, sửa harness trước khi suy luận về bug. Chạy trong **subprocess riêng**, kiểm tra exit code, stderr/sanitizer report, JVM fatal log (`hs_err_pid...`), OS core/dump nếu có. Một race native sai có thể crash cả JVM, nên không gộp tất cả test gây crash vào một tiến trình test runner chính.

### Tách test theo cấp

| Cấp test | Dùng để chứng minh | Giới hạn |
| --- | --- | --- |
| Java fake/unit (ví dụ phần 4) | API contract, thứ tự state, counter, late delivery tại Java boundary | Không thấy C global ref, thread đang sống và bộ nhớ thật |
| JNI/FFM integration với native test library | Native handle, callback registration, teardown, generation, ABI và thread attach | Cần harness thật và symbols của cùng build |
| Stress + sanitizer + subprocess | Nhiều interleaving hiếm, UAF/double free thực tế, process crash | Không chứng minh không còn bug; overhead thay timing |
| End-to-end trên artifact phát hành | Đóng theo đường đi thật của ứng dụng và thư viện đóng gói | Khó ép lịch scheduling; cần bổ sung các test cấp dưới |

## 8. Các lỗi phổ biến và hướng sửa

| Lỗi | Hệ quả | Hướng sửa |
| --- | --- | --- |
| `if (!closed) nativeUse(handle)` rồi thread khác free | Check-then-use race → UAF | Kiểm tra và lấy lease trong cùng vùng đồng bộ; close chờ lease |
| Chỉ dùng `AtomicBoolean.compareAndSet(false,true)` để đóng | Chặn double free nhưng không chặn native operation đã bắt đầu | Thêm lifecycle gate/in-flight count và quiescence native |
| `close()` gán `handle=0` sau khi free | Thread khác đã copy handle cũ vẫn dùng | Bảo vệ toàn bộ vòng đời sử dụng; không chỉ set 0 |
| `unregister` xong lập tức `DeleteGlobalRef` | Callback queued/worker đang chạy còn dùng jobject | Xác nhận unregister chặn dispatch mới **và** drain callback cũ trước khi delete ref |
| Giữ `JNIEnv*` trong global variable dùng từ thread khác | JNI thread-affinity violation, undefined behavior/crash | Giữ `JavaVM*`, attach đúng thread, lấy `JNIEnv*` của thread đó |
| Native worker callback về Java đúng lúc UI/executor shutdown | Listener bị gọi sau khi đóng hoặc event queue từ chối task | Chuyển sang `CLOSING` trước, ngừng phát sự kiện, xử lý hủy/chờ task |
| Callback gọi `close()` và close chờ chính callback kết thúc | Self-deadlock | Schedule close sang controller thread hoặc hỗ trợ close hai pha |
| FFM `Arena.close()` lần hai | `IllegalStateException` | Test đúng FFM contract hoặc đóng qua wrapper idempotent |
| Đóng shared arena trong lúc downcall đang dùng segment | Runtime có thể từ chối close; retry không kiểm soát dễ lỗi | Đồng bộ quiescence; test access/close race theo phiên bản JDK |
| Dùng lại địa chỉ handle cho session mới | Callback cũ nhận nhầm session mới (ABA) | Generation/epoch + registry cấp lease, không dereference freed context |
| Java callback ném exception xuyên ranh giới upcall | Có thể làm JVM dừng đột ngột với FFM upcall | Target phải catch, report và trả giá trị native hợp lệ |
| Test pass vì callback chưa bao giờ chạy | False positive | Đếm accepted/ignored/finished, bắt buộc trigger và đồng bộ bằng latch |

### Trường hợp lỗi không được che giấu

Nếu hàm hủy native có thể lỗi, wrapper phải mô tả rõ trạng thái. Ví dụ native destructor trả `BUSY` vì còn callback: không được đặt `CLOSED` rồi xóa thông tin handle; phải giữ nguyên ownership để có cách dọn dẹp an toàn và báo lỗi, hoặc fail fast với thông báo đáng tin. Nếu destructor đã chạy một phần rồi báo lỗi, **không tự retry free** nếu contract không xác nhận idempotence. Đây là trường hợp cần test fault injection riêng (T11), độc lập với bài lab fake vốn luôn hủy thành công.

## 9. Điều kiện nghiệm thu để phân phối Java/native library

Trước phát hành, định nghĩa một bộ tiêu chí có thể kiểm chứng:

1. **Tài liệu API:** xác định ai sở hữu handle, close có idempotent không, sự kiện sau close, callback thread, reentrancy và lỗi đóng.
2. **Lifecycle assertions:** với mỗi handle, `allocations == frees == 1` sau teardown thành công; mọi in-flight operations/callbacks có completion hoặc hủy được định nghĩa; không worker nào còn giữ pointer đã free.
3. **Race suite:** T01–T12 phù hợp với API thực; chạy cả đường đua `close/use`, `close/callback`, nhiều closer, và handle generation reuse; mọi test có timeout.
4. **JNI/FFM correctness:** validate `JNIEnv*` thread, global refs, upstream unregister + drain, FFM arena/thread scope, upcall-stub lifetime; không giải thích sai exception contract.
5. **Build matrix:** kiểm tra các JDK và OS/architecture được thư viện công bố hỗ trợ; JDK release không tự đảm bảo native ABI, libc hoặc sanitizer giống nhau.
6. **Packaging:** thử từ artifact thật (JAR, `.so`/`.dll`/`.dylib`, launcher, JVM flags, paths), không chỉ từ thư mục biên dịch; đảm bảo symbols và hash/debug info có thể truy hồi khi crash.
7. **Diagnosability:** khi test hỏng hoặc subprocess crash, giữ stdout/stderr, JVM fatal log, native symbol/build ID và core/minidump theo khả năng thu; ghi test seed, thời gian, PID, phiên bản binary.
8. **Release gate:** test deterministic phải luôn PASS, stress/sanitizer không phát hiện UAF/double free trong phạm vi kiểm thử, không leak/worker còn sống sau shutdown, và mọi hạn chế chưa thể kiểm chứng được ghi nhận rõ.

Không đặt tiêu chí “không từng crash trong test” ngang với chứng minh an toàn tuyệt đối. JNI/native code có thể biểu hiện lỗi sau hàng triệu interleaving. Giá trị của suite là buộc những bất biến quan trọng được kiểm chứng và tạo đủ bằng chứng khi xuất hiện crash.

## 10. Câu hỏi tự đánh giá

**Tình huống A.** Hai thread đều đọc `closed=false`, một thread gọi `nativeFree` và thread còn lại gọi `nativeRead`. Chỉ đổi `closed` thành `volatile` có đủ không? **Không.** Volatile hỗ trợ visibility nhưng không biến hai thao tác “kiểm tra + dùng pointer” thành một lease được bảo vệ trước close.

**Tình huống B.** `close()` được gọi ba lần; free count là 1. Có kết luận wrapper thread-safe không? **Chưa.** Cần chứng minh không có operation/callback in-flight dùng pointer sau free và nhiều closer không deadlock.

**Tình huống C.** `unregister_callback` trả về nhưng một callback đã queue vẫn giữ `jobject`. Được gọi `DeleteGlobalRef` chưa? **Chưa**, trừ khi API native đảm bảo các callback cần ref đã quiesced; phải đợi queue/callback drain trước.

**Tình huống D.** Đóng `Arena.ofShared()` lần thứ hai ném `IllegalStateException`. Đây là regression của Java? **Không.** Đây là contract chính thức của `Arena.close()`; chỉ wrapper riêng mới có thể chọn idempotent close.

**Tình huống E.** Test fake trong phần 4 PASS nhưng JNI integration báo heap-use-after-free trong callback. Mâu thuẫn không? **Không.** Fake chưa kiểm chứng global-ref lifetime, native thread join và callback đang ở phía C trước khi vào Java.

**Tình huống F.** Event của session A nhận đúng địa chỉ con trỏ nhưng được xử lý trong session B. Vì sao? **ABA**: allocator tái sử dụng địa chỉ; cần generation/epoch và lookup registry được đồng bộ.

## 11. Tài liệu chuẩn

- [Oracle — `Arena` (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): lifecycle, close không idempotent, confined/shared, `WrongThreadException` và concurrent access.
- [Oracle — `MemorySegment` / FFM package (JDK 24)](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/package-summary.html): temporal safety và segment scope.
- [Oracle — `Linker` (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/foreign/Linker.html): lifetime của upcall stub, native call và lỗi khi Java exception vượt ranh giới FFM upcall.
- [JNI Specification — Global/Local References](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/functions.html): `NewGlobalRef`, `DeleteGlobalRef`, pending exceptions.
- [JNI Specification — Invocation API](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/invocation.html): `AttachCurrentThread`, `DetachCurrentThread`, `JNIEnv*` theo thread.
- [OpenJDK JEP 454](https://openjdk.org/jeps/454): FFM API trở thành final từ JDK 22; mục tiêu và các giới hạn an toàn.

Điều quan trọng khi phân phối thư viện Java/native là biến vòng đời tài nguyên thành **hợp đồng có thể test được**: chấp nhận thao tác chỉ khi có lease hợp lệ; chuyển sang đóng một lần; ngừng và đợi native callbacks/operations đã nhận; hủy tài nguyên đúng một lần; từ chối mọi sử dụng và callback đến muộn. Chính các bất biến này, không phải một cờ boolean đơn lẻ, giúp ngăn double free, use-after-free và lỗi shutdown khó tái hiện.
