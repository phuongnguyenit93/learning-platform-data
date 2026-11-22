# ThreadLocal không tự theo công việc sang nhóm luồng khác

## Mục tiêu

Trong ứng dụng Spring, thông tin về một lần xử lý như correlation ID, request ID, tài khoản đang thao tác hay dữ liệu để ghi log thường được lưu trong `ThreadLocal`. Điều này thuận tiện khi mọi lời gọi diễn ra **trên cùng một thread**. Nhưng `@Async`, `TaskExecutor`, `ExecutorService`, `CompletableFuture.supplyAsync(...)` và một số cơ chế xử lý song song có thể chuyển phần việc sang **một thread khác**. Khi ấy, `ThreadLocal` của thread gửi **không tự xuất hiện** ở thread nhận.

Đây là một vấn đề về **ngữ cảnh thực thi**, không phải lỗi của `@Async`. Hiểu sai có thể gây mất correlation ID, log không gắn được request, đọc nhầm người dùng, hoặc tệ hơn là **rò rỉ dữ liệu ngữ cảnh của tác vụ trước** khi thread pool tái sử dụng worker.

Bài này giúp bạn:

1. Giải thích chính xác `ThreadLocal` gắn giá trị với **thread**, không với task, `Future`, HTTP request hay một Spring bean.
2. Hiểu lý do `ThreadLocal.get()` có thể có giá trị ở caller nhưng trả `null` ở worker chạy `@Async`.
3. Phân biệt `ThreadLocal`, `InheritableThreadLocal`, truyền dữ liệu bằng tham số và cơ chế context propagation có chủ đích.
4. Dùng `TaskDecorator` của Spring để **chụp** context lúc gửi task, **gắn** vào worker khi chạy, và **khôi phục/xóa** trong `finally`.
5. Chạy một chương trình Java 17+ với Spring Framework 6.2.x chứng minh cả trường hợp context mất, context được truyền có chủ đích và ngăn rò rỉ qua một worker được tái sử dụng.
6. Nhận diện những context **không nên sao chép mù quáng**, đặc biệt transaction, `EntityManager`, request-scoped object và security state mutable.

**Thông điệp chính:** `ThreadLocal` giải quyết việc truy cập dữ liệu **theo thread hiện tại**. Executor giải quyết việc thực thi **theo task**. Nếu muốn đưa một phần ngữ cảnh từ caller sang worker, phải thiết kế **chuyển giao context** tại ranh giới submit và cleanup tại ranh giới kết thúc task.

## 1. ThreadLocal lưu dữ liệu theo thread như thế nào?

`java.lang.ThreadLocal<T>` cung cấp các API cơ bản:

```java
ThreadLocal<String> requestId = new ThreadLocal<>();

requestId.set("req-123");
String sameThread = requestId.get(); // "req-123"
requestId.remove();                  // xóa binding trên thread hiện tại
```

Đây là đoạn Java đơn giản bên trong một method, không phải chương trình độc lập. Một object `ThreadLocal` dùng chung **không** có nghĩa các thread dùng chung một giá trị. Mỗi thread có binding riêng đối với cùng key `ThreadLocal`.

Mô hình:

```text
                  CÙNG MỘT ThreadLocal<String> KEY
                                  |
     +----------------------------+----------------------------+
     |                            |                            |
 request-thread-1             pool-worker-1                pool-worker-2
 key -> "req-A"               key -> null                  key -> "req-old"
     |                            |                            |
 get() -> "req-A"             get() -> null                get() -> "req-old"
```

`new ThreadLocal<>()` có `initialValue()` mặc định là `null`; thread chưa từng `set` key đó sẽ đọc được `null`. Nếu dùng `ThreadLocal.withInitial(supplier)`, một thread có thể nhận **giá trị khởi tạo riêng của nó**, nhưng đó vẫn **không phải** giá trị được copy tự động từ caller.

Một biến `static final ThreadLocal<String> ID` thường là **key chung** được mọi thread tham chiếu. Giá trị vẫn ở trong vùng lưu riêng của từng thread. Đừng nhầm `static` ở key với `static String currentRequestId` (một biến giá trị dùng chung, không an toàn nếu các request đồng thời ghi đè).

### ThreadLocal không phải kho dữ liệu cho một request

Một request HTTP đôi khi được xử lý hoàn toàn bởi một Servlet thread nên các thao tác cùng thread đọc `ThreadLocal` tương ứng. Nhưng khi request được dispatch qua worker, chuyển sang callback, lên lịch retry hoặc tham gia xử lý bất đồng bộ, việc giữ nguyên request identity **không còn được bảo đảm bằng ThreadLocal thông thường**. Nó cũng không phù hợp để lưu kết quả nghiệp vụ dài hạn hoặc chia sẻ state qua nhiều tiến trình.

## 2. Vì sao @Async không tự mang ThreadLocal sang worker?

Hãy hình dung code ở một controller/service:

```java
ContextHolder.TRACE_ID.set("trace-A");

CompletableFuture<String> answer = service.runAsync();
```

Đây là snippet giải thích hành vi; `ContextHolder`, `service`, hạ tầng Spring và các kiểu import được định nghĩa trong chương trình đầy đủ phía sau.

Nếu `service` là bean Spring có method `@Async("workerExecutor")`, lời gọi qua proxy thường được gửi sang executor:

```text
CALLER THREAD                            WORKER THREAD
--------------------------------        --------------------------------
TRACE_ID.set("trace-A")
TRACE_ID.get() == "trace-A"

call service.runAsync()
    |
    +-- Spring async proxy
    +-- executor.submit(task) ----------> worker nhận task
                                         TRACE_ID.get() == null (*)
                                         chạy thân runAsync()
    |
    +-- caller nhận Future
    |
caller vẫn giữ "trace-A"                 worker có map ThreadLocal riêng

(*) Giả định worker chưa được gắn giá trị cho key đó và ThreadLocal
    không có initialValue tùy chỉnh.
```

`@Async` chủ yếu điều phối **lời gọi phương thức** sang executor. Nó không tự sao chép tất cả thread-local variables, HTTP session state hay transaction từ caller. Tùy framework, một số loại context có wrapper/propagation chuyên biệt, nhưng **không được mặc định** rằng mọi ThreadLocal được chuyển đi.

Còn nếu `@Async` không kích hoạt vì thiếu `@EnableAsync` hoặc self-invocation `this.runAsync()`, thân method có thể chạy ngay trên caller. Lúc đó `ThreadLocal.get()` thấy giá trị caller, nhưng **đó không phải bằng chứng có propagation thành công**: thực tế có thể chưa hề chuyển thread.

### Phân biệt Java `Executor` và Spring `@Async`

- `Executor.execute(...)` nhận một `Runnable` và thực thi theo policy của executor. Có executor chạy trực tiếp trên caller (`Runnable::run`), có executor dùng pool.
- `ExecutorService.submit(...)` thường trả `Future`, nhưng `Future` **không mang** `ThreadLocal` của thread gửi theo hợp đồng.
- `@Async` trong Spring dùng proxy/interceptor để submit lời gọi tới executor, rồi trả completion handle; quy tắc dữ liệu theo thread vẫn như JDK.
- `CompletableFuture.supplyAsync(...)` lập task theo executor mặc định của JDK hoặc executor được truyền. Supplier có thể chạy trên thread không có `ThreadLocal` caller.
- Với callback `thenApply`, `whenComplete`, `handle`, code callback có thể chạy trên thread hoàn tất stage hoặc thread gọi đăng ký callback nếu stage đã hoàn tất. Context của callback phải được xác định theo chính thread thực thi, **không** theo thread đã tạo future lúc đầu.

## 3. Nguy cơ ở thread pool: thiếu context và rò rỉ context cũ

Thread pool **tái sử dụng** worker cho nhiều task:

```text
Request A:
  submit Task A -> worker-1
  Task A: TRACE_ID.set("A")
  Task A: quên remove()

Request B:
  submit Task B -> worker-1
  Task B: TRACE_ID.get() -> "A"  !!! nếu không reset

Request C:
  submit Task C -> worker-1
  Task C: có thể nhìn thấy giá trị để lại từ B
```

Nếu task tự `set` rồi quên cleanup, trạng thái tồn tại trên worker cho tới khi được xóa/thay thế hoặc thread kết thúc. Trong server lâu sống, đây là lỗi khó phát hiện: log của người dùng B có thể mang trace ID của A; với thông tin bảo mật, hậu quả nghiêm trọng hơn.

Hai vấn đề đối xứng:

1. **Không có dữ liệu đúng**: caller có `"B"` nhưng worker có `null` vì không truyền.
2. **Có dữ liệu sai**: worker giữ `"A"` từ task cũ vì không dọn, rồi Task B đọc nhầm.

Một cơ chế propagation đúng cần xử lý **cả hai**: thiết lập snapshot đúng cho task hiện tại, kể cả snapshot là `null`, và khôi phục trạng thái worker trước đó sau task.

Không nên chỉ viết:

```java
executor.execute(() -> {
    TRACE_ID.set(captured);
    doWork();
});
```

Đây là ví dụ thiếu cleanup, không phải mẫu nên dùng. Nếu `doWork()` ném exception, worker vẫn còn binding. Nếu `captured` null và ta muốn xóa binding, gọi `set(null)` chưa thể hiện rõ ý nghĩa remove, và còn có vấn đề khi `ThreadLocal.withInitial` cần tái khởi tạo. Thực hành tốt là dùng `try/finally`.

## 4. InheritableThreadLocal có cứu được không?

`InheritableThreadLocal<T>` là subclass của `ThreadLocal<T>`: khi **tạo một child thread mới**, runtime có thể cho thread đó một **giá trị ban đầu được kế thừa** từ parent tại thời điểm tạo thread. Đây không phải cơ chế “copy mỗi lần submit task”.

Ví dụ thuần Java 17:

```java
InheritableThreadLocal<String> inherited = new InheritableThreadLocal<>();
inherited.set("parent-A");

Thread child = new Thread(() ->
    System.out.println(inherited.get())
);
child.start();
child.join();
inherited.remove();
```

Đoạn này đặt trong method có xử lý `InterruptedException`, chạy thành công sẽ in:

```text
parent-A
```

Vì sao cách này **không phù hợp để truyền request context qua thread pool**?

- Pool worker có thể được tạo từ lâu **trước** request mới, nên nó không nhận giá trị cập nhật ở thread submit.
- Nếu worker tình cờ được tạo khi request A đang active, nó có thể kế thừa `"A"` và **giữ giá trị đó** cho request B/C, trừ khi ứng dụng có cleanup đúng.
- Tạo thread mới hay tái sử dụng thread là quyết định của executor. Không nên thiết kế đúng/sai ngữ cảnh dựa vào timing bất định này.
- Với mutable objects, inheritance có thể sao chép **tham chiếu**, không nhất thiết deep copy; các thread cùng sửa có thể gây race/data leak.
- Một số thread factory có thể chọn không kế thừa inheritable thread locals. Không nên đặt giả định phổ quát khi code chạy trên container hoặc thư viện quản lý worker.

Vì vậy, **đừng** thay `ThreadLocal` bằng `InheritableThreadLocal` như một cách sửa nhanh cho `@Async` hay pool. Tính đúng đắn cần dựa vào propagation theo **task submission**, không theo **thread construction**.

## 5. Truyền tham số tường minh thường là lựa chọn an toàn nhất

Nếu dữ liệu cần dùng được biết ở caller, cách dễ hiểu nhất là đưa nó thành tham số hoặc một request context immutable:

```java
public record JobContext(String correlationId, String tenantId) {}

@Async("workerExecutor")
public CompletableFuture<String> process(JobContext context, String payload) {
    return CompletableFuture.completedFuture(
        context.correlationId() + ":" + payload
    );
}
```

Đây là snippet của một Spring bean, cần `@EnableAsync`, bean `workerExecutor`, import và lời gọi qua proxy. Không phải file độc lập.

**Ưu điểm:** Không cần trạng thái ẩn, có thể đọc đúng thông tin mà task nhận, dễ test, thích hợp với công việc kéo dài qua request và qua message queue. Nếu task chạy sau khi caller hết request, thông tin cần thiết vẫn nằm trong DTO được truyền có chủ đích.

**Lưu ý:** Chỉ truyền dữ liệu cần thiết; không truyền tham chiếu tới HTTP request object, security mutable internals, transaction-bound resource hoặc JPA `EntityManager` sang worker. Khi giá trị của record là một object mutable, record **không tự tạo deep immutability**. Cần xét copy/ownership.

`ThreadLocal` vẫn hữu ích cho những API logging/tracing sử dụng context theo thread mà ta không thể thêm tham số vào mọi method. Khi đó nên thiết kế một bridge rõ ràng qua `TaskDecorator` hoặc wrapper tương đương.

## 6. TaskDecorator: chụp lúc gửi, gắn lúc chạy, dọn lúc kết thúc

Spring cung cấp `org.springframework.core.task.TaskDecorator`, một interface dùng để bọc `Runnable` **trước khi executor thực thi**. `ThreadPoolTaskExecutor` có setter `setTaskDecorator(...)`. Mục đích chính là bổ sung execution context hoặc theo dõi việc thực thi.

Mẫu an toàn cho một `ThreadLocal<String>`:

```java
executor.setTaskDecorator(task -> {
    String captured = ContextHolder.TRACE_ID.get(); // tại thread submit
    return () -> {
        String previous = ContextHolder.TRACE_ID.get(); // tại worker
        try {
            if (captured == null) {
                ContextHolder.TRACE_ID.remove();
            } else {
                ContextHolder.TRACE_ID.set(captured);
            }

            task.run();
        } finally {
            // Khôi phục trạng thái của worker, kể cả khi task thất bại.
            if (previous == null) {
                ContextHolder.TRACE_ID.remove();
            } else {
                ContextHolder.TRACE_ID.set(previous);
            }
        }
    };
});
```

Đây là đoạn cấu hình trong method có `ThreadPoolTaskExecutor executor` và `ContextHolder`, không phải Java file độc lập. Đoạn code đầy đủ ở phần kế tiếp sử dụng đúng nguyên lý.

### Giải thích từng điểm

1. **Lúc decorator được gọi ở thread submit:** `captured` là một snapshot của giá trị cần truyền. Nếu caller đổi `ThreadLocal` ngay sau submit, task vẫn dùng snapshot trước đó.
2. **Lúc wrapper chạy trong worker:** `previous` lưu binding cũ của **worker**, không phải của caller. Điều này giúp xử lý đúng khi có wrapper lồng nhau hoặc executor có context hợp lệ trước đó.
3. **Trước `task.run()`:** set giá trị captured, hoặc remove khi caller không có context. Nhờ vậy task B không nhìn thấy giá trị A để lại.
4. **Trong `finally`:** luôn khôi phục trạng thái worker trước khi wrapper chạy. Không phụ thuộc kết quả thành công hay exception.
5. **Không làm thay đổi caller:** code gắn và cleanup chỉ được chạy trên worker. Caller vẫn tự chịu trách nhiệm cleanup `ThreadLocal` của chính nó khi kết thúc request.
6. **Không tự tăng worker hoặc retry:** decorator chỉ bọc callback, không đổi chính sách queue/threads/rejection và không tự giải quyết lỗi nghiệp vụ.

Nếu muốn `TaskDecorator` luôn để worker sạch ngay cả khi có giá trị `previous` không mong muốn, cần quyết định ownership và yêu cầu từ các framework khác. Trong mô hình bọc callback có khả năng lồng nhau, **khôi phục giá trị trước đó** là cách ít phá hủy ngữ cảnh của lớp bao ngoài. Nhưng trạng thái rác đã có trước khi decorator chạy cần được xử lý từ nguồn phát sinh, không thể lấy “khôi phục previous” làm cách chữa rò rỉ có sẵn.

**Quan trọng khi dùng `submit` / `Future`:** `TaskDecorator` có thể được gọi trên callback wrapper như `FutureTask`, không trực tiếp trên `Runnable` của người dùng. Lỗi từ computation có thể được giữ bên trong `FutureTask` và **không ném ra** từ `Runnable.run()` của decorator. Vì vậy `try/catch` quanh `task.run()` trong decorator **không phải** cơ chế đầy đủ để quan sát task failure. Hãy dùng `Future`, completion callbacks, `AsyncUncaughtExceptionHandler` hoặc logging/metrics có hợp đồng rõ.

## 7. Ví dụ hoàn chỉnh Java 17+ và Spring Framework 6.2

Ví dụ thực hiện ba phép kiểm chứng:

- **Không propagation:** caller có trace `"req-A"`, lời gọi `@Async("plainExecutor")` dùng worker riêng và thấy `null`.
- **Có propagation:** `@Async("contextExecutor")` chạy cùng kiểu công việc nhưng `TaskDecorator` chụp `"req-A"` rồi gắn vào worker; worker đọc đúng.
- **Không rò rỉ qua reuse:** caller đổi context sang `"req-B"`, rồi xóa context; một worker của `contextExecutor` được dùng **ba lần** lần lượt thấy `"req-A"`, `"req-B"` và `null`, không giữ giá trị cũ.

Ta dùng một worker cố định cho mỗi pool và `Future.get(...)` để đảm bảo thứ tự quan sát. Không dựa vào `Thread.sleep()` hoặc sự cạnh tranh thời gian giữa các worker.

### Cấu trúc thư mục

```text
threadlocal-propagation-demo/
├── pom.xml
└── src/main/java/example/ThreadLocalPropagationDemo.java
```

Tạo tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>threadlocal-propagation-demo</artifactId>
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
                    <mainClass>example.ThreadLocalPropagationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/ThreadLocalPropagationDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ThreadLocalPropagationDemo {

    // Chỉ có key dùng chung; mỗi thread giữ giá trị riêng.
    public static class TraceContext {
        static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();
    }

    public record Reading(String traceId, String threadName) {
    }

    public static class WorkService {
        @Async("plainExecutor")
        public CompletableFuture<Reading> plainRead() {
            return CompletableFuture.completedFuture(
                new Reading(
                    TraceContext.TRACE_ID.get(),
                    Thread.currentThread().getName()
                )
            );
        }

        @Async("contextExecutor")
        public CompletableFuture<Reading> decoratedRead() {
            return CompletableFuture.completedFuture(
                new Reading(
                    TraceContext.TRACE_ID.get(),
                    Thread.currentThread().getName()
                )
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean("plainExecutor")
        public ThreadPoolTaskExecutor plainExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("plain-");
            return pool;
        }

        @Bean("contextExecutor")
        public ThreadPoolTaskExecutor contextExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("ctx-");

            pool.setTaskDecorator(task -> {
                // Chụp context từ thread đang submit task.
                String captured = TraceContext.TRACE_ID.get();

                return () -> {
                    String previous = TraceContext.TRACE_ID.get();
                    try {
                        if (captured == null) {
                            TraceContext.TRACE_ID.remove();
                        } else {
                            TraceContext.TRACE_ID.set(captured);
                        }
                        task.run();
                    } finally {
                        if (previous == null) {
                            TraceContext.TRACE_ID.remove();
                        } else {
                            TraceContext.TRACE_ID.set(previous);
                        }
                    }
                };
            });

            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            WorkService service = context.getBean(WorkService.class);

            // Một "request" giả lập đặt ThreadLocal ở caller.
            TraceContext.TRACE_ID.set("req-A");
            try {
                Reading plain = service.plainRead()
                    .get(5, TimeUnit.SECONDS);
                Reading copiedA = service.decoratedRead()
                    .get(5, TimeUnit.SECONDS);

                // Một request khác đi qua cùng worker ctx.
                TraceContext.TRACE_ID.set("req-B");
                Reading copiedB = service.decoratedRead()
                    .get(5, TimeUnit.SECONDS);

                // Caller không có context; worker phải không nhìn thấy
                // giá trị từ hai task trước.
                TraceContext.TRACE_ID.remove();
                Reading withoutContext = service.decoratedRead()
                    .get(5, TimeUnit.SECONDS);

                boolean reusedWorker =
                    copiedA.threadName().equals(copiedB.threadName())
                    && copiedB.threadName().equals(
                        withoutContext.threadName()
                    );

                System.out.println("plainMissing="
                    + (plain.traceId() == null));
                System.out.println("firstCopied=" + copiedA.traceId());
                System.out.println("secondCopied=" + copiedB.traceId());
                System.out.println("afterCallerClearMissing="
                    + (withoutContext.traceId() == null));
                System.out.println("plainPoolUsed="
                    + plain.threadName().startsWith("plain-"));
                System.out.println("contextPoolUsed="
                    + copiedA.threadName().startsWith("ctx-"));
                System.out.println("sameWorkerReused=" + reusedWorker);
                System.out.println("callerClean="
                    + (TraceContext.TRACE_ID.get() == null));
            } finally {
                // Caller thread cũng phải tự dọn context của chính nó.
                TraceContext.TRACE_ID.remove();
            }
        }
    }
}
```

Chạy tại thư mục `threadlocal-propagation-demo` với JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

Tám dòng do **chương trình** in ra theo thứ tự, khi chạy thành công:

```text
plainMissing=true
firstCopied=req-A
secondCopied=req-B
afterCallerClearMissing=true
plainPoolUsed=true
contextPoolUsed=true
sameWorkerReused=true
callerClean=true
```

### Tại sao kết quả này có thể kiểm chứng?

1. Spring context tạo `WorkService` bean, hai `ThreadPoolTaskExecutor` bean và bật `@Async`. `WorkService` là một class không có interface và có public methods, vì vậy lời gọi từ `context.getBean(...)` được async proxy xử lý.
2. Main đặt `"req-A"` trên **ThreadLocal của caller**, rồi gọi `plainRead()`. `plainExecutor` có worker `plain-...`; ThreadLocal **thông thường** không kế thừa từ main, nên `plain.traceId()` là `null`.
3. Gọi `decoratedRead()` trong cùng trạng thái caller. Khi task được submit, `TaskDecorator` của `contextExecutor` chụp `"req-A"`. Worker đặt snapshot, đọc giá trị và trả `Reading("req-A", "ctx-...")`.
4. Main chờ kết quả bằng `get` trước khi đổi giá trị sang `"req-B"`. Lần submit thứ hai chụp `"req-B"`, còn việc dùng lại worker không làm mất snapshot mới.
5. Main gọi `remove()` rồi submit lần thứ ba. Decorator chụp **giá trị không có** (`null`), nên wrapper xóa binding trước khi task chạy. Task đọc `null`, không đọc `req-B` cũ.
6. Vì mỗi pool `core=max=1` và các task được chờ tuần tự, ba task trang trí dùng cùng worker của `contextExecutor`; tên worker bằng nhau.
7. Tên thread được đặt prefix riêng nên hai phép kiểm tra `plainPoolUsed` và `contextPoolUsed` cho `true`. `finally` dọn caller ngay cả khi một lệnh chờ lỗi.
8. Các `println` được gọi **sau khi tất cả future đã hoàn tất**, không in cạnh tranh từ worker, nên stdout có thứ tự cố định.

Nếu môi trường không tải được dependency hoặc task không hoàn tất trước `get(5, SECONDS)`, chương trình báo lỗi thay vì in cả tám dòng; đó là vấn đề chạy trong môi trường, không phải thay đổi nguyên tắc ThreadLocal.

### Tại sao demo dùng một ThreadLocal tự định nghĩa?

Nó cho phép quan sát độc lập với Spring Security, servlet container, logging framework hoặc request scope. Nếu dùng `SecurityContextHolder` hay MDC, thư viện có thể đã có wrapper chuyên biệt hoặc cấu hình context propagation khác, làm việc chẩn đoán phức tạp hơn. Đầu tiên cần hiểu **ThreadLocal cơ bản**; sau đó chọn cơ chế chuyên biệt cho từng loại context.

`TraceContext` trong demo chỉ lưu một chuỗi giả lập, **không** lưu token bí mật hoặc quyền truy cập. Không dùng nguyên mẫu propagation một chuỗi request ID này để tuyên bố đã truyền đầy đủ, an toàn, mọi security context trong hệ thống thật.

## 8. Dọn ngữ cảnh: tại sao phải dùng try/finally?

Trong worker, exception có thể xảy ra ở bất kỳ thời điểm nào:

```java
String old = TRACE_ID.get();
try {
    TRACE_ID.set(captured);
    runPossiblyFailingTask();
} finally {
    if (old == null) {
        TRACE_ID.remove();
    } else {
        TRACE_ID.set(old);
    }
}
```

Đây là snippet, yêu cầu `TRACE_ID`, `captured` và `runPossiblyFailingTask` được định nghĩa ở method. Dù task trả bình thường, ném `RuntimeException` hay có đường code `return` bên trong try, `finally` vẫn được thực thi trong các tình huống Java thông thường.

Nếu wrapper chỉ gọi `TRACE_ID.remove()` trong finally mà quên khôi phục `old`, bạn có thể phá context của một lớp bao ngoài trên chính worker (ví dụ decorator lồng nhau). Nếu wrapper chỉ khôi phục `old` nhưng `old` đã là dữ liệu rác từ task trước, nguồn rò rỉ vẫn cần sửa. Quy tắc thiết kế đúng là **mỗi thành phần chịu trách nhiệm với binding mà nó tự đặt**, còn nơi sở hữu thread pool phải có chính sách tránh stale context.

`ThreadLocal.remove()` rất quan trọng với thread pool lâu sống vì giá trị còn gắn với thread cho đến khi được xóa, thay thế hoặc thread kết thúc. Đối với dữ liệu lớn, quên cleanup vừa gây memory retention vừa có nguy cơ lộ nhầm dữ liệu giữa các request.

### Có nên truyền nguyên object mutable không?

Không nên. Nếu caller chụp một tham chiếu mutable rồi tiếp tục thay đổi nó, worker có thể nhìn thấy state không nhất quán. `TaskDecorator` capture một **reference** không tự tạo snapshot sâu. Ưu tiên truyền giá trị nhỏ, immutable hoặc bản sao rõ ràng. Đặc biệt, tránh để worker giữ tham chiếu tới request-scoped bean, HTTP request đã hoàn tất hoặc data structure gắn với user khác.

## 9. Spring Security: security context là một bài toán riêng

Spring Security thường quản lý `SecurityContext` qua `SecurityContextHolder` với chiến lược gắn context vào thread (mặc định thường sử dụng `ThreadLocal`). Bởi vậy một phương thức `@Async` có thể thấy **khác** security context so với request thread.

Trong hệ thống cần mang authentication sang worker, Spring Security có các adapter như:

- `DelegatingSecurityContextRunnable`
- `DelegatingSecurityContextCallable`
- `DelegatingSecurityContextAsyncTaskExecutor`

Các loại này được thiết kế để thiết lập và dọn `SecurityContext` xung quanh callback, theo hợp đồng của Spring Security. Hãy đọc API tương ứng với phiên bản dự án và lựa chọn context snapshot/ownership đúng. Không tự copy toàn bộ `SecurityContextHolder` theo cách thô sơ, không giữ quyền của người dùng sau khi request kết thúc nếu nghiệp vụ không cho phép, và không kết luận có context là tự động có quyền truy cập hợp lệ ở mọi thời điểm.

**Security là ranh giới tin cậy.** Việc propagating correlation ID cho log không giống việc propagating authentication để ủy quyền tác vụ nền. Với tác vụ kéo dài, có thể phải xác thực lại hoặc dùng một danh tính dịch vụ được cấp quyền riêng thay vì mang security context của HTTP request.

## 10. MDC và correlation ID cho logging

Một trường hợp phổ biến là MDC (Mapped Diagnostic Context) của logging framework. MDC thường được backing bởi thread-local storage, nên log trong `@Async` có thể mất request ID trừ khi có propagation được cấu hình.

Ví dụ nguyên tắc dùng SLF4J MDC:

```java
Map<String, String> snapshot = MDC.getCopyOfContextMap();

return () -> {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        if (snapshot == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(snapshot);
        }

        delegate.run();
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
};
```

Đây là **snippet không độc lập**, cần logging implementation có MDC, `Map`, biến `delegate` và decorator được đặt đúng vào executor. Ý tưởng giống phần 6 nhưng áp dụng lên **toàn bộ map MDC**; cần kiểm tra cơ chế MDC và cách copy của logging provider đang dùng. Chỉ propagate các field phục vụ quan sát, không đưa secret, access token, thông tin nhạy cảm hoặc toàn bộ payload request vào log.

Trong hệ thống dùng OpenTelemetry hoặc Micrometer, tracing context có API và lifecycle riêng; tốt hơn sử dụng instrumentations/context propagation đã được kiểm chứng thay vì tự sao chép nhiều ThreadLocal một cách tản mạn.

## 11. ContextPropagatingTaskDecorator của Spring

Spring Framework cung cấp `org.springframework.core.task.support.ContextPropagatingTaskDecorator` tích hợp với **Micrometer Context Propagation** để hỗ trợ một số execution context, ví dụ tracing observation, khi môi trường có thư viện và context accessors phù hợp.

Ví dụ cấu hình minh họa:

```java
@Bean("observedExecutor")
ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(2);
    pool.setMaxPoolSize(4);
    pool.setQueueCapacity(16);
    pool.setThreadNamePrefix("observed-");
    pool.setTaskDecorator(
        new org.springframework.core.task.support.ContextPropagatingTaskDecorator()
    );
    return pool;
}
```

Đây là cấu hình Spring không độc lập; cần Spring Framework phiên bản hỗ trợ và dependency `io.micrometer:context-propagation` cùng các context accessor cần thiết. Việc cài decorator **không tự bảo đảm mọi ThreadLocal tùy ý được sao chép**, và không được hiểu là sao chép transaction hoặc security state một cách an toàn chỉ vì có thư viện.

Các framework có thể có cách propagation riêng, và instrumentation thêm overhead. Nên chọn đúng tập context cần truyền, benchmark nếu gửi rất nhiều task nhỏ, đồng thời tránh double-propagation khi nhiều decorator/wrapper cùng được áp dụng.

### Giới hạn của propagation tự động

- Chỉ các context được capture bởi cơ chế đã cấu hình mới đi theo task.
- Context có thể **hết hiệu lực** vào lúc task bắt đầu (ví dụ HTTP request đã kết thúc).
- Object mutable được share có thể race, bất kể reference được chuyển đi theo cách nào.
- Truyền security context không đồng nghĩa được phép dùng nó vô thời hạn.
- Không nên capture transaction-bound resources để dùng trên thread khác.

## 12. Transaction, RequestContextHolder và request scope

### Transaction là ngữ cảnh gắn với thread

`@Transactional` của Spring thường sử dụng `TransactionSynchronizationManager` để quản lý các resource/transaction-bound data **trên thread đang thực thi**. Nếu caller mở transaction rồi gọi một method `@Async`, worker **không tự tham gia transaction caller** chỉ vì có annotation hoặc decorator truyền một số ThreadLocal.

```text
Caller thread                             @Async worker
--------------------------------         --------------------------------
@Transactional method
  transaction A / connection A
  |
  +-- submit async task ----------------> method chạy trên thread khác
                                          không tự có transaction A
  |
  +-- caller commit/rollback A
```

Không cố “propagate transaction” bằng cách copy các ThreadLocal nội bộ hoặc chia sẻ JDBC `Connection`/JPA `EntityManager` sang worker. Điều đó phá lifecycle và các giả định về thread-safety của resource. Nếu task nền cần transaction, hãy **mở ranh giới giao dịch riêng ở worker** bằng cấu trúc Spring bean/proxy thích hợp và hiểu thứ tự advice của `@Async`/`@Transactional`.

### Request-scoped object có thể không tồn tại ở worker

`RequestContextHolder` gắn request attributes với thread. Một `@Async` task có thể chạy sau khi HTTP request kết thúc, và worker không được tự đưa vào một request context hợp lệ chỉ từ một tham chiếu cũ.

Các cơ chế inheritable request attributes có thể nguy hiểm với thread pool: worker có thể tồn tại lâu hơn request và bị tái sử dụng cho user khác. Không truyền `HttpServletRequest`, session object hay request-scoped proxy qua worker một cách mù quáng; hãy trích xuất dữ liệu immutable cần thiết trước lúc submit, hoặc thiết kế task nhận DTO rõ ràng.

### HTTP async không đồng nghĩa ThreadLocal tự truyền

Spring MVC có các hợp đồng xử lý HTTP bất đồng bộ riêng. Dù sử dụng một service `@Async`, request thread có thể bị chặn nếu caller lập tức `get()`/`join()`. Với `DeferredResult`, `Callable` hoặc các dạng asynchronous response khác, cần kiểm tra context propagation của **từng lớp**: servlet dispatch, executor, completion callback và rendering response. Đừng coi async HTTP như một thread liên tục giữ nguyên ThreadLocal.

## 13. Thứ tự gọi, callback và nested async

Một task async có thể gửi thêm task khác:

```java
CompletableFuture<Result> stage2 =
    stage1.thenApplyAsync(value -> transform(value), anotherExecutor);
```

Đây là snippet trong method có các biến và kiểu `Result`/`transform`; không phải chương trình độc lập. Callback chạy theo policy của `anotherExecutor`, do đó context mà nó nhìn thấy phụ thuộc thread thực thi **ở chính stage2**.

Ngay cả khi task đầu tiên đã được decorator chuyển trace ID, một bước `thenApplyAsync` đưa sang common pool hoặc executor khác **không có decorator** vẫn có thể mất context. Với callback non-async `thenApply`, callback có thể chạy trên thread làm stage trước hoàn tất hoặc thread đăng ký callback khi stage trước đã done. Không xây code dựa trên kỳ vọng callback luôn có một ThreadLocal nhất định nếu chưa kiểm soát ranh giới thread.

Khi có nhiều executor hoặc các stage gửi qua message broker, lựa chọn thường tốt hơn là **truyền context metadata bằng tham số hoặc message headers**. `TaskDecorator` chỉ giải quyết đường task đi qua executor đã gắn decorator, không phải toàn bộ pipeline qua nhiều hệ thống.

## 14. Bảng sai lầm thường gặp

| Nhận định sai | Vì sao sai | Thay bằng cách nào? |
| --- | --- | --- |
| “ThreadLocal là biến chung của mọi task.” | Giá trị gắn với thread, không gắn task. | Truyền context theo tham số hoặc bọc tại submit. |
| “@Async tự mang mọi ThreadLocal từ caller.” | Async proxy chọn executor, không mặc định clone toàn bộ thread state. | Dùng `TaskDecorator` hoặc wrapper phù hợp. |
| “Worker đọc `null` chứng tỏ @Async lỗi.” | Đó là hành vi ThreadLocal chuẩn trên thread khác. | Kiểm tra thread/qualifier và propagation riêng. |
| “Đổi sang InheritableThreadLocal là đủ.” | Kế thừa lúc tạo thread, không phải mỗi lần pool nhận task. | Snapshot theo task submission. |
| “Một thread pool luôn tạo worker mới cho task mới.” | Worker thường được tái sử dụng lâu dài. | Dọn binding trong `finally`. |
| “Task trước set rồi task sau tự ghi đè là được.” | Task sau có thể không set, hoặc có exception trước lúc set. | Clear cho snapshot absent và restore trong finally. |
| “Dùng `set(null)` luôn tương đương `remove()`.” | Binding vẫn tồn tại; withInitial có khác biệt khi đọc sau remove. | Dùng `remove()` để xóa binding theo hợp đồng. |
| “Decorator sẽ bắt được mọi exception bằng catch.” | FutureTask có thể giữ exception bên trong `Future`. | Quan sát Future/completion hoặc async handler riêng. |
| “Có security context thì có thể dùng vĩnh viễn.” | Quyền có lifecycle, hạn mức và tính hợp lệ riêng. | Dùng cơ chế Spring Security chuyên dụng, kiểm soát ủy quyền. |
| “Có @Transactional ở caller thì worker cùng transaction.” | Transaction-bound resources gắn thread. | Mở transaction của worker, không copy binding. |
| “TaskDecorator của tracing copy mọi ThreadLocal.” | Chỉ những context được đăng ký capture mới có thể propagate. | Cấu hình context accessors và kiểm thử từng loại. |
| “@Async xong thì mọi callback đều cùng worker.” | CompletableFuture có quy tắc executor riêng. | Chỉ rõ executor tại mỗi nhánh async. |
| “ThreadLocal giữ result của request là cách cache.” | Worker reuse có thể giữ nhầm dữ liệu và memory. | Dùng state thuộc request/task hoặc cache có lifecycle riêng. |
| “Kết thúc request thì mọi worker binding biến mất.” | Worker sống lâu hơn request và có thể giữ binding. | Cleanup cả caller và worker; không giữ request object. |

## 15. Checklist khi review một đường @Async

1. **Context nào cần thiết?** Trace ID, tenant ID, MDC, SecurityContext, locale, request metadata hay transaction? Đừng xếp tất cả vào một nhóm có cùng chiến lược.
2. **Giá trị thuộc về ai?** Caller request hiện tại, người dùng, hay một job dài hạn? Có thể hết hạn trước khi task chạy?
3. **Điểm submit nằm đâu?** Đúng bean/executor gắn `TaskDecorator` chưa, hay task đi sang một pool khác/common pool?
4. **Chụp khi nào?** Đã lấy snapshot trước khi caller dọn ThreadLocal chưa? `String`/immutable DTO hay object mutable?
5. **Đặt ở worker lúc nào?** Wrapper phải set trước `task.run()`, kể cả trường hợp snapshot null.
6. **Cleanup thế nào?** Có `finally` để restore/remove, ngay cả khi callback ném lỗi hoặc bị interrupt?
7. **Caller có tự dọn không?** Worker decorator không xóa ThreadLocal ở request thread; servlet filter/interceptor phải quản lý lifecycle riêng.
8. **Có lạm dụng InheritableThreadLocal không?** Pool có worker tái sử dụng và có nguy cơ kế thừa stale context khi tạo worker?
9. **Những context không thể copy là gì?** Transaction/JDBC connection, EntityManager, HttpServletRequest, mutable authentication state, security secret.
10. **Có nhiều stage async không?** `thenApplyAsync`, `@Scheduled`, `@EventListener`, messaging hoặc publisher khác cần xem riêng.
11. **Quan sát lỗi có đúng không?** `TaskDecorator` không phải toàn bộ error handling; Future/CompletableFuture có kết quả/lỗi riêng.
12. **Đã test đồng thời chưa?** Tạo Request A/B, một pool ít worker, kiểm tra không mất context và không rò rỉ; test cả exception, cancellation và shutdown.

## 16. Bài tập tự kiểm tra

**Câu 1.** Thread A gọi `TRACE_ID.set("A")`, rồi gửi task sang một worker của `ThreadPoolTaskExecutor`. Worker có mặc định đọc `"A"` không?

**Đáp án:** Không. `ThreadLocal` chuẩn lưu riêng theo thread; worker chỉ thấy binding của chính nó (thường null nếu chưa set). `@Async` không tự clone binding.

**Câu 2.** Vì sao `InheritableThreadLocal` không giải quyết ổn định propagation qua thread pool?

**Đáp án:** Nó kế thừa khi **thread mới được tạo**, trong khi pool có thể tái sử dụng worker để chạy rất nhiều task của các caller khác. Worker không nhận snapshot mới cho mỗi submit, thậm chí có thể giữ context cũ.

**Câu 3.** Trong ví dụ, tại sao `firstCopied=req-A`, `secondCopied=req-B`, nhưng `afterCallerClearMissing=true` dù cùng worker được dùng lại?

**Đáp án:** Decorator chụp snapshot ở mỗi lần submit, set/remove tương ứng trước `task.run()`, rồi khôi phục worker trong finally. Task sau không nhìn thấy binding trước.

**Câu 4.** Nếu `task.run()` ném exception, khi nào `finally` của decorator được chạy?

**Đáp án:** Khi rời khối try theo quy tắc Java, kể cả exception; wrapper khôi phục/remove context trước khi worker nhận task tiếp theo. Tuy nhiên một `FutureTask` có thể giữ exception trong Future, do đó decorator không nhất thiết nhìn thấy lỗi bằng catch.

**Câu 5.** Có nên copy `TransactionSynchronizationManager` hoặc JDBC connection từ caller sang worker không?

**Đáp án:** Không. Transaction/resource không tự an toàn qua thread; cần ranh giới giao dịch riêng ở worker, không copy ThreadLocal nội bộ.

**Câu 6.** Một callback `thenApplyAsync` được gửi sang executor khác không có decorator. Nó có chắc thấy trace ID từ task trước không?

**Đáp án:** Không. Mỗi ranh giới submit/thread cần cơ chế propagation riêng; trace ID không tự di chuyển giữa các pool.

**Câu 7.** `ThreadLocal.withInitial(() -> "default")` có tự copy value của caller sang worker không?

**Đáp án:** Không. Supplier khởi tạo giá trị cho **thread đang gọi `get`** khi chưa có binding; không copy giá trị từ thread khác.

**Câu 8.** Caller gọi `remove()` sau khi submit có làm task mất snapshot mà `TaskDecorator` đã chụp không?

**Đáp án:** Nếu snapshot là một giá trị immutable độc lập như `String`, không. Wrapper đã giữ giá trị tại thời điểm submit. Nếu snapshot là tham chiếu mutable, việc thay đổi state bên trong object vẫn có thể ảnh hưởng worker.

**Câu 9.** Một `@Async` method thấy `ThreadLocal` của caller vì nó đang chạy trên caller. Điều đó có khẳng định propagation đúng không?

**Đáp án:** Không. Có thể `@Async` chưa được bật, self-invocation bỏ qua proxy, hoặc executor chạy trực tiếp. Cần xác minh worker thread và đường proxy trước khi kết luận.

### Ghi nhớ

`ThreadLocal` gắn **giá trị vào thread**, không gắn **ngữ cảnh vào task**. Với Spring `@Async` và thread pools, một task có thể chạy trên worker khác caller và worker được dùng lại. Khi cần propagation, ưu tiên truyền metadata immutable bằng tham số; nếu API cần thread-bound context thì dùng `TaskDecorator` hoặc wrapper chuyên dụng để **capture ở caller → set ở worker → run → restore/remove trong finally**. Đừng truyền transaction/request/security state mù quáng và đừng nhầm log context với authorization.

### Tài liệu tham khảo chính thức

- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): binding theo thread, `get`, `set`, `remove` và `withInitial`.
- [Java SE 17 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html): kế thừa giá trị tại lúc tạo child thread, không phải lúc submit vào pool.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@EnableAsync`, `@Async` và executor.
- [Spring Framework 6.2.12 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): `setTaskDecorator`, pool, queue và lifecycle.
- [Spring Framework 6.2.12 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/core/task/TaskDecorator.html): bọc callback để đặt context và giới hạn quan sát exception.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html): `ContextPropagatingTaskDecorator` và Micrometer Context Propagation khi thích hợp.
