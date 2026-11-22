# Runnable, Callable và cách truyền kết quả tác vụ trong Java

Khi viết chương trình Java đồng thời (concurrency), ta cần tách hai câu hỏi: **tác vụ sẽ thực hiện việc gì?** và **người gọi lấy kết quả, biết lỗi hoặc chờ tác vụ hoàn tất bằng cách nào?** Hai functional interface `Runnable` và `Callable<V>` biểu diễn công việc; những công cụ như `Thread.join()`, `Future<V>`, `FutureTask<V>` và `ExecutorService` giúp quản lý quá trình thực thi và nhận kết quả. Bài này nói về **Java nói chung**, tập trung vào Thread API và Java concurrency tiêu chuẩn (Java 17+); không bàn về cơ chế riêng của Spring.

Sau bài này, bạn có thể:
- Phân biệt `Runnable.run()`, `Callable.call()`, giá trị trả về và checked exception.
- Chạy một tác vụ qua `Thread` hoặc gửi cho `ExecutorService`; biết lúc nào dùng `execute`, `submit`.
- Lấy kết quả từ luồng khác bằng `join` + đối tượng chia sẻ, `FutureTask` hoặc `Future`.
- Xử lý thành công, lỗi, chờ, timeout, hủy tác vụ và interrupt mà không làm mất lỗi.
- Nhận ra những sai lầm phổ biến: gọi `run()` thay vì `start()`, gọi `get()` quá sớm, coi `shutdown()` là đã đợi xong, hoặc bỏ qua `Future` khi tác vụ lỗi.

## 1. Runnable và Callable biểu diễn công việc như thế nào?

### 1.1. Runnable: thực thi hành động, không có giá trị trả về

`java.lang.Runnable` khai báo một phương thức trừu tượng:

~~~java
@FunctionalInterface
public interface Runnable {
    void run();
}
~~~

Một `Runnable` mô tả công việc có thể chạy; phương thức `run()` **trả về `void`** và **không khai báo checked exception**. Có thể viết bằng class, anonymous class, method reference hoặc lambda:

~~~java
Runnable logTask = () -> System.out.println("Running task");
~~~

`Runnable` không mang một kênh kết quả trả về trực tiếp qua `run()`, nhưng tác vụ vẫn có thể làm thay đổi một đối tượng được chia sẻ, phát thông điệp hoặc ghi dữ liệu. Việc chia sẻ đó cần thiết kế an toàn luồng khi có truy cập đồng thời.

### 1.2. Callable<V>: thực thi và trả về V

`java.util.concurrent.Callable<V>` khai báo:

~~~java
@FunctionalInterface
public interface Callable<V> {
    V call() throws Exception;
}
~~~

Khác biệt chính:
- `call()` trả về **một giá trị có kiểu `V`**; chẳng hạn `Callable<Integer>` trả về `Integer`.
- `call()` được phép khai báo `throws Exception`, nên tác vụ có thể ném checked exception.
- `Callable` không được truyền trực tiếp vào constructor `Thread(Runnable)`; muốn chạy với `Thread` có thể bọc nó trong `FutureTask`, hoặc thường gặp hơn là đưa cho `ExecutorService.submit`.

~~~java
Callable<Integer> calculate = () -> 6 * 7;
Callable<String> loadText = () -> "ready";
Callable<Void> withoutValue = () -> {
    System.out.println("Work completed");
    return null;
};
~~~

**Lưu ý:** `Callable<Void>` vẫn phải trả về một giá trị tương thích kiểu `Void` (trên thực tế thường là `null`). Nếu bạn chỉ cần diễn tả một hành động không có giá trị trả về, `Runnable` thường gọn hơn.

| Tiêu chí | `Runnable` | `Callable<V>` |
| --- | --- | --- |
| Phương thức trừu tượng | `void run()` | `V call() throws Exception` |
| Giá trị trả về trực tiếp | Không | Có, kiểu `V` |
| Checked exception khai báo trong phương thức | Không | Có |
| Có thể đưa trực tiếp vào `new Thread(...)` | Có | Không |
| Có thể đưa vào `ExecutorService.submit(...)` | Có | Có |
| Khi nào chọn | Hành động, tác vụ không cần trả giá trị | Tính toán, truy xuất hoặc xử lý cần trả giá trị / checked exception |

Cả hai là **functional interface** và đều biểu diễn *việc cần làm*; tự tạo `Runnable` hay `Callable` không khiến tác vụ chạy bất đồng bộ. Phải có cơ chế thực thi như `Thread.start()` hoặc executor.

## 2. Chạy Runnable bằng Thread và chờ bằng join()

### 2.1. Ví dụ Java 17+ có thể chạy độc lập

~~~java
// RunnableThreadDemo.java
import java.util.concurrent.atomic.AtomicInteger;

public class RunnableThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger result = new AtomicInteger();

        Runnable task = () -> {
            int value = 6 * 7;
            result.set(value);
        };

        Thread worker = new Thread(task, "calculation-worker");
        worker.start(); // Tạo đường thực thi mới rồi gọi task.run() trong luồng đó.
        worker.join();  // Đợi worker kết thúc.

        System.out.println("Result: " + result.get());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac RunnableThreadDemo.java
java RunnableThreadDemo
~~~

Stdout:

~~~text
Result: 42
~~~

Ở đây `Runnable.run()` không trả về `42`. Worker **ghi** vào `AtomicInteger`, còn luồng `main` **đọc** sau khi `join()`. `join()` chỉ chờ kết thúc; giá trị xuất hiện vì chúng ta chủ động lưu trong đối tượng dùng chung. Mọi hành động của worker trước khi kết thúc được bảo đảm *happens-before* luồng khác quay về thành công từ `join()`, nên dữ liệu được công bố đúng cách qua việc chờ này. Dùng `AtomicInteger` ở ví dụ nhằm làm rõ trạng thái được chia sẻ; nếu chỉ một worker ghi và main chỉ đọc sau `join()` thì một holder không biến đổi đồng thời khác cũng có thể phù hợp.

### 2.2. Không nhầm run() với start()

~~~java
worker.run();   // Gọi phương thức như một lời gọi thông thường trên luồng hiện tại.
worker.start(); // Yêu cầu JVM bắt đầu luồng mới; luồng đó sẽ chạy run().
~~~

Hai dòng trên là **minh họa hai lựa chọn**, không phải chuỗi lệnh cần chạy nối tiếp trên cùng `worker`. Một `Thread` chỉ được `start()` **một lần**; gọi lại sẽ ném `IllegalThreadStateException`. `Thread.join()` chờ luồng kết thúc, nhưng **không trả về kết quả tác vụ**. Khi có nhiều nhiệm vụ và cần kết quả/ngoại lệ, `Future` thường là mô hình tiện hơn tự quản lý nhiều `Thread` cùng các holder.

## 3. Future<V>: đại diện cho kết quả sẽ có trong tương lai

`java.util.concurrent.Future<V>` là một *handle* theo dõi tác vụ đã được đăng ký/chạy và nhận kết quả khi hoàn tất. `Future` không tự tạo luồng; một executor hoặc `FutureTask` phải thực thi công việc phía sau.

Các phương thức quan trọng:

| Phương thức | Ý nghĩa |
| --- | --- |
| `V get()` | Đợi đến khi hoàn tất rồi trả kết quả, hoặc ném ngoại lệ nếu thất bại/bị hủy/người đợi bị interrupt |
| `V get(long timeout, TimeUnit unit)` | Đợi tối đa thời gian chỉ định, có thể ném `TimeoutException` |
| `boolean isDone()` | `true` nếu tác vụ đã kết thúc theo một cách nào đó: thành công, lỗi hoặc bị hủy |
| `boolean isCancelled()` | `true` nếu tác vụ bị hủy |
| `boolean cancel(boolean mayInterruptIfRunning)` | Thử hủy tác vụ; kết quả phụ thuộc trạng thái và cơ chế thực thi |

`get()` có thể **chặn luồng gọi**. Nếu đã hoàn tất thành công, nó trả về giá trị; nếu tác vụ lỗi, nó ném `ExecutionException`, trong đó `getCause()` giữ nguyên nhân. Nếu bị hủy, `get()` ném `CancellationException` (unchecked). Nếu người chờ bị interrupt, `get()` ném `InterruptedException`.

`isDone() == true` **không đồng nghĩa với thành công**; sau khi trả về `true`, vẫn phải xử lý các trường hợp lỗi/hủy nếu cần kết quả.

Mô hình thời gian:

~~~text
Luồng gọi                     Luồng tác vụ
   | submit(callable)  -------> | bắt đầu làm việc
   | nhận Future<V>            | tính toán...
   | làm việc khác             | ...
   | future.get()              | ...
   | [có thể chờ]              | return value
   | <------------------------ | hoàn tất
   | nhận V                    |
~~~

Việc chờ `Future.get()` trả về thành công đồng thời tạo bảo đảm bộ nhớ cần thiết để nhìn thấy các hiệu ứng do tác vụ thực hiện trước khi hoàn tất. Tuy vậy, **giá trị trả về có thể là đối tượng mutable**: sau thời điểm hoàn tất, các truy cập đồng thời tiếp theo vào đối tượng đó vẫn cần quy tắc đồng bộ riêng.

## 4. ExecutorService: gửi tác vụ rồi nhận Future

`ExecutorService` là abstraction quản lý thực thi tác vụ, có thể tái sử dụng một pool luồng. Khác với tạo `new Thread(...)` cho từng lần, nó tách tác vụ khỏi quyết định sử dụng bao nhiêu luồng.

Các overload thường dùng:

| Cách gọi | Kết quả |
| --- | --- |
| `execute(Runnable)` | Trả về `void`; không nhận một `Future` để chờ/đọc kết quả |
| `submit(Runnable)` | `Future<?>`; khi hoàn tất thành công, `get()` trả về `null` |
| `submit(Runnable, T result)` | `Future<T>`; khi hoàn tất thành công, `get()` trả lại **giá trị `result` được cung cấp trước** |
| `submit(Callable<T>)` | `Future<T>`; `get()` trả lại giá trị do `call()` tính và trả về |

### 4.1. Runnable có Future để biết khi nào hoàn thành

~~~java
// RunnableFutureDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class RunnableFutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        AtomicInteger counter = new AtomicInteger();

        try {
            Future<?> first = pool.submit(() -> counter.addAndGet(3));
            Object noReturnValue = first.get();

            Future<String> second = pool.submit(
                () -> counter.addAndGet(2),
                "completed"
            );
            String status = second.get();

            System.out.println("First result: " + noReturnValue);
            System.out.println("Second result: " + status);
            System.out.println("Counter: " + counter.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac RunnableFutureDemo.java
java RunnableFutureDemo
~~~

Stdout xác định:

~~~text
First result: null
Second result: completed
Counter: 5
~~~

- `first.get()` đợi tác vụ cộng 3 kết thúc; vì tác vụ là `Runnable` nên `get()` trả về `null`.
- `submit(runnable, "completed")` **không biến `run()` thành hàm trả về String**. Chuỗi `"completed"` là giá trị caller cung cấp trước và chỉ được trả về sau khi tác vụ hoàn tất thành công.
- Hai phép cộng an toàn nhờ `AtomicInteger`. `get()` được gọi lần lượt nên kết quả in luôn là 5. Không nên suy luận thứ tự bắt đầu giữa các task nếu không có quan hệ đồng bộ rõ ràng.
- `shutdown()` từ chối tác vụ mới nhưng **không tự chờ** các tác vụ trước đó hoàn thành. Ví dụ này đã gọi `get()` cho cả hai trước khi shutdown.

### 4.2. Callable: lấy kết quả thực sự do tác vụ tính

~~~java
// CallableResultDemo.java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CallableResultDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Callable<Integer> sum = () -> {
                int total = 0;
                for (int i = 1; i <= 5; i++) {
                    total += i;
                }
                return total;
            };

            Future<Integer> future = pool.submit(sum);
            System.out.println("Sum: " + future.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac CallableResultDemo.java
java CallableResultDemo
~~~

Stdout:

~~~text
Sum: 15
~~~

`submit` trả về `Future<Integer>` ngay khi executor **chấp nhận** tác vụ, không đợi tính xong. `future.get()` là điểm có thể chờ và nhận `Integer` do `call()` trả về. `Callable` có thể được định nghĩa thành class riêng nếu logic dài; lambda phù hợp khi đoạn code ngắn, dễ đọc.

**Lựa chọn thực tế:** Nếu người gọi cần giá trị từ tác vụ, ưu tiên `Callable<T> + Future<T>`. Với logic không trả giá trị, `Runnable` phù hợp, kể cả khi bạn dùng `Future<?>` chỉ để theo dõi hoàn thành và lỗi.

## 5. FutureTask<V>: kết nối Callable với một Thread cụ thể

`FutureTask<V>` là một lớp hiện thực cả `Runnable` và `Future<V>`. Nó có thể **nhận một `Callable<V>` để thực thi** và **cho phép luồng khác gọi `get()` để lấy giá trị**. Vì `FutureTask` cũng là `Runnable`, bạn có thể truyền nó trực tiếp cho `new Thread(...)`.

~~~java
// FutureTaskThreadDemo.java
import java.util.concurrent.Callable;
import java.util.concurrent.FutureTask;

public class FutureTaskThreadDemo {
    public static void main(String[] args) throws Exception {
        Callable<String> work = () ->
            "calculated by " + Thread.currentThread().getName();

        FutureTask<String> task = new FutureTask<>(work);
        Thread thread = new Thread(task, "worker-1");

        thread.start();
        System.out.println(task.get());
    }
}
~~~

~~~bash
javac FutureTaskThreadDemo.java
java FutureTaskThreadDemo
~~~

Stdout:

~~~text
calculated by worker-1
~~~

Dòng `task.get()` có thể chờ đến khi thread hoàn thành. `FutureTask` chỉ hoàn tất một lần: gọi `run()` lại không tính lại kết quả của một instance đã hoàn thành. Với nhu cầu chạy nhiều tác vụ, điều phối tải và tái sử dụng luồng, `ExecutorService` thường thuận tiện hơn tự tạo hàng loạt `Thread`; `FutureTask` hữu ích khi cần kết nối mô hình `Thread` cơ bản với một kênh kết quả.

## 6. Truyền lỗi, hủy tác vụ và xử lý gián đoạn

### 6.1. Ngoại lệ trong task được quan sát như thế nào?

Khi một tác vụ được gửi bằng `submit` rồi ném exception, `Future.get()` ném `ExecutionException` và giữ ngoại lệ gốc ở `getCause()`. Điều này đúng cả với `Runnable` chạy qua `submit`; khác biệt ở khả năng **khai báo checked exception trong thân phương thức**, không phải ở việc có thể lỗi hay không.

Ví dụ Java 17+:

~~~java
// CallableFailureDemo.java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class CallableFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Callable<Integer> work = () -> {
                throw new IllegalArgumentException("invalid input");
            };
            Future<Integer> future = pool.submit(work);

            try {
                System.out.println(future.get());
            } catch (ExecutionException e) {
                Throwable cause = e.getCause();
                System.out.println(
                    cause.getClass().getSimpleName() + ": " + cause.getMessage()
                );
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac CallableFailureDemo.java
java CallableFailureDemo
~~~

Stdout:

~~~text
IllegalArgumentException: invalid input
~~~

Nếu dùng `execute(Runnable)`, caller không nhận `Future` để thu lỗi. Lỗi unchecked thoát khỏi `run()` được xử lý theo cơ chế uncaught-exception của luồng/executor, tùy cách quản lý luồng. Nếu dùng `submit` mà **bỏ qua `Future`**, người gọi có thể không nhìn thấy lỗi qua đường truyền kết quả. Vì thế hãy chủ động thu nhận/quan sát `Future` hoặc thiết lập cơ chế báo lỗi phù hợp.

### 6.2. Timeout và cancel

Ví dụ **đoạn mã minh họa**, giả sử đã có `Future<String> future` và phương thức bao quanh xử lý hoặc khai báo những exception cần thiết:

~~~java
String value = future.get(2, java.util.concurrent.TimeUnit.SECONDS);
~~~

Nếu quá 2 giây mà tác vụ chưa hoàn tất, lời gọi này ném `TimeoutException`. **Timeout của `get` chỉ giới hạn thời gian chờ của caller; nó không tự dừng task.** Caller có thể quyết định gọi `future.cancel(true)`, nhưng hủy có thành công hoặc khiến task dừng sớm hay không còn phụ thuộc trạng thái và khả năng hợp tác với interrupt.

~~~java
boolean cancellationRequested = future.cancel(true);
~~~

Với `mayInterruptIfRunning = true`, hệ thống có thể gửi interrupt tới luồng đang chạy; interrupt **không phải lệnh dừng cưỡng bức**. Tác vụ nên phản hồi khi thao tác chặn ném `InterruptedException`, hoặc kiểm tra trạng thái interrupt trong vòng lặp dài. Không được hiểu `isDone() == true` sau cancel là “công việc đã chạy đến cuối”; kết quả thành công, lỗi và hủy là các trạng thái khác nhau.

### 6.3. Đừng nuốt InterruptedException

Khi thread gọi `get()` hoặc `join()` đang chờ và bị interrupt, lời gọi có thể ném `InterruptedException`. Nếu tầng hiện tại có thể khai báo `throws InterruptedException`, thường nên truyền tiếp. Nếu phải xử lý tại chỗ, có thể khôi phục cờ interrupt để tầng trên biết:

~~~java
try {
    future.get();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Dừng/thoát công việc của caller theo chính sách ứng dụng.
} catch (java.util.concurrent.ExecutionException e) {
    // Xử lý nguyên nhân từ e.getCause().
}
~~~

Đây là **đoạn minh họa xử lý**, giả sử đã tồn tại biến `future`. Nếu cần quản lý timeout, thêm nhánh `TimeoutException`; nếu có thể cancel, cân nhắc `CancellationException`. Không gộp tất cả vào một `catch (Exception ignored)` vì làm mất thông tin lỗi và tín hiệu interrupt.

## 7. CompletableFuture: kết quả bất đồng bộ có thể kết hợp

Ngoài `Future` cơ bản, Java còn có `CompletableFuture<T>`. Nó hữu ích khi muốn **ghép các bước tính toán, biến đổi kết quả, kết hợp nhiều task hoặc xử lý lỗi** mà không phải ngay lập tức chặn bằng `get()`. Đây là công cụ của Java tiêu chuẩn; phần này chỉ giới thiệu điểm nối với chủ đề truyền kết quả, không đi sâu vào toàn bộ API.

~~~java
// CompletableFutureDemo.java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureDemo {
    public static void main(String[] args) {
        CompletableFuture<Integer> future =
            CompletableFuture.supplyAsync(() -> 21)
                .thenApply(value -> value * 2);

        System.out.println("Answer: " + future.join());
    }
}
~~~

~~~bash
javac CompletableFutureDemo.java
java CompletableFutureDemo
~~~

Stdout:

~~~text
Answer: 42
~~~

- `supplyAsync` nhận logic có giá trị trả về, gần với ý nghĩa `Callable`, nhưng dùng `Supplier<T>`: phương thức `get()` của `Supplier` không khai báo checked exception.
- `thenApply` mô tả bước biến đổi từ `Integer` sang `Integer` khi có kết quả; không cần caller tự lấy rồi gửi kết quả thủ công.
- `join()` của `CompletableFuture` chờ và trả kết quả giống ý tưởng `get()` nhưng dùng ngoại lệ unchecked cho lỗi tính toán (thường là `CompletionException`); nó không khai báo `InterruptedException`. Không nhầm `CompletableFuture.join()` với `Thread.join()`.
- Mặc định `supplyAsync` không truyền executor sẽ dùng cơ chế executor mặc định của `CompletableFuture` (thường là common ForkJoinPool; có thể dùng luồng khác khi common pool không đủ parallelism). Với ứng dụng cần kiểm soát tài nguyên, có thể truyền một `Executor` phù hợp vào overload của `supplyAsync`.

## 8. Chọn cách truyền kết quả theo tình huống

| Nhu cầu | Cách thường phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Chạy một hành động đơn giản trên một luồng thủ công | `Runnable` + `Thread.start()` | `run()` không tạo thread mới |
| Chỉ cần main đợi worker xong và đọc state đã ghi | Shared holder + `Thread.join()` | Đồng bộ trạng thái truy cập khi cần; `join()` không trả giá trị |
| Dùng `Thread` nhưng muốn nhận kết quả/ngoại lệ kiểu rõ ràng | `Callable<T>` + `FutureTask<T>` + `Thread` | `FutureTask` vừa là `Runnable` vừa là `Future<T>` |
| Chạy nhiều tác vụ độc lập, cần trả kết quả | `ExecutorService.submit(Callable<T>)` | Nhận `Future<T>` rồi `get()` ở điểm thích hợp |
| Không trả kết quả nhưng cần đợi/biết task có lỗi | `ExecutorService.submit(Runnable)` | `Future<?>.get()` trả `null` nếu thành công |
| Runnable và muốn có thông báo hoàn tất dạng một giá trị đã biết | `submit(Runnable, T result)` | `result` do caller truyền vào, không được tính bằng giá trị trả về của `run()` |
| Cần xâu chuỗi và biến đổi kết quả bất đồng bộ | `CompletableFuture<T>` | Xử lý exception, executor và luồng chạy continuation đúng cách |

### 8.1. Những lỗi thường gặp

1. **Gọi `task.run()` rồi nghĩ đã chạy đồng thời.** Đó là lời gọi trên thread hiện tại; cần `start()` hoặc executor.
2. **Truyền `Callable` trực tiếp cho `new Thread(callable)`.** Constructor nhận `Runnable`; bọc bằng `FutureTask` hoặc dùng `submit`.
3. **Thấy `Future<?>` nên nghĩ task trả kết quả hữu ích.** `submit(Runnable)` hoàn tất thành công cho giá trị `null`; muốn giá trị tính toán thì dùng `Callable<T>`.
4. **Ngay sau `submit` gọi `get()` cho từng task trong một vòng lặp và mong toàn bộ quy trình không chặn.** Tác vụ vẫn chạy trên executor nhưng caller có thể chờ từng phần. Có thể gửi các task trước rồi thu kết quả sau, hoặc dùng công cụ phối hợp bất đồng bộ phù hợp.
5. **Bỏ `Future`, quên exception trong task.** Với `submit`, lỗi tác vụ được lưu vào future và thường quan sát khi `get()`.
6. **Coi `shutdown()` là “mọi task đã hoàn thành”.** Nó khởi động quá trình đóng, từ chối task mới nhưng không chờ hoàn tất; khi cần có thể đợi future hoặc dùng `awaitTermination` với chiến lược timeout.
7. **Dùng `future.get()` vô hạn trong đường xử lý có deadline.** Xem xét `get(timeout, unit)`, cancellation và quản lý tài nguyên.
8. **Nghĩ `cancel(true)` luôn giết được tác vụ.** Tác vụ phải phản hồi hợp tác với interrupt; một số công việc chặn hoặc thư viện có quy tắc hủy khác nhau.
9. **Dùng chung một kết quả mutable rồi coi `Future.get()` xử lý mọi đồng bộ về sau.** Lời gọi hoàn thành tạo quan hệ bộ nhớ cho công việc đã hoàn tất, không bảo vệ các lần sửa đồng thời sau đó.

## 9. Câu hỏi tự kiểm tra

**1. Một tác vụ chỉ ghi log, không trả giá trị.** Dùng `Runnable`. Nếu cần đợi nó xong qua executor, `submit(runnable)` và `Future<?>.get()` thích hợp.

**2. Một tác vụ tính ra danh sách kết quả.** Dùng `Callable<List<T>>` với `ExecutorService.submit`; kiểu của `Future` là `Future<List<T>>`. Nếu muốn trả collection để nhiều luồng đọc tiếp, nên thiết kế khả năng bất biến hoặc đồng bộ phù hợp.

**3. Vì sao `new Thread(() -> 42)` không diễn tả kết quả kiểu `Callable<Integer>`?** Lambda cho `Thread(Runnable)` phải tương thích với `void run()`; expression body dạng phép tính thuần `42` không phải statement expression hợp lệ cho void-compatible lambda. Để trả một số nguyên, dùng `Callable<Integer>` và `FutureTask` hoặc `submit`.

**4. Vì sao `future.isDone()` là `true` nhưng `future.get()` vẫn ném exception?** Vì `isDone` bao gồm thành công, lỗi và hủy, không chỉ thành công.

**5. Người gọi timeout ở `future.get(1, SECONDS)`; tác vụ có chắc đã dừng?** Không. Timeout chỉ dừng việc đợi của caller. Cần quyết định có yêu cầu cancel hay không và thiết kế task hỗ trợ interrupt/timeout từ chính nó.

**6. Trong hai cách `submit(runnable, "OK")` và `submit(callableReturningOK)`, ai tạo ra chuỗi trả về?** Ở cách đầu, caller cấp chuỗi `"OK"` từ trước; ở cách sau, `Callable.call()` tính/trả giá trị, và `get()` nhận lại kết quả đó.

**Ghi nhớ:** `Runnable` và `Callable` định nghĩa công việc; `Thread` hoặc `ExecutorService` đảm nhận thực thi; `Future`/`FutureTask` biểu diễn điểm đồng bộ và kênh nhận **kết quả hoặc lỗi**. Chọn kiểu tác vụ theo nhu cầu trả giá trị, rồi chọn cách lấy kết quả theo nhu cầu điều phối luồng, timeout và xử lý thất bại.