# ThreadFactory để chuẩn hóa cách tạo luồng trong Java

Một ứng dụng Java có nhiều thread cần cách tạo thread nhất quán: tên dễ đọc trong thread dump, chế độ daemon phù hợp, mức ưu tiên hợp lý, xử lý exception, và quy tắc gắn thread với executor. Nếu các nơi trong chương trình trực tiếp gọi `new Thread(...)` với các thiết lập khác nhau, việc vận hành và truy vết sự cố rất khó kiểm soát.

`java.util.concurrent.ThreadFactory` là một **functional interface** cung cấp một điểm tập trung để tạo `Thread`. Nó tách **chính sách tạo thread** khỏi **công việc mà thread sẽ chạy**. Một `ExecutorService` có thể gọi factory mỗi khi cần worker mới; mã gọi executor không cần biết cách đặt tên hoặc cấu hình worker đó.

Bài học này chỉ xét **Java Concurrency và Thread API nói chung**, không triển khai cơ chế quản lý tác vụ riêng của Spring.

## 1. Mục tiêu và mô hình tư duy

Sau bài học, bạn cần phân biệt được các trách nhiệm:

| Thành phần | Trách nhiệm | Không chịu trách nhiệm |
| --- | --- | --- |
| `Runnable` / `Callable` | Mô tả việc cần thực hiện; `Callable` có thể trả kết quả/ném checked exception. | Quyết định cách đặt tên, daemon, số worker. |
| `ThreadFactory` | Tạo một đối tượng `Thread` để chạy `Runnable` được truyền vào và áp dụng chính sách thread. | Lập lịch tác vụ, giới hạn queue, tự khởi chạy thread, thu thập kết quả. |
| `Thread` | Đơn vị thực thi theo Thread API; `start()` khiến JVM bắt đầu thực thi `run()`. | Quản lý một hàng đợi nhiều tác vụ theo chính sách pool. |
| `Executor` / `ExecutorService` | Nhận tác vụ, lập lịch/phân phối chúng; `ExecutorService` thêm `submit`, shutdown và quản lý `Future`. | Bắt buộc tạo một thread mới cho mọi task; hành vi tùy implementation. |
| `ThreadPoolExecutor` | Quy định số worker, queue, timeout, rejection và vòng đời worker của một thread pool. | Dùng `ThreadFactory` để thay thế mọi cấu hình của pool. |

Luồng trách nhiệm thường là:

```text
Ứng dụng submit Runnable/Callable
             |
             v
     ExecutorService
         |  cần worker mới
         v
      ThreadFactory.newThread(Runnable worker)
         |
         v
       Thread (NEW, đã cấu hình)
         |
         v
     Executor gọi start()
         |
         v
   Worker xử lý task/queue
```

Factory **tạo** thread; executor thường **quyết định khi nào cần tạo, khi nào chạy và tái sử dụng**. Nếu gọi factory trực tiếp, chính người gọi phải `start()`, `join()`/chờ có kiểm soát và quản lý vòng đời.

## 2. Hợp đồng của ThreadFactory

Khai báo trong Java:

```java
@FunctionalInterface
public interface ThreadFactory {
    Thread newThread(Runnable r);
}
```

Những điểm cần hiểu chính xác:

1. `newThread(r)` nhận **chính Runnable do bên gọi cung cấp**. Factory phải gắn runnable này vào thread; bỏ qua runnable khiến executor không thể chạy worker theo thiết kế.
2. Thread được trả về thông thường ở trạng thái **`NEW`** (chưa gọi `start()`). Factory không tự gọi `start()`; nếu tự khởi chạy, executor có thể gặp `IllegalThreadStateException` khi cố start lại hoặc gặp race khó đoán.
3. Mỗi lần cần worker mới, factory phải trả về một thread **mới, dùng được**, không tái trả cùng một thread đã từng chạy. `Thread` chỉ được `start()` một lần.
4. Interface về mặt hợp đồng có thể trả `null` khi không thể tạo thread. Tuy nhiên, làm vậy có thể khiến executor không khởi tạo được worker hoặc không tiến triển theo kỳ vọng; trong ứng dụng thông thường nên tạo thread hợp lệ hoặc để lỗi tạo thread lộ rõ và được xử lý ở tầng phù hợp.
5. Không có nghĩa mọi lời gọi `submit()` dẫn tới một lần gọi `newThread()`: thread pool **tái sử dụng** worker.
6. Factory có thể được gọi đồng thời; trạng thái dùng để sinh số thứ tự/tên nên thread-safe. `AtomicInteger` là lựa chọn đơn giản. Không cần khóa quanh toàn bộ phần tạo thread chỉ để tăng bộ đếm.
7. Factory **không bảo đảm** `Runnable` hoàn thành, không bảo đảm thứ tự chạy, fairness, timeout hay số lượng thread hoạt động.

Tên thread là metadata giúp vận hành, không phải khóa duy nhất để nhận diện tác vụ. Một tên có thể trùng giữa hai factory instance; thread ID cũng không nên được coi là business ID lâu dài.

## 3. Ví dụ Java 17+: một factory tùy chỉnh chạy được

Tạo tệp `NamedThreadFactoryDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.atomic.AtomicInteger;

public final class NamedThreadFactoryDemo {

    public static void main(String[] args) throws InterruptedException {
        ThreadFactory factory = new NamedThreadFactory("demo-worker");

        Thread first = factory.newThread(() ->
                System.out.println("Task 1: "
                        + Thread.currentThread().getName()));
        first.start();
        first.join();

        Thread second = factory.newThread(() -> {
            System.out.println("Task 2: "
                    + Thread.currentThread().getName());
            throw new IllegalStateException("demo failure");
        });
        second.start();
        second.join();

        System.out.println("Main completed");
    }

    private static final class NamedThreadFactory implements ThreadFactory {
        private final String prefix;
        private final AtomicInteger sequence = new AtomicInteger();

        private NamedThreadFactory(String prefix) {
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public Thread newThread(Runnable task) {
            Objects.requireNonNull(task, "task");

            String name = prefix + "-" + sequence.incrementAndGet();
            Thread thread = new Thread(task, name);

            // Cấu hình trước khi executor hoặc caller start().
            thread.setDaemon(false);
            thread.setPriority(Thread.NORM_PRIORITY);
            thread.setUncaughtExceptionHandler((failedThread, error) ->
                    System.out.println("Uncaught in "
                            + failedThread.getName() + ": "
                            + error.getClass().getSimpleName()));

            return thread;
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac NamedThreadFactoryDemo.java
java NamedThreadFactoryDemo
```

Kết quả chuẩn (hai lần `join()` khiến thứ tự của ví dụ xác định):

```text
Task 1: demo-worker-1
Task 2: demo-worker-2
Uncaught in demo-worker-2: IllegalStateException
Main completed
```

**Giải thích:**

- `AtomicInteger.incrementAndGet()` cấp số thứ tự không bị mất cập nhật khi nhiều nơi yêu cầu tạo thread đồng thời. Trong phạm vi *cùng một factory instance*, tên được đánh số tăng.
- `new Thread(task, name)` liên kết `Runnable` với thread mới và đặt tên ngay từ khi khởi tạo. Không có task nào chạy bên trong `newThread()`.
- `setDaemon(false)` và `setPriority(Thread.NORM_PRIORITY)` tạo chính sách rõ ràng cho **platform thread**. Phải đặt daemon trước `start()`. Mức ưu tiên chỉ là gợi ý đối với bộ lập lịch, không phải SLA.
- `setUncaughtExceptionHandler` nhận lỗi thoát khỏi `run()` mà không được bắt. Ví dụ chủ động ném `IllegalStateException` để kiểm tra handler; trên chương trình thật nên ghi log/metric với ngữ cảnh phù hợp.
- `join()` chờ thread kết thúc trước khi chuyển bước; ví dụ này dùng chạy tuần tự để stdout xác định, còn trên ứng dụng thật hai thread thường có thể chạy đồng thời.

**Không nên** sửa class mẫu bằng cách thêm `thread.start()` trong `newThread()`: factory phải trả thread chưa start. Nếu chỉ cần chạy một vài thao tác độc lập, factory có thể được dùng trực tiếp như trên, nhưng với luồng tác vụ dài hạn, executor giúp quản lý lifecycle và tài nguyên rõ hơn.

## 4. Dùng ThreadFactory với ExecutorService

Ứng dụng phổ biến nhất là truyền factory vào constructor của executor. Nhiều API `Executors` nhận factory, ví dụ:

```java
Executors.newSingleThreadExecutor(threadFactory);
Executors.newFixedThreadPool(poolSize, threadFactory);
Executors.newCachedThreadPool(threadFactory);
Executors.newScheduledThreadPool(corePoolSize, threadFactory);
```

Chúng khác nhau về chính sách tạo/reuse thread, queue và khả năng tăng số worker. Factory chỉ ảnh hưởng **thread mới mà executor yêu cầu tạo**.

### 4.1 Chương trình chạy độc lập bằng Java 17+

Tạo tệp `ExecutorThreadFactoryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class ExecutorThreadFactoryDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger nextId = new AtomicInteger();

        ThreadFactory factory = task ->
                new Thread(task, "report-worker-" + nextId.incrementAndGet());

        ExecutorService executor = Executors.newSingleThreadExecutor(factory);
        try {
            Future<String> result =
                    executor.submit(() -> Thread.currentThread().getName());
            System.out.println(result.get());
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy:

```bash
javac ExecutorThreadFactoryDemo.java
java ExecutorThreadFactoryDemo
```

Stdout:

```text
report-worker-1
```

Ở đây `executor.submit(...)` nhận **tác vụ**, còn factory nhận `Runnable` nội bộ mà executor tạo ra để phục vụ worker. Một worker có thể thực hiện nhiều tác vụ nối tiếp. Vì vậy không nên lấy giá trị bộ đếm trong factory làm “task ID”: đó là **số lần tạo thread**, không phải số lần submit.

`Future.get()` đợi kết quả tác vụ; trong trường hợp này task trả về tên thread. Nếu tác vụ ném exception, `Future.get()` sẽ ném `ExecutionException` chứa nguyên nhân; nó không chuyển exception đó thành kết quả string. `shutdown()` ngừng nhận task mới và cho các task đã nhận cơ hội hoàn thành. `awaitTermination` có timeout chỉ giới hạn **thời gian đợi**, không tự chứng minh mọi task đã dừng. `shutdownNow()` cố gắng dừng bằng interruption và trả lại tác vụ chưa chạy; code tác vụ phải hợp tác với interruption nếu muốn dừng kịp thời.

### 4.2 ThreadFactory không thay thế cấu hình pool

Xét `newFixedThreadPool(4, factory)`: đây là policy tối đa bốn worker chạy tác vụ đồng thời của pool cố định. Khi bốn worker đã tồn tại và còn hoạt động, các submit mới thường được đưa vào queue, **không** khiến factory tạo thread thứ năm. Ngược lại, `newCachedThreadPool(factory)` có thể tăng số worker lớn khi có nhiều tác vụ ngắn và chưa có worker rảnh, không thích hợp nếu số thread cần được chặn cứng mà chưa thiết kế kiểm soát tải.

Đối với workload cần **queue hữu hạn** và chính sách khi quá tải, có thể dùng `ThreadPoolExecutor` cấu hình tường minh:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,                                  // corePoolSize
        4,                                  // maximumPoolSize
        30, TimeUnit.SECONDS,               // thời gian giữ worker dư
        new ArrayBlockingQueue<>(100),      // queue hữu hạn
        factory,                            // thread policy
        new ThreadPoolExecutor.AbortPolicy() // reject khi quá tải
);
```

Đây là **mảnh mã minh họa**, giả định đã import `ThreadPoolExecutor`, `TimeUnit`, `ArrayBlockingQueue` và có biến `factory` hợp lệ. Cần shutdown pool ở vòng đời ứng dụng. Khi core worker đã bận, `ThreadPoolExecutor` thường **ưu tiên đưa task vào queue** trước khi tăng số worker vượt core; chỉ khi queue không nhận thêm thì mới xét tăng worker tới maximum. `AbortPolicy` báo `RejectedExecutionException` khi không thể nhận task. Những hành vi đó thuộc executor, không thuộc factory.

## 5. Thiết kế chính sách factory nhất quán

Một factory tốt cung cấp cấu hình có ý nghĩa vận hành và giữ trách nhiệm nhỏ. Các chính sách thường gặp:

| Chính sách | Cách thực hiện | Lưu ý |
| --- | --- | --- |
| **Tên có ý nghĩa** | Prefix theo mục đích cộng số thứ tự: `event-dispatch-1`, `file-reader-2` | Tránh tên chứa dữ liệu người dùng/bí mật; prefix ngắn, ổn định. |
| **Daemon/platform thread** | `thread.setDaemon(boolean)` trước start | Daemon không giữ JVM sống; có thể bị dừng khi JVM kết thúc. |
| **Priority** | `thread.setPriority(Thread.NORM_PRIORITY)` hoặc giá trị 1–10 cho platform thread | Không bảo đảm CPU share, fairness, deadline hoặc tốc độ. |
| **Uncaught exception handler** | `setUncaughtExceptionHandler` | Chỉ nhận throwable thoát khỏi thread; không tự bao phủ lỗi được `Future` giữ lại. |
| **ThreadGroup** | Constructor `Thread(ThreadGroup, Runnable, String)` khi thật sự cần | Group không phải cơ chế cách ly tài nguyên hay quản lý pool hiện đại. |
| **ContextClassLoader** | `thread.setContextClassLoader(loader)` nếu có yêu cầu rõ | Có thể ảnh hưởng class loading và giữ classloader sống; phải quản lý vòng đời. |
| **Cấu hình dùng lại** | Inject `ThreadFactory` qua constructor của thành phần sử dụng | Dễ kiểm thử và tránh nhiều nơi viết lại quy tắc tên/handler. |

Nên ưu tiên chính sách tối thiểu, có căn cứ. Không nên tự ý tăng priority toàn bộ worker vì có thể làm thread khác ít được CPU. Không nên đặt daemon `true` cho mọi worker chỉ để chương trình thoát mà không xử lý shutdown; công việc đang chạy có thể bị cắt khi chỉ còn daemon thread.

Nếu một factory gắn `UncaughtExceptionHandler`, xử lý lỗi trong handler cũng cần an toàn. Handler không nên thực hiện tác vụ blocking không giới hạn, gọi lại tài nguyên lỗi đang giữ lock hoặc ném exception mới: handler ném exception sẽ được JVM bỏ qua ở tầng dispatch lỗi, khiến thông tin hỏng khó quan sát.

## 6. defaultThreadFactory và lựa chọn có sẵn

Java cung cấp:

```java
ThreadFactory factory = Executors.defaultThreadFactory();
```

Factory mặc định của `Executors` tạo **platform thread** (JDK 17), đặt tên dạng `pool-N-thread-M`, không daemon, ưu tiên `NORM_PRIORITY` (nếu phù hợp), và sử dụng `ThreadGroup` thích hợp theo thực thi của JDK. Thông thường đây là điểm khởi đầu đủ tốt nếu chưa cần quy tắc riêng.

**So sánh lựa chọn:**

- `new Thread(runnable)`: tạo trực tiếp; lập trình viên phải tự cấu hình và start.
- `Executors.defaultThreadFactory()`: có thể dùng lại khi cấu hình executor và muốn chính sách mặc định nhất quán.
- `Executors.privilegedThreadFactory()`: API cũ gắn với security context lịch sử; không phải hướng ưu tiên cho code Java mới và có thể bị deprecate/remove trong các phiên bản JDK. Đừng dùng như công cụ bảo mật chung.
- **Custom `ThreadFactory`**: cần tên rõ ràng, handler riêng, policy daemon hoặc khả năng inject/test. Chỉ tạo thread và cấu hình nó, đừng nhúng xử lý nghiệp vụ.
- **Java 21+ `Thread.Builder`**: tạo factory cho platform/virtual thread theo cú pháp mới, giải thích ở phần 9.

Factory thường nên là **một instance dùng chung** trong phạm vi executor, để bộ đếm tên không reset mỗi lần submit. Nếu tạo `new NamedThreadFactory("worker")` trong từng lời gọi, nhiều thread có thể đều mang tên `worker-1`, làm thread dump gây nhầm lẫn.

## 7. Exception: khác nhau giữa thread trực tiếp, execute và submit

Cấu hình `UncaughtExceptionHandler` thường bị hiểu nhầm là cơ chế tập trung bắt **mọi** exception của task.

### 7.1 Thread trực tiếp

Khi `new Thread(runnable).start()` chạy và `runnable.run()` ném exception không được bắt, exception thoát khỏi thread và handler tương ứng được gọi. Bài demo đầu đã minh họa chính xác trường hợp này.

### 7.2 Executor.execute(Runnable)

Với các executor dùng platform thread, một unchecked exception thoát khỏi `run()` của tác vụ do `execute` cung cấp có thể thoát tới worker và dẫn đến gọi uncaught handler; `ThreadPoolExecutor` có thể phải thay worker đã chết. Tuy vậy không nên dùng việc một task phá hủy worker làm chính sách lỗi bình thường. Hãy xử lý/retry task tại lớp nghiệp vụ với giới hạn phù hợp.

### 7.3 ExecutorService.submit(...)

`submit()` thường bọc tác vụ trong `FutureTask`. Exception từ task được **ghi nhận trong Future**, vì thế **không thoát khỏi `run()` của worker** để handler của thread bắt. Ví dụ:

```java
Future<?> job = executor.submit(() -> {
    throw new IllegalArgumentException("invalid input");
});

try {
    job.get();
} catch (ExecutionException e) {
    Throwable original = e.getCause();
    // Ghi nhận hoặc xử lý lỗi tác vụ, theo chính sách ứng dụng.
}
```

Mảnh này giả định có `ExecutorService executor` và import `Future`, `ExecutionException`. `get()` còn có thể ném `InterruptedException`; khi task bị hủy, nó có thể ném `CancellationException`. Trong ứng dụng, cần xử lý cả vòng đời Future và hủy tác vụ theo hợp đồng API.

**Nguyên tắc:** dùng `UncaughtExceptionHandler` cho lỗi không được bắt ở mức thread, còn lỗi của tác vụ asynchronous phải được xử lý ở mức `Future`/kết quả, chính sách retry và giám sát tác vụ. Một factory không biến `submit` thành fire-and-forget an toàn.

## 8. ThreadLocal, context và việc tái sử dụng worker

Tác vụ chạy trên worker của pool, **không nhất thiết** là thread đã gọi `submit()`. `ThreadLocal` đặt ở thread submit không tự trở thành `ThreadLocal` trong worker khác. Với `InheritableThreadLocal`, giá trị có thể được kế thừa **khi thread được tạo**, nhưng pool tạo worker trước hoặc tái sử dụng worker, nên kết quả không phải “context của từng task” và có nguy cơ lẫn dữ liệu giữa tác vụ.

Ví dụ mảnh mã dễ gây lỗi:

```java
static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

void process(String requestId) {
    REQUEST_ID.set(requestId);
    // ... business logic ...
    REQUEST_ID.remove();
}
```

Mảnh trên là phương pháp **thiết lập và dọn dẹp trong cùng thread**, nhưng bản thân nó chưa xử lý trường hợp `business logic` ném exception. Trong code thật, đặt cleanup trong `finally`:

```java
String previous = REQUEST_ID.get();
try {
    REQUEST_ID.set(requestId);
    // Chạy tác vụ ở đúng worker cần context.
} finally {
    if (previous == null) {
        REQUEST_ID.remove();
    } else {
        REQUEST_ID.set(previous);
    }
}
```

Đây là mảnh mã minh họa, giả định `REQUEST_ID` và `requestId` đã có. Nếu cần chuyển context giữa thread, capture **giá trị context phù hợp** tại lúc submit rồi gắn, sau đó cleanup ở **thời điểm thực thi trên worker**. Tránh đọc `ThreadLocal` của thread submit ngay trong factory rồi áp dụng mặc định cho mọi task của một worker: worker sống lâu và chạy nhiều request, context của lần tạo thread sẽ lỗi thời.

Không truyền dữ liệu bí mật, classloader hoặc context không cần thiết cho thread lâu sống. Factory chỉ nên quản lý thuộc tính thread; việc truyền context **theo từng task** cần một wrapper/decorator ở lớp thực thi task.

## 9. Platform thread và virtual thread từ Java 21

JDK 17 dùng `ThreadFactory` để tạo platform thread thông thường; với Java 21, `Thread.Builder` thêm cách khai báo factory cho cả platform và virtual thread.

Ví dụ Java 21+ tạo virtual thread factory:

```java
ThreadFactory factory = Thread.ofVirtual()
        .name("v-worker-", 0)
        .factory();
```

`Thread.ofVirtual()` tạo builder cho **virtual thread**; `name(prefix, start)` đặt tiền tố và số thứ tự; `factory()` tạo factory áp dụng cấu hình đó cho mỗi virtual thread mới.

### Ví dụ Java 21+ chạy độc lập

Tạo `VirtualFactoryDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.Future;

public final class VirtualFactoryDemo {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual()
                .name("v-worker-", 0)
                .factory();

        try (ExecutorService executor =
                Executors.newThreadPerTaskExecutor(factory)) {
            Future<String> future = executor.submit(() ->
                    Thread.currentThread().getName()
                    + ", virtual=" + Thread.currentThread().isVirtual());
            System.out.println(future.get());
        }
    }
}
```

Chạy bằng **JDK 21 trở lên**:

```bash
javac VirtualFactoryDemo.java
java VirtualFactoryDemo
```

Stdout:

```text
v-worker-0, virtual=true
```

`Executors.newThreadPerTaskExecutor(factory)` tạo **một thread mới cho mỗi task**, thay vì tái sử dụng worker của fixed pool. Với virtual thread, mô hình một thread cho mỗi tác vụ blocking thường khả thi hơn rất nhiều so với một platform thread cho mỗi task; tuy nhiên vẫn cần giới hạn truy cập DB, network, connection pool và tài nguyên downstream bằng cơ chế riêng. Factory **không** tự áp đặt backpressure.

Virtual thread trong Java 21 là daemon thread; không thể đặt priority/daemon theo cách platform thread tùy biến được. Đừng sao chép nguyên xi factory gọi `thread.setDaemon(false)` hoặc `setPriority` sang virtual thread. Nếu cần đặt cấu hình cho virtual thread, dùng builder hỗ trợ, ví dụ `Thread.ofVirtual().name(...).uncaughtExceptionHandler(...).factory()`.

Virtual thread vẫn dùng được `ThreadFactory`, `Runnable` và `ExecutorService`, nhưng mục tiêu dùng virtual thread không phải tạo một “virtual fixed pool” nhỏ để hạn chế số thread. Điều tiết tải bằng semaphore, queue hay giới hạn tại tài nguyên thực sự khan hiếm thường rõ ràng hơn. Nếu cần hỗ trợ Java 17, **không** đưa `Thread.ofVirtual()` vào code biên dịch với JDK 17: API này chưa có tại đó.

Với platform thread trên JDK 21, cũng có thể viết `Thread.ofPlatform().name("platform-", 0).factory()` thay cho custom factory đơn giản. Cần phân biệt rõ runtime/JDK mục tiêu trước khi chọn API.

## 10. Giới hạn hiệu năng, safety và liveness

Không nên nhầm `ThreadFactory` với một giải pháp concurrency hoàn chỉnh:

- **Safety:** factory không làm dữ liệu chia sẻ trở thành thread-safe; vẫn cần `synchronized`, lock, atomic operation hoặc immutable design phù hợp.
- **Liveness:** factory không ngăn deadlock, livelock, starvation hay chờ vô hạn trong task; cần thiết kế thứ tự khóa, timeout, cancellation và quản lý phụ thuộc giữa tác vụ.
- **Số worker:** factory chỉ tạo thread khi được hỏi; giới hạn tài nguyên nằm ở executor/pool. Một factory tự tạo worker bổ sung trái yêu cầu sẽ phá vỡ policy của executor.
- **Thread reuse:** task có thể chạy trên cùng worker nhiều lần; ThreadLocal và tên thread không phải ID riêng cho task.
- **Throughput/latency:** đặt tên và handler giúp quan sát; không bảo đảm pool nhanh hơn. Cấu hình queue không giới hạn có thể tích tụ backlog, trong khi unbounded thread creation có thể gây áp lực CPU/memory.
- **Thời gian shutdown:** `daemon` không phải chiến lược graceful shutdown. Cần xử lý interruption và deadline hợp lý trong task.
- **Quyền ưu tiên:** `setPriority` không phải cơ chế fairness và hành vi có thể khác giữa nền tảng JVM/hệ điều hành.

Một factory được gọi từ nhiều thread nên nhanh, không blocking lâu và tránh side effect ngoài việc khởi tạo/configure thread. Không gọi callback nghiệp vụ hay I/O trong `newThread()`. Nếu có giới hạn tài nguyên đặc thù, giao cho executor/admission control quyết định có tạo thêm worker hay từ chối task.

## 11. Kiểm thử ThreadFactory

Nên kiểm tra các thuộc tính **có thể quan sát được**, đồng thời không dựa vào thứ tự schedule khó đoán:

1. `newThread(runnable)` trả thread khác `null`, ở trạng thái `NEW` và chưa chạy `Runnable` trước khi gọi `start()`.
2. Thread thực sự chạy đúng `Runnable` đã truyền và hoàn thành khi `join()`.
3. Tên thread có prefix hợp lệ; trong cùng factory, các tên không trùng nhau dưới tranh chấp.
4. Với **platform thread**, daemon/priority/handler đúng chính sách; không dùng test này cho virtual thread khi API không hỗ trợ cùng thuộc tính.
5. Handler nhận exception không được bắt khi thread chạy `run()` sau `start()`; lỗi thoát khỏi lời gọi `run()` trực tiếp lan tới caller như lời gọi phương thức thường, còn lỗi task `submit()` nằm trong `Future`.
6. Khi tích hợp executor, kiểm tra worker được factory tạo thật sự được sử dụng, task hoàn tất, shutdown và tình huống quá tải theo cấu hình pool.

Một harness ngắn xác nhận `newThread()` chưa start:

```java
ThreadFactory factory = r -> new Thread(r, "test-worker");
Thread thread = factory.newThread(() -> { /* không cần in */ });

if (thread.getState() != Thread.State.NEW) {
    throw new AssertionError("Factory started the thread");
}
thread.start();
thread.join();
```

Đây là **mảnh mã minh họa** đặt trong method có thể `throws InterruptedException`, với import `ThreadFactory`. Với thread đã chạy, trạng thái có thể thay đổi rất nhanh; chỉ kiểm tra trạng thái `NEW` **trước khi start** là ổn định. Test concurrent uniqueness nên dùng tập hợp thread-safe, barrier để tăng tranh chấp, rồi kiểm tra tất cả tên sau khi tạo xong; không suy ra correctness chỉ từ một lần chạy.

Trong môi trường thực tế, tên thread có prefix nhất quán giúp tìm thread dump, nhưng việc điều tra còn cần task ID/correlation ID riêng, queue depth, saturation và thời gian chờ. Đừng dùng tên worker để suy ngược nguyên nhân lỗi của một request cụ thể khi worker chạy nhiều request.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách đúng |
| --- | --- | --- |
| Gọi `thread.start()` trong factory | Executor có thể start lại và ném `IllegalThreadStateException`; race ngoài kiểm soát. | Chỉ tạo/configure và trả thread `NEW`. |
| Bỏ qua `Runnable` đầu vào | Executor tạo worker nhưng không chạy được nhiệm vụ worker đã định. | Truyền chính xác runnable vào constructor/builder thread. |
| Mỗi lần `newThread()` lại tạo factory/bộ đếm từ 0 | Tên trùng nhau và chính sách phân tán. | Dùng factory instance sống cùng phạm vi executor. |
| Dùng `int counter++` trong factory bị gọi đồng thời | Mất cập nhật, tên trùng. | `AtomicInteger` hoặc đồng bộ phù hợp. |
| Tự đặt `daemon=true` cho mọi pool | JVM có thể kết thúc khi công việc chưa hoàn tất. | Chọn policy daemon dựa trên yêu cầu, shutdown đúng cách. |
| Tin uncaught handler sẽ bắt lỗi của `submit()` | Lỗi nằm trong `Future` nên dễ bị bỏ sót. | Thu thập `Future` và xử lý `get()`/completion. |
| Dùng priority thay cho kiểm soát tải | Scheduling khó dự đoán và không có SLA. | Cấu hình queue, pool, timeout, giới hạn downstream. |
| Dùng `ThreadLocal` tạo bởi caller để “tự truyền context” | Worker tái sử dụng có context thiếu/sai hoặc lưu dữ liệu cũ. | Bọc từng task, gắn context trong worker và dọn trong `finally`. |
| Gán “mỗi submit = một lần tạo thread” | Đếm task sai, giả định sai về worker reuse. | Phân biệt task, worker thread, executor policy. |
| Gọi `Thread.ofVirtual()` trong Java 17 | Không biên dịch vì API Java 21 chưa tồn tại. | Dùng Java 17 factory hoặc nâng minimum JDK lên 21. |

## 13. Quy trình áp dụng trong dự án Java

1. **Xác định workload và executor.** Tác vụ CPU-bound, I/O-blocking, lịch định kỳ, số lượng request và tốc độ đến khác nhau; chọn executor/pool trước theo yêu cầu tải.
2. **Định nghĩa quy tắc thread.** Prefix tên cho từng vai trò, daemon hay không, handler và chính sách logging; chỉ đặt thuộc tính phục vụ mục tiêu cụ thể.
3. **Tạo một `ThreadFactory` thread-safe.** Mỗi `newThread(r)` trả thread mới ở trạng thái `NEW`, gắn đúng `r`, cấu hình xong rồi trả về.
4. **Truyền factory vào executor.** Tách setup executor khỏi code `submit`; giới hạn core/max, queue, rejection và timeout tại lớp executor.
5. **Quan sát task và lỗi.** `Future`/result ghi nhận exception nghiệp vụ; handler xử lý uncaught exception; theo dõi pool saturation và thread dump.
6. **Định nghĩa shutdown.** Ngừng nhận task, đợi có giới hạn, yêu cầu hủy nếu cần, dọn tài nguyên; phối hợp interruption trong runnable.
7. **Kiểm tra độ đúng và tải.** Test contract factory, thread naming, lỗi task, concurrent creation, lifecycle; stress test theo workload thực.

### Tự kiểm tra

**Câu 1.** `ThreadFactory.newThread(r)` nên trả về thread đã gọi `start()` không?  
**Trả lời:** Không. Caller/executor chịu trách nhiệm start; thread trả về cần mới và chưa chạy.

**Câu 2.** Nếu gửi 100 task vào fixed thread pool có 4 worker, factory có nhất thiết được gọi 100 lần không?  
**Trả lời:** Không. Factory chỉ được gọi khi executor cần worker mới; worker có thể chạy nhiều task.

**Câu 3.** Vì sao `AtomicInteger` phù hợp cho bộ đếm tên trong factory?  
**Trả lời:** Khi factory được gọi đồng thời, mỗi lần tăng là atomic, tránh các thread nhận cùng số do mất cập nhật.

**Câu 4.** Vì sao handler trên worker không thấy exception của `executor.submit(() -> { throw ...; })`?  
**Trả lời:** `submit` bọc task và giữ lỗi trong `Future`; phải quan sát qua `Future.get()` hoặc cơ chế completion phù hợp.

**Câu 5.** Muốn chỉ có tối đa 8 task cùng truy cập database thì nên đặt giới hạn ở ThreadFactory không?  
**Trả lời:** Không. Dùng admission control, semaphore, giới hạn pool/connection pool hoặc chính sách queue phù hợp; factory chỉ tạo thread.

**Câu 6.** Khác biệt chính giữa `Executors.newFixedThreadPool(4, factory)` và `Executors.newThreadPerTaskExecutor(Thread.ofVirtual().factory())` là gì?  
**Trả lời:** Cái đầu tái sử dụng số lượng worker giới hạn; cái sau tạo một thread (thường virtual) mới cho mỗi task và là API Java 21+. Vẫn phải quản lý tài nguyên downstream.

**Ghi nhớ:** `ThreadFactory` là nơi chuẩn hóa **cách tạo và cấu hình thread**, giúp mã nhất quán và quan sát dễ hơn. Executor quyết định **khi nào tạo, dùng lại, xếp hàng và dừng worker**; ứng dụng quyết định **logic task, dữ liệu an toàn, hủy bỏ và xử lý lỗi**.