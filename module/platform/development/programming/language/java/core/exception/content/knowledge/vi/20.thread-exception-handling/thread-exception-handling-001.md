# Ngoại lệ chỉ lan truyền trong ngăn xếp của luồng đang thực thi (Java)

## 1. Ý nghĩa của nguyên tắc

Trong Java, khi một phương thức ném exception, JVM tìm nơi xử lý bằng cách lần lượt thoát các lời gọi phương thức **trên call stack của luồng đang chạy**. Quá trình đó gọi là *stack unwinding*. Nếu tìm thấy `catch` tương thích, luồng tiếp tục theo logic của handler. Nếu exception đi hết các frame mà vẫn không được xử lý, nó là **uncaught exception của luồng ấy**.

Mỗi `Thread` có ngăn xếp lời gọi riêng. Vì vậy, một exception được ném trong luồng B **không tự động nhảy sang** `try/catch` đang chạy trong luồng A, dù A chính là luồng đã tạo, khởi động hoặc đợi B. Đây là ranh giới nền tảng khi viết API có concurrency.

Từ khóa:

- **Call stack:** các frame phương thức đang thực thi của **một luồng**; mỗi frame chứa địa chỉ quay về và thông tin cần thiết cho lời gọi.
- **Stack unwinding:** JVM rời các frame trong cùng luồng, chạy các đoạn `finally` thích hợp, giải phóng monitor của phương thức/khối `synchronized` khi rời vùng, và tìm handler phù hợp.
- **Uncaught exception:** exception đi ra tới đỉnh luồng mà không có handler ứng dụng xử lý; cơ chế `Thread.UncaughtExceptionHandler` có thể được gọi.
- **Error delivery:** truyền **thông tin** về thất bại từ một tác vụ sang luồng khác bằng đối tượng kết quả, `Future`, `CompletableFuture`, hàng đợi, callback hoặc giao thức thông báo. Đây là hành động có chủ đích; không phải stack unwinding xuyên luồng.

Nguyên tắc áp dụng cho cả **platform thread** lẫn **virtual thread** ở những phiên bản Java hỗ trợ virtual thread: mỗi luồng thực thi có ngữ cảnh ngoại lệ riêng. Cơ chế tổ chức và chờ tác vụ có thể giúp chuyển **kết quả lỗi** về nơi gọi, nhưng không làm hai call stack trở thành một.

## 2. Vì sao `try/catch` của luồng cha không bắt được lỗi của luồng con?

Xét đoạn mã sau (là mảnh code trong một phương thức, với các import cần thiết đã có):

```java
try {
    Thread child = new Thread(() -> {
        throw new IllegalStateException("failed inside child");
    });
    child.start();
    child.join();
} catch (IllegalStateException ex) {
    System.out.println("This catch does not handle the child's exception");
}
```

`Thread.start()` yêu cầu JVM chạy `Thread.run()` trong **luồng mới**. Câu lệnh `throw` thuộc ngăn xếp lời gọi của child; khối `catch` bên ngoài đang ở ngăn xếp của luồng gọi `start()`, nên **không bắt** được exception từ child.

Điều kiện quan trọng:

- `start()` có thể tự ném exception ở **luồng gọi**, chẳng hạn `IllegalThreadStateException` khi cố khởi động một đối tượng `Thread` đã khởi động. Exception như vậy có thể được `catch` tương thích của caller xử lý.
- `join()` có thể ném `InterruptedException` **ở luồng đang đợi** khi luồng đó bị interrupt; đó không phải exception nghiệp vụ của child. Nếu `join()` bị interrupt, khối `catch (InterruptedException)` trong caller có thể bắt được vì exception này phát sinh trong chính caller.
- Với mã ở ví dụ, `join()` trả về sau khi child kết thúc; nó không ném lại `IllegalStateException` đã xảy ra trong child. Nếu không có handler tùy chỉnh, thông thường runtime báo uncaught exception trên `System.err`.
- `Thread.run()` được gọi **trực tiếp** bằng `child.run()` chỉ là lời gọi phương thức bình thường trên **luồng hiện tại**. Khi đó exception có thể lan về `catch` của caller; cũng không tạo một luồng mới.

Cần phân biệt rõ phương thức tạo việc bất đồng bộ với phương thức **chờ và lấy kết quả**. Tạo hoặc đợi một luồng không mặc nhiên mang theo cơ chế chuyển lỗi.

## 3. Sơ đồ ngăn xếp khi ném exception

Ví dụ A gọi `start()` để chạy B. Về mặt khái niệm, ta có hai luồng với hai stack độc lập:

```text
Luồng A (caller)                  Luồng B (worker)
----------------                 ----------------
main()                           Thread.run()
  start() [trả về]                 task()
  join() [đang đợi]                  step1()
                                     step2() -> throw X
  tiếp tục sau join()             unwind step2 -> step1 -> task
                                 -> run -> uncaught handler
```

Exception X được tìm handler ở `step2()`, rồi `step1()`, rồi `task()`, rồi những frame phía trên trong **luồng B**. JVM không tìm handler ở `main()` của A. Sau khi B kết thúc, A có thể tiếp tục sau `join()` mà không biết B đã gặp lỗi, trừ khi hai bên có **kênh báo kết quả**.

Các dấu hiệu dễ gây nhầm:

1. Luồng A đã gọi một phương thức tạo B: điều đó không làm call stack B thành nhánh con về mặt Java exception handling.
2. Bên trong B có gọi một phương thức của object do A tạo: object có thể dùng chung, nhưng stack vẫn riêng.
3. Tên ngoại lệ hoặc stack trace có nhắc class do A gọi: điều đó không làm `catch` của A được kích hoạt.
4. Hai tác vụ chạy chung một `ExecutorService`: mỗi lần thực thi có ngữ cảnh của thread thực hiện; việc chuyển lỗi còn phụ thuộc loại tác vụ và API lấy kết quả.

## 4. Ví dụ Java 17+ có thể biên dịch và chạy

Ví dụ này đặt cạnh nhau bốn tình huống: lời gọi đồng bộ, `Thread` thô, `Future` và `CompletableFuture`. Nó cố tình ném cùng một `IllegalStateException` để phân biệt **nơi exception được ném** với **nơi thông tin lỗi được quan sát**.

Tạo file `ThreadExceptionBoundaryDemo.java`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadExceptionBoundaryDemo {
    static void startOperation() {
        deeper();
    }

    static void deeper() {
        throw new IllegalStateException("boom");
    }

    public static void main(String[] args) throws InterruptedException {
        try {
            startOperation();
        } catch (IllegalStateException ex) {
            System.out.println("SYNCHRONOUS: " + ex.getClass().getSimpleName());
        }

        Thread worker = new Thread(ThreadExceptionBoundaryDemo::startOperation,
                                   "raw-worker");
        worker.setUncaughtExceptionHandler((thread, error) ->
                System.out.println("UNCAUGHT " + thread.getName() + ": "
                        + error.getClass().getSimpleName()));
        worker.start();
        worker.join();
        System.out.println("AFTER JOIN: main continues");

        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Future<?> future = executor.submit(
                    ThreadExceptionBoundaryDemo::startOperation);
            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println("FUTURE: "
                        + ex.getCause().getClass().getSimpleName());
            }
        } finally {
            executor.shutdown();
        }

        CompletableFuture<Void> stage = CompletableFuture.runAsync(
                ThreadExceptionBoundaryDemo::startOperation);
        try {
            stage.join();
        } catch (CompletionException ex) {
            System.out.println("COMPLETABLE: "
                    + ex.getCause().getClass().getSimpleName());
        }

        System.out.println("MAIN: done");
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn, từ thư mục chứa file:

```bash
javac -encoding UTF-8 ThreadExceptionBoundaryDemo.java
java ThreadExceptionBoundaryDemo
```

Standard output của ví dụ:

```text
SYNCHRONOUS: IllegalStateException
UNCAUGHT raw-worker: IllegalStateException
AFTER JOIN: main continues
FUTURE: IllegalStateException
COMPLETABLE: IllegalStateException
MAIN: done
```

**Điều xảy ra ở từng phần:**

1. `startOperation()` được `main` gọi trực tiếp, nên `IllegalStateException` di chuyển theo chuỗi `deeper() → startOperation() → main()` của chính main thread. `catch` ở `main` bắt được.
2. Một đối tượng `Thread` được khởi động bằng `start()`. Lỗi xảy ra trong worker; do worker không tự xử lý, `UncaughtExceptionHandler` **của worker** in thông tin. `join()` bảo đảm worker đã kết thúc trước khi main in dòng tiếp theo, nhưng không ném lại lỗi.
3. `ExecutorService.submit()` đưa tác vụ vào executor và trả một `Future`. Lỗi thực thi được giữ trong kết quả Future; lời gọi `future.get()` của main ném `ExecutionException` có `getCause()` là `IllegalStateException` ban đầu.
4. `CompletableFuture.runAsync()` tạo một stage bất đồng bộ. Khi tác vụ thất bại, stage hoàn thành với trạng thái exceptional; lời gọi `stage.join()` của main ném `CompletionException` bao lấy nguyên nhân.
5. Chương trình vẫn tới `MAIN: done`. Một thất bại ở worker không mặc nhiên kết thúc tất cả luồng khác hoặc hủy tiến trình.

Ví dụ dùng `setUncaughtExceptionHandler` để output ổn định, không dựa vào in stack trace mặc định trên stderr. `ExecutorService` được `shutdown()` sau khi lấy kết quả; trên Java 17 không giả định rằng `ExecutorService` là tài nguyên `AutoCloseable` cho cú pháp `try-with-resources`.

Lưu ý: `Future.get()` có thể ném thêm `InterruptedException` hoặc `CancellationException` theo trạng thái; `CompletableFuture.join()` có thể ném `CancellationException` nếu future bị hủy. Hai lệnh lấy kết quả được trình bày trong trường hợp tác vụ **thất bại do exception**, không phải trong mọi trạng thái.

## 5. Handler ở đâu trên cùng một call stack?

Một câu `catch` xử lý được exception khi:

- Exception phát sinh trong hoạt động đồng bộ trên **chính luồng hiện tại**.
- Loại exception được ném tương thích với loại trong `catch`, xét theo các quy tắc của Java.
- Không có handler ở frame thấp hơn đã xử lý dứt điểm exception trước đó.

Ví dụ một chuỗi gọi đồng bộ:

```java
static void level1() {
    level2();
}

static void level2() {
    throw new IllegalArgumentException("bad value");
}

// Trong một phương thức khác trên cùng thread:
try {
    level1();
} catch (IllegalArgumentException ex) {
    System.out.println(ex.getMessage());
}
```

Đây là các **mảnh phương thức minh họa**, không phải chương trình độc lập vì vị trí phương thức và mã gọi cần đặt vào lớp phù hợp. `level2()` không cần có `catch` thì handler ở lời gọi `level1()` của cùng thread vẫn bắt được. Nếu `level1()` tạo thread khác và `level2()` chạy trong thread đó, cách diễn giải sẽ thay đổi hoàn toàn.

Trên đường unwinding, các khối `finally` thích hợp vẫn thực thi trong **luồng ném lỗi**; tài nguyên `try-with-resources` được đóng trên luồng đang thực thi đường đó. Các cơ chế cleanup cũng có thể ném thêm lỗi, ví dụ suppressed exceptions, nhưng vẫn không làm exception tự chuyển sang caller của một thread khác.

## 6. Thread thô: `UncaughtExceptionHandler` có vai trò gì?

`Thread.UncaughtExceptionHandler` nhận thông báo khi một luồng chuẩn bị kết thúc do exception không được xử lý. Ví dụ:

```java
Thread worker = new Thread(() -> {
    throw new IllegalArgumentException("invalid task state");
}, "worker-A");

worker.setUncaughtExceptionHandler((thread, failure) -> {
    System.err.println("Worker " + thread.getName()
            + " failed: " + failure.getClass().getSimpleName());
});

worker.start();
```

Đoạn này là **mảnh triển khai** đặt trong phương thức có xử lý vòng đời worker. Handler chạy trong ngữ cảnh xử lý thất bại của worker; nó có thể ghi log, cập nhật trạng thái hoặc phát thông báo qua kênh chung phù hợp. Nó **không phải `catch` của parent thread**, và không tự làm tác vụ bị lỗi chạy tiếp từ nơi vừa ném exception.

Thứ tự chọn handler trong Java bao gồm handler được đặt trực tiếp trên thread hoặc handler của `ThreadGroup`, rồi hành vi mặc định tương ứng. Có thể cấu hình default handler bằng `Thread.setDefaultUncaughtExceptionHandler(...)`, nhưng thiết lập toàn cục đó phải được cân nhắc vì ảnh hưởng đến các luồng không đặt handler riêng. Nếu callback xử lý uncaught exception tự ném exception, JVM thường bỏ qua exception mới từ callback; không nên đặt logic phục hồi phức tạp hay dễ lỗi ở đây.

Khi không có handler tùy chỉnh, JVM thông thường in thông tin uncaught exception ra stderr. Phần chính xác của output có thể phụ thuộc runtime, logging và tên thread, nên không dựa vào nội dung log như một giao thức nhận kết quả. Việc thread chết vì uncaught exception không đồng nghĩa tất cả thread khác phải chết.

**Đáng chú ý:** đối với task chạy qua executor hoặc future, framework có thể **bắt exception để đưa vào đối tượng kết quả**. Vì vậy không được dựa duy nhất vào uncaught handler để phát hiện thất bại của mọi tác vụ bất đồng bộ.

## 7. Phân biệt `Thread.start()`, `Thread.run()` và `Thread.join()`

| API | Chạy ở luồng nào? | Cơ chế lỗi |
| --- | --- | --- |
| `thread.run()` | Luồng **đang gọi** `run()` | Exception có thể lan về `catch` của caller như lời gọi đồng bộ |
| `thread.start()` | Khởi động thực thi `run()` trên **luồng mới** | Lỗi trong `run()` được xử lý theo stack của luồng mới; `start()` không tự ném lại |
| `thread.join()` | Luồng gọi `join()` chờ luồng đích chết | Không truyền ngoại lệ của luồng đích; có thể ném `InterruptedException` ở luồng đang đợi |
| `thread.setUncaughtExceptionHandler(...)` | Đăng ký handler cho luồng đích | Xử lý/quan sát lỗi **không được catch trong đích**, không tự truyền về caller |

Trường hợp `thread.run()` có thể gây nhầm vì cùng một đối tượng `Thread` nhưng thực tế **không có thread mới**. Dùng `run()` trực tiếp thường sai khi mục tiêu là concurrency.

Với `join()`, giá trị quan trọng là **synchronization**: một luồng đã kết thúc thì luồng khác có thể quan sát tác dụng bộ nhớ của nó theo quy tắc *happens-before* khi join thành công. Nhưng *happens-before* về bộ nhớ không đồng nghĩa tự chuyển Throwable qua lại. Nếu muốn nhận lỗi, worker phải đưa kết quả/ngoại lệ vào một kênh chung hoặc dùng abstraction hỗ trợ kết quả như `Future`.

## 8. `ExecutorService`: `execute()` và `submit()` không giống nhau

`ExecutorService` quản lý tập các luồng thực thi task. Hai đường API có khác biệt quan trọng:

### `execute(Runnable)`

`execute` nhận một `Runnable` và **không trả `Future`**. Nếu task ném `RuntimeException` không được bắt, exception có thể đi tới cơ chế xử lý uncaught của luồng worker, tùy executor và cách task được bọc. Với `ThreadPoolExecutor` chuẩn, các trường hợp exception runtime từ task được gửi bằng `execute` có thể làm worker kết thúc đột ngột và kích hoạt xử lý uncaught.

Điều này không cho phép caller viết `try { executor.execute(task); } catch (...)` rồi kỳ vọng bắt exception xảy ra *sau đó* trong worker. `execute` chỉ có thể ném lỗi **đồng bộ lúc nộp task**, chẳng hạn `RejectedExecutionException` nếu executor từ chối công việc.

### `submit(Runnable/Callable)`

`submit` trả `Future`. Exception trong task thường được **ghi vào kết quả Future** thay vì thoát ra uncaught handler của worker. Người gọi phải quan sát kết quả:

```java
Future<Integer> future = executor.submit(() -> {
    throw new IllegalStateException("calculation failed");
});

try {
    Integer value = future.get();
    System.out.println(value);
} catch (ExecutionException ex) {
    Throwable root = ex.getCause();
    System.err.println("Task failed: " + root);
}
```

Đây là **mảnh code trong phương thức** có `ExecutorService executor` đang hoạt động và đã import `Future`, `ExecutionException`. `get()` cũng khai báo `InterruptedException`, nên phương thức bên ngoài phải khai báo/bắt đúng hoặc khôi phục trạng thái interrupt theo hợp đồng.

Một hệ quả thực tế: nếu gọi `submit` nhưng **bỏ kết quả `Future`**, exception của task có thể không được nơi gọi quan sát hoặc ghi log theo mong muốn. Thiết kế nên có nơi chịu trách nhiệm theo dõi từng task/future, nhất là các task làm thay đổi dữ liệu hoặc tài nguyên.

### Future chưa hoàn tất, hủy và timeout

`future.get()` có thể chờ đến khi task hoàn tất. `future.get(timeout, unit)` thêm khả năng ném `TimeoutException` ở luồng gọi **vì chờ quá lâu**; timeout của người đợi không tự đảm bảo task đã dừng. `future.cancel(true)` gửi yêu cầu hủy có thể dùng interrupt, nhưng task cần hợp tác và có thể không dừng ngay; trạng thái công việc đã làm phải được xử lý độc lập.

Khi gặp `ExecutionException`, `getCause()` chỉ ra Throwable khiến tác vụ thất bại. Đừng mặc định cause là loại checked hay unchecked cụ thể; kiểm tra loại và hợp đồng của tác vụ.

## 9. `CompletableFuture`: lỗi được ghi vào stage và lộ ra ở điểm quan sát

`CompletableFuture` biểu diễn kết quả hoặc thất bại của một chuỗi xử lý. Khi hàm bất đồng bộ ném exception, stage liên quan được đánh dấu hoàn thành **exceptionally**. Những điểm quan sát thường dùng:

| Cơ chế | Cách nhận lỗi | Ý nghĩa |
| --- | --- | --- |
| `future.join()` | `CompletionException` với `getCause()` là lỗi nguồn trong trường hợp thông thường | Lấy kết quả đồng bộ, exception dạng unchecked |
| `future.get()` | `ExecutionException` với `getCause()` là nguyên nhân | Giao diện `Future`; còn có `InterruptedException` |
| `future.exceptionally(fn)` | Callback nhận Throwable và có thể tạo giá trị dự phòng | Biến failure thành kết quả nếu có fallback hợp lệ |
| `future.handle((value, error) -> ...)` | Callback thấy thành công hoặc lỗi | Tạo stage kết quả mới theo logic đã chọn |
| `future.whenComplete((value, error) -> ...)` | Callback quan sát kết quả hoặc lỗi | Thường dùng log/metric, không mặc định phục hồi |

Ví dụ mảnh code trong phương thức đã có `CompletableFuture<Integer> future`:

```java
CompletableFuture<Integer> recovered = future.exceptionally(ex -> {
    System.err.println("Async failure: " + ex);
    return -1;
});
```

Đây chỉ là ví dụ biến kết quả lỗi thành `-1`; **chỉ làm như vậy nếu `-1` có nghĩa fallback được hợp đồng cho phép**. Nếu `-1` cũng là dữ liệu hợp lệ thì fallback có thể che mất lỗi. Với tác vụ cập nhật trạng thái hoặc tài chính, việc nuốt lỗi rồi trả mặc định thường rất nguy hiểm.

### Callback có chạy trên luồng main không?

Không được suy luận từ tên `handle`/`whenComplete` rằng callback chạy ở luồng gọi ban đầu. Các continuation không có hậu tố `Async` có thể được thực thi bởi luồng hoàn tất stage trước đó hoặc luồng kích hoạt completion, tùy thời điểm; các phương thức `...Async` có chính sách executor riêng và có thể nhận executor tường minh. Vì vậy:

- Logic callback phải đúng về thread safety.
- Không dựa vào `ThreadLocal` của luồng gọi nếu chưa truyền ngữ cảnh phù hợp.
- Không đặt giả định về thứ tự in log giữa các task đồng thời nếu không có điều kiện đồng bộ.
- Exception mới trong callback có thể khiến **stage tiếp theo** hoàn thành exceptionally; nó không tự trở về một `catch` đã kết thúc trước đó ở main.

## 10. Cách chuyển lỗi từ `Thread` thô sang luồng gọi

Nếu dùng `Thread` thô và muốn caller xác nhận thất bại, có thể dùng kênh kết quả được đồng bộ hóa. Ví dụ dưới đây là **mảnh code trong phương thức khai báo `throws InterruptedException`**, giả sử `doWork()` là phương thức có thể ném `RuntimeException`:

```java
AtomicReference<RuntimeException> failure = new AtomicReference<>();

Thread child = new Thread(() -> {
    try {
        doWork();
    } catch (RuntimeException ex) {
        failure.set(ex);
    }
});

child.start();
child.join();

RuntimeException observed = failure.get();
if (observed != null) {
    throw new IllegalStateException("Child task failed", observed);
}
```

Cần import `java.util.concurrent.atomic.AtomicReference`. `AtomicReference` hỗ trợ chia sẻ kết quả an toàn; thêm vào đó, `join()` thành công tạo quan hệ *happens-before* với tác vụ của child. Điều được chuyển sang caller là **một đối tượng Throwable như dữ liệu**, sau đó caller chủ động ném ngoại lệ mới với `cause` là lỗi của worker.

Đây **không phải** tình huống JVM tự đi ngược stack B sang stack A. Ở thời điểm caller ném `IllegalStateException` mới, JVM unwind **stack caller**; stack trace của cause vẫn giúp chỉ ra nơi lỗi trong worker xuất phát.

Mã chỉ bắt `RuntimeException` theo mục đích minh họa. Với task có checked exception, phải quyết định contract và kênh lưu kiểu ngoại lệ thích hợp. Thông thường không nên `catch (Throwable)` rồi giả định có thể phục hồi mọi `Error`; một lỗi nghiêm trọng có thể không cho phép tiếp tục vận hành an toàn.

Nếu phần mềm đã dùng executor, ưu tiên `Future` hoặc `CompletableFuture` thay vì tự chế kênh lưu lỗi mà dễ bỏ sót hủy, timeout và vòng đời thread.

## 11. Ngoại lệ checked, unchecked và lỗi trong lambda

Trong Java, `Runnable.run()` không khai báo checked exception. Vì vậy lambda truyền cho `new Thread(() -> ...)` không thể đơn giản ném một `IOException` checked ra ngoài nếu chưa xử lý hoặc chuyển đổi nó trong lambda. Có thể:

- Bắt `IOException` bên trong task, báo qua channel hoặc wrapper có `cause`;
- Dùng `Callable<V>` trong executor, vì `Callable.call()` khai báo `throws Exception`, rồi caller quan sát qua `Future.get()`;
- Cấu trúc lại API bất đồng bộ để kết quả hoặc lỗi là giá trị của future/stage.

Ví dụ mảnh code trong phương thức đã có `ExecutorService executor`:

```java
Future<String> fileJob = executor.submit(() -> {
    return java.nio.file.Files.readString(
            java.nio.file.Path.of("config.txt"));
});
```

Ở đây `Callable<String>` có thể ném checked `IOException`; exception đó được giữ làm `cause` của `ExecutionException` khi caller gọi `fileJob.get()`. File không tồn tại hoặc lỗi I/O chỉ phát sinh khi tác vụ chạy; lúc `submit` trả về, caller có thể chưa biết lỗi.

Unchecked exception (`RuntimeException`) cũng không tự “bay qua thread”; khác biệt checked/unchecked thuộc về **kiểm tra kiểu ở compile time và hợp đồng khai báo**, không xóa ranh giới stack.

## 12. `InterruptedException` thuộc về luồng đang chờ

Đây là trường hợp dễ nhầm với “exception từ child truyền về main”:

```java
try {
    child.join();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Mã trên là mảnh trong phương thức phù hợp, đã có `Thread child`; `return` yêu cầu được đặt ở nơi cú pháp Java cho phép. `InterruptedException` xuất hiện vì **luồng đang gọi `join()`** bị interrupt khi đợi, không phải vì child đã ném exception này cho caller. Lời gọi `Thread.currentThread().interrupt()` khôi phục cờ interrupt để các tầng ngoài có thể thấy tín hiệu nếu phương thức không truyền tiếp exception.

Không nên coi interrupt như một “exception gửi từ thread khác”. `interrupt()` đặt tín hiệu yêu cầu hợp tác; những API blocking nhất định sẽ ném `InterruptedException` trong thread bị interrupt, nhưng việc dừng task tùy code và điểm chờ. Không dùng cơ chế interrupt làm đường chuyển lỗi nghiệp vụ chính, hoặc ép worker dừng bằng cơ chế không an toàn.

## 13. Uncaught exception, tiến trình JVM và tài nguyên dùng chung

Một worker chết vì exception không được catch **không bảo đảm JVM tự tắt ngay**. JVM có thể tiếp tục chạy nếu vẫn có những luồng non-daemon đang hoạt động; trạng thái kết thúc tiến trình phụ thuộc các luồng còn lại và môi trường chạy. Đặc biệt:

- Trong server nhiều request, một request handler hoặc worker chết không đồng nghĩa tất cả request khác phải dừng.
- Thất bại của thread không tự hủy các task đang chạy trên thread khác.
- Ngoại lệ trong worker không tự rollback database, file hay mutable state dùng chung.
- `synchronized` monitor tự được nhả khi thoát stack, nhưng dữ liệu đã sửa một phần vẫn có thể ở trạng thái không nhất quán.
- Callback uncaught là nơi **quan sát/ghi nhận** thất bại, không tự bảo đảm khôi phục trạng thái nghiệp vụ.

Điều này đặt ra yêu cầu thiết kế thất bại: nếu một worker đang sở hữu khóa, tài nguyên, transaction hoặc cập nhật nhiều bước, hãy có hợp đồng rõ ràng về cleanup, tính nguyên tử, rollback trong phạm vi tài nguyên, và cách báo trạng thái cho phần còn lại của hệ thống.

Cũng đừng dùng tên thread hoặc thông báo exception làm mã định danh duy nhất của một request: executor có thể tái sử dụng worker cho nhiều task. Dùng correlation ID/task ID tường minh để gắn lỗi với nghiệp vụ cần xử lý.

## 14. Phân biệt lỗi tại thời điểm nộp và tại thời điểm chạy

Một API bất đồng bộ thường có **hai vùng lỗi** khác nhau:

**Vùng 1: ngay khi caller nộp công việc**

Ví dụ `executor.submit(task)` hoặc `executor.execute(task)` có thể thất bại đồng bộ vì executor đã shutdown hoặc vì không nhận thêm task. `RejectedExecutionException` phát sinh trong lời gọi nộp task của caller, nên `try/catch` ngay quanh lời gọi có thể xử lý.

**Vùng 2: khi worker thực thi công việc**

Ví dụ code trong `task` ném `IllegalArgumentException`, `IOException` hay `IllegalStateException`. Caller không bắt được trực tiếp chỉ bằng `try/catch` quanh `submit`. Cần quan sát `Future` hoặc một cơ chế thông báo lỗi tương ứng.

Tương tự, một phương thức `CompletableFuture.supplyAsync(...)` có thể bị lỗi đồng bộ ở giai đoạn tạo/sắp lịch do executor từ chối, còn exception trong supplier sau khi bắt đầu chạy làm stage hoàn thành exceptionally. Việc phân biệt giúp đặt `catch` và cơ chế giám sát đúng nơi.

## 15. Thiết kế đường xử lý lỗi đa luồng có trách nhiệm

Khi viết thư viện hoặc service có task chạy trên thread khác, hãy quyết định ngay từ hợp đồng API:

1. **Ai sở hữu task?** Caller nào phải đợi hoặc nhận kết quả của công việc đó?
2. **Lỗi cần được quan sát bằng gì?** `Future`/`CompletableFuture`, callback, message, log + state machine, hay handler? Log đơn thuần có đủ để caller quyết định không?
3. **Lỗi nào làm tác vụ thất bại?** Checked I/O, lỗi nghiệp vụ, timeout, cancellation và các loại bug được phân loại ra sao?
4. **Tác vụ còn chạy sau timeout/hủy không?** Nếu còn, liệu retry có làm trùng giao dịch hoặc side effect?
5. **Khi một task trong nhóm thất bại, những task khác ra sao?** Tiếp tục, hủy hợp tác, thu thập toàn bộ lỗi, hay fail fast theo hợp đồng?
6. **Trạng thái dùng chung có an toàn không?** Có cần transaction, lock, snapshot, bất biến hoặc idempotency?
7. **Lỗi được ghi ở đâu?** Có ID để ghép log từ worker với kết quả caller hay không?

Một đường triển khai thường rõ ràng là: caller gửi task, giữ reference tới kết quả, chờ/compose ở điểm phù hợp, kiểm tra thành công hoặc lỗi, sau đó thực hiện cleanup và retry theo loại lỗi. Với task dạng fire-and-forget, vẫn cần một nơi định nghĩa **ai nhận báo lỗi, theo dõi hoàn thành và xử lý tác dụng phụ**; “không ai gọi `get()`” không có nghĩa thất bại đã được xử lý.

## 16. Những lỗi hiểu sai thường gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| “Tôi đã bọc `thread.start()` bằng `try/catch` nên bắt được mọi lỗi trong worker.” | `catch` bên caller chỉ bắt lỗi xảy ra **ở caller** khi gọi `start()`; lỗi trong worker đi theo stack worker. |
| “Gọi `join()` thì exception của worker được ném lại.” | `join()` chỉ đợi worker hoàn tất; caller phải có kênh kết quả riêng. |
| “`ExecutorService.submit()` không ghi uncaught log tức là task không lỗi.” | `submit` có thể lưu lỗi trong `Future`. Phải theo dõi `get()` hoặc cơ chế quan sát kết quả phù hợp. |
| “Mọi callback `CompletableFuture` đều chạy ở luồng main.” | Luồng thực thi callback tùy loại continuation, thời điểm hoàn thành và executor. |
| “`CompletionException` là nguyên nhân gốc của lỗi.” | Thông thường đó là **wrapper**; xem `getCause()` và toàn bộ cause chain. |
| “`InterruptedException` từ `join()` là lỗi do thread đích truyền về.” | Đó là lỗi chờ của **thread đang gọi `join()`** khi nó bị interrupt. |
| “Worker ném RuntimeException thì JVM chắc chắn kết thúc.” | Worker có thể kết thúc, các thread khác và tiến trình có thể tiếp tục. |
| “Worker chết thì transaction và biến chia sẻ trở về trước.” | Java exception không tự rollback side effect hoặc mutable state. |
| “Gọi `thread.run()` tương đương `thread.start()`.” | `run()` trực tiếp chạy trong caller; `start()` tạo thực thi trên thread riêng. |
| “Bắt `Throwable` trong mọi worker là cách an toàn để không mất lỗi.” | Bắt cả `Error` có thể che tình trạng nghiêm trọng; cần chính sách lỗi và phục hồi có giới hạn rõ. |

## 17. Cách kiểm thử cơ chế lan truyền

Test concurrency nên xác nhận **nơi lỗi được bắt** và **đường chuyển lỗi**, không chỉ xác nhận log có chữ `Exception`:

- **Đồng bộ:** gọi hàm ném lỗi trực tiếp, dùng `assertThrows` tương ứng và kiểm tra handler trên caller.
- **Thread thô:** đặt handler cho thread; dùng `join()`; xác nhận handler nhận lỗi và `join()` không ném exception nghiệp vụ.
- **Thread.start vs run:** so sánh việc gọi `run()` trực tiếp (cùng stack) với `start()` (stack riêng).
- **Executor.submit:** nộp task ném exception, `future.get()` phải cho `ExecutionException` và đúng `getCause()`.
- **CompletableFuture:** stage thất bại, `join()` cho `CompletionException` và cause phù hợp; `handle`/`exceptionally` tạo kết quả đúng nếu hợp đồng cho phép.
- **Từ chối nộp task:** thử executor đã shutdown và xác nhận lỗi đồng bộ ở caller.
- **Cancel và interrupt:** đảm bảo người đợi xử lý `InterruptedException`; xác minh task có thể dừng hợp tác và các tác dụng phụ được quản lý.
- **Đa luồng thực sự:** dùng `CountDownLatch` hoặc đồng bộ kiểm thử rõ ràng để điều phối thứ tự; tránh phụ thuộc vào `Thread.sleep()` hoặc thời gian tình cờ.

Nếu test cần chờ task, nên có timeout rõ để tránh treo vô hạn. Đặc biệt, kiểm thử ghi nhận lỗi từ uncaught handler cần tránh phụ thuộc vào stdout/stderr có thể xen kẽ giữa thread, hoặc vào tên mặc định của thread tùy runtime.

## 18. Tổng hợp quy tắc làm việc

- Exception **unwind trong một call stack**: handler muốn bắt trực tiếp phải nằm trong luồng đang thực thi đường gọi đó.
- `Thread.start()` tạo một ranh giới bất đồng bộ; `Thread.join()` đợi hoàn thành **nhưng không mang exception trở lại**.
- `Thread.UncaughtExceptionHandler` quan sát lỗi không được xử lý của thread; nó không tự là kênh kết quả cho caller.
- `Future.get()` và `CompletableFuture.get()/join()` cho phép caller **chủ động quan sát thất bại**, thường qua `ExecutionException` hoặc `CompletionException` có `cause`.
- Exception ở worker và tác dụng phụ của worker là hai vấn đề khác nhau: cần mô tả trạng thái sau lỗi, bảo đảm đồng bộ, cleanup, hủy và retry có kiểm soát.

**Ghi nhớ:** *Ngoại lệ không tự vượt qua ranh giới luồng; thông tin về ngoại lệ có thể được chuyển qua một API kết quả hoặc kênh liên lạc rõ ràng.* Hiểu đúng sự khác biệt này giúp thiết kế API đa luồng có đường báo lỗi đáng tin và tránh bỏ sót các tác vụ thất bại.
