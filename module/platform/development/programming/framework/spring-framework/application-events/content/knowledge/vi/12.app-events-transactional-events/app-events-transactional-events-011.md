# Một event với nhiều phase listener trong Spring Framework

## 1. Một event, nhiều thời điểm xử lý theo transaction

Trong Spring Framework, một lần gọi `ApplicationEventPublisher.publishEvent(event)` có thể kích hoạt nhiều listener. Nếu listener khai báo `@TransactionalEventListener`, mỗi listener có thể được gắn với một **phase của transaction**: trước commit, sau commit thành công, sau rollback hoặc sau khi transaction hoàn tất với bất kỳ kết quả nào.

Ví dụ service phát `OrderSubmitted("ORD-101")` một lần trong lúc lưu đơn hàng. Bốn listener khác nhau có thể quan sát đúng event này:

- `BEFORE_COMMIT`: kiểm tra chốt trước khi transaction commit.
- `AFTER_COMMIT`: thực hiện tác vụ chỉ hợp lệ sau khi commit thành công.
- `AFTER_ROLLBACK`: phản ứng khi transaction bị rollback.
- `AFTER_COMPLETION`: dọn dẹp hoặc ghi metric sau khi transaction kết thúc, dù commit hay rollback.

**Đây vẫn là một event được publish một lần**, chứ không phải bốn event. Mỗi listener phù hợp đăng ký callback theo phase của transaction. Một lần transaction chỉ có thể kết thúc theo một kết quả, nên các listener thuộc phase đối nghịch không đồng thời được gọi.

Bài này minh họa **giao dịch imperative** dùng `PlatformTransactionManager` và thread-bound transaction context. Reactive transaction có cơ chế context khác, được lưu ý ở mục 8.

## 2. Ý nghĩa chính xác của từng TransactionPhase

| Phase | Thời điểm | Transaction commit | Transaction rollback |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Khi chuẩn bị commit, trước commit vật lý | Thường chạy | Không chạy trong nhánh rollback thông thường |
| `AFTER_COMMIT` | Khi commit đã thành công | Chạy | Không chạy |
| `AFTER_ROLLBACK` | Sau rollback | Không chạy | Chạy |
| `AFTER_COMPLETION` | Sau khi transaction đã hoàn tất | Chạy | Chạy |

`@TransactionalEventListener` mặc định có `phase = TransactionPhase.AFTER_COMMIT` nếu không khai báo gì thêm.

Luồng commit thường gặp:

```text
transaction bắt đầu
  |
  +-- service thay đổi dữ liệu
  +-- publishEvent(OrderSubmitted)
  |     +-- @EventListener thường chạy ngay nếu đồng bộ
  |     +-- @TransactionalEventListener đăng ký callbacks theo phase
  |
  +-- phần thân nghiệp vụ kết thúc bình thường
  +-- BEFORE_COMMIT listener
  +-- database commit thành công
  +-- AFTER_COMMIT listener
  +-- AFTER_COMPLETION listener
  +-- thao tác quản lý transaction trả về
```

Luồng rollback thường gặp:

```text
transaction bắt đầu
  |
  +-- service thay đổi dữ liệu
  +-- publishEvent(OrderSubmitted)
  |     +-- @EventListener thường chạy ngay nếu đồng bộ
  |     +-- @TransactionalEventListener đăng ký callbacks
  |
  +-- rollback-only hoặc lỗi nghiệp vụ
  +-- database rollback
  +-- AFTER_ROLLBACK listener
  +-- AFTER_COMPLETION listener
  +-- thao tác quản lý transaction trả về hoặc ném exception
```

**Điểm dễ nhầm:** Trong Spring Framework 6.2, `AFTER_COMMIT` là một trường hợp của chuỗi callback `afterCompletion`, không phải phương thức `TransactionSynchronization.afterCommit()`. `AFTER_ROLLBACK` cũng là trường hợp của `afterCompletion`. Điều này ảnh hưởng đến việc suy luận thứ tự tương đối giữa `AFTER_COMMIT` và `AFTER_COMPLETION`.

`BEFORE_COMMIT` không bảo đảm commit sau đó chắc chắn thành công: cơ sở dữ liệu hoặc mã khác vẫn có thể khiến commit thất bại. Các tác dụng phụ không thể rollback như gửi email không nên được kích hoạt chỉ dựa vào việc đã đến phase này.

## 3. Cùng event được đăng ký bởi nhiều listener ra sao?

Các phương thức sau có thể cùng nằm trong một bean do Spring quản lý, hoặc nằm ở những bean khác nhau:

```java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void validate(OrderSubmitted event) { /* kiểm tra trước commit */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void notifySuccess(OrderSubmitted event) { /* sau commit */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
void undoTemporaryAction(OrderSubmitted event) { /* sau rollback */ }

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
void recordCompletion(OrderSubmitted event) { /* sau mọi kết quả */ }
```

Đây là trích đoạn phương thức, chưa phải chương trình độc lập. Phiên bản chạy được nằm ở mục 4.

Khi `publishEvent` được gọi bên trong transaction, Spring chọn các listener phù hợp với kiểu event và điều kiện `condition` (nếu có). Adapter của mỗi transactional listener đăng ký synchronization với transaction đang hoạt động. Khi transaction chuyển giai đoạn, callback phù hợp mới chạy. Một listener `@EventListener` thông thường có hành vi khác: với multicaster đồng bộ, nó chạy ngay trong lời gọi `publishEvent` và không chờ transaction kết thúc.

Vì thế trong một transaction sau đó rollback, listener thường có thể **đã thực hiện tác dụng phụ**, trong khi `AFTER_COMMIT` không chạy. Khi thiết kế nghiệp vụ phải chọn đúng loại listener theo ngữ nghĩa cần bảo đảm.

## 4. Ví dụ Java 17 hoàn chỉnh: cùng event, hai kết quả transaction

Ví dụ dùng Spring Framework 6.2.8 và H2 trong bộ nhớ để có transaction JDBC thật. Chúng ta tạo hai transaction riêng: transaction đầu commit, transaction sau đánh dấu rollback-only. Trong mỗi transaction chỉ gọi `publishEvent` đúng một lần.

### Cấu trúc dự án Maven

```text
multi-phase-event/
├── pom.xml
└── src/main/java/demo/MultiPhaseEventDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>multi-phase-event</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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
                    <mainClass>demo.MultiPhaseEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/MultiPhaseEventDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public class MultiPhaseEventDemo {

    public record OrderSubmitted(String orderId) {}

    public static class OrderListeners {
        @EventListener
        public void onPublish(OrderSubmitted event) {
            System.out.println("immediate: " + event.orderId());
        }

        @Order(10)
        @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
        public void beforeCommit(OrderSubmitted event) {
            System.out.println("before commit: " + event.orderId());
        }

        @Order(20)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
        public void afterCommit(OrderSubmitted event) {
            System.out.println("after commit: " + event.orderId());
        }

        @Order(30)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
        public void afterRollback(OrderSubmitted event) {
            System.out.println("after rollback: " + event.orderId());
        }

        @Order(40)
        @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
        public void afterCompletion(OrderSubmitted event) {
            System.out.println("after completion: " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:phase_demo;DB_CLOSE_DELAY=-1", "sa", "");
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager transactionManager) {
            return new TransactionTemplate(transactionManager);
        }

        @Bean
        OrderListeners orderListeners() {
            return new OrderListeners();
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            var transactions = context.getBean(TransactionTemplate.class);

            System.out.println("=== COMMIT ===");
            transactions.executeWithoutResult(status -> {
                System.out.println("business: publish C-1");
                context.publishEvent(new OrderSubmitted("C-1"));
                System.out.println("business: body done C-1");
            });
            System.out.println("caller: commit returned");

            System.out.println("=== ROLLBACK ===");
            transactions.executeWithoutResult(status -> {
                System.out.println("business: publish R-1");
                context.publishEvent(new OrderSubmitted("R-1"));
                System.out.println("business: body done R-1");
                status.setRollbackOnly();
            });
            System.out.println("caller: rollback returned");
        }
    }
}
```

Chạy ở thư mục `multi-phase-event` với JDK 17+ và Maven:

```bash
mvn -q clean compile exec:java
```

Đầu ra do mã ứng dụng in ra (không tính log của Maven):

```text
=== COMMIT ===
business: publish C-1
immediate: C-1
business: body done C-1
before commit: C-1
after commit: C-1
after completion: C-1
caller: commit returned
=== ROLLBACK ===
business: publish R-1
immediate: R-1
business: body done R-1
after rollback: R-1
after completion: R-1
caller: rollback returned
```

**Vì sao có output này?**

1. `TransactionTemplate` mở transaction JDBC thông qua `DataSourceTransactionManager`. H2 cung cấp kết nối và ranh giới transaction; ví dụ không tạo bảng vì chỉ muốn chứng minh callback phase.
2. `@EventListener` thông thường xử lý ngay khi publish. Cả event `C-1` và `R-1` đều in `immediate`.
3. Với `C-1`, phần thân `executeWithoutResult` kết thúc bình thường; Spring gọi `BEFORE_COMMIT`, thực hiện commit rồi gọi callback tương ứng sau commit và completion.
4. Với `R-1`, `status.setRollbackOnly()` khiến transaction rollback sau khi phần thân callback trả về; `BEFORE_COMMIT` và `AFTER_COMMIT` không chạy. Listener `AFTER_ROLLBACK` và `AFTER_COMPLETION` chạy.
5. Các mức `@Order(20)`, `@Order(30)` và `@Order(40)` giúp xác định thứ tự callback phù hợp trong giai đoạn hoàn tất. `@Order` không thay đổi kết quả commit/rollback và không biến một phase thành phase khác.
6. Các dòng `caller: ... returned` nằm sau lời gọi `TransactionTemplate`. Trong cấu hình đồng bộ mặc định của ví dụ, chúng xuất hiện sau khi callback phase phù hợp đã hoàn tất.

Nếu service dùng Spring Boot, các annotation và phase vẫn tương tự, nhưng Spring Boot có thể cung cấp sẵn `DataSource`, `PlatformTransactionManager` và cấu hình bean. Ví dụ ở đây dùng `AnnotationConfigApplicationContext` để chạy độc lập với Boot.

## 5. Phase và @Order không thay thế nhau

**Phase quyết định *khi nào* listener được phép chạy; `@Order` điều chỉnh thứ tự tương đối giữa các listener cùng đang được gọi tại một giai đoạn.** Xét hai phương thức:

```java
@Order(100)
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void validate(OrderSubmitted e) { /* ... */ }

@Order(-100)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
void notifyCustomer(OrderSubmitted e) { /* ... */ }
```

Dù `notifyCustomer` có số ưu tiên thấp hơn, nó vẫn phải đợi commit thành công; không được chạy trước `validate` đang ở phase trước commit. Giá trị `@Order` có thể được dùng để sắp thứ tự giữa các listener cùng phase, và giữa các listener after-commit/after-completion trong chuỗi synchronization phù hợp.

Nếu hai listener có cùng `@Order`, **không dựa vào thứ tự khai báo phương thức hoặc tên bean** để thiết kế một quy trình có thứ tự bắt buộc. Hãy dùng mức ưu tiên khác nhau hoặc service điều phối rõ ràng.

Một transaction cũng có thể publish **nhiều event**. Mỗi lần publish sinh ra những đăng ký callback riêng cho các listener phù hợp; các callback cùng chờ kết quả của transaction đó. Thứ tự giữa nhiều lần publish, nhiều listener và các giai đoạn có thể chịu ảnh hưởng của thứ tự đăng ký/`@Order`. Đừng giả định mọi callback của event A luôn kết thúc trước mọi callback của event B nếu ứng dụng không chủ động bảo đảm điều đó.

## 6. Các trường hợp dễ sai trong nghiệp vụ

### 6.1. Phát event ngoài transaction

Mặc định, nếu không có transaction hoạt động, `@TransactionalEventListener` **không chạy** — kể cả `AFTER_COMPLETION`. `@EventListener` bình thường vẫn có thể chạy vì nó không yêu cầu transaction.

Có thể bật `fallbackExecution = true` để listener thực thi ngay khi không có transaction. Đây là đường đi fallback; nó **không phải bằng chứng rằng commit đã thành công**. Chỉ bật khi logic nghiệp vụ thực sự chấp nhận sự kiện được xử lý ngoài transaction.

### 6.2. AFTER_COMMIT không tự mở transaction mới

Theo Javadoc của `@TransactionalEventListener`, khi callback `AFTER_COMMIT`, `AFTER_ROLLBACK` hoặc `AFTER_COMPLETION` chạy, transaction đã hoàn tất nhưng tài nguyên JDBC/JPA có thể vẫn được gắn với thread. Truy cập dữ liệu lúc này đôi khi còn "tham gia" ngữ cảnh cũ **mà không còn commit tiếp theo**, dẫn đến thao tác tưởng như thành công nhưng không được lưu.

Nếu listener sau commit cần ghi một bản ghi mới, hãy mở transaction độc lập với propagation `REQUIRES_NEW`, chẳng hạn gọi qua một Spring-managed service có `@Transactional(propagation = Propagation.REQUIRES_NEW)` hoặc dùng `TransactionTemplate` được cấu hình tương ứng. Lưu ý gọi một phương thức `@Transactional` nội bộ bằng `this.method()` thường không đi qua Spring proxy.

### 6.3. BEFORE_COMMIT có thể gặp lỗi

`BEFORE_COMMIT` được gọi khi transaction chuẩn bị commit. Listener có thể ném lỗi làm transaction không commit; hoặc commit sau đó vẫn có thể thất bại vì database. Không gửi thông báo vĩnh viễn hoặc thực hiện side effect khó thu hồi tại bước này chỉ vì cho rằng đã "chắc chắn commit".

### 6.4. AFTER_COMMIT phù hợp về thời điểm, chưa bảo đảm gửi thành công

Chuyển việc gửi email hoặc message sang `AFTER_COMMIT` giúp tránh gửi khi dữ liệu bị rollback, nhưng nếu process sập ngay sau commit hoặc API đích lỗi, side effect có thể mất. Với yêu cầu gửi đáng tin, dùng transactional outbox, cơ chế retry, idempotency và giám sát thất bại. `@TransactionalEventListener` bản thân không biến event trong bộ nhớ thành hàng đợi bền vững.

### 6.5. AFTER_COMPLETION không tự báo kết quả commit/rollback

Annotation này chỉ cam kết được gọi sau khi transaction hoàn tất theo cơ chế transaction manager. Nếu cùng một xử lý cần biết commit hay rollback, cách dễ hiểu là dùng riêng `AFTER_COMMIT` và `AFTER_ROLLBACK`. Không đoán kết quả chỉ dựa vào một callback `AFTER_COMPLETION` không có tham số trạng thái.

### 6.6. setRollbackOnly khác với ném exception

Ví dụ dùng `status.setRollbackOnly()`: `TransactionTemplate` rollback bình thường và có thể trả về cho caller không ném lỗi. Ngược lại, nếu callback nghiệp vụ ném unchecked exception, `TransactionTemplate` rollback rồi truyền exception ra caller. Cả hai có thể dẫn đến `AFTER_ROLLBACK` và `AFTER_COMPLETION`, nhưng đường đi kiểm soát lỗi của caller khác nhau.

### 6.7. Async và transaction context

Giao dịch imperative thường gắn với thread hiện tại. Spring 6.1+ có `TransactionalApplicationListener.supportsAsyncExecution() == false` cho listener synchronization, nhằm bảo đảm bước đăng ký được thực hiện trong publisher thread phù hợp. Nếu tự chuyển `publishEvent` sang thread khác, hoặc kết hợp `@Async` không đúng cách, transaction context có thể không tồn tại ở worker. Không giả định một worker kế thừa transaction chỉ vì event được phát từ một service đang có `@Transactional`.

Nếu cần xử lý tác vụ nặng sau commit, hãy thiết kế rõ điểm giao cho executor, transaction mới nếu cần, retry và trạng thái thất bại; không dùng cấu hình async để suy diễn thêm bảo đảm về giao nhận sự kiện.

## 7. Phối hợp nhiều phase listener theo trách nhiệm

| Mục tiêu | Lựa chọn | Cẩn trọng |
| --- | --- | --- |
| Kiểm tra dữ liệu lần cuối trước commit | `BEFORE_COMMIT` | Có thể khiến commit thất bại; tránh side effect ngoài DB |
| Gửi thông báo sau khi bản ghi đã commit | `AFTER_COMMIT` | Cần cơ chế gửi tin cậy nếu nghiệp vụ quan trọng |
| Hoàn nguyên trạng thái tạm sau rollback | `AFTER_ROLLBACK` | Không ghi lại DB bằng transaction đã kết thúc |
| Ghi metric hoàn tất chung | `AFTER_COMPLETION` | Không tự phân biệt được kết quả |
| Xử lý ngay khi sự kiện được phát | `@EventListener` | Có thể chạy cả khi transaction về sau rollback |

Một event có thể mang ý nghĩa nghiệp vụ duy nhất nhưng được các listener nhìn từ nhiều thời điểm. Tuy nhiên, khi logic bước sau bắt buộc phụ thuộc vào kết quả bước trước, hoặc cần đồng bộ rollback chặt chẽ, service điều phối tuần tự thường dễ kiểm soát và kiểm thử hơn một chuỗi callback trải trên nhiều bean.

## 8. Reactive transaction khác imperative transaction

Các ví dụ sử dụng `PlatformTransactionManager` (JDBC/JPA) với transaction gắn vào thread. Khi dùng `ReactiveTransactionManager`, thông tin giao dịch nằm trong **Reactor Context**, không tự tồn tại trong `ThreadLocal`. Từ Spring Framework 6.1, `@TransactionalEventListener` có thể làm việc với reactive transaction khi context được truyền vào nguồn event theo cơ chế được hỗ trợ, ví dụ `TransactionalEventPublisher`.

Không sao chép nguyên ví dụ `TransactionTemplate` vào reactive pipeline rồi giả định listener sẽ quan sát được cùng thread-bound transaction. Reactive cần thiết kế cách publish sự kiện và truyền context tương thích.

## 9. Câu hỏi tự kiểm tra và cách chẩn đoán

1. **Một event có thể có cả `AFTER_COMMIT` lẫn `AFTER_ROLLBACK` listener?** Có. Chúng được đăng ký cho cùng kiểu event, nhưng chỉ nhánh phù hợp kết quả transaction chạy.
2. **Khi commit, cả bốn phase đều chạy?** Không. `AFTER_ROLLBACK` không chạy.
3. **Rollback thông thường có luôn gọi `BEFORE_COMMIT`?** Không. Nó thường bỏ qua before-commit.
4. **Một transaction vừa commit vừa rollback, khiến `AFTER_COMPLETION` chạy hai lần?** Không. Nó chỉ có một kết quả hoàn tất.
5. **`@Order(-100)` ở `AFTER_COMMIT` có thể chạy trước `BEFORE_COMMIT`?** Không. Phase quyết định thời điểm.
6. **Không có transaction, listener transactional có chạy theo mặc định?** Không; chỉ có thể bật fallback với ngữ nghĩa riêng.
7. **Có thể ghi DB trực tiếp trong `AFTER_COMMIT` rồi dựa vào transaction gốc để commit lần nữa?** Không. Nếu cần ghi, phải tạo transaction phù hợp mới.
8. **Publish event trong transaction reactive có tự động đưa transaction vào thread-local?** Không; cần cơ chế context reactive.

Khi debug, log event ID, thời điểm publish, transaction đang hoạt động hay không, phase callback, kết quả transaction và thread name. Nếu listener không chạy, kiểm tra bean có được Spring quản lý, event type/`condition` có khớp, transaction có hoạt động, có rollback, và `fallbackExecution` có đúng nhu cầu hay không.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionPhase API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework — TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
