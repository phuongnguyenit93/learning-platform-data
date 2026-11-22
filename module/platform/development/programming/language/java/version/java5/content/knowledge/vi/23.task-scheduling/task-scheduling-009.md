# Giới hạn chính xác của lịch chạy và hệ điều hành

## 1. Đến hạn không đồng nghĩa bắt đầu đúng ngay thời điểm đó

Khi viết `schedule(task, 100, MILLISECONDS)`, ta yêu cầu công việc trở thành đủ điều kiện thực thi sau một khoảng chờ. Không thể từ đó suy ra hệ điều hành chắc chắn cho luồng chạy đúng tại mốc 100 mili giây, hoặc công việc chắc chắn hoàn thành trong 100 mili giây.

Cần phân biệt ba mốc:

```text
đăng ký lịch → đến hạn → thực sự bắt đầu → thực sự hoàn thành
```

Lịch quản lý mốc đến hạn và thứ tự xét công việc theo hợp đồng. Mốc bắt đầu còn phụ thuộc luồng, CPU, khóa và môi trường. Mốc hoàn thành còn phụ thuộc phần việc và các tài nguyên nó sử dụng.

Với ScheduledThreadPoolExecutor, tác vụ chờ không chạy sớm hơn khi nó đủ điều kiện, nhưng không có bảo đảm thời gian thực về lúc nó sẽ bắt đầu sau đó. [ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

Bài nói về các API Java chuẩn đang áp dụng hiện nay, không gắn một giá trị độ phân giải cố định cho mọi hệ điều hành hoặc mọi JVM. Ví dụ chính tương thích Java 17 trở lên.

## 2. Đơn vị nhỏ không tự tạo độ chính xác tương ứng

Một phương thức nhận `TimeUnit.NANOSECONDS` không có nghĩa công việc sẽ được bắt đầu với sai số tối đa một nano giây.

| Khái niệm | Ý nghĩa | Điều không nên suy ra |
|---|---|---|
| Đơn vị biểu diễn | Một con số được diễn đạt bằng ms, µs hay ns | Đơn vị ns không chứng minh lịch đạt độ chính xác ns |
| Độ phân giải đồng hồ | Khoảng thay đổi nhỏ mà nguồn thời gian có thể thể hiện | Không tự là giới hạn trễ đánh thức luồng |
| Độ chính xác phép đo | Mức phù hợp của phép đo với khoảng thời gian cần biết | Không tự cung cấp CPU đúng lúc |
| Độ trễ bắt đầu | Khoảng từ mốc đến hạn đến khi phần việc thật bắt đầu | Không bằng thời lượng task.run |
| Độ trễ biến động (jitter) | Sự thay đổi của thời điểm/độ trễ qua nhiều lượt | Không thể kết luận từ một mẫu trung bình |
| Hạn chót hoàn thành | Thời điểm nghiệp vụ cần công việc xong | Không được bảo đảm chỉ bằng delay đăng ký |

`System.nanoTime()` trả giá trị theo nano giây nhưng tài liệu không bảo đảm độ phân giải nano giây. Nó dùng để đo khoảng thời gian trôi trong cùng JVM, không phải timestamp ngày giờ. [System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime()).

Đừng dùng việc in nhiều chữ số sau dấu thập phân làm bằng chứng phép đo hoặc lịch chạy chính xác tới những chữ số đó.

## 3. Những tầng có thể làm công việc bắt đầu trễ

Một tác vụ đủ điều kiện vẫn phải đi qua các tài nguyên hữu hạn:

```text
đã đến hạn trong hàng đợi lịch
    → có luồng scheduler rảnh?
    → luồng có được cấp CPU?
    → có bị chặn bởi khóa hoặc thao tác chuẩn bị?
    → phần việc bắt đầu
```

Các nguyên nhân cần xem xét gồm:

- Luồng scheduler đang chạy một tác vụ dài, chờ I/O hoặc chờ khóa.
- CPU bị nhiều luồng/tiến trình cạnh tranh, hoặc ngân sách CPU của môi trường triển khai bị hạn chế.
- Một số giai đoạn của JVM hoặc hoạt động bộ nhớ làm các luồng không tiến triển liên tục.
- Hệ điều hành đánh thức và lập lịch luồng với độ trễ biến động.
- Máy ảo, môi trường chia sẻ hoặc hệ thống tiết kiệm năng lượng có những đặc tính ảnh hưởng thời điểm tiến triển.
- Phần đầu tác vụ tự tạo độ trễ bằng log, lấy khóa, cấp phát hoặc gọi dịch vụ khác.

Không quy mọi độ trễ cho “timer của hệ điều hành quá thô”. Một scheduler chỉ có một luồng đang bị giữ ở một lời đọc mạng có thể trễ dù nguồn thời gian rất tốt.

Cũng không suy một con số cố định như “mọi lịch Java chỉ chính xác tới X ms” từ trải nghiệm một máy. Nó phụ thuộc nền tảng, JVM, tải và cách đo; API chuẩn không cam kết một biên trễ thời gian thực chung như vậy.

## 4. Ví dụ đầy đủ: đến hạn nhưng luồng vẫn chưa rảnh

Thí nghiệm dùng hai scheduler riêng:

- Scheduler công việc chỉ có một luồng, bị một công việc đầu giữ ở latch.
- Scheduler quan sát chạy một marker sau 100 ms, để main có một điểm kiểm chứng trong khi luồng công việc vẫn bị giữ.

Một tác vụ khác được hẹn sau 20 ms trên scheduler công việc. Dù đã qua mốc chờ của nó, nó chưa chạy được vì không còn luồng rảnh. Sau khi main mở latch, tác vụ mới bắt đầu.

Lưu thành `SchedulingLimitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;

public class SchedulingLimitDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor worker =
                new ScheduledThreadPoolExecutor(1);
        ScheduledThreadPoolExecutor observer =
                new ScheduledThreadPoolExecutor(1);
        CountDownLatch blockerStarted = new CountDownLatch(1);
        CountDownLatch releaseBlocker = new CountDownLatch(1);
        AtomicLong observedDelay = new AtomicLong();
        long requestedDelayNanos = TimeUnit.MILLISECONDS.toNanos(20);

        try {
            Future<?> blocker = worker.submit(() -> {
                blockerStarted.countDown();
                try {
                    releaseBlocker.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("Blocker interrupted", ex);
                }
            });
            if (!blockerStarted.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Blocker did not start");
            }

            long registeredAt = System.nanoTime();
            ScheduledFuture<Integer> target = worker.schedule(() -> {
                observedDelay.set(System.nanoTime() - registeredAt);
                return 42;
            }, 20, TimeUnit.MILLISECONDS);

            ScheduledFuture<?> marker = observer.schedule(
                    () -> { }, 100, TimeUnit.MILLISECONDS);
            marker.get(10, TimeUnit.SECONDS);
            System.out.println("target done while worker occupied: "
                    + target.isDone());

            releaseBlocker.countDown();
            blocker.get(10, TimeUnit.SECONDS);
            System.out.println("target result: "
                    + target.get(10, TimeUnit.SECONDS));
            System.out.println("observed delay exceeded request: "
                    + (observedDelay.get() > requestedDelayNanos));
        } finally {
            releaseBlocker.countDown();
            worker.shutdownNow();
            observer.shutdownNow();
            try {
                boolean workerStopped = worker.awaitTermination(
                        10, TimeUnit.SECONDS);
                boolean observerStopped = observer.awaitTermination(
                        10, TimeUnit.SECONDS);
                if (!workerStopped || !observerStopped) {
                    throw new IllegalStateException("Schedulers did not terminate");
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
javac --release 17 SchedulingLimitDemo.java
java SchedulingLimitDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
target done while worker occupied: false
target result: 42
observed delay exceeded request: true
```

### Thí nghiệm chứng minh gì?

Trong lúc worker bị giữ, target không có cơ hội chạy. Marker ở scheduler độc lập không giải phóng luồng worker; nó chỉ tạo một điểm quan sát sau một khoảng chờ lớn hơn delay của target. Khi mở latch, target mới tiến triển và trả kết quả.

Không in một giá trị như “target chắc chắn chạy sau đúng 100 ms”. Observer cũng chịu tác động lập lịch, nên marker có thể đến muộn. Mốc `registeredAt` ở phía ứng dụng còn bao gồm phần chi phí gọi đăng ký; phép đo là độ trễ quan sát từ trước lời schedule đến đầu Callable, không phải đọc trực tiếp thời điểm nội bộ của scheduler.

Ví dụ cho thấy rõ một nguồn gây trễ là luồng bận. Nó không đo biên trễ lớn nhất của hệ điều hành hoặc chứng minh một cam kết thời gian thực trên máy đó.

## 5. Sleep cũng không bảo đảm thức dậy và chạy đúng mốc

`Thread.sleep` làm luồng tạm ngừng thực thi, nhưng thời gian thực tế còn phụ thuộc độ chính xác/độ phân giải của timer và scheduler hệ thống. Hết thời gian ngủ không đồng nghĩa CPU lập tức chạy câu lệnh tiếp theo. [Thread.sleep](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#sleep(long)).

Vì vậy, một vòng kiểu:

```text
làm công việc → sleep(100 ms) → làm công việc tiếp
```

có khoảng giữa hai lần bắt đầu bao gồm cả thời gian công việc, thời gian ngủ và trễ đánh thức. Nó không tự tương đương scheduleAtFixedRate 100 ms.

Không thay sleep bằng vòng lặp bận đọc nanoTime rồi mặc định sẽ có bảo đảm thời gian thực. Nó có thể tiêu tốn CPU, tăng cạnh tranh và làm các phần việc khác trễ hơn, trong khi luồng vẫn có thể bị hệ điều hành hoặc JVM tạm ngừng. Nếu một cơ chế quay chờ có mục đích chuyên biệt, cần đo và phân tích ở cấp hệ thống; không dùng làm sửa chữa mặc định cho lịch ứng dụng.

Độ ưu tiên luồng cũng không phải công cụ bảo đảm hạn chót. Đặt ưu tiên cao không làm biến mất GC, khóa, I/O hoặc giới hạn tài nguyên và không bảo đảm mọi nền tảng cho thứ tự như người viết mong muốn.

## 6. Thời gian tương đối khác giờ trên lịch

Các phương thức ScheduledExecutorService nhận delay và period tương đối, không nhận trực tiếp một lịch ngày/giờ theo múi giờ. [ScheduledExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).

Cần phân biệt hai mục tiêu:

| Mục tiêu | Mô hình thời gian cần suy nghĩ |
|---|---|
| Chạy sau khoảng 5 giây | Khoảng thời gian trôi |
| Lấy mẫu theo nhịp mỗi 100 ms | Dãy mốc tương đối và chính sách khi trễ |
| Chạy mỗi ngày lúc 08:00 theo một múi giờ | Lịch ngày/giờ, múi giờ và thay đổi lịch |
| Hết hạn một yêu cầu sau 2 giây | Hạn chót đầu-cuối và ngân sách còn lại |

Dùng `Instant.now()` hoặc đồng hồ lịch để gắn thời điểm có nghĩa với người dùng/log. Dùng nanoTime để đo khoảng thời gian trong cùng JVM. Không trừ nanoTime của hai tiến trình/máy, không biến nanoTime thành một thời điểm UTC, và không lưu mốc nanoTime để khôi phục lịch sau khi JVM khởi động lại.

Nếu tính một delay từ một thời điểm lịch rồi gọi schedule, đó là quyết định dựa trên quan hệ đồng hồ ở thời điểm tính. Không mặc định mọi điều chỉnh đồng hồ hoặc lịch địa phương về sau đều tự được phản ánh đúng ý định “chạy theo giờ lịch” ban đầu.

## 7. Đo độ trễ và jitter mà không tự làm sai kết quả

Một bộ đo có ý nghĩa nên định nghĩa:

```text
mốc dự kiến                  d
thời điểm bắt đầu quan sát    s
thời điểm hoàn thành          f

trễ bắt đầu  = s - d
thời lượng   = f - s
trễ hoàn tất = f - hạn chót hoàn thành, nếu có hạn chót
```

Với fixed rate, mốc dự kiến cần giữ theo dãy ban đầu. Nếu cứ lấy “lần bắt đầu trước + period” làm chuẩn mới, một phần lệch tích lũy có thể bị che. Với fixed delay, mốc lại có quan hệ với lúc kết thúc lượt trước; không dùng cùng một phép diễn giải cho hai ý định khác nhau.

Các lưu ý khi đo:

- Thu nhiều mẫu dưới tải đại diện và quan sát phân vị/đỉnh, không chỉ trung bình.
- Tách chi phí quan sát như log đồng bộ hoặc ghi đĩa ra khỏi phần đo nếu mục tiêu không bao gồm chi phí đó.
- Nhận diện thời gian khởi động, nạp lớp và giai đoạn hệ thống chưa ổn định.
- Ghi cùng bối cảnh CPU, số lịch đang hoạt động và độ trễ phụ thuộc.
- Giữ đơn vị và quy tắc làm tròn rõ; chuyển về mili giây nguyên có thể làm mất chi tiết nhỏ hoặc cho vẻ ngoài “đúng 0 ms”.

Một lần không trễ không tạo ra bảo đảm không bao giờ trễ. Một lần trễ rất lớn cũng cần bối cảnh trước khi quy lỗi cho API. Đo giúp hiểu phân bố hành vi của cấu hình/môi trường đã thử, còn hợp đồng API xác định những điều có thể dựa vào khi viết mã.

## 8. Chọn cửa sổ chấp nhận thay vì kiểm tra bằng timestamp bằng nhau

Một yêu cầu thực tế nên nói rõ dung sai, chẳng hạn công việc phải bắt đầu trong một cửa sổ cho phép và phần lớn lượt đáp ứng một mục tiêu độ trễ. Cần đồng thời xác định điều gì xảy ra khi lệch cửa sổ: bỏ lượt, gộp việc, chạy trễ, báo lỗi hay thử lại.

Không viết kiểm tra kiểu “delay 100 ms thì elapsed phải bằng đúng 100 ms”. Cũng không dùng một ngưỡng trên quá sát làm bài kiểm tra phụ thuộc tải máy CI. Khi kiểm chứng thứ tự/trạng thái, ưu tiên latch và điều kiện có thể quan sát; dùng một timeout rộng hơn chỉ để phát hiện không tiến triển.

Ví dụ trong bài không chấm lịch bằng equality của timestamp. Nó kiểm chứng sự phụ thuộc tài nguyên: còn một công việc giữ luồng thì tác vụ khác chưa chạy, sau khi giải phóng thì có kết quả.

Nếu yêu cầu có hạn chót cứng mà vi phạm có hậu quả quan trọng, không suy rằng chỉ cần ScheduledThreadPoolExecutor là đủ. Phải đánh giá cả runtime, hệ điều hành, phần cứng, phụ thuộc và cơ chế khi vi phạm hạn chót. API Java chuẩn này tự nó không đưa ra cam kết thời gian thực cứng.

## 9. Thiết kế để xử lý việc trễ

Trước khi tối ưu độ chính xác, quyết định ý nghĩa của một lượt đã trễ:

- Nếu chỉ cần trạng thái mới nhất, có thể gộp hoặc bỏ qua một số lượt theo chính sách rõ ràng.
- Nếu mỗi kỳ là công việc bắt buộc, cần nhận dạng kỳ và theo dõi hoàn thành; lịch trong bộ nhớ không thay lưu trữ công việc bền vững.
- Nếu một lượt chậm do dịch vụ phía sau, cân nhắc giảm tốc hoặc backoff thay vì chạy sát các lượt để đuổi nhịp.
- Nếu cần phản hồi sau một sự kiện, dùng điều kiện/sự kiện thực thay vì chỉ ngủ rồi đoán công việc trước đã xong.

Giữ phần việc trên scheduler ngắn khi phù hợp, nhưng nếu chuyển công việc sang executor khác, vẫn cần giới hạn đồng thời và theo dõi hoàn tất. Việc tick lịch trở nên nhanh không chứng minh phần nghiệp vụ đã đáp ứng thời hạn; phần đó có thể chỉ chuyển sang một queue khác.

Tăng số luồng scheduler có thể giảm một loại chờ tài nguyên, nhưng không giải quyết mọi nguyên nhân trễ. Với cùng đăng ký định kỳ, các lượt không chồng; thêm luồng không tự làm một chuỗi chậm chạy song song. Tải, trạng thái và ranh giới hoàn thành phải được thiết kế cùng nhau.

## 10. Ngoại lệ, timeout và hủy không phải chỉ số chính xác thời gian

Một chuỗi định kỳ có thể ngừng vì ngoại lệ thoát khỏi một lượt. Khi đó việc không thấy tick không đơn giản là jitter lớn; cần quan sát ScheduledFuture và trạng thái nghiệp vụ.

`get(timeout, unit)` hết hạn chỉ kết thúc khoảng chờ của nơi gọi. Nó không tự hủy tác vụ lịch hoặc bảo đảm phần việc đang chạy đã dừng ở mốc đó. `cancel(true)` cũng chỉ cố yêu cầu ngắt khi hỗ trợ; tác dụng phụ và phần dọn dẹp có thể cần thêm thời gian.

Dừng scheduler có chính sách riêng cho công việc định kỳ và công việc trễ đã đăng ký. Chủ sở hữu cần cancel/shutdown/awaitTermination phù hợp, không lấy việc hết thời gian chờ ở main làm bằng chứng mọi luồng đã kết thúc.

## 11. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Delay 100 ms nghĩa task bắt đầu đúng 100 ms | Nó trở thành đủ điều kiện; còn trễ thực thi |
| TimeUnit.NANOSECONDS tạo lịch chính xác nano giây | Đơn vị biểu diễn khác độ phân giải/độ trễ lập lịch |
| nanoTime là giờ UTC chính xác hơn currentTimeMillis | Nó dùng để đo khoảng thời gian trong cùng JVM |
| Sleep đủ lâu thì câu lệnh sau chắc chạy đúng lúc | Còn phụ thuộc đánh thức và cấp CPU |
| Tăng priority hoặc quay chờ là có hạn chót cứng | Không loại bỏ các nguồn trễ của toàn hệ thống |
| Một lần chạy đúng giờ chứng minh lịch chính xác | Cần hợp đồng API và đo phân bố dưới điều kiện phù hợp |
| Không có tick nghĩa chắc chắn hệ điều hành trễ | Có thể chuỗi đã lỗi, bị hủy, bị chặn hoặc scheduler đã dừng |

Tự kiểm tra:

1. Vì sao target trong ví dụ chưa done dù delay 20 ms đã qua? **Luồng duy nhất của scheduler công việc vẫn bị giữ ở tác vụ trước.**
2. Vì sao observer phải độc lập trong thí nghiệm? **Marker phải có thể tiến triển trong khi worker đang bận; cùng nhóm một luồng sẽ tự chờ nhau.**
3. `observedDelay` đo chính xác thời điểm nội bộ nào không? **Không.** Nó đo từ mốc ứng dụng trước đăng ký đến đầu Callable, có cả chi phí ranh giới gọi.
4. Vì sao không kiểm thử output bằng một số mili giây cố định? **Thời điểm thực phụ thuộc môi trường; bài kiểm chứng điều kiện và quan hệ trước-sau có cơ sở.**

Thực hành: đổi scheduler công việc từ một thành hai luồng. Dự đoán việc giữ một luồng còn bảo đảm target chưa chạy không; sửa kiểm tra để không yêu cầu output false cố định trong cấu hình mới. Sau đó thu một tập mẫu độ trễ trên tải đại diện, nêu rõ ranh giới đo và cửa sổ chấp nhận trước khi kết luận cấu hình có phù hợp yêu cầu hay không.
