# Try-catch ở luồng tạo không tự bắt lỗi ở luồng con

## 1. Vấn đề: exception đi theo luồng thực thi nào?

Khi một phương thức Java gọi một phương thức khác **trên cùng một thread**, ngoại lệ chưa được bắt có thể lan ngược qua chuỗi lời gọi tới `catch` thích hợp. Nhưng khi code tạo thread khác bằng `Thread.start()`, việc thực thi `run()` diễn ra trên **thread mới với call stack riêng**. Exception phát sinh trong `run()` không “nhảy” ngược sang call stack của thread đã gọi `start()`.

Đây là nguyên tắc quan trọng trong Java Core:

> **`try-catch` bắt exception phát sinh trong luồng thực thi của khối `try`, hoặc được truyền lại qua cơ chế kết quả mà chính luồng đó đọc. Nó không tự bắt lỗi xảy ra bất đồng bộ trong một thread độc lập.**

Xét ý tưởng sau:

~~~java
try {
    Thread worker = new Thread(() -> {
        throw new IllegalStateException("worker failed");
    });
    worker.start();
} catch (IllegalStateException e) {
    System.out.println("caught by creator");
}
~~~

Đây là đoạn minh họa không độc lập, nhưng nội dung cú pháp hợp lệ khi đặt trong một phương thức. `start()` yêu cầu JVM khởi chạy công việc ở thread khác; exception `IllegalStateException` ném từ lambda chạy trong worker. `catch` trên thread tạo **không bắt lỗi này**. Nếu không có `UncaughtExceptionHandler` tùy chỉnh, handler mặc định có thể in stack trace ra luồng lỗi chuẩn; đầu ra cụ thể phụ thuộc môi trường chạy và thiết lập handler.

Tuy vậy, `start()` **có thể tự ném lỗi ngay ở thread gọi**, ví dụ `IllegalThreadStateException` khi cố `start()` cùng một `Thread` lần thứ hai. Lỗi đó thuộc lời gọi `start()` nên có thể được bắt tại thread tạo. Cần phân biệt rõ **lỗi khi yêu cầu tạo/chạy thread** với **lỗi trong công việc mà thread chạy sau đó**.

Sau bài này, bạn sẽ biết cách:
- Giải thích vì sao `catch` ở thread cha không bắt exception của thread con.
- Phân biệt `Thread.start()`, `Thread.run()` và `Thread.join()`.
- Quan sát lỗi của thread bằng `UncaughtExceptionHandler`, hoặc trả lỗi qua `Future`/`CompletableFuture`.
- Xử lý đúng `InterruptedException`, `ExecutionException`, `CompletionException`, cancellation và timeout.
- Thiết kế task có điểm thu nhận lỗi rõ ràng để không bỏ sót thất bại bất đồng bộ.

## 2. Mỗi Java thread có call stack riêng

Hình dung hai luồng:

~~~text
Thread "main"                         Thread "worker"
--------------------------------     --------------------------------
main()                                Thread.run()
  |
  +-- try {                            +-- xử lý task
  |     worker.start()                 |     +-- service.process()
  |     ...                            |           |
  |   } catch (...)                    |           +-- throw
  |                                    |
  +-- chạy tiếp                        +-- không có catch phù hợp
                                        -> UncaughtExceptionHandler
                                        -> thread kết thúc
~~~

Lệnh `start()` tạo ra quan hệ khởi chạy, chứ không phải một lời gọi đồng bộ vào stack của `main`. Khi thread mới gặp exception không được xử lý, JVM tìm handler trên **stack của chính thread đó**. Stack của thread khởi tạo không nằm trong chuỗi gọi này.

Một thread khác có thể quan sát **dữ liệu do thread con ghi** hoặc **một đối tượng kết quả** khi phối hợp đồng bộ đúng. Việc quan sát lỗi cần một trong những cơ chế truyền thông tin đó; quan hệ “tôi tạo ra thread này” tự nó không định nghĩa đường lan truyền exception.

### 2.1. So sánh `run()` và `start()`

~~~java
Runnable task = () -> {
    throw new IllegalStateException("failed");
};

try {
    task.run(); // Gọi đồng bộ trên thread hiện tại.
} catch (IllegalStateException e) {
    System.out.println("caught directly");
}
~~~

Đoạn trên minh họa một `Runnable`, chưa phải file Java có `main`. `run()` chỉ là lời gọi phương thức bình thường: exception lan trên cùng stack nên `catch` nhận được. Nhưng nếu tạo `new Thread(task).start()`, lambda chạy trên thread mới và `catch` quanh `start()` không quan sát exception của lambda.

**Không dùng `run()` thay `start()` chỉ để catch được lỗi**, vì như vậy đã bỏ mục tiêu chạy đồng thời. Hãy chọn cơ chế thu lỗi phù hợp.

## 3. `join()` chờ kết thúc, không chuyển exception của thread con

`Thread.join()` cho phép thread gọi chờ thread đích kết thúc. Nó **không trả đối tượng kết quả** của `run()` và **không ném lại exception chưa bắt** của thread đích.

Có hai nhóm lỗi cần phân biệt:

| Điều xảy ra | Thread nào quan sát trực tiếp? | `join()` có ném lại lỗi công việc không? |
| --- | --- | --- |
| Worker ném `IllegalStateException` và không bắt | Worker, rồi cơ chế uncaught handler | Không |
| Thread đang đợi bị interrupt trong `join()` | Thread đang đợi | `join()` có thể ném `InterruptedException` |
| Worker kết thúc bình thường | Thread tạo có thể thấy sau `join()` | Không có lỗi để ném |
| Worker không bao giờ kết thúc | Thread gọi `join()` vô hạn có thể chờ mãi | Không; cần chính sách chờ/hủy riêng |

Sau khi một lệnh `join()` kết thúc bình thường vì thread đích đã kết thúc, các hành động của thread đích **happens-before** những hành động của thread gọi sau `join()` theo Java Memory Model. Điều đó giúp quan sát state đã được worker ghi theo quy tắc bộ nhớ; nó **không đồng nghĩa nhận exception**. Nếu muốn chuyển lỗi qua state chung, còn cần thiết kế kênh trạng thái và cách xử lý đúng.

Một sai lầm thường gặp là viết:

~~~java
try {
    worker.start();
    worker.join();
} catch (Exception e) {
    // Không thể dựa vào catch này để phát hiện lỗi bên trong worker.
}
~~~

Đây là fragment, giả định `worker` đã khai báo. `Exception` ở đây có thể bắt `InterruptedException` của chính thread đang đợi, hoặc exception khác phát sinh trực tiếp ở thread gọi. Nó không nhận được exception xảy ra trên stack của worker.

## 4. Ví dụ hoàn chỉnh Java 17: ba cơ chế quan sát lỗi

Lưu chương trình sau thành **`ThreadExceptionBoundaryDemo.java`**. Trong cùng một chương trình, nó lần lượt trình diễn:

1. Một `Thread` riêng ném exception; handler của thread nhận lỗi, còn `catch` quanh `start()/join()` không nhận.
2. Một task chạy qua `ExecutorService.submit()`; lỗi được lưu trong `Future` và được báo khi gọi `get()`.
3. Một stage `CompletableFuture` thất bại; caller quan sát lỗi tại `join()` qua `CompletionException`.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadExceptionBoundaryDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread child = new Thread(() -> {
            throw new IllegalStateException("child crashed");
        }, "child");

        child.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("handler: " + thread.getName()
                        + " -> " + error.getMessage()));

        try {
            child.start();
            child.join();
        } catch (IllegalStateException error) {
            System.out.println("creator catch");
        }
        System.out.println("creator continued; terminated=" + !child.isAlive());

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> task = pool.submit(() -> {
                throw new IllegalArgumentException("task failed");
            });
            try {
                System.out.println(task.get());
            } catch (ExecutionException error) {
                System.out.println("future: " + error.getCause().getMessage());
            }

            CompletableFuture<String> stage =
                    CompletableFuture.supplyAsync(() -> {
                        throw new UnsupportedOperationException("stage failed");
                    }, pool);
            try {
                stage.join();
            } catch (CompletionException error) {
                System.out.println("stage: " + error.getCause().getMessage());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa file:

~~~bash
javac --release 17 ThreadExceptionBoundaryDemo.java
java ThreadExceptionBoundaryDemo
~~~

Stdout của ví dụ:

~~~text
handler: child -> child crashed
creator continued; terminated=true
future: task failed
stage: stage failed
~~~

### 4.1. Phân tích output và thứ tự

**Dòng 1:** exception trong `child` không có `catch` trong chính thread; JVM gọi `UncaughtExceptionHandler` do ta thiết lập riêng cho nó. Handler in ra `child crashed`. Handler chạy theo cơ chế xử lý exception chưa bắt của thread đang kết thúc; đừng xem đây là kết quả trực tiếp trả từ `Thread.start()`.

**Dòng 2:** thread `main` đã gọi `child.join()` nên chờ con kết thúc, rồi xác nhận `!child.isAlive() == true`. Dòng `creator catch` **không xuất hiện**, vì worker không ném exception qua stack của `main`.

**Dòng 3:** `submit` trả `Future<Integer>`. Task ném `IllegalArgumentException`, `Future.get()` ném `ExecutionException` có `getCause()` là exception gốc. Không cần “bắt lỗi worker” quanh lệnh `submit`.

**Dòng 4:** `CompletableFuture.supplyAsync` hoàn thành ngoại lệ. `join()` ném `CompletionException`, trong đó `getCause()` là `UnsupportedOperationException("stage failed")`.

Các cơ chế đồng bộ trong chương trình làm cho thứ tự dòng in phía trên xác định: `main` đợi `child` hoàn tất trước khi in dòng thứ hai; nó đợi task từ `Future.get()` trước khi tạo stage tiếp theo trên executor một luồng, rồi `join()` chờ stage đó. Ở ví dụ khác, nếu nhiều thread cùng ghi `System.out` mà không có quan hệ thứ tự như vậy, **không nên cam kết thứ tự stdout**.

Trong ứng dụng thực tế, nếu exception được tạo từ nguồn không kiểm soát, vẫn cần kiểm tra kiểu của `getCause()` và xử lý hoặc chuyển tiếp theo hợp đồng; chỉ in `getMessage()` là minh họa tối giản cho đoạn học này. Nếu caller bị interrupt trong `main`, chữ ký `throws InterruptedException` của ví dụ cho phép lan lỗi, thay vì âm thầm bỏ qua.

## 5. Bắt tại chính thread thực thi

Nếu biết cách xử lý lỗi ở bên trong task, đặt `try-catch` **trong lambda hoặc `Runnable.run()`**:

~~~java
Runnable task = () -> {
    try {
        performWork();
    } catch (IllegalArgumentException e) {
        recordFailure(e);
    }
};
new Thread(task).start();
~~~

Đây là **mã minh họa**, phụ thuộc các hàm `performWork()` và `recordFailure(Exception)` chưa định nghĩa. Vì `catch` thuộc code chạy trong worker, nó có thể nhận lỗi đó. Nhưng sau khi bắt, bạn phải xác định rõ điều kiện task được xem là thất bại hay đã phục hồi thành công. Nếu chỉ log exception rồi cho rằng task đã thành công, thông tin thất bại sẽ không đến nơi điều phối.

Với tác vụ xử lý một request, có thể hợp lý khi catch một exception nghiệp vụ, chuyển thành kết quả nghiệp vụ và tiếp tục; nhưng với lỗi bất thường không khôi phục được, có thể cần truyền lại qua kênh kết quả hoặc báo cho bộ điều phối. Tránh `catch (Throwable ignored)` và đừng nuốt `Error` của JVM chỉ để giữ thread tiếp tục chạy.

### 5.1. Checked exception bên trong `Runnable`

Phương thức `Runnable.run()` không khai báo `throws` cho checked exception. Vì vậy một lambda `Runnable` không thể ném trực tiếp `IOException` mà không xử lý hoặc chuyển đổi.

~~~java
Runnable fileTask = () -> {
    try {
        readFile();
    } catch (java.io.IOException e) {
        throw new java.io.UncheckedIOException("Reading failed", e);
    }
};
~~~

Đây là fragment minh họa với phương thức `readFile() throws IOException` chưa định nghĩa. Việc bọc bằng `UncheckedIOException` bảo toàn `cause`; nếu task không bắt tiếp, exception unchecked này sẽ đi tới cơ chế xử lý lỗi của task/thread. Chuyển checked thành unchecked là một lựa chọn hợp đồng, không phải cách duy nhất: một `Callable<T>` có `call() throws Exception` có thể phù hợp hơn khi sử dụng `ExecutorService.submit()`.

## 6. `UncaughtExceptionHandler`: nhận lỗi khi thread không bắt được

`Thread.UncaughtExceptionHandler` được gọi khi một thread sắp kết thúc do exception chưa được bắt. Có thể đăng ký riêng:

~~~java
Thread t = new Thread(() -> {
    throw new IllegalArgumentException("bad worker input");
}, "validation-worker");

t.setUncaughtExceptionHandler((thread, failure) -> {
    System.err.println(thread.getName() + ": " + failure);
});

t.start();
~~~

Đoạn này không có `main` độc lập. Handler nhận tham số `Thread` và `Throwable`. Cơ chế này hữu ích cho ghi nhận lỗi của những raw thread hoặc bảo vệ process khỏi việc thất bại biến mất khỏi hệ thống quan sát.

Ngoài handler riêng, Java hỗ trợ `Thread.setDefaultUncaughtExceptionHandler(...)` cho một default handler toàn JVM. Nếu không có handler riêng, chuỗi ủy quyền liên quan `ThreadGroup` và default handler được áp dụng theo quy tắc API. Cần hiểu chính xác môi trường chạy trước khi thay đổi default handler toàn tiến trình: thư viện, framework, máy chủ ứng dụng hoặc runner có thể đang dùng cơ chế ghi nhận riêng.

Những giới hạn thiết kế cần nhớ:
- Handler **không biến exception thành exception trên thread tạo**.
- Handler thường hoạt động lúc thread sắp kết thúc vì lỗi chưa bắt; nó không phải cơ chế “khôi phục và chạy lại từ chỗ throw”.
- Handler không nên thực hiện những công việc phức tạp dễ ném exception khác; nếu handler cũng lỗi thì JVM không bảo đảm sẽ có một handler thứ hai cứu kết quả đó.
- Handler không thay thế hệ thống thu kết quả có kiểu. Nếu caller cần biết task thành công/thất bại và tiếp tục theo nhánh, `Future` hoặc `CompletableFuture` thường thích hợp hơn.
- Với task đã được `ExecutorService.submit()` bọc vào `Future`, exception thường được **lưu trong Future**; không thể kỳ vọng uncaught handler nhận được lỗi chỉ vì callable ném exception.

Trong production, thường nên gắn tên thread, mã tác vụ, correlation ID và dữ liệu ngữ cảnh **không nhạy cảm** cho log, thay vì chỉ gọi `printStackTrace()` tự do từ nhiều nơi.

## 7. `ExecutorService`: khác biệt giữa `execute` và `submit`

Một `ExecutorService` nhận công việc để thực thi bởi các worker được quản lý. Cơ chế xử lý exception phụ thuộc phương thức gửi:

| API | Kết quả trả về | Quan sát thất bại từ mã gọi |
| --- | --- | --- |
| `execute(Runnable)` | `void` | Không có `Future`; cần xử lý bên trong task, cơ chế uncaught logging/giám sát của executor, hoặc cơ chế ứng dụng khác |
| `submit(Runnable)` | `Future<?>` | `get()` có thể ném `ExecutionException` nếu task ném exception |
| `submit(Callable<T>)` | `Future<T>` | `get()` trả giá trị hoặc ném `ExecutionException` |
| `invokeAll(...)` | `List<Future<T>>` | Phải quan sát từng `Future` để xác định task nào thất bại |
| `invokeAny(...)` | Giá trị từ một task hoàn thành thành công | Có thể ném `ExecutionException` nếu không có task thành công, cùng các lỗi điều phối phù hợp |

**`submit` không ném exception từ task vào caller khi gọi submit.** Nó trả một đối tượng mà sau này có thể biểu diễn trạng thái chạy/chưa xong, thành công, thất bại hoặc bị hủy. Nếu gọi `submit` rồi bỏ qua `Future`, task có thể thất bại mà không có nhánh ứng dụng nào xử lý lỗi.

Với `execute`, nếu `Runnable.run()` để lọt unchecked exception, ứng xử của worker và cách ghi nhận phụ thuộc executor/ThreadFactory và implementation. Ở `ThreadPoolExecutor` thông thường, task kết thúc bất thường có thể kích hoạt cơ chế xử lý uncaught; tuy nhiên đừng coi `execute` là “sẽ ném lỗi về thread gọi”, cũng không xây logic nghiệp vụ dựa vào stack trace mặc định.

### 7.1. Xử lý `Future.get()` đúng hợp đồng

~~~java
try {
    String value = future.get();
    use(value);
} catch (java.util.concurrent.ExecutionException e) {
    Throwable taskFailure = e.getCause();
    reportTaskFailure(taskFailure);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Fragment giả định `future`, `use` và `reportTaskFailure` tồn tại, và được đặt trong phương thức có thể `return`. `ExecutionException` biểu thị **task đã hoàn tất bằng exception**; nguyên nhân gốc lấy qua `getCause()`. `InterruptedException` biểu thị **thread đang đợi bị yêu cầu ngắt**, không phải bằng chứng rằng task đã thất bại.

Nếu cần giới hạn thời gian chờ, dùng `future.get(timeout, unit)`; khi quá hạn, phương thức ném `TimeoutException`. **Timeout không tự hủy task.** Caller quyết định tiếp tục chờ, báo trạng thái chưa xác định hay gọi `future.cancel(true)` phù hợp. Hủy với `mayInterruptIfRunning=true` chỉ cố yêu cầu interrupt worker đang chạy; việc dừng có hiệu quả hay không tùy task có hợp tác xử lý interrupt và trạng thái tác vụ. Khi `Future` bị hủy, `get()` có thể ném unchecked `CancellationException`.

### 7.2. Tập hợp nhiều Future

Nếu gọi `invokeAll` hoặc gửi 10 tác vụ bằng `submit`, việc tất cả Future đã ở trạng thái done **không có nghĩa tất cả thành công**. `Future.isDone()` trả true cho cả hoàn tất thành công, thất bại và hủy. Muốn có báo cáo đúng, truy xuất từng kết quả và phân biệt:
- giá trị `get()`: thành công;
- `ExecutionException`: thất bại của task;
- `CancellationException`: tác vụ bị hủy;
- `InterruptedException`: thread điều phối bị interrupt khi đợi.

Khi một task thất bại, hãy quyết định có tiếp tục các task khác, hủy các task còn lại, hay trả báo cáo tổng hợp. Không được suy từ một future thất bại rằng các future đã chạy trước đó không gây side effect.

## 8. `CompletableFuture`: exception đi theo chuỗi stage

`CompletableFuture<T>` vừa đại diện cho kết quả bất đồng bộ, vừa cung cấp các stage biến đổi. Một stage có thể **hoàn thành ngoại lệ** (*complete exceptionally*). Các phép nối stage sẽ truyền thất bại tới stage tiếp theo khi không có cơ chế phục hồi phù hợp.

### 8.1. Cách quan sát lỗi

| API | Khi stage thất bại | Cách sử dụng |
| --- | --- | --- |
| `join()` | Ném unchecked `CompletionException`; trường hợp bị hủy có thể ném `CancellationException` | Tiện khi caller không muốn checked exception |
| `get()` | Ném checked `ExecutionException`; cũng có thể `InterruptedException` | Dùng khi cần giao thức `Future` |
| `get(timeout, unit)` | Giống `get()` và thêm `TimeoutException` | Giới hạn thời gian chờ |
| `exceptionally(fn)` | Biến failure thành giá trị thay thế nếu xử lý thành công | Phục hồi theo chính sách |
| `handle((value, error) -> ...)` | Nhận cả nhánh thành công và lỗi, tạo kết quả mới | Tổng hợp hai nhánh |
| `whenComplete((value, error) -> ...)` | Quan sát kết quả và thực hiện side effect, thường không biến failure thành success | Ghi metric/log/cleanup có kiểm soát |

Ví dụ đoạn biểu thức:

~~~java
CompletableFuture<String> recovered =
        CompletableFuture.<String>supplyAsync(() -> {
            throw new IllegalStateException("remote data failed");
        }).exceptionally(error -> "fallback");
~~~

Đây là fragment, cần import `java.util.concurrent.CompletableFuture` và một phương thức bao quanh. Nếu supplier thất bại, stage `exceptionally` trả `fallback` nên `recovered.join()` có thể trả chuỗi thành công. Nhưng **việc trả fallback là quyết định nghiệp vụ**, không phải lúc nào cũng đúng. Với giao dịch thanh toán, không thể thay lỗi gửi lệnh bằng “success” tùy ý.

Một stage nối bằng `thenApply` có thể bị bỏ qua khi stage trước hoàn thành ngoại lệ; lỗi được truyền trong chuỗi, nên cần xử lý tại điểm quan sát thích hợp. Nếu tạo chuỗi:

~~~java
CompletableFuture<String> result = loadAsync()
        .thenApply(value -> transform(value))
        .whenComplete((value, failure) -> recordOutcome(value, failure));
~~~

thì đây chỉ là fragment minh họa với các hàm chưa khai báo. Nếu `loadAsync` hoặc `transform` thất bại, `whenComplete` có thể nhận lỗi để ghi nhận; nó không mặc nhiên xóa trạng thái thất bại. Nếu chính action của `whenComplete` ném exception thì cách stage kết quả hoàn tất phụ thuộc việc stage gốc đã thành công hay lỗi, theo quy tắc `CompletionStage`.

### 8.2. Không bỏ quên chuỗi bất đồng bộ

~~~java
CompletableFuture.runAsync(() -> saveSomething());
System.out.println("request accepted");
~~~

Fragment giả định `saveSomething`. Lệnh in chỉ thể hiện việc đã lên lịch xử lý, **không phải đã lưu thành công**. Nếu không lưu future để quan sát hoặc không gắn một nhánh xử lý lỗi đáng tin cậy, thất bại có thể trở thành một trạng thái không được ứng dụng xử lý.

Không chỉ bắt exception quanh `runAsync(...)` rồi cho là đã xử lý lỗi bên trong lambda: exception có thể đến sau khi lời gọi `runAsync` trả về. Khi trả future cho caller, cần thể hiện trong API liệu caller phải `join/get`, đăng ký callback, hay hệ thống sẽ quản lý task tới kết thúc.

## 9. `InterruptedException` và hủy task không giống task exception

`InterruptedException` có ý nghĩa riêng trong xử lý concurrency. Khi một thread đang ngủ, chờ `join` hoặc chờ `Future.get()` mà bị interrupt, API chờ có thể ném `InterruptedException`. Điều này phản ánh **thread chờ bị yêu cầu ngắt**, chứ không nói gì chắc chắn về kết quả của thread/task đang được chờ.

Trong mã `Runnable`, mẫu phổ biến:

~~~java
Runnable pollingTask = () -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            Thread.sleep(1_000);
            pollOnce();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return;
        }
    }
};
~~~

Đây là fragment dùng `pollOnce()` giả định. Khi bị interrupt trong `sleep`, Java ném `InterruptedException` và thường đã xóa interrupt status trong quá trình ném. Gọi lại `Thread.currentThread().interrupt()` giúp tầng trên biết yêu cầu ngắt; sau đó kết thúc task thay vì nuốt lỗi rồi tiếp tục chạy vô hạn. Nếu phương thức của bạn cho phép `throws InterruptedException`, một lựa chọn khác là truyền tiếp lỗi.

Không bao giờ coi `interrupt()` là cơ chế bắt buộc giết thread lập tức. Tác vụ CPU-bound không kiểm tra interrupt, thư viện chặn không hỗ trợ interrupt hoặc thao tác I/O cụ thể có thể tiếp tục. Việc gọi `Future.cancel(true)` cũng chỉ yêu cầu hủy theo hợp đồng Future và khả năng hợp tác của tác vụ, không tự rollback mọi hiệu ứng đã có.

## 10. Truyền lỗi bằng dữ liệu có kiểm soát

Nếu không dùng executor nhưng caller cần lấy lỗi từ một `Thread` tự tạo, có thể dùng một kênh chia sẻ có đồng bộ rõ ràng, chẳng hạn `AtomicReference<Throwable>`, hoặc một `BlockingQueue` chứa kết quả có kiểu. Một mẫu đơn giản:

~~~java
import java.util.concurrent.atomic.AtomicReference;

class CaptureThreadFailure {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                throw new IllegalStateException("validation failed");
            } catch (RuntimeException e) {
                failure.set(e);
            }
        });
        worker.start();
        worker.join();

        if (failure.get() != null) {
            System.out.println(failure.get().getMessage());
        }
    }
}
~~~

Nếu lưu thành `CaptureThreadFailure.java`, biên dịch/chạy:

~~~bash
javac --release 17 CaptureThreadFailure.java
java CaptureThreadFailure
~~~

Stdout:

~~~text
validation failed
~~~

Ở đây **worker chủ động bắt và lưu exception** vào `AtomicReference`; main gọi `join()` để chờ, rồi đọc lỗi. `join()` không tự bắt lỗi — nó chỉ tạo điểm phối hợp khiến main biết khi nào task đã hoàn tất. Với mẫu này, exception sẽ không tự chạy tới `UncaughtExceptionHandler` vì đã được catch trong worker. Nếu caller muốn ném lại thì tự quyết định cách chuyển đổi, ví dụ xét loại exception và bọc thành exception phù hợp với hợp đồng của caller.

Trong chương trình phức tạp, nên ưu tiên `Future`/`CompletableFuture` hoặc một abstraction quản lý lifecycle; chúng xử lý trạng thái completion/cancellation thuận tiện hơn việc tự phối hợp nhiều cờ, references và handlers. Với task có giá trị hoặc nhiều loại lỗi nghiệp vụ dự kiến, cũng có thể trả một result type có cấu trúc thay vì ném exception cho các trạng thái bình thường.

## 11. Vị trí catch đúng khi thiết kế ứng dụng đa luồng

Một thiết kế thực tế có các ranh giới khác nhau:

~~~text
Thread A: nhận yêu cầu
    |
    +-- submit/khởi chạy task trên Thread B
    |        |
    |        +-- catch lỗi có thể phục hồi ngay tại B
    |        +-- lỗi khác -> Future/CompletionStage/handler
    |
    +-- A tiếp tục làm việc
    |
    +-- A lấy kết quả/callback khi phù hợp
             |
             +-- success -> xử lý giá trị
             +-- failure -> kiểm tra cause và quyết định
             +-- cancel/timeout -> xử lý trạng thái điều phối
~~~

Chọn cơ chế dựa trên nhu cầu:
- **Task tự chịu trách nhiệm phục hồi:** xử lý bằng `try-catch` ngay trong task; nếu không thể phục hồi, phản ánh trạng thái thất bại.
- **Caller cần biết task thành công hay thất bại:** dùng `Callable` + `Future`, hoặc `CompletableFuture`/`CompletionStage` và quan sát kết quả ở ranh giới điều phối.
- **Raw thread lỗi bất thường:** đăng ký `UncaughtExceptionHandler` để log/giám sát, đồng thời tránh dựa vào nó để truyền kết quả nghiệp vụ.
- **Nhiều task cùng tham gia một công việc:** phải có quy tắc chờ/hủy/tổng hợp kết quả; thread khác đã hoàn thành có thể đã gây side effect trước khi một task thất bại.
- **Task không cần phản hồi cho request hiện tại:** hệ thống vẫn cần một nơi sở hữu lifecycle, ghi nhận exception và cơ chế retry/đối soát nếu có side effect bền vững.

Chú ý **lifecycle**: nếu trả response từ thread nhận yêu cầu trước khi task bất đồng bộ xong, cần phân biệt “đã tiếp nhận” với “đã xử lý thành công”. Exception đến sau đó không thể tự sửa response đã trả; thường phải thông báo trạng thái qua job ID, callback, polling hoặc kênh giao tiếp tương ứng.

### 11.1. Không kết luận mọi task thành công chỉ vì chờ xong

`Thread.join()` thành công, `CountDownLatch.await()` trả về, `Future.isDone() == true`, hoặc mọi task đã hoàn thành đều chỉ nói về một **mốc đồng bộ/trạng thái hoàn tất**. Muốn biết thành công, cần kiểm tra kết quả hoặc kênh lỗi được thiết kế. Tương tự, `ExecutorService.awaitTermination(...)` cho biết executor đã chấm dứt sau shutdown trong thời hạn, chứ không báo rằng mọi task không ném exception.

Đây cũng là chỗ exception và **bảo toàn trạng thái** giao nhau: worker có thể ghi một phần dữ liệu, rồi ném exception. Dù main biết lỗi qua Future, những ghi nhận, HTTP request hay phép thay đổi trước lỗi vẫn có thể đã xảy ra. Thu exception giúp quan sát thất bại; muốn phục hồi phải dùng transaction, bù trừ, idempotency hoặc quy tắc trạng thái phù hợp.

## 12. Lỗi phổ biến và cách sửa

| Anti-pattern | Điều sai | Hướng sửa |
| --- | --- | --- |
| Đặt `try-catch` ngoài `thread.start()` để bắt lỗi worker | Khác call stack | Catch trong worker, handler hoặc kết quả Future |
| Tin `join()` sẽ ném lỗi từ `run()` | `join()` chỉ đợi, có thể bị interrupt | Kết hợp `join` với kênh trạng thái, hoặc dùng Future |
| Gọi `run()` để “bắt được exception” | Chạy đồng bộ, không tạo thread | Dùng `start()` và cơ chế thu lỗi phù hợp |
| `submit()` rồi không lưu/đọc Future | Failure có thể không được caller quan sát | Giữ Future và gọi `get`/gắn quy trình quản lý |
| Catch `ExecutionException` nhưng chỉ in `getMessage()` | Mất ngữ cảnh lỗi gốc | Xem `getCause()`, chuyển đổi/ghi nhận thích hợp |
| Catch `InterruptedException` rồi bỏ qua | Mất tín hiệu hủy khi tầng trên cần biết | Truyền tiếp hoặc restore interrupt status và kết thúc |
| Catch `Throwable` để “không thread nào chết” | Che `Error` và lỗi hỏng trạng thái | Chỉ catch loại cần xử lý, có chính sách thất bại |
| Cho rằng `cancel(true)` chấm dứt mọi tác vụ | Interrupt mang tính hợp tác | Thiết kế timeout/hủy đúng loại task |
| Cho rằng `whenComplete` đã phục hồi lỗi | Callback thường chỉ quan sát | `exceptionally` hoặc `handle` khi thật sự muốn phục hồi |
| Xử lý exception xong nhưng không xử lý partial side effect | Thu được lỗi ≠ rollback | Thiết kế transaction, idempotency và compensation |

### 12.1. “Main không catch nhưng chương trình vẫn tiếp tục” có nghĩa gì?

Một exception không bắt trong worker thông thường làm worker đó kết thúc; **không tự làm JVM thoát lập tức** khi thread khác vẫn chạy. Điều này còn phụ thuộc số lượng và trạng thái daemon/non-daemon thread, chính sách ứng dụng và quá trình shutdown. Ngược lại, một executor có thể thay thread worker sau sự cố tùy implementation, khiến ứng dụng trông vẫn hoạt động dù task cụ thể đã thất bại.

Vì vậy, việc process còn sống, REST server vẫn trả request khác, hoặc log chỉ xuất hiện một stack trace **không chứng minh tác vụ quan trọng đã thành công**. Cần cơ chế theo dõi lỗi/khả năng hoàn thành ở cấp công việc.

## 13. Kiểm thử ngoại lệ ở nhiều thread

Đừng chỉ assert rằng lời gọi `start()` không ném. Tạo những kiểm thử đặc tả:
1. **Raw Thread:** đặt handler riêng, cho worker ném exception, gọi `join()`, assert handler nhận đúng loại và nội dung; assert `catch` quanh `start()/join()` không phải nơi nhận lỗi.
2. **Worker tự catch:** cho worker ghi lỗi vào kênh kết quả; sau `join()` kiểm tra dữ liệu, không phụ thuộc `Thread.sleep` để đoán khi nào xong.
3. **ExecutorService.submit:** task ném exception; `get()` ném `ExecutionException` và `getCause()` là lỗi mong đợi.
4. **CompletableFuture:** stage thất bại; `join()` ném `CompletionException`, `get()` ném `ExecutionException`; `exceptionally/handle` có thể chuyển thành kết quả khác theo chính sách.
5. **Interruption:** interrupt thread đang chờ; bảo đảm code xử lý đúng `InterruptedException` và giữ/công bố tín hiệu hủy theo hợp đồng.
6. **Timeout/cancellation:** kiểm tra task chưa bị xem là thành công chỉ vì caller hết thời gian chờ, và quy tắc hủy phù hợp.
7. **Side effect:** task ghi dữ liệu rồi lỗi; khẳng định trạng thái sau lỗi đúng thiết kế, không giả định thu exception nghĩa là rollback.

Với test nhiều thread, tránh khẳng định chính xác thứ tự log khi không có đồng bộ. Ưu tiên `CountDownLatch`, `Future.get(timeout, unit)`, `join` có thời hạn hoặc công cụ test concurrency phù hợp để điều phối có giới hạn; hạn chế dùng `Thread.sleep` như cách “chờ đại” trong test. Khi test hoàn thành, cần shutdown executor và giải phóng resource thuộc sở hữu test.

## 14. Checklist áp dụng

- [ ] Đã xác định exception phát sinh ở **thread nào** và khối `catch` chạy trên thread nào.
- [ ] Không chờ `catch` quanh `start()` bắt exception trong `run()`.
- [ ] Dùng `join()` đúng vai trò chờ kết thúc; có kênh kết quả riêng nếu cần biết success/failure.
- [ ] Thread độc lập có cơ chế quan sát lỗi không bắt, ví dụ `UncaughtExceptionHandler` thích hợp.
- [ ] Task `submit` được theo dõi thông qua Future; `ExecutionException.getCause()` được xử lý.
- [ ] Stage `CompletableFuture` được quan sát hoặc phục hồi có chủ đích; phân biệt `get` với `join`.
- [ ] `InterruptedException`, timeout và cancellation có chính sách riêng, không nhầm với exception của công việc.
- [ ] Lỗi không bị nuốt và không bị đánh đồng với task thành công.
- [ ] Nếu task có side effect, đã xác định cần rollback, bù trừ hay đối soát khi task thất bại.
- [ ] Có kiểm thử riêng cho exception ở worker, ở thread điều phối, trong callback và khi task bị hủy.

### Bài tập thực hành

Viết một API `loadAll(List<String> ids)` dùng `ExecutorService` để tra cứu nhiều mã song song. Mỗi task có thể trả bản ghi, báo “không tìm thấy” hoặc ném exception I/O. Hãy xác định cách caller phân biệt đủ ba kết quả; cách thu tất cả failure từ các Future mà không bỏ quên tác vụ còn lại; cách hủy khi request timeout; và lý do `try-catch` đặt quanh vòng lặp gọi `submit()` không thay thế được việc quan sát `Future.get()`.

Sau đó thay bằng `CompletableFuture`, thử `handle` để biến mỗi stage thành một kết quả có cấu trúc, rồi kiểm thử trường hợp một stage thất bại trước khi các stage khác hoàn thành. Đừng cam kết thứ tự hoàn thành trừ khi chính thiết kế đã áp dụng đồng bộ hoặc sắp xếp kết quả.

**Điểm cốt lõi:** Một exception lan theo call stack nơi nó phát sinh. Thread tạo và thread con có stack riêng; muốn chuyển thất bại qua ranh giới này, bạn phải **thiết kế kênh quan sát rõ ràng** như handler, Future hoặc CompletionStage.