# Kiểm thử gọi đồng thời, khởi tạo thất bại, dừng và thay thế nhiều thế hệ plugin Java

## 1. Bài toán: plugin chạy đúng khi tuần tự chưa đủ

Một hệ thống Java mở rộng lúc chạy có thể khám phá plugin bằng `ServiceLoader`, nạp plugin từ class loader riêng hoặc tạo `ModuleLayer` động. Những cơ chế đó giúp **tìm và nạp code**, nhưng không tự chứng minh rằng **plugin manager** an toàn khi nhiều request, startup lỗi giữa chừng, shutdown diễn ra đồng thời, hoặc hot replacement giữa các thế hệ implementation.

Kiểm thử plugin cần quan tâm đến **hành vi tại ranh giới thời gian**, chứ không chỉ `assertEquals` trên một method nghiệp vụ:

1. **Gọi đồng thời:** Hai hay nhiều request có thể cùng chạy trên một plugin. Manager có đếm đúng request đang chạy (*in-flight*) và bảo vệ shared state không?
2. **Khởi tạo thất bại:** Plugin có thể mở tài nguyên rồi ném lỗi. Host có đưa nhầm instance chưa sẵn sàng vào registry hoặc bỏ quên tài nguyên không?
3. **Dừng:** Khi có request đang thực thi, thao tác shutdown có chặn request mới, chờ request cũ và đóng tài nguyên đúng thời điểm không?
4. **Thay thế nhiều thế hệ:** Trong lúc một plugin phiên bản cũ vẫn xử lý request, host có thể kích hoạt bản mới, chuyển request mới tới bản mới và từ chối callback muộn của bản cũ không?

**Kết quả mong muốn:** kiểm thử phải lặp lại được, chủ động điều khiển lịch trình giữa threads, có timeout phát hiện deadlock, có assertions về state và ownership, không dùng `Thread.sleep(...)` để “hy vọng” một race xảy ra.

### 1.1. Ranh giới trách nhiệm

```text
   SPI / ModuleFinder / class loader
             │ khám phá implementation
             ▼
       Plugin Manager
     verify → initialize → READY
             │
             ▼
       Router / Registry
       ┌─────────────────┐
       │ Generation G1   │ ◄── request cũ, đã cấp lease
       │ QUIESCING       │
       └─────────────────┘
             │ chuyển traffic nguyên tử
             ▼
       ┌─────────────────┐
       │ Generation G2   │ ◄── request mới
       │ ACTIVE          │
       └─────────────────┘
             │
             ▼
  Đợi G1 in-flight = 0 → stop G1 → close resources
```

Host chịu trách nhiệm *routing*, vòng đời, timeout, version compatibility và cleanup. Plugin chịu trách nhiệm thread safety của implementation hoặc phải công bố policy chạy tuần tự. **Thread-safe routing không làm một plugin implementation vốn không thread-safe trở nên thread-safe.**

## 2. Mô hình kiểm thử: state, generation, lease và các bất biến

Một mô hình đủ để kiểm tra những lỗi quan trọng:

| Thành phần | Nhiệm vụ | Assertion quan trọng |
| --- | --- | --- |
| `Plugin` | `initialize`, `handle`, `close` | Không xử lý trước init; cleanup an toàn sau init thất bại |
| `Generation` | Một instance/plugin version + state + số in-flight | Không cấp lease ngoài ACTIVE; shutdown đợi đúng số request |
| `Router` | Một tham chiếu tới generation hiện hành | Swap và cấp lease dùng chung cơ chế đồng bộ |
| `Lease` | Quyền tạm thời cho một request sử dụng generation | Cấp đúng một lần; giải phóng trong `finally` |
| `Failure record` | Nguyên nhân startup/stop/callback lỗi | Không mất lỗi gốc dù cleanup thành công |
| `Generation ID` | Phân biệt các lần tạo instance | Callback cũ không sửa state của generation mới |

Các trạng thái có thể là `NEW`, `INITIALIZING`, `ACTIVE`, `QUIESCING`, `STOPPING`, `STOPPED` và `FAILED`. Đây là enum do ứng dụng thiết kế, **không phải trạng thái có sẵn của `ServiceLoader`**.

### 2.1. Bất biến không được phá

- **Admission:** Chỉ `ACTIVE` được nhận request mới và tăng `inFlight`.
- **Atomicity:** Kiểm tra `ACTIVE` và tăng `inFlight` phải xảy ra trong **cùng critical section**, tránh race với stop.
- **Release:** Sau khi đã cấp lease, mọi đường ra (thành công, exception, interrupt) đều giảm `inFlight` đúng một lần.
- **No premature close:** Không gọi `close` khi `inFlight > 0` nếu contract yêu cầu graceful shutdown và request còn dùng tài nguyên.
- **Quiesce:** Khi gate đã đóng, **không cấp lease mới cho generation cũ**, nhưng lease đã cấp vẫn được hoàn tất.
- **No early publish:** Candidate chỉ trở thành current generation **sau** khi initialize và readiness thành công.
- **Atomic cutover:** Không có khoảng trống hai router paths cùng nhận request mới sau thời điểm switch được công bố.
- **Fencing:** Kết quả callback thuộc generation cũ không được cập nhật registry hoặc state của generation mới.
- **Cleanup:** Khởi tạo một phần vẫn phải cleanup; stop lặp không tạo double-close.
- **Failure history:** Startup lỗi nhưng cleanup về `STOPPED` không làm mất `lastFailure`.

### 2.2. Lease quan trọng hơn một biến `volatile`

Phản ví dụ:

```java
// PSEUDOCODE nguy hiểm: check và tăng không nguyên tử.
if (state == State.ACTIVE) {
    inFlight++;
    plugin.handle(request);
    inFlight--;
}
```

Thread A có thể đọc `ACTIVE`, thread B chuyển `STOPPING` và đóng tài nguyên, rồi A mới tăng `inFlight` và gọi plugin. `volatile State` chỉ giúp nhìn thấy giá trị, không biến chuỗi *check → increment → use* thành một thao tác nguyên tử.

Mẫu thiết kế đúng:

```text
Route request:
  synchronized(generation.lock):
    require ACTIVE
    inFlight += 1
  try:
    plugin.handle(request)
  finally:
    synchronized(generation.lock):
      inFlight -= 1
      signal waiters

Stop generation:
  synchronized(generation.lock):
    state = QUIESCING
    reject new leases
    wait until inFlight == 0
  plugin.close()
```

Đây là **pseudocode**. Trong ứng dụng nhiều router, bước chọn current generation và cấp lease phải được phối hợp với **cùng lock/cơ chế CAS của thao tác swap**. Nếu router chọn generation cũ rồi tạm dừng trước khi cấp lease, swap có thể xuất hiện ở giữa.

## 3. Kiểm thử gọi đồng thời

### 3.1. Cần chứng minh điều gì?

Đừng chỉ chạy 100 request rồi thấy kết quả đều đúng. Một test tốt cho concurrent invocation nên chứng minh:

1. Có **ít nhất hai handler cùng vào vùng xử lý** trong lúc chưa được phép hoàn tất.
2. `inFlight` của manager bằng số lease đã cấp; không bị mất increment/decrement.
3. Request trả đúng kết quả và không chia sẻ dữ liệu mutable không bảo vệ.
4. Sau khi release các handlers, `inFlight == 0`.
5. Exception cũng giải phóng lease, không làm shutdown chờ mãi.
6. Khi policy plugin chỉ cho phép xử lý tuần tự, router/executor phải serialize thật sự thay vì chỉ hy vọng plugin không race.

### 3.2. Dùng `CountDownLatch` thay vì `Thread.sleep`

`CountDownLatch` tạo hai điểm đồng bộ chủ động:

```text
Thread A: acquire → handle → entered.countDown ─┐
                                                ├─ await(release)
Thread B: acquire → handle → entered.countDown ─┘

Test: await(entered == 0)
      assert inFlight == 2
      assert observedMaxConcurrent == 2
      release.countDown()
      assert outputs and inFlight == 0
```

Test biết chắc hai request đã vào handler trước khi mở cổng. `Thread.sleep(100)` không bảo đảm gì: máy CI chậm, GC pause hoặc scheduler khác có thể khiến test vừa pass giả vừa flaky.

Dùng `CountDownLatch.await(timeout, unit)` ở test để **fail khi bị treo**, không để kiểm soát thứ tự bằng thời gian. Một timeout chỉ là giới hạn an toàn; nó không chứng minh algorithm đúng nếu không có assertions trên trạng thái đã đồng bộ.

### 3.3. Cần xét cả các exception paths

Mẫu release:

```java
// Minh họa: acquire()/release() thuộc một Generation đồng bộ đúng.
generation.acquire();
try {
    return plugin.handle(input);
} finally {
    generation.release();
}
```

Nếu `plugin.handle` ném `IllegalArgumentException`, `IOException` hoặc `InterruptedException`, `finally` vẫn chạy. Test nên đưa lỗi có kiểm soát vào `handle` rồi xác nhận `inFlight == 0` và stop không bị treo.

Nếu một thread bị interrupt khi đang chờ, đừng xóa interrupt flag hoặc tự động retry khiến request bị xử lý hai lần. Thường để `InterruptedException` đi lên ở test/host boundary hoặc khôi phục cờ interrupt trong code không truyền exception ra ngoài.

## 4. Kiểm thử khởi tạo thất bại

### 4.1. Các pha lỗi khác nhau

| Điểm lỗi | Dấu vết cần kiểm tra | Hành vi host |
| --- | --- | --- |
| Provider discovery | Không có provider hoặc SPI descriptor hỏng | Phân biệt absent provider với `ServiceConfigurationError` |
| Verify | Thiếu dependency/version, ID trùng, policy từ chối | Không initialize/publish |
| Constructor | Constructor/initializer ném lỗi | Không có instance dùng được; cleanup tài nguyên phụ nếu đã cấp |
| Initialize trước khi mở tài nguyên | Config/secret không hợp lệ | `FAILED`, không ACTIVE |
| Initialize **sau khi mở tài nguyên** | File, socket, worker thread đã tạo nhưng bước sau lỗi | Cleanup phần đã mở, không leak |
| Start/readiness | Không sẵn sàng, timeout, dependency lỗi | Candidate không được publish |
| Khi thay thế | Generation mới khởi tạo lỗi | **Giữ generation cũ** đang phục vụ nếu chưa cutover |

Một test chỉ assert exception được ném là **chưa đủ**. Phải kiểm tra cùng lúc: candidate không được publish, không có request tới candidate, tài nguyên partial được giải phóng, nguyên nhân lỗi được giữ, và generation cũ (nếu có) vẫn hoạt động.

### 4.2. Tách initialize khỏi publish

Quy trình:

```text
construct candidate
        │
        ▼
verify dependencies/config
        │
        ▼
initialize candidate
        ├─ FAILED → close partially initialized resources → report
        ▼
readiness check
        ├─ FAILED → cleanup candidate → keep old generation
        ▼
atomic swap in router
        │
        ▼
old generation QUIESCING → drain → STOPPED
```

Nếu host publish candidate trước khi `initialize` hoàn tất, request có thể nhìn thấy object chưa được cấu hình hoặc mở chưa đủ resources.

Trong code test, hãy cố tình đặt cờ `resourceOpened=true` **trước khi ném lỗi** rồi assert sau `close` rằng cờ trở về `false`. Nó bắt được bug bỏ quên cleanup mà test ném lỗi ngay đầu `initialize` không phát hiện.

### 4.3. Tránh tự động retry instance hỏng

Không mặc định gọi lại `initialize` trên cùng object sau khi lỗi vì các biến instance, thread, connection và subscription có thể đang ở trạng thái không rõ. Chiến lược an toàn thường là:

```text
FAILED instance → best-effort cleanup → STOPPED
→ retry với generation/instance MỚI sau backoff
```

Nếu host hỗ trợ restart cùng instance thì đây phải là capability đã quy định và được kiểm thử ở mọi failure stage. Đừng chỉ thêm vòng lặp retry quanh `start()`.

## 5. Kiểm thử dừng: quiescing, drain và close

### 5.1. Một shutdown đúng có ba mốc

1. **Close admission:** Không còn request mới nào nhận lease của generation sẽ dừng.
2. **Drain in-flight:** Đợi các request đã được chấp nhận hoàn tất (hoặc deadline/cancellation policy).
3. **Cleanup:** Đóng plugin resources đúng một lần rồi ghi `STOPPED`.

`QUIESCING` là thời điểm gate đóng nhưng request cũ vẫn chạy. `STOPPING` là pha manager chuẩn bị/đang cleanup; tên trạng thái cụ thể do hệ thống quy định.

### 5.2. Dùng latch để buộc stop cạnh tranh với handler

```text
Request thread                  Shutdown thread
--------------                  ---------------
acquire generation lease
handle() enters
block on release latch
                                close gate
                                assert new request rejected
                                wait for inFlight = 0
assert plugin not yet closed
release latch
handle returns
release lease
                                plugin.close() once
                                state = STOPPED
```

Các assertions bắt buộc:

- Handler đang chạy tiếp tục trên generation cũ, không bị đổi instance giữa chừng.
- Sau close gate, một request **mới** bị từ chối hoặc được router chuyển sang generation khác, không được cấp thêm lease cũ.
- Trong lúc còn một request blocked, `closeCount == 0` và shutdown chưa hoàn thành.
- Chỉ sau khi release lease mới thấy `closeCount == 1` và state `STOPPED`.
- Gọi stop thêm lần nữa không close lần hai.
- Nếu `close` thất bại, host ghi lại cleanup failure, không báo thành công giả.

### 5.3. Timeout và cancellation

Mô hình demo thường chờ drain không giới hạn nhưng test dùng timeout để tránh treo mãi. **Production phải có deadline**. Tuy nhiên `Future.cancel(true)`/`Thread.interrupt()` không bảo đảm một handler đang thực hiện blocking I/O sẽ dừng ngay; càng không bảo đảm tài nguyên có thể đóng an toàn nếu thread vẫn sử dụng nó.

Khi hết hạn, host cần chính sách rõ: đánh dấu timeout, ngăn admission, ghi request còn sống, giới hạn tài nguyên, và có thể **cô lập trong process riêng** nếu cần cưỡng chế dừng. Không chỉ gọi `URLClassLoader.close()` rồi cho rằng mọi thread của plugin đã chết; Java class unloading cần không còn reference tới loader.

### 5.4. Dependency graph khi shutdown

Nếu plugin Report phụ thuộc Storage:

```text
Start: Storage → Report
Stop:  Report  → Storage
```

Test cần xác minh Report được quiesce/flush/close **trước** khi Storage đóng, kể cả khi có request chạy đồng thời. `ServiceLoader` không tự quyết định thứ tự dependency này.

## 6. Kiểm thử thay thế nhiều thế hệ

### 6.1. Generation là gì?

Một *generation* là **một instance plugin có identity duy nhất trong một lần kích hoạt**, ví dụ `pluginId=pdf, generation=7` và `generation=8`. Generation khác với version chuỗi `1.2.3`: hai lần restart cùng version vẫn là **hai generation khác nhau**.

Nên gắn dữ liệu với `pluginId + generationId + instanceId` hoặc token tương đương. Không lưu state chỉ theo plugin name nếu hai instance cùng tên có thể chạy chồng trong thời gian chuyển traffic.

### 6.2. Quy trình thay thế không gián đoạn

```text
T0:  current = G1 (ACTIVE)
     request A nhận lease G1, đang chạy

T1:  tạo G2, verify/init/readiness
     G1 vẫn phục vụ request mới

T2:  swap atomically:
     G1 close gate → QUIESCING
     current = G2 (ACTIVE)

T3:  request B được route tới G2
     request A vẫn hoàn thành trên G1

T4:  inFlight(G1) = 0
     stop/close G1 → STOPPED
     current vẫn G2

T5:  tạo G3, swap tương tự:
     G2 QUIESCING, current=G3
     callback muộn của G1/G2 bị bỏ qua
```

Ở thời điểm T2, **việc đóng gate G1 và gán current=G2 phải được phối hợp**. Nếu chỉ:

```java
// PSEUDOCODE có race nếu route() lấy reference trước swap.
current = newGeneration;
oldGeneration.stopAccepting();
```

một request có thể đã đọc reference G1 nhưng chưa acquire lease, sau đó vẫn được phép dùng G1 dù swap đã xảy ra. Cách giải quyết trong ví dụ runnable là Router và Generation sử dụng lock nhất quán để **swap và acquire lease có thứ tự tuyến tính**.

### 6.3. Test callback cũ (stale callback)

Một tác vụ bất đồng bộ có thể hoàn thành sau khi generation khác đã được publish. Nếu callback chỉ làm `registry.put(pluginId, result)`, nó có thể ghi đè trạng thái bản mới.

**Fencing token**:

```text
callback(sourceGeneration, result):
  synchronized(router.lock):
    if sourceGeneration != current:
        reject stale update
    else:
        publish result
```

Trong một hệ thống phân tán, có thể cần monotonic fencing token được backend kiểm tra, không chỉ object identity in-memory. Test nên có ba generations G1, G2, G3 và cố tình gửi callback G1/G2 **sau** khi G3 trở thành current; chúng phải bị từ chối. Callback G3 được chấp nhận.

### 6.4. Candidate thất bại trước swap

Nếu G2 không initialize được, router vẫn phải giữ G1:

```text
G1 ACTIVE ────────────────► G1 ACTIVE
                  G2 INITIALIZING
                         │ failure
                         ▼
                      G2 FAILED
                         │ cleanup
                         ▼
                      G2 STOPPED
```

Test này bắt lỗi implementation kiểu “gán `current = candidate` trước, rồi mới gọi `candidate.start()`”, khiến hệ thống không có provider hoạt động sau một deployment thất bại.

## 7. Công cụ kiểm thử trong Java 17+

| Công cụ | Công dụng | Điều phải chú ý |
| --- | --- | --- |
| `CountDownLatch` | Chặn/mở điểm chuyển trong test | One-shot; không reset được |
| `CyclicBarrier` | Nhiều thread cùng đến một checkpoint | Cần xử lý broken barrier/timeout |
| `Phaser` | Nhiều pha đồng bộ | Phức tạp hơn, phù hợp test có nhiều bước |
| `ExecutorService` | Chạy requests/shutdown trên worker threads | Shutdown executor trong `finally` |
| `Future.get(timeout, unit)` | Đợi kết quả, phát hiện treo | Timeout chỉ là guard, không phải bằng chứng về thứ tự |
| `CompletableFuture` | Kiểm thử async startup/callback | Unwrap lỗi, xác định executor và cancellation |
| `AtomicInteger` | Đếm số lần handle/close, đo max concurrency | Không thay thế atomic protocol liên quan nhiều biến |
| `AtomicReference` | Giữ current generation hoặc snapshot | Một CAS pointer không tự đóng gate của generation cũ |
| `synchronized`/`ReentrantLock` | Gom check + acquire hoặc swap thành critical section | Không giữ lock khi gọi code plugin có thể block |
| JUnit 5 `assertTimeoutPreemptively` | Giới hạn thời gian test ở framework | Thread khác, interrupt/cancellation có giới hạn; tránh khiến code vẫn chạy sau test |
| Awaitility (ngoài JDK) | Chờ eventual condition có deadline | Không dùng polling thay cho coordination khi có thể dùng latch |

Đối với example chỉ cần JDK 17+, phần dưới dùng **assert helper tự viết** và `CountDownLatch`. Khi đưa vào CI, có thể chuyển từng case thành JUnit 5 `@Test`. Không cần cài JUnit để chạy chương trình mẫu.

## 8. Ví dụ Java 17+ hoàn chỉnh: kiểm thử bằng nhiều thread và ba thế hệ

### 8.1. Mục tiêu và cấu trúc

Để dễ chạy lại, ví dụ là **một file Java** với các static nested types. Nó mô phỏng một Router, mỗi `Generation` có gate và bộ đếm in-flight, và một `FakePlugin` có latches chủ động để test điều khiển lịch chạy.

Năm ca kiểm thử:

1. Hai calls thực sự đồng thời và được release chính xác.
2. Initialize thất bại **sau** khi tạo resource; không publish và cleanup.
3. Stop khi một call đang chạy; không đóng sớm hoặc nhận call mới.
4. Thay G1 → G2 → G3, request đã cấp lease ở G1 hoàn thành, callback cũ bị từ chối.
5. Candidate G2 khởi tạo lỗi; G1 vẫn phục vụ đến khi có replacement hợp lệ.

File:

```text
LifecycleTests.java
```

### 8.2. Toàn bộ mã `LifecycleTests.java`

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class LifecycleTests {
    private static final long TIMEOUT_SECONDS = 10;

    interface Plugin {
        void initialize() throws Exception;
        String handle(String request) throws Exception;
        void close() throws Exception;
    }

    enum State {
        NEW, INITIALIZING, ACTIVE, QUIESCING,
        STOPPING, STOPPED, FAILED
    }

    static final class FakePlugin implements Plugin {
        final String version;
        final boolean failInitialize;
        final CountDownLatch entered;
        final CountDownLatch release;
        final AtomicInteger concurrent = new AtomicInteger();
        final AtomicInteger maximum = new AtomicInteger();
        final AtomicInteger closeCount = new AtomicInteger();
        volatile boolean resourceOpen;

        FakePlugin(String version, boolean failInitialize,
                   int expectedCalls, boolean blockHandlers) {
            this.version = version;
            this.failInitialize = failInitialize;
            this.entered = new CountDownLatch(expectedCalls);
            this.release = new CountDownLatch(blockHandlers ? 1 : 0);
        }

        @Override
        public void initialize() {
            // Cố ý mở resource TRƯỚC khi mô phỏng lỗi.
            resourceOpen = true;
            if (failInitialize) {
                throw new IllegalStateException("init denied");
            }
        }

        @Override
        public String handle(String request) throws Exception {
            if (!resourceOpen) {
                throw new IllegalStateException("not initialized");
            }
            int now = concurrent.incrementAndGet();
            maximum.accumulateAndGet(now, Math::max);
            try {
                entered.countDown();
                if (!release.await(
                        TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "handler gate timed out");
                }
                return version + ":" + request;
            } finally {
                concurrent.decrementAndGet();
            }
        }

        @Override
        public void close() {
            if (concurrent.get() != 0) {
                throw new IllegalStateException(
                    "closed while handler is running");
            }
            closeCount.incrementAndGet();
            resourceOpen = false;
        }
    }

    static final class Generation {
        final long id;
        final Plugin plugin;
        final Object monitor = new Object();
        final CountDownLatch gateClosed = new CountDownLatch(1);
        private State state = State.NEW;
        private int inFlight;
        private boolean shutdownStarted;
        private Exception lastFailure;

        Generation(long id, Plugin plugin) {
            this.id = id;
            this.plugin = plugin;
        }

        void start() throws Exception {
            synchronized (monitor) {
                require(state == State.NEW,
                        "start must begin from NEW");
                state = State.INITIALIZING;
            }
            try {
                plugin.initialize();
                synchronized (monitor) {
                    state = State.ACTIVE;
                }
            } catch (Exception error) {
                synchronized (monitor) {
                    lastFailure = error;
                    state = State.FAILED;
                }
                throw error;
            }
        }

        void acquire() {
            synchronized (monitor) {
                require(state == State.ACTIVE,
                        "generation not ACTIVE");
                inFlight++;
            }
        }

        String runLeased(String input) throws Exception {
            return plugin.handle(input);
        }

        void releaseLease() {
            synchronized (monitor) {
                require(inFlight > 0, "unbalanced release");
                inFlight--;
                monitor.notifyAll();
            }
        }

        void quiesce() {
            synchronized (monitor) {
                require(state == State.ACTIVE
                        || state == State.QUIESCING,
                        "cannot quiesce current state");
                if (state == State.ACTIVE) {
                    state = State.QUIESCING;
                    gateClosed.countDown();
                }
            }
        }

        void shutdown() throws Exception {
            synchronized (monitor) {
                if (shutdownStarted) {
                    // Đồng thời stop: chờ lần cleanup đầu kết thúc.
                    while (state == State.STOPPING) {
                        monitor.wait();
                    }
                    return;
                }
                require(state == State.NEW
                        || state == State.ACTIVE
                        || state == State.QUIESCING
                        || state == State.FAILED,
                        "invalid shutdown state");
                shutdownStarted = true;
                state = State.STOPPING;
                gateClosed.countDown();

                // wait() giải phóng monitor để request hoàn tất lease.
                while (inFlight != 0) {
                    monitor.wait();
                }
            }

            Exception closeError = null;
            try {
                plugin.close();
            } catch (Exception error) {
                closeError = error;
            }

            synchronized (monitor) {
                if (closeError == null) {
                    state = State.STOPPED;
                } else {
                    state = State.FAILED;
                    lastFailure = closeError;
                }
                monitor.notifyAll();
            }
            if (closeError != null) {
                throw closeError;
            }
        }

        State state() {
            synchronized (monitor) {
                return state;
            }
        }

        int inFlight() {
            synchronized (monitor) {
                return inFlight;
            }
        }

        Exception lastFailure() {
            synchronized (monitor) {
                return lastFailure;
            }
        }
    }

    static final class Router {
        private final Object lock = new Object();
        private Generation current;
        private String publishedMarker;

        // Initialize candidate trước khi thay thế current.
        Generation swap(Generation candidate) throws Exception {
            candidate.start();
            synchronized (lock) {
                Generation old = current;
                if (old != null) {
                    old.quiesce();
                }
                current = candidate;
                return old;
            }
        }

        String route(String request) throws Exception {
            Generation selected;
            synchronized (lock) {
                selected = current;
                require(selected != null,
                        "no current generation");
                // Chọn current và acquire là một transaction.
                selected.acquire();
            }
            try {
                return selected.runLeased(request);
            } finally {
                selected.releaseLease();
            }
        }

        void stopCurrent() throws Exception {
            Generation old;
            synchronized (lock) {
                old = current;
                if (old != null) {
                    old.quiesce();
                    current = null;
                }
            }
            if (old != null) {
                old.shutdown();
            }
        }

        boolean publishIfCurrent(Generation source, String value) {
            synchronized (lock) {
                if (current != source
                        || source.state() != State.ACTIVE) {
                    return false;
                }
                publishedMarker = value;
                return true;
            }
        }

        String marker() {
            synchronized (lock) {
                return publishedMarker;
            }
        }
    }

    static void require(boolean condition, String explanation) {
        if (!condition) {
            throw new AssertionError(explanation);
        }
    }

    static void await(CountDownLatch latch, String stage)
            throws InterruptedException {
        require(latch.await(TIMEOUT_SECONDS, TimeUnit.SECONDS),
                "timeout waiting for " + stage);
    }

    static String result(Future<String> future) throws Exception {
        return future.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
    }

    static void testConcurrentCalls() throws Exception {
        Router router = new Router();
        FakePlugin fake = new FakePlugin("v1", false, 2, true);
        Generation g1 = new Generation(1, fake);
        require(router.swap(g1) == null, "first swap");
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = pool.submit(() -> router.route("A"));
            Future<String> b = pool.submit(() -> router.route("B"));

            await(fake.entered, "two calls enter handler");
            require(g1.inFlight() == 2, "two active leases");
            require(fake.maximum.get() == 2,
                    "handlers did not overlap");

            fake.release.countDown();
            require(result(a).equals("v1:A"), "request A");
            require(result(b).equals("v1:B"), "request B");
            require(g1.inFlight() == 0, "leases drained");

            router.stopCurrent();
            require(g1.state() == State.STOPPED, "stopped");
            require(fake.closeCount.get() == 1, "closed once");
            System.out.println("PASS concurrent calls");
        } finally {
            fake.release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }

    static void testFailedInitialization() throws Exception {
        Router router = new Router();
        FakePlugin bad = new FakePlugin("bad", true, 0, false);
        Generation candidate = new Generation(1, bad);
        boolean failed = false;
        try {
            router.swap(candidate);
        } catch (IllegalStateException expected) {
            failed = expected.getMessage().equals("init denied");
        }
        require(failed, "initialize should fail");
        require(candidate.state() == State.FAILED, "failed state");
        require(candidate.lastFailure() != null, "failure recorded");
        require(bad.resourceOpen, "partial resource was opened");

        boolean rejected = false;
        try {
            router.route("must-not-run");
        } catch (IllegalStateException expected) {
            rejected = true;
        }
        require(rejected, "failed candidate must not be published");
        candidate.shutdown();
        require(candidate.state() == State.STOPPED, "cleanup done");
        require(!bad.resourceOpen, "partial resource closed");
        require(bad.closeCount.get() == 1, "one cleanup");
        require(candidate.lastFailure() != null,
                "failure history retained");
        System.out.println("PASS initialization rollback");
    }

    static void testGracefulStop() throws Exception {
        Router router = new Router();
        FakePlugin fake = new FakePlugin("stop", false, 1, true);
        Generation g1 = new Generation(1, fake);
        router.swap(g1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> running =
                pool.submit(() -> router.route("live"));
            await(fake.entered, "request entered");

            Future<?> stopping = pool.submit(() -> {
                router.stopCurrent();
                return null;
            });
            await(g1.gateClosed, "admission gate closed");
            require(g1.inFlight() == 1, "one in-flight request");
            require(fake.closeCount.get() == 0,
                    "cannot close while running");

            boolean rejected = false;
            try {
                router.route("late");
            } catch (IllegalStateException expected) {
                rejected = true;
            }
            require(rejected, "new request after stop rejected");

            fake.release.countDown();
            require(result(running).equals("stop:live"),
                    "old request completes");
            stopping.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            require(g1.state() == State.STOPPED, "shutdown completed");
            require(fake.closeCount.get() == 1, "closed once");
            g1.shutdown();
            require(fake.closeCount.get() == 1,
                    "second shutdown did not close twice");
            System.out.println("PASS graceful stop");
        } finally {
            fake.release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }

    static void testMultipleGenerations() throws Exception {
        Router router = new Router();
        FakePlugin p1 = new FakePlugin("v1", false, 1, true);
        Generation g1 = new Generation(1, p1);
        router.swap(g1);

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> oldCall =
                pool.submit(() -> router.route("old"));
            await(p1.entered, "G1 request entered");

            FakePlugin p2 = new FakePlugin("v2", false, 0, false);
            Generation g2 = new Generation(2, p2);
            require(router.swap(g2) == g1, "G1 retired");
            require(g1.state() == State.QUIESCING,
                    "old gate closed");
            require(router.route("new").equals("v2:new"),
                    "new request routes to G2");

            require(!router.publishIfCurrent(g1, "stale-g1"),
                    "stale G1 callback rejected");
            require(router.publishIfCurrent(g2, "fresh-g2"),
                    "G2 callback accepted");

            Future<?> draining = pool.submit(() -> {
                g1.shutdown();
                return null;
            });
            require(p1.closeCount.get() == 0,
                    "G1 must not close early");
            p1.release.countDown();
            require(result(oldCall).equals("v1:old"),
                    "G1 in-flight request completes");
            draining.get(TIMEOUT_SECONDS, TimeUnit.SECONDS);
            require(g1.state() == State.STOPPED, "G1 retired");

            FakePlugin p3 = new FakePlugin("v3", false, 0, false);
            Generation g3 = new Generation(3, p3);
            require(router.swap(g3) == g2, "G2 retired");
            require(!router.publishIfCurrent(g1, "late-g1"),
                    "late G1 rejected");
            require(!router.publishIfCurrent(g2, "late-g2"),
                    "late G2 rejected");
            require(router.publishIfCurrent(g3, "fresh-g3"),
                    "G3 accepted");
            require(router.marker().equals("fresh-g3"),
                    "newest callback wins");
            require(router.route("latest").equals("v3:latest"),
                    "new request routes to G3");

            g2.shutdown();
            router.stopCurrent();
            require(g2.state() == State.STOPPED, "G2 stopped");
            require(g3.state() == State.STOPPED, "G3 stopped");
            require(p1.closeCount.get() == 1
                    && p2.closeCount.get() == 1
                    && p3.closeCount.get() == 1,
                    "every generation cleaned once");
            System.out.println("PASS multi-generation replacement");
        } finally {
            p1.release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(TIMEOUT_SECONDS, TimeUnit.SECONDS);
        }
    }

    static void testFailedCandidateKeepsOld() throws Exception {
        Router router = new Router();
        FakePlugin previous = new FakePlugin(
            "stable", false, 0, false);
        Generation g1 = new Generation(1, previous);
        router.swap(g1);

        FakePlugin broken = new FakePlugin(
            "broken", true, 0, false);
        Generation g2 = new Generation(2, broken);
        boolean failed = false;
        try {
            router.swap(g2);
        } catch (IllegalStateException expected) {
            failed = expected.getMessage().equals("init denied");
        }
        require(failed, "candidate initialization fails");
        require(g1.state() == State.ACTIVE,
                "old generation still ACTIVE");
        require(router.route("ok").equals("stable:ok"),
                "old generation still handles requests");
        g2.shutdown();
        require(!broken.resourceOpen, "candidate cleaned");
        router.stopCurrent();
        require(previous.closeCount.get() == 1, "old cleaned");
        System.out.println("PASS failed replacement rollback");
    }

    public static void main(String[] args) throws Exception {
        testConcurrentCalls();
        testFailedInitialization();
        testGracefulStop();
        testMultipleGenerations();
        testFailedCandidateKeepsOld();
        System.out.println("ALL TESTS PASSED");
    }
}
```

### 8.3. Biên dịch và chạy

Với **JDK 17+**, đặt toàn bộ mã trên trong `LifecycleTests.java` rồi chạy:

```powershell
javac -encoding UTF-8 LifecycleTests.java
java LifecycleTests
```

**Stdout dự kiến, nếu mọi assertion đều thành công:**

```text
PASS concurrent calls
PASS initialization rollback
PASS graceful stop
PASS multi-generation replacement
PASS failed replacement rollback
ALL TESTS PASSED
```

Các thread phụ có thể chạy theo thứ tự khác nhau, nhưng chương trình **chỉ in các dòng PASS sau khi kiểm tra xong từng ca**, vì thế stdout thành công có thứ tự như trên. Nếu có bug, chương trình ném `AssertionError`/exception hoặc gặp test timeout thay vì in giả toàn bộ PASS.

### 8.4. Cách đọc các thành phần quan trọng

**`FakePlugin`** là *test double* có trạng thái tối thiểu:

- `entered` báo chính xác số request đã đi vào handler.
- `release` giữ các request trong handler đến khi test cho phép hoàn tất.
- `concurrent` và `maximum` chứng minh có chồng lấn thật, không chỉ submit hai `Future`.
- `resourceOpen` mô phỏng một tài nguyên được cấp phát trong `initialize`; bật trước khi ném lỗi để kiểm thử cleanup phần khởi tạo.
- `closeCount` chứng minh không đóng sớm hoặc hai lần.

**`Generation`** gói state và admission:

- `start()` chuyển `NEW → INITIALIZING → ACTIVE` hoặc `FAILED`, lưu `lastFailure`.
- `acquire()` chỉ tăng `inFlight` khi state `ACTIVE`.
- `releaseLease()` luôn giảm đúng một lần và `notifyAll()` người đang chờ shutdown.
- `quiesce()` ngăn lease mới nhưng không can thiệp lease đã được cấp.
- `shutdown()` chờ `inFlight == 0` trước khi gọi plugin `close()`; `shutdownStarted` chặn double-close.
- `gateClosed` chỉ là **điểm quan sát dành cho test**, không phải một cơ chế lifecycle mà mọi plugin phải có.

**`Router`** bảo vệ *current generation*:

- `route()` chọn `current` và gọi `selected.acquire()` dưới **cùng router lock**.
- `swap()` initialize candidate **trước**, sau đó dưới router lock đóng gate của old generation và gán current mới.
- `stopCurrent()` đóng gate và gỡ current dưới lock rồi dừng cũ **ngoài lock**.
- `publishIfCurrent()` từ chối callback của generation cũ, không chỉ so plugin ID.

Không giữ router lock trong lúc gọi `plugin.handle` hoặc `plugin.close`. Code plugin có thể block, ném lỗi hoặc gọi ngược host; giữ global lock trong lúc đó dễ gây deadlock và làm mọi request phải chờ nhau.

### 8.5. Vì sao không dùng `Thread.sleep`?

Ca concurrent chỉ tiếp tục khi cả hai threads đã tới `fake.entered`. Ca stop chỉ kiểm tra từ chối request sau khi `g1.gateClosed` đã được báo. Ca replace giữ G1 chờ trên `release` đến khi G2 đã được publish. Nhờ các latches này, test **chủ động tạo interleaving có ý nghĩa**.

Timeout 10 giây trên `await`/`Future.get` chỉ giúp báo deadlock hoặc CI treo. Nó không được dùng làm giả định rằng thread “chắc hẳn” đã đến một điểm nào đó chỉ vì đã qua 10 ms.

### 8.6. Giới hạn quan trọng của demo

Đây là **test harness minh họa**, không phải plugin manager production sẵn sàng triển khai. Cụ thể:

- `Generation.start()` và `shutdown()` được gọi theo workflow điều phối; demo **không** hỗ trợ cancel một `initialize()` đang block từ thread khác.
- `shutdown()` trong demo đợi in-flight không giới hạn cho đến khi request hoàn tất; `InterruptedException` trong lúc chờ chưa có rollback protocol. Production cần timeout, interrupt policy và state cleanup chính xác nếu thread dừng bị interrupt.
- `swap()` không serialize **nhiều candidate swaps đồng thời**; một manager production cần serialize deployment operations, giữ generation sequence/fencing token và rollback candidate nếu publish thất bại.
- `FakePlugin` dùng `volatile boolean resourceOpen` và atomics để đo thử nghiệm; plugin thật có thể chứa mutable state phức tạp và phải tự bảo vệ thread safety.
- `close()` trong test luôn thành công; trường hợp close lỗi, retry policy và trạng thái FAILED cần test riêng.
- Việc gọi `ServiceLoader`/nạp JAR/class loader bị tách khỏi demo để tập trung vào **lifecycle và concurrency**. Có thể kết nối manager này với provider được tìm qua SPI hoặc `ModuleLayer` sau khi xác minh identity và dependency.
- Các assertions về callback ở đây áp dụng cho **registry trong một JVM**. Khi callback ghi ra database hoặc hệ phân tán, cần fencing token được phía lưu trữ xác minh để chống stale write thực sự.

Mục tiêu của ví dụ là biến các điều kiện dễ gặp race thành những **test assertions tái lập được**, rồi mở rộng theo kiến trúc production.

## 9. Tổ chức kiểm thử với JUnit 5 và CI

### 9.1. Chuyển sang JUnit 5 như thế nào?

Trong dự án có JUnit 5, mỗi ca tương ứng một method `@Test`, dùng `Assertions.assertEquals`, `assertThrows`, `assertTrue` và timeout phù hợp. Phần runnable ở trên cố ý không phụ thuộc framework để có thể chạy với một JDK bất kỳ.

Có thể giữ `FakePlugin`, `Generation` và `Router` như test fixtures, rồi tách:

```java
// Mã minh họa dùng JUnit Jupiter; cần dependency junit-jupiter
// và đặt trong một lớp test có @Test import phù hợp.
@Test
void rejectedAfterStop() throws Exception {
    // Arrange: request đang blocked ở latch.
    // Act: stop khép gate, quan sát qua latch.
    // Assert: route mới bị từ chối; close chưa chạy.
    // Release: mở latch trong finally rồi đợi stop hoàn tất.
}
```

Khi dùng `assertTimeoutPreemptively`, framework chạy code test trong thread khác; thao tác interrupt không bắt buộc dừng được blocking I/O hoặc code plugin. Luôn có **cleanup riêng trong `finally`**, không để test tiếp theo bị ảnh hưởng bởi executor/threads còn chạy.

### 9.2. Cách thiết kế fake plugin có fault injection

Một fake chuyên sâu có thể có:

```text
failOnVerify
failOnInitializeBeforeResource
failOnInitializeAfterResource
failOnStart
failOnHandle
failOnClose
blockInitialize
blockHandle
blockClose
emitLateCallback
```

Mỗi case phải assert:

- Event order (`verify/initialize/start/handle/close`).
- Số lần gọi method và tài nguyên còn mở.
- State và failure history sau mỗi transition.
- Current generation không bị thay sai.
- Có/không có request mới sau quiescing.
- Số in-flight về 0 ngay cả khi handler ném exception.

Không cần ép một fake xử lý tất cả faults nếu khiến test khó hiểu; có thể dùng nhiều fake nhỏ, mỗi fake cho một hành vi.

### 9.3. Danh sách test bổ sung

| Tình huống | Assertion then chốt |
| --- | --- |
| Hai calls đồng thời | Cả hai vào handler trước khi release; `maxConcurrent >= 2` |
| N requests, một request ném lỗi | `inFlight` trở về 0; không deadlock stop |
| Request đến ngay sau quiesce | Không cấp lease generation cũ |
| Stop trong lúc handler blocked | Không close tài nguyên trước khi release |
| Hai lệnh stop đồng thời | Close đúng một lần, cả hai lệnh có kết quả nhất quán |
| Initialize lỗi trước khi mở resource | Không publish; cleanup an toàn |
| Initialize lỗi sau khi mở resource | Không leak; giữ root cause |
| Start/readiness timeout | Không ACTIVE; cleanup candidate; old generation còn chạy |
| Close ném lỗi | Ghi failure, không báo STOPPED giả, các resources khác được xử lý theo contract |
| Candidate replacement thất bại | Không đổi current; tiếp tục route old |
| Swap G1 → G2 khi G1 đang chạy request | Old request trả từ G1, new request đến G2 |
| Swap G1 → G2 → G3 | Stale callback G1/G2 không mutate G3 |
| Deployment G2 và G3 đồng thời | Có serialize/CAS và cleanup candidate thua |
| Restart cùng plugin version | Generation ID vẫn mới |
| Stop trước callback async hoàn thành | Callback cũ bị fence, không republish |
| Dependency plugin B bị dừng | Plugin A đang phụ thuộc không tiếp tục dùng B đã close |
| Hot reload nhiều lần | Không giữ loader cũ qua thread/TCCL/`ThreadLocal`/listeners |
| Artifact/module/SPI lỗi | Phân biệt không có provider với cấu hình hỏng |

### 9.4. Khi chạy trong CI

- Chạy các test deterministic latches trên mỗi pull request.
- Chạy lặp lại/concurrency stress tests ở một job riêng để bắt race ít gặp; **stress test không thay thế invariant test**.
- Thử trên JDK version hỗ trợ và nhiều cấu hình CPU nếu dự án có điều kiện.
- Đặt deadline cho cả test suite và từng `Future`; thread dump khi timeout, ghi generation ID và phase.
- Không dùng `sleep` làm primitive điều phối; dùng latch/barrier/phaser hoặc công cụ kiểm thử lịch trình.
- Test với **JAR/module artifact thật** (SPI descriptor, JPMS `uses/provides`, class loader policy) bên cạnh unit-level lifecycle harness.
- Nếu triển khai qua rolling upgrade, kiểm thử restart và failed deployment trong môi trường staging có nhiều instance, không chỉ một JVM.

## 10. Sai lầm phổ biến và cách khắc phục

| Sai lầm | Vì sao nguy hiểm | Cách thử đúng |
| --- | --- | --- |
| Chạy hai `Future` rồi cho rằng đã concurrent | Chưa chứng minh hai handler overlap | Dùng latch đợi cả hai vào handler |
| `Thread.sleep(100)` để chờ stop | Flaky phụ thuộc scheduler/CI | Latch/event báo gate thực sự đóng |
| Check state rồi tăng counter rời rạc | Race với close gate | Atomic lease acquire dưới một lock/CAS protocol |
| Chỉ test stop khi idle | Không phát hiện close sớm | Block handler, start stop, assert closeCount=0 |
| Chỉ assert initialize throws | Bỏ qua tài nguyên partial và publish | Resource flag + no-current + cleanup assertions |
| Publish candidate trước readiness | Deployment lỗi làm mất provider khỏe | Start candidate trước swap, test failure rollback |
| Đổi current và close gate bằng hai thao tác không phối hợp | Request có thể nhận old lease sau cutover | Route acquire/swap cùng lock |
| Chỉ so plugin ID cho callback | Old/new generation trùng ID | Fencing bằng generation instance/token |
| Reuse object FAILED sau lỗi partial | State/tài nguyên chưa rõ | New instance/generation sau cleanup |
| Gọi `URLClassLoader.close()` rồi xem như stop xong | Thread/callback vẫn chạy, class chưa unload | Quiesce, drain, cleanup, gỡ references |
| Test luôn có success path | Không test exception/interrupt/deadline | Fault injection theo từng phase |
| Assert số thread thay vì in-flight lease | Không phản ánh request thực sự được cấp | Assert admission và counter trong manager |
| Dùng race stress làm bằng chứng duy nhất | Có thể pass mà vẫn có race hiếm | Invariants + deterministic interleaving + stress |

## 11. Checklist kiểm thử trước khi triển khai

- [ ] Phân biệt `NEW/INITIALIZING/ACTIVE/QUIESCING/STOPPING/STOPPED/FAILED` và trạng thái desired vs observed.
- [ ] Có guard cho transitions và chỉ `ACTIVE` cấp lease.
- [ ] Router chọn current và cấp lease nguyên tử với swap.
- [ ] Release lease trong `finally` cả khi handler lỗi.
- [ ] Test hai handler overlap bằng latches, không bằng `sleep`.
- [ ] Test init fail **sau** resource allocation và cleanup một lần.
- [ ] Không publish candidate thất bại; old generation giữ ACTIVE nếu chưa cutover.
- [ ] Stop đóng gate trước, đợi in-flight, rồi close tài nguyên.
- [ ] Stop lặp/đồng thời không double-close; close failure có status và logs.
- [ ] Hot replace giữ old requests ở old generation, new requests vào new generation.
- [ ] Stale callback G1/G2 không sửa registry G3; dùng generation token.
- [ ] Có timeout/cancellation policy cho handlers và shutdown trong production.
- [ ] Test lỗi SPI/class loader/module/dependency riêng với lifecycle tests.
- [ ] Test hot reload nhiều vòng và leak check (threads, TCCL, caches, callbacks, loader refs).
- [ ] Chạy unit tests deterministic + integration artifact tests + concurrency stress ở CI.

**Kết luận:** Kiểm thử vòng đời plugin tốt không hỏi đơn giản “code có chạy không?”, mà hỏi “**khi các sự kiện chạy chồng nhau, bất biến nào vẫn đúng?**”. Hãy chủ động tạo race bằng latch/barrier, theo dõi in-flight leases và trạng thái, buộc initialize thất bại sau cấp phát, chứng minh graceful shutdown không close sớm, và dùng generation fencing khi chuyển G1 → G2 → G3. Khi các assertions này rõ ràng, bạn có cơ sở tin cậy hơn để triển khai và nâng cấp plugin mà không làm gián đoạn request hoặc rò tài nguyên.

**Tài liệu Java SE 17:** [`CountDownLatch`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html), [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html), [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html), [`AtomicInteger`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html), [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html).
