# Sử dụng OPTIMISTIC và OPTIMISTIC_FORCE_INCREMENT trong JPA

Khi nhiều người dùng hoặc nhiều tiến trình đồng thời đọc và sửa cùng một dữ liệu, hệ thống có thể gặp **lost update** (một lần ghi đè mất thay đổi của lần ghi khác), ra quyết định trên trạng thái cũ, hoặc vi phạm quy tắc của một aggregate. Java Persistence API (JPA) có cơ chế **optimistic locking — khóa lạc quan** để phát hiện một số xung đột như vậy mà không phải giữ khóa ghi trên database trong suốt thời gian người dùng đọc dữ liệu.

Hai chế độ được dùng để yêu cầu JPA kiểm soát phiên bản một cách tường minh là:

- `LockModeType.OPTIMISTIC`: yêu cầu **kiểm tra phiên bản** của entity được khóa theo ngữ nghĩa optimistic locking, kể cả khi transaction chỉ đọc entity rồi đưa ra quyết định.
- `LockModeType.OPTIMISTIC_FORCE_INCREMENT`: yêu cầu **kiểm tra và ép tăng phiên bản** của một versioned entity, kể cả khi không sửa trực tiếp scalar field nào trên entity đó.

Hai chế độ đều sử dụng ý tưởng so sánh **version của entity**; chúng không đơn giản là cách gọi khác của SQL `SELECT ... FOR UPDATE`. Tuy nhiên, chúng phục vụ những mục đích khác nhau:

~~~text
Một Order có version = 12
          |
          +--- OPTIMISTIC
          |      |
          |      +--- Đảm bảo phiên bản được kiểm tra
          |      +--- Không chủ đích tăng version chỉ vì đọc/lock
          |
          +--- OPTIMISTIC_FORCE_INCREMENT
                 |
                 +--- Đảm bảo phiên bản được kiểm tra
                 +--- Yêu cầu provider tăng version
                      ngay cả khi Order không dirty
~~~

Ví dụ điển hình của `OPTIMISTIC` là một service **đọc Order và kiểm tra điều kiện** trước khi cập nhật đối tượng khác, nhưng vẫn muốn phát hiện Order bị transaction khác sửa trong thời gian xử lý.

Ví dụ điển hình của `OPTIMISTIC_FORCE_INCREMENT` là service **thêm/sửa OrderLine** và muốn thay đổi đó cũng làm **revision của aggregate root PurchaseOrder** tăng lên, dù các field của Order không đổi trực tiếp.

Bài học này đi sâu vào cách hoạt động, API JPA thuần, transaction boundary, vòng đời managed entity, thời điểm version check/increment, so sánh với `@Version` mặc định, concurrency timeline, Spring Data JPA, hạn chế trong bulk UPDATE, chiến lược retry, tích hợp API và kiểm thử bằng nhiều transaction.

## 1. Vấn đề nền tảng: Hai transaction cùng đọc một phiên bản

Giả sử hệ thống có bảng đơn hàng:

~~~text
purchase_order
id  status    version
41  PENDING    7
~~~

Hai transaction chạy đồng thời:

~~~text
Transaction A                       Transaction B
----------------------------------  ----------------------------------
Đọc Order#41: PENDING, version 7    Đọc Order#41: PENDING, version 7

Xác nhận giao hàng                  Hủy Order
Sửa trạng thái thành SHIPPED         Sửa trạng thái thành CANCELLED

Ghi xuống database                  Ghi xuống database
~~~

Nếu cả hai đơn giản ghi:

~~~sql
UPDATE purchase_order
SET status = ?
WHERE id = 41;
~~~

lần ghi sau có thể ghi đè kết quả lần ghi trước. Khi đó quyết định của một transaction dựa trên trạng thái `PENDING` cũ có thể không còn hợp lệ.

Với optimistic locking theo version, thao tác cập nhật managed entity thường mang ý tưởng:

~~~sql
UPDATE purchase_order
SET status = ?,
    version = 8
WHERE id = 41
  AND version = 7;
~~~

Nếu transaction khác đã đổi version từ 7 sang 8, điều kiện `version = 7` không còn khớp. JPA có thể phát hiện xung đột và báo lỗi optimistic locking, thay vì âm thầm ghi đè.

**Đây là SQL minh họa logic, không phải cam kết chính xác JPA provider sẽ sinh một SQL statement với đúng thứ tự/giá trị đó.**

### 1.1. Optimistic locking lạc quan ở điểm nào?

Nó giả định **xung đột tương đối ít**, nên không cần khóa ghi kéo dài khi chỉ đọc. Khi transaction cố dùng trạng thái/version cũ, provider phát hiện xung đột trong quy trình kiểm tra/cập nhật.

Mô hình:

~~~text
READ entity + version
        |
        v
Làm việc trong transaction
        |
        v
Kiểm tra version hiện tại / cập nhật có điều kiện
        |
   +----+-----+
   |          |
Khớp        Không khớp
   |          |
   v          v
Tiếp tục    OptimisticLockException
commit      / rollback
~~~

Nhưng “không chủ đích giữ khóa ghi lúc đọc” **không có nghĩa không có bất kỳ database lock nào**. Câu SQL UPDATE vật lý, row changes và transaction isolation vẫn có cơ chế khóa riêng của DB.

### 1.2. Mục tiêu và giới hạn

Optimistic locking giúp phát hiện xung đột đối với **entity/version được theo dõi**. Nó không tự đảm bảo:

- Toàn bộ transaction tương đương isolation `SERIALIZABLE`.
- Mọi row ở những bảng liên quan đều được bảo vệ.
- Những thay đổi qua native SQL/bulk DML tự tăng version.
- Mọi quy tắc nghiệp vụ liên bảng được bảo vệ không cần constraint.
- Không có conflict giữa hai người dùng.

Vì vậy, cần xác định **entity nào phải được kiểm tra phiên bản** và **thao tác nào bắt buộc làm tăng phiên bản**.

## 2. @Version là nền tảng

JPA dùng một thuộc tính phiên bản để phát hiện thay đổi đồng thời:

~~~java
@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    // Những thuộc tính và association khác...
}
~~~

Bảng vật lý:

~~~sql
CREATE TABLE purchase_order (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL
);
~~~

`@Version` biểu thị một giá trị do persistence provider quản lý trong vòng đời entity. Thông thường:

1. Entity được tải với một version hiện tại.
2. Khi JPA cập nhật hoặc xóa managed entity, provider sử dụng version để phát hiện thay đổi đồng thời.
3. Khi cập nhật thành công, version được tiến lên theo cơ chế provider.
4. Nếu kiểm tra version thất bại, transaction có thể nhận `OptimisticLockException` hoặc exception bao bọc tương ứng khi flush/commit.

### 2.1. Version không phải business status

- `status = PENDING` là trạng thái nghiệp vụ.
- `version = 7` là dấu hiệu revision dùng trong kiểm soát concurrency.

Một Order có thể đổi dữ liệu mà vẫn giữ status PENDING, nhưng version thường cần thay đổi khi JPA cập nhật managed state đó.

### 2.2. Version không phải thời điểm cập nhật

`updatedAt` có thể phục vụ audit và UI, nhưng không mặc định là optimistic version. Một timestamp có giới hạn độ chính xác hoặc do nhiều clock ghi có thể gây khó khăn khi dùng làm concurrency token.

Các kiểu field được JPA hỗ trợ cho `@Version` tùy phiên bản đặc tả và provider. Với ví dụ xuyên suốt, dùng `long` cho rõ. Không tự thay đổi `@Version` bằng application setter; giá trị này thuộc trách nhiệm provider trừ khi dùng một cơ chế mở rộng/SQL concurrency được thiết kế riêng.

### 2.3. Đặt @Version ở đâu trong inheritance?

Nếu entity thuộc một hierarchy, mapping version phải tuân thủ quy tắc của JPA đối với hierarchy, thông thường đặt ở root entity phù hợp. Không tạo mỗi subclass một version độc lập rồi suy rằng JPA sẽ phối hợp tất cả.

### 2.4. Entity không có @Version

Khả năng áp dụng optimistic lock modes cho **unversioned entity** không được JPA yêu cầu hỗ trợ như versioned entity. Provider có thể báo lỗi nếu được yêu cầu optimistic lock trên loại entity đó.

Đối với một bài toán cần concurrency contract portable, hãy thiết kế versioned entity thay vì mong provider suy ra version từ mọi cột.

## 3. Những LockModeType liên quan

JPA cung cấp một số lock modes, nhưng bài này tập trung vào hai mode lạc quan.

| Lock mode | Ý nghĩa chính |
|---|---|
| `NONE` | Không yêu cầu explicit lock mode mới |
| `OPTIMISTIC` | Yêu cầu kiểm tra optimistic version |
| `OPTIMISTIC_FORCE_INCREMENT` | Yêu cầu kiểm tra và ép tăng optimistic version |
| `PESSIMISTIC_READ` | Yêu cầu khóa bi quan theo khả năng DB/provider |
| `PESSIMISTIC_WRITE` | Khóa ghi bi quan |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa bi quan đồng thời ép tăng version |

Những tên `READ` và `WRITE` là các alias lịch sử của `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT` trong JPA. Trong code mới, nên dùng tên **OPTIMISTIC** và **OPTIMISTIC_FORCE_INCREMENT** để mục đích rõ ràng, tránh nhầm với pessimistic database read/write locks.

### 3.1. OPTIMISTIC không có nghĩa SELECT FOR SHARE

Mode này là yêu cầu kiểm tra optimistic version, không phải một tên khác của SQL read lock. Provider có thể dùng các truy vấn/kiểm tra tùy implementation để bảo đảm semantics.

### 3.2. FORCE_INCREMENT không có nghĩa PESSIMISTIC_WRITE

Ép tăng version là một cách khiến những transaction khác dùng version cũ phải đối diện xung đột optimistic. Nó không yêu cầu giữ write lock ngay từ lúc entity được đọc như cách dùng pessimistic locking.

### 3.3. NONE không vô hiệu hóa @Version

Nếu một managed versioned entity bị sửa theo lifecycle thông thường, provider vẫn áp dụng optimistic locking do `@Version`, ngay cả khi không gọi `em.lock(..., OPTIMISTIC)`.

Điểm quan trọng là **explicit OPTIMISTIC** hữu ích khi cần đảm bảo kiểm tra phiên bản cho **entity được đọc để ra quyết định nhưng không nhất thiết bị sửa**.

## 4. Khác biệt cốt lõi: OPTIMISTIC so với OPTIMISTIC_FORCE_INCREMENT

Giả sử một Order được đọc với version 12 và không thay đổi scalar field nào của Order.

### 4.1. Với OPTIMISTIC

~~~java
em.lock(order, LockModeType.OPTIMISTIC);
~~~

Service yêu cầu provider kiểm tra optimistic version của Order. Nếu một transaction khác thay đổi Order và version theo cách tương thích với optimistic locking, transaction hiện tại có thể bị từ chối.

Tuy nhiên, chỉ gọi `OPTIMISTIC` **không chủ đích tăng version** khi entity không thay đổi.

~~~text
Trước: Order.version = 12
Chỉ đọc + OPTIMISTIC
Không có update khác và transaction thành công
Sau:   Version vẫn có thể là 12
~~~

### 4.2. Với OPTIMISTIC_FORCE_INCREMENT

~~~java
em.lock(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

JPA phải thực hiện cơ chế optimistic locking và **yêu cầu tăng version** của Order, ngay cả khi không có thay đổi scalar field trên entity đó.

~~~text
Trước: Order.version = 12
Chỉ đọc + OPTIMISTIC_FORCE_INCREMENT
Transaction commit thành công
Sau:   Version được tăng theo cơ chế provider
~~~

Không nên tự giả định version sẽ **luôn tăng đúng 1 theo kiểu long** ở mọi provider/mapping hoặc bạn có thể đọc giá trị Java mới ngay sau dòng `em.lock`. Điều bảo đảm là **ép tăng version theo semantics JPA**, còn thời điểm provider thực thi SQL và cập nhật field trong memory có thể được trì hoãn.

### 4.3. Bảng so sánh

| Tiêu chí | OPTIMISTIC | OPTIMISTIC_FORCE_INCREMENT |
|---|---|---|
| Dùng trên versioned entity | Có | Có |
| Kiểm tra version | Có | Có |
| Tăng version khi chỉ lock mà không dirty entity | Không chủ đích | **Có, bắt buộc theo semantics** |
| Ghi SQL do force-only | Không nhất thiết | Có thể cần SQL/operation để tăng version |
| Phù hợp cho đọc điều kiện và cần phát hiện Order đổi | Có | Có nhưng có thể tăng version không cần thiết |
| Phù hợp để đánh dấu aggregate root có revision mới khi child đổi | Thường chưa đủ | Thường phù hợp |
| Có thể tạo thêm xung đột optimistic | Có | **Có, thường nhiều hơn do revision được tăng** |
| Chi phí DB | Thường ít hơn nếu chỉ kiểm tra | Có overhead cho version increment |
| Ngăn transaction khác cập nhật DB bằng row lock kéo dài | Không phải mục đích | Không phải mục đích |

**Quy tắc thực dụng:** Nếu chỉ cần bảo vệ một quyết định dựa trên version hiện tại, cân nhắc `OPTIMISTIC`. Nếu một thay đổi logic phải làm revision của entity/aggregate tăng dù entity root không dirty, cân nhắc `OPTIMISTIC_FORCE_INCREMENT`.

## 5. Mô hình ví dụ: PurchaseOrder là aggregate root

Một Order có nhiều OrderLine:

~~~text
PurchaseOrder #41
  version = 12
  status  = PENDING
  |
  +-- OrderLine #7001 (SKU-A, quantity=1)
  +-- OrderLine #7002 (SKU-B, quantity=2)
~~~

Entity root:

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    @Column(nullable = false)
    private long version;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private OrderStatus status;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "total_amount", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public List<OrderLine> getLines() {
        return lines;
    }

    public void approve() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Only pending orders may be approved"
            );
        }
        status = OrderStatus.APPROVED;
    }
}
~~~

Enum minh họa:

~~~java
package com.example.shop.domain;

public enum OrderStatus {
    PENDING,
    APPROVED,
    CANCELLED
}
~~~

Entity con:

~~~java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "product_sku", nullable = false)
    private String productSku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    public Long getId() { return id; }
    public int getQuantity() { return quantity; }

    public void changeQuantity(int newQuantity) {
        if (newQuantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        quantity = newQuantity;
    }
}
~~~

Tùy mapping và thao tác, sửa một OrderLine có thể tạo SQL UPDATE trên bảng `order_line` mà **không nhất thiết làm PurchaseOrder bị dirty và version của parent tăng**. Đây là một trong những lý do quan trọng để hiểu `OPTIMISTIC_FORCE_INCREMENT`.

Trong code thực, association helper methods phải đảm bảo tính nhất quán hai phía, tính lại total và bảo vệ invariants; ví dụ trên chỉ trình bày những field phục vụ locking.

### 5.1. Sơ đồ version trong database

~~~text
purchase_order
id | status  | version
41 | PENDING | 12

order_line
id   | order_id | quantity
7001 | 41       | 1
7002 | 41       | 2
~~~

Một transaction chỉ thay `order_line.quantity` có thể không tự thay `purchase_order.version` nếu root không bị cập nhật. Do đó người khác chỉ nhìn version của Order có thể không phát hiện thay đổi child, trừ khi application có chiến lược duy trì root version phù hợp.

### 5.2. Các thao tác nào thuộc cùng aggregate?

Giả sử nghiệp vụ coi Order và Lines là một aggregate: mọi thay đổi số lượng dòng có thể ảnh hưởng tổng tiền, phân bổ inventory hoặc điều kiện phê duyệt.

Khi đó hệ thống có thể quyết định **bất kỳ thay đổi có ý nghĩa nào lên OrderLine cũng phải làm Order.version thay đổi**. `OPTIMISTIC_FORCE_INCREMENT` là một công cụ để yêu cầu provider thực hiện điều này trên root.

Đây là **quy ước kiến trúc phải áp dụng nhất quán trên tất cả đường ghi**, không phải điều JPA tự suy luận từ từ khóa “aggregate”.

## 6. Dùng EntityManager.find với OPTIMISTIC

Một API trực tiếp:

~~~java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    LockModeType.OPTIMISTIC
);
~~~

Nếu Order tồn tại, provider tải hoặc lấy entity tương ứng trong persistence context và yêu cầu optimistic lock theo mode chỉ định. Nếu entity không tồn tại, `find` trả `null`.

### 6.1. Ví dụ service đọc rồi quyết định

~~~java
@Transactional
public void validateOrderAndReserve(
        long orderId,
        long authenticatedTenantId) {

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId,
        LockModeType.OPTIMISTIC
    );

    if (order == null) {
        throw new NoSuchElementException(
            "Order not found"
        );
    }

    if (!order.getTenantId()
              .equals(authenticatedTenantId)) {
        throw new SecurityException(
            "Order not accessible"
        );
    }

    if (order.getStatus() != OrderStatus.PENDING) {
        throw new IllegalStateException(
            "Order is not pending"
        );
    }

    // Thao tác tiếp theo liên quan tới dữ liệu nghiệp vụ.
    // Cần thiết kế transaction, locking và constraint
    // của resource được cập nhật riêng.
}
~~~

Yêu cầu `OPTIMISTIC` có ý nghĩa khi service cần bảo đảm rằng Order không bị thay đổi một cách không phát hiện trong lúc ra quyết định.

### 6.2. Kiểm tra tenant sớm hơn bằng query

Ví dụ `find` rồi kiểm tra tenant giúp minh họa API, nhưng có thể đã tải Order của tenant khác trước khi từ chối. Trong hệ thống multi-tenant nên ưu tiên query có điều kiện tenant hoặc cơ chế DB isolation/security đã được xác minh:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """,
    PurchaseOrder.class
);

PurchaseOrder order = query
    .setParameter("id", orderId)
    .setParameter("tenantId", authenticatedTenantId)
    .setLockMode(LockModeType.OPTIMISTIC)
    .getSingleResult();
~~~

Điều kiện authorization và optimistic lock phục vụ **hai nhiệm vụ riêng**: quyền được phép truy cập và độ mới của dữ liệu.

### 6.3. Transaction requirement

Yêu cầu lock mode trên entity cần transaction phù hợp. Nếu gọi `find` với optimistic lock trong bối cảnh không có transaction đang hoạt động, provider có thể ném `TransactionRequiredException` theo contract JPA.

Một truy vấn SELECT không lock có thể chạy ngoài transaction trong một số môi trường; không suy ra `find(..., LockModeType.OPTIMISTIC)` cũng có thể làm như vậy.

## 7. Dùng EntityManager.lock cho entity managed

Nếu entity đã được tải:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

// Yêu cầu kiểm tra version cho entity managed:
em.lock(order, LockModeType.OPTIMISTIC);
~~~

`em.lock(...)` khác `em.find(...)` ở chỗ nó **không phải một thao tác tìm theo ID**. Nó áp lock mode lên entity instance được quản lý trong context.

### 7.1. Entity phải managed

Ví dụ dễ sai:

~~~java
PurchaseOrder detached = loadInOldEntityManager();
em.lock(detached, LockModeType.OPTIMISTIC);
~~~

Nếu object là detached đối với `em` hiện tại, `lock` không phải cách tự động attach lại. JPA yêu cầu entity được managed và có thể ném `IllegalArgumentException` nếu truyền entity không managed.

Nếu cần đọc lại một entity cho transaction mới, ưu tiên query/find theo ID trong context hiện tại, thay vì dùng `merge` chỉ để đặt lock trên bản detached cũ.

### 7.2. Đọc basic field có thể không tạo SQL ngay

Một managed entity có thể đã ở first-level cache. `em.lock(..., OPTIMISTIC)` có thể thực hiện kiểm tra thông qua statement ở một thời điểm khác; không thể suy luận trực tiếp “mỗi lock call bắt buộc SELECT mới ngay”.

### 7.3. Không nhầm lock với refresh

`em.lock(order, OPTIMISTIC)` yêu cầu lock/version semantics. Nó **không phải lời hứa nạp lại toàn bộ field từ DB** như `em.refresh(order)`.

Nếu cần state mới nhất trong transaction phù hợp, cân nhắc refresh hoặc query theo chính sách isolation; cần hiểu rằng refresh có thể ghi đè pending state của entity.

## 8. Dùng OPTIMISTIC_FORCE_INCREMENT cho managed entity

Ví dụ:

~~~java
PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId
);

em.lock(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

Khi transaction thành công, provider phải thực hiện việc tăng version của Order theo semantics optimistic force increment.

### 8.1. Vì sao cần gọi rõ ràng?

Một service có thể thay đổi dữ liệu liên quan tới Order nhưng không sửa field của root, ví dụ điều chỉnh quantity của một OrderLine qua repository riêng. Nếu version của root là đại diện cho revision của aggregate, service có thể dùng force increment để ghi nhận thay đổi này.

### 8.2. Chi phí tăng version

Tăng version có thể yêu cầu thao tác SQL cập nhật row parent hoặc cơ chế provider tương đương, làm phát sinh:

- Một write operation.
- Lock/contestion ngắn ở DB khi thực hiện update.
- Thay đổi version visible sau commit.
- Optimistic conflicts với transaction khác dùng version cũ.
- Cache invalidation phù hợp với entity bị thay đổi.

Do đó **không dùng FORCE_INCREMENT một cách mặc định cho mọi SELECT**.

### 8.3. Version increment xảy ra khi nào?

Một số provider thực thi increment khi gọi `lock`, một số trì hoãn đến `flush` hoặc `commit`. JPA không yêu cầu ứng dụng nhìn thấy version Java mới ngay sau invocation của `OPTIMISTIC_FORCE_INCREMENT`.

Không viết business logic kiểu:

~~~java
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);

long newVersion = order.getVersion();

// Sai nếu mặc định newVersion đã được tăng ngay lập tức.
sendExternalEventWithVersion(newVersion);
~~~

Nếu cần công bố revision đã commit, cần workflow lấy committed version đúng cách, ví dụ sau transaction commit hoặc trong một transaction mới; không phát event trước commit chỉ dựa vào field mới có thể chưa được provider đồng bộ.

## 9. Dùng Query.setLockMode với JPQL

JPA hỗ trợ yêu cầu lock mode trên một JPQL entity query:

~~~java
TypedQuery<PurchaseOrder> query = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """,
    PurchaseOrder.class
);

PurchaseOrder order = query
    .setParameter("id", orderId)
    .setParameter("tenantId", tenantId)
    .setLockMode(LockModeType.OPTIMISTIC)
    .getSingleResult();
~~~

Ví dụ force increment:

~~~java
PurchaseOrder order = em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id = :id
    """,
    PurchaseOrder.class
)
.setParameter("id", orderId)
.setLockMode(LockModeType.OPTIMISTIC_FORCE_INCREMENT)
.getSingleResult();
~~~

### 9.1. Khi nào setLockMode trên query phù hợp?

- Query có WHERE business/authorization cần thiết.
- Không muốn `find` theo ID rồi kiểm tra tenant.
- Query trả managed entities được yêu cầu locking.
- Muốn đặt lock mode cùng nơi định nghĩa fetch/filter.

### 9.2. Không áp lock mode tùy tiện lên scalar/DTO query

Một projection:

~~~jpql
SELECT new com.example.shop.read.OrderSummary(o.id, o.status)
FROM PurchaseOrder o
~~~

không trả `PurchaseOrder` entity result để JPA đặt optimistic lock theo cách giống entity SELECT. Các quy tắc `Query.setLockMode` áp dụng cho JPQL/Criteria SELECT phù hợp; không mặc định rằng mọi aggregate, DTO constructor hoặc native query đều chấp nhận lock mode.

Nếu cần lock entity, hãy thực hiện một entity read/lock phù hợp trong transaction, sau đó đọc projection nếu cần. Đừng nghĩ gọi `setLockMode(OPTIMISTIC)` trên `COUNT(*)` có nghĩa khóa mọi entity được đếm.

### 9.3. Fetch plan và lock mode

Một entity query có thể kết hợp `JOIN FETCH` hoặc EntityGraph cùng optimistic lock. Tuy nhiên, fetched associations không tự động có version check riêng cho tất cả những entity liên quan. Cần xác định aggregate boundary và provider semantics thay vì mặc định “lock root = lock cả database graph”.

## 10. Dùng EntityManager.refresh với lock mode

JPA có overload:

~~~java
em.refresh(
    order,
    LockModeType.OPTIMISTIC
);
~~~

Ý nghĩa chính: yêu cầu provider refresh state từ DB và áp optimistic locking theo mode phù hợp.

### 10.1. Refresh có thể mất pending changes

Giả sử:

~~~java
order.changeShippingAddress(...); // Chưa flush.
em.refresh(order, LockModeType.OPTIMISTIC);
~~~

`refresh` có thể thay thế state in-memory bằng state DB và bỏ các thay đổi chưa flush trên entity. Không dùng refresh như một thao tác “đọc lại vô hại” trong command transaction.

### 10.2. Refresh và force increment

Provider có thể hỗ trợ:

~~~java
em.refresh(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);
~~~

Nhưng đây là thao tác gồm **tải lại state và yêu cầu force version increment**. Nếu không cần refresh mà chỉ muốn version increment, `em.lock(order, ...)` thường diễn đạt ý định rõ hơn.

### 10.3. Entity không tồn tại

Nếu row đã bị xóa, refresh/find có thể gặp exception hoặc null theo API. Không chỉ dựa vào optimistic version để phân biệt “đã xóa” với “đã sửa”; cần xử lý exception/data absence theo use case.

## 11. Lock mode và EntityManager.getLockMode

Trong transaction phù hợp, JPA có thể cho ứng dụng hỏi mode đang được yêu cầu trên managed entity:

~~~java
LockModeType mode = em.getLockMode(order);
~~~

Thông tin này hữu ích khi chẩn đoán code path, nhưng **không nên coi nó là bằng chứng version check đã hoàn tất ở DB hoặc version đã tăng**. Provider có thể trì hoãn phần việc đến flush/commit.

## 12. Timeline: OPTIMISTIC khi chỉ đọc một entity

Giả sử Order#41 version=12.

~~~text
                  Transaction A                  Transaction B
                  ----------------------------   -------------------------
T0                BEGIN
T1                Load Order#41 (v12)
T2                lock(OPTIMISTIC)
T3                                                 BEGIN
T4                                                 Load Order#41 (v12)
T5                                                 Sửa status
T6                                                 COMMIT, version -> v13
T7                Đến bước kiểm tra version
T8                Nhận thấy version đã đổi
T9                Optimistic lock conflict
T10               ROLLBACK
~~~

Điều quan trọng: transaction A **không cần sửa Order** để có lý do yêu cầu version check. Nó có thể chỉ đọc status để tính một quyết định sau đó.

### 12.1. Trường hợp chỉ load mà không explicit lock

Nếu A chỉ đọc một entity và không sửa nó, provider không nhất thiết buộc transaction A thất bại khi B sửa và commit. **Explicit OPTIMISTIC** thể hiện rằng quyết định của A phụ thuộc tính ổn định của version trong transaction.

### 12.2. Chỉ kiểm tra Order không đồng nghĩa bảo vệ mọi dữ liệu liên quan

Nếu B chỉ cập nhật Inventory hoặc một OrderLine mà **không thay Order.version**, A có thể không phát hiện qua version Order. Đó là vấn đề chọn đúng object/version đại diện cho invariant.

### 12.3. Database isolation vẫn có vai trò

Snapshot isolation, READ COMMITTED, REPEATABLE READ và row lock behavior có thể ảnh hưởng thời điểm đọc và phát hiện xung đột. JPA optimistic locking không hứa toàn bộ transaction đạt SERIALIZABLE.

## 13. Timeline: OPTIMISTIC_FORCE_INCREMENT khi Order root không dirty

Giả sử Order#41 version=12, gồm hai Lines. Transaction A chỉ thay một Line, và muốn parent revision tăng.

~~~text
Transaction A
---------------------------------------------------------
BEGIN
Load Order#41                  (version 12)
Load OrderLine#7001
Change quantity 1 -> 3
em.lock(Order#41, OPTIMISTIC_FORCE_INCREMENT)

Provider thực thi version check/force increment
(chính xác lúc lock/flush/commit tùy implementation)

COMMIT thành công
---------------------------------------------------------
Sau commit:
  order_line.quantity đã đổi
  purchase_order.version đã tiến lên theo provider
~~~

Nếu transaction B đồng thời thay Order root dựa trên version 12, cơ chế optimistic concurrency có thể phát hiện xung đột.

### 13.1. Force increment không sửa tự động các số liệu nghiệp vụ

Nếu đổi quantity từ 1 sang 3, `OPTIMISTIC_FORCE_INCREMENT` **không tự tính lại totalAmount**. Application vẫn phải áp đúng domain rules và cập nhật aggregate state nếu cần.

### 13.2. Không thể dùng force increment thay database constraint

Một foreign key, unique constraint, check constraint hoặc quy tắc inventory không được “bảo đảm” chỉ vì parent version tăng. Concurrency version là một lớp bảo vệ; invariant phải được kiểm soát ở đúng nơi.

### 13.3. Tất cả đường ghi phải cùng tuân thủ quy ước

Nếu service A dùng force increment khi sửa OrderLine nhưng service B sửa cùng OrderLine bằng native SQL mà không đụng Order.version, những transaction chỉ kiểm tra version root có thể bỏ sót thay đổi B.

Không có lựa chọn API đơn lẻ nào sửa được **quy ước version không được áp dụng nhất quán**.

## 14. Ví dụ hoàn chỉnh: OrderLine thay đổi làm root revision tăng

Giả sử repository method cập nhật số lượng dòng hàng trong một Order. Service muốn:

1. Chỉ sửa Line thuộc Order của tenant hiện tại.
2. Chỉ cho sửa khi Order còn PENDING.
3. Đảm bảo không âm thầm trộn những cập nhật aggregate cạnh tranh.
4. Yêu cầu Order.version tăng ngay cả nếu scalar fields của Order không dirty.

Ví dụ service:

~~~java
@Service
public class OrderLineApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void changeQuantity(
            long orderId,
            long lineId,
            long authenticatedTenantId,
            int newQuantity) {

        PurchaseOrder order = em.createQuery(
            """
            SELECT o
            FROM PurchaseOrder o
            WHERE o.id = :id
              AND o.tenantId = :tenantId
            """,
            PurchaseOrder.class
        )
        .setParameter("id", orderId)
        .setParameter("tenantId", authenticatedTenantId)
        .setLockMode(
            LockModeType.OPTIMISTIC_FORCE_INCREMENT
        )
        .getSingleResult();

        if (order.getStatus() != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Order cannot be edited"
            );
        }

        OrderLine line = em.createQuery(
            """
            SELECT l
            FROM OrderLine l
            WHERE l.id = :lineId
              AND l.order = :order
            """,
            OrderLine.class
        )
        .setParameter("lineId", lineId)
        .setParameter("order", order)
        .getSingleResult();

        line.changeQuantity(newQuantity);

        // Nếu totalAmount là thông tin dẫn xuất,
        // domain phải cập nhật nó đúng cách.
        // Force increment không tự tính tổng tiền.
    }
}
~~~

### 14.1. Tại sao lock được đặt trên Order, không chỉ OrderLine?

Trong thiết kế này, Order là aggregate root; mọi hành vi thay đổi dòng hàng phải được các transaction xử lý Order nhìn thấy thông qua revision root. Nếu chỉ version OrderLine, một reader chỉ lock/check Order root có thể không phát hiện.

### 14.2. Vì sao query tìm Line có điều kiện l.order = :order?

Nó bảo đảm lineId thuộc Order đã được xác thực. Nếu chỉ query Line theo ID mà không kiểm tra Order, caller có thể vô tình hoặc cố ý sửa Line thuộc Order khác.

### 14.3. Có cần gắn @Version lên OrderLine không?

Tùy consistency model. Nếu OrderLine tự có lifecycle và concurrency contract, version con có thể hữu ích. Tuy nhiên, version con không tự thay thế version root nếu invariant nằm ở cấp aggregate. Không nhất thiết mọi child đều phải có `@Version` độc lập; cần chọn theo domain boundary.

### 14.4. Khi nào pattern này không đủ?

Nếu quy tắc liên quan Inventory hoặc Payment ở các aggregate khác, chỉ tăng version Order chưa bảo vệ những aggregate đó. Cần transaction, lock/version của thực thể liên quan, constraint và idempotency tương ứng.

## 15. Tình huống chỉ dùng OPTIMISTIC: Đọc rồi quyết định về đối tượng khác

Giả sử trước khi cấp quyền tải tài liệu liên quan đến Order, service cần chắc chắn Order không bị hủy trong transaction.

~~~java
@Transactional
public void issueDocumentAccess(
        long orderId,
        long tenantId) {

    PurchaseOrder order = em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :orderId
          AND o.tenantId = :tenantId
        """,
        PurchaseOrder.class
    )
    .setParameter("orderId", orderId)
    .setParameter("tenantId", tenantId)
    .setLockMode(LockModeType.OPTIMISTIC)
    .getSingleResult();

    if (order.getStatus() == OrderStatus.CANCELLED) {
        throw new IllegalStateException(
            "Cannot issue access for cancelled order"
        );
    }

    // Ghi một record cấp quyền trong cùng DB transaction.
}
~~~

### 15.1. Vì sao không dùng FORCE_INCREMENT?

Service có thể chỉ cần xác nhận Order không đổi trong transaction, không có lý do nghiệp vụ nào để tăng Order.version nếu bản thân Order không bị thay đổi.

`OPTIMISTIC_FORCE_INCREMENT` có thể tạo write overhead và làm những transaction khác bị conflict không cần thiết.

### 15.2. Kiểm tra phiên bản không tự làm external call atomic

Nếu service gửi một request HTTP tới một dịch vụ khác **trước khi commit**, dù OPTIMISTIC lock sau đó phát hiện conflict và rollback, HTTP call đã xảy ra có thể không được hoàn tác.

Với side effect ngoài DB, dùng outbox, event after-commit hoặc một workflow nhất quán phù hợp; optimistic locking chỉ kiểm soát trạng thái DB version, không tự rollback hệ thống bên ngoài.

## 16. OPTIMISTIC_FORCE_INCREMENT để chống thay đổi aggregate ở cấp child

Một ví dụ phổ biến khác:

- Transaction A đang tổng hợp Order dựa trên tập Lines.
- Transaction B đang thêm Line mới.
- Order.root.version có thể không đổi nếu B chỉ insert một Line qua association owning side/SQL.
- A có thể commit quyết định dựa trên tập Lines cũ mà không phát hiện.

Nếu mọi transaction sửa Lines đều yêu cầu `OPTIMISTIC_FORCE_INCREMENT` trên Order, root.version có thể đóng vai trò **concurrency token của aggregate**.

~~~text
           Aggregate root version
                       |
            +----------+----------+
            |                     |
        Root fields           Child operations
            |                     |
            v                     v
   Managed update          Force increment root
            |                     |
            +----------+----------+
                       |
                       v
            Version khác nhau sau
            những thay đổi đã commit
~~~

### 16.1. Không được nói “mọi @OneToMany update đều tăng parent version”

Tùy owning side, cascade, association mapping và provider, sửa collection có thể hoặc không làm version root tăng theo các quy tắc riêng. Cần **kiểm tra behavior chính xác của mapping**. Nếu yêu cầu chắc chắn root version đại diện cho thay đổi child, explicit force increment là một kỹ thuật rõ ý định.

### 16.2. Thiết kế một con đường ghi thống nhất

Nên gom các thao tác child vào application service/domain methods có quyền cập nhật aggregate, thay vì mỗi controller tự update `order_line`. Nhờ đó force increment không bị bỏ quên ở một số code path.

### 16.3. Đừng force increment sau khi transaction đã commit

Một lời gọi `em.lock(..., OPTIMISTIC_FORCE_INCREMENT)` phải thuộc transaction chứa thay đổi aggregate cần bảo vệ. Nếu sửa child trong transaction A rồi force increment root ở transaction B, có một khoảng trạng thái không đồng bộ và mất tính nguyên tử của quy ước root revision.

## 17. Flush, commit và thời điểm phát hiện xung đột

Ba thời điểm thường bị nhầm:

- **`em.lock(...)`**: yêu cầu lock mode.
- **`em.flush()`**: đồng bộ pending changes trong transaction với DB.
- **`commit()`**: kết thúc transaction thành công hoặc thất bại.

Đối với optimistic locking, provider có thể trì hoãn kiểm tra version hoặc increment đến một thời điểm phù hợp. Vì vậy exception có thể xuất hiện khi:

1. Gọi `em.lock`.
2. Thực hiện một operation đồng bộ cần thiết.
3. Gọi `em.flush`.
4. Gọi transaction commit.

### 17.1. Không giả định lock() thành công tức giao dịch không thể conflict

~~~java
em.lock(order, LockModeType.OPTIMISTIC);
doWork();
tx.commit();
~~~

Một transaction khác vẫn có thể thay entity trước thời điểm phiên bản được xác nhận. Phải xử lý conflict cả ở bước commit.

### 17.2. Flush không phải commit

~~~java
em.flush();
~~~

có thể làm SQL update/version increment được thực hiện trong transaction, nhưng transaction vẫn có thể rollback. Không phát external event “đã hoàn tất” chỉ dựa vào flush thành công.

### 17.3. Version in memory có thể chưa phản ánh ngay

Sau `OPTIMISTIC_FORCE_INCREMENT`, đừng dựa vào `order.getVersion()` tức thì để làm mã version đã được commit. Provider có quyền trì hoãn thay đổi version theo implementation.

### 17.4. Auto flush trên query

Nếu entity có dirty changes và application chạy JPQL query, `FlushModeType.AUTO` có thể khiến provider flush trước khi query. Khi dùng explicit locking, thứ tự flush/SQL tùy provider và query semantics. Nếu business logic phụ thuộc thứ tự đặc biệt, thiết kế boundary rõ và kiểm thử trên stack thực.

## 18. Transaction trong JPA RESOURCE_LOCAL

Ví dụ trực tiếp:

~~~java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    PurchaseOrder order = em.find(
        PurchaseOrder.class,
        orderId,
        LockModeType.OPTIMISTIC
    );

    if (order == null) {
        throw new NoSuchElementException();
    }

    // Kiểm tra và thực hiện business operation.

    tx.commit();

} catch (RuntimeException original) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackError) {
            original.addSuppressed(rollbackError);
        }
    }
    throw original;
} finally {
    em.close();
}
~~~

### 18.1. Vì sao catch cả exception từ commit?

Optimistic conflict có thể chỉ xuất hiện khi commit. Nếu chỉ try/catch xung quanh `em.lock` mà không bao gồm `tx.commit()`, application có thể bỏ sót điểm thất bại.

### 18.2. Transaction sau conflict

Một optimistic locking failure thường khiến transaction bị rollback hoặc đánh dấu rollback-only. Không bắt exception rồi cố tiếp tục dùng cùng persistence context như thể chưa có gì xảy ra.

### 18.3. RESOURCE_LOCAL không áp dụng cho mọi environment

Trong Spring/JTA application, transaction manager sở hữu transaction; không tự gọi `getTransaction().begin()` trên container-managed JTA EntityManager.

## 19. Transaction trong Spring

Ví dụ:

~~~java
@Service
public class OrderReviewService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void approve(
            long tenantId,
            long orderId) {

        PurchaseOrder order = em.createQuery(
            """
            SELECT o
            FROM PurchaseOrder o
            WHERE o.id = :id
              AND o.tenantId = :tenantId
            """,
            PurchaseOrder.class
        )
        .setParameter("id", orderId)
        .setParameter("tenantId", tenantId)
        .setLockMode(LockModeType.OPTIMISTIC)
        .getSingleResult();

        order.approve();
    }
}
~~~

Tại đây việc sửa managed Order theo domain method thường đã sử dụng `@Version`. Explicit `OPTIMISTIC` có thể không mang thêm lợi ích đáng kể nếu JPA sẽ ghi chính root trong transaction; nhưng nó làm rõ yêu cầu bảo vệ một lần đọc trong một số workflows.

### 19.1. Với FORCE_INCREMENT, không dùng readOnly transaction một cách mù quáng

~~~java
@Transactional(readOnly = true)
public void touchVersion(...) {
    em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
}
~~~

là cấu hình trái mục đích, bởi force increment có thể cần một operation ghi version. Spring `readOnly=true` là hint/cấu hình cho transaction/provider; tùy DB/transaction manager, write có thể bị từ chối hoặc không flush như mong đợi.

Nên dùng transaction cho phép ghi nếu có chủ đích ép version increment.

### 19.2. Self-invocation

Với proxy-based transaction handling phổ biến của Spring, lời gọi từ method trong cùng bean tới một method `@Transactional` khác có thể bỏ qua interceptor. Hậu quả là `em.lock` được gọi ngoài transaction mong muốn.

Đặt transaction boundary tại service method được gọi qua Spring proxy hoặc dùng cơ chế transaction rõ ràng.

### 19.3. Exception có thể được Spring dịch

Một lỗi version JPA/Hibernate có thể được Spring chuyển thành exception thuộc nhóm optimistic locking của Spring DataAccessException, hoặc nằm trong rollback exception từ commit. Xử lý ở đúng tầng service/API và không ràng buộc tất cả code vào duy nhất một class exception khi dùng framework.

## 20. Spring Data JPA @Lock

Spring Data cung cấp annotation `@Lock` cho repository query methods:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Lock(LockModeType.OPTIMISTIC)
    @Query("""
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :id
          AND o.tenantId = :tenantId
        """)
    Optional<PurchaseOrder> findForReview(
        @Param("id") Long id,
        @Param("tenantId") Long tenantId
    );
}
~~~

Một method khác:

~~~java
@Lock(LockModeType.OPTIMISTIC_FORCE_INCREMENT)
@Query("""
    SELECT o
    FROM PurchaseOrder o
    WHERE o.id = :id
      AND o.tenantId = :tenantId
    """)
Optional<PurchaseOrder> findForAggregateChange(
    @Param("id") Long id,
    @Param("tenantId") Long tenantId
);
~~~

### 20.1. @Lock là API Spring Data

`org.springframework.data.jpa.repository.Lock` không phải annotation chuẩn JPA entity. Nó giúp khai báo query lock mode ở repository level, sau đó Spring Data phối hợp với JPA provider.

### 20.2. Transaction vẫn cần thiết

Thêm `@Lock` lên repository method không tự bảo đảm application đã mở transaction đúng phạm vi business workflow. Gọi từ service `@Transactional` cho toàn thao tác có liên quan.

### 20.3. Khi nào chọn @Lock vs em.lock?

- `@Lock`: mode gắn cố định với repository query method.
- `em.lock`: code đã có managed entity và muốn yêu cầu version check/increment tại một bước cụ thể.
- `Query.setLockMode`: muốn mode gắn với JPQL query mà không tạo repository annotation.

Đừng dùng cả ba chồng lên nhau không cần thiết; chọn API làm rõ ý định.

## 21. @Version tự động so với explicit OPTIMISTIC

Nếu một transaction tải Order rồi đổi status:

~~~java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.approve();
~~~

JPA thường kiểm tra version và tăng version khi flush changes của managed versioned entity. Vì vậy explicit:

~~~java
em.lock(order, LockModeType.OPTIMISTIC);
~~~

thường không cần thiết chỉ để đạt optimistic locking của **chính update này**.

### 21.1. Khi explicit OPTIMISTIC có thêm ý nghĩa

Một service:

1. Đọc Order để kiểm tra status.
2. Cập nhật một entity khác hoặc ghi một permission record.
3. Không sửa Order.
4. Muốn transaction thất bại nếu Order bị thay đổi theo version trong khoảng đó.

Nếu không yêu cầu lock, provider không có lý do phải kiểm tra Order.version ở commit khi Order chỉ được đọc.

### 21.2. @Version không tự bảo vệ read dependencies khác

Nếu business decision phụ thuộc Order và Inventory, chỉ version Order không bảo vệ Inventory. Cần đặt optimistic lock trên những entities liên quan hoặc thiết kế constraint/isolation khác.

### 21.3. Force increment khi entity root đã dirty

Nếu bạn đã sửa một field trên root, JPA sẽ cập nhật version theo managed update. Gọi thêm `OPTIMISTIC_FORCE_INCREMENT` có thể là thừa và phát sinh overhead; timing/số lần increment phụ thuộc semantics và provider. Đừng gọi chỉ để “chắc chắn hơn” khi chưa có yêu cầu aggregate-specific.

## 22. Bulk JPQL UPDATE/DELETE có thể bỏ qua version handling

Một câu bulk JPQL:

~~~java
int changed = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :cancelled
    WHERE o.tenantId = :tenantId
      AND o.status = :pending
    """
)
.setParameter("cancelled", OrderStatus.CANCELLED)
.setParameter("pending", OrderStatus.PENDING)
.setParameter("tenantId", tenantId)
.executeUpdate();
~~~

không tự áp dụng optimistic locking/version increment cho từng managed entity theo cách gọi domain setter rồi flush.

### 22.1. Nguy cơ

Transaction A đang giữ Order.version=12. Transaction B bulk UPDATE đổi status nhưng không tăng version root; A có thể không phát hiện thay đổi B chỉ nhờ version 12.

### 22.2. Có thể viết version increment trong bulk JPQL không?

Không nên tự giả định một mẫu SET version là portable cho mọi JPA provider, kiểu version và version ownership rule. Một số provider có extension cho versioned bulk update; SQL native cũng có thể quản lý version tường minh theo hợp đồng DB-level.

Nếu hệ thống yêu cầu optimistic concurrency end-to-end, lựa chọn thường an toàn hơn là:

- Cập nhật từng managed entity khi cần JPA quản lý `@Version`.
- Dùng conditional update có kiểm tra expected version và tăng version đúng cách theo chiến lược đã kiểm thử.
- Dùng provider-specific versioned bulk feature có tài liệu/kiểm thử.
- Tránh trộn bulk DML với entity update trên cùng row mà không có thiết kế state/version.

### 22.3. Native SQL cũng phải tuân thủ quy ước

Một external job/update trigger hoặc SQL script sửa bảng nhưng không thay version có thể phá contract optimistic locking của application. Cần quản trị tất cả đường ghi, không chỉ JPA repositories.

## 23. PESSIMISTIC và OPTIMISTIC có thể cùng xuất hiện không?

Một transaction có thể cần pessimistic lock ở một điểm và optimistic version ở điểm khác. Nhưng **không coi chúng là hai tên cho cùng cách khóa**.

### 23.1. Optimistic

- Không yêu cầu giữ row lock từ lúc đọc.
- Phát hiện conflict qua version theo semantics JPA.
- Phù hợp khi contention thấp và retry chấp nhận được.
- Conflict có thể lộ muộn ở flush/commit.

### 23.2. Pessimistic

- Yêu cầu DB lock theo lock mode, dialect và transaction.
- Có thể chặn transaction khác, timeout hoặc deadlock.
- Phù hợp hơn trong một số nghiệp vụ contention cao hoặc tài nguyên phải được serialize từ sớm.
- Có thể gây bottleneck nếu lock giữ lâu.

### 23.3. PESSIMISTIC_FORCE_INCREMENT

Đây là mode khác với `OPTIMISTIC_FORCE_INCREMENT`. Nó kết hợp pessimistic locking với yêu cầu tăng version, không phải lựa chọn mặc định chỉ vì muốn tăng revision root.

### 23.4. Không có chiến lược nào thay việc đo contention

Nếu optimistic conflicts quá thường xuyên, retry hàng loạt có thể làm throughput giảm. Nếu pessimistic locks giữ lâu, latency/lock wait tăng. Cần đo workload thực tế để chọn.

## 24. OptimisticLockException và các cách lỗi xuất hiện

Khi provider phát hiện optimistic conflict, JPA có `OptimisticLockException`. Trong Spring/Hibernate có thể có exception khác hoặc exception wrapper liên quan.

Ví dụ:

~~~java
try {
    em.lock(order, LockModeType.OPTIMISTIC);
    // Work...
    em.flush();
} catch (OptimisticLockException ex) {
    // Transaction hiện tại không được tiếp tục commit
    // như thể thao tác vẫn còn hợp lệ.
    throw ex;
}
~~~

**Đoạn này không đảm bảo catch tại flush là đủ**, vì conflict có thể chỉ xuất hiện ở transaction commit ngoài method. Phải có xử lý exception tại transaction boundary.

### 24.1. Lỗi không nhất thiết xuất hiện ngay tại lock()

Có thể:

~~~text
em.lock(...): thành công
em.flush():  thành công
commit():    optimistic conflict
~~~

hoặc provider có thể báo sớm hơn. Đừng cho phép application gửi success response trước khi transaction owner xác nhận commit.

### 24.2. Sau conflict cần rollback

Một optimistic-lock failure thường làm transaction rollback-only hoặc cần rollback. Không sửa object cũ rồi retry tiếp trong **cùng transaction đã thất bại**.

### 24.3. Phân biệt không tìm thấy và version mismatch

`find` có thể trả null nếu ID không tồn tại; `getSingleResult` có thể ném `NoResultException`. OptimisticLockException chỉ ra conflict/kiểm tra version thất bại. Các trường hợp này có thể dẫn tới HTTP response khác nhau tùy API contract.

### 24.4. Exception không phải bằng chứng user cố tình sửa dữ liệu

Hai transaction hợp lệ có thể cạnh tranh bình thường. Conflict là một tín hiệu cần retry hoặc trả thông báo phù hợp, không phải lỗi đạo đức của người dùng.

## 25. Có nên tự động retry?

Một optimistic conflict có thể được xử lý bằng retry, nhưng phải cân nhắc use case.

### 25.1. Retry phù hợp với thao tác ngắn/idempotent

Ví dụ một background job cập nhật một giá trị theo quy tắc có thể tính lại từ state mới. Một chiến lược:

1. Rollback transaction cũ.
2. Tạo transaction/persistence context mới.
3. Tải lại entity và version mới.
4. Đánh giá lại business condition.
5. Thực hiện lệnh mới.
6. Giới hạn số lần thử và backoff khi cần.

### 25.2. Retry không tự phù hợp với hành vi người dùng

Nếu user vừa sửa địa chỉ giao hàng dựa trên form cũ, tự retry bằng cách ghi đè bản mới có thể xóa thay đổi của người khác. Một API nên báo conflict để client refresh/merge theo chính sách rõ ràng.

### 25.3. Không retry external side effects mù quáng

Nếu transaction đã gọi payment provider hoặc gửi email trước khi commit rồi gặp conflict, retry có thể gọi lại lần nữa. Cần idempotency key, outbox, after-commit event hoặc orchestration phù hợp.

### 25.4. Một mẫu retry pseudocode

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        return transactionRunner.runInNewTransaction(
            () -> performOperationWithFreshEntity()
        );
    } catch (OptimisticLockingFailureException conflict) {
        if (attempt == maxAttempts) {
            throw conflict;
        }
        // Backoff có giới hạn nếu cần.
    }
}
~~~

`transactionRunner` là abstraction minh họa; mỗi lần retry phải có **transaction mới**. Với Spring proxy transactions, cần tránh self-invocation làm retry tái sử dụng cùng transaction đã rollback-only.

## 26. Optimistic version và HTTP ETag/If-Match

Một REST API có thể dùng version như một concurrency token:

~~~json
{
  "id": 41,
  "status": "PENDING",
  "version": 12
}
~~~

Client gửi lệnh update kèm version đã đọc:

~~~text
PATCH /orders/41
If-Match: "12"
~~~

Server có thể:

1. Xác thực caller và tenant.
2. Tải managed entity trong transaction.
3. Kiểm tra version/expected token.
4. Thực thi domain method.
5. Để JPA optimistic locking kiểm tra lại ở flush/commit.
6. Trả HTTP response thành công sau commit hoặc conflict khi version cũ.

### 26.1. ETag không bắt buộc phải chính là @Version

Trong HTTP, ETag có thể được sinh từ representation/record revision theo contract của API. Nếu dùng JPA `@Version` trực tiếp làm ETag, phải hiểu version có thể thay đổi vì các operation như `OPTIMISTIC_FORCE_INCREMENT` ngay cả khi response fields không đổi.

### 26.2. Tránh TOCTOU

Check version bằng Java trước khi update là một kiểm tra ban đầu, nhưng transaction khác có thể đổi record **sau** thời điểm đó. JPA optimistic locking lúc flush/commit (hoặc một conditional UPDATE) vẫn cần thiết để phát hiện xung đột.

### 26.3. Phân biệt HTTP status

Tùy API contract, stale precondition có thể dùng `412 Precondition Failed` khi xử lý `If-Match`; một business conflict có thể dùng `409 Conflict`. Không có ánh xạ một-một bắt buộc từ mọi JPA OptimisticLockException sang cùng status cho mọi API.

## 27. OPTIMISTIC_FORCE_INCREMENT có phải cách tạo “logical write” không?

Có. Nó có thể đại diện cho một **revision change** mà không cần sửa field nghiệp vụ trên root.

Ví dụ khi thay OrderLine, service muốn Order.version tăng để:

- Các editor khác biết aggregate đã đổi.
- Tránh chấp nhận form cũ.
- Buộc transaction đang dựa trên root version phải xem lại.
- Làm concurrency token của aggregate root phản ánh những child modifications quan trọng.

### 27.1. Không nên dùng để lưu thời gian “đã xem”

Nếu chỉ user mở trang Order, tăng version có thể gây:

- Vô số updates không cần thiết.
- Tranh chấp version giữa readers.
- Các editor bị optimistic conflict do người khác chỉ xem trang.
- Cache churn và write amplification.

Nếu cần analytics “view count” hoặc “last viewed at”, cân nhắc event/read tracking riêng, không ép optimistic version chỉ vì đọc.

### 27.2. Không đồng nhất version increment với domain event

Version thay đổi chỉ biểu thị revision/concurrency token. Nó không tự phát `OrderLineChanged` hoặc `OrderApproved` domain event.

Nếu nghiệp vụ cần audit hoặc outbox per change, phải thiết kế những records/events đó riêng trong transaction.

### 27.3. Version không phải audit history

Từ version=12 sang 13 không cho biết ai đã sửa, sửa trường nào hoặc vì sao. Audit log cần dữ liệu và cơ chế riêng; optimistic locking không thay thế audit.

## 28. FORCE_INCREMENT và quan hệ cascade

Không nên nghĩ:

~~~java
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

sẽ ép tăng version của **mọi child entity** trong `order.getLines()`.

Lock propagation và cascade locking chịu quy tắc JPA/mapping như `CascadeType.LOCK`, nhưng không thể suy rộng từ việc khóa root thành “tăng version toàn object graph”. Phải xác định entity nào được yêu cầu lock và kiểm tra version riêng khi cần.

### 28.1. Aggregate version thường là một cơ chế phối hợp

Nếu Order được chọn là root concurrency token, việc tăng version root có thể là đủ để báo aggregate đã thay đổi, miễn tất cả đường ghi child đều tuân theo quy tắc đó.

### 28.2. Nhưng child identity và invariant vẫn tồn tại

Các OrderLine có thể có constraint/unique key riêng; force increment root không tự kiểm tra quantity>0, Product availability hoặc FK consistency. Những quy tắc ấy phải được bảo vệ bằng domain logic/DB constraints.

## 29. Khi query chỉ đọc DTO, có cần OPTIMISTIC không?

Giả sử một query tạo DTO:

~~~java
List<OrderSummary> summaries = em.createQuery(
    """
    SELECT new com.example.shop.read.OrderSummary(
        o.id, o.status, o.totalAmount
    )
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
    """,
    OrderSummary.class
).getResultList();
~~~

Nếu use case chỉ hiển thị dashboard, thường **không cần đặt optimistic lock trên từng Order**. DTO là một snapshot để đọc, không đại diện cho transaction update.

Nếu sau đó người dùng gửi command sửa Order dựa trên version cũ, command phải **mở transaction mới, tải state mới và kiểm tra concurrency**.

### 29.1. Không khóa hàng trăm nghìn entities chỉ để vẽ report

Optimistic checking cho toàn bộ tập row có thể tạo overhead không cần thiết, và force increment trên một tập lớn còn biến báo cáo thành write workload.

### 29.2. Khi report cần snapshot nhất quán

Nếu báo cáo cần đồng nhất giữa nhiều bảng và nhiều SELECT, `OPTIMISTIC` trên một root có thể không bảo vệ tất cả nguồn dữ liệu. Cần transaction isolation/snapshot hoặc thiết kế báo cáo phù hợp.

## 30. Chọn lock mode dựa trên invariant

Một bảng quyết định:

| Use case | Lựa chọn cân nhắc | Lý do |
|---|---|---|
| Load Order, sửa Order.status | `@Version` thường đủ | Managed update kiểm tra version |
| Load Order, chỉ kiểm tra status rồi ghi record khác | `OPTIMISTIC` | Phát hiện Order đổi trong transaction |
| Sửa OrderLine, muốn root revision tăng | `OPTIMISTIC_FORCE_INCREMENT` | Root không nhất thiết dirty |
| Chỉ hiển thị Order list | Không explicit lock | Tránh overhead |
| Chỉ hiển thị Order details | Không explicit lock theo mặc định | Snapshot cho UI, command sẽ kiểm tra sau |
| Chỉnh sửa aggregate ở nhiều child tables | FORCE_INCREMENT root hoặc model locking khác | Cần đồng bộ revision toàn aggregate |
| Update hàng loạt 1 triệu Order | Bulk DML/chiến lược riêng | Không force-lock từng entity vô cớ |
| Tài nguyên contention cao, cần serialize writer | Cân nhắc PESSIMISTIC_WRITE/DB strategy | Optimistic retries có thể đắt |
| Query COUNT báo cáo | Không setLockMode trên scalar query | Không có entity result để lock |
| External payment call kéo dài | Không giữ transaction quanh network call | Outbox/idempotency/đối soát |
| API edit form có expected version | JPA @Version + client concurrency token | Tránh ghi đè state cũ |

Không áp dụng table như lệnh tuyệt đối; thiết kế cuối cùng phải theo transaction và concurrency semantics thật.

## 31. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `TransactionRequiredException` khi lock | Không có active transaction phù hợp | Đặt transaction boundary đúng |
| `IllegalArgumentException` khi em.lock | Entity không managed hoặc kiểu không hợp lệ | Tải managed entity trong current EM |
| Optimistic conflict lúc commit | Transaction khác đã đổi version | Rollback, báo conflict hoặc retry từ transaction mới |
| Lock call thành công nhưng commit fail | Version check có thể trì hoãn | Bắt lỗi tại transaction owner |
| Version không tăng sau OPTIMISTIC | Chế độ không force increment | Dùng FORCE_INCREMENT khi business cần |
| Version không tăng ngay sau FORCE_INCREMENT | Increment có thể trì hoãn | Không đọc immediate version như committed version |
| Read-only service FORCE_INCREMENT lỗi | Transaction không cho phép ghi/flush | Dùng write transaction |
| Root version không đổi khi sửa child | Child update không nhất thiết dirty parent | Áp quy ước force root increment |
| Parent force increment nhưng vẫn bỏ sót conflict | Một số đường ghi khác không tăng parent version | Đồng bộ mọi code path/DB writer |
| @Version bị bypass bởi bulk UPDATE | Bulk DML không tự version từng entity | Conditional update/version strategy |
| Force increment mỗi GET gây nhiều conflicts | Read bị biến thành write | Chỉ dùng khi có revision semantic |
| Native UPDATE không thay version | Raw SQL bỏ qua JPA lifecycle | Bảo đảm DB-level version management |
| Dùng setLockMode trên DTO query lỗi | Không có entity result để lock | Lock entity riêng hoặc thiết kế concurrency khác |
| Gửi event trước commit rồi rollback | Side effect ngoài DB không rollback | Outbox/after-commit/idempotency |
| Retry cùng EntityManager sau conflict | Transaction/context có thể rollback-only/stale | Transaction và context mới |
| Test không phát hiện conflict | Dùng cùng EntityManager/snapshot không tạo cạnh tranh thật | Hai independent EM/transactions |
| Version timestamp không hoạt động như long | Version type/provider khác | Dùng type/mapping được hỗ trợ |
| Force increment làm DB chậm | Nhiều writes/lock contention | Đánh giá use case và đo workload |
| Lầm OPTIMISTIC với DB row lock | Hiểu sai semantics | Phân biệt optimistic vs pessimistic |
| Client version không khớp | Form/API snapshot cũ | Trả precondition/conflict và yêu cầu refresh |

### 31.1. Đừng catch OptimisticLockException rồi trả success

Nếu transaction đã rollback, application không được trả “đã lưu” chỉ vì đã gọi setter hay `em.lock` thành công trước đó.

### 31.2. Đừng convert mọi exception thành OptimisticLockException

Timeout, constraint violation, deadlock, connection failure, missing entity là những lỗi khác nhau và cần chính sách xử lý khác.

### 31.3. Đừng rely vào SQL log để kết luận commit

SQL UPDATE version có thể xuất hiện rồi transaction rollback. Chỉ đọc bằng transaction/context khác sau commit mới phản ánh trạng thái đã xác nhận, tùy isolation/cache.

## 32. Kiểm thử tích hợp với hai transaction riêng biệt

Muốn biết optimistic lock hoạt động, cần tạo **xung đột thật** trên cùng version.

### 32.1. Test OPTIMISTIC: A chỉ đọc và lock, B cập nhật

Fixture:

~~~text
Order#41: status=PENDING, version=12
~~~

Tiến trình ý tưởng:

~~~text
A: BEGIN
A: load Order#41 (v12), request OPTIMISTIC

B: BEGIN
B: load Order#41 (v12)
B: change status and COMMIT -> version moved

A: COMMIT
A: expected optimistic conflict / rollback
~~~

Dùng hai `EntityManager`/transaction riêng. Đừng dùng một EM duy nhất để “giả lập” hai transaction concurrent bằng cách trộn operation vì first-level cache và transaction sharing có thể làm test vô nghĩa.

### 32.2. Pseudocode setup hai EntityManagers

~~~java
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    EntityTransaction txA = emA.getTransaction();
    EntityTransaction txB = emB.getTransaction();

    txA.begin();

    PurchaseOrder fromA = emA.find(
        PurchaseOrder.class,
        orderId,
        LockModeType.OPTIMISTIC
    );

    txB.begin();

    PurchaseOrder fromB = emB.find(
        PurchaseOrder.class,
        orderId
    );

    fromB.approve();
    txB.commit();

    // Không sửa fromA, nhưng transaction A đã yêu cầu
    // OPTIMISTIC version check.
    assertThrows(
        RuntimeException.class,
        txA::commit
    );
} finally {
    // Rollback transaction active nếu cần.
    // Đóng emA và emB.
}
~~~

**Lưu ý:** Đoạn trên minh họa ý tưởng concurrency. Một số DB/isolation/provider có thể khiến txB chờ hoặc báo conflict ở thời điểm khác; integration test production-grade nên sử dụng hai threads/connections, latches/timeouts và assertion exception có chọn lọc, không mặc định trình tự một-thread này sẽ không bị block trên mọi database.

### 32.3. Tại sao không assert đúng exception class ở mọi tầng?

JPA có `OptimisticLockException` nhưng khi fail ở commit, `RollbackException` hoặc Spring-translated exception có thể bọc root cause. Test cần kiểm tra loại conflict theo transaction stack thực, không bỏ qua lỗi bất kỳ bằng một assertion RuntimeException chung trong test cuối.

## 33. Kiểm thử FORCE_INCREMENT: Không dirty root vẫn tăng version

Fixture:

~~~text
Order#41: version=12
~~~

Test khái niệm:

~~~java
long before;
long after;

EntityManager first = emf.createEntityManager();

try {
    first.getTransaction().begin();

    PurchaseOrder order =
        first.find(PurchaseOrder.class, orderId);

    before = order.getVersion();

    first.lock(
        order,
        LockModeType.OPTIMISTIC_FORCE_INCREMENT
    );

    first.getTransaction().commit();
} finally {
    first.close();
}

EntityManager second = emf.createEntityManager();
try {
    PurchaseOrder reloaded =
        second.find(PurchaseOrder.class, orderId);

    after = reloaded.getVersion();
} finally {
    second.close();
}

assertTrue(after > before);
~~~

Ví dụ giả định version kiểu `long` và provider quản lý tăng version theo thứ tự. Trong test thực, cleanup transaction khi lỗi và xác nhận DB version sau commit qua context mới. Nếu version dùng timestamp hoặc non-monotonic representation, không dùng so sánh `after > before` theo kiểu long.

### 33.1. Không kiểm tra ngay sau lock() thay cho sau commit

Sai assumption:

~~~java
long before = order.getVersion();

em.lock(
    order,
    LockModeType.OPTIMISTIC_FORCE_INCREMENT
);

assertEquals(before + 1, order.getVersion());
~~~

Provider có thể trì hoãn increment. Test nên xác nhận sau commit bằng context mới.

### 33.2. Kiểm thử OPTIMISTIC không làm tăng version

Trong một transaction chỉ đọc và gọi OPTIMISTIC, nếu không có writer nào khác và không sửa entity, version không nên được force-increment chỉ vì lock request.

### 33.3. Kiểm thử không có @Version

Nếu entity không versioned, provider có thể không hỗ trợ lock mode; test dự án nên phản ánh contract provider thật thay vì giả định tính portable.

## 34. Kiểm thử aggregate child và root revision

Một bài test quan trọng:

1. Insert Order với OrderLine.
2. Đọc `Order.version` ban đầu và commit.
3. Trong transaction khác, load Order, gọi `OPTIMISTIC_FORCE_INCREMENT` trên root.
4. Đổi quantity của một OrderLine.
5. Commit.
6. Đọc lại Order ở EntityManager khác, xác nhận version root đã tiến lên.
7. Đọc lại Line, xác nhận quantity mới.

### 34.1. Test two-writer conflict

Với hai transaction cùng sửa child/aggregate, cả hai đều force increment root. Test rằng hệ thống không âm thầm chấp nhận hai quyết định cạnh tranh dựa trên version cũ khi invariant yêu cầu một trong hai phải retry hoặc fail.

Dùng test orchestration rõ ràng với barriers/latches và connection pool đủ hai connections; không dùng chung EntityManager qua thread.

### 34.2. Test đường ghi bỏ qua force increment

Nếu có native SQL/job sửa OrderLine, kiểm tra root.version có tăng theo chính sách không. Đây là test kiến trúc quan trọng để phát hiện một đường ghi phá concurrency contract.

### 34.3. Đừng chỉ nhìn số SQL statement

Provider có thể sinh thêm SELECT/UPDATE hoặc trì hoãn operation. Test cần tập trung vào **version conflict semantics và database state cuối cùng**, còn SQL count là thông tin bổ sung về performance.

## 35. Kiểm thử trên database mục tiêu

Khác biệt giữa H2, PostgreSQL, MySQL, Oracle hoặc provider versions có thể liên quan:

- Transaction isolation.
- Row lock và update blocking.
- Version column type/precision.
- SQL do provider sinh cho optimistic checks.
- Thời điểm version increment.
- Exception wrappers.
- Deadlock/timeout và retry.
- Cache invalidation.
- Flush timing.

Do đó, kiểm thử optimistic locking quan trọng nên chạy trên DB/dialect tương ứng production, không chỉ dựa vào một unit test mock `EntityManager`.

### 35.1. Đừng viết unit test bằng mock để chứng minh concurrency

Mock có thể xác nhận `em.lock(order, OPTIMISTIC_FORCE_INCREMENT)` đã được gọi, nhưng không chứng minh transaction/DB/provider sẽ phát hiện conflict.

### 35.2. Kiểm tra transaction rollback

Sau conflict, mở context mới và xác nhận các thay đổi của transaction thất bại **không được commit**. Đừng assert trên instance detached cũ.

### 35.3. Test timeout khi contention

Khi test FORCE_INCREMENT cạnh tranh, có thể xảy ra lock wait. Đặt timeout cho test để phát hiện deadlock, không để CI treo vô hạn.

## 36. Tối ưu hiệu năng và giảm xung đột

### 36.1. Chỉ explicit lock khi cần

Nếu một query chỉ hiển thị Order, không yêu cầu lock optimistic mỗi lần. Nếu một command sửa chính root đã có `@Version`, explicit lock có thể là thừa.

### 36.2. Cân nhắc độ hạt của version

Dùng một root version cho aggregate rất lớn có thể khiến những thay đổi độc lập ở các child cùng tranh chấp một row version. Điều đó có thể đúng nếu invariant buộc serialize các thay đổi đó, nhưng nếu các child thực sự độc lập, cân nhắc tách aggregate/version boundaries.

### 36.3. Giảm thời gian transaction

Optimistic locking không chủ đích giữ read lock lâu, nhưng transaction dài làm tăng khả năng state thay đổi trong lúc xử lý. Tránh gọi external APIs hoặc xử lý nặng khi đang giữ transaction mở mà không có lý do.

### 36.4. Retry có giới hạn

Nếu contention cao, retry quá nhiều làm tăng workload và có thể tạo vòng lặp conflict. Dùng bounded retries, metrics và backoff có điều kiện.

### 36.5. Metric cần theo dõi

- Tỷ lệ optimistic conflicts theo use case.
- Số lần retry trung bình.
- Tỷ lệ transaction rollback.
- Latency P95/P99.
- Lock wait/deadlock nếu DB updates cạnh tranh.
- Số lần force increment root.
- Số lượng write từ các read-like workflows.
- Lỗi idempotency của side effects.

Một hệ thống có hàng nghìn optimistic conflicts mỗi giây có thể cần xem lại domain aggregate boundary hoặc concurrency strategy.

## 37. Bài tập thực hành

### Bài 1. Phân biệt hai mode

**Câu hỏi:** `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT` đều kiểm tra version. Mode nào yêu cầu tăng version ngay cả khi entity không dirty?

**Đáp án:** `OPTIMISTIC_FORCE_INCREMENT`.

### Bài 2. Chỉ đọc một Order

Service đọc Order và chỉ hiển thị lên UI, không ra quyết định ghi trong transaction.

**Câu hỏi:** Có cần FORCE_INCREMENT không?

**Đáp án:** Thường không. Đọc hiển thị là snapshot, không nên biến thành write workload vô ích.

### Bài 3. Đọc để ra quyết định

Service đọc Order.status, ghi một access record nhưng không sửa Order; cần biết nếu Order bị sửa trước commit.

**Đáp án:** Cân nhắc `OPTIMISTIC` trên Order trong transaction.

### Bài 4. Sửa OrderLine

Service đổi quantity nhưng scalar fields của Order không dirty; nghiệp vụ yêu cầu Order.version đại diện cho thay đổi aggregate.

**Đáp án:** Có thể yêu cầu `OPTIMISTIC_FORCE_INCREMENT` trên managed Order root, trong cùng transaction với việc sửa Line.

### Bài 5. Không có @Version

**Câu hỏi:** Có chắc mọi JPA provider hỗ trợ `em.lock(entity, OPTIMISTIC)` trên entity không có `@Version`?

**Đáp án:** Không. Hỗ trợ trên unversioned entity không được đảm bảo như versioned entity.

### Bài 6. Entity detached

~~~java
em.lock(detachedOrder, LockModeType.OPTIMISTIC);
~~~

**Câu hỏi:** Có thể xem là cách attach detached entity không?

**Đáp án:** Không. `em.lock` yêu cầu entity managed theo context hiện tại; dùng query/find phù hợp để lấy managed instance.

### Bài 7. TransactionRequiredException

**Câu hỏi:** Gọi `find(Order.class, id, OPTIMISTIC)` ngoài transaction có an toàn không?

**Đáp án:** Không mặc định. Optimistic lock request cần transaction; provider có thể ném `TransactionRequiredException`.

### Bài 8. Không thấy version tăng ngay

~~~java
em.lock(order, OPTIMISTIC_FORCE_INCREMENT);
System.out.println(order.getVersion());
~~~

**Câu hỏi:** Vì sao có thể vẫn là version cũ?

**Đáp án:** Provider có thể trì hoãn version increment đến flush/commit. Xác nhận version committed sau transaction.

### Bài 9. @Version khi root dirty

Entity root đã được sửa field status qua managed method.

**Câu hỏi:** Có bắt buộc thêm OPTIMISTIC lock để provider check version không?

**Đáp án:** Thường không; `@Version` tự hỗ trợ optimistic locking cho managed update. Explicit lock chỉ khi có ý nghĩa thêm.

### Bài 10. Bulk UPDATE

~~~jpql
UPDATE PurchaseOrder o SET o.status = :next
WHERE o.status = :old
~~~

**Câu hỏi:** Có tự tăng version mỗi Order như managed dirty checking không?

**Đáp án:** Không. Bulk DML không tự quản lý per-entity optimistic version theo cách managed update.

### Bài 11. FORCE_INCREMENT có tương đương PESSIMISTIC_WRITE không?

**Đáp án:** Không. FORCE_INCREMENT là optimistic check + required version increment, không phải cơ chế giữ DB pessimistic write lock ngay từ lúc đọc.

### Bài 12. Root version và external SQL

Service A force-increment Order khi sửa Line; batch job B sửa Line bằng SQL nhưng không đổi Order.version.

**Câu hỏi:** Có lỗ hổng gì?

**Đáp án:** Những transaction chỉ kiểm tra version root có thể bỏ sót thay đổi qua job B. Mọi đường ghi phải tuân theo concurrency contract.

### Bài 13. Transaction rollback

`em.lock(..., OPTIMISTIC_FORCE_INCREMENT)` đã thực hiện SQL increment nhưng transaction rollback.

**Câu hỏi:** Có chắc version mới được commit không?

**Đáp án:** Không. Rollback có thể hoàn tác thao tác trong transaction.

### Bài 14. HTTP ETag

Client gửi version 7, DB đã version 8.

**Đáp án:** Server cần báo stale precondition/conflict theo API contract, không âm thầm ghi đè. JPA optimistic locking vẫn cần bảo vệ race condition sau bước kiểm tra.

### Bài 15. Retry

Transaction gặp OptimisticLockException.

**Câu hỏi:** Có nên gọi lại `em.flush()` trong cùng transaction và thử tiếp?

**Đáp án:** Không. Thông thường phải rollback và tạo transaction/context mới, tải state mới, đánh giá lại invariant.

### Bài 16. FORCE_INCREMENT trên mọi GET

**Câu hỏi:** Có lợi gì nếu mỗi lần xem trang đều tăng version?

**Đáp án:** Thường không có lợi concurrency tương xứng; tạo writes, cache churn và xung đột với editor.

### Bài 17. Two-transaction test

Test dùng duy nhất một EntityManager và gọi two methods tuần tự.

**Câu hỏi:** Có đủ chứng minh optimistic conflict không?

**Đáp án:** Không. Cần hai transaction/contexts độc lập và tổ chức interleaving đúng để quan sát conflict thật.

### Bài 18. Exception lúc commit

`em.lock` thành công, `tx.commit` ném OptimisticLockException hoặc wrapper.

**Câu hỏi:** Có nên báo operation thành công vì lock đã return?

**Đáp án:** Không. Commit thất bại nghĩa transaction chưa thành công.

### Bài 19. Version con và version cha

OrderLine có `@Version` riêng, Order root không tăng khi sửa Line.

**Câu hỏi:** Root optimistic check có tự phát hiện Line change không?

**Đáp án:** Không mặc định. Phải chọn đúng version boundary, ví dụ force-increment root cho child operations.

### Bài 20. Aggregate phụ thuộc hai root

Business decision dựa trên Order và Inventory.

**Câu hỏi:** Force-increment Order có đủ bảo vệ Inventory khỏi thay đổi đồng thời không?

**Đáp án:** Không. Phải bảo vệ invariant của Inventory bằng version/lock/constraint/transaction strategy phù hợp.

## 38. Checklist trước khi dùng optimistic modes

1. Entity có `@Version` được mapping đúng không?
2. Mục tiêu là **kiểm tra version** hay **ép tăng version**?
3. Nếu entity sẽ dirty và được update bình thường, explicit lock có cần thiết không?
4. Nếu chỉ đọc để ra quyết định về record khác, có cần OPTIMISTIC không?
5. Nếu child change phải làm aggregate root revision tăng, có force increment không?
6. Mọi đường ghi child và native/bulk SQL có tuân theo version contract không?
7. Entity được truyền vào `em.lock` có managed không?
8. Có transaction cho toàn use case không?
9. Spring `@Transactional` có thực sự chạy qua interceptor không?
10. Có vô tình đặt FORCE_INCREMENT trong read-only transaction không?
11. Code có xử lý exception từ cả flush và commit không?
12. Sau conflict có rollback và tạo context mới khi retry không?
13. Retry có đánh giá lại business invariant thay vì ghi đè stale state không?
14. External side effects có idempotency/outbox/after-commit không?
15. Có dùng lock mode với DTO/scalar query sai ngữ nghĩa không?
16. Có hiểu phiên bản Java có thể chưa tăng ngay sau lock call không?
17. Có tránh dùng `@Version` như audit timestamp/history không?
18. Có phân biệt optimistic với pessimistic DB lock không?
19. Có cần bảo vệ những entity khác như Inventory/Payment không?
20. Có transaction isolation/constraint bổ sung cho cross-row invariant không?
21. Có integration test hai transaction riêng không?
22. Có test force increment sau commit qua context mới không?
23. Có test đường ghi child qua job/native SQL không?
24. Có đo conflict rate và write overhead khi force-increment không?
25. Có kiểm tra provider/database behavior trên stack thực tế không?

## 39. Tổng kết

~~~text
                  VERSIONED ENTITY
                       (@Version)
                           |
                           v
               Mục đích của transaction?
                   /                \
      Chỉ cần kiểm tra          Muốn tăng revision
      state không đổi           dù root không dirty
               |                      |
               v                      v
        OPTIMISTIC          OPTIMISTIC_FORCE_INCREMENT
               |                      |
               v                      v
        Version check          Version check + increment
               |                      |
               +-----------+----------+
                           |
                           v
                      Flush / commit
                           |
                 +---------+---------+
                 |                   |
               Khớp               Xung đột
                 |                   |
                 v                   v
              Commit           Optimistic lock
              thành công       exception / rollback
                                     |
                                     v
                              Transaction mới:
                              reload + re-evaluate
                              hoặc trả conflict
~~~

Những điểm cốt lõi:

1. **`@Version` là nền tảng của optimistic locking** cho versioned JPA entities.
2. **`OPTIMISTIC` yêu cầu kiểm tra phiên bản**, hữu ích cả khi entity chỉ được đọc để đưa ra quyết định trong transaction.
3. **`OPTIMISTIC_FORCE_INCREMENT` yêu cầu kiểm tra và tăng phiên bản**, kể cả khi scalar fields của entity không dirty.
4. **Không dùng FORCE_INCREMENT cho mọi SELECT**, vì nó biến việc đọc thành một write/revision operation và có thể tạo conflict.
5. **Managed entity được cập nhật bình thường đã có `@Version` handling**, nên explicit OPTIMISTIC không luôn cần thiết.
6. **Ép tăng root version hữu ích khi các thay đổi OrderLine phải được phản ánh ở revision Order**, nhưng chỉ đúng nếu mọi đường ghi tuân thủ cùng quy ước.
7. **`EntityManager.find`, `lock`, `refresh` và `Query.setLockMode` là các API cần hiểu**, cùng yêu cầu transaction/managed state tương ứng.
8. **Thời điểm version check/increment có thể được provider trì hoãn**; không giả định lock thành công là commit thành công hoặc version đã đổi ngay trong memory.
9. **OptimisticLockException có thể xuất hiện ở flush hoặc commit**; transaction thất bại cần rollback, không tiếp tục từ state cũ.
10. **Retry phải bắt đầu transaction mới, tải lại state và đánh giá lại invariant**; tuyệt đối không retry external side effects mù quáng.
11. **Bulk JPQL và native SQL không tự áp dụng per-entity version semantics**, cần một chiến lược concurrency riêng khi có đường ghi đó.
12. **Optimistic locking không tương đương transaction SERIALIZABLE**, và không tự bảo vệ Inventory/Payment/những rows ngoài version được theo dõi.
13. **Spring Data `@Lock` giúp khai báo mode trên repository**, nhưng không thay thế transaction boundary của service.
14. **Kiểm thử với hai EntityManager/transactions độc lập trên database thật** để xác nhận version conflict và force increment.
15. **Chọn mode theo mục đích nghiệp vụ, đo conflict rate và chi phí ghi**, thay vì áp một mode cho toàn bộ hệ thống.

Sử dụng `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT` đúng cách giúp application thiết kế ranh giới đọc–ghi rõ ràng: **OPTIMISTIC** để bảo vệ quyết định dựa trên phiên bản entity đang quan sát, và **OPTIMISTIC_FORCE_INCREMENT** để chủ động đánh dấu revision mới của một entity/aggregate root dù bản thân root không được sửa trực tiếp. Hiệu quả cuối cùng đến từ việc phối hợp lock mode với `@Version`, transaction, domain invariants, các đường ghi dữ liệu khác và một chiến lược xử lý xung đột có kiểm chứng.
