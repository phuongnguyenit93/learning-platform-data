# Đọc số bản ghi bị ảnh hưởng từ executeUpdate trong JPA

Khi dùng Jakarta Persistence (JPA), nhiều thao tác thay đổi dữ liệu không cần tải từng entity rồi gọi setter. Chẳng hạn, hệ thống có thể cần chuyển một nhóm đơn hàng từ trạng thái `PAID` sang `SHIPPED` hoặc xóa các bản ghi đã hết hạn. **JPQL bulk UPDATE/DELETE**, **CriteriaUpdate/CriteriaDelete** và một số câu **native SQL DML** cho phép thực hiện những thao tác đó trực tiếp tại database.

Sau khi thực thi, ứng dụng thường cần trả lời câu hỏi rất thực tế:

> **Có bao nhiêu bản ghi thực sự nằm trong phạm vi của lệnh thay đổi?**

JPA cung cấp phương thức:

```java
int affected = query.executeUpdate();
```

Giá trị `int` này là **update/delete count** do thao tác báo về. Nó hữu ích để xác nhận kết quả của lệnh, xử lý tình huống không khớp điều kiện, đưa ra quyết định nghiệp vụ, theo dõi công việc hàng loạt và phát hiện những cập nhật bất thường.

Ví dụ:

```java
int affected = entityManager.createQuery(
    """
    update SalesOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
    """
)
.setParameter("newStatus", OrderStatus.SHIPPED)
.setParameter("oldStatus", OrderStatus.PAID)
.executeUpdate();

System.out.println("Số đơn được tác động: " + affected);
```

Tuy nhiên, **`affected == 1` không tự chứng minh giao dịch đã commit**, **`affected == 0` không luôn có nghĩa bản ghi không tồn tại**, và **`affected == 3` không luôn tương đương ba SQL rows vật lý đã thay giá trị**, đặc biệt khi entity inheritance hoặc native SQL có semantics riêng.

Bài học thuộc chương **Truy vấn thay đổi** của module *Data Persistence Relational Access ORM JPA*. Nội dung đi từ hợp đồng của `executeUpdate()` tới cách diễn giải kết quả, quản lý transaction, optimistic locking, trạng thái persistence context, native query, kiểm thử và các tình huống xử lý ở production.

## 1. Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt `executeUpdate()` với `getResultList()`, `getSingleResult()` và `persist()/remove()`.
2. Viết JPQL `UPDATE`/`DELETE` và đọc kết quả `int`.
3. Hiểu `0`, `1` và `>1` dưới góc nhìn nghiệp vụ thay vì suy diễn quá mức.
4. Nhận biết khác biệt giữa **entity update count của JPQL** và **affected-row count của native SQL/JDBC**.
5. Thực thi DML trong transaction và hiểu tại sao count **chưa phải bằng chứng commit thành công**.
6. Tránh nhầm số entity bị tác động với số SQL statements, số dòng vật lý, số field thay đổi hoặc số side effects.
7. Thiết kế điều kiện update theo ID, tenant, trạng thái kỳ vọng và version để phát hiện xung đột.
8. Xử lý persistence context có thể bị stale sau bulk DML.
9. Kiểm thử kết quả đếm cùng các trường hợp không khớp, lặp yêu cầu và cạnh tranh đồng thời.

---

## 2. executeUpdate() là gì?

`executeUpdate()` là phương thức của `jakarta.persistence.Query`. Với một **update/delete query hợp lệ**, nó thực thi lệnh và trả về một giá trị nguyên:

```java
int executeUpdate();
```

Ví dụ:

```java
Query query = em.createQuery(
    """
    delete from SalesOrder o
    where o.status = :status
    """
);

int affected = query
    .setParameter("status", OrderStatus.CANCELLED)
    .executeUpdate();
```

Phân biệt với những phương thức khác:

| Phương thức | Mục đích | Kết quả |
|---|---|---|
| `getResultList()` | Đọc tập kết quả truy vấn SELECT | `List<?>` |
| `getSingleResult()` | Đọc đúng một kết quả SELECT | Một đối tượng/giá trị hoặc exception |
| `executeUpdate()` | Thực thi lệnh thay đổi phù hợp | `int` update/delete count |
| `EntityManager.persist(entity)` | Yêu cầu quản lý entity mới để INSERT | `void` |
| `EntityManager.remove(entity)` | Đánh dấu managed entity để DELETE | `void` |
| `EntityManager.flush()` | Đồng bộ những thay đổi pending với DB | `void` |

Điểm khác biệt quan trọng: `persist`, `remove` và dirty checking không trả trực tiếp một số lượng bản ghi từ `executeUpdate()`. Nếu cần số lượng ảnh hưởng của một **bulk query**, hãy thực hiện và đọc return value của `executeUpdate()`.

### 2.1. executeUpdate không phải hàm SELECT

Không đúng:

```java
int count = em.createQuery(
    "select count(o) from SalesOrder o"
).executeUpdate();
```

`SELECT COUNT(o)` trả **một giá trị số lượng dữ liệu đang tồn tại**, nên phải dùng `getSingleResult()`:

```java
Long count = em.createQuery(
    "select count(o) from SalesOrder o",
    Long.class
).getSingleResult();
```

Trong khi đó:

```java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :newStatus
    where o.status = :oldStatus
    """
)
.setParameter("newStatus", OrderStatus.SHIPPED)
.setParameter("oldStatus", OrderStatus.PAID)
.executeUpdate();
```

thực thi thao tác thay đổi dữ liệu rồi trả update count.

**`COUNT` và `executeUpdate()` có ý nghĩa khác nhau.** Một bên là giá trị tổng hợp do SELECT trả; bên kia là kết quả thực thi DML.

### 2.2. Giá trị trả về có kiểu int

`executeUpdate()` trả về `int`, không phải `Long`:

```java
int affected = query.executeUpdate();
```

Không nên viết:

```java
Long affected = query.executeUpdate(); // Không phù hợp kiểu Java.
```

Với tác vụ bulk rất lớn, kiểu `int` cũng có giới hạn biểu diễn. Nếu một hệ thống phải xử lý hàng tỷ bản ghi trong một lần, cần thiết kế batch/chunk hoặc cơ chế thống kê riêng thay vì suy luận rằng một `int` có thể diễn tả mọi khối lượng công việc vô hạn.

## 3. Mô hình thực hành: SalesOrder và OrderStatus

Giả sử ứng dụng thương mại điện tử có entity `SalesOrder`:

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity(name = "SalesOrder")
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "order_no", nullable = false, unique = true)
    private String orderNumber;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected SalesOrder() {
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public String getTenantId() {
        return tenantId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }
}
```

Enum:

```java
package com.example.shop.persistence;

public enum OrderStatus {
    NEW,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Ví dụ database:

```sql
CREATE TABLE sales_order (
    id BIGINT PRIMARY KEY,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    tenant_id VARCHAR(64) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    row_version BIGINT NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
```

DDL chỉ minh họa cấu trúc cột. Khi áp dụng thật, chọn generator ID, kiểu thời gian, tên schema, migration và dialect theo database.

Dữ liệu minh họa ban đầu:

| ID | tenant_id | order_status | row_version | total_amount |
|---:|---|---|---:|---:|
| 101 | shop-a | PAID | 3 | 120.00 |
| 102 | shop-a | NEW | 1 | 80.00 |
| 103 | shop-a | PAID | 2 | 200.00 |
| 201 | shop-b | PAID | 5 | 90.00 |
| 202 | shop-b | CANCELLED | 4 | 150.00 |

Các ví dụ sau sẽ nói rõ điều kiện và kết quả **nếu dữ liệu chưa bị thay đổi bởi ví dụ trước hoặc transaction khác**.

## 4. JPQL bulk UPDATE: đọc số entity được tác động

Ví dụ cập nhật đơn `PAID` của `shop-a` thành `SHIPPED`:

```java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :nextStatus,
        o.updatedAt = :now
    where o.tenantId = :tenantId
      and o.status = :currentStatus
    """
)
.setParameter("nextStatus", OrderStatus.SHIPPED)
.setParameter("now", Instant.now())
.setParameter("tenantId", "shop-a")
.setParameter("currentStatus", OrderStatus.PAID)
.executeUpdate();

System.out.println(affected);
```

Với dữ liệu mẫu ban đầu, **hai SalesOrder** thuộc `shop-a` có trạng thái `PAID`: IDs 101 và 103. Kết quả thường mong đợi:

```text
affected = 2
```

Ý nghĩa: bulk JPQL update đã báo **hai entity SalesOrder bị tác động** theo điều kiện. Không phải:

- Hai field thay đổi (thực tế câu lệnh set hai thuộc tính trên mỗi entity).
- Hai câu SQL đã gửi (provider có thể sinh một hoặc nhiều statement).
- Hai transaction đã commit.
- Hai notification/email đã gửi.
- Hai managed Java objects chắc chắn đã cập nhật trong memory.

### 4.1. Giải thích từng thành phần

| Đoạn JPQL | Vai trò |
|---|---|
| `update SalesOrder o` | Chọn entity cần cập nhật; `SalesOrder` là entity name |
| `set o.status = :nextStatus` | Gán thuộc tính persistent `status` |
| `o.updatedAt = :now` | Gán thời gian cập nhật |
| `where o.tenantId = :tenantId` | Giới hạn tenant |
| `and o.status = :currentStatus` | Chỉ cập nhật từ trạng thái kỳ vọng |
| `executeUpdate()` | Thực thi DML và trả update count |

JPQL truy vấn bằng **entity/Java properties**. Vì thế viết `o.status`, không phải tên cột SQL `o.order_status`. JPA provider tự dịch câu JPQL theo metadata `@Column`, `@Table` và SQL dialect.

### 4.2. Tại sao giới hạn tenant quan trọng?

Một câu:

```jpql
update SalesOrder o
set o.status = :nextStatus
where o.status = :currentStatus
```

có thể cập nhật cả shop-a và shop-b nếu chúng dùng chung bảng. Nếu hệ thống đa tenant, điều kiện `tenantId` hoặc cơ chế cách ly dữ liệu đáng tin là **bắt buộc theo nghiệp vụ**, không chỉ là tối ưu.

`affected = 3` thay vì `2` có thể là tín hiệu query chưa giới hạn đúng phạm vi. Tuy nhiên, **chỉ nhìn count không đủ phát hiện hoặc khắc phục lỗ hổng bảo mật**. Phải xác định quyền truy cập và dữ liệu được phép tác động trước khi chạy DML.

## 5. JPQL bulk DELETE: đọc số entity bị xóa

Ví dụ xóa những đơn đã bị hủy trước một thời điểm:

```java
int deleted = em.createQuery(
    """
    delete from SalesOrder o
    where o.status = :status
      and o.createdAt < :cutoff
      and o.tenantId = :tenantId
    """
)
.setParameter("status", OrderStatus.CANCELLED)
.setParameter("cutoff", cutoffInstant)
.setParameter("tenantId", "shop-b")
.executeUpdate();
```

Nếu đơn 202 thỏa cutoff, kết quả mong đợi là:

```text
deleted = 1
```

Câu lệnh không trả entity đã bị xóa; nó trả **số lượng entity được bulk delete báo về**.

### 5.1. Không nhầm số entity bị xóa với số row bị cascade ở DB

Giả sử database có bảng `order_line` và khóa ngoại `ON DELETE CASCADE`. Xóa một SalesOrder có 5 OrderLine có thể khiến database xóa thêm 5 dòng con.

**Không mặc định `executeUpdate()` sẽ trả 6.** Với bulk JPQL DELETE, giá trị trả về được hiểu theo số entity bị tác động bởi lệnh bulk ở cấp truy vấn JPA; các tác động thêm ở database bởi FK cascade, trigger hoặc nhiều bảng vật lý không trở thành phép cộng trực tiếp có thể dự đoán từ giá trị này.

### 5.2. Bulk DELETE không tương đương gọi remove từng entity

```java
em.remove(managedOrder);
```

và:

```java
em.createQuery(
    "delete from SalesOrder o where o.id = :id"
)
.setParameter("id", orderId)
.executeUpdate();
```

là hai đường thực thi có hệ quả khác nhau:

- `remove` thao tác trên managed entity, tham gia vòng đời entity-level, cascade và callbacks theo mapping.
- Bulk DELETE tác động qua truy vấn dữ liệu, không tự thực hiện entity-level cascade/callbacks cho từng entity theo cách lặp `remove`.
- Bulk DELETE có thể đụng FK restriction nếu quan hệ con chưa được DB cascade hoặc xóa phù hợp.
- Managed instances đã được tải có thể stale sau bulk DELETE.
- `executeUpdate()` cung cấp count, còn `remove` trả `void`.

Nếu nghiệp vụ cần `@PreRemove`, cascade JPA hoặc domain validation cho từng đơn, không thay bằng bulk DELETE chỉ để đọc được một con số.

## 6. Ý nghĩa của affected = 0

Khi một thao tác trả 0:

```java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :next
    where o.id = :id
      and o.tenantId = :tenant
      and o.status = :expected
    """
)
.setParameter("next", OrderStatus.SHIPPED)
.setParameter("id", 101L)
.setParameter("tenant", "shop-a")
.setParameter("expected", OrderStatus.PAID)
.executeUpdate();
```

`affected == 0` chỉ cho biết **lệnh không báo đối tượng nào bị tác động theo điều kiện hiện tại**. Nó **không tự chứng minh** lý do.

Có thể xảy ra:

1. Order ID 101 không tồn tại.
2. Order có tồn tại nhưng thuộc tenant khác.
3. Order đã bị chuyển khỏi trạng thái PAID.
4. Order đã bị xóa hoặc đổi state bởi transaction khác.
5. Điều kiện cutoff, version hoặc các predicate khác không thỏa.
6. Một native SQL update có semantics row count riêng của database/driver.
7. Một cơ chế authorization/soft-delete filter làm tập tác động rỗng.

**Cách diễn giải an toàn:**

```java
if (affected == 0) {
    // Không có cập nhật nào khớp điều kiện mong đợi.
    // Chưa thể kết luận "không tồn tại" nếu chưa kiểm tra thêm.
}
```

### 6.1. Với thao tác đơn giản theo ID

Nếu chỉ có:

```jpql
delete from SalesOrder o where o.id = :id
```

và ID là primary key duy nhất, `affected == 0` thường gợi ý không có entity thỏa ID ở thời điểm thao tác. Nhưng nếu ứng dụng cần phân biệt “không tồn tại”, “đã bị xóa” và “không có quyền”, phải thêm kiểm tra hoặc thiết kế response policy thích hợp.

### 6.2. Đừng tự lộ dữ liệu qua thông báo lỗi

Trong hệ thống đa tenant, nếu `affected == 0` do không khớp `tenantId`, đừng tự động query toàn hệ thống để nói cho client rằng “Order tồn tại nhưng thuộc tenant khác”. Điều đó có thể tiết lộ thông tin mà client không được phép biết.

Nhiều API cố ý dùng cùng một response cho “không tìm thấy trong phạm vi được phép” và “không có quyền”, tùy security policy.

### 6.3. Đừng đồng nhất 0 với lỗi kỹ thuật

Một tác vụ “xóa mọi đơn CANCELLED đã quá hạn” trả 0 có thể là **thành công hợp lệ**: không còn việc cần làm. Ngược lại, một thao tác “đổi trạng thái chính xác một đơn theo ID và version” trả 0 có thể biểu thị conflict hoặc không khớp precondition.

**Ngữ cảnh nghiệp vụ quyết định cách xử lý**, không phải bản thân con số 0.

## 7. Ý nghĩa của affected = 1

Một lệnh theo khóa chính và tenant:

```jpql
update SalesOrder o
set o.status = :next
where o.id = :id
  and o.tenantId = :tenant
  and o.status = :expected
```

nếu trả 1, cho biết **một entity đã được báo tác động**.

Điều đó đặc biệt hữu ích khi yêu cầu nghiệp vụ là “chuyển trạng thái cho đúng một đơn”. Nhưng vẫn có các giới hạn:

- Giao dịch có thể rollback sau `executeUpdate()`.
- Các thao tác khác trong transaction có thể thất bại ở commit.
- Count không tự chứng minh external system/email đã được gọi thành công.
- Managed entity cùng ID có thể chưa được refresh trong persistence context.
- Version `@Version` không nhất thiết được tăng tự động với bulk JPQL update.
- Một số database/driver có khác biệt khi native UPDATE gán lại cùng giá trị cũ.

**`affected == 1` là tín hiệu tốt ở thời điểm lệnh thực thi, không phải giấy chứng nhận kết quả cuối cùng của mọi bước nghiệp vụ.**

## 8. Ý nghĩa của affected > 1

Nếu thao tác dự kiến chỉ thay đổi **một entity duy nhất**, nhưng `executeUpdate()` trả 2 hoặc nhiều hơn, đó là một tín hiệu rất đáng chú ý.

Ví dụ query update theo `orderNumber`, nếu schema không ràng buộc unique đúng như kỳ vọng:

```jpql
update SalesOrder o
set o.status = :next
where o.orderNumber = :number
```

có thể tác động nhiều entity khi dữ liệu vi phạm giả định uniqueness hoặc query thiếu tenant scope.

Mẫu xử lý:

```java
if (affected != 1) {
    throw new IllegalStateException(
        "Expected exactly one order to be updated, got " +
        affected
    );
}
```

**Nhưng lưu ý quan trọng:** Exception cần làm transaction rollback theo framework/cách quản lý transaction đang dùng. Không chỉ log rồi tiếp tục commit một cập nhật đã làm thay đổi nhiều entity ngoài ý muốn.

### 8.1. Đừng thay database constraint bằng kiểm tra count

Nếu mỗi tenant chỉ được có một order với `orderNumber` nhất định, hãy đặt unique constraint phù hợp, chẳng hạn unique combination trên `(tenant_id, order_no)` khi schema yêu cầu.

Check `affected == 1` là một **lớp bảo vệ bổ sung**; không thay thế uniqueness constraint hoặc authorization.

### 8.2. Với lệnh bulk hợp lệ, >1 là bình thường

Một job chuyển 10.000 đơn đã hoàn tất thanh toán sang bước xử lý tiếp theo có thể mong đợi hàng nghìn entities bị tác động. Ở đây `affected > 1` không phải lỗi.

Vì vậy xác định contract rõ:

- “Cập nhật chính xác một đơn”: mong đợi 1.
- “Xóa mọi dữ liệu quá hạn”: mong đợi từ 0 trở lên.
- “Làm mới các record đủ điều kiện”: số lượng là metric, có thể thay đổi theo thời gian.
- “Cập nhật tối đa N đơn”: phải có cơ chế giới hạn/thao tác phù hợp; `executeUpdate` không tự áp limit vào JPQL bulk DML chuẩn.

## 9. Mẫu nghiệp vụ: cập nhật đúng một bản ghi khi trạng thái còn phù hợp

Một thiết kế phổ biến là **conditional update**, tức đưa điều kiện trạng thái kỳ vọng vào chính DML:

```java
public boolean markOrderShipped(
        EntityManager em,
        long orderId,
        String authorizedTenantId,
        Instant now
) {
    int affected = em.createQuery(
        """
        update SalesOrder o
        set o.status = :shipped,
            o.updatedAt = :now
        where o.id = :id
          and o.tenantId = :tenant
          and o.status = :paid
        """
    )
    .setParameter("shipped", OrderStatus.SHIPPED)
    .setParameter("now", now)
    .setParameter("id", orderId)
    .setParameter("tenant", authorizedTenantId)
    .setParameter("paid", OrderStatus.PAID)
    .executeUpdate();

    return switch (affected) {
        case 0 -> false;
        case 1 -> true;
        default -> throw new IllegalStateException(
            "Updated more than one order for a primary key"
        );
    };
}
```

Phương thức giả định được gọi **bên trong transaction ghi hợp lệ**.

Nếu hai request đồng thời cố chuyển Order#101 từ PAID sang SHIPPED:

1. Request A thực thi update có `WHERE status=PAID`.
2. Request B cũng thực thi cùng query.
3. Database dùng isolation/locking tương ứng để xử lý cạnh tranh cập nhật.
4. Sau khi A thành công và commit, B thường không còn thấy row thỏa điều kiện PAID để cập nhật, nên có thể nhận count 0.

Điều này có ích để tránh **blind overwrite**. Tuy nhiên chi tiết concurrency và các trường hợp rollback/deadlock/isolation phải được kiểm chứng trên database mục tiêu; count không tự giải quyết mọi race condition hoặc bảo đảm exactly-once cho external side effects.

### 9.1. Nếu cần phân biệt “đã SHIPPED” với “không tồn tại”

Sau count 0, có thể thực hiện một truy vấn trong phạm vi tenant:

```java
List<OrderStatus> statuses = em.createQuery(
    """
    select o.status
    from SalesOrder o
    where o.id = :id
      and o.tenantId = :tenant
    """,
    OrderStatus.class
)
.setParameter("id", orderId)
.setParameter("tenant", authorizedTenantId)
.getResultList();
```

Sau đó:

- Danh sách rỗng: không tìm thấy order trong phạm vi tenant.
- Trạng thái SHIPPED: có thể đây là request lặp hoặc order đã được xử lý.
- Trạng thái khác: transition không còn hợp lệ.

**Lưu ý:** Truy vấn đọc sau update là một quan sát khác trong transaction/concurrency context; trạng thái có thể tiếp tục bị transaction khác thay đổi. Nếu cần quyết định nghiệp vụ tuyệt đối chính xác, thiết kế transaction/locking hoặc versioning phù hợp, không chỉ SELECT bổ sung một cách vô điều kiện.

## 10. Idempotency: count 0 không đồng nghĩa request thất bại

Một endpoint có thể nhận lặp request “đánh dấu đơn SHIPPED” do client retry sau timeout. Câu conditional update:

```jpql
update SalesOrder o
set o.status = :shipped
where o.id = :id
  and o.status = :paid
```

trả 1 ở lần đầu và 0 ở lần tiếp theo khi trạng thái đã SHIPPED.

Nếu API muốn **idempotent semantics**, kết quả 0 có thể được diễn giải:

- Order đang SHIPPED: thao tác đã đạt trạng thái đích, có thể trả thành công theo contract.
- Order CANCELLED: không hợp lệ.
- Order không tồn tại/không thuộc tenant: xử lý theo policy.

Không được suy ra `0` luôn là “retry thành công”: nếu row không khớp vì bị hủy hoặc không thuộc phạm vi được phép, đó là tình huống khác.

### 10.1. Phân biệt "đã khớp điều kiện" và "giá trị thực sự thay đổi"

Nếu câu lệnh là:

```jpql
update SalesOrder o
set o.status = :shipped
where o.id = :id
```

và order **đã SHIPPED từ trước**, JPQL bulk update vẫn có thể báo entity đó bị tác động khi thỏa WHERE. Native database row-count semantics về matched rows/changed rows có thể khác.

Muốn count phản ánh một **state transition** cụ thể, hãy đưa trạng thái cũ vào WHERE:

```jpql
where o.id = :id and o.status = :paid
```

Lúc này không phải đơn nào đã SHIPPED cũng còn thỏa điều kiện, giúp diễn giải count tốt hơn.

## 11. Một lệnh executeUpdate chưa được coi là thành công cho tới khi commit

Một transaction có thể chạy nhiều thao tác:

```text
BEGIN TRANSACTION
   |
   +-- UPDATE SalesOrder      -> executeUpdate() trả 1
   |
   +-- INSERT AuditRecord     -> thành công hoặc thất bại
   |
   +-- UPDATE Inventory       -> có thể lỗi constraint
   |
   +-- COMMIT / ROLLBACK
```

Nếu `executeUpdate()` trả 1 nhưng bước sau gây rollback, cập nhật đơn hàng **không được lưu vĩnh viễn**.

### 11.1. Ví dụ JPA resource-local transaction

```java
EntityTransaction tx = em.getTransaction();

tx.begin();
try {
    int affected = em.createQuery(
        """
        update SalesOrder o
        set o.status = :next
        where o.id = :id
          and o.status = :expected
        """
    )
    .setParameter("next", OrderStatus.SHIPPED)
    .setParameter("id", orderId)
    .setParameter("expected", OrderStatus.PAID)
    .executeUpdate();

    if (affected != 1) {
        throw new IllegalStateException(
            "Expected exactly one order, got " + affected
        );
    }

    // Có thể còn các thao tác DB khác trong transaction này.

    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đây là mẫu **resource-local EntityManager**. Trong ứng dụng dùng JTA hoặc framework transaction manager, không nên gọi `em.getTransaction()` theo cách này nếu lifecycle transaction do container quản lý.

### 11.2. Ví dụ với Spring @Transactional

```java
@Service
public class ShippingService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void ship(long orderId, String authorizedTenantId) {
        int affected = em.createQuery(
            """
            update SalesOrder o
            set o.status = :shipped,
                o.updatedAt = :now
            where o.id = :id
              and o.tenantId = :tenant
              and o.status = :paid
            """
        )
        .setParameter("shipped", OrderStatus.SHIPPED)
        .setParameter("now", Instant.now())
        .setParameter("id", orderId)
        .setParameter("tenant", authorizedTenantId)
        .setParameter("paid", OrderStatus.PAID)
        .executeUpdate();

        if (affected == 0) {
            throw new IllegalStateException(
                "Order is not eligible for shipping"
            );
        }

        if (affected != 1) {
            throw new IllegalStateException(
                "Unexpected affected count: " + affected
            );
        }
    }
}
```

Ở ví dụ này `@Transactional`, `@Service` thuộc Spring, **không phải annotation JPA chuẩn**. Theo cấu hình Spring mặc định phổ biến, unchecked exception làm transaction rollback, nhưng quy tắc rollback có thể được tùy chỉnh. Ngoài ra, proxy boundaries và self-invocation cũng ảnh hưởng việc `@Transactional` có thật sự được áp dụng hay không.

**Count được đọc trong transaction; commit diễn ra theo transaction manager.** Nếu commit thất bại sau khi method body hoàn tất, không thể coi số count đã nhận trước đó là bảo đảm dữ liệu được lưu.

### 11.3. Gửi email sau count 1 không có nghĩa an toàn

Không nên:

```java
int changed = updateStatus();
if (changed == 1) {
    emailClient.sendShippingNotice(orderId);
}
// Transaction có thể còn rollback.
```

Gọi external system trước commit có thể khiến email đã gửi nhưng trạng thái DB rollback. Nếu cần bảo đảm event/notification gắn với thay đổi DB, cân nhắc **transactional outbox** hoặc cơ chế after-commit có xử lý retry/idempotency phù hợp. `executeUpdate()` không phải tín hiệu commit.

## 12. Vì sao executeUpdate yêu cầu transaction ghi?

Với JPA, bulk UPDATE/DELETE phải được thực thi trong transaction phù hợp. Nếu gọi khi không có transaction hợp lệ, provider có thể ném:

```java
jakarta.persistence.TransactionRequiredException
```

Ví dụ không nên kỳ vọng chạy được ngoài transaction:

```java
int changed = em.createQuery(
    "delete from SalesOrder o where o.status = :status"
)
.setParameter("status", OrderStatus.CANCELLED)
.executeUpdate();
```

Việc chạy một câu SQL `UPDATE` trên JDBC với auto-commit không tương đương bảo đảm ngữ nghĩa JPA `executeUpdate()` khi không có transaction.

### 12.1. Các tình huống khiến transaction không có hiệu lực

- Quên `@Transactional` ở tầng ghi.
- Gọi method nội bộ trong Spring bypass proxy `@Transactional`.
- Cấu hình transaction manager không điều khiển đúng EntityManager.
- Sử dụng EntityManager không join vào transaction cần thiết.
- Kết hợp sai resource-local JPA transaction và JTA.
- Transaction đã rollback-only hoặc kết thúc.
- Dùng chế độ read-only/DB replica không cho phép ghi.

Khi gặp lỗi transaction, không “sửa” bằng cách bỏ qua exception rồi giả định `affected = 0`. Lúc query ném exception, **không có một count hợp lệ được trả về**.

## 13. Các exception liên quan executeUpdate

Các vấn đề hay gặp:

| Tình huống | Hệ quả |
|---|---|
| Gọi `executeUpdate()` cho SELECT | `IllegalStateException` theo contract của query update/delete |
| Không có transaction khi DML yêu cầu | `TransactionRequiredException` |
| Câu JPQL sai entity/attribute | Query parsing/validation exception, thường là `IllegalArgumentException` hoặc `PersistenceException` tùy thời điểm/provider |
| SQL native sai table/column | Exception từ database được provider bọc/diễn giải |
| Vi phạm UNIQUE/FK/CHECK | Exception khi execute/flush/commit tùy thời điểm |
| Deadlock hoặc lock timeout | Provider/transaction exception tương ứng |
| Optimistic conflict qua entity updates | `OptimisticLockException` có thể xảy ra ở flush/commit |
| Bulk conditional update version không khớp | Thường `affected = 0` nếu lệnh chạy thành công nhưng không match |
| Transaction commit thất bại | Có thể có exception **sau** khi executeUpdate đã trả count |

Không phải mọi failure đều được thể hiện bằng count 0. **Exception và update count là hai kết quả khác nhau của việc thực thi.**

### 13.1. Không dùng broad catch rồi trả 0

Tránh:

```java
try {
    return query.executeUpdate();
} catch (Exception ignored) {
    return 0;
}
```

Đoạn này biến lỗi connection, syntax, FK, timeout hoặc deadlock thành “không có row khớp”, khiến service ra quyết định sai và che mất sự cố vận hành.

Hãy phân biệt **business outcome** (`0/1/N`) với **technical failure** (exception); log theo mức phù hợp và để transaction manager rollback khi cần.

## 14. Count của JPQL bulk UPDATE/DELETE có phải số dòng vật lý SQL không?

**Không nên đồng nhất hai khái niệm.**

Trong bulk JPQL UPDATE/DELETE, kết quả được mô tả theo **số entity instances bị tác động bởi thao tác truy vấn**, và có thể không bằng số dòng vật lý mà database cập nhật/xóa.

Ví dụ một entity inheritance strategy `JOINED`:

```text
              Payment (entity hierarchy)
                       |
        +--------------+-------------+
        |                            |
      CardPayment                BankPayment
        |                            |
 payment_base table      subtype tables
        |                     |
 payment_card            payment_bank
```

Một entity `CardPayment` có thể được biểu diễn bằng một row ở bảng base và một row ở bảng subtype. Bulk DELETE một entity qua JPA provider có thể cần thao tác trên nhiều bảng vật lý.

Vì vậy:

- **Một entity bị ảnh hưởng** không buộc phải tương ứng một SQL statement.
- **Một entity bị ảnh hưởng** không buộc phải tương ứng một physical table row.
- `executeUpdate()` của JPQL bulk DML **không phải bộ đếm mọi biến động vật lý ở database**.
- Với native SQL, semantics được thực thi và đếm ở cấp SQL/driver nên cần đánh giá khác.

### 14.1. Phân biệt bốn loại con số

| Con số | Ý nghĩa |
|---|---|
| **JPQL update count** | Số entity bị tác động theo hợp đồng bulk JPQL |
| **Native SQL update count** | Count do SQL/JDBC/provider báo cho câu DML cụ thể |
| **Số physical rows ở mọi bảng** | Tổng rows thực sự bị ghi/xóa trên các bảng vật lý liên quan |
| **Số business events** | Số giao dịch nghiệp vụ, email, payment, outbox events... |

Những con số này **có thể khác nhau**. Không thể dùng duy nhất `executeUpdate()` để suy ra toàn bộ hành vi trigger, FK cascade, cache invalidation hoặc side effects.

## 15. Native SQL executeUpdate(): cần hiểu DB/driver

Ví dụ:

```java
int affected = em.createNativeQuery(
    """
    UPDATE sales_order
    SET order_status = ?1,
        updated_at = ?2
    WHERE tenant_id = ?3
      AND order_status = ?4
    """
)
.setParameter(1, "SHIPPED")
.setParameter(2, timestampValue)
.setParameter(3, "shop-a")
.setParameter(4, "PAID")
.executeUpdate();
```

Native SQL viết **tên bảng/cột vật lý**. Count do statement báo về có thể chịu ảnh hưởng của SQL engine, JDBC driver và JPA provider, đặc biệt với những cấu trúc DML đặc biệt.

### 15.1. Matched rows và changed rows

Một số database hoặc driver có cấu hình ảnh hưởng việc báo **matched rows** hay **changed rows** khi UPDATE gán giá trị giống giá trị cũ.

Ví dụ:

```sql
UPDATE sales_order
SET order_status = 'PAID'
WHERE id = 101
  AND order_status = 'PAID';
```

Ở thời điểm thực thi:

- Điều kiện WHERE có thể khớp một row.
- Giá trị `order_status` trước/sau vẫn giống nhau.
- Native affected-row count có thể khác giữa DB/driver/configuration.

**Không thiết kế nghiệp vụ dựa trên giả định mọi native UPDATE trả 1 cho no-op assignment**, cũng không giả định mọi DB trả 0. Nếu cần diễn giải “trạng thái đã chuyển”, dùng điều kiện trạng thái kỳ vọng khác trạng thái đích hoặc cơ chế cập nhật có contract rõ.

### 15.2. Trigger và FK cascade

Nếu câu DELETE kích hoạt trigger hoặc `ON DELETE CASCADE` xóa bảng con, native `executeUpdate()` không cung cấp một quy tắc portable rằng count sẽ cộng tất cả những dòng do side effects này tạo ra.

Muốn biết toàn bộ số OrderLine bị xóa, phải thiết kế đo đếm/kiểm tra riêng nếu nghiệp vụ thực sự cần, chứ không lấy count của `DELETE sales_order` rồi cộng suy đoán.

### 15.3. Multi-table DML và vendor extensions

Một số database hỗ trợ UPDATE JOIN hoặc DELETE nhiều bảng trong một câu SQL; những cú pháp này khác nhau đáng kể. Count trả về cho multi-table DML cũng cần xác minh với database/driver cụ thể.

Ví dụ SQL kiểu MySQL có thể cho phép cú pháp `UPDATE ... JOIN`, còn PostgreSQL có cơ chế `UPDATE ... FROM` với semantics riêng. Nếu ứng dụng cần portable giữa nhiều database, hãy cô lập native DML trong adapter và có integration tests.

### 15.4. RETURNING không phải executeUpdate portable

Một số DB hỗ trợ:

```sql
UPDATE sales_order
SET order_status = 'SHIPPED'
WHERE id = 101
RETURNING id, row_version;
```

`RETURNING` cho phép câu DML đồng thời trả giá trị từ rows. Tuy nhiên cú pháp, JDBC exposure và hỗ trợ JPA provider khác nhau.

**Không mặc định `executeUpdate()` có thể dùng để nhận danh sách IDs hoặc row versions từ mọi native `RETURNING`.** Nếu cần nhận rows, dùng cơ chế database/provider/JDBC được chứng minh hỗ trợ và cô lập ở adapter; `executeUpdate()` vẫn có mục đích chính là trả update count.

### 15.5. Native INSERT và stored procedures

Một số provider cho phép gọi `executeUpdate()` với native INSERT hoặc thủ tục lưu trữ. Nhưng hợp đồng JPA cho update/delete queries và cơ chế JDBC update count không đồng nghĩa mọi native DML extension hoặc stored procedure đều trả count theo cùng quy tắc.

Với stored procedure, out parameters và nhiều result sets, nên dùng `StoredProcedureQuery` hoặc API provider/JDBC phù hợp theo database; đừng suy diễn kết quả thành số entity updated theo JPQL.

## 16. CriteriaUpdate: cùng nguyên tắc đọc count

Ngoài JPQL dạng String, JPA có Criteria API cho bulk UPDATE.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<SalesOrder> update =
    cb.createCriteriaUpdate(SalesOrder.class);

Root<SalesOrder> o = update.from(SalesOrder.class);

update.set(
    o.get("status"),
    OrderStatus.SHIPPED
);
update.set(
    o.get("updatedAt"),
    Instant.now()
);

update.where(
    cb.equal(o.get("tenantId"), "shop-a"),
    cb.equal(o.get("status"), OrderStatus.PAID)
);

int affected = em.createQuery(update).executeUpdate();
```

Trong ví dụ, `CriteriaUpdate<SalesOrder>` diễn đạt bulk update có điều kiện. `em.createQuery(update)` trả Query thực thi DML và `executeUpdate()` trả count theo ngữ nghĩa tương tự JPQL bulk update.

### 16.1. Với static metamodel

Nếu dự án có annotation processor sinh các class như `SalesOrder_`:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<SalesOrder> update =
    cb.createCriteriaUpdate(SalesOrder.class);

Root<SalesOrder> o = update.from(SalesOrder.class);

update.set(
    o.get(SalesOrder_.status),
    OrderStatus.SHIPPED
);

update.where(
    cb.equal(o.get(SalesOrder_.tenantId), authorizedTenantId),
    cb.equal(o.get(SalesOrder_.status), OrderStatus.PAID)
);

int affected = em.createQuery(update).executeUpdate();
```

`SalesOrder_` là **static metamodel class cần được sinh từ entity**, không phải class tự tồn tại trong mọi dự án. Nếu chưa cấu hình generator, dùng string-based paths hoặc cấu hình annotation processing thích hợp.

### 16.2. CriteriaUpdate không phải vòng lặp set trên managed entities

`CriteriaUpdate` tạo bulk DML. Nó **không tự đồng bộ từng entity đã managed** chỉ vì cú pháp được xây bằng Criteria API thay vì chuỗi JPQL. Những giới hạn về version, callbacks, persistence context và transaction vẫn áp dụng.

### 16.3. Giới hạn JOIN

Bulk CriteriaUpdate/Delete có quy tắc cấu trúc khác Criteria SELECT, ví dụ thường chỉ có một root update target, không dùng collection JOIN tùy ý theo cùng cách SELECT.

Nếu cần lọc theo association phức tạp, có thể sử dụng subquery/`EXISTS` phù hợp với JPQL/Criteria và provider, hoặc thiết kế query khác. Không xem CriteriaUpdate là cách để vượt mọi giới hạn cú pháp của bulk JPQL.

## 17. CriteriaDelete: đọc count tương tự

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaDelete<SalesOrder> delete =
    cb.createCriteriaDelete(SalesOrder.class);

Root<SalesOrder> o = delete.from(SalesOrder.class);

delete.where(
    cb.equal(o.get("tenantId"), "shop-b"),
    cb.equal(o.get("status"), OrderStatus.CANCELLED)
);

int deleted = em.createQuery(delete).executeUpdate();
```

`deleted` phản ánh số entity được bulk delete báo về. Nó không tự đo tất cả hàng con bị xóa bởi FK cascade hoặc logic khác.

Criteria API đặc biệt hữu ích khi điều kiện WHERE được dựng động bằng những biểu thức có kiểu, nhưng **hợp đồng kết quả của `executeUpdate()` vẫn giống nguyên lý bulk DML**.

## 18. Bulk update và @Version: lỗi dễ bị bỏ sót

Entity `SalesOrder` có:

```java
@Version
@Column(name = "row_version")
private Long version;
```

Với thao tác entity-level:

```java
SalesOrder order = em.find(SalesOrder.class, orderId);

// Giả sử domain method cho phép đổi trạng thái.
order.markShipped();
```

JPA có cơ chế optimistic locking/dirty checking dựa trên `@Version` khi entity được cập nhật trong transaction.

Nhưng bulk JPQL:

```jpql
update SalesOrder o
set o.status = :shipped
where o.id = :id
```

**không tự thực hiện optimistic version checking và tự tăng version cho từng entity theo cách entity-level update thông thường**. Đây là khác biệt quan trọng:

- Query trên không có điều kiện `o.version = :expectedVersion`.
- Query trên không gán lại `o.version`.
- `affected == 1` không chứng minh phiên bản client đọc vẫn mới.
- Managed SalesOrder đã được load có thể còn version/status cũ trong memory.

### 18.1. Manual optimistic compare-and-update

Nếu `version` là số Long và nghiệp vụ muốn cập nhật có kiểm soát:

```java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :nextStatus,
        o.updatedAt = :now,
        o.version = o.version + 1
    where o.id = :orderId
      and o.tenantId = :tenantId
      and o.status = :expectedStatus
      and o.version = :expectedVersion
    """
)
.setParameter("nextStatus", OrderStatus.SHIPPED)
.setParameter("now", Instant.now())
.setParameter("orderId", orderId)
.setParameter("tenantId", authorizedTenantId)
.setParameter("expectedStatus", OrderStatus.PAID)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();
```

Nếu count = 1, một entity đã khớp ID, tenant, trạng thái và version kỳ vọng tại thời điểm thao tác, đồng thời lệnh yêu cầu tăng version.

Nếu count = 0, có thể do:

- Không tồn tại trong phạm vi tenant.
- Trạng thái không còn PAID.
- Version không còn bằng expectedVersion.
- Row bị xóa hoặc thay đổi bởi giao dịch khác.

### 18.2. Không phải mọi 0 đều là OptimisticLockException

Query conditional bulk trên **không tự ném `OptimisticLockException` chỉ vì count 0**. Nó là DML bình thường, không khớp row theo WHERE.

Nếu business layer muốn biểu diễn xung đột phiên bản, cần tự diễn giải count và raise domain exception thích hợp:

```java
if (affected == 0) {
    throw new ConcurrentOrderUpdateException(
        "Order state or version has changed"
    );
}
```

Tên `ConcurrentOrderUpdateException` là exception nghiệp vụ do dự án định nghĩa, không phải exception JPA tích hợp.

Nếu muốn giữ cơ chế JPA entity-level optimistic locking mặc định, hãy tải entity managed rồi thay đổi trong transaction thay vì bulk update, tùy nhu cầu throughput.

### 18.3. Giới hạn của manual increment

`o.version = o.version + 1` phù hợp với **version kiểu số được ánh xạ và database/provider chấp nhận biểu thức đó**. Nó không phải mẫu dùng được cho mọi version strategy (ví dụ temporal/timestamp version hoặc cơ chế provider-specific).

Nếu entity có thêm auditing, callbacks, second-level cache hoặc domain constraints, manual version update **không tự kích hoạt tất cả**. Cần thiết kế toàn bộ contract cho bulk update, không chỉ gắn thêm một phép cộng.

### 18.4. Tránh hai cơ chế ghi vào cùng entity mà không đồng bộ

Nếu transaction có SalesOrder đã managed với version 3, rồi bulk update database thành version 4, instance Java có thể vẫn thấy version 3. Một thay đổi entity-level tiếp theo có thể dẫn tới optimistic lock failure ở flush/commit hoặc state không được mong muốn.

Sau bulk update cần rõ ranh giới persistence context và có thể `refresh`/`clear`/dùng context khác, như phần sau.

## 19. Bulk DML không đồng bộ persistence context

Một trong những điểm quan trọng nhất:

> Bulk JPQL UPDATE/DELETE **tác động lên dữ liệu ở database**, nhưng **không tự cập nhật toàn bộ managed entity instances hiện có trong persistence context**.

Ví dụ:

```java
SalesOrder order = em.find(SalesOrder.class, 101L);

OrderStatus before = order.getStatus();
// before == PAID

int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :shipped
    where o.id = :id
    """
)
.setParameter("shipped", OrderStatus.SHIPPED)
.setParameter("id", 101L)
.executeUpdate();

OrderStatus after = order.getStatus();
```

Sau bulk query, **không được mặc định** `after == SHIPPED`. Object `order` đã được load có thể vẫn giữ state PAID trong Java, dù database đã được cập nhật.

### 19.1. Tại sao lại như vậy?

Dirty checking entity-level quản lý các instance trong persistence context. Bulk query được dịch thành DML để áp dụng trực tiếp trên tập row/entity thỏa điều kiện; provider không bắt buộc phải duyệt tất cả managed objects và đồng bộ từng field theo lệnh đó.

Vì vậy:

```text
Persistence context (Java)        Database
--------------------------------  --------------------------
SalesOrder#101 status = PAID      SalesOrder#101 status = PAID
              |                              |
              | bulk JPQL UPDATE             |
              +----------------------------->|
                                             |
SalesOrder#101 status = PAID      SalesOrder#101 status = SHIPPED
   (managed state stale)                  (DB changed)
```

Count = 1 không tự khôi phục sự nhất quán của object đã load.

### 19.2. Flush trước bulk nếu có pending changes

Nếu persistence context còn những thay đổi quan trọng chưa flush:

```java
em.flush();

int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :status
    where o.id = :id
    """
)
.setParameter("status", OrderStatus.SHIPPED)
.setParameter("id", orderId)
.executeUpdate();
```

`flush` yêu cầu đồng bộ pending changes vào DB trong transaction hiện tại, giúp kiểm soát thứ tự tác động. Nhưng:

- `flush` **không phải commit**.
- Flush có thể ném exception.
- Flush trước bulk không làm entity tự refresh sau bulk.
- Trong `FlushModeType.AUTO`, provider có thể flush khi cần, nhưng explicit flush giúp thể hiện dependency thời điểm rõ khi nghiệp vụ yêu cầu.

### 19.3. Clear sau bulk khi phù hợp

```java
em.flush();

int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :status
    where o.tenantId = :tenant
    """
)
.setParameter("status", OrderStatus.SHIPPED)
.setParameter("tenant", authorizedTenantId)
.executeUpdate();

em.clear();
```

`clear()` detach **toàn bộ** managed entities của EntityManager, không chỉ SalesOrder được bulk update. Sau đó đọc lại `em.find(...)` có thể lấy state mới theo context/transaction isolation phù hợp.

**Cảnh báo:** Nếu gọi `clear()` khi còn pending changes chưa flush, các thay đổi đó có thể bị mất khỏi persistence context. Đừng dùng `clear()` như một “chữa stale cache” vô hại ở bất kỳ vị trí nào.

### 19.4. Refresh một entity cụ thể

Khi chỉ cần làm mới một entity đã có:

```java
em.refresh(order);
```

Nó có thể yêu cầu provider lấy lại dữ liệu hiện tại theo database/transaction semantics và cập nhật managed state. Nhưng `refresh` có thể ghi đè local changes; không gọi bừa nếu entity còn cập nhật chưa đồng bộ.

### 19.5. Có thể tách bulk query sang transaction riêng

Với job hàng loạt, đôi khi tốt hơn là dùng persistence context ngắn và tách rõ:

```text
Transaction/EntityManager A:
    bulk UPDATE
    read affected count
    COMMIT

Transaction/EntityManager B:
    SELECT dữ liệu cần xử lý tiếp
```

Điều này tránh giữ nhiều managed entities stale qua bulk update và giảm rủi ro first-level cache quá lớn. Tuy nhiên, bất kỳ quyết định nghiệp vụ xuyên transaction nào cũng phải tính concurrency và nhất quán eventual.

## 20. Tình huống Spring Data JPA: @Modifying và int return type

Spring Data JPA hỗ trợ khai báo update query bằng repository method:

```java
public interface SalesOrderRepository
        extends JpaRepository<SalesOrder, Long> {

    @Modifying
    @Query("""
        update SalesOrder o
        set o.status = :next,
            o.updatedAt = :now
        where o.id = :id
          and o.tenantId = :tenant
          and o.status = :expected
        """)
    int changeStatus(
        @Param("id") Long id,
        @Param("tenant") String tenant,
        @Param("expected") OrderStatus expected,
        @Param("next") OrderStatus next,
        @Param("now") Instant now
    );
}
```

Trong ví dụ:

- `@Modifying` là annotation **Spring Data JPA**, không phải Jakarta Persistence chuẩn.
- Repository method trả `int` tương ứng count của modifying query.
- Cần transaction ghi hợp lệ ở service/repository theo cấu hình.
- Count vẫn phải được diễn giải theo `WHERE` và contract nghiệp vụ.
- Bulk update vẫn không tự đồng bộ managed entities.

### 20.1. flushAutomatically và clearAutomatically

Spring Data JPA có thể hỗ trợ:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
```

Những tùy chọn này điều chỉnh việc flush/clear quanh modifying query theo hành vi Spring Data, **không phải JPA API chuẩn**.

Cần chú ý:

- Clear có thể detach các entities khác đang managed.
- Flush có thể đồng bộ nhiều pending changes khác.
- Những tùy chọn không tự xử lý optimistic version hoặc entity callbacks của bulk DML.
- Không bật `clearAutomatically` mặc định cho mọi query mà không xem transaction boundary.

### 20.2. Transaction ở service vẫn là yếu tố thiết kế quan trọng

Một service:

```java
@Transactional
public void shipOrder(long orderId) {
    int affected = repository.changeStatus(...);

    if (affected != 1) {
        throw new OrderTransitionRejectedException();
    }

    // Các thay đổi DB khác thuộc cùng transaction.
}
```

phải xác định nguyên tắc rollback, authorization và idempotency. Chỉ trả `int` từ repository không thay thế việc thiết kế transaction.

## 21. Không tự động hóa side effects theo affected count

Một lỗi thiết kế là:

```java
int affected = updateOrders();

for (int i = 0; i < affected; i++) {
    sendEmail();
}
```

Count chỉ nói **số lượng đối tượng được lệnh báo tác động**, không mang danh sách identity hoặc địa chỉ nhận email, cũng không bảo đảm commit.

Nếu cần gửi thông báo cho từng đơn, phải xác định các order IDs/recipients đủ điều kiện và quản lý idempotency. Một hướng đáng tin cậy là ghi các **outbox events** trong cùng database transaction khi dữ liệu chuyển trạng thái, sau đó một worker gửi và retry. Bulk update làm thay đổi 100 đơn không tự sinh 100 outbox events có identity đủ dùng.

### 21.1. Count dùng cho metric, không phải identity

Hợp lý:

```java
int affected = markExpiredOrders();

metrics.record("orders.expired.updated", affected);
```

Nhưng metric này cần được ghi nhận theo **thời điểm và ngữ nghĩa**: nếu transaction rollback thì con số “updated” đo trước commit có thể không phản ánh dữ liệu đã lưu. Với audit quan trọng, ghi log/số liệu sau commit hoặc phân biệt attempted và committed counts theo kiến trúc hệ thống.

### 21.2. Nếu cần biết chính xác rows nào đã thay đổi

Lựa chọn có thể gồm:

- Truy vấn trước để lấy IDs, sau đó conditional update có cơ chế concurrency thích hợp.
- Đặt sự kiện vào outbox cùng transaction khi thao tác theo từng entity.
- Dùng SQL `RETURNING` nếu database/provider hỗ trợ và adapter đã được test.
- Lưu record/batch ID của những target IDs trong một bảng công việc.
- Dùng domain workflow dạng state machine với event per entity.

**Không suy ra danh sách identities từ một số nguyên.**

## 22. Kiểm tra count trước và sau có đảm bảo correctness không?

Một cách dễ nghĩ là:

```java
Long before = em.createQuery(
    "select count(o) from SalesOrder o where o.status = :paid",
    Long.class
)
.setParameter("paid", OrderStatus.PAID)
.getSingleResult();

int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :shipped
    where o.status = :paid
    """
)
.setParameter("shipped", OrderStatus.SHIPPED)
.setParameter("paid", OrderStatus.PAID)
.executeUpdate();
```

Có phải `before == affected` không? **Không thể bảo đảm trong mọi hệ thống concurrent.**

Ví dụ:

1. Transaction A đếm 10 đơn PAID.
2. Transaction B thêm một đơn PAID rồi commit.
3. Transaction A chạy UPDATE có thể tác động 11 đơn, tùy isolation.
4. Count trước đó không còn mô tả chính xác tập mục tiêu tại lúc UPDATE.

Tương tự, transaction khác có thể chuyển trạng thái/xóa một số đơn giữa hai truy vấn.

### 22.1. Không dùng SELECT COUNT rồi UPDATE để tự bảo đảm atomicity

Nếu nghiệp vụ yêu cầu “chỉ đổi trạng thái nếu còn đúng X đơn”, việc đọc COUNT rồi cập nhật có thể cần:

- Transaction isolation phù hợp.
- Database locking/constraint.
- Conditional DML trên các row mục tiêu.
- Version/sequence hoặc aggregate invariant được bảo vệ riêng.
- Retry logic khi phát hiện conflict.

`executeUpdate()` cho biết outcome của câu lệnh, nhưng **không tự đặt isolation level đủ để mọi quan sát xung quanh là atomic**.

### 22.2. Count không thay UNIQUE constraint

Nếu cần bảo đảm chỉ một đơn có mã `orderNumber` trong tenant, database unique constraint mới là nguồn bảo vệ chắc chắn trước concurrent inserts. Kiểm tra count sau UPDATE không sửa được tình huống schema thiếu constraint.

## 23. Tình huống nhiều bảng, inheritance và trigger

Giả sử một entity được ánh xạ bằng inheritance `JOINED`:

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    private Long id;

    private String status;
}
```

```java
@Entity
public class CardPayment extends Payment {

    private String cardLastFour;
}
```

Một CardPayment có thể có bản ghi ở bảng `Payment` và `CardPayment`. Khi bulk DELETE theo entity hierarchy, provider có thể phát sinh SQL nhiều bước để xử lý nhiều bảng. `executeUpdate()` của JPQL báo số entity bị tác động, **không nhất thiết tổng số rows vật lý bị xóa trên tất cả bảng**.

Tương tự, entity có `@SecondaryTable` hoặc JOINED inheritance có thể liên quan nhiều bảng khi cập nhật một thuộc tính.

### 23.1. Cẩn thận khi so sánh với database audit log

Nếu audit trigger ghi thêm một row sau mỗi UPDATE, audit log count có thể không bằng JPQL update count. Đó không tự chứng minh query sai; hai nguồn có **đơn vị đếm khác nhau**.

### 23.2. Không suy ra số lần gọi SQL từ update count

Một bulk update trả 5 có thể:

- Được dịch thành một statement.
- Được dịch thành nhiều statements vì mapping/hierarchy.
- Kích hoạt triggers.
- Dẫn đến cascade DB.

Muốn đo số SQL statements, dùng log/metrics thích hợp ở JDBC/provider/database, không lấy `affected` làm proxy trực tiếp.

## 24. Đếm số row thay đổi và HTTP response

Khi API dùng query update theo ID, số count có thể được dịch sang kết quả nghiệp vụ.

Ví dụ một quy tắc:

| Count | Có thể xử lý | Điều kiện |
|---:|---|---|
| 1 | Trả thành công theo contract | Đã update target hợp lệ, transaction commit thành công |
| 0 | Không tìm thấy/không còn đủ điều kiện/conflict | Cần diễn giải theo WHERE và authorization |
| >1 | Lỗi invariant, rollback | Query dự kiến chỉ tác động một entity |
| Exception | Lỗi DB/transaction, rollback hoặc retry phù hợp | Không tráo thành count 0 |

Không mặc định HTTP 404 cho mọi count 0. Nếu `WHERE` có `status=PAID`, count 0 cũng có thể nghĩa order tồn tại nhưng đã SHIPPED hoặc CANCELLED; trả 409 Conflict, 200 idempotent, 404 trong phạm vi tenant, hay mã khác cần được quyết định theo **API contract**.

### 24.1. Thiết kế response không làm lộ tenant

Nếu một user không có quyền xem order ở tenant khác, không báo “order có tồn tại nhưng tenant không đúng” chỉ vì đã tìm thêm ngoài phạm vi authorized tenant. Độ chi tiết phản hồi phải tuân thủ policy.

### 24.2. Retry khi có timeout

Nếu client timeout sau khi server chạy UPDATE, client không biết:

- UPDATE chưa chạy.
- UPDATE đã chạy nhưng rollback.
- UPDATE đã commit nhưng response bị mất.

Retry với conditional update có thể trả 0 vì trạng thái đích đã đạt, nhưng cũng có thể do lý do khác. Với các thao tác quan trọng như thanh toán, cần **idempotency key**, state transition logic và cơ chế truy xuất outcome, chứ không dựa duy nhất vào `executeUpdate` của lần retry.

## 25. Một service mẫu: trả kết quả có ý nghĩa hơn int

Ở repository, `int` là dữ liệu kỹ thuật. Ở tầng service, thường nên trả kết quả nghiệp vụ có kiểu rõ.

Ví dụ enum:

```java
public enum ShipResult {
    UPDATED,
    NOT_ELIGIBLE,
    NOT_FOUND_IN_SCOPE
}
```

Một phương thức khung:

```java
@Transactional
public ShipResult ship(
        long orderId,
        String authorizedTenantId,
        Instant now
) {
    int affected = em.createQuery(
        """
        update SalesOrder o
        set o.status = :shipped,
            o.updatedAt = :now
        where o.id = :id
          and o.tenantId = :tenant
          and o.status = :paid
        """
    )
    .setParameter("shipped", OrderStatus.SHIPPED)
    .setParameter("now", now)
    .setParameter("id", orderId)
    .setParameter("tenant", authorizedTenantId)
    .setParameter("paid", OrderStatus.PAID)
    .executeUpdate();

    if (affected == 1) {
        return ShipResult.UPDATED;
    }

    if (affected > 1) {
        throw new IllegalStateException(
            "Primary key update affected multiple orders"
        );
    }

    List<OrderStatus> statuses = em.createQuery(
        """
        select o.status
        from SalesOrder o
        where o.id = :id
          and o.tenantId = :tenant
        """,
        OrderStatus.class
    )
    .setParameter("id", orderId)
    .setParameter("tenant", authorizedTenantId)
    .getResultList();

    return statuses.isEmpty()
        ? ShipResult.NOT_FOUND_IN_SCOPE
        : ShipResult.NOT_ELIGIBLE;
}
```

Đây là ví dụ **quyết định nghiệp vụ**, không phải giải pháp concurrency hoàn hảo. Query đọc sau count 0 có thể quan sát state khác trong môi trường concurrent; với chính sách yêu cầu phân biệt chính xác nguyên nhân, cần transaction/locking/version và authorization phù hợp hơn.

Ngoài ra, vì đây là Spring `@Transactional`, method return xảy ra trước hoặc trong quy trình transaction manager hoàn tất commit theo cách proxy áp dụng. Nếu commit ném lỗi, caller không nên nhận thành công cuối cùng.

## 26. Khi nào nên dùng entity-level update thay bulk executeUpdate?

Không phải lúc nào cũng nên chọn bulk update chỉ vì có count.

### 26.1. Entity-level update

```java
SalesOrder order = em.find(SalesOrder.class, orderId);

if (order == null) {
    throw new OrderNotFoundException(orderId);
}

order.markShipped(now);
// Dirty checking, @Version, callbacks/lifecycle theo mapping.
```

Ưu điểm:

- Dễ áp dụng domain methods và business invariants.
- JPA quản lý entity state.
- `@Version` optimistic locking được áp theo cơ chế entity-level.
- Entity listeners/callbacks có thể chạy.
- Cascade và association semantics đi theo mapping.

Nhược điểm:

- Phải load entity.
- Không tối ưu nếu cập nhật hàng chục nghìn records.
- Không trả count trực tiếp từ setter/flush theo `executeUpdate()`.

### 26.2. Bulk executeUpdate

```java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :next
    where o.status = :old
    """
)
.setParameter("next", OrderStatus.CANCELLED)
.setParameter("old", OrderStatus.NEW)
.executeUpdate();
```

Ưu điểm:

- Diễn đạt update tập hợp tại database.
- Không cần load từng entity.
- Có count để đo phạm vi tác động.
- Hữu ích cho batch jobs, cleanup, trạng thái đơn giản.

Nhược điểm:

- Không tự đồng bộ persistence context.
- Không tự chạy entity-level callbacks/cascade/versioning.
- Cần quản lý transaction và integrity thủ công hơn.
- Query thay đổi nhiều entity ngoài ý muốn có thể khó undo nếu đã commit.
- Bản thân count không đưa ra danh sách affected IDs.

### 26.3. Bảng lựa chọn

| Yêu cầu | Entity-level | Bulk DML |
|---|---|---|
| Thay đổi một entity có nhiều domain rules | Thường phù hợp hơn | Cần cân nhắc |
| Cập nhật 100.000 rows đơn giản | Có thể tốn chi phí load/batching | Thường phù hợp |
| Muốn JPA tự optimistic-lock theo `@Version` | Tự nhiên hơn | Cần manual version condition nếu muốn |
| Cần `@PreUpdate`/`@PreRemove` per entity | Có theo lifecycle | Không theo cách entity-level |
| Cần trả số bản ghi tác động | Phải đo riêng | `executeUpdate()` trả count |
| Đã có nhiều entity managed trong context | Dễ nhất quán hơn | Nguy cơ stale instances |
| Cần bảo đảm FK/cascade entity-level | Theo mapping | Cần thiết kế riêng |
| Chỉ muốn thay đổi state theo một predicate đơn giản | Có thể dùng | Rất phù hợp |

Lựa chọn nên xuất phát từ **tính đúng nghiệp vụ và tính nhất quán**, sau đó mới đo throughput.

## 27. Kiểm thử executeUpdate: setup dữ liệu rõ, assert count và state

Một integration test nên xác nhận **hai thứ**:

1. Count trả về đúng với điều kiện.
2. State database sau thao tác đúng với ý nghĩa của query.

Một test chỉ assert count có thể bỏ sót trường hợp query thay nhầm field hoặc thiếu filter tenant.

### 27.1. Fixture mẫu

Chuẩn bị các rows:

```text
id=101, tenant=shop-a, status=PAID, version=3
id=102, tenant=shop-a, status=NEW, version=1
id=103, tenant=shop-a, status=PAID, version=2
id=201, tenant=shop-b, status=PAID, version=5
id=202, tenant=shop-b, status=CANCELLED, version=4
```

Thao tác:

```jpql
update SalesOrder o
set o.status = :shipped
where o.tenantId = :tenant
  and o.status = :paid
```

với tenant=shop-a, expected affected=2.

### 27.2. Test 0 rows

Dùng tenant không có đơn PAID, hoặc ID không tồn tại. Expected affected=0. Không mong đợi `NoResultException` từ bulk update chạy thành công nhưng không match.

### 27.3. Test một row

Dùng primary key 101 với `where o.id=:id and o.tenantId=:tenant`. Expected affected=1 khi dữ liệu đang thỏa điều kiện.

### 27.4. Test nhiều rows

Dùng tenant=shop-a và status=PAID như fixture, expected affected=2. Assert rằng row 201 của shop-b không bị thay đổi.

### 27.5. Test retry

Thực thi conditional update PAID→SHIPPED hai lần trong những transaction có thứ tự rõ ràng:

```text
Lần 1: affected = 1
Lần 2: affected = 0 (trạng thái không còn PAID)
```

Đây là kỳ vọng với dữ liệu chỉ có một target và không có transaction khác xen vào, không phải quy tắc cho mọi native UPDATE no-op.

### 27.6. Test version mismatch

Tạo order version 3, gọi query `where version=:expected` với expected=2: affected=0. Gọi lại với expected=3 khi order vẫn hợp lệ: affected=1 và version được tăng theo câu bulk update manual.

Kiểm tra state bằng **EntityManager/context mới hoặc refresh thích hợp** để tránh kết quả stale do first-level cache.

### 27.7. Test rollback

Trong một transaction:

1. Execute UPDATE, nhận affected=1.
2. Cố ý gây một exception khiến rollback.
3. Mở transaction/EntityManager mới và kiểm tra database giữ state cũ.

Bài test nhấn mạnh rằng count != committed outcome.

### 27.8. Test stale managed state

1. Load SalesOrder#101 vào EntityManager.
2. Chạy bulk update status thành SHIPPED.
3. Quan sát state trên object đã load.
4. Clear/refresh/context mới đúng cách.
5. Đọc lại database và xác nhận state mới.

Không viết test với giả định object Java nhất định được cập nhật tự động.

### 27.9. Test FK cascade và inheritance

Nếu schema có foreign keys/cascades hoặc entity inheritance, so sánh:

- JPQL executeUpdate count.
- Số row thực tế ở bảng target.
- Số row bị ảnh hưởng ở bảng con.

Những giá trị có thể khác do **đơn vị đếm và mapping**, chứ không nhất thiết là bug.

### 27.10. Test trên DB phù hợp production

H2 hoặc database in-memory có thể khác PostgreSQL/MySQL/Oracle về native affected-row count, trigger, FK cascade, JDBC driver và concurrency. Với nghiệp vụ dựa vào count=0/1, cần integration test trên database/dialect mục tiêu.

Các ví dụ test trong bài là hướng dẫn cho người học; tác vụ soạn tài liệu này không thực thi test/Content QA.

## 28. Các lỗi thường gặp khi đọc executeUpdate()

### 28.1. Gọi getResultList trên UPDATE

```java
List<?> rows = em.createQuery(
    "update SalesOrder o set o.status = :status"
).getResultList();
```

Sai API. UPDATE/DELETE dùng `executeUpdate()`.

### 28.2. Gọi executeUpdate trên SELECT

```java
int count = em.createQuery(
    "select count(o) from SalesOrder o"
).executeUpdate();
```

Không đúng; SELECT dùng `getSingleResult()`.

### 28.3. Quên transaction

Query có thể ném `TransactionRequiredException`. Đừng coi là count 0.

### 28.4. Gán kết quả vào Long

```java
Long affected = query.executeUpdate();
```

Không đúng kiểu; dùng `int` hoặc `Integer`.

### 28.5. Count = 0 nên kết luận “không tồn tại”

Thiếu các khả năng trạng thái/version/tenant/cutoff không khớp. Diễn giải theo toàn bộ WHERE.

### 28.6. Count > 0 nên coi transaction đã commit

Sai. Commit có thể thất bại hoặc transaction bị rollback.

### 28.7. Count > 0 nên phát email ngay

Sai nếu external side effect diễn ra trước commit hoặc không có idempotency. Dùng outbox/after-commit theo nhu cầu.

### 28.8. Đếm field thay đổi thay vì entity

Một UPDATE set 3 fields cho 2 entities không có nghĩa count = 6. Count không đo số property assignments.

### 28.9. Dùng count làm số SQL statements

Entity inheritance/secondary tables và provider SQL generation có thể cần nhiều statements. Không suy ra trực tiếp từ count.

### 28.10. Cộng DB cascades vào count

Một DELETE parent có thể xóa hàng con qua FK cascade. Đừng suy ra count = parent + child rows.

### 28.11. Native UPDATE no-op luôn trả 1

Không portable giữa database/driver configurations. Phân biệt matched rows và changed rows.

### 28.12. Không có WHERE trong bulk UPDATE

```jpql
update SalesOrder o
set o.status = :status
```

Tác động **mọi SalesOrder** phù hợp phạm vi entity; có thể cực kỳ nguy hiểm trong hệ thống đa tenant. Đặt WHERE theo nghiệp vụ hoặc có quy trình bảo vệ riêng.

### 28.13. Dùng parameter để thay tên field/table

`:field` trong UPDATE không tự thay tên thuộc tính; parameters dành cho **giá trị**, không cho cấu trúc JPQL/SQL.

### 28.14. Bulk update tự tăng @Version

Sai theo entity-level versioning semantics. Phải thiết kế manual version check/increment hoặc dùng entity-level update.

### 28.15. Bulk update tự chạy @PreUpdate

Không phải như thao tác thay đổi managed entity từng record. Nếu cần callback/domain logic per entity, chọn chiến lược thích hợp.

### 28.16. Native DELETE tự gọi @PreRemove/cascade JPA

Sai. DB FK cascade có thể có, nhưng không đồng nghĩa entity lifecycle callbacks.

### 28.17. Sau bulk DML, managed entity tự đổi state

Không được bảo đảm. Persistence context có thể stale.

### 28.18. Gọi clear mà không flush

`clear()` có thể detach và làm mất pending changes chưa flush. Phải xác định thứ tự và transaction.

### 28.19. Retry UPDATE mà không kiểm tra state

Count 0 của retry có thể mang nhiều ý nghĩa; cần idempotency contract và state verification.

### 28.20. Chỉ assert count, không assert dữ liệu

Query có thể trả đúng số lượng nhưng sửa sai entity/tenant/field. Test cả dữ liệu và invariant.

### 28.21. Catch exception rồi trả 0

Che giấu lỗi SQL/DB/constraint/connection; làm service xử lý sai business outcome.

### 28.22. Dùng COUNT trước UPDATE làm “bằng chứng” số rows sẽ thay

Concurrent transactions có thể thay tập dữ liệu giữa hai câu lệnh.

### 28.23. Dùng COUNT để bảo đảm quota

`COUNT` chỉ là quan sát dữ liệu theo isolation tại thời điểm đọc, không tự khóa/đảm bảo invariant khi có concurrent inserts.

### 28.24. Xem count như danh sách IDs

`executeUpdate` không trả identities. Muốn biết targets phải thiết kế thêm.

### 28.25. Giả định provider nào cũng trả native count y hệt

Native DML có thể bị ảnh hưởng bởi DB/driver/provider, đặc biệt no-op UPDATE, triggers, RETURNING và multi-table statements.

## 29. Bảng quyết định nhanh theo yêu cầu nghiệp vụ

| Yêu cầu | Mẫu truy vấn | Diễn giải count |
|---|---|---|
| Đánh dấu đúng một đơn đã thanh toán thành đã giao | UPDATE theo ID + tenant + status kỳ vọng | 1 thành công ở cấp DML; 0 không match; >1 lỗi invariant |
| Hủy các đơn NEW quá hạn | UPDATE theo status + cutoff + tenant | 0 trở lên đều có thể hợp lệ |
| Xóa tất cả record cũ | DELETE theo cutoff | Count là số target entity bị bulk delete, không gồm mọi DB cascade |
| Đổi giá theo ID + version | UPDATE theo ID + version; tăng version thủ công nếu bulk | 0 có thể là stale version hoặc không tồn tại |
| Xóa hàng có khóa chính | DELETE theo ID + tenant | 0 có thể không tìm thấy trong phạm vi, 1 thường hợp lệ |
| Cập nhật hàng loạt theo JPQL entity inheritance | UPDATE/DELETE entity | Count theo entity, có thể khác physical rows |
| Native UPDATE với cùng giá trị cũ | SQL DML trực tiếp | Xác minh matched/changed row-count semantics |
| API cần biết IDs đã thay đổi | Query/RETURNING/outbox/claim table tùy DB | Count riêng không đủ |
| Muốn đảm bảo kết quả đã commit | Transaction manager và commit handling | Count trước commit không đủ |
| Muốn callback hoặc JPA cascade cho từng entity | Managed entity operation | Không thay bằng bulk DML chỉ vì muốn count |

## 30. Bài tập thực hành và đáp án gợi ý

### Bài 1: Đọc count của JPQL UPDATE

**Yêu cầu:** Chuyển mọi SalesOrder của shop-a từ `PAID` sang `SHIPPED` và ghi nhận số entity được cập nhật.

**Gợi ý:**

```java
int affected = em.createQuery(
    """
    update SalesOrder o
    set o.status = :next
    where o.tenantId = :tenant
      and o.status = :current
    """
)
.setParameter("next", OrderStatus.SHIPPED)
.setParameter("tenant", "shop-a")
.setParameter("current", OrderStatus.PAID)
.executeUpdate();
```

Với fixture ban đầu, expected affected=2.

### Bài 2: Count 0 có nghĩa gì?

Một query UPDATE theo ID+status trả 0.

**Đáp án gợi ý:** Không có entity thỏa toàn bộ WHERE tại thời điểm DML. Chưa thể kết luận ID không tồn tại; status hoặc tenant có thể khác.

### Bài 3: executeUpdate trả kiểu nào?

**Đáp án:** `int`, không phải `Long`.

### Bài 4: Dùng SELECT COUNT với executeUpdate?

```java
em.createQuery(
    "select count(o) from SalesOrder o"
).executeUpdate();
```

**Đáp án:** Sai API; dùng `getSingleResult()` với kiểu `Long`.

### Bài 5: Bulk DELETE không có row

`DELETE` những đơn CANCELLED trước năm 2020, nhưng dữ liệu không có order nào thỏa.

**Đáp án:** `executeUpdate()` trả 0 nếu lệnh chạy thành công; không phải mặc định ném `NoResultException`.

### Bài 6: Lệnh theo ID trả 2

Query dự kiến chỉ update một đơn nhưng `affected = 2`.

**Đáp án:** Coi đây là vi phạm invariant/query scope. Cần rollback transaction và kiểm tra WHERE, unique constraint, tenant, dữ liệu; không chỉ log rồi commit.

### Bài 7: Câu UPDATE set ba thuộc tính trên năm đơn

**Câu hỏi:** Count trả 15 hay 5?

**Gợi ý:** Thông thường `5` entity instances bị bulk update báo tác động, không đếm số field assignments.

### Bài 8: FK ON DELETE CASCADE

Xóa một SalesOrder có bốn OrderLine bị database cascade.

**Câu hỏi:** JPQL DELETE count có phải 5 không?

**Gợi ý:** Không tự động. Count của bulk JPQL phản ánh entity target; physical child deletes do DB cascade không được cộng theo một quy tắc portable.

### Bài 9: Không có transaction

**Câu hỏi:** Điều gì có thể xảy ra khi gọi bulk JPQL `executeUpdate()` ngoài transaction?

**Gợi ý:** `TransactionRequiredException`. Đây không phải outcome 0.

### Bài 10: Rollback sau count 1

UPDATE trả 1 nhưng bước SQL sau đó vi phạm FK, transaction rollback.

**Câu hỏi:** Order đã được cập nhật vĩnh viễn chưa?

**Gợi ý:** Chưa. Count xảy ra trước commit và không bảo đảm commit thành công.

### Bài 11: Entity managed stale

Load Order#101 status PAID, bulk update sang SHIPPED.

**Câu hỏi:** Getter trên object cũ chắc chắn trả SHIPPED không?

**Gợi ý:** Không. Cần refresh/clear/context mới thích hợp.

### Bài 12: @Version tự cập nhật?

Bulk JPQL:

```jpql
update SalesOrder o
set o.status = :next
where o.id = :id
```

**Câu hỏi:** Có tự kiểm tra version cũ và tăng `@Version` không?

**Gợi ý:** Không theo cơ chế entity-level mặc định; cần thiết kế manual version logic hoặc dùng managed entity update.

### Bài 13: Conditional version update

**Yêu cầu:** Viết query update status với ID, tenant, version kỳ vọng.

**Gợi ý:**

```jpql
update SalesOrder o
set o.status = :next,
    o.version = o.version + 1
where o.id = :id
  and o.tenantId = :tenant
  and o.version = :expectedVersion
```

Chỉ áp dụng cho version numeric phù hợp, cần transaction và test.

### Bài 14: Version mismatch count 0

**Câu hỏi:** Query ở bài 13 trả 0 có tự ném `OptimisticLockException` không?

**Đáp án:** Không nhất thiết. Đó là DML không match; service tự diễn giải và ném domain conflict nếu contract yêu cầu.

### Bài 15: Native no-op UPDATE

SQL cập nhật `status='PAID'` khi row đã PAID.

**Câu hỏi:** Mọi database/driver chắc chắn trả count=1?

**Gợi ý:** Không. Native count có thể phản ánh matched hoặc changed rows theo DB/driver configuration.

### Bài 16: CriteriaUpdate

**Yêu cầu:** Dùng Criteria API cập nhật status và đọc count.

**Gợi ý:** `cb.createCriteriaUpdate(SalesOrder.class)`, `update.set(...)`, `update.where(...)` và `em.createQuery(update).executeUpdate()`.

### Bài 17: CriteriaDelete

**Yêu cầu:** Xóa đơn CANCELLED theo tenant bằng CriteriaDelete.

**Gợi ý:** `cb.createCriteriaDelete(SalesOrder.class)` rồi `em.createQuery(delete).executeUpdate()`.

### Bài 18: Spring Data JPA

Một repository method có `@Query("update ...")`.

**Câu hỏi:** Cần annotation nào để Spring Data hiểu đây là modifying query?

**Đáp án gợi ý:** `@Modifying`, cùng transaction phù hợp; method có thể trả `int` count.

### Bài 19: @Modifying(clearAutomatically=true)

**Câu hỏi:** Tại sao có thể gây rủi ro?

**Gợi ý:** Nó clear persistence context; nếu còn pending changes chưa flush, chúng có thể bị mất. Đồng thời entity references bị detach.

### Bài 20: Idempotent retry

Lần đầu conditional PAID→SHIPPED affected=1, lần sau affected=0.

**Câu hỏi:** Lần sau nên HTTP 500 không?

**Gợi ý:** Không mặc định. Kiểm tra trạng thái hiện tại và idempotency policy. Count 0 có thể do đã SHIPPED hoặc điều kiện không hợp lệ khác.

### Bài 21: Không lộ tenant

Một update theo ID+authorized tenant trả 0.

**Câu hỏi:** Có nên query toàn bộ database để nói “ID này thuộc tenant khác” không?

**Gợi ý:** Không nếu authorization policy cấm tiết lộ sự tồn tại. Dùng response trong phạm vi được phép.

### Bài 22: Count không có identity

Bulk update 100 SalesOrder, affected=100.

**Câu hỏi:** Có thể biết 100 order IDs chỉ từ count không?

**Đáp án:** Không. Cần query/RETURNING/outbox/claim table phù hợp.

### Bài 23: Tính đúng dưới concurrency

SELECT COUNT(PAID)=10, sau đó UPDATE status PAID nhận affected=11.

**Câu hỏi:** Có nhất thiết provider đếm sai không?

**Gợi ý:** Không. Transaction khác có thể thay dữ liệu giữa hai câu query; isolation/snapshot khác nhau.

### Bài 24: Inheritance

Một Payment entity được lưu trên hai bảng do JOINED inheritance, DELETE một Payment.

**Câu hỏi:** Có thể có nhiều physical SQL rows bị xóa nhưng JPQL count=1 không?

**Đáp án:** Có. Count theo target entity không nhất thiết trùng tổng physical rows.

### Bài 25: Test kết quả

**Yêu cầu:** Thiết kế test cho `UPDATE SalesOrder WHERE tenant='shop-a' AND status='PAID'`.

**Gợi ý:** Fixture hai đơn PAID shop-a, một NEW shop-a và một PAID shop-b; assert count=2, chỉ đúng hai rows đổi status, transaction commit rồi đọc lại bằng context mới.

### Bài 26: Query ném exception

Một native UPDATE vi phạm FK, không trả count.

**Câu hỏi:** Có nên catch và trả affected=0?

**Đáp án:** Không. Đó là technical failure, cần rollback/handling thích hợp.

### Bài 27: Metric

Một batch UPDATE affected=400 sau đó rollback.

**Câu hỏi:** Metric “400 committed updates” có chính xác không?

**Gợi ý:** Không. Phân biệt attempted count với committed outcome hoặc ghi metric sau commit.

### Bài 28: External notification

Sau bulk UPDATE affected=20, service gửi 20 email ngay trong transaction.

**Câu hỏi:** Những rủi ro nào?

**Gợi ý:** Không biết identity/recipient chỉ từ count; transaction có thể rollback; email không rollback; cần outbox/after-commit/idempotency.

## 31. Quy trình thực tế khi dùng executeUpdate

Một quy trình ngắn cho team phát triển:

```text
           Xác định nghiệp vụ cần đổi dữ liệu
                          |
                          v
          Chọn entity-level hay bulk DML?
                  /               \
          Entity-level            Bulk DML
              |                       |
              v                       v
       Load managed entity      Viết WHERE chính xác
       + domain validation      ID/tenant/status/version
              |                       |
              |                       v
              |                 Có transaction ghi?
              |                       |
              |                       v
              |                 executeUpdate()
              |                       |
              |                +------+------+ 
              |                |      |      |
              |                v      v      v
              |               0      1      >1
              |                |      |      |
              |            No match  OK    Kiểm tra
              |            /conflict       invariant
              |                |      |      |
              |                +------+------+
              |                       |
              |                       v
              |             Flush/clear/refresh?
              |             Version/callback/cache?
              |                       |
              +-----------------------+
                          |
                          v
             Commit / rollback theo outcome
                          |
                          v
               Sau commit: events/metrics
                          |
                          v
              Test state và concurrency
```

Trước khi sử dụng return count để ra quyết định, hãy tự hỏi:

1. **Lệnh đang đếm entity hay SQL rows?** Có inheritance, trigger hoặc cascade không?
2. **WHERE đủ chặt chưa?** Có ID, tenant, trạng thái cũ và version khi cần không?
3. **Khi count 0, những nguyên nhân nào có thể xảy ra?**
4. **Khi count >1, có phải lỗi invariant không?**
5. **Có transaction ghi và rollback rules rõ ràng không?**
6. **Có entity đang managed có thể bị stale không?**
7. **Có yêu cầu @Version, callbacks hoặc JPA cascade không?**
8. **Có side effects cần chỉ xảy ra sau commit không?**
9. **Test có kiểm tra state DB, không chỉ count không?**
10. **Native SQL có semantics row count riêng theo driver/database không?**

## 32. Tóm tắt nhanh

| Tình huống | Giá trị/cách xử lý |
|---|---|
| `Query.executeUpdate()` với JPQL UPDATE/DELETE hợp lệ | Trả `int` update/delete count |
| Bulk SELECT `COUNT` | Dùng `getSingleResult()`, kết quả JPQL COUNT thường là `Long` |
| UPDATE match 0 entity | `affected == 0`, không tự nghĩa “ID không tồn tại” |
| UPDATE match 1 entity | `affected == 1`, chưa chắc transaction đã commit |
| UPDATE match nhiều entity | `affected > 1`, bình thường với bulk job; lỗi nếu dự kiến đúng một |
| DELETE parent có FK cascade | Count không mặc định cộng mọi child row |
| Entity inheritance JOINED | Entity count có thể khác số physical SQL rows |
| Native UPDATE no-op | Matched/changed rows semantics phụ thuộc DB/driver |
| Không có transaction cho bulk DML | Có thể `TransactionRequiredException` |
| Query SELECT gọi `executeUpdate()` | Sai mục đích, có thể `IllegalStateException` |
| Bulk update entity có `@Version` | Không tự entity-level optimistic version handling |
| Count 0 với `where version=:expected` | Có thể conflict/stale/not found; phải tự diễn giải |
| Entity đã managed trước bulk DML | Có thể stale, cần refresh/clear/context boundary |
| Dùng `em.clear()` | Detach tất cả managed entities, cẩn thận pending changes |
| JPQL vs CriteriaUpdate/Delete | Cùng ý nghĩa count của bulk DML |
| Spring Data JPA `@Modifying` | Có thể trả `int`, cần transaction |
| Count 1 rồi external call | Không có bảo đảm commit; dùng outbox/after-commit khi cần |
| Cần biết affected IDs | Count không đủ; cần thiết kế bổ sung |
| Test | Assert count **và** state DB, rollback, concurrency |

## 33. Ghi nhớ cốt lõi

1. **`executeUpdate()` trả một số `int`**, là update/delete count của thao tác DML; không trả danh sách entity.
2. **JPQL bulk UPDATE/DELETE tác động theo entity mapping**, do đó count không nhất thiết là tổng số rows vật lý bị ghi ở mọi bảng.
3. **Native SQL affected count phải được hiểu theo database/driver/provider**, nhất là no-op UPDATE, multi-table DML và triggers.
4. **`0` nghĩa lệnh không báo đối tượng nào được tác động**, không đủ để phân biệt không tồn tại, không có quyền, trạng thái khác hoặc version mismatch.
5. **`1` là một kết quả DML, không phải bằng chứng commit thành công**; transaction còn có thể rollback.
6. **`>1` cần diễn giải theo contract**: hợp lệ với bulk job, nhưng là lỗi nếu thao tác chỉ được thay một entity.
7. **Điều kiện `WHERE` là phần quan trọng nhất để hiểu count.** Cân nhắc ID, authorized tenant, expected status, cutoff và expected version.
8. **Bulk JPQL không tự đồng bộ @Version, entity callbacks và managed instances** theo cách entity-level updates.
9. **Persistence context có thể stale sau bulk DML.** Dùng flush/clear/refresh đúng nơi và hiểu tác dụng phụ của chúng.
10. **Không lấy count làm số emails, số outbox events, số SQL statements hoặc số affected IDs**.
11. **Không biến lỗi DB thành count 0**; exception phải được xử lý như technical failure.
12. **Dùng count để xây logic idempotency và conflict handling một cách có điều kiện**, không suy luận quá mức từ một số nguyên.
13. **Đo kết quả sau commit và kiểm thử trạng thái dữ liệu** nếu số affected count được dùng cho audit/metrics nghiệp vụ quan trọng.

**Kết luận:** Đọc số bản ghi bị ảnh hưởng từ `executeUpdate()` là kỹ năng nền tảng khi sử dụng JPQL/Criteria bulk UPDATE/DELETE và native DML trong JPA. Một phép gán `int affected = query.executeUpdate()` rất ngắn, nhưng **ý nghĩa của số này phụ thuộc query, WHERE, transaction, mapping và database**. Sử dụng đúng count giúp ứng dụng phát hiện tình trạng không khớp điều kiện, triển khai state transition an toàn hơn và giám sát batch jobs; đồng thời tránh ba sai lầm lớn: **coi count là bằng chứng commit, coi count là số physical rows trên mọi bảng và coi bulk DML là thay đổi entity-level có đầy đủ callbacks/versioning**.
