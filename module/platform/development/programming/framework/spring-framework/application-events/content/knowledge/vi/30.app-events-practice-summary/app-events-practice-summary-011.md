# Checklist review Application Events trong Spring Framework

## 1. Mục đích của checklist

Spring Framework hỗ trợ publish–subscribe nội bộ bằng **ApplicationEventPublisher**, **ApplicationListener**, **@EventListener** và **@TransactionalEventListener**. Mẫu này giảm coupling giữa publisher và những thành phần phản ứng với sự kiện. Nhưng việc có annotation không tự bảo đảm đúng transaction, đúng thread, không mất event hay chống xử lý trùng.

Checklist này dành cho code review của một PR dùng **Spring Framework Application Events**, thuộc nhóm **Thực hành và tổng kết**. Người review cần xác nhận:

- **Event contract**: sự kiện là sự thật nghiệp vụ nào, phát khi nào, dữ liệu gì?
- **Publisher và listener ownership**: ai phát, ai nghe, đăng ký trong context nào?
- **Transaction**: event được phản ứng trước commit, sau commit hay lúc rollback?
- **Execution**: đồng bộ hay async, exception ảnh hưởng caller thế nào?
- **Reliability**: nếu JVM chết, broker retry, event trùng hoặc sai thứ tự thì sao?
- **Security và observability**: dữ liệu nhạy cảm, trace, metric và alert đã đủ chưa?
- **Verification**: có test minh chứng, không chỉ mock publisher?

Với mỗi mục, ghi **PASS/FAIL/N/A** kèm bằng chứng. Những mục không liên quan (ví dụ outbox cho event telemetry best-effort) có thể ghi N/A với lý do. Nhưng đối với event thanh toán hoặc lập hóa đơn quan trọng, không thể dùng một listener in-memory rồi tuyên bố đã đảm bảo delivery.

## 2. Xác định event có phải giải pháp phù hợp không

**Event** nên mô tả một sự thật đã xảy ra, ví dụ **OrderPlaced**, **PaymentCaptured**, **StockReserved**. **Command** yêu cầu điều cần làm, ví dụ **ChargePayment** hoặc **SendInvoice**. Những tên như **ProcessOrderEvent** thường che một command phía sau event, khiến ownership không rõ.

| Câu hỏi | Tín hiệu tốt | Cảnh báo |
| --- | --- | --- |
| Listener có độc lập không? | Analytics lỗi không thay đổi tính hợp lệ của đơn hàng | Listener phụ quyết định kết quả use case |
| Có thứ tự bắt buộc không? | Application service/orchestrator nắm điều kiện chuyển bước | Chỉ dựa @Order giữa listeners |
| Cần trả kết quả tổng thể không? | Workflow owner/trạng thái rõ | Caller publish xong thì báo thành công của cả chain |
| Event có nhiều subscribers không? | Mỗi consumer có trách nhiệm riêng | Nhiều consumers cùng làm một side effect |
| Có phải chuyển integration event qua service không? | Durable broker/outbox theo SLA | Chỉ dùng Spring in-process event |

Một chuỗi event A → B → C có thể hợp lý cho nhiều phản ứng độc lập, nhưng khi quy trình có retry, timeout, bù trừ và cần resume sau restart, **orchestration** thường dễ review hơn. **@Order** không phải workflow engine, không đảm bảo async completion hay transaction chung.

## 3. Review event contract

Một event thuần Java 17:

~~~java
public record OrderPaid(
        String eventId,
        String orderId,
        String paymentId,
        long aggregateVersion) {}
~~~

Đây là kiểu dữ liệu minh họa, chưa phải chương trình độc lập. Spring có thể publish POJO mà không cần class extends **ApplicationEvent**. Domain không cần import Spring chỉ để định nghĩa sự thật nghiệp vụ; adapter application/infrastructure có thể bổ sung envelope, tracing metadata và transport.

**Checklist contract:**

- [ ] Tên event nói rõ sự thật đã xảy ra; không phát **OrderPaid** trước khi thanh toán thực sự được xác nhận theo hợp đồng.
- [ ] Event có identity ổn định (**eventId**) nếu cần retry/redelivery; không tạo ID mới cho cùng một lần phát lại.
- [ ] **aggregateId** và **aggregateVersion/sequence** có khi cần ordering hoặc projection.
- [ ] Integration event có **eventType/schemaVersion** để consumer version cũ và mới cùng hoạt động.
- [ ] Payload immutable/snapshot có ý nghĩa, không giữ JPA entity mutable hoặc lazy proxy qua async.
- [ ] Dữ liệu vừa đủ, không serialize cả object graph hoặc bí mật/PII ngoài mục đích cho phép.
- [ ] **occurredAt** có ý nghĩa rõ, nhưng không được dùng làm bằng chứng thứ tự commit tuyệt đối.
- [ ] Trace/correlation ID không bị dùng thay event ID hoặc business key.

Khi contract thay đổi, review compatibility, version migration và tests của producer/consumer. Event class có thể thuần Java trong domain, còn integration message có metadata khác; không cần ép domain phụ thuộc Kafka hay Spring.

## 4. Review publisher và context scope

Lần theo đường đi từ REST controller, job hoặc consumer đến nơi gọi **ApplicationEventPublisher.publishEvent(Object)**:

1. Bean publisher thuộc **ApplicationContext** nào?
2. Có bao nhiêu code paths phát cùng một business event?
3. Event được publish **trong transaction đang mở hay sau khi method đã kết thúc**?
4. Lúc retry command, có tạo duplicate state transition/event không?
5. Nếu service dùng **@Transactional**, caller có đi qua Spring proxy hay self-invocation bỏ qua advice?
6. Nếu dùng Spring Data **@DomainEvents**, repository method nào thực sự publish và pending events được clear khi nào?
7. Nếu event không được mất, có lưu ý định phát **trong cùng database transaction** với state change không?

Ví dụ snippet:

~~~java
@Transactional
public void pay(String id) {
    Order order = orders.load(id);
    order.markPaid();
    orders.save(order);
    publisher.publishEvent(new OrderPaidEvent(id));
}
~~~

Đây không phải file compile độc lập. **publishEvent(...)** không phải dấu mốc commit. Listener thường có thể nhận trước commit; transactional listener có thể đăng ký callback theo phase.

**Context hierarchy:** Trong parent–child ApplicationContext, event từ child có thể được forward lên parent. Parent listener có thể thấy cả lifecycle events từ parent và child. Nếu cần chỉ xử lý **ContextRefreshedEvent** của chính context chứa listener, so sánh **event.getApplicationContext()** với owning context. Với POJO payload, không nên suy origin gốc chỉ từ **PayloadApplicationEvent.getSource()** ở ancestor; dùng event metadata có contract rõ.

## 5. Review listener registration

Spring cần biết listener là một **managed bean**; gọi trực tiếp method annotated bằng Java không chứng minh Spring đã đăng ký nó.

- [ ] Listener được tạo bởi @Bean, @ComponentScan hoặc cơ chế container phù hợp.
- [ ] Listener nhận type đúng, không nghe toàn bộ **ApplicationEvent** khi chỉ cần một business type.
- [ ] **@EventListener(condition=...)** dùng SpEL và argument metadata có test.
- [ ] Generic event types không bị type erasure làm lọc sai.
- [ ] Không có duplicate bean registration do scan cùng package ở parent/child.
- [ ] Không có vòng lặp publish event vô hạn hoặc event chain không có owner.
- [ ] Phạm vi subscription đúng theo module, tenant và business boundary.

**Return event từ @EventListener:** Synchronous listener có thể trả object/Collection/array để Spring publish các event tiếp theo. **Async listener không hỗ trợ cơ chế publish bằng return value**; phải gọi publisher tường minh nếu cần. Không dùng return-value chaining cho một saga phức tạp mà không có state/retry/compensation.

## 6. Review transaction phase

| Loại listener | Thời điểm | Cần kiểm tra |
| --- | --- | --- |
| **@EventListener** | Dispatch ngay khi publish; mặc định sync | Side effect chạy trước commit có hợp lệ không? |
| **@TransactionalEventListener(BEFORE_COMMIT)** | Trước commit | Không giả định DB đã commit |
| **AFTER_COMMIT** | Sau commit thành công | Có ghi DB mới đúng transaction và recovery không? |
| **AFTER_ROLLBACK** | Sau rollback | Cleanup/compensation đúng scope không? |
| **AFTER_COMPLETION** | Cả commit và rollback | Handler có phân biệt outcome khi cần? |
| **fallbackExecution=true** | Cho phép chạy ngoài transaction | Có vi phạm “chỉ sau commit” không? |

Mặc định **@TransactionalEventListener** dùng **AFTER_COMMIT**, **fallbackExecution=false**. Event publish ngoài transaction tương thích sẽ không kích hoạt listener mặc định.

### Phản ví dụ 1: side effect trước rollback

~~~text
BEGIN TX
  save Order(status=PAID)
  publish OrderPaid
      -> @EventListener gọi API lập hóa đơn
  exception -> ROLLBACK
~~~

Hóa đơn có thể đã được tạo dù Order không commit. Đây là lỗi nếu nghiệp vụ chỉ cho phép lập hóa đơn sau commit. **@TransactionalEventListener(AFTER_COMMIT)** giúp lựa chọn thời điểm, nhưng vẫn có nguy cơ callback mất sau commit khi JVM crash.

### Phản ví dụ 2: DB write trong AFTER_COMMIT không có transaction mới

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void on(OrderPaidEvent event) {
    auditRepository.save(new AuditEntry(event.orderId()));
}
~~~

Đây là snippet phản ví dụ. Trong phase completion, resource từ transaction đã commit có thể còn bind, nhưng **không có commit mới** cho các writes phát sinh. Nếu cần ghi audit/read model sau commit, dùng **@Transactional(propagation = Propagation.REQUIRES_NEW)** trên Spring-managed service gọi qua proxy, hoặc **TransactionTemplate** với **PROPAGATION_REQUIRES_NEW** và integration test kiểm tra persisted row.

Nếu audit phải atomic cùng business state, ghi nó trong transaction gốc. **@Async** không làm thread worker tự tham gia transaction imperative của publisher.

### Test transaction

Trong Spring TestContext, test method có **@Transactional** thường rollback khi kết thúc, khiến AFTER_COMMIT không chạy. Để kiểm thử commit trong cùng test, dùng **TestTransaction.flagForCommit(); TestTransaction.end()**, hoặc **TransactionTemplate** trong test không annotated @Transactional.

## 7. Review sync/async và exception handling

**SimpleApplicationEventMulticaster** mặc định gọi listeners trên **thread publisher**. Listener chậm làm caller chậm; nếu listener ném exception và không có ErrorHandler phù hợp, exception có thể propagate về publisher. Không nên để một observer analytics không critical làm thanh toán trả lỗi ngoài chủ đích.

Hai cơ chế async chính:
- **@Async** cho từng listener, với @EnableAsync và Spring-managed TaskExecutor.
- **applicationEventMulticaster** tùy chỉnh dùng **setTaskExecutor(...)**.

**ApplicationListener.supportsAsyncExecution()** có thể khiến một số listeners, đặc biệt transaction-synchronized listeners, chạy ở publisher thread để đăng ký callbacks đúng cách, dù multicaster có executor.

Checklist async:
- [ ] Đã biết executor thực tế được sử dụng; không vô tình double scheduling.
- [ ] Đã cấu hình pool size, queue capacity, rejection và graceful shutdown.
- [ ] Exception của void @Async listener có **AsyncUncaughtExceptionHandler**, logs/metrics hoặc retry theo contract.
- [ ] **ThreadLocal/MDC/current trace context** được propagate khi cần; có thể dùng **ContextPropagatingTaskDecorator** với Micrometer accessors phù hợp.
- [ ] Không kỳ vọng async listener return event để chain tự hoạt động.
- [ ] Không kỳ vọng @Async mang transaction caller sang worker.
- [ ] Event critical có durable queue/outbox thay vì chỉ queue trong memory.
- [ ] Test async dùng CountDownLatch/Awaitility/polling, không dùng Thread.sleep cố định.

**@Order chỉ ưu tiên dispatch**, không bảo đảm thứ tự hoàn tất async, không lưu trạng thái workflow và không thay thế transaction.

## 8. Review reliability, retry và idempotency

Nếu domain DB commit nhưng JVM chết trước khi gửi event, **Spring ApplicationEventPublisher** không có bản ghi bền vững để replay. **AFTER_COMMIT** không phải durable queue.

Với event quan trọng, mẫu thường dùng:

~~~text
BEGIN PRODUCER DB TRANSACTION
   update business state
   insert outbox(eventId, aggregateId, payload)
COMMIT
     |
     v
outbox relay -> broker ACK -> consumer
     |
     +-- relay crash sau send trước ACK: có thể gửi lại
~~~

Outbox row và business state phải **cùng transaction thật**, không nằm trong hai REQUIRES_NEW độc lập. Relay chỉ mark SENT sau xác nhận theo broker contract, có retry/backoff, claim/lease và monitoring. Nếu ACK bị mất, cùng eventId có thể được gửi lại.

Consumer nên dùng idempotency:

~~~text
BEGIN CONSUMER DB TRANSACTION
   insert processed_events(consumer_name,eventId)
   nếu mới: apply business DB effect
   nếu duplicate: skip
COMMIT
ACK
~~~

Dedup marker và DB effect phải cùng local transaction. Với API bên ngoài như payment/email, inbox local không tự bao trùm external side effect; cần idempotency key ở provider hoặc reconciliation.

- [ ] Đã xác định event best-effort hay critical.
- [ ] Critical event có durable publication/recovery.
- [ ] eventId ổn định khi retry.
- [ ] Consumer idempotent trước duplicate/redelivery.
- [ ] Event cũ hoặc đảo thứ tự được xử lý bằng version/sequence phù hợp.
- [ ] Có backoff, parking/DLQ và đường repair.
- [ ] Có alarm cho outbox pending age/consumer lag.
- [ ] Có backup/retention, không purge event pending.
- [ ] Replay projection không gửi lại email hoặc charge tiền.
- [ ] Có reconciliation business outcome, không chỉ tin broker ACK.

**At-least-once** thường cho phép duplicate; **exactly-once business effect** không tự có nếu chưa xử lý idempotency tại nơi side effect thật xảy ra.

## 9. Review read model và ordering

Application Events thường cập nhật read model hoặc search index. Cần xác định **read-after-write có phải yêu cầu không**:

- Cùng DB, cần strong consistency: ghi projection và domain trong cùng transaction khi phù hợp.
- AFTER_COMMIT: cập nhật sau commit, transaction mới cho DB write, nhưng có crash window.
- Outbox + consumer: eventual consistency, cần version/lag monitoring/rebuild.

Read model có thể stale; không dùng nó làm nguồn duy nhất xác minh invariant quan trọng như saldo, stock hoặc payment completion.

~~~text
OrderPaid(order=A,version=2)      -> projection PAID
OrderPlaced(order=A,version=1)    -> event cũ đến muộn
~~~

Nếu projector ghi đè theo arrival order, nó có thể làm PAID lùi về CREATED. Snapshot projection có thể dùng atomic version guard/CAS; delta event cần dedup từng event và strict sequencing nếu phụ thuộc các bước. Với nhiều sources, không so sánh version của hai aggregates khác nhau như một sequence chung.

Nếu index hỏng, liệu có **event history, retained topic, outbox archive hoặc write-store snapshot** để rebuild? **ApplicationEventPublisher không có replay mặc định**. Khi replay, tách projection handler khỏi side effects nghiệp vụ.

## 10. Review security, observability và vận hành

Security checklist:
- [ ] Payload không chứa secrets, tokens, mật khẩu hoặc PII ngoài mục đích.
- [ ] Consumer/topic/queue có ACL và data classification phù hợp.
- [ ] Tenant identity được kiểm tra ở trust boundary, không chỉ tin metadata đến từ nguồn ngoài.
- [ ] Có giới hạn payload size và kiểm soát event loops/storms.
- [ ] Logs, DLQ, archive và trace baggage có retention và redaction.
- [ ] EventId/correlationId không bị nhầm là authentication credential.

Observability fields hữu ích:

| Field/metric | Ý nghĩa |
| --- | --- |
| eventId, eventType, schemaVersion | Nhận diện và contract |
| aggregateId, aggregateVersion | Business identity/ordering |
| publisher, listenerName, contextId | Đường dispatch |
| traceId, correlationId | Liên kết request/workflow |
| phase, threadName | Transaction và async diagnostics |
| outcome, attempt, duration | Success/failure/retry |
| executor queue depth, rejection count | Async pressure |
| outbox pending count, oldest pending age | Event kẹt |
| consumer lag, parked count, dedup total | Delivery health |
| business completion lag | Kết quả cuối |

Trace context qua thread pool cần propagation; qua broker phải inject/extract headers. **Broker ACK không chứng minh consumer đã hoàn tất nghiệp vụ**. Với event quan trọng cần đo outcome như InvoiceIssued sau OrderPaid, không chỉ metric gửi thành công.

## 11. Ma trận test tối thiểu

| Kịch bản | Kết quả cần chứng minh |
| --- | --- |
| Publish trong TX rồi commit | AFTER_COMMIT chạy đúng lúc |
| Publish trong TX rồi rollback | AFTER_COMMIT không chạy; data rollback |
| Exception sau publish | Ordinary listener có thể chạy, phase đúng outcome |
| Publish ngoài TX | fallbackExecution đúng hợp đồng |
| Sync listener ném exception | Caller hoặc ErrorHandler xử lý đúng |
| Async listener lỗi/rejection | Có error policy và monitoring |
| Duplicate/redelivery | Side effect không nhân đôi |
| Event cũ/đảo thứ tự | Projection không bị ghi lùi |
| Child context phát event | Parent listener không gây xử lý trùng ngoài ý muốn |
| Worker crash sau broker ACK trước mark SENT | Retry có thể trùng nhưng consumer dedup |
| Crash sau business commit | Outbox/recovery phục hồi nếu event critical |
| Replay/rebuild | Projection đúng mà không gọi lại side effect cũ |
| Schema version mismatch | Consumer tương thích hoặc park có kiểm soát |

**Test listener method trực tiếp** chỉ xác minh Java logic, không chứng minh Spring annotation đã được đăng ký và chạy đúng phase. Cần integration test qua ApplicationContext và transaction manager thật. Với async dùng latch/timeout, không ngủ cố định.

## 12. Ví dụ Java 17+ chạy được để tự review

Dự án dùng **Spring Framework 6.2.9**, **Spring JDBC**, **H2 2.3.232**, **Java 17+** và **Gradle 8.x**, không cần Spring Boot. Demo minh họa immediate listener, AFTER_COMMIT, AFTER_ROLLBACK và publish ngoài transaction.

### Cấu trúc và Gradle

~~~text
spring-event-review/
  build.gradle
  src/main/java/demo/SpringEventReview.java
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}
repositories {
    mavenCentral()
}
dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'org.springframework:spring-jdbc:6.2.9'
    runtimeOnly 'com.h2database:h2:2.3.232'
}
application {
    mainClass = 'demo.SpringEventReview'
}
~~~

### src/main/java/demo/SpringEventReview.java

~~~java
package demo;

import javax.sql.DataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringEventReview {

    public record OrderSubmitted(String id) {}

    public static final class Listeners {
        @EventListener
        public void immediate(OrderSubmitted event) {
            System.out.println("immediate: " + event.id());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_COMMIT)
        public void committed(OrderSubmitted event) {
            System.out.println("after-commit: " + event.id());
        }

        @TransactionalEventListener(
                phase = TransactionPhase.AFTER_ROLLBACK)
        public void rolledBack(OrderSubmitted event) {
            System.out.println("after-rollback: " + event.id());
        }
    }

    public static final class Service {
        private final JdbcTemplate db;
        private final TransactionTemplate tx;
        private final ApplicationEventPublisher publisher;

        public Service(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            this.db = db;
            this.tx = new TransactionTemplate(manager);
            this.publisher = publisher;
        }

        public void submit(String id, boolean rollback) {
            tx.executeWithoutResult(status -> {
                db.update("INSERT INTO orders(id) VALUES (?)", id);
                publisher.publishEvent(new OrderSubmitted(id));
                if (rollback) {
                    status.setRollbackOnly();
                }
            });
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:review_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            JdbcTemplate db = new JdbcTemplate(ds);
            db.execute(
                "CREATE TABLE IF NOT EXISTS orders "
                + "(id VARCHAR(80) PRIMARY KEY)");
            return db;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        Listeners listeners() {
            return new Listeners();
        }

        @Bean
        Service service(
                JdbcTemplate db,
                PlatformTransactionManager manager,
                ApplicationEventPublisher publisher) {
            return new Service(db, manager, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Service service = context.getBean(Service.class);
            JdbcTemplate db = context.getBean(JdbcTemplate.class);

            System.out.println("case: commit");
            service.submit("A", false);

            System.out.println("case: rollback");
            service.submit("B", true);

            System.out.println("case: outside");
            context.publishEvent(new OrderSubmitted("C"));

            int count = db.queryForObject(
                "SELECT COUNT(*) FROM orders", Integer.class);
            System.out.println("db rows: " + count);
        }
    }
}
~~~

Chạy tại thư mục **spring-event-review**:

~~~bash
gradle --console=plain -q run
~~~

**Stdout do chính chương trình in ra** với synchronous multicaster mặc định:

~~~text
case: commit
immediate: A
after-commit: A
case: rollback
immediate: B
after-rollback: B
case: outside
immediate: C
db rows: 1
~~~

Giải thích: A commit nên immediate và AFTER_COMMIT đều chạy. B đã publish nhưng rollback, nên immediate đã chạy còn AFTER_ROLLBACK được gọi thay vì AFTER_COMMIT; B không tồn tại trong DB. C publish ngoài transaction nên chỉ listener thường chạy. Database còn duy nhất A.

**Câu hỏi thực hành:** Nếu immediate listener gửi email thì B có gửi email sai không? Nếu AFTER_COMMIT ghi DB, cần transaction mới ở đâu? Nếu worker async chết trước khi xử lý, có durable outbox không? Nếu event redeliver, downstream có idempotent không?

Demo không triển khai outbox/broker/async hoặc security; không dùng output này để tuyên bố event critical có durability.

## 13. Phân cấp phát hiện khi review PR

**Blocker:**
- Critical event có thể mất sau business commit và không có durable recovery.
- External side effect chạy trước commit khi nghiệp vụ không cho phép.
- Payment/stock/invoice bị lặp khi redelivery mà không có idempotency.
- Async listener phụ thuộc transaction của publisher.
- Event chứa credentials hoặc vi phạm tenant/data privacy boundary.
- Hai handlers thực hiện cùng một effect bắt buộc mà không có ownership.
- Thiếu kiểm thử transaction/failure path bảo vệ business invariant.

**Major:**
- Thiếu eventId/version khi cần retry/ordering.
- Không có executor rejection/shutdown/error policy.
- @Order bị dùng thay orchestration.
- Không monitor pending age/consumer lag cho event có SLA.
- Schema migration không bảo đảm consumer compatibility.
- Tests chỉ verify publishEvent mà không kiểm tra listener transaction behavior.

**Improvement:**
- Chuẩn hóa event naming, metadata, docs và structured log.
- Bổ sung dashboard hoặc test nâng cao cho rủi ro thấp.
- Giảm payload, tách listener quá lớn, tối ưu performance dựa trên đo lường.

Một vấn đề có thể là blocker với thanh toán nhưng chỉ là improvement với telemetry best-effort. **Reviewer phải nêu hậu quả và bằng chứng**, không đánh đồng mọi event.

### Mẫu comment review

**Phát hiện:** “@EventListener hiện gọi invoice API trước khi domain transaction commit.”

**Tác động:** “Nếu transaction rollback, invoice vẫn có thể được tạo.”

**Đề xuất:** “Đặt side effect ở boundary sau commit; nếu không được mất khi JVM crash, ghi transactional outbox cùng business state và dùng consumer idempotent. Thêm rollback/crash-window tests.”

## 14. Phiếu checklist cuối cùng trước khi approve

### A. Contract/ownership
- [ ] Event biểu đạt một sự thật rõ ràng và đúng thời điểm.
- [ ] Event-driven phù hợp hơn direct call/orchestration.
- [ ] Publisher/consumer/side-effect owner rõ.
- [ ] Payload immutable, gọn, không chứa dữ liệu bị cấm.
- [ ] Event ID, aggregate ID, version và schema có khi cần.

### B. Spring wiring
- [ ] Listener là Spring-managed bean, type và condition đúng.
- [ ] Không có duplicate registration ngoài ý muốn.
- [ ] Parent–child context và lifecycle events đã được xem xét nếu có.
- [ ] Không nhầm @Order hoặc return-value chaining với workflow.
- [ ] Executor/AsyncUncaughtExceptionHandler/error policy được cấu hình khi cần.

### C. Transaction/reliability
- [ ] Biết transaction boundary của publisher.
- [ ] @TransactionalEventListener phase/fallback đúng contract.
- [ ] Rollback không gây external side effect sai.
- [ ] DB writes trong AFTER_COMMIT có transaction mới khi cần.
- [ ] Critical events có durability, retries và recovery.
- [ ] Consumer idempotent, xử lý out-of-order và replay an toàn.
- [ ] Có reconciliation/parking/monitoring khi cần.

### D. Security/observability
- [ ] Payload, logs, trace baggage đáp ứng bảo mật/retention.
- [ ] Consumer xác minh tenant/trust boundary.
- [ ] Trace/event/correlation IDs theo dõi được qua executor/broker.
- [ ] Có metrics, pending-age alerts, lag và business completion checks.

### E. Tests
- [ ] Integration test chứng minh Spring dispatch đúng.
- [ ] Có commit/rollback/outside-transaction cases.
- [ ] Có async error/rejection tests nếu dùng async.
- [ ] Có duplicate/stale/replay tests nếu có redelivery.
- [ ] Có crash/restart/broker outage tests nếu event critical.
- [ ] Tests kiểm tra **persisted business outcome**, không chỉ verify publisher.

## 15. Review nhanh trong 60 giây

1. Event là **sự thật gì**, ai phát?
2. Có subscriber nào mang business step bắt buộc nhưng không có workflow owner?
3. Listener chạy **trước hay sau commit**; rollback thì sao?
4. Synchronous/async exceptions đi đâu?
5. JVM chết ngay sau commit có mất critical event không?
6. Retry/redelivery có thể nhân đôi side effect không?
7. Event đảo thứ tự làm sai projection không?
8. Listener có thể được đăng ký trùng hoặc nhận event từ child context không?
9. Security/logging/tracing/monitoring đủ để điều tra chưa?
10. Tests chứng minh điều gì ngoài happy path?

**Kết luận:** Review Spring Application Events là review **ngữ nghĩa nghiệp vụ, wiring, transaction, async, delivery và vận hành**. Không cần outbox cho mọi event telemetry, nhưng với event payment/invoice quan trọng, callback in-memory không phải delivery guarantee. Chỉ approve khi những rủi ro cần thiết đã được giải quyết và có test hoặc bằng chứng kỹ thuật tương ứng.

### Tài liệu chính thức

- Spring Framework Reference — *Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Javadoc 6.2.9 — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Javadoc 6.2.9 — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Javadoc 6.2.9 — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework Javadoc 6.2.9 — *TransactionalEventListener*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html
