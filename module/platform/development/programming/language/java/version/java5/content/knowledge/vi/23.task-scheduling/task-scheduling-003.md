# scheduleAtFixedRate và chu kỳ tính từ mốc dự kiến

## 1. Fixed rate giữ một dãy mốc, không đợi xong rồi mới cộng chu kỳ

Một công việc định kỳ có thể được mô tả bằng hai ý định khác nhau:

- “Cố chạy theo nhịp mỗi một giây tính từ mốc ban đầu.”
- “Sau khi xong một lượt, nghỉ một giây rồi chạy tiếp.”

`scheduleAtFixedRate` phục vụ ý định đầu. Nó duy trì nhịp dự kiến theo mốc ban đầu, nên thời điểm đến hạn của lượt tiếp theo không được tính lại bằng thời điểm lượt trước vừa kết thúc.

Điều này hữu ích với các công việc lấy mẫu, cập nhật chỉ số hoặc các hoạt động cần nhịp tương đối ổn định. Nhưng fixed rate không phải bảo đảm thời gian thực, cũng không tự giải quyết việc công việc chạy lâu hơn nhịp mong muốn.

API này vẫn áp dụng trong Java hiện nay. Ví dụ trong bài chạy bằng Java 17 trở lên.

## 2. Chữ ký và công thức các mốc đến hạn

```java
ScheduledFuture<?> scheduleAtFixedRate(
        Runnable command,
        long initialDelay,
        long period,
        TimeUnit unit);
```

Đây là chữ ký để đọc hợp đồng; các kiểu lịch và đơn vị thuộc `java.util.concurrent`.

- `command`: phần việc được thực thi ở mỗi lượt.
- `initialDelay`: khoảng chờ trước mốc đầu tiên; dùng 0 khi muốn bắt đầu đủ điều kiện chạy ngay.
- `period`: chu kỳ, phải lớn hơn 0.
- `unit`: đơn vị áp dụng cho cả initialDelay và period.
- Kết quả: một ScheduledFuture theo dõi **cả chuỗi lặp**, không phải kết quả riêng của một lượt.

Gọi `t0` là mốc cơ sở của lần đăng ký, `D` là initialDelay và `P` là period:

```text
Mốc dự kiến của lượt k: d(k) = t0 + D + k × P
với k = 0, 1, 2, ...
```

Ví dụ D = 2 giây, P = 3 giây, các mốc tương đối là 2, 5, 8, 11 giây. Đây là **mốc đến hạn/đủ điều kiện**, không phải lời hứa mọi lượt bắt đầu đúng tới mili giây. [ScheduledExecutorService.scheduleAtFixedRate](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html#scheduleAtFixedRate(java.lang.Runnable,long,long,java.util.concurrent.TimeUnit)).

Trong mã minh họa bên trong một phương thức đã có scheduler:

```java
ScheduledFuture<?> handle = scheduler.scheduleAtFixedRate(
        () -> System.out.println("sample"),
        2, 3, TimeUnit.SECONDS);
```

In log trong ví dụ chỉ để minh họa đăng ký; không dùng thời gian log làm phép đo chính xác của lịch trong ứng dụng thực tế.

## 3. Thời gian chạy tác vụ ảnh hưởng nhịp thực tế thế nào?

### Khi mỗi lượt ngắn hơn chu kỳ

Giả định không có trễ đáng kể, chu kỳ 100 ms, mỗi lượt chiếm khoảng 30 ms:

```text
Mốc dự kiến:   0       100       200       300 ms
Lượt chạy:    [30]     [30]      [30]      [30]
```

Sau khi một lượt xong, phần thời gian còn lại đến mốc dự kiến tiếp theo có thể trở thành thời gian nghỉ. Không cộng lại 100 ms từ lúc xong.

### Khi một lượt chạy lâu hơn chu kỳ

Giả định mốc đầu là 0, period = 100 ms, lượt đầu chiếm 250 ms:

| Lượt | Mốc dự kiến | Tình huống sau lượt đầu dài |
|---|---:|---|
| 1 | 0 ms | Đang chạy đến khoảng 250 ms |
| 2 | 100 ms | Đã trễ; chưa thể chạy chồng lên lượt 1 |
| 3 | 200 ms | Cũng đã đến hạn |
| 4 | 300 ms | Vẫn theo dãy mốc ban đầu |

Trong ScheduledThreadPoolExecutor chuẩn, mốc của tác vụ fixed rate được tiến bằng cách cộng period cho mỗi lượt. Khi mốc kế tiếp đã ở quá khứ, lượt đó có thể được chạy tiếp sớm khi có luồng, rồi tiếp tục xét mốc sau. Vì thế các lượt có thể chạy sát nhau để đuổi nhịp; không mặc định tự bỏ các lượt trễ để nhảy thẳng đến giờ hiện tại. Đây là diễn giải từ [mã nguồn ScheduledThreadPoolExecutor](https://raw.githubusercontent.com/openjdk/jdk/jdk-25-ga/src/java.base/share/classes/java/util/concurrent/ScheduledThreadPoolExecutor.java).

Nếu mọi lượt đều mất 250 ms trong khi period là 100 ms, một chuỗi không thể đạt nhịp thực tế 100 ms bằng việc tự chạy chồng. Nó có thể tiếp tục trễ so với mốc dự kiến và ít có khoảng nghỉ. Cần xử lý năng lực công việc hoặc thay chính sách lịch theo mục tiêu, không chỉ giảm period.

## 4. Không chồng lượt của cùng một đăng ký

Các lượt của cùng một tác vụ định kỳ đăng ký qua scheduleAtFixedRate không chạy đồng thời với nhau. Với ScheduledThreadPoolExecutor, hiệu ứng của lượt trước còn có quan hệ happens-before với lượt kế tiếp, dù các lượt có thể dùng những luồng khác nhau. [ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

Phạm vi bảo đảm cần được giữ đúng:

- Hai đăng ký riêng, kể cả cùng giữ một đối tượng Runnable, không tự trở thành một chuỗi được khóa chung.
- Một lượt chỉ gửi công việc sang executor khác rồi trả về đã kết thúc phần Runnable được lịch theo dõi. Các công việc chuyển tiếp có thể chồng lên nhau nếu không có giới hạn riêng.
- Thêm luồng cho scheduler giúp các đăng ký khác có cơ hội chạy, nhưng không làm các lượt của cùng một đăng ký tự chạy song song.

Vì vậy, nếu nghiệp vụ yêu cầu một tiến trình cập nhật không bao giờ chồng lấn, phải đặt ranh giới “một lượt đã xong” bao gồm phần việc thật sự cần bảo vệ, không chỉ phần gửi lệnh.

## 5. Chương trình kiểm chứng không phụ thuộc timestamp cố định

Ví dụ dùng scheduler hai luồng. Lượt đầu bị giữ ở latch; trong khi đó một tác vụ một lần ở cùng scheduler xác nhận đã trôi qua đủ một khoảng để nhiều mốc chu kỳ 20 ms trở thành quá hạn. Sau khi mở lượt đầu, chương trình cho chuỗi tiến tới lượt thứ ba rồi giữ nó lại để hủy an toàn.

Không in các thời điểm bắt đầu chính xác vì lịch của hệ điều hành không cố định. Thí nghiệm kiểm chứng các tính chất: chuỗi vẫn tiến triển, không chồng lượt, và hủy đăng ký dừng việc lặp tiếp.

Lưu thành `FixedRateDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedRateDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(2);
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch releaseThird = new CountDownLatch(1);
        AtomicInteger calls = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();
        ScheduledFuture<?> periodic = null;

        Runnable work = () -> {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            int call = calls.incrementAndGet();
            try {
                if (call == 1) {
                    firstStarted.countDown();
                    releaseFirst.await();
                } else if (call == 3) {
                    thirdStarted.countDown();
                    releaseThird.await();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Periodic task interrupted", ex);
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            periodic = scheduler.scheduleAtFixedRate(
                    work, 0, 20, TimeUnit.MILLISECONDS);
            awaitSignal(firstStarted);

            ScheduledFuture<?> marker = scheduler.schedule(
                    () -> { }, 100, TimeUnit.MILLISECONDS);
            marker.get(10, TimeUnit.SECONDS);
            System.out.println("calls while first is blocked: " + calls.get());

            releaseFirst.countDown();
            awaitSignal(thirdStarted);
            boolean accepted = periodic.cancel(false);
            releaseThird.countDown();

            scheduler.shutdown();
            if (!scheduler.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Scheduler did not terminate");
            }

            System.out.println("calls after stopping: " + calls.get());
            System.out.println("peak active for registration: " + peak.get());
            System.out.println("cancel accepted: " + accepted);
            System.out.println("periodic cancelled: " + periodic.isCancelled());
            try {
                periodic.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException ex) {
                System.out.println("periodic get: cancelled");
            }
        } finally {
            if (periodic != null) {
                periodic.cancel(true);
            }
            releaseFirst.countDown();
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

    private static void awaitSignal(CountDownLatch latch)
            throws InterruptedException {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new AssertionError("Expected task phase did not start");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 FixedRateDemo.java
java FixedRateDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
calls while first is blocked: 1
calls after stopping: 3
peak active for registration: 1
cancel accepted: true
periodic cancelled: true
periodic get: cancelled
```

### Đọc các điểm kiểm chứng

Scheduler có hai luồng nhưng trong lúc lượt đầu bị giữ, chuỗi định kỳ vẫn chỉ có một lượt đang diễn ra. Luồng còn lại chạy marker sau khoảng chờ đã cấu hình; marker không làm cùng chuỗi định kỳ chạy chồng lên lượt đầu.

Lượt thứ ba bị giữ trước khi main hủy, nên không có cuộc đua khiến thí nghiệm đôi khi chạy thêm lượt thứ tư. `cancel(false)` không ngắt thân lượt thứ ba đang chờ; mở latch cho nó thoát và chờ scheduler kết thúc giúp kiểm chứng số đếm cuối.

Thí nghiệm không khẳng định lượt hai bắt đầu ở chính xác 100 hoặc 101 ms. Công thức mốc dự kiến được xác định bởi hợp đồng fixed rate; các ranh giới điều khiển trong mã dùng để kiểm tra tính không chồng và vòng đời.

## 6. So sánh vừa đủ với fixed delay

Với fixed rate, các mốc giữ theo mốc cơ sở:

```text
d(k+1) = d(k) + period
```

Với fixed delay, ý định là có một khoảng nghỉ sau khi lượt trước kết thúc:

```text
mốc lượt sau = thời điểm hoàn thành lượt trước + delay
```

Nếu một lượt mất 70 ms và cấu hình khoảng 100 ms, fixed rate hướng tới các mốc 0, 100, 200... trong điều kiện bình thường; fixed delay hướng tới nghỉ thêm 100 ms sau mỗi lần xong. Chọn theo ý nghĩa nghiệp vụ, không theo tên “fixed” chung chung.

Fixed rate hợp với một nhịp dự kiến; fixed delay hợp khi muốn tạo khoảng nghỉ sau mỗi lượt, chẳng hạn giảm áp lực polling sau một lần xử lý dài. Cả hai vẫn cần xử lý lỗi, tài nguyên và việc dừng.

## 7. Lỗi của một lượt có thể dừng cả chuỗi

Nếu một lượt ném ngoại lệ ra khỏi Runnable, các lượt sau của đăng ký định kỳ bị ngừng. ScheduledFuture chuyển sang trạng thái kết thúc bất thường; get báo ExecutionException giữ nguyên nhân. Không nên kết luận scheduler đã hỏng chỉ vì không còn thấy lượt chạy tiếp.

Khi chuỗi còn hoạt động bình thường, `periodicFuture.get()` không phải cách chờ một tick; Future đó đại diện toàn bộ chuỗi và không trả kết quả bình thường như một phép tính một lần. Khi hủy, get báo CancellationException; khi lỗi làm chuỗi dừng, nó báo thất bại theo Future.

Cần giữ handle và có cơ chế quan sát tình trạng chuỗi. Nếu có lỗi dự kiến mà nghiệp vụ cho phép tiếp tục, tác vụ có thể xử lý lỗi đó có chủ đích và ghi nhận, nhưng không bắt mọi Throwable rồi lặp im lặng. Một lỗi vĩnh viễn có thể biến thành vòng gọi thất bại nhanh liên tục ở nhịp cố định.

Nếu cần thử lại với khoảng chờ tăng dần hoặc dừng sau một số lần thất bại, hãy thiết kế chính sách đó rõ ràng thay vì kỳ vọng scheduleAtFixedRate tự cung cấp backoff.

## 8. Trễ lịch cần đo bằng đúng đại lượng

Ba loại thời gian giúp chẩn đoán:

| Đại lượng | Câu hỏi |
|---|---|
| Độ trễ so với mốc dự kiến | Lượt bắt đầu muộn hơn lịch bao nhiêu? |
| Thời lượng thực thi một lượt | Phần việc chiếm luồng bao lâu? |
| Khoảng cách bắt đầu thực tế giữa các lượt | Nhịp người dùng quan sát được có phù hợp không? |

Đừng chỉ lấy hiệu hai timestamp bắt đầu rồi kết luận period bị thay đổi. Một chuỗi có thể đang đuổi các mốc trễ hoặc tranh luồng với tác vụ khác. Đo các khoảng thời gian trong cùng tiến trình bằng đồng hồ đơn điệu phù hợp; thời điểm lịch theo ngày/giờ là một vấn đề khác.

ScheduledThreadPoolExecutor không bảo đảm một tác vụ đến hạn sẽ được CPU thực thi ngay. GC, luồng bận, khóa, I/O, số đăng ký và tải tiến trình có thể làm trễ. Tăng maximumPoolSize không có tác dụng như với một ThreadPoolExecutor hàng đợi hữu hạn thông thường; scheduler này hoạt động chủ yếu theo corePoolSize và hàng đợi lịch không giới hạn.

## 9. Tránh biến đuổi nhịp thành tăng áp lực

Nếu mỗi lượt phải gọi một dịch vụ đang chậm, các mốc trễ có thể khiến chuỗi ít nghỉ sau khi công việc trước xong. Nếu nhiều đăng ký cùng như vậy, áp lực dịch vụ phía sau có thể tăng thay vì được giảm.

Cần chọn chính sách cho công việc quá hạn:

- Mọi lượt có phải là một công việc phải làm đủ, hay chỉ cần dữ liệu mới nhất?
- Một lượt trễ có còn giá trị, hay nên bỏ qua theo quy tắc nghiệp vụ riêng?
- Có thể gộp nhiều nhu cầu cập nhật thành một công việc không?
- Khi dịch vụ phía sau chậm, cần giảm nhịp, backoff hay tạm ngừng theo điều kiện nào?

scheduleAtFixedRate tự nó không phải một hàng đợi công việc bền vững hoặc hệ thống xử lý mọi tick đúng một lần. Nếu yêu cầu ghi nhận mỗi kỳ phải được thực hiện kể cả khi tiến trình dừng, cần thêm lưu trữ và cơ chế điều phối phù hợp. Nếu chỉ cần ảnh chụp mới nhất, một chính sách gộp/bỏ qua có chủ đích có thể phù hợp hơn cố làm đủ mọi mốc đã cũ.

Không tự đẩy công việc sang một executor không giới hạn để “giữ scheduler luôn nhanh”: khi đó bảo đảm không chồng của Runnable lịch không còn bảo vệ phần việc thực được gửi đi. Cần giới hạn đồng thời và theo dõi hoàn thành ở ranh giới mới.

## 10. Dừng đăng ký và dừng scheduler là hai quyết định

Giữ ScheduledFuture để hủy một đăng ký khi không còn dùng. `cancel(false)` ngăn các lượt tiếp theo mà không yêu cầu ngắt lượt đang chạy; `cancel(true)` cho phép cố ngắt khi triển khai hỗ trợ, tác vụ vẫn cần hợp tác.

Trong ScheduledThreadPoolExecutor, có chính sách điều khiển việc tiếp tục các tác vụ định kỳ sau shutdown; mặc định không tiếp tục chuỗi định kỳ đó. Ví dụ đặt chính sách false tường minh và chủ động cancel handle. Việc shutdown/awaitTermination vẫn thuộc chủ sở hữu scheduler, không phải mỗi người dùng một đăng ký đều được quyền dừng scheduler dùng chung.

`setRemoveOnCancelPolicy(true)` giúp lấy công việc bị hủy ra khỏi hàng đợi ngay thay vì giữ tới khi hết delay. Đây là lựa chọn quản lý phần tử lịch bị hủy; nó không làm hủy có nghĩa hoàn tác tác dụng phụ đã xảy ra.

Các khoảng chờ/chu kỳ của API là thời gian tương đối, không phải biểu thức “mỗi ngày lúc 08:00” theo múi giờ. Đừng tự diễn giải fixed rate 24 giờ là lịch giờ địa phương luôn đúng qua mọi thay đổi giờ hoặc điều chỉnh lịch; yêu cầu theo ngày/giờ cần mô hình lịch tương ứng.

## 11. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Fixed rate là xong rồi nghỉ thêm period | Mốc tiếp theo dựa trên dãy mốc dự kiến |
| Lượt chạy lâu sẽ tự sinh các lượt song song để bù | Cùng đăng ký không chồng lượt |
| Lượt trễ luôn bị bỏ tự động | Triển khai chuẩn tiến mốc từng period; không tự coi như cơ chế bỏ tick cũ |
| Tăng scheduler lên hai luồng làm cùng chuỗi chạy gấp đôi | Giúp nhiều công việc khác cùng phục vụ, không bỏ bảo đảm không chồng của một chuỗi |
| Get trên periodic Future trả sau tick đầu | Future đại diện cả chuỗi, không phải từng tick |
| Chuỗi im lặng nghĩa scheduler chết | Có thể một lượt đã ném lỗi khiến chuỗi ngừng |
| Cancel đồng nghĩa mọi tác dụng phụ đã dừng | Cần xét lượt đang chạy và cơ chế hủy hợp tác |

Tự kiểm tra:

1. D = 1 giây, P = 2 giây, bốn mốc đầu là gì? **1, 3, 5, 7 giây tính từ mốc cơ sở.**
2. Lượt trước chưa xong khi lượt sau đến hạn thì cùng chuỗi có chạy chồng không? **Không.** Lượt sau có thể bắt đầu trễ.
3. Vì sao thí nghiệm dùng scheduler hai luồng? **Để marker có thể chạy trong lúc lượt đầu của chuỗi đang bị giữ.**
4. Vì sao giữ lượt ba ở latch trước khi cancel? **Để chặn cuộc đua chạy thêm lượt, giúp số đếm cuối có cơ sở.**

Thực hành: thay API bằng scheduleWithFixedDelay với cùng khoảng 20 ms và giữ các ranh giới dọn dẹp. Dự đoán cách tính mốc tiếp theo sau lúc mở lượt đầu khác ở đâu. Nếu muốn đo thực tế, thu timestamp thay vì yêu cầu một bảng mili giây chính xác bất biến; so sánh mô hình và chấp nhận biến động lập lịch trong giới hạn đã xác định.
