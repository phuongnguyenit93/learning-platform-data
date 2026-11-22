# scheduleWithFixedDelay và khoảng nghỉ sau khi hoàn tất

## 1. Lặp theo nhịp hoàn tất công việc

Một ứng dụng kiểm tra trạng thái của dịch vụ ngoài. Mỗi lần kiểm tra mất thời gian khác nhau. Yêu cầu là: **kiểm tra xong thì nghỉ năm giây, rồi mới kiểm tra tiếp**.

`scheduleWithFixedDelay` diễn tả đúng quan hệ đó. Nó khác yêu cầu “bắt đầu một lần kiểm tra tại mỗi mốc năm giây tính từ lịch gốc”.

Mô hình:

```text
đợi initialDelay
    -> lần 1 bắt đầu
    -> lần 1 hoàn tất
    -> nghỉ delay
    -> lần 2 bắt đầu
    -> lần 2 hoàn tất
    -> nghỉ delay
    -> lần 3 bắt đầu
```

Điểm tham chiếu của mỗi khoảng nghỉ là **lúc phần thực thi trước kết thúc**, không phải lúc nó bắt đầu.

Bài dùng Java 17+ và API vẫn áp dụng trên Java hiện đại. Phạm vi là lịch lặp theo khoảng nghỉ sau mỗi lần hoàn tất, không phải lịch theo ngày giờ hay hệ thống lưu công việc bền vững.

## 2. Chữ ký và ý nghĩa tham số

```java
ScheduledFuture<?> scheduleWithFixedDelay(
        Runnable command,
        long initialDelay,
        long delay,
        TimeUnit unit);
```

| Tham số | Ý nghĩa |
| --- | --- |
| `command` | Công việc lặp lại |
| `initialDelay` | Khoảng chờ trước lần thực thi đầu |
| `delay` | Khoảng chờ từ khi một lần kết thúc tới lần tiếp theo bắt đầu |
| `unit` | Đơn vị cho cả hai khoảng thời gian |

`delay` phải lớn hơn 0. Command hoặc unit null là đầu vào không hợp lệ. Lời gọi có thể ném `RejectedExecutionException` nếu bộ lập lịch không tiếp nhận được lịch, chẳng hạn đã shutdown theo chính sách tiêu chuẩn.

Giá trị trả về là một `ScheduledFuture` đại diện **cả chuỗi lặp**, không phải chỉ một lần chạy. [Tài liệu scheduleWithFixedDelay](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html#scheduleWithFixedDelay(java.lang.Runnable,long,long,java.util.concurrent.TimeUnit))

Cách gọi trong một phương thức, sau khi đã có scheduler và job:

```java
ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
        job, 1, 5, TimeUnit.SECONDS);
```

Nghĩa là lần đầu chờ khoảng một giây; mỗi lần sau nghỉ ít nhất khoảng năm giây sau khi lần trước kết thúc, trong khả năng lập lịch thực tế.

## 3. Công thức để đọc đúng thời gian

Ký hiệu:

- `S[n]`: thời điểm bắt đầu lần n.
- `F[n]`: thời điểm kết thúc lần n.
- `D`: khoảng delay.

Quan hệ cần nhớ:

```text
S[n+1] >= F[n] + D
```

Dấu lớn hơn hoặc bằng thể hiện scheduler có thể bắt đầu muộn hơn do luồng bận hoặc môi trường lập lịch. Không có cam kết thời gian thực rằng lần tiếp theo bắt đầu chính xác tại mốc đó.

Ví dụ lý tưởng hóa: công việc mất ba giây và delay là năm giây:

```text
0s       3s       8s      11s      16s
|--run1--|--5s----|--run2--|--5s----|--run3...
```

Khoảng cách giữa hai lần bắt đầu là khoảng tám giây, không phải năm giây. Nếu công việc mất lâu hơn, nhịp bắt đầu cũng chậm lại.

Đây là phép minh họa quan hệ thời gian, không phải stdout hay kết quả hiệu năng được đo. Chi phí xử lý và lập lịch có thể làm các mốc thực tế muộn hơn.

Fixed delay không có ý nghĩa “chạy bù cho đủ số lần đã bỏ lỡ trong lúc công việc đang bận”. Nó đặt khoảng nghỉ tiếp theo dựa trên lần hoàn tất gần nhất.

## 4. Thí nghiệm: có nghỉ sau hoàn tất và không chạy chồng lấn

Chương trình dùng scheduler ba luồng nhưng chỉ tạo **một chuỗi định kỳ**. Nó ghi thời điểm bắt đầu/kết thúc ba lần thực thi.

Lần thứ ba được giữ ở chốt để main có thể hủy chuỗi trước khi cho nó kết thúc. Nhờ vậy không có lần thứ tư xuất hiện do main bị lập lịch chậm.

Tệp **FixedDelayTraceDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedDelayTraceDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newScheduledThreadPool(3);
        long delayNanos = TimeUnit.MILLISECONDS.toNanos(50);
        long[] starts = new long[3];
        long[] ends = new long[3];

        AtomicInteger runs = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peakActive = new AtomicInteger();
        CountDownLatch thirdStarted = new CountDownLatch(1);
        CountDownLatch allowThirdFinish = new CountDownLatch(1);
        CountDownLatch thirdExited = new CountDownLatch(1);

        Runnable job = () -> {
            int index = runs.getAndIncrement();
            int current = active.incrementAndGet();
            peakActive.accumulateAndGet(current, Math::max);
            starts[index] = System.nanoTime();

            try {
                if (index == 2) {
                    thirdStarted.countDown();
                    allowThirdFinish.await();
                } else {
                    TimeUnit.MILLISECONDS.sleep(20);
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                ends[index] = System.nanoTime();
                active.decrementAndGet();
                if (index == 2) {
                    thirdExited.countDown();
                }
            }
        };

        ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                job, 0, delayNanos, TimeUnit.NANOSECONDS);

        try {
            if (!thirdStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Third execution did not start");
            }

            handle.cancel(false);
            allowThirdFinish.countDown();
            if (!thirdExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Third execution did not exit");
            }

            boolean gapsRespectDelay =
                    starts[1] - ends[0] >= delayNanos
                    && starts[2] - ends[1] >= delayNanos;

            System.out.println("runs=" + runs.get());
            System.out.println("peakActiveForThisSchedule=" + peakActive.get());
            System.out.println("gapsRespectDelay=" + gapsRespectDelay);
            System.out.println("scheduleCancelled=" + handle.isCancelled());
        } finally {
            handle.cancel(true);
            allowThirdFinish.countDown();
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
javac --release 17 FixedDelayTraceDemo.java
java FixedDelayTraceDemo
```

Stdout khi hoàn tất bình thường:

```text
runs=3
peakActiveForThisSchedule=1
gapsRespectDelay=true
scheduleCancelled=true
```

Cách đọc:

1. Scheduler có ba luồng nhưng một chuỗi không có hai lần thực thi chồng lấn.
2. Mỗi thời điểm bắt đầu sau nằm cách điểm kết thúc được ghi trước đó ít nhất 50 ms.
3. Không in số mili giây chính xác vì môi trường có thể tạo chậm trễ khác nhau.
4. Sleep 20 ms chỉ mô phỏng công việc có thời gian xử lý; chốt mới là cơ chế điều phối xác định lúc main hủy.
5. Hủy với false cho phép lần thứ ba rời chốt và hoàn tất phần đang chạy; nó không cho chuỗi tiếp tục lần thứ tư.

Điểm ends được ghi ngay trước khi phần thân trả về, nên khoảng thực tế tính từ khi Runnable hoàn toàn kết thúc tới lần kế tiếp còn bao gồm một ít chi phí sau điểm ghi. Ví dụ kiểm tra cận dưới, không khẳng định đo chính xác toàn bộ nội bộ scheduler.

Các lần thực thi kế tiếp của cùng tác vụ định kỳ trong ScheduledThreadPoolExecutor không chồng lấn; tác động của lần trước có quan hệ happens-before với lần sau, dù có thể đổi luồng làm việc. [Tài liệu ScheduledThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html)

`nanoTime` dùng cho khoảng thời gian đã trôi qua trong cùng JVM, không phải đồng hồ lịch hoặc mốc dùng để so sánh giữa các máy. [Tài liệu System.nanoTime](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/System.html#nanoTime())

## 5. Một chuỗi không chồng lấn không có nghĩa cả ứng dụng tuần tự

Bảo đảm ở trên thuộc về **một lần đăng ký lịch**, với phần thân Runnable mà scheduler thực sự gọi.

Những trường hợp khác vẫn có thể đồng thời:

- Đăng ký hai lịch riêng cho cùng một đối tượng Runnable.
- Hai lịch khác nhau cùng truy cập một collection.
- Phần thân gửi việc sang bộ thực thi khác rồi trả về ngay.
- Nhiều instance ứng dụng cùng đăng ký một công việc.

Ví dụ phần thân chỉ gọi `worker.submit(actualWork)` rồi kết thúc: khoảng delay được tính sau khi việc **gửi** hoàn tất, không đợi actualWork ở nơi khác làm xong. Các actualWork có thể chồng lấn và tích hàng đợi.

Nếu ý định là “việc nặng xong rồi mới nghỉ”, phải giữ quan hệ hoàn tất đúng trong thiết kế. Không coi callback gửi việc ngắn là bằng chứng công việc nghiệp vụ đã kết thúc.

Không giữ luồng scheduler để chờ một công việc con trên chính scheduler nếu có thể hết vị trí chạy; quan hệ chờ đó có thể làm hệ thống không tiến triển.

## 6. Future của chuỗi khác Future của một lần chạy

`ScheduledFuture` cho phép theo dõi/hủy lịch, nhưng handle của scheduleWithFixedDelay đại diện chuỗi lặp. [Tài liệu ScheduledFuture](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

| Quan sát | Ý nghĩa |
| --- | --- |
| Một lần chạy đã xong | Chưa làm Future của chuỗi hoàn thành thành công |
| Chuỗi vẫn hoạt động | get có thể tiếp tục chờ |
| Chuỗi bị hủy | get ném CancellationException |
| Một lần ném lỗi không được xử lý | Chuỗi kết thúc lỗi; get ném ExecutionException |
| get có timeout hết thời gian | Bên gọi hết lượt chờ; chuỗi không tự bị hủy |

Get của chuỗi không trả null sau mỗi lần hoàn tất như lịch một lần bằng Runnable. Nó không có một kết quả hoàn thành bình thường cho chuỗi vô hạn.

Nếu cần nhận kết quả từng lần, phải có cơ chế riêng như cập nhật trạng thái an toàn hoặc phát một sự kiện/kết quả theo hợp đồng. Không tạo một luồng chỉ để gọi get vô hạn rồi tưởng rằng nó đang thu kết quả từng lượt.

## 7. Lỗi không được xử lý sẽ ngừng những lần sau

Nếu một lần thực thi ném ngoại lệ ra khỏi Runnable, các lần tiếp theo bị chặn. Đừng giả định scheduler sẽ luôn gọi lại dù phần thân thất bại.

Tệp **FixedDelayFailureDemo.java**:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedDelayFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicInteger attempts = new AtomicInteger();

        ScheduledFuture<?> handle = scheduler.scheduleWithFixedDelay(
                () -> {
                    if (attempts.incrementAndGet() == 2) {
                        throw new IllegalStateException("Refresh failed");
                    }
                },
                0, 20, TimeUnit.MILLISECONDS);

        try {
            try {
                handle.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("failureCause="
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("attempts=" + attempts.get());
            System.out.println("scheduleDone=" + handle.isDone());
            System.out.println("scheduleCancelled=" + handle.isCancelled());

            String result = scheduler.schedule(
                    () -> "OK", 0, TimeUnit.MILLISECONDS)
                    .get(5, TimeUnit.SECONDS);
            System.out.println("schedulerStillUsable=" + result);
        } finally {
            handle.cancel(true);
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
javac --release 17 FixedDelayFailureDemo.java
java FixedDelayFailureDemo
```

Stdout:

```text
failureCause=IllegalStateException
attempts=2
scheduleDone=true
scheduleCancelled=false
schedulerStillUsable=OK
```

Lần thứ hai thất bại, không có lần thứ ba của chuỗi đó. Nhưng scheduler vẫn tiếp nhận lịch một lần khác. **Lịch ngừng** và **toàn bộ scheduler ngừng** là hai trạng thái riêng.

Nếu nghiệp vụ muốn tiếp tục sau một lỗi dự kiến, phải xử lý lỗi đó trong phần thân và ghi nhận kết quả rõ ràng trước khi trả bình thường. Khi đó delay được tính sau phần xử lý lỗi nữa.

Không bắt mọi Throwable rồi bỏ qua. Cần phân biệt lỗi dự kiến có thể tiếp tục với lỗi cần dừng để người vận hành biết; việc nuốt lỗi sẽ làm một lịch hỏng trông giống đang khỏe.

## 8. Hủy chuỗi và dừng ứng dụng

`handle.cancel(false)` yêu cầu hủy chuỗi mà không ngắt phần đang chạy. `cancel(true)` có thể yêu cầu ngắt luồng thực hiện theo lớp triển khai; mã tác vụ cần hợp tác.

Future đã canceled/done không chứng minh khối dọn tài nguyên của lần đang chạy đã hoàn tất. Trong ví dụ đầu, main chờ chốt thirdExited trước khi báo kết quả quan sát.

Bên sở hữu scheduler phải quyết định:

1. Ngừng nguồn đăng ký lịch mới.
2. Hủy lịch hoặc shutdown theo chính sách mong muốn.
3. Cho phần đang chạy hoàn tất hoặc yêu cầu ngắt.
4. Chờ xác nhận kết thúc.
5. Đóng tài nguyên mà phần việc sử dụng.

ScheduledThreadPoolExecutor mặc định không tiếp tục chuỗi định kỳ sau shutdown; nó có chính sách cấu hình cho trường hợp cần khác. Không thay chính sách mà chưa xét việc shutdown có thể chờ mãi với chuỗi vẫn tiếp tục.

Một thành phần chỉ mượn scheduler dùng chung không tự đóng nó khi một lịch kết thúc. Nó thường chỉ quản lý handle của lịch mà nó sở hữu.

## 9. Phù hợp với nhịp nghỉ, không phải nhịp đồng hồ

| Nhu cầu | Cách diễn đạt thường phù hợp |
| --- | --- |
| Xử lý xong rồi nghỉ một khoảng | scheduleWithFixedDelay |
| Theo các mốc chu kỳ dự kiến từ lịch gốc | scheduleAtFixedRate |
| Chỉ chạy một lần sau khoảng chờ | schedule |
| Chạy theo ngày/giờ/múi giờ | Cần thiết kế lịch theo thời gian lịch |
| Thử lại có số lượt và deadline thay đổi | Điều phối retry rõ ràng, có thể dùng schedule một lần |

Với fixed delay, công việc càng lâu thì khoảng giữa các lần bắt đầu càng dài. Đây thường là đặc điểm mong muốn khi thăm dò một dịch vụ: không tạo nhịp bắt đầu dồn dập chỉ để chạy bù lịch cũ.

Nhưng fixed delay không phải một bộ giới hạn tốc độ tổng của hệ thống. Nhiều lịch hoặc nhiều instance vẫn có thể cộng dồn tải; một lần chạy cũng có thể phát nhiều yêu cầu ra ngoài.

Nếu thời gian phần thân thay đổi từ 1 đến 20 giây và delay là 5 giây, nhịp bắt đầu thay đổi theo. Nếu hệ thống yêu cầu “đúng mỗi phút có một lần”, phải đánh giá lại yêu cầu thay vì chỉ đổi con số delay.

## 10. Quan sát để biết lịch còn khỏe

Những thông tin hữu ích gồm:

- Lần bắt đầu gần nhất và lần hoàn tất gần nhất.
- Thời gian thực thi mỗi lần.
- Số lần thành công/lỗi.
- Trạng thái handle: đang hoạt động, bị hủy hay lỗi.
- Thời gian từ lúc đủ điều kiện tới lúc bắt đầu nếu cần điều tra trễ.
- Sức khỏe tài nguyên mà phần việc gọi.

Không chỉ báo “đã đăng ký lịch thành công” rồi coi công việc sẽ chạy mãi. Một ngoại lệ không được xử lý có thể làm chuỗi ngừng.

Lần thực thi gần nhất có thể đang kéo dài, không nhất thiết lịch đã bị mất. Phân biệt không có lần mới vì lần cũ chưa kết thúc với không có lần mới vì Future đã kết thúc lỗi.

Trong thí nghiệm, không lấy các mốc thời gian tuyệt đối để làm stdout chuẩn; chỉ kiểm tra quan hệ khoảng nghỉ và không chồng lấn. Kiểm chứng hợp đồng thời gian nên dùng chốt và cận dưới có ý nghĩa thay vì đòi lịch chạy chính xác từng mili giây.

## 11. Giới hạn tài nguyên vẫn cần được quản lý

Một chuỗi fixed delay không chồng lấn giúp giới hạn bản thân chuỗi đó ở tối đa một lần thực thi tại một thời điểm. Nhưng một scheduler có thể chứa rất nhiều chuỗi, lịch một lần và phần tử giữ tham chiếu dữ liệu.

ScheduledThreadPoolExecutor dùng hàng đợi trì hoãn không giới hạn nhỏ theo cấu hình. Cần giới hạn nguồn đăng ký và dọn handle khi không còn cần.

Tác vụ chạy lâu chiếm một luồng và có thể làm các lịch khác đủ điều kiện nhưng bắt đầu muộn. Tăng luồng chỉ nên dựa trên khả năng tài nguyên phụ thuộc; không tăng chỉ để che một thao tác mạng không có timeout.

Hủy nhiều lịch xa cũng có thể giữ phần tử trong queue theo chính sách mặc định của lớp; nếu phù hợp, dùng remove-on-cancel policy để quản lý bộ nhớ. Nó là vấn đề lưu tham chiếu, khác việc phần thân đã dừng thực tế hay chưa.

## 12. Tự giải thích một lịch

Một lần kiểm tra mất 12 giây, initialDelay bằng 1 giây và delay bằng 5 giây. Hãy trả lời:

1. Trong mô hình không có chậm trễ thêm, lần đầu bắt đầu/kết thúc khi nào?
2. Lần tiếp theo có thể bắt đầu sớm nhất ở mốc nào?
3. Nếu một lần sau chỉ mất 2 giây, khoảng tới lần tiếp theo thay đổi thế nào?
4. Nếu lần thực thi ném lỗi ra ngoài, chuỗi có tự tiếp tục không?
5. Nếu phần thân chỉ gửi công việc sang bộ khác rồi trả về, “hoàn tất” đang chỉ mốc nào?
6. Khi hủy, ai xác nhận phần đang chạy đã dọn tài nguyên?

Với scheduleWithFixedDelay, câu hỏi quan trọng nhất là **phần công việc nào đã thật sự hoàn tất trước khi bắt đầu tính khoảng nghỉ**. Giữ đúng ranh giới đó giúp lịch lặp phản ánh đúng nhịp xử lý của ứng dụng.
