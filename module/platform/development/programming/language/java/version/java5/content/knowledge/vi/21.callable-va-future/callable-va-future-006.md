# TimeoutException: hết hạn chờ khác với hủy tác vụ

## 1. Một tác vụ có thể tiếp tục sau khi người gọi đã thôi chờ

Giả sử ứng dụng giao công việc xử lý một đơn hàng rồi đợi tối đa một giây. Khi hết một giây mà chưa lấy được kết quả, có ba câu hỏi riêng:

1. **Nơi gọi còn chờ không?** Lần chờ có thể đã kết thúc vì quá hạn.
2. **Future còn cho phép nhận kết quả bình thường không?** Nó có thể vẫn đang chạy, đã thành công, thất bại hoặc bị hủy.
3. **Mã xử lý đơn hàng đã dừng chưa?** Nó có thể vẫn đang chạy hoặc đang phản hồi yêu cầu hủy.

`TimeoutException` từ `Future.get(timeout, unit)` trả lời câu hỏi thứ nhất. `Future.cancel(...)` liên quan đến câu hỏi thứ hai và yêu cầu dừng công việc khi có thể. Muốn biết việc xử lý thực sự đã ngừng, cần xét cơ chế hợp tác và tín hiệu kết thúc phù hợp của tác vụ.

Không gộp cả ba thành một kết luận “quá giờ nên tác vụ đã bị hủy”. Phân biệt này giúp tránh để công việc chạy ngoài ý muốn, xử lý trùng hoặc đóng tài nguyên khi công việc vẫn dùng chúng.

Các API trong bài còn áp dụng hiện nay; ví dụ chạy bằng Java 17 trở lên.

## 2. TimeoutException biểu diễn điều gì?

`java.util.concurrent.TimeoutException` là ngoại lệ được kiểm tra dùng để báo một thao tác chờ có thời hạn đã hết thời gian. Trong phạm vi Future, nó được khai báo bởi:

```java
V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
```

Hai đối số cho biết **khoảng thời gian tối đa dành cho lần chờ hiện tại**. Khi `get(1, TimeUnit.SECONDS)` ném TimeoutException vì chưa có kết quả, phương thức get kết thúc ở luồng gọi; hợp đồng đó không tự phát lệnh cancel đến Future. [TimeoutException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/TimeoutException.html).

Ví dụ thời gian:

```text
Tác vụ:      bắt đầu ─────────── tiếp tục chạy ─────────── hoàn thành
Nơi gọi:         get(1 giây) ─ timeout → xử lý nhánh quá hạn
```

Nơi gọi có thể quay lại lấy kết quả ở lần sau nếu còn giữ Future và không có việc hủy hoặc trạng thái thất bại ngăn cản. Một lần timeout không làm Future trở thành vô dụng.

Nếu tác vụ hoàn thành sát thời hạn, sau khi bắt timeout, lần đọc `isDone()` tiếp theo có thể đã là `true`. Đó không phải mâu thuẫn: thời gian trôi giữa hai lần quan sát. Không dùng timeout để suy ra Future chắc chắn giữ nguyên trạng thái chưa xong ở mọi câu lệnh sau đó.

## 3. Bảng phân biệt chờ quá hạn, hủy và dừng thực thi

| Sự kiện | Ảnh hưởng trực tiếp | Điều chưa được bảo đảm |
|---|---|---|
| `get(timeout, unit)` ném TimeoutException | Lần chờ hiện tại kết thúc vì chưa lấy được kết quả kịp hạn | Tác vụ chưa chắc đã dừng hoặc bị hủy |
| Future chấp nhận yêu cầu `cancel(false)` | Future bị hủy theo triển khai; không yêu cầu ngắt công việc đang chạy bằng cờ này | Đoạn mã đã bắt đầu có thể vẫn tiếp tục |
| Future chấp nhận yêu cầu `cancel(true)` | Yêu cầu hủy và có thể ngắt luồng thực thi khi được triển khai hỗ trợ | Không cưỡng chế mọi mã dừng ngay |
| Tác vụ đã thoát phần xử lý và dọn dẹp | Công việc cụ thể đã đi đến điểm kết thúc được thiết kế | Tác dụng phụ đã xảy ra không tự bị hoàn tác |
| Executor đã terminated | Executor không còn công việc đang thực thi/đợi thực thi | Không chứng minh mọi công việc đã thành công |

Với `FutureTask` thông thường được dùng bởi các executor phổ biến, Future có thể chuyển sang cancelled trước khi thân tác vụ phản hồi interrupt và thoát. `isDone()` khi đó cũng có thể là `true`, vì “done” ở Future bao gồm cả hủy. [FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

## 4. cancel(true) và cancel(false) cần được hiểu đúng

Tham số của `cancel` là `mayInterruptIfRunning`, nghĩa là có cho phép yêu cầu ngắt nếu công việc đã chạy hay không.

- Nếu tác vụ chưa bắt đầu và hủy thành công, công việc đó không nên được chạy.
- `cancel(false)` không yêu cầu ngắt phần công việc đang chạy. Với FutureTask, một Future có thể đã cancelled trong khi mã tác vụ vẫn tiếp tục hoàn tất; kết quả trả về sau đó không còn được cung cấp như một kết quả thành công của Future đã hủy.
- `cancel(true)` cho phép cố ngắt luồng thực thi khi triển khai biết và hỗ trợ luồng đó. Đây là tín hiệu hợp tác.
- Yêu cầu hủy có thể không được chấp nhận, chẳng hạn công việc đã hoàn thành trước khi nơi gọi hủy. Cần quan sát kết quả và trạng thái phù hợp với hợp đồng triển khai, không chỉ in “đã hủy” ngay sau lời gọi.

Khi tác vụ đang chờ ở API hỗ trợ ngắt, nó có thể nhận `InterruptedException`. Khi tác vụ tính toán trong vòng lặp, nó cần chủ động kiểm tra ngắt ở các ranh giới phù hợp. Với một API I/O cụ thể, cần biết cơ chế hủy/đóng/thời hạn riêng của API đó; không giả định interrupt dừng mọi thao tác mạng.

`Future` là một giao diện; không nên áp đặt mọi chi tiết của FutureTask lên mọi loại Future tùy biến. Trong thí nghiệm dưới đây, executor chuẩn dùng FutureTask nên cơ chế hủy và quan sát được cố định rõ. [Hợp đồng Future.cancel](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html#cancel(boolean)).

## 5. Thí nghiệm đầy đủ với hai chính sách sau timeout

Chương trình có hai công việc:

- **A:** hết hạn chờ nhưng để tiếp tục, sau đó nhận kết quả thành công.
- **B:** hết hạn chờ rồi chủ động hủy. Tác vụ phản hồi ngắt và đi qua phần dọn dẹp. Một tác dụng phụ xảy ra trước lúc hủy vẫn còn.

Tác dụng phụ trong bài chỉ là bộ đếm trong bộ nhớ để thí nghiệm đơn giản, không phải mô phỏng đầy đủ cơ sở dữ liệu hoặc giao dịch. Latch giữ công việc ở đúng điểm kiểm chứng; chương trình không dựa vào việc chọn một số lần ngủ đủ lâu.

Lưu thành `TimeoutVsCancelDemo.java`:

```java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class TimeoutVsCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch firstRelease = new CountDownLatch(1);
        CountDownLatch secondStarted = new CountDownLatch(1);
        CountDownLatch secondRelease = new CountDownLatch(1);
        CountDownLatch secondCleanup = new CountDownLatch(1);
        AtomicInteger sideEffects = new AtomicInteger();

        try {
            Future<String> first = pool.submit(() -> {
                firstStarted.countDown();
                firstRelease.await();
                return "A completed";
            });
            requireSignal(firstStarted, "A did not start");
            expectTimeout("A", first);
            System.out.println("A cancelled: " + first.isCancelled());

            firstRelease.countDown();
            System.out.println("A result: "
                    + first.get(10, TimeUnit.SECONDS));

            Future<String> second = pool.submit(() -> {
                sideEffects.incrementAndGet();
                secondStarted.countDown();
                try {
                    secondRelease.await();
                    return "B completed";
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return "B interrupted";
                } finally {
                    secondCleanup.countDown();
                }
            });
            requireSignal(secondStarted, "B did not start");
            expectTimeout("B", second);

            System.out.println("B cancel accepted: " + second.cancel(true));
            System.out.println("B cancelled: " + second.isCancelled());
            try {
                second.get();
                throw new AssertionError("Expected CancellationException");
            } catch (CancellationException ex) {
                System.out.println("B get: cancelled");
            }

            requireSignal(secondCleanup, "B did not reach cleanup");
            System.out.println("B cleanup reached: true");
            System.out.println("side effects after cancel: "
                    + sideEffects.get());
        } finally {
            firstRelease.countDown();
            secondRelease.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        }
    }

    private static void expectTimeout(String name, Future<?> future)
            throws InterruptedException, ExecutionException {
        try {
            future.get(50, TimeUnit.MILLISECONDS);
            throw new AssertionError("Expected TimeoutException for " + name);
        } catch (TimeoutException ex) {
            System.out.println(name + ": wait timed out");
        }
    }

    private static void requireSignal(CountDownLatch latch, String message)
            throws InterruptedException {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new AssertionError(message);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 TimeoutVsCancelDemo.java
java TimeoutVsCancelDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
A: wait timed out
A cancelled: false
A result: A completed
B: wait timed out
B cancel accepted: true
B cancelled: true
B get: cancelled
B cleanup reached: true
side effects after cancel: 1
```

### Đọc bằng chứng theo đúng ranh giới

A không bị hủy bởi timeout. Sau khi được mở latch, nó vẫn trả kết quả bình thường.

B chỉ bị hủy vì luồng `main` gọi `cancel(true)`. Tại thời điểm đó B còn bị giữ ở latch nên chưa thể thành công trước yêu cầu hủy. `get()` báo `CancellationException`, kể cả thân Callable có bắt ngắt và `return "B interrupted"`: kết quả thân tác vụ không ghi đè trạng thái hủy đã được FutureTask chấp nhận. [CancellationException](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CancellationException.html).

`secondCleanup` là tín hiệu riêng để biết B đã đi tới phần `finally`; chương trình không dùng `isCancelled()` làm bằng chứng thay cho việc dọn dẹp. Latch đó đánh dấu ranh giới trong tác vụ; `awaitTermination` ở cuối còn chờ executor hoàn tất vòng đời.

Giá trị tác dụng phụ vẫn là 1. Hủy Future không chạy một cơ chế “quay ngược” lệnh tăng bộ đếm. Điều tương tự phải được phân tích với thao tác ghi tệp, gọi dịch vụ hay cập nhật dữ liệu thực tế.

## 6. Vì sao hủy không có nghĩa là hoàn tác?

Một công việc có thể gồm nhiều giai đoạn:

```text
kiểm tra đầu vào → ghi dữ liệu → gửi thông báo → trả kết quả
```

Nếu nơi gọi timeout sau lúc ghi dữ liệu nhưng trước khi nhận kết quả, dữ liệu có thể đã tồn tại. Nếu hủy được nhận lúc tác vụ đang gửi thông báo, bản ghi trước đó không tự biến mất.

Ứng dụng phải thiết kế ý nghĩa nghiệp vụ của việc bỏ dở:

- Dùng giao dịch khi phù hợp để bảo vệ một nhóm thay đổi trong cùng hệ thống.
- Dùng nhận dạng yêu cầu và xử lý lặp an toàn khi có khả năng thử lại.
- Ghi nhận trạng thái công việc để nơi gọi tra cứu khi chưa biết kết quả cuối.
- Nếu cần bù trừ, thiết kế thao tác bù trừ theo nghiệp vụ thay vì coi `cancel` là hoàn tác tự động.

Các cơ chế này xử lý trạng thái nghiệp vụ. Future chỉ quản lý hợp đồng thực thi/kết quả; nó không thay cho giao dịch hoặc giao thức của dịch vụ phía sau.

## 7. Đừng nhầm các ngoại lệ có cùng vẻ ngoài là “quá thời gian”

| Quan sát tại nơi gọi | Ý nghĩa cần kiểm tra |
|---|---|
| `get(timeout, unit)` ném trực tiếp TimeoutException | Nơi gọi hết ngân sách chờ của lần get |
| `get()` ném ExecutionException, nguyên nhân là TimeoutException | Chính mã tác vụ có thể đã ném TimeoutException; Future báo tác vụ thất bại |
| `get()` ném CancellationException | Future đã bị hủy, không có kết quả bình thường để lấy |
| `get()` ném InterruptedException | Luồng đang chờ bị ngắt; không tự khẳng định luồng chạy tác vụ cũng bị ngắt |

Một thư viện mạng cũng có thể báo một kiểu lỗi hết hạn riêng. Không bắt một nhóm ngoại lệ rộng rồi mặc định thực hiện cùng một hành động hủy/thử lại cho tất cả. Cần biết lỗi phát sinh ở ranh giới nào và công việc có thể đã tạo tác dụng phụ chưa.

Khi bắt `InterruptedException`, truyền nó lên nếu hợp đồng phương thức cho phép; nếu xử lý tại chỗ rồi kết thúc, thường khôi phục cờ ngắt. Không nuốt tín hiệu và tiếp tục chờ vô hạn. Trong chương trình chính, `main` khai báo `throws Exception` để các lỗi ngoài những đường đang thí nghiệm được truyền ra rõ ràng.

## 8. Chọn chính sách sau timeout theo người sở hữu công việc

Không phải nơi nào hết hạn chờ cũng có quyền hủy công việc dùng chung. Ví dụ hai yêu cầu cùng theo dõi một tác vụ tạo báo cáo; một người dùng thôi chờ không nhất thiết có nghĩa phải hủy tác vụ còn phục vụ người khác.

Trước khi hủy, xác định:

1. Công việc thuộc riêng yêu cầu này hay có nhiều bên dùng kết quả?
2. Khi nơi gọi rời đi, công việc có còn giá trị không?
3. Tác vụ hỗ trợ hủy ở đâu, và ai chịu trách nhiệm dọn tài nguyên?
4. Kết quả cuối hoặc lỗi về sau được ai thu nhận?

Nếu để tiếp tục, phải có chủ sở hữu thu nhận kết quả, ghi nhận thất bại và giải phóng tài nguyên. Nếu hủy, quan sát yêu cầu hủy và phản hồi của tác vụ theo nhu cầu; không báo “đã dừng hoàn toàn” chỉ vì đã gọi một phương thức.

Không gọi `shutdownNow()` trên executor dùng chung chỉ để xử lý timeout của một Future. Việc đó tác động đến các công việc khác. Dừng executor là quyết định vòng đời của chủ sở hữu executor, còn hủy Future hướng đến một lần thực thi cụ thể.

## 9. Thời hạn chờ và thời hạn công việc cần được phối hợp

Nếu yêu cầu có ngân sách tổng ba giây, việc liên tục gọi `get(3, SECONDS)` tạo ra nhiều khoảng chờ, không giữ một hạn chót chung. Cần tính phần thời gian còn lại từ một mốc bắt đầu phù hợp, thường bằng đồng hồ đơn điệu trong cùng tiến trình.

Nếu công việc bên trong gọi một dịch vụ có thời hạn đọc 30 giây, nhưng nơi gọi chỉ chờ một giây rồi rời đi, có thể còn nhiều công việc tiếp tục giữ luồng/kết nối. Phối hợp thời hạn ở các tầng và truyền yêu cầu hủy khi hợp đồng cho phép; không chỉ thêm timeout ở nơi lấy Future rồi cho rằng đã giới hạn mọi tài nguyên.

Tương tự, giới hạn chờ không thay cho giới hạn lượng việc đồng thời hoặc dung lượng hàng đợi. Khi mọi yêu cầu liên tục timeout nhưng công việc cũ vẫn chạy, hệ thống có thể tiếp tục tích tải. Theo dõi riêng số lần hết hạn chờ, số Future bị hủy và số tác vụ đã ngừng để hiểu cơ chế nào đang hoạt động.

## 10. Lỗi thường gặp và tự kiểm tra

| Ngộ nhận | Cách hiểu cần giữ |
|---|---|
| TimeoutException tự đặt isCancelled thành true | Timeout của get không tự hủy Future |
| cancel(true) giết luồng ngay | Nó yêu cầu hủy/ngắt theo triển khai và sự hợp tác |
| cancel(false) chỉ dùng được trước khi chạy | Với FutureTask, có thể chấp nhận hủy lúc đang chạy mà không ngắt thân tác vụ |
| isDone nghĩa mọi mã đã dừng | Future cancelled cũng done; mã có thể còn dọn dẹp |
| Hủy thành công nghĩa thay đổi đã được hoàn tác | Tác dụng phụ phải được quản lý riêng |
| Timeout thì thử lại luôn an toàn | Cần xét trạng thái chưa xác định và xử lý lặp |
| Bất kỳ người chờ nào cũng nên hủy công việc dùng chung | Quyền hủy phụ thuộc chủ sở hữu và hợp đồng sử dụng |

Tự kiểm tra:

1. Vì sao công việc A vẫn trả kết quả sau timeout? **Chỉ lần chờ đã hết hạn; Future không bị hủy.**
2. Vì sao B không trả chuỗi `B interrupted` qua get? **FutureTask đã chấp nhận trạng thái hủy, nên get báo CancellationException.**
3. Vì sao cần một tín hiệu riêng cho phần dọn dẹp? **Trạng thái Future không tự xác nhận mã tác vụ đã đi qua điểm đó.**
4. Vì sao bộ đếm không trở về 0 sau hủy? **Hủy không hoàn tác các lệnh đã thực hiện.**

Thực hành: đổi `second.cancel(true)` thành `second.cancel(false)`. Dự đoán Future có thể cancelled nhưng B vẫn chờ latch và chưa tới finally. Sửa chương trình để chủ động mở `secondRelease` trước khi chờ `secondCleanup`, rồi quan sát rằng mã tác vụ được cho phép tiếp tục dù Future không còn trả kết quả bình thường. Giữ giới hạn chờ và phần dọn executor để thí nghiệm không mắc kẹt.
