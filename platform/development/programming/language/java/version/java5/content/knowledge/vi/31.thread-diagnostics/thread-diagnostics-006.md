# UncaughtExceptionHandler của luồng và bộ xử lý mặc định

## 1. Lỗi đã thoát khỏi tác vụ phải được nhìn thấy

Một luồng có thể kết thúc bình thường khi `run()` hoàn tất, hoặc kết thúc bất thường vì một ngoại lệ không được bắt thoát ra khỏi phần thực thi.

Nếu chỉ quan tâm luồng “đã dừng chưa”, chương trình có thể bỏ lỡ nguyên nhân khiến công việc biến mất. Để chẩn đoán, cần ghi nhận ít nhất luồng nào gặp lỗi và lỗi gốc là gì.

`Thread.UncaughtExceptionHandler` là điểm nhận thông báo khi luồng sắp kết thúc vì một ngoại lệ không được bắt. Nó nhận hai đối số:

```java
void uncaughtException(Thread thread, Throwable error)
```

`Thread` cho biết luồng lỗi; `Throwable` chứa đối tượng lỗi cùng dấu vết ngăn xếp và nguyên nhân liên quan. Đây là cơ chế vẫn được hỗ trợ trên JDK hiện đại; xem [Thread.UncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.UncaughtExceptionHandler.html).

Handler là **điểm quan sát ở cuối đường lỗi của luồng**. Nó không quay ngược về câu lệnh vừa ném lỗi và không làm `run()` tiếp tục từ chỗ đó.

## 2. Ngoại lệ không được bắt nghĩa là gì?

Một lỗi xảy ra bên trong tác vụ chưa chắc sẽ đến handler:

```java
// Mã minh họa: lỗi đã được bắt trong luồng.
try {
    processInput();
} catch (IllegalArgumentException failure) {
    reportInvalidInput(failure);
}
```

Nếu lỗi đã được bắt và không ném lại ra ngoài, nó không còn là ngoại lệ chưa xử lý ở ranh giới kết thúc luồng.

Đối chiếu:

```java
// Mã minh họa: lỗi thoát khỏi thân Runnable.
Runnable task = () -> {
    throw new IllegalStateException("Cannot continue");
};
```

Khi `Runnable` này chạy trực tiếp làm thân một luồng và không có lớp bao bắt lỗi, ngoại lệ thoát khỏi `run()` khiến luồng kết thúc bất thường.

Do đó cần hỏi **ai đang bao quanh tác vụ**. Một bộ khung hoặc một đối tượng `FutureTask` có thể bắt và lưu lỗi trước khi lỗi đi tới ranh giới luồng.

## 3. Handler riêng của từng luồng

Cài handler trước khi bắt đầu luồng để không bỏ lỡ lỗi xảy ra sớm:

```java
// Mã minh họa.
Thread worker = new Thread(() -> {
    performWork();
}, "report-worker");

worker.setUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Uncaught failure in " + thread.getName());
    error.printStackTrace(System.err);
});

worker.start();
```

Handler riêng phù hợp khi bên tạo luồng hiểu rõ trách nhiệm của luồng đó. Nên đặt tên luồng có ý nghĩa để thông báo liên hệ được với công việc.

Hàm handler được gọi trong luồng đang kết thúc, không phải tự động chuyển sang một luồng ghi log riêng. Nếu dùng cùng một đối tượng handler cho nhiều luồng, nó có thể bị gọi đồng thời; mọi trạng thái dùng chung bên trong handler phải được xử lý an toàn.

Cài handler sau `start()` có thể quá muộn: tác vụ rất ngắn có thể đã phát sinh lỗi trước khi cấu hình hoàn tất.

## 4. Handler mặc định và thứ tự lựa chọn

Ứng dụng có thể cài một handler mặc định:

```java
// Mã minh họa.
Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    logUnexpectedThreadFailure(thread, error);
});
```

Handler mặc định là cấu hình tĩnh dùng chung trong JVM, không phải một thuộc tính chỉ của luồng đang gọi phương thức.

Cơ chế lựa chọn có thể hiểu như sau:

```text
Có handler riêng của luồng?
    ├─ Có → gọi handler riêng
    └─ Không → cơ chế chuyển tiếp qua ThreadGroup
                  ↓ nếu không có xử lý chuyên biệt ở đường đó
             handler mặc định, nếu đã cấu hình
```

Đường `ThreadGroup` ở đây giải thích cơ chế chuyển tiếp của API; không cần xây nhóm luồng tùy chỉnh để dùng handler trong ứng dụng mới. Xem [Thread.setDefaultUncaughtExceptionHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html#setDefaultUncaughtExceptionHandler(java.lang.Thread.UncaughtExceptionHandler)).

Các hệ quả thực tế:

- Handler riêng không tự động gọi tiếp handler mặc định.
- Handler mặc định không phải một bộ bắt mọi lỗi ở mọi nơi.
- Đặt handler riêng thành `null` gỡ cấu hình riêng; nó không có nghĩa “chặn mọi thông báo”.
- Đặt handler mặc định thành `null` nghĩa là không có handler mặc định do ứng dụng cài.
- Mã dùng chung không nên tùy tiện thay cấu hình mặc định của cả ứng dụng.

Khi không có xử lý riêng hoặc mặc định phù hợp, cơ chế tiêu chuẩn thường in chẩn đoán ra `System.err`. Đừng dựa vào dòng in đó thay cho kênh nhận kết quả của tác vụ.

## 5. Ví dụ đầy đủ: riêng, mặc định, bắt tại chỗ và Future

Chương trình tạo ba luồng theo thứ tự. Mỗi luồng được `join()` trước khi chuyển sang trường hợp tiếp theo để kết quả in có thứ tự xác định.

Sau đó chương trình gửi một tác vụ lỗi bằng `submit()` và lấy lỗi qua `Future.get()`.

Tệp `UncaughtHandlerDemo.java`, chạy trên JDK 17 trở lên:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class UncaughtHandlerDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();
        AtomicInteger calls = new AtomicInteger();

        try {
            Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
                calls.incrementAndGet();
                System.out.println("default:" + thread.getName() + ":"
                        + error.getClass().getSimpleName());
            });

            Thread specific = new Thread(() -> {
                throw new IllegalStateException("specific failure");
            }, "specific-worker");
            specific.setUncaughtExceptionHandler((thread, error) -> {
                calls.incrementAndGet();
                System.out.println("specific:" + thread.getName() + ":"
                        + error.getClass().getSimpleName());
            });
            specific.start();
            specific.join();

            Thread fallback = new Thread(() -> {
                throw new IllegalArgumentException("fallback failure");
            }, "fallback-worker");
            fallback.start();
            fallback.join();

            Thread caught = new Thread(() -> {
                try {
                    throw new IllegalStateException("handled locally");
                } catch (IllegalStateException expected) {
                    System.out.println("caught:" + expected.getMessage());
                }
            }, "caught-worker");
            caught.start();
            caught.join();

            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<?> result = pool.submit(() -> {
                    throw new IllegalStateException("submitted failure");
                });
                try {
                    result.get();
                    throw new AssertionError("Failure expected");
                } catch (ExecutionException failure) {
                    System.out.println("future:"
                            + failure.getCause().getMessage());
                }
            } finally {
                pool.shutdownNow();
            }

            System.out.println("handlerCalls=" + calls.get());
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(previous);
        }
    }
}
```

Biên dịch và chạy:

```shell
javac UncaughtHandlerDemo.java
java UncaughtHandlerDemo
```

Kết quả:

```text
specific:specific-worker:IllegalStateException
default:fallback-worker:IllegalArgumentException
caught:handled locally
future:submitted failure
handlerCalls=2
```

Giải thích từng đường đi:

| Trường hợp | Nơi nhận lỗi | Có gọi handler không? |
| --- | --- | --- |
| `specific-worker` ném lỗi ra ngoài | Handler riêng | Có, một lần |
| `fallback-worker` không có handler riêng | Handler mặc định qua cơ chế chuyển tiếp tiêu chuẩn | Có, một lần |
| `caught-worker` bắt lỗi bên trong | Khối `catch` của tác vụ | Không |
| Tác vụ gửi bằng `submit()` | `ExecutionException.getCause()` khi lấy Future | Không, với cơ chế submit trong ví dụ |

Số lần gọi là 2, không phải 3 hay 4. Handler mặc định không được gọi thêm sau handler riêng, và lỗi của tác vụ `submit` đã được lưu vào kết quả tính toán.

Ví dụ chỉ in tên loại lỗi để stdout ngắn và ổn định. Trong chẩn đoán thật, cần giữ cả đối tượng lỗi hoặc stack trace, không chỉ tên lớp hay thông điệp.

Giá trị handler mặc định cũ được lưu và phục hồi trong `finally` vì đây là cấu hình dùng chung. Việc lưu/phục hồi này phù hợp với chương trình minh họa kiểm soát được vòng đời; nó không tạo quyền sửa cấu hình toàn cục an toàn giữa nhiều thành phần đang tự thay handler đồng thời.

## 6. Vì sao try/catch quanh start() không bắt lỗi bên trong luồng?

Một nhầm lẫn phổ biến:

```java
// Ví dụ sai nếu mong catch bắt lỗi phát sinh trong run của worker.
try {
    worker.start();
} catch (RuntimeException failure) {
    handleWorkerFailure(failure);
}
```

Khối `try` chạy trong luồng gọi `start()`. Nó có thể bắt lỗi ném ra từ chính lời gọi đó, nhưng thân tác vụ chạy trên ngăn xếp của luồng khác.

Tương tự:

```java
worker.start();
worker.join();
```

`join()` đợi luồng kết thúc. Nó không tự ném lại lỗi mà luồng kia đã gặp và không biến “đã kết thúc” thành “đã thành công”.

Nếu cần bên điều phối nhận lỗi theo một kết quả có thể kiểm tra, dùng `Future`, một kiểu kết quả riêng hoặc cơ chế truyền lỗi được đồng bộ hóa. Handler có thể bổ sung chẩn đoán; nó không thay thế giao thức kết quả đó.

## 7. Lưu ý với ExecutorService: execute và submit

Với một `ThreadPoolExecutor` thông thường, lỗi không được bắt của một `Runnable` gửi trực tiếp qua `execute()` có thể thoát tới ranh giới luồng thực thi và đi tới handler. Nếu tự tạo nhóm thực thi, có thể cài handler khi `ThreadFactory` tạo từng luồng:

```java
// Mã minh họa; failureHandler đã được định nghĩa.
ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "background-worker");
    thread.setUncaughtExceptionHandler(failureHandler);
    return thread;
};
ExecutorService pool = Executors.newFixedThreadPool(2, factory);
```

Đây là cấu hình cho các luồng của nhóm. Để chẩn đoán nhiều tác vụ, nên có thêm định danh tác vụ, vì một luồng có thể thực hiện nhiều công việc nối tiếp.

Với `submit()`, tác vụ thường được bọc để lưu kết quả hoặc lỗi vào `Future`. Không thể chỉ cài handler rồi bỏ qua `Future` mà kỳ vọng mọi lỗi được ghi nhận. Tài liệu [ThreadPoolExecutor.afterExecute](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html#afterExecute(java.lang.Runnable,java.lang.Throwable)) giải thích khác biệt giữa ngoại lệ thoát trực tiếp và ngoại lệ được đối tượng tác vụ lưu lại.

```java
// Mã minh họa trong phương thức có thể ném InterruptedException.
Future<?> result = pool.submit(task);
try {
    result.get();
} catch (ExecutionException failure) {
    reportTaskFailure(failure.getCause());
}
```

`get()` cũng có thể bị ngắt; `Future` còn có trạng thái hủy. Phải xử lý theo vòng đời tác vụ. Xem [hợp đồng Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html).

Không khái quát mọi executor hoặc bộ khung đều có cùng đường xử lý lỗi. Lớp bao tác vụ, hook và chính sách riêng có thể đổi nơi lỗi được lưu. Khi chẩn đoán, lần theo đường gửi tác vụ và đường đọc kết quả thật sự.

## 8. Handler nên làm gì?

Một handler thường có trách nhiệm ngắn và rõ:

- Ghi nhận tên luồng và thời điểm lỗi.
- Ghi nguyên đối tượng lỗi để giữ stack trace và chuỗi nguyên nhân.
- Gắn thông tin ngữ cảnh có thể lấy an toàn.
- Phát tín hiệu cho một bộ giám sát đã được thiết kế sẵn, nếu ứng dụng cần.

Ví dụ minh họa sử dụng logging chuẩn của JDK:

```java
System.Logger logger = System.getLogger("thread-failures");

Thread.UncaughtExceptionHandler handler = (thread, error) -> {
    logger.log(
            System.Logger.Level.ERROR,
            "Uncaught failure in " + thread.getName(),
            error);
};
```

Handler cần đáng tin cậy vì nó chạy lúc công việc đã thất bại. Tránh tính toán dài, chờ vô hạn, giữ nhiều khóa hoặc dựa vào một tài nguyên mà luồng lỗi có thể đang làm hỏng.

Nếu handler tự ném ngoại lệ, JVM bỏ qua ngoại lệ do phương thức handler ném ra theo hợp đồng API. Nó không tự đưa lỗi đó sang handler mặc định để thử cứu lần nữa. Vì vậy không dùng việc ném lại từ handler như cách chuyển tiếp chẩn đoán.

Default handler cũng không nên gọi ngược về `thread.getThreadGroup().uncaughtException(...)`: đường chuyển tiếp có thể quay trở lại chính default handler và tạo đệ quy vô hạn.

Nếu muốn gọi một handler đã có trước đó, phải quyết định tường minh và tránh vòng gọi lại hoặc ghi log hai lần. Không mặc định rằng mọi cấu hình cũ đều an toàn để gọi chuỗi.

## 9. Handler không làm nhiệm vụ khôi phục tùy ý

Khi handler chạy, phần thực thi đã thoát do lỗi; không có thao tác “tiếp tục ngay sau dòng lỗi”. Luồng cũng không được khởi động lại bằng cách gọi `start()` thêm lần nữa.

Cũng không nên tự động chạy lại tác vụ từ handler mà chưa có chính sách:

- Tác vụ có thể đã gây tác dụng phụ trước khi lỗi.
- Chạy lại có thể tạo bản ghi trùng hoặc gửi yêu cầu hai lần.
- Một lỗi lặp có thể tạo vòng tái khởi động không giới hạn.
- Một lỗi nghiêm trọng của tài nguyên không được sửa chỉ bằng việc tạo luồng mới.

Nếu cần khôi phục, để tầng điều phối biết danh tính tác vụ, tính an toàn khi thử lại, hạn mức thử và trạng thái tài nguyên. Handler chỉ gửi bằng chứng hoặc tín hiệu mà tầng đó cần.

Vì đối số là `Throwable`, handler có thể nhận cả `Error`, không chỉ `RuntimeException`. Nhận được thông báo không chứng minh hệ thống còn đủ tài nguyên để làm công việc phức tạp. Thiết kế đường chẩn đoán nhỏ và có giới hạn, đặc biệt khi lỗi liên quan tài nguyên.

## 10. Kiểm tra bằng thực nghiệm, không chỉ đọc cấu hình

Khi xác minh hệ thống đã ghi nhận lỗi:

1. Tạo một tác vụ thử ném lỗi có kiểm soát.
2. Kiểm tra nó chạy trực tiếp trên luồng, qua `execute` hay qua `submit`.
3. Xác định handler riêng có được cài **trước khi luồng chạy** không.
4. Xác định có lớp bao bắt lỗi trước ranh giới luồng không.
5. Kiểm tra log giữ được stack trace và nguyên nhân gốc.
6. Kiểm tra bên điều phối có nhận trạng thái thất bại, thay vì chỉ thấy luồng đã kết thúc.
7. Xác nhận thử nghiệm không để lại handler mặc định đã thay hoặc nhóm thực thi còn chạy.

Bài tập:

- Gỡ handler riêng khỏi `specific-worker`: với cơ chế nhóm tiêu chuẩn trong ví dụ, lỗi sẽ đi tới handler mặc định.
- Thêm `catch` vào thân `fallback-worker` và không ném lại: handler mặc định không được gọi cho lỗi đó.
- Bỏ lời gọi `result.get()` trong phần `submit`: tác vụ vẫn thất bại, nhưng chương trình không còn đọc và in lỗi đã được Future lưu.
- Thử ném lỗi ngay sau khi một tác vụ đã tạo tác dụng phụ giả lập. Vì sao handler không đủ thông tin để tự quyết định chạy lại an toàn?

Điều cần phân biệt là **nơi ghi nhận lỗi cuối đời luồng** và **nơi quản lý kết quả, hủy hoặc thử lại của từng tác vụ**. Khi hai trách nhiệm được nối rõ ràng, lỗi không còn bị nhầm với một lần hoàn tất bình thường.
