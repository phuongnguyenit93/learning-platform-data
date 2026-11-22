# Giới hạn của timeout và cancellation đối với tác vụ bên dưới

## 1. Vấn đề: hết thời gian chờ không đồng nghĩa công việc đã dừng

Một chương trình Java thường gửi công việc bất đồng bộ tới `ExecutorService` hoặc `CompletableFuture` rồi giới hạn thời gian chờ kết quả. Nếu quá hạn, caller có thể nhận `TimeoutException` hoặc yêu cầu hủy bằng `Future.cancel(true)`. Tuy nhiên hai hành động này nói về **khả năng quan sát và điều phối công việc**, không phải một cam kết mọi phép tính, I/O hoặc side effect bên dưới đều đã dừng.

Cần tách rõ bốn sự kiện:

1. **Caller ngừng chờ**: luồng gọi thoát khỏi `get(timeout, unit)` vì chưa có kết quả đúng hạn.
2. **Handle được đánh dấu hủy hoặc hoàn thành lỗi**: trạng thái `Future`/`CompletableFuture` có thể chuyển thành terminal.
3. **Worker thực sự ngừng chạy**: thread thực thi đã kết thúc, thường cần tác vụ hợp tác với interruption, deadline hoặc một cơ chế hủy riêng.
4. **Tác động bên ngoài đã dừng/được phục hồi**: cơ sở dữ liệu, file, HTTP service hoặc thanh toán không còn thay đổi; mức bảo đảm này cần cơ chế riêng.

Những sự kiện trên **không thể hoán đổi ý nghĩa**. Ví dụ: `future.get(100, MILLISECONDS)` ném `TimeoutException`, nhưng worker vẫn gửi request và nhận phản hồi sau đó. Hoặc `future.cancel(true)` trả `true`, trong khi worker bỏ qua interrupt và tiếp tục ghi file. Hoặc `CompletableFuture.orTimeout` đã làm stage hoàn thành bằng `TimeoutException`, nhưng supplier đang chạy trong executor vẫn hoàn tất tác động phụ.

Sau bài này, bạn sẽ:
- Hiểu chính xác hợp đồng `Future.get(timeout)`, `Future.cancel`, `CompletableFuture.orTimeout` và `completeOnTimeout` trong Java 17+.
- Phân biệt timeout của caller, timeout của API I/O, interruption, cancellation và trạng thái kết quả phía remote.
- Thiết kế task hỗ trợ hủy hợp tác và dọn tài nguyên đúng quyền sở hữu.
- Đánh giá race condition, kết quả chưa xác định và nguy cơ side effect lặp lại khi retry.
- Viết test xác nhận **worker dừng thật** và trạng thái hậu xử lý, thay vì chỉ xác nhận Future có cờ `isCancelled`.

## 2. Mô hình thời gian: caller và worker không dùng chung một điểm dừng

Giả sử caller cần kết quả trong 200 ms, còn worker đang tải dữ liệu:

~~~text
Thời điểm       Caller                              Worker
t0              submit -> Future                    được lên lịch
t1              get(200 ms)                         đang gửi HTTP
t2              TimeoutException                    vẫn chờ máy chủ
t3              caller trả "quá hạn"                 máy chủ đã xử lý xong
t4              caller có thể retry                  worker nhận response
t5              ...                                  cập nhật trạng thái/file
~~~

Dòng thời gian chỉ minh họa, không phải lời hứa về thời điểm thực tế. Lệnh `get(timeout)` giới hạn **thời gian caller đợi lời gọi đó**. Nó không cài một đồng hồ bắt buộc dừng CPU, Java thread, socket, database query hay remote service.

Cùng một thao tác có thể có nhiều deadline khác nhau:
- **Request timeout** tại tầng HTTP đầu vào.
- **Timeout chờ kết quả** trong `Future.get(timeout, unit)`.
- **Connect timeout**, **read timeout** hoặc **request timeout** trong HTTP/JDBC client.
- **Deadline của toàn tác vụ** do ứng dụng truyền xuống các bước con.
- **Timeout của hệ thống xa** hoặc transaction tại database.
- **Thời hạn retry** của một policy bên ngoài.

Muốn người dùng nhận một kết quả đúng hạn **và** hạn chế tác vụ chạy quá lâu, phải phối hợp các cơ chế tương ứng. Chỉ bọc `get` bằng timeout là chưa đủ.

## 3. `Future.get(timeout, unit)` chỉ giới hạn thời gian chờ

Ví dụ:

~~~java
Future<String> future = executor.submit(this::loadData);
String value = future.get(500, TimeUnit.MILLISECONDS);
~~~

Đây là fragment, giả định `executor`, `loadData` và các import đã tồn tại; phương thức chứa nó cần xử lý `InterruptedException`, `ExecutionException`, `TimeoutException`. Nếu quá 500 ms mà Future chưa có kết quả, `get` có thể ném `TimeoutException`. **Future có thể vẫn đang chạy và chưa bị hủy**.

### Các kết cục của `get(timeout, unit)`

| Kết cục quan sát | Ý nghĩa | Có chứng minh worker đã dừng? |
| --- | --- | --- |
| Trả `T` | Future hoàn thành bình thường, có kết quả | Tác vụ mà Future đại diện đã hoàn thành; không bảo đảm side effect bên ngoài đã được đảo ngược |
| `ExecutionException` | Task hoàn thành ngoại lệ; nguyên nhân ở `getCause()` | Task được Future quản lý đã hoàn tất bằng lỗi; công việc phụ nó tạo ra có thể còn chạy |
| `TimeoutException` | Không nhận được kết quả trong khoảng chờ | **Không** |
| `InterruptedException` | Thread đang chờ bị interrupt | **Không** |
| `CancellationException` | Future đã hủy khi caller lấy kết quả | **Không nhất thiết**; task bên dưới có thể chưa thực sự dừng |

Gọi `future.isDone()` sau timeout cũng cần hiểu đúng: `true` bao gồm thành công, thất bại và hủy. Không suy ra thành công chỉ từ cờ đó. `isCancelled()` chỉ nói Future ở trạng thái hủy theo hợp đồng, không kiểm chứng các tài nguyên bên ngoài.

**Không được viết logic** “`get` timeout nên chắc chắn chưa có đơn hàng” hoặc “timeout nên retry ngay POST tạo đơn mới” khi công việc cũ có thể vẫn đang xử lý.

## 4. `Future.cancel(boolean)` là một yêu cầu hủy, không phải kill an toàn

`Future.cancel(mayInterruptIfRunning)` thử chuyển công việc sang trạng thái hủy. Nó có thể trả `false` khi không thể hủy, chẳng hạn task đã hoàn thành; `true` nói yêu cầu hủy Future thành công theo hợp đồng. Sự thành công này không có nghĩa thread đang chạy đã ngừng tức thì.

### 4.1. `cancel(false)` so với `cancel(true)`

| Lời gọi | Ý nghĩa quan trọng | Điều không bảo đảm |
| --- | --- | --- |
| `cancel(false)` | Cố hủy nhưng **không yêu cầu interrupt** nếu task đã chạy | Không bắt worker đang chạy dừng ngay |
| `cancel(true)` | Cố hủy và cho phép yêu cầu interrupt thread đang chạy | Không ép tác vụ không hợp tác ngừng; không rollback side effect |
| `get()` sau Future đã hủy | Ném `CancellationException` | Không nói worker/remote có còn đang chạy không |
| `isCancelled()` | Kiểm tra trạng thái Future đã hủy | Không xác nhận I/O hay hiệu ứng bên ngoài đã dừng |

`cancel(true)` thường tác động qua **interruption** nếu triển khai Future/Executor hỗ trợ điều đó. Nhưng interruption của Java là cơ chế hợp tác: nó đặt cờ interrupt hoặc khiến một số API blocking ném `InterruptedException`. Nó không phải một lệnh cưỡng chế dừng mọi loại tác vụ.

Trong một số tác vụ đang chạy, kết quả Future có thể được đánh dấu hủy trong khi worker vẫn tiếp tục một đoạn, thậm chí chạy tới cuối vì không kiểm tra interrupt. Sau khi Future bị hủy, `get()` không còn trả giá trị tính toán bình thường của worker, cho dù worker có làm xong sau đó.

### 4.2. Vì sao `Thread.stop()` không phải lời giải?

Không nên dùng `Thread.stop()` để cố cưỡng chế hủy vì API này bị deprecated vì không an toàn: nó có thể làm thread dừng tại thời điểm bất kỳ, để lại đối tượng chia sẻ/invariant trong trạng thái không nhất quán và gây hậu quả khó kiểm soát. Ngắt hợp tác, chính sách timeout của I/O và thiết kế task có điểm dừng an toàn mới là hướng cần học.

## 5. Interruption chỉ có tác dụng khi code bên dưới hợp tác

Trong Java, `Thread.interrupt()` thể hiện **một yêu cầu**. Tác vụ phải biết quan sát và phản hồi. Hai loại phản hồi phổ biến:

1. Với API interruptible blocking như `Thread.sleep`, `Object.wait`, `Thread.join` hoặc các thao tác `BlockingQueue` phù hợp, thread có thể bị đánh thức bằng `InterruptedException`.
2. Với vòng lặp tính toán hoặc thao tác không tự ném `InterruptedException`, code cần kiểm tra `isInterrupted()` hoặc một cancellation token/flag có quan hệ bộ nhớ đúng.

Mẫu task hợp tác:

~~~java
Runnable worker = () -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            processOneBatch();
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
        }
    }
};
~~~

Đây là fragment minh họa; `processOneBatch()` chưa định nghĩa, và cần có chính sách cho exception khác của chính tác vụ. Nếu `processOneBatch()` mất hàng phút và không hỗ trợ hủy, vòng lặp chỉ kiểm tra interrupt **sau khi hàm đó trở về**. Do vậy phải đặt điểm kiểm tra ở các vùng xử lý dài hoặc truyền deadline/cancellation vào API con có hỗ trợ.

### 5.1. Cờ interrupt và `InterruptedException`

Các thao tác blocking ném `InterruptedException` thường xóa interrupt status trong quá trình ném. Nếu code bắt exception này mà không thể khai báo `throws InterruptedException`, mẫu thường đúng là **khôi phục cờ** rồi kết thúc tác vụ:

~~~java
try {
    queue.put(item);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Đây là fragment minh họa nằm trong phương thức trả `void`, có `queue` và `item` được khai báo. Nếu nuốt exception rồi tiếp tục, hệ thống shutdown/cancel có thể không dừng được công việc. Nếu chữ ký phương thức cho phép `throws InterruptedException`, có thể truyền tiếp lỗi thay vì tự xử lý.

Cần phân biệt:
- `isInterrupted()` kiểm tra trạng thái của thread, **không xóa cờ**.
- `Thread.interrupted()` (static) kiểm tra trạng thái interrupt của **thread hiện tại** và **xóa cờ**.
- `Thread.currentThread().interrupt()` đặt lại cờ cho thread hiện tại.

Không gọi `Thread.interrupted()` trong điều kiện lặp một cách vô tình rồi đánh mất yêu cầu hủy nếu logic sau đó còn cần biết.

### 5.2. Những thao tác không nhất thiết ngắt ngay

Nhiều tác vụ không phản hồi hoặc chỉ phản hồi gián tiếp với interruption:
- Vòng lặp CPU-bound không kiểm tra cờ.
- Một đoạn native code, thư viện bên ngoài hoặc API blocking không công bố hành vi interrupt.
- Chờ giành intrinsic monitor của khối `synchronized` theo cơ chế truyền thống: một yêu cầu interrupt không tự phá việc chờ monitor.
- Gọi I/O có timeout/semantics riêng: không suy luận mọi socket, JDBC call, file operation đều lập tức ném `InterruptedException`.
- Remote HTTP request đã tới server: ngắt client không tự khiến server đảo thao tác.
- Đoạn code bắt `InterruptedException` nhưng bỏ qua rồi tiếp tục.

Một số API có cách phản hồi interrupt khác nhau, ví dụ có thể ném một unchecked exception/đóng channel/cập nhật trạng thái; hãy dựa vào hợp đồng của **API cụ thể**. Không hứa rằng mọi thư viện I/O đều phản hồi như `Thread.sleep`.

### 5.3. Hủy hợp tác và cleanup

Khi worker nhận yêu cầu hủy, nó thường cần dọn **tài nguyên do nó sở hữu**: đóng stream, giải phóng lock, xóa file tạm, rollback transaction chưa commit. Dùng `try/finally` và `try-with-resources` ở phạm vi phù hợp.

Tuy nhiên `finally` không phải rollback tự động. Nếu worker đã gửi email hoặc DB đã commit, cleanup sau interrupt không thu hồi hành động đó. Hơn nữa, nếu cleanup bản thân bị blocking không interruptible thì việc phản hồi hủy vẫn có thể chậm; nếu dọn dẹp ném exception, cần bảo toàn nguyên nhân chính theo chính sách ghi nhận lỗi.

## 6. Ví dụ Java 17 hoàn chỉnh: nhìn thấy ba giới hạn

Chương trình sau cố ý dùng `CountDownLatch` để kiểm soát thời điểm worker được phép tiếp tục, thay vì dựa vào thứ tự scheduling ngẫu nhiên.

1. `Future.get(timeout)` quá hạn nhưng Future vẫn chưa xong; mở latch, worker hoàn thành và caller lấy được kết quả.
2. `Future.cancel(true)` hủy một task đang ngủ; trong trường hợp này, `Thread.sleep` hợp tác với interrupt nên worker nhận `InterruptedException`. Dù worker trả về một chuỗi sau catch, `Future.get()` của Future đã hủy vẫn ném `CancellationException`.
3. `CompletableFuture.orTimeout` hoàn thành future bằng `TimeoutException` trong khi supplier vẫn chờ latch. Sau khi thả latch, worker hoàn tất, dù future đã ở trạng thái lỗi.

Lưu thành **`TimeoutCancellationLimitsDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutCancellationLimitsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CountDownLatch entered = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            Future<String> task = pool.submit(() -> {
                entered.countDown();
                release.await();
                return "work result";
            });
            entered.await();
            try {
                task.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("get timed out");
            }
            System.out.println("after timeout, done=" + task.isDone());
            release.countDown();
            System.out.println("later result=" + task.get());

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch stopped = new CountDownLatch(1);
            AtomicBoolean noticedInterrupt = new AtomicBoolean();
            Future<String> cancellable = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(Long.MAX_VALUE);
                    return "normal";
                } catch (InterruptedException e) {
                    noticedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "stopped";
                } finally {
                    stopped.countDown();
                }
            });
            started.await();
            boolean accepted = cancellable.cancel(true);
            stopped.await();
            System.out.println("cancel returned=" + accepted);
            System.out.println("worker noticed interrupt=" + noticedInterrupt.get());
            try {
                cancellable.get();
            } catch (CancellationException e) {
                System.out.println("cancelled future has no result");
            }

            CountDownLatch stageStarted = new CountDownLatch(1);
            CountDownLatch stageRelease = new CountDownLatch(1);
            CountDownLatch stageFinished = new CountDownLatch(1);
            CompletableFuture<String> stage = CompletableFuture.supplyAsync(() -> {
                stageStarted.countDown();
                try {
                    stageRelease.await();
                    return "stage result";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "interrupted";
                } finally {
                    stageFinished.countDown();
                }
            }, pool);
            stageStarted.await();
            stage.orTimeout(30, TimeUnit.MILLISECONDS);
            try {
                stage.join();
            } catch (CompletionException e) {
                System.out.println("stage result=" + e.getCause().getClass().getSimpleName());
            }
            stageRelease.countDown();
            stageFinished.await();
            System.out.println("stage worker completed=" + (stageFinished.getCount() == 0));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn từ thư mục chứa file:

~~~bash
javac --release 17 TimeoutCancellationLimitsDemo.java
java TimeoutCancellationLimitsDemo
~~~

Stdout dự kiến khi chương trình được chạy bình thường, không bị môi trường ngắt đột ngột:

~~~text
get timed out
after timeout, done=false
later result=work result
cancel returned=true
worker noticed interrupt=true
cancelled future has no result
stage result=TimeoutException
stage worker completed=true
~~~

### 6.1. Vì sao các dòng kết quả có ý nghĩa?

**Phần Future chờ timeout:** `entered.await()` bảo đảm task đã vào vùng chờ trên `release`. Do latch chưa được mở, `get(30 ms)` không thể nhận kết quả thành công, vì vậy ném `TimeoutException`. Lúc này Future chưa xong; khi main gọi `release.countDown()`, task tiếp tục và trả `work result`. Mốc timeout đã trôi qua nhưng worker vẫn có thể hoàn tất thành công.

**Phần cancel:** `started.await()` bảo đảm worker thực sự đã vào task. `cancel(true)` yêu cầu hủy; vì worker đang `Thread.sleep(Long.MAX_VALUE)`, interrupt được phản hồi qua `InterruptedException`. `stopped.await()` chờ worker chạy xong khối `finally` trước khi in cờ; do đó dòng `worker noticed interrupt=true` không dựa vào race đọc sớm. Future đã hủy không trả `"stopped"` qua `get()`, dù worker có thể kết thúc logic catch và trả giá trị đó nội bộ.

**Phần CompletableFuture:** supplier đợi `stageRelease`. `stage.orTimeout(30 ms)` làm chính future hoàn thành ngoại lệ nếu chưa xong trong khoảng thời gian đó; `join()` quan sát `CompletionException` chứa `TimeoutException`. Main chỉ sau đó mới mở `stageRelease`. `stageFinished.await()` chứng minh supplier đi hết `finally`. Dòng cuối không nói là giá trị `stage result` đã được xuất bản vào future: future đã hoàn tất bằng lỗi trước đó.

Ví dụ là một **thí nghiệm có điều phối bằng latch**, không phải một chiến lược timeout cho production. `await()` không timeout trong những chỗ có chủ đích vì main đã biết điểm cấp tín hiệu trong thí nghiệm; test và ứng dụng thực nên dùng thời hạn tổng, có lối thoát và cleanup phù hợp khi gặp lỗi bất thường.

## 7. `CompletableFuture.orTimeout` và `completeOnTimeout`

Java 9+ có hai API tiện dụng, đều dùng được trên Java 17:

~~~java
CompletableFuture<T> limited = original.orTimeout(2, TimeUnit.SECONDS);
CompletableFuture<T> defaulted = original.completeOnTimeout(fallback, 2, TimeUnit.SECONDS);
~~~

Đây là **cú pháp minh họa**, giả định `T`, `original`, `fallback` đã khai báo. Trong hai ví dụ, phương thức được gọi trên `original` **trả chính CompletableFuture đó**; nếu viết liên tiếp trên cùng một object thì có thể có sự cạnh tranh giữa hai chính sách, không có hai handle độc lập như tên biến gợi ý. Khi deadline tới và future chưa hoàn thành:

- `orTimeout` cố hoàn thành chính CompletableFuture **ngoại lệ** với `TimeoutException`.
- `completeOnTimeout` cố hoàn thành chính CompletableFuture **bình thường với giá trị dự phòng**.

Chúng **không tự động hủy hoặc interrupt supplier đang chạy** chỉ vì future bị hoàn thành do timeout. Đối với `CompletableFuture.supplyAsync`, một phép tính đang thực thi có thể tiếp tục trên executor ngay cả khi CompletableFuture đã có kết quả timeout. Nếu muốn ngắt nguồn, cần thiết kế một handle/cơ chế hủy thật sự cho nguồn đó và hiểu tính hợp tác của nguồn.

### 7.1. Timeout làm thay đổi handle chia sẻ

Khi nhiều caller cùng giữ reference đến **một** `CompletableFuture`, lời gọi `orTimeout` trên shared future có thể làm **cả những caller khác** nhìn thấy future đó hoàn thành bằng timeout. Đây là thay đổi trạng thái của đối tượng Future, không chỉ “tôi không muốn chờ nữa”.

Nếu cần timeout riêng cho từng caller mà không làm thay đổi kết quả chung, nên dùng một cơ chế giới hạn **việc chờ của caller** (ví dụ `get(timeout)`) hoặc tạo một dependent stage thích hợp rồi áp dụng timeout lên stage riêng. Cần chú ý vòng đời và việc lan truyền cancellation từ stage phụ về nguồn **không tự động được bảo đảm** chỉ vì hai stage liên kết với nhau.

### 7.2. `completeOnTimeout` có thể che trạng thái công việc vẫn đang xử lý

Ví dụ:

~~~java
CompletableFuture<String> displayed =
        CompletableFuture.supplyAsync(() -> remoteSave())
                .completeOnTimeout("pending", 1, TimeUnit.SECONDS);
~~~

Đây là fragment với `remoteSave()` chưa định nghĩa; cần import `CompletableFuture` và `TimeUnit`. Nếu sau 1 giây supplier vẫn đang chạy, `displayed.join()` có thể trả `pending`. Điều đó chỉ nói rằng **một giá trị mặc định đã được dùng làm kết quả cho future**. Không chứng minh remote write đã dừng, chưa bắt đầu, không tạo side effect hay sẽ thành công về sau.

Không nên đặt fallback `"saved"` cho một tác vụ lưu dữ liệu chưa biết kết quả, vì sẽ tạo thông báo sai. Một trạng thái như `PENDING`/`UNKNOWN` có thể phù hợp hơn nếu hệ thống có job ID và đường tra cứu hậu xử lý.

### 7.3. `CompletableFuture.cancel(true)` khác `FutureTask.cancel(true)`

`CompletableFuture` triển khai `Future` nhưng không trực tiếp kiểm soát thread đã khởi chạy phép tính. Theo hợp đồng Java, tham số `mayInterruptIfRunning` trong `CompletableFuture.cancel(boolean)` **không có tác dụng điều khiển interrupt đối với chính implementation này**. Lời gọi làm future hoàn thành ngoại lệ bằng `CancellationException` nếu còn có thể hủy; nó không bảo đảm interrupt supplier chạy bởi `supplyAsync`.

Không được suy từ `CompletableFuture.cancel(true)` rằng mã bên trong `supplyAsync` đã nhận interrupt như ví dụ `Future` được trả từ `ExecutorService.submit()`. Đây là khác biệt rất thực tế giữa hai cơ chế có chung interface `Future`.

## 8. Cancellation có race condition với hoàn tất bình thường

Một tác vụ có thể hoàn thành gần đúng lúc caller yêu cầu hủy:

~~~text
Tình huống A:
worker hoàn thành -> Future nhận result -> cancel() trả false

Tình huống B:
cancel() đánh dấu canceled -> worker có thể vẫn chạy ->
get() của Future đã hủy ném CancellationException

Tình huống C:
caller get(timeout) hết hạn -> worker hoàn thành ngay sau đó ->
caller thấy timeout ở lần chờ cũ, kết quả có thể đã sẵn sàng
~~~

Cả ba đều có thể xảy ra. Không có một phép kiểm tra `isDone()` rồi `cancel()` tách biệt nào biến hai thao tác thành một giao thức atomic “nếu chưa xong thì đảm bảo dừng”. Sau timeout, task có thể hoàn thành trước khi caller gọi hủy; lúc đó cancel thất bại nhưng kết quả có thể đã được ghi vào Future.

**Đừng viết logic nghiệp vụ dựa trên suy diễn từ thứ tự ở độ phân giải milli giây.** Hãy xây các nhánh rõ:
- `cancel` trả `false` thì task có thể đã hoàn tất hoặc hủy không thành công; đọc lại trạng thái có quản lý phù hợp.
- `cancel` trả `true` thì trạng thái Future đã hủy, nhưng công việc/side effect bên dưới vẫn cần một kênh xác minh riêng nếu yêu cầu.
- `get` timeout thì caller chưa nhận được kết quả trong thời hạn, không phải kết luận cuối của task.

Nếu một request có tiền thật hoặc tài nguyên quan trọng, trạng thái `UNKNOWN` thường an toàn hơn khẳng định thất bại tuyệt đối.

## 9. Timeout của I/O không đồng nghĩa rollback ở phía server

Một HTTP client có thể timeout khi:
- Không kết nối được đến server trong khoảng quy định.
- Đang đợi nhận dữ liệu từ server.
- Request tổng thể vượt quá deadline.
- Một tầng proxy/load balancer ngắt kết nối.
- Client bị interrupt hoặc hủy theo cơ chế riêng của thư viện.

Từ góc nhìn caller, timeout ở tầng nhận phản hồi **không phân biệt chắc**:
1. Request chưa rời khỏi client.
2. Request đã tới server nhưng chưa được thực thi.
3. Server đã thực thi và commit, nhưng response bị thất lạc.
4. Server đang tiếp tục thực thi sau khi client ngừng chờ.

Tương tự, một JDBC query timeout hoặc việc cancel statement là **yêu cầu điều khiển** được chuyển tới driver/database theo khả năng hỗ trợ, không phải chứng cứ mọi thao tác liên quan đã rollback. Cần kiểm tra transaction, isolation, auto-commit, loại lệnh và trạng thái commit theo hợp đồng của driver/database. Lỗi xảy ra đúng lúc `commit` có thể tạo kết quả **không chắc chắn**: server đã commit nhưng client chưa nhận được xác nhận.

### 9.1. Rủi ro double side effect khi retry sau timeout

Ví dụ quy trình thanh toán:

~~~text
Client gửi POST /charge, requestId=abc
    -> service nhận request và ghi thanh toán
Client hết timeout, chưa nhận response
Client retry POST /charge với requestId mới
    -> service tạo thêm một giao dịch
~~~

Đây là lỗi thiết kế. Khi một thao tác có side effect, nên dùng **idempotency key ổn định cho cùng yêu cầu logic**, kết hợp với quy tắc server hỗ trợ và truy vấn trạng thái để tránh tạo hiệu ứng trùng. Chỉ gắn header có tên `Idempotency-Key` mà server không lưu/tránh trùng ở mức atomic sẽ không tạo bảo đảm.

Một chiến lược thực tế:
1. Tạo `operationId` một lần trước yêu cầu đầu.
2. Gửi lại **cùng ID và payload hợp lệ** khi retry theo hợp đồng remote API.
3. Nếu timeout, tra cứu trạng thái bằng ID trước hoặc theo quy định của server.
4. Trả một trạng thái có cấu trúc như `PENDING`/`UNKNOWN` nếu chưa thể xác định.
5. Ghi nhận để reconciliation/đối soát khi kết quả cuối không thể xác nhận ngay.

Không retry vô hạn hoặc retry đồng thời nhiều request khi không biết cơ chế chống lặp của phía nhận. Nếu tác vụ thuộc job nền có tính bền vững qua restart, handle `Future` trong bộ nhớ là chưa đủ; cần kho trạng thái job/queue bền vững hoặc hệ thống điều phối phù hợp.

## 10. Truyền deadline xuống các bước bên dưới

Đối với một request có ngân sách tổng là 2 giây, cho ba lời gọi con mỗi lời chờ 2 giây có thể làm tổng thời gian vượt xa giới hạn. Cần phân bổ một **deadline chung** rồi truyền thời gian còn lại xuống từng bước.

Ví dụ ý tưởng Java:

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

// Trước mỗi bước:
long remaining = deadline - System.nanoTime();
if (remaining <= 0) {
    throw new TimeoutException("overall deadline exceeded");
}
String value = future.get(remaining, TimeUnit.NANOSECONDS);
~~~

Đây là fragment, cần import `TimeUnit`, `TimeoutException` và xử lý các checked exception khác từ `get`. `System.nanoTime()` thích hợp để **đo khoảng thời gian trôi qua** trong một tiến trình, không phải timestamp để ghi nhật ký hoặc đồng bộ với service ngoài. Với deadline cực lớn có thể cần xử lý vấn đề tràn số; với timeout nghiệp vụ thông thường và khoảng giới hạn hợp lý, mẫu này minh họa được nguyên tắc dùng ngân sách còn lại.

Nếu tầng HTTP client hỗ trợ request timeout riêng, hãy truyền `remaining` (hoặc mức nhỏ hơn phù hợp) vào client. Nếu database driver có query timeout hoặc API cancellation riêng, cấu hình đúng theo hợp đồng. Tuy vậy, ngay cả việc lan truyền deadline đầy đủ cũng chỉ **giới hạn thời gian chờ/cố gắng kết thúc**, không tạo bảo đảm remote side effect sẽ bị hoàn tác.

### 10.1. Có phải luôn phải cancel khi timeout?

Không. Caller có thể:
- **Chỉ thôi chờ** và để một job dùng chung tiếp tục chạy, ví dụ tác vụ cache warm-up.
- **Yêu cầu hủy** nếu công việc không còn giá trị, caller sở hữu quyền hủy và task hỗ trợ dừng.
- **Chuyển sang chế độ nền** với job ID và trạng thái theo dõi khi không thể dừng an toàn.
- **Đối soát trạng thái bên ngoài** nếu tác vụ đã gửi yêu cầu có side effect và chưa biết kết quả.

Hủy tự động một Future đang được **nhiều request sử dụng chung** có thể làm request khác mất kết quả. Tầng điều phối phải xác định quyền sở hữu handle trước khi hủy. Không gắn `cancel(true)` vào mọi khối `catch (TimeoutException)` mà không biết hậu quả.

## 11. `ExecutorService.shutdownNow()` không cưỡng chế dừng an toàn

Trong Java 17:

| API | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `shutdown()` | Không nhận task mới; các task đã gửi tiếp tục theo quy tắc executor | Không tự hủy task đang chạy |
| `shutdownNow()` | Cố ngừng task đang chạy, thường bằng interrupt, và thu hồi task còn chờ | Không bảo đảm tất cả task đang chạy đều ngừng |
| `awaitTermination(timeout, unit)` | Đợi executor kết thúc trong thời hạn | Trả `false` nếu chưa chấm dứt, không nói mọi task thành công |

Một code shutdown điển hình cần có deadline chờ, chính sách gửi signal, xử lý interruption và ghi nhận task chưa kết thúc. Nhưng gọi `shutdownNow()` hai lần hoặc đóng pool không thể sửa một task chặn không interruptible; cần sửa **task hoặc API bên dưới** để có lối thoát.

Nếu worker giữ file lock, connection hoặc một resource chỉ do nó sở hữu, việc cho phép worker dùng `finally` giải phóng thường an toàn hơn hành động từ ngoài thread đóng ngẫu nhiên một tài nguyên chung. Một số API hỗ trợ hủy bằng cách đóng resource do tác vụ sở hữu, nhưng phải đọc hợp đồng thread-safety và phạm vi sở hữu thật sự trước khi áp dụng.

## 12. Những lựa chọn thiết kế cho task dài

### 12.1. Chia công việc thành đơn vị nhỏ có điểm hủy

Nếu một task tính toán nhiều phần tử, thay vì một vòng lặp dài không kiểm tra, hãy:
- Giữ trạng thái ở các điểm có thể quan sát tiến độ.
- Kiểm tra deadline hoặc cờ interrupt theo chu kỳ phù hợp.
- Dừng ở điểm nhất quán, không để invariant hỏng.
- Dọn tài nguyên trong `finally` hoặc try-with-resources.
- Trả trạng thái hủy/partial result nếu hợp đồng cho phép.

Việc kiểm tra quá dày có thể làm tăng chi phí, còn quá thưa làm hủy chậm; chọn tần suất theo thời gian mỗi đơn vị công việc và yêu cầu về độ trễ dừng. Một task đang giữ lock lâu cần có chính sách rõ để tránh làm các luồng khác bị kẹt khi bị hủy.

### 12.2. Kết quả “partial success” cần được biểu đạt tường minh

Nếu đã xử lý 70/100 file rồi timeout, hệ thống không nên chỉ trả `false`. Có thể dùng result như `Completed(100)`, `Partial(70, failures)`, `Cancelled(70)` hoặc `Unknown(operationId)` tùy nghiệp vụ. Nếu caller cần tiếp tục hoặc bù trừ, phải biết:
- Những đơn vị nào đã hoàn tất.
- Những đơn vị nào chưa được xử lý hoặc trạng thái không xác định.
- Có thể chạy lại phần nào an toàn.
- Kết quả nào đã commit/được công bố.

Chỉ có `CancellationException` của Future không mang thông tin đó. Kênh tiến độ/định danh ngoài Future có thể cần thiết, nhất là sau crash hoặc restart.

### 12.3. Dừng an toàn không đồng nghĩa hoàn tác

Một worker nhận interrupt sau khi đã ghi 70 bản ghi có thể dừng rất nhanh, nhưng 70 bản ghi vẫn tồn tại nếu chúng đã commit. Nếu yêu cầu “tất cả hoặc không có gì”, phải dùng transaction/atomic publish trong phạm vi tài nguyên hỗ trợ. Nếu hành động đã xảy ra trên nhiều hệ thống, cần compensation, saga, outbox hoặc đối soát thích hợp; chúng đều có giới hạn và bản thân compensation cũng có thể thất bại.

## 13. Phản ví dụ phổ biến

### Sai lầm 1: Timeout đồng nghĩa task thất bại hoàn toàn

~~~java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    return "nothing happened";
}
~~~

Đây là fragment để phân tích anti-pattern; các kiểu/checked exception khác phải được xử lý trong code thật. `TimeoutException` chỉ nói caller chưa có kết quả trong một giây. Trả `"nothing happened"` có thể sai nếu server đã ghi dữ liệu hoặc worker sẽ còn xử lý.

### Sai lầm 2: `cancel(true)` có nghĩa worker chắc chắn chết

~~~java
future.cancel(true);
System.out.println("work was stopped");
~~~

Đây là fragment minh họa, không có cách kiểm chứng worker đã dừng. Hãy phân biệt **yêu cầu hủy Future** và **xác nhận completion của worker** nếu caller cần sự xác nhận đó. Có thể dùng một kênh completion riêng hoặc mô hình job state, đồng thời giữ timeout để không đợi mãi.

### Sai lầm 3: Nuốt `InterruptedException`

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ignored) {
    // Tiếp tục chạy như không có lệnh hủy.
}
~~~

Đây là fragment phản ví dụ. Nếu muốn tôn trọng yêu cầu hủy, nên truyền tiếp hoặc khôi phục cờ interrupt rồi thoát khỏi task theo đúng hợp đồng. Không biến interrupt thành giá trị thất bại của worker khi thực ra chính luồng điều phối mới bị interrupt.

### Sai lầm 4: `orTimeout` tự ngắt tất cả các stage nguồn

Nếu stage A gọi remote, stage B nối từ A và B được đặt timeout, điều này không tạo lệnh hủy chắc chắn tới socket/remote service do A dùng. Các dependent stage chỉ diễn đạt phụ thuộc kết quả; muốn dừng nguồn cần cơ chế hủy do API nguồn hỗ trợ.

### Sai lầm 5: Retry một tác vụ có side effect bằng operationId mới

Một lỗi mạng hoặc timeout có thể tới sau commit. Nếu retry tạo operationId khác, phía nhận có thể thực hiện tác động hai lần. Dùng cùng operationId và hợp đồng idempotency/tra cứu trạng thái đúng phía server.

### Sai lầm 6: Có `Future.isDone()` nên mọi tài nguyên đều đã được dọn

Future có thể xong do hủy, timeout stage, hoặc hoàn tất bất thường. Với `CompletableFuture`, supplier bên dưới vẫn có thể hoạt động sau khi future đã hoàn thành do timeout. Kiểm tra tài nguyên/worker theo kênh riêng nếu cần bảo đảm dọn xong.

### Sai lầm 7: Đóng bất kỳ tài nguyên nào từ thread điều phối

Đóng connection/stream đang được task khác hoặc nhiều request chia sẻ có thể phá tác vụ khác. Chỉ đóng resource có quyền sở hữu hợp lệ hoặc dùng API hủy được nhà cung cấp hỗ trợ, với quy tắc thread-safety rõ ràng.

## 14. Kiểm thử giới hạn thật của timeout và cancellation

Một bộ test tốt phải tạo được các trạng thái đúng thời điểm, thay vì dựa vào `Thread.sleep(100)` và đoán scheduler. `CountDownLatch` giúp biết task đã bắt đầu, chặn nó ở điểm xác định và thả nó ở thời điểm mong muốn.

| Kịch bản | Hành vi cần kiểm chứng |
| --- | --- |
| `get(timeout)` hết hạn | Caller nhận `TimeoutException` nhưng Future chưa bị tự động hủy |
| Thả latch sau timeout | Worker vẫn có thể hoàn thành và trả kết quả |
| `cancel(true)` khi task đang `sleep` | Worker nhận interrupt, chạy cleanup; Future báo canceled |
| `cancel(true)` khi task CPU bỏ qua interrupt | Future có thể canceled nhưng worker tiếp tục cho đến khi logic dừng |
| `cancel(false)` khi task đã chạy | Không có lời hứa gửi interrupt tới worker |
| `CompletableFuture.orTimeout` trên supplier bị chặn | Future hoàn thành lỗi timeout, supplier có thể tiếp tục |
| `completeOnTimeout` | Future trả fallback, nhưng nguồn có thể còn chạy |
| `cancel(true)` trên CompletableFuture | Không giả định supplier nhận interrupt |
| Timeout ngay gần lúc completion | Chấp nhận race giữa kết quả, timeout và hủy theo hợp đồng |
| Caller bị interrupt trong `get` | Xử lý `InterruptedException`, không suy ra task lỗi |
| Thao tác remote timeout sau khi commit | Tra operationId để xác minh, không nhân đôi side effect |
| Nhiều người dùng chung một future | Timeout/hủy của một caller không phá kết quả của caller khác ngoài ý muốn |

Để mô phỏng task **bỏ qua interrupt** trong một test, chỉ làm trong môi trường có deadline và lối thoát chắc chắn; ví dụ dùng một latch được giải phóng trong `finally` của test. Tránh tạo vòng lặp vô hạn không thể thu hồi. Kiểm thử cleanup cần xác nhận worker đã thật sự ra khỏi đoạn xử lý, chứ không chỉ kiểm tra Future `isCancelled()`.

Không khẳng định một thứ tự log từ hai thread nếu test không tạo quan hệ đồng bộ. Khi kiểm thử giới hạn mili giây, nên chọn latch/điểm sự kiện quyết định kết quả thay vì đặt timeout sát tốc độ máy đang chạy để tránh test chập chờn.

## 15. Cây quyết định sau khi caller bị timeout

~~~text
Caller chưa có kết quả trước deadline
|
+-- Công việc chỉ đọc, không có side effect?
|      +-- Có: có thể trả timeout/để tác vụ chạy hoặc yêu cầu hủy
|      +-- Không chắc: kiểm tra tác vụ con và ảnh hưởng ngoài hệ thống
|
+-- Caller có quyền sở hữu việc hủy?
|      +-- Không: không hủy task dùng chung chỉ vì caller timeout
|      +-- Có: cân nhắc cancel theo khả năng hỗ trợ
|
+-- Task có hỗ trợ interruption/deadline?
|      +-- Có: phát yêu cầu, xác nhận tiến độ dừng theo kênh quản lý
|      +-- Không: cần thay thiết kế I/O/task hoặc dùng trạng thái pending
|
+-- Có hiệu ứng bên ngoài chưa xác định?
       +-- Có: dùng operationId, idempotency, tra trạng thái/đối soát
       +-- Không: báo kết quả hủy/chưa hoàn tất theo hợp đồng
~~~

Không có một nhánh chung “timeout → rollback hết”. Cách đúng phụ thuộc vào phạm vi công việc, quyền sở hữu, cơ chế hợp tác với hủy và giao thức của từng tài nguyên.

## 16. Checklist dành cho Java API bất đồng bộ

1. **Đặt tên đúng trạng thái:** timeout là “chưa nhận kết quả đúng hạn”; cancel của Future là “handle đã hủy”; không đồng nhất với worker đã dừng hay side effect đã undo.
2. **Truyền deadline có mục đích:** giới hạn thời gian chờ của caller và cấu hình timeout cho network/database theo API cụ thể.
3. **Hủy đúng chủ sở hữu:** xác định Future dùng riêng hay dùng chung; tránh hủy một job vẫn cần cho caller khác.
4. **Tác vụ hợp tác:** hỗ trợ kiểm tra interrupt/deadline, không nuốt `InterruptedException`, đặt điểm dừng nhất quán và cleanup tài nguyên đúng phạm vi.
5. **Hiểu API:** `Future.get(timeout)` không hủy; `Future.cancel(true)` chỉ cố hủy/interrupt; `CompletableFuture.orTimeout` làm future hoàn thành lỗi; `CompletableFuture.cancel(true)` không đảm bảo interrupt supplier.
6. **Chấp nhận race:** task có thể hoàn tất khi timeout/cancel diễn ra; đọc trạng thái một cách có kiểm soát, không dựa vào thứ tự không có đồng bộ.
7. **Tôn trọng side effect:** hủy Java task không làm remote service rollback. Với request có tác dụng phụ, dùng idempotency key và tra trạng thái khi cần.
8. **Thiết kế vòng đời:** quản lý executor, chờ shutdown trong hạn, ghi nhận những task chưa thể kết thúc và tránh rò resource.
9. **Báo kết quả có ý nghĩa:** phân biệt completed, failed, canceled, pending và unknown; cung cấp job ID/progress nếu kết quả có thể tới sau khi caller đã timeout.
10. **Test đúng trạng thái bên dưới:** kiểm tra worker/remote đã dừng thật hay chưa, thay vì chỉ assert exception/cờ của handle.

### Bài tập vận dụng

Thiết kế một Java service nhận yêu cầu xuất báo cáo rồi tải lên object storage. API phải phản hồi trong 3 giây, trong khi công việc có thể kéo dài 30 giây. Hãy trả lời:

- Khi `future.get(3, SECONDS)` timeout, nên trả “thất bại”, “đã tiếp nhận”, hay một job ID để tiếp tục tra cứu? Tại sao?
- Nếu người dùng hủy báo cáo, nên gọi `cancel(true)` ở đâu? Task đang upload có hỗ trợ dừng không? Nếu upload đã hoàn tất ở storage nhưng phản hồi thất lạc, trạng thái nào là đúng?
- Có thể dùng một `CompletableFuture.orTimeout(3, SECONDS)` cho nhiều caller cùng tham gia không? Điều gì xảy ra với supplier?
- Nếu retry upload, làm thế nào tránh tạo ra hai file mang cùng nội dung nhưng định danh khác nhau hoặc công bố hai phiên bản nhầm lẫn?
- Viết test bằng latch chứng minh task còn chạy sau timeout; thêm test rằng worker nhận interrupt và dọn file tạm nhưng file đã công bố không bị xóa tùy tiện.

**Điểm cần nhớ:** Timeout giới hạn **sự chờ đợi hoặc trạng thái của future**, cancellation là **yêu cầu hủy**. Việc dừng được một tác vụ thực thi và việc kiểm soát ảnh hưởng của nó lên file, database hay dịch vụ ngoài phụ thuộc vào thiết kế tác vụ và giao thức của hệ thống bên dưới.