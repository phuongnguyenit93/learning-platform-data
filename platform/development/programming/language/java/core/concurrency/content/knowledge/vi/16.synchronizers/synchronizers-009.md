# Latch dùng một lần so với barrier tái sử dụng trong Java

## 1. Hai bài toán trông giống nhau nhưng có hợp đồng khác nhau

Trong lập trình đa luồng, nhiều thread có thể cần đợi nhau hoặc đợi một mốc chung. Hai công cụ quan trọng của `java.util.concurrent` là **`CountDownLatch`** và **`CyclicBarrier`**. Cả hai có thể khiến thread chờ, nhưng chúng mô hình hóa hai loại phối hợp khác nhau:

- **CountDownLatch:** một hoặc nhiều thread **đợi đủ N tín hiệu**. Thread báo hiệu gọi `countDown()` và **không phải đợi các bên khác**. Khi bộ đếm về 0, latch mở vĩnh viễn; không có thao tác reset.
- **CyclicBarrier:** một nhóm có **số bên tham gia cố định** cùng đi tới một điểm hẹn. Mỗi bên gọi `await()`; khi đủ số bên, tất cả cùng vượt qua điểm hẹn. Sau khi vượt thành công, barrier **tự sẵn sàng cho vòng kế tiếp**, không phải tạo lại.

Ví dụ thực tế:

- Khởi tạo ba module độc lập rồi mở dịch vụ khi cả ba đã báo sẵn sàng: `CountDownLatch(3)`.
- Bốn worker tính toán theo từng vòng; mọi worker phải hoàn tất vòng hiện tại trước khi bắt đầu vòng tiếp theo: `CyclicBarrier(4)`.
- Một thread điều phối đợi nhiều worker, nhưng các worker không cần đợi nhau: latch là mô hình gọn hơn.
- Một pipeline nhiều pha mà số lượng bên tham gia thay đổi: có thể cần `Phaser` thay vì barrier cố định.

**Không phải “CountDownLatch là CyclicBarrier kém tính năng hơn”.** Hai công cụ có semantics khác nhau về ai phải chờ, việc đếm, khả năng tái sử dụng và cách xử lý lỗi. Bài học giới hạn trong Java Concurrency của JDK, không liên quan đến Spring.

## 2. So sánh tổng quan

| Tiêu chí | `CountDownLatch` | `CyclicBarrier` |
| --- | --- | --- |
| Mục tiêu | Chờ một **mốc** đủ N tín hiệu | Đồng bộ nhiều thread tại một **điểm hẹn**, có thể lặp |
| Khởi tạo | `new CountDownLatch(count)`, `count >= 0` | `new CyclicBarrier(parties)`, `parties >= 1` |
| Ai báo đã đến? | `countDown()` | `await()` |
| Thread báo hiệu có phải chờ không? | **Không**; `countDown()` trả về ngay | **Có**; `await()` đợi đủ party |
| Ai đợi? | Một hoặc nhiều thread gọi `await()`; không bắt buộc chính là bên phát tín hiệu | Thông thường chính các party gọi `await()` |
| Khi đủ bên/mốc | Bộ đếm về 0; mọi awaiter được mở | Barrier tripped; mọi party của vòng đó được giải phóng |
| Tái sử dụng | **Không**; one-shot | **Có**; tự sang thế hệ/vòng tiếp theo sau khi tripped |
| Hết hạn đợi | `await(timeout,unit)` trả `false` | `await(timeout,unit)` ném `TimeoutException` và làm barrier **broken** |
| Một bên bị interrupt khi chờ | Awaiter đó ném `InterruptedException`; latch **không broken** | Một party ném `InterruptedException` và barrier thường bị **broken**, các bên chờ khác ném `BrokenBarrierException` |
| Hành động khi đủ bên | Không có callback tự động của latch | Có tùy chọn `barrierAction` chạy trước khi thả các party |
| Phục hồi sau lỗi | Kiểm soát tín hiệu/timeout ở tầng ứng dụng, hoặc tạo latch mới | Có `reset()`, nhưng cần phối hợp ngoài; nhiều tình huống nên tạo barrier mới |
| Quan sát | `getCount()` | `getParties()`, `getNumberWaiting()`, `isBroken()` |

Một điểm quan trọng về chữ *tái sử dụng*: `CyclicBarrier` tự tái sử dụng **sau một vòng thành công**. `reset()` không phải thao tác bắt buộc sau từng vòng; nó là cách đưa barrier về trạng thái ban đầu, thường phục vụ khôi phục lỗi và có nguy cơ phá vỡ những thread đang chờ.

## 3. Cơ chế của CountDownLatch: chỉ mở một lần

Tạo latch bằng bộ đếm ban đầu N:

```java
import java.util.concurrent.CountDownLatch;

CountDownLatch done = new CountDownLatch(3);
```

Mỗi khi một phần công việc hoàn tất, thread thực hiện:

```java
done.countDown();
```

Bộ đếm biến thiên:

```text
Ban đầu: 3
Sự kiện A: 2
Sự kiện B: 1
Sự kiện C: 0 → latch mở
Các countDown sau đó: vẫn 0
Mọi await sau mốc này: trở về ngay
```

Thread cần chờ có thể dùng:

```java
done.await(); // Chờ đến khi count về 0 hoặc bị interrupt.
```

Lời gọi `countDown()` không block đợi các bên khác; nó chỉ giảm số đếm nếu còn dương. `await()` có thể được gọi **trước hoặc sau** khi các tín hiệu đến. Nếu đã về 0, `await()` có thể trả về ngay mà không yêu cầu tín hiệu mới.

### Một tín hiệu không nhất thiết tương ứng một thread

`CountDownLatch(3)` không có danh sách đăng ký ba thread. Có thể ba worker cùng báo mỗi worker một lần, hoặc một worker báo ba mốc riêng biệt theo thiết kế. Latch chỉ biết **số lần đếm**, không biết danh tính hay trạng thái thành công của bên phát tín hiệu.

Nếu một worker nhầm lẫn gọi `countDown()` hai lần, latch có thể mở sớm dù một công việc khác chưa hoàn tất. Nếu một worker bị lỗi mà không gọi `countDown()`, bộ đếm có thể không bao giờ về 0. Cần thiết kế ownership của từng tín hiệu và dùng `try/finally` nếu hợp đồng là “đã thoát khỏi phần xử lý”:

```java
Runnable work = () -> {
    try {
        performWork();
    } finally {
        done.countDown();
    }
};
```

Đây là fragment; `performWork()` và `done` do ứng dụng khai báo. `finally` bảo đảm báo khi *body đã chạy rồi thoát*, không bảo đảm task thành công. Nếu task bị từ chối hoặc bị hủy trước khi bắt đầu, `finally` trong task **không chạy**; người điều phối phải xử lý trường hợp thiếu tín hiệu.

### Có thể tạo cổng mở bằng count = 1

`CountDownLatch start = new CountDownLatch(1)` cho phép nhiều thread chờ một lệnh mở cổng. Thread điều phối gọi `start.countDown()` một lần; tất cả waiter đủ điều kiện đi tiếp. Không có chuyện waiter phải tự gọi `countDown()` để được đi qua.

## 4. Cơ chế CyclicBarrier: các party tự đợi nhau

Tạo một barrier cho ba bên:

```java
import java.util.concurrent.CyclicBarrier;

CyclicBarrier barrier = new CyclicBarrier(3);
```

Mỗi party, sau khi hoàn tất phần việc của vòng hiện tại, gọi `barrier.await()`. Hai bên đầu tiên sẽ chờ; bên thứ ba đến làm barrier tripped và mở đường cho cả ba. Trong vòng kế tiếp, ba bên lại gọi `await()` trên **chính đối tượng barrier đó**.

```text
Vòng 1:
A đến await ──┐
B đến await ──┤ đợi đủ ba party
C đến await ──┘ → tripped → cả A, B, C tiếp tục

Vòng 2 (cùng CyclicBarrier):
B đến await ──┐
C đến await ──┤ đợi đủ ba party
A đến await ──┘ → tripped → cả A, B, C tiếp tục
```

Không cần gọi `reset()` giữa vòng 1 và vòng 2 thành công. Thứ tự party tới barrier không nhất thiết giống nhau qua các vòng.

### Arrival index và barrier action

`await()` trả về **arrival index**: bên đến cuối nhận `0`, bên đầu tiên nhận `parties - 1`. Index không phải ID thread hay thứ tự cố định qua các vòng.

Constructor tùy chọn:

```java
CyclicBarrier barrier = new CyclicBarrier(
        3,
        () -> System.out.println("Một vòng đã đủ ba party"));
```

`barrierAction` được thực thi bởi **party đến cuối cùng** sau khi tất cả party đã tới barrier nhưng **trước khi các bên được giải phóng**. Nó chạy một lần cho mỗi vòng thành công. Có thể dùng action để tổng hợp trạng thái của vòng hoặc cập nhật mốc pha, miễn hành động đủ ngắn và tránh chờ chính những party đang bị giữ ở barrier.

Nếu `barrierAction` ném exception, exception đó truyền ra trên thread thực thi action và barrier đi vào trạng thái **broken**. Các party khác đang chờ có thể nhận `BrokenBarrierException`. Không đặt logic dễ lỗi hoặc blocking dài trong action mà không thiết kế cách phục hồi.

## 5. Ví dụ Java 17 độc lập: latch một lần và barrier qua ba vòng

Chương trình gồm hai phép thử.

- Với latch: ba task tính ra các giá trị 2, 4, 6 và báo hoàn tất. Thread chính đợi latch về 0, tính tổng, rồi gọi `await()` thêm lần nữa; lần chờ thứ hai không cần tín hiệu nào mới.
- Với barrier: ba worker tính ba vòng trên mảng riêng theo chỉ số và cùng chờ tại barrier ở cuối mỗi vòng. `barrierAction` đếm số vòng đã tripped; sau khi worker hoàn tất, main tổng hợp các số nguyên và in ra theo thứ tự xác định.

Lưu thành **`LatchVsBarrierDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class LatchVsBarrierDemo {
    public static void main(String[] args) throws Exception {
        latchOnce();
        barrierAcrossRounds();
    }

    private static void latchOnce() throws Exception {
        CountDownLatch completed = new CountDownLatch(3);
        ExecutorService pool = Executors.newFixedThreadPool(3);
        int[] values = new int[3];

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int index = 0; index < 3; index++) {
                final int i = index;
                futures.add(pool.submit(() -> {
                    try {
                        values[i] = 2 * (i + 1);
                    } finally {
                        completed.countDown();
                    }
                }));
            }

            completed.await();
            for (Future<?> future : futures) {
                future.get(); // Ghi nhận lỗi task, nếu có.
            }

            int total = values[0] + values[1] + values[2];
            System.out.println("Latch: count="
                    + completed.getCount() + ", total=" + total);

            completed.await(); // Count vẫn là 0: không đợi vòng mới.
            System.out.println("Latch second await: returned");
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    private static void barrierAcrossRounds() throws Exception {
        final int parties = 3;
        final int rounds = 3;
        int[][] results = new int[rounds][parties];
        AtomicInteger completedRounds = new AtomicInteger();
        CyclicBarrier barrier = new CyclicBarrier(
                parties,
                completedRounds::incrementAndGet);
        ExecutorService pool = Executors.newFixedThreadPool(parties);

        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int index = 0; index < parties; index++) {
                final int worker = index;
                futures.add(pool.submit(() -> {
                    for (int phase = 0; phase < rounds; phase++) {
                        results[phase][worker] =
                                10 * (phase + 1) + worker;
                        barrier.await(); // Điểm hẹn mỗi vòng.
                    }
                    return null;
                }));
            }

            for (Future<?> future : futures) {
                future.get(); // Đợi tất cả worker và phát hiện lỗi.
            }

            System.out.println("Barrier: phases="
                    + completedRounds.get());
            for (int phase = 0; phase < rounds; phase++) {
                int sum = 0;
                for (int value : results[phase]) {
                    sum += value;
                }
                System.out.println("Round " + (phase + 1)
                        + " total=" + sum);
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Workers did not terminate");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac LatchVsBarrierDemo.java
java LatchVsBarrierDemo
```

Stdout của lần chạy thành công:

```text
Latch: count=0, total=12
Latch second await: returned
Barrier: phases=3
Round 1 total=33
Round 2 total=63
Round 3 total=93
```

Trong phép thử barrier, ba worker ghi vào ba vị trí khác nhau của từng hàng mảng (ví dụ vòng 1 là 10, 11, 12). Chúng không tranh ghi cùng phần tử. `Future.get()` trước khi main đọc mảng cũng bảo đảm đã hoàn tất và có quan hệ visibility phù hợp. Trật tự worker đạt barrier có thể khác nhau, nhưng mọi vòng thành công chỉ tăng `completedRounds` một lần; không có lệnh in từ worker nên stdout xác định.

**Giới hạn của demo:** Nó giả định tất cả task được executor nhận và có thể tiến triển. Nếu pool thiếu worker hoặc một task bị kẹt trước `await()`, các party khác có thể chờ vô hạn. Trong ứng dụng thật nên có timeout, interruption/cancellation và chính sách xử lý barrier hỏng. Demo cố ý tách thành công bình thường và lỗi để dễ thấy semantics cơ bản.

## 6. Vì sao không thay barrier bằng một CountDownLatch dùng lại?

Sau khi bộ đếm của latch về 0, không có API tăng đếm hoặc reset về giá trị ban đầu:

```java
CountDownLatch latch = new CountDownLatch(2);
latch.countDown();
latch.countDown();
latch.await(); // Đủ điều kiện đi tiếp.
latch.await(); // Cũng đi tiếp ngay; KHÔNG phải vòng hai.
```

Vì vậy, nếu mỗi worker cần **đợi nhau cuối mỗi vòng**, một latch duy nhất không đủ. Có thể tạo một `CountDownLatch` mới cho mỗi vòng và truyền tới đúng bên báo/đợi, nhưng điều đó đòi hỏi giao thức công bố latch mới và chuyển pha đúng lúc. Trong trường hợp số bên cố định, `CyclicBarrier` thường đơn giản hơn.

Ngược lại, đừng ép `CyclicBarrier` làm nhiệm vụ “main đợi ba worker hoàn thành” theo cách để **main chỉ chờ** nhưng ba worker chỉ phát tín hiệu rồi đi tiếp mà không chờ. Với barrier, mỗi party tham gia phải gọi `await()` và có thể bị chặn. `CountDownLatch` diễn đạt ý định của bài toán một chiều rõ hơn.

## 7. Failure: timeout và interruption có hiệu ứng khác nhau

Đây là khác biệt quan trọng nhất khi xử lý lỗi.

### 7.1. CountDownLatch không có trạng thái broken

`CountDownLatch.await(timeout, unit)` trả:

- `true` nếu bộ đếm đạt 0 trong thời gian chờ.
- `false` nếu hết thời hạn mà bộ đếm chưa về 0.
- `InterruptedException` nếu thread chờ bị interrupt.

Timeout hoặc interruption **không tự thay đổi bộ đếm** và không hủy các worker. Một thread đợi khác vẫn có thể chờ tiếp, và các lần `countDown()` sau đó vẫn có thể đưa count về 0. Không cần gọi reset vì latch không có reset; cũng không có `isBroken()`.

```java
CountDownLatch neverOpened = new CountDownLatch(1);
boolean reached = neverOpened.await(0, TimeUnit.NANOSECONDS);
System.out.println(reached); // false
System.out.println(neverOpened.getCount()); // 1
```

Đây là fragment nếu đặt cùng import thích hợp. Với timeout bằng 0 và count còn dương, `await(timeout)` không chờ; latch vẫn chưa mở và có thể nhận `countDown()` sau đó.

### 7.2. CyclicBarrier có trạng thái broken

`CyclicBarrier.await(timeout, unit)` có thể ném:

- `TimeoutException` khi chính lời gọi hết thời hạn; việc timeout làm barrier đi vào trạng thái **broken**.
- `InterruptedException` khi thread đang chờ bị interrupt; barrier bị broken, trừ trường hợp cuộc đua với một lần trip/điểm ngắt có semantics theo API.
- `BrokenBarrierException` nếu party khác bị interrupt/timeout, barrier đã broken, `reset()` xảy ra khi đang chờ hoặc barrier action lỗi.

Mô hình này thường được gọi là **all-or-none breakage**: khi một party không thể cùng vượt qua barrier của vòng hiện tại, những party khác không tiếp tục chờ một vòng thành công không còn khả thi.

`barrier.isBroken()` báo trạng thái hỏng; `barrier.getNumberWaiting()` cho biết số party hiện đang bị chặn trong `await()` (phục vụ chẩn đoán, không phải dữ kiện atomic để quyết định tiến trình). `barrier.getParties()` trả số party yêu cầu ban đầu và không tự thay đổi giữa các vòng.

### 7.3. Ví dụ lỗi có kết quả xác định

Lưu `BrokenBarrierDemo.java`:

```java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class BrokenBarrierDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);

        try {
            // Chỉ có main gọi await; timeout 0 khiến nó không chờ.
            barrier.await(0, TimeUnit.NANOSECONDS);
            throw new AssertionError("Expected timeout");
        } catch (TimeoutException expected) {
            System.out.println("Timed out");
        }

        System.out.println("Broken: " + barrier.isBroken());
        barrier.reset();
        System.out.println("Broken after reset: " + barrier.isBroken());
    }
}
```

Chạy:

```bash
javac BrokenBarrierDemo.java
java BrokenBarrierDemo
```

Stdout:

```text
Timed out
Broken: true
Broken after reset: false
```

Trong ví dụ này không có hai party tới cùng lúc nên cuộc hẹn không thể hoàn thành. Sau timeout, trạng thái broken là `true`. `reset()` đưa barrier về trạng thái ban đầu; **nó không có nghĩa những task cũ đã tự khôi phục**. Code ứng dụng phải bảo đảm mọi bên đang chờ và đang chạy đã nhận biết lỗi, sau đó thống nhất có tiếp tục hay không.

## 8. reset() không phải cơ chế phục hồi tự động

`CyclicBarrier.reset()` đưa barrier về trạng thái ban đầu, nhưng nếu đang có party đợi, những party đó nhận `BrokenBarrierException`. Nếu một số thread đang xử lý lỗi của vòng cũ còn thread khác bắt đầu vòng mới, việc reset thiếu phối hợp có thể gây race hoặc lẫn thế hệ.

Cần phân biệt:

- **Vòng kết thúc thành công:** không gọi `reset()`; barrier tự tái sử dụng.
- **Vòng bị broken:** mọi party cần biết lỗi, dừng/hủy/rollback phần việc liên quan theo nghiệp vụ; nếu muốn khôi phục, các thread phải phối hợp rõ việc tạo barrier mới hoặc reset.
- **Thêm hoặc bớt worker:** `CyclicBarrier` có số party cố định. `reset()` **không đổi** `getParties()`. Nếu tập tham gia thay đổi, tạo barrier mới với số party phù hợp hoặc dùng `Phaser`.

Một bên timeout không tự động hủy công việc của các bên khác đang xử lý ngoài barrier. Sau `BrokenBarrierException`, ứng dụng cần thiết kế đường thoát, hủy `Future`, interrupt và cleanup nếu không muốn một số worker tiếp tục tính toán mất kiểm soát.

## 9. Interruption và hủy task: phải xử lý như điều kiện điều phối

Hai phương thức `CountDownLatch.await()` và `CyclicBarrier.await()` đều có thể bị interrupt, nhưng hậu quả với synchronizer khác nhau:

| Sự kiện | Latch | Barrier |
| --- | --- | --- |
| Một thread chờ bị interrupt | Thread đó ném `InterruptedException`; các thread khác vẫn có thể đợi count về 0 | Có thể làm thế hệ hiện tại broken; bên khác nhận `BrokenBarrierException` |
| Caller timeout | Bộ đếm không đổi, caller nhận `false` | Thế hệ bị broken, caller nhận `TimeoutException` |
| Worker chưa từng bắt đầu | Có thể thiếu một `countDown()`, khiến latch không mở | Có thể thiếu một party, khiến các bên đã đến barrier chờ mãi |
| Hủy `Future` trước khi body chạy | `finally` bên trong body không chạy; cần accounting riêng | Party không đến barrier; các bên khác cần timeout/đường hủy |
| Worker giữ lock mà party khác cần | Có thể tạo circular wait | Có thể tạo circular wait |

Khi dùng executor, hãy lưu các `Future` nếu cần cancel; dùng timeout phù hợp và xử lý `InterruptedException`. Nếu một bên của barrier lỗi trước khi gọi `await()`, các bên khác **không tự biết** vì chưa có sự kiện gây broken ở barrier. Có thể cần `reset()` bởi thread điều phối, `Future.cancel(true)`, hoặc timeout tại các awaiter để tránh chờ vô hạn.

**Không nuốt `InterruptedException`.** Trong method cho phép, truyền ngoại lệ lên trên. Trong method không thể truyền, thường khôi phục interrupt flag bằng `Thread.currentThread().interrupt()` và thoát. Với barrier bị broken, không lặp `await()` mãi trên cùng barrier mà không có giao thức khôi phục.

## 10. Happens-before: điều gì được công bố khi vượt mốc?

### CountDownLatch

Hợp đồng memory consistency của latch: các hành động của một thread **trước khi `countDown()`** *happen-before* các hành động **sau khi `await()` tương ứng thành công** ở thread khác. Điều này giúp thread đợi thấy trạng thái được chuẩn bị trước khi các tín hiệu hoàn tất.

Ví dụ fragment:

```java
int[] shared = new int[1];
CountDownLatch ready = new CountDownLatch(1);

// Worker:
shared[0] = 42;
ready.countDown();

// Thread khác:
ready.await();
System.out.println(shared[0]); // Thấy ghi trước countDown.
```

Những dòng đánh dấu “Worker” và “Thread khác” là hai luồng thực thi giả định, không phải chương trình độc lập. Nếu `await(timeout)` trả `false` thì không được coi mốc đã đạt hoặc áp dụng bảo đảm của việc chờ **thành công**.

### CyclicBarrier

Hợp đồng memory consistency của barrier: các hành động trước khi một party gọi `await()` *happen-before* hành động trong `barrierAction`, và những hành động của action *happen-before* những hành động sau khi party khác **`await()` thành công** ở vòng đó. Vì thế barrier phù hợp cho thuật toán nhiều pha cần mỗi pha thấy kết quả của pha trước.

Dẫu vậy, latch và barrier **không biến thao tác read-modify-write trên shared mutable state thành nguyên tử**. Nếu hai worker cùng tăng một biến bằng `counter++` trước mốc mà không có đồng bộ hóa phù hợp, vẫn có thể xảy ra lost update. Dùng phần tử mảng tách biệt, `AtomicInteger`, lock hoặc cấu trúc dữ liệu concurrent khi các worker cùng sửa một trạng thái.

## 11. Deadlock do thread pool không đủ worker

Một bẫy nổi bật là **thread starvation deadlock**. Ví dụ:

- `ExecutorService pool = Executors.newFixedThreadPool(2)`.
- Submit ba task; mỗi task có nhiệm vụ gọi `barrier.await()` trên `CyclicBarrier(3)`.
- Hai task đầu giữ cả hai worker và đợi party thứ ba.
- Task thứ ba vẫn ở queue, không có worker trống để bắt đầu.
- Không party nào có thể hoàn tất: cả hai worker đang đợi lẫn nhau và task trong queue.

Bẫy tương tự có thể xuất hiện khi dùng latch với một cổng start: main đợi ba worker đều báo “ready”, nhưng chỉ hai worker của pool có thể bắt đầu, rồi cả hai bị giữ lại ở một latch chưa mở.

Cách tránh:

1. Bảo đảm số worker thực sự có thể chạy đồng thời ít nhất bằng số party **sẽ bị block ở barrier**, hoặc đổi thiết kế để không cần giữ worker suốt thời gian đợi.
2. Dùng `await(timeout, unit)` để không treo vô hạn, đồng thời xử lý `TimeoutException`/`BrokenBarrierException`.
3. Đừng giữ monitor/lock cần cho party khác trong khi chờ barrier hoặc latch.
4. Đừng đặt một `barrierAction` đợi kết quả từ worker khác đang bị chặn ở cùng barrier.
5. Nếu số party thay đổi động hoặc có sự kiện worker rời nhóm, cân nhắc `Phaser`.

Số thread lớn hơn số party cũng không giải quyết được mọi dạng deadlock nếu task giữ lock theo thứ tự vòng hoặc đang chờ I/O không có timeout.

## 12. Khi nào chọn Phaser?

`Phaser` là synchronizer có thể tái sử dụng qua nhiều **pha** và hỗ trợ số party thay đổi bằng `register()`, `bulkRegister(int)` và `arriveAndDeregister()`. Những thao tác như `arriveAndAwaitAdvance()` có vai trò tương tự đi tới một barrier rồi chờ pha tiếp theo.

| Nhu cầu | Công cụ phù hợp |
| --- | --- |
| Chờ đúng N sự kiện một lần | `CountDownLatch` |
| Mở một cổng cho nhiều waiter | `CountDownLatch(1)` |
| Nhóm N worker cố định gặp nhau ở cuối mỗi vòng | `CyclicBarrier(N)` |
| Nhóm worker có thể đăng ký/rút khỏi pha | `Phaser` |
| Muốn kiểm soát số tác vụ đồng thời bằng permit | `Semaphore` |
| Muốn chờ một `Future<T>` hoàn tất và đọc kết quả/lỗi | `Future.get()` |
| Muốn đợi một `Thread` cụ thể chấm dứt | `Thread.join()` |

Khác biệt đáng nhớ: `CyclicBarrier` có cơ chế **broken** khi một bên bị interrupt/timeout trong lúc chờ; `Phaser` có chính sách khác, các overload đợi pha với timeout/interruption **không tự phá trạng thái phaser** theo cách của CyclicBarrier. Cần đọc hợp đồng của `Phaser` trước khi chuyển qua vì cách xử lý lỗi không giống nhau.

Không chọn `Phaser` chỉ vì nó nhiều tính năng; cho bài toán fixed-party nhiều vòng, `CyclicBarrier` thường dễ đọc. Cho một mốc độc lập, `CountDownLatch` đơn giản và ít giao thức hơn.

## 13. Quy trình thiết kế synchronizer an toàn

Trước khi viết code, hãy tự trả lời:

1. **Mốc hay điểm hẹn?** Bên báo tín hiệu có cần chờ các bên còn lại không?
2. **Một lần hay nhiều pha?** Sau khi mở mốc, có thực sự cần đóng lại để chờ vòng mới không?
3. **Số party cố định?** Ai đăng ký party, ai được phép rời?
4. **Lỗi của một task ảnh hưởng ai?** Với barrier, khi một party thất bại, các party khác có tiếp tục một vòng khác không?
5. **Timeout là lỗi gì?** Latch trả boolean, barrier ném exception và có thể broken.
6. **Đủ worker?** Có task nào phải ở queue trong khi tất cả worker đều đang chờ synchronizer?
7. **Side effect và cleanup?** Tín hiệu đến có nghĩa thành công, đã rời task hay đã giải phóng tài nguyên?
8. **Kết quả được lưu ở đâu?** Latch/barrier không thay `Future` hoặc nơi thu thập exception.
9. **Memory visibility?** Có sử dụng đúng điểm đồng bộ, và có tránh data race giữa những worker cùng ghi dữ liệu không?
10. **Sau lỗi làm gì?** Hủy task, đóng tài nguyên, tạo barrier mới, hay dừng toàn bộ phép tính?

Nếu worker có thể bị hủy **trước khi bắt đầu**, `finally` bên trong task sẽ không chạy; điều phối viên phải xử lý task không được nhận. Với barrier, số party thực sự đến ít hơn kỳ vọng là nguyên nhân điển hình khiến chờ vô hạn.

## 14. Những lỗi phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng một `CountDownLatch` cho nhiều lượt rồi tưởng `await()` tự đợi lại | Sau khi count về 0, mọi `await()` tiếp theo đi qua ngay | Tạo latch mới đúng mỗi giai đoạn hoặc dùng `CyclicBarrier` |
| Dùng `CyclicBarrier` chỉ để một thread đợi N tín hiệu không chặn các worker | Các worker bị buộc phải đứng chờ ở `await()` | Dùng `CountDownLatch` |
| Cho rằng `countDown()` đợi bên khác | Hiểu sai độ trễ và luồng xử lý | Nhớ `countDown()` không block |
| Cho rằng barrier tự reset ngay cả khi bị broken | Các `await()` sau tiếp tục nhận lỗi | Phối hợp xử lý lỗi, reset có chủ đích hoặc tạo barrier mới |
| Gọi `reset()` sau mỗi vòng thành công | Có thể phá nhầm party đang tới vòng tiếp theo | Để barrier tự tái sử dụng |
| Dùng `await(timeout)` mà không phân biệt boolean và exception | Xử lý sai lỗi | Latch trả boolean; barrier ném `TimeoutException` |
| Nuốt `InterruptedException` ở một party | Hợp đồng hủy không rõ, barrier có thể broken | Truyền/khôi phục interrupt và điều phối lỗi |
| Cho ít worker hơn số party cần chờ | Thread starvation deadlock | Đủ capacity, timeout, thiết kế lại |
| Đọc `getNumberWaiting()` rồi dự đoán chắc chắn ai sẽ tới | Trạng thái thay đổi concurrent | Dùng để quan sát/debug, không để phối hợp chính |
| Dùng latch/barrier như cơ chế lưu exception hoặc rollback | Task có thể lỗi hoặc gây side effect dù mốc đã đạt | Kết hợp `Future`, result status và cleanup |
| Cho nhiều worker cùng tăng biến thường | Data race dù có barrier | Atomic/lock hoặc tách ô kết quả |
| Chạy I/O lâu trong barrier action | Giữ tất cả party ở barrier, tăng độ trễ | Action ngắn; I/O ở ngoài với timeout riêng |

## 15. Câu hỏi tự kiểm tra

**1. CountDownLatch đã về 0 có thể gọi reset để chờ vòng hai không?**  
Không. Nó là one-shot; muốn có mốc mới thì tạo latch mới hoặc chọn synchronizer khác.

**2. `CyclicBarrier(4)` cần bao nhiêu lần `await()` trong mỗi vòng?**  
Bốn party đến trong cùng một thế hệ. Khi đủ bốn, barrier tripped, rồi tự chuẩn bị vòng kế tiếp.

**3. Một worker chỉ báo hoàn tất và không cần chờ các worker khác nên dùng gì?**  
`CountDownLatch.countDown()` nếu mục tiêu là mở mốc cho các thread khác.

**4. `CountDownLatch.await(1, SECONDS)` bị timeout có ném `TimeoutException` không?**  
Không; overload này trả `false` khi count chưa về 0 và thời gian đã hết.

**5. Một party hết hạn chờ ở `CyclicBarrier.await(timeout,unit)` thì các party khác có tiếp tục chờ vòng đó đến khi đủ số không?**  
Không theo semantics thông thường; barrier trở thành broken và các bên chờ khác nhận `BrokenBarrierException`.

**6. Có cần gọi `barrier.reset()` sau vòng thành công?**  
Không. CyclicBarrier tự tái sử dụng. Reset có thể phá các party đang chờ.

**7. `barrierAction` chạy ở đâu?**  
Trên thread của party đến cuối cùng, trước khi giải phóng các party của vòng đó.

**8. Vì sao pool 2 worker và barrier 3 party có thể deadlock?**  
Hai worker có thể đang chờ party thứ ba, còn party thứ ba bị kẹt trong queue chưa có worker để chạy.

**9. Barrier có tự biến phép `sharedCounter++` của nhiều worker thành an toàn không?**  
Không. Barrier chỉ điều phối mốc pha và visibility; read-modify-write tranh chấp vẫn cần đồng bộ.

**10. Khi số party có thể thay đổi động qua các pha, nên cân nhắc gì?**  
`Phaser` vì nó hỗ trợ đăng ký và rút party, thay vì `CyclicBarrier` có số party cố định.

## Tài liệu tham khảo

- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- [Java SE 17 — Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)
- [Java SE 17 — Semaphore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Semaphore.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
