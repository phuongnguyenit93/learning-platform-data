# Tác vụ chưa chạy và tác vụ đang chạy khi dừng bộ thực thi

## 1. Dừng executor là một quá trình

Khi ứng dụng không còn cần một bộ thực thi, cần quyết định số phận của các công việc đã nhận. Hai tình huống khác nhau phải được tách ra:

- **Tác vụ chưa bắt đầu**: thường đang nằm trong hàng đợi, chưa có thân công việc nào chạy.
- **Tác vụ đang chạy**: đã được luồng xử lý nhận và có thể đang tính toán, chờ I/O hoặc chờ một tài nguyên.

Một lệnh dừng không thể biến hai nhóm này thành cùng một trạng thái ngay lập tức. Xóa một việc khỏi hàng đợi dễ hơn yêu cầu một việc đang chạy dọn dẹp rồi kết thúc.

Cần phân biệt thêm **dừng nhận việc mới**, **yêu cầu các việc đang chạy dừng**, **chờ executor kết thúc** và **hủy Future**. Những thao tác này liên quan nhưng không đồng nghĩa.

## 2. shutdown và shutdownNow đối xử với tác vụ thế nào?

Với nhóm luồng thông thường như `ThreadPoolExecutor`:

| Đối tượng quan sát | Sau `shutdown()` | Sau `shutdownNow()` |
|---|---|---|
| Tác vụ gửi mới | Không được tiếp nhận theo chế độ hoạt động bình thường | Không được tiếp nhận |
| Tác vụ đã nhận, còn chờ | Tiếp tục được xử lý khi tới lượt | Cố ngăn bắt đầu; các việc lấy khỏi hàng đợi được trả về |
| Tác vụ đang chạy | Tiếp tục chạy; không bị yêu cầu ngắt chỉ vì lệnh này | Được cố gắng ngắt để dừng |
| Luồng gọi phương thức dừng | Không tự chờ mọi việc xong | Cũng không tự chờ mọi việc xong |
| Giá trị trả về | `void` | `List<Runnable>` gồm việc chưa bắt đầu được lấy ra |

`shutdown()` thường được gọi là dừng có trật tự: đóng đầu vào nhưng cho các việc đã nhận cơ hội hoàn tất.

`shutdownNow()` là yêu cầu dừng mạnh hơn, nhưng từ “Now” không phải bảo đảm mọi thân tác vụ đã dừng khi phương thức trả về. Đây là nỗ lực tốt nhất theo khả năng của triển khai; với nhóm luồng thông thường, cơ chế chủ yếu là ngắt luồng.

Hợp đồng chung được quy định trong [ExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

### Ví dụ theo dòng thời gian

Có một luồng xử lý và ba tác vụ A, B, C; A đang chạy, B và C còn chờ:

```text
Trước khi dừng:
luồng xử lý: A
hàng đợi:    B -> C

Gọi shutdown():
A tiếp tục -> B chạy -> C chạy -> executor kết thúc

Gọi shutdownNow():
A nhận yêu cầu ngắt
B và C có thể được lấy ra khỏi hàng đợi, không chạy bởi executor đó
executor chỉ kết thúc sau khi công việc đang chạy thực sự dừng
```

Đây là mô hình khi B và C vẫn còn chờ đúng lúc chuyển sang chế độ dừng. Trong thực tế, một tác vụ có thể vừa được luồng nhận trước khi lệnh dừng có hiệu lực.

## 3. Ranh giới “chưa chạy” có thể thay đổi đồng thời

Không nên làm như sau rồi cho rằng danh sách chắc chắn đầy đủ:

1. Đọc `pool.getQueue().size()`.
2. Gọi `shutdownNow()`.
3. Kết luận mọi tác vụ trong số đếm bước 1 đều chưa chạy.

Giữa các bước, một luồng có thể lấy việc khỏi hàng đợi. Một tác vụ không nằm trong danh sách trả về có thể đã được giao cho luồng, dù thân công việc chưa in dòng log đầu tiên.

Vì vậy:

- Dùng danh sách trả về để xử lý những việc **thực sự được lấy ra** bởi thao tác dừng.
- Dùng trạng thái hoặc đối tượng theo dõi của từng công việc để xác định kết quả nghiệp vụ.
- Không dùng một ảnh chụp kích thước hàng đợi làm bằng chứng chính xác cho toàn bộ diễn biến đồng thời.

Khi cần thí nghiệm có kết quả xác định, thiết lập điều kiện đồng bộ rõ ràng bằng các công cụ như `CountDownLatch`, thay vì chờ một khoảng `sleep` rồi đoán tác vụ đang ở đâu.

## 4. Ngắt luồng là yêu cầu hợp tác

`Thread.interrupt()` không có nghĩa kết thúc cưỡng bức ở dòng lệnh bất kỳ.

Một số thao tác chặn hỗ trợ ngắt, chẳng hạn `Thread.sleep`, `Object.wait`, `BlockingQueue.take` hoặc `CountDownLatch.await`, có thể ném `InterruptedException`. Tác vụ phải quyết định cách dừng và dọn dẹp phù hợp.

Một vòng lặp tính toán nên có điểm kiểm tra yêu cầu ngắt:

```java
while (!Thread.currentThread().isInterrupted()) {
    processOneUnit();
}
```

Đây là mã minh họa; `processOneUnit()` là một đơn vị công việc do ứng dụng định nghĩa. Nếu phương thức ấy tự chặn vô hạn trong một thao tác không phản hồi ngắt, kiểm tra ở đầu vòng lặp vẫn chưa đủ.

### Khi bắt InterruptedException

```java
try {
    queue.take();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
```

Đây là đoạn minh họa trong một phương thức `void`. Khôi phục cờ ngắt giúp tầng bên ngoài còn nhận biết yêu cầu dừng; `return` bảo đảm phương thức không tiếp tục xử lý như chưa có chuyện gì.

Nếu có thể truyền ngoại lệ lên nơi chịu trách nhiệm, có thể để `InterruptedException` thoát ra theo hợp đồng phương thức thay vì bắt tại đây.

Một lỗi phổ biến là bắt ngoại lệ, in log rồi quay lại vòng lặp vô hạn. Khi ấy `shutdownNow()` có thể đã gửi yêu cầu ngắt nhưng tác vụ vẫn không chịu kết thúc.

Không phải mọi I/O hoặc lời gọi thư viện đều có cùng hành vi khi ngắt. Phải kiểm tra hợp đồng của API cụ thể; có thể cần timeout của thao tác, đóng tài nguyên hoặc một cơ chế hủy do thư viện cung cấp.

Các quy tắc ngắt của luồng nằm trong [Thread API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html).

## 5. Danh sách trả về không phải kết quả nghiệp vụ

Chữ ký:

```java
List<Runnable> neverStarted = pool.shutdownNow();
```

Danh sách này không chứa kết quả của những công việc đã chạy. Nó chứa các đối tượng tác vụ được lấy ra khi chưa bắt đầu thực thi.

### execute và submit có thể tạo hình dạng đối tượng khác nhau

- Với `execute(runnable)` trên nhóm luồng thông thường, đối tượng trong hàng đợi có thể chính là `Runnable` đã gửi.
- Với `submit(callable)` hoặc `submit(runnable)`, công việc thường được bọc thành `RunnableFuture`, chẳng hạn `FutureTask`.
- Một executor tùy biến có thể dùng lớp bọc khác.

Vì vậy, không ép kiểu mọi phần tử trả về thành lớp nghiệp vụ ban đầu. Nếu cần biết công việc nào bị bỏ lại, giữ mã công việc và đối tượng theo dõi ở cấp ứng dụng ngay từ lúc tiếp nhận.

`FutureTask` đồng thời có khả năng `Runnable` và `Future`, nên có thể được đưa vào hàng đợi dưới dạng tác vụ và được nơi gọi dùng để lấy kết quả. Xem [FutureTask API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

### Không tự chạy lại mọi phần tử

Danh sách trả về chưa nói rằng công việc an toàn để thử lại. Một phần hệ thống khác có thể đã xử lý yêu cầu tương ứng; dữ liệu hoặc thời hạn công việc cũng có thể đã thay đổi.

Ứng dụng cần chọn rõ: hủy, lưu lại để xử lý sau, trả lỗi chưa thực hiện, hoặc chuyển sang bộ thực thi khác. Nếu cần thực hiện lại, phải có chính sách nhận diện công việc và chống tác động lặp thích hợp.

Hàng đợi trong bộ nhớ không trở thành nơi lưu bền chỉ vì đã gọi `shutdownNow()`.

## 6. Tác vụ được lấy khỏi hàng đợi chưa chắc có Future đã hủy

Đây là điểm dễ làm chương trình chờ vô hạn:

```java
Future<String> result = pool.submit(() -> "finished");

// Sau do, cong viec van con cho va bi lay khoi queue:
List<Runnable> neverStarted = pool.shutdownNow();
```

Với `ThreadPoolExecutor` tiêu chuẩn, việc `shutdownNow()` lấy một `FutureTask` khỏi hàng đợi **không tự đồng nghĩa gọi `cancel` trên Future đó**. Nếu không còn ai chạy hoặc hủy nó, `result.get()` không có kết quả để trả.

Không được suy luận “executor đã dừng nên mọi Future đều isDone”.

Nếu ứng dụng quyết định hủy những công việc đã lấy ra và phần tử trả về có kiểu `Future`, có thể hủy rõ ràng:

```java
for (Runnable task : neverStarted) {
    if (task instanceof Future<?> future) {
        future.cancel(false);
    }
}
```

Đoạn trên dùng cú pháp Java 17+. `false` phù hợp với các công việc đã được lấy ra và chưa chạy: không cần yêu cầu ngắt một luồng đang thực thi chúng.

Không phải mọi `Runnable` đều là `Future`; công việc gửi bằng `execute` vẫn cần cách thông báo hoặc đối soát riêng nếu nghiệp vụ yêu cầu.

## 7. Tác vụ đang chạy có thể kết thúc theo nhiều cách

Sau yêu cầu dừng mạnh hơn, không chỉ có một kết quả “cancelled”:

| Hành vi trong tác vụ | Kết quả có thể quan sát |
|---|---|
| Hoàn tất ngay trước khi được ngắt | Future có kết quả thành công |
| Bắt yêu cầu ngắt, dọn dẹp rồi trả một giá trị | Future có thể hoàn tất bình thường với giá trị đó |
| Ném ngoại lệ ra ngoài thân tác vụ gửi bằng `submit` | `get()` có thể báo `ExecutionException` |
| Được hủy thành công bằng `Future.cancel(...)` | `get()` báo `CancellationException` |
| Phớt lờ ngắt hoặc kẹt ở thao tác không phản hồi | Thân tác vụ có thể tiếp tục chạy |

`shutdownNow()` tác động tới executor và luồng xử lý; `Future.cancel(true)` là yêu cầu hủy một tác vụ cụ thể, có thể kèm yêu cầu ngắt khi đang chạy.

Ngay cả khi hủy Future thành công và `isDone()` là `true`, không nên coi đó là chứng cứ rằng mọi mã trong thân tác vụ đã dừng tại cùng thời điểm. Việc dừng vật lý vẫn phụ thuộc khả năng hợp tác của tác vụ.

Ngược lại, tác vụ có thể phản hồi ngắt rồi trả một giá trị; nếu Future không bị hủy, nơi gọi nhận giá trị ấy. Chương trình ở phần tiếp theo thể hiện chính tình huống này.

## 8. Chương trình hoàn chỉnh: một việc đang chạy và một việc còn chờ

Lưu thành **`ExecutorStopDemo.java`**, dùng Java 17+:

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ExecutorStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> running = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                    return "released";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "interrupted";
                }
            });

            started.await();
            Future<String> queued = pool.submit(() -> "queued ran");

            List<Runnable> neverStarted = pool.shutdownNow();

            System.out.println("not started: " + neverStarted.size());
            System.out.println(
                    "queued done before cancel: " + queued.isDone());

            for (Runnable task : neverStarted) {
                if (task instanceof Future<?> future) {
                    future.cancel(false);
                }
            }

            System.out.println(
                    "queued cancelled: " + queued.isCancelled());
            System.out.println(
                    "running: " + running.get(5, TimeUnit.SECONDS));

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
            System.out.println("terminated: " + pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ExecutorStopDemo.java
java ExecutorStopDemo
```

Stdout chính xác:

```text
not started: 1
queued done before cancel: false
queued cancelled: true
running: interrupted
terminated: true
```

### Vì sao kết quả không phụ thuộc sleep?

Executor chỉ có một luồng. Tác vụ đầu thông báo đã bắt đầu bằng `started.countDown()`, rồi chờ tại `release.await()`. Luồng `main` chỉ gửi tác vụ thứ hai sau khi đã nhận thông báo ấy.

Chốt `release` chưa được mở trong lúc dừng. Do đó tác vụ thứ hai không thể được luồng duy nhất nhận để chạy trước `shutdownNow()`; nó được lấy ra khỏi hàng đợi.

Tác vụ đầu phản hồi ngắt bằng cách trả `"interrupted"`. Future của nó không bị gọi `cancel`, nên `get()` nhận một giá trị bình thường. Future của tác vụ thứ hai chỉ chuyển sang trạng thái hủy khi vòng lặp gọi `cancel(false)`.

Nếu gọi `queued.get()` sau khi hủy, nó sẽ ném `CancellationException`, không trả `"queued ran"`. Trong ví dụ, thân tác vụ thứ hai chưa bao giờ thực hiện.

Các timeout năm giây giúp chương trình báo lỗi nếu điều kiện thực thi không tiến triển như dự kiến. Chúng không phải cơ chế xác định thứ tự. `main` khai báo `throws Exception` để tập trung vào hành vi dừng; ứng dụng thực cần chính sách xử lý các lỗi chờ kết quả.

## 9. Chờ kết thúc phải là bước riêng

Các trạng thái quan sát cần phân biệt:

- `isShutdown()`: đã bắt đầu đóng đầu vào; không nói mọi công việc đã kết thúc.
- `isTerminated()`: executor đã kết thúc sau yêu cầu dừng.
- `awaitTermination(timeout, unit)`: chờ kết thúc, trả `true` nếu đã kết thúc, `false` nếu hết khoảng chờ.

Gọi `awaitTermination` không tự yêu cầu shutdown. Nó cũng không hủy công việc khi hết timeout.

Quy trình thường dùng:

1. Ngừng nguồn tạo công việc mới.
2. Gọi `shutdown()`.
3. Chờ một khoảng phù hợp để việc đã nhận hoàn tất.
4. Nếu chưa xong, gọi `shutdownNow()`.
5. Xử lý danh sách chưa bắt đầu và các đối tượng theo dõi công việc.
6. Chờ thêm theo thời hạn và báo rõ nếu vẫn chưa kết thúc.

Nếu luồng đang thực hiện quy trình chờ bị ngắt, cần quyết định phản hồi ngắt, thường là yêu cầu dừng mạnh hơn rồi phục hồi cờ ngắt hoặc truyền ngoại lệ. Không bắt ngắt rồi tiếp tục chờ mãi.

Nếu vẫn có việc không chịu dừng, cần ghi nhận và xử lý nguyên nhân như I/O không có timeout hoặc vòng lặp không kiểm tra ngắt; gọi `shutdownNow()` liên tiếp không biến yêu cầu hợp tác thành bảo đảm cưỡng bức.

## 10. Ngoại lệ cần biết khi làm với scheduler

Không áp dụng mọi chi tiết của nhóm luồng thông thường cho mọi bộ thực thi mà không kiểm tra hợp đồng.

Với `ScheduledThreadPoolExecutor`, hành vi sau `shutdown()` còn phụ thuộc các chính sách:

- Mặc định, các công việc chạy trễ đã được lập lịch vẫn được phép chạy.
- Mặc định, các lần chạy tiếp theo của công việc định kỳ không tiếp tục sau shutdown.
- Có thể thay đổi bằng `setExecuteExistingDelayedTasksAfterShutdownPolicy` và `setContinueExistingPeriodicTasksAfterShutdownPolicy`.

Một công việc trễ còn xa trong tương lai có thể khiến quá trình kết thúc kéo dài nếu chính sách vẫn giữ nó. Vì vậy, thời hạn chờ đóng và chính sách lịch phải được thiết kế cùng nhau.

`shutdownNow()` vẫn cố gắng ngăn công việc chờ và ngắt việc đang chạy, nhưng không nên giả định mọi đối tượng trong danh sách trả về chính là `Runnable` gốc: scheduler dùng các đối tượng bọc để quản lý lịch.

Xem [ScheduledThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ScheduledThreadPoolExecutor.html).

## 11. Dừng luồng không hoàn tác tác động đã xảy ra

Một tác vụ đang gửi dữ liệu, ghi tệp hoặc cập nhật cơ sở dữ liệu có thể đã thực hiện một phần trước khi nhận yêu cầu ngắt.

Hủy hoặc shutdown không tự:

- Thu hồi một thông báo đã được gửi.
- Xóa một phần tệp đã ghi.
- Hoàn tác thay đổi đã commit.
- Bảo đảm lời gọi dịch vụ ngoài chưa được xử lý.

Tác vụ phải thiết kế việc giải phóng tài nguyên trong `finally` hoặc try-with-resources, và nghiệp vụ cần cơ chế giao dịch, đối soát hoặc chống tác động lặp khi phù hợp.

Nếu thử lại một công việc sau khi dừng, “không nhận được kết quả” không đủ để kết luận “công việc chưa tạo tác động”.

## 12. Tự kiểm tra

1. `shutdown()` có ngắt tác vụ đang chạy và xóa việc chờ không?
2. `shutdownNow()` trả về có chứng minh mọi luồng đã kết thúc không?
3. Vì sao một Future của việc lấy khỏi queue có thể vẫn chưa hoàn tất?
4. Tác vụ bắt `InterruptedException` rồi trả `"stopped"` có nhất thiết tạo Future ở trạng thái hủy không?
5. `awaitTermination` trả `false` có tự hủy công việc còn lại không?
6. Sau khi một công việc cập nhật dữ liệu bị ngắt, có thể thử lại mà không kiểm tra tác động cũ không?

**Gợi ý:** (1) Không; việc đã nhận tiếp tục được xử lý theo chế độ có trật tự. (2) Không. (3) Lấy ra không nhất thiết gọi `cancel`. (4) Không; nếu không bị hủy, nó có thể trả kết quả bình thường. (5) Không. (6) Không; cần kiểm tra hoặc thiết kế nghiệp vụ phù hợp.

Khi dừng executor, phải theo dõi riêng **việc chưa bắt đầu, việc đang chạy, trạng thái Future và thời điểm executor thực sự kết thúc**.
