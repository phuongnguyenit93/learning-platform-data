# orTimeout() và completeOnTimeout() không mặc nhiên dừng thao tác đang chạy

## 1. Vì sao Future hết hạn nhưng tác vụ vẫn chạy?

Khi xử lý bất đồng bộ trong Java hoặc Spring, một `CompletableFuture<T>` thường biểu diễn **kết quả có thể nhận trong tương lai**, nhưng nó **không nhất thiết có quyền điều khiển vòng đời của công việc đã được gửi vào executor**. Đây là sự khác biệt quan trọng khi dùng:

- `orTimeout(long timeout, TimeUnit unit)` — nếu future chưa hoàn tất, cho **chính future đó** hoàn tất **exceptionally** bằng `TimeoutException` sau thời hạn.
- `completeOnTimeout(T value, long timeout, TimeUnit unit)` — nếu future chưa hoàn tất, cho **chính future đó** hoàn tất **bình thường** với giá trị dự phòng sau thời hạn.

**Cả hai đều thay đổi cách caller quan sát kết quả; không mặc nhiên ngắt thread đang chạy, hủy lệnh HTTP, dừng query database hay rollback tác dụng phụ của tác vụ.** Worker có thể tiếp tục làm việc sau khi future đã timeout hoặc đã trả fallback.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **trạng thái của `CompletableFuture`** với **trạng thái thật của computation/I/O bên dưới**.
2. Giải thích `orTimeout`, `completeOnTimeout`, `get(timeout)`, `cancel(true)` và giá trị trả về của từng API.
3. Xác định “first completion wins”: kết quả muộn thường không thay thế một future đã hoàn tất vì timeout/fallback.
4. Viết chương trình Java 17+ có kết quả xác định, sử dụng `CountDownLatch` để chứng minh worker còn bận sau khi future đã hoàn tất.
5. Áp dụng với `ThreadPoolTaskExecutor` của Spring, lựa chọn executor riêng, quản lý tài nguyên và timeout của I/O thật.
6. Tránh các lỗi production: retry chồng tác vụ, dùng fallback che lỗi, giữ connection quá lâu, gây đầy pool, hoặc tưởng `CompletableFuture.cancel(true)` đã interrupt worker.
7. Kiểm thử cả **phản hồi đúng hạn** và **giải phóng tài nguyên thật**, thay vì chỉ assert trạng thái future.

**Phiên bản:** `orTimeout` và `completeOnTimeout` có từ **Java 9**, chạy trong ví dụ **Java 17+**. Ví dụ Spring dùng **Spring Framework 6.1.3**; các API timeout là của JDK, không phải tính năng riêng của Spring.

## 2. Bốn đại lượng thời gian không giống nhau

Một request bất đồng bộ thường có ít nhất bốn mốc khác nhau:

| Loại thời gian | Đo điều gì? | API/cơ chế thường dùng |
| --- | --- | --- |
| **Thời gian chờ của caller** | Caller đợi kết quả tối đa bao lâu | `Future.get(timeout, unit)` |
| **Thời hạn hoàn tất Future** | Khi nào caller nhìn thấy timeout hoặc fallback | `orTimeout` / `completeOnTimeout` |
| **Thời gian thao tác thật** | HTTP/SQL/file I/O thực thi bao lâu | Timeout của HTTP client, JDBC, SDK, socket, query, driver |
| **Vòng đời worker/task** | Task đã chạy xong, bị interrupt, bị cancel hay vẫn đang chiếm worker | Executor, `FutureTask`, interrupt hợp tác, resource-specific cancellation |

Không thể chỉ nhìn trạng thái của Future để suy ra mọi tầng bên dưới đều đã dừng.

Ví dụ một `Supplier` gọi API đồng bộ trong 8 giây, nhưng `completeOnTimeout("cached", 1, SECONDS)` trả fallback sau 1 giây: caller thấy “cached” nhưng HTTP request đồng bộ **có thể vẫn chạy 7 giây nữa**. Nếu nhiều request như vậy xảy ra, worker và kết nối vẫn có thể bị chiếm, bất kể API của bạn trả lời nhanh.

### Timeline minh họa

~~~text
t = 0 ms       Caller submit task --> worker bắt đầu HTTP call
                 |
t = 1000 ms    orTimeout: Future hoàn tất với TimeoutException
                 |         hoặc
                 +------ completeOnTimeout: Future hoàn tất với fallback
                 |
                 |        Worker vẫn có thể đang đợi HTTP/DB
                 |        Không có interrupt tự động từ hai API trên
                 |
t = 8000 ms    HTTP call kết thúc, Supplier trả kết quả "real"
                 |
                 +------ Future đã timeout/fallback trước đó:
                         kết quả muộn không ghi đè kết quả thắng trước
~~~

Timeline này minh họa tình huống tác vụ thực tế chạy lâu hơn deadline; không phải quy định thread luôn chạy đủ 8 giây. Nếu có timeout đúng tầng I/O, worker có thể kết thúc sớm hơn.

## 3. API Java 17: các điểm chính xác nhất

Hai phương thức instance của `java.util.concurrent.CompletableFuture<T>`:

~~~java
// Chữ ký API rút gọn, không phải Java class độc lập.
CompletableFuture<T> orTimeout(long timeout, TimeUnit unit);

CompletableFuture<T> completeOnTimeout(
        T value, long timeout, TimeUnit unit);
~~~

Javadoc của **cả hai** đều ghi **returns: this CompletableFuture**. Chúng **không tạo một Future mới độc lập** chỉ vì phương thức có kiểu trả về `CompletableFuture<T>`. Chúng lập lịch một hành động cố hoàn tất **đối tượng gốc** nếu đối tượng đó chưa hoàn tất vào lúc timeout.

### 3.1. `orTimeout()`: hoàn tất bằng lỗi timeout

~~~java
// Fragment minh họa, giả sử future là CompletableFuture<String>.
CompletableFuture<String> timed =
        future.orTimeout(2, TimeUnit.SECONDS);
boolean sameObject = timed == future; // true
~~~

Nếu task đã hoàn tất trước 2 giây, kết quả bình thường/lỗi sẵn có được giữ nguyên. Nếu timeout thắng, future hoàn tất **exceptionally** với `TimeoutException`.

- `future.isDone()` trở thành `true`.
- `future.isCompletedExceptionally()` trở thành `true`.
- `future.isCancelled()` **không tự trở thành true**: timeout không đồng nghĩa cancellation.
- `future.join()` thường ném `CompletionException` với `getCause()` là `TimeoutException`.
- `future.get()` theo hợp đồng Future ném `ExecutionException` với cause là `TimeoutException`.
- Worker/I/O thực tế không tự bị ngắt bởi lệnh timeout này.

Không viết code kiểu `catch (TimeoutException ex)` trực tiếp quanh `join()`: `join()` không khai báo checked `TimeoutException`; cần bắt `CompletionException` và xem cause. `get(timeout, unit)` và `get()` có kiểu exception khác, hãy phân biệt chúng.

### 3.2. `completeOnTimeout()`: hoàn tất bằng fallback

~~~java
// Fragment minh họa.
CompletableFuture<String> recovered =
        future.completeOnTimeout("cached", 2, TimeUnit.SECONDS);
boolean sameObject = recovered == future; // true
~~~

Nếu future chưa hoàn tất sau 2 giây, nó hoàn tất **bình thường** với `"cached"`. Khi đó:

- `future.isDone()` là `true`.
- `future.isCompletedExceptionally()` là `false`, vì fallback được xem là **giá trị thành công của Future**.
- `future.join()` trả `"cached"`.
- Supplier vẫn có thể tiếp tục xử lý, truy cập database hoặc gọi API khác.
- Kết quả thực tới sau sẽ không làm `join()` tự chuyển từ `"cached"` sang giá trị thực.

Vì fallback được coi là thành công ở mức future, cần **đánh dấu rõ nguồn giá trị trong nghiệp vụ** (ví dụ `Result(value, fromFallback)`, metric hay log); nếu không, tầng gọi có thể không phân biệt dữ liệu mới với dữ liệu cache.

### 3.3. `get(timeout)` chỉ giới hạn thời gian caller đợi

~~~java
// Fragment: giới hạn lần đợi hiện tại.
String result = future.get(2, TimeUnit.SECONDS);
~~~

Nếu quá hạn, `get(timeout, unit)` ném **`TimeoutException` vào thread đang chờ**, nhưng **không tự hoàn tất hoặc hủy Future**. Nếu task sau đó trả kết quả thành công, bạn vẫn có thể gọi `future.get()`/`join()` lần nữa để lấy kết quả thực.

Đây là khác biệt quyết định:

| Đặc điểm | `get(2, SECONDS)` | `orTimeout(2, SECONDS)` | `completeOnTimeout("cached", 2, SECONDS)` |
| --- | --- | --- | --- |
| Mục đích | Giới hạn một lần caller **chờ** | Đặt hạn hoàn tất Future bằng lỗi | Đặt hạn hoàn tất Future bằng fallback |
| Trả về | Giá trị `T` hoặc ném exception | **Cùng đối tượng** `CompletableFuture<T>` | **Cùng đối tượng** `CompletableFuture<T>` |
| Khi quá hạn | Caller nhận `TimeoutException` | Future hoàn tất exceptionally với `TimeoutException` | Future hoàn tất bình thường với `"cached"` |
| `isDone()` của Future sau timeout | Có thể vẫn `false` | `true` | `true` |
| Kết quả thực đến muộn | **Vẫn có thể lấy được** | Thường không thay trạng thái Future đã timeout | Thường không thay giá trị fallback đã thắng |
| Ngắt worker tự động | **Không** | **Không** | **Không** |
| Hủy HTTP/SQL tự động | **Không** | **Không** | **Không** |

**Lưu ý race:** Nếu kết quả thật hoàn tất ngay gần lúc timeout, chính thao tác hoàn tất nào **thắng trước** quyết định trạng thái. Không viết test dựa vào việc hai sự kiện sát nhau nhất định diễn ra theo một thứ tự duy nhất.

## 4. Một Future đã timeout khác một task đã kết thúc

`CompletableFuture` là một cơ chế **hoàn tất giá trị** và **ghép stage**. `CompletableFuture.supplyAsync(supplier, executor)` đưa một tác vụ vào `Executor`, nhưng `CompletableFuture` không nhất thiết có handle để ngắt, dừng hoặc rollback việc `Supplier` đang làm.

Trong `CompletableFuture`, những lời gọi cố hoàn tất cùng future từ nhiều thread có cơ chế cạnh tranh: **chỉ một bên thắng** ở completion thông thường (`complete`, `completeExceptionally`, `cancel`). Khi deadline đã hoàn tất future trước, worker chạy xong muộn thường chỉ cố đưa kết quả vào một future đã hoàn tất; giá trị muộn không ghi đè completion thắng trước.

**Tác vụ vẫn có thể gây side effect sau thời điểm caller nhận timeout.** Ví dụ:

- Một giao dịch/chuyển khoản vẫn được gửi tới remote service.
- Lệnh INSERT/UPDATE có thể vẫn chạy, dù HTTP client đã trả fallback.
- Bộ nhớ, socket, database connection và thread của executor vẫn bị giữ.
- Task xong muộn có thể kích hoạt log/metric hoặc một side effect khác trong chính Supplier.
- Nếu caller retry ngay vì timeout, hai thao tác có thể **chạy chồng nhau**.

Không lấy `future.isDone() == true` làm tín hiệu rằng thread/socket/transaction đều đã hoàn thành và tài nguyên được giải phóng.

## 5. Ví dụ Java 17+ chạy độc lập: ba kiểu timeout và một worker còn bận

Đây là thí nghiệm cốt lõi của bài. Ta dùng `CountDownLatch` để **giữ Supplier ở trạng thái đang chạy** cho đến khi main chủ động mở khóa. Nhờ thế có thể chứng minh `orTimeout` và `completeOnTimeout` hoàn tất Future **trong khi Supplier chưa hoàn tất**.

Chương trình có ba nhánh:

1. `orTimeout`: Future báo `TimeoutException` nhưng worker vẫn đợi.
2. `completeOnTimeout`: Future trả `fallback` nhưng worker vẫn đợi.
3. `get(timeout)`: caller nhận `TimeoutException` nhưng Future vẫn pending, sau đó lấy được kết quả thật.

Lưu thành `TimeoutDoesNotStopDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class TimeoutDoesNotStopDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            showOrTimeout(pool);
            showCompleteOnTimeout(pool);
            showTimedGet(pool);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }

    private static CompletableFuture<String> blockedWork(
            ExecutorService pool,
            CountDownLatch started,
            CountDownLatch release,
            CountDownLatch workerReachedFinally) {

        return CompletableFuture.supplyAsync(() -> {
            started.countDown();
            try {
                release.await();
                return "real";
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return "interrupted";
            } finally {
                workerReachedFinally.countDown();
            }
        }, pool);
    }

    private static void showOrTimeout(ExecutorService pool)
            throws Exception {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch reachedFinally = new CountDownLatch(1);
        CompletableFuture<String> future = blockedWork(
                pool, started, release, reachedFinally);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            boolean same = future.orTimeout(
                    100, TimeUnit.MILLISECONDS) == future;
            System.out.println("orSameFuture=" + same);

            try {
                future.join();
                System.out.println("unexpected-or-success");
            } catch (CompletionException ex) {
                System.out.println("orCause="
                        + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("orWorkerFinishedAtTimeout="
                    + (reachedFinally.getCount() == 0));
        } finally {
            release.countDown(); // giải phóng ngay cả khi nhánh đợi lỗi
        }

        if (!reachedFinally.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not exit");
        }
        System.out.println("orStillExceptional="
                + future.isCompletedExceptionally());
    }

    private static void showCompleteOnTimeout(ExecutorService pool)
            throws Exception {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch reachedFinally = new CountDownLatch(1);
        CompletableFuture<String> future = blockedWork(
                pool, started, release, reachedFinally);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            boolean same = future.completeOnTimeout(
                    "fallback", 100, TimeUnit.MILLISECONDS) == future;
            System.out.println("fallbackSameFuture=" + same);
            System.out.println("fallbackValue=" + future.join());
            System.out.println("fallbackWorkerFinishedAtTimeout="
                    + (reachedFinally.getCount() == 0));
        } finally {
            release.countDown();
        }

        if (!reachedFinally.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not exit");
        }
        System.out.println("fallbackAfterRealWork=" + future.join());
    }

    private static void showTimedGet(ExecutorService pool)
            throws Exception {

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch reachedFinally = new CountDownLatch(1);
        CompletableFuture<String> future = blockedWork(
                pool, started, release, reachedFinally);

        try {
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not start");
            }

            try {
                future.get(100, TimeUnit.MILLISECONDS);
                System.out.println("unexpected-get-success");
            } catch (TimeoutException ex) {
                System.out.println("getTimedOut=true");
            }

            System.out.println("getFutureDoneAtTimeout="
                    + future.isDone());
        } finally {
            release.countDown();
        }

        if (!reachedFinally.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not exit");
        }
        System.out.println("getValueAfterRealWork=" + future.join());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac TimeoutDoesNotStopDemo.java
java TimeoutDoesNotStopDemo
~~~

**Đầu ra kỳ vọng khi chạy bình thường:**

~~~text
orSameFuture=true
orCause=TimeoutException
orWorkerFinishedAtTimeout=false
orStillExceptional=true
fallbackSameFuture=true
fallbackValue=fallback
fallbackWorkerFinishedAtTimeout=false
fallbackAfterRealWork=fallback
getTimedOut=true
getFutureDoneAtTimeout=false
getValueAfterRealWork=real
~~~

### Giải thích tính xác định của ví dụ

- `started.await(...)` chờ đúng tín hiệu worker **đã bắt đầu**; task sau đó đợi `release`.
- Khi main gọi `join()` sau `orTimeout` hoặc `completeOnTimeout`, worker vẫn bị `release.await()` giữ lại. Vì vậy in `...WorkerFinishedAtTimeout=false`, không cần đoán worker có ngủ đủ lâu hay không.
- `orTimeout` hoàn tất future bằng lỗi, nên `join()` báo `CompletionException` với nguyên nhân `TimeoutException`. Worker đến `finally` sau khi được mở latch **không thể biến future đó thành thành công**.
- `completeOnTimeout` đưa `"fallback"` vào chính future; khi worker cuối cùng trả `"real"`, `future.join()` vẫn là `"fallback"`.
- `get(100, MILLISECONDS)` chỉ giới hạn lần đợi; sau khi giải phóng worker, Future chưa bị ép timeout nên trả được `"real"`.
- Các dòng output chỉ được in bởi **main**, không in đồng thời từ worker, nên không phụ thuộc thứ tự log giữa threads.
- Mỗi phương thức có `finally` mở latch; `main` gọi `shutdown/awaitTermination` để dọn worker. Trong một môi trường không khởi chạy được worker trong vòng 5 giây, chương trình chủ động ném lỗi khởi động thay vì giả định kết quả chuẩn.

**Lưu ý kỹ thuật:** Latch `workerReachedFinally` xác nhận Supplier **đã đi đến `finally`**; ngay sau đó thread còn phải trả về khỏi lambda và executor cập nhật completion. Phép kiểm tra ở đây chỉ cần chứng minh lúc deadline xảy ra Supplier **chưa đến `finally`**, không dựa vào việc một latch là cơ chế công bố trạng thái công việc theo hợp đồng Java `Future`.

## 6. Vì sao không nên sử dụng Thread.sleep để “chứng minh” timeout?

Một ví dụ đơn giản thường làm `Thread.sleep(500)` rồi `orTimeout(100, MILLISECONDS)`. Nó có thể minh họa ý tưởng, nhưng nếu kiểm thử chỉ nhìn thời điểm in hoặc thread scheduling, máy CI quá tải có thể làm thứ tự khó dự đoán. Dùng `CountDownLatch` trong bài trên tốt hơn vì worker không thể vượt qua điểm chờ trước khi main mở latch.

Trong production, timeout đo bằng **thời gian thực** và hoàn toàn có race giữa tác vụ và deadline. Test nên tập trung vào **hành vi cần bảo đảm**: Future trả fallback hoặc lỗi timeout trong điều kiện tác vụ chưa được giải phóng, không tự hủy I/O, đồng thời pool được dọn sạch sau test. Không viết assertion rằng timer luôn kích hoạt chính xác ở mili giây thứ 100.

## 7. Spring Framework: TaskExecutor không tự đổi cơ chế timeout của CompletableFuture

`ThreadPoolTaskExecutor` trong Spring quản lý `java.util.concurrent.ThreadPoolExecutor`, cung cấp các tham số `corePoolSize`, `maxPoolSize` và `queueCapacity`. Bạn có thể dùng bean này như `Executor` được truyền vào `CompletableFuture.supplyAsync(supplier, executor)`.

Điểm cần nhớ:

- `orTimeout` và `completeOnTimeout` vẫn là **API của `CompletableFuture` trong Java**, không mang chức năng dừng task của `ThreadPoolTaskExecutor`.
- Chúng có thể hoàn tất future **trong khi worker Spring còn bận chờ I/O**.
- Tăng tốc phản hồi cho caller không tự tăng khả năng phục vụ: pool và downstream vẫn có thể đầy nếu work tiếp tục quá lâu.
- `AsyncTaskExecutor.submitCompletable(...)` có từ **Spring Framework 6.0+**, cũng trả `CompletableFuture`. Khi áp timeout lên future đó, không được mặc định rằng worker chạy `Runnable/Callable` đã bị interrupt.
- `TaskExecutor` bản cơ sở chỉ cần `execute(Runnable)`; `CompletableFuture.supplyAsync(..., taskExecutor)` vẫn hợp lệ vì `TaskExecutor` kế thừa `Executor`. Không nhầm với overload `submitCompletable` của `AsyncTaskExecutor`.
- Với `@Async`, chọn đúng executor và gọi method qua Spring proxy; timeout được gắn ở **future caller nhận** vẫn cần kết hợp timeout/cancellation ở tầng business operation.

### 7.1. Dự án Maven Spring có thể chạy độc lập

Ví dụ sử dụng **Spring Framework 6.1.3** và **JDK 17+**, tạo một `ThreadPoolTaskExecutor` dưới dạng bean Spring, rồi truyền trực tiếp vào `supplyAsync`. Một `CountDownLatch` giữ worker đang chạy để chứng minh `completeOnTimeout` trả fallback nhưng worker chưa dừng.

Cấu trúc:

~~~text
spring-timeout-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringTimeoutDemo.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-timeout-demo</artifactId>
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
                    <mainClass>demo.SpringTimeoutDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/java/demo/SpringTimeoutDemo.java`:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringTimeoutDemo {

    @Configuration
    public static class PoolConfiguration {

        @Bean("ioExecutor")
        public ThreadPoolTaskExecutor ioExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(2);
            pool.setThreadNamePrefix("io-");
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PoolConfiguration.class)) {

            ThreadPoolTaskExecutor executor =
                    context.getBean("ioExecutor", ThreadPoolTaskExecutor.class);

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            CountDownLatch workerReachedFinally = new CountDownLatch(1);

            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "remote-result";
                        } catch (InterruptedException ex) {
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            workerReachedFinally.countDown();
                        }
                    }, executor);

            try {
                if (!started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("worker did not start");
                }

                future.completeOnTimeout(
                        "cached-result", 100, TimeUnit.MILLISECONDS);

                System.out.println("springFallback=" + future.join());
                System.out.println("springWorkerFinishedAtFallback="
                        + (workerReachedFinally.getCount() == 0));
            } finally {
                release.countDown();
            }

            if (!workerReachedFinally.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("worker did not exit");
            }

            System.out.println("springResultAfterWork=" + future.join());
        }
    }
}
~~~

Chạy trong thư mục `spring-timeout-demo`:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra do chương trình Java in:

~~~text
springFallback=cached-result
springWorkerFinishedAtFallback=false
springResultAfterWork=cached-result
~~~

**Vì sao khác kết quả thật?** Worker của `ThreadPoolTaskExecutor` đang chờ `release`, còn future đã hoàn tất với `"cached-result"`. Khi worker được mở latch và trả `"remote-result"`, phép hoàn tất không ghi đè future đã có kết quả. `context.close()` trong `try-with-resources` kích hoạt container dọn executor bean.

**Không cần `@EnableAsync`** ở ví dụ này: chương trình dùng trực tiếp `CompletableFuture.supplyAsync(..., executor)`, không gọi một method `@Async` qua proxy. Đừng nhầm việc cấu hình executor bean với việc Spring tự chọn executor cho mọi `supplyAsync(supplier)` **không truyền tham số thứ hai**.

Đây là thí nghiệm có thời hạn 100 ms để quan sát; production phải chọn deadline dựa trên SLA thực, không lấy 100 ms làm mặc định cho tác vụ mạng.

## 8. Timeout của CompletableFuture khác timeout thật của HTTP, database và socket

Khi Supplier làm I/O đồng bộ như:

~~~java
// Phản ví dụ kiến trúc: remoteClient.fetch(id) là lời gọi I/O chặn.
// Mã chỉ minh họa; các biến/hàm không định nghĩa ở đây.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> remoteClient.fetch(id), ioExecutor)
        .completeOnTimeout("cached", 1, TimeUnit.SECONDS);
~~~

Caller có thể lấy `"cached"` sau 1 giây, nhưng `remoteClient.fetch` vẫn có thể chiếm một worker và connection. Cần **deadline cho operation thực**, ví dụ:

- **HTTP client:** connection timeout, response/read/request timeout tương thích với thư viện đang dùng. Với `java.net.http.HttpRequest.Builder.timeout(...)`, request timeout liên quan đến chính yêu cầu HTTP; khi dùng client SDK khác phải xem API của SDK.
- **JDBC/SQL:** query timeout ở `Statement.setQueryTimeout(...)` khi driver hỗ trợ, timeout giao dịch/bên database và chính sách cancel query. `Future.orTimeout` không phát lệnh cancel SQL.
- **Socket/SDK đồng bộ:** timeout đọc/ghi/tổng thời gian, khả năng hủy request và xử lý khi thread bị interrupt khác nhau giữa thư viện.
- **Bộ nhớ / hàng đợi:** pool bounded (`corePoolSize`, `maxPoolSize`, `queueCapacity`), semaphore/rate limit và admission control tránh số task “đã timeout nhưng vẫn còn chạy” tăng không giới hạn.
- **Vòng đời request:** nếu caller đã ngắt kết nối hoặc deadline hết, hệ thống vẫn phải quyết định business operation nên tiếp tục, hủy hợp tác hay lưu bền vững.

### Quy tắc phân bổ deadline

Giả sử API có SLA 2 giây. Không nên cho một DB query có thể chạy 30 giây trong khi Future trả fallback sau 2 giây rồi nghĩ hệ thống đã giải phóng tài nguyên. Hãy cân nhắc: thời gian queue wait, connect timeout, read/query timeout, retry budget và thời gian serialization/response.

**Một timeout ở tầng phản hồi không thay thế timeout ở tầng I/O.** Nếu thao tác phải bị hủy thật, cần dùng primitive mà thư viện cung cấp để hủy query/request, hoặc thiết kế cancellation có hợp đồng rõ ràng. Ngay cả khi có hủy, remote service có thể đã thực hiện side effect; cancellation không đồng nghĩa rollback.

## 9. Nếu cần hủy thật: cancel là yêu cầu, không phải phép màu

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` của JDK Java 17 được tài liệu hóa như một dạng **hoàn tất exceptionally bằng `CancellationException`**; tham số `mayInterruptIfRunning` **không dùng để ngắt computation** trong implementation `CompletableFuture`.

~~~java
// Fragment minh họa, future là CompletableFuture<T> đã có.
boolean cancelled = future.cancel(true);
boolean flag = future.isCancelled();
~~~

Dù `cancelled` có thể là true, điều đó không đủ để khẳng định worker đang chạy đã dừng. `CompletableFuture` không nhất thiết giữ handle của `Thread`/`FutureTask` đang thực thi Supplier.

Một `Future<?>` nhận được từ `ExecutorService.submit(...)` hoặc `AsyncTaskExecutor.submit(...)` có thể có khả năng `cancel(true)` để **thử interrupt worker** tùy implementation. Nhưng interrupt là **tín hiệu hợp tác**, không phải đảm bảo dừng mọi socket I/O, giao dịch, hoặc side effect.

~~~java
// Fragment: rawExecutor là ExecutorService có sẵn.
// Cần xử lý/khai báo InterruptedException và ExecutionException.
Future<String> operation = rawExecutor.submit(() -> remoteCall());
try {
    return operation.get(1, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    operation.cancel(true); // thử interrupt nếu implementation hỗ trợ
    throw ex;
}
~~~

Đây là fragment trong method có return type phù hợp, import `Future`/`TimeoutException`/`TimeUnit` và hàm `remoteCall()` của ứng dụng. `cancel(true)` **không thay thế timeout của HTTP/DB client**. Nếu caller đã gửi lệnh cập nhật dữ liệu, server nhận lệnh có thể vẫn xử lý dù local thread bị ngắt.

### Cooperative cancellation trong code tự viết

Với tác vụ tự điều khiển vòng lặp, có thể kiểm tra `Thread.currentThread().isInterrupted()` hoặc một token hủy có thread-safety phù hợp, đồng thời thoát trong thời gian hợp lý. Nhưng phải phân biệt:

1. **Future completion deadline** — khi caller được kết quả/lỗi.
2. **Cancellation request** — ai phát tín hiệu hủy, gửi tới đâu.
3. **Worker termination** — code thực thi thật đã dừng chưa.
4. **Resource cleanup** — connection, transaction, lock đã được đóng/hoàn tác phù hợp chưa.

Không có một lời gọi `completeOnTimeout` nào thực hiện đủ bốn trách nhiệm đó.

## 10. Tránh làm timeout che khuất kết quả và lỗi muộn

### 10.1. Kết quả muộn không tự được ghi vào Future đã hoàn tất

Nếu timeout/fallback đã thắng, một lần `Supplier` trả thành công sau đó thường không làm thay đổi giá trị caller thấy. Điều này đúng cho các completion bình thường của `CompletableFuture`: **first completion wins**. Tương tự, một exception xảy ra muộn trong Supplier có thể không còn hiển thị qua chính Future đã hoàn tất fallback.

Nếu tác vụ quan trọng, đừng chỉ log `future.whenComplete(...)` trên future đã dùng `completeOnTimeout` rồi cho rằng metric ấy phản ánh **thời gian chạy thật**. Nó có thể chạy lúc fallback xuất hiện, **trước khi worker kết thúc**.

Để đo công việc thật, instrument **bên trong Supplier** hoặc quanh thao tác mạng:

~~~java
// Fragment: ioExecutor và remoteClient là dependency đã có.
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(() -> {
            long startedAt = System.nanoTime();
            try {
                return remoteClient.fetch();
            } finally {
                recordOperationDuration(System.nanoTime() - startedAt);
            }
        }, ioExecutor).completeOnTimeout("cached", 1, TimeUnit.SECONDS);
~~~

Đây là fragment, không phải chương trình độc lập; `recordOperationDuration` và `remoteClient` chỉ để minh họa. Metric đo trong `finally` chạy khi **Supplier thật đến cuối**, khác với metric deadline của Future. Nếu cần biết operation có bị hủy hay không, phải đo thêm trạng thái/cancellation từ thư viện I/O.

### 10.2. Nếu cần tách Future của operation khỏi Future phản hồi

Vì `orTimeout`/`completeOnTimeout` trả **chính Future đã gọi**, áp timeout lên `upstream` sẽ thay trạng thái của chính upstream.

Nếu cần giữ **một Future gốc** để theo dõi kết quả thật, có thể dùng `copy()` (có từ Java 9) trước khi đặt timeout ở bản sao:

~~~java
// Fragment: upstream là CompletableFuture<String> đang chờ operation.
CompletableFuture<String> response =
        upstream.copy()
                .completeOnTimeout("cached", 1, TimeUnit.SECONDS);
~~~

`response` là một Future khác được đặt deadline. Nếu fallback thắng, nó không làm `upstream` tự chuyển thành `"cached"`; upstream vẫn có thể hoàn tất với giá trị/thất bại thật. **Tuy nhiên bản sao cũng không hủy thao tác bên dưới**. Đây là cách tách ngữ nghĩa completion, không phải cách quản lý I/O resources.

Đừng dùng `obtrudeValue(...)` để cưỡng bức sửa kết quả đã timeout rồi xem như giải quyết được việc cập nhật muộn; đây là API đặc biệt có thể gây bất nhất với dependent stages và không phải cơ chế timeout/late-result thông thường.

### 10.3. Nhiều timeout trên cùng Future có thể cạnh tranh nhau

~~~java
// Fragment minh họa một cách cấu hình dễ gây nhầm.
future.orTimeout(1, TimeUnit.SECONDS);
future.completeOnTimeout("cached", 2, TimeUnit.SECONDS);
~~~

Hai lời gọi trên tác động lên **cùng một future**. Nếu chưa hoàn tất và bộ hẹn 1 giây chạy trước, Future đã lỗi timeout; fallback 2 giây sau **không chuyển nó thành thành công**. Đừng xem chúng là hai Future độc lập có chính sách riêng.

Nếu có ý định báo fallback sau 1 giây nhưng cũng muốn lưu kết quả thật sau này, hãy giữ original Future và tạo một **response future khác** hoặc thiết kế explicit callback, deadline và state machine có kiểm soát.

## 11. Hệ quả production: retry, idempotency, resource exhaustion

### 11.1. Retry chồng lên thao tác chưa kết thúc

Một rủi ro nghiêm trọng:

1. Caller gửi `chargePayment(orderId)`.
2. `completeOnTimeout("pending", 2, SECONDS)` trả `"pending"` khi thao tác remote chưa xong.
3. Caller hiểu nhầm task đã dừng và gửi lại.
4. Hai yêu cầu thanh toán có thể đang xử lý đồng thời.

**Timeout không chứng minh tác vụ thất bại hoặc bị rollback.** Với nghiệp vụ có side effect, cần idempotency key, deduplication, trạng thái “unknown/pending”, kiểm tra kết quả ở nguồn sự thật và quy trình reconciliation. Đừng tự retry một lệnh có side effect chỉ vì một Future timeout.

### 11.2. Worker/connection vẫn bị giữ dù response nhanh

Ví dụ API fallback trong 100 ms nhưng HTTP client còn timeout 60 giây: nếu request đến liên tục, những task đã “trả kết quả” vẫn có thể giữ phần lớn pool, gây **`TaskRejectedException`** khi pool/queue đầy. Vì vậy monitoring chỉ đếm `CompletableFuture` hoàn tất không đủ; cần đọc active worker, queue depth, in-flight calls và timeout thật của downstream.

### 11.3. Cấu hình timeout theo ngân sách

- **Deadline ở API boundary:** caller có thể phản hồi sau mốc này, nhưng phải ghi nhận trạng thái operation là chưa chắc đã kết thúc.
- **Request/read/query timeout:** dừng chờ I/O ở tầng thư viện có khả năng kiểm soát hoạt động thực.
- **Retry budget:** số lần thử, backoff, jitter, idempotency và tổng thời hạn; tránh retry storm.
- **Concurrency limit:** không để số thao tác chạy nền tiếp tục tăng sau khi caller đã timeout.
- **Shutdown/cancellation:** xác định task nào phải chạy đến cùng, task nào được phép bỏ và giao thức giải phóng tài nguyên.

Không có một giá trị timeout “tối ưu chung” cho mọi hệ thống; cần đo p95/p99 latency, tỉ lệ timeout, tỉ lệ false fallback, queue wait và tải downstream.

## 12. Bảng xử lý lỗi đúng tầng

| Sự kiện | Future/caller nhận gì | Tầng cần xử lý |
| --- | --- | --- |
| Supplier hoàn tất trước deadline | Giá trị thật | Nghiệp vụ thông thường |
| `orTimeout` thắng | Future hoàn tất exceptionally với `TimeoutException` | Caller/response policy, metric deadline |
| `completeOnTimeout` thắng | Future hoàn tất bình thường với fallback | Gắn nhãn fallback, độ mới dữ liệu, cảnh báo |
| `get(timeout)` hết hạn | Caller nhận `TimeoutException`, Future **có thể còn pending** | Caller quyết định chờ lại, hủy hay thoát |
| Task đã được nhận nhưng ném lỗi | Future có thể hoàn tất exceptionally | `handle`/`exceptionally`, phân loại cause |
| Executor từ chối nộp task | Lỗi có thể ném **ngay tại `supplyAsync/submit`** | Catch quanh submission, capacity/lifecycle |
| Caller/worker bị interrupt | `InterruptedException` tại API chặn phù hợp, nếu implementation hỗ trợ | Phục hồi interrupt, cleanup hợp tác |
| Client HTTP đã ngắt kết nối | Future không tự biết mọi tài nguyên/remote work phải dừng | Request lifecycle và cancellation policy |

Với `ThreadPoolTaskExecutor`, rejection thường là `TaskRejectedException`, kế thừa `RejectedExecutionException` của JDK. Nó có thể xuất hiện **trước khi nhận được Future**; `future.exceptionally(...)` không thể xử lý một lời gọi chưa trả về Future.

Nếu task trả `CompletableFuture<T>` và đã hoàn tất exceptionally, `join()` thường ném unchecked `CompletionException` với cause gốc; `get()` thường ném checked `ExecutionException`. Với `orTimeout`, cause cần phân biệt là `TimeoutException`, không phải mọi exception đều do deadline.

## 13. Checklist kiểm thử và vận hành

### 13.1. Test hai trạng thái độc lập

1. Dùng latch để giữ Supplier **chưa hoàn tất**.
2. Đặt `orTimeout` và xác nhận Future hoàn tất lỗi `TimeoutException`, **worker vẫn chờ latch**.
3. Đặt `completeOnTimeout` ở một lần chạy khác và xác nhận Future nhận fallback trong khi Supplier vẫn chờ.
4. Mở latch và xác nhận Supplier đi tới `finally`; Future đã timeout/fallback **không đổi theo kết quả muộn**.
5. Dùng `get(timeout)` trên một Future chưa có timeout để xác nhận Future vẫn pending, rồi lấy được kết quả sau khi mở latch.
6. Test nhánh operation hoàn tất **trước** deadline để bảo đảm kết quả thật được giữ.
7. Test exception thật, rejection, interrupt, cancellation và cleanup; tránh test bằng `sleep` ngắn rồi assert millisecond tuyệt đối.
8. Kiểm tra connection/worker thật được giải phóng, không chỉ `isDone()` của Future.

### 13.2. Những số liệu nên theo dõi

- **Future deadline/fallback rate:** bao nhiêu response bị timeout hoặc dùng dữ liệu dự phòng.
- **Underlying operation duration:** HTTP/DB/SDK gọi bao lâu, kể cả sau khi response Future hoàn tất.
- **In-flight operations, active workers, pool size, queue depth:** công việc còn chiếm tài nguyên.
- **Rejection rate và downstream saturation:** tài nguyên cạn, queue đầy hoặc executor shutdown.
- **Late completion/late errors:** số operation về sau deadline; metric này không thể suy ra từ future đã hoàn tất sớm.
- **Business correctness:** duplicate operations, idempotency conflicts và giao dịch ở trạng thái không rõ kết quả.

### 13.3. Quy tắc lựa chọn

- Dùng `get(timeout)` nếu chỉ muốn **giới hạn thời gian caller đợi** và vẫn giữ Future gốc có khả năng hoàn tất sau.
- Dùng `orTimeout` nếu hợp đồng muốn **Future tự chuyển thành thất bại** ở mốc deadline và caller/dependent stages thấy lỗi.
- Dùng `completeOnTimeout` nếu nghiệp vụ chấp nhận **trả giá trị dự phòng** như kết quả của Future.
- Dùng **timeout của I/O thực, cancellation API và giới hạn concurrency** nếu cần giải phóng tài nguyên, tránh side effect muộn hoặc giảm áp lực lên thread pool.
- Dùng **bản sao hoặc Future phản hồi riêng** nếu muốn quan sát kết quả thật của operation mà không cho timeout làm mất trạng thái upstream.

## 14. Sai lầm thường gặp

1. **“`orTimeout` interrupt thread khi hết hạn.”** Sai. Nó hoàn tất `CompletableFuture` với lỗi; worker có thể vẫn chạy.
2. **“`completeOnTimeout` dừng HTTP rồi mới trả fallback.”** Sai. Nó chỉ hoàn tất Future với một giá trị nếu deadline thắng.
3. **“`future.get(timeout)` cũng sửa trạng thái Future thành timeout.”** Sai. Nó chỉ giới hạn một lần caller đợi.
4. **“`completeOnTimeout` trả Future mới, giữ nguyên Future cũ.”** Sai. Javadoc ghi **returns this CompletableFuture**.
5. **“Future đã `isDone` thì worker và connection chắc chắn đã được giải phóng.”** Sai khi timeout/fallback đã hoàn tất Future trước operation.
6. **“Có fallback thì không cần log lỗi muộn của task.”** Sai. Exception trong Supplier có thể xảy ra sau khi Future đã có fallback; cần quan sát operation thật.
7. **“`cancel(true)` trên CompletableFuture nhất định sẽ interrupt worker.”** Sai. Cờ `mayInterruptIfRunning` không điều khiển interrupt trong implementation này.
8. **“Đặt nhiều timeout trên cùng Future là tạo nhiều nhánh độc lập.”** Sai. Các lời gọi instance sửa cùng đối tượng.
9. **“Tăng thread pool là hết vấn đề.”** Sai. Downstream HTTP/SQL có thể tiếp tục quá lâu, làm cạn kết nối và nhân tải.
10. **“Retry sau timeout chắc chắn an toàn vì lần cũ đã dừng.”** Sai. Cần idempotency và xác minh trạng thái giao dịch.
11. **“Nếu `whenComplete` của Future đã chạy thì operation thật đã kết thúc.”** Sai khi timeout/fallback xảy ra trước Supplier completion.
12. **“Cần đổi sang `@Async` là mọi timeout đều tự ngắt operation.”** Sai. Spring async executor không thay đổi hợp đồng của `CompletableFuture` về timeout.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** `orTimeout(1, SECONDS)` hoàn tất Future với `TimeoutException`. SQL query bên trong Supplier có chắc đã dừng không?  
**Trả lời:** Không. Future completion không tự phát lệnh hủy SQL. Cần query timeout/cancellation ở tầng database/JDBC.

**Câu 2.** `completeOnTimeout("cached", 1, SECONDS)` thắng, sau đó Supplier trả `"fresh"`. `future.join()` trả gì?  
**Trả lời:** `"cached"`, vì Future đã hoàn tất bình thường với fallback; kết quả tới muộn không ghi đè completion trước.

**Câu 3.** `future.get(1, SECONDS)` ném `TimeoutException`, nhưng Future chưa gắn `orTimeout`. Có thể chờ tiếp và nhận kết quả thật không?  
**Trả lời:** Có, nếu task sau đó hoàn tất; timed `get` không hoàn tất/hủy Future.

**Câu 4.** `orTimeout` và `completeOnTimeout` trả về đối tượng nào?  
**Trả lời:** **Chính `CompletableFuture` được gọi**, không phải một bản sao.

**Câu 5.** `future.isDone()` đúng ngay sau `completeOnTimeout`. Có thể kết luận worker không còn hoạt động không?  
**Trả lời:** Không. `isDone` chỉ phản ánh Future; worker có thể đang giữ socket, DB connection hoặc tiếp tục side effect.

**Câu 6.** `CompletableFuture.cancel(true)` có bảo đảm interrupt Supplier không?  
**Trả lời:** Không. Java 17 Javadoc nêu `mayInterruptIfRunning` không có tác dụng điều khiển processing của `CompletableFuture`.

**Câu 7.** Nếu cần giữ kết quả thực sau timeout nhưng caller chỉ chờ tối đa 1 giây, lựa chọn nào đơn giản?  
**Trả lời:** Có thể dùng `get(1, SECONDS)` để giới hạn lần đợi, hoặc tạo `upstream.copy().completeOnTimeout(...)` để tách Future phản hồi khỏi upstream. Cả hai **không tự hủy task**.

**Câu 8.** Tại sao metric đếm Future hoàn tất không đủ để phát hiện quá tải?  
**Trả lời:** Future có thể đã hoàn tất sớm do deadline/fallback dù các operations thật vẫn đang giữ worker và connection; cần đo underlying in-flight work, queue và resource usage.

## 16. Tài liệu tham khảo chính thức

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `orTimeout`, `completeOnTimeout` (trả `this`), `copy`, `cancel`, completion semantics và `join`.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout)`, `cancel`, `isDone`, interrupt và cơ chế quan sát kết quả.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): nộp task, `shutdown`, `Future` và lifecycle executor.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): timeout ở tầng yêu cầu HTTP đối với Java HTTP client.
- [Java SE 17 — Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): `setQueryTimeout` và khả năng driver xử lý query timeout.
- [Spring Framework 6.1.3 — AsyncTaskExecutor](https://www.springframework.org/spring/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): `submitCompletable` (từ Spring 6.0), `Future` và rejection.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor](https://www.springframework.org/spring/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): cấu hình thread pool, queue, exception và lifecycle.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): lựa chọn Spring `TaskExecutor`, `@Async`, quản lý pool và xử lý tác vụ.
