# Ảnh hưởng của ngoại lệ đến các lần chạy tiếp theo

## 1. Một lượt lỗi có thể làm một chuỗi định kỳ ngừng hẳn

Một công việc được lập lịch chạy mỗi giây không có nghĩa nó sẽ luôn tiếp tục chạy bất chấp mọi ngoại lệ. Với `scheduleAtFixedRate` và `scheduleWithFixedDelay`, nếu một lượt ném ngoại lệ ra ngoài Runnable, các lượt tiếp theo của **đăng ký định kỳ đó** bị ngừng.

Điều này dễ bị nhầm với scheduler đã chết: ứng dụng không còn thấy bản cập nhật định kỳ, nhưng luồng của scheduler vẫn có thể xử lý những công việc khác.

Cần phân biệt ba đối tượng:

```text
scheduler                  bộ thực thi quản lý luồng và lịch
một đăng ký định kỳ          chuỗi lặp của một công việc
một lượt thực thi            một lần Runnable được gọi trong chuỗi
```

Ngoại lệ từ một lượt có thể kết thúc chuỗi của nó; không đồng nghĩa tự động shutdown toàn bộ scheduler. Kiến thức này còn áp dụng trong Java hiện nay; ví dụ chính chạy bằng Java 17 trở lên.

## 2. Hợp đồng áp dụng cho cả fixed rate và fixed delay

| Cách lập lịch | Lượt thành công bình thường | Lượt ném ngoại lệ ra ngoài |
|---|---|---|
| `schedule(Runnable/Callable, delay, unit)` | Công việc một lần hoàn tất, không có chuỗi tự lặp | Future của công việc báo thất bại |
| `scheduleAtFixedRate` | Tiếp tục các mốc theo chu kỳ dự kiến | Các lượt sau của đăng ký bị ngừng |
| `scheduleWithFixedDelay` | Chờ khoảng nghỉ sau khi xong rồi chạy lượt tiếp | Các lượt sau của đăng ký bị ngừng |

Đổi fixed rate sang fixed delay không tự giải quyết việc chuỗi dừng do ngoại lệ. Hai API khác cách tính thời điểm tiếp theo, nhưng cùng có quy tắc ngừng khi một lượt kết thúc bằng lỗi không được xử lý trong Runnable. [Hợp đồng các phương thức định kỳ](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).

“Có ngoại lệ trong một đoạn mã” và “ngoại lệ thoát khỏi lượt” cũng khác nhau. Nếu Runnable bắt một lỗi dự kiến, xử lý hợp lệ rồi kết thúc bình thường, scheduler có thể tiếp tục chuỗi. Khi đó ứng dụng đã chủ động chọn ý nghĩa của lỗi, không phải scheduler bỏ qua nó.

## 3. ScheduledFuture biểu diễn trạng thái của cả chuỗi

Phương thức đăng ký định kỳ trả `ScheduledFuture<?>`. Tay cầm này theo dõi chuỗi lặp, không phải Future riêng cho lượt thứ nhất.

- Khi chuỗi còn lặp bình thường, `get()` không trả một giá trị sau mỗi tick.
- Khi chuỗi bị hủy, get báo CancellationException.
- Khi một lượt thất bại làm chuỗi kết thúc bất thường, get báo ExecutionException với nguyên nhân gốc.
- `isDone()` bằng true không tự phân biệt thất bại với hủy; cần xét trạng thái/kết quả tương ứng.

Ví dụ minh họa bên trong một phương thức đã có scheduler và xử lý các ngoại lệ cần thiết:

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        () -> { throw new IllegalStateException("invalid state"); },
        0, 1, TimeUnit.SECONDS);

try {
    handle.get();
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
}
```

Đây là minh họa đường lỗi, không phải khuyến nghị chờ vô hạn mọi periodic Future trong luồng xử lý yêu cầu. Trong kiểm chứng hoặc giám sát cần giới hạn chờ phù hợp. `get(timeout, unit)` chỉ timeout ở phía chờ nếu chuỗi còn hoạt động; timeout đó không tự hủy chuỗi. [Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

## 4. Vì sao có thể không thấy stack trace như mong đợi?

ScheduledThreadPoolExecutor dùng đối tượng công việc có khả năng giữ trạng thái Future. Lỗi từ phần tính toán có thể được giữ trong đối tượng lịch, thay vì thoát ra khỏi luồng rồi kích hoạt UncaughtExceptionHandler.

Do đó, cài handler ở ThreadFactory chưa đủ để quan sát mọi chuỗi định kỳ thất bại. Nếu bỏ tay cầm sau khi đăng ký, một công việc có thể ngừng lặp mà không có đường báo lỗi ứng dụng mong đợi.

Tài liệu ScheduledThreadPoolExecutor cũng lưu ý afterExecute thường nhận Throwable bằng null vì công việc được bọc dưới dạng ScheduledFuture, kể cả khi lệnh bên trong đã thất bại. Nếu dùng hook để giám sát, phải hiểu đối tượng đang quan sát. Đặc biệt, không gọi get không thời hạn trên một periodic Future còn chạy bình thường ngay trong afterExecute: Future đó đại diện cả chuỗi nên chưa done. [ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

Với triển khai chuẩn, phần chạy định kỳ chỉ được đưa trở lại lịch sau một lượt hoàn tất theo đường phù hợp; khi lỗi được giữ, nó không tiếp tục tái lập lịch lượt sau. Đây là cách đọc cơ chế từ [mã nguồn OpenJDK](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ScheduledThreadPoolExecutor.java), không phải một lý do để phụ thuộc vào tên lớp nội bộ của scheduler.

## 5. Chương trình đầy đủ: hai chuỗi lỗi và một chuỗi xử lý lỗi dự kiến

Thí nghiệm có ba phần:

1. Fixed rate ném lỗi ở lượt thứ hai, sau đó chuỗi kết thúc thất bại.
2. Fixed delay cũng ném lỗi ở lượt thứ hai, cho thấy đổi kiểu lịch không tránh quy tắc đó.
3. Một chuỗi bắt riêng một lỗi mô phỏng được dự kiến ở lượt đầu, tiếp tục tới lượt thứ ba rồi được main hủy.

Tác vụ một lần chạy sau hai chuỗi thất bại xác nhận scheduler vẫn phục vụ việc khác. Latch ở lượt ba làm số đếm cuối ổn định; không đợi bằng một khoảng sleep rồi đoán số tick đã chạy.

Lưu thành `PeriodicExceptionDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicExceptionDemo {
    static final class SampleTransientFailure extends RuntimeException {
        SampleTransientFailure(String message) {
            super(message);
        }
    }

    private static void failingSeries(
            ScheduledThreadPoolExecutor scheduler,
            String label, boolean fixedRate) throws Exception {
        AtomicInteger calls = new AtomicInteger();
        Runnable work = () -> {
            if (calls.incrementAndGet() == 2) {
                throw new IllegalStateException("failure on second run");
            }
        };

        ScheduledFuture<?> handle = fixedRate
                ? scheduler.scheduleAtFixedRate(
                        work, 0, 10, TimeUnit.MILLISECONDS)
                : scheduler.scheduleWithFixedDelay(
                        work, 0, 10, TimeUnit.MILLISECONDS);
        try {
            handle.get(10, TimeUnit.SECONDS);
            throw new AssertionError("Expected ExecutionException");
        } catch (ExecutionException ex) {
            System.out.println(label + " runs: " + calls.get());
            System.out.println(label + " cause: "
                    + ex.getCause().getClass().getSimpleName());
            System.out.println(label + " done: " + handle.isDone());
            System.out.println(label + " cancelled: " + handle.isCancelled());
        } finally {
            handle.cancel(true);
        }
    }

    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
        AtomicInteger recoveredCalls = new AtomicInteger();
        AtomicInteger handledFailures = new AtomicInteger();
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch releaseThird = new CountDownLatch(1);
        ScheduledFuture<?> recovered = null;

        try {
            failingSeries(scheduler, "fixed rate", true);
            failingSeries(scheduler, "fixed delay", false);
            ScheduledFuture<String> probe = scheduler.schedule(
                    () -> "available", 0, TimeUnit.MILLISECONDS);
            System.out.println("scheduler after failures: "
                    + probe.get(10, TimeUnit.SECONDS));

            Runnable recoverableWork = () -> {
                int call = recoveredCalls.incrementAndGet();
                try {
                    if (call == 1) {
                        throw new SampleTransientFailure("temporary sample");
                    }
                } catch (SampleTransientFailure ex) {
                    handledFailures.incrementAndGet();
                }

                if (call == 3) {
                    thirdStarted.countDown();
                    try {
                        releaseThird.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("Task interrupted", ex);
                    }
                }
            };
            recovered = scheduler.scheduleAtFixedRate(
                    recoverableWork, 0, 10, TimeUnit.MILLISECONDS);
            if (!thirdStarted.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Recovered series did not reach run 3");
            }
            recovered.cancel(false);
            releaseThird.countDown();

            scheduler.shutdown();
            if (!scheduler.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Scheduler did not terminate");
            }
            System.out.println("recovered runs: " + recoveredCalls.get());
            System.out.println("handled expected failures: "
                    + handledFailures.get());
            System.out.println("recovered cancelled: " + recovered.isCancelled());
        } finally {
            if (recovered != null) {
                recovered.cancel(true);
            }
            releaseThird.countDown();
            scheduler.shutdownNow();
            try {
                if (!scheduler.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Cleanup did not terminate");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 PeriodicExceptionDemo.java
java PeriodicExceptionDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
fixed rate runs: 2
fixed rate cause: IllegalStateException
fixed rate done: true
fixed rate cancelled: false
fixed delay runs: 2
fixed delay cause: IllegalStateException
fixed delay done: true
fixed delay cancelled: false
scheduler after failures: available
recovered runs: 3
handled expected failures: 1
recovered cancelled: true
```

### Đọc kết quả theo nguyên nhân

Hai Future đầu done vì thất bại, không phải vì bị hủy. `cancel(true)` trong finally không đổi một Future đã kết thúc thất bại thành một kết quả thành công; đoạn đó chỉ bảo đảm thí nghiệm có đường dừng nếu lỗi khác làm rời phương thức sớm.

Probe trả `available`, cho thấy scheduler một luồng vẫn nhận và xử lý việc mới. Không cần dựa vào tên luồng hoặc đoán luồng đã được thay chưa để chứng minh điều này.

Chuỗi thứ ba bắt đúng lỗi mô phỏng đã được ứng dụng phân loại, nên lượt đầu vẫn kết thúc bình thường từ góc nhìn scheduler và chuỗi tiếp tục. Nó dừng vì main chủ động cancel ở lượt thứ ba, không phải lỗi mô phỏng đầu tiên.

## 6. Chọn tiếp tục hay dừng là chính sách ứng dụng

Không phải mọi ngoại lệ đều nên làm chuỗi ngừng, và cũng không phải mọi ngoại lệ đều nên bị bắt để tiếp tục. Cần xác định loại lỗi và trạng thái sau lỗi:

| Tình huống | Hướng xử lý cần cân nhắc |
|---|---|
| Một lần đọc nguồn dữ liệu tạm thời thất bại, trạng thái cũ vẫn dùng được | Ghi nhận rõ, có thể cho chuỗi tiếp tục theo chính sách |
| Đầu vào/cấu hình không hợp lệ kéo dài | Báo lỗi, ngừng hoặc chặn tiếp tục cho tới khi sửa |
| Công việc đã cập nhật một phần rồi lỗi | Kiểm tra tính nhất quán và đường phục hồi trước khi chạy lượt sau |
| Luồng nhận yêu cầu ngắt do dừng hệ thống | Tôn trọng tín hiệu ngắt và vòng đời, không tự coi như lỗi tạm để lặp tiếp |
| Tài nguyên hoặc runtime gặp lỗi nghiêm trọng | Không che bằng một catch rộng rồi báo hệ thống khỏe |

Một khối catch có chủ đích nên cho biết đã xử lý loại lỗi nào, công việc còn an toàn để chạy tiếp không và lỗi được quan sát ở đâu. Chỉ `printStackTrace()` hoặc bỏ trống catch có thể giúp lịch tiếp tục nhưng chưa tạo một chính sách phục hồi đáng tin.

Ví dụ `SampleTransientFailure` là lỗi mô phỏng để làm rõ đường điều khiển. Nó không có nghĩa mọi `RuntimeException` hoặc mọi lỗi mạng ngoài đời đều là tạm thời và nên lặp tiếp không giới hạn.

## 7. Ghi nhận lỗi mà không tự làm sai ý nghĩa thành công

Nếu Runnable bắt ngoại lệ rồi trả bình thường, periodic Future không tự cho biết lượt đó thất bại nghiệp vụ. Cần một kênh quan sát cho từng lượt, chẳng hạn bộ đếm lỗi, lần thành công cuối, mã nguyên nhân và trạng thái phục hồi.

Phân biệt các đại lượng:

- Lần tác vụ được gọi gần nhất.
- Lần nghiệp vụ thành công gần nhất.
- Số lỗi liên tiếp và thời gian lỗi bắt đầu.
- Trạng thái chuỗi: còn đăng ký, kết thúc thất bại, bị hủy hoặc scheduler đã dừng.

Một công việc có thể vẫn tick mỗi giây nhưng thất bại mọi lượt. “Có log bắt đầu” không đồng nghĩa hệ thống đang cập nhật thành công. Ngược lại, không có tick có thể do công việc đang bị chặn lâu chứ chưa chắc Future đã thất bại.

Ghi log cần giữ nguyên nhân hữu ích, đồng thời tránh lặp vô hạn một thông báo giống nhau ở nhịp cao. Gộp/chặn tần suất log là chính sách quan sát; không được làm mất trạng thái lỗi hoặc che việc chuỗi không còn tiến triển.

## 8. Phục hồi sau lỗi phải xét nhịp và tác dụng phụ

Nếu một chuỗi fixed rate có nhiều mốc trễ, sau một pha chậm hoặc một lỗi được bắt, các lượt sau có thể chạy gần nhau. Một catch rồi cho tiếp tục không tự thêm backoff. Với fixed delay, có một khoảng nghỉ sau lượt trước hoàn tất, nhưng đó cũng không phải một chính sách thử lại tăng dần theo lỗi.

Nếu cần backoff, số lần thử tối đa hoặc tạm ngừng khi phụ thuộc không phục hồi, phải mô tả chúng riêng. Có thể dùng một cách điều phối lập lịch lại theo trạng thái, nhưng phải tránh tạo nhiều đăng ký trùng nhau khi các đường phục hồi cùng chạy.

Khi một lượt có tác dụng phụ, thử lại hoặc chạy lượt sau không nhất thiết an toàn. Chẳng hạn dữ liệu đã ghi nhưng thông báo chưa gửi; hủy/ngoại lệ của Future không hoàn tác bản ghi. Cần giao dịch, nhận dạng xử lý lặp an toàn hoặc bước bù trừ tùy nghiệp vụ.

Nếu đăng ký mới sau khi chuỗi cũ thất bại, giữ nhận dạng và thay tay cầm theo một chính sách sở hữu rõ ràng. Đừng mỗi lần thấy lỗi lại tạo thêm một chuỗi mà quên đăng ký còn sống hoặc hoạt động chuyển tiếp do chuỗi cũ đã tạo.

## 9. Ranh giới lỗi thay đổi nếu chỉ gửi việc sang executor khác

Xét một tick chỉ thực hiện ý tưởng sau:

```text
scheduler tick → gửi công việc nền khác → tick kết thúc bình thường
```

Nếu phần công việc nền thất bại sau đó, ngoại lệ không tự quay ngược thời gian để thoát khỏi Runnable tick đã kết thúc. Chuỗi lịch có thể tiếp tục, dù công việc thật liên tục thất bại. Nếu chính thao tác gửi việc bị từ chối và ngoại lệ thoát khỏi tick, chuỗi lịch lại có thể ngừng.

Vì vậy phải xác định ranh giới một lượt: nó bao gồm thực hiện nghiệp vụ, hay chỉ bao gồm việc phát tín hiệu/gửi yêu cầu? Khi chuyển việc đi, cần giám sát Future/trạng thái bên thực thi, giới hạn lượng việc chưa xong và ngăn chồng tác vụ nếu nghiệp vụ yêu cầu.

Không dùng cách chuyển việc này chỉ để “đảm bảo scheduler không bao giờ dừng” rồi mất hoàn toàn đường quan sát lỗi. Ranh giới rõ giúp chọn chính sách tiếp tục/ngừng đúng phần công việc cần quản lý.

## 10. Các lỗi khác không phải thất bại của một lượt đã chạy

Lời đăng ký có thể thất bại ngay, chẳng hạn period/delay định kỳ không hợp lệ hoặc scheduler không nhận việc. Đó là lỗi tại ranh giới tạo lịch; không có nghĩa một lượt định kỳ đã chạy rồi ném lỗi.

Hủy một ScheduledFuture và shutdown scheduler cũng khác việc tác vụ ném ngoại lệ. Nếu cần giám sát trạng thái, đừng chỉ hỏi isDone rồi gán tất cả trường hợp thành “lỗi chương trình”.

Khi dừng hệ thống, không bắt InterruptedException trong tác vụ rồi tự tiếp tục vô hạn như thể đó là lỗi mạng tạm thời. Giữ cơ chế dọn tài nguyên và cho phép chủ sở hữu kết thúc scheduler. Nếu tác vụ cần đóng tài nguyên mỗi lượt, dùng finally hoặc cơ chế đóng thích hợp dù đang chọn tiếp tục hay ngừng chuỗi.

## 11. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Scheduler sẽ tự chạy tiếp sau mọi exception | Ngoại lệ thoát khỏi lượt có thể ngừng đăng ký định kỳ |
| Đổi fixed rate sang fixed delay sẽ tránh ngừng vì lỗi | Cả hai cùng có quy tắc dừng chuỗi khi lỗi thoát ra |
| Một chuỗi dừng thì cả scheduler đã shutdown | Scheduler có thể tiếp tục phục vụ đăng ký/công việc khác |
| Handler của luồng sẽ thấy mọi lỗi lịch | ScheduledFuture có thể giữ lỗi bên trong |
| Bắt Exception rồi im lặng là phục hồi | Cần phân loại lỗi, trạng thái và đường quan sát |
| isDone phân biệt được hủy với thất bại | Phải quan sát thêm trạng thái/kết quả |
| Tick còn chạy nghĩa nghiệp vụ vẫn thành công | Cần đo lần thành công, lỗi và tiến triển thực |

Tự kiểm tra:

1. Vì sao hai chuỗi đầu trong ví dụ dừng đúng ở lượt 2? **Lượt đó ném lỗi ra khỏi Runnable và Future ghi nhận chuỗi kết thúc thất bại.**
2. Vì sao chuỗi thứ ba vượt qua lượt lỗi đầu tiên? **Runnable đã bắt loại lỗi mô phỏng được dự kiến và kết thúc bình thường theo chính sách.**
3. Probe thành công chứng minh gì? **Scheduler còn phục vụ công việc khác sau khi hai đăng ký thất bại.**
4. Có nên dùng periodicFuture.get không thời hạn để đợi một lượt thành công không? **Không.** Future biểu diễn cả chuỗi, không phải một tick.

Thực hành: đổi lỗi ở lượt thứ hai thành một lỗi không được catch trong chuỗi recoverable và kiểm tra Future kết thúc bằng ExecutionException. Sau đó thiết kế một chính sách cho phép tối đa hai lỗi dự kiến liên tiếp trước khi ngừng, ghi rõ bộ đếm được đặt lại khi nào. Không chỉ thêm catch rộng; hãy giải thích vì sao lượt tiếp theo vẫn an toàn với dữ liệu và tài nguyên của công việc.
