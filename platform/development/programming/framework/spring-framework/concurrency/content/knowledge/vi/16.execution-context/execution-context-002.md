# Nguy cơ dữ liệu ngữ cảnh của tác vụ trước bị dùng lại

## 1. Vấn đề: một request đọc nhầm ngữ cảnh của request trước

Trong Spring Framework, `ThreadPoolTaskExecutor` thường **tái sử dụng worker thread**. Tác vụ A chạy trên worker W, gắn `tenantId=tenant-A` vào `ThreadLocal` hoặc SLF4J `MDC`. Sau khi A xong, W không biến mất: pool dùng lại W để chạy tác vụ B. Nếu A không dọn context, B có thể đọc lại `tenant-A` dù B thuộc `tenant-B` hoặc không có tenant nào. Đây là lỗi **stale execution context** hay *cross-task context leakage*.

Hệ quả có thể nghiêm trọng:

- Log B bị gán `requestId`/`traceId` của A, khiến điều tra sự cố và observability sai.
- Service lọc dữ liệu theo `tenantId` hay `userId` lấy từ thread-local cũ, có nguy cơ lộ dữ liệu chéo tenant hoặc phân quyền sai.
- `SecurityContextHolder` trên worker bị giữ lại `Authentication` của tác vụ khác; logic authorization dựa sai vào user hiện tại.
- Dữ liệu locale, timezone, feature flags, request metadata, audit actor bị dùng lại mà không được xác thực.
- `ThreadLocal` có thể nắm tham chiếu đến object lớn hoặc request-scoped object cho đến khi worker chết; memory retention tăng cùng số worker sống lâu.
- Lỗi chỉ xuất hiện khi **trúng đúng worker đã dùng trước**, nên test một request hoặc test tạo thread mới dễ bỏ sót.

**Nguyên tắc:** task mới không có nghĩa thread mới. Phải xác định ranh giới **capture → install/clear → run → restore/remove** cho từng tác vụ, trên đúng worker thread. Không được dùng `ThreadLocal` hay MDC như một nguồn xác thực duy nhất cho tenant hoặc security.

## 2. Cơ chế: ThreadLocal theo vòng đời thread, không theo vòng đời job

`ThreadLocal<T>` cho mỗi thread một giá trị riêng khi code gọi `set()/get()`. Giá trị đó thuộc **thread hiện tại**, không thuộc HTTP request hoặc đơn vị công việc. `ThreadLocal.remove()` loại bỏ giá trị của chính thread đang gọi; nó không dọn những worker thread khác.

~~~text
Caller request A        ThreadPoolTaskExecutor       Worker pool-1-thread-1
       |                          |                            |
       +---- task A ------------->|------ chạy A ------------>|
       |                          |    tenant.set("tenant-A")  |
       |                          |    process(A)              |
       |                          |    // quên remove()        |
       |                          |<----- task A xong --------|
       |                          |       worker giữ tenant-A  |
Caller request B                 |                            |
       +---- task B ------------->|------ chạy B ------------>|
                                  |    tenant.get() = tenant-A |
                                  |    // nhầm ngữ cảnh A      |
                                  |<----- task B xong --------|
~~~

Nếu hai task chạy **trên hai thread khác nhau**, chúng không tự đọc cùng ô `ThreadLocal`. Lỗi ở đây xuất hiện vì **worker W được sử dụng lại**. Điều này khác với race condition của một field singleton chia sẻ giữa nhiều worker.

Cũng cần phân biệt hai tình huống:

| Tình huống | Worker nhìn thấy | Ý nghĩa |
| --- | --- | --- |
| Caller có `tenant-A`, worker chưa được truyền context | `null` | Thiếu propagation, không phải stale |
| Caller B không có tenant, worker còn giá trị A | `tenant-A` | Stale value, lỗi isolation |
| Caller có `tenant-B`, wrapper chụp B và cài trước khi chạy | `tenant-B` | Propagation đúng khi giá trị đáng tin |
| Caller không có context, wrapper **clear** worker trước khi chạy | `null` | B không nhặt context cũ |
| Sau task, wrapper dọn/restore trong `finally` | Trở lại context thuộc scope trước | Không để context của task này rơi sang task kế |

Một decorator chỉ gọi `MDC.setContextMap(snapshot)` **khi snapshot khác null** sẽ sai: nếu tác vụ sau **không có MDC**, wrapper không set gì, nên worker có thể giữ MDC từ tác vụ trước. Nhánh snapshot null cần có hành động rõ ràng như `MDC.clear()` tại boundary phù hợp.

## 3. Những context nào trong Spring có rủi ro?

| Loại | Cơ chế thường gặp | Rủi ro khi dùng sai |
| --- | --- | --- |
| Application `ThreadLocal` | `ThreadLocal<String>` lưu tenant, job ID, batch metadata | Nhầm tenant/job, memory retention |
| Logging MDC | `org.slf4j.MDC` lưu map `requestId`, `traceId` | Log nhầm request, lộ thông tin và sai truy vết |
| Spring Security | `SecurityContextHolder`, thường `MODE_THREADLOCAL` | Dùng lại `Authentication`/principal của task trước |
| Request context | `RequestContextHolder`, request attributes gắn luồng | Dùng request đã hết vòng đời hoặc sai request |
| Transaction | `TransactionSynchronizationManager` và resource association | Resource/connection/transaction-bound state không hợp lệ |
| Micrometer observation | Scope/context của tracing/metrics | Correlation sai hoặc scope không được close |
| Context từ thư viện tự viết | Locale, timezone, routing, audit | Hành vi nghiệp vụ khác với payload thực |

**Không phải mọi thứ đều tự động propagate.** Khi đi từ servlet request thread sang worker thread, `ThreadLocal` thường không tự theo sang. Ngược lại, khi worker đã **có** giá trị cũ, nó cũng không tự xóa lúc tác vụ trước hoàn thành.

`ThreadLocal.remove()` được gọi trên HTTP caller thread không dọn biến của worker. `MDC.clear()` cũng chỉ dọn MDC của **thread đang gọi**; chỉ gọi ở controller sau khi submit chưa đủ để xóa MDC worker.

## 4. Ví dụ Java 17 độc lập: tái hiện leak có tính quyết định

Ví dụ dùng `Executors.newSingleThreadExecutor` nên các task đều chạy trên **cùng một worker**. `Future.get(timeout)` đợi task trước hoàn tất rồi mới chạy bước tiếp, không dựa vào `Thread.sleep` hay lịch CPU ngẫu nhiên.

### 4.1. ThreadLocalLeakDemo.java

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ThreadLocalLeakDemo {
    private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

    private static <T> T run(
            ExecutorService pool, Callable<T> job) throws Exception {
        return pool.submit(job).get(3, TimeUnit.SECONDS);
    }

    // Capture trên caller, install và restore trên worker.
    private static <T> Callable<T> withTenantContext(Callable<T> job) {
        String captured = TENANT.get();
        return () -> {
            String previous = TENANT.get();
            try {
                if (captured == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(captured);
                }
                return job.call();
            } finally {
                if (previous == null) {
                    TENANT.remove();
                } else {
                    TENANT.set(previous);
                }
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "context-worker"));
        try {
            System.out.println("FIRST=" + run(pool, () -> {
                TENANT.set("tenant-A");
                return TENANT.get(); // Anti-pattern: quên cleanup.
            }));

            // Worker cũ được sử dụng lại: B không có tenant vẫn thấy A.
            System.out.println("LEAKED_IN_SECOND="
                    + run(pool, TENANT::get));

            System.out.println("RESET=" + run(pool, () -> {
                TENANT.remove();
                return TENANT.get();
            }));

            // Cách đúng nếu task sở hữu riêng context của nó.
            System.out.println("SAFE_REQUEST=" + run(pool, () -> {
                TENANT.set("tenant-B");
                try {
                    return TENANT.get();
                } finally {
                    TENANT.remove();
                }
            }));
            System.out.println("AFTER_SAFE=" + run(pool, TENANT::get));

            // Caller có tenant-C, worker không tự nhận tenant-C.
            TENANT.set("tenant-C");
            try {
                System.out.println("NO_AUTO_PROPAGATION="
                        + run(pool, TENANT::get));

                System.out.println("PROPAGATED="
                        + run(pool, withTenantContext(TENANT::get)));

                System.out.println("AFTER_PROPAGATED="
                        + run(pool, TENANT::get));
            } finally {
                TENANT.remove(); // Dọn caller.
            }

            // Một lỗi nghiệp vụ cũng không được bỏ qua cleanup.
            Future<?> failed = pool.submit((Runnable) () -> {
                TENANT.set("tenant-D");
                try {
                    throw new IllegalStateException("boom");
                } finally {
                    TENANT.remove();
                }
            });
            try {
                failed.get(3, TimeUnit.SECONDS);
            } catch (ExecutionException ex) {
                System.out.println("ERROR_CAUSE="
                        + ex.getCause().getClass().getSimpleName());
            }
            System.out.println("AFTER_ERROR="
                    + run(pool, TENANT::get));
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(3, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Lưu file đúng tên, dùng JDK 17+:

~~~bash
javac --release 17 ThreadLocalLeakDemo.java
java ThreadLocalLeakDemo
~~~

Stdout của chương trình:

~~~text
FIRST=tenant-A
LEAKED_IN_SECOND=tenant-A
RESET=null
SAFE_REQUEST=tenant-B
AFTER_SAFE=null
NO_AUTO_PROPAGATION=null
PROPAGATED=tenant-C
AFTER_PROPAGATED=null
ERROR_CAUSE=IllegalStateException
AFTER_ERROR=null
~~~

Lý do kết quả xác định: `newSingleThreadExecutor` chỉ có một worker; các lệnh `run` đợi task trước xong. Khi A quên `remove()`, B đọc tenant-A ngay trên cùng worker. Sau reset, tác vụ B an toàn được bao trong `try/finally` nên lần sau đọc `null`. Context trên caller không tự truyền vào worker; wrapper `withTenantContext` snapshot tại caller, cài trên worker rồi restore. Khi task ném lỗi, `finally` vẫn chạy nên `AFTER_ERROR=null`.

**Chi tiết cần nhớ:** `withTenantContext` restore giá trị `previous` của worker, hữu ích cho nested scope. Nhưng nếu worker đã bị bẩn từ một đoạn code khác thì restore có thể trả nó về **chính giá trị sai**. Vì thế phải bảo đảm boundary hoặc component sở hữu worker dọn sạch từ gốc, không coi “restore previous” là cách chữa mọi leak đã tồn tại.

## 5. Cách xử lý: always cleanup và quản lý ownership

### 5.1. Task tự tạo ThreadLocal thì dọn trong finally

~~~java
// Snippet minh họa bên trong worker; Job và perform do dự án định nghĩa.
void process(String tenant, Job job) {
    try {
        CURRENT_TENANT.set(tenant);
        perform(job);
    } finally {
        CURRENT_TENANT.remove();
    }
}
~~~

`CURRENT_TENANT` là `ThreadLocal<String>` do ứng dụng tạo; `remove()` được thực thi trong chính worker. Dù `perform` ném exception hay return sớm, `finally` vẫn chạy. Không chỉ cleanup trong `catch`: ở đường thành công, `catch` không chạy và context vẫn còn.

### 5.2. Scope lồng nhau cần restore trạng thái cũ

~~~java
// Snippet: trong thread có thể đã có scope cha hợp lệ.
String previous = CURRENT_TENANT.get();
try {
    if (newTenant == null) {
        CURRENT_TENANT.remove();
    } else {
        CURRENT_TENANT.set(newTenant);
    }
    perform();
} finally {
    if (previous == null) {
        CURRENT_TENANT.remove();
    } else {
        CURRENT_TENANT.set(previous);
    }
}
~~~

Mẫu trên chỉ minh họa việc quản lý một `ThreadLocal` do ứng dụng sở hữu. Nếu `T` là object mutable (ví dụ `Map`, `SecurityContext`, `HttpServletRequest`) thì snapshot một **reference** không biến nó thành dữ liệu bất biến. Để task làm việc với user/tenant, ưu tiên truyền scalar ID đã xác thực hoặc immutable DTO thay vì chia sẻ toàn bộ request object.

### 5.3. Xác định ai chịu trách nhiệm cleanup

Có ít nhất ba boundary:

1. **Servlet/security/tracing filter**: tạo và dọn context của HTTP request. Không tùy tiện gọi `MDC.clear()` trong service rồi xóa dữ liệu của filter hoặc tracing framework.
2. **Task executor/decorator**: capture lúc submit, cài hoặc clear trên worker, chạy task và restore hoặc dọn trong `finally`. Bảo vệ giữa **các task**.
3. **Code nghiệp vụ**: nếu tự tạo `ThreadLocal` riêng trong worker, phải dọn chính scope đó, kể cả trường hợp task ném lỗi.

Nếu mỗi lớp tự xóa context của lớp khác, nested scope có thể hỏng; nếu không có lớp nào chịu trách nhiệm, stale context tồn tại qua các task. Hãy chỉ rõ ownership khi thiết kế.

## 6. Spring TaskDecorator: chụp và restore MDC cho mỗi submission

Spring `ThreadPoolTaskExecutor` có `setTaskDecorator(TaskDecorator)` để bao bọc execution callback. Đây là điểm phù hợp để đưa MDC từ caller sang worker **và không để MDC rơi sang tác vụ kế tiếp**. Ta minh họa với SLF4J `MDC.getCopyOfContextMap()` và một snapshot map gồm `String → String`.

### 6.1. Dự án Maven Java 17 + Spring Boot 3.3.5

Cấu trúc:

~~~text
spring-context-isolation/
├── pom.xml
└── src/main/java/com/example/context/
    ├── ContextIsolationApplication.java
    ├── MdcSnapshotTaskDecorator.java
    └── ContextProbe.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>spring-context-isolation</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` bao gồm logging backend phổ biến hỗ trợ SLF4J MDC. Ví dụ là ứng dụng command-line, không cần DB hoặc web server.

### 6.2. MdcSnapshotTaskDecorator.java

~~~java
package com.example.context;

import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

public final class MdcSnapshotTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable delegate) {
        // Capture lúc SUBMIT trên caller, không phải trên worker.
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            // Snapshot scope đã có trên worker để restore.
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    // Thiếu context cũng phải clear, tránh nhặt MDC cũ.
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
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
    }
}
~~~

Ba điều cần kiểm tra trong bất kỳ decorator tương tự nào:

- `captured` được đọc trong `decorate()` vào lúc task được gửi, trước khi chạy trên worker. Nếu đọc `MDC` trong `Runnable.run()` mà không capture trước, đó là **MDC của worker**, không phải MDC của caller.
- Khi `captured == null`, wrapper **xóa MDC trên worker trước khi delegate chạy**. Nếu chỉ set khi snapshot khác null, task không có context có thể thấy giá trị của task trước.
- Cleanup đặt trong `finally`. Snapshot `previous` giúp nested scope khôi phục context có trước; nhưng nếu context đó là dư lượng do component khác bỏ quên, chính component ấy cũng cần được sửa.

Javadoc `TaskDecorator` nói callback nhận được có thể là wrapper của executor, **không phải Runnable gốc do người dùng gửi**. Vì vậy decorator phù hợp quản lý context nhưng không phải điểm duy nhất để bắt lỗi nghiệp vụ của `FutureTask`: exception của `submit` có thể được giữ trong Future, vẫn cần handler theo dõi kết quả.

### 6.3. ContextProbe.java

~~~java
package com.example.context;

import java.util.concurrent.CompletableFuture;
import org.slf4j.MDC;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ContextProbe {
    public record Observed(
            String request, String tenant, String worker) { }

    @Async("contextExecutor")
    public CompletableFuture<Observed> read(String request) {
        return CompletableFuture.completedFuture(new Observed(
                request,
                MDC.get("tenant"),
                Thread.currentThread().getName()));
    }
}
~~~

`ContextProbe` là Spring-managed bean khác với caller. `@EnableAsync` phải bật; gọi `worker.read()` qua proxy, không phải `this.read()` nội bộ. Method trả `CompletableFuture` hợp lệ và ghi lại `MDC.get("tenant")` ngay bên trong worker.

### 6.4. ContextIsolationApplication.java

~~~java
package com.example.context;

import java.util.concurrent.TimeUnit;
import org.slf4j.MDC;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class ContextIsolationApplication {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(ContextIsolationApplication.class, args)) {
            // Runner kết thúc, context được đóng theo lifecycle.
        }
    }

    @Bean("contextExecutor")
    ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("ctx-");
        pool.setTaskDecorator(new MdcSnapshotTaskDecorator());
        pool.setWaitForTasksToCompleteOnShutdown(true);
        return pool;
    }

    @Bean
    ApplicationRunner showIsolation(ContextProbe worker) {
        return args -> {
            ContextProbe.Observed first;
            ContextProbe.Observed second;
            ContextProbe.Observed missing;

            try {
                MDC.put("tenant", "tenant-A");
                first = worker.read("A").get(3, TimeUnit.SECONDS);

                MDC.put("tenant", "tenant-B");
                second = worker.read("B").get(3, TimeUnit.SECONDS);

                MDC.remove("tenant");
                missing = worker.read("C").get(3, TimeUnit.SECONDS);
            } finally {
                MDC.remove("tenant"); // Dọn caller.
            }

            System.out.println("A=" + first.tenant());
            System.out.println("B=" + second.tenant());
            System.out.println("C=" + missing.tenant());
            System.out.println("REUSED_SAME_THREAD="
                    + first.worker().equals(second.worker()));
            System.out.println("WORKER_PREFIX="
                    + first.worker().startsWith("ctx-"));
            System.out.println("CALLER_CLEARED="
                    + (MDC.get("tenant") == null));
        };
    }
}
~~~

Pool được Spring quản lý, có một worker `ctx-*`. `ApplicationRunner` chủ động chờ từng `Future.get(3, SECONDS)` để đưa ra kết quả kiểm chứng xác định; đây **không** phải mẫu controller HTTP nên chờ đồng bộ để gọi đó là background processing. Trong hệ thống thật, trả Future hoặc job ID theo contract và cấu hình timeout/backpressure.

### 6.5. Chạy và stdout

Ở thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua các log khởi động của Spring/Maven, sáu dòng do ứng dụng in:

~~~text
A=tenant-A
B=tenant-B
C=null
REUSED_SAME_THREAD=true
WORKER_PREFIX=true
CALLER_CLEARED=true
~~~

A và B dùng cùng worker vì pool chỉ có một thread. Tuy vậy giá trị trên worker thay theo MDC snapshot tại **từng submission**. Task C không có MDC tenant trên caller, nên decorator clear MDC trước khi chạy và trả `null` thay vì giữ `tenant-B`. Các task được chạy tuần tự trong demo để kết quả có tính quyết định; production có thể có nhiều worker song song.

## 7. Vì sao decorator không có finally vẫn sai?

~~~java
// Anti-pattern: chỉ cài context nếu khác null, không bao giờ dọn.
Map<String, String> captured = MDC.getCopyOfContextMap();
return () -> {
    if (captured != null) {
        MDC.setContextMap(captured);
    }
    delegate.run();
};
~~~

Nếu task A mang `tenant-A`, worker giữ map đó sau A. Task B **không có** context trên caller, nhánh `if` bỏ qua, nên B nhìn thấy tenant-A. Nếu task ném exception, không có cleanup nào được thực hiện. Trong trường hợp context lồng nhau, gọi `MDC.clear()` không điều kiện ở cuối còn có thể phá context do scope cha sở hữu.

Mẫu đúng ở mục 6 **cài map hoặc clear khi vào**, rồi **restore previous hoặc clear khi ra**, luôn trong `finally`. Nhưng nó không được hiểu là “mọi context của mọi thư viện đều an toàn”: decorator chỉ quản lý **MDC map**, không tự propagate Spring Security, transaction, request attributes hoặc mọi `ThreadLocal` ứng dụng.

Có thể dùng `MDC.remove("key")` thay vì `MDC.clear()` khi một lớp chỉ sở hữu một khóa; với một decorator bao trọn MDC snapshot, restore map giúp bảo toàn scope hợp lệ. Cần thiết kế ownership cho cả hai đầu.

## 8. ContextPropagatingTaskDecorator từ Spring Framework 6.1

Spring Framework 6.1+ có `org.springframework.core.task.support.ContextPropagatingTaskDecorator` cho các context được hỗ trợ qua **Micrometer Context Propagation**. Thư viện có thể snapshot và khôi phục observation/logging context khi worker chạy.

Snippet cấu hình trong một `@Configuration`, **không phải project độc lập**:

~~~java
@Bean("observedExecutor")
ThreadPoolTaskExecutor observedExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(32);
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

Cần import `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator` và `@Bean`; ứng dụng cần dependency `io.micrometer:context-propagation` tương thích, cùng `ThreadLocalAccessor` đã đăng ký cho các loại context muốn truyền.

**Không suy luận rằng mọi ThreadLocal tự được truyền** chỉ vì dùng class trên. Phải xác nhận đúng accessor/registry và test thực tế. Thư viện cũng có chi phí capture/restore, không đáng áp dụng mù cho hàng triệu task cực nhỏ. Với một số giá trị đơn giản, explicit immutable payload (`tenantId` đã xác thực, `jobId`, `correlationId`) rẻ hơn và minh bạch hơn.

Cũng không nên cài đồng thời nhiều decorator tự quản cùng một MDC mà không hiểu thứ tự install/restore; chúng có thể ghi đè hoặc khôi phục sai scope.

## 9. Spring Security: tránh sử dụng Authentication của tác vụ trước

`SecurityContextHolder` mặc định thường dùng `ThreadLocal`. Trong servlet request, Spring Security filter chain quản lý thiết lập và dọn context ở ranh giới request. Nhưng trên thread pool custom, code `@Async` không tự được bảo đảm nhận đúng SecurityContext của caller, cũng không được phép đọc context cũ nếu task trước làm bẩn worker.

Anti-pattern (snippet, không dùng để ra quyết định phân quyền):

~~~java
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
// Worker bị bẩn có thể trả auth của tác vụ trước.
~~~

Spring Security có `DelegatingSecurityContextRunnable` và các wrapper như `DelegatingSecurityContextAsyncTaskExecutor` để cài context cho từng task rồi dọn theo scope. Snippet dưới đây chỉ minh họa cấu hình:

~~~java
@Bean("securedExecutor")
AsyncTaskExecutor securedExecutor(
        @Qualifier("rawAsyncExecutor") AsyncTaskExecutor raw) {
    return new DelegatingSecurityContextAsyncTaskExecutor(raw);
}
~~~

Cần import `org.springframework.core.task.AsyncTaskExecutor`, `org.springframework.beans.factory.annotation.Qualifier`, `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`, `@Bean`; bean `rawAsyncExecutor` và các dependency Spring Security phải tồn tại. Constructor không nhận `SecurityContext` cố định dùng context được capture theo submission; overload có context cố định sẽ dùng một principal đã chỉ định cho mọi task, chỉ phù hợp với service account có chủ đích.

Lưu ý:

- `SecurityContext` có thể chứa `Authentication` và object mutable; capture reference không làm nó immutable. Không chia sẻ rồi mutate đối tượng ấy tùy tiện giữa các thread.
- Một task không có quyền người dùng **không được** kế thừa principal của task trước; yêu cầu quyền phải được kiểm tra lại ở tầng service/DB.
- Nếu chỉ cần `userId` hoặc `tenantId` đã kiểm tra để làm việc nền, truyền DTO bất biến thường an toàn hơn truyền cả `HttpServletRequest`/session.
- Security context propagation không đồng nghĩa business authorization: tenant trong payload vẫn cần so khớp với quyền thực.
- `SecurityContextHolder.clearContext()` dọn context của thread đang gọi; đừng nghĩ gọi trên caller dọn được worker.

**Không dùng `MODE_INHERITABLETHREADLOCAL` như bản sửa cho thread pool.** `InheritableThreadLocal` nhận giá trị của parent **lúc tạo thread**, không phải lúc submit mỗi task. Một worker lâu sống có thể bị “thừa kế” dữ liệu từ request A khi sinh ra, rồi tiếp tục chạy request B/C; đó chính là stale value. Hơn nữa giá trị mutable có thể bị chia sẻ tham chiếu.

## 10. Transaction và RequestContext: không cố propagate theo cách thủ công

### 10.1. @Transactional và resource gắn theo thread

Spring quản lý transaction/resource association theo thread (ví dụ thông qua `TransactionSynchronizationManager`). Khi task chuyển sang một worker khác, transaction của caller **không tự đi theo**. Không copy `EntityManager`, `ConnectionHolder` hoặc JDBC connection từ HTTP thread vào worker: những resource này có vòng đời và thread-safety riêng.

Nếu worker cần transaction, mở boundary `@Transactional` trong service được gọi qua Spring proxy **trên worker thread**. Khi job dispatch trước commit và cần dữ liệu đã commit, dùng after-commit hook/outbox hoặc thiết kế ordering khác phù hợp. Nếu thư viện custom tự `bindResource` vào worker, nó phải `unbindResource` chính xác; code chuẩn nên để Spring transaction interceptor lo lifecycle.

### 10.2. RequestContextHolder

`RequestContextHolder` gắn request attributes vào thread của servlet request. Worker chạy lâu hơn request không được phép giữ `ServletRequestAttributes` hoặc `HttpServletRequest` rồi dùng sau khi request đã kết thúc. Những giá trị cần thiết nên được trích xuất **trước lúc submit** thành payload rõ ràng.

Snippet Java 17:

~~~java
record JobEnvelope(
        String jobId,
        String tenantId,
        String initiatedBy,
        String correlationId) { }
~~~

Các ID trong `JobEnvelope` phải được lấy từ nguồn đã xác thực và không chứa dữ liệu nhạy cảm thừa. Record là dữ liệu bất biến ở mức tham chiếu tới `String`, có thể truyền qua executor hoặc lưu vào job store; ThreadLocal trong JVM không thể thay thế durable job state cho multi-pod/restart.

## 11. Những đường kết thúc thường bị bỏ sót

| Đường kết thúc | Điều cần làm |
| --- | --- |
| Thành công | `finally` cleanup, giữ hoặc truyền kết quả theo contract |
| Exception | `finally` vẫn chạy; Future/handler nhận lỗi nghiệp vụ |
| Return sớm | Cleanup phải ở `finally`, không chỉ nhánh success |
| Timeout caller | `Future.get(timeout)` chỉ dừng **đợi**, worker có thể tiếp tục chạy và giữ context cho tới khi xong |
| Cancel task chưa chạy | Wrapper chưa vào worker nên chưa cài context; vẫn phải dọn job state/handle ở caller |
| Cancel task đang chạy | Interrupt chỉ là yêu cầu, không bảo đảm dừng ngay; dùng `finally` khi worker thoát |
| Submission rejection | Task không chạy, có thể không có Future trả về; catch `TaskRejectedException`/`RejectedExecutionException` |
| Shutdown | Queue có thể còn task chưa chạy; xử lý Future/job ledger riêng, cleanup thread-local không đủ |
| Nested async | Mỗi executor cần propagation boundary và scope hợp lệ riêng |
| `CompletableFuture.supplyAsync` mặc định | Có thể dùng `ForkJoinPool.commonPool()`, không áp dụng decorator của pool Spring khác |

Thời gian chờ ngắn ở HTTP caller không tự xóa MDC đang nằm trên worker. Khi task bị treo I/O, cả context lẫn resource có thể còn giữ cho đến khi task thật sự thoát, vì vậy cần timeout ở chính network/DB và chính sách cancellation thực tế.

## 12. Kiểm thử lỗi reuse và nguyên tắc fail-closed

### 12.1. Test có ít nhất hai tác vụ trên đúng một worker

Một test chỉ gửi một task không chứng minh isolation. Nên:

1. Tạo executor core=max=1 hoặc `newSingleThreadExecutor`.
2. Gửi A gắn `tenant-A` rồi kết thúc (trong bản lỗi, quên cleanup).
3. Đợi A qua Future có timeout; gửi B **không đặt tenant**.
4. Trước khi sửa, B sẽ đọc tenant-A. Sau khi sửa, B phải nhận null hoặc bị từ chối rõ ràng vì thiếu context.
5. Gửi C với `tenant-C` để kiểm tra propagation/cleanup. Gây exception bên trong C; gửi D để bảo đảm D không còn context C.
6. Bổ sung nested scope, cancellation, rejection và shutdown để cover mọi đường kết thúc.

Dùng `CountDownLatch`/barrier khi test nhiều worker song song, không dựa vào `Thread.sleep` và trùng hợp scheduling. Nếu test bằng `SyncTaskExecutor` chạy inline, nhiều lỗi thread-local sẽ không xuất hiện vì caller thread xử lý trực tiếp; cần ít nhất một test bằng executor tái sử dụng thread thực.

### 12.2. Test end-to-end đúng yêu cầu bảo mật

- Giả lập hai principal/tenant khác nhau và một request thiếu tenant trên cùng worker; xác minh DB query/authz không dùng principal/tenant cũ.
- Test log với `requestId` khác nhau: dòng của job B phải mang B hoặc null đúng contract, tuyệt đối không mang A.
- Nếu một bean có `@Async`, gọi từ **bean khác qua proxy**; `this.asyncMethod()` có thể bypass proxy khiến test đang chạy inline thay vì trên pool.
- Kiểm tra tất cả executor thật dùng trong ứng dụng, gồm `@Async`, `@Scheduled`, event listeners bất đồng bộ và CompletableFuture với executor chỉ định.
- Với nhiều worker, test high-load để phát hiện reuse dưới race/rejection; với một worker, test xác định đường leak.

### 12.3. Chỉ check tenant != null có đủ không?

Không. Nếu worker B có **stale tenant-A**, câu điều kiện `tenant != null` vẫn đúng. Quyết định truy vấn/authorization phải dựa trên **tenant đã xác thực gắn với job B**, không dựa vào một giá trị thread-local chưa được xác minh.

~~~java
// Snippet minh họa; tenantContext, repository là thành phần ứng dụng.
String actualTenant = tenantContext.currentTenant();
if (!job.verifiedTenantId().equals(actualTenant)) {
    throw new SecurityException("Unexpected tenant execution context");
}
repository.findByTenantIdAndOrderId(job.verifiedTenantId(), job.orderId());
~~~

`job` cần là object chứa verified tenant từ boundary an toàn; nếu không có context hợp lệ thì từ chối (fail closed). Tốt hơn nữa, truyền verified tenant trực tiếp vào service/repository để tránh phụ thuộc context ngầm trong logic bảo mật.

## 13. Lỗi phổ biến và checklist

| Triệu chứng | Nguyên nhân | Sửa đúng |
| --- | --- | --- |
| Log B mang requestId của A | MDC chưa dọn trên worker | Capture map lúc submit, install/clear và restore trong `finally` |
| Tenant B nhầm A | `ThreadLocal` còn giá trị của task trước | Worker cleanup, kiểm tra tenant đã xác thực |
| User B được xử lý bằng Authentication A | SecurityContext chưa dọn đúng | DelegatingSecurityContext wrapper, clear/restore đúng ownership |
| Test dev không thấy lỗi | Không ép reuse worker | Test một worker và nhiều task nối tiếp |
| Task không có MDC vẫn thấy MDC | Decorator chỉ set khi snapshot non-null | Khi snapshot null, clear worker |
| `@Async` chạy nhưng request context mất | Chuyển sang thread khác, chưa có propagation | Trích xuất ID bất biến, dùng integration phù hợp |
| `@Transactional` của caller không có trong worker | Transaction thread-bound | Tạo transaction trong worker qua Spring service |
| `MDC.clear()` ở service xóa cả tracing scope cha | Xóa context của thành phần không thuộc ownership | Snapshot previous và restore tại boundary |
| `InheritableThreadLocal` dùng sai user | Giá trị thừa hưởng lúc tạo worker, không theo task | Propagation theo từng submission |
| Task timeout nhưng context chưa biến mất | Worker vẫn chạy dù caller đã timeout | Timeout I/O và cleanup khi worker thật sự thoát |
| Chỉ pool A có decorator | Pool B hoặc commonPool bypass decorator | Audit mọi executor/scheduler/callback boundary |
| Lộ thông tin dù log context đúng | Log context không phải cơ chế authorization | Kiểm tra quyền và tenant tại nghiệp vụ/DB |

**Checklist trước khi merge:** (1) Có nhận diện mọi context dùng `ThreadLocal`/MDC/SecurityContext không? (2) Ai sở hữu cleanup? (3) Có xử lý snapshot null ở worker? (4) Có `finally` cho success/failure? (5) Có truyền mutable security/request/session object không? (6) Có truyền transaction/EntityManager sai luồng không? (7) Có test nhiều task trên một worker và task thiếu context? (8) Có test exception, timeout, cancellation và overload? (9) Có đảm bảo mọi executor cần propagation đều dùng cùng chiến lược? (10) Có cơ chế fail closed với tenant/user không hợp lệ?

## 14. Câu hỏi tự kiểm tra

1. Vì sao `ThreadLocal` không phải “một biến cho mỗi HTTP request”?
2. Task B không set tenant nhưng thấy tenant-A: đó là lỗi propagation hay stale reuse?
3. Gọi `MDC.clear()` trên controller có dọn được MDC của `ThreadPoolTaskExecutor` worker không?
4. Vì sao decorator phải **clear khi captured null**, không chỉ set khi có giá trị?
5. Nếu task A ném exception sau khi set context, vì sao `finally` quan trọng?
6. Một TaskDecorator MDC có tự truyền Spring SecurityContext và transaction không?
7. `MODE_INHERITABLETHREADLOCAL` có cập nhật context mỗi lần pool nhận task mới không?
8. Nếu `CompletableFuture.supplyAsync` dùng commonPool, decorator gắn vào `contextExecutor` có được gọi không?
9. Tại sao timeout từ `get(3, SECONDS)` không chứng minh worker đã dọn context?
10. Có stale tenant-A nhưng `tenant != null` là true: cần kiểm tra và thiết kế authorization thế nào?

**Kết luận:** worker thread thường sống lâu hơn từng task. Để tránh dùng lại ngữ cảnh cũ, phải **capture theo từng submission, cài hoặc clear trước khi chạy, restore/remove trong finally trên worker**, và kiểm thử hai tác vụ nối tiếp trên cùng thread. Propagation phục vụ tính nhất quán của execution context; authorization phải dựa vào dữ liệu đã xác thực, không phụ thuộc một giá trị thread-local không được kiểm chứng.

## Tài liệu tham khảo chính thức

- [Java SE 17 — ThreadLocal, set/get/remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
- [Spring Framework 6.2 — TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework 6.2 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework — Observability and context propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html)
