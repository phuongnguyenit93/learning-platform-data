# ConcurrentTaskExecutor: thích nghi Executor có sẵn trong Spring Framework

## Mục tiêu và tình huống sử dụng

Khi ứng dụng đã có một bộ thực thi của Java, chẳng hạn `ExecutorService` do thư viện, cấu hình hạ tầng hoặc một thành phần khác tạo ra, ta có thể muốn sử dụng **cùng bộ thực thi ấy** trong những API của Spring yêu cầu `TaskExecutor` hoặc `AsyncTaskExecutor`. `org.springframework.scheduling.concurrent.ConcurrentTaskExecutor` là một **adapter** cho tình huống đó.

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa `java.util.concurrent.Executor`, `ExecutorService`, Spring `TaskExecutor`, `AsyncTaskExecutor` và `ConcurrentTaskExecutor`.
2. Bọc một executor JDK đang có bằng `new ConcurrentTaskExecutor(existingExecutor)` và hiểu task chạy ở đâu.
3. Dùng adapter làm bean với `@Async("springExecutor")`, hoặc gọi `execute`/`submit` trực tiếp.
4. Xác định bên nào sở hữu thread pool, hàng đợi, chính sách từ chối, shutdown và monitoring.
5. Quyết định khi nào nên dùng `ConcurrentTaskExecutor`, `TaskExecutorAdapter`, `ThreadPoolTaskExecutor` hoặc `ConcurrentTaskScheduler`.

**Ý chính:** `ConcurrentTaskExecutor` **không tạo thêm một pool** khi bạn truyền vào một executor có sẵn. Nó cung cấp một bề mặt API tương thích với Spring và **ủy quyền thực thi** xuống executor gốc. Hành vi thực tế vẫn do executor gốc quyết định.

## 1. Vấn đề mà adapter giải quyết

Giả sử một hệ thống đã cấu hình:

```java
java.util.concurrent.ExecutorService existing =
    java.util.concurrent.Executors.newFixedThreadPool(2);
```

`existing` là bộ thực thi của JDK. Một thành phần Spring có thể muốn nhận `org.springframework.core.task.AsyncTaskExecutor` để dùng thống nhất các thao tác gửi công việc và nhận `Future`. Ta có thể thích nghi:

```java
import org.springframework.scheduling.concurrent.ConcurrentTaskExecutor;

ConcurrentTaskExecutor springExecutor = new ConcurrentTaskExecutor(existing);
```

Hai dòng trên chỉ minh họa phần liên kết, chưa phải chương trình độc lập: cần import, xử lý lifecycle của `existing` và đóng pool khi nó không còn được sử dụng.

Dòng chảy thực tế:

```text
Caller hoặc thành phần Spring
        |
        | execute(task) / submit(callable)
        v
ConcurrentTaskExecutor                 <-- adapter dùng API của Spring
        |
        | ủy quyền sang cùng Executor đã cung cấp
        v
Existing java.util.concurrent.Executor <-- nơi quyết định scheduling,
        |                                  threads, queue, rejection
        v
Thread thực thi công việc
        |
        +----> kết thúc, Future hoàn tất hoặc báo lỗi
```

**Đừng nhầm “thích nghi interface” với “biến đổi chính sách chạy”.** Adapter không tự đổi số worker, hàng đợi, độ ưu tiên, cancellation, timeout hay shutdown của executor bên dưới. Nó cũng không bảo đảm mọi task sẽ được chạy trên thread khác caller: JDK `Executor` được phép thực thi đồng bộ.

## 2. Phân biệt các interface có liên quan

| Kiểu | Hợp đồng chính | Điều quan trọng |
| --- | --- | --- |
| JDK `Executor` | `void execute(Runnable task)` | Chỉ yêu cầu thực thi; có thể chạy ngay, xếp hàng hoặc bị từ chối. |
| JDK `ExecutorService` | Mở rộng `Executor` với `submit`, `Future`, `shutdown`, quản lý vòng đời | Có thể là thread pool, nhưng không phải lúc nào cũng là loại pool bạn tự cấu hình. |
| Spring `TaskExecutor` | Mở rộng ý tưởng `Executor` với `execute(Runnable)` | Cổng chung để Spring nhận một bộ thực thi; quy ước lỗi của Spring có `TaskRejectedException`. |
| Spring `AsyncTaskExecutor` | Mở rộng `TaskExecutor`, thêm khả năng gửi task với `Callable` và nhận `Future`/`CompletableFuture` | Giúp thành phần Spring xử lý kết quả bất đồng bộ qua interface chung. |
| Spring `ConcurrentTaskExecutor` | Adapter nhận một JDK `Executor`, đồng thời triển khai các interface thực thi của Spring | Vẫn sử dụng executor được truyền vào; có thể dùng `execute`, `submit`, cấu hình `TaskDecorator`. |
| Spring `SchedulingTaskExecutor` | Biểu lộ một số đặc điểm liên quan tới scheduling cho bên gửi task | **Không phải** `TaskScheduler`, không cấp API đặt lịch chạy theo giờ/cron. |

Với Spring Framework 6.2, `ConcurrentTaskExecutor` triển khai cả `AsyncTaskExecutor` và `SchedulingTaskExecutor`; nó cũng hỗ trợ khả năng thích nghi của `ExecutorService` và phát hiện Jakarta `ManagedExecutorService` trong môi trường tương ứng.

### `execute` khác `submit` thế nào?

`execute(Runnable)` gửi một công việc không mang giá trị trả về. Phương thức có thể trả quyền điều khiển cho caller trước khi task chạy xong nếu executor thực thi bất đồng bộ. Nếu executor từ chối ngay khi gửi, caller nhận lỗi tại thời điểm gửi.

`submit(Callable<T>)` trả `Future<T>` để người gọi có thể lấy giá trị, chờ hoặc quan sát lỗi:

```java
Future<Integer> future = springExecutor.submit(() -> 21 * 2);
Integer value = future.get(); // có thể chặn caller cho đến khi xong
```

Đây là đoạn sử dụng bên trong phương thức đã có adapter và khai báo/handle ngoại lệ `get()`. Trong một ví dụ đầy đủ ở phần sau, ta dùng `CompletableFuture` với `@Async`.

Khi delegate là `ExecutorService`, adapter có thể tận dụng khả năng `submit` của delegate. Nếu chỉ là `Executor` cơ bản, Spring có thể dùng wrapper kiểu `FutureTask` và gửi nó qua `execute`. **Có `Future` không chứng tỏ task chạy song song**: hãy xem chính sách của delegate.

## 3. Chọn ConcurrentTaskExecutor khi nào?

| Bối cảnh | Lựa chọn phù hợp | Lý do |
| --- | --- | --- |
| Đã có `Executor`/`ExecutorService` cần tái sử dụng qua API Spring | `ConcurrentTaskExecutor(existingExecutor)` | Bọc executor đã được cấu hình/điều phối mà không tạo pool mới. |
| Chỉ cần adapter tối giản cho JDK `Executor` sang Spring `AsyncTaskExecutor` | `TaskExecutorAdapter` trong `org.springframework.core.task.support` | Adapter gọn hơn, hữu ích khi không cần các khả năng tích hợp thêm của `ConcurrentTaskExecutor`. |
| Muốn Spring cấu hình và quản lý thread pool bằng các bean properties | `ThreadPoolTaskExecutor` | Có `corePoolSize`, `maxPoolSize`, `queueCapacity`, điều khiển vòng đời và monitoring phù hợp. |
| Đã có `ScheduledExecutorService` và muốn API lập lịch `TaskScheduler` | `ConcurrentTaskScheduler` | Đây là adapter cho scheduling; **không** dùng `ConcurrentTaskExecutor` thay nó. |
| Chạy trong Jakarta EE server với executor do container quản lý | `DefaultManagedTaskExecutor` hoặc adapter tới managed executor phù hợp | Sử dụng cơ chế thread management của máy chủ; tránh tạo pool không được phép. |
| Chỉ cần gắn `@Async` với một bean `Executor` JDK theo tên | Có thể dùng trực tiếp bean `Executor` đó | Spring cho phép `@Async("beanName")` tham chiếu tới bean `Executor`; bọc adapter không phải thủ tục bắt buộc. |

Vậy vì sao vẫn dùng adapter khi `@Async` chấp nhận `Executor`? Bởi một thành phần khác có thể yêu cầu **chính interface `TaskExecutor`/`AsyncTaskExecutor`**, hoặc bạn muốn xuất một bean thống nhất của Spring đồng thời giữ quyền cấu hình tài nguyên ở JDK executor. Đừng tự động bọc mọi executor hai lần nếu ứng dụng không có nhu cầu đó.

`ConcurrentTaskExecutor` có constructor nhận `Executor`, cùng `setConcurrentExecutor(...)` và `getConcurrentExecutor()`. Constructor không đối số đã bị deprecated trong các bản Spring gần đây; ưu tiên **truyền executor tường minh** để ai tạo và ai sở hữu tài nguyên đều rõ ràng.

## 4. Ví dụ hoàn chỉnh: dùng chung một ExecutorService với @Async

Ví dụ dưới đây chạy với **Java 17+**, Maven và **Spring Framework 6.2.12**. Hệ thống sở hữu một JDK `ThreadPoolExecutor` đã được cấu hình, rồi công bố nó cho Spring qua `ConcurrentTaskExecutor`.

Ta chủ động chọn queue có giới hạn nhằm thể hiện rằng **chính pool JDK** quyết định mức song song và backpressure. Mẫu này tách bean JDK executor khỏi bean adapter; trong ứng dụng thực, bean JDK có thể được cung cấp bởi module hạ tầng hoặc thành phần tích hợp khác.

Cấu trúc thư mục:

```text
concurrent-executor-demo/
├── pom.xml
└── src/main/java/example/ConcurrentExecutorDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>concurrent-executor-demo</artifactId>
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
                <configuration>
                    <mainClass>example.ConcurrentExecutorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/ConcurrentExecutorDemo.java`:

```java
package example;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ConcurrentTaskExecutor;

public class ConcurrentExecutorDemo {

    public record WorkResult(String value, Thread executedBy) {
    }

    public static class WorkService {
        @Async("springExecutor")
        public CompletableFuture<WorkResult> process(String input) {
            // Thân phương thức chạy trên executor đã chọn qua Spring proxy.
            WorkResult result = new WorkResult(
                "processed:" + input,
                Thread.currentThread()
            );
            return CompletableFuture.completedFuture(result);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean(name = "externalPool", destroyMethod = "shutdown")
        public ExecutorService externalPool() {
            AtomicInteger threadIds = new AtomicInteger();
            ThreadFactory threadFactory = task ->
                new Thread(task, "external-pool-" + threadIds.incrementAndGet());

            return new ThreadPoolExecutor(
                2, 2, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(16),
                threadFactory,
                new ThreadPoolExecutor.AbortPolicy()
            );
        }

        @Bean("springExecutor")
        public ConcurrentTaskExecutor springExecutor(
                @Qualifier("externalPool") ExecutorService rawExecutor) {
            return new ConcurrentTaskExecutor(rawExecutor);
        }

        @Bean
        public WorkService workService() {
            return new WorkService();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            ExecutorService raw = context.getBean(
                "externalPool", ExecutorService.class);
            ConcurrentTaskExecutor adapted = context.getBean(
                "springExecutor", ConcurrentTaskExecutor.class);
            WorkService service = context.getBean(WorkService.class);
            Thread caller = Thread.currentThread();

            CompletableFuture<WorkResult> handle = service.process("A");
            WorkResult result = handle.join();

            System.out.println("sameDelegate="
                + (adapted.getConcurrentExecutor() == raw));
            System.out.println("workerPrefix="
                + result.executedBy().getName().startsWith("external-pool-"));
            System.out.println("differentThread="
                + (result.executedBy() != caller));
            System.out.println("value=" + result.value());
        }
    }
}
```

Từ thư mục `concurrent-executor-demo`, chạy:

```bash
mvn -q compile exec:java
```

Bốn dòng được **chương trình** in ra theo thứ tự (log của Maven hoặc thư viện, nếu có, không thuộc bốn dòng này):

```text
sameDelegate=true
workerPrefix=true
differentThread=true
value=processed:A
```

### Phân tích từng bước

1. `externalPool()` tạo một `ThreadPoolExecutor` thuộc **JDK**: tối đa hai worker, queue chứa 16 task chờ và chính sách từ chối `AbortPolicy`. Bean này được Spring giữ và đóng bằng `shutdown` khi context kết thúc.
2. `springExecutor(rawExecutor)` tạo một `ConcurrentTaskExecutor` tham chiếu **đúng executor đã có**. Phép so sánh `getConcurrentExecutor() == raw` chứng minh adapter không thay đối tượng delegate.
3. `@EnableAsync` kích hoạt xử lý `@Async` theo cơ chế proxy mặc định. `context.getBean(WorkService.class)` lấy bean được quản lý bởi Spring; lời gọi `process("A")` từ `main` đi qua proxy.
4. `@Async("springExecutor")` định danh bean executor rõ ràng. Interceptor gửi công việc qua adapter tới `externalPool`; worker JDK chạy thân `process`.
5. Worker tạo `WorkResult` cùng tên thread và trả `CompletableFuture.completedFuture(result)`. **Future hoàn tất bên trong worker** không có nghĩa phần thân phương thức chạy trên caller.
6. Caller có `handle` và gọi `join()` để lấy giá trị. Nếu tác vụ chưa xong, `join()` chặn caller; nếu đã xong, lấy ngay. Các dòng kiểm tra cho thấy delegate đồng nhất và thread thực thi khác caller trong **cấu hình cụ thể này**.
7. Khi thoát `try`, `AnnotationConfigApplicationContext.close()` kích hoạt hủy bean do container quản lý. Ví dụ đã `join()` thành công nên không còn công việc chưa hoàn tất cần chờ.

`Thread` nằm trong `WorkResult` chỉ để kiểm chứng ví dụ. Trong ứng dụng thực, response nghiệp vụ nên trả dữ liệu nghiệp vụ, không trả tham chiếu tới thread.

### Vì sao kết quả ví dụ xác định được?

Ta **không dựa vào thứ tự log giữa nhiều worker**. Chương trình chờ task duy nhất bằng `join()`, rồi mới in. Pool được tạo với `ThreadFactory` đặt tiền tố rõ ràng cho worker; `ThreadPoolExecutor` với hai worker luôn gửi công việc tới worker của pool, không chạy trực tiếp trên caller với `AbortPolicy`. Vì vậy bốn phép kiểm tra trong điều kiện chạy thành công đều cho giá trị nêu trên.

Nếu thay `AbortPolicy` bằng `CallerRunsPolicy`, khi pool quá tải một task bị từ chối có thể được chạy ngay trên thread submit. Lúc đó giả định `differentThread=true` sẽ không còn đúng với mọi task. Cần phân biệt ví dụ có kiểm soát và hành vi trong các chính sách khác.

## 5. Adapter không bảo đảm một thread khác

Hợp đồng JDK `Executor.execute()` cho phép một executor chạy task ngay trên caller. Chẳng hạn đoạn sau có thể đặt trong một phương thức Java đã có dependency `spring-context`:

```java
import java.util.concurrent.Executor;
import org.springframework.scheduling.concurrent.ConcurrentTaskExecutor;

Thread caller = Thread.currentThread();
Executor directExecutor = Runnable::run;
ConcurrentTaskExecutor adapter = new ConcurrentTaskExecutor(directExecutor);

adapter.execute(() ->
    System.out.println("sameThread="
        + (Thread.currentThread() == caller))
);
```

Kết quả:

```text
sameThread=true
```

`Runnable::run` chạy task trực tiếp. Spring adapter chỉ ủy quyền, nên không tạo thread mới. Nếu dùng executor kiểu này với `@Async`, lời gọi vẫn có thể thực thi ngay trên caller dù phương thức được gắn annotation. Tên `AsyncTaskExecutor` nói về **API có khả năng nhận task kiểu bất đồng bộ**, không phải cam kết độc lập với delegate về chính sách chạy.

Tương tự, một `ExecutorService` có một worker có thể chạy task bất đồng bộ nhưng **không chạy song song nhiều task cùng lúc**. Hàng đợi có thể tăng trong khi chỉ một worker xử lý. Muốn xác định concurrency thật, kiểm tra executor gốc, không chỉ kiểu của adapter.

## 6. Gửi task trực tiếp và quan sát kết quả

Ngoài `@Async`, các thành phần nội bộ có thể được inject một `AsyncTaskExecutor` hoặc `ConcurrentTaskExecutor` rồi gọi trực tiếp:

```java
// Đoạn bên trong phương thức đã nhận AsyncTaskExecutor executor.
executor.execute(() -> sendAuditSignal());

Future<String> answer = executor.submit(() -> fetchValue());
String value = answer.get();
```

Đoạn này là ví dụ thao tác, **không** phải chương trình Java độc lập; `sendAuditSignal()` và `fetchValue()` là hàm nghiệp vụ do ứng dụng cung cấp. `Future.get()` yêu cầu xử lý `InterruptedException` và `ExecutionException`, và có thể chặn.

Với `@Async` trả `CompletableFuture<T>`, ta thường ghép các stage:

```java
CompletableFuture<String> display = service.process("B")
    .thenApply(result -> "Result: " + result.value());
```

Đoạn trên giả định đã có `WorkService service` của ví dụ chính. `thenApply` có thể chạy ở thread hoàn tất stage hoặc thread đã quan sát stage hoàn tất; nó **không** bảo đảm chạy trên pool mới. Nếu dùng `thenApplyAsync`, xét rõ executor nào xử lý bước kế tiếp; dùng overload nhận `Executor` để tránh vô tình chuyển việc sang common pool của JDK.

### Thành công, thất bại, bị từ chối

Ba thời điểm cần phân biệt:

- **Trước khi nhận task:** `ThreadPoolExecutor` có thể từ chối bởi queue đầy hoặc đã shutdown. Khi gọi qua Spring adapter, dạng lỗi thường được dịch sang `TaskRejectedException`. Không có `Future` hợp lệ cho công việc chưa được chấp nhận.
- **Trong khi task chạy:** exception trong công việc được phản ánh qua `Future.get()` dưới `ExecutionException`, hoặc qua `CompletableFuture.join()` thường dưới `CompletionException`. Không nên coi việc `submit()` trả về thành công là nghiệp vụ đã hoàn tất.
- **Khi hủy/timeout:** `Future.cancel(...)` có thể yêu cầu hủy, nhưng sự dừng thực tế phụ thuộc task có hợp tác ngắt hay không. Timeout lúc chờ kết quả không tự buộc worker ngừng làm việc.

Với phương thức `@Async` trả `void`, không có `Future` để caller kiểm tra ngoại lệ. Nếu thật sự cần kiểu này, cấu hình `AsyncUncaughtExceptionHandler` và kênh quan sát lỗi phù hợp. Với công việc quan trọng, ưu tiên một handle kết quả và chiến lược idempotent/retry hoặc queue bền vững.

## 7. Ai cấu hình, ai sở hữu, ai đóng executor?

Câu hỏi quan trọng nhất khi dùng adapter là **đơn vị nào sở hữu delegate**.

`ConcurrentTaskExecutor` nhận executor bằng constructor hoặc setter. **Adapter không thay bạn quản lý toàn bộ lifecycle của executor được cung cấp**. Nếu pool được tạo bởi ứng dụng, ứng dụng phải có chính sách tắt pool khi dừng. Nếu pool được chia sẻ bởi nhiều thành phần, một component không được tự ý `shutdown` pool giữa lúc các component khác còn dùng. Nếu là managed executor của Jakarta EE container, việc cấp phát và shutdown thường thuộc container.

Trong ví dụ trên:

```text
ApplicationContext
  ├── externalPool : ExecutorService
  |      ├── 2 worker threads
  |      └── bounded queue(16)
  |            (Spring gọi shutdown lúc đóng context vì bean có destroyMethod)
  |
  ├── springExecutor : ConcurrentTaskExecutor
  |      └── tham chiếu externalPool, không tạo pool thứ hai
  |
  └── workService
         └── @Async("springExecutor") dùng lại externalPool
```

`shutdown()` thông thường **ngừng tiếp nhận task mới nhưng không mặc nhiên chờ tất cả task đang chạy hoàn tất**. Nếu cần shutdown có kiểm soát, nơi sở hữu pool phải định nghĩa chính sách `awaitTermination`, timeout, xử lý interruption, công việc chưa bắt đầu và dữ liệu cần bảo toàn. Ví dụ tự đóng context sau khi đã `join()` nên đơn giản hơn trường hợp production.

`ConcurrentTaskExecutor` cũng cho phép `setConcurrentExecutor(newExecutor)` để thay delegate. Việc đổi delegate chỉ áp dụng theo thời điểm gửi về sau; task đã submit vào executor cũ không vì vậy được di chuyển sang executor mới. Phải phối hợp vòng đời của cả hai pool trước khi đổi trong hệ thống đang hoạt động; tốt nhất cấu hình một lần khi khởi động trừ khi có yêu cầu vận hành rõ ràng.

### ManagedExecutorService trong Jakarta EE

Trong môi trường Jakarta EE, Spring adapter có thể nhận biết `ManagedExecutorService` và thích nghi thêm metadata của managed task. Nếu lấy executor mặc định từ JNDI, `DefaultManagedTaskExecutor` là lựa chọn chuyên dụng. Hãy tuân thủ chính sách thread của application server; đừng tự tạo `ThreadPoolExecutor` để né cơ chế quản lý luồng của server.

## 8. Cấu hình tải, hàng đợi và theo dõi phải xét ở delegate

Trong ví dụ, pool cấu hình:

```java
new ThreadPoolExecutor(
    2, 2, 0, TimeUnit.MILLISECONDS,
    new ArrayBlockingQueue<>(16),
    threadFactory,
    new ThreadPoolExecutor.AbortPolicy()
);
```

Đây là ví dụ có giới hạn rõ ràng, không phải kích thước tối ưu cho mọi hệ thống.

- **Số worker (`corePoolSize`, `maximumPoolSize`)** giới hạn concurrency của pool JDK. Nếu công việc blocking I/O, cách chọn thông số khác với công việc CPU-bound; cần đo thời gian chạy, chờ và tải thực.
- **Hàng đợi** giữ task chưa được thực thi; queue dài làm độ trễ tăng dù caller nhận `Future` nhanh. `Executors.newFixedThreadPool` tạo hàng đợi không giới hạn về số phần tử theo triển khai phổ biến; tránh coi nó tự tạo backpressure bảo vệ hệ thống.
- **Rejection policy** quyết định ứng xử khi không còn chỗ nhận. `AbortPolicy` ném lỗi; `CallerRunsPolicy` có thể ép caller thực thi task, gây chặn và phá giả định luôn khác thread; các policy bỏ task cần cân nhắc tính đúng đắn nghiệp vụ.
- **Monitoring** phải theo dõi số worker đang chạy, queue depth, thời gian chờ/chạy, số lỗi và rejection từ delegate hoặc hệ đo phù hợp. `ConcurrentTaskExecutor` không tự cung cấp mọi metric và nút cấu hình pool của `ThreadPoolTaskExecutor`.

Nếu delegate thực sự là `ThreadPoolExecutor`, các phương thức `getActiveCount()`, `getPoolSize()` và `getQueue().size()` chỉ cho ảnh chụp tức thời, có thể thay đổi ngay sau khi đọc. Không viết test giả định giá trị các metric này luôn cố định dưới concurrent load.

## 9. TaskDecorator và dữ liệu theo thread

`ConcurrentTaskExecutor.setTaskDecorator(TaskDecorator)` cho phép bọc callback trước khi thực thi, thường dùng để mang correlation ID/logging context hoặc đo thời gian. Nhưng adapter **không tự truyền** tất cả `ThreadLocal` từ caller sang worker.

Một decorator đúng phải:

1. Chụp dữ liệu cần thiết **ở phía gửi task**.
2. Đặt dữ liệu đó trong thread đang chạy task.
3. Dọn dẹp/khôi phục trạng thái trong `finally`, vì worker của pool có thể phục vụ request khác sau đó.
4. Tránh mang đối tượng request đã hết vòng đời, `SecurityContext` sai user hoặc đối tượng mutable không an toàn luồng.

Khi dùng `submit`, callback mà decorator thấy có thể là wrapper kiểu `FutureTask`, không phải `Runnable` gốc. `FutureTask` giữ lỗi để người gọi quan sát qua `get()`, nên decorator bắt lỗi đơn giản bằng `try/catch` quanh `runnable.run()` **có thể không nhìn thấy exception của task**. Thiết kế logging/metrics riêng cho kết quả `Future` nếu cần.

Tương tự, transaction gắn với thread gọi không được tự chuyển sang worker chỉ nhờ adapter hay `@Async`. Nếu cần thao tác giao dịch trong task nền, xác định ranh giới transaction ở worker thông qua cơ chế Spring phù hợp; không dựa vào transaction đang mở trên HTTP request thread.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách xử lý |
| --- | --- | --- |
| “Bọc `Executor` sẽ tạo pool mới.” | Đếm nhầm thread, resource hoặc tuning sai nơi. | Dùng `getConcurrentExecutor()` và kiểm tra delegate; adapter ủy quyền tới cùng instance. |
| “Adapter có chữ Concurrent nên chắc chắn chạy thread khác.” | `Executor` trực tiếp hoặc `CallerRunsPolicy` có thể chạy trên caller. | Đọc chính sách delegate, kiểm tra thread và tình huống overload. |
| “Dùng `@Async` là tự động chạy qua adapter.” | Chưa bật `@EnableAsync`, self-invocation hoặc chọn nhầm bean có thể làm khác kỳ vọng. | Gọi qua bean/proxy Spring, chọn `@Async("springExecutor")`, kiểm tra cấu hình. |
| “`submit()` trả Future nghĩa là task đã chạy xong.” | Xử lý dữ liệu chưa sẵn sàng hoặc bỏ sót lỗi. | Chọn callback/composition hoặc `get()`/`join()` có chủ đích. |
| “Muốn lịch cron thì dùng `ConcurrentTaskExecutor`.” | Không có API `TaskScheduler` để đặt lịch theo thời gian. | Dùng `ConcurrentTaskScheduler` hoặc `ThreadPoolTaskScheduler`. |
| “Đổi wrapper là thay luôn queue và core size.” | Tuning không có tác dụng. | Cấu hình chính executor gốc; nếu muốn Spring bean-style pool, xét `ThreadPoolTaskExecutor`. |
| “Tắt adapter sẽ tự giải quyết mọi task còn chạy.” | Task dở dang hoặc shutdown không đúng tài nguyên. | Gán ownership rõ ràng, gọi shutdown/await ở bên sở hữu delegate. |
| “Truyền được `ThreadLocal` nhờ Spring.” | Mất trace/security context hoặc rò rỉ context qua worker tái sử dụng. | Dùng decorator hoặc công cụ propagation phù hợp, khôi phục trong `finally`. |
| “Bọc `ExecutorService` là đủ để xử lý overload.” | Queue tăng, rejection gây lỗi hoặc caller bị chặn. | Giới hạn tài nguyên, đặt policy và quan sát queue/rejection. |

### Tình huống trước và sau khi thích nghi

**Trước:** module hạ tầng đã tạo `ExecutorService sharedExecutor` và có chính sách riêng. Một module Spring muốn nhận `AsyncTaskExecutor` và gọi `submit(Callable<T>)`; việc viết pool Spring mới sẽ làm phân tán cấu hình tài nguyên và chia tải khác ý định.

**Sau:** module tích hợp tạo **một** bean `ConcurrentTaskExecutor(sharedExecutor)` và inject cho thành phần Spring. Nơi cấp `sharedExecutor` vẫn quản lý số worker, queue, shutdown. Thành phần Spring gọi qua interface của mình và quan sát `Future`. Việc tích hợp có một ranh giới rõ ràng, không cần pool thứ hai.

Nếu yêu cầu thực tế chỉ là `@Async` trỏ tới bean `Executor`, có thể bỏ adapter và đặt `@Async("sharedExecutor")`: Spring hỗ trợ chọn một `Executor` bean. Chỉ duy trì adapter khi có lợi ích cụ thể về interface Spring hoặc quản lý tích hợp.

## 11. Câu hỏi tự kiểm tra

**1. `ConcurrentTaskExecutor` được tạo với `Executor direct = Runnable::run`. Gọi `execute` có chắc chạy trên thread khác không?**

Không. Delegate gọi `Runnable.run()` ngay; task chạy trên caller. Adapter không đổi chính sách thực thi.

**2. Vì sao `getConcurrentExecutor() == rawExecutor` có thể là `true`?**

Adapter lưu và sử dụng chính delegate đã truyền vào; nó không tạo thêm một thread pool để thay thế. Kết quả `true` chứng minh đồng nhất object trong ví dụ.

**3. Có cần `ConcurrentTaskExecutor` để chỉ định `@Async("myJdkExecutor")` không?**

Không nhất thiết. Tên trong `@Async` có thể tham chiếu bean `Executor`. Adapter hữu ích khi API khác cần `TaskExecutor`/`AsyncTaskExecutor` hoặc có yêu cầu tích hợp Spring cụ thể.

**4. Queue của JDK executor đầy, `AbortPolicy` từ chối task. Adapter có tự tạo worker bổ sung không?**

Không. Delegate quyết định từ chối. Spring adapter có thể biểu diễn lỗi theo hợp đồng `TaskRejectedException`; cần xử lý overload ở tầng thiết kế pool và nghiệp vụ.

**5. Một `ConcurrentTaskExecutor` có thể dùng để schedule cron không?**

Không. `SchedulingTaskExecutor` không đồng nghĩa `TaskScheduler`. Với `ScheduledExecutorService` cần API lập lịch Spring, xem `ConcurrentTaskScheduler`.

**6. Có hai executor bean, một là JDK pool và một là adapter bọc chính pool ấy. Điều này có nghĩa có bốn thread nếu pool có hai worker không?**

Không. Hai bean trỏ tới hai bề mặt API, nhưng chỉ có **một** JDK thread pool hai worker trong ví dụ. Số thread có thể thay đổi theo chính sách pool; adapter không tự nhân đôi worker.

**7. `@Async("springExecutor")` chạy trong worker, nhưng callback sau `thenApply` có nhất thiết dùng worker đó không?**

Không. `thenApply` có thể chạy trên thread hoàn tất stage hoặc thread đăng ký khi stage đã hoàn tất. Nếu cần cố định executor cho stage, dùng biến thể `...Async(..., executor)` và truyền executor theo thiết kế.

### Tóm lược

Khi chọn bộ thực thi trong Spring, hãy xác định **nơi executor đã tồn tại**, **API mà thành phần Spring cần**, **ai sở hữu pool**, **tài nguyên được giới hạn thế nào**, và **kết quả/lỗi được quan sát ra sao**. `ConcurrentTaskExecutor` có nhiệm vụ nối các interface để dùng lại đúng executor JDK đã có; quyết định về thread, queue, tính song song và lifecycle vẫn nằm ở delegate.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): mô hình `TaskExecutor`, các loại executor và tích hợp `@Async`.
- [Spring Framework — ConcurrentTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ConcurrentTaskExecutor.html): constructor, delegate, `execute`, `submit`, `setTaskDecorator`.
- [Spring Framework — TaskExecutorAdapter API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/support/TaskExecutorAdapter.html): adapter cơ bản từ JDK `Executor`.
- [Java 17 — Executor API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html) và [ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): hợp đồng thực thi, kết quả và shutdown.
