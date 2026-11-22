# Phân biệt hết thời hạn với dừng công việc nền trong Java

## 1. Hai khái niệm khác nhau

Trong xử lý bất đồng bộ, hết thời hạn (timeout) và dừng công việc nền (cancellation) thường xuất hiện cùng nhau nhưng không phải một hành động.

- **Timeout** giới hạn thời gian chờ một kết quả. Khi hết thời gian, bên gọi có thể nhận TimeoutException hoặc một giá trị dự phòng.
- **Cancellation** gửi yêu cầu hủy công việc đang chờ hoặc đang chạy. Công việc chỉ thực sự dừng nếu cơ chế thực thi hỗ trợ việc hủy và tác vụ phản hồi yêu cầu đó.

Ví dụ, một yêu cầu HTTP có thể hết thời hạn sau hai giây. Điều đó chỉ cho biết ứng dụng không muốn chờ lâu hơn. Tác vụ đang gửi yêu cầu, đọc dữ liệu hoặc tính toán ở nền có thể vẫn tiếp tục nếu không có cơ chế hủy tương ứng.

Cần phân biệt ba trạng thái:

1. Người gọi ngừng chờ kết quả.
2. Future được đánh dấu hoàn tất do timeout hoặc cancellation.
3. Công việc thực tế trong thread hoặc tài nguyên bên ngoài đã dừng.

Ba trạng thái này có thể xảy ra ở những thời điểm khác nhau. Một Future đã hoàn tất không chứng minh rằng mọi công việc nền liên quan đã kết thúc.

## 2. Timeout khi gọi get(timeout, unit)

Future.get(timeout, unit) chờ tối đa khoảng thời gian được chỉ định để lấy kết quả:

~~~java
try {
    String value = future.get(2, TimeUnit.SECONDS);
    System.out.println(value);
} catch (TimeoutException e) {
    System.out.println("The wait timed out");
}
~~~

Nếu hết thời hạn trước khi Future hoàn tất, get(timeout, unit) ném TimeoutException cho luồng gọi. Bản thân thao tác chờ kết thúc, nhưng Future vẫn có thể tiếp tục chạy và hoàn tất sau đó.

Điều này hữu ích khi chỉ muốn giới hạn thời gian chờ của một luồng cụ thể. Nếu có nhiều người gọi cùng chờ một Future, mỗi người có thể chọn thời hạn chờ riêng.

Không nên hiểu TimeoutException từ get(timeout, unit) là lệnh hủy công việc. Nếu cần dừng tác vụ, phải gửi yêu cầu cancellation riêng bằng Future.cancel hoặc một tín hiệu hủy do ứng dụng quản lý.

Với CompletableFuture, get(timeout, unit) cũng chỉ giới hạn lần chờ của người gọi. Nó không tự hoàn tất CompletableFuture bằng TimeoutException và không dừng computation đang chạy.

## 3. orTimeout: hoàn tất CompletableFuture bằng TimeoutException

CompletableFuture.orTimeout(timeout, unit) được bổ sung từ Java 9. Nếu Future chưa hoàn tất khi hết thời gian, nó được hoàn tất ngoại lệ bằng TimeoutException:

~~~java
CompletableFuture<String> result = CompletableFuture.supplyAsync(
    () -> callRemoteService()
);

result.orTimeout(2, TimeUnit.SECONDS);
~~~

Một điểm quan trọng: orTimeout trả về chính CompletableFuture đó và thay đổi trạng thái hoàn tất của nó. Khi timeout xảy ra, các consumer chờ Future sẽ nhận lỗi timeout.

~~~java
result.orTimeout(2, TimeUnit.SECONDS)
    .whenComplete((value, error) -> {
        if (error instanceof TimeoutException) {
            System.out.println("Request timed out");
        }
    });
~~~

orTimeout quản lý thời hạn hoàn tất của CompletableFuture. Nó không tự biết cách dừng thread, đóng socket, hủy truy vấn cơ sở dữ liệu hoặc ngắt một tác vụ đang chạy bên ngoài Future.

Nếu công việc được khởi chạy bằng supplyAsync, phần supplier có thể tiếp tục thực thi sau khi CompletableFuture đã timeout. Kết quả mà supplier cố gắng complete sau đó không thay thế được trạng thái timeout đã được ghi nhận.

## 4. completeOnTimeout: trả về giá trị dự phòng

completeOnTimeout(value, timeout, unit) cũng có từ Java 9. Nếu CompletableFuture chưa hoàn tất đúng hạn, nó được hoàn tất bình thường bằng giá trị dự phòng:

~~~java
CompletableFuture<String> result = CompletableFuture.supplyAsync(
    () -> loadDisplayName()
);

result.completeOnTimeout("Guest", 2, TimeUnit.SECONDS);
~~~

Khác biệt chính:

| API | Trạng thái Future khi hết hạn |
|---|---|
| get(timeout, unit) | Chỉ lần gọi get ném TimeoutException; Future không bị thay đổi |
| orTimeout(timeout, unit) | Future hoàn tất ngoại lệ bằng TimeoutException |
| completeOnTimeout(value, timeout, unit) | Future hoàn tất bình thường bằng giá trị dự phòng |

completeOnTimeout phù hợp khi ứng dụng có thể tiếp tục với một giá trị mặc định, chẳng hạn tên hiển thị, dữ liệu cache hoặc nội dung dự phòng.

Tuy nhiên, giá trị dự phòng không có nghĩa tác vụ nền đã bị hủy. Nếu supplier vẫn đang truy vấn hoặc tính toán, nó có thể tiếp tục tiêu thụ tài nguyên. Cần cơ chế hủy riêng nếu việc tiếp tục chạy không còn hữu ích.

## 5. cancel của CompletableFuture không đồng nghĩa interrupt thread

CompletableFuture.cancel(boolean mayInterruptIfRunning) đánh dấu CompletableFuture là bị hủy bằng CancellationException. Theo thiết kế của CompletableFuture, tham số mayInterruptIfRunning không được dùng để điều khiển việc thực thi và không có tác dụng ngắt thread đang chạy supplier.

~~~java
CompletableFuture<String> work = CompletableFuture.supplyAsync(
    () -> longRunningOperation()
);

boolean cancelled = work.cancel(true);
~~~

Lệnh trên làm Future chuyển sang trạng thái cancellation nếu việc hủy thành công. Nó không bảo đảm thread thực hiện longRunningOperation bị interrupt hoặc dừng ngay.

Đây là khác biệt quan trọng so với một số Future do ExecutorService.submit trả về. Không nên suy luận từ tên tham số true rằng mọi CompletableFuture đều sẽ ngắt thread nền.

Cancellation của CompletableFuture chủ yếu là thay đổi trạng thái hoàn tất và thông báo cho các stage phụ thuộc. Nếu cần điều khiển vòng đời công việc thực tế, hãy giữ một handle thực thi riêng, ví dụ Future<?> do ExecutorService.submit trả về, hoặc dùng token hủy hợp tác.

## 6. Future.cancel(true): gửi yêu cầu interrupt cho tác vụ

ExecutorService.submit trả về một Future đại diện cho tác vụ được thực thi. Với Future này, cancel(true) yêu cầu hủy tác vụ và, nếu tác vụ đang chạy, cố gắng interrupt thread thực hiện nó:

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();

Future<?> task = executor.submit(() -> {
    performWork();
});

boolean accepted = task.cancel(true);
~~~

cancel(true) không phải lệnh buộc JVM dừng thread. Nó gửi interrupt. Tác vụ phải phản hồi interrupt hoặc kiểm tra trạng thái interrupted để kết thúc đúng cách.

Nếu tác vụ chưa bắt đầu, cancellation có thể ngăn nó chạy. Nếu tác vụ đang chạy, thread có thể nhận InterruptedException từ các thao tác chờ có thể interrupt, chẳng hạn Thread.sleep, Object.wait hoặc BlockingQueue.take.

Nếu tác vụ bỏ qua interrupt, tiếp tục vòng lặp vô hạn hoặc đang thực hiện một thao tác I/O không phản hồi interrupt, nó có thể vẫn tiếp tục sau cancel(true). Vì vậy, cần thiết kế tác vụ có điểm kiểm tra hủy và giải phóng tài nguyên phù hợp.

## 7. Xử lý InterruptedException đúng cách

Khi một thao tác chờ ném InterruptedException, cờ interrupt của thread thường đã được xóa. Nếu không thể truyền InterruptedException lên caller, hãy khôi phục cờ interrupt trước khi thoát:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Với tác vụ tính toán CPU-bound, cần kiểm tra cờ interrupt định kỳ:

~~~java
for (int i = 0; i < limit; i++) {
    if (Thread.currentThread().isInterrupted()) {
        return;
    }

    calculateNextValue(i);
}
~~~

Nếu tác vụ có nhiều bước, hãy kiểm tra interruption tại các ranh giới hợp lý. Không nên kiểm tra quá dày đến mức làm giảm hiệu năng mà không cần thiết, nhưng cũng không để một vòng lặp dài bỏ qua tín hiệu dừng trong thời gian quá lâu.

Nếu dùng một cờ hủy riêng như AtomicBoolean, hãy kiểm tra cả cờ đó và trạng thái interrupt. Cờ hủy hữu ích khi muốn báo dừng mà không cần dựa hoàn toàn vào thread interruption.

## 8. Kết hợp timeout với cancellation thực sự

Một thiết kế thường dùng là tách hai đối tượng:

- CompletableFuture đại diện cho kết quả mà caller quan sát.
- Future<?> từ ExecutorService.submit đại diện cho tác vụ thực thi thực tế.

Khi kết quả timeout, callback gửi yêu cầu hủy tới Future thực thi:

~~~java
CompletableFuture<String> result = new CompletableFuture<>();

Future<?> task = executor.submit(() -> {
    try {
        String value = performInterruptibleWork();
        result.complete(value);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        result.completeExceptionally(e);
    }
});

result.orTimeout(2, TimeUnit.SECONDS)
    .whenComplete((value, error) -> {
        if (error instanceof TimeoutException) {
            task.cancel(true);
        }
    });
~~~

Ở đây timeout làm CompletableFuture hoàn tất ngoại lệ. Callback sau đó gọi cancel(true) trên Future của ExecutorService để yêu cầu interrupt thread thực thi.

Nếu task không phản hồi interruption, nó vẫn có thể chạy tiếp. Nếu task đã hoàn tất ngay trước khi callback chạy, cancel có thể trả về false vì tác vụ không còn ở trạng thái có thể hủy. Đây là race condition bình thường; code cần xử lý theo trạng thái thực tế thay vì giả định thứ tự tuyệt đối.

Không nên chỉ gọi result.cancel(true) rồi cho rằng task đã dừng. Nếu cần dừng công việc nền, phải giữ handle của tác vụ hoặc cung cấp cơ chế hủy riêng.

## 9. Dùng timeout cho toàn bộ quy trình hay từng bước?

Một chuỗi bất đồng bộ có thể gồm nhiều bước: gọi dịch vụ, xử lý dữ liệu, ghi kết quả. Cần xác định timeout áp dụng cho từng bước hay toàn bộ quy trình.

Nếu mỗi bước có timeout hai giây riêng, ba bước tuần tự có thể tiêu tốn gần sáu giây. Nếu yêu cầu nghiệp vụ là toàn bộ quy trình phải xong trong hai giây, cần dùng một deadline chung.

Có thể tính deadline bằng System.nanoTime(), vì đây là đồng hồ đơn điệu phù hợp để đo khoảng thời gian:

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

long remaining = deadline - System.nanoTime();
if (remaining <= 0) {
    throw new TimeoutException("Deadline exceeded");
}

String value = future.get(remaining, TimeUnit.NANOSECONDS);
~~~

Khi chuyển sang bước tiếp theo, tính lại remaining từ cùng deadline. Không đặt lại toàn bộ hai giây cho mỗi bước nếu yêu cầu là giới hạn tổng thời gian.

Với CompletableFuture, có thể áp dụng orTimeout cho Future tổng hợp đại diện cho cả chuỗi. Tuy nhiên, nếu timeout tổng xảy ra, vẫn cần hủy các tác vụ nền đang chạy nếu chúng không còn cần thiết.

## 10. Ví dụ hoàn chỉnh: timeout rồi dừng worker bằng interrupt

Chương trình sau tạo một worker chờ trong thời gian dài. CompletableFuture đại diện cho kết quả bị giới hạn thời gian bằng orTimeout. Khi timeout, callback gọi Future.cancel(true) để gửi interrupt cho worker.

**Tệp CompletableFutureTimeoutDemo.java:**

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch stopped = new CountDownLatch(1);
        CompletableFuture<String> result = new CompletableFuture<>();
        AtomicBoolean cancelAccepted = new AtomicBoolean();

        Future<?> worker = executor.submit(() -> {
            started.countDown();
            try {
                Thread.sleep(TimeUnit.SECONDS.toMillis(10));
                result.complete("completed");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                result.completeExceptionally(e);
            } finally {
                stopped.countDown();
            }
        });

        try {
            started.await();

            CompletableFuture<String> timed =
                    result.orTimeout(100, TimeUnit.MILLISECONDS);

            timed.whenComplete((value, error) -> {
                if (error instanceof TimeoutException) {
                    cancelAccepted.set(worker.cancel(true));
                }
            });

            boolean timeoutObserved = false;
            try {
                timed.join();
            } catch (CompletionException e) {
                timeoutObserved = e.getCause() instanceof TimeoutException;
            }

            boolean workerStopped = stopped.await(2, TimeUnit.SECONDS);
            executor.shutdown();
            boolean executorStopped =
                    executor.awaitTermination(2, TimeUnit.SECONDS);

            System.out.println("timeout observed: " + timeoutObserved);
            System.out.println("worker cancel accepted: " + cancelAccepted.get());
            System.out.println("worker stopped: " + workerStopped);
            System.out.println("executor terminated: " + executorStopped);
        } finally {
            executor.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac --release 17 -Xlint:all CompletableFutureTimeoutDemo.java
java CompletableFutureTimeoutDemo
~~~

Output:

~~~text
timeout observed: true
worker cancel accepted: true
worker stopped: true
executor terminated: true
~~~

CountDownLatch started bảo đảm worker đã bắt đầu trước khi timeout được áp dụng. Khi timeout xảy ra, callback yêu cầu hủy Future thực thi bằng cancel(true). Thread đang sleep nhận InterruptedException, khôi phục cờ interrupt rồi thoát. finally giảm latch stopped để luồng chính xác nhận worker đã rời khỏi tác vụ.

Ví dụ này cho thấy timeout và dừng worker là hai bước riêng. orTimeout hoàn tất CompletableFuture; callback mới là phần gửi yêu cầu interrupt tới tác vụ thực tế.

## 11. Giải phóng tài nguyên khi hủy

Dừng thread không tự động bảo đảm mọi tài nguyên bên ngoài được giải phóng đúng cách. Tác vụ cần đóng những tài nguyên mà nó sở hữu:

- Đóng InputStream, OutputStream, Socket hoặc JDBC resource bằng try-with-resources.
- Dùng timeout riêng của thư viện HTTP, JDBC hoặc client mạng nếu API cung cấp.
- Khi hủy, đóng resource đang chờ I/O nếu đó là cách thư viện yêu cầu để đánh thức thao tác.
- Không chia sẻ một resource giữa nhiều tác vụ nếu một tác vụ có thể đóng nó trong lúc tác vụ khác vẫn sử dụng.

Với tác vụ chờ I/O, interrupt không phải lúc nào cũng có nghĩa thao tác I/O sẽ dừng ngay. Hành vi phụ thuộc loại API và implementation. Hãy dùng cơ chế cancellation/timeout do thư viện cung cấp và đóng resource theo đúng hợp đồng của API đó.

Không dùng Thread.stop để ép dừng công việc. Cách này có thể làm đối tượng ở trạng thái không nhất quán và không phải cơ chế cancellation an toàn.

## 12. Race condition và các tình huống cần xử lý

Timeout và hoàn tất bình thường có thể xảy ra gần như cùng lúc. CompletableFuture chỉ chấp nhận một kết quả hoàn tất đầu tiên:

- Nếu tác vụ hoàn tất trước, timeout không còn thay đổi kết quả.
- Nếu timeout hoàn tất trước, kết quả thành công đến muộn không ghi đè trạng thái timeout.
- Callback timeout có thể chạy đồng thời với cleanup hoặc callback khác.
- cancel(true) có thể trả về false nếu task đã hoàn tất hoặc đã được hủy.

Do đó:

- Dùng complete() hoặc completeExceptionally() và kiểm tra giá trị boolean nếu cần biết thao tác hoàn tất có thắng race hay không.
- Cleanup nên idempotent: gọi nhiều lần vẫn an toàn.
- Không giả định callback chạy trên thread caller; callback phụ thuộc stage và executor thực thi.
- Không giữ lock lâu trong callback timeout, vì callback có thể chạy trên thread phục vụ việc hoàn tất Future.
- Nếu cần phân biệt timeout với cancellation do người dùng, biểu diễn nguyên nhân bằng trạng thái hoặc exception riêng thay vì gom mọi trường hợp thành một lỗi chung.

## 13. Lỗi thường gặp

- **Coi timeout là cancellation:** timeout chỉ giới hạn thời gian chờ hoặc hoàn tất Future. Hãy gửi yêu cầu hủy riêng nếu cần dừng worker.
- **Cho rằng orTimeout tự interrupt supplier:** orTimeout chỉ hoàn tất CompletableFuture bằng TimeoutException. Công việc nền có thể tiếp tục.
- **Cho rằng completeOnTimeout dừng computation:** giá trị dự phòng chỉ hoàn tất Future; supplier có thể vẫn chạy.
- **Dùng CompletableFuture.cancel(true) để ngắt thread:** tham số mayInterruptIfRunning không điều khiển thread trong CompletableFuture. Giữ Future từ ExecutorService nếu cần yêu cầu interrupt.
- **Bỏ qua InterruptedException:** hãy kết thúc tác vụ hoặc truyền lỗi; nếu bắt và không ném tiếp, khôi phục cờ interrupt khi phù hợp.
- **Không kiểm tra interrupt trong vòng lặp CPU-bound:** tác vụ có thể không phản hồi cancellation.
- **Không đóng resource:** worker có thể dừng nhưng socket, stream hoặc connection vẫn bị giữ nếu cleanup thiếu.
- **Đặt lại timeout ở từng stage:** tổng thời gian quy trình có thể vượt deadline nghiệp vụ. Dùng một deadline chung khi cần giới hạn tổng.
- **Giả định cancel(true) luôn dừng ngay:** đây là yêu cầu interrupt, không phải bảo đảm cưỡng bức dừng thread.
- **Không kiểm thử race condition:** kiểm tra cả trường hợp tác vụ hoàn tất trước timeout, timeout trước kết quả và cancellation trong lúc đang chạy.

## 14. Chọn API theo nhu cầu

| Mục tiêu | API phù hợp |
|---|---|
| Chỉ giới hạn thời gian chờ của caller | Future.get(timeout, unit) |
| Hoàn tất CompletableFuture bằng TimeoutException | CompletableFuture.orTimeout |
| Trả về giá trị dự phòng khi hết hạn | CompletableFuture.completeOnTimeout |
| Đánh dấu CompletableFuture bị hủy | CompletableFuture.cancel |
| Yêu cầu interrupt tác vụ ExecutorService | Future.cancel(true) |
| Kiểm tra thread có nhận interrupt | Thread.currentThread().isInterrupted() |
| Chờ kết quả bất đồng bộ | thenApply, thenAccept, whenComplete |
| Chờ worker dừng trong giới hạn thời gian | CountDownLatch.await hoặc ExecutorService.awaitTermination |
| Giới hạn tổng thời gian nhiều bước | Deadline dựa trên System.nanoTime() |

## 15. Ghi nhớ

Timeout và cancellation giải quyết hai vấn đề khác nhau. get(timeout, unit) chỉ giới hạn thời gian chờ của caller. orTimeout và completeOnTimeout hoàn tất CompletableFuture theo chính sách thời hạn, nhưng không tự dừng supplier hoặc tác vụ nền. CompletableFuture.cancel(true) cũng không gửi interrupt để điều khiển computation. Nếu cần dừng công việc thực tế, giữ Future từ ExecutorService và gọi cancel(true), đồng thời thiết kế tác vụ phản hồi interruption, kiểm tra tín hiệu hủy và giải phóng tài nguyên. Luôn kiểm thử race giữa timeout, hoàn tất và cancellation.
