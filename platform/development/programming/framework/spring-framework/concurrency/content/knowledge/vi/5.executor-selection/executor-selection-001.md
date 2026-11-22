# SyncTaskExecutor chạy ngay trên luồng gọi

## 1. Mục tiêu và ý tưởng cốt lõi

Trong Spring Framework, `TaskExecutor` là một abstraction để gửi công việc (một `Runnable`) cho thành phần thực thi. Tên “executor” **không bảo đảm** rằng công việc sẽ được đưa sang luồng mới. `org.springframework.core.task.SyncTaskExecutor` là trường hợp rõ nhất: khi gọi `execute(task)`, nó **chạy `task.run()` ngay trên luồng đang gọi**, và chỉ trả về sau khi `run()` kết thúc hoặc ném ngoại lệ.

Đây là một lựa chọn có chủ đích trong nhóm “**Chọn bộ thực thi**”: dùng nó khi muốn thực thi đồng bộ, hành vi dễ dự đoán hoặc không cần tách tác vụ khỏi caller. Không dùng chỉ vì thấy chữ “TaskExecutor” rồi cho rằng công việc sẽ tự chạy nền.

Ví dụ một luồng HTTP đang xử lý request:

~~~text
Luồng http-nio-8080-exec-1:
  log("before")
  syncTaskExecutor.execute(job)
    -> job.run()        [vẫn chính http-nio-8080-exec-1]
    -> job.run() xong
  log("after")

Thứ tự luôn là before -> toàn bộ job -> after nếu job kết thúc bình thường.
~~~

**Phân biệt quan trọng:** “đồng bộ” ở đây nghĩa là **mỗi lời gọi `execute` chờ chính task của nó**. Nó **không** có nghĩa rằng mọi task trên toàn ứng dụng được tuần tự hóa bằng một khóa. Nếu request A và B đang được xử lý trên hai luồng HTTP khác nhau, cùng một instance `SyncTaskExecutor` có thể chạy hai task đồng thời trên hai luồng gọi đó.

## 2. Cơ chế thực thi

Hợp đồng đơn giản nhất là:

~~~java
// Mã giả mô tả cơ chế; không phải source code Spring chép nguyên văn.
public void execute(Runnable task) {
    task.run(); // Gọi trực tiếp trên luồng hiện tại.
}
~~~

Phiên bản Spring thực còn kiểm tra đối số hợp lệ và có thể bổ sung cơ chế theo phiên bản framework; nhưng thuộc tính quyết định của `SyncTaskExecutor` vẫn là **thực thi trên caller thread**. Với Spring Framework 6.x dùng trong ví dụ bên dưới, không có pool thread hay hàng đợi nhiệm vụ bên trong executor này.

### Các hệ quả trực tiếp

- **Không chuyển luồng:** `Thread.currentThread()` bên trong task là cùng đối tượng thread của caller tại thời điểm gọi.
- **Có chặn caller:** task chạy 2 giây thì lời gọi `execute` cũng phải ở trong task khoảng 2 giây, cộng chi phí nhỏ của lời gọi Java. Nếu caller là HTTP request thread, thời gian phản hồi bị kéo dài.
- **Không có hàng đợi riêng:** không có nơi để gửi công việc rồi trả về ngay, không có số worker cố định hay throughput độc lập với số luồng đang gọi.
- **Kết quả / lỗi trực tiếp:** `execute(Runnable)` trả `void`; giá trị kết quả cần do code của caller/task quản lý. Nếu chính `Runnable.run()` ném unchecked exception mà không bắt, exception lan ra từ lời gọi `execute` trong trường hợp dùng trực tiếp.
- **Giữ ngữ cảnh luồng:** thread-local state, thread context classloader và mối liên kết transaction hiện tại của luồng vẫn là cùng ngữ cảnh trong lúc task chạy. Điều này có thể tiện khi test nhưng task cũng có thể vô tình thay đổi ngữ cảnh của caller.
- **Không tự bảo vệ shared state:** hai caller threads độc lập vẫn có thể đồng thời sửa cùng field của singleton service; cần atomic/lock/transaction theo đúng phạm vi dữ liệu.

Khác với `ThreadPoolTaskExecutor`, không có cấu hình `corePoolSize`, `maxPoolSize`, `queueCapacity` theo mô hình thread pool cho executor này trong Spring 6.x. Không suy ra những thuộc tính của bản Spring khác cho API đã được chọn.

## 3. Ví dụ chạy được: trực tiếp dùng SyncTaskExecutor

Ví dụ này dùng **Java 17** và **Spring Framework 6.2.12**. Nó chứng minh ba điểm bằng kết quả ổn định:

1. Task chạy giữa hai dòng `before/after` trên đúng caller thread.
2. Unchecked exception của task đi ra caller khi dùng trực tiếp `execute`.
3. Hai luồng gọi khác nhau có thể cùng chạy task trên một `SyncTaskExecutor` (không có khóa tuần tự toàn cục).

### 3.1. Cấu trúc tệp

~~~text
sync-executor-demo/
├── pom.xml
└── src/main/java/com/example/executor/
    └── SyncTaskExecutorDemo.java
~~~

### 3.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>sync-executor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` kéo theo `spring-core`, nơi chứa `TaskExecutor` và `SyncTaskExecutor`. Không cần Spring Boot, web server hay annotation để gọi API trực tiếp.

### 3.3. SyncTaskExecutorDemo.java

~~~java
package com.example.executor;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;

public final class SyncTaskExecutorDemo {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static void main(String[] args) throws InterruptedException {
        Thread.currentThread().setName("request-caller");
        TaskExecutor executor = new SyncTaskExecutor();

        REQUEST_ID.set("REQ-42");
        try {
            System.out.println("1 before: " + Thread.currentThread().getName());

            executor.execute(() -> {
                System.out.println("2 task: " + Thread.currentThread().getName());
                System.out.println("3 trace: " + REQUEST_ID.get());
            });

            System.out.println("4 after: " + Thread.currentThread().getName());
        } finally {
            REQUEST_ID.remove();
        }

        try {
            executor.execute(() -> {
                throw new IllegalStateException("boom");
            });
        } catch (IllegalStateException ex) {
            System.out.println("5 caught: " + ex.getMessage());
        }

        demonstrateMultipleCallers(executor);
    }

    private static void demonstrateMultipleCallers(TaskExecutor executor)
            throws InterruptedException {
        CountDownLatch bothEntered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maxActive = new AtomicInteger();

        Runnable job = () -> {
            int now = active.incrementAndGet();
            maxActive.accumulateAndGet(now, Math::max);
            bothEntered.countDown();

            try {
                release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            } finally {
                active.decrementAndGet();
            }
        };

        Thread callerA = new Thread(() -> executor.execute(job), "caller-A");
        Thread callerB = new Thread(() -> executor.execute(job), "caller-B");

        callerA.start();
        callerB.start();

        // Cả hai đã vào task, cùng chờ release; phải có 2 task active.
        bothEntered.await();
        release.countDown();
        callerA.join();
        callerB.join();

        System.out.println("6 max-active: " + maxActive.get());
    }
}
~~~

### 3.4. Lệnh chạy và stdout

Tại thư mục `sync-executor-demo`, có JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.executor.SyncTaskExecutorDemo
~~~

Các dòng **do chương trình in**, theo đúng thứ tự:

~~~text
1 before: request-caller
2 task: request-caller
3 trace: REQ-42
4 after: request-caller
5 caught: boom
6 max-active: 2
~~~

Vì `execute` chạy task trực tiếp, dòng 4 không thể xuất hiện trước dòng 2 hoặc 3 khi task thành công. `REQUEST_ID` dùng `ThreadLocal` nên task thấy cùng giá trị `REQ-42` trên caller thread. Phần cuối dùng hai `CountDownLatch` để chắc chắn task A và task B đều đã vào `run()` trước khi giải phóng; `max-active: 2` chứng minh cùng một executor có thể có **hai task đang chạy** khi hai caller thread khác nhau đồng thời gọi nó. Giá trị này được đo bằng `AtomicInteger`; ví dụ cố ý dùng cơ chế đồng bộ của JDK để tránh test phụ thuộc vào thời điểm ngẫu nhiên.

Tín hiệu `ThreadLocal.remove()` trong `finally` là cần thiết nếu sau đó luồng gọi còn được tái sử dụng, chẳng hạn luồng servlet container. Mã ở trên là một file Java độc lập trong Maven project vừa chỉ ra; không dựa vào file bên ngoài.

## 4. Dùng SyncTaskExecutor trong Spring bean và @Async

Trong ứng dụng Spring, có thể đăng ký executor này thành bean và inject qua kiểu chung `TaskExecutor`. Chỉ chọn `@Async("syncExecutor")` khi **muốn chủ đích biến lời gọi qua proxy thành xử lý đồng bộ** (thường để test). Chữ `@Async` trên phương thức **không thể bắt buộc tạo thread mới** nếu executor được chọn chính là `SyncTaskExecutor`.

Để kiểm tra cả wiring và cơ chế Spring AOP proxy, thêm file thứ hai vào cùng project Maven ở mục 3:

`src/main/java/com/example/executor/AsyncSyncExecutorDemo.java`

~~~java
package com.example.executor;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncSyncExecutorDemo {
    @Bean("syncExecutor")
    public TaskExecutor syncExecutor() {
        return new SyncTaskExecutor();
    }

    @Bean
    public ReportTask reportTask() {
        return new ReportTask();
    }

    public static void main(String[] args) {
        Thread.currentThread().setName("request-caller");

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncSyncExecutorDemo.class)) {
            // Lấy bean do Spring quản lý: lời gọi đi qua @Async proxy.
            ReportTask worker = context.getBean(ReportTask.class);

            System.out.println("A before");
            worker.generate();
            System.out.println("C after");
        }
    }

    public static class ReportTask {
        @Async("syncExecutor")
        public void generate() {
            System.out.println("B task: " + Thread.currentThread().getName());
        }
    }
}
~~~

Chạy:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.executor.AsyncSyncExecutorDemo
~~~

Các dòng do chương trình in (ngoài log framework nếu có):

~~~text
A before
B task: request-caller
C after
~~~

`@EnableAsync` bật hỗ trợ proxy cho `@Async`; `@Async("syncExecutor")` chọn đúng executor qua tên bean. Vì executor chạy đồng bộ, `worker.generate()` chỉ trả về sau khi nội dung phương thức hoàn tất. Ở ví dụ này `ReportTask` là public nested class không final, phương thức public; Spring có thể tạo proxy cho bean. Nếu gọi `this.generate()` từ chính `ReportTask`, lời gọi nội bộ thường bỏ qua proxy của `@Async` ở proxy mode; khi đó phương thức cũng chạy trực tiếp nhưng **vì bỏ qua interceptor**, không phải vì executor đã được áp dụng. Phân biệt hai nguyên nhân để chẩn đoán đúng.

### Tại sao không suy diễn toàn bộ hành vi của @Async từ execute?

- Với lời gọi **trực tiếp** `syncExecutor.execute(runnable)`, unchecked exception từ `Runnable.run()` thường truyền trực tiếp ra caller (như ví dụ 3).
- Khi qua **proxy `@Async`**, Spring gói tác vụ và xử lý kết quả/ngoại lệ theo kiểu trả về. Với `void`, lỗi chưa bắt được chuyển tới cơ chế `AsyncUncaughtExceptionHandler`; với `Future/CompletableFuture`, caller có thể quan sát lỗi qua kết quả tương lai (chẳng hạn `get()/join()`). Đừng hứa rằng mọi exception của phương thức `@Async` sẽ ném ra giống `execute` trực tiếp.
- Khi task chạy đồng bộ, một `CompletableFuture` được hoàn tất ngay trong lời gọi gửi task có thể đã hoàn thành lúc phương thức gọi trả về. API có tên “async” và kiểu `Future` **không bảo đảm** thao tác thực sự chạy nền.
- `@Async` có hỗ trợ return type hạn chế và quy tắc proxy của Spring; những chi tiết đó không thay đổi bản chất synchronous của `SyncTaskExecutor`.

Ví dụ với Java `CompletableFuture` (đoạn minh họa trong phương thức, giả sử `executor` là `TaskExecutor` ở mục 3):

~~~java
CompletableFuture<Void> future = CompletableFuture.runAsync(
        () -> System.out.println("runs inline"), executor);
System.out.println(future.isDone()); // true khi task thành công và đã chạy xong
~~~

`CompletableFuture.runAsync` nhận một `Executor` nhưng nó gọi `executor.execute`; với `SyncTaskExecutor` task được thực thi ngay, nên `future` đã hoàn tất khi `runAsync` trả về. Nếu task lỗi, `CompletableFuture` lưu lỗi để quan sát bằng `join/get`; đó là hành vi của wrapper `CompletableFuture`, không mâu thuẫn với cơ chế `execute` trực tiếp.

## 5. Ảnh hưởng trong HTTP request, transaction và thread context

Giả sử controller gọi:

~~~java
// Đoạn minh họa trong một @RestController; không phải class đầy đủ.
@GetMapping("/reports/{id}/refresh")
public String refresh(@PathVariable String id) {
    syncExecutor.execute(() -> reportService.refresh(id));
    return "Accepted";
}
~~~

Nếu `reportService.refresh(id)` gọi DB 5 giây, request HTTP phải đợi khoảng 5 giây mới trả chữ “Accepted”. Dùng chữ “Accepted” trong body **không** biến tác vụ thành xử lý background; status HTTP `202 Accepted` cũng không phù hợp nếu nhiệm vụ thực tế đã được xử lý xong ngay trong lời gọi mà không có ý định tiếp nhận tiếp. Với thao tác đồng bộ, API nên trả mã HTTP/kết quả phản ánh kết quả đã xử lý; với tác vụ nền thật sự dài, dùng executor bất đồng bộ có giới hạn hoặc message queue, kèm mã job để tra trạng thái.

### Ngữ cảnh nào còn trên luồng?

Khi dùng `SyncTaskExecutor` trực tiếp:

- `ThreadLocal` do chính caller thiết lập vẫn hiện diện trong task, bao gồm nhiều cấu hình logging MDC, security context hoặc context khác thường đặt trên luồng.
- `TransactionSynchronizationManager` ghi nhận transaction association trên luồng hiện tại. Vì task chạy cùng luồng, nếu transaction đã hoạt động thì truy cập tài nguyên theo transaction-bound context có thể tham gia chính transaction ấy, tùy các phương thức service và quy tắc propagation.
- `RequestContextHolder` thường có request attributes trong quá trình một HTTP request đồng bộ; task trực tiếp có thể nhìn thấy chúng khi context đang hoạt động. Điều này **không** có nghĩa có thể giữ và dùng request context sau khi request hoàn tất.
- Nếu task thay đổi MDC, security context, `ThreadLocal` hoặc context classloader mà không restore, caller có thể quan sát thay đổi đó ngay sau `execute`. Cần dọn hoặc khôi phục trong `finally` theo ownership.

Không suy ra rằng `SyncTaskExecutor` *tự tạo transaction*, tự propagate sang thread khác, hay thay thế `@Transactional`. Nếu code gọi qua Spring proxy của một service `@Transactional` thì các quy tắc transaction bình thường vẫn áp dụng; nếu self-invocation bypass proxy, annotation có thể không được xử lý.

### Vì sao điều này quan trọng khi thay executor?

Một thay đổi cấu hình từ `SyncTaskExecutor` sang `ThreadPoolTaskExecutor` có thể làm lộ ra giả định sai:

1. Caller trở về trước khi task xử lý xong; dữ liệu được đọc ngay sau `execute` có thể chưa sẵn sàng.
2. Task chạy trên luồng worker, nên `ThreadLocal` và transaction association của caller **không tự động** đi theo. Hãy truyền dữ liệu cần thiết như request ID, user ID đã xác thực hoặc immutable DTO; dùng cơ chế context propagation phù hợp nếu thật sự cần.
3. Exception của worker không thể mặc nhiên được bắt bằng `try/catch` quanh lời gọi gửi task; cần Future, error handler, callback hoặc trạng thái công việc.
4. Mutable collection chỉ an toàn vì task chạy inline trước đây có thể phát sinh race nếu caller tiếp tục sửa trong khi worker đọc. Truyền snapshot bất biến hoặc có đồng bộ đúng.

Ngược lại, khi test dùng `SyncTaskExecutor`, việc code chạy cùng thread có thể che giấu lỗi race/visibility và lỗi thiếu context propagation sẽ xuất hiện trên production executor. Cần thêm test chạy bằng executor thực tế khi những tính chất ấy là yêu cầu hệ thống.

## 6. So sánh khi chọn bộ thực thi

| Lựa chọn | Chạy ở đâu? | Lời gọi `execute` chờ task? | Điểm mạnh / khi dùng |
| --- | --- | --- | --- |
| `SyncTaskExecutor` | Trên caller thread | **Có**, đến khi task hoàn tất | Unit/integration test đồng bộ, luồng xử lý đơn giản |
| `SimpleAsyncTaskExecutor` | Mặc định tạo thread cho mỗi task; không tái sử dụng kiểu pool | Thường trả về sau khi giao task; có thể chờ vì cấu hình giới hạn | Tác vụ độc lập ngắn/đặc thù; phải hiểu chi phí tạo thread và giới hạn |
| `ThreadPoolTaskExecutor` | Các worker trong pool, có thể có queue | Thường trả về sau khi giao; có thể từ chối khi đầy | Tải nền có kiểm soát, tách khỏi request; cấu hình pool/queue/rejection |
| `ThreadPoolTaskScheduler` | Bộ thực thi kiêm lập lịch định kỳ | Được gọi theo lịch thay vì caller trực tiếp | `@Scheduled` và trigger cố định/cron |
| `ThreadPoolExecutor.CallerRunsPolicy` (JDK) | Chỉ có thể chạy trên caller khi pool từ chối task | Chỉ trong tình huống fallback tương ứng | Backpressure khi queue bão hòa; **khác** executor luôn đồng bộ |

`TaskExecutor` là interface, không cam kết thread mới. `SyncTaskExecutor` **không** giống “single-thread executor”: single-thread executor thường có **một worker thread riêng** và xếp các task vào hàng; `SyncTaskExecutor` dùng **bất cứ caller thread nào** đang gọi `execute`.

Đặc biệt khi triển khai 2 request đồng thời:

~~~text
Request A (thread-A) ---> sync.execute(taskA) ---> taskA.run() trên thread-A
Request B (thread-B) ---> sync.execute(taskB) ---> taskB.run() trên thread-B

Hai task có thể thực thi chồng thời gian.
Không có shared worker hay mutex chung ở SyncTaskExecutor.
~~~

Nếu mục tiêu là chỉ cho một task tại một thời điểm trong toàn JVM, cần một executor một worker thực sự hoặc một khóa phù hợp. Nếu mục tiêu là một task tại một thời điểm **trên nhiều pod**, phải dùng cơ chế coordination/lock ở kho chung, không dùng `SyncTaskExecutor`.

### Chọn executor cho tác vụ báo cáo lâu

Đối với request tạo báo cáo có bước đọc DB và render PDF chậm, `SyncTaskExecutor` khiến request giữ luồng HTTP. Chọn executor thực sự bất đồng bộ có giới hạn sẽ hợp lý hơn, ví dụ bean minh họa trong ứng dụng Spring:

~~~java
// Đoạn minh họa bên trong class @Configuration.
@Bean("reportExecutor")
public ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(20);
    pool.setThreadNamePrefix("report-");
    pool.setWaitForTasksToCompleteOnShutdown(true);
    return pool;
}
~~~

Trong mã trên, cần import `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` và `org.springframework.context.annotation.Bean`. Spring quản lý vòng đời bean khi đăng ký trong context; nếu khởi tạo `new ThreadPoolTaskExecutor()` thủ công ngoài Spring thì phải gọi `initialize()` trước khi dùng và đóng tài nguyên đúng cách. Khi queue/pool đã đầy, chọn chính sách rejection và cách HTTP phản hồi phù hợp thay vì tiếp nhận vô hạn. Việc đưa task sang pool không tự khiến công việc bền vững qua restart; báo cáo quan trọng nên có job state trong DB/queue bền vững.

## 7. Khi nào nên và không nên dùng SyncTaskExecutor?

**Nên cân nhắc khi:**

1. **Test cần tính quyết định:** đưa `TaskExecutor` vào constructor và inject `SyncTaskExecutor` trong unit test để assertion chạy sau `execute` và thấy kết quả ngay, không phải chờ/lặp poll. Với test concurrency thật, phải thay bằng pool thích hợp.
2. **Thao tác nhỏ, chủ đích chạy đồng bộ:** khi abstraction `TaskExecutor` được dùng chung nhưng một nhánh cần hành vi đồng bộ, không yêu cầu tách request khỏi task.
3. **Gỡ lỗi ứng dụng:** đổi sang executor đồng bộ tại môi trường thử nghiệm giúp call stack liền mạch. Phải ghi nhận rằng timing và race trong production có thể khác.

**Không phù hợp khi:**

- Tạo PDF, gửi email, gọi API chậm hoặc xử lý hàng nghìn bản ghi mà endpoint cần trả lời ngay.
- Muốn khống chế tổng số task đồng thời bằng chính executor trong phiên bản 6.x: số task active có thể bằng số caller đang gọi.
- Muốn thực thi tuần tự toàn JVM, chạy theo lịch, retry qua restart, hay phân tán tải nhiều node.
- Muốn kiểm chứng lỗi đồng bộ dữ liệu giữa worker threads mà test lại chạy tất cả inline.

### Cách dùng trong test

Giả sử service nhận abstraction qua constructor:

~~~java
// Đoạn minh họa, class còn cần import TaskExecutor.
public final class RefreshCoordinator {
    private final TaskExecutor executor;
    private boolean finished;

    public RefreshCoordinator(TaskExecutor executor) {
        this.executor = executor;
    }

    public void refresh() {
        executor.execute(() -> finished = true);
    }

    public boolean isFinished() {
        return finished;
    }
}
~~~

Trong test chạy tuần tự cùng thread:

~~~java
RefreshCoordinator coordinator =
        new RefreshCoordinator(new SyncTaskExecutor());
coordinator.refresh();
assert coordinator.isFinished();
~~~

Đây là *đoạn minh họa trong test*, không phải hai file Java độc lập. Nếu chạy với assertion Java, cần bật `-ea`; trong JUnit, nên dùng `assertTrue(...)`. Thuộc tính `finished` không được đồng bộ cho production async executor; chính vì test dùng sync executor nên có thể bỏ sót vấn đề visibility. Để production hỗ trợ async, hãy dùng `CompletableFuture`, `CountDownLatch` hoặc biến trạng thái thread-safe phù hợp với thiết kế thay vì dựa vào field boolean thông thường.

## 8. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng / nhận định | Nguyên nhân đúng | Kiểm tra hoặc xử lý |
| --- | --- | --- |
| “`@Async` vẫn chạy trên HTTP thread” | Bean được chọn là `SyncTaskExecutor`; hoặc self-invocation bypass proxy | In thread name, kiểm tra tên executor trong `@Async` và đường gọi qua proxy |
| “`execute` trả về chậm” | Task chạy inline, caller chờ task | Đo thời gian ngay trước/sau; chuyển sang pool nếu cần nền thật |
| “Có `SyncTaskExecutor` thì chắc không có race” | Nhiều caller threads vẫn chạy task song song | Dùng latch trong test, khóa/atomic/transaction cho shared state |
| “Bắt lỗi quanh `execute` không thấy lỗi `@Async`” | Proxy / `Future` có cách xử lý lỗi riêng | Kiểm tra return type, `AsyncUncaughtExceptionHandler`, `Future.get/join` |
| “Transaction/request context trong test có nhưng production không” | Test dùng same thread, production dùng worker thread | Truyền dữ liệu rõ ràng, mở transaction trong worker khi cần |
| “Single-thread executor và SyncTaskExecutor giống nhau” | Single-thread executor có worker và queue; Sync dùng caller | Xem thread name và thứ tự trước/sau lời gọi |
| “Test qua với sync executor nên production ổn” | Test không mô phỏng lịch đồng thời, queue, shutdown, rejection | Bổ sung integration/load test trên cấu hình production |

### Checklist trước khi chọn

- API có cần trả ngay sau khi *gửi* việc không? Nếu có, `SyncTaskExecutor` không đáp ứng mục tiêu xử lý nền.
- Công việc có thể tốn bao lâu? Từng task có giữ luồng request hoặc event-loop không? Trên event-loop/reactive stack, tuyệt đối tránh chạy blocking work bằng executor đồng bộ rồi kỳ vọng không block event-loop.
- Task có dùng transaction, MDC, SecurityContext hoặc request data gắn với thread không? Nếu chuyển sang worker, quản lý propagation và ownership.
- Có yêu cầu giới hạn số task đồng thời, hàng đợi, timeout, cancellation, graceful shutdown hoặc khôi phục sau restart không? Nếu có, một executor inline đơn giản là chưa đủ.
- Test đang cố xác minh logic tuần tự hay behavior concurrency thật? Chọn executor đúng cho mục đích kiểm thử.

## 9. Câu hỏi tự kiểm tra

1. Nếu `execute` được gọi trên `http-nio-8080-exec-2`, `Thread.currentThread().getName()` bên trong `Runnable` là gì? Dòng lệnh phía sau `execute` chạy khi nào?
2. Hai HTTP threads cùng gọi một `SyncTaskExecutor` có chạy được hai task đồng thời không? Vì sao tên “sync” không có nghĩa là serial trên toàn hệ thống?
3. Trong direct `execute`, `IllegalStateException` của `Runnable` đi tới đâu? Điều này khác thế nào khi phương thức chạy qua `@Async` proxy hoặc khi dùng `CompletableFuture`?
4. Vì sao `ThreadLocal` có thể nhìn thấy trong task, và vì sao vẫn cần dọn `ThreadLocal` trong `finally`?
5. Nếu test inject `SyncTaskExecutor` còn production inject `ThreadPoolTaskExecutor`, giả định nào về kết quả, transaction, chia sẻ biến hoặc lỗi có thể cần thiết kế lại?
6. Khi endpoint phải nhận yêu cầu render báo cáo rồi trả 202 ngay, bạn chọn executor và cơ chế lưu trạng thái nào?

**Ghi nhớ:** `SyncTaskExecutor` cho abstraction `TaskExecutor` nhưng thực chất chạy `Runnable.run()` **ngay trên caller thread**. Nó hữu ích cho xử lý có chủ đích đồng bộ và test quyết định, đồng thời có thể làm caller bị chặn; nó không phải thread pool, queue hay cơ chế đồng bộ toàn ứng dụng.

Tài liệu chính thức: [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) và [Spring Framework 6.2 — SyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/SyncTaskExecutor.html).