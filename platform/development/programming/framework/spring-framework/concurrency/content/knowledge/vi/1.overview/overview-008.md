# Lộ trình học và kiến thức Java concurrency cần có

## 1. Mục tiêu và vị trí trong Spring Framework concurrency

Concurrency (lập trình đồng thời) là khả năng quản lý nhiều công việc có thời gian thực thi chồng lấn; parallelism (song song) là thực sự chạy nhiều công việc cùng lúc trên nhiều lõi xử lý. Một ứng dụng Java có thể xử lý đồng thời nhiều yêu cầu dù không phải mọi thao tác đều chạy song song.

Trước khi học `TaskExecutor`, `@Async`, `TaskScheduler` hay cách Spring quản lý tác vụ nền, cần hiểu những vấn đề mà các cơ chế đó giải quyết: tạo và quản lý luồng, chia sẻ trạng thái an toàn, đồng bộ, hủy tác vụ, xử lý lỗi, giới hạn tài nguyên và kiểm thử. Spring cung cấp tầng trừu tượng/tích hợp, nhưng quy tắc Java Memory Model và vòng đời tác vụ vẫn có hiệu lực.

Sau bài này, người học nên có thể:

- Phân biệt concurrency, parallelism, asynchronous execution, non-blocking I/O và multithreading.
- Giải thích race condition, visibility, atomicity, ordering và quan hệ *happens-before*.
- Chọn giữa `synchronized`, `volatile`, atomic variables, locks và concurrent collections theo loại trạng thái được chia sẻ.
- Dùng `ExecutorService`, `Future`, `CompletableFuture` và cơ chế phối hợp để tổ chức công việc có kiểm soát.
- Thiết kế đường hủy bằng interruption, timeout và shutdown; tránh deadlock, starvation và tạo quá nhiều tác vụ.
- Hiểu virtual threads của Java 21 và liên hệ được các khái niệm Java với concurrency trong Spring.

**Điểm xuất phát:** nắm vững lớp/đối tượng, interface và lambda, exception handling, generic, collections, try/finally và cách biên dịch chương trình Java. Các ví dụ mặc định chạy trên Java 17+, trừ phần virtual threads ghi rõ Java 21+.

## 2. Bức tranh tổng thể: vấn đề nào dẫn tới công cụ nào?

| Vấn đề | Kiến thức/công cụ Java cần học | Khi nào dùng |
| --- | --- | --- |
| Có công việc độc lập chạy ngoài luồng gọi | `Thread`, `Runnable`, `Callable` | Hiểu mô hình thực thi cơ bản |
| Nhiều luồng cùng đọc/ghi trạng thái | Java Memory Model, `synchronized`, `volatile`, `AtomicInteger` | Đảm bảo tính đúng đắn |
| Cần phối hợp thời điểm và kết quả | `join`, `Future`, `CountDownLatch`, `BlockingQueue` | Tránh phụ thuộc vào `sleep` để đoán thời điểm |
| Nhiều tác vụ cần được quản lý | `ExecutorService`, thread pool, queue, shutdown | Quản lý tài nguyên và vòng đời |
| Cần kết hợp chuỗi tác vụ bất đồng bộ | `CompletableFuture` | Chuyển đổi, kết hợp kết quả, xử lý lỗi |
| Nhiều yêu cầu chờ I/O | Virtual threads (Java 21+) và giới hạn tải | Tăng khả năng phục vụ khi tác vụ thường chờ |
| Đưa concurrency vào Spring | `TaskExecutor`, `@Async`, `TaskScheduler` | Gắn mô hình tác vụ Java với cấu hình và vòng đời ứng dụng |

Không chọn công cụ chỉ vì “chạy nhanh hơn”. Trước tiên xác định tác vụ **CPU-bound** (tính toán) hay **I/O-bound** (chờ mạng, tệp, cơ sở dữ liệu), có chia sẻ dữ liệu hay không, có giới hạn tài nguyên nào và kết quả/lỗi phải trả về đâu.

## 3. Mô hình thread và vòng đời thực thi

Một *process* có vùng tài nguyên riêng; trong Java, nhiều thread của cùng JVM thường chia sẻ heap nhưng mỗi thread có call stack riêng. Dữ liệu trong các đối tượng dùng chung có thể bị truy cập đồng thời. Việc một biến được khai báo trong phương thức không tự bảo đảm an toàn nếu tham chiếu của nó trỏ tới đối tượng có thể thay đổi và được chia sẻ.

- `Thread` đại diện cho luồng thực thi; `Runnable` mô tả tác vụ không trả kết quả; `Callable<V>` mô tả tác vụ trả kết quả hoặc ném ngoại lệ.
- `start()` yêu cầu JVM bắt đầu luồng mới; gọi trực tiếp `run()` chỉ là lời gọi phương thức trên luồng hiện tại.
- `join()` đợi một thread kết thúc. `sleep()` chỉ tạm dừng thread hiện tại, **không** tạo ra cam kết rằng thread khác đã hoàn thành.
- Các trạng thái Java `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED` phản ánh trạng thái theo API; `RUNNABLE` không có nghĩa là thread chắc chắn đang dùng CPU tại thời điểm quan sát.
- Thread không phải daemon có thể giữ JVM còn hoạt động; daemon thread không phù hợp cho công việc bắt buộc phải hoàn tất trước khi ứng dụng dừng.

Ví dụ đầy đủ `ThreadBasics.java`:

```java
public class ThreadBasics {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> System.out.println("Worker finished"));
        worker.start();
        worker.join();
        System.out.println("Main finished");
    }
}
```

```bash
javac ThreadBasics.java
java ThreadBasics
```

Kết quả:

```text
Worker finished
Main finished
```

Thứ tự này được bảo đảm vì `join()` chờ worker kết thúc trước khi thread chính in dòng thứ hai. Không suy luận thứ tự chạy chỉ từ thứ tự gọi `start()` nếu không có phép phối hợp.

## 4. Race condition và Java Memory Model: nền tảng bắt buộc

**Race condition** xuất hiện khi kết quả phụ thuộc vào thứ tự xen kẽ thao tác giữa các thread mà chương trình không kiểm soát đúng. Ví dụ `counter++` thực chất gồm đọc giá trị, cộng 1 rồi ghi lại; hai thread có thể cùng đọc một giá trị và làm mất một lần tăng.

Cần phân biệt ba tính chất:

1. **Atomicity:** một thao tác được quan sát như một đơn vị không bị xen kẽ. `counter++` trên biến `int` dùng chung không atomic.
2. **Visibility:** cập nhật của thread này có được thread khác nhìn thấy đúng lúc hay không.
3. **Ordering:** compiler, CPU và JVM có thể sắp xếp lại thao tác trong giới hạn cho phép; không thể dựa vào trực giác về thứ tự mã nguồn giữa các thread.

Java Memory Model (JMM) định nghĩa khi nào các thao tác có quan hệ *happens-before*. Một số quy tắc quan trọng:

- Các thao tác trước `Thread.start()` trong thread gọi happens-before các thao tác của thread mới.
- Mọi hành động của một thread happens-before hành động khác sau khi `join()` trên thread đó trả về thành công.
- Thao tác mở khóa monitor happens-before lần khóa tiếp theo trên chính monitor đó.
- Một lần ghi `volatile` happens-before lần đọc tiếp theo đối với cùng biến `volatile`.
- Những thao tác trước `CountDownLatch.countDown()` happens-before những thao tác sau khi thread khác thoát `await()` thành công.

Không có quan hệ đồng bộ phù hợp thì mã có *data race* có thể đọc giá trị cũ hoặc biểu hiện hành vi bất ngờ. Thêm `sleep` không sửa được lỗi bộ nhớ.

### 4.1. Chọn cơ chế bảo vệ trạng thái

| Cơ chế | Cung cấp | Giới hạn |
| --- | --- | --- |
| `synchronized` | Mutual exclusion, visibility khi vào/ra monitor, lock có thể reentrant | Giữ khóa lâu làm giảm concurrency; cần tránh khóa theo nhiều thứ tự |
| `volatile` | Visibility và ordering cho đọc/ghi một biến; phù hợp cờ trạng thái | Không biến phép đọc–sửa–ghi phức hợp thành atomic |
| `AtomicInteger` / `AtomicReference` | Thao tác atomic riêng lẻ dựa trên CAS/biến thể | Không tự bảo đảm invariant trải trên nhiều trường độc lập |
| `ReentrantLock` | Khóa tường minh, `tryLock`, khóa có thể ngắt khi chờ | Phải `unlock` trong `finally` |
| Dữ liệu immutable | Tránh sửa trạng thái sau khi tạo, dễ chia sẻ | Vẫn cần *safe publication* khi công bố đối tượng |
| Concurrent collections | Cơ chế đồng bộ chuyên biệt theo cấu trúc dữ liệu | Chuỗi nhiều thao tác có thể vẫn cần phối hợp bổ sung |

Một cờ `volatile boolean running` phù hợp để một thread báo thread khác dừng vòng lặp, nếu vòng lặp thường xuyên kiểm tra cờ. Ngược lại, `volatile int count` **không** làm `count++` an toàn; cần atomic variable hoặc vùng khóa. Với điều kiện liên quan nhiều biến, bảo vệ toàn bộ invariant bằng cùng một cơ chế đồng bộ.

### 4.2. Ví dụ đếm an toàn với AtomicInteger

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();
        Runnable increment = () -> {
            for (int i = 0; i < 1_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(counter.get());
    }
}
```

```bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
```

Kết quả:

```text
2000
```

`incrementAndGet()` cập nhật atomic; hai lần `join()` bảo đảm chương trình đợi đủ hai thread trước khi đọc. Nếu thay bằng biến `int` dùng chung rồi tăng bằng `++`, giá trị cuối có thể nhỏ hơn 2000, dù đôi khi tình cờ bằng 2000; đó không phải một bài kiểm thử đúng đắn.

### 4.3. Ví dụ truyền tín hiệu và bảo đảm visibility

```java
import java.util.concurrent.CountDownLatch;

public class LatchDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        int[] shared = {0};

        Thread reader = new Thread(() -> {
            try {
                ready.await();
                System.out.println(shared[0]);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        reader.start();

        shared[0] = 42;
        ready.countDown();
        reader.join();
    }
}
```

```bash
javac LatchDemo.java
java LatchDemo
```

Kết quả khi không có yêu cầu ngắt ngoài chương trình:

```text
42
```

`countDown()` giải phóng thread đang `await()` và thiết lập quan hệ happens-before cho lần ghi trước đó. `join()` giúp thread chính đợi việc in hoàn tất. Không cần thêm `volatile` cho `shared[0]` trong đúng trình tự đồng bộ của ví dụ này.

## 5. Phối hợp giữa các tác vụ

Khi nhiều tác vụ phụ thuộc nhau, hãy diễn đạt sự phụ thuộc bằng primitive rõ ràng:

- `CountDownLatch(n)`: một hoặc nhiều thread đợi `n` sự kiện; latch chỉ dùng một lượt, không reset.
- `CyclicBarrier`: nhiều thread gặp nhau ở điểm đồng bộ theo vòng; hữu ích khi các pha thực sự cần bước cùng nhau.
- `Phaser`: phối hợp nhiều pha với số thành viên linh hoạt hơn.
- `Semaphore`: giới hạn số tác vụ đồng thời sử dụng tài nguyên; acquire/release phải cân bằng, kể cả khi có exception.
- `BlockingQueue`: kênh producer–consumer có cơ chế chờ khi lấy/đưa phần tử; queue có dung lượng giới hạn giúp áp dụng *backpressure*.
- `Condition` đi kèm `Lock`: chờ một điều kiện trạng thái; kiểm tra điều kiện trong vòng `while`, không dùng `if` đơn lẻ, vì có thể có lần đánh thức không đáp ứng điều kiện.

Chỉ dùng `wait()/notify()/notifyAll()` sau khi hiểu monitor, điều kiện vòng lặp và yêu cầu giữ khóa; trong phần lớn ứng dụng nên ưu tiên công cụ cấp cao từ `java.util.concurrent`.

Nguyên tắc: chia sẻ dữ liệu càng ít càng tốt. Bất biến (*immutable value*), message passing qua queue và tách trạng thái theo từng tác vụ thường đơn giản hơn một mạng lưới khóa.

## 6. ExecutorService, thread pool và Future

Tạo `new Thread(...)` cho mọi yêu cầu dễ khiến vòng đời và tài nguyên không được kiểm soát. `Executor` là cơ chế nộp công việc; `ExecutorService` thêm cơ chế nộp tác vụ có kết quả và quản lý shutdown; `Future<T>` đại diện cho kết quả có thể chưa sẵn sàng.

Quy trình tối thiểu:

1. Chọn executor phù hợp với đặc điểm tải và giới hạn tài nguyên.
2. Nộp `Runnable` hoặc `Callable<T>` bằng `execute`/`submit`.
3. Nhận kết quả qua `Future.get()` hoặc thiết kế chuỗi bất đồng bộ; `get()` có thể block và ném `ExecutionException`.
4. Đặt timeout khi việc chờ không được phép vô hạn; xử lý `InterruptedException`.
5. `shutdown()` ngừng nhận công việc mới nhưng để tác vụ đã nhận hoàn tất; `shutdownNow()` cố gắng ngắt các tác vụ đang chạy và trả lại danh sách chưa bắt đầu, **không** bảo đảm dừng cưỡng bức.
6. Nếu cần, dùng `awaitTermination` để đợi executor kết thúc theo một thời hạn.

Ví dụ hoàn chỉnh `ExecutorDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> answer = pool.submit(() -> 40 + 2);
            System.out.println(answer.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ExecutorDemo.java
java ExecutorDemo
```

Kết quả:

```text
42
```

Dùng `finally` bảo đảm gọi `shutdown()` cả khi `get()` thất bại. Trong ứng dụng dài hạn, executor thường thuộc vòng đời của một thành phần quản lý, thay vì tạo một pool mới cho mỗi lời gọi.

### 6.1. Hiểu pool và giới hạn tải

Pool có ít thread thích hợp để giới hạn lượng tính toán CPU đồng thời; pool nhiều thread phục vụ tác vụ I/O blocking có thể cải thiện mức sử dụng CPU nhưng gây tốn memory và chuyển ngữ cảnh. Số lượng thích hợp phụ thuộc cấu hình máy, thời gian chờ, tài nguyên downstream và SLA; không có “một con số tốt cho mọi ứng dụng”.

Bốn chỉ số cần quan sát: số tác vụ đang chạy, độ dài hàng đợi, thời gian chờ trong hàng đợi, và tỷ lệ từ chối/timeout. Hàng đợi không giới hạn có thể giấu quá tải bằng độ trễ và bộ nhớ ngày càng tăng. Với `ThreadPoolExecutor` cần hiểu `corePoolSize`, `maximumPoolSize`, `keepAliveTime`, queue và `RejectedExecutionHandler`; tương tác của chúng quan trọng hơn từng con số riêng lẻ.

Tránh deadlock do phụ thuộc trong pool: nếu tất cả worker đều đang `Future.get()` chờ các tác vụ khác cũng phải chạy trên chính pool đã kín worker, hệ thống có thể đứng mãi. Hãy xem lại cấu trúc phụ thuộc, tách loại công việc hoặc dùng composition không chặn phù hợp.

## 7. Cancellation, interruption, timeout và xử lý lỗi

Interruption trong Java là **tín hiệu hợp tác**. `Thread.interrupt()` đặt trạng thái interrupt; nhiều thao tác blocking như `sleep`, `wait`, `BlockingQueue.take` ném `InterruptedException` và thường xóa cờ interrupt khi ném. Mã tác vụ phải có chính sách phản hồi: thoát, dọn dẹp tài nguyên hoặc truyền tín hiệu lên tầng quản lý.

Ví dụ đoạn mã **minh họa trong phương thức chạy tác vụ**:

```java
try {
    // Giả lập một thao tác chờ có thể bị ngắt.
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // giữ tín hiệu để tầng gọi xử lý
    return; // chỉ hợp lệ nếu đang ở trong phương thức trả về void
}
```

Đoạn trên là fragment, không phải một lớp Java độc lập. Với `Callable` cho phép ném `InterruptedException`, có thể để exception truyền ra; không nên bắt rồi im lặng tiếp tục chạy như chưa có yêu cầu hủy.

- `Future.cancel(true)` yêu cầu ngắt nếu tác vụ đang chạy; không ép mã đang chờ CPU hoặc thư viện không hỗ trợ interrupt dừng ngay.
- `Future.get(timeout, unit)` giới hạn thời gian *người gọi đợi*, không tự động hủy công việc đang chạy; cân nhắc gọi `cancel(true)` theo chính sách ứng dụng.
- Timeout ở tầng tác vụ khác với timeout của socket/database/HTTP client. Cần giới hạn tại nguồn I/O để tránh giữ tài nguyên quá lâu.
- Exception trong `submit(Callable/Runnable)` được giữ trong `Future` và bộc lộ qua `get()`; bỏ qua `Future` có thể khiến lỗi bị bỏ sót.
- Không dùng `Thread.stop()` để hủy cưỡng bức; bảo đảm cleanup với `finally` hoặc `try-with-resources`.

## 8. CompletableFuture: xây chuỗi công việc bất đồng bộ

`CompletableFuture<T>` vừa biểu diễn kết quả cuối, vừa hỗ trợ các stage phụ thuộc nhau. Điểm cần học theo thứ tự:

- `supplyAsync` tạo công việc trả kết quả; `runAsync` không trả dữ liệu. Mặc định các phương thức async không truyền executor thường dùng `ForkJoinPool.commonPool()`.
- `thenApply` biến đổi giá trị; `thenCompose` dùng khi bước sau cũng trả về `CompletionStage` để tránh lồng `Future<Future<T>>`; `thenCombine` kết hợp hai kết quả độc lập.
- `thenApplyAsync`/`thenComposeAsync` cho phép chỉ định executor; method không có hậu tố `Async` không mặc nhiên chạy trên thread riêng, và có thể chạy ngay trong thread hoàn thành stage trước.
- `exceptionally` tạo giá trị fallback sau lỗi; `handle` xử lý cả thành công/lỗi; `whenComplete` quan sát kết quả và side effect, không phải cơ chế thay đổi kiểu kết quả.
- `join()` và `get()` đều có thể chặn khi chưa hoàn thành; `join()` bọc lỗi theo hướng unchecked (`CompletionException`), còn `get()` dùng checked exceptions.
- Khi đã có chuỗi stages, ưu tiên ghép pipeline thay vì gọi `join()` giữa từng bước, đặc biệt trong môi trường số worker hạn chế.

Ví dụ đầy đủ `CompletableFutureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> "java")
                        .thenApply(String::toUpperCase);

        System.out.println(result.join());
    }
}
```

```bash
javac CompletableFutureDemo.java
java CompletableFutureDemo
```

Kết quả:

```text
JAVA
```

Không suy ra tên thread hoặc thứ tự chạy stage từ kết quả này. Trong ứng dụng có I/O blocking, cân nhắc executor riêng có giới hạn và lifecycle rõ ràng thay cho mặc định common pool.

## 9. Concurrent collections, lock và thread-local state

### 9.1. Cấu trúc dữ liệu dùng chung

- `ConcurrentHashMap` hỗ trợ nhiều truy cập đồng thời và các thao tác atomic theo key như `compute`, `merge`, `putIfAbsent`. Mẫu `if (!map.containsKey(k)) map.put(k, v)` gồm hai thao tác riêng, không tự atomic.
- `CopyOnWriteArrayList` phù hợp trường hợp đọc rất nhiều, ghi rất ít; mỗi lần thay đổi có chi phí sao chép mảng.
- `BlockingQueue` giúp phối hợp producer–consumer; queue có capacity giới hạn thường an toàn hơn queue tăng vô hạn khi tải lớn.
- `ConcurrentLinkedQueue` là queue thread-safe không chặn; không tự tạo giới hạn dung lượng/backpressure.
- Bản thân một collection thread-safe không biến cả luồng xử lý gồm nhiều câu lệnh thành transaction. Cần xác định invariant của nghiệp vụ.

### 9.2. Khi nào cần Lock?

`ReentrantLock` cho phép chờ có timeout hoặc phản hồi interrupt khi giành khóa, nhưng phải luôn mở khóa đúng cách:

```java
lock.lock();
try {
    // Truy cập trạng thái dùng chung đã được bảo vệ.
} finally {
    lock.unlock();
}
```

Đây là fragment minh họa, giả định `lock` đã là `ReentrantLock` được khởi tạo và chia sẻ. `ReadWriteLock`/`StampedLock` có ích cho một số mô hình nhiều đọc ít ghi nhưng tăng độ phức tạp; chỉ sử dụng sau khi đo và xác minh tính đúng đắn.

### 9.3. ThreadLocal và ranh giới thread

`ThreadLocal<T>` lưu giá trị theo từng thread, **không** truyền tự động giữa executor worker khác nhau. Trong pool, worker được tái sử dụng, vì thế dữ liệu request còn tồn tại sau khi tác vụ kết thúc có thể gây rò rỉ hoặc lẫn ngữ cảnh. Khi đặt ThreadLocal thủ công, thường cần `remove()` trong `finally`. Không dùng ThreadLocal để thay cơ chế truyền tham số rõ ràng.

Trong Spring, transaction context, logging context (MDC) và một số security/request context thường gắn với thread. Việc chuyển việc qua `@Async` hoặc executor có thể làm mất ngữ cảnh, nên phải dùng cơ chế truyền ngữ cảnh được hỗ trợ và kiểm soát vòng đời; không giả định “cùng một request” nghĩa là “cùng một thread”.

## 10. Virtual threads của Java 21: bổ sung vào lộ trình

Java 21 cung cấp virtual threads ở mức ổn định. Virtual thread vẫn có ngữ nghĩa `Thread` của Java, nhưng nhiều virtual threads có thể được JVM quản lý trên một số lượng nhỏ carrier platform threads. Chúng đặc biệt hữu ích cho tác vụ có nhiều thời gian **chờ I/O blocking**, giúp viết mã tuần tự dễ hiểu mà vẫn đạt concurrency cao.

Ví dụ đầy đủ, **chỉ chạy trên Java 21+**, `VirtualThreadDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> result = executor.submit(() -> "hello virtual");
            System.out.println(result.get());
        }
    }
}
```

```bash
javac VirtualThreadDemo.java
java VirtualThreadDemo
```

Kết quả:

```text
hello virtual
```

Virtual threads **không** làm tính toán CPU nhanh hơn số lõi có thể xử lý, không khiến cấu trúc dữ liệu tự thread-safe và không làm biến mất giới hạn connection pool, database hoặc API bên ngoài. Không dùng “pool virtual threads để hạn chế số luồng”; khi cần giới hạn concurrency đối với tài nguyên bên ngoài, dùng semaphore, connection pool hoặc cơ chế backpressure. Trên Java 21, một số tình huống blocking bên trong monitor `synchronized` còn có thể giữ carrier thread (pinning); cần đo trên đúng phiên bản JDK đang triển khai. Hiểu platform threads và executor thông thường trước khi chọn virtual threads.

## 11. Những lỗi concurrency thường gặp và cách nhận biết

| Triệu chứng | Nguyên nhân hay gặp | Hướng khắc phục |
| --- | --- | --- |
| Counter hoặc tổng cuối bị thiếu ngẫu nhiên | Race trong read–modify–write | Atomic operation hoặc khóa bảo vệ invariant |
| Thread dường như không thấy cờ dừng | Không có bảo đảm visibility | `volatile`, khóa hoặc primitive đồng bộ |
| Ứng dụng đứng dù CPU thấp | Deadlock, chờ vòng hoặc tác vụ chờ trong pool kín | Thread dump, xác định chuỗi khóa/`Future.get`, tổ chức lại phụ thuộc |
| Độ trễ tăng và memory tăng theo tải | Queue vô hạn, không có backpressure | Bounded queue, timeout, rejection policy |
| Có exception nhưng luồng gọi không thấy | `Future` bị bỏ qua hoặc xử lý lỗi bất đồng bộ thiếu | Quan sát completion/error và logging có ngữ cảnh |
| Shutdown kéo dài, tác vụ không dừng | Không xử lý interruption hoặc I/O không có timeout | Cooperative cancellation, timeout tại nguồn |
| Transaction/log context sai khi dùng async | Ngữ cảnh thread-local không tự chuyển | Truyền context đúng cách, thiết kế transaction boundary rõ |
| Test lúc được lúc không | Dùng `sleep` để giả định thứ tự, hoặc có data race | Latch/barrier, future, timeout rõ ràng, stress test |

Ba khái niệm khác nhau: **deadlock** là chuỗi chờ mà các bên không thể tiến lên; **starvation** là tác vụ không được cấp tài nguyên/cơ hội chạy đủ; **livelock** là các bên liên tục phản ứng nhưng không đạt tiến triển. Cả ba đều cần phân tích tiến triển hệ thống, không chỉ “thêm thread”.

## 12. Kiểm thử, đo đạc và vận hành

Concurrency cần chứng minh cả **correctness** lẫn **performance**:

1. Viết invariant cụ thể: ví dụ “1000 yêu cầu thành công thì bộ đếm chính xác tăng 1000”, “mỗi job chỉ xử lý một lần”, “không có tác vụ chạy sau shutdown”.
2. Tạo điểm bắt đầu có điều khiển bằng `CountDownLatch`/barrier; tránh dùng `Thread.sleep` thay cơ chế đồng bộ.
3. Dùng timeout cho test và các thao tác chờ, bảo đảm test lỗi kết thúc có thông tin thay vì treo vô hạn.
4. Chạy nhiều lượt với tải và lịch thực thi khác nhau để tăng cơ hội lộ race; kết quả test “xanh” không phải chứng minh tuyệt đối rằng không có race.
5. Đọc thread dump để xem stack, trạng thái thread, monitor đang giữ/chờ; dùng Java Flight Recorder (JFR) và metric để đo blocking, lock contention, độ dài queue, số task active, timeout và latency.
6. Phân biệt throughput (số công việc hoàn tất mỗi đơn vị thời gian), latency (độ trễ từng công việc) và mức tiêu thụ tài nguyên; throughput tăng không đồng nghĩa latency tốt hơn.
7. Thử tình huống lỗi: task ném exception, client timeout, executor bị từ chối, hủy giữa chừng, shutdown khi còn tác vụ và hệ thống downstream chậm.

Dữ liệu đo chỉ có nghĩa trong bối cảnh workload, cấu hình CPU, JVM, pool và dịch vụ phụ thuộc. Không tối ưu bằng cảm giác.

## 13. Lộ trình học theo chặng và tiêu chí hoàn thành

| Chặng | Học nội dung | Bài thực hành nên hoàn thành | Điều kiện chuyển chặng |
| --- | --- | --- | --- |
| **1. Mô hình thực thi** | Concurrency vs parallelism; `Thread`, `Runnable`, `Callable`, `start/join`, lifecycle | Chạy hai công việc và giải thích thứ tự output khi có/không có `join` | Giải thích vì sao `run()` không tạo thread mới |
| **2. Tính đúng đắn bộ nhớ** | Race, atomicity, visibility, ordering, JMM, happens-before | Tạo race trên counter; sửa bằng `AtomicInteger` và `synchronized` | Chứng minh được vì sao `volatile count++` vẫn sai |
| **3. Phối hợp và hủy** | Latch, queue, semaphore, interrupt, timeout | Producer–consumer với queue hữu hạn; dừng an toàn theo yêu cầu | Không dùng `sleep` làm tín hiệu hoàn thành, không nuốt interrupt |
| **4. Quản lý thực thi** | Executor, pool sizing, queue, Future, shutdown/rejection | Xử lý nhiều jobs có giới hạn và thu kết quả/lỗi | Không rò thread, kiểm soát được overload |
| **5. Async composition** | `CompletableFuture`, các stage, kết hợp/lỗi, executor phù hợp | Chạy song song hai lời gọi giả lập, ghép kết quả, tạo fallback | Phân biệt non-blocking composition với gọi `join` chặn |
| **6. Công cụ bổ sung** | Concurrent collections, lock, ThreadLocal, Java 21 virtual threads | So sánh thiết kế state-sharing với message passing; đo tác vụ I/O chờ | Nêu được trade-off và giới hạn downstream |
| **7. Chuyển sang Spring** | `TaskExecutor`, `@Async`, `TaskScheduler`, lifecycle/context | Một service chạy nền có log, timeout, error handling và test rõ ràng | Biết chọn executor và hiểu context/transaction khi đổi thread |

Đây là thứ tự phụ thuộc kiến thức, không phải cam kết thời lượng cố định. Nếu mới bắt đầu, ưu tiên làm chắc chặng 1–4 trước khi chuyển sang các trừu tượng Spring. Người đã có kinh nghiệm có thể chứng minh năng lực bằng bài thực hành rồi bỏ qua phần đã thành thạo.

### Bài tập tích hợp đề xuất

Xây một chương trình Java xử lý danh sách 100 “công việc” giả lập, tối đa 5 công việc cùng hoạt động; mỗi công việc có ID, kết quả hoặc lỗi. Chương trình cần:

- Không tạo thread tùy tiện; dùng một executor có lifecycle và giới hạn concurrency rõ ràng.
- Thu đủ kết quả thành công, thống kê lỗi chính xác và không để tác vụ chưa hoàn tất bị bỏ quên.
- Có timeout/hủy hợp tác khi vượt deadline; shutdown gọn sau khi hoàn tất.
- Dùng dữ liệu/thread-safe primitives đúng chỗ; chứng minh invariant bằng test nhiều lượt.
- Đo thời gian toàn bộ, số job cùng chạy tối đa và giải thích điều gì xảy ra khi tăng số job lên gấp 10.

Một lời giải tốt có thể lựa chọn pool hữu hạn trên Java 17+, hoặc virtual-thread-per-task executor của Java 21 kết hợp semaphore khi I/O là bottleneck. Điều quan trọng là giải thích được giới hạn tài nguyên, hành vi hủy và tính đúng đắn, không phải chọn API “mới nhất”.

## 14. Ánh xạ kiến thức Java sang Spring Framework concurrency

Khi đã chắc phần Java, người học chuyển sang Spring với các câu hỏi tương ứng:

| Java concurrency | Câu hỏi tương ứng trong Spring |
| --- | --- |
| `Executor` / `ExecutorService` | `TaskExecutor` nào chạy tác vụ và ai quản lý lifecycle/pool? |
| `Future` / `CompletableFuture` | Service `@Async` trả kết quả/lỗi về nơi gọi như thế nào? |
| Thread boundary | Proxy của `@Async` có thực sự được gọi qua Spring bean? Self-invocation có bỏ qua advice không? |
| `ScheduledExecutorService` | `TaskScheduler` / `@Scheduled` định lịch, overlap và shutdown ra sao? |
| Interrupt, timeout, rejection | Khi quá tải hay hủy, chính sách lỗi/giới hạn và quan sát của ứng dụng là gì? |
| `ThreadLocal` và transaction | Security/logging/transaction context được xử lý thế nào qua thread boundary? |
| Virtual threads | Phiên bản JDK và Spring/Boot có cấu hình hỗ trợ nào, và downstream có chịu được concurrency cao không? |

Lưu ý quan trọng: lời gọi `@Async` thông thường hoạt động qua Spring proxy; gọi phương thức async từ một phương thức khác trên chính cùng đối tượng (*self-invocation*) có thể bỏ qua cơ chế proxy. Transaction bound với thread không tự chạy theo thread async; cần xác định lại transaction boundary và context trước khi triển khai. Phần Spring chuyên sâu sẽ giải quyết cách khai báo executor, enable async, cấu hình scheduler, exception handler và quan sát vận hành; bài Java này cung cấp nền tảng để hiểu các quyết định đó.

## 15. Checklist tự đánh giá trước khi học Spring concurrency

- [ ] Tôi phân biệt được việc nhiều task đang chờ với việc nhiều task đang dùng CPU song song.
- [ ] Tôi giải thích được `start`, `run`, `join`, `sleep` và ý nghĩa trạng thái thread.
- [ ] Tôi chỉ ra được race/visibility trong một ví dụ và mô tả quan hệ happens-before giải quyết nó.
- [ ] Tôi hiểu khi nào dùng `volatile`, atomic type, khóa và concurrent collection.
- [ ] Tôi viết được producer–consumer hoặc task pipeline có cơ chế phối hợp đúng, không phụ thuộc vào `sleep`.
- [ ] Tôi dùng executor có shutdown, timeout, kết quả và xử lý lỗi rõ ràng.
- [ ] Tôi biết cách xử lý `InterruptedException` và không giả định `cancel(true)` chắc chắn dừng tác vụ.
- [ ] Tôi kết hợp được nhiều `CompletableFuture` và phân biệt tác vụ bất đồng bộ với thao tác không chặn.
- [ ] Tôi nhận diện được queue không giới hạn, deadlock, thread starvation và sai lệch do ThreadLocal.
- [ ] Tôi giải thích được khi nào virtual threads hữu ích và giới hạn của chúng.
- [ ] Tôi có thể chỉ rõ nơi Spring đổi thread, nơi transaction/context có thể bị ảnh hưởng và phương án kiểm thử.

**Tiêu chuẩn hoàn thành:** tự viết được một ứng dụng concurrency nhỏ, chứng minh tính đúng đắn của dữ liệu chia sẻ, kiểm soát được lỗi/hủy/tài nguyên và giải thích được các quyết định sử dụng thread hoặc executor. Khi đó các tính năng concurrency của Spring trở thành cách tích hợp những nguyên lý đã hiểu vào vòng đời ứng dụng.
