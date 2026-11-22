# Tránh chặn luồng dọn dẹp hoặc làm mất lỗi quan trọng

`Cleaner` dùng một thread gắn với cleaner để xử lý các object đã trở nên phantom reachable và chạy cleaning action. API cho phép nhiều đăng ký dùng chung một Cleaner; vì vậy một action bị block có thể trì hoãn những action khác trong cùng Cleaner. Tài liệu Java cũng quy định mọi exception thoát ra từ cleaning action đều bị Cleaner bỏ qua.

Điều này tạo ra hai yêu cầu thiết kế: action phải ngắn và không chặn; mọi lỗi cleanup quan trọng phải được ghi nhận ngay bên trong action. Với đường đóng tường minh, `close()` cần thực hiện cleanup trong ngữ cảnh caller và truyền lỗi trở lại caller. Không dùng exception thoát khỏi `Runnable.run()` hoặc `UncaughtExceptionHandler` làm kênh báo lỗi cho Cleaner.

## Mục tiêu

- Hiểu thread thực thi cleaning action và tác động của action bị block.
- Giữ action ngắn, không chờ I/O, network, lock hoặc tác vụ khác.
- Tách cleanup nhanh khỏi công việc shutdown có thể block.
- Hiểu vì sao exception từ cleaning action không được truyền tới caller.
- Ghi nhận lỗi fallback bằng một kênh thread-safe, không block.
- Thiết kế `close()` để lỗi cleanup tường minh được trả về caller.
- Giữ exception chính và exception cleanup bằng cơ chế suppressed của try-with-resources.
- Đồng bộ trạng thái khi explicit close và Cleaner action cạnh tranh.

## 1. Cleaner thực thi action trên thread riêng

`Cleaner.create()` tạo một Cleaner cùng một daemon thread để xử lý các object phantom reachable và gọi cleaning action. Có thể cung cấp `ThreadFactory` bằng `Cleaner.create(threadFactory)` nếu cần cấu hình thread, nhưng điều đó không biến cleaning action thành công việc chạy trên executor có queue riêng.

Một Cleaner quản lý nhiều đăng ký. Nếu một action chờ network, chờ lock, sleep hoặc chờ một future chưa hoàn tất, thread của Cleaner có thể bị giữ lại và các action khác của cùng Cleaner bị trì hoãn.

~~~text
Cleaner thread
     |
     +---- action A: release nhanh ----> hoàn tất
     |
     +---- action B: chờ network ------> BLOCKED
     |
     +---- action C: cleanup ngắn -----> phải chờ B
~~~

API note khuyến nghị cleaning action chạy rất nhanh và không block. Các action cũng phải tương thích khi có thể được gọi đồng thời với action khác. Không dựa vào một thứ tự thực thi cố định giữa các đăng ký.

## 2. Những việc không nên làm trong cleaning action

Tránh các thao tác có thể chờ không giới hạn hoặc phụ thuộc hệ thống bên ngoài:

- Gọi network, HTTP, database hoặc RPC.
- Flush/close một pipeline I/O có thể chờ dữ liệu hoặc peer.
- Dùng `Thread.sleep()`, `join()`, `Future.get()` hoặc `CompletableFuture.join()` để đợi.
- Chờ `CountDownLatch`, semaphore hoặc condition mà thread khác có thể không giải phóng.
- Lấy lock có thời gian chờ không xác định.
- Chạy shutdown hook, callback nghiệp vụ hoặc chuỗi cleanup dài.
- Ghi log đồng bộ tới đĩa, console hoặc remote collector nếu logger có thể block.

Cleanup action nên làm phần tối thiểu cần thiết để nhả tài nguyên và trả về. Nếu tài nguyên cần một quy trình đóng có thể block, hãy để caller thực hiện qua `close()` trên thread do ứng dụng quản lý; Cleaner chỉ phù hợp làm fallback best-effort cho phần cleanup ngắn, an toàn.

## 3. Phân biệt cleanup nhanh và công việc shutdown

Không phải mọi thao tác mang tên `close()` đều có chi phí như nhau. Ví dụ:

| Công việc | Nơi phù hợp | Lý do |
| --- | --- | --- |
| Đánh dấu state đã đóng bằng atomic flag | Cleaning action | Nhanh, không chờ |
| Nhả một handle native bằng API có thời gian thực thi ngắn | Cleaning action nếu hợp đồng API cho phép | Có thể hoàn tất nhanh |
| Flush buffer ra network | Explicit `close()` | Có thể block và phát sinh lỗi I/O |
| Gửi thông báo tới service khác | Thread/executor do ứng dụng quản lý | Phụ thuộc hệ thống bên ngoài |
| Chờ worker kết thúc | Explicit shutdown path | Cần timeout, cancellation và quản lý vòng đời |

Nếu cleanup bắt buộc phải hoàn tất trước khi ứng dụng tiếp tục, không thể giao trách nhiệm đó cho GC. Hãy đóng tường minh và chờ kết quả trong luồng điều khiển của ứng dụng.

### 3.1. Offload sang worker có điều kiện

Trong một số hệ thống, cleaning action có thể chỉ enqueue một yêu cầu cleanup vào queue để worker riêng xử lý. Cách này chỉ phù hợp khi:

- Enqueue thực sự không block.
- Queue có chính sách đầy rõ ràng.
- Worker có vòng đời được quản lý và còn hoạt động khi cần xử lý.
- Lỗi của worker được ghi nhận và giám sát.
- Ứng dụng không giả định enqueue đồng nghĩa tài nguyên đã được giải phóng.

Không enqueue rồi bỏ quên future. Cleaner daemon có thể kết thúc khi JVM thoát; một công việc đã enqueue không có bảo đảm sẽ hoàn tất. Nếu việc giải phóng là bắt buộc, explicit close phải chờ worker và trả lỗi cho caller.

## 4. Exception từ cleaning action bị Cleaner bỏ qua

`Cleaner` quy định các exception thoát ra từ cleaning action bị bỏ qua. Cleaner và các action khác không bị ảnh hưởng bởi exception của một action. Vì vậy đoạn mã sau làm mất thông tin lỗi:

~~~java
private static final class State implements Runnable {
    @Override
    public void run() {
        releaseNativeResource(); // Có thể ném exception
    }
}
~~~

Nếu `releaseNativeResource()` ném lỗi, caller ban đầu có thể đã không còn tồn tại; Cleaner không chuyển exception này về một thread nghiệp vụ. Không thể dựa vào `try/catch` bên ngoài `cleaner.register()` để bắt lỗi xảy ra về sau.

Không dựa vào `Thread.UncaughtExceptionHandler` để quan sát exception từ action. Cleaner xử lý exception theo hợp đồng của nó; action phải tự bắt và chuyển thông tin lỗi tới kênh quan sát.

### 4.1. Bắt và ghi nhận lỗi bên trong action

Cleaning action nên bắt các lỗi cleanup có thể dự đoán, lưu chúng vào một kênh thread-safe và kết thúc nhanh:

~~~java
@Override
public void run() {
    try {
        releaseNativeResource();
    } catch (IOException failure) {
        FAILURE_QUEUE.offer(describe(failure));
    }
}
~~~

Ví dụ dùng `ConcurrentLinkedQueue` vì thao tác enqueue không chờ một consumer giải phóng slot. Trong hệ thống production, cần drain queue và kiểm soát bộ nhớ; queue không giới hạn mà không có consumer sẽ tăng mãi. Có thể dùng metrics, error reporter không block hoặc một queue giới hạn kèm counter/alert khi queue đầy.

Không gọi logger đồng bộ có thể block bên trong action. Không chỉ tăng một counter chung nếu cần biết resource nào thất bại; lưu mã định danh và loại lỗi đủ để truy vết, đồng thời tránh giữ lại object owner hoặc dữ liệu nhạy cảm.

### 4.2. Không nuốt lỗi fatal

Không dùng `catch (Throwable ignored) {}`. Nếu phải bắt `Throwable` tại ranh giới của Cleaner để ghi nhận mọi lỗi, hãy ghi nhận trước và giữ nguyên chính sách với `Error` nghiêm trọng, ví dụ rethrow sau khi ghi nhận. Không biến lỗi bộ nhớ hoặc lỗi VM thành trạng thái cleanup thành công.

Với explicit close, để lỗi được truyền ra caller. Với fallback Cleaner, ghi nhận lỗi vào error sink vì không có caller đồng bộ để nhận exception.

## 5. Explicit close phải báo lỗi cho caller

Đường đóng tường minh có một lợi thế mà Cleaner fallback không có: caller đang chờ kết quả và có thể xử lý exception.

~~~java
@Override
public void close() throws IOException {
    try {
        state.releaseExplicitly();
    } finally {
        cleanable.clean();
    }
}
~~~

Trong mẫu này, `state.releaseExplicitly()` thực hiện cleanup và có thể ném `IOException`. `finally` gọi `cleanable.clean()` để hủy đăng ký Cleaner. State phải có guard nguyên tử để action được gọi bởi `cleanable.clean()` không giải phóng lần thứ hai.

Đừng chỉ gọi `cleanable.clean()` rồi mong exception của action truyền ra khỏi `close()`. Hợp đồng Cleaner bỏ qua exception của cleaning action; vì vậy đường explicit close cần gọi logic release có khả năng trả lỗi trực tiếp.

## 6. Giữ exception chính và lỗi cleanup

Try-with-resources có quy tắc exception quan trọng: nếu phần thân ném exception và `close()` cũng ném exception, exception từ phần thân được giữ làm primary exception; exception từ `close()` được gắn vào danh sách suppressed.

~~~java
try (Resource resource = openResource()) {
    performWork(); // Ném WorkException
} catch (WorkException primary) {
    for (Throwable cleanupFailure : primary.getSuppressed()) {
        reportCleanupFailure(cleanupFailure);
    }
    throw primary;
}
~~~

Không bỏ qua `getSuppressed()` nếu lỗi cleanup có ý nghĩa vận hành. Khi cần ghi log, ghi primary exception cùng suppressed exceptions để giữ đầy đủ nguyên nhân.

Không tự bắt exception trong `close()` rồi chỉ log một dòng chung hoặc thay thế exception chính bằng exception cleanup. Hãy để try-with-resources duy trì quan hệ primary/suppressed và để tầng gọi quyết định cách xử lý.

## 7. Tránh cleanup hai lần khi close và Cleaner chạy cạnh tranh

Explicit close có thể xảy ra gần thời điểm Cleaner phát hiện object phantom reachable. Cần bảo đảm chỉ một bên bắt đầu giải phóng tài nguyên. `AtomicBoolean.compareAndSet()` là guard đơn giản; nếu explicit close cần nhận kết quả từ cleanup đã được Cleaner bắt đầu, có thể lưu kết quả hoàn tất trong `CompletableFuture`.

Trong ví dụ:

- `started` chỉ cho phép một thread bắt đầu release.
- `result` lưu kết quả cleanup để explicit close có thể chờ nếu Cleaner đã bắt đầu.
- `run()` không gọi `join()`; nếu một thread khác đã bắt đầu, action trả về ngay.
- `closeExplicitly()` có thể chờ kết quả trên caller thread và ném lại lỗi.
- `cleanable.clean()` trong `finally` hủy đăng ký; action không thực hiện release lần thứ hai.

Điểm quan trọng là không để Cleaner thread chờ một future do một action khác tạo ra. Việc chờ kết quả chỉ xảy ra trong đường close do caller chủ động gọi.

## 8. Ví dụ hoàn chỉnh chạy trên Java 17+

Ví dụ dưới đây kiểm tra bốn tình huống:

1. Explicit close thành công.
2. Explicit close thất bại và ném `IOException` về caller.
3. Body exception vẫn là primary, cleanup exception được lưu trong suppressed.
4. Cleaning action fallback bắt lỗi và ghi vào queue thay vì để exception bị Cleaner bỏ qua.

Để tránh phụ thuộc thời điểm GC, ví dụ gọi `cleanable.clean()` trực tiếp cho trường hợp fallback. Lời gọi này kích hoạt cùng `Runnable` đã đăng ký; nó kiểm tra logic ghi nhận lỗi nhưng không giả định khi nào object sẽ phantom reachable.

**Tệp:** `CleanerFailureHandlingDemo.java`

~~~java
import java.io.IOException;
import java.lang.ref.Cleaner;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;

public final class CleanerFailureHandlingDemo implements AutoCloseable {
    private static final Cleaner CLEANER = Cleaner.create();
    private static final ConcurrentLinkedQueue<String> CLEANUP_EVENTS =
        new ConcurrentLinkedQueue<>();
    private static final ConcurrentLinkedQueue<String> CLEANUP_FAILURES =
        new ConcurrentLinkedQueue<>();

    private static final class State implements Runnable {
        private final String id;
        private final boolean fail;
        private final AtomicBoolean started = new AtomicBoolean();
        private final CompletableFuture<Throwable> result = new CompletableFuture<>();

        State(String id, boolean fail) {
            this.id = id;
            this.fail = fail;
        }

        private Throwable releaseResource() {
            try {
                if (fail) {
                    throw new IOException("simulated cleanup failure: " + id);
                }
                CLEANUP_EVENTS.add("released " + id);
                return null;
            } catch (Throwable failure) {
                return failure;
            }
        }

        void closeExplicitly() throws IOException {
            if (started.compareAndSet(false, true)) {
                result.complete(releaseResource());
            }

            Throwable failure = result.join();
            if (failure instanceof IOException) {
                throw (IOException) failure;
            }
            if (failure instanceof RuntimeException) {
                throw (RuntimeException) failure;
            }
            if (failure instanceof Error) {
                throw (Error) failure;
            }
            if (failure != null) {
                throw new IOException("cleanup failed", failure);
            }
        }

        @Override
        public void run() {
            if (!started.compareAndSet(false, true)) {
                return;
            }
            Throwable failure = releaseResource();
            result.complete(failure);
            if (failure != null) {
                CLEANUP_FAILURES.add(id + ": " + failure.getClass().getSimpleName()
                    + ": " + failure.getMessage());
                if (failure instanceof Error) {
                    throw (Error) failure;
                }
            }
        }
    }

    private final State state;
    private final Cleaner.Cleanable cleanable;

    CleanerFailureHandlingDemo(String id, boolean fail) {
        state = new State(id, fail);
        cleanable = CLEANER.register(this, state);
    }

    void use() {
        System.out.println("using " + state.id);
    }

    @Override
    public void close() throws IOException {
        try {
            state.closeExplicitly();
        } finally {
            cleanable.clean();
        }
    }

    public static void main(String[] args) throws Exception {
        try (CleanerFailureHandlingDemo resource =
                new CleanerFailureHandlingDemo("normal", false)) {
            resource.use();
        }
        System.out.println(CLEANUP_EVENTS.poll());

        try (CleanerFailureHandlingDemo resource =
                new CleanerFailureHandlingDemo("explicit", true)) {
            resource.use();
        } catch (IOException failure) {
            System.out.println("explicit close reported: " + failure.getMessage());
        }

        try (CleanerFailureHandlingDemo resource =
                new CleanerFailureHandlingDemo("suppressed", true)) {
            throw new IllegalStateException("body failed");
        } catch (IllegalStateException primary) {
            System.out.println("primary: " + primary.getMessage());
            for (Throwable suppressed : primary.getSuppressed()) {
                System.out.println("suppressed: " + suppressed.getMessage());
            }
        }

        CleanerFailureHandlingDemo fallback =
            new CleanerFailureHandlingDemo("fallback", true);
        fallback.cleanable.clean();
        System.out.println("cleaner action failure recorded: "
            + CLEANUP_FAILURES.poll());
    }
}
~~~

Biên dịch và chạy:

~~~text
javac --release 17 CleanerFailureHandlingDemo.java
java CleanerFailureHandlingDemo
~~~

Output:

~~~text
using normal
released normal
using explicit
explicit close reported: simulated cleanup failure: explicit
primary: body failed
suppressed: simulated cleanup failure: suppressed
cleaner action failure recorded: fallback: IOException: simulated cleanup failure: fallback
~~~

### 8.1. Giải thích thiết kế

`State` là static nested class và không giữ tham chiếu tới `CleanerFailureHandlingDemo`. Cleaner chỉ giữ State và `Runnable`, do đó owner có thể trở nên phantom reachable.

`releaseResource()` mô phỏng một thao tác ngắn. Trong ứng dụng thật, không đưa network, sleep, wait hoặc logging đồng bộ vào đây. Thành công và lỗi được lưu qua các queue để demo in trên main thread.

`run()` chỉ bắt đầu nếu `started.compareAndSet(false, true)` thành công. Nếu release thất bại, action ghi nhận định danh và lỗi vào `CLEANUP_FAILURES`. Exception không thoát ra khỏi action; với `Error`, ví dụ ghi nhận rồi rethrow để không che giấu lỗi fatal.

`closeExplicitly()` dùng cùng guard. Nếu close là bên bắt đầu, nó thực hiện release và lưu kết quả; nếu Cleaner đã bắt đầu, close chờ kết quả trên caller thread. Nó ném lại `IOException`, `RuntimeException` hoặc `Error` theo loại. `close()` gọi `cleanable.clean()` trong `finally` để unregister đăng ký dù release thành công hay thất bại.

Queue trong ví dụ là queue không giới hạn và được drain ngay để giữ output dễ kiểm chứng. Trong production, phải đặt chính sách dung lượng, drain và cảnh báo overflow; không để error queue tăng không giới hạn.

## 9. Các giới hạn cần nhớ

- Cleaner không bảo đảm action chạy ngay khi object không còn được dùng.
- Không có bảo đảm action hoàn tất trước `System.exit()`.
- Cleaner mặc định dùng daemon thread; không dùng nó làm cơ chế shutdown bắt buộc.
- Action bị block có thể trì hoãn action khác cùng Cleaner.
- Exception thoát khỏi action bị Cleaner bỏ qua.
- Action phải thread-safe và không giữ tham chiếu tới referent.
- Explicit close có thể báo lỗi; fallback action cần error sink riêng.
- `cleanable.clean()` chỉ thực hiện action tối đa một lần cho mỗi đăng ký.

## 10. Lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Gọi network hoặc chờ I/O trong action | Cleaner thread bị block; action khác bị trì hoãn | Đưa công việc block vào explicit close hoặc worker có lifecycle rõ ràng |
| Dùng `Future.get()`/`join()` trong action | Cleaner thread chờ vô thời hạn | Không chờ trong action; enqueue công việc nhanh nếu có worker được quản lý |
| Ghi log đồng bộ từ action | Logger có thể block trên disk hoặc remote sink | Ghi vào queue/metrics không block rồi drain ở thread khác |
| Để exception thoát khỏi `run()` | Cleaner bỏ qua exception; lỗi có thể mất dấu | Catch lỗi cleanup, ghi nhận, rồi áp dụng chính sách với Error |
| Chỉ dùng `cleanable.clean()` trong `close()` | Lỗi action không phải kênh trả exception đáng tin | Gọi state cleanup trực tiếp để explicit close truyền lỗi về caller, sau đó unregister |
| Bắt rồi bỏ `IOException` trong close | Caller tưởng resource đã đóng thành công | Ném lại lỗi hoặc wrap với cause phù hợp |
| Bỏ qua suppressed exceptions | Mất thông tin lỗi cleanup khi body cũng thất bại | Kiểm tra `Throwable.getSuppressed()` |
| Không đồng bộ close và fallback | Có thể release hai lần hoặc close không thấy kết quả lỗi | Dùng atomic guard và lưu kết quả cleanup |
| Dùng queue lỗi không drain | Tăng bộ nhớ theo thời gian | Dùng sink có dung lượng/chính sách overflow và monitoring |
| Cho rằng Cleaner action chạy trước khi JVM thoát | Tài nguyên có thể không được giải phóng | Explicit close và quản lý shutdown tường minh |

## 11. Quy tắc thực hành

1. Giữ cleaning action ngắn, không block và không phụ thuộc hệ thống bên ngoài.
2. Không chờ future, latch, lock hoặc network trong Cleaner thread.
3. Nếu cleanup cần thời gian hoặc có thể thất bại, cung cấp `AutoCloseable.close()` cho caller.
4. Để explicit close thực hiện release trực tiếp và truyền exception về caller.
5. Dùng `cleanable.clean()` trong `finally` để unregister sau explicit close.
6. Dùng state thread-safe để tránh release hai lần khi close và Cleaner cạnh tranh.
7. Bắt và ghi nhận lỗi trong fallback action vì Cleaner bỏ qua exception thoát ra.
8. Dùng error sink không block; drain và giám sát queue.
9. Kiểm tra suppressed exceptions khi cả body và close cùng thất bại.
10. Không dựa vào UncaughtExceptionHandler hoặc System.gc() để bảo đảm báo lỗi/cleanup.
11. Không catch rồi bỏ qua `Throwable`; giữ nguyên chính sách với Error nghiêm trọng.
12. Kiểm thử explicit close và error reporting độc lập với thời điểm GC.

## 12. Tự kiểm tra

- Cleaner chạy action bằng loại thread nào? Thread gắn với Cleaner; `create()` mặc định tạo daemon thread.
- Một action bị block ảnh hưởng gì? Có thể trì hoãn các action khác đăng ký cùng Cleaner.
- Cleaner có truyền exception từ `Runnable.run()` về caller không? Không; exception thoát ra từ action bị bỏ qua.
- Có thể dùng UncaughtExceptionHandler làm error sink không? Không nên; Cleaner xử lý exception theo hợp đồng riêng.
- Cần ghi nhận lỗi fallback ở đâu? Ngay trong action, qua queue/metrics/error sink thread-safe không block.
- Vì sao close() nên gọi release trực tiếp? Để caller nhận được exception cleanup.
- Vì sao vẫn gọi cleanable.clean() trong finally? Để unregister đăng ký và ngăn fallback chạy lại.
- Nếu body và close cùng ném lỗi, lỗi nào là primary? Lỗi từ body; lỗi close nằm trong suppressed.
- Làm sao tránh release hai lần? Atomic guard và trạng thái cleanup dùng chung.
- Có nên chờ network hoặc Future trong Cleaner action không? Không.
- Cleaner có bảo đảm action chạy trước System.exit không? Không.

## Tài liệu API Java SE 17

- [Cleaner — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.html)
- [Cleaner.Cleanable — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Cleaner.Cleanable.html)

Điểm cốt lõi: **Cleaner action phải ngắn và không block; exception thoát khỏi action bị Cleaner bỏ qua.** Ghi nhận lỗi ngay trong fallback action, còn explicit `close()` phải truyền lỗi về caller và giữ nguyên suppressed exceptions.