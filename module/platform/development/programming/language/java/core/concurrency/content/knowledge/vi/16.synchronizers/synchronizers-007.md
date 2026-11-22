# Barrier action, trạng thái broken và reset trong Java CyclicBarrier

`java.util.concurrent.CyclicBarrier` là một **synchronizer** giúp một nhóm cố định các thread gặp nhau tại cùng một điểm đồng bộ: mỗi bên gọi `await()` sau khi hoàn thành phần việc của mình; **chỉ khi đủ số bên** (parties), barrier mới mở để tất cả tiếp tục sang pha kế tiếp. Sau khi mở thành công, cùng một barrier **tự tái sử dụng** cho nhiều pha, do đó mang tên *cyclic*.

Ba khái niệm cần hiểu sâu là:

1. **Barrier action**: một `Runnable` tùy chọn chạy **đúng một lần cho mỗi lần barrier mở thành công**, trên **thread đến cuối cùng**, sau khi tất cả parties đã đến nhưng **trước khi họ được giải phóng**. Nó thường tổng hợp kết quả của pha vừa xong.
2. **Broken state**: nếu một bên bị interrupt, timeout khi đang chờ, hoặc barrier action thất bại, `CyclicBarrier` có cơ chế **all-or-none breakage**: cả nhóm chờ cùng bị ảnh hưởng, thay vì các bên còn lại đứng chờ tưởng rằng pha vẫn hợp lệ.
3. **Reset**: `reset()` thiết lập **thế hệ barrier mới** sau sự cố. Đây không phải lệnh cứu sống một pha đang chạy; nếu reset khi có thread đang chờ, các thread đó sẽ nhận `BrokenBarrierException`. Phải phối hợp recovery ở cấp ứng dụng.

Bài này trình bày Java concurrency nói chung theo JDK 17+, không sử dụng cơ chế của Spring.

## 1. Bức tranh cơ bản: nhiều worker, một điểm hẹn

Giả sử có ba worker tính toán ba partition dữ liệu, đồng bộ ở cuối mỗi vòng:

```text
Pha 0
Worker A: compute A0 ------ await()
Worker B: compute B0 -- await()       [còn đợi]
Worker C: compute C0 --------- await()   <-- bên đến cuối
                                     |
                                     v
                            barrier action
                            combine A0+B0+C0
                                     |
                                     v
                         tất cả được phép đi tiếp
Pha 1
Worker A: compute A1 ---- await()
Worker B: compute B1 -------- await()
Worker C: compute C1 -- await()
                                     |
                                     v
                            barrier action lần 2
                                     |
                                     v
                         tất cả tiếp tục/hoàn tất
```

`CyclicBarrier(3)` có **3 parties**, không phải “3 lượt await tổng cộng trong cả vòng đời”. Mỗi **generation** cần đủ ba lời `await` tham gia. Khi tripped thành công, barrier chuyển sang generation mới tự động; không gọi `reset()` mỗi vòng.

### Thuật ngữ

| Thuật ngữ | Nghĩa |
| --- | --- |
| **Party** | Một bên tham gia; thường là worker/thread sẽ gọi `await` đúng một lần ở mỗi pha |
| **Generation** | Một lượt chờ của barrier, từ lúc chưa đủ parties tới khi tripped hoặc broken |
| **Arrival** | Một bên gọi `await()` cho generation hiện tại |
| **Trip** | Đủ parties và barrier action (nếu có) hoàn thành thành công; parties được mở |
| **Barrier action** | Runnable chạy một lần trên bên đến cuối trước khi parties được phép rời barrier |
| **Broken barrier** | Thế hệ đồng bộ bị hỏng; không thể coi pha hiện tại đã hoàn tất thành công |
| **Reset** | Kết thúc/loại bỏ generation cũ và tạo generation chờ mới |
| **Arrival index** | Giá trị từ `await()`, từ `parties-1` (đến sớm nhất) đến `0` (đến cuối cùng) |

Không cần mỗi party là một `Thread` cố định về mặt cú pháp, nhưng thuật toán thường cần **đúng N lượt đến cho mỗi pha**. Nếu chỉ có N−1 thread có khả năng gọi `await`, chương trình có thể chờ mãi nếu không dùng timeout/cancellation.

## 2. Các API quan trọng

```java
CyclicBarrier barrier = new CyclicBarrier(3);
CyclicBarrier withAction =
        new CyclicBarrier(3, () -> doPhaseSummary());
```

Đây là snippet, `doPhaseSummary()` là method ứng dụng; cần import `java.util.concurrent.CyclicBarrier`. Số `parties` phải **tối thiểu 1**, nếu không constructor ném `IllegalArgumentException`.

| API | Công dụng | Lưu ý |
| --- | --- | --- |
| `new CyclicBarrier(n)` | Tạo barrier cho n parties | Không có action |
| `new CyclicBarrier(n, action)` | Tạo barrier và action | Action là `Runnable`, không có result trả về |
| `int await()` | Đợi đủ parties | Có thể ném `InterruptedException` hoặc `BrokenBarrierException` |
| `int await(timeout, unit)` | Đợi có giới hạn | Có thể thêm `TimeoutException` |
| `int getParties()` | Số parties cấu hình | Không đổi do reset |
| `int getNumberWaiting()` | Số parties **đang chờ** trong generation hiện tại | Chủ yếu phục vụ debug/assertions, không phải business predicate |
| `boolean isBroken()` | Generation hiện tại đang broken? | Sau reset thường false vì là generation mới |
| `void reset()` | Đưa barrier về trạng thái ban đầu | Giải phóng waiters của generation cũ **bằng exception** |

**Không có** `arriveAndDeregister()` ở CyclicBarrier. Nếu số participants cần tăng/giảm linh hoạt, cân nhắc `Phaser`. Không dùng `reset()` để thay số parties vì nó giữ nguyên `getParties()`.

## 3. Barrier action chạy khi nào và trên thread nào?

Khi một `CyclicBarrier` có action:

```java
CyclicBarrier barrier = new CyclicBarrier(
        3,
        () -> aggregatePreviousPhase()
);
```

Đây là snippet; `aggregatePreviousPhase` là logic ứng dụng.

Trình tự **thành công** của một generation:

1. Các worker hoàn tất phần của mình và gọi `await()`.
2. Những bên đến chưa đủ số parties **chờ** ở barrier.
3. Thread đến **cuối cùng** chạy `barrierAction.run()` ngay trong đường `await` của nó.
4. Khi action kết thúc **bình thường**, generation được mở và các parties được giải phóng.
5. Barrier chuyển generation mới, sẵn sàng cho vòng tiếp theo.

**Không có một “thread action” riêng được tạo mặc định**: chính thread đến cuối thực thi callback. Action không chạy song song một lần trên mỗi party, không được tự schedule như một task riêng của executor.

Nếu số parties là 3, action **không chạy khi chỉ có 2 threads đến**. Điều này khác trigger “đã có ít nhất một kết quả”. Đừng thiết kế callback mà giả định luôn có thread thứ ba nếu task có thể fail/timeout trước khi `await`.

### Arrival index

`await()` trả **arrival index** trong khoảng `0..(parties-1)`:

- `parties - 1`: bên đến **đầu tiên**.
- `0`: bên đến **cuối cùng** (chạy barrier action nếu có).
- Các chỉ số khác: thứ tự đến trung gian.

Không dự đoán worker ID nào nhận index 0: điều đó phụ thuộc scheduling. Muốn chỉ định **một worker thực hiện thao tác sau barrier**, có thể viết:

```java
int index = barrier.await();
if (index == 0) {
    doOnceAfterTrip();
}
```

Đây là snippet trong method xử lý `InterruptedException`/`BrokenBarrierException`; `doOnceAfterTrip` do ứng dụng định nghĩa. Khác barrier action, `doOnceAfterTrip()` nằm **sau `await`**, khi các parties khác **đã có thể** bắt đầu pha tiếp theo. Không dùng mẫu `index==0` như một cách thay thế action nếu thao tác **phải hoàn tất trước khi tất cả các thread được giải phóng**.

### Hành vi khi barrier action thất bại

Nếu action ném unchecked exception, **thread đến cuối** nhìn thấy chính lỗi đó trên đường `await()`; barrier được đánh dấu broken, các bên đang chờ nhận `BrokenBarrierException`. Vì vậy exception ở callback không chỉ làm lỗi một worker; nó **phá tính hợp lệ của cả pha**.

**Không mặc định action luôn chạy:** nếu barrier bị timeout/interrupt/reset trước khi đủ parties, action của generation đó không được chạy trên đường trip thành công. Logic cleanup khi lỗi không nên chỉ đặt trong barrier action.

## 4. Memory consistency: barrier action có thấy dữ liệu của parties không?

Có bảo đảm theo **happens-before** của `CyclicBarrier`:

> Các thao tác của mỗi worker **trước khi `await()`** xảy ra-before các thao tác **trong barrier action**, và các thao tác **trong barrier action** xảy ra-before các thao tác **sau khi `await()` thành công** của các worker khác.

Nhờ đó, mẫu **mỗi worker ghi một vùng không chồng lấn, action đọc các vùng ấy** có thể đúng mà không cần bọc mọi phép gán bằng `synchronized`, miễn là cấu trúc dữ liệu và quyền sở hữu được thiết kế phù hợp:

```java
// Workers (mỗi worker có index riêng):
partialResults[workerIndex] = localCalculation();
barrier.await();

// Barrier action:
int sum = 0;
for (int value : partialResults) {
    sum += value;
}
phaseTotal = sum;
```

Đây là **snippet**, cần tạo `partialResults`, `phaseTotal` và các biến/method tương ứng ở nơi khác. Worker **không ghi cùng phần tử array với worker khác**, action đọc sau khi mọi bên tới barrier; kết quả `phaseTotal` được công bố trước khi các bên rời `await` thành công.

Bảo đảm này **không làm toàn bộ array thread-safe** nếu worker khác vẫn sửa cùng chỉ số đồng thời ngoài đúng protocol. Nếu action giữ reference tới một mutable object và trả về, worker khác có thể bắt đầu sửa object cho phase tiếp theo; code bên ngoài phải biết lúc nào dữ liệu còn ổn định.

### Vì sao action thường dùng để aggregate?

Nếu mỗi worker tự kiểm tra “tôi có phải người đến cuối không” rồi aggregate **sau `await`**, các worker khác đã được thả và có thể làm phase tiếp. Khi đó aggregate có thể đọc dữ liệu đã bị ghi đè bởi phase mới.

Đặt aggregate **trong barrier action** bảo đảm tất cả worker còn bị giữ lại tới khi aggregate hoàn thành. Đây là một lý do quan trọng để chọn action thay vì `if (await() == 0)`.

## 5. Java 17 runnable: action chạy một lần mỗi pha

Ví dụ ba worker chạy **hai pha**. Mỗi worker ghi một phần tử riêng của `partials` theo pha rồi gọi barrier. Action cộng ba phần tử, ghi kết quả pha, tăng action counter. Thread nào đến cuối mỗi pha không quan trọng; chương trình chỉ in thống kê sau khi tất cả futures hoàn tất.

Tạo tệp **`BarrierActionPhasesDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierActionPhasesDemo {
    public static void main(String[] args) throws Exception {
        int parties = 3;
        int phases = 2;
        int[] partials = new int[parties];

        AtomicInteger actions = new AtomicInteger();
        AtomicInteger lastSum = new AtomicInteger();
        AtomicInteger successfulAwaits = new AtomicInteger();
        AtomicInteger lastArrivalReturns = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(parties, () -> {
            int sum = 0;
            for (int p : partials) {
                sum += p;
            }
            lastSum.set(sum);
            actions.incrementAndGet();
        });

        ExecutorService pool = Executors.newFixedThreadPool(parties);
        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int id = 0; id < parties; id++) {
                final int workerId = id;
                futures.add(pool.submit(() -> {
                    for (int phase = 0; phase < phases; phase++) {
                        partials[workerId] = workerId + 1 + phase;
                        try {
                            int arrivalIndex =
                                    barrier.await(5, TimeUnit.SECONDS);
                            successfulAwaits.incrementAndGet();
                            if (arrivalIndex == 0) {
                                lastArrivalReturns.incrementAndGet();
                            }
                        } catch (Exception e) {
                            throw new IllegalStateException(
                                    "Barrier failed", e);
                        }
                    }
                }));
            }

            for (Future<?> f : futures) {
                f.get(10, TimeUnit.SECONDS);
            }

            System.out.println("phases=" + phases);
            System.out.println("barrierActions=" + actions.get());
            System.out.println("lastSum=" + lastSum.get());
            System.out.println(
                    "successfulAwaits=" + successfulAwaits.get());
            System.out.println(
                    "indexZeroReturns=" + lastArrivalReturns.get());
            System.out.println("broken=" + barrier.isBroken());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac BarrierActionPhasesDemo.java
java BarrierActionPhasesDemo
```

Stdout khi tất cả workers hoàn tất trong các deadline:

```text
phases=2
barrierActions=2
lastSum=9
successfulAwaits=6
indexZeroReturns=2
broken=false
```

**Phân tích kết quả:**

- Phase 0: `partials` có `1, 2, 3` → action ghi `6`.
- Phase 1: `partials` có `2, 3, 4` → action ghi `9`; đây là `lastSum` cuối cùng.
- Mỗi phase có ba successful `await` → tổng cộng 6.
- Mỗi phase đúng một thread nhận arrival index 0 → 2 lượt.
- Action chạy đúng một lần ở mỗi phase thành công → 2 lượt; không cần reset.
- Không in worker IDs vì không thể dự đoán thread nào đến cuối.
- `Future.get` chờ tất cả workers hoàn tất rồi main mới in, nên kết quả không phụ thuộc thứ tự in của threads.

**Giới hạn:** mỗi worker ghi riêng phần tử `partials[workerId]` và không có writer khác sửa cùng index trong phase đó. Action chạy trước khi release nên aggregate không bị trộn dữ liệu phase kế tiếp. Ví dụ không cho thấy hành vi khi một task thất bại; các phần sau xử lý đường lỗi.

## 6. Broken barrier là gì?

`CyclicBarrier` dùng mô hình **all-or-none breakage**. Khi một bên không thể chờ tới đủ parties do một nguyên nhân làm hỏng generation, các bên đang chờ cùng bị buộc rời điểm hẹn bằng exception; barrier không cho phần còn lại đi tiếp như một lần trip thành công giả tạo.

Các nguyên nhân quan trọng:

- Một waiter bị **interrupt** trong lúc chờ.
- Một waiter hết **timeout** ở `await(timeout, unit)`.
- **Barrier action ném exception**.
- Ai đó gọi **`reset()`** khi đang có waiters.
- Một thread mới gọi `await` khi barrier hiện tại **đang broken**, nó sẽ nhận `BrokenBarrierException` (theo contract, với lưu ý precedence của interruption).

### Bảng trạng thái theo nguyên nhân

| Nguyên nhân | Thread trực tiếp gặp lỗi | Những thread khác đang đợi | `isBroken()` sau sự cố, trước reset |
| --- | --- | --- | --- |
| Một waiter hết timeout | `TimeoutException` | Thường `BrokenBarrierException` | `true` |
| Một waiter bị interrupt | `InterruptedException` (flag thường được xóa khi ném) | Thường `BrokenBarrierException` | `true` |
| Barrier action ném unchecked exception | Thread chạy action nhận exception gốc | `BrokenBarrierException` | `true` |
| Gọi `reset()` khi waiters đang chờ | Thread gọi reset return bình thường | Waiters nhận `BrokenBarrierException` | **`false` ngay sau reset** vì generation mới |
| Một caller mới vào barrier đã broken | `BrokenBarrierException` | Không mở generation hỏng | `true` |

**Phân biệt rõ:** `reset()` **làm hỏng generation cũ và tạo generation mới**. Do đó không có lý do `isBroken()` phải còn true **ngay sau reset**. Nhưng những waiters thuộc generation cũ vẫn nhận `BrokenBarrierException`.

Một waiter có thể đồng thời bị interrupt đúng lúc sự cố khác xảy ra và nhận `InterruptedException` thay vì `BrokenBarrierException`. JDK cho phép các interleavings như vậy; không viết test mà khẳng định mọi waiter luôn nhận đúng một loại exception khi nhiều nguyên nhân xảy ra đồng thời.

### `BrokenBarrierException` có nghĩa “lỗi ở worker này” không?

Không nhất thiết. Nó thường cho biết **một bên khác** hoặc action của cả barrier đã làm generation thất bại. Khi thấy exception này, hãy tìm **nguyên nhân đầu tiên**: worker nào timeout, ai bị interrupt, action nào ném exception, có reset đồng thời không. Không xử lý bằng cách catch rồi bỏ qua để worker tiếp tục phase như thể dữ liệu đã được tổng hợp hoàn chỉnh.

## 7. Java 17 runnable: exception trong barrier action

Ví dụ có hai parties. Barrier action luôn ném `IllegalStateException`. Thread đến cuối chạy action nên nhận exception gốc; thread còn lại nhận `BrokenBarrierException`. Chương trình thu thập counter để stdout không phụ thuộc worker nào đến cuối.

Tạo **`BarrierActionFailureDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierActionFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger actionErrors = new AtomicInteger();
        AtomicInteger brokenWaiters = new AtomicInteger();

        CyclicBarrier barrier = new CyclicBarrier(2, () -> {
            throw new IllegalStateException("action failed");
        });

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<?>> futures = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                futures.add(pool.submit(() -> {
                    try {
                        barrier.await();
                        throw new AssertionError(
                                "Action should not succeed");
                    } catch (IllegalStateException e) {
                        if (!"action failed".equals(e.getMessage())) {
                            throw e;
                        }
                        actionErrors.incrementAndGet();
                    } catch (BrokenBarrierException e) {
                        brokenWaiters.incrementAndGet();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                }));
            }

            for (Future<?> f : futures) {
                f.get(5, TimeUnit.SECONDS);
            }
            System.out.println("actionErrors=" + actionErrors.get());
            System.out.println("brokenWaiters=" + brokenWaiters.get());
            System.out.println("broken=" + barrier.isBroken());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BarrierActionFailureDemo.java
java BarrierActionFailureDemo
```

Stdout trên đường chạy bình thường:

```text
actionErrors=1
brokenWaiters=1
broken=true
```

**Lập luận:** Barrier có hai parties, vì vậy một thread tới trước sẽ chờ và một thread tới cuối sẽ chạy callback. Callback ném unchecked exception → thread cuối nhận `IllegalStateException("action failed")`; waiter còn lại được giải phóng bằng `BrokenBarrierException`; barrier ở trạng thái broken.

Nếu một lần `await()` khác được gọi trên **barrier vẫn broken**, nó cũng không mở pha mới thành công mà ném `BrokenBarrierException`. Muốn tái sử dụng sau sự cố, cần recovery và `reset` hoặc tạo barrier mới.

**Điểm rất quan trọng:** `reset()` **không sửa lỗi trong barrier action**. Nếu reset rồi hai parties tới lại, callback vẫn ném lỗi đó và barrier lại broken. Cần sửa root cause, thay implementation action hay thay barrier nếu thích hợp, không chỉ reset lặp vô hạn.

## 8. Timeout: một bên thiếu làm hỏng cả generation

Dùng timeout khi một bên có thể không đến vì I/O, queue starvation, cancellation hoặc sự cố tài nguyên. Nếu `await(300, TimeUnit.MILLISECONDS)` hết hạn mà chưa đủ parties:

1. Thread hết hạn nhận `TimeoutException`.
2. Barrier được đánh dấu **broken**.
3. Các threads khác đang chờ cùng generation được đánh thức và thường nhận `BrokenBarrierException`.
4. Những arrivals sau đó cũng không thể dùng generation broken cho tới khi reset.

**Không nhầm timeout của barrier với timeout xử lý nghiệp vụ.** Một worker có thể mất 10 giây tính toán *trước khi gọi await*; nếu tất cả các waiter khác đặt deadline 1 giây tại barrier, họ có thể timeout trước khi worker chậm đến. Thời hạn phải phản ánh tính chất phase, deadline end-to-end và downstream.

### Java 17 runnable: timeout, broken, reset, reuse

Tạo **`BarrierTimeoutRecoveryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierTimeoutRecoveryDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        AtomicInteger successfulNextGeneration = new AtomicInteger();

        try {
            Future<Boolean> lone = pool.submit(() -> {
                try {
                    barrier.await(200, TimeUnit.MILLISECONDS);
                    return false;
                } catch (TimeoutException expected) {
                    return true;
                }
            });

            boolean timedOut = lone.get(5, TimeUnit.SECONDS);
            boolean brokenAfterTimeout = barrier.isBroken();

            boolean laterWaiterRejected;
            try {
                barrier.await();
                laterWaiterRejected = false;
            } catch (BrokenBarrierException expected) {
                laterWaiterRejected = true;
            }

            barrier.reset();
            boolean brokenAfterReset = barrier.isBroken();

            List<Future<?>> reused = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                reused.add(pool.submit(() -> {
                    try {
                        barrier.await(5, TimeUnit.SECONDS);
                        successfulNextGeneration.incrementAndGet();
                    } catch (Exception e) {
                        throw new IllegalStateException(e);
                    }
                }));
            }
            for (Future<?> f : reused) {
                f.get(10, TimeUnit.SECONDS);
            }

            System.out.println("timedOut=" + timedOut);
            System.out.println("brokenAfterTimeout=" + brokenAfterTimeout);
            System.out.println(
                    "laterWaiterRejected=" + laterWaiterRejected);
            System.out.println("brokenAfterReset=" + brokenAfterReset);
            System.out.println("successfulNextGeneration="
                    + successfulNextGeneration.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BarrierTimeoutRecoveryDemo.java
java BarrierTimeoutRecoveryDemo
```

Stdout khi chương trình hoàn thành bình thường:

```text
timedOut=true
brokenAfterTimeout=true
laterWaiterRejected=true
brokenAfterReset=false
successfulNextGeneration=2
```

**Vì sao kết quả không phụ thuộc sleep/scheduling?**

- Generation đầu có **2 parties nhưng chỉ 1 thread `await`**, do đó không thể trip thành công. Nó sẽ timeout sau thời gian được cấu hình.
- Main **chờ Future** hoàn tất rồi mới đọc `isBroken`, tránh race với thời điểm timeout.
- Một lời `await()` trên barrier broken ném `BrokenBarrierException` **ngay**, không chờ đủ parties.
- `reset()` tạo generation mới, `isBroken=false`.
- Hai tasks mới được gửi vào executor 2 workers, gọi `await` trong cùng generation mới nên có thể trip thành công. Main chờ cả hai futures trước khi in.
- Deadline 200 ms trong demo phục vụ **đường timeout có chủ đích**, không chứng minh một worker luôn được scheduler chạy chính xác ở mốc 200 ms.

Cần lưu ý `await()` trên main khi barrier broken sẽ ném theo hợp đồng; nếu main tình cờ bị interrupt sẵn, precedence exception có thể khác. Chương trình giả định main không bị interrupt từ nguồn ngoài trong lúc test bình thường.

## 9. Interrupt và chính sách all-or-none

Khi một waiter `await()` bị interrupt, nó nhận `InterruptedException`, và **trạng thái interrupt được xóa khi exception được ném** theo contract. Barrier thế hệ đó bị broken; các bên đang chờ khác thường nhận `BrokenBarrierException`.

Ví dụ **snippet**:

```java
try {
    barrier.await();
    useCompletedPhase();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    stopThisWorker();
} catch (BrokenBarrierException e) {
    abortThisPhase();
}
```

Các methods `useCompletedPhase`, `stopThisWorker`, `abortThisPhase` là nghiệp vụ của ứng dụng. Nếu method không có khả năng propagate `InterruptedException` ra ngoài, sau khi catch cần thường **restore interrupt flag** rồi **thoát đường xử lý**, thay vì nuốt cờ và chờ lại ngay.

Một người bị interrupt có thể khiến **cả thế hệ barrier hỏng**, vì vậy không thể để những parties khác cứ tính tiếp và giả định có kết quả đầy đủ. Nếu workflow cần partial results, phải thiết kế hợp đồng riêng cho việc chấp nhận thiếu worker.

### Không nuốt `BrokenBarrierException`

```java
try {
    barrier.await();
} catch (BrokenBarrierException ignored) {
    // SAI nếu tiếp tục coi phase đã hoàn thành.
}
continueUsingAllPartitions();
```

Đây là snippet **sai về business semantics**; `continueUsingAllPartitions` là method minh họa. Khi barrier broken, một hoặc nhiều participants chưa đến hoặc action thất bại. Những kết quả cần “đủ mọi partition” chưa được xác nhận. Người điều phối nên abort/retry/compensate theo generation, chứ không bỏ qua exception.

### Có nên auto-reset trong catch của mỗi waiter?

**Không.** Nếu tất cả parties đồng thời catch `BrokenBarrierException` rồi mỗi thread tự gọi `reset()`, sẽ xảy ra reset races: thread A vừa tham gia generation mới có thể bị thread B reset làm hỏng tiếp. Recovery cần **một coordinator/leader** theo protocol rõ, hoặc tạo barrier mới cho một nhóm workers được tạo/điều phối lại.

## 10. `reset()` thực sự làm gì?

Javadoc mô tả `reset()` đưa barrier về trạng thái ban đầu. Điều này có hai ý nghĩa riêng:

**A. Nếu barrier hiện đang broken:** reset kết thúc thế hệ cũ và mở một thế hệ mới **không broken** để một nhóm parties có thể chờ lại.

**B. Nếu barrier đang có waiters, chưa đủ parties:** reset **kết thúc thế hệ chờ ấy bất thường**. Những waiters đó nhận `BrokenBarrierException`; sau reset barrier đã sẵn sàng cho **một lượt đợi khác**. Điều này không giống `notifyAll` “cho qua thành công”.

```text
Generation G0, parties=3:
    Thread A -> await (WAITING)
    Thread B -> await (WAITING)
    Thread C -> chưa đến

Coordinator -> reset()

    A -> BrokenBarrierException (G0 invalid)
    B -> BrokenBarrierException (G0 invalid)
    G1 mới: isBroken() == false, waiting == 0

Sau khi coordinator xử lý/đồng bộ lại:
    A/B/C có thể cùng await() ở generation G1
```

**Không gọi reset ở mọi pha**: CyclicBarrier tự động chuyển generation sau trip thành công. Reset chủ yếu phục vụ **recovery/abandon** sau sự cố, và phải phối hợp để không có parties cũ lẫn parties mới.

### Cẩn thận với “reset nghĩa là phục hồi ngay mọi task”

Reset chỉ thay trạng thái **barrier**, không:

- Khởi động lại worker bị chết.
- Rollback side effects trước khi bị broken.
- Hoàn thành barrier action từng ném exception.
- Tự sinh parties còn thiếu.
- Hủy mọi future/task đã submit.
- Đặt lại state nghiệp vụ và dữ liệu của các worker về một snapshot đồng bộ.
- Chữa lỗi do executor có ít workers hơn số parties cần đợi.

Do đó nếu có lỗi nghiêm trọng, **tạo barrier mới** có thể dễ suy luận hơn reset tại chỗ, nhất là khi nhiều threads đã đi vào các nhánh recover khác nhau.

## 11. Java 17 runnable: reset khi có hai parties đang đợi

Ví dụ này có một barrier cần ba parties, nhưng chỉ submit hai waiters đầu. Main đợi tới khi **`getNumberWaiting()==2`** (với deadline) rồi gọi reset. Hai waiters nhận `BrokenBarrierException`. Sau khi cả hai Future đã hoàn thành, ta submit ba waiters mới để chứng minh barrier generation mới được dùng thành công.

Tạo **`BarrierResetWaitersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class BarrierResetWaitersDemo {
    public static void main(String[] args) throws Exception {
        CyclicBarrier barrier = new CyclicBarrier(3);
        AtomicInteger releasedByReset = new AtomicInteger();
        AtomicInteger nextGenerationSuccess = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(3);

        try {
            List<Future<?>> oldWaiters = new ArrayList<>();
            for (int i = 0; i < 2; i++) {
                oldWaiters.add(pool.submit(() -> {
                    try {
                        barrier.await();
                        throw new AssertionError(
                                "Old generation must not trip");
                    } catch (BrokenBarrierException expected) {
                        releasedByReset.incrementAndGet();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(e);
                    }
                }));
            }

            long deadline =
                    System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
            while (barrier.getNumberWaiting() != 2) {
                if (System.nanoTime() >= deadline) {
                    throw new IllegalStateException(
                            "Two waiters not observed");
                }
                Thread.onSpinWait();
            }

            barrier.reset();
            for (Future<?> f : oldWaiters) {
                f.get(5, TimeUnit.SECONDS);
            }

            boolean brokenAfterReset = barrier.isBroken();

            List<Future<?>> nextWaiters = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                nextWaiters.add(pool.submit(() -> {
                    try {
                        barrier.await(5, TimeUnit.SECONDS);
                        nextGenerationSuccess.incrementAndGet();
                    } catch (Exception e) {
                        throw new IllegalStateException(e);
                    }
                }));
            }

            for (Future<?> f : nextWaiters) {
                f.get(10, TimeUnit.SECONDS);
            }

            System.out.println(
                    "releasedByReset=" + releasedByReset.get());
            System.out.println(
                    "brokenAfterReset=" + brokenAfterReset);
            System.out.println(
                    "nextGenerationSuccess="
                    + nextGenerationSuccess.get());
            System.out.println(
                    "waitingNow=" + barrier.getNumberWaiting());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac BarrierResetWaitersDemo.java
java BarrierResetWaitersDemo
```

Stdout nếu hoàn thành bình thường trong deadline:

```text
releasedByReset=2
brokenAfterReset=false
nextGenerationSuccess=3
waitingNow=0
```

**Phân tích:**

- G0 đòi 3 parties nhưng chỉ có 2 threads gọi `await` nên cả hai chờ.
- Main dùng `getNumberWaiting()==2` làm **test checkpoint có kiểm soát** và gọi `reset` sau khi biết cả hai đang đợi. Hàm getter chủ yếu phục vụ debug/assertions; **không dùng snapshot này làm giao thức điều phối production** giữa nhiều resetters.
- Hai waiters G0 không được coi là thành công: mỗi người nhận `BrokenBarrierException` rồi return.
- Main đợi hai Future cũ hoàn tất **trước khi** submit ba tasks mới vào G1; tránh trộn generation trong bài test.
- G1 có đủ ba workers và tripped thành công. `getNumberWaiting()==0` sau khi cả ba futures đã hoàn tất.
- `reset()` không làm parties đổi từ 3 thành 2; G1 vẫn cần 3 arrivals.

**Lưu ý:** trong production, khi một coordinator quyết định reset do lỗi, cần có quy tắc ai được reset và cách các workers tái đồng bộ. Một vòng `while (getNumberWaiting()<N)` dùng cho giám sát không thể thay thế một barrier/protocol an toàn khi các threads khác có thể thay generation đồng thời.

## 12. Khi nào `getNumberWaiting()` và `isBroken()` hữu ích?

Hai getters có ý nghĩa quan sát:

```java
int configured = barrier.getParties();
int waiting = barrier.getNumberWaiting();
boolean broken = barrier.isBroken();
```

Đây là snippet (cần biến `barrier` được định nghĩa). Chúng có thể giúp xác định:

- Barrier đang đợi bao nhiêu parties?
- Có bao nhiêu bên còn thiếu cho thế hệ hiện tại?
- Thế hệ hiện tại đã broken do timeout/interrupt/action failure chưa?
- Sau reset có đang ở generation mới hay không?

**Nhưng:** đọc ba getters lần lượt **không phải snapshot nhất quán nguyên tử**. Workers có thể vừa trip hoặc reset giữa các lần đọc. `getNumberWaiting()` được Javadoc định hướng **debugging và assertions**, không phải điều kiện business để quyết định reset khi nhiều actor có thể chạy đồng thời.

Một barrier đang chờ có thể hoàn toàn bình thường (pha tính toán chưa đủ parties). Đừng tuyên bố deadlock chỉ vì thấy `WAITING` trên stack. Cần theo dõi ai chưa đến, queue/executor có worker không, I/O có timeout không và flow có exit/cancellation không.

### Ví dụ pool quá nhỏ

Nếu cấu hình `newFixedThreadPool(2)` nhưng submit **3 tasks** mỗi task gọi `barrier.await()` trên barrier có `parties=3`, hai worker đầu có thể chiếm hết threads và đợi bên thứ ba đang nằm trong queue **không bao giờ được chạy**. Đây là **thread-starvation deadlock** do sizing/graph phụ thuộc, không phải lỗi của `reset`.

Giải pháp có thể là pool đủ worker đồng thời, mô hình non-blocking/phased khác, hoặc tổ chức execution sao cho parties không phải chặn toàn bộ khả năng chạy của parties còn lại. Timeout chỉ là cơ chế fail-fast chứ không sửa được thiết kế thiếu capacity.

## 13. Action nặng hoặc blocking có vấn đề gì?

Barrier action chạy trên **thread đến cuối cùng** và tất cả parties khác đang đợi nó hoàn tất. Nếu action:

- Gọi I/O rất lâu.
- Thực hiện DB transaction nặng.
- Chờ `Future.get` của task cần một trong các worker đang ở barrier.
- Lấy mutex đang bị giữ bởi thread ở ngoài hoặc trong một chu trình chờ.
- Gọi lại `barrier.await` theo một protocol không hợp lệ.
- Ném unchecked exception do bug.

thì toàn pha có thể bị trì hoãn hoặc thất bại. Callback nên **ngắn, xác định và có tài nguyên/timeout rõ**. Nếu aggregation nặng, cân nhắc phân vùng kết quả, gom từng phần trước barrier hoặc chuyển xử lý sang một phase có người điều phối riêng; nhưng phải giữ điều kiện visibility và phase ownership.

**Một điểm tinh vi:** các waiter có timeout không nhất thiết có thể “phá” ngay một barrier action đang chạy dài nếu action đang giữ cơ chế đồng bộ bên trong của barrier; hợp đồng không cho phép dùng `await(timeout)` như một nút cưỡng chế ngắt bất kỳ callback nào. Đừng đặt callback có I/O vô thời hạn rồi tin một timeout ở caller sẽ dừng được nó.

### Action failure và cleanup

Barrier action thất bại có thể làm generation broken, nhưng worker trong partition khác có thể đã nắm resource hoặc có side effects trước khi chờ. Hãy:

1. Đóng resource per-task trong `finally`/`try-with-resources`.
2. Không commit kết quả incomplete sau khi nhận `BrokenBarrierException`.
3. Ghi log nguyên nhân đầu tiên (timeout/interrupt/action failure).
4. Chọn retry/abort policy tại cấp coordinator.
5. Nếu retry, tạo state mới hoặc rollback/compensate partial writes theo business contract.

Một action có side effect không idempotent (gửi payment/email) cần đặc biệt cẩn trọng nếu ứng dụng retry phase: một generation bị lỗi giữa chừng không tạo exactly-once semantics.

## 14. Recovery tốt hơn reset vô điều kiện

Một quy trình phục hồi được cân nhắc:

**Bước 1: Stop accepting work vào generation cũ.** Đưa phase vào trạng thái failed/cancelled ở cấp ứng dụng, ví dụ một `AtomicReference<State>`/owner coordinator.

**Bước 2: Collect failures.** Xác định bên nào bị interrupt, timeout, action nào thất bại và tasks nào còn chạy. Không chỉ bắt `BrokenBarrierException` ở một worker rồi suy ra nguyên nhân.

**Bước 3: Drain/terminate old work.** Hủy hợp tác các workers còn đang xử lý generation cũ; đợi cleanup phù hợp, tránh state cũ và mới ghi chung dữ liệu.

**Bước 4: Reset hoặc replace.** Nếu group parties/contract không đổi và mọi actor đã tái đồng bộ, có thể `reset()`. Khi generation cũ đã phức tạp, tạo một `CyclicBarrier` mới và công bố an toàn cho các workers mới thường rõ ràng hơn.

**Bước 5: Prepare new state.** Phân vùng dữ liệu và biến tổng hợp cho generation mới, không tái sử dụng partial results hỏng.

**Bước 6: Restart only with full participant plan.** Đảm bảo đủ parties sẽ có cơ hội tới `await`; tránh submit các blocking workers vào pool không đủ capacity.

**Bước 7: Verify success.** Đếm các phase hoàn tất và business outputs; không chỉ nhìn `isBroken()==false`, vì một barrier chưa có ai tới cũng false.

### Đừng reset tự động mỗi khi thấy broken

Một vòng vô hạn kiểu:

```java
for (;;) {
    try {
        barrier.await();
        break;
    } catch (BrokenBarrierException e) {
        barrier.reset(); // SAI nếu mỗi worker tự reset.
    }
}
```

là **snippet sai**; các workers có thể liên tục reset generation mới của nhau, mất khả năng tiến triển. Nếu thực sự muốn retry, hãy có một coordinator độc quyền quyết định, stop/restart protocol và deadline.

## 15. Barrier action so với logic sau `await()`

Hai cách chỉ khác nhau vài dòng nhưng khác contract:

### Cách A — barrier action

```java
CyclicBarrier barrier = new CyclicBarrier(
        parties, () -> publishAggregate());
```

Đây là snippet; action **xong trước** khi workers được phép đi tiếp. Có happens-before từ writes trước await tới action rồi tới các operations sau successful await.

### Cách B — leader sau await

```java
int index = barrier.await();
if (index == 0) {
    publishAggregate();
}
```

Đây là snippet; **các workers khác đã được giải phóng** khi leader làm aggregate. Nếu các workers có thể viết đè partial state cho pha mới, leader có thể đọc sai. Cần thêm một barrier thứ hai sau aggregation, chuyển ownership/immutable snapshot, hoặc đặt aggregate trong barrier action.

**Không dùng cùng một object barrier để tạo “thêm barrier thứ hai” một cách ngẫu nhiên** nếu các parties có số lượt `await` không thống nhất: thế hệ thứ hai có thể bị trộn với thế hệ tiếp theo của một worker. Thiết kế phase protocol phải rõ cho mọi participant.

## 16. CyclicBarrier so với CountDownLatch và Phaser

| Thuộc tính | `CyclicBarrier` | `CountDownLatch` | `Phaser` |
| --- | --- | --- | --- |
| Mục đích | N parties cùng gặp ở điểm hẹn | Một hoặc nhiều threads đợi count về 0 | Đồng bộ nhiều pha, số parties có thể thay đổi |
| Tái sử dụng sau thành công | **Có**, tự mở generation mới | **Không**, latch một lần | **Có**, chuyển phase |
| Đăng ký/hủy participant | `parties` cố định | Initial count cố định | `register`/`arriveAndDeregister` |
| Action khi hoàn tất pha | Constructor `Runnable barrierAction` | Không có callback sẵn | Có thể override `onAdvance` |
| Failure do timeout/interrupt waiter | Generation broken, các waiter khác nhận lỗi | Một waiter bị interrupt không tự “break” latch | Semantics khác; cần thiết kế termination/error riêng |
| Reset | Có, **phá generation cũ nếu đang chờ** | Không có reset | Không phải cùng mô hình reset; `forceTermination` và phase controls |
| Cách chờ | `await` của các parties | `await` trên latch, `countDown` riêng | `arriveAndAwaitAdvance`/`awaitAdvance` |
| Nên dùng khi | Nhóm cố định tính toán theo vòng | Một lần khởi động/hoàn thành | Nhiều pha với participants động |

**CyclicBarrier khác CountDownLatch ở chỗ parties đi qua barrier cùng nhau**, còn latch có thể được `countDown()` trước khi bất kỳ thread nào `await()` và sau khi count về 0, latch luôn mở.

**Phaser khác CyclicBarrier** khi một số workers có thể đăng ký thêm hoặc rút khỏi vòng. Không cố “rút party” bằng cách reset CyclicBarrier: `getParties` vẫn giữ nguyên.

Nếu bài toán chỉ là đợi ba Futures hoàn thành **một lần**, `CompletableFuture.allOf(...)` hoặc `CountDownLatch` thường đơn giản hơn CyclicBarrier.

## 17. Có nên dùng barrier cho I/O-bound workload?

`CyclicBarrier` phù hợp hơn khi nhóm workers biết chắc cần **đồng bộ từng phase**. Với I/O-bound workload:

- Một API chậm có thể khiến mọi party chờ theo “slowest participant”.
- Nhiều platform threads chờ sẽ chiếm worker slots, dù CPU rảnh.
- Nếu một request timeout/hủy thì cả generation có thể broken.
- Nếu executor không đủ workers để cùng tham gia, có starvation.
- Một phần output đã được tạo trước barrier vẫn cần cleanup khi generation failed.

Trong hệ thống xử lý streams/independent requests, barrier có thể làm giảm throughput nếu ép các công việc không liên quan phải “đợi người chậm nhất”. Cân nhắc asynchronous composition, queues, futures hoặc phaser tùy mô hình phụ thuộc. **Đừng dùng barrier chỉ để tạo cảm giác “có synchronization”**.

### Virtual threads từ Java 21

Virtual threads vẫn tuân thủ Java Memory Model và có thể chờ trên synchronization primitives, nhưng `CyclicBarrier` vẫn có **số parties cố định và hợp đồng all-or-none**. Dùng virtual threads không làm một bên bị thiếu tự xuất hiện, không ngăn barrier action ném exception và không thay đổi semantics `reset()`.

Các demo trong bài chạy bằng Java 17, không yêu cầu virtual-thread API.

## 18. Debug một hệ thống đứng ở barrier

Khi thấy thread dump có nhiều tasks ở `CyclicBarrier.await`:

1. **Số parties được yêu cầu?** `getParties()` là bao nhiêu?
2. **Bao nhiêu thread đang đợi?** `getNumberWaiting()`, đọc như snapshot/debug.
3. **Party còn thiếu ở đâu?** Đang compute, chờ I/O, queue executor, bị exception hay đã shutdown?
4. **Executor đủ capacity?** Có N−1 workers chờ và party N nằm trong queue của same pool không?
5. **Có failure trước khi await?** Worker ném exception rồi chết mà không báo coordinator, các bên khác có thể chờ mãi nếu không timeout.
6. **Barrier action có đang chạy?** Callback nặng/lock/I/O hay ném exception?
7. **`isBroken()` là gì?** Nếu true, tìm root cause và không cứ await tiếp.
8. **Có reset race?** Nhiều threads tự reset khi catch broken hoặc manager reset khi workers đang lẫn pha?
9. **Có timeout/cancellation policy?** Nếu không, một bên thiếu có thể treo cả nhóm.
10. **Dữ liệu phase có ownership không?** Có worker sửa partition mới trước khi action đọc xong không?
11. **Lấy nhiều snapshot/JFR**: tránh kết luận từ một thread dump đơn lẻ.
12. **Đối chiếu epoch/generation** bằng state do ứng dụng quản lý; CyclicBarrier không public generation identifier.

Khi instrument, có thể gắn một `phaseId`/runId do ứng dụng tự tạo vào logging. Không lấy `arrivalIndex` làm ID generation hoặc worker identity; nó chỉ là thứ tự đến trong một generation.

## 19. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Nghĩ barrier action chạy trên thread riêng | Sizing và latency sai | Action do **last arrival** chạy |
| Nghĩ action chạy khi chỉ N−1 parties đến | Callback không bao giờ chạy | Đảm bảo đủ parties hoặc timeout |
| Gọi action sau `await` và tưởng mọi bên vẫn bị giữ | Worker khác có thể bắt đầu phase sau | Đặt aggregate vào barrier action |
| Quên `await` ở một branch | Parties còn lại chờ mãi | Cùng protocol mọi paths, timeout |
| Cấp pool size nhỏ hơn parties mà tất cả đều block | Thread-starvation deadlock | Đủ execution capacity hoặc đổi thiết kế |
| Bắt `BrokenBarrierException` rồi tiếp tục bình thường | Dùng incomplete phase results | Abort/recover rõ |
| Mỗi waiter tự gọi `reset` | Reset race, có thể liên tục break | Một coordinator/leader |
| Reset khi đang có waiters và mong họ thành công | Họ nhận `BrokenBarrierException` | Phân biệt abandon với trip |
| `isBroken()==false` là bằng chứng pha hoàn tất | Một barrier mới cũng false | Đo output và completion state |
| Nghĩ reset sửa callback lỗi | Action cũ vẫn ném | Sửa root cause hoặc thay barrier |
| Action ném exception nhưng chỉ log ở waiter khác | Mất lỗi gốc | Collect failure ở last arrival |
| Bỏ qua `InterruptedException` | Tác vụ không dừng/đi sai phase | Propagate hoặc restore + exit |
| Nghĩ timeout ở await có thể kill callback blocking | Action có thể chặn lâu | Timeouts ở resource/callback |
| Dùng `getNumberWaiting` làm transactional state | Getter chỉ snapshot | Ứng dụng có state/ownership riêng |
| Dùng `arrivalIndex==0` như worker cố định | Worker đến cuối thay theo lịch | Không gắn logic vào ID worker |
| `reset` để giảm `getParties` | Số parties không đổi | Phaser/thiết kế mới |
| Đặt side effects không idempotent trong action rồi retry bừa | Có thể phát tác dụng phụ trùng | State machine/idempotency |
| Suy ra barrier bảo vệ mọi mutable field | Chỉ có HB theo protocol | Quy định ownership, không race ngoài pha |

## 20. Kiểm thử các interleavings cần thiết

Một bộ test đủ tốt không chỉ in một phase thành công. Nên có:

1. Barrier 1 party: action có chạy khi party duy nhất `await`?
2. 2–3 parties, nhiều pha thành công, action count đúng mỗi pha.
3. Một party tới trễ nhưng **trước deadline**, không broken.
4. Một party **không tới**, timed await ném `TimeoutException`, `isBroken=true`.
5. Một waiter bị interrupt, các waiter khác rời bằng `BrokenBarrierException` theo contract.
6. Action ném unchecked exception; last arrival nhận lỗi gốc, các waiters còn lại nhận broken.
7. Reset khi đang có waiters; họ bị broken dù sau reset `isBroken=false`.
8. Reset sau lỗi rồi **đủ N parties mới** dùng lại thành công.
9. Nhiều phases với worker IDs khác nhau nhận arrival index 0; **không assert thứ tự thread**.
10. Dữ liệu phase được tổng hợp chính xác trong action trước release.
11. Executor thiếu worker: phát hiện deadlock/starvation bằng timeout test.
12. Race giữa cancel/reset/late arrival: không lẫn dữ liệu giữa các generations.
13. Callback chặn lâu: coordinator phát hiện và có recovery ngoài barrier.
14. Cleanup resource trong `finally` khi await ném exception.
15. Hệ thống nhiều generations: business output không bị ghi đè/trộn phase.

### Không dùng `Thread.sleep` làm bằng chứng scheduling

`Thread.sleep(10)` không bảo đảm thread A đã vào `await` trước thread B hay callback đã hoàn tất. Để kiểm thử:

- Dùng `CountDownLatch` cho checkpoints trước khi submit/await.
- Dùng `Future.get(timeout)` cho deadline tránh treo.
- Với reset test, kiểm tra `getNumberWaiting` **chỉ khi đã cô lập mọi actor** và có deadline.
- Tổng hợp counters rồi main in sau `Future.get`, không phụ thuộc thứ tự log từ nhiều workers.
- Không để các tests tạo thread pools không shutdown.

## 21. Câu hỏi tự kiểm tra

**1. Barrier action chạy trên thread nào?** Thread đến **cuối cùng** tại barrier của generation đó, trước khi các parties khác được release.

**2. Barrier action có chạy nếu một party timeout trước khi đủ N?** Không theo đường trip thành công; generation broken, các parties đang chờ nhận exception.

**3. `await()` trả `0` nghĩa gì?** Đây là party đến cuối cùng trong generation ấy, không phải worker có ID 0.

**4. Gọi `reset()` sau mỗi pha thành công có cần thiết không?** Không. CyclicBarrier tự tái sử dụng sau successful trip.

**5. Reset khi hai waiters đang chờ thì họ được đi tiếp bình thường không?** Không. Họ nhận `BrokenBarrierException`; reset tạo generation mới.

**6. Sau reset, `isBroken()==false` có nghĩa generation cũ thành công?** Không. Nó chỉ nói generation mới đang không broken.

**7. Action ném `IllegalStateException` thì thread nào nhận nó?** Thread đến cuối chạy action; các parties khác đang chờ nhận `BrokenBarrierException`.

**8. Nếu một waiter bị interrupt, chỉ nó bị ảnh hưởng?** Không. Generation bị broken và các waiters khác thường nhận broken exception.

**9. `await(timeout,unit)` timeout có tự reset barrier không?** Không. Barrier broken cho đến khi có recovery/reset hoặc thay mới.

**10. `getNumberWaiting()` có là điều kiện đồng bộ mạnh không?** Không; chủ yếu là debugging/assertions snapshot, có race khi nhiều actors thay đổi trạng thái.

**11. Nếu pool có 2 threads mà barrier đòi 3, submit 3 blocking tasks thì sao?** Hai tasks đầu có thể chiếm worker đợi task thứ ba mãi ở queue; phải thiết kế execution capacity/protocol khác.

**12. Khi nào cần barrier action thay `if (await()==0)`?** Khi aggregate/phân phối state **phải hoàn tất trước** khi bất kỳ worker nào chuyển sang pha sau.

**13. `reset` có thay đổi `getParties` không?** Không. Muốn số participants động hãy cân nhắc Phaser.

**14. Barrier action có nghĩa mọi field shared đều thread-safe?** Không. Chỉ có memory consistency theo happens-before của protocol; concurrent writes ngoài vùng/phase vẫn có thể race.

**15. Có nên cho mọi thread tự reset trong catch `BrokenBarrierException`?** Không. Cần một coordinator và tái đồng bộ rõ ràng để tránh reset races.

**16. `CyclicBarrier` có giống CountDownLatch không?** Không. Barrier chờ các parties cùng đến và tái sử dụng; latch có counter một chiều, không reset.

**17. `isBroken()` true nghĩa là barrier không dùng lại được mãi mãi?** Không. Có thể reset theo protocol hoặc tạo barrier mới; nhưng nếu lỗi nguyên nhân còn tồn tại, sẽ broken lần nữa.

**18. Có thể dùng reset để thay thế failure compensation không?** Không. Nó không rollback side effects hay cleanup I/O của các worker.

## 22. Checklist thiết kế production

- Đã định nghĩa **parties và generation** theo workflow chưa?
- Mọi worker có chắc gọi `await` đúng **một lần mỗi phase** không?
- Pool/executor có **đủ khả năng chạy các parties đồng thời** không?
- Barrier action có **ngắn, đúng dữ liệu và không blocking vô thời hạn** không?
- Shared data trước `await` có ownership rõ và được aggregate **trước release** không?
- Đã hiểu `arrivalIndex==0` là **last arrival**, không phải worker cố định?
- `InterruptedException`/`TimeoutException`/`BrokenBarrierException` có được xử lý riêng và đúng policy không?
- Có thể một task ném exception **trước await** khiến các parties khác mắc kẹt không? Có timeout/cancellation?
- Nếu action thất bại, coordinator có bắt được **exception gốc** không?
- Có **một owner duy nhất cho reset/recovery** không, hay mọi worker tự reset?
- Recovery có chờ old tasks/cleanup xong trước khi dùng generation mới không?
- `reset` có được dùng chỉ khi thực sự cần? Có tránh reset ở healthy phase?
- Có phân biệt `isBroken=false` với **business phase completed** không?
- Có xác định side effects của action có **idempotent** khi retry không?
- Có cần dynamic participants? Nếu có, Phaser có thích hợp hơn không?
- Có load/stress tests với timeout, interrupt, broken action, reset và nhiều pha không?
- Có đo worker starvation, queue, waiting time và callback duration không?

**Kết luận:** `CyclicBarrier` tạo một điểm hẹn lặp lại cho nhóm cố định. **Barrier action** chạy một lần trên thread đến cuối và tạo ranh giới visibility trước khi parties được mở. **Broken** biểu thị rằng cả generation đồng bộ không còn hợp lệ do timeout, interrupt hoặc action failure; waiters còn lại phải nhận lỗi thay vì tiếp tục với dữ liệu thiếu. **Reset** loại bỏ generation cũ, tạo generation mới và làm các waiters hiện có ném `BrokenBarrierException`; nó không tự khôi phục business state, worker hay callback. Thiết kế đúng phải quản lý đầy đủ participants, action, timeouts, cancellation, recovery owner và dữ liệu theo phase.

### Tài liệu tham khảo

- Oracle Java SE 17 API: [CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html)
- Oracle Java SE 17 API: [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html)
- Oracle Java SE 17 API: [Phaser](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Phaser.html)