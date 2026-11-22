# lockInterruptibly và chờ khóa có thể bị ngắt

## 1. Vấn đề: tác vụ cần dừng dù chưa lấy được khóa

Một tác vụ có thể mất thời gian ngay trước khi vào đoạn xử lý: nó đang chờ khóa do luồng khác giữ. Nếu dùng một cách chờ không phản hồi yêu cầu hủy, tác vụ có thể tiếp tục nằm chờ dù bên gọi đã không còn cần kết quả.

`ReentrantLock.lockInterruptibly()` cho phép lấy khóa với khả năng bị ngắt trong quá trình lấy. Nếu lấy được, luồng trở thành chủ khóa và đi tiếp. Nếu nhận ngắt theo hợp đồng của phương thức, lời gọi ném `InterruptedException` để bên gọi có thể hủy tác vụ hoặc chuyển yêu cầu hủy lên tầng ngoài.

Khả năng này hỗ trợ hủy có hợp tác. Nó không cưỡng chế dừng luồng đang sở hữu khóa, không lấy khóa từ tay chủ hiện tại, và không tự hoàn tác công việc đã thực hiện.

Bài dùng `ReentrantLock` hiện hành và ví dụ Java 17 trở lên. Giao diện `Lock` cho phép triển khai công bố các đặc điểm riêng về khả năng ngắt, nên khi dùng loại khóa khác cần đọc hợp đồng của chính triển khai đó.

## 2. Hợp đồng của ReentrantLock.lockInterruptibly

```java
public void lockInterruptibly() throws InterruptedException
```

Có hai kết quả chính:

| Tình huống | Kết quả | Quyền sở hữu của lần gọi này |
| --- | --- | --- |
| Lấy được khóa và phương thức trả về bình thường | Tiếp tục vào khối xử lý | Đã lấy thành công, cần nhả tương ứng |
| Bị ngắt theo hợp đồng trong quá trình lấy | Ném `InterruptedException` và xóa cờ ngắt | Lần gọi không tạo thêm quyền giữ khóa |

Nếu cờ ngắt của luồng đã được đặt trước khi gọi, `ReentrantLock.lockInterruptibly()` có thể ném ngay, kể cả khi khóa đang rảnh. Nếu khóa do luồng khác giữ, luồng có thể chờ cho đến khi lấy được hoặc bị ngắt.

`ReentrantLock` ưu tiên phản hồi ngắt tại điểm ngắt tường minh này so với một lần lấy bình thường hoặc tái nhập. Không suy rằng cùng luồng đã giữ khóa thì `lockInterruptibly` chắc chắn bỏ qua cờ ngắt và lấy thêm một mức.

Chi tiết nằm trong [ReentrantLock.lockInterruptibly — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#lockInterruptibly()).

## 3. Mẫu đặt try/finally đúng quyền sở hữu

Ở tầng cho phép chuyển ngoại lệ lên bên gọi, mẫu thông thường là:

```java
// Đoạn minh họa trong một lớp có trường lock.
public void update() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        // Đọc/ghi dữ liệu được bảo vệ sau khi đã lấy khóa.
    } finally {
        lock.unlock();
    }
}
```

`try/finally` để nhả khóa bắt đầu **sau** lời gọi lấy khóa thành công. Nếu `lockInterruptibly()` ném, luồng không vào khối ấy và không nhả một khóa mình chưa lấy.

Đoạn sau dễ gây lỗi:

```java
// Đoạn minh họa sai: unlock chạy cả khi lấy khóa bị ngắt.
try {
    lock.lockInterruptibly();
    // Xử lý...
} finally {
    lock.unlock();
}
```

Nếu luồng không hề sở hữu khóa, `unlock()` trong `finally` có thể ném `IllegalMonitorStateException`, che mất thông tin ngắt ban đầu. Nếu luồng đã giữ khóa từ một tầng gọi ngoài nhưng lần lấy thêm bị ngắt, lệnh nhả không tương ứng này còn có thể làm giảm nhầm mức giữ của tầng ngoài.

Cũng cần giữ mọi thao tác có thể ném ngoại lệ sau khi lấy khóa trong vùng được `finally` bảo vệ, không chèn việc khởi tạo phức tạp giữa lần lấy thành công và `try`.

## 4. Ngắt luồng là một yêu cầu hợp tác

`worker.interrupt()` gửi yêu cầu ngắt tới worker. Nó không có nghĩa là “giết worker ngay tại câu lệnh này”. Tác dụng cụ thể phụ thuộc worker đang làm gì và các API đang dùng phản hồi ngắt ra sao.

`Thread.currentThread().isInterrupted()` đọc trạng thái mà không xóa. `Thread.interrupted()` là phương thức tĩnh kiểm tra và xóa cờ của luồng hiện tại. Không nhầm hai cách này khi chẩn đoán vì một lần đọc có xóa có thể làm thay đổi hành vi của lời gọi chờ phía sau. Xem [Thread — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#interrupt()).

Khi `lockInterruptibly()` ném `InterruptedException`, cờ ngắt đã bị xóa theo hợp đồng. Chính sách xử lý thường thuộc một trong hai trường hợp:

- **Chuyển yêu cầu lên:** để phương thức khai báo `throws InterruptedException`; tầng gọi quyết định vòng đời và hủy.
- **Kết thúc tại ranh giới tác vụ:** nếu đang ở `Runnable` không chuyển ngoại lệ kiểm tra được lên, thường khôi phục cờ bằng `Thread.currentThread().interrupt()` rồi kết thúc tác vụ.

Không khôi phục cờ rồi quay ngay vào một vòng lặp gọi `lockInterruptibly` vô hạn: cờ đang đặt có thể khiến mỗi lần gọi tiếp theo lập tức ném, tạo vòng lặp lỗi. Cũng không nuốt ngoại lệ rồi tiếp tục xử lý như thể đã có khóa.

Một tầng thực sự sở hữu chính sách ngắt có thể xử lý yêu cầu khác theo thiết kế, nhưng phải thể hiện rõ việc hủy đã được giải quyết ở đâu. Không xóa/ngó lơ cờ chỉ để mã chạy tiếp mà mất thông báo từ bên gọi.

## 5. Chương trình chạy đầy đủ

Main giữ khóa, mở một worker chuẩn bị lấy khóa có thể ngắt, rồi gửi yêu cầu ngắt. Main vẫn giữ khóa cho đến khi worker đã kết thúc, nên worker không thể vô tình đi vào đoạn tới hạn do main vừa nhả.

Lưu vào `InterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected lock result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempting = new CountDownLatch(1);
        AtomicBoolean entered = new AtomicBoolean(false);
        AtomicBoolean caught = new AtomicBoolean(false);
        AtomicBoolean flagInCatch = new AtomicBoolean(true);
        AtomicBoolean restored = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            try {
                attempting.countDown();
                lock.lockInterruptibly();
                try {
                    entered.set(true);
                } finally {
                    lock.unlock();
                }
            } catch (InterruptedException e) {
                caught.set(true);
                flagInCatch.set(Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            }
        }, "worker");

        lock.lock();
        try {
            worker.start();
            attempting.await();
            worker.interrupt();
            worker.join();

            check(caught.get());
            check(!entered.get());
            check(!flagInCatch.get());
            check(restored.get());
            check(lock.isHeldByCurrentThread());

            System.out.println("InterruptedException caught: " + caught.get());
            System.out.println("worker entered critical section: " + entered.get());
            System.out.println("flag inside catch: " + flagInCatch.get());
            System.out.println("flag after restore: " + restored.get());
            System.out.println("main still owns lock: "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }

        Thread.currentThread().interrupt();
        try {
            lock.lockInterruptibly();
            try {
                throw new AssertionError("Pre-interrupted call must fail");
            } finally {
                lock.unlock();
            }
        } catch (InterruptedException expected) {
            System.out.println("pre-interrupted free lock: InterruptedException");
            check(!Thread.currentThread().isInterrupted());
        }

        lock.lockInterruptibly();
        try {
            System.out.println("normal acquisition: "
                    + lock.isHeldByCurrentThread());
        } finally {
            lock.unlock();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 InterruptibleLockDemo.java
java InterruptibleLockDemo
```

Stdout:

```text
InterruptedException caught: true
worker entered critical section: false
flag inside catch: false
flag after restore: true
main still owns lock: true
pre-interrupted free lock: InterruptedException
normal acquisition: true
```

`attempting` chỉ xác nhận worker đã đi tới ngay trước lần gọi; nó không khẳng định worker đã nằm chờ bên trong khóa. Ngắt có thể tới trước lúc worker gọi `lockInterruptibly` hoặc trong lúc nó chờ. Cả hai trường hợp đều được hợp đồng hỗ trợ và cho cùng kết quả ở đây, vì main chưa nhả khóa.

`worker.join()` giúp main đợi worker kết thúc rồi mới đọc các biến kiểm tra. Main giữ khóa trong đoạn đợi này là lựa chọn riêng của ví dụ để cố định kết quả: worker phải phản hồi ngắt và không cần lấy khóa để kết thúc. Không áp dụng cách đợi này cho một tác vụ có đường dọn dẹp bắt buộc phải lấy chính khóa main đang giữ.

Phần thứ hai chủ động đặt cờ ngắt cho main khi khóa đã rảnh. Lời gọi vẫn ném trước khi lấy được; `catch` xác nhận cờ đã được xóa. Trong đoạn minh họa kiểm tra có kiểm soát này, main chủ động tiêu thụ yêu cầu do chính nó tạo để tiếp tục thử lần lấy bình thường. Đây không phải mẫu nuốt yêu cầu hủy từ một bên gọi thật.

Lần lấy cuối trả về bình thường, nên khối `finally` của nó nhả khóa đúng một lần.

## 6. So sánh với các cách lấy khóa khác

| Cách lấy | Có thể chờ khóa? | Cách phản hồi ngắt lúc lấy với ReentrantLock | Khi chưa được khóa |
| --- | --- | --- | --- |
| `lock()` | Có, không có thời hạn của lời gọi | Không dùng `InterruptedException` để từ bỏ chờ | Tiếp tục chờ |
| `lockInterruptibly()` | Có, không có thời hạn của lời gọi | Có thể ném `InterruptedException` | Chờ hoặc phản hồi ngắt |
| `tryLock()` | Không đợi khóa rảnh | Không phải điểm ngắt như dạng có ngắt | Trả `false` nếu chưa lấy được |
| `tryLock(timeout, unit)` | Có giới hạn | Có thể ném `InterruptedException` | Hết thời gian thì trả `false` |

Chờ vào một khối `synchronized` không cung cấp API tương đương trực tiếp để ngắt việc lấy monitor bằng `InterruptedException`. Điều đó khác với `Object.wait()` khi luồng đã vào monitor và tạm nhả để chờ điều kiện; không đánh đồng hai loại chờ.

Chọn `lockInterruptibly` khi thao tác có thể chờ không giới hạn về thời gian nhưng phải tuân theo yêu cầu hủy. Chọn timed `tryLock` nếu còn cần giới hạn thời gian lấy. Với timed `tryLock`, cũng chỉ nhả khi kết quả là `true`.

Các khả năng và nghĩa vụ triển khai của giao diện được trình bày trong [Lock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html#lockInterruptibly()).

## 7. Sau khi đã lấy khóa, khả năng ngắt vẫn phụ thuộc đoạn xử lý

Ngay sau khi `lockInterruptibly()` trả về, một luồng khác vẫn có thể gửi ngắt. Phương thức lấy khóa không biến mọi câu lệnh phía sau thành một điểm hủy tự động.

Nếu đoạn tới hạn chỉ tính toán CPU dài mà không kiểm tra ngắt, nó vẫn có thể tiếp tục chạy. Nếu gọi API khác phản hồi ngắt, API đó có thể ném và luồng phải dọn dẹp theo hợp đồng tương ứng. Trong cả hai trường hợp, `finally` vẫn là nơi bảo đảm nhả quyền giữ khóa đã lấy.

Yêu cầu hủy không tự hoàn tác thay đổi dữ liệu đã làm trước đó. Nếu cập nhật nhiều trường, cần giữ bất biến dữ liệu ngay cả khi thoát do ngắt hoặc ngoại lệ: có thể tính trước rồi công bố, dùng bước hoàn tác rõ ràng, hoặc thiết kế điểm hủy nằm giữa các thao tác hoàn chỉnh.

## 8. Khi có nhiều khóa hoặc nhiều tài nguyên

Giả sử tác vụ đã giữ khóa A rồi chờ khóa B bằng `lockInterruptibly()`. Nếu việc chờ B bị ngắt, chỉ lần lấy B thất bại; A vẫn thuộc tác vụ. Khối quản lý A phải nhả A trong đường thoát.

```java
// Đoạn minh họa trong phương thức throws InterruptedException.
first.lockInterruptibly();
try {
    second.lockInterruptibly();
    try {
        // Thao tác cần cả hai khóa.
    } finally {
        second.unlock();
    }
} finally {
    first.unlock();
}
```

Nếu bị ngắt khi lấy `second`, khối nhả `second` chưa được vào, còn `finally` ngoài vẫn nhả `first`. Mẫu này không tự ngăn vòng chờ giữa hai luồng lấy khóa theo thứ tự ngược nhau; cần thứ tự lấy thống nhất hoặc thiết kế tránh deadlock. Khả năng ngắt chỉ giúp một tác vụ có đường từ bỏ khi nhận yêu cầu, không thay thế thiết kế tránh chu trình.

Nguyên tắc tương tự áp dụng cho tệp, kết nối hoặc tài nguyên khác đã nhận trước khi chờ khóa: hủy chờ không tự giải phóng tất cả tài nguyên của tác vụ.

## 9. Những lỗi thường gặp

- Dùng `lock()` nhưng kỳ vọng `interrupt()` chắc chắn làm luồng bỏ chờ.
- Đặt `unlock()` trong `finally` bao cả lần lấy chưa thành công.
- Nhận `InterruptedException` rồi vẫn đi vào đoạn xử lý cần khóa.
- Khôi phục cờ nhưng thử lấy lại vô hạn, khiến tác vụ không thực sự kết thúc.
- Giữ khóa A khi chờ tác vụ khác hoàn tất, trong khi tác vụ ấy cần A để dọn dẹp.
- Cho rằng khóa rảnh hoặc đang do cùng luồng giữ thì `lockInterruptibly()` không thể ném vì cờ ngắt có sẵn.
- Coi yêu cầu ngắt là bảo đảm mọi thay đổi nghiệp vụ trước đó đã được hoàn tác.

## 10. Tự kiểm tra

1. Luồng bị ngắt trước khi gọi `lockInterruptibly` trên khóa rảnh có thể nhận ngoại lệ không? Có, với `ReentrantLock`.
2. Lời gọi lấy khóa ném `InterruptedException`; có nhả thêm khóa cho lần gọi thất bại đó không? Không.
3. Sau khi ngoại lệ được ném, cờ ngắt còn `true` mặc định không? Không; hợp đồng xóa cờ, tầng xử lý quyết định chuyển/khôi phục đúng chính sách.
4. `interrupt()` có nhả khóa do luồng khác đang giữ không? Không.
5. Lấy khóa thành công có làm mọi đoạn tính toán phía sau tự bị hủy khi ngắt không? Không; đoạn xử lý phải hợp tác.
6. Tác vụ đang giữ khóa A rồi bị ngắt khi lấy B có mất quyền giữ A không? Không; cần nhả A trên đường thoát tương ứng.
