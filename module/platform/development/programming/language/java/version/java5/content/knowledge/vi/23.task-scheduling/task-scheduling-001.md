# ScheduledExecutorService và tác vụ chạy sau độ trễ

## 1. Đặt lịch khác giữ luồng ngủ

Ứng dụng muốn làm mới một giá trị sau 200 ms hoặc thử lại một thao tác sau một khoảng chờ. Nếu cho luồng xử lý yêu cầu gọi `Thread.sleep`, luồng đó bị giữ trong suốt thời gian chờ.

`ScheduledExecutorService` nhận công việc cần chạy sau một **độ trễ tương đối**, trả một handle để theo dõi/hủy và để bộ lập lịch quản lý thời điểm công việc đủ điều kiện thực hiện.

Ba mốc cần phân biệt:

```text
gọi schedule
    -> chờ đủ độ trễ
        -> tác vụ đủ điều kiện chạy
            -> có luồng thực hiện
                -> kết thúc thành công/lỗi/hủy
```

Đủ độ trễ không có nghĩa tác vụ bắt đầu đúng tức khắc. Nếu các luồng đều bận hoặc hệ điều hành chưa lập lịch, thời điểm bắt đầu có thể muộn hơn.

Bài tập trung vào tác vụ **chạy một lần sau độ trễ**. Các API xuất hiện từ Java 5 và vẫn sử dụng trên Java hiện đại; các chương trình chạy với Java 17+.

## 2. Quan hệ với ExecutorService

`ScheduledExecutorService` mở rộng `ExecutorService`. Nó vẫn có những thao tác như submit, shutdown, awaitTermination, đồng thời bổ sung khả năng schedule.

Cách khởi tạo thường gặp:

```java
ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
```

Đây là câu lệnh đặt trong một phương thức sau khi nhập các lớp tương ứng. Bên sở hữu scheduler chịu trách nhiệm đóng nó khi hết vòng đời.

Số 2 là số luồng cốt lõi cho các tác vụ của bộ lập lịch tiêu chuẩn này, không phải số tác vụ tối đa có thể đặt lịch. Các tác vụ chưa đến hạn thường được giữ trong hàng đợi trì hoãn.

Hai dạng tác vụ một lần:

| Phương thức | Dạng công việc | Kết quả get khi thành công |
| --- | --- | --- |
| `schedule(Runnable, delay, unit)` | Không trả giá trị nghiệp vụ | `null` |
| `schedule(Callable<V>, delay, unit)` | Trả giá trị kiểu V | Giá trị do Callable trả về |

Cả hai đều trả `ScheduledFuture`, không trả ngay giá trị của phần thân tác vụ. [Tài liệu ScheduledExecutorService.schedule](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)

## 3. Độ trễ là tương đối và có đơn vị

Ví dụ:

```java
scheduler.schedule(task, 200, TimeUnit.MILLISECONDS);
```

Nghĩa là tác vụ được đặt để đủ điều kiện sau khoảng 200 ms tính từ lúc đặt lịch theo cơ chế scheduler. Nó không có nghĩa “200 ms tính từ khi một tác vụ khác kết thúc”, trừ khi chính bạn gọi schedule ở thời điểm đó.

Luôn ghi rõ đơn vị. Nhầm giây với mili giây có thể làm công việc chạy sớm hoặc trễ khác xa ý định.

Với các phương thức schedule một lần:

- Độ trễ dương: chờ đủ khoảng đã yêu cầu.
- Độ trễ bằng 0: yêu cầu đủ điều kiện ngay.
- Độ trễ âm: cũng được xem như yêu cầu thực hiện ngay.

“Ngay” vẫn đi qua cơ chế thực thi, không có nghĩa phần thân được gọi đồng bộ ngay trên luồng gửi.

Không nhầm quy tắc này với period của tác vụ lặp; period có yêu cầu riêng. Phần lập lịch định kỳ chỉ được phân biệt ngắn ở cuối bài.

## 4. Ví dụ: một Callable có kết quả và một Runnable

Trong chương trình, chỉ main in ra màn hình sau các mốc get nên stdout có thứ tự rõ ràng, không phụ thuộc tác vụ nào tự in trước.

Tệp **DelayedTasksDemo.java**:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class DelayedTasksDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);
        AtomicInteger updates = new AtomicInteger();

        try {
            ScheduledFuture<String> message = scheduler.schedule(
                    () -> "cache-ready",
                    50, TimeUnit.MILLISECONDS);

            Runnable update = () -> updates.incrementAndGet();
            ScheduledFuture<?> updateHandle = scheduler.schedule(
                    update,
                    100, TimeUnit.MILLISECONDS);

            System.out.println("registered=2");
            System.out.println("message=" + message.get(5, TimeUnit.SECONDS));
            System.out.println("runnableResult="
                    + updateHandle.get(5, TimeUnit.SECONDS));
            System.out.println("updates=" + updates.get());
            System.out.println("messageDone=" + message.isDone());
            System.out.println("updateDone=" + updateHandle.isDone());
        } finally {
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 DelayedTasksDemo.java
java DelayedTasksDemo
```

Stdout khi hoàn tất bình thường:

```text
registered=2
message=cache-ready
runnableResult=null
updates=1
messageDone=true
updateDone=true
```

Không kiểm tra “isDone phải false ngay sau schedule” trong ví dụ: luồng main có thể bị tạm dừng đủ lâu để tác vụ đã xong trước lúc nó đọc trạng thái.

Các lệnh get có thời hạn năm giây giới hạn khoảng chờ của main trong thí nghiệm. Chúng không thay đổi độ trễ đã đặt cho tác vụ và không tự hủy nếu hết thời gian chờ.

Ví dụ dùng Runnable đặt vào biến riêng để làm rõ overload nào được chọn; biểu thức lambda có trả giá trị có thể khiến người học nhầm dạng Callable và Runnable.

## 5. ScheduledFuture mô tả cả độ trễ và kết quả

`ScheduledFuture<V>` vừa là `Future<V>` vừa hỗ trợ hợp đồng `Delayed`. Có thể:

- Gọi `getDelay(unit)` để quan sát thời gian còn lại.
- Gọi `get` để chờ/lấy kết quả hoặc lỗi.
- Gọi `cancel` để yêu cầu hủy.
- Quan sát `isDone` và `isCancelled`.

`getDelay` không phải tiến độ xử lý. Giá trị bằng 0 hoặc âm có thể cho biết đã đến hạn, trong khi tác vụ vẫn chưa bắt đầu vì thiếu luồng. Giá trị này cũng có thể thay đổi ngay sau khi đọc. [Tài liệu ScheduledFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

Không quay vòng liên tục chờ getDelay về 0 rồi tự gọi phần thân tác vụ. Bộ lập lịch đã chịu trách nhiệm thực thi; cách đó có thể chạy lặp công việc ngoài handle.

Một handle có trạng thái done có thể là thành công, lỗi hoặc hủy. Muốn biết kết quả của tác vụ một lần, đọc get và xử lý các nhánh phù hợp.

## 6. Thí nghiệm: đã đến hạn nhưng chưa có luồng

Scheduler chỉ có một luồng. Một tác vụ được gửi trước giữ luồng đó ở chốt. Tác vụ zero-delay phía sau đủ điều kiện ngay, nhưng không thể bắt đầu.

Tệp **EligibleButWaitingDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class EligibleButWaitingDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch busy = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<?> blocker = scheduler.submit(() -> {
                busy.countDown();
                release.await();
                return null;
            });

            if (!busy.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Blocker did not start");
            }

            ScheduledFuture<String> due = scheduler.schedule(
                    () -> "done",
                    0, TimeUnit.NANOSECONDS);

            System.out.println("delayExpired="
                    + (due.getDelay(TimeUnit.NANOSECONDS) <= 0));
            System.out.println("doneWhileWorkerBusy=" + due.isDone());

            try {
                due.get(10, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                System.out.println("shortWait=TimeoutException");
            }

            release.countDown();
            blocker.get(5, TimeUnit.SECONDS);
            System.out.println("result=" + due.get(5, TimeUnit.SECONDS));
        } finally {
            release.countDown();
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 EligibleButWaitingDemo.java
java EligibleButWaitingDemo
```

Stdout:

```text
delayExpired=true
doneWhileWorkerBusy=false
shortWait=TimeoutException
result=done
```

Chốt giữ luồng bận cho tới sau lần get ngắn, nên kết quả không dựa vào phỏng đoán “tác vụ trước chắc đủ lâu”.

Tác vụ zero-delay không chạy trên main và không vượt qua công việc đang chiếm luồng. Đây là lý do độ trễ không phải cam kết thời gian thực. ScheduledThreadPoolExecutor bảo đảm tác vụ không chạy sớm hơn lúc đủ điều kiện, nhưng không đưa ra cam kết thời điểm bắt đầu chính xác sau mốc đó. [Tài liệu ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)

Trong hệ thống cần đo độ trễ lập lịch, nên phân biệt độ trễ yêu cầu, thời gian bắt đầu thực tế và thời gian chạy. Không dùng một số “elapsed” chung rồi quy mọi phần cho bộ lập lịch.

## 7. Lỗi, hủy và việc chờ quá thời hạn

| Tình huống | Cách quan sát |
| --- | --- |
| Callable trả bình thường | get trả giá trị |
| Runnable kết thúc bình thường | get trả null |
| Phần thân ném ngoại lệ | get ném ExecutionException, kiểm tra cause |
| Handle bị hủy | get ném CancellationException |
| Luồng chờ bị ngắt | get ném InterruptedException |
| Hết thời gian get có timeout | get ném TimeoutException |

Timeout của get chỉ giới hạn bên gọi chờ. Tác vụ vẫn có thể đang chờ đến hạn hoặc đang chạy. Nếu cần hủy, phải yêu cầu cancel riêng và hiểu chính sách dừng thực tế.

Nếu hủy được chấp nhận trước khi tác vụ chạy, phần thân không được thực hiện. Nếu hủy lúc đang chạy với yêu cầu ngắt, tác vụ cần hợp tác; không suy ra Future đã hủy là mã đã hoàn thành dọn tài nguyên. [Tài liệu Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Không bỏ quên ScheduledFuture khi cần biết công việc có thành công không. Ngoại lệ có thể được giữ trong handle thay vì xuất hiện ở luồng đã gọi schedule.

Đặt lịch cũng có thể bị từ chối bằng RejectedExecutionException, chẳng hạn bộ lập lịch đã ngừng tiếp nhận theo chính sách tiêu chuẩn. Đó là lỗi tiếp nhận, khác với lỗi bên trong tác vụ.

## 8. Vòng đời scheduler và công việc còn chờ

Bên tạo/sở hữu scheduler phải xác định khi nào dừng tiếp nhận và xử lý tác vụ còn chờ:

- `shutdown()`: ngừng nhận mới, áp dụng chính sách xử lý việc đã có.
- `shutdownNow()`: cố ngắt việc đang chạy và ngừng xử lý việc chờ.
- `awaitTermination`: chờ và xác nhận kết thúc.

Với ScheduledThreadPoolExecutor mặc định, tác vụ một lần đã có độ trễ thường vẫn được thực hiện sau shutdown khi đến hạn; tác vụ định kỳ có chính sách mặc định khác. Do đó, một lịch hẹn rất xa có thể kéo dài thời gian chờ kết thúc nếu không chủ động định nghĩa chính sách.

Lớp cụ thể có `setExecuteExistingDelayedTasksAfterShutdownPolicy(false)` khi ứng dụng muốn các lịch một lần chưa thực hiện không tiếp tục sau shutdown. Phải chọn theo yêu cầu, không đổi chính sách chỉ để làm chương trình thoát mà bỏ qua công việc đã cam kết.

Không tự đóng một scheduler dùng chung sau mỗi yêu cầu. Với Java 19+, nó có thể dùng qua cơ chế AutoCloseable, nhưng thao tác đóng có thể chờ kết thúc; khối try-with-resources không tự tạo một deadline ngắn cho các lịch xa.

Những tác vụ được schedule sau nhiều giờ vẫn là trạng thái trong bộ nhớ của tiến trình. Nếu cần khôi phục sau khởi động lại hoặc bảo đảm thực thi theo lịch bền vững, phải có cơ chế lưu và điều phối phù hợp; giao diện này không tự cung cấp điều đó.

## 9. Giữ scheduler khỏe khi có nhiều lịch

ScheduledThreadPoolExecutor dùng hàng đợi không giới hạn nhỏ theo cấu hình và hoạt động chủ yếu theo corePoolSize. Tăng maximumPoolSize không tạo cùng hiệu quả mở rộng như một ThreadPoolExecutor thông thường với hàng đợi giới hạn.

Cần giới hạn lượng lịch được tạo nếu nguồn yêu cầu mở có thể gửi rất nhiều. Mỗi lịch có thể giữ dữ liệu và handle trong suốt thời gian chờ.

Khi hủy nhiều lịch xa, lớp này có `setRemoveOnCancelPolicy(true)` để loại các tác vụ hủy khỏi hàng đợi ngay theo cơ chế của nó. Mặc định, phần tử hủy có thể còn được giữ tới khi độ trễ hết. Đây là vấn đề quản lý tham chiếu/bộ nhớ, khác việc Future đã có trạng thái canceled.

Tác vụ chậm cũng chiếm luồng scheduler và có thể làm lịch khác bắt đầu muộn. Một hướng thiết kế là giữ phần chạy trong scheduler ngắn, rồi gửi việc nặng tới bộ thực thi riêng có ngân sách. Khi đó phải quản lý thêm từ chối, thời hạn, hủy và thứ tự đóng hai thành phần; không coi việc gửi sang nơi khác là khả năng xử lý vô hạn.

## 10. Độ trễ tương đối khác lịch theo ngày giờ

Schedule nhận một khoảng trễ và TimeUnit, không nhận một ngày giờ tuyệt đối.

Nếu muốn chạy vào một thời điểm lịch:

1. Xác định thời điểm đích bằng API thời gian phù hợp.
2. Tính khoảng còn lại tại lúc lập lịch.
3. Chọn chính sách nếu thời điểm đã qua.
4. Hiểu rằng thay đổi đồng hồ lịch, múi giờ hoặc nhu cầu điều chỉnh lịch không tự được biểu đạt lại bởi một độ trễ đã đặt.

Một lịch “sau 30 phút” và lịch “đúng 09:00 mỗi ngày theo múi giờ địa phương” là hai hợp đồng khác nhau. Ví dụ thứ hai còn có vấn đề lịch theo ngày, thay đổi múi giờ và khoảng chuyển giờ theo địa phương; không thay bằng một số mili giây cố định mà cho rằng mọi yêu cầu đã được đáp ứng.

Bài này chỉ dùng độ trễ tương đối một lần để giữ phạm vi rõ ràng.

## 11. Phân biệt ngắn với lập lịch lặp

| API | Ý định |
| --- | --- |
| `schedule` | Chạy một lần sau độ trễ |
| `scheduleAtFixedRate` | Lặp theo các mốc chu kỳ dự kiến |
| `scheduleWithFixedDelay` | Lặp với khoảng chờ sau khi lần trước kết thúc |

Nếu muốn thử lại có điều kiện sau một lần lỗi, có thể cần schedule một lần ở thời điểm ra quyết định thử lại, kèm giới hạn số lượt và deadline; không tự biến thành lịch lặp vô hạn.

Nếu cần lặp liên tục, phải hiểu riêng hành vi khi tác vụ lỗi, thời gian chạy dài và hủy chuỗi. Đừng lấy kết quả get của tác vụ một lần trong bài để suy ra hợp đồng get của một chuỗi định kỳ.

## 12. Tự kiểm tra trước một lịch trì hoãn

Ứng dụng cần làm mới dữ liệu sau 500 ms. Hãy trả lời:

1. Mốc 500 ms là lúc đủ điều kiện hay cam kết bắt đầu chính xác?
2. Nếu mọi luồng scheduler đều bận, công việc có thể muộn không?
3. Ai giữ handle để biết kết quả hoặc hủy?
4. Nếu get hết thời gian chờ, tác vụ có tự hủy không?
5. Lịch chưa đến hạn sẽ được xử lý thế nào khi ứng dụng shutdown?
6. Nếu tiến trình khởi động lại, công việc có cần khôi phục không?

Câu trả lời quyết định scheduler chỉ là nơi hẹn giờ trong bộ nhớ hay là một phần của quy trình công việc rộng hơn. Với tác vụ chạy sau độ trễ, điều cốt lõi là giữ rõ các mốc đặt lịch, đủ điều kiện, thực thi và kết thúc.
