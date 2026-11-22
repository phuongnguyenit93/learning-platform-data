# Chờ kết quả có timeout và xử lý ExecutionException

Khi gửi một tác vụ qua `ExecutorService.submit(...)`, chương trình nhận về một `Future<V>` đại diện cho kết quả sẽ có trong tương lai. Có thể gọi `get()` để chờ kết quả, hoặc `get(timeout, unit)` để chỉ chờ trong một khoảng thời gian giới hạn.

Hai tình huống cần xử lý riêng là **timeout** và **tác vụ thất bại**. `TimeoutException` cho biết kết quả chưa sẵn sàng trong thời hạn chờ; nó không tự dừng tác vụ. `ExecutionException` cho biết tác vụ đã kết thúc bằng lỗi; nguyên nhân thực tế nằm trong `getCause()`. Ngoài ra, luồng đang chờ có thể bị interrupt, vì vậy cần xử lý `InterruptedException` đúng cách.

## 1. Future và cách chờ kết quả

`Future<V>` biểu diễn kết quả của một tác vụ bất đồng bộ. Sau khi submit, executor có thể chạy tác vụ trên một thread khác trong khi luồng gọi tiếp tục làm công việc khác.

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureGetDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<String> future = executor.submit(() -> {
                Thread.sleep(300);
                return "Task completed";
            });

            String result = future.get();
            System.out.println(result);
        }
    }
}
```

`future.get()` chờ vô thời hạn cho đến khi tác vụ hoàn tất, bị hủy hoặc luồng chờ bị interrupt. Nếu tác vụ chạy lâu hơn dự kiến, luồng gọi có thể phải chờ lâu mà không có giới hạn.

Java 21 cho phép dùng `ExecutorService` trong try-with-resources vì interface này là `AutoCloseable`. Khi thoát khối, `close()` thực hiện shutdown có trật tự và chờ các tác vụ đã submit kết thúc. Điều này thuận tiện cho quản lý vòng đời executor, nhưng cần nhớ rằng việc đóng executor cũng có thể chờ tác vụ còn chạy.

## 2. Dùng get(timeout, unit) để giới hạn thời gian chờ

`Future` cung cấp overload:

```java
V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
```

Phương thức chờ tối đa khoảng thời gian được chỉ định. Nếu kết quả có trước khi hết thời gian, nó trả về kết quả. Nếu hết thời gian mà tác vụ chưa hoàn tất, nó ném `TimeoutException`.

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutDemo {
    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<String> future = executor.submit(() -> {
                Thread.sleep(2_000);
                return "Completed";
            });

            try {
                String result = future.get(500, TimeUnit.MILLISECONDS);
                System.out.println(result);
            } catch (TimeoutException e) {
                future.cancel(true);
                System.out.println("Chưa có kết quả sau 500 ms");
            } catch (InterruptedException e) {
                future.cancel(true);
                Thread.currentThread().interrupt();
                System.out.println("Luồng chờ đã bị interrupt");
            } catch (ExecutionException e) {
                System.out.println("Tác vụ thất bại: " + e.getCause());
            }
        }
    }
}
```

Nếu tác vụ cần khoảng hai giây nhưng chương trình chỉ chờ 500 ms, `get` ném `TimeoutException`. Timeout ở đây chỉ giới hạn thời gian luồng gọi chờ kết quả; tác vụ có thể vẫn đang chạy ở executor.

Thời hạn truyền vào là thời lượng tương đối, không phải thời điểm đồng hồ. Chọn đơn vị bằng `TimeUnit` để code dễ đọc và tránh tự quy đổi sai giữa milliseconds, seconds hoặc nanoseconds.

## 3. Timeout không tự hủy tác vụ

Một lỗi thường gặp là cho rằng khi `get(timeout, unit)` ném `TimeoutException`, tác vụ tự động bị dừng. Thực tế, `Future` vẫn có thể đang chạy. Nếu không còn cần kết quả, chương trình phải chủ động yêu cầu hủy:

```java
try {
    String result = future.get(500, TimeUnit.MILLISECONDS);
    System.out.println(result);
} catch (TimeoutException e) {
    boolean cancellationRequested = future.cancel(true);
    System.out.println("Đã yêu cầu hủy: " + cancellationRequested);
}
```

`cancel(true)` yêu cầu hủy tác vụ và cho phép interrupt thread đang chạy tác vụ nếu có. Giá trị trả về cho biết yêu cầu hủy có được chấp nhận hay không; nó không chứng minh mọi công việc bên trong đã dừng ngay lập tức.

Để phản hồi interrupt, tác vụ cần sử dụng thao tác interruptible hoặc chủ động kiểm tra trạng thái interrupt. Ví dụ:

```java
Future<String> future = executor.submit(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            // Thực hiện một đơn vị công việc hữu hạn.
            Thread.sleep(100); // Điểm chờ có thể phản hồi interrupt.
        }
        return "Task stopped";
    } catch (InterruptedException e) {
        // Tác vụ kết thúc theo yêu cầu hủy.
        Thread.currentThread().interrupt();
        return "Interrupted";
    }
});
```

Ví dụ trên minh họa cách hợp tác với interrupt; trong ứng dụng thực tế, vòng lặp cần có điều kiện kết thúc nghiệp vụ và tài nguyên cần được đóng trong `finally` hoặc try-with-resources. Không được nuốt `InterruptedException` rồi tiếp tục chạy như chưa có gì xảy ra.

Nếu tác vụ đang thực hiện một lời gọi native hoặc thư viện không phản hồi interrupt, `cancel(true)` không thể bảo đảm dừng công việc tức thì. Vì vậy, timeout của `Future.get` không đồng nghĩa với giới hạn cứng cho thời gian sống của tác vụ hoặc thời gian đóng executor.

## 4. Xử lý ExecutionException và lấy nguyên nhân gốc

Khi tác vụ được submit kết thúc bằng exception, lời gọi `get()` hoặc `get(timeout, unit)` ném `ExecutionException`. Exception này là wrapper; lỗi thực tế do tác vụ ném được lấy bằng `getCause()`.

```java
import java.io.IOException;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutionExceptionDemo {
    public static void main(String[] args) {
        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Callable<String> failingTask = () -> {
                throw new IOException("Không đọc được dữ liệu");
            };
            Future<String> future = executor.submit(failingTask);

            try {
                System.out.println(future.get());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Luồng chờ bị interrupt");
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println("Loại lỗi gốc: " + cause.getClass().getSimpleName());
                System.out.println("Thông điệp: " + cause.getMessage());
            }
        }
    }
}
```

Kết quả minh họa:

```text
Loại lỗi gốc: IOException
Thông điệp: Không đọc được dữ liệu
```

Không nên chỉ ghi log `ExecutionException` rồi bỏ qua `getCause()`, vì khi đó thông tin nguyên nhân có thể khó nhận biết. Tùy hợp đồng của phương thức gọi, có thể:

- Xử lý nguyên nhân đã biết, ví dụ retry khi lỗi tạm thời và thao tác an toàn để retry.
- Ném lại nguyên nhân nếu API hiện tại cho phép khai báo kiểu exception đó.
- Bọc nguyên nhân trong exception nghiệp vụ hoặc `IllegalStateException`, giữ nguyên cause để không mất stack trace.

Ví dụ bọc lỗi:

```java
try {
    return future.get();
} catch (ExecutionException e) {
    throw new IllegalStateException("Không thể hoàn tất tác vụ", e.getCause());
}
```

Không tự động retry mọi `ExecutionException`. Lỗi có thể là lỗi dữ liệu, lỗi lập trình hoặc lỗi không thể khắc phục bằng retry. Cần xem nguyên nhân gốc và tính idempotent của tác vụ trước khi chạy lại.

## 5. Phân biệt các exception khi gọi Future.get

Các exception thường gặp có ý nghĩa khác nhau:

| Exception | Ý nghĩa | Cách xử lý thường dùng |
|---|---|---|
| `TimeoutException` | Chưa có kết quả trong thời gian chờ đã đặt | Quyết định tiếp tục chờ, fallback hoặc gọi `cancel(...)` |
| `ExecutionException` | Tác vụ hoàn tất nhưng ném lỗi | Kiểm tra `getCause()` và xử lý theo loại lỗi gốc |
| `InterruptedException` | Luồng đang chờ bị interrupt | Hủy/thu dọn công việc cần thiết, khôi phục interrupt nếu không ném tiếp exception này |
| `CancellationException` | Future đã bị hủy trước khi lấy kết quả | Xử lý như một trạng thái hủy riêng, không coi là task thành công |

`TimeoutException`, `ExecutionException` và `InterruptedException` là checked exceptions trong chữ ký của `get(timeout, unit)`. `CancellationException` là unchecked exception. Không gom tất cả vào một `catch (Exception)` nếu chương trình cần phản ứng khác nhau với timeout, lỗi tác vụ và hủy.

## 6. Xử lý InterruptedException đúng cách

`InterruptedException` được ném khi thread đang chờ bị interrupt. Khi exception này được ném, trạng thái interrupt của thread thường đã bị xóa. Nếu phương thức không thể truyền `InterruptedException` lên caller và quyết định chuyển thành một exception khác, cần khôi phục trạng thái interrupt:

```java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (InterruptedException e) {
    future.cancel(true);
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Bị ngắt khi chờ tác vụ", e);
}
```

Nếu chữ ký phương thức cho phép khai báo `throws InterruptedException`, có thể dọn dẹp cần thiết rồi ném tiếp exception đó. Khi ném tiếp chính `InterruptedException`, không cần gọi `Thread.currentThread().interrupt()` trước khi ném, vì caller nhận được tín hiệu interrupt qua exception.

Không viết catch rỗng:

```java
try {
    future.get();
} catch (InterruptedException ignored) {
    // Sai: nuốt tín hiệu interrupt.
}
```

Nuốt interrupt có thể làm luồng cấp trên không còn biết yêu cầu dừng đã xảy ra, khiến shutdown hoặc cancellation hoạt động sai.

## 7. Chờ nhiều Future với một deadline chung

Nếu gọi `get(1, SECONDS)` riêng cho từng Future trong một vòng lặp, tổng thời gian chờ có thể gần bằng số Future nhân với một giây. Nếu yêu cầu là toàn bộ nhóm tác vụ phải hoàn tất trong một deadline chung, hãy tính thời điểm hết hạn một lần bằng `System.nanoTime()` rồi truyền thời gian còn lại cho từng `get`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

static <T> List<T> collectBeforeDeadline(List<Future<T>> futures,
                                        long timeout,
                                        TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException {

    long deadline = System.nanoTime() + unit.toNanos(timeout);
    List<T> results = new ArrayList<>(futures.size());

    try {
        for (Future<T> future : futures) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new TimeoutException("Đã hết thời gian cho cả nhóm tác vụ");
            }

            results.add(future.get(remaining, TimeUnit.NANOSECONDS));
        }
        return results;
    } catch (TimeoutException | InterruptedException e) {
        for (Future<T> future : futures) {
            if (!future.isDone()) {
                future.cancel(true);
            }
        }
        throw e;
    }
}
```

Deadline chung tránh việc mỗi Future được cấp lại toàn bộ timeout. `System.nanoTime()` phù hợp để đo thời lượng vì không phụ thuộc thay đổi giờ hệ thống. Đoạn code hủy các tác vụ chưa hoàn tất khi timeout hoặc thread chờ bị interrupt; các tác vụ vẫn cần hợp tác với interrupt để dừng.

Nếu một Future hoàn tất bằng lỗi, `ExecutionException` được truyền lên caller. Tùy yêu cầu, caller có thể hủy các Future còn lại trong nhánh xử lý `ExecutionException` nữa. Đoạn ví dụ không tự quyết định chính sách đó vì có hệ thống muốn giữ các kết quả khác để chẩn đoán.

## 8. Timeout của Future khác timeout của toàn bộ request

`future.get(timeout, unit)` chỉ giới hạn thời gian luồng hiện tại chờ một Future. Nó không tự giới hạn:

- Thời gian tác vụ tiếp tục chạy sau khi `get` timeout.
- Thời gian chờ khi đóng executor nếu tác vụ không kết thúc.
- Thời gian của lời gọi mạng hoặc database bên trong tác vụ, trừ khi API I/O đó cũng có timeout.
- Tổng thời gian của nhiều thao tác nếu mỗi thao tác được cấp timeout mới thay vì dùng deadline chung.

Với ứng dụng server, nên truyền deadline hoặc thời gian còn lại đến từng tầng phụ thuộc. Ví dụ, request còn 800 ms thì lời gọi database và HTTP cần dùng timeout phù hợp với ngân sách còn lại, thay vì mỗi tầng tự chờ 5 giây.

Đặt timeout cho Future không thay thế timeout của socket, HTTP client, JDBC driver hoặc connection pool. Mỗi API I/O cần được cấu hình theo hợp đồng timeout riêng; cancellation chỉ là yêu cầu phối hợp dừng công việc.

## 9. Kết hợp timeout với ExecutorService và virtual threads

Java 21 có thể dùng virtual thread-per-task executor nếu mỗi tác vụ chủ yếu thực hiện blocking I/O. Cách chờ Future vẫn tương tự:

```java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class VirtualThreadTimeoutDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> future = executor.submit(() -> {
                Thread.sleep(2_000); // Mô phỏng I/O blocking.
                return "response";
            });

            try {
                String response = future.get(800, TimeUnit.MILLISECONDS);
                System.out.println(response);
            } catch (TimeoutException e) {
                future.cancel(true);
                System.out.println("Request hết thời gian chờ");
            }
        }
    }
}
```

`newVirtualThreadPerTaskExecutor()` tạo một virtual thread cho mỗi task được submit. Nó không tự giới hạn số request đang chờ hoặc quota của dịch vụ bên ngoài. Nếu downstream chỉ cho phép một số lượng lời gọi đồng thời, vẫn cần connection pool, semaphore hoặc cơ chế giới hạn phù hợp.

Khi thoát try-with-resources, `ExecutorService.close()` chờ executor hoàn tất shutdown. Nếu task không phản hồi interrupt, việc đóng executor có thể chờ lâu hơn timeout của `Future.get`. Vì vậy, task và API I/O bên trong cần có chính sách timeout/cancellation rõ ràng.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chờ mãi không có kết quả | Dùng `get()` không timeout cho tác vụ có thể chờ lâu | Dùng `get(timeout, unit)` hoặc deadline phù hợp |
| Bắt `TimeoutException` nhưng task vẫn chạy | Timeout chỉ kết thúc việc chờ kết quả | Gọi `cancel(true)` nếu không còn cần task và bảo đảm task phản hồi interrupt |
| Chỉ log `ExecutionException` | Bỏ qua exception gốc do task ném | Lấy `e.getCause()`, phân loại và giữ nguyên nguyên nhân khi bọc lỗi |
| Retry liên tục sau `ExecutionException` | Không phân biệt lỗi tạm thời với lỗi vĩnh viễn | Chỉ retry lỗi có thể khắc phục và thao tác có thể retry an toàn |
| Ứng dụng không dừng sau interrupt | Catch rồi nuốt `InterruptedException` | Dọn dẹp, ném tiếp hoặc khôi phục cờ interrupt |
| Tổng thời gian chờ vượt ngân sách | Cấp timeout mới cho từng Future | Dùng một deadline chung và tính thời gian còn lại |
| Executor đóng lâu dù Future đã timeout | Task không dừng hoặc I/O bên trong không có timeout | Thiết kế cancellation hợp tác và timeout ở API I/O |
| `get()` ném `CancellationException` | Future đã bị hủy | Xử lý trạng thái cancelled riêng với lỗi thực thi |

## 11. Checklist khi chờ Future

- Dùng `get(timeout, unit)` khi không thể chờ vô thời hạn.
- Xem `TimeoutException` là timeout của thao tác chờ; tự quyết định có hủy task hay không.
- Dùng `cancel(true)` khi cần yêu cầu interrupt và task có thể phản hồi interrupt.
- Lấy nguyên nhân gốc từ `ExecutionException.getCause()`.
- Không retry mọi lỗi một cách tự động; kiểm tra loại lỗi và tính idempotent.
- Xử lý `InterruptedException` bằng cách ném tiếp hoặc khôi phục trạng thái interrupt.
- Xử lý `CancellationException` như trạng thái hủy riêng.
- Dùng deadline chung nếu nhiều Future phải hoàn tất trong cùng ngân sách thời gian.
- Cấu hình timeout cho database/network riêng; timeout Future không tự giới hạn I/O.
- Hiểu rằng `ExecutorService.close()` chờ tác vụ kết thúc và cancellation không cưỡng bức dừng code không hợp tác.

`Future.get(timeout, unit)` giúp giới hạn thời gian chờ kết quả, còn `ExecutionException.getCause()` cho biết lỗi thực sự của tác vụ. Kết hợp hai cơ chế với xử lý interrupt, cancellation và deadline rõ ràng giúp ứng dụng Java 21 kiểm soát tác vụ bất đồng bộ tốt hơn, đồng thời tránh nhầm timeout chờ kết quả với việc tác vụ đã dừng.
