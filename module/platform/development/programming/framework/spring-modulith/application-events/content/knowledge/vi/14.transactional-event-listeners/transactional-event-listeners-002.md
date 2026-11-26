# Pha BEFORE_COMMIT

## 1. BEFORE_COMMIT là gì và tại sao cần hiểu đúng?

Trong ứng dụng **Spring Modulith**, một module có thể phát application event để thông báo cho module khác về một thay đổi nghiệp vụ. Ví dụ, `orders` xác nhận đơn hàng và phát `OrderConfirmed`; `notifications` gửi email, `reporting` cập nhật báo cáo, còn `audit` lưu dấu nghiệp vụ.

Nhưng **thời điểm xử lý event** quyết định tính đúng đắn của dữ liệu. Một event được phát **trong** transaction không có nghĩa transaction đó đã commit. Spring Framework cung cấp `@TransactionalEventListener` để listener gắn với một **pha của vòng đời transaction**. Trong số đó, `TransactionPhase.BEFORE_COMMIT` cho biết: **thực thi callback ngay trước khi transaction nguồn được commit, khi quá trình commit đang diễn ra**.

Đây là khác biệt quan trọng so với xử lý sau commit:

- Ở `BEFORE_COMMIT`, transaction nguồn **chưa hoàn tất**. Nếu listener ghi dữ liệu bằng cùng transaction manager và cùng tài nguyên giao dịch, phần ghi đó có thể được commit/rollback **cùng** thay đổi của publisher.
- Ở `AFTER_COMMIT`, transaction nguồn **đã commit**. Lỗi của listener không thể làm rollback kết quả nguồn vừa commit.
- `BEFORE_COMMIT` không phải async theo mặc định. Listener có thể kéo dài thời gian chờ commit, giữ lock và làm tăng độ trễ phản hồi.

Trong mô-đun học **SPRING_MODULITH_APPLICATION_EVENTS**, hiểu pha `BEFORE_COMMIT` giúp lựa chọn đúng giữa hành động cần tính nguyên tử, công việc phụ nên thực hiện sau commit, Event Publication Registry, retry và thiết kế ranh giới module. Bài này tập trung vào **pha BEFORE_COMMIT**, không đồng nhất nó với `@ApplicationModuleListener` vốn được thiết kế cho phản ứng sau commit.

## 2. Thứ tự thực thi: publish trước, callback BEFORE_COMMIT sau

Giả sử application service của `orders` chạy trong transaction `T1`:

~~~mermaid
sequenceDiagram
    participant API as Client
    participant O as orders service
    participant S as Spring Events
    participant A as audit listener
    participant DB as Database
    API->>O: confirmOrder()
    Note over O,DB: Transaction T1 bắt đầu
    O->>DB: Thay đổi trạng thái đơn trong T1
    O->>S: publishEvent(OrderConfirmed)
    S-->>O: Đăng ký callback BEFORE_COMMIT
    Note over O,S: Chưa chạy audit listener tại thời điểm publish
    O-->>S: Phương thức nghiệp vụ kết thúc
    S->>A: BEFORE_COMMIT trong T1
    A->>DB: Ghi audit bằng cùng T1
    A-->>S: Thành công
    S->>DB: Commit T1
    DB-->>API: Ghi nhận đơn và audit đã commit
~~~

Sơ đồ minh họa **đường thành công** với một transaction imperative do Spring quản lý; vị trí flush SQL thực tế phụ thuộc JPA/JDBC và transaction manager. Đừng hiểu rằng lần gọi `publishEvent(...)` tự bắt đầu commit. Spring đăng ký việc xử lý theo pha, còn transaction manager kích hoạt callback khi **thực sự bắt đầu commit**.

Một cách diễn giải ngắn:

1. Phương thức `@Transactional` bắt đầu transaction, thay đổi dữ liệu và publish event.
2. Spring nhận event và nhận diện listener đăng ký ở pha `BEFORE_COMMIT`.
3. Khi transaction manager đi vào quy trình commit, listener được gọi **trước** thao tác commit cuối cùng.
4. Listener thành công **không bảo đảm** transaction chắc chắn commit: bước flush, database constraint hoặc chính commit vẫn có thể thất bại sau đó.
5. Nếu transaction nguồn rollback **trước khi đi vào pha commit**, callback `BEFORE_COMMIT` sẽ không chạy.

**Điểm dễ nhầm:** `BEFORE_COMMIT` là *trước khi commit*, không phải *ngay khi publish*. Cũng không có nghĩa “mọi câu SQL đã flush ra database”. Ngay trong cùng một transaction, thời điểm flush và khả năng quan sát thay đổi còn phụ thuộc persistence provider và isolation.

## 3. So sánh bốn pha TransactionPhase

Spring Framework định nghĩa những pha thông dụng của `@TransactionalEventListener`:

| Pha | Khi nào callback được xử lý? | Nên cân nhắc dùng cho |
| --- | --- | --- |
| `BEFORE_COMMIT` | Khi transaction bắt đầu quá trình commit, **trước** commit cuối cùng | Bước ghi/kiểm tra cần cùng transaction nguồn và có thể làm commit thất bại |
| `AFTER_COMMIT` | Sau khi transaction nguồn commit thành công; **mặc định** nếu không chỉ rõ `phase` | Tác vụ phụ chỉ có ý nghĩa khi nghiệp vụ đã hoàn tất |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Quan sát/cleanup không đòi ghi vào chính transaction đã rollback |
| `AFTER_COMPLETION` | Khi transaction kết thúc, bất kể commit hay rollback | Theo dõi vòng đời, thu dọn ngữ cảnh |

Ví dụ cách khai báo:

~~~java
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void beforeCommit(OrderConfirmed event) {
    // Được gọi trong quá trình commit, trước commit cuối cùng.
}
~~~

Không được nhầm pha với **cách chạy thread**:

- `@EventListener` thông thường được gọi ngay tại `publishEvent(...)` (mặc định đồng bộ), **không chờ pha transaction**.
- `@TransactionalEventListener(BEFORE_COMMIT)` được gắn với transaction và **không tự trở thành bất đồng bộ**.
- `@TransactionalEventListener(AFTER_COMMIT)` cũng **không tự trở thành bất đồng bộ**; callback có thể vẫn chạy trên thread kết thúc transaction.
- Spring Modulith `@ApplicationModuleListener` kết hợp xử lý **sau commit**, **bất đồng bộ** và transaction riêng (`REQUIRES_NEW`). Nó không tương đương `BEFORE_COMMIT`.

Quyết định pha cần dựa trên **yêu cầu nhất quán nghiệp vụ**, không phải chỉ vì muốn dùng một annotation.

## 4. Ví dụ: ghi dấu audit bắt buộc cùng transaction xác nhận đơn

Giả sử quy tắc nội bộ yêu cầu: **không được commit một đơn đã xác nhận nếu chưa ghi được bản ghi audit tương ứng trong cùng database transaction**. Trách nhiệm ghi audit thuộc module `audit`; còn `orders` chỉ sở hữu đơn hàng.

Một cấu trúc Spring Modulith theo quy ước package:

~~~text
com.example.shop/
├── ShopApplication.java
├── orders/
│   ├── OrderConfirmed.java               # API event công khai
│   └── internal/
│       ├── OrderService.java
│       ├── OrderEntity.java
│       └── OrderRepository.java
├── audit/
│   └── internal/
│       ├── OrderConfirmationAuditListener.java
│       └── AuditWriter.java              # Chỉ sở hữu dữ liệu audit
└── notifications/
    └── internal/
        └── ConfirmationNotificationListener.java
~~~

### 4.1. Event công khai của orders

~~~java
// com/example/shop/orders/OrderConfirmed.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID correlationId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderConfirmed {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(correlationId, "correlationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

`eventId` dùng nhận diện event logic; `correlationId` giúp truy vết toàn bộ quy trình; `orderId` là khóa nghiệp vụ. Không truyền `OrderEntity` có thể còn gắn với persistence context sang module nhận. Mỗi `public` type trong ví dụ thuộc file Java riêng.

### 4.2. Publisher cập nhật dữ liệu và phát event trong transaction

~~~java
// com/example/shop/orders/internal/OrderService.java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher publisher,
                        Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId, UUID correlationId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();

        if (order.isConfirmed()) {
            return; // Không phát event khi trạng thái không thay đổi.
        }

        order.confirm(); // Áp dụng các quy tắc nghiệp vụ của orders.

        publisher.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                correlationId,
                order.getId(),
                Instant.now(clock)));
    }
}
~~~

`OrderEntity`, `OrderRepository` và bean `Clock` là thành phần minh họa cần được cài đặt/cấu hình trong ứng dụng. Đối với hai request xác nhận đồng thời, việc kiểm tra `isConfirmed()` chưa đủ: cần version/optimistic locking hoặc cơ chế tương đương.

**Sự kiện được publish trước commit**, nên trong pha `BEFORE_COMMIT` nó là thông tin về thay đổi **đang chuẩn bị commit**, chưa phải sự thật đã được xác nhận bền vững. Những consumer cần bảo đảm dữ liệu đã tồn tại nên chờ `AFTER_COMMIT`.

### 4.3. Listener BEFORE_COMMIT ghi vào dữ liệu do audit sở hữu

~~~java
// com/example/shop/audit/internal/OrderConfirmationAuditListener.java
package com.example.shop.audit.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class OrderConfirmationAuditListener {
    private final AuditWriter audit;

    OrderConfirmationAuditListener(AuditWriter audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    void on(OrderConfirmed event) {
        audit.insertConfirmation(
                event.eventId(), event.orderId(),
                event.correlationId(), event.occurredAt());
    }
}
~~~

Trong ví dụ này, `AuditWriter` và `OrderService` sử dụng **cùng transaction manager và database connection tham gia transaction nguồn**. `AuditWriter` không được chạy trong transaction tách biệt nếu yêu cầu là ghi audit và xác nhận đơn **nguyên tử**.

Ví dụ implementation JDBC theo giả định **PostgreSQL**, dùng `JdbcTemplate` được cấu hình với cùng `DataSource` do transaction manager quản lý:

~~~java
// com/example/shop/audit/internal/AuditWriter.java
package com.example.shop.audit.internal;

import java.time.Instant;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
class AuditWriter {
    private final JdbcTemplate jdbc;

    AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    void insertConfirmation(UUID eventId, UUID orderId,
                            UUID correlationId, Instant occurredAt) {
        jdbc.update("""
                INSERT INTO audit.order_confirmation_log
                    (event_id, order_id, correlation_id, occurred_at)
                VALUES (?, ?, ?, ?)
                """, eventId, orderId, correlationId, occurredAt);
    }
}
~~~

Một ví dụ bảng audit với khóa duy nhất:

~~~sql
-- PostgreSQL; schema audit giả định đã được tạo.
CREATE TABLE audit.order_confirmation_log (
    event_id       UUID PRIMARY KEY,
    order_id       UUID NOT NULL,
    correlation_id UUID NOT NULL,
    occurred_at    TIMESTAMPTZ NOT NULL
);
~~~

Trong trường hợp bình thường, khi listener thành công, bản ghi audit và thay đổi trạng thái đơn được commit **trong cùng T1**. Nếu câu SQL audit ném exception chưa được xử lý, transaction manager có thể rollback cả hai. Nếu database từ chối commit sau khi listener đã ghi audit trong transaction, cả những thay đổi thuộc T1 cũng rollback.

**Điều kiện nguyên tử là cùng tài nguyên giao dịch và transaction manager phù hợp**, không chỉ việc hai bean chạy trong một JVM. Nếu audit ghi vào database khác, dùng transaction manager khác hoặc gọi dịch vụ HTTP, `BEFORE_COMMIT` **không cung cấp atomicity phân tán**.

## 5. Ba tình huống: commit thành công, rollback trước commit, lỗi ở BEFORE_COMMIT

### 5.1. Đường thành công

~~~text
T1 BEGIN
  orders: cập nhật trạng thái CONFIRMED
  orders: publish OrderConfirmed(E1)
  Spring: đăng ký listener BEFORE_COMMIT(E1)
T1 BEFORE_COMMIT
  audit: INSERT audit_log(E1) trong T1
T1 COMMIT
  orders và audit cùng được commit
~~~

`@TransactionalEventListener(BEFORE_COMMIT)` không chạy ngay lúc publish; nó chờ transaction đi vào quá trình commit. Nếu publish nhiều event trong cùng transaction, mỗi publication phù hợp có thể đăng ký một callback tương ứng; **không mặc nhiên chỉ gọi listener một lần cho toàn transaction**.

### 5.2. Rollback trước khi tới pha BEFORE_COMMIT

~~~text
T1 BEGIN
  orders: cập nhật trạng thái
  orders: publish OrderConfirmed(E1)
  service: ném exception khiến T1 rollback
T1 ROLLBACK
  BEFORE_COMMIT không được thực thi
~~~

Đây là khác biệt với `@EventListener` đồng bộ: listener thường có thể đã chạy ngay tại `publishEvent(...)`, trước khi nguồn rollback. Đó là lý do không gửi email hoặc gọi cổng thanh toán trong một listener đồng bộ dựa trên sự thật chưa commit.

### 5.3. Listener BEFORE_COMMIT ném exception

~~~mermaid
flowchart TB
    P["publish OrderConfirmed"] --> BC["BEFORE_COMMIT callback"]
    BC --> A{"Audit write thành công?"}
    A -->|"Không; exception được lan ra"| RB["Transaction manager rollback T1"]
    A -->|"Có"| COM["Tiếp tục quá trình commit T1"]
    COM --> OK{"Commit DB thành công?"}
    OK -->|"Có"| DONE["Orders + audit đã commit"]
    OK -->|"Không"| FAIL["Không thể coi event đã commit"]
~~~

Với transaction manager thông thường của Spring, exception runtime từ callback `beforeCommit` được truyền lên quá trình commit, từ đó có thể khiến transaction rollback. **Không nuốt exception rồi trả về thành công** nếu audit là điều kiện bắt buộc. Đối với lỗi commit phát sinh sau callback, xử lý trả lỗi và đối soát theo kết quả thực tế của transaction.

Không nên đưa một tác vụ không đáng để rollback toàn bộ đơn hàng vào `BEFORE_COMMIT`. Ví dụ, nếu dịch vụ email đang tạm lỗi mà đơn vẫn phải được chấp nhận, email không phải điều kiện commit và nên được chuyển sang listener **sau commit**.

## 6. Giới hạn quan trọng: BEFORE_COMMIT không bảo đảm dữ liệu đã flush

Trong JPA/Hibernate, `repository.save(...)` hay việc thay đổi managed entity có thể mới được ghi trong persistence context; SQL thực tế có thể được flush khi query, khi commit hoặc theo cấu hình.

Vì vậy:

- Listener `BEFORE_COMMIT` có thể thấy thay đổi của entity trong **cùng persistence context** nhưng không nên giả định mọi truy vấn SQL bằng đường kết nối khác sẽ thấy được các thay đổi ấy.
- SQL thực thi trong **cùng transaction** vẫn chịu quy tắc isolation và flush của persistence provider.
- Nếu listener yêu cầu dữ liệu đã được flush để chạy SQL đọc phụ thuộc, cần thiết kế rõ điểm flush; **không coi tên pha `BEFORE_COMMIT` đồng nghĩa “sau flush”**.
- Việc cố flush sớm chỉ để phục vụ listener làm tăng coupling về persistence. Có thể tốt hơn khi truyền đủ dữ liệu cần thiết qua event hoặc dùng API đồng bộ có chủ đích.

Một rủi ro nữa là lỗi ràng buộc database chỉ xuất hiện tại **flush/commit**, sau khi listener tưởng đã hoàn thành. Vì vậy **log “before commit listener success” không phải bằng chứng commit thành công**.

## 7. BEFORE_COMMIT có nên dùng để kiểm tra bất biến nghiệp vụ?

Về mặt kỹ thuật, listener `BEFORE_COMMIT` có thể ném lỗi và ngăn transaction hoàn tất. Điều này làm nó hấp dẫn cho việc **validate**. Nhưng với một bất biến cốt lõi, dùng event listener có thể gây **điều phối ẩn**:

~~~java
// Anti-pattern khi đây là điều kiện bắt buộc để tạo đơn.
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
void validateStock(OrderConfirmed event) {
    if (!inventoryApi.hasEnoughStock(event.orderId())) {
        throw new IllegalStateException("Not enough stock");
    }
}
~~~

Trong trường hợp này, `orders` chỉ biết `publishEvent`, nhưng kết quả **xác nhận đơn** lại ngầm phụ thuộc một listener. Người đọc `OrderService.confirm(...)` không thấy điều kiện tồn kho, khó hiểu vì sao transaction đôi khi rollback. Hơn nữa, việc đọc trạng thái tồn kho rồi commit đơn không nhất thiết bảo vệ được race condition và tính nhất quán xuyên module.

Nếu `inventory` phải xác nhận khả năng giữ hàng **trước** khi đơn được chấp nhận, hãy dùng API đồng bộ với kết quả rõ ràng hoặc mô hình workflow có trạng thái (`PENDING_STOCK`, `STOCK_RESERVED`, `CONFIRMED`). Đừng giấu quyết định nghiệp vụ quan trọng sau `BEFORE_COMMIT` chỉ để tránh lời gọi API hiển thị.

Ngược lại, khi quy tắc thật sự là **“phải ghi audit cùng commit của orders”**, listener cùng transaction có thể là một lựa chọn có chủ đích. Đây là **coupling về transaction** mà đội phát triển phải chấp nhận và kiểm thử; không thể vừa yêu cầu nguyên tử giữa hai module vừa hứa chúng hoàn toàn độc lập về khả năng lỗi.

**Nguyên tắc:** quyết định nghiệp vụ cần phản hồi rõ ràng nên được thể hiện trong application service/domain service hoặc process manager. `BEFORE_COMMIT` chỉ phù hợp với trách nhiệm phải tham gia commit và được chủ động công bố trong kiến trúc.

## 8. Dùng cùng event cho audit BEFORE_COMMIT và notification AFTER_COMMIT

Một event có thể có nhiều listener, mỗi listener đăng ký pha phù hợp với vai trò của nó.

~~~mermaid
flowchart TB
    O["orders xác nhận đơn, publish OrderConfirmed"]
    O --> BC["audit listener BEFORE_COMMIT"]
    BC -->|"audit thành công"| C{"Transaction nguồn commit?"}
    BC -->|"audit lỗi"| R["Rollback nguồn"]
    C -->|"Có"| AC["notifications listener AFTER_COMMIT"]
    C -->|"Không"| R
    AC --> E["Gửi email idempotent"]
~~~

Listener gửi thông báo của `notifications` nên xử lý **sau khi nguồn đã commit**:

~~~java
// com/example/shop/notifications/internal/ConfirmationNotificationListener.java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ConfirmationNotificationListener {
    private final NotificationService notifications;

    ConfirmationNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.sendConfirmationOnce(
                event.orderId(), event.eventId());
    }
}
~~~

`@ApplicationModuleListener` của Spring Modulith sử dụng mô hình listener **AFTER_COMMIT**, **async** và transaction mới (`REQUIRES_NEW`). Cần cấu hình transaction, async executor và các dependency tương ứng. `NotificationService` là abstraction minh họa; ứng dụng phải hiện thực cơ chế chống gửi trùng và quản lý lỗi.

Nếu audit `BEFORE_COMMIT` thất bại khiến T1 rollback, listener `AFTER_COMMIT` **không nên được gọi** như thể đơn đã xác nhận thành công. Nếu T1 đã commit nhưng email thất bại, **không rollback lại** được đơn; cần xử lý lỗi email độc lập.

Một thiết kế như vậy có hai chính sách khác nhau:

| Tác động | Tính chất nghiệp vụ | Pha phù hợp |
| --- | --- | --- |
| Bản ghi audit bắt buộc phải cùng commit | Mất audit thì không được xác nhận đơn | `BEFORE_COMMIT`, cùng T1 |
| Email xác nhận | Chỉ gửi khi đơn thật sự đã commit; có thể xử lý muộn | `AFTER_COMMIT` / `@ApplicationModuleListener` |
| Projection báo cáo | Dữ liệu đọc có thể nhất quán sau | `AFTER_COMMIT` với retry/idempotency |
| Quyết định còn hàng trước khi xác nhận | Điều kiện bắt buộc cần kết quả rõ ràng | API đồng bộ/điều phối tường minh, không giấu vào listener |

## 9. BEFORE_COMMIT tác động đến độ trễ và lock như thế nào?

Listener `BEFORE_COMMIT` nằm trên **đường commit của transaction nguồn**. Vì vậy thời gian xử lý của nó có thể làm tăng:

- Thời gian HTTP request phải chờ `@Transactional` kết thúc.
- Thời gian transaction giữ connection/lock.
- Mức tranh chấp database khi nhiều transaction đồng thời.
- Số request bị timeout hoặc tỷ lệ thất bại nếu audit listener gọi dịch vụ chậm.

Một ví dụ **định lượng giả định**:

| Bước | Thời gian |
| --- | ---: |
| Kiểm tra và cập nhật đơn | 35 ms |
| Listener BEFORE_COMMIT ghi audit | 20 ms |
| Commit và phần overhead khác | 15 ms |
| **Response xấp xỉ** | **70 ms** |

Nếu listener audit chuyển sang gọi HTTP bên ngoài mất 800 ms, response có thể bị kéo dài đáng kể và transaction giữ tài nguyên lâu hơn. Đây là lý do không nên dùng pha `BEFORE_COMMIT` cho email, webhook hoặc API mạng ngoài mà không có lý do nhất quán đặc biệt và cơ chế chống lỗi.

Đổi sang `@ApplicationModuleListener` sau commit có thể giảm đường chờ của request, nhưng cũng **thay đổi tính nguyên tử của nghiệp vụ**: nếu audit không còn phải được commit cùng nguồn, nó có thể thất bại tạm thời dù đơn đã xác nhận. Đây là **đánh đổi nghiệp vụ**, không chỉ tối ưu performance.

## 10. Event Publication Registry có thay BEFORE_COMMIT không?

**Không.** Spring Modulith Event Publication Registry giúp theo dõi publication của application event tới các transactional listeners, phát hiện publication chưa hoàn tất và hỗ trợ phục hồi theo implementation/cấu hình. Khi sử dụng backend lưu trữ bền vững phù hợp (ví dụ JDBC/JPA), registry có thể phối hợp với transaction nguồn để ghi publication.

Tuy nhiên:

1. Registry **không biến tác động ở BEFORE_COMMIT thành tác động đã commit**; kết quả cuối cùng vẫn do transaction manager quyết định.
2. Registry không thay cho quy tắc audit đồng transaction. Nếu yêu cầu audit nguyên tử, phải kiểm chứng audit cùng transaction/tài nguyên và thất bại của audit làm transaction rollback.
3. Registry không tự làm listener `BEFORE_COMMIT` chạy bất đồng bộ hay có transaction riêng.
4. Cơ chế đăng ký/đánh dấu completion cho các loại listener khác nhau cần được xác minh với phiên bản Spring Modulith và backend đang dùng; **không mặc định mọi listener BEFORE_COMMIT đều có chính sách recovery giống listener AFTER_COMMIT**.
5. Resubmit một publication sau commit có thể không còn ngữ cảnh transaction nguồn ban đầu. **Không được dùng nó để “thực hiện lại BEFORE_COMMIT” và kỳ vọng thay đổi vẫn thuộc T1 đã kết thúc.**

Phân biệt hai câu hỏi:

- **BEFORE_COMMIT:** có được commit transaction nguồn khi phần việc bắt buộc chưa hoàn tất không?
- **Registry + AFTER_COMMIT:** một tác vụ phụ sau commit đã xử lý thành công chưa; nếu chưa, có thể phục hồi việc giao event thế nào?

Với các tác động phụ có thể chạy sau commit, lựa chọn thông thường là `@ApplicationModuleListener` cộng registry bền vững, retry có kiểm soát và listener idempotent. Không dùng `BEFORE_COMMIT` như cách thay thế một hệ thống giao message đáng tin cậy.

## 11. Các tình huống transaction dễ bị bỏ sót

### 11.1. Publish ngoài transaction

~~~java
// Không có @Transactional, và giả sử không có outer transaction.
void confirmWithoutTransaction(OrderConfirmed event) {
    publisher.publishEvent(event);
}
~~~

`@TransactionalEventListener` mặc định **không được thực thi** nếu không có transaction đang hoạt động. Có thể đặt `fallbackExecution = true` để gọi listener ngay cả ngoài transaction, nhưng với logic **bắt buộc phải chạy trước commit**, tùy chọn đó phá vỡ ý nghĩa: chẳng có commit nào để chờ.

**Khuyến nghị:** giữ `fallbackExecution = false` (mặc định) cho các listener BEFORE_COMMIT yêu cầu nguyên tử, bảo đảm publisher được gọi trong transaction do Spring quản lý, và kiểm thử điều đó.

### 11.2. Self-invocation làm mất transaction proxy

Trong mô hình proxy mặc định, phương thức trong cùng bean gọi trực tiếp một phương thức khác có `@Transactional` có thể **không đi qua proxy**, nên transaction bạn mong đợi không được kích hoạt. Khi đó event được publish ngoài transaction và listener không chạy.

Hãy gọi qua một Spring bean/proxy phù hợp hoặc thiết kế transaction boundary ở application service rõ ràng. Đừng sửa bằng cách bật `fallbackExecution` chỉ để listener “có vẻ chạy”.

### 11.3. `REQUIRES_NEW` có transaction độc lập

Nếu publisher phát event bên trong một phương thức `@Transactional(propagation = REQUIRES_NEW)`, callback `BEFORE_COMMIT` gắn với **transaction mới ấy**, không phải mặc nhiên gắn với transaction bên ngoài đang bị tạm dừng.

Kết quả: transaction trong `REQUIRES_NEW` có thể đã commit, rồi transaction ngoài rollback. Đừng giả định hai transaction lồng nhau luôn cùng một số phận. Thiết kế sự kiện cần xác định rõ **transaction nào là nguồn của sự thật nghiệp vụ**.

### 11.4. Async và context transaction

Với quản lý transaction imperative, ngữ cảnh transaction thường gắn với thread. Đưa phần việc `BEFORE_COMMIT` sang executor/thread mới có thể khiến phần việc đó **không tham gia T1**.

Không gắn `@Async` lên listener trước commit với kỳ vọng vừa trả response nhanh, vừa ghi chung transaction; hai mục tiêu này mâu thuẫn về thời điểm và ngữ cảnh. Với reactive transaction, việc chuyển ngữ cảnh đòi hỏi cơ chế khác (ví dụ `TransactionalEventPublisher` của Spring Framework trong những phiên bản hỗ trợ), không nên suy từ hành vi thread-bound.

### 11.5. Listener có transaction riêng do annotation khác

Nếu listener `BEFORE_COMMIT` gọi một service dùng `REQUIRES_NEW`, phần ghi của service có thể commit **độc lập trước T1**. Sau đó T1 rollback, để lại dữ liệu “audit” không khớp đơn hàng. Muốn atomically commit audit cùng orders, không được vô tình chuyển sang transaction riêng.

## 12. Kiểm thử pha BEFORE_COMMIT

Phải kiểm tra **thời điểm callback** và **ngữ nghĩa rollback**, không chỉ xác nhận một listener nhận được event.

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Transaction nguồn commit, audit thành công | Trạng thái đơn và audit cùng tồn tại sau commit |
| Publish trong transaction rồi chủ động rollback | Không có audit từ listener BEFORE_COMMIT và không có thay đổi đơn |
| Audit listener ném exception ở BEFORE_COMMIT | Phương thức/transaction trả lỗi; đơn không được commit |
| Audit listener thành công nhưng commit DB thất bại | Không được kết luận đơn đã hoàn tất chỉ từ log audit listener |
| Publish ngoài transaction | Listener không chạy theo mặc định |
| Email listener AFTER_COMMIT được đăng ký cùng event | Chỉ chạy khi transaction nguồn commit thành công |
| Gọi lại cùng command hoặc publish hai event | Phải xác định chính sách idempotency và tránh tạo audit/side effect trùng |
| Listener cố dùng transaction manager riêng | Kiểm tra tính nguyên tử bằng integration test, không dựa vào tên annotation |

### 12.1. Unit test cho việc publish

Test unit của `OrderService` có thể mock `ApplicationEventPublisher`, kiểm tra chỉ phát `OrderConfirmed` khi trạng thái đơn thay đổi. Tuy nhiên, mock publisher **không kích hoạt transaction synchronization**, nên không chứng minh listener `BEFORE_COMMIT` chạy đúng pha.

### 12.2. Integration test với TransactionTemplate

Ví dụ sau minh họa thời điểm callback, dùng JUnit 5 và AssertJ. Giả sử test có Spring context, `ApplicationEventPublisher` thực, `PlatformTransactionManager` và `AuditProbe` (abstraction kiểm tra các bản ghi audit đã commit):

~~~java
// Pseudocode integration test: AuditProbe là helper của test.
@Autowired TransactionTemplate transactionTemplate;
@Autowired ApplicationEventPublisher publisher;
@Autowired AuditProbe auditProbe;

@Test
void beforeCommitListenerRunsAtCommitBoundary() {
    UUID eventId = UUID.randomUUID();
    UUID correlationId = UUID.randomUUID();
    UUID orderId = UUID.randomUUID();

    transactionTemplate.executeWithoutResult(status -> {
        publisher.publishEvent(new OrderConfirmed(
                eventId, correlationId, orderId, Instant.now()));

        // Tại đây chưa bước vào BEFORE_COMMIT.
        assertThat(auditProbe.exists(eventId)).isFalse();
    });

    // TransactionTemplate đã commit, callback BEFORE_COMMIT đã được gọi.
    assertThat(auditProbe.exists(eventId)).isTrue();
}

@Test
void rollbackSkipsBeforeCommitListener() {
    UUID eventId = UUID.randomUUID();

    assertThatThrownBy(() ->
        transactionTemplate.executeWithoutResult(status -> {
            publisher.publishEvent(new OrderConfirmed(
                    eventId, UUID.randomUUID(),
                    UUID.randomUUID(), Instant.now()));
            throw new IllegalStateException("Force rollback");
        })
    ).isInstanceOf(IllegalStateException.class);

    assertThat(auditProbe.exists(eventId)).isFalse();
}
~~~

Mã test là **minh họa**: cần đặt trong test class có import phù hợp, khai báo bean `TransactionTemplate` hoặc khởi tạo từ `PlatformTransactionManager`, cung cấp `AuditProbe` và schema/test database. Điểm cần chứng minh là **callback chưa chạy ngay khi publish**, chạy ở commit boundary và không chạy nếu rollback xảy ra trước đó.

Để kiểm tra **listener BEFORE_COMMIT ném lỗi làm rollback**, dùng một `AuditWriter` test double ném exception ở sự kiện được chọn hoặc cấu hình database từ chối bản ghi audit. Gọi publisher trong transaction thực, chờ exception từ commit rồi xác nhận **cả bản ghi đơn và audit không được commit**.

### 12.3. Kiểm thử Spring Modulith và consumer sau commit

Trong test có đầy đủ `OrderService`, audit và notifications:

1. Xác nhận đơn thành công; audit tồn tại sau commit; listener notification sau commit được gọi.
2. Audit thất bại trong `BEFORE_COMMIT`; đơn rollback; notification `AFTER_COMMIT` không chạy.
3. Notification thất bại sau commit; đơn và audit vẫn được commit; publication của notification được theo dõi theo cấu hình registry.
4. Nếu notification nhận lại cùng event khi retry, không gửi tác động trùng.
5. Chạy `ApplicationModules.of(ShopApplication.class).verify()` để bảo đảm các listener chỉ import public event contract, không tham chiếu repository/entity nội bộ module khác.

Listener `@ApplicationModuleListener` chạy bất đồng bộ; test cần **chờ theo điều kiện và timeout**, không assert ngay khi `publishEvent(...)` trả về. Một test method `@Transactional` mặc định rollback ở cuối có thể khiến cả callback commit và after-commit không bao giờ chạy; bố trí test sao cho transaction nguồn **thực sự commit**.

## 13. Quan sát và vận hành: phân biệt “sắp commit” với “đã commit”

Vì `BEFORE_COMMIT` thực thi trước kết quả cuối cùng, log phải diễn đạt **đúng mốc sự kiện**.

Không nên ghi:

~~~java
// Sai về ý nghĩa khi đặt trong callback BEFORE_COMMIT:
log.info("Order CONFIRMED and committed, orderId={}", event.orderId());
~~~

Thay vào đó:

~~~java
log.debug("BEFORE_COMMIT audit attempt eventId={} orderId={} correlationId={}",
        event.eventId(), event.orderId(), event.correlationId());
~~~

Để biết đơn và audit **đã commit**, hãy dùng dữ liệu đã commit hoặc telemetry ở đúng mốc sau commit. Không biến log trước commit thành nguồn sự thật cuối cùng khi vận hành.

Các tín hiệu quan sát hữu ích:

- Số transaction rollback do callback `BEFORE_COMMIT` theo loại lỗi.
- Độ trễ `BEFORE_COMMIT` p95/p99 và mức chờ lock/connection.
- Số transaction commit thành công so với số yêu cầu xác nhận.
- Số publication `AFTER_COMMIT` chưa hoàn tất theo listener khi registry được cấu hình.
- `eventId`, `correlationId`, `orderId` trong log để nối publisher, callback và consumer sau commit.

Tránh dùng UUID `eventId`/`correlationId` làm tag metrics vì cardinality rất cao; lưu ID ở structured logs/traces, còn metrics dùng tên event, tên listener, trạng thái và loại lỗi.

## 14. Khi nào nên chọn BEFORE_COMMIT?

| Nhu cầu | Có nên dùng BEFORE_COMMIT? | Lý do |
| --- | --- | --- |
| Ghi audit trong **cùng database transaction**, thất bại audit phải làm đơn rollback | Có thể, nếu lựa chọn này được thiết kế rõ và kiểm thử | Chia sẻ transaction và điểm thất bại |
| Gửi email thông báo đơn đã xác nhận | **Không** | Email không rollback được, có thể gửi dù commit sau đó lỗi |
| Cập nhật projection báo cáo chấp nhận trễ | Thường **không** | Listener after-commit tách được độ trễ và lỗi |
| Kiểm tra tồn kho bắt buộc trước khi xác nhận đơn | Ưu tiên API/điều phối tường minh | Tránh điều phối ẩn qua listener |
| Gọi payment gateway hoặc HTTP bên ngoài | **Không nên** | Không có atomicity với T1 và có thể giữ lock quá lâu |
| Thực hiện cleanup sau rollback | Không | Dùng cơ chế phù hợp `AFTER_ROLLBACK` hoặc xử lý lỗi tường minh |
| Ghi dấu “đã commit” | Không | Tại BEFORE_COMMIT commit chưa chắc thành công |

Quy tắc thực dụng: **nếu một tác động có thể thất bại mà nguồn vẫn cần commit thành công, đừng đặt tác động ấy vào BEFORE_COMMIT**. Nếu tác động bắt buộc cùng transaction, phải xác nhận rằng dữ liệu/transaction manager thực sự cho phép nguyên tử, và rằng việc listener thất bại làm cả transaction rollback là đúng với hợp đồng nghiệp vụ.

## 15. Bài thực hành

Thiết kế ứng dụng Spring Modulith với ba module `orders`, `audit`, `notifications`. Quy tắc: **xác nhận đơn và ghi audit phải cùng commit; gửi email chỉ diễn ra sau khi đơn commit**.

Yêu cầu:

1. Tạo record `OrderConfirmed(eventId, correlationId, orderId, occurredAt)` công khai ở `orders`.
2. Viết `OrderService.confirm(...)` có `@Transactional`, thay đổi trạng thái hợp lệ và publish event đúng một lần.
3. Viết `OrderConfirmationAuditListener` với `@TransactionalEventListener(phase = BEFORE_COMMIT)`, dùng `JdbcTemplate` ghi bảng do `audit` sở hữu qua cùng transaction manager.
4. Viết `ConfirmationNotificationListener` với `@ApplicationModuleListener`, gửi email idempotent sau commit; không gửi từ `BEFORE_COMMIT`.
5. Test ba trường hợp: commit bình thường, rollback trước callback, audit ném exception làm rollback.
6. Cho email listener thất bại sau commit, quan sát publication khi registry bền vững được cấu hình; xác minh orders/audit vẫn tồn tại và retry không gửi trùng.
7. Đo latency trước commit khi audit bị làm chậm, giải thích tác động lên transaction duration và p95 HTTP.
8. Chạy kiểm tra module boundaries với `ApplicationModules.of(ShopApplication.class).verify()` và kiểm tra audit không import repository nội bộ của orders.

**Câu hỏi tự đánh giá:**

- `BEFORE_COMMIT` chạy tại `publishEvent(...)` hay khi transaction chuẩn bị commit?
- Nếu callback `BEFORE_COMMIT` đã hoàn tất, có chắc database đã commit không?
- Vì sao gửi email trong `BEFORE_COMMIT` có thể tạo thông báo sai?
- Nếu publisher không có transaction, listener có chạy theo mặc định không?
- Tại sao thêm `@Async` hoặc `REQUIRES_NEW` vào công việc cần nguyên tử cùng T1 có thể phá giả định?
- Registry phục hồi listener sau commit có thay được quy tắc audit ghi cùng transaction không?

## 16. Tổng kết

**`TransactionPhase.BEFORE_COMMIT` là pha xử lý event ngay trước khi commit transaction nguồn**, không phải lúc publish event và cũng không phải sau khi dữ liệu được commit. Với transaction manager và tài nguyên giao dịch phù hợp, listener có thể tham gia cùng transaction, và exception của listener có thể khiến cả transaction rollback. Đổi lại, mọi công việc tại pha này nằm trên đường commit, tăng coupling, độ trễ và rủi ro giữ lock.

Trong Spring Modulith, chỉ dùng `BEFORE_COMMIT` cho công việc **thực sự cần tham gia commit** với trách nhiệm được thiết kế rõ. Với email, projection và phản ứng phụ có thể hoàn tất muộn, dùng xử lý **AFTER_COMMIT** như `@ApplicationModuleListener`, phối hợp Event Publication Registry bền vững, retry có kiểm soát và idempotency. Khi cần một bất biến nghiệp vụ phải được xác nhận trước commit, ưu tiên một API/luồng điều phối tường minh hơn là giấu quyết định trong listener.

**Tài liệu tham khảo chính thức:**

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionPhase API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework — TransactionSynchronization.beforeCommit](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html#beforeCommit(boolean))
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
