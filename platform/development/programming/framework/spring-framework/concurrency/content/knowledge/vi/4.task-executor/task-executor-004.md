# Nhận CompletableFuture qua submitCompletable() khi phiên bản Spring hỗ trợ

## Mục tiêu và phạm vi

Trong Spring Framework, `TaskExecutor` cung cấp cách giao công việc cho một executor, còn `AsyncTaskExecutor` mở rộng nó bằng khả năng nộp tác vụ có kết quả. Kể từ **Spring Framework 6.0**, `AsyncTaskExecutor` có hai overload `submitCompletable(...)`, cho phép nhận ngay một `CompletableFuture` để chờ, ghép kết quả, xử lý lỗi và xây dựng chuỗi xử lý bất đồng bộ.

Sau bài này, bạn sẽ:

- Xác định **đúng phiên bản và interface** có `submitCompletable()`.
- Chọn overload `Runnable` hoặc `Callable<T>`, hiểu kết quả `Void`/`T` và cách exception đi vào future.
- Gọi `thenApply`, `thenCombine`, `exceptionally`/`handle` và `join()` đúng mục đích.
- Tạo ví dụ chạy được với `ThreadPoolTaskExecutor`, phân biệt lỗi thực thi và lỗi từ chối nhận task.
- Có phương án tương thích nếu đang dùng Spring Framework **trước 6.0**.
- Hiểu giới hạn của timeout, cancellation, thread pool và context propagation trong ứng dụng Spring.

**Phiên bản dùng để chạy ví dụ:** JDK **17+**, Maven, **Spring Framework 6.1.3**. Chức năng được giới thiệu từ **Spring Framework 6.0**; phiên bản 6.1.3 được chọn để có một tọa độ dependency cụ thể, có thể lặp lại. Nếu dự án dùng phiên bản khác, đọc Javadoc tương ứng trước khi áp dụng.

## 1. Phân biệt TaskExecutor, AsyncTaskExecutor và CompletableFuture

`org.springframework.core.task.TaskExecutor` kế thừa `java.util.concurrent.Executor` và có hợp đồng cốt lõi:

~~~java
void execute(Runnable task);
~~~

`execute` giao tác vụ để thực thi nhưng **không trả kết quả** cho người gọi. `AsyncTaskExecutor` là **interface con** của `TaskExecutor`. Từ Spring 6.0, nó khai báo hai phương thức mặc định:

~~~java
CompletableFuture<Void> submitCompletable(Runnable task);

<T> CompletableFuture<T> submitCompletable(Callable<T> task);
~~~

Các khai báo ở trên là **chữ ký API**, không phải file Java độc lập. Thư viện trả `CompletableFuture` đại diện cho việc tác vụ hoàn tất thành công, thất bại hoặc bị hủy. Việc gọi `submitCompletable` **không chặn để lấy kết quả công việc**; nhưng executor có thể tốn thời gian lúc nộp task do giới hạn/chiến lược từ chối, và việc chờ bằng `join()` hay `get()` sẽ chặn thread gọi đến khi có kết quả.

| Cách nộp | Interface / API | Giá trị trả về | Có chuỗi xử lý `thenApply` được ngay? |
| --- | --- | --- | --- |
| `execute(Runnable)` | `TaskExecutor` | `void` | Không |
| `submit(Runnable)` | `AsyncTaskExecutor` | `Future<?>`, kết quả thành công là `null` | Không trực tiếp |
| `submit(Callable<T>)` | `AsyncTaskExecutor` | `Future<T>` | Không trực tiếp |
| `submitCompletable(Runnable)` | `AsyncTaskExecutor`, **6.0+** | `CompletableFuture<Void>`, kết quả thành công `null` | Có |
| `submitCompletable(Callable<T>)` | `AsyncTaskExecutor`, **6.0+** | `CompletableFuture<T>` | Có |
| `CompletableFuture.supplyAsync(supplier, executor)` | Java 8+ và `Executor` bất kỳ | `CompletableFuture<T>` | Có |

**Đừng nhầm tên interface với khả năng biên dịch:** biến chỉ khai báo `TaskExecutor executor` không có phương thức `submitCompletable` ở **kiểu tĩnh**, ngay cả khi đối tượng thực là `ThreadPoolTaskExecutor`. Hãy khai báo/tiêm `AsyncTaskExecutor` hoặc kiểu triển khai phù hợp.

~~~java
// Minh họa cách chọn kiểu biến (đặt trong class có các import tương ứng).
TaskExecutor basic = pool;
basic.execute(() -> doWork()); // hợp lệ
// basic.submitCompletable(() -> "x"); // không biên dịch: TaskExecutor không có API này

AsyncTaskExecutor async = pool;
CompletableFuture<String> result = async.submitCompletable(() -> "x");
~~~

Đoạn trên chỉ minh họa **kiểu biên dịch**, giả sử `pool` là `ThreadPoolTaskExecutor` và `doWork()` tồn tại ở lớp chứa mã. Không phải chương trình độc lập.

### Kiểm tra phiên bản trước khi gọi

| Phiên bản thư viện Spring Framework | Hành vi cần ghi nhớ |
| --- | --- |
| **5.x** | `AsyncTaskExecutor` có `submit(...)` trả `Future`; **chưa có** `submitCompletable(...)`. |
| **6.0 trở lên** | Có `submitCompletable(Runnable)` và `submitCompletable(Callable<T>)`, cả hai được ghi `Since: 6.0` trong Javadoc. |
| **6.1/6.2** | Hai overload vẫn có; một số phương thức `submit(...)` cũ có default implementation từ 6.1, nhưng điều này **không đổi** mốc của `submitCompletable`. |

Spring Framework 6.x yêu cầu Java 17 hoặc mới hơn. Với dự án Spring Boot, hãy nhìn **phiên bản Spring Framework thực sự được resolve trong dependency tree**, không đoán chỉ dựa trên tên `spring-boot-starter` hoặc một bài viết về Boot.

## 2. Hai overload: Runnable và Callable<T>

### 2.1. `Runnable`: quan tâm trạng thái hoàn tất, không có payload

~~~java
CompletableFuture<Void> saved = async.submitCompletable((Runnable) () -> {
    saveToDatabase();
});

saved.thenRun(() -> notifyUser());
~~~

Đoạn trên là **mã minh họa**: `async`, `saveToDatabase()` và `notifyUser()` thuộc ứng dụng cụ thể. `Runnable.run()` không trả giá trị; khi thành công, `saved.join()` là **`null`**, nên `CompletableFuture<Void>` phù hợp với thao tác ghi dữ liệu, gửi sự kiện hoặc lưu audit log. Ép kiểu `(Runnable)` có thể giúp làm rõ overload với lambda phức tạp; với lambda body chỉ gọi một phương thức `void`, Java thường suy luận được tự nhiên.

### 2.2. `Callable<T>`: task có trả kết quả

~~~java
CompletableFuture<Integer> count = async.submitCompletable(() -> {
    return 21 * 2;
});

CompletableFuture<String> message =
        count.thenApply(value -> "count=" + value);
~~~

Đây cũng là **fragment** trong chương trình có biến `async`. Vì lambda trả `int`, Java suy luận overload `Callable<Integer>` và `T = Integer`; `count.join()` trả `42`, `message.join()` trả `"count=42"`. Khác `Supplier<T>`, `Callable<T>.call()` được phép khai báo **checked exception**; nếu task ném exception, future hoàn tất **exceptionally**.

### 2.3. Đường đi của kết quả

~~~text
Caller
  |
  | async.submitCompletable(callable)
  v
AsyncTaskExecutor -----------------> executor / queue / worker
  |                                      |
  | trả CompletableFuture<T> ngay        | gọi Callable.call()
  v                                      |
Caller làm việc khác                      +-- thành công --> complete(value)
  |                                      |
  +-- thenApply / thenCombine            +-- thất bại ----> completeExceptionally(error)
  |                                      |
  +-- join() / get() <------------------- trạng thái future hoàn tất
~~~

`submitCompletable` chỉ tạo **kênh nhận kết quả**. Nó không hứa rằng task bắt đầu ngay, không tăng số worker vô hạn và không tự cấu hình thread pool. Tốc độ, thread name, hàng đợi và quy tắc từ chối phụ thuộc **executor triển khai**.

## 3. Ví dụ hoàn chỉnh chạy với Maven và Spring Framework 6.1.3

Ví dụ này chạy độc lập với một chương trình `main`, **không cần Spring Boot server**, `@EnableAsync` hay `@Async`. Nó dùng `ThreadPoolTaskExecutor` (thực thi `AsyncTaskExecutor`), cấu hình pool cố định hai worker và hàng đợi hữu hạn.

Cấu trúc dự án:

~~~text
submit-completable-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SubmitCompletableDemo.java
~~~

### 3.1. Tệp `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>submit-completable-demo</artifactId>
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
                    <mainClass>demo.SubmitCompletableDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency `spring-context` mang theo các thư viện Spring cần cho `ThreadPoolTaskExecutor`. Maven tải các dependency từ repository đã cấu hình khi máy có quyền truy cập. Trong ứng dụng Spring hiện có, dùng hệ thống quản lý phiên bản của dự án thay vì tự thêm `spring-context` với một phiên bản khác.

### 3.2. Tệp `src/main/java/demo/SubmitCompletableDemo.java`

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class SubmitCompletableDemo {

    public static void main(String[] args) {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("lesson-");
        pool.initialize();

        try {
            AsyncTaskExecutor executor = pool;

            // Runnable: không có giá trị trả về.
            AtomicInteger counter = new AtomicInteger();
            CompletableFuture<Void> incremented =
                    executor.submitCompletable((Runnable) () -> {
                        counter.incrementAndGet();
                    });

            // Callable: mỗi task trả về một String.
            CompletableFuture<String> first =
                    executor.submitCompletable(() -> "Spring");
            CompletableFuture<String> second =
                    executor.submitCompletable(() -> "CompletableFuture");

            // Ghép hai kết quả độc lập khi cả hai hoàn thành.
            CompletableFuture<String> combined = first.thenCombine(
                    second, (a, b) -> a + " + " + b
            );

            System.out.println("combined=" + combined.join());
            System.out.println("runnable-result=" + incremented.join());
            System.out.println("counter=" + counter.get());

            // Chỉ lỗi trong task; submit vẫn được chấp nhận.
            CompletableFuture<Integer> failed =
                    executor.submitCompletable((Callable<Integer>) () -> {
                        throw new IllegalStateException("demo-failure");
                    });

            int recovered = failed.exceptionally(error -> -1).join();
            System.out.println("recovered=" + recovered);
        } finally {
            // Khi tự tạo pool ngoài Spring container, tự đóng nó.
            pool.shutdown();
        }
    }
}
~~~

Trong thư mục `submit-completable-demo` chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng do **chương trình Java** in ra (không tính log của công cụ xây dựng, nếu có):

~~~text
combined=Spring + CompletableFuture
runnable-result=null
counter=1
recovered=-1
~~~

**Vì sao kết quả ổn định dù task thực thi song song?** `thenCombine` chỉ hoàn tất khi cả hai future đã có giá trị; `combined.join()` đợi kết quả ghép. `incremented.join()` đợi thao tác tăng hoàn tất trước khi đọc `counter`. Future lỗi được `exceptionally` chuyển thành `-1` trước khi in. Thứ tự chạy thực tế của các worker **không được cố định**, chỉ thứ tự các câu `println` trong `main` là cố định.

**Vì sao phải `initialize()` và `shutdown()`?** Đây là executor tạo thủ công. `initialize()` thiết lập executor nội bộ; `shutdown()` kết thúc vòng đời của pool. Khi cùng loại executor được đăng ký làm Spring bean, Spring container quản lý vòng đời cho bean đó.

**Vì sao dùng `AtomicInteger`?** Tác vụ chạy ở thread khác; đối tượng AtomicInteger thể hiện một cách cập nhật an toàn. Ở ví dụ chỉ có một lần tăng, nhưng thói quen dùng cấu trúc thread-safe cho trạng thái chia sẻ vẫn cần được hình thành.

## 4. Kết hợp CompletableFuture sau khi nhận từ submitCompletable

Ưu điểm của `CompletableFuture` so với `Future` thuần là khả năng **xây dựng tiếp các giai đoạn xử lý** thay vì chỉ gọi `get()` để chờ kết quả.

| Phương thức | Vai trò | Ghi chú |
| --- | --- | --- |
| `thenApply(fn)` | Biến đổi kết quả `T → U` sau khi thành công | Callback không phải `Async`, có thể chạy trên thread hoàn tất future hoặc thread đã gọi completion |
| `thenCompose(fn)` | Nối một bước trả về `CompletionStage<U>`; tránh `Future<Future<U>>` | Hữu ích cho các tác vụ phụ thuộc nhau |
| `thenCombine(other, fn)` | Ghép hai task độc lập khi cả hai hoàn thành | Có thể chạy song song nếu executor còn worker |
| `allOf(f1, f2, ...)` | Chờ tất cả future hoàn tất | Future trả về có kiểu `CompletableFuture<Void>`; cần đọc từng kết quả riêng |
| `exceptionally(fn)` | Cung cấp giá trị dự phòng khi chuỗi lỗi | Không chạy khi future thành công |
| `handle((value, error) -> ...)` | Xử lý cả thành công và thất bại | Có thể biến đổi sang một kết quả khác |
| `whenComplete((value, error) -> ...)` | Quan sát/log hoàn tất | Không phải cách chính để phục hồi lỗi; callback tự ném lỗi có thể làm giai đoạn mới lỗi |
| `join()` / `get()` | Đợi và lấy kết quả cuối | Dùng ở ranh giới cần giá trị, hạn chế chặn bên trong worker |

Một đoạn mã minh họa **khi đã có biến `async` kiểu `AsyncTaskExecutor`**:

~~~java
CompletableFuture<Integer> price =
        async.submitCompletable(() -> 100);

CompletableFuture<Integer> tax =
        async.submitCompletable(() -> 10);

CompletableFuture<String> display = price
        .thenCombine(tax, Integer::sum)
        .thenApply(total -> "total=" + total);

System.out.println(display.join()); // total=110
~~~

Không cần gọi `join()` ngay sau khi nộp từng task; nếu làm thế, người gọi sẽ tuần tự chờ và làm mất lợi ích ghép công việc độc lập.

### `thenApply` khác `thenApplyAsync`

`thenApply` không cam kết chọn một executor riêng. `thenApplyAsync(fn)` **không truyền executor** mặc định dùng `ForkJoinPool.commonPool()` theo hợp đồng của `CompletableFuture` trong Java 17 (ngoại lệ runtime theo tài liệu JDK). Nếu muốn stage tiếp tục chạy trên cùng Spring executor, truyền rõ:

~~~java
CompletableFuture<String> next = async
        .submitCompletable(() -> "Spring")
        .thenApplyAsync(value -> value.toUpperCase(), async);
~~~

Đây là fragment với `async` đã tồn tại. Cách này hữu ích khi cần kiểm soát số worker hoặc gắn `TaskDecorator` vào task sau đó; song hãy tránh ép mọi thao tác biến đổi nhỏ sang một thread khác vì mỗi lần scheduling cũng có chi phí.

## 5. Ba nhóm lỗi cần phân biệt

### 5.1. Lỗi trong nội dung Callable/Runnable

Nếu task ném `IOException`, `IllegalStateException` hay exception khác, future **hoàn tất thất bại**, không mang giá trị bình thường. Ví dụ:

~~~java
CompletableFuture<Integer> failed =
        async.submitCompletable((Callable<Integer>) () -> {
            throw new IllegalArgumentException("invalid input");
        });

int value = failed.exceptionally(error -> 0).join(); // 0
~~~

Ở đây ép `Callable<Integer>` làm rõ overload cho lambda chỉ có `throw`. Với `join()` trên future bị lỗi **chưa được phục hồi**, Java thường ném `CompletionException` (unchecked), với `get()` thường là `ExecutionException` (checked); cần xem `getCause()` để xác định lỗi nghiệp vụ ban đầu. `get()` còn có thể ném `InterruptedException`, nên xử lý đúng tín hiệu interrupt.

### 5.2. Executor từ chối nhận task ngay lúc submit

`AsyncTaskExecutor.submitCompletable` được phép ném `TaskRejectedException` **ngay trong lời gọi nộp task** khi executor từ chối (ví dụ pool đã shutdown hoặc quá tải theo cấu hình). Đây là khác biệt lớn với **lỗi xảy ra sau khi task đã được chấp nhận**.

~~~java
try {
    CompletableFuture<String> future =
            async.submitCompletable(() -> "ok");
    // Chỉ có future khi bước submit thành công.
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Ứng dụng quyết định phản hồi quá tải hoặc retry có kiểm soát.
}
~~~

Mã này là fragment trong ứng dụng có `async`. Không giả định mọi lỗi đều đi vào `exceptionally(...)`: nếu quá trình submit **ném exception trước khi trả future**, chưa có future để nối stage. Nếu tạo fallback với `CompletableFuture.failedFuture(ex)`, hãy thực hiện rõ ràng tại tầng API khi chính sách nghiệp vụ cho phép.

### 5.3. Lỗi ở callback phía sau

Ngay cả khi `submitCompletable` thành công, callback `thenApply(...)` hoặc `thenCombine(...)` vẫn có thể ném lỗi. Khi đó **future giai đoạn sau** hoàn tất thất bại. Hãy gắn `exceptionally` hoặc `handle` ở giai đoạn phù hợp; nếu ghi log qua `whenComplete` thì log thêm nguyên nhân nhưng không coi nó tự động phục hồi lỗi.

## 6. Fallback khi phiên bản chưa có submitCompletable()

Trong **Spring Framework 5.x**, `AsyncTaskExecutor.submitCompletable` **không tồn tại**. Nếu thử gọi phương thức, lỗi biên dịch dạng `cannot find symbol: method submitCompletable(...)` là hợp lý. Không sửa lỗi bằng ép kiểu vì việc ép kiểu **không thêm phương thức** vào class của thư viện cũ.

Vì `TaskExecutor` kế thừa `java.util.concurrent.Executor`, có thể dùng phương thức JDK vốn có từ Java 8:

~~~java
// Fragment dùng được với TaskExecutor trong Spring 5.x.
// taskExecutor là một instance TaskExecutor đã được cấu hình.
CompletableFuture<String> withValue =
        CompletableFuture.supplyAsync(() -> "result", taskExecutor);

CompletableFuture<Void> withSideEffect =
        CompletableFuture.runAsync(() -> System.out.println("saved"),
                                   taskExecutor);
~~~

Đoạn này không phải class độc lập; cần import `java.util.concurrent.CompletableFuture` và có biến `taskExecutor`. Tham số thứ hai **rất quan trọng**: nếu gọi `supplyAsync(supplier)` hoặc `runAsync(runnable)` **không truyền executor**, JDK chọn executor mặc định của `CompletableFuture`, thường là common pool, chứ không phải Spring `TaskExecutor` bạn đã cấu hình.

**Khác biệt khi chuyển đổi:** `supplyAsync` nhận `Supplier<T>`, không phải `Callable<T>`; `Supplier.get()` không khai báo checked exception. Nếu tác vụ cần ném checked exception, bạn phải bắt/chuyển đổi ở lambda hoặc thiết kế API cho phù hợp. `runAsync` dùng `Runnable`; cả hai vẫn tạo `CompletableFuture`, nhưng đây là **phương án tương thích**, không phải `submitCompletable` tồn tại trên Spring 5.x.

Ngoài ra, nếu implementation thật là `SyncTaskExecutor`, việc gọi `CompletableFuture.supplyAsync(..., taskExecutor)` có thể **chạy đồng bộ ngay trong caller** vì executor được truyền không có tính bất đồng bộ. Không suy luận concurrency chỉ từ kiểu `CompletableFuture` của kết quả.

## 7. Đưa vào ứng dụng Spring: bean và dependency injection

Trong ứng dụng Spring thực, thay vì `new` executor ở mỗi request, cấu hình nó thành **singleton bean**, sau đó inject bằng interface `AsyncTaskExecutor`.

Tệp `ReportExecutorConfig.java` trong một ứng dụng đã bật Spring component scanning (đoạn minh họa không phải project chạy độc lập):

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ReportExecutorConfig {

    @Bean("reportExecutor")
    public ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("report-");
        return executor; // Spring quản lý initialize/destroy
    }
}
~~~

Tệp `ReportService.java` cùng module:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final AsyncTaskExecutor executor;

    public ReportService(
            @Qualifier("reportExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> buildReport(String reportId) {
        return executor.submitCompletable(
                () -> "report:" + reportId
        );
    }
}
~~~

Hai class trên minh họa cách gắn vào **ứng dụng Spring có sẵn**, không phải chương trình `main` độc lập. Spring container gọi các hook khởi tạo và dọn dẹp bean `ThreadPoolTaskExecutor`. Khi cần nhiều executor, dùng `@Qualifier` hoặc cấu hình chọn bean để bảo đảm dùng đúng pool.

**Khác với `@Async`:** `submitCompletable` gọi API trực tiếp nên **không cần `@EnableAsync`** và không phụ thuộc Spring AOP proxy. `@Async` là cơ chế khác: Spring chặn lời gọi method qua proxy để chuyển sang executor đã cấu hình. Một method `@Async` có thể trả `CompletableFuture`, nhưng không vì thế mà mọi `CompletableFuture` do ứng dụng tạo đều đi qua `@Async`.

**Ngữ cảnh Spring:** transaction, security context, MDC và request context thường gắn với thread hoặc phạm vi riêng. Không mặc định coi mọi context được copy qua task mới. Nếu cần, dùng cơ chế propagation được framework hỗ trợ, `TaskDecorator` hoặc truyền dữ liệu tường minh; dọn dẹp context trong `finally`. Tránh làm DB transaction của thread caller bị hiểu nhầm thành transaction tự động trải sang background thread.

## 8. Những bẫy thường gặp ở production

### 8.1. `join()` chặn và có thể tạo nghẽn pool

Ví dụ có **một worker duy nhất**: task A chạy trong pool, nộp task B vào **cùng pool** rồi gọi `B.join()`; B không có worker để chạy trong khi A giữ worker đợi B. Có thể dẫn đến **thread-starvation deadlock**. Dùng các stage bất đồng bộ như `thenCompose`/`thenCombine` thay cho việc đợi future con bên trong worker, hoặc điều chỉnh kiến trúc/executor.

### 8.2. Timeout của future không tự dừng I/O đang chạy

`future.orTimeout(2, TimeUnit.SECONDS)` làm **future hoàn tất exceptionally** với timeout nếu chưa có kết quả trong 2 giây, nhưng **không bảo đảm** dừng HTTP request, câu lệnh SQL hay Runnable đang tiếp tục. Tương tự, `completeOnTimeout(fallback, ...)` chỉ thay đổi trạng thái future khi quá hạn; business side effects có thể vẫn diễn ra.

`CompletableFuture.cancel(true)` cũng không bảo đảm interrupt thread đang thực hiện tác vụ: hợp đồng `CompletableFuture` xem cancellation như exceptional completion, và cờ `mayInterruptIfRunning` **không có tác dụng ngắt tương đương `FutureTask`**. Cần timeout cho chính HTTP client, JDBC/DB query, và cơ chế hủy tác vụ hợp tác ở tầng tác vụ.

### 8.3. Backpressure và rejection

`CompletableFuture` không làm tăng năng lực pool. Cấu hình `corePoolSize`, `maxPoolSize`, `queueCapacity` và `RejectedExecutionHandler` theo workload, rồi kiểm tra thông lượng, queue length, active count và tail latency. Khi queue đầy, task có thể bị từ chối đồng bộ; gắn `exceptionally` **chỉ ở future** không xử lý được lỗi submit đó.

Với `ThreadPoolTaskExecutor`, pool thường **ưu tiên xếp hàng** khi đã có core workers; chỉ tăng worker đến max khi hàng đợi không nhận thêm task. Vì vậy maxPoolSize lớn nhưng queueCapacity quá lớn có thể không tạo nhiều worker như bạn tưởng.

### 8.4. Callback chạy trên thread nào?

`thenApply` không bảo đảm ở worker Spring đã cấu hình; `thenApplyAsync` không chỉ định executor thường chạy trên `ForkJoinPool.commonPool()`. Khi lựa chọn thread, MDC hoặc giới hạn concurrency quan trọng, truyền executor tường minh cho các phương thức `...Async`.

Việc thread nào thực thi callback cũng phụ thuộc thời điểm future hoàn tất, nên không viết kiểm thử phụ thuộc vào tên thread cho các callback không `Async`.

### 8.5. Lỗi bị che khuất

Nếu nộp task rồi bỏ future, exception có thể **không được quan sát** tại caller. Với `submitCompletable`, lỗi task được phản ánh ở trạng thái future; hãy nối stage xử lý, trả future lên tầng gọi hoặc log/quan sát với trách nhiệm rõ ràng. Không chỉ dựa vào `Thread.UncaughtExceptionHandler` hay log của executor để biết mọi exception từ task do `Future`/`CompletableFuture` quản lý.

## 9. Chọn API cho đúng bài toán

| Nhu cầu thực tế | Gợi ý |
| --- | --- |
| Chỉ cần ra lệnh chạy `Runnable`, không cần theo dõi hoàn tất | `TaskExecutor.execute` |
| Cần chờ và lấy kết quả nhưng không nối callback | `AsyncTaskExecutor.submit` trả `Future` |
| Cần kết quả, ghép nhiều tác vụ, phục hồi lỗi ở chuỗi xử lý; Spring 6.0+ | **`AsyncTaskExecutor.submitCompletable`** |
| Mới có bean kiểu `TaskExecutor` hoặc dùng Spring 5.x | `CompletableFuture.supplyAsync/runAsync(..., taskExecutor)` |
| Muốn method Spring tự chạy qua proxy, có cấu hình `@EnableAsync` | Cân nhắc `@Async` và kiểu trả `CompletableFuture` |
| Tác vụ chủ yếu CPU-bound | Pool giới hạn theo tài nguyên CPU; không chỉ tăng task/future |
| Tác vụ I/O-bound có pool/connection downstream hạn chế | Giới hạn concurrency ở downstream, timeout, backpressure và đo tải |

### Checklist áp dụng

1. Xác minh Spring Framework resolve trong build là **6.0+** và kiểm tra kiểu biến là **`AsyncTaskExecutor`**.
2. Chọn `Callable<T>` khi cần giá trị, `Runnable` khi chỉ cần trạng thái hoàn tất.
3. Đảm bảo executor được khởi tạo/được container quản lý; cấu hình queue, worker và rejection phù hợp.
4. Nối `thenApply`/`thenCombine`/`exceptionally` theo luồng dữ liệu; chỉ `join` ở chỗ thật sự cần đồng bộ.
5. Bắt riêng `TaskRejectedException` ở **thời điểm submit**, và xử lý exception trong task qua future.
6. Có timeout thật ở I/O, hủy tác vụ hợp tác, context propagation và giám sát pool.

## 10. Tự kiểm tra

**Câu 1.** `TaskExecutor executor = new ThreadPoolTaskExecutor();` có thể gọi trực tiếp `executor.submitCompletable(...)` không?  
**Đáp án:** Không, vì kiểu tĩnh `TaskExecutor` chỉ khai báo `execute`. Dùng `AsyncTaskExecutor` hoặc kiểu triển khai phù hợp.

**Câu 2.** Tại sao `CompletableFuture<Void>.join()` trả `null` sau khi task `Runnable` hoàn tất thành công?  
**Đáp án:** `Runnable` không có giá trị trả về. Future dùng để theo dõi việc hoàn tất.

**Câu 3.** Một task đã được chấp nhận nhưng ném exception khác gì pool từ chối lúc nộp?  
**Đáp án:** Exception trong task hoàn tất future thất bại; từ chối nộp có thể ném `TaskRejectedException` trước khi nhận được future.

**Câu 4.** Vì sao `thenApplyAsync(fn)` có thể bỏ qua pool Spring?  
**Đáp án:** Không truyền đối số executor, JDK thường dùng default async execution facility, cụ thể là common pool theo hợp đồng `CompletableFuture` chuẩn.

**Câu 5.** Nếu chạy Spring 5.3, giải pháp tương thích nào vẫn cho phép nhận `CompletableFuture`?  
**Đáp án:** `CompletableFuture.supplyAsync(supplier, taskExecutor)` hoặc `runAsync(runnable, taskExecutor)` với bean `TaskExecutor` đã cấu hình; không gọi API chỉ xuất hiện từ Spring 6.0.

**Câu 6.** `cancel(true)` trên `CompletableFuture` có bảo đảm hủy việc ghi DB đang chạy?  
**Đáp án:** Không. Cancellation của `CompletableFuture` không bảo đảm interrupt tác vụ; cần timeout/cancellation thật tại tầng I/O và nghiệp vụ.

## Tham khảo chính thức

- [Spring Framework 6.1.3 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html): chữ ký hai overload, `Since: 6.0`, return types và `TaskRejectedException`.
- [Spring Framework 6.1.3 — TaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/task/TaskExecutor.html): interface cơ bản chỉ có `execute(Runnable)`.
- [Spring Framework 6.1.3 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): executor, pool/queue, lifecycle và rejection.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor, các implementation và sự khác biệt với `@Async`.
- [Java SE 17 — CompletableFuture Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): completion stage, thread thực thi callback, `join`/`get`, timeout và cancellation.
