# Spring Modulith hoặc ApplicationEvent cho sự kiện trong ứng dụng

> Phạm vi: dùng sự kiện để giảm phụ thuộc giữa các module trong cùng Spring ApplicationContext, chọn đúng listener và transaction phase, và quyết định khi nào cần Spring Modulith hoặc message broker để bảo đảm publication có thể phục hồi.

## 1. Mục tiêu

Sau bài này, bạn có thể:

- Giải thích `ApplicationEventPublisher`, `@EventListener` và cách Spring phân phối event.
- Phân biệt event đồng bộ, event sau commit và event chạy bất đồng bộ.
- Chọn `ApplicationEvent` cho giao tiếp nội bộ trong một ApplicationContext.
- Dùng Spring Modulith để tách module và quản lý publication của transactional listener.
- Hiểu Event Publication Registry, trạng thái publication, retry và cleanup.
- Externalize event ra Kafka, AMQP, JMS hoặc MessageChannel khi cần tích hợp bên ngoài.
- Thiết kế event contract bất biến, idempotent và có khả năng tương thích phiên bản.
- Kiểm thử event publication và listener theo ranh giới module.

## 2. Event trong Spring là gì?

Event là thông báo rằng một điều gì đó đã xảy ra. Ví dụ `OrderCompleted` nói rằng đơn hàng đã hoàn tất. Module phát event không cần biết tất cả module nào sẽ quan tâm; các listener đăng ký theo kiểu event để nhận thông báo.

Spring cung cấp `ApplicationEventPublisher` để publish event và `ApplicationListener` hoặc `@EventListener` để nhận event. Từ Spring Framework 4.2, có thể publish một object Java thông thường; không bắt buộc class phải kế thừa `ApplicationEvent`.

Ví dụ event contract:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {}
```

Record là lựa chọn phù hợp vì event thường là dữ liệu bất biến. `eventId` giúp nhận diện publication và hỗ trợ idempotency; `orderId` cho phép consumer tải trạng thái nghiệp vụ cần thiết; `occurredAt` ghi nhận thời điểm domain event xảy ra.

Không nên đưa toàn bộ JPA entity hoặc object có lazy relationship vào event. Event nên mang dữ liệu tối thiểu, rõ ràng và ổn định. Nếu consumer cần thêm dữ liệu, có thể tải qua service/repository theo ID và kiểm tra lại trạng thái hiện tại.

## 3. Publish và consume bằng ApplicationEvent

### 3.1. Publish event

Service phát event qua `ApplicationEventPublisher`:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.complete();

        events.publishEvent(new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()));
    }
}
```

Việc gọi `publishEvent` gửi event tới các listener trong cùng `ApplicationContext`. Bản thân API này không ghi event vào broker, không lưu bền vững và không phát event tới một JVM khác.

### 3.2. Nhận event bằng @EventListener

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    @EventListener
    void on(OrderCompleted event) {
        auditLog.record(event.orderId(), "ORDER_COMPLETED");
    }
}
```

Mặc định, Spring xử lý listener đồng bộ trên cùng thread khi event được publish. `publishEvent` chờ listener hoàn tất trước khi trả về. Nếu listener ném exception, exception có thể truyền về publisher và làm transaction đang chạy rollback.

Cách này hữu ích khi listener là một phần của cùng một thao tác nghiệp vụ và cần kết quả đồng bộ. Tuy nhiên, listener chậm sẽ kéo dài request và transaction; listener phụ thuộc nhiều module cũng làm tăng coupling vận hành.

### 3.3. Nhiều listener và module boundary

Một event có thể được nhiều listener cùng loại nhận. Producer chỉ phụ thuộc `ApplicationEventPublisher`, không cần inject từng consumer service.

Trong kiến trúc module, event nên biểu diễn một sự kiện domain hoặc application có ý nghĩa rõ ràng. Đặt event contract ở package/API mà các module được phép phụ thuộc. Tránh biến event thành một command mơ hồ như `DoSomething`; event mô tả điều đã xảy ra, còn command yêu cầu một hành động.

Spring Framework event system hướng tới giao tiếp giữa Spring beans trong cùng ApplicationContext. Nếu cần giao tiếp qua process, host hoặc ứng dụng khác, cần broker hoặc cơ chế integration riêng.

## 4. Event và transaction

### 4.1. Listener đồng bộ trong transaction

Với `@EventListener` đồng bộ mặc định, listener chạy trong luồng publish. Nếu publisher đang ở trong transaction, listener nhìn thấy transaction context đó. Các thay đổi database của listener có thể cùng tham gia transaction và cùng commit/rollback.

Đây là consistency model đơn giản: nếu listener quan trọng thất bại, transaction gốc có thể rollback. Đổi lại, transaction bị kéo dài và các công việc phụ cũng có thể khiến thao tác chính thất bại.

### 4.2. @TransactionalEventListener

Khi listener chỉ nên chạy sau khi transaction commit thành công, dùng `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class SearchIndexListener {

    @TransactionalEventListener
    void on(OrderCompleted event) {
        searchIndex.updateOrder(event.orderId());
    }
}
```

Mặc định listener chạy ở phase `AFTER_COMMIT`. Các phase có thể chọn:

| Phase | Khi listener được gọi |
| --- | --- |
| `BEFORE_COMMIT` | Trước khi transaction commit |
| `AFTER_COMMIT` | Sau khi transaction commit thành công; mặc định |
| `AFTER_ROLLBACK` | Khi transaction rollback |
| `AFTER_COMPLETION` | Sau khi transaction kết thúc, dù commit hay rollback |

Nếu không có transaction đang hoạt động, `@TransactionalEventListener` mặc định không được gọi. Có thể bật `fallbackExecution = true`, nhưng khi đó listener cũng chạy khi event được publish ngoài transaction; chỉ dùng khi semantics này được mong muốn.

Sau `AFTER_COMMIT`, transaction gốc đã hoàn tất. Nếu listener cần ghi database trong transaction riêng, hãy mở transaction mới, thường bằng `@Transactional(propagation = Propagation.REQUIRES_NEW)`.

### 4.3. Bất đồng bộ với @Async

Có thể kết hợp `@Async` và `@TransactionalEventListener`:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class NotificationListener {

    @Async
    @TransactionalEventListener
    void on(OrderCompleted event) {
        notificationService.sendOrderCompleted(event.orderId());
    }
}
```

Cần bật async execution bằng `@EnableAsync` và cấu hình executor có giới hạn thread/queue. Không dùng executor không giới hạn vì burst event có thể làm heap tăng hoặc tạo quá nhiều thread.

Listener bất đồng bộ tách thời gian xử lý khỏi thread publisher. Exception của listener không được ném ngược về caller như listener đồng bộ; cần error handling, logging, metric và cơ chế retry riêng.

Một rủi ro quan trọng: `@TransactionalEventListener` kết hợp `@Async` tự nó không bảo đảm event được lưu bền vững. Nếu process chết sau commit nhưng trước khi task listener bắt đầu, listener có thể không chạy. Nếu event không được phép mất, cần publication registry/outbox hoặc broker có durability.

### 4.4. Reactive transaction

Từ Spring Framework 6.1, transactional event listener hỗ trợ cả transaction thread-bound và reactive transaction. Reactive transaction lưu context trong Reactor Context thay vì ThreadLocal. Khi publish event trong reactive transaction, cần truyền transaction context vào event thông qua `TransactionalEventPublisher`; không giả định listener tự nhìn thấy transaction chỉ vì nó được gọi từ một Reactor chain.

## 5. Spring Modulith và ApplicationModuleListener

### 5.1. Spring Modulith giải quyết điều gì?

Spring Modulith hỗ trợ xây ứng dụng modular monolith: các module vẫn chạy trong cùng ứng dụng nhưng có ranh giới và API rõ ràng. Event là một cách để module phát thông báo mà không phải gọi trực tiếp bean nội bộ của module khác.

Spring Modulith cung cấp `@ApplicationModuleListener` như cách khai báo listener mặc định cho giao tiếp giữa các module. Annotation này kết hợp xử lý bất đồng bộ, transaction-bound event và transaction riêng cho listener (`REQUIRES_NEW`).

```java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryManagement {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        inventory.reserveOrAdjust(event.orderId());
    }
}
```

Với cách này, module Order chỉ phát `OrderCompleted`; module Inventory tự đăng ký listener và xử lý trong transaction riêng sau commit. Cần cấu hình async execution phù hợp cho ứng dụng.

### 5.2. Khi nào dùng ApplicationEvent và khi nào dùng Modulith?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Thông báo đơn giản giữa beans trong cùng ApplicationContext | `ApplicationEventPublisher` + `@EventListener` |
| Listener chỉ chạy sau commit, không cần publication log bền vững | `@TransactionalEventListener` |
| Xử lý module bất đồng bộ, tách transaction và kiểm soát module boundary | `@ApplicationModuleListener` |
| Cần ghi nhận listener nào đã xử lý, phục hồi publication lỗi sau restart | Spring Modulith Event Publication Registry |
| Cần phát event tới process/service khác | Broker hoặc event externalization |
| Cần advanced outbox semantics | Outbox implementation phù hợp, ví dụ hỗ trợ Namastack/JobRunr trong Modulith 2.1 |

Không cần dùng Modulith chỉ để phát một event nội bộ rất đơn giản. Giá trị của Modulith tăng lên khi event là contract giữa module, listener cần xử lý độc lập và việc mất publication là rủi ro cần quản lý.

## 6. Event Publication Registry

### 6.1. Vì sao cần publication registry?

Giả sử transaction tạo đơn hàng commit thành công. Một listener cập nhật tồn kho cần chạy sau commit. Nếu process chết trước khi listener hoàn tất, chỉ dùng `@TransactionalEventListener` thì không có bản ghi bền vững để biết publication nào chưa xử lý.

Spring Modulith Event Publication Registry theo dõi transactional listener. Khi event được publish, registry ghi một publication entry cho từng listener cần nhận event ngay trong transaction nghiệp vụ gốc. Khi listener chạy thành công, entry được đánh dấu completed. Nếu listener lỗi, entry vẫn tồn tại để phục hồi hoặc resubmit.

Như vậy, business transaction và publication record được ghi cùng transaction khi dùng repository hỗ trợ transaction. Đây là nền tảng giúp phát hiện listener chưa hoàn tất sau lỗi process.

### 6.2. Publication lifecycle

Từ Spring Modulith 2.0, publication có các trạng thái:

| Status | Ý nghĩa |
| --- | --- |
| `PUBLISHED` | Publication đã được lưu và đang chờ xử lý |
| `PROCESSING` | Listener đã claim publication và đang chạy |
| `COMPLETED` | Listener hoàn tất thành công |
| `FAILED` | Listener lỗi hoặc publication bị đánh dấu stale |
| `RESUBMITTED` | Publication lỗi đã được gửi lại để xử lý |

Registry còn theo dõi số lần thực thi và thời điểm resubmit. Nhờ vậy, có thể giới hạn số lần thử, lọc theo event type, độ tuổi publication hoặc completion attempts.

### 6.3. Persistence starter

Để lưu publication log, thêm starter phù hợp với persistence technology đang dùng. Ví dụ JDBC:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-jdbc</artifactId>
</dependency>
```

Spring Modulith cũng cung cấp starter JPA và MongoDB. Dùng dependency management/BOM tương thích với Spring Boot của dự án để quản lý version; không trộn tùy tiện các phiên bản Spring Modulith.

JDBC implementation tạo bảng publication nếu được bật schema initialization và bảng chưa tồn tại. Với production, có thể quản lý schema bằng Flyway hoặc Liquibase. Publication log lưu event đã serialize; event schema cần được giữ tương thích trong thời gian publication còn có thể được retry.

### 6.4. Retry và stale publication

Khi listener thất bại, có thể dùng API `FailedEventPublications` để resubmit publication lỗi:

```java
import org.springframework.modulith.events.FailedEventPublications;
import org.springframework.modulith.events.ResubmissionOptions;
import org.springframework.stereotype.Component;

@Component
class EventRecovery {

    private final FailedEventPublications failedPublications;

    EventRecovery(FailedEventPublications failedPublications) {
        this.failedPublications = failedPublications;
    }

    void retryFailedEvents() {
        failedPublications.resubmit(ResubmissionOptions.defaults());
    }
}
```

Đây là ví dụ API cho Spring Modulith 2.0+. Trong vận hành thực tế, nên lọc publication phù hợp, giới hạn batch/concurrency, đặt minimum age và giới hạn completion attempts. Không resubmit toàn bộ lỗi liên tục mà không điều tra nguyên nhân.

Publication có thể bị kẹt ở `PUBLISHED`, `PROCESSING` hoặc `RESUBMITTED` nếu process chết hoặc listener treo. Staleness Monitor từ Modulith 2.0 có thể đánh dấu các publication quá hạn thành `FAILED` khi cấu hình các ngưỡng staleness khác 0. Sau đó có thể resubmit hoặc xử lý thủ công.

### 6.5. Dọn dẹp publication đã hoàn tất

Mặc định completion mode là `UPDATE`: entry completed vẫn được giữ lại để tra cứu. Nếu không dọn dẹp, bảng publication sẽ tăng không giới hạn.

Spring Modulith hỗ trợ các mode:

- `UPDATE`: giữ entry và cập nhật completion date.
- `DELETE`: xóa entry khi listener hoàn tất.
- `ARCHIVE`: chuyển entry completed sang archive store.

Chọn mode theo nhu cầu audit và retention. Nếu giữ `UPDATE`, cần job định kỳ purge các publication completed cũ.

## 7. Externalize event ra broker

### 7.1. Khi nào cần broker?

Application event chỉ được phân phối trong ApplicationContext. Nếu consumer ở process khác, cần một giao thức truyền message như Kafka, AMQP/RabbitMQ hoặc JMS.

Spring Modulith hỗ trợ externalize một số application event sang broker bằng artifact theo broker và annotation `@Externalized`. Ví dụ:

```java
import org.springframework.modulith.events.Externalized;

@Externalized("orders.completed")
public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {}
```

Với Kafka, thêm `spring-modulith-events-kafka`; với AMQP, thêm `spring-modulith-events-amqp` và dependency Spring AMQP phù hợp; với JMS, dùng `spring-modulith-events-jms`. `@Externalized` chọn event cần phát và chỉ định logical routing target theo broker integration.

Ý nghĩa target phụ thuộc broker: Kafka dùng target làm topic và có thể dùng routing key làm message key; AMQP dùng routing key; JMS integration không hỗ trợ routing key. Hãy cấu hình topic/exchange/queue, binding, serializer và security của broker theo hạ tầng thực tế.

### 7.2. Externalization và outbox

Native Spring Modulith event externalization được triển khai qua transactional event listener và Event Publication Registry, nhờ đó có thể theo dõi và resubmit lỗi khi tương tác broker. Tuy nhiên, tài liệu Spring Modulith nêu rõ cách native này không bao gồm mọi tính năng mà người dùng kỳ vọng ở một outbox implementation chuyên dụng.

Từ Spring Modulith 2.1, có hỗ trợ externalization qua Namastack Outbox và JobRunr. Nếu cần outbox semantics nâng cao, hãy đánh giá các integration này hoặc triển khai transactional outbox phù hợp với database và broker.

Dù dùng outbox, không nên giả định consumer chỉ nhận đúng một lần. Publisher có thể gửi lại sau timeout hoặc crash; consumer cần idempotency theo `eventId` hoặc business key.

### 7.3. Contract khi event đi ra ngoài

Event externalized là API giữa các hệ thống. Cần:

- Dùng tên event và field ổn định, có versioning khi thay đổi breaking.
- Chỉ publish dữ liệu consumer được phép biết; không gửi secret hoặc dữ liệu cá nhân không cần thiết.
- Dùng ID và snapshot cần thiết thay vì serialize entity graph.
- Có `eventId`, `occurredAt` và aggregate id để trace/correlation.
- Quy định serialization format, schema compatibility và routing target.
- Có idempotency, retry, dead-letter handling và quan sát lỗi.
- Không đổi tên class/package tùy tiện nếu routing target mặc định được suy ra từ event type.

## 8. Idempotency và thứ tự xử lý

Event listener có thể được gọi lại khi retry publication, broker redelivery hoặc ứng dụng phục hồi sau crash. Một listener tốt phải an toàn khi nhận cùng event nhiều lần.

Mẫu đơn giản là lưu `eventId` đã xử lý với unique constraint trong cùng transaction với business update:

```sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Khi nhận event, insert `eventId`. Nếu key đã tồn tại, không lặp lại side effect. Nếu insert thành công, xử lý nghiệp vụ và commit trong cùng transaction. Nếu xử lý thất bại, transaction rollback để retry có thể chạy lại.

Nếu side effect nằm ở hệ thống ngoài database, ví dụ gửi email hoặc gọi API thanh toán, cần idempotency key ở hệ thống đích hoặc lưu trạng thái/outbox để quản lý kết quả không chắc chắn.

Nhiều listener có thể chạy song song; retry cũng có thể khiến event mới hoàn tất trước event cũ. Nếu thứ tự theo aggregate là bắt buộc, cần partition theo aggregate key, serialize xử lý hoặc kiểm tra version/sequence trong domain model.

## 9. Kiểm thử event

### 9.1. Kiểm thử event đã được publish

Spring Modulith cung cấp `@ApplicationModuleTest` và `PublishedEvents` để xác minh event được phát trong một module test:

```java
@ApplicationModuleTest
class OrderModuleTests {

    @Test
    void publishesOrderCompleted(PublishedEvents events) {
        // Execute the operation that completes an order.

        assertThat(events.ofType(OrderCompleted.class))
                .hasSize(1);
    }
}
```

Đoạn test minh họa cách kiểm tra publication; cần cấu hình test module, dữ liệu và AssertJ theo dự án. Có thể lọc `PublishedEvents` theo order id để kiểm tra đúng event của thao tác đang test.

### 9.2. Kiểm thử listener và failure path

Nên có test cho:

1. `@EventListener` đồng bộ chạy khi event được publish.
2. `@TransactionalEventListener` chỉ chạy sau commit và không chạy sau rollback.
3. Event publish ngoài transaction bị bỏ qua nếu `fallbackExecution` không bật.
4. Listener async xử lý lỗi đúng executor/error handler.
5. Listener Modulith tạo publication entry và đánh dấu completed sau thành công.
6. Listener lỗi để lại publication có thể resubmit.
7. Resubmission không tạo duplicate side effect nhờ idempotency.
8. Event externalization serialize đúng payload, header và routing target.
9. Event schema cũ vẫn deserialize được nếu publication tồn tại qua nhiều lần deploy.

Đối với module integration test, Spring Modulith có Scenario API để kiểm thử việc publish và xử lý event theo luồng thay vì chỉ kiểm tra event object đã xuất hiện.

## 10. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Listener không chạy | Dùng `@TransactionalEventListener` nhưng không có transaction | Kiểm tra transaction boundary hoặc cân nhắc `fallbackExecution` |
| Listener chạy trước commit | Dùng `@EventListener` đồng bộ | Dùng `@TransactionalEventListener` với phase phù hợp |
| Request chậm bất thường | Listener đồng bộ làm nhiều I/O hoặc xử lý nặng | Tách sang async listener/module listener hoặc broker |
| Event bị mất khi process restart | Chỉ dùng `@Async`/`@TransactionalEventListener` không có publication persistence | Dùng Event Publication Registry hoặc outbox/broker |
| Listener lỗi nhưng transaction chính đã commit | Listener chạy `AFTER_COMMIT` hoặc async | Thiết kế retry, registry và idempotency |
| Ghi DB trong after-commit không được commit | Dùng transaction đã hoàn tất của publisher | Mở transaction mới bằng `REQUIRES_NEW` |
| Event bị xử lý hai lần | Retry, resubmit hoặc broker redelivery | Deduplicate theo event id/business key |
| Publication table tăng liên tục | Giữ completed entries ở mode `UPDATE` nhưng không purge | Chọn retention, cleanup hoặc completion mode khác |
| Consumer bên ngoài không hiểu payload | Event contract thay đổi không tương thích | Version schema, mapping payload và kiểm thử contract |
| Event không ra broker | Thiếu broker-specific Modulith artifact, routing target hoặc broker configuration | Kiểm tra externalization selection, serializer, topic/exchange/queue và registry |

## 11. Chọn công cụ theo nhu cầu

| Tiêu chí | ApplicationEvent | Spring Modulith | Broker (Kafka/AMQP/JMS) |
| --- | --- | --- | --- |
| Phạm vi | Một ApplicationContext | Module trong một ứng dụng Spring | Nhiều process/hệ thống |
| Cài đặt | Có sẵn trong Spring Framework | Thêm dependency Modulith | Cần broker và client integration |
| Mặc định | Đồng bộ | Module listener có thể async/transaction-bound | Bất đồng bộ qua mạng |
| Durability | Không có publication log mặc định | Event Publication Registry nếu cấu hình persistence | Phụ thuộc broker durability/ack/retention |
| Retry | Tự xây hoặc executor policy | Có API quản lý publication và resubmit | Broker/client retry, DLQ và consumer policy |
| Phù hợp | Event nội bộ đơn giản | Modular monolith cần event contract và phục hồi listener | Integration phân tán, replay và nhiều consumer độc lập |

Đừng đưa broker vào chỉ để thay thế một lời gọi method nội bộ đơn giản. Ngược lại, đừng dùng `ApplicationEvent` làm message bus xuyên process hoặc kỳ vọng nó lưu event qua restart.

## 12. Checklist triển khai

- [ ] Event mô tả điều đã xảy ra và có tên domain rõ ràng.
- [ ] Event payload bất biến, nhỏ và không chứa entity graph/lazy reference.
- [ ] Có event id, aggregate id và timestamp khi cần trace/idempotency.
- [ ] Producer chỉ phụ thuộc `ApplicationEventPublisher` hoặc contract module công khai.
- [ ] Đã quyết định listener đồng bộ, transaction-bound hay async.
- [ ] `@TransactionalEventListener` dùng đúng phase và fallback policy.
- [ ] Listener ghi DB sau commit có transaction riêng nếu cần.
- [ ] Async executor có giới hạn và error handling.
- [ ] Nếu event không được phép mất, có publication registry/outbox/broker durability.
- [ ] Listener idempotent và an toàn khi retry.
- [ ] Có cleanup/retention cho completed publication records.
- [ ] Externalized event có schema/versioning, routing và data protection.
- [ ] Có test cho commit, rollback, failure, retry và duplicate.
- [ ] Có metrics/log/trace để theo dõi publication pending, failed và completed.

## 13. Tài liệu tham khảo

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `ApplicationListener`, `@EventListener`, synchronous/asynchronous listeners.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, transaction phases và reactive transaction context.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `@ApplicationModuleListener`, Event Publication Registry, retry, externalization và testing.
- [Spring Modulith — EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html): API lưu, tra cứu và hoàn tất publication.
- [Spring Modulith — FailedEventPublications API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/FailedEventPublications.html): resubmit failed publications.

Tài liệu Spring Modulith hiện hành có các tính năng khác nhau theo nhánh version. Publication lifecycle và `FailedEventPublications` yêu cầu Modulith 2.0+; Namastack/JobRunr outbox integration được bổ sung từ 2.1. Hãy dùng BOM/dependency versions tương thích với Spring Boot và kiểm tra API của phiên bản dự án trước khi triển khai.
