# Join, interrupt và phối hợp hoàn thành giữa các thread

Trong Java 21, `Thread.join()` cho phép một thread chờ thread khác kết thúc; `Thread.interrupt()` gửi tín hiệu yêu cầu thread dừng hoặc thay đổi luồng xử lý. Hai API thường được dùng cùng nhau để phối hợp vòng đời công việc: một thread yêu cầu worker kết thúc, worker tự xử lý tín hiệu interrupt và giải phóng tài nguyên, sau đó thread điều phối dùng `join()` để chờ worker hoàn tất.

`join()` không dừng thread đích và `interrupt()` cũng không cưỡng bức thread kết thúc. Java sử dụng cơ chế hủy hợp tác (cooperative cancellation): thread nhận tín hiệu phải phản hồi bằng cách kiểm tra interrupt status hoặc thoát khỏi thao tác đang chờ có thể bị interrupt. Cách phối hợp này áp dụng cho cả platform thread và virtual thread trong Java 21.

## 1. `Thread.join()` chờ thread kết thúc

`join()` được gọi trên đối tượng `Thread` mà ta muốn chờ:

```java
public class JoinExample {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("Worker started");
            // Thực hiện công việc...
            System.out.println("Worker finished");
        });

        worker.start();
        worker.join();
        System.out.println("Main continues after worker terminates");
    }
}
```

Luồng thực thi của thread gọi `join()` bị chặn cho đến khi `worker` kết thúc. Khi `join()` trả về bình thường, worker đã kết thúc; nếu worker chưa được start, `join()` trả về ngay vì thread chưa ở trạng thái alive. Vì vậy, phải gọi `start()` trước khi chờ nếu mục tiêu là chờ công việc được thực thi.

Các overload quan trọng trong Java 21:

| Phương thức | Hành vi |
| --- | --- |
| `join()` | Chờ đến khi thread kết thúc. |
| `join(long millis)` | Chờ tối đa số mili giây chỉ định; `0` nghĩa là chờ vô hạn. |
| `join(long millis, int nanos)` | Chờ tối đa khoảng thời gian kết hợp mili giây và nano giây; `0, 0` nghĩa là chờ vô hạn. |

Các overload có timeout trả về `void`. Khi hết thời gian chờ, chúng không trả về một giá trị boolean cho biết thread đã kết thúc hay chưa. Hãy kiểm tra `isAlive()` sau khi gọi:

```java
worker.join(1_000);

if (worker.isAlive()) {
    System.out.println("Worker is still running");
} else {
    System.out.println("Worker has terminated");
}
```

Giá trị `1_000` là thời gian chờ tối đa tính bằng mili giây. Timeout không tự dừng worker; nó chỉ giới hạn thời gian thread gọi `join()` chờ trước khi tiếp tục. Nếu cần yêu cầu worker dừng khi quá hạn, phải gửi `interrupt()` riêng.

Tham số mili giây âm, nano giây âm hoặc nano giây lớn hơn `999_999` sẽ gây `IllegalArgumentException`. `isAlive()` trả về `false` cả khi thread chưa được start và khi thread đã kết thúc; nếu cần phân biệt hai trường hợp, hãy quản lý trạng thái công việc trong ứng dụng thay vì chỉ dựa vào `isAlive()`.

## 2. Quan hệ happens-before sau `join()`

`join()` còn có ý nghĩa về khả năng nhìn thấy dữ liệu giữa các thread. Theo Java Memory Model, mọi hành động của một thread xảy ra trước khi thread đó kết thúc đều *happens-before* một thread khác phát hiện thread đó đã kết thúc, chẳng hạn bằng cách `join()` trả về bình thường.

Ví dụ, thread worker ghi kết quả vào field trước khi kết thúc; thread main đọc kết quả sau khi `join()` trả về:

```java
public class JoinVisibility {
    static final class ResultHolder {
        int result;
    }

    public static void main(String[] args) throws InterruptedException {
        ResultHolder holder = new ResultHolder();

        Thread worker = new Thread(() -> {
            holder.result = 42;
        });

        worker.start();
        worker.join();

        System.out.println(holder.result); // 42
    }
}
```

Hành động ghi `holder.result` trong worker được bảo đảm hiển thị với thread main sau khi `join()` xác nhận worker đã kết thúc. Trong ví dụ này không cần khai báo `result` là `volatile` chỉ để truyền giá trị qua ranh giới `start()`/`join()`.

Bảo đảm trên không thay thế đồng bộ nếu hai thread vẫn cùng truy cập dữ liệu trong lúc worker đang chạy. `join()` chỉ tạo điểm phối hợp khi thread đích kết thúc; nó không làm cho các thao tác đọc/ghi đồng thời trước thời điểm đó trở nên an toàn.

## 3. `interrupt()` gửi yêu cầu, không cưỡng bức dừng thread

Gọi `worker.interrupt()` tác động lên worker:

```java
worker.interrupt();
```

Hành vi phụ thuộc trạng thái của worker:

- Nếu worker đang không ở một thao tác chờ có thể bị interrupt, interrupt status của worker được đặt thành `true`.
- Nếu worker đang chờ trong `wait()`, `join()` hoặc `sleep()`, thao tác chờ kết thúc bằng `InterruptedException` và interrupt status bị xóa.
- Nếu worker đang chờ trên một `InterruptibleChannel`, channel bị đóng và interrupt status được đặt. Với `Selector`, thao tác chọn được đánh thức và interrupt status được đặt.
- Nếu thread đích chưa được start hoặc đã kết thúc, lời gọi `interrupt()` không có tác dụng.

`interrupt()` không buộc một vòng lặp tính toán kết thúc. Worker đang chạy CPU cần chủ động kiểm tra trạng thái interrupt hoặc kiểm tra một cờ hủy khác theo thiết kế ứng dụng.

### Kiểm tra interrupt status

Java cung cấp hai cách kiểm tra thường dùng:

```java
Thread.currentThread().isInterrupted();
Thread.interrupted();
```

- `isInterrupted()` kiểm tra interrupt status của đối tượng thread được gọi và không xóa trạng thái.
- `Thread.interrupted()` là phương thức static, kiểm tra interrupt status của thread hiện tại và **xóa trạng thái** sau khi đọc.

Khi chỉ cần kiểm tra để quyết định dừng vòng lặp, ưu tiên `isInterrupted()` để không vô tình xóa tín hiệu:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
```

Chỉ dùng `Thread.interrupted()` khi chủ đích tiêu thụ và xóa interrupt status đã nhận. Không gọi nó như một phép kiểm tra thông thường nếu phần còn lại của chương trình cần biết thread đã bị interrupt.

## 4. `InterruptedException` khi thread đang chờ

Các phương thức như `Thread.sleep()`, `Object.wait()` và `Thread.join()` có thể ném `InterruptedException`. Khi exception được ném do interrupt, interrupt status của thread đang thực hiện thao tác chờ bị xóa. Vì thế, sau khi bắt exception, `Thread.currentThread().isInterrupted()` thường trả về `false`, trừ khi có một interrupt mới được gửi.

Ví dụ, worker đang ngủ có thể phản hồi yêu cầu dừng:

```java
Thread worker = new Thread(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            System.out.println("Working...");
            Thread.sleep(500);
        }
    } catch (InterruptedException e) {
        // sleep đã xóa interrupt status khi ném exception.
        Thread.currentThread().interrupt();
    } finally {
        System.out.println("Release worker resources");
    }
});

worker.start();
```

Khi `sleep()` bị interrupt, worker nhảy đến `catch`, khôi phục interrupt status rồi đi đến `finally` để dọn dẹp. Sau khối `finally`, `Runnable` kết thúc và worker chấm dứt.

## 5. Hai tình huống interrupt khác nhau khi phối hợp với `join()`

Cần phân biệt thread đích bị interrupt với thread đang gọi `join()` bị interrupt.

### Gửi interrupt cho worker đang chạy

```java
worker.interrupt();
worker.join();
```

Lệnh đầu yêu cầu worker dừng. Lệnh thứ hai khiến thread hiện tại chờ worker kết thúc. Nếu worker phản hồi interrupt và thoát, `join()` trả về sau khi worker hoàn tất. Nếu worker bỏ qua tín hiệu hoặc đang chạy đoạn mã không kiểm tra interrupt, `join()` có thể chờ rất lâu hoặc vô hạn.

### Gửi interrupt cho thread đang chờ `join()`

Nếu một thread khác gọi `interrupt()` trên thread đang bị chặn trong `worker.join()`, chính lời gọi `join()` sẽ ném `InterruptedException`:

```java
try {
    worker.join();
} catch (InterruptedException e) {
    // Thread hiện tại bị interrupt trong lúc chờ worker.
    worker.interrupt(); // Tùy chính sách: chuyển yêu cầu dừng sang worker.
    Thread.currentThread().interrupt(); // Khôi phục tín hiệu cho tầng gọi.
}
```

`worker.interrupt()` không phải điều kiện để `join()` ném exception; nó gửi tín hiệu đến thread đích. Muốn đánh thức thread đang chờ `join()`, phải interrupt chính thread đang chờ đó. Trong ví dụ, sau khi bắt exception, code gửi yêu cầu dừng cho worker rồi khôi phục interrupt status của thread điều phối.

Nếu phương thức hiện tại có thể khai báo `throws InterruptedException`, cách đơn giản thường là để exception truyền lên tầng gọi. Chỉ bắt exception khi cần thực hiện cleanup hoặc chuyển đổi chính sách hủy; nếu không tiếp tục ném exception, thường phải khôi phục interrupt status bằng `Thread.currentThread().interrupt()`.

## 6. Mẫu phối hợp: worker phản hồi interrupt, main chờ kết thúc

Ví dụ sau thể hiện worker làm công việc có thể bị interrupt và main đợi bằng `join()`. Nếu chính main bị interrupt trong lúc chờ, main chuyển yêu cầu dừng sang worker và khôi phục interrupt status của mình.

```java
public class WorkerCoordination {
    public static void main(String[] args) {
        Thread worker = new Thread(() -> {
            try {
                for (int i = 1; i <= 10; i++) {
                    if (Thread.currentThread().isInterrupted()) {
                        break;
                    }

                    System.out.println("Processing item " + i);
                    Thread.sleep(300);
                }
            } catch (InterruptedException e) {
                // Không tiếp tục công việc sau khi nhận yêu cầu dừng.
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Worker cleanup completed");
            }
        }, "worker-1");

        worker.start();

        try {
            worker.join();
            System.out.println("Worker terminated normally");
        } catch (InterruptedException e) {
            worker.interrupt();
            Thread.currentThread().interrupt();
            System.out.println("Main was interrupted while waiting");
        }
    }
}
```

Trong ví dụ này, nhánh `catch` yêu cầu worker dừng nhưng main không tiếp tục chờ sau khi chính nó bị interrupt. Vì vậy, nhánh này không khẳng định worker đã hoàn tất cleanup. Nếu tầng gọi cần xác nhận worker kết thúc, hãy propagate `InterruptedException` để tầng đó quyết định cách chờ tiếp, hoặc áp dụng một chính sách chờ có giới hạn như ví dụ kế tiếp. Trong ứng dụng thực tế, tín hiệu hủy cũng có thể đến từ timeout, thao tác shutdown hoặc một điều kiện nghiệp vụ khác.

## 7. Chờ có giới hạn, yêu cầu dừng và kiểm tra kết quả

Khi không thể chờ vô hạn, dùng timed join. Sau timeout, kiểm tra `isAlive()` rồi mới quyết định bước tiếp theo:

```java
static void stopWithinDeadline(Thread worker) throws InterruptedException {
    worker.join(1_000);

    if (worker.isAlive()) {
        worker.interrupt();
        worker.join(500);
    }

    if (worker.isAlive()) {
        System.out.println("Worker did not terminate within the wait period");
    } else {
        System.out.println("Worker has terminated");
    }
}
```

Quy trình gồm ba bước: chờ trong thời gian đầu, gửi interrupt nếu worker vẫn chạy, rồi chờ thêm một khoảng thời gian ngắn. Nếu worker vẫn alive sau lần chờ thứ hai, chương trình phải quyết định cách xử lý tiếp theo (ghi log, báo lỗi, hoặc để một cơ chế quản lý khác theo dõi). Không có API interrupt an toàn nào bảo đảm ép một thread bất kỳ kết thúc ngay lập tức.

Nếu thread điều phối bị interrupt trong bất kỳ lần `join()` nào, `InterruptedException` được ném và interrupt status bị xóa. Vì phương thức trên khai báo `throws InterruptedException`, tầng gọi nhận trách nhiệm quyết định propagate hoặc khôi phục trạng thái.

## 8. Virtual thread trong Java 21

Java 21 chuẩn hóa virtual threads. Chúng vẫn là đối tượng `Thread`, nên có thể dùng `start()`, `interrupt()`, `isAlive()` và `join()` theo cùng mô hình phối hợp vòng đời:

```java
public class VirtualJoinExample {
    public static void main(String[] args) throws InterruptedException {
        Thread virtualWorker = Thread.ofVirtual().start(() -> {
            try {
                Thread.sleep(200);
                System.out.println("Virtual worker completed");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        virtualWorker.join();
    }
}
```

`join()` vẫn chờ virtual thread kết thúc và có thể ném `InterruptedException` nếu thread gọi `join()` bị interrupt. Virtual thread không làm thay đổi ý nghĩa của interrupt: đó vẫn là tín hiệu hợp tác, không phải lệnh cưỡng bức kết thúc. Không cần dùng thread pool hoặc API preview chỉ để minh họa `join()` và `interrupt()`.

## 9. Deadlock và những lỗi phối hợp thường gặp

`join()` có thể gây deadlock nếu các thread chờ lẫn nhau hoặc nếu thread điều phối giữ khóa mà worker cần để hoàn thành.

Ví dụ về self-join:

```java
Thread.currentThread().join(); // Chờ chính mình kết thúc: không thể tiếp tục.
```

Thread không thể kết thúc trong khi chính nó đang chờ `join()` của mình. Tránh self-join và tránh thiết kế chu trình A chờ B, B chờ A.

Không giữ monitor hoặc lock cần thiết bởi worker trong khi gọi `join()`. Nếu main giữ khóa và worker cần cùng khóa đó để kết thúc, main chờ worker còn worker chờ khóa, khiến cả hai không thể tiến triển.

| Lỗi thường gặp | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Gọi `join()` trước `start()` rồi nghĩ worker đã chạy xong | Thread chưa alive nên `join()` trả về ngay. | Gọi `start()` trước khi chờ. |
| Nghĩ timeout của `join()` tự dừng worker | Timeout chỉ giới hạn thời gian chờ của thread gọi. | Kiểm tra `isAlive()` và gửi `interrupt()` nếu cần yêu cầu dừng. |
| Worker không dừng sau `interrupt()` | Worker bỏ qua interrupt status hoặc không dùng thao tác chờ interruptible. | Kiểm tra `isInterrupted()` trong vòng lặp và xử lý `InterruptedException`. |
| Bắt `InterruptedException` rồi bỏ qua | Interrupt status đã bị xóa khi exception được ném. | Propagate exception hoặc khôi phục status bằng `Thread.currentThread().interrupt()`. |
| Interrupt worker nhưng nghĩ thread đang join sẽ thức dậy | `interrupt()` tác động đến thread đích được gọi, không phải thread đang chờ nó. | Muốn hủy thao tác chờ, interrupt chính thread đang gọi `join()`. |
| Tiếp tục xử lý như worker đã xong sau `InterruptedException` | `join()` bị ngắt trước khi xác nhận worker kết thúc. | Không giả định worker đã hoàn tất; gửi tín hiệu hủy và xử lý chờ/cleanup theo chính sách. |
| Deadlock khi gọi `join()` trong synchronized block | Worker cần monitor đang bị thread gọi join giữ. | Không giữ khóa mà worker cần trong lúc chờ thread đó kết thúc. |

## 10. Quy trình thực hành

1. Tạo thread và xác định công việc có thể bị interrupt ở đâu.
2. Gọi `start()` để bắt đầu worker.
3. Dùng `join()` nếu cần chắc chắn worker đã kết thúc trước khi đọc kết quả hoặc giải phóng tài nguyên phụ thuộc.
4. Dùng timed `join()` khi cần giới hạn thời gian chờ; sau timeout, kiểm tra `isAlive()`.
5. Khi cần hủy, gửi `interrupt()` đến worker và bảo đảm worker kiểm tra status hoặc thoát khỏi thao tác chờ.
6. Xử lý `InterruptedException` bằng cách propagate hoặc khôi phục interrupt status; không âm thầm nuốt tín hiệu.
7. Tránh self-join, chu trình chờ và giữ khóa mà worker cần trong lúc gọi `join()`.

## 11. Tài liệu tham khảo chính thức

- [Java SE 21 API — `Thread`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `start`, `join`, `interrupt`, interrupt status, platform thread và virtual thread.
- [Java SE 21 API — `InterruptedException`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InterruptedException.html): exception phát sinh khi thread bị interrupt trong thao tác chờ.
- [Java Language Specification, Java SE 21 — §17.4.5 Happens-before Order](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.4.5): quan hệ happens-before giữa kết thúc thread và việc thread khác phát hiện kết thúc bằng `join()`.
- [Java SE 21 API — `Object.wait()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#wait()): hành vi interrupt đối với thread đang chờ.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads được chuẩn hóa trong Java 21.
