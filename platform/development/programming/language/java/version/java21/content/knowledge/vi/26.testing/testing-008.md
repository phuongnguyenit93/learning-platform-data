# Kiểm thử đồng thời mà không phụ thuộc sleep hoặc lịch chạy cụ thể

Kiểm thử concurrent code cần xác minh kết quả vẫn đúng khi nhiều thread cùng thực hiện công việc. Một test đáng tin cậy phải điều khiển sự phối hợp bằng primitive đồng bộ hóa và kiểm tra các invariant của chương trình; nó không nên giả định thread nào chạy trước, thread nào chạy sau hoặc một khoảng Thread.sleep đủ để một tác vụ hoàn tất.

Trong Java 21, có thể dùng CountDownLatch, CyclicBarrier, Phaser, BlockingQueue, Future và CompletableFuture để phối hợp test. Timeout có vai trò giới hạn thời gian chờ và báo lỗi khi hệ thống không tiến triển; timeout không phải cách tạo thứ tự thực thi.

## 1. Vì sao Thread.sleep làm test concurrent thiếu tin cậy?

Một test thường bắt đầu bằng cách chạy tác vụ nền rồi ngủ một khoảng thời gian trước khi kiểm tra:

~~~java
executor.submit(() -> service.process());

Thread.sleep(500);

assertTrue(service.isCompleted());
~~~

Cách này không xác nhận tác vụ đã bắt đầu hoặc hoàn tất. Nó chỉ làm thread kiểm thử tạm ngừng trong 500 ms.

Kết quả có thể khác nhau giữa máy local và CI:

- Trên máy nhanh, tác vụ hoàn tất trước khi test thức dậy.
- Trên CI đang tải cao, tác vụ vẫn chưa chạy hoặc chưa hoàn tất.
- Khi thay đổi số CPU, garbage collection hoặc tải hệ thống, lịch chạy thay đổi.
- Tăng thời gian sleep chỉ làm test chậm hơn; nó không tạo ra một bảo đảm đồng bộ hóa.

Thread.sleep không thiết lập quan hệ happens-before giữa các thread và không bảo đảm thread khác đã thực hiện một hành động cụ thể. Thread.yield cũng không phải primitive đồng bộ hóa và không bảo đảm thread nào sẽ được chạy tiếp.

Hãy chờ một tín hiệu có ý nghĩa như latch được mở, phần tử xuất hiện trong queue hoặc Future hoàn tất.

## 2. Tách điều kiện đồng bộ khỏi giới hạn thời gian

Một test concurrent thường cần hai cơ chế khác nhau:

- **Synchronization:** xác định khi nào một thread được phép tiếp tục, hoặc xác nhận một sự kiện đã xảy ra.
- **Timeout:** giới hạn thời gian chờ để test thất bại rõ ràng nếu sự kiện không xảy ra.

Ví dụ với CountDownLatch:

~~~java
CountDownLatch completed = new CountDownLatch(1);

Future<?> task = executor.submit(() -> {
    try {
        service.process();
    } finally {
        completed.countDown();
    }
});

assertTrue(
    completed.await(5, TimeUnit.SECONDS),
    "Tác vụ không hoàn tất trong thời hạn kiểm thử"
);

task.get(5, TimeUnit.SECONDS); // Truyền exception của worker về test.
~~~

Thread kiểm thử chờ đúng tín hiệu countDown. Năm giây chỉ là giới hạn để phát hiện deadlock hoặc tác vụ bị kẹt; test không phụ thuộc việc tác vụ phải hoàn thành trong một khoảng sleep cố định.

Nếu await trả về false, test phải thất bại. Không tiếp tục assertion như thể tác vụ đã hoàn thành.

## 3. Các primitive đồng bộ hữu ích trong test

| Primitive | Cách dùng trong test | Khi phù hợp |
|---|---|---|
| CountDownLatch | Chờ một hoặc nhiều sự kiện; mở cổng để nhiều worker bắt đầu | Chờ task sẵn sàng, chờ xử lý hoàn tất |
| CyclicBarrier | Đợi một nhóm thread cùng đến một điểm | Đồng bộ các actor tại cùng một pha |
| Phaser | Điều phối nhiều pha với số party có thể thay đổi | Test workflow nhiều bước hoặc nhóm task động |
| BlockingQueue | Worker gửi kết quả/sự kiện; test dùng poll(timeout) để nhận | Consumer, producer, message handler |
| Semaphore | Kiểm tra giới hạn số thao tác đồng thời | Connection limit, admission control |
| Future | Lấy kết quả và chờ task hoàn tất có timeout | Task submit qua ExecutorService |
| CompletableFuture | Phối hợp kết quả bất đồng bộ và chờ có giới hạn | API async hoặc pipeline nhiều bước |

Chọn primitive phản ánh đúng sự kiện cần kiểm tra. Không tạo một latch chỉ để thay một sleep nếu latch không gắn với trạng thái hoặc mốc thực tế trong luồng xử lý.

## 4. CountDownLatch: chờ task sẵn sàng rồi mới cho bắt đầu

Một start gate giúp nhiều worker cùng đợi trước khi test cho phép chúng thực hiện thao tác cạnh tranh.

~~~java
int workers = 4;

CountDownLatch ready = new CountDownLatch(workers);
CountDownLatch start = new CountDownLatch(1);
List<Future<?>> tasks = new ArrayList<>();

try {
    for (int i = 0; i < workers; i++) {
        tasks.add(executor.submit(() -> {
            ready.countDown();

            if (!start.await(5, TimeUnit.SECONDS)) {
                throw new TimeoutException("Không nhận được tín hiệu bắt đầu");
            }

            service.performConcurrentOperation();
        }));
    }

    assertTrue(ready.await(5, TimeUnit.SECONDS));
} finally {
    start.countDown();
}

for (Future<?> task : tasks) {
    task.get(5, TimeUnit.SECONDS);
}
~~~

Luồng kiểm thử chỉ mở start sau khi các worker đã báo sẵn sàng. Nhờ đó, các lời gọi được phát hành gần nhau và có cơ hội cạnh tranh trên cùng trạng thái.

Start gate không bảo đảm mọi worker chạy cùng một CPU cycle hoặc một thứ tự cụ thể. Scheduler vẫn quyết định thread nào được chạy trước. Đây là điều mong muốn: test xác minh invariant qua các interleaving hợp lệ thay vì dựa vào một lịch chạy được giả định.

Gate luôn được mở trong finally để worker không bị kẹt nếu assertion trước đó thất bại. Future.get ở cuối cũng giúp exception từ worker được chuyển về thread kiểm thử.

## 5. Ví dụ Java 21: kiểm tra không bán vượt số lượng tồn kho

Giả sử một mặt hàng chỉ còn 10 đơn vị nhưng có 100 request đồng thời muốn đặt hàng. Invariant cần giữ là:

- Số lần đặt thành công không vượt quá số lượng ban đầu.
- Số lượng tồn kho không âm.
- Nếu tất cả request đều được xử lý, tổng số lần đặt thành công bằng đúng số lượng ban đầu.

Có thể triển khai thao tác giữ hàng bằng AtomicInteger và compare-and-set:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class Inventory {
    private final AtomicInteger available;

    Inventory(int initialStock) {
        if (initialStock < 0) {
            throw new IllegalArgumentException("initialStock must be >= 0");
        }
        this.available = new AtomicInteger(initialStock);
    }

    boolean tryReserve() {
        while (true) {
            int current = available.get();

            if (current == 0) {
                return false;
            }

            if (available.compareAndSet(current, current - 1)) {
                return true;
            }
        }
    }

    int available() {
        return available.get();
    }
}
~~~

Test dùng virtual thread per task của Java 21:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class InventoryConcurrencyTest {

    @Test
    @Timeout(value = 10, unit = TimeUnit.SECONDS)
    void doesNotOversell() throws Exception {
        int initialStock = 10;
        int callers = 100;

        Inventory inventory = new Inventory(initialStock);
        CountDownLatch ready = new CountDownLatch(callers);
        CountDownLatch start = new CountDownLatch(1);

        try (ExecutorService executor =
                 Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<Boolean>> attempts = new ArrayList<>();

            try {
                for (int i = 0; i < callers; i++) {
                    attempts.add(executor.submit(() -> {
                        ready.countDown();

                        if (!start.await(5, TimeUnit.SECONDS)) {
                            throw new TimeoutException(
                                "Không nhận được start signal"
                            );
                        }

                        return inventory.tryReserve();
                    }));
                }

                assertTrue(
                    ready.await(5, TimeUnit.SECONDS),
                    "Không phải tất cả worker đều sẵn sàng"
                );
            } finally {
                // Luôn giải phóng worker, kể cả khi assertion thất bại.
                start.countDown();
            }

            int successfulReservations = 0;

            for (Future<Boolean> attempt : attempts) {
                if (attempt.get(5, TimeUnit.SECONDS)) {
                    successfulReservations++;
                }
            }

            assertEquals(initialStock, successfulReservations);
            assertEquals(0, inventory.available());
        }
    }
}
~~~

Test không yêu cầu request nào phải thắng hoặc thread nào phải chạy đầu tiên. Nó chỉ kiểm tra kết quả cuối cùng theo invariant nghiệp vụ.

Executors.newVirtualThreadPerTaskExecutor phù hợp để mô phỏng nhiều task độc lập trên Java 21. try-with-resources đóng executor sau khi các Future đã hoàn tất. @Timeout của JUnit là watchdog ở cấp test; các latch và Future vẫn có timeout riêng để xác định điểm chờ nào bị kẹt.

Start gate làm các request cạnh tranh gần nhau hơn, nhưng không chứng minh mọi interleaving có thể xảy ra. Với thuật toán lock-free, cấu trúc dữ liệu concurrent hoặc lỗi phụ thuộc một interleaving rất hẹp, cần bổ sung stress test hoặc công cụ chuyên biệt.

## 6. Dùng Future.get thay vì giả định task đã hoàn tất

Khi submit một task qua ExecutorService, giữ lại Future để chờ kết quả:

~~~java
Future<Integer> result = executor.submit(() -> {
    return service.calculate();
});

int value = result.get(5, TimeUnit.SECONDS);

assertEquals(42, value);
~~~

Future.get(timeout, unit) có ba kết quả quan trọng:

- Trả về giá trị nếu task hoàn tất trong thời hạn.
- Ném TimeoutException nếu task chưa hoàn tất.
- Ném ExecutionException nếu task kết thúc bằng exception.

Không gọi get() không timeout trong test có nguy cơ deadlock. Khi cần biết nguyên nhân task thất bại, hãy giữ nguyên ExecutionException để JUnit hiển thị cause.

Việc một thread submit task xảy ra trước khi task bắt đầu; các hành động trong task xảy ra trước khi thread khác lấy kết quả thành công qua Future.get(). Quan hệ happens-before này giúp test đọc kết quả sau khi task hoàn tất một cách an toàn.


## 7. Dùng BlockingQueue để chờ sự kiện

Với producer/consumer hoặc message handler, queue thường biểu diễn đúng điều kiện cần kiểm tra hơn là cờ boolean kèm sleep.

~~~java
BlockingQueue<String> events = new LinkedBlockingQueue<>();

executor.submit(() -> {
    String result = service.processMessage("order-42");
    events.put(result);
    return null;
});

String result = events.poll(5, TimeUnit.SECONDS);

assertEquals("processed:order-42", result);
~~~

poll(timeout, unit) trả về null nếu hết thời hạn mà queue vẫn rỗng. Hãy assert kết quả không null hoặc so sánh trực tiếp như ví dụ; đừng tiếp tục kiểm tra nội dung nếu chưa nhận được sự kiện.

Cách này hữu ích khi test:

- Message consumer xử lý xong một message.
- Background worker phát ra event.
- Một callback gửi kết quả về test.
- Pipeline bất đồng bộ tạo output sau nhiều bước.

Nếu event có thể đến nhiều lần hoặc không đúng thứ tự, hãy kiểm tra correlation ID và nội dung thay vì chỉ đợi phần tử bất kỳ.

## 8. CyclicBarrier và Phaser cho nhiều pha đồng bộ

CyclicBarrier phù hợp khi một số lượng party cố định phải cùng đến một điểm trước khi tiếp tục:

~~~java
CyclicBarrier barrier = new CyclicBarrier(3);

Callable<String> task = () -> {
    prepareLocalState();
    barrier.await(5, TimeUnit.SECONDS);
    return executeNextPhase();
};
~~~

Mỗi task chuẩn bị trạng thái riêng rồi chờ các party còn lại. Khi đủ party đến, tất cả được giải phóng để thực hiện pha tiếp theo.

Nếu một party timeout hoặc bị interrupt, barrier có thể chuyển sang trạng thái broken và các party còn lại nhận BrokenBarrierException. Test cần coi đó là lỗi phối hợp, không cố tiếp tục dùng barrier đã hỏng như thể nó vẫn bình thường.

Phaser linh hoạt hơn khi số task tham gia thay đổi hoặc cần nhiều pha:

~~~java
Phaser phaser = new Phaser(1); // Test thread là party đầu tiên.

try (ExecutorService executor =
         Executors.newVirtualThreadPerTaskExecutor()) {
    phaser.register(); // Đăng ký party cho worker.

    Future<Integer> worker = executor.submit(() -> {
        return phaser.arriveAndAwaitAdvance();
    });

    int phase = phaser.arrive();
    phaser.awaitAdvanceInterruptibly(
        phase,
        5,
        TimeUnit.SECONDS
    );

    worker.get(5, TimeUnit.SECONDS);
}
~~~

Worker và test thread đến phase theo thứ tự bất kỳ; phase chỉ tiến lên khi cả hai đã arrive. Khi viết test thực tế, cần xác định rõ party nào đăng ký, party nào deregister và ai chịu trách nhiệm kết thúc phase. Nếu số party không khớp, test có thể chờ mãi; hãy dùng các biến thể có timeout và dọn trạng thái trong finally.

## 9. Kiểm tra giới hạn concurrency bằng Semaphore

Nếu service phải giới hạn tối đa N thao tác đồng thời, có thể kiểm tra invariant bằng bộ đếm active và Semaphore:

~~~java
Semaphore permits = new Semaphore(3);
AtomicInteger active = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

Callable<Void> task = () -> {
    permits.acquire();

    try {
        int now = active.incrementAndGet();
        maxObserved.accumulateAndGet(now, Math::max);

        try {
            service.performBoundedOperation();
        } finally {
            active.decrementAndGet();
        }
    } finally {
        permits.release();
    }

    return null;
};
~~~

Sau khi tất cả Future hoàn tất, kiểm tra:

~~~java
assertTrue(maxObserved.get() <= 3);
assertEquals(0, active.get());
~~~

Trong test hoàn chỉnh, cần dùng latch hoặc barrier để nhiều task cùng cạnh tranh permit và dùng Future có timeout để chờ tất cả kết thúc.

Đặt release() trong finally để một exception không làm mất permit. Nếu quên release, các task sau có thể chờ mãi và test chỉ kết thúc nhờ timeout.

## 10. Kiểm tra happens-before và visibility

Một lỗi concurrent phổ biến là thread ghi dữ liệu nhưng thread khác đọc mà không có quan hệ đồng bộ phù hợp.

Các primitive trong java.util.concurrent cung cấp memory consistency guarantees. Ví dụ, hành động trước countDown() xảy ra-before hành động sau một await() thành công trên cùng latch.

~~~java
final class SharedState {
    int value;
}

SharedState state = new SharedState();
CountDownLatch published = new CountDownLatch(1);

Future<?> writer = executor.submit(() -> {
    state.value = 42;
    published.countDown();
});

assertTrue(published.await(5, TimeUnit.SECONDS));
assertEquals(42, state.value);

writer.get(5, TimeUnit.SECONDS);
~~~

Ở đây, test đọc value sau khi latch được mở. Quan hệ happens-before bảo đảm write được công bố tới thread kiểm thử. Ví dụ này minh họa visibility qua synchronization; trong ứng dụng thật, hãy dùng field volatile, lock, atomic hoặc concurrent collection theo đúng invariant và quyền sở hữu dữ liệu.

Không dùng sleep hoặc yield để "chờ visibility". Chúng không tạo ra memory barrier theo hợp đồng của Java Memory Model.

## 11. Kiểm tra nhiều kết quả hợp lệ thay vì ép một thứ tự

Khi hai task độc lập có thể chạy theo nhiều thứ tự, test nên kiểm tra các kết quả được phép theo đặc tả.

Ví dụ, nếu hai worker ghi hai event độc lập vào concurrent collection, test có thể xác minh:

- Cả hai event đều xuất hiện.
- Mỗi event chỉ xuất hiện một lần.
- Không có trạng thái trung gian sai.
- Nếu đặc tả không quy định thứ tự, không assert thứ tự tuyệt đối.

Chỉ assert thứ tự khi có một cơ chế hoặc hợp đồng thực sự bảo đảm thứ tự đó, chẳng hạn cùng một single-thread executor, sequence number được cấp nguyên tử hoặc một barrier được đặt rõ ràng.

Tránh assertion như "thread A phải chạy trước thread B" chỉ vì test local đã quan sát được thứ tự đó một lần. Scheduler không cam kết một thứ tự cố định cho các thread độc lập.

## 12. Tạo interleaving cụ thể khi cần bắt race condition

Start gate giúp các task cạnh tranh cùng lúc, nhưng không buộc chúng dừng ở một instruction cụ thể. Khi cần tái hiện một race condition hẹp, hãy tạo điểm đồng bộ tại ranh giới nghiệp vụ hoặc dùng test seam có thể kiểm soát.

Ví dụ, với thao tác read-modify-write:

1. Actor A đọc giá trị hiện tại.
2. Actor B đọc cùng giá trị đó.
3. Test chờ tín hiệu xác nhận cả hai đã đọc.
4. Test mở gate cho cả hai tiếp tục ghi.
5. Test kiểm tra invariant sau khi cả hai hoàn tất.

Có thể biểu diễn bước 3–4 bằng hai CountDownLatch: một latch đếm số actor đã tới điểm sau khi đọc, một latch cho phép tiếp tục. Hook nên nằm trong collaborator hoặc seam dành cho test, không nên thêm Thread.sleep vào production code.

Cách này giúp kiểm soát interleaving cụ thể và làm lỗi có thể tái hiện. Tuy nhiên, test seam phải phản ánh đúng ranh giới của thao tác thực tế; nếu hook thay đổi ngữ nghĩa hoặc khóa ngoài ý muốn, test có thể không còn mô tả race trong production.

## 13. JUnit timeout là watchdog, không phải công cụ đồng bộ

JUnit Jupiter cung cấp @Timeout để giới hạn thời gian chạy của test hoặc lifecycle method:

~~~java
@Test
@Timeout(value = 5, unit = TimeUnit.SECONDS)
void asynchronousOperationCompletes() throws Exception {
    // Dùng latch/Future/queue để chờ sự kiện cụ thể.
}
~~~

Dùng timeout ở hai cấp:

- Timeout cục bộ cho await, Future.get, poll hoặc barrier để xác định điểm chờ bị kẹt.
- @Timeout ở cấp test để bảo vệ suite khỏi một test deadlock hoặc không kết thúc.

Đặt timeout đủ rộng để CI chậm không tạo false failure. Giá trị cần dựa trên thời gian thực tế của test và môi trường chạy; không dùng timeout để suy ra thứ tự thread.

Timeout cũng không tự dọn mọi worker. Khi test thất bại, hãy mở các gate trong finally, cancel Future nếu phù hợp, gọi shutdownNow() hoặc đóng executor và chờ termination có giới hạn. Task cần phản hồi interruption; không được nuốt InterruptedException rồi tiếp tục chạy vô hạn.

## 14. Dọn executor và xử lý interruption

Test tạo thread phải có trách nhiệm kết thúc chúng, kể cả khi assertion thất bại.

Với Java 21, ExecutorService hỗ trợ AutoCloseable, vì vậy có thể dùng try-with-resources. Khi rời khỏi block, close() khởi động orderly shutdown và chờ task hoàn tất. Hãy bảo đảm các task có đường thoát và không bị kẹt trên latch chưa mở.

Nếu cần chủ động hủy task, có thể dùng:

~~~java
future.cancel(true);
executor.shutdownNow();
boolean terminated =
    executor.awaitTermination(5, TimeUnit.SECONDS);
~~~

cancel(true) và shutdownNow() yêu cầu interrupt; chúng không thể buộc một task bỏ qua interruption hoặc đang mắc trong native call phải kết thúc ngay lập tức. Task nên truyền tiếp InterruptedException hoặc khôi phục interrupt status nếu không thể truyền tiếp.

Không để thread test kết thúc trong khi worker vẫn sửa shared state. Điều đó khiến test sau bị ảnh hưởng và tạo lỗi không ổn định.

## 15. Khi nào dùng jcstress?

JUnit phù hợp cho test nghiệp vụ và integration test có thể phối hợp rõ ràng bằng latch, barrier, queue hoặc Future. Nhưng một số lỗi phụ thuộc Java Memory Model, CPU reordering hoặc interleaving rất hiếm, khó tái hiện bằng một lần chạy unit test.

OpenJDK jcstress là harness chuyên biệt để nghiên cứu tính đúng đắn của concurrency trong JVM, class library và phần cứng. Một jcstress test định nghĩa state, các actor chạy đồng thời, kết quả quan sát được và những outcome được phép hoặc bị cấm.

Nên cân nhắc jcstress khi phát triển:

- Lock-free algorithm hoặc cấu trúc dữ liệu concurrent.
- Mã dùng volatile, VarHandle hoặc compare-and-set với invariant tinh vi.
- Thư viện nền tảng có hợp đồng memory-ordering quan trọng.
- Bug chỉ xuất hiện dưới một số interleaving hoặc kiến trúc CPU.

jcstress chạy nhiều lần và mang tính xác suất: không thấy outcome sai trong một lần chạy không chứng minh outcome đó không thể xảy ra. Nó bổ sung cho unit/integration test, không thay thế kiểm tra nghiệp vụ thông thường.

## 16. Checklist viết test concurrent ổn định

- [ ] Xác định invariant hoặc outcome được phép trước khi viết test.
- [ ] Dùng latch, barrier, phaser, queue hoặc Future để phối hợp.
- [ ] Dùng start gate để phát hành nhiều thao tác cạnh tranh gần nhau.
- [ ] Dùng timeout để test thất bại rõ ràng khi chờ không tiến triển.
- [ ] Không dùng Thread.sleep hoặc Thread.yield làm cơ chế đồng bộ.
- [ ] Không assert thứ tự chạy nếu hợp đồng không quy định thứ tự.
- [ ] Dùng test seam để điều khiển interleaving cụ thể khi thật sự cần.
- [ ] Chờ Future hoàn tất trước khi kiểm tra shared state.
- [ ] Kiểm tra visibility qua quan hệ happens-before đã được API bảo đảm.
- [ ] Mở gate và dọn executor trong mọi nhánh kết thúc.
- [ ] Đảm bảo task phản hồi interruption và không để worker chạy sót.
- [ ] Dùng jcstress cho các primitive/algorithm cần khảo sát sâu về Java Memory Model.

## Tài liệu tham khảo chính thức

- [Java SE 21 API — java.util.concurrent package summary and memory consistency](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/package-summary.html)
- [Java SE 21 API — CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 21 API — CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Java SE 21 API — Phaser](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Phaser.html)
- [Java SE 21 API — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [JUnit Jupiter — Timeout](https://docs.junit.org/5.13.0/api/org.junit.jupiter.api/org/junit/jupiter/api/Timeout.html)
- [OpenJDK jcstress — Java Concurrency Stress](https://github.com/openjdk/jcstress)

