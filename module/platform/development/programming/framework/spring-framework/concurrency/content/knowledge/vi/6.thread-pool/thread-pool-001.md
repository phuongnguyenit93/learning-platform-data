# Khai báo ThreadPoolTaskExecutor thành bean do container quản lý

> **Chủ đề:** Spring Framework – Concurrency / Nhóm luồng.  
> **Mục tiêu chính:** tạo một `ThreadPoolTaskExecutor` dưới dạng Spring bean, cấu hình rõ kích thước pool và hàng đợi, inject đúng bean vào nơi sử dụng, đồng thời giao cho **Spring container quản lý khởi tạo và hủy tài nguyên**. Một executor chạy đúng nghiệp vụ còn phải có chính sách xử lý quá tải, shutdown và quan sát trạng thái phù hợp.

## 1. Kết quả học tập

Sau khi hoàn thành, bạn có thể:

1. Nêu được sự khác nhau giữa `new ThreadPoolTaskExecutor()` như đối tượng Java thông thường và đối tượng được khai báo bằng `@Bean`/đăng ký trong `ApplicationContext`.
2. Viết cấu hình Java dùng `@Configuration` và `@Bean("...")` cho `ThreadPoolTaskExecutor`, không tự gọi `initialize()` hoặc `shutdown()` khi container sở hữu bean.
3. Hiểu tác động của `corePoolSize`, `maxPoolSize`, `queueCapacity`, `keepAliveSeconds`, `threadNamePrefix` và `RejectedExecutionHandler`.
4. Sử dụng constructor injection và `@Qualifier` khi có nhiều executor; chỉ định executor bằng `@Async("beanName")` khi cần.
5. Chạy ví dụ Spring Context + Java 17 có kiểm tra thread thực thi, bean identity và shutdown bằng tín hiệu đồng bộ, thay vì `Thread.sleep()`.
6. Thiết kế hành vi khi quá tải và dừng ứng dụng có chủ đích; tránh rò rỉ thread, mất task và vô tình gây chậm request.

## 2. ThreadPoolTaskExecutor là gì?

`org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` là lớp Spring bọc `java.util.concurrent.ThreadPoolExecutor` và cung cấp giao diện `TaskExecutor`/`AsyncTaskExecutor`. Nó cho phép cấu hình các thuộc tính quen thuộc của thread pool bằng setter kiểu JavaBean, ví dụ:

- Số luồng cơ bản và tối đa.
- Sức chứa hàng đợi.
- Thời gian giữ luồng nhàn rỗi.
- Tiền tố tên thread.
- Cách xử lý khi executor không thể tiếp nhận task.
- Cách phản ứng khi Spring context đóng.

Ứng dụng gửi tác vụ qua `execute(Runnable)` hoặc một API trả `Future` phù hợp; Spring executor dùng worker/queue để chạy tác vụ theo cấu hình. Lời gọi `execute` **không phải** một yêu cầu tạo thread mới cho mỗi task.

### Khi nào nên dùng?

Dùng `ThreadPoolTaskExecutor` khi cần giới hạn và quản lý việc thực thi tác vụ trong **một JVM**, chẳng hạn xử lý ảnh, gửi email, tính toán báo cáo hoặc tác vụ tích hợp có thể thực hiện bất đồng bộ. Để bảo đảm tác vụ sống sót sau crash/restart, cần thêm cơ chế lưu bền như message queue/job store; thread pool nằm trong bộ nhớ không đảm nhiệm chức năng đó.

### Một bean được container quản lý có ý nghĩa gì?

Sơ đồ vòng đời cơ bản:

~~~text
@Configuration / @Bean
        |
        v
Spring tạo đối tượng ThreadPoolTaskExecutor
        |
        v
Áp dụng cấu hình (core/max/queue/name/policy...)
        |
        v
Spring gọi afterPropertiesSet() -> initialize()
        |
        v
Executor sẵn sàng nhận task qua DI / @Async
        |
        v
ApplicationContext bắt đầu đóng
        |
        v
Spring điều phối lifecycle và gọi destroy() -> shutdown()
~~~

`ThreadPoolTaskExecutor` kế thừa `ExecutorConfigurationSupport`, thực thi `InitializingBean`, `DisposableBean` và các giao thức lifecycle của Spring. Khi là bean do container sở hữu, việc gọi `afterPropertiesSet()` để tạo underlying `ExecutorService` diễn ra trong khâu khởi tạo bean; khi bean bị hủy, container gọi callback hủy tương ứng. Với ứng dụng chạy thực tế, cần đóng `ApplicationContext` một cách có trật tự để các callback này xảy ra.

**Điểm then chốt:** trong factory method `@Bean`, bạn **khởi tạo đối tượng và đặt thuộc tính rồi `return`**. Đừng gọi `executor.initialize()` ngay trong `@Bean`, vì container sẽ tự thực hiện bước này trong vòng đời bean; gọi thủ công có thể gây khởi tạo trùng và khiến việc quản lý executor khó kiểm soát. Cũng không tự gọi `shutdown()` từ service đang sử dụng bean chung.

## 3. Mẫu cấu hình @Bean đúng và ngắn gọn

Trong dự án có `spring-context` hoặc Spring Boot starter phù hợp:

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class WorkerPoolConfig {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("report-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(15);
        return executor;
    }
}
~~~

Đây là **class cấu hình Spring**, chưa phải ứng dụng độc lập. Khi container quét hoặc import cấu hình `WorkerPoolConfig`:

1. Bean có tên chính xác là `reportExecutor` và kiểu cụ thể là `ThreadPoolTaskExecutor`.
2. Spring khởi tạo pool ở giai đoạn initialize của bean; tác vụ không cần tự gọi `initialize()`.
3. Các thành phần khác có thể inject theo tên/kiểu để dùng cùng instance bean singleton mặc định.
4. Khi context đóng, Spring điều phối shutdown. Với cấu hình chờ hoàn tất task, pool xử lý các công việc được chấp nhận trước khi đóng theo những ràng buộc timeout được chỉ định.

`@Configuration(proxyBeanMethods = false)` là cách hợp lệ cho phương pháp cấu hình qua tham số DI. Nếu có một `@Bean` cần dùng bean khác, hãy nhận nó qua **tham số phương thức**, thay vì tự gọi một factory method trong cùng configuration rồi giả định luôn nhận bean đã quản lý.

### Chú giải từng thuộc tính

| Cấu hình | Ý nghĩa | Nhận xét thực hành |
| --- | --- | --- |
| `setCorePoolSize(2)` | Số worker cơ bản mà pool hướng tới khi có tải | Không có nghĩa phải tạo sẵn 2 thread ngay tại startup |
| `setMaxPoolSize(4)` | Trần worker của pool | Chỉ có thể tăng vượt core khi chính sách queue cho phép, thường sau khi queue đầy |
| `setQueueCapacity(16)` | Số task chờ tối đa khi worker đang bận | Bounded queue tránh hàng đợi tăng vô hạn, nhưng sẽ có thời điểm bị từ chối |
| `setKeepAliveSeconds(30)` | Thời gian giữ worker thừa so với core khi nhàn rỗi | Không mặc nhiên cho core thread hết hạn; xem `setAllowCoreThreadTimeOut(...)` |
| `setThreadNamePrefix(...)` | Đặt tiền tố tên worker | Giúp debug thread dump/log, không tạo cơ chế cách ly hay đồng bộ |
| `setRejectedExecutionHandler(...)` | Quyết định ứng xử khi pool không thể nhận task | `AbortPolicy` ném lỗi; `CallerRunsPolicy` có thể chạy task trên caller |
| `setWaitForTasksToCompleteOnShutdown(true)` | Khi shutdown, ưu tiên hoàn thành task đang chạy và đang chờ thay vì ngắt/loại bỏ theo đường mặc định | Có thể kéo dài thời gian dừng, cần giới hạn và điều phối tài nguyên phụ thuộc |
| `setAwaitTerminationSeconds(15)` | Cho container chờ tối đa 15 giây ở bước chờ kết thúc executor | Timeout **không bảo đảm** tất cả tác vụ chắc chắn hoàn tất sau 15 giây |

Đây là **giá trị ví dụ**, không phải bộ thông số đúng cho mọi hệ thống. Chọn dựa trên workload CPU/I/O, giới hạn kết nối, memory, tốc độ nộp/tiêu thụ task, mục tiêu latency và cách xử lý khi hết tài nguyên.

### Các giá trị mặc định cần tránh hiểu sai

Theo Javadoc Spring 6.2, `ThreadPoolTaskExecutor` mặc định có `corePoolSize = 1`, `maxPoolSize` rất lớn và `queueCapacity` rất lớn. Vì queue có thể luôn nhận thêm việc, cấu hình này về thực tế thường hành xử gần như một worker với hàng đợi dài, dù `maxPoolSize` nhìn có vẻ vô hạn. **Không nên coi default là pool tự động tăng thread theo số request.**

- `queueCapacity > 0`: Spring thường dùng một `LinkedBlockingQueue` có capacity được cấu hình.
- `queueCapacity = 0`: dùng cơ chế chuyển giao trực tiếp kiểu `SynchronousQueue`; pool có thể mở thêm worker đến `maxPoolSize` nếu cần.
- Queue lớn: giảm từ chối trong các burst nhỏ nhưng tăng chờ đợi và rủi ro giữ nhiều task/payload trong RAM.
- Queue rất nhỏ: phản ứng nhanh hơn với quá tải nhưng cần thiết kế rejection/backpressure rõ ràng.

## 4. Ví dụ Java 17+ chạy được với Spring Context

Ví dụ này minh họa **đầy đủ vòng đời bean**, từ lúc tạo `ApplicationContext`, inject `TaskExecutor` vào service, chạy một task trên worker khác, đến khi context đóng. Nó không yêu cầu Spring Boot hoặc HTTP server.

### 4.1. Cấu trúc dự án

~~~text
managed-pool-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ManagedPoolDemo.java
~~~

Tệp **`pom.xml`** (Java 17, Spring Framework 6.2.16):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>managed-pool-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
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

Tệp **`src/main/java/demo/ManagedPoolDemo.java`**:

~~~java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ManagedPoolDemo {

    @Configuration(proxyBeanMethods = false)
    static class PoolConfig {

        @Bean("reportExecutor")
        ThreadPoolTaskExecutor reportExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(4);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("report-");
            pool.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            pool.setWaitForTasksToCompleteOnShutdown(true);
            pool.setAwaitTerminationSeconds(5);
            return pool;  // Spring gọi initialize() và destroy().
        }

        @Bean
        ReportService reportService(
                @Qualifier("reportExecutor") TaskExecutor taskExecutor) {
            return new ReportService(taskExecutor);
        }
    }

    static final class ReportService {
        private final TaskExecutor executor;

        ReportService(TaskExecutor executor) {
            this.executor = executor;
        }

        void runOnce(AtomicReference<Thread> used,
                     CountDownLatch completed) {
            executor.execute(() -> {
                try {
                    used.set(Thread.currentThread());
                } finally {
                    completed.countDown();
                }
            });
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread caller = Thread.currentThread();
        ThreadPoolTaskExecutor pool;

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             PoolConfig.class)) {

            pool = context.getBean(
                    "reportExecutor", ThreadPoolTaskExecutor.class);
            ReportService service = context.getBean(ReportService.class);

            System.out.println("same bean = " +
                    (pool == context.getBean("reportExecutor")));

            AtomicReference<Thread> used = new AtomicReference<>();
            CountDownLatch completed = new CountDownLatch(1);
            service.runOnce(used, completed);

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task timed out");
            }

            System.out.println("different thread = " +
                    (used.get() != caller));
            System.out.println("worker named = " +
                    used.get().getName().startsWith("report-"));
        } // context.close() gọi lifecycle shutdown của bean.

        System.out.println("pool shutdown = " +
                pool.getThreadPoolExecutor().isShutdown());
    }
}
~~~

### 4.2. Biên dịch và chạy

Trong thư mục chứa `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ManagedPoolDemo
~~~

**Stdout của chương trình** trong trường hợp chạy thành công (bỏ qua thông báo riêng của công cụ Maven nếu có):

~~~text
same bean = true
different thread = true
worker named = true
pool shutdown = true
~~~

Giải thích từng kết quả:

- Hai lần `getBean("reportExecutor")` trả lại cùng instance vì bean `@Bean` mặc định là singleton trong context.
- Task được nộp vào pool đang hoạt động, có worker với prefix `report-` nên phép so sánh với caller là `true` ở dòng `different thread`. Ở ví dụ tải nhẹ này, `AbortPolicy` không có lý do từ chối task.
- `CountDownLatch` bảo đảm task đã ghi `AtomicReference<Thread>` trước khi luồng main đọc; không dùng `sleep()`.
- `try-with-resources` đóng `AnnotationConfigApplicationContext` ngay sau khối `try`. `ThreadPoolTaskExecutor` đã được khởi tạo và được Spring hủy theo lifecycle, nên `isShutdown()` trả về `true`.

**Tại sao ví dụ không gọi `pool.initialize()` và `pool.shutdown()`?** Vì vòng đời thuộc container. Tự gọi `initialize()` trong `@Bean` không cần thiết; tự `shutdown()` trong service có thể làm những consumer khác của bean chung đột ngột nhận `TaskRejectedException`.

### Nếu không chạy trong Spring context

Đây là tình huống **khác**:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.initialize();
try {
    executor.execute(() -> System.out.println("work"));
} finally {
    executor.shutdown();
}
~~~

Đoạn này là **minh họa thủ công**, giả định code chạy trong một phương thức; bản thân nó không có `main`. Khi chính bạn tạo đối tượng ngoài bean factory, **bạn** phải khởi tạo, shutdown và chờ kết thúc nếu cần. Điều đó giải thích giá trị của việc biến executor thành Spring bean: container tập trung quản lý vòng đời, DI và cấu hình, giảm rủi ro quên dọn tài nguyên.

## 5. Inject và sử dụng đúng bean

### Constructor injection cùng @Qualifier

Khi hệ thống có nhiều executor, inject trực tiếp bean có tên xác định:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class InvoiceExportService {
    private final TaskExecutor reportExecutor;

    public InvoiceExportService(
            @Qualifier("reportExecutor") TaskExecutor reportExecutor) {
        this.reportExecutor = reportExecutor;
    }

    public void enqueue(long invoiceId) {
        reportExecutor.execute(() -> export(invoiceId));
    }

    private void export(long invoiceId) {
        // Thực hiện nghiệp vụ export; xử lý retry/lỗi tại tầng phù hợp.
    }
}
~~~

Đây là **service snippet cho dự án Spring đã quét component**, không phải tệp Java SE độc lập. Tên `@Qualifier("reportExecutor")` phải khớp bean name hoặc qualifier có hiệu lực. Nếu chỉ có một bean kiểu `TaskExecutor`, có thể inject theo type; khi nhiều bean cùng kiểu, chỉ rõ qualifier hoặc thiết kế primary bean để tránh lựa chọn mơ hồ.

### Vì sao chọn TaskExecutor ở service?

Service phần lớn chỉ cần phương thức `execute(...)`, nên có thể phụ thuộc `TaskExecutor` thay vì lớp cụ thể. Cấu hình Spring giữ thông tin pool size, queue và shutdown; business logic chỉ biết đang giao task cho executor đã cấp. Nếu service cần API `submit(...)`, dùng interface thích hợp như `AsyncTaskExecutor` hoặc phụ thuộc cụ thể có chủ đích.

### Tương tác với @Async

`@Async` là cơ chế annotation dựa trên proxy/interceptor của Spring. Nếu muốn một phương thức được điều phối qua bean cụ thể, bật `@EnableAsync` trong cấu hình và chỉ định tên:

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.stereotype.Service;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncFeatureConfig {
}

@Service
class InvoicePreviewService {
    @Async("reportExecutor")
    public CompletableFuture<String> generatePreview(long id) {
        String result = "preview-" + id;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Đây là **hai lớp minh họa trong ứng dụng Spring**; nếu đặt chung một file cần tuân thủ quy tắc tên/public class của Java. Phương thức `@Async("reportExecutor")` dùng bean có tên `reportExecutor` khi được gọi **qua Spring proxy**. Với cách dùng mặc định (proxy mode), `this.generatePreview(...)` từ chính class không được interceptor bắt, nên có thể chạy như lời gọi Java bình thường.

`@Async` không tự bảo đảm persistence hoặc transaction giữa các thread; khác luồng thì transaction context/`ThreadLocal` của caller không mặc nhiên được chuyển sang. Nếu cần kiểm soát lỗi, phương thức trả `CompletableFuture`/`Future` cho phép phía nhận theo dõi thất bại tốt hơn `void`.

## 6. Bên trong thread pool: core, queue, max và rejection

`ThreadPoolTaskExecutor` dùng các quy tắc quản lý pool của `ThreadPoolExecutor`. Với `corePoolSize = 2`, `maxPoolSize = 4` và `queueCapacity = 3`, hình dung một tình huống các task chạy đủ lâu để tiếp tục chiếm worker:

| Số task được nhận liên tiếp khi tất cả đang bận | Hành vi lý tưởng hóa |
| --- | --- |
| Task 1–2 | Dùng đến 2 core worker |
| Task 3–5 | Có thể chờ trong 3 vị trí queue |
| Task 6–7 | Pool có thể tạo thêm worker đến tối đa 4 |
| Task 8 | Worker và queue đều đầy: kích hoạt rejection policy |

Bảng là **mô phỏng khi task không kịp kết thúc trong lúc nộp**, không phải dự báo lịch thực thi cố định. Nếu một worker hoàn thành sớm, task mới có thể được tiếp nhận khác đi.

- `AbortPolicy` (mặc định của underlying executor): từ chối khi không thể tiếp nhận, thường biểu hiện thành `TaskRejectedException` qua Spring `TaskExecutor`.
- `CallerRunsPolicy`: nếu pool chưa shutdown, task bị từ chối bởi pool sẽ chạy trực tiếp trên **thread gọi `execute`**. Đây là backpressure nhưng có thể làm request chậm bất ngờ.
- `DiscardPolicy` hoặc `DiscardOldestPolicy`: có nguy cơ mất task, không nên dùng cho nghiệp vụ bắt buộc xử lý nếu chưa có cơ chế bù/giám sát.
- Khi pool đang đóng hoặc đã đóng, submission có thể bị từ chối; với `CallerRunsPolicy`, JDK không luôn chạy task đã bị từ chối khi executor đã shutdown.

**Đừng đồng nhất “được giao cho pool” với “chắc chắn chạy trên thread khác”** nếu đã bật `CallerRunsPolicy`. Đừng khẳng định “chắc chắn thực hiện” chỉ vì `execute` không ném exception khi handler có thể loại task.

### Ví dụ xử lý từ chối

~~~java
import org.springframework.core.task.TaskRejectedException;

public void submitJob(Runnable job) {
    try {
        reportExecutor.execute(job);
    } catch (TaskRejectedException ex) {
        // Chuyển sang hàng đợi bền vững, retry có giới hạn
        // hoặc báo quá tải cho client tùy nghiệp vụ.
        throw ex;
    }
}
~~~

Đây là **mẫu phương thức minh họa**, giả định `reportExecutor` đã được inject. Tránh retry vô hạn ngay trên request thread vì nó có thể làm tăng tải đúng lúc pool đã quá tải. Với các job quan trọng, thiết kế thông điệp idempotent, retry và lưu trạng thái ở nơi bền vững thay vì chỉ dựa vào queue trong RAM.

## 7. Vòng đời bean và đóng ứng dụng một cách an toàn

### 7.1. Khởi tạo tự động

`ThreadPoolTaskExecutor` kế thừa cơ chế `InitializingBean.afterPropertiesSet()`, dẫn tới `initialize()`. Spring gọi callback này sau khi áp dụng các thuộc tính bean, tạo underlying pool cho việc gửi task.

Vì vậy, trong `@Bean`:

~~~java
@Bean("imageExecutor")
ThreadPoolTaskExecutor imageExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(3);
    executor.setMaxPoolSize(6);
    executor.setQueueCapacity(50);
    return executor; // Chưa tự initialize() tại đây.
}
~~~

Nếu cần dùng pool trong component khác, hãy inject bean đó. **Đừng** viết `new ThreadPoolTaskExecutor()` trong mỗi request hoặc trong mỗi service chỉ để “dùng luôn”; điều này tạo ra nhiều pool không có vòng đời thống nhất, tốn thread và dễ bị quên shutdown.

### 7.2. Shutdown tự động

`ThreadPoolTaskExecutor` triển khai `DisposableBean.destroy()`, kế thừa từ `ExecutorConfigurationSupport`. Khi context đóng đúng cách, Spring gọi callback hủy để shutdown underlying executor. Đây là lý do không cần thêm `@PreDestroy` chỉ để gọi `shutdown()` cho cùng bean.

Tuy nhiên, **container quản lý shutdown không đồng nghĩa mọi task đã hoàn tất**. Cần phân biệt:

- Dừng tiếp nhận task mới.
- Cách xử lý task đang chạy.
- Cách xử lý task đang nằm trong queue.
- Có chờ task kết thúc hay không; chờ tối đa bao lâu.
- Các bean khác (database client, HTTP client...) còn sống đủ lâu để task đang chạy dùng chúng hay không.

### 7.3. Hai thuộc tính shutdown quan trọng

Với Spring Framework 6.2:

`setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor khi shutdown để task đã nhận được hoàn thành mà không chủ động interrupt chúng theo đường shutdown bình thường, kể cả các task còn trong queue. Điều này có thể kéo dài thời gian dừng nếu có backlog hoặc task bị treo.

`setAwaitTerminationSeconds(15)` yêu cầu phần shutdown chờ tối đa 15 giây cho executor kết thúc trước khi Spring tiếp tục hủy các bean còn lại. Nó **không hủy tự động** mọi task khi hết 15 giây theo cách biến công việc thành chắc chắn hoàn thành; nếu timeout, hệ thống vẫn có thể còn task hoặc cần shutdown orchestration ở tầng ứng dụng.

Kết hợp hai thuộc tính cần dựa trên thời gian chạy job thực tế. Nếu job có thể mất vài phút, giá trị 15 giây chỉ là chính sách chờ ngắn, không phải cam kết job kết thúc trước khi database pool đóng.

### 7.4. Lưu ý riêng về thay đổi lifecycle ở Spring 6.1/6.2

Các phiên bản Spring mới phối hợp shutdown của executor với `ContextClosedEvent` và `SmartLifecycle`. Thuộc tính như `acceptTasksAfterContextClose` và, trên `ThreadPoolTaskExecutor`, `strictEarlyShutdown` ảnh hưởng thời điểm từ chối task mới trong quá trình đóng context.

Đừng học thuộc một quy tắc “cứ context.close là mọi task lập tức dừng”. Hãy đọc Javadoc theo **phiên bản đang chạy** và kiểm thử đúng thứ tự shutdown của ứng dụng. Không bắt đầu tác vụ nền mới trong callback hủy rồi giả định pool còn nhận việc, trừ khi thiết kế lifecycle đã chủ động cho phép và được kiểm chứng.

### 7.5. Có nên tự thêm destroyMethod="shutdown"?

Đối với `ThreadPoolTaskExecutor` được Spring quản lý, **không cần**, vì lớp đã có callback hủy chuẩn. Ví dụ cấu hình thông thường chỉ dùng `@Bean("...")` và trả executor. Việc gọi `shutdown()` ở nhiều nơi có thể làm công việc còn lại bị từ chối; càng không nên để một consumer của pool có quyền tự đóng pool chia sẻ.

Nếu muốn loại bỏ trách nhiệm shutdown của container cho một bean đặc biệt, đó là quyết định thiết kế khác và phải tự chịu trách nhiệm lifecycle; không áp dụng cho mẫu bean quản lý thông thường của bài này.

## 8. Đặt tên và phân chia executor theo loại công việc

Một ứng dụng có thể có nhiều pool:

~~~java
@Configuration(proxyBeanMethods = false)
class MultiplePoolsConfig {

    @Bean("cpuExecutor")
    ThreadPoolTaskExecutor cpuExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("cpu-");
        return pool;
    }

    @Bean("ioExecutor")
    ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(8);
        pool.setMaxPoolSize(16);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("io-");
        return pool;
    }
}
~~~

**Đoạn cấu hình minh họa**, không phải cặp giá trị tuning mặc định. Số thread CPU-bound thường cần gắn với số CPU khả dụng; tác vụ I/O chờ lâu có thể cần mức concurrency khác nhưng phải tính thêm giới hạn kết nối DB/HTTP, memory và tốc độ nhận task. Nếu không cần cách ly tải, một pool đủ rõ ràng đôi khi đơn giản hơn nhiều pool.

Khi inject:

~~~java
public SomeService(
        @Qualifier("cpuExecutor") TaskExecutor cpuExecutor,
        @Qualifier("ioExecutor") TaskExecutor ioExecutor) {
    this.cpuExecutor = cpuExecutor;
    this.ioExecutor = ioExecutor;
}
~~~

Đây chỉ là **constructor snippet**: trong class thật cần khai báo hai field `TaskExecutor` tương ứng. Các tên bean riêng và `@Qualifier` giúp tránh trường hợp khi thêm executor thứ hai thì injection theo type đột ngột trở nên mơ hồ.

## 9. Cấu hình trong Spring Boot: chú ý bean mặc định

Spring Boot có tự động cấu hình executor theo phiên bản và các bean hiện diện. Ví dụ trong **Spring Boot 3.5**, khi chưa có custom `Executor`, Boot có thể tự tạo `AsyncTaskExecutor` cho các tích hợp khác nhau, thường là `ThreadPoolTaskExecutor` khi dùng platform threads.

**Khi tự khai báo một bean `Executor`**, auto-configuration có thể lùi lại và những tính năng như `@Async`, Spring MVC async handling hoặc WebFlux có thể chọn executor khác theo **tên bean và type**. Các quy tắc này phụ thuộc phiên bản Boot:

- `@Async("reportExecutor")`: chọn rõ bean `reportExecutor` cho riêng phương thức đó.
- Với một số tích hợp async web, tên `applicationTaskExecutor` và khả năng implement `AsyncTaskExecutor` có ý nghĩa đặc biệt.
- Với cấu hình `@EnableAsync`, Spring Framework có cơ chế chọn executor mặc định và có thể dùng `AsyncConfigurer`; đừng suy rằng bean nào có tên bất kỳ sẽ tự động được mọi tác vụ dùng.
- Cần phân biệt executor dùng cho `@Async` với scheduler cho `@Scheduled`. Một `ThreadPoolTaskExecutor` không tự biến thành `TaskScheduler`.

**Nguyên tắc thực hành:** nếu dự án đang dùng Spring Boot, đọc đúng mục “Task Execution and Scheduling” của **phiên bản Boot đang triển khai**, kiểm tra danh sách bean thực tế và chủ động đặt tên/qualifier. Không tự nhân đôi pool chỉ để có thêm một executor mà không kiểm soát ảnh hưởng auto-configuration.

## 10. TaskDecorator, context và lỗi trong worker

`ThreadPoolTaskExecutor#setTaskDecorator(...)` cho phép bọc tác vụ trước khi thực thi, hữu ích cho logging/tracing hoặc truyền một phần context được kiểm soát.

Ví dụ **minh họa**, đặt trong factory method trước `return executor`:

~~~java
executor.setTaskDecorator(original -> () -> {
    long started = System.nanoTime();
    try {
        original.run();
    } finally {
        long elapsedNanos = System.nanoTime() - started;
        System.out.println("Task runtime nanos = " + elapsedNanos);
    }
});
~~~

TaskDecorator được sử dụng cho `Runnable` đã được executor chuẩn bị; với những đường `submit(...)` có wrapper `FutureTask`, xử lý exception trong decorator có thể không hoạt động theo cách mong đợi. Muốn nhận exception của task, dùng `Future.get()`/`CompletableFuture`, exception handler phù hợp hoặc hook theo executor cụ thể.

**Không mặc định sao chép toàn bộ `ThreadLocal` từ request sang worker.** Transaction của Spring thông thường gắn với thread; ngữ cảnh bảo mật, MDC tracing và các giá trị request có thể cần cơ chế propagation riêng. Nếu tự capture/set context trong decorator, phải restore/clear trong `finally` để worker tái sử dụng không mang dữ liệu task trước sang task sau.

Đặc biệt, việc dùng `CallerRunsPolicy` có thể làm task chạy trong caller trong một số lần, thay đổi latency và context quan sát được. Chọn rejection handler phù hợp với yêu cầu vận hành và security của ứng dụng.

## 11. Giám sát và xác minh bean đang hoạt động

Để xem pool thật trong runtime, có thể lấy bean từ context:

~~~java
ThreadPoolTaskExecutor pool =
        context.getBean("reportExecutor", ThreadPoolTaskExecutor.class);

int currentPoolSize = pool.getPoolSize();
int activeThreads = pool.getActiveCount();
int queuedTasks = pool.getThreadPoolExecutor().getQueue().size();
~~~

Đây là **snippet bên trong code có `context` đã khởi tạo**. Các số là trạng thái tại thời điểm quan sát, thay đổi khi các task bắt đầu/kết thúc; không phải dữ liệu giao dịch nhất quán. Có thể đưa chúng vào Micrometer/Actuator hoặc hệ thống monitoring phù hợp, nhưng đừng phát log liên tục từng task ở mức gây tải lớn.

### Các chỉ số nên theo dõi

| Chỉ số | Điều cần quan sát |
| --- | --- |
| Active threads | Có liên tục sát max hay không |
| Queue depth | Hàng đợi tăng không ngừng, backlog mất bao lâu mới xử lý hết |
| Rejected submissions | Lần từ chối tăng đột biến và ảnh hưởng người gọi |
| Task duration / error rate | Tác vụ chậm do ngoại vi hay do CPU, lỗi có được báo đúng kênh |
| Caller latency | Có sự tăng mạnh do `CallerRunsPolicy` hay chờ submit không |
| Shutdown duration | Container có dừng trước khi task quan trọng kết thúc không |

Không thể suy ra throughput hoặc latency tốt chỉ từ số `corePoolSize`; cần kiểm tra thực tế với workload có cùng đặc điểm tài nguyên của production.

### Kiểm thử lifecycle có ý nghĩa

1. Bắt đầu context và lấy `reportExecutor`; bảo đảm nhận đúng bean name/type.
2. Submit một tác vụ và dùng `CountDownLatch` hoặc `Future` để đợi hoàn thành, không dùng `Thread.sleep`.
3. So sánh `Thread.currentThread()` với caller nếu yêu cầu off-thread là phần contract của cấu hình.
4. Đóng context; kiểm tra underlying `ThreadPoolExecutor.isShutdown()` và, nếu cần, `awaitTermination(...)`.
5. Với bài test quá tải, chủ động giữ worker bằng latch, lấp queue rồi gửi thêm task để kiểm tra policy. Không dựa vào may rủi scheduler.
6. Kiểm tra exception, cancellation, thời gian đóng và resource cleanup theo nhu cầu nghiệp vụ.

Một test pass ở tải nhẹ **không chứng minh** pool không bao giờ bị từ chối task hoặc luôn chạy ngoài caller khi đã cấu hình `CallerRunsPolicy`.

## 12. Những lỗi phổ biến khi khai báo bean

**Lỗi 1: tạo pool bằng `new` trong mỗi lời gọi request.**  
Hậu quả: thread tăng không kiểm soát, khó quản lý shutdown. Khắc phục: tạo một bean singleton dùng chung cho workload cụ thể và inject vào service.

**Lỗi 2: tự gọi `initialize()` bên trong phương thức `@Bean`.**  
Hậu quả: container cũng thực hiện callback khởi tạo. Khắc phục: cấu hình thuộc tính rồi `return`, để Spring điều khiển lifecycle.

**Lỗi 3: quên xác định khi nào pool dừng.**  
Hậu quả: khi tạo pool thủ công, không shutdown có thể giữ thread/process sống; nếu là bean, cần cho context đóng đúng cách. Khắc phục: container quản lý bean và thiết kế timeout shutdown phù hợp.

**Lỗi 4: nghĩ `maxPoolSize=100` đồng nghĩa có thể chạy 100 task ngay.**  
Hậu quả: với queue quá lớn, pool thường nhận task vào queue trước khi tăng vượt core. Khắc phục: hiểu thuật toán ưu tiên worker/queue và đặt queue capacity có chủ đích.

**Lỗi 5: để queue vô hạn vì muốn “không bao giờ lỗi”.**  
Hậu quả: độ trễ tăng, giữ nhiều payload trong RAM, nguy cơ cạn bộ nhớ. Khắc phục: giới hạn hợp lý, điều khiển tốc độ nộp task và xử lý rejection.

**Lỗi 6: cấu hình `CallerRunsPolicy` mà giả định task luôn background.**  
Hậu quả: request thread có thể tự làm task và chậm bất ngờ; context execution thay đổi. Khắc phục: chọn handler đúng mục tiêu, quan sát saturation.

**Lỗi 7: chỉ inject theo type khi có nhiều executor.**  
Hậu quả: ambiguity hoặc dùng nhầm pool. Khắc phục: đặt tên bean có ý nghĩa và `@Qualifier` hoặc `@Async("...")`.

**Lỗi 8: chỉ khai báo bean rồi nghĩ `@Async` tự bật.**  
Hậu quả: annotation có thể không được xử lý nếu không cấu hình `@EnableAsync`/cơ chế tương đương, hoặc self-invocation không đi qua proxy. Khắc phục: bật async support và gọi qua Spring proxy.

**Lỗi 9: nghĩ `@Bean` giúp các mutable field trong service thread-safe.**  
Hậu quả: mất cập nhật hoặc đọc dữ liệu sai khi nhiều task dùng cùng singleton. Khắc phục: thiết kế immutable state hoặc đồng bộ phù hợp; pool quản lý thread, không quản lý bất biến nghiệp vụ.

**Lỗi 10: tưởng shutdown thành công nghĩa là mọi công việc quan trọng đã được lưu bền.**  
Hậu quả: khi crash hoặc vượt timeout vẫn có thể mất task trong bộ nhớ. Khắc phục: dùng job store/message broker khi cần durability, retry và idempotency.

**Lỗi 11: bật `waitForTasksToCompleteOnShutdown` nhưng đặt timeout không đủ và bỏ qua phụ thuộc tài nguyên.**  
Hậu quả: task còn chạy trong khi các bean dùng bởi task đã đóng. Khắc phục: đánh giá worst-case duration, thử graceful shutdown thật và điều chỉnh thứ tự/timeout.

**Lỗi 12: thêm `@PreDestroy` trong consumer để tự đóng bean chung.**  
Hậu quả: consumer có thể khiến task của các consumer khác bị từ chối và việc hủy trở nên rối. Khắc phục: để bean executor sở hữu lifecycle qua container.

## 13. Bài tập áp dụng

### Bài 1 — Điền phần còn thiếu

Đoạn sau thiếu cấu hình cần để phân biệt pool dùng cho tác vụ xuất báo cáo:

~~~java
@Bean("reportExecutor")
ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(20);
    return pool;
}
~~~

**Đáp án gợi ý:** thêm `setThreadNamePrefix("report-")`; chọn `RejectedExecutionHandler` phù hợp. Với task phải hoàn thành lúc shutdown, xem xét `setWaitForTasksToCompleteOnShutdown(...)` và `setAwaitTerminationSeconds(...)`. Không cần gọi `initialize()` trong factory method.

### Bài 2 — Vì sao chỉ chạy hai worker?

Một pool có `corePoolSize=2`, `maxPoolSize=20`, `queueCapacity=Integer.MAX_VALUE`. Khi hàng trăm task ngắn được submit liên tiếp, tại sao chỉ có vài worker bận?

**Đáp án:** sau core worker, pool ưu tiên đưa task vào queue; queue rất lớn gần như không bao giờ đầy nên ít có cơ hội tạo worker vượt core. Muốn tăng concurrency theo tải, phải cân nhắc capacity/pool sizing, không chỉ tăng `maxPoolSize`.

### Bài 3 — Bean nào được @Async sử dụng?

Ứng dụng có `reportExecutor` và `notificationExecutor`. Phương thức khai báo `@Async("notificationExecutor")`.

**Đáp án:** Spring chọn bean theo qualifier/tên `notificationExecutor` khi async interception hoạt động. Nếu gọi trực tiếp từ `this` trong proxy mode, không thể kết luận lời gọi sẽ được dispatch qua executor.

### Bài 4 — Shutdown có chắc hoàn tất toàn bộ queue?

Một executor có 1.000 task đang chờ, `setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(5)`. Có thể cam kết toàn bộ task xong trước 5 giây không?

**Đáp án:** không. Cấu hình chờ tối đa 5 giây không biến workload dài thành tác vụ ngắn hoặc bảo đảm kết thúc hết queue trước deadline. Cần kiểm soát khối lượng, timeout và định nghĩa rõ xử lý job còn dở.

### Bài 5 — Phân tích đoạn code sai

~~~java
@Service
class WrongReportService {
    void start() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.execute(() -> System.out.println("report"));
    }
}
~~~

**Đáp án:** pool được tạo thủ công chưa gọi `initialize()` nên chưa có underlying executor; lời gọi `execute` không có pool đã khởi tạo và có thể thất bại. Nếu tự sửa bằng initialize nhưng quên shutdown, lại thêm rủi ro rò rỉ thread. Cách đúng với ứng dụng Spring: khai báo `@Bean` và constructor-inject pool có quản lý vòng đời.

## 14. Checklist để review một ThreadPoolTaskExecutor bean

- [ ] Executor được tạo một lần ở `@Bean`/cơ chế đăng ký bean phù hợp, và được Spring context quản lý.
- [ ] Đã đặt `@Bean` name rõ ràng, service dùng constructor injection và `@Qualifier` nếu có nhiều pool.
- [ ] Không tự gọi `initialize()` trong factory method và không tự shutdown pool ở consumer.
- [ ] Đã chọn `corePoolSize`/`maxPoolSize`/`queueCapacity` theo workload, có giới hạn memory và phản ứng với quá tải.
- [ ] Biết rõ `RejectedExecutionHandler` và đường error/backup queue khi không nhận task.
- [ ] Thread name prefix giúp quan sát, không lấy tên thread làm bằng chứng duy nhất cho correctness.
- [ ] Với `@Async`: đã bật `@EnableAsync`, gọi qua proxy và chỉ rõ executor khi cần.
- [ ] Đã thiết kế graceful shutdown, timeout chờ, thứ tự đóng tài nguyên và xử lý task dang dở.
- [ ] Đã đo queue depth, active threads, rejection và latency; kiểm thử được hành vi khi bão hòa.
- [ ] Nếu yêu cầu không mất task sau crash, đã dùng thành phần lưu trữ bền vững ngoài executor.

## 15. Tóm tắt kiến thức cốt lõi

**Công thức thực hành:** `@Configuration` + `@Bean("tênExecutor")` + `new ThreadPoolTaskExecutor()` + các setter cần thiết + `return executor`. Spring quản lý initialize/destroy; service nhận bean qua dependency injection.

Kích thước pool, queue và rejection là **một bộ chính sách**, không phải ba con số độc lập. Để an toàn trong production, cần xét cả cách đóng context, kết quả task, giao dịch/tài nguyên phụ thuộc và các cơ chế lưu bền cần thiết. Khi dùng `@Async`, hãy xác định chính xác executor được chọn và đảm bảo lời gọi đi qua proxy.

## Tài liệu tham khảo chính thức

- Spring Framework Reference — Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework 6.2 — `ExecutorConfigurationSupport` Javadoc (initialize, destroy, shutdown, await): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/scheduling/concurrent/ExecutorConfigurationSupport.html
- Spring Boot 3.5 — Task Execution and Scheduling: https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html
- Java SE 17 — `ThreadPoolExecutor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- Spring Framework — Bean Definition and Lifecycle: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
