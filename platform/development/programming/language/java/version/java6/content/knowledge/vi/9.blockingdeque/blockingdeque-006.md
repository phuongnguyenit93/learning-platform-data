# InterruptedException và hủy tác vụ hợp tác với BlockingDeque

## 1. Vấn đề: làm sao dừng một tác vụ đang chờ?

Một tác vụ lấy công việc từ `BlockingDeque` có thể chờ rất lâu khi hàng đợi rỗng. Ngược lại, bên tạo công việc có thể chờ khi deque có giới hạn dung lượng và đã đầy. Khi ứng dụng cần dừng tác vụ, chỉ đổi một biến `running` thành `false` chưa đủ: luồng đang mắc trong lời gọi chờ chưa quay về vòng lặp để đọc biến đó.

Hủy tác vụ hợp tác (cooperative cancellation) là cách bên quản lý gửi yêu cầu dừng, còn tác vụ tự phản hồi tại những điểm phù hợp, kết thúc công việc và giải phóng tài nguyên. Trong Java, ngắt luồng (interrupt) là tín hiệu thường dùng cho mục đích này.

Cần phân biệt ba việc:

- **Gửi yêu cầu:** gọi `interrupt()` trên luồng chạy tác vụ.
- **Nhận biết yêu cầu:** quan sát trạng thái ngắt hoặc nhận `InterruptedException` từ thao tác chờ có hỗ trợ ngắt.
- **Hoàn tất dừng:** thoát luồng điều khiển của tác vụ sau khi xử lý tài nguyên và trạng thái nghiệp vụ cần thiết.

Gửi yêu cầu không đồng nghĩa tác vụ đã dừng. Việc dừng nhanh hay chậm phụ thuộc vào những đoạn mã tác vụ thực thi.

Bài này tập trung vào các API hiện hành và ví dụ chạy với Java 17 trở lên. Mối liên hệ với Java 6 là `BlockingDeque` đã có từ phiên bản đó; cơ chế dưới đây vẫn hữu ích khi viết chương trình Java hiện nay.

## 2. Hai đường nhận tín hiệu ngắt

### 2.1. Khi đang chờ trên deque

Các thao tác sau cho phép luồng chờ và khai báo `throws InterruptedException`:

| Nhu cầu | Phương thức ở đầu/cuối deque | Kết quả thông thường |
| --- | --- | --- |
| Lấy phần tử, chờ nếu rỗng | `takeFirst()`, `takeLast()` | Phần tử đã lấy |
| Thêm phần tử, chờ nếu đầy | `putFirst(e)`, `putLast(e)` | Hoàn tất thêm |
| Lấy với thời gian chờ giới hạn | `pollFirst(t, unit)`, `pollLast(t, unit)` | Phần tử hoặc `null` khi hết thời gian |
| Thêm với thời gian chờ giới hạn | `offerFirst(e, t, unit)`, `offerLast(e, t, unit)` | `true` khi thêm được, `false` khi hết thời gian |

`take()` tương ứng `takeFirst()`; `put(e)` tương ứng `putLast(e)`. Bản có thời gian chờ vẫn có thể bị ngắt, không phải chỉ có hai kết quả thành công và hết thời gian. Xem [hợp đồng BlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Khi dùng `LinkedBlockingDeque`, việc ném `InterruptedException` từ thao tác chờ đi kèm với xóa trạng thái ngắt của luồng hiện tại. Vì thế trong `catch`, không được kỳ vọng `isInterrupted()` vẫn là `true`. Chính ngoại lệ đang mang thông tin “thao tác đã bị ngắt”.

Không nên dựa vào giả định “deque đang có phần tử nên lời gọi này chắc chắn không phản hồi ngắt”. Thời điểm ngắt và thời điểm thực hiện thao tác có thể xen kẽ; hãy xử lý đầy đủ hợp đồng của phương thức.

### 2.2. Khi đang tính toán

Một vòng lặp tính toán thông thường không tự ném `InterruptedException`. Tác vụ phải chủ động kiểm tra trạng thái ngắt ở các ranh giới công việc đủ nhỏ:

```java
// Đoạn minh họa bên trong tác vụ, không phải chương trình độc lập.
for (int chunk = 0; chunk < chunkCount; chunk++) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }
    calculateChunk(chunk);
}
```

`chunkCount` và `calculateChunk` thuộc ứng dụng. Mục đích chia thành từng phần là tránh để một lần tính toán rất dài trì hoãn phản hồi hủy.

## 3. Trạng thái ngắt: đọc, xóa và khôi phục

| API | Ý nghĩa trong luồng điều khiển |
| --- | --- |
| `worker.interrupt()` | Gửi tín hiệu tới luồng `worker` |
| `Thread.currentThread().isInterrupted()` | Đọc trạng thái của luồng hiện tại, không xóa |
| `Thread.interrupted()` | Đọc rồi xóa trạng thái của luồng hiện tại |
| `Thread.currentThread().interrupt()` trong `catch` | Đặt lại trạng thái cho chính luồng đang xử lý ngoại lệ |

Không dùng `Thread.interrupted()` chỉ để kiểm tra trong điều kiện lặp nếu chưa chủ ý tiêu thụ tín hiệu. Một lần đọc bằng phương thức này có thể làm mã phía sau không còn thấy yêu cầu hủy.

Khôi phục cờ cũng không tự thoát vòng lặp. Sau khi khôi phục, luồng điều khiển phải đi tới `return`, `break` hoặc kết thúc phương thức theo chính sách của tác vụ. Các API trạng thái ngắt được mô tả trong [tài liệu Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

## 4. Chọn một trong hai cách xử lý ngoại lệ

### 4.1. Truyền ngoại lệ lên nơi có quyền quyết định

Nếu phương thức của bạn được phép khai báo `throws InterruptedException`, thường nên để ngoại lệ đi lên:

```java
import java.util.concurrent.BlockingDeque;

// Một phương thức tiện ích; bên gọi quyết định cách hủy.
static <E> E receive(BlockingDeque<E> deque)
        throws InterruptedException {
    return deque.takeFirst();
}
```

Đoạn trên là thành viên của một lớp, không phải tệp chạy độc lập. Phương thức không che giấu yêu cầu ngắt, cũng không tự biến nó thành kết quả “không có công việc”.

Không cần bắt chỉ để khôi phục cờ rồi ném lại chính `InterruptedException`: ở đây ngoại lệ đã truyền thông tin hủy cho bên gọi. Nếu cần dọn tài nguyên, có thể dùng `finally` mà vẫn để ngoại lệ truyền lên.

### 4.2. Khôi phục trạng thái và kết thúc tại ranh giới Runnable

`Runnable.run()` không khai báo ngoại lệ kiểm tra. Tại ranh giới này, mẫu thông dụng là:

```java
// Đoạn minh họa trong Runnable; process là hàm của ứng dụng.
try {
    while (!Thread.currentThread().isInterrupted()) {
        String job = deque.takeFirst();
        process(job);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Kết thúc tác vụ sau catch; không quay lại vòng lặp.
} finally {
    // Giải phóng tài nguyên do tác vụ sở hữu.
}
```

Đặt `catch` bên ngoài vòng lặp giúp thể hiện rõ: một lần nhận ngắt sẽ kết thúc toàn bộ tác vụ. `finally` chỉ giải phóng tài nguyên thuộc quyền sở hữu của tác vụ; không tự đóng tài nguyên dùng chung của nhiều tác vụ.

Một tác vụ ở điểm kết thúc cao nhất có thể có chính sách xử lý ngắt riêng. Điều quan trọng là chính sách đó phải rõ ràng; không để một hàm tiện ích âm thầm ăn mất tín hiệu mà tầng quản lý đang trông đợi.

## 5. Ví dụ chạy đầy đủ: hủy bên nhận và bên gửi

Chương trình tạo hai tình huống tách biệt:

1. Deque rỗng: bên nhận không có phần tử để lấy.
2. Deque dung lượng một đã đầy: bên gửi không có chỗ để thêm.

`CountDownLatch` cho biết luồng phụ đã tới ngay trước thao tác deque. Nó không chứng minh luồng phụ đã thật sự chuyển sang trạng thái chờ. Điều này có chủ ý: chương trình vẫn đúng nếu yêu cầu ngắt đến ngay trước khi thao tác bắt đầu hoặc trong lúc thao tác đang chờ.

Lưu tệp **DequeCancellationDemo.java**:

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingDeque;

public class DequeCancellationDemo {
    private static void cancelConsumer() throws InterruptedException {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(1);
        CountDownLatch ready = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            try {
                ready.countDown();
                deque.takeFirst();
                throw new AssertionError("No item should be available");
            } catch (InterruptedException e) {
                System.out.println("consumer caught: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("consumer restored: "
                        + Thread.currentThread().isInterrupted());
            } finally {
                System.out.println("consumer cleanup");
            }
        }, "consumer");

        consumer.start();
        ready.await();
        consumer.interrupt();
        consumer.join();

        System.out.println("consumer alive: " + consumer.isAlive());
        System.out.println("consumer deque size: " + deque.size());
    }

    private static void cancelProducer() throws InterruptedException {
        BlockingDeque<String> deque = new LinkedBlockingDeque<>(1);
        deque.putLast("existing");
        CountDownLatch ready = new CountDownLatch(1);

        Thread producer = new Thread(() -> {
            try {
                ready.countDown();
                deque.putLast("new");
                throw new AssertionError("No space should be available");
            } catch (InterruptedException e) {
                System.out.println("producer caught: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("producer restored: "
                        + Thread.currentThread().isInterrupted());
            } finally {
                System.out.println("producer cleanup");
            }
        }, "producer");

        producer.start();
        ready.await();
        producer.interrupt();
        producer.join();

        System.out.println("producer alive: " + producer.isAlive());
        System.out.println("producer deque: " + deque);
    }

    public static void main(String[] args) throws InterruptedException {
        cancelConsumer();
        cancelProducer();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac DequeCancellationDemo.java
java DequeCancellationDemo
```

Stdout:

```text
consumer caught: false
consumer restored: true
consumer cleanup
consumer alive: false
consumer deque size: 0
producer caught: false
producer restored: true
producer cleanup
producer alive: false
producer deque: [existing]
```

Giải thích các điểm quan sát:

- `caught: false` cho thấy trạng thái đã được xóa khi ngoại lệ được ném trong hai thao tác này.
- `restored: true` xác minh đoạn `catch` đã bảo toàn tín hiệu trước khi kết thúc.
- `cleanup` xuất hiện vì `finally` vẫn chạy khi tác vụ rời thao tác chờ.
- `join()` giúp luồng chính đợi luồng phụ kết thúc rồi mới in `alive` và trạng thái deque. Thứ tự stdout không phụ thuộc vào việc đoán thời gian bằng `sleep`.
- Bên nhận không lấy được phần tử; bên gửi không thêm `"new"`. Phần tử `"existing"` vẫn còn nguyên trong deque của bên gửi.

Ví dụ không dùng deque không giới hạn cho tình huống bên gửi: phải tạo deque có giới hạn nhỏ và nạp đầy trước thì mới chắc chắn không có chỗ trống. Xem [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

## 6. Hết thời gian chờ khác với bị hủy

Với `pollFirst(timeout, unit)`, `null` chỉ nói rằng lần chờ này không lấy được phần tử trong thời gian cho phép. Nó không tự định nghĩa “tác vụ cần dừng”. Ngược lại, `InterruptedException` báo luồng điều khiển cần xử lý ngắt.

Ví dụ một vòng nhận có thời gian chờ:

```java
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.TimeUnit;

// Phương thức thành viên minh họa, không phải chương trình độc lập.
static void receiveUntilInterrupted(BlockingDeque<String> deque) {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String job = deque.pollFirst(1, TimeUnit.SECONDS);
            if (job == null) {
                continue; // Chưa có việc; chưa đồng nghĩa phải dừng.
            }
            System.out.println("received: " + job);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    }
}
```

Trong ứng dụng thật, thời gian chờ có thể là dịp kiểm tra hạn chót hoặc một điều kiện dừng khác. Nếu dùng một cờ được luồng khác thay đổi, cần cơ chế bảo đảm khả năng nhìn thấy như `volatile` hoặc `AtomicBoolean`. Cờ đó vẫn không đánh thức một `takeFirst()` đang chờ vô hạn; hãy phối hợp với ngắt hoặc một giao thức đánh thức rõ ràng.

Không thay `takeFirst()` bằng vòng `pollFirst()` không có thời gian chờ rồi lặp liên tục. Việc quay vòng khi deque rỗng tiêu tốn CPU mà không bổ sung một chính sách hủy có ích.

## 7. Tác vụ đã lấy phần tử: deque không quản lý phần việc đang xử lý

Hãy xét trình tự:

```text
takeFirst() trả về job
        ↓
job không còn trong deque
        ↓
tác vụ bắt đầu xử lý job
        ↓
yêu cầu ngắt đến
```

Nếu `takeFirst()` đã thành công, ngắt sau đó không tự đưa phần tử trở lại. Deque cũng không tự hoàn tác thay đổi cơ sở dữ liệu, tệp hoặc yêu cầu HTTP mà mã xử lý đã thực hiện.

Vì vậy cần thiết kế rõ hai chính sách riêng:

- **Chính sách dừng:** dừng trước việc tiếp theo, hay cho phép hoàn tất phần việc hiện tại?
- **Chính sách công việc dang dở:** bỏ có chủ ý, ghi nhận để xử lý lại, hay chuyển sang cơ chế lưu trữ bền vững có xác nhận hoàn tất?

Với xử lý có tác dụng phụ, khả năng chạy lại an toàn (idempotency) và ranh giới giao dịch cần được quyết định ở tầng nghiệp vụ. Một deque trong bộ nhớ không cung cấp bảo đảm “xử lý đúng một lần”.

Nếu muốn kiểm tra ngắt ngay sau khi lấy nhưng trước khi xử lý, phải đồng thời giải quyết quyền sở hữu phần tử vừa lấy. Thêm một `if (isInterrupted()) return;` vào chỗ đó mà không xử lý công việc dang dở có thể làm mất việc.

Cũng không tự động `putFirst(job)` vô hạn trong `finally`: deque có thể đã đầy bởi bên gửi khác, tất cả bên nhận có thể đang dừng, hoặc cờ ngắt vẫn đang bật. Hệ quả có thể là chờ không kết thúc hoặc lại nhận ngoại lệ. Cách chuyển việc dang dở phải có giới hạn và một lối xử lý thất bại được thiết kế trước.

## 8. Hủy một luồng không đóng toàn bộ deque

`interrupt()` gửi tới một luồng cụ thể. Nếu có nhiều bên gửi và nhiều bên nhận, ngắt một bên không tự ngắt các bên còn lại và không tạo trạng thái “đã đóng” cho `BlockingDeque`.

Hai mục tiêu dừng thường gặp cần giao thức khác nhau:

| Mục tiêu | Hướng thiết kế |
| --- | --- |
| Dừng nhanh tác vụ đang chờ | Gửi ngắt tới các tác vụ do thành phần quản lý sở hữu; xử lý phần việc dang dở |
| Hoàn tất công việc đã nhận rồi dừng | Ngừng nhận việc mới; phối hợp bên gửi/bên nhận để tiêu thụ hết phần việc còn lại; xác nhận hoàn tất |
| Đợi tác vụ dừng trong thời gian giới hạn | Gửi yêu cầu rồi đợi có giới hạn; báo rõ tác vụ chưa dừng nếu hết thời gian |

Không dùng `isEmpty()` tại một thời điểm làm bằng chứng tất cả công việc đã hoàn tất: bên nhận có thể đang xử lý phần tử đã lấy, hoặc bên gửi vẫn còn khả năng thêm việc mới.

Nếu lựa chọn phần tử báo kết thúc thay cho ngắt để dừng có trật tự, phải thiết kế rõ việc dừng bên gửi, số lượng bên nhận và thứ tự lấy ở hai đầu. Đây là giao thức của ứng dụng; nó không phải một trạng thái đóng có sẵn của deque.

## 9. Khi tác vụ chạy trong ExecutorService

Khi nộp tác vụ vào bộ thực thi, hãy giữ `Future` của tác vụ để có thể gửi yêu cầu hủy ở cấp tác vụ. Tránh tự giữ rồi ngắt một luồng bất kỳ của bộ thực thi: luồng đó thuộc bộ thực thi và có thể đã chuyển sang chạy công việc khác.

`future.cancel(true)` có thể cố gắng ngắt luồng đang chạy nếu cách triển khai hỗ trợ và biết luồng đó. Với tác vụ thông thường được nộp qua `ExecutorService.submit`, mã tác vụ vẫn phải xử lý ngắt hợp tác. Đừng suy rộng rằng mọi kiểu `Future` đều có cùng hành vi ngắt.

Một `Future` đã mang trạng thái hủy cũng không chứng minh mã tác vụ đã hoàn tất dọn tài nguyên. Nếu cần xác nhận giai đoạn dọn dẹp hoàn thành, hãy có tín hiệu hoàn tất riêng hoặc quản lý việc kết thúc bộ thực thi theo phạm vi sở hữu. Tham khảo [Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean)).

## 10. Những lỗi dễ làm hỏng cơ chế hủy

### Bắt ngoại lệ rồi tiếp tục chờ

```java
// Mẫu sai: minh họa việc làm mất yêu cầu dừng.
while (true) {
    try {
        deque.takeFirst();
    } catch (InterruptedException e) {
        System.out.println("interrupted");
    }
}
```

Ghi log không thay thế quyết định dừng. Sau `catch`, vòng lặp có thể trở lại chờ và tác vụ tiếp tục sống.

### Khôi phục trạng thái nhưng vẫn lặp vô hạn

Nếu `catch` nằm trong `while (true)`, khôi phục cờ rồi gọi lại thao tác chờ có hỗ trợ ngắt có thể làm ngoại lệ xảy ra lặp lại nhanh. Phải đổi luồng điều khiển để rời tác vụ; chỉ đặt lại cờ chưa đủ.

### Bắt Exception quá rộng

Một `catch (Exception e)` dùng chung cho lỗi nghiệp vụ và ngắt dễ dẫn tới “ghi log rồi thử lại” cho mọi lỗi. Nếu cần bắt rộng, xử lý `InterruptedException` riêng trước, rồi áp dụng chính sách cho các lỗi khác. Không biến yêu cầu hủy thành việc tự động thử lại vô hạn.

### Kiểm tra cờ một lần trước phần việc quá lớn

Một lần kiểm tra ở đầu vòng lặp không làm cho mọi mã bên trong đều có thể dừng. Nếu `process(job)` tính toán rất lâu hoặc gọi API không hỗ trợ ngắt, cần điểm kiểm tra, hạn chót hoặc cơ chế hủy đặc thù của tài nguyên đó.

### Xem ngắt là hoàn tác hoặc là xác nhận hoàn tất

Yêu cầu ngắt không rút lại phần tử đã được thêm thành công và không tự hoàn tác phần việc đã xử lý. Bên quản lý cần phân biệt “đã gửi yêu cầu” với “tác vụ đã kết thúc”.

## 11. Tự thực hành

1. Trong ví dụ đầy đủ, thay `takeFirst()` bằng `takeLast()`: cơ chế hủy có thay đổi không? Giải thích vì sao hai đầu deque không tạo hai chính sách ngắt khác nhau.
2. Thay `putLast("new")` bằng `putFirst("new")` khi deque vẫn đầy. Dự đoán và kiểm tra phần tử còn lại sau hủy.
3. Xóa dòng khôi phục cờ trong một nhánh `catch`. Quan sát dòng `restored`; giải thích vì sao tác vụ vẫn có thể kết thúc nhưng đã không bảo toàn trạng thái ngắt.
4. Thiết kế bằng lời chính sách xử lý một công việc đã rời deque nhưng mới cập nhật dữ liệu được một phần. Nêu rõ khi nào được thử lại và làm sao tránh tạo tác dụng phụ trùng lặp.

Khi áp dụng, hãy xác định đồng thời nơi nhận ngắt, nơi quyết định kết thúc, phần tài nguyên tác vụ sở hữu và số phận công việc dang dở. Bốn quyết định này biến một tín hiệu ngắt thành một cơ chế hủy có thể kiểm soát.
