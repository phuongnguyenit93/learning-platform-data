# TaskExecutor là hợp đồng thực thi tác vụ của Spring

## 1. TaskExecutor giải quyết vấn đề gì?

Trong ứng dụng Spring, một thành phần có thể cần giao một công việc cho cơ chế thực thi: gửi email, xử lý tệp, tạo báo cáo hoặc tính toán một phần dữ liệu. Thành phần gọi chỉ cần biết **cách gửi tác vụ**; nó không nên phải tự tạo `Thread`, quản lý hàng đợi và chọn thread cho mỗi lần gọi.

`org.springframework.core.task.TaskExecutor` là hợp đồng (interface) mà Spring cung cấp cho việc đó. Nó **kế thừa `java.util.concurrent.Executor`** và khai báo đúng một thao tác cốt lõi:

```java
public interface TaskExecutor extends java.util.concurrent.Executor {
    @Override
    void execute(Runnable task);
}
```

Đoạn trên là **mô hình chữ ký API**, không phải mã để chép thành một interface mới. Trong ứng dụng thật, hãy import `org.springframework.core.task.TaskExecutor` từ Spring.

`execute(Runnable)` có nghĩa: **yêu cầu một executor thực thi một `Runnable` theo chính sách của implementation**. Nó *không* cam kết task sẽ chạy trên thread khác, không cam kết thời điểm bắt đầu, và không trả về giá trị hay `Future`. Một implementation có thể chạy đồng bộ ngay trên thread gọi, có thể tạo thread mới, hoặc đưa công việc vào thread pool.

Phân biệt ba vai trò:

- **`Runnable`**: *làm việc gì?* Một hàm không có tham số truyền vào `run()` và không trả kết quả trực tiếp.
- **`TaskExecutor`**: *giao việc cho cơ chế thực thi nào?* Hợp đồng `execute(Runnable)` mà code nghiệp vụ phụ thuộc vào.
- **Implementation** như `ThreadPoolTaskExecutor`: *thực thi ra sao?* Quyết định thread, hàng đợi, giới hạn song song, từ chối tác vụ và vòng đời.

Vì chỉ phụ thuộc interface, một service có thể thay executor đồng bộ trong kiểm thử bằng executor sử dụng pool khi triển khai thật, mà không phải sửa logic gọi `execute`.

## 2. Hợp đồng `execute(Runnable)` và những gì không được giả định

Một lời gọi điển hình:

```java
taskExecutor.execute(() -> generateReport(reportId));
```

Đây là **mảnh mã bên trong một service đã có `taskExecutor` và `generateReport`**, không phải chương trình Java chạy độc lập. Nó chỉ biểu thị thao tác submit một `Runnable`.

Luồng xử lý khái niệm:

```text
Service gọi execute(task)
          |
          v
 TaskExecutor (hợp đồng)
          |
          +-- SyncTaskExecutor --------> chạy task ngay trên caller thread
          |
          +-- SimpleAsyncTaskExecutor -> tạo thread mới cho mỗi task
          |
          +-- ThreadPoolTaskExecutor --> thread đang rảnh / hàng đợi / thêm thread
          |
          +-- Adapter khác -----------> chuyển giao cho executor bên dưới
```

Cụ thể:

1. **Giao việc không nhất thiết là bất đồng bộ.** `SyncTaskExecutor` thực thi ngay trong lời gọi `execute`; `ThreadPoolTaskExecutor` thường giao cho thread khác. Không nên suy luận cách chạy chỉ từ tên interface.
2. **`execute` không có kết quả trả về.** Kiểu trả về là `void`, nên một lời gọi thành công chỉ cho biết executor đã xử lý yêu cầu theo hợp đồng của nó. Nếu triển khai bất đồng bộ, task có thể vẫn đang xếp hàng hoặc chạy.
3. **Executor có quyền từ chối.** Khi pool đóng hoặc không nhận thêm việc, Spring có thể ném `TaskRejectedException` (một subtype của `RejectedExecutionException`); tác vụ bị từ chối không được xem là đã xử lý.
4. **Executor không tự làm dữ liệu chia sẻ thành an toàn.** Dù task được xếp hàng đúng, truy cập đồng thời tới một biến `int` hoặc `ArrayList` mutable vẫn cần cơ chế đồng bộ thích hợp.
5. **Interface không có `submit()`, `get()`, `shutdown()` hay `schedule()`.** Những khả năng này nằm ở abstraction mở rộng hoặc API khác.

Một quy tắc thiết kế hữu ích: tham số, dependency hoặc field của service nên là `TaskExecutor` khi service **chỉ cần giao `Runnable`**. Nếu cần dùng Future để chờ kết quả, sử dụng `AsyncTaskExecutor` hoặc API trả về Future tương ứng.

## 3. Các kiểu TaskExecutor thường gặp

| Implementation | Cách chạy | Khi nào phù hợp | Cần lưu ý |
| --- | --- | --- | --- |
| `SyncTaskExecutor` | Chạy task trực tiếp trên caller thread | Kiểm thử xác định, đường xử lý đồng bộ | `execute` có thể chặn tới khi task xong; không tạo bất đồng bộ |
| `SimpleAsyncTaskExecutor` | Tạo thread mới cho mỗi tác vụ, không tái sử dụng pool | Công việc độc lập, trường hợp muốn tránh quản lý pool cố định | Nhiều tác vụ có thể tạo nhiều thread; cần xem giới hạn đồng thời |
| `ThreadPoolTaskExecutor` | Dùng `ThreadPoolExecutor` và hàng đợi được cấu hình | Phần lớn công việc bất đồng bộ cần kiểm soát tài nguyên | Phải hiểu `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection |
| `ConcurrentTaskExecutor` | Adapter bao quanh một `java.util.concurrent.Executor` sẵn có | Tích hợp executor JDK hoặc runtime cung cấp | Hành vi thực tế theo delegate; adapter không tạo quy tắc lập lịch mới |
| `VirtualThreadTaskExecutor` (Spring hỗ trợ trên JDK 21+) | Mỗi task chạy trên virtual thread | Tác vụ blocking/I/O phù hợp với mô hình virtual thread | Không nên dùng làm cách tự động xử lý mọi giới hạn tải; vẫn cần quản lý tài nguyên ngoài thread |

`TaskExecutor` kế thừa `Executor` nên có thể truyền Spring `TaskExecutor` vào nơi chấp nhận `Executor`. Chiều ngược lại không mặc định đúng: một `Executor` JDK bất kỳ không tự trở thành `TaskExecutor`; dùng adapter phù hợp nếu cần API Spring.

Lưu ý thêm: `AsyncTaskExecutor extends TaskExecutor` là hợp đồng **bất đồng bộ** của Spring; nó bổ sung các phương thức như `submit(Runnable)`, `submit(Callable<T>)`, `submitCompletable(...)` trong các phiên bản Spring hiện đại. `ThreadPoolTaskExecutor` triển khai abstraction mở rộng này.

## 4. Ví dụ Spring Framework có thể chạy trên Java 17+

Ví dụ dưới đây chứng minh ba điểm: client lấy bean bằng interface `TaskExecutor`; pool được Spring quản lý; caller dùng một tín hiệu hoàn tất riêng vì `execute` không trả `Future`.

Tạo dự án Maven tối thiểu:

```text
taskexecutor-demo/
├── pom.xml
└── src/main/java/demo/TaskExecutorContractDemo.java
```

Nội dung `pom.xml` (Spring Framework 6.2.7, không yêu cầu Spring Boot):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>taskexecutor-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Nội dung `src/main/java/demo/TaskExecutorContractDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TaskExecutorContractDemo {

    @Bean("workerPool")
    public ThreadPoolTaskExecutor workerPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("worker-");
        return pool;
        // Spring khởi tạo và hủy bean theo vòng đời context.
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                 new AnnotationConfigApplicationContext(TaskExecutorContractDemo.class)) {
            TaskExecutor taskExecutor =
                    context.getBean("workerPool", TaskExecutor.class);

            AtomicInteger answer = new AtomicInteger();
            CountDownLatch finished = new CountDownLatch(1);

            taskExecutor.execute(() -> {
                try {
                    answer.set(6 * 7);
                } finally {
                    finished.countDown();
                }
            });

            finished.await();
            System.out.println("Result = " + answer.get());
        }
    }
}
```

Tại thư mục gốc dự án, chạy với JDK 17+ và Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TaskExecutorContractDemo
```

Dòng stdout do chương trình tạo ra khi tác vụ hoàn thành bình thường:

```text
Result = 42
```

Giải thích từng bước:

1. `@Configuration` và `@Bean("workerPool")` tạo một bean `ThreadPoolTaskExecutor`. Container tự gọi lifecycle khởi tạo thích hợp; **không cần gọi `pool.initialize()` thủ công trong phương thức `@Bean`**.
2. Client lấy bean bằng kiểu `TaskExecutor`, chỉ sử dụng `execute`. Nó không cần phụ thuộc vào phương thức riêng của `ThreadPoolTaskExecutor`.
3. Task chạy qua pool, đặt `answer = 42` rồi gọi `countDown()`. Caller dùng `await()` để chờ trước khi đọc kết quả; quan hệ đồng bộ của `CountDownLatch` cũng giúp dữ liệu đã ghi hiển thị đúng.
4. Khối `try` đóng Spring context; container quản lý việc hủy executor theo lifecycle. Đừng tạo pool mới cho mỗi yêu cầu nghiệp vụ.

Ví dụ được thiết kế sao cho **thứ tự xuất stdout không phụ thuộc vào lịch chạy thread**. Nó không giả định `execute()` trả về khi tác vụ đã xong. Nếu cần xử lý lỗi hoặc kết quả tác vụ như một đối tượng, phần tiếp theo dùng `Future` sẽ phù hợp hơn.

## 5. Sử dụng TaskExecutor qua dependency injection

Trong ứng dụng có nhiều service, hãy inject executor qua constructor và chỉ định bean rõ ràng nếu có nhiều executor cùng kiểu:

```java
@Service
public class ReportService {
    private final TaskExecutor executor;

    public ReportService(@Qualifier("workerPool") TaskExecutor executor) {
        this.executor = executor;
    }

    public void requestReport(String reportId) {
        executor.execute(() -> generateReport(reportId));
    }

    private void generateReport(String reportId) {
        // Logic tạo báo cáo chạy theo chiến lược của executor.
    }
}
```

Đây là **mảnh mã tích hợp Spring**, cần import `@Service`, `@Qualifier`, `TaskExecutor` và có bean `workerPool` trong context. `requestReport` gửi yêu cầu thực thi; trong cấu hình thread pool, lời gọi có thể trở về trước khi báo cáo hoàn thành. Nếu việc tạo báo cáo thất bại sau đó, caller không tự nhận được exception qua `requestReport`.

Ưu điểm của việc inject theo hợp đồng: `ReportService` không phải tự quyết định số thread, queue hoặc shutdown. Cấu hình và giám sát các vấn đề đó nằm ở bean executor.

## 6. Cần kết quả: TaskExecutor khác AsyncTaskExecutor

`TaskExecutor.execute(Runnable)` trả `void`. Nếu cần lấy kết quả và nhận exception bất đồng bộ, Spring cung cấp `AsyncTaskExecutor` mở rộng hợp đồng:

```java
AsyncTaskExecutor executor = /* một bean AsyncTaskExecutor */;
Future<Integer> result = executor.submit(() -> 21 * 2);
int answer = result.get(); // 42
```

Đây là **mảnh mã API**, không phải chương trình biên dịch độc lập: nó cần import, bean executor và xử lý `InterruptedException`, `ExecutionException`. `submit(Callable<T>)` trả `Future<T>`; `Future.get()` chờ kết thúc và trả kết quả hoặc báo lỗi. `submit(Runnable)` trả `Future<?>` dùng để chờ hoàn tất (giá trị thành công là `null`). Với Spring 6+, `submitCompletable(...)` có thể trả `CompletableFuture` để ghép các bước xử lý.

So sánh nhanh:

| Nhu cầu | API thích hợp | Điều caller nhận |
| --- | --- | --- |
| Giao một công việc `Runnable` | `TaskExecutor.execute(task)` | Không có handle kết quả |
| Chạy tác vụ và đợi hoàn tất/lỗi | `AsyncTaskExecutor.submit(task)` | `Future` |
| Chạy `Callable<T>` để lấy giá trị | `AsyncTaskExecutor.submit(callable)` | `Future<T>` |
| Kết hợp nhiều bước bất đồng bộ | `submitCompletable` hoặc `CompletableFuture` | Có thể compose, chờ, xử lý lỗi |

Không nên cố ép `TaskExecutor` thành `ExecutorService` chỉ để gọi `submit`: hai abstraction này có API và vòng đời khác nhau. Cũng không nên dùng một biến thường kèm `Thread.sleep()` để đoán thời điểm task hoàn thành.

## 7. Chính sách thread pool nằm ở implementation

Với `ThreadPoolTaskExecutor`, ba thuộc tính cốt lõi là:

- `corePoolSize`: số thread nền tảng mà pool có thể tạo khi nhận việc.
- `queueCapacity`: số tác vụ có thể chờ trong hàng đợi; giá trị dương tạo hàng đợi có sức chứa tương ứng.
- `maxPoolSize`: giới hạn thread có thể mở rộng khi hàng đợi đã đầy.

Trong cấu hình JDK `ThreadPoolExecutor` mặc định mà Spring bao quanh, trình tự khái quát là: ưu tiên tạo thread tới mức core khi cần; khi đã đạt core, đưa task mới vào queue nếu còn chỗ; khi queue đầy mới tăng số thread tới max; khi không còn khả năng nhận thì từ chối theo chính sách đã cấu hình.

Ví dụ đã cấu hình `core=2, max=4, queue=8`: các tác vụ có thể chờ trong queue khi hai thread lõi bận, sau đó pool mới mở rộng vượt core nếu queue đã đầy. Con số này chỉ là **ví dụ cấu hình**, không phải mức mặc định bắt buộc cho mọi ứng dụng.

Một bẫy quan trọng: `ThreadPoolTaskExecutor` theo mặc định có `corePoolSize=1`, `maxPoolSize` rất lớn và queue gần như không giới hạn. Vì queue có thể tiếp tục nhận việc nên pool thường không cần tăng vượt core. **Chỉ tăng `maxPoolSize` mà giữ queue không giới hạn không đảm bảo tăng throughput song song**. Ngược lại, `queueCapacity=0` dùng cơ chế bàn giao trực tiếp và có thể tạo thread nhanh hơn; cần giới hạn max phù hợp để tránh quá tải.

Khi số task tới nhiều hơn khả năng xử lý, mặc định Spring có thể ném `TaskRejectedException`. Hãy chọn hành vi rõ: phản hồi bận, retry có giới hạn, lưu công việc vào hàng đợi bền vững hoặc áp dụng backpressure, tùy yêu cầu hệ thống. **Executor trong bộ nhớ không thay thế hệ thống hàng đợi bền vững**: task chưa thực thi có thể mất khi tiến trình kết thúc đột ngột.

## 8. Hợp đồng giao việc không tự bao gồm các bảo đảm khác

### Thứ tự và khả năng nhìn thấy bộ nhớ

Vì `TaskExecutor` kế thừa `java.util.concurrent.Executor`, quy tắc của JDK về giao task áp dụng: các hành động của caller **trước khi gửi `Runnable` tới Executor** có quan hệ *happens-before* với việc task thực thi. Nhưng một lời gọi `execute` bất đồng bộ trả về **không** tự công bố mọi thay đổi trong task về caller. Khi cần đọc kết quả, phải dùng `Future.get()`, `CountDownLatch.await()` hoặc cơ chế đồng bộ có hợp đồng rõ ràng.

Ví dụ sai về giả định hoàn tất:

```java
executor.execute(() -> state.value = 42);
System.out.println(state.value); // Có thể đọc giá trị cũ; thiếu tín hiệu hoàn tất.
```

Đây là **đoạn minh họa** giả sử `executor` bất đồng bộ và `state` là dữ liệu chia sẻ. Đổi thành `SyncTaskExecutor` có thể làm ví dụ *trông đúng* do chạy cùng thread, nhưng khi thay implementation thành pool thì lỗi xuất hiện. Đó là lý do không viết code nghiệp vụ dựa trên chi tiết thực thi ngoài hợp đồng.

### Exception, rejection và quan sát

Có hai thời điểm lỗi khác nhau: **lúc giao việc** (`TaskRejectedException` do executor không nhận task), và **lúc chạy task** (exception bên trong `Runnable`). Với executor bất đồng bộ và `execute`, exception trong worker không mặc nhiên được ném lại ở thread gọi. Muốn truyền kết quả/lỗi về caller, dùng Future hoặc cơ chế thông báo rõ ràng. Với Future, kiểm tra `ExecutionException`, ngắt, hủy và timeout thay vì luôn giả định thành công.

### Dữ liệu và ngữ cảnh theo thread

`ThreadLocal`, MDC logging, security context và transaction context của thread gọi thường **không tự chuyển nguyên vẹn** sang thread worker. Khi cần truyền một phần context có chủ đích, dùng cơ chế phù hợp (ví dụ `TaskDecorator`) và phải khôi phục/xóa context trong `finally` để tránh rò rỉ sang task kế tiếp trong pool. `TaskDecorator` wrap callback thực thi; với Future, callback được wrap có thể không phải chính `Runnable` gốc và không nhất thiết phơi ra exception của task để decorator bắt trực tiếp.

### Vòng đời

Một executor là bean Spring thường được khởi tạo và đóng theo application context. Nếu tự tạo `ThreadPoolTaskExecutor` bằng `new` **ngoài Spring container**, cần chủ động `initialize()` và shutdown khi không dùng nữa. `TaskExecutor` interface thuần không có `shutdown()`; không nên viết service nghiệp vụ tự ép kiểu để dừng bean executor dùng chung.

## 9. Quan hệ với @Async, TaskScheduler và Spring Boot

- **`TaskExecutor`**: cách một thành phần chủ động gọi `execute(task)` để giao `Runnable`.
- **`@Async`**: cơ chế khai báo trên phương thức; khi được bật bằng `@EnableAsync`, lời gọi đi qua Spring proxy được interceptor chuyển thành tác vụ trên executor. Có thể chọn bean bằng `@Async("workerPool")`. Tự gọi `this.someAsyncMethod()` trong cùng bean thường bỏ qua proxy ở chế độ mặc định.
- **`TaskScheduler`**: hợp đồng khác dùng để lên lịch theo thời điểm, chu kỳ hoặc `Trigger`; `TaskExecutor` chỉ nhận tác vụ để thực thi, không tự định nghĩa lịch cron.
- **Spring Boot**: có thể tự cấu hình executor theo điều kiện của Boot. **Đó là tiện ích của Boot**, không phải thuộc tính mặc định của interface `TaskExecutor` trong Spring Framework thuần.

Ví dụ tối giản để nhìn thấy ranh giới:

```java
// Tự giao Runnable:
taskExecutor.execute(() -> processOnce());

// Đánh dấu phương thức: framework gọi executor qua proxy khi đã bật @EnableAsync.
@Async("workerPool")
public void processLater() {
    processOnce();
}
```

Đây là **mảnh mã minh họa ngữ cảnh Spring**, không phải một class Java độc lập; `@Async` cần import và cấu hình, đồng thời phải được gọi qua proxy phù hợp. Dùng `@Async` không làm cho mọi lời gọi trực tiếp đến phương thức trong cùng object đều bất đồng bộ.

## 10. Lỗi thường gặp khi học TaskExecutor

1. **Nghĩ `TaskExecutor` đồng nghĩa thread pool.** Nó chỉ là hợp đồng; `SyncTaskExecutor` chạy trên caller thread. Kiểm tra implementation thực tế.
2. **Nghĩ `execute()` trả về là task xong.** Điều đó chỉ đúng nếu chiến lược thực thi đồng bộ. Với pool, cần handle hoặc tín hiệu hoàn tất.
3. **Đòi `get()` từ biến khai báo `TaskExecutor`.** Interface này chỉ có `execute`. Dùng `AsyncTaskExecutor` khi cần Future.
4. **Tự tạo thread/pool trong mỗi HTTP request.** Dễ mất kiểm soát tài nguyên và lifecycle. Inject bean executor dùng chung với giới hạn thích hợp.
5. **Chỉ chỉnh `maxPoolSize` mà để queue rất lớn.** Pool có thể không mở rộng như mong đợi; hiểu mối quan hệ core → queue → max.
6. **Bỏ qua task rejection và lỗi bên trong worker.** Phân biệt lỗi gửi việc với lỗi xử lý; theo dõi và xác định chính sách thông báo/retry.
7. **Phụ thuộc vào `ThreadLocal` của caller.** Xác định context nào cần truyền; không mặc định transaction hoặc dữ liệu thread-local đi theo task.
8. **Dùng `Thread.sleep()` để đợi hoàn thành.** Ngủ không cung cấp bảo đảm đồng bộ; dùng Future/latch/CompletionStage.
9. **Lẫn `TaskExecutor` với `TaskScheduler` hoặc `@Async`.** Một thứ là hợp đồng thực thi, một thứ là lên lịch, một thứ là cách kích hoạt bất đồng bộ qua proxy.

## 11. Tự kiểm tra hiểu bài

Hãy thử trả lời:

- Nếu đổi bean từ `ThreadPoolTaskExecutor` sang `SyncTaskExecutor`, lời gọi `execute` còn hợp lệ không? **Có**, vì cả hai tuân theo hợp đồng `TaskExecutor`; hành vi threading thay đổi.
- Tại sao caller không thể gọi `taskExecutor.get()`? **Vì `TaskExecutor` không quản lý một kết quả cụ thể và không có phương thức đó**.
- Cần chắc chắn tác vụ đã tạo xong kết quả để HTTP response đọc được: `execute` đủ chưa? **Chưa**; cần cơ chế chờ kết quả rõ ràng hoặc thiết kế workflow trả kết quả bất đồng bộ.
- Pool có `maxPoolSize=20` nhưng queue không giới hạn; liệu nó luôn dùng tới 20 thread? **Không**; queue thường nhận việc sau khi đạt core nên max có thể không được sử dụng.
- Nếu cùng một service chạy được khi dùng `SyncTaskExecutor` nhưng sai khi chuyển sang pool, nên kiểm tra gì? **Giả định hoàn tất ngay, dữ liệu chia sẻ, thứ tự và context theo thread**.

**Điểm cần nhớ:** `TaskExecutor` định nghĩa *cách giao việc*, còn cách thực thi thuộc implementation. Thiết kế đúng là chọn mức abstraction sát với nhu cầu: `execute` khi chỉ cần giao `Runnable`, `AsyncTaskExecutor`/Future khi cần kết quả, và một cơ chế đồng bộ hoặc workflow rõ ràng khi nhiều task phụ thuộc nhau.

### Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — `TaskExecutor` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskExecutor.html)
- [Spring Framework — `AsyncTaskExecutor` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Spring Framework — `ThreadPoolTaskExecutor` JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
