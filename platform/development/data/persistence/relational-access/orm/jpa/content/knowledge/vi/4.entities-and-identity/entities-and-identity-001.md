# Điều kiện để một lớp trở thành entity trong JPA

## 1. Entity là gì và vì sao một Java class chưa chắc là entity?

Trong kiến trúc **Data Persistence / Relational Access / ORM / JPA**, một *entity* là đối tượng miền nghiệp vụ có **danh tính riêng** và có thể được JPA quản lý, lưu trữ, truy vấn hoặc cập nhật dựa trên dữ liệu quan hệ. Lớp Java định nghĩa loại đối tượng đó gọi là **entity class**.

Ví dụ ứng dụng bán hàng có `Product`, `Customer` và `Order`. Một đối tượng `Product` có thể đại diện cho bản ghi sản phẩm trong bảng dữ liệu. Khi đối tượng trở thành *managed* trong một **persistence context**, JPA provider có thể theo dõi các thay đổi của nó và đồng bộ xuống cơ sở dữ liệu trong transaction thích hợp.

Tuy vậy, không phải cứ tạo một lớp Java với các field giống cột database là lớp đó trở thành entity:

```java
public class Product {
    private Long id;
    private String name;
}
```

Đoạn mã trên mới là một POJO (*Plain Old Java Object*). Để JPA nhận biết và quản lý lớp, nó phải đáp ứng **những điều kiện về khai báo, cấu trúc lớp, định danh và ánh xạ**.

> **Phân biệt hai việc:** (1) Một lớp **hợp lệ về mặt đặc tả** để làm entity; (2) lớp đó **thực sự được ứng dụng đăng ký/khám phá** trong một persistence unit và có provider để vận hành. Cả hai đều cần nếu muốn thao tác entity qua `EntityManager`.

Bài này dùng tên API hiện đại trong gói `jakarta.persistence`. Tài liệu JPA đời cũ có thể dùng `javax.persistence`; khi áp dụng vào project, cần dùng đúng hệ phiên bản API và provider của project.

## 2. Các điều kiện bắt buộc theo Jakarta Persistence

Với mã entity viết theo **Jakarta Persistence 3.2**, các yêu cầu cơ bản của entity class gồm:

| Nhóm điều kiện | Yêu cầu | Lý do |
|---|---|---|
| Khai báo entity | Gắn `@Entity` **hoặc** khai báo là entity trong XML ORM descriptor. | JPA phải nhận biết lớp là entity, không chỉ là POJO thông thường. |
| Dạng lớp | Lớp top-level hoặc `static` nested class; không phải `interface`, `enum` hay Java `record`. | Entity cần mô hình instance và vòng đời do provider quản lý. |
| Tính kế thừa | Lớp entity phải **không `final`**; các phương thức và field lưu trữ bền vững cũng không được `final`. | Đáp ứng hợp đồng của đặc tả và khả năng quản lý state của provider. |
| Constructor | Có constructor **không tham số** (`no-arg constructor`), với mức truy cập `public` hoặc `protected`. | Provider cần khởi tạo entity. |
| Định danh | Có định danh chính được ánh xạ bằng `@Id` hoặc `@EmbeddedId`, có thể **kế thừa từ entity/mapped superclass**. | JPA cần phân biệt các entity theo khóa chính. |
| Trạng thái lưu trữ | Những field/property cần lưu trữ phải có kiểu và cách ánh xạ phù hợp JPA. | Provider phải chuyển đổi state Java thành dữ liệu quan hệ. |
| Cách truy cập state | Ánh xạ nhất quán theo field access hoặc property access, hoặc phối hợp có khai báo rõ `@Access`. | Provider cần biết đọc/ghi state ở vị trí nào. |

**Lưu ý theo phiên bản:** Jakarta Persistence 3.2 cho phép entity là `static` nested class. Các phiên bản Jakarta Persistence 3.0/3.1 trước đó yêu cầu entity là **top-level class**. Nếu muốn mã tương thích rộng với nhiều bản JPA, chọn top-level class là cách đơn giản nhất.

Ngoài các điều kiện bắt buộc, rất nhiều annotation hay gặp như `@Table`, `@Column`, `@GeneratedValue`, `@Version`, `@OneToMany` là **tùy tình huống**, không bắt buộc với mọi entity.

## 3. Khai báo entity bằng `@Entity` hoặc metadata XML

### 3.1. Cách phổ biến: `@Entity`

```java
package com.example.catalog;

import jakarta.persistence.Entity;

@Entity
public class Product {
    // Còn cần constructor, khóa chính và state hợp lệ.
}
```

`@Entity` thuộc gói `jakarta.persistence`. Việc annotation xuất hiện giúp provider biết ý định ánh xạ lớp thành một entity, nhưng **chỉ thêm `@Entity` chưa đủ**: lớp còn cần đáp ứng các yêu cầu khác, đặc biệt là định danh.

Theo mặc định, *entity name* là tên lớp đơn giản. Entity name được dùng trong JPQL:

```java
@Entity
public class Product {
    // ...
}
```

Truy vấn:

```java
List<Product> products = em.createQuery(
        "SELECT p FROM Product p", Product.class
).getResultList();
```

Có thể đặt tên JPQL tường minh:

```java
@Entity(name = "CatalogItem")
@Table(name = "products")
public class Product {
    // ...
}
```

Khi đó:

- `Product` là tên lớp Java.
- `CatalogItem` là **entity name** dùng trong JPQL: `SELECT p FROM CatalogItem p`.
- `products` là **tên bảng SQL** chỉ định bằng `@Table(name = "products")`.

Không nên nhầm entity name với tên bảng. JPQL làm việc với **entity/property**, còn SQL làm việc với **table/column**.

### 3.2. Cách thay thế: XML mapping

Đặc tả cũng cho phép khai báo entity trong descriptor XML, chẳng hạn `META-INF/orm.xml`, thay vì chỉ dựa vào `@Entity`. Ví dụ ở mức ý tưởng:

```xml
<entity-mappings xmlns="https://jakarta.ee/xml/ns/persistence/orm"
                 version="3.2">
    <entity class="com.example.catalog.Product"
            access="FIELD">
        <attributes>
            <id name="id"/>
            <basic name="name"/>
        </attributes>
    </entity>
</entity-mappings>
```

Tài liệu XML phải được hệ thống JPA nhận diện qua cấu hình phù hợp (chẳng hạn persistence unit) và lớp vẫn cần đáp ứng điều kiện về constructor, kiểu lớp và định danh. Annotation và XML là **hai cơ chế cung cấp metadata**; chúng không thay đổi bản chất entity.

Trong các project thông dụng, `@Entity` kết hợp các annotation ánh xạ rõ ràng thường dễ đọc và dễ bảo trì hơn.

## 4. Entity phải là loại lớp Java phù hợp

### 4.1. Lớp thường, có thể kế thừa, nhưng không `final`

Một entity có thể là lớp cụ thể hoặc lớp `abstract`, có thể mở rộng entity khác hoặc lớp không phải entity. Tuy nhiên, **entity class không được khai báo `final`** theo đặc tả, và không được có phương thức hoặc field persistent bị khai báo `final`.

**Không hợp lệ theo JPA chuẩn:**

```java
@Entity
public final class Product {
    @Id
    private Long id;

    protected Product() {}
}
```

Một lớp `final` không cho phép provider mở rộng lớp theo những cơ chế thường dùng. Một số provider có thể chấp nhận cấu trúc ngoài đặc tả trong những trường hợp đặc biệt, nhưng dựa vào hành vi riêng của provider làm giảm tính di động.

**Ví dụ một field không phù hợp:**

```java
@Entity
public class Product {
    @Id
    private Long id;

    private final String name = "Unknown"; // Persistent field final: không hợp lệ.

    protected Product() {}
}
```

Nếu cần bất biến về mặt nghiệp vụ, hãy **không cung cấp setter tùy ý** và cập nhật qua phương thức nghiệp vụ có kiểm soát. Việc giữ field persistent không `final` không đồng nghĩa phải cho mọi nơi sửa field đó.

### 4.2. Top-level class và static nested class

Các kiểu sau không thể trực tiếp là entity:

- `interface`: không phải một lớp instance như entity yêu cầu.
- `enum`: có thể là **kiểu của một thuộc tính** được lưu, nhưng bản thân enum không phải entity.
- Java `record`: không được dùng làm entity trong Jakarta Persistence 3.2. Một `record` có thể dùng cho các mục đích khác như DTO và, theo hỗ trợ phiên bản, embeddable.
- **Non-static inner class**: giữ tham chiếu ngầm đến object lớp ngoài, không đáp ứng dạng entity class cho phép.

Vì vậy, một khai báo rõ ràng, ít phụ thuộc phiên bản là:

```java
package com.example.catalog;

@Entity
public class Product {
    // Top-level, non-final.
}
```

### 4.3. Constructor không tham số, `public` hoặc `protected`

JPA cần một constructor không tham số để khởi tạo entity bằng provider. Dạng phổ biến:

```java
@Entity
public class Product {
    @Id
    private Long id;
    private String name;

    protected Product() {
        // Dành cho JPA provider.
    }

    public Product(String name) {
        this.name = name;
    }
}
```

- Constructor không tham số có thể là `public` hoặc `protected`.
- Có thể khai báo thêm các constructor nghiệp vụ để bảo đảm entity được tạo với trạng thái hợp lệ.
- **Chỉ có constructor nhận tham số không đủ**: khi đã khai báo constructor nhận tham số, Java sẽ không tự tạo constructor mặc định.

**Không hợp lệ theo đặc tả:**

```java
@Entity
public class Product {
    @Id
    private Long id;

    public Product(String name) {
        // Không có constructor không tham số.
    }
}
```

Cũng không nên dựa vào constructor `private` hoặc package-private chỉ vì một provider có thể xử lý được; hợp đồng Jakarta Persistence yêu cầu `public` hoặc `protected`.

Nếu lớp hoàn toàn không khai báo constructor, Java có thể sinh constructor mặc định; tuy nhiên, việc khai báo `protected Product() {}` một cách tường minh thường làm ý đồ JPA rõ hơn và tránh lỗi khi sau này thêm constructor nhận tham số.

## 5. Entity phải có định danh: `@Id` hoặc `@EmbeddedId`

### 5.1. Khóa chính đơn

Mỗi entity cần có **khóa chính** để JPA nhận diện từng instance. Với khóa đơn, dùng `@Id`:

```java
@Entity
public class Product {
    @Id
    private Long id;

    protected Product() {}
}
```

Khóa chính thường tương ứng với cột `PRIMARY KEY` của bảng. Các giá trị ID của những entity cùng kiểu phải phân biệt được từng bản ghi trong phạm vi mapping.

Nếu database sinh khóa, có thể dùng `@GeneratedValue`:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

`@GeneratedValue` **không bắt buộc** để trở thành entity. Nếu không dùng nó, ứng dụng cần có chiến lược gán khóa đúng trước khi lưu. Chọn `IDENTITY`, `SEQUENCE`, `TABLE`, `UUID` hoặc chiến lược khác phụ thuộc loại khóa, phiên bản JPA, provider và khả năng database. Ví dụ dùng `Long` và `IDENTITY` khi database hỗ trợ cột tự sinh giá trị.

**Khóa chính có thể được kế thừa.** Ví dụ:

```java
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    protected Long id;

    protected BaseEntity() {}

    public Long getId() {
        return id;
    }
}
```

Và:

```java
import jakarta.persistence.Entity;

@Entity
public class Product extends BaseEntity {
    private String name;

    protected Product() {}

    public Product(String name) {
        this.name = name;
    }
}
```

`Product` vẫn có khóa chính vì thừa hưởng mapping `id`. `BaseEntity` là `@MappedSuperclass`: nó đóng góp các mapping cho lớp con nhưng **không phải entity độc lập** và không có vòng đời/truy vấn JPQL như một entity riêng.

### 5.2. Khóa chính tổng hợp

Nếu định danh gồm nhiều thành phần, JPA hỗ trợ các cách như `@EmbeddedId` hoặc `@IdClass`. Ví dụ một dòng đơn hàng được xác định bằng mã đơn và số thứ tự dòng:

```java
import jakarta.persistence.Embeddable;
import java.io.Serializable;
import java.util.Objects;

@Embeddable
public class OrderLineId implements Serializable {
    private Long orderId;
    private Integer lineNumber;

    protected OrderLineId() {}

    public OrderLineId(Long orderId, Integer lineNumber) {
        this.orderId = orderId;
        this.lineNumber = lineNumber;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof OrderLineId other)) return false;
        return Objects.equals(orderId, other.orderId)
                && Objects.equals(lineNumber, other.lineNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hash(orderId, lineNumber);
    }
}
```

Entity dùng khóa tổng hợp:

```java
import jakarta.persistence.EmbeddedId;
import jakarta.persistence.Entity;

@Entity
public class OrderLine {
    @EmbeddedId
    private OrderLineId id;

    private Integer quantity;

    protected OrderLine() {}

    public OrderLine(OrderLineId id, Integer quantity) {
        this.id = id;
        this.quantity = quantity;
    }
}
```

**Lưu ý:** Khóa tổng hợp có yêu cầu bổ sung đối với lớp định danh (chẳng hạn tính bằng nhau của các thành phần khóa, `equals/hashCode`; khả năng tuần tự hóa khi dùng khóa dạng class). Các yêu cầu dành cho **lớp khóa** không nên nhầm với yêu cầu dành cho **entity class**.

Nếu không có khóa chính trong entity hoặc mapping được kế thừa, thì lớp không đáp ứng mô hình entity JPA chuẩn.

## 6. Trạng thái persistent và chiến lược truy cập

### 6.1. Hai kiểu access hợp lệ

JPA provider có thể đọc và ghi trạng thái bằng hai cách:

1. **Field access:** truy cập trực tiếp field. Đặt `@Id` và các annotation mapping lên field.
2. **Property access:** truy cập bằng getter/setter JavaBeans. Đặt `@Id` và annotation mapping lên getter.

JPA suy ra kiểu access mặc định của một entity hierarchy dựa trên vị trí metadata, đặc biệt vị trí `@Id` hoặc `@EmbeddedId`, nếu không khai báo `@Access` rõ ràng.

**Field access:**

```java
@Entity
public class Product {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Product() {}

    public String getName() {
        return name;
    }
}
```

Provider đọc và ghi **field**, do đó getter/setter không phải điều kiện bắt buộc cho mọi field. Ứng dụng vẫn nên có phương thức để truy cập trạng thái và thực thi logic nghiệp vụ.

**Property access:**

```java
@Entity
@Access(AccessType.PROPERTY)
public class ProductView {
    private Long id;
    private String name;

    protected ProductView() {}

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @Column(nullable = false)
    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Trong ví dụ này, `@Id` và `@Column` nằm trên getter; provider sử dụng các phương thức accessor, và các accessor persistent phải có mức truy cập phù hợp theo đặc tả.

**Tránh vô tình trộn metadata** giữa field và getter trong cùng hierarchy. Nếu cần trộn ở những thuộc tính cụ thể, dùng `@Access(AccessType.FIELD)` hoặc `@Access(AccessType.PROPERTY)` và nắm rõ quy tắc mapping của JPA.

### 6.2. Field nào được lưu xuống database?

Ở **field access**, các instance field không bị đánh dấu `transient` theo Java và không có `@Transient` thường được xem là persistent theo mặc định, miễn là kiểu dữ liệu đó ánh xạ được. Field `static` không đại diện cho state riêng của từng entity nên không được lưu như thuộc tính instance.

Ví dụ:

```java
@Entity
public class Product {
    @Id
    private Long id;

    private String name;             // Persistent
    private java.math.BigDecimal price; // Persistent

    @Transient
    private String displayLabel;     // Không lưu vào DB

    private transient String token;  // Không lưu vào DB

    private static final String TYPE = "PRODUCT"; // Hằng số của class

    protected Product() {}
}
```

Các loại thuộc tính có thể ánh xạ gồm:

- Các kiểu cơ bản như `String`, kiểu số, `boolean`, `BigDecimal`, `LocalDate`, `Instant` (tùy phiên bản và mapping).
- Kiểu enum khi được ánh xạ theo quy định.
- Các lớp `@Embeddable`, dùng để nhúng nhóm giá trị vào entity.
- Quan hệ đến entity khác: `@ManyToOne`, `@OneToOne`, `@OneToMany`, `@ManyToMany`.
- Collection các giá trị cơ bản hoặc embeddable thông qua `@ElementCollection`.

Một field có kiểu Java tùy ý **không tự được lưu** nếu provider không biết ánh xạ nó sang database. Khi cần chuyển đổi kiểu riêng, có thể dùng `AttributeConverter` / `@Convert` hoặc mapping phù hợp.

### 6.3. Tên bảng và tên cột không phải điều kiện khai báo bắt buộc

`@Table` và `@Column` giúp kiểm soát SQL mapping nhưng **không nhất thiết phải có**.

```java
@Entity
@Table(name = "catalog_products")
public class Product {
    @Id
    @Column(name = "product_id")
    private Long id;

    @Column(name = "product_name", nullable = false, length = 200)
    private String name;

    protected Product() {}
}
```

Nếu bỏ `@Table` và `@Column`, JPA sử dụng quy tắc tên mặc định (kèm quy tắc naming của provider/cấu hình). Việc tên mặc định có khớp schema hiện có hay không là một vấn đề **cấu hình ánh xạ**, không phải lý do để nói rằng lớp thiếu `@Table` thì không thể là entity.

## 7. Ví dụ entity hoàn chỉnh

Đây là một entity `Product` tiêu biểu dùng **field access** và khóa chính sinh tự động. Ví dụ minh họa cấu trúc hợp lệ mà ứng dụng bán hàng có thể sử dụng:

```java
package com.example.catalog;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;
import jakarta.persistence.Version;
import java.math.BigDecimal;

@Entity(name = "Product")
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    @Transient
    private String formattedPrice;

    protected Product() {
        // Để provider có thể khởi tạo entity.
    }

    public Product(String name, BigDecimal price) {
        changeName(name);
        changePrice(price);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void changeName(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không được trống");
        }
        this.name = newName;
    }

    public void changePrice(BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Giá sản phẩm phải >= 0");
        }
        this.price = newPrice;
    }
}
```

Mỗi thành phần trong đoạn mã có vai trò riêng:

| Thành phần | Mục đích | Có bắt buộc với mọi entity? |
|---|---|---|
| `@Entity` | Khai báo lớp là entity bằng annotation. | **Có**, nếu không khai báo tương đương trong XML. |
| `@Table(name = "products")` | Đặt tên bảng database. | Không. |
| `@Id` | Xác định khóa chính. | **Có** (hoặc `@EmbeddedId`; có thể được kế thừa). |
| `@GeneratedValue` | Đề nghị provider/database sinh ID. | Không. |
| `@Column` | Tùy chỉnh ánh xạ cột và metadata như nullable, length, precision. | Không. |
| `@Version` | Dùng để hỗ trợ optimistic locking. | Không. |
| `@Transient` | Loại trừ state không lưu trữ. | Không; chỉ cần khi có field/property muốn loại trừ. |
| `protected Product()` | Constructor không tham số cho JPA. | **Có**, trừ khi lớp đã có constructor không tham số public/protected hợp lệ. |
| Constructor có tham số | Bảo đảm đầu vào khi tạo entity từ mã nghiệp vụ. | Không. |
| Getter và phương thức `change...` | Cung cấp API nghiệp vụ để đọc/sửa state có kiểm soát. | Không bắt buộc cho field access, nhưng thường nên có. |

`@Version` là một cơ chế giúp phát hiện hai transaction cùng cập nhật một entity theo **optimistic locking**. Đây là lựa chọn thiết kế cho quản lý xung đột dữ liệu, không phải điều kiện để lớp có thể được JPA nhận diện là entity.

### Ví dụ sử dụng qua `EntityManager`

Giả sử persistence unit đã đăng ký lớp `com.example.catalog.Product` và provider/database đã được cấu hình:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Product product = new Product(
                "Bàn phím cơ",
                new BigDecimal("1290000.00")
        );

        em.persist(product);

        // Khi product là managed, JPA theo dõi các thay đổi.
        product.changePrice(new BigDecimal("1190000.00"));

        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Mẫu `EntityTransaction` trên dành cho persistence unit **`RESOURCE_LOCAL`**. Nếu ứng dụng dùng JTA/container-managed transaction, transaction được điều phối theo cơ chế tương ứng và không dùng `em.getTransaction()` để bắt đầu/commit.

Điều kiện trở thành entity **khác** với trạng thái entity: `new Product(...)` tạo object Java ở trạng thái *new/transient*; `em.persist(product)` đưa object vào persistence context để trở thành *managed* (trong ngữ cảnh thao tác phù hợp); transaction commit mới xác nhận thay đổi database.

## 8. Entity phải được JPA provider khám phá trong persistence unit

Một lớp có `@Entity` hợp lệ chưa chắc đã được ứng dụng sử dụng thành công nếu **chưa thuộc tập managed classes** mà provider biết đến.

Ví dụ Java SE có thể đăng ký entity trong `META-INF/persistence.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="catalogPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.catalog.Product</class>
        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user" value="sa"/>
            <property name="jakarta.persistence.jdbc.password" value=""/>
            <property name="jakarta.persistence.schema-generation.database.action"
                      value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Sau đó tạo factory bằng đúng tên persistence unit:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("catalogPU");
```

Ví dụ cần Jakarta Persistence API, một provider tương thích và JDBC driver H2 trên classpath/module path phù hợp. `drop-and-create` chỉ dùng trong môi trường thử nghiệm vì có thể xóa dữ liệu cũ.

Tùy nền tảng, provider có thể khám phá entity thông qua quét package, classpath hoặc cách cấu hình của container/framework. Ví dụ, trong ứng dụng Spring Boot, các entity thường được tìm thấy qua phạm vi package scanning do framework cấu hình. Vì vậy cần kiểm tra **cấu hình persistence unit và phạm vi quét entity**, không suy đoán rằng `@Entity` luôn được phát hiện ở mọi nơi.

Một số lỗi thường biểu hiện bằng thông báo như `Not a managed type`, `Unknown entity` hoặc lỗi khởi tạo `EntityManagerFactory`. Nguyên nhân có thể nằm ở việc thiếu metadata, class chưa được quét, xung đột phiên bản `javax`/`jakarta`, thiếu provider hoặc mapping không hợp lệ.

## 9. Phân biệt `@Entity`, `@Embeddable` và `@MappedSuperclass`

Ba annotation này đều dùng trong mô hình persistence nhưng **không thể thay thế tùy tiện**:

| Khai báo | Ý nghĩa | Có danh tính/lifecycle entity độc lập? | Có truy vấn JPQL trực tiếp như entity riêng? |
|---|---|---|---|
| `@Entity` | Một thực thể có định danh, ánh xạ vào dữ liệu quan hệ. | Có. | Có. |
| `@Embeddable` | Nhóm giá trị nhúng vào entity khác, ví dụ địa chỉ hoặc khoảng tiền. | Không có định danh entity độc lập. | Không theo tên embeddable như entity. |
| `@MappedSuperclass` | Lớp cơ sở cung cấp mapping được kế thừa cho entity con. | Không. | Không; các entity con có thể được truy vấn. |

Ví dụ địa chỉ chỉ là thành phần của khách hàng:

```java
@Embeddable
public class Address {
    private String city;
    private String street;

    protected Address() {}
}

@Entity
public class Customer {
    @Id
    private Long id;

    @Embedded
    private Address address;

    protected Customer() {}
}
```

`Address` không cần `@Id` vì không phải entity độc lập. `Customer` cần định danh vì là entity. Một **record** trong Jakarta Persistence 3.2 có thể được dùng làm embeddable theo quy tắc của phiên bản đó, nhưng vẫn **không được dùng làm entity**.

## 10. Các ví dụ chưa đáp ứng điều kiện

### 10.1. Có `@Table` nhưng không khai báo entity

```java
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    protected Product() {}
}
```

`@Table` chỉ cung cấp metadata tên bảng; bản thân nó không khai báo một entity. Cần `@Entity` hoặc metadata XML tương đương.

### 10.2. Có `@Entity` nhưng không có khóa chính

```java
@Entity
public class Product {
    private String name;

    protected Product() {}
}
```

Lớp không có `@Id` hoặc `@EmbeddedId`, cũng không kế thừa mapping định danh; đây không phải entity mapping hợp lệ theo JPA.

### 10.3. Lớp `record`

```java
@Entity
public record Product(Long id, String name) {}
```

Không hợp lệ: record không phải dạng entity được đặc tả cho phép. Record có ích làm DTO (ví dụ kết quả truy vấn), nhưng DTO không phải một managed entity.

### 10.4. Constructor không tham số ở mức `private`

```java
@Entity
public class Product {
    @Id
    private Long id;

    private Product() {}
}
```

Không thỏa điều kiện portable JPA: constructor không tham số phải là `public` hoặc `protected`.

### 10.5. Trộn annotation field/property thiếu nhất quán

```java
@Entity
public class Product {
    @Id
    private Long id;

    private String name;

    @Column(name = "product_name")
    public String getName() {
        return name;
    }

    protected Product() {}
}
```

`@Id` trên field xác định field access mặc định, còn `@Column` trên getter có thể khiến mapping không như mong đợi hoặc rơi vào hành vi không được quy định khi trộn thiếu `@Access`. Nên đặt `@Column` cùng field `name`, hoặc định nghĩa kiểu access rõ ràng.

### 10.6. Có entity hợp lệ nhưng không được ứng dụng quản lý

```java
@Entity
public class Product {
    @Id
    private Long id;
    protected Product() {}
}
```

Lớp trên có thể hoàn toàn hợp lệ, nhưng nếu ứng dụng không đăng ký/khám phá nó trong persistence unit thì `EntityManager` vẫn không thể thao tác với nó như managed entity. Cần kiểm tra cấu hình bootstrap, quét package, tên lớp và dependencies.

## 11. Những điều không phải yêu cầu bắt buộc

Nhiều quy tắc được nhắc đến trong hướng dẫn ORM là **khuyến nghị thiết kế** hoặc **quy định riêng của công nghệ**, chứ không phải điều kiện bắt buộc để lớp trở thành JPA entity:

- **Không bắt buộc mọi entity đều khai báo `@Table`**: JPA có quy tắc tên bảng mặc định.
- **Không bắt buộc khai báo `@Column` cho mọi thuộc tính**: nhiều thuộc tính cơ bản được persistent theo quy tắc access.
- **Không bắt buộc dùng `@GeneratedValue`**: khóa chính có thể do ứng dụng gán.
- **Không bắt buộc mọi field có getter/setter public** khi dùng field access: provider đọc/ghi trực tiếp field; phương thức nghiệp vụ vẫn được khuyến nghị để bảo vệ tính hợp lệ.
- **Không bắt buộc entity luôn có `equals()` và `hashCode()` tự viết**: nhưng nếu entity tham gia `Set`, làm key trong `Map` hoặc cần so sánh theo định danh, cách hiện thực phải được cân nhắc cẩn thận. Lớp **khóa tổng hợp** có yêu cầu giá trị bằng nhau riêng.
- **Không bắt buộc entity implements `Serializable` trong mọi trường hợp**. Việc truyền detached entity theo giá trị qua biên từ xa, session serialization hoặc cơ chế phân tán có thể đòi hỏi `Serializable`; còn các lớp khóa tổng hợp cũng có yêu cầu riêng.
- **Không bắt buộc mọi entity phải có `@Version`**: nên cân nhắc nếu cần optimistic locking để phát hiện cập nhật đồng thời.
- **Không bắt buộc entity extends một lớp framework**: POJO hợp lệ và metadata JPA đủ để mô tả một entity.
- **Không bắt buộc entity đồng nhất với DTO**: entity được quản lý bởi persistence context; DTO là cấu trúc truyền dữ liệu, không mặc nhiên có danh tính và vòng đời managed.

Một lưu ý riêng với **Hibernate**: một số cấu trúc ngoài giới hạn JPA portable có thể vẫn hoạt động với Hibernate nhờ cơ chế riêng, ví dụ thay đổi mức truy cập của constructor trong một số tình huống. Khi mục tiêu là **viết mã JPA đúng đặc tả và ít lệ thuộc provider**, hãy tuân thủ yêu cầu chuẩn đã nêu.

## 12. Kiểm tra theo các tình huống thực tế

**Tình huống A — Lớp có `@Entity` và `@Id` nhưng báo `Not a managed type`.**  
Xem lại package scanning, danh sách lớp thuộc persistence unit, tên package, đường dẫn `persistence.xml` và sự phù hợp giữa API `jakarta.persistence` với provider thực tế.

**Tình huống B — Provider không khởi tạo được entity.**  
Xem lớp có constructor không tham số `public`/`protected` hay không, lớp có bị `final` hoặc là non-static inner class hay không, và metadata entity có mâu thuẫn hay không.

**Tình huống C — Chạy được nhưng SQL ghi vào cột sai tên.**  
Xem lại `@Table`, `@Column`, naming strategy và kiểu access. Điều này khác với lỗi “không phải entity”.

**Tình huống D — Một thuộc tính tưởng không lưu lại bị provider cố ánh xạ.**  
Theo field access, field instance không có `transient` hoặc `@Transient` thường persistent theo mặc định. Với state chỉ dùng tính toán, cần đánh dấu rõ là không persistent.

**Tình huống E — Thay đổi object Java nhưng database không được cập nhật.**  
Ngay cả với lớp entity hợp lệ, object có thể vẫn là `new` hoặc đã `detached`, hoặc transaction chưa commit. Cần kiểm tra trạng thái managed và ranh giới transaction, thay vì thêm annotation vào entity một cách ngẫu nhiên.

**Tình huống F — Muốn entity không cho thay đổi từ bên ngoài.**  
Không cần dùng class `final` hoặc persistent field `final`. Có thể giữ field `private`, constructor JPA `protected`, chỉ cung cấp phương thức nghiệp vụ thích hợp, và kiểm tra invariant trong các thao tác ứng dụng.

## 13. Kết luận về điều kiện để một lớp là entity

Một lớp Java được JPA quản lý thành entity khi **được khai báo bằng `@Entity` hoặc metadata XML tương đương**, **đáp ứng hình dạng lớp và constructor theo đặc tả**, **có khóa chính hợp lệ** và **có ánh xạ state nhất quán**; đồng thời ứng dụng phải đưa lớp vào tập managed classes mà provider xử lý.

Với một entity thông thường, có thể nhớ cấu trúc tối thiểu:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;

@Entity
public class SampleEntity {
    @Id
    private Long id;

    protected SampleEntity() {}
}
```

Lớp đơn giản này đã thể hiện các thành phần quan trọng: **khai báo entity, khóa chính, lớp không final và constructor không tham số có mức truy cập hợp lệ**. Những annotation khác được bổ sung dựa trên nhu cầu ánh xạ và nghiệp vụ thực tế.

### Tài liệu tham khảo chính thức

- [Jakarta Persistence 3.2 Specification — Chương 2: Entities](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html#entities)
- [Jakarta Persistence 3.2 API — `@Entity`](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/Entity.html)
- [Jakarta EE Tutorial — Introduction to Jakarta Persistence](https://jakarta.ee/learn/docs/jakartaee-tutorial/current/persist/persistence-intro/persistence-intro.html)
