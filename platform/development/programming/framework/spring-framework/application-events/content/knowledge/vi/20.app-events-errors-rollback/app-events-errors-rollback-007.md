# Fallback và xử lý lỗi có chủ đích trong Spring Application Events

## 1. Tại sao phải thiết kế fallback thay vì chỉ try/catch?

Spring Application Events cho phép một thành phần phát thông tin đã xảy ra bằng `ApplicationEventPublisher.publishEvent(...)` và để những listener phù hợp phản ứng. Nhưng “event đã được publish” **không đồng nghĩa** “mọi listener đã thành công”, “transaction đã commit” hoặc “event có thể được xử lý lại sau khi ứng dụng crash”.

Trong bài này, **fallback** là một **đường xử lý thay thế được thiết kế trước** khi đường bình thường không thể tiếp tục: tiếp tục dù lỗi không thiết yếu, chạy công việc trên caller khi executor từ chối, xử lý event khi không có transaction, lưu nhiệm vụ vào outbox/queue bền vững, hoặc chuyển sang quy trình bù trừ. Mỗi cách có điều kiện kích hoạt và độ tin cậy khác nhau.

Một thiết kế xử lý lỗi có chủ đích phải trả lời:

1. **Lỗi ở đâu?** Listener, executor, transaction, downstream hay transport?
2. **Ai chịu trách nhiệm?** Publisher, multicaster, listener, transaction manager hay worker retry?
3. **Có thể tiếp tục không?** Bước quan trọng hay chỉ là side effect phụ?
4. **Bảo toàn sự thật như thế nào?** Có commit, được lưu bền vững, có thể gửi lại hay không?
5. **Quan sát thế nào?** Lỗi phải đo được; suppress không được trở thành “giấu lỗi”.
6. **Có an toàn khi thử lại không?** Idempotency, duplicate và thứ tự cần được xác định.

**Nguyên tắc:** Chọn fallback theo **mức độ quan trọng của công việc** và **điều kiện thực thi**, không đặt một `catch (Exception)` chung rồi coi mọi event đều đã được xử lý.

## 2. Bốn nghĩa “fallback” dễ bị nhầm

| Cơ chế | Khi nào kích hoạt? | Spring cung cấp gì? | Không phải điều gì? |
| --- | --- | --- | --- |
| **Multicaster ErrorHandler** | Listener ném lỗi khi multicaster gọi nó | Có thể xử lý/log rồi suppress, hoặc ném tiếp | Không tự retry hoặc lưu event |
| **Executor rejection fallback** | Executor của `SimpleApplicationEventMulticaster` từ chối scheduling | Ở triển khai có nhánh bắt `RejectedExecutionException`, listener được gọi tại caller | Không phải bảo đảm fail-fast hay backpressure bền vững |
| **Transactional listener fallbackExecution** | Event được publish mà **không có transaction tương ứng** | `@TransactionalEventListener(fallbackExecution=true)` có thể xử lý ngay | Không phải fallback sau rollback, không thay thế `AFTER_ROLLBACK` |
| **Business/reliability fallback** | Thao tác ngoài thất bại, queue đầy, mạng đứt, consumer lỗi… | Ứng dụng tự thiết kế retry, outbox, DLQ, compensation… | Spring in-process events không tự bảo đảm giao hàng |

Hai chữ “fallback” trong `fallbackExecution` và “fallback khi executor bị từ chối” **không liên quan trực tiếp**. Một cái là lựa chọn có xử lý event khi không có transaction; cái kia là cách phân phối listener khi task không được executor chấp nhận.

Nếu gặp câu hỏi “có fallback không?”, hãy hỏi tiếp “**fallback từ bước nào sang bước nào, được phép mất việc không, và ai biết kết quả?**”.

## 3. Luồng lỗi đi qua ApplicationEventPublisher thế nào?

`ApplicationEventPublisher.publishEvent(Object)` giao event cho cơ chế phân phối trong context. Với `SimpleApplicationEventMulticaster` mặc định, các listener chạy **đồng bộ trên luồng publisher**. Khi cấu hình `TaskExecutor`, listener hỗ trợ async có thể được giao sang thread khác.

```text
Application service
      |
      v
publishEvent(event)
      |
      v
SimpleApplicationEventMulticaster
      |
      +---- Listener A (sync hoặc async)
      |          |
      |          +--> thành công
      |          |
      |          +--> ném exception
      |                   |
      |             ErrorHandler?
      |             /         \
      |         Không          Có
      |           |             |
      |     propagate theo     suppress hoặc
      |     đường thực thi     rethrow theo policy
      |
      +---- Listener B
             |
             +--> có thể không được gọi nếu
                  lỗi sync đã chặn vòng phân phối

Khi có async executor:
   execute(listenerTask)
      |
      +--> accepted: chạy trên worker khi đến lượt
      |
      +--> RejectedExecutionException:
             nhánh fallback của SimpleApplicationEventMulticaster
             có thể gọi listener trực tiếp ở caller
```

Các lưu ý:

- Trong đường **sync**, lỗi không được xử lý có thể đi ngược về `publishEvent(...)`, làm publisher nhận exception. Những listener phía sau có thể chưa được gọi.
- Trong đường **async**, publisher có thể trở về trước khi listener thực thi. Lỗi xảy ra sau đó không tự nhảy ngược về stack của publisher.
- Với listener `@Async`, cơ chế xử lý exception còn liên quan tới `AsyncUncaughtExceptionHandler` (đặc biệt khi phương thức trả `void`); nó không đồng nhất với `ErrorHandler` của multicaster.
- Với transactional listener, việc đăng ký callback và thời điểm gọi sau commit/rollback phụ thuộc `TransactionPhase`; không nên coi nó như listener sync bình thường ở mọi giai đoạn.

**Không thiết kế tính đúng đắn dựa trên suy đoán** rằng mọi listener đều được gọi đúng một lần hoặc bất kỳ exception nào đều tự rollback được transaction.

## 4. Lỗi của listener đồng bộ: propagate hay suppress?

### 4.1. Mặc định: không có ErrorHandler

`SimpleApplicationEventMulticaster` mặc định **không đặt `ErrorHandler`**. Khi listener đồng bộ ném exception:

- Exception có thể truyền ngược tới nơi phát event.
- Vòng phân phối có thể dừng tại listener đó; các listener được xếp sau chưa chắc được gọi.
- Nếu lời gọi publish nằm trong một phương thức `@Transactional` và exception lan ra khỏi transaction boundary, transaction manager có thể quyết định rollback theo rule áp dụng.
- Nếu caller bắt rồi nuốt exception **bên trong** method transaction, transaction có thể vẫn commit; rollback không tự động chỉ vì đã từng xảy ra exception.

Không nên mô tả “một event lỗi thì Spring luôn rollback tất cả”. Spring Application Events là cơ chế thông báo, không phải transaction manager.

### 4.2. Đặt ErrorHandler để chủ động tiếp tục

Với một event audit/telemetry **không thiết yếu**, có thể chấp nhận việc listener A lỗi nhưng listener B vẫn có cơ hội chạy.

```java
import org.springframework.context.event.SimpleApplicationEventMulticaster;

SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();

multicaster.setErrorHandler(error -> {
    // Mẫu đơn giản: thay bằng log/metric/alert có kiểm soát.
    System.err.println("Listener failed: " + error.getClass().getName());
    // Không throw -> lỗi được suppress tại đây.
});
```

Đây là **đoạn cấu hình minh họa**, chưa đăng ký multicaster làm bean Spring. Trong ứng dụng, bean dùng tên chuẩn `applicationEventMulticaster`; ví dụ chạy được ở phần 8 minh họa đầy đủ.

Khi `ErrorHandler.handleError(Throwable)` **trả về bình thường**, multicaster coi lỗi listener đã được xử lý và có thể tiếp tục listener kế tiếp. Khi handler **ném exception**, lỗi tiếp tục lan theo đường gọi; nếu sync, publisher có thể nhận lỗi.

Spring có các chính sách hỗ trợ như `TaskUtils.LOG_AND_SUPPRESS_ERROR_HANDLER` và `TaskUtils.LOG_AND_PROPAGATE_ERROR_HANDLER`. Tuy nhiên, việc “log rồi bỏ qua” không phù hợp với tác vụ tạo hóa đơn, ghi sổ tiền hoặc gửi thông điệp bắt buộc phải hoàn thành.

### 4.3. Khi không nên suppress

Nếu listener thực hiện một bước **bắt buộc** để nghiệp vụ được xem là thành công, suppress có thể khiến caller nhận kết quả thành công giả:

```text
Publisher: "Đã phê duyệt hóa đơn"
  |
  +--> Listener ghi dữ liệu pháp lý bị lỗi
  |
  +--> ErrorHandler suppress
  |
  +--> Caller thấy thành công
```

Nếu dữ liệu pháp lý là điều kiện bắt buộc, tốt hơn đưa thao tác đó vào transaction/business workflow có hợp đồng lỗi rõ ràng, hoặc lưu nhiệm vụ bền vững để đảm bảo xử lý tiếp. Một event phụ chỉ nên được coi là best effort khi **nghiệp vụ cho phép**.

### 4.4. ErrorHandler không phải hệ thống retry

`setErrorHandler(...)` nhận lỗi do listener ném. Spring không tự giữ một bản event bền vững, không tự triển khai exponential backoff, không giới hạn retry và không tạo dead-letter queue. Tự gọi lại listener ngay trong handler có thể gây đệ quy, lặp vô hạn, side effect kép và thiếu transaction boundary.

Một handler thực tế nên ghi nhận error classification, event identity, listener identity và correlation; nếu phải retry, hãy đưa công việc vào **một cơ chế được quản lý** có retry budget và idempotency rõ ràng.

## 5. Executor từ chối: fallback sang luồng caller không giống fail-fast

Khi dùng `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, một số listener được nộp thành task vào executor. Nếu executor ném `RejectedExecutionException` khi gọi `execute(...)`, các phiên bản triển khai Spring có logic **gọi listener trực tiếp trên luồng đang publish** như một fallback, thay vì mặc nhiên bỏ event.

Hậu quả cần tính:

1. **Giới hạn thread/queue không đồng nghĩa giới hạn tổng lượng công việc**: nếu nhiều publisher cùng bị đẩy sang xử lý tại chỗ, tổng số listener chạy đồng thời có thể tăng ngoài pool.
2. **Latency caller tăng**: HTTP request hoặc luồng xử lý transaction có thể phải chạy một listener nặng.
3. **Thread context khác dự kiến**: listener có thể nhìn thấy transaction/ThreadLocal của caller trong fallback nhưng không thấy chúng trong đường async thông thường.
4. **Lỗi listener có thể quay về caller** khi được chạy trực tiếp và không bị ErrorHandler suppress.
5. **Không được suy ra rằng `AbortPolicy` làm `publishEvent(...)` luôn ném `TaskRejectedException`**: đó chỉ là hành vi executor, còn multicaster có tầng xử lý riêng.

Đường fallback này hữu ích để tránh mất notification khi pool đang shutdown, nhưng **không phải hợp đồng đảm bảo backpressure phù hợp cho mọi domain**. Hãy kiểm tra đúng phiên bản Spring đang chạy, vì implementation của multicaster là yếu tố quyết định cuối cùng.

Một ví dụ executor cố tình từ chối:

```java
SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(task -> {
    throw new RejectedExecutionException("simulated overload");
});
```

Đây là đoạn minh họa; cần import `java.util.concurrent.RejectedExecutionException` và đăng ký đúng multicaster trong ApplicationContext để chạy. Ví dụ hoàn chỉnh ở phần 8 có chế độ `reject` và cho thấy listener vẫn được gọi trực tiếp.

**Chú ý:** Một số `ApplicationListener` tuy có executor nhưng khai báo `supportsAsyncExecution() == false`, ví dụ transactional listener cần gắn với transaction. Chúng được gọi trên thread publisher chứ không được submit vào pool.

### Khi cần admission control thật sự

Nếu điều kiện nghiệp vụ là “khi quá tải phải trả kết quả từ chối ngay”, đừng trông chờ `AbortPolicy` của executor multicaster là toàn bộ cơ chế. Cần giới hạn việc nhận yêu cầu ở **trước** bước publish, hoặc gửi tác vụ tới queue/broker có giao thức accept/reject rõ ràng.

Khi cần “không mất event”, fallback sang caller cũng chưa đủ: caller có thể crash, listener có thể ném lỗi, hoặc transaction có thể rollback.

## 6. @TransactionalEventListener: phase và fallbackExecution

`@TransactionalEventListener` khác `@EventListener` thông thường vì callback được gắn với kết quả **transaction đang hoạt động**.

Các phase:

| TransactionPhase | Thời điểm | Tình huống |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit thật sự | Kiểm tra/chuẩn bị công việc cần ràng buộc với transaction |
| `AFTER_COMMIT` (mặc định) | Sau commit thành công | Side effect chỉ có ý nghĩa nếu dữ liệu đã commit |
| `AFTER_ROLLBACK` | Sau rollback | Dọn dẹp, thông báo có chủ đích về thất bại |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback | Metrics/cleanup chung, phân biệt kết quả khi cần |

### 6.1. Fallback mặc định là tắt

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // Chỉ xử lý khi phát event trong transaction và transaction commit.
}
```

Đoạn trên là phương thức minh họa trong Spring bean có transaction manager. **Nếu không có transaction đang hoạt động tại lúc publish**, Spring mặc định **bỏ qua callback transactional này**. Event không phải bị xóa khỏi ApplicationContext; chỉ listener có điều kiện transaction không thực thi.

Việc bỏ qua này là một **quyết định bảo vệ semantics**: không thể hứa “sau commit” khi chưa có transaction nào để commit.

### 6.2. fallbackExecution=true: chạy khi không có transaction

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void afterCommitOrNoTransaction(OrderPlaced event) {
    // Có transaction: sau commit thành công.
    // Không có transaction: xử lý khi event được publish.
}
```

Hai trường hợp phải được phân biệt rõ:

- **Có transaction:** listener gắn vào phase `AFTER_COMMIT` và chỉ chạy khi transaction commit thành công.
- **Không có transaction:** listener được gọi ngay theo đường fallback; **không hề có commit xảy ra**.

Khi transaction tồn tại nhưng **rollback**, `fallbackExecution=true` **không làm listener AFTER_COMMIT chạy lại**. Fallback chỉ xử lý tình huống **không có transaction**, không phải “sau khi commit thất bại”.

### 6.3. Tránh fallbackExecution=true với AFTER_ROLLBACK khi không chủ định

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK,
        fallbackExecution = true)
public void ambiguousRollbackListener(OrderPlaced event) {
    // Không có transaction vẫn có thể được gọi qua fallback.
}
```

Đây là mẫu **cần cân nhắc kỹ**, vì khi không có transaction listener có thể thực thi ngay dù **chưa hề có rollback**. Đừng dùng tên method/metric kiểu “rollbackConfirmed” cho mọi lần gọi nếu có đường no-transaction fallback.

Nếu thật sự yêu cầu chỉ hành động sau rollback, thường nên để `fallbackExecution=false`.

### 6.4. Reactive transaction khác thread-bound transaction

Với transaction dùng `PlatformTransactionManager` trong mô hình thông thường, đồng bộ transaction gắn với thread. Từ Spring Framework 6.1, transactional listener còn có thể làm việc với reactive transaction khi **Reactor context được đưa vào event** theo cơ chế `TransactionalEventPublisher` phù hợp. Không thể lấy trạng thái reactive transaction từ `ThreadLocal` như transaction servlet thông thường.

Một event phát trên thread khác mà mất transaction context có thể khiến transactional listener không đăng ký đúng phase. Đừng “sửa” vấn đề đó bằng cách bật `fallbackExecution=true` một cách mù quáng; như vậy có thể khiến callback chạy trước khi dữ liệu commit.

## 7. Rollback không phải một loại lỗi listener đơn giản

Hãy phân biệt các mốc:

```text
@Transactional service
    |
    +--> thay đổi DB trong transaction
    |
    +--> publishEvent(OrderPlaced)
    |        |
    |        +--> @EventListener sync:
    |        |      chạy ngay khi publish
    |        |
    |        +--> @TransactionalEventListener AFTER_COMMIT:
    |        |      đăng ký callback
    |        |
    |        +--> @TransactionalEventListener AFTER_ROLLBACK:
    |               đăng ký callback
    |
    +--> transaction manager quyết định
             /                   \
            /                     \
          COMMIT                 ROLLBACK
            |                       |
            v                       v
       AFTER_COMMIT             AFTER_ROLLBACK
       callbacks                callbacks
```

Điểm then chốt:

- Listener `@EventListener` sync được gọi **trước khi transaction kết thúc**, nên exception có thể đi ngược vào service.
- Nếu exception lan ra khỏi transaction boundary, Spring rollback theo quy tắc transaction thích hợp; ví dụ runtime exceptions thường được rollback mặc định với declarative transactions, nhưng rules có thể tùy biến.
- Nếu exception đã được catch/suppress và service vẫn kết thúc bình thường, transaction **có thể commit**.
- Listener `AFTER_COMMIT` thất bại **không thể quay ngược thời gian để undo DB commit đã hoàn tất**.
- `AFTER_ROLLBACK` là hook quan sát kết quả rollback, không phải cách “làm cho bất kỳ exception nào ở listener đều rollback”.

**Cảnh báo về tài nguyên sau completion:** Ở phase `AFTER_COMMIT`/`AFTER_ROLLBACK`, transaction đã kết thúc nhưng một số tài nguyên transaction còn gắn với thread trong khoảng callback. Một lệnh ghi DB có vẻ chạy nhưng không được commit như transaction mới. Nếu cần lưu kết quả xử lý sau completion, thiết kế transaction mới rõ ràng (ví dụ service riêng với `REQUIRES_NEW` qua proxy thích hợp) hoặc queue/outbox.

### @Transactional và no-transaction khác nhau ở đâu?

Nếu `@TransactionalEventListener(fallbackExecution = true)` được gọi không có transaction, listener chạy ngay không có bảo đảm commit. Không dùng nó như “fallback an toàn” cho thao tác phải bền vững. Muốn event luôn phải đi cùng DB commit, cách đúng là **bắt buộc transaction tại producer** hoặc dùng transactional outbox.

## 8. Ví dụ Maven/Java 17 chạy được: bốn chế độ lỗi và fallback

Ví dụ này dùng **Java 17+**, **Spring Framework 6.2.12**, Maven và H2 in-memory để minh họa hai lớp cơ chế:

1. **`default`**: listener đầu ném lỗi, không có ErrorHandler; publisher nhận exception.
2. **`suppress`**: ErrorHandler ghi nhận/suppress, listener thứ hai vẫn được gọi.
3. **`reject`**: executor luôn từ chối; multicaster thử chạy listener trên caller.
4. **`tx`**: dùng transaction JDBC thật để minh họa callback `AFTER_COMMIT`, `AFTER_ROLLBACK` và `fallbackExecution=true` khi không có transaction.

Phần transaction dùng H2 chỉ để kích hoạt và quản lý transaction thật; không cần tạo bảng để minh họa phase callback. Kết quả là **thử cơ chế**, không phải một kiến trúc giao dịch production.

### 8.1. Cấu trúc dự án

```text
spring-event-fallback/
├── pom.xml
└── src/main/java/demo/EventFallbackDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-fallback</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                    <mainClass>demo.EventFallbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/EventFallbackDemo.java`:

```java
package demo;

import java.util.concurrent.RejectedExecutionException;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class EventFallbackDemo {

    public record FailureEvent(String id) {}
    public record RejectedEvent(String id) {}
    public record PhaseEvent(String id) {}

    public static final class Handlers {

        @Order(1)
        @EventListener
        public void first(FailureEvent event) {
            System.out.println("FIRST " + event.id());
            throw new IllegalStateException("simulated failure");
        }

        @Order(2)
        @EventListener
        public void second(FailureEvent event) {
            System.out.println("SECOND " + event.id());
        }

        @EventListener
        public void onRejected(RejectedEvent event) {
            System.out.println("REJECTED_EXECUTOR_FALLBACK " + event.id());
        }

        @Order(1)
        @EventListener
        public void immediate(PhaseEvent event) {
            System.out.println("IMMEDIATE " + event.id());
        }

        @Order(2)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(PhaseEvent event) {
            System.out.println("AFTER_COMMIT " + event.id());
        }

        @Order(3)
        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT,
                fallbackExecution = true)
        public void afterCommitOrNoTx(PhaseEvent event) {
            System.out.println("COMMIT_OR_NO_TX " + event.id());
        }

        @Order(4)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(PhaseEvent event) {
            System.out.println("AFTER_ROLLBACK " + event.id());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        Handlers handlers() {
            return new Handlers();
        }

        @Bean
        DataSource dataSource() {
            JdbcDataSource dataSource = new JdbcDataSource();
            dataSource.setURL("jdbc:h2:mem:eventfallback;DB_CLOSE_DELAY=-1");
            dataSource.setUser("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }
    }

    private static AnnotationConfigApplicationContext createContext(
            String mode) {
        var context = new AnnotationConfigApplicationContext();

        // Đăng ký trước refresh để context sử dụng multicaster này.
        context.registerBean(
                "applicationEventMulticaster",
                SimpleApplicationEventMulticaster.class,
                () -> {
                    var multicaster = new SimpleApplicationEventMulticaster();
                    if ("suppress".equals(mode)) {
                        multicaster.setErrorHandler(error ->
                                System.out.println("HANDLED "
                                        + error.getClass().getSimpleName()));
                    }
                    if ("reject".equals(mode)) {
                        multicaster.setTaskExecutor(task -> {
                            throw new RejectedExecutionException(
                                    "simulated pool saturation");
                        });
                    }
                    return multicaster;
                });

        context.register(Config.class);
        context.refresh();
        return context;
    }

    private static void runFailure(
            AnnotationConfigApplicationContext context) {
        try {
            context.publishEvent(new FailureEvent("F1"));
            System.out.println("PUBLISH_RETURNED");
        } catch (RuntimeException error) {
            System.out.println(
                    "PUBLISH_FAILED " + error.getClass().getSimpleName());
        }
    }

    private static void runReject(
            AnnotationConfigApplicationContext context) {
        System.out.println("BEFORE_REJECT");
        context.publishEvent(new RejectedEvent("R1"));
        System.out.println("AFTER_REJECT");
    }

    private static void runTransactions(
            AnnotationConfigApplicationContext context) {
        var template = new TransactionTemplate(
                context.getBean(PlatformTransactionManager.class));

        template.execute(status -> {
            context.publishEvent(new PhaseEvent("C1"));
            return null; // TransactionTemplate commit khi callback thành công.
        });

        template.execute(status -> {
            context.publishEvent(new PhaseEvent("R1"));
            status.setRollbackOnly();
            return null; // TransactionTemplate rollback do rollback-only.
        });

        context.publishEvent(new PhaseEvent("N1")); // Không có transaction.
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "default" : args[0];

        try (var context = createContext(mode)) {
            switch (mode) {
                case "default", "suppress" -> runFailure(context);
                case "reject" -> runReject(context);
                case "tx" -> runTransactions(context);
                default -> throw new IllegalArgumentException(
                        "mode must be default, suppress, reject or tx");
            }
        }
    }
}
```

Lưu ý: `import org.springframework.transaction.annotation.Propagation;` trong đoạn mã không được dùng; có thể bỏ dòng import đó mà không đổi hành vi hoặc kết quả. Java cho phép unused import hợp lệ về cú pháp, dù static analysis của một số dự án sẽ cảnh báo.

### 8.2. Chạy và hiểu từng chế độ

Chạy default:

```bash
mvn -q compile exec:java -Dexec.args=default
```

Các dòng do chương trình in (không tính log thư viện):

```text
FIRST F1
PUBLISH_FAILED IllegalStateException
```

**Tại sao không có SECOND?** Listener có `@Order(1)` ném `IllegalStateException`; multicaster đồng bộ không có ErrorHandler, nên exception làm ngừng đường gọi đang phân phối và đi tới publisher.

Chạy suppress:

```bash
mvn -q compile exec:java -Dexec.args=suppress
```

Các dòng ứng dụng:

```text
FIRST F1
HANDLED IllegalStateException
SECOND F1
PUBLISH_RETURNED
```

ErrorHandler được cài đặt cho multicaster đã nhận lỗi và **không ném tiếp**. Listener khác vẫn được gọi; từ phía publisher, `publishEvent` trả về bình thường. Đây là **best effort**, không chứng minh listener đầu đã thành công.

Chạy reject:

```bash
mvn -q compile exec:java -Dexec.args=reject
```

Các dòng ứng dụng:

```text
BEFORE_REJECT
REJECTED_EXECUTOR_FALLBACK R1
AFTER_REJECT
```

Executor chủ ý ném `RejectedExecutionException` cho mọi task. Multicaster theo triển khai được trình bày nhận sự từ chối và gọi listener trực tiếp. Kết quả nằm **giữa** hai dòng in của publisher, nên không thể coi event được chạy async trong trường hợp này.

Chạy transaction:

```bash
mvn -q compile exec:java -Dexec.args=tx
```

Các dòng ứng dụng theo thứ tự đăng ký callback và `@Order` trong ví dụ:

```text
IMMEDIATE C1
AFTER_COMMIT C1
COMMIT_OR_NO_TX C1
IMMEDIATE R1
AFTER_ROLLBACK R1
IMMEDIATE N1
COMMIT_OR_NO_TX N1
```

Ý nghĩa:

1. `C1` publish **trong transaction** rồi commit: listener thường chạy ngay, hai listener `AFTER_COMMIT` chạy sau commit.
2. `R1` publish **trong transaction** rồi rollback: listener thường vẫn đã chạy trước rollback; listener `AFTER_ROLLBACK` được gọi, nhưng hai listener `AFTER_COMMIT` không được gọi.
3. `N1` publish **không có transaction**: listener thường chạy ngay; listener `AFTER_COMMIT` mặc định bị bỏ qua; listener có `fallbackExecution=true` chạy ngay dù không có commit; `AFTER_ROLLBACK` cũng không chạy.

Đường H2 dùng transaction manager thật, không có “bảng nghiệp vụ”. Vì vậy đây chỉ là minh họa thời điểm listener, **không phải bài test atomicity của một nghiệp vụ ghi DB**.

### 8.3. Giới hạn của ví dụ

- Chế độ `reject` giả lập executor bị từ chối, không đo hiệu năng thật của một bounded thread pool.
- Chế độ `suppress` chỉ in lỗi thay vì metric/tracing/alert; production cần observability đủ để phát hiện lỗi ẩn.
- Chế độ `tx` không dùng `@Transactional` proxy mà dùng `TransactionTemplate`, để transaction boundary không mơ hồ.
- Chương trình không làm HTTP, gửi mail hoặc queue message; đây là các tác vụ cần thiết kế retry/fallback riêng.
- Tất cả event là object trong bộ nhớ của một JVM. Một lần `publishEvent` không tạo bất kỳ bản ghi outbox bền vững nào.
- Khi cấu hình multicaster bất đồng bộ hoặc `@Async`, thứ tự stdout và đường lỗi không còn giống ví dụ sync.

## 9. Chiến lược xử lý lỗi theo mức độ quan trọng

Không nên chọn một ErrorHandler toàn cục mà không phân loại listener. Có thể phân chia theo criticality:

### 9.1. Bước nghiệp vụ bắt buộc: fail fast hoặc transaction rõ ràng

Nếu không cập nhật ledger thì không được kết thúc thanh toán thành công, hãy giữ logic bắt buộc trong application/domain service hoặc transaction cần thiết. Không để một `@EventListener` best-effort quyết định tính đúng đắn cốt lõi chỉ bằng side effect ẩn.

Một cách nghĩ:

```text
Command CapturePayment
        |
        v
Validate + Authorize
        |
        v
Write canonical payment state + ledger (transaction boundary)
        |
        +--> fail -> command trả lỗi / rollback theo rule
        |
        +--> commit thành công -> có thể phát PaymentCaptured
```

Nếu hệ thống cần công bố ra ngoài mà không mất sự kiện giữa commit và publish, lưu **outbox record cùng transaction** rồi relay ra broker. Việc gọi `ApplicationEventPublisher` ngay sau commit không tự loại bỏ cửa sổ crash.

### 9.2. Side effect không thiết yếu: best effort có quan sát

Ví dụ cập nhật một cache có thể xây dựng lại:

- Listener lỗi không nhất thiết làm thất bại nghiệp vụ chính.
- Có thể suppress để consumer khác tiếp tục, **nhưng** phải ghi metric/log có ngữ cảnh và kênh repair phù hợp.
- Đừng log một câu “success” bao phủ cả pipeline khi thực tế listener có lỗi.

Ví dụ mô tả policy:

```text
CacheWarmupEvent
  ├── cache refresh thành công -> done
  └── lỗi cache -> metric + structured log
                  -> cache có TTL/tái tạo khi cần
                  -> không rollback đơn hàng
```

### 9.3. Công việc quan trọng nhưng có thể hoàn thành sau: durable retry

Ví dụ gửi hóa đơn điện tử đến một cổng ngoài có thể chậm/gián đoạn. Nếu phải đảm bảo xử lý về sau:

1. Ghi work item/outbox vào storage bền vững.
2. Worker nhận task với khóa idempotency ổn định.
3. Phân biệt transient error và permanent error.
4. Retry có giới hạn và backoff/jitter, không busy-loop.
5. Sau giới hạn, chuyển sang trạng thái xử lý thủ công/quarantine/DLQ.
6. Có replay tools với audit; tránh gửi hóa đơn trùng khi retry.
7. Bảo đảm trạng thái công việc được quan sát và cảnh báo.

Không có lớp `ErrorHandler` nào của Spring Application Events tự thực hiện chu trình trên.

### 9.4. Workflow phân tán cần bù trừ

Nếu một transaction nghiệp vụ trải qua nhiều hệ thống, “rollback” của database A không undo được email đã gửi hoặc khoản tiền đã thu bên provider. Khi cần, thiết kế **compensating action** có quy tắc cụ thể, ví dụ yêu cầu hoàn tiền sau khi đặt hàng bị hủy.

Compensation là một **hành động nghiệp vụ mới**, có thể thất bại và cần retry/idempotency riêng, không phải “đảo ngược mọi thứ” bằng cách ném exception.

## 10. Chọn retry, bỏ qua, bù trừ hay báo lỗi?

| Loại lỗi | Ví dụ | Chính sách gợi ý |
| --- | --- | --- |
| Input/domain invalid | Đơn hàng không hợp lệ | Trả lỗi/fail fast, không retry tự động |
| Authorization failure | Actor không có quyền tenant | Từ chối, không dùng fallback vượt quyền |
| Transient network error | HTTP 503, timeout tạm | Retry có giới hạn, backoff/jitter, idempotency |
| Permanent downstream rejection | Payload bị từ chối vì schema sai | Quarantine/DLQ hoặc sửa dữ liệu; không retry vô hạn |
| Executor saturation | Hết worker/queue | Admission control, scale hợp lý hoặc durable queue |
| Listener bug | `NullPointerException` do code | Log/alert, fix lỗi; retry không sửa bug |
| Transaction rollback | DB constraint, business validation | Không phát nhận định “đã commit”; AFTER_ROLLBACK nếu cần |
| No transaction context | Publish ngoài transaction | Dùng chính sách rõ ràng: bỏ qua listener transaction hoặc `fallbackExecution=true` khi hợp lệ |
| Worker/process crash | Event đang nằm trong RAM | Cần outbox/broker/storage bền vững nếu không được mất |
| Duplicate delivery | Broker retry/redelivery | Consumer idempotent theo event/business key |

**Không retry vô hạn** trên lỗi không thể phục hồi. **Không bỏ qua** lỗi mà hợp đồng nghiệp vụ yêu cầu phải xử lý. Mỗi policy nên có owner, giới hạn thời gian, số lần thử, kết quả cuối và cách giám sát.

## 11. Một số pattern có chủ đích

### Pattern A — ErrorHandler chỉ để quan sát lỗi không thiết yếu

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster() {
    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setErrorHandler(error -> {
        // Ghi error metric/log theo context, với chính sách redaction.
        // Không throw: listener khác có thể tiếp tục.
        errorMetrics.increment("spring_event_listener_failure");
        eventLogger.warn("Noncritical event listener failed", error);
    });
    return multicaster;
}
```

Đây là **đoạn thiết kế minh họa**, không chạy độc lập: `errorMetrics` và `eventLogger` là các dependency ứng dụng chưa được định nghĩa trong snippet, và cần import Spring Configuration/Bean phù hợp. Không nên áp dụng một cách mù quáng cho mọi event nếu có listener quan trọng.

### Pattern B — Quản lý lỗi ở chính listener với outcome rõ ràng

```java
@EventListener
public void onNotificationRequested(NotificationRequested event) {
    try {
        notificationSender.send(event.recipientId(), event.messageId());
    } catch (TemporaryTransportException ex) {
        retryQueue.enqueue(event); // Phải là queue có hợp đồng bền vững.
    }
}
```

Đoạn này là **pseudocode**: các type service/exceptions phải do ứng dụng định nghĩa. Nếu không ghi được vào retry queue, không được suppress lỗi rồi tuyên bố công việc đã được bảo toàn. Cần nêu rõ liệu `enqueue` có xác nhận bền vững trước khi listener trả về không.

Ngoài ra, phải tránh retry khi gửi thực tế đã thành công nhưng response bị mất; dùng idempotency key ổn định ở downstream khi có hỗ trợ.

### Pattern C — Transactional outbox

```text
@Transactional
  update business row
  insert outbox event (same database transaction)
  COMMIT
       |
       v
outbox relay polls/CDC
       |
       +--> broker success -> mark published
       |
       +--> failure -> retain + retry
       |
       v
consumer processes with deduplication
```

Outbox giúp tránh cửa sổ “DB đã commit nhưng process chết trước khi publish”, miễn phần update nghiệp vụ và outbox thực sự dùng **cùng transaction**. Nó vẫn thường có khả năng gửi trùng khi relay crash giữa gửi và đánh dấu đã gửi, nên cần idempotent consumer.

### Pattern D — After-rollback observability

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onOrderRolledBack(OrderAttempted event) {
    // Metrics/log/cleanup cho sự kiện đã được publish trong transaction
    // vừa rollback, không được giả định có bản ghi committed.
}
```

Đây là đoạn minh họa cần Spring bean/transaction manager và type `OrderAttempted`. Không nên dùng callback này để ghi một record mới trên transaction cũ; nếu cần audit bền vững về thất bại, chủ động tạo transaction mới hoặc kênh durable độc lập với transaction đã rollback.

## 12. Không nhầm suppression với rollback và consistency

Một số chuỗi lỗi thường gặp:

**Trường hợp 1 — Listener sync lỗi, transaction rollback**

```text
@Transactional service
  saveOrder()
  publishEvent(OrderPlaced)
    listener throws RuntimeException
  -> exception lan ra khỏi transaction boundary
  -> rollback theo transaction rule
```

Đường này chỉ xảy ra nếu exception thực sự thoát ra phù hợp với rollback rule. Nếu listener throw nhưng publisher catch và coi như thành công, kết quả khác.

**Trường hợp 2 — ErrorHandler suppress, transaction commit**

```text
@Transactional service
  saveOrder()
  publishEvent(OrderPlaced)
    listener throws
    ErrorHandler suppress
  method returns normally
  -> transaction có thể commit
```

Trong trường hợp này, không được gọi “toàn bộ xử lý sự kiện thành công”. Chỉ có sự thật rằng **publisher không nhận exception đó**.

**Trường hợp 3 — AFTER_COMMIT listener lỗi**

```text
@Transactional service
  saveOrder()
  publishEvent(OrderPlaced)
  DB COMMIT thành công
  AFTER_COMMIT callback throws
  -> DB đã commit, không thể rollback commit vừa xảy ra
```

Exception có thể được log hoặc có hành vi lan truyền phụ thuộc phase/transaction integration; không suy ra một outcome rollback. Với việc bắt buộc sau commit, durable work queue/outbox đáng tin hơn callback in-memory không có replay.

**Trường hợp 4 — Không có transaction + fallbackExecution=true**

```text
publishEvent(OrderPlaced) (no transaction)
  transactional listener with fallbackExecution=true
  -> handler chạy ngay
  -> không có commit nào xảy ra
```

Tên `AFTER_COMMIT` trong annotation không biến đường fallback thành một cam kết commit.

## 13. Định danh và idempotency cho fallback/retry

Nếu fallback chuyển công việc sang retry queue, phải mang dữ liệu đủ để phát lại **đúng công việc**:

- `eventId`: định danh occurrence, dùng cho deduplication.
- `eventType`/schema version: consumer hiểu đúng payload.
- `aggregateId` và version: kiểm tra thứ tự/trạng thái nếu cần.
- `tenantId`: cô lập dữ liệu multi-tenant (không dùng như bằng chứng authorization).
- `correlationId` và `causationId`: truy vết một luồng xử lý.
- `occurredAt`: thời điểm sự thật xảy ra, phân biệt với thời điểm retry.
- `attempt`/retry metadata: nên nằm ở work item/transport nếu là chi tiết delivery, không làm méo fact domain.

Khi retry, thường **giữ nguyên eventId của fact gốc**. Đừng tạo event ID mới mỗi lần thử gửi rồi khiến consumer tưởng là sự thật mới. Nếu phát sinh một fact nghiệp vụ hoàn toàn mới, đó lại là một event riêng với ID riêng.

Cần phân biệt **at-least-once delivery** với **exactly-once side effects**: broker có thể giao lại cùng message, và consumer phải phòng side effect lặp. Một cách phổ biến là lưu `(consumerName, eventId)` đã xử lý cùng transaction với cập nhật nghiệp vụ.

Nếu listener gọi cổng thanh toán, ngoài dedup ở consumer còn phải có idempotency key tại provider; lỗi timeout có thể xảy ra **sau** khi provider đã thực hiện thành công.

## 14. Cần quan sát những gì khi dùng fallback?

Một hệ thống có ErrorHandler chỉ log một dòng không thể gọi là “đã xử lý lỗi”. Các tín hiệu quan trọng:

| Chỉ số/tín hiệu | Nó trả lời điều gì? |
| --- | --- |
| `listener_attempt_total` | Có bao nhiêu lượt xử lý được thử? |
| `listener_failure_total` theo loại event/error | Tỷ lệ thất bại thực tế? |
| `listener_suppressed_total` | Bao nhiêu lỗi bị chính sách best-effort bỏ qua? |
| `executor_rejected_total` | Pool bao nhiêu lần từ chối task? |
| `caller_fallback_total` | Bao nhiêu listener phải chạy trên publisher thread? |
| `transaction_phase_callbacks_total` | AFTER_COMMIT / AFTER_ROLLBACK / no-TX fallback có bao nhiêu lượt? |
| `outbox_pending_count` và tuổi record cũ nhất | Công việc durable có bị tồn đọng? |
| `retry_attempt_total` và tuổi công việc | Có vòng retry liên tục hoặc delay quá lớn không? |
| `dead_letter_count` / quarantine count | Có bao nhiêu tác vụ cần xử lý thủ công? |
| `idempotency_duplicate_total` | Có nhiều redelivery/trùng xử lý không? |

Đây là **gợi ý tên metric do ứng dụng tự instrument**, không phải tên metric tự động do Spring cung cấp. Tránh dùng `eventId`, `userId` hoặc `tenantId` tùy ý làm label có cardinality cực cao; đưa chúng vào structured log/tracing có kiểm soát thay vì làm nổ metric series.

Khi log lỗi, cần có context tối thiểu nhưng tránh ghi credential, access token, toàn bộ event chứa PII hoặc dữ liệu thanh toán nhạy cảm.

## 15. Kịch bản kiểm thử cần có

| Kịch bản | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| Listener sync lỗi, không ErrorHandler | Listener A ném; B sau A | Publisher nhận lỗi; B có thể không được gọi |
| ErrorHandler suppress | A lỗi; ErrorHandler không throw | Có quan sát lỗi; B tiếp tục |
| ErrorHandler propagate | Handler ghi log rồi throw | Publisher sync nhận lỗi |
| Executor từ chối | Executor `execute` ném `RejectedExecutionException` | Xác minh fallback của multicaster đúng version và ảnh hưởng latency |
| Executor chấp nhận task nhưng listener ném | Async worker exception | Không giả định caller sync nhìn thấy lỗi |
| @Async void listener ném | Có `@EnableAsync` | Quan sát `AsyncUncaughtExceptionHandler` hoặc cấu hình tương đương |
| Transaction commit | Publish trong transaction thật, commit | AFTER_COMMIT gọi, AFTER_ROLLBACK không |
| Transaction rollback | Publish rồi rollback | AFTER_ROLLBACK gọi, AFTER_COMMIT không |
| Publish không có transaction | Transactional listener fallback=false | Callback bị bỏ qua |
| Publish không có transaction | Transactional listener fallback=true | Callback chạy mà **không có commit** |
| Transaction rollback + fallback=true | AFTER_COMMIT listener | Không tự gọi fallback như thể không có transaction |
| Listener AFTER_COMMIT ghi DB | Không có transaction mới | Kiểm tra hành vi commit thực tế, không tin vào log “saved” |
| Side effect sau commit bị lỗi | Crash/timeout sau commit | Công việc quan trọng có thể được replay từ outbox |
| Retry cùng event | Cùng eventId gửi nhiều lần | Consumer không nhân đôi side effect |
| Tenant khác | Fallback/retry mang tenantId | Không được đọc/ghi nhầm tenant |
| Shutdown với backlog | Executor đang ngừng | Xác định task được hoàn thành, chạy caller, từ chối hay mất theo policy |
| Permanent failure | Payload/schema sai | Không retry vô hạn; quarantine/alert |
| Partial success | Listener A thành công, B thất bại | Có trạng thái/compensation phù hợp, không gắn nhãn toàn bộ “thành công” |
| Multiple instances | Hai node cùng phát hoặc tiêu thụ | Idempotency/routing theo scope đúng |

Không chỉ dựa vào `Thread.sleep(...)` để giả lập overload. Nên dùng `CountDownLatch`/bounded executor với điều kiện tái hiện được, hoặc executor giả lập chủ động ném rejection như ví dụ ở phần 8.

## 16. Những lỗi thiết kế thường gặp

1. **Gọi mọi loại catch là fallback.** Catch rồi log không giúp công việc hoàn thành hoặc được lưu để thử lại.
2. **Suppress lỗi listener thiết yếu.** Caller thấy thành công dù nghiệp vụ mất một bước bắt buộc.
3. **Tưởng `ErrorHandler` tự retry.** Nó chỉ nhận lỗi, không có durable work/retry budget.
4. **Đặt ErrorHandler toàn cục mà không phân loại business criticality.** Một policy không phù hợp với mọi event.
5. **Nhầm executor rejection thành mặc nhiên fail-fast.** Multicaster có thể fallback chạy trực tiếp trên caller.
6. **Cho rằng bounded queue ngăn toàn bộ overload.** Caller fallback có thể làm tăng tổng công việc và kéo dài request.
7. **Cho rằng listener async ném lỗi sẽ rollback transaction publisher.** Khác thread/stack và không có transaction chung mặc định.
8. **Dùng `fallbackExecution=true` để xử lý sau rollback.** Nó áp dụng khi **không có transaction**, không phải khi rollback.
9. **Bật fallback cho AFTER_ROLLBACK rồi ghi log “rollback happened” khi không có transaction.** Dữ kiện ghi nhận sai.
10. **Dùng AFTER_COMMIT như bảo đảm gửi message.** Process có thể crash sau commit mà chưa xử lý callback.
11. **Ghi DB ở callback AFTER_COMMIT nhưng không tạo transaction mới.** Thay đổi có thể không được commit.
12. **Phát fact trước commit rồi để listener ngoài hệ thống hành động.** Transaction rollback có thể khiến downstream xử lý một sự thật chưa durable.
13. **Retry toàn bộ workflow dù một số side effect đã thành công.** Có thể tạo trùng payment/email/invoice.
14. **Không có idempotency key ổn định.** Retry sinh event ID mới làm khó dedup.
15. **Không phân biệt lỗi transient/permanent.** Retry vô hạn trên schema invalid hoặc unauthorized.
16. **Dùng fallback để vượt qua kiểm tra quyền.** Bảo mật không phải lựa chọn tùy hoàn cảnh.
17. **Giấu lỗi ở log không được giám sát.** Cần metric, alerts, trạng thái cuối và runbook.
18. **Nhầm Spring application event với message queue.** In-memory publish không có persistence/replay tự động.
19. **Không kiểm tra phase với transaction thật.** Mock `@Transactional` trên method private hoặc self-invocation có thể không tạo transaction như tưởng.
20. **Không tính shutdown và executor saturation.** “Không lỗi khi dev” không bảo đảm ứng dụng chịu tải và có thể đóng an toàn.

## 17. Quy trình thiết kế fallback trước khi triển khai

**Bước 1 — Xác định sự thật nghiệp vụ.** Event đại diện điều gì, có cần bắt buộc xử lý hay chỉ phục vụ quan sát?

**Bước 2 — Định nghĩa điểm thất bại.** Sync listener, task scheduling, business transaction, external call, broker publish hay consumer commit?

**Bước 3 — Chốt kết quả hợp lệ.** Fail-fast/rollback, best-effort, pending-for-retry, compensating hoặc quarantine? Ai có quyền quyết định?

**Bước 4 — Chọn cơ chế theo tầng.** `ErrorHandler` cho lỗi listener được multicaster gọi, `fallbackExecution` cho absence of transaction, admission control cho overload, outbox/broker cho durability, transaction rules cho rollback.

**Bước 5 — Thiết kế truyền và lưu metadata.** Event ID, tenant, aggregate, correlation, occurrence time và schema đúng contract, không dùng runtime objects.

**Bước 6 — Đảm bảo an toàn khi thử lại.** Idempotency, retry budget, exponential backoff, timeout, DLQ/quarantine, version compatibility.

**Bước 7 — Kiểm thử kết quả thực tế.** Đồng bộ/bất đồng bộ, commit/rollback/no transaction, executor reject, crash giữa commit và publish, duplicate và shutdown.

**Bước 8 — Đưa vào vận hành có quan sát.** Metrics/errors/alerts, replay runbook, trách nhiệm xử lý cuối cùng, data retention và bảo mật.

### Checklist quyết định nhanh

- [ ] Mỗi listener được phân loại **critical** hay **best effort**.
- [ ] Biết rõ exception nào lan về publisher và exception nào chỉ xuất hiện ở worker.
- [ ] `ErrorHandler` suppress chỉ dùng khi tác vụ được phép thất bại và có giám sát.
- [ ] Có kiểm thử trường hợp executor từ chối và đường fallback caller.
- [ ] Biết chính xác `fallbackExecution=true` chỉ xử lý **không có transaction**.
- [ ] Callback `AFTER_COMMIT`/`AFTER_ROLLBACK` không bị hiểu sai là phép undo commit.
- [ ] Side effect quan trọng có lưu bền vững/outbox hoặc đường replay.
- [ ] Retry và compensation có idempotency, timeout và giới hạn.
- [ ] Không dùng fallback vượt authorization hoặc thay đổi tenant scope.
- [ ] Có metric và cảnh báo cho lỗi bị suppress, backlog và task lỗi lâu ngày.

**Kết luận:** “Fallback và xử lý lỗi có chủ đích” không phải một annotation duy nhất. `ErrorHandler` quyết định phản ứng với exception khi listener chạy; multicaster có thể fallback chạy listener tại caller khi executor từ chối; `fallbackExecution=true` chỉ mở đường xử lý **không có transaction**; còn yêu cầu retry, replay, rollback hoặc không mất event phải được thiết kế ở cấp nghiệp vụ và hạ tầng. Hãy để mọi đường lỗi có **kết quả, giới hạn và khả năng quan sát rõ ràng**.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2.9 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2.6 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — Multicaster source code](https://github.com/spring-projects/spring-framework/blob/main/spring-context/src/main/java/org/springframework/context/event/SimpleApplicationEventMulticaster.java)
