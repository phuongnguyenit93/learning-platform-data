# Thread.UncaughtExceptionHandler: xử lý ngoại lệ không được bắt trong luồng Java

Khi một `Thread` thực thi mã và có một exception hoặc error thoát ra khỏi điểm bắt đầu của luồng mà không được xử lý, luồng sẽ chấm dứt do lỗi. Java cung cấp giao diện `Thread.UncaughtExceptionHandler` để nhận thông báo về **`Throwable` chưa được bắt**, cùng thông tin luồng gặp lỗi. Đây là điểm quan sát thất bại cuối cùng của một luồng, hữu ích cho logging, cảnh báo, ghi nhận sự cố và phối hợp với cơ chế giám sát.

Tuy nhiên, **handler không phải một khối `catch` có thể tiếp tục công việc tại vị trí lỗi**. Khi nó được gọi, thread đang đi đến kết thúc bất thường; muốn phục hồi tác vụ, trả kết quả hay thử lại, ứng dụng phải có cơ chế riêng. Đặc biệt, lỗi trong tác vụ gửi qua `ExecutorService.submit` hoặc trong `CompletableFuture` có thể được **lưu trong đối tượng kết quả** và không đi qua uncaught-exception handler của worker thread.

## 1. Hiểu đúng “uncaught” theo ranh giới của Thread

Ví dụ đơn giản:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Dữ liệu trạng thái không hợp lệ");
});
worker.start();
```

Đây là đoạn minh họa chưa có `main` độc lập. Một `IllegalStateException` thoát khỏi `Runnable.run()` mà không được `catch` trong worker. JVM chuẩn bị chấm dứt worker do lỗi và gọi handler có hiệu lực cho thread ấy. Nếu không có handler tùy chỉnh, runtime thông thường sẽ in thông tin exception và stack trace ra `System.err` thông qua cơ chế của `ThreadGroup`.

So sánh với đoạn sau:

```java
Thread worker = new Thread(() -> {
    try {
        riskyOperation();
    } catch (IllegalStateException ex) {
        reportAndRecover(ex);
    }
});
```

Đây cũng là đoạn minh họa, với `riskyOperation` và `reportAndRecover` do ứng dụng định nghĩa. Nếu `catch` thực sự xử lý exception và không ném lỗi mới, handler không được gọi, vì exception không còn “uncaught”.

Điều cần phân biệt:

- **Exception được bắt bên trong thread:** mã `catch` có thể xử lý, thay đổi kết quả, thử lại có kiểm soát hoặc quyết định chấm dứt.
- **Exception không được bắt và thoát khỏi thread:** `UncaughtExceptionHandler` được gọi như cơ chế báo cáo cuối; thread không quay lại tiếp tục từ câu lệnh thất bại.
- **Exception được framework/task wrapper bắt rồi lưu lại:** có thể không có exception thoát khỏi worker thread; caller lấy lỗi qua `Future`, `CompletionStage` hoặc callback framework.

Một thread bị lỗi không tự động làm tất cả thread khác dừng. Ứng dụng có thể vẫn hoạt động với trạng thái không còn đúng nếu thread vừa chết là thành phần quan trọng; vì vậy handler có thể chỉ là một phần của hệ thống giám sát.

## 2. Giao diện Thread.UncaughtExceptionHandler

Giao diện lồng trong `java.lang.Thread` có phương thức:

```java
@FunctionalInterface
public interface UncaughtExceptionHandler {
    void uncaughtException(Thread thread, Throwable error);
}
```

Đoạn trên mô tả chữ ký API để học, không định nghĩa lại giao diện JDK trong một chương trình ứng dụng.

Hai tham số mang ý nghĩa:

| Tham số | Ý nghĩa | Dùng để làm gì? |
| --- | --- | --- |
| `Thread thread` | Luồng mà exception không được bắt | Ghi tên luồng, ID hoặc metadata để định vị thành phần lỗi. |
| `Throwable error` | Exception hoặc error thoát khỏi luồng | Ghi loại lỗi, thông điệp, stack trace, cause và suppressed exceptions nếu cần. |

Vì tham số thứ hai là `Throwable`, handler có thể nhận cả `RuntimeException` lẫn `Error` như `AssertionError` hoặc `OutOfMemoryError`. **Không nên cố xử lý mọi `Error` như lỗi nghiệp vụ có thể phục hồi.** Khi nguồn lực JVM đã cạn, ngay cả logging hoặc cấp phát thêm bộ nhớ cũng có thể thất bại.

Có thể cài handler bằng lambda:

```java
Thread.UncaughtExceptionHandler handler = (thread, error) -> {
    System.err.println("Luồng lỗi: " + thread.getName());
    error.printStackTrace(System.err);
};
```

Đây là snippet hợp lệ khi đặt trong phương thức hoặc initializer phù hợp. Trong môi trường production, thường dùng logger và hệ thống quan sát có cấu trúc; không phụ thuộc vào việc in ra console như hợp đồng ứng dụng.

## 3. Đăng ký handler cho từng thread và cho toàn ứng dụng

Java có hai điểm cấu hình chính:

**Per-thread handler:**

```java
Thread thread = new Thread(task, "import-worker");
thread.setUncaughtExceptionHandler((t, e) -> {
    System.err.println(t.getName() + " gặp lỗi: " + e);
});
thread.start();
```

Snippet này giả định `task` đã được định nghĩa. Handler được đặt **trước `start()`** để tránh race giữa lúc thread bắt đầu thất bại và lúc đăng ký handler. Handler gắn cho một đối tượng `Thread` cụ thể.

**Default handler dùng chung:**

```java
Thread.setDefaultUncaughtExceptionHandler((t, e) -> {
    System.err.println("Uncaught trong " + t.getName() + ": " + e);
});
```

Handler mặc định là cấu hình tĩnh ở cấp JVM, có ảnh hưởng rộng tới nhiều luồng sử dụng đường xử lý mặc định. Trong ứng dụng nhiều thư viện/framework, việc thay đổi nó có thể ảnh hưởng đến cơ chế báo lỗi đã tồn tại. Chỉ nên đặt tại ranh giới khởi tạo ứng dụng khi có quyền quản lý cấu hình đó.

Một số điểm API cần nhớ:

- `thread.setUncaughtExceptionHandler(handler)` gắn handler riêng cho thread; có thể đặt `null` để dùng cơ chế fallback.
- `thread.getUncaughtExceptionHandler()` trả về handler được gắn trực tiếp, hoặc `ThreadGroup` tương ứng nếu chưa gắn trực tiếp. **Không nên hiểu** kết quả trả về luôn là chính default handler hiện được đặt.
- `Thread.setDefaultUncaughtExceptionHandler(handler)` đặt default handler; `Thread.getDefaultUncaughtExceptionHandler()` đọc giá trị ấy.
- Khi có `ThreadGroup` custom hoặc môi trường quản lý thread riêng, luồng báo lỗi còn phụ thuộc cách group/framework xử lý.

## 4. Thứ tự chọn handler của JVM

Với một thread đang kết thúc do uncaught exception, thứ tự diễn giải cơ bản:

1. Nếu thread có handler được đặt trực tiếp bằng `setUncaughtExceptionHandler`, JVM gọi handler ấy.
2. Nếu không, thread sử dụng `ThreadGroup` như uncaught-exception handler.
3. Implementation mặc định của `ThreadGroup.uncaughtException` có thể ủy quyền lên group cha; ở group gốc nó có thể chuyển cho default handler nếu có.
4. Nếu không có default handler phù hợp, implementation chuẩn của `ThreadGroup` thường in thông tin lỗi ra `System.err`. Có quy tắc riêng đối với `ThreadDeath`.

Điểm quan trọng: **per-thread handler có độ ưu tiên thực tế cao hơn default handler** theo cơ chế nói trên. Nhưng không nên coi mọi thread đều chắc chắn đến default handler: một `ThreadGroup` ghi đè `uncaughtException` có thể xử lý theo cách khác, và framework có thể chủ động bắt lỗi trước khi exception thoát khỏi thread.

Sơ đồ khái niệm:

```text
Throwable thoát khỏi phần thực thi của Thread
              |
              v
Thread có handler riêng?
       /               \
     Có               Không
     |                  |
     v                  v
Handler riêng       ThreadGroup xử lý
                        |
                 Có thể chuyển lên group cha
                        |
                 Có thể dùng default handler
                        |
               Fallback theo ThreadGroup
```

Handler chỉ được thông báo khi thất bại **thực sự đến ranh giới kết thúc thread**. Câu lệnh `throw` ở bên trong một tác vụ không tự bảo đảm handler được gọi nếu lớp bao bên ngoài đã bắt exception.

## 5. Ví dụ Java 17 hoàn chỉnh: default và per-thread handler

Ví dụ sau tạo tuần tự hai thread. Thread thứ nhất không có handler riêng nên dùng default handler trong môi trường Java chuẩn; thread thứ hai có handler riêng. Cả hai ném exception chưa được bắt. `join()` giúp main chờ từng luồng hoàn tất, nhờ đó thứ tự dòng output có thể dự đoán.

Tạo tệp `UncaughtHandlerDemo.java`:

```java
public class UncaughtHandlerDemo {

    public static void main(String[] args) throws InterruptedException {
        Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();

        try {
            Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
                System.out.println(
                    "DEFAULT " + thread.getName()
                        + " " + error.getClass().getSimpleName()
                        + ": " + error.getMessage()
                );
            });

            Thread first = new Thread(() -> {
                throw new IllegalStateException("boom A");
            }, "default-worker");

            first.start();
            first.join();

            Thread second = new Thread(() -> {
                throw new IllegalArgumentException("boom B");
            }, "custom-worker");

            second.setUncaughtExceptionHandler((thread, error) -> {
                System.out.println(
                    "CUSTOM " + thread.getName()
                        + " " + error.getClass().getSimpleName()
                        + ": " + error.getMessage()
                );
            });

            second.start();
            second.join();

            System.out.println("MAIN finished");
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(previous);
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac -encoding UTF-8 UncaughtHandlerDemo.java
java UncaughtHandlerDemo
```

Kết quả chuẩn trong runtime Java thông thường:

```text
DEFAULT default-worker IllegalStateException: boom A
CUSTOM custom-worker IllegalArgumentException: boom B
MAIN finished
```

Phân tích:

- `first` có exception thoát khỏi `Runnable` và không có handler riêng; default handler in dòng bắt đầu bằng `DEFAULT`.
- `second` được gắn handler riêng **trước** khi bắt đầu nên dòng bắt đầu bằng `CUSTOM`. Default handler không xử lý cùng exception này trong luồng xử lý tiêu chuẩn.
- `join()` của từng thread chặn main đến khi thread đó chấm dứt. Trong ví dụ không có race khi main in `MAIN finished` vì từng thread đã hoàn tất.
- `finally` khôi phục default handler trước đó nhằm hạn chế tác động toàn cục nếu chạy ví dụ trong môi trường tích hợp. Một ứng dụng thực không nên đổi handler mặc định liên tục theo từng tác vụ.
- Handler ở đây cố ý in thông tin tối giản, không in full stack trace để output dễ kiểm tra. Khi vận hành thực, stack trace cùng cause/suppressed exception thường hữu ích để chẩn đoán.

`main` khai báo `throws InterruptedException` vì `join()` là thao tác blocking có checked exception đó. `InterruptedException` của main là vấn đề riêng và **không phải** lỗi `IllegalStateException`/`IllegalArgumentException` đã thoát khỏi các worker. Nếu main bị ngắt trong khi chờ, cách xử lý cần tuân thủ chính sách interruption của chương trình.

## 6. Handler được chạy ở đâu và làm được những gì?

Thông thường JVM gọi `uncaughtException(thread, error)` trên luồng đang kết thúc do lỗi; nó không tạo một “luồng cứu hộ” chuyên biệt để xử lý logic của ứng dụng. Do đó, công việc nặng hoặc blocking trong handler có thể làm chậm việc kết thúc thread, giữ tài nguyên hoặc gây deadlock trong hoàn cảnh bất lợi.

Handler hợp lý thường chỉ:

- Ghi nhận thất bại cùng danh tính thread, loại exception và ngữ cảnh an toàn.
- Thông báo cho bộ phận giám sát hoặc coordinator (nếu thiết kế ứng dụng có cơ chế đó).
- Kích hoạt chính sách đánh dấu thành phần không lành mạnh hoặc yêu cầu hệ thống dừng, với cân nhắc an toàn và tính nhất quán.
- Giữ handler tối giản, không phát sinh lỗi phụ và không giả định mọi hệ thống ngoại vi còn hoạt động khi JVM đang thiếu nguồn lực.

Handler **không thể** quay ngược instruction pointer về dòng ném lỗi, không khôi phục stack frame đã unwound và không biến thread chết thành thread đang chạy bình thường. Nếu muốn chạy lại một tác vụ, cần scheduler hoặc supervisor tạo công việc/đối tượng thread khác theo chính sách rõ ràng.

Javadoc của `Thread.UncaughtExceptionHandler` quy định exception do chính `uncaughtException` ném ra sẽ bị JVM **bỏ qua**. Do đó, không nên xây dựng hệ thống theo giả định rằng thất bại của logger/handler sẽ được chuyển tiếp sang một handler dự phòng.

Nếu chính handler ném lỗi:

```java
thread.setUncaughtExceptionHandler((t, e) -> {
    throw new IllegalStateException("handler also failed");
});
```

Đây chỉ là snippet minh họa, với `thread` tồn tại trong ngữ cảnh phù hợp. Lỗi của handler không được coi là phương pháp báo lỗi đáng tin cậy; thiết kế handler đơn giản và bảo đảm có chiến lược vận hành khi logging gặp trục trặc.

## 7. Khác biệt cốt lõi: Thread trực tiếp và ExecutorService.submit

Một nhầm lẫn thường gặp là nghĩ **mọi exception ném trong một tác vụ async sẽ vào `UncaughtExceptionHandler`**.

Xét lời gọi:

```java
Thread direct = new Thread(() -> {
    throw new IllegalStateException("direct failed");
});
direct.start();
```

Exception không được bắt có thể đến handler của `direct`.

Nhưng khi dùng:

```java
Future<?> future = executor.submit(() -> {
    throw new IllegalStateException("task failed");
});
```

Đây là snippet giả định `executor` đã được tạo. Với `ExecutorService.submit` chuẩn, tác vụ thường được bọc trong `FutureTask`. Exception của tác vụ được **bắt và ghi nhận trong `Future`**. Worker của executor có thể tiếp tục xử lý công việc khác; per-thread handler thường **không nhận** lỗi nghiệp vụ này.

Caller cần gọi `future.get()` để quan sát thất bại; với exception ở task, `get()` ném `ExecutionException` và nguyên nhân gốc nằm trong `getCause()`. Nếu caller bỏ qua `Future`, lỗi có thể không được quan sát theo ý định, dù nhiệm vụ thực sự đã thất bại.

### Ví dụ Java 17 hoàn chỉnh với submit và Future

Tạo tệp `FutureFailureDemo.java`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> result = executor.submit(() -> {
                throw new IllegalStateException("task failed");
            });

            try {
                result.get();
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println(
                    "FUTURE " + cause.getClass().getSimpleName()
                        + ": " + cause.getMessage()
                );
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

Lệnh chạy:

```bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
```

Stdout:

```text
FUTURE IllegalStateException: task failed
```

Giải thích:

- `submit` trả một `Future`, trong đó lưu tình trạng hoàn thành và lỗi của task.
- `result.get()` chờ task hoàn thành và ném `ExecutionException` khi task lỗi.
- `ExecutionException.getCause()` chứa `IllegalStateException` gốc; caller có thể quyết định retry, rollback, báo lỗi hoặc dừng workflow.
- `executor.shutdown()` ngừng nhận task mới và cho phép các task đã gửi tiếp tục hoàn thành; `shutdown()` không đồng nghĩa chờ tất cả task xong. Ở ví dụ này, `get()` đã đợi đúng task đó, nên output xác định.
- Không cần `UncaughtExceptionHandler` để nhận lỗi task được `submit` bắt. Nếu muốn logging tự động cho mọi tác vụ, cần thiết kế ở mức task wrapper, kết quả `Future` hoặc cơ chế quan sát của executor.

`result.get()` còn có thể ném `InterruptedException` khi thread chờ bị ngắt; phương thức `main` khai báo checked exception này. Trường hợp task bị hủy, `get()` có thể ném `CancellationException` (unchecked), khác với `ExecutionException` do task thất bại.

## 8. ExecutorService.execute và sự khác nhau với submit

Hai cách gửi một `Runnable` vào executor có thể làm thay đổi cách exception được quan sát:

| Cách thực thi | Cơ chế quan sát lỗi thường gặp | Lưu ý |
| --- | --- | --- |
| `new Thread(task).start()` | Exception thoát khỏi `run()` có thể đến uncaught handler | Thread chấm dứt khi exception thoát ra ngoài. |
| `executor.execute(task)` | Ở `ThreadPoolExecutor` chuẩn, exception unchecked không được bắt trong task có thể thoát khỏi worker và được báo qua handler/logging của worker | Chi tiết phụ thuộc triển khai executor, `ThreadFactory` và wrapper; không dựa duy nhất vào handler. |
| `executor.submit(task)` | Exception được lưu vào `Future`; caller quan sát qua `get()` | Có thể thất lạc tín hiệu lỗi nếu không ai kiểm tra `Future`. |
| `CompletableFuture.supplyAsync(...)` | Thất bại được ghi trong `CompletableFuture` | Quan sát qua `whenComplete`, `handle`, `exceptionally` hoặc `join/get`. |

Một `ThreadPoolExecutor` có thể sử dụng hook `afterExecute(Runnable r, Throwable t)` để quan sát tác vụ; nhưng với `FutureTask` được tạo bởi `submit`, tham số `t` có thể là `null` ngay cả khi task thất bại vì lỗi đã được lưu trong `Future`. Implementation cần kiểm tra `Future` và xử lý `ExecutionException` một cách có chủ đích nếu chọn cách này. Không nên tự gọi `get()` trên một `Future` chưa hoàn thành từ hook trong tình huống có thể gây chờ không cần thiết; với `afterExecute` của task đã hoàn thành, vẫn cần xử lý interruption/cancellation cẩn thận.

Quan trọng hơn, `ExecutorService` là abstraction thực thi tác vụ, không phải một `Thread` do client luôn sở hữu. Worker thread có thể được tái sử dụng, thay thế hoặc quản lý bởi framework; việc gắn handler trực tiếp cho một worker không đồng nghĩa quan sát được mọi lỗi trong các task.

## 9. CompletableFuture và exception bất đồng bộ

`CompletableFuture` là ví dụ rõ ràng về một lỗi được ghi nhận theo **kết quả bất đồng bộ** thay vì thoát khỏi điểm khởi đầu của thread.

```java
CompletableFuture<Integer> stage =
    CompletableFuture.supplyAsync(() -> {
        throw new IllegalArgumentException("bad input");
    });

stage.whenComplete((value, failure) -> {
    if (failure != null) {
        // Quan sát lỗi của stage, không trông chờ handler của worker.
    }
});
```

Đây là snippet minh họa, giả định import `java.util.concurrent.CompletableFuture`. Lỗi có thể được biểu diễn bằng `CompletionException` bọc cause tùy điểm quan sát và hình dạng chuỗi stage. `join()` thường ném `CompletionException` khi stage hoàn thành exceptional; `get()` dùng `ExecutionException` cho thất bại thông thường. Code xử lý nên dựa vào hợp đồng API của stage.

Tránh tạo callback `whenComplete` chỉ để log rồi bỏ qua kết quả mà không kiểm soát hành vi phụ hoặc luồng xử lý tiếp theo. Khi lỗi cần ảnh hưởng quyết định nghiệp vụ, hãy chuyển nó vào pipeline xử lý kết quả theo một chiến lược nhất quán.

## 10. Thread.join không truyền exception của worker về caller

`Thread.join()` chỉ đợi thread kết thúc. Nó **không ném lại exception chưa được bắt của worker** trên thread gọi `join()`.

Ví dụ với một worker tự tạo:

```java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("worker failed");
});
worker.start();
worker.join();

// Đã kết thúc thread, nhưng join không có kiểu kết quả để báo worker thất bại.
```

Snippet trên giả định nằm trong phương thức có xử lý `InterruptedException`. Sau `join()`, việc `worker.isAlive() == false` không cho biết worker thành công hay thất bại. Handler có thể ghi lỗi nhưng caller muốn phân biệt phải có cơ chế trao đổi trạng thái, ví dụ `Future`, `BlockingQueue`, `CountDownLatch` kết hợp nơi giữ kết quả, hoặc một wrapper trả kết quả có cấu trúc.

Nếu caller cần nhận hoặc xử lý thất bại như một kết quả tính toán, dùng `Future` hoặc API composition thường phù hợp hơn dùng global uncaught handler làm đường truyền lỗi.

## 11. Trường hợp đặc biệt: handler được gọi trên luồng “sắp chết”

Cách nghĩ đúng là handler nhận thông tin khi thread không thể tiếp tục đường thực thi cũ. Điều này dẫn đến các quyết định thiết kế:

**Không retry trực tiếp ngay trong handler theo cách tùy tiện.** Nếu thread vừa chết do lỗi bất ngờ, việc chạy lại một tác vụ có side effect có thể làm thao tác lặp, ghi dữ liệu hai lần hoặc rơi vào vòng lỗi vô hạn. Retry cần điều kiện, backoff, idempotency và giới hạn số lần.

**Không dựa vào handler để giải phóng mọi tài nguyên.** Resource được mở trong thread nên được đóng bởi `try-with-resources`/`finally` gần nơi tạo và sở hữu. Handler không biết toàn bộ ownership và có thể không chạy trong mọi kiểu chấm dứt tiến trình. Nó cũng có thể được gọi khi trạng thái chương trình đã bị lỗi nghiêm trọng.

**Không xem handler là nơi sửa trạng thái dùng chung.** Tại thời điểm thất bại, các invariant có thể đã bị phá. Một supervisor có thể đánh dấu thành phần không lành mạnh và dừng pipeline thay vì tự ý tiếp tục.

**Không khóa chéo dễ dẫn đến deadlock.** Nếu lỗi xảy ra trong thread đang giữ monitor/lock hoặc đang tham gia shutdown, handler gọi ngược sang chính subsystem đó có thể treo. Ưu tiên ghi nhận tối giản và truyền sự kiện thất bại cho hệ thống giám sát phù hợp.

## 12. Exception, Error, interruption và shutdown

Một số loại kết thúc công việc có cách xử lý khác nhau:

| Tình huống | Uncaught handler có nhất thiết được gọi? | Hướng xử lý |
| --- | --- | --- |
| `RuntimeException` thoát khỏi `Thread.run()` | Có, theo cơ chế uncaught-exception thông thường của thread | Ghi nhận nguyên nhân và trạng thái thành phần. |
| `Error` thoát khỏi thread | Handler nhận `Throwable`, nhưng việc báo cáo có thể không đáng tin trong lỗi nghiêm trọng | Tránh recovery liều lĩnh, cân nhắc fail-fast. |
| `InterruptedException` được bắt và xử lý đúng | Không, nếu không có exception mới thoát khỏi thread | Tuân thủ chính sách hủy; phục hồi cờ interrupt khi phù hợp. |
| `InterruptedException` bị bọc thành unchecked rồi thoát khỏi `run()` | Có thể có handler vì unchecked exception mới đã uncaught | Giữ cause và chính sách interrupt. |
| `FutureTask` bắt lỗi task được `submit` | Thông thường không | Kiểm tra `Future.get()` và cause. |
| `Thread.stop()` (API đã bị deprecated, không an toàn) | Không nên sử dụng để quản lý lỗi/cleanup | Dùng cooperative cancellation. |
| JVM/OS cưỡng bức kết thúc tiến trình | Không có bảo đảm handler hoặc `finally` sẽ chạy | Dựa vào recovery, supervision và quản lý tài nguyên ngoài tiến trình khi cần. |

`InterruptedException` là checked exception và `Runnable.run()` không khai báo checked exception, vì thế task thường cần bắt nó. Nếu muốn kết thúc sạch, có thể phục hồi interrupt rồi `return`:

```java
@Override
public void run() {
    try {
        blockingOperation();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    }
}
```

Đây là snippet minh họa; `blockingOperation` do ứng dụng cung cấp. Trường hợp này không tạo uncaught exception và handler không được gọi. Cách truyền tiếp hay dừng còn phụ thuộc semantics của thread.

`ThreadDeath` là `Error` đặc biệt từng liên quan đến `Thread.stop()`; `ThreadGroup` có hành vi fallback đặc biệt đối với nó. Đừng dựa vào cơ chế cũ này để hủy luồng.

## 13. Gắn handler bằng ThreadFactory trong ứng dụng nhiều worker

Nếu một thành phần thực sự **quản lý việc tạo thread**, có thể cấu hình per-thread handler ở `ThreadFactory`:

```java
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "service-worker");
    thread.setUncaughtExceptionHandler((t, error) -> {
        System.err.println(t.getName() + " failed: " + error);
    });
    return thread;
};
```

Đây là snippet minh họa (cần import `java.util.concurrent.ThreadFactory`). `ThreadFactory` thường được truyền cho các executor như `Executors.newFixedThreadPool(int, ThreadFactory)` để gắn cấu hình vào worker được tạo.

Nhưng **factory chỉ định handler cho thread**, không khiến exception do `submit` lưu trong `Future` tự nhiên thoát ra ngoài. Đừng nhầm “mọi worker có handler” với “mọi task exception đều được quan sát”.

Thiết kế production thường kết hợp:
- Handler cho thất bại *uncaught* của thread.
- Xử lý kết quả `Future` hoặc pipeline `CompletableFuture` cho task failure.
- Logging/metrics/tracing với định danh tác vụ và xử lý dữ liệu nhạy cảm.
- Chính sách dừng/restart phù hợp tại service/supervisor, không đặt trong handler riêng lẻ.

ThreadFactory còn được dùng để gắn tên dễ nhận diện và các thuộc tính thread theo yêu cầu. Không nên tự ý đặt `Thread.setDaemon(true)` nếu thay đổi semantics shutdown của ứng dụng mà chưa hiểu rõ hậu quả.

## 14. Java 21+ virtual threads và phạm vi kiến thức

Ví dụ ở đây dùng **platform thread**, chạy trên Java 17+. Từ Java 21, virtual threads cũng là `Thread` và có cơ chế xử lý uncaught exception, nhưng việc quản lý lifecycle và task thường dựa nhiều hơn vào structured concurrency hoặc executor. Nếu tác vụ virtual thread được bọc bởi abstraction lưu kết quả, cần phân biệt lỗi của task với uncaught exception theo chính abstraction đó.

Không nên suy luận rằng virtual thread bị lỗi sẽ làm toàn bộ nhóm công việc dừng hoặc tự động truyền exception sang thread cha. Cần đọc hợp đồng cụ thể của API tạo và chờ task đang sử dụng; nhóm tác vụ và cơ chế cancel/join có semantics riêng.

## 15. Một handler vận hành tốt cần ghi nhận điều gì?

Một bản ghi sự cố hữu ích có thể gồm:

- Thời điểm và danh tính tiến trình/service.
- Tên/ID thread, vai trò worker, tác vụ hoặc correlation ID nếu có.
- Loại `Throwable`, message, stack trace, chuỗi cause và suppressed exceptions.
- Mức độ nghiêm trọng hoặc trạng thái thành phần (healthy/degraded/unavailable).
- Thông tin đã được **lọc** để không lộ token, thông tin đăng nhập, dữ liệu cá nhân hoặc nội dung nhạy cảm.

Message exception không phải API dữ liệu ổn định. Đừng dùng so khớp message từ exception không được bắt để quyết định retry. Nếu tác vụ có thể thất bại vì quy tắc nghiệp vụ, nên chuyển thành lỗi có cấu trúc **trước khi** ra đến uncaught handler.

Một handler chỉ in `error.getMessage()` có thể bỏ mất nguyên nhân sâu hơn; ngược lại in toàn bộ exception vào hệ thống log công khai có thể làm lộ dữ liệu. Cần chọn logger và quyền truy cập phù hợp với môi trường.

## 16. Lỗi thường gặp

**Coi handler là `catch` để thread tiếp tục.** Sai vì handler chạy khi thread đang kết thúc do uncaught exception. Logic phục hồi cần đặt trong workflow hoặc supervisor.

**Chỉ đăng ký default handler rồi cho rằng `submit` đã được giám sát.** `submit` có thể bắt exception vào `Future`. Cần kiểm tra kết quả hoặc wrap các tác vụ.

**Dùng `join` như cơ chế phát hiện lỗi.** `join` chỉ chờ hoàn thành; không cho biết success/failure.

**Gắn handler sau `start`.** Thread có thể ném exception trước khi gắn. Đặt handler trước khi bắt đầu hoặc thông qua factory.

**Đặt lại default handler từ từng library.** Đây là cấu hình cấp JVM, có thể xung đột với framework hoặc code ứng dụng. Nếu library cần quan sát lỗi của chính nó, thường nên quản lý thread/task và handler của riêng mình.

**Handler ghi log rồi tự ném exception.** Exception do handler ném ra bị JVM bỏ qua; dễ mất cả báo cáo ban đầu nếu logging chưa hoàn tất.

**Làm công việc blocking hoặc nguy hiểm trong handler.** Handler có thể chạy trong bối cảnh thread đã lỗi và còn liên quan lock; việc kết thúc thread có thể bị chậm hoặc deadlock.

**Gọi `System.exit` vô điều kiện trong handler.** Có thể chấm dứt cả tiến trình vì lỗi của một worker không quan trọng. Chính sách dừng cả service phải do tầng vận hành và criticality quyết định.

**Bắt `Throwable` trong mọi `Runnable` chỉ để ngăn handler.** Có thể che `Error` nghiêm trọng và phá khả năng quan sát lỗi. Chỉ bắt những gì task thực sự có thể xử lý.

**Không quản lý tài nguyên khi lỗi uncaught.** Handler không thay cho `finally` hoặc `try-with-resources`; cleanup phải gắn với resource owner.

## 17. Kiểm thử handler và luồng quan sát lỗi

Các test nên dựa vào hành vi công khai, tránh so khớp format stack trace mặc định giữa JVM:

1. Với một `Thread` trực tiếp ném `IllegalStateException`, gắn per-thread handler thu nhận `Throwable` vào một cấu trúc thread-safe; gọi `start` rồi `join` và xác nhận handler được gọi, đúng thread/name/cause.
2. Với default handler, lưu handler cũ và khôi phục bằng `finally`; tránh làm test chạy song song bị ảnh hưởng bởi cấu hình toàn cục. Nếu runtime hoặc `ThreadGroup` tùy chỉnh có semantics khác, test phải có giả định môi trường rõ ràng.
3. Xác nhận handler per-thread được chọn thay cho default handler trong mô hình thread bình thường.
4. Với `ExecutorService.submit`, tạo task thất bại và xác nhận `Future.get` ném `ExecutionException` có cause đúng; không dùng việc handler có/không log như phép xác nhận duy nhất.
5. Với `CompletableFuture`, xác nhận stage hoàn thành exceptional và callback xử lý nhận đúng trạng thái.
6. Với thread cleanup tài nguyên, xác nhận `try-with-resources` hoặc `finally` thực thi dù task ném exception.
7. Đảm bảo handler không giữ cả tiến trình treo khi logger hoặc thành phần quan sát lỗi thất bại.

Ví dụ unit test thực có thể dùng `AtomicReference<Throwable>` hoặc `BlockingQueue<Throwable>` để ghi nhận exception từ handler mà không phụ thuộc vào console. Hãy đặt timeout phù hợp khi `join` hoặc `Future.get` trong môi trường CI để test không treo vô hạn nếu worker gặp deadlock.

## 18. Tự kiểm tra

**Câu 1:** `Runnable.run` ném `IllegalArgumentException` không ai bắt, và thread có per-thread handler. Handler có thể làm cho `run` chạy tiếp từ dòng sau `throw` không?

**Trả lời:** Không. Handler là nơi nhận thông báo lỗi cuối khi thread đang kết thúc. Muốn tiếp tục hoặc retry, ứng dụng phải có logic riêng và một execution context thích hợp.

**Câu 2:** Cùng một lỗi `IllegalStateException`, vì sao `new Thread(task).start()` có thể gọi handler nhưng `executor.submit(task)` thường không?

**Trả lời:** Với thread trực tiếp, exception có thể thoát khỏi entry point của thread. Với `submit`, task được bọc trong `FutureTask` và lỗi được lưu vào `Future` để caller lấy bằng `get`; worker không nhất thiết có uncaught exception.

**Câu 3:** `join()` trả về bình thường có nghĩa worker thành công?

**Trả lời:** Không. `join()` chờ thread kết thúc và không truyền exception của worker. Cần kênh trạng thái/kết quả riêng.

**Câu 4:** Tại sao một library không nên tự tiện thay default handler?

**Trả lời:** Default handler là cấu hình toàn JVM, có thể ảnh hưởng thread của framework hoặc phần khác của ứng dụng. Library nên quản lý lỗi của chính nó bằng handler/thread factory hoặc task result, và để chủ ứng dụng quyết định default policy.

**Câu 5:** Thread đang ghi file ném uncaught exception. Handler nên trực tiếp đóng mọi file của thread?

**Trả lời:** Không nên dựa vào handler làm owner tài nguyên. Mã sở hữu file phải dùng `try-with-resources`/`finally` để cleanup đúng phạm vi. Handler có nhiệm vụ quan sát thất bại và hỗ trợ xử lý vận hành.

## 19. Ghi nhớ khi thiết kế

`Thread.UncaughtExceptionHandler` trả lời câu hỏi **“điều gì xảy ra khi một Throwable thoát khỏi thread mà không được bắt?”**: runtime chọn handler và thông báo thất bại trước khi thread chấm dứt. Nó **không** thay `catch`, không tự truyền lỗi sang `join`, không thay cơ chế xử lý `Future`/`CompletableFuture` và không làm thread tự hồi phục.

Với thread tự tạo, cài per-thread handler trước `start`, có thể dùng default handler ở cấp ứng dụng để quan sát rộng. Với executor và pipeline bất đồng bộ, ưu tiên quan sát lỗi qua **hợp đồng kết quả của task**. Luôn làm cleanup gần resource owner và dùng supervisor hoặc chính sách service để quyết định ảnh hưởng của một thread thất bại.