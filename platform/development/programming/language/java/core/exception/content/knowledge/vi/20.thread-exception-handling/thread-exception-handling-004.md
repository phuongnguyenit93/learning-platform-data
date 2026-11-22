# Handler riêng, ThreadGroup và handler mặc định khi luồng Java gặp ngoại lệ chưa được bắt

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện tình huống một ngoại lệ thoát khỏi phương thức `run()` của luồng mà không được bắt.
- Giải thích vai trò của `Thread.UncaughtExceptionHandler`, handler riêng của từng `Thread`, `ThreadGroup` và handler mặc định toàn tiến trình.
- Xác định đúng thứ tự xử lý: handler gán riêng cho luồng, handler của nhóm luồng và chuỗi nhóm cha, sau đó đến default handler hoặc cách in lỗi dự phòng.
- Viết handler có thể quan sát lỗi mà không làm gián đoạn hoặc che giấu đường xử lý khác; biết cách gắn handler **trước khi khởi động luồng**.
- Phân biệt ngoại lệ thoát khỏi luồng với ngoại lệ đã được lưu trong `Future` của `ExecutorService.submit()`.
- Kiểm thử hành vi xử lý ngoại lệ một cách xác định mà không phụ thuộc vào thứ tự lập lịch ngẫu nhiên hoặc nội dung stack trace.

## 2. Khi nào uncaught exception handler được gọi?

Mỗi luồng Java có một đường thực thi. Khi một `Throwable` lan truyền ra ngoài đoạn thực thi cao nhất của luồng mà không được code ứng dụng bắt, JVM dùng cơ chế xử lý **uncaught exception** cho luồng đó.

Ví dụ minh họa trong một chương trình có luồng riêng:

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Tác vụ không thể tiếp tục");
}, "worker");
worker.start();
~~~

Khối `run()` ném lỗi và không có `catch` bao quanh. Đây là **ngoại lệ không được bắt ở luồng worker**. Nó không tự động nhảy sang một khối `catch` đang bao quanh lời gọi `worker.start()` của luồng cha.

Phân biệt ba hoạt động:

1. **Tạo luồng:** `new Thread(...)` tạo đối tượng, chưa chạy công việc.
2. **Khởi động:** `start()` yêu cầu JVM bắt đầu đường thực thi mới. `start()` bình thường không đợi toàn bộ `run()` hoàn tất.
3. **Thực thi công việc:** nếu exception thoát khỏi `run()`, quá trình xử lý ngoại lệ chưa bắt diễn ra trên đường kết thúc của chính luồng đó.

`Thread.join()` chỉ đợi luồng kết thúc, **không chuyển ngoại lệ của luồng con thành ngoại lệ được ném ở luồng gọi `join()`**. Nếu muốn thu thập kết quả thành công/thất bại để luồng khác xử lý, cần thêm cơ chế truyền kết quả, chẳng hạn `Future`, biến trạng thái được đồng bộ hóa hoặc hệ thống giám sát thích hợp.

### Handler làm gì và không làm gì?

`Thread.UncaughtExceptionHandler` là một interface có một phương thức:

~~~java
@FunctionalInterface
public interface UncaughtExceptionHandler {
    void uncaughtException(Thread t, Throwable e);
}
~~~

Đây là **dạng chữ ký API được rút gọn để học**, không phải lớp cần tự khai báo. JVM gọi phương thức tương ứng khi có ngoại lệ chưa được bắt, truyền vào **luồng gặp lỗi** và **đối tượng lỗi**.

Handler thường dùng để ghi log, lưu thông tin sự cố, gửi tín hiệu tới thành phần quản lý hoặc thống nhất cách báo cáo lỗi nghiêm trọng. Nó **không khôi phục ngăn xếp và không làm công việc của luồng tiếp tục tại dòng sau lệnh ném lỗi**.

Một ngoại lệ có thể được xử lý ngay tại nơi phát sinh nếu code có giải pháp phục hồi phù hợp. Uncaught handler chỉ là điểm quan sát cuối cùng cho lỗi đã thoát khỏi phần xử lý của luồng.

## 3. Ba mức xử lý: từng luồng, ThreadGroup, mặc định

Có ba cơ chế cần phân biệt:

| Cơ chế | Đăng ký/cấu hình | Phạm vi chủ yếu |
| --- | --- | --- |
| Handler riêng của một luồng | `thread.setUncaughtExceptionHandler(handler)` | Chỉ luồng được gán handler |
| Handler qua `ThreadGroup` | `ThreadGroup.uncaughtException(thread, error)` | Luồng trong nhóm không có handler riêng; có thể chuyển tiếp lên nhóm cha |
| Handler mặc định | `Thread.setDefaultUncaughtExceptionHandler(handler)` | Điểm dự phòng toàn JVM qua cơ chế nhóm luồng khi không có handler được chọn ở mức gần hơn |

Các nhóm luồng của JDK cũng thực hiện `Thread.UncaughtExceptionHandler`. Theo hợp đồng `Thread.getUncaughtExceptionHandler()`, nếu luồng đã được gán handler riêng thì trả về handler đó; nếu chưa, nhóm `ThreadGroup` của luồng là handler được dùng.

Điều này giải thích vì sao **default handler không đơn giản là giá trị trả về trực tiếp của `getUncaughtExceptionHandler()`** khi chưa gán handler riêng: thông thường phương thức sẽ trả về đối tượng `ThreadGroup`, và chính logic mặc định của `ThreadGroup` mới tìm tới handler mặc định.

### Sơ đồ ưu tiên

~~~text
Ngoại lệ thoát khỏi run() của Thread T
                    |
                    v
T có handler riêng không?
      | Có                    | Không
      v                       v
Gọi handler riêng       Gọi T.getThreadGroup()
      |                       |
      |                       v
      |               ThreadGroup.uncaughtException(T, e)
      |                       |
      |              +--------+---------------------+
      |              | nhóm override và xử lý     |
      |              |                            |
      |              | logic mặc định của nhóm    |
      |              | -> có nhóm cha: chuyển lên |
      |              | -> tới nhóm gốc:            |
      |              |    kiểm tra default handler |
      |              |    nếu không có: in lỗi     |
      v              v                            v
   Kết thúc xử lý báo cáo; luồng lỗi không tự chạy tiếp
~~~

Sơ đồ mô tả **đường xử lý thường gặp** dựa trên `ThreadGroup` tiêu chuẩn. Một lớp con của `ThreadGroup` có thể ghi đè `uncaughtException()` và tự quyết định có gọi `super.uncaughtException(...)` hay không. Vì thế, handler mặc định **không chắc chắn sẽ được gọi** nếu group tùy biến đã xử lý và không chuyển tiếp.

## 4. Handler riêng của Thread

Đăng ký một handler cho một luồng cụ thể:

~~~java
Thread worker = new Thread(() -> {
    throw new IllegalStateException("Lỗi xử lý");
}, "import-worker");

worker.setUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Luồng lỗi: " + thread.getName());
    System.err.println("Kiểu lỗi: " + error.getClass().getName());
});

worker.start();
~~~

Đây là **đoạn minh họa độc lập trong một phương thức**, có thể đặt trong `main` của một lớp Java. Handler riêng có hai tham số:

- `thread`: luồng mà lỗi không được bắt.
- `error`: chính đối tượng `Throwable` đã thoát ra, có thể chứa cause chain, stack trace và suppressed exceptions.

Khi handler riêng đã được gán, nó được ưu tiên hơn logic `ThreadGroup.uncaughtException()` của cùng luồng. Nếu chỉ cần xử lý lỗi cho một công việc độc lập, đây là lựa chọn dễ kiểm soát nhất.

**Đăng ký trước `start()`.** Nếu đợi tới sau khi khởi động, công việc có thể ném lỗi trước khi handler được gán. Đây là race condition. Trong các hệ thống có `ThreadFactory`, nên gán handler ngay lúc tạo đối tượng luồng, trước khi trả luồng cho executor.

### setUncaughtExceptionHandler(null) nghĩa là gì?

Gọi `thread.setUncaughtExceptionHandler(null)` xóa handler đã gán riêng cho luồng. Khi có lỗi chưa bắt về sau, luồng quay về dùng handler dự phòng của nó, thông thường là `ThreadGroup`. Lời gọi này **không** thiết lập một “handler rỗng” có chức năng nuốt lỗi.

Không nên đặt `null` chỉ để tắt ghi nhận lỗi. Nếu cần thay hành vi báo cáo, hãy chọn handler thích hợp và xem tác động tới giám sát của ứng dụng.

## 5. ThreadGroup vừa gom luồng, vừa tham gia xử lý ngoại lệ

`ThreadGroup` cho phép đặt luồng vào một nhóm. Ngoài các chức năng quản lý nhóm mang tính lịch sử, nó triển khai `Thread.UncaughtExceptionHandler` và đóng vai trò handler dự phòng của các luồng không có handler riêng.

Một nhóm có thể có nhóm cha. Triển khai `ThreadGroup.uncaughtException()` chuẩn xử lý đại ý như sau:

1. Nếu có nhóm cha, gọi `parent.uncaughtException(thread, error)`.
2. Nếu đã tới nhóm gốc, lấy `Thread.getDefaultUncaughtExceptionHandler()`.
3. Nếu default handler không phải `null`, gọi handler đó.
4. Nếu không có default handler, in thông tin ngoại lệ cùng stack trace ra `System.err`, ngoại trừ cách xử lý đặc biệt với `ThreadDeath` của JDK.

Vì vậy, khi dùng `ThreadGroup` tiêu chuẩn không override, ngoại lệ có thể đi qua nhiều nhóm cha trước khi tới handler mặc định. Cơ chế này không tạo ra exception mới; nó chuyển đối tượng lỗi được nhận lên phương thức xử lý tiếp theo.

### Ghi đè uncaughtException trong nhóm

~~~java
class LoggingGroup extends ThreadGroup {
    LoggingGroup(String name) {
        super(name);
    }

    @Override
    public void uncaughtException(Thread thread, Throwable error) {
        System.err.println("Nhóm bắt gặp lỗi ở " + thread.getName());
        error.printStackTrace(System.err);
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, đặt trong tệp/phạm vi phù hợp. Vì phương thức override không gọi `super.uncaughtException(...)`, luồng thuộc nhóm này và không có handler riêng sẽ được báo cáo tại đây; lỗi **không tự động tiếp tục** tới nhóm cha hoặc default handler.

Nếu muốn bổ sung log của nhóm nhưng vẫn chuyển lên cấp mặc định, có thể gọi `super.uncaughtException(thread, error)`. Khi ấy có khả năng một sự cố bị ghi log hai lần, vì cả nhóm và handler bên trên đều báo cáo. Quy định rõ ai chịu trách nhiệm ghi log cuối cùng để tránh trùng lặp.

**Lưu ý thiết kế:** `ThreadGroup` có nhiều API quản lý luồng không còn được ưu tiên trong code hiện đại. Nếu chỉ cần gắn handler nhất quán cho những luồng do mình tạo, `ThreadFactory` hoặc gắn handler trực tiếp thường dễ bảo trì hơn. Tuy nhiên, cần hiểu cơ chế nhóm vì nó nằm trong đường dự phòng của xử lý ngoại lệ chưa bắt.

## 6. Handler mặc định của JVM

Đăng ký handler toàn cục:

~~~java
Thread.UncaughtExceptionHandler previous =
        Thread.getDefaultUncaughtExceptionHandler();

Thread.setDefaultUncaughtExceptionHandler((thread, error) -> {
    System.err.println("Unhandled error in " + thread.getName());
    error.printStackTrace(System.err);
});
~~~

Đây là **đoạn minh họa**, đặt trong ứng dụng có chiến lược quản lý vòng đời handler phù hợp. `setDefaultUncaughtExceptionHandler` là phương thức `static` trên `Thread`.

Handler mặc định hữu ích khi muốn có một điểm báo cáo dự phòng chung. Nó không ghi đè handler riêng đã gán cho từng luồng và không cưỡng ép một `ThreadGroup` tùy biến phải chuyển lỗi lên mặc định.

Một số nguyên tắc khi đăng ký:

- Cấu hình sớm tại điểm khởi tạo ứng dụng để tránh bỏ sót lỗi từ luồng khởi động trước.
- Đăng ký một cách có chủ đích, vì mọi phần của cùng JVM có thể chịu ảnh hưởng của default handler.
- Khi viết ví dụ hoặc kiểm thử, có thể lưu giá trị cũ bằng `getDefaultUncaughtExceptionHandler()` và khôi phục nó sau khi các luồng đã kết thúc.
- Khi nhiều thư viện cùng sửa default handler, giá trị thiết lập sau có thể thay thế giá trị trước. Không dùng cơ chế này như kênh trao đổi trạng thái giữa các thành phần độc lập.
- Handler mặc định không thay thế cơ chế giám sát lỗi của framework, `Future` hoặc ứng dụng web nơi ngoại lệ thường được bắt và chuyển thành kết quả theo cách riêng.

Nếu không có default handler và đường chuẩn của `ThreadGroup` tới điểm dự phòng cuối cùng, JDK thường in dòng dạng `Exception in thread "..."` và stack trace vào `System.err`. Chuỗi cụ thể có thể phụ thuộc runtime; không nên coi đây là API log có định dạng ổn định. Trường hợp `ThreadDeath` có xử lý đặc biệt trong `ThreadGroup` tiêu chuẩn; không dùng `Thread.stop()` để tạo tình huống thử nghiệm vì API này không an toàn và đã bị loại khỏi thực hành hiện đại.

## 7. Ví dụ Java 17+ độc lập: kiểm tra ba mức ưu tiên

Bài chạy độc lập dưới đây tạo ba luồng lần lượt để stdout có thứ tự xác định:

1. Một luồng vừa thuộc nhóm tùy biến vừa có handler riêng: **handler riêng được gọi**.
2. Một luồng thuộc nhóm tùy biến nhưng không có handler riêng: **handler của nhóm được gọi**.
3. Một luồng thuộc nhóm tiêu chuẩn và không có handler riêng: lỗi được chuyển lên **handler mặc định**.

Lưu toàn bộ chương trình vào tệp **HandlerDispatchDemo.java**:

~~~java
public class HandlerDispatchDemo {
    static final class ObservingGroup extends ThreadGroup {
        ObservingGroup(String name) {
            super(name);
        }

        @Override
        public void uncaughtException(Thread thread, Throwable error) {
            System.out.println("GROUP: " + thread.getName()
                    + " -> " + error.getMessage());
        }
    }

    static Thread failingThread(ThreadGroup group, String name, String message) {
        return new Thread(group, () -> {
            throw new IllegalStateException(message);
        }, name);
    }

    public static void main(String[] args) throws InterruptedException {
        Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();

        try {
            Thread.setDefaultUncaughtExceptionHandler((thread, error) ->
                    System.out.println("DEFAULT: " + thread.getName()
                            + " -> " + error.getMessage()));

            ThreadGroup specialGroup = new ObservingGroup("special");
            Thread local = failingThread(
                    specialGroup, "worker-local", "local-failure");
            local.setUncaughtExceptionHandler((thread, error) ->
                    System.out.println("THREAD: " + thread.getName()
                            + " -> " + error.getMessage()));
            local.start();
            local.join();

            Thread grouped = failingThread(
                    specialGroup, "worker-group", "group-failure");
            grouped.start();
            grouped.join();

            ThreadGroup regularGroup = new ThreadGroup("regular");
            Thread globally = failingThread(
                    regularGroup, "worker-default", "default-failure");
            globally.start();
            globally.join();
        } finally {
            Thread.setDefaultUncaughtExceptionHandler(previous);
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 HandlerDispatchDemo.java
java HandlerDispatchDemo
~~~

**Stdout chính xác:**

~~~text
THREAD: worker-local -> local-failure
GROUP: worker-group -> group-failure
DEFAULT: worker-default -> default-failure
~~~

Chương trình đã được thiết kế để không phải dựa vào stack trace chứa tên package hay số dòng bất định. Mỗi handler in cùng một mẫu đơn giản; từng luồng được `join()` trước khi tạo luồng tiếp theo.

### Vì sao từng dòng xuất hiện?

**Dòng 1 — THREAD:** `local` thuộc `ObservingGroup` nhưng đã có handler riêng. Khi lỗi thoát khỏi `run()`, Java gọi handler riêng, nên không gọi `ObservingGroup.uncaughtException()` và cũng không gọi default handler cho lỗi này.

**Dòng 2 — GROUP:** `grouped` không có handler riêng. Handler của nó là nhóm `ObservingGroup`. Phương thức override in dòng `GROUP` rồi trả về, không gọi `super`, nên chuỗi chuyển tiếp kết thúc ngay tại nhóm.

**Dòng 3 — DEFAULT:** `globally` thuộc `ThreadGroup` tiêu chuẩn. Nhóm này dùng logic `uncaughtException` mặc định, chuyển tới các nhóm cha và cuối cùng gọi handler mặc định toàn JVM. Vì vậy hiện dòng `DEFAULT` và không có dòng in stack trace dự phòng.

**Vì sao cần `try/finally` ở main?** Đoạn `finally` khôi phục handler mặc định trước đó để ví dụ không vô tình thay đổi hành vi của những phần code chạy sau. Vì từng luồng đều được `join()`, ba lỗi đã có cơ hội hoàn tất xử lý trước khi khôi phục.

**Vì sao ví dụ không bắt ngoại lệ ở main?** Lỗi được ném từ những luồng khác. `main` chỉ tạo, khởi động và chờ luồng kết thúc. `join()` không ném lại `IllegalStateException` của luồng worker.

## 8. Tự kiểm tra thứ tự ưu tiên

Từ ví dụ trên, có thể thử thay đổi một chi tiết tại một thời điểm:

| Thay đổi | Hành vi dự kiến |
| --- | --- |
| Xóa lời gọi `local.setUncaughtExceptionHandler(...)` | Lỗi của `worker-local` đi tới `ObservingGroup` |
| Giữ handler riêng và thay đổi nhóm | Handler riêng vẫn là cấp ưu tiên cho luồng đó |
| Trong `ObservingGroup.uncaughtException`, gọi `super.uncaughtException(thread, error)` sau khi in | Hệ thống có thể in thêm dòng default do lỗi được chuyển tiếp lên trên |
| Gọi `Thread.setDefaultUncaughtExceptionHandler(null)` và dùng nhóm chuẩn | Nếu không có tầng xử lý riêng, đường cuối cùng của nhóm chuẩn in lỗi vào `System.err` |
| Dùng `thread.setUncaughtExceptionHandler(null)` trước khi start | Luồng không còn handler riêng; nhóm là cấp dự phòng |

Lưu ý: Thay đổi default handler trong một JVM đang chạy nhiều công việc có thể ảnh hưởng các luồng không liên quan. Hãy thử các thay đổi này trong một chương trình hoặc môi trường kiểm thử riêng, không cập nhật cấu hình toàn cục của hệ thống đang phục vụ người dùng.

## 9. Handler không thay thế catch, finally hoặc phục hồi lỗi

Xét công việc có tài nguyên:

~~~java
Thread worker = new Thread(() -> {
    openResource();
    try {
        doWork();
    } finally {
        closeResource();
    }
});
~~~

Đây là **mã minh họa không độc lập**, giả định các phương thức cần thiết tồn tại và chữ ký checked exception cho phép cách gọi đó. Nếu `doWork()` ném một ngoại lệ unchecked chưa được bắt, `finally` vẫn chạy trên đường thoát thông thường, rồi ngoại lệ còn lại mới đi tới uncaught handler.

Nhưng handler:

- Không tự đóng file/socket/lock bị quên giải phóng.
- Không tự rollback trạng thái dữ liệu được cập nhật dở dang.
- Không thể tiếp tục thực thi luồng tại vị trí lỗi.
- Không thay thế các khối `catch` dành cho lỗi dự kiến mà ứng dụng có thể phục hồi.

Đối với tài nguyên `AutoCloseable`, nên ưu tiên `try-with-resources`. Nếu thao tác chính và việc đóng tài nguyên cùng ném lỗi, Java có thể giữ lỗi đóng trong `getSuppressed()` của ngoại lệ chính; handler có thể ghi nhận toàn bộ đối tượng `Throwable` để chẩn đoán. Nếu `finally` tự ném một exception khác, lỗi mới có thể thay thế lỗi đang lan truyền trước đó. Đây là lý do giải phóng tài nguyên cần được thiết kế đúng ngay bên trong công việc.

### Vì sao không bắt mọi lỗi chỉ để coi là thành công?

~~~java
Thread worker = new Thread(() -> {
    try {
        performWork();
    } catch (Exception ignored) {
        // Không báo cáo, không sửa trạng thái, tiếp tục như đã thành công.
    }
});
~~~

Đây là ví dụ **cố ý không nên áp dụng**, với `performWork()` là phương thức minh họa. Lỗi đã bị bắt nên uncaught handler sẽ không biết đến. Nếu hợp đồng công việc thực sự cho phép phục hồi, code ở đây phải xử lý và công bố kết quả chính xác; nếu không, nên cho lỗi lan truyền hoặc chuyển nó thành kết quả thất bại có cấu trúc.

## 10. ExecutorService.submit() có điểm khác quan trọng

Một hiểu nhầm phổ biến: “Đã gán `UncaughtExceptionHandler` cho thread của executor thì mọi exception trong task đều đi tới handler.”

Điều này **không đúng với đường thực thi thông thường của `ExecutorService.submit()`**. `submit()` trả về `Future`. Task được bao bọc bởi cơ chế ghi nhận kết quả; khi task ném exception, `Future` lưu trạng thái thất bại. Lời gọi `Future.get()` sau đó báo `ExecutionException` với cause chứa nguyên nhân task. Exception đã được cơ chế task bắt/ghi nhận, vì thế không thoát ra khỏi `Thread.run()` dưới dạng uncaught exception.

### Ví dụ Java 17+ độc lập với Future

Tạo tệp **FutureFailureDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class FutureFailureDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger handlerCalls = new AtomicInteger();

        ThreadFactory factory = task -> {
            Thread thread = new Thread(task, "pool-worker");
            thread.setUncaughtExceptionHandler(
                    (t, error) -> handlerCalls.incrementAndGet());
            return thread;
        };

        ExecutorService executor = Executors.newSingleThreadExecutor(factory);
        try {
            Future<?> future = executor.submit(() -> {
                throw new IllegalArgumentException("bad task");
            });

            try {
                future.get();
            } catch (ExecutionException e) {
                System.out.println("FUTURE: "
                        + e.getCause().getClass().getSimpleName()
                        + " -> " + e.getCause().getMessage());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new AssertionError("Executor không kết thúc");
            }
        }

        System.out.println("HANDLER CALLS: " + handlerCalls.get());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
~~~

**Stdout chính xác:**

~~~text
FUTURE: IllegalArgumentException -> bad task
HANDLER CALLS: 0
~~~

Giải thích:

1. `ThreadFactory` tạo thread cho executor và gán handler riêng. Handler chỉ tăng bộ đếm.
2. `submit()` trả về một `Future` cho task ném `IllegalArgumentException`.
3. `future.get()` quan sát thất bại qua `ExecutionException`; `getCause()` là exception gốc của task.
4. Vì task thất bại đã được lưu trong `Future`, handler của thread **không được gọi cho lỗi đó**; bộ đếm là 0.
5. `shutdown()` và `awaitTermination()` bảo đảm tài nguyên executor được quản lý gọn. Chương trình đã xử lý `ExecutionException` của task này để in một kết quả xác định.

### Còn execute() thì sao?

Với `ThreadPoolExecutor.execute(Runnable)`, một `RuntimeException` hoặc `Error` thoát khỏi `Runnable.run()` có thể khiến worker thread kết thúc bất thường; đường xử lý uncaught exception của thread đó có thể được kích hoạt. Tuy nhiên, cách một executor cụ thể xử lý task còn phụ thuộc vào implementation, wrapper và chính loại task đã được giao.

Vì vậy, **không thiết kế hệ thống chỉ dựa vào handler để thu thập mọi lỗi task**. Với `Future`, quan sát kết quả bằng `get()`; với các cơ chế async khác như `CompletableFuture`, dùng các API completion và xử lý exceptional completion phù hợp. Nếu cần ghi nhận thống nhất ở executor, có thể áp dụng chính sách xử lý ở cấp task hoặc tại điểm giám sát được framework cung cấp.

## 11. ThreadFactory: gắn handler cho các thread mới

Khi tự quản lý nhóm worker hoặc dùng `ExecutorService`, `ThreadFactory` giúp áp dụng nhất quán tên luồng và handler:

~~~java
java.util.concurrent.ThreadFactory factory = runnable -> {
    Thread thread = new Thread(runnable, "document-worker");
    thread.setUncaughtExceptionHandler((t, error) -> {
        System.err.println("Worker thất bại: " + t.getName());
        error.printStackTrace(System.err);
    });
    return thread;
};
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. Điểm quan trọng là factory cấu hình thread **trước khi executor hoặc thành phần khác khởi động nó**.

Nếu tạo nhiều thread, nên có chính sách đặt tên phân biệt chúng thay vì tên trùng lặp để dễ đọc log. Handler cần đủ nhẹ, đáng tin cậy và không thực hiện thao tác blocking dài. Việc một thread lỗi không đồng nghĩa toàn executor hoặc cả JVM đã ngừng hoạt động; các cơ chế thay thế worker, trạng thái task và policy shutdown phụ thuộc executor.

## 12. Những ngoại lệ nào có thể đi tới handler?

Phương thức `uncaughtException(Thread, Throwable)` nhận `Throwable`, không chỉ `Exception`. Bởi vậy handler có thể nhìn thấy `RuntimeException`, những unchecked exception khác và cả `Error` đã thoát khỏi luồng.

Không nên diễn giải rằng handler có thể **phục hồi được mọi `Error`**. Các lỗi nghiêm trọng như lỗi tài nguyên JVM có thể khiến cả thao tác ghi log cũng không còn đáng tin cậy. Handler là điểm quan sát tốt nhất có thể, không phải bộ máy tự sửa chữa mọi sự cố.

Các checked exception như `IOException` thường bị buộc bắt hoặc khai báo tại nơi gọi theo quy tắc Java. `Runnable.run()` không khai báo checked exception nên code trực tiếp trong lambda `Runnable` phải xử lý hoặc chuyển đổi chúng trước khi có thể thoát dưới dạng ngoại lệ không được bắt.

Ví dụ minh họa:

~~~java
Runnable task = () -> {
    try {
        readFromFile();
    } catch (java.io.IOException original) {
        throw new IllegalStateException("Không thể đọc dữ liệu", original);
    }
};
~~~

Đoạn này giả định có phương thức `readFromFile()` khai báo `throws IOException`. Nếu `IllegalStateException` thoát khỏi task thực thi trực tiếp trong thread, handler sẽ nhận wrapper đó. `getCause()` của wrapper vẫn giữ `IOException` gốc để chẩn đoán.

Ngoại lệ mà code ứng dụng **đã bắt và xử lý** sẽ không được xem là uncaught; handler không biết về nó nếu code không chủ động báo cáo.

## 13. Handler nên làm những gì?

Một handler tốt thường giới hạn nhiệm vụ ở việc **ghi nhận sự cố đủ chính xác** và cung cấp tín hiệu cho tầng quản lý. Có thể:

- Ghi tên/ID luồng, thời gian và tên tác vụ nếu có.
- Ghi exception object để lưu đầy đủ type, cause, stack trace và suppressed exceptions.
- Tăng một metric hoặc phát sự kiện nội bộ với giới hạn tài nguyên phù hợp.
- Thông báo một bộ quản lý worker rằng một luồng đã kết thúc bất thường.
- Đặt cơ chế báo lỗi thống nhất, ví dụ gửi tới logger của ứng dụng.

Các giới hạn quan trọng:

1. **Không coi handler là chỗ chạy lại task**: không có đủ dữ liệu chắc chắn về tính idempotent, tác dụng phụ đã xảy ra hoặc trạng thái sau lỗi.
2. **Không thực hiện xử lý phức tạp dễ thất bại**: handler có thể được gọi khi hệ thống đang ở trạng thái suy giảm.
3. **Không làm mất thông tin gốc**: khi chuyển lỗi thành sự kiện, cố gắng giữ cause để nội bộ điều tra.
4. **Không tiết lộ thông tin nhạy cảm**: stack trace có thể chứa đường dẫn, tên tài nguyên, message kỹ thuật hoặc thông tin ứng dụng; lưu/hiển thị theo mức quyền thích hợp.
5. **Tránh ghi log trùng**: nếu handler của nhóm và handler mặc định đều in cùng exception, vận hành dễ đếm một sự cố thành hai.
6. **Không dựa vào console cho xử lý nghiệp vụ**: `System.err` không phải hợp đồng giao tiếp ổn định của hệ thống phân tán.

### Nếu handler tự ném ngoại lệ?

Theo hợp đồng của `Thread.UncaughtExceptionHandler`, ngoại lệ do chính phương thức `uncaughtException` ném ra sẽ bị JVM bỏ qua. Không thể kỳ vọng một handler lỗi sẽ kích hoạt vòng báo lỗi thứ hai hay quay lại thực hiện công việc ban đầu.

Vì vậy nên viết handler ngắn, tránh dùng trạng thái chung dễ lỗi và kiểm thử chính handler với trường hợp thông tin đầu vào bất thường. Tùy yêu cầu, có thể bao quanh code báo cáo với cơ chế bảo vệ phù hợp, nhưng không nên tạo vòng gọi handler đệ quy khi bản thân hệ thống ghi log đang lỗi.

## 14. Sự khác nhau giữa xử lý lỗi trong task và xử lý ở handler

| Câu hỏi | Bắt lỗi trong task | Uncaught handler |
| --- | --- | --- |
| Có thể phục hồi rồi tiếp tục công việc? | Có, nếu logic task biết cách phục hồi | Không thể quay lại vị trí đã thoát |
| Có thể chuyển lỗi thành kết quả nghiệp vụ? | Có, theo hợp đồng task | Thường chỉ quan sát/report; cần kênh kết quả khác |
| Có thể giải phóng tài nguyên cục bộ? | Có, qua `finally` hoặc try-with-resources | Quá muộn để dựa vào handler làm cleanup thay cho task |
| Có đủ ngữ cảnh nghiệp vụ? | Thường có | Chỉ được truyền `Thread` và `Throwable`; thông tin khác phải được thiết kế thêm |
| Có nhận lỗi của `submit()` không? | Future/task wrapper lưu exception; caller xử lý qua `get()` | Thường không thấy lỗi task vì đã được wrapper bắt |

Không có một cấp duy nhất phù hợp mọi lỗi. Lỗi dự kiến và có thể phục hồi nên xử lý trong task hoặc trong hợp đồng async tương ứng. Uncaught handler là điểm dự phòng giúp quan sát những lỗi **đã thoát ra ngoài** đường xử lý thông thường.

## 15. Kiểm thử handler và thứ tự xử lý

Bộ kiểm thử nên kiểm tra hành vi **theo cơ chế**, không phụ thuộc vào thời gian chạy hay stack trace của JVM.

| Kịch bản | Kỳ vọng |
| --- | --- |
| Thread có handler riêng và nằm trong nhóm tùy biến | Chỉ handler riêng nhận ngoại lệ, nếu chính handler không chuyển tiếp |
| Thread không có handler riêng, nhóm override `uncaughtException` | Handler của nhóm được gọi |
| Thread dùng nhóm chuẩn, có default handler | Cuối chuỗi nhóm cha, default handler được gọi |
| Nhóm override nhưng không gọi `super` | Default handler không tự động nhận lỗi |
| Nhóm override có gọi `super` | Đường xử lý có thể tới nhóm cha/default |
| Task đã bắt và xử lý exception | Không kích hoạt uncaught handler cho exception đó |
| Task chạy qua `ExecutorService.submit()` | Lỗi lấy qua `Future.get()`, handler của thread không tự động nhận nó |

Trong kiểm thử, có thể dùng `AtomicReference<Throwable>` hoặc một công cụ đồng bộ để ghi nhận exception đã gửi cho handler. Khởi động luồng, gọi `join()`, rồi xác nhận loại exception và **cùng đối tượng** nếu cần.

**Không viết kiểm thử rủi ro treo vô thời hạn** khi task có thể chờ khóa hay chờ I/O. Có thể đặt thời hạn kiểm thử thích hợp và xử lý trạng thái timeout. Không nên khẳng định handler “không bao giờ được gọi” chỉ vì một lần đọc biến đếm quá sớm khi luồng chưa kết thúc.

Với handler mặc định, lưu và khôi phục handler cũ theo vòng đời kiểm thử. Nếu nhiều test chạy song song trong cùng một JVM và đồng thời chỉnh handler mặc định, các test có thể can thiệp nhau; cần cô lập hoặc phối hợp trạng thái toàn cục này.

## 16. Lỗi thường gặp

1. **Bắt ngoại lệ quanh `thread.start()` rồi mong bắt được lỗi ở `run()`:** hai lời gọi chạy trên hai luồng khác nhau.
2. **Gắn handler sau `start()`:** luồng có thể đã ném lỗi trước khi handler được cài.
3. **Tưởng handler mặc định luôn được gọi:** handler riêng hoặc `ThreadGroup` override có thể kết thúc đường báo lỗi trước đó.
4. **Tưởng nhóm chỉ là nhãn phân loại:** `ThreadGroup` cũng là `UncaughtExceptionHandler` dự phòng.
5. **Override group rồi quên quyết định có gọi `super`:** hoặc bỏ mất default logging, hoặc vô tình ghi log trùng.
6. **Cho rằng handler giúp task chạy tiếp:** luồng đã thoát khỏi đường thực thi bị lỗi.
7. **Trông đợi `join()` ném lại ngoại lệ của worker:** `join()` chỉ chờ kết thúc và có thể bị gián đoạn ở luồng đang chờ.
8. **Dùng handler để tìm mọi lỗi từ `submit()`:** exception của task có thể nằm trong `Future`.
9. **Chỉ ghi `error.getMessage()`:** mất type, cause chain và stack trace.
10. **Ghi log toàn bộ thông tin lỗi ra đầu ra công khai:** có nguy cơ lộ chi tiết hạ tầng.
11. **Làm tác vụ nặng trong handler:** dễ phát sinh lỗi mới khi hệ thống đang bất ổn.
12. **Quên khôi phục default handler sau test:** thay đổi hành vi của các test hoặc thành phần chạy sau.
13. **Coi mọi lỗi là khôi phục được:** `Error` và lỗi hệ thống nghiêm trọng có thể không cho phép phục hồi.
14. **Ghi log cùng một lỗi ở nhiều cấp:** gây nhiễu việc đếm và phân tích sự cố.

## 17. Checklist thiết kế

Trước khi vận hành một chương trình dùng nhiều luồng, hãy tự kiểm tra:

- Đã phân biệt **lỗi dự kiến trong task** với **ngoại lệ chưa được bắt thoát khỏi luồng** chưa?
- Những luồng cần xử lý riêng đã được gán handler **trước `start()`** chưa?
- ThreadGroup tùy biến có quy tắc chuyển tiếp lỗi rõ ràng không, và có tránh log trùng không?
- Handler mặc định đã được cấu hình ở điểm khởi tạo thích hợp chưa?
- Nếu code sử dụng `ExecutorService.submit()`, ai chịu trách nhiệm `Future.get()` hoặc xử lý kết quả thất bại?
- Khi lỗi phát sinh, cleanup cục bộ đã được đảm bảo bởi `finally` hoặc `try-with-resources` chưa?
- Handler có đủ ngữ cảnh quan sát mà không tiết lộ thông tin nhạy cảm không?
- Kiểm thử có xác nhận thứ tự ưu tiên, danh tính throwable và đường báo lỗi thực tế không?
- Chính sách khôi phục, thử lại hoặc chấm dứt ứng dụng có được quyết định ở tầng đủ ngữ cảnh hay không?

**Điều cần nhớ:** handler riêng ưu tiên cho từng `Thread`; nếu không có, `ThreadGroup` nhận lỗi và có thể chuyển lên nhóm cha; logic chuẩn ở nhóm gốc mới sử dụng handler mặc định, trước khi rơi về cách in lỗi dự phòng. Uncaught handler giúp **quan sát lỗi cuối đường chạy của luồng**, còn xử lý kết quả, cleanup và phục hồi phải được thiết kế ở đúng tầng có đủ ngữ cảnh.