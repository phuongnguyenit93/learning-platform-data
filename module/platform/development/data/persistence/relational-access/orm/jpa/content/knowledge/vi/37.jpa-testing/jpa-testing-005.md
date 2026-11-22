# Kiểm thử phía sở hữu, cascade và orphanRemoval trong JPA

Một quan hệ JPA có thể trông hoàn toàn đúng khi nhìn vào object Java nhưng vẫn lưu sai xuống database. Ví dụ một đơn hàng có danh sách dòng hàng:

```java
order.getLines().add(line);
```

Sau lời gọi trên, `order.getLines().size()` đã tăng. Nhưng điều đó **không chứng minh khóa ngoại `order_id` trong bảng dòng hàng đã được cập nhật**. Nếu quan hệ hai chiều có `mappedBy`, phía sở hữu quan hệ mới quyết định cách đồng bộ liên kết trong database. Nếu code chỉ sửa collection ở phía đối ứng, hai đầu quan hệ có thể mâu thuẫn.

Tương tự:

```java
em.persist(order);
```

không tự động persist mọi object liên quan nếu không có cascade phù hợp; và:

```java
order.removeLine(line);
```

không tự động có nghĩa database sẽ DELETE dòng hàng, trừ khi mapping và quy trình cập nhật quan hệ đáp ứng điều kiện như `orphanRemoval = true`.

Bài này thuộc chương **Kiểm thử JPA**, trong chủ đề **Data Persistence Relational Access ORM JPA**, với đề mục **“Kiểm thử phía sở hữu, cascade và orphanRemoval”**.

Sau bài, người học có thể:

1. Xác định đúng **owning side** và **inverse side** của quan hệ JPA.
2. Kiểm tra sự đồng bộ giữa collection ở Java và khóa ngoại trong database.
3. Phân biệt các hành động **persist**, **merge**, **remove** được truyền qua `CascadeType` với hành vi xóa orphan.
4. Viết integration test xác minh `@OneToMany`, `@ManyToOne` và `@OneToOne`.
5. Phân biệt `flush()`, `commit()` và việc quan sát trạng thái từ persistence context hiện tại.
6. Kiểm tra thao tác thêm, bỏ, xóa parent, cập nhật quan hệ và chuyển child giữa parents.
7. Nhận biết bẫy từ `equals/hashCode`, `List`/`Set`, nullable foreign keys và các query bulk.
8. Thiết kế test dùng transaction độc lập với fixture, đọc lại dữ liệu từ `EntityManager` mới.
9. Sử dụng JUnit 5, JPA RESOURCE_LOCAL, Testcontainers và Spring JPA test đúng ranh giới.
10. Tránh test xanh giả khi chỉ assert trạng thái trong bộ nhớ hoặc dùng schema tự sinh khác production.

**Thông điệp trung tâm:** *Kiểm thử quan hệ JPA phải xác minh cả graph Java lẫn trạng thái đã commit trong database. Cascade quyết định thao tác lifecycle lan truyền; owning side quyết định quan hệ được ghi thế nào; orphanRemoval quyết định điều gì xảy ra với child bị tách khỏi quan hệ sở hữu vòng đời.*

---

## 1. Ba khái niệm độc lập phải kiểm thử riêng

### 1.1. Owning side — phía sở hữu quan hệ

Trong một association hai chiều, JPA chỉ định một phía là **owning side**. Phía này kiểm soát cập nhật biểu diễn quan hệ trong database.

Ví dụ:

```java
@Entity
class PurchaseOrder {

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
```

```java
@Entity
class OrderLine {

    @ManyToOne
    @JoinColumn(name = "order_id")
    private PurchaseOrder order;
}
```

`OrderLine.order` là phía sở hữu. `PurchaseOrder.lines` là phía đối ứng, được khai báo bởi `mappedBy = "order"`.

### 1.2. Cascade — lan truyền thao tác lifecycle

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
private List<OrderLine> lines;
```

Khi `em.persist(order)`, JPA có thể lan truyền `persist` tới các lines phù hợp, theo association được cascade.

Điều này **không làm thay đổi phía sở hữu khóa ngoại**.

### 1.3. orphanRemoval — xử lý child bị loại khỏi quan hệ

Ví dụ:

```java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Khi một **managed child có vòng đời phụ thuộc parent** bị tách khỏi association được cấu hình, provider thực hiện thao tác remove theo semantics của JPA, thường vào lúc flush.

Điều này khác với `CascadeType.REMOVE`, vốn chủ yếu lan truyền hành động xóa **parent** sang các target được cascade.

### 1.4. Bảng phân biệt

| Cơ chế | Câu hỏi được trả lời | Không tự bảo đảm |
| --- | --- | --- |
| Owning side | Phía nào điều khiển liên kết DB? | Persist/remove tự động |
| `mappedBy` | Property nào bên kia sở hữu? | Hai phía Java tự đồng bộ |
| `CascadeType.PERSIST` | Persist parent có lan sang child? | Xóa orphan khi rời collection |
| `CascadeType.MERGE` | Merge graph có lan sang child? | Mọi detached graph đều an toàn |
| `CascadeType.REMOVE` | Remove parent có lan sang child? | Remove child khỏi collection sẽ DELETE |
| `CascadeType.ALL` | Áp dụng toàn bộ cascade operations | Một domain aggregate an toàn trong mọi quan hệ |
| `orphanRemoval = true` | Child bị tách khỏi association có bị remove? | Chuyển child đã orphan sang parent khác an toàn |
| DB `ON DELETE CASCADE` | DB xóa dependent rows khi xóa key cha | JPA callback/context semantics giống cascade remove |

**Một bài test đúng cần nêu rõ cơ chế nào đang được kiểm chứng, không gộp mọi kết quả thành “cascade hoạt động”.**

---

# Phần I — Phía sở hữu và biểu diễn quan hệ

## 2. Khóa ngoại nằm ở đâu?

Với mô hình đơn hàng:

```text
purchase_orders
+----+------------+
| id | order_code |
+----+------------+
| 10 | PO-10      |
+----+------------+

order_lines
+----+----------+-------+
| id | order_id | sku   |
+----+----------+-------+
| 90 | 10       | SKU-A |
| 91 | 10       | SKU-B |
+----+----------+-------+
```

Trong mapping bidirectional `@OneToMany(mappedBy = "order")` + `@ManyToOne`, cột `order_lines.order_id` do property `OrderLine.order` quản lý.

```text
PurchaseOrder.lines            OrderLine.order
    inverse side                  owning side
         |                            |
         +------- cùng quan hệ --------+
                                      |
                                      v
                              order_lines.order_id
```

### 2.1. `mappedBy` trỏ tới property Java

```java
@OneToMany(mappedBy = "order")
```

`"order"` là tên property `OrderLine.order`, **không phải** tên cột `order_id`.

Sai:

```java
@OneToMany(mappedBy = "order_id")
```

nếu child không có property Java tên `order_id`.

### 2.2. Phía collection không luôn là owner

Nhiều người nghĩ `PurchaseOrder` là parent nên luôn là owning side của mọi association. Trong mapping bidirectional này, điều đó sai.

**Aggregate root theo domain design** và **owning side theo JPA mapping** là hai khái niệm khác nhau.

Parent có thể là nơi expose domain methods như `addLine`, nhưng khóa ngoại vẫn được đồng bộ từ `OrderLine.order`.

### 2.3. Cascade không đổi owner

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL
)
```

Dù đặt cascade trên `PurchaseOrder.lines`, property điều khiển FK vẫn là `OrderLine.order`.

---

## 3. Tại sao chỉ sửa phía inverse là nguy hiểm?

Sai:

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class, orderId
);

OrderLine line = em.find(
    OrderLine.class, lineId
);

order.getLines().add(line);

// Quên: line.setOrder(order)
```

Trong cùng Java object graph, collection đã có `line`. Nhưng `line.order` vẫn có thể trỏ tới parent cũ hoặc là `null`.

Không được suy rằng JPA sẽ tự sửa owning property chỉ vì collection inverse được thêm phần tử.

### 3.1. Phía nào thắng trong database?

Với bidirectional association, portable application phải **duy trì nhất quán hai phía**. Trong điều kiện graph không nhất quán, provider có thể xử lý chi tiết khác nhau hoặc phát lỗi. Test không nên xây business behavior dựa trên trạng thái không nhất quán.

### 3.2. Test chỉ nhìn Java collection sẽ xanh giả

```java
assertEquals(2, order.getLines().size());
```

Assertion này chỉ chứng minh cấu trúc Java hiện tại có hai phần tử.

Để kiểm tra FK, cần:

1. Đồng bộ và commit transaction.
2. Đóng hoặc bỏ persistence context cũ.
3. Mở EntityManager khác.
4. Đọc lại `OrderLine.order.id` hoặc truy vấn `order_id` thực tế.
5. Assert liên kết đã commit.

### 3.3. Helper giữ hai phía đồng bộ

```java
public void addLine(OrderLine line) {
    if (line == null) {
        throw new IllegalArgumentException(
            "line is required"
        );
    }

    if (line.getOrder() != null) {
        throw new IllegalStateException(
            "Line already belongs to an order"
        );
    }

    lines.add(line);
    line.setOrder(this);
}
```

```java
public void removeLine(OrderLine line) {
    if (lines.remove(line)) {
        line.setOrder(null);
    }
}
```

Một **domain method** kiểm soát cả collection và owning property sẽ đáng tin cậy hơn việc mở public setters/collections cho mọi caller sửa tùy ý.

---

## 4. Khác biệt với unidirectional @OneToMany

JPA có thể map unidirectional one-to-many:

```java
@OneToMany
@JoinColumn(name = "order_id")
private List<OrderLine> lines;
```

Trong mapping này, **không có `mappedBy`**. Cách mô tả ownership và SQL updates khác bidirectional association.

Nếu unidirectional one-to-many không có `@JoinColumn`, provider có thể sử dụng join table theo mapping defaults.

### 4.1. Không áp kết luận cứng cho mọi @OneToMany

Câu “many side luôn là owner” chỉ đúng cho **bidirectional many-to-one/one-to-many** theo semantics tương ứng. Unidirectional mappings có cách sở hữu association khác.

### 4.2. Test đúng DDL thực tế

Khi chuyển từ bidirectional sang unidirectional mapping, cần kiểm tra:

- Có join table hay FK?
- Nullable và foreign-key constraints.
- SQL UPDATEs/DELETEs provider sinh.
- Orphan deletion.
- Các thao tác add/remove.
- Migration schema.

Không chỉ so sánh số phần tử trong Java collection.

---

## 5. @OneToOne và phía sở hữu

Một bidirectional one-to-one:

```java
@Entity
class Customer {

    @OneToOne(
        mappedBy = "customer",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private CustomerProfile profile;
}
```

```java
@Entity
class CustomerProfile {

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(
        name = "customer_id",
        nullable = false,
        unique = true
    )
    private Customer customer;
}
```

`CustomerProfile.customer` là owning side do `@JoinColumn`; `Customer.profile` là inverse side do `mappedBy`.

### 5.1. Thay một profile

Khi business muốn xóa profile cũ và tạo profile mới, helper phải xử lý cả hai phía. Với `orphanRemoval = true`, profile cũ có thể được schedule DELETE, profile mới có thể được persist qua cascade.

### 5.2. Unique và thứ tự SQL

Nếu database có `UNIQUE(customer_id)`, việc đổi profile cũ sang mới trong cùng flush có thể gặp constraint violation tùy thời điểm DELETE/INSERT và provider ordering.

Không mặc định orphanRemoval bảo đảm DELETE cũ chạy trước INSERT mới trong mọi trường hợp. Test trên DB/driver mục tiêu và cân nhắc operation sequencing phù hợp.

### 5.3. @MapsId/shared primary key

Với one-to-one dùng shared primary key, `@MapsId` làm identity của dependent entity gắn với parent. Các thao tác replace/reparent có constraints riêng; không áp dụng máy móc pattern của một FK nullable.

---

# Phần II — Mapping mẫu có thể kiểm thử

## 6. Thiết kế entity PurchaseOrder

Ví dụ dùng Java 17+, Jakarta Persistence 3.x, PostgreSQL và Hibernate cho bài test tích hợp. Quy tắc chính về owning side/cascade/orphanRemoval đến từ JPA; cấu hình test cụ thể có thể thay đổi theo provider.

```java
package com.example.jpa.relationship;

import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code",
            nullable = false,
            unique = true)
    private String orderCode;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderCode) {
        if (orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException(
                "orderCode is required"
            );
        }
        this.orderCode = orderCode;
    }

    public Long getId() {
        return id;
    }

    public String getOrderCode() {
        return orderCode;
    }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(OrderLine line) {
        if (line == null) {
            throw new IllegalArgumentException(
                "line is required"
            );
        }

        if (line.getOrder() != null) {
            throw new IllegalStateException(
                "Line already belongs to an order"
            );
        }

        lines.add(line);
        line.setOrder(this);
    }

    public void removeLine(OrderLine line) {
        if (lines.remove(line)) {
            line.setOrder(null);
        }
    }
}
```

### 6.1. Vì sao không expose collection để caller tự sửa?

```java
Collections.unmodifiableList(lines)
```

giúp caller không làm:

```java
order.getLines().clear();
```

mà bỏ qua việc cập nhật `OrderLine.order`.

Domain methods cung cấp một cổng duy nhất để giữ invariant hai phía.

### 6.2. Không thêm setter orderCode tùy tiện

Với ví dụ này, order code là identity nghiệp vụ ổn định. Nếu nghiệp vụ cho phép sửa, cần domain method và constraint/test tương ứng.

### 6.3. CascadeType.ALL đang làm gì?

`ALL` gồm các cascade types do Jakarta Persistence hỗ trợ như `PERSIST`, `MERGE`, `REMOVE`, `REFRESH`, `DETACH`.

Đặt `ALL` ở đây vì `OrderLine` có vòng đời phụ thuộc `PurchaseOrder`. **Không dùng `ALL` mặc định cho mọi quan hệ**, đặc biệt quan hệ tới dữ liệu dùng chung.

---

## 7. Thiết kế entity OrderLine

```java
package com.example.jpa.relationship;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(
        name = "order_id",
        nullable = false
    )
    private PurchaseOrder order;

    @Column(nullable = false)
    private String sku;

    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    protected OrderLine() {
    }

    public OrderLine(
            String sku,
            BigDecimal unitPrice) {

        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                "sku is required"
            );
        }

        if (unitPrice == null ||
                unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "unitPrice must be non-negative"
            );
        }

        this.sku = sku;
        this.unitPrice = unitPrice;
    }

    public Long getId() {
        return id;
    }

    public PurchaseOrder getOrder() {
        return order;
    }

    public String getSku() {
        return sku;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    // Package-private: chỉ aggregate method được
    // chủ động thiết lập association.
    void setOrder(PurchaseOrder order) {
        this.order = order;
    }
}
```

### 7.1. Owning side

`OrderLine.order` là phía sở hữu vì nó map `@ManyToOne` với `@JoinColumn`.

### 7.2. Foreign key không null

```java
optional = false
@JoinColumn(nullable = false)
```

và database `NOT NULL` khiến `OrderLine` không được tồn tại lâu dài mà không có `PurchaseOrder`.

Nhưng `@JoinColumn(nullable=false)` chỉ là metadata và không chứng minh production schema có cột `NOT NULL`. Cần kiểm thử DDL/migration thực tế.

### 7.3. Không dùng `CascadeType.REMOVE` ở ManyToOne tùy tiện

Nếu đặt REMOVE cascade ở phía child:

```java
@ManyToOne(cascade = CascadeType.REMOVE)
private PurchaseOrder order;
```

xóa một line có thể lan truyền xóa cả parent — thường **sai nghiệp vụ**. Cascade hướng theo quan hệ mà nó được khai báo, không tự suy ra parent/child semantics.

### 7.4. Lưu ý equals/hashCode

Ví dụ không override `equals/hashCode`, nên `List.remove(line)` trong cùng persistence context dựa trên object identity. Trong dự án thực:

- Nếu dùng `Set`, `equals/hashCode` ảnh hưởng membership/remove.
- Không tạo hash từ mutable/generated ID theo cách khiến phần tử đổi hash sau `persist()`.
- Không đưa lazy associations hoặc entire collection vào `equals/hashCode`.
- Nếu business-key equality, key phải có semantics ổn định.

Các lỗi `remove()` không tác động collection có thể đến từ `equals/hashCode`, không phải orphanRemoval.

---

## 8. DDL tương ứng

Ví dụ PostgreSQL:

```sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT
       AS IDENTITY PRIMARY KEY,
    order_code VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    id BIGINT GENERATED BY DEFAULT
       AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(255) NOT NULL,
    unit_price NUMERIC(19,2) NOT NULL,
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_orders(id)
);
```

Không có `ON DELETE CASCADE` trong ví dụ để các test nhìn rõ JPA cascade remove/orphan deletion. Một production schema có thể cần phương án khác, nhưng phải test behavior cụ thể.

### 8.1. `ON DELETE CASCADE` là DB behavior

Nếu thêm:

```sql
FOREIGN KEY (order_id)
REFERENCES purchase_orders(id)
ON DELETE CASCADE
```

database có thể xóa lines khi parent row bị DELETE, kể cả không có JPA REMOVE cascade.

Điều này **không tương đương** JPA cascade về entity callbacks và persistence context.

### 8.2. Test phải xác định nguồn xóa

Nếu mục tiêu là kiểm tra `CascadeType.REMOVE`, database `ON DELETE CASCADE` có thể khiến bài test “parent delete → children biến mất” xanh dù ORM không phát child DELETE.

Do đó cần hiểu DDL, và nếu muốn kiểm tra SQL do provider phát, dùng logging/JDBC instrumentation trong một provider-specific test riêng.

---

# Phần III — Cấu hình integration test

## 9. Vì sao cần database thực?

Unit test không khởi tạo EntityManager:

```java
PurchaseOrder order = new PurchaseOrder("PO-1");
OrderLine line = new OrderLine(
    "SKU-A",
    new BigDecimal("10.00")
);

order.addLine(line);

assertSame(order, line.getOrder());
assertEquals(1, order.getLines().size());
```

Nó rất hữu ích để kiểm tra **domain helper**. Nhưng chưa kiểm tra:

- `mappedBy` đúng property.
- FK được ghi đúng.
- Cascade PERSIST có hoạt động trong JPA provider.
- Orphan row có bị xóa sau flush/commit.
- SQL constraint có cho phép thay đổi đó.
- Transaction rollback/commit.
- Dữ liệu có đúng khi mở context mới.

Cần integration test với `EntityManagerFactory`, driver và database tương ứng.

### 9.1. Không chỉ kiểm tra `em.contains(line)`

`contains` cho biết instance có managed trong context hay không. Nó không chứng minh row đã commit hoặc khóa ngoại đã đúng.

### 9.2. Không chỉ kiểm tra `getLines().size()`

Collection trong L1 có thể chứa phần tử dù owning FK chưa đồng bộ; sau commit cần đọc lại.

### 9.3. Hai loại test bổ sung nhau

| Test | Mục đích |
| --- | --- |
| Unit test domain helpers | Hai phía Java được đồng bộ |
| JPA integration test | Provider ghi quan hệ, cascade, orphanRemoval đúng |
| Schema migration integration test | FK/NOT NULL/UNIQUE thực sự tồn tại |
| SQL instrumentation test | Quan sát loại và thứ tự SQL nếu cần tối ưu |
| API/service test | Business transaction, authorization và lỗi HTTP |

---

## 10. Testcontainers + PostgreSQL + JUnit 5

Một setup minh họa:

```java
package com.example.jpa.relationship;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import java.util.HashMap;
import java.util.Map;

@Testcontainers
class RelationshipMappingIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    static EntityManagerFactory emf;

    @BeforeAll
    static void createFactory() {
        Map<String, Object> properties = new HashMap<>();

        properties.put(
            "jakarta.persistence.jdbc.driver",
            "org.postgresql.Driver"
        );
        properties.put(
            "jakarta.persistence.jdbc.url",
            postgres.getJdbcUrl()
        );
        properties.put(
            "jakarta.persistence.jdbc.user",
            postgres.getUsername()
        );
        properties.put(
            "jakarta.persistence.jdbc.password",
            postgres.getPassword()
        );

        // CHỈ cho test database tách biệt.
        properties.put(
            "hibernate.hbm2ddl.auto",
            "create-drop"
        );

        emf = Persistence.createEntityManagerFactory(
            "relationship-it",
            properties
        );
    }

    @AfterAll
    static void closeFactory() {
        if (emf != null) {
            emf.close();
        }
    }

    // Các @Test và helper nằm trong cùng class.
}
```

Ví dụ này phụ thuộc Hibernate, pgJDBC, JUnit 5 và Testcontainers PostgreSQL/JUnit Jupiter. Các versions nên được quản lý bằng BOM/dependency management của project.

### 10.1. Persistence unit thử nghiệm

`src/test/resources/META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">

    <persistence-unit
        name="relationship-it"
        transaction-type="RESOURCE_LOCAL">

        <provider>
            org.hibernate.jpa.HibernatePersistenceProvider
        </provider>

        <class>
            com.example.jpa.relationship.PurchaseOrder
        </class>
        <class>
            com.example.jpa.relationship.OrderLine
        </class>

        <exclude-unlisted-classes>true</exclude-unlisted-classes>
    </persistence-unit>
</persistence>
```

Trong ví dụ, các Java class giữ nguyên fully qualified package names. Cần bảo đảm `persistence.xml` ở đúng test resources và driver/provider dependencies tồn tại.

### 10.2. `create-drop` chỉ dành cho test cô lập

`hibernate.hbm2ddl.auto=create-drop` dễ khởi tạo schema test, **không phải chiến lược production migrations**.

Đối với test xác minh DDL production, thay bằng migrations của Flyway/Liquibase/SQL tương ứng và tránh để Hibernate tự tạo schema che mất lỗi migration.

### 10.3. Testcontainers không có nghĩa mọi môi trường đều giống production

Container Postgres giúp sát semantics PostgreSQL hơn H2. Tuy nhiên vẫn cần xem version, collation, extensions, constraints, isolation và migration thực tế.

---

## 11. Helper transaction và fixture có commit thật

Trong cùng test class:

```java
private static <T> T inTransaction(
        java.util.function.Function<EntityManager, T> work) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        T value = work.apply(em);

        // Lỗi DML có thể xuất hiện ở flush.
        em.flush();

        // Có thể lỗi tại commit, không chỉ flush.
        em.getTransaction().commit();

        return value;

    } catch (RuntimeException ex) {
        try {
            if (em.getTransaction().isActive()) {
                em.getTransaction().rollback();
            }
        } catch (RuntimeException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }

        throw ex;

    } finally {
        em.close();
    }
}
```

Helper tạo fixture:

```java
private static Long newOrderWithTwoLines() {
    String code =
        "PO-" + java.util.UUID.randomUUID();

    return inTransaction(em -> {
        PurchaseOrder order = new PurchaseOrder(code);

        order.addLine(new OrderLine(
            "SKU-A",
            new BigDecimal("12.50")
        ));
        order.addLine(new OrderLine(
            "SKU-B",
            new BigDecimal("7.00")
        ));

        em.persist(order);

        return order.getId();
    });
}
```

Với `GenerationType.IDENTITY`, ID thường được cấp khi INSERT cần thiết; trong stack này `order.getId()` có thể sẵn trước flush. Để tránh phụ thuộc timing trong fixture khác, có thể gọi `em.flush()` trước khi lấy ID.

### 11.1. Tại sao fixture phải commit?

Nếu fixture còn trong một test transaction rồi test đọc trong cùng persistence context, kết quả có thể đến từ L1. Test orphan deletion cần kiểm tra đối tượng **đã persistent** và trạng thái DB đã commit.

### 11.2. Mỗi lần test dùng khóa nghiệp vụ riêng

`UUID` giảm collision giữa tests chạy song song. Không dùng cùng `"PO-1"` trong nhiều tests mà chưa có chính sách cleanup.

### 11.3. Không share EntityManager giữa threads/tests

`EntityManager` không thread-safe. Mỗi attempt/transaction dùng context được quản lý thích hợp. `EntityManagerFactory` có thể được share và cần được close đúng lifecycle.

---

# Phần IV — Bộ kiểm thử phía sở hữu

## 12. Test domain helper đồng bộ hai phía

Một unit test:

```java
@Test
void addLineUpdatesBothJavaSides() {
    PurchaseOrder order = new PurchaseOrder("PO-TEST");

    OrderLine line = new OrderLine(
        "SKU-X",
        new BigDecimal("5.00")
    );

    order.addLine(line);

    assertSame(order, line.getOrder());
    assertTrue(order.getLines().contains(line));
}
```

Điểm đang kiểm tra: `addLine` vừa cập nhật inverse collection vừa set owning property.

### 12.1. Test remove cũng phải kiểm tra cả hai phía

```java
@Test
void removeLineUnlinksBothJavaSides() {
    PurchaseOrder order = new PurchaseOrder("PO-TEST");

    OrderLine line = new OrderLine(
        "SKU-X",
        new BigDecimal("5.00")
    );

    order.addLine(line);
    order.removeLine(line);

    assertFalse(order.getLines().contains(line));
    assertNull(line.getOrder());
}
```

Đây là unit test quan hệ Java; chưa kiểm tra DB DELETE.

### 12.2. Không kiểm tra một phía rồi mặc định phía kia đúng

Nếu helper chỉ gọi `lines.remove(line)` mà không set `line.order=null`, assertion collection có thể xanh dù graph mâu thuẫn.

---

## 13. Test owning side được ghi vào database

Tạo parent với hai children, commit, rồi reload:

```java
@Test
void persistCascadesAndWritesOwningForeignKey() {
    Long orderId = newOrderWithTwoLines();

    EntityManager verify = emf.createEntityManager();

    try {
        PurchaseOrder saved =
            verify.find(PurchaseOrder.class, orderId);

        assertNotNull(saved);
        assertEquals(2, saved.getLines().size());

        for (OrderLine line : saved.getLines()) {
            assertNotNull(line.getId());
            assertEquals(
                orderId,
                line.getOrder().getId()
            );
        }
    } finally {
        verify.close();
    }
}
```

### 13.1. Vì sao test có ý nghĩa?

`newOrderWithTwoLines()` chỉ gọi:

```java
em.persist(order);
```

không gọi `em.persist(line)` riêng. Khi hai lines tồn tại sau commit, test đang kiểm tra `CascadeType.PERSIST` trong `CascadeType.ALL`.

Khi `line.getOrder().getId()` đúng, test cũng đang quan sát association qua owning property.

### 13.2. Cần query raw FK nếu mục tiêu là cột cụ thể

Một test có thể đọc native SQL:

```java
@SuppressWarnings("unchecked")
List<Object[]> rows = verify.createNativeQuery(
    """
    SELECT id, order_id
    FROM order_lines
    WHERE order_id = ?
    """
)
.setParameter(1, orderId)
.getResultList();

assertEquals(2, rows.size());
```

Native query dùng để xác minh schema/FK mapping thực, không thay JPA test. Với PostgreSQL, ID columns thường được JDBC trả dưới kiểu số phù hợp; đừng cast mù quáng `Object[]` phần tử thành `Long` nếu driver có thể trả `Number` khác.

### 13.3. Fresh context ngăn L1 che lỗi

Một context mới sau commit không giữ nguyên collection Java của fixture. Kết quả được tải lại từ database.

---

## 14. Test thay đổi owning association

Để kiểm tra owning side độc lập, ta có thể tạo một test mapping **không bật orphanRemoval** hoặc thao tác trên association khác khi thực hiện reparenting. Lý do: với `orphanRemoval=true`, chuyển child giữa parents là một bài toán **lifecycle** khác, không chỉ đơn thuần cập nhật FK.

Ví dụ mapping riêng dành cho một child có thể chuyển chủ:

```java
@Entity
class Task {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "project_id")
    private Project project;

    public void assignProject(Project project) {
        this.project = project;
    }
}
```

```java
@Entity
class Project {

    @Id
    private Long id;

    @OneToMany(mappedBy = "project")
    private List<Task> tasks = new ArrayList<>();
}
```

Một test kiểm tra:

1. Tạo hai projects và một task thuộc project A.
2. Commit.
3. Trong transaction mới, gán owning property `task.assignProject(projectB)`.
4. Đồng bộ hai inverse collections bằng helper thích hợp.
5. Commit.
6. Mở EntityManager mới, xác nhận FK `task.project_id` trỏ tới B.
7. Xác nhận A/B collections khi đọc lại đúng.

### 14.1. Không dùng orphanRemoval để minh họa chuyển child

Nếu child đã bị xem là orphan khi remove khỏi A, JPA portable semantics không bảo đảm bạn có thể gắn ngay child đó vào B rồi mong provider chuyển FK thay vì DELETE.

Tách mô hình **dependent aggregate children** khỏi mô hình **movable associations** giúp test có hợp đồng rõ ràng.

---

## 15. Negative test: chỉ sửa phía inverse

Với `Task`/`Project` không có orphanRemoval, có thể tạo một negative test mang tính minh họa:

```java
// Sau khi project A, project B và task thuộc A
// đã được commit, mở transaction mới.

Project b = em.find(Project.class, bId);
Task task = em.find(Task.class, taskId);

// Cố ý tạo Java graph không nhất quán:
b.getTasks().add(task);

// Không gọi task.assignProject(b).
```

Sau commit, nếu JPA provider không tự cập nhật owning property, task vẫn thuộc A khi tải lại từ DB. Quan trọng hơn, **ứng dụng portable không được dựa vào hành vi provider với graph hai chiều cố ý không nhất quán**.

### 15.1. Điều phải khẳng định

- Test này là **negative/diagnostic test**, không phải domain workflow hợp lệ.
- Đừng thiết kế production logic theo expectation về behavior trong trạng thái không nhất quán.
- Positive test luôn cập nhật cả hai phía.
- Nếu muốn bảo vệ contract, tập trung test public domain helpers không cho caller sửa inverse collection trực tiếp.

### 15.2. Có thể dùng unit test để ngăn sai lầm này

Expose collection dạng unmodifiable và giới hạn setter owning side, như model `PurchaseOrder`/`OrderLine`, để caller không dễ tạo inconsistency.

---

# Phần V — Cascade PERSIST, MERGE, REMOVE

## 16. Kiểm thử CascadeType.PERSIST

Mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.PERSIST
)
```

Test tạo parent mới + children mới, chỉ gọi:

```java
em.persist(parent);
```

Sau commit, kiểm tra children tồn tại và FK đúng.

### 16.1. Điều không nên làm

Nếu test gọi:

```java
em.persist(parent);
em.persist(child);
```

thì child vẫn có thể được lưu dù thiếu PERSIST cascade. Bài test đó **không chứng minh PERSIST cascade**.

### 16.2. Negative test khi không có PERSIST cascade

Trong một model khác:

```java
@OneToMany(mappedBy = "parent")
private List<Child> children;
```

Khi chỉ persist parent, children mới không tự được persist bởi association này. Tùy owning FK và các thao tác khác, có thể không xuất hiện rows mới hoặc provider ném lỗi về transient reference/unsaved instance.

Đừng assert một exception class cụ thể nếu không cố định provider và mapping; hãy assert contract dữ liệu cuối và cause phù hợp.

---

## 17. Kiểm thử CascadeType.MERGE

Với graph detached:

```java
PurchaseOrder detached = ...;
```

`em.merge(detached)` có thể lan truyền merge tới children khi association có `CascadeType.MERGE`.

### 17.1. Merge trả managed instance mới

```java
PurchaseOrder managed =
    em.merge(detached);
```

`managed` là kết quả cần dùng trong context hiện tại. `detached` không tự trở thành managed chỉ vì gọi merge.

### 17.2. Test không được che hành vi bằng persist riêng

Nếu muốn kiểm tra cascade MERGE, tạo fixture đã commit, đóng context, sửa detached graph một cách hợp lệ, mở transaction mới gọi **chỉ** `em.merge(detached)`, commit và đọc lại bằng context khác.

### 17.3. Merge detached graph có rủi ro

- Collection thiếu child có thể bị hiểu là đã bỏ child, tùy graph/state và provider.
- Với orphanRemoval, merge graph thiếu phần tử có thể dẫn tới DELETE theo semantics được áp dụng.
- Lazy collection chưa tải không đồng nghĩa người dùng có ý định xóa toàn bộ.
- Không merge raw DTO từ client thành entity graph mà không kiểm soát ownership, version và authorization.

### 17.4. Test update đơn giản

Một biến thể model có setter domain cho `OrderLine.unitPrice` có thể test thay đổi giá của detached child, merge parent, commit, rồi reload giá.

Quan sát cả parent và child từ context mới; không chỉ assert field của detached object.

---

## 18. Kiểm thử CascadeType.REMOVE

Trong mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE
)
```

`em.remove(order)` lan truyền remove tới lines thuộc association được cascade.

Với model có `CascadeType.ALL`:

```java
@Test
void removingParentDeletesDependentLines() {
    Long orderId = newOrderWithTwoLines();

    inTransaction(em -> {
        PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

        em.remove(order);
        return null;
    });

    EntityManager verify = emf.createEntityManager();

    try {
        assertNull(
            verify.find(PurchaseOrder.class, orderId)
        );

        Number count = (Number) verify
            .createNativeQuery(
                """
                SELECT COUNT(*)
                FROM order_lines
                WHERE order_id = ?
                """
            )
            .setParameter(1, orderId)
            .getSingleResult();

        assertEquals(0L, count.longValue());
    } finally {
        verify.close();
    }
}
```

### 18.1. Test này kiểm tra lifecycle cascade

Parent bị xóa trực tiếp. Đây là trường hợp `CascadeType.REMOVE` có thể phát huy vai trò.

### 18.2. OrphanRemoval cũng có semantics khi parent bị remove

Trong trường hợp one-to-many/one-to-one có `orphanRemoval = true`, remove operation có thể được cascade tới target theo JPA semantics. Vì vậy với mapping có **cả** `CascadeType.REMOVE` và `orphanRemoval=true`, một test chỉ xóa parent rồi thấy child biến mất không **tách biệt** được đóng góp của từng cơ chế.

Muốn test độc lập từng mechanism, dùng những mapping/fixtures khác nhau:

- Cascade REMOVE bật, orphanRemoval tắt.
- Cascade REMOVE tắt, orphanRemoval bật.
- Cả hai tắt.
- Các database FK behaviors được kiểm soát.

### 18.3. Không đặt REMOVE cascade lên shared entity

Một `PurchaseOrder` tham chiếu `Customer`, `Product` hoặc `Category` dùng chung; xóa order **không được xóa customer/product** nếu các thực thể đó có vòng đời độc lập.

Cascade REMOVE nguy hiểm đặc biệt trên `@ManyToMany` nơi target thường được nhiều parents chia sẻ.

---

## 19. CascadeType.ALL và phạm vi vòng đời

`ALL` thường phù hợp với entity con thật sự thuộc aggregate, ví dụ line items chỉ tồn tại như một phần của order.

Nó có thể không phù hợp với:

- `Order.customer`: customer tồn tại độc lập.
- `OrderLine.product`: product được nhiều order lines tham chiếu.
- `Employee.department`: department có vòng đời riêng.
- Many-to-many shared tags/categories.
- Reference/master data.

### 19.1. Test business ownership trước khi chọn cascade

Câu hỏi quan trọng:

> Nếu parent bị xóa, target có nên bị xóa khỏi database không?

Nếu câu trả lời là **không**, phải cẩn thận với REMOVE/ALL và orphanRemoval.

### 19.2. Cascade là directional

Nếu đặt `cascade=ALL` ở `Order.lines`, không có nghĩa thao tác `em.persist(line)` sẽ tự persist `order` khi phía `line.order` không cấu hình PERSIST cascade.

Không dựa vào ý niệm “quan hệ có cascade ở đâu đó” để suy ra nó truyền hai chiều.

---

# Phần VI — orphanRemoval

## 20. Hợp đồng cơ bản của orphanRemoval

Trong mô hình:

```java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.ALL,
    orphanRemoval = true
)
private List<OrderLine> lines;
```

Khi một line **đã được persist** bị tách khỏi association trong một context hợp lệ, nó có thể được đánh dấu để xóa theo JPA orphan-removal semantics khi provider đồng bộ.

### 20.1. Xóa khỏi association khác xóa parent

```java
order.removeLine(line);
```

Parent vẫn tồn tại, child được tách ra và có thể bị DELETE.

Trong khi:

```java
em.remove(order);
```

Parent bị xóa, children có thể bị xóa qua cascade/lifecycle semantics.

### 20.2. orphanRemoval chỉ dành cho quan hệ phù hợp

JPA hỗ trợ orphan removal cho `@OneToOne` và `@OneToMany`.

Không cấu hình `orphanRemoval` trên `@ManyToMany` hoặc `@ManyToOne` vì chúng không có thuộc tính này trong Jakarta Persistence.

### 20.3. Đừng suy rằng setting này là database FK ON DELETE

`orphanRemoval=true` thuộc ORM lifecycle; database `ON DELETE CASCADE` là constraint action khi parent row bị xóa.

Xóa một child khỏi collection mà parent vẫn tồn tại không phải tình huống DB `ON DELETE CASCADE` trực tiếp xử lý.

---

## 21. Test xóa orphan đã tồn tại

Test này đặc biệt quan trọng: child đã được persist và commit ở transaction trước.

```java
@Test
void removingPersistedChildDeletesOnlyThatChild() {
    Long orderId = newOrderWithTwoLines();

    Long removedLineId = inTransaction(em -> {
        PurchaseOrder order =
            em.find(PurchaseOrder.class, orderId);

        OrderLine target = order.getLines().stream()
            .filter(line -> "SKU-A".equals(line.getSku()))
            .findFirst()
            .orElseThrow();

        Long id = target.getId();

        order.removeLine(target);

        assertFalse(
            order.getLines().contains(target)
        );
        assertNull(target.getOrder());

        return id;
    });

    EntityManager verify = emf.createEntityManager();

    try {
        assertNull(
            verify.find(OrderLine.class, removedLineId)
        );

        PurchaseOrder saved =
            verify.find(PurchaseOrder.class, orderId);

        assertNotNull(saved);
        assertEquals(1, saved.getLines().size());
        assertEquals(
            "SKU-B",
            saved.getLines().get(0).getSku()
        );
    } finally {
        verify.close();
    }
}
```

### 21.1. Điều bài test chứng minh

- Parent row vẫn tồn tại.
- Child đã bỏ khỏi quan hệ không còn trong DB.
- Child còn lại vẫn tồn tại.
- Database state được xác minh **sau commit** qua EntityManager mới.

### 21.2. Vì sao test này tách biệt với CascadeType.REMOVE?

Trong transaction này **không gọi `em.remove(order)`**. Chỉ tách child khỏi association.

Do đó nếu child bị DELETE, đó là hành vi phù hợp với orphanRemoval chứ không phải thao tác cascade remove do xóa parent.

### 21.3. Không assert DELETE SQL xảy ra ngay tại removeLine

```java
order.removeLine(target);
```

chủ yếu cập nhật state trong persistence context. SQL DELETE thường xuất hiện khi flush/commit; thời điểm cụ thể phụ thuộc provider.

---

## 22. orphanRemoval=false có khác gì?

Nếu mapping:

```java
@OneToMany(
    mappedBy = "order",
    orphanRemoval = false
)
private List<OrderLine> lines;
```

thì xóa phần tử khỏi collection không có nghĩa ORM phải DELETE row đó.

Nếu helper đồng thời gọi `line.setOrder(null)`:

- Với FK **nullable**, provider có thể UPDATE `order_id` thành NULL khi owning property được đồng bộ.
- Với FK `NOT NULL`, database có thể từ chối UPDATE.
- Nếu chỉ sửa inverse collection mà không sửa owning property, database có thể vẫn giữ liên kết cũ.

### 22.1. Test cần phù hợp model

Không dùng mapping `nullable=false` rồi kỳ vọng `orphanRemoval=false` biến child thành unattached row `order_id=NULL` hợp lệ.

Nếu nghiệp vụ cho phép child tồn tại độc lập, FK và domain invariants phải được thiết kế theo điều đó.

### 22.2. OrphanRemoval=true giải quyết điều gì?

Nó giúp mô hình hóa **dependent lifecycle**: child không có ý nghĩa tồn tại độc lập khỏi parent.

Không bật chỉ để tránh lỗi NOT NULL mà chưa quyết định chính sách xóa dữ liệu.

---

## 23. Xóa child mới chưa persist

Theo JPA semantics, orphanRemoval không yêu cầu remove operation đối với target vẫn ở trạng thái **new**, **detached** hoặc **removed** theo các trường hợp được đặc tả.

Ví dụ:

```java
PurchaseOrder order = new PurchaseOrder("PO-TEMP");

OrderLine line = new OrderLine(
    "SKU-TEMP",
    new BigDecimal("1.00")
);

order.addLine(line);
order.removeLine(line);

em.persist(order);
```

Nếu line chỉ là object mới và đã bị bỏ khỏi collection **trước persist**, thường sẽ không có row nào của line cần DELETE.

### 23.1. Test không nhầm new object với managed persistent orphan

Một unit test tạo `new OrderLine` rồi remove khỏi collection và assert không có row không đủ để chứng minh orphan removal hoạt động.

**Test bắt buộc cần child đã persistent** để kiểm chứng DELETE khi orphan được tạo.

---

## 24. Không reparent orphan vừa bị tách khi orphanRemoval=true

Một pattern nguy hiểm:

```java
orderA.removeLine(line);
orderB.addLine(line);
```

Với `orphanRemoval=true`, child có thể đã được xem là orphan khi tách khỏi A. Portable applications **không nên gán lại một entity đã bị orphan sang relationship khác** hoặc cố persist lại nó rồi dựa vào SQL ordering cụ thể.

### 24.1. Vì sao nguy hiểm?

- Provider có thể schedule DELETE cho line.
- FK có thể được cập nhật rồi DELETE, hoặc gặp constraint conflict.
- In-memory graph có thể trông như child đã chuyển sang B.
- Database state sau flush/commit có thể không như dự đoán hoặc bị lỗi.
- Behavior có thể khác giữa providers/versions.

### 24.2. Nếu business cần chuyển child

Có ba lựa chọn thiết kế:

1. **Không dùng orphanRemoval** cho association mà child có thể di chuyển, và quản lý reassignment rõ.
2. Diễn đạt move bằng một workflow khác có lifecycle được kiểm soát, không gắn lại orphan đã schedule delete trong cùng attempt.
3. Tạo một child mới ở parent B và xóa child cũ ở A nếu business semantics là copy/move data, không phải reuse cùng persistent identity.

Chọn theo domain, không chỉ vì dễ làm Hibernate chạy qua một test.

---

## 25. `clear()` và thay cả collection

Giả sử:

```java
order.getLines().clear();
```

Nếu mapping cho phép sửa collection trực tiếp và `orphanRemoval=true`, provider có thể xóa toàn bộ managed children khi đồng bộ association.

Nhưng pattern này có nguy cơ lớn nếu collection chỉ được **partial load**, DTO thiếu dữ liệu hoặc request update chưa phân biệt “không gửi field” với “muốn xóa hết”.

### 25.1. Expose domain method rõ ý định

Thay vì public mutable collection, có thể cung cấp:

```java
public void removeAllLines() {
    for (OrderLine line : new ArrayList<>(lines)) {
        removeLine(line);
    }
}
```

Đoạn code minh họa nằm trong `PurchaseOrder` cùng domain helper.

### 25.2. Test bulk removal phải xác minh DB

Tạo 3 persisted children, gọi `removeAllLines` trong transaction mới, commit, reopen, assert zero children và parent còn tồn tại.

### 25.3. Thay reference collection không luôn vô hại

Một số provider như Hibernate quản lý collection wrapper đặc biệt. Thay toàn bộ instance collection bằng:

```java
this.lines = new ArrayList<>(newLines);
```

có thể làm orphan tracking hoặc lifecycle hoạt động khác, thậm chí gây provider exception trong một số mappings.

Ưu tiên mutate managed collection qua domain methods được kiểm soát và test với provider thực tế.

---

# Phần VII — Test flush, commit và rollback

## 26. Flush không phải commit

Một test có thể làm:

```java
em.getTransaction().begin();

PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

order.removeLine(target);

em.flush();
```

Sau flush, SQL DELETE có thể đã gửi nhưng transaction vẫn chưa commit.

### 26.1. Kiểm tra commit bằng context mới

```text
Tx A:
  load order
  remove line
  flush
  commit

EM B:
  find deleted line -> null
```

Test cần commit thành công rồi query ở EM B để khẳng định persisted state cuối.

### 26.2. L1 có thể tạo kết luận sai

Sau `em.remove(line)`, `em.find(lineId)` trong cùng context có thể trả giá trị phản ánh removed state, nhưng không chứng minh DB đã commit.

### 26.3. Rollback undo DB change, không tự undo Java object

```java
em.getTransaction().begin();

order.removeLine(line);
em.flush();
em.getTransaction().rollback();
```

Sau rollback, DB không giữ DELETE đã rollback. Nhưng Java `order.getLines()` có thể vẫn thiếu line; object graph cũ không tự rewind.

Cần reopen context để kiểm tra state committed.

---

## 27. Test rollback không xóa orphan vĩnh viễn

Kịch bản:

1. Tạo order có hai lines, commit.
2. Transaction A đọc order, remove một line.
3. `flush()`.
4. Rollback A.
5. EntityManager B mới đọc order.
6. Assert cả hai lines vẫn tồn tại trong DB.

Mục tiêu là phân biệt **SQL đã flush** với **DB đã commit**.

### 27.1. Tránh dùng cùng Java object để verify

Nếu assert:

```java
assertEquals(1, order.getLines().size());
```

ngay sau rollback, đó là state Java, không phải DB.

### 27.2. Khi rollback cũng thất bại

Nếu network/DB connection bị mất, transaction outcome có thể phức tạp. Integration test bình thường có thể assume rollback thành công nhưng production error handling phải xem commit ambiguity và idempotency.

---

## 28. Exception có thể xuất hiện ở persist, flush hoặc commit

Với generated identifiers và database constraints:

- `persist()` có thể gửi INSERT sớm để lấy ID.
- `flush()` thường là nơi SQL pending được thực thi.
- `commit()` có thể phát hiện lỗi từ delayed flush hoặc deferred constraints.

Không viết integration test kiểu:

```java
assertThrows(
    PersistenceException.class,
    () -> em.remove(order)
);
```

nếu thực tế lỗi chỉ xuất hiện khi flush/commit.

Bọc đúng unit of work:

```java
assertThrows(
    RuntimeException.class,
    () -> {
        em.remove(order);
        em.flush();
        em.getTransaction().commit();
    }
);
```

Sau đó **phân loại nguyên nhân cụ thể**, không chỉ assert một `RuntimeException` bất kỳ: network error hoặc missing table cũng có thể khiến test xanh giả.

### 28.1. Failed context phải được bỏ

Sau failed flush/commit, transaction có thể rollback-only hoặc aborted. Rollback, close EM và dùng context mới; không cố tiếp tục kiểm tra SQL trong transaction lỗi.

---

# Phần VIII — Test nhiều association types

## 29. One-to-one orphanRemoval

Một model:

```java
@Entity
class Account {

    @Id
    private Long id;

    @OneToOne(
        mappedBy = "account",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private AccountProfile profile;

    public void removeProfile() {
        if (profile != null) {
            profile.setAccount(null);
            profile = null;
        }
    }
}
```

```java
@Entity
class AccountProfile {

    @Id
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(
        name = "account_id",
        nullable = false,
        unique = true
    )
    private Account account;

    void setAccount(Account account) {
        this.account = account;
    }
}
```

Đây là sketch cần constructors/ID generation/DDL tương ứng trước khi chạy.

### 29.1. Test case

- Tạo Account + Profile, persist parent, commit.
- Reload xác nhận profile owning FK đúng.
- Transaction mới gọi `account.removeProfile()`.
- Flush/commit.
- Fresh EM: Account vẫn tồn tại, Profile đã bị xóa.
- Xác nhận không có Profile row trỏ tới account.

### 29.2. Không test remove bằng cách xóa Account

Nếu test chỉ `em.remove(account)`, không phân biệt orphan deletion do gỡ profile khỏi association.

### 29.3. Thử thay profile mới

Test này phải xử lý uniqueness/order-of-SQL constraints như đã nói; không giả định mọi mapping có thể replace old/new trong cùng flush.

---

## 30. Many-to-many: không dùng orphanRemoval

Ví dụ:

```java
@ManyToMany
@JoinTable(
    name = "article_tags",
    joinColumns = @JoinColumn(name = "article_id"),
    inverseJoinColumns = @JoinColumn(name = "tag_id")
)
private Set<Tag> tags = new HashSet<>();
```

Một tag có thể được nhiều articles tham chiếu.

### 30.1. Xóa association khác xóa target

```java
article.getTags().remove(tag);
```

thường có nghĩa xóa liên kết trong join table, **không** xóa row `tags`.

### 30.2. `orphanRemoval` không tồn tại ở @ManyToMany

Không tìm cách bật nó để tự động xóa Tag. Target có thể còn được sử dụng bởi articles khác.

### 30.3. Cascade REMOVE có thể nguy hiểm

Nếu một article bị xóa và REMOVE cascade sang tags, database có thể cố xóa các tags đang được articles khác dùng, gây FK errors hoặc mất dữ liệu dùng chung.

Test phải xác nhận xóa article **không xóa shared tag** khi domain không cho phép.

### 30.4. Owning side của many-to-many

Một phía sở hữu join table mapping, phía kia dùng `mappedBy`. Dù owner là parent hay child về domain, cần test join table rows sau commit và verify fresh context.

---

## 31. @ElementCollection không phải orphanRemoval của entity

Ví dụ:

```java
@ElementCollection
@CollectionTable(
    name = "order_notes",
    joinColumns = @JoinColumn(name = "order_id")
)
@Column(name = "note")
private List<String> notes = new ArrayList<>();
```

Các phần tử là **value objects/basic values**, không phải entity có `@Id` và lifecycle độc lập.

Xóa phần tử khỏi `@ElementCollection` có thể khiến provider cập nhật collection table, nhưng không phải cùng cơ chế `orphanRemoval` trên `@OneToMany` entity association.

### 31.1. Test theo loại mapping

Với value collection: verify row trong collection table.

Với dependent entity: verify entity row bị DELETE theo orphanRemoval.

Không áp dụng cùng assertion lifecycle cho hai loại.

---

# Phần IX — Spring Data JPA và test transaction

## 32. `@DataJpaTest` mặc định có transaction rollback

Trong Spring Boot:

```java
@DataJpaTest
class PurchaseOrderRepositoryTest {

    @Autowired
    TestEntityManager testEm;

    @Test
    void createsOrder() {
        PurchaseOrder order =
            new PurchaseOrder("PO-TEST");

        order.addLine(new OrderLine(
            "SKU-A",
            new BigDecimal("10.00")
        ));

        testEm.persistAndFlush(order);

        assertNotNull(order.getId());
    }
}
```

Đây là một test hợp lệ cho nhiều quan sát trong transaction nhưng **thường mặc định rollback khi test kết thúc**.

### 32.1. Rủi ro khi muốn kiểm tra committed state

`persistAndFlush()` **không phải commit**. Nếu chỉ query bằng cùng EntityManager hoặc cùng transaction, test có thể thấy dữ liệu mà transaction khác chưa thấy.

### 32.2. Nếu cần commit thực

Có thể:

- Dùng một test method không có outer test transaction, bao các operations trong `TransactionTemplate`.
- Dùng `TestTransaction` nếu test framework hỗ trợ và được cấu hình phù hợp.
- Dùng `@SpringBootTest` với transaction boundary do service thật quản lý.
- Dùng JPA RESOURCE_LOCAL test như phần trước.

Phải thiết kế cleanup/fixture isolation vì rows đã commit sẽ không bị test framework tự rollback.

### 32.3. Không để Spring transaction lồng vô tình

Nếu service `@Transactional` được gọi trong outer transactional test, nó có thể tham gia transaction của test thay vì commit độc lập. Điều này làm kiểm thử cascade/orphan persistence sau commit thiếu đáng tin.

### 32.4. TestEntityManager.clear() không commit

`clear()` chỉ detach entities. Nó giúp test buộc nạp lại trong cùng transaction ở một số tình huống, nhưng **không biến dữ liệu uncommitted thành committed state**.

---

## 33. TransactionTemplate tạo hai phases độc lập

Với Spring JPA:

```java
TransactionTemplate tx =
    new TransactionTemplate(transactionManager);
```

Create + commit:

```java
Long orderId = tx.execute(status -> {
    PurchaseOrder order = new PurchaseOrder(
        "PO-" + UUID.randomUUID()
    );

    order.addLine(new OrderLine(
        "SKU-A",
        new BigDecimal("10.00")
    ));

    em.persist(order);
    em.flush();
    return order.getId();
});
```

Sau khi `execute` trả thành công, callback transaction đã kết thúc theo semantics của template.

Verify trong transaction khác:

```java
Integer lines = tx.execute(status -> {
    PurchaseOrder order =
        em.find(PurchaseOrder.class, orderId);

    return order.getLines().size();
});

assertEquals(1, lines);
```

`em` minh họa là Spring-injected transaction-aware EntityManager proxy. Đoạn code cần đứng trong test/service với `transactionManager` phù hợp và **không có outer transaction** vô tình khiến các callbacks cùng tham gia giao dịch.

### 33.1. Cẩn thận propagation REQUIRED

`TransactionTemplate` default thường sử dụng propagation REQUIRED; nếu đã có active transaction, nó có thể join thay vì tạo transaction mới.

Nếu test yêu cầu hai transaction độc lập, cần xác định outer boundary, không chỉ nhìn hai lời gọi `execute()`.

---

# Phần X — Những bẫy tạo test xanh giả

## 34. Chỉ kiểm tra object graph trong cùng context

```java
order.addLine(line);

assertSame(order, line.getOrder());
assertEquals(1, order.getLines().size());
```

Tốt cho unit test, **không đủ** cho JPA integration test.

## 35. Chỉ gọi flush, không commit

```java
em.persist(order);
em.flush();
```

Chưa chứng minh committed state. Cần commit và đọc từ context mới.

## 36. Gọi persist riêng cho child trong bài test cascade

```java
em.persist(order);
em.persist(line);
```

Test có thể xanh dù parent không có cascade PERSIST. Muốn test cascade, chỉ persist root.

## 37. Chỉ xóa parent khi muốn test orphanRemoval

```java
em.remove(order);
```

Có thể test cascade REMOVE hoặc DB ON DELETE CASCADE, không chứng minh **xóa child khỏi association khi parent vẫn tồn tại**.

## 38. Database FK ON DELETE CASCADE che ORM behavior

Parent xóa, children biến mất vì DB trigger/constraint. Nếu muốn kiểm thử JPA REMOVE cascade riêng, cần kiểm soát schema hoặc inspect provider SQL.

## 39. Test với child mới chưa persist

Tạo line mới rồi bỏ khỏi collection trước khi persist parent: không có persisted orphan để xóa. Không chứng minh orphanRemoval.

## 40. Chuyển child giữa parents trong orphanRemoval=true

Provider có thể schedule child DELETE. Không coi đây là một portable owner-FK update test.

## 41. Không cập nhật owning property

Java inverse collection thay đổi nhưng FK có thể không thay đổi. Public helper phải giữ hai phía đồng bộ.

## 42. equals/hashCode làm Set.remove thất bại

Entity chuyển từ ID null sang ID generated có thể đổi hash nếu hashCode dựa trực tiếp vào mutable ID. Khi `Set.remove()` không tìm thấy item, orphan removal không có association change để phát hiện.

## 43. Đổi hẳn collection reference

Hibernate-managed collection wrapper có tracking semantics. Thay instance collection tùy tiện có thể gây lỗi orphan tracking. Nên dùng domain methods.

## 44. Query bulk DELETE được coi như em.remove()

```java
em.createQuery(
    "DELETE FROM OrderLine l WHERE l.order.id = :id"
)
.setParameter("id", orderId)
.executeUpdate();
```

Bulk JPQL DML không có cùng per-entity lifecycle/cascade semantics. Managed entities có thể stale; không dùng để chứng minh orphanRemoval.

## 45. Dùng H2 auto-generated schema để chứng minh PostgreSQL migration

H2/DDL do ORM tạo có thể khác production FK/unique constraints. Test migration thật nếu mục tiêu là production schema fidelity.

## 46. Assert chính xác thứ tự SQL DELETE/UPDATE một cách portable

JPA không hứa mọi SQL ordering cụ thể. Nếu SQL order là vấn đề optimization/driver riêng, ghi rõ provider/dialect/version và test ở lớp phù hợp.

## 47. Test với outer @Transactional rồi tưởng commit thật

Test framework rollback outer transaction khiến fixtures chưa bao giờ committed. Với các câu hỏi về commit visibility cần boundary độc lập.

---

# Phần XI — Bảng tình huống và phương án kiểm thử

## 48. Ma trận kiểm thử đề xuất

| Tình huống | Operation chính | Kết quả phải verify sau commit |
| --- | --- | --- |
| Thêm child mới vào parent mới | `parent.addLine(child); em.persist(parent)` | Parent và child tồn tại, FK đúng |
| Thêm child mới vào parent managed | `addLine` + cascade phù hợp | Child row mới, owning FK đúng |
| Remove persisted child | `parent.removeLine(child)` | Child bị DELETE, parent vẫn tồn tại |
| Remove parent | `em.remove(parent)` | Parent mất; children xử lý theo cascade/DB policy |
| Không có cascade PERSIST | Chỉ persist parent | Không mặc định child được persist |
| Không có orphanRemoval | Tách child | Không mặc định child bị DELETE |
| Update owning FK (movable model) | Set owning association | FK chuyển sang parent mới |
| Chỉ inverse thay đổi | Diagnostic negative test | Không dựa vào graph không nhất quán |
| One-to-one remove profile | Set inverse/owning null đúng cách | Profile bị DELETE, account còn |
| Many-to-many remove tag | Remove join association | Join row mất, shared Tag còn |
| ElementCollection remove | Remove value | Collection table đúng |
| Remove new transient child | Add rồi remove trước persist | Không cần DELETE persisted row |
| Orphan remove + rollback | Remove, flush, rollback | DB row vẫn tồn tại |
| Merge detached parent | Merge graph hợp lệ | Child changes theo cascade MERGE |
| Bulk DML | JPQL/native UPDATE/DELETE | L1 synchronization riêng, không mặc định cascade |
| Test schema constraints | Thao tác invalid FK/NOT NULL | DB từ chối đúng constraint |
| Concurrent edit | Hai transactions | Conflict/rollback theo locking policy |
| Soft delete | Domain-specific update | Không mặc định orphan removal |
| Pagination collection | Fetch graph/slice | Không xóa children ngoài phần dữ liệu được update có chủ đích |

---

## 49. Chẩn đoán lỗi thực tế

### Triệu chứng: child không được insert

Kiểm tra:

- Có `CascadeType.PERSIST` ở association được persist không?
- Đã gọi `em.persist(parent)` hay chỉ dựng object graph?
- Child có owning property trỏ parent không?
- Transaction đã flush/commit chưa?
- Child có thuộc cùng persistence unit và mapping đúng không?
- Có thiếu FK/NOT NULL value không?

### Triệu chứng: child tồn tại nhưng order_id NULL

Kiểm tra:

- `OrderLine.order` có được set không?
- `mappedBy` có đúng property không?
- Có chỉ sửa parent inverse collection không?
- DB FK có nullable sai policy không?
- Có native DML/bulk update thay state không?

### Triệu chứng: remove khỏi collection nhưng DB row còn

Kiểm tra:

- `orphanRemoval=true` có ở association đúng không?
- Child đã persistent hay còn transient?
- Collection có thực sự remove item không?
- Equals/hashCode của Set/List có làm remove thất bại không?
- Có flush/commit không?
- Test có đọc từ fresh context không?
- Helper có update owning side không?

### Triệu chứng: FK NOT NULL violation khi remove child

Có thể mapping `orphanRemoval=false` nhưng helper set child FK null. Nếu domain cho phép child bị xóa, cân nhắc orphanRemoval và test DELETE; nếu domain cho phép child tồn tại độc lập, xem lại nullable FK/policy.

### Triệu chứng: xóa parent làm mất dữ liệu dùng chung

Có thể cấu hình CascadeType.REMOVE/ALL trên association tới shared entity, hoặc DB `ON DELETE CASCADE` quá rộng. Xem lại domain ownership và test negative cases.

### Triệu chứng: test pass nhưng production khác

Có thể:

- Hibernate/JPA provider version khác.
- Test schema do Hibernate tạo thay vì migration.
- FK ON DELETE khác nhau.
- DB isolation/collation khác.
- `@DataJpaTest` rollback và không có commit thật.
- Test chỉ assert Java collection.

---

# Phần XII — Bài tập có lời giải

## 50. Câu hỏi tình huống

### Bài 1. Bên nào sở hữu FK trong bidirectional OneToMany?

**Lời giải:** `OrderLine.order` với `@ManyToOne/@JoinColumn`; parent `lines` dùng `mappedBy` là inverse.

### Bài 2. `mappedBy="order_id"` đúng không?

**Lời giải:** Sai nếu không có Java property tên `order_id`. `mappedBy` trỏ property sở hữu `order`.

### Bài 3. `order.getLines().add(line)` đã đủ chưa?

**Lời giải:** Không. Cần cập nhật `line.order` và kiểm thử FK sau commit.

### Bài 4. Domain helper cần làm gì?

**Lời giải:** Thêm/xóa collection đồng thời gán/bỏ owning association, giữ Java graph nhất quán.

### Bài 5. `CascadeType.PERSIST` có làm owner đổi phía không?

**Lời giải:** Không. Cascade lifecycle độc lập với ownership của association.

### Bài 6. Chỉ persist parent và child vẫn tồn tại?

**Lời giải:** Đó là hướng kiểm thử PERSIST cascade phù hợp, nếu mapping/graph và transaction đúng.

### Bài 7. Persist parent rồi persist child riêng?

**Lời giải:** Không chứng minh cascade PERSIST; child tồn tại có thể do lời gọi persist riêng.

### Bài 8. Xóa parent khiến child biến mất có chứng minh orphanRemoval?

**Lời giải:** Không tách biệt được cascade REMOVE, orphan semantics hoặc DB ON DELETE CASCADE.

### Bài 9. Test orphanRemoval chính xác?

**Lời giải:** Persist/commit parent và child; transaction mới remove child khỏi association, commit; fresh EM xác minh child DELETE, parent tồn tại.

### Bài 10. Child new bị remove khỏi collection trước persist?

**Lời giải:** Không có persisted row phải DELETE; không phải test đủ cho orphanRemoval.

### Bài 11. `orphanRemoval=false`, child FK nullable?

**Lời giải:** Khi owning association được set null, DB có thể lưu child không thuộc parent nếu policy/schema cho phép; không tự DELETE.

### Bài 12. `orphanRemoval=false`, FK NOT NULL?

**Lời giải:** Tách child bằng cách set FK null có thể gây constraint violation. Cần sửa lifecycle policy hoặc schema.

### Bài 13. Child đã orphan rồi add vào parent khác?

**Lời giải:** Không nên dựa vào behavior này khi orphanRemoval=true. Dùng model cho phép reparent hoặc workflow khác.

### Bài 14. `CascadeType.REMOVE` ở ManyToOne child→parent?

**Lời giải:** Có thể khiến xóa một child lan truyền xóa parent, thường sai business ownership.

### Bài 15. `CascadeType.ALL` ở shared Product?

**Lời giải:** Nguy hiểm, đặc biệt REMOVE. Product có vòng đời độc lập với order line.

### Bài 16. Xóa tag khỏi many-to-many?

**Lời giải:** Xóa association join row, không tự xóa Tag shared row. `orphanRemoval` không dùng cho ManyToMany.

### Bài 17. One-to-one mappedBy ở đâu?

**Lời giải:** Phía inverse khai báo `mappedBy` trỏ tới owning property; bên có FK `@JoinColumn` là owning side trong ví dụ.

### Bài 18. Thay profile mới bị UNIQUE conflict?

**Lời giải:** Có thể do FK unique và SQL ordering. Test cụ thể DB/provider, thiết kế replacement workflow đúng.

### Bài 19. `@ElementCollection` có phải entity orphanRemoval?

**Lời giải:** Không. Value collection có lifecycle theo owner nhưng không dùng cùng cơ chế orphanRemoval của entity association.

### Bài 20. Flush đã xóa row nhưng rollback?

**Lời giải:** DB undo trong transaction rollback; Java graph có thể không tự khôi phục. Verify bằng context mới.

### Bài 21. `em.contains(line)` chứng minh row committed?

**Lời giải:** Không. Nó chỉ cho biết membership trong persistence context.

### Bài 22. `getLines().size()` sau remove bằng 1?

**Lời giải:** Chỉ chứng minh Java collection; cần fresh EM hoặc native SELECT sau commit.

### Bài 23. Hibernate collection wrapper bị thay mới?

**Lời giải:** Có thể ảnh hưởng orphan tracking. Ưu tiên mutate managed collection qua helpers.

### Bài 24. `Set.remove()` không tìm thấy child?

**Lời giải:** Xem equals/hashCode và generated ID/mutable fields; orphanRemoval không thể xử lý một phần tử mà collection không thực sự tách.

### Bài 25. `@DataJpaTest` mặc định rollback?

**Lời giải:** Thường có. PersistAndFlush không chứng minh commit; cần transaction boundary riêng khi test committed state.

### Bài 26. Testcontainers H2 hay PostgreSQL?

**Lời giải:** Chọn DB tương ứng production khi kiểm tra FK/orphan semantics và migration, tránh dựa vào H2 behavior như chuẩn của PostgreSQL.

### Bài 27. ORM schema create-drop chứng minh Flyway đúng?

**Lời giải:** Không. Nó có thể che migration thiếu; test migration riêng trên database sạch.

### Bài 28. Query bulk DELETE có gọi cascade REMOVE?

**Lời giải:** Không mặc định; bulk JPQL bypass per-entity lifecycle/cascade. Xem context stale và database constraints.

### Bài 29. SQL DELETE child xuất hiện lúc nào?

**Lời giải:** Thường ở flush hoặc commit; không bắt buộc ngay khi gọi helper remove khỏi collection.

### Bài 30. Cần test query native order_id?

**Lời giải:** Hữu ích để xác nhận cột FK thực tế, song JPA graph test vẫn cần để kiểm chứng mapping semantics.

### Bài 31. Cascade MERGE trả về object nào?

**Lời giải:** `em.merge(detached)` trả managed instance; detached input không tự trở thành managed.

### Bài 32. Merge graph từ DTO thiếu children?

**Lời giải:** Có thể gây xóa ngoài ý muốn nếu orphanRemoval và collection semantics được áp dụng. Dùng domain commands/authorization và test rõ partial update.

### Bài 33. Query từ context cũ sau rollback?

**Lời giải:** Không dùng stale managed state làm bằng chứng DB; mở context mới.

### Bài 34. Parent xóa child bởi DB ON DELETE CASCADE?

**Lời giải:** Đó là DB constraint behavior; không đồng nghĩa JPA đã gọi remove cho từng child.

### Bài 35. Assertion tối thiểu khi xóa orphan?

**Lời giải:** Child đã persist từ trước, parent vẫn có, orphan không còn sau commit, child còn lại vẫn có, xác minh bằng EntityManager mới.

---

## 51. Checklist triển khai và kiểm thử

### Phía sở hữu

1. Có xác định `@JoinColumn`/join table và owning side đúng chưa?
2. `mappedBy` có trỏ đúng Java property?
3. Domain helper có cập nhật hai phía?
4. Có tránh public mutable collection không?
5. Positive test có verify FK bằng context mới?
6. Negative test có tránh dựa vào behavior graph không nhất quán?
7. Unidirectional mapping có được kiểm tra DDL riêng?
8. Many-to-many join table có được kiểm tra đúng?

### Cascade

9. Cascade PERSIST được test bằng cách chỉ persist root?
10. Cascade MERGE được test bằng detached graph hợp lệ?
11. Cascade REMOVE được test bằng remove parent?
12. Có tránh REMOVE/ALL trên shared reference entities?
13. Có phân biệt cascade direction?
14. Có kiểm tra lifecycle callbacks/soft delete policy?
15. Có phân biệt JPA cascade và DB ON DELETE CASCADE?

### orphanRemoval

16. Chỉ dùng cho OneToOne/OneToMany phù hợp?
17. Có test child **đã persist** rồi bị tách?
18. Parent có còn tồn tại sau orphan deletion?
19. Children còn lại có nguyên vẹn?
20. Có tránh reparent orphan trong cùng workflow?
21. Có xử lý khác biệt khi orphanRemoval=false?
22. FK nullable/NOT NULL có khớp business lifecycle?
23. Có tránh thay collection instance tùy tiện?
24. Có test equals/hashCode, List/Set remove behavior?
25. Có kiểm soát detached merge/partial collection update?

### Transaction và DB

26. Fixture được commit trước khi test removal?
27. Có flush/commit đúng ranh giới?
28. Có verify bằng fresh EntityManager?
29. Có test rollback giữ DB row?
30. Có kiểm tra exception ở flush/commit khi cần?
31. Có dùng DB/provider mục tiêu?
32. Migrations/FK constraints có được kiểm chứng riêng?
33. Test có tránh outer transaction mặc định che commit?
34. Có tránh dùng failed context tiếp sau DB error?
35. Có test native/bulk paths riêng nếu hệ thống sử dụng?

---

## 52. Sơ đồ tư duy

```text
          JPA relationship behavior
                     |
          +----------+-----------+
          |          |           |
          v          v           v
       Owning      Cascade    orphanRemoval
        side          |           |
          |           |           |
          v           v           v
   Ai ghi liên     persist/     Xóa target
   kết DB?         merge/       bị loại khỏi
                   remove       association?
          |           |           |
          +-----------+-----------+
                      |
                      v
             Java graph consistent?
                      |
                      v
          Transaction -> flush -> commit
                      |
                      v
              NEW EntityManager
                      |
                      v
             Query committed DB state
                      |
                      v
         Assert FK, child rows, parent rows
```

Một bài test chỉ assert Java graph mới kiểm tra **nửa đầu** của sơ đồ.

---

## 53. Kết luận

Để kiểm thử **phía sở hữu, cascade và orphanRemoval** đúng trong JPA, cần phân biệt ba lớp:

- **Owning side:** xác định property quản lý quan hệ lưu trong database; trong bidirectional `@OneToMany(mappedBy="order")`/`@ManyToOne`, FK do `OrderLine.order` kiểm soát.
- **Cascade:** quyết định lifecycle operations như `PERSIST`, `MERGE`, `REMOVE` được lan truyền sang target nào, theo hướng mapping đã khai báo.
- **orphanRemoval:** quản lý vòng đời của child **đã persistent** khi nó bị tách khỏi `@OneToOne`/`@OneToMany` phù hợp, không đơn giản là một tên khác của `CascadeType.REMOVE`.

Những nguyên tắc quan trọng nhất:

1. **Luôn giữ hai phía quan hệ đồng bộ qua domain methods.** Đừng chỉ thêm/xóa khỏi inverse collection.
2. **Test CascadeType.PERSIST bằng cách chỉ persist parent**, không persist child riêng làm che lỗi.
3. **Test orphanRemoval bằng cách remove persisted child trong khi parent vẫn tồn tại**, sau đó commit.
4. **Test CascadeType.REMOVE bằng cách xóa parent**, đồng thời biết DB `ON DELETE CASCADE` có thể ảnh hưởng kết quả.
5. **Đừng chuyển child đã orphan sang parent khác** nếu mapping xem child có vòng đời sở hữu bởi parent.
6. **Không dùng REMOVE/ALL trên shared entities** khi việc xóa parent không được phép xóa target.
7. **`flush()` không phải commit; `EntityManager` hiện tại có thể trả object từ L1.**
8. **Đọc lại bằng EntityManager mới sau commit** để xác nhận FK/DELETE/INSERT thực sự tồn tại trong DB.
9. **`@DataJpaTest` có thể rollback mặc định**, nên khi kiểm tra committed state phải xác định transaction boundaries.
10. **Test với database/schema mục tiêu** khi điều quan trọng là FK, DDL, SQL ordering hoặc migration.
11. **Orphan deletion, association unlink và database ON DELETE CASCADE là ba cơ chế khác nhau**.
12. **Tránh merge partial detached graph một cách mù quáng** khi orphanRemoval có thể diễn giải missing children như deletion.

**Một quan hệ JPA chỉ được kiểm thử đầy đủ khi test chứng minh Java graph nhất quán, thao tác lifecycle đúng và database sau commit có đúng các khóa ngoại và rows còn tồn tại theo hợp đồng nghiệp vụ.**
