# Chỉ số số luồng, số tác vụ hoạt động và hàng đợi

## 1. Ba con số mô tả ba phần khác nhau

Một bộ luồng có 8 luồng, 8 tác vụ hoạt động và hàng đợi rỗng. Hệ thống có đang rảnh không? Không thể kết luận chỉ từ hàng đợi rỗng: cả 8 tác vụ có thể đang chờ phản hồi cơ sở dữ liệu.

Một bộ khác có 8 luồng nhưng chỉ 1 tác vụ hoạt động. Điều đó cũng chưa chứng minh cấu hình sai; có thể nguồn công việc hiện ít.

Khi quan sát `ThreadPoolExecutor`, cần phân biệt:

- **Số luồng hiện có:** tài nguyên luồng đang tồn tại trong bộ.
- **Số luồng đang thực hiện tác vụ:** luồng được bộ thực thi coi là bận xử lý công việc.
- **Số phần tử trong hàng đợi:** công việc chưa được luồng lấy ra theo cơ chế queue.

Các chỉ số giúp chẩn đoán khi đặt cùng cấu hình, vòng đời, tốc độ công việc và độ trễ. Chúng không phải các điều kiện nguyên tử để tự quyết định một lần gửi chắc chắn được tiếp nhận.

Các ví dụ trong bài dùng Java 17+ và các API vẫn áp dụng trên Java hiện đại.

## 2. Bảng đọc chỉ số

| API | Loại số liệu | Ý nghĩa |
| --- | --- | --- |
| `getCorePoolSize()` | Cấu hình | Ngưỡng luồng core |
| `getMaximumPoolSize()` | Cấu hình | Giới hạn trên số luồng của bộ |
| `getPoolSize()` | Giá trị hiện tại | Số luồng hiện có |
| `getActiveCount()` | Ước lượng hiện tại | Số luồng đang thực hiện tác vụ |
| `getQueue().size()` | Giá trị queue quan sát | Số phần tử đang được lưu trong queue |
| `getLargestPoolSize()` | Đỉnh lịch sử | Số luồng lớn nhất từng đồng thời có trong bộ |
| `getCompletedTaskCount()` | Bộ đếm ước lượng tích lũy | Số tác vụ được các luồng của bộ thực thi hoàn tất |
| `getTaskCount()` | Tổng ước lượng | Số tác vụ đã được lập lịch theo cách thống kê của bộ |

Số liệu như active, completed và task count có hợp đồng **ước lượng**. Một lần gọi phương thức không tạo ảnh chụp đồng thời với tất cả phương thức còn lại. [Tài liệu chỉ số ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#getActiveCount())

Nên đặt tên metric kèm đơn vị và phạm vi, chẳng hạn số luồng, số tác vụ, số phần tử chờ. Một nhãn chung “pool usage” dễ làm người đọc nhầm tỷ lệ luồng bận với CPU hoặc mức đầy bộ nhớ.

## 3. poolSize khác core/max

Nếu core bằng 4, max bằng 16 nhưng chưa gửi công việc, poolSize có thể bằng 0 vì mặc định luồng được tạo khi cần. Có thể dùng prestart để khởi tạo sớm khi đó là yêu cầu của ứng dụng.

Nếu đã đạt core và hàng đợi tiếp tục nhận được công việc, bộ thực thi có thể không tạo thêm luồng tới max. Vì vậy:

```text
poolSize thấp hơn max
không tự chứng minh
bộ luồng còn khả năng xử lý ngay mọi tác vụ mới
```

Phải xét loại queue, số phần tử chờ và quan hệ core/max. Với hàng đợi không đặt giới hạn nhỏ theo cấu hình, việc chờ có thể tích tụ mà poolSize vẫn ở core.

Sau khi bộ thực thi kết thúc, poolSize về 0 nhưng largestPoolSize có thể vẫn giữ đỉnh trước đó. Hai chỉ số có mục đích khác nhau: một mô tả hiện tại, một lưu lịch sử.

Không dùng largestPoolSize làm số luồng đang bận; nó không giảm mỗi khi tải giảm.

## 4. Active không phải CPU đang chạy

Một luồng làm việc đang thực hiện tác vụ có thể:

- Tính toán trên CPU.
- Chờ một khóa.
- Chờ dữ liệu mạng hoặc cơ sở dữ liệu.
- Chờ một chốt đồng bộ do tác vụ gọi.
- Chạy mã dọn dẹp hoặc ngữ cảnh thực thi liên quan.

Từ góc nhìn bộ thực thi, luồng vẫn chưa sẵn sàng nhận tác vụ tiếp theo. Do đó, active có thể cao trong lúc CPU thấp.

Ngược lại, số luồng hoạt động ít không chứng minh CPU thấp: một số tác vụ tính toán có thể đã dùng hết phần CPU khả dụng cho tiến trình.

`getActiveCount()` cũng không đếm toàn bộ tác vụ trên mọi luồng của ứng dụng. Nếu CallerRunsPolicy chạy công việc trên luồng gửi, công việc đó không trở thành một luồng làm việc mới của bộ. Cần số đo nghiệp vụ riêng để biết đầy đủ công việc đang thực hiện.

Không dùng tỷ lệ `active / max` như một chỉ số CPU. Nếu muốn dùng nó để quan sát mức chiếm vị trí trong bộ, hãy đặt tên và giải thích đúng phạm vi.

## 5. Thí nghiệm ba mốc: chưa dùng, đang bận và đã kết thúc

Chương trình tạo bộ hai luồng và queue hai phần tử:

1. Chưa gửi công việc: chưa có luồng được tạo.
2. Hai công việc bị giữ ở chốt, hai việc khác chờ.
3. Mở chốt, đọc kết quả của cả bốn việc, shutdown và chờ kết thúc.

Một công việc được nhận sẽ ném lỗi để thấy “completed” không chỉ đếm thành công.

Tệp **PoolMetricsDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PoolMetricsDemo {
    private static void printMetrics(String label, ThreadPoolExecutor pool) {
        System.out.println(label
                + ": pool=" + pool.getPoolSize()
                + ", active=" + pool.getActiveCount()
                + ", queued=" + pool.getQueue().size()
                + ", completed=" + pool.getCompletedTaskCount()
                + ", total=" + pool.getTaskCount()
                + ", largest=" + pool.getLargestPoolSize());
    }

    public static void main(String[] args) throws Exception {
        AtomicInteger rejected = new AtomicInteger();
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<Runnable>(2),
                (task, executor) -> {
                    rejected.incrementAndGet();
                    throw new RejectedExecutionException("No capacity");
                });

        CountDownLatch started = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            printMetrics("new", pool);

            for (int i = 0; i < 2; i++) {
                futures.add(pool.submit(() -> {
                    started.countDown();
                    release.await();
                    return 1;
                }));
            }
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Workers did not start");
            }

            futures.add(pool.submit(() -> 3));
            futures.add(pool.submit(() -> {
                throw new IllegalArgumentException("Bad report input");
            }));

            try {
                pool.submit(() -> 5);
            } catch (RejectedExecutionException ex) {
                System.out.println("fifth=rejected");
            }

            printMetrics("held", pool);
            System.out.println("rejected=" + rejected.get());

            release.countDown();

            int success = 0;
            int failure = 0;
            for (Future<Integer> future : futures) {
                try {
                    future.get();
                    success++;
                } catch (ExecutionException ex) {
                    failure++;
                }
            }

            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }

            printMetrics("terminated", pool);
            System.out.println("businessSuccess=" + success);
            System.out.println("businessFailure=" + failure);
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac --release 17 PoolMetricsDemo.java
java PoolMetricsDemo
```

Stdout với bộ thực thi chuẩn ở những mốc được giữ ổn định của thí nghiệm:

```text
new: pool=0, active=0, queued=0, completed=0, total=0, largest=0
fifth=rejected
held: pool=2, active=2, queued=2, completed=0, total=4, largest=2
rejected=1
terminated: pool=0, active=0, queued=0, completed=4, total=4, largest=2
businessSuccess=3
businessFailure=1
```

Các chốt làm hai tác vụ đầu chưa thể hoàn tất trước mốc held. Chúng đang chờ chốt nhưng vẫn được tính active: đây là bằng chứng active không đồng nghĩa dùng CPU liên tục.

Mốc cuối được chụp sau khi `awaitTermination` xác nhận kết thúc. Nếu chỉ gọi get trên Future cuối rồi lập tức đọc completed count, luồng làm việc có thể chưa đi hết phần cập nhật thống kê của bộ thực thi. Vì vậy chương trình dùng một mốc kết thúc rõ hơn.

Thí nghiệm tạo các khoảng không có tác vụ đến/đi để dễ quan sát. Nó không thay đổi hợp đồng ước lượng của API thành một bảo đảm ảnh chụp nguyên tử trong môi trường có tải liên tục.

## 6. Completed không phải số tác vụ thành công

Trong ví dụ, completed bằng 4 nhưng businessSuccess bằng 3. Công việc lỗi cũng đã đi qua phần thực thi và kết thúc.

Để biết kết quả nghiệp vụ, cần theo dõi riêng:

- Thành công.
- Thất bại.
- Bị hủy.
- Chưa được tiếp nhận.
- Kết quả một phần nếu hợp đồng có trạng thái đó.

Không suy ra số lỗi bằng `total - completed - active - queued`. Các số đọc ở thời điểm khác nhau, có tính ước lượng và chịu ảnh hưởng của cơ chế bao/hủy/dọn tác vụ. Đây không phải phương trình kế toán nghiệp vụ.

Tác vụ bị từ chối và chưa được chạy bởi bộ luồng không trở thành một thành công hay thất bại thực thi trong completed count của ví dụ. Vì vậy chương trình có bộ đếm rejected riêng.

Nếu dùng CallerRunsPolicy hoặc handler tùy chỉnh chạy tác vụ ngoài các luồng của bộ, đừng giả định completed count của bộ sẽ bao phủ những công việc đó.

Nếu dùng hook `afterExecute` để ghi lỗi, tác vụ submit thường đã giữ ngoại lệ trong Future; tham số Throwable của hook không tự thể hiện mọi lỗi nghiệp vụ. Cần quan sát đúng kênh kết quả. [Tài liệu ThreadPoolExecutor.afterExecute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#afterExecute(java.lang.Runnable,java.lang.Throwable))

## 7. Queue size chỉ có ý nghĩa khi biết loại queue

Với ArrayBlockingQueue, size mô tả số phần tử đang lưu chờ. Với SynchronousQueue, size luôn bằng 0 vì nó là điểm chuyển giao trực tiếp, không có vùng đệm nội bộ.

Do đó:

```text
queued = 0
không suy ra
có khả năng nhận thêm công việc
```

### Thí nghiệm hàng đợi rỗng nhưng vẫn từ chối

Tệp **EmptyQueueBusyDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class EmptyQueueBusyDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.SECONDS,
                new SynchronousQueue<Runnable>(),
                new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return null;
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            System.out.println("queued=" + pool.getQueue().size());
            System.out.println("active=" + pool.getActiveCount());
            System.out.println("pool=" + pool.getPoolSize());

            try {
                pool.submit(() -> 2);
            } catch (RejectedExecutionException ex) {
                System.out.println("nextTask=rejected");
            }

            release.countDown();
            first.get();
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 EmptyQueueBusyDemo.java
java EmptyQueueBusyDemo
```

Stdout:

```text
queued=0
active=1
pool=1
nextTask=rejected
```

Luồng duy nhất đang bận và không còn khả năng tạo thêm. SynchronousQueue không giữ tác vụ chờ, nên lần gửi tiếp bị từ chối dù size bằng 0. [Tài liệu SynchronousQueue.size](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/SynchronousQueue.html#size())

Với hàng đợi lớn không có giới hạn nhỏ theo cấu hình, size tăng có thể che giấu việc poolSize không mở rộng vượt core. Với các phần tử bao đã hủy nhưng còn ở queue, size cũng chưa chắc bằng số công việc còn giá trị nghiệp vụ.

## 8. Một tập số đọc không phải một ảnh chụp nguyên tử

Hàm printMetrics gọi nhiều phương thức lần lượt:

```text
đọc poolSize
    -> tác vụ có thể kết thúc
đọc active
    -> nguồn khác có thể gửi thêm
đọc queue size
    -> một luồng có thể lấy việc khỏi queue
```

Ngay cả khi gói các giá trị vào một record, những lần đọc bên trong vẫn không tự xảy ra cùng thời điểm.

Hệ quả:

- Không báo lỗi dữ liệu chỉ vì một đẳng thức tự suy đoán không khớp.
- Không dùng kiểm tra queue còn chỗ làm khóa tiếp nhận.
- Không tự điều phối công việc bằng cách đếm active rồi chèn trực tiếp vào queue.
- Nếu cần quyết định tiếp nhận, dùng API gửi việc và xử lý chính sách từ chối.

Khóa riêng của ứng dụng quanh hàm đọc cũng không đóng băng các luồng làm việc, trừ khi mọi đường thay đổi đều thực sự tuân theo cùng giao thức đó. Chỉ thêm synchronized vào phương thức đo không tạo ảnh chụp nguyên tử của bộ thực thi.

## 9. Bộ đếm tích lũy khác tốc độ

Completed count là số tích lũy trong vòng đời instance, không phải “tác vụ/giây”.

Một cách ước lượng thông lượng quan sát:

```text
số hoàn tất tăng trong khoảng đo
--------------------------------
thời gian đã trôi qua trong khoảng đo
```

Ví dụ số đếm tăng từ 100 lên 160 trong hai giây thì mức tăng trung bình là 30 tác vụ/giây. Đây chỉ là ví dụ số học, không phải kết quả đo hiệu năng của hai chương trình.

Khi thay instance bộ thực thi hoặc khởi động lại ứng dụng, bộ đếm có vòng đời mới. Hệ thống quan sát phải xử lý việc reset, không diễn giải một mức giảm bộ đếm thành thông lượng âm.

Cần đo riêng tốc độ thành công nếu đó là thứ nghiệp vụ quan tâm. Thông lượng kết thúc cao có thể đi cùng tỷ lệ lỗi cao.

## 10. Đọc theo tổ hợp và theo thời gian

| Quan sát lặp lại | Hướng điều tra |
| --- | --- |
| Active gần số luồng, queue tăng | Công việc đến nhanh hơn khả năng xử lý hoặc tác vụ bị giữ lâu |
| Active cao, CPU thấp | I/O, khóa, kết nối hoặc chờ công việc khác |
| Queue tăng nhưng pool không tăng tới max | Chính sách ưu tiên queue sau core và loại queue |
| Queue thấp, rejection cao | SynchronousQueue, shutdown hoặc giới hạn tiếp nhận khác |
| Completed vẫn tăng, lỗi nghiệp vụ tăng | Khả năng kết thúc vẫn có nhưng kết quả không đạt yêu cầu |
| Largest lớn nhưng hiện tại pool nhỏ | Đỉnh tải trước đó, thu hồi luồng hoặc vòng đời |
| Active không giảm khi đang dừng | Tác vụ chưa kết thúc, không đáp ứng ngắt hoặc tài nguyên chặn |

Đây là các hướng kiểm tra, không phải chẩn đoán chắc chắn chỉ từ vài con số. Cần bổ sung độ trễ, log có mã tác vụ, thread dump và sức khỏe tài nguyên phụ thuộc khi có bằng chứng.

Một lần lấy mẫu có thể bỏ lỡ đợt tải rất ngắn. Lấy mẫu liên tục quá dày cũng tạo chi phí. Chọn chu kỳ phù hợp với nhu cầu quan sát; giữ lịch sử thay vì chỉ nhìn giá trị hiện tại.

## 11. Thiết kế số đo đủ dùng

Một bộ số đo thực dụng thường gồm:

- Cấu hình core/max, loại queue và dung lượng có giới hạn nếu có.
- Pool/active/queue hiện tại và largest.
- Mức tăng completed theo thời gian.
- Số lần từ chối phân biệt với lỗi tác vụ.
- Độ trễ chờ queue và độ trễ thực thi.
- Kết quả nghiệp vụ thành công/lỗi/hủy.

ThreadPoolExecutor không tự cung cấp mọi phân phối thời gian chờ queue và thực thi. Nếu cần đo, có thể gắn mốc thời gian ở ranh giới gửi/bắt đầu/kết thúc hoặc tích hợp công cụ quan sát phù hợp.

Phải xác định rõ phạm vi đo, đặc biệt khi tác vụ bị từ chối, chạy trên bên gửi, bị hủy trước khi chạy hoặc thực hiện công việc con. Không tạo số liệu chính xác giả bằng cách suy ra mọi trạng thái chỉ từ các getter.

Đừng gắn một nhãn metric riêng cho từng mã yêu cầu nếu hệ thống đo không được thiết kế cho số lượng nhãn lớn. Tên vai trò bộ luồng ổn định giúp so sánh, còn định danh từng công việc thường phù hợp hơn trong log/truy vết.

## 12. Tự đọc một bảng quan sát

Bạn thấy:

```text
core=4, max=20
pool=4, active=4
queue tăng theo thời gian
CPU ở mức thấp
completed vẫn tăng chậm
```

Hãy đặt câu hỏi:

1. Hàng đợi có đang tiếp tục nhận nên bộ luồng chưa mở rộng không?
2. Tác vụ đang dùng CPU hay đang chờ I/O/khóa?
3. Công việc chờ đã vượt thời hạn hữu ích chưa?
4. Tài nguyên ngoài có cho phép tăng đồng thời không?
5. Số lỗi và số từ chối biến động thế nào?
6. Có thể giảm tải hoặc sửa tác vụ chậm trước khi tăng luồng không?

Cách đọc này giữ đúng ý nghĩa của từng chỉ số: số luồng mô tả tài nguyên, active mô tả vị trí đang bận và queue mô tả phần việc được lưu chờ. Cần kết hợp chúng với kết quả và độ trễ để đánh giá sức khỏe xử lý.
