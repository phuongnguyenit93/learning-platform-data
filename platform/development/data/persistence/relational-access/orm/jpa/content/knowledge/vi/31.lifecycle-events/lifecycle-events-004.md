# Đăng ký listener riêng và listener dùng chung trong sự kiện vòng đời JPA

Trong **Jakarta Persistence (JPA)**, một entity trải qua nhiều sự kiện vòng đời: được tạo và chuẩn bị lưu, được nạp từ database, bị thay đổi, hoặc được đánh dấu để xóa. JPA cho phép ứng dụng gắn **callback** vào các mốc này để thực hiện những công việc liên quan trực tiếp đến vòng đời của dữ liệu.

Ví dụ, khi lưu `PurchaseOrder`, hệ thống có thể cần:

- Gán `createdAt` trước lần insert đầu tiên.
- Gán `updatedAt` mỗi khi cập nhật entity.
- Kiểm tra một số bất biến đơn giản của dữ liệu trước khi ghi.
- Tính lại giá trị `@Transient` sau khi entity được nạp.

Nếu đặt logic đó trong mọi entity, code sẽ lặp lại và khó bảo trì. Nếu chuyển toàn bộ vào một listener toàn cục, có thể gây tác dụng ngoài ý muốn lên những entity không liên quan. JPA cung cấp những cách đăng ký khác nhau để cân bằng **tính riêng biệt** và **khả năng tái sử dụng**:

1. **Callback ngay trong entity**: method được gắn `@PrePersist`, `@PostLoad`… trong chính lớp entity hoặc mapped superclass.
2. **Listener riêng cho entity**: lớp listener bên ngoài, được đăng ký với `@EntityListeners(...)` trên entity tương ứng.
3. **Listener dùng chung**: một lớp listener được gắn lên nhiều entity hoặc trên một `@MappedSuperclass` để kế thừa.
4. **Default entity listener cấp persistence unit**: đăng ký thông qua metadata XML `orm.xml` để dùng rộng cho những entities áp dụng cấu hình mặc định.

> **Nguyên tắc quan trọng:** `@EntityListeners` đăng ký lớp listener cho những entity được chỉ định; một lớp có tên `AuditListener` chỉ được viết ra **không tự động được chạy cho mọi entity**. Muốn sử dụng rộng, phải đăng ký ở từng nơi, qua mapped superclass hoặc metadata mặc định của persistence unit.

Bài học thuộc chương **Sự kiện vòng đời** của module **Data Persistence Relational Access ORM JPA**, tập trung vào cách đăng ký, chia sẻ, kế thừa, loại trừ và kiểm thử entity listeners, đồng thời chỉ rõ thời điểm callback chạy và những giới hạn cần tránh.

---

## 1. Entity listener giải quyết vấn đề gì?

Giả sử ứng dụng có ba entity:

```text
Customer
   id
   name
   createdAt
   updatedAt

PurchaseOrder
   id
   reference
   status
   createdAt
   updatedAt

Product
   id
   sku
   price
   createdAt
   updatedAt
```

Cả ba đều cần audit timestamps. Một cách trực tiếp là viết trong mỗi entity:

```java
@PrePersist
void beforeInsert() {
    createdAt = Instant.now();
    updatedAt = createdAt;
}

@PreUpdate
void beforeUpdate() {
    updatedAt = Instant.now();
}
```

Cách này có thể hợp lý nếu chỉ có một entity, nhưng khi dự án có hàng chục loại entity, nó tạo ra:

- Code lặp lại.
- Nhiều nơi dùng quy tắc timestamp khác nhau.
- Khó đổi chính sách chung.
- Khó kiểm thử cùng một quy tắc trên nhiều entity.
- Nguy cơ entity nào đó quên gắn `@PreUpdate`.

Đưa phần logic chung sang listener dùng lại sẽ giúp entity tập trung hơn vào dữ liệu và quy tắc domain riêng.

Ngược lại, một quy tắc như “mã tham chiếu đơn hàng bắt buộc có tiền tố phù hợp” không nên áp cho mọi entity. Nó nên nằm trong domain model hoặc **listener riêng của PurchaseOrder**, thay vì một listener mặc định cho toàn bộ persistence unit.

### 1.1. Ba vai trò thường gặp

| Nhu cầu | Vị trí phù hợp để cân nhắc |
| --- | --- |
| Gán timestamp giống nhau cho nhiều entity | Listener dùng chung hoặc mapped superclass callback |
| Kiểm tra invariant riêng của PurchaseOrder | Callback trong entity hoặc listener riêng |
| Ghi trace kỹ thuật cho mọi entity | Default listener trong `orm.xml` khi thật sự cần |
| Tính trường hiển thị không persistent sau khi load | `@PostLoad` trong entity hoặc listener riêng |
| Gửi email sau khi đơn hàng commit | **Không** làm trực tiếp trong lifecycle callback; dùng event sau commit/outbox |
| Ghi lịch sử thay đổi phức tạp liên quan nhiều bảng | Domain service, audit infrastructure hoặc outbox phù hợp hơn |
| Authorization dựa trên người dùng hiện tại | Service/application boundary, không mặc định dựa vào callback |

**Không phải hành vi nào xảy ra gần thao tác lưu entity cũng nên đưa vào lifecycle listener.**

## 2. Các sự kiện vòng đời cần biết

JPA cung cấp những annotation callback thông dụng sau:

| Annotation | Mốc vòng đời | Nhu cầu minh họa |
| --- | --- | --- |
| `@PrePersist` | Trước khi insert entity mới | Gán dữ liệu mặc định, createdAt |
| `@PostPersist` | Sau thao tác persist/insert được xử lý tương ứng | Ghi nhận ID đã được tạo, xử lý trạng thái nội bộ |
| `@PreUpdate` | Trước SQL update tương ứng | updatedAt, xác minh state |
| `@PostUpdate` | Sau SQL update tương ứng | Quan sát update đã thực thi |
| `@PreRemove` | Trước khi remove entity | Kiểm tra điều kiện xóa đơn giản |
| `@PostRemove` | Sau thao tác delete tương ứng | Quan sát thao tác xóa |
| `@PostLoad` | Sau khi JPA hoàn tất việc nạp/refresh entity theo ngữ nghĩa callback | Tính trường `@Transient` |

Import:

```java
import jakarta.persistence.PrePersist;
import jakarta.persistence.PostPersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.PostUpdate;
import jakarta.persistence.PreRemove;
import jakarta.persistence.PostRemove;
import jakarta.persistence.PostLoad;
```

### 2.1. Không nhầm PrePersist với constructor

Constructor Java chạy khi object được tạo; `@PrePersist` chạy khi JPA thực hiện lifecycle persist của một entity mới.

```java
PurchaseOrder order = new PurchaseOrder();
// Constructor: entity chưa cần thuộc persistence context.

em.persist(order);
// Lifecycle persist có thể kích hoạt @PrePersist.
```

Một entity có thể được tạo nhưng không bao giờ gọi `persist()`. Khi ấy không có lý do để `@PrePersist` chạy.

### 2.2. Không nhầm PostPersist với sau commit

`@PostPersist` có thể được gọi sau SQL insert ở một mốc trước khi toàn bộ transaction commit. Nếu transaction về sau rollback, database không lưu thay đổi, dù callback đã chạy.

Tương tự, `@PostUpdate` và `@PostRemove` **không phải cam kết transaction đã được commit thành công**.

### 2.3. Thời điểm @PreUpdate có thể khác dự đoán

Một entity managed bị thay đổi ở Java không nhất thiết lập tức có SQL UPDATE. Provider thường đồng bộ thay đổi ở flush/commit.

Nếu entity không có thay đổi persistent cần ghi, không được dựa vào `@PreUpdate` như một callback chắc chắn chạy mỗi lần gọi một setter hoặc mỗi lần gọi `save()`.

### 2.4. @PostLoad không đồng nghĩa một lần mỗi HTTP request

`@PostLoad` gắn với vòng đời nạp entity, không phải vòng đời web request. Khi entity đã managed trong cùng persistence context, `find()` lặp lại có thể trả instance cũ mà không có một lượt load mới.

Đối với L2 cache và cách provider dựng entity, không nên dùng số lần gọi `@PostLoad` như phép đo số SQL SELECT.

## 3. Callback đặt trực tiếp trong entity

Cách đơn giản nhất là đánh dấu một method trong entity:

```java
package com.example.orders;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String reference;

    private Instant createdAt;

    private Instant updatedAt;

    @PrePersist
    private void beforeInsert() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    private void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Đối với callback nằm trong entity, phương thức thường có:

- Kiểu trả về `void`.
- Không tham số.
- Không được khai báo thành một static callback.
- Là method có annotation lifecycle tương ứng.
- Logic ngắn, tập trung vào state của entity đó.

### 3.1. Ưu điểm

- Dễ tìm thấy quy tắc ngay trong entity.
- Không cần thêm class listener.
- Phù hợp với hành vi nội tại của một entity.
- Có thể thao tác với private fields của chính entity.

### 3.2. Nhược điểm

- Dễ trùng lặp khi nhiều entity có cùng chính sách.
- Entity phình to nếu chứa nhiều logic kỹ thuật.
- Một quy tắc chung bị rải ra nhiều lớp.
- Khó tách chính sách auditing khỏi domain model.

### 3.3. Khi nào nên giữ callback trong entity?

Ví dụ một `@PostLoad` chỉ tính trường trình bày của PurchaseOrder:

```java
@Transient
private String displayLabel;

@PostLoad
private void buildDisplayLabel() {
    displayLabel = reference == null
        ? "(chưa có mã)"
        : "Đơn " + reference;
}
```

Đây là hành vi gắn chặt với entity và không cần tái sử dụng. Giữ nó trong entity có thể dễ hiểu hơn tạo một listener chỉ chứa một method.

**Lưu ý:** `@Transient` chỉ định giá trị không persistent, không tự động biến nó thành dữ liệu đáng tin để làm validation nghiệp vụ ở nơi khác.

## 4. Listener bên ngoài entity là gì?

Một **entity listener class** là lớp Java không cần được map thành JPA entity. Nó chứa những method được đánh dấu lifecycle annotations và nhận entity đang có sự kiện.

Ví dụ:

```java
package com.example.orders;

import jakarta.persistence.PrePersist;

public class OrderRulesListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        if (entity instanceof PurchaseOrder order) {
            order.validateForPersistence();
        }
    }
}
```

Để JPA biết listener này áp dụng cho PurchaseOrder, phải đăng ký:

```java
@Entity
@EntityListeners(OrderRulesListener.class)
public class PurchaseOrder {
    // ...
}
```

### 4.1. Sự khác nhau về chữ ký method

**Callback nằm trong entity:**

```java
@PrePersist
void beforeInsert() {
    // Không nhận tham số.
}
```

**Callback nằm trong listener class:**

```java
@PrePersist
public void beforeInsert(Object entity) {
    // Nhận entity đang có sự kiện.
}
```

Dùng tham số `Object` là lựa chọn rõ ràng cho listener tái sử dụng với nhiều entity types, đồng thời tránh gắn callback vào một kiểu entity cụ thể. Trong listener, có thể dùng `instanceof` hoặc interface để thao tác an toàn với entity phù hợp.

### 4.2. Một listener có thể có nhiều callback

```java
public class OrderRulesListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        check(entity);
    }

    @PreUpdate
    public void beforeUpdate(Object entity) {
        check(entity);
    }

    private void check(Object entity) {
        if (entity instanceof PurchaseOrder order) {
            order.validateForPersistence();
        }
    }
}
```

Các annotations xác định sự kiện; tên method `beforeInsert` hay `check` không phải magic name.

### 4.3. Không viết callback như một service thông thường

Một listener JPA thường được provider tạo và quản lý theo vòng đời của nó. Đừng mặc định nó là Spring bean bình thường được constructor-inject chỉ vì class nằm trong một package Spring component scan.

Nếu cần truy cập services bên ngoài, cách tích hợp dependency injection phụ thuộc môi trường (Jakarta EE/CDI, Spring và provider). Để ví dụ portable, giữ listener **stateless**, có constructor không tham số phù hợp và thao tác trên chính entity được truyền vào.

## 5. Đăng ký listener riêng bằng @EntityListeners

Ví dụ PurchaseOrder cần một quy tắc riêng: kiểm tra mã tham chiếu và trạng thái hợp lệ trước insert/update.

```java
package com.example.orders;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "purchase_orders")
@EntityListeners(OrderRulesListener.class)
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 60)
    private String reference;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status = OrderStatus.DRAFT;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    @Version
    private Long version;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String reference) {
        this.reference = reference;
    }

    public void validateForPersistence() {
        if (reference == null || reference.isBlank()) {
            throw new IllegalStateException(
                "Order reference must not be blank"
            );
        }

        if (status == null) {
            throw new IllegalStateException(
                "Order status is required"
            );
        }
    }

    public Long getId() {
        return id;
    }

    public String getReference() {
        return reference;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public Long getVersion() {
        return version;
    }

    public void setAuditTimes(
            Instant createdAt,
            Instant updatedAt) {
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
```

Enum:

```java
package com.example.orders;

public enum OrderStatus {
    DRAFT,
    CONFIRMED,
    CANCELLED
}
```

Listener riêng:

```java
package com.example.orders;

import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;

public class OrderRulesListener {

    @PrePersist
    public void validateBeforeInsert(Object entity) {
        validate(entity);
    }

    @PreUpdate
    public void validateBeforeUpdate(Object entity) {
        validate(entity);
    }

    private static void validate(Object entity) {
        if (!(entity instanceof PurchaseOrder order)) {
            throw new IllegalArgumentException(
                "OrderRulesListener applied to wrong type"
            );
        }

        order.validateForPersistence();
    }
}
```

### 5.1. Tại sao gọi là listener riêng?

Nó chỉ được gắn cho `PurchaseOrder`, và quy tắc của nó chỉ có ý nghĩa đối với đơn hàng. Không nên đem nó đăng ký trên `Product` hoặc `Customer`.

### 5.2. Khi callback ném exception

Nếu `validateForPersistence()` ném runtime exception trong lúc JPA thực thi callback, thao tác persistence có thể thất bại và transaction liên quan bị đánh dấu rollback.

Không catch exception ngay trong listener rồi cho phép lưu entity sai một cách thầm lặng.

### 5.3. Listener không thay thế validation ở service

Ứng dụng nên kiểm tra đầu vào sớm ở controller/service/domain command để trả thông điệp rõ cho người dùng. Listener là một lớp kiểm tra bổ sung gần lifecycle persistence, không phải nơi duy nhất bảo vệ mọi rule nghiệp vụ.

Với ràng buộc database, vẫn cần `NOT NULL`, foreign keys, unique constraints và chính sách concurrency thích hợp.

## 6. Đăng ký nhiều listeners trên cùng entity

Annotation `@EntityListeners` nhận danh sách classes:

```java
@Entity
@EntityListeners({
    AuditStampListener.class,
    OrderRulesListener.class
})
public class PurchaseOrder {
    // ...
}
```

Có thể phân chia trách nhiệm:

- `AuditStampListener`: timestamps áp dụng cho nhiều entities.
- `OrderRulesListener`: invariant riêng của PurchaseOrder.

### 6.1. Thứ tự trong annotation có ý nghĩa

Với nhiều listener classes được khai báo trên cùng một entity cho cùng sự kiện, thứ tự trong `@EntityListeners({...})` là thứ tự cần được xem xét theo mô hình callback của JPA.

Ví dụ:

```text
@PrePersist:
    AuditStampListener
    OrderRulesListener
    [entity callback nếu có]
```

Nếu `OrderRulesListener` yêu cầu `createdAt` đã có, cần bảo đảm audit listener chạy trước trong quy tắc đăng ký áp dụng.

### 6.2. Đừng tạo phụ thuộc ngầm phức tạp giữa listeners

Nếu có năm listeners mỗi listener đòi state do listener khác tạo, hệ thống sẽ khó hiểu và khó bảo trì. Một cách tốt hơn là:

- Mỗi listener làm một việc độc lập.
- Quy tắc phụ thuộc phức tạp nằm trong domain service.
- Nếu thật sự cần một chuỗi xử lý có thứ tự, định nghĩa rõ trong một thành phần thay vì dựa vào quá nhiều callbacks.

### 6.3. Listener có thể kết hợp với entity callback

`@EntityListeners` không ngăn entity có một callback trực tiếp khác:

```java
@Entity
@EntityListeners({
    AuditStampListener.class,
    OrderRulesListener.class
})
public class PurchaseOrder {

    @Transient
    private String displayLabel;

    @PostLoad
    private void updateDisplayLabel() {
        displayLabel = "Đơn " + reference;
    }
}
```

Đoạn trên chỉ minh họa việc phối hợp; field `reference` và mapping đầy đủ thuộc class `PurchaseOrder` trước đó.

## 7. Tái sử dụng một listener qua nhiều entity

Chỉ một listener class có thể được khai báo trên nhiều entity types:

```java
@Entity
@EntityListeners(AuditStampListener.class)
public class Customer implements AuditStamped {
    // ...
}
```

```java
@Entity
@EntityListeners(AuditStampListener.class)
public class Product implements AuditStamped {
    // ...
}
```

```java
@Entity
@EntityListeners({
    AuditStampListener.class,
    OrderRulesListener.class
})
public class PurchaseOrder implements AuditStamped {
    // ...
}
```

Nhưng không nên giả định Java sẽ tự hiểu mọi entity đều có hai trường `createdAt` và `updatedAt`. Cần thiết kế một **hợp đồng Java** mà shared listener có thể gọi.

### 7.1. Interface cho các entity có audit timestamps

```java
package com.example.audit;

import java.time.Instant;

public interface AuditStamped {

    void setCreatedAt(Instant value);

    void setUpdatedAt(Instant value);
}
```

Các entities muốn dùng cùng listener triển khai interface này.

### 7.2. AuditStampListener dùng chung

```java
package com.example.audit;

import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.time.Instant;

public class AuditStampListener {

    @PrePersist
    public void beforeInsert(Object entity) {
        if (entity instanceof AuditStamped audit) {
            Instant now = Instant.now();

            audit.setCreatedAt(now);
            audit.setUpdatedAt(now);
        }
    }

    @PreUpdate
    public void beforeUpdate(Object entity) {
        if (entity instanceof AuditStamped audit) {
            audit.setUpdatedAt(Instant.now());
        }
    }
}
```

### 7.3. Vì sao dùng instanceof?

`AuditStampListener` có thể được đăng ký trên nhiều entity types. Chỉ entities thực hiện `AuditStamped` mới có thể nhận thao tác tương ứng.

Nếu hợp đồng của dự án bắt buộc mọi entity gắn listener phải triển khai `AuditStamped`, có thể thay nhánh bỏ qua bằng lỗi rõ ràng khi cấu hình sai:

```java
if (!(entity instanceof AuditStamped audit)) {
    throw new IllegalStateException(
        "Entity must implement AuditStamped"
    );
}
```

Nên quyết định rõ listener có hành vi **bỏ qua loại không áp dụng** hay **báo lỗi cấu hình**. Không trộn hai chính sách mà không có chủ đích.

### 7.4. Interface không tạo cột database

Chỉ có `implements AuditStamped` không tự tạo các cột persistent. Entity vẫn phải map `createdAt` và `updatedAt`, hoặc kế thừa mapping từ `@MappedSuperclass`.

### 7.5. Timestamp có thể cần Clock injection

`Instant.now()` giúp ví dụ ngắn, nhưng khiến test cố định thời gian khó hơn. Trong ứng dụng cần kiểm thử chính xác, có thể dùng một `Clock` hoặc time provider theo cơ chế dependency injection được hỗ trợ. Đừng tự giả định listener JPA luôn được Spring constructor injection.

## 8. Tái sử dụng thông qua @MappedSuperclass

Một hướng khác là đưa fields và callback chung vào một mapped superclass.

```java
package com.example.audit;

import jakarta.persistence.*;
import java.time.Instant;

@MappedSuperclass
public abstract class AuditedEntity {

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    protected void setInitialAuditTimes() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void touchUpdatedAt() {
        updatedAt = Instant.now();
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
```

Entity kế thừa:

```java
@Entity
@Table(name = "customers")
public class Customer extends AuditedEntity {

    @Id
    private Long id;

    private String name;
}
```

### 8.1. Khi nào phù hợp?

- Các entities thực sự chia sẻ **cấu trúc dữ liệu persistent**.
- Dự án chấp nhận một base type chung.
- Mọi entity kế thừa cần cùng audit callback.
- Muốn giảm trùng lặp cả fields lẫn callback logic.

### 8.2. Hạn chế

Java chỉ có **single class inheritance**, nên nếu entity đã cần một superclass khác, mô hình này có thể khó áp dụng.

Đồng thời, việc đưa logic vào superclass có thể làm mọi descendants bị ràng buộc với cùng chính sách ngay cả khi về sau một entity muốn ngoại lệ.

### 8.3. Chia sẻ listener bằng mapped superclass, nhưng không chia sẻ method callback

Một cách dung hòa:

```java
@MappedSuperclass
@EntityListeners(AuditStampListener.class)
public abstract class AuditTrackedEntity
        implements AuditStamped {

    @Column(nullable = false)
    protected Instant createdAt;

    @Column(nullable = false)
    protected Instant updatedAt;

    @Override
    public void setCreatedAt(Instant value) {
        createdAt = value;
    }

    @Override
    public void setUpdatedAt(Instant value) {
        updatedAt = value;
    }
}
```

Lúc này subclass kế thừa mapping fields và **listener registration** từ mapped superclass; listener logic vẫn nằm trong lớp riêng.

### 8.4. Ba mô hình nên phân biệt

| Mô hình | Chia sẻ mapping | Chia sẻ callback logic | Cần entity đăng ký riêng? |
| --- | --- | --- | --- |
| Lặp lại `@EntityListeners` trên từng entity | Không | Có | Có |
| Entity kế thừa `@MappedSuperclass` có callbacks | Có | Có, qua kế thừa method | Không trên từng subclass |
| Entity kế thừa `@MappedSuperclass` có `@EntityListeners` | Có | Có, qua listener class | Không trên từng subclass |

Lựa chọn phụ thuộc việc các entity có thật sự chung một mô hình dữ liệu hay chỉ muốn chung xử lý kỹ thuật.

## 9. Listener dùng chung không đồng nghĩa listener mặc định

Hai cách dễ bị nhầm:

**Listener dùng chung bằng Java annotation:**

```java
@EntityListeners(AuditStampListener.class)
public class Customer { /* ... */ }
```

và:

```java
@EntityListeners(AuditStampListener.class)
public class Product { /* ... */ }
```

Cùng một listener class nhưng vẫn có **đăng ký rõ ràng** ở các entity hoặc superclass.

**Default entity listener cấp persistence unit:**

Được cấu hình thông qua `orm.xml` ở metadata mặc định; nó có thể áp dụng cho các entities trong phạm vi persistence unit theo quy tắc của JPA, không cần lặp annotation trên từng entity.

### 9.1. Khi nào nên chọn shared annotations?

- Muốn kiểm soát chính xác entity nào có audit.
- Một số entity không được tự ghi timestamp.
- Có policy khác nhau theo nhóm entity.
- Muốn đọc source code entity là thấy ngay listener được áp dụng.
- Dự án không muốn dùng XML metadata cho việc này.

### 9.2. Khi nào nên chọn default listener?

- Quy tắc thực sự phổ biến trên hầu hết entities.
- Muốn đăng ký tập trung cấp persistence unit.
- Muốn tách metadata kỹ thuật khỏi các entity classes.
- Cần policy có khả năng exclude những entity ngoại lệ.

**Không tự suy rằng “dùng chung nhiều nơi” có nghĩa phải cấu hình thành default listener.** Default listener có phạm vi rộng hơn và khả năng tạo side effects ngoài dự kiến lớn hơn.

## 10. Đăng ký listener mặc định qua orm.xml

JPA hỗ trợ XML object–relational mapping metadata, thường đặt tại:

```text
src/main/resources/META-INF/orm.xml
```

Có thể đăng ký một default listener trong `persistence-unit-defaults`.

### 10.1. Ví dụ GlobalLifecycleListener

```java
package com.example.audit;

import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.util.logging.Logger;

public class GlobalLifecycleListener {

    private static final Logger LOG =
        Logger.getLogger(
            GlobalLifecycleListener.class.getName()
        );

    @PrePersist
    public void beforeInsert(Object entity) {
        LOG.fine(
            "Preparing entity insert: " +
            entity.getClass().getName()
        );
    }

    @PreUpdate
    public void beforeUpdate(Object entity) {
        LOG.fine(
            "Preparing entity update: " +
            entity.getClass().getName()
        );
    }
}
```

Đây là minh họa kỹ thuật tối giản. Trong ứng dụng sản xuất, log ở mức lifecycle cho mọi entity có thể tạo **khối lượng log rất lớn**, có thể chứa thông tin nhạy cảm nếu ghi thêm fields; nên sử dụng có kiểm soát.

### 10.2. orm.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<entity-mappings
    xmlns="https://jakarta.ee/xml/ns/persistence/orm"
    version="3.1">

    <persistence-unit-metadata>
        <persistence-unit-defaults>
            <entity-listeners>
                <entity-listener
                    class="com.example.audit.GlobalLifecycleListener">

                    <pre-persist
                        method-name="beforeInsert"/>

                    <pre-update
                        method-name="beforeUpdate"/>

                </entity-listener>
            </entity-listeners>
        </persistence-unit-defaults>
    </persistence-unit-metadata>

</entity-mappings>
```

Ở đây:

- `entity-mappings` là root XML metadata.
- `persistence-unit-defaults` chứa các mặc định áp dụng trong persistence unit.
- `entity-listeners` đăng ký các default entity listener classes.
- `entity-listener class="..."` dùng tên class đầy đủ.
- `pre-persist` / `pre-update` liên kết event với method tương ứng.

**XML được minh họa theo nhánh Jakarta Persistence 3.x.** Khi dự án sử dụng version đặc tả khác, namespace/schema/version cần tương thích với Jakarta Persistence version thực tế.

### 10.3. Kết nối mapping file với persistence unit

Trong `persistence.xml` có thể khai báo explicit mapping file:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit name="catalogPU">
        <mapping-file>META-INF/orm.xml</mapping-file>

        <!-- Các class, datasource và properties khác
             được cấu hình theo môi trường ứng dụng. -->
    </persistence-unit>

</persistence>
```

Đây là file cấu hình rút gọn mang tính minh họa. Trong dự án thực tế, cần thêm những thành phần phù hợp với môi trường, chẳng hạn connection settings, provider, managed classes hoặc datasource/JTA settings.

Một số cấu hình có thể tự nhận diện `META-INF/orm.xml` mặc định; khai báo `mapping-file` rõ ràng giúp thể hiện chủ đích và nên kiểm chứng theo cơ chế bootstrap đang dùng.

### 10.4. Tại sao không dùng @EntityListeners cho default listener?

`@EntityListeners` là annotation gắn với entity/mapped superclass. Nó không tự tạo quy tắc “mọi entity trong persistence unit đều đăng ký listener class này”.

Default listeners cấp persistence unit được khai báo bằng XML metadata chuẩn hoặc cơ chế provider-specific khác. Không nhầm hai hình thức.

### 10.5. Không trộn annotation và XML tùy tiện

Khi cùng một entity có:

- Default listener từ XML.
- Listener kế thừa từ mapped superclass.
- Listener riêng qua `@EntityListeners`.
- Entity callback trực tiếp.

tất cả có thể tham gia lifecycle event theo thứ tự áp dụng. Cần tránh cùng một hành vi audit được đăng ký lặp ở nhiều tầng gây nhiều lần gọi hoặc side effects không mong muốn.

Một chính sách rõ ràng hơn là xác định **một điểm đăng ký chủ đạo cho từng loại hành vi**.

## 11. Loại trừ default listeners bằng @ExcludeDefaultListeners

Một entity có thể không muốn nhận default listener.

Ví dụ `AuditEvent` là bảng lưu bản ghi audit; nếu default listener của toàn persistence unit lại ghi audit mỗi khi lưu `AuditEvent`, hệ thống có thể phát sinh vòng lặp logic hoặc ghi không cần thiết.

JPA hỗ trợ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.ExcludeDefaultListeners;

@Entity
@ExcludeDefaultListeners
public class AuditEvent {

    @Id
    private Long id;

    // ...
}
```

### 11.1. Tác động

`@ExcludeDefaultListeners` chỉ định bỏ qua những **default entity listeners** theo quy tắc inheritance/metadata áp dụng.

Nó không có nghĩa:

- Bỏ qua hoàn toàn mọi callback trong entity.
- Bỏ qua tất cả listeners riêng mà entity đăng ký.
- Vô hiệu hóa JPA dirty checking.
- Bỏ qua database triggers hoặc database constraints.
- Vô hiệu hóa Bean Validation một cách tổng quát.

### 11.2. Khi nào nên dùng?

- Entity kỹ thuật có policy riêng.
- Entity đại diện cho audit/outbox nhưng không nên áp các default hooks.
- Entity có dữ liệu bất biến không thích hợp với policy mặc định.
- Có requirement giảm overhead trên một nhóm entity cụ thể.

### 11.3. Điều gì xảy ra nếu sau đó vẫn muốn listener riêng?

Có thể kết hợp:

```java
@Entity
@ExcludeDefaultListeners
@EntityListeners(AuditEventRulesListener.class)
public class AuditEvent {
    // ...
}
```

Ý định là loại default listener nhưng vẫn dùng listener **riêng** được đăng ký cho entity.

## 12. Loại trừ listener kế thừa bằng @ExcludeSuperclassListeners

Listener được khai báo trên entity superclass hoặc mapped superclass có thể được kế thừa trong callback configuration của descendants.

Ví dụ:

```java
@MappedSuperclass
@EntityListeners(AuditStampListener.class)
public abstract class AuditTrackedEntity {
    // ...
}
```

Một subclass:

```java
@Entity
public class Product extends AuditTrackedEntity {
    // ...
}
```

có thể nhận `AuditStampListener` do thừa kế metadata từ superclass.

Nếu một descendant cần **không kế thừa listener đó**, JPA hỗ trợ:

```java
@Entity
@ExcludeSuperclassListeners
public class SpecialProduct extends AuditTrackedEntity {
    // ...
}
```

### 12.1. Phạm vi của @ExcludeSuperclassListeners

Annotation này loại trừ **superclass entity listeners** theo semantics JPA.

Không được coi nó là “tắt hết callback của tất cả superclasses” theo nghĩa tùy ý; **entity callback methods được định nghĩa trực tiếp trong superclass** và listener classes là hai cơ chế khác nhau, cần phân biệt.

### 12.2. Hai annotations exclude không thay thế nhau

| Annotation | Nhóm bị ảnh hưởng |
| --- | --- |
| `@ExcludeDefaultListeners` | Default listeners cấp persistence unit |
| `@ExcludeSuperclassListeners` | Listeners được kế thừa từ superclass theo JPA |
| Cả hai | Hai nhóm listener tương ứng |
| Không có | Các listeners áp dụng theo metadata/inheritance thông thường |

Nếu subclass muốn bỏ cả hai nhóm, có thể dùng cả hai annotations theo nhu cầu.

### 12.3. Không dùng exclude để thay đổi policy một cách khó hiểu

Nếu một mô hình có quá nhiều subclasses và các quy tắc exclude chồng chéo, việc suy ra chính xác listener nào chạy trở nên khó khăn. Khi đó nên xem xét tách hierarchy hoặc dùng đăng ký tường minh theo entity thay vì một default quá rộng.

## 13. Thứ tự thực thi callbacks giữa các nhóm

Khi nhiều callbacks áp dụng cùng một sự kiện, cần hiểu rằng thứ tự **không tùy tiện hoàn toàn**.

Ở mức khái quát theo JPA:

1. **Default entity listeners** của persistence unit, nếu không bị exclude.
2. **Entity listeners được kế thừa** từ các superclass/mapped superclasses, đi từ cấp tổng quát tới cấp cụ thể theo quy tắc JPA.
3. **Entity listeners khai báo trên entity**; thứ tự trong danh sách `@EntityListeners` có ý nghĩa.
4. **Callback methods nằm trong entity hierarchy**, với những quy tắc kế thừa và override tương ứng.

XML metadata có thể tham gia vào việc khai báo và thứ tự; không nên dựa vào một thứ tự tự suy đoán nếu dự án kết hợp annotation và XML phức tạp.

### 13.1. Ví dụ sơ đồ

```text
Persistence unit default:
    GlobalLifecycleListener

@MappedSuperclass AuditTrackedEntity:
    AuditStampListener

@Entity PurchaseOrder:
    OrderRulesListener
    @PrePersist localCallback()

Possible @PrePersist processing:

GlobalLifecycleListener.beforeInsert
       |
       v
AuditStampListener.beforeInsert
       |
       v
OrderRulesListener.beforeInsert
       |
       v
PurchaseOrder.localCallback
```

Sơ đồ trên minh họa **ý tưởng thứ tự theo tầng đăng ký** trong một cấu hình đơn giản.

### 13.2. Vì sao thứ tự ảnh hưởng correctness?

Nếu OrderRulesListener kiểm tra:

```java
if (order.getCreatedAt() == null) {
    throw new IllegalStateException();
}
```

nhưng AuditStampListener lại là nơi điền createdAt, thứ tự hai listeners có thể quyết định kết quả.

Giải pháp tốt nhất thường là:

- Giảm phụ thuộc giữa callbacks.
- Định nghĩa contract rõ.
- Dùng service/domain method để điều phối những logic có quan hệ nhân quả phức tạp.
- Kiểm thử thứ tự trong cấu hình JPA thực tế.

### 13.3. Multiple listener classes

```java
@EntityListeners({
    FirstListener.class,
    SecondListener.class
})
```

khác với:

```java
@EntityListeners({
    SecondListener.class,
    FirstListener.class
})
```

nếu cả hai callbacks cùng tham gia một lifecycle event và hành vi phụ thuộc thứ tự.

### 13.4. Một listener nên có trách nhiệm rõ

Đừng chia một validation rule thành năm listeners rồi chỉ dựa vào thứ tự annotation để tạo nên một business workflow. Lifecycle callbacks phù hợp với hành vi ngắn, gần lifecycle; còn workflow có bước điều phối nên nằm ở service.

## 14. Listener riêng, listener dùng chung và default listener: bảng so sánh

| Tiêu chí | Listener riêng qua `@EntityListeners` | Listener dùng chung trên nhiều entities | Default listener qua XML |
| --- | --- | --- | --- |
| Phạm vi | Một entity / nhóm khai báo rõ | Nhiều entities đăng ký hoặc kế thừa | Rộng trong persistence unit |
| Khả năng tái sử dụng | Có thể, nhưng thường chuyên biệt | Cao | Cao và phạm vi rộng |
| Nơi đăng ký | Entity annotation | Nhiều entity annotations hoặc mapped superclass | `orm.xml` |
| Dễ tìm từ source entity | Rõ ràng | Rõ nếu annotation trực tiếp, gián tiếp nếu kế thừa | Phải xem cấu hình XML |
| Rủi ro tác động entity không liên quan | Thấp | Phụ thuộc điểm đăng ký | Cao hơn nếu logic không lọc |
| Cách ngoại lệ | Gỡ/đổi registration | Tách hierarchy/registration | `@ExcludeDefaultListeners` |
| Phù hợp | Quy tắc PurchaseOrder | Audit timestamps chung | Logging/chính sách thật sự phổ biến |
| Độ phức tạp | Thấp | Trung bình | Trung bình đến cao |

Không có một phương án tốt nhất cho mọi ứng dụng. Chọn theo **phạm vi quy tắc**, **mức độc lập**, **rủi ro side effect** và **khả năng quan sát cấu hình**.

## 15. Lifecycle callback khác EntityManager lifecycle operation

Một lỗi khái niệm là coi callbacks có thể thay thế mọi service gọi `persist()`, `merge()`, `remove()` hay `refresh()`.

Trong thực tế:

```java
em.persist(order);
```

yêu cầu chuyển entity mới vào persistence context. Callback là logic **được kích hoạt trong quá trình** xử lý lifecycle đó.

Tương tự:

```java
em.remove(order);
```

là operation xóa theo lifecycle; `@PreRemove` và `@PostRemove` có thể tham gia các mốc phù hợp.

### 15.1. Listener không tự được gọi khi tạo object

```java
PurchaseOrder order = new PurchaseOrder("PO-100");
```

Nếu không có JPA lifecycle operation, `@PrePersist` không chạy chỉ vì constructor hoàn thành.

### 15.2. Listener không tự chạy với mọi SQL UPDATE

```java
em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :status " +
    "WHERE o.id = :id"
)
.setParameter("status", OrderStatus.CONFIRMED)
.setParameter("id", 101L)
.executeUpdate();
```

JPQL **bulk UPDATE** không đi qua lifecycle update từng managed entity giống dirty checking thông thường. **Không nên dựa vào `@PreUpdate`/`@PostUpdate` để xử lý toàn bộ từng row bị bulk DML tác động.**

Tương tự, bulk DELETE, native SQL, JDBC jobs, stored procedures và database triggers không mặc nhiên kích hoạt callback JPA của từng entity.

### 15.3. Vì sao quan trọng đối với audit?

Nếu `updatedAt` chỉ được set trong `@PreUpdate`, một bulk JPQL UPDATE hoặc external writer có thể bỏ qua callback và không cập nhật timestamp.

Khi dự án có nhiều đường ghi dữ liệu, cần thiết kế audit consistency ở cấp hệ thống:

- Managed-entity writes dùng JPA listener.
- Bulk DML phải tự cập nhật audit columns phù hợp.
- External writers dùng rule tương ứng hoặc database-side mechanism.
- Database triggers nếu chọn thì phải có chính sách tránh cập nhật trùng/xung đột với JPA mapping.

## 16. Callback chạy trong transaction, không phải sau commit

Đây là giới hạn quan trọng nhất khi dùng listeners trong nghiệp vụ có side effects.

Ví dụ sai:

```java
public class OrderNotificationListener {

    @PostPersist
    public void notifyCustomer(Object entity) {
        if (entity instanceof PurchaseOrder order) {
            emailClient.sendConfirmation(
                order.getReference()
            );
        }
    }
}
```

Giả sử `@PostPersist` chạy, email đã được gửi, sau đó transaction rollback vì constraint violation hoặc optimistic conflict. Khách hàng nhận “đặt hàng thành công” dù đơn chưa được commit.

### 16.1. PostPersist không có nghĩa commit thành công

Cần phân biệt:

```text
EntityManager.persist
       |
       v
@PrePersist
       |
       v
SQL INSERT / generated ID
       |
       v
@PostPersist
       |
       v
Other SQL / validations
       |
       +-- COMMIT succeeds
       |
       +-- OR transaction ROLLBACKS
```

Thời điểm chính xác của insert và callbacks có thể phụ thuộc chiến lược ID và provider. Sơ đồ chỉ nhấn mạnh: **@PostPersist có thể xảy ra trước kết quả commit cuối cùng**.

### 16.2. Giải pháp: domain event sau commit

Nếu cần phát một event sau khi transaction thành công:

- Domain service có thể ghi thay đổi và điều phối sự kiện sau commit theo transaction manager.
- Spring có `@TransactionalEventListener(phase = AFTER_COMMIT)` cho những tình huống thích hợp.
- Với yêu cầu tin cậy cao, dùng **transactional outbox**: ghi event vào bảng outbox trong cùng transaction, worker riêng phát hành sau commit.

### 16.3. Outbox phù hợp hơn cho nghiệp vụ cần bảo đảm

```text
Transaction:
    INSERT PurchaseOrder
    INSERT OutboxEvent(OrderCreated)
            |
          COMMIT
            |
        Dispatcher
            |
     Email/message broker
```

Nếu transaction rollback, cả Order và OutboxEvent đều rollback. Worker gửi có thể cần idempotency vì message delivery thường không bảo đảm exactly-once.

### 16.4. Không gọi EntityManager/Query tùy tiện trong callback

Để tăng khả chuyển, lifecycle callback nên ưu tiên:

- Đọc/điều chỉnh scalar state của entity đang được xử lý.
- Kiểm tra giá trị đơn giản.
- Tính field không persistent.

Tránh:

- Gọi `EntityManager.persist()`/`remove()` trên entity khác trong callback.
- Thực hiện query đòi flush lồng nhau.
- Thay đổi relationships phức tạp.
- Truy cập nhiều entities khác trong cùng persistence context.
- Tạo transaction mới.
- Gọi external service không thể rollback.

Đây là những thao tác làm callback khó dự đoán, dễ gây recursion hoặc gặp giới hạn provider.

## 17. Callback và truy cập quan hệ entity

Giả sử Order có collection:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Một listener:

```java
@PostLoad
public void calculateTotal(Object entity) {
    PurchaseOrder order = (PurchaseOrder) entity;

    BigDecimal total = order.getLines()
        .stream()
        .map(OrderLine::getAmount)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```

Mẫu này có vấn đề:

- `lines` có thể LAZY.
- Truy cập lines trong `@PostLoad` có thể kích hoạt SQL bất ngờ.
- Có thể gây N+1 khi tải danh sách Orders.
- Callback có thể chạy trong lúc provider còn đang dựng entity graph.
- Tính tổng từ collection có thể là logic domain nên được thực hiện ở service/query phù hợp hơn.

### 17.1. Nên làm gì?

Nếu cần tổng tiền trong trang danh sách:

- Dùng JPQL aggregation/DTO projection.
- Dùng cột tổng đã được duy trì theo domain rule.
- Tải association có chủ đích trong service khi cần.
- Chỉ dùng `@PostLoad` cho những giá trị tính toán từ **fields đã sẵn có** của cùng entity nếu phù hợp.

### 17.2. @PostLoad và refresh

`EntityManager.refresh(entity)` có thể làm JPA tải lại state entity và kích hoạt callback `@PostLoad` theo vòng đời. Nhưng không dùng `refresh` chỉ để chạy lại một callback, vì nó còn có semantics làm mới dữ liệu từ database và có thể ghi đè managed changes.

## 18. Listener và ID được tạo bởi database

Một bẫy khác là dùng ID quá sớm trong `@PrePersist`.

Ví dụ:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Với chiến lược `IDENTITY`, ID có thể chỉ có sau insert vào database. Trong `@PrePersist`, **không được giả định ID đã có giá trị**.

### 18.1. Không dùng @PrePersist để bắt buộc ID do DB sinh

Sai:

```java
@PrePersist
void beforeInsert() {
    auditMessage = "Inserted entity " + id.toString();
}
```

Nếu `id == null`, code sẽ lỗi.

### 18.2. @PostPersist có thể quan sát ID

`@PostPersist` là mốc phù hợp hơn để tham khảo ID generated theo lifecycle contract của JPA. Nhưng **đó vẫn không phải sau commit**, nên không gửi sự kiện bên ngoài chỉ vì ID đã tồn tại.

### 18.3. UUID do ứng dụng tạo

Nếu ứng dụng chủ động tạo UUID trước persist, `@PrePersist` có thể thấy ID đó. Tuy nhiên, chính sách phát sinh ID nên được định nghĩa thống nhất; không xây listener phụ thuộc ngầm vào một strategy của provider nếu muốn khả chuyển.

## 19. Listener có thể thay đổi field nào?

Một câu hỏi thực tế:

> “Có được sửa dữ liệu của entity trong @PrePersist hoặc @PreUpdate không?”

Có thể dùng callback để thiết lập **non-relationship persistent state** của entity đang được xử lý, ví dụ timestamps hoặc normalize chuỗi.

```java
@PrePersist
public void beforePersist(Object entity) {
    if (entity instanceof Product product) {
        product.normalizeSku();
    }
}
```

### 19.1. Thao tác phù hợp

- Gán `createdAt`.
- Gán `updatedAt`.
- Chuẩn hóa một scalar field.
- Điền một giá trị mặc định hợp lệ.
- Tính `@Transient` derived value sau load.
- Kiểm tra một invariant đơn giản của entity.

### 19.2. Thao tác nên tránh

- Sửa foreign keys/relationship graph một cách phức tạp.
- Gọi cascading persist/remove trên entity khác từ callback.
- Truy vấn database để tìm entity khác.
- Duyệt LAZY collections gây N+1.
- Tạo thread hoặc transaction từ listener.
- Gọi external systems.
- Ném lỗi vì một service bên ngoài không khả dụng.

Trong một thiết kế portable, lifecycle callbacks nên **ngắn, đồng bộ và dễ dự đoán**.

### 19.3. Không dùng listener để xử lý mọi business rule

Ví dụ “đơn có đủ hàng và khách hàng còn hạn mức công nợ” đòi đọc nhiều aggregates và có concurrency requirement. Nó thuộc domain service/transaction logic, không phải một `@PreUpdate` đơn giản.

## 20. Listener dùng chung nên stateless

Một listener có thể được provider tái sử dụng theo lifecycle/implementation riêng. Không nên đặt mutable request state trong fields của listener:

```java
public class UnsafeAuditListener {

    private Long lastProcessedEntityId;

    @PreUpdate
    public void beforeUpdate(Object entity) {
        lastProcessedEntityId = extractId(entity);
    }
}
```

Các invocations đồng thời có thể trộn state và làm hành vi khó dự đoán.

### 20.1. Thiết kế stateless

```java
public class AuditStampListener {

    @PreUpdate
    public void beforeUpdate(Object entity) {
        if (entity instanceof AuditStamped audit) {
            audit.setUpdatedAt(Instant.now());
        }
    }
}
```

Mọi dữ liệu cần xử lý đến từ tham số entity hoặc cấu hình bất biến phù hợp. Listener không ghi giữ entity vào instance field cho callback tiếp theo.

### 20.2. Không giữ managed entity trong static collection

Ví dụ:

```java
static List<Object> pendingAudit = new ArrayList<>();
```

rồi append mỗi callback là nguy hiểm:

- Có thể memory leak.
- Entity có thể detach/đổi state.
- Không phản ánh commit/rollback.
- Không an toàn khi concurrent.
- Đưa JPA-managed objects ra ngoài persistence context.

Nếu cần audit event bền vững, dùng domain event/outbox thích hợp thay vì giữ entity trong bộ nhớ listener.

### 20.3. Dependency injection là chi tiết môi trường

Trong Jakarta EE/CDI integration, entity listeners có thể được hỗ trợ injection theo môi trường. Trong Java SE hoặc cấu hình Spring/Hibernate khác, hành vi có thể khác.

Không viết listener bắt buộc một `@Autowired` field phải có giá trị rồi giả định mọi JPA provider đều đáp ứng. Với yêu cầu portable, tách logic thuần Java hoặc dùng tích hợp DI được tài liệu hóa/kiểm thử cho đúng stack.

## 21. Listener và Bean Validation

JPA có thể tích hợp Bean Validation; entity có thể dùng:

```java
@NotBlank
@Column(nullable = false)
private String reference;
```

Callback riêng:

```java
@PrePersist
public void beforePersist(Object entity) {
    // ...
}
```

có thể bổ sung quy tắc, nhưng cần phân biệt:

| Cơ chế | Mục đích |
| --- | --- |
| Jakarta Bean Validation `@NotNull`, `@NotBlank`, custom validators | Ràng buộc dữ liệu theo nhóm validation |
| Database `NOT NULL`, `CHECK`, `UNIQUE` | Bảo vệ dữ liệu ở DB |
| JPA lifecycle callback | Xử lý logic tại mốc lifecycle entity |
| Domain service | Điều phối use case, nhiều entities/transactions |
| Transaction/version/lock | Kiểm soát concurrency |

### 21.1. Không phụ thuộc một mình vào @PrePersist

Nếu ứng dụng cập nhật entity bằng bulk query, callback không được kích hoạt theo từng entity, trong khi database constraints vẫn có thể ngăn dữ liệu sai.

### 21.2. Thứ tự callback và validation có thể ảnh hưởng

Nếu callback chuẩn hóa chuỗi trước persist và Bean Validation kiểm tra chuỗi, cần hiểu thời điểm lifecycle/validation tích hợp của stack đang dùng. Không nên dựa vào giả định thứ tự phức tạp mà chưa test integration.

### 21.3. Callback ném RuntimeException

Nếu callback phát hiện state sai và ném unchecked exception, thao tác persistence trong transaction sẽ thất bại và transaction có thể bị đánh dấu rollback. Không nên bắt lỗi rồi tiếp tục commit như thể entity đã được lưu đúng.

## 22. Cascades và thứ tự callbacks giữa entities

Một `PurchaseOrder` có nhiều `OrderLine`:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

`em.persist(order)` có thể cascade persist xuống child entities. Nếu cả parent và child đều có listeners, các callbacks tương ứng có thể được kích hoạt cho từng entity.

Nhưng cần phân biệt:

- **Thứ tự listeners của một entity cho cùng sự kiện** có quy tắc JPA.
- **Thứ tự callbacks giữa nhiều entity instances trong một cascade/flush** không nên bị dùng làm business workflow ordering tuyệt đối.

### 22.1. Điều không nên giả định

Không nên viết:

```text
Parent @PostPersist -> luôn gửi dữ liệu cho child listener
Child @PrePersist -> luôn chạy sau khi parent đã commit
```

Parent có thể chưa commit, SQL ordering tùy provider, ID generation và cascade strategy. Nếu child cần parent ID/state, dùng mapping và relationship management đúng trong domain model, không dùng callback order như cơ chế thông điệp giữa entities.

### 22.2. Không dùng callback để tự tạo cascade

Nếu cần persist child cùng parent, dùng `CascadeType.PERSIST` có chủ đích hoặc service gọi `persist()` phù hợp. Không tự viết `em.persist(child)` trong `@PrePersist` của parent rồi kỳ vọng portable và không recursion.

## 23. Listener và inheritance hierarchy

Giả sử:

```text
@MappedSuperclass AbstractDocument
   @EntityListeners(DocumentAuditListener)
       |
       +-- @Entity Invoice
       |       @EntityListeners(InvoiceRulesListener)
       |
       +-- @Entity CreditNote
               @ExcludeSuperclassListeners
               @EntityListeners(CreditNoteRulesListener)
```

Ở đây:

- `Invoice` có thể nhận listener kế thừa từ AbstractDocument và listener riêng của Invoice.
- `CreditNote` có thể loại listener kế thừa từ superclass theo semantics `@ExcludeSuperclassListeners`.
- Default listeners của persistence unit là một nhóm riêng, xử lý bằng `@ExcludeDefaultListeners` khi cần.

### 23.1. Đừng nhầm callback method kế thừa và listener class kế thừa

**Method callback trong mapped superclass:**

```java
@MappedSuperclass
public abstract class AbstractDocument {

    @PrePersist
    protected void beforeInsert() {
        // ...
    }
}
```

**Listener class được khai báo trên mapped superclass:**

```java
@MappedSuperclass
@EntityListeners(DocumentAuditListener.class)
public abstract class AbstractDocument {
    // ...
}
```

Chúng không phải một cơ chế duy nhất. `@ExcludeSuperclassListeners` được thiết kế để điều chỉnh **inherited listener classes**, không phải dùng như một công tắc tổng quát xóa mọi method callback của base type.

### 23.2. Override callbacks

Khi subclass override methods của superclass, cách JPA xem các callback methods liên quan có quy tắc kế thừa và override theo đặc tả. Không nên override một callback chỉ để “ngăn nó chạy” mà không hiểu metadata inheritance. Nếu cần policy khác biệt, thiết kế rõ với listeners/exclusions hoặc base class APIs thay vì dùng override như một mẹo không kiểm chứng.

## 24. Không nhầm entity listener với Hibernate EventListener

Trong hệ sinh thái Hibernate, còn có event system mở rộng với các loại listener cho persist/update/flush/load hoặc collection events. Chúng có thể cung cấp khả năng khác JPA lifecycle callbacks.

### 24.1. JPA standard

```java
@EntityListeners(MyListener.class)
@PrePersist
@PostLoad
```

Đây là những thành phần theo Jakarta Persistence.

### 24.2. Provider-specific

Các interface, APIs, event types hoặc service registry của Hibernate/Event system **không nằm trong bộ annotation lifecycle chuẩn JPA**.

Chúng có thể phù hợp khi cần logic sâu hơn trong persistence engine, nhưng đổi JPA provider có thể yêu cầu viết lại.

### 24.3. Khi nào chấp nhận provider extension?

- Cần intercept SQL/bulk/collection events ở mức không có trong JPA standard.
- Cần audit infrastructure chuyên sâu.
- Provider được xác định cố định trong sản phẩm.
- Có integration tests và tài liệu phụ thuộc version.

Không nên gọi một callback Hibernate-specific là “default listener của JPA” nếu nó được cài bằng API provider.

## 25. Một thiết kế hoàn chỉnh: audit chung và rules riêng

Giả sử module bán hàng có ba entity: `Customer`, `Product`, `PurchaseOrder`.

**Mục tiêu:**

- Customer, Product, PurchaseOrder đều có `createdAt` và `updatedAt`.
- PurchaseOrder có quy tắc riêng về `reference`.
- AuditEvent không áp chính sách audit chung.
- Không gửi thông báo email trực tiếp trong callback.
- Một số thao tác batch update cần tự xử lý audit columns vì bypass callbacks.

### 25.1. Cấu trúc Java gợi ý

```text
com.example.audit
    AuditStamped.java
    AuditStampListener.java
    AuditTrackedEntity.java

com.example.orders
    PurchaseOrder.java
    OrderRulesListener.java
    OrderStatus.java

com.example.catalog
    Product.java

com.example.customer
    Customer.java
```

### 25.2. Quyết định đăng ký

**Lựa chọn A — annotations riêng từng entity:**

```java
@EntityListeners(AuditStampListener.class)
public class Product implements AuditStamped {
    // ...
}

@EntityListeners(AuditStampListener.class)
public class Customer implements AuditStamped {
    // ...
}

@EntityListeners({
    AuditStampListener.class,
    OrderRulesListener.class
})
public class PurchaseOrder implements AuditStamped {
    // ...
}
```

**Lựa chọn B — mapped superclass:**

```java
@MappedSuperclass
@EntityListeners(AuditStampListener.class)
public abstract class AuditTrackedEntity
        implements AuditStamped {
    // mapped audit fields
}

@Entity
public class Product extends AuditTrackedEntity {
    // ...
}

@Entity
@EntityListeners(OrderRulesListener.class)
public class PurchaseOrder
        extends AuditTrackedEntity {
    // ...
}
```

**Lựa chọn C — default listener qua XML:**

Nếu audit policy thật sự áp cho gần như mọi entity, có thể đăng ký default listener, kèm `@ExcludeDefaultListeners` ở entity ngoại lệ. Khi ấy listener phải xử lý an toàn những entity không có audit fields.

**Không kích hoạt cùng một AuditStampListener đồng thời ở cả ba con đường cho cùng entity** nếu chưa kiểm soát cách metadata/lifecycle xử lý đăng ký lặp.

### 25.3. Vì sao tách OrderRulesListener?

Audit timestamps là policy kỹ thuật dùng chung. Kiểm tra reference/status của PurchaseOrder thuộc domain cụ thể. Hai trách nhiệm thay đổi bởi các lý do khác nhau nên để thành listeners khác nhau hoặc domain method riêng.

### 25.4. Business rules phức tạp nằm trong service

```java
@Transactional
public void confirmOrder(long orderId) {
    PurchaseOrder order =
        orderRepository.findById(orderId).orElseThrow();

    // Load/check inventory, customer status,
    // payment authorization... theo use case.

    order.confirm();

    // Ghi outbox theo transaction nếu cần.
}
```

Không đưa phần kiểm tra kho, thanh toán hoặc gọi các repository khác vào `@PreUpdate` của PurchaseOrder.

## 26. Kiểm thử listener riêng và listener dùng chung

Một unit test trực tiếp gọi method Java có thể xác nhận logic của listener, nhưng không chứng minh JPA đã **đăng ký** và **kích hoạt** listener đúng.

Ví dụ:

```java
AuditStampListener listener =
    new AuditStampListener();

listener.beforeInsert(new Product(...));
```

chỉ kiểm tra method chạy khi được gọi thủ công; nó không xác nhận:

- Annotation `@EntityListeners` được nhận diện.
- XML `orm.xml` đã được load.
- Listener kế thừa từ superclass.
- Exclusion annotations được áp dụng.
- @PreUpdate có thực sự kích hoạt khi flush.
- @PostLoad chạy khi provider nạp entity.

Vì vậy cần integration tests trên JPA provider thật.

### 26.1. Ma trận kiểm thử gợi ý

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Persist PurchaseOrder mới | Audit listener và OrderRulesListener cùng được gọi |
| Persist Customer | AuditStampListener chạy, OrderRulesListener không chạy |
| Update Product với persistent changes | `updatedAt` được cập nhật theo policy |
| Load entity từ persistence context mới | Callback `@PostLoad` chạy theo tình huống |
| Remove entity | `@PreRemove`/`@PostRemove` nếu được đăng ký |
| Entity không có modifications | Không dựa vào `@PreUpdate` để làm side effects |
| Default listener qua orm.xml | Có chạy trên entity thuộc phạm vi mặc định |
| Entity có `@ExcludeDefaultListeners` | Default listener không chạy |
| Subclass có `@ExcludeSuperclassListeners` | Inherited listener bị loại theo kỳ vọng |
| Kết hợp default/superclass/entity listeners | Thứ tự callbacks đúng và không có effects ngoài dự kiến |
| JPQL bulk UPDATE | Không nhầm là từng entity `@PreUpdate` |
| Transaction rollback sau @PostPersist | Không có thông báo external được gửi sai |
| Nhiều entities trong cascade | Không phụ thuộc thứ tự callbacks giữa entities |

### 26.2. Tách persistence contexts khi kiểm thử load

Nếu test:

```java
Product p1 = em.find(Product.class, 101L);
Product p2 = em.find(Product.class, 101L);
```

trong cùng EntityManager, `p2` có thể là instance đã managed. Không nên coi hai `find` là hai lượt load độc lập.

Để kiểm thử `@PostLoad` trong ngữ cảnh phù hợp:

1. Commit và đóng EntityManager đã persist.
2. Tạo EntityManager khác.
3. Gọi `find()` hoặc query để nạp entity.
4. Xác nhận derived state/counter test phù hợp.

Không dựa vào callback count để suy số lượng SQL SELECT vì L1/L2 caching còn ảnh hưởng truy vấn.

### 26.3. Test @PreUpdate cần sửa persistent field

Một integration test phải thay đổi field được JPA map:

```java
tx.begin();

Product product = em.find(Product.class, 101L);
product.changePrice(new BigDecimal("120.00"));

em.flush();

tx.commit();
```

Không chỉ load entity rồi commit không đổi gì và khẳng định `@PreUpdate` luôn phải chạy.

### 26.4. Test XML default listener

Cần bootstrap đúng persistence unit có mapping file. Một test chỉ instantiate listener class thủ công không xác nhận `orm.xml` đã được đưa vào metadata.

### 26.5. Test thứ tự callback với một trace đơn giản

Có thể dùng một test-only trace collector an toàn trong phạm vi một test, ghi các marker:

```text
default.prePersist
superclassListener.prePersist
entityListener.prePersist
entityCallback.prePersist
```

Sau đó so với expected order cho cấu hình đang dùng. Tránh global mutable static recorder dùng chung giữa các parallel tests nếu không có isolation phù hợp.

## 27. Những lỗi thường gặp

### Lỗi 1 — Tạo class có @PrePersist nhưng quên đăng ký

Một class listener nằm trên classpath **không tự áp cho mọi entity**. Cần `@EntityListeners`, mapped superclass registration hoặc XML metadata phù hợp.

### Lỗi 2 — Nhầm callback trong entity với callback trong listener

Entity callback không tham số; external listener callback nhận entity parameter. Đừng đổi chữ ký tùy tiện.

### Lỗi 3 — Gắn listener riêng cho mọi entity

Một listener kiểm tra `PurchaseOrder.reference` không phù hợp với Product/Customer. Cần scope đúng.

### Lỗi 4 — Nhầm listener dùng chung với default listener

Đăng ký cùng class cho nhiều entities không đồng nghĩa nó đã trở thành default listener cấp persistence unit.

### Lỗi 5 — Không kiểm tra orm.xml có được bootstrap không

Có XML file trong repository nhưng persistence unit không load metadata đó thì listener không chạy như dự kiến.

### Lỗi 6 — Đăng ký audit lặp ở annotation và XML

Một quy tắc có thể bị áp lại hoặc tạo cấu hình khó suy luận. Cần một chiến lược đăng ký rõ.

### Lỗi 7 — Nghĩ @ExcludeDefaultListeners tắt tất cả callbacks

Nó nhắm vào default listeners, không phải toàn bộ JPA lifecycle.

### Lỗi 8 — Nghĩ @ExcludeSuperclassListeners xóa mọi superclass callbacks

Nó liên quan inherited listener classes; method callbacks trực tiếp trong hierarchy có quy tắc khác.

### Lỗi 9 — Dựa vào tên method trước khi ghi

`beforePersist` không phải magic name. Callback được gắn bằng annotation/XML metadata.

### Lỗi 10 — Đưa mutable request state vào listener

Provider có thể quản lý listener instances theo cách khiến state không an toàn khi concurrent. Giữ listeners stateless.

### Lỗi 11 — Gửi email ở @PostPersist

`@PostPersist` chưa chắc transaction commit thành công. Email không tự rollback.

### Lỗi 12 — Gọi EntityManager.persist() từ @PrePersist

Có thể gây recursion, provider-specific behavior và khó kiểm soát flush. Logic điều phối nên ở service.

### Lỗi 13 — Duyệt LAZY collection trong @PostLoad

Có thể kích hoạt truy vấn bổ sung/N+1 hoặc truy cập state đang dựng.

### Lỗi 14 — Cho rằng @PreUpdate chạy mỗi lần save()

Nếu entity không dirty, SQL UPDATE có thể không xảy ra. Không dựa vào callback làm bộ đếm số lần gọi service.

### Lỗi 15 — Cho rằng @PrePersist luôn có ID generated

Với chiến lược IDENTITY, ID có thể chưa sẵn có trước insert.

### Lỗi 16 — Cho rằng callback được gọi sau commit

Các Post callbacks không phải transaction after-commit events.

### Lỗi 17 — Cho rằng JPQL bulk update gọi @PreUpdate từng entity

Bulk DML không sử dụng vòng đời managed entity từng row theo cách đó.

### Lỗi 18 — Chỉ kiểm thử method listener bằng unit test thủ công

Chưa xác nhận registration, metadata, timing và provider integration.

### Lỗi 19 — Dùng listener như transaction manager

Callback không thay `@Transactional`, `EntityTransaction` hoặc database constraints.

### Lỗi 20 — Đưa mọi business rule vào listener

Các quy tắc cần nhiều repositories, lock/version, external calls thuộc application/domain service thích hợp hơn.

### Lỗi 21 — Tự sửa foreign key/relationships từ listener

Có thể phá consistency của persistence context và khó portable.

### Lỗi 22 — Chỉ sửa một subclass rồi nghĩ mọi descendants cùng listener policy

Inheritance, XML metadata và exclusion annotations phải được xét đúng phạm vi.

### Lỗi 23 — Dùng listener để xóa hoặc refresh cache toàn bộ

Lifecycle callback không phải nơi gọi `Cache.evictAll()` hoặc `EntityManager.clear()` tùy tiện; có thể làm mất state và tạo side effects bất ngờ.

### Lỗi 24 — Không phân biệt EntityListener và Hibernate event SPI

Provider-specific events có khả năng khác nhưng không phải portable JPA lifecycle callbacks.

## 28. Bài tập thực hành

### Bài 1 — Listener riêng

Tạo `OrderRulesListener` kiểm tra `PurchaseOrder.reference` khác null/trống ở `@PrePersist` và `@PreUpdate`.

**Gợi ý:** Dùng một class có hai method callbacks, đăng ký bằng `@EntityListeners(OrderRulesListener.class)` trên PurchaseOrder; không gắn trên Product.

### Bài 2 — Audit dùng chung

Ba entities có `createdAt` và `updatedAt`. Muốn tránh lặp code.

**Gợi ý:** Tạo interface `AuditStamped` và `AuditStampListener`, gắn listener lên các entities tương ứng hoặc một mapped superclass chung.

### Bài 3 — Phân biệt default và shared

Một listener class có `@PrePersist` được khai báo trên Customer và Product qua `@EntityListeners`.

**Hỏi:** Nó tự chạy cho Invoice không?

**Đáp án:** Không, trừ khi Invoice nhận listener qua đăng ký/kế thừa hoặc metadata mặc định khác phù hợp.

### Bài 4 — Default listener qua XML

Đăng ký `GlobalLifecycleListener` cho cả persistence unit.

**Gợi ý:** Dùng `orm.xml` trong `persistence-unit-defaults/entity-listeners` và bảo đảm persistence unit load mapping file.

### Bài 5 — Exclude default

`AuditEvent` không muốn chạy GlobalLifecycleListener nhưng vẫn cần `AuditEventRulesListener`.

**Gợi ý:** `@ExcludeDefaultListeners` cùng `@EntityListeners(AuditEventRulesListener.class)`.

### Bài 6 — Exclude superclass

`SpecialProduct` kế thừa `AuditTrackedEntity` có `@EntityListeners(AuditStampListener.class)` nhưng không muốn inherited listener.

**Đáp án:** Xem `@ExcludeSuperclassListeners`; phải hiểu nó không tự loại mọi callback method trong superclass.

### Bài 7 — Thứ tự listeners

`@EntityListeners({AuditStampListener.class, OrderRulesListener.class})`.

**Hỏi:** Vì sao không nên đổi thứ tự tùy tiện?

**Đáp án:** Nếu validation dựa trên timestamps do listener trước gán, đổi thứ tự có thể đổi kết quả. Nên giảm coupling hoặc kiểm thử rõ.

### Bài 8 — IDENTITY ID

`Order.id` dùng `GenerationType.IDENTITY`. Listener `@PrePersist` muốn in ID.

**Đáp án:** Không giả định ID đã được gán trước insert. `@PostPersist` là mốc phù hợp hơn để đọc generated ID, nhưng chưa phải after commit.

### Bài 9 — Gửi email

`@PostPersist` của Order gửi email xác nhận; transaction sau đó rollback.

**Đáp án:** Thiết kế sai. Dùng outbox/after-commit handling phù hợp.

### Bài 10 — Bulk update

Chạy:

```jpql
UPDATE Product p
SET p.active = false
WHERE p.price < 10
```

**Hỏi:** `@PreUpdate` của từng Product có chạy không?

**Đáp án:** Không được coi bulk JPQL DML là các entity lifecycle updates riêng lẻ. Cần tự duy trì audit data và xử lý persistence context/cache theo chiến lược.

### Bài 11 — PostLoad và LAZY collection

`@PostLoad` gọi `order.getLines().size()` cho 500 orders.

**Đáp án:** Có thể tạo N+1 và phụ thuộc vào fetch state. Dùng projection/fetch plan có chủ đích hoặc không đọc collection ở callback.

### Bài 12 — Stateless listener

Một shared listener lưu `lastEntityId` trong instance field để dùng cho callback tiếp theo.

**Đáp án:** Không an toàn/không đáng tin về lifecycle và concurrent access. Chỉ dùng dữ liệu của invocation hiện tại.

### Bài 13 — Inheritance

Một mapped superclass khai báo entity listener và phương thức `@PrePersist` trực tiếp. Subclass dùng `@ExcludeSuperclassListeners`.

**Hỏi:** Có tự động tắt cả hai loại không?

**Đáp án:** Không nên suy như vậy; annotation nhắm tới listener classes kế thừa, trong khi callback methods trong hierarchy có quy tắc riêng.

### Bài 14 — Kiểm thử registration

Một unit test khởi tạo `new AuditStampListener()` rồi gọi `beforeInsert(entity)` thành công.

**Hỏi:** Đã đủ chứng minh JPA registration đúng chưa?

**Đáp án:** Chưa. Cần integration test thực hiện `em.persist()` trong persistence unit có metadata thực tế.

### Bài 15 — Thiết kế policy

Ứng dụng có 80 entities, trong đó 60 cần audit timestamps, 20 entities hệ thống không cần.

**Gợi ý:** Cân nhắc explicit shared listener hoặc mapped superclass cho 60 entities. Default XML listener chỉ phù hợp khi chính sách toàn cục và các exceptions được quản lý rõ, tránh làm 20 entities không liên quan chịu overhead.

## 29. Câu hỏi tự kiểm tra

**1. Entity listener khác callback trong entity thế nào?**

Callback trong entity là method của chính entity; listener là class bên ngoài nhận entity đang có sự kiện.

**2. Annotation nào đăng ký listener classes cho entity?**

`@EntityListeners`.

**3. Listener class có @PrePersist tự động áp mọi entity không?**

Không. Phải được đăng ký theo metadata phù hợp.

**4. Listener có thể được dùng lại cho nhiều entities không?**

Có, qua nhiều đăng ký `@EntityListeners` hoặc mapped superclass/default metadata.

**5. Một cách đặt audit fields dùng chung là gì?**

Dùng `@MappedSuperclass` với các persistent fields và callback hoặc listener registration kế thừa.

**6. Cách đăng ký default listener cấp persistence unit chuẩn là gì?**

XML metadata `orm.xml` với `persistence-unit-defaults` / `entity-listeners`.

**7. @ExcludeDefaultListeners dùng để làm gì?**

Loại default listeners áp dụng cho entity theo semantics JPA.

**8. @ExcludeSuperclassListeners dùng để làm gì?**

Loại inherited entity listener classes theo quy tắc của JPA.

**9. Hai annotation exclude có phải hoàn toàn giống nhau không?**

Không. Chúng nhắm tới hai nhóm listeners khác nhau.

**10. Method callback trong entity có nhận một tham số Object không?**

Không; callback method đặt trực tiếp trong entity dùng chữ ký không tham số.

**11. Callback method trong listener thường nhận gì?**

Entity object đang trải qua sự kiện lifecycle.

**12. Tên method là beforePersist có đủ để nó tự chạy không?**

Không. Cần lifecycle annotation hoặc XML metadata đúng.

**13. @PostPersist có nghĩa dữ liệu đã commit bền vững không?**

Không.

**14. Có nên gửi email trong @PostPersist không?**

Không khi cần gắn với transaction commit; nên dùng after-commit/outbox.

**15. @PreUpdate có luôn chạy mỗi lần service.save() không?**

Không. Nó gắn với lifecycle update thực tế và flush/dirty state.

**16. @PostLoad có thể chạy mỗi lần gọi find cùng ID trong một EntityManager không?**

Không được giả định; persistence context có thể trả managed instance sẵn có.

**17. @PrePersist có chắc đọc được generated IDENTITY ID không?**

Không.

**18. Bulk JPQL UPDATE có kích hoạt @PreUpdate từng row không?**

Không theo managed-entity lifecycle thông thường.

**19. Callback có nên gọi repository khác và mở transaction mới không?**

Không nên cho thiết kế portable, dễ dự đoán; hãy điều phối ở service.

**20. Vì sao shared listener nên stateless?**

Vì vòng đời/sự tái sử dụng instances và concurrent callbacks không nên phụ thuộc mutable request state.

**21. Interface AuditStamped có tự map columns không?**

Không. Entity vẫn cần persistent fields/mapping phù hợp.

**22. @MappedSuperclass dùng để làm gì?**

Chia sẻ metadata và state mapping cho subclasses, có thể chia sẻ callback/registration.

**23. Nếu có default listener và entity listener, có thể cả hai chạy không?**

Có, nếu không bị exclusion hoặc metadata khác điều chỉnh.

**24. Vì sao không nên để nhiều listeners phụ thuộc lẫn nhau phức tạp?**

Vì thứ tự callback biến thành hidden business workflow khó duy trì và kiểm thử.

**25. Annotation @EntityListeners có thể khai báo nhiều classes không?**

Có, bằng danh sách classes trong annotation.

**26. Hibernate event listener SPI có phải @EntityListeners chuẩn JPA không?**

Không; đó là extension của provider.

**27. Unit test trực tiếp gọi listener có chứng minh JPA metadata được load không?**

Không; cần integration test qua EntityManager.

**28. Khi nào nên chọn listener riêng?**

Khi rule gắn với một entity hoặc nhóm entity rất cụ thể.

**29. Khi nào nên chọn listener dùng chung?**

Khi một logic có cùng ý nghĩa cho nhiều entities và có contract chung rõ ràng.

**30. Khi nào default listener đáng cân nhắc?**

Khi policy thật sự phổ biến trong persistence unit và ngoại lệ được xử lý rõ.

## 30. Tình huống tổng hợp: hệ thống đơn hàng và audit

Một ứng dụng có:

```text
Customer
Product
PurchaseOrder
OrderLine
AuditEvent
OutboxEvent
```

Yêu cầu:

1. Customer, Product, PurchaseOrder, OrderLine cần timestamps.
2. PurchaseOrder phải có `reference` hợp lệ trước insert/update.
3. AuditEvent và OutboxEvent không bị một global listener audit làm phát sinh recursion hoặc timestamp policy không cần thiết.
4. Khi Order được tạo thành công, hệ thống sẽ gửi thông báo.
5. Bulk update trạng thái Products phải giữ audit data đúng.
6. Các callback phải dễ kiểm thử và có phạm vi rõ.

### 30.1. Lựa chọn kiến trúc

```text
@MappedSuperclass AuditTrackedEntity
   |
   +-- @EntityListeners(AuditStampListener)
   |
   +-- Customer
   +-- Product
   +-- OrderLine
   +-- PurchaseOrder
            |
            +-- @EntityListeners(OrderRulesListener)

AuditEvent
   |
   +-- Không dùng AuditTrackedEntity nếu không phù hợp

OutboxEvent
   |
   +-- Được tạo bởi domain service trong transaction
```

Đây là **một phương án**, không phải cấu trúc bắt buộc. Nếu dự án không thích class inheritance, có thể dùng interface + explicit listener registrations.

### 30.2. Luồng tạo PurchaseOrder

```text
HTTP POST /orders
        |
        v
Controller validates request
        |
        v
@Transactional OrderService
        |
        +-- Check business rules, inventory, customer
        |
        +-- Create PurchaseOrder
        |
        +-- em.persist(order)
        |       |
        |       +-- @PrePersist AuditStampListener
        |       |
        |       +-- @PrePersist OrderRulesListener
        |
        +-- Persist OutboxEvent
        |
        v
Flush / Commit
        |
        +-- Success:
        |     Outbox dispatcher publishes OrderCreated
        |
        +-- Failure:
              Database transaction rolls back
              No durable outbox event
```

### 30.3. Vì sao OrderRulesListener chỉ kiểm tra rule đơn giản?

Đơn hàng đã được service kiểm tra quan hệ phức tạp (khách hàng, kho, quyền và transaction). Listener chỉ giữ invariant nội tại, ví dụ reference không rỗng. Không để listener tự gọi database để làm lại toàn bộ service workflow.

### 30.4. Vì sao không đặt email trong PostPersist?

Vì callback có thể chạy trước commit. Ghi outbox trong cùng transaction giúp thông báo phụ thuộc vào kết quả commit theo cách tin cậy hơn.

### 30.5. Bulk update Products

Một job:

```jpql
UPDATE Product p
SET p.active = false
WHERE p.discontinued = true
```

không được giả định sẽ tự chạy `AuditStampListener.@PreUpdate` từng Product. Job cần cập nhật audit columns theo rule phù hợp và giải quyết persistence context/cache nếu cần.

### 30.6. Integration tests bắt buộc ở tầng kiến trúc

- Persist Order gọi audit và rules một cách chính xác.
- Persist Product không gọi OrderRulesListener.
- Outbox chỉ được commit khi transaction thành công.
- Excluded entities không nhận default policy ngoài ý muốn.
- Bulk jobs duy trì audit fields theo chính sách.
- Có thể thay provider mà metadata lifecycle chuẩn vẫn có semantics mong muốn.

## 31. Ghi nhớ cuối bài

JPA cung cấp cơ chế callback sự kiện vòng đời linh hoạt, nhưng điểm quan trọng nhất là **đăng ký đúng phạm vi**:

```java
// Listener riêng hoặc một trong nhiều listener:
@EntityListeners(OrderRulesListener.class)

// Nhiều listeners:
@EntityListeners({
    AuditStampListener.class,
    OrderRulesListener.class
})

// Không sử dụng default listener:
@ExcludeDefaultListeners

// Không kế thừa superclass listeners:
@ExcludeSuperclassListeners
```

Với nhu cầu dùng chung:

- Gắn cùng listener class lên nhiều entities.
- Hoặc dùng `@MappedSuperclass` để chia sẻ metadata/registration.
- Hoặc dùng `orm.xml` để khai báo default listener cho persistence unit khi chính sách thật sự có phạm vi rộng.

Những nguyên tắc cần giữ:

1. **Một listener class không tự được kích hoạt nếu chưa được đăng ký** theo metadata.
2. **Listener riêng** phù hợp quy tắc của một entity; **listener dùng chung** phù hợp chính sách nhiều entity; **default listener** là cấu hình rộng cấp persistence unit.
3. **Thứ tự listeners và inheritance** có thể ảnh hưởng hành vi; dùng `@ExcludeDefaultListeners` và `@ExcludeSuperclassListeners` đúng nhóm.
4. **Callback trong entity** có chữ ký khác callback trong listener class.
5. **Callback nên ngắn, stateless, tập trung vào state của entity** và tránh điều phối nhiều entity/transactions từ bên trong.
6. **@PostPersist/@PostUpdate/@PostRemove không có nghĩa sau commit**; dùng outbox hoặc cơ chế after-commit cho side effects bên ngoài.
7. **Bulk JPQL/native SQL/external writers không tự kích hoạt lifecycle callbacks từng entity**; cần bảo đảm audit consistency ở những đường ghi đó.
8. **Không nhầm @PreUpdate với một lời gọi save()**; callback phụ thuộc lifecycle update và flush.
9. **Kiểm thử registration bằng EntityManager thật**, không chỉ tự gọi listener method trong unit test.
10. **Tách business workflow khỏi persistence callback** để giảm phụ thuộc vào thứ tự ngầm và tránh lỗi concurrency.

Khi được dùng đúng, listener riêng và listener dùng chung giúp code JPA rõ ràng, ít lặp, dễ tái sử dụng và dễ quản lý hơn. Khi phạm vi được đăng ký quá rộng hoặc callback bị dùng như một transaction/event bus, chúng có thể tạo side effects khó dự đoán. Hãy thiết kế listeners như **các hook vòng đời nhỏ và có hợp đồng rõ**, không phải nơi thay thế domain service hoặc transaction manager.
