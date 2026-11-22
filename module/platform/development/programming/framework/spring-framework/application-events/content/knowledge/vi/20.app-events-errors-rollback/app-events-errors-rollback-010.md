# Ghi nhận lỗi mà không che giấu nguyên nhân trong Spring Application Events

Trong hệ thống sử dụng **Spring Framework Application Events**, một lỗi có thể xuất hiện ở nơi phát event, listener xử lý event, transaction manager, bước ghi log/metric hoặc dịch vụ ngoài được gọi từ listener. **Ghi nhận lỗi mà không che giấu nguyên nhân** nghĩa là có đủ thông tin để chẩn đoán lỗi, đồng thời bảo toàn **exception gốc, cause chain và quyết định rollback** mà nghiệp vụ cần.

Điều nguy hiểm không phải chỉ là “quên log lỗi”, mà còn là những cách ghi nhận sai khiến một lỗi phụ (ví dụ hệ thống telemetry không hoạt động) thay thế nguyên nhân chính (ví dụ không đủ tồn kho), hoặc khiến transaction **commit thành công mặc dù listener bắt buộc đã thất bại**.

Mục tiêu của bài:

- Phân biệt **lỗi nghiệp vụ ban đầu** với **lỗi phát sinh khi quan sát/ghi nhận**.
- Hiểu exception đi qua `ApplicationEventPublisher`, `@EventListener`, `@TransactionalEventListener`, multicaster đồng bộ/bất đồng bộ và transaction như thế nào.
- Giữ nguyên exception gốc khi phải log, enrich context, chuyển thành exception nghiệp vụ khác hoặc xử lý nhiều lỗi cùng lúc.
- Thiết kế observability, retry và xử lý sau commit mà **không nói sai trạng thái dữ liệu**.
- Kiểm chứng bằng một ví dụ Java 17+ chạy được với Spring Framework, Spring JDBC và H2.

## 1. Các loại lỗi cần phân biệt

Xét thao tác đặt đơn:

```text
OrderService.placeOrder()
  |
  +-- INSERT order (transaction T1)
  +-- publishEvent(OrderSubmitted)
          |
          +-- InventoryListener
          |     +-- kiểm tra tồn kho
          |     +-- có thể throw InventoryUnavailable
          |
          +-- AuditListener / Logger / Telemetry
                +-- có thể lỗi do mất kết nối
  |
  +-- COMMIT hoặc ROLLBACK T1 (tùy luồng và cấu hình)
```

**Lỗi nguyên phát (primary/root failure)** là lỗi khiến yêu cầu không hoàn thành theo hợp đồng nghiệp vụ, ví dụ `InventoryUnavailableException` từ việc kiểm tra tồn kho. **Lỗi thứ cấp (secondary failure)** là lỗi xảy ra *khi đang xử lý hoặc ghi nhận primary failure*, ví dụ backend ghi metric bị ngắt. Nếu bỏ mất primary exception, log chỉ còn “Metrics unavailable” và người vận hành có thể điều tra sai hướng.

Một exception có thể chứa nhiều mảnh thông tin:

| Thành phần | Cần giữ vì |
| --- | --- |
| **Exception type** | Phân loại lỗi và áp dụng retry/rollback hợp lý |
| **Message** | Mô tả ý nghĩa cụ thể; tránh ghi bí mật |
| **Stack trace** | Nơi lỗi thực sự phát sinh |
| **`getCause()` chain** | Nguyên nhân của exception bọc ở tầng cao hơn |
| **`getSuppressed()`** | Những lỗi phụ không được phép thay thế primary |
| **Event context** | `eventId`, `orderId`, `eventType`, listener name, transaction phase, attempt |
| **Outcome** | Transaction commit/rollback, listener success/failure, message delivery status |

Hai nguyên tắc chủ đạo:

1. **Không thay nguyên nhân gốc bằng lỗi ghi log/quan sát.** Nếu bắt buộc phải báo thêm một lỗi phụ, hãy gắn nó theo cách không phá primary.
2. **Không thay đổi quyết định nghiệp vụ chỉ để có log đẹp.** Nếu lỗi listener phải khiến transaction rollback, đừng nuốt exception để request nhìn như thành công.

## 2. Exception đi qua Spring event bus như thế nào?

### 2.1. Listener đồng bộ mặc định

`ApplicationEventPublisher.publishEvent(...)` không phải message queue bền vững. Với `SimpleApplicationEventMulticaster` mặc định, listener được gọi **trên thread của publisher** nếu không cấu hình executor khác. Mặc định **không có `ErrorHandler`**: một RuntimeException từ listener có thể dừng lượt multicast hiện tại và **được truyền về lời gọi publish**.

```java
@Component
class StockListener {
    @EventListener
    public void onOrderSubmitted(OrderSubmitted event) {
        throw new IllegalStateException("Inventory unavailable");
    }
}
```

Đây là **mã khung minh họa**, giả định `OrderSubmitted` là lớp event hợp lệ và listener được Spring phát hiện. Khi publisher nằm trong một phương thức `@Transactional`, exception không được bắt có thể thoát khỏi service, khiến transaction rollback theo mặc định nếu là `RuntimeException` hoặc `Error`.

**Lưu ý về thứ tự:** không bảo đảm mọi listener còn lại đều được gọi nếu một listener đồng bộ ném exception. Việc xử lý exception là một phần hành vi của multicaster; không nên giả định “phát event” đồng nghĩa “tất cả listener đã nhận và xử lý xong”.

### 2.2. Catch chỉ để log rồi **rethrow chính exception**

```java
try {
    applicationEventPublisher.publishEvent(event);
} catch (RuntimeException original) {
    log.error("Failed to publish eventId={}, orderId={}",
            event.eventId(), event.orderId(), original);
    throw original;
}
```

Đây là **đoạn minh họa**: cần ứng dụng cung cấp `applicationEventPublisher`, `event` và logger `log`. Truyền `original` làm tham số exception để hệ thống log ghi stack trace. Câu `throw original` không tạo một lỗi mới mất dấu vết; nó giữ object exception gốc. Trong môi trường có yêu cầu rollback, nguyên nhân vẫn được truyền ra cho transaction interceptor.

Tuy nhiên, nếu chính lời gọi ghi log hoặc telemetry có thể ném exception, đoạn trên vẫn có thể bị một lỗi thứ cấp thay thế. Với một reporter không đáng tin cậy, cần cô lập nó như mục 4.

### 2.3. Catch rồi **nuốt lỗi** thay đổi hành vi transaction

**Mẫu nguy hiểm:**

```java
@Transactional
public void placeOrder() {
    repository.save(order);
    try {
        applicationEventPublisher.publishEvent(new OrderSubmitted(order.getId()));
    } catch (Exception ex) {
        log.error("Event listener failed", ex);
        // Không throw, không mark rollback-only.
    }
    // Phương thức có thể thoát bình thường -> transaction có thể COMMIT.
}
```

Đây là **mã minh họa có chủ ý sai**, không phải class chạy độc lập. Nếu nghiệp vụ yêu cầu listener kiểm tra tồn kho thành công trước commit, cách bắt lỗi này che giấu thất bại và có thể cho phép lưu đơn không hợp lệ.

Có những trường hợp **best-effort** hợp lệ để không ảnh hưởng transaction (ví dụ metric không quan trọng), nhưng phải được quyết định ở mức hợp đồng nghiệp vụ và có cách ghi nhận failure riêng. Không gắn nhãn “best-effort” cho bước kiểm soát bất biến quan trọng chỉ để né rollback.

## 3. Giữ nguyên `cause`, `suppressed` và stack trace

### 3.1. Nếu bọc exception, luôn giữ `cause`

Không nên:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot send notification");
}
```

Thông tin về `IOException`, stack trace của lỗi mạng và các nested causes đã biến mất khỏi exception mới.

Nên:

```java
catch (IOException ex) {
    throw new IllegalStateException("Cannot send notification", ex);
}
```

`getCause()` sẽ trỏ tới `IOException` ban đầu. Bọc exception có ý nghĩa khi đi qua **ranh giới abstraction**: ví dụ từ lỗi I/O thuần Java sang lỗi ứng dụng được định danh. Không cần bọc cùng exception qua từng method nếu việc đó chỉ tạo message lặp.

### 3.2. Nếu recorder cũng hỏng, dùng suppressed cho lỗi phụ

```java
RuntimeException primary = ...;  // Lỗi nghiệp vụ cần bảo toàn.
try {
    failureRecorder.record(primary);
} catch (RuntimeException reportingFailure) {
    if (reportingFailure != primary) {
        primary.addSuppressed(reportingFailure);
    }
}
throw primary;
```

Đây là **mã minh họa**. Cách này giữ chính `primary` để tầng transaction/caller phân loại rollback. Lỗi `reportingFailure` được gắn vào `primary.getSuppressed()`, không bị “mất tích” nhưng cũng không chiếm chỗ lỗi gốc.

Không gọi `addSuppressed(primary)` lên chính primary: Java không cho phép self-suppression. Với các lỗi hệ thống nghiêm trọng (`VirtualMachineError`, mất tài nguyên nghiêm trọng...), không nên áp dụng một chính sách `catch (Throwable)` quá rộng chỉ để làm đẹp log. Catch loại lỗi mà reporter có thể hợp lý ném ra và giữ các cơ chế xử lý lỗi nghiêm trọng của JVM.

### 3.3. Tránh `throw` mới trong `finally`

Mẫu sai:

```java
try {
    inventory.reserve(orderId);   // Ném lỗi A.
} finally {
    auditStore.flush();            // Nếu ném lỗi B, B che lỗi A.
}
```

Đoạn trên chỉ minh họa nguyên tắc về `finally`. Nếu cả hai thao tác thất bại, exception từ `finally` có thể thay thế exception đang được truyền ra. **Try-with-resources** trong Java có cách quản lý suppressed exceptions cho nhiều tình huống đóng tài nguyên, nên thường tốt hơn tự viết `finally` dễ che lỗi.

Nếu bắt buộc có bước cleanup thủ công quan trọng, cần thiết kế để lỗi cleanup được ghi nhận/phối hợp mà không tùy tiện thay exception nghiệp vụ. Đồng thời, nếu cleanup là phần bắt buộc để bảo toàn dữ liệu, đừng đơn giản nuốt nó; phải công bố cả primary và secondary cho cơ chế phục hồi phù hợp.

### 3.4. Không log cùng stack trace ở mọi lớp

Nếu một exception được log tại listener, tại publisher, ở service và ở HTTP advice, sẽ tạo nhiều bản stack trace giống nhau. Điều đó không phải luôn “ghi nhận tốt hơn”. Nên quy định **lớp sở hữu báo lỗi chính**; tầng dưới bổ sung context khi cần nhưng không nhân bản log vô ích. Nếu lỗi được bọc lại, phải giữ cause; nếu được chuyển thành response API, không tiết lộ thông tin nhạy cảm từ stack trace cho client.

## 4. Ví dụ Java 17+ có thể chạy: lỗi telemetry không che lỗi listener, transaction rollback

Ví dụ dùng Spring Context, Spring JDBC và H2. Trong **kịch bản đúng**, listener đồng bộ ném `IllegalStateException`; mã ứng dụng cố ghi nhận lỗi qua telemetry, nhưng telemetry cũng ném lỗi. Chương trình gắn lỗi telemetry vào **suppressed** rồi rethrow exception listener, để `TransactionTemplate` rollback bản ghi đơn hàng.

Trong **kịch bản sai có chủ đích**, service nuốt cùng lỗi listener; transaction hoàn thành bình thường và bản ghi được commit. Kết quả cho thấy một dòng log không đủ thay cho cơ chế propagation.

### 4.1. Cấu trúc thư mục

```text
event-error-cause-demo/
├── pom.xml
└── src/main/java/EventErrorCauseDemo.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-error-cause-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <configuration>
                    <mainClass>EventErrorCauseDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. `src/main/java/EventErrorCauseDemo.java`

```java
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class EventErrorCauseDemo {

    public record OrderSubmitted(long id) {}

    public static final class InventoryListener {
        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            throw new IllegalStateException(
                    "inventory unavailable for order " + event.id());
        }
    }

    public static final class FailureRecorder {
        public void record(long orderId, RuntimeException primary) {
            // Mô phỏng hệ thống telemetry gặp sự cố.
            throw new IllegalStateException("telemetry offline");
        }
    }

    private static void reportWithoutMasking(
            long orderId,
            RuntimeException primary,
            FailureRecorder recorder) {

        System.out.println("record: order=" + orderId
                + " primary=" + primary.getMessage());

        try {
            recorder.record(orderId, primary);
        } catch (RuntimeException reportingFailure) {
            if (reportingFailure != primary) {
                primary.addSuppressed(reportingFailure);
            }
        }
    }

    private static int count(JdbcTemplate jdbc, long id) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders WHERE id = ?",
                Integer.class, id);
        return value == null ? 0 : value;
    }

    public static void main(String[] args) {
        var ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:error_cause_demo;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");

        var jdbc = new JdbcTemplate(ds);
        jdbc.execute(
                "CREATE TABLE purchase_orders (id BIGINT PRIMARY KEY)");

        var tx = new TransactionTemplate(
                new DataSourceTransactionManager(ds));
        var recorder = new FailureRecorder();

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(InventoryListener.class);
            context.refresh();

            // Kịch bản đúng: primary vẫn được ném để transaction rollback.
            try {
                tx.executeWithoutResult(status -> {
                    jdbc.update(
                            "INSERT INTO purchase_orders(id) VALUES (?)", 42L);

                    try {
                        context.publishEvent(new OrderSubmitted(42L));
                    } catch (RuntimeException primary) {
                        reportWithoutMasking(42L, primary, recorder);
                        throw primary;
                    }
                });
            } catch (IllegalStateException primary) {
                System.out.println(
                        "caller: primary=" + primary.getMessage());
                System.out.println(
                        "caller: suppressed="
                        + primary.getSuppressed()[0].getMessage());
            }

            System.out.println("database: order 42 count=" + count(jdbc, 42L));

            // Kịch bản sai: exception bị nuốt -> có thể commit.
            tx.executeWithoutResult(status -> {
                jdbc.update(
                        "INSERT INTO purchase_orders(id) VALUES (?)", 43L);

                try {
                    context.publishEvent(new OrderSubmitted(43L));
                } catch (IllegalStateException ignored) {
                    System.out.println(
                            "unsafe: swallowed=" + ignored.getMessage());
                    // CHỈ MINH HỌA LỖI: không throw, không mark rollback-only.
                }
            });

            System.out.println("database: order 43 count=" + count(jdbc, 43L));
        }
    }
}
```

Chạy trong thư mục dự án, với JDK 17+, Maven và quyền tải dependencies lần đầu:

```bash
mvn -q compile exec:java
```

Các dòng do **chương trình** in ra, theo thứ tự (bỏ qua log ngoài của Maven và framework):

```text
record: order=42 primary=inventory unavailable for order 42
caller: primary=inventory unavailable for order 42
caller: suppressed=telemetry offline
database: order 42 count=0
unsafe: swallowed=inventory unavailable for order 43
database: order 43 count=1
```

Phân tích:

1. `InventoryListener` là Spring bean có `@EventListener`; mặc định được gọi đồng bộ khi `context.publishEvent(...)` thực thi.
2. Lời gọi listener ném `IllegalStateException` cho đơn `42`. `reportWithoutMasking(...)` in thông tin lỗi chính rồi thử ghi telemetry; telemetry lại lỗi, nhưng exception này được đưa vào `primary.getSuppressed()`.
3. Chính `primary` được ném tiếp từ callback trong `TransactionTemplate`. Spring rollback transaction của đơn `42`, sau đó caller thấy **lỗi tồn kho vẫn là primary** và telemetry lỗi vẫn có trong suppressed.
4. Với đơn `43`, chương trình cố tình nuốt `IllegalStateException`. `TransactionTemplate` không thấy lỗi ra khỏi callback, transaction hoàn thành bình thường và bản ghi đơn `43` được commit.
5. Demo dùng `System.out` để stdout xác định; ứng dụng thật dùng structured logger/tracing và tránh việc reporter phụ gây lỗi mới. Chỉ dùng nhánh `unsafe` để học và kiểm thử, **không áp dụng cho nghiệp vụ yêu cầu listener thành công trước commit**.

`TransactionTemplate` tạo transaction thật trên H2; `JdbcTemplate` và `DataSourceTransactionManager` dùng cùng `DataSource` nên `INSERT` thuộc transaction đang chạy. Bởi vậy các giá trị `count=0` và `count=1` phản ánh kết quả rollback và commit của database, không đơn thuần là log từ listener.

## 5. `ErrorHandler` của multicaster: lựa chọn “log rồi bỏ qua” hay “log rồi propagate”

`SimpleApplicationEventMulticaster` có API `setErrorHandler(ErrorHandler)`. Theo hợp đồng mặc định, nếu không có handler, exception của listener đồng bộ được truyền về publisher. Khi cấu hình `ErrorHandler`, bạn phải chủ động chọn cách xử lý.

Spring cung cấp các handler gợi ý trong `org.springframework.scheduling.support.TaskUtils`:

| Chính sách | Ý nghĩa | Rủi ro/ứng dụng |
| --- | --- | --- |
| **Không cấu hình ErrorHandler** | Exception listener đồng bộ được propagate theo hành vi mặc định | Hợp lý khi listener bắt buộc cần quyết định rollback |
| `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER` | Log lỗi và tiếp tục propagate | Có thể dùng khi cần log ở multicaster mà vẫn giữ lỗi truyền tới publisher |
| `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` | Log và **suppress** exception | Có thể khiến publisher không thấy lỗi; không phù hợp với bước bắt buộc phải rollback |

Cấu hình minh họa cho một ứng dụng Spring, **không phải phần thêm vào chương trình độc lập ở mục 4**:

```java
@Configuration
class EventMulticasterConfiguration {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster eventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(
                TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER);

        return multicaster;
    }
}
```

Đoạn trên yêu cầu các import `@Configuration`, `@Bean`, `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster` và `TaskUtils` tương ứng. Tên bean `applicationEventMulticaster` là tên framework dùng để phát Spring application events. Nếu sử dụng Spring Boot, không cần tự tạo cấu hình này trừ khi thật sự có yêu cầu thay đổi mặc định.

**Không chọn `LOG_AND_SUPPRESS` chỉ để dashboard hết lỗi.** Nó thay đổi cơ chế event propagation; exception bị suppress có thể khiến transaction của service tiếp tục như chưa có lỗi. Cần xác định rõ listener nào là bắt buộc, listener nào là best-effort, và tách chúng theo kiến trúc nếu chính sách lỗi khác nhau.

### Multicaster bất đồng bộ có khác

Nếu multicaster được cấu hình `TaskExecutor`, một số listener có thể chạy ở executor. Exception có thể được chuyển đến executor/error handler và **không nhất thiết truyền về publisher** hoặc ngăn các listener khác chạy. Việc không có exception ở phía publisher **không chứng minh listener đã xử lý thành công**.

Cũng không được giả định mọi listener chạy trên executor: một số listener transaction-bound có thể khai báo không hỗ trợ async multicasting và vẫn chạy ở thread publish để gắn transaction đúng cách. Phải kiểm tra chính xác loại listener, cấu hình multicaster và API version.

## 6. `@Async`, `@TransactionalEventListener` và ranh giới rollback

### 6.1. Listener `@Async`

Một phương thức `@EventListener` dùng `@Async` sẽ được xử lý theo cơ chế async của Spring nếu cấu hình phù hợp. Lỗi của listener trên thread khác **không thể mặc nhiên rollback transaction của thread đang publish**. Với phương thức `void` async, có thể cấu hình `AsyncUncaughtExceptionHandler`; với `Future`/`CompletableFuture`, lỗi phải được quan sát qua trạng thái completion. Không tự suy luận lỗi listener đã được xử lý chỉ vì `publishEvent(...)` trả về.

Khi triển khai logging/tracing bất đồng bộ:

- Gắn `eventId`, `aggregateId`, `traceId` vào event hoặc propagate context theo cơ chế được hỗ trợ; không giả định MDC/`ThreadLocal` tự chạy sang mọi executor.
- Ghi rõ attempt count và tên listener khi retry.
- Không dùng `Thread.sleep(...)` để “chờ listener chạy” trong test; dùng completion hoặc latch/test support.
- Chọn cơ chế retry, dead-letter hoặc outbox phù hợp cho event phải được xử lý bền vững.

### 6.2. Listener gắn với pha transaction

`@TransactionalEventListener` cho phép chọn các pha:

| Pha | Thời điểm | Ghi nhận lỗi cần lưu ý |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit transaction nguồn | RuntimeException phù hợp có thể làm quá trình commit thất bại và gây rollback |
| `AFTER_COMMIT` (mặc định) | Sau khi commit thành công | Ghi nhận thất bại riêng; **không thể rollback transaction đã commit** |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Ghi nhận nguyên nhân rollback; tránh ném lỗi mới che nguyên nhân chính |
| `AFTER_COMPLETION` | Sau khi kết thúc bất kể commit/rollback | Quan sát outcome; cleanup/telemetry nên tránh thay primary failure |

Ví dụ minh họa độc lập với demo JDBC ở mục 4:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendNotification(OrderSubmitted event) {
    notificationGateway.send(event.id());
}
```

Đoạn này cần các bean và import tương ứng. Nếu gửi thông báo lỗi, đơn hàng của transaction nguồn vẫn **đã commit**. Không nên bắt lỗi rồi nói “đơn hàng đã rollback”. Hãy ghi một trạng thái gửi thông báo riêng, có retry/backoff hoặc dùng Transactional Outbox nếu yêu cầu không được thất lạc.

Đặc biệt, callback sau completion của transaction có các quy tắc riêng về **log/propagate exception**, nên **không thể áp dụng chung** kết luận “mọi exception của `@TransactionalEventListener` đều được truyền về service”. Cần xem phase và transaction manager. Với `AFTER_COMMIT`, kết quả commit đã được quyết định; ngoại lệ có xuất hiện ở caller hay chỉ trong log cũng không thay đổi dữ liệu đã commit.

### 6.3. `@Transactional` và checked exception

Theo quy tắc mặc định của Spring transaction dạng khai báo, `RuntimeException` và `Error` làm rollback, còn **checked exception thường không** (trừ khi cấu hình rollback rules). Có thể dùng `rollbackFor`, `noRollbackFor` hoặc cấu hình quy tắc toàn cục khi phù hợp.

Ví dụ:

```java
@Transactional(rollbackFor = IOException.class)
public void process() throws IOException {
    // Nếu IOException thoát khỏi transaction boundary -> rollback.
}
```

Đây là **mã minh họa**. Không phải mọi loại `Exception` đều có cùng hành vi rollback. Nếu bọc một `IOException` vào `IllegalStateException` có cause thì cần hiểu rằng bạn có thể thay đổi rollback classification tại tầng transaction; phải làm điều đó có chủ đích, không phải chỉ để viết log.

## 7. Log đủ để điều tra nhưng không làm lộ dữ liệu

Một bản ghi lỗi hữu ích nên có **cấu trúc ổn định** và đủ ngữ cảnh:

```text
level=ERROR
component=OrderEventListener
eventType=OrderSubmitted
eventId=evt-5d1...
aggregateId=order-42
phase=BEFORE_COMMIT
operation=reserveInventory
outcome=failed
exceptionType=InventoryUnavailableException
message="inventory unavailable"
traceId=<trace identifier, nếu có>
```

Các giá trị trên **chỉ minh họa format**, không phải output của ví dụ Java. Trong log production, nên:

1. Lưu **stack trace của primary exception** hoặc hệ thống error tracking liên kết với nó; nếu chỉ ghi `ex.getMessage()` thường không đủ.
2. Chỉ ghi identifier cần thiết như event ID, aggregate ID, tên listener, pha transaction, attempt, trace ID. Tránh log toàn bộ payload chứa PII, token, mật khẩu hoặc dữ liệu thẻ thanh toán.
3. Phân biệt **event được publish**, **listener thành công**, **transaction commit** và **message đã gửi ra hệ thống ngoài** — đó là các trạng thái khác nhau.
4. Dùng structured logging/tracing để gắn correlation mà không sửa kiểu exception. Với async, quan sát context propagation qua executor thay vì suy luận thread-local tự hiện diện.
5. Đặt trách nhiệm **ghi log chính** ở tầng đã quyết định cách xử lý lỗi; các tầng khác có thể thêm context, nhưng không cần lặp vô hạn cùng một stack trace.
6. Với lỗi quan trọng, đừng phụ thuộc duy nhất vào log volatile: sử dụng trạng thái bền vững, outbox, retry hoặc hệ thống cảnh báo tùy mức SLA.

Ví dụ có cause chain trong logger:

```java
try {
    orderService.placeOrder(command);
} catch (InventoryUnavailableException ex) {
    log.error("Cannot place order, orderId={}, eventId={}",
            command.orderId(), command.eventId(), ex);
    throw ex;
}
```

Đoạn trên là **mã minh họa**, phụ thuộc vào các lớp ứng dụng và logger đã cấu hình. Tham số cuối là exception, giúp giữ stack trace; `throw ex` không thay exception gốc. Khi xây error response, sử dụng mã lỗi nghiệp vụ ổn định, không sao chép nguyên stack trace ra response public.

## 8. Xử lý nhiều listener: đừng tự chế “thành công một phần” bằng cách nuốt lỗi

Nếu một event có nhiều listener:

```text
publish(OrderSubmitted)
    |
    +-- ValidateInventory      (bắt buộc)
    +-- UpdateSearchIndex      (best-effort/async)
    +-- SendConfirmationEmail  (sau commit)
    +-- RecordMetric           (best-effort)
```

Dùng cùng một chính sách lỗi cho cả bốn listener có thể làm kết quả sai:

- Bước **bắt buộc** `ValidateInventory` nên nằm trong giao dịch nghiệp vụ rõ ràng, hoặc tốt hơn là thực hiện trực tiếp trong use case trước commit nếu không muốn phụ thuộc vào thứ tự listener. Nếu nó thất bại, transaction cần thấy exception/rollback-only.
- `RecordMetric` không được làm thất bại transaction chỉ vì backend metrics lỗi; có thể tự catch và ghi nhận theo chính sách best-effort, nhưng phải chủ động và có circuit breaker nếu cần.
- `SendConfirmationEmail` nên thực thi sau commit hoặc qua outbox; lỗi email **không quay ngược** được đơn hàng đã commit.
- `UpdateSearchIndex` thường có thể retry hoặc xây lại từ dữ liệu nguồn; nên có tiêu chí observability riêng cho độ trễ đồng bộ.

Nếu bạn cần “phát cho tất cả listener, thu thập mọi lỗi, sau đó mới quyết định rollback”, multicaster mặc định **không tự cung cấp một hợp đồng tổng hợp lỗi như vậy**. Phải có orchestrator rõ ràng, lưu từng failure và quyết định có ném aggregate exception hay đánh dấu rollback-only. Không tự cấu hình `LOG_AND_SUPPRESS` và mặc nhiên xem đó là cơ chế xử lý lỗi đầy đủ.

## 9. Retry, idempotency và không đánh đồng lỗi với rollback

Một lỗi đã được log **không có nghĩa** công việc sẽ được retry. Với event trong JVM, nếu process dừng sau khi commit mà trước callback sau commit hoàn thành, một side effect có thể bị mất. Nếu retry không cẩn thận, side effect cũng có thể bị thực hiện nhiều lần.

Với nghiệp vụ cần bảo đảm có thể phục hồi:

1. Ghi dữ liệu nghiệp vụ và **outbox message** trong cùng transaction.
2. Sau commit, worker độc lập đọc outbox để giao event.
3. Nếu giao thất bại, lưu attempt, lỗi có cấu trúc và thời điểm retry; không thay event gốc bằng lỗi giao tiếp.
4. Consumer xử lý idempotent bằng event ID hoặc khóa nghiệp vụ để an toàn trước duplicate delivery.
5. Thiết lập cảnh báo khi vượt retry budget, dead-letter hoặc quá thời hạn xử lý.

Ví dụ trạng thái riêng:

```text
ORDER: COMMITTED
OUTBOX: PENDING / RETRYING / SENT / DEAD_LETTER
LAST_ERROR: ExternalServiceTimeout (cause preserved)
ATTEMPT: 3
NEXT_RETRY_AT: ...
```

Không nên trả về cho client một thông báo “đơn hàng rollback” chỉ vì `OUTBOX=RETRYING`. Trạng thái transaction nguồn và trạng thái xử lý event phụ là hai trục độc lập.

Với nghiệp vụ phân tán, đôi khi cần **compensation** cho một bước đã commit. Compensation là **một hành động nghiệp vụ mới**, không phải rollback kỹ thuật của transaction cũ. Khi bù trừ thất bại, cần giữ cả nguyên nhân ban đầu lẫn lỗi bù trừ để điều tra.

## 10. Quy trình xử lý sự cố thực tế

Khi có báo cáo “đã publish event nhưng hệ thống sai trạng thái”, thực hiện theo thứ tự:

1. **Xác định transaction nguồn.** Event phát trong transaction hay ngoài transaction? Trước commit, sau commit hay async?
2. **Xác định listener thực sự nhận event.** Kiểm tra event type, điều kiện `@EventListener`, phase `@TransactionalEventListener` và `fallbackExecution`; không suy luận từ log publisher.
3. **Thu thập primary exception.** Lấy type, message, cause chain, stack trace, suppressed và ngữ cảnh event; đừng chỉ nhìn lỗi cuối cùng trong log.
4. **Kiểm tra cấu hình multicaster.** Có custom `ErrorHandler`? Có `TaskExecutor`? Có dùng `LOG_AND_SUPPRESS` hay `@Async`?
5. **Đối chiếu kết quả database.** Query từ connection/transaction độc lập để xác nhận commit/rollback; HTTP 500 hoặc lỗi listener không tự khẳng định rollback.
6. **Đánh giá lỗi phụ.** Monitoring/logging, cleanup, notification hay retry có lỗi tiếp không? Có đang che hoặc thay nguyên nhân chính không?
7. **Khôi phục đúng tầng.** Nếu transaction nguồn rollback, xử lý request gốc; nếu transaction nguồn commit mà side effect lỗi, dùng retry/outbox/compensation theo hợp đồng.
8. **Bổ sung regression tests.** Bao gồm lỗi reporter, listener error, listener async và commit/rollback timing.

Một log dễ tìm kiếm rất hữu ích, nhưng **trạng thái giao dịch đã được database xác nhận** mới là bằng chứng cho kết luận commit/rollback.

## 11. Kiểm thử những tình huống quan trọng

| Tình huống | Kỳ vọng | Kiểm tra |
| --- | --- | --- |
| Listener đồng bộ ném `RuntimeException`, không bị catch | Exception ra khỏi publisher; transaction nguồn có thể rollback theo chính sách | Error type và dữ liệu thực tế |
| Lỗi listener + lỗi telemetry | Primary giữ nguyên; secondary nằm trong suppressed hoặc cấu trúc tương đương | `getMessage()`, `getSuppressed()`, stack trace |
| Service bắt và nuốt lỗi listener | Transaction có thể commit nếu không còn rollback-only | Chứng minh bằng query DB |
| Dùng multicaster `LOG_AND_SUPPRESS` | Publisher có thể không nhận exception | Test rollback policy thay vì chỉ log |
| Dùng `LOG_AND_PROPAGATE` | Vẫn thấy lỗi ở publisher đồng bộ | Test loại exception và cause |
| Listener `@Async` ném lỗi | Publisher không mặc định rollback vì lỗi trên thread khác | Handler/completion/error metric |
| Listener `AFTER_COMMIT` ném lỗi | Transaction nguồn đã commit; xử lý lỗi side effect riêng | DB state và retry/outbox |
| Reporter ném từ `finally` | Nguy cơ che exception trước đó | Test primary stack/cause |
| Checked exception thoát transaction `@Transactional` | Mặc định không giống unchecked | Test `rollbackFor`/policy thực tế |
| Có retry/dual delivery | Không thực hiện side effect không idempotent hai lần | Event ID, inbox/dedup state |

**Chiến lược test:** Một test dùng Spring Context + transaction manager thật giống ví dụ mục 4; test khác có thể dùng mock reporter để buộc phát sinh lỗi phụ. Nếu muốn kiểm tra propagating error handler, cấu hình multicaster có chủ đích rồi assert exception type. Với async, dùng `CompletableFuture`/latch hoặc test executor kiểm soát được thay vì ngủ cố định.

### Ví dụ JUnit 5: chỉ rõ ý định giữ lỗi gốc

Đoạn sau **mang tính tích hợp minh họa**, cần test class, fixtures và Maven/JUnit setup tương ứng:

```java
@Test
void preservesOriginalFailureWhenTelemetryFails() {
    IllegalStateException primary =
            new IllegalStateException("inventory unavailable");

    RuntimeException telemetry =
            new RuntimeException("metrics unavailable");

    try {
        primary.addSuppressed(telemetry);
        throw primary;
    } catch (IllegalStateException caught) {
        assertSame(primary, caught);
        assertEquals("inventory unavailable", caught.getMessage());
        assertSame(telemetry, caught.getSuppressed()[0]);
    }
}
```

Test này không thay thế integration test rollback; nó chỉ chứng minh **lựa chọn quản lý exception**. Integration test phải kiểm tra trạng thái database sau khi transaction hoàn tất.

## 12. Câu hỏi tự đánh giá

**1. Tại sao catch, log rồi không throw có thể nguy hiểm trong `@Transactional`?**  
Vì transaction interceptor có thể thấy phương thức hoàn thành bình thường và commit những thay đổi đáng ra phải rollback. Nếu lỗi là best-effort thì phải ghi rõ quyết định đó; nếu lỗi là bắt buộc thì phải propagate hoặc đánh dấu rollback-only theo chính sách.

**2. Nếu telemetry cũng lỗi trong khi đang log lỗi listener, làm sao không che lỗi listener?**  
Giữ object exception primary, xử lý lỗi telemetry riêng và gắn nó vào `primary.addSuppressed(...)` nếu phù hợp; sau đó rethrow primary.

**3. Sự khác biệt giữa `new RuntimeException("message")` và `new RuntimeException("message", cause)` là gì?**  
Constructor thứ hai giữ nguyên nhân gốc trong `getCause()`. Constructor đầu có thể làm mất chuỗi nguyên nhân khi thay exception cũ.

**4. `SimpleApplicationEventMulticaster` có tự luôn nuốt exception của listener không?**  
Không. Mặc định listener đồng bộ exception được propagate về publisher; handler hoặc executor tùy chỉnh có thể đổi hành vi.

**5. Listener `AFTER_COMMIT` ném lỗi có rollback được transaction đã commit không?**  
Không. Cần trạng thái xử lý riêng và cơ chế retry/compensation nếu nghiệp vụ yêu cầu.

**6. Vì sao log HTTP 500 không đủ chứng minh transaction rollback?**  
Request có thể lỗi sau khi commit, hoặc lỗi xảy ra trong listener async, hoặc ngoại lệ bị handler suppress. Phải đối chiếu transaction outcome và dữ liệu database.

**7. Có nên catch mọi `Throwable` để mọi lỗi đều được ghi nhận không?**  
Không nên áp dụng tùy tiện. Một số `Error` phản ánh sự cố JVM/tài nguyên nghiêm trọng; catch rộng có thể làm hỏng đường xử lý khẩn cấp. Chọn đúng loại lỗi được phép xử lý, giữ primary và không che giấu trạng thái thất bại thật.

## 13. Tài liệu chính thức

- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster, mặc định đồng bộ và ErrorHandler](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Declarative Transaction Rollback Rules](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Observability Support for Application Events](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Java SE 17 — Throwable: cause và suppressed exceptions](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html)

