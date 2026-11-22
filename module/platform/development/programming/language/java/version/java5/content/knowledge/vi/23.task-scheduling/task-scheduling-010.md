# Vòng đời ScheduledThreadPoolExecutor khi ứng dụng dừng

## 1. Dừng ứng dụng không chỉ là ngừng đặt lịch mới

Một scheduler đang có:

- Một lần làm mới dữ liệu đang chạy.
- Một thông báo sẽ chạy sau một ngày.
- Một lịch thăm dò định kỳ.

Khi ứng dụng dừng, ba nhóm này không nhất thiết có cùng chính sách. Có thể cần cho phần đang chạy hoàn tất, hủy thông báo xa và ngừng mọi lượt thăm dò tiếp theo.

Nếu chỉ gọi shutdown rồi coi đã dọn xong, ứng dụng có thể tiếp tục chờ một lịch rất xa hoặc đóng nguồn dữ liệu khi tác vụ vẫn đang sử dụng.

Cần phân biệt:

```text
ngừng nguồn đăng ký
    -> ngừng tiếp nhận lịch
        -> xử lý phần đang chạy/chờ theo chính sách
            -> xác nhận scheduler kết thúc
                -> đóng tài nguyên phụ thuộc
```

Bài dùng Java 17+ cho ví dụ chính. Phần AutoCloseable có từ Java 19 được giải thích riêng trong bối cảnh Java hiện đại.

## 2. Các mốc vòng đời và API

| API/trạng thái | Ý nghĩa |
| --- | --- |
| `shutdown()` | Bắt đầu dừng có trật tự; không nhận việc mới |
| `isShutdown()` | Đã bắt đầu quá trình đóng tiếp nhận |
| `shutdownNow()` | Cố ngắt việc đang chạy, lấy việc chờ ra khỏi queue |
| `awaitTermination(timeout, unit)` | Chờ sau yêu cầu dừng tới khi kết thúc, hết thời gian hoặc bị ngắt |
| `isTerminated()` | Không còn công việc đang chạy/chờ theo vòng đời bộ thực thi |

Shutdown và shutdownNow không tự chờ mọi phần thực thi kết thúc. IsShutdown đúng cũng không chứng minh isTerminated đúng.

Bộ thực thi đã dừng không có thao tác mở lại để nhận việc. Nếu ứng dụng cần vòng đời mới, tạo instance mới với quyền sở hữu và cấu hình rõ ràng.

Lời gọi schedule/submit sau shutdown bị xử lý theo rejection handler. Với cấu hình mặc định của ScheduledThreadPoolExecutor, nó ném RejectedExecutionException; nếu thay handler, phải hiểu hợp đồng từ chối tương ứng.

## 3. Ba chính sách phải chọn trước khi dừng

| Chính sách | Mặc định | Tác động |
| --- | --- | --- |
| `executeExistingDelayedTasksAfterShutdownPolicy` | true | Cho lịch một lần đã nhận còn chờ tiếp tục sau shutdown khi đến hạn |
| `continueExistingPeriodicTasksAfterShutdownPolicy` | false | Không tiếp tục các lượt định kỳ sau shutdown |
| `removeOnCancelPolicy` | false | Không bắt buộc gỡ ngay phần tử hủy khỏi queue lúc hủy |

Các phương thức cấu hình tương ứng:

```java
scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
scheduler.setRemoveOnCancelPolicy(true);
```

Ở đây scheduler có kiểu ScheduledThreadPoolExecutor. Đây là một **chính sách ví dụ**: không giữ lịch một lần chưa đến hạn khi dừng, không tiếp tục chuỗi định kỳ và gỡ phần tử hủy khỏi queue sớm. Nó không phải cấu hình đúng bắt buộc cho mọi ứng dụng. [Tài liệu chính sách ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)

Hai điều cần đọc chính xác:

- Tắt execute-existing-delayed làm các lịch một lần **chưa hết độ trễ** bị hủy khi shutdown; không coi nó là yêu cầu ngắt mọi tác vụ đã chạy hoặc đã đến hạn.
- Không tiếp tục chuỗi định kỳ nghĩa là ngừng các lượt sau theo vòng đời; shutdown không tự ngắt phần thân của lượt hiện tại.

Nếu bật continue-existing-periodic thành true, các lượt lặp có thể tiếp tục sau shutdown. Khi đó scheduler không thể kết thúc nếu chuỗi vẫn tiếp tục; cần hủy chuỗi, đổi chính sách hoặc shutdownNow theo hợp đồng.

Remove-on-cancel là chính sách giữ phần tử/tham chiếu trong queue. Nó không thay thế quyết định công việc nào được phép hoàn tất sau khi ứng dụng bắt đầu dừng.

## 4. Thí nghiệm: lịch xa có thể giữ scheduler chưa kết thúc

Để không phụ thuộc tốc độ tác vụ, ví dụ đặt cả lịch một lần và lượt đầu của chuỗi định kỳ sau một ngày. Không cần chờ một ngày: chương trình chủ động hủy lịch còn lại sau khi quan sát.

Tệp **ShutdownPoliciesDemo.java**:

```java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ShutdownPoliciesDemo {
    public static void main(String[] args) throws Exception {
        inspect(true);
        inspect(false);
    }

    private static void inspect(boolean keepDelayed) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(keepDelayed);
        scheduler.setRemoveOnCancelPolicy(true);
        AtomicInteger delayedRuns = new AtomicInteger();
        AtomicInteger periodicRuns = new AtomicInteger();
        String label = "keepDelayed=" + keepDelayed;

        ScheduledFuture<Integer> delayed = scheduler.schedule(
                delayedRuns::incrementAndGet, 1, TimeUnit.DAYS);
        ScheduledFuture<?> periodic = scheduler.scheduleWithFixedDelay(
                () -> periodicRuns.incrementAndGet(),
                1, 1, TimeUnit.DAYS);

        try {
            scheduler.shutdown();

            System.out.println(label + ": shutdown=" + scheduler.isShutdown());
            System.out.println(label + ": periodicCancelled="
                    + periodic.isCancelled());
            System.out.println(label + ": delayedCancelled="
                    + delayed.isCancelled());

            long waitMillis = keepDelayed ? 10 : 5000;
            boolean terminated = scheduler.awaitTermination(
                    waitMillis, TimeUnit.MILLISECONDS);
            System.out.println(label + ": terminatedBeforeOwnerCleanup="
                    + terminated);

            delayed.cancel(false);
            periodic.cancel(false);
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not terminate");
            }

            System.out.println(label + ": terminatedAfterOwnerCleanup="
                    + scheduler.isTerminated());
            System.out.println(label + ": bodyRuns="
                    + delayedRuns.get() + "," + periodicRuns.get());
        } finally {
            delayed.cancel(true);
            periodic.cancel(true);
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
javac --release 17 ShutdownPoliciesDemo.java
java ShutdownPoliciesDemo
```

Stdout khi lịch xa chưa đến hạn trong thí nghiệm:

```text
keepDelayed=true: shutdown=true
keepDelayed=true: periodicCancelled=true
keepDelayed=true: delayedCancelled=false
keepDelayed=true: terminatedBeforeOwnerCleanup=false
keepDelayed=true: terminatedAfterOwnerCleanup=true
keepDelayed=true: bodyRuns=0,0
keepDelayed=false: shutdown=true
keepDelayed=false: periodicCancelled=true
keepDelayed=false: delayedCancelled=true
keepDelayed=false: terminatedBeforeOwnerCleanup=true
keepDelayed=false: terminatedAfterOwnerCleanup=true
keepDelayed=false: bodyRuns=0,0
```

Thí nghiệm bật remove-on-cancel để lần hủy chủ động loại phần tử khỏi queue ngay. Nếu giữ phần tử hủy trong queue của lịch xa, phải xét thêm việc dọn queue thay vì giả định mọi lần hủy đều làm scheduler kết thúc tức thì.

Nhánh true tương ứng mặc định giữ lịch một lần: scheduler đã shutdown nhưng vẫn còn lịch xa cần chờ. Nhánh false hủy lịch chưa đến hạn nên có thể kết thúc.

Chuỗi định kỳ chưa bắt đầu bị hủy ở cả hai nhánh vì chính sách tiếp tục định kỳ vẫn giữ mặc định false.

Lượt chờ 10 ms chỉ để quan sát scheduler chưa thể kết thúc trong nhánh còn lịch một ngày; nó không phải công thức chọn ngân sách dừng ứng dụng. Chương trình chủ động dọn handle sau quan sát, không để một tiến trình thử nghiệm tồn tại tới ngày hôm sau.

## 5. shutdownNow lấy việc chờ ra, nhưng handle còn cần chính sách

ShutdownNow trả danh sách những công việc chưa bắt đầu đã được lấy khỏi queue. Với ScheduledThreadPoolExecutor, phần tử là ScheduledFuture; với các tác vụ schedule, đó là đối tượng handle tương ứng.

Không xem việc “đã lấy khỏi queue” thành bảo đảm rằng mọi Future bên gọi đang giữ đã được hoàn tất/hủy theo điều họ mong muốn. Bên sở hữu nên quyết định cách báo không thực hiện, hủy hoặc chuyển công việc.

Thí nghiệm giữ một tác vụ đang chạy và một lịch xa. Khi shutdownNow, mã chủ động hủy các Future trong danh sách bị lấy ra để không để kết quả chờ bị bỏ lửng.

Tệp **ShutdownNowScheduledDemo.java**:

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownNowScheduledDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean observedInterrupt = new AtomicBoolean();

        ScheduledFuture<String> running = scheduler.schedule(() -> {
            started.countDown();
            try {
                release.await();
                return "released";
            } catch (InterruptedException ex) {
                observedInterrupt.set(true);
                Thread.currentThread().interrupt();
                return "interrupted";
            }
        }, 0, TimeUnit.MILLISECONDS);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            ScheduledFuture<Integer> pending =
                    scheduler.schedule(() -> 7, 1, TimeUnit.DAYS);

            List<Runnable> notStarted = scheduler.shutdownNow();
            for (Runnable command : notStarted) {
                if (command instanceof Future<?> future) {
                    future.cancel(false);
                }
            }

            System.out.println("notStarted=" + notStarted.size());
            System.out.println("pendingCancelled=" + pending.isCancelled());

            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Scheduler did not terminate");
            }

            System.out.println("runningResult=" + running.get());
            System.out.println("runningObservedInterrupt="
                    + observedInterrupt.get());
            System.out.println("terminated=" + scheduler.isTerminated());
        } finally {
            release.countDown();
            running.cancel(true);
            for (Runnable command : scheduler.shutdownNow()) {
                if (command instanceof Future<?> future) {
                    future.cancel(false);
                }
            }
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```shell
javac --release 17 ShutdownNowScheduledDemo.java
java ShutdownNowScheduledDemo
```

Stdout:

```text
notStarted=1
pendingCancelled=true
runningResult=interrupted
runningObservedInterrupt=true
terminated=true
```

Tác vụ đang chạy nhận ngắt và **chủ động** trả kết quả `interrupted` trong ví dụ. Vì không hủy trực tiếp handle running trước đó, get có thể đọc kết quả đã được phần thân trả về. Đây là lựa chọn minh họa để phân biệt tín hiệu ngắt với trạng thái hủy Future, không phải khuôn trả thành công cho mọi yêu cầu bị dừng.

Trong nghiệp vụ khác, phần thân có thể truyền lỗi ngắt hoặc biểu diễn trạng thái chưa hoàn tất riêng. Không giả vờ thao tác chính đã thành công chỉ vì cần thoát phần thân.

ShutdownNow chỉ cố ngắt tác vụ đang chạy; tác vụ bỏ qua ngắt vẫn có thể làm scheduler không kết thúc. [Tài liệu ScheduledThreadPoolExecutor.shutdownNow](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html#shutdownNow())

## 6. Dừng hai giai đoạn với kết quả quan sát rõ ràng

Sau khi đã chọn chính sách tại lúc cấu hình, bên sở hữu có thể thực hiện:

1. Shutdown để ngừng tiếp nhận, cho phần được phép hoàn tất.
2. Chờ trong ngân sách giai đoạn một.
3. Nếu chưa kết thúc, shutdownNow và xử lý việc lấy khỏi queue.
4. Chờ thêm trong ngân sách giai đoạn hai.
5. Báo chưa xác nhận kết thúc nếu vẫn còn tác vụ.

Đoạn dưới là **phương thức tiện ích trong một lớp**, cần nhập List, Future, ScheduledThreadPoolExecutor và TimeUnit:

```java
static void cancelRemovedCommands(List<Runnable> commands) {
    for (Runnable command : commands) {
        if (command instanceof Future<?> future) {
            future.cancel(false);
        }
    }
}

static boolean stopOwnedScheduler(ScheduledThreadPoolExecutor scheduler)
        throws InterruptedException {
    scheduler.shutdown();

    try {
        if (scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
            return true;
        }

        cancelRemovedCommands(scheduler.shutdownNow());
        return scheduler.awaitTermination(2, TimeUnit.SECONDS);
    } catch (InterruptedException ex) {
        cancelRemovedCommands(scheduler.shutdownNow());
        throw ex;
    }
}
```

Return true là đã quan sát scheduler kết thúc. Return false nghĩa chưa xác nhận kết thúc sau lượt chờ thứ hai. Ném InterruptedException nghĩa luồng điều phối bị ngắt; phương thức đã yêu cầu dừng mạnh hơn rồi truyền tín hiệu cho tầng gọi.

Nếu tầng trên không truyền tiếp ngoại lệ ngắt, nó cần khôi phục cờ ngắt rồi rời luồng xử lý theo chính sách. Không biến ngắt thành “dừng thành công”.

Các mốc 5 và 2 giây là ví dụ ngân sách chờ. Chúng không buộc tác vụ hoặc tài nguyên ngoài phải dừng trong đúng 7 giây. Chính sách cho trường hợp không dừng được thuộc về vận hành ứng dụng.

Phương thức chỉ dùng cho scheduler thuộc quyền sở hữu của bên gọi và các policy đã được lựa chọn. Nó không tự thay mọi policy hay đóng tài nguyên mượn dùng chung.

## 7. Tác vụ phải được viết để có thể kết thúc

Một quy trình shutdown tốt vẫn có thể thất bại nếu phần thân:

- Lặp vô hạn mà không kiểm tra yêu cầu ngắt.
- Chờ I/O không có timeout hay cơ chế đóng phù hợp.
- Nuốt InterruptedException rồi tiếp tục công việc.
- Chờ một tác vụ con trên cùng scheduler đã cạn luồng.
- Gửi lại lịch mới khi đang dừng rồi không xử lý từ chối.

Tín hiệu ngắt là cơ chế hợp tác, không là lệnh cưỡng ép kết thúc mọi câu lệnh. Tài nguyên chặn có thể cần phương thức hủy hoặc đóng riêng.

Future đã isCancelled hoặc isDone không xác nhận phần thân đã đi qua finally. Muốn đóng một tài nguyên phụ thuộc an toàn, cần mốc hoàn tất phù hợp hoặc xác nhận cả bộ thực thi đã kết thúc. [Tài liệu Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean))

Không gọi phương thức chờ scheduler kết thúc từ chính một tác vụ đang chạy trên scheduler đó: nó có thể chờ sự kết thúc của bản thân. Hãy báo tín hiệu cho thành phần điều phối bên ngoài.

## 8. Thứ tự đóng khi scheduler gọi worker hoặc nguồn dữ liệu

Một thiết kế phổ biến:

```text
scheduler
    -> callback định kỳ
        -> worker nhận việc nặng
            -> kết nối dữ liệu/dịch vụ ngoài
```

Khi dừng:

1. Ngừng nguồn đăng ký và ngăn callback phát thêm công việc theo hợp đồng.
2. Hủy/đóng scheduler, chờ callback đang chạy kết thúc hoặc xử lý theo chính sách.
3. Đóng tiếp nhận ở worker.
4. Chờ/hủy công việc đã gửi sang worker.
5. Đóng nguồn dữ liệu và các tài nguyên còn phụ thuộc.

Nếu đóng worker trước mà callback vẫn đang gửi, nó có thể nhận RejectedExecutionException. Nếu đóng cơ sở dữ liệu trước, công việc đang chạy có thể lỗi giữa chừng.

Hủy ScheduledFuture của callback không tự hủy các Future mà callback đã tạo ở worker. Cần quản lý handle và quyền sở hữu của toàn quy trình, không chỉ điểm hẹn giờ.

Nếu một phần không kết thúc trong ngân sách, không giả định đã an toàn để đóng mọi tài nguyên còn lại. Phải ghi nhận tình trạng và áp dụng chính sách vận hành đã chọn.

## 9. Java 19+: close có thể chờ lịch còn lại

ExecutorService triển khai AutoCloseable từ Java 19; vì thế scheduler có thể được dùng trong try-with-resources trên Java hiện đại.

Close khởi động shutdown và chờ kết thúc. Nó không nhận timeout. Nếu policy mặc định vẫn giữ một lịch một lần sau một ngày, việc đóng có thể chờ lịch đó.

Nếu bật tiếp tục chuỗi định kỳ sau shutdown, một chuỗi tiếp tục chạy có thể giữ thao tác đóng không trả về. Cú pháp tự động không thay thế quyết định policy.

Khi luồng đang close bị ngắt, cơ chế mặc định yêu cầu dừng như shutdownNow, tiếp tục chờ rồi khôi phục cờ ngắt trước khi trả về. Đừng nhầm điều này với một phương thức đóng có thời hạn cứng. [Tài liệu ExecutorService.close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#close())

Khi cần ngân sách shutdown riêng, điều phối tường minh như phương thức hai giai đoạn giúp biểu đạt kết quả quan sát rõ hơn.

## 10. Quyền sở hữu, daemon và tiến trình

Scheduler do thành phần ứng dụng tạo riêng thường phải được chính thành phần quản lý vòng đời đóng. Thành phần chỉ mượn scheduler dùng chung thường chỉ hủy các lịch nó sở hữu.

Factory mặc định tạo luồng nền tảng non-daemon; quên dừng scheduler có thể khiến tiến trình chưa thoát dù main hoặc phần nghiệp vụ chính đã kết thúc.

Chuyển sang daemon chỉ thay đổi việc luồng tham gia điều kiện kết thúc JVM; nó không xác nhận công việc đã hoàn tất, không tự lưu lịch và không bảo đảm dọn tài nguyên. [Tài liệu Thread và daemon](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html)

Không chờ thu gom rác để đóng lịch. Vòng đời tài nguyên cần một điểm điều phối rõ trong ứng dụng/container và có thể kiểm chứng.

## 11. Việc dừng trong bộ nhớ khác phục hồi sau khởi động lại

Các lịch của ScheduledThreadPoolExecutor là trạng thái trong tiến trình. Khi tiến trình kết thúc, scheduler không tự phục hồi danh sách lịch và không cung cấp bảo đảm đúng một lần qua mọi lần khởi động.

Nếu một lịch xa bắt buộc không được mất, cần lưu định danh, thời điểm, trạng thái và chính sách phục hồi ở một cơ chế phù hợp. Việc đổi policy shutdown không biến hàng đợi RAM thành kho công việc bền vững.

Tương tự, shutdownNow không tự hoàn tác tác dụng phụ đã gửi tới hệ thống ngoài. Muốn chạy lại sau khi dừng giữa chừng, cần khả năng xử lý lặp an toàn và kiểm tra trạng thái nghiệp vụ.

## 12. Kiểm chứng quy trình dừng

Một kiểm chứng đủ ý nghĩa nên xác nhận:

- Lịch mới sau đóng tiếp nhận nhận phản hồi đúng hợp đồng.
- Lịch một lần chưa đến hạn được giữ hoặc hủy đúng policy.
- Chuỗi định kỳ không tiếp tục ngoài ý định.
- Tác vụ đang chạy được hoàn tất hoặc đáp ứng dừng.
- Future của việc không chạy không bị để chờ vô hạn.
- Scheduler thực sự terminated trước khi báo dừng thành công.
- Tài nguyên phụ thuộc đóng theo đúng mốc.

Không chỉ kiểm tra isShutdown. Cũng không dùng sleep một khoảng ngắn rồi coi không thấy log mới là bằng chứng mọi xử lý đã dừng.

Khi đọc mã đóng một scheduler, câu hỏi cuối cùng nên là: **sau từng bước, còn việc nào được phép chạy, việc nào đã được xác nhận dừng và ai chịu trách nhiệm cho phần chưa kết thúc?** Câu trả lời đó mới mô tả đầy đủ vòng đời ứng dụng.
