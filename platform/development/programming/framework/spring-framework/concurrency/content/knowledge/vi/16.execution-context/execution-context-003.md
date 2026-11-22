# TaskDecorator bao tác vụ để thiết lập và dọn ngữ cảnh

## 1. Vì sao tác vụ bất đồng bộ có thể mất ngữ cảnh?

Trong Spring Framework, lời gọi qua `@Async` hoặc `ThreadPoolTaskExecutor` thường thực thi công việc trên **worker thread khác caller thread**. Điều này làm nảy sinh một lỗi khó nhận biết: caller có request ID trong `ThreadLocal` hoặc MDC để ghi log, nhưng bên trong tác vụ async giá trị lại `null`; ngược lại, một worker tái sử dụng còn giữ ngữ cảnh **của request trước**, gây nhầm log, trace hoặc thậm chí rò rỉ dữ liệu giữa các tác vụ.

`ThreadLocal` gắn dữ liệu **với từng thread**, không gắn với một logical request, một `Runnable` hay một `Future`. Thread pool tái sử dụng worker giữa nhiều tác vụ. Vì vậy, những gì caller thiết lập trên chính thread của nó **không tự xuất hiện** trong worker, và thứ worker từng lưu trước đó cũng không tự biến mất khi task kết thúc.

`TaskDecorator` trong Spring là điểm mở rộng để **bao tác vụ bằng một `Runnable` khác**. Decorator thường được dùng nhằm:

1. **Chụp một snapshot ngữ cảnh phù hợp** ở thread gọi, tại thời điểm executor nhận công việc.
2. **Thiết lập snapshot trên worker** ngay trước khi delegate `Runnable.run()`.
3. **Chạy tác vụ gốc**.
4. **Khôi phục ngữ cảnh worker đã có trước đó, hoặc xóa hẳn nếu ban đầu không có**, trong `finally`, kể cả khi công việc thất bại.

Đây là một mẫu **capture → set → run → restore/clear**, rất quan trọng khi worker được tái sử dụng. Bài này giải thích cơ chế ấy, tích hợp `ThreadPoolTaskExecutor`, minh họa Java 17+ chạy thật, cách dùng MDC, giới hạn bảo mật/transaction và kiểm thử chống rò rỉ ngữ cảnh.

## 2. TaskDecorator là gì, nó nằm ở đâu trong đường đi của tác vụ?

Spring khai báo interface chức năng:

```java
@FunctionalInterface
public interface TaskDecorator {
    Runnable decorate(Runnable runnable);
}
```

Đây là **chữ ký giản lược đúng trọng tâm** của `org.springframework.core.task.TaskDecorator`. `decorate` nhận callback sắp được executor chạy và **trả về một `Runnable` mới**, có trách nhiệm cuối cùng gọi đến `runnable.run()`. Phần quan trọng không phải biến đổi dữ liệu đầu vào, mà là tạo một **execution scope** bao quanh việc thực thi.

Đường đi điển hình:

```text
Caller thread                                   Worker thread của pool
-------------                                   ---------------------
MDC / ThreadLocal có requestId=REQ-7
          |
          v
executor.submit(task)
          |
          v
TaskDecorator.decorate(callback)
          |
          +-- capture requestId="REQ-7"
          |
          +-- return wrapped Runnable ---------+
                                               |
                                        worker lấy callback
                                               |
                                        lưu ngữ cảnh cũ
                                               |
                                        set requestId="REQ-7"
                                               |
                                        callback.run()
                                               |
                                          finally
                                               |
                                        restore / remove
                                               |
                                        worker trở lại pool
```

**Thời điểm quan trọng:** việc chụp ngữ cảnh cần diễn ra **khi submit trên caller thread**; không đợi tới lúc `run()` trên worker mới đọc từ `ThreadLocal`, bởi worker có thread-local riêng. Chức năng của `Runnable` mới trả về là thiết lập snapshot đã chụp lên worker.

Điều này không có nghĩa mọi implementation `TaskExecutor` đều bảo đảm chuyển sang một thread khác. `TaskDecorator` chỉ bao callback được thực thi; thực tế thread nào chạy còn tùy executor. Lợi ích chuyển context rõ nhất ở `ThreadPoolTaskExecutor`, nơi worker tách khỏi caller.

## 3. Ba đối tượng cần phân biệt: caller context, captured snapshot và worker context

Để không ghi đè/để sót dữ liệu, phải tách rõ:

| Đối tượng | Sống ở đâu? | Thời điểm đọc/ghi | Trách nhiệm |
| --- | --- | --- | --- |
| **Caller context** | `ThreadLocal` hoặc MDC trên thread gọi | Có trước khi gửi tác vụ | Cung cấp các giá trị cần truyền |
| **Captured snapshot** | Biến được đóng gói trong decorator `Runnable` | Chụp khi `decorate` được gọi | Lưu giá trị bất biến/độc lập cho đúng task |
| **Worker previous context** | `ThreadLocal` hoặc MDC đã hiện diện trên worker | Đọc ngay trước khi chạy task | Phải được khôi phục ở `finally`, kể cả khi task lỗi |
| **Worker current context** | Context được thiết lập cho task hiện hành | Trong lúc `runnable.run()` | Dành cho log/tracing/logic theo yêu cầu |
| **Cleanup state** | Worker sau task | Sau khi `finally` chạy | Không để lại context của task hiện hành |

Ví dụ worker trước khi chạy task A không có request ID. Khi A chạy, decorator thiết lập `A`. Khi A xong, phải **remove**, không để A tồn tại trên worker để B nhận nhầm. Nếu worker vốn có một context hợp lệ khác (chẳng hạn từ một wrapper ngoài), decorator phải **restore giá trị cũ**, không xóa bừa. Đây là lý do nên có biến `previous` thay vì chỉ gọi `ThreadLocal.remove()` vô điều kiện.

Một snapshot đúng thường là **giá trị**, không phải tham chiếu tới request object mutable. Nếu capture một `Map` có thể bị caller sửa sau khi submit, các task không còn snapshot đáng tin; hãy copy dữ liệu cần thiết hoặc dùng API snapshot chuyên dụng.

## 4. Mẫu TaskDecorator chuẩn: capture khi submit, restore trong finally

Ý tưởng triển khai với `ThreadLocal<String>`:

```java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

TaskDecorator decorator = runnable -> {
    String captured = REQUEST_ID.get(); // Đọc trên caller thread.
    return () -> {
        String previous = REQUEST_ID.get(); // Đọc trên worker thread.
        try {
            if (captured == null) {
                REQUEST_ID.remove();
            } else {
                REQUEST_ID.set(captured);
            }
            runnable.run();
        } finally {
            if (previous == null) {
                REQUEST_ID.remove();
            } else {
                REQUEST_ID.set(previous);
            }
        }
    };
};
```

Đây là **mảnh Java minh họa**, đặt trong class có import `org.springframework.core.task.TaskDecorator` và biến `REQUEST_ID`. Nó thể hiện đầy đủ chính sách cho một context key đơn giản:

- `captured` được đọc **trước khi Runnable được giao cho worker**.
- `previous` được đọc ở **worker** để bảo vệ một scope đã có.
- Nếu caller không có ID, phải xóa ID ở worker cho thời gian chạy task để tránh đọc nhầm request trước.
- `runnable.run()` có thể thành công hoặc ném exception. `finally` chạy trong cả hai trường hợp khi control rời khỏi `try`.
- Sau task, worker trở về context trước đó; nếu ban đầu trống thì trở về trống.

**Không sử dụng mẫu dưới đây:**

```java
// SAI: thiết lập context nhưng quên cleanup/restore.
return () -> {
    REQUEST_ID.set(captured);
    runnable.run();
};
```

Đây là **mảnh phản ví dụ**; worker thread sẽ có thể giữ lại `captured` sau khi chạy xong. Nếu `captured == null`, việc `set(null)` cũng không có ý nghĩa như remove: `ThreadLocal.remove()` rõ ràng loại entry khỏi ThreadLocalMap, phù hợp để tránh giữ tham chiếu không cần thiết trên worker dài hạn.

## 5. Ví dụ Spring Framework 6.2.9 + Java 17+ có thể chạy

Ví dụ sau sử dụng chính `ThreadPoolTaskExecutor.setTaskDecorator` với một worker tái sử dụng. Nó chứng minh ba tình huống:

1. Context `req-169` từ caller được chụp và có mặt khi task đầu chạy.
2. Task thứ hai ném `IllegalStateException`; lỗi được nhận qua `Future.get()`.
3. Sau khi xóa context caller, một task tiếp theo không thấy context cũ. Decorator đồng thời kiểm tra ngữ cảnh worker đã trống **trước khi thiết lập context mới**.

Cấu trúc Maven:

```text
task-decorator-demo/
├── pom.xml
└── src/main/java/demo/TaskDecoratorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>task-decorator-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
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

File `src/main/java/demo/TaskDecoratorDemo.java`:

```java
package demo;

import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class TaskDecoratorDemo {

    private static final ThreadLocal<String> TRACE = new ThreadLocal<>();
    private static final AtomicBoolean WORKER_CLEAN = new AtomicBoolean(false);

    private static TaskDecorator capturedTraceDecorator() {
        return task -> {
            String submittedTrace = TRACE.get(); // Thread nộp task.

            return () -> { // Thread worker chạy đoạn này.
                String previous = TRACE.get();

                // Chứng minh worker không mang context từ task trước.
                if (submittedTrace == null) {
                    WORKER_CLEAN.set(previous == null);
                }

                try {
                    if (submittedTrace == null) {
                        TRACE.remove();
                    } else {
                        TRACE.set(submittedTrace);
                    }

                    task.run();
                } finally {
                    if (previous == null) {
                        TRACE.remove();
                    } else {
                        TRACE.set(previous);
                    }
                }
            };
        };
    }

    public static void main(String[] args) throws Exception {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(4);
        pool.setThreadNamePrefix("worker-");
        pool.setTaskDecorator(capturedTraceDecorator());
        pool.initialize();

        try {
            TRACE.set("req-169");
            Future<String> first = pool.submit(() -> {
                return TRACE.get();
            });
            System.out.println("first = " + first.get());

            TRACE.set("req-fail");
            Future<?> failed = pool.submit(() -> {
                throw new IllegalStateException("boom");
            });
            try {
                failed.get();
            } catch (ExecutionException ex) {
                System.out.println("failure = "
                        + ex.getCause().getClass().getSimpleName());
            }

            TRACE.remove();
            Future<String> second = pool.submit(() -> {
                return String.valueOf(TRACE.get());
            });
            System.out.println("second = " + second.get());
            System.out.println("worker clean = " + WORKER_CLEAN.get());
            System.out.println("caller clean = " + (TRACE.get() == null));
        } finally {
            TRACE.remove();
            pool.shutdown();
        }
    }
}
```

Chạy ở thư mục dự án với Maven và JDK 17 trở lên:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TaskDecoratorDemo
```

Stdout phần chương trình:

```text
first = req-169
failure = IllegalStateException
second = null
worker clean = true
caller clean = true
```

**Giải thích kết quả:**

- Caller đặt `TRACE=req-169` rồi submit. `TaskDecorator.decorate` chụp chuỗi này khi thread gọi giao việc. `first.get()` đợi worker hoàn tất rồi in `req-169`.
- Caller đổi sang `req-fail`. Task thứ hai vẫn được chụp/thiết lập độc lập; nó ném exception. `Future.get()` ném `ExecutionException`; `getCause()` cho biết lỗi gốc `IllegalStateException`.
- Sau task lỗi, `finally` của decorator vẫn khôi phục context worker trước task. Caller xóa `TRACE` rồi submit task thứ ba.
- Vì pool chỉ có một worker và mỗi bước đều được `get()` trước khi gửi bước kế tiếp, task thứ ba chạy trên worker đã xử lý hai task trước. `WORKER_CLEAN` kiểm tra `previous == null` ngay **trước** khi decorator xóa/thiết lập context cho task thứ ba. `true` là bằng chứng cleanup đã hoạt động ở worker được tái sử dụng trong ví dụ này.
- Task thứ ba thấy `TRACE.get() == null`; caller cũng không còn ID. Không có dữ liệu request cũ bị giữ trên worker.

Ví dụ sử dụng Spring Framework 6.2.9 để minh họa API ổn định tại phiên bản đó. Đã thực thi lớp tương đương với các thư viện Spring 6.2.9 trên JShell, kết quả đúng năm dòng trên; điều này kiểm chứng đường chạy chính, còn cấu hình Maven được trình bày như project có thể tái tạo.

`TaskDecorator` là một **callback runtime**, không phải annotation trên nghiệp vụ. Trong chương trình console tự tạo executor, phải gọi `initialize()` trước khi dùng và `shutdown()` khi xong. Với executor được khai báo là Spring bean, container quản lý lifecycle; không nên gọi `shutdown` theo mỗi request.

## 6. Cấu hình TaskDecorator thành Spring bean cho @Async

Trong Spring-managed application, đặt decorator vào bean `ThreadPoolTaskExecutor` để mọi task **được gửi qua chính executor đó** có wrapper. Ví dụ cấu hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncContextConfig {

    @Bean("contextPool")
    public ThreadPoolTaskExecutor contextPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("context-");
        executor.setTaskDecorator(requestIdDecorator());
        return executor;
    }

    private TaskDecorator requestIdDecorator() {
        return task -> {
            String captured = RequestIdContext.get();
            return () -> {
                String previous = RequestIdContext.get();
                try {
                    RequestIdContext.setOrClear(captured);
                    task.run();
                } finally {
                    RequestIdContext.setOrClear(previous);
                }
            };
        };
    }
}
```

Đây là **mảnh cấu hình Spring cần class tiện ích `RequestIdContext` do ứng dụng định nghĩa**; `setOrClear(null)` phải gọi `ThreadLocal.remove()`, không chỉ `set(null)`. Các thông số 4/8/100 là ví dụ, không phải đề xuất mặc định cho production. Khi bean do Spring quản lý, container khởi tạo và dọn executor theo lifecycle của context.

Một service dùng executor đó:

```java
@Service
public class AuditService {

    @Async("contextPool")
    public CompletableFuture<String> writeAudit() {
        String requestId = RequestIdContext.get();
        // Xử lý nghiệp vụ và log theo requestId đã thiết lập trên worker.
        return CompletableFuture.completedFuture(requestId);
    }
}
```

Đây cũng là **mảnh tích hợp Spring**, cần imports `@Service`, `@Async` và `CompletableFuture`. `@EnableAsync` phải bật trong đúng application context, caller phải gọi bean qua Spring proxy (không tự `new` hoặc `this.writeAudit()` trong cùng target), và `@Async("contextPool")` phải chọn bean chứa decorator. Nếu `@Async` chọn executor khác, decorator gắn trên `contextPool` sẽ **không tự đi theo** tác vụ đó.

Trong proxy mode điển hình, interceptor giao callback tới executor khi nhận lời gọi; decorator chụp context từ thread đang submit. Một lời gọi async đã đi qua nhiều tầng executor có thể có **nhiều lần chụp context** tại các ranh giới tương ứng; cần hiểu nơi nào sinh task mới và nơi nào worker đã mang context.

## 7. MDC logging: sao chép bản đồ và dọn đúng scope

Một ứng dụng dùng SLF4J MDC thường đặt `traceId` hoặc `requestId` trên caller thread:

```java
MDC.put("requestId", requestId);
```

`MDC` thường dựa trên context gắn với thread (tùy binding/implementation). Với thread pool, không nên giả định bản đồ MDC của caller tự theo worker. Mẫu decorator minh họa:

```java
TaskDecorator mdcDecorator = task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
};
```

Đây là **mảnh mã tích hợp**, cần SLF4J binding hỗ trợ MDC, imports `org.slf4j.MDC`, `java.util.Map`, `TaskDecorator`; không phải chương trình JDK thuần. `getCopyOfContextMap` trả bản sao bản đồ hiện tại (hoặc null), phù hợp hơn việc giữ reference mutable dùng chung. `MDC.setContextMap` thay thế map trên thread thực thi, nên khôi phục map cũ trong `finally` là bước bắt buộc.

Sử dụng `MDC.clear()` khi không có map vừa bảo vệ request khác, vừa tránh sót thread-local map trên worker. Không chỉ `MDC.remove("requestId")` nếu decorator đã thay đổi **cả map**; nó có thể xóa hoặc giữ sai các key ngữ cảnh khác. Khi ứng dụng có nhiều lớp bọc context, thứ tự capture/restore phải được thống nhất.

**Không sao chép mọi thông tin nhạy cảm vào MDC.** Chỉ đưa ID và thuộc tính log an toàn cần thiết, không đưa password, token, thông tin riêng tư hoặc body request; MDC có thể được log hoặc gửi tới hệ thống quan sát bên ngoài.

## 8. ContextPropagatingTaskDecorator: lựa chọn có sẵn từ Spring 6.1

Spring Framework 6.1+ có class `org.springframework.core.task.support.ContextPropagatingTaskDecorator` hỗ trợ truyền một số execution context nhờ hệ sinh thái **Micrometer Context Propagation**, đặc biệt hữu ích với logging và observation/tracing context.

Ví dụ cấu hình khi đã có những thư viện và context accessors cần thiết:

```java
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

// Trong cấu hình ThreadPoolTaskExecutor:
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

Đây là **mảnh tích hợp**, không phải file Java chạy độc lập. Khi dùng, phải kiểm tra phiên bản Spring tương thích, dependency Micrometer context-propagation và **các ThreadLocalAccessor/context accessors được đăng ký**. Decorator này không thể tự biết mọi `ThreadLocal` tùy ý mà ứng dụng tạo: nếu không có accessor phù hợp, giá trị đó có thể không được capture/restore.

Cơ chế snapshot/scope giúp tránh phải tự viết wrapper cho từng integration thông dụng, nhưng không tự truyền hay sao chép một transaction JDBC đang mở. JavaDoc cũng cảnh báo overhead: với hàng trăm nghìn task cực nhỏ, chi phí chụp/khôi phục context có thể đáng kể; đo trước khi áp dụng đại trà.

Nếu nhiều decorator cần dùng cùng lúc, Spring cung cấp `CompositeTaskDecorator` ở các phiên bản hỗ trợ. Dù tổ hợp nhiều wrapper, vẫn cần hiểu thứ tự thực thi và thứ tự restore; tránh vừa dùng decorator thủ công vừa dùng propagation tự động cho cùng context mà không xác định ai là chủ sở hữu scope.

## 9. Đừng dùng InheritableThreadLocal như cách thay thế per-task propagation

`InheritableThreadLocal` có thể chuyển một giá trị từ thread cha sang thread con **khi thread con được tạo**, nhưng worker của thread pool có thể tồn tại lâu trước khi một request mới được xử lý. Do đó:

- Worker tạo trong request A có thể thừa hưởng một giá trị từ A.
- Worker ấy sau đó phục vụ request B, C, D mà không được tạo lại.
- `InheritableThreadLocal` **không tự cập nhật snapshot cho mỗi lần submit** và có thể gây ngữ cảnh sai/đọng lại.

Đừng dùng thread inheritance để giải quyết context propagation trong pool tái sử dụng. Capture per task và restore sau task phù hợp hơn. Một số executor tạo thread mới theo mỗi task có thể có hành vi kế thừa khác, nhưng điều đó không biến inheritance thành cơ chế rõ ràng hay an toàn cho tất cả executor.

## 10. Ngữ cảnh nào có thể truyền, ngữ cảnh nào không được sao chép tùy tiện?

| Ngữ cảnh | Hướng xử lý | Vì sao |
| --- | --- | --- |
| Correlation ID, request ID | Chụp một chuỗi bất biến, khôi phục sau chạy | Thích hợp cho log/tracing, ít trạng thái |
| MDC Map | Copy snapshot và restore Map cũ | Worker được tái sử dụng; không để sót key |
| Tracing/observation context | Dùng Micrometer Context Propagation/instrumentation tương thích | Cần scope và lifecycle chính xác |
| Spring SecurityContext | Dùng cơ chế truyền SecurityContext được Spring Security hỗ trợ, xác định principal/authorities và cleanup | Tự copy context mutable có thể sai hoặc rò rỉ quyền |
| Transaction JDBC/JPA | **Không** copy `TransactionSynchronizationManager`, `Connection` hoặc `EntityManager` sang thread khác | Transaction imperative và persistence context thường gắn với thread/tài nguyên không thread-safe |
| Servlet request/response | Không mang nguyên `HttpServletRequest`/`Response` sang worker sau khi request scope kết thúc | Container quản lý vòng đời, object có thể không còn hợp lệ |
| Locale/timezone | Nếu cần, truyền giá trị an toàn và restore theo scope | Không tự giả định locale từ caller xuất hiện trên worker |
| Reactor Context | Dùng tích hợp context propagation tương thích Reactor | Reactor có mô hình context khác `ThreadLocal` |
| Credentials/tokens bí mật | Hạn chế tối đa; dùng API/context chuyên dụng khi cần | Nguy cơ dữ liệu nhạy cảm bị giữ trên worker/log |

**Không dùng `TaskDecorator` để “chuyển transaction” bằng cách copy các thread-local nội bộ của Spring.** Spring imperative transaction thường dùng `TransactionSynchronizationManager` gắn tài nguyên với thread; mang một `Connection`/`EntityManager` sang worker khác có thể vi phạm lifecycle và an toàn đồng thời. Nếu worker cần thao tác database, hãy mở transaction **trên worker** thông qua một transactional service/proxy phù hợp.

Ví dụ một service async có thể gọi sang bean khác có `@Transactional` để thiết lập transaction mới trong worker, rồi trả DTO độc lập. Context truyền bằng decorator có thể mang correlation ID phục vụ log, nhưng **transaction boundary vẫn là trách nhiệm riêng**.

## 11. Error handling: decorator không thay thế Future.get()

Một điều tinh tế trong JavaDoc Spring: `TaskDecorator.decorate` có thể được áp dụng lên **callback thực thi nội bộ**, chứ không nhất thiết đúng chính `Runnable`/`Callable` do người dùng truyền vào. Đặc biệt với `submit(...)`, callback thường là một `FutureTask` hoặc wrapper tương tự.

Với `FutureTask`, exception của callable được **ghi vào Future**, không phải luôn ném trực tiếp ra khỏi `Runnable.run()`. Do đó:

```java
return () -> {
    try {
        task.run();
    } catch (RuntimeException ex) {
        // Có thể KHÔNG nhận được lỗi nghiệp vụ nếu task là FutureTask.
        logFailure(ex);
        throw ex;
    } finally {
        restoreContext();
    }
};
```

Đoạn này là **mảnh phản ví dụ về giả định catch được mọi lỗi**, cần `logFailure` và `restoreContext` do ứng dụng định nghĩa. Phần `finally` vẫn là nơi đúng để dọn context, nhưng `catch` quanh `run()` **không phải cơ chế giám sát đáng tin cho mọi lỗi trong task gửi qua `submit`**.

Hãy đọc lỗi qua `Future.get()` (bắt `ExecutionException` rồi kiểm tra `getCause()`), hoặc dùng `CompletableFuture.handle/whenComplete/exceptionally`, `AsyncUncaughtExceptionHandler` với phương thức `@Async void`, hay điểm quan sát phù hợp với API. Ví dụ Spring đầy đủ ở mục 5 chứng minh `failed.get()` nhìn được `IllegalStateException`.

Phân biệt rõ:

- **Lỗi lúc gửi việc/rejection:** executor có thể ném `TaskRejectedException` ngay phía submit/caller.
- **Lỗi khi chạy:** task đã được nhận rồi ném exception; `submit` thường phản ánh qua Future.
- **Lỗi khi cleanup context:** `finally` có thể ném exception riêng; cần thiết kế `restore` đáng tin và không vô tình che mất nguyên nhân nghiệp vụ.

Decorator nên đơn giản, không thực hiện I/O chặn, không nuốt exception của delegate và không phụ thuộc vào việc phải đoán trạng thái Future.

## 12. Cancellation, timeout và queue có thể khiến ngữ cảnh sống lâu hơn dự kiến

Context snapshot được capture khi submit, nhưng task có thể chờ lâu trước khi chạy. Điều đó gây các hệ quả:

1. **Snapshot là giá trị tại thời điểm submit**, không phải trạng thái mới nhất trên caller ở lúc task thật bắt đầu.
2. Một task chờ queue lâu có thể giữ snapshot, bao gồm tham chiếu tới object nếu capture không đúng. Tránh giữ servlet request, session hoặc object lớn.
3. Nếu task bị từ chối khi submit, wrapper có thể đã được tạo nhưng `run()` không được gọi; phải xử lý rejection ở caller. Việc thiết lập context **trên worker** không diễn ra nếu không có worker thực thi.
4. Nếu Future bị hủy **trước khi chạy**, worker có thể chạy một callback Future đã bị cancel mà không thực hiện business logic, hoặc implementation có thể loại khỏi queue; không suy đoán rằng một cleanup worker chắc chắn chạy trong mọi trạng thái. Tránh lưu tài nguyên phải đóng trong snapshot ngay từ đầu.
5. `get(timeout)` chỉ giới hạn lượt chờ của caller, không tự dừng worker hay bảo đảm cleanup đã chạy. `cancel(true)` không cưỡng bức dừng mọi I/O; `finally` chỉ chạy khi luồng thực thi thật sự rời scope.
6. Nếu task tự tạo **một child task** trên executor khác, decorator của pool đầu không tự gắn vào pool thứ hai. Muốn context xuyên suốt qua nhiều boundary, phải có propagation tại mỗi boundary được xác định.

Không nên làm cho decorator phụ thuộc vào request body/HTTP session sau khi request đã kết thúc. Nếu chỉ cần ID/logging, chụp giá trị `String`. Với dữ liệu nghiệp vụ, tạo DTO/value object độc lập có lifecycle và giới hạn rõ.

## 13. Kiểm thử chống rò rỉ ngữ cảnh trên pool tái sử dụng

Một phép test chỉ chạy **một task duy nhất** rồi xác nhận nó thấy request ID là chưa đủ. Vì worker chưa được tái sử dụng, bạn chưa chứng minh cleanup.

Test có giá trị nên:

1. Tạo pool cố định **một worker**, để chắc chắn các task chạy lần lượt trên cùng thread.
2. Caller đặt `requestId=A`, submit task A, đợi kết quả và xác nhận worker thấy A.
3. Caller đặt `requestId=B`, submit task lỗi B, xác nhận exception được truyền về caller và `finally` vẫn xử lý.
4. Caller xóa `requestId`, submit task C; decorator kiểm tra **context hiện hữu trước khi set/clear** trên worker. Nó phải bằng null nếu các task trước đã cleanup đúng.
5. Trong task C, xác nhận request ID không có, và sau C worker vẫn sạch. Khi test có thêm scope lồng nhau, kiểm tra khả năng **khôi phục previous** thay vì luôn clear.
6. Kiểm tra cả nhánh queue đầy/rejection, caller bị interrupt, timeout/hủy, và task chạy lâu.
7. Thử concurrency nhiều request với các ID khác nhau; không thấy một task đọc nhầm ID của task khác và không bị memory/resource retention theo thời gian.

Ví dụ `TaskDecoratorDemo` ở mục 5 làm các bước 1–4 với `AtomicBoolean WORKER_CLEAN`. Không chỉ kiểm tra output của task C, bởi một decorator **bắt đầu bằng `remove()`** có thể che đi việc task A đã để sót context. Cần kiểm tra `previous` ngay trước thao tác thiết lập mới để thực sự phát hiện rò rỉ.

### Kiểm tra log và trace

Khi làm việc với MDC/observability, ghi nhận correlation ID ở caller và worker. Dùng id an toàn, không chứa thông tin nhạy cảm. Quan sát cùng một request qua các log nhưng vẫn cần bảo đảm không có ID của request cũ trong log của request mới. Với trace context, kiểm tra parent–child span relation bằng instrumentation phù hợp; chỉ copy một chuỗi `traceId` vào MDC không tự tạo một span hợp lệ.

## 14. Hiệu năng và giới hạn áp dụng

Decorator được gọi trên đường nộp task và wrapper chạy mỗi lần task thực thi, do đó có overhead:

- Snapshot một map MDC có thể phải copy các key-value mỗi lần submit.
- Restore context tốn thao tác ThreadLocal và có thể giữ nhiều reference nếu thực hiện sai.
- Wrapper nhiều tầng và capture context không cần thiết sẽ tăng chi phí khi tác vụ cực ngắn.
- Context propagation không làm một API chặn trở thành nonblocking, không tăng giới hạn CPU hay database, và không làm dữ liệu mutable thành thread-safe.

Hãy chỉ truyền **ngữ cảnh thật sự cần** cho logging, tracing hoặc business boundary. Nếu mọi task chỉ tính một phép toán rất nhỏ mà không cần request ID, có thể không cần decorator. Nếu task I/O dài và việc giữ correlation ID có ích cho debug, chi phí decorator thường hợp lý nhưng vẫn cần đo.

Khi dùng `@Async`, phải xác nhận executor thực tế được chọn; `setTaskDecorator` trên bean A không tác động các task chạy ở bean B hoặc common pool của `CompletableFuture.supplyAsync` không chỉ định executor.

## 15. Những lỗi thực tế thường gặp

1. **Chụp context ở thời điểm `run()` trên worker.** Lúc đó `ThreadLocal` của caller không tồn tại trên worker; phải capture khi submit.
2. **Không có `finally`.** Nếu task ném exception, context có thể bị bỏ lại trên worker phục vụ request tiếp.
3. **Luôn `remove()` mà không restore previous.** Có thể phá scope do decorator khác đã thiết lập trước đó; phải lưu ngữ cảnh cũ của worker.
4. **Luôn `set(captured)` kể cả khi null.** Nên `remove()` khi không có giá trị để tránh giữ một ThreadLocal entry vô ích.
5. **Truyền tham chiếu mutable thay vì snapshot.** Caller có thể sửa map/list sau submit; task đọc dữ liệu không nhất quán.
6. **Dùng `InheritableThreadLocal` cho thread pool.** Worker tái sử dụng không nhận snapshot mới theo từng request; có thể giữ context cũ.
7. **Chuyển nguyên `HttpServletRequest`, `Connection`, `EntityManager` hay transaction sang worker.** Chúng có scope/thread lifecycle riêng và có thể không an toàn.
8. **Tưởng TaskDecorator bắt được mọi exception khi `submit`.** `FutureTask` có thể giữ lỗi bên trong Future; phải kiểm tra `get()`/handler.
9. **Tưởng TaskDecorator hoạt động trên mọi executor trong ứng dụng.** Nó chỉ áp dụng lên nơi được cấu hình; `@Async` và `CompletableFuture` có thể chọn executor khác.
10. **Tin rằng `ContextPropagatingTaskDecorator` tự biết mọi custom ThreadLocal.** Cần context accessors đã đăng ký và dependency phù hợp.
11. **Chỉ test một request.** Lỗi rò rỉ chỉ lộ khi worker tái sử dụng cho request khác hoặc task trước ném exception.
12. **Chỉ copy ID vào MDC rồi coi như trace propagation.** Log correlation không tự thay thế observation/span context.
13. **Để snapshot giữ credentials/token không cần thiết.** Có nguy cơ rò rỉ dữ liệu và tồn tại lâu trong queue.
14. **Dùng decorator làm nơi mở transaction rồi chuyển resource sang worker khác.** Transaction cần được thiết kế trong đúng thread thực thi, không copy thread-local nội bộ.
15. **Bỏ qua cleanup khi task tự sinh nested async work.** Mỗi boundary cần propagation rõ ràng; cleanup của parent không trực tiếp cleanup child.
16. **Quên lifecycle của pool.** Console demo cần `initialize` và shutdown; Spring bean do container quản lý không nên tự shutdown sau mỗi request.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `ThreadLocal` của caller thường không hiện trong tác vụ chạy trên `ThreadPoolTaskExecutor`?  
**Đáp án:** ThreadLocal gắn với thread, còn worker của pool là thread khác. Cần chụp giá trị tại submission và thiết lập trong worker.

**Câu 2.** Vì sao phải restore `previous` thay vì chỉ gọi `remove()` sau task?  
**Đáp án:** Worker có thể đang ở trong một scope bên ngoài có context hợp lệ. Restore giữ nguyên contract của scope đó; nếu previous null, mới remove.

**Câu 3.** Task ném exception nhưng `TaskDecorator` vẫn cần làm gì?  
**Đáp án:** Chạy cleanup ở `finally`. Với `submit`, lỗi có thể nằm trong Future thay vì được ném trực tiếp từ callback.

**Câu 4.** Dùng `ContextPropagatingTaskDecorator` có tự chuyển transaction JDBC từ caller sang worker không?  
**Đáp án:** Không. Transaction imperative và resource gắn với thread; cần transactional boundary riêng trên worker.

**Câu 5.** Test task A thấy request ID đúng rồi kết luận không rò rỉ, đã đủ chưa?  
**Đáp án:** Chưa. Cần test B/C dùng cùng worker, nhất là sau task lỗi, và kiểm tra previous worker context trước khi setup task mới.

**Câu 6.** Nếu method dùng `@Async("poolA")` nhưng TaskDecorator chỉ gắn trên poolB, có tác dụng không?  
**Đáp án:** Không, trừ khi thực sự có task được giao qua poolB theo đường khác. Phải gắn vào executor đúng đang nhận tác vụ.

**Câu 7.** Khi caller đã đổi request ID sau submit, worker nên thấy ID nào?  
**Đáp án:** Snapshot tại thời điểm `decorate`/submit của chính task, không phải giá trị mới nhất của caller sau đó.

**Ghi nhớ:** với mỗi tác vụ bất đồng bộ, **capture trên caller → set trên worker → chạy delegate → restore/clear trong finally**. Chính bước dọn và khôi phục trên worker tái sử dụng mới giúp propagation vừa hữu ích vừa không làm lẫn ngữ cảnh giữa các request.

### Tài liệu tham khảo

- [Spring Framework — TaskDecorator JavaDoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework — ThreadPoolTaskExecutor JavaDoc và setTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Micrometer — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
