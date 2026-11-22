# Khóa trên thực thể, quan hệ và phạm vi bảo vệ thực tế

## 1. Một lệnh khóa đang bảo vệ điều gì?

Trong Hibernate ORM, gọi khóa trên một entity thường tạo cảm giác như toàn bộ object graph của entity đó đã được bảo vệ. Nhưng database không nhìn thấy một đồ thị Java. Database nhìn thấy **các hàng, khóa, chỉ mục, quan hệ khóa ngoại, predicate và transaction**.

Giả sử một đơn hàng có các dòng hàng:

```text
Order #100
  ├── OrderLine #201 (SKU=JAVA, quantity=2)
  ├── OrderLine #202 (SKU=SQL,  quantity=1)
  └── OrderLine #203 (SKU=JPA,  quantity=3)
```

Nếu ứng dụng khóa `Order #100`, điều đó có tự động khóa cả ba hàng `order_lines` không? Một request khác có thể thêm `OrderLine #204` trong lúc khóa đang giữ không? Nếu một transaction đổi `OrderLine #201.quantity`, version của Order có tăng không?

Không thể trả lời các câu hỏi ấy chỉ bằng cách nhìn vào:

```java
em.find(Order.class, 100L, LockModeType.PESSIMISTIC_WRITE);
```

Phải biết **mapping quan hệ**, phía sở hữu khóa ngoại, loại khóa, phạm vi khóa, database dialect và quy ước transaction của mọi đường ghi.

Bài học quan trọng nhất:

> Khóa một entity không đồng nghĩa khóa đệ quy mọi entity và mọi hàng có thể truy cập từ entity đó.

Khóa trên một row thường bảo vệ row được database khóa. Muốn bảo vệ một invariant liên quan nhiều row, ứng dụng phải chọn thêm versioning, khóa các row liên quan, constraint, isolation level hoặc một protocol khóa thống nhất.

## 2. Tách ba khái niệm: entity, quan hệ Java và row database

Một quan hệ trong Java:

```java
order.getLines()
```

có thể được ánh xạ thành nhiều cấu trúc khác nhau:

| Mapping | Dữ liệu quan hệ được lưu ở đâu? | Hàng nào đại diện cho association? |
|---|---|---|
| `@ManyToOne` | FK trong bảng entity sở hữu | Hàng của entity sở hữu FK |
| `@OneToOne` | FK ở một trong hai bảng | Hàng của phía sở hữu FK |
| `@OneToMany(mappedBy=...)` | FK trong bảng entity con | Hàng của từng entity con |
| `@ManyToMany` | Bảng join | Hàng trong join table |
| `@ElementCollection` | Collection table | Hàng trong collection table |
| `@Embedded` | Các cột nằm trong bảng owner | Chính hàng của owner |

Hibernate có thể tạo proxy và persistent collection để biểu diễn các quan hệ ấy trong memory. Nhưng proxy không phải một khóa database. Việc khóa một Java object reference không tự làm các hàng khác bị khóa; Hibernate phải phát ra câu SQL phù hợp và database phải thực thi lock.

### 2.1. Ví dụ Order và OrderLine

DDL:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id),
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_order_lines_order_id
    ON order_lines(order_id);
```

Ở đây:

- Hàng `orders(id=100)` lưu trạng thái và version của Order.
- Mỗi hàng `order_lines(id=201...)` lưu một OrderLine và FK `order_id=100`.
- Một association Order–OrderLine không được lưu bằng join table; FK nằm trong bảng con.
- Khóa hàng `orders.id=100` không tự động có nghĩa các hàng `order_lines` đã bị khóa.

Nếu dùng `@ManyToMany`, quan hệ có thể nằm ở join table. Nếu dùng `@ElementCollection`, nó nằm ở collection table. Phạm vi bảo vệ sẽ khác nhau theo cấu trúc đó.

## 3. Hai họ khóa chính trong JPA/Hibernate

JPA định nghĩa hai họ khóa thường dùng:

- **Optimistic locking:** cho nhiều transaction cùng đọc; khi ghi, kiểm tra xem dữ liệu có thay đổi kể từ lúc đọc không. Thường dùng `@Version`.
- **Pessimistic locking:** yêu cầu database giữ khóa trong transaction để ngăn các thao tác xung đột theo semantics của database.

| Tiêu chí | Optimistic | Pessimistic |
|---|---|---|
| Cách bảo vệ | So sánh version/state khi flush hoặc commit | Khóa database được giữ trong transaction |
| Hành vi khi cạnh tranh | Một transaction có thể thất bại lúc ghi | Transaction khác có thể phải chờ hoặc timeout |
| Chi phí khi ít xung đột | Thường thấp | Có thêm lock acquisition/holding |
| Chi phí khi xung đột cao | Có thể retry nhiều | Có thể block, deadlock, timeout |
| Thích hợp | Đọc nhiều, ghi ít; conflict hiếm | Critical section ngắn, conflict đáng kể hoặc cần tuần tự hóa |
| Bảo vệ phạm vi | Entity/version được kiểm tra | Các row/database resources thực sự được khóa |

Không có họ khóa nào tự bảo vệ mọi invariant. Một ứng dụng có thể kết hợp optimistic locking, pessimistic locking và constraint database.

## 4. Optimistic locking với @Version

Một entity có thể khai báo version:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class InventoryItem {
    @Id
    private Long id;

    @Column(nullable = false)
    private int available;

    @Version
    private Long version;

    protected InventoryItem() {}

    public void reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            throw new IllegalArgumentException(
                    "Không đủ số lượng tồn kho");
        }
        available -= quantity;
    }
}
```

Khi tải một item, Hibernate đọc cả `available` và `version`. Khi entity được sửa, câu UPDATE có điều kiện version tương tự:

```sql
UPDATE inventory_items
SET available = :new_available,
    version = :new_version
WHERE id = :id
  AND version = :old_version;
```

Nếu một transaction khác đã cập nhật cùng row, điều kiện version cũ không còn khớp. Hibernate nhận biết số hàng được cập nhật không như mong đợi và báo optimistic locking failure (thường là `OptimisticLockException` qua JPA hoặc ngoại lệ tương ứng của Hibernate).

### 4.1. Ví dụ hai transaction cùng đọc

```text
Database: InventoryItem #7
available=5, version=10

Transaction A                  Transaction B
-------------                  -------------
read (5, v10)                  read (5, v10)
reserve(4) → local 1            reserve(3) → local 2
UPDATE ... WHERE v=10           UPDATE ... WHERE v=10
row updated = 1                 row updated = 0
commit                          optimistic lock failure
                                rollback

Kết quả database: available=1, version=11
```

Version ngăn transaction B ghi đè mù lên kết quả A. Nhưng nó không tự làm cho code retry đúng nghiệp vụ. Nếu retry B, phải tải lại số tồn kho và tính lại xem có còn đủ ba đơn vị hay không.

### 4.2. Version bảo vệ row nào?

`@Version` của `InventoryItem` bảo vệ trạng thái entity đó theo mapping và provider. Nó không tự bảo vệ mọi hàng khác chỉ vì chúng có FK tới item. Nếu một entity `Reservation` được sửa, version của `InventoryItem` không nhất thiết tăng.

Ví dụ:

```text
InventoryItem(id=7, version=10)
    ├── Reservation(id=31, version=4)
    └── Reservation(id=32, version=8)

Update Reservation #31:
  - version Reservation #31 có thể tăng lên 5
  - version InventoryItem #7 không tự động tăng chỉ vì child đổi
```

Nếu invariant yêu cầu mọi thay đổi reservation phải được phối hợp qua một version của InventoryItem, cần thiết kế protocol rõ: cập nhật parent có kiểm soát, khóa parent, dùng force increment hoặc đặt constraint/cơ chế database phù hợp. Không giả định FK làm version tự lan truyền.

## 5. LockModeType trong Jakarta Persistence

JPA cung cấp các lock mode qua `jakarta.persistence.LockModeType`:

| Lock mode | Ý nghĩa |
|---|---|
| `NONE` | Không yêu cầu lock mode bổ sung |
| `OPTIMISTIC` | Yêu cầu optimistic lock check cho entity versioned |
| `OPTIMISTIC_FORCE_INCREMENT` | Optimistic lock và buộc tăng version |
| `PESSIMISTIC_READ` | Yêu cầu pessimistic read/shared lock theo khả năng provider/database |
| `PESSIMISTIC_WRITE` | Yêu cầu pessimistic write/exclusive lock |
| `PESSIMISTIC_FORCE_INCREMENT` | Pessimistic write lock và tăng version của entity versioned |

Các tên cũ `READ` và `WRITE` từng là alias cho optimistic lock modes; code mới nên dùng tên tường minh `OPTIMISTIC` và `OPTIMISTIC_FORCE_INCREMENT`.

### 5.1. OPTIMISTIC

```java
em.lock(item, LockModeType.OPTIMISTIC);
```

Đây không phải SQL `SELECT ... FOR UPDATE`. Hibernate/JPA bảo đảm optimistic version check phù hợp với entity versioned trong transaction. Nó hữu ích khi muốn tuyên bố rõ rằng kết quả đọc phải còn hợp lệ tới thời điểm transaction hoàn tất.

### 5.2. OPTIMISTIC_FORCE_INCREMENT

```java
em.lock(item, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

Ngay cả khi field thường của entity không đổi, provider phải thực hiện optimistic lock check và tăng version theo semantics của mode này. Nó có thể dùng để báo rằng một thay đổi ở thành phần/aggregate liên quan cần làm version của root thay đổi, nhưng chỉ hiệu quả nếu **mọi đường ghi có thể vi phạm invariant đều tuân theo cùng protocol**.

### 5.3. PESSIMISTIC_READ

```java
em.lock(item, LockModeType.PESSIMISTIC_READ);
```

Yêu cầu shared/read lock theo khả năng database. Một số database/provider có thể thực hiện lock bằng cơ chế khác hoặc nâng cấp lên write lock khi không có shared lock phù hợp. Không suy ra mọi transaction khác đều được phép ghi trong khi lock này giữ; semantics cụ thể phụ thuộc database.

### 5.4. PESSIMISTIC_WRITE

```java
em.lock(item, LockModeType.PESSIMISTIC_WRITE);
```

Yêu cầu khóa loại write/exclusive lock trên entity state. Trên database hỗ trợ row-level locking, Hibernate thường phát SQL tương tự:

```sql
SELECT id, available, version
FROM inventory_items
WHERE id = ?
FOR UPDATE;
```

Đây là ví dụ PostgreSQL phổ biến; cú pháp SQL và cách provider thực hiện phụ thuộc dialect. Lock thường được giữ tới khi transaction commit hoặc rollback.

### 5.5. PESSIMISTIC_FORCE_INCREMENT

```java
em.lock(item, LockModeType.PESSIMISTIC_FORCE_INCREMENT);
```

Yêu cầu pessimistic write lock và tăng version của entity versioned. Nó kết hợp việc tuần tự hóa ở database với tín hiệu version để các transaction optimistic khác nhận ra entity đã thay đổi.

### 5.6. Lock mode cần transaction phù hợp

Pessimistic lock cần transaction đang hoạt động. Gọi lock khi không có transaction phù hợp có thể dẫn tới `TransactionRequiredException`. Với optimistic locking, cũng cần thực hiện trong transaction có lifecycle nhất quán để version check có ý nghĩa.

Không giữ pessimistic lock qua thời gian người dùng suy nghĩ, gọi HTTP service hoặc chờ nhập liệu. Giữ lock lâu làm tăng blocking và deadlock risk.

## 6. Đặt lock khi tải entity

JPA cho phép yêu cầu lock ngay trong `find()`:

```java
InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE);
```

Có thể truyền thêm hints:

```java
import jakarta.persistence.LockModeType;
import jakarta.persistence.PessimisticLockScope;
import java.util.HashMap;
import java.util.Map;

Map<String, Object> hints = new HashMap<>();
hints.put("jakarta.persistence.lock.timeout", 3000);
hints.put("jakarta.persistence.lock.scope",
        PessimisticLockScope.NORMAL);

InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE,
        hints);
```

Trong ví dụ, timeout là 3.000 milliseconds theo hint JPA. Provider/database có thể có giới hạn hoặc không hỗ trợ chính xác mọi giá trị; hint có thể bị bỏ qua theo khả năng implementation. Không dùng con số này như một cam kết portable rằng request sẽ luôn chờ đúng ba giây.

### 6.1. Khóa entity đã managed

Nếu entity đã được tải:

```java
InventoryItem item = em.find(InventoryItem.class, itemId);
em.lock(item, LockModeType.PESSIMISTIC_WRITE);
```

Hibernate cần thực hiện lock phù hợp cho row của entity. Nếu entity detached, trước hết phải lấy managed instance trong persistence context hiện tại; không coi một Java object có ID hợp lệ là đối tượng có thể khóa trực tiếp.

### 6.2. Khóa qua query

```java
List<InventoryItem> items = em.createQuery(
        "select i from InventoryItem i " +
        "where i.id in :ids order by i.id",
        InventoryItem.class)
        .setParameter("ids", itemIds)
        .setLockMode(LockModeType.PESSIMISTIC_WRITE)
        .getResultList();
```

Query lock mode yêu cầu lock các entity được chọn theo khả năng provider. `ORDER BY` giúp kết quả có thứ tự, nhưng không phải mọi database/provider đều bảo đảm thứ tự acquire lock đúng thứ tự kết quả. Nếu deadlock là rủi ro quan trọng, hãy kiểm tra SQL thực tế và cân nhắc khóa từng row theo thứ tự ổn định trong cùng transaction.

### 6.3. Spring Data JPA

Với repository Spring Data JPA, có thể gắn lock mode:

```java
public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from InventoryItem i where i.id = :id")
    Optional<InventoryItem> findForUpdate(@Param("id") Long id);
}
```

Phương thức repository phải được gọi trong transaction thích hợp. Annotation `@Lock` cấu hình lock mode cho query; nó không tự mở một transaction đủ dài nếu transaction boundary bên ngoài không được thiết lập đúng.

## 7. Khóa thực thể không phải khóa toàn bộ object graph

Xét:

```java
Order order = em.find(
        Order.class, orderId, LockModeType.PESSIMISTIC_WRITE);
```

Không thể suy ra các câu sau đều đúng:

- Mọi `OrderLine` của order đã bị khóa.
- Mọi `Product` được tham chiếu từ OrderLine đã bị khóa.
- Mọi hàng trong join table liên quan đã bị khóa.
- Không transaction nào có thể thêm OrderLine mới cho Order này.
- Version của Order sẽ tăng khi một OrderLine được sửa.

JPA phân biệt khóa trên **state của entity** và phạm vi bổ sung đối với các hàng quan hệ. Một lock request không mặc nhiên cascade qua toàn bộ entity graph như `CascadeType.PERSIST` hay `CascadeType.REMOVE`.

### 7.1. Quan hệ @ManyToOne

Ví dụ OrderLine sở hữu FK:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "order_id", nullable = false)
private Order order;
```

FK `order_id` nằm trên hàng `order_lines`. Nếu khóa Order, database khóa row trong `orders` theo lock request. Hàng OrderLine không tự động trở thành một row bị khóa chỉ vì nó có FK trỏ tới Order.

Ngược lại, nếu khóa một OrderLine bằng `PESSIMISTIC_WRITE`, row OrderLine được khóa; row Order mà nó tham chiếu không tự động bị khóa chỉ vì association được khởi tạo.

### 7.2. Quan hệ @OneToMany(mappedBy=...)

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Phía `Order.lines` là inverse side; FK nằm ở `OrderLine.order`. Khóa Order không đồng nghĩa Hibernate đã khóa từng row con. Nếu invariant yêu cầu không ai sửa bất kỳ dòng nào khi Order được submit, application phải thiết kế một protocol:

1. Mọi command sửa dòng phải khóa Order trước.
2. Command submit cũng khóa cùng Order trước khi kiểm tra trạng thái.
3. Các thao tác child kiểm tra trạng thái parent trong cùng transaction.
4. Có constraint hoặc cơ chế bổ sung nếu cần bảo vệ cả các đường ghi ngoài protocol.

Nếu chỉ một trong hai đường ghi khóa parent, protocol bị phá vỡ.

### 7.3. Quan hệ @ManyToMany

Quan hệ nhiều-nhiều được lưu qua join table:

```text
users
  id=1
     │
     ▼
user_roles(user_id, role_id)
     │
     ▼
roles
  id=10
```

Khóa User không tự khóa row Role; và cũng không mặc nhiên khóa mọi row trong `user_roles`. JPA có `PessimisticLockScope.EXTENDED` để mở rộng phạm vi khóa sang các hàng join table/collection table phù hợp với mapping, nhưng nó **không khóa các entity được tham chiếu**. Khả năng cụ thể còn phụ thuộc provider, dialect và database.

### 7.4. @ElementCollection

Collection table:

```sql
CREATE TABLE account_permissions (
    account_id BIGINT NOT NULL REFERENCES accounts(id),
    permission_code VARCHAR(80) NOT NULL,
    PRIMARY KEY (account_id, permission_code)
);
```

Các giá trị trong collection không phải entity độc lập có `@Version` riêng. Lock scope EXTENDED có thể yêu cầu khóa cả các hàng collection table theo semantics JPA/provider. Tuy nhiên, điều đó không biến một collection lớn thành một vùng được khóa đệ quy và không mặc nhiên chặn mọi row mới được chèn bởi mọi transaction trên mọi database.

### 7.5. @OneToOne

Nếu entity sở hữu FK một-một, row của entity đó chứa FK và khóa row có thể bảo vệ việc đổi FK trên chính row ấy. Nhưng entity đích vẫn là row khác. Nếu cần bảo vệ cả hai entity, phải khóa cả hai hoặc dùng protocol khác.

## 8. PessimisticLockScope.NORMAL và EXTENDED

JPA định nghĩa scope cho pessimistic locks:

| Scope | Phạm vi khái niệm |
|---|---|
| `PessimisticLockScope.NORMAL` | Các hàng đại diện cho state của entity được khóa, bao gồm secondary tables thích hợp |
| `PessimisticLockScope.EXTENDED` | Mở rộng khóa sang các hàng trong join tables/collection tables thuộc các quan hệ phù hợp |

Điểm quan trọng:

- EXTENDED **không** có nghĩa khóa tất cả entity được tham chiếu.
- Với `@OneToMany(mappedBy=...)` có FK trong bảng con, các row child vẫn là entity rows riêng; đừng giả định EXTENDED khóa đệ quy mọi child row.
- Với `@ManyToMany` hoặc `@ElementCollection`, các hàng join/collection table là nơi lưu quan hệ/giá trị; EXTENDED có thể mở rộng scope tới chúng theo mapping.
- Scope không phải predicate/range lock tổng quát bảo vệ mọi hàng có thể được insert trong tương lai.
- Provider/database có thể dùng SQL riêng hoặc không hỗ trợ toàn bộ semantics như mong đợi; cần kiểm tra implementation thực tế.

Đặt scope:

```java
Map<String, Object> hints = Map.of(
        "jakarta.persistence.lock.scope",
        PessimisticLockScope.EXTENDED);

Account account = em.find(
        Account.class,
        accountId,
        LockModeType.PESSIMISTIC_WRITE,
        hints);
```

Nếu chỉ muốn khóa row entity, dùng NORMAL (thường là mặc định). EXTENDED có thể làm tăng số row bị khóa, thời gian giữ lock và khả năng contention. Chỉ bật khi invariant thực sự cần bảo vệ hàng quan hệ được lưu ở join/collection table.

### 8.1. Lock scope không thay thế việc khóa target entity

Giả sử User có nhiều Role qua join table. EXTENDED có thể bảo vệ row liên kết theo semantics của provider, nhưng không tự khóa các row trong bảng `roles`. Nếu một Role có thể bị đổi trạng thái/xóa trong khi đang cấp cho User, cần khóa Role hoặc constraint/FK phù hợp.

### 8.2. Lock scope không tự ngăn phantom rows

Giả sử query đã đọc mọi OrderLine thuộc Order #100. Một transaction khác chèn thêm một dòng mới sau khi các row cũ được khóa. Nếu database chỉ khóa các row đã tồn tại, row mới có thể không bị khóa bởi những lock đó.

Muốn bảo vệ điều kiện “không có thêm dòng mới trong thời gian submit”, có thể:

- Mọi writer phải khóa cùng parent row trước khi insert child.
- Dùng database isolation/predicate or range locking phù hợp.
- Dùng constraint hoặc state transition có điều kiện.
- Thiết kế command để kiểm tra parent state trong cùng transaction với insert child.

Khóa những hàng đang có và bảo vệ một predicate về **tập hợp hàng** là hai vấn đề khác nhau.

## 9. Khóa parent như một mutex nghiệp vụ

Một kỹ thuật phổ biến là khóa row root/parent để serialize các thay đổi liên quan. Ví dụ, tất cả command thêm/xóa/sửa OrderLine phải khóa Order:

```java
@Transactional
public void addLine(Long orderId, String sku, int quantity) {
    Order order = em.find(
            Order.class, orderId, LockModeType.PESSIMISTIC_WRITE);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }
    if (!"DRAFT".equals(order.getStatus())) {
        throw new IllegalStateException(
                "Không thể thêm dòng cho đơn đã gửi");
    }

    OrderLine line = new OrderLine(order, sku, quantity);
    em.persist(line);
}
```

Command submit cũng phải khóa cùng row:

```java
@Transactional
public void submit(Long orderId) {
    Order order = em.find(
            Order.class, orderId, LockModeType.PESSIMISTIC_WRITE);
    if (order == null) {
        throw new IllegalArgumentException("Không tìm thấy đơn");
    }
    if (!"DRAFT".equals(order.getStatus())) {
        throw new IllegalStateException("Đơn không còn ở trạng thái nháp");
    }

    order.markSubmitted();
}
```

Nếu cả hai command đều khóa cùng Order row, một command phải chờ command kia hoàn tất. Khi command submit lấy được lock, nó kiểm tra trạng thái mới nhất trong transaction và chuyển trạng thái. Writer thêm dòng sau đó lấy lock và thấy Order đã SUBMITTED, nên từ chối.

### 9.1. Đây là protocol hợp tác

Khóa parent như mutex chỉ bảo vệ invariant nếu **mọi đường ghi liên quan đều tuân theo**:

- API thêm OrderLine.
- API sửa hoặc xóa OrderLine.
- Job import/batch.
- Admin tool.
- Native SQL hoặc service khác.
- Trigger/procedure nếu có thay đổi liên quan.

Nếu một đường ghi bỏ qua khóa parent, mutex ở application không bảo vệ nó. Constraint database vẫn cần thiết cho invariant có thể diễn đạt bằng unique/check/FK.

### 9.2. Khóa parent không tự khóa mọi child row

Trong ví dụ, lock parent dùng để **tuần tự hóa các command theo quy ước**, không phải vì database tự khóa đệ quy toàn bộ OrderLine. Đây là khác biệt quan trọng giữa:

- “Tôi khóa tất cả child rows.”
- “Mọi writer phải giành cùng một khóa parent trước khi sửa child.”

Cách thứ hai thường giảm số lock cần acquire và xử lý cả trường hợp tập hợp hiện chưa có row nào. Nhưng nó đòi hỏi mọi writer hợp tác.

### 9.3. Có nên kết hợp @Version với parent lock?

Có thể. `@Version` hỗ trợ phát hiện stale update từ các đường optimistic; pessimistic parent lock tuần tự hóa các command cần phối hợp. Nếu thay đổi child không làm parent version tăng, có thể cần `OPTIMISTIC_FORCE_INCREMENT` hoặc protocol cập nhật parent version khi child thay đổi.

Không trộn hai cơ chế một cách tùy tiện. Hãy xác định một quy tắc rõ:

1. Mọi child command khóa parent pessimistic; hoặc
2. Mọi child command force-increment parent version; hoặc
3. Dùng version riêng cho child và constraint database, không yêu cầu parent version bao phủ child graph.

Lựa chọn phụ thuộc contention và invariant thực tế.

## 10. Locking association entity khi quan hệ có vòng đời riêng

Nếu mỗi dòng quan hệ cần ID, version, trạng thái và audit, hãy mô hình hóa nó thành entity liên kết:

```text
Project
  └── ProjectMembership
         ├── id
         ├── project_id
         ├── user_id
         ├── role
         ├── status
         └── version
```

Khi đó có thể khóa chính association entity:

```java
ProjectMembership membership = em.find(
        ProjectMembership.class,
        membershipId,
        LockModeType.PESSIMISTIC_WRITE);
```

Hoặc optimistic locking:

```java
@Entity
public class ProjectMembership {
    @Id
    @GeneratedValue
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Project project;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private User user;

    @Enumerated(EnumType.STRING)
    private MembershipRole role;

    @Version
    private Long version;
}
```

Đây là cách bảo vệ một lần cấp quyền cụ thể. Nhưng nếu invariant là “mỗi project chỉ có tối đa 10 thành viên”, khóa một membership không đủ; cần bảo vệ tổng thể project/collection, ví dụ khóa Project root, dùng counter có cập nhật nguyên tử, constraint hoặc isolation thích hợp.

### 10.1. Unique constraint vẫn quan trọng

Nếu một user chỉ được có một membership cho một project:

```sql
ALTER TABLE project_memberships
ADD CONSTRAINT uq_project_user
UNIQUE (project_id, user_id);
```

Hai transaction có thể cùng đọc và thấy chưa có membership rồi cùng insert. Lock trên một membership chưa tồn tại không có row để khóa. Unique constraint bảo vệ invariant cuối cùng ngay cả khi kiểm tra Java bị race.

## 11. Khóa hàng đang tồn tại và bảo vệ hàng sẽ được tạo

Một câu query:

```sql
SELECT id
FROM reservations
WHERE room_id = :room_id
  AND booking_date = :booking_date
FOR UPDATE;
```

khóa những hàng phù hợp đang tồn tại theo semantics của database. Nếu chưa có reservation nào, query có thể trả 0 row và không có hàng nào để khóa. Hai transaction có thể cùng nhận 0 row rồi cùng insert.

Đây là **insert race/phantom problem**. Cách giải quyết không phải chỉ thêm `PESSIMISTIC_WRITE` vào query.

Các lựa chọn:

- Unique constraint trên `(room_id, booking_date, slot)` nếu domain yêu cầu duy nhất.
- Khóa row Room/Resource đã tồn tại trước khi kiểm tra và insert reservation; mọi writer phải tuân theo protocol đó.
- Isolation `SERIALIZABLE` hoặc cơ chế range/predicate locking được database hỗ trợ, cùng logic retry serialization failure.
- Dùng một bảng slot/inventory row có identity ổn định để khóa trước khi đặt chỗ.

Ví dụ unique constraint:

```sql
CREATE TABLE reservations (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL,
    booking_date DATE NOT NULL,
    slot_code VARCHAR(20) NOT NULL,
    CONSTRAINT uq_room_date_slot
        UNIQUE (room_id, booking_date, slot_code)
);
```

Database là nơi cuối cùng cưỡng chế uniqueness khi nhiều transaction cạnh tranh. Service cần bắt lỗi constraint phù hợp và chuyển thành phản hồi nghiệp vụ, thay vì coi mọi race đều là lỗi hệ thống không thể xử lý.

## 12. Locking và các dạng quan hệ cụ thể

### 12.1. @ManyToOne: khóa hàng sở hữu FK

Giả sử:

```java
@Entity
public class OrderLine {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "order_id")
    private Order order;
}
```

Nếu khóa OrderLine, row `order_lines` bị khóa; nếu đổi `order`, FK ở row con được cập nhật theo transaction. Khóa Order target không tự bảo vệ các thay đổi trên tất cả OrderLine.

### 12.2. @OneToMany mappedBy: parent inverse, child owns FK

Trong:

```java
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

việc add/remove trên collection inverse phải đồng bộ phía `OrderLine.order` để ghi FK đúng. Locking parent không tự khóa mọi row con, nên nếu muốn ngăn sửa child khi parent đóng, dùng root-lock protocol hoặc khóa child rows cụ thể.

### 12.3. @ManyToMany: join table

Khi thêm User vào Role:

```sql
INSERT INTO user_roles(user_id, role_id)
VALUES (:user_id, :role_id);
```

Row mới chưa tồn tại trước khi insert, nên khóa các row User và Role không tự khóa một row join table chưa được tạo. Unique constraint `(user_id, role_id)` ngăn duplicate. Nếu cần serialize việc thay đổi membership theo User, khóa User root trước khi insert/delete join rows.

### 12.4. @ElementCollection: collection table

Với quyền của account hoặc tag của article, phần tử value không có entity version riêng. Nếu cần invariant như “không được thêm permission khi account bị khóa”, lock Account và kiểm tra state trong cùng transaction, đồng thời yêu cầu mọi writer tuân theo protocol.

### 12.5. @Embedded: không có hàng riêng

Giá trị embeddable được lưu trong cột của owner. Khóa row owner bao phủ các cột embedded cùng row đó. Không có entity con riêng để lock bằng identifier. Nếu một giá trị cần được tham chiếu/khóa độc lập, cân nhắc mô hình hóa nó thành entity.

## 13. Locking nhiều entity: thứ tự acquire lock và deadlock

Deadlock có thể xảy ra khi hai transaction khóa cùng nhiều row theo thứ tự ngược:

```text
Transaction A                 Transaction B
-------------                 -------------
lock Account #1               lock Account #2
wait for Account #2           wait for Account #1
       │                             │
       └──────── DEADLOCK ────────────┘
```

Ví dụ hai tài khoản chuyển tiền theo hai hướng đồng thời. Một biện pháp phổ biến là khóa theo thứ tự ID tăng dần:

```java
List<Long> ids = Stream.of(fromId, toId)
        .sorted()
        .toList();

Map<Long, WalletAccount> locked = new HashMap<>();
for (Long id : ids) {
    WalletAccount account = em.find(
            WalletAccount.class,
            id,
            LockModeType.PESSIMISTIC_WRITE);
    if (account == null) {
        throw new IllegalArgumentException("Tài khoản không tồn tại");
    }
    locked.put(id, account);
}

WalletAccount from = locked.get(fromId);
WalletAccount to = locked.get(toId);
```

Đoạn code giả định Java 16+ cho `Stream.toList()` và đã import các collection/stream cần thiết. Việc khóa theo thứ tự ổn định làm giảm một lớp deadlock do lock order đảo ngược, nhưng không loại bỏ mọi deadlock từ foreign key, index, trigger hoặc những bảng khác.

Nếu database báo deadlock victim, transaction bị chọn hủy phải rollback. Có thể retry **toàn bộ transaction** với backoff có giới hạn nếu command idempotent và lỗi được xác định là retryable.

## 14. Lock timeout và các ngoại lệ JPA

JPA cung cấp hint timeout:

```java
Map<String, Object> hints = Map.of(
        "jakarta.persistence.lock.timeout", 0);

InventoryItem item = em.find(
        InventoryItem.class, id,
        LockModeType.PESSIMISTIC_WRITE, hints);
```

Giá trị 0 thường yêu cầu không chờ nếu provider/database hỗ trợ NOWAIT; giá trị dương thường biểu thị milliseconds theo hint. Giá trị âm có thể để provider dùng default. Hint là yêu cầu tới provider, không phải SLA portable cho thời gian chờ.

Các lỗi có thể gặp:

- `PessimisticLockException`: lock failure làm transaction rollback theo semantics JPA.
- `LockTimeoutException`: timeout ở mức statement; transaction không nhất thiết rollback-only.
- `OptimisticLockException`: version/state không khớp.
- Deadlock/serialization errors từ database được provider ánh xạ thành exception cụ thể.
- `TransactionRequiredException` nếu không có transaction.

Việc transaction còn active sau LockTimeoutException và cách driver/provider ánh xạ lỗi cụ thể cần được kiểm tra trong môi trường. Nếu SQL error làm transaction database ở trạng thái aborted, ứng dụng phải rollback trước khi tiếp tục.

### 14.1. Bắt lỗi ở đúng ranh giới

Pessimistic lock có thể thất bại ngay lúc acquire; optimistic lock có thể chỉ thất bại lúc flush/commit. Do đó:

```java
try {
    tx.begin();
    performOperation();
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
```

Không chỉ bao try/catch quanh `em.find()` hoặc `em.lock()`. Cần xử lý cả flush và commit. Trong Spring/JTA, để transaction manager rollback theo rollback rules; không tự commit/rollback thủ công khi interceptor sở hữu transaction.

## 15. Bulk DML và native SQL có bỏ qua optimistic version không?

JPQL bulk update:

```java
int changed = em.createQuery(
        "update InventoryItem i " +
        "set i.available = i.available - :quantity " +
        "where i.id = :id and i.available >= :quantity")
        .setParameter("quantity", quantity)
        .setParameter("id", itemId)
        .executeUpdate();
```

Bulk DML chạy trực tiếp trên database và bỏ qua dirty checking/lifecycle của từng managed entity. Nó không tự áp dụng đầy đủ optimistic versioning như khi sửa một managed entity bình thường. Nếu muốn version được tăng, phải chủ động đưa field version vào query hoặc dùng cơ chế khác:

```java
int changed = em.createQuery(
        "update InventoryItem i " +
        "set i.available = i.available - :quantity, " +
        "    i.version = i.version + 1 " +
        "where i.id = :id " +
        "  and i.version = :expectedVersion " +
        "  and i.available >= :quantity")
        .setParameter("quantity", quantity)
        .setParameter("id", itemId)
        .setParameter("expectedVersion", expectedVersion)
        .executeUpdate();

if (changed != 1) {
    throw new IllegalStateException(
            "Tồn kho đã thay đổi hoặc không đủ số lượng");
}
```

Đây là compare-and-set ở database: điều kiện ID, version và available phải đồng thời đúng. Sau bulk DML, những managed instances tương ứng trong persistence context có thể vẫn giữ state cũ; cần `clear()`, `refresh()` hoặc dùng PC mới theo thiết kế.

Bulk DML là một lựa chọn hữu ích cho thao tác atomic đơn giản, nhưng phải tự quản lý version, validation, audit và cache invalidation nếu cần.

## 16. Locking và isolation level: hai cơ chế bổ trợ nhau

Isolation level xác định những hiệu ứng đọc/ghi mà transaction có thể quan sát; row locks kiểm soát cạnh tranh trên những resource cụ thể. Không thể dùng một thay cho mọi trường hợp của cơ chế còn lại.

| Isolation | Một số đặc tính thường gặp | Vấn đề vẫn cần xem xét |
|---|---|---|
| `READ UNCOMMITTED` | Có thể cho phép dirty reads tùy database | Không phù hợp nhiều nghiệp vụ |
| `READ COMMITTED` | Không đọc dữ liệu chưa commit; mỗi statement có thể thấy snapshot khác | Non-repeatable reads, phantoms tùy database |
| `REPEATABLE READ` | Giữ tính lặp lại của một số lần đọc trong transaction | Semantics phantom/locking khác nhau theo DB |
| `SERIALIZABLE` | Cố tạo kết quả tương đương chạy tuần tự | Có thể abort transaction do serialization conflict; cần retry |

PostgreSQL, MySQL/InnoDB và các database khác có semantics isolation/locking khác nhau. Không copy kết luận về gap locks, next-key locks hoặc predicate locks từ một database sang database khác.

### 16.1. Khi nào cần SERIALIZABLE?

Nếu invariant dựa trên một predicate phức tạp như “tổng số reservation trong khoảng thời gian không vượt 20” và không thể bảo vệ bằng row/counter/constraint đơn giản, SERIALIZABLE có thể là một phương án. Nhưng transaction có thể bị hủy do serialization failure; ứng dụng phải retry toàn bộ unit of work an toàn.

### 16.2. Khóa hàng không tự tạo snapshot nghiệp vụ

Pessimistic lock trên một row không làm mọi truy vấn trong transaction trở thành snapshot bất biến. Transaction vẫn cần hiểu isolation level và những row được khóa. Nếu nghiệp vụ cần bảo vệ một tập hợp hoặc tổng hợp, thiết kế counter/constraint/aggregate row có thể rõ và hiệu quả hơn.

## 17. @Version của parent có bảo vệ collection child không?

Đây là câu hỏi quan trọng khi dùng aggregate root.

Giả sử:

```java
@Entity
public class Order {
    @Id
    private Long id;

    @Version
    private Long version;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
```

và `OrderLine.order` sở hữu FK. Khi một transaction sửa:

```java
line.changeQuantity(4);
```

Hibernate cập nhật row OrderLine. Nếu OrderLine có `@Version` riêng, version của child được bảo vệ. Nhưng không nên giả định parent Order version luôn tăng chỉ vì child đổi. Với mapping inverse `mappedBy`, quan hệ FK thuộc child; việc thay đổi child state không nhất thiết là thay đổi persistent state của parent theo cách khiến parent version tăng.

Với collection do owner trực tiếp quản lý như join/collection table, thay đổi collection có thể tác động version của owner tùy mapping/provider. Phải phân biệt trường hợp đó với child entity có FK ở bảng riêng.

### 17.1. Nếu cần parent version đại diện cho toàn aggregate

Có thể yêu cầu force increment:

```java
Order order = em.find(Order.class, orderId);
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);

OrderLine line = em.find(OrderLine.class, lineId);
line.changeQuantity(4);
```

Hoặc khóa pessimistic parent:

```java
Order order = em.find(
        Order.class, orderId, LockModeType.PESSIMISTIC_WRITE);
```

Nhưng các cách trên chỉ tạo protocol đáng tin nếu **mọi command** sửa child và mọi command kiểm tra invariant của Order đều thực hiện cùng quy tắc. Nếu một batch job cập nhật trực tiếp OrderLine không force-increment hoặc lock parent, parent version không thể đại diện cho thay đổi đó.

### 17.2. Version riêng cho child hay version của root?

| Mô hình | Ưu điểm | Đánh đổi |
|---|---|---|
| Mỗi child có `@Version` riêng | Các dòng độc lập có thể cập nhật song song | Không phát hiện mọi thay đổi giữa nhiều dòng trong cùng aggregate |
| Parent có version được force-increment mỗi child command | Một token đại diện cho aggregate state | Nhiều child updates tranh chấp cùng parent version |
| Pessimistic lock parent cho mọi child command | Tuần tự hóa thay đổi theo root | Blocking, throughput thấp hơn khi nhiều child writes |
| Constraint/counter row ở DB | Bảo vệ invariant cụ thể tại nơi dữ liệu được ghi | Cần thiết kế SQL và error mapping rõ |

Chọn theo invariant thực tế. Không phải aggregate nào cũng cần một version duy nhất cho mọi child.

## 18. Locking trong một workflow đặt chỗ

Giả sử có bảng phòng và reservation:

```sql
CREATE TABLE rooms (
    id BIGINT PRIMARY KEY,
    active BOOLEAN NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE reservations (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL REFERENCES rooms(id),
    slot_start TIMESTAMP NOT NULL,
    slot_end TIMESTAMP NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT ck_reservation_range
        CHECK (slot_end > slot_start)
);
```

Nếu mỗi phòng có một số slot cố định, có thể tạo row đại diện slot và khóa row đó. Nếu booking là khoảng thời gian tùy ý, một unique constraint đơn giản có thể chưa đủ để ngăn overlap; database-specific exclusion constraint, serializable transaction hoặc một mô hình slot phù hợp có thể cần thiết.

Ví dụ khóa Room root:

```java
@Transactional
public Long reserve(Long roomId, LocalDateTime start,
                    LocalDateTime end) {
    Room room = em.find(
            Room.class, roomId, LockModeType.PESSIMISTIC_WRITE);
    if (room == null || !room.isActive()) {
        throw new IllegalStateException("Phòng không khả dụng");
    }

    boolean overlaps = !em.createQuery(
            "select r.id from Reservation r " +
            "where r.room.id = :roomId " +
            "and r.status = :status " +
            "and r.slotStart < :end " +
            "and r.slotEnd > :start",
            Long.class)
            .setParameter("roomId", roomId)
            .setParameter("status", ReservationStatus.CONFIRMED)
            .setParameter("start", start)
            .setParameter("end", end)
            .setMaxResults(1)
            .getResultList()
            .isEmpty();

    if (overlaps) {
        throw new IllegalStateException("Khung giờ đã được đặt");
    }

    Reservation reservation = new Reservation(room, start, end);
    em.persist(reservation);
    return reservation.getId();
}
```

Ví dụ giả định các entity/enum/constructor được định nghĩa và có transaction manager hoạt động. Khóa Room row làm các request cùng phòng phải tuần tự **nếu mọi đường tạo/cancel reservation đều khóa Room trước**. Nếu có đường ghi bỏ qua Room lock, query overlap vẫn có race. Với khoảng thời gian, cần một cơ chế database phù hợp để bảo vệ không-overlap nếu yêu cầu là invariant tuyệt đối.

## 19. Khóa trên entity đã được query: follow-on locking

Một số query có cấu trúc phức tạp (ví dụ DISTINCT, pagination, outer join hoặc query có thể không tương thích trực tiếp với `FOR UPDATE`) có thể khiến Hibernate thực hiện **follow-on locking**:

1. Chạy query lấy entity/ID.
2. Sau đó phát thêm query khóa từng entity hoặc nhóm entity.

Hệ quả có thể là nhiều SQL hơn dự kiến, thứ tự khóa khác với thứ tự query và cửa sổ cạnh tranh giữa lần đọc và lần acquire lock. Cách Hibernate xử lý phụ thuộc dialect/version/query shape.

Khi lock query quan trọng về correctness/performance:

- Bật SQL logging trong môi trường phát triển/test.
- Kiểm tra query thực tế và lock clauses.
- Xem có follow-on locking hay warning liên quan không.
- Tránh pagination phức tạp trên query lock nếu chưa kiểm chứng.
- Nếu cần lock một tập ID, cân nhắc tải và khóa theo batch có thứ tự ổn định.

Không chỉ dựa vào annotation `@Lock` hoặc API `setLockMode()` để kết luận database đã khóa đúng toàn bộ tập row mong muốn.

## 20. Lock timeout và cách xử lý lỗi

JPA hỗ trợ hint:

```java
Map<String, Object> hints = Map.of(
        "jakarta.persistence.lock.timeout", 0);

InventoryItem item = em.find(
        InventoryItem.class, id,
        LockModeType.PESSIMISTIC_WRITE, hints);
```

Giá trị 0 thường yêu cầu không chờ nếu provider/database hỗ trợ NOWAIT. Giá trị dương thường biểu thị milliseconds; provider có thể không hỗ trợ hoặc ánh xạ theo cách riêng. Cần kiểm tra dialect và database.

Các lỗi có thể gặp:

- `PessimisticLockException`: lock failure làm transaction rollback theo semantics JPA.
- `LockTimeoutException`: timeout ở mức statement; transaction không nhất thiết rollback-only.
- `OptimisticLockException`: version/state không khớp.
- Deadlock/serialization errors từ database được provider ánh xạ thành exception cụ thể.
- `TransactionRequiredException` nếu không có transaction.

Không nên catch mọi `PersistenceException` rồi retry ngay trong cùng transaction. Khi DB đã đánh dấu transaction aborted, các câu SQL tiếp theo có thể tiếp tục lỗi. Hãy rollback, mở transaction mới và chỉ retry lỗi được xác định là transient.

### 20.1. Retry cần idempotency

Nếu request đặt chỗ timeout sau khi database đã commit nhưng response bị mất, retry có thể tạo reservation thứ hai. Dùng request key/business key duy nhất:

```sql
ALTER TABLE reservations
ADD COLUMN request_key VARCHAR(80) NOT NULL;

ALTER TABLE reservations
ADD CONSTRAINT uq_reservation_request_key UNIQUE (request_key);
```

Trong ứng dụng, retry cùng request key sẽ tìm hoặc xử lý bản ghi hiện có thay vì tạo tác dụng lặp. Unique constraint là lớp bảo vệ cuối cùng cho tính idempotent của thao tác tạo.

## 21. Transaction boundary quyết định thời gian giữ lock

Pessimistic lock thường được giữ cho đến khi transaction kết thúc. Do đó code:

```java
@Transactional
public void process(Long id) {
    Item item = em.find(
            Item.class, id, LockModeType.PESSIMISTIC_WRITE);

    callRemotePricingService(); // Không nên giữ DB lock khi chờ mạng.

    item.updatePrice(...);
}
```

có thể giữ lock trong suốt thời gian remote service chậm. Điều này làm tăng lock wait, deadlock và connection pool pressure.

Một cấu trúc tốt hơn thường là:

1. Đọc dữ liệu cần thiết và gọi service ngoài trước khi mở critical transaction, nếu semantics cho phép.
2. Mở transaction ngắn.
3. Acquire lock, kiểm tra state/version hiện tại.
4. Áp dụng thay đổi database.
5. Commit sớm.
6. Gửi event/notification qua outbox hoặc cơ chế sau commit phù hợp.

Không thể luôn chuyển network call ra ngoài transaction nếu kết quả bên ngoài quyết định dữ liệu ghi; khi ấy cần saga, idempotency hoặc protocol bù trừ, thay vì giữ lock trong thời gian không giới hạn.

## 22. Locking trên nhiều bảng và thứ tự khóa

Một entity có thể dùng secondary tables hoặc nhiều association. Pessimistic lock scope NORMAL có thể yêu cầu khóa các row biểu diễn entity state, bao gồm secondary table rows theo semantics JPA/provider. Điều đó vẫn khác với việc khóa tất cả entity liên quan.

Nếu một transaction phải khóa:

```text
Order
  ├── Customer
  ├── OrderLine A
  └── OrderLine B
```

hãy xác định thứ tự nhất quán, ví dụ:

1. Khóa Order.
2. Khóa Customer.
3. Khóa OrderLine theo ID tăng dần.

Mọi command liên quan nên tuân theo cùng thứ tự. Một transaction khác khóa Customer trước rồi Order có thể tạo deadlock. Thứ tự khóa là một phần của protocol kiến trúc, không chỉ chi tiết tối ưu.

## 23. @Lock trong Spring Data và transaction boundary

Ví dụ repository:

```java
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findForUpdate(@Param("id") Long id);
}
```

Service:

```java
@Service
public class OrderCommandService {
    private final OrderRepository orders;

    public OrderCommandService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void submit(Long id) {
        Order order = orders.findForUpdate(id)
                .orElseThrow(() ->
                        new IllegalArgumentException("Không tìm thấy đơn"));
        order.markSubmitted();
    }
}
```

Repository method có thể được gọi trong transaction service. Nếu chỉ gọi một locking query không có transaction đủ dài, database lock có thể được giải phóng ngay khi transaction implicit kết thúc hoặc provider báo lỗi transaction required. Đặt transaction boundary quanh toàn bộ read-check-write, không chỉ quanh câu query khóa.

Trong Spring, annotation `@Transactional` cần được gọi qua proxy/interceptor. Self-invocation hoặc cấu hình nhiều transaction managers có thể khiến method không tham gia transaction như mong đợi.

## 24. Database constraints và locking phải đi cùng nhau

Khóa thường bảo vệ một luồng thao tác trong khi transaction đang chạy. Constraint bảo vệ dữ liệu **cuối cùng** bất kể writer đến từ Hibernate, SQL script hay một service khác.

| Invariant | Công cụ phù hợp |
|---|---|
| Một user chỉ có một membership trong project | UNIQUE(project_id, user_id) |
| Quantity phải dương | CHECK(quantity > 0) |
| Child phải thuộc parent tồn tại | FOREIGN KEY |
| Không cho phép số dư âm | CHECK(balance >= 0) kết hợp atomic update/locking phù hợp |
| Không có hai reservation cùng slot | UNIQUE key/slot model |
| Parent phải còn DRAFT khi thêm child | Parent lock protocol + state check trong transaction; có thể bổ sung DB procedure/conditional write |
| Tổng child không vượt giới hạn | Root lock/counter atomic/serializable hoặc mô hình slot, tùy domain |

Không phải mọi invariant đều biểu diễn được bằng một constraint đơn giản. Nhưng khi database có thể cưỡng chế, hãy để database làm lớp bảo vệ cuối cùng thay vì chỉ kiểm tra Java trước khi ghi.

## 25. @Version và unique constraint giải quyết hai loại race khác nhau

Giả sử hai transaction thêm cùng một email vào danh sách subscriber:

```text
T1: SELECT → chưa có email
T2: SELECT → chưa có email
T1: INSERT
T2: INSERT
```

Nếu parent version không tăng khi hai transaction cùng thêm child, optimistic locking trên parent có thể không ngăn được race này. Unique constraint:

```sql
ALTER TABLE subscribers
ADD CONSTRAINT uq_subscriber_email UNIQUE (email);
```

mới trực tiếp bảo vệ tính duy nhất. Ngược lại, nếu hai transaction cùng cập nhật một field mutable trên cùng entity, `@Version` là cơ chế thích hợp để phát hiện stale write.

Hãy chọn cơ chế theo **điều kiện cần bảo vệ**, không theo tên gọi chung “concurrency control”.

## 26. Kiểm thử phạm vi bảo vệ thay vì chỉ kiểm thử annotation

Một unit test xác nhận code gọi:

```java
em.find(Order.class, id, LockModeType.PESSIMISTIC_WRITE);
```

chưa chứng minh database thực sự bảo vệ invariant. Cần integration test với database engine gần production và hai transaction độc lập.

### 26.1. Kiểm thử row lock cơ bản

Một kịch bản:

1. Transaction A mở và khóa row InventoryItem bằng `PESSIMISTIC_WRITE`.
2. A giữ transaction chưa commit.
3. Transaction B thử khóa/cập nhật cùng row.
4. Xác nhận B bị block hoặc timeout theo database/hint.
5. A commit/rollback.
6. Xác nhận B tiếp tục hoặc nhận lỗi đúng.

Dùng hai EntityManager/Session khác nhau và hai connection thực sự độc lập. Không chạy hai thao tác trong cùng persistence context rồi suy ra behavior concurrency.

### 26.2. Kiểm thử root-lock protocol

Kiểm tra:

- Request A khóa Order và chuẩn bị submit.
- Request B thêm OrderLine nhưng cũng phải khóa Order.
- Xác nhận B chờ A; sau khi A commit, B đọc trạng thái mới và từ chối.
- Tạo một đường ghi thử nghiệm bỏ qua root lock để thấy protocol không bảo vệ đường đó; nếu có external writer, cần constraint/database enforcement.

### 26.3. Kiểm thử phantom/unique race

Hai transaction cùng query “chưa tồn tại”, sau đó cùng insert. Xác nhận unique constraint chỉ cho một transaction thành công. Nếu thiết kế dựa trên SERIALIZABLE, kiểm thử serialization failure và retry.

### 26.4. Kiểm thử version

Hai EntityManager tải cùng entity/version. Transaction A commit update; transaction B sửa stale instance và commit. Xác nhận B nhận optimistic lock exception và dữ liệu A được giữ.

### 26.5. Theo dõi SQL và lock ở database

Trong môi trường test:

- Bật SQL logging để xem `FOR UPDATE` hoặc câu lệnh lock tương ứng.
- Xem bind parameters và thứ tự query.
- Dùng công cụ database để quan sát lock waits/blocked sessions.
- Kiểm tra index của predicate query.
- Không dùng H2 thay thế hoàn toàn cho PostgreSQL/MySQL khi đang kiểm thử lock semantics phụ thuộc dialect.

## 27. Chọn chiến lược theo invariant

| Nhu cầu nghiệp vụ | Chiến lược thường cân nhắc |
|---|---|
| Nhiều user sửa độc lập các trường của cùng một entity | `@Version` trên entity |
| Hai request cùng cập nhật số tồn kho và cần giữ không âm | Optimistic version hoặc atomic conditional UPDATE, kết hợp CHECK |
| Mọi thao tác trên một Order phải tuần tự hóa | Pessimistic lock trên Order root, mọi writer cùng tuân thủ |
| Cập nhật một OrderLine độc lập | Version/lock trên OrderLine; kiểm tra parent state theo protocol |
| Thay đổi membership qua join table | Lock owner/association theo invariant, unique constraint |
| Chỉ bảo vệ row association đang tồn tại | Pessimistic lock scope EXTENDED nếu mapping/provider phù hợp |
| Chặn duplicate association chưa tồn tại | Unique constraint, không chỉ row lock |
| Bảo vệ predicate/range phức tạp | Isolation SERIALIZABLE hoặc database-specific range/predicate mechanism |
| Nhiều row luôn khóa theo nhóm | Acquire theo thứ tự ổn định; transaction ngắn |
| Nhiều resource phải commit nguyên tử | JTA/XA nếu mọi resource hỗ trợ; nếu không cân nhắc outbox/saga |

## 28. Quy trình thiết kế khóa cho một aggregate

Khi bắt đầu một tính năng, đi theo các bước:

**1. Viết invariant bằng ngôn ngữ nghiệp vụ.** Ví dụ: “Order đã SUBMITTED không được thêm, sửa hoặc xóa dòng”.

**2. Xác định mọi row tham gia invariant.** Order, OrderLine, bảng join, inventory, reservation hoặc counter.

**3. Xem mapping lưu quan hệ ở đâu.** FK nằm ở owner hay child? Association có join table? Collection có table riêng?

**4. Xác định cơ chế cạnh tranh.** Version từng entity, lock row cụ thể, root lock, unique/check/FK constraint hoặc isolation level.

**5. Định nghĩa một protocol cho mọi writer.** API, batch, scheduler, admin, native SQL và service khác phải cùng tuân thủ nếu invariant dựa trên lock hợp tác.

**6. Giữ transaction ngắn.** Acquire lock, kiểm tra state, ghi và commit; tránh network calls và công việc lâu trong critical section.

**7. Xử lý failure có chủ đích.** Optimistic conflict, lock timeout, deadlock và serialization failure có retry policy riêng; command cần idempotency nếu có thể retry.

**8. Kiểm thử trên database thực tế.** Hai transaction độc lập, lock wait, insert race, version conflict và SQL thực tế.

## 29. Sơ đồ chọn phạm vi khóa

```text
                Cần bảo vệ một invariant
                           │
                 Invariant nằm trên đâu?
                           │
          ┌────────────────┼─────────────────┐
          │                │                 │
      Một entity       Nhiều entity       Tập hợp/Predicate
          │                │                 │
          ▼                ▼                 ▼
       @Version       Có root ổn định?   Có constraint biểu diễn
          │              │              được invariant không?
          │        ┌─────┴─────┐             │
          │       CÓ          KHÔNG      ┌────┴────┐
          │        │            │       CÓ       KHÔNG
          │        ▼            ▼        │          │
          │   Lock root +   Khóa từng    ▼          ▼
          │   protocol      row/association UNIQUE / CHECK /
          │   cho mọi writer entity cụ thể FK       SERIALIZABLE /
          │                                    range/predicate lock
          └────────────────┬───────────────────────┘
                           ▼
                 Transaction boundary rõ ràng
                 timeout, deadlock, retry, idempotency
                           │
                           ▼
                Integration test với DB thực tế
```

## 30. Những kết luận cần nhớ

`@Version` bảo vệ state của entity được version hóa; nó không tự lan sang mọi entity có quan hệ. `PESSIMISTIC_WRITE` thường khóa row đại diện cho entity, không tự khóa đệ quy object graph. `PessimisticLockScope.EXTENDED` có thể mở rộng tới các row join/collection table phù hợp, nhưng không khóa entity được tham chiếu và không phải cơ chế chặn mọi phantom insert.

Với `@ManyToOne` và `@OneToMany(mappedBy=...)`, FK thường nằm ở bảng con; khóa parent không tự khóa tất cả child rows. Với `@ManyToMany` và `@ElementCollection`, association nằm trong join/collection table; scope mở rộng có thể liên quan đến các row đó nhưng cần kiểm chứng theo provider và database. Khi cần bảo vệ invariant trên một aggregate, root-lock protocol chỉ hiệu quả nếu mọi đường ghi đều tuân thủ.

Cuối cùng, **row lock, version check, constraint và isolation level giải quyết các loại race khác nhau**. Thiết kế tốt bắt đầu từ invariant, xác định đúng row/predicate cần bảo vệ, rồi chọn cơ chế phù hợp. Kiểm tra SQL và thử nghiệm bằng nhiều transaction độc lập trên database thật mới cho thấy phạm vi bảo vệ thực tế.
