# Tác vụ chạy lâu hơn chu kỳ và giới hạn chồng lặp

## 1. Đến mốc tiếp theo nhưng lần trước chưa xong

Giả sử một công việc cần khoảng 8 giây để thực hiện, nhưng được lập lịch mỗi 5 giây.

Câu hỏi cần trả lời không chỉ là “lịch chạy nhanh hay chậm”, mà gồm:

- Lần tiếp theo bắt đầu theo mốc ban đầu hay sau khi lần trước kết thúc?
- Hai lần của cùng lịch có chạy đồng thời không?
- Tăng số worker có làm một lịch tự chồng lặp không?
- Nếu Runnable chỉ chuyển việc sang executor khác, phần xử lý bên kia có còn được bảo vệ không?

Với các phương thức định kỳ của ScheduledExecutorService, một lần chạy lâu có thể làm các lần sau bắt đầu trễ. Nó không tự buộc hai lần của cùng lịch chạy cùng lúc.

Bài tập trung vào hành vi khi thời gian thực hiện vượt chu kỳ; ví dụ hoàn chỉnh dùng Java 17+ và vẫn phù hợp hợp đồng Java hiện hành.

## 2. Fixed rate và fixed delay đo khoảng cách khác nhau

| API | Cách xác định thời điểm dự kiến |
|---|---|
| `scheduleAtFixedRate` | Theo dãy mốc từ lúc bắt đầu: initialDelay, initialDelay + period, ... |
| `scheduleWithFixedDelay` | Đợi delay tính từ khi một lần kết thúc tới khi lần tiếp theo được bắt đầu |

Ví dụ khai báo minh họa:

```java
scheduler.scheduleAtFixedRate(
        task, 0, 5, TimeUnit.SECONDS);

scheduler.scheduleWithFixedDelay(
        task, 0, 5, TimeUnit.SECONDS);
```

Đây là hai lựa chọn để so sánh, không phải đề xuất đăng ký cả hai cho cùng công việc trong ứng dụng. `task` là Runnable và `scheduler` là ScheduledExecutorService đã được chuẩn bị.

### Khi công việc mất 8 giây

Bỏ qua chi phí phụ và giả sử worker được cấp thời gian chạy ngay khi có thể:

| Kiểu lịch | Các mốc dự kiến hoặc sớm nhất trong ví dụ |
|---|---|
| Fixed rate 5 giây | Mốc ban đầu là 0, 5, 10, 15, ... nhưng lần 2 không bắt đầu trước khi lần 1 xong ở khoảng giây 8 |
| Fixed delay 5 giây | Lần 1 từ 0 tới 8; lần 2 sớm nhất khoảng 13; lần 3 sớm nhất khoảng 26 |

Với fixed rate, lần sau có thể bắt đầu gần như ngay sau khi lần trước kết thúc nếu nó đã trễ mốc. Với fixed delay, luôn có khoảng delay giữa kết thúc lần trước và thời điểm được phép bắt đầu lần sau.

Đó là khác biệt về cách lập lịch, không phải bảo đảm thời gian thực. Tải hệ thống hoặc worker đang bận còn có thể làm thời điểm thực tế muộn hơn.

Hợp đồng nằm trong [ScheduledExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).

## 3. Một lịch định kỳ không chồng các lần chạy của chính nó

Với các lịch định kỳ này, lần chạy tiếp theo của **cùng tác vụ được đăng ký định kỳ** không thực hiện đồng thời với lần trước.

Điều đó vẫn đúng khi ScheduledThreadPoolExecutor có nhiều worker. Một worker khác có thể chạy lần tiếp theo sau khi lần trước xong, nhưng không được dùng để mở đồng thời hai lần của cùng lịch.

```text
Cùng một lịch:
lần 1 [----------]
                  lần 2 [----------]
                                    lần 3 [----------]

Không tự biến thành:
lần 1 [----------]
        lần 2 [----------]
                lần 3 [----------]
```

Tài liệu ScheduledThreadPoolExecutor còn quy định tác động của lần trước xảy ra trước tác động của lần sau trong cùng chuỗi, dù chúng có thể chạy trên các Thread khác nhau. Không nên dựa vào tên hoặc danh tính một Thread cụ thể để lưu trạng thái nghiệp vụ của lịch.

Chi tiết tại [ScheduledThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

### Tăng worker giúp gì?

Nhiều worker có thể giúp các lịch **khác nhau** hoặc tác vụ chạy một lần không phải chờ một công việc dài giữ worker duy nhất.

Nó không làm một chuỗi định kỳ có hai bản thực thi đồng thời để bắt kịp. Nếu công việc luôn cần 8 giây, muốn xong mỗi 5 giây phải xem lại công việc hoặc yêu cầu, thay vì chỉ tăng kích thước scheduler và kỳ vọng chuỗi ấy tự song song hóa.

## 4. Fixed rate trễ có thể chạy sát nhau để đuổi mốc

Một chu kỳ ngắn không có nghĩa mỗi chu kỳ tạo ra một worker mới.

Nếu một lần chạy đột nhiên mất lâu rồi các lần sau ngắn lại, fixed rate có thể thực hiện các lần tiếp theo với khoảng cách nhỏ để tiến gần dãy mốc ban đầu. Không được giả định luôn có một khoảng nghỉ bằng period sau mỗi lần kết thúc.

Nếu mọi lần đều dài hơn period, độ trễ so với dãy mốc có thể tiếp tục tăng; không có cách tăng tốc tự động chỉ từ chữ “rate”.

Ứng dụng phải quyết định liệu các lần xử lý trễ còn hữu ích không. Chẳng hạn cập nhật trạng thái hiện tại có thể không cần xử lý riêng mọi mốc cũ, còn một nghiệp vụ cần từng kỳ xử lý lại có yêu cầu khác.

Không tự suy luận chính sách bỏ các mốc trễ chỉ từ API này. Nếu cần bỏ, gộp hoặc chỉ giữ lần gần nhất, phải thiết kế quy tắc ở cấp ứng dụng.

## 5. Thí nghiệm Java 17+: giữ lần đầu lâu hơn chu kỳ

Ví dụ đặt fixed rate một mili giây nhưng giữ lần đầu tại chốt trong khoảng quan sát 50 ms. Scheduler có hai worker để chứng minh không chồng lặp không phải chỉ do thiếu worker thứ hai.

Lưu thành **`PeriodicOverlapDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicOverlapDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(2);

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);

        AtomicInteger calls = new AtomicInteger();
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxActive = new AtomicInteger();

        Runnable job = () -> {
            int currentActive = active.incrementAndGet();
            maxActive.accumulateAndGet(currentActive, Math::max);
            int number = calls.incrementAndGet();

            try {
                if (number == 1) {
                    firstStarted.countDown();
                    releaseFirst.await();
                } else if (number == 2) {
                    secondStarted.countDown();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        };

        ScheduledFuture<?> periodic = null;
        try {
            periodic = scheduler.scheduleAtFixedRate(
                    job, 0, 1, TimeUnit.MILLISECONDS);

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "First execution did not start");
            }

            boolean secondWhileFirstHeld =
                    secondStarted.await(50, TimeUnit.MILLISECONDS);

            System.out.println(
                    "second while first held: "
                    + secondWhileFirstHeld);
            System.out.println(
                    "calls while first held: " + calls.get());

            releaseFirst.countDown();

            if (!secondStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Second execution did not start");
            }

            periodic.cancel(false);

            System.out.println(
                    "max concurrent: " + maxActive.get());
            System.out.println(
                    "at least two calls: " + (calls.get() >= 2));
        } finally {
            releaseFirst.countDown();
            if (periodic != null && !periodic.isDone()) {
                periodic.cancel(true);
            }

            scheduler.shutdown();
            try {
                if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                    scheduler.shutdownNow();
                    if (!scheduler.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Scheduler did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                scheduler.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 PeriodicOverlapDemo.java
java PeriodicOverlapDemo
```

Stdout chính xác:

```text
second while first held: false
calls while first held: 1
max concurrent: 1
at least two calls: true
```

### Đọc kết quả đúng phạm vi

Chốt giữ lần đầu chưa thể thoát, còn lần chờ 50 ms quan sát rằng lần hai chưa bắt đầu dù period chỉ là 1 ms. Khi mở chốt, các lần tiếp theo mới có thể tiếp tục.

Bộ đếm maxActive chỉ đạt 1. Có thể nhiều hơn hai lần đã chạy trước lúc main hủy lịch, nên ví dụ không khẳng định số lần cuối cùng chính xác bằng 2.

Mục tiêu là xác minh không chồng lặp, không đo độ chính xác của period một mili giây. Chu kỳ rất ngắn trong ví dụ không phải giá trị khuyến nghị cho tác vụ thật.

Các chốt thiết lập quan hệ rõ ràng; không dùng một sleep để đoán lần đầu đã bắt đầu hay chưa. Main chỉ in sau các điều kiện cần quan sát. Các khoảng chờ năm giây giúp báo lỗi khi không có tiến triển.

Main khai báo throws Exception để giữ ví dụ tập trung; trong ứng dụng thật, cần phản hồi ngắt, lỗi lập lịch và lỗi thực thi theo chính sách.

## 6. Bảo đảm áp dụng cho một lần đăng ký, không khóa cả đối tượng Runnable

Nếu dùng cùng một đối tượng Runnable để đăng ký hai lịch khác nhau:

```java
scheduler.scheduleAtFixedRate(job, 0, 5, TimeUnit.SECONDS);
scheduler.scheduleAtFixedRate(job, 0, 5, TimeUnit.SECONDS);
```

thì hai chuỗi độc lập có thể chạy đồng thời khi có worker. Scheduler không khóa toàn cục đối tượng job để ngăn mọi cách gọi vào nó.

Tương tự, một thành phần khác có thể gọi trực tiếp `job.run()` hoặc submit chính job sang executor khác.

Vì vậy, với trạng thái dùng chung, vẫn cần xác định mọi đường truy cập. Bảo đảm giữa các lần của một lịch không tự bảo vệ dữ liệu trước các luồng bên ngoài.

## 7. Chuyển việc sang executor khác có thể tạo chồng lặp nghiệp vụ

Đoạn mã minh họa:

```java
scheduler.scheduleAtFixedRate(
        () -> workers.submit(this::rebuildIndex),
        0,
        5,
        TimeUnit.SECONDS);
```

`workers` là executor khác và `rebuildIndex` là công việc nặng của ứng dụng.

Runnable được lập lịch ở đây chỉ làm thao tác submit. Nó có thể kết thúc rất nhanh, dù `rebuildIndex` mất 20 giây.

Năm giây sau, lần Runnable kế tiếp có thể lại submit thêm một rebuild. Kết quả:

```text
Runnable định kỳ:  submit -> submit -> submit -> ...
Việc bên workers: [----------------]
                           [----------------]
                                    [----------------]
```

Không có mâu thuẫn với bảo đảm của scheduler: các Runnable chuyên submit không chồng lặp; chính những công việc tách ra phía sau mới chồng lặp.

Nếu cần chỉ một rebuild hoạt động, phải quản lý trạng thái của **toàn bộ công việc nặng**, không chỉ thời gian callback trên scheduler.

### Chọn chính sách khi công việc trước còn chạy

| Chính sách nghiệp vụ | Ý nghĩa |
|---|---|
| Bỏ lần kích hoạt mới | Không nhận thêm nếu công việc trước còn hoạt động |
| Gộp yêu cầu | Ghi nhận cần làm thêm một lần sau khi lần hiện tại xong |
| Xếp hàng có giới hạn | Chấp nhận một số lần chờ, từ chối hoặc bỏ theo quy tắc khi đầy |
| Cho phép song song có giới hạn | Cho nhiều lần chạy cùng lúc khi công việc và tài nguyên cho phép |

Nếu dùng cờ AtomicBoolean hoặc permit để ngăn chồng lặp, phải xử lý cả thất bại submit, việc bị hủy trước khi bắt đầu và việc bị handler âm thầm bỏ. Không chỉ đặt cờ true rồi chờ finally của thân việc để xóa: thân việc có thể không bao giờ được thực thi.

## 8. Tác vụ dài cũng ảnh hưởng các lịch khác

Scheduler một luồng có thể bị một việc dài giữ worker khiến mọi lịch khác trễ. Đây là vấn đề giữa những công việc khác nhau, tách khỏi việc không chồng lặp của một chuỗi.

Tăng số core worker có thể giúp các lịch độc lập có năng lực chạy, nhưng vẫn cần xét CPU, kết nối và queue.

ScheduledThreadPoolExecutor dùng corePoolSize như số worker hữu ích cho mô hình của nó; chỉ tăng maximumPoolSize không phải cách mở rộng hữu ích như nhiều người suy luận từ ThreadPoolExecutor thường.

Nếu nhiều công việc đều tốn CPU quá mức hoặc cùng chờ tài nguyên hữu hạn, thêm worker có thể chỉ tăng tranh chấp. Cần đo cả thời gian chạy, độ trễ bắt đầu và số công việc còn hoạt động.

## 9. Ngoại lệ hoặc hủy làm chuỗi định kỳ kết thúc

Nếu một lần chạy ném ngoại lệ ra ngoài, các lần sau của lịch đó bị dừng. ScheduledFuture chuyển sang trạng thái hoàn tất do lỗi; get có thể báo ExecutionException chứa nguyên nhân.

Vì vậy, một lịch “không chạy lần sau” không nhất thiết do việc trước còn kéo dài. Nó có thể đã kết thúc vì lỗi.

Nếu muốn tiếp tục sau một loại lỗi tạm thời, mã cần bắt và xử lý có chủ đích. Không bắt mọi lỗi rồi bỏ qua chỉ để giữ lịch sống; điều đó có thể khiến hệ thống tiếp tục trong trạng thái không đúng.

Khi không còn cần lịch, giữ ScheduledFuture để hủy. `cancel(false)` không yêu cầu ngắt lần đang chạy; `cancel(true)` có thể cố ngắt theo khả năng triển khai. Tác vụ vẫn cần hợp tác dừng và dọn dẹp.

Future của lịch định kỳ đại diện cho **cả chuỗi**, không phải “kết quả của lần thứ ba”. Khi chuỗi vẫn hoạt động bình thường, get không trả về sau từng lần lặp. Vai trò đối tượng được mô tả tại [ScheduledFuture API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledFuture.html).

## 10. Độ trễ thời gian và tính đúng của nghiệp vụ

Khi một công việc chạy lâu hơn chu kỳ, phải xem lại ý nghĩa của “mỗi 5 giây”:

- Muốn lấy ảnh chụp trạng thái mới nhất khi có thể?
- Muốn thực hiện đủ từng kỳ với mã kỳ riêng?
- Muốn khoảng nghỉ tối thiểu sau mỗi lần?
- Hay muốn cho phép nhiều công việc độc lập thực hiện song song?

Fixed delay thường diễn đạt rõ nhu cầu “xong rồi nghỉ một khoảng”. Fixed rate phù hợp khi cần bám các mốc tương đối, nhưng ứng dụng phải chấp nhận và xử lý việc chạy trễ.

Không dùng scheduler trong bộ nhớ để tự suy ra cam kết xử lý đúng một lần cho từng mốc nghiệp vụ. Nếu tiến trình khởi động lại hoặc việc bị lỗi giữa chừng, cần cơ chế lưu trạng thái và đối soát phù hợp.

Một tác vụ cũng có thể tạo tác động bên ngoài trước khi bị ngắt; hủy không tự hoàn tác phần ấy. Việc chống xử lý trùng và việc ngăn chồng lặp là hai yêu cầu liên quan nhưng khác nhau.

## 11. Cách kiểm tra và giám sát

Để phát hiện công việc vượt chu kỳ, theo dõi:

- Thời gian bắt đầu và kết thúc của từng lần.
- Thời gian chạy.
- Độ trễ so với mốc dự kiến nếu có ý nghĩa.
- Số lần đang thực hiện của công việc nghiệp vụ.
- Số lần bị bỏ, gộp, từ chối hoặc kết thúc do lỗi theo chính sách.

Đo thời gian trôi qua nên dùng đồng hồ thích hợp như System.nanoTime, còn dấu thời gian lịch phục vụ liên kết log và nhu cầu nghiệp vụ.

Khi kiểm thử không chồng lặp, dùng bộ đếm số lần đang hoạt động và chốt giữ một lần chạy như ví dụ. Đừng chỉ xem hai dòng log có vẻ không gần nhau rồi kết luận mọi đường gọi đều an toàn.

Nếu công việc được chuyển sang executor khác, phải đặt phép đo quanh phần nghiệp vụ thực sự, không chỉ quanh callback submit trên scheduler.

## 12. Tự kiểm tra

1. Công việc fixed rate mất 8 giây với period 5 giây có tự chồng hai lần của cùng lịch không?
2. Scheduler có bốn worker có thay đổi bảo đảm ấy không?
3. Fixed delay 5 giây với công việc mất 8 giây có lần sau sớm nhất khoảng bao lâu tính từ lúc bắt đầu lần trước, nếu bỏ chi phí phụ?
4. Đăng ký cùng Runnable hai lần có được bảo vệ như một lịch duy nhất không?
5. Callback định kỳ chỉ submit việc nặng sang nơi khác: phần việc nặng có thể chồng lặp không?
6. Vì sao không nên dùng get của ScheduledFuture định kỳ để chờ “một lần chạy vừa xong”?

**Gợi ý:** (1) Không. (2) Không, bảo đảm vẫn áp dụng trong cùng chuỗi. (3) Khoảng 13 giây. (4) Không. (5) Có. (6) Future đại diện cho cả chuỗi, không hoàn tất bình thường sau từng lần.

Giới hạn cần nhớ là: **các lần thực hiện của cùng một lịch định kỳ không chồng lặp, nhưng công việc khác, lần đăng ký khác hoặc xử lý tách ra phía sau vẫn có thể chạy đồng thời**.
