# Interceptor, event listener và trường hợp cần cơ chế Hibernate riêng

Khi ứng dụng Java sử dụng JPA/Hibernate, các thao tác `persist()`, `find()`, thay đổi field, `flush()`, `remove()` và `commit()` không chỉ đơn giản là những lời gọi SQL. Hibernate còn quản lý vòng đời entity, dirty checking, cascading, persistence context, thứ tự các hành động SQL và nhiều loại sự kiện nội bộ. Đôi khi ứng dụng cần **quan sát hoặc can thiệp** vào những thời điểm nhất định trong luồng đó.

Ví dụ:

- Gán thông tin audit như thời điểm tạo, thời điểm sửa hoặc người thao tác.
- Theo dõi những entity nào được INSERT/UPDATE/DELETE.
- Kiểm tra một điều kiện kỹ thuật khi Hibernate chuẩn bị ghi entity.
- Thu thập chỉ số về các thao tác ORM.
- Tích hợp một cơ chế mở rộng vào Hibernate ở mức `SessionFactory`.
- Nhận sự kiện collection thay đổi, trong khi JPA callback chỉ cung cấp entity-level lifecycle.
- Phối hợp một module như Hibernate Envers hoặc một extension riêng với các event groups của Hibernate.

Có nhiều cơ chế nghe gần giống nhau nhưng khác đáng kể:

1. **Jakarta Persistence lifecycle callback**: `@PrePersist`, `@PostPersist`, `@PreUpdate`, `@PostUpdate`, `@PreRemove`, `@PostRemove`, `@PostLoad` và `@EntityListeners`. Đây là lựa chọn portable, phù hợp khi chỉ cần làm việc với một entity.
2. **Hibernate `Interceptor`**: API riêng Hibernate để quan sát và, ở những callback cho phép, thay đổi các mảng trạng thái entity trước khi ghi hoặc sau khi đọc.
3. **Hibernate event listener SPI**: đăng ký callback cho từng `EventType`, như `PRE_INSERT`, `POST_UPDATE`, `PRE_COLLECTION_UPDATE`, `PERSIST`, `FLUSH`. Cơ chế này có thể can thiệp sâu vào chuỗi xử lý nội bộ.
4. **Các extension chuyên biệt khác**: `StatementInspector`, `AttributeConverter`, Envers, Hibernate filters, custom types, transaction synchronization, database constraints và transactional outbox.

**Nguyên tắc lựa chọn:** dùng cơ chế ít phụ thuộc Hibernate nhất mà vẫn diễn đạt được yêu cầu. Không nên viết event listener cấp thấp chỉ để gán `createdAt`, và càng không nên dùng `@PostPersist` để gửi một thông báo không thể rollback tới hệ thống khác rồi giả định transaction đã commit.

Bài học trình bày contract và thời điểm thực thi của từng cơ chế, cách đăng ký, cách thay đổi state an toàn, những giới hạn về transaction/reentrancy, trường hợp nên dùng Hibernate SPI và phương án thay thế khi cần bảo đảm nghiệp vụ.

---

## 1. Một mô hình entity để đối chiếu các hook

Giả sử hệ thống quản lý đơn hàng:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "order_number", nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false, precision = 18, scale = 2)
    private BigDecimal total;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public PurchaseOrder(String number, BigDecimal total) {
        this.orderNumber = number;
        this.total = total;
        this.status = OrderStatus.DRAFT;
    }

    public void markPaid() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only DRAFT can become PAID");
        }
        status = OrderStatus.PAID;
    }

    public Long getId() { return id; }
    public OrderStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}

enum OrderStatus {
    DRAFT, PAID, CANCELLED
}
```

Mỗi ví dụ phía dưới **không đồng thời yêu cầu sử dụng tất cả cơ chế**. Ta lần lượt minh họa callback JPA, `Interceptor` và event listener để chọn phương án thích hợp.

Một workflow:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

PurchaseOrder order =
    new PurchaseOrder("PO-001", new BigDecimal("250.00"));

em.persist(order);
order.markPaid();

em.flush();
tx.commit();
```

Những điều cần nhớ:

- `persist()` chuyển entity mới sang managed state; INSERT có thể được lên lịch để chạy khi flush hoặc thực thi sớm tùy ID generator.
- Một entity chỉ bị UPDATE nếu Hibernate xác định state đã thay đổi và cần ghi.
- `flush()` đồng bộ pending actions xuống database trong transaction.
- `commit()` xác nhận transaction; **flush trước commit không có nghĩa đã commit**.
- Callback có thể được gọi ở giai đoạn `persist`, dirty checking/flush hoặc khi SQL được thực thi, tùy loại hook.

## 2. Sơ đồ các lớp extension point

```text
Application service / domain model
           |
           v
JPA EntityManager / Hibernate Session
           |
           +---- JPA lifecycle callbacks
           |       @PrePersist / @PreUpdate / @PostLoad ...
           |
           +---- Hibernate Interceptor
           |       onPersist / onFlushDirty / onLoad ...
           |
           +---- Hibernate event system
           |       PERSIST / PRE_INSERT / POST_INSERT
           |       PRE_UPDATE / POST_UPDATE / collections ...
           |
           +---- ActionQueue / SQL generation
           |       INSERT / UPDATE / DELETE
           |
           +---- StatementInspector
           |       Inspect SQL text before preparation
           |
           v
        JDBC / Database
           |
           v
      Transaction commit / rollback
```

Sơ đồ này để phân loại trách nhiệm, **không cam kết thứ tự gọi tuyệt đối giữa mọi JPA callback và Hibernate event hook**. Thứ tự chi tiết phụ thuộc event type, entity lifecycle, cascade, flush mode, generator, phiên bản Hibernate và các listeners khác được cài đặt.

Đặc biệt, **“Post” trong tên `PostInsertEventListener` không có nghĩa “post commit”**. Nó thường có nghĩa sau thao tác SQL INSERT liên quan. Transaction có thể vẫn đang mở và rollback.

## 3. Chọn cơ chế bằng một bảng ngắn

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Gán `createdAt`, `updatedAt` cho một entity | `@PrePersist`, `@PreUpdate`; hoặc timestamp generation của Hibernate | Ít phụ thuộc SPI |
| Chuẩn hóa giá trị của một field | Domain method, `AttributeConverter`, JPA callback tùy ngữ nghĩa | Tránh xử lý array state cấp thấp |
| Kiểm tra quy tắc nghiệp vụ khi gọi command | Service/domain + Bean Validation + DB constraints | Có đủ business context |
| Quan sát state array trước ORM INSERT/UPDATE | `Interceptor` | Có `state`, `propertyNames`, `types` |
| Theo dõi một event Hibernate rất cụ thể | Event listener SPI | Có `EventType`/`Event` tương ứng |
| Theo dõi thay đổi collection membership | Collection event listener | JPA callbacks không cung cấp trực tiếp collection SPI |
| Ghi lịch sử revision entity | Hibernate Envers | Giải pháp audit chuyên dụng |
| Inspect SQL text | `StatementInspector` | Đúng extension point của SQL layer |
| Thay cách bind/map một Java type | `AttributeConverter`, BasicType/UserType | Type conversion khác lifecycle event |
| Đảm bảo email duy nhất | Database UNIQUE constraint | Bảo vệ mọi writers và concurrency |
| Gửi message sau khi DB commit an toàn | Transactional outbox + publisher | Không mất event khi process crash |
| Lọc tenant/quyền truy cập | Hibernate multi-tenancy/filter hoặc query/security layer | Listener không thay authorization |
| Thay chuỗi xử lý ORM rất sâu | Hibernate event SPI/custom listener | Chỉ khi thật sự cần và có tests |

## 4. Jakarta Persistence lifecycle callbacks: lựa chọn đầu tiên

Jakarta Persistence định nghĩa:

```java
@PrePersist
@PostPersist
@PreUpdate
@PostUpdate
@PreRemove
@PostRemove
@PostLoad
```

Ví dụ gán timestamps tại entity:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    public void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    public void onUpdate() {
        updatedAt = Instant.now();
    }
}
```

Đây là một **biến thể rút gọn của entity ví dụ**, không phải đoạn bổ sung các field trùng lặp vào class đã trình bày ở mục 1.

Ưu điểm:

- Thuộc Jakarta Persistence, ít lock-in hơn Hibernate SPI.
- Logic nằm cạnh entity/lifecycle cần xử lý.
- Không cần đăng ký `Integrator` hoặc nắm cấu trúc `EventListenerRegistry`.
- Dễ kiểm thử bằng một transaction thực và flush.

Nhược điểm:

- Không có các arrays `currentState`/`previousState` từ Hibernate.
- Không bao quát mọi hoạt động JDBC ngoài ORM.
- Không có hook “sau transaction commit thành công” chỉ bằng `@PostPersist`.
- Không phù hợp cho hành động tốn tài nguyên, query lồng hoặc publish message đồng bộ.

### 4.1. `@PreUpdate` không chạy khi entity không đổi

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);
em.flush();
```

Nếu entity không dirty, Hibernate thường không phát UPDATE, do đó `@PreUpdate` không được gọi chỉ vì ứng dụng gọi `flush()`.

Đừng dùng `@PreUpdate` làm “heartbeat” bắt buộc mỗi lần request chạm vào entity.

### 4.2. `@PostPersist` không đồng nghĩa commit

```text
persist/order INSERT
       |
       v
@PostPersist có thể chạy
       |
       v
Các SQL khác trong transaction
       |
       v
Transaction có thể ROLLBACK
```

Nếu callback gửi email hoặc message tới broker ngay:

```java
@PostPersist
void onPersisted() {
    emailClient.send(...);
}
```

thì email có thể đã gửi mặc dù DB rollback. Callback không phải một transactional message delivery system.

### 4.3. `@PostLoad` chỉ khi entity được load/hydrate

Nếu `em.find()` trả một entity **đã managed trong L1**, Hibernate không bắt buộc thực hiện lại load/hydration, vì thế đừng dùng `@PostLoad` như logging hook cho **mọi lời gọi find**.

## 5. Tách callbacks bằng `@EntityListeners`

Khi audit timestamps dùng cho nhiều entities, có thể tạo listener theo JPA:

```java
public interface TimeStamped {
    void markCreated(Instant when);
    void markUpdated(Instant when);
}
```

```java
public class TimestampEntityListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        if (entity instanceof TimeStamped stamped) {
            Instant now = Instant.now();
            stamped.markCreated(now);
            stamped.markUpdated(now);
        }
    }

    @PreUpdate
    public void beforeUpdate(Object entity) {
        if (entity instanceof TimeStamped stamped) {
            stamped.markUpdated(Instant.now());
        }
    }
}
```

```java
@EntityListeners(TimestampEntityListener.class)
@Entity
public class Invoice implements TimeStamped {
    // Fields, mapping và implementations...
}
```

`TimeStamped` là interface ứng dụng; các method implementer phải thực sự cập nhật những persistent fields được mapping.

Có thể dùng `@MappedSuperclass` để chia sẻ mapping và callbacks nếu nhiều entity dùng cùng contract.

### 5.1. Những giới hạn của callback chuẩn

Callback không phải vị trí tốt để:

- Gọi `EntityManager` và thực hiện query phức tạp.
- Truy cập và lazy-initialize collection/proxy không cần thiết.
- Thay đổi nhiều entities khác.
- Tạo giao dịch nested.
- Gửi network request cần reliability.
- Thực thi logic business cần đầy đủ request/authorization context.

Các hạn chế và quy tắc portable cụ thể theo Jakarta Persistence spec; nếu một provider tình cờ cho phép thao tác phức tạp trong callback, không nên coi hành vi đó là contract portable.

## 6. Hibernate `Interceptor` là gì?

`org.hibernate.Interceptor` là extension point riêng Hibernate. Nó cho phép ứng dụng nhận callback về lifecycle entity và collection, kiểm tra hoặc trong một số callback thay đổi **persistent state arrays** mà Hibernate đang xử lý.

Một interface tổng quát:

```java
import org.hibernate.Interceptor;

public class MyInterceptor implements Interceptor {
    // Chỉ override các callback cần dùng.
}
```

Trong Hibernate 6/7 hiện đại, nhiều methods của `Interceptor` có default implementation, nên có thể implement trực tiếp và override ít methods.

Một số tài liệu cũ sử dụng:

```java
extends EmptyInterceptor
```

hoặc:

```java
onSave(...)
onDelete(...)
```

Trong Hibernate 6.6+ các callback kiểu `onSave`/`onDelete` đã được đánh dấu deprecated, hướng API mới cho stateful sessions là `onPersist`/`onRemove`. **Đừng sao chép signature từ Hibernate 5 mà không kiểm tra Javadoc của version hiện tại.**

### 6.1. Một Interceptor có thể dùng để làm gì?

- Quan sát entity trước khi được persist.
- Quan sát khi Hibernate phát hiện entity dirty ở flush.
- Nhận state trước khi inject vào entity lúc load.
- Nhận callbacks collection create/update/remove.
- Định nghĩa một số heuristics về transient/detached state.
- Theo dõi transaction begin/before completion/after completion ở mức Hibernate transaction facade.

Nó không phải framework event bus nghiệp vụ, không tự bảo đảm event delivery và không trực tiếp bảo vệ các câu SQL được ứng dụng khác thực thi.

## 7. `onPersist`: inspect state trước khi entity được persist

Ví dụ không sửa state, chỉ đếm những lần Hibernate xử lý `PurchaseOrder` trong callback:

```java
import org.hibernate.Interceptor;
import org.hibernate.type.Type;

import java.util.concurrent.atomic.LongAdder;

public final class OrderCountingInterceptor
        implements Interceptor {

    private final LongAdder persistAttempts = new LongAdder();

    @Override
    public boolean onPersist(
            Object entity,
            Object id,
            Object[] state,
            String[] propertyNames,
            Type[] types
    ) {
        if (entity instanceof PurchaseOrder) {
            persistAttempts.increment();
        }

        return false; // Không sửa mảng state.
    }

    public long getPersistAttempts() {
        return persistAttempts.sum();
    }
}
```

Điều quan trọng:

- `state[i]`, `propertyNames[i]`, `types[i]` tham chiếu **cùng một persistent property**.
- Callback có thể xảy ra trước khi actual SQL INSERT hoàn tất.
- `id` có thể chưa phản ánh generated identifier cuối cùng trong mọi mapping/strategy.
- Counter đo **callback invocations**, không phải số committed rows.
- Nếu một transaction rollback, counter không tự giảm.
- Nếu interceptor dùng chung giữa sessions, mọi state mutable cần thread-safe.

### 7.1. Tại sao `return false`?

Trong callback như `onPersist`, giá trị trả về cho Hibernate biết **interceptor đã chỉnh sửa state array hay chưa**:

- `false`: không có thay đổi state do interceptor.
- `true`: có thay đổi trong array mà Hibernate cần áp dụng.

Nó **không phải** kết quả “cho phép/không cho phép INSERT”. Đừng nhầm boolean của Interceptor với boolean veto trong một số `Pre*EventListener`.

## 8. `onFlushDirty`: quan sát entity thay đổi ở flush

Callback:

```java
@Override
public boolean onFlushDirty(
        Object entity,
        Object id,
        Object[] currentState,
        Object[] previousState,
        String[] propertyNames,
        Type[] types
) {
    // Inspect currentState/previousState.
    return false;
}
```

Nó được gọi khi Hibernate phát hiện object dirty trong quá trình flush theo lifecycle của interceptor.

Một implementation quan sát property `status`:

```java
import org.hibernate.Interceptor;
import org.hibernate.type.Type;

public final class StatusChangeInterceptor
        implements Interceptor {

    @Override
    public boolean onFlushDirty(
            Object entity,
            Object id,
            Object[] currentState,
            Object[] previousState,
            String[] propertyNames,
            Type[] types
    ) {
        if (!(entity instanceof PurchaseOrder)) {
            return false;
        }

        int index = indexOf(propertyNames, "status");
        if (index < 0) {
            return false;
        }

        Object before = previousState == null
            ? null
            : previousState[index];
        Object after = currentState[index];

        if (!java.util.Objects.equals(before, after)) {
            // Log/metric kỹ thuật tối giản tại đây;
            // không gửi network request và không gọi Session.
        }

        return false;
    }

    private static int indexOf(String[] names, String wanted) {
        for (int i = 0; i < names.length; i++) {
            if (wanted.equals(names[i])) return i;
        }
        return -1;
    }
}
```

Chú ý:

- `previousState` có thể null trong một số trường hợp.
- Không dùng chỉ số cố định như `currentState[2]` nếu không có mapping contract rõ.
- Không sửa `previousState`; Javadoc khuyến cáo mạnh việc không can thiệp previous snapshot.
- `onFlushDirty` không cam kết transaction commit thành công.
- Nếu cần audit *chính xác các bản ghi đã commit*, một metric trong callback chưa đủ.

## 9. Khi cần sửa `state[]` trong Interceptor

Hibernate `onPersist` và `onFlushDirty` cho phép sửa những giá trị trong state arrays rồi trả `true`, miễn là kiểu và mapping tương thích.

Ví dụ cho field `updatedAt`:

```java
public final class UpdatedAtInterceptor
        implements org.hibernate.Interceptor {

    @Override
    public boolean onFlushDirty(
            Object entity,
            Object id,
            Object[] currentState,
            Object[] previousState,
            String[] propertyNames,
            org.hibernate.type.Type[] types
    ) {
        if (!(entity instanceof PurchaseOrder)) {
            return false;
        }

        for (int i = 0; i < propertyNames.length; i++) {
            if ("updatedAt".equals(propertyNames[i])) {
                currentState[i] = java.time.Instant.now();
                return true; // Đã sửa currentState.
            }
        }
        return false;
    }
}
```

Theo contract của Hibernate, `currentState` đã sửa được dùng trong flush và được propagate vào entity tương ứng.

### 9.1. Có nên dùng Interceptor chỉ để set timestamp?

Thông thường **không cần**. Chọn một trong các cách đơn giản hơn:

```java
@PrePersist
@PreUpdate
```

hoặc tính năng timestamp generation Hibernate:

```java
@CreationTimestamp
private Instant createdAt;

@UpdateTimestamp
private Instant updatedAt;
```

Các annotation của Hibernate là `org.hibernate.annotations.CreationTimestamp` và `UpdateTimestamp`; semantics (VM/DB source, timezone, timing) cần kiểm tra theo Hibernate version.

Dùng Interceptor khi đã có lý do rõ ràng về cross-cutting behavior hoặc cần state arrays mà callback JPA không cung cấp. Không xây một interceptor phức tạp chỉ để tránh vài dòng `@PreUpdate`.

### 9.2. Tránh mâu thuẫn nhiều cơ chế

Nếu cùng một field `updatedAt` được sửa bởi:

- JPA `@PreUpdate`.
- `@UpdateTimestamp`.
- Interceptor `onFlushDirty`.
- Database trigger.

thì kết quả phụ thuộc nhiều thời điểm và có thể không ổn định. Chọn **một nơi sở hữu** việc tạo timestamp hoặc xác định contract/precedence cụ thể rồi test.

## 10. `onLoad` và trạng thái trước khi hydrate entity

Signature:

```java
@Override
public boolean onLoad(
        Object entity,
        Object id,
        Object[] state,
        String[] propertyNames,
        org.hibernate.type.Type[] types
) {
    return false;
}
```

Hibernate gọi ở giai đoạn state được load trước khi các giá trị được inject vào entity; theo Javadoc, `entity` có thể là một instance **chưa được khởi tạo field state đầy đủ**.

Vì vậy không viết:

```java
if (entity instanceof Customer customer) {
    customer.getAddress().getCity(); // Có thể chưa init/lazy.
}
```

trong `onLoad`.

Nếu cần xử lý một scalar field trước hydration, làm việc với `state` và property metadata theo contract của interceptor. Nếu chỉ cần tính một thuộc tính transient sau load, JPA `@PostLoad` có thể đơn giản hơn.

### 10.1. `onLoad` không bảo đảm mọi lần `find()` đều gọi

Một entity đã managed trong L1 có thể được trả lại trực tiếp. Một query cũng có thể chỉ trả DTO/scalars. Do đó `onLoad` không phải hook cho mọi operation đọc của ứng dụng.

## 11. `onRemove`, collection hooks và các callback khác

Một số methods đáng biết:

```java
onRemove(entity, id, state, propertyNames, types)
onCollectionRecreate(collection, key)
onCollectionUpdate(collection, key)
onCollectionRemove(collection, key)

preFlush(iterator)
postFlush(iterator)

beforeTransactionCompletion(tx)
afterTransactionCompletion(tx)
```

Giới hạn:

- `onRemove` có mặt ở lifecycle ORM, không phản ánh mọi raw SQL DELETE/DB cascade.
- Collection callback nói về thay đổi collection được Hibernate xử lý, không bảo đảm mỗi thay đổi quan hệ vật lý đều kích hoạt cùng một event.
- `preFlush` và `postFlush` liên quan flush; có thể có nhiều flush trong một transaction.
- Transaction callback có thể chạy cho commit **hoặc rollback**; phải kiểm tra trạng thái nếu cần.
- Không gọi một `Session` từ callback của Interceptor và không làm lazy initialization theo cảnh báo trong Javadoc Hibernate.

### 11.1. `findDirty` không phải nơi tối ưu tùy tiện

Interceptor có:

```java
int[] findDirty(
    Object entity,
    Object id,
    Object[] currentState,
    Object[] previousState,
    String[] propertyNames,
    Type[] types
)
```

Ý nghĩa kết quả:

- `null`: sử dụng dirty checking mặc định của Hibernate.
- Mảng rỗng: khẳng định entity **không dirty** theo callback.
- Mảng property indices: khẳng định những properties tương ứng dirty.

Một `findDirty` custom sai có thể khiến Hibernate **bỏ qua UPDATE thật sự cần thiết** hoặc UPDATE dư thừa. Hầu hết ứng dụng nên để mặc định; bytecode enhancement/dynamic update và ORM dirty checking đã có cơ chế chuyên dụng.

## 12. Scope của Interceptor: một Session hay một SessionFactory?

Có hai mô hình quan trọng.

**SessionFactory-scoped interceptor**:

```text
SessionFactory
  └─ Interceptor instance S (shared)
       ├─ Session A
       ├─ Session B
       └─ Session C
```

**Session-scoped interceptor**:

```text
SessionFactory
  ├─ Session A -> Interceptor A
  ├─ Session B -> Interceptor B
  └─ Session C -> Interceptor C
```

Một shared interceptor có thể nhận callbacks đồng thời từ nhiều request threads/sessions. Không lưu biến như `currentUserId` trong field instance trừ khi thiết kế thread-safe và có scoping đúng.

### 12.1. Cấu hình Interceptor theo properties

Trong Hibernate 6/7 hiện đại có các settings:

```properties
hibernate.session_factory.interceptor=com.example.persistence.OrderCountingInterceptor
```

và:

```properties
hibernate.session_factory.session_scoped_interceptor=com.example.persistence.OrderCountingInterceptor
```

- Setting shared có thể nhận instance/class/class name tùy bootstrap.
- Session-scoped nhận class/class name hoặc supplier để tạo interceptor riêng cho từng Session.
- Tránh cấu hình cả hai mà không xác định precedence và expected behavior.
- Cần constructor/DI integration thích hợp để Hibernate tạo được instance.

Trong ứng dụng Spring Boot, có thể truyền property qua:

```properties
spring.jpa.properties.hibernate.session_factory.interceptor=\
com.example.persistence.OrderCountingInterceptor
```

Đây là property cách viết minh họa trong file `.properties`; thực tế đặt trên **một dòng**, hoặc dùng cách xuống dòng hợp lệ của properties format.

### 12.2. Cấu hình qua Hibernate `SessionFactoryBuilder`

Khi bootstrap Hibernate trực tiếp:

```java
SessionFactory sessionFactory = metadata
    .getSessionFactoryBuilder()
    .applyInterceptor(new OrderCountingInterceptor())
    .build();
```

Có thể cấu hình interceptor riêng khi mở session qua `SessionBuilder.interceptor(...)`, nếu use case đòi hỏi session-level customization.

Không trộn nhiều cách cài đặt trùng nhau nếu không rõ interceptor nào đang thực sự active.

## 13. Vì sao shared interceptor cần thread-safe?

Ví dụ sai:

```java
public class UnsafeInterceptor implements Interceptor {

    private Long currentOrderId;

    @Override
    public boolean onPersist(
            Object entity, Object id,
            Object[] state, String[] propertyNames, Type[] types
    ) {
        currentOrderId = (Long) id;
        return false;
    }
}
```

Nếu một instance được dùng bởi nhiều sessions:

```text
Thread A: currentOrderId = 100
Thread B: currentOrderId = 200
Thread A: đọc currentOrderId -> 200 (sai request)
```

Đừng giữ transaction/request context trong mutable fields của shared interceptor.

Các lựa chọn:

- Logic stateless.
- Atomic/LongAdder cho counters kỹ thuật aggregate.
- Một interceptor instance theo Session khi thực sự cần state riêng.
- Truyền correlation/actor context qua một mechanism có lifecycle rõ ràng.
- Giữ business context ở application service rồi dùng explicit arguments trong domain methods.

`ThreadLocal` không tự an toàn trong thread pools và asynchronous flows; nếu dùng phải cleanup, và cũng không làm transaction events đáng tin cậy hơn.

## 14. Hibernate event listener SPI là gì?

Ngoài Interceptor, Hibernate có event system với các loại sự kiện riêng:

```java
import org.hibernate.event.spi.EventType;
```

Một số groups quan trọng:

| Event group | Khi nào thường liên quan |
| --- | --- |
| `PERSIST` | ORM xử lý yêu cầu persist/cascade |
| `MERGE` | Xử lý merge detached state |
| `DELETE` | Xử lý yêu cầu remove/delete |
| `PRE_INSERT` | Ngay trước thao tác INSERT của entity |
| `POST_INSERT` | Sau INSERT của entity |
| `PRE_UPDATE` | Trước SQL UPDATE của entity |
| `POST_UPDATE` | Sau SQL UPDATE của entity |
| `PRE_DELETE` | Trước SQL DELETE |
| `POST_DELETE` | Sau SQL DELETE |
| `PRE_LOAD`, `POST_LOAD` | Giai đoạn load entity |
| `FLUSH`, `AUTO_FLUSH`, `FLUSH_ENTITY` | Flush/dirty checking processing |
| `PRE_COLLECTION_RECREATE/UPDATE/REMOVE` | Collection operations trước thực thi |
| `POST_COLLECTION_RECREATE/UPDATE/REMOVE` | Collection operations sau thực thi |
| `POST_COMMIT_INSERT/UPDATE/DELETE` | Các event groups liên quan transaction-completion hooks |

**Không nên giả định tên gần giống nhau có cùng callback signature**. `PersistEventListener` không giống `PreInsertEventListener`; `PostInsertEventListener` cũng không phải `PostCommitInsertEventListener`.

## 15. Khi nào chọn `PRE_INSERT` thay vì `PERSIST`?

Phân biệt:

```text
em.persist(entity)
      |
      v
PERSIST event handling
      |
      v
Entity trở thành managed / ActionQueue
      |
      v
Flush hoặc INSERT sớm nếu generator yêu cầu
      |
      v
PRE_INSERT
      |
      v
JDBC INSERT
      |
      v
POST_INSERT
      |
      v
Có thể tiếp tục transaction rồi COMMIT/ROLLBACK
```

Đây là luồng khái niệm; cascade và implementation có thể thêm nhiều bước.

Nếu cần biết **application đã yêu cầu persist**, `PERSIST` nằm gần lifecycle operation hơn.

Nếu cần observe **SQL INSERT sắp thực thi**, `PRE_INSERT` là hook thích hợp.

Nếu cần quan sát **SQL INSERT đã thực thi**, `POST_INSERT` phù hợp hơn — nhưng vẫn chưa chứng minh transaction đã commit.

## 16. Một `PreInsertEventListener` đơn giản và an toàn

Ví dụ chỉ thu thập số lần INSERT chuẩn bị thực thi:

```java
package com.example.persistence;

import com.example.domain.PurchaseOrder;
import org.hibernate.event.spi.PreInsertEvent;
import org.hibernate.event.spi.PreInsertEventListener;

import java.util.concurrent.atomic.LongAdder;

public final class OrderPreInsertListener
        implements PreInsertEventListener {

    private final LongAdder observed = new LongAdder();

    @Override
    public boolean onPreInsert(PreInsertEvent event) {
        if (event.getEntity() instanceof PurchaseOrder) {
            observed.increment();
        }

        return false;
    }

    public long observedCount() {
        return observed.sum();
    }
}
```

Điểm quan trọng: `PreInsertEventListener.onPreInsert()` trả **`true` nếu veto thao tác INSERT**, `false` để cho phép tiếp tục theo contract Hibernate tương ứng.

Điều đó trái với semantics boolean của `Interceptor.onPersist()`, trong đó `true` nghĩa **state array đã được sửa**.

### 16.1. Không veto INSERT chỉ để “bỏ qua dữ liệu không hợp lệ”

Ví dụ:

```java
@Override
public boolean onPreInsert(PreInsertEvent event) {
    return isInvalid(event); // TRUE -> veto
}
```

có thể để lại entity lifecycle và object graph ở tình trạng không như application kỳ vọng, vì ứng dụng đã gọi persist nhưng SQL lại bị chặn ở tầng rất thấp.

Với business validation, ưu tiên:

- Domain method validation.
- Bean Validation.
- Database `NOT NULL`, `CHECK`, `UNIQUE`, FK.
- Application service reject trước `persist()`.

Nếu event veto là requirement thực sự của một Hibernate extension, phải test cẩn thận cả persistence context, flush order, cascades, generated IDs và transaction behavior.

### 16.2. Listener cũng không đếm committed rows

Một `PRE_INSERT` hook chạy và tăng counter không có nghĩa INSERT sẽ commit. DB có thể ném constraint error; transaction có thể rollback. Counter nên có tên `observedAttempts`, không phải `successfullyCommittedOrders`.

## 17. `PostInsertEventListener`: sau SQL nhưng chưa chắc sau commit

Một sample:

```java
package com.example.persistence;

import com.example.domain.PurchaseOrder;
import org.hibernate.event.spi.PostInsertEvent;
import org.hibernate.event.spi.PostInsertEventListener;

public final class OrderPostInsertListener
        implements PostInsertEventListener {

    @Override
    public void onPostInsert(PostInsertEvent event) {
        if (event.getEntity() instanceof PurchaseOrder order) {
            // Có thể ghi telemetry kỹ thuật ít tốn chi phí.
            // Không publish business message ra ngoài DB tại đây.
        }
    }
}
```

`requiresPostCommitHandling(EntityPersister)` có default implementation trên các Hibernate versions hiện đại; nếu version cũ yêu cầu override, dùng Javadoc của version đang triển khai.

`onPostInsert` không phải một callback after-commit. SQL đã chạy trong transaction nhưng một lỗi ở action tiếp theo có thể làm transaction rollback.

### 17.1. “INSERT đã thực thi” vẫn có thể rollback

```text
SQL INSERT order -> thành công
POST_INSERT listener -> chạy
SQL INSERT outbox? -> lỗi UNIQUE
TRANSACTION ROLLBACK -> order không được commit
```

Nếu listener đã gửi message đến Kafka/HTTP trước rollback, hệ thống ngoài có thể tin có order không tồn tại.

## 18. Các event groups POST_COMMIT

Hibernate có các groups:

```java
EventType.POST_COMMIT_INSERT
EventType.POST_COMMIT_UPDATE
EventType.POST_COMMIT_DELETE
```

và các listener interfaces tương ứng, ví dụ `PostCommitInsertEventListener`. Callback/registration yêu cầu xem chính xác contract `onPostInsert`, `onPostInsertCommitFailed`, `requiresPostCommitHandling(...)` của Hibernate version.

Cơ chế này phù hợp với một số extension cần nhận transaction outcome, nhưng cần xét:

- Có session/transaction thực sự của Hibernate phù hợp không?
- Có phát sinh callbacks cho failed commits không?
- Logic xử lý callback có thể chạy trước process crash không?
- Có transaction broker/network khác không?
- Event đã được persist/durable ở đâu?
- Có retry/idempotency khi việc publish thất bại không?

**Post-commit hook nội bộ không phải một message queue bền vững.** Nó không thể tự bảo đảm delivery nếu JVM crash ngay sau DB commit hoặc broker mất kết nối.

## 19. Đăng ký listeners bằng `EventListenerRegistry`

Hibernate quản lý event handlers theo `EventType`.

```java
import org.hibernate.event.service.spi.EventListenerRegistry;
import org.hibernate.event.spi.EventType;
```

Các thao tác quan trọng:

```java
registry.appendListeners(
    EventType.PRE_INSERT,
    new OrderPreInsertListener()
);

registry.prependListeners(
    EventType.POST_INSERT,
    new OrderPostInsertListener()
);

// Có thể thay toàn bộ listeners của một group:
registry.setListeners(EventType.PRE_INSERT, listener);
```

Khác nhau:

| API | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `appendListeners(type, listener)` | Thêm vào cuối group | Ít can thiệp hơn, vẫn cần hiểu thứ tự |
| `prependListeners(type, listener)` | Thêm vào đầu group | Listener chạy trước các handlers khác |
| `setListeners(type, listener)` | **Thay thế** listeners trong group | Có thể làm mất default behavior quan trọng |
| Duplication strategy | Quy định cách nhận diện/tránh listener trùng | Phải cấu hình nhất quán |

### 19.1. Không `setListeners()` chỉ để thêm một listener

Một event group có thể đã chứa default Hibernate listener, Envers listener, validation listener hoặc extension khác. Thay thế group có thể làm mất cascade, persistence behavior hoặc tích hợp đã hoạt động.

**Mặc định ưu tiên `appendListeners()`** nếu chỉ quan sát một event, và xác định thứ tự nếu business yêu cầu. Chỉ replace default listeners khi thực sự phát triển một Hibernate engine integration và hiểu toàn bộ contract.

## 20. Đăng ký qua `Integrator`

Một cách phổ biến và được Hibernate tài liệu hóa là dùng `org.hibernate.integrator.spi.Integrator`.

Ví dụ cho Hibernate 7.1-style API:

```java
package com.example.persistence;

import org.hibernate.boot.Metadata;
import org.hibernate.boot.spi.BootstrapContext;
import org.hibernate.engine.spi.SessionFactoryImplementor;
import org.hibernate.event.spi.EventType;
import org.hibernate.integrator.spi.Integrator;

public final class OrderEventIntegrator implements Integrator {

    @Override
    public void integrate(
            Metadata metadata,
            BootstrapContext bootstrapContext,
            SessionFactoryImplementor sessionFactory
    ) {
        var registry =
            sessionFactory.getEventListenerRegistry();

        registry.appendListeners(
            EventType.PRE_INSERT,
            new OrderPreInsertListener()
        );

        registry.appendListeners(
            EventType.POST_INSERT,
            new OrderPostInsertListener()
        );
    }
}
```

`Integrator` được gọi trong quá trình bootstrap SessionFactory. Tài liệu Hibernate lưu ý instance SessionFactory được truyền vào **chưa hoàn tất initialization** khi `integrate()` chạy, vì vậy không dùng nó để thực thi query/business transaction tùy tiện.

Trong những Hibernate 6.x variants, cách truy cập `EventListenerRegistry` có thể là qua service registry của SessionFactory. Chọn **Javadoc đúng version**; code ví dụ theo Hibernate 7.1 và API hiện đại, không phải một adapter hỗ trợ mọi major release.

### 20.1. Java ServiceLoader

Tạo file:

```text
src/main/resources/META-INF/services/org.hibernate.integrator.spi.Integrator
```

Nội dung là fully qualified class name:

```text
com.example.persistence.OrderEventIntegrator
```

Nếu có nhiều integrators, mỗi class name một dòng.

Điều kiện:

- File được đóng gói vào runtime classpath/JAR.
- Class thực sự implements `Integrator`.
- Constructor có thể được ServiceLoader tạo.
- Không có lỗi classloader/module permissions.
- Không bị merge/shading mất service descriptor khi đóng gói fat JAR.

**Chỉ tạo class Java mà không đăng ký ServiceLoader thường chưa đủ** để Hibernate tự phát hiện extension.

## 21. Spring Boot và dependency injection cho listener

`Integrator` do Hibernate ServiceLoader khởi tạo không mặc nhiên là một Spring bean đã được autowire.

Ví dụ cần tránh:

```java
public class OrderPreInsertListener
        implements PreInsertEventListener {

    @Autowired
    private MessagePublisher publisher; // Không chắc được inject.
}
```

Nếu listener được khởi tạo trực tiếp bằng `new` trong Integrator, Spring sẽ không tự inject field này.

Các hướng tích hợp:

- Giữ listener stateless và không phụ thuộc Spring services.
- Dùng cơ chế Spring/Hibernate bootstrap customization được Spring Boot hỗ trợ trong version đó để truyền dependencies.
- Tạo một Spring-managed contributor/Integrator integration theo lifecycle chuẩn, không dùng static ApplicationContext holder.
- Để logic publish event ở service layer thay vì listener.
- Kiểm thử trong **Spring Boot application context thực**, không chỉ unit test `new Listener()`.

Nếu có nhiều EntityManagerFactory, cần đăng ký listener đúng factory, tránh listener chạy nhầm database/module.

### 21.1. Không đăng ký listener sau khi factory đã phục vụ traffic

Event listeners thường được cấu hình lúc bootstrap. Không tự thay đổi event listener registry trong lúc các Sessions đang chạy để phục vụ một request, vì thứ tự/consistency/thread safety có thể không được bảo đảm.

## 22. Event ordering và tương tác với listeners khác

Giả sử có ba listeners trong `PRE_INSERT`:

```text
Default Hibernate handler
Audit listener
Validation listener
```

Thứ tự có thể ảnh hưởng:
- State đã bị chỉnh sửa trước đó.
- Có exception/veto hay không.
- Logging/metrics.
- Việc các extensions cùng yêu cầu can thiệp.

`prependListeners` và `appendListeners` thể hiện vị trí tương đối trong group. Nhưng không dựa vào thứ tự giữa **các event groups khác nhau** như một contract bất biến nếu chưa được tài liệu hóa và kiểm chứng cho version.

Nếu phải xử lý thứ tự, cân nhắc:
1. Gộp phần liên quan trong một service/domain operation.
2. Dùng listener ordering được registry hỗ trợ.
3. Tránh nhiều listeners chỉnh cùng một property.
4. Test với chính Hibernate version và extensions đang chạy.
5. Đừng replace default listeners chỉ để đổi thứ tự một observer.

## 23. Tránh truy vấn đệ quy và tái nhập Session

Một lỗi nguy hiểm là từ event listener lại dùng chính Session để `persist`, `flush`, `find` hoặc query một graph khác.

Ví dụ:

```java
@Override
public boolean onPreInsert(PreInsertEvent event) {
    // Không nên:
    // event.getSession().persist(new AuditLog(...));
    return false;
}
```

Sự kiện đang xảy ra **bên trong quá trình flush/ActionQueue**. Re-enter Session có thể:

- Gây nested flush/recursion.
- Thay đổi ActionQueue trong lúc đang duyệt.
- Dẫn tới `ConcurrentModificationException` hoặc state inconsistent.
- Tạo các event lặp vô hạn (AuditLog insert lại kích AuditLog listener).
- Gây SQL order/constraint bugs khó xác định.

Hibernate Javadoc `Interceptor` đặc biệt cảnh báo **không được gọi Session từ interceptor callback** và không lazy-initialize collection/proxy trong đó. Với event SPI, dù có `event.getSession()`, cũng không nên xem đó là giấy phép cho thao tác ORM tùy ý.

### 23.1. Nếu cần ghi audit row thì làm thế nào?

Các phương án thường tốt hơn:

- **Hibernate Envers** cho revision audit được hỗ trợ.
- **Service layer** gọi `em.persist(order)` và `em.persist(auditEntry)` trong cùng transaction.
- **Transactional outbox** cho domain events.
- **Database trigger** nếu muốn bao quát SQL từ mọi writers.
- Một Hibernate SPI integration chuyên dụng chỉ khi đã có hiểu biết sâu về Event processing và test version-specific.

Không biến generic `PreInsertEventListener` thành một “repository” có thể chạy mọi nghiệp vụ trong callback.

## 24. Ghi audit history: chọn Envers hay listener tự viết?

Yêu cầu: lưu các phiên bản trước/sau của `PurchaseOrder` mỗi lần dữ liệu thay đổi.

Hibernate Envers được thiết kế cho entity revision history:

```java
import org.hibernate.envers.Audited;

@Entity
@Audited
public class PurchaseOrder {
    @Id
    private Long id;
    // ...
}
```

Envers thường tạo/đòi hỏi audit tables như `purchase_orders_AUD` và revision metadata table theo naming/configuration; schema migration cần quản lý tương ứng trong dự án migration-owned.

Ưu điểm:
- Có cấu trúc audit/revision chuyên dụng.
- Tích hợp với Hibernate entity changes.
- Hỗ trợ truy vấn revision history theo API Envers.
- Tránh tự duy trì nhiều event listeners cho INSERT/UPDATE/DELETE.

Giới hạn:
- Không tự audit mọi SQL UPDATE từ process khác ngoài Hibernate.
- Bulk HQL/native SQL có thể bypass normal entity lifecycle.
- Cần hiểu relation auditing, performance, retention và DB schema.
- Không thay thế compliance audit/security event pipeline toàn hệ thống nếu cần nguồn dữ liệu khác ORM.

Nếu yêu cầu audit **mọi writer**, có thể cần database triggers/CDC, không chỉ Envers.

## 25. Domain event và transactional outbox

Yêu cầu: khi order được PAID, hệ thống phải phát `OrderPaid` sang service fulfillment **chỉ khi DB commit thành công**, có retry nếu broker tạm lỗi.

Không nên:

```java
@PostUpdate
void afterUpdate() {
    broker.publish(new OrderPaid(...));
}
```

Hoặc:

```java
@Override
public void onPostUpdate(PostUpdateEvent event) {
    broker.publish(...);
}
```

Vì nếu transaction rollback, message có thể đã được gửi. Nếu chỉ dùng after-commit callback, process crash ngay sau commit có thể làm mất message.

### 25.1. Transactional outbox pattern

Trong một transaction:

```java
@Transactional
public void payOrder(Long orderId) {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, orderId);

    order.markPaid();

    OutboxMessage message = OutboxMessage.orderPaid(
        orderId,
        java.util.UUID.randomUUID().toString()
    );

    entityManager.persist(message);
}
```

`OutboxMessage` là entity riêng chứa:

```text
id / event_id
aggregate_type
aggregate_id
event_type
payload
created_at
published_at / delivery_status
```

Khi commit thành công, **order update và outbox insert** cùng được commit. Một background publisher đọc các outbox records chưa gửi, publish tới broker rồi đánh dấu trạng thái, với retries và idempotency.

```text
Application transaction
    |
    +-- UPDATE purchase_orders (status = PAID)
    |
    +-- INSERT outbox (OrderPaid)
    |
    v
DB COMMIT
    |
    v
Outbox relay (retryable)
    |
    v
Message broker / consumer (idempotent)
```

### 25.2. Outbox không có nghĩa exactly-once delivery tự động

Nếu relay publish thành công nhưng crash trước khi đánh dấu `published_at`, event có thể được publish lại.

Thiết kế cần:
- Unique event ID/idempotency key.
- Consumer deduplication.
- Retry và dead-letter strategy.
- Monitoring lag/backlog.
- Không xóa outbox record trước khi confirmed durable delivery.
- Transaction/locking strategy cho nhiều relay workers.

Nhưng outbox mạnh hơn một JPA/Hibernate post callback đơn lẻ về độ bền của sự kiện.

## 26. `@TransactionalEventListener` trong Spring

Spring có thể gọi handler sau commit:

```java
@Component
public class OrderPaidHandler {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPaid(OrderPaid event) {
        // Side effect sau commit.
    }
}
```

Đây là Spring application event, **không phải Hibernate `EventType`**.

Phù hợp với:
- In-process notification không yêu cầu durable guarantee cao.
- Cập nhật cache/application metrics sau commit.
- Trigger nội bộ có thể retry bằng cơ chế riêng.

Nhưng nếu JVM crash sau DB commit mà trước callback, message có thể bị mất. Nếu hệ thống cần phát tin reliably cho service khác, dùng outbox/CDC.

Ngoài ra, `AFTER_COMMIT` handler chạy trong giai đoạn transaction completion; resource có thể còn bound. Nếu cần ghi DB mới trong handler, phải xác định transaction propagation mới phù hợp thay vì dựa vào transaction đã commit.

## 27. Bulk HQL/JPQL/native SQL thường bypass per-entity callbacks

Ví dụ bulk HQL:

```java
int count = em.createQuery("""
    update PurchaseOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
    """)
    .setParameter("newStatus", OrderStatus.CANCELLED)
    .setParameter("oldStatus", OrderStatus.DRAFT)
    .executeUpdate();
```

Đây là bulk mutation, **không load từng entity, gọi setter rồi dirty-check như vòng lặp Java**. Vì vậy không được mong `@PreUpdate`, `Interceptor.onFlushDirty` hoặc `PreUpdateEventListener` sẽ chạy **cho từng row** bị ảnh hưởng.

Native SQL:

```java
em.createNativeQuery("""
    update purchase_orders
    set status = ?
    where status = ?
    """)
    .setParameter(1, "CANCELLED")
    .setParameter(2, "DRAFT")
    .executeUpdate();
```

càng không phải entity-by-entity lifecycle.

Database constraints và triggers vẫn có thể áp dụng theo quy tắc DBMS. Persistence Context đã load entity có thể bị stale sau bulk DML, và cache synchronization cần xem theo Hibernate/query spaces.

### 27.1. Tại sao đây là bẫy audit nghiêm trọng?

Nếu hệ thống “audit mọi UPDATE” chỉ dựa vào `@PreUpdate` hoặc Hibernate `PreUpdateEventListener`, một bulk UPDATE có thể thay đổi hàng nghìn rows mà không tạo audit records tương ứng.

Hãy xác định mọi write paths:
- Entity managed updates.
- Bulk HQL/JPQL.
- Native SQL.
- JDBC batch/ETL.
- DB jobs/triggers.
- Các service khác chia sẻ DB.

Nếu yêu cầu bảo đảm audit toàn DB, cần cơ chế ở database/log/CDC hoặc ép mọi writes đi qua một service boundary được bảo vệ.

## 28. `StatelessSession` không giống stateful Session

Hibernate có `StatelessSession` cho các thao tác đọc/ghi theo kiểu stateless/bulk-oriented. Nó không có Persistence Context stateful như Session thông thường và không dùng cùng automatic dirty checking/cascade semantics.

Trong Hibernate hiện đại, `Interceptor` có các callback riêng cho stateless operations:

```java
onInsert(...)
onUpdate(...)
onUpsert(...)
onDelete(...)
```

và các methods này khác với stateful:

```java
onPersist(...)
onFlushDirty(...)
onRemove(...)
```

Không giả định một interceptor chỉ override `onFlushDirty()` sẽ nhận mọi UPDATE được `StatelessSession` thực hiện.

Trước khi chọn extension:
- Xác định code dùng `Session` hay `StatelessSession`.
- Đọc Javadoc chính xác của version.
- Kiểm thử callback semantics khi insert/update/upsert/delete.
- Đừng mặc định JPA lifecycle callbacks và Hibernate event system hoạt động y hệt với stateless operations.

## 29. Collection events: khi nào cần?

Một `Order` có collection:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines = new ArrayList<>();
```

Các thao tác:

```java
order.addLine(line);
order.removeLine(line);
```

có thể dẫn đến collection actions khi flush. Hibernate có groups:

```java
EventType.PRE_COLLECTION_RECREATE
EventType.PRE_COLLECTION_UPDATE
EventType.PRE_COLLECTION_REMOVE

EventType.POST_COLLECTION_RECREATE
EventType.POST_COLLECTION_UPDATE
EventType.POST_COLLECTION_REMOVE
```

Những listener interfaces tương ứng cho phép quan sát collection event và owner/role information theo SPI.

Dùng khi:
- Phải quan sát cache invalidation cho collection membership.
- Có extension engine liên quan collection state.
- Cần telemetry kỹ thuật đặc thù của Hibernate.

Nhưng nếu yêu cầu nghiệp vụ là “khi order có một line được thêm, cập nhật tổng tiền” thì **domain method `order.addLine()` và constraint/invariant** rõ ràng hơn. Không nên dựa vào một collection listener để suy đoán mọi thay đổi FK, nhất là khi owning side có thể được sửa qua đường khác hoặc native SQL.

### 29.1. `orphanRemoval` và callback trên child

Khi orphan removal dẫn đến DELETE entity, Hibernate có thể phát entity delete events theo hành động thực tế. Nhưng một collection event không phải một event cho từng phần tử theo contract business.

Cần kiểm thử collection update/recreate/remove, batch, cascade và orphan deletion riêng nếu extension phụ thuộc những chi tiết đó.

## 30. `StatementInspector` khi mục tiêu thật sự là SQL

Nếu cần quan sát SQL text do Hibernate tạo, `Interceptor` không phải cơ chế lý tưởng. Hibernate cung cấp:

```java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public final class SqlLoggingInspector
        implements StatementInspector {

    @Override
    public String inspect(String sql) {
        // Thêm correlation metadata vào telemetry,
        // hoặc quan sát SQL trong môi trường debug.
        return sql;
    }
}
```

Cấu hình (theo Hibernate settings):

```properties
hibernate.session_factory.statement_inspector=\
com.example.persistence.SqlLoggingInspector
```

Hoặc trong bootstrap:

```java
metadata.getSessionFactoryBuilder()
    .applyStatementInspector(new SqlLoggingInspector())
    .build();
```

`StatementInspector.inspect(sql)` chạy khi SQL được Hibernate chuẩn bị để gửi JDBC, không đồng nghĩa statement đã execute/commit. Nó thường không chứa các **giá trị bind parameters**; không lấy SQL text làm log đầy đủ cho business auditing.

### 30.1. Không rewrite SQL tùy tiện

Một inspector có thể thay đổi SQL string nếu contract cho phép, nhưng sửa SQL bằng thao tác string replace thiếu parser có thể:

- Đụng SQL literals/comments.
- Làm sai generated SQL aliases/parameter positions.
- Phá pagination/locking syntax của dialect.
- Làm sai cache/query semantics.

Dùng SQL comments/telemetry có kiểm soát hoặc provider feature chuyên biệt. Nếu cần thay đổi mapping/query filtering, sửa ở HQL/Criteria/filter/multi-tenancy layer thay vì string-rewrite SQL cuối cùng.

## 31. `AttributeConverter` và custom type: không phải lifecycle event

Nếu muốn lưu một enum mã nghiệp vụ dưới dạng string:

```java
public enum PaymentState {
    NEW("N"), SETTLED("S");

    private final String code;

    PaymentState(String code) {
        this.code = code;
    }

    public String code() { return code; }

    public static PaymentState fromCode(String code) {
        return switch (code) {
            case "N" -> NEW;
            case "S" -> SETTLED;
            default -> throw new IllegalArgumentException(code);
        };
    }
}
```

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class PaymentStateConverter
        implements AttributeConverter<PaymentState, String> {

    @Override
    public String convertToDatabaseColumn(PaymentState state) {
        return state == null ? null : state.code();
    }

    @Override
    public PaymentState convertToEntityAttribute(String code) {
        return code == null ? null : PaymentState.fromCode(code);
    }
}
```

```java
@Convert(converter = PaymentStateConverter.class)
private PaymentState paymentState;
```

Đây là **type conversion**, không phải event hook. Dùng converter để ánh xạ value object/enum, không dùng `onLoad` hoặc `PreInsertEventListener` để tự chuyển từng field trừ khi có lý do kiến trúc đặc biệt.

Custom `UserType`, `JavaType`, `JdbcType` hoặc `@JdbcTypeCode` phù hợp hơn nếu cần Hibernate type system sâu hơn.

## 32. Nếu cần kiểm soát truy cập hoặc multi-tenancy

Một ý tưởng không an toàn:

```java
@Override
public boolean onPreInsert(PreInsertEvent event) {
    if (!currentUserCanWrite(event.getEntity())) {
        return true; // Chặn INSERT âm thầm.
    }
    return false;
}
```

Vấn đề:
- Veto không phải exception authorization rõ ràng.
- Nhiều write paths có thể bypass per-entity listener.
- `currentUser` khó quản lý đúng trong shared listener.
- Data từ native SQL/DB job không đi qua listener.
- Query đọc dữ liệu nhạy cảm không tự được bảo vệ.

Thay vào đó:
- Xác thực/authorization tại service boundary.
- Hibernate multi-tenancy nếu model phù hợp.
- Hibernate `@Filter`/query predicates cho dynamic data scoping.
- DB row-level security khi yêu cầu multi-writer protection.
- Constraints/triggers cho data integrity.

**Listener không phải lớp bảo mật cuối cùng.** Test phải bao quát native/bulk SQL và nhiều tenants.

## 33. Transaction boundary và side effects

Cần phân biệt:

| Sự kiện | DB transaction đã commit? | Có thể rollback sau đó? |
| --- | --- | --- |
| JPA `@PrePersist` | Chưa | Có |
| JPA `@PostPersist` | Không bảo đảm | Có |
| Interceptor `onPersist` | Chưa | Có |
| Interceptor `onFlushDirty` | Chưa | Có |
| Hibernate `PRE_INSERT` | Chưa | Có |
| Hibernate `POST_INSERT` | Không bảo đảm | Có |
| Hibernate `POST_COMMIT_*` phù hợp | Gắn với transaction-completion handling | Phụ thuộc callback/commit outcome |
| Spring `@TransactionalEventListener(AFTER_COMMIT)` | Sau commit thành công theo Spring | DB commit đã xảy ra, nhưng callback vẫn có thể thất bại |
| Outbox relay | Sau khi outbox record đã commit | Có retry/idempotency riêng |

Các callback dạng `Post*` ở entity/ORM level thường biểu diễn **vị trí trong persistence lifecycle**, không phải cam kết dữ liệu đã bền vững ngoài DB transaction.

### 33.1. Side effect trong callback có được rollback không?

- Thay đổi SQL trong cùng DB transaction: rollback có thể hoàn tác.
- Ghi log process: không rollback.
- Gửi email: không rollback.
- Gọi REST API service khác: không rollback tự động.
- Publish Kafka message: không đồng bộ commit với DB chỉ vì gọi trong listener.
- Tăng in-memory counter: không rollback.
- Ghi metrics: không rollback.

Vì vậy tên các metric/notification phải phản ánh **attempted, executed hoặc committed**, không trộn lẫn.

## 34. Exception trong listener ảnh hưởng transaction

Nếu một callback ném exception khi Hibernate đang flush, transaction có thể bị đánh dấu rollback-only, flush dừng và persistence context có thể không còn sử dụng an toàn.

Ví dụ:

```java
@Override
public boolean onPreInsert(PreInsertEvent event) {
    if (violatesTechnicalInvariant(event)) {
        throw new IllegalStateException("Invalid mapping state");
    }
    return false;
}
```

Với một invariant thực sự cần kiểm tra, hãy ưu tiên xác thực sớm ở service/domain hoặc Bean Validation và dùng DB constraint để bảo vệ dữ liệu. Nếu listener báo exception, application nên:

1. Ghi nhận nguyên nhân.
2. Rollback transaction.
3. Đóng/loại bỏ EntityManager/Session liên quan nếu flush lỗi.
4. Không `clear()` rồi tiếp tục cùng transaction như chưa có gì.
5. Retry trong transaction mới **chỉ khi lỗi có thể retry**, ví dụ deadlock/transient connectivity, và có idempotency đúng.

Đừng nuốt exception và cho rằng một INSERT bị veto/skip không ảnh hưởng đến graph/consistency.

## 35. Performance: callback chạy trong hot path

Một listener được gọi cho mỗi entity INSERT có thể chạy hàng chục nghìn lần trong batch.

```text
100.000 entities
      |
      v
100.000 PRE_INSERT callbacks
      |
      v
Nếu mỗi callback thêm 3 ms:
  300.000 ms thời gian xử lý phụ thêm
```

Đây là phép tính minh họa, không phải benchmark thực tế. Nó cho thấy tại sao logic hook phải nhẹ:

- Không gọi HTTP, broker, filesystem hoặc query không cần thiết trong callback.
- Không serialize object graph lớn.
- Không gọi `toString()` có thể chạm lazy associations.
- Không query metadata bằng reflection mỗi callback nếu có thể tính trước.
- Không log INFO cho từng entity trong import hàng triệu rows.
- Không thao tác trên shared mutable collections thiếu synchronization.

Có thể dùng `LongAdder`, histogram aggregates và sampled traces nhưng tránh coi attempted callback counters là committed counts.

### 35.1. Instrument SQL và ORM riêng biệt

Nếu muốn biết:
- Entity events: dùng listener/Interceptor metrics.
- SQL statements executed: datasource proxy/JDBC metrics/DB logs.
- Query latency: tracing/DB metrics.
- Committed business operations: đo ở transaction completion/outbox.
- Data-integrity violations: DB constraints/error metrics.

Một chỉ số duy nhất không giải thích được toàn bộ persistence pipeline.

## 36. Thiết kế listener idempotent và có thể đăng ký lặp

Nếu ServiceLoader resource bị merge trùng hoặc cùng `Integrator` được cài qua hai cơ chế bootstrap, cùng listener có thể được đăng ký hai lần.

Hệ quả:
- Metrics tăng đôi.
- Side effect lặp.
- Audit logic chạy hai lần.
- Thứ tự listeners thay đổi.

Hibernate `EventListenerRegistry` có khả năng duplication strategy cho các event listener groups. Nếu cần, định nghĩa `DuplicationStrategy` theo SPI của version dùng và quyết định thế nào là duplicate.

Một lựa chọn tốt hơn là:
- Có **một chủ sở hữu đăng ký**.
- Sử dụng ServiceLoader **hoặc** bootstrap customization theo quy trình rõ.
- Kiểm thử listener được gọi đúng số lần trong một thao tác đơn giản, không phụ thuộc số sự kiện nội bộ khác.
- Không giữ side effects không idempotent trong listener.

## 37. Integration test: callback chạy vào thời điểm nào?

Một test có thể dùng `EntityManagerFactory`/database Testcontainers và một listener đếm attempt.

Dữ liệu entity:

```java
PurchaseOrder order = new PurchaseOrder(
    "PO-101",
    new BigDecimal("100.00")
);
```

Trong transaction:

```java
tx.begin();

em.persist(order);
em.flush();

// Lúc này INSERT có thể đã chạy,
// nhưng transaction vẫn chưa commit.

tx.rollback();
```

Một `POST_INSERT` counter có thể tăng, trong khi transaction rollback và DB không còn order.

Test nên xác minh **hai điều tách biệt**:

1. Hook có được gọi theo event được thiết kế không?
2. Row có tồn tại sau commit hoặc không tồn tại sau rollback không?

Chúng không tương đương.

### 37.1. Test JPA `@PreUpdate` chỉ khi dirty

```java
PurchaseOrder order = em.find(PurchaseOrder.class, id);

em.flush(); // Không đổi field.

order.markPaid();
em.flush(); // Entity dirty, Hibernate có thể phát UPDATE.
```

Test số lần callback bằng counter phù hợp hoặc assert timestamp/DB state. Chú ý event có thể được gọi nhiều lần trong những flow flush phức tạp; không cứng hóa giả định “mỗi service call đúng một callback” trừ khi contract và test fixture bảo đảm.

### 37.2. Test bulk DML không tạo per-row event

```java
em.createQuery("""
    update PurchaseOrder o
    set o.status = :status
    """)
    .setParameter("status", OrderStatus.CANCELLED)
    .executeUpdate();
```

Assert database rows đổi, nhưng per-entity JPA callbacks/PreUpdate listener không bị gọi cho từng row theo semantics bulk DML.

Nếu test cùng EntityManager đã có managed orders, refresh/clear đúng để tránh L1 stale làm assertion sai.

## 38. Kiểm thử Integrator/ServiceLoader được phát hiện

Một lỗi phổ biến: class `OrderEventIntegrator` được viết đúng nhưng service file không nằm trong packaged JAR.

Các bước:

1. Kiểm tra resource tồn tại:
   `META-INF/services/org.hibernate.integrator.spi.Integrator`.
2. Kiểm tra tên fully qualified class và package thật.
3. Kiểm tra class implements `Integrator`, constructor có thể truy cập.
4. Kiểm tra build artifact chứa file resource.
5. Nếu dùng shading/fat JAR, kiểm tra service descriptors không bị overwrite.
6. Bootstrap `SessionFactory` trong integration test.
7. Persist entity, flush và assert observer nhận event.
8. Test các add-on Hibernate khác vẫn hoạt động (Envers, validation, cascades).

Chỉ unit test:

```java
new OrderPreInsertListener().onPreInsert(mockEvent);
```

không chứng minh Hibernate đã load và gắn listener vào event registry thật.

## 39. Integration test với PostgreSQL/Testcontainers

Khi extension phụ thuộc thứ tự SQL, constraints hoặc ID generation, dùng DBMS gần production.

Một test setup khái niệm:

```java
@Testcontainers
@SpringBootTest
class OrderEventIntegrationTest {

    @Container
    static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            db::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            db::getUsername
        );
        registry.add(
            "spring.datasource.password",
            db::getPassword
        );
    }

    // Integration tests with EMF and listener registration.
}
```

Đoạn trên minh họa kiểu setup và cần các imports/dependencies Testcontainers, JUnit 5, Spring Boot phù hợp.

Hãy test:
- Bootstrap đăng ký listener đúng.
- `persist()`/`flush()`/`commit()`/`rollback()`.
- `IDENTITY` và `SEQUENCE` nếu ID timing quan trọng.
- INSERT/UPDATE/DELETE + collection changes.
- Cascade và orphan removal.
- Bulk HQL/native SQL.
- Multi-session, concurrency.
- Nhiều EntityManagerFactories nếu ứng dụng có.
- Cache/provider/integration khác như Envers.
- SQL logs/DB rows thay vì chỉ nhìn callback counter.

## 40. Ví dụ một test toàn diện về rollback

Ý tưởng:

```java
@Test
void postInsertIsNotProofOfCommit() {
    // Có listener POST_INSERT đã đăng ký trong EMF.

    Long id;

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        PurchaseOrder order = new PurchaseOrder(
            "PO-rollback",
            new BigDecimal("10.00")
        );

        em.persist(order);
        em.flush();

        id = order.getId();

        // POST_INSERT đã có cơ hội chạy.
        tx.rollback();
    } finally {
        if (tx.isActive()) tx.rollback();
        em.close();
    }

    EntityManager verify = emf.createEntityManager();

    try {
        assertNull(verify.find(PurchaseOrder.class, id));
    } finally {
        verify.close();
    }
}
```

Nếu ID generator trả ID khi persist/flush, sau rollback vẫn có thể thấy **khoảng trống ID** do sequence/identity không rollback theo cùng cách transaction rows; đó là behavior DBMS, không chứng minh INSERT đã commit.

Test cần fixture có `emf`, migrations, listener registration và đủ imports. Không dùng constructor trên `PurchaseOrder` rút gọn có thiếu các `@PrePersist`/audit fields ở schema production; test fixture phải chọn đúng biến thể entity đang được chạy.

## 41. Những lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `onSave()` override không chạy sau nâng cấp | Hibernate version dùng `onPersist()` mới | Đối chiếu Interceptor Javadoc, cập nhật signature |
| Interceptor `onPersist()` trả true nhưng INSERT bị chặn? | Hiểu sai return value | `true` nghĩa state đã bị sửa, không phải veto |
| `PreInsertEventListener` trả true và INSERT biến mất | Return true là veto | Chỉ veto khi thực sự phát triển extension hiểu hậu quả |
| Listener không chạy | Integrator chưa được ServiceLoader discover | Kiểm tra `META-INF/services`, classpath và bootstrap |
| Listener chạy hai lần | Đăng ký trùng | Chọn một registration owner/duplication strategy |
| Callback bị gọi khi chưa commit | Hook chạy ở persist/flush/SQL lifecycle | Dùng outbox/after-commit phù hợp |
| PostPersist gửi email nhưng DB rollback | External side effect không transactional | Không publish trong callback, dùng outbox |
| Listener bị N+1/timeout | Query/network call bên trong hook | Giữ hook nhẹ, chuyển việc ra service/worker |
| Reentrant flush/exception | Gọi Session từ callback đang flush | Tránh ORM calls/lazy initialization trong callback |
| Custom `findDirty` làm mất UPDATE | Trả mảng dirty indices sai | Để default `null` nếu không có lý do mạnh |
| Timestamp thay đổi không ổn định | Nhiều cơ chế cùng sở hữu field | Chọn một generation policy |
| `onLoad` đọc field chưa được hydrate | Entity chưa initialized khi callback | Dùng state array hoặc `@PostLoad` |
| Shared interceptor lẫn request state | Singleton mutable state không thread-safe | Stateless hoặc session-scoped |
| Spring `@Autowired` null trong listener | Listener được Hibernate tự `new` | DI integration đúng hoặc không phụ thuộc Spring |
| Bulk HQL update không audit từng entity | Bypass entity lifecycle | Envers không bao trùm bulk; dùng DB trigger/CDC/service boundary |
| Native SQL thay dữ liệu mà listener không chạy | JDBC ngoài ORM | Database-level hooks hoặc capture writer path |
| `POST_COMMIT_*` event vẫn có thể mất message | Không durable khi JVM crash | Transactional outbox và retries |
| Collection listener không bắt mọi FK change | Thay đổi owning side/native SQL khác | Domain invariant + integration tests |
| `setListeners` làm mất behavior Hibernate | Ghi đè default listeners | Dùng append/prepend cho observer |
| Một testcase H2 pass, PostgreSQL lỗi | SQL/ID/constraint behavior khác | Testcontainers đúng DBMS |
| Counter listener khác rows committed | Đếm attempts hoặc SQL operations, rollback xảy ra | Metric name đúng và đo commit riêng |
| Version nâng cấp phá SPI | Hibernate internals không portable | Pin version, compile/integration tests trước upgrade |

## 42. Quy trình quyết định trước khi viết một listener

**Bước 1 — Phát biểu rõ yêu cầu:** cần validate state, mutate field, audit history, observe SQL, security, publish event hay kiểm tra collection?

**Bước 2 — Xác định source of truth:** yêu cầu chỉ áp cho ORM-managed writes hay cho mọi writer kể cả native SQL/ETL/service khác?

**Bước 3 — Chọn cơ chế có hợp đồng nhỏ nhất:** domain/service/Bean Validation/DB constraint → JPA callback → Hibernate Interceptor → event SPI.

**Bước 4 — Cần entity values hay state arrays?** Nếu chỉ field của entity, callback chuẩn có thể đủ; nếu cần `previousState/currentState`, Interceptor phù hợp hơn.

**Bước 5 — Cần event cụ thể nào?** Phân biệt `PERSIST`, `PRE_INSERT`, `POST_INSERT`, `POST_COMMIT_INSERT`; đọc đúng Javadoc.

**Bước 6 — Có chỉnh sửa state không?** Hiểu return value; với Interceptor true = modified state, với `PreInsertEventListener` true = veto.

**Bước 7 — Có network/SQL side effect không?** Đưa ra khỏi hook nếu có thể. Không reenter Session đang flush.

**Bước 8 — Có transaction consistency requirement không?** Nếu cần reliable external publish, dùng outbox/CDC thay callback trực tiếp.

**Bước 9 — Một Session hay nhiều Sessions?** Kiểm tra shared vs session-scoped interceptor, thread safety và DI.

**Bước 10 — Đăng ký có làm mất default behavior không?** Ưu tiên `appendListeners()`, tránh `setListeners()` khi không cần.

**Bước 11 — Có bulk/native/stateless writes?** Không giả định listener nhận tất cả đường đi; test write-path matrix.

**Bước 12 — Version compatibility:** Hibernate event SPI có thể đổi ở major version; pin API và chạy integration tests trước upgrade.

**Bước 13 — Đo performance:** sample latency/SQL count/memory với workload lớn.

**Bước 14 — Xác nhận correctness:** test commit, rollback, exception, cascade, collection changes, multi-thread và real DB.

## 43. Bài tập tình huống

### Bài 1 — Gán timestamp

Muốn điền `createdAt` và `updatedAt` trước INSERT. Có cần `PreInsertEventListener`?

**Đáp án:** Thường không. Dùng JPA `@PrePersist`, `@PreUpdate` hoặc Hibernate timestamp annotations khi phù hợp.

### Bài 2 — So sánh state cũ/mới

Cần biết `status` trước và sau khi Hibernate flush dirty entity. Chọn JPA callback hay Interceptor?

**Đáp án:** `Interceptor.onFlushDirty` cung cấp `previousState` và `currentState` arrays; callback JPA không cung cấp hai arrays đó trực tiếp.

### Bài 3 — Return value

`Interceptor.onPersist()` sửa `state[i]` rồi trả `true`. `true` có nghĩa INSERT bị chặn không?

**Đáp án:** Không. Nó thông báo state array đã được sửa.

### Bài 4 — Veto

`PreInsertEventListener.onPreInsert()` trả `true`. Điều gì xảy ra?

**Đáp án:** Theo contract của listener này, `true` veto thao tác INSERT. Dùng rất thận trọng; validation thường nên reject bằng domain/Bean Validation/constraint.

### Bài 5 — `@PostPersist` gửi Kafka

Order INSERT thành công rồi `@PostPersist` gửi Kafka; transaction sau đó rollback. Có thể xảy ra sai lệch gì?

**Đáp án:** Kafka đã nhận event về một order không commit. Dùng transactional outbox nếu cần reliable cross-system messaging.

### Bài 6 — `POST_INSERT` và `POST_COMMIT_INSERT`

Hai event groups có giống nhau không?

**Đáp án:** Không. POST_INSERT gắn với SQL entity insert; POST_COMMIT_INSERT là cơ chế callback liên quan transaction completion theo SPI. Cả hai không tự mang lại durable broker delivery.

### Bài 7 — Đăng ký event listener

Muốn thêm observer vào PRE_INSERT group nhưng giữ default listeners. Nên gọi gì?

**Đáp án:** `registry.appendListeners(EventType.PRE_INSERT, observer)` hoặc prepend nếu cần priority; không `setListeners()` tùy tiện.

### Bài 8 — Không được DI

Listener có `@Autowired` field nhưng null khi Hibernate chạy. Vì sao?

**Đáp án:** Integrator/ServiceLoader khởi tạo listener ngoài Spring bean lifecycle; cần bridge/injection chính thức hoặc bỏ dependency.

### Bài 9 — Shared state

Một interceptor được cấu hình qua `hibernate.session_factory.interceptor`, có field `currentUserId` mutable. Có nguy cơ gì?

**Đáp án:** Nhiều Sessions dùng cùng instance có thể ghi đè state lẫn nhau. Dùng stateless/session-scoped design.

### Bài 10 — `onLoad` và proxy

Có nên gọi lazy association getter trong `Interceptor.onLoad()`?

**Đáp án:** Không. Entity có thể chưa được hydrate; Interceptor Javadoc còn cảnh báo không lazy-initialize proxy/collection từ callback.

### Bài 11 — Bulk update

Bulk HQL UPDATE 10.000 rows. Có 10.000 callback `@PreUpdate` không?

**Đáp án:** Không. Bulk mutation không đi qua vòng đời từng managed entity như cập nhật từng object.

### Bài 12 — Delete ngoài Hibernate

Một DBA chạy `DELETE FROM purchase_orders`. Event listener `POST_DELETE` có được gọi không?

**Đáp án:** Không, vì Hibernate không xử lý những rows đó. Cần database-level auditing/CDC nếu muốn mọi writer.

### Bài 13 — Audit revisions

Muốn lịch sử entity theo revision, không cần thao tác SQL ngoài Hibernate. Nên cân nhắc gì?

**Đáp án:** Hibernate Envers thường phù hợp hơn việc tự viết Pre/Post listeners.

### Bài 14 — SQL inspection

Muốn xem generated SQL text trước khi JDBC prepare. Có nên dùng `Interceptor.onFlushDirty()`?

**Đáp án:** Không. Dùng `StatementInspector` hoặc JDBC tracing phù hợp.

### Bài 15 — Một field enum custom

Muốn lưu `PaymentState.NEW` thành `'N'` trong VARCHAR. Dùng event listener?

**Đáp án:** Không cần. Dùng `AttributeConverter<PaymentState, String>` hoặc type mapping thích hợp.

### Bài 16 — Ghi một outbox row

Muốn atomically ghi order update và outbox event. Nên viết ở listener đang flush hay service transaction?

**Đáp án:** Ưu tiên service method ghi cả hai trong cùng DB transaction; relay ngoài transaction publish sau commit và retry.

### Bài 17 — `clear()` sau callback

Listener ghi metrics khi flush; application gọi `clear()`. Metrics có tự rollback hoặc biến mất không?

**Đáp án:** Không. Metrics là side effect ngoài DB transaction; `clear()` chỉ detach managed entities.

### Bài 18 — Two-pass test

Tại sao phải test cả rollback nếu listener báo `POST_INSERT` đã chạy?

**Đáp án:** Để chứng minh event after SQL không đồng nghĩa commit. Phải assert row absent sau rollback.

### Bài 19 — Multi-tenant security

Có nên dùng PreInsertEventListener để bảo vệ mọi tenant writes, kể cả native SQL?

**Đáp án:** Không. Native SQL và writers ngoài ORM có thể bypass per-entity events; cần authorization/service, Hibernate tenancy và/hoặc DB RLS.

### Bài 20 — Version upgrade

Dự án nâng Hibernate 5 lên Hibernate 7 và `onSave` cũ deprecated. Cần làm gì?

**Đáp án:** Đối chiếu API mới (`onPersist`, `onRemove`), kiểm tra registration và semantics bằng integration tests với chính version mới.

## 44. Tài liệu tham khảo chính thức

- [Hibernate ORM User Guide — Interceptors and Events](https://docs.hibernate.org/orm/7.1/userguide/html_single/#events): interceptor, event listener registration và callbacks.
- [Hibernate ORM 7.1 Javadoc — `Interceptor`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/Interceptor.html): state arrays, `onPersist`, `onFlushDirty`, `onLoad`, `findDirty`, transaction callbacks và phạm vi session.
- [Hibernate ORM 7.1 Javadoc — `EventType`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/event/spi/EventType.html): các groups `PRE_INSERT`, `POST_INSERT`, collection và post-commit.
- [Hibernate ORM 7.1 Javadoc — `EventListenerRegistry`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/event/service/spi/EventListenerRegistry.html): `appendListeners`, `prependListeners`, `setListeners` và duplication strategy.
- [Hibernate ORM 7.1 Javadoc — `PreInsertEventListener`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/event/spi/PreInsertEventListener.html): semantics callback và veto.
- [Hibernate ORM 7.1 Javadoc — `PostInsertEventListener`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/event/spi/PostInsertEventListener.html): post-insert callback và post-commit handling contract.
- [Hibernate ORM 7.1 Javadoc — `Integrator`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/integrator/spi/Integrator.html): bootstrapping và ServiceLoader.
- [Hibernate ORM 7.1 Javadoc — `SessionEventSettings`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/cfg/SessionEventSettings.html): shared/session-scoped interceptor configuration.
- [Hibernate ORM Javadoc — `StatementInspector`](https://docs.hibernate.org/orm/7.1/javadocs/org/hibernate/resource/jdbc/spi/StatementInspector.html): SQL inspection đúng vị trí.
- [Hibernate ORM User Guide — Envers](https://docs.hibernate.org/orm/7.1/userguide/html_single/#envers): audit revision history.
- [Jakarta Persistence 3.2 Specification](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html): entity lifecycle callbacks, `@EntityListeners` và portable restrictions.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và transaction phases.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries, after commit, exceptions.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): commit DB và publish event đáng tin cậy bằng outbox.

**Ghi chú phiên bản:** Ví dụ tập trung Jakarta Persistence và Hibernate 6.6+/7.1. Các event SPI, interceptor callback names, bootstrap integration và `StatelessSession` callbacks có thể khác đáng kể giữa Hibernate 5, 6, 7 và 8. Hãy dùng Javadoc/implementation tests đúng Hibernate version của ứng dụng. Những API `Interceptor`, `EventType`, `Integrator`, `StatementInspector` và Envers là Hibernate-specific, không portable sang JPA provider khác.

## Kết luận

JPA lifecycle callbacks đủ cho phần lớn nhu cầu gắn liền với **một entity**: khởi tạo timestamps, xử lý field nhẹ và quan sát persistence lifecycle. Hibernate `Interceptor` cần thiết khi ứng dụng muốn inspect/change `state[]`, có `previousState/currentState` hoặc cần một hook dùng chung ở nhiều entity types. Hibernate event listeners đi sâu hơn, cho phép tham gia các `EventType` cụ thể như `PRE_INSERT`, `POST_UPDATE`, collection events hay flush processing; việc đăng ký phải giữ nguyên các default handlers và hiểu rõ thứ tự trong event groups.

Bất kỳ callback nào chạy quanh `persist()`/`flush()`/SQL **đều không tự chứng minh transaction đã commit**. Không query/lazy-initialize entity graph hoặc publish network messages từ hook đang flush; không dùng listener để thay database constraints/authorization; và không chờ per-entity listeners cho các bulk/native SQL operations. Nếu cần revision auditing, cân nhắc Envers; nếu cần SQL inspection, dùng `StatementInspector`; nếu cần publish domain event đáng tin cậy, dùng transactional outbox.

Chọn extension point ít xâm lấn nhất, kiểm soát thread safety và transaction outcomes, test cả commit lẫn rollback và kiểm tra behavior trên đúng Hibernate version/DBMS trước khi đưa một listener vào production.
