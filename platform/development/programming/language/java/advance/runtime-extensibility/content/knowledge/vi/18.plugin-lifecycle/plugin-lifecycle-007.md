# Vòng đời plugin: dừng nhận yêu cầu, chờ công việc đang chạy và hủy hợp tác

Khi một plugin Java cần **disable, hot-reload, nâng cấp phiên bản hoặc gỡ bỏ**, không thể chỉ đổi một cờ `enabled=false` rồi đóng `ClassLoader`. Plugin có thể đang xử lý request, giữ callback trong host, chạy background jobs, sử dụng thread pool hoặc còn tham gia các chuỗi `CompletionStage` chưa kết thúc. Nếu đóng resource quá sớm, các yêu cầu đã được chấp nhận có thể lỗi giữa chừng, dữ liệu bị ghi một phần, class loader cũ bị giữ mãi hoặc tác vụ cũ tiếp tục can thiệp phiên bản mới.

Một quy trình shutdown đúng phải tách ba việc:

1. **Dừng nhận việc mới (quiesce/admission stop):** quyết định ngăn yêu cầu mới tiếp cận plugin theo một điểm đồng bộ rõ ràng.
2. **Chờ công việc đang chạy (graceful drain):** cho các tác vụ đã nhận cơ hội hoàn tất và giải phóng tài nguyên, nhưng có giới hạn thời gian.
3. **Hủy hợp tác (cooperative cancellation):** nếu hết thời gian chờ, phát tín hiệu hủy để các task tự dừng an toàn, chờ chúng **thực sự** thoát rồi mới hoàn tất cleanup. `Thread.interrupt()`, `Future.cancel(true)` và `ExecutorService.shutdownNow()` chỉ là **yêu cầu hủy**, không phải lệnh ép chấm dứt ngay lập tức.

Chủ đề thuộc **vòng đời plugin**: trọng tâm không phải dừng toàn bộ JVM, mà là ngừng một thế hệ plugin mà không làm gián đoạn vô lý host hay các plugin khác. Những invariant, ví dụ Java 17, giới hạn và checklist sau có thể áp dụng cho plugin tải bằng `ServiceLoader`, custom `ClassLoader`, `ModuleLayer` hoặc kiến trúc extension point riêng.

## 1. Định nghĩa chính xác “ngừng plugin”

Hãy phân biệt **không nhận thêm công việc** với **đã kết thúc toàn bộ công việc**. Đây là hai mốc khác nhau.

~~~text
            host routes requests / events
                         |
                         v
                   admission gate
                  /              \
           ACCEPT                REJECT
             |                      |
             v                      +--> lỗi có kiểm soát / chuyển sang plugin mới
      register in-flight
             |
             v
       execute plugin work
             |
     success / failure / cancelled
             |
             v
      release in-flight
             |
             v
          drain == 0
             |
             v
  detach callbacks, close owned resources
             |
             v
           STOPPED
~~~

Các trạng thái thường có ý nghĩa:

| Trạng thái logic | Nhận yêu cầu mới? | Công việc đã nhận | Điều được phép làm |
| --- | --- | --- | --- |
| `ACTIVE` / `RUNNING` | Có | Đang chạy | Tiếp nhận và thực thi bình thường |
| `QUIESCING` | **Không** | Tiếp tục chạy | Chờ hoàn tất, giữ resource cần thiết |
| `CANCELLING` | Không | Được yêu cầu dừng | Đặt cancellation token, cancel task/Future, interrupt nếu an toàn |
| `STOPPING` / `CLEANUP` | Không | Phải đã thoát hoặc đã được cách ly bằng chiến lược rõ ràng | Gỡ callback, đóng executor/resource, dọn registry |
| `STOPPED` | Không | **Không còn sử dụng tài nguyên plugin** | Có thể bỏ tham chiếu đến thế hệ loader/layer cũ |
| `FAILED_TO_STOP` / `QUARANTINED` | Không | Có task không chịu dừng hoặc cleanup thất bại | Giữ cách ly, báo lỗi, tiếp tục xử lý theo chính sách |

Đây là **mô hình khái niệm**; không bắt buộc mọi implementation phải có đủ sáu enum. Ví dụ runnable ở mục 5 dùng ba trạng thái `ACTIVE`, `QUIESCING`, `STOPPED` và cờ hủy, đủ để chứng minh logic lõi. Trong production, có thể cần trạng thái lỗi và escalation riêng.

### Bốn bất biến quan trọng

1. **Không có admission mới sau điểm đóng cổng.** Nếu hai thao tác `accept` và `quiesce` chạy đồng thời, phải có một điểm *linearization*: request chỉ được tính là “đã nhận” nếu nó thắng trước thời điểm đóng cổng.
2. **Mỗi đơn vị công việc được nhận có một lần đăng ký và một lần hoàn tất.** Bộ đếm `inFlight` không được âm hoặc rò rỉ khi callback ném `Exception` hay `Error`.
3. **Không tuyên bố `STOPPED` khi plugin vẫn được sử dụng.** Việc `Future` báo cancelled, `ExecutorService.shutdownNow()` trả về hoặc thời gian chờ hết không chứng minh worker đã kết thúc.
4. **Cleanup có owner và thứ tự rõ ràng.** Chỉ đóng những tài nguyên thuộc thế hệ plugin đó; không đóng thread pool, HTTP client hoặc class loader dùng chung của host/plugin khác.

Nếu các điều kiện này không được giữ, một ứng dụng vẫn có thể in “plugin unloaded” trong khi worker cũ tiếp tục thao tác lên database hoặc callback cũ gọi vào lớp đã thay thế.

## 2. Đóng cổng admission trước khi chờ

Một lỗi cạnh tranh phổ biến:

~~~java
// Minh họa sai: check và tăng bộ đếm không cùng thao tác đồng bộ.
if (running) {
    inFlight++;
    executePlugin();
}
~~~

Nếu thread shutdown đặt `running=false` **giữa** bước kiểm tra và bước tăng `inFlight`, thread drain có thể thấy `inFlight==0` rồi đóng resource, sau đó một request cũ mới bắt đầu gọi plugin.

Giải pháp là một **cổng tiếp nhận đồng bộ**. Trong ví dụ Java 17, `call(...)` và `quiesce()` đều cập nhật trạng thái dưới **cùng `ReentrantLock`**:

~~~text
Request thread                        Shutdown thread
---------------                       ----------------
acquire lock                          acquire lock
check state == ACTIVE                 set state = QUIESCING
inFlight++                            release lock
release lock
execute operation
finally inFlight-- / signal

=> hai bên không thể cùng "thắng" sau cùng một thời điểm đóng cổng.
~~~

Cả hai thứ tự đều an toàn:

- Nếu request lấy lock trước và được accept, `inFlight` tăng trước khi shutdown nhìn thấy trạng thái; shutdown phải **đợi** request đó.
- Nếu shutdown lấy lock trước và đổi thành `QUIESCING`, request đến sau sẽ nhận `RejectedExecutionException`, không chạm đến plugin.

**Không giữ khóa trạng thái trong toàn bộ lúc gọi code plugin**: callback có thể chờ I/O, dùng lock riêng hoặc gọi ngược host; giữ lock suốt thời gian thực thi dễ gây tắc nghẽn và deadlock. Lock chỉ bao bọc **admission/counting/transition**, còn plugin work chạy bên ngoài lock.

### 2.1. Cổng phải nằm đúng nơi có thể tạo công việc mới

Đóng giao diện HTTP mà quên event consumer, scheduler, listener hoặc task queue thì plugin vẫn nhận việc. Một plugin thực tế có thể có nhiều ingress:

- Router/gateway: REST/gRPC request, WebSocket handler.
- Subscription: event bus, message consumer, database change streams.
- Scheduler: cron job, timer, retry queue.
- Callback/capability: extension registry, hooks, listener, completion callback.
- Async continuation: một request đã nhận có thể phát sinh tác vụ phụ sau khi handler chính trả về.

**Admission gate cần bao phủ tất cả ingress vào thế hệ plugin** hoặc mỗi nguồn phải ngừng nhận và được theo dõi cùng một shutdown coordinator. Trong hot reload, chuyển route sang thế hệ plugin mới và đóng cổng thế hệ cũ nên là một thao tác điều phối có tính nhất quán, không để request “rơi” giữa hai registry.

### 2.2. Phân biệt accepted, queued và running

`inFlight` phải phản ánh đúng hợp đồng:

| Loại công việc | Có nên tính? | Lưu ý |
| --- | --- | --- |
| Request đang chạy code plugin | Có | Chỉ giảm khi code plugin thực sự thoát |
| Request đã được host **accept** và nằm trong queue | Nếu hợp đồng cam kết phục vụ, **có** hoặc theo dõi ở bộ đếm riêng | Khi bị loại khỏi queue/cancel trước khi chạy vẫn phải giải phóng đúng một lần |
| Callback đã schedule nhưng chưa chạy | Nếu callback sẽ truy cập plugin cũ | Đóng ingress và quản lý queue/lifecycle của callback |
| Async task được sinh ra rồi handler trả về | Có, theo **vòng đời async thực tế** | Đếm mỗi task hoặc giữ lease đến khi toàn bộ chuỗi công việc kết thúc |
| Thread đang ngủ nhưng chỉ thuộc host và không dùng plugin | Không nhất thiết | Không được ngăn plugin unload vì resource không thuộc plugin |

Một lỗi khác là tăng `inFlight` lúc `submit` vào executor, nhưng chỉ giảm trong `Runnable.finally`. Nếu `shutdownNow()` trả về task **chưa hề chạy**, `finally` không bao giờ được thực thi và bộ đếm bị treo. Có thể quản lý accepted/queued/running tách biệt, hoặc hủy/giải phóng lease của task chưa bắt đầu một cách chính xác.

## 3. Graceful drain: chờ công việc hoàn tất có giới hạn

Sau khi đóng cổng:

1. Để các request đã nhận có thời gian hoàn tất nghiệp vụ và trả kết quả.
2. Quan sát số lượng `inFlight`; chỉ khi về 0 mới chắc những vùng công việc đã được đo lường đã thoát.
3. Đặt **deadline hữu hạn**: không chờ vô tận vì một task mất kết nối, deadlock hoặc bị block ở I/O.
4. Khi hết hạn, không coi timeout là “đã dừng”; chuyển sang nhánh **hủy hợp tác** hoặc chính sách escalation.

Với `ReentrantLock`, `Condition.awaitNanos(...)` là cách tự nhiên để đợi: thao tác `await` **tạm nhả lock trong khi đợi** và lấy lại lock khi thức dậy. Luôn kiểm tra điều kiện bằng vòng `while` vì có thể nhận tín hiệu ngoài ý muốn (*spurious wakeup*) hoặc bị đánh thức nhưng còn công việc khác.

~~~java
// Snippet logic minh họa, đặt trong class đang giữ lock và Condition.
lock.lockInterruptibly();
try {
    while (inFlight > 0 && remainingNanos > 0) {
        remainingNanos = drained.awaitNanos(remainingNanos);
    }
    return inFlight == 0;
} finally {
    lock.unlock();
}
~~~

Một implementation dùng `synchronized`/`wait`/`notifyAll`, `Phaser` hoặc counter với `CompletableFuture` cũng có thể đúng, miễn là bảo đảm **admission và completion được đồng bộ với transition đóng cổng**, tránh lost notification và double release.

### 3.1. Vì sao không dùng `Thread.sleep` để “chờ đủ lâu”?

Chờ một số mili-giây rồi đoán mọi công việc đã kết thúc sẽ bị race. `sleep` không gắn với tiến độ thực và không bảo đảm tính đúng đắn. Hãy chờ **điều kiện thực tế** (`inFlight==0` hoặc executor `isTerminated()`) với deadline.

Tránh dùng `Thread.join(0)` nếu mong timeout 0 nghĩa là “không chờ”: trong Java, `join(0)` là **chờ vô hạn**. Các API khác cũng có khác biệt về giá trị 0; đọc đúng hợp đồng từng API.

### 3.2. Deadline và thời gian đơn điệu

Với thời gian chờ, ưu tiên phép tính còn lại bằng `System.nanoTime()` hoặc `Condition.awaitNanos` để tránh sai lệch đồng hồ tường. Một budget tổng có thể chia:

~~~text
T0: đóng ingress
|---- graceful drain budget ----|
                                 |---- cooperative cancel grace ----|
                                                                       |---- cleanup budget ----|
                                                                         ^
                                                                      final outcome
~~~

Trong thực tế, shutdown phải bị ràng buộc bởi deadline của host/process (Kubernetes termination grace period, application server, quy trình deploy...). Không dùng mỗi task một deadline đầy đủ rồi cộng vô hạn khiến tổng thời gian stop vượt ngân sách vận hành.

## 4. Hủy hợp tác: yêu cầu dừng, không ép dừng

Khi grace period hết, host có thể gọi `cancel` để mọi công việc đang chạy biết cần sớm kết thúc. **Cooperative** có nghĩa code tác vụ **chủ động kiểm tra tín hiệu và tự đi ra theo đường an toàn**, không bị host tùy tiện giết giữa một thao tác đang giữ lock hoặc giữa transaction.

### 4.1. Cancellation token cho vòng lặp CPU hoặc workflow nhiều bước

Một mô hình tối thiểu:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean();

    void cancel() { requested.set(true); }
    boolean isCancelled() { return requested.get(); }
}
~~~

Đây là class hoàn chỉnh nhưng **không có `main`**. Mỗi tác vụ nhận token thuộc vòng đời request hoặc plugin rồi kiểm tra tại các điểm an toàn:

~~~java
for (Item item : items) {
    if (token.isCancelled()) {
        // Dừng tại boundary an toàn; cleanup/rollback qua finally hoặc policy riêng.
        break;
    }
    process(item);
}
~~~

Vòng trên là **minh họa giả định** `items`/`process` và `token` đã được định nghĩa. Token không tự phá được tác vụ đang kẹt ở blocking I/O; nếu không có điểm kiểm tra, nó chỉ là một cờ không được quan sát.

### 4.2. Thread interruption cho tác vụ đang chờ

`Thread.interrupt()` đặt interrupt status và đánh thức nhiều thao tác blocking chuẩn như `CountDownLatch.await()`, `Thread.sleep()` và `Object.wait()` bằng `InterruptedException`. Nó không phải `Thread.stop()` và không bảo đảm mọi đoạn code hoặc native I/O đều dừng.

Ví dụ xử lý đúng ở boundary có trách nhiệm:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Khôi phục trạng thái nếu không ném tiếp.
    return; // Thoát, sau đó finally sẽ dọn tài nguyên.
}
~~~

Đây là snippet, chưa có method `blockingOperation`. Nếu method cho phép `throws InterruptedException`, **ưu tiên truyền exception lên trên** thay vì catch rồi tiếp tục làm việc như bình thường. Khi `InterruptedException` được ném bởi nhiều blocking API, interrupt status đã được xóa; khôi phục bằng `Thread.currentThread().interrupt()` trước khi rời tầng không ném tiếp là quy ước quan trọng.

**Sai:** bắt `InterruptedException` rồi bỏ qua và tiếp tục vòng lặp, hoặc gọi `Thread.interrupted()` chỉ để in log mà vô tình xóa trạng thái. `Thread.currentThread().isInterrupted()` đọc cờ mà **không xóa**.

### 4.3. `Future.cancel(true)` và `shutdownNow()` có giới hạn gì?

- `Future.cancel(true)` **thử** hủy task, có thể yêu cầu interrupt nếu task đang chạy; việc Future có `isCancelled()==true` hoặc `isDone()==true` không chứng minh code task đã ra khỏi `finally`.
- `ExecutorService.shutdown()` ngừng nhận task mới, cho task đã submit cơ hội hoàn tất; nó **không tự chờ**. Cần gọi `awaitTermination(timeout, unit)`.
- `ExecutorService.shutdownNow()` thử dừng task đang chạy, ngăn task còn trong queue bắt đầu và trả về các `Runnable` chưa khởi chạy; cách làm thường dựa vào interrupt, **best effort**, không có bảo đảm thread kết thúc.
- Với `CompletableFuture.cancel(boolean)`, API nêu tham số `mayInterruptIfRunning` **không ảnh hưởng đến implementation** của `CompletableFuture`, nên không dựa vào lời gọi đó để khẳng định worker thread bị interrupt.
- `Thread.stop()`/`Thread.suspend()` là các cơ chế nguy hiểm, deprecated, có thể làm hỏng invariant/lock; **không** dùng để ép ngừng plugin.

Nếu task thực hiện database transaction, host phải quy định ranh giới commit/rollback và cơ chế idempotency. Hủy request không có nghĩa thao tác bên ngoài JVM (HTTP API, transaction, message publish) chắc chắn đã được đảo ngược.

### 4.4. Tránh interrupt sai thread trong shared pool

Đối với **thread được tạo riêng cho request/plugin**, host có thể giữ tham chiếu và gửi interrupt trong ví dụ. Nhưng **không nên** lưu `Thread` của các task chạy trên pool dùng chung rồi interrupt không có điều kiện: task có thể đã kết thúc và thread được tái sử dụng cho công việc plugin khác/host khi tín hiệu đến muộn.

Trong production, nên:

- Quản lý `Future`/cancellation handle riêng cho **từng task** và token riêng cho generation.
- Dùng executor thuộc sở hữu plugin nếu muốn gọi `shutdown()/shutdownNow()` mà không ảnh hưởng host.
- Gắn version/generation ID khi đăng ký tác vụ để không gửi cancel nhầm sang thế hệ mới.
- Bảo đảm mã task kiểm tra token/interrupt và hoàn tất cleanup rồi mới được tính là quiesced.
- Tách cancellation **logical** của Future khỏi completion **physical** của công việc plugin.

## 5. Ví dụ Java 17 đầy đủ: cổng tiếp nhận, drain và cancel

Ví dụ độc lập sau đây mô tả hai tình huống:

- **Graceful:** plugin đã chấp nhận một công việc; host quiesce, chờ, rồi worker tự hoàn tất; không cần cancel.
- **Timeout/abort:** plugin đã chấp nhận một công việc đang chờ latch; host quiesce, từ chối request mới, xác nhận chưa drain, phát interrupt hợp tác, đợi worker thoát rồi đánh dấu `STOPPED`.

Vì là bài học về shutdown, code cố ý dùng `CountDownLatch` thay cho network/database để **stdout ổn định**, không phụ thuộc vào tốc độ máy. Đây là mô hình cổng đồng bộ; nó không tự đăng ký HTTP routes, message subscriptions hay `ExecutorService`. Ví dụ cũng chưa có tài nguyên plugin thật để đóng; với plugin thực tế phải cleanup **sau khi drain** và **trước khi công bố stop hoàn tất**.

### 5.1. Một tệp PluginShutdownDemo.java

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class PluginShutdownDemo {
    static final class PluginGate {
        enum State { ACTIVE, QUIESCING, STOPPED }

        private final ReentrantLock lock = new ReentrantLock();
        private final Condition drained = lock.newCondition();
        private final Map<Thread, Integer> activeThreads = new HashMap<>();
        private State state = State.ACTIVE;
        private int inFlight;
        private volatile boolean cancelRequested;

        <T> T call(Callable<T> operation) throws Exception {
            Objects.requireNonNull(operation);
            Thread owner = Thread.currentThread();
            lock.lock();
            try {
                if (state != State.ACTIVE) {
                    throw new RejectedExecutionException("plugin is stopping");
                }
                inFlight++;
                activeThreads.merge(owner, 1, Integer::sum);
            } finally {
                lock.unlock();
            }
            try {
                return operation.call();
            } finally {
                lock.lock();
                try {
                    inFlight--;
                    activeThreads.compute(owner,
                            (thread, depth) -> depth == 1 ? null : depth - 1);
                    if (inFlight == 0) drained.signalAll();
                } finally {
                    lock.unlock();
                }
            }
        }

        void quiesce() {
            lock.lock();
            try {
                if (state == State.ACTIVE) state = State.QUIESCING;
            } finally {
                lock.unlock();
            }
        }

        boolean awaitDrained(Duration timeout) throws InterruptedException {
            long remaining = timeout.toNanos();
            if (remaining < 0) throw new IllegalArgumentException("negative timeout");
            lock.lockInterruptibly();
            try {
                while (inFlight > 0 && remaining > 0) {
                    remaining = drained.awaitNanos(remaining);
                }
                return inFlight == 0;
            } finally {
                lock.unlock();
            }
        }

        void requestCancellation() {
            List<Thread> snapshot;
            lock.lock();
            try {
                if (state != State.QUIESCING) {
                    throw new IllegalStateException("quiesce first");
                }
                cancelRequested = true;
                snapshot = new ArrayList<>(activeThreads.keySet());
            } finally {
                lock.unlock();
            }
            for (Thread thread : snapshot) {
                thread.interrupt();
            }
        }

        boolean cancellationRequested() {
            return cancelRequested;
        }

        int activeCalls() {
            lock.lock();
            try { return inFlight; }
            finally { lock.unlock(); }
        }

        void markStopped() {
            lock.lock();
            try {
                if (state != State.QUIESCING || inFlight != 0) {
                    throw new IllegalStateException("still running");
                }
                state = State.STOPPED;
            } finally {
                lock.unlock();
            }
        }

        State state() {
            lock.lock();
            try { return state; }
            finally { lock.unlock(); }
        }
    }

    public static void main(String[] args) throws Exception {
        PluginGate normal = new PluginGate();
        CountDownLatch normalEntered = new CountDownLatch(1);
        CountDownLatch normalRelease = new CountDownLatch(1);
        Thread normalWorker = new Thread(() -> {
            try {
                normal.call(() -> {
                    normalEntered.countDown();
                    normalRelease.await();
                    return "ok";
                });
                System.out.println("gracefulWorker=completed");
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }, "normal-request");
        normalWorker.start();
        normalEntered.await();
        normal.quiesce();
        System.out.println("gracefulBeforeRelease="
                + normal.awaitDrained(Duration.ZERO));
        normalRelease.countDown();
        normalWorker.join();
        System.out.println("gracefulAfterRelease="
                + normal.awaitDrained(Duration.ofSeconds(1)));
        normal.markStopped();
        System.out.println("gracefulState=" + normal.state());

        PluginGate gate = new PluginGate();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocked = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                gate.call(() -> {
                    started.countDown();
                    blocked.await();
                    return "completed";
                });
            } catch (InterruptedException expected) {
                Thread.currentThread().interrupt();
                System.out.println("worker=cancelled");
            } catch (Exception unexpected) {
                throw new RuntimeException(unexpected);
            }
        }, "plugin-request");

        worker.start();
        started.await();
        System.out.println("inFlight=" + gate.activeCalls());

        gate.quiesce();
        System.out.println("state=" + gate.state());
        try {
            gate.call(() -> "late request");
        } catch (RejectedExecutionException expected) {
            System.out.println("lateRequest=rejected");
        }
        System.out.println("drainedBeforeCancel="
                + gate.awaitDrained(Duration.ZERO));

        gate.requestCancellation();
        worker.join();
        System.out.println("cancelRequested=" + gate.cancellationRequested());
        System.out.println("drainedAfterCancel="
                + gate.awaitDrained(Duration.ofSeconds(1)));
        gate.markStopped();
        System.out.println("state=" + gate.state());
    }
}
~~~

Tại sao `activeThreads` là `Map<Thread,Integer>` thay vì `Set<Thread>`? Một thread có thể gọi lồng `gate.call(...)`; map giữ số lần đăng ký theo thread để việc thoát inner call không xóa nhầm thread vẫn còn outer call. `inFlight` được tăng/giảm theo mỗi lần vào/ra. Mọi cập nhật bộ đếm và map đều nằm dưới lock; gọi `operation.call()` nằm **ngoài** lock.

Trong ví dụ, mỗi task dùng **thread chuyên biệt** và không tái sử dụng thread đó cho task khác. `requestCancellation` snapshot các thread đang thực hiện plugin và gửi interrupt **sau khi nhả lock** để tránh giữ mutex trong lúc tác động lên task. Với pool dùng chung/async task, phải thay cách tracking bằng task-specific cancellation handles như mục 4.4.

### 5.2. Biên dịch và chạy

Lưu đúng tệp `PluginShutdownDemo.java` trong thư mục hiện tại. Với Java 17 trở lên:

~~~bash
javac --release 17 PluginShutdownDemo.java
java -cp . PluginShutdownDemo
~~~

**Stdout đã kiểm chứng bằng Amazon Corretto JDK 17.0.15:**

~~~text
gracefulBeforeRelease=false
gracefulWorker=completed
gracefulAfterRelease=true
gracefulState=STOPPED
inFlight=1
state=QUIESCING
lateRequest=rejected
drainedBeforeCancel=false
worker=cancelled
cancelRequested=true
drainedAfterCancel=true
state=STOPPED
~~~

### 5.3. Phân tích nhánh graceful

1. `normalWorker` vào `normal.call(...)` trước: bộ đếm tăng lên 1 và latch `normalEntered` thông báo đã được accept.
2. `normal.quiesce()` đóng cổng; request này **vẫn được phép hoàn thành** vì nó đã đi qua admission.
3. `awaitDrained(Duration.ZERO)` trả ngay `false` do worker vẫn chờ `normalRelease`.
4. Host mở latch, worker hoàn tất bình thường. `finally` của `call` giảm bộ đếm về 0 và `signalAll()`.
5. `normalWorker.join()` bảo đảm thread kết thúc trong fixture; `awaitDrained(Duration.ofSeconds(1))` trả `true`; host mới gọi `markStopped()`.

Điều quan trọng: **không cần hủy** nếu các task hoàn tất trong thời gian grace. Đóng cổng không nên mặc định phá tất cả request đã được nhận.

### 5.4. Phân tích nhánh cancel

1. `worker` được accept, `inFlight=1`, rồi block ở `CountDownLatch.await()`.
2. Host đổi `state=QUIESCING`; một `gate.call(...)` mới bị từ chối bằng `RejectedExecutionException`.
3. `awaitDrained(Duration.ZERO)` trả `false`; không được bỏ qua tình trạng này để chuyển thẳng sang `STOPPED`.
4. `requestCancellation()` đặt volatile token và gọi `interrupt()` tới thread chuyên biệt của fixture.
5. `blocked.await()` phản ứng bằng `InterruptedException`. Worker catch, khôi phục interrupt status và thoát; `finally` trong `gate.call` **vẫn chạy** để giảm `inFlight`.
6. Host gọi `worker.join()`; sau đó `awaitDrained(...)` trở thành `true` và `markStopped()` thành công.

Kết quả này chứng minh **tín hiệu hủy** và **xác nhận công việc đã kết thúc** phải được xử lý thành hai bước độc lập. Trong chương trình này `join()` không có timeout vì test fixture biết chắc latch hỗ trợ interrupt; production không được giả định mọi plugin sẽ phản ứng nhanh như vậy.

### 5.5. Những ranh giới của demo

- `PluginGate.call` chạy đồng bộ trong thread gọi nó; nếu plugin gọi `executor.submit(...)` rồi trả ngay, phải giữ lease hoặc theo dõi **task async thật** đến khi nó thoát.
- `blocked` cố ý không bao giờ được `countDown()`; nó dùng để minh họa interrupt của task đang chờ. Thực tế nên có deadline để host không kẹt vô hạn.
- `requestCancellation()` giữ bản snapshot thread đã đăng ký và interrupt; phù hợp **thread dành riêng cho công việc của ví dụ**, không phải pattern an toàn mặc định cho thread pool dùng chung.
- `markStopped()` ở demo chỉ đổi state vì không sở hữu DB connection/HTTP client/executor. Khi có tài nguyên thật, phải đóng/cleanup chúng theo thứ tự và ghi nhận lỗi trước khi đánh dấu hoàn tất.
- Mô hình xử lý `InterruptedException` phía trong callback là trách nhiệm tác vụ; host không thể ép code plugin phản ứng nếu callback bỏ qua tín hiệu.
- `Duration.toNanos()` có thể ném lỗi với duration âm/quá lớn; production nên validate ngân sách tổng và xử lý overflow khi dựng deadline.

## 6. Khi plugin dùng ExecutorService hoặc Future

Nhiều plugin sử dụng background executor riêng. Nếu **executor là tài nguyên thuộc plugin**, API `ExecutorService` đã hỗ trợ một shutdown hai pha:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

static boolean stopOwnedExecutor(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown(); // Ngừng nhận task mới trong executor này.
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow(); // Best effort: cancel queued/running tasks.
        return executor.awaitTermination(3, TimeUnit.SECONDS);
    }
    return true;
}
~~~

Đây là **method minh họa**, phải đặt trong một class. Các timeout là ví dụ chính sách, không phải thời lượng mặc định của JDK.

**Thứ tự thực tế cần thực hiện:**

1. Đóng cổng plugin ở router/registry/consumer trước, để callback không tiếp tục tạo task mới.
2. Chỉ gọi `executor.shutdown()` nếu executor **thuộc quyền sở hữu riêng của plugin**.
3. Chờ `awaitTermination` với giới hạn cụ thể. Nếu timeout, gọi `shutdownNow()` rồi chờ lần nữa.
4. Nếu executor vẫn chưa terminate, **không** coi `shutdownNow()` là thành công; báo stop-incomplete, quarantine plugin hoặc để cấp điều phối cao hơn quyết định restart process.
5. Ngoài executor này còn có thread, subscription hoặc continuation độc lập không? Chúng phải được theo dõi riêng.

`shutdownNow()` trả về list những task chưa chạy. Nếu hệ thống có bộ đếm task pending/accepted, cần cập nhật chúng nhất quán sau khi queue bị hủy. Đối với `Future.cancel(true)`, đừng dùng `Future.isDone()` làm thay thế chắc chắn cho việc **worker đã ra khỏi plugin code**.

**Lưu ý khi bị interrupt trong shutdown:** Nếu thread điều phối bị `InterruptedException` khi đợi, nó phải bảo toàn yêu cầu hủy, áp dụng chính sách cấp trên và thường khôi phục interrupt status ở tầng không ném tiếp. Không “nuốt” interruption rồi ghi log `STOPPED` dù công việc vẫn đang chạy.

## 7. Khi request sinh ra công việc bất đồng bộ

Một handler có thể trông như đã xong nhưng vẫn có tác vụ plugin tồn tại:

~~~java
// Minh họa lỗi vòng đời nếu chỉ đếm thời gian handler chạy:
CompletionStage<Result> handle(Request request) {
    return remoteCall(request).thenApply(this::transform);
}
~~~

Nếu `handle` trả lại `CompletionStage` ngay và admission lease được release tại thời điểm **trả stage**, việc drain có thể về 0 trong khi continuation `transform` chưa chạy. Để đúng, một hướng là:

~~~java
// Mã minh họa: lease và stage được định nghĩa bởi host.
CompletionStage<Result> stage = startPluginWork(request);
return stage.whenComplete((value, failure) -> lease.close());
~~~

`lease.close()` trong callback `whenComplete` phải được thiết kế **idempotent**, bảo đảm đúng một lần decrement, và không bỏ sót khi `startPluginWork` ném lỗi trước khi trả stage. Có thể dùng `try/catch` cho nhánh submit thất bại và một `AtomicBoolean` guard cho việc release; quan trọng là không đếm đôi.

**Phân biệt thêm:** một future/stage có thể hoàn tất **trước khi mọi công việc bên ngoài nó dừng thật sự**, đặc biệt khi cancellation chỉ đổi trạng thái logical. Nếu plugin khởi chạy thread/process phụ mà stage không theo dõi, host vẫn cần tracking độc lập.

### 7.1. Task tiếp tục sinh task sau khi quiesce

Một request đã được accept có thể muốn phát sinh job con. Hãy định nghĩa chính sách:

- **Không chấp nhận task con mới** sau quiesce (đơn giản và an toàn nếu handler có thể tự kết thúc).
- Hoặc cho phép task con thuộc request đã được accept và **kế thừa cùng request lease**, nhưng phải bảo đảm deadline/cancellation được truyền và drain chờ cả cây task.

Không nên để request cũ mở cổng lại hoặc đăng ký background timer mới vô thời hạn. Vì vậy token nên được propagate qua RPC, callback chain và executor wrapper, thay vì một cờ boolean ở root không ai kiểm tra.

### 7.2. Điều phối hủy với side effects

Nếu plugin thực hiện chuỗi:

~~~text
read input -> update database -> publish event -> acknowledge message
~~~

dừng hợp tác giữa hai bước có thể để lại trạng thái “DB đã ghi, message chưa publish”. Cancellation không tự đảo ngược side effect đã commit. Cần transaction ở phạm vi hỗ trợ, outbox pattern, idempotency key, checkpoint/retry và xử lý duplicate theo hợp đồng nghiệp vụ. Đặc biệt trong message consumer, đừng ack sớm khi handler chưa thực sự thành công; shutdown phải có chính sách requeue/dead-letter hoặc retry rõ ràng.

## 8. Hot reload: một thế hệ plugin mới và một thế hệ cũ

Một cách triển khai an toàn hơn “đóng rồi load lại ngay”:

~~~text
Version/generation V1                  Version/generation V2
---------------------                  ---------------------
ACTIVE: accepts traffic                LOADING + health check
      |
      +-- atomically update host routing to V2 -----------> ACTIVE
      |
      +-- QUIESCING: reject new V1 entry
      |
      +-- DRAIN or CANCEL outstanding V1 calls
      |
      +-- detach callbacks, timers, event subscriptions
      |
      +-- close V1-owned resources and classloader (when safe)
      |
      +-- STOPPED; release strong references to V1
~~~

Chỉ chuyển route sang V2 khi V2 đã được nạp, đăng ký và kiểm tra sức khỏe phù hợp. Nếu phiên bản mới fail initialization, giữ V1 phục vụ (nếu chưa quiesce) hoặc rollback routing theo chính sách rõ ràng; không mặc nhiên kéo state V1 từ QUIESCING về ACTIVE nếu việc đó có thể tái sử dụng tài nguyên đang bị cleanup.

### 8.1. Detach callback phải có thứ tự

Một shutdown thông thường gồm:

1. **Disable/quiesce ingress:** ngăn route mới, deregister service discovery đối với generation cũ, pause message consumer nếu API hỗ trợ.
2. **Stop producers:** dừng timer/cron/retry producers tạo thêm work.
3. **Drain hoặc cancel:** chờ active requests, long-running tasks, queue và continuations.
4. **Detach extension hooks:** unregister event listeners, callbacks, MBeans, service handles, observers, thread-local references liên quan.
5. **Close owned resources:** plugin-owned executor, HTTP/DB client, file handles, sockets, cache, classloader/JAR handles theo ownership.
6. **Remove registry strong refs:** bỏ instance, `Class<?>`, provider factory, `ModuleLayer` và loader của V1 khỏi các registry/cache khi không còn sử dụng.
7. **Report terminal outcome:** STOPPED hoặc trạng thái lỗi/needs escalation nếu vẫn có work không chịu dừng.

Không đóng resources theo một thứ tự cứng chung cho mọi plugin. Chẳng hạn worker cần DB connection để hoàn tất rollback thì đóng pool DB trước khi worker thoát là sai; ngược lại scheduler producer phải dừng sớm để không tạo task mới.

### 8.2. Closing ClassLoader không có nghĩa unloading class ngay

`URLClassLoader.close()` giải phóng tài nguyên của loader như handles đến các JAR được quản lý, nhưng nó **không** cưỡng bức JVM unload mọi class đã từng được loader đó định nghĩa và không hủy instance còn tồn tại. Còn tham chiếu từ thread, thread context class loader (TCCL), static registry trong host, cache, listener hoặc đang chạy method của plugin thì generation cũ có thể không được thu hồi.

Nếu dùng custom `ModuleLayer`, module graph/classloader cũng tuân theo khả năng truy cập object và cơ chế thu gom. Không có `ModuleLayer.close()` chuẩn để chấm dứt mọi tác vụ trong layer. Chủ động gỡ references/callbacks và để GC quyết định khả năng thu hồi sau khi hết sử dụng.

### 8.3. Không cancel nhầm V2 khi đang stop V1

Mọi task cancellation handle, token, lease và registry entry nên gắn với **generation ID**, không chỉ plugin logical name. Ví dụ `payments:v12` khác `payments:v13`, dù cả hai cùng implement `PaymentPlugin`. Hành động “stop v12” chỉ được đóng gate và cancel task của generation v12.

Nếu tất cả phiên bản dùng chung executor, chỉ cancel **task handles của V1**, không `shutdownNow()` pool chung. Nếu dùng TCCL để nạp plugin, restore TCCL của worker trong `finally` ngay sau tác vụ, tránh giữ classloader cũ trên thread pool.

## 9. Phương án khi một plugin không chịu hủy

Có task không phản ứng với interrupt: đang chạy vòng lặp CPU không kiểm tra token, mắc kẹt ở native call, bị lock deadlock hoặc chờ I/O không có timeout. Sau grace period và cancel grace period, **không nói đã dừng thành công** khi chưa có chứng cứ.

| Trạng thái quan sát | Phản ứng nên chọn |
| --- | --- |
| `inFlight==0`, resource cleanup thành công | Chuyển `STOPPED` |
| Task chưa thoát nhưng vẫn phản hồi cancel | Chờ trong ngân sách còn lại, cập nhật progress |
| Task không phản hồi, không thể isolate | Giữ `FAILED_TO_STOP`/`QUARANTINED`, không tái sử dụng resource có nguy cơ |
| Task đang giữ side effect/transaction nguy hiểm | Không đóng connection/loader một cách mù quáng; kích hoạt recovery policy |
| Process shutdown có deadline cứng | Điều phối cấp process có thể phải terminate/restart instance và khôi phục công việc bền vững sau đó |

Đối với plugin chạy **trong cùng một JVM**, không có primitive Java SE an toàn để “cưỡng bức kết thúc riêng một plugin bất kỳ” mà chắc chắn không làm hỏng host. Nếu yêu cầu cách ly cứng cho mã không hợp tác, nên chạy plugin không tin cậy trong **process/container riêng** và dùng IPC/RPC; khi đó cấp điều phối hệ điều hành có thể terminate process sau deadline với cơ chế phục hồi thích hợp.

Shutdown coordinator phải ghi nhận **quá hạn** và trả kết quả không thành công khi cần. Đánh dấu `STOPPED` chỉ để làm dashboard đẹp là lỗi vận hành nghiêm trọng.

## 10. Chính sách timeout, retry và dữ liệu cần quan sát

Đặt một chính sách shutdown cụ thể, ví dụ:

| Giai đoạn | Ví dụ thời lượng | Quy tắc |
| --- | --- | --- |
| Quiesce admission | Ngay khi bắt đầu stop | Không accept request mới sau điểm đồng bộ đóng gate |
| Graceful drain | 10 giây | Chờ có điều kiện, không interrupt sớm các task sắp hoàn tất |
| Cooperative cancel grace | 5 giây tiếp theo | Gửi token/cancel handles, interrupt đúng những task hỗ trợ |
| Cleanup | Theo budget còn lại | Gỡ listener, close đúng resource đã sở hữu |
| Escalation | Khi hết tổng deadline | Báo non-terminal/incomplete hoặc restart process theo policy |

Các giá trị chỉ là **ví dụ vận hành**, không phải timeout chuẩn của `ServiceLoader`/JPMS/JDK. Cấu hình thời gian phụ thuộc giao ước SLA, loại task và deadline của platform.

Nên đo và ghi log:

- `pluginId`, `generationId`, state trước/sau, lý do stop (deploy, disable, crash, timeout).
- Thời điểm đóng ingress, active/queued requests lúc bắt đầu và còn lại theo từng giai đoạn.
- Số tác vụ hoàn tất tự nhiên, thất bại, bị cancel, bỏ qua interrupt hoặc còn treo.
- Thời gian drain, thời gian cancel, thời gian cleanup, tổng thời gian đến terminal outcome.
- Những tài nguyên không đóng được, stack traces, nguyên nhân thực của `InterruptedException`/`CancellationException`.
- Tỷ lệ late requests rejected và hành vi trả response/fallback cho caller.

Không cần log dữ liệu nhạy cảm từ request hoặc toàn bộ script/plugin payload để theo dõi shutdown. Log định danh tác vụ và lỗi có chủ đích, hạn chế leakage.

## 11. Những lỗi thường gặp và cách sửa

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| Đặt boolean `enabled=false` không có đồng bộ với nhận task | Race: request vượt qua check trước khi gate đóng | Admission state và `inFlight++` phải atomic dưới cùng lock/CAS protocol |
| `inFlight++` lúc submit, decrement chỉ trong `Runnable.finally` | Task bị hủy khi còn trong queue không chạy finally | Có lease cho queued/cancel-before-start, giải phóng đúng một lần |
| Dùng `Future.isDone()` để chứng minh plugin idle | Future canceled có thể complete trước khi code worker thoát | Theo dõi completion vật lý/owned executor termination |
| `shutdownNow()` rồi đóng plugin ngay | Interrupt chỉ best effort | Chờ `awaitTermination`/drain xác nhận, report failure nếu không dừng |
| Catch `InterruptedException` rồi bỏ qua | Task tiếp tục chạy khi host tưởng đã hủy | Truyền lên hoặc khôi phục interrupt rồi thoát ở điểm an toàn |
| Gọi `Thread.stop()` | Phá invariants/locks và trạng thái chia sẻ | Cancellation token và interruption tự nguyện |
| Giữ lock trong lúc chạy callback plugin | Deadlock, shutdown không lấy được lock | Lock chỉ quản lý state/counter, release trước callback |
| Đóng DB client/JAR loader trước drain | Task đang dùng resource lỗi giữa chừng | Đợi task dừng/rollback phù hợp rồi close |
| Chỉ gỡ router, quên event listener/timer | Plugin vẫn được gọi ngoài HTTP | Inventory mọi ingress và async continuation |
| Dùng cùng ID để cancel V1 và V2 | Có thể hủy request phiên bản mới | Gắn generation ID và ownership vào task handles |
| Không đặt deadline | Shutdown treo mãi nếu plugin không hợp tác | Grace budget, cancel budget, escalate rõ ràng |
| Bắt mọi `Throwable` rồi báo thành công | Nuốt lỗi cleanup/stop nghiêm trọng | Tập hợp lỗi, giữ trạng thái failed/incomplete nếu cần |
| Đóng executor chia sẻ giữa plugins | Làm hỏng host hoặc plugin khác | Chỉ shutdown resource plugin sở hữu |
| Xóa registry nhưng còn TCCL/callback | Giữ classloader cũ, leak | Cleanup callback/TCCL/threads/cache và kiểm tra heap khi cần |

Một điều dễ nhầm: `ServiceLoader.reload()` chỉ làm mới cache provider của một đối tượng loader; nó **không** ngừng các request đang chạy, cancel tác vụ, đóng instance, đóng thread pool hoặc unload plugin. Đừng sử dụng `reload()` như một lệnh shutdown.

## 12. Kiểm thử và tiêu chí chấp nhận

Một triển khai lifecycle đáng tin cậy nên có bộ kiểm thử tự động:

### 12.1. Admission race

Chạy nhiều request cạnh tranh với `quiesce`. Xác minh sau điểm quiesce không có request nào **được accept mới** vào generation đó. Những request đã accept trước mốc phải được ghi nhận trong active/queued counters. Không chỉ kiểm tra giá trị cuối; thử bơm request liên tục trong lúc stop.

### 12.2. Graceful completion

Tạo một task bị chặn bởi latch; chuyển gate sang QUIESCING; xác minh drain chưa xong; mở latch và xác minh drain thành công. Không có cancellation cần thiết. Nhánh này được minh họa ở `gracefulBeforeRelease=false` / `gracefulAfterRelease=true` của code mục 5.

### 12.3. Cooperative cancellation

Dùng task blocking trong `await` hoặc `sleep` và task CPU có token checks. Phát cancel; kiểm tra worker nhận tín hiệu, chạy `finally`, giảm counter đúng một lần. Nhánh `worker=cancelled` của code mẫu thể hiện chờ interruptible. Thêm test một task bỏ qua interrupt để kiểm tra **timeout dẫn đến FAILED_TO_STOP**, không báo `STOPPED`.

### 12.4. Queued task bị hủy trước khi chạy

Đưa task vào bounded queue, quiesce rồi cancel pending tasks. Kiểm tra task chưa bắt đầu vẫn được release khỏi accepted/queued count; không chờ một `finally` chưa từng chạy. Nếu giữ `Future`, phân biệt isCancelled với task cleanup thực tế.

### 12.5. Async continuation và callbacks

Task gốc trả `CompletionStage` sớm; stage vẫn đang xử lý. Đảm bảo drain chưa hoàn tất; sau khi stage/child tasks kết thúc mới release generation lease. Ngừng timer/scheduler và unregister hook để không phát sinh lại work.

### 12.6. Cleanup lỗi và reload

Giả lập lỗi `AutoCloseable.close()`; hệ thống phải log lỗi, xử lý các resource còn lại theo chính sách, không che là thành công tuyệt đối. Nạp generation mới song song với generation cũ đang drain; bảo đảm task V1 không gọi nhầm V2 và việc stop V1 không shutdown shared executor.

### 12.7. Thread interruption của coordinator

Cắt ngang thread đang `awaitDrained`. Đảm bảo quy trình shutdown không lén bỏ dở mà công bố STOPPED; trạng thái quiesce vẫn được bảo toàn, interruption được truyền/khôi phục đúng theo ownership, coordinator cấp trên biết tác vụ stop chưa hoàn tất.

### 12.8. Metrics và memory leak

Sau nhiều vòng load/quiesce/unload, theo dõi threads, executor, active listener, open handles và retained classloaders. Không hứa classloader sẽ GC ngay; có thể dùng heap dump và weak references để điều tra các strong references còn tồn tại sau một thời gian hợp lý.

**Tiêu chí `STOPPED`:** cổng không nhận request mới; mọi công việc generation đã chấm dứt theo định nghĩa đã thống nhất; callback/subscription và resource sở hữu đã cleanup; không còn đường host cố tình gọi lại plugin cũ; không có lỗi stop chưa được giải quyết hoặc bị che giấu.

## 13. Checklist triển khai trong hệ plugin thật

Trước khi đưa feature hot reload/disable vào production, trả lời rõ:

1. **Tất cả ingress nào có thể gọi plugin?** Router, event bus, scheduler, message consumer, callback registry, async tasks.
2. **Admission ở đâu?** Có một điểm đồng bộ bảo đảm `accept` và `quiesce` không race không?
3. **Đếm cái gì?** In-flight call, task đang queue, future/continuation hay tất cả? Có release đúng một lần ngay cả khi exceptional completion/cancel trước lúc chạy?
4. **Grace budget bao nhiêu?** Ai sở hữu deadline tổng, có ưu tiên hoàn tất request hợp lệ không?
5. **Cơ chế cancel cụ thể?** Task có token checks, interruptible waits, timeout cho I/O, rollback/idempotency không?
6. **Xác nhận task thực sự dừng ở đâu?** Không nhầm Future canceled với worker exited.
7. **Khi task không chịu dừng thì sao?** Có state incomplete/quarantine, alarm, process isolation hoặc restart policy không?
8. **Tài nguyên nào thuộc plugin?** Executor, connections, cache, listeners, class loader; không đóng đồ host chia sẻ.
9. **Hot reload quản lý generation thế nào?** Routing mới, cancel riêng V1, loại bỏ refs cũ, không ảnh hưởng V2.
10. **Kiểm thử khó gồm gì?** Concurrent requests, queued cancellation, async continuation, delayed interrupt, timeout, cleanup failure và leak.
11. **Dữ liệu nghiệp vụ sau cancel?** Có transaction/compensation, idempotency, retry và cơ chế bảo toàn kết quả cho request đã nhận không?
12. **Ai được phép công bố STOPPED?** Chỉ coordinator đã xác minh điều kiện dừng thật sự, không dựa vào timeout hoặc chỉ một tín hiệu cancel.

## 14. Ghi nhớ nhanh

~~~text
RUNNING
   |
   +-- close admission gate (atomic with new-request registration)
   v
QUIESCING
   |
   +-- wait until inFlight == 0 (bounded graceful deadline)
   |              |
   |              +-- drained --> cleanup owned resources --> STOPPED
   |
   +-- timeout --> request cooperative cancellation
                           |
                           +-- set token / cancel task handles / interrupt when safe
                           |
                           +-- wait until ACTUAL workers have exited
                                         |
                                         +-- drained --> cleanup --> STOPPED
                                         |
                                         +-- still running --> FAILED_TO_STOP
                                                            / QUARANTINED
                                                            / escalation
~~~

**Nguyên tắc kết luận:** **Dừng nhận yêu cầu** là thay đổi chính sách admission; **chờ công việc đang chạy** là một sự kiện thực tế phải đo được; **hủy hợp tác** chỉ là tín hiệu đề nghị task tự dừng. Ba việc này không thể thay thế nhau. Một plugin chỉ hoàn tất vòng đời shutdown khi không còn đường vào thế hệ cũ, các tác vụ thực sự không còn dùng tài nguyên của nó và cleanup đã được thực hiện theo ownership.

### Tài liệu tham khảo chính thức

- [Java SE 17 – ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination` và mẫu shutdown hai pha.
- [Java SE 17 – Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `join`, trạng thái interruption, lý do `Thread.stop()` không an toàn.
- [Java SE 17 – InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html): phản ứng khi đợi/chờ bị ngắt và status.
- [Java SE 17 – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): yêu cầu cancel và trạng thái Future.
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): ngữ nghĩa cancel trong implementation.
- [Java SE 17 – Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `awaitNanos`, condition wait và spurious wakeups.
- [Java SE 17 – URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()` và phạm vi giải phóng tài nguyên của class loader.
