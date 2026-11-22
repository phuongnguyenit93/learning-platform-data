# Phân biệt kiểm thử quy tắc miền và kiểm thử ánh xạ JPA

> **Module:** Data Persistence Relational Access ORM JPA  
> **Chương:** Kiểm thử JPA  
> **Bài học:** Phân biệt kiểm thử quy tắc miền và kiểm thử ánh xạ JPA

Một lớp được đánh dấu `@Entity` có thể vừa chứa các quy tắc nghiệp vụ, vừa mang siêu dữ liệu ánh xạ Java–SQL. Ví dụ, `PurchaseOrder.submit()` có thể kiểm tra không cho gửi đơn hàng rỗng, còn `@OneToMany` và `@JoinColumn` mô tả cách các dòng hàng được lưu trong database. Cả hai thuộc cùng mã nguồn Java, nhưng **không thuộc cùng một hợp đồng kiểm thử**.

- **Kiểm thử quy tắc miền** (*domain rule testing*): trả lời “Hành vi nghiệp vụ và các bất biến của đối tượng có đúng không?” Thường chỉ cần JUnit và Java objects, không cần khởi động ORM, Spring hay DB.
- **Kiểm thử ánh xạ JPA** (*JPA mapping integration testing*): trả lời “ORM có lưu, cập nhật, tìm lại, xóa và chuyển đổi object graph sang database đúng theo metadata không?” Cần JPA provider, transaction và thường cần DB phù hợp môi trường triển khai.
- **Kiểm thử database và migration**: chứng minh unique/FK/check constraints, các đặc điểm transaction/locking và đường nâng cấp schema thật.
- **Kiểm thử service/API**: chứng minh transaction orchestration, authorization, error mapping và giao tiếp đầu-cuối.

Nếu chỉ chạy unit tests, lỗi `@JoinColumn(name="incorrect_fk")`, `orphanRemoval` hoặc enum mapping có thể bị bỏ qua. Nếu chỉ chạy JPA integration tests, bộ test dễ chậm, rối rắm và không bao phủ đầy đủ các trường hợp nghiệp vụ như quantity âm, đơn rỗng hay chuyển trạng thái sai.

**Nguyên lý của bài:** Chọn loại test theo điều cần chứng minh, chứ không theo việc lớp Java có annotation JPA hay không. Một `@Entity` có domain methods vẫn được unit test thuần Java; một repository test dùng mock không tự biến thành bằng chứng cho mapping SQL.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt domain invariant, persistence mapping contract và database constraint.
2. Xác định hành vi cần kiểm thử thuần Java, không cần EntityManager.
3. Biết khi nào cần Hibernate/JPA provider và database thực tế.
4. Giải thích vì sao `new Entity(...)` không tự chạy `@Column`, `@GeneratedValue`, cascade hoặc SQL.
5. Viết domain unit tests cho constructor, value object, trạng thái và phép tính.
6. Viết integration tests cho generated ID, enum, embedded fields, owning side, cascade và orphanRemoval.
7. Dùng `persist → flush → clear → find` để kiểm tra dữ liệu đã được ORM đồng bộ.
8. Hiểu persistence context/first-level cache có thể che lỗi test thế nào.
9. Phân biệt Bean Validation, Java validation và database constraints.
10. Tạo negative DB tests cho NOT NULL, UNIQUE, foreign key, CHECK.
11. Kiểm thử `@Version` với hai persistence contexts và hai transactions.
12. Hiểu giới hạn rollback mặc định của `@DataJpaTest`.
13. Dùng Testcontainers để kiểm tra mapping với database engine giống production.
14. Phân biệt schema được ORM sinh ra và schema được migrations tạo.
15. Không mock JPA provider khi mục tiêu là kiểm thử mapping.
16. Test repository JPQL/derived queries bằng provider thật.
17. Xác định lúc nào cần test LAZY loading, fetch plan, cache và N+1.
18. Thiết kế fixtures ổn định, không phụ thuộc generated IDs cố định.
19. Tránh kiểm thử cùng một edge case ở mọi tầng không cần thiết.
20. Thiết kế một test matrix dễ duy trì cho dự án JPA.

---

## 2. Bản đồ các tầng kiểm thử

```text
                  BUSINESS REQUIREMENTS
                           |
                           v
                   DOMAIN MODEL/RULES
             invariants, value objects, state
                           |
                   UNIT TEST thuần Java
                           |
                           v
                    APPLICATION SERVICE
              orchestration, authorization,
                   transaction boundary
                           |
                SERVICE/INTEGRATION TEST
                           |
                           v
                      JPA MAPPING
           @Entity @Embedded @JoinColumn @Version
                           |
               JPA PROVIDER INTEGRATION
                           |
                           v
                  JDBC + REAL DATABASE
                 FK, UNIQUE, CHECK, DDL,
                locking, isolation, schema
                           |
             DB/MIGRATION INTEGRATION TEST
                           |
                           v
                       API / SYSTEM
                   HTTP, security, events
                           |
                      END-TO-END TEST
```

| Cần chứng minh | Tầng phù hợp | Ví dụ |
|---|---|---|
| Đơn rỗng không được submit | Domain unit | `order.submit()` throw |
| Tổng tiền tính chính xác | Domain unit | BigDecimal và Money |
| Không sửa đơn sau submit | Domain unit | State transition |
| Child được insert cùng parent | JPA integration | Cascade persist |
| Child bị xóa khi gỡ khỏi aggregate | JPA integration | orphanRemoval |
| Foreign key đúng | JPA/DB integration | order_lines.order_id |
| @Embedded lưu đúng nhiều cột | JPA integration | unit_amount/unit_currency |
| @Version phát hiện stale write | Transaction integration | 2 EntityManagers |
| UNIQUE chống trùng toàn database | DB integration | Duplicate order_code |
| V1 schema nâng lên V2 không mất dữ liệu | Migration integration | Flyway/Liquibase |
| HTTP 409 khi xung đột version | API integration | Error mapping |

**Không cần test mọi phương thức ở mọi tầng.** Unit tests bao phủ logic nghiệp vụ rộng; integration tests nhắm tới những đặc tính chỉ provider/DB mới thực hiện được.

---

## 3. Kiểm thử quy tắc miền là gì?

Quy tắc miền (*domain rule*) diễn đạt nghiệp vụ được phép hay không được phép làm gì, độc lập với việc dữ liệu lưu ở SQL, NoSQL hay memory.

Ví dụ cho một đơn hàng:

- Mã đơn không rỗng.
- Đơn mới bắt đầu ở trạng thái `DRAFT`.
- Số lượng của một dòng hàng phải lớn hơn 0.
- Giá tiền không được âm.
- Các dòng hàng phải dùng chung một loại tiền tệ.
- Không được thêm trùng SKU trong một đơn.
- Không được submit đơn rỗng.
- Sau khi submit, không được thêm/xóa dòng.
- Tổng tiền là tổng `quantity × unitPrice`.
- Không được submit hai lần.

Các tình huống này có thể xác nhận ngay trên object graph trong bộ nhớ, không cần chạy SQL.

### 3.1. Kiểm thử bất biến và chuyển trạng thái

Một bất biến nên được bảo vệ qua public API của domain. Nếu `OrderLine` không cho quantity âm, test nên thử tạo hoặc thêm một dòng âm và kiểm tra exception xảy ra **trước khi đối tượng đi vào trạng thái không hợp lệ**.

Nếu `PurchaseOrder.submit()` chỉ hợp lệ từ DRAFT và có dòng hàng, test cần kiểm tra cả đường thành công và đường bị từ chối.

### 3.2. Java annotation không làm unit test trở thành JPA test

```java
PurchaseOrder order = new PurchaseOrder("PO-001");
order.submit();
```

Nếu test này không mở persistence context, không có JDBC và không gọi repository thật thì nó vẫn là **domain unit test**, dù `PurchaseOrder` được annotate `@Entity`.

### 3.3. Khi không cần Mockito

Nếu test chỉ gọi constructor, `addLine`, `submit`, `total`, không có dependency bên ngoài cần mock. Tạo object thật và assert kết quả thường đơn giản, chính xác hơn dựng nhiều mocks.

---

## 4. Kiểm thử ánh xạ JPA là gì?

Mapping test xác minh provider có thể đọc metadata và thực thi đúng persistence lifecycle.

Các ví dụ:

- `@Entity` được nhận diện, có entity name hợp lệ.
- `@Id`/`@GeneratedValue` sinh và giữ identity.
- `@Table`/`@Column` trỏ tới bảng/cột thật.
- `@Enumerated(STRING)` lưu và đọc lại enum đúng.
- `@Embedded`/`@AttributeOverride` lưu value object vào đúng columns.
- `@ManyToOne`/`@OneToMany` tạo quan hệ đúng owner và foreign key.
- `CascadeType.PERSIST` lưu child khi persist parent.
- `orphanRemoval=true` xóa child row khi bị gỡ khỏi relationship.
- `@Version` kiểm soát optimistic update.
- `@Convert` được gọi khi ghi/đọc dữ liệu.
- JPQL/Criteria/native queries có hoạt động trên schema/provider thật.
- Lazy associations hoạt động theo fetch plan và transaction semantics.

**Annotation không tự tác động database khi chỉ gọi `new`.** JPA provider phải quản lý object, thực hiện flush, SQL và transaction thì những thứ trên mới phát huy tác dụng.

---

## 5. Ví dụ xuyên suốt: aggregate đơn hàng

Chúng ta sẽ dùng mô hình:

```text
@Embeddable Money
  amount: BigDecimal
  currency: String

@Entity PurchaseOrder
  id: Long                @Id @GeneratedValue
  orderCode: String       @Column(unique=true)
  status: OrderStatus     @Enumerated(STRING)
  version: long           @Version
  lines: List<OrderLine>  @OneToMany(cascade=ALL, orphanRemoval=true)
       |
       +-- @Entity OrderLine
             id: Long           @Id @GeneratedValue
             order              @ManyToOne @JoinColumn(order_id)
             sku: String
             quantity: int
             unitPrice: Money   @Embedded with column overrides
```

Mô hình có cả **domain behavior** và **mapping semantics**, giúp đối chiếu hai loại test trên cùng dữ liệu.

---

## 6. Money: value object với domain rules

```java
package demo.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Locale;
import java.util.Objects;

@Embeddable
public class Money {

    @Column(name = "amount",
            precision = 19, scale = 2, nullable = false)
    private BigDecimal amount;

    @Column(name = "currency",
            length = 3, nullable = false)
    private String currency;

    protected Money() {
        // Constructor dành cho JPA provider.
    }

    public Money(BigDecimal amount, String currency) {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        if (amount.signum() < 0) {
            throw new IllegalArgumentException(
                "Amount must not be negative");
        }

        String code =
            currency.trim().toUpperCase(Locale.ROOT);
        Currency.getInstance(code);

        this.amount = amount.setScale(
            2, RoundingMode.UNNECESSARY);
        this.currency = code;
    }

    public static Money zero(String currency) {
        return new Money(BigDecimal.ZERO, currency);
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other);

        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Cannot add different currencies");
        }

        return new Money(
            amount.add(other.amount), currency);
    }

    public Money times(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        return new Money(
            amount.multiply(BigDecimal.valueOf(quantity)),
            currency);
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrency() {
        return currency;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof Money value)) return false;

        return amount.equals(value.amount)
            && currency.equals(value.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currency);
    }
}
```

### 6.1. Điều cần domain unit test

- Money âm bị từ chối.
- Giá trị có quá hai decimal digits bị từ chối.
- Currency code được chuẩn hóa.
- Cộng hai Money khác currency bị từ chối.
- Value equality đúng.
- Tính tiền chính xác bằng BigDecimal.

### 6.2. Điều cần JPA integration test

- Hai fields `amount` và `currency` được lưu ở cột đúng.
- JDBC/DB type giữ precision/scale.
- Sau `flush/clear/find`, Money có giá trị đúng.
- Các cột bắt buộc thật sự tồn tại và không bị null.

**Giới hạn của ví dụ:** Scale 2 là chính sách nghiệp vụ giả định. Hệ thống nhiều tiền tệ hoặc tính toán tài chính phức tạp có thể cần các quy tắc làm tròn và scale khác.

---

## 7. OrderLine: quy tắc miền và relationship mapping

```java
package demo.domain;

import jakarta.persistence.AttributeOverride;
import jakarta.persistence.AttributeOverrides;
import jakarta.persistence.Column;
import jakarta.persistence.Embedded;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(
        fetch = FetchType.LAZY,
        optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "sku",
            nullable = false, length = 100)
    private String sku;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "unit_amount",
                nullable = false,
                precision = 19,
                scale = 2)),
        @AttributeOverride(
            name = "currency",
            column = @Column(
                name = "unit_currency",
                nullable = false,
                length = 3))
    })
    private Money unitPrice;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            String sku,
            int quantity,
            Money unitPrice) {

        if (order == null) {
            throw new IllegalArgumentException(
                "Parent order is required");
        }

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "SKU must not be blank");
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        this.order = order;
        this.sku = sku.trim();
        this.quantity = quantity;
        this.unitPrice =
            Objects.requireNonNull(unitPrice);
    }

    void detachFromOrder() {
        this.order = null;
    }

    public Money lineTotal() {
        return unitPrice.times(quantity);
    }

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
    public Money getUnitPrice() { return unitPrice; }
}
```

### 7.1. Domain concerns

Constructor không cho SKU rỗng, quantity âm hoặc null price; `lineTotal()` tính chính xác.

### 7.2. JPA concerns

- `order_id` là khóa ngoại thật.
- Provider lưu embedded Money thành `unit_amount` và `unit_currency`.
- Generated ID có giá trị sau persist.
- LAZY association không gây sai behavior khi được truy cập trong persistence context hợp lệ.

Một test `new OrderLine(...)` không thể chứng minh SQL foreign key đúng.

---

## 8. PurchaseOrder: aggregate root

```java
package demo.domain;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "order_code",
        nullable = false,
        unique = true,
        length = 80)
    private String orderCode;

    @Enumerated(EnumType.STRING)
    @Column(
        name = "status",
        nullable = false,
        length = 20)
    private OrderStatus status;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true)
    private List<OrderLine> lines =
        new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(String orderCode) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException(
                "Order code must not be blank");
        }

        this.orderCode = orderCode.trim();
        this.status = OrderStatus.DRAFT;
    }

    public OrderLine addLine(
            String sku,
            int quantity,
            Money unitPrice) {

        requireDraft();
        Objects.requireNonNull(unitPrice);

        if (!lines.isEmpty()
            && !lines.get(0).getUnitPrice()
                .getCurrency()
                .equals(unitPrice.getCurrency())) {
            throw new IllegalArgumentException(
                "Mixed currencies not allowed");
        }

        String normalized = sku == null
            ? null : sku.trim();

        for (OrderLine existing : lines) {
            if (existing.getSku().equals(normalized)) {
                throw new IllegalArgumentException(
                    "Duplicate SKU");
            }
        }

        OrderLine line = new OrderLine(
            this, normalized, quantity, unitPrice);

        lines.add(line);
        return line;
    }

    public void removeLine(OrderLine line) {
        requireDraft();

        if (line == null || !lines.remove(line)) {
            throw new IllegalArgumentException(
                "Line not owned by this order");
        }

        line.detachFromOrder();
    }

    public void submit() {
        requireDraft();

        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot submit empty order");
        }

        status = OrderStatus.SUBMITTED;
    }

    public Money total() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Empty order has no currency");
        }

        String currency =
            lines.get(0).getUnitPrice().getCurrency();

        Money result = Money.zero(currency);

        for (OrderLine line : lines) {
            result = result.plus(line.lineTotal());
        }

        return result;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Order already submitted");
        }
    }

    public Long getId() { return id; }
    public String getOrderCode() { return orderCode; }
    public OrderStatus getStatus() { return status; }
    public long getVersion() { return version; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }
}
```

Enum:

```java
package demo.domain;

public enum OrderStatus {
    DRAFT,
    SUBMITTED
}
```

### 8.1. Domain behavior

`addLine` kiểm soát duplicate SKU, tiền tệ và trạng thái. `submit` kiểm soát chuyển trạng thái. `total` tính toán thuần Java.

### 8.2. ORM behavior

`@OneToMany(mappedBy="order")` nói parent là inverse side, child `OrderLine.order` là owning side. `cascade=ALL` và `orphanRemoval=true` điều khiển lifecycle của child khi thao tác trên managed aggregate. `@Version` giúp kiểm soát optimistic locking.

### 8.3. Đóng gói collection

Getter trả unmodifiable view, callers không thể sửa collection trực tiếp. JPA dùng **field access** vì mapping annotations được đặt trên fields; domain methods là con đường public để thay đổi aggregate.

---

## 9. Unit test cho domain: không database

```java
package demo.domain;

import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

class PurchaseOrderDomainTest {

    static Money usd(String amount) {
        return new Money(
            new BigDecimal(amount), "USD");
    }

    @Test
    void newOrderStartsAsDraft() {
        PurchaseOrder order =
            new PurchaseOrder("PO-001");

        assertEquals(
            OrderStatus.DRAFT,
            order.getStatus());

        assertTrue(order.getLines().isEmpty());
        assertNull(order.getId());
    }

    @Test
    void emptyOrderCannotBeSubmitted() {
        PurchaseOrder order =
            new PurchaseOrder("PO-002");

        assertThrows(
            IllegalStateException.class,
            order::submit);

        assertEquals(
            OrderStatus.DRAFT,
            order.getStatus());
    }

    @Test
    void totalUsesExactDecimalMath() {
        PurchaseOrder order =
            new PurchaseOrder("PO-003");

        order.addLine("A", 2, usd("12.50"));
        order.addLine("B", 3, usd("2.25"));

        assertEquals(
            usd("31.75"),
            order.total());
    }

    @Test
    void cannotEditAfterSubmit() {
        PurchaseOrder order =
            new PurchaseOrder("PO-004");

        order.addLine("A", 1, usd("10.00"));
        order.submit();

        assertEquals(
            OrderStatus.SUBMITTED,
            order.getStatus());

        assertThrows(
            IllegalStateException.class,
            () -> order.addLine(
                "B", 1, usd("5.00")));

        assertThrows(
            IllegalStateException.class,
            order::submit);
    }
}
```

### 9.1. Test này không dùng JPA

Không có `EntityManager`, không có repository, không cần tạo tables và không cần Spring application context.

### 9.2. ID null là quan sát Java, chưa chứng minh generation

`assertNull(order.getId())` xác minh ID ban đầu của object chưa persist. Nó **không** chứng minh database/provider sẽ sinh ID khi lưu.

### 9.3. Tại sao test này nhanh và rõ?

Nếu `submit()` không từ chối đơn rỗng, test fail vì domain behavior; developer không cần điều tra migration, JDBC URL hoặc transaction.

---

## 10. Các negative domain tests

```java
@Test
void rejectsNonPositiveQuantity() {
    PurchaseOrder order =
        new PurchaseOrder("PO-005");

    assertThrows(
        IllegalArgumentException.class,
        () -> order.addLine(
            "BOOK-A", 0, usd("5.00")));

    assertTrue(order.getLines().isEmpty());
}

@Test
void rejectsDuplicateSku() {
    PurchaseOrder order =
        new PurchaseOrder("PO-006");

    order.addLine("BOOK-A", 1, usd("5.00"));

    assertThrows(
        IllegalArgumentException.class,
        () -> order.addLine(
            "BOOK-A", 2, usd("5.00")));

    assertEquals(1, order.getLines().size());
}

@Test
void rejectsMixedCurrencies() {
    PurchaseOrder order =
        new PurchaseOrder("PO-007");

    order.addLine("BOOK-A", 1, usd("5.00"));

    assertThrows(
        IllegalArgumentException.class,
        () -> order.addLine(
            "BOOK-B", 1,
            new Money(
                new BigDecimal("5.00"), "EUR")));
}

@Test
void moneyHasValueEquality() {
    Money a = new Money(
        new BigDecimal("10.0"), "usd");

    Money b = new Money(
        new BigDecimal("10.00"), "USD");

    assertEquals(a, b);
    assertEquals(a.hashCode(), b.hashCode());
}
```

### 10.1. Hãy assert cả state sau lỗi

Một exception được ném chưa đủ nếu trước đó domain đã thêm một phần tử sai rồi mới throw. Kiểm tra `getLines()` và `getStatus()` vẫn nhất quán.

### 10.2. Không buộc exact exception message nếu không là public contract

Loại exception và invariant thường quan trọng hơn một chuỗi message dễ bị thay đổi khi refactor.

### 10.3. Không dùng double khi test tính tiền

`new BigDecimal("12.50")` minh bạch hơn tạo BigDecimal từ floating-point approximation.

---

## 11. Domain unit test khác JPA test cho Money ra sao?

Domain unit tests:

- `Money.plus` cộng chính xác.
- `Money.times` nhân đúng quantity.
- Two Money objects cùng giá trị so sánh bằng nhau.
- Giá trị âm/scale sai bị từ chối.
- Currency code không hợp lệ bị từ chối.

JPA integration tests:

- `@Embedded` được nhận diện.
- `unit_amount` và `unit_currency` nằm đúng trong `order_lines`.
- Numeric precision/scale được lưu và đọc lại.
- Giá trị sau reload đúng.
- NOT NULL/CHECK được thực thi ở database.

Đây là khác biệt giữa **nghĩa của giá trị** và **cách giá trị được biểu diễn bền vững**.

---

## 12. Vì sao mock EntityManager không kiểm được mapping?

Một test:

```java
EntityManager em = mock(EntityManager.class);
PurchaseOrder order =
    new PurchaseOrder("PO-MOCK");

em.persist(order);

verify(em).persist(order);
```

Chỉ chứng minh một method call đến mock. Nó không chạy provider, không thực thi SQL, không sinh key và không kiểm cascade.

### 12.1. Mock phù hợp ở đâu?

Một application service có repository port có thể được test bằng fake/mock để chứng minh gọi load/save và áp quy tắc nghiệp vụ đúng thứ tự.

### 12.2. Mock không thay integration test

Nếu cần kiểm `@JoinColumn`, `@Embedded`, JPQL, optimistic locking hoặc database constraint, phải để JPA provider xử lý mapping thật.

### 12.3. Dấu hiệu test mock quá sâu

Khi bạn cố viết mock mô phỏng `flush`, L1 identity map, cascading, optimistic versions và JDBC exceptions, bạn đang tự tái tạo ORM behavior — thường vừa sai vừa tốn công hơn integration test có DB.

---

## 13. JPA integration test cần môi trường gì?

Tối thiểu:

1. Provider như Hibernate ORM được khởi tạo.
2. Entity classes được nhận diện trong persistence unit.
3. Schema có bảng/cột tương ứng.
4. EntityManager/repository thật.
5. Transaction hoạt động.
6. Database hoặc engine test được lựa chọn có chủ đích.
7. Test fixture hợp lệ.
8. Assertions sau khi state đã được đồng bộ/đọc lại.

Flow thường dùng:

```text
Arrange:
  new PurchaseOrder + OrderLine + Money

Act:
  em.persist(order)
  em.flush()
  store generated IDs
  em.clear()
  em.find(PurchaseOrder.class, orderId)

Assert:
  status, orderCode, IDs
  child count and foreign keys
  unit amount/currency
  database constraints if relevant
```

### 13.1. Test sử dụng DB thật là integration test

Không phải test nhanh thuần Java; nó kiểm tra sự phối hợp giữa entity mapping, provider, JDBC và DBMS.

---

## 14. Flush và clear: hai bước quan trọng

### 14.1. Vấn đề nếu không clear

```java
em.persist(order);

PurchaseOrder again =
    em.find(PurchaseOrder.class, order.getId());

assertSame(order, again);
```

Persistence context có thể trả **chính managed instance đang có**. Test có thể xanh dù chưa chứng minh việc đọc dữ liệu từ DB.

### 14.2. Flush

```java
em.flush();
```

Yêu cầu ORM đồng bộ pending writes xuống database theo flush semantics. Nhiều SQL constraint/mapping errors xuất hiện lúc flush, nhưng một số lỗi có thể trì hoãn đến commit theo DB/provider.

### 14.3. Clear

```java
em.clear();
```

Detach tất cả managed entities khỏi persistence context. Lần `find` tiếp theo không lấy same instance từ first-level cache; nếu có second-level cache, provider có thể dùng nó, do đó muốn kiểm tra physical SQL thì cần instrumentation/bypass cache.

### 14.4. Readback pattern

```java
em.persist(order);
em.flush();

Long id = order.getId();

em.clear();

PurchaseOrder reloaded =
    em.find(PurchaseOrder.class, id);

assertNotNull(reloaded);
assertEquals(
    "PO-ROUNDTRIP",
    reloaded.getOrderCode());
```

Đây là bằng chứng mạnh hơn một assertion trên object chưa ra khỏi L1 context.

---

## 15. Spring Boot @DataJpaTest + PostgreSQL Testcontainers

Một integration test phổ biến:

```java
package demo.persistence;

import demo.domain.Money;
import demo.domain.OrderLine;
import demo.domain.OrderStatus;
import demo.domain.PurchaseOrder;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

@DataJpaTest(properties = {
    "spring.jpa.hibernate.ddl-auto=validate",
    "spring.flyway.enabled=true"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class PurchaseOrderMappingTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
        registry.add(
            "spring.datasource.username",
            postgres::getUsername);
        registry.add(
            "spring.datasource.password",
            postgres::getPassword);
    }

    @PersistenceContext
    private EntityManager em;

    private static Money usd(String amount) {
        return new Money(
            new BigDecimal(amount), "USD");
    }

    @Test
    void persistsAndReloadsOrderGraph() {
        PurchaseOrder order =
            new PurchaseOrder("PO-ROUNDTRIP");

        OrderLine line =
            order.addLine("BOOK-A", 2, usd("12.50"));

        order.submit();

        em.persist(order);
        em.flush();

        Long orderId = order.getId();
        Long lineId = line.getId();

        assertNotNull(orderId);
        assertNotNull(lineId);

        em.clear();

        PurchaseOrder loaded =
            em.find(PurchaseOrder.class, orderId);

        assertNotNull(loaded);
        assertEquals(
            OrderStatus.SUBMITTED,
            loaded.getStatus());
        assertEquals(1, loaded.getLines().size());

        OrderLine loadedLine =
            loaded.getLines().get(0);

        assertEquals(
            "BOOK-A", loadedLine.getSku());
        assertEquals(
            2, loadedLine.getQuantity());
        assertEquals(
            usd("12.50"),
            loadedLine.getUnitPrice());
        assertEquals(
            orderId,
            loadedLine.getOrder().getId());
    }
}
```

### 15.1. Điều kiện chạy

Ví dụ cần Spring Data JPA, Spring Test/JUnit, PostgreSQL JDBC, Testcontainers modules và Flyway/dependencies phù hợp stack. Với `ddl-auto=validate`, schema phải được tạo bởi migrations trước JPA validation; không thể chỉ mở container rỗng rồi mong provider tự tạo bảng.

### 15.2. Vì sao dùng @AutoConfigureTestDatabase?

`@DataJpaTest` có thể thay DataSource thành embedded database tùy version/cấu hình. Nếu mục tiêu là PostgreSQL container, cần xác nhận test thực sự kết nối đến PostgreSQL, không âm thầm chuyển sang H2.

### 15.3. Test này xác minh gì?

Nó chứng minh mapping thực thi trên DB đã migrate, parent/child và embedded Money được persist/read lại đúng sau flush/clear.

### 15.4. Test này chưa chứng minh gì?

Nó chưa tự chứng minh mọi CHECK/UNIQUE index, transaction rollback, optimistic conflict, concurrency hay đường upgrade từ schema cũ. Những điều đó cần các test riêng.

---

## 16. Schema SQL minh họa cho test

Dùng PostgreSQL migration:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_purchase_orders_code
        UNIQUE (order_code)
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_amount NUMERIC(19, 2) NOT NULL,
    unit_currency VARCHAR(3) NOT NULL,

    CONSTRAINT fk_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id),

    CONSTRAINT uq_lines_order_sku
        UNIQUE (order_id, sku),

    CONSTRAINT ck_lines_quantity
        CHECK (quantity > 0),

    CONSTRAINT ck_lines_price
        CHECK (unit_amount >= 0)
);

CREATE INDEX idx_lines_order_id
    ON order_lines(order_id);
```

### 16.1. Domain và DB có thể bảo vệ cùng một invariant

OrderLine constructor cấm quantity <= 0; DB CHECK cũng cấm. Java bảo vệ state qua public domain API, DB bảo vệ **mọi write path**, kể cả native SQL hoặc import jobs.

### 16.2. Không coi ORM validate kiểm mọi constraint

Hibernate `ddl-auto=validate` phát hiện một số mismatch giữa entity và schema, nhưng không bảo đảm kiểm mọi CHECK, index, FK option hoặc unique condition. Khi chúng là contract quan trọng, cần negative DB tests.

### 16.3. Không nhầm migration test với schema generation test

Nếu Hibernate create-drop tạo schema trực tiếp từ mapping, quên cập nhật Flyway migration sẽ không bị lộ. Test dùng schema do migrations tạo mới có thể phát hiện sự lệch ấy.

---

## 17. Cascade persist: unit test không đủ

Domain test:

```java
PurchaseOrder order =
    new PurchaseOrder("PO-CHILD");

order.addLine("SKU-A", 1, usd("8.00"));

assertEquals(1, order.getLines().size());
```

Điều này chỉ xác nhận Java collection có child.

JPA test:

```java
@Test
void persistingParentCascadesToChild() {
    PurchaseOrder order =
        new PurchaseOrder("PO-CASCADE");

    OrderLine line =
        order.addLine("SKU-A", 1, usd("8.00"));

    em.persist(order);
    em.flush();

    Long parentId = order.getId();
    Long childId = line.getId();

    assertNotNull(parentId);
    assertNotNull(childId);

    em.clear();

    OrderLine reloaded =
        em.find(OrderLine.class, childId);

    assertNotNull(reloaded);
    assertEquals(
        parentId,
        reloaded.getOrder().getId());
}
```

### 17.1. Owning side

`OrderLine.order` có `@ManyToOne` và `@JoinColumn`, nên là owning side của association. Parent `mappedBy="order"` là inverse side. Một Java List đủ phần tử không chứng minh FK đúng; đọc child ở context mới sẽ kiểm tra tốt hơn.

### 17.2. CascadeType.ALL có nhiều semantics

Nó bao gồm persist/merge/remove/refresh/detach theo JPA cascade types. Test nên tập trung lifecycle thực sự được domain sử dụng, tránh giả định cascade đồng nghĩa database `ON DELETE CASCADE`.

---

## 18. OrphanRemoval: cần kiểm row bị DELETE

Đơn hàng DRAFT có một Line. Khi gỡ Line khỏi managed parent, JPA có `orphanRemoval=true` cần xử lý orphan theo mapping/lifecycle.

```java
@Test
void removingLineDeletesPersistedOrphan() {
    PurchaseOrder order =
        new PurchaseOrder("PO-ORPHAN");

    OrderLine line =
        order.addLine("SKU-A", 1, usd("5.00"));

    em.persist(order);
    em.flush();

    Long parentId = order.getId();
    Long childId = line.getId();

    em.clear();

    PurchaseOrder managed =
        em.find(PurchaseOrder.class, parentId);

    OrderLine existing =
        managed.getLines().get(0);

    managed.removeLine(existing);

    em.flush();
    em.clear();

    assertNull(
        em.find(OrderLine.class, childId));
}
```

### 18.1. Domain test tương ứng

Nó chỉ cần bảo đảm `removeLine` làm List giảm đi một và không cho gỡ line khi SUBMITTED.

### 18.2. Integration test tương ứng

Nó bảo đảm **SQL row không còn** sau flush, không chỉ mất tham chiếu trong Java memory.

### 18.3. Gỡ child khỏi List và DELETE không luôn tương đương

Nếu không khai báo `orphanRemoval`, hoặc relationship mapping khác, gỡ child có thể không dẫn đến DELETE. Tùy FK nullability/owning side, việc gỡ quan hệ có thể gây lỗi constraint hoặc cần thao tác explicit.

---

## 19. Embedded value: round-trip và physical columns

Một unit test Money:

```java
assertEquals(
    usd("30.00"),
    usd("10.00").times(3));
```

Một JPA test lại cần xác nhận `unit_amount` và `unit_currency`.

Có thể kiểm qua entity reload như phần 15, và khi physical representation là contract thì đọc SQL:

```sql
SELECT unit_amount, unit_currency
FROM order_lines
WHERE id = ?;
```

### 19.1. Vì sao hai loại test khác nhau?

Phép tính Money đúng trong Java không chứng minh column overrides được provider nhận đúng. Ngược lại, lưu/read Money đúng không chứng minh `Money.plus` xử lý mixed currency đúng.

### 19.2. Thử các giá trị biên

Thử 0.00, 12.50 và số lớn nhưng vẫn trong NUMERIC(19,2). Kiểm làm tròn/truncation theo policy. Dùng dữ liệu và schema phù hợp database mục tiêu.

---

## 20. Enum mapping: unit test Java vs persisted representation

`PurchaseOrder.submit()` chuyển status thành `OrderStatus.SUBMITTED`: kiểm bằng unit test.

`@Enumerated(EnumType.STRING)` lưu chuỗi `SUBMITTED`: kiểm bằng JPA/DB test.

```java
order.submit();

em.persist(order);
em.flush();

Long id = order.getId();
em.clear();

PurchaseOrder loaded =
    em.find(PurchaseOrder.class, id);

assertEquals(
    OrderStatus.SUBMITTED,
    loaded.getStatus());
```

Nếu nghiệp vụ hoặc migrations dựa vào representation thực, có thể assert SQL:

```sql
SELECT status
FROM purchase_orders
WHERE id = ?;
```

### 20.1. Vì sao cần test?

Một thay đổi nhầm từ STRING sang ORDINAL có thể không làm unit test fail, nhưng làm lưu trạng thái bằng số hoặc không tương thích dữ liệu cũ.

### 20.2. Rename enum còn liên quan migration

Nếu DB đang có `SUBMITTED` mà Java đổi thành `PLACED`, cần data migration/transitional strategy. Chỉ test tạo schema sạch từ code mới có thể không phát hiện legacy value.

---

## 21. Generated ID và identity map

Sau `new`, ID của entity dùng generated strategy thường là null. Sau persist/flush:

```java
em.persist(order);
em.flush();

assertNotNull(order.getId());
```

### 21.1. Không assert một số ID cố định

`assertEquals(1L, order.getId())` dễ lỗi khi sequence/identity counters khác nhau hoặc tests chạy song song.

### 21.2. IDENTITY có thể INSERT sớm

Với `GenerationType.IDENTITY`, provider có thể cần thực hiện INSERT sớm để lấy generated ID. Vì vậy lỗi DB constraint có thể xảy ra ở `persist` hoặc `flush`, không nhất thiết ở cùng một method trong mọi setup.

### 21.3. First-level cache

Khi entity đã managed, `em.find` có thể trả cùng instance mà không SELECT. Đừng lấy `assertSame(order, em.find(...))` làm bằng chứng schema lưu đúng.

---

## 22. Database validation khác domain validation

So sánh ba cơ chế:

| Cơ chế | Ví dụ | Khi nào được thực thi? |
|---|---|---|
| Domain Java | quantity > 0 trong constructor | Khi gọi Java API |
| Jakarta Bean Validation | `@Positive`, `@NotNull` | Theo validation call/lifecycle integration |
| Database constraint | `CHECK(quantity > 0)` | Khi DB kiểm statement/transaction |

### 22.1. Domain validation phản hồi sớm

Các methods cần từ chối thao tác sai ngay cả khi chưa bắt đầu transaction.

### 22.2. Bean Validation không thay aggregate rules

`@Positive` có thể kiểm một field, nhưng điều kiện “không submit nếu lines rỗng” và “không sửa sau khi submitted” thường cần domain behavior cụ thể.

### 22.3. DB là lớp bảo vệ khi có nhiều writers

Import scripts, JDBC direct writes hoặc một service khác có thể bypass domain method. UNIQUE/CHECK/FK constraints ngăn dữ liệu sai ở database.

### 22.4. Kiểm thử đúng từng lớp

- Unit test quantity âm: assert constructor/`addLine` ném lỗi.
- DB constraint test quantity âm: gửi một SQL INSERT có giá trị sai qua JDBC/native SQL trong DB test.
- Bean Validation test: gọi validator hoặc lifecycle path phù hợp để xác minh annotations/groups.

---

## 23. Unique constraint cần DB test

Hai đối tượng riêng biệt:

```java
new PurchaseOrder("PO-DUP");
new PurchaseOrder("PO-DUP");
```

đều có mã hợp lệ về mặt cấu trúc object; tính duy nhất toàn database chưa được kiểm tra.

### 23.1. Integration scenario

1. Persist Order mã `PO-DUP` trong transaction A.
2. Commit.
3. Tạo Order khác cùng mã trong transaction B.
4. Thử persist/flush/commit.
5. Assert lỗi unique constraint đúng, không phải lỗi khác.
6. Rollback B.
7. Đọc DB ở transaction mới xác nhận chỉ có một record.

### 23.2. Vì sao không chỉ gọi existsByOrderCode?

Hai transactions có thể cùng thấy code chưa có rồi cùng INSERT. Race này cần database UNIQUE (hoặc kỹ thuật transaction/lock tương đương theo yêu cầu).

### 23.3. Test negative path phải kiểm root cause

Chỉ assert `RuntimeException` quá rộng có thể tạo false green do query syntax, FK hoặc connection failure. Trong project thật, assert SQLState/constraint name/root cause theo provider/DB stack.

---

## 24. Kiểm thử foreign key và CHECK

Dùng DB test disposable có parent row hợp lệ, rồi cố chèn child sai.

```sql
-- Ví dụ phải có purchase_orders.id = 42.
INSERT INTO order_lines (
    order_id,
    sku,
    quantity,
    unit_amount,
    unit_currency
) VALUES (
    42, 'INVALID', 0, 10.00, 'USD'
);
```

Nếu schema có `CHECK(quantity > 0)`, DB phải từ chối.

Thử orphan FK:

```sql
INSERT INTO order_lines (
    order_id,
    sku,
    quantity,
    unit_amount,
    unit_currency
) VALUES (
    99999999, 'ORPHAN', 1, 10.00, 'USD'
);
```

Nếu parent ID đó không tồn tại, DB phải từ chối FK.

### 24.1. Tại sao không tạo child sai bằng domain constructor?

Domain public API đã từ chối quantity=0. Nếu muốn **kiểm chứng DB guardrail riêng**, phải bypass Java validation bằng native SQL/test fixtures hợp lệ cho mục tiêu kiểm thử.

### 24.2. Không dùng transaction lỗi để test tiếp

Với PostgreSQL, một SQL statement lỗi thường khiến transaction phải rollback trước khi thực thi các statements tiếp. Mỗi negative constraint test nên ở transaction riêng hoặc rollback/cleanup đúng cách.

---

## 25. Optimistic locking: test hai transactions

`@Version` giúp JPA phát hiện stale updates. Unit test `getVersion()` không chứng minh concurrency behavior.

Kịch bản:

```text
Create + COMMIT Order#42, version 0

Transaction A:
    load Order#42, version 0

Transaction B:
    load Order#42, version 0

Transaction A:
    submit order
    flush/commit -> success, version 1

Transaction B:
    submit stale copy
    flush/commit -> optimistic conflict
    rollback

New transaction:
    verify committed state of A
```

### 25.1. Cần hai persistence contexts thật

Nếu hai references được tìm trong cùng EntityManager, JPA identity map thường trả cùng managed instance, không mô phỏng hai clients độc lập.

### 25.2. Dữ liệu seed phải đã commit

Nếu test bao quanh mọi thứ bằng transaction rollback mặc định của `@DataJpaTest`, EntityManager B có thể không nhìn thấy data seed chưa commit.

### 25.3. Lỗi có thể xuất hiện ở flush hoặc commit

Theo JPA provider và DBMS, exception có thể được wrap bởi `OptimisticLockException`, `RollbackException`, Spring exceptions hoặc Hibernate stale exception. Test nên kiểm root cause/semantics đúng với stack, không chỉ bắt bất kỳ RuntimeException nào.

### 25.4. Đừng quên rollback transaction thua

Một optimistic conflict làm transaction không còn khả năng commit thành công. Dùng finally cleanup và context mới để xác minh persisted state.

---

## 26. Ví dụ RESOURCE_LOCAL cho hai EntityManagers

Đoạn code dưới đây là mẫu cho JPA `RESOURCE_LOCAL`. Với Spring/JTA, dùng transaction manager tương ứng thay vì `EntityManager.getTransaction()`.

```java
EntityManager seed = emf.createEntityManager();
Long orderId;

try {
    seed.getTransaction().begin();

    PurchaseOrder order =
        new PurchaseOrder("PO-CONCURRENT");

    order.addLine(
        "SKU-A", 1,
        new Money(
            new BigDecimal("10.00"), "USD"));

    seed.persist(order);
    seed.getTransaction().commit();

    orderId = order.getId();
} finally {
    seed.close();
}

EntityManager a = emf.createEntityManager();
EntityManager b = emf.createEntityManager();

try {
    a.getTransaction().begin();
    b.getTransaction().begin();

    PurchaseOrder first =
        a.find(PurchaseOrder.class, orderId);

    PurchaseOrder stale =
        b.find(PurchaseOrder.class, orderId);

    first.submit();
    a.getTransaction().commit();

    stale.submit();

    assertThrows(RuntimeException.class, () -> {
        b.flush();
        b.getTransaction().commit();
    });

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

Đây là **minh họa về transaction coordination**, không phải một test production hoàn thiện. Cần bổ sung assertions xác nhận root cause optimistic conflict và trạng thái DB cuối cùng; cũng cần tính đến locks/isolation trên target DBMS.

---

## 27. @DataJpaTest rollback: lợi ích và giới hạn

Spring Boot `@DataJpaTest` thường mở transaction cho từng test và rollback khi hoàn tất. Điều này giúp tests độc lập mà không phải xóa mọi row thủ công.

Tuy nhiên:

- Một số constraints/deferred checks chỉ lộ tại commit.
- Data trong uncommitted transaction không thấy được ở transaction khác theo isolation semantics.
- Một test gọi service `@Transactional` có thể tham gia test transaction và không thực hiện actual commit.
- Assertions về rollback sau exception không thể chỉ đọc managed object còn trong transaction đã lỗi.

### 27.1. Khi nào dùng TransactionTemplate?

Để kiểm nhiều transaction/commit/rollback thực, có thể dùng Spring `TransactionTemplate` hoặc `TestTransaction` theo phiên bản và cấu hình; hoặc tắt test-level transaction cho một test class và chủ động quản lý.

### 27.2. Không gọi self-invoked transactional methods rồi coi đã test proxy

Trong Spring proxy model, gọi `this.someTransactionalMethod()` có thể bypass proxy. Test transaction phải đi qua đường gọi thực tế.

---

## 28. Hibernate create-drop và migration tests

Hai test đều có thể tạo database sạch nhưng **nguồn schema khác**.

**Mapping-focused sandbox test:**

```properties
spring.jpa.hibernate.ddl-auto=create-drop
```

ORM dựa trên entity metadata để tạo schema tạm. Hữu ích kiểm annotations và CRUD.

**Migration-aligned integration test:**

```properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
```

Flyway/Liquibase tạo/upgrade schema theo versioned scripts; Hibernate chỉ validate (trong giới hạn provider).

### 28.1. Vì sao cần cả hai mục đích?

Một developer thêm `unit_currency` vào entity, test create-drop vẫn pass vì provider tự tạo column mới; production migration quên cột sẽ fail. Migration-aligned test phát hiện thiếu script.

### 28.2. Upgrade-path test còn khác nữa

Để chứng minh V1→V2 không mất dữ liệu, phải tạo schema ở V1, chèn legacy data, chạy pending migrations và assert rows/constraints. Fresh-install test từ DB rỗng chưa kiểm tra đường nâng cấp.

### 28.3. Không dùng Hibernate update để che lỗi

Trong suite kiểm tra migrations, `ddl-auto=update` có thể sửa schema tự động và làm test “xanh giả”. Hãy chọn rõ source of truth.

---

## 29. H2 so với PostgreSQL Testcontainers

H2 tiện cho integration tests nhẹ và phát hiện nhiều mapping defects. Nhưng H2 không tương đương PostgreSQL/MySQL/Oracle/SQL Server về:

- Identity/sequence semantics.
- Numeric scale/precision.
- Timestamp/timezone.
- JSON, array, enum columns.
- SQL syntax và identifier quoting.
- Constraints/indexes.
- Transaction isolation/locking.
- Query plans và performance.

### 29.1. Khi nào H2 đủ?

Khi test chỉ cần persistence smoke test không phụ thuộc database-specific behavior và tốc độ rất quan trọng.

### 29.2. Khi nào cần target DBMS?

Khi có migrations, native SQL, concurrency, constraints, custom types, converters, dialect-specific queries hoặc production-like behavior quan trọng.

### 29.3. Container không thay staging

PostgreSQL container có engine thật nhưng dữ liệu nhỏ, ít load và topology khác production. Performance, lock/DDL behavior trên bảng lớn vẫn cần rehearsal phù hợp.

---

## 30. Repository query tests

Một repository Spring Data:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder>
        findByOrderCode(String orderCode);

    @Query("""
        SELECT o
        FROM PurchaseOrder o
        WHERE o.status = :status
        ORDER BY o.id
        """)
    List<PurchaseOrder> findByStatus(
        @Param("status") OrderStatus status);
}
```

### 30.1. Cần kiểm gì?

- JPQL đúng tên entity/persistent attributes.
- Derived method `findByOrderCode` tạo query đúng.
- Enum parameters được bind đúng.
- Filters đúng khi có nhiều Orders khác trạng thái.
- Sorting/pagination đúng với `ORDER BY` phù hợp.
- Empty result không bị nhầm với lỗi.
- Không sinh duplicate roots khi join collections ngoài ý định.

### 30.2. Vì sao mock repository không đủ?

Mock trả một list do test tự lập. Nó không parse JPQL, không bind parameter, không chạy SQL và không biết schema.

### 30.3. Seed nhiều rows có khác biệt

Một dataset chỉ có một Order không phát hiện query quên WHERE hoặc ORDER BY. Tạo DRAFT/SUBMITTED orders, nhiều orderCodes và child counts khác nhau.

---

## 31. LAZY loading là mối quan tâm integration

Domain test:

```java
assertEquals(2, order.getLines().size());
```

không chứng minh LAZY behavior.

JPA integration có thể dùng:

```java
em.flush();
em.clear();

PurchaseOrder loaded =
    em.find(PurchaseOrder.class, orderId);

boolean initiallyLoaded =
    em.getEntityManagerFactory()
      .getPersistenceUnitUtil()
      .isLoaded(loaded, "lines");

int count = loaded.getLines().size();
```

### 31.1. Đừng khẳng định mọi provider bắt buộc trả false

LAZY là hint theo một số mapping và provider có thể fetch sớm do query graph/cache. Test portability nên tập trung vào functional loading; nếu muốn kiểm fetch strategy cụ thể, dùng provider/SQL instrumentation với expected behavior rõ.

### 31.2. LazyInitializationException không phải lỗi domain rule

Truy cập lazy association ngoài persistence context có thể lỗi. Đây là persistence boundary/fetch-plan issue, không nhất thiết `OrderLine` hoặc `submit()` sai.

### 31.3. Đo N+1 khi hiệu năng là yêu cầu

Một request truy cập Lines của 100 Orders có thể phát nhiều SQL. Nếu có performance budget, thêm integration test đo statement count/rows theo provider version, đồng thời tránh assertions quá brittle khi caching và batching thay đổi.

---

## 32. Transaction rollback phải test trên dữ liệu đã commit

Yêu cầu: khi một bước thanh toán lỗi, Order và Payment rows trong cùng transaction không được commit.

Domain unit tests có thể chứng minh service không tiếp tục business transition khi lỗi. Nhưng rollback thật cần kiểm:

```text
BEGIN
  INSERT Order
  INSERT Lines
  INSERT Payment -> fail
ROLLBACK

new transaction:
  SELECT Orders/Payments
  assert no partial committed data
```

### 32.1. Mock chỉ kiểm calls

`verify(repository).save(...)` không chứng minh SQL rollback.

### 32.2. Kiểm ở context/transaction mới

Đọc object graph chưa detach trong transaction bị rollback có thể cho bạn Java state không phản ánh DB. Sau failure, rollback và query từ context độc lập.

### 32.3. DB rollback không hủy external message

Email, Kafka publish hoặc HTTP call đã thực hiện trước rollback có thể vẫn xảy ra. Test transaction/outbox/integration phải xét điều này riêng.

---

## 33. Dùng test fixture builders thuần domain

```java
final class Orders {

    private Orders() {}

    static Money usd(String amount) {
        return new Money(
            new BigDecimal(amount), "USD");
    }

    static PurchaseOrder draftWithOneLine(
            String orderCode) {

        PurchaseOrder order =
            new PurchaseOrder(orderCode);

        order.addLine(
            "SKU-A", 1, usd("10.00"));

        return order;
    }
}
```

### 33.1. Dùng lại cho hai loại test

Domain test gọi builder rồi assert. JPA test gọi builder rồi `em.persist`.

### 33.2. Không để builder domain tự persist

Nếu builder gọi repository/EntityManager, unit tests bị phụ thuộc DB. Nếu integration suite cần helper persist, đặt nó ở persistence fixture layer riêng.

### 33.3. Không dựa vào ID=1 hay row insertion order

Generated IDs có thể khác giữa các lượt test; SQL rows không có order bảo đảm nếu thiếu `ORDER BY`.

---

## 34. Kiểm thử equality và identity

### 34.1. Value object Money

Hai Money cùng amount/currency hợp lệ thường được coi là bằng nhau; dùng unit test cho `equals/hashCode`.

### 34.2. Entity PurchaseOrder

Với generated ID, equality/hashCode cần thiết kế cẩn thận. Hai transient entities có ID null không nên tự bị coi là cùng identity. Ví dụ PurchaseOrder này dùng reference equality mặc định của Object, tránh một implementation ID-based sai.

### 34.3. Provider proxy

Nếu domain có entity equals/hashCode custom và Hibernate proxies, nên có integration tests cho proxy/loaded/detached cases nếu equality behavior quan trọng. Unit test đơn giản không mô phỏng đầy đủ proxies.

### 34.4. Persistence identity map

Trong cùng persistence context, tìm một entity type và primary key thường trả cùng managed identity. Điều này khác value equality và không phải bằng chứng trực tiếp cho physical database round-trip.

---

## 35. Tổ chức bộ test theo tốc độ và độ tin cậy

Một chiến lược:

```text
Fast suite (mỗi commit)
  Domain unit tests
  Application service unit tests with fakes

Persistence suite (CI)
  JPA round-trip
  Cascade / orphan
  Embedded / enum
  Repository queries
  DB constraints

Transaction suite (CI)
  Optimistic locking
  Rollback
  Isolation / concurrent updates

Migration suite (CI/release)
  Fresh-install migrations
  Upgrade from old schema
  Hibernate validate
  Legacy data assertions

System suite
  HTTP security / serialization
  Critical business journeys
```

### 35.1. Không lặp mọi unit edge case trong integration

Ví dụ 20 permutations của quantity không hợp lệ nên nằm ở unit tests; JPA test cần representative valid persist, DB constraint negative path và các rủi ro mapping thật.

### 35.2. Quan sát failures theo tầng

- Unit fail: logic Java/domain.
- JPA fail: annotation/provider/SQL relationship.
- Constraint fail: schema hoặc fixture.
- Migration fail: versioned DDL/data evolution.
- System fail: orchestration/config/security/network.

Sự phân tầng giúp developer tìm nguyên nhân nhanh hơn.

---

## 36. Những bẫy khi viết JPA tests

| Bẫy | Vấn đề | Cách tránh |
|---|---|---|
| Chỉ assert trên object trước persist | Không có bằng chứng persistence | Flush/clear/reload |
| Find ngay trong cùng EntityManager | L1 cache có thể trả same instance | Clear/new context |
| Assert ID = 1 | Generated IDs phụ thuộc môi trường | Assert non-null/unique |
| Assert thứ tự List không có mapping ORDER | SQL không cam kết order | ORDER BY/@OrderColumn nếu cần |
| Test DB constraint mà không flush | Lỗi chưa xuất hiện | Flush/commit |
| Chỉ catch mọi RuntimeException | False positive vì lỗi sai loại | Kiểm root cause/constraint |
| Tiếp tục dùng failed transaction | DB/context có thể unusable | Rollback/context mới |
| Dùng H2 để test PostgreSQL-specific SQL | Dialect không tương đương | Testcontainers target DB |
| Bật create-drop trong migration suite | Che thiếu migration | Flyway + validate |
| Dùng @DataJpaTest và kỳ vọng commit | Rollback mặc định | Explicit transactions |
| Dùng two EM nhưng seed chưa commit | Isolation không cho thấy data | Seed committed |
| Mock EntityManager | Không chạy metadata/SQL | Real provider test |
| Dùng @Transactional bean qua new | Không có proxy semantics | Lấy Spring bean |
| So sánh detached lazy collection | Có thể LazyInitializationException | Fetch đúng trong transaction |
| Assert SQL count quá chặt | Provider/cache changes gây brittle | Chỉ làm nếu performance contract |
| Builder tự persist | Unit tests lệ thuộc DB | Tách fixture layers |

---

## 37. Khi nào cần pure domain model tách khỏi JPA entities?

Có hai thiết kế phổ biến:

**Cùng một class làm domain entity và JPA entity:**

```text
PurchaseOrder.java
  @Entity + domain methods
```

Domain unit test gọi methods trực tiếp. JPA mapping test persist/read lại chính class đó. Ít mapping code nhưng domain phụ thuộc JPA annotations/no-args/access semantics.

**Tách domain và persistence model:**

```text
domain/PurchaseOrder          pure Java
persistence/JpaPurchaseOrder  @Entity
OrderMapper / JpaAdapter      conversion
```

Domain tests không phụ thuộc JPA; adapter integration tests kiểm mapping giữa domain và DB. Đánh đổi là thêm code chuyển đổi/state synchronization.

### 37.1. Cả hai cách đều cần phân biệt test responsibilities

Không nên đánh giá kiến trúc “thuần” hơn chỉ vì có nhiều lớp; chọn theo độ phức tạp domain, persistence constraints và khả năng bảo trì. Dù dùng chung hay tách lớp, không bỏ mapping integration tests.

---

## 38. Lập test matrix cho nghiệp vụ

| Scenario | Domain unit | JPA integration | DB/migration |
|---|---|---|---|
| DRAFT khi mới tạo | Chính | Round-trip representative | — |
| Cấm submit rỗng | Chính | Không cần lặp mọi path | — |
| Quantity > 0 | Chính | Optional representative | CHECK constraint |
| Mixed currency | Chính | Khi policy lưu trữ cần | — |
| Tính tổng tiền | Chính | Money round-trip | Precision |
| Duplicate SKU trong Order | Chính | Parent/child mapping | UNIQUE(order_id,sku) |
| ID sinh | Không | Chính | Identity DDL |
| Cascade insert | Không | Chính | FK |
| Orphan delete | Domain collection behavior | Chính | DELETE/FK semantics |
| Enum value | Transition chính | STRING round-trip | Legacy enum migration |
| Optimistic conflict | Không | Two transactions | Isolation |
| Service rollback | Service orchestration | Transaction integration | Committed state |
| JPQL findByStatus | Không | Chính | Schema |
| Thêm cột mới | Không | Mapping validate | Upgrade migration |
| HTTP error 409 | Không | Có thể kiểm service | API/E2E |

Bảng này là **phân công bằng chứng**, không phải yêu cầu viết đủ ba test cho mỗi hàng.

---

## 39. Bài thực hành A — Tách domain test khỏi JPA test

Cho test sau:

```java
@Test
void emptyOrderCannotSubmit() {
    var order = new PurchaseOrder("PO-EMPTY");

    em.persist(order);
    em.flush();

    assertThrows(
        IllegalStateException.class,
        order::submit);
}
```

1. Nêu chính xác mục tiêu kiểm thử.
2. Loại bỏ mọi bước DB không cần thiết.
3. Viết unit test thuần Java.
4. Viết integration test riêng cho phép persist DRAFT Order.
5. So sánh failure diagnostics và thời gian chạy.

---

## 40. Bài thực hành B — Domain invariant coverage

1. Order code rỗng bị từ chối.
2. Quantity 0 bị từ chối.
3. Quantity âm bị từ chối.
4. Money âm bị từ chối.
5. Amount có scale vượt policy bị từ chối.
6. Mixed currencies bị từ chối.
7. Duplicate SKU bị từ chối.
8. Submit rỗng bị từ chối.
9. Submit thành công.
10. Submit lần hai bị từ chối.
11. Không sửa lines sau submit.
12. Kiểm total với nhiều prices/quantities.

Toàn bộ phần này không cần database.

---

## 41. Bài thực hành C — Persistence round-trip

1. Tạo Order hợp lệ có hai Lines.
2. Persist parent.
3. Flush, lưu ID của parent/children.
4. Clear.
5. Find Order theo ID.
6. Assert orderCode/status.
7. Assert số Lines và nội dung.
8. Assert Money unit price.
9. Assert FK `order_id` bằng child.getOrder().getId().
10. Dùng SQL inspect columns nếu cần.
11. So sánh với test chỉ `assertSame` trong cùng EntityManager.

---

## 42. Bài thực hành D — Cascade và orphanRemoval

1. Persist parent với một Line.
2. Kiểm child ID sau flush.
3. Clear, reload parent.
4. Gỡ Line qua domain method.
5. Flush/clear.
6. Find child trả null.
7. Thử bỏ orphanRemoval trong sandbox khác.
8. Quan sát sự khác biệt.
9. Phân biệt JPA cascade REMOVE và database ON DELETE CASCADE.
10. Kiểm không xóa Line đã thuộc Order khác.

---

## 43. Bài thực hành E — DB constraint tests

1. Tạo UNIQUE(order_code).
2. Insert hai Orders trùng code ở transactions riêng.
3. Assert đúng unique violation.
4. Dùng native SQL insert quantity=0, assert CHECK.
5. Dùng native SQL order_id không tồn tại, assert FK.
6. Insert NULL vào required column, assert NOT NULL.
7. Kiểm đúng SQLState/constraint name nếu stack hỗ trợ.
8. Rollback sau negative tests.
9. Không sửa domain constructor chỉ để cho DB test đi qua.

---

## 44. Bài thực hành F — Optimistic locking

1. Seed/commit một DRAFT Order có Line.
2. Mở hai EntityManagers độc lập.
3. Load cùng Order/version.
4. A submit và commit.
5. B submit stale copy.
6. Assert optimistic conflict lúc flush/commit.
7. Rollback B.
8. Đọc lại bằng context mới.
9. Assert DB giữ trạng thái A.
10. Giải thích vì sao không dùng một EntityManager để tạo xung đột.

---

## 45. Bài thực hành G — Schema generation vs migration

1. Bật Hibernate create-drop ở test DB disposable.
2. Thêm column mới vào entity.
3. Chạy mapping test, quan sát schema mới.
4. Tắt create-drop; dùng Flyway và validate.
5. Cố tình thiếu migration cho column mới.
6. Quan sát startup/test fail.
7. Bổ sung versioned migration.
8. Test fresh install.
9. Test upgrade từ schema cũ có data.
10. Ghi khác biệt giữa hai bộ test.

---

## 46. Bài thực hành H — Repository integration

1. Tạo Orders DRAFT/SUBMITTED.
2. Test findByOrderCode.
3. Test findByStatus.
4. Test empty result.
5. Test ORDER BY với nhiều rows.
6. Test pagination theo parent.
7. Test enum binding.
8. Test persist/flush/clear giữa arrange và assert.
9. Thử sai JPQL attribute name trong sandbox.
10. Quan sát lỗi từ provider thật.

---

## 47. Bài thực hành I — Service transaction

1. Tạo Spring service với `@Transactional`.
2. Seed/commit Order.
3. Gọi service qua Spring bean/proxy.
4. Assert status persisted qua context mới.
5. Cho một DB operation fail giữa transaction.
6. Assert rollback, không có partial rows.
7. So sánh gọi trực tiếp `new Service(...)`.
8. Thử self-invocation và phân tích proxy boundary.
9. Tách domain transition unit test khỏi transaction integration test.

---

## 48. Bài thực hành J — H2 và Testcontainers

1. Chạy cùng mapping test trên H2.
2. Chạy trên PostgreSQL Testcontainers.
3. So sánh ID generation.
4. So sánh BigDecimal precision.
5. Kiểm FK/CHECK/UNIQUE.
6. Thử native query đặc thù PostgreSQL.
7. Test optimistic conflicts.
8. Ghi các khác biệt.
9. Chọn suite phù hợp target DBMS.
10. Không suy mọi kết quả H2 portable.

---

## 49. Bài thực hành K — Test fixture isolation

1. Tạo Orders builder thuần Java.
2. Tái sử dụng ở unit và integration tests.
3. Không để domain builder tự persist.
4. Không assert generated ID cụ thể.
5. Không phụ thuộc SQL row order.
6. Dùng business keys riêng cho từng test.
7. Chạy tests song song trên isolated schemas nếu cần.
8. Test cleanup sau transaction lỗi.
9. Kiểm dữ liệu test không rò giữa các cases.

---

## 50. Bài thực hành L — Chẩn đoán lỗi theo tầng

Cố tình gây các lỗi:

1. Bỏ kiểm quantity dương trong constructor.
2. Đổi `@JoinColumn` thành tên sai.
3. Bỏ cột `unit_currency` khỏi migration.
4. Bỏ `@Transactional` ở service.
5. Đổi `EnumType.STRING` thành `ORDINAL`.

Với mỗi lỗi: test nào fail đầu tiên? Lỗi thuộc domain, ORM, schema, transaction hay API? Test nào vẫn có thể xanh giả? Có cách nào phát hiện lỗi nhanh hơn mà không thêm quá nhiều integration tests?

---

## 51. Checklist trước khi merge

| Câu hỏi | Cần xác nhận |
|---|---|
| Domain rule có unit tests không DB? | Có |
| Test không dùng EntityManager chỉ để kiểm Java method? | Có |
| Có negative/edge domain scenarios? | Có |
| State không bị hỏng sau exception? | Có |
| Money equality/BigDecimal chuẩn? | Có |
| Mapping test có real provider? | Có |
| Mapping test có DB phù hợp? | Có |
| Round-trip có flush/clear/find? | Có |
| Không nhầm L1 cache với persisted data? | Có |
| Generated IDs không bị hardcode? | Có |
| Cascade persist đã được kiểm? | Có |
| Orphan DELETE đã được kiểm? | Có |
| FK owning side đúng? | Có |
| @Embedded fields round-trip đúng? | Có |
| Enum representation được kiểm khi cần? | Có |
| DB constraints có negative tests riêng? | Nếu quan trọng |
| DB error root cause được kiểm? | Có |
| Failed transaction được rollback/cleanup? | Có |
| @Version có two-context test? | Nếu cần concurrency |
| Transaction seed đã commit trước concurrent test? | Có |
| JPA queries được test với multiple records? | Có |
| H2 limitations được biết? | Có |
| Testcontainers target DBMS được dùng khi cần? | Có |
| Migration suite không bị ORM auto-update che lỗi? | Có |
| Fresh-install/upgrade tests tồn tại? | Nếu DB có lịch sử |
| Spring @DataJpaTest rollback được hiểu? | Có |
| Service @Transactional được test qua proxy? | Khi cần |
| Không assert SQL row order thiếu ORDER BY? | Có |
| Lazy fetching ngoài transaction được xử lý? | Có |
| Test suite phân tầng và chạy ổn định? | Có |

---

## 52. Ngộ nhận thường gặp

### 52.1. Có `@Entity` nên mọi test của class phải dùng DB

Sai. Domain methods vẫn là Java và nên được unit test khi phù hợp.

### 52.2. Domain tests xanh nên mapping chắc chắn đúng

Sai. Annotation, FK, enum mapping, cascade và DB schema chưa được kiểm.

### 52.3. Mock EntityManager verify(persist) là mapping test

Sai. Mock không thực thi JPA provider.

### 52.4. Persist rồi find trong cùng EntityManager chứng minh SQL round-trip

Không đủ. L1 identity map có thể trả lại same managed instance.

### 52.5. save luôn gửi INSERT ngay

Không mặc nhiên. Flush/commit và ID generation strategy ảnh hưởng thời điểm SQL.

### 52.6. @Column(nullable=false) bảo đảm constructor throw

Không. Đây là mapping metadata, không thay domain validation.

### 52.7. Giảm size của List chứng minh orphanRemoval

Không. Cần xác minh child row DELETE sau persistence synchronization.

### 52.8. @Version chỉ cần assert tăng một con số trong Java

Không. Optimistic locking đòi hai transactions cạnh tranh thật.

### 52.9. H2 pass thì PostgreSQL chắc pass

Không. Dialect, constraints, types và locking khác nhau.

### 52.10. @DataJpaTest luôn commit

Không. Test slice thường rollback theo mặc định, cần explicit transaction tests khi muốn kiểm commit.

### 52.11. Hibernate validate kiểm mọi schema feature

Không. Nó là guardrail có phạm vi, không thay CHECK/index/FK/data assertions.

### 52.12. Mỗi domain edge case phải có thêm một test HTTP/DB giống hệt

Không. Chia coverage theo mức rủi ro/tầng phù hợp.

### 52.13. Catch mọi RuntimeException đủ cho negative DB test

Không. Có thể xanh vì lỗi hoàn toàn khác với expected constraint.

### 52.14. Assert ID=1 và thứ tự insertion là ổn định

Không. Generated ID và SQL ordering thay đổi theo test isolation/provider/DB.

### 52.15. Test Spring @Transactional bằng cách new service object là đủ

Không. Transaction proxy semantics phải được kiểm trên Spring-managed bean.

---

## 53. Câu hỏi ôn tập

1. Domain unit test và JPA mapping test khác nhau về mục tiêu nào?
2. Tại sao `new PurchaseOrder` không chạy `@Column`?
3. Khi nào entity class annotated vẫn unit test được mà không DB?
4. Domain invariant là gì? Cho ba ví dụ.
5. `PurchaseOrder.submit()` nên được test ở tầng nào?
6. `@JoinColumn` nên được test ở tầng nào?
7. Lý do cần `flush` trong JPA test?
8. Lý do cần `clear` trước khi tìm lại entity?
9. L1 cache có thể tạo false confidence ra sao?
10. Vì sao `assertSame(order, em.find(...))` không chứng minh DB round-trip?
11. `@Embedded Money` có hai loại test nào?
12. Vì sao BigDecimal value equality là domain test?
13. Vì sao precision/scale trong SQL là mapping/DB test?
14. `CascadeType.ALL` cần kiểm qua database thế nào?
15. `orphanRemoval=true` khác xóa khỏi Java List ở đâu?
16. Phía nào sở hữu quan hệ `@OneToMany(mappedBy)` và `@ManyToOne`?
17. Vì sao domain code có thể bảo vệ quantity nhưng DB cũng nên có CHECK?
18. UNIQUE constraint cần kiểm trong transaction thực vì sao?
19. Tại sao kiểm `existsByOrderCode` trước insert vẫn có race?
20. Khi nào database có thể báo lỗi unique?
21. Vì sao cần rollback khi một SQL statement đã fail?
22. `EnumType.STRING` được kiểm thế nào?
23. Vì sao unit test chuyển enum không đủ?
24. `@Version` có tác dụng gì với concurrent writes?
25. Vì sao cần hai EntityManagers để test optimistic conflict?
26. Dữ liệu seed chưa commit gây vấn đề gì?
27. Mockito repository phù hợp với loại test nào?
28. Vì sao mock repository không xác nhận JPQL?
29. `@DataJpaTest` làm gì và giới hạn nào?
30. Datasource replacement ảnh hưởng Testcontainers ra sao?
31. H2 khác PostgreSQL ở những điểm có liên quan?
32. ORM create-drop test khác migration-aligned integration thế nào?
33. Hibernate update có thể che migration bug ra sao?
34. Fresh-install migrations khác upgrade-path migrations test thế nào?
35. Vì sao SQL order phải được xác định rõ khi assert?
36. Có nên hard-code generated ID không?
37. Khi nào cần LAZY/fetch tests?
38. Khi nào test rollback cần context mới?
39. JPA entity và domain model có buộc phải là cùng một class?
40. Với một project mới, bạn sẽ chọn tối thiểu những domain unit và JPA mapping tests nào cho PurchaseOrder?

---

## 54. Tổng kết ngắn gọn

| Vấn đề | Kiểm thử phù hợp |
|---|---|
| Quy tắc và trạng thái miền | JUnit thuần Java |
| Hành vi value object | Unit test không DB |
| Service phối hợp dependencies | Unit/fake hoặc service integration |
| Ánh xạ bảng/cột/relationship | JPA provider integration |
| Generated ID, cascade, orphanRemoval | JPA integration với flush/clear |
| Enum/embedded value round-trip | JPA integration |
| NOT NULL, FK, UNIQUE, CHECK | Target DB integration |
| Optimistic locking, rollback | Multiple transactions/contexts |
| Schema create và upgrade | Migration integration |
| HTTP/security/serialization | API/E2E |

### Quy tắc quyết định

```text
             CẦN KIỂM CHỨNG MỘT HÀNH VI
                           |
                           v
                Có thể chứng minh bằng
                  Java objects thuần?
                    /           \
                  CÓ            KHÔNG
                   |               |
                   v               v
             DOMAIN UNIT     Phụ thuộc JPA/SQL?
                 TEST            /       \
                               CÓ       KHÔNG
                                |         |
                                v         v
                         JPA INTEGRATION Service/API/
                                |         External tests
                                v
                       Cần DB constraint,
                      locking hoặc migration?
                            /        \
                          CÓ         KHÔNG
                           |           |
                           v           v
                      DB/TRANSACTION  JPA round-trip
                       INTEGRATION    flush/clear/find
                           |           |
                           +-----+-----+
                                 |
                                 v
                         Assert persistent
                       contract đúng tầng
```

**Ghi nhớ:** Kiểm thử quy tắc miền chứng minh **đúng nghiệp vụ** bằng việc gọi Java methods trên object state; kiểm thử ánh xạ JPA chứng minh **đúng persistence contract** khi provider thực hiện SQL, lifecycle, transaction và hydration trên database. `@Entity` không bắt mọi behavior phải test qua DB, nhưng Mockito/Java constructor cũng không thể chứng minh `@JoinColumn` hay `orphanRemoval` đúng. Một bộ test tốt kết hợp unit tests nhanh cho edge cases với integration tests có chủ đích cho mapping, constraints và concurrency — mỗi tầng cung cấp bằng chứng mà tầng kia không thể thay thế.

