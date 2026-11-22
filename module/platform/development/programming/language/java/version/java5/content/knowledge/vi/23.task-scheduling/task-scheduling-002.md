# Lập lịch một lần với Runnable hoặc Callable

## 1. Lập lịch một lần giải quyết việc gì?

Một tác vụ có thể cần thực hiện **sau một khoảng trễ**, chẳng hạn kiểm tra trạng thái sau vài giây hoặc tính một kết quả khi đã qua thời gian chờ.

Với `ScheduledExecutorService`, phương thức `schedule` nhận công việc và khoảng trễ, rồi trả một đối tượng theo dõi. Luồng gọi không cần ngủ để chờ tới lúc công việc được phép chạy.

Cần tách hai ý:

- **Chạy trễ một lần**: dùng `schedule`.
- **Chạy lặp lại theo lịch**: là nhu cầu khác, có các phương thức định kỳ riêng.

Một lần schedule không tự lặp. Nếu cùng Runnable được gửi schedule ba lần thì đó là ba lần lập lịch độc lập, không phải một lịch duy nhất tự chạy ba lần.

Các API trong bài vẫn áp dụng trong Java hiện hành; chương trình hoàn chỉnh chạy trên Java 17+.

## 2. Chuẩn bị bộ thực thi có lịch

Ví dụ khai báo:

```java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();
```

Các lớp nằm trong `java.util.concurrent`.

Một worker phù hợp khi công việc đơn giản và có thể thực hiện tuần tự. Nếu có nhiều tác vụ độc lập cần khả năng thực hiện đồng thời, có thể tạo:

```java
ScheduledExecutorService scheduler =
        Executors.newScheduledThreadPool(2);
```

Đây là hai lựa chọn thay thế trong ví dụ, không phải yêu cầu tạo hai scheduler cho cùng một công việc.

Scheduler quyết định khi nào công việc được phép bắt đầu và tổ chức việc thực hiện. Bản thân Runnable hoặc Callable vẫn là nơi mô tả công việc.

Không tự tạo một Thread rồi sleep chỉ để biểu diễn một lời gọi cần chạy trễ, khi một scheduler có vòng đời quản lý rõ đã phù hợp.

## 3. Hai overload của schedule

Các chữ ký cốt lõi:

```java
ScheduledFuture<?> schedule(
        Runnable command, long delay, TimeUnit unit);

<V> ScheduledFuture<V> schedule(
        Callable<V> callable, long delay, TimeUnit unit);
```

Đây là phần trích chữ ký để đọc API, không phải các phương thức cần chép lại vào ứng dụng.

| Tác vụ | Chữ ký công việc | Giá trị nhận từ get khi thành công |
|---|---|---|
| Runnable | `void run()` | `null` |
| Callable<V> | `V call() throws Exception` | Giá trị kiểu V do công việc trả |

Với Runnable, Future vẫn hữu ích dù không có dữ liệu nghiệp vụ: nó cho phép biết công việc đã hoàn tất, có thất bại không hoặc đã bị hủy chưa.

Với Callable, có thể truyền checked exception ra khỏi `call()`; lỗi được công bố qua đối tượng kết quả khi thực thi.

Chi tiết hai overload nằm trong [ScheduledExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html).

### Khai báo kiểu giúp làm rõ ý định

Mã minh họa:

```java
Runnable notification = () -> {
    sendNotification();
};

Callable<String> report = () -> buildReport();
```

Các phương thức `sendNotification` và `buildReport` thuộc ứng dụng.

Một số lambda dạng biểu thức lời gọi phương thức có thể phù hợp với nhiều kiểu đích. Nếu việc chọn overload không rõ, khai báo biến Runnable hoặc Callable trước khi schedule, thay vì suy đoán chỉ từ hình thức lambda.

## 4. Delay là khoảng trễ, không phải thời hạn hoàn thành

```java
ScheduledFuture<?> handle = scheduler.schedule(
        notification,
        2,
        TimeUnit.SECONDS);
```

Ý nghĩa: công việc được phép chạy sau khoảng trễ hai giây tính theo lần lập lịch này.

Nó không có nghĩa:

- Công việc hoàn tất trong hai giây.
- Scheduler đánh thức worker đúng một mốc thời gian thực tuyệt đối.
- Worker chắc chắn rảnh ngay khi hết khoảng trễ.
- Công việc bị hủy nếu bắt đầu muộn.

Nếu worker đang bận, công việc đến hạn có thể bắt đầu trễ. Tải hệ thống và việc lập lịch luồng cũng ảnh hưởng thời điểm thực tế.

### Delay bằng 0 hoặc âm

Với schedule chạy một lần, delay bằng 0 hoặc âm được coi là yêu cầu thực hiện ngay khi có thể. Điều đó không buộc công việc chạy trực tiếp trên luồng gọi.

Đừng nhầm với chu kỳ của lịch lặp; các tham số period của phương thức khác có quy tắc riêng.

### Không truyền thời điểm lịch như một delay

Schedule nhận khoảng trễ tương đối. Một giá trị epoch milliseconds không phải “ngày giờ cần chạy” nếu truyền thẳng vào đối số delay.

Nếu tính chênh lệch từ một thời điểm lịch, cần xác định múi giờ, trường hợp đã quá hạn và tác động của điều chỉnh đồng hồ. Với nhu cầu “chạy vào một giờ lịch mỗi ngày” hoặc lịch cron, không nên tự xem một lời schedule tương đối là giải pháp đầy đủ.

## 5. ScheduledFuture: trạng thái, kết quả và thời gian trễ còn lại

ScheduledFuture kế thừa khả năng của Future và Delayed:

- `get()`: chờ kết quả.
- `get(timeout, unit)`: chờ kết quả trong một khoảng.
- `isDone()`: kiểm tra đã hoàn tất theo một trạng thái cuối cùng chưa.
- `isCancelled()`: kiểm tra trạng thái hủy.
- `cancel(...)`: yêu cầu hủy.
- `getDelay(unit)`: xem khoảng trễ theo đơn vị yêu cầu.

Xem [ScheduledFuture API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledFuture.html).

### get bao gồm cả thời gian đợi tới hạn

Nếu schedule một công việc sau 30 giây rồi gọi get ngay, nơi gọi có thể phải chờ cả khoảng trễ, thời gian đợi worker rảnh và thời gian công việc thực hiện.

`getDelay` không dự đoán thời gian còn lại tới lúc có kết quả. Delay đã về 0 hoặc âm chỉ cho biết mốc được phép chạy đã tới hoặc đã qua; công việc có thể vẫn đang đợi worker hoặc đang chạy.

Không dùng `getDelay` để hiển thị “còn bao nhiêu giây chắc chắn hoàn tất” cho người dùng.

### Timeout chờ không tự hủy lịch

Nếu `handle.get(1, TimeUnit.SECONDS)` hết hạn, nơi gọi nhận TimeoutException. Công việc đã lập lịch vẫn có thể được chạy sau đó nếu ứng dụng không yêu cầu hủy hoặc thay đổi vòng đời scheduler.

Đây là khác biệt giữa thời hạn chờ của nơi gọi và thời điểm tác vụ được thực hiện.

## 6. Chương trình Java 17+: Runnable, Callable và một lỗi

Lưu thành **`OneShotScheduleDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class OneShotScheduleDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicInteger actions = new AtomicInteger();

        try {
            Runnable action = () -> {
                actions.incrementAndGet();
            };

            ScheduledFuture<?> actionFuture = scheduler.schedule(
                    action, 50, TimeUnit.MILLISECONDS);

            System.out.println(
                    "Runnable result: "
                    + actionFuture.get(5, TimeUnit.SECONDS));

            Callable<String> report =
                    () -> "actions=" + actions.get();

            ScheduledFuture<String> reportFuture = scheduler.schedule(
                    report, 50, TimeUnit.MILLISECONDS);

            System.out.println(
                    "Callable result: "
                    + reportFuture.get(5, TimeUnit.SECONDS));

            Callable<String> failing = () -> {
                throw new IOException("report unavailable");
            };

            ScheduledFuture<String> failedFuture = scheduler.schedule(
                    failing, 0, TimeUnit.MILLISECONDS);

            try {
                failedFuture.get(5, TimeUnit.SECONDS);
                throw new AssertionError("Expected failure");
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println(
                        "Failure: " + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage());
            }

            System.out.println("Action executions: " + actions.get());
        } finally {
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
javac --release 17 OneShotScheduleDemo.java
java OneShotScheduleDemo
```

Stdout chính xác:

```text
Runnable result: null
Callable result: actions=1
Failure: IOException: report unavailable
Action executions: 1
```

### Vì sao kết quả có thứ tự xác định?

Main đợi action hoàn tất rồi mới schedule report. Vì vậy report đọc số hành động đã là 1; không dựa vào giả định công việc 50 ms luôn chạy đúng giờ.

Chỉ main in thông tin, sau khi đọc từng Future. Những khoảng trễ làm rõ cách lập lịch, còn quan hệ phụ thuộc được thiết lập bằng việc nhận kết quả action trước khi gửi report.

Callable thất bại được lập lịch với delay bằng 0. IOException được quan sát qua ExecutionException, không tự ném trực tiếp từ dòng schedule trên main.

Action chỉ được schedule một lần nên tăng bộ đếm một lần. Main khai báo throws Exception để giữ ví dụ tập trung; ứng dụng thực cần xử lý thêm ngắt, timeout và thất bại tiếp nhận theo chính sách của nó.

## 7. Ngoại lệ có thể xảy ra ở hai thời điểm

### Khi lập lịch

Lời gọi schedule có thể không được tiếp nhận, chẳng hạn scheduler đã shutdown. Với chính sách từ chối mặc định của ScheduledThreadPoolExecutor, nơi gọi nhận RejectedExecutionException.

Trường hợp đó khác việc thân tác vụ chạy rồi ném lỗi.

### Khi thực hiện

Nếu thân Callable hoặc Runnable ném lỗi, đối tượng kết quả có thể hoàn tất do lỗi. Khi gọi get, nơi gọi nhận ExecutionException và kiểm tra nguyên nhân qua getCause.

Một lỗi công việc không tự khiến scheduler chạy lại công việc ấy. Schedule một lần không có cam kết retry.

Nếu Runnable cần xử lý checked exception, phải bắt bên trong hoặc chọn Callable có hợp đồng phù hợp. Không bắt rồi bỏ qua chỉ để làm mã biên dịch.

Đường quan sát lỗi, hủy và ngắt được quy định trong [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

## 8. Hủy một công việc đã lập lịch

Mã minh họa:

```java
ScheduledFuture<?> handle = scheduler.schedule(
        notification, 10, TimeUnit.MINUTES);

// Khi khong con can thong bao:
boolean accepted = handle.cancel(false);
```

Nếu hủy thành công trước khi công việc bắt đầu, công việc không nên chạy. Nếu đã chạy, false không yêu cầu ngắt luồng thực thi; không được kết luận mọi tác động đã dừng.

`cancel(true)` cho phép cố ngắt khi đang chạy, theo khả năng triển khai. Tác vụ vẫn cần hợp tác dừng; hủy không tự hoàn tác việc đã gửi thông báo hoặc cập nhật dữ liệu.

Khi Future đã hủy, get báo CancellationException.

### Hủy không đồng nghĩa lấy khỏi queue ngay

ScheduledThreadPoolExecutor mặc định có thể giữ đối tượng tác vụ đã hủy trong queue tới mốc trễ. Khi có nhiều lịch chờ lâu rồi bị hủy, điều này ảnh hưởng việc giữ tham chiếu trong bộ nhớ.

Nếu trực tiếp sở hữu ScheduledThreadPoolExecutor và chính sách phù hợp, có thể dùng:

```java
scheduler.setRemoveOnCancelPolicy(true);
```

Đoạn setter này yêu cầu biến scheduler có kiểu hoặc đối tượng truy cập được API cụ thể của ScheduledThreadPoolExecutor; nó không thuộc giao diện ScheduledExecutorService.

Không ép kiểu một scheduler từ factory bọc rồi giả định chắc chắn là lớp triển khai cụ thể. Nếu cần tùy chỉnh đặc thù, tạo và quản lý ScheduledThreadPoolExecutor trực tiếp từ đầu.

## 9. Vòng đời scheduler và tác vụ chưa tới hạn

Phải đóng scheduler khi thành phần sở hữu nó kết thúc. Nếu dùng chung do tầng khác quản lý, không tự đóng sau mỗi tác vụ.

Một điểm cần biết của ScheduledThreadPoolExecutor: mặc định các tác vụ chạy trễ đã được lập lịch vẫn được phép thực hiện sau shutdown có trật tự. Vì vậy shutdown không tự có nghĩa “bỏ mọi việc chưa tới hạn”.

Nếu thành phần không muốn chạy các lịch còn chờ sau khi đóng, phải đặt chính sách thích hợp, chẳng hạn `setExecuteExistingDelayedTasksAfterShutdownPolicy(false)`, khi trực tiếp cấu hình lớp này.

Một lịch còn một giờ mới tới hạn có thể làm quy trình chờ kết thúc kéo dài nếu chính sách giữ lịch. Cần quyết định thời hạn chờ, việc hủy và bước dừng mạnh hơn rõ ràng.

Hợp đồng giữ lịch, lấy khỏi queue khi hủy và shutdown nằm tại [ScheduledThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

Ví dụ hoàn chỉnh chỉ đóng sau khi đã thu cả ba kết quả nên không còn lịch chưa tới hạn trong đường chạy bình thường.

## 10. Công việc nặng có thể làm lịch khác trễ

Một scheduler một luồng không thể thực hiện hai thân công việc cùng lúc. Nếu một tác vụ chặn lâu, tác vụ chạy một lần khác đã đến hạn vẫn có thể phải đợi.

Có thể xem xét:

- Giữ công việc trên scheduler ngắn và có giới hạn thời gian.
- Chọn số worker phù hợp nếu công việc độc lập và cần đồng thời.
- Chuyển công việc nặng sang executor riêng khi kiến trúc thật sự cần, đồng thời kiểm soát queue, từ chối và kết quả.

Nếu chuyển việc, ScheduledFuture có thể chỉ đại diện cho thao tác chuyển, không tự đại diện cho việc nặng đã hoàn tất. Đừng in “xử lý xong” chỉ vì Future của một Runnable chuyên submit sang nơi khác đã xong.

Tương tự, không giữ worker duy nhất của scheduler để chờ một việc khác cũng cần chính scheduler ấy thực hiện; điều đó có thể tạo cạn luồng do phụ thuộc.

## 11. Lịch trong bộ nhớ không phải cam kết thực hiện bền vững

Nếu tiến trình dừng trước mốc chạy, đối tượng lịch trong bộ nhớ không tự xuất hiện lại khi ứng dụng khởi động.

Với công việc quan trọng như xử lý nghiệp vụ sau một khoảng thời gian dài, cần xác định:

- Có cần lưu bền yêu cầu lập lịch không?
- Khi khởi động lại, công việc quá hạn được xử lý thế nào?
- Có thể bị gửi hoặc thực hiện lặp không?
- Nơi nào chịu trách nhiệm đối soát trạng thái?

Một lời schedule không cung cấp sẵn tất cả các cam kết ấy. Không chọn cơ chế trong bộ nhớ rồi tuyên bố “chắc chắn thực hiện đúng một lần” chỉ từ tên phương thức.

## 12. Tự kiểm tra

1. Schedule một Callable sau hai giây có bảo đảm nó hoàn tất sau đúng hai giây không?
2. Get của ScheduledFuture từ Runnable trả gì khi thành công?
3. Delay âm có nghĩa chạy trên chính luồng gọi không?
4. Get có timeout hết hạn có tự hủy tác vụ chưa tới lịch không?
5. Shutdown có trật tự mặc định của ScheduledThreadPoolExecutor có tự bỏ hết lịch trễ đã nhận không?
6. Nếu một Runnable chỉ gửi công việc sang executor khác, Future của Runnable ấy hoàn tất có chứng minh công việc bên kia đã xong không?

**Gợi ý:** (1) Không; đó là khoảng trễ trước khi được phép chạy. (2) Null. (3) Không, chỉ là yêu cầu chạy ngay khi có thể. (4) Không. (5) Không. (6) Không.

Lập lịch một lần cần làm rõ **công việc là hành động hay phép tính có kết quả, khi nào được phép chạy, ai theo dõi ScheduledFuture và ai quản lý vòng đời scheduler**.
