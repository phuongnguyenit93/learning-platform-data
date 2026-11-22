# Kiểm soát vòng đời tác vụ để tránh công việc chạy quá phạm vi request

## Mục tiêu

Một request có thể khởi chạy nhiều tác vụ phụ: đọc hồ sơ, lấy danh sách đơn hàng, gọi dịch vụ HTTP hoặc truy vấn dữ liệu. Khi request hoàn tất, hết thời gian chờ hoặc bị hủy, các tác vụ con thường cũng cần kết thúc. Nếu chúng tiếp tục chạy mà không còn ai sử dụng kết quả, ứng dụng sẽ lãng phí tài nguyên, giữ kết nối và có thể thực hiện những thay đổi dữ liệu ngoài ý muốn.

Trong Java 21, có thể quản lý vòng đời các tác vụ bằng `ExecutorService`, `Future`, timeout, cancellation và interrupt. Virtual threads giúp tạo tác vụ nhẹ hơn, nhưng không tự gắn vòng đời task với vòng đời request. Bài học này tập trung vào cách xác định quyền sở hữu tác vụ, chờ kết quả trong giới hạn thời gian, hủy công việc còn lại khi request kết thúc và đóng executor đúng nơi.

## 1. Vấn đề khi tác vụ sống lâu hơn request

Giả sử một endpoint cần lấy dữ liệu từ ba nguồn. Request gửi ba tác vụ đồng thời, nhưng chỉ cần trả response khi cả ba kết quả đã sẵn sàng. Nếu một tác vụ lỗi hoặc request đã hết deadline, hai tác vụ còn lại có thể vẫn tiếp tục chạy.

Điều này tạo ra một số rủi ro:

- **Tốn tài nguyên:** tác vụ vẫn chiếm thread, bộ nhớ, socket hoặc database connection dù response không còn cần kết quả.
- **Tác dụng phụ ngoài ý muốn:** một tác vụ ghi dữ liệu hoặc gửi lệnh đến hệ thống khác sau khi request đã bị hủy.
- **Tích tụ công việc:** request đến liên tục nhưng các task cũ không kết thúc, làm hàng đợi và số thao tác đang chờ tăng lên.
- **Khó truy vết:** log của một request đã hoàn tất nhưng các task nền vẫn phát sinh lỗi hoặc hoạt động sau đó.

Nguyên tắc thiết kế là xác định rõ **request nào sở hữu task nào**, điều kiện nào làm task bị hủy và ai chịu trách nhiệm chờ task kết thúc. Việc submit task vào executor chỉ khởi chạy công việc; nó không tự thiết lập quan hệ vòng đời với request đã tạo ra task.

## 2. Phân biệt vòng đời executor, task và request

Ba vòng đời liên quan nhưng không giống nhau:

| Thành phần | Vòng đời | API thường dùng |
|---|---|---|
| Request | Từ lúc nhận request đến khi trả response, timeout hoặc bị hủy | Deadline, cancellation signal của framework, xử lý lỗi |
| Task | Từ lúc submit đến khi hoàn tất, thất bại hoặc bị yêu cầu hủy | `Future`, `cancel()`, `get()`, interrupt |
| Executor | Từ lúc được tạo đến khi ngừng nhận task và kết thúc các task đang chạy | `shutdown()`, `shutdownNow()`, `awaitTermination()`, `close()` |

Executor có thể được sở hữu bởi một request hoặc được chia sẻ trong toàn bộ ứng dụng. Quyền sở hữu quyết định nơi được phép đóng executor:

- Executor tạo riêng cho một request có thể được đóng khi request scope kết thúc.
- Executor dùng chung bởi nhiều request phải do thành phần cấp ứng dụng quản lý; một request không được tự ý `shutdown()` hoặc `close()` executor dùng chung.

Đặc biệt, `Executors.newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task được submit. Executor này không tự giới hạn số task và cũng không tự hủy task khi request gọi nó kết thúc.

## 3. Tạo task và giữ `Future` để quản lý

Khi submit một `Callable` hoặc `Runnable` vào `ExecutorService`, hãy giữ `Future` trả về nếu cần chờ, kiểm tra hoặc hủy task sau đó.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

class KeepFutureExample {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            Future<String> profile = executor.submit(() -> loadProfile("user-101"));

            // Có thể thực hiện công việc khác trong lúc task chạy.
            String result = profile.get();
            System.out.println(result);
        }
    }

    private static String loadProfile(String userId) {
        return "Profile của " + userId;
    }
}
```

`Future` đại diện cho kết quả của một task có thể hoàn tất trong tương lai. Nó cho phép:

- `get()` chờ kết quả.
- `get(timeout, unit)` chờ trong một khoảng thời gian giới hạn.
- `cancel(true)` yêu cầu hủy task và cho phép gửi interrupt đến thread đang chạy task.
- `isDone()` kiểm tra Future đã hoàn tất, thất bại hoặc bị hủy.
- `isCancelled()` kiểm tra Future đã bị hủy hay chưa.

Không bỏ tham chiếu `Future` nếu request vẫn cần khả năng hủy task khi timeout hoặc có lỗi ở một tác vụ khác.

## 4. Giới hạn thời gian chờ và hủy task khi timeout

`Future.get(timeout, unit)` ném `TimeoutException` nếu chưa có kết quả trong khoảng thời gian được chỉ định. Bản thân timeout này **không tự hủy task**. Nếu request không còn cần kết quả, code phải chủ động gọi `cancel(true)`.

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class CancelOnTimeoutExample {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> task = executor.submit(() -> loadRemoteData());

            try {
                String result = task.get(800, TimeUnit.MILLISECONDS);
                System.out.println(result);
            } catch (TimeoutException e) {
                task.cancel(true);
                System.out.println("Request hết thời gian chờ; đã yêu cầu hủy task");
            } catch (ExecutionException e) {
                task.cancel(true);
                throw new IllegalStateException("Không lấy được dữ liệu", e.getCause());
            }
        }
    }

    private static String loadRemoteData() throws InterruptedException {
        Thread.sleep(5_000); // Mô phỏng một thao tác chờ có thể bị interrupt.
        return "remote data";
    }
}
```

`cancel(true)` yêu cầu hủy task và, nếu task đã bắt đầu, yêu cầu interrupt thread đang thực thi. Tham số `true` không phải lệnh buộc JVM dừng ngay mọi mã đang chạy. Task phải phản ứng với interrupt hoặc sử dụng API blocking có khả năng đáp ứng việc hủy.

Nếu task đang chạy một thư viện hoặc I/O không phản ứng với interrupt, nó có thể tiếp tục hoạt động sau khi `Future` đã được đánh dấu cancelled. Vì thế, timeout ở `get()` không phải bảo đảm rằng tài nguyên bên dưới đã được giải phóng ngay.

Tương tự, `Future.isDone()` trả về `true` khi Future đã hoàn tất, thất bại **hoặc bị hủy**. Sau `cancel(true)`, kết quả này cho biết Future đã ở trạng thái kết thúc đối với caller; nó không chứng minh mọi lệnh dọn dẹp trong task đã chạy xong. Nếu cần xác nhận executor và các task thực sự đã dừng, phải chờ vòng đời executor kết thúc hoặc dùng một cơ chế báo hiệu hoàn tất riêng của task.

## 5. Dùng chung một deadline cho nhiều task của request

Nếu request gọi nhiều dịch vụ, không nên cấp toàn bộ timeout riêng cho từng `Future.get()`. Ví dụ ba task, mỗi task được chờ tối đa hai giây theo cách độc lập, có thể khiến request chờ gần sáu giây.

Thay vào đó, xác định một deadline chung khi bắt đầu xử lý request và tính thời gian còn lại trước mỗi lần chờ. Dùng `System.nanoTime()` để đo thời lượng vì nó phù hợp cho tính toán elapsed time, không phụ thuộc việc đồng hồ hệ thống được điều chỉnh.

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class RequestDeadline {
    static <T> T getBeforeDeadline(Future<T> task, long deadlineNanos)
            throws InterruptedException, ExecutionException, TimeoutException {
        long remaining = deadlineNanos - System.nanoTime();
        if (remaining <= 0) {
            throw new TimeoutException("Request deadline đã hết");
        }
        return task.get(remaining, TimeUnit.NANOSECONDS);
    }
}
```

Khi request có deadline 1.500 ms, tất cả task con cùng chia sẻ ngân sách thời gian đó. Nếu task đầu mất 1.000 ms, task tiếp theo chỉ còn khoảng 500 ms. Như vậy thời gian chờ được tính theo toàn request thay vì cộng dồn timeout cho từng task.

Deadline cần được truyền nhất quán tới các tầng gọi tiếp theo. Một `Future.get()` có timeout không tự cấu hình connect timeout hoặc request timeout của HTTP client, JDBC driver hay SDK bên ngoài.

## 6. Hủy các task còn lại khi một task lỗi hoặc request bị hủy

Khi một request tạo nhiều task song song, cần giữ tất cả Future để có thể hủy những task chưa hoàn tất khi một task thất bại, deadline hết hoặc thread xử lý request bị interrupt.

```java
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class RequestFanOut {
    record User(String name) {
    }

    record Orders(int count) {
    }

    record Dashboard(User user, Orders orders) {
    }

    static Dashboard loadDashboard(String userId)
            throws InterruptedException, ExecutionException, TimeoutException {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<?>> tasks = new ArrayList<>();
            long deadline = System.nanoTime() + Duration.ofSeconds(2).toNanos();

            try {
                Future<User> userTask = executor.submit(() -> loadUser(userId));
                tasks.add(userTask);

                Future<Orders> ordersTask = executor.submit(() -> loadOrders(userId));
                tasks.add(ordersTask);

                User user = getBeforeDeadline(userTask, deadline);
                Orders orders = getBeforeDeadline(ordersTask, deadline);
                return new Dashboard(user, orders);
            } catch (TimeoutException | ExecutionException e) {
                cancelAll(tasks);
                throw e;
            } catch (InterruptedException e) {
                cancelAll(tasks);
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }

    private static <T> T getBeforeDeadline(Future<T> task, long deadline)
            throws InterruptedException, ExecutionException, TimeoutException {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            throw new TimeoutException("Request deadline đã hết");
        }
        return task.get(remaining, TimeUnit.NANOSECONDS);
    }

    private static void cancelAll(List<Future<?>> tasks) {
        for (Future<?> task : tasks) {
            if (!task.isDone()) {
                task.cancel(true);
            }
        }
    }

    private static User loadUser(String userId) throws InterruptedException {
        // Thay bằng lời gọi dịch vụ hoặc database có timeout phù hợp.
        Thread.sleep(200);
        return new User(userId);
    }

    private static Orders loadOrders(String userId) throws InterruptedException {
        Thread.sleep(300);
        return new Orders(4);
    }
}
```

Ví dụ dùng một deadline chung và hủy các Future còn lại nếu một thao tác thất bại, hết thời gian hoặc thread request bị interrupt. Trong catch `InterruptedException`, code khôi phục trạng thái interrupt trước khi truyền lỗi lên tầng gọi.

`try-with-resources` đóng executor khi thoát khỏi phạm vi request. `ExecutorService.close()` thực hiện shutdown có trật tự và chờ các task kết thúc. Vì vậy, các task con cần hỗ trợ interrupt và các lời gọi I/O phải có timeout phù hợp; nếu task không chịu kết thúc, thao tác đóng executor có thể tiếp tục chờ.

## 7. Cancellation là yêu cầu hợp tác, không phải cưỡng chế dừng task

Java sử dụng interrupt để báo cho thread biết nó nên dừng hoặc thay đổi cách xử lý. Một số phương thức blocking như `Thread.sleep()` ném `InterruptedException` khi bị interrupt. Code task cần xử lý tín hiệu đó đúng cách.

```java
class CooperativeTask {
    static String pollUntilDone() throws InterruptedException {
        while (!Thread.currentThread().isInterrupted()) {
            if (checkRemoteJob()) {
                return "done";
            }

            Thread.sleep(100);
        }

        throw new InterruptedException("Task đã nhận yêu cầu hủy");
    }

    private static boolean checkRemoteJob() {
        // Kiểm tra trạng thái công việc từ một dịch vụ.
        return false;
    }
}
```

Khi task không gọi phương thức blocking có thể bị interrupt, nó có thể chủ động kiểm tra `Thread.currentThread().isInterrupted()` tại các điểm an toàn. Nếu bắt `InterruptedException` mà không thể truyền tiếp, hãy khôi phục cờ interrupt bằng `Thread.currentThread().interrupt()` trước khi kết thúc hoặc chuyển sang cơ chế hủy khác.

Không dùng các cơ chế cưỡng chế dừng thread. Chúng có thể làm chương trình dừng giữa lúc đang giữ lock hoặc cập nhật dữ liệu, khiến trạng thái ứng dụng không nhất quán. Thiết kế task để hủy hợp tác và giải phóng tài nguyên trong `finally`.

## 8. Timeout của request phải đi cùng timeout của I/O

Hủy Future không thay thế timeout ở tầng I/O. Mỗi dependency cần giới hạn thời gian riêng phù hợp với deadline tổng thể:

- HTTP client: cấu hình connect timeout và request timeout; xử lý `InterruptedException` từ lời gọi blocking.
- Database: cấu hình query timeout, connection acquisition timeout và transaction timeout theo driver/framework.
- File hoặc socket: sử dụng API có timeout hoặc cơ chế đóng tài nguyên để đánh thức thao tác đang chờ khi phù hợp.
- Hàng đợi và semaphore: giới hạn thời gian chờ permit hoặc thời gian chờ nhận task.

Nếu request còn 300 ms nhưng một lời gọi database có timeout 30 giây, request có thể đã kết thúc trong khi thao tác database vẫn tiếp tục. Deadline nên được truyền xuống tầng phụ thuộc để giới hạn thời gian thực thi thực tế, không chỉ giới hạn thời gian chờ Future ở tầng trên.

## 9. Executor dùng chung và quyền sở hữu task

Trong ứng dụng server, executor thường được tạo ở cấp ứng dụng hoặc service để nhiều request cùng sử dụng. Trong trường hợp này, mỗi request có thể hủy các Future do chính nó submit, nhưng không được đóng executor dùng chung.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

class SharedExecutorService {
    private final ExecutorService executor =
            Executors.newVirtualThreadPerTaskExecutor();

    String handleRequest(String id) throws Exception {
        Future<String> task = executor.submit(() -> loadData(id));
        try {
            return task.get(1, TimeUnit.SECONDS);
        } catch (TimeoutException | InterruptedException e) {
            task.cancel(true);
            if (e instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }
            throw e;
        }
    }

    void closeAtApplicationShutdown() {
        executor.close();
    }

    private String loadData(String id) throws InterruptedException {
        Thread.sleep(200);
        return "Data của " + id;
    }
}
```

Ví dụ minh họa quyền sở hữu: `handleRequest()` chỉ hủy task của request đó; executor được đóng khi service hoặc ứng dụng kết thúc. Trong ứng dụng thực tế, nên gắn `closeAtApplicationShutdown()` vào lifecycle hook của framework hoặc thành phần quản lý service. Không gọi `executor.close()` trong mỗi request vì sẽ làm các request khác mất khả năng submit task.

Với executor dùng chung, việc đóng executor cũng cần có chính sách shutdown rõ ràng: ngừng nhận task mới, chờ task đang chạy trong khoảng thời gian phù hợp, sau đó yêu cầu hủy nếu cần. Không để một request tự quyết định vòng đời của tài nguyên cấp ứng dụng.

## 10. Phân biệt `shutdown()`, `shutdownNow()`, `awaitTermination()` và `close()`

Các API vòng đời của `ExecutorService` có mục đích khác nhau:

| API | Hành vi |
|---|---|
| `shutdown()` | Ngừng nhận task mới; task đã submit được phép hoàn tất |
| `shutdownNow()` | Cố gắng dừng task đang chạy bằng interrupt và trả về các task đang chờ chưa bắt đầu; không bảo đảm dừng cưỡng chế |
| `awaitTermination(timeout, unit)` | Chờ executor kết thúc trong thời gian giới hạn; trả `true` nếu đã kết thúc |
| `close()` | Shutdown có trật tự và chờ các task đã submit kết thúc; phù hợp với try-with-resources khi executor thuộc phạm vi hiện tại |

Ví dụ quản lý shutdown có giới hạn thời gian ở cấp ứng dụng:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

class ExecutorShutdown {
    static void stop(ExecutorService executor) throws InterruptedException {
        executor.shutdown();

        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Một số task chưa kết thúc");
            }
        }
    }
}
```

Đây là chính sách shutdown ở cấp thành phần sở hữu executor. Với request scope, không cần tự shutdown executor dùng chung. Với executor riêng của request, try-with-resources là cách quản lý gọn, nhưng task vẫn phải có khả năng kết thúc để `close()` không chờ vô hạn.

## 11. Lưu ý khi dùng `CompletableFuture`

`CompletableFuture` hữu ích để ghép nối các bước xử lý bất đồng bộ. Tuy nhiên, không nên giả định `cancel(true)` trên `CompletableFuture` luôn interrupt thread đang thực thi công việc nền. Hợp đồng cancellation của `CompletableFuture` khác với việc quản lý trực tiếp một `Future` do `ExecutorService.submit()` trả về.

Nếu cần kiểm soát chặt việc hủy task chạy trên executor, hãy giữ `Future` tương ứng hoặc thiết kế rõ cơ chế cancellation được task thực thi kiểm tra. Khi dùng `CompletableFuture`, cũng cần xử lý exception ở pipeline, áp dụng timeout phù hợp và bảo đảm các tác vụ phụ không tiếp tục tạo side effect sau khi request không còn quan tâm kết quả.

## 12. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi `Future.get()` không timeout | Request có thể chờ vô hạn | Dùng deadline và `get(remaining, unit)` |
| Nghĩ timeout tự dừng task | Task vẫn chạy sau khi caller ngừng chờ | Gọi `cancel(true)` và làm task phản ứng với interrupt |
| Hủy Future nhưng task bỏ qua interrupt | Tài nguyên có thể tiếp tục bị giữ | Dùng timeout I/O, kiểm tra interrupt và giải phóng trong `finally` |
| Đóng executor dùng chung trong request | Request này làm gián đoạn request khác | Chỉ chủ sở hữu cấp ứng dụng được đóng executor |
| Dùng timeout riêng cho từng Future | Tổng thời gian request vượt deadline dự kiến | Dùng một deadline chung và tính thời gian còn lại |
| Dùng virtual-thread-per-task executor mà không giới hạn tải | Có thể tạo quá nhiều task chờ dependency | Áp dụng backpressure, semaphore hoặc giới hạn ở connection pool |
| Cho task tiếp tục ghi dữ liệu sau khi request timeout | Side effect xảy ra ngoài vòng đời nghiệp vụ dự kiến | Kiểm tra cancellation trước các bước ghi và dùng transaction/idempotency phù hợp |

## 13. Checklist kiểm soát task theo request

Khi review một request có tạo task con, hãy xác nhận:

1. Mỗi task có chủ sở hữu rõ ràng và có `Future` hoặc cơ chế cancellation tương ứng không?
2. Request có một deadline tổng thể được truyền xuống các bước phụ thuộc không?
3. Khi timeout, lỗi hoặc request bị interrupt, các task còn lại có được yêu cầu hủy không?
4. Task có phản ứng với interrupt và giải phóng tài nguyên trong `finally` không?
5. HTTP, database và các I/O khác có timeout riêng không?
6. Executor được tạo riêng cho request hay dùng chung ở cấp ứng dụng; ai chịu trách nhiệm đóng nó?
7. Có tránh đóng executor dùng chung trong code xử lý request không?
8. Có giới hạn concurrency và số task đang chờ để bảo vệ dependency không?
9. Các side effect có thể xảy ra sau khi request bị hủy đã được kiểm soát không?

## Kết luận

Để tránh công việc chạy quá phạm vi request, cần quản lý cả task lẫn executor theo đúng quyền sở hữu. Giữ `Future` để chờ và hủy task; dùng deadline chung thay vì timeout cộng dồn; gọi `cancel(true)` khi request không còn cần kết quả và thiết kế task phản ứng với interrupt. Timeout của Future phải đi cùng timeout ở tầng I/O và chính sách backpressure. Executor riêng của request có thể được đóng bằng try-with-resources; executor dùng chung phải được quản lý ở lifecycle cấp ứng dụng. Virtual threads làm task chờ I/O nhẹ hơn, nhưng không tự giải quyết cancellation, giới hạn dependency hoặc vòng đời request.
