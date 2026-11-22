# AbortPolicy báo lỗi tại điểm gửi tác vụ

## Mục tiêu và phạm vi

Khi một ứng dụng Spring đẩy công việc sang thread pool, có hai câu hỏi tách biệt: **pool đã nhận công việc chưa?** và **công việc đã thực hiện thành công chưa?** Chính sách `ThreadPoolExecutor.AbortPolicy` giải quyết câu hỏi đầu tiên: nếu pool không thể nhận task mới, nó **ném exception ngay tại điểm gửi**. Đây là tín hiệu quá tải hoặc executor đã đóng, cần được xử lý ngay ở caller.

Sau bài này, bạn có thể:

- Giải thích điều kiện `ThreadPoolExecutor` từ chối task: **pool/queue bão hòa** hoặc **shutdown**.
- Phân biệt `RejectedExecutionException` của JDK với `TaskRejectedException` khi đi qua `ThreadPoolTaskExecutor` của Spring.
- Dự đoán sự tương tác giữa `corePoolSize`, `maxPoolSize`, `queueCapacity` và rejection handler.
- Viết ví dụ Java 17+ và Spring có tình huống từ chối **xác định bằng latch**, không dựa vào `sleep()` may rủi.
- Phân biệt exception **ngay lúc `execute/submit`** với exception xảy ra **bên trong task**; lựa chọn xử lý phù hợp cho HTTP, queue và job.
- Chẩn đoán rejection, giám sát backlog và tránh các cách xử lý gây mất dữ liệu hoặc retry storm.

**Phạm vi:** `java.util.concurrent.ThreadPoolExecutor` và `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor`. Ví dụ JDK chạy với Java 17+, ví dụ Spring dùng **Spring Framework 6.1.3** và Maven. Nội dung mô tả mô hình platform thread pool thông thường, không mặc định áp dụng cho executor tạo virtual thread cho mỗi task.

## 1. Hiểu đúng hai giai đoạn: nhận task và chạy task

Khi caller gửi một `Runnable`, executor trước hết cần **tiếp nhận (admission)** rồi mới lên lịch **thực thi (execution)**. Việc `execute(...)` trả về bình thường chỉ nói rằng task đã được nhận, **không nói task đã hoàn thành**.

| Giai đoạn và kết quả | Điều xảy ra | Caller thấy gì? |
| --- | --- | --- |
| `execute(task)` được nhận | Task được worker chạy hoặc vào queue | Phương thức gửi trả về bình thường |
| `execute(task)` bị từ chối bởi AbortPolicy | Task **không được nhận** | Ném unchecked exception ngay trong lời gọi gửi |
| `submit(callable)` được nhận | Caller có `Future`; task sẽ chạy sau | Có thể chờ bằng `Future.get()` |
| `submit(callable)` bị từ chối | Không có `Future` hợp lệ | Exception ném **trước khi `submit` trả về** |
| Task đã nhận nhưng `run()/call()` ném lỗi | Lỗi xảy ra khi chạy task | Quan sát qua `Future.get()`, callback hoặc log theo API |
| Executor đã shutdown | Không nhận task mới dù queue rỗng | AbortPolicy cũng ném exception tại điểm gửi |

`AbortPolicy` chỉ từ chối **task mới**. Nó không tự động xóa task đã nằm trong queue, không dừng task đang chạy và không rollback những side effect đã xảy ra từ các task được nhận trước đó.

### Tại sao phải bắt lỗi ở caller?

Cơ chế rejection chạy trong **luồng đang gọi `execute/submit`**, ví dụ request thread của Spring MVC hoặc thread của một scheduler. Nếu task không được chấp nhận, **phần thân Runnable chưa chạy**, nên `try/catch` đặt *bên trong* Runnable đó không thể bắt lỗi rejection của chính lời gọi gửi task.

~~~java
// Fragment trong một service có biến executor kiểu TaskExecutor.
try {
    executor.execute(() -> performWork());
    // Đã gửi thành công; chưa có nghĩa performWork() hoàn thành.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Pool không tiếp nhận task: xử lý ngay trong caller.
    recordAdmissionFailure(ex);
}
~~~

Đây là **đoạn minh họa**, không phải Java class độc lập; giả sử ứng dụng đã có `executor`, `performWork()` và `recordAdmissionFailure(...)`. Nếu không bắt ở ranh giới phù hợp, exception sẽ tiếp tục lan lên caller/framework.

## 2. Khi nào ThreadPoolExecutor gọi RejectedExecutionHandler?

### 2.1. Quy trình nhận việc

Với `ThreadPoolExecutor` thông dụng, `execute(Runnable)` hoạt động theo các bước khái quát:

1. Khi số worker còn dưới `corePoolSize`, thử tạo worker mới để chạy task.
2. Khi đã có đủ core workers, thử đưa task vào **work queue**.
3. Nếu queue **không nhận được** task, thử tạo worker vượt core, nhưng không vượt `maximumPoolSize`.
4. Nếu việc tạo worker cũng thất bại do đã đạt giới hạn, chuyển task sang `RejectedExecutionHandler`.
5. Nếu executor đã `shutdown()`, task mới cũng bị từ chối; mã JDK có các kiểm tra trạng thái lại để xử lý race với shutdown.

~~~text
                  task mới
                     |
           executor đang nhận việc?
              /             \
            không            có
              |               |
          REJECTION       workers < core?
                           /       \
                         có         không
                         |            |
                    tạo worker     queue nhận?
                                     /     \
                                   có       không
                                   |           |
                                xếp hàng    workers < max?
                                               /     \
                                             có       không
                                              |          |
                                         tạo worker   REJECTION
~~~

Sơ đồ là mô hình để học; mã thực tế có nhiều kiểm tra lại do concurrency. Đừng dùng snapshot `getQueue().size()` để cam kết task tiếp theo sẽ được nhận.

### 2.2. Ví dụ pool có giới hạn

Giả sử `corePoolSize=1`, `maxPoolSize=2` và `queueCapacity=1`, đồng thời các task trước vẫn đang bận/chờ trong suốt lúc gửi:

| Task | Diễn biến khi chưa task nào hoàn tất |
| --- | --- |
| A | Tạo core worker thứ nhất |
| B | Vào queue một slot |
| C | Queue đã đầy, tạo worker thứ hai |
| D | Queue đầy và worker đạt max=2; bị từ chối |

Nếu A hoặc C hoàn thành trước khi D đến, D **có thể được nhận**. Đó là lý do bài thực hành sẽ giữ A bằng `CountDownLatch` thay vì hy vọng task chạy đủ chậm.

### 2.3. Queue và maximumPoolSize ảnh hưởng rejection ra sao?

`ThreadPoolTaskExecutor` mặc định có `corePoolSize=1`, `maxPoolSize=Integer.MAX_VALUE` và `queueCapacity=Integer.MAX_VALUE`. Khi queue rất lớn, những task vượt năng lực core thường bị **xếp hàng**; pool không có lý do tạo nhiều worker vượt core cho đến khi queue không nhận thêm. Kết quả là ứng dụng có thể chậm nghiêm trọng hoặc tốn tài nguyên trước khi thấy rejection do **đầy queue**.

Để đặt giới hạn có chủ đích, cấu hình **core/max/queue hữu hạn** sau khi hiểu tốc độ task đến, thời gian chạy, giới hạn CPU, kết nối database và độ trễ được chấp nhận. Với `queueCapacity=0`, Spring dùng `SynchronousQueue`: task phải được trao ngay cho một worker, không có vị trí để xếp hàng. Với `queueCapacity>0`, Spring dùng queue có dung lượng tương ứng.

## 3. AbortPolicy: chính sách fail-fast mặc định

`java.util.concurrent.RejectedExecutionHandler` là contract cho việc xử lý tác vụ không được nhận. `ThreadPoolExecutor.AbortPolicy` là handler mặc định của `ThreadPoolExecutor`; nó **luôn ném `RejectedExecutionException`** khi `rejectedExecution(...)` được gọi.

~~~java
new ThreadPoolExecutor.AbortPolicy()
~~~

Đây chỉ là **biểu thức khởi tạo handler**, không phải chương trình độc lập. `RejectedExecutionException` kế thừa `RuntimeException`, nên caller không bị trình biên dịch bắt buộc khai báo `throws`, nhưng vẫn cần chính sách xử lý rõ ràng.

Ví dụ, khi task C bị từ chối:

~~~text
Caller thread                   Thread pool
     |                              |
     | execute(task C)              | worker đang chạy A
     | ---------------------------> | queue đang chứa B
     |                              |
     | <--- RejectedExecutionException
     |
     +-- catch trong caller
          C chưa được nhận
          A và B không tự bị hủy
~~~

**“Abort” ở đây không có nghĩa hủy toàn bộ pool**: nó ném lỗi cho lời gọi gửi **task đang bị từ chối**. Các task được nhận từ trước vẫn hoạt động theo vòng đời riêng, trừ khi có thao tác shutdown/cancellation khác.

Có hai nhóm nguyên nhân chính:

- **Bão hòa:** queue không nhận thêm và worker đã đến giới hạn; task mới bị từ chối.
- **Executor ngừng nhận việc:** `shutdown()`, quá trình đóng Spring context hoặc vòng đời executor khiến task mới không được nhận, ngay cả khi queue còn trống.

Không thể kết luận cứ gặp `RejectedExecutionException` là phải tăng `maxPoolSize`: trước hết phải xác minh executor đang shutdown hay bão hòa, hàng đợi có tăng hay không và downstream có phải nút thắt thực hay không.

## 4. Ví dụ Java 17+ độc lập: rejection xảy ra ngay tại execute()

Ví dụ sau dùng một worker và một slot queue. Một `CountDownLatch` xác nhận task A đã bắt đầu, latch còn lại giữ A đang chờ. Sau đó task B chiếm queue. Do đó task C chắc chắn bị từ chối tại thời điểm nộp.

Lưu thành `AbortPolicyDemo.java`:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class AbortPolicyDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // A đang giữ worker duy nhất

            pool.execute(() -> { }); // B vào queue

            try {
                pool.execute(() -> { }); // C bị từ chối
                System.out.println("unexpected-accepted");
            } catch (RejectedExecutionException ex) {
                System.out.println("jdk-rejected="
                        + ex.getClass().getSimpleName());
            }

            System.out.println("queue=" + pool.getQueue().size());
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

Chạy bằng JDK 17+:

~~~bash
javac AbortPolicyDemo.java
java AbortPolicyDemo
~~~

Đầu ra xác định:

~~~text
jdk-rejected=RejectedExecutionException
queue=1
~~~

**Vì sao kết quả xác định?**

1. `started.await()` bảo đảm A đã chạy và báo đã bắt đầu.
2. A đang chờ `release`, nên worker duy nhất chưa thể xử lý task mới.
3. B chiếm đúng slot queue duy nhất.
4. C không vào được queue và không được tạo thêm worker (core=max=1), khiến `AbortPolicy` ném exception ngay trong **thread main**.
5. C không làm mất B; khi main in `queue=1`, B vẫn chờ.
6. `finally` mở latch, shutdown pool, đợi kết thúc để không để lại worker bị kẹt.

Nếu bỏ latch và chỉ cho A gọi `Thread.sleep(100)`, kết quả sẽ phụ thuộc lịch chạy và tốc độ máy, không phù hợp làm kiểm thử ổn định.

## 5. Trong Spring, TaskRejectedException là lỗi cần bắt

`ThreadPoolTaskExecutor` quản lý một `ThreadPoolExecutor` nội bộ và thực thi `TaskExecutor` của Spring. Handler mặc định vẫn là **AbortPolicy**. Spring chuyển exception không nhận task theo contract thành `org.springframework.core.task.TaskRejectedException`. `TaskRejectedException` là một lớp con của `RejectedExecutionException`.

| Lời gọi | Khi bị từ chối với AbortPolicy |
| --- | --- |
| `ThreadPoolExecutor.execute(...)` từ JDK | `RejectedExecutionException` |
| `ThreadPoolTaskExecutor.execute(...)` từ Spring | `TaskRejectedException` |
| `ThreadPoolTaskExecutor.submit(...)` | `TaskRejectedException` trước khi trả `Future` |
| `AsyncTaskExecutor.submitCompletable(...)` (Spring 6.0+) | `TaskRejectedException` trước khi trả `CompletableFuture` |

Với API Spring, nên catch `TaskRejectedException` vì nó thể hiện hợp đồng Spring và giúp code phân biệt rejection từ Spring với lỗi được ném ở tầng khác. Catch lớp cha `RejectedExecutionException` vẫn bắt được, nhưng có thể làm mờ nguồn lỗi.

### 5.1. Dự án Maven Spring chạy độc lập

Để kiểm chứng chính exception của Spring, tạo một dự án nhỏ với **Java 17+** và **Spring Framework 6.1.3**. Chương trình chạy bằng `main`, không cần mở Spring Boot server và không cần `@EnableAsync` vì gọi trực tiếp `executor.execute(...)`.

Cấu trúc:

~~~text
spring-abort-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SpringAbortDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-abort-demo</artifactId>
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
                    <mainClass>demo.SpringAbortDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/demo/SpringAbortDemo.java`:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SpringAbortDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(1);
        pool.setThreadNamePrefix("abort-demo-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.initialize();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            started.await(); // A đang giữ worker
            pool.execute(() -> { }); // B nằm trong queue

            try {
                pool.execute(() -> { }); // C bị từ chối
                System.out.println("unexpected-accepted");
            } catch (TaskRejectedException ex) {
                System.out.println("spring-rejected="
                        + ex.getClass().getSimpleName());
            }

            System.out.println("queue=" + pool.getQueueSize());
        } finally {
            release.countDown();
            ThreadPoolExecutor nativePool =
                    pool.getThreadPoolExecutor();
            pool.shutdown();
            if (!nativePool.awaitTermination(5, TimeUnit.SECONDS)) {
                nativePool.shutdownNow();
            }
        }
    }
}
~~~

Chạy trong thư mục `spring-abort-demo`:

~~~bash
mvn -q compile exec:java
~~~

Đầu ra do chương trình Java in, không tính log riêng từ Maven nếu có:

~~~text
spring-rejected=TaskRejectedException
queue=1
~~~

Spring nhận cùng tình huống worker bận và queue đầy, nhưng báo `TaskRejectedException` ở lời gọi `ThreadPoolTaskExecutor.execute(...)`. Ta in **tên lớp exception** thay vì toàn bộ `getMessage()`, vì nội dung thông báo có thể thay đổi giữa phiên bản. Việc in `queue=1` xác nhận task B vẫn nằm trong queue khi C bị từ chối.

`setRejectedExecutionHandler(new AbortPolicy())` ở đây chỉ làm rõ chính sách; đó đã là mặc định nếu bạn không thay handler. `initialize()` cần thiết vì pool được tạo thủ công. Trong ứng dụng Spring, hãy dùng **bean singleton** và để container quản lý vòng đời.

### 5.2. Cấu hình làm bean Spring

Trong một ứng dụng Spring đã bật component scanning, có thể cấu hình executor dùng chung như sau (đây là **fragment tích hợp**, không phải dự án độc lập):

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class BoundedPoolConfig {
    @Bean("boundedExecutor")
    public ThreadPoolTaskExecutor boundedExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(8);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("bounded-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return pool;
    }
}
~~~

Các số `4/8/100` là ví dụ về giới hạn hữu hạn, **không phải cấu hình tối ưu mặc định**. Nếu dùng `@Async("boundedExecutor")`, Spring cần async method processing (ví dụ `@EnableAsync`) và lời gọi phải đi qua proxy; tự gọi method bên trong cùng object có thể bỏ qua proxy. Khi executor không nhận được task tại thời điểm proxy gửi, rejection có thể nổi lên từ **lời gọi method của caller**, nên tầng gọi cần có chiến lược xử lý.

## 6. Rejection khi submit và lỗi chạy task là hai luồng khác nhau

`ThreadPoolTaskExecutor.submit(...)` trả `Future` chỉ **khi task đã được nhận**. Nếu AbortPolicy từ chối, `submit` ném `TaskRejectedException` **ngay lúc gọi**. Sau khi task được chấp nhận, lỗi do `Callable.call()` mới được quan sát qua `Future.get()`.

~~~java
// Fragment trong service có asyncExecutor kiểu AsyncTaskExecutor
// và các phương thức reportSubmissionFailure, reportTaskFailure.
Future<Integer> future;
try {
    future = asyncExecutor.submit(() -> calculate());
} catch (TaskRejectedException ex) {
    reportSubmissionFailure(ex);
    return;
}

try {
    Integer result = future.get();
    System.out.println(result);
} catch (ExecutionException ex) {
    reportTaskFailure(ex.getCause());
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
}
~~~

Đây là **đoạn minh họa bên trong một method trả `void`**; cần import `Future`, `ExecutionException`, `InterruptedException`, `TaskRejectedException` và có biến/hàm của service. `future.get()` có thể chặn thread caller; không gọi nó tùy tiện trong worker đang phụ thuộc vào cùng pool nhỏ vì có thể tạo starvation/deadlock. Lỗi được ném trong task **không quay lại catch tại điểm `submit`**.

Với Spring 6.0+ có `AsyncTaskExecutor.submitCompletable(...)` trả `CompletableFuture`. Các stage `exceptionally(...)` hoặc `handle(...)` xử lý **future đã trả về**; nếu việc nộp bị từ chối trước khi trả future, callback **chưa tồn tại**. Vì vậy vẫn phải bọc lời gọi `submitCompletable` bằng `try/catch(TaskRejectedException)`, rồi mới nối callback cho lỗi thực thi.

### Khi bị từ chối, task có “biến mất” không?

Với AbortPolicy, task bị từ chối **không nằm trong queue** và không được chạy. Nếu ứng dụng nuốt exception, đó là **mất công việc ở tầng nghiệp vụ** do code bỏ qua lỗi. Nếu công việc phải được xử lý chắc chắn, bạn cần giao thức nhận việc có lưu bền vững (ví dụ durable queue hoặc transactional outbox), acknowledgement rõ ràng và cơ chế retry hợp lệ. Executor trong bộ nhớ không thay thế một hệ thống đảm bảo giao hàng.

Không báo HTTP “đã nhận để xử lý” khi việc gửi executor đã thất bại, trừ khi một thành phần bền vững khác thực sự đã ghi nhận công việc.

## 7. Xử lý quá tải đúng vị trí

Tùy trách nhiệm của API, ứng dụng có thể:

- **Fail fast** với phản hồi rõ cho caller. HTTP 503 thường phù hợp với tình trạng service tạm thiếu năng lực; HTTP 429 thường phù hợp hơn với hạn mức theo client. Không tự động chuyển mọi `TaskRejectedException` thành một mã cố định khi chưa xét hợp đồng API.
- **Retry hữu hạn** với exponential backoff/jitter khi task có thể retry an toàn và dữ liệu đầu vào còn hiệu lực. Tránh retry tức thì liên tục ngay trong catch vì có thể tạo retry storm.
- **Giảm tốc đầu vào** bằng semaphore, rate limiter, admission control hoặc backpressure ở upstream trước khi hàng đợi phình lớn.
- **Dời công việc sang durable queue** nếu không được phép mất task và caller có thể chờ xử lý sau; cần thiết kế idempotency và xác nhận enqueue.
- **Sửa lifecycle** nếu pool đã shutdown, chẳng hạn task scheduler vẫn nộp việc trong khi Spring context đang đóng.

Không phải cứ tăng `maxPoolSize` là xử lý được quá tải: task có thể đang chờ DB connection hoặc external API, nên tăng số worker chỉ làm nhiều tác vụ cạnh tranh cùng tài nguyên hơn.

### So sánh các chính sách từ chối

| Chính sách | Hành vi khi bị từ chối | Đánh đổi |
| --- | --- | --- |
| **AbortPolicy** | Ném `RejectedExecutionException` ngay tại caller | Rõ ràng, dễ fail fast; caller phải có kế hoạch xử lý |
| `CallerRunsPolicy` | Chạy task trên **caller thread** nếu executor chưa shutdown | Tạo backpressure gián tiếp nhưng có thể chặn HTTP/event-loop thread; khi shutdown có thể bỏ task |
| `DiscardPolicy` | Bỏ task mà không ném lỗi | Dễ gây mất tác vụ âm thầm |
| `DiscardOldestPolicy` | Loại task cũ nhất trong queue rồi thử nhận task mới | Có nguy cơ mất task và phá vỡ kỳ vọng thứ tự, đặc biệt nguy hiểm khi có Future |

Đừng thay `AbortPolicy` bằng `DiscardPolicy` chỉ để “không còn exception”: điều đó biến một sự cố quan sát được thành mất công việc không dễ phát hiện. Với `CallerRunsPolicy`, phải kiểm tra chi phí chạy task trên caller và cách xử lý khi executor đã shutdown.

Nếu dùng custom `RejectedExecutionHandler` để tăng counter, hãy **vẫn ném rejection** khi muốn giữ nghĩa fail fast; handler chỉ ghi log rồi return bình thường có thể khiến phía gọi hiểu nhầm rằng task được nhận.

## 8. Giám sát và kiểm thử

### 8.1. Các số liệu nên theo dõi

- **Tỉ lệ rejected task:** ghi tại catch `TaskRejectedException` hoặc handler có metric; phân biệt rejection do quá tải và shutdown khi có đủ ngữ cảnh.
- **Active workers / pool size:** `getActiveCount()`, `getPoolSize()` chỉ là snapshot.
- **Queue depth / wait duration:** `getQueueSize()` và thời gian chờ hàng đợi; queue tăng liên tục là tín hiệu backlog.
- **Task duration / throughput / p95-p99 latency:** cho biết bottleneck do task chậm hoặc lưu lượng vượt khả năng xử lý.
- **Tình trạng downstream:** DB connection pool, socket, API quota, CPU, memory và GC.

Không viết logic kiểu “đọc queue đang 0 rồi chắc chắn submit sẽ thành công”, vì các thread khác có thể đổi trạng thái ngay sau lần đọc. Chính lời gọi `execute/submit` và handler là cơ chế quyết định việc nhận task.

### 8.2. Các trường hợp kiểm thử cần có

1. **Saturation:** core=max=1, queue=1; dùng latch giữ task đầu, gửi task thứ hai vào queue và xác nhận task thứ ba bị từ chối ngay khi submit.
2. **Normal acceptance:** không đầy queue, gọi `execute` thành công; theo dõi task hoàn tất riêng.
3. **Shutdown:** gọi `shutdown()` rồi gửi task mới; kiểm tra lỗi rejection ngay dù queue rỗng.
4. **Task failure:** nộp `Callable` được nhận nhưng ném exception; kiểm tra `Future.get()` trả `ExecutionException`, không nhầm với rejection.
5. **Đường Spring:** xác nhận catch `TaskRejectedException` ở chỗ gọi `ThreadPoolTaskExecutor.execute` thay vì chỉ đợi log từ worker.
6. **Recovery:** quá tải giảm thì task gửi mới có thể tiếp tục được nhận, miễn pool chưa shutdown; không retry vô hạn khi điều kiện chưa thay đổi.

Dùng latch/barrier và giới hạn rõ ràng cho kiểm thử thay vì `Thread.sleep(100)`; việc phụ thuộc tốc độ CPU có thể làm test thỉnh thoảng thất bại trên CI.

## 9. Lỗi thường gặp và cách sửa

1. **Catch exception bên trong task bị từ chối.** Không hiệu quả vì task không chạy; bắt quanh `execute/submit` tại caller.
2. **Cho rằng submit luôn trả Future kể cả khi quá tải.** Không đúng: rejection có thể ném trước khi Future được trả.
3. **Chỉ xử lý `CompletableFuture.exceptionally`.** Không bắt được lời gọi `submitCompletable` đã ném exception đồng bộ.
4. **Nghĩ AbortPolicy dừng cả executor.** Nó từ chối task hiện tại; các task đã nhận vẫn tiếp tục theo lifecycle.
5. **Cấu hình queue gần vô hạn và mong `maxPoolSize` tăng worker nhanh.** Pool ưu tiên queue sau khi đạt core, nên max có thể không được dùng như kỳ vọng.
6. **Tăng pool vô hạn để tránh rejection.** Có thể đẩy giới hạn sang DB, memory hoặc network; cần điều tiết tải và đo năng lực thực.
7. **Nuốt TaskRejectedException rồi trả “đã nhận”.** Caller sẽ mất thông tin task chưa được xử lý.
8. **Đổi sang DiscardPolicy để loại bỏ lỗi.** Task bị mất mà không có tín hiệu; chỉ dùng khi nghiệp vụ thực sự cho phép bỏ task.
9. **Retry ngay trong vòng lặp không giới hạn.** Có thể khiến tình trạng quá tải tự khuếch đại.
10. **Đồng nhất rejection do shutdown với bão hòa.** Cần kiểm tra lifecycle và thông tin tại thời điểm xảy ra sự cố.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Pool `core=1,max=1,queue=1` đang chạy A và xếp hàng B. Task C gửi vào sẽ ra sao?  
**Trả lời:** C không vào queue và không tạo thêm worker được, vì vậy AbortPolicy ném exception ngay tại lời gọi gửi, nếu A vẫn đang chiếm worker.

**Câu 2.** Tại sao `try/catch` trong thân của C không thể xử lý rejection?  
**Trả lời:** C chưa được nhận nên thân C chưa hề chạy.

**Câu 3.** Spring `ThreadPoolTaskExecutor` sử dụng AbortPolicy. Caller nên bắt exception nào?  
**Trả lời:** `TaskRejectedException` theo hợp đồng Spring; lớp này kế thừa `RejectedExecutionException` của Java.

**Câu 4.** `submit` đã trả `Future`, nhưng task ném `IllegalStateException` khi chạy. Đây là rejection?  
**Trả lời:** Không. Executor đã nhận task; lỗi thực thi được quan sát qua `Future.get()` dưới dạng `ExecutionException` có cause là lỗi gốc.

**Câu 5.** Executor đã shutdown nhưng queue không đầy. AbortPolicy có thể từ chối task mới không?  
**Trả lời:** Có. Shutdown là một nguyên nhân rejection độc lập với saturation.

**Câu 6.** Vì sao thay AbortPolicy bằng DiscardPolicy có thể gây rủi ro nghiệp vụ?  
**Trả lời:** Task mới có thể bị bỏ mà caller không được báo lỗi; hệ thống dễ ghi nhận nhầm công việc đã nhận.

## Tham khảo chính thức

- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): quy tắc core/queue/max, shutdown, rejected tasks và các handler.
- [Java SE 17 — ThreadPoolExecutor.AbortPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html): handler mặc định luôn ném `RejectedExecutionException`.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): cấu hình executor, mặc định core/max/queue, exception theo hợp đồng Spring.
- [Spring Framework 6.1.3 — TaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskExecutor.html): phương thức `execute(Runnable)` và `TaskRejectedException`.
- [Spring Framework 6.1.3 — AsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): cách `submit` và `submitCompletable` trả kết quả và báo lỗi khi bị từ chối.
- [Spring Framework 6.1.3 — TaskRejectedException](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskRejectedException.html): exception Spring khi không nhận task.
