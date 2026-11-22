# Phân biệt lỗi không được bắt với lỗi được giữ trong Future

## 1. Cùng ném ngoại lệ, nhưng đường báo lỗi có thể khác

Một tác vụ có thể ném `IllegalStateException` trong luồng nền. Kết quả quan sát phụ thuộc vào việc có thành phần nào bắt ngoại lệ trước khi nó thoát khỏi luồng hay không.

Hai đường đi quan trọng là:

```text
Tác vụ ném ngoại lệ
        |
        +-> không được bắt ở biên chạy của luồng
        |        |
        |        +-> luồng kết thúc bất thường
        |        +-> UncaughtExceptionHandler được gọi
        |
        +-> được lớp bọc tác vụ bắt và lưu
                 |
                 +-> Future ghi nhận hoàn tất với lỗi
                 +-> get() báo ExecutionException
```

**Lỗi không được bắt (uncaught exception)** nói về ngoại lệ thoát ra tới biên kết thúc của một luồng. **Lỗi được giữ trong Future** nói về kết quả thất bại của một phép tính bất đồng bộ.

Không thấy stack trace trên console chưa chứng minh tác vụ thành công. Có thể ngoại lệ đang nằm trong một Future mà chưa ai quan sát.

Bài dùng các API còn phù hợp trên Java hiện đại: `Thread.UncaughtExceptionHandler`, `FutureTask`, `ExecutorService` và `Future.get()`. Các chương trình chạy với Java 17+.

## 2. UncaughtExceptionHandler quan sát điều gì?

Khi một luồng sắp kết thúc vì ngoại lệ không được bắt, JVM gọi bộ xử lý ngoại lệ không được bắt của luồng đó, truyền vào luồng và `Throwable`.

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("cannot load configuration");
}, "config-loader");

worker.setUncaughtExceptionHandler((thread, error) -> {
    System.err.println(thread.getName() + ": " + error);
});
worker.start();
```

Đây là đoạn minh họa đặt trong một phương thức. Handler có thể ghi nhận tên luồng, ngoại lệ và ngữ cảnh chẩn đoán. Nó không biến phương thức đã ném lỗi thành thành công và không cho luồng tiếp tục ngay tại lệnh vừa thất bại.

Không có handler riêng, `ThreadGroup` tham gia cơ chế xử lý và có thể chuyển tới handler mặc định. Cách hiển thị cuối cùng phụ thuộc cấu hình; không nên coi một dòng stderr mặc định là toàn bộ chiến lược quan sát lỗi.

Handler cũng không phải chỗ thích hợp cho công việc phục hồi dài, chờ khóa khó dự đoán hoặc tự động chạy lại thao tác có hiệu ứng bên ngoài. Nó đang xử lý tình huống luồng sắp kết thúc.

Hợp đồng về thời điểm gọi và các tham số được quy định trong [Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html).

### try/catch quanh start không bắt được lỗi của worker

```java
try {
    worker.start();
} catch (RuntimeException e) {
    // Không phải nơi nhận ngoại lệ phát sinh về sau trong worker.
}
```

`start()` khởi động một luồng khác. Ngoại lệ trong stack của worker không tự nhảy sang stack của bên gọi. Khối catch trên chỉ nhận lỗi xảy ra đồng bộ ở lời gọi start tương ứng.

Tương tự, `join()` đợi luồng kết thúc nhưng không ném lại ngoại lệ nghiệp vụ của luồng ấy. Cần một kênh báo lỗi riêng nếu bên điều phối phải biết tác vụ thất bại.

## 3. Future lưu một kết quả hoàn tất, bao gồm thất bại

`FutureTask` có thể bọc một `Callable` hoặc `Runnable`. Khi chạy phần tính toán, nó quản lý kết quả thành công, thất bại hoặc hủy theo hợp đồng của Future.

Nếu phần tính toán thất bại và lỗi được lưu, `Future.get()` ném `ExecutionException`; ngoại lệ gốc nằm trong `getCause()`.

```java
try {
    Integer result = future.get();
} catch (ExecutionException e) {
    Throwable cause = e.getCause();
    // Quan sát hoặc chuyển lỗi theo hợp đồng của tầng gọi.
}
```

Đoạn minh họa cần `future`, import và xử lý `InterruptedException` phù hợp. Điểm quan trọng là `ExecutionException` được ném **trong luồng gọi get**, còn nguyên nhân bắt nguồn từ phép tính bất đồng bộ.

`get()` không chạy lại tác vụ. Việc đọc Future cũng không “tiêu thụ rồi xóa” lỗi: các lần get sau của Future đã hoàn tất với lỗi vẫn báo thất bại ấy.

`FutureTask` không phải một loại luồng. Nó triển khai `Runnable` và có thể được một Thread hoặc executor chạy. Ranh giới bắt–lưu lỗi nằm ở lớp bọc phép tính, không nằm ở tên của luồng. Xem [FutureTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/FutureTask.html).

## 4. Thí nghiệm: Thread chạy trực tiếp và Thread chạy FutureTask

Lưu thành `ExceptionBoundaryDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.FutureTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ExceptionBoundaryDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger uncaughtCount = new AtomicInteger();

        Thread direct = new Thread(() -> {
            throw new IllegalStateException("direct failure");
        }, "direct-worker");

        direct.setUncaughtExceptionHandler((thread, error) -> {
            uncaughtCount.incrementAndGet();
            System.out.println("Handler: " + thread.getName()
                    + " -> " + error.getClass().getSimpleName());
        });

        direct.start();
        direct.join();
        System.out.println("After direct: " + uncaughtCount.get());

        FutureTask<Integer> task = new FutureTask<>(() -> {
            throw new IllegalArgumentException("captured failure");
        });

        Thread wrapped = new Thread(task, "future-worker");
        wrapped.setUncaughtExceptionHandler((thread, error) -> {
            uncaughtCount.incrementAndGet();
            System.out.println("Unexpected handler: "
                    + thread.getName());
        });

        wrapped.start();
        wrapped.join();

        System.out.println("Future done: " + task.isDone());
        System.out.println("After FutureTask: " + uncaughtCount.get());

        try {
            task.get();
        } catch (ExecutionException e) {
            System.out.println("get: "
                    + e.getClass().getSimpleName());
            System.out.println("cause: "
                    + e.getCause().getClass().getSimpleName()
                    + " / " + e.getCause().getMessage());
        }
    }
}
```

Chạy:

```shell
javac ExceptionBoundaryDemo.java
java ExceptionBoundaryDemo
```

Stdout:

```text
Handler: direct-worker -> IllegalStateException
After direct: 1
Future done: true
After FutureTask: 1
get: ExecutionException
cause: IllegalArgumentException / captured failure
```

Hai luồng đều thực thi mã ném ngoại lệ, nhưng:

- `direct` để ngoại lệ thoát tới biên luồng, nên handler được gọi.
- `wrapped` chạy `FutureTask`; lỗi phần tính toán được giữ trong task, nên không tới handler của Thread trong tình huống này.
- `task.isDone()` bằng true vì phép tính đã kết thúc với lỗi. Nó không có nghĩa kết quả thành công.
- `task.get()` làm bên điều phối nhận biết thất bại.

`join()` trong thí nghiệm chỉ cố định thời điểm quan sát cho stdout. Nó không phải cơ chế chuyển ngoại lệ từ worker sang main.

## 5. execute và submit trong ThreadPoolExecutor

Trong cách dùng thông thường với `ThreadPoolExecutor`:

| Cách gửi | Đối tượng executor thực thi | Đường quan sát lỗi điển hình |
| --- | --- | --- |
| execute(runnable) với Runnable trực tiếp | Runnable được truyền vào | Lỗi không được bắt có thể thoát khỏi worker và tới handler |
| submit(runnable) | Tác vụ có lớp bọc Future | Future.get báo ExecutionException |
| submit(callable) | Tác vụ có lớp bọc Future | Future.get trả giá trị hoặc báo ExecutionException |
| execute(futureTask) | Chính FutureTask | Lỗi có thể được giữ trong FutureTask |

Do đó, quy tắc chính xác không phải “execute luôn tới handler, submit luôn in lỗi”. Cần xem **đối tượng nào đang được chạy** và ai bắt lỗi ở trong nó.

`ExecutorService.submit` trả một Future để theo dõi kết quả. Nếu chương trình bỏ Future đó, nó có thể bỏ luôn con đường quan sát thất bại. Việc gọi `shutdown()` hoặc `awaitTermination()` không tự lấy và ném lại nguyên nhân lỗi của từng tác vụ.

Đối với Runnable trực tiếp thất bại trong ThreadPoolExecutor, worker có thể kết thúc bất thường và pool có thể thay thế worker theo chính sách của nó. Không được khái quát rằng một tác vụ thất bại làm toàn bộ pool dừng.

[ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html) mô tả việc submit tạo Future và quản lý vòng đời executor.

### Thí nghiệm với handler từ ThreadFactory

Lưu thành `ExecutorFailureDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecutorFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger threadNumber = new AtomicInteger();
        AtomicInteger uncaughtCount = new AtomicInteger();
        CountDownLatch executeFailureObserved = new CountDownLatch(1);

        ThreadFactory factory = runnable -> {
            Thread thread = new Thread(runnable,
                    "pool-worker-" + threadNumber.incrementAndGet());

            thread.setUncaughtExceptionHandler((failed, error) -> {
                uncaughtCount.incrementAndGet();
                System.out.println("execute handler: "
                        + error.getMessage());
                executeFailureObserved.countDown();
            });
            return thread;
        };

        ExecutorService pool = Executors.newFixedThreadPool(1, factory);

        try {
            pool.execute(() -> {
                throw new IllegalStateException("execute failed");
            });

            if (!executeFailureObserved.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("handler not observed");
            }

            Future<?> submitted = pool.submit(() -> {
                throw new IllegalStateException("submit failed");
            });

            try {
                submitted.get(10, TimeUnit.SECONDS);
            } catch (ExecutionException e) {
                System.out.println("submit cause: "
                        + e.getCause().getMessage());
            }

            Future<Integer> next = pool.submit(() -> 42);
            System.out.println("Next result: "
                    + next.get(10, TimeUnit.SECONDS));
            System.out.println("Uncaught count: "
                    + uncaughtCount.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac ExecutorFailureDemo.java
java ExecutorFailureDemo
```

Stdout khi các thao tác hoàn tất trong thời hạn:

```text
execute handler: execute failed
submit cause: submit failed
Next result: 42
Uncaught count: 1
```

Thí nghiệm dùng pool một worker để dễ quan sát nhưng không dựa vào tên hay số lượng worker được tạo. Latch chỉ bảo đảm main đã nhận tín hiệu từ handler của lỗi execute trước khi chuyển sang bước tiếp theo.

Lỗi submit đi qua `ExecutionException`, không làm handler tăng đếm. Tác vụ sau trả 42 cho thấy pool vẫn phục vụ công việc tiếp theo trong tình huống này.

Các giới hạn 10 giây là thời hạn thí nghiệm, không phải lựa chọn chung cho mọi ứng dụng.

## 6. afterExecute không luôn nhận được Throwable của tác vụ submit

`ThreadPoolExecutor` cung cấp hook:

```java
protected void afterExecute(Runnable task, Throwable error)
```

Đây là chữ ký API để nhận diện, không phải một phương thức đã triển khai.

Với Runnable trực tiếp làm worker kết thúc bất thường, tham số `error` có thể phản ánh lỗi thoát ra. Nhưng nếu `task` là một FutureTask đã bắt và giữ lỗi, lời gọi `run()` của lớp bọc có thể trở về bình thường; `error` lúc ấy có thể bằng null dù phép tính bên trong thất bại.

Theo [ThreadPoolExecutor.afterExecute](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#afterExecute(java.lang.Runnable,java.lang.Throwable)), một hook muốn quan sát lỗi được giữ trong Future phải xét trường hợp task là Future và kiểm tra kết quả phù hợp.

Khi thiết kế hook riêng, cần lưu ý:

- Chỉ đọc Future theo cách không làm hook chờ ngoài dự kiến; kiểm tra trạng thái hoàn tất trước khi gọi get theo mẫu phù hợp.
- Phân biệt thất bại, hủy và ngắt của luồng quan sát.
- Lấy nguyên nhân của ExecutionException thay vì chỉ ghi mỗi lớp bọc.
- Không để chính hook ném lỗi từ quá trình ghi nhận hay xử lý.
- Quy định ai là chủ sở hữu việc ghi lỗi để tránh vừa hook vừa bên gọi get cùng báo một sự cố thành hai sự cố.

Hook là cơ chế cho một loại executor cụ thể, không phải hợp đồng chung cho mọi ExecutorService hoặc mọi framework. Không sao chép một giả định về ThreadPoolExecutor sang ScheduledThreadPoolExecutor hay một executor khác mà chưa kiểm tra cách bọc tác vụ của nó.

## 7. ExecutionException khác với các kết quả không thành công khác

| Hiện tượng | Nơi xuất hiện | Ý nghĩa |
| --- | --- | --- |
| ExecutionException | Future.get | Phép tính đã thất bại; nguyên nhân nằm trong cause |
| InterruptedException | Luồng gọi get đang đợi | Chính luồng đợi bị ngắt |
| TimeoutException | get có thời hạn | Lần đợi hết hạn; tác vụ có thể còn chạy |
| CancellationException | get trên Future bị hủy | Kết quả đã ở trạng thái hủy |
| RejectedExecutionException | Lời gọi gửi việc vào executor | Việc gửi bị từ chối theo cơ chế/cấu hình tương ứng |

Bắt ExecutionException không có nghĩa nên bật lại cờ ngắt của luồng gọi get. Cần xem đó là lỗi của phép tính. Ngược lại, khi chính get ném InterruptedException, việc xử lý ngắt ở luồng đang đợi phải được tôn trọng.

Một tác vụ có thể thất bại vì nó nhận InterruptedException. Nếu tác vụ truyền lỗi đó ra phần tính toán, bên gọi có thể thấy nó dưới dạng cause của ExecutionException. Điều ấy khác với InterruptedException do chính luồng gọi get bị ngắt.

Với chính sách từ chối tùy biến của ThreadPoolExecutor, một tác vụ bị từ chối không nhất thiết luôn ném RejectedExecutionException; cần kiểm tra hợp đồng cấu hình để tránh tạo Future không có người hoàn tất rồi đợi mãi.

## 8. Handler và get đều là quan sát, không phải hoàn tác

Khi lỗi đã xảy ra, tác vụ có thể đã:

- Ghi một phần dữ liệu.
- Gửi một yêu cầu tới dịch vụ khác.
- Lấy tài nguyên cần được trả.
- Thay đổi trạng thái chia sẻ trước khi ném ngoại lệ.

Handler được gọi hoặc get ném ExecutionException không tự hoàn tác các hiệu ứng ấy. Dùng `finally` hoặc cơ chế quản lý tài nguyên thích hợp bên trong tác vụ để cleanup phần mình sở hữu.

Không dùng `catch (Throwable)` rồi trả một giá trị giả chỉ để “không mất worker”. Cách đó có thể biến thất bại thành kết quả có vẻ thành công và che cả lỗi nghiêm trọng. Nếu thực sự bắt để thêm ngữ cảnh, phải có chính sách phân loại và truyền/ghi nhận phù hợp; không mặc định mọi Throwable đều có thể phục hồi.

Ngược lại, không cần cố làm ngoại lệ thoát khỏi luồng để được in ra console. Một mô hình Future có bên chịu trách nhiệm quan sát rõ ràng là đường báo lỗi hợp lệ và thường thuận tiện hơn cho điều phối kết quả.

## 9. Chẩn đoán một tác vụ “biến mất mà không có log”

Một trình tự kiểm tra hữu ích:

1. Xác định việc được gửi bằng execute, submit hay thông qua một lớp/framework khác.
2. Xác định Runnable thực sự có phải FutureTask hoặc lớp bọc bắt lỗi không.
3. Tìm Future trả về và bên chịu trách nhiệm đọc kết quả của nó.
4. Kiểm tra có catch nào chỉ nuốt lỗi hoặc đổi sang giá trị mặc định không.
5. Kiểm tra handler/hook có được gắn vào đúng các worker thực tế không.
6. Phân biệt tác vụ thất bại, bị hủy, chưa được chạy và bị từ chối.
7. Ghi nguyên nhân gốc cùng định danh tác vụ, không chỉ tên luồng.

Tên luồng hữu ích khi đọc stack trace nhưng không phải định danh ổn định cho công việc: một worker có thể chạy nhiều tác vụ; một công việc có thể đi qua nhiều tầng bất đồng bộ.

Nếu gửi nhiều tác vụ, cần quan sát từng kết quả ngay cả khi một Future trước đó thất bại. Một vòng get dừng ở lỗi đầu tiên có thể bỏ qua lỗi của những tác vụ còn lại nếu không có chính sách hủy/thu lỗi rõ ràng.

Với việc không cần giá trị trả về, vẫn phải có chủ sở hữu báo lỗi: wrapper ghi nhận có kiểm soát, cơ chế completion hoặc hook phù hợp. “Không cần kết quả” không có nghĩa “không cần biết thất bại”.

## 10. Tự kiểm tra

**Một worker ném RuntimeException có luôn gọi UncaughtExceptionHandler không?**  
Không. Có thể lớp bọc tác vụ đã bắt và giữ ngoại lệ trước khi nó thoát khỏi luồng.

**join() có ném lại lỗi của Thread đã kết thúc không?**  
Không. Nó chỉ tham gia việc đợi vòng đời luồng theo hợp đồng của nó.

**Future.isDone() bằng true có nghĩa tác vụ thành công không?**  
Không. Hoàn tất có thể là thành công, thất bại hoặc hủy.

**Bỏ Future của submit có ảnh hưởng đến đường báo lỗi không?**  
Có. Nếu không có cơ chế quan sát khác, lỗi có thể được giữ mà không được bên ứng dụng ghi nhận.

**execute một FutureTask có giống execute Runnable trực tiếp về đường thoát lỗi không?**  
Không nên giả định như vậy. FutureTask có cơ chế bắt–lưu kết quả thất bại.

Điểm quyết định là biên bắt ngoại lệ: lỗi thoát tới biên luồng đi vào handler, còn lỗi được phép tính bất đồng bộ giữ lại phải được quan sát qua kênh kết quả hoặc cơ chế hoàn tất tương ứng.
