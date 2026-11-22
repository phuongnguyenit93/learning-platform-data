# Đặt tên luồng và thiết lập UncaughtExceptionHandler trong Java

## 1. Mục tiêu bài học

Khi nhiều luồng cùng hoạt động, tên luồng giúp người phát triển xác định **luồng nào đang thực hiện công việc gì** trong log, debugger, thread dump và công cụ giám sát. `Thread.UncaughtExceptionHandler` cung cấp một điểm **ghi nhận lỗi cuối cùng** khi một `Throwable` thoát khỏi phương thức chạy của luồng mà không được bắt.

Sau bài này, bạn cần có khả năng:

- Tạo và đổi tên một `Thread`; chọn tên có ý nghĩa khi xử lý đồng thời.
- Đọc tên của luồng hiện tại bằng `Thread.currentThread().getName()` và phân biệt tên luồng với định danh của một tác vụ.
- Cài handler cho một luồng riêng lẻ hoặc handler mặc định của JVM, hiểu thứ tự lựa chọn handler.
- Hiểu khi nào handler được gọi, khi nào lỗi nằm trong `Future` hoặc `CompletableFuture` và không đi qua handler.
- Viết ví dụ Java 17+ có thể chạy, rồi xác minh tên luồng và đường đi của exception.

Bài tập trung vào **Thread API và concurrency Java nói chung**, không đi vào cơ chế bất đồng bộ hoặc cấu hình executor của Spring.

## 2. Tại sao tên luồng quan trọng?

JVM có thể chạy nhiều thread với các nhiệm vụ khác nhau: nhận dữ liệu, xử lý tệp, tính toán, đọc hàng đợi, dọn dẹp hoặc thực hiện công việc nền. Nếu log chỉ hiển thị `Thread-0`, `Thread-1`, người đọc khó biết nguồn gốc và vai trò của một luồng khi lỗi xảy ra.

Ví dụ một thông báo như:

~~~text
[import-parser-2] Invalid input at row 18
~~~

thường dễ truy vết hơn:

~~~text
[Thread-7] Invalid input at row 18
~~~

Tên luồng đặc biệt hữu ích khi:

1. **Đọc thread dump:** phân biệt luồng đang chờ I/O, giữ lock, chờ queue hoặc bị kẹt.
2. **Tìm log theo thành phần:** nhóm các log của worker theo tiền tố tên.
3. **Gỡ lỗi trong IDE/JFR:** liên hệ một thread với nhóm tác vụ, pool hoặc chức năng.
4. **Điều tra lỗi bất ngờ:** handler có thể ghi cả tên thread và stack trace của exception.

Tên luồng là **thông tin mô tả và hỗ trợ quan sát**, không phải định danh toàn cục có bảo đảm duy nhất, không phải cơ chế đồng bộ, bảo mật hay kiểm soát quyền. Hai thread vẫn có thể có cùng tên; đổi tên không thay đổi thứ tự thực thi hoặc tính thread-safe của code.

## 3. API đặt tên và đọc tên thread

### 3.1. Đặt tên ngay khi tạo thread

Hai cách cơ bản:

~~~java
// Minh họa: Runnable task đã được khai báo.
Thread first = new Thread(task, "file-reader-1");
Thread second = new Thread(task);
second.setName("file-reader-2");
~~~

`new Thread(Runnable, String)` đặt tên tại thời điểm tạo; `setName(String)` đổi tên sau khi tạo. Nên đặt tên **trước `start()`** để mọi sự kiện từ khi luồng bắt đầu đều mang tên mong muốn. Cả hai cách đều không tự chạy task; gọi `start()` mới khởi động một luồng thực thi mới.

`Thread.getName()` đọc tên của một đối tượng `Thread`. Bên trong task đang chạy, `Thread.currentThread().getName()` trả về tên của **luồng thực thi hiện tại**. Không nên dùng biến `thread` từ bên ngoài để thay cho `currentThread()` khi task có thể chạy trên nhiều thread.

### 3.2. Đổi tên khi luồng đang chạy

Java cho phép gọi `setName` trên một thread đã khởi động. Tuy nhiên, tên có thể đổi giữa các thời điểm ghi log, khiến việc ghép dấu vết khó hiểu. Với worker dùng lại trong pool, đổi tên theo từng yêu cầu mà quên khôi phục còn làm log của tác vụ sau mang tên tác vụ trước.

Nếu thật sự cần đổi tên tạm thời, phải khôi phục bằng `finally`:

~~~java
// Minh họa nằm trong một task đang chạy, không phải chương trình độc lập.
Thread current = Thread.currentThread();
String previousName = current.getName();
try {
    current.setName("image-transform-temporary");
    processImage(); // Phương thức do ứng dụng định nghĩa.
} finally {
    current.setName(previousName);
}
~~~

Trong phần lớn hệ thống, cách ổn định hơn là giữ **tên worker** cố định và đưa request ID, job ID hoặc correlation ID vào cấu trúc log/context riêng. Không đặt dữ liệu nhạy cảm, token hoặc thông tin cá nhân vào tên luồng vì tên có thể xuất hiện trong thread dump và hệ thống quan sát.

### 3.3. Quy ước đặt tên

Một quy ước dễ đọc là `<thành-phần>-<vai-trò>-<số-thứ-tự>`. Ví dụ:

| Tên | Vai trò gợi ý |
| --- | --- |
| `import-parser-1` | Worker thứ nhất phân tích dữ liệu nhập |
| `report-writer-2` | Worker thứ hai tạo báo cáo |
| `socket-reader-1` | Worker đọc dữ liệu mạng |
| `batch-cpu-3` | Worker xử lý tính toán |

Đặt tên ngắn, ổn định, có tiền tố đặc trưng và không trộn tên **thread** với mã **task**. Thứ tự các số trong tên không nói lên thứ tự chạy hay hoàn tất.

## 4. Ví dụ 1 — đặt tên và bắt lỗi không được xử lý (Java 17+)

Tạo tệp `NamedThreadDemo.java`:

~~~java
public class NamedThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println(
                "Running: " + Thread.currentThread().getName()
            );
            throw new IllegalStateException("invalid payload");
        }, "import-validator-1");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            System.out.println(
                "Uncaught in " + thread.getName() + ": "
                + error.getClass().getSimpleName()
                + " (" + error.getMessage() + ")"
            );
        });

        worker.start();
        worker.join();
        System.out.println(
            "Main finished; worker isAlive=" + worker.isAlive()
        );
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NamedThreadDemo.java
java NamedThreadDemo
~~~

Đầu ra tiêu chuẩn (stdout) chính xác:

~~~text
Running: import-validator-1
Uncaught in import-validator-1: IllegalStateException (invalid payload)
Main finished; worker isAlive=false
~~~

Diễn giải:

1. Tên `import-validator-1` được gán trước khi `start()`, nên `currentThread().getName()` bên trong `Runnable` trả về tên đó.
2. `IllegalStateException` thoát khỏi phương thức chạy mà không có `catch`. JVM gọi handler đã đăng ký với `worker`.
3. Handler nhận đúng đối tượng `Thread` và `Throwable`, sau đó in tên, loại lỗi và thông điệp.
4. `join()` khiến luồng `main` đợi `worker` kết thúc, vì vậy dòng cuối được in sau khi worker xử lý xong đường thoát bất thường. `isAlive()` lúc đó là `false`.
5. Handler tùy chỉnh đã xử lý việc báo lỗi, nên không có stack trace mặc định do handler mặc định in ra. Trong hệ thống thật, nên ghi **đầy đủ exception/stack trace** vào bộ ghi log có khả năng chịu lỗi; chỉ in `getMessage()` là chưa đủ để chẩn đoán.

**Lưu ý:** Handler không làm cho task thành công và không khởi động lại thread. Sau khi exception không được bắt thoát ra ngoài, worker chấm dứt. `join()` xác nhận thread kết thúc nhưng không tự báo task thành công; cần một kênh kết quả/trạng thái rõ ràng nếu nghiệp vụ phải biết thất bại.

## 5. UncaughtExceptionHandler hoạt động như thế nào?

### 5.1. Giao diện và thời điểm kích hoạt

`Thread.UncaughtExceptionHandler` là một functional interface với phương thức:

~~~java
// Chữ ký API; không phải một chương trình độc lập.
void uncaughtException(Thread thread, Throwable error);
~~~

JVM thông báo tới handler khi một thread sắp kết thúc do một **uncaught exception** — một `Throwable` đã thoát khỏi đường thực thi của luồng. `Throwable` bao gồm `RuntimeException` và cả `Error`; handler có thể thấy những lỗi nghiêm trọng như `OutOfMemoryError`, nhưng lúc đó không được giả định còn đủ tài nguyên để ghi log hay khôi phục.

Handler **không được gọi** chỉ vì:

- Một phương thức ném exception rồi được `try/catch` xử lý trong cùng luồng.
- Task kết thúc bình thường, trả về `run()` hoặc bị yêu cầu dừng bằng cơ chế hợp lệ.
- Task báo lỗi qua một kênh đã bắt/giữ exception, ví dụ `Future` của `submit()`.
- Có lời gọi `Thread.interrupt()` đơn thuần. Interrupt là tín hiệu phối hợp; nó không tự biến thành uncaught exception.

Nếu gọi `worker.run()` trực tiếp thay vì `worker.start()`, code chạy trên luồng gọi, không tạo luồng mới. Exception thoát khỏi lời gọi `run()` sẽ truyền lên caller theo quy tắc Java thông thường; không nên mong handler của đối tượng `worker` được sử dụng như lúc một thread thực sự chết do exception.

### 5.2. Handler theo từng thread và handler mặc định

| API | Phạm vi | Cách dùng |
| --- | --- | --- |
| `thread.setUncaughtExceptionHandler(handler)` | Một thread cụ thể | Ghi lỗi của worker có vai trò riêng |
| `thread.getUncaughtExceptionHandler()` | Xem handler áp dụng trực tiếp cho thread | Trả handler đã gán riêng; nếu không, trả `ThreadGroup` của thread |
| `Thread.setDefaultUncaughtExceptionHandler(handler)` | Handler mặc định ở mức tiến trình JVM | Điểm ghi nhận cuối cùng cho thread không có xử lý chuyên biệt |
| `Thread.getDefaultUncaughtExceptionHandler()` | Xem handler mặc định toàn cục | Có thể trả `null` nếu chưa được cấu hình |

**Thứ tự quan trọng:**

1. Nếu thread có handler riêng đã đặt bằng `setUncaughtExceptionHandler`, handler đó được chọn.
2. Nếu không, `Thread.getUncaughtExceptionHandler()` chuyển việc xử lý tới `ThreadGroup` của thread. Cơ chế `ThreadGroup.uncaughtException` mặc định có thể ủy quyền cho nhóm cha, rồi handler mặc định của JVM (nếu có); nếu vẫn không có, nó có thể in lỗi ra `System.err`.
3. Một `ThreadGroup` tùy biến có thể ghi đè `uncaughtException` và xử lý theo cách khác. Vì vậy không nên giả định handler mặc định sẽ luôn chạy cho mọi thread.

`ThreadGroup` là cơ chế cũ của Thread API; với code mới, nên ưu tiên cấu hình handler rõ ràng trên thread hoặc qua `ThreadFactory`, và quản lý vòng đời bằng executor hoặc cấu trúc phù hợp.

### 5.3. Có nên đặt handler mặc định?

Nếu ứng dụng muốn có nơi báo lỗi cuối cùng cho các thread chưa có handler riêng, có thể cài:

~~~java
// Minh họa cấu hình khi khởi động ứng dụng, không phải chương trình độc lập.
Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    System.err.println(
        "Unhandled failure in thread: " + thread.getName()
    );
    error.printStackTrace(System.err);
});
~~~

Đây là **thay đổi trạng thái toàn cục của JVM**. Chỉ thành phần sở hữu vòng đời ứng dụng nên quyết định cài handler mặc định, thường ở lúc khởi động, sau khi xem xét cấu hình và logging sẵn có. Thư viện tái sử dụng không nên tự thay handler mặc định của toàn bộ ứng dụng; nhiều thành phần cùng ghi đè sẽ khiến lỗi đi vào handler không mong muốn.

Không phụ thuộc vào việc `getUncaughtExceptionHandler()` của từng thread sẽ trả trực tiếp handler mặc định: khi không có handler riêng, nó trả `ThreadGroup` như mô tả ở trên.

## 6. Đặt tên và cài handler cho worker tạo bởi ExecutorService

Trong chương trình có nhiều task, thường không tạo một `Thread` thủ công cho mỗi task. `ExecutorService` quản lý worker; muốn đặt tên và handler cho **worker thread**, sử dụng `ThreadFactory` khi tạo executor.

Một factory có thể làm ba việc: tạo `Thread` mới, sinh tên theo vai trò + thứ tự, và đăng ký `UncaughtExceptionHandler` trước khi thread chạy.

### 6.1. Phân biệt `execute()` và `submit()` khi task ném lỗi

Đây là điểm thường gây hiểu nhầm:

- Với `execute(Runnable)` trên `ThreadPoolExecutor` chuẩn, nếu `Runnable.run()` ném `RuntimeException` ra ngoài, worker có thể kết thúc bất thường và handler của worker được gọi. Executor có thể thay worker để tiếp tục duy trì pool.
- Với `submit(Runnable)` hoặc `submit(Callable)`, executor thường bọc task trong `FutureTask`. Exception được **giữ làm trạng thái thất bại của `Future`**. `future.get()` ném `ExecutionException` có `getCause()` là lỗi gốc; handler của worker **không được gọi chỉ vì task đó thất bại**.
- Với `CompletableFuture`, lỗi có thể được lưu trong trạng thái hoàn thành thất bại và quan sát qua `join()`, `get()`, `handle()`, `exceptionally()` hoặc nhánh xử lý lỗi phù hợp; không mặc định trông chờ vào uncaught handler.

Sự khác nhau ở trên mô tả cách hoạt động của các executor chuẩn thường dùng trong JDK, nhất là `ThreadPoolExecutor`. Một `Executor` tự cài đặt có thể chọn cách điều phối/xử lý lỗi riêng. Luôn hiểu hợp đồng của executor cụ thể.

### 6.2. Ví dụ 2 — ThreadFactory, execute và submit (Java 17+)

Tạo tệp `ExecutorFailureDemo.java`:

~~~java
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
        AtomicInteger sequence = new AtomicInteger(1);
        AtomicInteger handlerCalls = new AtomicInteger();
        CountDownLatch handlerCalled = new CountDownLatch(1);

        ThreadFactory factory = task -> {
            Thread worker = new Thread(
                task,
                "report-worker-" + sequence.getAndIncrement()
            );
            worker.setUncaughtExceptionHandler((thread, error) -> {
                handlerCalls.incrementAndGet();
                System.out.println(
                    "Handler: " + thread.getName() + " -> "
                    + error.getClass().getSimpleName()
                );
                handlerCalled.countDown();
            });
            return worker;
        };

        ExecutorService executor =
            Executors.newSingleThreadExecutor(factory);

        try {
            Future<?> failed = executor.submit(() -> {
                throw new IllegalArgumentException("submit failure");
            });

            try {
                failed.get();
            } catch (ExecutionException error) {
                System.out.println(
                    "Future cause: "
                    + error.getCause().getClass().getSimpleName()
                );
            }
            System.out.println(
                "Handler calls after submit: " + handlerCalls.get()
            );

            executor.execute(() -> {
                throw new IllegalStateException("execute failure");
            });

            if (!handlerCalled.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Timed out waiting for uncaught handler"
                );
            }
            System.out.println(
                "Handler calls after execute: " + handlerCalls.get()
            );
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ExecutorFailureDemo.java
java ExecutorFailureDemo
~~~

Khi hai task được chạy theo thứ tự như trong chương trình và handler được gọi trong giới hạn 5 giây, stdout là:

~~~text
Future cause: IllegalArgumentException
Handler calls after submit: 0
Handler: report-worker-1 -> IllegalStateException
Handler calls after execute: 1
~~~

Vì sao kết quả như vậy?

- `submit` tạo `Future` giữ `IllegalArgumentException`; `get()` phát hiện lỗi, nhưng thread xử lý không kết thúc bất thường nên bộ đếm handler vẫn là 0.
- `execute` chạy `Runnable` trực tiếp theo cơ chế của `ThreadPoolExecutor`. `IllegalStateException` thoát khỏi worker, làm worker kết thúc bất thường; handler cài trong `ThreadFactory` được gọi.
- `CountDownLatch` cho phép `main` chờ handler thật sự chạy. Không dùng `Thread.sleep(...)` để đoán handler đã chạy.
- `AtomicInteger` giúp tăng số thứ tự tên hoặc bộ đếm handler an toàn nếu factory/handler được gọi đồng thời. Thread được tạo thay thế sau một lỗi có thể có tên số thứ tự kế tiếp.
- `shutdown()` và `awaitTermination(...)` giải phóng executor có kiểm soát. `shutdownNow()` chỉ **yêu cầu** ngắt công việc còn chạy; không bảo đảm chấm dứt tức thời.

**Phạm vi output:** Đoạn mẫu chạy bằng executor chuẩn của JDK và giả định máy không bị treo/scheduler không trì hoãn quá 5 giây. Khi môi trường không đáp ứng deadline, chương trình sẽ ném lỗi timeout; nó không in giả rằng handler đã chạy.

Quan trọng hơn, ngay cả khi có handler, **ứng dụng vẫn phải quan sát lỗi từ `Future`**. Nếu gọi `submit` rồi bỏ qua `Future`, lỗi của task rất dễ bị bỏ sót.

## 7. Viết handler an toàn và có ích cho vận hành

### 7.1. Handler nên làm gì?

Một handler hữu ích thường thu thập **tên thread, lớp exception, message, stack trace**, ngữ cảnh an toàn đã có sẵn và gửi đến nơi ghi nhận lỗi phù hợp. Nếu cần cảnh báo sức khỏe tiến trình hoặc metrics, chỉ dùng đường xử lý ngắn, có khả năng thất bại an toàn.

Mẫu xử lý về ý tưởng:

~~~java
// Minh họa, logger được cung cấp bởi ứng dụng.
thread.setUncaughtExceptionHandler((failedThread, failure) -> {
    logger.error(
        "Uncaught error in thread " + failedThread.getName(),
        failure
    );
});
~~~

Đoạn này **không độc lập** vì `thread` và `logger` phải được ứng dụng khởi tạo. Truyền nguyên đối tượng `Throwable` giúp logger giữ stack trace, thay vì chỉ ghi một dòng `getMessage()`.

Handler phải ưu tiên **không ném exception mới, không block lâu và không chờ khóa có thể đang được giữ bởi luồng lỗi**. Nếu chính `uncaughtException` ném exception, JVM **bỏ qua exception phát sinh từ handler**, khiến thông tin lỗi gốc có thể bị mất. Khi heap đã cạn hoặc tiến trình ở trạng thái nguy hiểm, việc tạo chuỗi dài, gửi mạng đồng bộ hoặc khởi tạo nhiều đối tượng để ghi log có thể thất bại.

### 7.2. Handler không thay thế kiểm soát lỗi nghiệp vụ

| Vị trí xử lý | Mục đích |
| --- | --- |
| `try/catch` tại nơi hiểu được lỗi | Phục hồi hoặc chuyển lỗi thành kết quả nghiệp vụ |
| `Future.get()` / `CompletableFuture` | Biết task bất đồng bộ thành công hay thất bại |
| `UncaughtExceptionHandler` | Ghi nhận lỗi thoát ra khỏi đường thực thi của thread |
| Quản lý vòng đời executor/task | Quyết định retry, hủy, giới hạn tài nguyên và shutdown |

Không tự động retry một tác vụ từ uncaught handler: trạng thái đã có thể thay đổi một phần, dữ liệu có thể không nhất quán hoặc task có thể không idempotent. Việc khởi chạy lại phải thuộc chính sách nghiệp vụ có kiểm soát.

Một lỗi nghiêm trọng ở thread không nhất thiết chấm dứt JVM; các thread khác có thể tiếp tục chạy. Điều đó **không đồng nghĩa ứng dụng vẫn khỏe mạnh**. Hệ thống cần cơ chế quan sát và quyết định tình trạng phục vụ dựa trên mức độ ảnh hưởng của lỗi.

### 7.3. Phối hợp với interrupt và cancellation

`Thread.interrupt()` gửi tín hiệu interrupt, không tự gọi `UncaughtExceptionHandler`. Ví dụ một task bắt `InterruptedException` rồi thoát bình thường sẽ không kích hoạt handler. Khi không thể ném lại `InterruptedException`, thường nên khôi phục cờ bằng `Thread.currentThread().interrupt()` và kết thúc task hợp lý.

Nếu task ném một `RuntimeException` từ logic xử lý interrupt và exception đó thật sự thoát khỏi worker, handler mới có thể được gọi. Vì vậy không nên dùng handler để theo dõi mọi lần hủy hoặc dừng task.

## 8. Các tình huống dễ mắc lỗi

### Sai lầm 1 — Gọi `run()` thay vì `start()`

~~~java
// Minh họa sự khác biệt, không phải chương trình độc lập.
Thread t = new Thread(task, "background-1");
t.run();    // Chạy ngay trên thread đang gọi.
t.start();  // Mới thực sự khởi động thread riêng (nếu chưa start lần nào).
~~~

Đoạn trên dùng để so sánh hai phương thức; trong chương trình thực tế, **chọn một cách gọi phù hợp**. `start()` không được gọi lần thứ hai trên cùng đối tượng thread, nếu không sẽ ném `IllegalThreadStateException`.

### Sai lầm 2 — Cài handler rồi tưởng mọi exception đều đi qua đó

`try/catch`, `FutureTask` và các cơ chế completion có thể đã giữ lỗi. Khi xử lý task qua executor, hãy dùng `Future.get()` hoặc pipeline xử lý kết quả, đồng thời có cơ chế nhận diện task thất bại từ tầng nghiệp vụ.

### Sai lầm 3 — Cài handler mặc định từ thư viện

`Thread.setDefaultUncaughtExceptionHandler` thay đổi chính sách của **mọi thread trong JVM** theo tuyến xử lý mặc định. Code thư viện không sở hữu toàn bộ vòng đời ứng dụng nên không nên ghi đè handler toàn cục.

### Sai lầm 4 — Ghi lỗi nhưng không ghi stack trace

Chỉ in `exception.getMessage()` làm mất vị trí phát sinh, call stack và chuỗi nguyên nhân `getCause()`. Trong sản phẩm thực, truyền nguyên `Throwable` cho hệ thống logging hoặc dùng `printStackTrace` khi thích hợp.

### Sai lầm 5 — Đặt tên theo request rồi để worker pool tái sử dụng

Worker của pool phục vụ nhiều task theo thời gian. Tên nên mô tả **vai trò của worker**; request/correlation ID cần đi trong log context có vòng đời rõ ràng. Nếu đổi tên tạm thời, khôi phục trong `finally`.

### Sai lầm 6 — Dùng handler như cơ chế khôi phục hoặc cô lập lỗi

Handler là tầng báo cáo cuối, không bảo đảm task có thể chạy lại, không rollback side effect, không bảo vệ shared mutable state và không bảo đảm tiếp tục phục vụ an toàn sau một `Error` nghiêm trọng.

## 9. Liên hệ với Java 21+ và virtual threads

Java 21 đưa virtual threads thành tính năng chính thức. Virtual thread vẫn là đối tượng `Thread`, có thể có tên và `UncaughtExceptionHandler`, nhưng cách tổ chức chúng thường là **một virtual thread cho mỗi task** thay vì một nhóm worker nền tảng tái sử dụng.

Một minh họa API **chỉ dành cho Java 21+**, không chạy trên Java 17:

~~~java
ThreadFactory factory = Thread.ofVirtual()
    .name("io-task-", 0)
    .uncaughtExceptionHandler((thread, error) -> {
        error.printStackTrace(System.err);
    })
    .factory();
~~~

Đoạn mã chỉ khai báo `ThreadFactory`; nó chưa tạo hoặc khởi động task. Trong hệ thống dùng virtual threads, cần phân biệt tên task/virtual thread với tên carrier thread, đồng thời vẫn phải quan sát lỗi trong `Future` nếu executor đóng gói kết quả. Đặt tên hữu ích cho chẩn đoán nhưng không thay thế việc quản lý task và giới hạn tài nguyên.

## 10. Checklist áp dụng và tự kiểm tra

Trước khi triển khai:

1. Mỗi nhóm thread có **tên theo vai trò** dễ nhận biết trong log/thread dump hay chưa?
2. Tên worker có ổn định khi thread được tái sử dụng không? Có tránh dữ liệu cá nhân/secret trong tên không?
3. Handler riêng được cài **trước khi `start()`** hoặc thông qua `ThreadFactory` trước khi executor sử dụng worker chưa?
4. Ứng dụng có hiểu handler mặc định khác handler theo thread và tuyến `ThreadGroup` không?
5. Với `submit` và `CompletableFuture`, lỗi có được lấy và xử lý qua kênh kết quả không?
6. Handler có ghi stack trace mà không gây thêm lỗi, deadlock hoặc blocking kéo dài không?
7. Khi thread chết bất thường, có cơ chế giám sát và quyết định retry/fail job/ảnh hưởng sức khỏe tiến trình không?
8. Executor có kế hoạch shutdown và thời gian chờ hữu hạn không?

**Tình huống kiểm tra kiến thức:**

- Một task do `new Thread(task, "reader-1")` tạo ném `IllegalStateException` chưa được bắt và đã gán handler riêng. **Kết quả:** handler riêng được gọi, nhận thread `reader-1` và exception; thread chấm dứt.
- Một task do `executor.submit(...)` tạo ném `IllegalArgumentException`. **Kết quả:** với executor chuẩn của JDK, `Future.get()` báo `ExecutionException` với nguyên nhân là `IllegalArgumentException`; handler của worker không được gọi chỉ vì task đó thất bại.
- Một thread pool phục vụ nhiều request, mỗi request muốn có ID riêng. **Lựa chọn phù hợp:** đặt tên worker theo vai trò, đưa request ID vào log context với phạm vi/cơ chế dọn dẹp rõ ràng.

Tên luồng giúp quan sát *ai đang thực thi*; `UncaughtExceptionHandler` giúp ghi nhận *lỗi nào đã thoát khỏi thread*. Hai công cụ hỗ trợ chẩn đoán concurrency, nhưng tính đúng đắn và độ tin cậy của hệ thống vẫn cần quản lý kết quả task, shared state, giới hạn tài nguyên và vòng đời thread/executor.