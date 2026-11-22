# Kiểm thử khóa ghép, kế thừa và đối tượng giá trị trong JPA

Một entity chỉ dùng khóa chính `Long id`, không có kế thừa và chỉ chứa các trường kiểu chuỗi/số thường tương đối dễ kiểm thử. Khi mô hình phức tạp hơn với **khóa ghép**, **entity inheritance** hoặc **value objects**, một bài test chỉ gọi `em.persist(entity)` rồi kiểm tra `entity.getId()` thường không đủ để phát hiện những lỗi quan trọng:

- Hai entity khác nhau được coi là cùng định danh do `equals()/hashCode()` của composite key sai.
- Khóa ghép đọc đúng trong cùng persistence context nhưng thất bại sau khi đóng rồi mở context mới.
- `@MapsId` lưu foreign key khác với thành phần primary key mà model mong đợi.
- Một subclass lưu thành công nhưng JPQL polymorphic query trả thiếu bản ghi.
- `@Inheritance(strategy = JOINED)` tạo bảng subtype nhưng bảng quan hệ phụ không có dữ liệu đúng.
- Một `@Embeddable` ở hai vị trí bị ánh xạ trùng tên cột do thiếu `@AttributeOverride`.
- Cập nhật object value không được ghi xuống database như kỳ vọng.
- `@ElementCollection` chạy đúng khi đọc lần đầu nhưng thiếu/xóa thừa rows sau update.
- Một test đi qua bộ nhớ cấp một của JPA và vô tình **không kiểm tra database**.

Những vấn đề này có thể chỉ xuất hiện khi **flush**, khi EntityManager bị **clear**, khi **commit**, khi truy vấn đa hình hoặc khi dùng schema/driver khác với database in-memory trong test.

Bài học này thuộc chương **Kiểm thử JPA** của module *Data Persistence Relational Access ORM JPA*. Ta sẽ xây dựng các test cases có thể tái lập, từ unit test thuần Java tới integration test chạy trên hệ quản trị gần production, đồng thời phân biệt hành vi do chuẩn JPA quy định với phần phụ thuộc Hibernate, Spring Data JPA hoặc database dialect.

> **Nguyên tắc xuyên suốt:** Test JPA tốt không chỉ chứng minh “entity object có dữ liệu đúng”. Nó phải chứng minh **persistent identity đúng**, **mapping xuống các bảng/cột đúng**, **đọc lại trong persistence context mới đúng**, và **ràng buộc nghiệp vụ vẫn đúng khi flush/commit hoặc nhiều transaction cùng truy cập**.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Thiết kế unit test cho `@Embeddable` composite key với `equals`/`hashCode` ổn định.
2. Viết integration test cho `@EmbeddedId`, `@IdClass` và khóa được dẫn xuất bằng `@MapsId`.
3. Phân biệt object identity Java, persistent identity JPA và primary key constraint của database.
4. Kiểm tra uniqueness của khóa ghép theo toàn bộ thành phần key.
5. Kiểm tra quan hệ chứa composite foreign key và mapping `@JoinColumns`.
6. Nhận diện lỗi do chỉnh sửa key của managed entity hoặc dùng generated ID strategy không phù hợp.
7. Test cả ba chiến lược inheritance: `SINGLE_TABLE`, `JOINED` và `TABLE_PER_CLASS`.
8. Viết JPQL polymorphic queries với root class, `TYPE` và `TREAT` ở phạm vi được hỗ trợ.
9. Phân biệt `@MappedSuperclass` với entity inheritance.
10. Kiểm tra `@Embeddable`/`@Embedded`, `@AttributeOverride` và nested value objects.
11. Kiểm tra persistence semantics của `@ElementCollection` và `AttributeConverter`.
12. Thiết kế bộ test bao phủ nulls, embedded replacement, collection update và immutable value patterns.
13. Dùng `flush`, `clear`, transaction boundary và EntityManager mới để kiểm tra dữ liệu thực.
14. Chọn Testcontainers/schema migration thay vì dựa hoàn toàn vào H2 khi cần kiểm tra dialect/schema behavior.
15. Giữ isolation giữa tests, quan sát SQL, assertions trên PK/FK/UNIQUE constraints và kiểm thử concurrency.
16. Lập test matrix cân bằng correctness, mapping portability, hiệu năng và regression protection.

## 2. Ba lớp kiểm thử cần kết hợp

| Lớp | Kiểm tra gì? | Có cần database? |
|---|---|---|
| Unit test thuần Java | Composite key equality/hash; value-object validation/equality; domain invariants | Không |
| JPA integration test | Mapping annotations, generated SQL, flush/clear, persistence context, JPQL, schema | Có |
| Database integration/concurrency test | PK/FK/UNIQUE, isolation, generated IDs, index/schema portability, multi-transaction | Có, nên cùng loại DB đích |

Ví dụ `StockId.equals()` là logic Java: một unit test không cần JPA. Ngược lại, chỉ unit test `equals()` không chứng minh `@EmbeddedId` ánh xạ đúng vào `PRIMARY KEY(tenant_id,sku)`.

### 2.1. Vì sao mock EntityManager không đủ?

Mock có thể xác nhận `em.persist(stock)` được gọi, nhưng không tạo bảng, không phát SQL, không xác thực khóa ghép, không ném lỗi FK từ database và không kiểm tra JPQL polymorphism.

### 2.2. Vì sao test một persistence context chưa đủ?

Khi gọi `em.find` ngay sau `em.persist`, persistence context có thể trả lại chính managed instance đã lưu trong cache cấp một, ngay cả khi chưa có câu SQL INSERT hoàn chỉnh.

### 2.3. Vì sao test chỉ commit cũng có thể khó chẩn đoán?

Commit có thể flush và ném lỗi muộn. Test rõ ràng nên tách các điểm quan sát: entity state, `flush`, `clear`, load lại, commit và transaction mới khi yêu cầu kiểm tra durability.

---

## 3. Tập mô hình được dùng trong bài

Ta sử dụng ba nhóm model độc lập:

1. **Inventory:** `WarehouseStock` có khóa ghép `StockId(tenantId, sku)`; `StockMovement` tham chiếu khóa đó.
2. **Payment:** `Payment` là entity base class, `CardPayment` và `BankTransferPayment` là subclasses; so sánh các inheritance strategies.
3. **CustomerProfile:** chứa hai `PostalAddress` value objects; `OrderNote` hoặc `CustomerProfile` chứa `@ElementCollection` các giá trị phụ.

Sơ đồ:

```text
StockId(tenantId, sku)              Payment (entity root)
          |                          /                \
          v                         /                  \
 WarehouseStock                  CardPayment     BankTransferPayment
          ^
          |
     StockMovement (@MapsId / composite FK)

CustomerProfile
    |
    +-- @Embedded billingAddress: PostalAddress
    +-- @Embedded shippingAddress: PostalAddress
    +-- @ElementCollection contacts: Set<ContactMethod>
```

Các class là ví dụ độc lập về model; không cần kết hợp hết vào một schema production. Những đoạn SQL DDL là biểu diễn mong muốn, không khẳng định mọi JPA provider sinh đúng từng tên hoặc kiểu cột theo mặc định.

---

# Phần I — Khóa ghép

## 4. Khóa ghép là gì?

Một entity có composite key được nhận diện bằng **tổ hợp** nhiều thuộc tính.

Ví dụ một SKU có thể lặp ở tenant khác:

| tenant_id | sku | quantity |
|---|---|---:|
| shop-a | BOOK-JPA | 50 |
| shop-b | BOOK-JPA | 12 |
| shop-a | BOOK-SPRING | 20 |

Khóa chính logic:

```sql
PRIMARY KEY (tenant_id, sku)
```

Không có vấn đề khi `sku` giống nhau giữa hai tenant, nhưng không thể có hai rows cùng `(tenant_id,sku)`.

### 4.1. Khóa ghép không giống UNIQUE nghiệp vụ thông thường

Nếu entity có `@Id Long id` và `UNIQUE(tenant_id,sku)`, persistent identity JPA vẫn là `id`. Nếu dùng `@EmbeddedId StockId`, persistent identity chính là tuple hai thành phần.

### 4.2. Hai dạng mapping phổ biến

- `@EmbeddedId`: một object value chứa toàn bộ key.
- `@IdClass`: các ID fields được khai trên entity; một ID class riêng diễn tả khóa.

Hai kiểu có ưu/nhược điểm trong JPQL, API model và khả năng reuse. Không trộn chúng cho cùng entity nếu không có lý do và mapping tương ứng hợp lệ.

### 4.3. Khóa không nên bị sửa sau khi entity đã managed

Một persistent identity phải ổn định. Đổi `tenantId` hoặc `sku` trong ID object đã được dùng để quản lý entity có thể làm identity map bị sai lệch và có behavior không được hỗ trợ/không portable.

---

## 5. Entity khóa ghép với @EmbeddedId

ID type:

```java
package com.example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class StockId implements Serializable {

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "sku", nullable = false, length = 80)
    private String sku;

    protected StockId() {
        // JPA provider
    }

    public StockId(String tenantId, String sku) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant required");
        }
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU required");
        }
        this.tenantId = tenantId;
        this.sku = sku;
    }

    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof StockId other)) return false;
        return Objects.equals(tenantId, other.tenantId)
            && Objects.equals(sku, other.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku);
    }
}
```

Entity:

```java
package com.example.inventory;

import jakarta.persistence.*;

@Entity
@Table(name = "warehouse_stock")
public class WarehouseStock {

    @EmbeddedId
    private StockId id;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Version
    @Column(name = "row_version")
    private Long version;

    protected WarehouseStock() {}

    public WarehouseStock(StockId id, int quantity) {
        if (id == null) {
            throw new IllegalArgumentException("ID required");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("Negative quantity");
        }
        this.id = id;
        this.quantity = quantity;
    }

    public StockId getId() { return id; }
    public int getQuantity() { return quantity; }
    public Long getVersion() { return version; }

    public void replenish(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be > 0");
        }
        quantity = Math.addExact(quantity, amount);
    }
}
```

### 5.1. DDL mong đợi

```sql
CREATE TABLE warehouse_stock (
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    row_version BIGINT,
    CONSTRAINT pk_warehouse_stock PRIMARY KEY (tenant_id, sku)
);
```

Trong production, migration/schema authority quyết định DDL thực. `@Column(nullable=false)` không thay việc xác nhận table PK được tạo đúng.

### 5.2. Vì sao equals/hashCode cần cả hai fields?

Nếu chỉ dùng `sku`, hai IDs `(shop-a,BOOK-JPA)` và `(shop-b,BOOK-JPA)` bị coi bằng nhau, gây lỗi với `HashSet`, `HashMap` và code dùng ID equality.

### 5.3. Tính bất biến

`StockId` ở trên không có setters công khai. JPA vẫn cần khả năng gán fields khi hydrate. Không thay đổi fields qua reflection hoặc thêm setter rồi mutate khi entity đã managed.

### 5.4. Quy tắc Serializable

ID classes của JPA cần tuân thủ yêu cầu về tính serializable/equality và constructor theo mapping/spec áp dụng. Đây là lý do `StockId implements Serializable`, có protected no-arg constructor và equality dựa trên các thành phần khóa.

---

## 6. Unit test equality của khóa ghép

JUnit 5:

```java
import org.junit.jupiter.api.Test;
import java.util.HashMap;
import static org.junit.jupiter.api.Assertions.*;

class StockIdTest {

    @Test
    void equalKeysHaveEqualHashCodes() {
        StockId a = new StockId("shop-a", "BOOK-JPA");
        StockId b = new StockId("shop-a", "BOOK-JPA");

        assertNotSame(a, b);
        assertEquals(a, b);
        assertEquals(a.hashCode(), b.hashCode());
    }

    @Test
    void allComponentsParticipateInEquality() {
        StockId a = new StockId("shop-a", "BOOK-JPA");
        StockId b = new StockId("shop-b", "BOOK-JPA");
        StockId c = new StockId("shop-a", "BOOK-SPRING");

        assertNotEquals(a, b);
        assertNotEquals(a, c);
    }

    @Test
    void usableAsHashMapKey() {
        var lookup = new HashMap<StockId, Integer>();
        lookup.put(new StockId("shop-a", "BOOK-JPA"), 50);

        assertEquals(
            50,
            lookup.get(new StockId("shop-a", "BOOK-JPA"))
        );
    }
}
```

### 6.1. Những test nên bổ sung

- `equals(null)` trả `false`.
- So với object khác type trả `false`.
- `equals` phản xạ/đối xứng/bắc cầu với input hợp lệ.
- Hash code không thay đổi khi object đang là key của `HashMap`.
- Normalization của SKU (case/trim) được quy định ở domain trước khi tạo `StockId`.

### 6.2. Equality Java khác equality database về collation

Nếu DB sử dụng case-insensitive collation nhưng Java `String.equals` phân biệt chữ hoa/thường, `"book-jpa"` và `"BOOK-JPA"` có thể được DB coi là trùng tùy cấu hình. **Phải thiết kế canonicalization hoặc DB constraint phù hợp**, không coi unit test equality là chứng minh uniqueness theo database.

---

## 7. Integration test cơ bản: persist → flush → clear → find

Phép thử quan trọng nhất:

```java
@Test
void embeddedIdSurvivesPersistenceContextClear() {
    StockId id = new StockId("shop-a", "BOOK-JPA");

    WarehouseStock stock = new WarehouseStock(id, 7);
    em.persist(stock);
    em.flush();
    em.clear();

    WarehouseStock reloaded =
        em.find(WarehouseStock.class, id);

    assertNotNull(reloaded);
    assertEquals(id, reloaded.getId());
    assertEquals(7, reloaded.getQuantity());
}
```

Đoạn test giả định một EntityManager `em` đang tham gia transaction test và schema đã được chuẩn bị.

### 7.1. Vai trò của flush

`flush` đồng bộ SQL pending với database trong transaction. Các constraint thường có thể được phát hiện tại đây, dù một số deferred constraints có thể được kiểm tra tại commit.

### 7.2. Vai trò của clear

`clear` loại managed instances khỏi persistence context. Lần `find` sau phải đi qua đường tải dữ liệu khác với việc trả ngay object đã managed trong L1.

### 7.3. Flush + clear vẫn chưa phải commit

Nếu test dùng `@Transactional` rồi rollback cuối test, test trên chứng minh mapping đọc lại được trong **cùng transaction**, không chứng minh row durable sau commit.

### 7.4. Muốn chứng minh durability

Tạo một transaction, commit, mở transaction/EntityManager khác và query lại. Đừng coi kết quả trong cùng transaction là bằng chứng data đã commit.

---

## 8. Test tìm kiếm và JPQL với @EmbeddedId

JPQL truy cập path các thành phần ID:

```java
List<WarehouseStock> found = em.createQuery(
    """
    select s
    from WarehouseStock s
    where s.id.tenantId = :tenant
      and s.id.sku = :sku
    """,
    WarehouseStock.class
)
.setParameter("tenant", "shop-a")
.setParameter("sku", "BOOK-JPA")
.getResultList();
```

Assertions:

```java
assertEquals(1, found.size());
assertEquals(
    new StockId("shop-a", "BOOK-JPA"),
    found.get(0).getId()
);
```

### 8.1. Không query theo tên cột SQL trong JPQL

`s.id.tenantId` là entity attribute path; `tenant_id` là database column name. JPQL dùng tên attributes của entity model.

### 8.2. Test theo một phần khóa

Một query `where s.id.tenantId = :tenant` có thể trả nhiều stocks. Đừng dùng `getSingleResult` trừ khi uniqueness predicate thật sự đủ.

### 8.3. Tenant security

Một request với SKU nhưng thiếu `tenantId` trong filter có thể lấy stock tenant khác. Thêm integration tests với hai tenant có cùng SKU.

### 8.4. Query cache có thể che SQL behavior

Nếu đang đo query count, cần kiểm soát L1/L2/query cache. Với test correctness, quan trọng là data/tenant scope đúng.

---

## 9. Test uniqueness của toàn bộ khóa ghép

Thiết lập:

```text
Existing:
  (tenant_id='shop-a', sku='BOOK-JPA')

Attempt:
  (tenant_id='shop-a', sku='BOOK-JPA') -> conflict

Allowed:
  (tenant_id='shop-b', sku='BOOK-JPA')
  (tenant_id='shop-a', sku='BOOK-SPRING')
```

### 9.1. Test Java identity collision và DB PK collision riêng

Nếu gọi `persist` hai different entities cùng key trong **một EntityManager**, provider có thể phát hiện conflict trước SQL.

Nếu muốn test DB constraint, hãy:

1. Persist row đầu trong transaction A và commit.
2. Tạo EntityManager B mới, không có managed instance cùng key.
3. Cố persist row thứ hai.
4. Quan sát exception khi `persist`/`flush`/`commit`.
5. Rollback transaction B.
6. Mở context mới xác minh chỉ có một committed row.

### 9.2. Không assert cứng mọi provider đều ném EntityExistsException

Có thể là `EntityExistsException`, provider-specific persistence exception, JDBC/constraint wrapper hoặc Spring `DataIntegrityViolationException` tùy timing/translation. Nên assert **ngữ nghĩa conflict**, DB state và exception class phù hợp stack mục tiêu.

### 9.3. Transaction lỗi không tiếp tục như bình thường

Sau flush/commit failure, transaction có thể rollback-only/aborted. Không catch rồi gọi tiếp repository trong cùng transaction để “xem còn dữ liệu gì”.

### 9.4. Unique constraints phải tồn tại thật

Nếu schema production do Flyway/Liquibase quản lý, test cần dùng migrations thực thay vì tin annotation tự tạo PK.

---

## 10. @IdClass: cách khai khóa ghép thứ hai

Một entity có ID attributes trực tiếp:

```java
import jakarta.persistence.*;
import java.io.Serializable;
import java.util.Objects;

public class StockIdClass implements Serializable {

    private String tenantId;
    private String sku;

    public StockIdClass() {}

    public StockIdClass(String tenantId, String sku) {
        this.tenantId = tenantId;
        this.sku = sku;
    }

    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }

    @Override
    public boolean equals(Object object) {
        if (this == object) return true;
        if (!(object instanceof StockIdClass other)) return false;
        return Objects.equals(tenantId, other.tenantId)
            && Objects.equals(sku, other.sku);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku);
    }
}

@Entity
@IdClass(StockIdClass.class)
@Table(name = "warehouse_stock_idclass")
public class StockWithIdClass {

    @Id
    @Column(name = "tenant_id")
    private String tenantId;

    @Id
    @Column(name = "sku")
    private String sku;

    @Column(name = "quantity")
    private int quantity;

    protected StockWithIdClass() {}

    public StockWithIdClass(
            String tenantId,
            String sku,
            int quantity
    ) {
        this.tenantId = tenantId;
        this.sku = sku;
        this.quantity = quantity;
    }

    public int getQuantity() { return quantity; }
}
```

### 10.1. ID class phải khớp tên và kiểu

`StockIdClass` có `tenantId` và `sku` cùng tên/kiểu tương ứng ID attributes trên entity. Sai tên hoặc kiểu có thể gây mapping bootstrap error.

### 10.2. Khác cách viết JPQL

Với `@IdClass`, query thường là `s.tenantId` và `s.sku`; với `@EmbeddedId`, là `s.id.tenantId` và `s.id.sku`.

### 10.3. Khác cách gọi find

```java
StockWithIdClass stock = em.find(
    StockWithIdClass.class,
    new StockIdClass("shop-a", "BOOK-JPA")
);
```

### 10.4. Test matrix cho @IdClass

- Provider bootstrap được.
- Persist/flush/clear/find bằng ID object mới.
- Query theo cả hai `@Id` attributes.
- Không lẫn hai tenants trùng SKU.
- Duplicate key bị DB chặn.
- Class equality/hash code đúng.
- Schema có composite primary key.

### 10.5. Đừng giả định @IdClass và @EmbeddedId tự động tương đương mọi mapping

Các associations tham gia ID/derived identity có rules riêng. Chọn mapping theo model và kiểm tra JPQL/schema cụ thể.

---

## 11. Khóa ghép và @MapsId

Một dòng biến động kho `StockMovement` thuộc về một `WarehouseStock` và được đánh số `sequenceNo` theo stock.

Composite key ba phần:

```java
@Embeddable
public class MovementId implements Serializable {

    private String tenantId;
    private String sku;
    private Long sequenceNo;

    protected MovementId() {}

    public MovementId(
            String tenantId,
            String sku,
            Long sequenceNo
    ) {
        this.tenantId = tenantId;
        this.sku = sku;
        this.sequenceNo = sequenceNo;
    }

    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public Long getSequenceNo() { return sequenceNo; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof MovementId other)) return false;
        return Objects.equals(tenantId, other.tenantId)
            && Objects.equals(sku, other.sku)
            && Objects.equals(sequenceNo, other.sequenceNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, sku, sequenceNo);
    }
}
```

Mapping association to ID portion:

```java
@Entity
@Table(name = "stock_movement")
public class StockMovement {

    @EmbeddedId
    private MovementId id;

    @MapsId("stockKey")
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumns({
        @JoinColumn(
            name = "tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @JoinColumn(
            name = "sku",
            referencedColumnName = "sku"
        )
    })
    private WarehouseStock stock;

    @Column(name = "delta", nullable = false)
    private int delta;

    protected StockMovement() {}
}
```

**Quan trọng:** Đoạn `@MapsId("stockKey")` ở trên chỉ hợp lệ nếu `MovementId` thật sự có thuộc tính `stockKey` kiểu `StockId`. Với `MovementId` phẳng `tenantId` và `sku` như ví dụ phía trên, ta phải **đổi thiết kế ID cho khớp**. Đây là một chỗ rất dễ tạo mapping sai.

Thiết kế nhất quán hơn:

```java
@Embeddable
public class MovementId implements Serializable {

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "tenantId",
            column = @Column(name = "tenant_id")
        ),
        @AttributeOverride(
            name = "sku",
            column = @Column(name = "sku")
        )
    })
    private StockId stockKey;

    @Column(name = "sequence_no")
    private Long sequenceNo;

    protected MovementId() {}

    public MovementId(StockId stockKey, Long sequenceNo) {
        this.stockKey = stockKey;
        this.sequenceNo = sequenceNo;
    }

    public StockId getStockKey() { return stockKey; }
    public Long getSequenceNo() { return sequenceNo; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof MovementId other)) return false;
        return Objects.equals(stockKey, other.stockKey)
            && Objects.equals(sequenceNo, other.sequenceNo);
    }

    @Override
    public int hashCode() {
        return Objects.hash(stockKey, sequenceNo);
    }
}
```

Ở phiên bản **nhất quán** này, `@MapsId("stockKey")` ánh xạ phần `stockKey` của `MovementId` từ `WarehouseStock.id`. Code của `StockMovement` ở trên được hiểu là dùng **MovementId phiên bản thứ hai**, không phải cùng tồn tại hai class `MovementId`.

### 11.1. DDL mong đợi

```sql
CREATE TABLE stock_movement (
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    sequence_no BIGINT NOT NULL,
    delta INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, sku, sequence_no),
    CONSTRAINT fk_movement_stock
        FOREIGN KEY (tenant_id, sku)
        REFERENCES warehouse_stock(tenant_id, sku)
);
```

### 11.2. Ba assertions không thể bỏ qua

- PK movement là tuple `(tenant, sku, sequenceNo)`.
- Composite FK trỏ đúng `WarehouseStock(tenant,sku)`.
- Khi persist movement, ID components và association trùng nhau.

### 11.3. Không tự cấp sequenceNo bằng MAX+1 trong concurrency mà không kiểm soát

Hai transactions có thể cùng chọn sequenceNo. Nếu number allocation cần chính xác, thiết kế allocator/locking hoặc DB uniqueness và retry có trách nhiệm.

### 11.4. Không nhân bản writable mapping của cùng columns một cách tùy tiện

Nếu cả `@EmbeddedId` và `@JoinColumns` ghi cùng các columns mà không dùng `@MapsId`/rules phù hợp, Hibernate có thể báo repeated column mappings hoặc persistence inconsistency.

---

## 12. Test @MapsId và composite foreign key

Kịch bản:

1. Persist `WarehouseStock(id=(shop-a,BOOK-JPA))`.
2. Persist `StockMovement` với `MovementId(stockId,1)` và association tới Stock.
3. Flush và clear.
4. Find Movement bằng ID đầy đủ.
5. Đọc `movement.getStock().getId()`.
6. Xác nhận ID của association bằng `MovementId.stockKey`.
7. Query DB xác minh PK/FK columns.

Pseudo integration test:

```java
@Test
void movementReferencesExactlyMatchingStockKey() {
    StockId stockId = new StockId("shop-a", "BOOK-JPA");

    WarehouseStock stock = new WarehouseStock(stockId, 9);
    em.persist(stock);

    MovementId movementId = new MovementId(stockId, 1L);
    StockMovement movement =
        new StockMovement(movementId, stock, +3);

    em.persist(movement);
    em.flush();
    em.clear();

    StockMovement reloaded =
        em.find(StockMovement.class, movementId);

    assertNotNull(reloaded);
    assertEquals(
        stockId,
        reloaded.getStock().getId()
    );
    assertEquals(
        stockId,
        reloaded.getId().getStockKey()
    );
}
```

`new StockMovement(id,stock,delta)` và getters là API bổ sung hợp lý cho ví dụ entity, cần triển khai ở fixture/project. Các snippets này nhằm minh họa assertion strategy, không phải nguyên một source file có thể compile độc lập.

### 12.1. Test FK violation riêng

Cố lưu Movement trỏ Stock không tồn tại bằng đường mapping hợp lệ, rồi flush/commit: database phải từ chối nếu FK thật sự tồn tại.

### 12.2. Test sai tenant/sku

Stock tenant A không được tự động gắn Movement ID chứa tenant B. Application constructor/service nên giữ invariant này; nếu mapping không tự ngăn, thêm validation test.

### 12.3. Test cascade lifecycle

Nếu Movement dùng `CascadeType.PERSIST` đến một Stock đã tồn tại, cascade có thể cố persist shared parent không mong muốn. Thường nên gán managed reference cho independent Stock thay vì cascade create.

---

## 13. Test thay đổi khóa và tính ổn định của identity map

Một bài test âm rất quan trọng là xác nhận **domain không cho phép thay đổi key**.

```java
StockId key = new StockId("shop-a", "BOOK-JPA");
WarehouseStock stock = new WarehouseStock(key, 5);

em.persist(stock);
em.flush();
```

Không nên làm:

```java
// Giả sử có setter không an toàn:
stock.getId().setSku("BOOK-SPRING");
```

### 13.1. Vì sao sai?

Persistence context đã index entity theo original persistent identity. Thay ID bên trong managed object làm mapping/state invalid, có thể ném exception hoặc gây behavior không portable.

### 13.2. Kiểm thử bất biến bằng API design

- ID fields private.
- Không có public mutation methods.
- Constructor từ chối null/blank key parts.
- Nếu cần “đổi SKU”, thiết kế domain operation tạo identity mới và chuyển dữ liệu theo transaction/foreign-key rules.

### 13.3. Equality và mutable key là lỗi kép

Nếu key đang trong `HashSet` rồi `hashCode` thay đổi, collection Java cũng không thể tra cứu đúng. Đây là lý do composite key nên là value object ổn định.

---

## 14. Test quan hệ giữa @EmbeddedId và database column types

Các mapping:

```java
@Column(name = "tenant_id", length = 64)
private String tenantId;

@Column(name = "sku", length = 80)
private String sku;
```

không tự đảm bảo production schema chính xác. Test với migrations thật cần xác minh:

- `tenant_id`/`sku` đúng kiểu và kích thước.
- PK gồm cả hai columns, thứ tự có ý nghĩa với index performance.
- Composite FK trỏ cùng loại/chiều dài columns.
- Collation của SKU phù hợp domain.
- NOT NULL được thực thi.
- Không có unique constraint ngoài ý muốn chỉ trên `sku`.

### 14.1. Cùng DB engine quan trọng

H2 và PostgreSQL có thể khác ở case sensitivity, collation, constraint violation timing và generated SQL. Test integration về correctness nên chạy trên engine mục tiêu khi các yếu tố này ảnh hưởng.

### 14.2. Test Unicode/case/whitespace

SKU có phân biệt chữ hoa thường không? `"BOOK-JPA"` và `"book-jpa"` có được xem là một key không? Quyết định domain rồi test cả Java normalization và DB uniqueness.

### 14.3. Test tenant khác cùng SKU

Đây là case giúp phát hiện bỏ sót một column trong PK hoặc JPQL predicate.

---

## 15. Composite keys trong Spring Data JPA

Repository:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface WarehouseStockRepository
        extends JpaRepository<WarehouseStock, StockId> {
}
```

### 15.1. Repository ID type là StockId

`findById(new StockId("shop-a","BOOK-JPA"))`, không phải `findById("BOOK-JPA")`.

### 15.2. Phân biệt save và create-only

`repository.save` có thể chọn `persist` hoặc `merge` tùy `isNew` detection. Với assigned composite ID khác null, new entity có thể bị phân loại existing trừ khi dùng `@Version`/`Persistable`/custom new detection phù hợp.

### 15.3. Test SQL thực sự được dùng

Đừng chỉ assert repository returns entity; quan sát INSERT/UPDATE/SELECT behavior nếu create semantics quan trọng. `merge` không phải create-only operation an toàn cho mọi assigned ID.

### 15.4. DataJpaTest rollback

`@DataJpaTest` thường chạy test trong transaction và rollback cuối test. Đó là cách tốt để isolate fixtures, nhưng **không kiểm tra durability qua commit**. Để test commit/unique concurrency, cần transactions riêng có kiểm soát.

---

# Phần II — Kế thừa entity

## 16. Kế thừa Java và kế thừa JPA khác nhau

Java:

```java
abstract class Payment {
    // ...
}
class CardPayment extends Payment {
    // ...
}
class BankTransferPayment extends Payment {
    // ...
}
```

Nhưng JPA cần biết:

- Type nào là entity root?
- Strategy ánh xạ root/subtypes xuống bảng?
- Khóa chính dùng chung ra sao?
- Có discriminator column hay không?
- JPQL `from Payment p` trả subtypes như thế nào?
- Provider khởi tạo subtype nào khi đọc một row?
- Mỗi subtype có constraint/columns riêng không?

### 16.1. Ba chiến lược chính

| `@Inheritance` strategy | Bố trí bảng | Điểm cần kiểm thử |
|---|---|---|
| `SINGLE_TABLE` | Một table cho root và tất cả subclasses | Discriminator, nullable subtype columns, polymorphic read |
| `JOINED` | Root table và các subtype tables liên kết PK | PK/FK giữa bảng, joins, row reconstruction |
| `TABLE_PER_CLASS` | Mỗi concrete class có table | Polymorphic queries/UNION, globally unique IDs, schema |

### 16.2. Default strategy

Trong một entity inheritance hierarchy, nếu không khai `@Inheritance` rõ, JPA mặc định dùng `SINGLE_TABLE`. Với dự án quan trọng, nên khai rõ strategy để dễ đọc migration và tests.

### 16.3. Mapped superclass không giống inheritance root entity

`@MappedSuperclass` chia sẻ mappings cho subclasses, nhưng class đó không là entity được query trực tiếp bằng `from MappedBase` như polymorphic root entity.

---

## 17. Mô hình SINGLE_TABLE cho Payment

Base entity:

```java
package com.example.payment;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "payment")
@Inheritance(strategy = InheritanceType.SINGLE_TABLE)
@DiscriminatorColumn(
    name = "payment_kind",
    discriminatorType = DiscriminatorType.STRING,
    length = 24
)
public abstract class Payment {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "payment_id_generator"
    )
    @SequenceGenerator(
        name = "payment_id_generator",
        sequenceName = "payment_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Column(name = "amount", nullable = false, precision = 18, scale = 2)
    private BigDecimal amount;

    @Version
    @Column(name = "row_version")
    private Long version;

    protected Payment() {}

    protected Payment(String tenantId, BigDecimal amount) {
        this.tenantId = tenantId;
        this.amount = amount;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public BigDecimal getAmount() { return amount; }
}
```

Subtypes:

```java
@Entity
@DiscriminatorValue("CARD")
public class CardPayment extends Payment {

    @Column(name = "payment_token_ref")
    private String tokenReference;

    protected CardPayment() {}

    public CardPayment(
            String tenantId,
            BigDecimal amount,
            String tokenReference
    ) {
        super(tenantId, amount);
        this.tokenReference = tokenReference;
    }

    public String getTokenReference() {
        return tokenReference;
    }
}

@Entity
@DiscriminatorValue("BANK")
public class BankTransferPayment extends Payment {

    @Column(name = "bank_reference")
    private String bankReference;

    protected BankTransferPayment() {}

    public BankTransferPayment(
            String tenantId,
            BigDecimal amount,
            String bankReference
    ) {
        super(tenantId, amount);
        this.bankReference = bankReference;
    }

    public String getBankReference() {
        return bankReference;
    }
}
```

Không lưu số thẻ nguyên văn trong ví dụ. `tokenReference` là một surrogate reference có ranh giới an toàn riêng, không tự mặc định là public.

### 17.1. DDL mô hình

```sql
CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    payment_kind VARCHAR(24) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    row_version BIGINT,
    payment_token_ref VARCHAR(120),
    bank_reference VARCHAR(120)
);
```

### 17.2. Vì sao subtype columns có thể nullable?

Trong SINGLE_TABLE, CardPayment không có `bank_reference`, BankTransferPayment không có `payment_token_ref`. Một `NOT NULL` áp lên cả table cho cột chỉ dùng bởi một subtype có thể làm subtype khác không insert được. Có thể dùng DB CHECK constraint phụ thuộc discriminator nếu business yêu cầu.

### 17.3. Test không chỉ xét object subtype

Phải chứng minh discriminator value và subtype columns được ghi/read đúng, không lộ fields của subtype khác vào DTO.

---

## 18. Test SINGLE_TABLE round-trip và phân biệt subtype

```java
@Test
void cardPaymentRoundTripHasCorrectConcreteType() {
    CardPayment card = new CardPayment(
        "shop-a",
        new BigDecimal("120.50"),
        "token-ref-test"
    );

    em.persist(card);
    em.flush();

    Long id = card.getId();
    em.clear();

    Payment reloaded = em.find(Payment.class, id);

    assertInstanceOf(CardPayment.class, reloaded);
    CardPayment typed = (CardPayment) reloaded;

    assertEquals(
        new BigDecimal("120.50"),
        typed.getAmount()
    );
    assertEquals(
        "token-ref-test",
        typed.getTokenReference()
    );
}
```

### 18.1. assertInstanceOf yêu cầu JUnit version hỗ trợ

Ví dụ dùng JUnit Jupiter API; nếu dự án dùng JUnit cũ, dùng `assertTrue(reloaded instanceof CardPayment)`.

### 18.2. Test BankTransferPayment tương ứng

Một test khác persist `BankTransferPayment` rồi xác nhận `em.find(Payment.class,id)` trả concrete subtype đúng.

### 18.3. Đọc qua root entity rất quan trọng

Nếu chỉ `em.find(CardPayment.class,id)`, ta chưa kiểm tra đầy đủ polymorphic dispatch từ root class.

### 18.4. Query raw discriminator có thể bổ sung

Để khẳng định mapping schema, native SQL read `payment_kind`, không update raw discriminator trừ khi test explicit corruption handling.

---

## 19. Test JPQL polymorphic query

JPA query root:

```java
List<Payment> payments = em.createQuery(
    """
    select p
    from Payment p
    where p.tenantId = :tenant
    order by p.id
    """,
    Payment.class
)
.setParameter("tenant", "shop-a")
.getResultList();
```

Nếu đã persist một CardPayment và một BankTransferPayment trong tenant A, cần assert:

- Có đủ 2 payment entities.
- Cả hai có subclass đúng.
- Amount chính xác.
- Payment của tenant B không xuất hiện.

### 19.1. Root query trả về subclasses

Với entity inheritance mapping hợp lệ, query `from Payment` có tính đa hình theo entity hierarchy. Đây là khác biệt với `@MappedSuperclass`.

### 19.2. Không dựa vào thứ tự nếu không có ORDER BY

JPA result order không được bảo đảm theo insertion order. Nếu assertions yêu cầu order, thêm explicit `order by`, hoặc so sánh sets theo IDs.

### 19.3. Test subtype-only query

```jpql
select c
from CardPayment c
where c.tenantId = :tenant
```

Expected: chỉ CardPayment; không trả BankTransferPayment.

---

## 20. Test TYPE trong JPQL

`TYPE` giúp biểu diễn subtype predicate:

```java
List<Payment> cards = em.createQuery(
    """
    select p
    from Payment p
    where type(p) = CardPayment
      and p.tenantId = :tenant
    """,
    Payment.class
)
.setParameter("tenant", "shop-a")
.getResultList();
```

Một số cú pháp có thể tham chiếu entity type qua entity name. Provider/version cụ thể có thể cho phép bind type parameter; kiểm tra tài liệu stack nếu dùng dynamic type filtering.

### 20.1. Test TYPE cho từng strategy

Với SINGLE_TABLE, provider thường dùng discriminator. Với JOINED/TABLE_PER_CLASS, SQL strategy có thể khác. **Test result semantics** trước rồi đo SQL nếu performance quan trọng.

### 20.2. Không sử dụng class name Java như SQL literal

`TYPE(p)` thuộc JPQL entity type system, không phải `WHERE payment_kind = 'CardPayment'` viết theo bảng.

### 20.3. Test unknown discriminator

Một row có discriminator không nhận diện được có thể gây lỗi provider hoặc behavior khác. Nếu cần kiểm tra dữ liệu legacy/corruption, tạo database fixture có kiểm soát và xác định expected handling theo provider — không coi unknown value tự động biến thành Payment root.

---

## 21. TREAT trong JPQL

`TREAT` cho phép sử dụng thuộc tính riêng của subtype trong query.

Ví dụ:

```java
List<Payment> results = em.createQuery(
    """
    select p
    from Payment p
    where treat(p as CardPayment).tokenReference = :tokenRef
      and p.tenantId = :tenant
    """,
    Payment.class
)
.setParameter("tokenRef", "token-ref-test")
.setParameter("tenant", "shop-a")
.getResultList();
```

### 21.1. Query được phép truy cập field đặc thù

`Payment` không có `tokenReference`. `TREAT` diễn tả downcast entity path theo JPA query language.

### 21.2. Test không trả subtype khác

Nếu BankTransferPayment có một bankReference bằng text trùng tokenRef, query vẫn phải chọn CardPayment đúng subtype, không so sánh sai column do mapping.

### 21.3. Các vấn đề portability

Cú pháp `TREAT`, Criteria equivalents và SQL rendering phụ thuộc JPA version/provider/dialect. Nếu project yêu cầu portable JPQL, chạy integration tests với các provider/database mục tiêu thay vì chỉ test parse string.

### 21.4. Không dùng TYPE/TREAT để bỏ authorization

Vẫn cần tenant/ownership predicate trong cùng query.

---

## 22. Kiểm thử JOINED inheritance

Giả sử đổi hierarchy sang:

```java
@Entity
@Table(name = "payment_root")
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class JoinedPayment {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "joined_payment_seq"
    )
    @SequenceGenerator(
        name = "joined_payment_seq",
        sequenceName = "joined_payment_seq",
        allocationSize = 1
    )
    private Long id;

    @Column(name = "amount", nullable = false)
    private BigDecimal amount;

    protected JoinedPayment() {}
}

@Entity
@Table(name = "card_payment")
public class JoinedCardPayment extends JoinedPayment {

    @Column(name = "payment_token_ref")
    private String tokenReference;

    protected JoinedCardPayment() {}
}
```

Đây là **một hierarchy khác**, không đổi annotation strategy của cùng một hierarchy tùy runtime.

### 22.1. Expected schema

```text
payment_root
  id (PK)
  amount

card_payment
  id (PK and FK to payment_root.id)
  payment_token_ref
```

### 22.2. Test round-trip

Persist JoinedCardPayment, flush/clear, find bằng JoinedPayment root. Kết quả phải là JoinedCardPayment với cả base và subtype fields.

### 22.3. Kiểm tra database rows

Một CardPayment thuộc JOINED thường tương ứng một row trong root table và một row trong subtype table, cùng key. DB migration phải có PK/FK phù hợp.

### 22.4. Test transaction atomicity

Nếu INSERT subtype fail vì constraint, root row cũng không nên committed trong cùng transaction. Test rollback state sau failure bằng transaction mới.

### 22.5. Join query performance

Polymorphic query JOINED có thể cần nhiều joins. Test bằng SQL plans/row counts trên database đích nếu endpoint query base root nhiều và hierarchy lớn.

---

## 23. Kiểm thử TABLE_PER_CLASS inheritance

```java
@Entity
@Inheritance(strategy = InheritanceType.TABLE_PER_CLASS)
public abstract class PaymentTablePerClass {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Column(name = "amount")
    private BigDecimal amount;

    protected PaymentTablePerClass() {}
}

@Entity
@Table(name = "card_payment_concrete")
public class CardPaymentConcrete
        extends PaymentTablePerClass {

    @Column(name = "payment_token_ref")
    private String tokenReference;

    protected CardPaymentConcrete() {}
}
```

### 23.1. Một table cho mỗi concrete entity

Columns inherited từ base được lặp trong từng concrete table theo mapping strategy. Không có root table giống JOINED.

### 23.2. Polymorphic root query

Provider có thể tạo SQL UNION/UNION ALL để trả nhiều subtypes. Test `from PaymentTablePerClass` và kết quả concrete types.

### 23.3. ID uniqueness xuyên hierarchy

Nếu query hoặc association sử dụng root identity, generated IDs cần không xung đột giữa subtype tables. Một sequence dùng chung là lựa chọn có thể phù hợp; nhiều `IDENTITY` counters cục bộ có thể tạo trùng IDs hoặc không được provider hỗ trợ trong strategy này.

### 23.4. Performance test nếu cần

Khi số subclasses lớn, polymorphic queries có thể tốn hơn một table scan/join khác. Không suy rằng TABLE_PER_CLASS luôn chậm hoặc nhanh; đo workload với data distribution thực.

### 23.5. Chú ý database dialect

Một vài providers/dialects có hạn chế ở TABLE_PER_CLASS unions, generators hoặc relationships. Integration test trên production-like DB là cần thiết.

---

## 24. Bảng test matrix ba inheritance strategies

| Case | SINGLE_TABLE | JOINED | TABLE_PER_CLASS |
|---|---|---|---|
| Persist subtype và reload qua root | Bắt buộc | Bắt buộc | Bắt buộc |
| Query base root trả mọi subtype | Bắt buộc | Bắt buộc | Bắt buộc |
| Query subtype chỉ trả đúng type | Có | Có | Có |
| `TYPE`/`TREAT` | Có | Có | Có, theo provider support |
| Discriminator column | Trọng tâm | Tùy strategy/provider | Không mặc định cùng kiểu |
| PK/FK giữa root và subtype tables | Không có | Trọng tâm | Không có root FK cùng kiểu |
| Subclass-only columns | Nullable trong chung table | Ở subtype table | Ở concrete table |
| ID uniqueness toàn hierarchy | Một PK table | Root PK | Cần chú ý generator |
| Query plan đa hình | Filter một table | Joins | Unions |
| Rollback khi subtype insert lỗi | Test transaction | Đặc biệt quan trọng | Test transaction |

### 24.1. Đừng đổi strategy chỉ vì một test chậm

Inheritance strategy ảnh hưởng migrations, schema, query plans, constraints, association targets và lifecycle. Cần đánh giá kiến trúc + dữ liệu thực.

### 24.2. Một shared test contract có thể chạy theo nhiều mapping

Có thể xây abstract test utilities cho: “persist subtype A/B → clear → root query → đúng count/type”. Nhưng setup/entity classes khác nhau vẫn cần mappings tương ứng.

---

## 25. @MappedSuperclass không phải polymorphic entity

Ví dụ:

```java
@MappedSuperclass
public abstract class AuditedRecord {

    @Column(name = "created_at", nullable = false)
    protected Instant createdAt;

    @Column(name = "created_by")
    protected String createdBy;
}

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder extends AuditedRecord {

    @Id
    private Long id;

    protected PurchaseOrder() {}
}
```

### 25.1. Assertions cần có

- Fields `createdAt`/`createdBy` tồn tại ở bảng `purchase_order`.
- Persist/read PurchaseOrder lấy đúng inherited attributes.
- Query `from PurchaseOrder` hoạt động.
- Không mong `from AuditedRecord` hoạt động như một entity root query.

### 25.2. Mapped superclass không có table riêng

Không tạo DDL table `audited_record` chỉ vì class có `@MappedSuperclass`.

### 25.3. Unit tests có thể kiểm tra inherited domain methods

Nhưng persistence mapping vẫn cần integration test, đặc biệt khi subclasses override columns hoặc access type.

### 25.4. Không nhầm với Java-only base class

Một Java superclass không annotated có thể có fields, nhưng JPA mapping rules của inherited fields khác; không giả định nó giống `@MappedSuperclass`.

---

## 26. Kế thừa và AccessType

Với JPA, đặt `@Id` trên field thường xác định **field access** trong hierarchy nếu không override; đặt trên getter thường là **property access**.

### 26.1. Lỗi thường gặp

Base entity dùng field access, subclass đặt một annotation lên getter và mong nó có hiệu lực. Mapping có thể bị bỏ qua hoặc bất nhất nếu không dùng `@Access` có chủ đích.

### 26.2. Test bootstrap + database column

Đừng chỉ kiểm tra getter sau persist, vì getter có thể trả Java field dù column chưa được map. Flush/clear/reload và inspect schema/SQL.

### 26.3. Override inherited field

`@AttributeOverride` có thể được dùng trong những cấu hình thích hợp để đổi column mapping của inherited basic attribute. Test class-specific column và schema correctness.

### 26.4. Hạn chế reflection-based tests

Chỉ đọc annotations không chứng minh provider áp metadata thế nào khi kế thừa/mapped superclass/XML override. Runtime persistence test đáng tin hơn.

---

## 27. Kế thừa và optimistic locking

Entity root `Payment` có `@Version`. Nếu một subtype được update:

1. Load `CardPayment` version V.
2. Transaction khác update cùng row/identity và commit.
3. Transaction đầu cố update state cũ.
4. Expected optimistic conflict theo JPA/provider semantics.

### 27.1. Version nằm ở đâu?

Với SINGLE_TABLE, row chung chứa version. Với JOINED, thường version ở root table nếu khai tại base. Test migration/SQL phải xác nhận version column và update paths.

### 27.2. Không nghĩ subtype là transaction độc lập

CardPayment và Payment base là một persistent entity identity. Update subtype field vẫn chịu version/concurrency policy của entity hierarchy.

### 27.3. Test failed update state

Sau `OptimisticLockException`, rollback transaction và đọc lại bằng EntityManager mới; không dùng stale instance làm expected DB state.

---

# Phần III — Đối tượng giá trị và @Embeddable

## 28. Entity khác value object thế nào?

Một **entity** có identity độc lập, có thể được tìm bằng `EntityManager.find` và được quản lý theo lifecycle.

Một **value object** thường được phân biệt theo giá trị các thuộc tính. Nó không có persistent identity độc lập và trong JPA có thể được mô hình bằng `@Embeddable`, `@Embedded` hoặc `@ElementCollection`.

Ví dụ `PostalAddress`:

```text
street   = "12 Main Road"
city     = "Da Nang"
postCode = "550000"
```

Hai PostalAddress objects có cùng ba thuộc tính có thể được coi bằng nhau theo domain equality dù `a != b`.

### 28.1. Value object thường bất biến về mặt API

Thay địa chỉ thường nên tạo `new PostalAddress(...)` và gán vào owner, thay vì sửa từng field nội bộ của value object đã được dùng ở nhiều nơi.

### 28.2. @Embeddable vẫn có JPA requirements

Provider cần tạo/hydrate instances qua constructor/access mapping theo spec và version. Đừng giả định mọi Java record/final class đều portable embeddable trên mọi JPA provider.

### 28.3. Không phải mọi value object đều dùng @Embeddable

Một value type có thể được lưu một cột qua `AttributeConverter`, ví dụ `EmailAddress` → VARCHAR. Một value collection có thể dùng `@ElementCollection`.

---

## 29. Mô hình @Embeddable PostalAddress

```java
package com.example.customer;

import jakarta.persistence.*;
import java.util.Objects;

@Embeddable
public class PostalAddress {

    @Column(name = "street", length = 200)
    private String street;

    @Column(name = "city", length = 100)
    private String city;

    @Column(name = "postal_code", length = 30)
    private String postalCode;

    protected PostalAddress() {}

    public PostalAddress(
            String street,
            String city,
            String postalCode
    ) {
        this.street = requireText(street);
        this.city = requireText(city);
        this.postalCode = requireText(postalCode);
    }

    private static String requireText(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Address component required"
            );
        }
        return value;
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof PostalAddress other)) return false;

        return Objects.equals(street, other.street)
            && Objects.equals(city, other.city)
            && Objects.equals(postalCode, other.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
```

### 29.1. Value equality

```java
assertEquals(
    new PostalAddress("12 Main Road", "Da Nang", "550000"),
    new PostalAddress("12 Main Road", "Da Nang", "550000")
);
```

### 29.2. Validation ở constructor

Unit test kiểm tra null/blank. Nhưng JPA cần no-arg constructor và có thể hydrate fields trực tiếp nên **constructor validation không thay database/Bean Validation constraints** trong mọi đường đi.

### 29.3. Tính bất biến ở cấp API

Không có setters. Trong JPA mapping field access, provider vẫn có thể gán fields khi đọc. Đừng tự kết luận entity đã deep immutable nếu bên trong chứa mutable collections.

---

## 30. Hai @Embedded cùng kiểu cần @AttributeOverrides

Entity có billing và shipping addresses:

```java
@Entity
@Table(name = "customer_profile")
public class CustomerProfile {

    @Id
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "billing_street")
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "billing_city")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "billing_postal_code")
        )
    })
    private PostalAddress billingAddress;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "shipping_street")
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "shipping_city")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "shipping_postal_code")
        )
    })
    private PostalAddress shippingAddress;

    @Version
    private Long version;

    protected CustomerProfile() {}

    public CustomerProfile(
            Long id,
            String tenantId,
            PostalAddress billing,
            PostalAddress shipping
    ) {
        this.id = id;
        this.tenantId = tenantId;
        this.billingAddress = billing;
        this.shippingAddress = shipping;
    }

    public Long getId() { return id; }
    public PostalAddress getBillingAddress() {
        return billingAddress;
    }
    public PostalAddress getShippingAddress() {
        return shippingAddress;
    }

    public void changeShippingAddress(PostalAddress next) {
        this.shippingAddress = next;
    }
}
```

### 30.1. Expected columns

```text
customer_profile
  customer_id
  tenant_id
  billing_street
  billing_city
  billing_postal_code
  shipping_street
  shipping_city
  shipping_postal_code
  version
```

### 30.2. Failure mode khi thiếu overrides

Provider có thể báo repeated column mappings, hoặc metadata/implicit naming strategy cho ra một kết quả khác mong đợi. Không dựa vào naming strategy tự xử lý mọi cặp embedded cùng kiểu.

### 30.3. Test đọc riêng từng group

Nếu billing và shipping có giá trị giống nhau, một mapping nhầm cột vẫn có thể lọt test. **Dùng fixture khác biệt rõ cho từng address**.

---

## 31. Test embedded round-trip

```java
@Test
void twoEmbeddedAddressesUseDifferentColumns() {
    PostalAddress billing = new PostalAddress(
        "1 Billing Street", "Hanoi", "100000"
    );

    PostalAddress shipping = new PostalAddress(
        "9 Delivery Road", "Da Nang", "550000"
    );

    CustomerProfile profile = new CustomerProfile(
        101L, "shop-a", billing, shipping
    );

    em.persist(profile);
    em.flush();
    em.clear();

    CustomerProfile reloaded =
        em.find(CustomerProfile.class, 101L);

    assertEquals(
        billing,
        reloaded.getBillingAddress()
    );
    assertEquals(
        shipping,
        reloaded.getShippingAddress()
    );
    assertNotEquals(
        reloaded.getBillingAddress(),
        reloaded.getShippingAddress()
    );
}
```

### 31.1. Vì sao phải clear?

Không clear, `em.find` có thể lấy cùng object từ persistence context, không chứng minh billing/shipping mappings xuống columns khác nhau.

### 31.2. Nếu cần kiểm tra tên cột chính xác

Dùng metadata inspection hoặc native SQL read cho `billing_street` và `shipping_street`, đồng thời giữ integration test JPA để kiểm tra round-trip.

### 31.3. Test empty/null address

Nếu shipping optional, test `shippingAddress == null`; xem behavior null composite columns trên target provider/database, đặc biệt khi một số columns null còn số khác non-null.

---

## 32. Embedded null semantics và partial null columns

JPA embeddable thường không có independent identity. Một nhóm embedded columns tất cả NULL có thể được provider materialize thành `null` hoặc một object có null fields tùy mapping, provider/settings và version.

### 32.1. Không giả định tuyệt đối một representation

Nếu domain coi “không có địa chỉ” là `null`, cần integration test behavior trên target provider. Với partial fields null, cũng phải xác định domain interpretation.

### 32.2. @AttributeOverride nullable settings

Nếu embedded optional, không khai `nullable=false` cho toàn bộ embedded columns mà không có cách xử lý null owner state. Schema constraint phải khớp domain.

### 32.3. Dùng explicit presence field nếu cần

Khi có sự khác biệt nghiệp vụ giữa “không có address” và “address object với fields thiếu”, có thể cần một cột trạng thái hoặc quy ước rõ thay vì dựa vào provider null inference.

### 32.4. Test read và write null

- Persist profile với shipping=null.
- Flush/clear/read lại.
- Chuyển shipping từ null sang non-null.
- Flush/clear/read.
- Chuyển ngược sang null và xác minh columns.
- Kiểm tra rằng business validation/schema cho phép đúng các trạng thái này.

---

## 33. Test thay thế value object và dirty checking

Thay shipping address:

```java
CustomerProfile profile =
    em.find(CustomerProfile.class, 101L);

PostalAddress replacement = new PostalAddress(
    "77 New Street", "Hue", "530000"
);

profile.changeShippingAddress(replacement);
em.flush();
em.clear();

CustomerProfile reloaded =
    em.find(CustomerProfile.class, 101L);

assertEquals(
    replacement,
    reloaded.getShippingAddress()
);
```

### 33.1. Replacement rõ nghĩa hơn mutation nội bộ

Thay object value thường dễ hiểu và dễ kiểm thử. Nếu một mutable embeddable thay field trực tiếp, dirty checking behavior có thể phụ thuộc enhancement/provider/mapping; cần test cụ thể.

### 33.2. Không đòi một SQL UPDATE cho mỗi field

Provider có thể update nhiều columns của owner dù chỉ một embedded field thay đổi. Hãy test **kết quả persisted đúng**, rồi đo SQL shape riêng nếu performance quan trọng.

### 33.3. Versioning

Nếu owner có `@Version`, update embedded state thường là update của owner. Test version/concurrency behavior nếu API dựa vào optimistic locking, không chỉ so sánh value.

### 33.4. Không thay đổi value object chỉ vì muốn giữ identity

`PostalAddress` không có independent ID. “Đổi address” về mặt domain không giống reassign primary key.

---

## 34. Nested @Embeddable

Có thể có:

```text
ContactInfo (@Embeddable)
   +-- email: EmailAddress-like fields
   +-- primaryAddress: PostalAddress (@Embedded)
```

Mapping:

```java
@Embeddable
public class ContactInfo {

    @Column(name = "email")
    private String email;

    @Embedded
    private PostalAddress primaryAddress;

    protected ContactInfo() {}
}
```

Owner có thể override nested column path qua `@AttributeOverride` theo attribute naming/path rules, chẳng hạn `"contact.primaryAddress.city"` tùy vị trí của embedded attributes.

### 34.1. Test nested path cẩn thận

- Mapping bootstrap thành công.
- Persist/flush/clear/reload nested fields.
- Tên columns thật khớp migration.
- Không duplicate columns khi owner có hai ContactInfo objects.
- Null propagation được định nghĩa.

### 34.2. Mapping path phải khớp Java attribute names

`postalCode` là Java field; `postal_code` là SQL column. `@AttributeOverride(name = "...")` dùng attribute path đúng theo JPA mapping, không tự dùng SQL column name.

### 34.3. Tránh object graph quá sâu trong value object

Một embeddable quá nhiều nested fields làm SQL rows rộng, khó validate và khó đổi schema. Test correctness và xem xét model boundaries.

---

## 35. @ElementCollection: tập đối tượng giá trị

Một Profile có nhiều contact methods; mỗi phần tử không có entity ID độc lập.

Value type:

```java
@Embeddable
public class ContactMethod {

    @Column(name = "contact_kind", nullable = false)
    private String kind;

    @Column(name = "contact_value", nullable = false)
    private String value;

    protected ContactMethod() {}

    public ContactMethod(String kind, String value) {
        if (kind == null || kind.isBlank()
                || value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Contact method fields required"
            );
        }
        this.kind = kind;
        this.value = value;
    }

    public String getKind() { return kind; }
    public String getValue() { return value; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof ContactMethod other)) return false;
        return Objects.equals(kind, other.kind)
            && Objects.equals(value, other.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(kind, value);
    }
}
```

Owner association:

```java
@ElementCollection(fetch = FetchType.LAZY)
@CollectionTable(
    name = "customer_contact_method",
    joinColumns = @JoinColumn(
        name = "customer_id",
        referencedColumnName = "customer_id"
    )
)
private Set<ContactMethod> contactMethods = new HashSet<>();
```

### 35.1. Vì sao @ElementCollection?

Các ContactMethod values được sở hữu bởi CustomerProfile, không có lifecycle độc lập như entity `ContactMethodEntity`.

### 35.2. Không cần em.persist(contactMethod)

ElementCollection được lưu qua owner. `ContactMethod` không là entity được `em.find(ContactMethod.class,...)`.

### 35.3. Schema có collection table

```text
customer_contact_method
  customer_id -> customer_profile.customer_id
  contact_kind
  contact_value
```

Có thể có unique constraint hoặc index theo `(customer_id,kind,value)` nếu business/set semantics cần, nhưng JPA `Set` trong memory **không tự đảm bảo** DB unique constraint tồn tại.

### 35.4. Test equality quan trọng

Nếu Set elements equality/hashCode sai, duplicate contact values có thể lọt hoặc phần tử không xóa được sau thay đổi.

---

## 36. Test @ElementCollection persist và reload

```java
@Test
void persistsValueCollection() {
    CustomerProfile profile = profileFixture(101L);

    profile.addContact(
        new ContactMethod("EMAIL", "demo@example.invalid")
    );
    profile.addContact(
        new ContactMethod("PHONE", "+84000000000")
    );

    em.persist(profile);
    em.flush();
    em.clear();

    CustomerProfile loaded =
        em.find(CustomerProfile.class, 101L);

    assertEquals(2, loaded.getContactMethods().size());
    assertTrue(
        loaded.getContactMethods().contains(
            new ContactMethod("EMAIL", "demo@example.invalid")
        )
    );
}
```

`profileFixture`, `addContact` và `getContactMethods` là helper/domain methods bổ sung trong class owner. Ví dụ nêu các assertions chính.

### 36.1. Không kiểm tra thứ tự của Set

`Set` không bảo đảm iteration order; dùng `contains`/set equality thay vì `get(0)`.

### 36.2. Nếu cần thứ tự

Dùng `List` với semantics phù hợp và `@OrderColumn` hoặc `@OrderBy` theo use case. Test index/order storage và behavior chèn/xóa phần tử giữa danh sách.

### 36.3. Tránh canary thật

Contact values ví dụ là dữ liệu giả. Production tests không cần dùng email/phone người thật để xác minh mapping.

---

## 37. Test thêm, xóa và thay thế @ElementCollection

Case cần bao phủ:

```text
Initial:
  [EMAIL:a, PHONE:b]

Add:
  + EMAIL:c

Remove:
  - PHONE:b

Replace:
  EMAIL:a -> EMAIL:new

Delete owner:
  collection rows deleted according to mapping/DB FK strategy
```

### 37.1. Test sau clear hoặc transaction mới

Một `Set.remove` trong memory có thể trả true nhưng chưa chứng minh SQL đã xóa đúng row. Flush/clear/read lại.

### 37.2. Test duplicate value

Nếu Set equality coi hai values giống nhau, adding duplicate không làm Set size tăng. Nhưng DB constraint cho cùng bộ giá trị vẫn cần kiểm tra nếu external JDBC writers có thể ghi bảng.

### 37.3. Có thể phát nhiều DELETE/INSERT hơn mong đợi

Với embeddable collections, provider có thể chọn xóa và insert lại nhiều rows khi thay đổi; correctness test và performance test là hai việc khác nhau.

### 37.4. Xóa owner

Collection table thường phụ thuộc lifecycle owner, nhưng test xem DB rows còn lại sau delete + commit. FK/cascade semantics, orphan removal ở value collection và DDL thực phải phù hợp.

---

## 38. @ElementCollection với composite owner key

Nếu chủ sở hữu `WarehouseStock` có `StockId(tenantId,sku)` và collection của value objects:

```java
@ElementCollection
@CollectionTable(
    name = "stock_label",
    joinColumns = {
        @JoinColumn(
            name = "tenant_id",
            referencedColumnName = "tenant_id"
        ),
        @JoinColumn(
            name = "sku",
            referencedColumnName = "sku"
        )
    }
)
@Column(name = "label_text")
private Set<String> labels = new HashSet<>();
```

### 38.1. Composite join columns phải đầy đủ

Nếu chỉ join theo `sku`, labels của các tenant có cùng SKU có thể bị trộn hoặc FK bị mapping sai.

### 38.2. Test two-tenant same-SKU

Seed Stock IDs `(shop-a,BOOK-JPA)` và `(shop-b,BOOK-JPA)`, mỗi stock có labels khác nhau. Reload và assert không cross-tenant leakage.

### 38.3. Index/FK constraints

Collection table cần composite FK columns đúng, có thể có index `(tenant_id,sku)`. Test migrations và database catalog khi schema correctness quan trọng.

### 38.4. Không nhầm @CollectionTable với @JoinTable entity association

`@ElementCollection` lưu basic/embeddable values, khác `@ManyToMany` entity association.

---

## 39. AttributeConverter cho value types một cột

Một email value object có thể dùng converter:

```java
public final class EmailAddress {

    private final String normalized;

    public EmailAddress(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("Email required");
        }
        this.normalized = raw.trim().toLowerCase(
            Locale.ROOT
        );
    }

    public String value() { return normalized; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof EmailAddress other
            && normalized.equals(other.normalized);
    }

    @Override
    public int hashCode() {
        return normalized.hashCode();
    }
}
```

JPA converter:

```java
@Converter(autoApply = false)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(
            EmailAddress attribute
    ) {
        return attribute == null
            ? null
            : attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(
            String dbData
    ) {
        return dbData == null
            ? null
            : new EmailAddress(dbData);
    }
}
```

Usage:

```java
@Convert(converter = EmailAddressConverter.class)
@Column(name = "email", nullable = false)
private EmailAddress email;
```

### 39.1. Test cả hai chiều conversion

- Java value -> normalized DB string.
- DB string -> EmailAddress equality.
- Null conversion policy.
- Case/whitespace normalization.
- Invalid stored values nếu hệ thống có legacy data.
- Queries với converter-bound parameters theo JPA/provider.

### 39.2. Converter không tự bảo đảm uniqueness

Nếu business coi email normalized là unique, tạo database constraint thích hợp. Test race và collation theo database đích.

### 39.3. Không lạm dụng converter cho @Id

JPA có giới hạn và provider-specific behavior với ID/version/relationship attributes. Nếu cần converted identifier mapping, xác nhận chuẩn/phiên bản cụ thể; không mặc định `AttributeConverter` hoạt động như basic field ở mọi loại khóa.

### 39.4. Converter không phải crypto

Có thể dùng converter cho encryption khi được thiết kế đúng, nhưng một ví dụ normalize email không mã hóa và không tự bảo vệ logging.

---

## 40. Test converter bằng database thật

Một test có thể:

```java
@Test
void emailValueRoundTripsThroughConverter() {
    CustomerEmailEntity entity = new CustomerEmailEntity(
        200L,
        new EmailAddress("  DEMO@EXAMPLE.INVALID ")
    );

    em.persist(entity);
    em.flush();
    em.clear();

    CustomerEmailEntity loaded = em.find(
        CustomerEmailEntity.class,
        200L
    );

    assertEquals(
        new EmailAddress("demo@example.invalid"),
        loaded.getEmail()
    );
}
```

`CustomerEmailEntity` là entity fixture chứa field `EmailAddress` ở phần trước.

### 40.1. Đọc raw DB column để xác minh converter

```java
String dbEmail = (String) em.createNativeQuery(
    "select email from customer_email where id = ?1"
)
.setParameter(1, 200L)
.getSingleResult();

assertEquals("demo@example.invalid", dbEmail);
```

Tên table/column phải khớp fixture mapping. Assertion raw SQL giúp phát hiện code chỉ đang trả cached object mà chưa chứng minh conversion đúng.

### 40.2. Test null/invalid DB data

Nếu `email` nullable ở một entity khác, converter phải có null semantics rõ. Với dữ liệu legacy invalid, policy có thể là reject/normalize/migration trước, không tự cho converter silently sửa và ghi data.

---

## 41. Value-object equality và monetary amounts

Một object `Money(amount,currency)` là tình huống điển hình:

```java
@Embeddable
public class Money {

    @Column(name = "amount", precision = 18, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency", length = 3)
    private String currency;

    protected Money() {}

    public Money(BigDecimal amount, String currency) {
        this.amount = amount;
        this.currency = currency;
    }

    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }

    // equals/hashCode theo business numeric semantics
    // do domain định nghĩa, không nhất thiết BigDecimal.equals.
}
```

### 41.1. BigDecimal equals và scale

`new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là `false`, nhưng `compareTo(...) == 0`. Nếu domain muốn hai values bằng nhau về số học, implement equality/normalization nhất quán và test hashCode tương ứng.

### 41.2. Currency code cần chuẩn hóa

`USD` và `usd` có được coi bằng nhau không? Normalize/validate sớm, đừng để DB collation quyết định ngầm.

### 41.3. Currency precision

Một phép test được đọc qua cột DECIMAL(18,2) có thể round/scale values theo DB/provider. Test values 10.00, 10.01, boundary precision và policy xử lý nhiều chữ số thập phân.

### 41.4. Null invariants

Money thiếu currency thường không hợp lệ; test constructors, Bean Validation và schema NOT NULL tương ứng khi business yêu cầu.

---

## 42. Immutable value-object pattern và dirty checking

Thay vì:

```java
profile.getShippingAddress().setCity("Hue");
```

nên có:

```java
PostalAddress next = new PostalAddress(
    profile.getShippingAddress().getStreet(),
    "Hue",
    profile.getShippingAddress().getPostalCode()
);
profile.changeShippingAddress(next);
```

### 42.1. Test replacement

Flush/clear/read lại và assert `city="Hue"`.

### 42.2. Nếu vẫn dùng mutable embeddable

Viết test riêng xem provider phát hiện thay đổi; bytecode enhancement và access type có thể thay behavior. Đừng dựa vào mutation mà chưa kiểm tra.

### 42.3. Không dùng Java record làm @Embeddable portable mặc định

Một số hiện đại provider/JPA versions có hỗ trợ record embeddables hoặc cơ chế constructor binding đặc thù, nhưng không giả định mọi runtime đều hỗ trợ đầy đủ no-arg/field initialization theo cùng cách. Với portability, class embeddable thông thường là phương án an toàn hơn.

### 42.4. Không gửi value object qua JSON tự động nếu chứa fields nội bộ

Value object có equality đúng vẫn có thể chứa PII; response DTO phải chọn fields theo quyền.

---

# Phần IV — Hạ tầng kiểm thử

## 43. Test trên H2 và test trên database mục tiêu

H2 rất tiện cho fast tests, nhưng có thể khác database production ở:

- Composite PK column collation/case sensitivity.
- FK, constraints, deferred constraints.
- Sequence and identity generation.
- JOINED/TABLE_PER_CLASS polymorphic SQL.
- DISTINCT/UNION query plans.
- JSON/UUID/ENUM/DATE/TIMESTAMP mapping.
- Locking/isolation/concurrent writes.
- Composite index uniqueness behavior.

### 43.1. Phân tầng hợp lý

- Unit tests: không cần database.
- Fast JPA mapping tests: có thể dùng embedded DB khi compatibility có ích.
- Integration correctness trên provider/dialect đích: Testcontainers/target DB.
- Concurrency/schema/performance tests: database gần môi trường triển khai nhất có thể.

### 43.2. Đừng kết luận từ H2 rằng PostgreSQL schema chuẩn

H2 compatibility mode chỉ cố tương thích một phần syntax/behavior. Nó không dùng PostgreSQL planner và collation rules thật.

### 43.3. Đừng đổi database production chỉ để test dễ hơn

Môi trường test nên điều chỉnh để mô phỏng production, không phải làm sai lựa chọn architecture.

---

## 44. Testcontainers + Spring Data JPA mẫu

Ví dụ dành cho ứng dụng Spring Boot/JUnit 5 với PostgreSQL:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest
@Testcontainers
class StockMappingIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void dataSourceProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add("spring.datasource.url", db::getJdbcUrl);
        registry.add("spring.datasource.username", db::getUsername);
        registry.add("spring.datasource.password", db::getPassword);
    }

    @Test
    void canLoadCompositeKey() {
        // Inject TestEntityManager or EntityManager;
        // apply migrations/seed via test setup;
        // then persist, flush, clear, find and assert.
    }
}
```

### 44.1. Image version chỉ minh họa

Thay `postgres:16` bằng engine/version tương ứng target environment. Có thể pin digest/minor version theo nhu cầu reproducibility.

### 44.2. @DataJpaTest rollback mặc định

Test methods thường được bọc trong test-managed transaction và rollback sau test; điều này giúp isolation nhưng không chứng minh commit durability.

### 44.3. Migrations phải giống thật

Nếu production dùng Flyway/Liquibase, test nên sử dụng migration scripts thật, không chỉ để Hibernate create-drop sinh schema với missing indexes/constraints.

### 44.4. Test profile không được auto-replace DB ngoài ý muốn

Trong một số Spring Boot/test configurations, `@DataJpaTest` có thể thay datasource bằng embedded DB. Đảm bảo dynamic/Testcontainers datasource thật được dùng, hoặc cấu hình `@AutoConfigureTestDatabase(replace = NONE)` theo Spring Boot version/setup.

### 44.5. Không cần chạy performance load ở mọi unit test

Mapping correctness tests cần nhanh và lặp lại. Concurrency/large dataset test có thể là suite riêng.

---

## 45. Gợi ý xây test fixture đúng cách

Một fixture nguy hiểm là tạo cùng values cho mọi test:

```java
new StockId("tenant", "sku")
```

Nếu tests chạy chung database, duplicate PK có thể làm test phụ thuộc thứ tự và fail ngẫu nhiên.

### 45.1. Dùng deterministic unique keys per test

```text
stock-embedded-basic -> shop-test-1 / SKU-A
stock-embedded-duplicate -> shop-test-2 / SKU-B
stock-mapsid -> shop-test-3 / SKU-C
```

### 45.2. Cân nhắc cleanup

Dùng rollback test transactions, schema reset, isolated containers hoặc cleanup đúng FK dependency. Không làm `TRUNCATE CASCADE` trên shared database không thuộc test.

### 45.3. Không reuse EntityManager giữa threads

EntityManager không có contract thread-safe. Với test concurrency, mỗi thread/transaction có context riêng.

### 45.4. Fixture builders có thể che mappings

Nếu helper tự gọi `merge` hoặc `flush` bất ngờ, test dễ đoán sai state. Ghi rõ helper có persist/commit hay chỉ tạo transient object.

---

## 46. Transaction boundaries trong test

Các dạng quan sát:

```text
Transient object
  |
em.persist
  |
  +-- identity map contains managed instance
  |
em.flush
  |
  +-- pending SQL synchronized; not committed
  |
em.clear
  |
  +-- L1 cleared; subsequent find needs database load
  |
tx.commit
  |
  +-- commit completed or failed
  |
new EM/tx.find
  |
  +-- verify committed data
```

### 46.1. Test mapping nội bộ

`persist -> flush -> clear -> find` thường hiệu quả.

### 46.2. Test constraint ở commit

Một số DB supports deferred constraints; test phải bao gồm commit boundary nếu muốn khẳng định constraint check outcome.

### 46.3. Test rollback

Nếu cố INSERT duplicate composite PK, rollback và tạo EM mới để xác nhận DB không còn partial writes.

### 46.4. Test isolation

Với concurrent updates/unique keys, dùng separate connections/transactions, barrier và assert state sau cả hai kết thúc.

### 46.5. Spring self-invocation caveat

Nếu test gọi method `@Transactional` qua `this.method()` trong cùng proxy-based bean, Spring advice có thể không áp dụng. Đừng đánh giá transaction semantics từ method calls không đi qua proxy.

---

## 47. Test SQL vs test kết quả

Có hai loại assertions:

**Behavior assertions:**

```java
assertEquals(expectedId, reloaded.getId());
assertInstanceOf(CardPayment.class, reloaded);
assertEquals(expectedAddress, profile.getShippingAddress());
```

**SQL/schema assertions:**

- Table `warehouse_stock` có PK hai columns.
- `stock_movement` có composite FK.
- SINGLE_TABLE có discriminator.
- JOINED lưu root + subtype rows.
- ElementCollection có collection table, correct owner keys.
- Converter cột email chứa normalized value.

### 47.1. Không assert exact SQL alias string trừ khi cần

Hibernate versions có thể đổi aliases/format. Ưu tiên semantics hoặc SQL normalization khi kiểm tra performance.

### 47.2. Dùng native SQL test chỉ khi cần kiểm tra mapping vật lý

Query vào system catalog hoặc raw columns là hữu ích cho schema tests; đừng lạm dụng raw SQL khiến test bị vendor-lock khi portability là mục tiêu.

### 47.3. Migrations là ground truth

Annotation có thể đúng nhưng migration thiếu constraint; chỉ behavior test với Hibernate auto-DDL có thể bỏ sót mismatch production.

---

## 48. Test concurrency với composite key

Hai transactions cùng cố tạo:

```text
Transaction A:
  INSERT stock(shop-a,BOOK-JPA,10)

Transaction B:
  INSERT stock(shop-a,BOOK-JPA,20)
```

Một database có PK hợp lệ phải đảm bảo không thể commit hai rows với cùng tuple.

### 48.1. Không chỉ dùng repository.exists trước INSERT

Cả A và B có thể cùng đọc absent rồi cùng INSERT. DB PK là hàng rào cuối; test race window có thể dùng barrier.

### 48.2. Expected outcome

Một request thành công, request khác nhận conflict hoặc failure phù hợp (tùy timing/isolation), và committed row count theo key bằng một.

### 48.3. Không giả định thread nào thắng

Scheduling/lock acquisition khác nhau theo môi trường. Assert invariant chứ không hard-code A luôn thành công.

### 48.4. Sau failed insert

Rollback transaction thất bại; không dùng EM lỗi để query state.

### 48.5. Test tenant khác

A tạo `(shop-a,BOOK-JPA)`, B tạo `(shop-b,BOOK-JPA)`; cả hai có thể thành công. Case này giúp phát hiện composite uniqueness sai scope.

---

## 49. Trường hợp @MapsId với transaction và cascading

Derived identity có thể phụ thuộc việc parent được persist trước, hoặc cascade persist được cấu hình đúng.

### 49.1. Test parent new + child new

- Tạo Stock mới.
- Tạo Movement tham chiếu Stock.
- Persist Stock rồi Movement, hoặc cascade theo domain.
- Flush/clear/reload.
- Xác nhận PK/FK chính xác.

### 49.2. Test parent existing

- Persist Stock trong transaction trước.
- Mở context mới.
- Lấy managed Stock qua `find`/`getReference` theo requirements.
- Persist Movement với ID đúng.
- Không vô tình INSERT lại Stock.

### 49.3. Test missing parent

DB FK phải chặn Movement trỏ Stock không tồn tại, nếu schema có constraint. `getReference` không tự chứng minh target row tồn tại trước khi flush/access.

### 49.4. Test parent deletion

Nếu Stock có Movements, policy có cho delete không? DB FK/cascade/removal semantics phải rõ. Không bật `CascadeType.REMOVE`/orphanRemoval tùy ý cho independent/shared entities.

---

## 50. Kiểm thử value object liên quan optimistic locking

CustomerProfile có `@Version` và `shippingAddress` là embeddable.

Scenario:

```text
Tx A loads Profile#101 version=4
Tx B loads Profile#101 version=4

Tx A changes shipping address, commits -> version=5
Tx B changes billing address based on version=4,
     attempts flush/commit -> optimistic conflict
```

### 50.1. Tại sao embedded update vẫn liên quan concurrency?

Embedded columns thường là một phần row của owner entity. Hai transactions update hai groups fields có thể vẫn cùng owner version.

### 50.2. Không tự merge detached state sau exception

Sau `OptimisticLockException`, rollback/reload/re-evaluate business merge. Không copy stale billing/shipping values đè dữ liệu mới.

### 50.3. Test mới EntityManager cho mỗi transaction

Nếu cả A và B dùng cùng EM, không có hai independent snapshots và test không mô phỏng concurrency thật.

---

## 51. Mối quan hệ giữa composite keys, inheritance và value objects

Ba kỹ thuật có thể kết hợp nhưng làm mapping phức tạp hơn.

Ví dụ:

- `Payment` là root entity dùng inheritance.
- Payment có `Money` embeddable.
- `StockMovement` dùng composite key derived từ Stock.
- Movement có `@ElementCollection` labels hoặc metadata values.

### 51.1. Đừng cố bao phủ mọi giao điểm trong một test

Một test quá lớn có thể fail vì rất nhiều nguyên nhân và khó chẩn đoán. Tạo tests nhỏ theo mapping, rồi một vài end-to-end tests cho tổ hợp thực tế.

### 51.2. Test schema cho combined mappings

Inheritance + embeddable columns cần xem column placement theo strategy; @Embedded trong subclass sẽ nằm ở bảng tương ứng (SINGLE_TABLE chung, JOINED subtype, TABLE_PER_CLASS concrete), tùy provider/mapping.

### 51.3. Test query polymorphism với embedded fields

Nếu embedded property nằm ở root, root query có thể select/filter nó. Nếu property chỉ ở subtype, dùng subtype query/TREAT theo support.

### 51.4. Test migration evolution

Thêm subclass, thêm field vào embeddable hoặc thêm thành phần composite key là schema migration lớn; cần backward compatibility và tests với dữ liệu cũ.

---

# Phần V — Lỗi thường gặp và cách khắc phục

## 52. Những anti-pattern khi test khóa ghép

### 52.1. Chỉ assert ID object trong memory

`stock.getId().equals(expected)` sau constructor không chứng minh mapping.

### 52.2. @EmbeddedId thiếu equals/hashCode

Entity có thể persist nhưng collection Java và identity comparisons sai, ảnh hưởng cả test fixtures.

### 52.3. equals chỉ dùng một thành phần key

Có thể trộn tenants cùng SKU.

### 52.4. ID object có setters và bị mutate sau persist

Identity map có thể bất nhất.

### 52.5. @IdClass fields tên/kiểu không khớp entity @Id

Provider bootstrap có thể fail, hoặc behavior khác mong đợi.

### 52.6. @MapsId trỏ attribute path không tồn tại

Ví dụ `@MapsId("stockKey")` nhưng ID embeddable không có `stockKey`.

### 52.7. Composite FK chỉ có một @JoinColumn

Association có thể thiếu tenant và trỏ sai parent.

### 52.8. Test duplicate trong cùng EM nhưng tưởng đang test DB PK

Provider có thể chặn L1 identity collision trước SQL.

### 52.9. Không rollback transaction sau flush failure

Transaction có thể bị đánh dấu rollback-only hoặc aborted.

### 52.10. Tin H2 collation giống production

Case/Unicode equality và uniqueness có thể khác.

---

## 53. Những anti-pattern khi test inheritance

### 53.1. Chỉ query concrete subclass

Không chứng minh root polymorphic query trả đúng subclasses.

### 53.2. Không test discriminator value

SINGLE_TABLE có thể đọc nhầm subtype nếu metadata/schema không nhất quán.

### 53.3. Đặt subtype field NOT NULL trong SINGLE_TABLE một cách máy móc

Các subtype khác không có giá trị cột đó.

### 53.4. JOINED chỉ test row root

Subtype table có thể không có record đúng.

### 53.5. TABLE_PER_CLASS dùng ID generators cục bộ không thống nhất

Polymorphic root identity có thể bị xung đột.

### 53.6. Query @MappedSuperclass như entity

`@MappedSuperclass` không tự là JPA entity root.

### 53.7. Dùng Java class name như SQL discriminator không có mapping contract

`@DiscriminatorValue` quyết định giá trị theo metadata, không suy đoán từ simple class name.

### 53.8. Chỉ test kết quả và bỏ qua query shape

Một JOINED/TABLE_PER_CLASS hierarchy lớn có thể đúng nhưng chậm; thêm performance tests khi cần.

### 53.9. Thay inheritance strategy không đi cùng migrations

Tests dùng auto-DDL có thể pass nhưng production schema fail.

---

## 54. Những anti-pattern khi test value objects

### 54.1. Dùng hai embedded addresses cùng values

Mapping nhầm cột có thể không bị phát hiện.

### 54.2. Không @AttributeOverride cho hai @Embedded cùng kiểu

Duplicate columns hoặc provider-specific naming bất ngờ.

### 54.3. Nghĩ @Embeddable có entity identity độc lập

Không thể `em.find(PostalAddress.class,id)` theo entity semantics.

### 54.4. Thay đổi fields in-memory nhưng không flush/clear/reload

Không biết dirty checking đã persist chưa.

### 54.5. Giả định embedded null luôn materialize giống nhau

Provider/dialect có thể khác; cần test contract thực.

### 54.6. ElementCollection Set thiếu equality/hashCode

Duplicate/removal behavior sai.

### 54.7. Gọi persist trực tiếp cho element

`@ElementCollection` elements không phải entities.

### 54.8. Test List như có guaranteed order khi không mapping order

Database không tự duy trì order.

### 54.9. Tin AttributeConverter sẽ tự chạy trên mọi mapping

ID/version/relationship/special mappings có giới hạn.

### 54.10. Dùng BigDecimal.equals mà không cân nhắc scale

Money 10.0 vs 10.00 có thể bị coi khác theo Java equality.

### 54.11. Coi encryption/converter đồng nghĩa value object an toàn log

Java object vẫn có thể chứa plaintext PII.

---

## 55. Mẫu test plan cho một module

| Test ID | Chủ đề | Setup chính | Assertion |
|---|---|---|---|
| CK-01 | StockId equality | Hai instances cùng tuple | equals/hashCode cùng |
| CK-02 | StockId tenant boundary | Cùng SKU, tenant khác | không bằng nhau |
| CK-03 | Embedded PK roundtrip | persist/flush/clear | find bằng StockId mới |
| CK-04 | IDClass roundtrip | khác mapping | find bằng ID class |
| CK-05 | DB PK uniqueness | TxA commit, TxB duplicate | chỉ một row commit |
| CK-06 | Shared SKU across tenants | Hai tenant | cả hai hợp lệ |
| CK-07 | @MapsId | Stock và Movement | ID portion = FK |
| CK-08 | Composite FK | Missing parent | FK rejects |
| CK-09 | Concurrent insert | 2 tx/EM | không double commit |
| CK-10 | Query by key | JPQL nested ID paths | đúng rows |
| IN-01 | SINGLE_TABLE | Persist 2 subtypes | discriminator/type/fields |
| IN-02 | Polymorphic root | query Payment | cả hai subtype |
| IN-03 | TYPE/TREAT | subtype predicate | đúng type |
| IN-04 | JOINED | root + child tables | same PK, data đúng |
| IN-05 | TABLE_PER_CLASS | concrete tables | polymorphic query đúng |
| IN-06 | MappedSuperclass | inherited basic fields | đọc/ghi đúng |
| IN-07 | Optimistic version | concurrent update | conflict/rollback |
| VO-01 | Address equality | Hai address cùng fields | equals/hashCode |
| VO-02 | Two embeddeds | Billing != shipping | cột không trộn |
| VO-03 | Replace address | managed owner update | reload đúng |
| VO-04 | Nullable embedded | null/non-null transitions | persisted contract |
| VO-05 | Nested address | nested embeddable | path/column đúng |
| VO-06 | ElementCollection add | owner+2 elements | 2 rows sau reload |
| VO-07 | ElementCollection remove | delete one element | DB rows đúng |
| VO-08 | ElementCollection composite owner | cùng SKU khác tenant | không cross-tenant |
| VO-09 | Converter | EmailAddress normalization | DB + Java roundtrip |
| VO-10 | Money numeric equality | 10.0 vs 10.00 | theo domain rule |
| SYS-01 | Migrations | target database | PK/FK/columns/indexes |
| SYS-02 | Transaction durability | commit + new EM | row persisted |
| SYS-03 | Rollback | failed duplicate | không partial committed |
| SYS-04 | SQL shape | fetch/queries | không N+1 ngoài dự kiến |

### 55.1. Tối thiểu cần đủ data đa dạng

Nếu mọi test dùng một tenant, một subtype và billing=shipping, coverage rất thấp dù số test methods nhiều.

### 55.2. Tách integration tests thành suites

Một bộ fast unit/mapping tests chạy mỗi PR; cross-provider/database conformance và concurrency performance tests có thể chạy theo pipeline thích hợp, miễn rủi ro được theo dõi.

---

## 56. Bài tập thực hành

### Bài 1 — Equality của StockId

Hai `StockId("shop-a","BOOK-JPA")` được tạo độc lập có nên bằng nhau?

**Gợi ý:** Có, nếu value semantics dựa trên hai fields.

### Bài 2 — Tenant boundary

`StockId("shop-a","BOOK-JPA")` và `StockId("shop-b","BOOK-JPA")` có cùng identity không?

**Đáp án:** Không.

### Bài 3 — ID mutation

Vì sao không sửa `sku` trong `@EmbeddedId` sau khi persist?

**Gợi ý:** Persistent identity và HashMap/HashSet invariants.

### Bài 4 — Find trước flush

`em.find` trả lại object vừa `persist`. Đã chứng minh DB INSERT chưa?

**Đáp án:** Chưa; có thể L1 managed instance.

### Bài 5 — Flush vs commit

`em.flush` không lỗi có chắc dữ liệu đã durable?

**Đáp án:** Không; commit vẫn có thể fail/rollback.

### Bài 6 — EmbeddedId JPQL

Viết predicate lọc `tenantId` của `StockId`.

**Gợi ý:** `s.id.tenantId = :tenant`.

### Bài 7 — IdClass JPQL

Viết predicate lọc tenant nếu entity khai `@Id private String tenantId` trực tiếp.

**Gợi ý:** `s.tenantId = :tenant`.

### Bài 8 — IDClass contract

Vì sao IDClass phải có fields tên/kiểu tương ứng entity ID attributes?

**Gợi ý:** JPA dùng class đó làm representation của composite identity.

### Bài 9 — Composite PK

Có thể có hai Stock rows cùng SKU ở hai tenants?

**Gợi ý:** Có nếu PK là `(tenant_id,sku)` và không có constraint khác cấm.

### Bài 10 — DB duplicate

Nếu hai instances cùng ID trong cùng EntityManager bị từ chối, đã test được database PK chưa?

**Gợi ý:** Chưa chắc; test thêm EM/transaction mới.

### Bài 11 — @MapsId name

`@MapsId("stockKey")` đòi hỏi gì?

**Gợi ý:** ID embeddable có attribute `stockKey` tương ứng derived key portion.

### Bài 12 — Composite FK

Movement tham chiếu Stock có PK hai columns. Cần bao nhiêu join columns?

**Gợi ý:** Hai, để mapping đủ tenant và SKU.

### Bài 13 — Missing parent

Nếu Movement trỏ Stock không tồn tại, điều gì nên xảy ra khi FK thật được thực thi?

**Gợi ý:** DB từ chối INSERT/commit theo constraint timing.

### Bài 14 — Race insert

Hai transactions cùng chọn `(shop-a,BOOK-JPA)`. Bảo vệ cuối cùng là gì?

**Đáp án:** Composite PRIMARY KEY constraint ở database.

### Bài 15 — SINGLE_TABLE

Hai subclasses của Payment được lưu trong bao nhiêu table theo SINGLE_TABLE?

**Đáp án:** Một table chung cho hierarchy.

### Bài 16 — Discriminator

Tại sao cần test `payment_kind` của CardPayment?

**Gợi ý:** Root load phải xác định đúng concrete subtype.

### Bài 17 — Subtype column

Vì sao cột `bank_reference` có thể nullable trong SINGLE_TABLE?

**Gợi ý:** CardPayment không dùng nó.

### Bài 18 — Polymorphic query

`select p from Payment p` có thể trả các subclass nào?

**Gợi ý:** Mọi mapped concrete subtypes phù hợp query.

### Bài 19 — TYPE

`type(p) = CardPayment` đang lọc điều gì?

**Gợi ý:** Runtime persistent subtype trong hierarchy.

### Bài 20 — TREAT

Tại sao cần `treat(p as CardPayment).tokenReference`?

**Gợi ý:** Field chỉ có trên subclass, không có ở root Payment.

### Bài 21 — JOINED schema

Persist CardPayment với JOINED tạo rows ở đâu?

**Gợi ý:** Root table và subtype table, cùng primary key.

### Bài 22 — JOINED rollback

Nếu subtype INSERT lỗi sau root INSERT, kết quả committed cuối cùng nên là gì?

**Gợi ý:** Transaction rollback, không có partial root row nếu cùng transaction.

### Bài 23 — TABLE_PER_CLASS

Vì sao generator ID phải xét toàn hierarchy?

**Gợi ý:** Polymorphic identity/query có thể trùng ID giữa concrete tables nếu cấp không đúng.

### Bài 24 — MappedSuperclass

Có thể query `from AuditedRecord` nếu chỉ có `@MappedSuperclass` không?

**Đáp án:** Không như entity root.

### Bài 25 — AccessType

Base dùng field access, subclass annotation đặt trên getter không có `@Access`. Rủi ro?

**Gợi ý:** Provider bỏ qua/mapping sai annotation; test SQL/readback.

### Bài 26 — Embedded value

PostalAddress có independent persistent ID không?

**Đáp án:** Không, nó là value object được lưu cùng owner.

### Bài 27 — Two embedded addresses

Test nào phát hiện mapping billing và shipping lẫn cột?

**Gợi ý:** Persist hai values khác nhau rồi flush/clear/reload.

### Bài 28 — AttributeOverride

`name = "postalCode"` trong `@AttributeOverride` trỏ Java property hay SQL column?

**Đáp án:** Tên attribute JPA, không phải column name `postal_code`.

### Bài 29 — Value equality

Hai PostalAddress có fields giống nhau nhưng instance khác có nên bằng nhau?

**Gợi ý:** Có nếu domain value semantics.

### Bài 30 — Null embedded

Có nên mặc định all-null columns luôn materialize thành `null` trên mọi provider?

**Đáp án:** Không, kiểm tra runtime/provider contract.

### Bài 31 — Replacement

Đổi shipping address bằng object mới rồi chỉ assert getter. Đã đủ chưa?

**Gợi ý:** Chưa; flush/clear/load lại.

### Bài 32 — Mutable embeddable

Provider có luôn detect thay đổi sâu trong mutable embeddable không?

**Gợi ý:** Cần test enhancement/mapping/provider behavior.

### Bài 33 — ElementCollection

`em.persist(new ContactMethod(...))` có đúng không?

**Đáp án:** Không, ContactMethod không phải entity.

### Bài 34 — ElementCollection Set

Vì sao cần equals/hashCode cho ContactMethod trong Set?

**Gợi ý:** Duplicate/removal semantics.

### Bài 35 — Collection table

CustomerProfile có `@ElementCollection Set<ContactMethod>`: bảng con thuộc lifecycle nào?

**Gợi ý:** Owner value collection; không có independent entity identity.

### Bài 36 — Composite collection owner

Stock có key `(tenantId,sku)`. Collection join table chỉ FK theo sku có an toàn không?

**Gợi ý:** Không, có thể trộn tenant.

### Bài 37 — Money

`BigDecimal("10.0").equals(BigDecimal("10.00"))` có true không?

**Đáp án:** False; quyết định domain equality/normalization.

### Bài 38 — Currency

`USD` và `usd` trong Money có nên là một giá trị không?

**Gợi ý:** Domain quyết định và normalize sớm.

### Bài 39 — Converter

`AttributeConverter<EmailAddress,String>` cần kiểm thử những hướng nào?

**Gợi ý:** Java→DB, DB→Java, null, normalize và query parameters.

### Bài 40 — Converter và @Id

Có nên mặc định @Convert hoạt động như nhau trên ID/version/relationship field?

**Đáp án:** Không; có các giới hạn trong JPA/provider.

### Bài 41 — @DataJpaTest rollback

Test pass trong transaction rồi tự rollback. Đã kiểm tra durability sau commit chưa?

**Đáp án:** Chưa.

### Bài 42 — Testcontainers

Vì sao PostgreSQL Testcontainers có ích nếu production là PostgreSQL?

**Gợi ý:** Schema/dialect/constraint/locking behavior gần target hơn H2.

### Bài 43 — H2 collation

Case-insensitive SKU trên H2 có chứng minh production cũng vậy không?

**Gợi ý:** Không.

### Bài 44 — Unique PK constraint

Chỉ thấy `@EmbeddedId` annotation, có chắc DB có đúng composite PK không?

**Đáp án:** Không; cần kiểm tra migration/schema.

### Bài 45 — Constraint failure

Sau duplicate PK flush exception, có nên tiếp tục query bằng cùng transaction?

**Gợi ý:** Không mặc định; rollback trước, context mới để verify.

### Bài 46 — Concurrency

Hai threads cùng dùng một EntityManager để test race có hợp lệ không?

**Đáp án:** Không; mỗi thread có EM/tx riêng.

### Bài 47 — Polymorphic results

Một query không có ORDER BY có trả theo thứ tự insert không?

**Đáp án:** Không bảo đảm.

### Bài 48 — Versioned embedded change

Hai transactions đổi hai embedded groups trên cùng owner version cũ.

**Gợi ý:** Có thể optimistic conflict; test transaction isolation.

### Bài 49 — Root/subtype migration

Thêm subclass cho SINGLE_TABLE cần chú ý schema nào?

**Gợi ý:** Discriminator, subtype columns/nullability, constraints và backward compatibility.

### Bài 50 — Synthesis

Thiết kế test suite cho Stock+Movement+Payment+CustomerProfile; chọn 10 cases quan trọng nhất.

**Gợi ý:** Composite key equality, PK roundtrip, uniqueness, @MapsId FK, polymorphic root, subtype roundtrip, two embedded overrides, value replacement, element collection reload và DB migrations/commit checks.

---

## 57. Checklist triển khai

Trước khi coi một mapping phức tạp là ổn định:

- [ ] ID class có no-arg constructor, Serializable và equality/hashCode đúng.
- [ ] Composite key equality dùng **đủ** các thành phần key.
- [ ] ID fields không bị mutate trong lifecycle managed entity.
- [ ] Key normalization phù hợp với DB collation/uniqueness.
- [ ] `@EmbeddedId` round-trip sau flush/clear đúng.
- [ ] `@IdClass` field names/types khớp entity IDs.
- [ ] JPQL path tới composite ID đúng.
- [ ] Schema có PRIMARY KEY đúng các columns.
- [ ] DB chặn duplicate composite key trong transaction mới.
- [ ] Cùng SKU khác tenant hợp lệ theo business scope.
- [ ] Composite FK có đủ join columns.
- [ ] `@MapsId` trỏ đúng ID attribute/derived key portion.
- [ ] Parent/child persist order và cascade đúng.
- [ ] Missing parent được FK chặn nếu design yêu cầu.
- [ ] Concurrency tests dùng EM/transactions độc lập.
- [ ] Inheritance strategy được khai rõ và được migration hỗ trợ.
- [ ] SINGLE_TABLE discriminator và nullable subtype columns đúng.
- [ ] Root query trả đúng concrete subtypes.
- [ ] `TYPE`/`TREAT` query behavior đúng trên provider mục tiêu.
- [ ] JOINED root/subtype rows có cùng PK và FK đúng.
- [ ] TABLE_PER_CLASS ID generator phù hợp polymorphic hierarchy.
- [ ] `@MappedSuperclass` không bị query như entity root.
- [ ] Inherited access type/overrides hoạt động khi reload.
- [ ] Optimistic version conflict được test nếu hierarchy có writes.
- [ ] Embeddable equality/hashCode theo value semantics.
- [ ] Hai embedded instances cùng kiểu có AttributeOverrides rõ.
- [ ] Embedded null và partial-null cases được xác định.
- [ ] Replacement embeddable được persist qua dirty checking.
- [ ] Nested embedded paths map đúng columns.
- [ ] ElementCollection add/remove/replace/reload đúng.
- [ ] Set equality và collection ordering semantics đúng.
- [ ] ElementCollection composite owner join đúng tenant/key.
- [ ] Converter có tests cả hai hướng + null/normalization.
- [ ] Money/BigDecimal equality/precision được định nghĩa.
- [ ] Database target được dùng cho portability-sensitive tests.
- [ ] Migrations/schema có PK/FK/columns/indexes mong đợi.
- [ ] Flush và clear được dùng khi cần xác minh DB reads.
- [ ] Commit + new EM được test khi cần kiểm tra durability.
- [ ] Lỗi persistence được rollback, không reuse context sai trạng thái.
- [ ] Regression tests bao phủ cả correctness và query/transaction behavior.
- [ ] Fixtures không dùng dữ liệu cá nhân thực khi không cần thiết.
- [ ] Test suite không phụ thuộc thứ tự và không ghi dữ liệu ra DB chia sẻ.

## 58. Bảng tra cứu nhanh

| Nhu cầu | Cách làm |
|---|---|
| Test @EmbeddedId | persist → flush → clear → find bằng ID mới |
| Test @IdClass | ID class đúng tên/kiểu + find/reload |
| Test equality | equals/hashCode, HashMap, tenant boundary |
| Test duplicate composite PK | commit row A; Tx B INSERT duplicate; rollback |
| Test composite FK | @JoinColumns đầy đủ; DB FK schema |
| Test @MapsId | derived ID portion khớp parent key |
| Test mutation of key | API không cho phép sửa; state không phụ thuộc mutation |
| Test JPQL EmbeddedId | `s.id.tenantId`, `s.id.sku` |
| Test inherited root | query `from Payment` trả subtypes |
| Test SINGLE_TABLE | discriminator, subtype fields, root reload |
| Test JOINED | root + subtype rows, same PK |
| Test TABLE_PER_CLASS | polymorphic UNION semantics, ID uniqueness |
| Test subtype predicate | JPQL `TYPE` / `TREAT` |
| Test @MappedSuperclass | inherited fields mapped; no entity root query |
| Test @Version | concurrent stale update/rollback |
| Test @Embeddable | value equality + round-trip |
| Test two embedded attributes | @AttributeOverrides + distinct fixtures |
| Test null embedded | null/non-null transitions, provider behavior |
| Test replace value object | assign new VO, flush/clear/reload |
| Test @ElementCollection | add/remove/replace, collection table |
| Test composite owner collection | two join columns and two-tenant fixture |
| Test @AttributeConverter | Java→DB, DB→Java, null/normalized values |
| Test Money BigDecimal | precision, scale/equality domain semantics |
| Test migration correctness | DB catalogs + real schema |
| Test SQL behavior | generated SQL/statistics if performance-sensitive |
| Test commit durability | transaction A commit, EM B reload |
| Test rollback | failed transaction doesn't commit partial state |
| Test target dialect | PostgreSQL/MySQL/Oracle/Testcontainers matching deployment |

## 59. Tổng kết

1. **Khóa ghép là persistent identity gồm nhiều thành phần**. Test phải kiểm tra equality/hashCode, JPA mapping, DB PK và tenant scope, không chỉ kiểm tra object ID ở Java.
2. **`@EmbeddedId` và `@IdClass` có cách biểu diễn khác nhau**, cần test JPQL paths, find IDs và runtime schema tương ứng.
3. **`@MapsId` dùng để diễn đạt derived identity**; tên thuộc tính và composite FK phải khớp chính xác, nếu không provider có thể mapping sai hoặc bootstrap fail.
4. **Không sửa primary key của entity đã managed**; composite key nên ổn định và có API bất biến.
5. **Kế thừa entity phải kiểm thử theo strategy**, nhất là discriminator của SINGLE_TABLE, bảng gốc/phụ của JOINED và polymorphic query/ID generation của TABLE_PER_CLASS.
6. **`@MappedSuperclass` không phải entity root**, dù nó có thể khai inherited persistence attributes.
7. **Test JPQL đa hình**, bao gồm root query, subtype query và `TYPE`/`TREAT` khi code thật dùng chúng.
8. **Value object được kiểm tra bằng giá trị chứ không bằng identity**, đồng thời phải xác minh persistence round-trip qua `@Embedded`/`@AttributeOverride`.
9. **Hai embedded objects cùng kiểu cần fixtures khác nhau** để phát hiện nhầm cột và override.
10. **`@ElementCollection` phụ thuộc lifecycle owner**, cần test collection table, add/remove, equality, ordering và composite owner FK.
11. **`AttributeConverter` cần test hai chiều và DB column thật**, không chỉ unit test Java value type.
12. **Flush, clear và context/transaction mới là công cụ để nhìn thấy sự thật ở DB**. Flush không phải commit; commit/rollback behavior phải được test đúng ranh giới.
13. **H2 không thay mọi conformance test trên database đích**; migrations, constraints, collation, SQL dialect và locking có thể khác.
14. **Test mỗi invariants riêng rồi thêm ít end-to-end cases** để không tạo test khổng lồ khó chẩn đoán.
15. **Một mapping đúng phải giữ được tính đúng đắn khi persistence context đổi, dữ liệu kế thừa được truy vấn đa hình, và value object thay đổi theo domain semantics**.

**Kết luận:** Kiểm thử khóa ghép, kế thừa và đối tượng giá trị trong JPA đòi hỏi vượt qua mức “persist không lỗi”. Hãy xác nhận identity ở Java và database, các bảng/columns/FKs được tạo đúng, entity subclasses đọc lại đúng type qua root queries, embedded values và collections round-trip chính xác, đồng thời transaction boundaries và migrations phản ánh môi trường triển khai. Với bộ test có cấu trúc và fixtures đủ khác biệt, những lỗi tinh vi về ánh xạ và vòng đời sẽ được phát hiện sớm trước khi chúng trở thành sự cố dữ liệu thực tế.
