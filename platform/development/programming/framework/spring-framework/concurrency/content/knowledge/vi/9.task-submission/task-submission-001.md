# Gửi Runnable không có kết quả bằng execute()

## 1. Bài toán: giao một công việc cho bộ thực thi

Trong ứng dụng Spring, một luồng đang xử lý yêu cầu có thể cần giao một công việc cho thành phần khác xử lý: ghi log nghiệp vụ, cập nhật một bộ đếm, gửi sự kiện, làm sạch dữ liệu tạm, hoặc kích hoạt một thao tác nền. Khi công việc **không cần trả về một giá trị cho bên gửi**, Java cung cấp `Runnable` và phương thức `execute(Runnable)` của `Executor`; Spring cung cấp cùng cách làm qua `TaskExecutor`.

Ta cần phân biệt hai trách nhiệm:

1. **Tác vụ (`Runnable`)** mô tả việc phải thực hiện.
2. **Bộ thực thi (`Executor` hoặc `TaskExecutor`)** quyết định thực thi tác vụ ở đâu, khi nào và với chính sách tài nguyên nào.

Ví dụ về ý định của bên gửi:

```java
Runnable task = () -> System.out.println("Đã xử lý sự kiện");
executor.execute(task);
```

Đây là **mảnh mã minh họa**, giả định `executor` đã được khai báo và khởi tạo. Lời gọi `execute` trả về `void`. Bên gửi không nhận được giá trị của `run()`, không có `Future` để chờ, và không tự nhận thông báo thành công/thất bại sau khi task chạy.

Một điểm đặc biệt quan trọng: **`execute()` không đồng nghĩa “luôn chạy trên luồng mới”**. Với bộ thực thi trực tiếp, `run()` có thể được gọi ngay trên luồng gửi; với thread pool, task thường chạy trên worker thread sau khi được chấp nhận, có thể sau một thời gian ở hàng đợi. Vì vậy việc dùng `execute` chỉ nói lên *hợp đồng gửi công việc*, còn tính bất đồng bộ phụ thuộc **triển khai executor**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Viết `Runnable` bằng lambda, method reference hoặc một lớp hiện thực.
- Gửi tác vụ bằng `execute(Runnable)` qua Java `Executor` và Spring `TaskExecutor`.
- Phân biệt `run()`, `Thread.start()`, `execute()` và `submit()`.
- Hiểu `void` không có nghĩa task chắc chắn thành công hoặc được thực hiện bất đồng bộ.
- Xử lý trường hợp executor từ chối tác vụ; quan sát lỗi, hoàn tất và vòng đời bằng cơ chế riêng khi cần.
- Đưa mẫu gửi việc vào một bean Spring mà vẫn kiểm soát giới hạn worker, queue, trạng thái chia sẻ và thời điểm ứng dụng đóng.

## 2. Hợp đồng của Runnable và execute()

### 2.1. Runnable biểu diễn tác vụ không trả giá trị

`Runnable` là một functional interface trong `java.lang`:

```java
@FunctionalInterface
public interface Runnable {
    void run();
}
```

Chữ ký `void run()` có nghĩa lời gọi `run()` không trả dữ liệu trực tiếp. Phương thức này cũng không khai báo `throws Exception` cho checked exception. Tuy nhiên, tác vụ vẫn có thể gặp lỗi, có thể ném `RuntimeException` hoặc `Error`, và có thể thực hiện tác động phụ như ghi dữ liệu hoặc gửi yêu cầu.

Ba kiểu biểu diễn tương đương về mục tiêu:

```java
// Lambda:
Runnable lambda = () -> System.out.println("Làm việc");

// Method reference, đặt trong phạm vi có phương thức logMessage():
Runnable reference = this::logMessage;

// Lớp ẩn danh:
Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Làm việc");
    }
};
```

Đoạn này **chỉ minh họa các cách khai báo trong một class phù hợp**; `this::logMessage` yêu cầu phương thức instance `logMessage()` có sẵn. Khi làm ứng dụng thật, lambda thường đủ gọn nếu công việc nhỏ; với logic phức tạp, nên đưa nghiệp vụ vào một method/service có tên rõ ràng.

Không nên suy luận từ tên `Runnable` rằng Java đã tạo hay bắt đầu một thread. `Runnable` chỉ là đối tượng chứa hành vi cho tới khi có bên gọi `run()` hoặc giao nó cho một executor.

### 2.2. Executor có một phương thức cốt lõi

Java định nghĩa:

```java
public interface Executor {
    void execute(Runnable command);
}
```

Spring định nghĩa một abstraction tương thích:

```java
public interface TaskExecutor extends java.util.concurrent.Executor {
    void execute(Runnable task);
}
```

Đây là **chữ ký API tóm lược**, không phải mã nguồn đầy đủ của thư viện. Trong Spring, `TaskExecutor` mang hợp đồng thực thi `Runnable`, với `TaskRejectedException` nếu task không được chấp nhận. Các implementation có thể thực thi trực tiếp, tạo thread mới hoặc tái sử dụng worker trong pool.

Khi gọi:

```java
executor.execute(task);
```

- `task` là việc phải làm, không phải tên thread.
- `execute(...)` **không** trả `Future`, ID job, trạng thái hoàn tất hoặc kết quả tính toán.
- Nếu executor sử dụng chiến lược bất đồng bộ, lời gọi có thể trả rất nhanh sau khi tiếp nhận task; công việc có thể chưa bắt đầu.
- Nếu executor chạy đồng bộ hoặc áp dụng chính sách cho caller tự chạy task, lời gọi có thể chặn cho đến khi task chạy xong.
- Executor có thể từ chối task khi đã đóng hoặc vượt giới hạn; trong Spring `ThreadPoolTaskExecutor` với chính sách từ chối mặc định, việc này thường xuất hiện dưới dạng `TaskRejectedException`.
- Một ngoại lệ phát sinh **khi gọi execute** cần được phân biệt với lỗi của tác vụ phát sinh **sau khi đã được nhận để chạy**.

### 2.3. Bốn hành vi không giống nhau

| Cách gọi | Ai quyết định luồng thực thi? | Bên gửi nhận gì? | Khi nào nên dùng? |
|---|---|---|---|
| `task.run()` | Chính luồng gọi | `void` | Muốn gọi tác vụ như một phương thức thông thường |
| `new Thread(task).start()` | JVM khởi chạy thread đã tạo | `void` | Cần quản lý một thread cụ thể ở mức thấp |
| `executor.execute(task)` | Triển khai `Executor` | `void` | Muốn tách gửi việc khỏi chính sách thực thi |
| `executorService.submit(task)` | `ExecutorService` | `Future<?>` | Cần theo dõi hoàn tất, lỗi, hủy hoặc chờ |

**Khác biệt chính của bài này:** `execute()` giao một `Runnable` theo hợp đồng đơn giản nhất; nó **không cung cấp kênh lấy kết quả hoàn tất**. Nếu người gọi thật sự cần biết task xong hay lỗi, hãy thiết kế cơ chế báo hiệu hoặc chọn `submit` khi thích hợp. Không nên tạo `Future` trong đầu rồi giả định `execute` đã tự cấp một cái.

## 3. Đường đi của một tác vụ sau execute()

Mô hình khi executor dùng pool:

```text
Luồng gửi (caller)
     |
     | tạo Runnable
     |
     +--> execute(task)
             |
             v
      Executor / TaskExecutor
             |
             +--> Có worker phù hợp -> chạy run()
             |
             +--> Worker đang bận -> xếp hàng (nếu còn chỗ)
             |
             +--> Không nhận thêm -> rejection
             |
             v
       execute() có thể đã trả về ở caller
             |
             ... một thời điểm khác ...
             v
           task.run()
             |
             +--> thực hiện thành công
             |
             +--> ném ngoại lệ
```

Chú ý chữ “có thể”: một executor trực tiếp không có hàng đợi và chạy `run()` trước khi `execute()` trở về. Java không yêu cầu mọi executor tạo thread mới.

Lời gọi `execute` trả về bình thường **chỉ cho biết executor không báo lỗi ngay cho lời gọi đó**. Nó không bảo đảm rằng mọi tác động bên trong task đã thành công. Với một số `RejectedExecutionHandler` như `DiscardPolicy`, thậm chí có thể bỏ task khi quá tải mà không ném ngoại lệ. Vì vậy kết luận “task đã được thực thi” từ việc `execute` trả về chỉ hợp lý khi đã biết rõ chính sách của executor cụ thể.

Không có bảo đảm chung rằng các tác vụ được xử lý đúng thứ tự gửi: điều này phụ thuộc executor, cấu trúc hàng đợi, số worker và lịch chạy. Trong một pool nhiều worker, thứ tự bắt đầu, kết thúc và ghi log có thể khác nhau.

## 4. Ví dụ Java 17 độc lập: trực tiếp và qua worker pool

Ví dụ này chứng minh cùng một lời gọi `execute` có thể chạy trên `main` hoặc trên worker thread. `CountDownLatch` làm thứ tự in ra có thể dự đoán, không cần ngủ để đoán task đã xong.

**Tệp `ExecuteRunnableDemo.java`:**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

public class ExecuteRunnableDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Executor direct = Runnable::run;

        direct.execute(() -> System.out.println(
                "Trực tiếp: " + Thread.currentThread().getName()));

        ThreadFactory namedThread = task ->
                new Thread(task, "background-worker");

        ExecutorService pool =
                Executors.newSingleThreadExecutor(namedThread);

        CountDownLatch finished = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                try {
                    System.out.println("Trong pool: "
                            + Thread.currentThread().getName());
                } finally {
                    finished.countDown();
                }
            });

            finished.await();
            System.out.println("Caller xác nhận đã hoàn tất");
        } finally {
            pool.shutdown();
        }
    }
}
```

**Biên dịch và chạy (JDK 17+):**

```bash
javac ExecuteRunnableDemo.java
java ExecuteRunnableDemo
```

**Đầu ra xác định:**

```text
Trực tiếp: main
Trong pool: background-worker
Caller xác nhận đã hoàn tất
```

Giải thích:

1. `Executor direct = Runnable::run` tạo executor có triển khai tương đương `command.run()`. Nó chạy **ngay trên main** và trở về khi lambda hoàn tất.
2. `Executors.newSingleThreadExecutor(...)` dùng một worker do factory tạo ra, tên `background-worker`. Code tạo task không cần biết chi tiết pool.
3. `pool.execute(...)` trả về `void`. Bản thân nó không tạo ra giá trị “thành công”.
4. Task gọi `finished.countDown()` trong `finally`; `finished.await()` chỉ cho caller đi tiếp sau tín hiệu đó.
5. `pool.shutdown()` là trách nhiệm của code đã tạo pool. Nó ngừng nhận việc mới; riêng `shutdown()` không phải lệnh chờ hoàn tất.
6. Hai dòng đầu xuất hiện trước dòng cuối: direct chạy trước, còn pool task phải báo `finished` trước khi main in dòng xác nhận.

Trong ví dụ trên, `CountDownLatch` đóng vai trò **kênh hoàn tất được thiết kế thêm**, không phải thứ `execute()` trả về. Nếu ứng dụng không cần chờ, có thể bỏ latch; nhưng khi ấy không được công bố rằng task đã hoàn tất ngay sau `execute`.

**Không nhầm với:**

```java
Runnable task = () -> System.out.println("Chạy trên caller");
task.run();  // Một lời gọi phương thức; không tạo thread.
```

## 5. Tích hợp Spring: cấu hình TaskExecutor có giới hạn

Trong Spring Framework, một lựa chọn phổ biến cho ứng dụng tự quản lý pool là `ThreadPoolTaskExecutor`. Lớp này triển khai `TaskExecutor`, dựa trên `ThreadPoolExecutor` của Java và hỗ trợ cấu hình số worker, hàng đợi, tên thread và xử lý từ chối.

**Tệp `BackgroundExecutorConfig.java` — một class cấu hình Spring, không có `main` độc lập:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BackgroundExecutorConfig {

    @Bean("backgroundTaskExecutor")
    public ThreadPoolTaskExecutor backgroundTaskExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("background-");

        return executor;
    }
}
```

Phân tích:

- `corePoolSize=2`: khi cần, executor tạo tới hai worker lõi trước khi ưu tiên queue.
- `maxPoolSize=4`: giới hạn số worker tối đa là bốn. Với `ThreadPoolExecutor`, sau core, việc thường được đưa vào queue trước; khi queue không nhận thêm mới cân nhắc tăng worker đến max.
- `queueCapacity=32`: giới hạn tối đa 32 tác vụ đang chờ trong queue của pool, **không phải** 32 tác vụ đang chạy.
- `threadNamePrefix` giúp đọc log và thread dump.
- Bean do Spring quản lý nên việc khởi tạo và đóng executor đi theo lifecycle của `ApplicationContext` theo cấu hình Spring.

Ví dụ dùng `ThreadPoolTaskExecutor` để dạy hợp đồng gửi việc; **các con số 2/4/32 chỉ là giả định**. Trong production cần chọn theo độ trễ, bộ nhớ mỗi tác vụ, tải đến, downstream và chính sách từ chối. Một queue quá lớn có thể làm thời gian chờ và lượng heap giữ lại tăng mạnh.

### 5.1. Dùng TaskExecutor trong một service

**Tệp `EventDispatchService.java` — Spring component, cần dependency Spring và context:**

```java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class EventDispatchService {
    private final TaskExecutor executor;
    private final AtomicInteger processed = new AtomicInteger();

    public EventDispatchService(
            @Qualifier("backgroundTaskExecutor")
            TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String eventId) {
        String id = Objects.requireNonNull(eventId, "eventId");

        executor.execute(() -> {
            // Công việc minh họa: ghi nhận một sự kiện đã được xử lý.
            processed.incrementAndGet();
            System.out.println("Đã xử lý sự kiện: " + id);
        });
    }

    public int processedCount() {
        return processed.get();
    }
}
```

Mã này minh họa một bean Spring dùng executor với **constructor injection**. Không cần `@EnableAsync` chỉ để gọi `TaskExecutor.execute(...)` trực tiếp: `@EnableAsync` dùng cho cơ chế xử lý `@Async`.

`dispatch` trả `void` sau lời gọi `execute`. Nếu pool bất đồng bộ, một lời gọi `processedCount()` ngay sau `dispatch` **có thể chưa thấy tác vụ vừa gửi**. `AtomicInteger` làm phép tăng an toàn khi nhiều worker cùng cập nhật, nhưng không buộc task hoàn tất trước khi caller đọc; hai vấn đề **an toàn dữ liệu** và **chờ hoàn tất** là khác nhau.

`System.out.println(...)` chỉ giúp quan sát ví dụ, không phải cơ chế audit đáng tin cậy. Nếu nghiệp vụ cần bảo đảm sự kiện không bị mất khi JVM chết, gửi vào in-memory executor chưa đủ; cần lưu công việc bền vững, xử lý retry/idempotency và một cơ chế tiếp nhận có xác nhận theo yêu cầu.

### 5.2. Lời gọi từ controller có thể trả trước task

Ví dụ controller chỉ nhận yêu cầu gửi việc:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EventController {
    private final EventDispatchService dispatchService;

    public EventController(EventDispatchService dispatchService) {
        this.dispatchService = dispatchService;
    }

    @PostMapping("/events/{id}/dispatch")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public void dispatch(@PathVariable String id) {
        dispatchService.dispatch(id);
    }
}
```

Đây là thành phần **Spring Web**, không phải mã Java SE chạy độc lập. Mã này dùng HTTP `202 Accepted` để biểu đạt rằng thao tác gửi đã được thực hiện ở tầng ứng dụng khi không có lỗi đồng bộ. **202 không chứng minh task nền đã thành công**, không cam kết có lưu trữ bền vững, và cũng không có cách truy vấn trạng thái job trong ví dụ. Đối với API sản xuất cần trạng thái công việc, phải thiết kế ID và kho lưu trạng thái riêng.

Nếu executor từ chối tác vụ và `TaskRejectedException` lan lên từ `dispatch`, request không nên vẫn được trả 202. Cần xử lý ngoại lệ ở tầng web để trả một phản hồi phù hợp, chẳng hạn 503 hoặc 429 theo hợp đồng API. Không nuốt rejection rồi giả vờ đã nhận việc.

## 6. Không trả kết quả không có nghĩa không cần xử lý lỗi

Có hai thời điểm lỗi riêng:

### 6.1. Lỗi khi gửi: task chưa được nhận

`ThreadPoolTaskExecutor` có thể từ chối khi pool đã đóng hoặc đã đạt giới hạn worker và queue. Với chính sách mặc định, Spring báo `TaskRejectedException` theo hợp đồng `TaskExecutor`.

```java
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;

// Đoạn đặt trong một phương thức có biến executor và eventId:
try {
    executor.execute(() ->
            System.out.println("Xử lý: " + eventId));
} catch (TaskRejectedException rejected) {
    // Đẩy lỗi lên tầng có quyền trả trạng thái quá tải/retry.
    throw rejected;
}
```

Đoạn này chỉ minh họa **vị trí bắt lỗi đồng bộ**. Việc bắt rồi ném lại là hợp lệ nếu muốn bổ sung log/metrics trước khi lan lỗi; nếu không làm gì khác, không cần khối `try/catch` này. Không nên giả định mọi rejection policy đều ném ngoại lệ: `DiscardPolicy` có thể bỏ tác vụ, còn `CallerRunsPolicy` có thể khiến chính luồng gửi chạy tác vụ khi executor chưa đóng.

### 6.2. Lỗi khi task đã chạy: không có Future để lấy

`Runnable.run()` không khai báo checked exception, nhưng runtime exception vẫn có thể phát sinh trong nội dung:

```java
executor.execute(() -> {
    throw new IllegalStateException("Không xử lý được");
});
```

Nếu `executor` là executor đồng bộ, lỗi có thể ném ngược lại trong cùng lời gọi `execute`. Nếu `executor` là worker pool bất đồng bộ, caller thường đã rời khỏi phương thức gửi; không có `Future.get()` để báo lỗi này cho caller. Với `ThreadPoolExecutor.execute(...)` mặc định, runtime exception không được xử lý có thể làm worker kết thúc bất thường và đi qua `UncaughtExceptionHandler`; cách hiển thị log phụ thuộc thread factory, runtime và cơ chế giám sát.

Không nên viết unit test chỉ bắt exception ngay quanh `execute` rồi nghĩ đã bao phủ lỗi trong một worker bất đồng bộ.

**Mẫu xử lý lỗi ngay trong tác vụ** khi có một kênh giám sát phù hợp:

```java
executor.execute(() -> {
    try {
        processEvent(eventId);
    } catch (RuntimeException failure) {
        reportFailure(eventId, failure);
    }
});
```

Đây là **mảnh mã đặt trong class nghiệp vụ** đã có `processEvent(...)` và `reportFailure(...)`; không phải chương trình độc lập. `reportFailure` phải thực sự xử lý được việc ghi nhận lỗi, ví dụ metrics/log có cấu trúc hoặc kho trạng thái công việc. Nếu tác vụ có side effect nguy hiểm, cần quyết định có retry được không và tránh thực hiện trùng.

**Đặc biệt:** Đừng bắt `Throwable` rồi lặng lẽ bỏ qua mọi lỗi. Những lỗi nghiêm trọng ở mức JVM có thể cần để hệ thống giám sát hoặc xử lý theo chính sách. Với `InterruptedException` trong logic chặn, nên kết thúc tác vụ hoặc truyền tín hiệu phù hợp; khi bắt mà không ném tiếp, thường khôi phục bằng `Thread.currentThread().interrupt()`.

## 7. Java 17: quan sát queue đầy và execute() bị từ chối

Ví dụ sau dùng Java SE để mô tả trường hợp `execute` không chấp nhận thêm tác vụ. Nó có **một worker**, queue dung lượng **một**, và latch giữ worker đang bận trong lúc ta gửi các task còn lại. Vì vậy kết quả in ra không phụ thuộc tốc độ máy.

**Tệp `ExecuteRejectionDemo.java`:**

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ExecuteRejectionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());

        try {
            executor.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await();

            executor.execute(() -> {});
            System.out.println("Số tác vụ chờ: "
                    + executor.getQueue().size());

            try {
                executor.execute(() -> {});
                System.out.println("Không mong đợi nhận thêm tác vụ");
            } catch (RejectedExecutionException rejected) {
                System.out.println("Tác vụ thứ ba bị từ chối");
            }
        } finally {
            release.countDown();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ExecuteRejectionDemo.java
java ExecuteRejectionDemo
```

Đầu ra chính xác:

```text
Số tác vụ chờ: 1
Tác vụ thứ ba bị từ chối
```

Tại sao chắc chắn? `started.await()` đợi task đầu tiên đã chiếm worker. Task đó phải đợi `release`, nên worker chưa lấy task thứ hai khỏi queue. `ArrayBlockingQueue<>(1)` chỉ cho một task chờ. Task thứ ba không thể chạy và không còn chỗ chờ, nên `AbortPolicy` ném `RejectedExecutionException` ngay ở caller.

**Phân biệt exception:** Trong ví dụ Java `ThreadPoolExecutor` trực tiếp, kiểu bị bắt là `RejectedExecutionException`. Trong `ThreadPoolTaskExecutor` của Spring, hợp đồng báo từ chối thường là `TaskRejectedException` (một dạng lỗi từ chối do Spring sử dụng). Cách chuyển đổi và xử lý phụ thuộc implementation/policy được chọn; không nên gộp mọi lỗi của task với lỗi từ chối khi gửi.

Ở môi trường thật, `getQueue().size()` thay đổi liên tục; dùng nó để quan sát tải, không xem nó là bảo đảm tuyệt đối cho quyết định nghiệp vụ ở luồng khác. Mẫu trên giữ worker có kiểm soát để minh họa tình huống hoàn toàn xác định.

## 8. Khi nào không nên dùng execute() một mình?

`execute` thích hợp nếu code gọi thực sự **không cần nhận kết quả tác vụ**. Nhưng “không trả dữ liệu” khác với “không cần biết đã hoàn tất”. Có ba loại nhu cầu:

| Nhu cầu | Cách phù hợp | Lưu ý |
|---|---|---|
| Gửi một tác vụ độc lập, không cần phản hồi giá trị | `TaskExecutor.execute(Runnable)` | Thiết kế xử lý lỗi, quá tải và vòng đời riêng |
| Tác vụ không trả giá trị nhưng caller phải biết khi nào xong/lỗi | `ExecutorService.submit(Runnable)` hoặc `AsyncTaskExecutor.submit(Runnable)` để nhận `Future<?>` | `get()` có thể chặn; phải xử lý `ExecutionException`/hủy |
| Tác vụ tạo ra kết quả thuộc kiểu `T` | `Callable<T>` + `submit`, hoặc API bất đồng bộ phù hợp | Có kết quả và đường xử lý ngoại lệ |
| Phối hợp nhiều bước bất đồng bộ và kết quả | `CompletableFuture` hoặc cơ chế orchestration | Cần cấu hình executor cho các bước chạy bất đồng bộ |
| Công việc phải sống qua crash/restart | Hàng đợi bền vững, cơ sở dữ liệu, cơ chế job chuyên dụng | Pool trong heap không tự bảo đảm giao việc bền vững |

Với `submit(Runnable)`, `Future.get()` trả `null` nếu tác vụ hoàn thành bình thường; lỗi tác vụ thường được bọc vào `ExecutionException`. `execute(Runnable)` không cung cấp `Future` tương ứng. Đây là **phân biệt API**, không có nghĩa `submit` sẽ tự bảo đảm task hoàn tất khi ứng dụng dừng hoặc hệ thống lỗi.

Nếu chỉ cần đếm task thành công hoặc ghi status, có thể đặt kênh quan sát trong thân `Runnable` và dùng cấu trúc an toàn luồng. Nhưng khi caller cần tính đúng đắn dựa trên trạng thái đó, vẫn phải phối hợp thời điểm đọc qua latch, Future, callback hoặc một điều kiện đồng bộ thích hợp.

## 9. Quan sát hoàn tất mà vẫn dùng execute()

Đôi khi kiến trúc yêu cầu chỉ phụ thuộc `Executor`, nhưng một bài kiểm thử hoặc bước điều phối vẫn cần biết lúc nào task kết thúc. Có thể truyền riêng `CountDownLatch` hoặc một callback để phát tín hiệu. Ví dụ sau cũng chứng minh `execute` không trả kết quả.

**Tệp `ExecuteCompletionDemo.java`:**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class ExecuteCompletionDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ExecutorService owner = Executors.newFixedThreadPool(2);
        Executor executor = owner;
        AtomicInteger completed = new AtomicInteger();
        CountDownLatch done = new CountDownLatch(3);

        try {
            for (int i = 0; i < 3; i++) {
                executor.execute(() -> {
                    try {
                        completed.incrementAndGet();
                    } finally {
                        done.countDown();
                    }
                });
            }

            done.await();
            System.out.println("Đã hoàn tất: " + completed.get());
        } finally {
            owner.shutdown();
        }
    }
}
```

Lệnh chạy:

```bash
javac ExecuteCompletionDemo.java
java ExecuteCompletionDemo
```

Kết quả:

```text
Đã hoàn tất: 3
```

Mặc dù pool có hai worker và thứ tự ba tác vụ không xác định, `AtomicInteger` bảo vệ phép tăng khỏi mất cập nhật và `CountDownLatch` chỉ mở cho main khi cả ba lần `countDown()` đã xảy ra. Thứ tự in dòng cuối vì thế xác định.

**Cảnh báo về ý nghĩa số liệu:** `completed` ở đây thực chất là **số task đã thực hiện phép tăng**, không phải một cơ chế bảo đảm tác động nghiệp vụ bên ngoài thành công. Đặt tên counter theo mốc mà chương trình thực sự kiểm tra (submitted, started, succeeded, failed); không đánh đồng task đã nhận với task đã hoàn tất thành công.

Nếu cần phản hồi lỗi khi chờ, latch đơn thuần chưa đủ; phải thêm một kênh chứa lỗi an toàn luồng hoặc chuyển sang `Future`/`CompletableFuture`. Nếu có thể xảy ra mất task, phải thiết kế timeout cho việc chờ thay vì chờ vô hạn.

## 10. Đồng thời không tự làm bean singleton an toàn luồng

Spring bean singleton thường được nhiều request gọi đồng thời. Khi một bean gửi nhiều `Runnable` vào pool, các tác vụ có thể cùng đọc hoặc ghi các trường của bean đó.

**Ví dụ nguy hiểm:**

```java
private int count;

void dispatch(TaskExecutor executor) {
    executor.execute(() -> count++);
}
```

Đây là **mảnh code minh họa lỗi** đặt trong một class. `count++` gồm thao tác đọc, tính và ghi; nhiều worker có thể cùng thấy giá trị cũ và làm mất cập nhật. Việc dùng `execute` không tạo đồng bộ tự động.

Một phương án khi chỉ cần đếm độc lập:

```java
private final AtomicInteger count = new AtomicInteger();

void dispatch(TaskExecutor executor) {
    executor.execute(count::incrementAndGet);
}
```

Đây là đoạn mã minh họa trong một class với import `java.util.concurrent.atomic.AtomicInteger` và `org.springframework.core.task.TaskExecutor`. Nếu cần bảo vệ nhiều trường có bất biến chung, một kiểu atomic riêng lẻ có thể chưa đủ; cân nhắc khóa ngắn, snapshot bất biến hoặc thay đổi cấu trúc dữ liệu. Không nên giữ khóa của bean trong thời gian gọi I/O chậm chỉ để thực hiện một cập nhật nhanh.

**Cũng không mặc định ThreadLocal được truyền theo.** Với thread pool, worker có thể được tái sử dụng giữa các task. Các giá trị `ThreadLocal`, ngữ cảnh request, MDC hoặc `SecurityContextHolder` từ luồng gửi không tự động được sao chép chính xác cho mọi executor. Nếu cần correlation ID hay tenant ID, truyền tham số bất biến hoặc cấu hình cơ chế truyền ngữ cảnh phù hợp và kiểm tra việc dọn context sau mỗi task.

## 11. execute() và ranh giới transaction trong Spring

Một task chạy trên thread khác **không tự tiếp tục transaction** của luồng gửi. Ví dụ:

```text
Thread request:
  bắt đầu @Transactional
  ghi dữ liệu chưa commit
  execute(runnable)
  kết thúc transaction

Worker:
  có thể chạy trước hoặc sau commit
  không tự tham gia transaction của caller
```

Nếu task đọc một bản ghi vừa được sửa nhưng chưa commit, kết quả phụ thuộc isolation và thời điểm thực thi; không nên giả định nó sẽ thấy bản ghi mới. Với hành động chỉ được thực hiện sau khi transaction thành công, cân nhắc sự kiện xử lý sau commit, outbox hoặc cơ chế chuyển việc có tính bền vững. Nếu task tự cần transaction, mở một ranh giới transaction riêng qua thành phần Spring được quản lý phù hợp.

**Không dùng `execute()` như cách “chuyển” an toàn một `EntityManager`, JDBC connection hoặc đối tượng request còn sống sang thread khác.** Những tài nguyên này có vòng đời, chính sách thread-safety và quyền sở hữu riêng.

## 12. Quản lý vòng đời và khả năng chịu tải

Khi tự tạo `ExecutorService` bằng `Executors` trong Java SE, code sở hữu pool phải chịu trách nhiệm `shutdown()` và chờ kết thúc theo chính sách. Trong Spring, nếu `ThreadPoolTaskExecutor` được đăng ký làm bean thông thường, Spring quản lý khởi tạo và đóng theo `ApplicationContext`.

Một số điểm thực tế:

- Tránh `new Thread(...)` hoặc `Executors.newFixedThreadPool(...)` trong mỗi request; tạo quá nhiều thread/pool và khó dọn dẹp.
- Tránh queue gần như vô hạn nếu task có thể tăng nhanh hơn khả năng xử lý; nó có thể giữ rất nhiều đối tượng trong heap.
- Cấu hình giới hạn số worker, queue và chính sách rejection đồng bộ với yêu cầu độ trễ và bộ nhớ.
- Chọn chính sách khi application đóng: chờ tác vụ đã nhận, từ chối task mới, hoặc yêu cầu hủy theo nhu cầu. Các thuộc tính lifecycle của Spring phụ thuộc phiên bản/cấu hình; kiểm tra tài liệu phiên bản đang dùng.
- Không tự gọi `shutdown()` trên một executor chung do Spring hoặc application server quản lý nếu service không phải owner.
- Không nhầm `TaskExecutor.execute(...)` với hệ thống job bền vững: JVM crash/redeploy có thể làm mất tác vụ chưa hoàn tất.

### 12.1. Nếu executor từ chối, caller nên làm gì?

Một API đồng bộ có thể ánh xạ rejection sang lỗi quá tải có chủ đích; một consumer có thể giảm tốc độ nhận; một tác vụ quan trọng có thể được đưa vào hàng đợi bền vững nếu thiết kế cho phép. Không có một chính sách phù hợp cho mọi trường hợp.

Với `CallerRunsPolicy` của `ThreadPoolExecutor`, nếu pool chưa đóng, task bị từ chối theo đường worker/queue có thể chạy ngay trên **thread gửi**. Điều này tạo áp lực ngược nhưng có thể làm request chậm hoặc khiến exception của task lan lên caller. Với `DiscardPolicy`, công việc có thể bị bỏ im lặng. Vì vậy phải xác minh chính sách thực tế trước khi diễn giải “`execute` trả bình thường”.

## 13. Thiết kế xử lý lỗi và khả năng quan sát cho task không có kết quả

Khi task không trả một giá trị, nên xác định rõ **bằng chứng nào đánh dấu thành công**. Tối thiểu, có thể quan sát ba thời điểm:

1. **Đã nhận để xử lý (`accepted`):** `execute` không báo lỗi trong chính sách nhận việc đã chọn.
2. **Đã bắt đầu (`started`):** task thật sự được worker/caller gọi `run()`.
3. **Đã hoàn tất thành công (`succeeded`) hoặc thất bại (`failed`):** logic nghiệp vụ đã đạt kết quả hoặc có ngoại lệ.

Các chỉ số nên tách biệt:

| Chỉ số | Diễn giải |
|---|---|
| `tasks.submitted` | Số lần caller cố gửi việc |
| `tasks.rejected` | Số việc bị từ chối theo policy có thể quan sát |
| `tasks.started` | Số task bước vào `run()` |
| `tasks.succeeded` | Số task hoàn tất nghiệp vụ thành công |
| `tasks.failed` | Số task lỗi |
| `queue.depth` | Số việc còn đợi trong queue |
| `executor.active` | Số worker hiện bận |
| `task.queue.wait` | Thời gian từ tiếp nhận đến bắt đầu |
| `task.run.duration` | Thời gian task thực thi |

Trong Spring, `ThreadPoolTaskExecutor` có các phương thức quan sát như `getActiveCount()`, `getPoolSize()`, `getQueueSize()` theo phiên bản Spring phù hợp. Các giá trị là số liệu tại thời điểm quan sát, không bảo đảm một ảnh chụp nguyên tử của cả hệ thống.

Nếu dùng `TaskDecorator` để ghi context hoặc đo thời gian, phải nhớ decorator có thể bao quanh một `Runnable` đã được framework bọc; cách lỗi xuất hiện khác nhau với `execute` và `submit`. Cần kiểm chứng trong đúng phiên bản Spring và chọn một nơi đáng tin để ghi lỗi của task.

### 13.1. Ghi nhận dữ liệu tối thiểu, tránh giữ cả request

Lambda có thể vô tình capture nguyên một request object, input stream, session hoặc đồ thị dữ liệu lớn; nếu queue còn nhiều việc chờ, chúng vẫn bị giữ trong heap. Thay vào đó, ưu tiên dữ liệu bất biến đủ dùng như ID, checksum hoặc bản sao nhỏ của các tham số.

Đối với task gửi email/thanh toán/ghi cơ sở dữ liệu, vấn đề quan trọng không chỉ là memory: cần xác định idempotency, thời điểm xác nhận cho caller, retry có giới hạn và quyền thao tác của worker. Một lệnh `execute` không tự giải quyết được các điều kiện đó.

## 14. Cách kiểm thử execute() cho đúng

Vì `execute` trả `void`, một unit test viết như sau thường sai mục đích:

```java
service.dispatch("A-1");
// Sai kỳ vọng nếu dùng pool: công việc có thể chưa chạy.
assertEquals(1, service.processedCount());
```

Đây là **mảnh kiểm thử minh họa**, không phải class độc lập; `assertEquals` thuộc framework kiểm thử. Với pool thật, kết quả phụ thuộc lịch chạy.

Có hai cách kiểm thử tùy mục tiêu:

**Kiểm thử logic tác vụ đồng bộ:** inject `SyncTaskExecutor` của Spring. Nó gọi task ngay trên luồng kiểm thử, giúp kết quả ổn định. Đây là lựa chọn tốt khi chỉ cần biết service đã tạo và gửi đúng logic, không cần kiểm tra thread thật.

```java
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.SyncTaskExecutor;

// Đặt trong mã kiểm thử/tạo đối tượng service phù hợp.
TaskExecutor direct = new SyncTaskExecutor();
direct.execute(() -> System.out.println("Kiểm thử đồng bộ"));
```

**Kiểm thử tích hợp thực thi bất đồng bộ:** dùng latch, Future (nếu API cung cấp), callback hoặc một điều kiện có timeout để chờ mốc hoàn tất; không dùng `Thread.sleep(100)` rồi hy vọng worker đã xử lý xong.

Kiểm thử nên bao phủ tối thiểu: task thành công, task lỗi, executor từ chối, task bị hủy hoặc ứng dụng đóng khi còn việc, và tính đúng đắn của trạng thái chia sẻ. Đặc biệt, hãy kiểm tra hành vi API khi `dispatch` trả về trước khi task hoàn tất.

## 15. Những nhầm lẫn phổ biến

| Nhầm lẫn | Thực tế | Cách sửa tư duy |
|---|---|---|
| `execute()` luôn tạo thread mới | Executor có thể chạy trực tiếp, trong pool hoặc theo chiến lược khác | Kiểm tra implementation |
| `execute()` trả về là task đã hoàn tất | Với async pool, task có thể còn chờ hoặc đang chạy | Phân biệt accepted/started/succeeded |
| `Runnable` không thể thất bại vì `run()` trả `void` | Runtime exception vẫn có thể phát sinh | Thiết kế quan sát và xử lý lỗi |
| Bắt exception quanh `execute` là đủ | Không bắt được mọi lỗi xảy ra sau trên worker | Xử lý bên trong task hoặc qua kênh giám sát |
| `execute()` tự cấp `Future` | Hợp đồng trả `void` | Dùng `submit` nếu cần Future |
| Cần `@EnableAsync` để dùng `TaskExecutor.execute` | `execute` là lời gọi trực tiếp; `@EnableAsync` phục vụ `@Async` | Chọn cơ chế đúng mục đích |
| Gửi task bằng pool thì trường singleton an toàn luồng | Nhiều worker có thể sửa cùng biến | Atomic, lock ngắn, dữ liệu bất biến |
| `ThreadLocal`/transaction tự theo task | Context thường gắn với luồng; chuyển thread không tự sao chép | Truyền dữ liệu cần thiết, tạo transaction riêng |
| Bỏ qua `TaskRejectedException` | Có thể báo nhận việc sai hoặc mất task | Xử lý quá tải ở ranh giới người gọi |
| Queue lớn đảm bảo không mất việc | Queue trong heap không bền vững; có thể OOM | Giới hạn queue, backpressure, lưu bền vững nếu cần |
| Đặt `shutdown()` sau từng `execute` trên bean chung | Pool bị đóng, các request khác không thể gửi việc | Để owner quản lý lifecycle |
| Dùng `Thread.sleep` để kiểm thử xong việc | Thời gian chạy thay đổi theo máy/tải | Latch/Future/điều kiện có timeout |

## 16. Bài tập thực hành

### Bài 1 — Cùng task, hai executor

Viết một `Runnable` in tên thread. Gửi bằng `Runnable::run` và bằng `Executors.newSingleThreadExecutor(...)`. Giải thích tại sao kết quả có thể khác mặc dù chỗ gọi đều là `execute`.

**Định hướng:** Executor trực tiếp thực thi `run()` trong caller, còn pool có worker riêng; contract `execute` không quyết định tên/loại thread.

### Bài 2 — Không có Future

Cho lời gọi `executor.execute(task)`. Làm thế nào để caller biết task đã hoàn tất nếu không thay đổi API executor? Vì sao chỉ dùng `execute` và kiểm tra một biến `boolean` thường là chưa đủ?

**Định hướng:** Dùng latch/callback/đối tượng trạng thái an toàn luồng với quy tắc đồng bộ phù hợp. Biến boolean thường có thể gặp vấn đề visibility và timing; ngay cả `volatile` cũng chưa tự cung cấp chờ hoặc xử lý lỗi.

### Bài 3 — Phân biệt hai loại lỗi

Pool đã đầy và ném `TaskRejectedException` khi gửi A. Task B đã được nhận nhưng ném `IllegalStateException` sau khi chạy trên worker. Hai lỗi xuất hiện ở đâu? Vì sao một `try/catch` quanh `execute(B)` chưa chắc bắt được lỗi B?

**Định hướng:** Rejection xảy ra đồng bộ ở caller; lỗi runtime của B ở luồng thực thi. Không có `Future` từ `execute` để quan sát B tự động.

### Bài 4 — Thử nghiệm rejection Java 17

Chạy `ExecuteRejectionDemo.java`. Giữ số worker là 1, tăng queue từ 1 lên 2 rồi gửi thêm một task. Khi worker vẫn chờ latch, task thứ mấy bị từ chối?

**Định hướng:** Một task đang chạy, hai task được xếp hàng; task thứ tư bị từ chối nếu `AbortPolicy` đang dùng.

### Bài 5 — Chọn đúng API

Một service A gửi cập nhật dữ liệu không cần trả giá trị cho caller; service B cần nhận `Integer` từ tính toán; service C không cần giá trị nhưng bắt buộc biết công việc đã thành công trước khi commit một bước khác. Chọn `execute` hay `submit` cho từng trường hợp và giải thích.

**Định hướng:** A có thể dùng `execute` với cơ chế lỗi phù hợp; B cần `Callable<Integer>` và API trả kết quả; C cần kênh hoàn tất/lỗi như `Future` hoặc thiết kế orchestration rõ ràng, không chỉ `execute`.

### Bài 6 — Tình huống Spring thực tế

Một controller trả HTTP 202 ngay sau `eventDispatchService.dispatch(id)`. Pool vừa nhận task nhưng process chết trước khi worker thực hiện. Client có cơ sở nào để khẳng định sự kiện đã được xử lý hoặc sẽ chắc chắn được xử lý?

**Định hướng:** Không. 202 trong ví dụ chỉ xác nhận thao tác gửi ở thời điểm đó; cần lưu bền vững, ID công việc và cơ chế theo dõi nếu muốn cam kết khác.

## 17. Quy trình sử dụng trong dự án

Khi có nhu cầu gửi một `Runnable` không trả kết quả, kiểm tra theo thứ tự:

1. **Mục đích:** Có thật sự không cần giá trị, kết quả thành công hay phản hồi lỗi cho caller? Nếu cần, xem lại lựa chọn `submit` hoặc API khác.
2. **Executor:** Xác định rõ bean `TaskExecutor` được inject; biết nó có chạy đồng bộ hay qua pool.
3. **Tài nguyên:** Đặt giới hạn worker/queue phù hợp; xử lý trường hợp quá tải và đóng ứng dụng.
4. **Tác vụ:** Viết logic có trách nhiệm, không capture dữ liệu request/transaction không phù hợp; bảo vệ trạng thái chung.
5. **Lỗi:** Phân biệt lỗi gửi và lỗi khi task chạy; có logging/metrics/retry đúng nghiệp vụ.
6. **Quan sát:** Nếu task quan trọng, xác định mốc accepted/started/succeeded, cách kiểm tra quá hạn và tác vụ mất.
7. **Kiểm thử:** Dùng direct executor để kiểm thử logic, dùng latch/điều kiện với timeout cho integration test và xác minh rejection.

## 18. Điều cần nhớ

- `Runnable` mô tả **việc làm** và `run()` trả `void`; `execute(Runnable)` là cách **gửi việc** tới `Executor` hoặc `TaskExecutor`.
- `execute()` **không trả `Future`, không truyền kết quả và không bảo đảm task đã hoàn tất**.
- **Đồng bộ hay bất đồng bộ phụ thuộc executor**: `SyncTaskExecutor` chạy ngay, `ThreadPoolTaskExecutor` dùng pool theo cấu hình.
- **Bắt lỗi đúng thời điểm**: rejection xảy ra ở đường gửi; lỗi trong worker cần một kênh ghi nhận riêng.
- **Trạng thái bean và tài nguyên vẫn phải được quản lý**: thread safety, giới hạn pool/queue, context, transaction, shutdown và tính bền vững của công việc.
- Khi cần biết chính xác đã xong hay lỗi, thiết kế tín hiệu hoàn tất phù hợp hoặc dùng API như `submit`.

### Tài liệu API chính thức

- [Java SE 17 — Runnable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runnable.html)
- [Java SE 17 — Executor.execute](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework — TaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
