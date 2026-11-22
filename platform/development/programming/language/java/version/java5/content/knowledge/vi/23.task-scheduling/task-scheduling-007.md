# ScheduledFuture và điều khiển hủy lịch

## 1. Handle của lịch là quyền điều khiển phần việc nào?

Sau khi gọi schedule, ứng dụng có thể cần bỏ một thông báo chưa đến giờ hoặc dừng một chuỗi làm mới dữ liệu. Muốn làm đúng phải giữ handle trả về và biết handle đó đại diện cho điều gì.

`ScheduledFuture<V>` kết hợp:

- Hợp đồng Future: kết quả, lỗi, trạng thái và yêu cầu hủy.
- Hợp đồng Delayed: quan sát thời gian còn lại qua getDelay và khả năng so sánh theo độ trễ.

Một lịch một lần đại diện cho một phép thực thi. Một lịch định kỳ đại diện cho **toàn bộ chuỗi**, không chỉ một lượt. [Tài liệu ScheduledFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

Điều khiển hủy lịch cần phân biệt ba mốc:

```text
yêu cầu hủy
    -> Future ghi nhận trạng thái hủy
        -> mã đang chạy thực sự thoát/dọn tài nguyên
```

Hai mốc sau không tự là một thời điểm. Bài dùng Java 17+ và các cơ chế vẫn áp dụng trên Java hiện đại.

## 2. Lịch một lần và lịch lặp khác nhau ở get

| Nguồn tạo handle | Handle đại diện | get khi hoàn tất bình thường |
| --- | --- | --- |
| `schedule(Runnable, ...)` | Một lần thực hiện | Trả null |
| `schedule(Callable<V>, ...)` | Một lần có kết quả | Trả giá trị V |
| `scheduleAtFixedRate(...)` | Chuỗi lặp | Không có lần trả bình thường cho chuỗi đang hoạt động |
| `scheduleWithFixedDelay(...)` | Chuỗi lặp | Không có lần trả bình thường cho chuỗi đang hoạt động |

Khi lịch bị hủy, get ném CancellationException. Khi phần thực thi kết thúc bằng lỗi, get ném ExecutionException để bên đọc truy nguyên cause.

Với chuỗi định kỳ, một lượt chạy thành công không làm Future của cả chuỗi thành công. Nếu một lượt ném ngoại lệ ra ngoài, những lượt sau bị chặn và handle kết thúc lỗi. [Tài liệu ScheduledExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)

Đừng gọi get vô hạn chỉ để “đợi lượt đầu xong” trên handle định kỳ. Nếu cần mốc lượt đầu, dùng tín hiệu hoặc kết quả được thiết kế riêng.

## 3. Đọc đúng cancel và trạng thái

Chữ ký:

```java
boolean cancel(boolean mayInterruptIfRunning);
```

| Tình huống | cancel(false) | cancel(true) |
| --- | --- | --- |
| Lịch chưa bắt đầu và hủy được chấp nhận | Ngăn phần việc đó chạy | Tương tự |
| Lần thực thi đang chạy, lớp triển khai cho phép hủy | Không yêu cầu ngắt mã đang chạy | Cố gửi tín hiệu ngắt tới luồng được biết |
| Chuỗi định kỳ được hủy | Không tiếp tục các lượt sau | Tương tự, có thêm yêu cầu ngắt lượt đang chạy |
| Future đã có trạng thái kết thúc | Không thay đổi kết quả cuối | Không thay đổi kết quả cuối |

Giá trị trả về của cancel nói về lần cố hủy đó. Để xem Future hiện có bị hủy hay không, dùng isCancelled. Một lời gọi trả false có thể là vì lịch đã hoàn thành hoặc một bên khác đã hủy trước.

Khi Future đã hủy, isDone cũng đúng. Nhưng isDone không có nghĩa mã tác vụ đã dọn tài nguyên xong. Cancel không có thao tác “join phần thân đang chạy”. [Tài liệu Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean))

Không dùng cancel(false) rồi cancel(true) như cách tăng mức dừng: nếu lần đầu đã chuyển handle sang hủy, lần sau không có tác dụng thay đổi trạng thái và không bảo đảm gửi thêm ngắt. Chọn chính sách từ đầu hoặc có giao thức dừng riêng cho công việc khi cần.

## 4. Hủy lịch chưa đến hạn và việc giữ phần tử trong queue

Hủy thành công trước khi lịch chạy sẽ ngăn phần thân. Tuy nhiên, với ScheduledThreadPoolExecutor mặc định, phần tử đã hủy không nhất thiết được loại khỏi hàng đợi ngay; nó có thể được giữ tới lúc độ trễ hết.

Lớp cụ thể cung cấp:

```java
scheduler.setRemoveOnCancelPolicy(true);
```

Trong đoạn này, scheduler có kiểu ScheduledThreadPoolExecutor. Chính sách giúp loại tác vụ hủy khỏi queue ngay theo cơ chế của lớp. Nó quản lý việc giữ phần tử/tham chiếu trong bộ nhớ, khác với trạng thái canceled và khác việc ngắt mã đang chạy.

### Thí nghiệm so sánh chính sách giữ queue

Tệp **CancelledScheduleQueueDemo.java**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CancelledScheduleQueueDemo {
    public static void main(String[] args) throws Exception {
        inspect(false);
        inspect(true);
    }

    private static void inspect(boolean removeOnCancel) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setRemoveOnCancelPolicy(removeOnCancel);
        AtomicInteger bodyRuns = new AtomicInteger();
        String label = "remove=" + removeOnCancel;

        try {
            ScheduledFuture<Integer> pending = scheduler.schedule(
                    bodyRuns::incrementAndGet,
                    1, TimeUnit.DAYS);

            System.out.println(label + ": queueBefore="
                    + scheduler.getQueue().size());
            System.out.println(label + ": cancelReturned="
                    + pending.cancel(false));
            System.out.println(label + ": cancelled=" + pending.isCancelled());
            System.out.println(label + ": done=" + pending.isDone());
            System.out.println(label + ": queueAfter="
                    + scheduler.getQueue().size());

            try {
                pending.get();
            } catch (CancellationException ex) {
                System.out.println(label + ": get=CancellationException");
            }

            String health = scheduler.schedule(
                    () -> "OK", 0, TimeUnit.MILLISECONDS)
                    .get(5, TimeUnit.SECONDS);
            System.out.println(label + ": scheduler=" + health);
            System.out.println(label + ": bodyRuns=" + bodyRuns.get());
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
javac --release 17 CancelledScheduleQueueDemo.java
java CancelledScheduleQueueDemo
```

Stdout trong thí nghiệm, khi hủy lịch xa ngay sau đăng ký:

```text
remove=false: queueBefore=1
remove=false: cancelReturned=true
remove=false: cancelled=true
remove=false: done=true
remove=false: queueAfter=1
remove=false: get=CancellationException
remove=false: scheduler=OK
remove=false: bodyRuns=0
remove=true: queueBefore=1
remove=true: cancelReturned=true
remove=true: cancelled=true
remove=true: done=true
remove=true: queueAfter=0
remove=true: get=CancellationException
remove=true: scheduler=OK
remove=true: bodyRuns=0
```

Ở cả hai chính sách, lịch đã canceled và phần thân không chạy. Khác biệt là phần tử còn trong queue hay được gỡ ngay.

Tác vụ kiểm tra sức khỏe chạy thành công cho thấy hủy handle không đóng scheduler. Ví dụ đặt một ngày để lịch chưa đến hạn trong lần chạy thí nghiệm thông thường; finally dùng shutdownNow để không đợi tới ngày hôm sau.

Khi hệ thống tạo/hủy rất nhiều lịch xa, cần xem xét chính sách lưu queue và nguồn đăng ký. Không kết luận cứ canceled là mọi phần tử và tham chiếu đều được giải phóng ngay. [Tài liệu remove-on-cancel policy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html#setRemoveOnCancelPolicy(boolean))

## 5. Hủy chuỗi khi một lượt đang chạy

Muốn dừng các lượt tiếp theo nhưng cho lượt hiện tại kết thúc, cancel(false) thường thể hiện đúng ý định với bộ lập lịch chuẩn.

Muốn yêu cầu lượt hiện tại ngừng sớm, có thể dùng cancel(true), nhưng phần thân cần đáp ứng ngắt. Nếu nó đang chờ bằng API hỗ trợ InterruptedException, phải truyền lỗi ngắt hoặc rời phần xử lý phù hợp, thay vì bắt rồi tiếp tục làm việc vô hạn.

Thí nghiệm sau dùng một chốt để giữ lượt đầu đang chạy. Vì main hủy trước khi mở chốt, không có lượt thứ hai phát sinh do main bị chậm lịch.

Tệp **PeriodicCancellationDemo.java**:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicCancellationDemo {
    public static void main(String[] args) throws Exception {
        inspect(false);
        inspect(true);
    }

    private static void inspect(boolean interrupt) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch bodyExited = new CountDownLatch(1);
        AtomicInteger runs = new AtomicInteger();
        AtomicBoolean observedInterrupt = new AtomicBoolean();
        String label = "interrupt=" + interrupt;

        ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                () -> {
                    runs.incrementAndGet();
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        observedInterrupt.set(true);
                        Thread.currentThread().interrupt();
                    } finally {
                        bodyExited.countDown();
                    }
                },
                0, 1, TimeUnit.MILLISECONDS);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Execution did not start");
            }

            handle.cancel(interrupt);
            System.out.println(label + ": cancelled=" + handle.isCancelled());
            System.out.println(label + ": done=" + handle.isDone());

            if (!interrupt) {
                System.out.println(label + ": bodyExitedBeforeRelease="
                        + (bodyExited.getCount() == 0));
            }

            release.countDown();
            if (!bodyExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Execution did not exit");
            }

            try {
                handle.get();
            } catch (CancellationException ex) {
                System.out.println(label + ": get=CancellationException");
            }

            scheduler.shutdown();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not terminate");
            }

            System.out.println(label + ": runs=" + runs.get());
            System.out.println(label + ": observedInterrupt="
                    + observedInterrupt.get());
        } finally {
            handle.cancel(true);
            release.countDown();
            scheduler.shutdownNow();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Scheduler termination was not confirmed");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 PeriodicCancellationDemo.java
java PeriodicCancellationDemo
```

Stdout:

```text
interrupt=false: cancelled=true
interrupt=false: done=true
interrupt=false: bodyExitedBeforeRelease=false
interrupt=false: get=CancellationException
interrupt=false: runs=1
interrupt=false: observedInterrupt=false
interrupt=true: cancelled=true
interrupt=true: done=true
interrupt=true: get=CancellationException
interrupt=true: runs=1
interrupt=true: observedInterrupt=true
```

Trong nhánh false, handle đã done/cancelled nhưng lượt đang chạy vẫn bị giữ. Chỉ sau khi main mở chốt, phần thân mới rời tới finally.

Trong nhánh true, yêu cầu ngắt làm await ném InterruptedException. Mã ghi nhận ngắt rồi kết thúc phần xử lý. Cả hai nhánh không có lượt thứ hai vì chuỗi đã bị hủy.

Chốt bodyExited chứng minh tác vụ đã đi qua điểm cuối dọn dẹp được định nghĩa trong Runnable. AwaitTermination sau shutdown xác nhận thêm vòng đời cả scheduler trong thí nghiệm. Không thay hai bằng chứng đó bằng get trên handle đã canceled.

## 6. getDelay không phải trạng thái hủy hoặc tiến độ

Một ScheduledFuture có thể báo delay dương khi đang chờ, hoặc delay không dương khi đã đến hạn. Đến hạn không chứng minh đã có luồng thực hiện.

Sau khi hủy, không dùng getDelay về 0 như điều kiện xác nhận hủy. Trạng thái hủy thuộc isCancelled và kết quả get thuộc hợp đồng Future; thời gian trì hoãn không thay thế chúng.

GetDelay cũng không nói “còn bao lâu công việc xong”. Thời gian thực thi có thể phụ thuộc I/O, khóa hoặc dữ liệu đầu vào mà scheduler không biết.

Nếu cần giao diện đếm ngược, phải thể hiện đó là khoảng đến lúc đủ điều kiện, không hứa chắc tác vụ sẽ bắt đầu hay hoàn tất chính xác tại mốc hiển thị.

## 7. Những cuộc đua cần dự kiến

### Tác vụ hoàn tất ngay trước yêu cầu hủy

Cancel có thể không thay đổi được kết quả đã có. Nếu ứng dụng nhận false, cần xem trạng thái/kết quả phù hợp; không tự báo tác vụ bị hủy thành công.

### Hai nơi cùng hủy

Một nơi có thể đã hủy trước. Kết quả false của nơi còn lại không chứng minh lịch đang hoạt động. Dùng isCancelled để quan sát trạng thái thay vì chỉ dùng giá trị trả về của một lần cancel.

### Lịch bắt đầu trước khi nơi gọi gán xong biến handle

Nếu initialDelay bằng 0, Runnable có thể chạy trước khi câu lệnh gán handle ở bên gọi hoàn tất. Vì vậy, mã tự hủy trong callback cần một giao thức công bố handle đúng, không giả định một biến hoặc AtomicReference đã được điền kịp.

Các thí nghiệm đặt điều phối hủy ở main sau tín hiệu started để tránh cuộc đua này.

### Cancel false rồi muốn chuyển thành true

Sau khi handle đã hủy, một lần cancel tiếp theo không có nghĩa nâng cấp thành một tín hiệu ngắt mới. Nếu cần hai giai đoạn dừng công việc, phải thiết kế cơ chế điều khiển tác vụ hoặc vòng đời tài nguyên rõ ràng.

Không tự gọi get trên Future của chính chuỗi từ trong lần thực thi đó để chờ mình kết thúc. Nó có thể tạo quan hệ chờ vào chính công việc đang giữ luồng.

## 8. Hủy lịch không hủy mọi công việc mà callback đã tạo

Nếu callback gửi một tác vụ khác sang worker rồi trả về, ScheduledFuture chỉ quản lý callback/chuỗi của scheduler. Việc hủy lịch không tự truyền sang Future của công việc đã gửi.

Muốn hủy cả quy trình cần giữ các handle liên quan và định nghĩa:

- Công việc nào chưa bắt đầu cần bị ngăn.
- Công việc nào đang chạy cần tín hiệu dừng.
- Ai đợi việc dọn tài nguyên.
- Kết quả cuối cùng được báo ra sao.

Tương tự, một yêu cầu mạng đã gửi có thể vẫn được máy chủ bên ngoài xử lý. Hủy handle ở JVM không chứng minh thao tác bên kia đã được hoàn tác.

Với công việc tạo tác dụng phụ, cần thiết kế định danh và khả năng chạy lại an toàn theo nghiệp vụ. Không lấy trạng thái cancelled làm bằng chứng “chưa có gì xảy ra”.

## 9. Quyền sở hữu handle khác quyền đóng scheduler

Một thành phần có thể sở hữu một lịch trên scheduler dùng chung. Nó được phép hủy lịch của mình nhưng không tự đóng scheduler rồi làm ảnh hưởng các lịch khác.

Bên sở hữu scheduler phải chọn chính sách dừng:

- Ngừng đăng ký lịch mới.
- Hủy lịch liên quan hoặc gọi shutdown theo hợp đồng.
- Chờ/hủy phần đang chạy.
- Xác nhận kết thúc trước khi đóng tài nguyên phụ thuộc nếu cần.

ScheduledThreadPoolExecutor có chính sách riêng cho việc tiếp tục tác vụ trì hoãn một lần và chuỗi định kỳ sau shutdown. Đọc/chọn chính sách đó theo yêu cầu, không giả định mọi loại lịch đều giống nhau.

Nếu chỉ muốn dừng một nhắc việc, hủy ScheduledFuture là thao tác đúng phạm vi hơn shutdownNow trên scheduler dùng chung. Ngược lại, hủy một handle cũng không dọn mọi lịch mà ứng dụng đã tạo.

## 10. Đổi lịch là một quy trình, không phải sửa delay trong handle

ScheduledFuture không cung cấp setter để đổi thời điểm chạy của lịch đã đăng ký.

Một cách thường gặp là hủy handle cũ rồi tạo lịch mới. Nhưng cần nghĩ tới cuộc đua: lịch cũ có thể đã bắt đầu hoặc có tác dụng phụ trước khi hủy.

Khi chỉ muốn lịch mới nhất còn hiệu lực, có thể cần mã phiên bản/thế hệ để callback kiểm tra có còn là lịch hiện hành trước khi thực hiện hành động. Bản thân việc lưu một handle mới vào biến không tự làm mọi callback cũ trở nên vô hiệu.

Không tạo lịch mới rồi quên giải phóng handle cũ. Nếu nguồn yêu cầu liên tục đổi lịch, số phần tử lưu và lượng callback có thể tăng, nhất là khi chưa cấu hình remove-on-cancel phù hợp.

Một lịch trong bộ nhớ cũng không tự tồn tại qua việc tiến trình khởi động lại. Nếu yêu cầu cần bền vững, quyền hủy và trạng thái lịch phải được mô hình hóa trong một cơ chế lưu/điều phối khác phù hợp.

## 11. Quan sát một lần hủy cho đúng ý nghĩa

Các trạng thái phản hồi nên phân biệt:

| Thông điệp | Bằng chứng tương ứng |
| --- | --- |
| Đã gửi yêu cầu hủy | Lời gọi điều khiển đã được thực hiện |
| Lịch đã bị hủy | Future có trạng thái cancelled |
| Phần đang chạy đã dọn xong | Mốc hoàn tất công việc/tài nguyên đã được xác nhận |
| Scheduler đã kết thúc | AwaitTermination hoặc trạng thái vòng đời phù hợp |

Một giao diện có thể chỉ cần báo “lịch đã hủy, lần đang xử lý có thể còn kết thúc”, nếu đó là hợp đồng đã chọn. Không báo “đã dừng mọi xử lý” chỉ từ isDone.

Nên có số đo số lịch đăng ký/hủy, lịch còn hoạt động, lỗi chuỗi và lượng phần tử queue nếu cần điều tra bộ nhớ. Dữ liệu quan sát phải gắn đúng handle/định danh nghiệp vụ, không suy ra từ tên luồng làm việc.

## 12. Tự kiểm tra

Một lịch làm mới đang chạy khi người dùng nhấn Hủy. Hãy xác định:

1. Muốn cho lượt hiện tại kết thúc hay yêu cầu dừng sớm?
2. Handle đại diện một lần hay cả chuỗi?
3. Khi isCancelled đúng, còn tài nguyên nào tác vụ có thể đang dùng?
4. Nếu lịch cũ bị thay bằng lịch mới, callback cũ đã bắt đầu thì xử lý thế nào?
5. Có cần dọn phần tử hủy khỏi queue ngay không?
6. Thành phần này có quyền đóng scheduler hay chỉ quyền hủy lịch của mình?

ScheduledFuture cung cấp handle để quản lý lịch, nhưng quyền hủy, việc ngắt hợp tác và sự kết thúc thực tế cần được giữ thành những khái niệm riêng. Nhờ vậy, điều khiển lịch không trở thành nguồn hủy nhầm tài nguyên hoặc lời hứa dừng thiếu bằng chứng.
