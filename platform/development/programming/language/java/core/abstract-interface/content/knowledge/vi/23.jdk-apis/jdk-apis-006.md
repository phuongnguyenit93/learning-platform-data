# Runnable và Callable: hợp đồng công việc và kết quả

Trong Java, `Runnable` và `Callable<V>` đều mô tả một đơn vị công việc có thể được thực thi sau đó. Điểm khác biệt cốt lõi nằm ở hợp đồng: `Runnable` thực hiện hành động và không trả kết quả; `Callable<V>` trả về một giá trị kiểu `V` và có thể khai báo checked exception. Chọn đúng kiểu giúp API thể hiện rõ kết quả cần lấy, cách xử lý lỗi và cách quản lý công việc bất đồng bộ.

## 1. Hai hợp đồng khác nhau

| Đặc điểm | `Runnable` | `Callable<V>` |
| --- | --- | --- |
| Phương thức trừu tượng | `void run()` | `V call() throws Exception` |
| Giá trị trả về | Không có | Có, kiểu `V` |
| Khai báo checked exception | `run()` không được khai báo checked exception | `call()` có thể khai báo `Exception` hoặc ngoại lệ checked cụ thể |
| Thuộc package | `java.lang` | `java.util.concurrent` |
| Ví dụ sử dụng | Ghi log, gửi tín hiệu, cập nhật một trạng thái | Tính toán kết quả, đọc dữ liệu, truy vấn cần trả giá trị |
| Hỗ trợ trực tiếp bởi `Thread` | Có | Không; có thể bọc trong `FutureTask<V>` |
| Dùng với `ExecutorService` | `execute(Runnable)`, `submit(Runnable)` | `submit(Callable<V>)` |

Cả hai đều là functional interface, vì mỗi kiểu có một phương thức trừu tượng. Vì vậy, có thể dùng lambda hoặc method reference khi truyền một hành vi vào API.

~~~java
Runnable notify = () -> System.out.println("Da hoan tat");
Callable<Integer> calculate = () -> 6 * 7;
~~~

Lambda thứ nhất không trả kết quả; lambda thứ hai trả về số nguyên. Dòng `Callable<Integer>` cũng cho biết rõ kiểu dữ liệu mà bên gọi sẽ nhận lại.

## 2. Chạy Runnable với Thread

`Thread` nhận một `Runnable`. Khi gọi `start()`, JVM khởi động luồng thực thi mới và gọi `run()` trong luồng đó. Gọi trực tiếp `run()` chỉ thực thi phương thức như một lời gọi thông thường trên luồng hiện tại, không khởi động luồng mới.

~~~java
public class RunnableThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable work = () -> System.out.println("Work is running");

        Thread thread = new Thread(work);
        thread.start();
        thread.join();
        System.out.println("Main continues");
    }
}
~~~

Chạy:

~~~bash
javac RunnableThreadDemo.java
java RunnableThreadDemo
~~~

Kết quả:

~~~text
Work is running
Main continues
~~~

`join()` khiến luồng main đợi luồng công việc kết thúc, nên thứ tự đầu ra trong ví dụ này được xác định. Nếu bỏ `join()`, không nên giả định thứ tự giữa thông báo của main và thông báo của luồng công việc.

Không cần tạo lớp riêng cho mỗi tác vụ nhỏ; lambda thường đủ rõ ràng. Tuy vậy, nếu công việc cần nhiều trạng thái hoặc nhiều phương thức, một lớp triển khai `Runnable` có thể giúp tổ chức mã tốt hơn.

## 3. Callable trả kết quả và có thể ném ngoại lệ

`Callable<V>` phù hợp khi công việc cần tạo ra kết quả. Phương thức `call()` trả về kiểu `V` và có thể khai báo checked exception, chẳng hạn `IOException`. Nhưng bản thân `Callable` không phải một luồng và cũng không tự chạy khi được khởi tạo; nó cần một thành phần thực thi gọi nó.

Ví dụ dưới đây minh họa việc gọi `Callable` qua `ExecutorService`:

~~~java
import java.util.concurrent.Callable;

public class CallableDefinitionDemo {
    public static void main(String[] args) throws Exception {
        Callable<Integer> calculate = () -> 6 * 7;
        System.out.println(calculate.call());
    }
}
~~~

Chạy:

~~~bash
javac CallableDefinitionDemo.java
java CallableDefinitionDemo
~~~

Kết quả:

~~~text
42
~~~

Ví dụ này gọi `call()` trực tiếp trên luồng hiện tại chỉ để minh họa hợp đồng trả về. Trong ứng dụng bất đồng bộ, thường nên giao tác vụ cho một executor và lấy kết quả thông qua `Future<V>`.

Với `Runnable`, checked exception phải được xử lý bên trong `run()` hoặc chuyển thành unchecked exception. Với `Callable`, ngoại lệ checked có thể được khai báo trên `call()`; khi tác vụ chạy bất đồng bộ qua executor, bên lấy kết quả thường nhận ngoại lệ tác vụ qua `ExecutionException` từ `Future.get()`.

## 4. ExecutorService và Future

`ExecutorService` tách việc mô tả công việc khỏi cách bố trí luồng. Thay vì tự tạo một `Thread` cho mỗi tác vụ, ta nộp công việc cho executor để nó lên lịch và thực thi. Phương thức `submit(...)` trả về một `Future`, đại diện cho trạng thái và kết quả của tác vụ.

- `submit(Runnable)` trả về `Future<?>`. Khi tác vụ hoàn tất bình thường, `get()` trả về `null`, vì `Runnable` không tạo giá trị.
- `submit(Callable<V>)` trả về `Future<V>`. Khi tác vụ hoàn tất bình thường, `get()` trả về giá trị kiểu `V`.
- `execute(Runnable)` chỉ nộp một hành động và không trả về `Future`. Dùng khi không cần lấy kết quả hoặc theo dõi hoàn tất qua một `Future`.
- `submit(Runnable, result)` cho phép gắn một giá trị kết quả do bên gọi cung cấp. `Future.get()` trả về giá trị đó sau khi `Runnable` hoàn tất bình thường; đây không phải giá trị do `run()` trả về.

### Ví dụ chạy được: so sánh hai kiểu

Tệp `RunnableCallableDemo.java`:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RunnableCallableDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> action = pool.submit(
                () -> System.out.println("Runnable: saved")
            );
            Future<Integer> calculation = pool.submit(() -> 20 + 22);
            Future<String> status = pool.submit(() -> "done");

            action.get();
            System.out.println("Callable result: " + calculation.get());
            System.out.println("Callable status: " + status.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy bằng Java 17 trở lên:

~~~bash
javac RunnableCallableDemo.java
java RunnableCallableDemo
~~~

Kết quả:

~~~text
Runnable: saved
Callable result: 42
Callable status: done
~~~

Executor chỉ có một luồng worker, các tác vụ được thực hiện theo thứ tự nộp. Lời gọi `action.get()` đợi tác vụ đầu hoàn tất trước khi in các kết quả sau, vì vậy đầu ra minh họa có thứ tự ổn định. Khối `finally` bảo đảm yêu cầu executor ngừng nhận tác vụ mới ngay cả khi có lỗi khi lấy kết quả.

`shutdown()` cho phép các tác vụ đã nộp hoàn tất. Nó không có nghĩa là main đợi executor kết thúc ngay tại dòng gọi; trong ví dụ, các lời gọi `get()` đã đợi từng tác vụ. Với quy trình cần kiểm soát thời gian chờ, có thể dùng thêm `awaitTermination(...)`.

## 5. Hiểu đúng Future.get() và lỗi

`Future.get()` thường chặn luồng gọi cho đến khi tác vụ hoàn tất. Có ba tình huống quan trọng:

1. **Thành công:** với `Callable<V>`, `get()` trả kết quả; với `Runnable` đã nộp qua `submit`, `get()` trả `null` nếu không truyền giá trị kết quả riêng.
2. **Tác vụ thất bại:** `get()` ném `ExecutionException`; gọi `getCause()` để xem ngoại lệ gốc do tác vụ gây ra.
3. **Luồng đang đợi bị ngắt:** `get()` có thể ném `InterruptedException`. Việc này báo rằng luồng chờ bị ngắt, không tự động có nghĩa tác vụ đã bị hủy.

Ví dụ xử lý kết quả theo kiểu cụ thể:

~~~java
Future<Integer> result = pool.submit(() -> {
    if (System.nanoTime() < 0) {
        throw new IllegalStateException("Unexpected state");
    }
    return 42;
});

try {
    int value = result.get();
    System.out.println(value);
} catch (ExecutionException e) {
    System.err.println("Task failed: " + e.getCause());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting thread interrupted", e);
}
~~~

Đoạn trên là fragment để minh họa xử lý lỗi; nó giả định biến `pool` đã được khởi tạo và quản lý vòng đời ở bên ngoài. Trong mã thực tế, không nên bắt rồi bỏ qua `InterruptedException`. Nếu không thể ném ngoại lệ lên tầng gọi, khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` để phần còn lại của chương trình có thể nhận biết việc ngắt.

Có thể dùng `get(timeout, unit)` khi không muốn đợi vô thời hạn; phương thức này còn có thể ném `TimeoutException`. Hết thời gian chờ không tự hủy công việc. Nếu muốn yêu cầu hủy, gọi `cancel(true)` trên Future và thiết kế tác vụ để phản ứng hợp lý với ngắt.

## 6. Hủy tác vụ và vòng đời executor

`Future` cung cấp `isDone()`, `isCancelled()` và `cancel(...)`. Hủy thành công có nghĩa Future được đánh dấu hủy; nó không bảo đảm mọi mã đang chạy dừng tức thì. Tham số `true` yêu cầu ngắt luồng thực thi nếu tác vụ đang chạy, nhưng tác vụ phải hợp tác bằng cách kiểm tra trạng thái ngắt hoặc phản ứng với `InterruptedException`.

Executor cũng cần được quản lý vòng đời:

- `shutdown()`: ngừng nhận tác vụ mới và cho tác vụ đã nộp tiếp tục hoàn tất.
- `shutdownNow()`: cố gắng ngắt tác vụ đang chạy và trả về danh sách tác vụ đang chờ chưa bắt đầu; đây là yêu cầu dừng tốt nhất có thể, không phải bảo đảm dừng tức thì.
- `awaitTermination(timeout, unit)`: chờ executor kết thúc trong một khoảng thời gian tối đa.
- Sau khi executor đã shutdown, các lần nộp tác vụ mới thường thất bại với `RejectedExecutionException`.

Không nên tạo một executor mới cho từng tác vụ nhỏ mà không quản lý việc đóng nó. Trong ứng dụng thật, executor có thể được dùng chung theo vòng đời của thành phần hoặc ứng dụng; nơi sở hữu executor phải có trách nhiệm shutdown đúng lúc.

## 7. Checked exception: lý do Callable hữu ích

Xét API đọc tệp `Files.readString(Path)`, có thể ném `IOException`. Một `Callable<String>` có thể mô tả trực tiếp công việc đọc và cho phép khai báo ngoại lệ checked:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

Callable<String> readText = () -> Files.readString(Path.of("input.txt"));
~~~

Đây là một fragment, không phải tệp độc lập; nó cần đặt trong phương thức hoặc lớp thích hợp. Khi nộp cho executor, hãy lấy kết quả qua `Future<String>`. Nếu đọc tệp thất bại, `Future.get()` sẽ báo `ExecutionException` với nguyên nhân thường là `IOException`.

Với `Runnable`, không thể để `IOException` thoát trực tiếp khỏi `run()` như một checked exception. Có thể bắt và xử lý ngay trong lambda, hoặc bọc thành `UncheckedIOException`, nhưng cách đó làm thay đổi hợp đồng ngoại lệ mà bên gọi nhìn thấy. Nếu kết quả và ngoại lệ là một phần tự nhiên của tác vụ, `Callable<V>` thường phù hợp hơn.

## 8. Callable và Runnable liên hệ với nhau thế nào?

Một `Callable<V>` không thể truyền trực tiếp vào `new Thread(...)`, vì constructor của `Thread` nhận `Runnable`. Nếu cần lấy kết quả trong khi vẫn dùng cơ chế `Runnable`, Java cung cấp `FutureTask<V>`, triển khai `RunnableFuture<V>` và có thể được khởi tạo từ một `Callable<V>`:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

Callable<Integer> work = () -> 21 * 2;
FutureTask<Integer> task = new FutureTask<>(work);
Thread thread = new Thread(task);
thread.start();

Integer answer = task.get();
System.out.println(answer);
~~~

Fragment trên cần đặt trong phương thức có xử lý hoặc khai báo `InterruptedException` và `ExecutionException`. Kết quả là:

~~~text
42
~~~

`FutureTask` vừa có thể được thực thi như một `Runnable`, vừa giữ kết quả và trạng thái Future. Trong phần lớn ứng dụng, `ExecutorService` vẫn là lựa chọn thuận tiện hơn vì cung cấp cơ chế quản lý luồng và hàng đợi tác vụ.

## 9. Các nhầm lẫn phổ biến

- **Chờ kết quả từ Runnable:** `Runnable` không trả dữ liệu qua `run()`. Nếu cần giá trị do tác vụ tạo ra, hãy dùng `Callable<V>` và `Future<V>`, hoặc thiết kế cách trao đổi kết quả rõ ràng.
- **Nghĩ rằng Callable tự chạy:** tạo lambda hoặc đối tượng `Callable` chỉ mô tả công việc. Phải gọi `call()` trực tiếp hoặc nộp nó cho một thành phần thực thi.
- **Nhầm submit với execute:** `submit` trả `Future`; `execute` thì không. Nếu dùng `submit` và không gọi `get()`, lỗi của tác vụ có thể không được quan sát ở nơi gọi.
- **Bỏ qua ExecutionException:** ngoại lệ phát sinh trong tác vụ được bọc trong `ExecutionException` khi lấy kết quả. Hãy kiểm tra `getCause()` để chẩn đoán.
- **Cho rằng cancel(true) dừng tác vụ ngay:** ngắt luồng là cơ chế yêu cầu hợp tác. Công việc không kiểm tra trạng thái ngắt hoặc không phản ứng với ngoại lệ ngắt có thể tiếp tục chạy.
- **Gọi run() rồi kỳ vọng bất đồng bộ:** `run()` là lời gọi phương thức thông thường; dùng `start()` để khởi động luồng mới.
- **Quên đóng executor:** một executor vẫn có thể giữ tài nguyên luồng. Xác định rõ thành phần nào sở hữu nó và khi nào cần shutdown.
- **Chia sẻ trạng thái có thể thay đổi mà không đồng bộ:** Runnable và Callable chỉ mô tả công việc. Chúng không tự làm cho dữ liệu dùng chung trở nên thread-safe.

## 10. Quy tắc lựa chọn nhanh

- Chọn **Runnable** khi chỉ cần mô tả một hành động không trả kết quả, đặc biệt với `Thread`, `Executor.execute` hoặc khi kết quả được truyền qua một cơ chế khác.
- Chọn **Callable&lt;V&gt;** khi tác vụ tạo ra kết quả kiểu `V`, cần khai báo checked exception, hoặc khi API bất đồng bộ cần trả kết quả qua `Future<V>`.
- Chọn **`ExecutorService.submit(...)`** khi cần theo dõi trạng thái, lấy kết quả, hủy hoặc quan sát lỗi qua Future.
- Dùng **execute(Runnable)** khi chỉ cần giao việc cho executor và không cần Future. Cần có chiến lược xử lý lỗi phù hợp vì không có Future để gọi `get()`.
- Chọn **FutureTask&lt;V&gt;** khi cần một đối tượng vừa là Runnable vừa giữ kết quả Future, chẳng hạn khi tích hợp Callable với API chỉ nhận Runnable.

Điểm cần nhớ: `Runnable` trả lời câu hỏi “cần thực hiện hành động nào?”, còn `Callable<V>` trả lời “cần thực hiện công việc nào và kết quả kiểu `V` là gì?”. Khi chạy bất đồng bộ, `Future` là cầu nối để kiểm tra trạng thái, nhận kết quả và quan sát lỗi của công việc đó.