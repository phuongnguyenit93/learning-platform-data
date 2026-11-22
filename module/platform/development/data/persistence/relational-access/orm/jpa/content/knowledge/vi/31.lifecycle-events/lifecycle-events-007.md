# Phân biệt callback sau thao tác và sự kiện sau commit thành công trong JPA

Trong Jakarta Persistence (JPA), một annotation như `@PostPersist` hoặc `@PostUpdate` có chữ **Post** rất dễ khiến lập trình viên hiểu rằng *dữ liệu đã được lưu thành công và không thể rollback*. Đây là một ngộ nhận nguy hiểm.

**Callback sau thao tác của entity không đồng nghĩa với sự kiện sau khi transaction commit thành công.** Một entity có thể đã được INSERT hoặc UPDATE khi `flush()` chạy, callback tương ứng đã thực thi, nhưng giao dịch vẫn có thể rollback vì lỗi nghiệp vụ, vi phạm ràng buộc, optimistic locking, timeout hoặc một thành phần khác đánh dấu rollback-only.

Ví dụ một đơn hàng được xác nhận:

~~~text
Transaction begin
       |
       v
Order.status = CONFIRMED
       |
       v
flush() -> SQL UPDATE
       |
       v
@PostUpdate chạy
       |
       v
Lỗi nghiệp vụ ở bước kế tiếp
       |
       v
Transaction rollback
       |
       v
Database vẫn có Order.status = DRAFT
~~~

Nếu `@PostUpdate` đã gửi email “Đơn hàng được xác nhận” tới khách hàng, email đó **không thể tự rollback cùng database**. Người dùng nhận thông báo cho một thay đổi **chưa từng commit thành công**.

Bài này thuộc chủ đề **Data Persistence Relational Access ORM JPA**, chương **Sự kiện vòng đời**, với mục tiêu trực tiếp là **“Phân biệt callback sau thao tác và sự kiện sau commit thành công”**.

Nội dung sẽ giúp xác định đúng ranh giới của JPA lifecycle callbacks, Spring transaction events, JTA transaction synchronization và transactional outbox; đồng thời đưa ra các ví dụ, kiểm thử commit/rollback và quy tắc lựa chọn cho hệ thống production.

**Quy tắc cần nhớ:**

> `@PostPersist`, `@PostUpdate`, `@PostRemove` là callback vòng đời entity; **chúng không phải xác nhận transaction đã commit**. Muốn làm việc *chỉ sau khi commit thành công*, cần dùng cơ chế transaction-aware phù hợp. Muốn bảo đảm sự kiện không bị mất khi process crash, cần cơ chế bền vững như **transactional outbox**, chứ không chỉ một callback sau commit.

---

## 1. Phân biệt hai cấp độ: thao tác JPA và giao dịch database

Một unit of work JPA thường có các bước:

1. Bắt đầu transaction.
2. Nạp hoặc tạo entity.
3. Thay đổi managed state.
4. Provider đồng bộ thay đổi thành SQL khi flush.
5. Database xử lý SQL trong transaction chưa commit.
6. Transaction manager cố gắng commit.
7. Database xác nhận commit, hoặc rollback nếu không thể hoàn tất.
8. Ứng dụng thực hiện công việc tiếp theo theo kết quả transaction.

**`flush` và `commit` không phải cùng thao tác.**

| Khái niệm | Ý nghĩa | Dữ liệu bền vững sau lời gọi? |
| --- | --- | --- |
| `entity.setStatus(...)` | Thay đổi Java managed state | Chưa |
| `em.persist(entity)` | Đưa entity mới vào persistence context | Chưa nhất thiết INSERT; chưa commit |
| `em.remove(entity)` | Đánh dấu entity cần xóa | Chưa commit |
| `em.flush()` | Đồng bộ pending changes thành SQL | Chưa; SQL vẫn thuộc transaction |
| `transaction.commit()` | Hoàn tất transaction thành công | Có theo bảo đảm của database |
| `transaction.rollback()` | Hủy các thay đổi của transaction | Không giữ DML chưa commit |
| `@PostUpdate` | Lifecycle callback sau cập nhật theo quy tắc JPA | **Không bảo đảm commit** |
| `AFTER_COMMIT` listener | Handler được kích hoạt sau outcome commit thành công | Commit đã xảy ra, nhưng handler chưa chắc giao được sự kiện bền vững |

### 1.1. Một thao tác UPDATE có thể hoàn tất mà transaction vẫn thất bại

~~~text
T0 BEGIN
T1 UPDATE orders SET status='CONFIRMED' WHERE id=101
T2 @PostUpdate
T3 INSERT audit_row -> lỗi constraint
T4 ROLLBACK

Final database:
  orders.id=101, status='DRAFT'
~~~

`@PostUpdate` có thể chạy tại T2 nhưng **không thể biết trước** rằng T3 sẽ thành công.

### 1.2. Sau commit mới khác sau flush

~~~text
Entity callback:
  [flush/SQL] --> @PostUpdate --------> [commit hoặc rollback]

Transaction callback:
  [flush/SQL] --> [COMMIT thành công] --> AFTER_COMMIT
~~~

Hai ranh giới này có hợp đồng khác nhau, nên phải lựa chọn theo **ý nghĩa nghiệp vụ** của thao tác cần làm.

## 2. Tổng quan JPA entity lifecycle callbacks

JPA định nghĩa các callback phổ biến:

- `@PrePersist`
- `@PostPersist`
- `@PreUpdate`
- `@PostUpdate`
- `@PreRemove`
- `@PostRemove`
- `@PostLoad`

Chúng được đặt trong entity class hoặc một entity listener class đăng ký qua `@EntityListeners`. Mỗi callback tương ứng **sự kiện lifecycle của entity**, không phải sự kiện transaction manager báo commit.

### 2.1. Bảng ý nghĩa và giới hạn

| Annotation | Khi nào mang ý nghĩa? | Có khẳng định transaction commit? |
| --- | --- | --- |
| `@PrePersist` | Trước khi entity được persist/INSERT theo lifecycle | Không |
| `@PostPersist` | Sau INSERT entity theo lifecycle; có thể trước commit | **Không** |
| `@PreUpdate` | Trước khi update được đồng bộ theo lifecycle | Không |
| `@PostUpdate` | Sau update theo lifecycle; thời điểm có thể ở flush/transaction completion | **Không** |
| `@PreRemove` | Trước khi entity được remove theo lifecycle | Không |
| `@PostRemove` | Sau DELETE entity theo lifecycle; có thể trước commit | **Không** |
| `@PostLoad` | Sau khi entity được load/refresh theo lifecycle | **Không** |

Một số provider có cách bố trí chính xác callback quanh SQL và transaction boundary khác nhau trong những trường hợp như ID generation, flush mode, batching hoặc lifecycle transitions. Nhưng **không callback nào trong bảng là “after successful commit” portable của JPA**.

### 2.2. “Post” là sau mốc entity, không phải sau mốc transaction

`@PostPersist` có thể được gọi sau khi database đã thực hiện INSERT trong **transaction đang mở**.

`@PostUpdate` có thể được gọi sau UPDATE khi flush.

`@PostRemove` có thể được gọi sau DELETE trong quá trình flush.

`@PostLoad` thậm chí có thể chạy trong một thao tác đọc, **không có update để commit**.

Không viết:

~~~java
@PostUpdate
void notifyCustomer() {
    // Sai nếu coi đây là AFTER_COMMIT.
    emailGateway.send(...);
}
~~~

mà không xem xét việc rollback và side effects.

---

## 3. Mô hình ví dụ: đơn hàng và sự kiện xác nhận

Ta dùng một entity đơn hàng nhỏ để quan sát vòng đời. Ví dụ dùng Java 17+, `jakarta.persistence.*`.

### 3.1. Trạng thái đơn hàng

~~~java
package com.example.order.domain;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
~~~

### 3.2. Entity SalesOrder

~~~java
package com.example.order.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "sales_orders")
@EntityListeners(SalesOrderLifecycleLogger.class)
public class SalesOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true)
    private String orderCode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Version
    private Long version;

    protected SalesOrder() {
    }

    public SalesOrder(String orderCode) {
        this.orderCode = orderCode;
        this.status = OrderStatus.DRAFT;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only draft orders can be confirmed"
            );
        }
        status = OrderStatus.CONFIRMED;
    }
}
~~~

Entity này có:

- ID database-generated.
- Một business state chuyển từ `DRAFT` sang `CONFIRMED`.
- `@Version` để phát hiện concurrent updates.
- `@EntityListeners` để quan sát lifecycle.

### 3.3. Listener dùng để ghi log kỹ thuật

~~~java
package com.example.order.domain;

import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.PostRemove;
import jakarta.persistence.PostUpdate;
import java.util.logging.Logger;

public class SalesOrderLifecycleLogger {

    private static final Logger LOG =
        Logger.getLogger(
            SalesOrderLifecycleLogger.class.getName()
        );

    @PostPersist
    public void afterInsert(SalesOrder order) {
        LOG.fine(
            "JPA PostPersist orderId=" + order.getId()
        );
    }

    @PostUpdate
    public void afterUpdate(SalesOrder order) {
        LOG.fine(
            "JPA PostUpdate orderId=" + order.getId()
        );
    }

    @PostRemove
    public void afterDelete(SalesOrder order) {
        LOG.fine(
            "JPA PostRemove orderId=" + order.getId()
        );
    }

    @PostLoad
    public void afterLoad(SalesOrder order) {
        LOG.fine(
            "JPA PostLoad orderId=" + order.getId()
        );
    }
}
~~~

Ở đây callback chỉ ghi **log kỹ thuật mang tính quan sát**, không gửi email, thanh toán, gọi HTTP hoặc giả định transaction thành công. Log “PostUpdate” có nghĩa ORM đã đến mốc callback tương ứng; không có nghĩa order đã commit.

**Ví dụ listener này không phải một hệ thống audit bền vững.** Log có thể được ghi dù transaction về sau rollback và có thể không được giữ nếu process crash.

### 3.4. Schema đơn giản

~~~sql
CREATE TABLE sales_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL
);
~~~

Schema ví dụ cần được điều chỉnh theo dialect, migration và JPA provider của dự án.

---

## 4. Cách khai báo callback trong entity và entity listener

Có hai cách thường gặp.

**Đặt trực tiếp trên entity:**

~~~java
@Entity
public class ExampleEntity {

    @PostLoad
    private void onLoaded() {
        // Chỉ xử lý logic phù hợp lifecycle entity.
    }
}
~~~

**Đặt trong listener class:**

~~~java
public class ExampleListener {

    @PostPersist
    public void afterPersist(ExampleEntity entity) {
        // Nhận entity đang xảy ra lifecycle event.
    }
}
~~~

Với listener class, đăng ký:

~~~java
@Entity
@EntityListeners(ExampleListener.class)
public class ExampleEntity {
    // ...
}
~~~

Đoạn mã ngắn minh họa cú pháp. Không nên tạo thêm một class `ExampleEntity` khác trong dự án đã có entity cùng tên.

### 4.1. Callback không phải service có đủ transaction API

JPA lifecycle callback có ràng buộc portability. Không nên từ callback tùy ý:

- Gọi `EntityManager.persist/remove/flush`.
- Mở JPQL query.
- Chỉnh quan hệ giữa các entity trong cùng persistence context.
- Gọi nghiệp vụ phức tạp có thể khiến provider tái nhập flush.
- Gửi request HTTP có thể chậm hoặc thất bại.
- Khởi tạo side effects mà transaction rollback không hoàn tác được.

Các nguyên tắc portable của JPA cho phép xử lý trạng thái không phải relationship của chính entity trong các tình huống phù hợp, nhưng **không biến callback thành nơi điều phối một transaction nghiệp vụ khác**.

Nếu cần thao tác database khác cùng transaction, thường rõ ràng hơn khi thực hiện trong **application service**.

### 4.2. Injection vào entity listener phụ thuộc môi trường

Một listener do JPA provider tạo không phải lúc nào cũng là Spring bean hoặc CDI bean đã được inject như application tưởng. Jakarta EE/CDI và framework integration có thể hỗ trợ injection trong một số môi trường, nhưng không nên giả định:

~~~java
@Autowired
private EmailService emailService;
~~~

luôn hoạt động trong mọi JPA listener hoặc mọi cách bootstrap Java SE.

Cho dù injection hoạt động, **vấn đề commit boundary vẫn tồn tại**. Không gửi email ở `@PostUpdate` chỉ vì đã có thể inject service.

### 4.3. Không đảm bảo mỗi thao tác Java tạo đúng một callback

Một lời gọi:

~~~java
order.confirm();
~~~

chưa nhất thiết phát SQL ngay. `@PostUpdate` có thể chỉ đến khi dirty checking/flush thực hiện UPDATE.

Nếu gán lại cùng giá trị cũ, entity có thể không dirty, dẫn tới **không có UPDATE và không có `@PostUpdate`**.

Nếu entity được thay đổi và flush nhiều lần trong một transaction, những callbacks gắn với updates thực tế có thể xảy ra nhiều lần. Không dùng số callback làm số lượng sự kiện nghiệp vụ “chắc chắn đã commit”.

---

## 5. Dòng thời gian: PostUpdate chạy trước rollback

Một service JPA resource-local minh họa:

~~~java
EntityManager em = emf.createEntityManager();

try {
    em.getTransaction().begin();

    SalesOrder order =
        em.find(SalesOrder.class, orderId);

    order.confirm();

    em.flush();
    // UPDATE có thể đã chạy; @PostUpdate có thể đã chạy.

    if (businessRuleFailed()) {
        throw new IllegalStateException(
            "Related business operation failed"
        );
    }

    em.getTransaction().commit();
} catch (RuntimeException ex) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw ex;
} finally {
    em.close();
}
~~~

`businessRuleFailed()` là predicate nghiệp vụ minh họa; trong ví dụ thực, thay bằng validation hoặc thao tác có thể thất bại sau flush.

Diễn biến:

~~~text
t0 BEGIN
t1 SELECT sales_orders WHERE id = ?
t2 Java: DRAFT -> CONFIRMED
t3 em.flush()
t4 SQL UPDATE sales_orders ...
t5 @PostUpdate invoked
t6 businessRuleFailed -> exception
t7 ROLLBACK

Giá trị bền vững:
  status vẫn DRAFT
~~~

Nếu email đã gửi ở t5, database rollback ở t7 không thu hồi được email đó.

### 5.1. Nguy cơ không chỉ là exception trong code Java

Rollback có thể xảy ra khi:

- Database phát lỗi foreign key/unique constraint lúc flush hoặc commit.
- Optimistic locking phát hiện version cũ.
- Transaction bị đánh dấu rollback-only bởi tầng service khác.
- Transaction manager phát timeout hoặc hệ thống hủy giao dịch.
- Một operation khác trong transaction thất bại.
- Kết quả commit không thành công do lỗi hạ tầng.

Do đó logic “cứ `@PostUpdate` là đã lưu” là không đúng ngay cả khi code service không có dòng `throw` tường minh.

## 6. PostPersist và PostRemove cũng có thể chạy trước commit

### 6.1. PostPersist sau INSERT không phải sau commit

~~~java
em.getTransaction().begin();

SalesOrder order =
    new SalesOrder("ORD-001");

em.persist(order);
em.flush();

// @PostPersist có thể đã được gọi.
em.getTransaction().rollback();
~~~

Sau rollback, order có thể **không tồn tại trong database**, dù callback đã ghi log “PostPersist”.

Với `GenerationType.IDENTITY`, provider có thể phải gửi INSERT sớm để lấy ID; vì thế callback có thể xảy ra ngay trong lộ trình `persist`/flush trước khi commit. Với những generation strategies khác, thời điểm insert có thể khác.

**ID đã được sinh không chứng minh transaction đã commit.**

### 6.2. PostRemove sau DELETE không phải sau commit

~~~java
em.getTransaction().begin();

SalesOrder order =
    em.find(SalesOrder.class, orderId);

em.remove(order);
em.flush();

// @PostRemove có thể đã chạy.
em.getTransaction().rollback();
~~~

Nếu transaction rollback, database vẫn có thể giữ order như trước. Đừng xóa file trên object storage hoặc phát sự kiện “đơn hàng đã xóa vĩnh viễn” ngay trong callback `@PostRemove`.

### 6.3. PostLoad càng không liên quan commit

`@PostLoad` chạy theo lifecycle tải entity hoặc refresh tùy provider/cách truy cập. Nó có thể xảy ra khi chỉ đọc dữ liệu, không có DML hay transaction commit.

~~~java
SalesOrder order =
    em.find(SalesOrder.class, orderId);

// @PostLoad có thể được gọi trong quá trình load.
~~~

Nếu cùng context đã giữ managed entity, `find` lần hai có thể trả instance hiện có mà không thực hiện load mới và không gọi lại `@PostLoad`.

---

## 7. Flush có thể tự động xảy ra trước query

Không phải code nào cũng viết `em.flush()` tường minh.

Trong flush mode thông thường, provider có thể đồng bộ pending changes trước khi thực thi một JPQL query có liên quan.

~~~java
order.confirm();

// Có thể khiến provider flush pending changes
// trước query, tùy flush mode và provider.
List<SalesOrder> matches = em.createQuery(
    """
    SELECT o
    FROM SalesOrder o
    WHERE o.status = :status
    """,
    SalesOrder.class
)
.setParameter("status", OrderStatus.CONFIRMED)
.getResultList();
~~~

Nếu flush diễn ra trước SELECT, `@PostUpdate` có thể chạy **ngay trong lời gọi query**, trong khi transaction còn mở.

### 7.1. Không phụ thuộc vào “callback chỉ chạy ở commit”

Sai về thiết kế:

~~~text
@PostUpdate sẽ chạy đúng lúc commit,
nên side effect ở callback chắc chắn an toàn.
~~~

Đúng hơn:

~~~text
@PostUpdate gắn với JPA update lifecycle;
thời điểm có thể là flush/transaction completion
và không phải tín hiệu successful commit.
~~~

### 7.2. FlushModeType.COMMIT cũng không phải after-commit event

`FlushModeType.COMMIT` ảnh hưởng lịch đồng bộ SQL, nhưng không biến `@PostUpdate` thành callback có contract “chỉ sau commit thành công”. Lỗi có thể xảy ra khi commit đang được xử lý sau khi lifecycle callbacks đã chạy.

Muốn quan sát transaction outcome, hãy dùng transaction manager integration phù hợp.

---

## 8. Hai luồng sự kiện độc lập

Một hệ thống nên phân biệt:

**Luồng A — entity persistence lifecycle:**

~~~text
Entity được persist/dirty/remove
             |
             v
Provider chọn thời điểm flush
             |
             v
INSERT / UPDATE / DELETE
             |
             v
@PostPersist / @PostUpdate / @PostRemove
             |
             v
Transaction vẫn có thể commit hoặc rollback
~~~

**Luồng B — successful-commit notification:**

~~~text
Application service thực hiện nghiệp vụ
             |
             v
Phát một domain/application event
  trong transaction, hoặc ghi outbox row
             |
             v
Transaction manager cố commit
             |
       +-----+------+
       |            |
       v            v
    COMMITTED     ROLLED BACK
       |            |
       v            v
  AFTER_COMMIT    Không phát
  processing      success event
~~~

Ở luồng B, event được gắn với **kết quả của transaction**, không chỉ việc entity đã qua một callback.

### 8.1. Domain event khác entity lifecycle event

Ví dụ `OrderConfirmedEvent` có ý nghĩa:

> “Nghiệp vụ xác nhận đơn hàng đã được thực hiện và transaction xác nhận đơn hàng commit thành công.”

Trong khi `@PostUpdate` chỉ cho biết:

> “Provider đã cập nhật một entity theo lifecycle và callback tương ứng được gọi.”

Một update entity có thể đến từ các nghiệp vụ khác: thay địa chỉ, cập nhật ghi chú, sửa trạng thái hoặc migration. `@PostUpdate` không tự nói **ý định nghiệp vụ là gì**.

Nên tạo domain event ở **application service**, nơi business operation đã được xác định.

---

## 9. Spring: @EventListener khác @TransactionalEventListener

Khi dùng Spring Framework/Spring Data JPA, có hai kiểu listener dễ nhầm.

### 9.1. Event thường: @EventListener

~~~java
@Component
public class ImmediateOrderListener {

    @EventListener
    public void on(OrderConfirmedEvent event) {
        notificationGateway.send(event.orderId());
    }
}
~~~

Với application event publisher đồng bộ mặc định, `@EventListener` thường xử lý **ngay tại thời điểm `publishEvent`**, có thể vẫn nằm giữa transaction chưa commit.

~~~text
@Transactional method begins
    |
    +-- order.confirm()
    +-- publisher.publishEvent(event)
            |
            v
        @EventListener chạy NGAY
            |
            v
        gửi email
    |
    +-- commit hoặc rollback sau đó
~~~

Không dùng event thường rồi giả định Spring tự đợi commit.

### 9.2. Transaction-bound event: @TransactionalEventListener

Spring cung cấp:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void on(OrderConfirmedEvent event) {
    notificationGateway.send(event.orderId());
}
~~~

Khi event được publish trong một transaction được Spring quản lý và listener có phase `AFTER_COMMIT`, handler được gắn với transaction outcome và chạy sau khi transaction **commit thành công**.

Đây là cơ chế phù hợp hơn khi cần **không gửi thông báo cho một transaction rollback**.

**Nhưng nó chưa phải cơ chế giao sự kiện bền vững qua process crash.** Sau database commit, nếu JVM chết trước khi listener xử lý, sự kiện chỉ nằm trong bộ nhớ có thể bị mất.

---

## 10. Ví dụ hoàn chỉnh: phát OrderConfirmedEvent đúng nơi

### 10.1. Event chứa dữ liệu độc lập

~~~java
package com.example.order.event;

public record OrderConfirmedEvent(
    Long orderId,
    String orderCode
) {
}
~~~

Event không chứa `SalesOrder` managed entity. Điều này quan trọng vì sau commit persistence context có thể không còn hợp lệ, và listener không nên dựa vào lazy loading của object được truyền ra ngoài transaction.

### 10.2. Spring Data repository

~~~java
package com.example.order.repository;

import com.example.order.domain.SalesOrder;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {
}
~~~

### 10.3. Application service thực hiện nghiệp vụ

~~~java
package com.example.order.service;

import com.example.order.domain.SalesOrder;
import com.example.order.event.OrderConfirmedEvent;
import com.example.order.repository.SalesOrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {

    private final SalesOrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderCommandService(
            SalesOrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(Long orderId) {
        SalesOrder order = orders.findById(orderId)
            .orElseThrow(
                () -> new IllegalArgumentException(
                    "Order does not exist: " + orderId
                )
            );

        order.confirm();

        events.publishEvent(
            new OrderConfirmedEvent(
                order.getId(),
                order.getOrderCode()
            )
        );

        // Spring transaction interceptor sẽ flush/commit
        // khi method hoàn tất thành công.
    }
}
~~~

**Điểm cần chú ý:** `publishEvent` ở đây được gọi **trước commit**. Điều an toàn không đến từ bản thân lời gọi publish; nó đến từ listener gắn `AFTER_COMMIT`.

### 10.4. Listener chỉ chạy sau commit

~~~java
package com.example.order.event;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderConfirmationListener {

    private final NotificationGateway notifications;

    public OrderConfirmationListener(
            NotificationGateway notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterCommit(OrderConfirmedEvent event) {
        notifications.sendOrderConfirmed(
            event.orderId(),
            event.orderCode()
        );
    }
}
~~~

Gateway interface:

~~~java
package com.example.order.event;

public interface NotificationGateway {

    void sendOrderConfirmed(
        Long orderId,
        String orderCode
    );
}
~~~

Trong ví dụ này, notification gateway là một abstraction cho hệ thống gửi thông báo. Implementation có thể gọi HTTP/email, nhưng cần timeout, idempotency và retry policy phù hợp.

### 10.5. Trình tự thành công

~~~text
Controller -> OrderCommandService.confirm(101)
                 |
                 v
          Spring transaction begins
                 |
                 v
          Load SalesOrder#101
                 |
                 v
          DRAFT -> CONFIRMED
                 |
                 v
          publish OrderConfirmedEvent
                 |
                 v
          Listener đăng ký AFTER_COMMIT
                 |
                 v
          Flush UPDATE và commit thành công
                 |
                 v
          AFTER_COMMIT listener chạy
                 |
                 v
          Send notification
~~~

### 10.6. Trình tự rollback

~~~text
Service confirm(101)
      |
      v
DRAFT -> CONFIRMED
      |
      v
Publish event vào transaction scope
      |
      v
Exception / rollback-only / commit failure
      |
      v
ROLLBACK
      |
      v
AFTER_COMMIT listener không chạy
~~~

Đây là khác biệt quan trọng so với gửi notification trực tiếp trong `@PostUpdate` hoặc `@EventListener` đồng bộ.

---

## 11. Các phase của @TransactionalEventListener

Spring hỗ trợ một số phase:

| Phase | Thời điểm | Use case |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước bước commit khi transaction đang hoàn tất | Logic gắn với giai đoạn trước commit, không phải external success notification |
| `AFTER_COMMIT` | Sau khi transaction commit thành công | Gửi signal/thông báo sau commit nếu chấp nhận best-effort |
| `AFTER_ROLLBACK` | Sau khi transaction rollback | Metrics/compensation logic thích hợp |
| `AFTER_COMPLETION` | Sau transaction completion dù commit hay rollback | Cleanup/observability không mặc định thành công |

### 11.1. BEFORE_COMMIT không bảo đảm commit sau đó

Một listener `BEFORE_COMMIT` có thể chạy trước khi bước commit thất bại, vì vậy cũng không thích hợp để gửi “đã hoàn tất” ra ngoài.

### 11.2. AFTER_ROLLBACK không phải tín hiệu xóa business data

`AFTER_ROLLBACK` hữu ích để ghi metric hoặc giải phóng một số tài nguyên tạm. Không nên mặc định tự động xóa hàng database trong cùng transaction đã rollback.

### 11.3. AFTER_COMPLETION cần kiểm tra outcome nếu có

`AFTER_COMPLETION` mang nghĩa transaction đã kết thúc, **không khẳng định committed**. Với JTA `Synchronization.afterCompletion(int status)`, status cho biết transaction committed/rolled back/unknown.

Nếu logic chỉ đúng sau commit, hãy sử dụng `AFTER_COMMIT` hoặc kiểm tra status một cách rõ ràng.

## 12. Khi event được publish ngoài transaction

`@TransactionalEventListener` mặc định có `fallbackExecution = false`. Nếu event được publish **không có transaction phù hợp**, listener transaction-bound thường không được gọi.

Ví dụ:

~~~java
events.publishEvent(
    new OrderConfirmedEvent(orderId, code)
);
~~~

trong một method không có transaction active **không phải cách an toàn để “gửi ngay”** nếu listener chờ `AFTER_COMMIT`.

### 12.1. fallbackExecution=true là quyết định nghiệp vụ

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handle(OrderConfirmedEvent event) {
    // ...
}
~~~

Khi không có transaction, cấu hình fallback cho phép listener xử lý event; lúc đó **không hề có commit để chờ**. Điều này có thể phá semantics “chỉ sau database commit”.

Chỉ bật fallback khi use case thực sự cho phép xử lý sự kiện ngoài transaction; không dùng nó như biện pháp chữa triệu chứng listener “không chạy”.

### 12.2. Event phải được publish trong đúng transaction scope

Transaction synchronization trong Spring thông thường gắn với thread/context transaction hiện tại. Nếu phát event trong một thread khác không mang transaction context, listener có thể không đăng ký như mong muốn.

Không chuyển việc publish sang `CompletableFuture.runAsync(...)` rồi mặc định nó vẫn thuộc transaction ban đầu.

---

## 13. AFTER_COMMIT không đồng nghĩa một transaction mới

Một điểm tinh tế của Spring: khi `AFTER_COMMIT` callback chạy, một số transaction-bound resources có thể **vẫn còn accessible trong giai đoạn completion**. Nếu listener cố ghi database qua resource vẫn gắn với transaction vừa commit, việc ghi đó có thể **không được commit như application mong muốn**.

Không nên làm:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public void handle(OrderConfirmedEvent event) {
    auditRepository.save(
        new NotificationAudit(event.orderId())
    );
    // Đừng mặc định có transaction commit mới.
}
~~~

### 13.1. Dùng REQUIRES_NEW khi cần ghi database sau commit

Tách một service riêng:

~~~java
package com.example.order.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NotificationAuditService {

    private final NotificationAuditRepository audits;

    public NotificationAuditService(
            NotificationAuditRepository audits) {
        this.audits = audits;
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW
    )
    public void record(Long orderId) {
        audits.save(
            new NotificationAudit(orderId)
        );
    }
}
~~~

Listener:

~~~java
@Component
public class AuditingOrderListener {

    private final NotificationAuditService auditService;

    public AuditingOrderListener(
            NotificationAuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void handle(OrderConfirmedEvent event) {
        auditService.record(event.orderId());
    }
}
~~~

`NotificationAudit` và `NotificationAuditRepository` là thành phần minh họa cần được mapping/triển khai theo schema thật.

**Vì sao tách bean?** Spring proxy-based `@Transactional` thường không kích hoạt advice trên self-invocation `this.record(...)` trong cùng instance.

### 13.2. REQUIRES_NEW không làm hai transactions atomic

Transaction A (order confirmation) đã commit. Transaction B (audit notification) mới bắt đầu. Nếu B thất bại:

~~~text
Transaction A: COMMITTED
Transaction B: ROLLED BACK
~~~

A **không tự rollback trở lại**. Đây là hai transactions độc lập, không phải một distributed atomic transaction.

Nếu business bắt buộc order confirmation và audit record có cùng số phận commit/rollback, hãy **ghi audit record trong cùng transaction A**, không đợi AFTER_COMMIT rồi ghi transaction B.

---

## 14. Lỗi trong AFTER_COMMIT không hủy commit đã hoàn tất

Giả sử database đã commit order thành CONFIRMED. Sau đó listener gọi email provider và provider báo timeout.

~~~text
DB transaction -> COMMITTED
         |
         v
AFTER_COMMIT listener
         |
         v
Email timeout / exception
~~~

**Không thể dựa vào exception ở listener để rollback transaction đã commit.** Tùy Spring event infrastructure/callback handling, exception có thể ảnh hưởng response hoặc log/đường xử lý lỗi, nhưng database outcome vẫn là COMMITTED.

Do đó API có thể gặp tình huống:

- Database đã lưu thành công.
- Email chưa gửi.
- Client nhận lỗi hoặc không chắc lệnh confirm có thành công hay không.
- Client retry lệnh và cần tránh side effects trùng.

Phải xây dựng **idempotency**, trạng thái gửi notification riêng hoặc outbox để xử lý thực tế.

### 14.1. Gửi HTTP trong AFTER_COMMIT có thể kéo dài response

Nếu listener đồng bộ và gọi HTTP/email chậm:

~~~text
DB commit thành công:      30 ms
Notification external:   2000 ms
API response total:      > 2030 ms
~~~

Các số trên chỉ minh họa. Even after-commit listener có thể nằm trên critical path của HTTP request khi chạy đồng bộ.

Với nhu cầu thông báo không ảnh hưởng latency, cần queue/worker hoặc asynchronous processing có chính sách reliability rõ. Chỉ thêm `@Async` không tự tạo durable event delivery.

---

## 15. JPA chuẩn không có @PostCommit portable

Các annotation JPA như `@PostPersist` và `@PostUpdate` thuộc **entity lifecycle callbacks**. Jakarta Persistence không cung cấp một annotation chuẩn tương đương `@PostCommit` cho mọi entity/provider.

Một số ORM có API proprietary để nghe post-commit events, nhưng mức độ portable, semantics và cách register phụ thuộc provider/version.

Nếu ứng dụng muốn không phụ thuộc Hibernate-specific internals, có thể chọn:

- Spring `@TransactionalEventListener(AFTER_COMMIT)` khi Spring là transaction manager.
- Jakarta Transactions (JTA) `Synchronization.afterCompletion` khi dùng JTA.
- Explicit transaction outcome handling trong application-managed resource-local code.
- Transactional outbox khi cần durability và retry.

Không ép `@PostUpdate` đóng vai trò mà đặc tả JPA không hứa.

## 16. JTA: Synchronization.afterCompletion kiểm tra commit status

Trong môi trường Jakarta EE/JTA, transaction manager cung cấp **Synchronization** callback.

~~~java
package com.example.order.service;

import jakarta.annotation.Resource;
import jakarta.ejb.Stateless;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Status;
import jakarta.transaction.Synchronization;
import jakarta.transaction.TransactionSynchronizationRegistry;

@Stateless
public class OrderJtaService {

    @PersistenceContext
    private EntityManager em;

    @Resource
    private TransactionSynchronizationRegistry txRegistry;

    public void confirm(Long orderId) {
        SalesOrder order =
            em.find(SalesOrder.class, orderId);

        if (order == null) {
            throw new IllegalArgumentException(
                "Order does not exist"
            );
        }

        order.confirm();

        Long idForEvent = order.getId();

        txRegistry.registerInterposedSynchronization(
            new Synchronization() {

                @Override
                public void beforeCompletion() {
                    // Chưa được xem là committed.
                }

                @Override
                public void afterCompletion(int status) {
                    if (status == Status.STATUS_COMMITTED) {
                        // Gửi signal tới handler phù hợp.
                        onCommitSignal(idForEvent);
                    }
                }
            }
        );
    }

    private void onCommitSignal(Long orderId) {
        // Ví dụ: notify component nội bộ;
        // production cần xử lý durability/retry.
    }
}
~~~

`SalesOrder` trong ví dụ là entity đã định nghĩa. Để code compile trong project thật cần imports/package phù hợp cho entity.

### 16.1. Vì sao dùng TransactionSynchronizationRegistry?

`TransactionSynchronizationRegistry` cho phép thành phần JTA đăng ký callback theo transaction hiện tại qua `registerInterposedSynchronization`. Registration yêu cầu transaction context thích hợp; không gọi khi không có transaction rồi kỳ vọng callback tự thực thi.

Callback:

~~~java
afterCompletion(int status)
~~~

có thể nhận:

- `Status.STATUS_COMMITTED`.
- `Status.STATUS_ROLLEDBACK`.
- `Status.STATUS_UNKNOWN` hoặc status khác tùy kết quả và implementation.

Chỉ nhánh **COMMITTED** mới mang nghĩa successful commit.

### 16.2. Không thao tác EntityManager tùy ý trong afterCompletion

Trong callback completion, transaction vừa kết thúc và resource lifecycle đang chuyển trạng thái. Không dựa vào managed entity/proxy hoặc gọi JPA write như thể còn transaction active.

Ví dụ bắt `idForEvent` trước khi commit là có chủ đích. Nếu cần đọc/ghi database sau commit, mở **transaction/context mới** từ một thành phần được điều phối đúng.

### 16.3. beforeCompletion không phải before successful commit

`beforeCompletion()` xảy ra trước completion; transaction vẫn có thể rollback sau đó.

Chỉ sử dụng cho logic phù hợp transaction synchronization, không gửi “đã đặt hàng thành công” từ đây.

### 16.4. JTA callback cũng có crash window

Database có thể commit, nhưng process chứa `afterCompletion` crash trước khi gửi notification. JTA synchronization **không tự biến một HTTP call thành thành viên atomic của database transaction**.

Nếu cần giao sự kiện bền vững, outbox vẫn là lựa chọn quan trọng.

---

## 17. Resource-local: xử lý sau commit bằng code tường minh

Nếu ứng dụng dùng `EntityManagerFactory.createEntityManager()` với `RESOURCE_LOCAL`, có thể đặt side effect **sau lời gọi commit thành công**:

~~~java
public void confirmOrder(
        EntityManagerFactory emf,
        NotificationGateway notifier,
        Long orderId) {

    EntityManager em = emf.createEntityManager();

    String code;

    try {
        em.getTransaction().begin();

        SalesOrder order =
            em.find(SalesOrder.class, orderId);

        if (order == null) {
            throw new IllegalArgumentException(
                "Order not found"
            );
        }

        order.confirm();
        code = order.getOrderCode();

        em.getTransaction().commit();

    } catch (RuntimeException ex) {
        if (em.getTransaction().isActive()) {
            em.getTransaction().rollback();
        }
        throw ex;
    } finally {
        em.close();
    }

    // Chỉ đến đây nếu commit() trả về thành công.
    notifier.sendOrderConfirmed(orderId, code);
}
~~~

**Ưu điểm:** dễ nhìn thấy thứ tự “commit rồi gọi notifier”.

**Giới hạn lớn:** sau commit, process có thể chết trước lời gọi notifier; hoặc notifier thất bại khi database đã commit. Không có atomicity giữa database commit và network side effect.

### 17.1. Không gọi notifier trong finally

Sai:

~~~java
try {
    transaction.commit();
} finally {
    notifier.sendOrderConfirmed(...);
}
~~~

`finally` chạy cả khi commit ném lỗi. Không dùng finally làm cơ chế successful-commit signaling.

### 17.2. Commit có thể trả outcome khó xác định khi mất kết nối

Nếu kết nối bị mất vào thời điểm commit, caller có thể không biết database đã commit hay chưa. Đây là một lý do khác để thiết kế idempotent commands và durable event tracking thay vì chỉ dựa vào một cờ Java trong memory.

---

## 18. Kiểu side effect nào được phép ở entity callbacks?

Không phải mọi callback đều “cấm dùng”. Cần phân loại công việc.

### 18.1. Thường phù hợp với callback

- Chuẩn hóa field trước persist/update.
- Cập nhật timestamp trong `@PrePersist`/`@PreUpdate` khi logic phù hợp.
- Kiểm tra điều kiện cục bộ của entity.
- Thiết lập giá trị dẫn xuất không liên quan relationship theo quy tắc portable.
- Log kỹ thuật phục vụ quan sát lifecycle (ghi rõ không phải commit proof).

Ví dụ:

~~~java
@PrePersist
void beforeInsert() {
    createdAt = java.time.Instant.now();
}
~~~

Cần tránh gọi query/EntityManager và các thao tác tái nhập flush không portable trong callback.

### 18.2. Không phù hợp khi cần successful commit

- Gửi email “đã thanh toán”.
- Gọi API vận chuyển để tạo đơn giao hàng.
- Publish event tới message broker có yêu cầu không gửi khi rollback.
- Trừ tiền ở hệ thống ngoài.
- Xóa file ngoài database.
- Thay đổi search index bên ngoài như một trạng thái nghiệp vụ đã hoàn tất.
- Gửi websocket notification xác nhận dữ liệu committed.

Những việc này phải được thiết kế theo transaction outcome; nếu cần **reliable delivery**, nên dùng outbox/inbox hoặc giải pháp đồng bộ trạng thái bền vững.

### 18.3. Log/audit có hai loại khác nhau

**Technical logs:** có thể ghi “PostUpdate invoked” để debug, dù transaction rollback.

**Business audit:** ghi “Đơn đã xác nhận thành công” thường chỉ nên tồn tại khi thay đổi nghiệp vụ commit thành công. Có thể ghi **audit row trong cùng DB transaction**, để rollback cùng nghiệp vụ, hoặc phát durable event theo outbox.

Không trộn technical lifecycle log với committed business audit.

---

## 19. Audit cùng transaction khác audit sau commit

Nếu business yêu cầu:

> Xác nhận đơn hàng và ghi audit log phải **cùng thành công hoặc cùng thất bại**.

Cách đơn giản thường là ghi hai entity trong **cùng transaction**:

~~~java
@Transactional
public void confirm(Long orderId) {
    SalesOrder order = orders.findById(orderId)
        .orElseThrow();

    order.confirm();

    audits.save(
        OrderAudit.confirmed(
            order.getId(),
            "Order confirmed"
        )
    );
}
~~~

`OrderAudit`, `OrderAudit.confirmed` và `audits` là những thành phần minh họa phải được định nghĩa riêng theo model thực tế.

Trong cùng transaction:

~~~text
UPDATE sales_orders
INSERT order_audit
       |
       v
COMMIT -> cả hai thành công

hoặc

ROLLBACK -> cả hai đều không được lưu
~~~

Đây là **transactional audit**, không cần chờ AFTER_COMMIT để tạo audit row.

### 19.1. Tại sao tránh EntityManager calls trong @PostUpdate?

Nếu `@PostUpdate` trực tiếp persist một Audit entity bằng EntityManager, code có thể vi phạm các giới hạn portable của lifecycle callback và gây vòng lặp flush/re-entrancy. Đặt thao tác audit trong service rõ ràng hơn.

### 19.2. Audit một hành động thất bại cần chính sách riêng

Nếu bắt buộc ghi nhận cả “attempted but rolled back”, log/audit đó **không thể cùng chung transaction bị rollback** nếu vẫn muốn giữ lại. Cần cơ chế ghi nhận độc lập, phân quyền và định nghĩa rõ trạng thái attempted vs committed; không gọi attempt là một successful order confirmation.

---

## 20. Transactional outbox: giải pháp bền vững hơn after-commit callback

`@TransactionalEventListener(AFTER_COMMIT)` tránh gửi event trên rollback, nhưng vẫn có một **khoảng hở mất sự kiện**:

~~~text
Database COMMIT thành công
           |
           | Process crash
           v
Không kịp gửi notification
~~~

**Transactional outbox** giải quyết khoảng hở này bằng cách ghi một **outbox record trong cùng database transaction** với thay đổi nghiệp vụ.

~~~text
Transaction A:
    UPDATE sales_orders
    INSERT outbox_events
           |
           v
          COMMIT
           |
           v
   Database giữ cả business state và event intent
           |
           v
Worker đọc outbox row đã commit
           |
           v
Gửi message/email tới hệ thống ngoài
           |
           v
Đánh dấu delivered / retry khi lỗi
~~~

Nếu Transaction A rollback, cả UPDATE và outbox record rollback. Nếu Transaction A commit, worker có thể tìm lại outbox row sau khi process restart.

### 20.1. Schema outbox minh họa

~~~sql
CREATE TABLE outbox_events (
    id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_outbox_pending
    ON outbox_events (delivered_at, created_at);
~~~

Schema mang tính minh họa, portable ở mức khái niệm; production cần cân nhắc DB dialect, indexing, retention, claim/lease và concurrency.

### 20.2. Entity OutboxEvent

~~~java
package com.example.order.outbox;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "outbox_events")
public class OutboxEvent {

    @Id
    @Column(length = 36)
    private String id;

    @Column(name = "aggregate_type", nullable = false)
    private String aggregateType;

    @Column(name = "aggregate_id", nullable = false)
    private Long aggregateId;

    @Column(name = "event_type", nullable = false)
    private String eventType;

    @Column(name = "payload", nullable = false)
    private String payload;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected OutboxEvent() {
    }

    public OutboxEvent(
            String aggregateType,
            Long aggregateId,
            String eventType,
            String payload) {

        this.id = java.util.UUID.randomUUID().toString();
        this.aggregateType = aggregateType;
        this.aggregateId = aggregateId;
        this.eventType = eventType;
        this.payload = payload;
        this.createdAt = Instant.now();
    }

    public String getId() {
        return id;
    }

    public String getPayload() {
        return payload;
    }
}
~~~

Outbox event phải có **event ID ổn định** để downstream consumers có thể deduplicate.

### 20.3. Ghi business update và outbox trong một transaction

~~~java
@Service
public class ReliableOrderCommandService {

    private final SalesOrderRepository orders;
    private final EntityManager em;

    public ReliableOrderCommandService(
            SalesOrderRepository orders,
            EntityManager em) {
        this.orders = orders;
        this.em = em;
    }

    @Transactional
    public void confirm(Long orderId) {
        SalesOrder order = orders.findById(orderId)
            .orElseThrow();

        order.confirm();

        String payload =
            "{\"orderId\":" + order.getId() +
            ",\"orderCode\":\"" +
            escapeJson(order.getOrderCode()) + "\"}";

        em.persist(new OutboxEvent(
            "SalesOrder",
            order.getId(),
            "OrderConfirmed",
            payload
        ));
    }

    private static String escapeJson(String value) {
        return value.replace("\\", "\\\\")
            .replace("\"", "\\\"");
    }
}
~~~

Đây là ví dụ đơn giản minh họa **atomic transaction**. Production nên dùng **JSON serializer chuẩn** thay vì tự xây JSON bằng nối chuỗi; encoder trên chỉ xử lý một phần ký tự và không phải giải pháp serialize toàn diện.

Mấu chốt là:

~~~text
UPDATE sales_orders
INSERT outbox_events
COMMIT chung transaction
~~~

Nếu commit thất bại, không có outbox record đã commit để worker nhầm gửi event.

### 20.4. Worker giao outbox event

Một worker/dispatcher có thể:

1. Lấy một nhóm outbox records chưa delivered.
2. Claim/lock records để nhiều workers không xử lý cùng lúc.
3. Gửi tới message broker/email service.
4. Ghi nhận kết quả delivery.
5. Retry nếu chưa xác nhận thành công.
6. Giữ event ID cho idempotency.

Với PostgreSQL, `FOR UPDATE SKIP LOCKED` là một khả năng claim rows; đây là tính năng SQL của database, không phải JPQL portable cho mọi provider.

### 20.5. At-least-once và duplicate delivery

Có một tình huống quan trọng:

~~~text
Worker gửi event thành công
          |
          v
Process chết trước khi đánh dấu delivered_at
          |
          v
Worker khởi động lại và gửi lại event
~~~

Outbox giúp **không bỏ sót event intent đã commit**, nhưng có thể dẫn đến **giao lặp**. Vì vậy subscriber phải **idempotent** hoặc dùng inbox/deduplication theo event ID.

Không khẳng định “outbox bảo đảm exactly-once delivery end-to-end” chỉ vì dùng một database transaction.

---

## 21. Khi nào AFTER_COMMIT đủ, khi nào cần outbox?

| Nhu cầu | Cách thường phù hợp | Giới hạn |
| --- | --- | --- |
| Ghi log kỹ thuật khi entity UPDATE | `@PostUpdate` | Có thể chạy trước rollback |
| Chuẩn hóa field trước persist | `@PrePersist` | Không phù hợp external side effects |
| In-process UI hint best-effort sau commit | `@TransactionalEventListener(AFTER_COMMIT)` | Crash window |
| Signal sau JTA commit | `Synchronization.afterCompletion(COMMITTED)` | Crash window; không tự durable |
| Email có thể retry bằng job định kỳ | Outbox + worker | Có thể duplicate, cần idempotency |
| Publish message nghiệp vụ quan trọng | Transactional outbox + broker/CDC | Cần vận hành worker/CDC |
| Audit row phải atomic với thay đổi DB | Ghi cùng transaction | Không đại diện side effect bên ngoài |
| Đọc DB và ghi DB sau commit | Transaction mới, ví dụ `REQUIRES_NEW` | Không atomic với transaction trước |
| Trừ tiền ngoài hệ thống | Idempotent command + saga/outbox/compensation | Không thể rollback như local SQL |
| Phát sự kiện sau bulk UPDATE | Event ở application service/outbox | Bulk không gọi lifecycle callback từng entity |

**Không có một annotation duy nhất vừa bảo đảm after successful commit, vừa bảo đảm giao sự kiện bền vững và exactly-once across systems.**

## 22. JPA callback không được gọi cho mọi thay đổi database

Một giới hạn quan trọng: **bulk JPQL/native updates** không đi qua lifecycle dirty checking trên từng managed instance như `persist`/`remove`/managed updates thông thường.

Ví dụ:

~~~java
int changed = em.createQuery(
    """
    UPDATE SalesOrder o
    SET o.status = :confirmed
    WHERE o.status = :draft
    """
)
.setParameter("confirmed", OrderStatus.CONFIRMED)
.setParameter("draft", OrderStatus.DRAFT)
.executeUpdate();
~~~

Đừng kỳ vọng `@PostUpdate` được gọi một lần cho **mỗi row** bị ảnh hưởng bởi bulk UPDATE.

Tương tự, SQL chạy từ migration, JDBC job hay service ngoài JPA không tự phát lifecycle callbacks trong JVM của ứng dụng.

### 22.1. Callback không phải nguồn sự kiện nghiệp vụ đáng tin cậy

Nếu một nghiệp vụ có cả đường ghi:

- Managed entity update.
- Bulk JPQL update.
- Native SQL.
- Stored procedure.
- External integration.

thì việc gửi event hoàn toàn dựa vào `@PostUpdate` có thể tạo **thiếu sự kiện** ở những đường không đi qua callback.

Hãy phát domain event/outbox từ **command/use case** hoặc thiết kế CDC/change capture ở tầng dữ liệu theo yêu cầu.

### 22.2. @PostLoad cũng không tương ứng mỗi SELECT

Khi entity đã managed trong first-level cache, `em.find` lặp lại có thể trả cùng object và không trigger một load lifecycle mới. Vì vậy không dùng `@PostLoad` để đếm số SQL SELECT hoặc số lần user xem dữ liệu.

---

## 23. Nhiều flush trong một transaction không tương đương nhiều commit

Ví dụ:

~~~java
em.getTransaction().begin();

SalesOrder order =
    em.find(SalesOrder.class, orderId);

order.confirm();

em.flush(); // UPDATE và có thể PostUpdate

// Thêm thay đổi khác trên entity khác.
otherEntity.changeState();

em.flush(); // SQL bổ sung; lifecycle khác có thể được gọi

em.getTransaction().commit(); // Chỉ một commit
~~~

Có thể có nhiều persistence callbacks trong cùng một transaction, nhưng kết quả transaction có **một outcome** commit/rollback.

Nếu mỗi `@PostUpdate` gửi một notification, hệ thống có thể gửi thừa hoặc sai số lượng.

### 23.1. Một business event có thể liên quan nhiều entity updates

Ví dụ “Xác nhận đơn hàng” có thể thay:

- `SalesOrder.status`.
- `OrderLine` reservations.
- `InventoryItem` quantities.
- `OrderAudit` entries.

Có thể có nhiều entity callbacks, nhưng chỉ nên tạo một `OrderConfirmedEvent` có nghĩa nghiệp vụ sau khi toàn bộ transaction thành công.

### 23.2. Một entity có thể được cập nhật nhiều lần

Nếu thao tác tiếp tục thay entity sau một flush, provider có thể phát thêm UPDATE ở flush tiếp. Vì vậy không coi `@PostUpdate` là “exactly once per transaction” hoặc “exactly once per business command”.

---

## 24. Spring @Transactional và self-invocation

Giả sử service:

~~~java
@Service
class OrderService {

    @Transactional
    public void confirm(Long id) {
        doConfirm(id);
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW
    )
    public void doConfirm(Long id) {
        // ...
    }
}
~~~

Trong Spring proxy-based AOP, lời gọi nội bộ `this.doConfirm(...)` có thể **không đi qua transaction proxy**, nên annotation `REQUIRES_NEW` không có hiệu lực như mong muốn.

Hệ quả:

- Event có thể được publish vào transaction không như dự kiến.
- Commit/rollback boundaries bị hiểu nhầm.
- AFTER_COMMIT listener có thể đăng ký vào transaction khác hoặc không có transaction.
- Test chạy xanh giả vì cùng context/proxy setup.

Hãy gọi qua bean/proxy khác hoặc dùng `TransactionTemplate` khi thật sự cần điều phối nhiều transactions.

## 25. Async event processing phải giữ semantics commit

Nếu listener dùng `@Async`, code chạy trên thread pool khác. Có những điểm cần kiểm tra:

- Event được đăng ký với transaction ở thread/transaction context đúng lúc **publish**.
- Handler `AFTER_COMMIT` có thể được dispatch async tùy cấu hình.
- Thread xử lý không mặc định có transaction/persistence context của publisher.
- Không truy cập lazy entity graph được truyền qua event.
- Exception trong async listener cần được ghi nhận và xử lý retry.
- Process crash vẫn có thể làm mất event chỉ tồn tại trong bộ nhớ.

Ví dụ nên truyền:

~~~java
public record OrderConfirmedEvent(
    Long orderId,
    String orderCode
) {
}
~~~

Không truyền:

~~~java
public record OrderConfirmedEvent(
    SalesOrder managedOrder
) {
}
~~~

rồi trông đợi listener async có thể lazy-load các association trong transaction đã commit.

**Async cải thiện scheduling/latency, không thay thế durability.**

---

## 26. Kiểm thử sự khác biệt bằng integration tests

Bài test cần phân biệt ít nhất ba điều:

1. Callback `@PostUpdate` có thể đã chạy trước rollback.
2. `AFTER_COMMIT` listener **không được chạy khi rollback**.
3. `AFTER_COMMIT` listener **được chạy sau commit thành công** trong cấu hình phù hợp.

Test mock thuần Java chỉ có thể chứng minh một method được gọi, **không thể tự chứng minh transaction manager đã commit hoặc rollback đúng**.

### 26.1. Chuẩn bị fixture

Ví dụ dùng JUnit 5, Spring Boot Test và transaction manager thật cùng database thử nghiệm.

Fixture có thể được tạo ở một transaction riêng:

~~~java
@Transactional
public Long createDraftOrder(String code) {
    SalesOrder order = new SalesOrder(code);
    orders.save(order);
    return order.getId();
}
~~~

Method này phải được gọi **qua một Spring bean/proxy** để `@Transactional` có hiệu lực, không phải self-invocation. Với IDENTITY, ID thường được gán qua INSERT; nếu cần chắc chắn cho test, dùng `saveAndFlush` theo repository API.

Test tạo mã đơn unique để không va unique constraint.

### 26.2. Test double notification gateway

Một implementation test-only:

~~~java
package com.example.order.test;

import com.example.order.event.NotificationGateway;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

public class RecordingNotificationGateway
        implements NotificationGateway {

    private final List<Long> sentOrderIds =
        new CopyOnWriteArrayList<>();

    @Override
    public void sendOrderConfirmed(
            Long orderId,
            String orderCode) {
        sentOrderIds.add(orderId);
    }

    public List<Long> sentOrderIds() {
        return List.copyOf(sentOrderIds);
    }

    public void reset() {
        sentOrderIds.clear();
    }
}
~~~

Có thể đăng ký bean test này bằng `@TestConfiguration` và `@Primary`, hoặc mock bean theo version Spring Boot đang dùng. Không để test double thành một notification gateway production mặc định.

### 26.3. Test thành công: AFTER_COMMIT được gọi

~~~java
@Test
void confirmedOrderTriggersNotificationAfterCommit() {
    Long id = fixtures.createDraftOrder(
        "ORDER-" + java.util.UUID.randomUUID()
    );

    notifications.reset();

    service.confirm(id);

    // Với listener đồng bộ mặc định và service transaction
    // đã hoàn tất, notification phải được ghi nhận.
    assertEquals(
        List.of(id),
        notifications.sentOrderIds()
    );

    OrderStatus persisted =
        queryService.readStatusInNewTransaction(id);

    assertEquals(
        OrderStatus.CONFIRMED,
        persisted
    );
}
~~~

Các field `fixtures`, `notifications`, `service` và `queryService` đại diện các Spring beans được inject vào integration test. `readStatusInNewTransaction` phải thực sự mở transaction/context mới hoặc đọc từ một scope có state mới, tránh first-level cache của test.

**Đây là code minh họa cho cấu hình listener đồng bộ**. Nếu dự án sử dụng `@Async`, assertion cần cơ chế await có timeout thay vì giả định handler hoàn thành ngay khi service trả.

### 26.4. Test rollback: AFTER_COMMIT không được gọi

Dùng `TransactionTemplate`:

~~~java
@Test
void rollbackDoesNotTriggerAfterCommitNotification() {
    Long id = fixtures.createDraftOrder(
        "ORDER-" + java.util.UUID.randomUUID()
    );

    notifications.reset();

    transactionTemplate.executeWithoutResult(status -> {
        service.confirm(id);

        // Service @Transactional REQUIRED tham gia
        // transaction đang được TransactionTemplate quản lý.
        status.setRollbackOnly();
    });

    assertTrue(
        notifications.sentOrderIds().isEmpty()
    );

    assertEquals(
        OrderStatus.DRAFT,
        queryService.readStatusInNewTransaction(id)
    );
}
~~~

Các điều kiện cần:

- `service.confirm` dùng propagation mặc định `REQUIRED` và thực sự tham gia outer transaction.
- Event được publish trong transaction đó.
- Test không bị một `REQUIRES_NEW` khác commit confirmation riêng.
- Listener `@TransactionalEventListener(AFTER_COMMIT)` không có fallback xử lý ngoài transaction.
- Đọc trạng thái cuối bằng context mới.

**Nếu test method tự có `@Transactional` bao ngoài, cần kiểm soát nó**; nếu không, outer transaction khác có thể làm lịch commit/rollback không giống mong muốn.

---

## 27. Kiểm thử @PostUpdate có thể xảy ra trước rollback

Để quan sát callback, có thể tạo một **test-only lifecycle probe** đếm `@PostUpdate` trong memory. Đây chỉ là công cụ test, không phải business event delivery.

Ví dụ listener trong test:

~~~java
public final class LifecycleProbe {

    public static final java.util.concurrent.atomic.AtomicInteger
        POST_UPDATES = new java.util.concurrent.atomic.AtomicInteger();

    private LifecycleProbe() {
    }

    @PostUpdate
    public static void afterUpdate(SalesOrder order) {
        POST_UPDATES.incrementAndGet();
    }
}
~~~

**Lưu ý kỹ thuật:** ví dụ trên thể hiện ý tưởng probe; khi đăng ký làm JPA entity listener trong provider thực tế, hãy dùng listener class với **instance method hợp lệ**, constructor phù hợp và đăng ký `@EntityListeners`/metadata tương ứng. Không sao chép static callback test helper thành production code khi chưa xác minh lifecycle listener signature.

Một bản dễ dùng hơn:

~~~java
public class ProbeEntityListener {

    public static final java.util.concurrent.atomic.AtomicInteger
        POST_UPDATES = new java.util.concurrent.atomic.AtomicInteger();

    @PostUpdate
    public void onUpdate(SalesOrder order) {
        POST_UPDATES.incrementAndGet();
    }
}
~~~

Đăng ký probe cho entity test chuyên biệt hoặc mapping test, không thay đổi entity production chỉ vì một assertion. Test phải chạy tuần tự/cô lập vì static counter có thể bị nhiễu từ tests khác.

### 27.1. Kịch bản có flush rồi rollback

~~~java
@Test
void postUpdateCanRunEvenWhenTransactionRollsBack() {
    Long id = fixtures.createDraftOrder(
        "ORDER-" + java.util.UUID.randomUUID()
    );

    ProbeEntityListener.POST_UPDATES.set(0);
    notifications.reset();

    transactionTemplate.executeWithoutResult(status -> {
        SalesOrder order =
            entityManager.find(SalesOrder.class, id);

        order.confirm();

        entityManager.flush();

        assertTrue(
            ProbeEntityListener.POST_UPDATES.get() >= 1,
            "Expected lifecycle callback after flush"
        );

        // Hoàn tất bằng rollback.
        status.setRollbackOnly();
    });

    assertEquals(
        OrderStatus.DRAFT,
        queryService.readStatusInNewTransaction(id)
    );

    assertTrue(
        notifications.sentOrderIds().isEmpty()
    );
}
~~~

**Ý nghĩa:** JPA callback đã được quan sát, nhưng transaction rollback nên database vẫn DRAFT và AFTER_COMMIT notification không chạy.

**Điều kiện:** probe phải thực sự được đăng ký trong entity mapping của integration test; listener setup, flush behavior và test context phải tương thích provider. Đây là phép kiểm tra với Hibernate/JPA configuration cụ thể, không phải lời khẳng định rằng mọi provider buộc callback đúng tại mọi dòng được minh họa.

### 27.2. Tránh assertion dựa vào commit trong cùng test transaction bị auto-rollback

Trong Spring tests, `@Transactional` trên test method thường khiến transaction rollback khi test kết thúc. Nếu dùng cấu hình này và expect `AFTER_COMMIT` listener chạy ngay trong body test, test sẽ thất bại hoặc cho kết quả gây nhầm lẫn.

Có thể:

- Không gắn `@Transactional` trên test method kiểm tra successful commit.
- Dùng `TransactionTemplate` để commit tường minh.
- Dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` trong môi trường Spring Test phù hợp.
- Tách fixture transaction và act transaction rõ ràng.

Không chỉ thêm `@Commit` mà không hiểu test transaction boundary thực sự.

---

## 28. Kiểm thử JTA afterCompletion

Trong JTA, phép đo nên xác nhận:

- `registerInterposedSynchronization` được gọi khi active transaction.
- Với transaction commit, `afterCompletion(STATUS_COMMITTED)` được nhận.
- Với rollback, status không phải COMMITTED.
- Handler nghiệp vụ “success only” không chạy ở nhánh rollback.
- Không đọc managed entity từ callback sau transaction.

Một test có thể dùng một observer test-only ghi lại statuses:

~~~java
List<Integer> statuses =
    new java.util.concurrent.CopyOnWriteArrayList<>();

txRegistry.registerInterposedSynchronization(
    new Synchronization() {
        @Override
        public void beforeCompletion() {
        }

        @Override
        public void afterCompletion(int status) {
            statuses.add(status);
        }
    }
);
~~~

Đây chỉ là minh họa quan sát callback; phải chạy bên trong một JTA transaction thật do container/test framework tạo. Nếu test có nhiều transactions, dùng correlation ID hoặc observer riêng cho từng transaction, không chỉ một list global.

**Không coi callback COMMITTED tương đương email đã giao thành công**. Nó chỉ xác nhận outcome của transaction.

---

## 29. Những tình huống lỗi dễ nhầm

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `@PostUpdate` chạy nhưng DB không thay đổi | Transaction rollback sau flush | Không dùng callback làm committed event |
| Email gửi dù order rollback | Email được gửi trong callback hoặc immediate listener | Chuyển sang AFTER_COMMIT/outbox |
| Listener `AFTER_COMMIT` không chạy | Event publish ngoài transaction; fallback mặc định false | Kiểm tra transaction boundary |
| `@Transactional` có nhưng không có transaction mới | Spring self-invocation/proxy | Dùng bean khác/TransactionTemplate |
| `AFTER_COMMIT` chạy nhưng ghi DB audit không lưu | Không có transaction commit mới | Dùng REQUIRES_NEW hoặc ghi cùng transaction chính |
| DB đã commit nhưng notification thất bại | External side effect sau commit | Outbox, retry, idempotency |
| Process crash làm mất event | In-memory after-commit callback không durable | Transactional outbox |
| Email bị gửi hai lần | Retry/at-least-once delivery | Event ID + idempotent consumer |
| `@PostUpdate` không chạy khi bulk JPQL UPDATE | Bulk bypass entity lifecycle | Emit event theo command/outbox |
| `@PostUpdate` không chạy khi setter no-op | Không có dirty UPDATE | Không dùng callback làm business command counter |
| `@PostLoad` chạy khi chỉ đọc | Load lifecycle | Không liên quan commit |
| Listener đọc LAZY entity bị lỗi | Context đã kết thúc/async thread | Event chỉ chứa ID/scalars; transaction mới khi đọc |
| Query trong entity listener gây lỗi | Callback re-entrancy/portability constraint | Đưa persistence orchestration sang service |
| Listener gửi external call quá chậm | Callback đồng bộ | Queue/worker và latency budget |
| Test AFTER_COMMIT luôn không chạy | Test tự rollback `@Transactional` | Commit tường minh qua test boundary |
| Test callback và event bị lặp | Nhiều flush hoặc listeners đăng ký trùng | Quan sát transaction và registration |
| JTA callback nhận STATUS_UNKNOWN | Transaction outcome không được xác nhận | Không giả định thành công; reconcile |
| Test pass với mock publisher | Chưa kiểm tra transaction commit thực | Integration test thật |
| Audit có record dù nghiệp vụ rollback | Audit ghi ở transaction ngoài/side effect sớm | Xác định attempted vs committed audit |
| Cache/state vẫn cũ sau event | EntityManager cũ giữ L1 | Đọc context mới/refresh theo contract |

## 30. Những ngộ nhận cần tránh

### “PostUpdate nghĩa là update đã commit”

Sai. `@PostUpdate` là entity lifecycle callback, có thể xảy ra trong flush trước commit.

### “Flush thành công đồng nghĩa transaction thành công”

Sai. SQL đã được thực thi trong transaction có thể rollback trước khi trở thành thay đổi bền vững.

### “PostPersist có ID nghĩa là dữ liệu đã tồn tại bền vững”

Sai. ID database-generated có thể được cấp trước commit; rollback vẫn hủy INSERT.

### “@EventListener của Spring tự chờ commit”

Sai. Listener thường xử lý khi publisher phát event, thường trước commit.

### “@TransactionalEventListener luôn chạy kể cả không có transaction”

Sai. Mặc định `fallbackExecution=false`, không có transaction thích hợp thì event có thể không được xử lý bởi transactional listener.

### “AFTER_COMMIT có thể rollback nghiệp vụ nếu email lỗi”

Sai. Commit đã hoàn tất, listener thất bại không đảo ngược database commit.

### “AFTER_COMMIT tự mở một transaction database mới”

Sai. Nếu muốn một DB write mới được commit, hãy thiết kế transaction mới phù hợp, thường qua service `REQUIRES_NEW`.

### “@Async giải quyết mất sự kiện”

Sai. Async chuyển việc xử lý sang thread khác, nhưng event chỉ ở memory vẫn có thể mất khi process crash.

### “Outbox nghĩa là exactly-once tự động”

Sai. Worker có thể giao lại event nếu crash sau khi gửi nhưng trước khi đánh dấu delivered. Consumer cần idempotency.

### “Entity callback đủ để phát mọi event từ database”

Sai. Bulk/native SQL, stored procedures và thay đổi từ ứng dụng khác không tự kích hoạt JPA callback trên từng entity.

### “Một PostUpdate tương ứng một nghiệp vụ”

Sai. Một update có thể phục vụ nhiều loại business operations, hoặc một nghiệp vụ gây nhiều updates.

### “PostLoad là dấu hiệu SELECT thành công rồi commit”

Sai. PostLoad liên quan load/refresh entity, không phải transaction completion.

---

## 31. Bài tập tình huống có lời giải

### Bài 1. Email trong @PostUpdate

Sau `em.flush()`, listener gửi email; bước cuối ném exception, transaction rollback.

**Đáp án:** Email đã gửi nhưng DB rollback. Không dùng `@PostUpdate` cho success notification; dùng after-commit event hoặc outbox.

### Bài 2. @PostPersist sau IDENTITY insert

Provider INSERT để lấy ID, PostPersist chạy, rồi transaction rollback.

**Đáp án:** ID đã có và callback đã chạy không chứng minh row được commit. Không báo “đơn đã tạo thành công” từ PostPersist.

### Bài 3. @PostRemove rồi rollback

**Đáp án:** Row có thể vẫn tồn tại sau rollback. Không xóa file ngoài database chỉ dựa vào PostRemove.

### Bài 4. @PostLoad khi find

**Đáp án:** Liên quan entity load, không có nghĩa đã có commit. L1 có thể làm lần find sau không load mới.

### Bài 5. @EventListener thông thường

Service phát event giữa transaction; listener gửi notification ngay, rồi commit thất bại.

**Đáp án:** Plain EventListener không chờ transaction outcome. Dùng `@TransactionalEventListener(AFTER_COMMIT)` khi cần commit success.

### Bài 6. Publish event ngoài transaction

Listener `@TransactionalEventListener(AFTER_COMMIT)` không chạy.

**Đáp án:** Mặc định không fallback ngoài transaction. Sửa transaction boundary hoặc quyết định rõ semantics của fallback.

### Bài 7. AFTER_COMMIT ghi thêm audit row

Listener dùng repository save nhưng không có transaction mới, audit không được commit.

**Đáp án:** Dùng service khác có `REQUIRES_NEW` nếu audit thật sự phải ghi sau commit; hoặc ghi audit trong cùng transaction nếu cần atomicity.

### Bài 8. Sau commit email provider timeout

**Đáp án:** DB đã commit; không rollback được. Dùng retry/idempotency và outbox nếu cần giao notification bền vững.

### Bài 9. JVM crash giữa commit và notification

**Đáp án:** In-memory AFTER_COMMIT event có thể mất. Dùng outbox row ghi trong cùng transaction rồi worker xử lý sau restart.

### Bài 10. Outbox gửi trùng

Worker gửi thành công nhưng chết trước khi đánh dấu delivered.

**Đáp án:** Có thể gửi lại. Consumer/gateway cần dedupe theo event ID hoặc idempotent operation.

### Bài 11. Bulk UPDATE thay 1.000 orders

**Đáp án:** Không mong `@PostUpdate` chạy 1.000 lần. Domain event/outbox cần được tạo từ application operation hoặc một cơ chế data capture phù hợp.

### Bài 12. Hai flush trong một transaction

**Đáp án:** Có thể có nhiều lifecycle callbacks, nhưng chỉ một transaction outcome. Không dùng callback count thay event count.

### Bài 13. JTA afterCompletion status ROLLEDBACK

**Đáp án:** Không phát committed success notification. Chỉ nhánh `STATUS_COMMITTED` mới xác nhận successful commit.

### Bài 14. JTA afterCompletion status UNKNOWN

**Đáp án:** Không giả định commit thành công. Cần reconciliation/operational handling phù hợp.

### Bài 15. Callback dùng EntityManager.persist(Audit)

**Đáp án:** Không portable và dễ gây re-entrancy khi flush. Chuyển việc ghi audit vào application service cùng transaction.

### Bài 16. Event chứa managed SalesOrder

Listener async truy cập `order.getLines()` sau commit và lỗi lazy.

**Đáp án:** Event chỉ nên chứa ID/scalars. Nếu cần đọc trạng thái đã commit, mở transaction/context mới.

### Bài 17. Spring self-invocation

`@Transactional(REQUIRES_NEW)` trên method nội bộ không hoạt động như mong đợi.

**Đáp án:** Đi qua bean/proxy khác hoặc TransactionTemplate. Không mặc định annotation có hiệu lực qua `this.method()`.

### Bài 18. @Transactional test tự rollback

Test mong AFTER_COMMIT listener chạy nhưng cuối test rollback.

**Đáp án:** Commit tường minh trong integration test hoặc bỏ outer test transaction, dùng transaction boundaries rõ.

### Bài 19. Business audit phải atomic với order

**Đáp án:** Ghi audit row cùng transaction; đừng chờ AFTER_COMMIT rồi mới ghi nếu yêu cầu “cùng thành công hoặc cùng thất bại”.

### Bài 20. Log kỹ thuật “PostUpdate invoked”

**Đáp án:** Log này có thể hợp lệ dù transaction rollback, miễn được đặt tên đúng và không trình bày như một committed business audit.

### Bài 21. Event nên gắn entity update hay command?

**Đáp án:** Một event `OrderConfirmedEvent` có ý nghĩa nghiệp vụ nên được phát từ command/service xử lý confirm, không suy từ mọi `PostUpdate`.

### Bài 22. Có nên gửi HTTP đồng bộ ở AFTER_COMMIT?

**Đáp án:** Có thể nếu best-effort và chấp nhận latency/failure, nhưng không bảo đảm delivery. Với event quan trọng cần outbox/worker/retry.

### Bài 23. AFTER_ROLLBACK dùng để làm gì?

**Đáp án:** Có thể ghi metrics hoặc cleanup phù hợp; không nên gọi đó là successful business event.

### Bài 24. Hai transactions cùng update versioned order

Một transaction commit, transaction kia gặp `OptimisticLockException` khi flush.

**Đáp án:** Transaction thất bại không được phát AFTER_COMMIT event; entity lifecycle callback vẫn không thay thế transaction outcome.

---

## 32. Checklist thiết kế sự kiện vòng đời và commit

Trước khi thêm callback hoặc event listener, hãy hỏi:

1. Hành động cần xử lý xảy ra sau **entity lifecycle** hay sau **successful commit**?
2. Có khả năng flush chạy trước commit không?
3. Nếu transaction rollback, side effect có được phép tồn tại không?
4. Có dùng `@PostPersist`, `@PostUpdate` hoặc `@PostRemove` chỉ để phát business event không?
5. Có biết `@PostLoad` không tương ứng commit không?
6. Có bulk/native SQL bypass entity callbacks không?
7. Service có transaction boundary thực sự không?
8. Với Spring, publish event có nằm trong transaction đúng không?
9. Listener là `@EventListener` hay `@TransactionalEventListener`?
10. `TransactionPhase` nào phản ánh yêu cầu?
11. `fallbackExecution` có làm event chạy ngoài transaction không?
12. Với JTA, có kiểm tra status `STATUS_COMMITTED` không?
13. Listener có cố đọc entity/proxy sau context đóng không?
14. Event có mang ID/scalars thay vì managed entity graph không?
15. Handler có cần ghi database trong transaction mới không?
16. `REQUIRES_NEW` có thực sự được gọi qua Spring proxy không?
17. Sau commit handler thất bại, nghiệp vụ xử lý thế nào?
18. Có crash window khiến event bị mất không?
19. Event có yêu cầu durability không?
20. Nếu dùng outbox, business update và outbox INSERT có cùng transaction không?
21. Worker có retry và claim rows an toàn không?
22. Consumer có idempotency/event ID không?
23. Có tách technical log, attempted audit và committed audit không?
24. Integration tests có kiểm chứng cả commit lẫn rollback không?
25. Test có bị `@Transactional` auto-rollback che khuất AFTER_COMMIT không?
26. Có test flush rồi rollback để chứng minh khác nhau không?
27. Có test optimistic conflict/commit failure không?
28. Có quan sát callback mà không lẫn với business notification không?
29. Event handler có timeout và monitoring thích hợp không?
30. Kết quả có thể được reconcile sau sự cố hệ thống không?

## 33. Sơ đồ ra quyết định

~~~text
                 Có một hành động cần thực hiện
                              |
                              v
             Chỉ xử lý state cục bộ của entity?
                    /                 \
                  Có                 Không
                  |                    |
                  v                    v
        JPA lifecycle callback     Phụ thuộc commit?
        Pre/Post phù hợp             /          \
                                  Không         Có
                                    |            |
                                    v            v
                             Application     Có cần durable
                             service/event   delivery/retry?
                                             /           \
                                           Không          Có
                                             |             |
                                             v             v
                                 AFTER_COMMIT / JTA       Transactional
                                 afterCompletion           Outbox
                                             |             |
                                             v             v
                                      Best-effort      Worker + broker/
                                      follow-up        idempotent consumer
~~~

Đây là sơ đồ lựa chọn hướng giải pháp, không phải một quy tắc cứng cho mọi kiến trúc. Với audit atomic cùng business update, ghi audit **trong cùng transaction** thường hợp lý hơn cả hai nhánh side-effect sau commit.

## 34. Tổng kết

Chìa khóa của bài học là **xác định đúng mốc thời gian**.

~~~text
Entity operation
    |
    v
Managed state changes
    |
    v
Flush / SQL INSERT, UPDATE, DELETE
    |
    +--> @PostPersist / @PostUpdate / @PostRemove
    |         |
    |         +-- Chưa bảo đảm commit!
    |
    v
Transaction completion
    |
    +-----------------------------+
    |                             |
    v                             v
COMMITTED                      ROLLED BACK
    |                             |
    v                             v
AFTER_COMMIT                 Không phát successful
listener / JTA status        commit event
COMMITTED
    |
    v
Nếu cần durable delivery:
  Outbox trong DB transaction
  + worker / retry / idempotency
~~~

Những điều cần nhớ:

- **`@PostPersist`, `@PostUpdate`, `@PostRemove` là callback sau mốc entity**, không phải sau successful transaction commit.
- **`flush()` không phải `commit()`**; callback có thể chạy rồi toàn bộ SQL bị rollback.
- `@PostLoad` liên quan load/refresh, không mang ý nghĩa commit.
- **Spring `@EventListener`** thường xử lý ngay khi publish; **`@TransactionalEventListener(AFTER_COMMIT)`** gắn với commit outcome.
- **JTA `Synchronization.afterCompletion`** cung cấp transaction outcome; chỉ `STATUS_COMMITTED` là committed success.
- Sau commit, lỗi external side effect **không rollback được giao dịch đã hoàn tất**.
- Nếu handler cần DB write mới, phải thiết kế một transaction mới như `REQUIRES_NEW`; đó không còn atomic với giao dịch trước.
- **Transactional outbox** ghi event intent cùng business update và cho phép worker xử lý sau restart, nhưng thường cần **at-least-once + idempotency**.
- Phát **domain events từ application service** nơi biết ý nghĩa nghiệp vụ, không suy mọi business event từ callback cập nhật entity.
- Kiểm thử cần có cả **flush rồi rollback** và **commit thành công**, dùng transaction boundaries thật thay vì chỉ mock listener.

**Một callback báo rằng JPA đã đi qua một mốc thao tác; chỉ transaction outcome mới nói giao dịch đã commit thành công. Khi sự kiện phải sống sót qua cả sự cố tiến trình và retry, hãy biến ý định phát sự kiện thành dữ liệu bền vững trong cùng transaction.**
