# Test tính đúng đắn khi nhiều tác vụ cùng truy cập state — Java Concurrency

## 1. Vì sao kiểm thử đồng thời khó?

Trong Java, nhiều thread có thể truy cập cùng một **shared mutable state**. Khi các thao tác đọc và ghi đan xen theo lịch thực thi khác nhau, code tưởng đúng trên một thread có thể bị mất cập nhật, quan sát trạng thái dở dang hoặc chờ nhau mãi. Lỗi có thể biến mất khi bật debugger, thêm logging hoặc chạy lại test.

Một lần test pass chỉ cho thấy lịch thực thi đã gặp chưa phát hiện vấn đề; **không chứng minh** implementation luôn đúng với mọi interleaving. Test có giá trị phải diễn đạt chính xác hợp đồng, chủ động tạo cạnh tranh, thu đủ kết quả của mọi task và kiểm tra các thuộc tính không được phép vi phạm.

Bài này thuộc phạm vi **Java concurrency nói chung** (`java.lang` và `java.util.concurrent`, Java Memory Model, thread/executor, synchronization), không triển khai tính năng hoặc cấu hình riêng của Spring.

Sau bài, bạn sẽ biết:

- Xác định tính đúng đắn bằng **invariant**, precondition/postcondition, safety và liveness.
- Nhận biết lost update, check-then-act, visibility, ordering và trạng thái nhiều biến không nhất quán.
- Phối hợp thread bằng `CountDownLatch`/`CyclicBarrier`, dùng `Future.get()` để nhận lỗi và biết khi nào assert.
- Tạo ví dụ Java 17+ tái hiện chắc chắn lost update và so sánh với `AtomicInteger`.
- Viết test JUnit 5 cho nhiều worker cùng sửa một state và tránh các lỗi trong chính test harness.
- Dùng stress test, lịch sử thao tác và công cụ concurrency chuyên biệt để mở rộng phạm vi kiểm tra.

## 2. Định nghĩa tính đúng đắn trước khi tạo thread

### Safety — không xuất hiện kết quả trái hợp đồng

Ví dụ: nếu 8 worker cùng tăng một counter 2.000 lần, kết quả **sau khi cả 8 hoàn thành** phải là `16_000`. Nếu kết quả nhỏ hơn, một hoặc nhiều lần cập nhật có thể bị mất.

Với 1 vé còn lại và hai yêu cầu đặt vé đồng thời, hợp đồng có thể cho phép A hoặc B thắng; điều **không được phép** là cả hai cùng thành công hoặc số vé âm. Test phải chấp nhận mọi thứ tự hợp lệ thay vì áp đặt bên nào thắng.

Với nhiều biến, test cần bất biến chung: khi chuyển số lượng từ `available` sang `reserved`, tổng `available + reserved` phải giữ bằng số ban đầu. Chỉ assert một trường không đủ để chứng minh trạng thái tổng thể nhất quán.

### Liveness — tác vụ vẫn có thể tiến triển

Chương trình có thể không ghi dữ liệu sai nhưng gặp deadlock, livelock, starvation hoặc chờ tài nguyên mãi mãi. Test phải có deadline khi chờ worker, lưu thông tin chẩn đoán và dọn tài nguyên. Timeout **không tự chứng minh deadlock**: máy CI chậm, GC, tài nguyên hệ thống cạn hoặc I/O chậm cũng có thể gây timeout.

### Atomicity, visibility, ordering

- **Atomicity:** một thao tác nghiệp vụ phải có hiệu lực như một đơn vị khi hợp đồng yêu cầu. `counter++` gồm đọc–cộng–ghi; không atomic dưới nhiều writer.
- **Visibility:** một thread cần nhìn thấy cập nhật của thread khác tại thời điểm hợp đồng yêu cầu. Chỉ viết vào biến thường mà không có đồng bộ phù hợp có thể dẫn đến quan sát lỗi.
- **Ordering:** nếu “ghi dữ liệu xong rồi công bố cờ ready”, phải có quan hệ happens-before cho reader; `Thread.sleep()` không thiết lập quan hệ đó.

**Data race** là các truy cập xung đột tới cùng biến thông thường, có ít nhất một ghi, nhưng không được sắp xếp bằng happens-before. **Race condition** rộng hơn: kết quả sai phụ thuộc thứ tự thao tác, kể cả khi từng thao tác `get`/`put` là thread-safe nhưng chuỗi gồm nhiều thao tác không atomic.

## 3. Thiết kế oracle của test

**Oracle** là điều kiện rõ ràng xác định test pass/fail, độc lập với việc task được scheduler cho chạy trước. Ghi trạng thái khởi tạo, thao tác được phép, trạng thái cuối, invariant trong lúc chạy và thời hạn hoàn tất.

| Kịch bản | Oracle đúng đắn | Lưu ý |
| --- | --- | --- |
| N worker tăng shared counter | Sau khi tất cả xong, giá trị bằng `N × số lần tăng` | Không assert khi worker còn chạy |
| Hai yêu cầu lấy tài nguyên cuối | Tối đa một thành công; số lượng không âm | Không áp đặt task A phải thắng |
| Chuyển tiền/tồn kho giữa hai ô | Tổng nguồn + đích được bảo toàn | Snapshot phải nhất quán |
| Cache tạo một key | Không nhân bản side effect trái hợp đồng | `get` rồi `put` là thao tác ghép |
| Writer công bố cấu hình | Reader chỉ thấy cấu hình đã khởi tạo hợp lệ | Cần safe publication |
| Nhiều task giữ lock | Hoàn tất trong giới hạn thời gian đặt trước | Timeout cần thread dump để chẩn đoán |

Phân biệt **assert trạng thái cuối** với **assert trạng thái trong lúc thực thi**. Đọc hai `AtomicInteger` liên tiếp không tự tạo snapshot atomic của cặp. Nếu hợp đồng đòi mọi snapshot nhất quán, cần synchronized snapshot, immutable object được publish atomic hoặc cơ chế tương ứng.

## 4. Điều phối lịch thực thi bằng đồng bộ, không bằng sleep

Một mẫu kiểm thử contention có kiểm soát:

1. Tạo executor có số worker **đủ** cho số task cùng đứng ở cổng start.
2. Mỗi worker gọi `ready.countDown()` rồi `start.await()`.
3. Thread kiểm thử chờ `ready.await(timeout)` để xác nhận mọi worker đã sẵn sàng.
4. Mở cổng bằng `start.countDown()` cho các thao tác cùng được phép bắt đầu.
5. Chờ **tất cả** `Future.get(timeout)`. Nếu task ném exception, `get` ném `ExecutionException` và test phải fail.
6. Khi các worker đã hoàn tất, kiểm tra oracle; mở cổng và đóng executor trong `finally` kể cả đường lỗi.

`CountDownLatch` là cổng một lần. `CyclicBarrier` thuận tiện khi các worker phải gặp nhau ở nhiều vòng cùng số participant, nhưng có thể broken khi có timeout/interrupt. `Phaser` cho phép quản lý các pha và số participant linh hoạt hơn. Lựa chọn theo mục tiêu test, không dùng thêm cơ chế chỉ để tăng độ phức tạp.

**Bẫy deadlock trong test:** nếu tạo 8 task cùng chờ cổng và chỉ có executor 2 worker, hai task đầu chiếm worker đứng đợi, sáu task còn lại không được chạy để báo ready. Thread điều phối cũng chờ đủ ready nên không ai mở cổng. Dùng pool ít nhất 8 worker cho mẫu này, có timeout và cleanup, hoặc thiết kế cách phối hợp khác.

**Cùng mở cổng không có nghĩa chạy tại cùng một nano giây.** Mẫu này tăng contention và kiểm soát thời điểm được phép chạy; scheduling vẫn do JVM/OS quyết định. Muốn ép một lịch read–modify–write cụ thể, đặt điểm đồng bộ **giữa các bước** của thao tác trong môi trường test.

## 5. Ví dụ Java 17+: tái hiện lost update theo lịch xác định

Chương trình sau cố ý chia increment của counter thường thành “đọc trước, ghi sau”. Hai worker buộc phải **đọc xong trước khi worker nào ghi**, nên cả hai cùng đọc `0` và cùng ghi `1`. Sau đó so sánh với `AtomicInteger.incrementAndGet()`, vốn là phép tăng atomic.

Tạo tệp **`SharedStateCorrectnessDemo.java`** với toàn bộ mã sau:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedStateCorrectnessDemo {
    private static final class UnsafeCounter {
        int value;

        void incrementInTwoPhases(
                CountDownLatch bothRead,
                CountDownLatch allowWrite) throws InterruptedException {
            int previous = value;
            bothRead.countDown();
            if (!allowWrite.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out before write");
            }
            value = previous + 1;
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            int unsafe = runUnsafe(executor);
            if (unsafe != 1) {
                throw new AssertionError("Unexpected demo result");
            }
            System.out.println("unsafe: actual=1, required=2 (lost update)");

            int safe = runAtomic(executor);
            if (safe != 2) {
                throw new AssertionError("Atomic update was lost");
            }
            System.out.println("atomic: actual=2, required=2 (correct)");
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(3, TimeUnit.SECONDS);
        }
    }

    private static int runUnsafe(ExecutorService executor) throws Exception {
        UnsafeCounter counter = new UnsafeCounter();
        CountDownLatch bothRead = new CountDownLatch(2);
        CountDownLatch allowWrite = new CountDownLatch(1);

        Callable<Void> task = () -> {
            counter.incrementInTwoPhases(bothRead, allowWrite);
            return null;
        };
        Future<Void> first = executor.submit(task);
        Future<Void> second = executor.submit(task);

        try {
            check(bothRead.await(3, TimeUnit.SECONDS),
                    "Both workers must read before writing");
            allowWrite.countDown();
            first.get(3, TimeUnit.SECONDS);
            second.get(3, TimeUnit.SECONDS);
            return counter.value;
        } finally {
            allowWrite.countDown();
        }
    }

    private static int runAtomic(ExecutorService executor) throws Exception {
        AtomicInteger counter = new AtomicInteger();
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> task = () -> {
            ready.countDown();
            if (!start.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Start gate timeout");
            }
            counter.incrementAndGet();
            return null;
        };
        Future<Void> first = executor.submit(task);
        Future<Void> second = executor.submit(task);

        try {
            check(ready.await(3, TimeUnit.SECONDS),
                    "Both workers must reach the start gate");
            start.countDown();
            first.get(3, TimeUnit.SECONDS);
            second.get(3, TimeUnit.SECONDS);
            return counter.get();
        } finally {
            start.countDown();
        }
    }

    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên:

```bash
javac SharedStateCorrectnessDemo.java
java SharedStateCorrectnessDemo
```

Kết quả khi chương trình chạy thành công:

```text
unsafe: actual=1, required=2 (lost update)
atomic: actual=2, required=2 (correct)
```

**Giải thích chính xác kết quả:**

- Cả hai task dùng **cùng instance** `UnsafeCounter`. Mỗi task đọc `value` vào `previous` trước khi gọi `bothRead.countDown()`. Main chỉ cho ghi khi cả hai đã báo đọc, nên cả hai đã lưu `previous = 0`. Các phép gán sau đó đều là `value = 1`. Kết quả 1 là lỗi lost update.
- `runAtomic` cũng có hai task được mở cổng cùng đợt, nhưng `incrementAndGet()` cung cấp read–modify–write atomic. Sau cả hai future, kết quả là 2.
- Chương trình minh họa **cố ý kiểm tra rằng lỗi đã được tạo ra**; trong một regression test cho code thực, oracle phải là 2 và implementation trả 1 **phải fail**.
- `Future.get(timeout)` chờ hoàn tất và truyền lỗi task về main; không có đoạn code nào đoán worker đã xong chỉ vì một khoảng `sleep` đã trôi qua.
- Các `finally` mở latch để tránh để worker kẹt nếu main gặp lỗi. `shutdownNow()` yêu cầu interrupt best-effort, không bảo đảm mọi tác vụ tùy ý dừng ngay lập tức.

Mẫu này cố ý chèn điểm đồng bộ vào thuật toán lỗi để tạo phản ví dụ. Khi kiểm thử code nghiệp vụ thực, không nên sửa hành vi production chỉ để “chữa” race; dùng test hook hoặc một seam thích hợp khi cần quan sát lịch thực thi.

## 6. Ví dụ JUnit 5: kiểm tra không mất increment khi cạnh tranh

Đây là một **test class dùng JUnit Jupiter 5**, dành cho dự án đã khai báo JUnit Jupiter và cấu hình test runner. Nó minh họa mẫu test có thể tái sử dụng để thay đối tượng counter bằng implementation đang phát triển. Không chạy tệp này bằng `java` trực tiếp khi thiếu dependency/test runner.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ConcurrentCounterTest {
    @Test
    void allConcurrentIncrementsArePreserved() throws Exception {
        int workers = 8;
        int iterationsPerWorker = 2_000;
        AtomicInteger counter = new AtomicInteger();

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Start timeout");
                    }
                    for (int j = 0; j < iterationsPerWorker; j++) {
                        counter.incrementAndGet();
                    }
                    return null;
                }));
            }

            assertTrue(ready.await(5, TimeUnit.SECONDS),
                    "Some workers did not reach start gate");
            start.countDown();
            for (Future<?> future : futures) {
                future.get(10, TimeUnit.SECONDS);
            }
            assertEquals(workers * iterationsPerWorker, counter.get());
        } finally {
            start.countDown();
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

**Kiểm tra gì?** Có 8 worker cùng sửa một state; mọi worker đã “ready” trước khi mở cổng; tất cả future được quan sát; chỉ sau khi hoàn tất mới assert `8 × 2_000 = 16_000`. Nếu task ném exception, `Future.get()` khiến test fail thay vì âm thầm bỏ qua. `finally` giải phóng cổng và dọn executor.

`AtomicInteger` vốn đã có cam kết atomic của JDK; trong ứng dụng, thay nó bằng **đúng lớp/hàm cần test**, giữ cùng oracle và dùng một shared instance. Các timeout 5 và 10 giây ở đây là giá trị minh họa; cần chọn theo môi trường CI và hạn mức tiến độ hợp lý. Nếu gọi `shutdownNow()` khi một task chưa dừng, phải bảo đảm test harness không cho background worker còn sống sửa state mà test tiếp theo dùng chung.

## 7. Invariant trên nhiều field: atomic từng phần chưa đủ

Giả sử hệ thống có `available = 100` và `reserved = 0`. Mỗi lệnh đặt chỗ chuyển 30 từ available sang reserved. Nếu hợp đồng yêu cầu snapshot luôn hợp lệ, bất biến là:

- `available >= 0`.
- `reserved >= 0`.
- `available + reserved == 100`.

Hai biến `AtomicInteger` với hai lời gọi `addAndGet` riêng biệt vẫn có thể cho reader thấy tổng tạm thời là 70 hoặc 130 giữa hai bước cập nhật. Nếu snapshot đồng thời phải nhất quán, cập nhật và snapshot phải được phối hợp như **một giao dịch logic**.

Ví dụ mã thành phần, không phải chương trình có `main()`:

```java
final class ReservationBook {
    private int available = 100;
    private int reserved = 0;

    synchronized boolean reserve(int amount) {
        if (amount <= 0 || amount > available) {
            return false;
        }
        available -= amount;
        reserved += amount;
        return true;
    }

    synchronized Snapshot snapshot() {
        return new Snapshot(available, reserved);
    }

    record Snapshot(int available, int reserved) {}
}
```

Nếu hai thread cùng đặt 80, phải đúng **một yêu cầu thành công**; sau khi hoàn tất, snapshot phải là `(20, 80)`. Để test invariant trong lúc các writer đang chạy, dùng một reader liên tục lấy `snapshot()`, assert bất biến trên từng snapshot, và cho reader dừng bằng một cờ/đồng bộ đúng khi tất cả writer xong. Không đọc riêng `available`/`reserved` bằng các getter không đồng bộ rồi kết luận class không nhất quán.

Với `ConcurrentHashMap`, `get` và `put` an toàn riêng lẻ nhưng chuỗi `if (map.get(key) == null) map.put(key, value)` vẫn có cửa sổ check-then-act: hai thread có thể cùng coi key chưa tồn tại và cùng thực hiện side effect tạo value. Có thể cần `putIfAbsent` hoặc `computeIfAbsent`, nhưng semantics của side effect bên ngoài map (ví dụ ghi thanh toán) còn cần thiết kế idempotency/điều phối riêng. Thread-safe collection **không tự làm nguyên tử thao tác nghiệp vụ gồm nhiều lệnh**.

## 8. Happens-before và Java Memory Model trong test

Các quan hệ bộ nhớ cần hiểu:

- Thứ tự chương trình trong một thread là một nguồn happens-before.
- Một lần unlock monitor happens-before lần lock tiếp theo **cùng monitor**.
- Một lần ghi `volatile` happens-before lần đọc `volatile` tương ứng tiếp theo; các primitive atomic có memory semantics được đặc tả.
- Hành động trước `Thread.start()` happens-before hành động trong thread mới; hành động trong thread kết thúc happens-before thread khác phát hiện kết thúc qua `join()` thành công.
- Với executor, những hành động trước `submit` happens-before hành động của task; hành động của task happens-before hành động sau `Future.get()` thành công.
- Với latch, hành động trước `countDown()` happens-before hành động sau khi `await()` tương ứng trở về thành công.

Vì `Future.get()` tạo đồng bộ với task đã hoàn tất, main có thể quan sát trạng thái do các task ghi **sau tất cả future**. Nhưng điều đó không hàn gắn race giữa các task: nếu cả hai cùng đọc cũ rồi ghi chồng, giá trị cuối vẫn có thể sai.

Đặc biệt, `volatile int counter; counter++` vẫn không atomic: visibility tốt hơn nhưng read–modify–write vẫn có thể mất cập nhật. Với nhiều writer, dùng `AtomicInteger.incrementAndGet()`, lock thích hợp hoặc phân quyền sở hữu state để không cần share mutable data.

Khi test safe publication, reader không được dựa vào việc “đợi thêm 100 ms” để chắc chắn thấy giá trị. Nếu writer publish một object nhưng thiếu synchronization, test không thể mong JVM luôn lộ bug trong mọi lần chạy. Cần đúng cơ chế publication (`volatile`, final-field semantics dùng đúng cách, monitor, queue hoặc synchronizer) trước khi dựa vào kết quả test.

## 9. Testing ordering và linearizability

Không phải mọi state concurrent đều cần một thứ tự kết quả cố định. Nếu hai yêu cầu cùng lấy vé cuối, lịch A thắng/B thua và lịch B thắng/A thua đều hợp lệ. Nhưng lịch **cả hai thắng** là vi phạm.

**Linearizability** có nghĩa mỗi thao tác quan sát như có hiệu lực tại một thời điểm duy nhất nằm giữa lúc gọi và lúc trả, đồng thời giữ thứ tự thực của các thao tác không chồng lấp. Muốn test một API phức tạp:

1. Ghi history có operation id, input, thời điểm gọi và kết thúc, output/exception.
2. Có một mô hình tuần tự chính xác cho state và các phép chuyển.
3. Tìm một lịch tuần tự khớp history và giữ quan hệ thứ tự của các lời gọi không chồng lấp.
4. Nếu không tồn tại lịch hợp lệ, history là phản ví dụ; nếu tồn tại, chỉ có **history đó pass**, chưa chứng minh mọi history tương lai.

Timestamp log chỉ cung cấp quan sát; ghi log trong/ngoài lock có thể thay timing và không nhất thiết là thời điểm thao tác có hiệu lực. Với bài toán đơn giản, assert invariant cuối; với API state machine phức tạp, cân nhắc checker/model-based test chuyên dụng.

## 10. Stress testing, randomized testing và jcstress

Lịch do latch ép chứng minh một kịch bản; lỗi khác có thể đòi lịch hiếm hoặc reorder do tối ưu JVM/hardware. Các tầng test bổ sung:

| Phương pháp | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| Test controlled interleaving | Tái hiện lỗi cụ thể ổn định, dễ debug | Chỉ kiểm tra lịch đã điều phối |
| Contention test hàng nghìn thao tác | Phát hiện lost update, invariant hỏng dưới tranh chấp | Có thể pass tình cờ |
| Stress/randomized test, nhiều lần với seed | Bao phủ nhiều lịch, giúp tìm phản ví dụ | Không chứng minh tuyệt đối |
| Model-based/linearizability checking | So history với hợp đồng tuần tự | Phụ thuộc model và độ đầy đủ history |
| OpenJDK **jcstress** | Mô tả actor/outcome để thử các tình huống Java Memory Model khó | Cần harness, hiểu allowed/forbidden outcomes và môi trường |
| Load/soak test | Tìm tắc nghẽn, rò tài nguyên, liveness dưới tải | Throughput tốt không chứng minh safety |

Không dùng `Thread.yield()` hay `Thread.sleep()` như bảo đảm tạo ra interleaving. Chúng chỉ ảnh hưởng scheduling; việc một bug không tái hiện sau khi thêm sleep không phải đã sửa đúng.

Với randomized test, ghi lại **seed, số worker, số iteration, JVM/OS, cấu hình CPU, thời gian, input và lịch sử thao tác**. Khi tìm được lỗi, cố tạo một test ngắn có latch/barrier ép đúng lịch đó để chống regression. Mỗi vòng thử nên tạo state mới hoặc reset hoàn toàn; không để thread, task hay cache của vòng trước nhiễu vào vòng sau.

## 11. Diagnosing failure và timeout

Khi test fail, thông tin hữu ích gồm: trạng thái ban đầu, bất biến bị vi phạm, số thao tác thành công/thất bại, exception của từng future, state lúc kết thúc, seed và điểm đồng bộ đã đi qua.

Khi bị treo, thu thread dump để thấy thread ở `BLOCKED`, `WAITING` hay `TIMED_WAITING`, monitor/lock đang giữ và tài nguyên đang chờ. `ThreadMXBean.findDeadlockedThreads()` có thể phát hiện các deadlock của monitor và một số ownable synchronizer; nó không phát hiện mọi dạng chờ logic, ví dụ chờ latch do test không mở cổng. Phân biệt deadlock thật với thiếu worker trong executor, GC lâu, I/O treo và quá tải CPU.

Đừng lạm dụng print/log trong vòng lặp tranh chấp: logging làm thay đổi timing và bản thân nó có lock/I/O. Thay vào đó, lưu sự kiện có id thao tác vào buffer có giới hạn, hoặc chỉ bật instrument chọn lọc khi cần. Kiểm tra exception được truyền từ worker trước khi đọc kết quả.

## 12. Những sai lầm phổ biến trong concurrency test

- **Assert quá sớm:** `submit` chỉ xếp lịch, không chờ hoàn tất; luôn chờ kết thúc hợp đồng rồi mới assert state cuối.
- **Bỏ qua `Future.get()`:** exception worker bị giữ trong future, dễ tạo test xanh giả.
- **Dùng `sleep` để chờ:** timing nhạy máy và scheduler, dễ flaky; dùng synchronization + deadline.
- **Pool nhỏ hơn số task cùng chờ barrier:** test deadlock vì các task còn trong queue chưa thể báo ready.
- **Không mở latch trong `finally`:** test thất bại khiến worker treo, ảnh hưởng test sau.
- **Test với các instance riêng:** mỗi task sửa state khác nhau nên không có contention thật.
- **Chỉ kiểm tra counter:** bỏ qua invariant liên trường, unique side effect hoặc yêu cầu ordering.
- **Đọc snapshot không đồng bộ:** coi trạng thái trung gian hợp lệ là bug, hoặc ngược lại bỏ sót trạng thái không hợp lệ.
- **Dùng `volatile` như phép tăng atomic:** visibility không đồng nghĩa atomicity.
- **Chạy stress 10.000 lần rồi tuyên bố chắc chắn đúng:** chưa thử mọi lịch hợp lệ.
- **Không cleanup:** executor còn sống, callback hoặc thread vẫn có thể sửa shared state sau khi test kết thúc.

## 13. Quy trình áp dụng thực tế

1. Viết rõ state khởi tạo, thao tác đồng thời, invariant, những kết quả cuối được phép và deadline tiến độ.
2. Chỉ ra điểm có thể đan xen: read–modify–write, check-then-act, publish, lock, snapshot nhiều biến.
3. Viết một test nhỏ điều phối lịch nguy hiểm bằng latch/barrier và assert **hợp đồng**.
4. Đảm bảo mọi worker dùng chung state, có đủ worker, được mở cổng và được chờ qua future.
5. Sửa code bằng atomics, lock, concurrent collection hoặc loại bỏ shared mutable state; không chữa lỗi bằng delay.
6. Thêm contention/stress test, kiểm tra exception, cancellation, timeout, shutdown và những interleaving khó.
7. Khi gặp lỗi, lưu phản ví dụ với seed/history và đưa vào regression test có thể tái hiện.

**Ý chính:** kiểm thử concurrency phải nhắm vào **tính đúng đắn dưới mọi lịch thực thi hợp lệ**, chứ không chỉ “chạy song song mà không ném exception”. Bất biến tạo oracle; đồng bộ kiểm thử tạo lịch cạnh tranh có kiểm soát; future/timeout cung cấp quan sát hoàn tất; stress và công cụ chuyên biệt giúp tìm lịch mà unit test chưa chạm tới.
