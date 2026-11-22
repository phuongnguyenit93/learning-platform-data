# Ánh xạ thuộc tính phiên bản bằng @Version trong JPA

Trong các ứng dụng dùng Jakarta Persistence (JPA), hai người dùng hoặc hai tiến trình có thể đồng thời đọc và sửa cùng một entity. Nếu cả hai đều dựa trên dữ liệu cũ, thay đổi của một bên có thể ghi đè kết quả của bên kia mà ứng dụng không hề nhận biết. Đây là một dạng **lost update** — cập nhật bị mất trong môi trường đồng thời.

JPA hỗ trợ **khóa lạc quan (optimistic locking)** bằng cách ánh xạ một thuộc tính phiên bản với annotation **`@Version`**. Provider theo dõi giá trị phiên bản đã đọc và kiểm tra giá trị đó khi ghi thay đổi. Nếu bản ghi đã được transaction khác sửa trước, thao tác ghi không còn hợp lệ theo phiên bản cũ và có thể kết thúc bằng **`OptimisticLockException`**.

Ví dụ:

```java
import jakarta.persistence.*;

@Entity
@Table(name = "inventory_item")
public class InventoryItem {

    @Id
    private Long id;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected InventoryItem() {
    }

    public Long getId() {
        return id;
    }

    public int getAvailableQuantity() {
        return availableQuantity;
    }

    public Long getVersion() {
        return version;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }
        if (quantity > availableQuantity) {
            throw new IllegalStateException(
                "Not enough inventory"
            );
        }

        availableQuantity -= quantity;
    }
}
```

Điểm đặc biệt là ứng dụng **không cần tự tăng `version` trong phương thức `reserve`**. Khi entity được JPA quản lý và cập nhật đúng theo cơ chế entity-level, provider chịu trách nhiệm dùng phiên bản để phát hiện xung đột.

Bài học này thuộc chương **Khóa lạc quan** của module *Data Persistence Relational Access ORM JPA*, tập trung vào việc **ánh xạ thuộc tính phiên bản bằng `@Version`**: vị trí đặt annotation, kiểu dữ liệu phù hợp, cơ chế kiểm tra/increment, vòng đời entity, các lỗi thường gặp, bulk DML, transaction và kiểm thử.

> **Thông điệp quan trọng:** `@Version` là cơ chế phát hiện xung đột cho entity được quản lý theo JPA, **không phải khóa độc quyền một dòng dữ liệu**, không thay thế transaction/constraint của database, và không tự bảo vệ những cập nhật trực tiếp bằng SQL bên ngoài cơ chế versioned entity update.

---

## 1. Mục tiêu học tập

Sau khi hoàn thành bài này, bạn có thể:

1. Giải thích vì sao cần optimistic locking khi nhiều transaction sửa cùng một entity.
2. Đặt `@Version` đúng trên persistent field/property và ánh xạ tới cột database.
3. Chọn kiểu phiên bản số nguyên hoặc timestamp phù hợp với yêu cầu khả chuyển.
4. Hiểu quy trình **đọc version → so sánh khi cập nhật → tăng version**.
5. Nhận biết khác biệt giữa `@Version` và `@Column` bình thường, khóa bi quan, database constraint.
6. Phân biệt thời điểm JPA phát hiện version conflict ở `flush`, `commit` hoặc thao tác liên quan.
7. Xử lý `OptimisticLockException` và rollback/retry theo transaction boundary đúng.
8. Hiểu điều gì xảy ra với detached entity, `merge`, `remove` và entity đã được quản lý.
9. Biết rằng bulk JPQL/Criteria/native SQL **không tự áp dụng toàn bộ entity-level version handling**.
10. Thiết kế API/service có expected version, bảo mật tenant, xử lý conflict và kiểm thử đồng thời.

---

## 2. Vì sao phát sinh lost update?

Giả sử trong database có:

| id | sku | available_quantity | row_version |
|---:|---|---:|---:|
| 42 | BOOK-JPA | 10 | 7 |

Hai giao dịch đồng thời muốn giữ chỗ số lượng sản phẩm:

- Giao dịch A cần 3 sản phẩm.
- Giao dịch B cần 4 sản phẩm.

Nếu cả hai đều đọc `availableQuantity = 10`:

```text
Thời gian       Transaction A            Transaction B
----------------------------------------------------------------
T1              READ qty = 10, ver = 7
T2                                       READ qty = 10, ver = 7
T3              qty = 10 - 3 = 7
T4                                       qty = 10 - 4 = 6
T5              UPDATE qty = 7
T6                                       UPDATE qty = 6
----------------------------------------------------------------
Kết quả cuối nếu B ghi đè A: qty = 6
Kỳ vọng nếu cả hai phép giữ chỗ đều được chấp nhận: qty = 3
```

**Thay đổi của A đã bị mất**: database chỉ trừ 4 thay vì trừ cả 3 và 4. Trong thực tế, thứ tự flush, locking và isolation có thể thay đổi hành vi, nhưng đây là ví dụ điển hình về rủi ro khi không có cơ chế phát hiện stale state.

### 2.1. Cơ chế có @Version

Với version 7, provider có thể thực hiện một câu UPDATE có điều kiện tương đương:

```sql
UPDATE inventory_item
SET
    available_quantity = ?,
    row_version = ?
WHERE
    id = ?
    AND row_version = ?;
```

Nếu A cập nhật từ version 7 thành 8 thành công, B vẫn dựa trên version 7 sẽ không còn thỏa điều kiện phiên bản.

```text
Ban đầu: qty = 10, version = 7

Transaction A:
  đọc (10, 7)
  reserve(3) -> qty = 7
  UPDATE ... WHERE id=42 AND row_version=7
  cập nhật thành công
  database: qty = 7, version = 8

Transaction B:
  đã đọc (10, 7)
  reserve(4) -> qty = 6
  UPDATE ... WHERE id=42 AND row_version=7
  không còn row khớp version=7
  phát hiện optimistic conflict, rollback

Nếu B thử lại bằng transaction mới:
  đọc (7, 8)
  reserve(4) -> qty = 3
  UPDATE ... WHERE id=42 AND row_version=8
  thành công, database: qty = 3, version = 9
```

Đây là cơ chế **phát hiện xung đột**, không phải cơ chế để hai giao dịch tự động thành công đồng thời. B phải quyết định có retry, báo người dùng, hay hủy yêu cầu theo nghiệp vụ.

### 2.2. Optimistic locking không phải database row lock dài hạn

`@Version` không có ý nghĩa “đọc row là khóa row đến cuối transaction”. Khi đọc, nhiều giao dịch vẫn có thể thấy cùng một phiên bản. Konflikt được kiểm tra khi provider phải đảm bảo tính nhất quán version theo thao tác ghi/lock tương ứng.

Database vẫn có thể dùng các khóa nội bộ trong quá trình UPDATE để thực hiện điều kiện atomically. Điều đó không biến mô hình JPA optimistic locking thành chiến lược giữ khóa bi quan xuyên suốt toàn bộ thời gian người dùng xem biểu mẫu.

### 2.3. Khi nào phù hợp?

Optimistic locking thường hợp lý khi:

- Xung đột ghi tương đối hiếm.
- Nhiều thao tác đọc hơn thao tác ghi.
- Người dùng có thể chỉnh sửa biểu mẫu trong vài giây hoặc phút.
- Không muốn giữ database lock trong suốt thời gian người dùng suy nghĩ.
- Có cách báo/retry rõ khi dữ liệu đã thay đổi.
- Muốn bảo vệ entity state trước stale writes giữa các giao dịch.

Nếu nhiều writers liên tục cạnh tranh trên cùng một row (counter nóng, một kho tồn duy nhất, job claim queue...), optimistic conflict có thể xảy ra thường xuyên; khi đó cần đánh giá thiết kế cập nhật atomic, partitioning, database locking hoặc mô hình dữ liệu khác.

## 3. @Version là annotation nào?

Annotation chuẩn nằm trong:

```java
import jakarta.persistence.Version;
```

Dùng trên một persistent field:

```java
@Version
private Long version;
```

hoặc persistent property, khi entity sử dụng property-based access.

Provider dùng thuộc tính này để lưu **giá trị phiên bản hiện tại** của entity, phục vụ kiểm tra optimistic concurrency control và xác định entity nào đã bị thay đổi bởi một transaction khác.

### 3.1. @Version không tự là khóa chính

```java
@Id
private Long id;

@Version
private Long version;
```

Hai annotation có nhiệm vụ khác:

| Annotation | Vai trò |
|---|---|
| `@Id` | Xác định identity của entity |
| `@Version` | Theo dõi trạng thái phiên bản để phát hiện concurrent modification |
| `@Column` | Mô tả mapping tới database column |
| `@GeneratedValue` | Chỉ định chiến lược sinh primary key |
| `@Temporal` | Mô tả kiểu thời gian cho một số Java legacy date/calendar mappings, không phải cách tạo version |

Ví dụ entity `InventoryItem#42` có thể lần lượt ở version 7, 8, 9... nhưng vẫn là **cùng một persistent identity id=42**.

### 3.2. @Version không phải mã sửa đổi của user

Không dùng version như “số lần bấm nút Lưu của người dùng” hay “revision đã được business phê duyệt”. Provider có thể thực hiện flush/check/increment theo vòng đời transaction và mapping; version thường tăng khi có managed entity update, không nhất thiết bằng số sự kiện nghiệp vụ.

Nếu domain cần `approvedRevision`, `documentRevision` hoặc mã phiên bản công bố cho khách, có thể tạo field nghiệp vụ khác. Đừng trộn nó với cơ chế optimistic locking.

## 4. Ánh xạ @Version vào cột database

Một mapping phổ biến:

```java
@Entity
@Table(name = "inventory_item")
public class InventoryItem {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "sku", nullable = false)
    private String sku;

    @Column(name = "available_quantity", nullable = false)
    private int availableQuantity;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected InventoryItem() {
    }
}
```

Schema minh họa:

```sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(64) NOT NULL UNIQUE,
    available_quantity INTEGER NOT NULL,
    row_version BIGINT NOT NULL
);
```

Tên `row_version` được chọn để tránh nhầm với version của ứng dụng, phiên bản sản phẩm hay một keyword/cột tên `version` đã tồn tại. Không bắt buộc mọi dự án phải dùng chính tên này.

### 4.1. @Column(nullable=false) có ý nghĩa gì?

`nullable = false` biểu đạt rằng cột version không nên có SQL NULL đối với row đã được lưu. Đây là một ràng buộc hữu ích:

- Tránh trạng thái phiên bản không rõ ràng ở database.
- Phù hợp với chiến lược kiểm tra equality của version.
- Giúp schema migration và dữ liệu legacy được chuẩn hóa.

Nhưng `@Column(nullable = false)` **không phải công cụ migrate schema** trong mọi môi trường. Nếu database hiện tại chứa NULL, phải viết migration và xử lý dữ liệu trước khi bật `NOT NULL`.

### 4.2. Có nên đặt DEFAULT 0?

Một số schema đặt:

```sql
row_version BIGINT NOT NULL DEFAULT 0
```

để thuận tiện với các thao tác SQL ngoài JPA. Nhưng không được mặc định database DEFAULT sẽ phối hợp đúng với mọi provider-generated INSERT và version initialization.

Khi entity được persist qua JPA, provider thường chủ động gán giá trị version ban đầu. Mức khởi tạo cụ thể có thể phụ thuộc provider, kiểu dữ liệu và cơ chế mapping. **Đừng hard-code ý nghĩa “new entity luôn version 0” vào business contract nếu chưa kiểm chứng stack thực tế.**

### 4.3. Không đặt insertable=false hoặc updatable=false tùy tiện

Tránh:

```java
@Version
@Column(name = "row_version", updatable = false)
private Long version;
```

Version là field **do JPA provider quản lý** trong cập nhật thông thường. Đánh dấu column không được cập nhật có thể xung đột cơ chế tăng version hoặc gây hành vi không mong muốn theo provider. Tương tự, `insertable=false` chỉ nên cân nhắc nếu có một chiến lược version initialization được hỗ trợ và kiểm chứng rõ.

Với mapping JPA version chuẩn, thường để mặc định insertable/updatable và để provider quản lý.

## 5. Kiểu dữ liệu nào phù hợp với @Version?

JPA hỗ trợ một tập kiểu phiên bản cơ bản. Khi hướng tới mapping khả chuyển giữa các JPA providers, nên ưu tiên các kiểu số nguyên phổ biến:

| Java type | Đặc điểm | Lưu ý |
|---|---|---|
| `int` / `Integer` | Phiên bản số nguyên 32-bit | Có giới hạn, cần cân nhắc vòng đời rất dài |
| `long` / `Long` | Phiên bản số nguyên 64-bit | Thường là lựa chọn thực tế, biên độ lớn |
| `short` / `Short` | Phiên bản 16-bit | Biên độ nhỏ, ít phù hợp với row được cập nhật nhiều |
| `java.sql.Timestamp` | Phiên bản theo timestamp | Có rủi ro precision/độ phân giải, phụ thuộc stack |
| Kiểu khác như một số `java.time` types | Có thể được hỗ trợ trong một số spec/provider/version | Kiểm tra đặc tả và provider được dự án hỗ trợ |

Danh sách portable chính xác cần được đối chiếu với **phiên bản Jakarta Persistence** của dự án; không suy luận rằng một kiểu mới được provider A hỗ trợ thì provider B bắt buộc hỗ trợ giống vậy.

### 5.1. Vì sao thường chọn Long?

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Ưu điểm:

- Cú pháp và ý nghĩa dễ hiểu.
- Tránh rủi ro precision của timestamp.
- Khoảng giá trị rộng hơn short/int.
- Tương thích tốt với nhiều database số nguyên.
- Dễ truyền expectedVersion giữa các lớp service/DTO khi cần.

**Long là lựa chọn tiện dụng**, không phải bắt buộc theo domain. Nếu dự án có chuẩn khác, cần thống nhất trên toàn persistence unit và database schema.

### 5.2. Tại sao timestamp version cần cân nhắc?

Giả sử version dùng `Timestamp`:

```java
@Version
@Column(name = "row_version")
private java.sql.Timestamp version;
```

Một số hệ thống dùng timestamp để xác định bản cập nhật mới. Tuy nhiên:

- Database có độ chính xác timestamp khác nhau.
- JDBC driver có thể làm tròn/cắt phần thập phân giây.
- Nhiều cập nhật diễn ra trong cùng một đơn vị độ phân giải.
- Đồng hồ ứng dụng/database có thể khác nhau.
- Provider quyết định cách khởi tạo và so sánh timestamp version.

Do đó khi mục tiêu chính là **counter optimistic locking dễ hiểu và bền vững**, numeric `Long` thường là lựa chọn đơn giản hơn.

### 5.3. Không biến version thành kiểu String tùy ý

```java
@Version
private String version;
```

Không phải lựa chọn portable thông thường. Nếu nghiệp vụ cần một ETag hoặc revision token kiểu String, hãy tạo contract API riêng từ version/ID/hash phù hợp, không yêu cầu `@Version` tự làm String token.

### 5.4. Numeric overflow có đáng lo không?

Một field `Short` có phạm vi nhỏ hơn `Integer` và `Long`. Với row được cập nhật nhiều, việc tới giới hạn kiểu số có thể trở thành rủi ro. Đừng dùng `Short` chỉ để tiết kiệm hai bytes khi đồng thời yêu cầu trạng thái version tin cậy trong thời gian dài.

## 6. Có thể khai báo bao nhiêu @Version?

Trong một entity class/hierarchy, nguyên tắc portable là **một version attribute** dùng để quản lý optimistic locking.

Ví dụ hợp lý:

```java
@MappedSuperclass
public abstract class VersionedEntity {

    @Version
    @Column(name = "row_version", nullable = false)
    protected Long version;

    public Long getVersion() {
        return version;
    }
}
```

Entity kế thừa:

```java
@Entity
@Table(name = "inventory_item")
public class InventoryItem extends VersionedEntity {

    @Id
    private Long id;

    @Column(name = "available_quantity")
    private int availableQuantity;

    protected InventoryItem() {
    }
}
```

Ở đây `InventoryItem` kế thừa version attribute từ `@MappedSuperclass`.

### 6.1. Đừng khai báo thêm một @Version trong subclass

Không nên:

```java
@MappedSuperclass
class VersionedBase {
    @Version
    Long version;
}

@Entity
class SpecialItem extends VersionedBase {
    @Version
    Long secondaryVersion; // Không phù hợp như một hierarchy chuẩn.
}
```

Hai version attributes không tự tăng độ an toàn. Chúng khiến mapping không phù hợp contract portable và khó xác định provider phải dùng phiên bản nào.

### 6.2. Version ở primary table

Với mapping JPA portable, version attribute nên nằm ở **primary table của entity**. Không tùy tiện đặt cột version vào một secondary table qua `@Column(table = "...")` rồi kỳ vọng mọi provider xử lý đúng.

Ví dụ entity có `@SecondaryTable` nhưng version ở bảng chính là thiết kế đơn giản hơn:

```java
@Entity
@Table(name = "account")
@SecondaryTable(name = "account_profile")
public class Account {

    @Id
    private Long id;

    @Version
    @Column(name = "row_version")
    private Long version;

    @Column(table = "account_profile", name = "bio")
    private String biography;
}
```

Cập nhật field ở secondary table có những chi tiết về SQL/version handling cần kiểm chứng theo provider/mapping, nhưng version attribute vẫn được đặt tại primary table cho tính portable.

### 6.3. @Version trong @Embeddable?

Không coi việc đặt `@Version` bên trong một embeddable component là thiết kế portable chuẩn. Version nên được khai báo như một persistent attribute thích hợp ở entity hoặc mapped superclass, theo cấu trúc mapping được JPA hỗ trợ.

## 7. Field access và property access: đặt @Version đúng nơi

JPA có hai kiểu truy cập chính.

**Field access** khi mapping annotations như `@Id` đặt trên field:

```java
@Entity
public class Item {

    @Id
    private Long id;

    @Version
    private Long version;

    protected Item() {
    }

    public Long getVersion() {
        return version;
    }
}
```

Provider làm việc trực tiếp với persistent fields theo access strategy.

**Property access** khi mapping annotations đặt trên getter:

```java
@Entity
@Access(AccessType.PROPERTY)
public class PropertyItem {

    private Long id;
    private Long version;

    protected PropertyItem() {
    }

    @Id
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @Version
    @Column(name = "row_version")
    public Long getVersion() {
        return version;
    }

    protected void setVersion(Long version) {
        this.version = version;
    }
}
```

Mục đích là minh họa property-based mapping; setter accessibility và cách provider gọi setter cần phù hợp JPA/provider/runtime mà ứng dụng chọn.

### 7.1. Tránh trộn annotation tùy tiện

Không nên đặt `@Id` trên field nhưng `@Version` trên getter **chỉ do quên** mà không cấu hình access rõ ràng. Có thể khiến provider không nhận mapping như bạn nghĩ.

Nếu thật sự cần mixed access, hãy sử dụng `@Access` với ý định rõ ràng và kiểm chứng. Cách dễ bảo trì hơn là giữ nhất quán field/property access trong từng entity hierarchy.

### 7.2. Getter version có thể public nhưng setter không nên là API nghiệp vụ

Bài học không khuyến khích:

```java
public void setVersion(Long version) {
    this.version = version;
}
```

như một method được service tự do gọi.

Ngay cả khi provider cần setter vì property access, đó là chi tiết persistence mapping. Business code **không nên tự tăng/giảm/sửa version**. Có thể giới hạn phạm vi setter phù hợp provider/runtime hoặc giữ nó không xuất hiện trong public domain API.

## 8. Ai chịu trách nhiệm khởi tạo và tăng version?

Khi entity dùng `@Version`, **JPA provider quản lý version value** theo cơ chế persistence lifecycle.

Một service thông thường:

```java
@Transactional
public void reserveStock(long itemId, int requestedQuantity) {
    InventoryItem item =
        entityManager.find(InventoryItem.class, itemId);

    if (item == null) {
        throw new IllegalArgumentException(
            "Inventory item not found"
        );
    }

    item.reserve(requestedQuantity);
}
```

Ở đây `@Transactional` là annotation Spring hoặc transaction framework tương ứng, **không phải annotation JPA chuẩn**. Code được gọi trong transaction ghi có persistence context hợp lệ.

Sau `reserve`:

1. Managed entity có `availableQuantity` mới trong memory.
2. Provider phát hiện dirty state tại flush.
3. Provider tiến hành optimistic check/increment theo mapping.
4. Nếu phiên bản database khớp, UPDATE được áp dụng.
5. Nếu không khớp, provider báo optimistic conflict theo contract tương ứng.

### 8.1. Không viết version++ trong setter/domain method

Sai:

```java
public void reserve(int quantity) {
    availableQuantity -= quantity;
    version++; // Không nên tự quản lý @Version.
}
```

Provider đã quản lý version. Tự tăng có thể làm giá trị expected version bị lệch, khiến điều kiện UPDATE sai hoặc xung đột không mong muốn.

### 8.2. Không “reset version” khi save

Sai:

```java
item.setVersion(0L);
entityManager.merge(item);
```

Đây không phải cách buộc một bản detached cũ ghi đè database. Nó làm méo optimistic locking contract, có thể gây lỗi hoặc che giấu một vấn đề thiết kế.

### 8.3. Có nên gán version trong constructor tạo mới?

Thông thường không cần:

```java
public InventoryItem(Long id, int quantity) {
    this.id = id;
    this.availableQuantity = quantity;
    // Không gán version.
}
```

Provider quản lý version khi entity được persist. Một số chiến lược nhận diện new/detached entities có thể dựa vào version state, nên **đừng gán version thủ công như một mẹo nhận diện entity mới**.

## 9. SQL mà provider có thể phát sinh

Giả sử row hiện có:

```text
id = 42
available_quantity = 10
row_version = 7
```

Lệnh managed entity update có thể tạo SQL tương đương:

```sql
UPDATE inventory_item
SET
    available_quantity = 7,
    row_version = 8
WHERE
    id = 42
    AND row_version = 7;
```

Đây là **SQL minh họa cơ chế**, không phải một chuỗi SQL bắt buộc JPA provider phải sinh y hệt. Provider có thể:

- Dùng parameter placeholders.
- Sắp thứ tự cột khác.
- Thêm những cột persistent khác vào SET.
- Dùng version expression/driver-specific SQL.
- Tách thao tác theo secondary tables/inheritance.
- Thực hiện check vào thời điểm flush/commit khác nhau.
- Sử dụng các kỹ thuật SQL phù hợp dialect.

Điểm cốt lõi là **đảm bảo một concurrent update đã làm version thay đổi sẽ không bị ghi đè im lặng theo entity version cũ**.

### 9.1. Khi database báo 1 row được update

Nếu điều kiện ID+version khớp và database thực hiện UPDATE, provider có đủ thông tin để coi optimistic check thành công tại bước ấy, theo những kiểm tra khác có liên quan.

### 9.2. Khi database báo 0 row được update

Nếu row không còn version 7 hoặc đã bị xóa, WHERE không match. Provider có thể kết luận rằng entity đang stale và báo `OptimisticLockException`.

Không nên tự phụ thuộc vào số row-count nội bộ trong JDBC của provider để dựng cơ chế retry vì provider đã chuyển nó thành JPA exception với semantics rõ hơn.

### 9.3. Khi row tồn tại nhưng giá trị mới giống cũ

Nếu managed entity không có thay đổi persistent nào, provider có thể không gửi UPDATE, và version không cần tăng chỉ vì bạn gọi getter hoặc đọc entity lại. Khi transaction chỉ đọc, đừng giả định mỗi transaction làm version tăng.

## 10. Timeline hai transaction cùng sửa entity

Một ví dụ đầy đủ:

```text
Database: Item#42 (quantity=10, version=7)

                Transaction A                   Transaction B
                ----------------               ----------------
T1              emA.find(42)
                -> quantity=10, version=7

T2                                              emB.find(42)
                                                -> quantity=10, version=7

T3              reserve(3)
                -> quantity=7 trong emA

T4                                              reserve(4)
                                                -> quantity=6 trong emB

T5              emA.flush()
                -> optimistic UPDATE thành công
                -> version=8 theo quản lý của provider

T6              emA.commit()
                -> database có qty=7, version=8

T7                                              emB.flush() hoặc commit()
                                                -> optimistic check thất bại
                                                -> OptimisticLockException

T8                                              rollback transaction B

T9                                              Nếu nghiệp vụ cho phép:
                                                dùng transaction C mới,
                                                reload qty=7/version=8,
                                                đánh giá reserve(4) lần nữa
```

**Lưu ý về isolation và thời điểm:** Không phải mọi database/provider đều phát hiện conflict ở đúng bước T7; có trường hợp phải chờ lock, báo deadlock/timeout hoặc ném exception lúc commit. Dù khác thời điểm/kỹ thuật, ứng dụng phải xem thao tác ghi stale là một outcome cần xử lý, không mặc định cả A và B đều được chấp nhận.

### 10.1. Optimistic locking phát hiện xung đột, không tự cộng dồn

Nếu hai người đều chỉnh tên sản phẩm:

- A đặt tên = “JPA Handbook”.
- B đặt tên = “Jakarta Persistence Guide”.

Với version, một người cập nhật trước có thể thắng và người còn lại nhận conflict. JPA **không tự trộn hai thay đổi** thành một tên đúng.

Nếu hai phép cộng tồn kho có thể gộp về mặt nghiệp vụ, ứng dụng cần retry/recompute trên state mới, không đơn giản ghi lại snapshot cũ.

### 10.2. Một entity version không phải khóa cho cả database

`@Version` trên Item#42 không ngăn Transaction B sửa một row Item#43 độc lập. Nó phát hiện xung đột theo phạm vi persistent identity và mapping version liên quan.

Với invariants trải trên nhiều rows, cần thêm ràng buộc database, isolation, locking hoặc aggregate design.

## 11. Khi nào version được kiểm tra?

Provider có thể kiểm tra version ở những thời điểm khác nhau tùy thao tác:

- Khi flush một managed dirty entity.
- Khi transaction commit kích hoạt flush.
- Trong lúc `merge` nhận một detached entity có version cũ, hoặc muộn hơn tại flush/commit.
- Khi remove một versioned entity.
- Khi áp dụng `LockModeType.OPTIMISTIC` hoặc `OPTIMISTIC_FORCE_INCREMENT`.
- Theo cơ chế check khác của provider/transaction synchronization.

Vì vậy không nên code:

```java
try {
    entityManager.merge(detached);
    // merge không ném => chắc chắn không conflict.
} catch (OptimisticLockException ex) {
    // ...
}
```

rồi bỏ qua khả năng exception xuất hiện **khi flush hoặc commit**.

### 11.1. flush không phải commit

```java
entityManager.flush();
```

yêu cầu đồng bộ pending changes tới database trong transaction. Nó có thể làm optimistic conflict xuất hiện sớm, nhưng:

- Flush thành công **không đảm bảo** commit sẽ thành công.
- Transaction có thể rollback sau flush.
- Có thể còn constraints/locks khác chưa được xác nhận hoàn toàn.
- Side effects ngoài database không được tự động rollback.

### 11.2. Đừng gửi email khi flush vừa thành công

Sai về thứ tự nghiệp vụ:

```java
item.reserve(1);
entityManager.flush();
emailClient.sendConfirmation();
```

Một thao tác database khác có thể làm transaction rollback sau đó. Email đã gửi không quay lại được.

Với quy trình có notification/payment/event, cân nhắc transactional outbox hoặc cơ chế after-commit thích hợp và có idempotency.

## 12. OptimisticLockException là gì?

Exception chuẩn JPA:

```java
import jakarta.persistence.OptimisticLockException;
```

Nó thông báo rằng thao tác optimistic locking không thể hoàn tất vì một xung đột phù hợp với contract provider/transaction.

### 12.1. Không bắt rồi tiếp tục như không có chuyện gì

Tránh:

```java
try {
    entityManager.flush();
} catch (OptimisticLockException ex) {
    log.warn("Conflict", ex);
    // Tiếp tục ghi thêm vào cùng transaction như thành công.
}
```

Khi provider báo optimistic conflict, transaction có thể bị đánh dấu **rollback-only**. Ngay cả khi exception được catch, tiếp tục làm việc trong persistence context/transaction đó có thể không hợp lệ.

Cách xử lý thông thường:

1. Cho transaction hiện tại rollback.
2. Không tái sử dụng stale managed state để ghi lại.
3. Nếu có lý do retry, mở transaction/persistence context mới.
4. Đọc state mới nhất phù hợp.
5. Chạy lại **business decision**, không chỉ replay SQL/state cũ.
6. Có giới hạn số lần retry và quan sát xung đột.

### 12.2. Không trộn xung đột lạc quan với mọi lỗi DB

Một `OptimisticLockException` khác với:

- Vi phạm UNIQUE constraint.
- Foreign key constraint failure.
- Connection timeout.
- Deadlock/lock timeout.
- SQL syntax error.
- Transaction manager misconfiguration.

Những lỗi đó cũng có thể làm transaction thất bại, nhưng **không phải tất cả đều có nghĩa version stale**. Retry policy phải phân loại lỗi đúng, không retry vô điều kiện mọi `PersistenceException`.

### 12.3. Exception có thể xảy ra ở transaction boundary của Spring

Với Spring:

```java
@Transactional
public void updateStock(...) {
    InventoryItem item = em.find(...);
    item.reserve(...);
    // Có thể chưa flush tại đây.
}
```

Ngay khi method body chạy hết, transaction interceptor còn cần commit. Optimistic conflict có thể xuất hiện **trong quá trình hoàn tất transaction**, trước khi caller nhận thành công cuối cùng.

Vì vậy service/controller không nên xem “method body đã return” là bằng chứng commit được chấp nhận.

## 13. Thay đổi entity managed: cách @Version được áp dụng tự nhiên

Một service thực tế:

```java
@Service
public class InventoryService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserve(long itemId, int requestedQuantity) {
        InventoryItem item =
            em.find(InventoryItem.class, itemId);

        if (item == null) {
            throw new ItemNotFoundException(itemId);
        }

        item.reserve(requestedQuantity);

        // Không gọi item.setVersion(...).
        // Dirty checking và optimistic version handling
        // được JPA thực hiện khi flush/commit.
    }
}
```

Đoạn code trên dùng Spring (`@Service`, `@Transactional`, `@PersistenceContext` tích hợp) cùng JPA. `ItemNotFoundException` là exception nghiệp vụ minh họa do dự án định nghĩa.

Nếu entity được quản lý trong transaction ghi, thay đổi persistent field được JPA phát hiện theo dirty checking.

### 13.1. Có cần gọi em.merge(item) không?

Nếu `item` được trả bởi `em.find` trong cùng persistence context và vẫn managed, thường **không cần**:

```java
em.merge(item);
```

để JPA nhận ra thay đổi. Entity đã managed; provider theo dõi state của nó.

Gọi merge không cần thiết có thể làm code khó hiểu, đặc biệt khi lẫn managed/detached objects.

### 13.2. Có cần gọi em.flush() thủ công không?

Không bắt buộc trong mọi use case. JPA thường flush theo transaction lifecycle khi cần. Nhưng nếu service cần phát hiện constraint/version conflict trước một bước database khác, có thể flush tại một mốc có chủ đích.

Tuy nhiên, `flush` không phải commit; đừng dùng nó như bằng chứng đã hoàn tất nghiệp vụ.

### 13.3. Nếu không thay đổi field nào thì sao?

`em.find` chỉ để đọc:

```java
InventoryItem item = em.find(InventoryItem.class, itemId);
System.out.println(item.getAvailableQuantity());
```

không tự làm `@Version` tăng. Optimistic locking có thể được dùng cho kiểm tra khi đọc bằng LockMode, nhưng annotation không biến mọi SELECT thành UPDATE.

## 14. Detached entity và merge: phiên bản đi cùng dữ liệu cũ

Một entity có thể bị **detached** sau khi EntityManager đóng:

```java
InventoryItem detached;

EntityManager em1 = emf.createEntityManager();
try {
    detached = em1.find(InventoryItem.class, 42L);
} finally {
    em1.close();
}
```

`detached` giữ ID, availableQuantity và version từ lần đọc.

Giả sử:

```text
detached.version = 7
database.version = 8
```

vì một transaction khác đã cập nhật row.

Nếu ứng dụng đưa `detached` vào một transaction khác:

```java
EntityManager em2 = emf.createEntityManager();
EntityTransaction tx = em2.getTransaction();

tx.begin();
try {
    InventoryItem managedCopy = em2.merge(detached);
    tx.commit();
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
} finally {
    em2.close();
}
```

JPA phải bảo vệ versioned state theo contract optimistic locking. Khi version stale, `merge`, flush hoặc commit có thể dẫn tới optimistic conflict.

### 14.1. merge trả managed instance

Lưu ý:

```java
InventoryItem managedCopy = em.merge(detached);
```

`managedCopy` là instance managed được trả về; `detached` không tự trở thành managed object.

Nếu sau đó tiếp tục sửa `detached` và mong JPA theo dõi, đó là nhầm lẫn lifecycle.

### 14.2. Không “xóa version” trên DTO rồi merge như entity mới

Nếu request DTO không có version nhưng code tạo một entity với ID cũ và version null rồi `merge`, bạn đã mất thông tin cần thiết để biểu diễn expected version. Hành vi new/detached detection có thể khác theo provider, thậm chí dẫn đến INSERT/exception không mong muốn.

Giải pháp tốt hơn cho API là nhận DTO có ID/expectedVersion, **load managed entity** rồi áp cập nhật theo một concurrency policy rõ ràng.

### 14.3. Detached entity không đồng nghĩa version vô ích

Ngược lại, đây là một lợi ích quan trọng của version: entity detached có thể mang dấu thời gian/concurrency token logic từ lúc đọc và giúp phát hiện việc database đã thay đổi trước khi áp dữ liệu cũ.

## 15. Thiết kế DTO cập nhật có expectedVersion

Một API chỉnh sửa sản phẩm có thể trả:

```json
{
  "id": 42,
  "sku": "BOOK-JPA",
  "availableQuantity": 10,
  "version": 7
}
```

Khi client gửi lệnh cập nhật, có thể kèm:

```json
{
  "id": 42,
  "requestedQuantity": 3,
  "expectedVersion": 7
}
```

Bộ DTO Java:

```java
public record ReserveStockRequest(
    Long itemId,
    int requestedQuantity,
    Long expectedVersion
) { }
```

Tại service:

```java
@Transactional
public void reserve(ReserveStockRequest request) {
    InventoryItem item =
        em.find(InventoryItem.class, request.itemId());

    if (item == null) {
        throw new ItemNotFoundException(request.itemId());
    }

    if (!Objects.equals(
            item.getVersion(),
            request.expectedVersion())) {
        throw new VersionConflictException(
            "Inventory changed since the client read it"
        );
    }

    item.reserve(request.requestedQuantity());

    // @Version vẫn là tuyến bảo vệ ở flush/commit.
}
```

Yêu cầu thêm `import java.util.Objects;`. `VersionConflictException` là domain exception do dự án định nghĩa.

### 15.1. Vì sao check version bằng Java vẫn chưa đủ?

Có thể xảy ra:

```text
Service A: load version=7
Service A: kiểm tra expectedVersion=7 -> đúng
Service B: update version=8 và commit
Service A: reserve(...)
Service A: flush -> conflict
```

Kiểm tra sớm giúp tạo thông báo nghiệp vụ thân thiện, nhưng **không thay thế optimistic check atomic khi ghi**. `@Version` vẫn cần để phát hiện thay đổi xảy ra giữa check và flush.

### 15.2. Phân biệt concurrency token với dữ liệu không đáng tin

Client có thể gửi `expectedVersion` đã bị sửa. Nó chỉ là **điều kiện kỳ vọng**: server phải đối chiếu với state và authorization đáng tin. Không coi version do client gửi là bằng chứng quyền sở hữu item hoặc tenant.

### 15.3. Không bao giờ bỏ authorization khỏi query/update

Nếu ứng dụng nhiều tenant, service phải bảo đảm item thuộc tenant được phép. `@Version` chỉ giải quyết xung đột về trạng thái entity, **không xác nhận quyền truy cập**.

## 16. REST API: 409 Conflict, 412 Precondition Failed và ETag

Khi một client gửi phiên bản cũ:

- Có thể trả **409 Conflict** nếu API mô tả xung đột nghiệp vụ.
- Có thể dùng **ETag/If-Match** theo HTTP conditional request và trả **412 Precondition Failed** nếu precondition không khớp.

Ví dụ ý tưởng:

```http
GET /inventory/items/42

HTTP/1.1 200 OK
ETag: "item-42-v7"

{
  "id": 42,
  "availableQuantity": 10
}
```

Client cập nhật:

```http
PATCH /inventory/items/42
If-Match: "item-42-v7"

{
  "reserveQuantity": 3
}
```

Nếu DB đã chuyển sang version 8, server không được áp patch như một bản cập nhật không điều kiện dựa trên version 7.

### 16.1. ETag không đồng nhất với JPA version

ETag là contract HTTP; JPA `@Version` là persistence concurrency token. Có thể xây ETag dựa trên version và identity, nhưng cần xác định:

- ETag mô tả phiên bản của **representation** nào?
- Có bao gồm dữ liệu association không?
- Cách encode có lộ thông tin nội bộ không?
- Có xử lý strong/weak ETag semantics đúng chuẩn HTTP không?
- Có đồng bộ với cache và serialization không?

Không hứa rằng chỉ thêm `@Version` sẽ tự động tạo một ETag hợp lệ cho mọi REST endpoint.

### 16.2. Idempotency vẫn cần thiết cho side effects

Một request reserve tồn kho có thể được retry sau timeout. Nếu lần đầu đã commit nhưng response mất, retry thiếu idempotency key có thể giữ chỗ lần thứ hai trên **version mới**.

`@Version` không tự mang lại “exactly once processing” cho toàn bộ workflow. Cần idempotency key, unique business constraint, event/outbox hoặc một cơ chế đồng bộ khác khi nghiệp vụ yêu cầu.

## 17. @Version và EntityManager.remove

Với entity versioned, việc xóa một managed entity cũng cần tôn trọng optimistic consistency.

```java
@Transactional
public void deleteItem(long id) {
    InventoryItem item = em.find(InventoryItem.class, id);

    if (item == null) {
        return;
    }

    em.remove(item);
}
```

Nếu transaction khác đã sửa hoặc xóa row sau khi item được đọc, provider phải xử lý stale state theo optimistic locking contract khi thực hiện remove/flush/commit tương ứng.

Một DELETE minh họa:

```sql
DELETE FROM inventory_item
WHERE id = ?
  AND row_version = ?;
```

Provider không bắt buộc sinh đúng SQL này trong mọi mapping; ý nghĩa là không được xóa im lặng một version đã thay đổi mà lệnh optimistic removal được phép bảo vệ.

### 17.1. Không đánh đồng remove với bulk DELETE

```java
em.remove(item);
```

khác:

```java
em.createQuery(
    "delete from InventoryItem i where i.id = :id"
)
.setParameter("id", id)
.executeUpdate();
```

Bulk JPQL DELETE không tự thực hiện entity-level optimistic version checking/callbacks/cascade giống như xóa managed entity từng phần tử. Nếu cần điều kiện version trong bulk DELETE, phải thiết kế nó tường minh.

## 18. @Version và LockModeType.OPTIMISTIC

Ngoài việc tự động bảo vệ các versioned entity updates, JPA cho phép yêu cầu optimistic lock có chủ đích.

Ví dụ:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    itemId,
    LockModeType.OPTIMISTIC
);
```

hoặc:

```java
em.lock(item, LockModeType.OPTIMISTIC);
```

Mục đích là yêu cầu kiểm tra optimistic version theo lock mode khi làm việc với entity, ngay cả khi transaction không nhất thiết trực tiếp sửa persistent field của entity ấy.

### 18.1. Vì sao cần optimistic lock khi chỉ đọc?

Giả sử một transaction:

1. Đọc một Order.
2. Đọc một số entity khác để tính quyền/quy tắc.
3. Ghi một bản ghi tổng hợp phụ thuộc trạng thái của Order.
4. Muốn phát hiện Order bị transaction khác thay đổi trong quá trình đó.

Một optimistic lock trên Order có thể giúp xác minh version không bị thay đổi theo contract lock mode của JPA trong transaction phù hợp.

Nhưng hãy cân nhắc **phạm vi invariant**: nếu kết quả còn phụ thuộc nhiều rows/aggregate khác không được version-checked, lock một Order đơn lẻ không tự bảo vệ mọi dữ liệu liên quan.

### 18.2. Khi nào lock được kiểm tra?

Một lời gọi `lock`/`find` với optimistic lock mode có thể dẫn tới kiểm tra ở thời điểm gọi, flush hoặc commit tùy provider/contract. Không nên khẳng định cứ gọi `em.lock(item, OPTIMISTIC)` là có SQL update ngay tại dòng code đó.

### 18.3. Transaction là điều kiện quan trọng

Các lock modes yêu cầu transaction context thích hợp. Nếu gọi optimistic lock ngoài transaction hợp lệ, có thể gặp `TransactionRequiredException` theo API/operation.

Không dùng `LockModeType.OPTIMISTIC` như một biến thể “SELECT nhẹ” có thể gọi tùy tiện bên ngoài transaction.

## 19. OPTIMISTIC_FORCE_INCREMENT: yêu cầu tăng phiên bản

JPA cũng có:

```java
LockModeType.OPTIMISTIC_FORCE_INCREMENT
```

Một ví dụ:

```java
@Transactional
public void markOrderWorkflowChanged(long orderId) {
    SalesOrder order =
        em.find(SalesOrder.class, orderId);

    if (order == null) {
        throw new OrderNotFoundException(orderId);
    }

    em.lock(
        order,
        LockModeType.OPTIMISTIC_FORCE_INCREMENT
    );
}
```

Ý định là **yêu cầu tăng phiên bản** của entity được khóa, ngay cả khi ứng dụng không có một thay đổi persistent state thông thường ở entity ấy.

### 19.1. Khi nào có ích?

- Cần đánh dấu một aggregate root đã thay đổi về mặt concurrency contract.
- Cần phát hiện concurrent modifications trên một entity chủ khi workflow liên quan dữ liệu khác.
- Muốn buộc một entity version được tiến lên theo transaction.

Tuy nhiên dùng `OPTIMISTIC_FORCE_INCREMENT` không tự giải quyết mọi invariant của một aggregate lớn nếu các thành viên được sửa ngoài quy tắc transaction/locking đã thiết kế.

### 19.2. Tên gọi “force increment” không có nghĩa update tức thì

Provider có thể trì hoãn version increment đến flush/commit. Đừng dựa vào `item.getVersion()` ngay sau lời gọi lock để khẳng định database version đã tăng và commit.

### 19.3. Khi nào không nên lạm dụng?

Nếu chỉ cần đọc danh sách 100.000 entity, force increment trên tất cả sẽ tạo writes/contended versions không cần thiết. Nó không phải công cụ tối ưu read performance.

### 19.4. Pessimistic locks vẫn là lựa chọn khác

Các modes như `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` có ngữ nghĩa khác, liên quan database locking. Chúng có thể phù hợp khi tranh chấp cao nhưng có chi phí lock contention/deadlock/timeout riêng.

`@Version` và optimistic lock modes không tự thay thế các ràng buộc database hoặc lựa chọn pessimistic locking khi workflow cần.

## 20. Bulk JPQL UPDATE không tự tăng @Version

Một trong những lỗi quan trọng nhất:

```java
int affected = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = :newQuantity
    where i.id = :id
    """
)
.setParameter("newQuantity", 5)
.setParameter("id", 42L)
.executeUpdate();
```

Đây là **bulk JPQL UPDATE**, không phải managed entity dirty checking. Câu này:

- Không cần load InventoryItem vào persistence context.
- Không tự làm optimistic version check như entity-level update.
- Không tự tăng `@Version` theo cơ chế version management của managed entity.
- Không tự chạy toàn bộ entity-level callbacks/validation như thao tác sửa từng entity.
- Có thể để managed instance trong persistence context ở trạng thái stale.

Chỉ vì entity có `@Version` **không có nghĩa mọi câu UPDATE trên bảng sẽ bảo vệ version**.

### 20.1. Mẫu conditional bulk update với numeric version

Nếu quyết định dùng bulk UPDATE và muốn bảo vệ expected version:

```java
int affected = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = :newQuantity,
        i.version = i.version + 1
    where i.id = :id
      and i.version = :expectedVersion
    """
)
.setParameter("newQuantity", newQuantity)
.setParameter("id", itemId)
.setParameter("expectedVersion", expectedVersion)
.executeUpdate();
```

Đây là **manual compare-and-update**:

- `WHERE i.version = :expectedVersion` kiểm tra trạng thái kỳ vọng.
- `SET i.version = i.version + 1` tăng version theo công thức numeric.
- `affected == 1` thường nói rằng một target entity thỏa điều kiện đã được bulk update.
- `affected == 0` có thể do stale version hoặc không tồn tại, không tự có nghĩa “optimistic exception”.
- Nếu dự kiến ID là primary key, `affected > 1` biểu thị vấn đề phạm vi/mapping/invariant nghiêm trọng cần xử lý.

### 20.2. Không coi count 0 là OptimisticLockException tự động

Trong bulk DML, query không match thường trả 0:

```java
if (affected == 0) {
    throw new VersionConflictException(
        "Item is missing or its version changed"
    );
}
```

`VersionConflictException` là domain exception do dự án định nghĩa. JPA không bắt buộc tự ném `OptimisticLockException` chỉ vì bulk conditional update trả count 0.

### 20.3. Khi nào manual version increment có giới hạn?

Công thức `i.version + 1` phù hợp cho numeric versions mà provider/database hỗ trợ phép cộng đó. Nó **không phải** giải pháp chung cho timestamp version hoặc mọi provider-specific version strategy.

Nó cũng không tự áp:

- Entity-level lifecycle callbacks.
- Cascading JPA.
- Bean Validation theo từng entity.
- Domain methods/invariants không thể biểu diễn bằng SQL.
- Đồng bộ những managed entities đã load trước đó.

### 20.4. Không chỉ check version mà quên increment

Sai về ý định:

```jpql
update InventoryItem i
set i.availableQuantity = :quantity
where i.id = :id and i.version = :expected
```

Nếu query thành công mà **không tăng version**, transaction tiếp theo vẫn có thể dùng cùng expectedVersion cũ và ghi đè state. Với manual bulk version strategy, thường cần cả **so sánh và cập nhật token**.

## 21. Native SQL UPDATE cũng cần xử lý version riêng

Ví dụ:

```sql
UPDATE inventory_item
SET available_quantity = ?
WHERE id = ?;
```

Nếu chạy trực tiếp qua JDBC/native query, lệnh không tự biết entity có `@Version` và không tự đảm bảo cơ chế update phiên bản của JPA-managed entity.

Một SQL có chủ đích:

```sql
UPDATE inventory_item
SET
    available_quantity = ?,
    row_version = row_version + 1
WHERE
    id = ?
    AND row_version = ?;
```

Dùng từ JPA:

```java
int affected = em.createNativeQuery(
    """
    UPDATE inventory_item
    SET
        available_quantity = ?1,
        row_version = row_version + 1
    WHERE
        id = ?2
        AND row_version = ?3
    """
)
.setParameter(1, newQuantity)
.setParameter(2, itemId)
.setParameter(3, expectedVersion)
.executeUpdate();
```

### 21.1. Native SQL không tự hiểu domain invariants

Một query đặt availableQuantity=-5 có thể vẫn chạy nếu database không có constraint và query không tự kiểm tra số lượng. Domain method `reserve` trước đó có validation, nhưng native SQL không gọi method này.

Có thể đưa điều kiện vào SQL khi đúng mục tiêu, chẳng hạn:

```sql
UPDATE inventory_item
SET
    available_quantity = available_quantity - ?,
    row_version = row_version + 1
WHERE
    id = ?
    AND available_quantity >= ?
    AND row_version = ?;
```

Đây là một **atomic conditional decrement** theo predicate, giúp tránh âm tồn kho khi nhiều giao dịch cạnh tranh, nếu SQL và isolation/constraint của database phù hợp.

Nhưng count 0 lúc này có thể do:

- Không đủ tồn kho.
- Sai phiên bản.
- Không tồn tại.
- Không đúng tenant/scope.
- Các predicate khác không khớp.

Cần thiết kế response/retry theo nghiệp vụ.

### 21.2. Không để native SQL phá version của entity managed

Nếu một InventoryItem đã được load vào persistence context, native UPDATE có thể làm database version từ 7 lên 8 trong khi Java object vẫn giữ 7.

Sau đó dirty checking trên cùng managed instance có thể gây optimistic failure hoặc stale data. Khi trộn native DML với entity operations:

- Rõ transaction boundary.
- Flush pending JPA changes trước native update khi cần.
- Cân nhắc refresh/clear hoặc persistence context mới.
- Không tiếp tục thao tác trên stale managed instance như mới.
- Test second-level cache/query cache nếu đang bật.

### 21.3. Không dùng database trigger tăng version “bí mật” mà chưa thiết kế

Một DB trigger tự tăng `row_version` khi UPDATE có thể xung đột với JPA provider cũng tăng version, tạo double increments hoặc snapshot không khớp.

Nếu dự án chọn database-generated version, phải có **mapping/strategy provider hỗ trợ** để nhận đúng giá trị generated và optimistic checks, có integration test. Đừng ghép trigger và `@Version` mặc định rồi giả định chúng tự phối hợp.

## 22. CriteriaUpdate cũng bỏ qua entity-level version management

JPA Criteria API có bulk update:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaUpdate<InventoryItem> update =
    cb.createCriteriaUpdate(InventoryItem.class);

Root<InventoryItem> root =
    update.from(InventoryItem.class);

update.set(
    root.get("availableQuantity"),
    newQuantity
);

update.where(
    cb.equal(root.get("id"), itemId)
);

int affected = em.createQuery(update).executeUpdate();
```

Giống JPQL bulk update, nó không tự biến thành một vòng lặp managed entity updates.

### 22.1. Khi cần optimistic check cho CriteriaUpdate

Có thể xây predicate version:

```java
update.where(
    cb.equal(root.get("id"), itemId),
    cb.equal(root.get("version"), expectedVersion)
);
```

Và cần thiết kế cập nhật version numeric phù hợp. Nếu Criteria `set` với expression increment trở nên phức tạp hoặc khó portable trong provider đang dùng, có thể chọn JPQL bulk query rõ ràng hoặc managed entity update.

**Không áp dụng chiến lược một cách nửa vời:** chỉ thêm WHERE version mà không làm thay đổi version sau khi update không tạo token mới để bảo vệ lần ghi tiếp theo.

## 23. Persistence context stale sau bulk DML

Giả sử:

```java
InventoryItem item = em.find(InventoryItem.class, 42L);

Long beforeVersion = item.getVersion();

int affected = em.createQuery(
    """
    update InventoryItem i
    set i.availableQuantity = 5,
        i.version = i.version + 1
    where i.id = :id
    """
)
.setParameter("id", 42L)
.executeUpdate();

Long afterVersion = item.getVersion();
```

Không được mặc định `afterVersion` đã tăng. Bulk UPDATE tác động database; JPA **không tự đồng bộ managed instances đã tồn tại** theo từng thay đổi của lệnh bulk.

### 23.1. Giải pháp đọc lại

Nếu cần quan sát state mới:

```java
em.refresh(item);
```

trong context/transaction phù hợp, hoặc dùng:

```java
em.clear();
InventoryItem reloaded =
    em.find(InventoryItem.class, 42L);
```

Nhưng:

- `refresh` có thể ghi đè local changes chưa được đồng bộ.
- `clear` detach **toàn bộ** managed entities.
- `clear` khi chưa flush có thể làm mất pending changes.
- Transaction isolation còn ảnh hưởng dữ liệu quan sát được.
- Với second-level cache, native DML có thể cần chính sách invalidation riêng tùy provider.

### 23.2. Flush trước bulk khi có pending changes

```java
em.flush();

int count = em.createQuery(
    "update InventoryItem i set i.availableQuantity = :qty"
)
.setParameter("qty", newQty)
.executeUpdate();

em.clear();
```

Đây là thứ tự có thể phù hợp trong một số batch workflow, nhưng không phải mẫu nên copy vô điều kiện. Bulk UPDATE trên **mọi item** nếu không có WHERE có thể là lỗi nghiêm trọng; ví dụ trên chỉ minh họa thứ tự flush/bulk/clear, không khuyến khích bỏ scope.

### 23.3. Cân nhắc transaction riêng cho bulk jobs

Một batch job có thể thực thi bulk UPDATE trong persistence context ngắn, commit, rồi mở context mới để đọc kết quả. Cách này giảm nguy cơ trộn stale managed entity state với direct DB writes, đổi lại cần xử lý concurrency giữa các transaction.

## 24. Quan hệ entity và phạm vi tăng version

Một câu hỏi thường gặp:

> Nếu Order có `@Version`, sửa một OrderLine có tự tăng version của Order không?

**Không thể trả lời tuyệt đối cho mọi mapping.** Nó phụ thuộc:

- Entity nào là owner của relationship.
- Có thay đổi persistent state của Order hay chỉ OrderLine?
- Relationship được quản lý ở owning/inverse side nào?
- Provider và chiến lược versioning.
- Có dùng `OPTIMISTIC_FORCE_INCREMENT` hoặc domain method làm thay đổi Order không?

Ví dụ:

```java
@Entity
public class SalesOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines;
}
```

`mappedBy = "order"` nói collection phía Order là **inverse side** của relationship. Nếu chỉ sửa thuộc tính `quantity` trong một `OrderLine` độc lập, không nên mặc định parent Order version sẽ tăng.

### 24.1. Aggregate root không tự được bảo vệ toàn bộ graph

Một aggregate nghiệp vụ có thể gồm Order và Lines, nhưng JPA version không tự bảo vệ mọi thay đổi xuyên nhiều bảng theo cách domain aggregate yêu cầu.

Nếu business invariant phụ thuộc vào cả Order+Lines, cần một thiết kế rõ:

- Mọi thay đổi Lines phải đi qua service/aggregate root.
- Kiểm tra version của root.
- Khi cần, force increment root hoặc cập nhật một field quản lý phù hợp.
- Dùng constraint/database locking khi invariant trải nhiều rows.
- Test cạnh tranh giữa hai transaction sửa children.

### 24.2. @Version trên child entity

Nếu OrderLine có `@Version` riêng:

```java
@Entity
public class OrderLine {

    @Id
    private Long id;

    @Version
    private Long version;

    @ManyToOne(fetch = FetchType.LAZY)
    private SalesOrder order;

    private int quantity;
}
```

nó bảo vệ concurrency cho **OrderLine entity** theo version riêng. Điều này không đồng nghĩa mỗi lần cập nhật OrderLine sẽ buộc Order.version tăng.

### 24.3. Đừng tăng version root bằng setter thủ công

Không dùng:

```java
order.setVersion(order.getVersion() + 1);
```

Thay vào đó, chọn JPA lock mode hoặc domain/mapping strategy phù hợp nếu cần ghi nhận thay đổi aggregate root.

## 25. Optimistic locking không thay unique constraint và foreign key

`@Version` xử lý cập nhật stale của một entity đã có version. Nó không thay thế:

- UNIQUE constraint cho SKU/mã đơn.
- FOREIGN KEY constraint để bảo vệ association.
- CHECK constraint như `available_quantity >= 0`.
- NOT NULL constraint.
- Transaction isolation khi đọc/ghi nhiều rows.
- Authorization và tenant isolation.
- Idempotency cho external events.
- Exactly-once processing trong hệ thống phân tán.

### 25.1. Một ví dụ duplicate insert

Hai transaction cùng kiểm tra SKU `BOOK-JPA` “chưa tồn tại” rồi INSERT hai sản phẩm mới. `@Version` trên từng row mới không tự làm SKU unique.

Database phải có:

```sql
CONSTRAINT uq_inventory_item_sku UNIQUE (sku)
```

hoặc unique index phù hợp. Với concurrent insert, unique constraint là lớp bảo vệ cần thiết.

### 25.2. Write skew khi invariant trải nhiều rows

Giả sử luật nghiệp vụ yêu cầu “ít nhất một nhân viên trực ca”. Hai transaction đồng thời đọc hai rows phiên trực khác nhau, mỗi bên tắt một row. Version trên từng row có thể không phát hiện xung đột **nếu không ai ghi vào cùng row**.

Đây là lý do không đồng nhất optimistic versioning **theo entity** với serializable isolation hoặc bảo vệ mọi cross-row invariant.

### 25.3. Có cần CHECK available_quantity >= 0?

Domain method `reserve` kiểm tra số lượng trong Java. Nhưng nếu có bulk/native SQL hoặc ứng dụng khác ghi DB, một CHECK constraint phù hợp có thể cung cấp hàng rào bảo vệ bổ sung.

Không dùng `@Version` làm lý do bỏ qua database constraints.

## 26. So sánh khóa lạc quan và khóa bi quan

| Tiêu chí | Optimistic locking bằng `@Version` | Pessimistic locking |
|---|---|---|
| Ý tưởng | Phát hiện stale write qua version | Yêu cầu DB locking khi truy cập dữ liệu |
| Có giữ row lock dài hạn lúc chỉ đọc? | Không theo ý nghĩa optimistic | Có thể có theo lock mode/DB |
| Phù hợp khi | Ít concurrent writes vào cùng entity | Tranh chấp cao, cần chặn writers theo workflow |
| Kết quả cạnh tranh | Một bên có thể nhận optimistic conflict | Một bên có thể chờ, timeout hoặc deadlock |
| Khả năng retry | Thường cần reload/re-evaluate state | Có thể cần retry deadlock/timeout |
| Rủi ro | Nhiều conflicts dưới hot-row load | Lock contention, deadlock, transaction dài |
| Hạn chế | Không tự bảo vệ cross-row invariant | Không tự sửa mọi logic business/concurrency |
| API ví dụ | `@Version`, `LockModeType.OPTIMISTIC` | `LockModeType.PESSIMISTIC_WRITE` |

Chọn theo semantics và workload thực tế. Không có kỹ thuật nào “tốt nhất cho mọi transaction”.

### 26.1. Không gộp hai loại exception

Optimistic conflict thường liên quan `OptimisticLockException`. Pessimistic lock có thể báo `PessimisticLockException`, `LockTimeoutException` hoặc exception khác tùy tình huống.

Chính sách retry phải phân loại đúng exception và xem trạng thái transaction.

## 27. Retry optimistic conflict đúng cách

Một hướng service-level retry có thể như sau:

```text
Nhận yêu cầu reserve(quantity)
              |
              v
       Bắt đầu transaction mới
              |
              v
       Load InventoryItem mới nhất
              |
              v
       Kiểm tra quantity và business rules
              |
              v
       Thực hiện reserve trong managed entity
              |
              v
       Flush / commit
        /           \
      Thành công    Optimistic conflict
        |             |
        v             v
     Trả kết quả     Rollback
                      |
                      v
             Có thể retry theo policy?
                /            \
               Có           Không
                |              |
                v              v
         Transaction mới   Báo conflict
         + reload state
```

### 27.1. Không retry trong cùng transaction bị rollback-only

Sai:

```java
try {
    em.flush();
} catch (OptimisticLockException ex) {
    // Không tiếp tục dùng chính em/transaction cũ để thử lại
    // bằng cách em.find rồi em.flush.
}
```

Sau conflict, transaction/persistence context có thể không còn trạng thái đáng tin cậy để tiếp tục. Retry phải có transaction mới, thường do outer layer hoặc retry framework tạo.

### 27.2. Không retry bằng cách ghi lại snapshot cũ

Nếu A và B đều đọc 10:

```text
B cũ: newQuantity = 6
```

sau khi A cập nhật qty=7, retry B bằng cách gán cứng 6 vẫn bỏ qua A. Cần **tính lại**:

```text
qty mới = 7
reserve(4) => 3
```

Đây là lý do retry đúng phải chạy lại **business calculation** trên state mới, không replay stale entity state.

### 27.3. Giới hạn retry

Không retry vô hạn:

- Xung đột cao có thể không bao giờ giảm.
- Có thể làm bão hòa database.
- Có thể tăng độ trễ API.
- Có thể vi phạm SLA.
- Nếu workflow có external side effects, retry có thể gửi/lặp thao tác ngoài DB.

Cân nhắc số lần retry nhỏ có backoff/jitter phù hợp với kiến trúc. Nếu vẫn thất bại, trả conflict hoặc đặt yêu cầu vào queue theo policy.

### 27.4. Với thanh toán, không retry cả workflow một cách mù quáng

Nếu transaction đã gọi payment provider, không được tự gửi lại charge mỗi lần gặp `OptimisticLockException` mà không có idempotency key và trạng thái điều phối rõ.

Ưu tiên ghi trạng thái/outbox theo transaction, tách external calls khỏi transaction dài và dùng idempotent APIs.

## 28. Một mẫu Spring service với @Version

Ví dụ:

```java
@Service
public class InventoryReservationService {

    private final EntityManager em;

    public InventoryReservationService(EntityManager em) {
        this.em = em;
    }

    @Transactional
    public void reserve(
            long itemId,
            String authorizedTenantId,
            int quantity
    ) {
        InventoryItem item =
            em.find(InventoryItem.class, itemId);

        if (item == null) {
            throw new ItemNotFoundException(itemId);
        }

        // Minh họa: dự án thật cần property tenantId
        // và kiểm tra item có thuộc tenant được phép hay không.
        authorize(item, authorizedTenantId);

        item.reserve(quantity);

        // Không gọi setVersion.
        // Không cần merge khi item đang managed.
        // Transaction manager xử lý commit.
    }

    private void authorize(
            InventoryItem item,
            String authorizedTenantId
    ) {
        // Kiểm tra quyền/tenant theo security domain thật.
    }
}
```

Ở ví dụ này, `authorize` là một chỗ đánh dấu **cần triển khai chính sách bảo mật thực**, không phải mẫu hoàn chỉnh để copy nguyên vào production. Nếu entity đa tenant, nên có mapping `tenantId` cùng truy vấn/authorization thích hợp.

### 28.1. Đừng bắt exception chỉ ở bên trong method và kỳ vọng bắt được mọi commit failure

Một phương thức `@Transactional` có thể trả khỏi body trước khi transaction interceptor thực hiện commit. Đặt retry ở **outer boundary** có thể quan sát được outcome của cả transactional invocation, hoặc ở một retry service gọi method transactional qua proxy/transaction template mới.

### 28.2. Tách một attempt và retry coordinator

```text
ReservationController
       |
       v
ReservationCoordinator (retry policy)
       |
       v
ReservationAttemptService.reserveOnce(...)
       |  @Transactional
       v
EntityManager + @Version + commit
```

Lợi ích: mỗi attempt có transaction riêng và retry coordinator không nhầm flush success với commit success. Với Spring, cần chú ý self-invocation bypass proxy `@Transactional` nếu đặt retry và transactional method sai cấu trúc.

### 28.3. Spring exception translation

Spring Data JPA/Spring ORM có thể chuyển exception JPA/provider thành họ `DataAccessException`, ví dụ optimistic locking failure được biểu diễn bằng exception phù hợp của Spring. Không thiết kế catch logic chỉ dựa vào class exception provider cụ thể nếu tầng ứng dụng đang dùng Spring exception translation.

Tuy nhiên, phải kiểm tra transaction và exception contract của framework/version thực tế; không catch mọi `DataAccessException` để retry.

## 29. Version ban đầu và migration dữ liệu legacy

Khi bổ sung `@Version` vào một bảng đã tồn tại, cần migration.

Giả sử bảng `inventory_item` hiện chưa có cột version.

Một quy trình migration có thể gồm:

1. Thêm `row_version` nullable hoặc có default tạm thời.
2. Backfill phiên bản cho tất cả rows hiện có.
3. Đảm bảo không còn NULL.
4. Đặt NOT NULL.
5. Cập nhật entity mapping với `@Version`.
6. Kiểm tra mọi writer đang dùng bảng này.
7. Triển khai phối hợp để không còn ứng dụng cũ ghi bỏ qua version.
8. Kiểm thử xung đột với dữ liệu thực tế.

DDL mang tính minh họa:

```sql
ALTER TABLE inventory_item
ADD COLUMN row_version BIGINT;

UPDATE inventory_item
SET row_version = 0
WHERE row_version IS NULL;

-- Tùy dialect để chuyển cột thành NOT NULL.
```

**Cú pháp ALTER COLUMN đặt NOT NULL khác nhau theo database**. Phần trên không phải migration portable đầy đủ có thể chạy nguyên trên mọi DB.

### 29.1. Không chỉ backfill rồi tuyên bố đã an toàn

Nếu một ứng dụng cũ tiếp tục:

```sql
UPDATE inventory_item SET available_quantity = ?
WHERE id = ?;
```

mà không check/tăng version, nó vẫn có thể ghi đè dữ liệu của ứng dụng JPA mới.

Migration thành công về schema **không đồng nghĩa mọi writer đã tuân thủ concurrency contract**.

### 29.2. Có nhiều ứng dụng viết cùng bảng?

Cần thống nhất:

- Có phải tất cả đều dùng JPA cùng mapping?
- Có raw JDBC, batch ETL, stored procedures, triggers, admin scripts?
- Những lệnh đó có cập nhật version đúng không?
- Có giám sát các phiên bản ứng dụng cũ khi rolling deployment?
- Nếu không thể thống nhất, có nên đặt version strategy xuống DB hoặc tách ownership dữ liệu không?

`@Version` an toàn nhất khi mọi writer của một entity tuân thủ cùng một quy tắc concurrency.

## 30. Version và auditing

`@Version` khác các trường audit:

```java
@Version
private Long version;

@Column(name = "updated_at")
private Instant updatedAt;

@Column(name = "updated_by")
private String updatedBy;
```

| Field | Công dụng |
|---|---|
| `version` | Optimistic concurrency token |
| `updatedAt` | Thời điểm cập nhật theo audit/domain |
| `updatedBy` | Danh tính người/hệ thống thay đổi |
| `createdAt` | Thời điểm tạo |
| `revisionId` | Có thể là revision trong hệ thống audit/version-history riêng |

### 30.1. @Version không chứa lịch sử

Nếu Item#42 đang version 9, database không tự lưu những giá trị của version 1..8 chỉ vì entity có `@Version`. Đây là **counter/token**, không phải audit log.

Muốn lịch sử thay đổi, cần audit table, event log, Envers/provider extension hoặc cơ chế khác phù hợp.

### 30.2. @PreUpdate có thể ghi updatedAt nhưng không thay version logic

Một entity callback:

```java
@PreUpdate
void touch() {
    updatedAt = Instant.now();
}
```

có thể dùng cho audit trong entity-level lifecycle. Nhưng bulk JPQL/native SQL không tự gọi callback này cho từng entity. Và callback không nên tự sửa `@Version`.

### 30.3. Version có luôn tăng khi chỉ thay association?

Không thể xem version là “mọi thay đổi trong graph”. Với collection inverse hoặc entity con độc lập, provider/mapping có thể không tăng version của root. Thiết kế audit và aggregate consistency phải tách biệt với giả định quá rộng về `@Version`.

## 31. Version và cache

Trong persistence context, một managed entity có identity/snapshot riêng. Một versioned entity có thể kết hợp với caching của provider, nhưng cần phân biệt:

- **First-level cache**: persistence context, quản lý một managed instance cho mỗi identity.
- **Second-level cache**: cache chia sẻ tùy provider/configuration.
- **Query cache**: cache kết quả truy vấn ở một số provider.
- **Database state**: nguồn dữ liệu đã commit theo transaction/isolation.

`@Version` giúp provider thực hiện optimistic checks cho entity lifecycle, nhưng không tự đảm bảo **mọi cache và mọi native writer** luôn đồng bộ chính xác.

### 31.1. Query đọc lại không nhất thiết refresh managed object

```java
InventoryItem first =
    em.find(InventoryItem.class, 42L);

InventoryItem second =
    em.find(InventoryItem.class, 42L);
```

Trong cùng persistence context, chúng thường là một managed instance theo identity map. Nếu một transaction khác đã cập nhật row, `find` lần hai không tự đảm bảo lấy version mới.

Muốn dữ liệu mới, cần xem `refresh`, context/transaction mới và isolation.

### 31.2. Native DML + cache cần hợp đồng riêng

Nếu một job khác cập nhật `row_version` bằng raw SQL, provider cache invalidation có thể không tự nhận biết. Có thể cần evict/refresh hoặc một cách đồng bộ cache được provider hỗ trợ. Không dựa vào version field như cơ chế broadcast invalidation cho mọi tiến trình.

## 32. Tối ưu hiệu năng: version check có chi phí gì?

Một phiên bản số nguyên thường thêm:

- Một cột database.
- Một giá trị trong entity snapshot.
- Một predicate vào UPDATE/DELETE hoặc cơ chế check tương đương.
- Một thao tác thay đổi version khi entity được cập nhật.
- Khả năng phát sinh conflict/retry.

Đây thường là chi phí hợp lý để bảo vệ dữ liệu, nhưng không miễn phí.

### 32.1. Đừng dùng version như “lock table” toàn hệ thống

Nếu mọi thay đổi trong cả hệ thống đều làm tăng version của một row cấu hình duy nhất, row đó có thể thành điểm nóng. Nhiều transaction sẽ tranh chấp cùng optimistic version, tạo conflict liên tục.

Hãy xác định phạm vi consistency theo entity/aggregate hợp lý.

### 32.2. Counter nóng có thể cần SQL atomic update

Với counter chỉ cần tăng/giảm atomically, SQL:

```sql
UPDATE inventory_item
SET
    available_quantity = available_quantity - ?,
    row_version = row_version + 1
WHERE
    id = ?
    AND available_quantity >= ?;
```

có thể phù hợp hơn round-trip load→modify→flush cho một số workload, nhưng phải đánh giá:

- Version check có cần expectedVersion từ client không?
- Cập nhật có bao gồm domain constraints ngoài quantity không?
- Có được phép retry hay không?
- Có managed instances khác trong context không?
- Database/provider hỗ trợ affected-row semantics ra sao?
- Vấn đề fairness, contention, lock wait, hot row, deadlocks thế nào?

Không đổi sang native SQL chỉ vì một benchmark nhỏ mà bỏ các invariants của domain.

## 33. Kiểm thử optimistic locking bằng hai EntityManager

Một test concurrency nên dùng **hai persistence contexts độc lập**. Nếu dùng cùng EntityManager, identity map khiến bạn không mô phỏng hai snapshot khác nhau của cùng entity đúng cách.

Kịch bản với JPA resource-local transactions:

```java
EntityManager a = emf.createEntityManager();
EntityManager b = emf.createEntityManager();

try {
    EntityTransaction txA = a.getTransaction();
    EntityTransaction txB = b.getTransaction();

    txA.begin();
    txB.begin();

    InventoryItem itemA =
        a.find(InventoryItem.class, 42L);

    InventoryItem itemB =
        b.find(InventoryItem.class, 42L);

    // Giả sử cả hai đều đọc version ban đầu 7.
    itemA.reserve(3);
    itemB.reserve(4);

    txA.commit();

    boolean conflictDetected = false;
    try {
        txB.commit();
    } catch (OptimisticLockException ex) {
        conflictDetected = true;
    } catch (RollbackException ex) {
        // Ở một số stack, lỗi optimistic check có thể
        // được bọc trong rollback/commit exception.
        conflictDetected = containsOptimisticConflict(ex);
    }

    if (!conflictDetected) {
        throw new AssertionError(
            "Expected an optimistic conflict"
        );
    }
} finally {
    if (a.getTransaction().isActive()) {
        a.getTransaction().rollback();
    }
    if (b.getTransaction().isActive()) {
        b.getTransaction().rollback();
    }
    a.close();
    b.close();
}
```

`containsOptimisticConflict` là **helper test do dự án tự triển khai** để duyệt cause chain theo provider/transaction manager; đoạn code minh họa cần helper này, fixture và imports phù hợp.

### 33.1. Kịch bản cần chuẩn bị

Trước test, tạo row:

```text
Item#42: available_quantity=10, row_version=7
```

Hoặc dùng version do provider tạo ban đầu, đọc giá trị thực thay vì hard-code 7.

### 33.2. Vì sao test phải giữ hai snapshots cũ?

Nếu Transaction B bắt đầu **sau** khi A commit và đọc version 8, B không còn stale; cả hai thao tác có thể thành công theo thứ tự bình thường. Để kiểm tra optimistic conflict, phải chắc chắn cả A và B đều đã đọc version ban đầu trước khi A commit.

### 33.3. Lưu ý isolation khi test

Một số database/isolation có thể báo deadlock/serialization/lock timeout thay vì lộ `OptimisticLockException` đúng y hệt trên mọi lịch trình. Vì vậy test cần:

- Xác định isolation và target database.
- Không để SQL lock khiến hai transaction chờ nhau vô hạn.
- Kiểm tra loại exception và cause chain thực tế.
- Xác minh state database sau các transaction.
- Nếu cần, dùng threads/barrier để điều phối chính xác thời điểm đọc/flush/commit.

### 33.4. Đọc lại bằng EntityManager mới

Sau test:

```java
EntityManager verify = emf.createEntityManager();
try {
    InventoryItem reloaded =
        verify.find(InventoryItem.class, 42L);

    assertEquals(7, reloaded.getAvailableQuantity());
    // Version dự kiến tăng theo provider khi A commit thành công.
} finally {
    verify.close();
}
```

Với fixture A reserve(3) thành công và B conflict, quantity mong đợi là 7. Không sử dụng entity từ context B bị rollback để xác minh dữ liệu sau commit.

## 34. Kiểm thử phiên bản được tăng tự động

Một test cơ bản:

1. Persist entity mới theo setup chuẩn của dự án, commit.
2. Đọc lại entity ở transaction/context mới.
3. Ghi nhớ version ban đầu.
4. Gọi domain method thay đổi field persistent.
5. Commit.
6. Đọc lại và so sánh version.

Ví dụ pseudo-code:

```java
Long before = loadVersion(itemId);

updateInTransaction(itemId, item -> {
    item.reserve(1);
});

Long after = loadVersion(itemId);

assertNotEquals(before, after);
```

Với numeric version, trong mô hình thông thường version tăng khi entity thực sự được cập nhật. Tuy nhiên không viết test dựa vào `before + 1` nếu project còn có force increments, provider-specific mapping, triggers hoặc những thao tác khác trong cùng transaction mà bạn chưa kiểm soát.

### 34.1. Test read-only không tăng version

Đọc entity, không thay đổi persistent state, commit. Version thường không tăng chỉ vì entity đã được đọc.

### 34.2. Test stale merge

Tải detached entity version cũ, cho transaction khác update version, rồi merge detached và flush/commit. Xác nhận xung đột theo provider/contract, không giả định exception luôn xuất hiện ngay tại lời gọi merge.

### 34.3. Test delete conflict

Tải entity ở hai contexts; A update và commit, B remove stale entity. Xác nhận optimistic detection theo target stack.

### 34.4. Test manual bulk UPDATE

Thực hiện JPQL bulk UPDATE mà không sửa version, quan sát không tự có entity-level version increment. Sau đó dùng conditional bulk UPDATE với WHERE version và SET version=version+1, assert count=1 khi match và 0 khi stale.

### 34.5. Test native SQL writer

Nếu hệ thống có raw JDBC hoặc batch job, test rằng chúng tuân thủ version strategy hoặc không được phép ghi trực tiếp. Đây là một phần bảo đảm concurrency mà chỉ test JPA repository không thể bao phủ.

### 34.6. Test rollback

Cho optimistic conflict xảy ra, xác nhận transaction bị rollback và database không chứa một phần thay đổi bất hợp lệ từ transaction đó.

### 34.7. Test application-level retry

Khi conflict:

- Attempt cũ rollback.
- Attempt mới reload state.
- Domain rule được tính lại.
- Không có duplicate payment/email/outbox event.
- Retry được giới hạn số lần.

Đây là integration test hoặc workflow test, không chỉ unit test gọi mock `EntityManager`.

## 35. Các lỗi phổ biến khi dùng @Version

### 35.1. Không khai báo @Version nên tin rằng JPA sẽ tự nhận concurrent write

Không nên mặc định ORM luôn phát hiện lost update cho mọi entity không version. Cần cơ chế locking/concurrency policy rõ.

### 35.2. Dùng @Column(name="version") nhưng quên @Version

```java
@Column(name = "row_version")
private Long version;
```

chỉ là một persistent field bình thường. Không tự có optimistic version management nếu thiếu `@Version` hoặc một chiến lược lock khác.

### 35.3. Đặt @Version trên String hoặc kiểu không được provider hỗ trợ

Không portable. Chọn numeric version hoặc kiểu được JPA version/target provider hỗ trợ theo tài liệu và test.

### 35.4. Đặt nhiều @Version trên một entity hierarchy

Không làm tăng an toàn, có thể khiến mapping không hợp lệ. Dùng một version attribute thích hợp.

### 35.5. Đặt version ở secondary table rồi nghĩ portable

Version attribute nên thuộc primary table của entity theo JPA portable mapping.

### 35.6. Dùng @Version trên field nhưng @Id trên getter không có access strategy rõ

Dễ làm provider đọc metadata không như dự kiến.

### 35.7. Tự gọi version++ trong setter

Provider đã quản lý version. Sửa thủ công có thể phá expected version tracking.

### 35.8. Gán version = 0 để ép merge

Không phải cách an toàn xử lý detached entity cũ. Có thể gây lỗi new/detached state hoặc stale version conflict.

### 35.9. Cho rằng @Version khóa row ngay từ lúc find

Sai. Optimistic locking chủ yếu phát hiện xung đột chứ không giữ database lock dài hạn theo cách pessimistic locking.

### 35.10. Cho rằng read-only transaction luôn tăng version

Không. Thông thường không có dirty update thì version không cần tăng, trừ các lock modes hoặc provider behaviors được yêu cầu riêng.

### 35.11. Cho rằng OptimisticLockException luôn xuất hiện tại setter

Không. Nó thường xuất hiện khi provider kiểm tra version ở flush/commit hoặc thao tác khác theo contract.

### 35.12. Catch OptimisticLockException rồi tiếp tục transaction hiện tại

Nguy hiểm. Transaction có thể rollback-only; cần rollback và transaction mới cho retry.

### 35.13. Retry bằng stale entity mà không reload

Không giải quyết lost update và có thể ghi lại state cũ.

### 35.14. Retry vô hạn mọi PersistenceException

Có thể lặp lỗi không phải optimistic conflict và làm database quá tải.

### 35.15. Bulk JPQL UPDATE mặc định tăng version

Không theo entity-level version management. Phải thiết kế manual version strategy hoặc dùng managed entity update.

### 35.16. Bulk UPDATE check version nhưng không đổi version

Một transaction sau vẫn có thể update bằng expectedVersion cũ. Nếu cần concurrency token mới, phải increment theo chiến lược phù hợp.

### 35.17. Native SQL UPDATE quên điều kiện version

Có thể ghi đè thay đổi của JPA-managed entities và phá concurrency contract.

### 35.18. DB trigger tự tăng version đồng thời JPA cũng tăng

Có thể double increment hoặc không đồng bộ snapshot. Cần một chiến lược duy nhất được provider hỗ trợ.

### 35.19. @Version bảo vệ mọi child của aggregate tự động

Không. Entity con/relationship và inverse side có semantics riêng; cần thiết kế aggregate consistency.

### 35.20. @Version thay UNIQUE, FK, CHECK và isolation

Sai. Các cơ chế bảo vệ các loại invariant khác nhau.

### 35.21. Version thay đổi nên nghĩ có lịch sử bản cũ

Không. Version là token/concurrency metadata, không phải audit history.

### 35.22. Trả entity trực tiếp ra REST rồi để client set version

Không nên để client điều khiển version như field editable tùy ý. DTO có expectedVersion phục vụ conditional update là một contract rõ ràng hơn.

### 35.23. Đọc lại bằng cùng EntityManager rồi tin chắc version đã mới

First-level cache có thể trả managed state hiện tại. Khi cần refresh, dùng strategy phù hợp.

### 35.24. Dùng VersionConflictException cho mọi lỗi DB

Làm mờ nguyên nhân deadlock, SQL syntax, validation, FK và connection failure.

### 35.25. Flush thành công nên gửi external notification trước commit

Flush không phải commit. Cần after-commit/outbox nếu external side effect phụ thuộc commit.

### 35.26. Gán optimistic locking như một phương án exactly-once

Nó không tự loại duplicate request/payment/notification. Cần idempotency workflow.

### 35.27. Khi xung đột cao vẫn cố optimistic retry hàng trăm lần

Có thể gây retry storm. Đo conflict rate và cân nhắc kỹ thuật concurrency khác.

### 35.28. Chỉ test một EntityManager nên không thấy conflict

Một persistence context có identity map riêng, không mô phỏng hai snapshots độc lập. Dùng hai contexts/transactions.

### 35.29. Kiểm thử chỉ assert exception, không kiểm tra database state

Cần xác nhận transaction rollback và dữ liệu cuối đúng. Một exception không tự bảo đảm nghiệp vụ không có side effect.

### 35.30. Chỉ test trên H2 rồi khẳng định mọi DB có cùng lock timing

Thời điểm conflict, isolation, deadlock/timeout behavior có thể khác. Với concurrency quan trọng, test target database/provider.

## 36. Bảng quyết định thực tế

| Tình huống | Hướng xử lý ưu tiên | Vì sao |
|---|---|---|
| Người dùng sửa một entity, conflict hiếm | Managed entity + `@Version` | Có optimistic check tự nhiên |
| Form chỉnh sửa có dữ liệu stale | API expectedVersion hoặc ETag/If-Match | Tránh ghi đè dựa trên bản cũ |
| Transaction chỉ đọc nhưng phải phát hiện entity thay đổi | `LockModeType.OPTIMISTIC` khi phù hợp | Yêu cầu optimistic check có chủ đích |
| Cần buộc version root tăng | `OPTIMISTIC_FORCE_INCREMENT` | Điều chỉnh concurrency token theo workflow |
| Cập nhật hàng loạt với JPQL | Bulk UPDATE + manual version strategy nếu cần | Bulk bỏ qua entity-level version handling |
| Bulk DELETE cần expected version | WHERE ID + version; diễn giải count | Không có automatic per-entity check như remove |
| Raw JDBC/native SQL writer | Check/increment version theo quy tắc đã thống nhất | Tránh phá concurrency contract |
| Tranh chấp nóng trên một row | Đo conflict; cân nhắc atomic SQL/pessimistic locks/partitioning | Optimistic retries có thể tốn |
| Cần bảo vệ uniqueness SKU | Database UNIQUE constraint | Version không bảo vệ duplicate inserts |
| Invariant nhiều rows | Isolation/locking/constraint/aggregate design | Version một entity không đủ |
| Cập nhật child cần parent version tăng | Root workflow + force increment/mapping phù hợp | Không tự xảy ra trong mọi association |
| Conflict xảy ra | Rollback, reload, retry có giới hạn hoặc báo conflict | Không dùng stale transaction |
| External payment/email | Outbox/after-commit/idempotency | Version không rollback side effect ngoài DB |
| Cần audit lịch sử | Audit log/revision table/event log | Version không lưu các bản dữ liệu cũ |

## 37. Bài tập thực hành có lời giải gợi ý

### Bài 1 — Tạo version field

**Yêu cầu:** Thêm version mapping cho entity Product.

**Gợi ý:**

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

Đặt đúng theo field/property access strategy của entity.

### Bài 2 — Hai transaction đọc cùng phiên bản

A và B đều đọc Item#42 version 7. A commit update thành version 8. B muốn update theo version 7.

**Kết luận:** B cần nhận optimistic conflict theo entity-level version strategy, không ghi đè im lặng.

### Bài 3 — Version có phải @Id không?

**Đáp án:** Không. ID là persistent identity; version là concurrency token của entity đó.

### Bài 4 — Tự tăng version

```java
item.setVersion(item.getVersion() + 1);
```

**Câu hỏi:** Có nên làm?

**Đáp án:** Không với managed entity `@Version` thông thường. Provider chịu trách nhiệm.

### Bài 5 — Long hay Timestamp?

**Yêu cầu:** Chọn kiểu phiên bản cho hệ thống có cập nhật nhanh, cần khả chuyển.

**Gợi ý:** `Long` thường đơn giản hơn timestamp do tránh precision/clock issues. Vẫn đối chiếu target JPA spec/provider.

### Bài 6 — Mapped superclass

**Yêu cầu:** Chia sẻ version mapping giữa Order và Product.

**Gợi ý:** Đặt một `@Version Long version` trong một `@MappedSuperclass` phù hợp, không khai báo lại trong subclass.

### Bài 7 — Hai @Version

Base entity đã có version, subclass thêm một version nữa.

**Kết luận:** Không phải mapping portable/hợp lý của entity hierarchy; chỉ dùng một version attribute.

### Bài 8 — UPDATE SQL có điều kiện

Viết SQL cập nhật quantity nếu Item ID=42 đang version 7.

**Gợi ý:**

```sql
UPDATE inventory_item
SET available_quantity = ?,
    row_version = row_version + 1
WHERE id = 42 AND row_version = 7;
```

### Bài 9 — Đọc số row update

Query manual bulk có expectedVersion nhưng affected=0.

**Câu hỏi:** Có chắc là stale version không?

**Gợi ý:** Không; có thể không tồn tại hoặc các điều kiện khác không khớp. Phải diễn giải theo toàn bộ WHERE.

### Bài 10 — Exception xuất hiện lúc nào?

`em.merge(detached)` không ném exception, nhưng `commit` thất bại vì stale version.

**Kết luận:** Đây là tình huống cần dự đoán; optimistic conflict không buộc phải được phát hiện ngay tại merge.

### Bài 11 — Flush thành công

`em.flush()` thành công, nhưng một câu SQL sau đó gây rollback.

**Câu hỏi:** Dữ liệu versioned update đã được commit chưa?

**Đáp án:** Chưa, vì flush không phải commit.

### Bài 12 — Managed entity update

`em.find` → `item.reserve(2)` → commit.

**Câu hỏi:** Có cần gọi `em.merge(item)` không?

**Đáp án:** Không, nếu item vẫn managed trong context và transaction phù hợp.

### Bài 13 — Detached entity

Một entity đọc trước có version 5; database hiện version 6.

**Câu hỏi:** Nếu merge detached entity và flush/commit sẽ có gì?

**Gợi ý:** Có thể phát hiện optimistic conflict. Dùng managed copy trả từ merge, không sửa detached và mong dirty checking.

### Bài 14 — LockModeType.OPTIMISTIC

**Yêu cầu:** Đọc entity với optimistic lock có chủ đích.

```java
InventoryItem item =
    em.find(
        InventoryItem.class,
        id,
        LockModeType.OPTIMISTIC
    );
```

### Bài 15 — Force increment

**Câu hỏi:** Mode nào yêu cầu tăng version khi cần biểu thị concurrency change của root?

**Đáp án:** `LockModeType.OPTIMISTIC_FORCE_INCREMENT`.

### Bài 16 — Bulk JPQL UPDATE

```jpql
update InventoryItem i
set i.availableQuantity = 100
where i.id = :id
```

**Câu hỏi:** `@Version` tự tăng không?

**Đáp án:** Không theo entity-level bulk semantics. Cần manual version strategy hoặc managed entity update.

### Bài 17 — Manual bulk version

**Yêu cầu:** Viết JPQL bulk update có expectedVersion và numeric increment.

**Gợi ý:**

```jpql
update InventoryItem i
set i.availableQuantity = :qty,
    i.version = i.version + 1
where i.id = :id
  and i.version = :expected
```

### Bài 18 — Version mismatch không ném tự động ở bulk

Manual bulk UPDATE affected=0.

**Câu hỏi:** JPA có nhất thiết ném `OptimisticLockException` không?

**Đáp án:** Không. Service phải diễn giải count và đưa ra domain outcome.

### Bài 19 — Native SQL

Một job raw JDBC chỉ UPDATE quantity theo ID.

**Câu hỏi:** Có bảo vệ concurrency token của JPA không?

**Gợi ý:** Không. Cần thống nhất version check/increment hoặc hạn chế writer.

### Bài 20 — Two writers

Cùng database có Hibernate và một script admin cập nhật hàng tồn.

**Gợi ý:** Kiểm tra script tuân thủ row_version; nếu không, `@Version` riêng phía Hibernate không đủ.

### Bài 21 — Parent và child

Sửa OrderLine.quantity nhưng không sửa Order.

**Câu hỏi:** Order.version có chắc chắn tăng?

**Gợi ý:** Không; phụ thuộc mapping/owning side/provider và aggregate workflow. Cân nhắc force increment hoặc strategy rõ.

### Bài 22 — Unique SKU

Hai requests cùng tạo Product mới có SKU giống nhau.

**Câu hỏi:** `@Version` bảo vệ được không?

**Gợi ý:** Không thay UNIQUE constraint.

### Bài 23 — Write skew

Hai doctors rời ca trên hai rows khác nhau, mỗi row có version.

**Câu hỏi:** Vì sao version riêng từng row có thể không đủ?

**Gợi ý:** Không có concurrent modification trên cùng row, nhưng invariant tổng thể bị vi phạm. Cần isolation/locking/constraint/aggregate guard.

### Bài 24 — Retry

A reserve(3) trước, B reserve(4) sau nhưng B dùng snapshot cũ 10.

**Câu hỏi:** B có nên retry bằng cách gán quantity=6?

**Đáp án:** Không. B phải reload quantity=7 và tính lại thành 3, nếu business rule vẫn cho phép.

### Bài 25 — Retry trong transaction bị rollback

**Câu hỏi:** Có thể tiếp tục gọi `em.find` và `flush` trên chính transaction đã ném `OptimisticLockException` không?

**Gợi ý:** Không nên; rollback rồi bắt đầu transaction/context mới.

### Bài 26 — Trả HTTP status

API PATCH dùng `If-Match` với ETag stale.

**Gợi ý:** Có thể trả `412 Precondition Failed` theo conditional request contract; nếu diễn đạt domain conflict không dựa HTTP precondition, `409 Conflict` có thể phù hợp.

### Bài 27 — ETag bằng version

**Câu hỏi:** Một Long version có tự trở thành HTTP ETag không?

**Đáp án:** Không. API phải định nghĩa representation/concurrency token và HTTP semantics phù hợp.

### Bài 28 — Audit

Entity version tăng từ 4 lên 5.

**Câu hỏi:** Có thể truy vấn lại state version 4 từ `@Version` không?

**Gợi ý:** Không tự động; cần audit/history system riêng.

### Bài 29 — Test xung đột

**Yêu cầu:** Viết test hai transaction cùng đọc version 7, A commit trước, B ghi sau.

**Gợi ý:** Dùng hai `EntityManager` độc lập, tạo stale snapshots, assert conflict/rollback và verify database state trong EntityManager mới.

### Bài 30 — SQL trigger

Một trigger DB cũng tăng row_version, trong khi JPA @Version đang tăng.

**Câu hỏi:** Rủi ro gì?

**Gợi ý:** Hai cơ chế có thể xung đột/double-increment. Cần một chiến lược được mapping hỗ trợ, test theo provider/database thật.

### Bài 31 — Cache và read freshness

Một entity đã managed ở version 7; transaction khác commit version 8. Gọi `find` lần nữa trong cùng persistence context.

**Gợi ý:** Không tự đảm bảo nhận version 8 vì identity map. Khi cần fresh state, dùng refresh/context mới/isolation phù hợp.

### Bài 32 — Tồn kho âm

Hai requests cùng reserve quantity trên cùng Item.

**Câu hỏi:** Version có thay CHECK constraint và business validation không?

**Đáp án:** Không. Cần kiểm tra availableQuantity, có thể kèm database CHECK/atomic conditional update.

### Bài 33 — Email sau flush

`em.flush()` thành công rồi gửi email, nhưng transaction rollback ở bước sau.

**Câu hỏi:** Sai ở đâu?

**Gợi ý:** External notification xảy ra trước commit. Dùng outbox/after-commit/idempotency.

### Bài 34 — Phân loại xung đột

Một câu UPDATE báo UNIQUE constraint violation.

**Câu hỏi:** Có phải OptimisticLockException không?

**Gợi ý:** Không tự động. Đây là lỗi ràng buộc uniqueness, xử lý và retry khác với stale version.

### Bài 35 — Chọn optimistic hay pessimistic

Một row bị hàng trăm workers update mỗi giây và liên tục gặp version conflict.

**Gợi ý:** Đo thực tế; cân nhắc atomic SQL update, partitioning, queue coordination hoặc pessimistic locking thay vì tăng retry vô hạn.

## 38. Checklist mapping @Version trong dự án

Khi triển khai optimistic locking cho một entity, hãy đảm bảo:

- [ ] Có một `@Version` rõ ràng trong entity/hierarchy phù hợp.
- [ ] Annotation nằm đúng vị trí theo field/property access strategy.
- [ ] Kiểu version được JPA provider/database mục tiêu hỗ trợ.
- [ ] Cột version được ánh xạ ở primary table theo mục tiêu portable.
- [ ] Schema có version column và dữ liệu legacy đã được backfill.
- [ ] Không để client/service tùy tiện sửa hoặc reset version.
- [ ] Mọi writer quan trọng đều theo version strategy hoặc bị giới hạn quyền ghi.
- [ ] Managed entity update được thực hiện trong transaction thích hợp.
- [ ] Các bulk JPQL/Criteria/native DML có strategy version riêng nếu cần.
- [ ] Transaction rollback khi optimistic conflict và không tái dùng stale persistence context.
- [ ] Retry, nếu có, reload state và chạy lại business decision.
- [ ] Retry giới hạn, có observability và không lặp external side effects.
- [ ] Business invariants nhiều rows được bảo vệ bằng cơ chế bổ sung.
- [ ] Có UNIQUE/FK/CHECK constraints phù hợp thay vì chỉ dựa vào version.
- [ ] Có integration tests với hai EntityManager/transactions độc lập.
- [ ] Test kiểm tra final database state, rollback và exception timing.
- [ ] Test trên database/provider thật khi concurrency quan trọng.
- [ ] API có policy xử lý conflict/expectedVersion/ETag rõ.
- [ ] Các cache/provider extensions và triggers không phá version contract.

Đây là checklist triển khai mà người học có thể dùng trong dự án; **không phải lượt Content QA tự động đối với bài Markdown**.

## 39. Bảng tra cứu nhanh

| Câu hỏi | Câu trả lời cốt lõi |
|---|---|
| Annotation tạo version mapping? | `@Version` |
| Namespace Jakarta? | `jakarta.persistence.Version` |
| ID có thay version không? | Không; `@Id` và `@Version` có vai trò khác nhau |
| Kiểu thường dùng? | `Long` hoặc numeric type được JPA hỗ trợ |
| JPA có tự quản lý version? | Có với entity-level versioned lifecycle phù hợp |
| Business code có nên version++? | Không |
| Khi nào check version? | Provider có thể check tại flush/commit/merge/lock tương ứng |
| Khi version stale? | Thường `OptimisticLockException` theo entity-level contract |
| Conflict có rollback transaction? | Cần rollback/không tiếp tục transaction lỗi |
| Retry ở đâu? | Transaction mới + reload + re-evaluate domain |
| Version là khóa bi quan? | Không |
| Có cần @Transactional? | Cần transaction ghi phù hợp cho update/locking |
| flush có phải commit? | Không |
| merge detached entity có dùng version? | Có, stale version có thể bị phát hiện |
| remove có bảo vệ optimistic version không? | Có theo entity-level optimistic locking contract |
| JPQL bulk UPDATE tự tăng version? | Không theo entity-level version management |
| CriteriaUpdate tự tăng version? | Không theo entity-level version management |
| Native SQL tự check @Version? | Không |
| Manual numeric bulk pattern? | `WHERE version=:expected` và `SET version=version+1` |
| affected=0 trong bulk chắc là stale? | Không, có thể không tồn tại/không match điều kiện khác |
| Sửa child có tăng parent version? | Không tự đảm bảo trong mọi mapping |
| Có thể force increment version? | `OPTIMISTIC_FORCE_INCREMENT` |
| Có thể optimistic-lock khi đọc? | `LockModeType.OPTIMISTIC` |
| Version thay UNIQUE/FK/CHECK? | Không |
| Version lưu lịch sử dữ liệu? | Không |
| Version tự tạo HTTP ETag? | Không |
| Test concurrency tối thiểu? | Hai contexts/transactions cùng snapshot cũ và kiểm tra conflict |
| Dữ liệu mới sau conflict? | Đọc lại trong transaction/context mới |
| Có thể retry payment tùy ý? | Không; cần idempotency/outbox |

## 40. Tổng kết

Những nguyên tắc quan trọng nhất:

1. **`@Version` ánh xạ một persistent attribute dùng làm concurrency token** để JPA phát hiện stale updates/deletes trên entity.
2. **`@Id` xác định entity identity**, còn **`@Version` xác định phiên bản trạng thái** đã đọc để kiểm tra khi ghi.
3. **Provider quản lý việc kiểm tra/tăng version trong entity-level lifecycle**; business code không nên tự sửa version.
4. **Numeric `Long` thường phù hợp** cho optimistic version column; kiểu timestamp cần đặc biệt chú ý precision và target provider.
5. **Đặt annotation đúng access strategy** và giữ version ở primary table theo mục tiêu portable.
6. **Hai transaction cùng đọc version cũ có thể xung đột khi ghi**; một bên thường phải rollback/retry hoặc báo conflict.
7. **Exception có thể xuất hiện tại flush/commit/merge/lock**, không chỉ ở lệnh setter hoặc `merge`.
8. **Flush thành công không đồng nghĩa commit thành công**, nên không dùng nó để phát external side effects không thể rollback.
9. **`OptimisticLockException` thường đòi hỏi rollback**; retry đúng phải dùng transaction/context mới và tính lại business logic.
10. **Bulk JPQL, CriteriaUpdate/Delete và native DML không tự thực hiện entity-level version handling**; phải có manual version strategy khi dùng chúng để sửa dữ liệu versioned.
11. **Version không tự bảo vệ cả aggregate graph, mọi child hoặc cross-row invariant**; cần phối hợp domain design, locking/isolation và database constraints.
12. **Version không thay authorization, uniqueness, audit history, ETag và idempotency**.
13. **Kiểm thử bằng hai EntityManager độc lập** cùng đọc bản cũ, kiểm tra optimistic conflict và final database state trên database/provider mục tiêu.
14. **Lựa chọn chiến lược concurrency theo workload**: optimistic locking hiệu quả khi conflict hiếm; với hot rows phải đo contention và cân nhắc phương án khác.

**Kết luận:** Ánh xạ một thuộc tính bằng `@Version` là bước nền tảng để JPA quản lý **khóa lạc quan** trên entity. Chỉ một annotation có thể giúp phát hiện trường hợp transaction đang cố ghi lên trạng thái cũ, nhưng hiệu quả thực tế phụ thuộc việc tất cả writers tuân thủ version contract, transaction được xử lý đúng và ứng dụng biết làm gì khi có conflict. Khi kết hợp `@Version` với domain validation, constraints, security, retry có giới hạn và integration tests đồng thời, hệ thống có thể giảm đáng kể nguy cơ **lost update** mà không cần giữ khóa bi quan dài hạn cho mọi thao tác đọc.
