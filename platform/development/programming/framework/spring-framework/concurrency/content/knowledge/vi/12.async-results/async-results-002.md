# Future cho phép chờ kết quả hoặc nhận lỗi khi công việc kết thúc

## 1. Tại sao cần Future?

Trong ứng dụng Java và Spring, công việc có thể được giao cho một worker thread để caller tiếp tục xử lý việc khác. Tuy nhiên, caller vẫn cần biết **task đã kết thúc chưa, kết quả là gì và có lỗi xảy ra không**. Giao diện `java.util.concurrent.Future<V>` cung cấp một **handle đại diện cho kết quả của một phép tính có thể chưa hoàn tất**.

Ví dụ nghiệp vụ: request gửi công việc tạo báo cáo vào một thread pool. Sau đó hệ thống muốn nhận đường dẫn báo cáo, phát hiện thất bại, hoặc không chờ lâu hơn một thời hạn nhất định. Thay vì xem việc gửi task là đã thành công, code giữ lại `Future<Report>` và đọc nó tại điểm thực sự cần kết quả.

Sau bài này, bạn sẽ:

- Hiểu `Future<V>` trong mô hình thread pool và phân biệt **nhận task**, **hoàn tất task**, **thành công**, **thất bại** và **hủy**.
- Sử dụng `get()`, `get(timeout, unit)`, `isDone()`, `isCancelled()` và `cancel(...)` chính xác.
- Bắt `ExecutionException` để lấy **cause là lỗi gốc của task**, phân biệt với `InterruptedException`, `TimeoutException` và `CancellationException`.
- Tạo ví dụ chạy độc lập bằng **Java 17+**, có đầu ra ổn định và kiểm tra timeout/cancellation mà không suy đoán lịch chạy.
- Sử dụng `Future` qua `ExecutorService.submit(...)` của JDK và `AsyncTaskExecutor.submit(...)`/`@Async` trong Spring.
- Biết khi nào `Future` là đủ, khi nào nên dùng `CompletableFuture` để ghép các bước bất đồng bộ, và các rủi ro khi đợi Future bên trong cùng một pool.

**Phiên bản:** Các ví dụ JDK sử dụng Java 17+, ví dụ Spring độc lập dùng Spring Framework 6.1.3 và Java 17+. Chúng minh họa những API ổn định, không phụ thuộc Java 21 virtual threads.

## 2. Mô hình: task chạy ở nơi khác, Future là tay cầm

`Future<V>` không phải một worker thread và cũng không phải bản thân công việc. Nó là đối tượng cho phép caller theo dõi trạng thái của một phép tính được nộp vào executor.

~~~text
Caller thread                            Executor / worker
      |                                          |
      | submit(Callable<V>)                      |
      |----------------------------------------->|
      |<------ Future<V> -----------------------|
      |                                          |
      | làm công việc khác                       | chạy call()
      |                                          |
      | future.get()                             |
      | ------ đợi nếu chưa hoàn thành --------> |
      |                                          |
      |<------- giá trị V / exception ------------|
~~~

Từ lúc nhận được `Future` đến khi gọi `get()`, caller có thể tiếp tục xử lý độc lập. Nếu gọi `get()` **ngay lập tức**, caller có thể bị chặn cho đến khi worker hoàn tất; lợi ích concurrency vẫn có thể có, nhưng không nhất thiết cải thiện độ trễ theo cách bạn mong muốn.

### Bốn tình huống cần phân biệt

| Tình huống | `isDone()` | `isCancelled()` | `get()` |
| --- | --- | --- | --- |
| Task còn đang đợi hoặc chạy | `false` | `false` | Có thể **chặn** |
| Task hoàn thành thành công | `true` | `false` | Trả về `V`; `Runnable` trả `null` |
| Task hoàn thành với exception | `true` | `false` | Ném `ExecutionException`, cause là lỗi thực thi |
| Task bị hủy thành công | `true` | `true` | Ném `CancellationException` |

**Quan trọng:** `isDone() == true` chỉ có nghĩa là task đã **kết thúc theo một cách nào đó**, có thể là thành công, exception hoặc cancellation. Không dùng `isDone()` làm bằng chứng nghiệp vụ thành công.

Một task có thể bị **từ chối ngay ở bước submit** khi pool quá tải hoặc shutdown. Khi đó lời gọi submit có thể ném exception **trước khi trả Future**: không có `Future` để đợi kết quả. Đây là lỗi **admission**, không phải lỗi bên trong task đã được chấp nhận.

## 3. API cốt lõi của Future trong Java 17

`Future<V>` thuộc package `java.util.concurrent`; `V` là kiểu kết quả mong đợi. Những method quan trọng trong API Java 17 là:

| Method | Hành vi | Lưu ý |
| --- | --- | --- |
| `V get()` | Chờ nếu cần, rồi lấy kết quả | Có thể chặn vô thời hạn nếu task không bao giờ hoàn tất |
| `V get(long timeout, TimeUnit unit)` | Chờ tối đa thời gian đã cho rồi lấy kết quả | Ném `TimeoutException` nếu chưa hoàn tất trong thời hạn |
| `boolean isDone()` | Cho biết Future đã kết thúc, gồm cả lỗi/hủy | **Không xác nhận thành công** |
| `boolean isCancelled()` | Cho biết đã bị hủy | `false` không đồng nghĩa task thành công |
| `boolean cancel(boolean mayInterruptIfRunning)` | Thử hủy phép tính | Cần xét implementation và khả năng task hợp tác với interrupt |

Ví dụ chữ ký:

~~~java
// Các chữ ký API dùng để giải thích; không phải class độc lập.
V get() throws InterruptedException, ExecutionException;

V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;

boolean isDone();
boolean isCancelled();
boolean cancel(boolean mayInterruptIfRunning);
~~~

**Lưu ý phiên bản:** Đây là bộ method tương thích Java 17. Các phiên bản JDK mới hơn có thêm tiện ích truy cập trạng thái như `state()`/`resultNow()`/`exceptionNow()`, nhưng không viết code Java 17 dựa trên các method mới đó.

### 3.1. `get()` trả kết quả khi thành công

~~~java
// Fragment: executor là ExecutorService được cấu hình.
Future<Integer> answer = executor.submit(() -> 21 * 2);
Integer result = answer.get(); // 42 khi thành công
~~~

`submit(Callable<Integer>)` nhận một lambda có trả giá trị; `Future<Integer>` cho phép lấy kết quả. `get()` **chặn thread gọi** nếu chưa hoàn thành. Nếu task đã hoàn thành, method trở về ngay. `get()` không thực thi task thay cho worker.

### 3.2. `submit(Runnable)` vẫn trả Future nhưng không có payload

~~~java
// Fragment: Runnable không trả dữ liệu.
Future<?> saved = executor.submit(() -> saveRecord());
Object result = saved.get(); // null nếu chạy thành công
~~~

Ở đây `saveRecord()` là hàm ứng dụng chưa được định nghĩa, nên đoạn code không độc lập. Với `Runnable`, future theo dõi hoàn tất và lỗi; kết quả thành công thường là `null`. Nếu cần trả một giá trị nghiệp vụ, dùng `Callable<T>` hoặc overload `submit(Runnable, result)` của `ExecutorService`.

Không nhầm với `execute(Runnable)`: method `execute` nhận công việc nhưng có kiểu trả về `void`, nên không trực tiếp cung cấp Future để theo dõi.

### 3.3. `get(timeout, unit)` giới hạn thời gian đợi của caller

~~~java
// Fragment: lấy kết quả trong tối đa 2 giây chờ.
String data = future.get(2, TimeUnit.SECONDS);
~~~

Nếu hết 2 giây mà Future chưa hoàn tất, caller nhận `TimeoutException` và có thể chuyển sang fallback hoặc phản hồi timeout. **Task không tự bị hủy chỉ vì `get` timeout**; nó vẫn có thể đang chạy và gây side effect. Muốn hủy, ứng dụng phải ra quyết định riêng (ví dụ `future.cancel(true)` khi phù hợp) và biết rằng cancellation không đảm bảo chặn toàn bộ I/O ở mọi implementation.

### 3.4. Quan hệ happens-before và kết quả chia sẻ

Javadoc `Future` của JDK 17 quy định: những hành động trong tính toán bất đồng bộ **happen-before** những hành động của thread khác **sau một lời gọi `Future.get()` tương ứng**. Vì vậy, sau `get()` thành công, caller có quan hệ đồng bộ để quan sát kết quả được công bố qua việc hoàn tất task. Tuy vậy, nếu task còn tiếp tục hoặc bạn chia sẻ đối tượng mutable cho nhiều thread khác, các vấn đề data race khác vẫn cần giải quyết bằng thiết kế thread-safe, không coi `Future` là khóa bảo vệ mọi biến.

## 4. Những exception của Future.get và cách xử lý

Mỗi exception báo một câu chuyện khác nhau:

| Exception | Xuất hiện khi | Hành động thường cần |
| --- | --- | --- |
| `ExecutionException` (checked) | Task đã chạy và ném exception | Đọc `getCause()`, log/phân loại lỗi nghiệp vụ |
| `InterruptedException` (checked) | Thread đang đợi bị interrupt | Giữ lại tín hiệu `Thread.currentThread().interrupt()` nếu không truyền tiếp |
| `TimeoutException` (checked, chỉ với timed get) | Caller chờ quá hạn, Future chưa hoàn tất | Fallback/return timeout; quyết định riêng có hủy task không |
| `CancellationException` (unchecked) | Future bị hủy | Đường xử lý cancellation, không lấy giá trị như thành công |

### `ExecutionException` chứa lỗi gốc, không thay nó

Giả sử task ném `IllegalStateException("invalid-state")`. Nếu task đã được chấp nhận thông qua `submit(Callable)`, ngoại lệ được lưu ở Future. Caller gọi `get()` và nhận `ExecutionException`. Hãy dùng `ex.getCause()` để biết lỗi gốc:

~~~java
try {
    Integer value = future.get();
    use(value);
} catch (ExecutionException ex) {
    Throwable rootCause = ex.getCause();
    reportFailure(rootCause);
}
~~~

Đây là **fragment**, cần biến/hàm của ứng dụng, imports và xử lý/khai báo `InterruptedException`. Đừng log duy nhất dòng `ExecutionException` rồi bỏ qua stack trace/cause. Nhưng cũng không luôn “ném cause” trực tiếp mà không phân loại: lỗi kết nối, validation và lỗi lập trình có thể cần chính sách khác nhau.

### `InterruptedException` không có nghĩa worker đã thất bại

`get()` ném `InterruptedException` khi **thread caller đang đợi** bị interrupt. Điều đó **không tự chứng minh** task ở worker đã thất bại hoặc dừng. Nếu không có trách nhiệm xử lý interrupt ở tầng hiện tại, bạn có thể truyền tiếp exception hoặc phục hồi interrupt flag rồi thoát đường xử lý:

~~~java
try {
    return future.get();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Waiting thread interrupted", ex);
}
~~~

Đây là fragment bên trong method có kiểu trả về phù hợp và cần xử lý `ExecutionException`; không phải class độc lập. Việc phục hồi interrupt là quan trọng vì nhiều blocking APIs xóa cờ interrupt khi ném `InterruptedException`. Không tự động tiếp tục chờ vô hạn và nuốt tín hiệu đó.

### `TimeoutException` không phải `ExecutionException`

Khi `future.get(1, TimeUnit.SECONDS)` hết hạn, caller có thể nhận `TimeoutException` ngay cả nếu worker hoàn tất **sau đó một phần nghìn giây**. Không đọc `isDone()` ở thời điểm khác rồi suy ngược rằng timeout trước đó là không thể: hai hành động xảy ra ở hai mốc thời gian. Timeout là kết quả của việc **đợi quá lâu**, không phải kết luận task chắc chắn sai.

## 5. Ví dụ Java 17+ hoàn chỉnh: kết quả và lỗi

Lưu chương trình dưới đây thành `FutureBasicsDemo.java`. Nó nộp một task thành công, một task thất bại và một `Runnable`, rồi lần lượt đọc Future. Không phụ thuộc Spring để bạn hiểu hợp đồng nền tảng trước.

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureBasicsDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Integer> ok = pool.submit(() -> 21 * 2);

            Future<Integer> failed = pool.submit(
                    (Callable<Integer>) () -> {
                        throw new IllegalStateException("invalid-state");
                    });

            Future<?> sideEffect = pool.submit((Runnable) () -> { });

            System.out.println("value=" + ok.get());

            try {
                failed.get();
                System.out.println("unexpected-success");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("error="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }

            System.out.println("runnableValue=" + sideEffect.get());
            System.out.println("okDone=" + ok.isDone());
            System.out.println("failedDone=" + failed.isDone());

        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac FutureBasicsDemo.java
java FutureBasicsDemo
~~~

**Đầu ra do chương trình in:**

~~~text
value=42
error=IllegalStateException:invalid-state
runnableValue=null
okDone=true
failedDone=true
~~~

**Giải thích:**

1. `ok` đại diện cho `Callable<Integer>` trả `42`, nên `ok.get()` là `42`.
2. `failed` là task đã **được chấp nhận** nhưng ném `IllegalStateException`; `failed.get()` ném `ExecutionException` với cause chứa `invalid-state`.
3. `sideEffect` là `Runnable` không trả payload; `get()` thành công trả `null`.
4. Cả `ok.isDone()` và `failed.isDone()` đều là `true`. Đây là minh chứng rõ rằng **done không có nghĩa success**.
5. `shutdown()` và `awaitTermination()` dọn pool; không để lại non-daemon worker. Nếu hết thời gian dọn, ví dụ gọi `shutdownNow()` để yêu cầu dừng.

Code chỉ in từ **main** sau khi đợi các Future, không in từ nhiều worker đồng thời nên thứ tự dòng đầu ra ổn định dù thứ tự **thực thi** của ba task không được đảm bảo.

## 6. Ví dụ Java 17+ hoàn chỉnh: timeout không tự hủy task

Ví dụ thứ hai sử dụng hai `CountDownLatch`: `started` xác nhận task đã bắt đầu; `release` giữ task lại cho đến khi main chủ động cho phép hoàn thành. Nhờ vậy có thể xác minh timeout **mà không dựa vào `Thread.sleep()` hoặc tốc độ máy**.

Lưu thành `FutureTimeoutDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class FutureTimeoutDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> pending = pool.submit(() -> {
                started.countDown();
                release.await();
                return "ready";
            });

            started.await(); // task đã bắt đầu

            try {
                pending.get(100, TimeUnit.MILLISECONDS);
                System.out.println("unexpected-value");
            } catch (TimeoutException ex) {
                System.out.println("timed-out=true");
            }

            System.out.println("doneBeforeRelease=" + pending.isDone());

            release.countDown();
            System.out.println("value=" + pending.get(5, TimeUnit.SECONDS));

        } finally {
            release.countDown(); // tránh giữ worker nếu caller lỗi
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac FutureTimeoutDemo.java
java FutureTimeoutDemo
~~~

Đầu ra:

~~~text
timed-out=true
doneBeforeRelease=false
value=ready
~~~

Lần `get(100, MILLISECONDS)` đầu tiên timeout vì task vẫn đang chờ `release`. Khi đó `isDone()` là `false`, chứng tỏ **timeout của caller không kết thúc task**. Sau khi `release.countDown()`, worker tiếp tục, và `get(5, SECONDS)` trả `"ready"`.

Trong hệ thống thực, nếu task đang gọi HTTP hoặc JDBC thay vì `CountDownLatch.await()`, timeout của `Future.get` vẫn không tự động làm HTTP request hay DB query dừng. Hãy đặt timeout riêng cho downstream I/O, giới hạn concurrency, và cân nhắc hủy tác vụ theo đúng hợp đồng nghiệp vụ.

## 7. Cancellation: Future có thể hủy, nhưng không phải công tắc dừng tuyệt đối

`future.cancel(boolean mayInterruptIfRunning)` yêu cầu hủy tác vụ; kết quả phụ thuộc trạng thái và implementation:

- Nếu Future đã hoàn tất, `cancel(...)` thường trả `false` và không thay đổi kết quả.
- Nếu tác vụ chưa bắt đầu và hủy thành công, tác vụ không nên chạy.
- Nếu tác vụ đang chạy, `cancel(true)` cho phép implementation thử **interrupt worker thread** khi biết worker. Task phải hợp tác với interrupt và khả năng hủy của I/O bên dưới.
- `cancel(false)` không yêu cầu interrupt worker đang chạy; điều đó không chứng minh mọi tác dụng phụ sẽ ngừng xảy ra. Đừng hiểu `cancel` là một giao dịch rollback.
- Sau khi Future hủy thành công, `isCancelled()` và `isDone()` có thể đều là `true`; `get()` ném `CancellationException`.

Để quan sát rõ, dùng `FutureTask` của JDK thông qua executor. Lưu thành `FutureCancelDemo.java`:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class FutureCancelDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> task = pool.submit(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return "interrupted";
                }
                return "finished";
            });

            started.await(); // task đang chạy, chưa có kết quả
            boolean requested = task.cancel(true);

            System.out.println("cancelRequested=" + requested);
            System.out.println("isCancelled=" + task.isCancelled());
            System.out.println("isDone=" + task.isDone());

            try {
                task.get();
                System.out.println("unexpected-value");
            } catch (CancellationException ex) {
                System.out.println("get=CancellationException");
            }

        } finally {
            release.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac FutureCancelDemo.java
java FutureCancelDemo
~~~

Đầu ra kỳ vọng ổn định với `ExecutorService.newSingleThreadExecutor()` và task được giữ bởi latch:

~~~text
cancelRequested=true
isCancelled=true
isDone=true
get=CancellationException
~~~

Chú ý: dòng `cancelRequested=true` thể hiện **yêu cầu hủy được Future chấp nhận**, không bảo đảm mọi side effect đã hoặc sẽ xảy ra trong task đều được hoàn tác. Trong ví dụ, task chờ ở điểm hỗ trợ interrupt; một tác vụ thực thi mã không kiểm tra interrupt hoặc một thư viện I/O không đáp ứng interrupt có thể không dừng ngay. Khi task không được phép làm dở giao dịch nghiệp vụ, cần thiết kế cancellation và transaction rõ ràng.

### Sự khác nhau của CompletableFuture.cancel

`CompletableFuture` **implements Future**, nhưng JDK quy định `CompletableFuture.cancel(boolean)` xem việc hủy như **exceptional completion**; cờ `mayInterruptIfRunning` không có tác dụng kiểm soát interrupt trực tiếp trên tác vụ như ở một `FutureTask` thông thường. Đừng chuyển từ `FutureTask` sang `CompletableFuture` rồi mặc định cơ chế hủy thực thi bên dưới giống hệt.

## 8. Tích hợp Spring: AsyncTaskExecutor trả Future

Trong Spring, `org.springframework.core.task.TaskExecutor` cơ bản có `execute(Runnable)` và trả `void`. Interface `AsyncTaskExecutor` mở rộng nó bằng các overload `submit`:

~~~java
// Chữ ký API, không phải file chạy độc lập:
Future<?> submit(Runnable task);
<T> Future<T> submit(Callable<T> task);
~~~

Spring Framework 6.1.3 `AsyncTaskExecutor` hỗ trợ hai phương thức trên. `ThreadPoolTaskExecutor` là implementation phổ biến để quản lý nhóm worker threads và queue. Nếu khai báo biến kiểu `TaskExecutor`, bạn **không thể gọi `submit` qua kiểu tĩnh đó**; hãy inject `AsyncTaskExecutor` hoặc một implementation phù hợp.

### 8.1. Ví dụ Spring Framework 6.1.3 độc lập (Maven)

Ví dụ sau chạy bằng `main`, **không cần Spring Boot server hay `@EnableAsync`**, bởi vì gọi `submit` trực tiếp trên executor đã khởi tạo. Cấu trúc:

~~~text
spring-future-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringFutureDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-future-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.SpringFutureDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/SpringFutureDemo.java`:

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringFutureDemo {

    public static void main(String[] args) throws Exception {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("spring-future-");
        pool.initialize();

        try {
            AsyncTaskExecutor executor = pool;

            Future<String> ok = executor.submit(() -> "report-ready");
            Future<Integer> bad = executor.submit(
                    (Callable<Integer>) () -> {
                        throw new IllegalArgumentException("invalid-id");
                    });

            System.out.println("springValue=" + ok.get(5, TimeUnit.SECONDS));

            try {
                bad.get(5, TimeUnit.SECONDS);
                System.out.println("unexpected-value");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                System.out.println("springCause="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }

        } finally {
            pool.shutdown();
        }
    }
}
~~~

Trong thư mục `spring-future-demo` chạy:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra do chương trình Java in (không tính log riêng từ Maven):

~~~text
springValue=report-ready
springCause=IllegalArgumentException:invalid-id
~~~

Ở đây Spring `ThreadPoolTaskExecutor` nhận cả task thành công và task thất bại. Cả hai Future đều là handle của công việc được nộp. `get` chờ hoàn tất và cung cấp giá trị hoặc `ExecutionException` bao quanh nguyên nhân của lỗi. `pool.shutdown()` dọn executor được tạo thủ công; trong ứng dụng Spring thật, hãy đăng ký pool làm bean singleton để container quản lý lifecycle.

### 8.2. Rejection xảy ra trước khi có Future

`AsyncTaskExecutor.submit(...)` có thể ném `TaskRejectedException` **ngay tại điểm gửi** nếu pool bị shutdown, queue đầy và không thể mở rộng worker. Khi đó lệnh `Future<T> future = executor.submit(...)` **không hoàn thành việc gán biến**. Không gọi `future.get()` để tìm exception nếu Future chưa từng được trả về.

~~~java
// Fragment trong service có biến executor kiểu AsyncTaskExecutor.
try {
    Future<String> future = executor.submit(() -> "ok");
    return future;
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Ghi metric/log cho quá tải hoặc lifecycle shutdown.
    throw ex;
}
~~~

Đoạn này không độc lập; giả sử method bao quanh có kiểu trả `Future<String>`. `TaskRejectedException` của Spring kế thừa `RejectedExecutionException` của JDK. Nó khác `ExecutionException` của task **đã được chấp nhận**.

## 9. Spring @Async: trả Future từ phương thức nghiệp vụ

Spring `@Async` cho phép một method được gọi bất đồng bộ thông qua interceptor/proxy khi `@EnableAsync` đã bật và bean/caller đúng điều kiện. Method có thể khai báo kiểu trả về `Future<T>` hoặc `CompletableFuture<T>` thay vì `void`. Caller sẽ nhận một Future đại diện cho lời gọi phương thức bất đồng bộ.

Ví dụ cấu hình trong một ứng dụng Spring đã có component scanning (các class là **fragment kiến trúc**, không phải project `main` độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class ReportAsyncConfig {
    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("report-");
        return executor;
    }
}
~~~

Method nghiệp vụ nằm trong một bean khác:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        String result = "report:" + id;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Ví dụ caller **được Spring quản lý** và đã inject `ReportService`:

~~~java
CompletableFuture<String> result = reportService.generate("A42");
String value = result.get(5, TimeUnit.SECONDS); // "report:A42"
~~~

Đoạn caller là fragment; cần khai báo/tiêm `reportService`, import `TimeUnit`, khai báo hoặc xử lý checked exceptions. Spring proxy nộp lời gọi sang executor và trả Future cho caller. Khi worker chạy target method, method có thể trả `CompletableFuture.completedFuture(...)` như phương tiện cung cấp giá trị; **Future mà caller nhận từ proxy** mới đại diện cho công việc bất đồng bộ.

**Điều kiện thường bị quên:**

- Gắn `@EnableAsync` trong configuration và đảm bảo service là bean do Spring quản lý.
- Gọi từ bean khác **qua Spring proxy**. Self-invocation (`this.generate(...)` trong chính service) thường **bỏ qua proxy** ở chế độ mặc định `AdviceMode.PROXY`.
- `@Async("reportExecutor")` chọn executor đúng tên; nếu dùng sai tên hoặc caller tạo service bằng `new`, hành vi không như kỳ vọng.
- Đừng gắn `@Async` lên method khai báo **trong lớp `@Configuration`**: Javadoc Spring ghi rõ không hỗ trợ trường hợp đó. Để configuration khai báo executor và business method nằm trong service.
- Với `@Async void`, caller **không có Future** để đọc exception; Spring hỗ trợ `AsyncUncaughtExceptionHandler` hoặc logging theo cấu hình. Nếu cần kiểm soát lỗi, ưu tiên API trả Future/CompletableFuture khi phù hợp.

## 10. So sánh Future và CompletableFuture

`CompletableFuture<T>` **là một implementation của `Future<T>`** nhưng còn implements `CompletionStage<T>`. Nó có các API ghép xử lý bất đồng bộ, ví dụ `thenApply`, `thenCombine`, `thenCompose` và `exceptionally`.

| Nhu cầu | `Future<T>` thuần | `CompletableFuture<T>` |
| --- | --- | --- |
| Chờ task và lấy kết quả | `get()` | `get()` hoặc `join()` |
| Kiểm tra done / cancel | Có | Có |
| Chờ có timeout | `get(timeout, unit)` | `get(timeout, unit)`; ngoài ra có API timeout riêng |
| Ghép nhiều task mà không đợi từng Future bằng cách blocking | Không có API chaining trong interface | Có `thenCombine`, `thenCompose`, `allOf` |
| Khôi phục giá trị khi task lỗi | Chủ động `try/catch` quanh `get` | Có `exceptionally`/`handle` |
| Cách exception xuất hiện ở `join()` | Không có `join()` | `CompletionException` (unchecked) khi lỗi |
| Hành vi `cancel(true)` | Phụ thuộc implementation `Future` | Không dùng cờ `mayInterruptIfRunning` để ngắt tác vụ theo hợp đồng `CompletableFuture` |

Nếu bài toán chỉ cần “nộp công việc, thỉnh thoảng chờ kết quả”, `Future` rất phù hợp. Nếu cần **ghép nhiều bước không chặn**, `CompletableFuture` thường phù hợp hơn.

Trong Spring Framework 6.0+, `AsyncTaskExecutor` còn có:

~~~java
// Chữ ký minh họa (Spring 6.0+):
CompletableFuture<Void> submitCompletable(Runnable task);
<T> CompletableFuture<T> submitCompletable(Callable<T> task);
~~~

Điểm quan trọng: các overload `submitCompletable` **chỉ có từ Spring Framework 6.0**. Với Spring 5.x, có thể dùng `CompletableFuture.supplyAsync(..., taskExecutor)` hoặc `runAsync(..., taskExecutor)`, nhưng cần hiểu `Supplier` không khai báo checked exception như `Callable`. Không lẫn API Java 17, Spring version và kiểu interface khi nâng cấp dự án.

### Ví dụ ghép hai Future khác CompletableFuture thế nào?

Với hai `Future<Integer>` thuần, thường bạn phải `get()` để lấy từng kết quả:

~~~java
Future<Integer> a = executor.submit(() -> 10);
Future<Integer> b = executor.submit(() -> 20);
int sum = a.get() + b.get(); // 30
~~~

Đây là fragment với `executor` kiểu `ExecutorService` và method bao quanh xử lý checked exceptions. Hai task được nộp **trước khi chờ**, nên có thể chạy song song, nhưng `get()` vẫn chặn caller.

Với `CompletableFuture`, có thể mô tả bước ghép để chạy khi cả hai hoàn tất:

~~~java
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 10, executor);
CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 20, executor);

CompletableFuture<Integer> sum =
        a.thenCombine(b, Integer::sum);
~~~

Đây cũng là fragment, yêu cầu `executor` là `Executor` và các import `CompletableFuture`. Nếu cần giữ concurrency trong Spring, truyền **executor tường minh** thay vì vô tình dùng `ForkJoinPool.commonPool()`. `sum` có thể được trả lên tầng khác mà không cần chặn tại vị trí tạo nó.

## 11. Tránh tự gây nghẽn thread pool khi đợi Future

Một lỗi phổ biến là **task A đang chạy trên pool có một worker**, rồi A gửi task B vào cùng pool và gọi `B.get()`. A giữ worker duy nhất để đợi B; B không có worker để chạy. Đây là dạng **thread-starvation deadlock**.

~~~text
Pool có đúng 1 worker:
  worker chạy task A
      |
      +-- submit(task B) vào cùng pool
      |
      +-- B.get() --> A bị chặn
                      |
                      +-- B đang ở queue,
                          nhưng worker vẫn bị A giữ
~~~

Không giải quyết bằng việc đổi `get()` thành `get(timeout)` rồi xem như hết vấn đề: timeout chỉ giúp A cuối cùng ngừng đợi, nhưng kiến trúc vẫn thiếu worker nếu cùng cách làm. Cân nhắc tách các bước phụ thuộc thành composition bất đồng bộ, sử dụng executor phù hợp, không chặn worker vào task con nằm trong cùng pool nhỏ hoặc phân rã luồng xử lý.

Ngoài ra, `isDone()` liên tục trong một vòng `while(!future.isDone())` mà không ngủ/đợi là **busy-wait**, gây lãng phí CPU. Dùng `get` ở ranh giới cần dữ liệu, callback của `CompletableFuture` hoặc các API đồng bộ chuyên dụng theo mục tiêu.

## 12. Checklist áp dụng Future trong ứng dụng thật

1. **Chọn API có kết quả:** `ExecutorService.submit(Callable)` hoặc `AsyncTaskExecutor.submit(Callable)` trả `Future<T>`; `execute` không cho handle.
2. **Nộp các task độc lập trước khi chờ:** tránh serial hóa do gọi `get()` ngay sau từng `submit` nếu không cần.
3. **Đặt giới hạn chờ ở ranh giới cần SLA:** dùng `get(timeout, unit)` thay vì đợi vô thời hạn cho remote I/O không đáng tin; có timeout riêng tại HTTP/JDBC.
4. **Tách đường lỗi:** `TaskRejectedException` tại **submit** khác `ExecutionException` tại **get**. Đừng để một catch khái quát che hai nguyên nhân.
5. **Kiểm tra cause:** log context có ích và `getCause()` thay vì chỉ message của `ExecutionException`.
6. **Xử lý interrupt:** nếu catch `InterruptedException` mà không truyền tiếp, phục hồi interrupt flag.
7. **Không coi done là thành công:** `isDone` có thể đúng khi task failed hoặc cancelled.
8. **Cân nhắc cancellation hợp tác:** `cancel(true)` chỉ thử interrupt khi implementation hỗ trợ; side effects, transaction và I/O không tự rollback.
9. **Không bỏ Future của task quan trọng:** nếu caller không bao giờ gọi `get` hay đăng ký cơ chế quan sát, exception trong task có thể không được xử lý đúng trách nhiệm.
10. **Đo pool và queue:** backlog, số worker, task duration, timeout và rejection rate giúp phát hiện quá tải; đừng tăng queue vô hạn chỉ để che lỗi.
11. **Tránh chờ trong cùng pool nhỏ:** giữ worker để đợi Future phụ thuộc có thể làm pool không tiến triển.
12. **Trong Spring, đảm bảo async thực sự chạy:** service do context quản lý, lời gọi qua proxy, `@EnableAsync` và executor name đúng.

### Câu hỏi tự kiểm tra

**Câu 1.** `future.isDone()` bằng `true` có chứng minh task thành công không?  
**Đáp án:** Không. `isDone` đúng khi hoàn tất bình thường, ném lỗi hoặc bị hủy.

**Câu 2.** Khi một `Callable` ném `IllegalArgumentException` trong worker sau khi task được nhận, `future.get()` báo gì?  
**Đáp án:** `ExecutionException`; lỗi gốc nằm trong `getCause()`.

**Câu 3.** `future.get(100, MILLISECONDS)` ném `TimeoutException`. Task có bị dừng ngay không?  
**Đáp án:** Không. Chỉ việc **chờ của caller** hết thời gian; task vẫn có thể chạy tiếp.

**Câu 4.** Nếu caller bị interrupt trong lúc đợi, điều đó cho biết worker đã thất bại chưa?  
**Đáp án:** Chưa. `InterruptedException` thuộc thread đang chờ; cần xử lý interrupt, không tự suy luận tình trạng worker.

**Câu 5.** Spring `TaskExecutor` chỉ khai báo `execute`. Làm thế nào để lấy `Future<String>` từ một tác vụ trả String?  
**Đáp án:** Dùng `AsyncTaskExecutor` hoặc implementation phù hợp và gọi `submit(Callable<String>)`. Với `@Async` có thể khai báo return type `Future<String>` hoặc `CompletableFuture<String>` trên method của bean được Spring xử lý.

**Câu 6.** Tại sao `future.get()` không bắt được việc executor từ chối task lúc submit?  
**Đáp án:** Nếu bị từ chối, `submit` đã ném exception **trước khi trả về Future**; phải catch tại điểm nộp.

**Câu 7.** Vì sao hai `Future` được nộp vào pool một worker rồi task đầu chờ `get` của task thứ hai có thể deadlock?  
**Đáp án:** Task đầu giữ worker duy nhất; task thứ hai nằm trong queue mà không có worker để thực thi, nên lời đợi không được đáp ứng.

**Câu 8.** `CompletableFuture` khác `Future` thuần ở điểm nào hữu ích cho quy trình nhiều bước?  
**Đáp án:** Có `CompletionStage` với các phương thức composition/callback/khôi phục lỗi, tránh phải chặn caller tại từng bước.

## 13. Tài liệu tham khảo chính thức

- [Java SE 17 — Future Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): định nghĩa `get`, timeout, exception, cancellation, `isDone` và quan hệ happens-before.
- [Java SE 17 — ExecutorService Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown` và vòng đời executor.
- [Java SE 17 — FutureTask Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): một implementation cho phép dùng Future với Runnable.
- [Java SE 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `CompletionStage`, `join`, chaining, lỗi và hủy.
- [Spring Framework 6.1.3 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): `submit` trả `Future` và `submitCompletable` (từ Spring 6.0).
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): triển khai pool, queue, submit và TaskRejectedException.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@Async`, Future return types và xử lý exception.
