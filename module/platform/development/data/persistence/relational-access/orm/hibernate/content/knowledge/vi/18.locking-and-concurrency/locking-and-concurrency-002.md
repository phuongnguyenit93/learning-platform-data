# @Version cho kiểm soát khóa lạc quan

Trong Hibernate/JPA, nhiều người dùng hoặc request có thể cùng tải và cập nhật một entity. Nếu hai transaction đều đọc một phiên bản dữ liệu cũ rồi lần lượt ghi thay đổi, **người ghi sau có thể vô tình ghi đè kết quả của người ghi trước**. Hiện tượng này được gọi là **lost update**.

Annotation **`@Version`** của Jakarta Persistence giúp Hibernate áp dụng **optimistic locking** (kiểm soát đồng thời lạc quan). Thay vì giữ khóa database từ lúc đọc đến lúc ghi, Hibernate kiểm tra xem phiên bản của bản ghi có thay đổi kể từ lần đọc hay không. Nếu dữ liệu đã bị transaction khác sửa, thao tác ghi không được âm thầm tiếp tục như thể dữ liệu vẫn mới.

Cơ chế thường được mô tả bằng SQL:

~~~sql
UPDATE inventory_items
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

Điều kiện `WHERE version = ?` kiểm tra phiên bản đã đọc. Một câu UPDATE cần ảnh hưởng đúng một hàng mà nhận 0 hàng có thể báo hiệu dữ liệu đã cũ, hàng đã bị xóa hoặc phiên bản không còn khớp.

Bài học trình bày cách dùng `@Version`, cơ chế SQL, transaction và flush, xử lý xung đột, giao tiếp REST, cách dùng trong Spring Data JPA và những giới hạn cần lưu ý với bulk SQL hoặc nhiều entity.

## 1. Bài toán lost update

Giả sử bảng `inventory_items` có:

| id | sku | quantity |
| ---: | --- | ---: |
| 10 | LAPTOP-01 | 10 |

Hai transaction cùng muốn xuất kho:

- Transaction A xuất 3 chiếc.
- Transaction B xuất 4 chiếc.
- Cả hai đều đọc số lượng ban đầu là 10.

Nếu không có cơ chế phát hiện xung đột:

~~~text
Thời điểm   Transaction A                    Transaction B
----------  -------------------------------  ----------------------------
T1          SELECT quantity → 10
T2                                           SELECT quantity → 10
T3          Tính 10 - 3 = 7
T4                                           Tính 10 - 4 = 6
T5          UPDATE quantity = 7
T6          COMMIT
T7                                           UPDATE quantity = 6
T8                                           COMMIT

Kết quả cuối là quantity = 6, thay vì 3.
~~~

Khi B tính trên snapshot cũ và ghi 6, kết quả xuất 3 chiếc của A bị mất khỏi số lượng cuối. Đây là lost update.

Không nên mặc định một transaction thông thường luôn ngăn được trường hợp này. Hành vi đồng thời còn phụ thuộc isolation của database, cấu trúc SQL, lock và thời điểm các transaction đọc/ghi. `@Version` đưa ra một **hợp đồng kiểm tra phiên bản rõ ràng** cho entity được Hibernate quản lý.

### 1.1. Optimistic locking có phải khóa từ lúc SELECT?

Không. Với optimistic locking, hai transaction có thể cùng đọc hàng và cùng xử lý trong Java. Khi gửi UPDATE, mỗi transaction cố ghi với version mà nó đã đọc; một transaction thành công, transaction còn lại có thể nhận lỗi vì version đã cũ.

Điều này khác pessimistic locking: pessimistic lock chủ động yêu cầu database khóa hàng hoặc tài nguyên liên quan khi đọc/ghi theo lock mode, có thể khiến transaction khác phải chờ.

### 1.2. Khi nào thích hợp?

Optimistic locking thường phù hợp nếu:

- Xung đột ghi tương đối hiếm.
- Các transaction đọc nhiều nhưng ghi không liên tục lên cùng một hàng.
- Có thể báo lỗi cho người dùng hoặc retry một cách có kiểm soát.
- Muốn tránh giữ database lock dài từ lúc đọc đến lúc ghi.

Nếu hàng quá “nóng”, nhiều transaction liên tục cạnh tranh, số lần retry có thể tăng cao. Khi đó cần xem xét mô hình cập nhật hoặc concurrency strategy khác.

## 2. Khai báo @Version

Import chuẩn Jakarta Persistence:

~~~java
import jakarta.persistence.Version;
~~~

Cách dùng thông dụng:

~~~java
@Version
private Long version;
~~~

Hoặc:

~~~java
@Version
private long version;
~~~

Hibernate quản lý giá trị version khi entity được persist và thay đổi. Ứng dụng **không tự tăng hoặc tùy ý gán version** bằng setter nghiệp vụ.

Ví dụ:

~~~java
@Version
@Column(nullable = false)
private Long version;

public Long getVersion() {
    return version;
}
~~~

Không nên mở public setter chỉ để client gửi version mới vào object:

~~~java
// Không khuyến nghị:
// public void setVersion(Long value) { this.version = value; }
~~~

Version là metadata persistent dùng để phát hiện đồng thời. Nếu cần client truyền phiên bản mong đợi, hãy nhận qua DTO/HTTP precondition và so sánh theo hợp đồng API; không coi giá trị do client gán trực tiếp vào entity là nguồn tin cậy.

### 2.1. Kiểu version

JPA hỗ trợ các kiểu số nguyên và timestamp theo đặc tả. Hibernate có thể hỗ trợ thêm dạng/version strategy tùy phiên bản. Với hệ thống mới, kiểu `Long` hoặc `long` thường đơn giản, dễ quan sát và ít rủi ro hơn timestamp khi so sánh.

Kiểu wrapper `Long` có lợi trong một số cơ chế xác định entity mới/detached khi giá trị chưa được gán là `null`. Không dựa vào giả định rằng mọi entity mới luôn bắt đầu version 0 hoặc 1: giá trị seed/increment còn tùy provider, kiểu dữ liệu và mapping.

### 2.2. Annotation đặt trên field hay getter?

Nếu `@Id` đặt trên field, entity mặc định dùng field access; đặt `@Version` trên field tương ứng:

~~~java
@Id
private Long id;

@Version
private Long version;
~~~

Nếu `@Id` đặt trên getter và entity dùng property access, nên đặt `@Version` trên getter:

~~~java
@Id
public Long getId() {
    return id;
}

@Version
public Long getVersion() {
    return version;
}
~~~

Đừng trộn annotation field/getter một cách tùy tiện nếu chưa xác định `@Access`; Hibernate có thể không ánh xạ như mong muốn.

## 3. Entity mẫu: InventoryItem

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String sku;

    @Column(nullable = false)
    private int quantity;

    @Version
    @Column(nullable = false)
    private Long version;

    protected InventoryItem() {
        // JPA constructor.
    }

    public InventoryItem(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("Tồn kho âm");
        }
        this.sku = sku;
        this.quantity = quantity;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public Long getVersion() {
        return version;
    }

    public void decrease(int amount) {
        if (amount <= 0 || amount > quantity) {
            throw new IllegalArgumentException("Không đủ hàng");
        }
        quantity -= amount;
    }

    public void increase(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        quantity += amount;
    }
}
~~~

Một schema PostgreSQL minh họa:

~~~sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(100) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT ck_quantity_non_negative CHECK (quantity >= 0)
);
~~~

Đây là ví dụ cấu trúc SQL, không phải DDL sinh ra giống hệt trên mọi database. Migration thực tế cần phù hợp với dialect và dữ liệu cũ.

Ràng buộc `CHECK (quantity >= 0)` bảo vệ giá trị không âm. `@Version` bảo vệ một số dạng xung đột giữa những transaction cập nhật cùng entity. **Hai cơ chế giải quyết hai vấn đề khác nhau.**

## 4. Hibernate sử dụng @Version trong SQL ra sao?

Giả sử một entity có version 5:

~~~java
InventoryItem item = em.find(InventoryItem.class, 10L);
item.decrease(3);
~~~

Khi Hibernate dirty-check và flush, nó có thể phát SQL tương đương:

~~~sql
UPDATE inventory_items
SET quantity = 7,
    version = 6
WHERE id = 10
  AND version = 5;
~~~

Trong JDBC thực tế, Hibernate dùng `?` và bind giá trị chứ không nhất thiết nhúng số literal như minh họa. Mấu chốt là:

- `id = 10` chọn hàng muốn sửa.
- `version = 5` chọn đúng **phiên bản** ứng dụng đã đọc.
- Nếu thành công, state persistent chuyển sang version mới theo cơ chế versioning.
- Nếu hàng không còn version 5, UPDATE không khớp và Hibernate có thể báo lỗi stale state.

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as Transaction B
    participant DB as Database
    A->>DB: SELECT item version=5, quantity=10
    B->>DB: SELECT item version=5, quantity=10
    A->>DB: UPDATE quantity=7, version=6 WHERE version=5
    DB-->>A: 1 row updated
    A->>DB: COMMIT
    B->>DB: UPDATE quantity=6, version=6 WHERE version=5
    DB-->>B: 0 rows / conflict
    B-->>B: Rollback hoặc xử lý lỗi
~~~

Kết quả không phải B tự được “tính lại quantity=3”. Optimistic locking **phát hiện xung đột, không tự hòa giải state**.

### 4.1. Không nhất thiết tăng version khi không đổi state

~~~java
InventoryItem item = em.find(InventoryItem.class, 10L);
em.flush();
~~~

Nếu không có persistent changes và không yêu cầu force increment, Hibernate thường không phát UPDATE chỉ vì flush, nên version không tự tăng mỗi lần gọi API đọc.

Version không phải bộ đếm số lần SELECT hoặc số lần người dùng nhấn nút.

### 4.2. Khi xóa entity

Với một entity versioned, DELETE do ORM thực hiện có thể kèm version:

~~~sql
DELETE FROM inventory_items
WHERE id = ?
  AND version = ?;
~~~

Nếu hàng bị cập nhật/xóa bởi transaction khác, câu DELETE theo snapshot cũ có thể không còn phù hợp và gây optimistic locking conflict.

Không nên áp dụng kết luận này cho mọi bulk SQL/native DELETE; bulk operations có semantics riêng, được trình bày ở phần sau.

## 5. Lỗi xung đột có thể xuất hiện lúc nào?

Setter trên managed entity thường chỉ đổi state Java:

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.decrease(2);
// Chưa bảo đảm UPDATE đã chạy.
~~~

Hibernate thường gửi UPDATE lúc flush hoặc commit. Vì vậy lỗi version có thể phát sinh tại:

~~~java
em.flush();
~~~

hoặc tại transaction commit nếu SQL mới được thực thi/kiểm tra khi đó.

### 5.1. Resource-local transaction

~~~java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    InventoryItem item = em.find(
        InventoryItem.class, itemId
    );

    item.decrease(2);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
~~~

Ví dụ dùng JPA resource-local; nếu ứng dụng dùng Spring-managed transaction hoặc JTA, không tự gọi `em.getTransaction()` trên shared EntityManager do framework quản lý.

Nếu một transaction khác đã cập nhật entity và version không còn tương ứng, transaction hiện tại có thể thất bại. Khi phát sinh lỗi persistence, thường cần **rollback và kết thúc persistence context không còn đáng tin**, thay vì cố sửa object rồi commit trong cùng transaction.

### 5.2. Các loại exception

API JPA thường sử dụng:

~~~java
jakarta.persistence.OptimisticLockException
~~~

Hibernate có thể ném exception nội bộ về stale object state. Spring Data JPA/Spring ORM có thể chuyển đổi thành `OptimisticLockingFailureException` hoặc `ObjectOptimisticLockingFailureException` tùy tình huống.

Điểm xử lý exception cụ thể phụ thuộc transaction manager, provider và tầng abstraction. Không nên giả định exception luôn xuất hiện ngay tại lệnh setter hoặc ngay tại `save()`.

### 5.3. Flush không đồng nghĩa commit

~~~java
item.decrease(2);
em.flush(); // Có thể gửi UPDATE và kiểm tra version.

// Nếu transaction rollback sau đó,
// dữ liệu/version mới chưa được commit sẽ bị hoàn tác.
~~~

Version mới có thể đã hiện trong managed object và SQL đã được gửi, nhưng transaction chưa được xác nhận bền vững. Sau rollback, không nên dùng object Java cũ như biểu diễn chắc chắn của database; cần đọc lại trong transaction mới.

## 6. Xử lý OptimisticLockException như thế nào?

Khi gặp conflict, không nên tắt `@Version` hoặc bỏ điều kiện version để “cho cập nhật qua”. Cần quyết định nghiệp vụ về việc state đã thay đổi trong thời gian xử lý.

Quy trình điển hình:

1. Để transaction lỗi rollback.
2. Kết thúc scope `EntityManager`/`Session` liên quan.
3. Bắt đầu một transaction mới nếu cần đọc lại dữ liệu.
4. So sánh state mới với thao tác mà request muốn thực hiện.
5. Chọn báo người dùng, yêu cầu xác nhận, hoặc retry có giới hạn.
6. Nếu retry, **tính lại quyết định trên state mới**, không ghi lại nguyên snapshot cũ.
7. Xử lý tác dụng phụ ngoài database để tránh thực hiện trùng lặp.

### 6.1. Ví dụ retry đúng nghiệp vụ

Ban đầu stock=10:

- A xuất 7 chiếc, commit stock=3.
- B cũng đã đọc stock=10 và định xuất 5 chiếc.
- B nhận optimistic locking exception khi cố ghi stock=5.
- B retry đúng: nạp lại stock=3, kiểm tra không đủ 5 chiếc, trả lỗi nghiệp vụ.
- B retry sai: dùng lại state detached cũ và ép ghi quantity=5.

Optimistic locking chỉ chỉ ra rằng thao tác cũ không còn hợp lệ. Nó không tự biết cần trừ kho, cộng tiền hoặc điều chỉnh lịch đặt chỗ thế nào.

### 6.2. Retry trong transaction mới

Nếu service dùng Spring `@Transactional` và flush bị lỗi, đừng bắt exception rồi chạy lại thao tác trong **cùng transaction đã rollback-only**. Retry nên được đặt ở tầng bao ngoài mỗi transaction attempt, ví dụ một orchestration layer gọi lại service transaction với dữ liệu mới.

Chính sách retry cần có giới hạn, có thể có backoff và metrics. Với thao tác giao diện người dùng sửa nội dung, thường nên trả conflict để họ quyết định thay vì tự retry và ghi đè.

### 6.3. Side effect bên ngoài DB

Nếu service gửi email hoặc gọi payment API trước khi commit thất bại, rollback DB không tự thu hồi side effect đó. Khi retry, email/call có thể bị lặp.

Đối với nghiệp vụ cần độ tin cậy, cân nhắc idempotency key, transactional outbox, event sau commit và thiết kế khả năng phục hồi đúng phạm vi; `@Version` không thay thế các cơ chế này.

## 7. Spring Data JPA và @Transactional

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface InventoryRepository
        extends JpaRepository<InventoryItem, Long> {
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void ship(Long itemId, int amount) {
        InventoryItem item = repository.findById(itemId)
            .orElseThrow(() ->
                new IllegalArgumentException("Không tìm thấy hàng"));

        item.decrease(amount);

        // Dirty checking + @Version xử lý tại flush/commit.
    }
}
~~~

Nếu entity được tải là managed trong cùng transaction, không nhất thiết gọi `repository.save(item)`. Hibernate theo dõi thay đổi qua dirty checking.

### 7.1. Không bắt lỗi và tiếp tục transaction cũ

~~~java
@Transactional
public void unsafe(Long itemId) {
    try {
        InventoryItem item = repository.findById(itemId)
            .orElseThrow();
        item.decrease(1);
        repository.flush();
    } catch (RuntimeException ex) {
        // Không nên bỏ qua rồi coi transaction vẫn hợp lệ.
    }
}
~~~

Sau lỗi flush, transaction có thể được đánh dấu rollback-only hoặc persistence context có state không còn nhất quán. Hướng thông thường là rollback, tạo transaction/context mới, rồi mới retry nếu nghiệp vụ cho phép.

### 7.2. saveAndFlush không phải commit

~~~java
InventoryItem saved = repository.saveAndFlush(item);
~~~

`saveAndFlush()` có thể làm UPDATE và kiểm tra version xảy ra sớm hơn trong transaction, nhưng **không commit một transaction bao ngoài**. Giao dịch vẫn có thể rollback ở bước tiếp theo.

### 7.3. @Transactional không tự thay thế version

`@Transactional` chỉ định phạm vi transaction. `@Version` bổ sung kiểm tra optimistic concurrency cho entity được ORM ghi. Hai cơ chế kết hợp, không phải cách gọi khác nhau của cùng tính năng.

## 8. Detached entity, merge và version

Khi entity rời persistence context, nó trở thành **detached** nhưng vẫn có thể giữ ID, version và các field đã đọc.

~~~java
InventoryItem detached = loadFromOldContext();

InventoryItem managed = em.merge(detached);
~~~

`merge()` sao chép persistent state của detached source vào managed counterpart và trả về managed instance. Với versioned entity, nếu detached source mang version cũ, Hibernate có thể phát hiện xung đột tại merge, flush hoặc commit.

**Lưu ý:** Merge không biến chính object detached truyền vào thành managed.

~~~java
InventoryItem managed = em.merge(detached);
managed.decrease(1);
~~~

Nên sửa trên managed result và hiểu rằng một source detached có thể chứa toàn bộ persistent state cũ, không chỉ những field người dùng vừa sửa.

### 8.1. Không xem JSON có ID là entity detached an toàn

Giả sử client gửi:

~~~json
{
  "id": 10,
  "quantity": 7,
  "version": 3
}
~~~

Nếu server tự dựng entity từ JSON rồi gọi merge, những field không được gửi có thể có giá trị `null`/mặc định và vô tình ghi đè state khác, tùy mapping và quá trình deserialize. Client còn có thể gán ID hoặc version tùy ý.

Với API cập nhật, hướng phổ biến là:

- Dùng DTO chỉ gồm những trường được phép thay đổi.
- Xác thực quyền của người dùng.
- Load managed entity trong transaction.
- Kiểm tra phiên bản client kỳ vọng nếu phải chống ghi từ form cũ.
- Thực hiện domain method cho các field được phép sửa.
- Để Hibernate `@Version` phát hiện race trong lúc flush/commit.

### 8.2. Tại sao chỉ @Version vẫn có thể không phát hiện form cũ?

Đây là điểm rất quan trọng với REST/web.

1. Client A GET item khi version=3.
2. Client B sửa item và commit, DB lên version=4.
3. Client A gửi form cũ lên server.
4. Service của A **không nhận hoặc không kiểm tra version=3**, mà `find()` lấy managed item version=4.
5. Service cập nhật vài field rồi commit từ version=4 lên 5 thành công.

Hibernate không biết A đã xem version=3 vì transaction A **mới bắt đầu sau khi B commit** và đã load version 4. `@Version` bảo vệ race kể từ khi A load version 4, không tự biết những lần xem form trước đó.

Nếu muốn **optimistic concurrency xuyên nhiều HTTP request**, API phải mang thông tin phiên bản/ETag mà client đã xem và so sánh ở server.

## 9. REST API: expectedVersion và If-Match

Một response có thể bao gồm version:

~~~http
HTTP/1.1 200 OK
ETag: "item-10-v5"
Content-Type: application/json

{
  "id": 10,
  "sku": "LAPTOP-01",
  "quantity": 10,
  "version": 5
}
~~~

Khi cập nhật:

~~~http
PATCH /inventory-items/10
If-Match: "item-10-v5"
Content-Type: application/json

{
  "decreaseBy": 3
}
~~~

Server cần xác thực quyền, kiểm tra ETag hoặc version mong đợi, thực hiện thao tác trên managed entity và để Hibernate kiểm tra version tại thời điểm ghi.

Với HTTP conditional request, khi `If-Match` không còn đúng, phản hồi phổ biến là **412 Precondition Failed**. Hệ thống cũng có thể sử dụng **409 Conflict** cho các xung đột mang tính nghiệp vụ theo hợp đồng API. Không thay thế authorization bằng ETag.

### 9.1. DTO expectedVersion

~~~java
public record DecreaseStockRequest(
    long expectedVersion,
    int amount
) {}
~~~

Service:

~~~java
@Transactional
public void decreaseWithVersion(
        Long itemId,
        DecreaseStockRequest request) {

    InventoryItem item = repository.findById(itemId)
        .orElseThrow(() ->
            new IllegalArgumentException("Không tìm thấy hàng"));

    if (!Long.valueOf(request.expectedVersion())
            .equals(item.getVersion())) {
        throw new StaleClientVersionException(
            "Dữ liệu đã thay đổi, vui lòng tải lại");
    }

    item.decrease(request.amount());

    // @Version vẫn kiểm tra xung đột phát sinh sau SELECT.
}
~~~

`StaleClientVersionException` là class exception nghiệp vụ giả định của ứng dụng.

Kiểm tra `expectedVersion` trong Java **không thay thế `@Version`**. Hai transaction có thể cùng vượt qua phép so sánh Java khi đọc cùng version. Điều kiện version trong SQL UPDATE mới phát hiện race giữa lần kiểm tra và lúc ghi.

### 9.2. ETag cần đại diện đúng resource

Nếu response tổng hợp nhiều entity hoặc dữ liệu ngoài bảng item, version của riêng InventoryItem có thể không đại diện cho toàn bộ representation. Thiết kế ETag cần phù hợp hợp đồng API, không chỉ nối một ID và version tùy ý rồi mặc định bao phủ mọi dữ liệu.

## 10. Optimistic lock modes của JPA

JPA cung cấp thêm lock mode cho những trường hợp cụ thể:

~~~java
em.lock(item, LockModeType.OPTIMISTIC);
~~~

~~~java
em.lock(item, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

| Lock mode | Mục đích | Điểm cần nhớ |
| --- | --- | --- |
| `OPTIMISTIC` | Yêu cầu kiểm tra optimistic version phù hợp | Không nhất thiết tăng version khi không có thay đổi |
| `OPTIMISTIC_FORCE_INCREMENT` | Kiểm tra và buộc tăng version theo semantics JPA | Có thể sinh update version dù không sửa field domain |
| `PESSIMISTIC_READ` / `PESSIMISTIC_WRITE` | Yêu cầu DB lock phù hợp | Có thể chờ/timeout/deadlock tùy DB |

Ví dụ:

~~~java
Order order = em.find(Order.class, orderId);
em.lock(order, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
~~~

Trường hợp này có thể được dùng khi muốn version của root thay đổi do một thao tác nghiệp vụ ảnh hưởng aggregate dù không sửa trực tiếp field persistent của root.

Không lạm dụng FORCE_INCREMENT để “chắc ăn” trong mọi luồng đọc. Việc tăng version không cần thiết tạo thêm conflict và UPDATE.

## 11. @Version của aggregate root và entity con

Một entity root:

~~~java
@Entity
public class Order {

    @Id
    private Long id;

    @Version
    private long version;

    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderLine> lines = new ArrayList<>();
}
~~~

`@Version` trên Order bảo vệ thao tác cập nhật persistent state của **Order**. Nó **không tự cam kết** rằng mọi lần thêm/sửa/xóa `OrderLine` sẽ luôn tăng version của Order.

Hành vi tăng version do collection/association changes có thể phụ thuộc Hibernate mapping, ownership và loại thao tác. Vì thế, nếu bất biến nghiệp vụ yêu cầu mọi thay đổi dòng hàng phải được phối hợp với trạng thái Order, cần thiết kế ranh giới nhất quán rõ ràng.

### 11.1. Ví dụ race giữa confirm và thêm dòng hàng

- Transaction A tải Order đang DRAFT.
- Transaction B confirm Order thành CONFIRMED, commit.
- Transaction A thêm một OrderLine dựa vào trạng thái DRAFT cũ.
- Nếu thao tác của A chỉ INSERT child mà không kiểm tra/increment version root đúng cách, `@Version` trên root có thể không phát hiện xung đột theo điều kiện nghiệp vụ.

Có thể cần update root, force increment root, lock root, predicate hoặc chiến lược transaction khác. Lựa chọn phụ thuộc thiết kế aggregate và database.

### 11.2. Mỗi entity có thể có version riêng

OrderLine có thể có `@Version` của chính nó khi cần bảo vệ cập nhật đồng thời trên một dòng hàng. Version của child không nhất thiết là version của root. Không nên coi tất cả entity được cascade như một hàng SQL duy nhất.

### 11.3. Quan hệ tới aggregate độc lập

Nếu Invoice tham chiếu Customer, việc sửa Invoice không cần mặc định tăng version của Customer. Những aggregate có vòng đời độc lập nên có chính sách concurrency tương ứng, không tăng version mọi entity liên quan một cách không cần thiết.

## 12. Bulk JPQL/HQL update không tự áp dụng @Version như dirty checking

Một giới hạn quan trọng: **bulk JPQL update** hoạt động theo tập hàng và bỏ qua vòng đời update từng managed entity.

Ví dụ:

~~~java
int changed = em.createQuery("""
    UPDATE InventoryItem i
    SET i.quantity = i.quantity - :amount
    WHERE i.id = :id
    """)
    .setParameter("amount", 3)
    .setParameter("id", itemId)
    .executeUpdate();
~~~

Câu lệnh này không tự áp dụng kiểm tra/increment version theo cách UPDATE do Hibernate dirty-check trên entity. Nó cũng có thể làm những entity đã managed trong persistence context bị stale.

### 12.1. Bulk update có điều kiện phiên bản

Với version số nguyên, có thể thiết kế command tường minh:

~~~java
int changed = em.createQuery("""
    UPDATE InventoryItem i
    SET i.quantity = i.quantity - :amount,
        i.version = i.version + 1
    WHERE i.id = :id
      AND i.version = :expectedVersion
      AND i.quantity >= :amount
    """)
    .setParameter("amount", amount)
    .setParameter("id", itemId)
    .setParameter("expectedVersion", expectedVersion)
    .executeUpdate();

if (changed != 1) {
    throw new ConcurrentUpdateException(
        "Dữ liệu đã đổi, không đủ hàng hoặc không tồn tại");
}
~~~

`ConcurrentUpdateException` là exception nghiệp vụ giả định. Lưu ý:

- `WHERE version = expectedVersion` từ chối bản cũ.
- `quantity >= amount` đảm bảo không âm trong chính UPDATE đó.
- Tăng version để các giao dịch ORM khác nhận ra thay đổi.
- Số hàng ảnh hưởng 0 không tự nói vì sao: version cũ, không đủ hàng hoặc bản ghi không tồn tại.
- Bulk SQL bỏ qua callback và các quy tắc domain method thông thường.
- Managed entity hiện có có thể stale; xử lý `flush()`/`clear()` hoặc dùng transaction độc lập khi phù hợp.

Đây là một command set-based có chủ đích, không phải lời khuyên chuyển mọi repository save thành bulk UPDATE.

### 12.2. Native SQL và batch jobs

Nếu một script ngoài Hibernate chạy:

~~~sql
UPDATE inventory_items
SET quantity = 5
WHERE id = 10;
~~~

nhưng không tăng version, transaction ORM đã đọc entity với version cũ có thể không phát hiện rằng quantity đã đổi.

Mọi đường ghi — JPA entity operations, JPQL bulk, native SQL, ETL, job nền, stored procedure hoặc trigger — cần tuân thủ cùng hợp đồng version, hoặc có cơ chế khác bảo đảm đồng thời.

### 12.3. Không tự phối hợp trigger và ORM version nếu chưa thiết kế

Có thể dùng database-generated version trong một số Hibernate mapping, nhưng khi đó phải cấu hình provider biết cách đọc generated version. Nếu cả trigger lẫn Hibernate tự tăng version không nhất quán, câu WHERE và state Java có thể bị sai.

Với bài toán thông thường, dùng numeric version do Hibernate quản lý thường đơn giản hơn.

## 13. Optimistic và pessimistic locking

| Tiêu chí | Optimistic `@Version` | Pessimistic lock |
| --- | --- | --- |
| Cách làm | Đọc trước, kiểm tra version khi ghi | Giữ lock database theo yêu cầu trong transaction |
| Xung đột | Phát sinh conflict, rollback/retry | Có thể chờ, timeout hoặc deadlock |
| Lock từ lúc đọc | Không mặc nhiên | Có thể có tùy lock mode |
| Phù hợp | Xung đột hiếm | Tranh chấp cao hoặc cần tuần tự hóa phần việc |
| Rủi ro | Retry tốn công, xung đột liên tục | Tắc nghẽn, tăng thời gian giữ lock |
| Bảo vệ invariant nhiều hàng | Không tự động | Cũng cần chọn đúng các row/range và isolation |

Ví dụ:

~~~java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Pessimistic write có thể khiến DB thực hiện truy vấn có lock tùy dialect và khả năng driver. Không nên dùng nó cho mọi lần đọc vì có thể làm giảm throughput.

### 13.1. Optimistic không có nghĩa DB không sử dụng lock

Khi UPDATE chạy, database có thể lấy row lock hoặc áp dụng MVCC/write conflict detection. “Lạc quan” ở đây nghĩa là ứng dụng không chủ động giữ lock từ lúc đọc trong suốt quá trình xử lý, mà phát hiện xung đột theo version khi ghi.

### 13.2. Hàng nóng và atomic updates

Một row counter bị hàng nghìn request cập nhật mỗi giây có thể gặp conflict liên tục với `@Version`. Một SQL atomic increment, hàng đợi xử lý lệnh hoặc phân vùng dữ liệu có thể phù hợp hơn tùy invariant. Cần đo tỷ lệ conflict trước khi thay chiến lược.

## 14. @Version không thay ràng buộc nghiệp vụ nhiều hàng

Giả sử hệ thống giới hạn tối đa 100 booking đang hoạt động cho một tài nguyên:

- Transaction A đếm 99 booking.
- Transaction B cũng đếm 99 booking.
- A INSERT booking mới.
- B INSERT booking mới.
- Mỗi booking mới là một entity khác nhau với version riêng.

`@Version` trên từng Booking **không tự ngăn tổng số booking thành 101**. Không có cùng một versioned row bị hai transaction cập nhật.

Đây là ví dụ về bất biến đa hàng/write skew tùy isolation. Cần một cơ chế bảo vệ điều kiện chung, như:

- Một row đại diện capacity/counter được cập nhật có điều kiện.
- Pessimistic lock trên tài nguyên chung.
- Database constraint phù hợp.
- Isolation cao hơn hoặc transaction serialization.
- Thiết kế aggregate/invariant theo cách khác.

Optimistic locking của một entity không biến mọi workflow nhiều hàng thành serializable transaction.

## 15. Timestamp version và độ chính xác

Một mapping timestamp version có thể được dùng khi cần tương thích schema:

~~~java
@Version
private java.sql.Timestamp version;
~~~

Tuy nhiên, timestamp có thể gặp vấn đề về độ phân giải, nguồn đồng hồ, chuyển đổi múi giờ/precision và khả năng phân biệt những cập nhật rất sát nhau. Hành vi còn phụ thuộc database và Hibernate version.

Khi không có lý do đặc biệt, numeric version thường dễ hiểu và dễ kiểm thử hơn. Không nên coi `updated_at` thông thường tương đương optimistic version nếu chưa bảo đảm chính xác semantics so sánh và tăng phiên bản.

## 16. Bổ sung version vào bảng đang chạy production

Nếu bảng chưa có cột version, cần migration dữ liệu. Ví dụ PostgreSQL:

~~~sql
ALTER TABLE inventory_items
ADD COLUMN version BIGINT;

UPDATE inventory_items
SET version = 0
WHERE version IS NULL;

ALTER TABLE inventory_items
ALTER COLUMN version SET NOT NULL;
~~~

Đây chỉ là quy trình backfill minh họa. Với bảng lớn, cân nhắc online migration, batching, lock, downtime và thứ tự triển khai ứng dụng.

### 16.1. Vấn đề khi có code cũ và code mới

Trong giai đoạn rollout, service mới dùng `@Version` nhưng một service cũ vẫn UPDATE cùng hàng mà **không tăng cột version**. Khi đó service mới có thể không nhận ra dữ liệu bị service cũ sửa.

Phải rà soát và chuyển đổi các đường ghi trước khi coi version protection đã bao phủ dữ liệu.

### 16.2. Schema validation chưa đủ

Hibernate validate có thể kiểm tra metadata cột, nhưng không chứng minh mọi native SQL/job đều tuân thủ version. Cần hợp đồng ghi và kiểm thử concurrent workflows.

## 17. Kiểm thử xung đột bằng hai transaction

Không thể kiểm tra concurrency đúng chỉ bằng hai biến trỏ cùng một entity trong một `EntityManager`. Nên có **hai persistence context/transaction độc lập**.

Một kịch bản integration test:

1. Persist InventoryItem quantity=10, commit.
2. Transaction A mở EntityManager A, tải item và version.
3. Transaction B mở EntityManager B, tải cùng item và version.
4. A giảm 3, flush/commit thành công.
5. B giảm 4 trên object đã đọc trước đó.
6. B flush/commit và nhận optimistic lock conflict.
7. Transaction mới đọc item, xác nhận quantity là 7 (nếu A là transaction duy nhất đã commit) và version được tăng đúng.
8. Kiểm tra transaction B rollback và không phát side effect trùng lặp.

Với Spring, cần bảo đảm test không vô tình chạy tất cả các bước trong một outer transaction mặc định khiến dữ liệu không commit hoặc persistence context bị chia sẻ. Có thể dùng `TransactionTemplate` hoặc transaction boundaries được kiểm soát để tạo race thật.

### 17.1. Test detached merge

Một test khác:

1. Load entity, kết thúc transaction để object thành detached.
2. Transaction thứ hai cập nhật entity và commit version mới.
3. Transaction thứ ba thử merge detached object cũ.
4. Kiểm tra conflict và rollback; dữ liệu mới không bị ghi đè.

### 17.2. Test bulk/native update

Nếu ứng dụng có SQL riêng cập nhật cùng bảng, cần test rằng nó phối hợp với version hoặc có chính sách concurrency khác. Đây là vùng dễ bị bỏ sót khi chỉ test repository.save().

### 17.3. Test HTTP precondition

GET trả ETag/version, một client khác cập nhật, sau đó request cũ gửi If-Match/expectedVersion cũ. API phải từ chối trước khi ghi đè; đừng chỉ kiểm thử `@Version` trong một transaction đơn.

## 18. Quan sát và tối ưu hiệu năng

Chi phí optimistic locking thường gồm một cột version, một điều kiện WHERE, việc cập nhật version và xử lý exception khi có conflict. Khi xung đột ít, chi phí này thường hợp lý so với giữ pessimistic lock lâu.

Nhưng ở các điểm ghi nóng, nên đo:

- Tỷ lệ `OptimisticLockException`/stale state.
- Số lần retry và thời gian retry.
- Latency, thời gian transaction và lock wait.
- Số UPDATE trên root/child.
- Tỷ lệ conflict vì thay đổi thực sự cùng field hay chỉ do cùng hàng.
- Tác động của batch job/native SQL ngoài ORM.

Nếu các thao tác nghiệp vụ độc lập đều làm tăng version của một entity lớn, có thể cân nhắc thu nhỏ aggregate boundary hoặc thay đổi mô hình, miễn là vẫn bảo vệ được invariant.

### 18.1. Retry phải hữu hạn

Không dùng vòng lặp retry vô hạn. Với operation có thể tính lại an toàn, cân nhắc số lần retry nhỏ, backoff và metrics. Nếu xung đột vẫn xảy ra, trả conflict/try-again thay vì làm nghẽn DB.

### 18.2. Không coi conflict là lỗi hệ thống luôn phải giấu

Nhiều conflict là hành vi cạnh tranh bình thường của một hệ thống nhiều người dùng. Thông báo rõ “dữ liệu đã thay đổi, cần tải lại” có thể đúng hơn tự retry và ghi đè thay đổi người khác.

## 19. Những hiểu lầm phổ biến

| Nhận định | Cách hiểu đúng |
| --- | --- |
| “`@Version` khóa row từ lúc SELECT.” | Nó chủ yếu phát hiện xung đột tại thời điểm ghi/kiểm tra version. |
| “`@Transactional` tự ngăn mọi lost update.” | Cần version, lock, isolation và SQL phù hợp. |
| “Version tăng mỗi khi gọi find/flush.” | Thường tăng khi thực sự có thay đổi persistent hoặc force increment. |
| “Client có thể sửa version để vượt xung đột.” | Version do provider quản lý, client version chỉ là expected metadata. |
| “Optimistic locking exception luôn xuất hiện tại save().” | Có thể xuất hiện lúc flush, merge hoặc commit tùy ngữ cảnh. |
| “Sau exception vẫn có thể tiếp tục transaction hiện tại.” | Thông thường rollback và bắt đầu transaction/context mới. |
| “Bulk JPQL tự kiểm tra `@Version`.” | Bulk DML không tự dùng cơ chế dirty checking/version increment như entity UPDATE. |
| “Native SQL thay đổi data thì version tự tăng.” | Không nếu SQL/trigger không thiết kế tăng version. |
| “Version của root luôn tăng khi child được sửa.” | Phụ thuộc mapping và cách cập nhật, không được giả định chung. |
| “Version tự bảo vệ mọi invariant đa hàng.” | Nó không tự giải quyết write skew hoặc constraint trải nhiều hàng. |
| “Đã có `@Version` thì form cũ tự bị từ chối.” | Cần client gửi version/ETag đã xem để chống stale form xuyên request. |
| “Flush thành công đồng nghĩa commit thành công.” | Flush và commit là hai giai đoạn khác nhau. |
| “Timestamp version và numeric version luôn như nhau.” | Timestamp có precision/clock concern; numeric thường đơn giản hơn. |
| “Optimistic lock tự chọn state đúng khi conflict.” | Nó phát hiện xung đột; domain quyết định hòa giải/retry. |

## 20. Quy trình áp dụng @Version

1. **Xác định các entity dễ có concurrent writers.** Xem mất cập nhật gây hậu quả gì.
2. **Chọn kiểu version thích hợp.** Numeric `Long`/`long` thường dễ quản lý.
3. **Thêm `@Version` đúng access strategy** và giữ version do Hibernate quản lý.
4. **Migration schema và dữ liệu cũ** để có cột version phù hợp.
5. **Load managed entity trong transaction**, áp dụng domain method/validation.
6. **Để Hibernate flush/commit** và kiểm tra version ở SQL.
7. **Rollback khi conflict**, không dùng tiếp context lỗi.
8. **Thiết kế phản hồi/retry** theo nghiệp vụ, tránh side effect trùng lặp.
9. **Đưa expectedVersion/ETag vào API** nếu cần bảo vệ form cũ.
10. **Rà soát các đường bulk/native SQL, job và trigger** để chúng tăng/kiểm tra version nhất quán.
11. **Xác định ranh giới aggregate/concurrency**: root, child, invariants đa hàng.
12. **Integration test với hai transaction thực** và đo conflict rate khi vận hành.

## 21. Bài tập thực hành

### Bài 1: Lost update

Hai transaction đọc stock=10. A trừ 3 rồi ghi 7; B trừ 4 từ snapshot cũ rồi ghi 6. Giải thích vì sao stock cuối sai. `WHERE version = oldVersion` làm tình huống khác đi như thế nào?

### Bài 2: SQL version predicate

~~~sql
UPDATE inventory_items
SET quantity = 7, version = 6
WHERE id = 10 AND version = 5;
~~~

Nếu hàng đang có version=6, câu UPDATE ảnh hưởng bao nhiêu hàng? Khi Hibernate kỳ vọng một hàng nhưng nhận 0, ứng dụng nên làm gì?

### Bài 3: Flush so với commit

~~~java
InventoryItem item = em.find(InventoryItem.class, id);
item.decrease(1);
em.flush();
// Sau đó transaction rollback.
~~~

Version/quantity mới đã commit chưa? Có nên dùng object Java cũ như trạng thái DB đáng tin sau rollback không?

### Bài 4: Detached merge

Một detached entity giữ version=2, trong khi DB đã lên version=3. Khi gọi `em.merge(detached)`, điều gì có thể xảy ra? Object detached có được reattach thành managed không?

### Bài 5: HTTP stale form

Client A GET item version=4; client B sửa lên version=5; A PATCH từ form cũ, server chỉ find() rồi sửa managed version=5. Vì sao `@Version` một mình có thể không từ chối A? Đề xuất expectedVersion hoặc If-Match.

### Bài 6: Bulk JPQL

~~~java
em.createQuery("""
    UPDATE InventoryItem i
    SET i.quantity = i.quantity - 2
    WHERE i.id = :id
    """)
    .setParameter("id", id)
    .executeUpdate();
~~~

Bulk DML có tự increment/check version theo cơ chế entity update không? Bổ sung điều kiện version, quantity và kiểm tra row count như thế nào?

### Bài 7: Root và child

Order có `@Version`, nhưng một transaction chỉ thêm OrderLine. Transaction khác confirm Order. Liệu version trên root có chắc chắn phát hiện xung đột không? Nếu invariant cấm thêm line sau confirm, có thể cần thêm cơ chế gì?

### Bài 8: Retry và email

Một transaction gửi email trước commit rồi gặp optimistic locking conflict. Service retry và gửi email lần hai. Vì sao version không ngăn email trùng? Nêu cách dùng outbox/idempotency/after-commit.

### Gợi ý

- **Bài 1:** B dùng snapshot cũ, làm mất thay đổi A; version predicate khiến UPDATE B không khớp khi version đã đổi.
- **Bài 2:** 0 hàng; rollback, tải lại dữ liệu và xử lý conflict theo nghiệp vụ.
- **Bài 3:** Flush không commit; rollback hủy thay đổi transactional, nên đọc lại trong context mới.
- **Bài 4:** Có thể nhận optimistic locking exception; merge tạo/tìm managed counterpart và không biến source detached thành managed.
- **Bài 5:** Transaction mới chỉ biết version=5; cần request mang version=4 và so sánh với state mới.
- **Bài 6:** Bulk DML cần kiểm tra/tăng version tường minh nếu muốn cùng semantics; dùng predicate và row count phù hợp.
- **Bài 7:** Không chắc; cân nhắc cập nhật/force increment root, locking hoặc transaction design theo invariant.
- **Bài 8:** Side effect ngoài DB không tự rollback; dùng cơ chế gửi sau commit, outbox và idempotency.

---

**Ghi nhớ:** `@Version` giúp Hibernate triển khai **optimistic locking**: khi ghi, provider kiểm tra phiên bản entity đã đọc và từ chối cập nhật âm thầm trên một phiên bản đã bị thay đổi. Nó bảo vệ khỏi một số lost updates nhưng **không tự hòa giải xung đột, không thay transaction, không bao phủ mọi bulk SQL, không đảm bảo invariant nhiều hàng và không tự biết client đang dùng form cũ** nếu API không mang version/ETag.
