# execute(Runnable) không mặc nhiên bảo đảm chạy trên luồng khác

> **Chủ đề:** Spring Framework – Concurrency / TaskExecutor  
> **Ý chính:** `TaskExecutor.execute(Runnable)` là yêu cầu thực thi một tác vụ theo chiến lược của executor. Chỉ nhìn vào lời gọi `execute(...)` **không thể kết luận** tác vụ sẽ chạy trên một thread khác, không thể kết luận luôn trả về ngay và cũng không thể kết luận tác vụ đã chạy xong khi phương thức trả về.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc đúng hợp đồng của `java.util.concurrent.Executor` và `org.springframework.core.task.TaskExecutor`.
2. Giải thích vì sao `SyncTaskExecutor` thực thi ngay trong **luồng gọi**, trong khi `SimpleAsyncTaskExecutor` và `ThreadPoolTaskExecutor` thường giao việc cho luồng khác.
3. Chỉ ra tình huống `CallerRunsPolicy` khiến một thread pool chạy task ngay trên luồng gọi dù bình thường pool có worker.
4. Phân biệt **gửi tác vụ**, **bắt đầu tác vụ**, **hoàn thành tác vụ**, **chạy bất đồng bộ** và **chạy trên một luồng khác**.
5. Viết ví dụ Java 17 và kiểm thử đáng tin bằng định danh `Thread`, `CountDownLatch`, thay vì đoán qua log hoặc `Thread.sleep(...)`.
6. Chọn cấu hình executor, xử lý từ chối và quản lý ngữ cảnh luồng thích hợp trong ứng dụng Spring.

## 1. `execute(Runnable)` thật sự cam kết điều gì?

Trong Java, giao diện `Executor` có một phương thức cơ bản:

~~~java
public interface Executor {
    void execute(Runnable command);
}
~~~

Trong Spring, `TaskExecutor` kế thừa `Executor` và cũng cung cấp `execute(Runnable task)`. Hai giao diện tách **mã tạo công việc** khỏi **cách chạy công việc**. Người gọi đưa một `Runnable` cho executor; chính implementation và cấu hình của executor quyết định nó chạy ở đâu và khi nào.

Bởi vậy:

- `execute` **không đồng nghĩa** `new Thread(task).start()`.
- Một implementation có thể gọi thẳng `task.run()` trong cùng call stack, vì vậy tác vụ hoàn thành **trước khi `execute` trả về**.
- Một implementation khác có thể đưa `task` vào hàng đợi để worker chạy sau; task cũng có thể bắt đầu **trước khi `execute` trả về**.
- Có implementation dùng thread mới, dùng worker có sẵn, hoặc ủy quyền cho executor khác. Không phải mọi `TaskExecutor` đều là thread pool.
- Task có thể bị từ chối khi không còn khả năng nhận việc hoặc đã shutdown. Tùy chính sách từ chối, lời gọi có thể ném lỗi, tự chạy trong caller hoặc bỏ tác vụ. Vì vậy, chỉ thấy `execute` trả về không đồng nghĩa tác vụ chắc chắn đã hoàn thành.

Spring Javadoc của `TaskExecutor` ghi rõ các chiến lược thực thi có thể **synchronous** hoặc **asynchronous**. `execute` trả về kiểu `void`: nó không cung cấp kết quả hay handle chờ hoàn thành. Nếu cần phản hồi kết quả/thất bại, hãy chọn API trả `Future`/`CompletableFuture` và quản lý hợp đồng executor tương ứng.

### Đừng đồng nhất ba câu hỏi

| Câu hỏi | Ý nghĩa | Có suy ra chỉ từ `execute(Runnable)` không? |
| --- | --- | --- |
| Tác vụ chạy trên **cùng thread** hay **thread khác**? | Thread identity | **Không** |
| Lời gọi `execute` có **trả về nhanh** không? | Độ trễ của caller | **Không** |
| Khi `execute` trả về, task có **hoàn thành** không? | Trạng thái hoàn thành | **Không** |

Ví dụ, `SyncTaskExecutor` làm cả ba điều theo cách dễ đoán: **cùng thread**, caller bị chặn trong khi chạy task, và task đã kết thúc trước khi `execute` trả về thành công. Một executor có hàng đợi có thể giao việc cho worker nhưng vẫn chặn caller lúc chờ tài nguyên. Việc “không chặn” và việc “không chạy cùng thread” là hai tính chất cần xét riêng.

## 2. Hình dung đường đi của lời gọi

### Trường hợp A: thực thi đồng bộ ngay tại caller

~~~text
Thread request/main
    |
    | gọi executor.execute(task)
    |       |
    |       +-- task.run()
    |       |     làm việc / có thể ném exception
    |       +-- run() kết thúc
    |
    +-- execute() trả về
    +-- câu lệnh tiếp theo
~~~

Đây là `SyncTaskExecutor`: nó gọi `Runnable.run()` trực tiếp. Trong trường hợp này không xuất hiện một thread thực thi task mới chỉ vì ta dùng API executor.

### Trường hợp B: chuyển việc sang worker

~~~text
Thread request/main                 Thread worker
    |                                     |
    +-- execute(task)                     |
    |      +-- nhận/đưa vào queue --------+-- lấy task
    +-- có thể tiếp tục                    +-- task.run()
    |                                     +-- hoàn thành
~~~

Đây là chiến lược thông thường của `ThreadPoolTaskExecutor` khi pool chấp nhận tác vụ. Thời điểm worker bắt đầu, thời điểm caller quay về và thời điểm task hoàn thành **không có thứ tự tổng quát cố định** nếu không có một cơ chế chờ/đồng bộ rõ ràng.

### Trường hợp C: pool đầy và chính sách chuyển sang caller

~~~text
Thread request/main                 Thread pool
    |                                     |
    +-- execute(task)                     +-- mọi worker bận
    |      +-- queue đầy                   +-- queue đầy
    |      +-- CallerRunsPolicy
    |             +-- task.run()
    |             +-- hoàn thành
    +-- execute() trả về
~~~

Trong cấu hình này, một executor bình thường chạy async có thể thực thi **task bị từ chối bởi pool ngay trên luồng gọi**. Đó là điểm cần kiểm tra kỹ khi chọn chính sách chống quá tải.

## 3. Ví dụ Java SE 17 độc lập: cùng API, hai cách chạy

Đoạn này chỉ dùng Java SE để chứng minh hợp đồng `Executor` cho phép nhiều chiến lược. Tạo tệp **`ExecutorDispatchDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorDispatchDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();

        // Hợp lệ: implementation chạy trực tiếp trong thread gọi.
        Executor direct = Runnable::run;

        System.out.println("before direct");
        direct.execute(() -> System.out.println(
                "direct same thread = " + (Thread.currentThread() == caller)));
        System.out.println("after direct");

        // ExecutorService này tạo một worker riêng để xử lý task.
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch completed = new CountDownLatch(1);

        try {
            pool.execute(() -> {
                try {
                    System.out.println(
                            "pool same thread = " + (Thread.currentThread() == caller));
                } finally {
                    completed.countDown();
                }
            });

            completed.await(); // Chờ task in xong, không dựa vào sleep.
            System.out.println("after pool completed");
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac ExecutorDispatchDemo.java
java ExecutorDispatchDemo
~~~

**Stdout xác định:**

~~~text
before direct
direct same thread = true
after direct
pool same thread = false
after pool completed
~~~

Giải thích:

- `Runnable::run` là một implementation hợp lệ của `Executor`: truyền `Runnable` vào, nó gọi phương thức `run()` ngay trên caller.
- `Executors.newSingleThreadExecutor()` sử dụng một worker riêng; so sánh **đối tượng `Thread`** trả về `false`.
- `CountDownLatch.await()` giữ thứ tự dòng `after pool completed`; không suy luận thứ tự từ thời gian hệ điều hành xếp lịch.
- `shutdown()` giải phóng executor sau khi xử lý xong. Một chương trình dùng executor sống lâu cần quản lý vòng đời hoặc để Spring container quản lý bean.

Ví dụ này đã chứng minh điều cốt lõi ở mức JDK. Ta tiếp tục áp dụng trực tiếp vào `TaskExecutor` của Spring.

## 4. Ví dụ Spring: `SyncTaskExecutor` và `SimpleAsyncTaskExecutor`

### 4.1. Chuẩn bị dự án nhỏ có thể chạy

Dùng **JDK 17+** và **Maven**. Tạo cấu trúc:

~~~text
executor-spring-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── SpringTaskExecutorDemo.java
~~~

Nội dung **`pom.xml`** (dùng Spring Core 6.2.16 để ví dụ có phiên bản xác định):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>executor-spring-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.16</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung **`src/main/java/SpringTaskExecutorDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

import org.springframework.core.task.SimpleAsyncTaskExecutor;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;

public class SpringTaskExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();

        TaskExecutor sync = new SyncTaskExecutor();

        System.out.println("before sync");
        sync.execute(() -> System.out.println(
                "sync same thread = " + (Thread.currentThread() == caller)));
        System.out.println("after sync");

        TaskExecutor async = new SimpleAsyncTaskExecutor("demo-worker-");
        CountDownLatch finished = new CountDownLatch(1);

        async.execute(() -> {
            try {
                System.out.println(
                        "async same thread = " + (Thread.currentThread() == caller));
            } finally {
                finished.countDown();
            }
        });

        finished.await();
        System.out.println("after async completed");
    }
}
~~~

Chạy trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SpringTaskExecutorDemo
~~~

**Stdout từ chương trình** (các log Maven nếu có không thuộc stdout minh họa):

~~~text
before sync
sync same thread = true
after sync
async same thread = false
after async completed
~~~

### 4.2. Rút ra điều gì từ ví dụ?

- Cả hai biến có **cùng kiểu khai báo** `TaskExecutor`; sự khác biệt nằm ở implementation thực tế.
- `SyncTaskExecutor.execute` gọi trực tiếp `run()` nên thread thực thi là caller. Dòng `after sync` chỉ xuất hiện sau khi task hoàn thành.
- `SimpleAsyncTaskExecutor` khởi chạy luồng khác cho tác vụ, không phải pool tái sử dụng thread theo nghĩa `ThreadPoolTaskExecutor`. Ví dụ dùng latch để xác nhận task đã in trước khi chương trình kết thúc.
- Việc đặt tên thread `demo-worker-...` giúp quan sát khi debug nhưng không thay thế phép so sánh `Thread.currentThread() == caller`.
- `SimpleAsyncTaskExecutor` có thể áp dụng giới hạn đồng thời và chặn lúc nhận thêm việc. Đừng suy từ chữ `Async` rằng submission luôn tức thì hay tài nguyên vô hạn là an toàn.

### 4.3. Phân biệt `TaskExecutor` và `AsyncTaskExecutor`

Spring có subinterface `AsyncTaskExecutor` dành cho executor có hợp đồng thực thi bất đồng bộ và hỗ trợ các API tác vụ trả handle. Javadoc của subinterface này mô tả rằng `execute(Runnable)` được thực thi ở luồng khác, khác với hợp đồng tổng quát của `TaskExecutor`.

Khi sử dụng một executor cụ thể, vẫn phải xem **cấu hình xử lý từ chối và adapter**. Chẳng hạn, tùy chọn `CallerRunsPolicy` của thread pool cố ý chuyển việc về caller lúc pool bị bão hòa. Chính sách vận hành cụ thể có thể làm sai giả định “task này luôn off-thread”, kể cả với đối tượng có interface async. Nếu ứng dụng **bắt buộc** chạy ngoài caller, hãy chọn implementation/cấu hình giữ đúng yêu cầu ấy và xử lý từ chối minh bạch.

## 5. `ThreadPoolTaskExecutor`: bình thường giao cho worker nhưng phải xem chính sách quá tải

`ThreadPoolTaskExecutor` của Spring bọc cấu hình `ThreadPoolExecutor` của JDK. Nó thường nhận task vào worker/queue; task không đồng nghĩa với một thread mới. Worker có thể được dùng lại cho nhiều task, và các task có thể chờ queue.

Trong ứng dụng Spring có dependency `spring-context` (hoặc Spring Boot starter phù hợp), có thể định nghĩa bean cấu hình rõ ràng:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ExecutorConfiguration {
    @Bean("applicationExecutor")
    ThreadPoolTaskExecutor applicationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("application-job-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor; // Spring quản lý initialize và shutdown cho bean.
    }
}
~~~

**Đây là đoạn cấu hình của một ứng dụng Spring**, chưa phải chương trình chạy độc lập. Spring container sẽ khởi tạo bean trước khi nó được inject và sử dụng.

Với `AbortPolicy`, khi pool từ chối công việc, lệnh gọi sẽ ném exception thay vì lặng lẽ chuyển task sang caller. Trong Spring, việc từ chối qua `TaskExecutor` thường được biểu diễn bằng `TaskRejectedException` (thuộc họ `RejectedExecutionException`). Ứng dụng phải quyết định có retry, đưa sang queue bền vững, trả lỗi quá tải hoặc áp dụng cơ chế khác tùy nghiệp vụ.

### 5.1. Tại sao queue và kích thước pool ảnh hưởng tới hành vi?

Quy tắc điển hình của `ThreadPoolExecutor`:

1. Nếu số worker hiện có thấp hơn `corePoolSize`, có thể khởi tạo worker để xử lý task.
2. Khi đủ worker cơ bản, executor thường ưu tiên đưa công việc vào queue.
3. Khi queue không nhận thêm việc, executor có thể tăng worker tới `maxPoolSize`.
4. Khi cả worker và queue đã đạt giới hạn, **rejection policy** quyết định tác vụ tiếp theo.

Với queue không giới hạn thực tế, `maxPoolSize` có thể ít cơ hội phát huy tác dụng; vì thế phải xem đồng thời số worker, giới hạn queue và tốc độ xử lý, không chỉ nhìn tên bean.

### 5.2. `CallerRunsPolicy`: thread pool cũng có thể chạy task trong caller

Nếu cấu hình:

~~~java
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.CallerRunsPolicy());
~~~

thì khi pool bão hòa **và chưa shutdown**, task bị từ chối khỏi pool sẽ chạy trực tiếp trong thread đang gọi `execute`. Đây là hình thức **backpressure**: caller bị chiếm dụng để tự làm công việc, nên tốc độ nộp task giảm. Khi executor đã shutdown, `CallerRunsPolicy` có thể **bỏ** task thay vì chạy nó. Không được coi chính sách này là bảo đảm giao việc thành công trong mọi tình huống.

Hệ quả thực tế: một controller hoặc luồng xử lý request có thể mất nhiều thời gian hơn vì nó bất ngờ phải thực thi chính tác vụ nền, làm biến động latency. Đối với code dựa vào phân tách transaction, security context hoặc thread-local, việc chuyển task vào caller còn có thể thay đổi hành vi quan sát được.

### 5.3. Ví dụ Java 17 độc lập ép `CallerRunsPolicy` một cách xác định

Tệp **`CallerRunsDemo.java`** sau chủ động làm bận một worker, lấp đầy queue có dung lượng 1, rồi gửi task thứ ba. Vì mọi điều kiện đều được phối hợp bằng latch, **task thứ ba chắc chắn đi qua đường CallerRunsPolicy** nếu executor chưa shutdown.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class CallerRunsDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread caller = Thread.currentThread();
        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch releaseWorker = new CountDownLatch(1);

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.CallerRunsPolicy());

        try {
            pool.execute(() -> {
                workerStarted.countDown();
                try {
                    releaseWorker.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            workerStarted.await();     // Worker đang bận.
            pool.execute(() -> { });  // Một slot queue đã đầy.

            // Pool bão hòa: policy sẽ gọi run() trên chính caller.
            pool.execute(() -> System.out.println(
                    "third task same thread = " +
                    (Thread.currentThread() == caller)));
        } finally {
            releaseWorker.countDown();
            pool.shutdown();
        }

        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("pool did not terminate");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac CallerRunsDemo.java
java CallerRunsDemo
~~~

Kết quả chính xác:

~~~text
third task same thread = true
~~~

**Giải thích tại sao test đáng tin:** `workerStarted.await()` chắc chắn worker đang giữ task đầu và đợi `releaseWorker`; task thứ hai được đưa vào queue dung lượng 1; task thứ ba không có worker/queue trống. `CallerRunsPolicy` thực hiện chính task thứ ba trên caller. Không cần `Thread.sleep`, không phụ thuộc vào việc máy nhanh hay chậm.

**Lưu ý:** Ví dụ này kiểm tra cơ chế của `ThreadPoolExecutor` trong JDK. Với `ThreadPoolTaskExecutor`, kết quả tương tự áp dụng khi bean dùng cùng rejection policy và task thực sự đi đến trạng thái quá tải. Nếu chọn mặc định `AbortPolicy`, task thứ ba sẽ bị từ chối, **không được chạy trên caller**.

## 6. `execute()` trả về lúc nào và exception đi về đâu?

Không thể suy ra “đã hoàn tất” từ dấu `;` cuối câu lệnh `executor.execute(task);`.

| Cơ chế | Khi nào `execute` thường trả về? | Task ném `RuntimeException` sẽ xuất hiện ở đâu? |
| --- | --- | --- |
| `SyncTaskExecutor` | Sau khi `Runnable.run()` kết thúc | Propagate ngay trong lời gọi của caller |
| `SimpleAsyncTaskExecutor` | Sau khi giao/khởi chạy task, có thể chịu giới hạn đồng thời | Trong thread thực thi task; caller không tự nhận lại exception tác vụ |
| `ThreadPoolTaskExecutor` | Sau khi chấp nhận task, hoặc ném lỗi nếu từ chối | Ở worker khi task chạy; riêng lỗi submission có thể ném tại caller |
| Pool với `CallerRunsPolicy` khi bão hòa | Sau khi caller trực tiếp chạy xong task | Có thể propagate trong caller, theo handler và wrapper thực tế |

Các nhận định trên mô tả **đường xử lý thông thường**; adapter, decorator và policy cụ thể có thể bổ sung hành vi.

Ví dụ dễ mắc lỗi:

~~~java
try {
    taskExecutor.execute(() -> {
        throw new IllegalStateException("task failed");
    });
} catch (IllegalStateException e) {
    // Chỉ chắc chắn bắt được exception tác vụ nếu task chạy đồng bộ
    // và exception được truyền ra đúng lời gọi này.
}
~~~

Đây là **đoạn minh họa** dùng biến `taskExecutor` đã được inject. Với executor bất đồng bộ, catch bên ngoài thường không bắt được lỗi xảy ra sau đó trên worker. Nếu muốn caller có một điểm để chờ và lấy kết quả/thất bại, dùng API trả handle như `Future`, `CompletableFuture` hoặc thiết kế kênh kết quả/queue phù hợp.

Có thể sử dụng `CompletableFuture.runAsync(task, taskExecutor)` vì `TaskExecutor` cũng là `Executor`. Nhưng việc trả `CompletableFuture` **không tự đảm bảo** task chạy khác thread nếu executor được truyền vào là direct/sync. Future là cơ chế theo dõi hoàn thành và exception, không phải bản thân chính sách lựa chọn thread.

## 7. Hệ quả trong ứng dụng Spring

### 7.1. Controller gửi việc nền chưa chắc đã giao sang thread nền

Mẫu sau nhận một `TaskExecutor` qua dependency injection:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    private final TaskExecutor executor;

    public ExportService(
            @Qualifier("applicationExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void exportLater(long reportId) {
        executor.execute(() -> generateReport(reportId));
    }

    private void generateReport(long reportId) {
        // Gọi service hoặc thành phần nghiệp vụ tạo báo cáo.
    }
}
~~~

**Đây là đoạn tích hợp Spring, không phải chương trình Java SE độc lập.** Hành vi phụ thuộc bean thật sự mang tên `applicationExecutor`. Nếu cấu hình bean bằng `SyncTaskExecutor`, lời gọi `exportLater` **chạy tạo báo cáo trên thread hiện tại** rồi mới trả về. Nếu là thread pool bình thường, tác vụ có thể chạy ngoài caller. Nếu cấu hình `CallerRunsPolicy`, tác vụ đôi khi chạy trên caller khi bão hòa.

Vì vậy, tài liệu thiết kế nên ghi rõ **executor bean nào**, **loại implementation nào**, **pool/queue/rejection policy** và **tính chất off-thread có bắt buộc hay không**. Đừng khẳng định “đã chạy background” chỉ vì mã gọi `execute`.

### 7.2. `@Async` là một cơ chế khác, nhưng vẫn phải biết executor được chọn

Spring cung cấp `@Async` để thực thi phương thức qua cơ chế interceptor và executor được cấu hình:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    @Async("applicationExecutor")
    public void sendNotification(String recipient) {
        // Công việc gửi thông báo.
    }
}
~~~

Ứng dụng cần bật `@EnableAsync` hoặc cấu hình tương đương. Khi gọi qua proxy Spring, phương thức được điều phối qua executor được chỉ định. **Self-invocation** (gọi `this.sendNotification(...)` từ chính instance trong proxy mode thông thường) không đi qua proxy, nên không kích hoạt interception `@Async`. Không nhầm một lời gọi `@Async` có hiệu lực với việc gọi trực tiếp `taskExecutor.execute(...)`; chúng có cơ chế tích hợp khác nhau dù cùng dùng executor.

Ngữ nghĩa cuối cùng của việc chạy task còn phụ thuộc bean executor và policy. Với nghiệp vụ cần chạy ngoài luồng xử lý request trong mọi trường hợp được chấp nhận, phải xác minh cả async interception lẫn chiến lược executor.

### 7.3. Transaction, security context, MDC và `ThreadLocal`

Một thay đổi thread là thay đổi **execution context**, không chỉ thay đổi tên hiển thị:

- Với `SyncTaskExecutor`, task chạy trong caller, có thể nhìn thấy các `ThreadLocal` và transaction association gắn với caller tại thời điểm đó.
- Với worker ở luồng khác, transaction association, MDC tracing, request context và security context **không mặc nhiên được chép sang**. Phải dựa vào cơ chế propagation được framework hỗ trợ hoặc truyền dữ liệu tường minh.
- Dùng `TaskDecorator` cho metadata phù hợp và bảo đảm dọn trạng thái sau task nếu tự quản lý `ThreadLocal`; tránh giữ dữ liệu request qua các lần tái sử dụng worker.
- Với `@Transactional`, giao dịch của caller không tự “đi theo” tác vụ chạy ở thread khác. Nếu task cần transaction, hãy thiết kế biên giao dịch cho phần thực thi tương ứng.
- Khi task đôi khi chạy trên caller do `CallerRunsPolicy`, vấn đề không chỉ hiệu năng: giả định về context, logging, transaction và latency có thể khác lúc bình thường.

Vì thế, không nên dùng thread-local làm kênh truyền dữ liệu nghiệp vụ không được khai báo. Hãy truyền các giá trị cần thiết qua argument/message và áp dụng context propagation đúng nhu cầu.

### 7.4. TaskExecutor không tự làm trạng thái chia sẻ thành thread-safe

Task executor điều phối **việc chạy**, không tự khóa các mutable field của bean. Nếu nhiều worker tăng `counter++` trên một singleton `@Service`, vẫn có thể xảy ra lost update. Phải bảo vệ trạng thái bằng cấu trúc thích hợp (`AtomicInteger`, lock, immutable state, transaction ở tầng dữ liệu...) và tách biệt yêu cầu **thread-safety** khỏi yêu cầu **off-thread**.

Ngay cả khi `SyncTaskExecutor` chỉ chạy đồng bộ trong từng lời gọi, hai request khác nhau vẫn có thể gọi cùng singleton qua **hai caller thread khác nhau**. Do đó “executor sync” cũng **không bảo đảm** toàn bộ ứng dụng chỉ có một thread.

## 8. Kiểm thử đúng giả định chạy trên thread nào

Khi cần kiểm tra implementation/cấu hình, lưu tham chiếu đến thread caller rồi so sánh bên trong task, và dùng cơ chế chờ để không đọc kết quả sớm.

Mẫu **minh họa** cho một `TaskExecutor` đã inject:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.core.task.TaskExecutor;

public class ExecutorThreadProbe {
    public static boolean runsOnCaller(TaskExecutor executor)
            throws InterruptedException {
        Thread caller = Thread.currentThread();
        AtomicReference<Thread> actual = new AtomicReference<>();
        CountDownLatch finished = new CountDownLatch(1);

        executor.execute(() -> {
            try {
                actual.set(Thread.currentThread());
            } finally {
                finished.countDown();
            }
        });

        if (!finished.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("task did not finish in time");
        }

        return actual.get() == caller;
    }
}
~~~

Đoạn này là một **lớp hỗ trợ kiểm thử**, không có `main`. Sau khi đã cung cấp executor thật, giá trị trả về nói rằng **lần thực thi đó** có dùng caller hay không. Nó không chứng minh mọi lần chạy trong tương lai sẽ giống vậy, đặc biệt khi chính sách thay đổi theo tải.

Không nên dùng:

- `Thread.sleep(100)` rồi đoán task đã hoàn thành: scheduler và tải máy không cho thời hạn chắc chắn.
- Chỉ nhìn tên thread `pool-1-thread-1`: tên có thể tùy chỉnh; nên so sánh `Thread` hiện tại hoặc kiểm tra id khi cần.
- Chỉ xem thứ tự timestamp của hai dòng log: việc log bất đồng bộ, buffering hoặc độ phân giải timestamp có thể khiến suy luận sai.
- Viết test chỉ kiểm tra rằng `execute` không ném lỗi: test này không đo việc task đã hoàn thành hoặc đã được chạy trên thread khác.
- Ép test “luôn off-thread” trong khi cấu hình thực tế có `CallerRunsPolicy` mà không tạo tải: test có thể pass ở tải nhẹ và sai khi pool bão hòa.

**Đối với kiểm thử quy tắc tuyệt đối**, hãy kiểm tra cả đường bình thường, đường quá tải, shutdown và lỗi từ chối. Đối với kiểm thử chức năng, nên dùng latch/Future và kiểm tra kết quả nghiệp vụ thay vì dựa vào một lịch thực thi cụ thể.

## 9. Chọn cách thực thi theo yêu cầu thực tế

| Nhu cầu | Cách tiếp cận phù hợp | Phải xác minh thêm |
| --- | --- | --- |
| Muốn task chạy ngay, tuần tự trong caller (ví dụ unit test) | `SyncTaskExecutor` | Runtime exception có thể truyền thẳng cho caller |
| Muốn mỗi task chạy trên thread riêng, không cần pool | `SimpleAsyncTaskExecutor` | Giới hạn đồng thời, tài nguyên, vòng đời |
| Muốn xử lý nền bằng worker và queue có giới hạn | `ThreadPoolTaskExecutor` | Pool size, queue capacity, rejection policy, shutdown |
| Muốn giảm tải bằng cách bắt caller tự làm khi bão hòa | `CallerRunsPolicy` | Caller latency có thể tăng, task có thể chạy trên caller |
| Cần giữ off-thread ngay cả khi quá tải | Cấu hình executor chấp nhận hoặc **từ chối** minh bạch, thay vì caller-runs | Xử lý `TaskRejectedException`, retry/backpressure ở tầng phù hợp |
| Cần biết khi nào task xong hoặc nhận lỗi | `Future` / `CompletableFuture` / completion signal | Future không tự quy định thread thực thi |
| Cần xử lý bền vững sau khi request và process kết thúc | Queue/message broker hoặc cơ chế job bền vững | `TaskExecutor` nội bộ JVM không tự bảo đảm lưu trữ, retry, hay exactly-once |

Cần phân biệt **độ trễ request**, **điều kiện nhận task**, **hành vi khi bão hòa** và **yêu cầu tin cậy của công việc**. Một giải pháp đúng cho tác vụ phụ trợ có thể không phù hợp với tác vụ cần đảm bảo xử lý từng đơn hàng hoặc không mất thông báo.

## 10. Lỗi phổ biến và cách sửa

**Sai 1: “Gọi `execute` chắc chắn tạo thread mới.”**  
Sửa: đọc contract và xác định implementation. `SyncTaskExecutor` chạy ngay trong caller; `ThreadPoolTaskExecutor` thường tái sử dụng worker.

**Sai 2: “Có chữ `TaskExecutor` nên task luôn async.”**  
Sửa: `TaskExecutor` là giao diện tổng quát, chấp nhận cả sync và async; xem `AsyncTaskExecutor` và bean cấu hình nếu cần contract chuyên biệt.

**Sai 3: “Thread pool thì tuyệt đối không bao giờ dùng caller.”**  
Sửa: xem `RejectedExecutionHandler`; `CallerRunsPolicy` làm caller chạy task khi pool bão hòa.

**Sai 4: “`execute` trả về là task chạy xong.”**  
Sửa: chỉ đúng với executor đồng bộ hoặc khi có đồng bộ khác. Với async, dùng latch, Future hoặc callback để biết kết quả.

**Sai 5: “Trả về nhanh chứng tỏ task chạy thread khác.”**  
Sửa: một task cực ngắn chạy sync cũng có thể trả về nhanh; một async executor có thể chặn lúc chờ slot. Dùng thread identity/contract.

**Sai 6: “Task throw exception thì try/catch quanh `execute` luôn bắt được.”**  
Sửa: phân biệt lỗi submission với lỗi trong worker. Dùng result handle/log/exception handler tương ứng.

**Sai 7: “Một bean Spring inject là cấu hình được biết chắc.”**  
Sửa: dùng qualifier/tên bean rõ ràng, kiểm tra implementation, queue, pool và policy; môi trường test và production có thể cấu hình khác.

**Sai 8: “`@Async` là đủ, bất kể gọi từ đâu.”**  
Sửa: bảo đảm gọi qua Spring proxy, bật async support và kiểm tra executor, tránh tự gọi cùng instance trong proxy mode thông thường.

**Sai 9: “Task có ThreadLocal/transaction giống caller.”**  
Sửa: task chạy khác thread cần cơ chế truyền context phù hợp; caller-runs có thể khiến hành vi khác giữa tải nhẹ và tải nặng.

**Sai 10: “Một task chạy đúng thread trong một lần test chứng minh hệ thống luôn thế.”**  
Sửa: kiểm tra cả đường từ chối/quá tải/shutdown và áp dụng bất biến thiết kế, không chỉ dựa vào log một lần chạy.

## 11. Tình huống luyện tập

### Bài tập 1: đọc code và dự đoán output

~~~java
TaskExecutor executor = new SyncTaskExecutor();
System.out.println("A");
executor.execute(() -> System.out.println("B"));
System.out.println("C");
~~~

**Đáp án:** `A`, `B`, `C` theo thứ tự vì `SyncTaskExecutor` gọi `run()` trực tiếp. Đoạn code minh họa cần classpath Spring, imports và một phương thức chứa nó để chạy.

### Bài tập 2: thread pool có thể làm HTTP request bị chậm không?

Một controller gọi `execute(...)` tới pool với 2 worker, queue 10 và `CallerRunsPolicy`. Khi tải cao, vì sao latency request tăng đột ngột?

**Đáp án:** khi hai worker bận và queue đầy, handler chạy task trên chính request thread. Controller chỉ tiếp tục sau khi task hoàn thành; đây là backpressure nhưng có thể phá giả định tác vụ luôn chạy nền.

### Bài tập 3: phát biểu nào đúng?

1. Nếu `execute` trả về `void` thì task chạy đồng bộ.
2. `TaskExecutor` không loại trừ implementation đồng bộ.
3. `SimpleAsyncTaskExecutor` và `ThreadPoolTaskExecutor` đều bắt buộc tạo thread mới cho mỗi task.
4. `CallerRunsPolicy` có thể khiến task chạy trong caller khi pool quá tải.

**Đáp án:** (2) và (4). Kiểu trả về `void` không quy định thời điểm/chỗ chạy; thread pool thường tái sử dụng worker.

### Bài tập 4: làm thế nào chứng minh chắc chắn job đã hoàn thành?

Một test gọi `executor.execute(job)` rồi ngay lập tức `assertEquals(1, result.get())`. Test không ổn định với async executor.

**Đáp án:** nếu cần chờ job hoàn thành, truyền `CountDownLatch`/`Future` và chờ có timeout, sau đó mới assert. Không chèn `sleep`. Nếu còn yêu cầu “task không được chạy trên request thread”, kiểm tra/khống chế executor và policy riêng.

## 12. Checklist khi review code có `execute(Runnable)`

1. **Executor nào?** Bean name, concrete class và cấu hình ở runtime đã rõ chưa?
2. **Thread nào?** Có yêu cầu off-thread bắt buộc không? Hợp đồng có bảo đảm, hay đang suy từ tên method?
3. **Quá tải ra sao?** Queue, max threads, `CallerRunsPolicy`, `AbortPolicy` và shutdown đã được thiết kế chưa?
4. **Caller có thể chặn?** Cần xác định ảnh hưởng latency và thực thi trong request transaction.
5. **Biết task đã xong bằng gì?** Latch, Future, callback, trạng thái job hay thông điệp kết quả?
6. **Lỗi được xử lý ở đâu?** Lỗi nhận task khác với exception trong task.
7. **Context nào được truyền?** Transaction, security, MDC, request data và ThreadLocal.
8. **Trạng thái dùng chung đã an toàn?** Executor không bảo vệ hộ mutable fields của singleton.
9. **Test có kiểm soát được interleaving và tình huống overload không?** Tránh lệ thuộc `sleep` hoặc log order.

## 13. Ghi nhớ

- `execute(Runnable)` mô tả **nộp một tác vụ cho executor**; nó **không mặc nhiên yêu cầu chạy trên thread khác**.
- `SyncTaskExecutor` thực thi **đồng bộ trên caller**, còn `SimpleAsyncTaskExecutor`/`ThreadPoolTaskExecutor` được thiết kế cho công việc bất đồng bộ với đặc điểm quản lý thread khác nhau.
- Ngay cả thread pool, `CallerRunsPolicy` có thể chuyển task sang caller khi quá tải; chính sách từ chối cũng quyết định liệu task có được chấp nhận hay không.
- Đừng dùng tốc độ trả về, tên method, timestamp hay `Thread.sleep` để chứng minh thread identity hoặc completion. Hãy xem contract/config và dùng primitive đồng bộ đúng mục đích.
- Trong Spring, tác động thực tế còn liên quan request latency, `@Async` proxy, transaction, security/MDC context, exception handling và lifecycle của executor.

## Tài liệu tham khảo

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework Javadoc — `TaskExecutor` (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework Javadoc — `SyncTaskExecutor` (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/SyncTaskExecutor.html
- Spring Framework Javadoc — `AsyncTaskExecutor` (6.2.16): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html
- Java SE 17 — `Executor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 17 — `ThreadPoolExecutor` và rejection handlers: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Java SE 17 — `CountDownLatch`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html
