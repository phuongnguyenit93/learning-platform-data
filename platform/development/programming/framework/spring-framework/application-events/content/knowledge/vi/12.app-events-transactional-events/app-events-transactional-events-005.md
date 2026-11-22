# Transaction phase AFTER_ROLLBACK

`@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)` cho phép xử lý một event sau khi transaction chứa event đó đã rollback. Đây là hook dành cho tình huống transaction kết thúc thất bại: giải phóng tài nguyên bên ngoài, ghi nhận một lần thử không thành công, phát cảnh báo hoặc khởi chạy quy trình bù trừ phù hợp.

Điểm cốt lõi là event thường được **publish khi transaction vẫn đang hoạt động**. Spring đăng ký listener với transaction synchronization, sau đó chỉ gọi method listener nếu transaction thực sự rollback. Listener không tự gây rollback và cũng không thay thế cơ chế rollback của database.

## 1. AFTER_ROLLBACK là gì?

`TransactionPhase` là enum trong package:

~~~java
org.springframework.transaction.event
~~~

Các giá trị:

| Phase | Thời điểm xử lý |
|---|---|
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi commit thành công; phase mặc định |
| `AFTER_ROLLBACK` | Sau khi transaction rollback |
| `AFTER_COMPLETION` | Sau khi transaction hoàn tất, dù commit hay rollback |

`AFTER_ROLLBACK` là một trường hợp chuyên biệt của `AFTER_COMPLETION`. Nó chỉ xử lý khi transaction hoàn tất với trạng thái rollback. Nếu transaction commit thành công, listener phase này không chạy.

Ví dụ khai báo:

~~~java
@Component
class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onOrderRolledBack(OrderPlacementAttempted event) {
        System.out.println("Order rolled back: " + event.orderId());
    }
}
~~~

Nếu không chỉ định `phase`, `@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`. Vì vậy, hãy khai báo rõ `TransactionPhase.AFTER_ROLLBACK` khi mục tiêu là xử lý sau rollback.

## 2. Event được đăng ký như thế nào?

Trong luồng imperative, khi một event được publish bên trong transaction đang hoạt động:

1. Service gọi `ApplicationEventPublisher.publishEvent(event)`.
2. Spring tìm transactional listener phù hợp.
3. Listener adapter đăng ký callback với transaction synchronization hiện tại.
4. Method listener chưa chạy tại vị trí publish.
5. Transaction manager thực hiện commit hoặc rollback.
6. Nếu transaction rollback, Spring gọi các listener có phase `AFTER_ROLLBACK`.
7. Nếu transaction commit, listener `AFTER_ROLLBACK` bị bỏ qua.

~~~text
@Transactional service
        |
        | publishEvent(OrderPlacementAttempted)
        v
Spring registers transaction synchronization
        |
        v
Service continues
        |
        +---- commit ----------------> AFTER_ROLLBACK is skipped
        |
        +---- rollback --------------> AFTER_ROLLBACK listener runs
~~~

Điều này khác với `@EventListener` thông thường: listener thường được gọi trong lúc dispatch event, còn `@TransactionalEventListener` đợi transaction đạt phase đã chọn.

Với listener đồng bộ, callback rollback thường được thực thi trong quá trình transaction manager hoàn tất transaction, trước khi lời gọi qua transaction proxy trả kết quả hoặc ném exception về caller bên ngoài.

## 3. Ví dụ chạy được: transaction rollback kích hoạt listener

Ví dụ sau dùng Java 17+, Spring Boot 3.5.x, JDBC và H2. Service ghi một đơn hàng, publish event rồi cố ý ném runtime exception. Database rollback thao tác insert; listener `AFTER_ROLLBACK` nhận event đã được đăng ký trước đó.

**Maven dependencies:**

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.6</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
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
~~~

**File `src/main/resources/schema.sql`:**

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY
);
~~~

**File `src/main/java/com/example/rollback/RollbackEventDemo.java`:**

~~~java
package com.example.rollback;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@SpringBootApplication
public class RollbackEventDemo {

    public static void main(String[] args) {
        SpringApplication.run(RollbackEventDemo.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService service, JdbcTemplate jdbc) {
        return args -> {
            try {
                service.placeAndFail("ORD-130");
            } catch (IllegalStateException ex) {
                System.out.println("Caller caught: " + ex.getMessage());
            }

            Integer count = jdbc.queryForObject(
                    "select count(*) from orders where order_id = ?",
                    Integer.class,
                    "ORD-130"
            );
            System.out.println("Rows after rollback: " + count);
        };
    }
}

record OrderPlacementAttempted(String orderId) {}

@Service
class OrderService {
    private final JdbcTemplate jdbc;
    private final ApplicationEventPublisher publisher;

    OrderService(
            JdbcTemplate jdbc,
            ApplicationEventPublisher publisher
    ) {
        this.jdbc = jdbc;
        this.publisher = publisher;
    }

    @Transactional
    public void placeAndFail(String orderId) {
        jdbc.update(
                "insert into orders(order_id) values (?)",
                orderId
        );

        publisher.publishEvent(new OrderPlacementAttempted(orderId));
        System.out.println("Service: event published");

        throw new IllegalStateException("simulated failure");
    }
}

@Component
class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacementAttempted event) {
        System.out.println("Rollback listener: " + event.orderId());
    }
}
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Các dòng output do code ứng dụng tạo ra; log startup của Spring Boot được lược bỏ:

~~~text
Service: event published
Rollback listener: ORD-130
Caller caught: simulated failure
Rows after rollback: 0
~~~

Giải thích:

1. `OrderService.placeAndFail` chạy qua Spring transaction proxy.
2. JDBC insert được thực hiện trong transaction.
3. Event `OrderPlacementAttempted` được publish khi transaction còn hoạt động; Spring đăng ký callback rollback.
4. Runtime exception làm transaction rollback theo mặc định.
5. Listener nhận event ở phase `AFTER_ROLLBACK`.
6. Exception tiếp tục được trả về caller và được bắt trong `CommandLineRunner`.
7. Truy vấn sau rollback xác nhận bản ghi không tồn tại.

Ví dụ này cần các class nằm trong package được Spring Boot component scan, file `schema.sql` ở đúng vị trí và dependency JDBC/H2 như trên. Nó minh họa rollback thực tế của database và callback sau rollback, không chỉ gọi method listener trực tiếp.

## 4. Điều gì khiến transaction rollback?

`AFTER_ROLLBACK` phụ thuộc vào kết quả cuối cùng của transaction. Một exception xuất hiện trong code không phải lúc nào cũng đồng nghĩa transaction đã rollback.

Với `@Transactional` theo quy tắc mặc định truyền thống của Spring:

- `RuntimeException` và `Error` làm transaction rollback.
- Checked exception thường không làm rollback mặc định.
- Có thể thay đổi quy tắc bằng `rollbackFor` và `noRollbackFor`.
- Code có thể đánh dấu transaction rollback-only bằng `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` hoặc API transaction status tương ứng.
- Transaction manager có thể rollback do lỗi trong quá trình commit hoặc do trạng thái rollback-only đã được đánh dấu.

Ví dụ checked exception yêu cầu rollback:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrder() throws IOException {
    // Thao tác dữ liệu.
    throw new IOException("invalid input");
}
~~~

Ví dụ đánh dấu rollback-only:

~~~java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
~~~

Trong trường hợp thứ hai, method có thể kết thúc mà không ném exception tại dòng đánh dấu. Khi transaction interceptor cố commit, transaction vẫn rollback và listener `AFTER_ROLLBACK` được gọi.

Từ Spring Framework 6.2, có thể đổi quy tắc rollback mặc định toàn cục bằng `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`, để checked exception cũng làm rollback nếu không có rule cụ thể ghi đè. Hãy kiểm tra cấu hình transaction management của ứng dụng trước khi suy luận từ loại exception.

Vì vậy, listener nên phản ánh trạng thái transaction cuối cùng. Không suy luận rằng listener sẽ chạy chỉ vì service có log lỗi hoặc đã bắt một exception.

## 5. Phân biệt rollback với một lần xử lý thất bại

Một transaction rollback có thể xuất phát từ nhiều nguyên nhân:

- Validation nghiệp vụ thất bại.
- Không đủ số dư hoặc không thỏa điều kiện.
- Lỗi truy cập database.
- Deadlock hoặc optimistic locking conflict.
- Một service downstream ném exception khiến transaction bị đánh dấu rollback-only.
- Code chủ động gọi `setRollbackOnly()`.

Event được publish trước khi transaction kết thúc nên thường mô tả một **lần thử hoặc yêu cầu đang xử lý**, chẳng hạn `OrderPlacementAttempted`, `PaymentRequested` hoặc `InventoryReservationRequested`.

Listener `AFTER_ROLLBACK` biết transaction đã rollback, nhưng event payload không tự biết nguyên nhân cụ thể. Nếu cần phân loại nguyên nhân, hãy đưa mã lỗi hoặc dữ liệu chẩn đoán phù hợp vào event trước khi publish, hoặc ghi nhận nguyên nhân ở tầng xử lý exception.

Không nên đặt tên event là `OrderCommitted` rồi dùng nó để xử lý rollback. Tên event cần mô tả đúng điều đã xảy ra tại thời điểm publish.

## 6. Khi nào AFTER_ROLLBACK chạy và khi nào bị bỏ qua?

| Kết quả transaction | Listener AFTER_ROLLBACK |
|---|---|
| Transaction commit thành công | Không chạy |
| Transaction rollback do runtime exception | Chạy |
| Transaction rollback do checked exception có `rollbackFor` | Chạy |
| Transaction bị đánh dấu rollback-only rồi hoàn tất rollback | Chạy |
| Transaction rollback do lỗi commit/transaction manager | Chạy nếu transaction synchronization hoàn tất với trạng thái rollback |
| Không có transaction đang hoạt động | Mặc định không chạy |
| Không có transaction và `fallbackExecution=true` | Chạy ngay như fallback, không có rollback thực tế |

Một event được publish ngoài transaction không được giữ lại để đợi transaction tương lai. Nếu muốn xử lý khi không có transaction, phải bật fallback và chấp nhận ngữ nghĩa chạy ngay.

## 7. fallbackExecution và phase AFTER_ROLLBACK

Mặc định, `fallbackExecution` là `false`. Nếu không có transaction để đăng ký synchronization, transactional listener bị bỏ qua.

Có thể bật:

~~~java
@Component
class RollbackObserver {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_ROLLBACK,
            fallbackExecution = true
    )
    public void onRollback(OrderPlacementAttempted event) {
        System.out.println("Observed: " + event.orderId());
    }
}
~~~

Cần hiểu rõ hai nhánh:

- **Có transaction:** listener chỉ chạy khi transaction thực sự rollback.
- **Không có transaction:** fallback gọi listener ngay tại thời điểm publish, bất kể phase được khai báo.

Vì vậy, với `fallbackExecution=true`, listener mang tên `onRollback` có thể chạy dù không hề có rollback. Spring xem đây là fallback execution; nó không giả lập transaction rollback.

Chỉ bật fallback nếu xử lý ngay ngoài transaction vẫn đúng nghiệp vụ. Nếu listener chỉ có ý nghĩa khi database transaction thất bại, giữ mặc định false.

## 8. AFTER_ROLLBACK và AFTER_COMPLETION khác nhau thế nào?

`AFTER_COMPLETION` chạy sau khi transaction kết thúc dù commit hay rollback. `AFTER_ROLLBACK` chỉ chạy khi kết quả là rollback.

Ví dụ hai listener:

~~~java
@Component
class TransactionOutcomeListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacementAttempted event) {
        System.out.println("Rollback: " + event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void onCompletion(OrderPlacementAttempted event) {
        System.out.println("Completed: " + event.orderId());
    }
}
~~~

Nếu transaction rollback, cả hai listener đều có thể được gọi. Nếu transaction commit, chỉ listener `AFTER_COMPLETION` được gọi.

Nên chọn:

- `AFTER_ROLLBACK` khi chỉ cần phản ứng với rollback.
- `AFTER_COMPLETION` khi cần dọn dẹp hoặc ghi nhận ở cả hai kết quả.
- `AFTER_COMMIT` khi chỉ xử lý sau commit thành công.

Không dùng `AFTER_COMPLETION` rồi tự kiểm tra trạng thái rollback nếu yêu cầu đơn giản có thể được biểu diễn trực tiếp bằng phase phù hợp.

## 9. Thứ tự giữa nhiều listener rollback

Có thể dùng `@Order` để sắp xếp các transactional listener cùng nhận event:

~~~java
@Component
class RollbackListeners {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    @Order(10)
    public void releaseReservation(OrderPlacementAttempted event) {
        System.out.println("Release reservation");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    @Order(20)
    public void recordAudit(OrderPlacementAttempted event) {
        System.out.println("Record rollback audit");
    }
}
~~~

Giá trị order nhỏ hơn có độ ưu tiên cao hơn. `@Order` giúp sắp xếp callback trong cùng cơ chế dispatch; nó không tạo transaction mới, không bảo đảm retry và không điều phối một workflow phân tán.

Nếu bước audit chỉ được thực hiện sau khi bước release thành công, hãy mô hình hóa quan hệ phụ thuộc đó trong một service điều phối rõ ràng. Không nên dựa vào thứ tự listener để bảo đảm một chuỗi nghiệp vụ phức tạp.

## 10. Ghi database từ AFTER_ROLLBACK cần transaction mới

Đây là lưu ý quan trọng khi callback cần lưu một bản ghi audit hoặc trạng thái xử lý.

Ở phase `AFTER_ROLLBACK`, transaction gốc đã rollback. Tuy nhiên, các transaction resource có thể vẫn còn được gắn và truy cập trong quá trình callback. Một thao tác data access mới có thể vẫn tham gia resource của transaction cũ, nhưng không có lần commit tiếp theo để lưu thay đổi.

Vì vậy, nếu listener cần ghi database, hãy mở transaction độc lập, thường bằng propagation `REQUIRES_NEW`.

~~~java
@Component
class OrderRollbackListener {
    private final RollbackAuditService auditService;

    OrderRollbackListener(RollbackAuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacementAttempted event) {
        auditService.record(event.orderId(), "TRANSACTION_ROLLED_BACK");
    }
}

@Service
class RollbackAuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId, String outcome) {
        // Ghi audit trong transaction độc lập.
    }
}
~~~

Tách service thành bean riêng giúp lời gọi `record` đi qua Spring proxy. Nếu gọi một method `@Transactional(REQUIRES_NEW)` khác trong cùng object bằng self-invocation, proxy mặc định không được áp dụng.

Có thể dùng `TransactionTemplate` với transaction definition `PROPAGATION_REQUIRES_NEW` nếu cần điều khiển tường minh. Dù dùng cách nào, transaction audit là transaction mới; nó không thể khôi phục transaction nghiệp vụ đã rollback.

## 11. Dùng AFTER_ROLLBACK để làm gì?

Các trường hợp phù hợp:

- Giải phóng một reservation hoặc tài nguyên đã được giữ ở hệ thống ngoài.
- Ghi nhận một lần xử lý thất bại vào audit store độc lập.
- Phát cảnh báo vận hành khi transaction quan trọng rollback.
- Khởi chạy quy trình bù trừ cho side effect ngoài database.
- Cập nhật metric hoặc trạng thái quan sát lỗi.
- Thông báo một hệ thống khác về kết quả thất bại khi yêu cầu nghiệp vụ cho phép.

Cần cân nhắc kỹ với các side effect:

- Gửi email hoặc webhook trong callback không có retry bền vững.
- Gọi API downstream chậm có thể kéo dài quá trình hoàn tất transaction.
- Ghi audit vào cùng transaction đã rollback sẽ không lưu được.
- Gửi message ra broker trực tiếp có thể gặp lỗi giữa thời điểm rollback và publish.
- Callback chạy trong process không bảo đảm được thực hiện nếu ứng dụng dừng đột ngột.

Nếu thông báo rollback phải được giao bền vững, cần một thiết kế lưu trữ/điều phối riêng. Có thể dùng transaction độc lập để ghi failure record/outbox sau rollback rồi relay đến broker. Outbox ghi trong transaction đã rollback cũng sẽ bị rollback, nên phải xác định rõ transaction độc lập dùng để lưu kết quả thất bại.

## 12. Transaction propagation ảnh hưởng đến thời điểm listener

Khi method transaction lồng nhau hoặc tham gia transaction bên ngoài, listener gắn với kết quả của transaction mà nó được đăng ký vào.

- `REQUIRED`: method tham gia transaction hiện có nếu có. Listener đợi kết quả cuối cùng của transaction chung; method con kết thúc bình thường chưa có nghĩa listener chạy.
- `REQUIRES_NEW`: tạo transaction độc lập. Listener được đăng ký trong transaction mới và chạy theo kết quả của transaction đó.
- `SUPPORTS`: tham gia transaction nếu có; nếu không, không có synchronization để đăng ký listener, trừ khi fallback được bật.
- `NOT_SUPPORTED`: chạy ngoài transaction sau khi tạm ngưng transaction hiện tại; transactional listener có thể bị bỏ qua hoặc chạy fallback.
- `MANDATORY`: yêu cầu transaction hiện có; nếu không có sẽ ném exception trước khi phần thân method chạy.

Ví dụ với `REQUIRED`: service con có thể publish event rồi trả về, nhưng listener `AFTER_ROLLBACK` chỉ chạy nếu transaction ngoài cùng cuối cùng rollback. Nếu transaction ngoài cùng commit, listener không chạy.

Không suy luận phase từ việc một method cụ thể ném exception. Hãy xem propagation và kết quả cuối cùng của transaction thực sự sở hữu synchronization.

## 13. Reactive transaction và AFTER_ROLLBACK

Từ Spring Framework 6.1, transactional event listener cũng hỗ trợ reactive transaction do `ReactiveTransactionManager` quản lý.

Reactive transaction lưu context trong Reactor Context thay vì `ThreadLocal`. Khi publish event trong reactive transaction, event source cần mang `TransactionContext`. Có thể dùng `TransactionalEventPublisher` để tạo event đúng source và compose Mono trả về vào cùng reactive pipeline.

Ví dụ khái niệm:

~~~java
return repository.save(entity)
        .flatMap(saved ->
                transactionalEventPublisher
                        .publishEvent(new OrderPlacementAttempted(saved.id()))
                        .thenReturn(saved)
        )
        .as(transactionalOperator::transactional);
~~~

Listener vẫn có thể khai báo:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRollback(OrderPlacementAttempted event) {
    // Xử lý sau khi reactive transaction rollback.
}
~~~

Không gọi `.subscribe()` tách rời bên trong service. Nếu event không mang transaction context hoặc subscription nằm ngoài transaction pipeline, Spring không thể gắn listener với đúng reactive transaction. Với ứng dụng imperative dùng `PlatformTransactionManager`, event source không cần tự chứa `TransactionContext` theo cách reactive này.

## 14. Kiểm thử AFTER_ROLLBACK

Kiểm thử nên dùng transaction manager thật hoặc test transaction phù hợp. Chỉ gọi trực tiếp method listener không chứng minh Spring đăng ký và gọi callback đúng phase.

Các trường hợp nên kiểm tra:

1. Publish event trong transaction rồi rollback: listener được gọi đúng một lần.
2. Publish event trong transaction rồi commit: listener AFTER_ROLLBACK không được gọi.
3. Đánh dấu rollback-only: listener chạy khi transaction thực sự kết thúc bằng rollback.
4. Checked exception không có `rollbackFor`: xác nhận transaction có thể commit và listener không chạy theo quy tắc mặc định.
5. Checked exception có `rollbackFor`: xác nhận rollback và listener chạy.
6. Publish ngoài transaction với fallback false: listener bị bỏ qua.
7. Publish ngoài transaction với fallback true: listener chạy ngay, dù không có rollback.
8. Listener ghi database qua `REQUIRES_NEW`: bản ghi audit tồn tại sau khi transaction gốc rollback.

Ví dụ kiểm tra với Spring Boot integration test có thể gọi service thật và xác nhận audit/rollback state sau khi lời gọi qua proxy hoàn tất. Nếu cần kiểm tra không có callback ở nhánh commit, dùng một recording listener ghi số lần nhận event rồi assert bằng 0.

Không dùng `Thread.sleep` để chờ callback đồng bộ. Với listener async, dùng latch/future hoặc Awaitility với timeout hữu hạn và kiểm thử riêng chính sách lỗi của executor.

## 15. Lỗi thường gặp

- **Publish event sau khi transaction đã rollback rồi mong AFTER_ROLLBACK nhận nó.** Listener cần được đăng ký trong transaction trước khi transaction kết thúc.
- **Nghĩ method có exception là chắc chắn rollback.** Checked exception mặc định có thể không rollback; hãy kiểm tra rollback rules và trạng thái cuối cùng.
- **Dùng AFTER_ROLLBACK để đảo ngược thay đổi database.** Database đã rollback thay đổi của transaction gốc; listener chủ yếu xử lý side effect bên ngoài hoặc ghi nhận kết quả.
- **Ghi audit bằng transaction mặc định trong callback.** Resource cũ có thể vẫn được gắn nhưng không còn commit; dùng REQUIRES_NEW cho lần ghi độc lập.
- **Gọi method REQUIRES_NEW trong cùng bean.** Self-invocation có thể bỏ qua proxy.
- **Bật fallbackExecution rồi coi callback là bằng chứng rollback.** Không có transaction thì fallback chạy ngay, không có rollback thực tế.
- **Dùng AFTER_COMPLETION khi chỉ cần rollback.** Chọn AFTER_ROLLBACK để tránh chạy cả khi commit.
- **Cho rằng listener callback có retry hoặc durable delivery.** Transactional event listener trong process không tự cung cấp retry bền vững.
- **Dùng listener order làm workflow điều phối.** @Order chỉ sắp thứ tự callback, không tạo quan hệ phụ thuộc nghiệp vụ.
- **Bỏ qua propagation.** Listener gắn với transaction thực sự sở hữu synchronization, không nhất thiết là method gần nhất đã publish.

## 16. Checklist triển khai

- [ ] Event được publish trong transaction mà kết quả rollback cần quan sát?
- [ ] Listener khai báo rõ `phase = TransactionPhase.AFTER_ROLLBACK`?
- [ ] Transaction manager thực sự rollback theo exception/rollback rule?
- [ ] Đã phân biệt runtime exception, checked exception và rollback-only?
- [ ] Event payload chứa đủ dữ liệu để xử lý sau rollback?
- [ ] Không dùng fallback true nếu cần xác nhận rollback thực sự?
- [ ] Nếu ghi database trong callback, đã dùng transaction độc lập `REQUIRES_NEW`?
- [ ] Lời gọi REQUIRES_NEW đi qua Spring proxy?
- [ ] Side effect ngoài hệ thống có timeout, idempotency và xử lý lỗi?
- [ ] Đã kiểm thử cả commit, rollback, fallback và propagation?
- [ ] Nếu cần giao nhận bền vững, đã thiết kế failure record/outbox/broker riêng?

`AFTER_ROLLBACK` cho phép Spring gọi listener khi transaction chứa event kết thúc bằng rollback. Hãy publish event trong transaction, chọn phase rõ ràng và để listener xử lý các tác động phù hợp với trạng thái thất bại. Nếu callback cần ghi database, mở transaction mới bằng `REQUIRES_NEW`; nếu cần giao nhận bền vững, bổ sung cơ chế lưu trữ và retry riêng.

## Tài liệu tham khảo

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [TransactionSynchronization.afterCompletion Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
