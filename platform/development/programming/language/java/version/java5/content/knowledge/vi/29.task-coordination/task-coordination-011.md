# Chờ có thời hạn để tránh phụ thuộc vô hạn

## 1. Chờ là một sự phụ thuộc

Một tác vụ có thể cần đợi tác vụ khác tính kết quả, một giấy phép tài nguyên được trả hoặc đủ nhóm đến điểm hội tụ.

Nếu điều kiện ấy không bao giờ xảy ra, lệnh chờ không thời hạn có thể giữ luồng và tài nguyên mãi:

```text
A đợi B
B đã lỗi / không được chạy / đang đợi tài nguyên A giữ
A không còn đường tự thoát
```

**Chờ có thời hạn (timed wait)** đặt một giới hạn cho lần chờ: nếu chưa đạt điều kiện trong thời gian cho phép, chương trình đi theo nhánh hết hạn thay vì mặc định tiếp tục phụ thuộc vô hạn.

Thời hạn không sửa nguyên nhân deadlock hoặc lỗi tác vụ. Nó tạo cơ hội phát hiện tình huống, giải phóng những gì mình sở hữu và chuyển sang từ chối, hủy, trả kết quả một phần hoặc báo lỗi.

Bài này dùng các API ổn định còn phù hợp trên Java hiện đại. Các ví dụ chạy với Java 17+.

## 2. Ba khái niệm cần tách riêng

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Timeout | Khoảng chờ tương đối của một lần gọi | Đợi giấy phép tối đa 200 ms |
| Deadline | Mốc phải kết thúc một thao tác theo chính sách | Toàn bộ yêu cầu có ngân sách 1 giây |
| Cancellation | Yêu cầu không tiếp tục công việc | Gửi ngắt tới tác vụ đang chạy |

Một lần `Future.get(200, MILLISECONDS)` hết hạn không đồng nghĩa tác vụ được Future đại diện đã bị hủy. Tương tự, kết thúc lần đợi giấy phép không có nghĩa chủ tài nguyên đã trả tài nguyên.

Deadline của thao tác tổng thể phải tính cả thời gian đã tiêu ở những bước trước. Nếu mỗi bước đều được cấp lại toàn bộ timeout, tổng thời gian có thể vượt xa ngân sách ban đầu.

## 3. Mỗi API báo hết hạn theo cách khác nhau

| Nhu cầu | Lời gọi có thời hạn | Dấu hiệu không đạt điều kiện đúng hạn |
| --- | --- | --- |
| Đợi đủ tín hiệu | CountDownLatch.await(t, unit) | Trả false |
| Lấy giấy phép | Semaphore.tryAcquire(t, unit) | Trả false |
| Đợi đủ nhóm | CyclicBarrier.await(t, unit) | TimeoutException; thế hệ có thể bị phá vỡ |
| Lấy kết quả tác vụ | Future.get(t, unit) | TimeoutException |
| Lấy khóa có sở hữu | Lock.tryLock(t, unit) | Trả false |
| Lấy phần tử hàng đợi | BlockingQueue.poll(t, unit) | Trả null |

Phải đọc đúng hợp đồng từng phương thức. Không dùng một mẫu “không ném ngoại lệ tức là thành công” cho các API trả boolean hoặc null.

Ví dụ với latch:

```java
boolean completed = done.await(500, TimeUnit.MILLISECONDS);
if (!completed) {
    // Đi theo nhánh chưa nhận đủ tín hiệu.
    return;
}
// Chỉ xử lý dữ liệu cần đủ tín hiệu sau khi đã xác nhận completed.
```

Đây là đoạn minh họa trong một phương thức, cần các biến/import và xử lý `InterruptedException` tương ứng. [CountDownLatch](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html) phân biệt rõ await thành công và hết thời gian.

Với semaphore:

```java
boolean acquired = slots.tryAcquire(500, TimeUnit.MILLISECONDS);
if (!acquired) {
    return;
}
try {
    useResource();
} finally {
    slots.release();
}
```

`useResource()` là hàm nghiệp vụ minh họa. Chỉ trả giấy phép nếu thật sự lấy được. Hết hạn khi chưa được cấp giấy phép không tạo ra quyền gọi `release()`.

## 4. Không bỏ qua ngắt luồng và lỗi tác vụ

Một lần đợi có thể kết thúc vì nhiều nguyên nhân khác nhau:

- Điều kiện đã đạt.
- Thời hạn đã hết.
- Luồng chờ bị ngắt.
- Tác vụ được đợi kết thúc với lỗi.
- Tác vụ bị hủy.
- Công cụ phối hợp chuyển sang trạng thái lỗi.

Với `Future.get(timeout, unit)`:

| Kết quả | Cách hiểu |
| --- | --- |
| Trả giá trị | Đã lấy được kết quả |
| TimeoutException | Lần đợi chưa lấy được kết quả đúng hạn |
| InterruptedException | Luồng đang đợi bị ngắt |
| ExecutionException | Tác vụ kết thúc với lỗi; xem nguyên nhân |
| CancellationException | Future đã bị hủy |

Không gộp mọi ngoại lệ thành “timeout”. Phân biệt giúp bên gọi chọn đúng phản ứng và giúp quan sát hệ thống phản ánh đúng nguyên nhân.

Nếu phương thức không thể truyền tiếp `InterruptedException`, thông thường nên khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi kết thúc/chuyển nhánh hủy phù hợp. Bắt rồi tiếp tục như đã đợi thành công sẽ phá giao thức điều phối.

## 5. Thí nghiệm: Future hết thời gian đợi nhưng tác vụ vẫn chưa dừng

Chương trình giữ tác vụ tại một latch chưa mở. Main thử lấy kết quả với thời hạn bằng 0, chắc chắn chưa thể có kết quả. Sau đó main chủ động yêu cầu hủy và đợi tín hiệu xác nhận tác vụ đã rời phần chạy.

Lưu thành `TimedWaitCancellationDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimedWaitCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch gate = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean observedInterrupt = new AtomicBoolean();

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    gate.await();
                    return "completed";
                } catch (InterruptedException e) {
                    observedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    throw e;
                } finally {
                    exited.countDown();
                }
            });

            if (!started.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("task did not start");
            }

            try {
                future.get(0, TimeUnit.NANOSECONDS);
            } catch (TimeoutException e) {
                System.out.println("Wait timed out: true");
            }

            System.out.println("Task exited at timeout: "
                    + (exited.getCount() == 0));
            System.out.println("Cancellation accepted: "
                    + future.cancel(true));

            if (!exited.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("task did not exit");
            }
            System.out.println("Interrupt observed: "
                    + observedInterrupt.get());
        } finally {
            gate.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac TimedWaitCancellationDemo.java
java TimedWaitCancellationDemo
```

Stdout khi chương trình chạy bình thường, không có ngắt từ bên ngoài:

```text
Wait timed out: true
Task exited at timeout: false
Cancellation accepted: true
Interrupt observed: true
```

Không dùng `Thread.sleep` để mong tác vụ chưa xong: latch `gate` xác định điều kiện ấy một cách chủ động. Timeout bằng 0 chỉ phục vụ kiểm tra ngay trong thí nghiệm, không phải cấu hình chờ thực tế.

`cancel(true)` yêu cầu ngắt tác vụ nếu cơ chế Future hỗ trợ việc đó; nó không cưỡng chế chấm dứt mã bất kỳ. Tác vụ trong ví dụ đang đợi tại API có thể ngắt nên hợp tác thoát.

Đặc biệt, `isCancelled()` hay `isDone()` của Future không thay thế bằng chứng rằng tài nguyên bên dưới đã ngừng được sử dụng. Tín hiệu `exited` trong ví dụ xác nhận riêng việc phần chạy đã rời khối xử lý.

Xem [Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html) để phân biệt lấy kết quả có thời hạn và yêu cầu hủy.

## 6. Chia ngân sách chung thay vì đặt lại thời hạn ở mỗi bước

Giả sử một yêu cầu có ngân sách 1.000 ms và cần hai tín hiệu liên tiếp:

```text
Đợi A: tối đa 1.000 ms
Đợi B: tối đa 1.000 ms
```

Cách viết này có thể dành gần 2.000 ms chỉ cho hai lần đợi, chưa kể xử lý khác. Nếu yêu cầu tổng thể chỉ cho 1.000 ms thì bước B phải nhận **phần ngân sách còn lại**.

```text
Ngân sách ban đầu: 1.000 ms
Bước A đã tiêu:     700 ms
Bước B còn tối đa:  300 ms
```

Dùng `System.nanoTime()` để đo khoảng thời gian đã trôi trong cùng JVM. Không dùng `currentTimeMillis()` để đo ngân sách nội bộ vì giờ lịch có thể được hiệu chỉnh.

Giá trị nanoTime không phải dấu thời gian ngày/giờ và không có ý nghĩa độc lập để lưu làm deadline giữa các máy. Quan trọng là hiệu giữa hai lần đọc. [System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()) mô tả quy tắc đo thời gian này.

### Ví dụ hai lần đợi chia cùng ngân sách

Lưu thành `SharedWaitBudgetDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class SharedWaitBudgetDemo {
    public static boolean awaitBoth(
            CountDownLatch first,
            CountDownLatch second,
            long timeoutMillis) throws InterruptedException {

        if (timeoutMillis <= 0 || timeoutMillis > 60_000) {
            throw new IllegalArgumentException(
                    "timeoutMillis must be in 1..60000");
        }

        long budgetNanos =
                TimeUnit.MILLISECONDS.toNanos(timeoutMillis);
        long started = System.nanoTime();

        long remaining =
                budgetNanos - (System.nanoTime() - started);
        if (remaining <= 0
                || !first.await(remaining, TimeUnit.NANOSECONDS)) {
            return false;
        }

        remaining = budgetNanos - (System.nanoTime() - started);
        if (remaining <= 0) {
            return false;
        }
        return second.await(remaining, TimeUnit.NANOSECONDS);
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstReady = new CountDownLatch(0);
        CountDownLatch secondReady = new CountDownLatch(1);

        boolean ready = awaitBoth(firstReady, secondReady, 50);
        System.out.println("Both ready: " + ready);
    }
}
```

Chạy:

```shell
javac SharedWaitBudgetDemo.java
java SharedWaitBudgetDemo
```

Stdout:

```text
Both ready: false
```

Latch thứ nhất đã mở; latch thứ hai không có bên phát tín hiệu. Hàm trả false khi ngân sách không còn cho việc đợi. Không khẳng định stdout xuất hiện chính xác sau 50 ms: bộ lập lịch và thời gian thực thi vẫn có thể làm thời điểm quan sát lệch.

Giới hạn 1..60.000 ms là lựa chọn đơn giản cho ví dụ, giúp phép chuyển đổi và hiệu thời gian nằm trong miền nhỏ, dễ lập luận. Thiết kế thư viện tổng quát cần định nghĩa rõ miền giá trị, xử lý tràn/saturation khi chuyển đơn vị và ngữ nghĩa timeout bằng 0 hoặc âm.

Hàm chọn chính sách không bắt đầu bước chờ mới khi ngân sách đã hết. Một API khác có thể cho phép kiểm tra điều kiện ngay cả khi không còn thời gian chờ; hãy nói rõ lựa chọn thay vì dựa vào suy đoán.

Nếu yêu cầu còn bước xử lý sau khi nhận đủ tín hiệu, bước ấy cũng phải nằm trong ngân sách của thao tác tổng thể. Đoạn ví dụ chỉ giới hạn hai lần đợi, không tự áp deadline cho công việc không được đưa vào hàm.

## 7. Timeout không phải bảo đảm thời gian thực cứng

Truyền 100 ms vào API không có nghĩa toàn bộ phương thức chắc chắn trả về đúng trước 100 ms theo đồng hồ bên ngoài.

Có thể có:

- Trễ do bộ lập lịch hoặc tạm dừng JVM.
- Thời gian lấy lại quyền chạy sau khi thời hạn hết.
- Thời gian cleanup hoặc xử lý ngoại lệ.
- Công việc đồng bộ khác ngoài phần đợi có thời hạn.
- Một bước xử lý do chính lời gọi thực hiện thay vì chỉ đợi.

Ví dụ, luồng đến cuối của `CyclicBarrier` có thể phải chạy barrier action. Thời hạn truyền cho await không biến action thành một công việc bị cưỡng chế ngắt đúng lúc. Action chặn vô hạn vẫn là vấn đề phải xử lý bằng thiết kế riêng.

Vì vậy, timed wait là cơ chế tránh phụ thuộc đợi không có lối ra theo hợp đồng API; nó không biến JVM và hệ điều hành thành hệ thống thời gian thực cứng.

## 8. Hết hạn ảnh hưởng các công cụ khác nhau ra sao?

### CountDownLatch

`await(timeout, unit)` trả false không tự giảm bộ đếm, hủy tác vụ hoặc “đóng” latch. Các tác vụ có thể tiếp tục chạy và về sau đưa bộ đếm về 0.

Sau lần await trả false, không xử lý dữ liệu như thể đã nhận đủ tín hiệu. Những mốc công bố bộ nhớ của lần đợi thành công cũng không được suy ra từ một lần hết hạn.

### Semaphore

`tryAcquire(timeout, unit)` trả false nghĩa là lần này chưa nhận giấy phép. Không truy cập vùng giới hạn và không trả giấy phép chưa lấy.

Nếu có giấy phép được trả ngay sau khi bên gọi bỏ cuộc, điều đó không biến kết quả false thành thành công. Đây là cuộc đua bình thường quanh ranh giới thời hạn.

### CyclicBarrier

Một bên hết hạn trong lúc đợi có thể phá vỡ thế hệ, khiến các bên chờ khác nhận `BrokenBarrierException`. Không được tiếp tục xử lý như mọi người đã đến.

Một tác vụ lỗi trước khi tới barrier không tự làm công cụ biết rằng nó sẽ vắng mặt; thời hạn giúp nhóm phát hiện không đủ bên. Chính sách dừng/thử lại cả nhóm vẫn thuộc tầng điều phối. Xem [CyclicBarrier](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CyclicBarrier.html).

### Future

`get` hết hạn chỉ kết thúc lần đợi kết quả ấy. Tác vụ có thể hoàn tất ngay sau timeout, hoặc tiếp tục sử dụng tài nguyên rất lâu. Gọi cancel có thể thành công, thất bại hoặc tác vụ không phản ứng nhanh với yêu cầu ngắt.

Với thao tác gửi sang hệ thống ngoài, hủy Future trong JVM cũng không tự hoàn tác yêu cầu đã được phía ngoài nhận.

## 9. Thiết kế nhánh hết hạn như một phần của nghiệp vụ

Trước khi thêm timeout, cần quyết định cụ thể điều gì xảy ra sau đó:

| Tình huống | Phản ứng có thể phù hợp |
| --- | --- |
| Chưa lấy được tài nguyên | Trả trạng thái bận, từ chối hoặc thử lại trong ngân sách còn lại |
| Báo cáo thiếu một nguồn dữ liệu | Trả kết quả một phần nếu hợp đồng cho phép |
| Một vòng phối hợp không đủ nhóm | Hủy/dừng đợt xử lý và ghi nhận lỗi |
| Không biết giao dịch bên ngoài đã thành công chưa | Kiểm tra trạng thái bằng mã yêu cầu, tránh gửi lại mù quáng |
| Tác vụ vẫn dùng tài nguyên sau timeout | Giữ đúng vòng đời sở hữu, theo dõi dừng thực sự |

Retry không có giới hạn có thể biến nhiều lần chờ hữu hạn thành một vòng phụ thuộc vô hạn mới. Nếu thử lại, cần số lần/ngân sách tổng, khoảng nghỉ hợp lý và xem thao tác có an toàn khi lặp hay không.

Không giải phóng tài nguyên mà công việc nền vẫn đang sử dụng chỉ vì bên chờ đã trả lỗi. Ví dụ, trả giấy phép tải dữ liệu trong khi yêu cầu tải chưa dừng có thể cho phép công việc mới vào và vượt giới hạn thật.

Cũng không giữ tài nguyên không còn cần thiết trong lúc chờ cleanup của tác vụ khác. Phân biệt rõ thứ mình sở hữu, thứ tác vụ nền sở hữu và mốc bàn giao.

## 10. Những cách viết tưởng có giới hạn nhưng vẫn sai

### Nuốt kết quả false

```java
done.await(1, TimeUnit.SECONDS);
// Sai nếu ngay sau đây mặc định mọi dữ liệu đã sẵn sàng.
```

### Retry vô hạn với timeout được cấp lại

```java
while (!ready.await(1, TimeUnit.SECONDS)) {
    // Không có điều kiện dừng: toàn bộ vòng vẫn có thể kéo dài mãi.
}
```

### Kiểm tra thời gian nhưng chặn bằng API không thời hạn

```java
if (stillHaveTime()) {
    future.get();
}
```

`stillHaveTime()` là hàm minh họa. Việc kiểm tra trước đó không giới hạn lần `get()` không thời hạn tiếp theo.

### Dùng sleep thay cho phối hợp

Ngủ 500 ms không chứng minh tác vụ khác đã hoàn tất. Cần chờ đúng điều kiện, kiểm tra kết quả và có nhánh hết hạn rõ ràng.

### Tự thêm timeout để che một vòng chờ sai

Nếu A giữ khóa mà B cần rồi A đợi B, thêm timeout chỉ giúp A có đường thoát. Thiết kế vẫn cần bỏ vòng phụ thuộc hoặc thay đổi thứ tự sở hữu tài nguyên.

## 11. Tự kiểm tra

1. Lần đợi đang phụ thuộc ai và điều gì làm nó kết thúc?
2. Kết quả thành công được thể hiện bằng giá trị, boolean, null hay không có ngoại lệ?
3. Có deadline chung, hay mỗi bước đang được cấp lại toàn bộ thời gian?
4. Sau timeout, công việc nền còn chạy và ai chịu trách nhiệm dừng?
5. Những tài nguyên nào cần trả ngay, và tài nguyên nào phải giữ tới khi công việc thực sự kết thúc?
6. Nếu timeout sát lúc thành công, việc thử lại có tạo hiệu ứng lặp không?
7. Lỗi, hủy, ngắt và hết hạn đã được phân biệt trong kết quả/quan sát hệ thống chưa?

Chờ có thời hạn hữu ích khi nó đi cùng một nhánh xử lý hoàn chỉnh: nhận biết không đạt điều kiện, tôn trọng ngân sách còn lại, quản lý công việc nền và giữ đúng quyền sở hữu tài nguyên.
