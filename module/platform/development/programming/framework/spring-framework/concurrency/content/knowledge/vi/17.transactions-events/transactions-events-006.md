# @TransactionalEventListener cho xử lý gắn với kết quả giao dịch

Trong Spring Framework, một thao tác nghiệp vụ có thể **ghi dữ liệu trong transaction** và đồng thời cần phát thông báo, cập nhật cache, tạo audit record hoặc gửi một công việc sang hệ thống khác. Thời điểm xử lý sự kiện rất quan trọng: nếu consumer thực hiện việc phụ **trước khi transaction commit**, hệ thống bên ngoài có thể nhận thông báo về một bản ghi sau đó bị rollback. Nếu chỉ muốn xử lý khi giao dịch đã thành công, Spring cung cấp **`@TransactionalEventListener`**, cho phép gắn listener vào **giai đoạn của transaction** thay vì thực thi listener ngay lúc sự kiện được phát.

Mặc định, `@TransactionalEventListener` chạy với `TransactionPhase.AFTER_COMMIT`. Nó cũng hỗ trợ `BEFORE_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Sự khác biệt giữa các pha, hành vi khi không tồn tại transaction, và tương tác với `@Async` là nền tảng để xây dựng xử lý đồng thời đúng.

**Cảnh báo cốt lõi:** “chạy sau commit” **không đồng nghĩa** “chạy trong một transaction mới” và **không bảo đảm giao việc bền vững qua JVM crash**. Sau commit, một số tài nguyên transaction cũ vẫn có thể còn được gắn với thread; nếu cần ghi database từ callback, thường phải mở **transaction mới** với `REQUIRES_NEW`. Với công việc không được phép mất, dùng **transactional outbox** hoặc một thiết kế lưu job bền vững.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt `@EventListener` với `@TransactionalEventListener` và mô tả cơ chế đăng ký callback theo transaction hiện hành.
- Giải thích bốn giá trị của `TransactionPhase`, điều kiện gọi listener và giới hạn của từng pha.
- Hiểu `fallbackExecution=false` mặc định: sự kiện xuất bản **ngoài transaction** không được xử lý bởi transactional listener.
- Đặt `ApplicationEventPublisher.publishEvent(...)` ở đúng transaction/thread để listener gắn với outcome mong muốn.
- Giải thích vì sao `AFTER_COMMIT` không đồng nghĩa với một transaction mới, và khi nào cần `@Transactional(propagation = REQUIRES_NEW)`.
- Kết hợp `@TransactionalEventListener` với `@Async` một cách có chủ đích mà không giả định context giao dịch tự truyền sang worker.
- Phân biệt độ bền của một callback nội bộ trong JVM với bảo đảm giao việc qua shutdown, crash hoặc nhiều replica.
- Kiểm thử commit, rollback, no-transaction, thứ tự callback và rejection mà không dùng `Thread.sleep` để đoán.
- Nhận diện trường hợp transaction reactive trong Spring 6.1+ và nhu cầu truyền context khác với transaction dựa trên thread.
- Chọn đúng phương án cho gửi email, phát message, cập nhật audit/cache và tác vụ cần retry/idempotency.

## 2. Tình huống vấn đề: gửi thông báo quá sớm

Giả sử chức năng tạo đơn hàng:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    orderRepository.save(new Order(request));
    emailGateway.sendConfirmation(request.email());
}
~~~

Đây là **mã minh họa trong Spring service**, cần `@Transactional`, các type và dependency ứng dụng. Khi gửi email ngay bên trong method, email có thể được gửi thành công **trước khi database transaction thực sự commit**. Sau đó commit có thể thất bại hoặc một exception dẫn đến rollback: khách hàng nhận thông báo về đơn hàng không được lưu.

Thay vì gửi trực tiếp, ta có thể phát một **domain event** trong transaction:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(new Order(request));
    publisher.publishEvent(new OrderCreatedEvent(order.getId()));
}
~~~

Và xử lý khi transaction commit thành công:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommitted(OrderCreatedEvent event) {
    notifications.notifyOrderCreated(event.orderId());
}
~~~

Đây cũng là **mã minh họa**, `publisher` là `ApplicationEventPublisher`, `notifications` là service/gateway do ứng dụng cung cấp. `@TransactionalEventListener` ở đây giúp **không chạy listener nếu transaction bị rollback** trong đường xử lý chuẩn. Tuy vậy, gửi email ngay trong after-commit callback vẫn có thể lỗi; nếu JVM chết sau commit nhưng trước khi gửi, email có thể không bao giờ đi. **Không dùng after-commit callback đơn lẻ để cam kết exactly-once hoặc durable delivery.**

## 3. @EventListener và @TransactionalEventListener khác nhau thế nào?

| Tiêu chí | `@EventListener` thông thường | `@TransactionalEventListener` |
| --- | --- | --- |
| Thời điểm xử lý mặc định | Khi event được multicast tới listener, theo cấu hình multicaster (mặc định thường đồng bộ) | Khi transaction đạt pha `AFTER_COMMIT` |
| Phụ thuộc transaction hiện hành? | Không yêu cầu | Có theo mặc định |
| Nếu publisher phát trong transaction rồi rollback | Listener thường đã được gọi nếu multicaster đồng bộ | `AFTER_COMMIT` không chạy |
| Có thể chọn trước commit/sau rollback? | Không tự có ràng buộc pha giao dịch | Có `BEFORE_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION` |
| Phát event khi không có transaction | Listener thông thường vẫn có thể nhận | Mặc định **không xử lý**; `fallbackExecution=true` thay đổi điều đó |
| Có đảm bảo message/job không mất qua JVM crash? | Không | Không |
| Thread/context | Phụ thuộc multicaster và `@Async` | Đăng ký giao dịch cần đúng context; xử lý sau pha có thể đồng bộ hoặc dispatch async |

`@TransactionalEventListener` được khai báo như một event listener với thêm ràng buộc theo transaction. **Không cần chồng `@EventListener` lên cùng method** chỉ để nhận event. Việc gắn hai annotation theo cách tùy tiện có thể gây nhầm logic đọc cấu hình, còn tên method không quyết định pha.

### Hình dung luồng điển hình

~~~text
Request thread
   |
   v
Spring @Transactional proxy mở transaction
   |
   +-- INSERT order
   |
   +-- publishEvent(OrderCreated)
   |       |
   |       +-- transactional listener nhận event
   |           và đăng ký synchronization cho TX hiện tại
   |
   +-- service method trở về
   |
   +-- transaction manager quyết định commit / rollback
           |
           +-- COMMIT thành công --> AFTER_COMMIT listener
           |
           +-- ROLLBACK ---------> AFTER_ROLLBACK listener
           |
           +-- kết thúc ---------> AFTER_COMPLETION listener
~~~

**Thời điểm method `publishEvent` trả về không chứng minh listener `AFTER_COMMIT` đã chạy.** Thông thường lúc publish, listener mới được đăng ký gắn với transaction. Spring gọi listener theo pha khi transaction manager tiến hành synchronization.

## 4. Bốn pha TransactionPhase

`org.springframework.transaction.event.TransactionPhase` cung cấp bốn giá trị:

| Pha | Khi nào? | Mục tiêu thường gặp | Cần nhớ |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit transaction | Kiểm tra hoặc chuẩn bị một thao tác cần xảy ra trước commit | **Chưa chắc commit thành công**; commit có thể thất bại sau callback |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Phát tín hiệu, kích hoạt việc phụ sau khi dữ liệu đã commit | Không còn lượt commit cho transaction cũ; I/O/DB phụ cần kế hoạch riêng |
| `AFTER_ROLLBACK` | Sau khi transaction bị rollback | Ghi nhận rollback, giải phóng/cập nhật trạng thái thất bại theo nhu cầu | Ghi DB mới cần transaction độc lập |
| `AFTER_COMPLETION` | Khi transaction đã kết thúc, bất kể commit hoặc rollback | Cleanup, metric, audit về completion | Không chỉ có thành công; cần biết kết quả nếu logic phân biệt |

### 4.1 BEFORE_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreatedEvent event) {
    verifyRequiredMetadata(event.orderId());
}
~~~

Đây là **mã tích hợp**, `verifyRequiredMetadata` do ứng dụng định nghĩa. `BEFORE_COMMIT` chạy ở giai đoạn chuẩn bị commit; transaction vẫn đang trong quá trình hoàn tất. Với synchronous callback, exception runtime có thể ảnh hưởng quá trình commit và khiến giao dịch rollback theo cơ chế transaction manager. Nhưng **callback thành công không bảo đảm database commit thành công**: lỗi ràng buộc, mạng hoặc lỗi commit vẫn có thể xảy ra sau đó.

Không gửi thông báo khẳng định đơn hàng đã thành công trong `BEFORE_COMMIT`. Nếu callback gửi email trước commit và commit sau đó thất bại, vấn đề ban đầu vẫn tồn tại.

### 4.2 AFTER_COMMIT — pha mặc định

~~~java
@TransactionalEventListener
public void onCommitted(OrderCreatedEvent event) {
    queueNonCriticalNotification(event.orderId());
}
~~~

Tương đương về pha với `@TransactionalEventListener(phase=TransactionPhase.AFTER_COMMIT)`. Điều kiện cần là event được publish trong một transaction được Spring hỗ trợ và transaction đó **commit thành công**.

Mặc định listener không nhất thiết chạy trong một thread khác: transactional phase là **điều kiện về transaction**, không phải cấu hình concurrency. Nếu listener làm việc blocking trong callback đồng bộ, nó có thể kéo dài thời gian trả về của luồng đã commit transaction và thậm chí gây timeout ở request, dù transaction chính đã commit.

### 4.3 AFTER_ROLLBACK

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRolledBack(OrderCreatedEvent event) {
    recordRollbackMetric(event.orderId());
}
~~~

Đây là **mã minh họa**. `AFTER_ROLLBACK` chỉ có ý nghĩa khi transaction bị rollback. Nếu DB commit thành công, listener này không được gọi cho event đã đăng ký trong transaction đó.

Cần phân biệt rollback của transaction thực tế với việc một hàm nghiệp vụ trả mã lỗi **nhưng transaction vẫn commit**; listener không suy ra “thất bại nghiệp vụ” từ HTTP status hay giá trị return. Mốc quyết định là outcome của transaction manager.

### 4.4 AFTER_COMPLETION

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void onCompleted(OrderCreatedEvent event) {
    cleanupTemporaryState(event.orderId());
}
~~~

Callback sẽ được gọi khi giao dịch kết thúc với commit hoặc rollback theo contract của Spring. Vì nhận cùng payload `OrderCreatedEvent` mà không có status trong method signature mặc định, **không tự suy ra outcome từ việc listener chạy**. Nếu phải phân biệt commit và rollback, dùng hai listener theo pha tương ứng hoặc một transaction synchronization có thông tin trạng thái phù hợp.

## 5. Ví dụ Java 17+ độc lập mô phỏng timeline của hai kết quả

Chương trình bên dưới **không sử dụng Spring và không thực hiện transaction DB**. Nó chỉ minh họa chuỗi callback theo bốn pha để người học tự chạy được bằng JDK 17. Kết quả này không thay thế integration test `@TransactionalEventListener` trên một transaction manager thật.

Tệp **TransactionPhaseTimelineDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public final class TransactionPhaseTimelineDemo {
    enum Phase {
        BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION
    }

    static final class Timeline {
        private final Map<Phase, List<Runnable>> callbacks =
                new EnumMap<>(Phase.class);
        private boolean active = true;

        Timeline() {
            for (Phase phase : Phase.values()) {
                callbacks.put(phase, new ArrayList<>());
            }
        }

        void register(Phase phase, Runnable callback) {
            if (!active) {
                throw new IllegalStateException("Transaction already finished");
            }
            callbacks.get(phase).add(callback);
        }

        private void fire(Phase phase) {
            for (Runnable callback : callbacks.get(phase)) {
                callback.run();
            }
        }

        void complete(boolean commit) {
            if (!active) {
                throw new IllegalStateException("Already completed");
            }
            if (commit) {
                fire(Phase.BEFORE_COMMIT);
            }
            active = false;
            fire(commit ? Phase.AFTER_COMMIT : Phase.AFTER_ROLLBACK);
            fire(Phase.AFTER_COMPLETION);
        }
    }

    private static String simulate(boolean commit) {
        Timeline tx = new Timeline();
        List<String> observations = new ArrayList<>();

        tx.register(Phase.BEFORE_COMMIT,
                () -> observations.add("before"));
        tx.register(Phase.AFTER_COMMIT,
                () -> observations.add("committed"));
        tx.register(Phase.AFTER_ROLLBACK,
                () -> observations.add("rolledBack"));
        tx.register(Phase.AFTER_COMPLETION,
                () -> observations.add("completed"));

        tx.complete(commit);
        return String.join(">", observations);
    }

    public static void main(String[] args) {
        System.out.println("commit=" + simulate(true));
        System.out.println("rollback=" + simulate(false));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac TransactionPhaseTimelineDemo.java
java TransactionPhaseTimelineDemo
~~~

Stdout mong đợi:

~~~text
commit=before>committed>completed
rollback=rolledBack>completed
~~~

**Ý nghĩa:** khi mô hình chọn commit, đường `BEFORE_COMMIT` và `AFTER_COMMIT` được kích hoạt, không có `AFTER_ROLLBACK`. Khi mô hình chọn rollback, chỉ callback `AFTER_ROLLBACK` và `AFTER_COMPLETION` liên quan. `AFTER_COMPLETION` xuất hiện ở cả hai đường. Đây là mô hình **timeline khái niệm**, không phản ánh mọi nuance về exception, JTA, nested transaction, timeout hoặc thứ tự tất cả synchronization trong Spring.

## 6. Viết Spring event và publisher đúng cách

Ví dụ dưới đây là một cấu trúc Spring ứng dụng điển hình, gồm event bất biến, service phát event và bean listener theo commit. Các đoạn là **Spring classes**; cần dependency của Spring, transaction manager và repository/gateway của dự án, không thể chạy độc lập chỉ bằng `javac`.

### Event bất biến mang ID

Tệp **OrderCreatedEvent.java**:

~~~java
public record OrderCreatedEvent(String orderId) {
}
~~~

Với Java 17, `record` phù hợp để mang metadata bất biến. Event chứa **orderId**, không giữ reference đến entity JPA có lazy relation, EntityManager hoặc transaction-bound object. Vì listener chạy sau thời điểm ghi dữ liệu, dùng ID giúp tách rõ vòng đời của entity và consumer.

### Service phát event trong transaction

Tệp **OrderCommandService.java**:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderCommandService(
            OrderRepository orders,
            ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void createOrder(String orderId) {
        orders.insert(orderId);
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

`OrderRepository` ở đây là interface ứng dụng với method `insert(String)`; cần có bean repository thực sự kết nối DB. Để callback gắn với transaction, **một bean khác phải gọi `createOrder(...)` qua Spring transactional proxy** hoặc code phải có transaction đang hoạt động theo cơ chế khác. Nếu bạn tự gọi `this.createOrder(...)` từ cùng class trong proxy mode, `@Transactional` có thể bị bỏ qua, khiến `publishEvent` xảy ra **ngoài transaction**.

Để bảo đảm event phản ánh đúng dữ liệu commit, phép `orders.insert` và event publication phải nằm trong cùng transaction do manager hỗ trợ. Đừng xuất bản event trên một worker khác ngay tại đây rồi kỳ vọng worker tự thấy transaction gắn với request thread.

### Listener sau commit

Tệp **OrderNotificationListener.java**:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {
    private final OrderNotificationGateway notificationGateway;

    public OrderNotificationListener(
            OrderNotificationGateway notificationGateway) {
        this.notificationGateway = notificationGateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        notificationGateway.notifyCreated(event.orderId());
    }
}
~~~

`OrderNotificationGateway` là interface/service ứng dụng đảm nhiệm gửi thông báo. Listener này chỉ có pha commit; nếu transaction rollback nó không chạy. **Đây không phải một cơ chế retry/durable queue**: nếu gửi thông báo thất bại trong callback, dữ liệu đơn hàng đã commit vẫn tồn tại, và caller có thể gặp lỗi hoặc không tùy cơ chế gọi/logging. Phải xử lý thông báo theo hợp đồng nghiệp vụ, không cố rollback một transaction đã chốt.

## 7. Không có transaction: fallbackExecution

Thuộc tính của annotation:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = false)
public void listener(OrderCreatedEvent event) {
    // ...
}
~~~

`fallbackExecution=false` là mặc định. Nếu code thực thi `publisher.publishEvent(...)` mà **không có transaction tương thích đang hoạt động**, transactional listener thông thường **không được gọi**. Đây là hành vi có chủ đích: không thể đăng ký pha “after commit” khi không có transaction để commit.

Ví dụ ngoài transaction:

~~~java
public void publishOutsideTransaction(String id) {
    publisher.publishEvent(new OrderCreatedEvent(id));
}
~~~

Đây là **mã minh họa** trong một Spring bean có `publisher` đã inject. Nếu không có transaction và listener chỉ có `@TransactionalEventListener` mặc định, sự kiện này bị bỏ qua đối với listener đó, dù một `@EventListener` thông thường khác vẫn có thể nhận event.

### Khi bật fallbackExecution=true

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onCommitOrNoTransaction(OrderCreatedEvent event) {
    // ...
}
~~~

Nếu transaction tồn tại, listener vẫn gắn với `AFTER_COMMIT`. Nếu không có transaction, Spring cho phép **xử lý ngay theo đường fallback**, không có sự kiện commit nào để chờ. Vì thế tên `onCommitOrNoTransaction` thể hiện hợp đồng chính xác hơn so với tên `afterCommit`.

**Không dùng `fallbackExecution=true` để chữa “@Transactional bị vô hiệu” mà chưa điều tra.** Nó có thể làm listener chạy ngoài transaction và bỏ qua quy tắc “chỉ gửi khi dữ liệu đã commit”. Khi nghi ngờ code self-invocation hoặc transaction manager cấu hình sai, cần sửa nguyên nhân trước.

### Khi nào bật fallback hợp lý?

Một event mang tính thông báo có thể xuất hiện ở cả code transactional lẫn nontransactional, và việc xử lý ngay ngoài transaction được sản phẩm cho phép. Ngược lại, nếu listener gửi message về bản ghi cần tồn tại chắc chắn, thường **giữ mặc định false** và bảo đảm publish trong transaction. Việc listener không được gọi trong trường hợp no-tx nên có test và metric phù hợp, thay vì tự động bật fallback.

## 8. Sau commit: tài nguyên cũ có thể còn tồn tại

Đây là điểm rất dễ hiểu sai khi học `@TransactionalEventListener`.

Ở pha `AFTER_COMMIT`, transaction chính đã được commit. Tuy nhiên, Spring transaction synchronization có thể còn giữ connection/session hoặc resource liên kết thread cho đến khi hoàn tất dọn dẹp. Theo Javadoc Spring, nếu data access code chạy ở thời điểm này, nó **có thể trông như đang tham gia transaction cũ**, nhưng **không còn lần commit tiếp theo** cho transaction đó.

Vì thế code dạng:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreatedEvent event) {
    auditRepository.save(new AuditRecord(event.orderId()));
}
~~~

là **mã minh họa có rủi ro**. `AuditRecord`, `auditRepository` được dự án định nghĩa. Việc gọi `save` sau commit **không bảo đảm record audit mới được commit vào DB** nếu nó tham gia vào resource của transaction cũ. Đây là lý do Spring khuyến nghị dùng **`PROPAGATION_REQUIRES_NEW`** cho những thao tác transactional phát sinh ở callback sau commit/completion.

### Cách an toàn hơn: service riêng mở transaction mới

Tệp **AuditWriteService.java**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriteService {
    private final AuditRepository auditRepository;

    public AuditWriteService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeCommittedOrderAudit(String orderId) {
        auditRepository.insertCommittedOrder(orderId);
    }
}
~~~

`AuditRepository` là interface ứng dụng với `insertCommittedOrder(String)`. Listener inject service khác:

~~~java
@Component
public class OrderAuditListener {
    private final AuditWriteService auditWriteService;

    public OrderAuditListener(AuditWriteService auditWriteService) {
        this.auditWriteService = auditWriteService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        auditWriteService.writeCommittedOrderAudit(event.orderId());
    }
}
~~~

Đây là **đoạn Spring cần imports `Component`, `TransactionalEventListener` và `TransactionPhase`** như phần trước. Vì lời gọi đi qua bean `AuditWriteService` khác, `@Transactional(REQUIRES_NEW)` có cơ hội được Spring proxy intercept để mở một transaction độc lập. Nếu bạn đặt `@Transactional(REQUIRES_NEW)` trên method rồi tự gọi `this.method()` trong cùng bean, proxy mode có thể không tạo transaction mới.

**Ghi nhớ:** REQUIRES_NEW giúp có lượt commit riêng cho ghi audit, nhưng **không tự biến việc gửi thông báo thành thao tác atomic với transaction chính**. Sau khi main transaction commit nhưng trước khi audit transaction commit, tiến trình có thể crash. Nếu yêu cầu “order commit thì luôn có audit/message”, cần thiết kế **outbox** trong cùng transaction gốc thay vì chỉ thêm REQUIRES_NEW.

### Với AFTER_ROLLBACK và AFTER_COMPLETION cũng cần lưu ý

Ở `AFTER_ROLLBACK`/`AFTER_COMPLETION`, resource của transaction cũ cũng có thể còn gắn với thread. Một thao tác **ghi database mới** từ listener ở những pha này nên dùng transaction mới độc lập và test thật. Không giả định chỉ do đã rollback xong là mọi DAO call tự lập transaction mới.

## 9. BEFORE_COMMIT và exception: không nên nhầm với validation service

Có thể dùng listener `BEFORE_COMMIT` cho logic phải xảy ra trong commit sequence. Tuy nhiên callback là một phần gián tiếp của cơ chế transaction synchronization, khiến dòng lỗi và thứ tự khó đọc hơn việc gọi validation trực tiếp trước khi kết thúc service method.

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void verify(OrderCreatedEvent event) {
    if (!businessRuleIsSatisfied(event.orderId())) {
        throw new IllegalStateException("Order rule violation");
    }
}
~~~

Đây là **ví dụ minh họa**. Trong đường synchronization đồng bộ chuẩn, exception runtime tại `beforeCommit` thường có thể làm commit fail/rollback. Nhưng **không dùng nó thay cho kiểm tra bắt buộc ở nơi tạo đơn** nếu nghiệp vụ cần phản hồi rõ ràng, hoặc nếu event publication/ordering có thể thay đổi. Một `BEFORE_COMMIT` listener chạy xong vẫn không chứng minh database đã commit.

**Không gửi side effect không rollback được tại BEFORE_COMMIT**, vì event đã “chuẩn bị” không bằng event đã “được commit”.

## 10. Kết hợp @TransactionalEventListener và @Async

Một listener theo pha transaction **không mặc nhiên bất đồng bộ**. Nếu listener phải gọi network hoặc xử lý lâu và không muốn block đường completion, có thể xét sử dụng `@Async`:

~~~java
@Component
public class AsyncOrderNoticeListener {
    private final NoticeSender sender;

    public AsyncOrderNoticeListener(NoticeSender sender) {
        this.sender = sender;
    }

    @Async("notificationExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        sender.send(event.orderId());
    }
}
~~~

Đây là **Spring class minh họa**; cần imports `Component`, `Async`, `TransactionalEventListener`, `TransactionPhase`, đồng thời có bean `NoticeSender`, executor tên `notificationExecutor` và `@EnableAsync`. Khi được cấu hình đúng, Spring đăng ký listener theo transaction ở thread phát event; **đến lúc pha AFTER_COMMIT được kích hoạt**, method target có thể được dispatch qua executor bởi `@Async`.

Tác động:

- **Pha transaction** quyết định **khi nào listener đủ điều kiện chạy**.
- **Executor** quyết định **thread nào thực thi body và khi nào body thật sự hoàn tất**.
- Thread worker **không tự thừa hưởng** transaction/thread-local của publisher.
- Nếu queue bị từ chối, `TaskRejectedException` có thể xảy ra tại thời điểm dispatch; logic xử lý failure và observability phải được thiết kế.
- Nếu executor dùng `CallerRunsPolicy` khi bão hòa, body có thể chạy inline trên thread gọi mặc dù có `@Async`, nên delay của đường commit vẫn có thể tăng.
- Vì job ở queue JVM, task đã được submit vẫn có thể mất khi process chết.

### Phân biệt với ApplicationEventMulticaster có executor

Trong các phiên bản Spring mới, transactional listener có yêu cầu đăng ký transaction synchronization trong context của event publication; `TransactionalApplicationListener` không cho phép bộ multicaster tùy ý dịch chuyển chính phần đăng ký synchronization sang thread khác. Có thể làm **target listener** xử lý async theo cơ chế phù hợp (ví dụ `@Async`), nhưng đừng chỉ cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)` rồi mặc định transactional listener sẽ hoạt động/nhận đúng transaction ở worker.

Điểm kỹ thuật cần kiểm tra ở integration test là: **event đã được đăng ký với transaction nào, trên thread nào** và **body listener thực thi sau outcome nào**. Trong Spring 6.1+, `TransactionalApplicationListener.supportsAsyncExecution()` thể hiện khác biệt này: synchronization listener phải xử lý theo context nguồn, còn target listener có thể có đường thực thi bất đồng bộ riêng.

### Ví dụ cấu hình executor

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class NotificationAsyncConfig {
    @Bean(name = "notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("notice-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

Đây là **Spring configuration class**, không phải chương trình `javac` độc lập. Các thông số minh họa, phải sizing theo tải; với `AbortPolicy`, cần xử lý việc không nhận task khi pool đầy hoặc shutdown. `@EnableAsync` là điều kiện của phương thức `@Async`; chỉ thêm annotation vào một bean không được Spring quản lý không kích hoạt proxy.

## 11. Khi nào async listener làm sai kỳ vọng giao dịch?

### Đọc ThreadLocal hoặc transaction của caller

Trong Spring dùng `PlatformTransactionManager` truyền thống, transaction được liên kết với thread. Khi `@Async` chuyển body sang worker, thread worker không tự mang theo transaction context, MDC hoặc SecurityContext của publisher. Dùng `TransactionSynchronizationManager.isActualTransactionActive()` trong body async để suy ra “vẫn đang ở giao dịch gốc” là một giả định sai. Ngay cả ở callback đồng bộ sau commit, tài nguyên transaction có thể còn khả dụng trong một thời gian nhưng không còn commit mới.

**Giải pháp:** truyền ID, correlation ID và dữ liệu tối thiểu cần thiết trong payload bất biến; xác định transaction riêng trong service của listener khi cần ghi DB; dùng context propagation có chủ đích cho logging/security. Không truyền EntityManager, connection, JPA managed entity hoặc transaction status qua event.

### Chạy ngoài transaction vì publish từ worker khác

~~~java
@Async
public void publishLater(OrderCreatedEvent event) {
    publisher.publishEvent(event);
}
~~~

Đây là đoạn minh họa trong bean có `publisher`. Nếu transaction chính đang ở thread A còn `publishLater` chạy trên thread B, event thường được phát **không có transaction bound trên B**. `@TransactionalEventListener` mặc định có thể bỏ qua event ấy. Nên publish event **ở thread đang có transaction**, rồi để listener chọn giai đoạn và có thể thực thi body async **sau khi đến pha**.

### Lỗi listener sau commit không đảo ngược commit gốc

Nếu giao dịch chính đã commit, exception xảy ra trong `AFTER_COMMIT` không thể làm nó “uncommit”. Hành vi exception có lan tới caller hay chỉ bị log còn phụ thuộc giai đoạn synchronization, executor và cách Spring gọi listener. Đừng xây dựng hợp đồng “request lỗi tức transaction đã rollback” nếu có listener post-commit đang ném exception.

Nếu side effect cần nhiều lần retry, cần mã job và trạng thái rõ ràng. Nếu cần business consistency, dùng thiết kế dựa trên transaction/outbox hoặc saga/compensation, không chờ callback sau commit để cố rollback dữ liệu đã chốt.

## 12. Transaction reactive trong Spring 6.1+

Đối với transaction truyền thống quản lý bằng `PlatformTransactionManager`, Spring theo dõi state bằng thread-bound context. Với `ReactiveTransactionManager`, transaction context nằm trong **Reactor Context**, không phải ThreadLocal.

Từ Spring Framework **6.1**, `@TransactionalEventListener` có thể làm việc với cả hai mô hình, nhưng với **reactive transaction**, sự kiện phải mang context cần thiết trong **event source**; Spring giới thiệu `TransactionalEventPublisher` để hỗ trợ publication đúng cách trong reactive pipeline.

Điểm cần nhớ:

1. **Đừng** gọi `ApplicationEventPublisher.publishEvent(...)` tùy tiện trong một Reactor operator rồi mặc định thread hiện tại mang transaction reactive.
2. Xem tài liệu `TransactionalEventPublisher` của đúng phiên bản Spring và dùng đường publish gắn Reactor transaction context.
3. Không copy nguyên ví dụ servlet/JPA/`@Transactional` thread-bound sang R2DBC mà bỏ qua khác biệt context.
4. Khi xử lý async/reactive, đánh giá executor/scheduler, error propagation và backpressure riêng; transaction event không tự biến mọi side effect thành non-blocking.

Đây là phần nhận diện khác biệt, không phải hướng dẫn đầy đủ của Reactor/R2DBC. Việc bật `fallbackExecution=true` không giải quyết sai transaction context: nó chỉ cho phép listener chạy khi không tìm thấy transaction, đồng thời phá mất yêu cầu “chỉ sau commit” nếu dùng không đúng.

## 13. Nhiều transaction và lời gọi lồng nhau

### REQUIRES_NEW trong producer

Giả sử transaction ngoài A đang chạy; một service khác được gọi qua Spring proxy với `@Transactional(propagation=REQUIRES_NEW)` tạo transaction B, rồi **publish event trong B**. Event được gắn với transaction B; listener `AFTER_COMMIT` của event ấy chạy sau khi **B** commit, không đợi A commit. Sau đó A vẫn có thể rollback.

Điều này không trái với contract: listener ràng buộc theo **transaction thực tế đang hoạt động lúc publish**, không theo toàn bộ yêu cầu HTTP hoặc “transaction lớn nhất theo trực giác”. Vì thế nếu nghiệp vụ cần kết quả của transaction ngoài, event phải được publish ở đúng boundary hoặc lưu trong outbox của transaction phù hợp.

### NESTED/savepoint

Một thao tác `NESTED` có thể dùng savepoint trong cùng physical transaction (tùy manager/driver), không phải một physical commit độc lập như `REQUIRES_NEW`. Không mặc định `@TransactionalEventListener(AFTER_COMMIT)` chạy khi chỉ release một savepoint nested. Cần test kỹ điều kiện rollback-to-savepoint và sự kiện đã đăng ký: một event đã đăng ký tại synchronization của physical transaction có thể không tương ứng với outcome bạn muốn ở cấp nested step.

### Transaction rollback-only

Nếu transaction đã bị đánh dấu rollback-only, method `@Transactional` vẫn có thể chạy đến cuối và `publishEvent` vẫn đã đăng ký listener. Khi transaction manager kết thúc bằng rollback, `AFTER_COMMIT` không chạy; listener `AFTER_ROLLBACK` chạy theo phase thích hợp. Đừng suy từ “method return không ném exception ngay” sang “commit chắc chắn thành công”.

## 14. @Order, condition và lọc event

`@TransactionalEventListener` kế thừa nhiều khả năng event listener thông thường:

### Sắp xếp callback

~~~java
@Order(10)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyAfterCommit(OrderCreatedEvent event) {
    // ...
}
~~~

Đây là mã minh họa, cần import `org.springframework.core.annotation.Order`. `@Order` có thể sắp xếp mức ưu tiên giữa những listener/callback liên quan, nhưng **không** tạo một thứ tự delivery toàn cục giữa các JVM, executor, message broker hay những listener async. Không dựa vào ordering để bảo đảm tác vụ có side effect thực thi đúng một lần.

### Điều kiện bằng SpEL

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#event.orderId() != null")
public void onOrderCreated(OrderCreatedEvent event) {
    // ...
}
~~~

Đây là ví dụ Spring SpEL minh họa ý định chỉ xử lý event có ID. Tên tham số trong SpEL phụ thuộc metadata parameter name và cấu hình Spring; khi cần cấu hình portable, hãy dùng hình thức truy cập đối số được Spring hỗ trợ và test. Một lựa chọn dễ bảo trì hơn là kiểm tra dữ liệu ngay trong listener hoặc xây dựng event constructor đảm bảo non-null.

### Sự kiện cùng kiểu nhưng nhiều pha

Một event có thể được nhiều listener khác nhau đăng ký với `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Mỗi listener chạy theo pha của nó nếu transaction phù hợp. Đừng kết luận một event sẽ chỉ kích hoạt đúng một method trong toàn ứng dụng.

## 15. Kiểm thử transaction outcome đúng cách

Một test chỉ gọi service và kiểm tra log có thể bỏ sót transaction thật. Nên test trực tiếp những trường hợp:

| Kịch bản | Kỳ vọng |
| --- | --- |
| Publish trong transaction rồi commit | `AFTER_COMMIT` chạy, `AFTER_ROLLBACK` không chạy |
| Publish trong transaction rồi rollback | `AFTER_ROLLBACK` chạy, `AFTER_COMMIT` không chạy |
| Commit hoặc rollback | `AFTER_COMPLETION` chạy ở cả hai đường |
| Publish ngoài transaction, fallback mặc định | Transactional listener không xử lý |
| Publish ngoài transaction, `fallbackExecution=true` | Listener được xử lý theo fallback, không có transaction commit thực |
| Publish sau khi transaction đã kết thúc | Không gắn vào transaction cũ; cần xem no-tx/fallback |
| Listener thực hiện ghi DB sau commit | Ghi qua service `REQUIRES_NEW` tồn tại sau commit |
| Listener có `@Async` | Xác nhận body chạy sau outcome và có lối quan sát completion |
| Main transaction dùng `REQUIRES_NEW` ở nơi phát event | Callback gắn với transaction trong cùng nơi phát event |
| Transaction rollback-only | `AFTER_COMMIT` không chạy |
| Event được publish trong worker thread khác | Nếu không có transaction bound trên worker, listener mặc định bị bỏ qua |
| Executor từ chối task async | Xử lý rejection rõ ràng, không nhầm với rollback của transaction chính |

### Dùng TransactionTemplate để kiểm soát commit/rollback trong integration test

Một test có Spring context thật và `PlatformTransactionManager` phù hợp có thể điều khiển transaction rõ ràng:

~~~java
import org.springframework.transaction.support.TransactionTemplate;

// Trong một test method với variables đã inject từ Spring:
TransactionTemplate template =
        new TransactionTemplate(transactionManager);

template.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderCreatedEvent("commit-1"));
});
// TransactionTemplate hoàn tất transaction trước khi dòng sau chạy.
// Assert listener AFTER_COMMIT theo cơ chế sync.

template.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderCreatedEvent("rollback-1"));
    status.setRollbackOnly();
});
// Assert listener AFTER_ROLLBACK, không có AFTER_COMMIT.
~~~

Đây là **test fragment**, cần `transactionManager`, `publisher`, listener/recorder và assertion framework. Chỉ dùng khi hai lời gọi tạo **transaction mới thích hợp**: nếu test method đang có một transaction bên ngoài, `TransactionTemplate` với propagation mặc định có thể tham gia transaction đó, và “commit” chỉ xảy ra ở boundary ngoài. Trong Spring Test với `@Transactional` trên test method, transaction thường rollback ở cuối test; do đó **đừng để test đang được bọc bởi transaction làm sai kỳ vọng after commit**.

Tốt hơn, có thể dùng test không annotated `@Transactional`, một transaction manager thật, và các repository đã cấu hình. Nếu test cần thao tác sau commit, đợi callback completion (nếu listener async) bằng latch hoặc Future/recorder thread-safe, không dùng `Thread.sleep(500)` tùy ý.

### Dùng latch cho listener async

Trong test integration, event listener async có thể ghi nhận:

~~~java
CountDownLatch received = new CountDownLatch(1);

// Trong listener callback khi chạy thành công:
received.countDown();

// Trong test (sau lúc transaction đã commit):
assertTrue(received.await(3, TimeUnit.SECONDS));
~~~

Đây là **các fragment minh họa ở hai vị trí khác nhau**, không phải một chương trình hoàn chỉnh. Thay đổi được bảo vệ bởi `CountDownLatch` giúp xác nhận listener đã vào điểm kiểm tra, không giả định timing ngẫu nhiên của pool. Nếu cần xác minh đã **gửi email thành công**, latch phải được thả sau khi gateway/mock được gọi và trả về thành công, không phải ngay khi listener vừa bắt đầu.

## 16. Khi không được phép mất sự kiện: transactional outbox

`@TransactionalEventListener(AFTER_COMMIT)` chỉ đảm bảo **điểm gọi listener theo kết quả transaction trong tiến trình đang chạy**, không đảm bảo sự kiện được lưu bền sau khi transaction commit. Có một **khoảng trống thất bại**:

~~~text
TX chính:
  INSERT order
  COMMIT thành công
             |
             | JVM crash trước khi listener gửi / enqueue job
             v
  order đã tồn tại nhưng notification không được gửi
~~~

Tương tự, listener đã được gọi nhưng executor queue đầy, shutdown hoặc worker lỗi trước khi gửi message. `@Async` chỉ đổi thread, không giải quyết độ bền.

**Transactional outbox** xử lý bằng cách ghi dữ liệu nghiệp vụ và bản ghi outbox trong **cùng transaction**:

~~~text
BEGIN TRANSACTION
  INSERT orders (...)
  INSERT outbox (event_id, event_type, payload, status=NEW)
COMMIT
        |
        v
Outbox worker / CDC
        |
        +-- publish message / invoke downstream
        +-- retry với backoff nếu lỗi
        +-- ghi trạng thái và kiểm soát duplicate
~~~

Nếu transaction rollback, cả đơn và outbox record đều rollback. Nếu commit, outbox row tồn tại bền vững để một worker khác hoặc tiến trình phục hồi gửi sau restart.

### Ví dụ ý tưởng producer

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(new Order(request));
    outboxRepository.insert(new OutboxEvent(
            UUID.randomUUID().toString(),
            "OrderCreated",
            order.getId().toString()));
}
~~~

Đây là **mã minh họa cần class/repository của ứng dụng**, không phải Spring file runnable độc lập. Một worker độc lập quét/publish những record NEW và cập nhật trạng thái có chiến lược retry. Listener `AFTER_COMMIT` có thể dùng như **tín hiệu đánh thức worker sớm**, nhưng outbox row mới là **nguồn sự thật**; nếu tín hiệu bị mất, worker định kỳ vẫn quét record chưa gửi.

### At-least-once và idempotency

Ngay cả với outbox, vẫn có thể xảy ra tình huống publisher gửi message thành công rồi crash **trước khi đánh dấu outbox SENT**. Sau restart, message được gửi lại. Vì thế giải pháp thực tế thường là **at-least-once + idempotent consumer**, không tự hứa exactly-once end-to-end. Dùng event ID làm idempotency key, trạng thái đã xử lý ở receiver hoặc transactional inbox khi cần.

## 17. Khi nào chọn phase nào?

| Yêu cầu thực tế | Pha/giải pháp phù hợp | Vì sao |
| --- | --- | --- |
| Chỉ xử lý sự kiện khi transaction đã commit | `AFTER_COMMIT` mặc định | Bỏ qua đường rollback |
| Thực hiện bước chuẩn bị/kiểm tra trong sequence commit | `BEFORE_COMMIT` nếu phù hợp | Callback còn trước outcome commit |
| Quan sát việc rollback | `AFTER_ROLLBACK` | Chỉ chạy khi transaction bị rollback |
| Dọn state/ghi metric sau bất kỳ kết quả | `AFTER_COMPLETION` | Cả commit và rollback |
| Ghi audit DB sau khi commit | `AFTER_COMMIT` + service `REQUIRES_NEW` | Có transaction mới để commit ghi audit |
| Gửi email best-effort sau tạo đơn | `AFTER_COMMIT`, có thể `@Async` | Tránh gửi trước commit nhưng vẫn có rủi ro mất |
| Bảo đảm event không mất qua crash | Transactional outbox / durable job store | Event được lưu trong transaction chính |
| Xử lý event cả ngoài transaction | Xem xét `fallbackExecution=true` | Fallback có semantics không chờ commit |
| Reactive transaction | `TransactionalEventPublisher` theo Spring 6.1+ | Context nằm trong Reactor Context |
| Một event từ inner `REQUIRES_NEW` | Gắn listener vào transaction inner | Outcome inner khác outcome outer |
| Event không được listener nhận do no-tx | Sửa transaction/publish context trước | Tránh “chữa” bằng bật fallback sai ý nghĩa |

**Mẹo ra quyết định:** trả lời ba câu hỏi riêng: (1) Sự kiện **có cần chờ commit thành công?** (2) Listener **cần thread/transaction riêng không?** (3) Tác vụ **có bắt buộc hoàn thành qua crash/restart không?** `@TransactionalEventListener` chủ yếu trả lời câu thứ nhất; `@Async`/`REQUIRES_NEW` liên quan câu thứ hai; outbox/queue bền vững giải quyết câu thứ ba.

## 18. Các lỗi thường gặp

1. **Dùng `@EventListener` cho việc chỉ được gửi sau commit** rồi giả định listener tự đợi transaction kết thúc.
2. **Nhầm `AFTER_COMMIT` với “có transaction mới”.** Tài nguyên cũ có thể còn gắn thread nhưng không còn commit tiếp.
3. **Ghi DB trực tiếp trong `AFTER_COMMIT`** mà không có `REQUIRES_NEW` và tưởng thay đổi chắc chắn được commit.
4. **Đưa cả entity JPA vào event** rồi gọi lazy relation sau commit; tài nguyên và trạng thái entity có thể không còn như kỳ vọng.
5. **Publish event ngoài transaction** rồi nghĩ transactional listener mặc định luôn nhận.
6. **Bật `fallbackExecution=true` để tránh event bị bỏ** mà không xem hậu quả chạy trước/không có commit.
7. **Self-invocation bỏ qua `@Transactional` proxy**, khiến publisher không có transaction thực sự.
8. **Publish event từ `@Async` worker** rồi nghĩ worker kế thừa transaction thread của request.
9. **Gắn `@Async` lên listener và nghĩ nó tự tạo hàng đợi durable.** Executor queue trong RAM không chịu được crash.
10. **Dùng `SimpleApplicationEventMulticaster.setTaskExecutor` tùy tiện** và chuyển việc đăng ký synchronization ra khỏi thread transaction.
11. **Coi `BEFORE_COMMIT` như bằng chứng commit đã thành công.** Có thể commit lỗi hoặc rollback sau callback.
12. **Coi `AFTER_COMPLETION` luôn đồng nghĩa commit.** Nó cũng dùng cho rollback.
13. **Dùng `AFTER_ROLLBACK` nhưng listener lại mở default transaction gắn resource cũ**, khiến audit ghi không được commit.
14. **Giả định exception của after-commit listener có thể rollback transaction chính.** Outcome đã được chốt.
15. **Không có đường ghi nhận lỗi listener**, khiến notification thất bại nhưng trạng thái nghiệp vụ vẫn success mà không có reconciliation.
16. **Dùng `@Order` để đảm bảo thứ tự tuyệt đối giữa nhiều thread/JVM.** Annotation chỉ giúp ordering trong phạm vi Spring callback liên quan.
17. **Cho rằng event từ transaction inner `REQUIRES_NEW` chờ transaction outer.** Event gắn transaction thực tại thời điểm publish.
18. **Bỏ qua reactive transaction context**, dù R2DBC không dựa trên ThreadLocal như JDBC transaction manager.
19. **Dùng `@Transactional` trên test method rồi assert AFTER_COMMIT trước lúc test transaction kết thúc**; test thường rollback theo mặc định.
20. **Dùng `Thread.sleep` trong test để đoán listener async đã chạy.** Dùng latch/recorder và deadline.
21. **Cho rằng outbox loại bỏ mọi duplicate.** Producer có thể gửi lặp nếu crash sau publish trước khi ack; consumer phải idempotent.
22. **Gửi email ngay trong `BEFORE_COMMIT`** dù email không thể rollback theo DB transaction.
23. **Không đo latency callback đồng bộ**, khiến request chậm dù dữ liệu đã commit.
24. **Đọc `TransactionSynchronizationManager` ở after-completion rồi kết luận chắc chắn đang có transaction còn commit được.** Bound resource không đồng nghĩa một commit tương lai.
25. **Dùng event publisher như message broker liên JVM.** `ApplicationEventPublisher` mặc định chỉ phát event trong Spring ApplicationContext/JVM, không có durable replication.

## 19. Câu hỏi tự kiểm tra

1. `@TransactionalEventListener` mặc định dùng pha nào? Có cần khai báo `phase` mới chờ commit không?
2. Khác biệt lớn nhất giữa `@EventListener` và `@TransactionalEventListener` khi transaction rollback là gì?
3. Nếu một event được publish mà không có transaction, listener mặc định có xử lý không? `fallbackExecution=true` thay đổi điều gì?
4. Listener `BEFORE_COMMIT` chạy thành công có bảo đảm DB commit thành công không?
5. Vì sao `AFTER_COMPLETION` không thể tự suy ra transaction commit?
6. Gọi `auditRepository.save(...)` trong `AFTER_COMMIT` mà không mở transaction mới có nguy cơ gì?
7. Vì sao nên gọi một **bean khác** có `@Transactional(REQUIRES_NEW)` để ghi audit?
8. Nếu một worker `@Async` publish event trong khi transaction JDBC gốc nằm trên request thread, listener gắn với transaction nào?
9. `@Async` trên transactional listener có nghĩa transaction outcome được chờ ở thread nào và body được gửi tới thread nào?
10. Nếu transaction chính đã commit nhưng async listener lỗi, có thể rollback commit cũ không?
11. Nếu inner method được gọi qua `REQUIRES_NEW` publish event rồi commit, outer transaction sau đó rollback, listener của event inner sẽ làm gì?
12. Trong Spring 6.1+, reactive transaction sử dụng context gì và tại sao cần `TransactionalEventPublisher`?
13. Vì sao `@TransactionalEventListener` không thay thế transactional outbox khi message không được phép mất?
14. Nếu outbox worker crash sau khi gửi message nhưng trước lúc đánh dấu đã gửi, hệ thống phải xử lý duplicate thế nào?
15. Tại sao không nên để `@Transactional` trên test method rồi mong assertion after-commit chạy ngay?
16. Làm sao test việc listener không chạy trên rollback mà không dùng chờ thời gian tùy ý?
17. Phân biệt trạng thái “transaction đã commit” và “notification đã gửi thành công” bằng những nguồn dữ liệu nào?
18. Trong tình huống publisher chạy ngoài transaction một cách hợp lệ, tiêu chí nào cho phép bật `fallbackExecution` mà không phá nghiệp vụ?

## 20. Tài liệu tham khảo chính thức

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — TransactionalApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — TransactionalEventPublisher (Reactive)](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)

**Ghi nhớ:** `@TransactionalEventListener` ràng buộc **thời điểm gọi listener với kết quả transaction**: mặc định `AFTER_COMMIT`, ngoài ra có `BEFORE_COMMIT`, `AFTER_ROLLBACK`, `AFTER_COMPLETION`. Nó không tự tạo transaction mới hoặc hàng đợi bền vững. Khi cần ghi DB sau commit, hãy chủ động mở **`REQUIRES_NEW`**; khi sự kiện không được phép mất, ghi **outbox cùng transaction gốc**; khi kết hợp `@Async`, kiểm tra thread/context, lỗi submit và lifecycle của executor.