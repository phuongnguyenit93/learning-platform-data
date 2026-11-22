# Ngắt luồng đang chờ và quản lý thời hạn với BlockingQueue

Một luồng gọi `take()` trên hàng đợi rỗng có thể chờ mãi nếu không còn bên sản xuất. Tương tự, `put()` có thể mắc kẹt khi hàng đợi đầy và bên tiêu thụ đã dừng. Vì vậy, thiết kế hàng đợi cần trả lời hai câu hỏi: **ai có thể yêu cầu dừng việc chờ, và việc chờ được phép kéo dài bao lâu?**

Bài này dùng cơ chế ngắt hợp tác và các phương thức có thời gian chờ của `BlockingQueue`. Các cơ chế này vẫn áp dụng trong Java hiện đại; ví dụ biên dịch với Java 17 trở lên.

## 1. Phân biệt chờ, hết thời gian và yêu cầu hủy

| Tình huống | Phương thức | Kết quả cần xử lý |
|---|---|---|
| Chờ có phần tử, không đặt thời gian chờ | `take()` | Trả phần tử hoặc ném `InterruptedException` khi bị ngắt lúc chờ |
| Chờ có chỗ, không đặt thời gian chờ | `put(e)` | Thêm thành công hoặc ném `InterruptedException` khi bị ngắt lúc chờ |
| Chờ phần tử trong thời gian cho phép | `poll(timeout, unit)` | Trả phần tử; trả `null` nếu hết thời gian chờ mà chưa lấy được |
| Chờ chỗ trống trong thời gian cho phép | `offer(e, timeout, unit)` | Trả `true` nếu thêm được; `false` nếu hết thời gian chờ mà chưa thêm được |

Hai phương thức có thời gian chờ cũng có thể ném `InterruptedException`. Hết thời gian chờ là một kết quả bình thường của API, khác với tín hiệu yêu cầu hủy. `BlockingQueue` không nhận phần tử `null`, nên `null` từ `poll` không phải một công việc hợp lệ. Xem hợp đồng tại [BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Thời gian chờ của một lần `poll` không bao gồm thời gian xử lý công việc sau khi lấy ra. Nếu hệ thống hứa hoàn thành yêu cầu trong một giây, chỉ đặt `poll(1, SECONDS)` là chưa đủ.

## 2. Ngắt là yêu cầu hợp tác

`worker.interrupt()` gửi tín hiệu tới luồng `worker`; nó không cưỡng bức kết thúc luồng và không phải lệnh đóng hàng đợi. Luồng cần phản ứng bằng cách thoát khỏi thao tác chờ, kết thúc vòng lặp hoặc truyền yêu cầu hủy lên bên gọi. Luồng đang xử lý tính toán cũng cần điểm kiểm tra ngắt phù hợp. Hợp đồng về trạng thái ngắt được mô tả trong [Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

Có hai cách xử lý thường dùng:

- **Hàm tiện ích cho phép bên gọi quyết định:** khai báo `throws InterruptedException` và truyền ngoại lệ lên.
- **Biên thực thi như `Runnable.run()` không khai báo ngoại lệ này:** kết thúc tác vụ; thường khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` để giữ tín hiệu cho mã bao quanh có thể quan sát.

Ví dụ sau là đoạn minh họa trong một lớp đã có trường `queue` và hàm `process`, không phải chương trình độc lập:

```java
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String job = queue.take();
            process(job);
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        // Thoát run; không quay lại vòng lặp chờ.
    }
}
```

Khi một thao tác chờ ném `InterruptedException`, cờ ngắt thường đã được xóa. `isInterrupted()` chỉ đọc cờ; phương thức tĩnh `Thread.interrupted()` đọc rồi xóa cờ của **luồng hiện tại**. Không dùng phương thức thứ hai chỉ để xem trạng thái khi vẫn cần giữ tín hiệu.

Nếu hàm chủ động dùng `Thread.interrupted()` rồi ném `InterruptedException`, việc xóa cờ là có chủ đích: tín hiệu được truyền bằng ngoại lệ. Ngược lại, bắt ngoại lệ rồi bỏ qua và tiếp tục `take()` dễ làm yêu cầu dừng bị mất.

Việc luồng sở hữu toàn bộ chính sách ngắt bắt ngoại lệ rồi kết thúc ngay cũng là hợp lệ; khôi phục cờ không phải nghi thức bắt buộc trước mọi lệnh thoát. Điều cần giữ là ý nghĩa hủy, không vô tình nuốt tín hiệu.

## 3. Thời gian chờ từng lần và ngân sách chung

Giả sử cần nhận tối đa ba thông điệp trong tổng cộng 500 ms. Đoạn sau chỉ minh họa một lỗi thiết kế:

```java
// Sai nếu yêu cầu là tổng thời gian chờ 500 ms cho cả nhóm.
for (int i = 0; i < 3; i++) {
    String item = queue.poll(500, TimeUnit.MILLISECONDS);
    if (item != null) {
        handle(item);
    }
}
```

Mỗi vòng lại nhận đủ 500 ms; riêng ba lần chờ có thể dùng khoảng 1.500 ms. Cách làm phù hợp là ghi nhận thời điểm bắt đầu một lần, sau đó tính phần còn lại trước từng thao tác:

```text
thời gian đã dùng = nanoTime hiện tại - nanoTime bắt đầu
thời gian còn lại = ngân sách - thời gian đã dùng
```

Dùng `System.nanoTime()` để đo khoảng thời gian trong cùng JVM; không dùng nó như giờ lịch, không lưu giá trị để trao đổi thời hạn giữa các máy. Phép trừ để đo thời gian đã trôi tránh cách so sánh trực tiếp hai mốc có thể tràn số; khoảng đo phải dưới khoảng 292 năm. Đồng hồ hệ thống từ `currentTimeMillis()` có thể bị điều chỉnh nên không phù hợp cho ngân sách chờ nội bộ. Xem [System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

Khi phần còn lại không dương, phải có chính sách rõ ràng. Ví dụ dưới chọn dừng ngay, kể cả hàng đợi đang có dữ liệu. Một hệ thống khác có thể cho phép một lần `poll()` không chờ, nhưng cần ghi rõ ý nghĩa đó.

**Ngân sách không phải bảo đảm thời gian thực.** Bộ lập lịch, việc lấy khóa và thời gian chạy mã có thể làm hàm trở về trễ hơn mốc mong muốn. Nó giúp không chủ động cấp lại toàn bộ thời gian chờ sau mỗi bước. Nếu cần giới hạn cả xử lý, I/O và các lần thử lại, những bước đó cũng phải nhận ngân sách còn lại và hỗ trợ hủy riêng.

## 4. Chương trình chạy đầy đủ

Lưu thành `QueueWaitingDemo.java`. Chương trình minh họa ba việc: hủy bên tiêu thụ không có dữ liệu, hết thời gian chờ khi thêm/lấy, và chia sẻ một ngân sách giữa nhiều lần lấy.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class QueueWaitingDemo {
    static List<String> collectWithin(
            BlockingQueue<String> queue, int maxItems,
            long timeout, TimeUnit unit) throws InterruptedException {
        if (maxItems < 0 || timeout < 0) {
            throw new IllegalArgumentException("Negative limit");
        }

        long budget = unit.toNanos(timeout);
        long started = System.nanoTime();
        List<String> result = new ArrayList<>();

        while (result.size() < maxItems) {
            if (Thread.interrupted()) {
                throw new InterruptedException();
            }
            long remaining = budget - (System.nanoTime() - started);
            if (remaining <= 0) {
                break;
            }
            String value = queue.poll(remaining, TimeUnit.NANOSECONDS);
            if (value == null) {
                break;
            }
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> empty = new ArrayBlockingQueue<>(1);
        CountDownLatch ready = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            try {
                ready.countDown();
                empty.take();
                throw new AssertionError("No producer exists");
            } catch (InterruptedException e) {
                System.out.println("consumer: interrupted");
                System.out.println("flag before restore: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("flag after restore: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "consumer");

        consumer.start();
        ready.await();
        consumer.interrupt();
        consumer.join();
        System.out.println("consumer alive: " + consumer.isAlive());

        BlockingQueue<String> full = new ArrayBlockingQueue<>(1);
        full.put("occupied");
        boolean accepted = full.offer("new", 20, TimeUnit.MILLISECONDS);
        System.out.println("accepted: " + accepted);
        System.out.println("head: " + full.peek());

        BlockingQueue<String> missing = new ArrayBlockingQueue<>(1);
        String value = missing.poll(20, TimeUnit.MILLISECONDS);
        System.out.println("missing: " + value);

        BlockingQueue<String> batch = new ArrayBlockingQueue<>(2);
        batch.put("first");
        List<String> collected =
                collectWithin(batch, 2, 20, TimeUnit.MILLISECONDS);
        System.out.println("collected fewer than two: "
                + (collected.size() < 2));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 --release 17 QueueWaitingDemo.java
java QueueWaitingDemo
```

Với một lượt chạy bình thường, không có luồng bên ngoài ngắt `main`, stdout là:

```text
consumer: interrupted
flag before restore: false
flag after restore: true
consumer alive: false
accepted: false
head: occupied
missing: null
collected fewer than two: true
```

Giải thích:

1. Không có bên sản xuất cho `empty`, nên `take()` không thể thành công. Chốt `ready` báo rằng luồng đã đi tới trước lời gọi; nó không chứng minh luồng đã nằm trong trạng thái chờ. Dù tín hiệu ngắt đến ngay trước hay trong lúc `ArrayBlockingQueue.take()` chờ, nhánh bắt ngắt vẫn hoạt động trong ví dụ.
2. Không có lần ngắt thứ hai, nên cờ là `false` khi bắt ngoại lệ và thành `true` sau khi khôi phục. `join()` chờ luồng con kết thúc trước khi in các phần tiếp theo.
3. `full` chứa đúng một phần tử và không có bên tiêu thụ: `offer` có thời gian chờ trả `false`, phần tử cũ vẫn còn. `missing` không có bên sản xuất: `poll` trả `null`. Đây là hành vi cụ thể của hàng đợi có dung lượng cố định [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).
4. `collectWithin` không cấp lại 20 ms cho mỗi phần tử. Nó có thể thu được 0 hoặc 1 phần tử tùy tiến độ lập lịch; không thể thu đủ hai vì chỉ có một phần tử và không có bên sản xuất. Vì thế stdout kiểm tra điều kiện ổn định thay vì khẳng định một số đo thời gian hay số phần tử phụ thuộc lịch chạy.

`collectWithin` có chính sách trả kết quả từng phần khi hết ngân sách; thời hạn bằng 0 trả danh sách rỗng. Nó truyền ngắt bằng ngoại lệ. **Nếu đã lấy vài phần tử rồi mới bị ngắt, các phần tử đó đã rời hàng đợi, nhưng hàm không trả danh sách vì ngoại lệ.** Đây là lựa chọn minh họa, chỉ phù hợp khi bên gọi chấp nhận bỏ nhóm đang thu thập. Với công việc cần bảo toàn, phải thiết kế thêm nơi ghi nhận phần đã nhận, cơ chế xác nhận/đưa lại hoặc loại kết quả mang trạng thái hủy và dữ liệu từng phần. `BlockingQueue` tự nó không cung cấp giao dịch hay bảo đảm xử lý đúng một lần.

## 5. Quyền sở hữu công việc và dừng hệ thống

Ngắt và thời hạn thường bộc lộ lỗi ở ranh giới nhận công việc:

- `poll` trả phần tử: luồng đã nhận quyền xử lý phần tử đó. Một lần ngắt đến sau kết quả thành công không tự đặt phần tử trở lại hàng đợi.
- `offer` trả `false`: lần gọi đó chưa thêm công việc; bên gửi quyết định từ chối, ghi nhận lỗi hay thử lại trong ngân sách còn lại.
- Nhận công việc rồi xử lý lỗi: cần chính sách thử lại và chống xử lý trùng ở tầng nghiệp vụ, thay vì coi hàng đợi bộ nhớ là cơ chế xác nhận bền vững.

Không dùng `isEmpty()` rồi mới `take()` để tránh chờ: luồng khác có thể lấy mất phần tử giữa hai thao tác. Không tự bao hàng đợi bằng một khóa ngoài mà bên sản xuất cũng cần rồi gọi hàm chờ; điều đó có thể chặn chính bên có khả năng giải phóng tình trạng chờ.

Khi dừng dịch vụ, chọn rõ mục tiêu: hủy ngay hay xử lý hết công việc đã nhận. Ngắt bên tiêu thụ đang chờ thường phù hợp với hủy nhanh; nó không tự hoàn thành chiến lược xử lý hết hàng đợi. Cần quản lý cả bên sản xuất, bên tiêu thụ và việc chờ chúng kết thúc. Không có thao tác `close()` chung trên `BlockingQueue`; dấu kết thúc là giao thức ứng dụng, không thay thế mặc nhiên cho mọi tình huống hủy. [Hợp đồng vòng đời BlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

## 6. Tự kiểm tra

1. Nếu bắt `InterruptedException` rồi lại gọi `take()` trong vòng lặp, tín hiệu dừng có còn hiệu lực không? — Có thể đã bị mất vì cờ bị xóa và chương trình tiếp tục chờ.
2. Ba lần `poll(1, SECONDS)` có giới hạn cả yêu cầu trong một giây không? — Không; cần ngân sách chung và giới hạn cả các công đoạn khác.
3. `poll` trả `null` có nghĩa hàng đợi đã đóng không? — Không; đó là kết quả hết thời gian chờ mà chưa lấy được phần tử.
4. Đã lấy phần tử rồi mới phát hiện yêu cầu hủy thì ai bảo toàn công việc? — Giao thức ứng dụng phải quyết định; ngắt luồng không hoàn tác thao tác hàng đợi.
