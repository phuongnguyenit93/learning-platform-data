# execute so với submit trong Executor

## 1. Hiểu đúng câu hỏi cần giải quyết

Khi giao một tác vụ cho bộ thực thi (executor), có hai câu hỏi khác nhau: **ai sẽ chạy công việc** và **ai sẽ theo dõi kết quả của công việc**. `execute` và `submit` đều giao việc cho executor; điểm khác biệt chính là hợp đồng theo dõi kết quả, hoàn thành và lỗi.

Ví dụ, một tác vụ tính tổng cần trả số cho nơi gọi; một tác vụ cập nhật bộ nhớ đệm có thể không trả dữ liệu nhưng vẫn cần báo thất bại. Vì vậy, quyết định dùng phương thức nào không chỉ dựa vào việc tác vụ có `return` hay không.

Các thuật ngữ trong bài:

- **Tác vụ**: phần công việc được mô tả bằng `Runnable` hoặc `Callable<T>`.
- **Luồng gọi**: luồng gọi `execute`/`submit`.
- **Luồng thực thi**: luồng thực sự chạy tác vụ; trong ví dụ là luồng của nhóm luồng.
- **Future<T>**: đối tượng đại diện cho một kết quả đang chờ hoặc đã hoàn thành, giúp chờ, lấy kết quả và yêu cầu hủy.

`execute` thuộc `Executor`; `submit` thuộc `ExecutorService`, là giao diện mở rộng của `Executor`. Các phương thức này vẫn được dùng trong Java hiện nay. Ví dụ dưới đây chạy bằng Java 17 trở lên, không cần thư viện ngoài.

## 2. So sánh hợp đồng phương thức

| Tiêu chí | `execute(Runnable)` | `submit(...)` |
|---|---|---|
| Nơi khai báo | `Executor` | `ExecutorService` |
| Đầu vào | `Runnable` | `Runnable`, `Runnable` kèm kết quả định trước, hoặc `Callable<T>` |
| Giá trị trả về từ lời gọi giao việc | `void` | `Future<?>` hoặc `Future<T>` |
| Nhận giá trị tính toán | Không có kênh trả kết quả qua phương thức này | `Future.get()` với `Callable<T>` |
| Chờ một tác vụ hoàn thành | Cần cơ chế khác như latch, hoặc tự cung cấp một `FutureTask` | Dùng Future được trả về |
| Yêu cầu hủy một tác vụ | Không nhận tay cầm hủy từ `execute` | Dùng `Future.cancel(...)` |
| Quan sát lỗi của tác vụ | Phụ thuộc đối tượng Runnable và executor thực thi | Lỗi tính toán thường được giữ trong Future; `get()` báo bằng `ExecutionException` |

**`void` không có nghĩa là thất bại sẽ bị bỏ qua, và có Future không có nghĩa là thất bại sẽ tự được ghi log.** Cần chỉ rõ thành phần nào chịu trách nhiệm quan sát kết quả.

Cả hai phương thức cũng không tự cam kết “luôn tạo luồng mới” hoặc “luôn chạy song song”. `Executor` có thể chạy ngay trên luồng gọi. Nhóm luồng một luồng thực thi các tác vụ lần lượt. Cơ chế chạy phụ thuộc executor, không phụ thuộc riêng tên `execute`/`submit`. [Hợp đồng Executor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executor.html).

## 3. Ba dạng submit và ý nghĩa kết quả

Đoạn dưới minh họa bên trong một phương thức đã có biến `ExecutorService pool`; đây chưa phải chương trình độc lập:

```java
Runnable refreshCache = () -> {
    // Thực hiện công việc không trả giá trị.
};

Future<?> completion = pool.submit(refreshCache);
Future<String> receipt = pool.submit(refreshCache, "accepted-result");
Future<Integer> calculation = pool.submit(() -> 6 * 7);
```

- `completion.get()` trả `null` nếu tác vụ kết thúc bình thường. Future vẫn hữu ích để phát hiện lỗi và chờ hoàn thành.
- `receipt.get()` trả chuỗi `"accepted-result"` **sau khi** Runnable hoàn thành bình thường. Đây là giá trị truyền sẵn vào `submit`, không phải dữ liệu do `run()` tính ra. Nếu tác vụ thất bại thì `get()` báo lỗi.
- `calculation.get()` trả `42` vì lambda này là `Callable<Integer>`.

`Runnable.run()` không khai báo `throws Exception`; muốn truyền một ngoại lệ được kiểm tra (checked exception) ra khỏi phần tính toán, `Callable<T>` thường phù hợp hơn vì `call()` cho phép ném `Exception`.

Có thể khai báo kiểu tường minh để tránh nhầm các phương thức nạp chồng khi dùng lambda:

```java
Callable<Integer> task = () -> 42;
Future<Integer> result = pool.submit(task);
```

Lời gọi `submit` trả Future không đồng nghĩa tác vụ đã thành công. Tác vụ có thể chưa chạy, đang chạy, đã xong hoặc đã thất bại trước lúc luồng gọi nhận được Future. [Các dạng submit trong ExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#submit(java.util.concurrent.Callable)).

## 4. Vì sao đường đi của ngoại lệ khác nhau?

### 4.1. Giao một Runnable thông thường bằng execute

Xét một `ThreadPoolExecutor` thông thường, tác vụ không tự bắt lỗi, không được bọc bằng đối tượng giữ lỗi:

```java
pool.execute(() -> {
    throw new IllegalStateException("execute failed");
});
```

Ngoại lệ không được xử lý thoát khỏi `run()`, có thể làm luồng thực thi đó kết thúc đột ngột và đến `UncaughtExceptionHandler` của luồng. Nhóm luồng có thể tạo luồng thay thế để tiếp tục phục vụ công việc.

Không suy rộng thành “execute luôn in stack trace” hoặc “execute luôn giết luồng”. Nếu Runnable tự bắt lỗi, nếu có lớp bọc giữ lỗi, hoặc executor chạy trực tiếp trên luồng gọi, đường xử lý sẽ khác. Phần thử nghiệm bên dưới cố định loại executor và cài handler riêng để quan sát rõ hành vi.

### 4.2. Giao bằng submit

Trong triển khai mặc định của `AbstractExecutorService`, `submit` tạo một `RunnableFuture` (mặc định là `FutureTask`), chuyển đối tượng đó cho `execute`, rồi trả nó về. Mô hình khái niệm:

```text
submit(task)
    → tạo lớp bọc giữ kết quả/lỗi
    → execute(lớp bọc)
    → trả Future cho nơi gọi
```

Đây là mô hình triển khai mặc định, không phải yêu cầu mọi `ExecutorService` tùy biến phải dùng đúng lớp `FutureTask`. Lớp con có thể thay cách tạo đối tượng tác vụ. [AbstractExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html).

Với lớp bọc mặc định, lỗi tính toán được lưu vào Future. Khi gọi `get()`, luồng gọi nhận `ExecutionException`; `getCause()` cho biết lỗi gốc. Việc này thường không kích hoạt `UncaughtExceptionHandler` của luồng thực thi do lỗi không thoát ra khỏi lớp bọc tác vụ.

Một hệ quả quan trọng: `pool.submit(task);` rồi bỏ Future có thể khiến lỗi không được quan sát. Không có stack trace trên console không chứng minh tác vụ thành công.

Khi viết công cụ giám sát bằng `ThreadPoolExecutor.afterExecute`, tham số `Throwable` có thể là `null` dù tác vụ gửi bằng `submit` đã thất bại: cần kiểm tra Future đã hoàn thành và lấy lỗi từ nó. [Tài liệu afterExecute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#afterExecute(java.lang.Runnable,java.lang.Throwable)).

### 4.3. execute vẫn có thể đi cùng Future

Đoạn minh họa sau dùng biến `pool` đã có:

```java
FutureTask<Integer> future = new FutureTask<>(() -> 42);
pool.execute(future);
int answer = future.get();
```

`execute` vẫn trả `void`, nhưng chính đối tượng được giao đã là Future. Lỗi của phép tính được lớp bọc giữ lại. Vì vậy, phải xem cả **phương thức giao việc** lẫn **đối tượng được giao** khi phân tích hành vi lỗi. `submit` chỉ giúp tự tạo và trả đối tượng theo dõi theo một hợp đồng thuận tiện. [FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

## 5. Chương trình kiểm chứng đầy đủ

Lưu toàn bộ vào `ExecuteSubmitDemo.java`. Ví dụ dùng một executor với một luồng thực thi và handler riêng. `CountDownLatch` chờ handler thực sự nhận lỗi trước khi in kết quả, không dùng `sleep` để đoán thứ tự.

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class ExecuteSubmitDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch uncaughtReceived = new CountDownLatch(1);
        AtomicReference<Throwable> uncaught = new AtomicReference<>();

        ExecutorService pool = Executors.newSingleThreadExecutor(task -> {
            Thread thread = new Thread(task, "demo-worker");
            thread.setUncaughtExceptionHandler((failedThread, failure) -> {
                uncaught.set(failure);
                uncaughtReceived.countDown();
            });
            return thread;
        });

        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });
            if (!uncaughtReceived.await(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Handler did not receive failure");
            }
            System.out.println("execute error: "
                    + uncaught.get().getClass().getSimpleName());

            Callable<Integer> calculation = () -> 6 * 7;
            Future<Integer> value = pool.submit(calculation);
            System.out.println("Callable result: " + value.get());

            Future<?> noValue = pool.submit(() -> { });
            System.out.println("Runnable result: " + noValue.get());

            Future<String> preset = pool.submit(() -> { }, "done");
            System.out.println("Preset result: " + preset.get());

            Callable<Integer> brokenCalculation = () -> {
                throw new IllegalArgumentException("submit failed");
            };
            Future<Integer> failure = pool.submit(brokenCalculation);
            try {
                failure.get();
                throw new AssertionError("Expected ExecutionException");
            } catch (ExecutionException ex) {
                System.out.println("submit error: "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            shutdown(pool);
        }
    }

    private static void shutdown(ExecutorService pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```shell
javac --release 17 ExecuteSubmitDemo.java
java ExecuteSubmitDemo
```

Stdout khi chương trình hoàn thành bình thường:

```text
execute error: IllegalStateException
Callable result: 42
Runnable result: null
Preset result: done
submit error: IllegalArgumentException
```

Cách đọc thí nghiệm:

1. Runnable gửi bằng `execute` ném lỗi; handler thu lỗi của luồng thực thi.
2. Executor tiếp tục nhận công việc sau khi luồng lỗi được thay thế.
3. `submit(Callable)` trả giá trị tính toán; `submit(Runnable)` trả `null` qua `get()`.
4. Kết quả định trước chỉ nhận được khi Runnable xong bình thường.
5. Lỗi của `submit` được lấy bằng `get()`, không trông chờ handler.

Handler chỉ lưu lỗi, không in; các dòng stdout đều do luồng `main` in nên ví dụ không dựa vào thứ tự in ngẫu nhiên giữa các luồng. Thời hạn 10 giây dành cho việc phát hiện thí nghiệm không tiến triển, không phải cam kết thời gian chạy của executor.

## 6. Phân biệt lỗi giao việc và lỗi chạy việc

Đây là hai thời điểm khác nhau:

```text
Luồng gọi giao tác vụ
    ├─ bị từ chối → xử lý tại lời gọi giao việc
    └─ được chấp nhận → tác vụ chạy → thành công hoặc thất bại
```

`try/catch` quanh `submit` không thay cho xử lý lỗi trong `Future.get()`. Ngược lại, chỉ bắt `ExecutionException` ở `get()` không thay cho xử lý việc bị từ chối trước khi nhận Future.

Với chính sách mặc định `AbortPolicy` của `ThreadPoolExecutor`, executor đã dừng nhận việc hoặc nhóm luồng/hàng đợi có giới hạn đã đầy có thể làm `execute` và `submit` ném `RejectedExecutionException` ngay trên luồng gọi. Chính sách tùy chỉnh có thể đổi hành vi: `CallerRunsPolicy` có thể chạy công việc trên luồng gọi; chính sách bỏ tác vụ có thể làm một Future không bao giờ hoàn thành nếu không hủy nó. Chọn `submit` không khắc phục việc thiết kế hàng đợi hoặc chính sách từ chối sai.

Cần ghi nhận rõ yêu cầu nào chưa được nhận để quyết định báo lỗi, thử lại có giới hạn, hoặc giảm tải. Không tự động thử lại mọi lỗi tính toán: tác vụ có tác dụng phụ có thể đã thực hiện một phần trước khi thất bại.

## 7. Chờ, hủy và vòng đời executor

Sau khi có Future, các trạng thái cần phân biệt là:

| Kết quả khi quan sát | Ý nghĩa |
|---|---|
| `get()` trả giá trị | Tác vụ hoàn thành bình thường |
| `ExecutionException` | Tác vụ tính toán thất bại; xem `getCause()` |
| `CancellationException` | Future đã bị hủy |
| `InterruptedException` | Luồng đang chờ bị ngắt; không tự kết luận tác vụ thất bại |
| `TimeoutException` từ `get(timeout, unit)` | Hết thời gian chờ; tác vụ có thể vẫn đang chạy |

`isDone()` trả `true` cũng bao gồm thất bại hoặc hủy, không đồng nghĩa thành công. Hết thời gian chờ không tự hủy tác vụ. `cancel(true)` chỉ yêu cầu ngắt nếu đang chạy và triển khai hỗ trợ; tác vụ phải hợp tác với tín hiệu ngắt. Future đã hủy cũng không chứng minh công việc đã ngừng mọi tác dụng phụ. [Hợp đồng Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

Một tình huống cần tránh là tác vụ trên executor một luồng lại gửi tác vụ con vào chính executor đó rồi gọi `get()`: luồng duy nhất đang chờ nên tác vụ con không có luồng để chạy. Vấn đề nằm ở phụ thuộc và tài nguyên thực thi, không phải ở cú pháp lambda.

`shutdown()` ngừng nhận việc mới nhưng không chờ tác vụ cũ hoàn thành; dùng `awaitTermination` nếu cần chờ cả executor. Đóng executor do thành phần sở hữu nó thực hiện. Không dừng một executor dùng chung chỉ vì một yêu cầu đã xong. Ví dụ dùng `finally` để quản lý vòng đời và tương thích Java 17.

Cả hai cách giao việc đều cung cấp quan hệ bộ nhớ trước khi giao tác vụ đến khi tác vụ chạy; `Future.get()` còn tạo điểm đồng bộ khi nhận kết quả. Điều đó không làm mọi đối tượng chia sẻ tự trở nên an toàn: nếu các tác vụ cùng sửa một cấu trúc dữ liệu, vẫn cần thiết kế đồng bộ thích hợp.

## 8. Chọn cách nào trong thực tế?

- Chọn `execute` khi giao một `Runnable` và việc báo lỗi/hoàn thành đã có một cơ chế rõ ràng khác, chẳng hạn tác vụ tự ghi nhận kết quả vào hệ thống công việc có giám sát.
- Chọn `submit` khi nơi gọi cần kết quả, cần biết tác vụ hoàn thành hay thất bại, hoặc cần giữ Future để yêu cầu hủy. Một Runnable không trả dữ liệu vẫn phù hợp với `submit` nếu cần những khả năng này.
- Khi chọn `submit`, xác định ai sẽ đọc hoặc thu nhận trạng thái Future. Bỏ Future phải là quyết định có chủ đích với một đường quan sát lỗi khác.

Không dùng `submit` chỉ vì nghĩ nó nhanh hơn, và không dùng `execute` chỉ vì nghĩ mọi tác vụ trả `void` đều không cần theo dõi. Chi phí và thông lượng phụ thuộc cả công việc, executor, mức song song và cơ chế giám sát.

## 9. Tự kiểm tra

1. Runnable không trả dữ liệu nhưng phải biết khi nào lưu xong. Có nên dùng `submit` không? **Có.** Future theo dõi hoàn thành/lỗi ngay cả khi `get()` trả `null`.
2. Bọc `pool.submit(task)` trong `try/catch` đã bắt được lỗi chạy tác vụ chưa? **Chưa**, với tác vụ chạy nền thông thường cần quan sát Future; `try/catch` đó chủ yếu xử lý lỗi ngay khi giao việc.
3. `get(1, TimeUnit.SECONDS)` hết hạn có nghĩa tác vụ đã bị hủy? **Không.** Đó là giới hạn chờ của nơi gọi.
4. `execute(new FutureTask<>(callable))` có làm lỗi luôn đến handler không? **Không.** Chính `FutureTask` giữ lỗi để báo qua Future.
5. Gọi `submit` rồi `get()` ngay trong mỗi vòng lặp có tận dụng tốt nhiều tác vụ độc lập không? **Thường không.** Mỗi vòng chờ xong mới giao tác vụ kế tiếp; có thể giao một nhóm công việc hợp lý trước rồi thu kết quả, đồng thời kiểm soát lượng việc chờ.

Thực hành: đổi `brokenCalculation` thành `return 7;`, sửa phần kiểm tra tương ứng để in kết quả; sau đó đổi Runnable rỗng thành một Runnable ném lỗi và kiểm tra `noValue.get()` báo `ExecutionException`. Dự đoán đường đi của lỗi trước khi chạy, đồng thời giữ nguyên phần dừng executor.
