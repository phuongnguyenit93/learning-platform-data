# Ngoại lệ của tác vụ qua execute và submit

## 1. Cùng một công việc thất bại, nơi quan sát có thể khác

Một `Runnable` ném `IllegalStateException` không tự động báo lỗi trên luồng đã gửi nó. Nếu công việc chạy trên một worker khác, lỗi phát sinh ở luồng ấy.

Hai cách gửi thông dụng của `ThreadPoolExecutor` có đường báo lỗi khác nhau:

- `execute(Runnable)` không trả đối tượng kết quả. Nếu Runnable thông thường để lỗi thoát ra trên worker, lỗi đi theo đường ngoại lệ không được bắt của luồng.
- `submit(...)` trả Future. Trong triển khai tiêu chuẩn, công việc được bọc để ghi nhận kết quả hoặc lỗi; nơi gọi quan sát bằng `Future.get()`.

Không có nghĩa execute “có lỗi” còn submit “không có lỗi”. Cả hai đều có thể thực hiện công việc thất bại; chúng khác cách tổ chức việc công bố thất bại.

Trong bài, các mô tả worker áp dụng cho ThreadPoolExecutor thông thường khi tác vụ được thực thi trên luồng của nhóm, không phải mọi Executor tùy biến đều có cùng cơ chế.

## 2. Tách lỗi tiếp nhận khỏi lỗi thực hiện

| Thời điểm | Ví dụ | Nơi cần xử lý |
|---|---|---|
| Khi gửi công việc | `RejectedExecutionException` vì không thể tiếp nhận theo chính sách | Luồng gọi execute hoặc submit |
| Khi kiểm tra đầu vào API | Gửi tác vụ null | Luồng gọi API |
| Trong thân công việc | Lỗi phân tích dữ liệu, `IOException`, `IllegalStateException` | Đường quan sát tác vụ trên worker hoặc Future |
| Khi chờ kết quả | Luồng gọi get bị ngắt hoặc hết thời gian chờ | Nơi gọi get |

Một khối try-catch quanh lời gọi gửi có thể xử lý lỗi tại thời điểm gửi. Nó không bao quanh thời gian chạy sau này trên một luồng khác.

Mã minh họa:

```java
try {
    executor.execute(() -> {
        throw new IllegalStateException("task failed");
    });
} catch (RejectedExecutionException e) {
    handleNotAccepted();
}
```

`executor` và `handleNotAccepted` thuộc ứng dụng. Khối catch này dành cho việc không được tiếp nhận, không phải bắt `IllegalStateException` từ thân tác vụ bất đồng bộ.

Tương tự, chỉ bao submit bằng catch không thay cho việc lấy Future và kiểm tra kết quả của công việc.

## 3. execute với Runnable thông thường

Với một Runnable không tự bắt lỗi và không có lớp bọc giữ lỗi:

```java
executor.execute(() -> {
    throw new IllegalArgumentException("invalid record");
});
```

Trong ThreadPoolExecutor tiêu chuẩn, khi lỗi không được kiểm tra thoát khỏi `run()` trên worker:

1. Công việc kết thúc đột ngột.
2. Hook `afterExecute` có thể nhận Throwable tương ứng.
3. Worker đó kết thúc theo đường lỗi.
4. Cơ chế ngoại lệ không được bắt của Thread nhận lỗi.
5. Executor có thể tạo worker thay thế khi cần theo trạng thái và cấu hình.

Việc một worker chết không tự có nghĩa toàn bộ pool đã shutdown. Công việc thất bại cũng không tự được chạy lại chỉ vì có worker thay thế.

### UncaughtExceptionHandler để quan sát

Có thể gắn `Thread.UncaughtExceptionHandler` qua ThreadFactory để ghi nhận lỗi không được bắt trên worker.

Handler nhận luồng và Throwable đã làm luồng kết thúc đột ngột. Nó là điểm quan sát cấp luồng, không phải một cơ chế sửa lại tác vụ hoặc biến nó thành thành công.

Không đặt giả định mọi lỗi của mọi tác vụ đều sẽ tới handler: Runnable có thể tự bắt, một lớp bọc có thể giữ lỗi, hoặc công việc có thể chạy trên luồng khác theo chính sách từ chối.

Hợp đồng của handler được mô tả trong [Thread.UncaughtExceptionHandler API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html).

## 4. submit bọc công việc thành đối tượng có kết quả

`ThreadPoolExecutor` kế thừa cách triển khai submit từ `AbstractExecutorService`. Cách mặc định tạo một `RunnableFuture`, thường là FutureTask, rồi đưa nó đi thực hiện.

Mô hình:

```text
Callable hoặc Runnable do ứng dụng gửi
        |
        v
RunnableFuture / FutureTask
        |
        v
ThreadPoolExecutor.execute
        |
        v
worker gọi run của đối tượng bọc
        |
        +--> thành công: lưu giá trị
        |
        +--> thất bại: lưu Throwable cho Future
```

Vì đối tượng bọc đã ghi nhận lỗi của công việc, lỗi ấy thường không thoát ra khỏi `FutureTask.run()` theo đường Runnable thông thường. UncaughtExceptionHandler của worker không được gọi chỉ vì công việc bọc trong FutureTask thất bại.

Worker thường tiếp tục xử lý việc khác sau thất bại đã được FutureTask ghi nhận. Điều này không có nghĩa lỗi được xử lý về mặt nghiệp vụ; nó chỉ đã được giữ để nơi gọi quan sát.

Lớp con có thể thay `newTaskFor` để dùng RunnableFuture khác. Cơ chế mặc định và khả năng mở rộng nằm tại [AbstractExecutorService API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html).

### Submit không đồng nghĩa Callable

Submit nhận cả Runnable và Callable:

```java
Future<?> action = executor.submit((Runnable) () -> {
    throw new IllegalStateException("action failed");
});

Future<String> calculation = executor.submit(() -> {
    throw new java.io.IOException("read failed");
});
```

Đây là mã minh họa; cần các import tương ứng.

Runnable vẫn không được để checked exception thoát trực tiếp khỏi `run()`. Nhưng RuntimeException của nó cũng có thể được FutureTask giữ lại khi gửi bằng submit.

Callable cho phép checked exception thoát khỏi `call()`. Điểm khác nhau về checked exception thuộc hợp đồng tác vụ, không phải khẳng định rằng chỉ Callable mới có thể thất bại.

## 5. Future.get báo ExecutionException và giữ nguyên nhân

Ví dụ:

```java
try {
    String value = calculation.get();
    useValue(value);
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    reportTaskFailure(original);
}
```

Đây là đoạn minh họa chưa bao gồm các nhánh ngắt hoặc hủy; các phương thức xử lý do ứng dụng định nghĩa.

`ExecutionException` là lớp bọc báo công việc kết thúc do lỗi. `getCause()` cho phép xem lỗi gốc như IOException hoặc IllegalStateException.

Cần giữ bối cảnh công việc cùng lỗi gốc: mã yêu cầu, loại thao tác, dữ liệu nhận diện phù hợp và stack trace. Chỉ in tên ExecutionException thường chưa đủ để biết lỗi thực sự ở đâu.

Hợp đồng lớp bọc được mô tả tại [ExecutionException API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutionException.html).

### Ba ngoại lệ chờ không được gộp vào lỗi nghiệp vụ

- `InterruptedException`: luồng đang gọi get bị ngắt; không tự chứng minh công việc đã bị hủy.
- `TimeoutException`: hết thời gian của lời gọi get có thời hạn; không tự dừng công việc.
- `CancellationException`: Future đã bị hủy; không có kết quả thành công để lấy.

Một Callable có thể tự ném InterruptedException trên worker; nếu Future không bị hủy, nơi get có thể nhận ExecutionException với nguyên nhân ấy. Nó khác việc luồng đang gọi get bị ngắt trực tiếp.

Nếu bắt InterruptedException mà không truyền lên trên, thường cần phục hồi cờ ngắt rồi thoát hoặc xử lý dừng theo quyền sở hữu của thành phần. Không bắt mọi Exception rồi coi tất cả là “tác vụ tính sai”.

## 6. Chương trình Java 17+: so sánh hai đường báo lỗi

Lưu thành **`TaskFailureDemo.java`**:

```java
import java.io.IOException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class TaskFailureDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch uncaughtObserved = new CountDownLatch(1);
        AtomicReference<Throwable> uncaught = new AtomicReference<>();
        AtomicInteger handlerCalls = new AtomicInteger();

        ThreadFactory factory = worker -> {
            Thread thread = new Thread(worker, "failure-worker");
            thread.setUncaughtExceptionHandler((failedThread, error) -> {
                uncaught.set(error);
                handlerCalls.incrementAndGet();
                uncaughtObserved.countDown();
            });
            return thread;
        };

        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1,
                1,
                0, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>(),
                factory);

        try {
            executor.execute(() -> {
                throw new IllegalStateException("execute failed");
            });

            if (!uncaughtObserved.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Uncaught failure was not observed");
            }

            Throwable executeError = uncaught.get();
            System.out.println(
                    "execute: "
                    + executeError.getClass().getSimpleName()
                    + ": " + executeError.getMessage());

            Future<String> submitted = executor.submit(() -> {
                throw new IOException("submit failed");
            });

            try {
                submitted.get(5, TimeUnit.SECONDS);
                throw new AssertionError("Expected task failure");
            } catch (ExecutionException e) {
                Throwable submitError = e.getCause();
                System.out.println(
                        "submit: "
                        + submitError.getClass().getSimpleName()
                        + ": " + submitError.getMessage());
            }

            Future<String> next = executor.submit(() -> "still usable");
            System.out.println(
                    "next task: " + next.get(5, TimeUnit.SECONDS));
            System.out.println(
                    "uncaught handler calls: " + handlerCalls.get());
        } finally {
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                    if (!executor.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 TaskFailureDemo.java
java TaskFailureDemo
```

Stdout chính xác:

```text
execute: IllegalStateException: execute failed
submit: IOException: submit failed
next task: still usable
uncaught handler calls: 1
```

### Những gì ví dụ chứng minh

Lỗi của Runnable gửi bằng execute thoát khỏi worker và được handler ghi lại. Main chờ chốt thông báo rồi mới in, nên không phụ thuộc vào một khoảng sleep phỏng đoán.

Callable gửi bằng submit ném IOException. FutureTask giữ lỗi ấy; main thấy nguyên nhân qua ExecutionException khi get. Không có lần gọi uncaught handler thứ hai chỉ vì Callable thất bại.

Tác vụ kế tiếp vẫn chạy được. Điều này cho thấy lỗi của một công việc không tự đóng toàn bộ bộ thực thi.

Handler riêng không in stack trace mặc định trong thí nghiệm; main in thông tin đã ghi nhận để stdout có thứ tự xác định. Trong ứng dụng thực, nên ghi stack trace và bối cảnh cần thiết theo chính sách quan sát lỗi.

Các timeout năm giây là giới hạn để phát hiện thiếu tiến triển. Main khai báo throws Exception để giữ ví dụ tập trung, không phải đề xuất bỏ qua xử lý ngắt hoặc lỗi tiếp nhận trong ứng dụng thật.

## 7. Vì sao afterExecute có thể nhận Throwable là null?

ThreadPoolExecutor cho phép override:

```java
protected void afterExecute(Runnable task, Throwable escaped)
```

`escaped` phản ánh Throwable thoát ra từ quá trình chạy Runnable theo đường worker, không phải “mọi lỗi nghiệp vụ của tác vụ”.

Với Runnable thông thường ném lỗi trực tiếp, hook có thể thấy lỗi ở tham số này.

Với FutureTask, công việc đã ném lỗi nhưng lớp bọc ghi nhận nó; lời chạy đối tượng bọc có thể trở về bình thường. Khi đó `escaped` có thể là null dù Future kết thúc thất bại.

Vì vậy, mẫu kiểm tra “escaped khác null thì log, bằng null thì chắc chắn thành công” là không đầy đủ.

### Nếu muốn quan sát Future trong hook

Một thiết kế hook cần:

1. Xử lý Throwable đã thoát trực tiếp nếu có.
2. Nếu Runnable là một Future đã hoàn tất, đọc kết quả để phát hiện lỗi được bọc.
3. Phân biệt thất bại với hủy.
4. Giữ tín hiệu ngắt nếu việc đọc bị ngắt.
5. Không chặn vô hạn trong hook.

Kiểm tra `isDone()` trước khi get giúp tránh chờ một Future chưa kết thúc. Điều này cũng quan trọng với các kiểu tác vụ có vòng đời đặc biệt; không mặc định mọi Runnable có kiểu Future đều đã có kết quả cuối cùng tại mọi lần gọi hook.

API và lưu ý dành cho hook nằm tại [ThreadPoolExecutor.afterExecute](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#afterExecute(java.lang.Runnable,java.lang.Throwable)).

Hook chạy trên đường worker. Nếu bản thân hook ném lỗi, nó có thể làm worker kết thúc; cơ chế giám sát phải đủ gọn và không biến một lỗi ghi log thành nguồn mất luồng.

### Tránh báo trùng mà không có trách nhiệm rõ

Nếu hook ghi lỗi và nơi gọi Future cũng ghi cùng stack trace, log có thể lặp. Cần xác định đâu là ghi nhận kỹ thuật, đâu là xử lý hoặc phản hồi nghiệp vụ, và liên kết chúng bằng mã công việc.

Không vì sợ log trùng mà bỏ toàn bộ quan sát ở một phía không có nơi thay thế.

## 8. execute không luôn có nghĩa ngoại lệ sẽ tới uncaught handler

Tên phương thức chưa mô tả hết đối tượng được chạy.

Ví dụ:

```java
FutureTask<String> wrapped = new FutureTask<>(() -> {
    throw new IllegalStateException("wrapped failure");
});
executor.execute(wrapped);
```

Dù gọi execute, Runnable thực tế là FutureTask. Nó vẫn có thể giữ lỗi và báo qua `wrapped.get()`, giống đường bọc đã giải thích.

Ngược lại, Runnable có thể tự bắt lỗi:

```java
executor.execute(() -> {
    try {
        runOperation();
    } catch (IllegalStateException e) {
        recordFailure(e);
    }
});
```

Đây là đoạn minh họa; các hàm thuộc ứng dụng. Nếu đã bắt và không ném tiếp, uncaught handler không được gọi chỉ vì nhánh xử lý lỗi ấy đã chạy.

Vì vậy, phải đọc cả **cách gửi** và **đối tượng/lớp bọc đang được thực thi**. Vai trò của FutureTask được mô tả trong [FutureTask API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

### Chính sách từ chối có thể đổi luồng chạy

Với CallerRunsPolicy, một công việc bị từ chối khi executor còn mở có thể chạy ngay trên luồng gửi. Khi đó không áp dụng nguyên xi mô tả “lỗi đi trên worker” cho Runnable được chạy trực tiếp.

Đối với submit tiêu chuẩn, lớp bọc FutureTask vẫn có vai trò giữ lỗi dù chính sách cho nó chạy trên bên gửi. Đây là lý do thiết kế quan sát lỗi phải xét handler và cấu hình executor.

## 9. Chọn nơi chịu trách nhiệm về thất bại

Có hai nhu cầu khác nhau:

- **Phát hiện và ghi nhận** công việc thất bại.
- **Quyết định nghiệp vụ** sau thất bại: phản hồi, thử lại, bỏ qua có chủ đích hoặc đánh dấu trạng thái.

Uncaught handler hay afterExecute có thể phục vụ quan sát kỹ thuật nhưng thường không đủ thông tin để tự quyết định nghiệp vụ của mọi loại công việc.

Future giúp nơi sở hữu công việc nhận kết quả và quyết định phản hồi. Nếu dùng submit rồi bỏ Future, lỗi có thể được giữ mà không có ai đọc nó.

Một hệ thống nên xác định rõ ai thu kết quả cho mỗi nhóm công việc, thay vì để mỗi nơi gửi tự giả định sẽ có một handler toàn cục lo mọi chuyện.

### Thử lại cần hiểu tác động trước lỗi

Một tác vụ có thể đã cập nhật dữ liệu hoặc gọi dịch vụ ngoài trước khi ném ngoại lệ. Không nhận được giá trị thành công không có nghĩa chưa xảy ra tác động.

Retry cần quy tắc chống lặp hoặc đối soát thích hợp. Việc worker được thay thế cũng không tự cung cấp khả năng thử lại an toàn.

## 10. Những lỗi xử lý thường gặp

| Cách làm | Vấn đề |
|---|---|
| Chỉ catch quanh submit rồi bỏ Future | Không quan sát lỗi phát sinh sau khi đã nhận |
| Chỉ cài uncaught handler và nghĩ đã bao phủ submit | FutureTask có thể giữ lỗi trước khi tới handler |
| Xem afterExecute có Throwable null là thành công | Lỗi có thể nằm trong Future |
| Bắt mọi Exception rồi không phản hồi | Mất ngữ nghĩa thất bại, ngắt hoặc timeout |
| Tự chuyển mọi lỗi thành giá trị mặc định | Bên gọi không phân biệt dữ liệu thật với thất bại |
| Giả định worker chết thì tác vụ tự chạy lại | ThreadPoolExecutor không cung cấp cam kết đó |
| Chỉ đếm submit không ném ngoại lệ như số thành công | Mới biết tiếp nhận, chưa biết kết quả |

Không cần bắt Throwable ở mọi tác vụ chỉ để che tất cả lỗi nghiêm trọng. Error và các vấn đề tài nguyên có thể đòi hỏi phản ứng khác với lỗi dữ liệu thông thường. Cơ chế bọc có thể lưu Throwable, nhưng quyết định phục hồi phải dựa trên loại lỗi và trạng thái thực của ứng dụng.

## 11. Tự kiểm tra

1. Catch trên luồng gửi có tự bắt RuntimeException phát sinh sau đó trên worker không?
2. Runnable gửi bằng submit có thể báo ExecutionException qua Future.get không?
3. Vì sao uncaught handler không được gọi khi một Callable thông thường thất bại trong FutureTask?
4. afterExecute có Throwable null có đủ để khẳng định kết quả thành công không?
5. Gọi execute với một FutureTask có giống execute với Runnable không bọc về đường báo lỗi không?
6. Nếu worker bị thay thế, công việc đã thất bại có tự được thử lại không?

**Gợi ý:** (1) Không. (2) Có. (3) Lớp bọc ghi nhận lỗi để Future công bố. (4) Không. (5) Không; lớp bọc vẫn giữ lỗi. (6) Không.

Muốn quan sát thất bại đúng, cần xác định **lỗi phát sinh lúc gửi hay lúc chạy, có lớp bọc giữ lỗi hay không, và ai sẽ nhận kết quả cuối cùng của công việc**.
