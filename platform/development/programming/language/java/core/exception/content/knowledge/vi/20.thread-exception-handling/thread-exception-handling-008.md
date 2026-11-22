# TimeoutException và CancellationException trong Java Concurrency

## 1. Hai tín hiệu rất khác nhau khi làm việc với tác vụ bất đồng bộ

Khi một luồng gọi chờ kết quả từ tác vụ đang chạy ở luồng khác, có ít nhất hai câu hỏi phải tách biệt:

- **Đã chờ quá thời hạn cho phép chưa?** Đây là vấn đề *timeout*: lời gọi chờ không nhận được kết quả trong khoảng thời gian quy định.
- **Kết quả của tác vụ đã bị hủy chưa?** Đây là vấn đề *cancellation*: một đối tượng quản lý tác vụ ghi nhận rằng kết quả không còn được chờ nhận theo đường hoàn tất thông thường.

Trong Java, **java.util.concurrent.TimeoutException** và **java.util.concurrent.CancellationException** biểu diễn hai tình huống này. Chúng thường xuất hiện khi làm việc với **Future**, **ExecutorService** và **CompletableFuture**, nhưng ý nghĩa và cách xử lý không giống nhau.

Một lần gọi **Future.get(timeout, unit)** có thể ném TimeoutException vì chờ quá lâu. **Điều đó không tự động dừng task.** Task có thể tiếp tục chạy, hoàn tất sau đó và trả về kết quả trong một lần get khác. Ngược lại, khi Future đã chuyển sang trạng thái canceled, **Future.get()** sẽ ném CancellationException; ngay cả khi mã của worker còn đang chạy một thời gian do chưa hợp tác với yêu cầu hủy, đối tượng Future đã không còn cung cấp kết quả theo đường thông thường.

Nguyên tắc quan trọng nhất: **timeout là tình trạng của lần chờ; cancellation là trạng thái hủy của tác vụ/kết quả được quản lý**. Một timeout có thể khiến ứng dụng *quyết định* yêu cầu hủy, nhưng việc yêu cầu ấy là một hành động riêng cần được thiết kế rõ ràng.

## 2. Khái niệm và phân loại exception

| Khía cạnh | TimeoutException | CancellationException |
| --- | --- | --- |
| Package | **java.util.concurrent** | **java.util.concurrent** |
| Kiểu | Checked exception, kế thừa **Exception** | Unchecked exception, kế thừa **IllegalStateException** qua **RuntimeException**? Không: nó kế thừa trực tiếp **IllegalStateException**, là một **RuntimeException** |
| Ý nghĩa trong Future | Không nhận được kết quả trong khoảng chờ chỉ định | Future đã bị hủy |
| Ví dụ thường gặp | **future.get(100, MILLISECONDS)** hết thời gian | **future.get()** sau khi Future được hủy |
| Task nền chắc chắn đã dừng? | **Không** | **Không nhất thiết** |
| Tự động gọi **cancel**? | **Không** | Trạng thái hủy thường do lời gọi **cancel** hoặc cơ chế hủy của API |
| Hướng xử lý | Xác định deadline, retry, fallback, hoặc quyết định hủy | Tôn trọng ý định hủy; dừng chờ, cleanup và báo trạng thái phù hợp |

**Lưu ý về phân loại:** CancellationException **trực tiếp extends IllegalStateException**, mà IllegalStateException extends RuntimeException. TimeoutException trực tiếp extends Exception. Vì là checked exception, TimeoutException phải được bắt hoặc khai báo nếu phương thức có thể ném nó qua chữ ký. CancellationException là unchecked, nên Java không bắt buộc khai báo trong **throws**.

Không phải mọi API có chữ “timeout” đều ném TimeoutException. **Thread.sleep** bị interrupt sẽ ném InterruptedException; **Object.wait(timeout)** hết thời gian bình thường chỉ trở về; **CountDownLatch.await(timeout, unit)** trả về **false** nếu hết thời gian; **Lock.tryLock(timeout, unit)** trả về **false** nếu không lấy được lock. Cần đọc hợp đồng của đúng phương thức đang gọi.

## 3. Mô hình trạng thái: deadline, hoàn tất và hủy

Một Future thường được xem dưới các khái niệm:

- **Chưa hoàn tất:** task đang chờ hoặc đang chạy; **isDone()** thường là false.
- **Hoàn tất bình thường:** có kết quả; **get()** trả về kết quả.
- **Hoàn tất có exception:** **get()** ném **ExecutionException** có cause là lỗi task.
- **Đã bị hủy:** **isCancelled()** là true, **isDone()** cũng là true, và **get()** ném **CancellationException**.

**isDone() = true không có nghĩa thành công.** Nó bao gồm hoàn tất bình thường, hoàn tất bất thường và cancellation. Cũng không được suy ra “worker đã thoát” từ **isDone()** của một Future bị hủy, vì cơ chế hủy có thể đánh dấu Future đã canceled trước khi luồng chạy thực sự kết thúc.

Sơ đồ khái niệm:

~~~text
Future chưa hoàn tất
    |                  |
    | get(timeout)     | cancel(...)
    | quá thời hạn     v
    |              Future canceled
    |                  |
    |                  +-- get() -> CancellationException
    |
    +-- TimeoutException cho lượt chờ này
    |
    +-- Task vẫn có thể chạy tiếp
            |
            +-- Thành công -> get() trả kết quả
            |
            +-- Thất bại -> get() ném ExecutionException
~~~

Sơ đồ tập trung vào kết quả quan sát từ **Future**, không phải biểu đồ tất cả trạng thái nội bộ của **Thread** hoặc **FutureTask**. Một lời gọi get hết hạn không chuyển Future sang canceled.

## 4. Ví dụ Java 17+ hoàn chỉnh và chạy được

Chương trình sau tạo một **ExecutorService** với một worker. Tình huống đầu giữ tác vụ ở trạng thái chờ bằng **CountDownLatch**, gây timeout rồi mở latch để lấy kết quả sau đó. Tình huống thứ hai chủ động hủy task bằng **cancel(true)** và kiểm tra worker có quan sát interrupt không.

Dùng latch để điều khiển trình tự giúp không phải dựa vào việc máy tính nhanh hay chậm để quyết định kết quả. Khoảng chờ 30 ms chỉ phục vụ minh họa cho timeout khi latch vẫn đóng, không phải một khuyến nghị timeout cho ứng dụng thực tế.

Lưu vào tệp **TimeoutCancellationDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            CountDownLatch releaseFirst = new CountDownLatch(1);
            Future<String> first = executor.submit(() -> {
                releaseFirst.await();
                return "completed";
            });
            try {
                first.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("1. First get: TimeoutException");
            }
            System.out.println("2. Cancelled by timeout: " + first.isCancelled());
            releaseFirst.countDown();
            System.out.println("3. Later result: " + first.get());

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch releaseSecond = new CountDownLatch(1);
            CountDownLatch exited = new CountDownLatch(1);
            AtomicBoolean sawInterrupt = new AtomicBoolean(false);
            Future<String> second = executor.submit(() -> {
                started.countDown();
                try {
                    releaseSecond.await();
                    return "completed";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "stopped";
                } finally {
                    exited.countDown();
                }
            });

            started.await();
            try {
                second.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("4. Second get: TimeoutException");
            }
            System.out.println("5. Cancel request accepted: " + second.cancel(true));
            exited.await();
            System.out.println("6. Worker saw interrupt: " + sawInterrupt.get());
            System.out.println("7. Cancelled: " + second.isCancelled());
            System.out.println("8. Done: " + second.isDone());
            try {
                second.get();
            } catch (CancellationException e) {
                System.out.println("9. Get after cancel: CancellationException");
            }
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 TimeoutCancellationDemo.java
java TimeoutCancellationDemo
~~~

Kết quả stdout đã được xác minh bằng biên dịch và chạy chương trình:

~~~text
1. First get: TimeoutException
2. Cancelled by timeout: false
3. Later result: completed
4. Second get: TimeoutException
5. Cancel request accepted: true
6. Worker saw interrupt: true
7. Cancelled: true
8. Done: true
9. Get after cancel: CancellationException
~~~

### Giải thích phần đầu: timeout không hủy task

**releaseFirst** chưa được mở. Task đầu tiên gọi **releaseFirst.await()**, nên chưa thể trả về. Vì vậy **first.get(30, MILLISECONDS)** ném TimeoutException. Sau khi bắt ngoại lệ, **first.isCancelled()** là false: quá thời gian đợi *không yêu cầu hủy*.

Lệnh **releaseFirst.countDown()** cho task được tiếp tục, và **first.get()** sau đó trả về **completed**. Điều này chứng minh một Future đã từng gây TimeoutException cho một lần đợi vẫn có thể cung cấp kết quả bình thường ở lần đợi sau.

### Giải thích phần sau: yêu cầu hủy và interrupt

Task thứ hai đã báo **started** rồi chờ trong **releaseSecond.await()**. Luồng main chờ chắc chắn task đã bắt đầu trước khi gọi get có timeout.

Sau TimeoutException, **second.cancel(true)** yêu cầu hủy và gửi yêu cầu interrupt tới worker đang thực thi. **CountDownLatch.await()** là thao tác chờ có thể bị ngắt; nó ném **InterruptedException**. Worker ghi nhận sự kiện này vào **AtomicBoolean**, khôi phục interrupt flag rồi thoát đường chờ. **exited.await()** đảm bảo main không in trạng thái **sawInterrupt** trước khi worker có cơ hội xử lý interrupt.

Trong tình huống minh họa có điều khiển này, **cancel(true)** trả về true, **isCancelled()** và **isDone()** là true. **second.get()** ném CancellationException thay vì trả về chuỗi **stopped**: khi kết quả Future đã canceled, giá trị do mã Callable trả về sau interrupt không trở lại đường get bình thường.

**Điểm cần phân biệt:** Việc worker thật sự quan sát interrupt được kiểm chứng ở ví dụ nhờ cờ riêng và latch **exited**. Chỉ nhìn vào **isCancelled()** hoặc giá trị true của **cancel(true)** không đủ để khẳng định mọi tác vụ thực tế đã dừng toàn bộ tác dụng phụ.

## 5. Future.get(timeout) có nghĩa chính xác là gì?

Phương thức:

~~~java
// Phương thức của Future<T>, minh họa chữ ký API:
T get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

Yêu cầu luồng gọi chờ tối đa khoảng thời gian được chỉ định để nhận kết quả Future. Theo hợp đồng API, kết quả có thể là:

| Diễn biến | Kết quả từ get(timeout, unit) |
| --- | --- |
| Task hoàn tất bình thường trong thời gian chờ | Trả về kết quả |
| Task hoàn tất bằng exception | Ném **ExecutionException**, có cause là exception từ task |
| Future đã canceled | Ném **CancellationException** (unchecked) |
| Hết thời gian mà kết quả chưa sẵn sàng | Ném **TimeoutException** |
| Luồng đang chờ bị interrupt | Ném **InterruptedException** |

Vì vậy, **catch TimeoutException** là một nhánh điều khiển của lời gọi đợi. Nhánh này không nói task xử lý được bao nhiêu phần trăm công việc, đã ghi dữ liệu bên ngoài hay chưa, hoặc có nên retry hay không.

### Thời hạn của lần chờ và thời hạn nghiệp vụ

Mỗi lần gọi **future.get(1, SECONDS)** có một khoảng chờ riêng. Nếu ứng dụng lặp lại lời gọi 10 lần, nó có thể dành khoảng thời gian chờ lớn hơn 1 giây cho cùng một task. Muốn giới hạn thời gian của cả chuỗi bước nghiệp vụ, hãy dùng **deadline chung** và tính phần thời gian còn lại trước từng bước; không reset timeout vô tình sau mỗi lần retry.

Ví dụ, một request có ngân sách thời gian 500 ms cho cả việc gọi dịch vụ A, lấy kết quả từ Future và ghi phản hồi. Dùng riêng 500 ms cho từng bước sẽ khiến tổng thời gian có thể vượt xa deadline thực tế.

### Timeout và thực thi chậm

Timeout có thể là tín hiệu cần quan sát hiệu năng, tắc nghẽn thread pool, deadlock, giới hạn tài nguyên hoặc một dependency chậm. Một TimeoutException đơn lẻ không tự chứng minh lỗi nghiệp vụ hay treo vĩnh viễn. Cần xem trạng thái executor, tiến độ tác vụ, thời gian đã tiêu tốn và hệ quả nếu task vẫn tiếp tục chạy.

### API khác có thời gian chờ nhưng không ném TimeoutException

- **CountDownLatch.await(timeout, unit)** trả về boolean.
- **Thread.join(millis)** hết thời gian có thể trở về mà thread vẫn sống.
- **BlockingQueue.poll(timeout, unit)** có thể trả về null nếu không có phần tử trong hạn chờ.
- **Semaphore.tryAcquire(timeout, unit)** trả về false khi không lấy được permit.
- **Future.get(timeout, unit)** mới dùng TimeoutException cho hết hạn chờ theo hợp đồng của Future.

Vì vậy không nên viết một catch TimeoutException cho mọi API có tham số timeout mà chưa xem chữ ký phương thức.

## 6. Future.cancel(boolean) và tính hợp tác khi hủy

Giao diện Future cung cấp:

~~~java
// Phương thức trên một Future<?>:
boolean cancel(boolean mayInterruptIfRunning);
~~~

Giá trị trả về biểu thị yêu cầu hủy có chuyển trạng thái Future thành canceled thành công hay không theo hợp đồng triển khai. Thông thường, nếu tác vụ đã hoàn tất bình thường hoặc đã bị hủy trước đó, lời gọi cancel sau sẽ trả về false. Có race giữa hoàn tất và hủy; phải xử lý cả hai kết quả.

Hai cách gọi mang ý nghĩa khác nhau:

- **cancel(false):** yêu cầu hủy kết quả Future mà không đề nghị ngắt luồng đang thực thi. Nếu task đã chạy, mã của nó có thể tiếp tục cho đến khi tự hoàn tất.
- **cancel(true):** cho phép cơ chế thực thi gửi interrupt đến thread đang chạy, khi triển khai hỗ trợ. Đây là **tín hiệu hợp tác**, không phải lệnh buộc hệ điều hành giết thread.

Ngay cả khi **cancel(true)** trả về true, không thể suy ra thao tác I/O, truy vấn database hoặc code bên trong chắc chắn đã dừng ngay. Nếu worker chỉ tính toán trong vòng lặp và không kiểm tra interrupt, nó có thể tiếp tục chạy. Một số thư viện chặn có cơ chế ngắt riêng; những lời gọi khác không phản ứng với interrupt hoặc cần API cancel/close chuyên biệt.

Ví dụ mã minh họa cho một worker có thể hủy:

~~~java
// Minh họa trong Callable<Result> hoặc Runnable có vòng lặp.
while (!Thread.currentThread().isInterrupted()) {
    doOneSmallUnitOfWork();
}
// Dọn dẹp theo hợp đồng rồi kết thúc.
~~~

Khi worker dùng API ném **InterruptedException**:

~~~java
// Minh họa trong thân worker; chưa phải chương trình độc lập.
try {
    blockingOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Hoàn tất cleanup thích hợp rồi thoát.
    return;
}
~~~

Việc khôi phục interrupt flag có ý nghĩa vì những phương thức như **CountDownLatch.await()** khi ném InterruptedException thường xóa trạng thái interrupt trên thread. Tuy nhiên, có trường hợp API muốn **ném tiếp InterruptedException** thay vì tự khôi phục và trả về. Hãy theo hợp đồng tầng gọi và tránh nuốt tín hiệu hủy rồi tiếp tục như bình thường.

## 7. TimeoutException, CancellationException, InterruptedException và ExecutionException

Bốn loại exception sau thường xuất hiện trong cùng một luồng nghiệp vụ nhưng không thể dùng thay cho nhau:

| Exception | Điều gì xảy ra? | Điều nên cân nhắc |
| --- | --- | --- |
| **TimeoutException** | Caller đợi quá lâu | Deadline, fallback, task còn chạy, có cần hủy không |
| **CancellationException** | Future đã canceled | Tôn trọng hủy; cleanup, không chờ kết quả bình thường |
| **InterruptedException** | Thread đang chờ bị yêu cầu interrupt | Khôi phục flag hoặc ném tiếp, dừng/chuyển giao điều khiển |
| **ExecutionException** | Bản thân task hoàn tất bằng lỗi | Kiểm tra **getCause()**, phân loại lỗi nghiệp vụ/hạ tầng |

**InterruptedException** của **future.get(...)** liên quan tới *thread đang chờ* bị interrupt. Nó không có nghĩa task worker tự bị canceled. Một luồng main có thể bị interrupt khi đang chờ Future, trong khi worker vẫn tiếp tục chạy. Nếu nghiệp vụ muốn hủy công việc khi caller bị interrupt, đó là quyết định phải thêm vào chính sách xử lý.

**ExecutionException** cũng khác CancellationException. Nếu Callable ném IllegalArgumentException, Future chưa hẳn bị hủy; **future.get()** thường ném ExecutionException với cause IllegalArgumentException. Không được dùng isCancelled() để phát hiện mọi tác vụ thất bại.

Đừng dựa vào chuỗi message để suy diễn loại lỗi. Hãy bắt đúng exception, kiểm tra **getCause()** khi cần và giữ stack trace, context.

## 8. Mẫu xử lý Future theo chính sách có timeout

Một phương thức ứng dụng thường có thể chọn hủy task khi vượt deadline. Đó là **chính sách ứng dụng**, tách khỏi hành vi mặc định của **get(timeout)**:

~~~java
// Mã minh họa trong một phương thức đã có:
// Future<Result> future; long waitMillis;
// logger và nghiệp vụ xử lý kết quả được định nghĩa ở nơi khác.
try {
    Result value = future.get(waitMillis, TimeUnit.MILLISECONDS);
    useResult(value);
} catch (TimeoutException e) {
    boolean accepted = future.cancel(true);
    recordTimeout(accepted, e);
} catch (CancellationException e) {
    recordCancellation(e);
} catch (ExecutionException e) {
    Throwable taskCause = e.getCause();
    recordTaskFailure(taskCause);
} catch (InterruptedException e) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    recordCallerInterrupted(e);
}
~~~

Đây là đoạn **theo ngữ cảnh**, chưa phải một class Java độc lập. Các hàm **useResult**, **recordTimeout**, **recordCancellation**, **recordTaskFailure** và **recordCallerInterrupted** đại diện cho ứng xử riêng của ứng dụng. Không nên copy đoạn này rồi tưởng rằng gọi **recordTimeout** đã xử lý tác dụng phụ đang chạy dở.

Trong code thật, cần xác định:

1. Hết timeout có luôn hủy hay vẫn giữ task để dùng kết quả sau?
2. Có được phép retry không? Nếu retry, task cũ đã chắc chắn dừng tác dụng phụ chưa?
3. Nếu **cancel** thất bại do task vừa hoàn tất, có cần đọc kết quả cuối không?
4. Nếu caller bị interrupt, nên hủy công việc liên quan, chuyển việc cho luồng khác, hay để job dài hạn chạy tiếp?
5. Có cần ghi nhận trạng thái “timed out but completion unknown” đối với hệ bên ngoài không?

Cũng nên cân nhắc việc ghi log một lần tại ranh giới quan sát lỗi, để không nhân nhiều log trùng nhau qua các tầng.

## 9. Cancellation là trạng thái Future, không phải bằng chứng worker đã ngừng

Đây là bẫy dễ gặp trong thực hành.

Khi Future được đánh dấu canceled, **isDone()** thường là true và **get()** ném CancellationException. Nhưng worker có thể:

- Chưa bắt đầu chạy và được ngăn không chạy nữa.
- Đang bị chặn trong API có khả năng nhận interrupt và sẽ dừng khi API phản ứng.
- Đang tính toán dài nhưng không kiểm tra interrupt.
- Đang gọi hệ thống ngoài không có đường hủy hiệu quả.
- Đã thực hiện một phần side effect, sau đó mới nhận yêu cầu cancel.

Do đó, **isCancelled() == true không phải giấy chứng nhận đã rollback**. Nếu một task đã gửi request thanh toán và bị hủy local Future, bên thanh toán vẫn có thể đã xử lý request. Nếu một task đã ghi một phần file, cancel không tự xóa dữ liệu. Nếu một task đã sửa object chia sẻ, cancel không đảo ngược thay đổi.

Khi cần bảo toàn trạng thái mạnh, tổ chức task để tính toán trên dữ liệu tạm, kiểm tra cancellation ở các ranh giới thích hợp và chỉ công bố kết quả khi chắc chắn còn được phép commit. Với tác vụ có side effect bên ngoài, cần transaction, idempotency, trạng thái công việc hoặc cơ chế phục hồi riêng.

Một tác vụ có thể tự kết thúc bình thường khi nhận interrupt, nhưng Future vẫn đã bị hủy nếu lệnh cancel thắng cuộc đua với hoàn tất. Điều này đã được minh họa bằng giá trị **"stopped"** trong Callable của chương trình chính: giá trị đó không được trả qua get sau khi Future bị canceled.

## 10. Race condition giữa timeout, hoàn tất và cancel

Các thời điểm sau không diễn ra trong một transaction duy nhất:

~~~text
Caller                      Worker
  |                            |
  |--- get(timeout) ---------->|
  |                            | đang tính toán
  |<-- TimeoutException -------|
  |--- cancel(true) ---------->| có thể vừa hoàn tất
  |<-- true hoặc false --------|
~~~

Trong khoảng từ lúc caller nhận TimeoutException đến khi gọi cancel, worker có thể hoàn tất. Khi đó cancel có thể không còn chuyển được trạng thái Future và trả về false. Một nhánh ứng dụng ghi log “đã hủy thành công” ngay khi bắt TimeoutException là không có cơ sở.

Cùng một task có thể có nhiều consumer chờ Future với các timeout khác nhau. Timeout của consumer thứ nhất không tự hủy task cho consumer thứ hai. Nếu consumer thứ nhất chủ động cancel một Future dùng chung, các consumer còn lại có thể bất ngờ nhận CancellationException. Vì vậy quyền hủy nên thuộc về thành phần sở hữu vòng đời task, không tùy tiện đặt ở bất kỳ nơi gọi get nào.

Nếu task đã có side effect, retry ngay sau TimeoutException có thể tạo tác dụng phụ trùng lặp. Ví dụ timeout chờ phản hồi từ một job tạo hóa đơn không chứng minh hóa đơn chưa được tạo. Cần có request id, idempotency key hoặc cơ chế truy vấn trạng thái công việc trước khi retry.

## 11. CompletableFuture: timeout và cancellation có khác Future không?

**CompletableFuture<T>** vừa là một **Future<T>**, vừa hỗ trợ pipeline theo mô hình **CompletionStage**. Một vài API liên quan nhưng có ngữ nghĩa khác:

| API | Hành vi chính |
| --- | --- |
| **cf.get(timeout, unit)** | Đợi tối đa thời gian; có thể ném checked TimeoutException; không tự hủy |
| **cf.get()** | Đợi và trả kết quả, hoặc ném ExecutionException/CancellationException |
| **cf.join()** | Đợi, không khai báo checked InterruptedException/ExecutionException; lỗi hoàn tất bất thường thường bọc qua CompletionException; canceled trực tiếp có thể ném CancellationException |
| **cf.orTimeout(timeout, unit)** | Nếu chưa hoàn tất khi hết hạn, hoàn tất **chính CompletableFuture đó** một cách bất thường với TimeoutException |
| **cf.completeOnTimeout(value, timeout, unit)** | Nếu chưa hoàn tất khi hết hạn, hoàn tất **chính CompletableFuture đó** bình thường với giá trị fallback |
| **cf.cancel(true/false)** | Hoàn tất CompletableFuture theo trạng thái cancellation; tham số **mayInterruptIfRunning** không điều khiển interrupt của quá trình tính toán do CompletableFuture sở hữu |

**Điểm khác biệt quan trọng:** **cf.get(200, MILLISECONDS)** hết hạn ném TimeoutException trực tiếp tại lời gọi chờ. Còn **cf.orTimeout(200, MILLISECONDS)** thiết lập việc *hoàn tất bất thường chính cf* khi hết hạn. Nếu sau đó gọi **cf.get()**, người gọi thường nhận **ExecutionException** có **getCause()** là TimeoutException; với **join()**, người gọi nhận CompletionException có cause là TimeoutException. Hai đường này không nên bị gộp thành cùng một nhánh catch.

Ví dụ minh họa theo ngữ cảnh:

~~~java
// Minh họa phương thức Java 9+; không phải chương trình đầy đủ.
CompletableFuture<String> result = new CompletableFuture<>();
result.orTimeout(200, TimeUnit.MILLISECONDS);

// Nếu không ai hoàn tất result trước hạn, chính result sẽ
// được hoàn tất bất thường với TimeoutException.
~~~

Với **completeOnTimeout("fallback", 200, MILLISECONDS)**, nếu chưa hoàn tất trước hạn, Future có thể hoàn tất bình thường bằng **fallback**, vì vậy consumer không nhất thiết thấy exception. Hãy thiết kế rõ việc fallback là dữ liệu thật hay trạng thái suy giảm chất lượng.

### Timeout CompletableFuture không mặc nhiên giết computation

Các phương thức **orTimeout**, **completeOnTimeout** và **cancel** quyết định trạng thái hoàn tất của CompletableFuture. Chúng **không tự bảo đảm** rằng một supplier đang chạy trong **supplyAsync** đã bị interrupt, dừng xử lý hoặc ngừng tạo side effect. Đặc biệt, tài liệu **CompletableFuture.cancel(boolean)** nêu tham số **mayInterruptIfRunning** không có hiệu lực vì interruption không được dùng để điều khiển xử lý theo cách đó.

Nếu cần hủy computation thực sự, quản lý riêng task bên dưới (ví dụ Future trả từ ExecutorService), token hủy, hoặc API của dependency. Không nên giả định rằng gọi **CompletableFuture.cancel(true)** tương đương gọi **FutureTask.cancel(true)** đối với một worker đang chạy.

### Nhánh xử lý bất thường trong pipeline

**exceptionally**, **handle** và **whenComplete** có thể dùng để quan sát hoặc chuyển đổi kết quả bất thường. Nhưng:

- **exceptionally** có thể tạo fallback và biến pipeline hậu tiếp thành hoàn tất bình thường.
- **handle** nhận cả kết quả và Throwable, có thể chuyển đổi thành giá trị hoặc lỗi khác.
- **whenComplete** thích hợp cho quan sát/side effect, nhưng callback tự ném lỗi cũng cần được xét.
- Một stage phụ thuộc có thể biểu diễn lỗi của stage trước bằng **CompletionException**, nên cần quan sát chuỗi cause thay vì giả định mọi stage đều ném đúng loại exception gốc.

Nếu downstream xử lý cả timeout và cancellation, hãy phân biệt TimeoutException được dùng để hoàn tất bất thường, CancellationException do Future canceled, và những exception nghiệp vụ khác.

## 12. Mối quan hệ với ExecutorService và shutdown

**ExecutorService.submit(...)** thường trả về Future để quan sát kết quả và yêu cầu hủy. **ExecutorService.shutdown()** ngừng nhận task mới nhưng **không tự cancel mọi task đang chạy**. **shutdownNow()** cố gắng dừng tác vụ đang chạy bằng interrupt và trả về danh sách tác vụ chưa được bắt đầu, nhưng không bảo đảm mọi tác vụ đang chạy sẽ dừng ngay.

**Future.cancel(true)** nhắm tới một Future cụ thể; **shutdownNow()** là yêu cầu dừng ở phạm vi executor. Hai thao tác có mục tiêu khác nhau, và cả hai đều cần worker hợp tác đối với interruption.

Trong một ứng dụng có executor sống lâu, đừng tắt executor chung chỉ vì một yêu cầu client timeout. Nếu tạo executor riêng cho một khối nghiệp vụ, cần có chính sách đóng, await termination và quản lý thread để tránh rò rỉ tài nguyên. Nếu task không hợp tác với interrupt, **awaitTermination** cũng có thể hết hạn trong khi một số worker còn sống.

Một số API cấp cao có cơ chế timeout/cancellation riêng, như **ExecutorService.invokeAll(tasks, timeout, unit)**, có thể hủy những task chưa hoàn tất khi hết thời gian theo hợp đồng của nó. Không chuyển quy tắc của API đó sang **Future.get(timeout)**; mỗi phương thức cần đọc đúng JavaDoc.

## 13. Thiết kế deadline và cancellation cho API nghiệp vụ

Một thiết kế rõ ràng nên tách ba quyết định:

**Thời gian chờ của caller:** Người gọi có thể chịu được bao lâu? Đây là timeout hoặc deadline. Một caller HTTP có thể dừng đợi nhưng job nền vẫn cần chạy để hoàn tất xử lý.

**Quyền hủy kết quả/task:** Ai được cancel và khi nào? Nếu nhiều client cùng chờ một Future cache chung, một client timeout không nên mặc nhiên hủy công việc mà client khác còn cần.

**Khả năng dừng side effect:** Worker có thể đáp ứng interruption ở đâu, cần rollback hoặc compensation gì? Một lời gọi mạng bị timeout không khẳng định server chưa commit.

Có thể định nghĩa kết quả nghiệp vụ thành những trạng thái dễ phân biệt:

- **SUCCEEDED:** có dữ liệu và kết quả đã được xác nhận.
- **FAILED:** task hoàn tất với lỗi thật sự, cần giữ cause.
- **TIMED_OUT_WAITING:** caller hết hạn chờ, kết quả cuối có thể chưa biết.
- **CANCEL_REQUESTED:** đã phát yêu cầu cancel nhưng việc dừng thực tế có thể còn đang diễn ra.
- **CANCELED:** Future ở trạng thái canceled; nghiệp vụ vẫn phải xem xét side effect.
- **UNKNOWN_REMOTE_OUTCOME:** phía ngoài có thể đã xử lý nhưng phản hồi không về trước hạn.

Những tên trạng thái này chỉ là gợi ý thiết kế ứng dụng, **không** phải các enum chuẩn có sẵn của JDK.

### Khi nào nên retry?

Retry chỉ an toàn khi hiểu tính chất thao tác:

- Phép tính thuần trong bộ nhớ, không side effect, có thể tạo task mới nếu bị timeout theo chính sách.
- Đọc dữ liệu có thể retry với timeout/backoff hợp lý, nhưng cần tránh làm quá tải dependency chậm.
- Tạo đơn hàng, ghi tiền hoặc phát sự kiện cần idempotency/deduplication nếu retry có thể tạo kết quả trùng.
- Task đã bị canceled ở local nhưng external service chưa xác nhận dừng cần truy vấn trạng thái trước khi khởi chạy lại, nếu API hỗ trợ.

Không nên dùng một catch chung để coi TimeoutException, CancellationException, InterruptedException và ExecutionException là “lỗi mạng tạm thời” rồi retry đồng loạt.

## 14. Cách kiểm thử timeout và cancellation đáng tin

Kiểm thử với **Thread.sleep(100)** và hy vọng kết quả đến đúng thứ tự thường dễ lỗi trên máy CI chậm hoặc khi scheduler thay đổi. Để kiểm thử deterministic, nên dùng **CountDownLatch**, **CyclicBarrier** hoặc công cụ đồng bộ phù hợp nhằm chủ động điều khiển thời điểm task có thể hoàn tất.

Bảng tình huống cần xác minh:

| Kịch bản | Kiểm tra quan trọng |
| --- | --- |
| Future chưa hoàn tất, get có deadline ngắn | TimeoutException; Future chưa tự canceled |
| Sau timeout, cho task hoàn tất | get tiếp theo trả kết quả đúng |
| Cancel trước khi task bắt đầu | Future chuyển canceled nếu hủy thắng race |
| Cancel(true) khi worker đang await | Interrupt được quan sát nếu API hỗ trợ, Future get ném CancellationException |
| Cancel(false) khi worker đang chạy | Không được giả định worker bị interrupt |
| Task ném exception | get ném ExecutionException và cause giữ lỗi gốc |
| Luồng caller bị interrupt trong get | Bắt InterruptedException; xử lý interrupt policy |
| Future đã canceled | isDone và isCancelled đều true; get ném CancellationException |
| CompletableFuture orTimeout hết hạn | Chính CF hoàn tất bất thường; get/join có kiểu bọc phù hợp |
| Hai caller cùng chờ một task | Timeout của một caller không mặc nhiên phá hủy kết quả chung |

Trong ví dụ chính, latch thứ nhất chứng minh task có thể hoàn tất sau một TimeoutException. Latch **started** giúp bảo đảm worker thứ hai đang chạy trước khi main gọi cancel. Latch **exited** bảo đảm main chờ cho đến khi worker thực sự đi hết finally, thay vì nhầm trạng thái Future canceled với việc worker đã dừng.

Không cần cố tình tạo race chỉ bằng timing ngẫu nhiên; nếu muốn kiểm thử race giữa complete và cancel, hãy điều khiển lịch chạy bằng barrier và xác minh các kết quả được hợp đồng cho phép, không hard-code một thứ tự scheduler không được bảo đảm.

## 15. Những lỗi thường gặp

**Hiểu nhầm “timeout nghĩa là task đã dừng”.** Future.get(timeout) chỉ giới hạn thời gian đợi. Nếu không cancel hoặc task chưa tự hoàn tất, worker có thể còn chạy.

**Gọi cancel(true) rồi coi side effect đã rollback.** Interrupt là tín hiệu hợp tác; kết quả từ hệ ngoài có thể đã commit. Cần chính sách dữ liệu/transaction riêng.

**Dùng isDone() như cờ thành công.** isDone còn true với cancellation và lỗi. Cần gọi get hoặc quản lý trạng thái kết quả đầy đủ.

**Nhầm CancellationException với InterruptedException.** CancellationException báo trạng thái hủy của Future; InterruptedException báo thread đang chờ hoặc worker bị interrupt trong API có hỗ trợ.

**Nuốt InterruptedException.** Khi không ném tiếp, thông thường cần khôi phục interrupt flag và kết thúc hoặc chuyển giao chính sách hủy cho tầng trên.

**Bắt TimeoutException rồi retry việc ghi ngay lập tức.** Task cũ có thể vẫn đang chạy hoặc external request đã hoàn tất. Retry không idempotent có thể lặp side effect.

**Cho rằng CompletableFuture.cancel(true) buộc supplier dừng.** CompletableFuture không dùng tham số này để interrupt xử lý theo cách FutureTask thông thường. Phải quản lý computation bên dưới riêng.

**Đặt orTimeout rồi mong get() ném trực tiếp TimeoutException.** Khi CF đã hoàn tất bất thường với TimeoutException, get thường bọc trong ExecutionException; join thường qua CompletionException. Đây là đường khác get(timeout) hết hạn chờ.

**Tạo nhiều deadline độc lập cho cùng request.** Reset timeout sau mỗi lần chờ/retry có thể khiến tổng thời gian vượt ngân sách.

**Tắt executor chia sẻ khi một task chậm.** Quản lý vòng đời executor theo quyền sở hữu; hủy task cụ thể nếu cần và đóng executor vào ranh giới phù hợp.

## 16. Bảng kiểm trước khi xử lý timeout/cancellation

1. Đang gọi API nào: Future.get(timeout), CompletableFuture.orTimeout hay một API trả boolean khi hết hạn?
2. Timeout chỉ dừng chờ hay còn chủ động chuyển trạng thái kết quả?
3. Nếu timeout xảy ra, task vẫn chạy có gây vấn đề nghiệp vụ hoặc tài nguyên không?
4. Ai sở hữu Future và có quyền cancel khi nhiều caller dùng chung?
5. Nếu cancel(true), worker có kiểm tra interrupt hoặc gọi API có thể bị interrupt không?
6. Nếu cancel trả false vì task vừa hoàn tất, có cần lấy và xử lý kết quả cuối không?
7. Có phân biệt **CancellationException**, **InterruptedException** và **ExecutionException.getCause()** không?
8. Deadline có tính cho toàn bộ chuỗi nghiệp vụ, kể cả retry và cleanup, không?
9. Nếu đã có I/O hoặc side effect, làm sao biết outcome và tránh retry trùng?
10. Test có xác minh timeout không tự cancel, cancel không đồng nghĩa worker đã dừng, và các đường lỗi được quan sát đúng không?

**Ghi nhớ:** **TimeoutException** trong **Future.get(timeout)** nói rằng *lượt chờ đã quá hạn*; nó không hủy task. **CancellationException** cho biết *Future đã bị hủy*, nhưng trạng thái Future không tự chứng minh mọi computation và tác dụng phụ đã dừng. Xử lý đúng cần kết hợp deadline rõ ràng, quyền cancel phù hợp, khả năng đáp ứng interrupt của worker, phân biệt các loại exception và cơ chế an toàn trạng thái khi thao tác có side effect.
