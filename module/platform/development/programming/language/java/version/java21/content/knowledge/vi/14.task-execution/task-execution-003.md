# Quản lý ExecutorService bằng try-with-resources

Trong Java 21, `ExecutorService` triển khai `AutoCloseable`, vì vậy có thể quản lý vòng đời executor bằng `try-with-resources`. Khi rời khỏi khối `try`, `close()` khởi động quá trình shutdown có trật tự và chờ các tác vụ đã được submit hoàn tất trước khi trả quyền điều khiển cho luồng gọi.

Cách này giúp tránh quên gọi `shutdown()` ở các nhánh return hoặc khi có exception. Tuy nhiên, cần hiểu rằng `close()` chờ công việc hoàn tất; nó không có nghĩa là hủy ngay mọi tác vụ. Bài này giải thích vòng đời executor, cách lấy kết quả, xử lý lỗi và chọn loại executor phù hợp trong Java 21.

## 1. Vì sao ExecutorService cần được đóng?

`ExecutorService` quản lý việc nhận task, lập lịch thực thi, worker thread và hàng đợi công việc. Khi ứng dụng không còn sử dụng executor, cần yêu cầu nó ngừng nhận task mới và kết thúc các task đã được nhận.

Nếu tạo executor nhưng không đóng, các worker thread có thể tiếp tục tồn tại và giữ JVM hoạt động, hoặc tài nguyên quản lý task vẫn được giữ lâu hơn dự kiến. Với các executor dùng chung trong suốt vòng đời ứng dụng, việc đóng thường thuộc về thành phần sở hữu executor. Với executor chỉ phục vụ một thao tác hoặc một phạm vi công việc, `try-with-resources` là cách quản lý gọn và an toàn.

Từ Java 19, `ExecutorService` kế thừa `AutoCloseable` và cung cấp `close()`. Do đó, API này đã là tính năng ổn định trong Java 21:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor = Executors.newFixedThreadPool(4)) {
    executor.submit(() -> generateReport());
}
// Rời khối try sau khi executor đã đóng và các task đã kết thúc.
```

Không cần tự viết `finally` chỉ để gọi `shutdown()` cho executor được sở hữu bởi khối `try`. Java tự gọi `close()` khi rời khỏi phạm vi, kể cả khi thân khối kết thúc bằng exception hoặc `return`.

## 2. close() hoạt động như thế nào?

Trong Java 21, `ExecutorService.close()` thực hiện shutdown có trật tự:

1. Ngừng chấp nhận task mới.
2. Cho các task đã submit trước đó tiếp tục chạy.
3. Chờ các task hoàn tất và executor chuyển sang trạng thái terminated.
4. Chỉ trả về sau khi executor đã kết thúc.

Vì vậy, sau khi thoát khỏi khối `try-with-resources`, các task đã được submit vào executor phải kết thúc (dù thành công hay thất bại) trước khi chương trình tiếp tục qua câu lệnh kế tiếp.

Ví dụ sau cho thấy task vẫn chạy dù thân khối `try` đã kết thúc:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorCloseExample {
    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            executor.submit(() -> {
                System.out.println("Task bắt đầu");
                doWork();
                System.out.println("Task hoàn tất");
            });

            System.out.println("Đã submit task");
        }

        System.out.println("Executor đã đóng");
    }

    static void doWork() {
        // Xử lý công việc.
    }
}
```

Thông báo `Executor đã đóng` chỉ được in sau khi task đã kết thúc. Thứ tự giữa `Đã submit task` và `Task bắt đầu` không được bảo đảm vì task chạy bất đồng bộ; nhưng `Task hoàn tất` sẽ xảy ra trước khi `close()` trả về.

Nếu task bị treo vô thời hạn, hoặc chờ một tài nguyên không bao giờ sẵn sàng, `close()` cũng có thể chờ vô thời hạn. Vì vậy, task cần có timeout, cơ chế hủy hoặc điều kiện kết thúc rõ ràng khi nghiệp vụ yêu cầu giới hạn thời gian.

## 3. So sánh close(), shutdown() và shutdownNow()

Ba phương thức có mục đích liên quan nhưng hành vi khác nhau:

| Phương thức | Ngừng nhận task mới | Task đã submit | Chờ executor kết thúc |
|---|---|---|---|
| `shutdown()` | Có | Tiếp tục chạy | Không chờ; trả về ngay |
| `shutdownNow()` | Có | Cố gắng dừng task đang chạy, không khởi chạy task đang chờ và trả danh sách task chưa bắt đầu | Không chờ; trả về ngay |
| `close()` | Có | Shutdown có trật tự, cho task đã submit hoàn tất | Có; chờ đến khi terminated |

`shutdownNow()` chỉ cố gắng dừng task đang chạy, thường bằng cách gửi interrupt tới worker. Nó không bảo đảm task sẽ dừng ngay; task phải hợp tác bằng cách phản hồi interrupt hoặc kiểm tra trạng thái interrupt. Các task không phản hồi interrupt có thể tiếp tục chạy.

`close()` phù hợp khi muốn hoàn tất công việc đã nhận trước khi rời phạm vi. Nếu cần dừng sớm vì hủy thao tác hoặc hết thời hạn, hãy dùng `shutdownNow()`/`Future.cancel(true)` và thiết kế task phản hồi interrupt phù hợp. Không nên thay `close()` bằng `shutdownNow()` chỉ để khối try thoát nhanh hơn nếu nghiệp vụ yêu cầu bảo toàn công việc đã submit.

### Dùng shutdown và awaitTermination khi cần điều khiển thủ công

`try-with-resources` phù hợp với executor có vòng đời gắn với một phạm vi. Nếu executor là tài nguyên cấp ứng dụng, được quản lý bởi lifecycle của server hoặc framework, thành phần sở hữu có thể cần gọi shutdown trong callback đóng ứng dụng và tự điều khiển thời gian chờ:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

static void stopExecutor(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                System.err.println("Executor chưa kết thúc");
            }
        }
    } catch (InterruptedException e) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
```

Đây là cách điều khiển thủ công hữu ích khi cần timeout cụ thể. Không gọi `shutdown()` rồi bỏ quên executor; phải quyết định cách xử lý khi hết thời gian chờ và khi luồng đóng bị interrupt.

## 4. Lấy kết quả và xử lý exception từ task

`submit()` trả về `Future`. Khi cần kết quả hoặc cần biết task có thất bại hay không, hãy giữ `Future` và gọi `get()`:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    Future<Integer> total = executor.submit(() -> calculateTotal());

    try {
        int result = total.get();
        System.out.println("Total: " + result);
    } catch (ExecutionException e) {
        throw new IllegalStateException("Không tính được tổng", e.getCause());
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Đã bị interrupt khi chờ kết quả", e);
    }
}
```

`Future.get()` chờ task hoàn tất nếu task chưa xong. Nếu task ném exception, `get()` ném `ExecutionException` và nguyên nhân gốc có thể lấy qua `getCause()`. Nếu luồng gọi bị interrupt trong lúc chờ, `get()` ném `InterruptedException`; nên khôi phục trạng thái interrupt hoặc truyền tín hiệu hủy lên tầng gọi theo hợp đồng ứng dụng.

`close()` chờ task hoàn tất nhưng **không tự ném lại exception nghiệp vụ từ mọi task đã submit**. Với `submit()`, exception được lưu trong `Future`; nếu không gọi `get()` hoặc kiểm tra kết quả theo cách khác, lỗi task có thể không được luồng gọi quan sát. Với `execute()`, exception không được bắt trong task có thể đi tới uncaught exception handler của worker.

Nếu task chỉ cần chạy nền và không có kết quả trả về, có thể dùng `execute(Runnable)`. Nếu cần kết quả, lỗi, hoặc hủy riêng từng task, dùng `submit()` và quản lý `Future` tương ứng.

## 5. Điều gì xảy ra khi thân try ném exception?

`try-with-resources` luôn gọi `close()` khi rời khỏi khối, kể cả khi thân `try` ném exception. Ví dụ:

```java
try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
    executor.submit(() -> saveData());
    throw new IllegalStateException("Lỗi trong luồng chính");
}
```

Trước khi exception thoát ra khỏi câu lệnh try-with-resources, Java gọi `executor.close()`. Các task đã submit vẫn được phép hoàn tất theo shutdown có trật tự. Vì vậy, exception của luồng gọi không tự động hủy các task đang chạy.

Nếu `close()` cũng phát sinh exception trong khi thân `try` đã có exception, exception từ `close()` được ghi nhận là *suppressed exception* trên exception chính theo quy tắc try-with-resources. Có thể đọc các exception này bằng `getSuppressed()` khi cần chẩn đoán.

Điều này đặc biệt quan trọng nếu task phụ thuộc vào tài nguyên khác trong cùng khối. Hãy tổ chức thứ tự khai báo resource sao cho executor đóng trước các tài nguyên mà task cần dùng. Tài nguyên được khai báo sau sẽ được đóng trước; tài nguyên được khai báo trước sẽ được đóng sau.

```java
try (var connection = openConnection();
     ExecutorService executor = Executors.newFixedThreadPool(2)) {
    executor.submit(() -> writeUsing(connection));
}
```

Ở ví dụ này, `executor` được khai báo sau `connection`, nên `executor.close()` chạy trước và chờ task kết thúc; sau đó `connection` mới được đóng. Cần bảo đảm việc chia sẻ `connection` giữa các task cũng tuân thủ hợp đồng thread-safety của driver và API JDBC đang sử dụng.

## 6. Xử lý interrupt khi close đang chờ

`close()` có thể phải chờ trong một khoảng thời gian dài. Nếu thread đang gọi `close()` bị interrupt trong khi chờ, hợp đồng Java 21 quy định executor chuyển sang hành vi dừng mạnh hơn: gọi `shutdownNow()`, tiếp tục chờ các task kết thúc, rồi khôi phục trạng thái interrupt cho thread gọi sau khi chờ xong.

Điều này có nghĩa interrupt không làm `close()` lập tức trả về. Nếu một task không phản hồi interrupt, quá trình đóng vẫn có thể tiếp tục chờ. Do đó:

- Thiết kế task blocking có timeout hoặc cơ chế hủy rõ ràng.
- Không nuốt `InterruptedException` trong task; khôi phục trạng thái interrupt hoặc kết thúc task theo hợp đồng.
- Tránh gọi `close()` trên một luồng cần phản hồi nhanh nếu executor có thể chứa task dài hoặc không có giới hạn thời gian.
- Với shutdown cần deadline, dùng quy trình `shutdown()`, `awaitTermination()` và `shutdownNow()` có timeout do thành phần sở hữu quản lý.

## 7. Chọn loại ExecutorService trong Java 21

`try-with-resources` hoạt động với các implementation `ExecutorService` khác nhau. Cách chọn executor phụ thuộc workload và giới hạn tài nguyên:

| Executor | Phù hợp khi | Điểm cần lưu ý |
|---|---|---|
| `Executors.newFixedThreadPool(n)` | Muốn giới hạn số worker platform thread | Dùng hàng đợi không giới hạn mặc định; tải submit vượt khả năng xử lý có thể làm hàng đợi tăng lớn |
| `Executors.newSingleThreadExecutor()` | Cần thực thi tuần tự trên một worker | Task chạy lâu sẽ chặn các task sau trong hàng đợi |
| `Executors.newCachedThreadPool()` | Tác vụ ngắn, tải biến động và cần tái sử dụng worker | Có thể tạo nhiều platform thread khi tải tăng; cần cân nhắc giới hạn |
| `Executors.newVirtualThreadPerTaskExecutor()` | Nhiều task đồng thời, phần lớn chờ I/O hoặc dùng API blocking | Mỗi task có virtual thread riêng; vẫn cần giới hạn tài nguyên bên ngoài như connection pool hoặc dịch vụ từ xa |

Ví dụ Java 21 với virtual thread:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
    for (int i = 0; i < 1_000; i++) {
        int taskId = i;
        executor.submit(() -> callRemoteService(taskId));
    }
}
```

Khi rời khối `try`, executor ngừng nhận task và chờ các virtual thread đã tạo hoàn tất. Virtual thread giảm chi phí quản lý thread cho nhiều tác vụ blocking, nhưng không làm cho database, connection pool, API từ xa hoặc CPU có khả năng xử lý vô hạn. Cần đặt giới hạn ở các tài nguyên có dung lượng hữu hạn.

## 8. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chương trình tiếp tục chạy sau khi đã submit task | Executor chưa được đóng hoặc thuộc sở hữu của thành phần khác | Đóng executor tại nơi sở hữu bằng try-with-resources hoặc lifecycle callback |
| Thoát khối try chậm | `close()` đang chờ task hoàn tất | Kiểm tra task blocking, timeout và điều kiện kết thúc |
| Task ném exception nhưng luồng gọi không biết | Đã dùng `submit()` nhưng không đọc `Future` | Gọi `Future.get()` hoặc thu thập kết quả/lỗi bằng cơ chế tương ứng |
| `shutdownNow()` nhưng task vẫn chạy | Task không phản hồi interrupt | Thiết kế task hợp tác với interrupt và timeout |
| Hàng đợi tăng liên tục | Pool cố định có producer submit nhanh hơn worker xử lý | Thêm backpressure, giới hạn hàng đợi hoặc chọn executor phù hợp |
| Resource dùng bởi task bị đóng quá sớm | Resource được khai báo sau executor trong try-with-resources | Sắp xếp thứ tự resource để executor đóng trước dependency của task |

## 9. Checklist quản lý ExecutorService bằng try-with-resources

- [ ] Executor có vòng đời gắn với phạm vi hiện tại và được khai báo trong `try-with-resources`.
- [ ] Đã hiểu `close()` thực hiện orderly shutdown và chờ các task đã submit hoàn tất.
- [ ] Không kỳ vọng `close()` hủy task ngay lập tức.
- [ ] Giữ và kiểm tra `Future` nếu cần kết quả hoặc cần quan sát exception từ `submit()`.
- [ ] Task blocking có timeout hoặc cơ chế phản hồi interrupt phù hợp.
- [ ] Đã chọn executor theo workload và giới hạn tài nguyên thực tế.
- [ ] Nếu dùng `newFixedThreadPool`, đã đánh giá nguy cơ hàng đợi không giới hạn.
- [ ] Nếu task dùng resource trong cùng khối, đã khai báo resource theo thứ tự đóng phù hợp.
- [ ] Executor dùng chung ở cấp ứng dụng được đóng bởi đúng thành phần sở hữu, không đóng sau mỗi lần gọi service.
- [ ] Đã xác định cách xử lý khi shutdown bị interrupt hoặc task không thể kết thúc.

## Tài liệu tham khảo

- [ExecutorService — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `AutoCloseable`, `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination()` và vòng đời executor.
- [Executor — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html): khác biệt giữa `execute` và cách gửi task đến executor.
- [Future — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): lấy kết quả, hủy task và xử lý trạng thái hoàn tất.
- [Executors — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): các factory tạo thread pool và virtual-thread-per-task executor.
- [JEP 444: Virtual Threads](https://openjdk.org/jeps/444): cách sử dụng virtual thread trong Java 21 cho workload có nhiều tác vụ blocking.
