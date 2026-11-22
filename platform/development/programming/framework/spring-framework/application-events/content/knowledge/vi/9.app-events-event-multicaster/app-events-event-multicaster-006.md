# ErrorHandler của multicaster trong Spring Framework Application Events

## 1. Vấn đề mà ErrorHandler giải quyết

Trong Spring Framework, `ApplicationEventPublisher.publishEvent(...)` gửi một sự kiện đến những listener đăng ký phù hợp. Thành phần thực hiện việc phân phối là `ApplicationEventMulticaster`; triển khai thông dụng do Spring dùng mặc định là `SimpleApplicationEventMulticaster`.

Giả sử một sự kiện `OrderSubmitted` có ba listener:

- Listener A ghi audit.
- Listener B cập nhật chỉ số.
- Listener C gửi thông báo.

Nếu listener A ném ngoại lệ, câu hỏi không chỉ là “ghi log thế nào?” mà còn là: **ngoại lệ có truyền về nơi phát event không, và listener B/C có còn chạy không?** Câu trả lời phụ thuộc vào cách multicaster được cấu hình và việc listener chạy đồng bộ hay bất đồng bộ.

`ErrorHandler` của multicaster là một callback kiểu `org.springframework.util.ErrorHandler`, có phương thức:

```java
void handleError(Throwable t);
```

Có thể gắn callback này vào `SimpleApplicationEventMulticaster` bằng `setErrorHandler(...)`. Khi một listener ném lỗi trong phạm vi gọi trực tiếp của multicaster, Spring chuyển `Throwable` cho callback. **Điều ErrorHandler làm sau đó** quyết định lỗi bị bỏ qua để tiếp tục hay được ném lại cho luồng gọi.

Đây là cơ chế kiểm soát lỗi **khi phân phối event trong cùng ApplicationContext**. Nó không tự cung cấp retry, transaction rollback có chủ đích, hàng đợi bền vững, dead-letter queue hay thông báo qua nhiều tiến trình.

## 2. Vị trí của ErrorHandler trong đường đi của event

Luồng xử lý điển hình:

```text
ApplicationEventPublisher.publishEvent(event)
    |
    v
ApplicationEventMulticaster.multicastEvent(event)
    |
    +--> xác định ApplicationListener phù hợp
    |
    +--> listener 1 ---> thành công
    |
    +--> listener 2 ---> ném Throwable
    |                        |
    |                        +--> ErrorHandler.handleError(error)
    |                                  |
    |                                  +--> trả về bình thường: tiếp tục vòng lặp
    |                                  |
    |                                  +--> ném lại lỗi: lỗi tiếp tục lan truyền
    |
    +--> listener 3 (nếu vòng phân phối vẫn tiếp tục)
```

Ở mức khái niệm, phương thức gọi listener của `SimpleApplicationEventMulticaster` có hành vi tương đương:

```java
// Mã minh họa cơ chế, không phải bản sao đầy đủ mã nguồn Spring.
if (errorHandler != null) {
    try {
        invokeActualListener(listener, event);
    } catch (Throwable error) {
        errorHandler.handleError(error);
    }
} else {
    invokeActualListener(listener, event);
}
```

Một số điểm cần nắm:

1. `ApplicationEventMulticaster` là **hợp đồng phân phối**; `setErrorHandler` thuộc triển khai `SimpleApplicationEventMulticaster`. Không phải mọi triển khai multicaster tự viết đều có cùng chính sách bắt lỗi.
2. Với `@EventListener`, Spring tạo một adapter theo `ApplicationListener`. Ngoại lệ đồng bộ do phương thức listener ném ra thường đi qua đường gọi của multicaster, nên ErrorHandler có thể nhận được.
3. ErrorHandler nhận **lỗi**, không được trao sẵn đối tượng event, tên listener hay kết quả xử lý. Nếu cần log theo `eventId`/`listenerName`, phải thiết kế cơ chế ghi nhận context riêng.
4. ErrorHandler không tạo event khác và không quyết định listener có khớp kiểu hay `@EventListener(condition=...)` hay không; nó xử lý **thất bại tại lúc gọi** một listener đã được chọn.
5. Vì tham số là `Throwable`, handler có thể nhận cả `Error` nghiêm trọng. Chính sách suppress không nên nuốt vô điều kiện những lỗi hệ thống như `OutOfMemoryError`.

## 3. Ba chính sách phổ biến

| Chính sách | Trong multicaster đồng bộ | Phù hợp khi |
| --- | --- | --- |
| Không đặt `ErrorHandler` (mặc định) | Exception thường truyền ngược từ `publishEvent`; vòng gọi listener dừng tại lỗi chưa được bắt | Listener là phần bắt buộc của thao tác và caller cần biết thất bại |
| Handler **ghi nhận rồi trả về** (*suppress*) | Sau khi handler trả về, multicaster tiếp tục gọi các listener còn lại | Listener độc lập, lỗi không được phép chặn listener khác; có giám sát/phục hồi phù hợp |
| Handler **ném lại** (*propagate*) | Exception tiếp tục lan truyền; các listener phía sau trong cùng vòng gọi đồng bộ không chạy | Lỗi phải được báo cho caller, nhưng muốn log/đính kèm chẩn đoán tập trung |

Có thể diễn đạt hành vi quan trọng bằng bảng quyết định:

| Cấu hình | A thành công | B ném exception | C phía sau có chạy? | Bên publish có thấy exception từ B? |
| --- | --- | --- | --- | --- |
| Đồng bộ, không handler | Có | Không được xử lý tại multicaster | **Không**, nếu B ném trước C | **Có**, trừ khi phía ngoài bắt |
| Đồng bộ, handler suppress | Có | Handler xử lý rồi trả về | **Có**, nếu không phát sinh lỗi khác | **Không**, với lỗi đã suppress |
| Đồng bộ, handler rethrow | Có | Handler ném lỗi ra | **Không**, nếu B ném trước C | **Có**, trừ khi phía ngoài bắt |
| TaskExecutor bất đồng bộ | Phụ thuộc task | Handler chạy trong luồng task của listener được giao | Không có bảo đảm thứ tự hoàn tất; task khác có thể vẫn chạy | Thông thường **không** nhận exception thực thi trong task qua luồng gọi `publishEvent` |

“Tiếp tục” ở đây chỉ có nghĩa **đa phần các listener còn lại vẫn được thử gọi** sau khi handler trả về. Nó không bảo đảm những listener đó chạy thành công, cũng không có nghĩa một listener thất bại được chạy lại.

## 4. Cấu hình trong Spring: bean tên `applicationEventMulticaster`

Khi tạo `ApplicationContext`, Spring tìm bean có **tên chính xác** `applicationEventMulticaster`. Nếu không có, context dùng multicaster mặc định. Muốn thay đổi chính sách xử lý lỗi, cách trực tiếp là khai báo một `SimpleApplicationEventMulticaster` với tên bean chuẩn đó:

```java
@Configuration
class EventConfig {

    @Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
    SimpleApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error -> {
            // Chỉ phù hợp khi các lỗi listener được phép bỏ qua.
            System.err.println("Event listener failed: " + error.getMessage());
        });

        return multicaster;
    }
}
```

Các import cần thiết cho đoạn này gồm `org.springframework.context.annotation.Configuration`, `Bean`, `org.springframework.context.event.SimpleApplicationEventMulticaster` và `org.springframework.context.support.AbstractApplicationContext`.

Đây là **đoạn cấu hình minh họa** để đặt trong ứng dụng Spring, chưa phải chương trình độc lập. Nếu muốn tích hợp vào Spring Boot, cũng có thể khai báo bean trong một lớp `@Configuration` được quét bởi ứng dụng; cấu hình bean multicaster không cần một API riêng của Boot.

Lưu ý:

- **Tên bean quyết định việc Spring dùng nó như event multicaster của context**. Khai báo bean tên `customMulticaster` rồi kỳ vọng nó tự thay thế mặc định là sai.
- Chỉ thay giá trị `userEnteredValue` hay viết code listener không cấu hình ErrorHandler. Chính sách lỗi nằm ở multicaster, không phải ở từng annotation `@EventListener`.
- Không thể kết luận “mọi event trong hệ thống đều sử dụng một ErrorHandler” nếu ứng dụng có nhiều `ApplicationContext`, custom multicaster khác hoặc cơ chế messaging riêng.
- Callback chỉ ghi `getMessage()` không đủ chẩn đoán trong môi trường production. Nên ghi stack trace, kiểu event/correlation ID khi có thể, và metrics theo listener.

## 5. Ví dụ chạy được: mặc định dừng, handler suppress thì tiếp tục

Ví dụ này sử dụng **Java 17+** và **Spring Framework 6.2.12** trên Maven. Nó tạo hai `ApplicationContext` độc lập:

- Context thứ nhất dùng multicaster mặc định.
- Context thứ hai khai báo ErrorHandler ghi nhận lỗi rồi trả về.

Trong mỗi context, listener thứ nhất cố ý ném `IllegalStateException`; listener thứ hai in thông báo khi được gọi. `@Order` tạo thứ tự rõ ràng để minh họa hành vi đồng bộ.

Cấu trúc:

```text
multicaster-errors/
├── pom.xml
└── src/main/java/demo/MulticasterErrorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multicaster-errors</artifactId>
    <version>1.0-SNAPSHOT</version>

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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.MulticasterErrorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/MulticasterErrorDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.annotation.Order;

public class MulticasterErrorDemo {

    public record ReportReady(String reportId) {}

    @Configuration(proxyBeanMethods = false)
    public static class ListenerConfig {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @EventListener
        @Order(1)
        public void writeAudit(ReportReady event) {
            System.out.println("FIRST " + event.reportId());
            throw new IllegalStateException("audit unavailable");
        }

        @EventListener
        @Order(2)
        public void updateMetrics(ReportReady event) {
            System.out.println("SECOND " + event.reportId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class SuppressingMulticasterConfig {

        @Bean(name =
                AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public SimpleApplicationEventMulticaster applicationEventMulticaster() {
            var multicaster = new SimpleApplicationEventMulticaster();
            multicaster.setErrorHandler(error ->
                    System.out.println("HANDLED " + error.getMessage()));
            return multicaster;
        }
    }

    private static void execute(String label, boolean enableHandler) {
        System.out.println("=== " + label + " ===");

        try (var context = new AnnotationConfigApplicationContext()) {
            context.register(ListenerConfig.class);
            if (enableHandler) {
                context.register(SuppressingMulticasterConfig.class);
            }
            context.refresh();

            try {
                context.publishEvent(new ReportReady("R-42"));
            } catch (IllegalStateException error) {
                System.out.println("PUBLISH_FAILED " + error.getMessage());
            }
        }
    }

    public static void main(String[] args) {
        execute("DEFAULT", false);
        execute("WITH_HANDLER", true);
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

Các dòng do chương trình chủ động in bằng `System.out.println`:

```text
=== DEFAULT ===
FIRST R-42
PUBLISH_FAILED audit unavailable
=== WITH_HANDLER ===
FIRST R-42
HANDLED audit unavailable
SECOND R-42
```

Giải thích:

1. Cả hai context đều đăng ký `Handlers`. Spring biến hai phương thức `@EventListener` thành các listener cho `ReportReady`.
2. Trường hợp `DEFAULT` không có ErrorHandler, `writeAudit` ném ngoại lệ và lời gọi `context.publishEvent(...)` ném ra. `updateMetrics` không được gọi vì lỗi đã làm gián đoạn vòng phân phối đồng bộ.
3. Trường hợp `WITH_HANDLER` sử dụng bean multicaster mang tên chuẩn, callback được gọi sau khi `writeAudit` lỗi.
4. Callback in `HANDLED ...` và **trả về bình thường**. Multicaster tiếp tục đến `updateMetrics`, vì thế xuất hiện `SECOND R-42`.
5. Bản thân `publishEvent(...)` không biết việc ghi audit thất bại trong kịch bản suppress; người phát event chỉ thấy lời gọi trả về bình thường.

Ví dụ không sử dụng transaction hay executor để kết quả có thứ tự dễ quan sát. Việc in console chỉ dùng cho học tập; ở production cần logging và metrics thích hợp.

## 6. Nếu ErrorHandler ném ngoại lệ trở lại thì sao?

ErrorHandler không bắt buộc phải nuốt lỗi:

```java
multicaster.setErrorHandler(error -> {
    // Chẩn đoán rồi buộc luồng gọi biết việc xử lý thất bại.
    System.err.println("Listener failed: " + error.getMessage());

    if (error instanceof Error fatal) {
        throw fatal;
    }
    if (error instanceof RuntimeException runtime) {
        throw runtime;
    }
    throw new IllegalStateException("Listener failed", error);
});
```

Đây là đoạn **cấu hình minh họa** thay cho lambda ở ví dụ trên. Khi handler ném exception trong kiểu phân phối đồng bộ, exception đi ra từ lời gọi listener, vòng gọi các listener tiếp theo bị ngắt và bên publish có thể bắt được. Nếu ném một exception mới có bọc `cause`, hãy giữ nguyên nguyên nhân gốc để truy vết.

Ngược lại, handler chỉ ghi log rồi trả về có thể khiến yêu cầu HTTP hoặc transaction nghiệp vụ **trông như đã thành công**, dù side effect của listener chưa hoàn tất. Đây không nhất thiết là lỗi: audit/analytics độc lập thường không nên chặn thanh toán; nhưng với kiểm tra bắt buộc trước khi hoàn tất thanh toán, suppress là chính sách nguy hiểm.

Spring có các helper mang ý nghĩa `LOG_AND_SUPPRESS_ERROR_HANDLER` và `LOG_AND_PROPAGATE_ERROR_HANDLER` trong `org.springframework.scheduling.support.TaskUtils`. Có thể tham khảo khi cần chính sách chuẩn, nhưng handler riêng thường cần log giàu ngữ cảnh hơn. Đừng nhầm helper logging với retry hay circuit breaker.

## 7. ErrorHandler với TaskExecutor bất đồng bộ

`SimpleApplicationEventMulticaster` cho phép cấu hình `setTaskExecutor(...)`. Khi có executor, những listener hỗ trợ async execution có thể được giao cho task khác, trong khi một số listener đặc biệt yêu cầu thực thi trên luồng gốc.

Ví dụ **minh họa cấu hình** (không phải chương trình độc lập):

```java
@Bean(name = AbstractApplicationContext.APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
SimpleApplicationEventMulticaster applicationEventMulticaster(
        TaskExecutor eventExecutor) {

    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(eventExecutor);
    multicaster.setErrorHandler(error ->
            log.error("Application event listener failed", error));

    return multicaster;
}
```

Đoạn này giả định ứng dụng đã khai báo `TaskExecutor eventExecutor` và biến `log`. Không nên đặt executor một cách tùy tiện trong thư viện hoặc tạo thread không giới hạn cho tải production; cần cấu hình pool, queue, rejection policy và shutdown.

Với listener thực sự được executor chạy:

- Phần thân listener có thể chạy **sau khi** `publishEvent(...)` trả về.
- ErrorHandler gắn trên multicaster vẫn có thể bắt lỗi do listener ném **trong task mà multicaster tạo**, nhưng handler đó chạy trong **luồng executor**.
- Nếu handler ném lại lỗi, lỗi tiếp tục trên **luồng task**; bên gọi `publishEvent(...)` thường không nhận trực tiếp ngoại lệ thực thi đó.
- Không có bảo đảm listener thực thi hoặc hoàn tất theo thứ tự `@Order` như trường hợp đồng bộ; `@Order` không tạo đồng bộ hóa giữa các task.
- Nếu executor từ chối nhận task, lỗi phát sinh **khi nộp task** có thể truyền về publisher; đây không giống lỗi ném từ bên trong listener sau khi task bắt đầu.
- Thread-local state, security context và transaction context của publisher **không tự động được sao chép** vào thread của listener.

Cần phân biệt **executor của multicaster** với `@Async` gắn trực tiếp lên phương thức listener. Với `@Async`, proxy có thể trả về trước khi phần thân phương thức chạy; lỗi xảy ra sau đó do cơ chế `@Async` xử lý (ví dụ `AsyncUncaughtExceptionHandler` cho phương thức `void`), nên không thể kỳ vọng ErrorHandler của multicaster luôn bắt được lỗi ở phần thân phương thức async. Nếu muốn chính sách nhất quán, xác định rõ ứng dụng sử dụng cơ chế async nào.

**Quy tắc đọc log:** “handler đã xử lý” không có nghĩa publisher biết lỗi. Cần correlation ID, giám sát tác vụ và cơ chế retry riêng khi có yêu cầu tin cậy.

## 8. Quan hệ với transaction và @TransactionalEventListener

Đây là một điểm dễ gây nhầm lẫn.

### 8.1. Listener đồng bộ trong giao dịch

Giả sử một phương thức `@Transactional` phát event và listener đồng bộ ném `RuntimeException`:

- Nếu không có ErrorHandler hoặc handler ném lại, ngoại lệ có thể đi ra khỏi phương thức giao dịch, khiến interceptor transaction đánh dấu rollback theo quy tắc rollback đang áp dụng.
- Nếu handler suppress và không còn lỗi khác, phương thức nghiệp vụ có thể tiếp tục và transaction **có thể commit** dù listener đã thất bại.
- Việc transaction có rollback hay không vẫn phụ thuộc loại exception, nơi exception bị bắt, cấu hình rollback và trạng thái transaction thực tế. Không suy ra đơn giản rằng “có ErrorHandler thì luôn commit”.

Nếu side effect của listener là điều kiện bắt buộc để thao tác nghiệp vụ hợp lệ, hãy cân nhắc đặt nó trực tiếp trong application service hoặc thiết kế giao dịch rõ ràng, thay vì coi một listener dễ bỏ qua là bước xác thực bắt buộc.

### 8.2. @TransactionalEventListener có vòng đời khác

`@TransactionalEventListener` có thể chạy tại `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION`. Với cấu hình mặc định, nó không xử lý event nếu không có transaction đang hoạt động, trừ khi `fallbackExecution = true`.

Ví dụ minh họa:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderPlaced event) {
    sendNotification(event);
}
```

Đây là đoạn phương thức bên trong Spring bean; `OrderPlaced` và `sendNotification` là các thành phần ứng dụng minh họa.

Ở phase sau commit, callback thực sự thường được thực thi **về sau bởi cơ chế transaction synchronization**, không nằm trong lời gọi tức thời của `SimpleApplicationEventMulticaster.invokeListener`. Vì vậy, **ErrorHandler của multicaster không phải cơ chế tổng quát để bắt mọi lỗi phát sinh từ logic deferred của `@TransactionalEventListener`**. Phải theo dõi và xử lý lỗi ở tầng callback/transaction phù hợp.

Trong các phiên bản Spring hiện đại, transactional listeners mặc định không hỗ trợ chuyển việc gọi listener sang executor của multicaster vì phải giữ ngữ cảnh transaction; điều đó **không biến** callback after-commit thành một thao tác retry bền vững.

Nếu phải bảo đảm thông điệp ra ngoài được phát **sau commit**, đồng thời không bị mất khi tiến trình chết, xem xét transactional outbox và hệ thống truyền tin bền vững. Chỉ đặt `AFTER_COMMIT` và một ErrorHandler không tạo ra bảo đảm đó.

## 9. Chọn chính sách lỗi theo độ quan trọng của listener

Một ứng dụng thường có nhiều loại listener:

| Loại xử lý | Ví dụ | Hướng xử lý lỗi nên cân nhắc |
| --- | --- | --- |
| Bắt buộc để hoàn tất nghiệp vụ | Xác thực điều kiện trước khi chấp nhận tác vụ | Không suppress âm thầm; cân nhắc gọi trực tiếp trong service |
| Độc lập, ưu tiên không chặn request | Thu thập số liệu, ghi trace phụ | Suppress có log/metrics, cảnh báo phù hợp |
| Quan trọng nhưng có thể thực hiện lại | Gửi email sau khi đơn đã thanh toán | Tách thành job/message bền vững, retry có giới hạn, idempotency |
| Bắt buộc theo transaction | Ghi dữ liệu liên quan trong cùng transaction | Thiết kế cùng transaction rõ ràng, giám sát rollback |
| Xử lý nhiều consumer độc lập | Audit, metrics, notification | Quy định failure policy theo consumer; cân nhắc tách multicaster/executor hoặc giao thức riêng |

**Một ErrorHandler trên multicaster áp dụng chung cho những listener được multicaster đó gọi.** Nếu vài listener cần fail-fast trong khi vài listener khác cần best-effort, một lambda “log rồi bỏ qua mọi lỗi” là chính sách quá rộng.

Các phương án thường rõ ràng hơn:

1. Phân biệt việc bắt buộc trong luồng nghiệp vụ với side effect tùy chọn.
2. Để listener tùy chọn tự xử lý lỗi dự kiến của nó, báo cáo đúng metric/trace.
3. Dùng message queue/outbox cho công việc không thể mất và cần retry.
4. Chỉ sử dụng global ErrorHandler khi một chính sách chung thật sự phù hợp với các listener trong context đó.

## 10. Ghi log ErrorHandler sao cho hữu dụng

Ghi duy nhất `error.getMessage()` thường không đủ. Một báo cáo lỗi nên có:

- **Loại exception** và stack trace, gồm `cause`.
- **Loại event và ID nghiệp vụ** nếu đã đưa được context vào log.
- **Tên listener/tác vụ** đang chạy; `ErrorHandler.handleError(Throwable)` chỉ nhận Throwable, nên cần instrumentation, wrapper hoặc logging tại listener nếu cần thông tin này.
- **Request ID/correlation ID** để nối với trace của thao tác gốc. Khi xử lý async, cần truyền context có chủ đích.
- **Số lần lỗi, tần suất và xu hướng**, cùng cảnh báo để biết listener đang hỏng dù request vẫn thành công.
- **Quyết định của chính sách**: đã suppress, đã propagate, hay sẽ retry bằng một cơ chế riêng.

Ví dụ mẫu xử lý lỗi với SLF4J (**đoạn minh họa, giả định có logger `log`**):

```java
multicaster.setErrorHandler(error -> {
    if (error instanceof Error fatal) {
        throw fatal;
    }
    log.error("Spring application event listener failed", error);
    // Returning normally means suppressing this listener failure.
});
```

Nếu mỗi listener cần một chính sách khác nhau, nên bổ sung log ngay tại listener và chỉ suppress các ngoại lệ đã được xác định là có thể phục hồi. Việc suppress toàn cục mọi RuntimeException có thể che giấu lỗi dữ liệu và vi phạm bất biến nghiệp vụ.

## 11. Kiểm thử ErrorHandler: không chỉ kiểm tra có log

Trong bài toán ví dụ, nên xác minh tối thiểu:

| Trường hợp | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Listener thành công | Listener A và B đều thành công | Cả hai được gọi, không có ErrorHandler |
| Listener lỗi, không handler | A lỗi trước B, đồng bộ | `publishEvent` ném lỗi, B không chạy |
| Listener lỗi, handler suppress | A lỗi trước B, đồng bộ | Handler ghi nhận lỗi; B vẫn chạy; publisher không ném lỗi do A |
| Listener lỗi, handler rethrow | A lỗi trước B, đồng bộ | Handler ghi nhận rồi ném lại; B không chạy |
| Hai listener cùng lỗi | Handler suppress | Handler được gọi cho từng lỗi; không “gộp” thành một exception |
| Async listener lỗi trong executor | Có TaskExecutor | Ghi nhận đúng trên task; publisher không chờ task hoàn tất |
| `@Async` listener lỗi sau khi proxy đã trả về | `@EnableAsync` được cấu hình | Kiểm tra đường xử lý lỗi của async proxy, không mặc định quy về multicaster handler |
| Transactional listener sau commit lỗi | `@TransactionalEventListener` | Kiểm tra tại phase callback, không chỉ theo dõi handler của multicaster |
| Executor từ chối task | Pool/queue đầy | Kiểm tra rejection policy và exception phát sinh khi giao task |

Khi viết test, nên dùng một recorder thread-safe hoặc `CountDownLatch`/`CompletableFuture` cho tình huống async; **không** dùng `Thread.sleep(...)` rồi suy diễn chắc chắn rằng listener đã hoàn tất. Với ví dụ đồng bộ, có thể assert thứ tự gọi cùng số lần ErrorHandler được kích hoạt.

Nên có thêm test trên chính giao dịch nghiệp vụ: handler suppress **có được phép** để request thành công khi một listener lỗi không? Kiểm thử policy đó quan trọng hơn việc xác nhận một chuỗi log cụ thể.

## 12. Các lỗi hiểu nhầm thường gặp

1. **Cấu hình một bean multicaster sai tên**: bean vẫn tồn tại nhưng context tiếp tục dùng multicaster mặc định.
2. **Tưởng ErrorHandler luôn chạy**: mặc định handler có thể chưa được cấu hình; nếu listener bắt và nuốt exception bên trong, multicaster không thấy exception đó.
3. **Cho rằng suppress tương đương khắc phục lỗi**: handler trả về không đồng nghĩa tác vụ listener hoàn tất hay được retry.
4. **Nghĩ mọi listener đều tiếp tục sau lỗi**: với handler rethrow hoặc không handler trong chế độ đồng bộ, vòng phân phối bị gián đoạn.
5. **Nhầm thứ tự @Order với thứ tự hoàn tất async**: TaskExecutor có thể chạy nhiều task song song.
6. **Kỳ vọng exception async truyền về publisher**: hai luồng thực thi khác nhau; cần cơ chế thu thập lỗi của executor/tác vụ.
7. **Nhầm ErrorHandler với AsyncUncaughtExceptionHandler**: `@Async` có đường xử lý exception riêng cho lỗi xảy ra sau khi proxy trả về.
8. **Nhầm ErrorHandler với transaction phase**: `@TransactionalEventListener` có thể chạy ở callback transaction về sau; không thể chỉ dựa vào handler lúc multicast.
9. **Suppress lỗi bắt buộc**: request/giao dịch có thể tiếp tục dù điều kiện quan trọng chưa đạt.
10. **Nuốt Throwable vô điều kiện**: che giấu lỗi JVM nghiêm trọng; luôn cân nhắc việc propagate `Error`.
11. **Không quan sát hệ thống**: policy suppress không có log/metrics khiến sự cố listener kéo dài mà không ai biết.
12. **Giả định có retry, exactly-once, persistence**: Spring Application Events nội bộ không tự bảo đảm các tính chất này.

## 13. Checklist trước khi bật ErrorHandler trên multicaster

- Listener nào được phép thất bại mà không ảnh hưởng kết quả nghiệp vụ?
- Listener nào phải báo lỗi về caller để rollback hoặc sửa dữ liệu?
- Đã xác định luồng synchronous, multicaster executor, hay `@Async` ở phương thức chưa?
- Đã xác minh bean multicaster có đúng tên `applicationEventMulticaster` chưa?
- Handler sẽ **suppress** hay **propagate**? Chính sách ấy áp dụng được cho mọi listener liên quan không?
- Có bảo vệ lỗi `Error` nghiêm trọng, log stack trace, correlation ID và metric lỗi không?
- Có công việc nào yêu cầu retry hoặc phân phối bền vững cần outbox/queue không?
- Có `@TransactionalEventListener` chạy về sau khiến ErrorHandler của multicaster không còn nằm trên đường gọi thực thi chính không?
- Đã viết test xác nhận hành vi của listener phía sau, bên publisher và transaction chưa?

**Điểm cần nhớ:** ErrorHandler của `SimpleApplicationEventMulticaster` là nơi quyết định một ngoại lệ của listener **được ghi nhận rồi cho phép phân phối tiếp** hay **được ném lại** trong đường gọi mà multicaster kiểm soát. Hãy chọn chính sách dựa trên trách nhiệm nghiệp vụ của listener và bối cảnh đồng bộ/bất đồng bộ; không coi việc suppress lỗi là bảo đảm đã xử lý thành công event.

**Tài liệu tham khảo:**

- [Spring Framework Reference — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [ErrorHandler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/ErrorHandler.html)
- [Transactional Application Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
