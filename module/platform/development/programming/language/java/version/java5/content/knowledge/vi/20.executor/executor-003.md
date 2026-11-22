# ExecutorService và vòng đời bộ thực thi

## 1. Vì sao gửi tác vụ chưa đủ?

Giả sử chương trình cần tính báo cáo nền. Việc tạo và gửi tác vụ mới giải quyết nửa đầu của bài toán. Khi ứng dụng ngừng nhận báo cáo, ai ngăn yêu cầu mới, ai chờ báo cáo đang chạy và ai xử lý phần công việc chưa bắt đầu?

`ExecutorService` bổ sung quản lý vòng đời và theo dõi kết quả cho `Executor`. Ba đối tượng cần phân biệt:

- **Tác vụ:** một đơn vị công việc, thường biểu diễn bằng `Runnable` hoặc `Callable<T>`.
- **Bộ thực thi:** tiếp nhận và điều phối tác vụ; bên tạo ra nó phải xác định lúc kết thúc sử dụng.
- **`Future<T>`:** đại diện cho kết quả/trạng thái của một tác vụ, không đại diện cho toàn bộ bộ thực thi.

Một báo cáo hoàn thành không có nghĩa bộ thực thi đã kết thúc. Ngược lại, yêu cầu ngừng bộ thực thi cũng không có nghĩa báo cáo đang chạy đã dừng.

Các API nền tảng của bài có từ Java 5 và vẫn hữu ích trên Java hiện đại. Hai ví dụ chính chạy với Java 17+. Phần cuối giải thích `try-with-resources` được hỗ trợ từ Java 19; không dùng cơ chế dừng luồng đã lỗi thời.

## 2. Gửi công việc và quan sát kết quả

| Cách gửi | Công việc | Giá trị nhận ngay |
| --- | --- | --- |
| `execute(Runnable)` | Không trả kết quả nghiệp vụ | `void` |
| `submit(Runnable)` | Không trả kết quả nghiệp vụ | `Future<?>`; `get()` trả `null` nếu thành công |
| `submit(Callable<T>)` | Trả kết quả kiểu `T` | `Future<T>` |
| `submit(Runnable, T)` | Chạy `Runnable`, rồi dùng kết quả đã cung cấp | `Future<T>` |

`submit` trả về `Future` không đồng nghĩa tác vụ đã chạy xong. Nó có thể còn trong hàng đợi. Lệnh `get()` chờ kết quả khi cần và có thể ném `ExecutionException` nếu tác vụ thất bại, `CancellationException` nếu bị hủy, hoặc `InterruptedException` nếu luồng đang chờ bị ngắt.

Với `ThreadPoolExecutor`, lỗi của tác vụ gửi qua `submit` được giữ trong `Future`; bỏ quên `Future` có thể làm lỗi không được quan sát. Đừng giả định tác vụ thất bại sẽ luôn in lỗi ra màn hình. Hãy lấy kết quả, ghi nhận lỗi hoặc có cơ chế theo dõi phù hợp. [Tài liệu ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

Một tác vụ thất bại cũng không tự đóng toàn bộ bộ thực thi. Chính sách tiếp tục, hủy tác vụ khác hay dừng dịch vụ thuộc về mã điều phối.

## 3. Mô hình vòng đời

Ở mức giao diện, có thể hình dung:

```text
Đang tiếp nhận tác vụ
    |
    +-- shutdown() ----> Ngừng tiếp nhận, xử lý công việc đã nhận
    |                                  |
    |                                  +-- hoàn tất --> Đã kết thúc
    |
    +-- shutdownNow() -> Bỏ công việc đang chờ, yêu cầu dừng việc đang chạy
                                       |
                                       +-- thực sự dừng hết --> Đã kết thúc
```

Đây là mô hình khái niệm; không phải tên các trạng thái nội bộ của mọi lớp triển khai. Bộ thực thi đã ngừng tiếp nhận không có thao tác khởi động lại; muốn có vòng đời mới phải tạo đối tượng mới.

| API | Ý nghĩa cần nhớ |
| --- | --- |
| `shutdown()` | Ngừng nhận mới, cho tác vụ đã nhận tiếp tục; không chờ |
| `shutdownNow()` | Trả danh sách việc chưa chạy, cố dừng việc đang chạy; không chờ |
| `isShutdown()` | Đã bắt đầu quá trình dừng |
| `isTerminated()` | Đã dừng và không còn việc đang chạy/chờ |
| `awaitTermination(timeout, unit)` | Chờ sau yêu cầu dừng; trả `false` nếu hết thời gian |

Không gọi `awaitTermination` thay cho `shutdown`: phương thức chờ không khởi động việc dừng. Cũng không hiểu `isShutdown() == true` thành “mọi việc đã xong”. [Tài liệu ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)

Bộ thực thi tạo bằng các factory chuẩn thường từ chối tác vụ sau khi dừng bằng `RejectedExecutionException`. Với `ThreadPoolExecutor` tự cấu hình, hành vi còn phụ thuộc chính sách từ chối; ví dụ chính sách bỏ qua có thể không ném ngoại lệ. Không dựa vào `isShutdown()` rồi mới gửi để tránh lỗi: một luồng khác có thể dừng bộ thực thi ngay giữa hai thao tác. Mã gửi vẫn phải có chính sách xử lý từ chối.

## 4. Thí nghiệm: đã shutdown nhưng chưa terminated

Tệp **LifecycleDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;

public class LifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> result = pool.submit(() -> {
                release.await();
                return 42;
            });

            pool.shutdown();

            System.out.println("shutdown=" + pool.isShutdown());
            System.out.println("terminatedBeforeRelease=" + pool.isTerminated());

            try {
                pool.submit(() -> 99);
            } catch (RejectedExecutionException ex) {
                System.out.println("newTask=rejected");
            }

            release.countDown();
            System.out.println("result=" + result.get());

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
            System.out.println("terminatedAfterWait=" + pool.isTerminated());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy trên JDK 17+:

```shell
javac --release 17 LifecycleDemo.java
java LifecycleDemo
```

Stdout khi thực thi hoàn tất bình thường:

```text
shutdown=true
terminatedBeforeRelease=false
newTask=rejected
result=42
terminatedAfterWait=true
```

`CountDownLatch` giữ tác vụ chưa thể hoàn thành trước dòng kiểm tra đầu tiên. Vì vậy, kết quả không phụ thuộc phỏng đoán rằng “ngủ một chút chắc luồng đã chạy”. Tác vụ được nhận trước `shutdown()` vẫn có thể trả `42`.

Lệnh `get()` xác nhận tác vụ đó thành công. Lệnh `awaitTermination` tiếp theo xác nhận cả bộ thực thi kết thúc. Hai mốc này có ý nghĩa khác nhau.

Khối `finally` mở chốt nếu luồng chính gặp lỗi, đồng thời yêu cầu dọn dẹp bộ thực thi. Mốc chờ 5 giây là ngưỡng của thí nghiệm; trong ứng dụng phải chọn theo thời gian xử lý và yêu cầu vận hành.

## 5. ShutdownNow là yêu cầu hợp tác

Chữ “Now” không có nghĩa Java cưỡng ép mọi lệnh đang chạy phải dừng ngay. Với bộ luồng thông thường, tác vụ đang chạy nhận tín hiệu ngắt (`interrupt`). Mã tác vụ cần kiểm tra tín hiệu hoặc thoát khi API chờ ném `InterruptedException`.

Ví dụ sau chủ động tạo đúng hai tác vụ: một tác vụ đang chờ chốt, một tác vụ chắc chắn nằm trong hàng đợi. Nó dùng bộ thực thi một luồng nên tác vụ thứ hai không thể chạy khi tác vụ thứ nhất còn bị giữ.

Tệp **ForceStopDemo.java**:

```java
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ForceStopDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);

        try {
            pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            Future<Integer> queued = pool.submit(() -> 7);
            List<Runnable> notStarted = pool.shutdownNow();

            // Ma dieu phoi so huu Future cua cong viec bi bo khoi hang doi.
            queued.cancel(false);

            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }

            System.out.println("notStarted=" + notStarted.size());
            System.out.println("queuedCancelled=" + queued.isCancelled());
            System.out.println("runningObservedInterrupt=" + interrupted.get());
            System.out.println("terminated=" + pool.isTerminated());
        } finally {
            neverReleased.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac --release 17 ForceStopDemo.java
java ForceStopDemo
```

Stdout khi thực thi hoàn tất bình thường:

```text
notStarted=1
queuedCancelled=true
runningObservedInterrupt=true
terminated=true
```

Bốn điểm cần đọc đúng:

1. Tác vụ đang chạy thoát vì xử lý `InterruptedException`, không phải bị xóa khỏi CPU một cách cưỡng chế.
2. Danh sách trả về chứa công việc chưa bắt đầu. Khi dùng `submit`, phần tử có thể là đối tượng bao tác vụ, không phải đối tượng nghiệp vụ ban đầu.
3. `shutdownNow()` không bảo đảm tự chuyển mọi `Future` của việc bị lấy khỏi hàng đợi sang trạng thái hủy. Vì còn giữ `queued`, mã điều phối chủ động gọi `cancel(false)`; nếu bỏ bước này rồi gọi `get()` vô hạn, có thể chờ một công việc sẽ không bao giờ chạy.
4. Không tự gửi lại danh sách công việc bị bỏ: cần xác định có cho phép chạy lại hay không và tác dụng phụ có thể lặp hay không.

Đối với vòng lặp tính toán dài, có thể kiểm tra `Thread.currentThread().isInterrupted()` tại ranh giới từng đơn vị công việc. Với API chặn không đáp ứng ngắt, cần timeout hoặc cơ chế đóng tài nguyên riêng. Khôi phục cờ ngắt chỉ giữ tín hiệu; tác vụ vẫn phải thoát hoặc truyền lỗi đúng cách, không tiếp tục lặp vô hạn. [Tài liệu Thread.interrupt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html#interrupt())

## 6. Dừng theo hai giai đoạn có ngân sách chờ

Một ứng dụng thường cần cho việc đang xử lý cơ hội hoàn thành, rồi mới yêu cầu hủy nếu vượt thời gian. Đoạn sau là **phương thức tiện ích**, đặt trong lớp của ứng dụng; không phải chương trình có `main` độc lập:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

static boolean stopOwnedExecutor(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown();

    try {
        if (executor.awaitTermination(10, TimeUnit.SECONDS)) {
            return true;
        }

        executor.shutdownNow();
        return executor.awaitTermination(5, TimeUnit.SECONDS);
    } catch (InterruptedException ex) {
        executor.shutdownNow();
        throw ex;
    }
}
```

Đoạn này cho tối đa 10 giây chờ hoàn tất thông thường, rồi thêm tối đa 5 giây sau yêu cầu ngắt. Các mốc chờ không phải cam kết tác vụ đã dừng:

- Trả `true`: đã quan sát bộ thực thi kết thúc.
- Trả `false`: hết lượt chờ thứ hai; phải báo tình trạng còn việc chạy và áp dụng chính sách vận hành.
- Ném `InterruptedException`: luồng điều phối bị ngắt; đã yêu cầu dừng mạnh hơn nhưng không xác nhận kết thúc.

Phương thức truyền `InterruptedException` cho bên gọi nên không nuốt tín hiệu. Nếu tầng trên bắt lỗi và không truyền tiếp, tầng đó thường cần khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi rời luồng xử lý phù hợp.

Đây là ngân sách cho **thời gian chờ**, không phải giới hạn cứng 15 giây cho mọi lớp triển khai và mọi tài nguyên bên ngoài. Một truy vấn mạng thiếu timeout hay tác vụ bỏ qua ngắt vẫn có thể sống lâu hơn. Nếu ứng dụng còn các `Future` của việc chưa chạy, nó cần chính sách hoàn tất/hủy chúng như thí nghiệm trước.

Không gọi phương thức chờ kết thúc này từ chính tác vụ đang chạy trên bộ thực thi đó. Tác vụ có thể chờ cả sự kết thúc của chính mình, gây kẹt hoặc chờ hết ngân sách vô ích.

## 7. Vòng đời của Future khác vòng đời bộ thực thi

| Thao tác | Phạm vi |
| --- | --- |
| `future.get(timeout, unit)` | Giới hạn thời gian bên gọi chờ kết quả |
| `future.cancel(true)` | Cố hủy một tác vụ, có thể yêu cầu ngắt nếu đang chạy |
| `executor.shutdown()` | Dừng tiếp nhận cho cả bộ thực thi |
| `executor.awaitTermination(...)` | Chờ toàn bộ bộ thực thi kết thúc |

`TimeoutException` từ `get(timeout, unit)` không tự hủy tác vụ. Nếu nghiệp vụ yêu cầu hủy, cần gọi `cancel` và xử lý tác dụng phụ đã xảy ra.

`Future.isDone()` cũng đúng khi kết thúc bằng lỗi hoặc bị hủy; nó không đồng nghĩa thành công. Sau yêu cầu hủy, không coi trạng thái `Future` là bằng chứng rằng mã tác vụ không còn chạy: tác vụ có thể chưa đáp ứng ngắt. [Tài liệu Future](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Thí dụ tải báo cáo bị hủy sau khi đã ghi một phần tệp cần dọn tệp tạm. Hủy `Future` không tự hoàn tác phần dữ liệu đã ghi.

Về khả năng nhìn thấy dữ liệu giữa các luồng, việc lấy kết quả qua `Future.get()` có quan hệ đồng bộ được API quy định. Tuy nhiên, hai tác vụ cùng sửa một `ArrayList` vẫn cần thiết kế an toàn riêng. Dùng `ExecutorService` không tự làm dữ liệu chia sẻ trở nên an toàn.

## 8. Quyền sở hữu quyết định ai được đóng

Một quy tắc thực dụng: **thành phần quản lý vòng đời tài nguyên phải chịu trách nhiệm đóng tài nguyên đó**.

- Chương trình dòng lệnh tự tạo bộ thực thi cho một đợt công việc: đóng sau khi đợt công việc kết thúc.
- Dịch vụ nhận bộ thực thi dùng chung từ bên ngoài: không tự đóng sau mỗi yêu cầu; bên cung cấp quản lý vòng đời.
- Ứng dụng web quản lý bộ thực thi ở cấp ứng dụng: dừng tiếp nhận công việc theo vòng đời ứng dụng, rồi chờ/hủy theo chính sách.
- Một tác vụ con được truyền `Executor` chỉ để gửi việc: không ép kiểu nhằm chiếm quyền đóng bộ thực thi.

Tạo `newFixedThreadPool` trong mỗi lần gọi rồi quên đóng có thể làm tích tụ luồng. Với factory mặc định, luồng nền tảng là non-daemon và có thể khiến tiến trình chưa thoát dù `main` đã xong. Đổi sang daemon không thay thế chính sách hoàn tất công việc.

`newFixedThreadPool(n)` giới hạn số luồng hoạt động nhưng dùng hàng đợi không giới hạn. Chỉ quản lý vòng đời chưa giải quyết quá tải: nếu tốc độ nhận liên tục cao hơn xử lý, hàng đợi có thể phình lớn. Hệ thống thực tế cần giới hạn tải, hàng đợi và chính sách từ chối phù hợp. [Tài liệu Executors](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html)

## 9. Java 19+: đóng bằng try-with-resources

Từ Java 19, `ExecutorService` triển khai `AutoCloseable`. Với JDK 21+, có thể viết tệp **ScopedExecutorDemo.java**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ScopedExecutorDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService pool = Executors.newFixedThreadPool(2)) {
            Future<Integer> answer = pool.submit(() -> 6 * 7);
            System.out.println("answer=" + answer.get());
        }
        System.out.println("scope=closed");
    }
}
```

Chạy trên JDK 21+:

```shell
javac --release 21 ScopedExecutorDemo.java
java ScopedExecutorDemo
```

Stdout:

```text
answer=42
scope=closed
```

`close()` thực hiện dừng có trật tự và chờ kết thúc, nên dòng `scope=closed` chỉ xuất hiện sau khi bộ thực thi kết thúc. Nó không có tham số timeout; tác vụ không kết thúc có thể giữ khối đóng rất lâu.

Nếu luồng đang `close()` bị ngắt, phương thức yêu cầu dừng các tác vụ như `shutdownNow()`, tiếp tục chờ và khôi phục cờ ngắt trước khi trả về. Khi cần thời hạn riêng cho giai đoạn dừng, hãy thiết kế điều phối tường minh. Cú pháp trên không biên dịch khi nhắm `--release 17`. [Tài liệu ExecutorService.close](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#close())

Không đặt bộ thực thi dùng chung do thành phần khác sở hữu vào khối `try-with-resources` của một yêu cầu đơn lẻ.

## 10. Tự kiểm tra bằng một tình huống

Ứng dụng nhận 100 công việc, sau đó người vận hành yêu cầu dừng. Có 4 việc đang chạy, các việc khác còn chờ.

Hãy tự xác định:

1. Nếu phải xử lý mọi công việc đã nhận, gọi API nào trước?
2. Nếu chỉ chờ thêm 10 giây, hết hạn thì yêu cầu dừng bằng cách nào?
3. Cần kiểm tra điều gì để kết luận toàn bộ bộ thực thi đã kết thúc?
4. Công việc đã bị lấy khỏi hàng đợi được đánh dấu thất bại, hủy hay đưa sang nơi xử lý lại?
5. Tác vụ ghi dữ liệu đã làm được một nửa có thể chạy lại an toàn không?

Hướng trả lời: bắt đầu bằng `shutdown()`, chờ bằng `awaitTermination`, khi vượt ngân sách cân nhắc `shutdownNow()`, rồi tiếp tục xác nhận kết thúc. Phần việc chưa chạy và tác dụng phụ phải có chính sách riêng. Không báo “dừng thành công” chỉ vì một lệnh yêu cầu dừng đã trả về.
