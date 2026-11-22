# `Thread.join()`: chờ một thread kết thúc trong Java

## 1. `join()` giải quyết bài toán gì?

Trong Java, sau khi gọi `Thread.start()`, thread mới có thể chạy đồng thời với thread đang gọi. `start()` **không chờ** công việc trong thread đó hoàn tất. Nếu thread hiện tại cần kết quả hoặc cần bảo đảm công việc kia đã kết thúc trước khi tiếp tục, có thể gọi `join()` trên chính đối tượng `Thread` đại diện cho thread cần chờ.

```java
Thread worker = new Thread(() -> doWork());
worker.start();  // Yêu cầu JVM bắt đầu thread worker
worker.join();   // Thread hiện tại chờ worker kết thúc
useResult();     // Chỉ chạy sau khi join() trở về bình thường
```

Đoạn trên **chỉ là mã minh họa** vì `doWork()` và `useResult()` chưa được định nghĩa; ví dụ hoàn chỉnh ở phần tiếp theo.

**Cú pháp cốt lõi:** `worker.join()` có nghĩa “thread **đang gọi** sẽ chờ cho `worker` kết thúc”. Nó không mang nghĩa worker chờ thread đang gọi, cũng không tự khởi động worker.

- Nếu gọi từ `main`, `main` là thread bị chặn trong lúc chờ.
- Nếu gọi từ một worker khác, worker gọi `join()` là thread bị chặn.
- Thread đích vẫn tiếp tục thực thi theo lịch của JVM; `join()` không “chạy hộ”, không khiến thread đích kết thúc sớm và không bảo đảm nó thành công.
- Thread đích có thể hoàn tất trước khi gọi `join()`; lúc đó `join()` có thể trở về ngay.

### `join()` và `sleep()` khác nhau

`Thread.sleep(100)` yêu cầu **thread hiện tại** tạm nghỉ khoảng thời gian được chỉ định, không quan tâm worker đã xong chưa. `worker.join()` chờ một **điều kiện cụ thể là worker kết thúc**. Vì thế, dùng `sleep()` để “đợi worker đủ lâu rồi lấy kết quả” là sai về mặt đồng bộ: worker có thể nhanh hơn hoặc chậm hơn dự tính.

## 2. Ví dụ Java 17+: bảo đảm thứ tự và đọc kết quả sau `join()`

Tạo tệp `JoinBasic.java`:

```java
public class JoinBasic {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            int sum = 0;
            for (int number = 1; number <= 5; number++) {
                sum += number;
            }

            result = sum;
            System.out.println("Worker finished");
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("Result: " + result);
        System.out.println("Worker alive: " + worker.isAlive());
    }
}
```

Biên dịch và chạy:

```bash
javac JoinBasic.java
java JoinBasic
```

Đầu ra khi thực thi thành công:

```text
Worker finished
Result: 15
Worker alive: false
```

**Diễn giải chính xác:**

1. `new Thread(...)` tạo đối tượng mô tả luồng; chưa có tác vụ nào được chạy bởi thread mới.
2. `worker.start()` khởi động thread, sau đó `main` và worker có thể tiến triển độc lập.
3. Worker cộng các số từ 1 đến 5, gán `result = 15` rồi in thông báo.
4. `worker.join()` không trả về bình thường trước khi worker thực sự kết thúc.
5. Sau `join()`, `main` đọc `result` và quan sát `isAlive() == false`. Vì thông báo được in trước khi worker kết thúc, thứ tự ba dòng trên là xác định trong chương trình ví dụ.

**Điểm liên quan tới Java Memory Model:** mọi hành động của worker **happens-before** việc thread khác phát hiện worker đã kết thúc thành công qua `join()`. Vì vậy, với ví dụ trên, sau `join()` trả về bình thường, `main` thấy giá trị `result = 15`; trường `result` không cần đánh dấu `volatile` chỉ để truyền kết quả ở ranh giới kết thúc này. Điều đó **không** biến mọi truy cập đồng thời vào biến chia sẻ trước khi worker kết thúc thành an toàn, cũng không bảo đảm đúng nếu `join()` bị ngắt hoặc chỉ chờ có thời hạn mà worker vẫn chạy.

## 3. Các overload của `join()`

`Thread` trong Java 17 cung cấp các overload phổ biến:

| Phương thức | Ý nghĩa |
| --- | --- |
| `void join() throws InterruptedException` | Chờ thread đích kết thúc, không đặt thời hạn chờ |
| `void join(long millis) throws InterruptedException` | Chờ tối đa khoảng `millis` mili-giây nếu `millis > 0`; `millis == 0` là chờ vô hạn |
| `void join(long millis, int nanos) throws InterruptedException` | Chờ có giới hạn thời gian với phần mili-giây và nano-giây; phần nano được xử lý theo độ phân giải của triển khai |

Đối số thời gian không hợp lệ ném `IllegalArgumentException`: `millis < 0`, hoặc `nanos < 0` hay `nanos > 999_999`.

**Bẫy:** `join(0)` **không** phải “kiểm tra ngay, không chờ”. Nó có nghĩa chờ cho tới khi thread kết thúc, tương tự `join()`. Nếu cần biết thread còn sống mà không chặn, dùng `isAlive()` nhưng nhớ rằng trạng thái có thể thay đổi ngay sau lúc kiểm tra.

**Bẫy thời gian:** `join(100)` không cam kết trở về đúng sau 100 ms. Việc đánh thức và lập lịch tùy JVM/OS, nên thực tế có thể muộn hơn. Không sử dụng `join(long)` như bộ đếm thời gian chính xác. Với `join(long, int)`, độ phân giải và việc làm tròn phần nano phụ thuộc triển khai.

**Giá trị trả về:** cả ba overload đều trả về `void`. Với timed join, việc quay lại **không cho biết** worker đã xong hay hết thời gian chờ. Cần kiểm tra `worker.isAlive()` sau khi gọi, rồi quyết định tiếp tục chờ, hủy tác vụ hoặc ghi nhận trạng thái chưa hoàn tất.

## 4. Ví dụ Java 17+: `join(timeout)` và xử lý worker chưa hoàn tất

Tạo tệp `JoinTimeout.java`:

```java
public class JoinTimeout {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(200); // Mô phỏng một công việc mất thời gian
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "slow-worker");

        worker.start();
        worker.join(25); // Chờ nhiều nhất xấp xỉ 25 ms

        if (worker.isAlive()) {
            System.out.println("Worker may still be running");
            worker.join(); // Đợi kết thúc thật để dọn dẹp ví dụ
        }

        System.out.println("Worker terminated: " + !worker.isAlive());
    }
}
```

Chạy:

```bash
javac JoinTimeout.java
java JoinTimeout
```

Dòng cuối **luôn là** `Worker terminated: true` nếu chương trình hoàn tất bình thường. Dòng `Worker may still be running` có thể có hoặc không, vì kết quả phụ thuộc việc lập lịch: worker có thể đã kết thúc trước khi `main` kiểm tra `isAlive()`. Không dùng thời gian sleep trong ví dụ này để kết luận một ngưỡng timeout thực tế cho production.

Mã trên chỉ cho thấy kỹ thuật phát hiện trạng thái sau timed join. Với task không có giới hạn hoàn thành, `join()` lần thứ hai **có thể chờ vô hạn**. Trong ứng dụng thật, cần có chính sách rõ ràng: trả kết quả “đang xử lý”, đặt hạn chót, gửi tín hiệu hủy hợp tác, hoặc tiếp tục theo dõi từ thành phần quản lý vòng đời. `join(timeout)` **không tự hủy** thread đích khi hết hạn.

## 5. InterruptedException: người đang chờ bị ngắt

Các overload của `join()` khai báo `throws InterruptedException`. Nếu thread **đang chờ trong `join()`** bị interrupt, lệnh chờ có thể ném `InterruptedException`. Đây là tín hiệu yêu cầu ngừng chờ hoặc dừng công việc theo giao thức của chương trình; nó **không đồng nghĩa** thread đích đã kết thúc, cũng không tự truyền interrupt sang worker.

Hai hướng xử lý thường gặp:

- **Cho phép truyền lỗi ra ngoài:** phương thức khai báo `throws InterruptedException` để caller có quyền quyết định cách kết thúc, dọn dẹp và khôi phục.
- **Bắt lỗi ở tầng không thể truyền tiếp:** dọn dẹp cần thiết và thường gọi lại `Thread.currentThread().interrupt()` để giữ tín hiệu interrupt cho tầng trên. Khi `InterruptedException` được ném từ thao tác chờ, interrupt status của thread hiện tại thường đã bị xóa; vì vậy khôi phục là bước quan trọng nếu bạn không truyền ngoại lệ tiếp.

Ví dụ về cách khôi phục cờ interrupt trong một phương thức không khai báo `throws`:

```java
static boolean waitFor(Thread worker) {
    try {
        worker.join();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

Đoạn này là **phương thức minh họa** dùng trong một class khác; biến `worker` là thread cần chờ. Giá trị `false` có nghĩa **không hoàn tất việc chờ**; không được suy ra worker đã thất bại hoặc đã kết thúc. Caller phải quyết định ứng xử tiếp theo theo chính sách dừng/hủy của ứng dụng.

**Phân biệt hai hành động:**

- `waitingThread.interrupt()`: yêu cầu ngắt thread đang nằm trong `join()`; có thể làm phát sinh `InterruptedException` ở thread đó.
- `worker.interrupt()`: gửi tín hiệu interrupt tới worker; worker phải tự phản ứng thích hợp, chẳng hạn xử lý `InterruptedException` hoặc kiểm tra cờ interrupt. Không bảo đảm worker sẽ kết thúc ngay, đặc biệt với tác vụ bỏ qua interrupt.

Không dùng `Thread.stop()` để cưỡng ép kết thúc worker: API này đã lỗi thời và không an toàn.

## 6. `join()` có bảo đảm tác vụ thành công không?

**Không.** `join()` chỉ xác nhận thread đã chấm dứt khi trả về bình thường không có timeout. Worker có thể kết thúc vì chạy xong hoặc vì lỗi không được xử lý. Ngoại lệ phát sinh trong worker **không tự được ném sang** thread đang gọi `join()`. Do đó, `join()` không thay thế cơ chế thông báo kết quả hoặc lỗi.

Nếu dùng `Thread` trực tiếp, có thể ghi kết quả và lỗi trong nơi lưu trữ được thiết kế rõ ràng. Ví dụ sau bắt lỗi nghiệp vụ trong worker và đọc sau `join()`:

Tạo tệp `JoinFailure.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class JoinFailure {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<String> error = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                throw new IllegalArgumentException("invalid input");
            } catch (IllegalArgumentException e) {
                error.set(e.getMessage());
            }
        });

        worker.start();
        worker.join();

        if (error.get() != null) {
            System.out.println("Task failed: " + error.get());
        }
    }
}
```

Chạy:

```bash
javac JoinFailure.java
java JoinFailure
```

Đầu ra:

```text
Task failed: invalid input
```

`AtomicReference` ở đây cung cấp nơi lưu trạng thái lỗi rõ nghĩa và an toàn khi dùng giữa các thread. Với truyền dữ liệu **chỉ sau khi `join()` thành công**, quan hệ happens-before của `join()` đã đủ cho visibility; tuy nhiên trong bài toán phức tạp hơn, `Future`/`CompletableFuture` thường diễn đạt kết quả, ngoại lệ, timeout và hủy task trực tiếp hơn.

## 7. Các trường hợp dễ gây treo hoặc chờ sai

### 7.1. Thread tự `join()` chính mình

```java
Thread.currentThread().join(); // Nguy hiểm: đợi chính thread đang chạy kết thúc
```

Thread chỉ kết thúc khi mã của chính nó kết thúc, nhưng nó lại chờ chính mình: có thể mắc kẹt vô hạn trừ khi có interrupt phù hợp. Không dùng self-join.

### 7.2. Hai thread chờ nhau

Nếu thread A gọi `b.join()` còn B gọi `a.join()` khi cả hai đang hoạt động, cả hai có thể chờ vô thời hạn. Đây là chu trình phụ thuộc tương tự deadlock, dù không nhất thiết xảy ra trên monitor do lập trình viên tự khóa.

Quy tắc thiết kế: xây dựng **đồ thị chờ không có vòng**. Thường một thread điều phối chờ các worker; worker không nên chờ ngược thread điều phối trong lúc thread điều phối đang chờ worker đó.

### 7.3. Giữ một lock mà worker cũng cần

Nếu thread gọi giữ một monitor/lock rồi `join()` worker, trong khi worker cần đúng lock đó để hoàn tất, chương trình có thể bế tắc: caller giữ lock để chờ worker, worker chờ lock để kết thúc. Hãy tách vùng giữ lock khỏi thao tác chờ và kiểm tra thứ tự phụ thuộc khóa.

Ví dụ cần tránh về mặt ý tưởng:

```java
synchronized (sharedLock) {
    worker.join(); // Nguy hiểm nếu worker phải lấy sharedLock để thoát
}
```

Đây là mã minh họa khi `worker` và `sharedLock` đã được khai báo. Không nên kết luận mọi `join()` nằm trong `synchronized` đều deadlock; lỗi xuất hiện khi có đường phụ thuộc ngược.

### 7.4. Gọi `join()` trên thread chưa `start()`

Một đối tượng `Thread` còn ở trạng thái `NEW` chưa thực thi `run()`; gọi `join()` không khiến tác vụ bắt đầu. Vì thread đó chưa `isAlive()`, `join()` có thể trả về ngay. Vì vậy phải gọi `start()` đúng lúc trước khi chờ, trừ khi chủ ý kiểm tra một thread đã kết thúc.

### 7.5. Coi timed join trả về là hoàn tất

`worker.join(100)` không cam kết worker đã xong. Nếu cần kết quả hoàn chỉnh, kiểm tra `!worker.isAlive()` sau lúc chờ và chỉ đọc kết quả phụ thuộc hoàn tất khi điều kiện đó được thỏa mãn. Nếu thread vẫn chạy, không dùng dữ liệu mutable chưa được đồng bộ như thể nó đã hoàn thành.

### 7.6. Chờ vô hạn trên một công việc có thể treo

`join()` không có timeout khiến thread gọi chờ cho đến khi thread đích kết thúc hoặc bị interrupt. Nếu worker kẹt I/O, deadlock hoặc vòng lặp không dừng, người chờ cũng có thể kẹt. Hãy xem xét timeout/cancellation ở cấp kiến trúc, đặc biệt trên đường xử lý cần đáp ứng hạn chót.

## 8. `join()` và các cách chờ khác trong Java

| Cách chờ | Khi nào phù hợp | Điều cần nhớ |
| --- | --- | --- |
| `Thread.join()` | Cần đợi **một thread cụ thể** kết thúc | Chỉ cho biết hoàn tất vòng đời thread, không trả kết quả hoặc lỗi task |
| `Thread.join(timeout)` | Muốn dành thời gian có giới hạn để đợi thread kết thúc | Trả về `void`; phải kiểm tra còn sống hay không |
| `Future.get()` | Task được submit qua `ExecutorService`, cần kết quả và lỗi task | Có thể ném `ExecutionException`; có overload timeout |
| `CompletableFuture.join()` | Pipeline bất đồng bộ có `CompletableFuture` | Có thể ném `CompletionException` unchecked; tên `join` nhưng ngữ nghĩa khác `Thread.join` |
| `CountDownLatch.await()` | Một hoặc nhiều thread chờ **mốc công việc/sự kiện** | Không gắn trực tiếp với việc thread nào kết thúc; cần countdown đúng |
| `Thread.sleep()` | Cần tạm nghỉ thread hiện tại | Không xác nhận một công việc khác đã hoàn tất |

Các lựa chọn này là API Java tiêu chuẩn; không cần đưa nội dung framework vào bài học về `Thread.join()`.

## 9. Ghi nhớ và checklist thực hành

1. Tạo `Thread`, gọi `start()`, rồi gọi `join()` từ thread **cần chờ**.
2. `join()` đợi vòng đời thread, **không** bắt đầu thread và **không** chuyển tự động kết quả/ngoại lệ.
3. Một `join()` thành công sau khi thread đích kết thúc tạo quan hệ **happens-before**, giúp thấy các ghi của worker trước khi kết thúc.
4. `join(0)` là chờ vô hạn; với `join(timeout)` luôn kiểm tra `isAlive()` trước khi giả định công việc đã xong.
5. Có thể bị `InterruptedException`; truyền lỗi lên trên hoặc khôi phục interrupt status nếu bắt và không truyền.
6. Tránh self-join, vòng A → B → A và chờ khi đang giữ lock mà worker cần.
7. Nếu bài toán đã có thread pool, kết quả, lỗi, timeout hoặc nhiều task cần phối hợp, cân nhắc `Future` và các abstraction concurrent phù hợp thay vì tạo/chờ thread thủ công.

**Kết luận:** `Thread.join()` là primitive đơn giản và quan trọng để một thread chờ thread khác hoàn tất, đồng thời thiết lập quan hệ đồng bộ cần thiết với các ghi trước khi thread đích kết thúc. Sử dụng nó đúng thời điểm, xử lý interrupt và xác minh trạng thái khi có timeout sẽ tránh phần lớn lỗi thường gặp.