# Runnable, Callable, Executor và ExecutorService

## 1. Bức tranh tổng thể: công việc khác với luồng thực thi

Khi viết chương trình Java, có hai câu hỏi khác nhau:

1. **Cần làm việc gì?** Ví dụ: xử lý một tệp, gọi dịch vụ bên ngoài, tính toán một báo cáo.
2. **Ai thực thi và quản lý việc đó?** Ví dụ: một luồng do ta tạo trực tiếp hoặc một nhóm luồng được tái sử dụng.

`Runnable` và `Callable` mô tả **tác vụ (task)**. `Executor` và `ExecutorService` mô tả **cơ chế thực thi tác vụ**. Tách hai vai trò này giúp tránh tạo `new Thread(...)` cho từng việc, quản lý tài nguyên tập trung, thu nhận kết quả và kết thúc chương trình có kiểm soát.

```text
Mã gọi (caller)
   |
   | tạo Runnable / Callable
   v
Tác vụ: "làm gì?"
   |
   | execute(...) / submit(...)
   v
Executor / ExecutorService: "chạy bằng cách nào?"
   |
   +--> worker thread 1
   +--> worker thread 2      (nếu dùng pool)
   +--> hàng đợi chờ xử lý
              |
              v
          Future<T>          (khi submit)
              |
              v
      kết quả / lỗi / hủy
```

Một tác vụ **không đồng nghĩa** một luồng: nhiều tác vụ có thể chạy lần lượt trên cùng một worker thread; ngược lại, nhiều tác vụ có thể chạy đồng thời trên các worker khác nhau. Và một `Executor` hoàn toàn có thể chạy tác vụ ngay trên luồng gọi, nên tên API không tự bảo đảm chạy bất đồng bộ.

Trong module Spring Framework về concurrency, đây là nền tảng để hiểu các cơ chế cao hơn như `TaskExecutor`, `ThreadPoolTaskExecutor` và `@Async`. Trước hết cần nắm chính xác hợp đồng của các API Java chuẩn.

### Mục tiêu của bài

Sau bài này, bạn có thể chọn đúng loại tác vụ, gửi tác vụ tới bộ thực thi, lấy kết quả hoặc ngoại lệ qua `Future`, xử lý ngắt/hủy, đóng bộ thực thi an toàn, và nhận ra các lỗi dễ gặp khi dùng thread pool.

## 2. Bốn giao diện cốt lõi

| Thành phần | Vai trò | Phương thức cốt lõi | Kết quả và ngoại lệ |
|---|---|---|---|
| `Runnable` | Mô tả việc cần chạy nhưng không trả về giá trị | `void run()` | Không khai báo checked exception từ `run()` |
| `Callable<V>` | Mô tả việc tính toán có kết quả | `V call() throws Exception` | Trả về `V`; có thể ném checked exception |
| `Executor` | Nhận `Runnable` và quyết định cách thực thi | `void execute(Runnable)` | Không trả về `Future`; không bắt buộc tạo luồng mới |
| `ExecutorService` | Mở rộng `Executor` bằng quản lý vòng đời và tác vụ có kết quả | `submit(...)`, `shutdown()`, `awaitTermination(...)` | Trả về `Future` từ `submit`; hỗ trợ hủy, chờ, đóng |

Quan hệ kiểu:

```text
Runnable       Callable<V>
    |               |
    +-- tác vụ -----+

Executor
   ^
   |
ExecutorService   (extends Executor)
   |
   +-- execute(Runnable)
   +-- submit(Runnable | Callable<V>)
   +-- shutdown / shutdownNow / awaitTermination
   +-- invokeAll / invokeAny
```

`ExecutorService` là **giao diện**. `Executors` (số nhiều) là **lớp tiện ích/factory** có các phương thức tạo bộ thực thi, chẳng hạn `Executors.newFixedThreadPool(2)`. Hai tên này rất dễ nhầm.

## 3. Runnable: tác vụ không cần trả về giá trị

`Runnable` là functional interface có một phương thức trừu tượng `run()`. Có thể triển khai bằng lớp thường, lớp ẩn danh hoặc lambda. Dùng khi hành vi tạo ra tác động phụ có chủ đích, như ghi log, cập nhật trạng thái hoặc gửi thông báo, và người gọi không cần một giá trị trả về từ `run()`.

Ví dụ độc lập, chạy được trên Java 17:

**Tệp `RunnableDemo.java`**

```java
public class RunnableDemo {
    public static void main(String[] args) throws InterruptedException {
        Runnable task = () ->
                System.out.println("Tác vụ chạy trên: "
                        + Thread.currentThread().getName());

        Thread worker = new Thread(task, "worker-1");
        worker.start();
        worker.join();

        System.out.println("Main đã đợi xong");
    }
}
```

Biên dịch và chạy:

```bash
javac RunnableDemo.java
java RunnableDemo
```

Kết quả chính xác:

```text
Tác vụ chạy trên: worker-1
Main đã đợi xong
```

Ở đây:

- `task` chỉ chứa hành vi. Tạo đối tượng `Runnable` **chưa** tạo luồng và **chưa** thực thi.
- `new Thread(task, "worker-1")` tạo đối tượng `Thread` gắn với tác vụ.
- `start()` yêu cầu JVM khởi chạy một luồng mới để gọi `run()`. Nếu gọi trực tiếp `task.run()` thì tác vụ chạy **đồng bộ trên luồng hiện tại**.
- `join()` chờ worker kết thúc; nhờ vậy dòng cuối luôn xuất hiện sau dòng do worker in ra. Không nên dùng `Thread.sleep(...)` để đoán khi nào tác vụ xong.

Giới hạn: chữ ký `run()` không có giá trị trả về và không khai báo `throws Exception`. Ta vẫn có thể xử lý checked exception *bên trong* `run()`, và runtime exception vẫn có thể phát sinh. Nếu cần kết quả tính toán hoặc muốn đưa lỗi checked exception tới phía gọi theo hợp đồng tác vụ, `Callable<V>` thích hợp hơn.

## 4. Callable<V>: tác vụ có kết quả và có thể báo lỗi

`Callable<V>` cũng là functional interface, nhưng `call()` trả về `V` và có thể khai báo `throws Exception`:

```java
import java.util.concurrent.Callable;

Callable<Integer> sum = () -> {
    int result = 0;
    for (int i = 1; i <= 5; i++) {
        result += i;
    }
    return result;
};
```

Đoạn trên là **một khai báo để đặt trong phương thức hoặc lớp phù hợp**, chưa phải chương trình độc lập. `Callable<Integer>` biểu diễn phép tính trả về `15`. `Thread` không có constructor nhận trực tiếp `Callable`; cách phổ biến là gửi `Callable` tới `ExecutorService.submit(...)` và lấy `Future<Integer>`.

Tham số kiểu có ý nghĩa: `Callable<String>` cho `Future<String>`; `Callable<Integer>` cho `Future<Integer>`. Bộ thực thi vẫn không biết công việc nghiệp vụ là gì; nó chỉ nhận tác vụ và bố trí chạy.

**Quy tắc chọn nhanh:** Nếu không cần giá trị thì bắt đầu bằng `Runnable`; nếu cần nhận kết quả hoặc biểu diễn lỗi checked exception từ tác vụ, chọn `Callable<V>`. Dù tác vụ là `Runnable`, `submit(Runnable)` vẫn cung cấp `Future<?>` để theo dõi hoàn tất hoặc lỗi.

## 5. Executor: tách nơi gửi công việc khỏi nơi chạy

`Executor` có đúng một phương thức trừu tượng:

```java
void execute(Runnable command);
```

Bên gọi yêu cầu “hãy thực thi tác vụ này”; bộ thực thi quyết định chạy ngay, tạo luồng hay xếp hàng. Hợp đồng `Executor` **không** cam kết tác vụ chạy bất đồng bộ hoặc có thread pool.

Ví dụ bộ thực thi chạy **ngay trên luồng gọi**:

**Tệp `ExecutorDemo.java`**

```java
import java.util.concurrent.Executor;

public class ExecutorDemo {
    public static void main(String[] args) {
        Executor inlineExecutor = Runnable::run;
        inlineExecutor.execute(() ->
                System.out.println("Tên luồng: "
                        + Thread.currentThread().getName()));
    }
}
```

```bash
javac ExecutorDemo.java
java ExecutorDemo
```

Kết quả:

```text
Tên luồng: main
```

Lệnh `Runnable::run` tạo một triển khai `Executor` thực hiện `command.run()` ngay trong luồng gọi. Điều này hữu ích khi minh họa hợp đồng hoặc viết kiểm thử đơn giản, nhưng không đem lại chạy song song. Một `Executor` khác có thể dùng worker pool mà không phải sửa code tạo tác vụ.

Phân biệt `execute` với `submit`:

- `execute(Runnable)` là phương thức của `Executor`; không trả về đối tượng theo dõi công việc.
- `submit(...)` do `ExecutorService` bổ sung; trả về `Future` để lấy kết quả, quan sát lỗi, chờ hoặc yêu cầu hủy.
- Cả hai có thể từ chối tác vụ mới, ví dụ khi bộ thực thi đã đóng; trường hợp phổ biến là `RejectedExecutionException`. Một số cách cấu hình pool còn có chính sách từ chối riêng.

## 6. ExecutorService: gửi việc, nhận Future và quản lý vòng đời

`ExecutorService` thường được hiện thực bằng thread pool, cho phép nhiều tác vụ chia sẻ một số worker. Ví dụ sau dùng factory `Executors.newFixedThreadPool(2)`.

**Tệp `ExecutorServiceDemo.java`**

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorServiceDemo {
    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Runnable greeting =
                    () -> System.out.println("Runnable hoàn thành");

            Callable<Integer> calculation = () -> {
                int sum = 0;
                for (int i = 1; i <= 5; i++) {
                    sum += i;
                }
                return sum;
            };

            Future<?> greetingDone = executor.submit(greeting);
            Future<Integer> result = executor.submit(calculation);

            greetingDone.get();
            System.out.println("Tổng = " + result.get());
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac ExecutorServiceDemo.java
java ExecutorServiceDemo
```

Kết quả luôn theo thứ tự:

```text
Runnable hoàn thành
Tổng = 15
```

Tác vụ `calculation` có thể chạy hoặc xong trước `greeting` vì pool có hai worker. Tuy nhiên, dòng “Tổng” chỉ được in sau khi `greetingDone.get()` trả về, nên thứ tự **hai dòng đầu ra** ở ví dụ này là xác định.

Ý nghĩa từng bước:

1. `newFixedThreadPool(2)` tạo một pool có tối đa hai worker hoạt động đồng thời; nếu tác vụ đến nhiều hơn khả năng xử lý, các tác vụ khác chờ trong hàng đợi.
2. `submit(greeting)` và `submit(calculation)` xếp lịch thực thi, trả về ngay `Future<?>` và `Future<Integer>`, trừ trường hợp bị từ chối hoặc có lỗi khi gửi.
3. `greetingDone.get()` chờ `Runnable` hoàn thành; nếu thành công, giá trị nhận được từ overload `submit(Runnable)` là `null`.
4. `result.get()` chờ và lấy giá trị `15`; nếu `calculation` ném ngoại lệ, `get()` ném `ExecutionException` thay cho giá trị.
5. `shutdown()` trong `finally` thông báo ngừng nhận việc mới và tiếp tục xử lý các việc đã được chấp nhận. Ở ví dụ này, cả hai việc đã hoàn tất trước khi tới `finally`.

Đừng quên rằng `ExecutorService` quản lý **nhiều tác vụ**, không phải “mỗi `submit` tạo một thread”. Cũng không nên dựa vào tên worker thread để xác định tác vụ nào sẽ chạy trước.

### Các overload submit thường dùng

| Cách gọi | Kiểu trả về | `Future.get()` khi hoàn tất bình thường |
|---|---|---|
| `submit(Runnable task)` | `Future<?>` | `null` |
| `submit(Runnable task, T result)` | `Future<T>` | Giá trị `result` đã cung cấp, không phải return từ `run()` |
| `submit(Callable<T> task)` | `Future<T>` | Giá trị mà `call()` trả về |

`submit(Runnable, result)` hữu ích khi cần đính kèm một kết quả định sẵn sau khi tác vụ không trả về giá trị hoàn thành thành công. Nó không thay thế `Callable` cho phép tính tạo kết quả mới.

## 7. Future: trạng thái, lỗi, chờ và hủy

`Future<T>` là **tay cầm (handle)** đại diện cho kết quả của một tác vụ đã gửi; nó không phải bản thân tác vụ hay một thread.

- `get()` chặn luồng gọi cho đến khi xong, bị hủy hoặc thất bại. Kết quả thành công là `T`; tác vụ thất bại dẫn đến `ExecutionException` (nguyên nhân gốc nằm ở `getCause()`); tác vụ bị hủy dẫn đến `CancellationException`.
- `get(timeout, unit)` chỉ chờ tối đa khoảng thời gian chỉ định; hết thời gian ném `TimeoutException`. **Hết thời gian chờ không tự động hủy tác vụ**.
- `isDone()` đúng khi tác vụ đã hoàn tất bình thường, thất bại **hoặc bị hủy**. Vì vậy “done” không có nghĩa là “thành công”.
- `isCancelled()` báo tác vụ đã được hủy.
- `cancel(false)` cố hủy tác vụ chưa bắt đầu, nhưng không yêu cầu ngắt tác vụ đang chạy. `cancel(true)` có thể yêu cầu ngắt thread đang chạy nếu tác vụ được thực hiện trên thread và việc hủy thành công; không có bảo đảm buộc tác vụ dừng.

Ví dụ dùng thời gian chờ (một đoạn mã đặt trong phương thức có xử lý `InterruptedException` và `ExecutionException`):

```java
try {
    Integer value = future.get(2, TimeUnit.SECONDS);
    System.out.println(value);
} catch (TimeoutException timeout) {
    future.cancel(true);
    System.out.println("Quá hạn, đã yêu cầu hủy tác vụ");
}
```

Ở đây `future` là `Future<Integer>` đã có và cần import `java.util.concurrent.*`. Đây **không phải chương trình độc lập**. Dòng thông báo chỉ xác nhận lời gọi yêu cầu hủy được thực hiện, không chứng minh tác vụ đã dừng; trong chương trình thật cần kiểm tra giá trị boolean từ `cancel(true)` nếu trạng thái đó quan trọng.

### Lỗi từ task đi đâu?

Khi `submit` một `Runnable`/`Callable`, ngoại lệ phát sinh trong tác vụ được giữ để `Future.get()` báo lại qua `ExecutionException`. Vì vậy gọi `submit` rồi bỏ qua `Future` có thể làm lỗi nghiệp vụ không được quan sát ở nơi gọi.

**Tệp `FailureDemo.java`**

```java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FailureDemo {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            Callable<Integer> faultyTask = () -> {
                throw new IllegalStateException("Sai trạng thái");
            };

            Future<Integer> future = executor.submit(faultyTask);
            try {
                System.out.println(future.get());
            } catch (ExecutionException failure) {
                Throwable cause = failure.getCause();
                System.out.println(
                        cause.getClass().getSimpleName()
                                + ": " + cause.getMessage());
            }
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac FailureDemo.java
java FailureDemo
```

Kết quả:

```text
IllegalStateException: Sai trạng thái
```

`get()` cũng có thể ném `InterruptedException` khi luồng **đang chờ** bị ngắt; điều này khác với một ngoại lệ ném **bên trong tác vụ** và được bọc trong `ExecutionException`.

Với `execute(Runnable)`, không có `Future` để lấy lỗi. Hành vi truyền hoặc báo runtime exception phụ thuộc cách `Executor` thực thi: bộ thực thi chạy inline có thể ném lỗi về luồng gọi, còn worker thread có thể kết thúc bất thường và đi qua cơ chế `UncaughtExceptionHandler`. Đừng mặc định `execute` và `submit` báo lỗi giống nhau.

### Hủy tác vụ cần hợp tác

Ngắt (`interrupt`) là tín hiệu hợp tác, không phải thao tác giết thread. Tác vụ chặn ở các API có hỗ trợ ngắt, chẳng hạn `Thread.sleep` hoặc `BlockingQueue.take`, thường nhận `InterruptedException`. Một tác vụ xử lý dài nên kiểm tra ngắt định kỳ và dừng hoặc dọn dẹp hợp lý.

Ví dụ **đoạn thân một Runnable**, không phải chương trình độc lập:

```java
Runnable responsiveTask = () -> {
    try {
        for (int i = 0; i < 100; i++) {
            if (Thread.currentThread().isInterrupted()) {
                return;
            }
            Thread.sleep(100);
            // Thực hiện một phần việc ngắn tại đây.
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        // Giữ lại tín hiệu ngắt để tầng gọi có thể nhận biết.
    }
};
```

Khi bắt `InterruptedException`, trạng thái ngắt thường đã bị xóa; khôi phục bằng `Thread.currentThread().interrupt()` nếu không thể ném tiếp và chính sách xử lý yêu cầu bảo toàn tín hiệu. Không nuốt ngắt rồi chạy vô hạn. Đồng thời không lạm dụng `Thread.stop()`, vì đây không phải cách quản lý hủy an toàn.

## 8. Đóng ExecutorService đúng cách

Thread pool có thể giữ các worker tồn tại sau khi `main` chạy xong; không đóng pool sở hữu có thể khiến ứng dụng tiếp tục sống hoặc rò rỉ tài nguyên.

- `shutdown()`: ngừng nhận tác vụ mới, cho các tác vụ đã gửi tiếp tục chạy; **không chờ** đến lúc tất cả kết thúc.
- `awaitTermination(timeout, unit)`: chờ sau khi đã bắt đầu đóng; trả `true` nếu đã kết thúc trong thời hạn, `false` nếu hết hạn.
- `shutdownNow()`: cố ngừng các tác vụ đang chạy bằng ngắt thread và trả về danh sách tác vụ đang đợi chưa bắt đầu. Đây là nỗ lực tốt nhất, **không bảo đảm dừng ngay**.
- `isShutdown()`: việc đóng đã bắt đầu; `isTerminated()`: mọi tác vụ đã kết thúc sau khi đóng. Hai trạng thái không đồng nghĩa.

Ví dụ **phương thức tiện ích để đặt trong lớp Java**, dùng khi tác vụ có thể chạy lâu:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

// Phương thức đặt bên trong một class:
static void stopGracefully(ExecutorService executor) {
    executor.shutdown();
    try {
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Vẫn còn tác vụ chưa kết thúc");
            }
        }
    } catch (InterruptedException interrupted) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
```

Hàm này bảo vệ luồng gọi trước việc chờ vô hạn và cố dọn dẹp khi thời gian chờ hết. `shutdownNow()` không cưỡng ép tác vụ bất hợp tác; nếu tác vụ bỏ qua mọi ngắt, sau thời hạn vẫn có thể còn hoạt động. Thời hạn 5 giây chỉ là ví dụ, phải chọn theo nghiệp vụ. Đối với Java 17, nên dùng `try/finally` hoặc một cơ chế quản lý vòng đời rõ ràng; đừng giả định `ExecutorService` có thể dùng trực tiếp với `try-with-resources` như các phiên bản JDK mới hơn.

**Quyền sở hữu quan trọng:** Code tạo `ExecutorService` thường có trách nhiệm đóng nó. Nếu ứng dụng Spring tạo và quản lý `ThreadPoolTaskExecutor` như một bean, hãy để vòng đời của container quản lý; không tự ý `shutdown` một pool đang được những thành phần khác dùng chung.

## 9. Chọn loại pool, độ song song và hàng đợi

Một số factory của `Executors` thường gặp:

| Factory | Hành vi tiêu biểu | Điểm cần chú ý |
|---|---|---|
| `newSingleThreadExecutor()` | Một worker chạy từng tác vụ tuần tự | Không nên đặt tác vụ chờ tác vụ khác cùng pool; một tác vụ treo chặn cả hàng |
| `newFixedThreadPool(n)` | Tối đa `n` worker thực thi song song | Hàng đợi mặc định không giới hạn dung lượng theo cấu hình; tải dồn có thể làm bộ nhớ tăng |
| `newCachedThreadPool()` | Tạo thêm worker khi cần, tái sử dụng worker nhàn rỗi | Số worker có thể tăng rất lớn khi tải mạnh; cần cân nhắc giới hạn tài nguyên |

Kích thước pool không phải “càng lớn càng nhanh”. Tác vụ tính toán thuần CPU chịu giới hạn số lõi và chi phí chuyển ngữ cảnh. Tác vụ đợi I/O có thể hưởng lợi từ mức đồng thời cao hơn, nhưng còn giới hạn kết nối, tốc độ dịch vụ ngoài, bộ nhớ và thời gian đáp ứng. Hãy đo hiệu năng với tải thực tế.

`Executors.newFixedThreadPool(n)` thuận tiện cho minh họa, nhưng hàng đợi không có giới hạn cấu hình sẵn nên chưa đủ an toàn cho mọi hệ thống nhận lưu lượng lớn. Trong ứng dụng vận hành, cân nhắc `ThreadPoolExecutor` với `corePoolSize`, `maximumPoolSize`, hàng đợi có dung lượng rõ ràng và chính sách từ chối.

Ví dụ tạo pool **có hàng đợi giới hạn** (đoạn khai báo trong phương thức, cần `import java.util.concurrent.*;`):

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2, 4,
        30, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(100),
        new ThreadPoolExecutor.AbortPolicy()
);
```

Pool trên có tối đa bốn worker, hàng đợi tối đa 100 tác vụ đang chờ, và có thể ném `RejectedExecutionException` khi không thể nhận thêm. Nó vẫn cần `shutdown()` khi không còn dùng. Với `ThreadPoolExecutor`, tác vụ sẽ ưu tiên sử dụng số worker lõi rồi được đưa vào hàng đợi; khi hàng đợi đầy mới cân nhắc tăng worker tới `maximumPoolSize`, nên cấu hình queue ảnh hưởng mạnh đến hành vi mở rộng.

Nếu cần thực thi sau độ trễ hoặc theo chu kỳ, đó là nhiệm vụ của `ScheduledExecutorService` (một nhánh chuyên biệt). Đừng dùng vòng lặp `Thread.sleep` để tự chế bộ lập lịch trong mọi trường hợp.

## 10. Điều phối nhiều tác vụ

Khi có một nhóm tác vụ `Callable<T>`, ngoài `submit` từng cái, `ExecutorService` còn hỗ trợ:

- `invokeAll(collection)`: gửi cả nhóm và chờ tất cả hoàn tất, trả `List<Future<T>>` theo **thứ tự đầu vào**, không phải thứ tự hoàn tất; từng Future có thể giữ lỗi hoặc trạng thái hủy. Có phiên bản với timeout.
- `invokeAny(collection)`: trả kết quả của **một tác vụ hoàn thành thành công**, không nhất thiết là tác vụ được gửi đầu tiên; các tác vụ còn lại chưa xong được yêu cầu hủy. Nếu không có tác vụ thành công, phương thức báo lỗi thích hợp.

Ví dụ độc lập:

**Tệp `InvokeAllDemo.java`**

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InvokeAllDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Callable<Integer>> tasks = List.of(
                    () -> 2 * 2,
                    () -> 3 * 3
            );
            List<Future<Integer>> results = executor.invokeAll(tasks);

            int total = 0;
            for (Future<Integer> result : results) {
                total += result.get();
            }
            System.out.println("Tổng = " + total);
        } finally {
            executor.shutdown();
        }
    }
}
```

```bash
javac InvokeAllDemo.java
java InvokeAllDemo
```

Kết quả:

```text
Tổng = 13
```

Một nhóm tác vụ độc lập có thể được phân công chạy song song, nhưng phần gom kết quả vẫn phải xử lý lỗi và thời gian chờ. `Future` phù hợp để chờ/lấy kết quả đơn lẻ; nếu cần ghép chuỗi nhiều bước bất đồng bộ, kết hợp kết quả hoặc xử lý chuỗi sự kiện linh hoạt, có thể tìm hiểu thêm `CompletableFuture` ở bài riêng.

## 11. Đồng bộ dữ liệu và những bẫy khó thấy

### Chia sẻ trạng thái giữa worker không tự an toàn

Pool chỉ điều phối việc chạy, không tự bảo vệ biến dùng chung. Ví dụ nhiều tác vụ cùng thực hiện `count++` trên một `int` có thể mất cập nhật vì phép tăng gồm nhiều thao tác đọc–tính–ghi. Dùng thiết kế tránh chia sẻ dữ liệu có thể thay đổi, hoặc dùng cơ chế phù hợp như `AtomicInteger`, đồng bộ hóa và collection hỗ trợ concurrent.

JDK quy định quan hệ **happens-before** quan trọng đối với `ExecutorService`: hành động trên luồng gửi xảy ra trước `submit` được nhìn thấy bởi tác vụ; hành động của tác vụ xảy ra trước khi phía gọi nhận kết quả qua `Future.get()`. Nhờ đó ta có quan hệ công bố dữ liệu và quan sát kết quả rõ ràng. Tuy nhiên, quy tắc này **không thay thế** cơ chế phối hợp cho nhiều tác vụ đồng thời sửa cùng một biến.

### Đừng chờ chính công việc đang xếp hàng sau mình

Giả sử dùng `newSingleThreadExecutor()`:

1. Tác vụ A đang chiếm worker duy nhất.
2. A lại `submit` tác vụ B vào **cùng pool** và gọi `B.get()` để chờ.
3. B nằm trong hàng đợi, chờ A nhường worker; A lại chờ B ⇒ bế tắc (deadlock).

Mã minh họa trường hợp lỗi, **không chạy nguyên đoạn như một ví dụ hoàn tất**:

```java
ExecutorService single = Executors.newSingleThreadExecutor();
single.submit(() -> {
    Future<Integer> inner = single.submit(() -> 42);
    try {
        System.out.println(inner.get()); // Có thể chờ vô hạn.
    } catch (InterruptedException | ExecutionException e) {
        Thread.currentThread().interrupt(); // Minh họa tối giản; xem lưu ý dưới.
    }
});
```

Đoạn này chỉ minh họa vị trí chờ sai và giả định đã import `java.util.concurrent.*`; cố ý không có lệnh chạy. Trong code thật, chỉ khôi phục trạng thái ngắt khi bắt `InterruptedException`; còn `ExecutionException` phải xử lý theo nguyên nhân lỗi riêng. Cách sửa thiết kế là tránh chặn worker khi đang chờ công việc chỉ chính pool đó mới có thể thực hiện, hoặc tổ chức lại tác vụ để không có phụ thuộc vòng.

### Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng sửa |
|---|---|---|
| Gọi `run()` và tưởng đã tạo luồng mới | `run()` chạy như phương thức bình thường | Dùng `Thread.start()` hoặc gửi qua executor phù hợp |
| `submit` rồi bỏ `Future` và không có xử lý lỗi | Lỗi có thể chỉ nằm trong Future | `get()`, ghi nhận hoàn tất/lỗi hoặc dùng cơ chế quan sát rõ ràng |
| `get()` ngay sau mỗi `submit` trong vòng lặp | Có thể biến xử lý dự kiến song song thành tuần tự | Gửi tất cả việc trước, sau đó thu kết quả |
| Cứ gọi `get()` trong worker chờ việc từ cùng pool | Có thể bế tắc khi pool hết worker | Loại bỏ chờ vòng; thiết kế lại phụ thuộc |
| Không gọi `shutdown()` cho pool tự tạo | Worker/tài nguyên tồn tại ngoài ý muốn | Xác định owner, đóng trong `finally` |
| Tin `shutdownNow()` buộc mọi tác vụ dừng | Ngắt chỉ là yêu cầu hợp tác | Viết task đáp ứng interrupt và có timeout hợp lý |
| Dùng nhiều worker cùng sửa `HashMap`/biến chung không bảo vệ | Race condition, dữ liệu sai hoặc lỗi | Tránh shared mutable state; dùng đồng bộ hay concurrent collection |
| Tạo pool mới cho từng request | Tốn thread và tài nguyên, khó kiểm soát tải | Tái sử dụng pool do ứng dụng quản lý |
| Cho rằng `execute` luôn bất đồng bộ | `Executor` có thể chạy inline | Kiểm tra triển khai và hợp đồng thực tế |

**Lưu ý về xử lý ngoại lệ hỗn hợp:** Nếu bắt gộp `InterruptedException` với một ngoại lệ khác, không được gọi `interrupt()` cho cả hai loại một cách máy móc. Hãy tách catch và chỉ khôi phục cờ ngắt khi thực sự gặp `InterruptedException`.

## 12. Liên hệ với Spring Framework

Spring cung cấp `TaskExecutor` để trừu tượng hóa việc thực thi `Runnable`, và `ThreadPoolTaskExecutor` là triển khai phổ biến bọc thread pool có thể cấu hình kích thước, hàng đợi và vòng đời trong container. Các khái niệm Java cơ sở vẫn giữ nguyên:

| Java concurrency | Ý nghĩa khi sang Spring |
|---|---|
| `Runnable` / `Callable` | Phần công việc cần chạy; logic nghiệp vụ nên tách khỏi việc quản lý worker |
| `Executor.execute(Runnable)` | Tương ứng tư duy gửi tác vụ cho `TaskExecutor` |
| `ExecutorService` / thread pool | Cơ sở hiểu `ThreadPoolTaskExecutor`, năng lực xử lý, queue và chính sách từ chối |
| `Future<T>` | Hiểu kết quả hoặc lỗi từ công việc được gửi bất đồng bộ; không nên chặn tùy tiện |
| `shutdown` / vòng đời | Pool do Spring quản lý nên đóng theo lifecycle của application context |

`@Async` hỗ trợ chạy phương thức được cấu hình qua bộ thực thi của Spring, nhưng việc hoạt động phụ thuộc cơ chế proxy và cấu hình async; gọi nội bộ một phương thức `@Async` qua `this` thường không đi qua proxy nên không tạo chuyển luồng như mong đợi. Ngoài ra, chuyển sang worker khác không có nghĩa các giá trị trong `ThreadLocal`, ngữ cảnh request hay transaction trên luồng gọi sẽ tự động đi theo. Các trường hợp cần truyền ngữ cảnh phải được thiết kế rõ ràng.

Trong ứng dụng web, không nên dùng `@Async` như cách vô điều kiện tăng tốc mọi request: công việc vẫn cần CPU, connection, queue, quyền truy cập tài nguyên và xử lý lỗi. Nếu tác vụ cần độ bền qua lần khởi động lại, thread pool nằm trong tiến trình chưa thay thế được hàng đợi tác vụ bền vững.

## 13. Cách chọn công cụ theo yêu cầu

| Yêu cầu thực tế | Lựa chọn ban đầu | Lý do |
|---|---|---|
| Mô tả một thao tác không có kết quả | `Runnable` | Gọn và rõ ý định |
| Tính toán trả về một giá trị hoặc checked exception | `Callable<T>` | `call()` có kiểu trả về và `throws Exception` |
| Chỉ muốn gửi `Runnable`, không cần quản lý kết quả/vòng đời | `Executor` | Hợp đồng tối thiểu, dễ thay thế triển khai |
| Muốn lấy kết quả, chờ hoàn tất hoặc kiểm soát đóng pool | `ExecutorService` + `Future` | Có `submit` và lifecycle |
| Nhiều việc độc lập cần kết quả | `ExecutorService.invokeAll` hoặc nhiều `Future` | Có thể chạy đồng thời, sau đó gom kết quả |
| Ứng dụng Spring cần pool dùng chung | Bean `ThreadPoolTaskExecutor` được cấu hình | Vòng đời tập trung và có giới hạn tài nguyên |

Có thể ghi nhớ chuỗi tư duy: **chọn task → chọn executor → gửi tác vụ → quan sát hoàn tất/lỗi → đóng đúng owner**. Câu hỏi “cần thread mới không?” thường nên đến sau câu hỏi “tác vụ nào và ai chịu trách nhiệm quản lý chúng?”.

## 14. Tự luyện tập và câu hỏi kiểm tra

1. Tạo `Runnable` in tên thread và so sánh hành vi khi gọi trực tiếp `run()` với khi gửi qua `ExecutorService.execute(...)`. Có phải mọi lần dùng `Executor` đều sang thread khác không? Giải thích bằng `ExecutorDemo`.
2. Viết `Callable<Long>` tính tổng từ 1 đến 100 và gửi qua `newSingleThreadExecutor()`. Kiểm tra `Future.get()` trả `5050`; luôn đóng executor ở `finally`.
3. Gửi ba `Callable<Integer>` vào pool hai worker bằng `invokeAll`. Dự đoán thứ tự trả `List<Future<Integer>>` khi tác vụ thứ ba kết thúc nhanh nhất.
4. Thay một `Callable` bằng tác vụ ném `IllegalArgumentException`. Kiểm tra `Future.isDone()` và xử lý nguyên nhân qua `ExecutionException.getCause()`. Vì sao `isDone() == true` không nói rằng tác vụ thành công?
5. Viết một tác vụ ngủ từng đoạn ngắn, gọi `cancel(true)` khi nó đang chạy, rồi quan sát trạng thái. Vì sao chương trình phải xử lý `InterruptedException` và không thể dựa vào `cancel(true)` như một lệnh cưỡng chế?
6. Vẽ timeline của một pool một worker khi A nộp B rồi gọi `B.get()`. Giải thích deadlock và đề xuất cách tách phụ thuộc.

**Đáp án định hướng:** (1) `run()` chạy trên caller, `execute` tùy implementation; (2) tổng bằng 5050; (3) `invokeAll` trả các Future theo thứ tự danh sách đầu vào; (4) `isDone` cũng đúng với lỗi/hủy; (5) ngắt là hợp tác; (6) A giữ worker nên B không có cơ hội chạy. Hãy kiểm tra code bằng `javac`/`java` thay vì dựa vào `Thread.sleep` để đoán thứ tự thực thi.

## 15. Điều cần nhớ

- **`Runnable` và `Callable` mô tả công việc**; `Executor` và `ExecutorService` điều phối việc thực hiện.
- **`Callable<V>` trả giá trị** và có thể ném checked exception; `Runnable.run()` không có hai khả năng đó trong chữ ký.
- **`execute` không trả Future**, còn **`submit` trả Future** để chờ, nhận lỗi, lấy kết quả hoặc hủy.
- **`Future.get()` có thể chặn**, `isDone()` không đồng nghĩa thành công, và `cancel(true)` chỉ yêu cầu hủy/ngắt theo khả năng thực hiện.
- **Pool có vòng đời, hàng đợi và giới hạn tài nguyên**. Người sở hữu pool chịu trách nhiệm đóng nó; Spring có thể sở hữu và quản lý pool thay ứng dụng.
- **Đồng thời không tự động an toàn luồng**: phải thiết kế việc chia sẻ dữ liệu, thời gian chờ và phụ thuộc giữa tác vụ một cách rõ ràng.
