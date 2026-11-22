# Tiêm bộ thực thi qua interface để tách khỏi cách triển khai trong Spring

## 1. Vấn đề: nghiệp vụ cần gửi tác vụ, không cần quản lý thread pool

Giả sử ứng dụng cần ghi nhật ký nghiệp vụ, gửi thông báo hoặc tạo báo cáo sau khi nhận một yêu cầu. Thành phần nghiệp vụ cần phát lệnh **“hãy thực hiện công việc này”**. Nó không nhất thiết phải biết công việc chạy trên một thread mới, trên pool, trong thread hiện tại hay qua một executor do hạ tầng quản lý.

Nếu service tự tạo `new Thread(...)` hoặc `new ThreadPoolTaskExecutor()`, service bắt đầu chịu thêm trách nhiệm chọn số thread, cấu hình hàng đợi, khởi tạo, dừng executor và xử lý tài nguyên. Khi muốn đổi cách chạy trong môi trường production, integration test hay unit test, nhiều chỗ trong mã nghiệp vụ phải thay đổi.

**Dependency Injection (DI) qua interface** giúp thiết lập ranh giới rõ ràng:

- **Business service:** chỉ phụ thuộc vào hợp đồng `TaskExecutor` và gửi một `Runnable`.
- **Cấu hình Spring:** quyết định bean nào hiện thực hợp đồng: `ThreadPoolTaskExecutor`, `SyncTaskExecutor` hoặc một implementation thích hợp khác.
- **Spring container:** tạo, tiêm và quản lý vòng đời các bean liên quan.

Hướng phụ thuộc nên là:

```text
BusinessService  --depends on-->  TaskExecutor (interface)
                                    ^
                                    |
                       Spring injects a concrete bean
                         /                    \
            ThreadPoolTaskExecutor       SyncTaskExecutor
                 (pool)                     (same thread)
```

Điểm mấu chốt là **tách “công việc cần làm” khỏi “cách thực thi công việc”**. Thay đổi implementation ở lớp cấu hình không buộc sửa logic xử lý trong service.

## 2. Hợp đồng `TaskExecutor` thực sự bảo đảm gì?

`org.springframework.core.task.TaskExecutor` là interface của Spring, mở rộng `java.util.concurrent.Executor` của Java. Phương thức cốt lõi:

```java
void execute(Runnable task);
```

Khi gọi `execute(task)`, caller yêu cầu executor thực thi một `Runnable` theo chính sách của implementation. Hợp đồng **không hứa** rằng tác vụ luôn chạy trên thread khác, được chạy ngay lập tức, chạy theo thứ tự gửi, hoặc chắc chắn được chấp nhận khi hệ thống đã quá tải.

| Implementation | Cách thực thi nổi bật | Phù hợp khi |
| --- | --- | --- |
| `ThreadPoolTaskExecutor` | Dùng thread pool và hàng đợi có thể cấu hình; Spring quản lý vòng đời | Ứng dụng cần pool để xử lý nhiều tác vụ |
| `SyncTaskExecutor` | Gọi `Runnable.run()` ngay trên thread hiện tại | Test đơn giản hoặc trường hợp chủ ý chạy đồng bộ |
| `SimpleAsyncTaskExecutor` | Thường tạo thread mới cho mỗi tác vụ, không tái sử dụng pool; có thể cấu hình virtual threads trên nền tảng hỗ trợ | Nhu cầu thực thi khác với mô hình pool truyền thống |
| `ConcurrentTaskExecutor` | Adapter bọc một Java `Executor` có sẵn | Muốn dùng executor do nơi khác cung cấp |

Một implementation có thể chạy *synchronous*, một implementation khác chạy *asynchronous*. Vì thế, tên interface `TaskExecutor` nói về **khả năng gửi tác vụ**, không nói rằng mọi implementation đều luôn bất đồng bộ.

Đừng nhầm các mức trừu tượng:

- `TaskExecutor`: cần chức năng `execute(Runnable)`; không nhận trực tiếp kết quả trả về.
- `AsyncTaskExecutor`: interface mở rộng với khả năng gửi tác vụ nhận `Future` (tùy phương thức và phiên bản API); chỉ phụ thuộc vào nó nếu service thực sự cần tính năng này.
- `TaskScheduler`: dùng để lên lịch chạy tại thời điểm cụ thể hoặc theo chu kỳ; đây là mục đích khác với gửi một task để chạy.
- `Executor` của JDK: cũng có `execute(Runnable)`; có thể dùng làm kiểu tham số nếu không cần hợp đồng riêng của Spring.

**Nguyên tắc lựa chọn:** dùng interface hẹp nhất đáp ứng nghiệp vụ. Service chỉ “gửi việc” nên thường chỉ cần `TaskExecutor`.

## 3. Ví dụ chạy được: một service, hai cách thực thi

Ví dụ dưới đây dùng **Java 21, Spring Framework 6.2.1 và Maven**. Service phụ thuộc `TaskExecutor`; phần cấu hình chọn bean có tên `businessExecutor`. Mặc định ứng dụng dùng pool; khi bật profile `sync`, ứng dụng dùng executor chạy đồng bộ. Không cần sửa `MessageService` giữa hai chế độ.

### 3.1. Tạo cấu trúc dự án

```text
executor-di-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ExecutorDiDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>executor-di-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>21</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.1</version>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.ExecutorDiDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp Maven định nghĩa dependency cần thiết cho Spring Context, dùng mã nguồn tương thích Java 21. Không cần Spring Boot để chứng minh constructor injection; Boot cũng sử dụng cùng nguyên tắc DI này.

### 3.2. Mã Java hoàn chỉnh

**Tệp `src/main/java/example/ExecutorDiDemo.java`:**

```java
package example;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.task.SyncTaskExecutor;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ExecutorDiDemo {
    public static final class MessageService {
        private final TaskExecutor executor;

        public MessageService(TaskExecutor executor) {
            this.executor = executor;
        }

        public CountDownLatch submit(String message) {
            CountDownLatch done = new CountDownLatch(1);
            executor.execute(() -> {
                try {
                    System.out.println("Processed: " + message);
                } finally {
                    done.countDown();
                }
            });
            return done;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("businessExecutor")
        @Profile("!sync")
        public ThreadPoolTaskExecutor pooledExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(32);
            executor.setThreadNamePrefix("business-");
            return executor;
        }

        @Bean("businessExecutor")
        @Profile("sync")
        public TaskExecutor syncExecutor() {
            return new SyncTaskExecutor();
        }

        @Bean
        public MessageService messageService(
                @Qualifier("businessExecutor") TaskExecutor executor) {
            return new MessageService(executor);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        String mode = args.length > 0 && "sync".equals(args[0])
                ? "sync" : "pool";
        try (var context = new AnnotationConfigApplicationContext()) {
            if ("sync".equals(mode)) {
                context.getEnvironment().setActiveProfiles("sync");
            }
            context.register(AppConfig.class);
            context.refresh();

            System.out.println("Mode: " + mode);
            CountDownLatch done =
                    context.getBean(MessageService.class).submit("M001");
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task timed out");
            }
            System.out.println("Completed: true");
        }
    }
}
```

### 3.3. Chạy và kiểm chứng

Chạy tại thư mục chứa `pom.xml` với JDK 21 trở lên và Maven:

```bash
mvn -q -DskipTests compile exec:java
```

Output của ứng dụng:

```text
Mode: pool
Processed: M001
Completed: true
```

Chuyển sang executor đồng bộ bằng profile `sync`:

```bash
mvn -q -Dexec.args=sync exec:java
```

Output của ứng dụng:

```text
Mode: sync
Processed: M001
Completed: true
```

Các output trên đã được chạy kiểm chứng với Maven và biên dịch ở mức ngôn ngữ Java 21. Maven/JVM có thể in thêm thông báo môi trường khi chạy không ở chế độ `-q`.

**Vì sao thứ tự output ổn định trong ví dụ?** Luồng chính đợi `CountDownLatch.await(...)`; task in dòng `Processed` trước khi gọi `countDown()`. Dù bản pool có thể xử lý task trên thread khác, chương trình chỉ in `Completed: true` sau khi latch đã được giải phóng.

`CountDownLatch` ở đây chỉ minh họa cách đợi task kết thúc. Trong ứng dụng thực tế, một latch được giảm trong `finally` không khẳng định công việc thành công; để nhận giá trị hoặc lỗi, hãy dùng cơ chế trả kết quả và xử lý exception phù hợp.

## 4. Phân tích vì sao ví dụ tách được implementation

### 4.1. Service chỉ biết interface

```java
private final TaskExecutor executor;

public MessageService(TaskExecutor executor) {
    this.executor = executor;
}
```

Không có lời gọi `new ThreadPoolTaskExecutor()`, không biết kích thước pool và không kiểm tra `instanceof` để quyết định cách chạy. Điều service biết là **đã có một đối tượng nhận `Runnable` để thực thi**.

Trong Spring, constructor injection làm dependency hiển thị rõ khi tạo service, dễ kiểm thử và cho phép trường `final`. Khi service chỉ có một constructor, Spring có thể tự tiêm mà không cần `@Autowired` trên constructor.

### 4.2. Cấu hình sở hữu implementation

Hai method cấu hình đều khai báo bean tên `businessExecutor`, nhưng điều kiện `@Profile` bảo đảm chỉ cấu hình phù hợp được kích hoạt:

- Không bật profile `sync` → `pooledExecutor()` tạo `ThreadPoolTaskExecutor`.
- Bật profile `sync` → `syncExecutor()` tạo `SyncTaskExecutor`.

Bean `messageService(...)` chỉ yêu cầu tham số kiểu `TaskExecutor`. Spring tra cứu bean tương thích rồi tiêm. Chính phần cấu hình biết tên implementation và các thông số kỹ thuật.

Ở bản pool, đối tượng cụ thể là `ThreadPoolTaskExecutor` để có thể đặt `corePoolSize`, `maxPoolSize`, `queueCapacity` và tên thread. Khi Spring quản lý bean này, Spring kích hoạt callback khởi tạo và đóng executor theo vòng đời context. Đừng tự khởi tạo rồi bỏ mặc một thread pool ở bên trong business service.

### 4.3. Vì sao cần `@Qualifier`?

Trong ứng dụng lớn, có thể cùng tồn tại executor cho gửi email, ghi báo cáo, xử lý sự kiện và các tác vụ khác. Nếu chỉ inject kiểu `TaskExecutor` khi có nhiều bean cùng kiểu, Spring có thể không xác định được bean nào cần chọn, hoặc một bean `@Primary` có thể vô tình được dùng không đúng mục đích.

```java
@Bean
public MessageService messageService(
        @Qualifier("businessExecutor") TaskExecutor executor) {
    return new MessageService(executor);
}
```

`@Qualifier("businessExecutor")` xác định **vai trò** của executor, không ràng buộc service vào một class implementation. Tên bean mang nghĩa nghiệp vụ ổn định qua các cấu hình; tên implementation có thể thay đổi.

Nếu chỉ có một bean thích hợp, qualifier có thể không cần. Khi có nhiều bean, ưu tiên qualifier hoặc cách đặt tên rõ ràng để tránh đổi executor ngoài ý muốn.

## 5. Kiểm thử dễ hơn khi tiêm interface

Một lợi ích lớn của DI là có thể kiểm thử phần logic **mà không phải tạo pool, không chờ thread hay dùng `Thread.sleep`**.

Ví dụ dùng executor giả thu lại các `Runnable`. Đoạn dưới là một fragment minh họa trong test; nó dùng `MessageService` của ví dụ phía trên và các import Java tương ứng:

```java
List<Runnable> submittedTasks = new ArrayList<>();
TaskExecutor fakeExecutor = submittedTasks::add;
ExecutorDiDemo.MessageService service =
        new ExecutorDiDemo.MessageService(fakeExecutor);

CountDownLatch done = service.submit("T001");

// Task mới chỉ được gửi vào fake executor, chưa được chạy.
if (submittedTasks.size() != 1 || done.getCount() != 1) {
    throw new AssertionError("Expected exactly one pending task");
}

submittedTasks.get(0).run(); // Test chủ động quyết định khi nào chạy.
if (done.getCount() != 0) {
    throw new AssertionError("Task did not finish");
}
```

Các import cho fragment: `java.util.List`, `java.util.ArrayList`, `java.util.concurrent.CountDownLatch` và `org.springframework.core.task.TaskExecutor`.

Cách làm này kiểm tra được **service có gửi đúng một tác vụ** và việc thực thi task hoàn tất khi test chủ động gọi `run()`. Test không phụ thuộc thread scheduling. Nếu cần test tuần tự đơn giản hơn, dùng `new SyncTaskExecutor()`.

Lưu ý rằng “test được gửi tác vụ” chưa đồng nghĩa test được side effect cuối cùng như gửi email thành công. Hãy tách việc tạo nội dung/email ra khỏi cơ chế gửi nền để có thể assert kết quả nghiệp vụ độc lập.

## 6. Khi nào nên tiêm interface nào?

Chọn theo thứ **business service thật sự sử dụng**:

| Nhu cầu | Phụ thuộc phù hợp | Điều không nên giả định |
| --- | --- | --- |
| Chỉ giao `Runnable` để thực thi | `TaskExecutor` hoặc `Executor` | Task chắc chắn chạy ở thread khác |
| Muốn API `submit(...)` và nhận handle kết quả | `AsyncTaskExecutor` hoặc loại executor hỗ trợ `Future` | Mọi `TaskExecutor` đều có `submit` |
| Cần tác vụ chạy theo giờ/chu kỳ | `TaskScheduler` | `TaskExecutor` tự tạo lịch |
| Cần lấy active count, queue size để giám sát | Thành phần cấu hình/monitoring gắn với implementation, ví dụ `ThreadPoolTaskExecutor` | Service nghiệp vụ phải ép kiểu từ `TaskExecutor` |
| Chỉ muốn tuân theo JDK không phụ thuộc Spring API | `java.util.concurrent.Executor` | Phải dùng class Spring trong business logic |

Không nên tiêm `ThreadPoolTaskExecutor` vào service chỉ để gọi `execute()`. Nếu service phải gọi `getActiveCount()` hoặc thay đổi `setCorePoolSize()` trong lúc xử lý request, đó thường là dấu hiệu đang trộn trách nhiệm nghiệp vụ với giám sát/vận hành.

Đừng dùng ép kiểu như `((ThreadPoolTaskExecutor) executor).getActiveCount()` trong service: một ngày chuyển implementation sang `SyncTaskExecutor` sẽ gây `ClassCastException`. Những tính năng đặc thù nên nằm ở cấu hình hoặc thành phần chuyên giám sát hạ tầng.

## 7. Tiêm `TaskExecutor` khác gì với dùng `@Async`?

**Inject một `TaskExecutor`** nghĩa là business code chủ động gửi `Runnable` bằng `executor.execute(...)`. Nó hoạt động theo implementation đã tiêm, không yêu cầu cơ chế proxy của `@Async`.

**`@Async`** là cơ chế riêng của Spring để chuyển lời gọi method phù hợp sang executor. Với cấu hình Spring Framework thuần, thường cần `@EnableAsync` và method phải được gọi thông qua Spring proxy từ bên ngoài bean. Method tự gọi bằng `this.someAsyncMethod()` thường không đi qua proxy và không kích hoạt hành vi `@Async` theo cấu hình proxy mặc định.

Ví dụ minh họa (cần cấu hình `@EnableAsync` và một Spring-managed bean thích hợp, **không phải đoạn chạy độc lập**):

```java
@Async("businessExecutor")
public void sendNoticeAsync(String id) {
    // Xử lý nội dung thông báo.
}
```

`@Async("businessExecutor")` yêu cầu Spring tra executor theo tên; còn `@Qualifier("businessExecutor") TaskExecutor executor` là DI tại điểm khai báo dependency. Hai cơ chế có thể dùng cùng một bean nhưng khác đường gọi, vòng đời và nơi quan sát exception.

Tương tự, `CompletableFuture.runAsync(runnable, executor)` có thể nhận một `Executor`, nhưng tương tác đó không tự làm I/O bên trong task thành nonblocking. Một worker đang chờ JDBC/HTTP blocking vẫn có thể bị chiếm suốt thời gian chờ.

## 8. Ranh giới thực thi cần được quản lý dù đã tách interface

### 8.1. Số thread, hàng đợi và quá tải

Cấu hình minh họa `corePoolSize=2`, `maxPoolSize=4`, `queueCapacity=32` là thông số cho ví dụ, **không phải giá trị mặc định thích hợp cho mọi ứng dụng**. Với một `ThreadPoolTaskExecutor` dùng hàng đợi có dung lượng dương, pool thường ưu tiên dùng core threads rồi xếp hàng; chỉ khi queue đầy mới mở rộng vượt core đến max. Vì thế, đặt `maxPoolSize` lớn không đảm bảo pool lập tức mở rộng khi nhiều tác vụ đến.

Khi pool và queue đều không còn chỗ, lời gọi `execute(...)` có thể bị từ chối bằng `TaskRejectedException` (theo hợp đồng của Spring). Service phải có chính sách phù hợp: báo lỗi, retry có giới hạn, ghi nhận trạng thái thất bại hoặc sử dụng hàng đợi bền vững nếu nghiệp vụ cần bảo đảm giao việc.

Đo `active threads`, `queue depth`, tỷ lệ rejection, độ trễ xử lý và mức sử dụng CPU để cấu hình; không tăng pool vô hạn để giải quyết vấn đề downstream chậm.

### 8.2. Exception và kết quả

Khi dùng `execute(Runnable)` với implementation bất đồng bộ, exception phát sinh **bên trong worker** không tự động trở thành exception được ném lại trên thread gọi. Tách hai trường hợp:

- **Lỗi lúc gửi task:** có thể xảy ra trực tiếp tại `execute(...)`, ví dụ bị từ chối do quá tải.
- **Lỗi trong lúc chạy task:** cần ghi log/capture ở worker hoặc dùng cơ chế Future/CompletionStage, hệ thống quan sát task, hay cơ chế báo lỗi nghiệp vụ.

Không trả về “đã xử lý thành công” chỉ vì `execute(...)` không ném exception. Điều đó thường chỉ cho biết executor đã chấp nhận tác vụ theo hợp đồng implementation.

### 8.3. Giao dịch, bảo mật và ThreadLocal

Khi task thực sự chạy trên thread khác, không giả định các giá trị gắn với thread gọi được mang theo tự động. `ThreadLocal`, MDC logging, security context hoặc transaction context có thể không xuất hiện tại worker. Spring transaction khai báo bằng `@Transactional` không tự mở rộng nguyên vẹn sang một thread mới chỉ vì caller đang có transaction.

Thiết kế truyền **dữ liệu cần thiết** vào task, giới hạn thời gian thực thi, xử lý context propagation có chủ đích khi cần và đặt ranh giới transaction ở nơi tác vụ thực sự chạy. Có thể dùng `TaskDecorator` hoặc giải pháp context propagation phù hợp cho metadata quan sát, nhưng không lạm dụng sao chép trạng thái mutable giữa threads.

### 8.4. Thread safety và lifecycle

Một service được Spring tạo mặc định là singleton, và nhiều task có thể dùng chung cùng một instance. Mã trong `Runnable` phải bảo vệ trạng thái chia sẻ bằng cơ chế đồng bộ phù hợp hoặc ưu tiên dữ liệu bất biến. Việc inject qua interface không làm logic tự động thread-safe.

Để Spring quản lý executor nhằm có cơ chế khởi tạo, shutdown và lifecycle thích hợp. Khi đóng ứng dụng, cần xác định task đang chạy được hoàn tất, bị hủy hay bị chờ theo cấu hình; đừng giả định mọi công việc nền luôn được flush khi context đóng.

## 9. Lỗi thiết kế thường gặp

1. **Tiêm implementation vào mọi service:** làm code nghiệp vụ phụ thuộc API cấu hình pool; thay executor buộc sửa nhiều nơi.
2. **Gọi `new ThreadPoolTaskExecutor()` trong service:** bỏ qua quản lý bean lifecycle, dễ quên khởi tạo hoặc shutdown và khó thay thế khi test.
3. **Cho rằng `TaskExecutor` luôn async:** `SyncTaskExecutor` là phản ví dụ rõ ràng. Nếu nghiệp vụ yêu cầu tuyệt đối không chặn caller, phải đưa yêu cầu đó vào thiết kế và kiểm thử cấu hình thực tế.
4. **Có nhiều bean `TaskExecutor` nhưng không chỉ định rõ:** dễ injection ambiguity hoặc chọn sai pool; dùng tên vai trò và `@Qualifier` phù hợp.
5. **Dựa vào `maxPoolSize` khi queue còn rộng:** cấu hình pool có thể xếp hàng lâu và không mở rộng như tưởng tượng.
6. **Không xử lý rejection hoặc lỗi worker:** service báo đã gửi việc dù task bị từ chối hoặc thất bại bên trong.
7. **Tưởng thread mới giữ nguyên context request/transaction:** gây mất correlation id hoặc lỗi quyền truy cập, hoặc dùng transaction không đúng ranh giới.
8. **Test bằng `Thread.sleep` chờ tác vụ:** thường chậm và flakey; thay bằng test executor, latch có timeout, hoặc Future có kết quả.
9. **Dùng một pool cho mọi loại công việc:** task chờ I/O dài có thể chiếm hết worker, khiến tác vụ nhạy độ trễ bị starvation. Tách pool theo nhu cầu thực tế và đo tải.

## 10. Checklist áp dụng vào dự án Spring

Trước khi đưa một executor vào service, hãy tự trả lời:

- **Business contract:** service chỉ cần gửi `Runnable`, hay cần `Future`/kết quả, lên lịch hoặc bảo đảm giao việc?
- **Injection boundary:** field và constructor của service dùng `TaskExecutor` (hoặc `Executor`) hay đang vô tình phụ thuộc class pool?
- **Bean identity:** có bean executor đúng vai trò, tên nhất quán và `@Qualifier` rõ ràng khi có nhiều bean?
- **Runtime behavior:** trong môi trường hiện tại executor chạy đồng bộ hay bất đồng bộ, pool/queue có thể quá tải thế nào?
- **Testability:** có thể thay bằng `SyncTaskExecutor` hoặc fake executor và kiểm thử không phụ thuộc timing?
- **Operations:** timeout, exception, rejection, propagation, shutdown và các metric đã được xử lý ở đúng tầng chưa?

Một cách chia lớp dễ bảo trì là **business service nói “thực hiện tác vụ này” qua interface; phần cấu hình nói “thực hiện bằng cách nào” qua implementation**. Cấu trúc này giữ nghiệp vụ ổn định khi chuyển từ thực thi đồng bộ trong test sang thread pool trong runtime hoặc thay executor về sau.

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)