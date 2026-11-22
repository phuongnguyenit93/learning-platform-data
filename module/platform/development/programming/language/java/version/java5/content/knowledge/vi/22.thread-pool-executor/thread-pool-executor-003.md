# Vai trò của workQueue trong quyết định tạo luồng

## 1. Hàng đợi không chỉ là chỗ chứa việc chưa chạy

Trong `ThreadPoolExecutor`, hàng đợi công việc `workQueue` nằm giữa hai quyết định: **giữ tác vụ lại để luồng hiện có xử lý sau** hoặc **tạo thêm luồng để xử lý ngay**.

Vì vậy, cấu hình `maximumPoolSize = 20` không có nghĩa executor sẽ tăng lên 20 luồng mỗi khi tải tăng. Nếu hàng đợi vẫn nhận được việc sau khi đã đạt mức lõi, executor thường tiếp tục xếp hàng trước. Chính khả năng nhận việc của hàng đợi quyết định khi nào nhánh tăng vượt mức lõi được xét.

Ba thuật ngữ cần dùng:

- **Luồng thực thi**: luồng đang chạy hoặc chờ nhận công việc trong nhóm; không đồng nghĩa với tác vụ.
- **Mức lõi (`corePoolSize`)**: ngưỡng ưu tiên tạo luồng ở giai đoạn đầu tiếp nhận.
- **Mức tối đa (`maximumPoolSize`)**: trần cấu hình cho việc thêm luồng khi không xếp được việc vào hàng đợi.

Bài xét `ThreadPoolExecutor` chuẩn đang hoạt động bình thường, tài nguyên tạo luồng còn đủ, không có tùy biến làm thay đổi cơ chế. Các API này vẫn áp dụng trong Java hiện nay.

## 2. Quy tắc tiếp nhận cần nhớ theo đúng thứ tự

Mô hình khái niệm của việc giao một tác vụ qua `execute`:

```text
Tác vụ mới
    ↓
Số luồng hiện có dưới corePoolSize?
    ├─ Có → thử tạo luồng để chạy tác vụ
    └─ Không / không tạo được ở nhánh này
          ↓
      Executor còn nhận việc và workQueue.offer nhận được?
          ├─ Có → xếp hàng, kiểm tra lại trạng thái cần thiết
          └─ Không
                ↓
          Thử tạo thêm luồng đến maximumPoolSize
                ├─ Được → chạy tác vụ mới
                └─ Không → chính sách từ chối
```

**Thứ tự cốt lõi: tạo đến mức lõi → thử xếp hàng → tăng đến mức tối đa khi không xếp được → từ chối nếu không nhận được nữa.** [ThreadPoolExecutor: Queuing](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

Số luồng hiện có ở đây không chỉ là số luồng đang bận. Khi nhóm chưa đạt mức lõi, executor có thể tạo luồng mới dù đã có luồng rảnh. Khi đạt mức lõi, việc đưa vào hàng đợi có thể được một luồng rảnh lấy ngay, nên “đã offer vào queue” không có nghĩa tác vụ nhất thiết phải nằm chờ lâu.

Đây là sơ đồ học tập; triển khai còn xử lý cạnh tranh trạng thái. Chẳng hạn, sau khi offer thành công, executor kiểm tra lại việc shutdown có xảy ra không. Nếu hàng đợi có việc nhưng không còn luồng thực thi, nó cũng có cơ chế bảo đảm có luồng lấy việc. Không tự viết lại thuật toán dựa trên một ảnh chụp `getPoolSize()` và `queue.size()` ở mã ứng dụng. [Mã nguồn OpenJDK ThreadPoolExecutor.execute](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ThreadPoolExecutor.java).

## 3. Ba kiểu workQueue dẫn tới ba hành vi khác nhau

| Kiểu hàng đợi | Khi đã đạt mức lõi | Ảnh hưởng thường gặp |
|---|---|---|
| Không giới hạn thực tế, như `new LinkedBlockingQueue<>()` | Thường tiếp tục nhận thêm tác vụ vào hàng đợi | Nhóm ít có lý do tăng vượt mức lõi; việc chờ có thể tích rất lớn |
| Có dung lượng hữu hạn, như `new ArrayBlockingQueue<>(100)` | Xếp hàng đến khi không nhận được nữa | Khi đầy mới xét tăng vượt lõi; sau đó có thể từ chối |
| Chuyển giao trực tiếp, như `new SynchronousQueue<>()` | Chỉ giao được nếu có bên nhận sẵn sàng | Không có vùng đệm tác vụ; dễ tạo thêm luồng khi mọi luồng đều bận |

### 3.1. Hàng đợi không giới hạn làm mức tối đa ít có tác dụng

Với `core = 2`, `max = 20` và hàng đợi không đặt dung lượng hữu hạn, sau khi có hai luồng, các tác vụ tiếp theo thường vào hàng đợi. Nhánh tạo đến 20 chỉ được xét khi không thể nhận vào hàng đợi; trong điều kiện thông thường, queue này không báo đầy theo một giới hạn nhỏ.

Hệ quả là tăng riêng `maximumPoolSize` có thể không làm tăng số tác vụ đang xử lý song song. Số tác vụ chờ và độ trễ có thể tăng dù biểu đồ luồng chỉ quanh mức lõi. “Không giới hạn” không phải vô hạn bộ nhớ: mỗi tác vụ chờ giữ dữ liệu và tài nguyên liên quan trong tiến trình.

### 3.2. Hàng đợi hữu hạn là vùng đệm có giới hạn

`ArrayBlockingQueue` có dung lượng cố định và thứ tự FIFO cho các phần tử nằm trong hàng đợi. `offer` không có thời hạn trả `false` nếu đầy, thay vì chờ đến khi có chỗ. [ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

Vùng đệm nhỏ khiến executor xét tăng vượt lõi sớm hơn. Vùng đệm lớn làm nhiều công việc chờ trước khi nhánh tăng được kích hoạt. Không có dung lượng đúng cho mọi hệ thống; cần cân bằng thời gian chờ, lượng bộ nhớ giữ lại, mức song song và khả năng phục vụ của tài nguyên phía sau.

### 3.3. SynchronousQueue không chứa cả một tác vụ để đợi

`SynchronousQueue` không có dung lượng lưu phần tử. Nó là cơ chế chuyển giao giữa bên giao và bên nhận. Khi không có luồng sẵn sàng nhận, phép offer có thể không thành công; executor thử thêm luồng trong giới hạn.

Do đó `queue.size() == 0` không chứng minh hệ thống đang nhẹ tải. Có thể tất cả các luồng đều bận hoặc bị chặn I/O. [SynchronousQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

## 4. Ví dụ suy luận: core 1, max 2, queue 2

Giả sử các tác vụ chạy đều bị giữ lại đủ lâu để không giải phóng luồng hoặc hàng đợi:

| Lần giao | Quyết định | Luồng hiện có | Tác vụ đang chờ |
|---|---|---:|---:|
| Tác vụ 1 | Dưới mức lõi, tạo luồng thứ nhất | 1 | 0 |
| Tác vụ 2 | Đã đạt lõi, queue còn chỗ | 1 | 1 |
| Tác vụ 3 | Queue vẫn còn chỗ | 1 | 2 |
| Tác vụ 4 | Queue đầy, còn dưới max, tạo luồng thứ hai | 2 | 2 |
| Tác vụ 5 | Queue đầy và đã đạt max | 2 | 2 |

Ở lần thứ năm, chính sách từ chối quyết định hành vi. Với `AbortPolicy`, lời giao việc ném `RejectedExecutionException`.

Chú ý tác vụ 4 có thể bắt đầu trước tác vụ 2 và 3, vì nó được giao trực tiếp làm công việc đầu tiên của luồng mới trong khi 2 và 3 vẫn trong queue. FIFO của queue không phải cam kết thứ tự bắt đầu của mọi tác vụ được gửi vào toàn bộ executor; nhiều luồng cũng không bảo đảm thứ tự hoàn thành.

## 5. Chương trình kiểm chứng đầy đủ

Chương trình dưới đây dùng latch để giữ các tác vụ đang chạy. Nhờ đó, main đọc số luồng và hàng đợi trong những điều kiện đã được cố định; không dùng sleep để đoán các tác vụ có còn bận không.

Lưu thành `WorkQueueDecisionDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class WorkQueueDecisionDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(2),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch fourthStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Integer>> accepted = new ArrayList<>();

        try {
            accepted.add(pool.submit(blockedTask(1, firstStarted, release)));
            requireStarted(firstStarted);
            printState("after task 1", pool);

            accepted.add(pool.submit(blockedTask(2, null, release)));
            accepted.add(pool.submit(blockedTask(3, null, release)));
            printState("after task 3", pool);

            accepted.add(pool.submit(blockedTask(4, fourthStarted, release)));
            requireStarted(fourthStarted);
            printState("after task 4", pool);

            try {
                pool.submit(blockedTask(5, null, release));
                throw new AssertionError("Expected rejection");
            } catch (RejectedExecutionException ex) {
                System.out.println("task 5: rejected");
            }

            release.countDown();
            int sum = 0;
            for (Future<Integer> future : accepted) {
                sum += future.get(10, TimeUnit.SECONDS);
            }
            System.out.println("accepted result sum: " + sum);
        } finally {
            release.countDown();
            pool.shutdown();
            try {
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("Executor did not terminate");
                    }
                }
            } catch (InterruptedException ex) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }

    private static Callable<Integer> blockedTask(
            int value, CountDownLatch started, CountDownLatch release) {
        return () -> {
            if (started != null) {
                started.countDown();
            }
            release.await();
            return value;
        };
    }

    private static void requireStarted(CountDownLatch started)
            throws InterruptedException {
        if (!started.await(10, TimeUnit.SECONDS)) {
            throw new AssertionError("Task did not start");
        }
    }

    private static void printState(String label, ThreadPoolExecutor pool) {
        System.out.println(label + ": pool=" + pool.getPoolSize()
                + ", queue=" + pool.getQueue().size());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 WorkQueueDecisionDemo.java
java WorkQueueDecisionDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
after task 1: pool=1, queue=0
after task 3: pool=1, queue=2
after task 4: pool=2, queue=2
task 5: rejected
accepted result sum: 10
```

Cách đọc bằng chứng:

1. Tác vụ 1 tạo luồng đến mức lõi rồi bị giữ ở latch.
2. Tác vụ 2 và 3 được nhận nhưng không làm tạo luồng thứ hai, vì queue vẫn nhận được chúng.
3. Chỉ khi tác vụ 4 không vào queue được, executor mới tăng lên hai luồng.
4. Tác vụ 5 không được nhận với AbortPolicy; không có kết quả của nó trong danh sách accepted.
5. Sau khi mở latch, các tác vụ 1–4 hoàn thành; tổng 10 xác nhận bốn kết quả đã được thu nhận.

Việc đọc queue trong chương trình này dùng cho quan sát cơ chế. Trong ứng dụng đang có tải thay đổi, các chỉ số có thể đổi ngay sau khi được đọc; không dùng một ảnh chụp như vậy để tự quyết định thay executor rằng tác vụ tiếp theo chắc chắn được nhận.

## 6. Vì sao BlockingQueue không làm submit tự chờ chỗ trống?

Tên `BlockingQueue` cho biết giao diện có các thao tác có thể chặn như `put` và `take`. Nó cũng có các thao tác không chờ như `offer`.

Trong cơ chế tiếp nhận thông thường của ThreadPoolExecutor, executor thử `workQueue.offer(command)`. Nó không mặc nhiên gọi `put` để giữ luồng gửi chờ đến khi có chỗ. Khi offer thất bại, executor xét tạo luồng rồi chính sách từ chối.

Do đó, một queue hữu hạn không tự cung cấp “submit chặn tới khi có chỗ”. Nếu hệ thống cần kiểm soát tốc độ nhận việc, phải thiết kế cơ chế đó rõ ràng. `CallerRunsPolicy` có thể tạo phản hồi giảm tốc bằng cách để bên gọi tự chạy một công việc khi bị từ chối trong trạng thái phù hợp, nhưng cũng có hệ quả: luồng xử lý yêu cầu hoặc luồng sự kiện có thể bị giữ lâu. Không dùng chính sách đó mà bỏ qua nơi công việc sẽ chạy.

Chính sách bỏ tác vụ âm thầm cũng không phải một cách giảm tải vô hại. Nếu nơi gọi giữ Future và công việc bị bỏ nhưng không được hủy/ghi nhận, nó có thể chờ kết quả không bao giờ đến. Bài chọn AbortPolicy để việc không nhận được được thể hiện rõ ngay tại lời giao việc.

## 7. Queue lớn hơn không tự làm xử lý nhanh hơn

Tăng dung lượng queue có thể hấp thụ một đợt công việc ngắn mà không tăng ngay số luồng. Nhưng nếu tốc độ đến liên tục cao hơn tốc độ xử lý, nó chỉ cho phép giữ thêm việc đang chờ và kéo dài độ trễ.

Một tác vụ ở cuối queue có thể hết giá trị trước khi bắt đầu: chẳng hạn người dùng đã thôi chờ hoặc hạn chót yêu cầu đã qua. Vì thế cần xét cả thời gian chờ trong queue, thời gian xử lý, thời hạn công việc và tài nguyên mà mỗi tác vụ giữ.

Ngược lại, queue nhỏ có thể làm nhóm tăng luồng sớm, tăng số truy cập đồng thời vào cơ sở dữ liệu hoặc dịch vụ bên ngoài. Nếu tài nguyên phía sau chỉ phục vụ tốt một số lượng yêu cầu đồng thời nhất định, tăng luồng không tạo thêm khả năng phục vụ của tài nguyên đó.

Không có công thức chỉ nhìn số CPU rồi chọn được mọi tham số. Cần hiểu công việc chủ yếu tính toán hay chờ I/O, đo độ trễ/khả năng phục vụ và kiểm tra lúc quá tải. Queue và giới hạn luồng phải được thiết kế cùng nhau.

## 8. Những giới hạn cần giữ khi suy luận

### Số chỗ nhận không phải cam kết thời gian thực

Với điều kiện thí nghiệm bị giữ ổn định, có thể mô tả bốn tác vụ được nhận bằng hai luồng cộng hai chỗ chờ. Trong hệ thống thực, các tác vụ bắt đầu/kết thúc đồng thời, luồng mới có thể không tạo được, hoặc shutdown có thể cạnh tranh với việc giao việc. Không coi `max + capacity` là một lời hứa mọi đợt gửi đúng số đó chắc chắn thành công dưới mọi điều kiện.

### Hàng đợi FIFO không bảo đảm thứ tự toàn cục

Các tác vụ đã nằm trong queue FIFO được lấy theo hợp đồng queue. Nhưng công việc giao trực tiếp cho một luồng mới có thể bắt đầu trước công việc cũ đang chờ, và các luồng khác nhau hoàn thành với thời lượng khác nhau. Nếu nghiệp vụ cần thứ tự, phải thiết kế một mô hình thực thi/đồng bộ phù hợp riêng.

### corePoolSize bằng 0 không nhất thiết là không có ai lấy queue

Triển khai chuẩn có nhánh bảo đảm tồn tại luồng thực thi nếu việc đã được đưa vào queue mà nhóm không còn luồng. Tuy nhiên, dùng core 0 với một queue tích được nhiều việc không có nghĩa executor tự tăng lên max theo lượng việc đang chờ. Hãy phân tích lại quy tắc offer trước khi đổi kiểu queue.

### Không đẩy trực tiếp vào getQueue để thay submit

`getQueue()` dành chủ yếu cho theo dõi và gỡ lỗi. Chèn thẳng công việc vào đó có thể bỏ qua logic nhận việc, kiểm tra trạng thái, tạo luồng và chính sách từ chối. Dùng `execute`/`submit` làm lối vào bình thường; không sửa hàng đợi chỉ vì nó đang được phơi ra qua một phương thức công khai.

## 9. Quan sát đúng để giải thích hành vi tải

Khi điều tra vì sao nhóm không tăng như dự đoán, xem đồng thời:

- `corePoolSize`, `maximumPoolSize` và số luồng hiện có.
- Loại queue, dung lượng được cấu hình, số tác vụ đang chờ.
- Số tác vụ bị từ chối và chính sách xử lý chúng.
- Độ trễ chờ trước khi bắt đầu và thời lượng thực thi.
- Trạng thái phụ thuộc phía sau như kết nối/độ trễ dịch vụ.

Queue gần rỗng với nhiều luồng bận có ý nghĩa khác queue tích lớn với số luồng đứng yên ở mức lõi. Không kết luận chỉ từ một chỉ số. Các số đọc phục vụ chẩn đoán và đo lường; chúng không thay cho cơ chế tiếp nhận nguyên tử bên trong executor.

## 10. Tự kiểm tra và thực hành

1. Core 2, max 10, queue không giới hạn thực tế; vì sao có thể chỉ thấy hai luồng xử lý dù gửi nhiều tác vụ? **Sau mức lõi, queue vẫn nhận việc nên nhánh tăng vượt lõi không được kích hoạt trong điều kiện thường.**
2. Trong ví dụ, vì sao tác vụ 3 chưa tạo luồng thứ hai? **Queue vẫn còn chỗ nhận nó.**
3. Vì sao tác vụ 4 có thể chạy trước tác vụ 2? **Nó được giao trực tiếp cho luồng mới sau khi queue đầy.**
4. Queue là BlockingQueue thì submit có tự chờ queue trống không? **Không theo cơ chế tiếp nhận chuẩn; nó thử offer rồi xét tăng luồng/từ chối.**
5. SynchronousQueue có size 0 có nghĩa không có công việc đang chạy không? **Không; nó không lưu vùng đệm, còn công việc có thể chiếm các luồng.**

Thực hành: đổi dung lượng `ArrayBlockingQueue` trong ví dụ từ 2 thành 1. Dự đoán lại tác vụ nào làm tăng luồng và tác vụ nào bị từ chối; sửa latch và đường thu kết quả để phù hợp trước khi chạy. Tiếp theo, dùng queue không giới hạn và chỉ gửi một số tác vụ hữu hạn nhỏ: quan sát vì sao nhóm giữ gần mức lõi. Không tạo thử tải vô hạn để chứng minh khả năng đầy bộ nhớ; cơ chế được giải thích từ quy tắc tiếp nhận và kiểm chứng bằng trường hợp có giới hạn.
