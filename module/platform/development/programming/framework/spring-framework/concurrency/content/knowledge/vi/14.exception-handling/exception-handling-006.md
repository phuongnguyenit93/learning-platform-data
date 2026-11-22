# Phân biệt phục hồi bằng giá trị thay thế với chỉ quan sát lỗi trong Spring Framework

## Mục tiêu

Khi một lời gọi bất đồng bộ thất bại, ta thường muốn **ghi log/đo lỗi** hoặc **cung cấp giá trị thay thế** để bước sau tiếp tục. Hai mục đích này khác nhau: ghi nhận lỗi không tự làm kết quả thành công, còn trả fallback có thể biến một future thất bại thành future thành công. Trong Spring Framework, đặc biệt với phương thức `@Async` trả `CompletableFuture<T>`, sự khác biệt này quyết định caller nhận giá trị hay ngoại lệ.

Bài tập trung vào ba API của Java `CompletableFuture`/`CompletionStage`:

- **`whenComplete((value, error) -> ...)`**: quan sát kết quả hoặc lỗi, thực hiện side effect như log/metrics; nếu action kết thúc bình thường, stage trả về giữ **cùng kết quả hoặc lỗi** của stage nguồn.
- **`exceptionally(error -> fallbackValue)`**: chỉ chạy khi nguồn hoàn tất ngoại lệ; tạo stage mới **thành công với giá trị thay thế** nếu hàm phục hồi trả về bình thường.
- **`handle((value, error) -> newValue)`**: chạy với cả thành công và thất bại, có thể đổi kiểu hoặc giá trị cho **cả hai nhánh**, cũng có thể phục hồi một lỗi.

Sau bài này, bạn có thể giải thích luồng lan truyền lỗi, chọn operator đúng mục đích, dự đoán giá trị trả về của chuỗi stage, hiểu khi nào fallback vô tình che giấu lỗi, và thử một ví dụ **Java 17+ + Spring Framework 6.2.x** chạy được bằng Maven.

**Quy tắc ngắn:** `whenComplete` để **nhìn thấy** lỗi; `exceptionally` hoặc `handle` để **quyết định kết quả sau lỗi**. Một callback có ghi log chưa hẳn là xử lý phục hồi.

## 1. Trước tiên phân biệt lỗi của task và lỗi khi submit

Trong ứng dụng Spring, một service có thể được đánh dấu:

```java
@Async("lessonExecutor")
public CompletableFuture<String> fetch(String key) {
    String value = remoteCall(key);
    return CompletableFuture.completedFuture(value);
}
```

Đây là **mã minh họa chưa chạy độc lập**: cần Spring bean, `@EnableAsync`, executor `lessonExecutor` và `remoteCall` do ứng dụng định nghĩa. Khi gọi qua Spring AOP proxy, method thực thi trong worker của executor đã chọn. Caller nhận future để quan sát sự hoàn tất.

Có ít nhất hai ranh giới lỗi:

1. **Submit thất bại:** không tìm được executor, pool đã đóng hoặc queue đầy dẫn đến `TaskRejectedException`. Lỗi này có thể xảy ra ngay khi caller gọi phương thức qua proxy, **trước khi có future để gắn** `exceptionally` hay `whenComplete`. Cần bảo vệ ranh giới submit nếu muốn bắt lỗi này.
2. **Task đã được nhận, sau đó thất bại:** `remoteCall` ném exception trong worker hoặc target trả một future thất bại. Với phương thức `@Async` trả `CompletableFuture`, hạ tầng Spring phản ánh lỗi vào **future của caller**. Từ đây, các toán tử của `CompletableFuture` mới có cơ hội xử lý kết quả bất đồng bộ.

Lưu ý `@Async void` không trao future cho caller, vì vậy không thể gọi `whenComplete` hoặc `exceptionally` trên một kết quả không tồn tại. Spring hỗ trợ `AsyncUncaughtExceptionHandler` để quan sát lỗi không được trả qua future cho loại method này.

## 2. Phân biệt trạng thái nguồn với kết quả cuối theo nghiệp vụ

Các trạng thái success, exceptional và cancellation đã được giải thích trong bài ba toán tử CompletionStage. Ở đây, câu hỏi là **caller có được phép diễn giải một fallback như thành công nghiệp vụ không?**

| Trạng thái nguồn | Quyết định nghiệp vụ | Thông tin không được mất |
| --- | --- | --- |
| Thành công với dữ liệu hợp lệ, có thể là `null` theo contract | Dùng dữ liệu gốc | Nguồn và chất lượng dữ liệu thực. |
| Lỗi transient, có cache đủ mới | Có thể trả fallback | Lỗi backend, tuổi cache và cờ `degraded`. |
| Lỗi validation, quyền hoặc toàn vẹn dữ liệu | Giữ failure | Mã lỗi phù hợp và nguyên nhân để điều tra. |
| Timeout/cancellation trong khi I/O có thể còn chạy | Không mặc định thành công hay đã dừng task | Trạng thái chưa rõ, deadline và khả năng đối soát. |

Hai stage cùng hoàn thành bình thường không nhất thiết có cùng ý nghĩa: một chứa dữ liệu từ primary, stage kia chứa dữ liệu thay thế. Thiết kế domain outcome để thể hiện sự khác biệt.

## 3. Quan sát là một ranh giới telemetry, không phải hành động phục hồi

`whenComplete((value, error) -> ...)` thích hợp ghi nhận kết quả/lỗi nguồn mà vẫn giữ trạng thái stage nếu callback chạy bình thường. Khi định nghĩa chính sách, hãy tách ba sự kiện:

- `primary_failed`: nguồn thật sự lỗi trước khi fallback.
- `fallback_used`: hệ thống đã chấp nhận và dùng dữ liệu dự phòng.
- `final_failed`: kết quả cuối vẫn không đáp ứng hợp đồng.

Một observer chỉ đặt **sau** `exceptionally` đã phục hồi sẽ thấy stage thành công và có thể bỏ sót outage của nguồn. Nếu observer cần thuộc về kết quả caller nhận, phải giữ/trả stage do `whenComplete` tạo; bỏ stage này có thể bỏ luôn lỗi của callback quan sát.

Handler logging/metrics nên nhanh, không block và không ném lỗi không kiểm soát. Nếu nguồn thành công nhưng observer lỗi, stage phụ thuộc có thể thất bại vì chính observer; cần test điều kiện này.

## 4. Fallback phải có hợp đồng chấp nhận rõ ràng

`exceptionally(error -> fallbackValue)` tạo stage mới thành công nếu handler trả giá trị bình thường; **nó không tự gửi lại request**. Trước khi triển khai, cần quyết định:

1. Loại lỗi nào được phép fallback? Dữ liệu gợi ý giao diện có thể dùng cache; thanh toán và kiểm tra quyền không được trả success giả.
2. Dữ liệu thay thế có còn hợp lệ theo TTL, tenant, version hoặc giới hạn stale-data không?
3. Caller có biết nguồn dữ liệu suy giảm qua flag hoặc Outcome không?
4. Lỗi gốc và mức sử dụng fallback có được log/đo riêng hay đã bị che?
5. Nếu cache miss hoặc lỗi không thuộc loại cho phép, stage có giữ failure đúng nguyên nhân không?

Không dùng `exceptionally(ex -> null)` một cách đại trà nếu `null` không được định nghĩa là giá trị hợp lệ: điều đó có thể chuyển backend failure thành một NPE rất muộn. Cần phân loại exception và duy trì cause phù hợp.

## 5. Dùng handle để công bố nguồn và chất lượng kết quả

`handle((value, error) -> outcome)` chạy trên cả hai nhánh, cho phép trả kiểu domain rõ ràng về **kết quả thật, kết quả suy giảm hoặc thất bại**.

Đoạn Java 17 sau nằm trong method đã có biến `source` kiểu `CompletableFuture<String>`:

~~~java
record LookupOutcome(String value, boolean degraded, String errorCode) {}

CompletableFuture<LookupOutcome> result =
        source.handle((value, error) -> error == null
                ? new LookupOutcome(value, false, null)
                : new LookupOutcome("cached-value", true, "BACKEND_UNAVAILABLE"));
~~~

Ở đây nhánh lỗi giả định cache luôn hợp lệ **chỉ để minh họa hình dạng dữ liệu**; production phải kiểm tra loại lỗi và cache trước khi cho fallback. Stage trả `LookupOutcome(degraded=true)` là success về Future nhưng chứa kết quả suy giảm về nghiệp vụ. Consumer cần đọc các trường đó.

Nếu không có fallback hợp lệ, giữ exceptional completion hoặc biểu diễn `Outcome.failure` đúng contract. Dùng `handle` chỉ để ghi log rồi `return null` sẽ làm mất giá trị thành công và có thể che lỗi; `whenComplete` phù hợp hơn cho quan sát thuần túy.

## 6. Quyết định operator theo trách nhiệm nghiệp vụ

| Mục đích ở boundary | Operator | Dấu hiệu cần kiểm chứng |
| --- | --- | --- |
| Đếm lỗi nguồn nhưng vẫn để caller biết lỗi | `whenComplete` trước phục hồi | Observer thấy failure gốc, stage vẫn exceptional. |
| Dùng cache cho một lỗi transient được cho phép | `exceptionally` | Stage mới trả fallback hợp lệ và metric phân biệt cache. |
| Chuyển cả success và failure sang domain result | `handle` | Outcome có error/status/degraded rõ ràng. |
| Đo kết quả cuối sau mọi phục hồi | `whenComplete` sau phục hồi | Metric phản ánh outcome cuối, không giả là lỗi backend. |
| Fallback phải gọi API async khác | `exceptionallyCompose` | Stage phụ thuộc chờ nguồn dự phòng mà không `join` blocking. |

Trong ví dụ sau, cả ba nhánh xuất phát từ **cùng một Future lỗi** để quan sát riêng failure nguồn, fallback và kết quả đã ánh xạ. Điều đó rõ hơn việc chỉ nhớ chữ ký operator.

## 7. Ví dụ Spring Framework chạy được: cùng một lỗi, ba nhánh khác nhau

Chương trình dưới đây chạy với **Java 17+**, Maven và **Spring Framework 6.2.12**. Ta tạo Spring `@Async` service có một nhánh nghiệp vụ cố ý thất bại, rồi từ **cùng future nguồn** tạo ba nhánh:

- `observation = source.whenComplete(...)` để đếm số lần thấy lỗi.
- `recovery = source.exceptionally(...)` để trả fallback `"cache:B"`.
- `handled = source.handle(...)` để trả `"handled:B"` khi lỗi, nhưng cũng biết xử lý success.

Ta cũng gửi một lời gọi thành công để chứng minh `exceptionally` **không thay** giá trị thành công.

Để output xác định, callback chỉ cập nhật `AtomicInteger` chứ không in từ worker; `main` đợi các future hoàn tất rồi mới in theo thứ tự cố định. Không cần `Thread.sleep` hay dựa vào lịch chạy ngẫu nhiên.

### Cấu trúc

```text
async-error-recovery-demo/
├── pom.xml
└── src/main/java/example/AsyncErrorRecoveryDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-error-recovery-demo</artifactId>
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
                    <mainClass>example.AsyncErrorRecoveryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/example/AsyncErrorRecoveryDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncErrorRecoveryDemo {

    public static class LookupService {
        @Async("lessonExecutor")
        public CompletableFuture<String> lookup(String key) {
            if ("bad".equals(key)) {
                throw new IllegalStateException("Backend unavailable");
            }
            return CompletableFuture.completedFuture("remote:" + key);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public LookupService lookupService() {
            return new LookupService();
        }

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("lesson-");
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            LookupService service = context.getBean(LookupService.class);
            AtomicInteger observedErrors = new AtomicInteger();

            // Một invocation @Async cố ý thất bại trên worker.
            CompletableFuture<String> source = service.lookup("bad");

            // Nhánh 1: chỉ ghi nhận; không đổi lỗi thành success.
            CompletableFuture<String> observation = source.whenComplete(
                (value, error) -> {
                    if (error != null) {
                        observedErrors.incrementAndGet();
                    }
                }
            );

            // Nhánh 2: phục hồi lỗi bằng giá trị đã được cho phép.
            CompletableFuture<String> recovery = source.exceptionally(
                error -> "cache:B"
            );

            // Nhánh 3: xử lý cả success và failure.
            CompletableFuture<String> handled = source.handle(
                (value, error) ->
                    error == null ? "handled:" + value : "handled:B"
            );

            // Trường hợp thành công: exceptionally giữ value gốc.
            CompletableFuture<String> healthy = service.lookup("OK");
            CompletableFuture<String> successWithFallback =
                healthy.exceptionally(error -> "cache:OK");

            // Chờ từng stage trước khi in để stdout có thứ tự ổn định.
            String recoveredValue = recovery.get(5, TimeUnit.SECONDS);
            String handledValue = handled.get(5, TimeUnit.SECONDS);
            String healthyValue = successWithFallback.get(5, TimeUnit.SECONDS);

            boolean observerStillFailed = false;
            try {
                observation.get(5, TimeUnit.SECONDS);
            } catch (ExecutionException expected) {
                observerStillFailed = true;
            }

            System.out.println("sourceFailed="
                + source.isCompletedExceptionally());
            System.out.println("observedErrors=" + observedErrors.get());
            System.out.println("observerStillFailed=" + observerStillFailed);
            System.out.println("recoveredValue=" + recoveredValue);
            System.out.println("handledValue=" + handledValue);
            System.out.println("healthyValue=" + healthyValue);
        }
    }
}
```

Chạy tại thư mục `async-error-recovery-demo` (có JDK 17+ và Maven):

```bash
mvn -q compile exec:java
```

Khi chương trình chạy thành công, sáu dòng **do ứng dụng in ra** theo đúng thứ tự:

```text
sourceFailed=true
observedErrors=1
observerStillFailed=true
recoveredValue=cache:B
handledValue=handled:B
healthyValue=remote:OK
```

### Diễn giải từng dòng

1. `sourceFailed=true`: `lookup("bad")` ném `IllegalStateException` trong worker. Spring proxy phản ánh lỗi vào `CompletableFuture<String>` mà caller nhận, nên source hoàn tất ngoại lệ.
2. `observedErrors=1`: `whenComplete` thực thi đúng một lần cho lần hoàn tất lỗi của source. `AtomicInteger` giúp công bố phép đếm an toàn giữa các thread; sau `observation.get`, `main` đã chờ callback này xong.
3. `observerStillFailed=true`: stage `observation` **vẫn ném `ExecutionException`** khi `get`, bởi action quan sát không làm fallback.
4. `recoveredValue=cache:B`: nhánh `exceptionally` nhận lỗi và trả về một `String`, làm stage recovery hoàn tất bình thường.
5. `handledValue=handled:B`: nhánh `handle` đọc `error != null` nên chọn nhánh phục hồi.
6. `healthyValue=remote:OK`: lời gọi `lookup("OK")` thành công; `exceptionally` không chạy, vì thế giữ nguyên value nguồn.

**Quan trọng:** `source`, `observation`, `recovery` và `handled` là những stage khác nhau, dù có cùng nguồn. `recovery` thành công **không viết lại** trạng thái failure của `source`, và `observation` không tự được chữa lỗi khi `recovery` thành công. Output không dựa vào thứ tự giữa worker và caller; chương trình chờ có timeout rồi in từ thread `main` theo thứ tự cố định.

Spring `@EnableAsync` và tên executor nằm trên cấu hình thực sự; `LookupService` được container quản lý và không tự gọi `this.lookup(...)`. Các phương thức/chữ ký phù hợp với Spring AOP proxy. Khi môi trường không tải được dependency hoặc tác vụ không hoàn tất trong hạn 5 giây, chương trình có thể báo lỗi thay vì có sáu dòng trên; đó không phải thay đổi hợp đồng của operator.

## 8. Thứ tự nối các operator làm đổi lỗi được quan sát

Đây là phần quan trọng nhất khi triển khai hệ thống cần vừa giám sát vừa fallback.

### Quan sát trước khi phục hồi

```java
CompletableFuture<String> answer = source
    .whenComplete((value, error) -> {
        if (error != null) {
            metrics.countBackendFailure();
        }
    })
    .exceptionally(error -> "cache");
```

Đây là snippet trong ứng dụng có `source` và `metrics`; không độc lập. `whenComplete` thấy **lỗi gốc** để cập nhật chỉ số. `exceptionally` phía sau nhận lỗi và chuyển thành `"cache"` nếu cần. `answer` là một stage thành công khi fallback thành công.

### Phục hồi trước rồi mới quan sát

```java
CompletableFuture<String> answer = source
    .exceptionally(error -> "cache")
    .whenComplete((value, error) -> {
        if (error != null) {
            metrics.countBackendFailure();
        }
    });
```

Nếu lỗi nguồn đã được `exceptionally` chuyển thành fallback thành công, callback sau đó nhận `error == null` và không đếm lỗi backend. Nếu mục tiêu giám sát là tỷ lệ lỗi thật của backend, thứ tự này **che mất nguyên nhân ở tầng quan sát sau phục hồi**.

Điều đó **không** có nghĩa operator phía sau không bao giờ thấy lỗi: nếu fallback tự ném exception hoặc stage khác ném lỗi, `whenComplete` phía sau có thể thấy lỗi mới. Hãy định nghĩa rõ metric là “backend failures”, “fallback used”, “final request failures” hay “user-visible failures”; chúng không đồng nhất.

### Minh họa pipeline

```text
Backend failure
     |
     +--> whenComplete(log backend failure)
                   |
                   v
             exceptionally(cache)
                   |
                   v
             SUCCESS("cache") ----------> caller

Backend failure
     |
     +--> exceptionally(cache)
                   |
                   v
             SUCCESS("cache")
                   |
                   v
             whenComplete(log final outcome)
                error == null ----------> caller
```

Trong thực tế nên đo **cả lỗi nguồn lẫn tỷ lệ dùng fallback**. Caller nhận được kết quả thay thế không có nghĩa backend đang khỏe hoặc không cần điều tra.

## 9. Nếu chỉ muốn ghi log nhưng giữ thất bại, làm thế nào?

Sử dụng `whenComplete` và **trả stage đó**, không biến lỗi thành giá trị:

```java
return service.lookup(key)
    .whenComplete((value, error) -> {
        if (error != null) {
            logger.error("Async lookup failed for key={}", key, error);
        }
    });
```

Snippet này nằm trong phương thức có `service`, `key`, logger; không độc lập. Nếu source lỗi, stage trả về vẫn lỗi (khi logging không ném lỗi). Caller vẫn có thể dùng `get()`/`join()` hoặc exception mapping ở controller để thấy thất bại.

Đừng dùng:

```java
return service.lookup(key)
    .handle((value, error) -> {
        if (error != null) {
            logger.error("Failed", error);
        }
        return null;
    });
```

Đoạn này chỉ minh họa lỗi thiết kế, cũng không chạy độc lập. `handle` trả null cho **cả success và failure**, khiến caller nhận future thành công với `null`; vừa mất value bình thường vừa nuốt nguyên nhân lỗi. Với API `Result<T>`, điều này có thể dẫn tới `NullPointerException` ở tầng sau và làm mất ngữ cảnh sự cố ban đầu.

Nếu muốn *lựa chọn* tiếp tục ném lỗi sau khi dùng `handle`, cần ném lại đúng cách (có thể dùng `CompletionException`) và hiểu rằng stage mới khi ấy vẫn failed, không phải recovered. Đơn giản hơn, dùng `whenComplete` cho mục đích quan sát.

## 10. Fallback có điều kiện: chỉ phục hồi lỗi được chấp nhận

Không phải mọi lỗi đều đáng được biến thành success. Ví dụ: backend không truy cập được có thể cho phép cache, nhưng invalid credentials, vi phạm quy tắc nghiệp vụ, dữ liệu không nhất quán hay error bảo mật có thể phải được truyền lên.

```java
CompletableFuture<String> controlled = source.exceptionally(error -> {
    Throwable root = error;
    while (root instanceof java.util.concurrent.CompletionException
            && root.getCause() != null) {
        root = root.getCause();
    }

    if (root instanceof TransientBackendException) {
        return "stale-cache-value";
    }

    throw new java.util.concurrent.CompletionException(root);
});
```

Đây là snippet minh họa, `TransientBackendException` là loại lỗi do ứng dụng định nghĩa. `CompletionException` có thể bọc nguyên nhân khi stage bất đồng bộ truyền lỗi; các implementation có thể tạo wrapper khác, nên phân loại cần được kiểm thử với chính pipeline của dự án. Không coi mọi `Throwable` là transient. Nếu fallback thất bại, ném lỗi từ handler khiến stage mới failed thay vì âm thầm trả null.

Với nghiệp vụ nhạy cảm, nên dùng result type có metadata:

```java
record LoadResult(String value, boolean fallbackUsed) {}

CompletableFuture<LoadResult> result = source.handle(
    (value, error) -> error == null
        ? new LoadResult(value, false)
        : new LoadResult("cached", true)
);
```

Đoạn trên là snippet Java 17 (cần `source` có kiểu `CompletableFuture<String>`). Nếu giá trị dự phòng không được chấp nhận cho lỗi hiện tại, handler phải **truyền tiếp lỗi** thay vì cứ dùng `"cached"`.

## 11. Fallback bất đồng bộ: `exceptionallyCompose` khác `exceptionally`

`exceptionally` yêu cầu callback trả **giá trị `T`**; nếu fallback bản thân cần gọi một API async khác, có thể dùng `exceptionallyCompose` (có trong Java 17) để lấy một `CompletionStage<T>` rồi “làm phẳng” nó.

Ví dụ:

```java
CompletableFuture<String> answer = primary.loadAsync(key)
    .exceptionallyCompose(error -> secondary.loadAsync(key));
```

Đây là snippet kiến trúc; cả `primary` và `secondary` phải cung cấp API trả `CompletableFuture<String>` hoặc stage tương thích, và cần thiết kế timeout, hạn mức, idempotency phù hợp. Tác vụ secondary chỉ được gọi khi primary thất bại. Nếu secondary cũng thất bại, stage tổng cũng thất bại, trừ khi có bước phục hồi khác.

**Đừng** viết một fallback chặn thread chỉ để lấy async value:

```java
CompletableFuture<String> answer = primary.loadAsync(key)
    .exceptionally(error -> secondary.loadAsync(key).join());
```

Đoạn này minh họa anti-pattern khi chạy trong pool nhỏ hoặc hệ thống có nhiều I/O. Callback `.join()` có thể chiếm thread cho đến khi secondary hoàn tất, làm giảm throughput hoặc tạo deadlock nếu secondary cần cùng worker. `exceptionallyCompose` giữ dạng chuỗi async rõ hơn.

Nếu fallback cần chuyển sang executor khác để làm công việc nặng, cân nhắc `exceptionallyAsync(fn, executor)` hoặc `exceptionallyComposeAsync(fn, executor)` theo API Java 17, không giả định callback non-async tự chọn pool riêng.

## 12. `whenCompleteAsync`, `handleAsync` và luồng callback

Các biến thể thường dùng:

| API | Callback được gọi ở đâu? | Khi nên dùng |
| --- | --- | --- |
| `whenComplete(action)` | Có thể chạy ở thread hoàn tất stage hoặc thread đăng ký/hỗ trợ completion nếu stage đã done. | Quan sát nhẹ, không blocking. |
| `whenCompleteAsync(action)` | Chuyển action qua executor async mặc định của stage/JDK. | Muốn action được lập lịch async nhưng chấp nhận executor mặc định. |
| `whenCompleteAsync(action, executor)` | Chạy action theo executor cung cấp. | Muốn kiểm soát pool cho logging/audit callback. |
| `exceptionally(fn)` | Thực thi theo completion policy không-async; không tự lập lịch thêm worker. | Fallback đơn giản và nhanh. |
| `exceptionallyAsync(fn, executor)` | Chạy fallback trên executor chỉ định. | Fallback có logic cần tách tài nguyên. |
| `handleAsync(fn, executor)` | Chạy hàm xử lý cả success/failure qua executor chỉ định. | Cần chuyển đổi outcome nhưng không muốn chiếm completion thread. |

Sự tồn tại của Spring `@Async("lessonExecutor")` **không có nghĩa** tất cả các stage nối sau đó tự dùng `lessonExecutor`. `CompletableFuture` có quy tắc executor riêng: các overload `...Async(...)` không truyền executor thường dùng facility mặc định của stage/JDK (thường là common pool). Với workload blocking hoặc dữ liệu nhạy cảm, chọn executor và context propagation rõ ràng.

Không đặt một thao tác I/O blocking rất lâu trong `whenComplete` nếu nó chạy trực tiếp trên thread đang hoàn tất một Future quan trọng. Callback có thể kéo dài thời gian trước khi dependent stage hoàn tất và giữ worker Spring bị bận. Đối với logging, cân nhắc cơ chế nonblocking/queue logging phù hợp và theo dõi lỗi của chính pipeline quan sát.

## 13. Khi `whenComplete`/`exceptionally` che hoặc đổi lỗi theo cách bất ngờ

### Trường hợp 1 — Logging callback ném lỗi trên success

```java
CompletableFuture<String> ok =
    CompletableFuture.completedFuture("OK");

CompletableFuture<String> afterLog = ok.whenComplete(
    (value, error) -> {
        throw new IllegalStateException("Logging is down");
    }
);
```

Đoạn Java thuần này tạo `afterLog` ở trạng thái failed, dù `ok` vẫn successful. Đây là lý do side-effect observer phải được thiết kế đáng tin cậy, nhất là audit/logging external có thể lỗi.

### Trường hợp 2 — Recovery callback tự thất bại

```java
CompletableFuture<String> afterFallback = source.exceptionally(
    error -> {
        throw new IllegalArgumentException("Cache is not ready");
    }
);
```

Nếu source failed, `afterFallback` sẽ failed do chính lỗi cache. Không phải cứ thêm `exceptionally` là có kết quả thành công; chỉ khi fallback trả về bình thường mới phục hồi được.

### Trường hợp 3 — Phục hồi `null` vô tình biến failure thành success

```java
CompletableFuture<String> masked = source.exceptionally(
    error -> null
);
```

Với `String` là kiểu tham chiếu, `masked.join()` có thể trả `null` mà không ném lỗi. Nếu caller không dự kiến null, bạn đã chuyển một backend failure rõ ràng thành NPE khó tìm ở bước sau. Hãy đặt fallback hợp đồng cụ thể, hoặc giữ failure để tầng trên xử lý.

### Trường hợp 4 — Chỉ quan sát rồi vẫn `thenApply`

```java
CompletableFuture<String> transformed = source
    .whenComplete((value, error) -> audit(error))
    .thenApply(String::toUpperCase);
```

Nếu source failed, `whenComplete` vẫn truyền failure và `thenApply` **không chạy**; `transformed` tiếp tục failed. Nếu cần `thenApply` luôn có một giá trị (trừ khi fallback cũng lỗi), đặt `exceptionally` hoặc `handle` **trước** bước chuyển đổi.

## 14. Phục hồi không đồng nghĩa mọi tác dụng phụ đã được xử lý

### Trong Spring MVC

Nếu controller nhận một `CompletableFuture<String>` đã phục hồi, tầng MVC/API có thể trả response success với fallback. Điều này hợp lý cho dịch vụ có chấp nhận cache, nhưng không nên biến một lỗi thanh toán hoặc kiểm tra quyền truy cập thành HTTP 200 giả. Nên phân biệt “result from primary” và “result from fallback” trong domain/observability khi ảnh hưởng quyết định người dùng.

Một controller gọi `future.get()` hoặc `join()` ngay vẫn chặn request thread dù service được `@Async`. Lớp HTTP async có hợp đồng riêng; một future không tự bảo đảm toàn bộ request xử lý non-blocking.

### Transaction và retry

Nếu worker đã ghi database một phần rồi ném exception, `exceptionally` trả fallback **không rollback** transaction hoặc undo side effect. Rollback phụ thuộc transaction boundary/isolation và chính code nghiệp vụ. `@Transactional` ở caller không mặc nhiên truyền qua worker `@Async`; cần xem proxy và transaction ở thread thực thi.

Fallback cũng **không retry** backend. Retry thực sự là thao tác gọi lại, phải giới hạn số lần, timeout, backoff, idempotency, tổng deadline và tránh làm nghẽn pool đang quá tải. Khi một tác vụ đã phát sinh side effect, retry có thể nhân đôi tác động nếu không có bảo vệ.

### Timeout và cancellation

`Future.get(timeout, unit)` chỉ giới hạn **caller chờ**, không tự cancel worker. `CompletableFuture.orTimeout(...)` có thể hoàn tất chính future bằng exception timeout khi pending; nếu sau đó `exceptionally` trả fallback, caller có thể nhận giá trị thay thế nhưng worker bên dưới vẫn tiếp tục chạy. `completeOnTimeout(...)` trực tiếp đưa fallback vào future nếu chưa hoàn tất đến hạn, cũng không tự buộc worker dừng.

`CompletableFuture.cancel(true)` không bảo đảm interrupt computation tạo ra completion. Nếu người dùng không còn cần kết quả, phải có chính sách cancellation hợp tác và timeout tại I/O client thực sự. Không giả định “đã phục hồi rồi” nghĩa tài nguyên đã được thu hồi.

### Context và thread safety

`@Async` là ranh giới thread. MDC logging, `SecurityContext`, request attributes, transaction, và nhiều `ThreadLocal` của caller không tự truyền sang worker. Callback `whenComplete` non-async cũng có thể chạy trên thread hoàn tất stage khác; nếu cần correlation ID, dùng context propagation có chủ đích và dọn/khôi phục trong `finally`. Không lưu thông tin request của người dùng vào một singleton mutable field để phục vụ logging bất đồng bộ.

## 15. Thiết kế quan sát lỗi và fallback trong production

Nên phân biệt các tín hiệu:

| Chỉ số | Ý nghĩa | Tại sao cần riêng? |
| --- | --- | --- |
| `primary_failure_total` | Backend/tác vụ nguồn lỗi trước phục hồi. | Fallback có thể làm request cuối thành công; chỉ đo final error sẽ bỏ lỡ outage. |
| `fallback_attempt_total` | Đã thử lấy giá trị dự phòng. | Biết hệ thống đang phụ thuộc fallback ở mức nào. |
| `fallback_success_total` | Fallback trả value hợp lệ. | Đo khả năng phục hồi thật. |
| `fallback_failure_total` | Chính fallback thất bại. | Phân biệt suy giảm kép. |
| `final_request_failure_total` | Caller cuối vẫn nhận lỗi. | Đo tác động thực đối với người dùng. |
| `fallback_data_age` | Độ cũ của cached/stale value nếu có. | Ngăn dữ liệu dự phòng không phù hợp bị coi như dữ liệu tươi. |

Nếu metric chỉ được ghi **sau** `exceptionally`, upstream failure có thể không còn biểu hiện dưới dạng `error`. Thường cần quan sát source trước khi phục hồi, rồi đo outcome cuối sau khi fallback. Đừng cho metric sink hoặc logger làm nghẽn thread pool nghiệp vụ hoặc gây exception bất ngờ.

Có thể biểu đạt kết quả cuối bằng domain type thay vì che khuất nguồn:

```java
record FetchOutcome(String value, boolean degraded) {}

CompletableFuture<FetchOutcome> finalResult = source.handle(
    (value, error) -> error == null
        ? new FetchOutcome(value, false)
        : new FetchOutcome("cached", true)
);
```

Đây là snippet Java 17; business phải xác định có thể dùng `"cached"` trong trường hợp lỗi nào, dữ liệu dự phòng có hợp lệ hay không. Nếu không có fallback tin cậy, hãy cho failure tiếp tục truyền lên tầng xử lý phù hợp.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Giải pháp |
| --- | --- | --- |
| Dùng `whenComplete` để log rồi tưởng đã chữa lỗi. | Caller tiếp tục nhận failure. | Dùng `exceptionally`/`handle` nếu **thực sự muốn** trả fallback. |
| Dùng `handle` chỉ để log rồi `return null`. | Nuốt lỗi, mất giá trị success, NPE xuất hiện muộn. | Dùng `whenComplete` để quan sát mà giữ outcome. |
| Dùng `exceptionally(ex -> null)` cho mọi lỗi. | Failure bị biến thành success null. | Có fallback hợp đồng rõ hoặc để lỗi truyền tiếp. |
| Fallback mọi exception, kể cả validation/security. | Che lỗi nghiệp vụ và có thể phá bảo mật. | Chỉ phục hồi các loại lỗi được chấp nhận. |
| Gắn metrics sau khi đã recovery, chỉ đếm `error != null`. | Không thấy backend outage đã được fallback che. | Đếm lỗi nguồn trước fallback, đo thêm outcome cuối. |
| Nghĩ `exceptionally` sửa chính future nguồn. | Consumer khác giữ source vẫn nhận lỗi. | Trả/tiếp tục dùng stage sau recovery; hiểu mỗi stage riêng. |
| Nghĩ `exceptionally` tự retry. | Không gửi lại backend, kết quả chỉ đến từ fallback. | Nếu cần retry, thiết kế gọi lại có giới hạn và idempotency. |
| Gọi `.join()` trong fallback để chờ API khác trên pool nhỏ. | Tốn worker, có thể deadlock. | Dùng `exceptionallyCompose` cho fallback async. |
| Đặt logging I/O dài trong `whenComplete`. | Giữ thread hoàn tất stage và làm tăng latency. | Observer nhẹ, hoặc tách executor có kiểm soát. |
| Cho rằng callback non-async chắc chạy trên main thread. | Context/MDC không đúng, thread safety sai. | Hiểu completion thread và propagation. |
| `@Async void` mà cố gọi `exceptionally` từ caller. | Không có handle kết quả. | Dùng Future return hoặc `AsyncUncaughtExceptionHandler`. |
| Bỏ qua lỗi submit task. | `TaskRejectedException` xảy ra trước callback chain. | Bắt tại điểm submit, quản lý quá tải/rejection. |
| Fallback thành công nên coi worker đã dừng. | Task/side effect cũ có thể tiếp tục. | Tách completion policy với cancellation và I/O timeout. |

## 17. Checklist khi đọc code

1. **Đang quan sát hay đang thay kết quả?** Nếu chỉ log/metrics, `whenComplete`; nếu muốn success fallback, `exceptionally`/`handle`.
2. **Stage nào được trả cho caller?** Original hay recovery stage? Có stage quan sát bị bỏ và exception của callback không ai theo dõi?
3. **Nhánh success có bị đổi không?** `exceptionally` giữ success, `handle` chạy cả hai nhánh.
4. **Lỗi nào được phục hồi?** Có phân loại transient, validation, auth, cancellation, timeout hay cứ bắt mọi `Throwable`?
5. **Fallback có ý nghĩa nghiệp vụ?** Dữ liệu dự phòng hợp lệ, đủ mới và được gắn nhãn degraded chưa?
6. **Có giám sát upstream failure không?** Log/metrics trước khi recovery, đếm số lần fallback và kết quả cuối?
7. **Callback có blocking/throw không?** `whenComplete` ném lỗi trên success làm stage mới thất bại; fallback ném lỗi làm stage recovery failed.
8. **Có đúng ranh giới Spring async không?** Bean Spring-managed, `@EnableAsync`, lời gọi qua proxy, executor qualifier?
9. **Có xử lý lỗi submit và @Async void không?** Chúng không nhất thiết đi vào pipeline Future.
10. **Có cần fallback bất đồng bộ không?** Ưu tiên `exceptionallyCompose` khi fallback trả một stage khác, tránh blocking `join`.
11. **Context và transaction được quản lý ở đâu?** Worker/callback không mặc nhiên có ThreadLocal caller.
12. **Caller cuối cùng cần thấy gì?** Thành công thật, thành công suy giảm, hoặc lỗi; đừng dùng HTTP 200 giả để che lỗi quan trọng.

## 18. Bài tập kiểm tra

**Câu 1.** `source` kết thúc với `IllegalStateException`. `source.whenComplete((v,e) -> log(e))` có làm `join()` của stage mới trả value không?

**Đáp án:** Không. Callback log kết thúc bình thường thì stage mới giữ exception của source; `join()` vẫn ném lỗi.

**Câu 2.** `source.exceptionally(e -> "cache")` làm thay đổi `source.isCompletedExceptionally()` thành false không?

**Đáp án:** Không. Recovery tạo stage phụ thuộc mới; source vẫn failed. Chỉ stage recovery thành công với `"cache"`.

**Câu 3.** `source` thành công `"OK"`. `source.exceptionally(e -> "cache")` trả gì?

**Đáp án:** `"OK"`. Callback fallback không chạy khi source thành công.

**Câu 4.** Một `handle` được viết là `(v,e) -> null` để in lỗi. Điều gì xảy ra?

**Đáp án:** Handler chạy cho mọi outcome và stage sau đó thành công với `null` nếu handler không ném lỗi; đây không phải “chỉ quan sát”, có thể che failure và mất success value.

**Câu 5.** `whenComplete` ném exception khi nguồn thành công. Stage mới có còn success không?

**Đáp án:** Không. Stage phụ thuộc thất bại với exception của callback. Nếu nguồn đã lỗi, theo quy tắc `whenComplete`, lỗi nguồn được ưu tiên khi callback cũng lỗi.

**Câu 6.** Khi muốn ghi nhận cả lỗi backend và tỷ lệ fallback thành công, nên đặt log/metric ở đâu?

**Đáp án:** Quan sát lỗi nguồn **trước** khi phục hồi và đo kết quả fallback **sau** đó. Nếu chỉ quan sát sau recovery, lỗi backend có thể đã biến thành một success.

**Câu 7.** Fallback phải gọi một API async khác. `exceptionally(error -> secondary.getAsync().join())` có phải cách tối ưu?

**Đáp án:** Thường không, vì `.join()` có thể chặn completion thread. Dùng `exceptionallyCompose` và quản lý timeout/executor phù hợp.

**Câu 8.** Một phương thức `@Async` trả `void` lỗi trong worker. Caller gắn `whenComplete` lên đâu?

**Đáp án:** Không có Future trả về để gắn. Cần exception handler/logging dành cho `@Async void`, hoặc thay hợp đồng method thành `CompletableFuture` nếu caller cần quan sát.

**Câu 9.** `get(timeout)` hết hạn và một `exceptionally` sau `orTimeout` trả cache. Có nghĩa I/O worker đã dừng không?

**Đáp án:** Không. Completion/fallback của future và lifecycle I/O task khác nhau; cần timeout/cancellation ở tầng thực thi.

### Ghi nhớ

**Chỉ quan sát lỗi** và **phục hồi bằng giá trị thay thế** là hai quyết định khác nhau. `whenComplete` giúp log/metrics và thông thường giữ nguyên outcome; `exceptionally` thay failure bằng value; `handle` có quyền tạo outcome mới trên cả thành công lẫn thất bại. Trong Spring `@Async`, hãy quan sát đúng stage caller nhận, cấu hình executor rõ ràng và tách recovery policy khỏi timeout, retry, transaction và side effects. Một fallback tốt có nghĩa nghiệp vụ, có giới hạn, có giám sát và không xóa dấu vết lỗi nguồn.

### Tài liệu tham khảo chính thức

- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): hợp đồng `whenComplete`, `exceptionally`, `handle`, `exceptionallyCompose`, `get`/`join` và completion state.
- [Java SE 17 — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html): quy tắc các stage phụ thuộc và lỗi callback.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `@Async`, executor selection, `Future` và quản lý exception.
- [Spring Framework 6.2 — @Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/Async.html): kiểu return, proxy và future mà caller quan sát.
